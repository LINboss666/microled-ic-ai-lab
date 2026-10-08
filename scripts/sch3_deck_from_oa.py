#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCH-3 section 13/14: build regression decks whose devices come out of the OA database.

The Cadence netlister is not callable in a batch session on this build (measured in SCH-2: the asi*/
nl* entry points exist but return nil without a session object), so the OA-to-netlist step has to be
done by this project. That is only acceptable if the exported numbers really are the schematic's own,
so:

  * instance names, masters, models, terminal->net binding, length and width all come from the
    read-only readback log (skill/sch3_readback.il). Nothing in this file reads a W/L out of a deck.
  * the accepted deck supplies only the TESTBENCH: the PDK include, the ideal sources, the probe,
    the analyses and the net naming.
  * in --form flat the rebuilt device lines are additionally diffed against the deck's own lines
    (nets, master, count). A schematic that no longer describes the accepted circuit therefore stops
    the run instead of quietly simulating something else. --form hier instead composes the two
    cellviews as sub-circuits, which is what proves each channel keeps its own private gate/body node.

Usage:
  python scripts/sch3_deck_from_oa.py --deck spectre/generated/<accepted>.scs \
      --readback results/evidence/sch3_readback_post_fix.log --form flat \
      --out spectre/generated/sch3_<name>.scs
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sch_parameter_integrity_check import parse_row   # same RD-ROW grammar, one parser
from sch3_golden_extract import CELL_PORTS            # one port order per cell, no second list

ROLES = ("Mcas", "Mout", "Mpass_local", "Mbleed_local", "Mref")
SINK_ROLES = ("Mcas", "Mout", "Mpass_local", "Mbleed_local")
SINK, BIAS = "data_sink_1ch", "data_bias_ref"
INST_RX = re.compile(r"^\s*(\w+)\s*\(\s*([^)]+?)\s*\)\s*(\w+)\s+(.*)$")
NUMBER_RX = re.compile(r"^-?\d+\.?\d*(?:[eE][-+]?\d+)?$")


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def oa_devices(log):
    """cell -> [device dict], straight off the readback: nets by terminal name, sizes resolved."""
    cells, current = {}, None
    for line in read(log).split("\n"):
        if "RD-CELL" in line:
            m = re.search(r'RD-CELL\s+"?[^"/\s]+"?/"?(\w+)"?', line)
            current = m.group(1) if m else None
            cells.setdefault(current, [])
        elif "RD-ROW" in line and current:
            r = parse_row(line)
            l_txt = r.get("num_l", "").strip("()")
            w_txt = r.get("num_w", "").strip("()")
            if not (NUMBER_RX.match(l_txt) and NUMBER_RX.match(w_txt)):
                raise SystemExit("OA_SIZE_UNRESOLVED %s: l=%r w=%r -- refusing to export"
                                 % (r.get("inst"), r.get("num_l"), r.get("num_w")))
            cells[current].append(dict(name=r["inst"], master=r["master_cell"],
                                       model=r["model"], l=l_txt, w=w_txt,
                                       nets=[r.get("D"), r.get("G"), r.get("S"), r.get("B")],
                                       term_names=r.get("terms", "")))
    return cells


def deck_devices(text):
    """The accepted deck's own device lines, grouped by channel suffix: '' is channel 0."""
    groups, order = {}, []
    for line in text.split("\n"):
        m = INST_RX.match(line)
        if not m:
            continue
        name, nets, master, rest = m.group(1), m.group(2).split(), m.group(3), m.group(4)
        role = re.match(r"^(%s)(\d*)$" % "|".join(ROLES), name)
        if not role:
            continue
        suffix = role.group(2)
        attrs = dict(re.findall(r"(\w+)\s*=\s*(\S+)", rest))
        if suffix not in groups:
            groups[suffix] = {}
            order.append(suffix)
        groups[suffix][role.group(1)] = dict(name=name, nets=nets, master=master, attrs=attrs)
    return groups, order


def port_nets_for(grp):
    """Which deck net plays each OA port role, read out of the deck's own device lines.

    The role->terminal index is fixed by circuit semantics (the pass device's gate IS DATA_EN, the
    cascode's drain IS DATA_OUT, ...), so this is a derivation, not a transcription.
    """
    if "Mref" in grp and not (set(grp) & set(SINK_ROLES)):
        return {CELL_PORTS[BIAS][0][0]: grp["Mref"]["nets"][0],
                CELL_PORTS[BIAS][1][0]: grp["Mref"]["nets"][2]}
    return {
        "DATA_EN": grp["Mpass_local"]["nets"][1],
        "DATA_EN_B": grp["Mbleed_local"]["nets"][1],
        "VBIAS_SHARED": grp["Mpass_local"]["nets"][0],
        "VCAS": grp["Mcas"]["nets"][1],
        "DATA_OUT": grp["Mcas"]["nets"][0],
        "VSS": grp["Mout"]["nets"][2],
    }


def internal_nets(suffix):
    """OA-internal net -> deck net for this channel (the deck numbered them, the cell does not)."""
    return {"node_m": "node_m" + suffix, "vbias_ch": "vbias_ch" + suffix}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--readback", required=True)
    ap.add_argument("--form", choices=("flat", "hier"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    text = read(args.deck)
    cells = oa_devices(args.readback)
    groups, order = deck_devices(text)
    fails = []

    sink_devs = dict((d["name"], d) for d in cells.get(SINK, []))
    bias_devs = dict((d["name"], d) for d in cells.get(BIAS, []))
    if len(sink_devs) != 4 or len(bias_devs) != 1:
        fails.append("readback has sink=%d bias=%d, expected 4 and 1"
                     % (len(sink_devs), len(bias_devs)))

    # OA name -> deck net, per channel group, derived from the deck's own device lines. The
    # single-channel deck keeps Mref and the four channel devices in one group (no suffix), the
    # two-channel deck adds a second group suffixed "1".
    mapping = {}
    for suffix in order:
        grp = groups[suffix]
        if not (set(grp) & set(SINK_ROLES)):
            continue
        missing = sorted(set(SINK_ROLES) - set(grp))
        if missing:
            fails.append("deck channel group %r is missing %s" % (suffix, missing))
            continue
        mapping[suffix] = port_nets_for(grp)
        mapping[suffix].update(internal_nets(suffix))
    if "" not in mapping:
        fails.append("no complete channel group found in %s" % args.deck)
    if "Mref" not in groups.get("", {}):
        fails.append("the deck's shared reference device Mref is not in the unsuffixed group")

    def unmap(net, suffix):
        return mapping.get(suffix, {}).get(net, net)

    # ---- rebuild the device lines from OA, then diff them against the deck
    body_flat = []
    for suffix in order:
        grp = groups[suffix]
        for role in ROLES:
            if role not in grp:
                continue
            oa = (bias_devs if role == "Mref" else sink_devs).get(role)
            if oa is None:
                fails.append("OA has no %s" % role)
                continue
            nets = [unmap(n, suffix) for n in oa["nets"]]
            want = grp[role]["nets"]
            if nets != want:
                fails.append("%s%s: OA nets %s != deck nets %s -- schematic and accepted circuit "
                             "are no longer the same wiring" % (role, suffix, nets, want))
            if oa["master"] != grp[role]["master"]:
                fails.append("%s%s: OA master %s != deck master %s"
                             % (role, suffix, oa["master"], grp[role]["master"]))
            # the instance name carries the channel suffix because the deck has one flat namespace
            body_flat.append("%s%s (%s %s %s %s) %s l=%s w=%s"
                             % (role, suffix, nets[0], nets[1], nets[2], nets[3],
                                oa["master"], oa["l"], oa["w"]))

    lines = []
    if args.form == "flat":
        for ln in text.split("\n"):
            m = INST_RX.match(ln)
            if m and re.match(r"^(%s)(\d*)$" % "|".join(ROLES), m.group(1)):
                continue                      # replaced by the OA-derived lines below
            lines.append(ln)
        block = ["", "* ---- devices rebuilt from the OA cellviews by scripts/sch3_deck_from_oa.py ----"]
        block += body_flat
    else:
        block = ["", "* ---- cellviews exported from OA by scripts/sch3_deck_from_oa.py (hier) ----"]
        for cell, devs in ((BIAS, bias_devs), (SINK, sink_devs)):
            ports = [p for p, _d in CELL_PORTS[cell]]
            block.append("subckt %s (%s)" % (cell, " ".join(ports)))
            for name in sorted(devs):
                d = devs[name]
                block.append("  %s (%s %s %s %s) %s l=%s w=%s"
                             % (name, d["nets"][0], d["nets"][1], d["nets"][2], d["nets"][3],
                                d["master"], d["l"], d["w"]))
            block.append("ends %s" % cell)
            block.append("")
        for suffix in sorted(mapping):
            ports = [p for p, _d in CELL_PORTS[SINK]]
            block.append("Xc%s (%s) %s" % (suffix, " ".join(mapping[suffix][p] for p in ports), SINK))
        block.append("Xb (%s %s) %s" % (mapping[""]["VBIAS_SHARED"], mapping[""]["VSS"], BIAS))
        # the channel's gate nodes live inside the cellview now, so they are not top-level nets;
        # they are dropped from the deck's save list rather than guessed at with an unverified
        # hierarchical path. The currents the verdicts use come from the top-level iprobes.
        internal = set()
        for suffix in mapping:
            internal.update(internal_nets(suffix).values())
        lines = []
        for ln in text.split("\n"):
            m = INST_RX.match(ln)
            if m and re.match(r"^(%s)(\d*)$" % "|".join(ROLES), m.group(1)):
                continue
            if ln.startswith("save ") and any(t in internal for t in ln.split()):
                keep = [t for t in ln.split() if t not in internal]
                print("SAVE_LIST_ADJUSTED: %s -> %s" % (ln.strip(), " ".join(keep)))
                ln = " ".join(keep)
            lines.append(ln)
    # put the OA block where the deck's own device block used to start, so the file layout the
    # reviewer already knows is preserved
    idx = len(lines)
    for i, ln in enumerate(lines):
        if ln.startswith("parameters IREF") or ln.startswith("include "):
            idx = i + 1
            break
    out = lines[:idx] + block + [""] + lines[idx:]
    text_out = "\n".join(out) + "\n"
    directory = os.path.dirname(args.out)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(text_out)

    print("DECK_IN: %s" % args.deck)
    print("READBACK: %s" % args.readback)
    print("FORM: %s" % args.form)
    print("CHANNEL_GROUPS: %s" % " ".join("''+empty" if s == "" else s for s in order))
    print("OA_DEVICE_LINES: %d" % len(body_flat))
    for ln in block:
        if ln.strip() and not ln.startswith("*"):
            print("  | %s" % ln)
    kept = [ln for ln in text_out.split("\n")
            if re.match(r"^(Iref|Iout|Ip\d|V[a-z]\w*|dc1|tran1|save|method|options|include|parameters)",
                        ln.strip())]
    print("TESTBENCH_LINES_PASSED_THROUGH: %d" % len(kept))
    for f in fails:
        print("OA_DECK_MISMATCH: %s" % f)
    gate = "PASS" if not fails else "FAIL"
    print("OA_NETLIST_EXPORT: %s" % gate)
    print("OA_NETLIST_SOURCE: OA_DB_READBACK_ONLY (scripts/sch_parameter_integrity_check.py gate "
          "must have passed on the same log)")
    print("DECK_OUT: %s" % args.out)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
