#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-2 Part D: turn the accepted golden netlist into a numeric device parameter table.

Sizes in the golden are written as design-variable EXPRESSIONS (l=ln, w=wcp). A schematic
readback cannot be compared against an expression, so every expression is resolved here into a
number in SI metres, in two steps that are both kept visible:

  1. the design variables declared inside the subckt (parameters ln=2e-7 ...)
  2. the instance attribute that names one of them (l=ln -> 2e-7)

If any instance attribute cannot be resolved, GOLDEN_PARAMETER_PARSE: FAIL is printed and the exit
code is non-zero, because a golden table with holes would silently let a wrong schematic pass.

Fingers and multiplier are NOT written in the golden netlist at all. They are recorded as
DEFAULT_FROM_NETLIST_ABSENCE = 1 and cross-checked against what the PDK CDF itself defaults to
(see reports/c2mos_cdf_parameter_audit.md); a design size that happens to equal the PDK default is
legitimate, so the checker never treats "equals default" as a failure by itself.

Usage: python scripts/sch1_golden_params.py <golden.scs> <out.csv>
"""
from __future__ import print_function

import io
import re
import sys

# Spectre length suffixes, as used by the golden file and by the PDK CDF strings
SUFFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3}


def to_metres(text, variables):
    """Resolve "2e-7", "ln", "220n" or "2u" into metres, or None if it cannot be resolved."""
    if text is None:
        return None
    s = str(text).strip().strip('"')
    if s in variables:
        s = str(variables[s]).strip()
    m = re.match(r"^(\d+\.?\d*(?:[eE][-+]?\d+)?)([fpnuµm]?)$", s)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    if unit and unit not in ("m",):
        return value * SUFFIX[unit]
    if unit == "m":
        # bare "m" is metre in Spectre only after a number; "2m" is never used in this netlist
        return value * SUFFIX["m"]
    return value


def main():
    path, out_csv = sys.argv[1], sys.argv[2]
    text = io.open(path, encoding="utf-8", errors="replace").read()

    hdr = re.search(r"^subckt\s+(\S+)\s*\(([^)]*)\)", text, re.M)
    if not hdr:
        print("GOLDEN_PARAMETER_PARSE: FAIL (no subckt header)")
        return 1
    cell_name, ports = hdr.group(1), hdr.group(2).split()

    # the body between subckt/ends, so nothing outside the cell is parsed
    body = text[text.index(hdr.group(0)):]
    end = re.search(r"^ends\s+%s" % re.escape(cell_name), body, re.M)
    body = body[:end.start()] if end else body

    variables = {}
    for name, value in re.findall(r"^\s*parameters\s+(\w+)\s*=\s*(\S+)", body, re.M):
        variables[name] = value

    rows, failures = [], []
    for line in body.split("\n"):
        m = re.match(r"\s*((?:mp|mn)\w+)\s*\(\s*([^)]+?)\s*\)\s*(\w+)\s+(.*)$", line)
        if not m:
            continue
        name, nets, model, rest = m.group(1), m.group(2).split(), m.group(3), m.group(4)
        attrs = dict(re.findall(r"(\w+)\s*=\s*(\S+)", rest))
        if len(nets) != 4:
            failures.append("%s: %d nets, expected 4 (d g s b)" % (name, len(nets)))
            continue
        l_raw, w_raw = attrs.get("l"), attrs.get("w")
        l_m, w_m = to_metres(l_raw, variables), to_metres(w_raw, variables)
        if l_m is None or w_m is None:
            failures.append("%s: cannot resolve l=%r w=%r (variables known: %s)"
                            % (name, l_raw, w_raw, sorted(variables)))
            continue
        # multi-device attributes are not used in this netlist; say so instead of assuming
        for surprise in sorted(set(attrs) - set(["l", "w"])):
            failures.append("%s: unexpected attribute %s=%s (table has no rule for it)"
                            % (name, surprise, attrs[surprise]))
        rows.append(dict(inst=name, model=model, D=nets[0], G=nets[1], S=nets[2], B=nets[3],
                         l_raw=l_raw, w_raw=w_raw, L=l_m, W=w_m,
                         fingers="1", mult="1",
                         fingers_src="DEFAULT_FROM_NETLIST_ABSENCE",
                         mult_src="DEFAULT_FROM_NETLIST_ABSENCE"))

    rows.sort(key=lambda r: r["inst"])
    cols = ["instance_name", "model", "D", "G", "S", "B",
            "golden_L_raw", "golden_L_m", "golden_W_raw", "golden_W_m",
            "golden_fingers", "golden_fingers_source", "golden_multiplier", "golden_multiplier_source"]
    out = [",".join(cols)]
    for r in rows:
        out.append(",".join(str(v) for v in [r["inst"], r["model"], r["D"], r["G"], r["S"], r["B"],
                                             r["l_raw"], "%.9g" % r["L"], r["w_raw"], "%.9g" % r["W"],
                                             r["fingers"], r["fingers_src"], r["mult"], r["mult_src"]]))
    io.open(out_csv, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")

    counts = {}
    for r in rows:
        counts.setdefault((r["model"], "%.9g" % r["L"], "%.9g" % r["W"]), 0)
        counts[(r["model"], "%.9g" % r["L"], "%.9g" % r["W"])] += 1

    print("GOLDEN_CELLS: %s" % cell_name)
    print("GOLDEN_PORTS: %s" % " ".join(ports))
    print("GOLDEN_DESIGN_VARIABLES: %s" % " ".join("%s=%s" % kv for kv in sorted(variables.items())))
    print("GOLDEN_MOS_ROWS: %d" % len(rows))
    for key in sorted(counts):
        print("GOLDEN_CLASS: model=%s L=%s W=%s count=%d" % (key[0], key[1], key[2], counts[key]))
    print("GOLDEN_TABLE: %s" % out_csv)
    for f in failures:
        print("PARSE_FAILURE: %s" % f)
    if len(rows) != 18 or failures:
        print("GOLDEN_PARAMETER_PARSE: FAIL")
        return 1
    print("GOLDEN_PARAMETER_PARSE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
