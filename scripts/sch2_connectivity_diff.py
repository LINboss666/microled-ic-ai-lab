#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-2 Part H: prove that a parameter fix did not change the schematic's structure.

Compares two readback logs (see skill/sch2_readback.il): instance set, masters, models, the net on
every D/G/S/B terminal, the net list with its port pins, and the counts. Only the size fields are
expected to differ, so anything else that moves is reported and the exit code is non-zero.

Usage: python scripts/sch2_connectivity_diff.py --before pre.log --after post.log
"""
from __future__ import print_function

import argparse
import io
import re
import sys

PAIR = re.compile(r'(\w+)=(?:"([^"]*)"|(\((?:[^()]|\([^()]*\))*\))|([^\s]+))')
SIZE_KEYS = ("raw_l", "raw_w", "raw_fw", "raw_fingers", "raw_mult", "simW",
             "cdf_l", "cdf_w", "cdf_fw", "cdf_fingers", "cdf_mult", "num_l", "num_w", "bbox")


def rows_of(path):
    out, pins, summary = {}, [], {}
    for line in io.open(path, encoding="utf-8", errors="replace"):
        if "RD-ROW" in line:
            r = {}
            for m in PAIR.finditer(line):
                v = m.group(2)
                if v is None:
                    v = m.group(3) if m.group(3) is not None else m.group(4)
                r[m.group(1)] = v.strip()
            out[r.get("inst")] = r
        elif "RD-NETPIN" in line:
            m = re.search(r'net="?([^"\s]+)"?', line)
            if m:
                pins.append(m.group(1))
        elif "RD-CELL" in line:
            for m in PAIR.finditer(line):
                summary[m.group(1)] = m.group(2) or m.group(4)
    return out, sorted(set(pins)), summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    args = ap.parse_args()

    before, pins_b, sum_b = rows_of(args.before)
    after, pins_a, sum_a = rows_of(args.after)
    diffs = []

    if sorted(before) != sorted(after):
        diffs.append("instance set changed: only-before=%s only-after=%s"
                     % (sorted(set(before) - set(after)), sorted(set(after) - set(before))))
    for name in sorted(set(before) & set(after)):
        b, a = before[name], after[name]
        for field in ("master_lib", "master_cell", "master_view", "model", "D", "G", "S", "B"):
            if b.get(field) != a.get(field):
                diffs.append("%s.%s: %s -> %s" % (name, field, b.get(field), a.get(field)))
    if pins_b != pins_a:
        diffs.append("port pins: %s -> %s" % (" ".join(pins_b), " ".join(pins_a)))
    for key in ("instances", "nets", "shapes"):
        if sum_b.get(key) != sum_a.get(key):
            diffs.append("%s count: %s -> %s" % (key, sum_b.get(key), sum_a.get(key)))

    print("MOS_ROWS_BEFORE: %d" % len(before))
    print("MOS_ROWS_AFTER: %d" % len(after))
    print("INSTANCE_COUNT_UNCHANGED: %s" % ("PASS" if sorted(before) == sorted(after) else "FAIL"))
    def any_field(*names):
        return any(any(("%s." % n) in d for n in names) for d in diffs)
    print("CONNECTIVITY_UNCHANGED: %s"
          % ("FAIL" if any_field("D", "G", "S", "B") else "PASS"))
    print("MASTERS_UNCHANGED: %s"
          % ("FAIL" if any_field("master_lib", "master_cell", "master_view", "model") else "PASS"))
    print("EXTERNAL_PORTS_UNCHANGED: %s" % ("PASS" if pins_b == pins_a else "FAIL"))
    print("COUNTS_UNCHANGED: %s" % ("FAIL" if any("count:" in d for d in diffs) else "PASS"))
    for d in diffs:
        print("STRUCTURE_DIFF: %s" % d)
    if not diffs:
        print("SCHEMATIC_STRUCTURE_UNCHANGED: PASS")
        return 0
    print("SCHEMATIC_STRUCTURE_UNCHANGED: FAIL")
    return 1


sys.exit(main())
