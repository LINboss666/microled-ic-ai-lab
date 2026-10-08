#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-3 Part C: extract the accepted Candidate E-DNW golden deck into OA-importable cells.

Why a script instead of a hand-written netlist: SCH-3 section 3 makes the accepted Spectre deck the
only authority for connectivity and parameters ("不得重新手写连线逻辑"), and DATA-5 section 3 shows what
happens when a generator default silently rewrites a bulk connection. So this file reads the deck,
splits it into the two cells the spec asks for, renames ONLY the port nets, and then refuses to
continue unless the generated sub-circuits re-parse back to the deck's device lines token for token.

Cell split (SCH-3 sections 4 and 6):
  data_sink_1ch   Mcas, Mout, Mpass_local, Mbleed_local        pins DATA_EN DATA_EN_B VBIAS_SHARED
                                                               VCAS DATA_OUT VSS
  data_bias_ref   Mref                                          pins VBIAS_SHARED VSS
  The ideal 15 uA source, VCAS/DATA_EN sources, VDD rail and the current probe stay in the
  testbench -- they are TESTBENCH ASSUMPTIONS, not cell content.

Net renaming is a declared 1:1 map, recorded in results/data_driver_schematic_connectivity.csv;
internal nets (node_m, vbias_ch) keep the deck's names so the incidence structure is literally the
deck's.

Usage:
  python scripts/sch3_golden_extract.py \
      --deck spectre/generated/ddrv_E_local_gate_n33_tt_l2e6w2e5_ch1_iprobe_dnwpass_tt_on.scs \
      --outdir spectre/import --resultsdir results
Exit 0 only when the round-trip check passes.
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sch2_golden_params import to_metres   # one SI resolver for the whole project (AGENTS rule 27)

# device -> cell. Anything not listed is a hard error, because inventing a role is how a device
# quietly disappears from both cells.
ROLE_CELL = {
    "Mcas": "data_sink_1ch",
    "Mout": "data_sink_1ch",
    "Mpass_local": "data_sink_1ch",
    "Mbleed_local": "data_sink_1ch",
    "Mref": "data_bias_ref",
}
DNW_MASTER = "n33_dnw_4t_ckt"

# golden net -> OA port name, only for nets that become pins
PORT_MAP = {
    "data_en": "DATA_EN",
    "data_en_b": "DATA_EN_B",
    "vbias": "VBIAS_SHARED",
    "vcas": "VCAS",
    "data_out": "DATA_OUT",
    "vss": "VSS",
}
# internal nets that must stay internal (they are the channel's own nodes, not ports)
INTERNAL = ("node_m", "vbias_ch")
# port order + direction per cell (SCH-3 section 6: directions follow circuit semantics)
CELL_PORTS = {
    "data_sink_1ch": [("DATA_EN", "input"), ("DATA_EN_B", "input"), ("VBIAS_SHARED", "input"),
                      ("VCAS", "input"), ("DATA_OUT", "output"), ("VSS", "inputOutput")],
    "data_bias_ref": [("VBIAS_SHARED", "output"), ("VSS", "inputOutput")],
}

INST_RX = re.compile(r"^\s*(\w+)\s*\(\s*([^)]+?)\s*\)\s*(\w+)\s+(.*)$")


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def parse_devices(text):
    """Every MOS instance line of the deck: name, 4 nets, master, attributes, original line."""
    out, skipped = [], []
    for line in text.split("\n"):
        if not line or line.lstrip().startswith("*"):
            continue
        m = INST_RX.match(line)
        if not m:
            continue
        name, nets, master, rest = m.group(1), m.group(2).split(), m.group(3), m.group(4)
        if master in ("vsource", "isource", "vsense"):
            continue
        attrs = dict(re.findall(r"(\w+)\s*=\s*(\S+)", rest))
        if len(nets) != 4:
            skipped.append("%s: %d nets, expected 4 (d g s b)" % (name, len(nets)))
            continue
        out.append(dict(name=name, nets=nets, master=master, attrs=attrs,
                        l_raw=attrs.get("l"), w_raw=attrs.get("w"), line=line.rstrip()))
    return out, skipped


def check_devices(devs):
    """The guards SCH-3 section 5 puts on this circuit: DNW master, body tie, diode, gates."""
    fails, by = [], dict((d["name"], d) for d in devs)
    want = set(ROLE_CELL)
    if set(by) != want:
        fails.append("deck devices %s != the expected set %s" % (sorted(by), sorted(want)))
    for d in devs:
        if d["name"] not in ROLE_CELL:
            continue
        if d["master"] != "n33" and d["name"] != "Mpass_local":
            fails.append("%s: master %s is not n33" % (d["name"], d["master"]))
    p = by.get("Mpass_local")
    if p:
        if p["master"] != DNW_MASTER:
            fails.append("Mpass_local master %s != the accepted isolated-body master %s"
                         % (p["master"], DNW_MASTER))
        pd, pg, ps, pb = p["nets"]
        if ps != "vbias_ch" or pb != "vbias_ch":
            fails.append("Mpass_local nets %s: Source and Body must both be this channel's own "
                         "vbias_ch (VBS = 0)" % p["nets"])
        if pb == "vss":
            fails.append("Mpass_local body tied to vss -- the DATA-4.5 bodyfix that FAILED at ss")
        if pg != "data_en":
            fails.append("Mpass_local gate %s != data_en (the pass device is gated by DATA_EN, "
                         "not by the complementary input)" % pg)
        if pd != "vbias":
            fails.append("Mpass_local drain %s != vbias (it passes the SHARED bias onto the local "
                         "gate node)" % pd)
    m = by.get("Mout")
    if m and m["nets"][1] != "vbias_ch":
        fails.append("Mout gate %s != vbias_ch (the local mirror gate is what gating controls)"
                     % m["nets"][1])
    c = by.get("Mcas")
    if c and c["nets"][1] != "vcas":
        fails.append("Mcas gate %s != vcas" % c["nets"][1])
    bl = by.get("Mbleed_local")
    if bl and bl["nets"][1] != "data_en_b":
        fails.append("Mbleed_local gate %s != data_en_b (the complementary input, no local inverter)"
                     % bl["nets"][1])
    r = by.get("Mref")
    if r and not (r["nets"][0] == r["nets"][1]):
        fails.append("Mref is not diode-connected (D=%s G=%s)" % (r["nets"][0], r["nets"][1]))
    for d in devs:
        for key in ("l", "w"):
            if to_metres(d["attrs"].get(key), {}) is None:
                fails.append("%s: %s=%r does not resolve to a number"
                             % (d["name"], key, d["attrs"].get(key)))
        extra = sorted(set(d["attrs"]) - set(["l", "w"]))
        if extra:
            fails.append("%s: unexpected attributes %s (no rule for them)" % (d["name"], extra))
    return fails


COLS = ["instance_name", "model", "D", "G", "S", "B",
        "golden_L_raw", "golden_L_m", "golden_W_raw", "golden_W_m",
        "golden_fingers", "golden_fingers_source", "golden_multiplier",
        "golden_multiplier_source", "cell"]


def golden_rows(devs, cell_of=None):
    """Rows in the schema scripts/sch_parameter_integrity_check.py reads.

    cell_of defaults to the data-driver role table but can be replaced, which is how the same
    formatting is used for the SCH-3 section 8 smoke cell without a second copy of this code.
    """
    pick = cell_of or (lambda name: ROLE_CELL.get(name, "-"))
    rows = []
    for d in sorted(devs, key=lambda x: x["name"]):
        rows.append(",".join([d["name"], d["master"]] + d["nets"] + [
            d["l_raw"], "%.9g" % to_metres(d["l_raw"], {}),
            d["w_raw"], "%.9g" % to_metres(d["w_raw"], {}),
            "1", "DEFAULT_FROM_NETLIST_ABSENCE", "1", "DEFAULT_FROM_NETLIST_ABSENCE",
            pick(d["name"])]))
    return rows


def golden_csv(devs, path, cell_of=None):
    """One table for review plus one per cell: the integrity gate is run per cellview, so each
    call needs a golden side that contains exactly that cell's devices."""
    out = [",".join(COLS)] + golden_rows(devs, cell_of)
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    return len(out) - 1


def emit_subckt(devs, cell, outdir):
    """The import body: deck device lines with port nets renamed and nothing else changed."""
    ports = CELL_PORTS[cell]
    lines = ["subckt %s (%s)" % (cell, " ".join(p for p, _d in ports))]
    for name, direction in ports:
        lines.append("  parameters %s %s" % (name, direction))
    body = [d for d in devs if ROLE_CELL[d["name"]] == cell]
    for d in sorted(body, key=lambda x: x["name"]):
        nets = [PORT_MAP.get(n, n) for n in d["nets"]]
        lines.append("  %s (%s) %s %s" % (d["name"], " ".join(nets), d["master"],
                                          " ".join("%s=%s" % (k, d["attrs"][k])
                                                   for k in sorted(d["attrs"]))))
    lines.append("ends %s" % cell)
    path = os.path.join(outdir, "%s.scs" % cell)
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    return path, lines


def round_trip(deck_devs, paths):
    """Re-parse what was emitted and demand the deck's device lines back, modulo the declared map."""
    fails = []
    got = {}
    for cell, path in paths:
        text = read(path)
        devs, _skipped = parse_devices(text)
        for d in devs:
            got[d["name"]] = d
    for d in deck_devs:
        g = got.get(d["name"])
        if g is None:
            fails.append("round-trip lost %s" % d["name"])
            continue
        want_nets = [PORT_MAP.get(n, n) for n in d["nets"]]
        if g["nets"] != want_nets:
            fails.append("%s nets %s != mapped deck nets %s" % (d["name"], g["nets"], want_nets))
        if g["master"] != d["master"]:
            fails.append("%s master %s != deck %s" % (d["name"], g["master"], d["master"]))
        if g["attrs"] != d["attrs"]:
            fails.append("%s attrs %s != deck %s" % (d["name"], g["attrs"], d["attrs"]))
    return fails


def net_map_csv(path, devs):
    """The declared golden-net -> OA-name map, with the cells each name appears in."""
    def cells_using(net):
        return sorted(set(ROLE_CELL[d["name"]] for d in devs if net in d["nets"]))
    rows = ["golden_net,oa_name,kind,cells"]
    for net in sorted(PORT_MAP):
        rows.append("%s,%s,EXTERNAL_PORT,%s" % (net, PORT_MAP[net], "+".join(cells_using(net))))
    for net in INTERNAL:
        rows.append("%s,%s,INTERNAL_NET,%s" % (net, net, "+".join(cells_using(net))))
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")


def emit_top(paths, outdir, top):
    """The import scaffold spiceIn insists on (SPICEIN-77: the top cell may not be a subckt).

    Generated from the parsed subckt port lists, never hand-written: a port name two cells share
    (VBIAS_SHARED, VSS) becomes one top-level net of that name, which is the shared-bias
    composition SCH-3 section 15 asks for, expressed mechanically rather than by re-wiring.
    """
    lines = ["simulator lang=spectre insensitive=yes", "global 0"]
    nets, insts = [], []
    for i, (cell, path) in enumerate(sorted(paths)):
        text = read(path)
        hdr = re.search(r"^subckt\s+(\S+)\s*\(([^)]*)\)", text, re.M)
        if not hdr or hdr.group(1) != cell:
            return None, None, "subckt header for %s is missing or misnamed" % cell
        if not re.search(r"^ends\s+%s" % re.escape(cell), text, re.M):
            return None, None, "subckt %s has no ends statement" % cell
        ports = hdr.group(2).split()
        if ports != [p for p, _d in CELL_PORTS[cell]]:
            return None, None, "subckt %s port list %s != the declared one" % (cell, ports)
        lines.append("")
        lines += text[text.index(hdr.group(0)):].rstrip("\n").split("\n")
        for n in ports:
            if n not in nets:
                nets.append(n)
        insts.append("X%d (%s) %s" % (i + 1, " ".join(ports), cell))
    lines.append("")
    lines.append("parameters %s inputOutput" % " ".join(nets))
    lines += insts
    path = os.path.join(outdir, "%s.scs" % top)
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    return path, lines, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--outdir", default="spectre/import")
    ap.add_argument("--resultsdir", default="results")
    ap.add_argument("--top", default="sch3_top")
    args = ap.parse_args()

    for d in (args.outdir, args.resultsdir):
        if not os.path.isdir(d):
            os.makedirs(d)
    text = read(args.deck)
    devs, skipped = parse_devices(text)
    print("DECK: %s" % args.deck)
    print("DECK_MOS_LINES: %d" % len(devs))
    for s in skipped:
        print("DECK_SKIP: %s" % s)

    fails = check_devices(devs)
    if fails:
        for f in fails:
            print("GOLDEN_GUARD_FAIL: %s" % f)
        print("GOLDEN_EXTRACTION: FAIL")
        return 1
    print("GOLDEN_GUARDS: DNW_MASTER=%s MPASS_SOURCE_EQ_BODY=YES MREF_DIODE=YES "
          "MBLEED_GATE=DATA_EN_B MOUT_GATE=vbias_ch MCAS_GATE=vcas" % DNW_MASTER)

    n = golden_csv(devs, os.path.join(args.resultsdir, "data_driver_golden_devices.csv"))
    print("GOLDEN_TABLE: results/data_driver_golden_devices.csv rows=%d" % n)
    for cell in sorted(set(ROLE_CELL.values())):
        sub = [d for d in devs if ROLE_CELL[d["name"]] == cell]
        p = os.path.join(args.resultsdir, "data_driver_golden_%s.csv" % cell)
        golden_csv(sub, p)
        print("GOLDEN_TABLE_CELL: %s rows=%d" % (p, len(sub)))

    paths = []
    for cell in sorted(set(ROLE_CELL.values())):
        p, lines = emit_subckt(devs, cell, args.outdir)
        paths.append((cell, p))
        print("IMPORT_NETLIST: %s" % p)
        for ln in lines:
            print("  | %s" % ln)

    rt = round_trip(devs, paths)
    if rt:
        for f in rt:
            print("ROUND_TRIP_FAIL: %s" % f)
        print("IMPORT_LINES_MATCH_GOLDEN: FAIL")
        return 1
    print("ROUND_TRIP_DEVICES: %d/%d" % (len(devs), len(devs)))
    print("IMPORT_LINES_MATCH_GOLDEN: PASS")
    tpath, tlines, terr = emit_top(paths, args.outdir, args.top)
    if terr:
        print("TOP_SCAFFOLD_FAIL: %s" % terr)
        print("GOLDEN_EXTRACTION: FAIL")
        return 1
    print("IMPORT_TOP: %s" % tpath)
    for ln in tlines:
        print("  | %s" % ln)
    net_map_csv(os.path.join(args.resultsdir, "data_driver_net_rename_map.csv"), devs)
    print("NET_MAP: results/data_driver_net_rename_map.csv")
    print("GOLDEN_EXTRACTION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
