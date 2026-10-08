#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-3 section 8: build the expected-parameter table for a hand-authored gate/smoke cellview.

The real data-driver cells take their golden values from the accepted Candidate E-DNW deck
(scripts/sch3_golden_extract.py). The smoke cell has no deck -- its whole purpose is to ask the PDK
two questions before any design cell is touched: does spiceIn instantiate these masters by name, and
does a numeric length/width survive save + read-only reopen as the value the CDF reports. So its
"golden" is the netlist that was imported, and this script turns that netlist into the same CSV
schema the integrity gate consumes, reusing the gate's own parser and formatter rather than a second
implementation.

It also refuses to produce a table whose sizes coincide with the master's CDF default, because a
smoke cell sized at the default proves nothing about whether the write path worked.

Usage:
  python scripts/sch3_expect_from_netlist.py --netlist spectre/import/sch3_smoke_top.scs \
      --cell data_pdk_param_smoke --out results/data_pdk_param_smoke_expected.csv \
      --default-l 350n --default-w 350n
"""
from __future__ import print_function

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sch3_golden_extract import COLS, golden_rows, parse_devices, read   # one parser, one schema
from sch2_golden_params import to_metres


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--cell", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--default-l", required=True, help="the master's own CDF default length")
    ap.add_argument("--default-w", required=True, help="the master's own CDF default width")
    args = ap.parse_args()

    devs, skipped = parse_devices(read(args.netlist))
    for s in skipped:
        print("SKIP: %s" % s)
    if not devs:
        print("EXPECTED_TABLE: FAIL (no MOS instance lines found)")
        return 1

    d_l, d_w = to_metres(args.default_l, {}), to_metres(args.default_w, {})
    fails = []
    for d in devs:
        l_m, w_m = to_metres(d["l_raw"], {}), to_metres(d["w_raw"], {})
        if l_m is None or w_m is None:
            fails.append("%s: l=%s w=%s does not resolve to a number" % (d["name"], d["l_raw"], d["w_raw"]))
            continue
        if l_m <= 0 or w_m <= 0:
            fails.append("%s: non-positive size" % d["name"])
        if d_l is not None and d_w is not None and abs(l_m - d_l) < 1e-18 and abs(w_m - d_w) < 1e-18:
            fails.append("%s: sized at the master's CDF default %s/%s, so this cell could not "
                         "detect a fall-back to defaults" % (d["name"], args.default_l, args.default_w))
    if fails:
        for f in fails:
            print("EXPECTED_TABLE_FAIL: %s" % f)
        print("EXPECTED_TABLE: FAIL")
        return 1

    rows = golden_rows(devs, lambda name: args.cell)
    out = [",".join(COLS)] + rows
    directory = os.path.dirname(args.out)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    io_write(args.out, out)
    for d in devs:
        print("EXPECTED %s master=%s l=%s w=%s D=%s G=%s S=%s B=%s"
              % (d["name"], d["master"], d["l_raw"], d["w_raw"], d["nets"][0], d["nets"][1],
                 d["nets"][2], d["nets"][3]))
    print("EXPECTED_TABLE: %s rows=%d" % (args.out, len(rows)))
    print("EXPECTED_TABLE_NON_DEFAULT_SIZES: PASS")
    return 0


def io_write(path, lines):
    import io
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
