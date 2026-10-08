#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH parameter integrity gate: compare an OA schematic readback against a golden netlist table.

This exists because an imported schematic passed every count and connectivity check while all 18
transistors silently carried the PDK's default geometry (see
reports/lessons_learned/spicein_cdf_parameter_mapping.md). Instance counts, wire connectivity and a
golden Spectre run can all be green at the same time, so this gate only accepts the numbers that
the database itself reports, per instance, and fails otherwise.

Design rules:
  * the golden side is the CSV from scripts/sch2_golden_params.py (already resolved to metres);
    nothing here reads a netlist to backfill a missing schematic value
  * a value is accepted only if it appears in the raw OA property, in the CDF dictionary, and
    parses to the same number -- an unresolved text such as the design-variable name "ln" is a
    failure, not a pass-by-default
  * the raw property and the CDF must mean the same NUMBER, not be the same string: measured, a
    property written as "1e-06" comes back out of the CDF as "1u"
  * "equals the PDK default" is only suspicious when the golden value differs from that default;
    a design size that legitimately coincides with a default must not fail
  * when the readback carries the vendor's own per-master CDF defaults (RD3-MPARAM lines), those
    decide what "sitting on the default" means, and a --pdk-default-* pair that disagrees with them
    is itself a failure -- n18 defaults to 180n/220n while n33 and n33_dnw_4t_ckt default to
    350n/350n, so reusing one pair across families silently switches the detector off
  * comparison is in SI units, so "2u", "2000n" and "2e-6" are the same size and "220n" is not "2u"
  * generic by construction: golden CSV + readback log + PDK defaults are all arguments, so the
    Data Driver schematic import can call the same script

Usage:
  python scripts/sch_parameter_integrity_check.py \
      --golden results/c2mos_golden_device_parameters.csv \
      --readback logs/sch1/readback.log \
      --out results/c2mos_schematic_device_readback.csv \
      --pdk-default-l 180n --pdk-default-w 220n
Exit code 0 only when every gate below passes.
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys

SUFFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
UNRESOLVED = ("ABSENT", "NO-CDF-PARAM", "NO-PIN", "-", "nil", "UNCONNECTED", "")

PAIR = re.compile(r'(\w+)=(?:"([^"]*)"|(\((?:[^()]|\([^()]*\))*\))|([^\s]+))')


def parse_row(line):
    """key=value tokens of one RD-ROW, with the value as printed."""
    out = {}
    for m in PAIR.finditer(line):
        key = m.group(1)
        val = m.group(2)
        if val is None:
            val = m.group(3) if m.group(3) is not None else m.group(4)
        out[key] = val.strip()
    return out


def to_metres(text):
    """'200n' / '2e-6' / '(2e-07)' -> metres, or None when the text is not a real value."""
    if text is None:
        return None
    s = str(text).strip()
    while s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    s = s.strip('"')
    if s in UNRESOLVED:
        return None
    m = re.match(r"^(\d+\.?\d*(?:[eE][-+]?\d+)?)([fpnum]?)$", s)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2)
    return value * SUFFIX[unit] if unit and unit != "m" else value


def same_size(a, b, rel=1e-9):
    if a is None or b is None:
        return False
    if a == b == 0:
        return True
    return abs(a - b) <= rel * max(abs(a), abs(b))


def load_golden(path):
    lines = io.open(path, encoding="utf-8", errors="replace").read().strip().split("\n")
    hdr = lines[0].split(",")
    out = {}
    for row in lines[1:]:
        r = dict(zip(hdr, row.split(",")))
        out[r["instance_name"]] = r
    return out


def load_readback(path):
    rows, pins, master_defaults = {}, [], {}
    for line in io.open(path, encoding="utf-8", errors="replace"):
        if "RD-ROW" in line:
            r = parse_row(line)
            if "inst" in r:
                rows[r["inst"]] = r
        elif "RD-NETPIN" in line:
            r = parse_row(line)
            if "net" in r:
                pins.append(r["net"])
        elif "RD3-MPARAM" in line:
            # one master's own CDF default, printed by the readback SKILL straight off the vendor
            # cell: skill/sch3_readback.il -> RD3-MPARAM cell="n33" name="l" value="350n"
            r = parse_row(line)
            if r.get("cell") and r.get("name") and r.get("value") != "UNREADABLE":
                master_defaults.setdefault(r["cell"], {})[r["name"]] = r["value"]
    return rows, pins, master_defaults


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--readback", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdk-default-l", default="180n")
    ap.add_argument("--pdk-default-w", default="220n")
    ap.add_argument("--expect-mos", type=int, default=18)
    ap.add_argument("--expect-pins", default="d,clk,q,qbar,vdd,vss")
    ap.add_argument("--expect-lib", default="smic18mmrf",
                    help="library the golden models must be instantiated from, so a wrong-PDK import fails here")
    args = ap.parse_args()

    golden = load_golden(args.golden)
    read, pins, master_defaults = load_readback(args.readback)
    dflt_l, dflt_w = to_metres(args.pdk_default_l), to_metres(args.pdk_default_w)

    fails = []
    counters = dict(UNRESOLVED_PARAMETER_COUNT=0, CDF_ERROR_COUNT=0,
                    INVALID_LENGTH_COUNT=0, DEFAULT_VALUE_FALLBACK_COUNT=0,
                    PDK_DEFAULT_DECLARATION_MISMATCH_COUNT=0)
    master_match = 0
    l_match = 0
    w_match = 0

    if len(read) != args.expect_mos:
        fails.append("readback has %d MOS rows, golden has %d" % (len(read), len(golden)))
    missing = sorted(set(golden) - set(read))
    extra = sorted(set(read) - set(golden))
    if missing:
        fails.append("instances missing from the schematic: %s" % " ".join(missing))
    if extra:
        fails.append("instances not in the golden: %s" % " ".join(extra))

    cols = ["instance_name", "master", "model", "raw_L", "raw_W", "raw_finger_width",
            "raw_fingers", "raw_multiplier", "cdf_L", "cdf_W", "resolved_L_m",
            "resolved_effective_W_m", "golden_L_m", "golden_W_m", "L_match", "W_match",
            "verdict"]
    table = [",".join(cols)]

    for name in sorted(golden):
        g = golden[name]
        r = read.get(name)
        if r is None:
            table.append(",".join([name, "MISSING", g["model"], "", "", "", "", "", "", "",
                                   "", "", g["golden_L_m"], g["golden_W_m"], "FAIL", "FAIL",
                                   "FAIL"]))
            continue
        reasons = []
        gL, gW = float(g["golden_L_m"]), float(g["golden_W_m"])

        # --- the value has to be present in BOTH representations and mean the same number
        raw_l, cdf_l = to_metres(r.get("raw_l")), to_metres(r.get("cdf_l"))
        raw_w, cdf_w = to_metres(r.get("raw_w")), to_metres(r.get("cdf_w"))
        raw_fw = to_metres(r.get("raw_fw"))
        fingers = to_metres(r.get("raw_fingers"))
        mult = to_metres(r.get("raw_mult"))
        for label, val in (("raw_l", raw_l), ("cdf_l", cdf_l), ("raw_w", raw_w), ("cdf_w", cdf_w),
                           ("raw_fw", raw_fw)):
            if val is None:
                counters["UNRESOLVED_PARAMETER_COUNT"] += 1
                reasons.append("%s is not a real value (%s)" % (label, r.get(label)))
        # The CDF and the raw property must mean the SAME NUMBER. They are not required to be the
        # same STRING: measured on this build, a property written as "1e-06" is reported by the CDF
        # as "1u", and an earlier string comparison turned that into a false CDF_ERROR.
        for label, raw_v, cdf_v in (("l", raw_l, cdf_l), ("w", raw_w, cdf_w)):
            if raw_v is not None and cdf_v is not None and not same_size(raw_v, cdf_v):
                counters["CDF_ERROR_COUNT"] += 1
                reasons.append("CDF %s=%s (%.9g) disagrees with the raw property %s (%.9g)"
                               % (label, r.get("cdf_" + label), cdf_v, r.get("raw_" + label), raw_v))

        # --- fingers x multiplier must reproduce the total width, or the size is fictional
        if None not in (raw_w, raw_fw, fingers, mult) and not same_size(
                raw_w, raw_fw * fingers * mult):
            reasons.append("w=%s != fw=%s * fingers=%s * m=%s"
                           % (r.get("raw_w"), r.get("raw_fw"), r.get("raw_fingers"),
                              r.get("raw_mult")))

        # --- which default applies: the vendor CDF's own value for THIS master if the readback
        # carried it, otherwise the value declared on the command line. n18 defaults to 180n/220n
        # and n33 to 350n/350n (both measured), so a single hard-coded pair cannot cover a PDK.
        md = master_defaults.get(r.get("master_cell", "")) or {}
        md_l, md_w = to_metres(md.get("l")), to_metres(md.get("w"))
        eff_dflt_l = md_l if md_l is not None else dflt_l
        eff_dflt_w = md_w if md_w is not None else dflt_w
        for key, declared, measured in (("l", dflt_l, md_l), ("w", dflt_w, md_w)):
            if declared is not None and measured is not None and not same_size(declared, measured):
                counters["PDK_DEFAULT_DECLARATION_MISMATCH_COUNT"] += 1
                fails.append("%s: master %s defaults %s=%s in its own CDF but the gate was told "
                             "%s -- a stale default declaration switches the fall-back detector off"
                             % (name, r.get("master_cell"), key, md.get(key),
                             args.pdk_default_l if key == "l" else args.pdk_default_w))

        # --- legal length, and no silent fall-back to the PDK default. The judgement is on the size
        # the device ACTUALLY has (the CDF answer is used when the raw property is missing), but both
        # length and width must coincide with the default before it counts: a design legitimately at
        # the minimum length with a different width must not be flagged, which is why SCH-2's rule
        # "golden differs from the default, and both dims match it" is kept.
        eff_l = raw_l if raw_l is not None else cdf_l
        eff_w = raw_w if raw_w is not None else cdf_w
        if raw_l is None or (eff_dflt_l is not None and raw_l <= 0):
            counters["INVALID_LENGTH_COUNT"] += 1
            reasons.append("length unusable (%s)" % r.get("cdf_l"))
        if (eff_dflt_l is not None and eff_dflt_w is not None
                and eff_l is not None and eff_w is not None
                and same_size(eff_l, eff_dflt_l) and same_size(eff_w, eff_dflt_w)
                and not (same_size(gL, eff_dflt_l) and same_size(gW, eff_dflt_w))):
            counters["DEFAULT_VALUE_FALLBACK_COUNT"] += 1
            reasons.append("device sits on the PDK default %s/%s while golden is %s/%s"
                           % (md.get("l", args.pdk_default_l), md.get("w", args.pdk_default_w),
                              g["golden_L_raw"], g["golden_W_raw"]))

        ok_l = raw_l is not None and cdf_l is not None and same_size(raw_l, gL) and same_size(cdf_l, gL)
        ok_w = raw_w is not None and cdf_w is not None and same_size(raw_w, gW) and same_size(cdf_w, gW)
        l_match += 1 if ok_l else 0
        w_match += 1 if ok_w else 0
        if not ok_l:
            reasons.append("L %s/%s != golden %.9g" % (r.get("raw_l"), r.get("cdf_l"), gL))
        if not ok_w:
            reasons.append("W %s/%s != golden %.9g" % (r.get("raw_w"), r.get("cdf_w"), gW))

        if r.get("model") != g["model"]:
            reasons.append("model %s != golden %s" % (r.get("model"), g["model"]))
        lib, cell = r.get("master_lib", ""), r.get("master_cell", "")
        if lib != args.expect_lib or cell != g["model"]:
            reasons.append("master %s/%s != golden master %s/%s"
                           % (lib, cell, args.expect_lib, g["model"]))
        else:
            master_match += 1
        for pin in ("D", "G", "S", "B"):
            if r.get(pin) in UNRESOLVED or r.get(pin) is None:
                reasons.append("terminal %s not bound" % pin)

        verdict = "PASS" if not reasons else "FAIL"
        for why in reasons:
            fails.append("%s: %s" % (name, why))
        table.append(",".join([name, lib + "/" + cell + ":" + r.get("master_view", ""), r.get("model", ""), r.get("raw_l", ""),
                               r.get("raw_w", ""), r.get("raw_fw", ""),
                               r.get("raw_fingers", ""), r.get("raw_mult", ""),
                               r.get("cdf_l", ""), r.get("cdf_w", ""),
                               "%.9g" % raw_l if raw_l else "", "%.9g" % raw_w if raw_w else "",
                               g["golden_L_m"], g["golden_W_m"],
                               "yes" if ok_l else "no", "yes" if ok_w else "no", verdict]))

    want = [p.strip() for p in args.expect_pins.split(",") if p.strip()]
    got = sorted(set(pins))
    if sorted(want) != got:
        fails.append("port pins differ: schematic=%s required=%s" % (" ".join(got), " ".join(sorted(want))))

    io.open(args.out, "w", encoding="utf-8", newline="\n").write("\n".join(table) + "\n")

    n = len(golden)
    print("MOS_COUNT_GOLDEN: %d" % n)
    print("MOS_COUNT_READBACK: %d" % len(read))
    print("MOS_MASTER_MATCH: %d/%d" % (master_match, n))
    print("L_MATCH: %d/%d" % (l_match, n))
    print("W_MATCH: %d/%d" % (w_match, n))
    for key in sorted(counters):
        print("%s: %d" % (key, counters[key]))
    if master_defaults:
        for cell in sorted(master_defaults):
            md = master_defaults[cell]
            print("PDK_MASTER_DEFAULT: %s l=%s w=%s fw=%s m=%s fingers=%s"
                  % (cell, md.get("l", "?"), md.get("w", "?"), md.get("fw", "?"),
                     md.get("m", "?"), md.get("fingers", "?")))
    else:
        print("PDK_MASTER_DEFAULT: none in this readback -- judged against --pdk-default-* only")
    print("PORT_PINS: %s" % " ".join(got))
    print("READBACK_TABLE: %s" % args.out)
    for f in fails[:40]:
        print("MISMATCH: %s" % f)
    if len(fails) > 40:
        print("MISMATCH_MORE: %d" % (len(fails) - 40))
    bad_counters = any(counters[k] for k in counters)
    gate = (not fails) and len(read) == n == len(golden) and not bad_counters
    print("OA_DEVICE_PARAMETER_READBACK: %s" % ("PASS" if gate else "FAIL"))
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
