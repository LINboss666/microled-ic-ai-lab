#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_xtalk.py -- cross-channel error for the two-channel Candidate D testbench.

This is a separate analysis on purpose: the accepted checkers (ddrv_characterize.py,
ddrv_tran.py) keep their criteria untouched, so nothing here can make the rework pass by
moving a goalpost. It only answers the question the review asked:

    when channel 0 switches, how much does channel 1's current move?

    python scripts/ddrv_xtalk.py <psf> [--target 15e-6] [--rsen 1e4]
                                 [--ch 1] [--skip-frac 0.25] [--limit 0.01]
                                 [--steady <uA>] [--label ...] [--csv out.csv]

`--ch 1` reads the `vsw1` / `data_out1` / `data_en1` nets of the two-channel deck.
The first `--skip-frac` of the run is ignored so the initial power-up transient is not
counted as crosstalk; crosstalk is what happens around the *neighbour's* edges.
"""

from __future__ import print_function

import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ddrv_tran import parse, edges            # same PSF reader, no second implementation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("psf")
    ap.add_argument("--target", type=float, default=15e-6)
    ap.add_argument("--rsen", type=float, default=1e4)
    ap.add_argument("--ch", default="1")
    ap.add_argument("--skip-frac", type=float, default=0.25)
    ap.add_argument("--limit", type=float, default=0.01,
                    help="POC cross-channel criterion, fraction of the target current")
    ap.add_argument("--neigh-sig", default="data_en")
    ap.add_argument("--label", default="")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    suf = a.ch
    names, rows = parse(a.psf)
    need = ("vsw" + suf, "data_out" + suf)
    if not rows or any(n not in rows[0] for n in need):
        print("TWO_CHANNEL_INDEPENDENCE: FAIL (channel %s nets missing; have %s)"
              % (suf, names))
        return 2
    t0, t1 = rows[0]["time"], rows[-1]["time"]
    t_start = t0 + a.skip_frac * (t1 - t0)
    obs = [(r["time"], (r["vsw" + suf] - r["data_out" + suf]) / a.rsen, r) for r in rows
           if r["time"] >= t_start]
    if len(obs) < 3:
        print("TWO_CHANNEL_INDEPENDENCE: FAIL (too few samples after the skip window)")
        return 2

    steady = sum(o[1] for o in obs) / len(obs)
    dev = max(abs(o[1] - steady) for o in obs)
    dev_target = max(abs(o[1] - a.target) for o in obs)
    frac = dev_target / a.target
    # where in time the worst excursion happens, and was the neighbour switching then?
    worst_t = max(obs, key=lambda o: abs(o[1] - a.target))[0]
    up, down = ([], [])
    if a.neigh_sig in rows[0]:
        up, down = edges([r for _t, _i, r in obs], a.neigh_sig)
    near = None
    for e in up + down:
        if near is None or abs(e - worst_t) < abs(near - worst_t):
            near = e

    print("== %s  channel %s samples=%d (after skipping %.0f%% of the run)"
          % (a.label or os.path.basename(a.psf), suf or "0", len(obs),
             a.skip_frac * 100))
    print("   I_%s mean      : %.6f uA" % (suf or "0", steady * 1e6))
    print("   I_%s max excursion from its own mean : %.6f uA" % (suf or "0", dev * 1e6))
    print("   I_%s worst |I - 15uA|               : %.6f uA = %.3f %% of target"
          % (suf or "0", dev_target * 1e6, frac * 100.0))
    if near is not None:
        print("   worst sample at t=%.4e s, nearest neighbour edge at t=%.4e s "
              "(delta %.3e s)" % (worst_t, near, abs(worst_t - near)))
    else:
        print("   neighbour enable net `%s` not found: measuring the held value only"
              % a.neigh_sig)

    if a.csv:
        exists = os.path.isfile(a.csv)
        dd = os.path.dirname(os.path.abspath(a.csv))
        if dd and not os.path.isdir(dd):
            os.makedirs(dd)
        blob = (u"" if exists else
                u"label,channel,samples,mean_uA,max_err_uA,max_err_pct_of_target,limit_pct\n")
        blob += (u"%s,%s,%d,%.6f,%.6f,%.4f,%.1f\n"
                 % (a.label, suf or "0", len(obs), steady * 1e6, dev_target * 1e6,
                    frac * 100.0, a.limit * 100.0))
        with open(a.csv, "ab") as fh:
            fh.write(blob.encode("utf-8") if not isinstance(blob, bytes) else blob)

    if frac <= a.limit:
        print("TWO_CHANNEL_INDEPENDENCE: PASS (crosstalk %.3f %% <= %.1f %% POC criterion)"
              % (frac * 100.0, a.limit * 100.0))
        return 0
    print("TWO_CHANNEL_INDEPENDENCE: FAIL (crosstalk %.3f %% > %.1f %% POC criterion)"
          % (frac * 100.0, a.limit * 100.0))
    return 1


if __name__ == "__main__":
    sys.exit(main())
