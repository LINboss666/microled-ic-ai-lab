#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ddrv_probe.py -- one place that decides how a data-driver run's IOUT is read.

Two methods exist and they are NOT equal:

  iprobe    `Ip1 (vsw data_out) iprobe` is a zero-impedance series element, so it reports
            the absorbed current with 0 V across it. The DUT then sees the V(DATA_OUT) the
            testbench asked for. Proven on this build (15.1.0.284) by
            spectre/current_probe_syntax.scs: trace `Ip1:i`, and `vsw == data_out`.

  RSEN      the 10 k sense resistor used by the first rounds computes
            IOUT = (V(vsw) - V(data_out)) / RSEN. At 15 uA that drop is 150 mV, which
            shifts the compliance knee by 150 mV and makes every low-VOUT transient a
            measurement of the resistor, not of the channel. Runs that only have these
            traces are reported under the explicit label LEGACY_BURDENED_MEASUREMENT.

A deck that carries both prefers the probe; nothing here ever silently adds a resistor.
`Mout:1` (the MOS terminal-1 current) is saved alongside the probe purely as an
independent cross-check, never as the reported number.
"""

from __future__ import print_function

PROBE = "iprobe"
LEGACY = "rsen"

LEGACY_TAG = "LEGACY_BURDENED_MEASUREMENT"


def probe_key(names, suffix=""):
    """Channel index 0 -> Ip1, index 1 -> Ip2 (build_E numbers probes from 1)."""
    try:
        idx = int(suffix) if suffix else 0
    except ValueError:
        return None
    key = "Ip%d:i" % (idx + 1)
    return key if key in names else None


def check_key(names, suffix=""):
    """The device terminal current saved next to the probe: Mout:1, Mout1:1, ..."""
    key = "Mout%s:1" % ("" if not suffix else suffix)
    return key if key in names else None


def method_for(names, suffix="", allow_legacy=True):
    """Return (method, probe trace, cross-check trace)."""
    pk = probe_key(names, suffix)
    if pk:
        return PROBE, pk, check_key(names, suffix)
    if not allow_legacy:
        return None, None, None
    return LEGACY, None, check_key(names, suffix)


def current(row, method, pk, rsen, vsn, onn):
    if method == PROBE:
        return row[pk]
    return (row[vsn] - row[onn]) / rsen


def crosscheck(rows, pk, dk):
    """Worst absolute and relative disagreement between the two independent views of the
    same current. Returns (worst_abs_A, worst_pct, n_compared); a 15 uA sink whose probe
    and drain current disagree by more than a few percent is a deck problem, not a number."""
    pairs = [(r[pk], r[dk]) for r in rows if pk in r and dk in r]
    if not pairs:
        return None, None, 0
    worst_abs = max(abs(a - b) for a, b in pairs)
    ref = max(max(abs(a), abs(b)) for a, b in pairs)
    worst_pct = (worst_abs / ref * 100.0) if ref else 0.0
    return worst_abs, worst_pct, len(pairs)


def report(method, pk, dk, rows, rsen, prefix="   IOUT_SOURCE", fullscale=None, note=None):
    if method == PROBE:
        print("%s : %s trace `%s`, 0 V burden (DC drop across the probe is 0 by "
              "construction)" % (prefix, PROBE, pk))
        if dk:
            res = crosscheck(rows, pk, dk)
            if res[0] is None:
                print("   PROBE_CROSSCHECK  : `%s` not in the data file" % dk)
            else:
                # two ways of scaling the same worst difference. In an OFF sweep both
                # currents are pA, so "94 %% of the observed value" is true but useless,
                # while "0.00003 %% of full scale" is what decides whether the deck is
                # consistent. Report both rather than pick the flattering one.
                line = ("   PROBE_CROSSCHECK  : |%s - %s| <= %.3e A over %d samples"
                        % (pk, dk, res[0], res[2]))
                if fullscale:
                    line += " = %.6f %% of full scale" % (res[0] / abs(fullscale) * 100.0)
                print(line)
                print("   PROBE_CROSSCHECK  : %.4f %% of the largest observed current "
                      "(%.3e A) -- the two views of the same branch" % (res[1], max(
                          abs(r[pk]) for r in rows if pk in r)))
                if note:
                    print("   PROBE_CROSSCHECK  : note -- %s" % note)
    else:
        print("%s : %s -- IOUT=(v(vsw)-v(%s))/%.3g, which burdens the circuit by "
              "%.1f mV at 15 uA and is NOT an accepted method for new baselines"
              % (prefix, LEGACY_TAG, "data_out", rsen, 15e-6 * rsen * 1000.0))


if __name__ == "__main__":
    # self-test: the two lookups must not silently cross over
    n = ["Ip1:i", "Ip2:i", "Mout:1", "Mout1:1", "vsw", "data_out"]
    assert probe_key(n, "") == "Ip1:i" and probe_key(n, "1") == "Ip2:i"
    assert check_key(n, "") == "Mout:1" and check_key(n, "1") == "Mout1:1"
    assert probe_key(["vsw"], "") is None
    assert method_for(["vsw", "data_out"], "")[0] == LEGACY
    assert method_for(n, "")[0] == PROBE
    assert method_for(["vsw"], "", allow_legacy=False)[0] is None
    assert abs(current({"Ip1:i": 1.5e-5}, PROBE, "Ip1:i", 1e4, "vsw", "data_out")
               - 1.5e-5) < 1e-20
    assert abs(current({"vsw": 1.0, "data_out": 0.85}, LEGACY, None, 1e4, "vsw",
                       "data_out") - 1.5e-5) < 1e-20
    res = crosscheck([{"Ip1:i": 1.5e-5, "Mout:1": 1.49e-5}], "Ip1:i", "Mout:1")
    assert abs(res[0] - 1e-7) < 1e-12 and abs(res[1] - 0.6667) < 0.01 and res[2] == 1
    print("DDRIV_PROBE_SELFCHECK: PASS")
