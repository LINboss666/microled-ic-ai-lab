#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_characterize.py -- turn one Spectre PSF-ASCII DC sweep into the numbers this
round is actually about: IOUT(VOUT), the error against the 15 uA course requirement, and
the output compliance voltage at +/-1/2/5%.

Run on the guest (Python 2.6) or on Windows (Python 3); no third-party modules.

    python scripts/ddrv_characterize.py <psfascii file> [--rsen 1e4] [--target 15e-6]
                                        [--csv out.csv] [--label A_series_n18_l5e-7_w2e-6]

The current is reconstructed from the sense resistor: IOUT = (V(vsw) - V(data_out)) / RSEN.
That is deliberate -- this Spectre build rejects `save *:current` with a warning, and a
result file built on ignored warnings is not evidence.

±1/2/5% are POC characterisation criteria chosen to compare topologies against each other.
They are NOT course requirements: the course gives only I_PIXEL_ON = 15 uA (instantaneous,
while the pixel is selected and ON).
"""

from __future__ import print_function

import argparse
import io
import os
import sys


def parse_records(path):
    """PSF-ASCII here interleaves the sweep variable inside each VALUE record:
        "dc" 0.02
        "vdd" 1.8
        ...
    Returns a list of dicts, one per sweep point, plus the list of trace names seen."""
    rows, cur, names = [], {}, set()
    invalue = False
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
            if rest.startswith("PROP("):          # TRACE header entry, not data
                names.add(key)
                continue
            try:
                val = float(rest.split()[0])
            except (ValueError, IndexError):
                continue
            names.add(key)
            if key == "dc":
                if cur:
                    rows.append(cur)
                cur = {"dc": val}
            else:
                cur[key] = val
    if cur:
        rows.append(cur)
    return rows, sorted(names)


def compliance(rows, col_v, col_i, target, tol_frac, lo=0.0):
    """Lowest VOUT from which EVERY larger point stays inside +/-tol. Reporting the
    worst-case-over-the-rest definition (not 'the first point that happens to be close')
    is what makes this a compliance voltage rather than a lucky sample."""
    best = None
    pts = [r for r in rows if r[col_v] >= lo - 1e-12]
    pts.sort(key=lambda r: r[col_v])
    for i, r in enumerate(pts):
        ok = True
        for q in pts[i:]:
            if abs(q[col_i] - target) > tol_frac * abs(target):
                ok = False
                break
        if ok:
            best = r[col_v]
            break
    return best


def rout_ohms(rows, target, frac_start=0.6):
    """Small-signal output resistance over the upper part of the curve (least-squares
    slope of I versus V, then dV/dI)."""
    pts = [r for r in rows if r["vout"] >= frac_start * max(x["vout"] for x in rows)]
    pts.sort(key=lambda r: r["vout"])
    n = len(pts)
    if n < 3:
        return None
    sx = sum(p["vout"] for p in pts) / n
    sy = sum(p["iout"] for p in pts) / n
    sxy = sum((p["vout"] - sx) * (p["iout"] - sy) for p in pts)
    sxx = sum((p["vout"] - sx) ** 2 for p in pts)
    if sxx == 0 or sxy == 0:
        return None
    return sxx / sxy


def monotonic_max_jump(rows, target, frac_start=0.5):
    pts = sorted([r for r in rows if r["vout"] >= frac_start * max(x["vout"] for x in rows)],
                 key=lambda r: r["vout"])
    worst = 0.0
    for a, b in zip(pts, pts[1:]):
        worst = max(worst, abs(b["iout"] - a["iout"]))
    return worst / abs(target) if target else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("psf")
    ap.add_argument("--rsen", type=float, default=1e4)
    ap.add_argument("--target", type=float, default=15e-6)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--nominal", type=float, default=None,
                    help="also report IOUT at the sample closest to this V(DATA_OUT)")
    ap.add_argument("--net-suffix", default="",
                    help="'1' to characterise channel 1 of the two-channel deck; the "
                         "accepted channel-0 net names stay the default")
    a = ap.parse_args()

    vsn, onn = "vsw" + a.net_suffix, "data_out" + a.net_suffix
    if not os.path.isfile(a.psf):
        print("DATA_DRIVER_DC: FAIL  (no psfascii data file at %s)" % a.psf)
        return 1
    raw, names = parse_records(a.psf)
    need = (vsn, onn)
    for k in need:
        if not raw or k not in raw[0]:
            print("DATA_DRIVER_DC: FAIL  (traces %s missing; found %s)" % (k, names))
            return 1
    rows = []
    for r in raw:
        rec = dict(r)
        rec["vout"] = r[onn]                    # compliance is at the device drain
        rec["vsw"] = r[vsn]
        rec["iout"] = (r[vsn] - r[onn]) / a.rsen
        rec["err_pct"] = (rec["iout"] - a.target) / a.target * 100.0
        rows.append(rec)
    rows.sort(key=lambda r: r["vsw"])

    if a.csv:
        d = os.path.dirname(os.path.abspath(a.csv))
        if not os.path.isdir(d):
            os.makedirs(d)
        # append: one sweep run produces one labelled block per geometry, and the whole
        # file is the deliverable. The driver starts a grid with DDRV_CSV_RESET=1.
        exists = os.path.isfile(a.csv)
        with io.open(a.csv, "a" if exists else "w", encoding="utf-8", newline="") as fh:
            if not exists:
                fh.write(u"candidate,vsw_V,vout_device_V,iout_uA,err_pct,vbias_V\n")
            for r in rows:
                fh.write(u"%s,%.6f,%.6f,%.6f,%.4f,%.6f\n"
                         % (a.label, r["vsw"], r["vout"], r["iout"] * 1e6,
                            r["err_pct"], r.get("vbias", float("nan"))))

    vmax_pt = max(rows, key=lambda r: r["vout"])
    c5 = compliance(rows, "vout", "iout", a.target, 0.05)
    c2 = compliance(rows, "vout", "iout", a.target, 0.02)
    c1 = compliance(rows, "vout", "iout", a.target, 0.01)
    ro = rout_ohms(rows, a.target)
    jump = monotonic_max_jump(rows, a.target)

    print("== %s  points=%d  VOUT_max=%.4f V  IOUT@max=%.6f uA (err %.3f %%)"
          % (a.label or os.path.basename(a.psf), len(rows), vmax_pt["vout"],
             vmax_pt["iout"] * 1e6, vmax_pt["err_pct"]))
    for tag, v in (("+/-1%", c1), ("+/-2%", c2), ("+/-5%", c5)):
        print("   COMPLIANCE %-6s : %s" % (tag, "NOT_FOUND" if v is None else "%.4f V" % v))
    print("   ROUT(upper 40%%)   : %s" % ("n/a" if ro is None else "%.3e ohm" % ro))
    print("   MAX_ADJACENT_JUMP : %s (fraction of target, VOUT>50%% of sweep)"
          % ("n/a" if jump is None else "%.5f" % jump))
    if a.nominal is not None:
        pt = min(rows, key=lambda r: abs(r["vout"] - a.nominal))
        print("   NOMINAL VOUT=%.4f V: IOUT=%.6f uA  err=%.3f %%"
              % (pt["vout"], pt["iout"] * 1e6, pt["err_pct"]))
    lo_i = min(r["iout"] for r in rows)
    hi_i = max(r["iout"] for r in rows)
    # one point is never the finding. The span over the WHOLE sweep includes the turn-on
    # region, so it is dominated by "the sink is not on yet"; the regulation number is the
    # span above the +/-5% knee, which is what a driver channel is asked to hold.
    reg = [r for r in rows if c5 is not None and r["vout"] >= c5]
    if reg:
        rlo = min(r["iout"] for r in reg)
        rhi = max(r["iout"] for r in reg)
        print("   IOUT_SPAN above the +/-5%% knee (%.4f V, %d pts): %.6f .. %.6f uA "
              "= %.2f %% of target"
              % (c5, len(reg), rlo * 1e6, rhi * 1e6, (rhi - rlo) / abs(a.target) * 100.0))
    print("   IOUT_SPAN whole sweep: %.6f .. %.6f uA = %.2f %% of target"
          % (lo_i * 1e6, hi_i * 1e6, (hi_i - lo_i) / abs(a.target) * 100.0))
    print("DATA_DRIVER_DC: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
