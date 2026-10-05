#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_curve_diff.py -- max deviation between two DC IOUT(V_DATA_OUT) curves.

The claim under test is "the reworked gating leaves the accepted current core untouched".
That is a curve comparison, not a comparison of two headline numbers: a compliance that
happens to land on the same grid point can still hide a curve that moved.

    python scripts/ddrv_curve_diff.py <a.psf> <b.psf> [--label-a ...] [--label-b ...]
                                      [--net-suffix ""] [--rsen 1e4] [--target 15e-6]
                                      [--knee <V>] [--csv out.csv]

Points are matched on V(DATA_OUT) within MATCH_MV; both decks must therefore be swept with
the same step (they are generated from the same builder, and a mismatch is reported rather
than silently interpolated). MAX deviation is the deciding number and is reported both over
the whole sweep and above --knee (the regulating region), because below the knee the
channel is legitimately not in current control.
"""

from __future__ import print_function

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ddrv_characterize import parse_records      # one PSF reader, not two
import ddrv_probe

MATCH_MV = 1.0                                  # 1 mV: the decks share a 20 mV sweep grid


def curve(path, suffix, rsen):
    rows, names = parse_records(path)
    if not rows:
        return None, None, "no VALUE records in %s" % path
    method, pk, dk = ddrv_probe.method_for(names, suffix)
    vsn, onn = "vsw" + suffix, "data_out" + suffix
    if any(k not in rows[0] for k in (vsn, onn)):
        return None, None, "traces %s/%s missing in %s" % (vsn, onn, path)
    pts = {}
    for r in rows:
        v = r[onn]
        key = round(v * 1000.0)                  # mV bucket
        pts[key] = (v, ddrv_probe.current(r, method, pk, rsen, vsn, onn))
    return method, pts, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--net-suffix", default="")
    ap.add_argument("--rsen", type=float, default=1e4)
    ap.add_argument("--target", type=float, default=15e-6)
    ap.add_argument("--knee", type=float, default=None,
                    help="regulating region: only points at or above this V(DATA_OUT)")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    for p in (a.a, a.b):
        if not os.path.isfile(p):
            print("CURVE_DIFF: FAIL (no data file at %s)" % p)
            return 1
    ma, pa, erra = curve(a.a, a.net_suffix, a.rsen)
    mb, pb, errb = curve(a.b, a.net_suffix, a.rsen)
    if erra or errb:
        print("CURVE_DIFF: FAIL (%s)" % (erra or errb))
        return 1
    common = sorted(set(pa) & set(pb))
    if not common:
        print("CURVE_DIFF: FAIL (no V(DATA_OUT) sample within %.0f mV in common)" % MATCH_MV)
        return 1
    skipped = len(set(pa) ^ set(pb))

    rows = []
    for k in common:
        va, ia = pa[k]
        vb, ib = pb[k]
        rows.append((va, ib, ia, ib - ia))       # vout, I_b, I_a, delta
    worst = max(rows, key=lambda r: abs(r[3]))
    sum_sq = sum(r[3] * r[3] for r in rows)
    rms = (sum_sq / len(rows)) ** 0.5

    def fmt(tag, sel):
        if not sel:
            print("   %-22s : (no points)" % tag)
            return None
        w = max(sel, key=lambda r: abs(r[3]))
        print("   %-22s : max %.6f uA = %.4f %% of target at VOUT=%.4f V   "
              "(rms %.6f uA, %d pts)"
              % (tag, w[3] * 1e6, w[3] / a.target * 100.0, w[0],
                 (sum(q[3] ** 2 for q in sel) / len(sel)) ** 0.5 * 1e6, len(sel)))
        return w

    print("== CURVE_DIFF  A=%s (%s)   B=%s (%s)"
          % (a.label_a, ma, a.label_b, mb))
    print("   matched %d points, %d points only on one side" % (len(common), skipped))
    fmt("MAX_DEVIATION_all", rows)
    if a.knee is not None:
        fmt("MAX_DEVIATION_>knee", [r for r in rows if r[0] >= a.knee - 1e-12])
    print("   worst pair: A=%.6f uA  B=%.6f uA at VOUT=%.4f V" % (worst[2] * 1e6,
                                                                  worst[1] * 1e6, worst[0]))
    print("   rms over all matched points: %.6f uA = %.4f %% of target"
          % (rms * 1e6, rms / a.target * 100.0))
    if a.csv:
        blob = (u"" if os.path.isfile(a.csv) else
                u"label_a,label_b,points,knee_V,max_dev_uA,max_dev_pct_of_target,"
                u"max_dev_at_vout_V,rms_dev_uA\n")
        blob += (u"%s,%s,%d,%s,%.6f,%.4f,%.4f,%.6f\n"
                 % (a.label_a, a.label_b, len(common),
                    "n/a" if a.knee is None else "%.4f" % a.knee,
                    worst[3] * 1e6, worst[3] / a.target * 100.0, worst[0], rms * 1e6))
        with open(a.csv, "ab") as fh:
            fh.write(blob.encode("utf-8") if not isinstance(blob, bytes) else blob)
    print("CURVE_DIFF: DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
