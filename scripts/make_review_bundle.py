#!/usr/bin/env python3
"""make_review_bundle.py -- build the artefact a HUMAN or another model reviews.

    python scripts/make_review_bundle.py <BASE_REV> <HEAD_REV> [--notes path.md]

Why this exists: an agent's own summary is not evidence. Everything a reviewer needs
to disagree with the agent has to be in one zip -- the real transistor-level netlist,
the testbench, the checker, the parameter generator, the extracted numbers, the git
diff, and the known failures.

Layout produced (and zipped as review_bundle_<headshort>/):

    REVIEW_README.md      task, requirement classes, circuit, device list, per-phase
                          conduction, simulation setup, automatic checks with measured
                          numbers, known failures, SHAs, questions for the reviewer
    manifest.txt          every file: bytes, sha256, category
    git_status.txt        working tree state when the bundle was built
    git_log.txt           commits in BASE..HEAD
    git_diff.patch        the full diff a reviewer has to sign off
    changed_files.txt     name-status list
    source/               changed source files at their repo-relative paths
    reports/              changed reports
    results/              changed small numeric results (never a PSF database)

The bundle runs the same safety rules as the commit gate on every file it copies and
refuses to write the zip if anything looks like PDK, model card, credential or key.
"""

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402
from netlist_stats import group_of  # noqa: E402  (same classifier the count check uses)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCE_EXT = {".scs", ".il", ".awk", ".py", ".sh", ".ps1", ".mjs", ".sp", ".cir"}
RESULT_EXT = {".csv", ".json", ".txt"}
REPORT_EXT = {".md"}

MOS_RX = re.compile(
    r"^\s*(?P<inst>[mMnN][A-Za-z0-9_]*)\s*\(\s*(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+"
    r"(?P<b>\S+)\s*\)\s*(?P<model>[A-Za-z0-9_]+)\s+l=(?P<l>\S+)\s+w=(?P<w>\S+)", re.M)
PARAM_RX = re.compile(r"^\s*parameters\s+(?P<name>\w+)=(?P<val>\S+)", re.M)
SUBCKT_RX = re.compile(r"^\s*subckt\s+(?P<name>\w+)\s*\((?P<ports>[^)]*)\)", re.M)


def git(*args):
    p = subprocess.run(("git", "-c", "core.quotePath=false") + tuple(args), cwd=ROOT,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise SystemExit("git %s failed: %s" % (" ".join(args),
                                                p.stderr.decode("utf-8", "replace")))
    return p.stdout.decode("utf-8", "replace")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def changed(base, head):
    out = []
    for line in git("diff", "--name-status", "-M", base + ".." + head).splitlines():
        parts = line.split("\t")
        if parts[0].startswith("R"):
            out.append(("R", parts[2]))
        else:
            out.append((parts[0], parts[1]))
    return out


def read_blob(rel, rev):
    try:
        raw = subprocess.run(("git", "show", "%s:%s" % (rev, rel)), cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if raw.returncode != 0:
            return None
        return raw.stdout
    except OSError:
        return None


# ----------------------------------------------------------- netlist structure --
def devices_of(text):
    """Parse MOS instances out of a subckt body, resolving local `parameters`."""
    params = {m.group("name"): m.group("val") for m in PARAM_RX.finditer(text)}
    rows = []
    sub = SUBCKT_RX.search(text)
    ports = sub.group("ports").split() if sub else []
    for m in MOS_RX.finditer(text):
        def val(sym):
            return params.get(sym, sym)
        rows.append({
            "inst": m.group("inst"), "model": m.group("model"),
            "d": m.group("d"), "g": m.group("g"), "s": m.group("s"), "b": m.group("b"),
            "l": val(m.group("l")), "w": val(m.group("w")),
        })
    return rows, params, ports


def phase_table(rows):
    """Which devices are gated by a clock net, and when they conduct.

    Derived from the netlist, not from prose: a PMOS whose gate is `clk` conducts while
    clk=0, an NMOS whose gate is `clk` conducts while clk=1, and the same for clkb.
    """
    lines = ["| instance | model | gate net | conducts while |", "|---|---|---|---|"]
    for r in rows:
        g = r["g"]
        if g not in ("clk", "clkb"):
            continue
        p = "PMOS" if r["inst"].lower().startswith("m") and r["model"].startswith("p") else "NMOS"
        if r["model"].startswith("p"):
            when = "%s = 0" % g
        else:
            when = "%s = 1" % g
        lines.append("| `%s` | %s | `%s` | %s |" % (r["inst"], r["model"], g, when))
    return "\n".join(lines)


# ------------------------------------------------------------------ README -----


def supply_nets(rows):
    """Which net is the positive rail and which is ground, inferred from the devices
    themselves (PMOS source/body tie high, NMOS source/body tie low). No net name is
    assumed, so renaming vdd/vss would not silently change this analysis."""
    hi = [r["s"] for r in rows if r["model"].startswith("p")] + \
         [r["b"] for r in rows if r["model"].startswith("p")]
    lo = [r["s"] for r in rows if not r["model"].startswith("p")] + \
         [r["b"] for r in rows if not r["model"].startswith("p")]
    if not hi or not lo:
        return None, None
    return max(set(hi), key=hi.count), max(set(lo), key=lo.count)


def clock_complements(rows, ports, hi, lo):
    """Internal nets that a clock port inverts: driven only by devices gated by that port,
    and neither a subckt port nor a rail."""
    internal = set(r["d"] for r in rows) - set(ports) - {hi, lo}
    out = {}
    for p in ports:
        if not p.lower().startswith(("clk", "ck")):
            continue
        for n in sorted(internal):
            drivers = [r for r in rows if r["d"] == n]
            if drivers and all(r["g"] == p for r in drivers):
                out[p] = n
                break
    return out


def gate_value(g, phase, clkname, comp):
    """Logic level a net carries at this phase; None when the net is not a clock net."""
    if g == clkname:
        return phase == 1
    if g == comp.get(clkname):
        return phase == 0
    return None


def conducts(r, phase, clkname, comp):
    """Whether this device is ON at this phase. Conduction is polarity-dependent: a PMOS
    is ON with its gate low, an NMOS with its gate high -- confusing the gate's level with
    the switch state is exactly how a table like this one goes silently wrong."""
    val = gate_value(r["g"], phase, clkname, comp)
    if val is None:
        return None
    return (not val) if r["model"].startswith("p") else val


def paths_to_rail(rows, start, hi, lo, max_depth=5):
    """Series paths from `start` to a rail, as [(inst, from_net, to_net), ...]."""
    adj = {}
    for r in rows:
        for a, b in ((r["d"], r["s"]), (r["s"], r["d"]), (r["d"], r["b"]), (r["b"], r["d"])):
            adj.setdefault(a, []).append((b, r["inst"]))
    found, stack = [], [(start, [], 0)]
    while stack:
        node, seq, depth = stack.pop()
        if depth >= max_depth:
            continue
        for nxt, inst in adj.get(node, []):
            if any(inst == s[0] for s in seq):
                continue
            if nxt in (hi, lo):
                found.append(seq + [(inst, node, nxt)])
            else:
                stack.append((nxt, seq + [(inst, node, nxt)], depth + 1))
    return found


def ascii_stacks(rows, nodes, hi, lo):
    """Topology text straight out of the parsed devices -- no hand-drawing step where a
    transcription error could hide."""
    by = {r["inst"]: r for r in rows}
    out = []
    for node in nodes:
        out.append("")
        out.append("```")
        for rail, tag in ((hi, "up  "), (lo, "down")):
            seen = set()
            for path in sorted(paths_to_rail(rows, node, hi, lo), key=lambda p: [s[0] for s in p]):
                if path[-1][2] != rail:
                    continue
                line = "%s " % rail + " ".join(
                    "[%s %s g=%s]" % (i, by[i]["model"], by[i]["g"]) for i, _a, _b in path
                ) + " %s" % node
                if line in seen:
                    continue
                seen.add(line)
                out.append("  %s %s" % (tag, line))
        out.append("```")
    return "\n".join(out)


def clock_behaviour(rows, ports, hi, lo):
    """Per storage node, whether a data path to each rail is live at clk=0 and at clk=1.

    Nodes come from the keeper devices' own gates, the rails from the device terminals, and
    transparent/hold falls out of which switches are on. Nothing here is typed in from a
    description, so a topology change moves this table instead of leaving prose behind.
    """
    comp = clock_complements(rows, ports, hi, lo)
    clks = [p for p in ports if p in comp]
    keep = [r["g"] for r in rows if re.search(r"k[1-4]$", r["inst"], re.I)]
    nodes = [n for n in dict.fromkeys(keep) if n not in (hi, lo)]
    if not clks or not nodes or hi is None:
        return ["_(clock phases or storage nodes could not be derived from this netlist; "
                "read the device table instead)_"], []
    clk = clks[0]
    by = {r["inst"]: r for r in rows}
    keep_nodes = nodes
    # A data stack is a path to a rail that contains at least one clock-gated device; a
    # keeper path has none. That distinction is read off the netlist, not from names.
    origins = [p for p in ports if p not in (clk, hi, lo) and p not in keep_nodes
               and not p.lower().startswith(("clk", "ck", "vdd", "vss"))]
    clocked = {i for i, r in by.items() if gate_value(r["g"], 0, clk, comp) is not None}
    node_stacks, node_ck = {}, {}
    for node in keep_nodes:
        stacks = [p for p in paths_to_rail(rows, node, hi, lo)
                  if any(i in clocked for i, _a, _b in p)]
        node_stacks[node] = stacks
        node_ck[node] = sorted({i for p in stacks for i, _a, _b in p if i in clocked})

    def live(node, phase):
        return [any(p[-1][2] == rail and all(conducts(by[i], phase, clk, comp) is not False
                                             for i, _a, _b in p)
                  for p in node_stacks[node]) for rail in (hi, lo)]

    def on_list(node, phase):
        return ", ".join("`%s`" % i for i in node_ck[node]
                         if conducts(by[i], phase, clk, comp)) or "none"

    def role_of(node, phase):
        if not node_stacks[node]:
            return "no data stack"
        l = live(node, phase)
        return ("transparent" if all(l) else ("partly live" if any(l) else "hold"))

    lines = ["| storage node | held by | clocked switches ON at `%s=0` | at `%s=1` | derived role |"
             % (clk, clk), "|---|---|---|---|---|"]
    roles = {}
    for node in keep_nodes:
        holders = ", ".join("`%s`" % h for h in sorted(
            {group_of(r["inst"]) for r in rows
             if r["g"] == node and re.search(r"k[1-4]$", r["inst"], re.I)}))
        if not node_stacks[node]:
            lines.append("| `%s` | %s | keeper path only | keeper path only | keeper copy of "
                         "the other node, not a capture point |" % (node, holders))
            continue
        r0, r1 = role_of(node, 0), role_of(node, 1)
        roles[node] = (r0, r1)
        lines.append("| `%s` | %s | ON: %s | ON: %s | `%s=0` %s / `%s=1` %s |"
                     % (node, holders, on_list(node, 0), on_list(node, 1),
                        clk, r0, clk, r1))

    links = {n: sorted({r["g"] for r in rows if r["d"] == n and r["inst"] not in clocked
                        and r["g"] not in (clk, hi, lo)}) for n in keep_nodes}
    lines.append("")
    lines.append("Gate chain, where each hop is the stack whose non-clocked gate is the "
                 "previous net: " + "; ".join(
                     "`%s` <- %s" % (n, ", ".join("`%s`" % g for g in links[n]) or "(none)")
                     for n in keep_nodes) + ".")
    for port in origins:
        frontier, hops, reached = {port}, 0, {}
        while hops < 4:
            nxt = {n for n in keep_nodes if frontier & set(links[n])}
            for n in nxt:
                reached.setdefault(n, hops + 1)
            frontier, hops = nxt, hops + 1
        for node in sorted(reached, key=lambda x: (reached[x], x)):
            lines.append("- `%s` -> `%s`: %d inverting stack stage(s), so `%s` is **%s** with "
                         "respect to `%s` (counted from the parsed gates)."
                         % (port, node, reached[node], node,
                            "non-inverting" if reached[node] % 2 == 0 else "inverting", port))

    masters = [n for n, r in roles.items() if r[0] == "transparent" and r[1] == "hold"]
    slaves = [n for n, r in roles.items() if r[0] == "hold" and r[1] == "transparent"]
    if masters and slaves:
        lines.append("")
        lines.append("Derived edge behaviour: `%s` (the %s node) is transparent only while "
                     "`%s=0` and `%s` (the %s node) only while `%s=1`, so a **rising** edge on "
                     "`%s` hands whatever `%s` was holding to `%s` -- single-phase posedge "
                     "capture, read off the switch states rather than asserted. While one node "
                     "is transparent the other has no conducting data path, so there is no "
                     "same-phase %s-to-output race to hide in."
                     % (masters[0], holders_of(rows, masters[0]), clk, slaves[0],
                        holders_of(rows, slaves[0]), clk, clk, masters[0], slaves[0],
                        origins[0] if origins else "input"))
        lines.append("")
        lines.append("TOPOLOGY_DERIVATION: PASS (master node %s, slave node %s)"
                     % (",".join(masters), ",".join(slaves)))
    elif roles:
        lines.append("")
        lines.append("_The two-latch pattern could not be recognised from the derived roles; "
                     "treat the table above as the finding and this round's prose as void._")
        lines.append("")
        lines.append("TOPOLOGY_DERIVATION: UNRECOGNISED_PATTERN")
    return lines, keep_nodes


def holders_of(rows, node):
    return "/".join(sorted({group_of(r["inst"]).split()[0] for r in rows
                            if r["g"] == node and re.search(r"k[1-4]$", r["inst"], re.I)})) or "keeper"


TB_RX = [
    ("rail source", re.compile(r"^\s*(\w+)\s*\(\s*(\S+)\s+(\S+)\s*\)\s*vsource\b[^\n]*?\bdc=(\S+)", re.M)),
    ("pulse source", re.compile(r"^\s*(\w+)\s*\(\s*(\S+)\s+(\S+)\s*\)\s*vsource\s+type=pulse[^\n]*", re.M)),
    ("load capacitor", re.compile(r"^\s*(\w+)\s*\(\s*(\S+)\s+(\S+)\s*\)\s*capacitor\s+c=(\S+)", re.M)),
    ("transient", re.compile(r"^\s*tran\b[^\n]*", re.M)),
    ("section (corner)", re.compile(r"section=(\w+)")),
    ("temperature", re.compile(r"^\s*temp\s*=\s*(\S+)", re.M | re.I)),
]


def tb_condition_lines(rel, text):
    out = ["- `%s`" % rel]
    for label, rx in TB_RX:
        for m in list(rx.finditer(text))[:3]:
            body = " ".join(x for x in m.groups() if x) or m.group(0)
            out.append("      %s: %s" % (label, body.strip()))
    return out


def build_readme(base, head, files, notes_text, results_bundles, gate_out=""):
    short_base, short_head = base[:7], head[:7]

    parts = []
    A = parts.append
    A("# Review bundle %s..%s" % (short_base, short_head))
    A("")
    A("Generated by `scripts/make_review_bundle.py` on %s." %
      datetime.date.today().isoformat())
    A("")
    A("## Identifiers")
    A("")
    A("| item | value |")
    A("|---|---|")
    A("| base (reviewed-against) | `%s` |" % base)
    A("| head (this round) | `%s` |" % head)
    A("| branch | `%s` |" % git("rev-parse", "--abbrev-ref", "HEAD").strip())
    A("| commits in range | %d |" % len(
        git("log", "--oneline", "%s..%s" % (base, head)).strip().splitlines()))
    A("| files in bundle | %d |" % len(files))
    A("")
    # The reviewer reads the code from GitHub, not from this zip: the zip is a snapshot,
    # the repository is the live source. Paths come from remote.origin.url, never typed in.
    origin = git("config", "--get", "remote.origin.url").strip()
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", origin, re.I)
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if m:
        base_url = "https://github.com/%s/%s/blob/%s" % (m.group(1), m.group(2), branch)
        key = [rel for rel, _ in files
               if re.search(r"(C2MOS_DFF\.scs|run_(ff1|shift3)[^/]*\.scs|psf_check\.awk|"
                            r"test_psf_check\.py|tb_preflight\.sh|c2mos_check\.sh|"
                            r"c2mos_margin\.sh|pvt_probe\.sh|provenance_check\.py|"
                            r"netlist_stats\.py|public_release_audit\.md|"
                            r"c2mos_validation_report\.md)$", rel)]
        A("Readable straight from the public repository (`%s`), no download needed:" % branch)
        A("")
        for rel in key:
            A("- <%s/%s>" % (base_url, rel))
        A("")
        A("`scripts/run_spectre.sh` needs the PDK path from an untracked `spectre/pdk_local.env`, "
          "so the numbers here are reproducible only where that PDK exists -- the code, the "
          "checkers and the extracted results are readable anywhere.")
        A("")

    A("Read the diff first: `git_diff.patch`. Do not grade this round from the")
    A("prose alone -- the netlists under `source/` and the numbers under `results/`")
    A("are what the claims rest on.")
    A("")
    A("## Task / requirements / assumptions")
    A("")
    if notes_text:
        A(notes_text.strip())
        A("")
    else:
        A("_no --notes file supplied; requirement classification is missing and the_")
        A("_bundle is incomplete for review purposes._")
        A("")
    A("## Circuit, as parsed from the netlist in this bundle")
    A("")
    for rel, text, rows, params, ports in results_bundles["netlists"]:
        A("### `%s`" % rel)
        A("")
        if ports:
            A("subckt ports: " + ", ".join("`%s`" % p for p in ports))
            A("")
        if params:
            A("local parameters: " + ", ".join("`%s=%s`" % kv for kv in sorted(params.items())))
            A("")
        A("| instance | model | D | G | S | B | L | W |")
        A("|---|---|---|---|---|---|---|---|")
        for r in rows:
            A("| `%s` | %s | `%s` | `%s` | `%s` | `%s` | %s | %s |" %
              (r["inst"], r["model"], r["d"], r["g"], r["s"], r["b"], r["l"], r["w"]))
        A("")
        A("Clock-gated devices and the phase they conduct in:")
        A("")
        A(phase_table(rows))
        A("")
        hi, lo = supply_nets(rows)
        behaviour, storage_nodes = clock_behaviour(rows, ports, hi, lo)
        A("### Clock behaviour, derived from the switch states")
        A("")
        A("\n".join(behaviour))
        A("")
        if storage_nodes:
            A("### ASCII topology (generated from the same parse)")
            A("")
            A(ascii_stacks(rows, storage_nodes, hi, lo))
            A("")
        A("Model parameters of the PDK are deliberately not reproduced here.")
        A("")

    A("## Testbench conditions, quoted from the files in this bundle")
    A("")
    A("Every value below is copied out of the netlist text by rule, not retyped. All of it "
      "is `POC_ASSUMPTION`: the assigned process fixes the 1.8 V core device family, but the "
      "stimulus, the 50 fF load, the clock period and the slew are this POC's choices and "
      "represent no specification. The rail-to-node-0 grounding that the preflight asserts "
      "is visible in the `rail source` lines.")
    A("")
    shown = 0
    for rel, _cat in files:
        if not rel.endswith(".scs") or "/generated/" not in "/" + rel:
            continue
        if not re.search(r"run_(ff1|shift3)", rel):
            continue
        body = read_blob(rel, head)
        if body is None:
            continue
        A("\n".join(tb_condition_lines(rel, body.decode("utf-8", "replace"))))
        shown += 1
        if shown >= 4:
            break
    A("")
    A("Margin sweeps (`scripts/c2mos_margin.sh`, results under `results/`) use the same "
      "stimulus shape with the data edge moved relative to the clock edge; the two slew sets "
      "are `s1e-9` and `s5e-11`.")
    A("")
    A("## Two separate release-safety dimensions")
    A("")
    A("Circuit status and repository hygiene are different questions, and the bundle keeps "
      "them apart so an accepted privacy item cannot read as a design failure:")
    A("")
    A("```")
    for line in gate_out.strip().splitlines():
        if re.match(r"^(PDK_TRACKED_FILES|CREDENTIAL_TRACKED_FILES|PRIVATE_KEYS_TRACKED_FILES|"
                    r"VENDOR_MODEL_TRACKED_FILES|SAFETY_GATE)", line.strip()):
            A(line.strip())
    A("```")
    A("")
    A("Those counters are the content audit: PDK files, vendor model cards, Calibre decks, "
      "credentials, private keys and raw PSF databases. `reports/public_release_audit.md` "
      "records the other dimension -- the owner's accepted, still-open identity cleanup "
      "(superseded commit objects that GitHub keeps serving by SHA). It is not a circuit "
      "verdict and does not change any number in this bundle.")
    A("")
    A("## Automatic checks and measured numbers")
    A("")
    for rel in results_bundles["summary_files"]:
        A("### `%s`" % rel)
        A("")
        body = read_blob(rel, head)
        A("```json")
        A(body.decode("utf-8", "replace").strip() if body else "")
        A("```")
        A("")
    A("Checker sources (read them; the thresholds are in there, not paraphrased):")
    A("")
    for rel, _ in files:
        if rel.endswith((".awk", ".sh")) and ("check" in rel or "psf" in rel or "margin" in rel):
            A("- `source/%s`" % rel)
    A("")
    A("## Files changed in range")
    A("")
    A("```")
    A(git("diff", "--name-status", "-M", "%s..%s" % (base, head)))
    A("```")
    A("")
    A("## How to re-verify")
    A("")
    A("```bash")
    A("# from a checkout of head, with the PDK path in local config (never committed)")
    A("cp spectre/pdk_local.env.example spectre/pdk_local.env   # then edit the paths")
    A("bash scripts/c2mos_check.sh ff1 2e-7 review 2            # expect C2MOS_DFF_1CH: PASS")
    A("bash scripts/c2mos_check.sh shift3 2e-7 review 2          # expect C2MOS_SHIFT_3STAGE: PASS")
    A("bash scripts/c2mos_margin.sh setup; bash scripts/c2mos_margin.sh hold")
    A("python scripts/export_results.py                          # regenerates results/*.csv")
    A("```")
    A("")
    A("`run_spectre.sh` refuses a netlist outside the project and refuses to run when a")
    A("`${QODER_*}` include variable is unset, so a reviewer without this PDK will get a")
    A("clear message rather than a mysterious simulation failure.")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------- main ----
def main():
    args = [a for a in sys.argv[1:]]
    if len(args) < 2:
        print("usage: make_review_bundle.py <BASE> <HEAD> [--notes path.md] [--out dir]")
        return 9
    base, head = git("rev-parse", args[0]).strip(), git("rev-parse", args[1]).strip()
    notes_path = None
    out_dir = os.path.join(ROOT, "review")
    if "--notes" in args:
        notes_path = args[args.index("--notes") + 1]
    if "--out" in args:
        out_dir = args[args.index("--out") + 1]

    notes_text = ""
    if notes_path:
        with open(os.path.join(ROOT, notes_path), encoding="utf-8") as fh:
            notes_text = fh.read()

    # gate: full history scan before we package anything out of it
    gate = subprocess.run((sys.executable, os.path.join(ROOT, "scripts",
                              "precommit_safety_check.py"), "--mode", "history"),
                          cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    gate_out = gate.stdout.decode("utf-8", "replace")
    if gate.returncode != 0:
        print(gate_out)
        print("BUNDLE: BLOCKED by the history safety gate")
        return 1

    ch = changed(base, head)
    files = []
    netlists, summary_files = [], []
    manifest = []
    stag = os.path.join(out_dir, "review_bundle_%s" % head[:7])
    for sub in ("source", "reports", "results"):
        os.makedirs(os.path.join(stag, sub), exist_ok=True)

    for status, rel in ch:
        if status == "D":
            continue
        data = read_blob(rel, head)
        if data is None:
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext not in SOURCE_EXT | RESULT_EXT | REPORT_EXT:
            continue
        hits = [n for n, _ in R.content_denied(data.decode("latin-1"))] + \
               [n for n, _ in R.secrets_in(data.decode("latin-1"))]
        if R.path_denied(rel) or hits:
            print("BUNDLE: refusing %s (%s)" % (rel, hits or "path rule"))
            return 1
        if ext in SOURCE_EXT:
            cat = "source"
        elif ext in REPORT_EXT:
            cat = "reports"
        else:
            cat = "results"
        dest = os.path.join(stag, cat, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        files.append((rel, cat))
        manifest.append((cat + "/" + rel, len(data), sha256(data)))
        if ext == ".scs" and "subckt" in data.decode("latin-1"):
            text = data.decode("utf-8", "replace")
            rows, params, ports = devices_of(text)
            if rows:
                netlists.append((rel, text, rows, params, ports))
        if rel.startswith("results/") and ext in (".json", ".csv") and \
                os.path.basename(rel) in ("summary.json",):
            summary_files.append(rel)

    gitfiles = {
        "git_status.txt": git("status", "--porcelain=v1", "--branch"),
        "git_log.txt": git("log", "--stat", "%s..%s" % (base, head)),
        "git_diff.patch": git("diff", "%s..%s" % (base, head)),
        "changed_files.txt": git("diff", "--name-status", "-M", "%s..%s" % (base, head)),
    }
    for name, body in gitfiles.items():
        with open(os.path.join(stag, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        manifest.append((name, len(body.encode("utf-8")), sha256(body.encode("utf-8"))))

    readme = build_readme(base, head, files, notes_text,
                          {"netlists": netlists, "summary_files": summary_files}, gate_out)
    if any("C2MOS_DFF.scs" in rel for rel, _ in files) and \
            "TOPOLOGY_DERIVATION: PASS" not in readme:
        print("BUNDLE: BLOCKED -- the generator parsed the cell but no longer derives one "
              "master node (transparent while clk=0) and one slave node (transparent while "
              "clk=1). Either the netlist changed or the derivation broke; shipping a clock "
              "table the tool cannot justify is the one thing this bundle must not do.")
        return 1
    with open(os.path.join(stag, "REVIEW_README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(readme)
    manifest.insert(0, ("REVIEW_README.md", len(readme.encode("utf-8")),
                        sha256(readme.encode("utf-8"))))

    man = ["# manifest: relative_path<TAB>bytes<TAB>sha256"]
    man += ["%s\t%d\t%s" % m for m in sorted(manifest)]
    # manifest.txt lists itself with a placeholder hash: it cannot contain its own
    # digest. The count check below takes that into account, so "manifest rows == files
    # in the zip" is a real assertion instead of something a reviewer has to eyeball.
    man.append("manifest.txt\t-\t(self, cannot hash itself)")
    body = "\n".join(man) + "\n"
    with open(os.path.join(stag, "manifest.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)

    zpath = os.path.join(out_dir, "review_bundle_%s.zip" % head[:7])
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _dn, fnames in os.walk(stag):
            for fn in fnames:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, out_dir).replace("\\", "/"))

    with zipfile.ZipFile(zpath) as z:
        in_zip = set(i.filename for i in z.infolist() if not i.is_dir())
    listed = set(m[0].replace("\\", "/") for m in manifest) | {"manifest.txt"}
    listed_zip = set(s.split("review_bundle_%s/" % head[:7], 1)[-1] for s in in_zip)
    missing = sorted(listed - listed_zip)
    extra = sorted(listed_zip - listed)
    print("BUNDLE dir : %s" % stag)
    print("BUNDLE zip : %s (%d bytes)" % (zpath, os.path.getsize(zpath)))
    print("files      : manifest=%d zip=%d" % (len(listed), len(listed_zip)))
    if missing or extra:
        print("BUNDLE_SELF_CHECK: MISMATCH missing=%s extra=%s" % (missing, extra))
        print("MANIFEST_MATCH: FAIL")
        return 1
    print("BUNDLE_SELF_CHECK: manifest and zip contents agree")
    print("MANIFEST_MATCH: PASS")

    # The zip is what a reviewer actually opens, so the deny rules run over the bytes
    # inside it instead of trusting that they came from a clean history. The bulk-blob
    # and extension rules are history hygiene, not release blockers, so they are not
    # applied here; findings name the rule only, never the matched value.
    #
    # A patch needs one adjustment: every added line starts with '+', which is also how
    # a SPICE model-card continuation line looks, so scanning the raw text flags our own
    # diff (an added line "VTH = 0.900 V" reads as "+VTH = 0.900"). The first character is
    # therefore stripped and the headers dropped -- the rules then see the file content
    # the patch actually carries, with the same strength.
    def scan_text(name, data):
        if not name.endswith(".patch"):
            return data.decode("latin-1")
        keep = []
        for line in data.decode("latin-1").splitlines():
            if line.startswith(("diff --git", "index ", "--- ", "+++ ", "@@")):
                continue
            keep.append(line[1:] if line[:1] in "+- " else line)
        return "\n".join(keep)

    # Before trusting that unwrapping, plant one line of each kind: a real model-card
    # continuation must still be caught once the leading '+' is removed, and our own
    # threshold label must stay uncaught. A scan that cannot fail is not a scan.
    # The vendor line is assembled at run time on purpose -- the commit gate refuses to
    # store that text in a tracked file, and it is right to, so the fixture has to be
    # live at run time without being a literal in source.
    _model_line = "+.mo" + "del n18 bsim4"
    _planted = ("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n"
                + _model_line + "\n+  parameters ln=2e-7\n"
                + "+VTH = 0.900 V (= 0.5 * VDD)\n")
    if not R.content_denied(scan_text("x.patch", _planted.encode())):
        print("SAFETY_SCAN: FAIL (patch unwrapping stopped catching a planted model line)")
        return 1
    _benign = "diff --git a/x b/x\n+++ b/x\n@@ -1 +1 @@\n+VTH = 0.900 V (= 0.5 * VDD = 1.800)\n"
    if R.content_denied(scan_text("x.patch", _benign.encode())):
        print("SAFETY_SCAN: FAIL (patch unwrapping still trips on our own netlist lines)")
        return 1

    hits = []
    members = [i for i in zipfile.ZipFile(zpath).infolist() if not i.is_dir()]
    zin = zipfile.ZipFile(zpath)
    for zi in members:
        data = zin.read(zi.filename)
        pat = R.path_denied(zi.filename)
        if pat:
            hits.append("%s: PATH deny rule '%s'" % (zi.filename, pat))
        text = scan_text(zi.filename, data)
        for name, line in R.content_denied(text):
            hits.append("%s: VENDOR CONTENT '%s' at line %d" % (zi.filename, name, line))
        for name, line in R.secrets_in(text):
            hits.append("%s: SECRET '%s' at line %d" % (zi.filename, name, line))
    if hits:
        for h in hits[:20]:
            print("SAFETY_SCAN finding: " + h)
        print("SAFETY_SCAN: FAIL (%d/%d files flagged)"
              % (len(set(h.split(":")[0] for h in hits)), len(members)))
        return 1
    print("SAFETY_SCAN: PASS (%d files in zip)" % len(members))
    print("gate(history) rc=%d" % gate.returncode)
    print("MAKE_REVIEW_BUNDLE: DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
