#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-3 section 11: independent connectivity check of the OA cellviews against the accepted deck.

The parameter gate (scripts/sch_parameter_integrity_check.py) proves each device carries the right
size; it deliberately does not judge whether the right NET hangs off each terminal -- terminals only
have to be bound at all. This script closes that half: it reads the terminal->net table the read-only
SKILL dumped, maps the deck's net names onto the OA port names through the machine-readable rename
map, and demands per-terminal equality. It then asserts the specific properties SCH-3 section 5 calls
the highest-risk ones, because both have been real defects in this project's history:

  A1 the pass device is the deep-N-well master, not plain n33
  A2 its Source and Body are the same node, that node is this channel's own, and it is not VSS
     (DATA-4.5: tying the body of an ordinary n33 to vss FUNCTIONAL FAILed at the ss corner)
  A3 the mirror gate that the output device responds to is the LOCAL node, not the shared bias
  A4 the shared reference device is exactly one, diode-connected, and lives in the bias cell
  A5 the bleed device responds to the complementary input, and the channel contains no local
     inverter: every non-device instance in the cell is a port pin
  A6 DATA_OUT is a port of the channel cell and the two internal nodes are not

Usage:
  python scripts/sch3_connectivity_check.py --readback results/evidence/sch3_readback_post_fix.log \
      --golden results/data_driver_golden_devices.csv \
      --netmap results/data_driver_net_rename_map.csv
Exit 0 only when every assertion holds.
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sch_parameter_integrity_check import parse_row   # one token parser, same RD-ROW grammar

PAIR = re.compile(r'(\w+)=(\d+)')   # the RD-CELL counters are always plain integers
SINK, BIAS = "data_sink_1ch", "data_bias_ref"
DNW = "n33_dnw_4t_ckt"


def load(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def parse_readback(path):
    """cell -> {devices, port_nets, instances, nets, shapes}; devices keyed by instance name."""
    cells = {}
    current = None
    for line in load(path).split("\n"):
        if "RD-CELL" in line:
            m = re.search(r'RD-CELL\s+"?[^"/\s]+"?/"?(\w+)"?', line)
            current = m.group(1) if m else None
            hdr = dict(PAIR.findall(line))
            cells.setdefault(current, {"devices": {}, "port_nets": [], "instances": 0,
                                       "nets": 0, "shapes": 0})
            cells[current]["instances"] = int(hdr.get("instances", 0))
            cells[current]["nets"] = int(hdr.get("nets", 0))
            cells[current]["shapes"] = int(hdr.get("shapes", 0))
        elif "RD-ROW" in line:
            r = parse_row(line)
            cell = r.get("cell", current)
            cells.setdefault(cell, {"devices": {}, "port_nets": [], "instances": 0,
                                    "nets": 0, "shapes": 0})
            cells[cell]["devices"][r["inst"]] = r
        elif "RD-NETPIN" in line:
            r = parse_row(line)
            if current:
                cells.setdefault(current, {"devices": {}, "port_nets": [], "instances": 0,
                                          "nets": 0, "shapes": 0})["port_nets"].append(r["net"])
    return cells


def load_netmap(path):
    lines = load(path).strip().split("\n")
    hdr = lines[0].split(",")
    out = {}
    for row in lines[1:]:
        r = dict(zip(hdr, row.split(",")))
        out[r["golden_net"]] = r["oa_name"]
    return out


def load_golden(path):
    lines = load(path).strip().split("\n")
    hdr = lines[0].split(",")
    return dict((r["instance_name"], r) for r in (dict(zip(hdr, l.split(","))) for l in lines[1:]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readback", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--netmap", required=True)
    ap.add_argument("--out", default="results/data_driver_schematic_connectivity.csv")
    args = ap.parse_args()

    cells = parse_readback(args.readback)
    netmap = load_netmap(args.netmap)
    golden = load_golden(args.golden)

    fails = []
    rows = ["instance,cell,oa_master,golden_master,D,G,S,B,expected_D,expected_G,expected_S,"
            "expected_B,terminal_match"]
    matched = 0
    total = 0
    for name in sorted(golden):
        g = golden[name]
        cell = g["cell"]
        dev = cells.get(cell, {}).get("devices", {}).get(name)
        if dev is None:
            fails.append("%s: not present in %s" % (name, cell))
            rows.append("%s,%s,MISSING,%s,,,,,,,,FAIL" % (name, cell, g["model"]))
            continue
        expect = [netmap.get(n, n) for n in (g["D"], g["G"], g["S"], g["B"])]
        got = [dev.get("D"), dev.get("G"), dev.get("S"), dev.get("B")]
        ok = expect == got
        matched += 1 if ok else 0
        total += 1
        if not ok:
            fails.append("%s terminals %s != golden (mapped) %s" % (name, got, expect))
        if dev.get("master_cell") != g["model"]:
            fails.append("%s master %s != golden %s" % (name, dev.get("master_cell"), g["model"]))
        rows.append(",".join([name, cell, "%s/%s:%s" % (dev.get("master_lib"), dev.get("master_cell"),
                                                         dev.get("master_view")), g["model"]]
                             + got + expect + ["yes" if ok else "no"]))

    sink = cells.get(SINK, {"devices": {}, "port_nets": [], "instances": 0, "nets": 0, "shapes": 0})
    bias = cells.get(BIAS, {"devices": {}, "port_nets": [], "instances": 0, "nets": 0, "shapes": 0})
    pm = sink["devices"].get("Mpass_local")
    ml = sink["devices"].get("Mbleed_local")
    mo = sink["devices"].get("Mout")
    ref = bias["devices"].get("Mref")

    def assert_that(label, cond, detail):
        if cond:
            print("ASSERT %s: PASS" % label)
        else:
            print("ASSERT %s: FAIL  (%s)" % (label, detail))
            fails.append("%s: %s" % (label, detail))

    assert_that("A1_DNW_MASTER_FOR_PASS", pm and pm.get("master_cell") == DNW,
                "Mpass_local master=%s" % (pm and pm.get("master_cell")))
    assert_that("A2_PASS_SOURCE_EQ_BODY_OWN_CHANNEL",
                pm and pm.get("S") == pm.get("B") == "vbias_ch" and pm.get("B") != "VSS",
                "S=%s B=%s" % (pm and pm.get("S"), pm and pm.get("B")))
    assert_that("A3_MOUT_GATE_IS_LOCAL_NODE", mo and mo.get("G") == "vbias_ch",
                "Mout gate=%s" % (mo and mo.get("G")))
    assert_that("A4_SHARED_REF_DIODE_AND_SINGLE",
                ref and ref.get("D") == ref.get("G") and len(bias["devices"]) == 1,
                "Mref D=%s G=%s bias devices=%d" % (ref and ref.get("D"), ref and ref.get("G"),
                                                   len(bias["devices"])))
    assert_that("A5_BLEED_ON_COMPLEMENT_AND_NO_LOCAL_INVERTER",
                ml and ml.get("G") == "DATA_EN_B"
                and sink["instances"] - len(sink["devices"]) == len(set(sink["port_nets"]))
                and bias["instances"] - len(bias["devices"]) == len(set(bias["port_nets"])),
                "sink instances=%d devices=%d pins=%d | bias instances=%d devices=%d pins=%d"
                % (sink["instances"], len(sink["devices"]), len(set(sink["port_nets"])),
                   bias["instances"], len(bias["devices"]), len(set(bias["port_nets"]))))
    assert_that("A6_PORT_SET",
                sorted(set(sink["port_nets"])) == ["DATA_EN", "DATA_EN_B", "DATA_OUT", "VBIAS_SHARED",
                                                   "VCAS", "VSS"]
                and sorted(set(bias["port_nets"])) == ["VBIAS_SHARED", "VSS"]
                and "vbias_ch" not in sink["port_nets"] and "node_m" not in sink["port_nets"],
                "sink=%s bias=%s" % (sorted(set(sink["port_nets"])), sorted(set(bias["port_nets"]))))

    if len(sink["devices"]) != 4:
        fails.append("%s has %d devices, expected 4" % (SINK, len(sink["devices"])))
    if len(bias["devices"]) != 1:
        fails.append("%s has %d devices, expected 1" % (BIAS, len(bias["devices"])))

    directory = os.path.dirname(args.out)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")

    print("MOS_COUNT: %d" % (len(sink["devices"]) + len(bias["devices"])))
    print("TERMINAL_CONNECTIVITY_MATCH: %d/%d" % (matched, total))
    print("CELL_SINK_NETS_SHAPES: nets=%d shapes=%d" % (sink["nets"], sink["shapes"]))
    print("CELL_BIAS_NETS_SHAPES: nets=%d shapes=%d" % (bias["nets"], bias["shapes"]))
    print("CONNECTIVITY_TABLE: %s" % args.out)
    for f in fails:
        print("MISMATCH: %s" % f)
    gate = not fails and matched == total == len(golden)
    print("OA_CONNECTIVITY: %s" % ("PASS" if gate else "FAIL"))
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
