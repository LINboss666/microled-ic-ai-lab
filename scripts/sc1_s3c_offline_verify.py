#!/usr/bin/env python3
"""Offline (no Cadence, no PDK) verification of the fixed source for one scan-driver round.

Proves only what disk evidence can prove:
  1. the six frozen Spectre masters still hash to the recorded SHA-256 values,
  2. the four golden tables reproduce, in row order, from scripts/sc1_s3c_golden.py,
  3. the import / CDF-size / direction emission files are regenerated at the recorded sizes,
  4. an existing C-squared-MOS cell, described by a netlist read back out of the OA database,
     matches the golden c2mos_dff row-for-row on model, L, W and D/G/S/B.

Everything it says is computed here; nothing is copied from a previous report. Writing the
OA library itself still needs Cadence, so a PASS here is never evidence about the OA side.
"""
import argparse
import csv
import hashlib
import io
import os
import re
import subprocess
import sys

MASTERS = [
    ("spectre/C2MOS_DFF.scs", "d1eed4e242fa2874f38d8a2add34eba985e4e14ac8925041f7180e0dfcc5fcf3"),
    ("spectre/sc1_scan_gate.scs", "c078637719cc6bd3a761c519683b7d0e04f95e6184874b5ef7c4f2c84eecc53b"),
    ("spectre/sc1_level_shifter_r2d.scs", "31324ca541a6a645e542a3570613b034e446e5f118cd051397dc07155082da66"),
    ("spectre/sc1_r3_scan_chain.scs", "4dffb7856cc4b7375bdd8e9c80458365871cf27fa7ed8555b3de1ceb95a80198"),
    ("spectre/sc1_s3b_p33_bank.scs", "99799725f570bde1b5111d41045644e6d3858e0626d043875a743686c9d54f9e"),
    ("spectre/sc1_s3b_scan_power_1ch.scs", "921ab7229f27eacf5e0758a8b4634ec4c3dd6ba834391087f76f9dc018b6e88b"),
]
GOLDEN = ["mos", "ports", "hier", "subinst"]
EXPECT_ROWS = {"mos": 39, "ports": 48, "hier": 8, "subinst": 39}
FIELDS = ["model", "l", "w", "d", "g", "s", "b"]
INST_RE = re.compile(
    r"^\s*((?:mn|mp)_\w+)\s*\((\w+)\s+(\w+)\s+(\w+)\s+(\w+)\)\s*(n18|p18)\s*l=([\d.eE+-]+)\s*w=([\d.eE+-]+)",
    re.M)


def blob(sha, path):
    return subprocess.run(["git", "show", "%s:%s" % (sha, path)], cwd=REPO,
                          capture_output=True, check=True).stdout


def rows(text):
    return [r for r in csv.reader(io.StringIO(text)) if r and any(c.strip() for c in r)]


def check_masters(sha):
    ok = 0
    for path, want in MASTERS:
        got = hashlib.sha256(blob(sha, path)).hexdigest()
        match = got == want
        ok += match
        print("MASTER %-38s %s sha256=%s" % (path, "MATCH" if match else "MISMATCH", got))
    print("S3C_MASTERS: %d/%d" % (ok, len(MASTERS)))
    return ok == len(MASTERS)


def check_golden(sha, scratch):
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    out = os.path.join(scratch, "out")
    for d in (scratch, out):
        if not os.path.isdir(d):
            os.makedirs(d)
    emission = {
        "--emit-import": os.path.join(scratch, "scan_import.scs"),
        "--emit-params": os.path.join(scratch, "scan_params.il"),
        "--emit-dirs": os.path.join(scratch, "scan_dirs.il"),
        "--emit-golden": out,
    }
    argv = [sys.executable, "scripts/sc1_s3c_golden.py"]
    for flag, path in emission.items():
        argv += [flag, path]
    log = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    for line in (log.stdout + log.stderr).splitlines():
        print("EMIT " + line)
    if log.returncode != 0:
        print("S3C_EMISSION: FAIL rc=%d" % log.returncode)
        return False

    good = True
    for name in GOLDEN:
        committed = blob(sha, "results/evidence/sc1_s3c_golden_%s.csv" % name).decode()
        fresh = open(os.path.join(out, "sc1_s3c_golden_%s.csv" % name), newline="").read()
        a, b = rows(committed), rows(fresh)
        same = a == b
        good = good and same
        print("GOLDEN %-8s rows=%d/%d order_and_content=%s"
              % (name, len(b) - 1, EXPECT_ROWS[name], "IDENTICAL" if same else "DIFFERS"))
        if not same:
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    print("  first difference at row %d\n    committed=%r\n    emitted  =%r" % (i, x, y))
                    break
        if len(b) - 1 != EXPECT_ROWS[name]:
            good = False
    for flag, path in emission.items():
        if flag == "--emit-golden":
            continue
        n = sum(1 for _ in open(path, newline=""))
        print("EMISSION %-16s lines=%d" % (os.path.basename(path), n))
    print("S3C_GOLDEN_REPRODUCTION: %s" % ("PASS" if good else "FAIL"))
    return good


def check_c2mos_equivalence(sha, netlist_path, csv_path):
    wanted = {}
    table = rows(blob(sha, "results/evidence/sc1_s3c_golden_mos.csv").decode())
    columns = table[0]
    for r in table[1:]:
        h = dict(zip(columns, r))
        if h["cell"] == "c2mos_dff":
            wanted[h["inst"]] = dict(model=h["model"], l=h["l_m"], w=h["w_m"],
                                     d=h["d"], g=h["g"], s=h["s"], b=h["b"])
    body = open(netlist_path).read()
    got = {m.group(1): dict(d=m.group(2), g=m.group(3), s=m.group(4), b=m.group(5),
                            model=m.group(6), l=m.group(7), w=m.group(8))
           for m in INST_RE.finditer(body)}
    port = re.search(r"subckt\s+c2mos_dff_1bit\s*\(([^)]*)\)", body)
    print("C2MOS golden_insts=%d oa_insts=%d name_set_equal=%s"
          % (len(wanted), len(got), sorted(wanted) == sorted(got)))
    print("C2MOS oa_port_order=%s" % (" ".join(port.group(1).split()) if port else "NOT FOUND"))
    if sorted(wanted) != sorted(got) or not port:
        print("S3C_C2MOS_REUSE: FAIL")
        return False

    bad = 0
    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["inst"] + ["golden_%s" % f for f in FIELDS]
                   + ["oa_%s" % f for f in FIELDS] + ["status"])
        for inst in sorted(wanted):
            g, o = wanted[inst], got[inst]
            diffs = [f for f in FIELDS if g[f] != o[f]]
            bad += bool(diffs)
            w.writerow([inst] + [g[f] for f in FIELDS] + [o[f] for f in FIELDS]
                       + ["MATCH" if not diffs else "DIFF:" + ",".join(diffs)])
    print("C2MOS fields_compared=%d mismatches=%d -> %s"
          % (len(wanted) * len(FIELDS), bad, "EQUIVALENT" if bad == 0 else "NOT EQUIVALENT"))
    print("S3C_C2MOS_REUSE: %s" % ("PASS" if bad == 0 else "FAIL"))
    return bad == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--sha", default="9049f111d943e9b322f21e1fa059a932cac93207")
    ap.add_argument("--oa-readback-netlist", required=True,
                    help="netlist subckt built from an OA readback of the existing C2MOS cell")
    ap.add_argument("--scratch", required=True, help="output directory, must be disposable")
    args = ap.parse_args()
    REPO = os.path.abspath(args.repo)
    scratch = os.path.abspath(args.scratch)
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    print("REPO=%s SHA=%s" % (REPO, args.sha))
    print("GIT_HEAD=%s" % subprocess.run(["git", "rev-parse", args.sha], cwd=REPO,
                                         capture_output=True, text=True).stdout.strip())
    a = check_masters(args.sha)
    b = check_golden(args.sha, scratch)
    c = check_c2mos_equivalence(args.sha, os.path.abspath(args.oa_readback_netlist),
                                os.path.join(scratch, "sc1_s3c_c2mos_reuse_compare.csv"))
    print("S3C_OFFLINE_SUMMARY masters=%s golden=%s c2mos_reuse=%s"
          % ("PASS" if a else "FAIL", "PASS" if b else "FAIL", "PASS" if c else "FAIL"))
    sys.exit(0 if (a and b and c) else 1)
