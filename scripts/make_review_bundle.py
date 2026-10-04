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

import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402

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
def build_readme(base, head, files, notes_text, results_bundles):
    short_base, short_head = base[:7], head[:7]
    parts = []
    A = parts.append
    A("# Review bundle %s..%s" % (short_base, short_head))
    A("")
    A("Generated by `scripts/make_review_bundle.py` on %s." %
      __import__("datetime").date().isoformat())
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
        A("Model parameters of the PDK are deliberately not reproduced here.")
        A("")
    A("## Automatic checks and measured numbers")
    A("")
    for rel in results_bundles["summary_files"]:
        A("### `%s`" % rel)
        A("")
        A("```json")
        A(read_blob(rel, head).strip() if read_blob(rel, head) else "")
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
                          {"netlists": netlists, "summary_files": summary_files})
    with open(os.path.join(stag, "REVIEW_README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(readme)
    manifest.insert(0, ("REVIEW_README.md", len(readme.encode("utf-8")),
                        sha256(readme.encode("utf-8"))))

    man = ["# manifest: relative_path<TAB>bytes<TAB>sha256"]
    man += ["%s\t%d\t%s" % m for m in sorted(manifest)]
    man.append("# files=%d" % len(manifest))
    with open(os.path.join(stag, "manifest.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(man) + "\n")

    zpath = os.path.join(out_dir, "review_bundle_%s.zip" % head[:7])
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _dn, fnames in os.walk(stag):
            for fn in fnames:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, out_dir).replace("\\", "/"))
    print("BUNDLE dir : %s" % stag)
    print("BUNDLE zip : %s (%d bytes)" % (zpath, os.path.getsize(zpath)))
    print("files      : %d  netlists parsed: %d" % (len(manifest), len(netlists)))
    print("gate(history) rc=%d" % gate.returncode)
    print("MAKE_REVIEW_BUNDLE: DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
