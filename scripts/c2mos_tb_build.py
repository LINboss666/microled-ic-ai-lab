#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 1 builder: create the OA testbench cell microled_cells/c2mos_dff_tb (schematic).

Method, and why it is not a new design:
  * Cadence's own netlist->schematic importer (spiceIn / ASG) is the only proven batch route to a
    real schematic on this build (schCreate is undefined in -nograph; measured), and it is the same
    importer the project already used for c2mos_dff_1bit and the data driver.
  * Every stimulus number is PARSED out of the frozen golden deck spectre/c2mos_ff1_func.scs.
    This file contains no literal T, VDD, delay, width, period, slew or capacitance value of its
    own, and no transistor parameter at all: the DUT is referenced as an existing cell master,
    so nothing about the circuit is restated here.
  * Probed first in the scratch library microled_probe (SPICEIN-24 showed refLibList must also carry
    microled_cells, or the DUT's symbol is not found), before writing into the project library.

Ground-node caveat that this script deliberately keeps visible: ASG renames the netlist node "0"
to "gnd!" and adds an iopin, so the imported cell is a faithful picture of the sources but its
re-exported netlist must map gnd! back to 0 before Spectre sees a reference node. scripts/
c2mos_tb_verify.sh does that mapping and proves the result; nothing here hides it.

Usage: python scripts/c2mos_tb_build.py [--lib microled_cells] [--cell c2mos_dff_tb] [--dry-run]
"""
from __future__ import print_function

import argparse
import os
import re
import subprocess
import sys
import time
from decimal import Decimal

PROJ = os.environ.get("PROJ", "/root/microled_ai_project")
GOLDEN = os.path.join(PROJ, "spectre", "c2mos_ff1_func.scs")
DUT_DEFAULT = "c2mos_dff_1bit"

NUM = r"[-+0-9.eE]+"
# the attribute set the golden deck's pulse sources carry, in the order written out
VPULSE_ATTRS = ("val0", "val1", "period", "delay", "width", "rise", "fall")


def parse_golden(path):
    """Pull the stimulus values out of the frozen deck, keyed by the source instance."""
    txt = io_read(path)
    p = {}
    m = re.search(r"^parameters\s+T\s*=\s*(%s)" % NUM, txt, re.M)
    if not m:
        raise SystemExit("BUILD_REFUSE: golden deck has no `parameters T=`")
    p["T"] = Decimal(m.group(1))
    m = re.search(r"^parameters\s+VDDV\s*=\s*(%s)" % NUM, txt, re.M)
    if not m:
        raise SystemExit("BUILD_REFUSE: golden deck has no `parameters VDDV=`")
    p["VDDV"] = Decimal(m.group(1))
    for name in ("Ck", "Dd"):
        line = re.search(r"^%s\s*\(\s*(\w+)\s+0\s*\)\s*vsource\s+(.*)$" % name, txt, re.M)
        if not line:
            raise SystemExit("BUILD_REFUSE: golden deck has no %s line" % name)
        attrs = dict(kv.split("=", 1) for kv in line.group(2).split())
        p[name] = {"net": line.group(1), "attrs": attrs}
    m = re.search(r"^X1\s*\(([^)]*)\)\s*(\w+)", txt, re.M)
    if not m:
        raise SystemExit("BUILD_REFUSE: golden deck has no X1 DUT line")
    p["dut_ports"] = [x.strip() for x in m.group(1).split()]
    p["dut_cell_in_golden"] = m.group(2)
    for cap in ("Cq", "Cqb"):
        m = re.search(r"^%s\s*\(\s*(\w+)\s+0\s*\)\s*capacitor\s+c=(%s)" % (cap, NUM), txt, re.M)
        if not m:
            raise SystemExit("BUILD_REFUSE: golden deck has no %s line" % cap)
        p[cap] = {"net": m.group(1), "c": Decimal(m.group(2))}
    m = re.search(r"tran\s+stop=(\S+)\s+maxstep=(\S+)", txt)
    p["tran"] = m.groups() if m else ("4.8*T", "1e-4*T")
    return p


def io_read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace")


def as_number(v, p):
    """Evaluate a golden expression like 0.5*T or 2e-7 into an exact Decimal.

    Decimal, not float: 0.35*2e-7 is 6.9999999999999992e-08 in binary but the deck's decimal
    intent is exactly 7e-08, and emitting the binary artifact would be a silent perturbation.
    """
    v = v.strip()
    if re.match(r"^%s$" % NUM, v):
        return Decimal(v)
    if v == "T":
        return p["T"]
    m = re.match(r"^([-+]?[0-9.]+)\*T$", v)
    if m:
        return Decimal(m.group(1)) * p["T"]
    if v == "VDDV":
        return p["VDDV"]
    raise SystemExit("BUILD_REFUSE: cannot resolve golden value %r without inventing one" % v)


def build_deck(p, dut_cell):
    def fmt(x):
        s = "%.9g" % float(x)
        # a rounded number would let a wrong testbench look right, so refuse instead
        if Decimal(s) != x:
            raise SystemExit("BUILD_REFUSE: %s does not round-trip %r" % (s, x))
        return s

    lines = ["simulator lang=spectre insensitive=yes", "global 0"]
    lines.append("Vdd (vdd 0) vdc dc=%s" % fmt(p["VDDV"]))
    lines.append("Vss (vss 0) vdc dc=0")
    for inst in ("Ck", "Dd"):
        s = p[inst]
        a = dict(s["attrs"])
        # the golden deck uses `vsource type=pulse`; analogLib's vpulse IS the pulse source, so
        # `type` has no counterpart here. Anything else unexpected must stop the build rather
        # than be dropped in silence.
        a.pop("type", None)
        unknown = sorted(set(a) - set(VPULSE_ATTRS))
        if unknown:
            raise SystemExit("BUILD_REFUSE: golden %s carries unhandled attribute(s) %s"
                             % (inst, " ".join(unknown)))
        missing = sorted(set(VPULSE_ATTRS) - set(a))
        if missing:
            raise SystemExit("BUILD_REFUSE: golden %s lacks attribute(s) %s" % (inst, " ".join(missing)))
        lines.append("%s (%s 0) vpulse %s" % (
            inst, s["net"],
            " ".join("%s=%s" % (k, fmt(as_number(a[k], p))) for k in VPULSE_ATTRS)))
    lines.append("X1 (%s) %s" % (" ".join(p["dut_ports"]), dut_cell))
    for cap in ("Cq", "Cqb"):
        lines.append("%s (%s 0) cap c=%s" % (cap, p[cap]["net"], fmt(p[cap]["c"])))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default="microled_cells")
    ap.add_argument("--cell", default="c2mos_dff_tb")
    ap.add_argument("--dut", default=DUT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--import", dest="do_import", action="store_true",
                    help="after writing the deck, run spiceIn to create the OA cell")
    a = ap.parse_args()

    p = parse_golden(GOLDEN)
    if p["dut_cell_in_golden"] != DUT_DEFAULT:
        print("BUILD_NOTE: golden X1 master is %s (the netlist-level cell); the OA cell imported "
              "from it is %s" % (p["dut_cell_in_golden"], a.dut))
    deck = os.path.join(PROJ, "spectre", "import", "%s.scs" % a.cell)
    body = build_deck(p, a.dut)
    head = ("; %s.scs -- generated by scripts/c2mos_tb_build.py from the FROZEN golden deck\n"
            "; %s\n; every number above is a parsed golden value; nothing here is chosen afresh.\n"
            % (a.cell, GOLDEN))
    if a.dry_run:
        sys.stdout.write(head + body)
        print("DRY_RUN_OK")
        return 0
    with open(deck, "w") as f:
        f.write(head + body)
    print("IMPORT_DECK=%s" % deck)
    print("GOLDEN_PARSED T=%g VDDV=%g dut=%s caps=%s/%s" % (
        p["T"], p["VDDV"], " ".join(p["dut_ports"]), p["Cq"]["c"], p["Cqb"]["c"]))
    print("SOURCE_PARAMS ck=%s d=%s" % (p["Ck"]["attrs"], p["Dd"]["attrs"]))

    if not a.do_import:
        print("DECK_WRITTEN (no --import given, nothing was created in any library)")
        return 0

    work = os.path.join(PROJ, "cadence_work")
    cell_dir = os.path.join(work, a.lib, a.cell)
    if os.path.exists(cell_dir):
        print("BUILD_REFUSE: %s/%s already exists -- nothing is ever overwritten" % (a.lib, a.cell))
        return 7
    log = os.path.join(work, "logs", "asg_spiceIn_tb_%s.log" % time.strftime("%Y%m%d_%H%M%S"))
    param = os.path.join(work, "asg_in", "%s_param.il" % a.cell)
    if not os.path.isdir(os.path.dirname(param)):
        os.makedirs(os.path.dirname(param))
    # same parameter set scripts/sch3_asg_import.sh uses, with microled_cells added to
    # refLibList (measured: without it SPICEIN-24 cannot find the DUT's symbol view)
    with open(param, "w") as f:
        f.write("spiceInParams = list(nil\n")
        f.write("    'topCell         \"%s\"\n" % a.cell)
        f.write("    'language        \"SPECTRE\"\n")
        f.write("    'netlistFile     \"%s\"\n" % deck)
        f.write("    'outputLib       \"%s\"\n" % a.lib)
        f.write("    'refLibList      \"smic18mmrf analogLib microled_cells\"\n")
        f.write("    'outputViewType  \"schematic\"\n")
        f.write("    'outputViewName  \"schematic\"\n")
        f.write("    'simName         \"spectre\"\n")
        f.write("    'outputSimName   \"spectre\"\n")
        f.write("    'overwriteCells  \"NONE\"\n")
        f.write("    'logFile         \"%s\"\n" % log)
        f.write(")\n")
    env = dict(os.environ)
    env["HOME"] = os.path.join(work, "home")
    rc = subprocess.call(["spiceIn", "-param", param], cwd=work, env=env)
    print("ASG rc=%d" % rc)
    print("ASG_LOG=%s" % log)
    txt = io_read(log) if os.path.exists(log) else ""
    for tag in ("SPICEIN-33", "SPICEIN-54", "SPICEIN-24", "SPICEIN-56", "ERROR"):
        hits = [l for l in txt.split("\n") if tag in l]
        if hits:
            print("%s -> %s" % (tag, hits[-1].strip()[:160]))
    print("CELL_DIR_CREATED=%s (%s)" % (os.path.isdir(cell_dir), cell_dir))
    return 0 if os.path.isdir(os.path.join(cell_dir, "schematic")) else 1


if __name__ == "__main__":
    sys.exit(main())
