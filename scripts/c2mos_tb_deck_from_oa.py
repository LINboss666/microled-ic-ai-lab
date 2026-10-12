#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build a runnable Spectre deck whose ENTIRE content comes out of the OA testbench cell.

Why this file exists (Task 1 outcome, measured -- see skill/c2mos_tb_native_run.il and
reports/c2mos_tb_native_simulation.md): Cadence's own netlister is not callable on this build from
any batch startup path. asi* is nil, sim*/nl* are nil, and ADE XL will create a session
(axlCreateSession -> "tb_session") but refuses to attach a design to it (axlSetMainSetupDBLCV and
axlNewSetupDBLCV both nil), so there is no setup db, no test, and axlRunSimulation never starts.

The repository's documented fallback for exactly this case is scripts/sch3_deck_from_oa.py, whose
rule is: the OA-to-netlist step may be done by the project ONLY if every number provably came out of
the database. This file obeys that rule:

  * sources, loads, instance names, terminal->net binding and the DUT reference all come from the
    read-only readback log (TBCA-* lines written by skill/c2mos_tb_cdf_audit.il). No stimulus value
    is read out of a deck here.
  * the analysis is the one the frozen golden deck states (tran stop/maxstep and the save list),
    parsed by the builder's own parse_golden(). That is the Task 2 fix: the builder computed
    p["tran"] and never emitted it, and never parsed "save" at all.
  * the only textual substitution is the ground name: the cell's ground net is literally "gnd!"
    (measured: 6 instance terms on it) and Spectre's reference node is 0. The mapping is counted and
    printed; any other net sitting on a source's MINUS pin makes the build refuse.

Component names are Spectre's (vsource / capacitor) because analogLib's own implementation records
componentName vsource for vdc/vpulse and capacitor for cap -- a name lookup against the vendor
dictionary, not a restyle of the schematic.

Usage:
  python scripts/c2mos_tb_deck_from_oa.py \
      --evidence results/evidence/c2mos_tb_cdf_audit.txt \
      --golden spectre/c2mos_ff1_func.scs \
      --out spectre/c2mos_dff_tb_from_oa.scs
"""
from __future__ import print_function

import argparse
import io
import os
import re
import sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from c2mos_tb_build import parse_golden                      # the golden deck's own parser
from c2mos_tb_cdf_check import parse_evidence, to_decimal     # the audit log's own reader

# analogLib CDF name -> the Spectre parameter name that same cell netlists, read off the vendor
# propMapping in the audit (SECTION A of results/evidence/c2mos_tb_cdf_audit.txt).
OA_TO_SPECTRE = {"vdc": "dc", "v1": "val0", "v2": "val1", "per": "period", "td": "delay",
                 "tr": "rise", "tf": "fall", "pw": "width", "srcType": "type", "c": "c"}
GROUND_NET = "gnd!"
REF_NODE = "0"
# the pulse parameters this deck builder is willing to carry, in netlist order
PULSE_ORDER = ("srcType", "v1", "v2", "per", "td", "tr", "tf", "pw")


def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def fmt(v):
    s = "%.9g" % float(v)
    if Decimal(s) != v:
        raise SystemExit("DECK_REFUSE: %r would be rounded by writing %s" % (v, s))
    return s


def value_of(cell, who, oa_name):
    """raw property first (that is the layer the schematic really stores), CDF value second --
    srcType is the documented exception: it is carried by the master default, not the instance"""
    for layer in ("raw", "cdf"):
        got = cell[layer].get(oa_name)
        if got not in (None, ""):
            return got
    raise SystemExit("DECK_REFUSE: %s has no value for %s in either layer" % (who, oa_name))


def number_of(cell, who, oa_name):
    v = to_decimal(value_of(cell, who, oa_name))
    if v is None:
        raise SystemExit("DECK_REFUSE: %s.%s is not a number" % (who, oa_name))
    return fmt(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--golden", default=os.path.join("spectre", "c2mos_ff1_func.scs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--dut-subckt", default="generated/c2mos_dff_1bit_from_oa_readback.scs")
    ap.add_argument("--cell", default="c2mos_dff_tb")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = parse_golden(a.golden)
    gtxt = read(a.golden)
    m_save = re.search(r"^save\s+(.+)$", gtxt, re.M)
    if not m_save:
        raise SystemExit("DECK_REFUSE: the golden deck states no save list")
    save_list = m_save.group(1).split()
    if not p["tran"]:
        raise SystemExit("DECK_REFUSE: the golden deck states no tran")

    insts = parse_evidence(a.evidence)
    srcs, caps, dut, skipped = [], [], None, []
    for nm in sorted(insts):
        master = insts[nm]["master"].replace('"', "")
        if master.endswith("/vdc/symbol"):
            srcs.append(("dc", nm))
        elif master.endswith("/vpulse/symbol"):
            srcs.append(("pulse", nm))
        elif master.endswith("/cap/symbol"):
            caps.append(nm)
        elif master.startswith("microled_cells/"):
            dut = nm
        elif master.startswith("basic/"):
            skipped.append((nm, master, "instTerms unbound"))
        else:
            raise SystemExit("DECK_REFUSE: unexpected master %s on instance %s" % (master, nm))
    if dut is None:
        raise SystemExit("DECK_REFUSE: readback contains no DUT instance")
    if len(srcs) != 4 or len(caps) != 2:
        raise SystemExit("DECK_REFUSE: expected 2 dc + 2 pulse + 2 cap, got %s / %s" % (srcs, caps))
    print("SKIPPED_NON_ELECTRICAL %s" % (skipped,))

    conn = {}
    for nm, cell in insts.items():
        conn[nm] = dict(cell.get("connect", []))

    def term_net(nm, term):
        n = conn[nm].get(term)
        if n is None:
            raise SystemExit("DECK_REFUSE: %s has no %s terminal in the readback" % (nm, term))
        return n

    def ground_mapped(nm, net):
        if net == GROUND_NET:
            return REF_NODE, 1
        if net == REF_NODE:
            return REF_NODE, 0
        raise SystemExit("DECK_REFUSE: %s is tied to net %s, which is neither gnd! nor 0" % (nm, net))

    body, ground_count = [], 0
    for kind, nm in srcs:
        cell = insts[nm]
        plus = term_net(nm, "PLUS")
        minus, k = ground_mapped(nm, term_net(nm, "MINUS"))
        ground_count += k
        if plus == GROUND_NET:
            raise SystemExit("DECK_REFUSE: %s PLUS is on the ground net" % nm)
        if kind == "dc":
            body.append("%s (%s %s) vsource dc=%s" % (nm, plus, minus, number_of(cell, nm, "vdc")))
        else:
            params = []
            for oa in PULSE_ORDER:
                params.append("%s=%s" % (OA_TO_SPECTRE[oa], value_of(cell, nm, oa)))
            body.append("%s (%s %s) vsource %s" % (nm, plus, minus, " ".join(params)))
    for nm in sorted(caps):
        cell = insts[nm]
        plus = term_net(nm, "PLUS")
        minus, k = ground_mapped(nm, term_net(nm, "MINUS"))
        ground_count += k
        body.append("%s (%s %s) capacitor c=%s" % (nm, plus, minus, number_of(cell, nm, "c")))

    ports = p["dut_ports"]
    nets = [term_net(dut, t) for t in ports]
    model = insts[dut]["raw"].get("model")
    if not model:
        raise SystemExit("DECK_REFUSE: the DUT instance carries no model name in the readback")
    body.append("%s (%s) %s" % (dut, " ".join(nets), model))
    body.append("tr1 tran stop=%s maxstep=%s" % (p["tran"][0], p["tran"][1]))
    body.append("save %s" % " ".join(save_list))

    head = ["; c2mos_dff_tb_from_oa.scs -- built from the OA cell microled_cells/%s" % a.cell,
            ";   by scripts/c2mos_tb_deck_from_oa.py; device side comes from the TBCA readback in",
            ";   results/evidence/c2mos_tb_cdf_audit.txt, analysis side is parsed from the frozen",
            ";   golden deck. Nothing in this file was typed in by hand.",
            "; NETLIST_PROVENANCE: OA_READBACK -- Cadence's own netlister is unavailable on this",
            ";   build (NATIVE_NETLIST_BLOCKED, see reports/c2mos_tb_native_simulation.md).",
            ";   This is the project's documented readback route, not a native ADE netlist.",
            "simulator lang=spectre insensitive=yes",
            "global 0",
            "include \"${QODER_PDK_LIB}\" section=tt",
            "include \"%s\"" % a.dut_subckt,
            "parameters T=%s" % fmt(p["T"]),
            "parameters VDDV=%s" % fmt(p["VDDV"])]

    out_txt = "\n".join(head + body) + "\n"
    print("GROUNDED_TERMINALS=%d (%s -> %s)" % (ground_count, GROUND_NET, REF_NODE))
    print("SOURCES=%s CAPS=%s DUT=%s model=%s ports=%s"
          % (" ".join(s[1] for s in srcs), " ".join(sorted(caps)), dut, model, ",".join(ports)))
    print("ANALYSIS tran stop=%s maxstep=%s save=%s" % (p["tran"][0], p["tran"][1], " ".join(save_list)))
    if a.dry_run:
        sys.stdout.write(out_txt)
        print("DRY_RUN_OK")
        return 0
    io.open(a.out, "w", encoding="utf-8", newline="\n").write(out_txt)
    print("DECK_WRITTEN=%s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
