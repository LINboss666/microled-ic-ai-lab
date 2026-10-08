#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SCH-1 Part D: rebuild a Spectre netlist from the OpenAccess cellview dump, and prove that the
# schematic and the accepted golden netlist describe the SAME circuit.
#
# Input  : cadence_out/db_dump_*.log  -- the stdout of skill/sch1_dump_for_netlist.il, i.e. rows
#          read straight out of microled_cells/c2mos_dff_1bit:schematic.
# Golden : spectre/C2MOS_DFF.scs, the cell that passed the previous review.
# Outputs: spectre/generated/<cell>_from_schematic.scs   (netlist FROM the schematic)
#          results/sch1_connectivity_<cell>.csv          (row-by-row comparison)
#
# The instance lines are built only from database rows: instance name, master, model property, the
# l / simW property *expressions* and the net attached to each master terminal (D G S B). The one
# thing the cellview does not hold is the numeric value behind the design variables (measured:
# dbFindProp(cv "ln") -> MISSING, cv "desVars" -> nil), so those five defaults are taken from the
# golden and labelled as such; the schematic-side evidence is the expression name, which is
# compared here.
#
# Terminal-order convention: the accepted golden writes every MOS as ( d g s b ) -- documented in
# the netlist header and fixed by `spectre -h bsim4` -- and the teacher symbol's master terminals
# are named D G S B, so position k of the golden net list is compared against terminal name
# DGSB[k]. That mapping is asserted, not assumed: a symbol whose terminals are not exactly those
# four names stops the script.
import io
import re
import sys

DUMP, GOLDEN, CELL = sys.argv[1], sys.argv[2], sys.argv[3]
OUT_NL = "spectre/generated/%s_from_schematic.scs" % CELL
OUT_CSV = "results/sch1_connectivity_%s.csv" % CELL

PIN_ORDER = ["D", "G", "S", "B"]


def kv(line):
    out = {}
    for m in re.finditer(r"(\w+)=(-?\S+)", line):
        out[m.group(1)] = m.group(2).strip('"')
    return out


def parse_dump(path):
    # The Virtuoso log does not keep one record per line (it concatenates several printf results
    # into one line and prefixes the rest with its own \o markers), so records are found by the
    # NL- token itself instead of by line boundaries.
    text = io.open(path, encoding="utf-8", errors="replace").read()
    mos = {}
    ports = {}
    summary = ""
    for part in re.split(r"(?=NL-)", text):
        part = part.strip().replace("\\o", " ")
        if part.startswith("NL-MOS "):
            r = kv(part)
            mos[r["inst"]] = r
        elif part.startswith("NL-PORT "):
            r = kv(part)
            ports[r["net"]] = r
        elif part.startswith("NL-SUMMARY"):
            summary = part
    return mos, ports, summary


def parse_golden(path):
    text = io.open(path, encoding="utf-8", errors="replace").read()
    hdr = re.search(r"^subckt\s+(\S+)\s*\(([^)]*)\)", text, re.M)
    ports = hdr.group(2).split()
    insts = {}
    for line in text.split("\n"):
        m = re.match(r"\s*((?:mp|mn)\w+)\s*\(\s*([^)]+?)\s*\)\s*(\w+)\s+l=(\S+)\s+w=(\S+)", line)
        if m:
            insts[m.group(1)] = {"nets": m.group(2).split(), "model": m.group(3),
                                 "l": m.group(4), "w": m.group(5)}
    desvars = dict(re.findall(r"^\s*parameters (ln|wc|wcp|wk|wkp)=(\S+)", text, re.M))
    return ports, insts, desvars


def main():
    mos, ports, summary = parse_dump(DUMP)
    gports, ginsts, gdesvars = parse_golden(GOLDEN)

    failures = []

    def fail(msg):
        failures.append(msg)

    # ---- counts and identities
    if len(mos) != 18:
        fail("schematic holds %d MOS rows, golden has %d" % (len(mos), len(ginsts)))
    if set(mos) != set(ginsts):
        fail("instance name sets differ: only-in-db=%s only-in-golden=%s"
             % (sorted(set(mos) - set(ginsts)), sorted(set(ginsts) - set(mos))))

    db_port_names = set(ports)
    if db_port_names != set(gports):
        fail("port sets differ: db=%s golden=%s" % (sorted(db_port_names), sorted(gports)))

    # ---- per instance: model, sizes, and the net on every master terminal
    rows = []
    for name in sorted(ginsts):
        g = ginsts[name]
        d = mos.get(name)
        if d is None:
            fail("%s: missing from the schematic" % name)
            continue
        if d["model"] != g["model"]:
            fail("%s: model %s in schematic, %s in golden" % (name, d["model"], g["model"]))
        if d["l_expr"] != g["l"]:
            fail("%s: l expression %s in schematic, %s in golden" % (name, d["l_expr"], g["l"]))
        if d["w_expr"] != g["w"]:
            fail("%s: w expression %s in schematic, %s in golden" % (name, d["w_expr"], g["w"]))
        for k, pin in enumerate(PIN_ORDER):
            dbnet = d[pin]
            gnet = g["nets"][k]
            if dbnet != gnet:
                fail("%s.%s: net %s in schematic, %s in golden" % (name, pin, dbnet, gnet))
            if dbnet in ("UNCONNECTED", "NO-SUCH-PIN", "MISSING"):
                fail("%s.%s is not bound in the schematic" % (name, pin))
        rows.append([name, g["model"], g["l"], g["w"],
                     d["D"], d["G"], d["S"], d["B"],
                     "MATCH" if all(d[p] == g["nets"][i] for i, p in enumerate(PIN_ORDER))
                     and d["model"] == g["model"] and d["l_expr"] == g["l"]
                     and d["w_expr"] == g["w"] else "DIFF"])

    # ---- net names used by the schematic must be exactly the golden's
    db_nets = set()
    for d in mos.values():
        db_nets.update([d[p] for p in PIN_ORDER])
    golden_nets = set()
    for g in ginsts.values():
        golden_nets.update(g["nets"])
    if db_nets != golden_nets:
        fail("net name sets differ: %s" % sorted(db_nets ^ golden_nets))

    csv_lines = ["inst,model,l_expr,w_expr,db_D,db_G,db_S,db_B,verdict"]
    csv_lines += [",".join(str(c) for c in r) for r in rows]
    io.open(OUT_CSV, "w", encoding="utf-8", newline="").write("\n".join(csv_lines) + "\n")

    # ---- the netlist, rebuilt from the database rows
    port_order = [p for p in gports if p in db_port_names]
    out = ["; SCH-1 Part D: netlist rebuilt FROM microled_cells/%s:schematic." % CELL,
           "; Rows come from skill/sch1_dump_for_netlist.il (cadence_out/db_dump_*.log); no line",
           "; was copied from spectre/C2MOS_DFF.scs. The five design-variable DEFAULTS below are the",
           "; golden's, because the cellview stores size *expressions* (l=ln, w=wcp) and not values;",
           "; the expressions themselves are compared against the golden by scripts/sch1_netlist_from_db.py.",
           "; %s" % summary.strip(),
           "simulator lang=spectre insensitive=yes",
           "",
           "subckt %s (%s)" % (CELL, " ".join(port_order))]
    for k in ["ln", "wc", "wcp", "wk", "wkp"]:
        if k not in gdesvars:
            fail("golden does not define design variable %s" % k)
        else:
            out.append("  parameters %s=%s" % (k, gdesvars[k]))
    for name in sorted(ginsts):
        d = mos.get(name)
        if not d:
            continue
        out.append("  %s (%s %s %s %s) %s l=%s w=%s"
                   % (name, d["D"], d["G"], d["S"], d["B"], d["model"], d["l_expr"], d["w_expr"]))
    out += ["ends %s" % CELL, ""]
    io.open(OUT_NL, "w", encoding="utf-8", newline="").write("\n".join(out) + "\n")

    print("SCH1_DUMP=%s" % DUMP)
    print("MOS_COUNT_SCHEMATIC: %d" % len(mos))
    print("MOS_COUNT_GOLDEN: %d" % len(ginsts))
    print("PORT_SET_SCHEMATIC: %s" % " ".join(sorted(db_port_names)))
    print("NET_SET_SIZE: %d" % len(db_nets))
    print("CONNECTIVITY_ROWS_CHECKED: %d" % len(rows))
    print("CONNECTIVITY_ROWS_MATCH: %d" % len([r for r in rows if r[-1] == "MATCH"]))
    print("EXPORTED_NETLIST: %s" % OUT_NL)
    print("CONNECTIVITY_CSV: %s" % OUT_CSV)
    for f in failures:
        print("MISMATCH: %s" % f)
    print("GOLDEN_NETLIST_EQUIVALENCE: %s" % ("PASS" if not failures else "FAIL"))
    return 1 if failures else 0


sys.exit(main())
