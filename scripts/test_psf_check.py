#!/usr/bin/env python3
"""test_psf_check.py -- unit tests for CROSS/FALL in scripts/psf_check.awk.

The checker must not be validated by running it on the C2MOS circuit: a checker and a
circuit can be wrong in agreeing ways. These cases are hand-built synthetic waveforms
with crossings at known, analytically computable times.

Coverage (the independent review asked for exactly these, plus two threshold-boundary
regressions that used to be ambiguous):

  1 already HIGH at t0 and stays HIGH  -> must report NOT FOUND, not "crossing at t0"
  2 standard rising crossing           -> interpolated time
  3 standard falling crossing          -> interpolated time
  4 several crossings                  -> the first one at/after t0, not the earliest
  5 crossing between two samples       -> linear interpolation checked numerically
  6 no crossing at all                 -> explicit not-found, never the last sample
  7 sample sitting exactly on VTH      -> documented edge semantics
  8 ramp touching VTH exactly at a sample -> crossing located at that sample

  python scripts/test_psf_check.py [--write-transcript results/checker_unit_test.txt]
"""

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AWK = os.path.join(ROOT, "scripts", "psf_check.awk")
VDD = 1.8
VTH = 0.5 * VDD          # 0.9 V, the same convention the delay extraction uses

LINE_OK = re.compile(r"^OK\s+(\S+)\s+(\S+)\s+thr=(\S+)\s+t=(\S+)(.*)$")
LINE_FAIL = re.compile(r"^FAIL\s+(\S+)\s+(\S+)\s+thr=(\S+)\s+not-found(.*)$")


def psf(signals, samples):
    """samples: list of (time, {sig: value}) -> minimal PSF-ASCII text."""
    out = ['PSFversion "1.00"', 'PSFANALYSIS_BEGIN  tran', "SWEEP",
           '"time" "sweep" PROP(', '"units" "s"', ')', "TRACE"]
    for s in signals:
        out.append('"%s" "V"' % s)
    out.append("VALUE")
    for t, vals in samples:
        out.append('"time" %.15e' % t)
        for s in signals:
            out.append('"%s" %.15e' % (s, vals[s]))
    out.append("END")
    return "\n".join(out) + "\n"


def ramp(t0, v0, t1, v1, extra=()):
    """two samples forming one edge on signal 'a', plus optional following samples
    given as (time, value) pairs."""
    s = [(t0, {"a": v0}), (t1, {"a": v1})]
    for item in extra:
        t, v = item
        s.append((t, {"a": v}))
    return s


def run_case(name, data, directives, expect_rc, checks):
    """checks: list of (kind, signal, expected_time_or_None) evaluated on the output."""
    d = tempfile.mkdtemp(prefix="psfut_")
    dpath = os.path.join(d, "case.psf")
    spath = os.path.join(d, "case.dirs")
    with open(dpath, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(data)
    with open(spath, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(directives) + "\n")
    p = subprocess.run(("awk", "-f", AWK, spath, dpath),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace")
    rc = p.returncode
    lines = out.strip().splitlines()
    problems = []
    if rc != expect_rc:
        problems.append("exit code %d, expected %d" % (rc, expect_rc))
    for kind, sig, want, tol in checks:
        m_ok = [m for m in (LINE_OK.match(l) for l in lines) if m and m.group(2) == sig]
        m_no = [m for m in (LINE_FAIL.match(l) for l in lines) if m and m.group(2) == sig]
        if want is None:
            if not m_no:
                problems.append("%s %s: expected not-found, got: %s" % (kind, sig, lines))
            if any("t=" in l and sig in l for l in lines):
                problems.append("%s %s: returned a time instead of not-found" % (kind, sig))
            continue
        if not m_ok:
            problems.append("%s %s: expected crossing at %.6gs, got: %s" % (kind, sig, want, lines))
            continue
        got = float(m_ok[0].group(4))
        if abs(got - want) > tol:
            problems.append("%s %s: crossing t=%.12g, expected %.12g (|d|=%.3g > tol %.3g)"
                            % (kind, sig, got, want, abs(got - want), tol))
    verdict = "PASS" if not problems else "FAIL"
    return {"name": name, "verdict": verdict, "problems": problems,
            "output": lines, "rc": rc, "data": data, "dirs": directives}


def main():
    n = 1e-9
    cases = []

    # 1 already high at t0, stays high: the only edge is at 5 ns, i.e. BEFORE t0=15 ns
    cases.append(run_case(
        "already_high_at_t0_must_not_report_crossing_at_t0",
        psf(["a"], ramp(0, 0.0, 10 * n, VDD, [(20 * n, VDD), (30 * n, VDD), (40 * n, VDD)])),
        ["CROSS a %.1f %.9g" % (VTH, 15 * n)],
        1, [("CROSS", "a", None, 0)]))

    # 2 standard rising crossing: linear ramp 0 -> 1.8 over 10 ns crosses 0.9 at 5 ns
    cases.append(run_case(
        "standard_rising_crossing",
        psf(["a"], ramp(0, 0.0, 10 * n, VDD)),
        ["CROSS a %.1f 0" % VTH],
        0, [("CROSS", "a", 5 * n, 1e-18)]))

    # 3 standard falling crossing
    cases.append(run_case(
        "standard_falling_crossing",
        psf(["a"], ramp(0, VDD, 10 * n, 0.0)),
        ["FALL a %.1f 0" % VTH],
        0, [("FALL", "a", 5 * n, 1e-18)]))

    # 4 several crossings, t0 past the first one -> must report 25 ns, not 5 ns
    cases.append(run_case(
        "multiple_crossings_first_after_t0",
        psf(["a"], [(0, {"a": 0.0}), (10 * n, {"a": VDD}), (20 * n, {"a": 0.0}),
                    (30 * n, {"a": VDD}), (40 * n, {"a": VDD})]),
        ["CROSS a %.1f %.9g" % (VTH, 20 * n)],
        0, [("CROSS", "a", 25 * n, 1e-18)]))

    # 5 interpolation between two arbitrary samples: 0.3 -> 1.5 over 10 ns, VTH 0.9
    #    t = 0 + (0.9-0.3)/(1.5-0.3)*10 ns = 5 ns ; second point: 0.0 -> 1.8, VTH 0.45
    cases.append(run_case(
        "interpolation_between_two_samples",
        psf(["a", "b"], [(0, {"a": 0.3, "b": 0.0}), (10 * n, {"a": 1.5, "b": 1.8}),
                          (20 * n, {"a": 1.5, "b": 1.8})]),
        ["CROSS a %.1f 0" % VTH, "CROSS b %.2f 0" % 0.45],
        0, [("CROSS", "a", 5 * n, 1e-18), ("CROSS", "b", 2.5 * n, 1e-18)]))

    # 6 no crossing at all
    cases.append(run_case(
        "no_crossing_returns_not_found",
        psf(["a", "b"], [(t, {"a": 0.5, "b": VDD}) for t in
                         (0, 10 * n, 20 * n, 30 * n, 40 * n)]),
        ["CROSS a %.1f 0" % VTH, "FALL b %.1f 0" % VTH],
        1, [("CROSS", "a", None, 0), ("FALL", "b", None, 0)]))

    # 7 sample sitting exactly on the threshold then rising: edge is at t=0 by
    #    v_prev <= VTH and v_now > VTH -- pinned so the semantics cannot drift
    cases.append(run_case(
        "sample_exactly_on_threshold_then_rising",
        psf(["a"], ramp(0, VTH, 10 * n, VDD)),
        ["CROSS a %.1f 0" % VTH],
        0, [("CROSS", "a", 0.0, 1e-18)]))

    # 8 ramp touching VTH exactly at a sample: the crossing is at that sample
    cases.append(run_case(
        "ramp_touching_threshold_at_a_sample",
        psf(["a"], [(0, {"a": 0.0}), (10 * n, {"a": VTH}), (20 * n, {"a": VDD})]),
        ["CROSS a %.1f 0" % VTH],
        0, [("CROSS", "a", 10 * n, 1e-18)]))

    # 9 ASSERT semantics stay intact (regression guard for the rewrite)
    cases.append(run_case(
        "assert_window_still_counts_violations",
        psf(["a"], [(t, {"a": 1.7}) for t in (0, 10 * n, 20 * n, 30 * n)] +
                  [(40 * n, {"a": 1.0})]),
        ["ASSERT a 0 %.9g gt 1.5" % (40 * n)],
        1, []))

    failed = [c for c in cases if c["verdict"] == "FAIL"]
    transcript = ["# synthetic unit tests for scripts/psf_check.awk CROSS/FALL/ASSERT",
                  "# generated by scripts/test_psf_check.py -- datasets are hand-built,",
                  "# NOT simulated from the DUT, and every expected time is analytic.",
                  "VTH = %.3f V (= 0.5 * VDD = %.3f)" % (VTH, VDD), ""]
    for c in cases:
        transcript.append("== %s : %s" % (c["name"], c["verdict"]))
        transcript.append("   directives : " + " | ".join(c["dirs"]))
        for l in c["output"]:
            transcript.append("   | " + l)
        for p in c["problems"]:
            transcript.append("   PROBLEM " + p)
        transcript.append("")
    body = "\n".join(transcript)
    print(body)
    if "--write-transcript" in sys.argv:
        out = sys.argv[sys.argv.index("--write-transcript") + 1]
        with open(os.path.join(ROOT, out), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        print("transcript -> %s" % out)
    print("cases=%d failed=%d" % (len(cases), len(failed)))
    print("CROSSING_CHECKER_UNIT_TEST: %s" % ("PASS" if not failed else "FAIL"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
