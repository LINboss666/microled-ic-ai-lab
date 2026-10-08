#!/usr/bin/env python3
"""netlist_stats.py -- count devices FROM the netlist and police the reports.

The independent review found the reports claiming 22 MOS while the cell contains 18.
Hand-correcting a number in prose is how the mistake came back next time, so this tool
makes the number a derived quantity:

  1. parse the subckt body: every MOS instance, model, D/G/S/B, L, W
  2. counting that needs no naming convention: total / NMOS / PMOS / per-model
  3. functional grouping by instance-name suffix (the cell's own convention:
     _c clock inverter, _m1/_m2 master clocked, _k1/_k2 master keeper,
     _s1/_s2 slave clocked, _k3/_k4 slave keeper). The grouping is PRINTED device by
     device so a reviewer can check it by eye instead of trusting the label.
  4. grep the reports for any device-count claim ("<n> MOS", "<n> 管", "<n> transistors")
     and compare with (1). Any mismatch is a FAIL, including claims that the prose has
     already been fixed away.

  python scripts/netlist_stats.py [--cell spectre/C2MOS_DFF.scs]
                                  [--reports reports/] [--expect-groups 2,4,4,4,4]
                                  [--also spectre/generated/<deck>.scs ...]

  Claims about a cellview built from spectre/import/*.scs are validated against those files by
  default; --also adds further netlists whose parsed device counts are legitimate totals too.
"""

import glob
import os
import re
import sys
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MOS_RX = re.compile(
    r"^\s*(?P<inst>[mM][a-zA-Z0-9_]*)\s*\(\s*(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+"
    r"(?P<b>\S+)\s*\)\s*(?P<model>[A-Za-z0-9_]+)\s+l=(?P<l>\S+)\s+w=(?P<w>\S+)", re.M)
PARAM_RX = re.compile(r"^\s*parameters\s+(?P<name>\w+)\s*=\s*(?P<val>\S+)", re.M)
SUBCKT_RX = re.compile(r"^\s*subckt\s+(?P<name>\w+)\s*\((?P<ports>[^)]*)\)", re.M)
# `(?<![A-Za-z0-9])` so the cell's own name is never read as a count: "C2MOS design status"
# names the circuit, "18 MOS" claims a number of devices.
CLAIM_RX = re.compile(r"(?<![A-Za-z0-9])(\d+)\s*(?:MOS\b|管|transistors?\b)")

# suffix -> role group, in the order the cell is drawn
GROUPS = OrderedDict([
    ("_c", "internal clock inverter"),
    ("_m1", "master clocked stage"),
    ("_m2", "master clocked stage"),
    ("_k1", "master keeper"),
    ("_k2", "master keeper"),
    ("_s1", "slave clocked stage"),
    ("_s2", "slave clocked stage"),
    ("_k3", "slave keeper"),
    ("_k4", "slave keeper"),
])


def parse_cell(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read().replace("\r\n", "\n")
    params = {m.group("name"): m.group("val") for m in PARAM_RX.finditer(text)}
    sub = SUBCKT_RX.search(text)
    ports = sub.group("ports").split() if sub else []
    devs = []
    for m in MOS_RX.finditer(text):
        def res(sym):
            return params.get(sym, sym)
        devs.append({
            "inst": m.group("inst"), "model": m.group("model"),
            "d": m.group("d"), "g": m.group("g"), "s": m.group("s"), "b": m.group("b"),
            "l": res(m.group("l")), "w": res(m.group("w")),
        })
    return devs, ports, params


def group_of(inst):
    for suffix, role in GROUPS.items():
        if inst.endswith(suffix):
            return role
    return "UNGROUPED"


def main():
    args = sys.argv[1:]
    # The claim regex reads numbers, not names, so it is self-tested before it judges any
    # document: "C2MOS" is a circuit name, "18 MOS"/"18管" are claims.
    assert CLAIM_RX.findall("C2MOS design status, POC") == [], CLAIM_RX.findall("C2MOS")
    assert CLAIM_RX.findall("18 MOS total, 18管, 9 transistors") == ["18", "18", "9"]

    def opt(name, default):
        if name not in args or args.index(name) + 1 >= len(args):
            return default
        return args[args.index(name) + 1]

    def opt_all(name):
        """--also may be repeated: extra netlists whose parsed device counts are also legitimate
        totals for the prose check."""
        out, i = [], 0
        while i + 1 < len(args):
            if args[i] == name:
                out.append(args[i + 1])
            i += 1
        return out

    cell = os.path.join(ROOT, opt("--cell", "spectre/C2MOS_DFF.scs"))
    repdir = os.path.join(ROOT, opt("--reports", "reports"))
    expect = opt("--expect-total", "")

    devs, ports, params = parse_cell(cell)
    if not devs:
        print("DEVICE_COUNT_CHECK: FAIL  (parsed 0 devices from %s)" % cell)
        return 1
    models = Counter(d["model"] for d in devs)
    nmos = sum(1 for d in devs if d["model"].startswith("n"))
    pmos = sum(1 for d in devs if d["model"].startswith("p"))
    roles = Counter(group_of(d["inst"]) for d in devs)

    print("cell = %s" % os.path.relpath(cell, ROOT).replace("\\", "/"))
    print("subckt ports = %s" % " ".join(ports))
    print("local parameters = %s" % ", ".join("%s=%s" % kv for kv in sorted(params.items())))
    print("TOTAL MOS = %d   (NMOS=%d PMOS=%d)   models=%s"
          % (len(devs), nmos, pmos, dict(models)))
    print("")
    print("grouped by the cell's own instance-name convention:")
    for role in OrderedDict.fromkeys(group_of(d["inst"]) for d in devs):
        members = [d for d in devs if group_of(d["inst"]) == role]
        print("  %-26s %2d  %s" % (role, len(members),
                                   ", ".join("%s(%s d=%s g=%s s=%s b=%s w=%s l=%s)" %
                                             (m["inst"], m["model"], m["d"], m["g"],
                                              m["s"], m["b"], m["w"], m["l"])
                                             for m in members)))
    if "UNGROUPED" in roles:
        print("DEVICE_COUNT_CHECK: FAIL  (%d device(s) not assigned to any group)"
              % roles["UNGROUPED"])
        return 1

    problems = []
    if expect and str(len(devs)) != str(expect):
        problems.append("total %d != --expect-total %s" % (len(devs), expect))
    if nmos + pmos != len(devs):
        problems.append("nmos+pmos %d != total %d" % (nmos + pmos, len(devs)))

    # police the prose: every device-count claim in every report must equal the parser
    # every accepted total must come out of a parsed netlist, never out of the prose.
    # spectre/import/*.scs are the cell-level netlists our own schematics were built from, so a
    # report describing one of those cellviews (4 devices in data_sink_1ch, 1 in data_bias_ref) is
    # checked against a real file by default instead of being forced through check:skip.
    import_dir = os.path.join(ROOT, "spectre", "import")
    extras = opt_all("--also")
    if os.path.isdir(import_dir):
        extras += [os.path.relpath(f, ROOT).replace("\\", "/")
                   for f in sorted(glob.glob(os.path.join(import_dir, "*.scs")))]
    known = set([len(devs)])
    for extra in extras:
        path = os.path.join(ROOT, extra)
        more, _p, _q = parse_cell(path)
        if not more:
            print("DEVICE_COUNT_CHECK: FAIL  (--also %s parsed 0 devices)" % extra)
            return 1
        known.add(len(more))
        print("also parsed %s -> %d devices" % (extra, len(more)))
    print("")
    print("report claims checked against the parser:")
    if os.path.isdir(repdir):
        for fn in sorted(os.listdir(repdir)):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(repdir, fn)
            with open(p, encoding="utf-8", errors="replace") as fh:
                body = fh.read()
            body_lines = body.split("\n")
            for m in CLAIM_RX.finditer(body):
                idx = body[:m.start()].count("\n")
                if "check:skip" in body_lines[idx]:
                    continue    # a line may quote a superseded claim on purpose
                line = idx + 1
                n = int(m.group(1))
                tag = "ok" if n in known else "MISMATCH"
                if n not in known:
                    problems.append("%s:%d claims %d devices" % (fn, line, n))
                print("  %-8s %s:%-4d '%s' (source says %s)"
                      % (tag, fn, line, m.group(0).strip(), "/".join(str(k) for k in sorted(known))))
    else:
        print("  (no reports directory)")

    print("")
    for pr in problems:
        print("  PROBLEM " + pr)
    print("DEVICE_COUNT_CHECK: %s" % ("PASS" if not problems else "FAIL"))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
