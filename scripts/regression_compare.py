#!/usr/bin/env python3
"""regression_compare.py -- did fixing the checker change the reported clk->Q?

A checker rewrite must not silently move the numbers. Every clk->Q measurement taken
BEFORE the CROSS/FALL fix (results/c2mos_delays.csv, produced by the old
"first sample past the threshold" rule) is paired with the same measurement taken AFTER
the fix (new edge-interpolated values) and the difference is compared against the
transient maxstep that produced them: a difference within one integration step is
print resolution, anything larger is a real change and has to be explained.

  python scripts/regression_compare.py \
      --old results/c2mos_delays.csv \
      --new results/evidence/c2mos_delays_ff1_rev1_1.txt \
      --new results/evidence/c2mos_delays_shift3_rev1_1.txt \
      --new results/evidence/c2mos_delays_shift3_revnom_1.txt

Exit 0 = every pair agrees within maxstep (C2MOS_FUNCTION_REGRESSION: PASS).
"""

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# old rows: "clk->Q fall (edge after t0=1.40T)" / "FF0 clk->Q (rise)"
OLD_ROW = re.compile(r"^(?P<file>[^,]+),(?P<meas>[^,]+),(?P<val>[0-9.eE+-]+)")
# new rows, single-FF: TIMING lines
NEW_TIMING = re.compile(r"TIMING edge=(?P<edge>[0-9.]+)T kind=(?P<kind>rise|fall).*"
                        r"CLK50_to_Q50=(?P<val>[0-9.eE+-]+)")
# new rows, chain: DELAY lines
NEW_DELAY = re.compile(r"DELAY\s+FF(?P<ff>\d) clk->Q \(rise\) = (?P<val>[0-9.eE+-]+)")
# which clock period each tag was run at, so maxstep = 1e-4 * T is derived not guessed
TAG_T = {"envtest": 2e-7, "rev1": 2e-7, "envnominal": 9.765625e-6, "revnom": 9.765625e-6}
# the before/after pairs: same netlist, same period, only the checker changed
PAIRS = [("envtest", "rev1"), ("envnominal", "revnom")]


def key_of_ff1(edge, kind):
    return "clk->Q %s (edge after t0=%sT)" % (kind, edge)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", action="append", default=[])
    args = ap.parse_args()

    old = {}
    with open(os.path.join(ROOT, args.old), encoding="utf-8") as fh:
        for line in fh:
            m = OLD_ROW.match(line.strip())
            if not m or m.group("meas").startswith("measurement"):
                continue
            tag = next((t for t in TAG_T if "_%s_" % t in m.group("file") or
                        m.group("file").endswith("_%s.txt" % t)), None)
            if tag is None:
                continue
            old.setdefault(tag, {})[m.group("meas").strip()] = (float(m.group("val")),
                                                                TAG_T[tag])
    print("old baseline file : %s  groups=%s" % (args.old, sorted(old)))
    for tag, rows in sorted(old.items()):
        print("   %s: %d measurements (T=%g s, maxstep=%g s)"
              % (tag, len(rows), TAG_T[tag], 1e-4 * TAG_T[tag]))

    pairs = {}
    for path in args.new:
        p = os.path.join(ROOT, path)
        if not os.path.exists(p):
            print("MISSING new evidence file: %s" % path)
            return 1
        tag = next((t for t in TAG_T if "_%s_" % t in os.path.basename(p)), None)
        if tag is None:
            print("cannot map %s to a clock period" % path)
            return 1
        body = open(p, encoding="utf-8", errors="replace").read()
        for m in NEW_TIMING.finditer(body):
            pairs.setdefault(tag, {})[key_of_ff1(m.group("edge"), m.group("kind"))] = \
                float(m.group("val"))
        for m in NEW_DELAY.finditer(body):
            pairs.setdefault(tag, {})["FF%s clk->Q (rise)" % m.group("ff")] = \
                float(m.group("val"))

    worst = 0.0
    rows = 0
    bad = []
    print("")
    print("%-38s %12s %12s %12s %10s %s" %
          ("measurement", "old_s", "new_s", "delta_s", "maxstep", "verdict"))
    for old_tag, new_tag in PAIRS:
        if old_tag not in old:
            bad.append("no old baseline for tag %s" % old_tag)
            continue
        if new_tag not in pairs:
            bad.append("no new evidence for tag %s" % new_tag)
            continue
        T = TAG_T[old_tag]
        ms = 1e-4 * T
        for key in sorted(pairs[new_tag]):
            if key not in old[old_tag]:
                bad.append("no old counterpart for %s (%s)" % (key, old_tag))
                continue
            oldv, _ = old[old_tag][key]
            newv = pairs[new_tag][key]
            d = abs(newv - oldv)
            worst = max(worst, d)
            rows += 1
            ok = d <= ms
            if not ok:
                bad.append("%s (%s): |%.4g-%.4g|=%.3g > maxstep %.3g"
                           % (key, old_tag, newv, oldv, d, ms))
            print("%-38s %12.5g %12.5g %12.3g %10.3g %s" %
                  (key, oldv, newv, d, ms, "ok" if ok else "TOO LARGE"))

    print("")
    print("compared=%d  worst|delta|=%.3g s" % (rows, worst))
    for b in bad:
        print("PROBLEM " + b)
    if bad:
        print("C2MOS_FUNCTION_REGRESSION: FAIL")
        return 1
    print("C2MOS_FUNCTION_REGRESSION: PASS")
    print("  (every clk->Q moved by at most one transient step, i.e. the checker fix")
    print("   changed where the sample lands, not what the cell does)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
