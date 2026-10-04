#!/usr/bin/env python3
"""export_results.py -- turn the raw checker output into small, reviewable numbers.

The PSF databases stay on the simulation host (tens of MB, and a reviewer cannot read
them in a browser). What belongs in the repository and in a review bundle is the
extracted verdict per assertion:

  results/c2mos_ff1_levels.csv       one row per level window: signal, [t0,t1], op,
                                     limit, samples n, min, max, verdict
  results/c2mos_shift3_levels.csv    same for the 3-stage chain
  results/c2mos_delays.csv           clk->Q per measurement, per run
  results/margin_setup.csv           margin_ns, q_min, q_max, verdict
  results/margin_hold.csv            same for hold
  results/summary.json               tokens, counts, boundary brackets

Inputs are the pulled checker transcripts in results/evidence/ plus the generated
netlists in spectre/generated/ (which carry the exact per-margin data edge times).

  python scripts/export_results.py
"""

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "results", "evidence")
GEN = os.path.join(ROOT, "spectre", "generated")
OUT = os.path.join(ROOT, "results")

ASSERT_RX = re.compile(
    r"^(?P<verdict>OK|FAIL)\s+ASSERT\s+(?P<sig>\S+)\s+\[(?P<t0>[^,]+),(?P<t1>[^\]]+)\]\s+"
    r"(?P<op>gt|lt)\s+(?P<lim>\S+)\s+n=(?P<n>\d+)\s+min=(?P<mn>\S+)\s+max=(?P<mx>\S+)"
    r"(?:\s+viol=(?P<viol>\d+))?", re.M)
CROSS_RX = re.compile(
    r"^(?P<verdict>OK|FAIL)\s+(?P<kind>CROSS|FALL)\s+(?P<sig>\S+)\s+thr=(?P<thr>\S+)\s+"
    r"t=(?P<t>\S+)(?:\s+t0=(?P<t0>\S+))?", re.M)
# The label may itself contain '=' (e.g. "clk->Q rise (edge after t0=2.40T)"), so the
# label part must not exclude '='; the value is anchored on the " = <number> s" shape.
DELAY_RX = re.compile(
    r"^\s*DELAY\s+(?P<label>.+?)\s*=\s*(?P<val>[0-9][0-9.eE+-]*)\s*s"
    r"(?:\s*=\s*(?P<pct>[0-9.eE+-]+)%\s*of T)?", re.M)
DLINE_RX = re.compile(r"^D(\d+)\s+\(d\d+ 0\) vsource .*?delay=(\S+) width=(\S+)", re.M)
TOKEN_RX = re.compile(r"^(C2MOS_[A-Z0-9_]+|MARGIN_SWEEP\[\w+\]|SHIFT_UNIT_CHECK\[\w+\])"
                      r"(?:\[\w+\])?: (PASS|FAIL|DONE)", re.M)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def parse_asserts(text):
    return [m.groupdict() for m in ASSERT_RX.finditer(text)]


def parse_crosses(text):
    return [m.groupdict() for m in CROSS_RX.finditer(text)]


def write_rows(name, header, rows):
    p = os.path.join(OUT, name)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print("wrote %-34s rows=%d" % (name, len(rows)))
    return p, rows


def levels_csv(pattern, outname):
    rows = []
    for fn in sorted(os.listdir(EV)):
        if not re.match(pattern, fn):
            continue
        for m in parse_asserts(read(os.path.join(EV, fn))):
            rows.append([fn, m["sig"], m["t0"], m["t1"], m["op"], m["lim"],
                         m["n"], m["mn"], m["mx"], m["verdict"], m.get("viol") or "0"])
    return write_rows(outname, ["evidence_file", "signal", "t0_s", "t1_s", "op", "limit",
                                 "samples", "min_V", "max_V", "verdict", "violations"], rows)


def delays_csv():
    rows = []
    for fn in sorted(os.listdir(EV)):
        if not fn.endswith(".txt") and not fn.endswith(".out"):
            continue
        for m in DELAY_RX.finditer(read(os.path.join(EV, fn))):
            rows.append([fn, m.group("label").strip(), m.group("val"),
                         m.group("pct") or ""])
    return write_rows("c2mos_delays.csv",
                      ["evidence_file", "measurement", "seconds", "percent_of_T"], rows)


def margin_csv(mode):
    """margin_ns, q_min_V, q_max_V, verdict -- joined by directive order."""
    ap = os.path.join(EV, "margin_assert_%s.txt" % mode)
    gp = os.path.join(GEN, "margin_%s.scs" % mode)
    if not (os.path.exists(ap) and os.path.exists(gp)):
        print("skip margin_%s (missing %s or %s)" % (mode, ap, gp))
        return None, []
    edges = {}
    for line in read(gp).splitlines():
        m = DLINE_RX.match(line)
        if m:
            d, w = float(m.group(2)), float(m.group(3))
            edges[int(m.group(1))] = d + w if mode == "hold" else d
    tested = 2.5 * 2e-7          # the third rising clock edge, T = 200 ns
    rows = []
    for i, m in enumerate(parse_asserts(read(ap))):
        edge = edges.get(i)
        if edge is None:
            continue
        margin_ns = (edge - tested) if mode == "hold" else (tested - edge)
        rows.append(["%.3f" % (margin_ns * 1e9), m["mn"], m["mx"], m["verdict"],
                     m["sig"], "%.9g" % edge])
    return write_rows("margin_%s.csv" % mode,
                      ["margin_ns", "q_min_V", "q_max_V", "assert_verdict",
                       "signal", "data_edge_s"], rows)


def summary(tokens):
    out = {}
    for fn in sorted(os.listdir(EV)):
        if not fn.endswith(".out"):
            continue
        for m in TOKEN_RX.finditer(read(os.path.join(EV, fn))):
            out[m.group(0)] = m.group(2)
    out.update(tokens)
    p = os.path.join(OUT, "summary.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print("wrote summary.json keys=%d" % len(out))
    return p


def margin_tables():
    """Aggregate the measured, per-slew margin CSVs written by c2mos_margin.sh.

    Those CSVs already carry the threshold-to-threshold margin column, so the bracket
    here is a statement about measured crossings, not about the delay knob of a source.
    """
    out = {}
    for fn in sorted(os.listdir(OUT)):
        m = re.match(r"margin_(setup|hold)_(s[0-9.eE-]+)\.csv$", fn)
        if not m:
            continue
        mode, tag = m.group(1), m.group(2)
        with open(os.path.join(OUT, fn), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        col = "setup_margin_ns" if mode == "setup" else "hold_margin_ns"
        ok = [float(r[col]) for r in rows if r["level_verdict"] == "PASS"
              and re.match(r"^-?[0-9.]+$", r[col] or "")]
        bad = [float(r[col]) for r in rows if r["level_verdict"] == "FAIL"
               and re.match(r"^-?[0-9.]+$", r[col] or "")]
        out["%s@%s" % (mode, tag)] = {
            "points": len(rows),
            "working_margin_min_ns": min(ok) if ok else None,
            "working_margin_max_ns": max(ok) if ok else None,
            "failing_margin_min_ns": min(bad) if bad else None,
            "failing_margin_max_ns": max(bad) if bad else None,
            "boundary_found": bool(ok and bad),
        }
    return out


def main():
    if not os.path.isdir(EV):
        print("FATAL: %s missing (pull the checker output from the guest first)" % EV)
        return 8
    ff1, ff1_rows = levels_csv(r"c2mos_assert_ff1_.*\.txt", "c2mos_ff1_levels.csv")
    sh3, sh3_rows = levels_csv(r"c2mos_assert_shift3_.*\.txt", "c2mos_shift3_levels.csv")
    delays_csv()
    for p in (margin_csv("setup"), margin_csv("hold")):      # legacy pre-fix transcripts
        if p and p[1]:
            with open(p[0], "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["note"])
                w.writerow(["superseded: source-delay based table produced by the OLD"
                            " checker; the measured per-slew tables live in"
                            " results/margin_<mode>_s<slew>.csv"])
    extra = {}
    for rows, name in ((ff1_rows, "ff1_windows"), (sh3_rows, "shift3_windows")):
        extra[name] = {"total": len(rows),
                       "failed": sum(1 for r in rows if r[9] == "FAIL")}
    extra["margin_measured"] = margin_tables()
    extra["margin_legacy_note"] = ("results/margin_setup.csv and results/margin_hold.csv"
                                   " are marked superseded: they were derived from the"
                                   " source-delay knob by the pre-fix checker")
    summary(extra)
    print("EXPORT_RESULTS: DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
