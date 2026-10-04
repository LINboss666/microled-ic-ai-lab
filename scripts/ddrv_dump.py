#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_dump.py -- print a few samples of a PSF-ASCII run, for reading a curve by eye.

    python scripts/ddrv_dump.py <psfascii> [--stride 12] [--rsen 1e4] [--limit 26]

Exists because "the checker said 8.4e-7 s" is not evidence: the numbers here came from a
waveform that had to be looked at.
"""

from __future__ import print_function

import argparse
import io
import sys


def parse(path):
    rows, cur, inv = [], {}, False
    for line in io.open(path, encoding="utf-8", errors="replace"):
        s = line.strip()
        if s == "VALUE":
            inv = True
            continue
        if not inv or not s.startswith('"'):
            continue
        p = s.split('"')
        if len(p) < 3:
            continue
        k, rest = p[1], " ".join(p[2:]).strip()
        if rest.startswith("PROP("):
            continue
        try:
            v = float(rest.split()[0])
        except (ValueError, IndexError):
            continue
        if k in ("time", "dc"):
            if cur:
                rows.append(cur)
            cur = {"x": v}
        else:
            cur[k] = v
    if cur:
        rows.append(cur)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("psf")
    ap.add_argument("--stride", type=int, default=12)
    ap.add_argument("--rsen", type=float, default=1e4)
    ap.add_argument("--limit", type=int, default=26)
    a = ap.parse_args()
    rows = parse(a.psf)
    print("samples=%d" % len(rows))
    keys = [k for k in ("data_en", "vsw", "data_out", "vbias", "node_m", "ref_top")
            if rows and k in rows[0]]
    print("x  " + "  ".join("%s" % k for k in keys) + "  iout_uA")
    for r in rows[::a.stride][:a.limit]:
        i = None
        if "vsw" in r and "data_out" in r:
            i = (r["vsw"] - r["data_out"]) / a.rsen * 1e6
        print("%.4e  %s  %s" % (r["x"], "  ".join("%.4f" % r[k] for k in keys),
                                 "%.4f" % i if i is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
