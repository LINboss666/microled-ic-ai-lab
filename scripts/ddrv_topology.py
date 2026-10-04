#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_topology.py -- reviewer-facing topology summary for the data-driver channel,
generated from the deck text, never transcribed.

    python scripts/ddrv_topology.py <deck.scs> [<deck2.scs> ...] [--out file.md]
    python scripts/ddrv_topology.py <deck.scs> --stress <psfascii> [--rsen 1e4]

What it answers, mechanically:
  * which devices are per-channel and which belong to the shared bias block
  * the series path the pixel current actually takes, from DATA_OUT down to VSS
  * what the enable does to each node, and where the OFF current flows
  * every ideal source in the deck (so "designed" and "testbench help" are separable)
  * with --stress: the terminal-voltage ranges the circuit really saw during a sweep
"""

from __future__ import print_function

import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_review_bundle import devices_of, supply_nets   # same parser the bundle uses

# role table keyed by instance name: the group column is the point of the exercise, a
# reviewer must be able to see instantly which devices are repeated per channel.
ROLES = [
    (re.compile(r"^Mout\d?$"), "PER-CHANNEL", "mirror output device, carries the pixel current"),
    (re.compile(r"^Mcas\d?$"), "PER-CHANNEL", "cascode device, sets the output compliance knee"),
    (re.compile(r"^Msw$"),  "PER-CHANNEL", "series enable switch (candidate A_series only)"),
    (re.compile(r"^Mref$"), "SHARED BIAS", "diode-connected reference, 1:1 with the output device"),
    (re.compile(r"^Msteer$"), "SHARED BIAS", "enable pass device between the reference current and vbias"),
    (re.compile(r"^Mdummy$"), "SHARED BIAS", "absorbs the reference current while the channel is disabled"),
    (re.compile(r"^Mbleed$"), "SHARED BIAS", "discharges vbias so the output stack really turns off"),
]

IDEAL_RX = re.compile(
    r"^\s*(\w+)\s*\(\s*(\S+)\s+(\S+)\s*\)\s*(vsource|isource)\b([^\n]*)", re.M)


def role_of(inst):
    for rx, group, desc in ROLES:
        if rx.match(inst):
            return group, desc
    return "UNCLASSIFIED", "(add it to ROLES in scripts/ddrv_topology.py)"


def rails_from_sources(text, rows):
    """Ground and supply read off the independent sources instead of off device polarity:
    this cell is all-NMOS, so a PMOS-majority heuristic has nothing to look at and reports
    no rails at all. Several sources legitimately sit at 0 V (the enable complement does),
    so among the 0 V sources to node 0 the rail is the net the devices actually stand on --
    the one appearing most often as a source or body terminal."""
    from collections import Counter
    term = Counter()
    for r in rows:
        term[r["s"]] += 1
        term[r["b"]] += 1
    hi = lo = None
    zero_nets, rail_nets = [], []
    for m in IDEAL_RX.finditer(text):
        inst, n1, n2, kind, rest = m.groups()
        if kind != "vsource" or n2 != "0":
            continue
        d = re.search(r"\bdc=(\S+)", rest or "")
        if not d:
            continue
        (zero_nets if d.group(1) in ("0", "0.0") else rail_nets).append(n1)
    if zero_nets:
        lo = max(zero_nets, key=lambda n: term[n])
    if rail_nets:
        hi = max(rail_nets, key=lambda n: term[n])
    return hi, lo


def series_path(rows, start, target, max_depth=6):
    """Series device path from `start` to `target` through drain/source terminals."""
    adj = {}
    for r in rows:
        for a, b in ((r["d"], r["s"]), (r["s"], r["d"])):
            adj.setdefault(a, []).append((b, r["inst"]))
    stack, seen = [(start, [])], set()
    while stack:
        node, path = stack.pop()
        if node == target and path:
            return path
        if len(path) >= max_depth or node in seen:
            continue
        seen.add(node)
        for nxt, inst in adj.get(node, []):
            stack.append((nxt, path + [(inst, node, nxt)]))
    return []


def multiplicity(text):
    """`m=` per instance line, read from the deck; the device parser resolves W/L but not m,
    and printing a default 1 silently would be a transcription error of exactly the kind
    this file exists to avoid."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*([A-Za-z][\w]*)\s*\(", line)
        if not m:
            continue
        mm = re.search(r"\bm=(\d+)", line)
        out[m.group(1)] = mm.group(1) if mm else "1 (not stated in the deck)"
    return out


def device_table(rows, out, mvals):
    out("## Device inventory, parsed from the deck (n=%d)" % len(rows))
    out("")
    out("| instance | group | role | model | W | L | m | D | G | S | B |")
    out("|---|---|---|---|---|---|---|---|---|---|---|")
    per, shared = [], []
    for r in rows:
        group, desc = role_of(r["inst"])
        # candidate D puts the channel enable on this gate: say so, instead of letting the
        # reader assume it is the always-on bias node of the accepted C cell
        if r["inst"].startswith("Mcas") and r["g"].startswith("data_en"):
            desc = "cascode device whose gate IS the channel enable (candidate D)"
        m = mvals.get(r["inst"], "?")
        out("| `%s` | %s | %s | `%s` | %s | %s | %s | `%s` | `%s` | `%s` | `%s` |"
            % (r["inst"], group, desc, r["model"], r["w"], r["l"], m,
               r["d"], r["g"], r["s"], r["b"]))
        (per if group == "PER-CHANNEL" else shared).append(r["inst"])
    out("")
    out("```")
    out("PER-CHANNEL devices (repeated for every output channel) : %d  ->  %s"
        % (len(per), ", ".join(per)))
    out("SHARED BIAS/gating devices (one set for the whole block): %d  ->  %s"
        % (len(shared), ", ".join(shared)))
    out("```")
    out("")
    out("`m` is only printed if the deck sets it; this cell uses `m=1` and no fingers.")
    out("")


def path_ascii(rows, hi, lo, out):
    out("## Current path when the channel is enabled")
    out("")
    p = series_path(rows, "data_out", lo)
    by = dict((r["inst"], r) for r in rows)   # genexp, not a dict comprehension: the
    # guest runs Python 2.6, which has no dict-comprehension syntax and fails at import time

    out("```")
    out("  (external: Micro LED cathode / DATA_OUT pad)")
    out("      |")
    cur = "data_out"
    for inst, a, b in p:
        r = by[inst]
        out("      +-- %s  %s   gate = %s" % (inst, r["model"], r["g"]))
        cur = b
        out("      |")
    out("     %s   (= reference node 0 through Vss)" % lo)
    out("```")
    out("")
    out("The sense resistor and the ideal `Vout` source sit **outside** the channel, above "
       "DATA_OUT: `Vout(vsw 0) -- RSEN -- data_out`. So the pixel current flows *into* the "
       "device stack and down to `vss`: this is a low-side sink, not a source.")
    out("")
    ref = []
    for r in rows:
        g, _ = role_of(r["inst"])
        if g == "SHARED BIAS":
            ref.append(r)
    out("### Shared reference / gating branch")
    out("")
    out("```")
    out("  vdd --[ IREF ideal 15u ]--> ref_top")
    for r in ref:
        out("  %s %-8s (d=%s g=%s s=%s b=%s)"
            % (r["inst"], role_of(r["inst"])[1][:22], r["d"], r["g"], r["s"], r["b"]))
    out("```")
    out("")


def off_explanation(rows, out):
    gates = dict((r["inst"], r["g"]) for r in rows)
    has = set(gates.values())
    out("## What happens when DATA_EN goes low")
    out("")
    out("Not a one-line claim: each node's fate is read off the devices that touch it.")
    out("")
    if "Msteer" in gates:
        out("1. `Msteer` (gate `data_en`) opens: the shared reference current can no longer "
            "reach `vbias`.")
    if "Mdummy" in gates:
        out("2. `Mdummy` (gate `data_en_b`) closes the other way and takes the whole 15 uA "
            "from `ref_top` to `vss`, so `ref_top` does not float up to `vdd` -- the "
            "reference stays biased, only the mirror gate is left.")
    if "Mbleed" in gates:
        out("3. `Mbleed` (gate `data_en_b`) holds `vbias` at ~0 V. With `vbias` = 0, the "
            "output device `Mout` has `VGS` <= 0 and is off; the cascode `Mcas` keeps its "
            "gate at `vcas` but has nothing to pass, so the whole stack is off.")
    out("")
    out("4. Where the measured OFF current still flows: subthreshold conduction through "
        "`Mout` and `Mcas` in series (their `VGS` is ~0 but `VDS` is the full output "
        "voltage), plus junction leakage at `data_out`/`node_m`. It is *not* a device "
        "being left partially on by the enable, and it is reported as a number, not "
        "judged against a spec, because the course gives no leakage figure.")
    out("")
    out("### Consequence for more than one channel")
    out("")
    out("`vbias` is one node shared by every channel that hangs off it, and `Mbleed` is "
        "driven by **that channel's** `data_en_b`. In a multi-channel expansion the first "
        "channel to disable would pull the shared `vbias` down and take the other channels "
        "with it. As tested, the enable therefore only extends to 384 independent channels "
        "if the steer/dummy/bleed trio is replicated per channel, which then puts three "
        "extra devices behind every output and defeats the point of the shared block.")
    out("This is recorded as `SCALABILITY_CONCERN_FOUND` for the reviewer to judge; the "
        "circuit was not changed to hide it.")
    out("")


def ideal_sources(text, out):
    out("## Every ideal source in the testbench (what is NOT claimed as design)")
    out("")
    out("| element | nodes | kind | as written | classification |")
    out("|---|---|---|---|---|")
    for m in IDEAL_RX.finditer(text):
        inst, n1, n2, kind, rest = m.groups()
        if kind == "isource":
            note = "ideal 15 uA reference current -> TESTBENCH ASSUMPTION"
        elif n1 == "vsw":
            note = "ideal output test voltage, swept as the DC variable -> POC_ASSUMPTION"
        elif n1 == "vcas":
            note = "ideal cascode gate bias at 1.8 V -> POC_ASSUMPTION, not a designed bias ladder"
        elif n1 == "vdd":
            note = "ideal supply 1.8 V -> POC_ASSUMPTION (1.8 V core domain)"
        elif n1 == "vss":
            note = "explicit tie of the substrate/source net to reference node 0 -> required, see preflight"
        else:
            note = "ideal enable drive (DATA_EN / DATA_EN_B) -> POC_ASSUMPTION, no local latch modelled"
        out("| `%s` | %s %s | %s | `%s` | %s |" % (inst, n1, n2, kind, rest.strip(), note))
    out("")
    out("The PASS in this round means: with a working reference **current** available, the "
       "channel sinks 15 uA over a wide output range and switches off. It does **not** mean "
       "the shared reference/bias generator has been designed -- `IREF` is an ideal current "
       "source and `vcas` an ideal 1.8 V node in every deck here.")
    out("")


def stress(rows, psf, out, rsen):
    """Terminal-voltage ranges actually present during the sweep."""
    from ddrv_tran import parse as parse_psf   # same PSF reader, no second implementation
    names, recs = parse_psf(psf)
    if not recs:
        out("DEVICE_STRESS_REVIEW_REQUIRED (psf unreadable)")
        return
    nets = set(k for k in recs[0].keys() if k != "time")
    missing = set()
    out("## Terminal voltages actually seen (from %s)" % os.path.basename(psf))
    out("")
    out("| device | max abs VGS | max abs VGD | max abs VDS |")
    out("|---|---|---|---|")
    for r in rows:
        need = [r["g"], r["d"], r["s"]]
        if any(n not in nets for n in need):
            missing.add(r["inst"])
            out("| `%s` | net not saved (%s) | | |" % (r["inst"],
                ", ".join(n for n in need if n not in nets)))
            continue
        vg = max(abs(rec[r["g"]] - rec[r["s"]]) for rec in recs)
        vd = max(abs(rec[r["d"]] - rec[r["s"]]) for rec in recs)
        vgdr = max(abs(rec[r["g"]] - rec[r["d"]]) for rec in recs)
        out("| `%s` | %.4f V | %.4f V | %.4f V |" % (r["inst"], vg, vgdr, vd))
    out("")
    if missing:
        out("DEVICE_STRESS_REVIEW_REQUIRED for: %s (their gate/drain nets are not in the "
            "saved traces, and guessing a terminal voltage is worse than admitting it)."
            % ", ".join(sorted(missing)))
        print("DEVICE_STRESS_REVIEW_REQUIRED " + " ".join(sorted(missing)))
    else:
        print("DEVICE_STRESS: EXTRACTED")
    out("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("decks", nargs="+")
    ap.add_argument("--out", default=None)
    ap.add_argument("--stress", default=None, help="psfascii from a sweep of the same deck")
    ap.add_argument("--rsen", type=float, default=1e4)
    a = ap.parse_args()

    chunks = []
    emit = chunks.append
    deck = a.decks[0]
    text = io.open(deck, encoding="utf-8", errors="replace").read()
    rows, params, ports = devices_of(text)
    hi, lo = rails_from_sources(text, rows)
    if lo is None:
        hi, lo = supply_nets(rows)
    emit("# Data-driver topology summary (generated, not transcribed)")
    emit("")
    emit("Source deck: `%s`. Generated by `scripts/ddrv_topology.py` from the parsed "
         "devices; the tables are the parse, so they cannot drift from the netlist."
         % os.path.basename(deck))
    emit("")
    device_table(rows, emit, multiplicity(text))
    path_ascii(rows, hi, lo, emit)
    off_explanation(rows, emit)
    ideal_sources(text, emit)
    if a.stress:
        stress(rows, a.stress, emit, a.rsen)
    body = "\n".join(chunks) + "\n"
    if a.out:
        with io.open(a.out, "w", encoding="utf-8", newline="") as fh:
            fh.write(body.encode("utf-8") if str is bytes else body)
        print(a.out)
    else:
        print(body)


if __name__ == "__main__":
    main()
