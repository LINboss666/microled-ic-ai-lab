#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_xtalk.py -- cross-channel error for the two-channel data-driver testbench.

This is a separate analysis on purpose: the accepted checkers (ddrv_characterize.py,
ddrv_tran.py) keep their criteria untouched, so nothing here can make a rework pass by
moving a goalpost. It answers the question the review asked, in three parts:

    python scripts/ddrv_xtalk.py <psf> [--target 15e-6] [--rsen 1e4]
                                 [--ch 1] [--skip-frac 0.25] [--limit 0.01]
                                 [--band-frac 0.01] [--baseline-ua X] [--ref other.psf]
                                 [--slew-desc ...] [--label ...] [--csv out.csv]

  PEAK_CROSSTALK_ERROR   worst |I_victim - target| as a %% of the target current. This is
                         the number the previous round was judged on.
  Q_error / CHARGE_ERROR_PERCENT
                         the same event counted as charge instead of as a peak:
                             Q_error = integral( I_victim(t) - I_baseline(t) ) dt
                             CHARGE_ERROR_PERCENT = |Q_error| / (target * T_observed) * 100
                         A short spike that moves the average charge little and a long
                         droop that removes a frame's worth of charge are not the same
                         failure, and a peak-only metric cannot tell them apart.
  GLITCH_DURATION        time for which |I_victim - I_baseline| stays above
                         +/- band-frac * target (POC criterion, 1% by default).

I_victim is read from the iprobe trace when the deck has one, otherwise from the sense
resistor and labelled LEGACY_BURDENED_MEASUREMENT (scripts/ddrv_probe.py).

`I_baseline` is the victim's own steady level: the median of the observed window by
default, or a pinned value (--baseline-ua), or the same channel measured in a static deck
where the neighbour does not switch at all (--ref; only valid when both runs hold the same
V(DATA_OUT)). The first `--skip-frac` of the run is ignored so the initial power-up
transient is not counted as crosstalk.
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ddrv_tran import parse, edges, median, ringing_metrics   # one PSF reader, no second impl
import ddrv_probe


def csv_field(v):
    """Quote a free-text field: `--slew-desc` and `--label` legitimately contain commas, and
    an unquoted comma silently shifts every following column -- the header then lies about
    what the numbers are (this is how the corner table's `vbias_shared_min_v` came back
    holding the text " method=gear2only-")."""
    t = u"%s" % (v,)
    if u"," in t or u'"' in t:
        return u'"%s"' % t.replace(u'"', u'""')
    return t


def mean(xs):
    return sum(xs) / float(len(xs))


def integrate(ts, xs):
    """Trapezoid over a non-uniform sample sequence."""
    acc = 0.0
    for a, b in zip(range(len(xs) - 1), range(1, len(xs))):
        acc += 0.5 * (xs[a] + xs[b]) * (ts[b] - ts[a])
    return acc


def duration_above(ts, devs, tol):
    """Total seconds the deviation stays above tol, measured on adjacent sample intervals
    (a sample-based count would depend on the simulator's step, not on the circuit)."""
    total = 0.0
    for i in range(len(devs) - 1):
        if abs(devs[i]) > tol and abs(devs[i + 1]) > tol:
            total += ts[i + 1] - ts[i]
    return total


def metrics(obs, base, target, band_frac):
    """All four crosstalk numbers from one sample list. Split out of main() so the
    --selftest fixture checks the arithmetic, not just the file reading."""
    ts = [r["time"] for r in obs]
    cur = [r["iout"] for r in obs]
    dev = [q - base for q in cur]
    q_err = integrate(ts, dev)
    return {
        "t_span": ts[-1] - ts[0],
        "mean": mean(cur),
        "dev_max": max(abs(d) for d in dev),
        "err_vs_target": max(abs(c - target) for c in cur),
        "q_error": q_err,
        "charge_pct": abs(q_err) / (abs(target) * (ts[-1] - ts[0])) * 100.0,
        "glitch_s": duration_above(ts, dev, band_frac * abs(target)),
        # the documented POC criterion is a +/-5 % band held for a fraction of the window,
        # so report the victim's own hold as well as the 1 % glitch
        "outside5_s": duration_above(ts, dev, 0.05 * abs(target)),
        "worst_t": obs[max(range(len(cur)), key=lambda i: abs(dev[i]))]["time"],
    }


def selftest():
    """A known-answer check of the charge metric: a 3 uA glitch held for three samples of a
    15 uA victim (10 us spacing, so 20 us between the first and last high sample).

    The expected Q_error is the trapezoid of that shape, not 3uA x 20us: the rising and
    falling edge samples are half-weighted, which is exactly how a real spike of one sample
    width is counted. Getting this wrong in the checker would silently scale every charge
    number in the review, so it is asserted against hand arithmetic here instead.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qoder_xtalk_fixture.psf")
    lines = ["TRACE", '  "Ip2:i" PROP("signal" "v")', "VALUE"]
    n, dt = 101, 10e-6
    for i in range(n):
        t = i * dt
        iout = 15e-6 + (3e-6 if 50 <= i <= 52 else 0.0)
        lines.append('"time" %.9g' % t)
        lines.append('"Ip2:i" %.9g' % iout)
        lines.append('"vsw1" %.9g' % 1.2)
        lines.append('"data_out1" %.9g' % 1.2)
        lines.append('"data_en" %.9g' % (1.8 if i % 50 else 0.0))
    with open(path, "wb") as fh:
        fh.write(("\n".join(lines) + "\n").encode("utf-8"))
    try:
        names, rows = parse(path)
        for r in rows:
            r["iout"] = r["Ip2:i"]
        obs = [r for r in rows if r["time"] >= rows[0]["time"]]
        base = median([r["iout"] for r in obs])
        m = metrics(obs, base, 15e-6, 0.01)
        want = (("I_baseline", base, 15e-6),
                ("dev_max", m["dev_max"], 3e-6),
                ("q_error", m["q_error"], 2 * 3e-6 * 10e-6 + 2 * 0.5 * 3e-6 * 10e-6),
                ("charge_pct", m["charge_pct"], 9e-11 / (15e-6 * 1000e-6) * 100.0),
                ("glitch_s", m["glitch_s"], 20e-6),
                ("err_vs_target", m["err_vs_target"], 3e-6))
        problems = []
        for name, got, exp in want:
            if abs(got - exp) > 1e-12 * max(1.0, abs(exp)):
                problems.append("%s got %.9g want %.9g" % (name, got, exp))
        if problems:
            print("XTALK_SELFTEST: FAIL " + "; ".join(problems))
            return 1
        print("XTALK_SELFTEST: PASS  (baseline %.6g A, peak %.6g A, Q %.6g C, %.4f %%, "
              "glitch %.6g s over %.6g s)" % (base, m["dev_max"], m["q_error"],
                                              m["charge_pct"], m["glitch_s"], m["t_span"]))
        return 0
    finally:
        os.remove(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("psf", nargs="?", default=None)
    ap.add_argument("--target", type=float, default=15e-6)
    ap.add_argument("--rsen", type=float, default=1e4)
    ap.add_argument("--ch", default="1")
    ap.add_argument("--skip-frac", type=float, default=0.25)
    ap.add_argument("--limit", type=float, default=0.01,
                    help="POC cross-channel criterion, fraction of the target current")
    ap.add_argument("--band-frac", type=float, default=0.01,
                    help="glitch band as a fraction of the target (POC criterion)")
    ap.add_argument("--neigh-sig", default=None,
                    help="enable net of the toggling neighbour; default: the other channel")
    ap.add_argument("--baseline-ua", type=float, default=None,
                    help="pin I_baseline to this value in uA instead of the observed median")
    ap.add_argument("--ref", default=None,
                    help="static-deck psfascii of the same channel to take I_baseline from")
    ap.add_argument("--require-probe", action="store_true")
    ap.add_argument("--slew-desc", default="", help="what slew produced this row")
    ap.add_argument("--ring-floor", type=float, default=0.001,
                    help="alternation amplitude, as a fraction of the target current, above "
                         "which adjacent-point alternation is reported as YES")
    ap.add_argument("--label", default="")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="check the charge/glitch arithmetic against a known fixture and "
                         "exit; a metric nobody can reproduce is not evidence")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.psf:
        ap.error("psf is required unless --selftest")

    suf = a.ch                                  # "" for channel 0, "1" for channel 1
    names, rows = parse(a.psf)
    need = ("vsw" + suf, "data_out" + suf)
    if not rows or any(n not in rows[0] for n in need):
        print("TWO_CHANNEL_INDEPENDENCE: FAIL (channel %s nets missing; have %s)"
              % (suf or "0", names))
        return 2
    method, pk, dk = ddrv_probe.method_for(names, suf, allow_legacy=not a.require_probe)
    if method is None:
        print("TWO_CHANNEL_INDEPENDENCE: FAIL (no iprobe trace, --require-probe set)")
        return 2
    rows.sort(key=lambda r: r["time"])
    ddrv_probe.report(method, pk, dk, rows, a.rsen, note=(
        "Ip vs Mout:1 differ by the displacement current of the internal nodes while the "
        "neighbour switches; the DC sweeps are the agreement test for the observation method"))

    for r in rows:
        r["iout"] = ddrv_probe.current(r, method, pk, a.rsen, "vsw" + suf,
                                       "data_out" + suf)

    t0, t1 = rows[0]["time"], rows[-1]["time"]
    t_start = t0 + a.skip_frac * (t1 - t0)
    obs = [r for r in rows if r["time"] >= t_start]
    if len(obs) < 3:
        print("TWO_CHANNEL_INDEPENDENCE: FAIL (too few samples after the skip window)")
        return 2

    cur = [r["iout"] for r in obs]

    # ---- the baseline the charge error is measured against ----------------------------
    base, base_src = median(cur), "median of the observed window"
    if a.ref:
        rnames, rrows = parse(a.ref)
        rmethod, rpk, _rdk = ddrv_probe.method_for(rnames, suf,
                                                   allow_legacy=not a.require_probe)
        if rmethod is None or not rrows:
            print("TWO_CHANNEL_INDEPENDENCE: FAIL (baseline deck %s unreadable)" % a.ref)
            return 2
        rc = [ddrv_probe.current(r, rmethod, rpk, a.rsen, "vsw" + suf, "data_out" + suf)
              for r in rrows if r["time"] >= rrows[0]["time"]
              + a.skip_frac * (rrows[-1]["time"] - rrows[0]["time"])]
        if rc:
            base, base_src = median(rc), "median of the static neighbour-held run %s" % \
                os.path.basename(a.ref)
        # a baseline is only a baseline at the same operating point: this comparison once
        # silently compared a channel held at 1.2 V against a reference deck whose output
        # sat at 0 V, which produced a 100 % "crosstalk" number out of a wiring mistake
        vdyn = mean([r["vsw" + suf] for r in obs])
        vref = mean([r["vsw" + suf] for r in rrows if "vsw" + suf in r])
        if abs(vdyn - vref) > 1e-3:
            print("TWO_CHANNEL_INDEPENDENCE: FAIL (baseline deck holds V(vsw%s)=%.4f V but "
                  "the run under test holds %.4f V: the two are not the same operating "
                  "point)" % (suf, vref, vdyn))
            return 2

    if a.baseline_ua is not None:
        base, base_src = a.baseline_ua * 1e-6, "pinned by --baseline-ua"

    m = metrics(obs, base, a.target, a.band_frac)
    t_span = m["t_span"]
    steady, dev_max = m["mean"], m["dev_max"]
    dev_target, frac = m["err_vs_target"], m["err_vs_target"] / a.target
    q_err, charge_pct, glitch, worst_t = (m["q_error"], m["charge_pct"], m["glitch_s"],
                                          m["worst_t"])

    # ---- is the victim's own sequence step-locked? --------------------------------------
    # A real inter-channel disturbance has a physical time constant and does not care how
    # the solver prints; trapezoidal ringing alternates at every sample. Reporting peak and
    # charge without this number is what let a numerical artifact look like crosstalk.
    ring_flip, ring_p2p, ring_n = ringing_metrics(cur)
    ring_yes = "NO"
    if ring_flip is not None:
        ring_yes = ("YES" if (ring_p2p >= a.ring_floor * abs(a.target)
                              and ring_flip >= 0.70) else "NO")
    shared_lo = shared_hi = gate_lo = gate_hi = None
    if "vbias" in obs[0]:
        vs = [r["vbias"] for r in obs]
        shared_lo, shared_hi = min(vs), max(vs)
    gsig = "vbias_ch" + suf
    if gsig in obs[0]:
        gs = [r[gsig] for r in obs]
        gate_lo, gate_hi = min(gs), max(gs)

    neigh = a.neigh_sig
    if neigh is None:
        # the neighbour is the OTHER channel: the victim on channel 1 is disturbed by
        # channel 0's enable (`data_en`), and the victim on channel 0 by `data_en1`.
        # An earlier version had this inverted, which silently turned every "no edge found"
        # report into a lost correlation between the disturbance and its cause.
        neigh = "data_en" if suf == "1" else "data_en1"
    up, down = edges(obs, neigh) if (neigh and neigh in rows[0]) else ([], [])
    near = None
    for e in up + down:
        if near is None or abs(e - worst_t) < abs(near - worst_t):
            near = e

    print("== %s  channel %s samples=%d (after skipping %.0f%% of the run)  window=%.4g s"
          % (a.label or os.path.basename(a.psf), suf or "0", len(obs),
             a.skip_frac * 100, t_span))
    if a.slew_desc:
        print("   SLEW              : %s" % a.slew_desc)
    print("   I_BASELINE        : %.6f uA   (%s)" % (base * 1e6, base_src))
    print("   I_%s mean         : %.6f uA" % (suf or "0", steady * 1e6))
    print("   PEAK_CROSSTALK_ERROR   : %.6f uA above baseline = %.3f %% of target"
          % (dev_max * 1e6, dev_max / abs(a.target) * 100.0))
    print("   PEAK_|I-target|        : %.6f uA = %.3f %% of target"
          % (dev_target * 1e6, frac * 100.0))
    print("   Q_error                : %+.4e C (integral of I_victim - I_baseline)" % q_err)
    print("   CHARGE_ERROR_PERCENT   : %.4f %%  (|Q_error| / (15uA x %.4g s))"
          % (charge_pct, t_span))
    print("   GLITCH_DURATION >+/- %.0f%% : %.4e s (%.2f %% of the observed window)"
          % (a.band_frac * 100, glitch, glitch / t_span * 100.0))
    print("   VICTIM_HOLD_WITHIN_5PCT : %.2f %% of the observed window sits inside +/-5 %% of "
          "baseline\n                             (the documented POC regulation criterion "
          "wants a channel to hold, not just avoid a peak)"
          % (100.0 * (1.0 - m["outside5_s"] / t_span)))
    if shared_lo is not None:
        print("   VBIAS_SHARED      : %.6f .. %.6f V   (spread %.6f V)"
              % (shared_lo, shared_hi, shared_hi - shared_lo))
    if gate_lo is not None:
        print("   %-17s : %.6f .. %.6f V   (spread %.6f V)"
              % (gsig, gate_lo, gate_hi, gate_hi - gate_lo))
    if ring_flip is None:
        print("   RINGING           : not measurable (%d distinct-sample differences)"
              % ring_n)
    else:
        print("   RINGING           : ADJACENT_POINT_ALTERNATION: %s   (alternation %.6f uA "
              "p2p, sign-flip ratio %.3f over %d samples; YES needs p2p >= %.4f uA and "
              "flips >= 0.70)"
              % (ring_yes, ring_p2p * 1e6, ring_flip, ring_n,
                 a.ring_floor * a.target * 1e6))
    if near is not None:
        print("   worst sample at t=%.4e s, nearest neighbour edge at t=%.4e s "
              "(delta %.3e s)" % (worst_t, near, abs(worst_t - near)))
    else:
        print("   no edge found on `%s`: the neighbour is held, so this row is the static "
              "level of the victim, not a switching disturbance" % neigh)

    if a.csv:
        exists = os.path.isfile(a.csv)
        dd = os.path.dirname(os.path.abspath(a.csv))
        if dd and not os.path.isdir(dd):
            os.makedirs(dd)
        csv_hdr = (u"label,channel,samples,observed_window_s,i_baseline_uA,mean_uA,"
                   u"peak_crosstalk_uA,peak_crosstalk_pct_of_target,"
                   u"peak_err_vs_target_pct,q_error_C,charge_error_pct,"
                   u"glitch_dur_s_above_1pct,iout_method,slew,vbias_shared_min_v,"
                   u"vbias_shared_max_v,gate_min_v,gate_max_v,ring_alternation_p2p_uA,"
                   u"ring_flip_ratio,adjacent_point_alternation\n")
        csv_fmt = (u"%s,%s,%d,%.6g,%.6f,%.6f,%.6f,%.4f,%.4f,%.6e,%.4f,%.6e,%s,%s,%s,%s,"
                   u"%s,%s,%s,%s,%s\n")
        csv_vals = (
            csv_field(a.label), suf or "0", len(obs), t_span, base * 1e6, steady * 1e6,
            dev_max * 1e6, dev_max / abs(a.target) * 100.0, frac * 100.0,
            q_err, charge_pct, glitch, method, csv_field(a.slew_desc),
            "n/a" if shared_lo is None else "%.6f" % shared_lo,
            "n/a" if shared_hi is None else "%.6f" % shared_hi,
            "n/a" if gate_lo is None else "%.6f" % gate_lo,
            "n/a" if gate_hi is None else "%.6f" % gate_hi,
            "n/a" if ring_p2p is None else "%.6f" % (ring_p2p * 1e6),
            "n/a" if ring_flip is None else "%.3f" % ring_flip, ring_yes)
        n_col = csv_hdr.rstrip(u"\n").count(u",") + 1
        n_slot = len(re.findall(u"%[-+ #0]*[0-9.]*[a-zA-Z]", csv_fmt))
        if not (n_col == n_slot == len(csv_vals)):
            print("TWO_CHANNEL_INDEPENDENCE: FAIL (csv field mismatch: header=%d format=%d "
                  "args=%d)" % (n_col, n_slot, len(csv_vals)))
            return 2
        blob = (u"" if exists else csv_hdr) + (csv_fmt % csv_vals)
        with open(a.csv, "ab") as fh:
            fh.write(blob.encode("utf-8") if not isinstance(blob, bytes) else blob)

    ok_peak = frac <= a.limit
    ok_charge = charge_pct <= a.limit * 100.0
    if ok_peak and ok_charge:
        print("TWO_CHANNEL_INDEPENDENCE: PASS (peak %.3f %% <= %.1f %%, charge %.3f %% "
              "<= %.1f %% POC criteria)"
              % (frac * 100.0, a.limit * 100.0, charge_pct, a.limit * 100.0))
        return 0
    print("TWO_CHANNEL_INDEPENDENCE: FAIL (peak %.3f %%, charge %.3f %% vs %.1f %% POC "
          "criterion)" % (frac * 100.0, charge_pct, a.limit * 100.0))
    return 1


if __name__ == "__main__":
    sys.exit(main())
