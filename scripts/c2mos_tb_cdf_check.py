#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only gate for the C2MOS testbench CDF audit.

Answers one question with numbers instead of adjectives: does the OA cell
microled_cells/c2mos_dff_tb really hold the golden stimulus, and under WHICH names?

Why this file exists at all: the golden deck writes Spectre parameter names (val0/val1/period/...),
analogLib's CDF dictionary names the same quantities v1/v2/per/... and publishes the pair list in
its propMapping. A readback that looks up the Spectre names reports "empty" for values that are
present, so the name pair has to come from the vendor dictionary. The pairs below are transcribed
from analogLib/{vdc,vpulse,cap}/data.dm on this install -- the dump is committed in
results/evidence/c2mos_tb_cdf_audit.txt -- and are asserted here, not trusted.

Nothing in this file writes to a library and it holds no stimulus value of its own: every expected
number is parsed out of the frozen deck by the builder's own parser.

Usage:
  python scripts/c2mos_tb_cdf_check.py --evidence results/evidence/c2mos_tb_cdf_audit.txt
"""
from __future__ import print_function

import argparse
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c2mos_tb_build import parse_golden, as_number  # reuse the builder's own golden parser

# (attribute name in the golden Spectre deck -> parameter name in analogLib's CDF), read off the
# vendor propMapping lists:
#   vdc    propMapping (nil dc vdc mag acm phase acp ... type srcType)   componentName vsource
#   vpulse propMapping (nil dc vdc ... val0 v1 val1 v2 period per delay td rise tr fall tf width
#            pw ... type srcType)                                        componentName vsource
#   cap    instParameters (c w l m scale trise ic tc1 tc2 area perim)     componentName capacitor
SPECTRE_TO_OA = {
    "dc": "vdc", "val0": "v1", "val1": "v2", "period": "per", "delay": "td",
    "rise": "tr", "fall": "tf", "width": "pw", "type": "srcType", "c": "c",
}
# srcType has no instance property on these cells; its value is the MASTER DEFAULT recorded in the
# vendor dump (vpulse def=[pulse], vdc def=[dc]), so "raw ABSENT + CDF equal" is a match here.
MASTER_DEFAULT_BACKED = ("srcType",)
UNIT = {"T": Decimal(10) ** 12, "G": Decimal(10) ** 9, "M": Decimal(10) ** 6,
        "k": Decimal(10) ** 3, "m": Decimal(10) ** -3, "u": Decimal(10) ** -6,
        "n": Decimal(10) ** -9, "p": Decimal(10) ** -12, "f": Decimal(10) ** -15,
        "a": Decimal(10) ** -18}


def to_decimal(text):
    """'200n' -> Decimal('2.0E-7'); plain numbers pass through; non-numeric -> None.

    Cadence normalises units (5e-14 on the raw layer reads back as 50f through the CDF), so the two
    layers must be compared as NUMBERS, never as strings -- AGENTS.md rule 29.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    m = re.match(r"^([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)([a-zA-Z]*)$", s)
    if not m:
        return None
    val = Decimal(m.group(1))
    if not m.group(2):
        return val
    if m.group(2) not in UNIT:
        return None
    return val * UNIT[m.group(2)]


def same(golden, stored):
    """numeric when both sides are numbers, exact string otherwise"""
    if stored is None or golden is None:
        return False
    a = to_decimal(stored)
    if a is None:
        return str(golden) == str(stored)
    b = golden if isinstance(golden, Decimal) else to_decimal(golden)
    if b is None:
        return False
    return a == b


def parse_evidence(path):
    """Rebuild {instance: {'raw': {}, 'cdf': {}, 'master': ''}} from the TBCA-* log lines."""
    insts = {}
    cur = None
    with open(path, "rb") as f:
        for line in f.read().decode("utf-8", "replace").split("\n"):
            line = line.replace("\\o ", "").replace("\\e ", "").strip()
            m = re.match(r'^TBCA-INST name="([^"]+)" master=(".*/[^ ]*) ', line)
            if m:
                cur = m.group(1)
                insts[cur] = {"raw": {}, "cdf": {}, "master": m.group(2)}
                continue
            if cur is None:
                continue
            m = re.match(r'^TBCA-RAWPROP name="([^"]+)" value="([^"]*)"', line)
            if m:
                insts[cur]["raw"][m.group(1)] = m.group(2)
                continue
            m = re.match(r'^TBCA-CDF name="([^"]+)" type=\S+ def=\S+ value="([^"]*)"', line)
            if m and m.group(1) not in insts[cur]["cdf"]:
                insts[cur]["cdf"][m.group(1)] = m.group(2)
    return insts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=os.path.join("spectre", "c2mos_ff1_func.scs"))
    ap.add_argument("--evidence", required=True)
    a = ap.parse_args()

    p = parse_golden(a.golden)
    # the two dc sources are outside parse_golden's output; read them from the same frozen deck
    txt = open(a.golden, "rb").read().decode("utf-8", "replace")
    vsrc = {}
    for name in ("Vdd", "Vss"):
        m = re.search(r"^%s\s*\(\s*(\w+)\s+0\s*\)\s*vsource\s+dc=(\S+)" % name, txt, re.M)
        if not m:
            raise SystemExit("CHECK_REFUSE: golden deck has no %s vsource line" % name)
        vsrc[name] = as_number(m.group(2), p)

    insts = parse_evidence(a.evidence)
    for required in ("Vdd", "Vss", "Ck", "Dd", "Cq", "Cqb", "X1"):
        if required not in insts:
            raise SystemExit("CHECK_REFUSE: evidence has no instance %s -- the audit did not run"
                             % required)

    rows = []
    bad = 0

    def add(inst, attr, golden):
        oa = SPECTRE_TO_OA[attr]
        cell = insts[inst]
        raw, cdf = cell["raw"].get(oa), cell["cdf"].get(oa)
        ok_raw, ok_cdf = same(golden, raw), same(golden, cdf)
        if raw is None and cdf is None:
            status = "MISSING"
        elif ok_raw and ok_cdf:
            status = "MATCH"
        elif ok_cdf and raw is None and oa in MASTER_DEFAULT_BACKED:
            status = "MATCH_VIA_MASTER_DEFAULT"
        elif ok_cdf:
            status = "MATCH_CDF_ONLY"
        elif ok_raw:
            status = "MATCH_RAW_ONLY"
        else:
            status = "MISMATCH"
        if not status.startswith("MATCH"):
            bad += 1
        rows.append(("%s" % golden, oa, raw or "ABSENT", cdf or "ABSENT", status, "%s/%s" % (inst, attr)))

    for inst in ("Vdd", "Vss"):
        add(inst, "dc", vsrc[inst])
    for inst, key in (("Ck", "Ck"), ("Dd", "Dd")):
        attrs = p[key]["attrs"]
        for attr in ("type", "val0", "val1", "period", "delay", "width", "rise", "fall"):
            # `type` is the one attribute whose golden value is a token, not a number
            golden = attrs[attr] if attr == "type" else as_number(attrs[attr], p)
            add(inst, attr, golden)
    for inst in ("Cq", "Cqb"):
        add(inst, "c", p[inst]["c"])

    print("# GOLDEN_VALUE     : value stated by the frozen deck, parsed (never retyped)")
    print("# CDF_PROPERTY_NAME: analogLib's own name for it, from data.dm propMapping")
    print("# OA_RAW_VALUE     : dbFindProp on the instance | OA_CDF_VALUE : cdfFindParamByName value")
    hdr = "%-16s %-18s %-14s %-14s %-27s %s"
    print(hdr % ("GOLDEN_VALUE", "CDF_PROPERTY_NAME", "OA_RAW_VALUE", "OA_CDF_VALUE",
                 "MATCH_STATUS", "INSTANCE/DECK_ATTR"))
    for g, oa, raw, cdf, st, who in rows:
        print(hdr % (g, oa, raw, cdf, st, who))

    print("ROWS=%d BAD=%d" % (len(rows), bad))
    for inst in sorted(insts):
        print("OA_MASTER instance=%s master=%s raw_prop_count=%d"
              % (inst, insts[inst]["master"], len(insts[inst]["raw"])))
    if bad:
        print("TB_CDF_CHECK: FAIL")
        return 1
    print("TB_CDF_CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
