#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_tran.py -- switch-on / switch-off metrics for one data-driver channel transient.

The PSF-ASCII transient carries `vsw` (the ideal output test source), `data_out` (the
device drain) and `data_en`; the absorbed current is reconstructed across the sense
resistor, exactly as in the DC characterisation:

    IOUT(t) = (V(vsw) - V(data_out(t))) / RSEN

Metrics (POC characterisation criteria, NOT course requirements):
  TURN_ON_SETTLING : worst, over all ON windows, time from the DATA_EN rising edge until
                     IOUT stays inside +/-band for HOLD_FRAC of that window
  TURN_OFF         : worst, over all OFF windows, time from the falling edge until |IOUT|
                     stays below the band
  PEAK_UA          : largest |IOUT| in the run
  OFF_LEAKAGE_UA   : worst median |IOUT| over the last 30% of an OFF window

Measuring per window is the point. An earlier version of this script searched the whole
run and borrowed samples from the next cycle, which turned a 200 ns period into a
"settling time" of 837 ns and reported 12 uA as OFF leakage -- both wrong, and both only
catchable by looking at the waveform (scripts/ddrv_dump.py).
"""

from __future__ import print_function

import argparse
import io
import os
import sys

VSPLIT = 0.9            # DATA_EN threshold: half of the 1.8 V pulse (POC_ASSUMPTION)


def parse(path):
    """Return (names, rows); rows are dicts keyed by signal, with 'time' set."""
    names, rows, cur, invalue = [], [], {}, False
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if s == "VALUE":
                invalue = True
                continue
            if not invalue or not s.startswith('"'):
                continue
            parts = s.split('"')
            if len(parts) < 3:
                continue
            key, rest = parts[1], " ".join(parts[2:]).strip()
            if rest.startswith("PROP("):
                if key not in names:
                    names.append(key)
                continue
            try:
                val = float(rest.split()[0])
            except (ValueError, IndexError):
                continue
            if key == "time":
                if cur:
                    rows.append(cur)
                cur = {"time": val}
            else:
                cur[key] = val
    if cur:
        rows.append(cur)
    return names, rows


def edges(rows, sig):
    """Adjacent-pair crossings with linear interpolation (the C2MOS checker's rule): a
    signal already high at the first sample must not be counted as a crossing."""
    up, down, prev = [], [], None
    for r in rows:
        v = r[sig]
        if prev is not None:
            if prev[1] <= VSPLIT < v:
                f = (VSPLIT - prev[1]) / (v - prev[1]) if v != prev[1] else 0.0
                up.append(prev[0] + f * (r["time"] - prev[0]))
            elif prev[1] >= VSPLIT > v:
                f = (prev[1] - VSPLIT) / (prev[1] - v) if prev[1] != v else 0.0
                down.append(prev[0] + f * (r["time"] - prev[0]))
        prev = (r["time"], v)
    return up, down


def windows(up, down):
    """Pair edges into (on_start, on_end) and (off_start, off_end) intervals."""
    ons, offs = [], []
    for u in up:
        later = [x for x in down if x > u]
        if later:
            ons.append((u, later[0]))
    for d in down:
        later = [x for x in up if x > d]
        if later:
            offs.append((d, later[0]))
    return ons, offs


def median(xs):
    if not xs:
        return None
    y = sorted(xs)
    return y[len(y) // 2] if len(y) % 2 else 0.5 * (y[len(y) // 2 - 1] + y[len(y) // 2])


def worst(values):
    good = [v for v in values if v is not None]
    return max(good) if good else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("psf")
    ap.add_argument("--rsen", type=float, default=1e4)
    ap.add_argument("--target", type=float, default=15e-6)
    ap.add_argument("--band", type=float, default=0.05)
    ap.add_argument("--hold-frac", type=float, default=0.4)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    if not os.path.isfile(a.psf):
        print("DATA_DRIVER_TRAN: FAIL (no data file at %s)" % a.psf)
        return 1
    names, rows = parse(a.psf)
    for need in ("vsw", "data_out", "data_en"):
        if not rows or need not in rows[0]:
            print("DATA_DRIVER_TRAN: FAIL (trace %s missing; have %s)" % (need, names))
            return 1
    for r in rows:
        r["iout"] = (r["vsw"] - r["data_out"]) / a.rsen
    rows.sort(key=lambda r: r["time"])
    t0, t1 = rows[0]["time"], rows[-1]["time"]
    up, down = edges(rows, "data_en")
    ons, offs = windows(up, down)
    tol = a.band * a.target
    peak = max(abs(r["iout"]) for r in rows)

    def in_win(lo, hi):
        return [r for r in rows if lo - 1e-18 <= r["time"] <= hi + 1e-18]

    def settle_in(w, hold, want):
        """First instant in this window from which the band holds for `hold` seconds. The
        tail must genuinely span `hold` inside the window; a window shorter than that fails
        honestly instead of drifting into the next cycle."""
        test = (lambda q: abs(q["iout"] - a.target) <= tol) if want == "on" \
            else (lambda q: abs(q["iout"]) <= tol)
        for i, r in enumerate(w):
            tail = [q for q in w[i:] if q["time"] <= r["time"] + hold]
            if len(tail) < 2 or tail[-1]["time"] - r["time"] < hold * 0.9:
                continue
            if all(test(q) for q in tail):
                return r["time"] - w[0]["time"]
        return None

    on_delays, on_lens = [], []
    for (u, d) in ons:
        w = in_win(u, d)
        if len(w) < 3:
            continue
        L = w[-1]["time"] - w[0]["time"]
        on_lens.append(L)
        on_delays.append(settle_in(w, a.hold_frac * L, "on"))
    off_delays, leaks = [], []
    for (d, u) in offs:
        w = in_win(d, u)
        if len(w) < 3:
            continue
        L = w[-1]["time"] - w[0]["time"]
        off_delays.append(settle_in(w, min(a.hold_frac * L, L * 0.9), "off"))
        quiet = [abs(q["iout"]) for q in w if q["time"] >= w[-1]["time"] - 0.3 * L]
        leaks.append(median(quiet))

    worst_on, worst_off = worst(on_delays), worst(off_delays)
    n_on_fail = sum(1 for x in on_delays if x is None)
    n_off_fail = sum(1 for x in off_delays if x is None)
    leak_max = worst(leaks)

    print("== %s  samples=%d  window=%.6g..%.6g s  ON windows=%d  OFF windows=%d"
          % (a.label or os.path.basename(a.psf), len(rows), t0, t1, len(on_delays),
             len(off_delays)))
    if on_lens:
        print("   longest ON window : %.4g s   (band must hold for %.0f%% of it)"
              % (max(on_lens), a.hold_frac * 100))
    print("   TURN_ON_SETTLING  : %s   (worst of %d, %d never settled)"
          % ("NOT_FOUND" if worst_on is None else "%.4g s" % worst_on,
             len(on_delays), n_on_fail))
    print("   TURN_OFF          : %s   (worst of %d, %d never met the band)"
          % ("NOT_FOUND" if worst_off is None else "%.4g s" % worst_off,
             len(off_delays), n_off_fail))
    print("   PEAK              : %.6f uA" % (peak * 1e6))
    print("   OFF_LEAKAGE       : %s   (worst median over the last 30%% of an OFF window)"
          % ("n/a" if leak_max is None else "%.6f uA" % (leak_max * 1e6)))

    if a.csv:
        exists = os.path.isfile(a.csv)
        dd = os.path.dirname(os.path.abspath(a.csv))
        if dd and not os.path.isdir(dd):
            os.makedirs(dd)
        with io.open(a.csv, "a" if exists else "w", encoding="utf-8", newline="") as fh:
            if not exists:
                fh.write(u"label,samples,on_windows,off_windows,longest_on_window_s,"
                         u"turn_on_settling_s,turn_off_s,peak_uA,off_leakage_uA,band_pct,"
                         u"on_windows_not_settled\n")
            fh.write(u"%s,%d,%d,%d,%s,%s,%s,%.6f,%s,%.1f,%d\n"
                     % (a.label, len(rows), len(on_delays), len(off_delays),
                        "%.6g" % max(on_lens) if on_lens else "n/a",
                        "NOT_FOUND" if worst_on is None else "%.4g" % worst_on,
                        "NOT_FOUND" if worst_off is None else "%.4g" % worst_off,
                        peak * 1e6, "n/a" if leak_max is None else "%.6f" % (leak_max * 1e6),
                        a.band * 100, n_on_fail))

    if not ons:
        print("DATA_DRIVER_TRAN: FAIL (no complete ON window in the run)")
        return 1
    if worst_on is None or n_on_fail:
        print("DATA_DRIVER_TRAN: FAIL (IOUT does not stay inside +/-%.0f%% for %.0f%% of the "
              "ON window in %d/%d ON windows -- at this period the pixel is not regulated "
              "for most of the time it is selected)"
              % (a.band * 100, a.hold_frac * 100, n_on_fail, len(on_delays)))
        return 1
    print("DATA_DRIVER_TRAN: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
