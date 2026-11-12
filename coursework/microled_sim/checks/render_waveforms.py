#!/usr/bin/env python3
"""Render timing diagrams from a REAL ModelSim VCD.

Every transition plotted here is parsed from the VCD produced by
tb/course_selfcheck_tb.sv.txt in a real `vsim -c` run. Nothing is synthesised,
hand-drawn or edited to look like a pass. These are VCD-derived timing
figures, NOT ModelSim GUI screenshots; the source VCD SHA-256 is recorded in
the manifest so a reviewer can re-render from the original file.

Usage:
  python checks/render_waveforms.py --vcd <native/run02/course_sim.vcd> \
      --figures <coursework/microled_sim/figures> \
      --manifest <coursework/microled_sim/results/waveform_render_manifest.csv>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


VAR_RE = re.compile(r"^\$var\s+(\S+)\s+(\d+)\s+(\S+)\s+(\S+)(?:\s+(\[?\d+\]?))?\s+\$end")


def parse_vcd(path):
    """Return (signals, bus_bits, timescale_ps).

    signals: {signal_name: [(t_ps, value_str), ...]} for scalar signals
    bus_bits: {bus_name: {bit_index: [(t_ps, value_str), ...]}}
    """
    signals = defaultdict(list)
    bus_bits = defaultdict(dict)
    id_to_scalar = {}
    id_to_busbit = {}
    timescale_ps = 1.0
    t = 0
    pending_timescale = False

    with open(path, "r", encoding="latin-1") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if pending_timescale:
                m = re.match(r"(\d+(?:\.\d+)?)\s*(fs|ps|ns|us|ms|s)", line)
                if m:
                    unit = {"fs": 1e-3, "ps": 1.0, "ns": 1e3,
                            "us": 1e6, "ms": 1e9, "s": 1e12}[m.group(2)]
                    timescale_ps = float(m.group(1)) * unit
                pending_timescale = False
                continue
            if line == "$timescale":
                pending_timescale = True
                continue
            if line.startswith("$var"):
                m = VAR_RE.match(raw.strip())
                if not m:
                    continue
                _typ, width, sid, name, rng = m.groups()
                if rng and rng.startswith("["):
                    bit = int(rng.strip("[]"))
                    id_to_busbit[sid] = (name, bit)
                    bus_bits[name][bit] = []
                else:
                    id_to_scalar[sid] = name
                    signals[name]  # ensure key exists
                continue
            if line.startswith("#"):
                t = int(line[1:])
                continue
            if line.startswith("$"):
                continue
            if line[0] in "01xXzZ":
                sid = line[1:].strip()
                if sid in id_to_scalar:
                    signals[id_to_scalar[sid]].append((t, line[0]))
                elif sid in id_to_busbit:
                    name, bit = id_to_busbit[sid]
                    bus_bits[name][bit].append((t, line[0]))
                continue
            if line[0] in "bBrR":
                parts = line.split()
                if len(parts) >= 2 and parts[-1] in id_to_scalar:
                    signals[id_to_scalar[parts[-1]]].append((t, parts[0][1:]))
                elif len(parts) >= 2 and parts[-1] in id_to_busbit:
                    name, bit = id_to_busbit[parts[-1]]
                    bus_bits[name][bit].append((t, parts[0][1:]))
    return signals, bus_bits, timescale_ps


def bus_series(bits, scale_ns):
    """Merge individual bit timelines into an integer bus timeline."""
    all_t = sorted({t for series in bits.values() for t, _ in series})
    if not all_t:
        return [], []
    state = {b: 0 for b in bits}
    idx = {b: 0 for b in bits}
    out_t, out_v = [], []
    for t in all_t:
        for b, series in bits.items():
            while idx[b] < len(series) and series[idx[b]][0] <= t:
                raw = series[idx[b]][1]
                state[b] = 1 if raw in "1hH" else 0
                idx[b] += 1
        val = 0
        for b, v in state.items():
            if v:
                val |= (1 << b)
        out_t.append(t * scale_ns)
        out_v.append(val)
    return out_t, out_v


def scalar_series(series, scale_ns):
    t = [p[0] * scale_ns for p in series]
    v = [1 if p[1] in "1hH" else 0 for p in series]
    return t, v


def clip(t, v, t0, t1):
    """Return a step-plot-friendly series including the last value before t0."""
    if not t:
        return [], []
    out_t, out_v = [], []
    prev_v = v[0]
    for i, ti in enumerate(t):
        if ti < t0:
            prev_v = v[i]
            continue
        if not out_t:
            out_t.append(t0)
            out_v.append(prev_v)
        if ti <= t1:
            out_t.append(ti)
            out_v.append(v[i])
        else:
            break
    if not out_t:
        out_t, out_v = [t0, t1], [prev_v, prev_v]
    elif out_t[-1] < t1:
        out_t.append(t1)
        out_v.append(out_v[-1])
    return out_t, out_v


def digital(ax, t, v, label, t0, t1, color="#1f6feb"):
    x, y = clip(t, v, t0, t1)
    ax.step(x, y, where="post", linewidth=1.3, color=color)
    ax.set_ylim(-0.25, 1.45)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["0", "1"], fontsize=8)
    ax.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=9, labelpad=42)
    ax.grid(axis="x", alpha=0.35, linewidth=0.6)
    ax.tick_params(axis="y", length=0)


def bus(ax, t, v, label, t0, t1, color="#8250df"):
    x, y = clip(t, v, t0, t1)
    ax.step(x, y, where="post", linewidth=1.3, color=color)
    ax.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=9, labelpad=42)
    ax.grid(axis="both", alpha=0.35, linewidth=0.6)
    ax.tick_params(axis="y", labelsize=8)
    # do not force a symmetric range; keep the measured integer values visible
    lo, hi = min(y), max(y)
    if hi - lo < 1:
        ax.set_ylim(lo - 0.6, hi + 0.6)
    else:
        pad = (hi - lo) * 0.12
        ax.set_ylim(lo - pad, hi + pad)


def build_figure(signals, bus_bits, scale_ns, spec, path, sha):
    t0, t1 = spec["window"]
    rows = spec["rows"]
    fig, axes = plt.subplots(len(rows), 1, figsize=(15, max(2.2, 1.15 * len(rows))),
                             sharex=True, squeeze=False)
    axes = axes[:, 0]
    for ax, row in zip(axes, rows):
        name, kind = row[0], row[1]
        if kind == "bit":
            t, v = scalar_series(signals.get(name, []), scale_ns)
            digital(ax, t, v, name, t0, t1)
        else:
            t, v = bus_series(bus_bits.get(name, {}), scale_ns)
            bus(ax, t, v, name, t0, t1)
    axes[-1].set_xlabel("Time (ns)  |  source: real ModelSim VCD", fontsize=9)
    axes[-1].set_xlim(t0, t1)
    for mark, text in spec.get("marks", []):
        for ax in axes:
            ax.axvline(mark, color="#d1242f", linewidth=0.8, linestyle="--", alpha=0.65)
        axes[0].text(mark, 1.5, text, fontsize=8, color="#d1242f",
                     ha="center", va="bottom", rotation=0)
    fig.suptitle(spec["title"] + "\nVCD SHA-256 " + sha[:24] + "… (full hash in manifest)",
                 fontsize=10, y=0.995)
    fig.tight_layout(rect=[0.10, 0, 1, 0.96])
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


SPECS = [
    {
        "key": "wave_scan_latch",
        "title": "Scan / latch timing: 1023->0 column wrap, blanked LATCH, one-hot strobes",
        "window": (10290.0, 10700.0),
        "rows": [("col_addr", "bus"), ("col_wrap", "bit"), ("scan_even_sel", "bit"),
                 ("scan_odd_sel", "bit"), ("blank", "bit"), ("latch_stb", "bit"),
                 ("latch_count", "bus"), ("drive_gate", "bit")],
        "marks": [(10326.0, "col wrap 1023->0"), (10566.0, "LATCH in blank")],
    },
    {
        "key": "wave_pwm_full",
        "title": "PWM maximum code (63 -> 64 conducting ticks), full Hybrid window",
        "window": (10800.0, 18550.0),
        "rows": [("pwm_tick", "bit"), ("obs_tick", "bit"), ("data_en", "bit"),
                 ("win_state", "bus"), ("drive_gate", "bit")],
        "marks": [(10836.0, "window start"), (18396.0, "window end")],
    },
    {
        "key": "wave_pwm_boundary_zoom",
        "title": "PWM boundary zoom: last conducting ticks and the DONE boundary (65th tick)",
        "window": (18180.0, 18550.0),
        "rows": [("pwm_tick", "bit"), ("obs_tick", "bit"), ("data_en", "bit"),
                 ("win_state", "bus"), ("drive_gate", "bit")],
        "marks": [(18396.0, "65th tick -> S_DONE")],
    },
    {
        "key": "wave_blank_negative",
        "title": "Blank force-off and negative protocol cases (C07 / C12)",
        "window": (34250.0, 35250.0),
        "rows": [("blank", "bit"), ("data_en", "bit"), ("drive_gate", "bit"),
                 ("onehot_pop", "bus"), ("win_state", "bus"), ("proto_err", "bus")],
        "marks": [(35046.0, "blank asserted mid-window")],
    },
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcd", required=True)
    ap.add_argument("--figures", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()

    raw = open(args.vcd, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    print("VCD", args.vcd, "bytes", len(raw), "sha256", sha)

    signals, bus_bits, ts_ps = parse_vcd(args.vcd)
    scale_ns = ts_ps / 1000.0
    print("timescale_ps", ts_ps, "scalar_signals", len(signals), "buses", len(bus_bits))

    os.makedirs(args.figures, exist_ok=True)
    os.makedirs(os.path.dirname(args.manifest), exist_ok=True)

    with open(args.manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["figure", "window_start_ns", "window_end_ns", "signals",
                    "source_vcd_sha256", "source_vcd_bytes", "renderer"])
        for spec in SPECS:
            path = os.path.join(args.figures, spec["key"] + ".svg")
            build_figure(signals, bus_bits, scale_ns, spec, path, sha)
            w.writerow([spec["key"] + ".svg", spec["window"][0], spec["window"][1],
                        "|".join(r[0] for r in spec["rows"]), sha, len(raw),
                        "checks/render_waveforms.py"])
            print("wrote", path, os.path.getsize(path), "bytes")
    print("RENDER_DONE figures=%d" % len(SPECS))


if __name__ == "__main__":
    main()
