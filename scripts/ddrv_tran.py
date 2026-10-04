#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_tran.py -- switch-on / switch-off metrics for one data-driver channel transient.

The PSF-ASCII transient carries `vsw` (the ideal output test source), `data_out` (the
device drain) and `data_en`. The absorbed current is read the same way as in the DC
characterisation (scripts/ddrv_probe.py): a zero-drop `iprobe` trace when the deck has one,
otherwise the sense-resistor reconstruction

    IOUT(t) = (V(vsw) - V(data_out(t))) / RSEN          LEGACY_BURDENED_MEASUREMENT

Metrics (POC characterisation criteria, NOT course requirements):
  TURN_ON_SETTLING : worst, over all ON windows, time from the DATA_EN rising edge until
                     IOUT stays inside +/-band for HOLD_FRAC of that window
  TURN_OFF         : worst, over all OFF windows, time from the falling edge until |IOUT|
                     stays below the band
  PEAK_UA          : largest |IOUT| in the run
  OFF_LEAKAGE_UA   : worst mean |IOUT| over the last 30% of an OFF window
  ON_SETTLED_UA    : mean IOUT over the last 30% of each ON window, min..max across windows
  ON_RIPPLE        : peak-to-peak sample alternation inside that tail (numerical honesty:
                     method=traponly with maxstep ~ the gate RC alternates around the true
                     value, so a median would report one branch of it)
  VBIAS_SHARED     : min..max of the shared bias node, i.e. the ripple the gating produces
  VBIAS_CH         : min..max of this channel's own mirror gate (candidate E), plus the
                     worst VBIAS_SHARED - VBIAS_CH gate-pass deficit

Measuring per window is the point. An earlier version of this script searched the whole
run and borrowed samples from the next cycle, which turned a 200 ns period into a
"settling time" of 837 ns and reported 12 uA as OFF leakage -- both wrong, and both only
catchable by looking at the waveform (scripts/ddrv_dump.py).
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddrv_probe

VSPLIT = 0.9            # DATA_EN threshold: half of the 1.8 V pulse (POC_ASSUMPTION)


def parse(path):
    """Return (names, rows); rows are dicts keyed by signal, with 'time' set.

    `names` is every trace that actually carries data, not only the ones declared with
    PROP(...): this build writes the transient TRACE section as `"Ip1:i" "A"` (name plus
    unit) with no PROP block at all, and a lookup keyed off the declaration style silently
    reported "no iprobe trace" on a file that contains one.
    """
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
            if key not in names:
                names.append(key)
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


def mean(xs):
    return sum(xs) / float(len(xs)) if xs else None


def ringing_metrics(series):
    """Estimate 2-sample alternation (trapezoidal ringing) inside one settled sequence.

    The point of making this step-locked rather than amplitude-only: a real circuit ripple
    survives a change of print step or integration method, while trapezoidal ringing
    alternates sign at (almost) every sample because the trapezoidal rule is not L-stable.
      flip_ratio : fraction of consecutive first-differences whose sign alternates
      alt_p2p    : median |x[i+1] - x[i]|. For a pure 2-cycle oscillation this IS its
                   peak-to-peak swing; a monotone settling ramp has the same median step,
                   which is exactly why a YES needs BOTH numbers and not just an amplitude.
    """
    if len(series) < 5:
        return None, None, 0
    diffs = [series[i + 1] - series[i] for i in range(len(series) - 1)]
    nz = [d for d in diffs if d != 0.0]
    if len(nz) < 3:
        return None, None, len(series)
    flips = sum(1 for a, b in zip(nz, nz[1:]) if (a > 0) != (b > 0))
    flip_ratio = flips / float(len(nz) - 1)
    return flip_ratio, median([abs(d) for d in nz]), len(series)


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
    ap.add_argument("--net-suffix", default="",
                    help="'1' to measure channel 1 of the two-channel deck")
    ap.add_argument("--ensig", default="data_en",
                    help="which enable net marks the windows (data_en or data_en1)")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--require-probe", action="store_true",
                    help="FAIL instead of falling back to the sense resistor")
    ap.add_argument("--gate-net", default=None,
                    help="extra node to report min/max for, e.g. vbias_ch (candidate E)")
    ap.add_argument("--ring-floor", type=float, default=0.001,
                    help="sawtooth amplitude, as a fraction of the target current, above "
                         "which adjacent-point alternation is reported as YES")
    a = ap.parse_args()

    if not os.path.isfile(a.psf):
        print("DATA_DRIVER_TRAN: FAIL (no data file at %s)" % a.psf)
        return 1
    names, rows = parse(a.psf)
    vsn, onn = "vsw" + a.net_suffix, "data_out" + a.net_suffix
    for need in (vsn, onn, a.ensig):
        if not rows or need not in rows[0]:
            print("DATA_DRIVER_TRAN: FAIL (trace %s missing; have %s)" % (need, names))
            return 1
    method, pk, dk = ddrv_probe.method_for(names, a.net_suffix,
                                           allow_legacy=not a.require_probe)
    if method is None:
        print("DATA_DRIVER_TRAN: FAIL (no iprobe trace and --require-probe was given; "
              "have %s)" % names)
        return 1
    for r in rows:
        r["iout"] = ddrv_probe.current(r, method, pk, a.rsen, vsn, onn)
    rows.sort(key=lambda r: r["time"])
    ddrv_probe.report(method, pk, dk, rows, a.rsen, note=(
        "in a transient Ip1:i and Mout:1 are not expected to be equal: the node between "
        "Mcas and Mout is charged and discharged through them, so their difference is that "
        "displacement current. DC sweeps (where it is < 0.2 %% of full scale) are the "
        "agreement test; here the two traces are reported as the circuit's own dynamics"))
    t0, t1 = rows[0]["time"], rows[-1]["time"]
    up, down = edges(rows, a.ensig)
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

    def interior(w, frac, transform=None):
        """Values over the last `frac` of a window, with BOTH window edges excluded.

        The sample that sits on the falling or rising edge belongs to the edge, not to the
        settled level: a 1 ns edge sample averaged into a 30-sample tail moved the mean by
        ~10 % (which is how a 0.03 uA OFF leakage read as 0.63 uA). The mean is not robust
        the way a median is, so the interval has to be honest instead.
        """
        def val(q):
            return transform(q) if transform else q["iout"]
        if len(w) < 4:
            return [val(q) for q in w]
        span = w[-1]["time"] - w[0]["time"]
        dt = span / (len(w) - 1)
        guard = max(2.0 * dt, 0.02 * span)
        hi = w[-1]["time"] - guard
        lo = w[0]["time"] + (1.0 - frac) * span
        sel = [val(q) for q in w if lo <= q["time"] <= hi]
        return sel or [val(q) for q in w[1:-1]] or [val(w[-1])]

    on_delays, on_lens, on_settled, on_ripple, on_series = [], [], [], [], []
    for (u, d) in ons:
        w = in_win(u, d)
        if len(w) < 3:
            continue
        L = w[-1]["time"] - w[0]["time"]
        on_lens.append(L)
        on_delays.append(settle_in(w, a.hold_frac * L, "on"))
        # The level the window actually ends up at, so a transient result can be compared
        # with the DC curve instead of being assumed equal to it. MEAN, not median: with
        # method=traponly and a print step comparable to the local gate RC, adjacent samples
        # alternate around the true value, and a median then reports one branch of the
        # alternation -- which made the settled current look step-dependent (14.73 vs 15.19
        # uA at the same operating point). The alternation itself is reported as RIPPLE.
        tail = interior(w, 0.3)
        on_settled.append(mean(tail))
        on_ripple.append(max(tail) - min(tail))
        on_series.append(interior(w, 0.7))
    off_delays, leaks, off_ripple = [], [], []
    for (d, u) in offs:
        w = in_win(d, u)
        if len(w) < 3:
            continue
        L = w[-1]["time"] - w[0]["time"]
        off_delays.append(settle_in(w, min(a.hold_frac * L, L * 0.9), "off"))
        quiet = interior(w, 0.3, transform=lambda q: abs(q["iout"]))
        leaks.append(mean(quiet))
        off_ripple.append(max(quiet) - min(quiet))

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
    off_rip_txt = "n/a" if not off_ripple else "%.6f uA" % (max(off_ripple) * 1e6)
    print("   OFF_LEAKAGE       : %s   (worst mean over the last 30%% of the OFF window "
          "INTERIOR, edges excluded; sample ripple %s)"
          % ("n/a" if leak_max is None else "%.6f uA" % (leak_max * 1e6), off_rip_txt))
    on_set_lo = on_set_hi = on_set_err = on_rip_max = None
    if on_settled:
        on_set_lo, on_set_hi = min(on_settled), max(on_settled)
        on_set_err = max(abs(x - a.target) for x in on_settled)
        on_rip_max = max(on_ripple)
        print("   ON_SETTLED        : %.6f .. %.6f uA (mean over the last 30%% of the ON "
              "window INTERIOR, edges excluded), worst |I - target| = %.6f uA = %.3f %%   "
              "<- compare with the DC curve at the same VOUT"
              % (on_set_lo * 1e6, on_set_hi * 1e6, on_set_err * 1e6,
                 on_set_err / abs(a.target) * 100.0))
        print("   ON_RIPPLE         : %.6f uA peak-to-peak worst (spread of the settled tail; "
              "could be circuit ripple or solver alternation -- RINGING below separates them)"
              % (on_rip_max * 1e6,))

    ring_flip = ring_p2p = None
    ring_n = 0
    ring_yes = "NO"
    if on_series:
        per = [ringing_metrics(s) for s in on_series]
        per = [p for p in per if p[0] is not None and p[1] is not None]
        if per:
            ring_flip, ring_p2p, _n = max(per, key=lambda p: p[1])
            ring_n = sum(p[2] for p in per)
            floor = a.ring_floor * abs(a.target)
            ring_yes = "YES" if (ring_p2p >= floor and ring_flip >= 0.70) else "NO"
            print("   RINGING           : ADJACENT_POINT_ALTERNATION: %s   (worst alternation "
                  "%.6f uA p2p, sign-flip ratio %.3f, %d samples over %d ON windows; YES needs "
                  "p2p >= %.4f uA and flips >= 0.70. Step-locked by construction, so a real "
                  "ripple survives changing maxstep while ringing does not.)"
                  % (ring_yes, ring_p2p * 1e6, ring_flip, ring_n, len(per), floor * 1e6))
        else:
            print("   RINGING           : not measurable (fewer than 5 distinct samples per "
                  "ON window interior)")



    # The rework claim under test is "the shared VBIAS now stays up". Measure it instead of
    # asserting it: a structure that quietly kept charging a gate node would still pass the
    # current-window checks.
    vb_lo = vb_hi = vb_dev = None
    if "vbias" in rows[0]:
        vs = [r["vbias"] for r in rows]
        vb_lo, vb_hi = min(vs), max(vs)
        vb_med = median(vs)
        vb_dev = max(abs(vb_med - vb_lo), abs(vb_hi - vb_med))
        print("   VBIAS_SHARED      : %.6f .. %.6f V   (worst deviation %.6f V = %.4f %% of 1.8 V)"
              % (vb_lo, vb_hi, vb_dev, vb_dev / 1.8 * 100.0))
    gsig = a.gate_net or ("vbias_ch" + a.net_suffix)
    g_lo = g_hi = None
    if gsig in rows[0]:
        gs = [r[gsig] for r in rows]
        g_lo, g_hi = min(gs), max(gs)
        print("   %s : %.6f .. %.6f V   (the channel's own mirror gate: ON must reach "
              "VBIAS_SHARED, OFF must reach 0)" % (gsig.upper(), g_lo, g_hi))
        if "vbias" in rows[0]:
            deficit = max(r["vbias"] - r[gsig] for r in rows)
            print("   GATE_PASS_ERROR   : worst (VBIAS_SHARED - %s) = %.6f V   "
                  "(a pass device that cannot equal its input leaves the mirror short)"
                  % (gsig, deficit))

    if a.csv:
        exists = os.path.isfile(a.csv)
        dd = os.path.dirname(os.path.abspath(a.csv))
        if dd and not os.path.isdir(dd):
            os.makedirs(dd)
        # The header, the format and the value tuple are named so their field counts can be
        # checked against each other. Two rounds of this project already produced a CSV whose
        # last column was silently dropped by a placeholder the format string did not have,
        # and a deliverable that quietly loses a measurement is worse than one that fails.
        csv_hdr = (u"label,samples,on_windows,off_windows,longest_on_window_s,"
                   u"turn_on_settling_s,turn_off_s,peak_uA,off_leakage_uA,band_pct,"
                   u"on_windows_not_settled,iout_method,vbias_shared_min_v,"
                   u"vbias_shared_max_v,vbias_shared_dev_v,gate_net_min_v,"
                   u"gate_net_max_v,on_settled_min_uA,on_settled_max_uA,"
                   u"on_settled_worst_err_pct,on_ripple_p2p_uA,ring_alternation_p2p_uA,"
                   u"ring_flip_ratio,adjacent_point_alternation\n")
        csv_fmt = (u"%s,%d,%d,%d,%s,%s,%s,%.6f,%s,%.1f,%d,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                   u"%s,%s,%s\n")
        csv_vals = (
            a.label, len(rows), len(on_delays), len(off_delays),
            "%.6g" % max(on_lens) if on_lens else "n/a",
            "NOT_FOUND" if worst_on is None else "%.4g" % worst_on,
            "NOT_FOUND" if worst_off is None else "%.4g" % worst_off,
            peak * 1e6, "n/a" if leak_max is None else "%.6f" % (leak_max * 1e6),
            a.band * 100, n_on_fail, method,
            "n/a" if vb_lo is None else "%.6f" % vb_lo,
            "n/a" if vb_hi is None else "%.6f" % vb_hi,
            "n/a" if vb_dev is None else "%.6f" % vb_dev,
            "n/a" if g_lo is None else "%.6f" % g_lo,
            "n/a" if g_hi is None else "%.6f" % g_hi,
            "n/a" if on_set_lo is None else "%.6f" % (on_set_lo * 1e6),
            "n/a" if on_set_hi is None else "%.6f" % (on_set_hi * 1e6),
            "n/a" if on_set_err is None else "%.4f" % (on_set_err / abs(a.target) * 100.0),
            "n/a" if on_rip_max is None else "%.6f" % (on_rip_max * 1e6),
            "n/a" if ring_p2p is None else "%.6f" % (ring_p2p * 1e6),
            "n/a" if ring_flip is None else "%.3f" % ring_flip, ring_yes)
        n_col = csv_hdr.rstrip(u"\n").count(u",") + 1
        n_slot = len(re.findall(u"%[-+ #0]*[0-9.]*[a-zA-Z]", csv_fmt))
        if not (n_col == n_slot == len(csv_vals)):
            print("DATA_DRIVER_TRAN: FAIL (csv field mismatch: header=%d format=%d args=%d "
                  "-- refusing to write a CSV that silently drops a column)"
                  % (n_col, n_slot, len(csv_vals)))
            return 1
        with io.open(a.csv, "a" if exists else "w", encoding="utf-8", newline="") as fh:
            if not exists:
                fh.write(csv_hdr)
            fh.write(csv_fmt % csv_vals)

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
