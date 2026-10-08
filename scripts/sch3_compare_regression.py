#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-3 section 14: compare the OA-derived regression numbers against the accepted DATA-5 ones.

The circuit was not re-tuned, so the two result sets should agree to the printed precision. This
script is deliberately not a pass/fail fudge knob: it reports, per corner and per column, the largest
absolute difference it found and how many rows were matched, and it FAILS when a row present on one
side is missing on the other. The tolerance is a command-line argument so the reviewer can see what
was accepted, and the default (0.01 % of the 15 uA target for currents, 1e-6 V for node voltages) is
tighter than anything a re-sizing would need.

Usage:
  python scripts/sch3_compare_regression.py --kind sweep --group-re '_([a-z]+)_(on|off)$' \
      --xcol vsw_V --cols iout_uA,err_pct,vbias_V \
      --accepted results/data_driver_Ednw_corner_dc.csv --new results/data_driver_schematic_dc.csv
  python scripts/sch3_compare_regression.py --kind scalar --group-re '_([a-z]{2})_' \
      --accepted results/data_driver_Ednw_corner_transient.csv --new results/data_driver_schematic_transient.csv
"""
from __future__ import print_function

import argparse
import csv
import io
import math
import os
import re
import sys


def load(path, header_from=None):
    """Rows as dicts, read with the csv module: ddrv_xtalk.py quotes a description field that
    contains commas, so splitting on "," would silently compare the wrong columns."""
    text = io.open(path, encoding="utf-8", errors="replace").read()
    rows = list(csv.reader(text.splitlines()))
    rows = [r for r in rows if r and any(f.strip() for f in r)]
    if not rows:
        return []
    hdr = rows[0]
    if header_from and "label" not in hdr and "candidate" not in hdr:
        # results/data_driver_Ednw_static.csv was written without a header line; borrow the column
        # names from the file produced by the same analyser instead of guessing the field order
        hdr, rows = header_from, rows
    else:
        rows = rows[1:]
    return [dict(zip(hdr, r)) for r in rows if len(r) == len(hdr)]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def group_of(row, rx, first_col):
    m = re.search(rx, row.get(first_col, ""))
    return "|".join(m.groups()) if m else None


def compare(accepted, new, group_rx, key_col, cols, xcol, excluded, cur_tol, vol_tol):
    """Returns (worst-per-column, problems). Nothing is averaged away: a missing row is a problem."""
    def bucket(rows):
        out = {}
        for r in rows:
            g = group_of(r, group_rx, key_col)
            if g is None:
                continue
            out.setdefault(g, []).append(r)
        return out

    A, B = bucket(accepted), bucket(new)
    problems = []
    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))
    for g in only_a:
        problems.append("group %s present in the accepted data, missing from the OA run" % g)
    for g in only_b:
        problems.append("group %s present in the OA run, missing from the accepted data" % g)

    worst = {}
    detail = []
    for g in sorted(set(A) & set(B)):
        rows_a, rows_b = A[g], B[g]
        if len(rows_a) != len(rows_b):
            problems.append("%s: %d accepted rows vs %d OA rows" % (g, len(rows_a), len(rows_b)))
        cols_a = [c for c in cols if c not in excluded]
        if xcol:
            index_b = dict((round(num(r.get(xcol, "")) or 0.0, 6), r) for r in rows_b)
            pairs = [(ra, index_b.get(round(num(ra.get(xcol, "")) or 0.0, 6))) for ra in rows_a]
        else:
            pairs = [(rows_a[0], rows_b[0] if rows_b else None)]
        for ra, rb in pairs:
            if rb is None:
                problems.append("%s: row %s=%s not found in the OA run" % (g, xcol, ra.get(xcol)))
                continue
            for c in cols_a:
                va, vb = num(ra.get(c)), num(rb.get(c))
                if va is None or vb is None:
                    continue
                tol = vol_tol if c.endswith("_V") or c.endswith("_v") else cur_tol
                d = abs(va - vb)
                prev = worst.get((c,))
                if prev is None or d > prev[0]:
                    worst[(c,)] = (d, "%s: %s %s vs %s" % (g, c, ra.get(c), rb.get(c)))
                detail.append([g, c, ra.get(c), rb.get(c), "%.9g" % d, "%.9g" % tol,
                               "OVER" if d > tol else "OK"])
                if d > tol:
                    problems.append("%s OVER TOLERANCE: %s %s -> %s (delta %.6g > %.6g)"
                                    % (g, c, ra.get(c), rb.get(c), d, tol))
    return worst, problems, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=("sweep", "scalar"), required=True)
    ap.add_argument("--accepted", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--group-col", default="label")
    ap.add_argument("--group-re", required=True)
    ap.add_argument("--accepted-filter", default=None,
                    help="only compare accepted rows whose group column matches this regex; the "
                         "DATA-5 CSVs hold the same sweep twice under two labels (the run tag and "
                         "the report tag), and comparing against both would be a row-count error "
                         "rather than a result")
    ap.add_argument("--new-filter", default=None,
                    help="the same selector for the OA run, used where the newer probe set has "
                         "more rows than the accepted one (this round added a baseline run per "
                         "corner, DATA-5 did not)")
    ap.add_argument("--xcol", default=None, help="sweep: the column that identifies a point")
    ap.add_argument("--cols", default=None, help="sweep: comma list; scalar compares every numeric column")
    ap.add_argument("--current-tol", type=float, default=1.5e-3,
                    help="uA; default is 0.01 %% of the 15 uA target")
    ap.add_argument("--voltage-tol", type=float, default=1e-6, help="V")
    ap.add_argument("--exclude", default="", help="comma list of columns not to compare, with the "
                                                  "reason stated in the report")
    ap.add_argument("--out", default=None, help="append every compared (group, column) pair here")
    ap.add_argument("--dataset", default=None, help="label written into --out")
    args = ap.parse_args()

    xcol = args.xcol if args.kind == "sweep" else None
    cols = args.cols.split(",") if args.cols else None
    exclude = [c for c in args.exclude.split(",") if c]
    new = load(args.new)
    accepted = load(args.accepted, header_from=list(new[0].keys()) if new else None)
    if cols is None:
        # scalar mode compares every column the analyser wrote, minus anything explicitly excluded
        cols = [c for c in new[0] if c not in exclude and c != "channel"]
    else:
        cols = [c for c in cols if c not in exclude]
    if args.accepted_filter:
        # DATA-5's CSV carries the same sweep under two labels (the deck tag and the report tag);
        # comparing against both would report a duplicate-row difference that is not a difference
        rx = re.compile(args.accepted_filter)
        accepted = [r for r in accepted if rx.search(r.get(args.group_col, ""))]
        print("ACCEPTED_FILTER: %s rows=%d" % (args.accepted_filter, len(accepted)))
    if args.new_filter:
        rx = re.compile(args.new_filter)
        new = [r for r in new if rx.search(r.get(args.group_col, ""))]
        print("OA_RUN_FILTER: %s rows=%d" % (args.new_filter, len(new)))
    if not accepted or not new:
        print("COMPARE: FAIL (empty input: %d/%d rows)" % (len(accepted), len(new)))
        return 1
    worst, problems, detail = compare(accepted, new, args.group_re, args.group_col, cols, xcol,
                                      set(exclude), args.current_tol, args.voltage_tol)
    if args.out:
        exists = os.path.isfile(args.out)
        fh = io.open(args.out, "a", encoding="utf-8", newline="\n")
        if not exists:
            fh.write(u"dataset,group,column,accepted,oa_run,delta,tolerance,verdict\n")
        for row in detail:
            fh.write(u",".join([args.dataset or os.path.basename(args.new)] + row) + u"\n")
        fh.close()
        print("COMPARE_DETAIL: %s rows=%d" % (args.out, len(detail)))
    print("ACCEPTED: %s rows=%d" % (args.accepted, len(accepted)))
    print("OA_RUN: %s rows=%d" % (args.new, len(new)))
    for (c,), (d, where) in sorted(worst.items()):
        print("MAXDELTA %-22s %.9g   (%s)" % (c, d, where))
    for p in problems[:30]:
        print("DELTA_PROBLEM: %s" % p)
    if len(problems) > 30:
        print("DELTA_PROBLEM_MORE: %d" % (len(problems) - 30))
    verdict = "PASS" if not problems else "FAIL"
    print("REGRESSION_MATCH: %s" % verdict)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
