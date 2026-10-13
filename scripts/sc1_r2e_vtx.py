#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E measurement helper: the extreme of a DIFFERENCE of two saved nodes at the SAME sample.

    sc1_r2e_vtx.py --data FILE --a NODE [--b NODE] [--t0 T --t1 T] [--mode max|min]
                   [--require-n K] [--quiet]
    sc1_r2e_vtx.py --selftest                       offline, synthetic files only

Why it exists: scripts/sc1_read_psf.py aggregates one signal at a time, while a MOS stress voltage is
a difference of two node voltages at the SAME instant (VGS = Vg - Vs). Taking each node's window min
and max separately pairs instants that never coexisted and can invent a stress that never happened.

R2E1 rule -- the review showed the second, lenient parser was the defect, not the arithmetic:

  * this tool no longer reads psfascii itself. It calls the audited sc1_read_psf.parse(), which
    already refuses a non-finite value, a duplicate signal inside one group, a value row before the
    first axis row, a file ending inside an unfinished group, and any group whose signal set differs
    from group 0;
  * parse() does NOT validate the whole time axis, so that is added here and fails closed: the axis
    must be `time`, and times must be strictly increasing (a duplicate or a reversed axis is
    BAD_AXIS, never a certified value);
  * every sample inside the window must carry BOTH signals and their difference must be finite;
  * unknown mode, non-numeric or reversed window, empty/too-short window and a missing signal each
    exit non-zero and print no number.

Tie-break policy for equal extremes: the FIRST sample in file order that reaches the extreme is
reported. Values print with the same 6 significant digits the audited reader uses, so comparison
bandwidth stay explicit rather than vague.

Exit codes follow sc1_read_psf.py: 0 value printed, 2 no data file, 3 no such signal, 4 not enough
samples in the window, 5 bad numeric / non-finite difference, 7 truncated or inconsistent groups,
8 bad axis, 9 bad usage. Output: '<value>\\t<time at the extreme>'.
"""
from __future__ import print_function

import optparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc1_read_psf as RD                # audited parser; reused rather than re-implemented

MODES = ('max', 'min')


def strict_load(path):
    """-> (groups, axis, exit_code, message): the audited parse, then the caller-side axis rules."""
    if not path or not os.path.isfile(path):
        return None, None, 2, 'NO_DATA_FILE %s' % path
    try:
        groups, axis = RD.parse(path)
    except ValueError as e:
        txt = str(e)
        code = 7 if txt.startswith('TRUNCATED') else (8 if txt.startswith('BAD_AXIS') else 5)
        return None, None, code, txt
    if axis != 'time':
        return None, None, 8, 'BAD_AXIS axis=%r, this tool only reads transient time axes' % (axis,)
    prev = None
    for i, g in enumerate(groups):
        t = g[axis]
        if prev is not None:
            if t == prev:
                return None, None, 8, 'BAD_AXIS duplicate time %.9g s at group %d' % (t, i)
            if t < prev:
                return None, None, 8, ('BAD_AXIS time not strictly increasing at group %d '
                                       '(%.9g -> %.9g)' % (i, prev, t))
        prev = t
    return groups, axis, 0, ''


def extreme(groups, axis, a, b, mode, lo, hi, need):
    """-> (exit_code, message, (value, time)) in one file-order pass; the earliest extreme wins ties"""
    names = set(groups[0].keys())
    for s in (a, b):
        if s and s not in names:
            return 3, 'NO_SIGNAL %s (have: %s)' % (s, ','.join(sorted(names)[:40])), None
    picks = []
    for i, g in enumerate(groups):
        t = g[axis]
        if t < lo or t > hi:
            continue
        if a not in g or (b and b not in g):
            return 7, ('TRUNCATED group %d at t=%.9g s lacks one of %s/%s inside the window'
                       % (i, t, a, b or '-')), None
        d = g[a] - (g[b] if b else 0.0)
        if not RD.finite(d):
            return 5, 'BAD_NUMERIC non-finite difference at group %d t=%.9g s' % (i, t), None
        picks.append((d, t))
    if len(picks) < need:
        return 4, 'TOO_FEW samples=%d need=%d in window' % (len(picks), need), None
    best = picks[0]
    for cand in picks[1:]:
        if (cand[0] > best[0]) if mode == 'max' else (cand[0] < best[0]):
            best = cand
    return 0, '', best


def main():
    op = optparse.OptionParser()
    op.add_option('--data')
    op.add_option('--a')
    op.add_option('--b')
    op.add_option('--t0')
    op.add_option('--t1')
    op.add_option('--mode', default='max')
    op.add_option('--require-n', default='2')
    op.add_option('--quiet', action='store_true')
    o, _ = op.parse_args()
    if not o.data or not o.a:
        print('BAD_USAGE: --data and --a are required')
        return 9
    if o.mode not in MODES:
        print('BAD_USAGE unknown mode %r (have: %s)' % (o.mode, ','.join(MODES)))
        return 9
    try:
        need = int(o.require_n)
    except ValueError:
        print('BAD_USAGE --require-n must be an integer, got %r' % o.require_n)
        return 9
    if need < 2:
        # one point is not a window; the audited reader refuses too few samples and so does this
        need = 2
    try:
        lo = RD.qty(o.t0) if o.t0 else -1e30
        hi = RD.qty(o.t1) if o.t1 else 1e30
    except ValueError as e:
        print('BAD_NUMERIC %s' % e)
        return 5
    if hi < lo:
        print('BAD_NUMERIC window reversed t0=%s > t1=%s' % (o.t0, o.t1))
        return 5

    groups, axis, code, msg = strict_load(o.data)
    if code:
        print(msg)
        return code
    code, msg, best = extreme(groups, axis, o.a, o.b, o.mode, lo, hi, need)
    if code:
        print(msg)
        return code
    if not o.quiet:
        print('window %.9g..%.9g s, %d groups, %s of (%s%s), the earliest sample at the extreme wins '
              'ties' % (lo, hi, len(groups), o.mode, o.a,
                        (' - ' + o.b) if o.b else ''), file=sys.stderr)
    print('%.6g\t%.6g' % (best[0], best[1]))
    return 0


# ------------------------------------------------------------------ offline self test
HDR_T = ['HEADER', '"simulator" "spectre"', 'SWEEP', '"time" "sweep"', 'TRACE', '"a" "V"', '"b" "V"']

# (name, header, value lines, args, wanted exit code, wanted text). The bad-data list is exactly the
# one the R2E1 review reproduced: skipping an incomplete group must never still print a value.
BAD_CASES = [
    ('middle group missing b',
     ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 1e-9', '"a" 100',
      '"time" 2e-9', '"a" 1', '"b" 0', 'END'], 7, 'TRUNCATED'),
    ('NaN value',
     ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 1e-9', '"a" nan', '"b" 0', 'END'],
     5, 'BAD_NUMERIC'),
    ('Inf value',
     ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 1e-9', '"a" inf', '"b" 0', 'END'],
     5, 'BAD_NUMERIC'),
    ('no END, file stops inside a group',
     ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 1e-9', '"a" 1', '"b" 1'], 7, 'TRUNCATED'),
    ('duplicate time',
     ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 0', '"a" 1', '"b" 0',
      '"time" 1e-9', '"a" 2', '"b" 0', 'END'], 8, 'duplicate time'),
    ('reversed time axis',
     ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 2e-9', '"a" 2', '"b" 0',
      '"time" 1e-9', '"a" 1', '"b" 0', 'END'], 8, 'not strictly increasing'),
    ('non-time axis', ['VALUE', '"dc" 0', '"a" 0', '"b" 0', '"dc" 1', '"a" 1', '"b" 0', 'END'],
     8, 'BAD_AXIS'),
]
GOOD_CASES = [
    ('max reports the difference and the instant it occurred',
     ['VALUE', '"time" 0', '"a" 1', '"b" 1', '"time" 1e-9', '"a" 2', '"b" 1', 'END'],
     ['--a', 'a', '--b', 'b', '--mode', 'max'], 0, '1\t1e-09'),
    ('min reports the value and its own instant',
     ['VALUE', '"time" 0', '"a" 3.3', '"b" 0', '"time" 1e-9', '"a" 0', '"b" 1.8',
      '"time" 2e-9', '"a" 3.3', '"b" 1.8', 'END'],
     ['--a', 'a', '--b', 'b', '--mode', 'min'], 0, '-1.8\t1e-09'),
    ('window keeps its inclusive bounds and picks inside them',
     ['VALUE', '"time" 0', '"a" 0.0', '"b" 1.8', '"time" 1e-9', '"a" 1.8', '"b" 0.0',
      '"time" 2e-9', '"a" 0.9', '"b" 0.9', 'END'],
     ['--a', 'b', '--b', 'a', '--mode', 'max', '--t0', '1n', '--t1', '2n'], 0, '0\t2e-09'),
    ('equal extremes take the earliest sample',
     ['VALUE', '"time" 0', '"a" 5', '"b" 0', '"time" 1e-9', '"a" 5', '"b" 0',
      '"time" 2e-9', '"a" 1', '"b" 0', 'END'],
     ['--a', 'a', '--b', 'b', '--mode', 'max'], 0, '5\t0'),
]
USAGE_CASES = [
    ('unknown mode refused', ['--mode', 'mean'], 9, 'unknown mode'),
    ('reversed window refused', ['--t0', '2n', '--t1', '1n'], 5, 'reversed'),
    ('window with too few samples', ['--t0', '5n', '--t1', '6n'], 4, 'TOO_FEW'),
    ('unknown signal names itself', ['--b', 'nope'], 3, 'NO_SIGNAL'),
    ('absent data file', ['--data', '__absent__'], 2, 'NO_DATA_FILE'),
]


def selftest():
    """Synthetic files only, no simulator. Every case asserts the REAL subprocess exit code and the
    expected value+time or the specific refusal reason -- a crash or an unfounded 0 is a failure."""
    d = os.path.join(os.environ.get('TMP', '/tmp'), 'sc1_r2e_vtx_selftest1')
    if not os.path.isdir(d):
        os.makedirs(d)
    me = os.path.abspath(__file__)
    good_vals = ['VALUE', '"time" 0', '"a" 0', '"b" 0', '"time" 1e-9', '"a" 1', '"b" 0', 'END']

    def run(path, args):
        proc = subprocess.Popen([sys.executable, me, '--data', path] + args + ['--quiet'],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        return proc.returncode, out.decode('utf-8', 'replace').strip()

    fails = 0
    n = 0
    for name, vals, args, want_rc, want_txt in GOOD_CASES:
        p = os.path.join(d, 'good_%d.psf' % n)
        with open(p, 'wb') as f:
            f.write(('\n'.join(HDR_T + vals) + '\n').encode('utf-8'))
        rc, out = run(p, args)
        hit = rc == want_rc and want_txt in out
        print('%-44s want(%s,%r) got(%s,%r) %s' % (name, want_rc, want_txt, rc, out[:26],
                                                   'PASS' if hit else 'FAIL'))
        fails += 0 if hit else 1
        n += 1
    for name, vals, want_rc, want_txt in BAD_CASES:
        hdr = HDR_T if want_txt != 'BAD_AXIS' else \
            ['HEADER', 'SWEEP', '"dc" "sweep"', 'TRACE', '"a" "V"', '"b" "V"']
        p = os.path.join(d, 'bad_%d.psf' % n)
        with open(p, 'wb') as f:
            f.write(('\n'.join(hdr + vals) + '\n').encode('utf-8'))
        rc, out = run(p, ['--a', 'a', '--b', 'b', '--mode', 'max'])
        hit = rc == want_rc and want_txt in out
        print('%-44s want(%s,%r) got(%s,%r) %s' % (name, want_rc, want_txt, rc, out[:26],
                                                   'PASS' if hit else 'FAIL'))
        fails += 0 if hit else 1
        n += 1
    base = os.path.join(d, 'usage.psf')
    with open(base, 'wb') as f:
        f.write(('\n'.join(HDR_T + good_vals) + '\n').encode('utf-8'))
    for name, args, want_rc, want_txt in USAGE_CASES:
        a = list(args)
        path = base
        if '--data' in a:
            a = [x for x in a if x != '--data' and x != '__absent__']
            path = os.path.join(d, 'does_not_exist.psf')
        rc, out = run(path, ['--a', 'a', '--b', 'b'] + a)
        hit = rc == want_rc and want_txt in out
        print('%-44s want(%s,%r) got(%s,%r) %s' % (name, want_rc, want_txt, rc, out[:26],
                                                   'PASS' if hit else 'FAIL'))
        fails += 0 if hit else 1
    total = len(GOOD_CASES) + len(BAD_CASES) + len(USAGE_CASES)
    print('VTX_SELFTEST cases=%d failures=%d' % (total, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.argv = [a for a in sys.argv if a != '--selftest']
        sys.exit(selftest())
    sys.exit(main())
