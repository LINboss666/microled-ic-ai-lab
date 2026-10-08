#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unit tests for scripts/sch_parameter_integrity_check.py.

The gate was written after a schematic passed every other check while all its transistors carried
the PDK's default geometry, so a checker that only ever sees good data proves nothing. Each case
builds a golden table plus a synthetic readback log in a temp directory and asserts the exit code
and the counter that must (or must not) fire.

Both directions are covered on purpose: devices sitting on the PDK default must fail (CASE2), and a
design size that legitimately equals that default must not (CASE7) -- otherwise the gate gets
switched off the first time it cries wolf.

Run: python scripts/test_sch_parameter_integrity_check.py
"""
from __future__ import print_function

import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "sch_parameter_integrity_check.py")

GOLDEN_HDR = ("instance_name,model,D,G,S,B,golden_L_raw,golden_L_m,golden_W_raw,golden_W_m,"
              "golden_fingers,golden_fingers_source,golden_multiplier,golden_multiplier_source")
DEFAULT_L, DEFAULT_W = "180n", "220n"

# (name, model, D, G, S, B, L_raw, L_m, W_raw, W_m)
BASE = [
    ("mn_c", "n18", "clkb", "clk", "vss", "vss", "200n", "2e-07", "2u", "2e-06"),
    ("mp_c", "p18", "clkb", "clk", "vdd", "vdd", "200n", "2e-07", "4u", "4e-06"),
    ("mn_k1", "n18", "mb", "m", "vss", "vss", "200n", "2e-07", "500n", "5e-07"),
]
# same cell, first device specified at exactly the PDK default: "equals default" must not be
# suspicious when the golden says that IS the design size
DEFAULT_SIZED = [("mn_c", "n18", "clkb", "clk", "vss", "vss", DEFAULT_L, "1.8e-07",
                  DEFAULT_W, "2.2e-07")] + BASE[1:]

NL = chr(10)


def golden_text(rows):
    lines = [GOLDEN_HDR]
    for r in rows:
        lines.append(",".join(list(r) + ["1", "DEFAULT_FROM_NETLIST_ABSENCE", "1",
                                         "DEFAULT_FROM_NETLIST_ABSENCE"]))
    return NL.join(lines) + NL


def row(inst, model, d, g, s, b, l_txt, w_txt, fingers="1", mult="1", raw_w_absent=False):
    """One RD-ROW line in the shape skill/sch2_readback.il prints it."""
    w_field = "ABSENT" if raw_w_absent else '"%s"' % w_txt
    return ('RD-ROW inst="%s" master_lib="smic18mmrf" master_cell="%s" master_view="symbol" '
            'model="%s" raw_l="%s" raw_w=%s raw_fw=%s raw_fingers="%s" raw_mult="%s" simW="%s" '
            'cdf_l="%s" cdf_w="%s" cdf_fw="%s" cdf_fingers="%s" cdf_mult="%s" '
            'num_l=(2e-07) num_w=(2e-06) bbox=(((0 0) (1 1))) D="%s" G="%s" S="%s" B="%s"'
            % (inst, model, model, l_txt, w_field, w_field, fingers, mult, w_txt,
               l_txt, w_txt, w_txt, fingers, mult, d, g, s, b))


def matching_rows(golden_rows):
    return [row(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[8]) for r in golden_rows]


def all_default(golden_rows):
    return [row(r[0], r[1], r[2], r[3], r[4], r[5], DEFAULT_L, DEFAULT_W) for r in golden_rows]


def unresolved(golden_rows):
    """The real defect: l holds the design-variable name and the raw w/fw properties never existed."""
    return [row(r[0], r[1], r[2], r[3], r[4], r[5], "ln", DEFAULT_W, raw_w_absent=True)
            for r in golden_rows]


def write_readback(path, rows):
    body = ["RD-CELL microled_cells/test_cell instances=%d nets=13 shapes=219" % len(rows)]
    body += rows
    for net in ("d", "clk", "q", "qbar", "vdd", "vss"):
        body.append('RD-NETPIN net="%s" pins=1' % net)
    io.open(path, "w", encoding="utf-8", newline=NL).write(NL.join(body) + NL)


def run(golden, readback, out, expect_mos):
    cmd = [sys.executable, CHECKER, "--golden", golden, "--readback", readback, "--out", out,
           "--expect-mos", str(expect_mos), "--pdk-default-l", DEFAULT_L,
           "--pdk-default-w", DEFAULT_W]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.communicate()[0].decode("utf-8", "replace")  # reaps the child
    return proc.returncode, text  # reading returncode before communicate() yields None


def main():
    tmp = tempfile.mkdtemp(prefix="sch_gate_test_")
    golden = os.path.join(tmp, "golden.csv")
    readback = os.path.join(tmp, "readback.log")
    out = os.path.join(tmp, "out.csv")
    n = len(BASE)
    good = matching_rows(BASE)

    cases = [
        ("CASE1 correct MOS parameters -> PASS", BASE, good, 0, None),
        ("CASE2 every device on the PDK default -> FAIL", BASE, all_default(BASE), 1,
         "DEFAULT_VALUE_FALLBACK_COUNT: %d" % n),
        ("CASE3 one device with the wrong width -> FAIL", BASE,
         [good[0], row("mp_c", "p18", "clkb", "clk", "vdd", "vdd", "200n", "2u"), good[2]],
         1, "W_MATCH: 2/%d" % n),
        ("CASE4 one device with an invalid length -> FAIL", BASE,
         [good[0], row("mp_c", "p18", "clkb", "clk", "vdd", "vdd", "0", "4u"), good[2]],
         1, "INVALID_LENGTH_COUNT: 1"),
        # four fields per device are unreadable in that state: raw l, CDF l, raw w, raw fw
        ("CASE5 CDF expression unresolved -> FAIL", BASE, unresolved(BASE), 1,
         "UNRESOLVED_PARAMETER_COUNT: %d" % (4 * n)),
        ("CASE6 different textual units, same physical size -> PASS", BASE,
         [row("mn_c", "n18", "clkb", "clk", "vss", "vss", "200n", "2000n"),
          row("mp_c", "p18", "clkb", "clk", "vdd", "vdd", "2e-7", "4000n"),
          row("mn_k1", "n18", "mb", "m", "vss", "vss", "0.2u", "500n")], 0, None),
        ("CASE7 size that legitimately equals the PDK default -> PASS", DEFAULT_SIZED,
         matching_rows(DEFAULT_SIZED), 0, "DEFAULT_VALUE_FALLBACK_COUNT: 0"),
    ]

    failures = 0
    for case in cases:
        label, gold_rows, rb_rows, want_rc, want_text = case
        io.open(golden, "w", encoding="utf-8", newline=NL).write(golden_text(gold_rows))
        write_readback(readback, rb_rows)
        rc, text = run(golden, readback, out, len(gold_rows))
        ok = rc == want_rc and (not want_text or want_text in text)
        note = "" if ok or not want_text else ", missing '%s'" % want_text
        print("%-58s %s (exit=%s want=%s%s)" % (label, "PASS" if ok else "FAIL", rc, want_rc, note))
        if not ok:
            failures += 1
            print("----- gate output -----")
            print(text)
    print("TEST_PARAMETER_INTEGRITY_CHECKER: %s" % ("PASS" if failures == 0 else "FAIL"))
    return 1 if failures else 0


sys.exit(main())
