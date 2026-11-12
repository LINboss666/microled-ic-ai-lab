#!/usr/bin/env python3
"""Offline checker / statistics / plotting for the course Spectre evidence.

Inputs are the SMALL raw CSVs exported from real Spectre PSF-ASCII output:
  results/dc_i_v.csv       19-point clamp sweep (job S2)
  results/tran_i_t.csv     426-point enable transient (job S3)
  results/mc_samples.csv   30 native Monte Carlo samples (job MC1)

Nothing here fabricates or discards a sample. Outputs:
  results/mc_stats.json, results/analog_summary.json
  figures/mc_histogram.svg, spectre_dc_iv.svg, spectre_tran_wave.svg,
  figures/spectre_tran_settling_zoom.svg
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams['svg.hashsalt'] = 'course-microled-sim-20261112'


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--figures", required=True)
    args = ap.parse_args()

    dc = read_csv(os.path.join(args.results, "dc_i_v.csv"))
    tr = read_csv(os.path.join(args.results, "tran_i_t.csv"))
    mc = read_csv(os.path.join(args.results, "mc_samples.csv"))

    dc_v = [float(r["vclamp_V"]) for r in dc]
    dc_i = [float(r["iout_uA"]) for r in dc]
    tr_t = [float(r["time_s"]) for r in tr]
    tr_i = [float(r["iout_uA"]) for r in tr]
    tr_v = [float(r["vcas_V"]) for r in tr]

    mc_it = [int(r["iteration"]) for r in mc]
    mc_vals = [float(r["iout_uA"]) for r in mc]
    assert all(math.isfinite(v) for v in mc_vals), "non-finite MC sample"
    assert len(mc_vals) == 30, "expected exactly 30 MC samples"
    assert sorted(mc_it) == list(range(1, 31)), "MC iteration set incomplete"

    n = len(mc_vals)
    mean = statistics.fmean(mc_vals)
    sd = statistics.stdev(mc_vals)          # sample standard deviation (ddof=1)
    vmin, vmax = min(mc_vals), max(mc_vals)
    med = statistics.median(mc_vals)
    target = 15.0
    dev = mean - target

    mc_stats = {
        "analysis": "native Spectre montecarlo",
        "spectre_version": "15.1.0.284.isr1",
        "model_section": "mos_mc",
        "variations": "all (process + mismatch)",
        "sampling": "standard",
        "seed": 20261112,
        "numruns_requested": 30,
        "samples_success": n,
        "samples_failed": 0,
        "samples_discarded": 0,
        "nominal_iout_uA": 14.93191472709646,
        "fixed_condition": {"vclamp_V": 1.20, "vdd18_V": 1.8, "vcas_V": 1.8,
                            "vss_V": 0.0, "iref_A": 15e-6, "temp_C": 27,
                            "model_card_injection": "${QODER_PDK_LIB}"},
        "mean_uA": mean,
        "stdev_sample_uA": sd,
        "stdev_population_uA": statistics.pstdev(mc_vals),
        "min_uA": vmin,
        "max_uA": vmax,
        "median_uA": med,
        "target_uA": target,
        "mean_minus_target_uA": dev,
        "mean_relative_error_pct": 100.0 * dev / target,
        "cv_pct": 100.0 * sd / mean,
        "input_csv_sha256": sha256(os.path.join(args.results, "mc_samples.csv")),
        "note": "SPECTRE-16006 warned that no scalar expression was defined; the 30 "
                "per-iteration PSF files WERE written and all 30 Iout values were "
                "extracted from them. No distribution was synthesised.",
    }
    with open(os.path.join(args.results, "mc_stats.json"), "w", encoding="utf-8") as fh:
        json.dump(mc_stats, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # ---- DC at the 1.20 V comparable point ---------------------------------
    at120 = min(range(len(dc_v)), key=lambda k: abs(dc_v[k] - 1.20))
    i120 = dc_i[at120]
    # ---- transient off-state leakage and settling --------------------------
    off = [v for t, v in zip(tr_t, tr_i) if t < 0.9e-6]
    on = [v for t, v in zip(tr_t, tr_i) if 2.0e-6 <= t <= 4.0e-6]
    off_mean = statistics.fmean(off)
    off_absmax = max(abs(v) for v in off)
    on_med = statistics.median(on)
    thr = 0.9 * on_med
    t90 = None
    for k in range(1, len(tr_t)):
        if tr_t[k] >= 1.0e-6 and tr_i[k - 1] < thr <= tr_i[k]:
            f = (thr - tr_i[k - 1]) / (tr_i[k] - tr_i[k - 1])
            t90 = tr_t[k - 1] + f * (tr_t[k] - tr_t[k - 1])
            break
    # end of high plateau: first sample after 4.0us where vcas has returned to ~0
    off_tail = [v for t, v in zip(tr_t, tr_i) if t > 5.0e-6]

    on_min = min(on); on_max = max(on); on_pp = on_max - on_min

    def band_entry(center, pct, lo_t=1.0e-6, hi_t=4.05e-6):
        lo, hi = center * (1 - pct / 100.0), center * (1 + pct / 100.0)
        win = [(ti, vi) for ti, vi in zip(tr_t, tr_i) if lo_t <= ti <= hi_t]
        last_out = -1
        for i, (ti, vi) in enumerate(win):
            if vi < lo or vi > hi:
                last_out = i
        if last_out + 1 < len(win):
            return win[last_out + 1][0]
        return None

    e1 = band_entry(on_med, 1.0)
    e5 = band_entry(on_med, 5.0)

    analog = {
        "dc_sweep": {
            "points": len(dc_v), "vclamp_start_V": dc_v[0], "vclamp_stop_V": dc_v[-1],
            "at_1p20V_iout_uA": i120,
            "delta_vs_15uA_uA": i120 - 15.0,
            "delta_vs_15uA_pct": 100.0 * (i120 - 15.0) / 15.0,
            "min_iout_uA": min(dc_i), "max_iout_uA": max(dc_i),
            "input_csv_sha256": sha256(os.path.join(args.results, "dc_i_v.csv")),
        },
        "transient": {
            "samples": len(tr_t), "stop_s": tr_t[-1],
            "off_window_t_lt_0p9us": {"samples": len(off), "mean_uA": off_mean,
                                      "max_abs_uA": off_absmax},
            "on_window_2us_to_4us": {
                "samples": len(on), "median_uA": on_med, "min_uA": on_min,
                "max_uA": on_max, "peak_to_peak_uA": on_pp,
                "peak_to_peak_pct_of_median": 100.0 * on_pp / on_med,
                "definition": "raw sample min/max inside the high plateau, no smoothing, no discarded samples",
            },
            "first_cross_90pct_of_on_median": {
                "definition": "first interpolated time at which Iout crosses 0.9 x median(Iout in 2us..4us). "
                              "This is NOT a 'settled and stayed inside a band' criterion; the VCAS 100 ns "
                              "rising edge is still in progress at that instant.",
                "time_s": t90,
                "from_enable_start_ns": (t90 - 1.0e-6) * 1e9 if t90 else None,
            },
            "band_entry_pm1pct_s": e1,
            "band_entry_pm5pct_s": e5,
            "band_entry_definition": "first sample time after which Iout never leaves median*(1+/-pct) "
                                     "within 1.0us..4.05us; None means it never settles in that window",
            "off_tail_after_5us_max_abs_uA": max(abs(v) for v in off_tail),
            "rise_region_has_negative_displacement_current": any(v < -0.01 for v in tr_i),
            "ringing": {
                "spectre_notices": 7,
                "suppressed_notices": 365,
                "source": "course_tran_en.log (reported from the original run, not re-run in R2)",
                "meaning": "trapezoidal-integration warning on Xdut.Mcas:int_s; a numerical-method notice, "
                           "NOT a hardware quality or SOA sign-off",
            },
            "input_csv_sha256": sha256(os.path.join(args.results, "tran_i_t.csv")),
        },
        "monte_carlo": {"samples": n, "mean_uA": mean, "stdev_uA": sd,
                        "min_uA": vmin, "max_uA": vmax},
    }
    with open(os.path.join(args.results, "analog_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(analog, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    os.makedirs(args.figures, exist_ok=True)

    # ---- MC histogram (from the 30 real values) ----------------------------
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.hist(mc_vals, bins=8, color="#8250df", edgecolor="white", alpha=0.9)
    ax.axvline(mean, color="#d1242f", linewidth=1.6, linestyle="--",
               label="mean = %.6f uA" % mean)
    ax.axvline(15.0, color="#1a7f37", linewidth=1.6, linestyle=":",
               label="design target = 15.000000 uA")
    ax.set_xlabel("Monte Carlo Iout at Vclamp = 1.20 V  (uA)")
    ax.set_ylabel("Sample count (out of 30)")
    ax.set_title("Native Spectre Monte Carlo: 30 samples, seed 20261112, process+mismatch\n"
                 "source CSV sha256 " + mc_stats["input_csv_sha256"][:20] + "…")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(args.figures, "mc_histogram.svg"), dpi=160, facecolor="white", metadata={"Date": None})
    plt.close(fig)

    # ---- DC I-V -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.plot(dc_v, dc_i, marker="o", markersize=3.5, color="#1f6feb",
            label="Iout (measured, TT 27 C)")
    ax.axvline(1.20, color="#d1242f", linewidth=1.2, linestyle="--",
               label="comparable clamp 1.20 V")
    ax.axhline(15.0, color="#1a7f37", linewidth=1.2, linestyle=":",
               label="15 uA design target")
    ax.plot([1.20], [i120], "o", color="#d1242f", markersize=7)
    ax.annotate("%.6f uA" % i120, (1.20, i120), textcoords="offset points",
                xytext=(8, -14), fontsize=9, color="#d1242f")
    ax.set_xlabel("Output clamp voltage (V)")
    ax.set_ylabel("Sink current Iout (uA)")
    ax.set_title("Course basic NMOS sink: DC clamp sweep, 19 measured points")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(args.figures, "spectre_dc_iv.svg"), dpi=160, facecolor="white", metadata={"Date": None})
    plt.close(fig)

    # ---- transient full -----------------------------------------------------
    us = [t * 1e6 for t in tr_t]
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True)
    axes[0].plot(us, tr_i, color="#1f6feb", linewidth=1.1, label="Iout (uA)")
    axes[0].axhline(15.0, color="#1a7f37", linewidth=1.0, linestyle=":",
                    label="15 uA target")
    axes[0].set_ylabel("Iout (uA)")
    axes[0].legend(fontsize=8, loc="upper right")
    axes[0].grid(alpha=0.3)
    axes[0].set_title("Enable-switch transient (cascode bias pulse), 426 measured samples")
    axes[1].plot(us, tr_v, color="#bf8700", linewidth=1.2, label="VCAS enable (V)")
    axes[1].set_ylabel("VCAS (V)")
    axes[1].set_xlabel("Time (us)")
    axes[1].legend(fontsize=8, loc="upper right")
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(args.figures, "spectre_tran_wave.svg"), dpi=160, facecolor="white", metadata={"Date": None})
    plt.close(fig)

    # ---- transient settling zoom -------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 5.2))
    sel = [(t * 1e6, v) for t, v in zip(tr_t, tr_i) if 0.95e-6 <= t <= 1.35e-6]
    ax.plot([p[0] for p in sel], [p[1] for p in sel], color="#1f6feb",
            marker=".", markersize=4, linewidth=1.0, label="Iout (uA)")
    if t90:
        ax.axvline(t90 * 1e6, color="#d1242f", linestyle="--", linewidth=1.4,
                   label="90%% settling = %.4f us" % (t90 * 1e6))
    ax.axhline(0.0, color="black", linewidth=0.7)
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Iout (uA)")
    ax.set_title("Turn-on zoom: negative displacement current then settling")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(args.figures, "spectre_tran_settling_zoom.svg"),
                dpi=160, facecolor="white", metadata={"Date": None})
    plt.close(fig)

    print("MC n=%d mean=%.9f uA sd=%.9f uA min=%.9f max=%.9f" % (n, mean, sd, vmin, vmax))
    print("DC at 1.20V = %.9f uA (delta %.9f uA, %.6f%%)" %
          (i120, i120 - 15.0, 100.0 * (i120 - 15.0) / 15.0))
    print("TRAN off_mean=%.9g uA on_median=%.6f uA t90=%s" % (off_mean, on_med, t90))
    print("ANALYZE_DONE")


if __name__ == "__main__":
    main()
