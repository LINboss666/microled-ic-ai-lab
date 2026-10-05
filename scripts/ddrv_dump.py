#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_dump.py -- print samples of a PSF-ASCII run, for reading a curve by eye.

    python scripts/ddrv_dump.py <psfascii> [--stride 12] [--rsen 1e4] [--limit 26]
                                [--t0 0.2e-6] [--t1 0.5e-6]

Exists because "the checker said 8.4e-7 s" is not evidence: the numbers here came from a
waveform that had to be looked at. `--t0/--t1` zoom into one switching window, which is how
the per-window metrics were debugged. IOUT is taken from the iprobe trace when the run has
one, otherwise reconstructed from the sense resistor (LEGACY_BURDENED_MEASUREMENT).
"""

from __future__ import print_function

import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddrv_probe

KEYS = ("data_en", "data_en_b", "vsw", "data_out", "vbias", "vbias_ch", "node_m",
        "vcas", "ref_top", "Ip1:i", "Ip2:i", "Mout:1", "Mout1:1")


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
    ap.add_argument("--t0", type=float, default=None, help="zoom: first time to print (s)")
    ap.add_argument("--t1", type=float, default=None, help="zoom: last time to print (s)")
    ap.add_argument("--net-suffix", default="")
    a = ap.parse_args()
    rows = parse(a.psf)
    names = list(rows[0].keys()) if rows else []
    method, pk, _dk = ddrv_probe.method_for(names, a.net_suffix)
    print("samples=%d  iout from %s%s" % (len(rows), method if pk is None else "%s trace %s"
                                          % (method, pk),
                                          "  [%s]" % ddrv_probe.LEGACY_TAG
                                          if method == ddrv_probe.LEGACY else ""))
    keys = [k for k in KEYS if rows and k in rows[0]]
    print("x  " + "  ".join("%s" % k for k in keys) + "  iout_uA")
    sel = [r for r in rows
           if (a.t0 is None or r["x"] >= a.t0 - 1e-18)
           and (a.t1 is None or r["x"] <= a.t1 + 1e-18)]
    for r in sel[::a.stride][:a.limit]:
        i = ddrv_probe.current(r, method, pk, a.rsen, "vsw" + a.net_suffix,
                               "data_out" + a.net_suffix)
        print("%.4e  %s  %.6f" % (r["x"], "  ".join(
            ("%9.6f" % r[k]) if k in r else "        -" for k in keys), i * 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
