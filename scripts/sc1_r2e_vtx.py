#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R2E measurement helper: the extreme of a DIFFERENCE of two saved nodes inside a time window.

    sc1_r2e_vtx.py --data FILE --a NODE [--b NODE] [--t0 T --t1 T] [--mode max|min] [--quiet]

Why this exists: scripts/sc1_read_psf.py aggregates one signal at a time, and a MOS stress voltage is
a difference of two node voltages at the SAME sample (VGS = Vg - Vs). Taking min/max of each node
separately would pair samples from different instants and could invent a stress that never happened,
so the two traces are read together and the difference is formed per sample. This is deliberately a
single-purpose reader for this round's transient decks, not a general PSF parser: it reads the
psfascii VALUE block that scripts/run_spectre.sh produces with -format psfascii and nothing else.

Exit codes follow scripts/sc1_read_psf.py: 0 value printed, 2 no data file, 3 no such signal,
4 not enough samples in the window, 8 axis/signal shape is not a plain scalar trace, 9 bad usage.
Prints '<value>\\t<time_at_the_extreme>' on stdout.
"""
from __future__ import print_function

import io
import optparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc1_read_psf as RD                # audited reader: only its qty() time grammar is reused

try:
    _text = unicode
except NameError:
    _text = str


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def load(path):
    """-> (axis, [names...], [[(t, {name: value})...]]) with the samples in file order."""
    if not path or not os.path.isfile(path):
        return None, None, None, 2
    invalue = False
    axis = 'time'
    rows, cur = [], {}
    names = set()
    for raw in open(path, 'rb'):
        line = u(raw).strip()
        if line.startswith('VALUE'):
            invalue = True
            continue
        if not invalue:
            continue
        if line.startswith('END'):
            break
        m = re.match(r'^"([^"]+)"\s+(.*)$', line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2).split()
        if len(rest) != 1:
            return axis, names, rows, 8
        try:
            val = float(rest[0])
        except ValueError:
            return axis, names, rows, 8
        if name == axis:
            if cur:
                rows.append(cur)
            cur = {'__t__': val}
            continue
        names.add(name)
        cur[name] = val
    if cur and len(cur) > 1:
        rows.append(cur)
    return axis, sorted(names), rows, 0


def main():
    op = optparse.OptionParser()
    op.add_option('--data')
    op.add_option('--a')
    op.add_option('--b')
    op.add_option('--t0')
    op.add_option('--t1')
    op.add_option('--mode', default='max')
    op.add_option('--quiet', action='store_true')
    o, _ = op.parse_args()
    if not o.data or not o.a:
        print('BAD_USAGE: --data and --a are required')
        return 9
    axis, names, rows, rc = load(o.data)
    if rc == 2:
        print('NO_DATA_FILE %s' % o.data)
        return 2
    if rc == 8:
        print('BAD_SHAPE not a plain scalar trace')
        return 8
    want = [o.a] + ([o.b] if o.b else [])
    for s in want:
        if s not in names:
            print('NO_SIGNAL %s (have: %s)' % (s, ','.join(names[:40])))
            return 3
    lo = RD.qty(o.t0) if o.t0 else -1e30
    hi = RD.qty(o.t1) if o.t1 else 1e30
    picks = []
    for r in rows:
        t = r.get('__t__')
        if t is None or t < lo - 1e-21 or t > hi + 1e-21:
            continue
        if o.a not in r or (o.b and o.b not in r):
            continue
        d = r[o.a] - (r[o.b] if o.b else 0.0)
        picks.append((d, t))
    if len(picks) < 2:
        print('TOO_FEW samples=%d in window' % len(picks))
        return 4
    best = max(picks) if o.mode == 'max' else min(picks)
    if not o.quiet:
        print('window %.9g..%.9g s, %d samples, %s of (%s%s)'
              % (lo if lo > -1e29 else 0.0, hi if hi < 1e29 else t_max(rows), len(picks), o.mode,
                 o.a, (' - ' + o.b) if o.b else ''), file=sys.stderr)
    print('%.6g\t%.6g' % best)
    return 0


def t_max(rows):
    return max([r.get('__t__', 0.0) for r in rows])


# ------------------------------------------------------------------ offline self test
def selftest():
    """Synthetic psfascii only -- no simulator. Each case checks value, time of the extreme and rc."""
    d = os.path.join(os.environ.get('TMP', '/tmp'), 'sc1_r2e_vtx_selftest')
    if not os.path.isdir(d):
        os.makedirs(d)
    cases = [
        ('in phase: a-b is flat', [(0.0, 1.0, 1.0), (1e-9, 2.0, 2.0)],
         ('a', 'b', 'max'), 0.0),
        ('extremes at the same instant', [(0.0, 3.3, 0.0), (1e-9, 0.0, 1.8), (2e-9, 3.3, 1.8)],
         ('a', 'b', 'min'), -1.8),
        ('min and max differ', [(0.0, 0.0, 1.8), (1e-9, 1.8, 0.0), (2e-9, 0.9, 0.9)],
         ('b', 'a', 'max'), 1.8),
    ]
    bad = 0
    for n, (label, samples, (a, b, mode), want_v) in enumerate(cases):
        p = os.path.join(d, 'case_%d.psf' % n)
        with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u('HEADER\n"simulator" "spectre"\nSWEEP\n"time" "sweep"\nTRACE\n"a" "V"\n"b" "V"\n'))
            f.write(u('VALUE\n'))
            for t, av, bv in samples:
                f.write(u('"time" %.17e\n"%s" %.17e\n"%s" %.17e\n' % (t, a, av, b, bv)))
            f.write(u('END\n'))
        out = os.popen('%s %s --data "%s" --a "%s" --b "%s" --mode %s --quiet 2>&1'
                       % (sys.executable, os.path.abspath(__file__), p, a, b, mode)).read().strip()
        got_v = float(out.split('\t')[0]) if out and '\t' in out else None
        ok = got_v is not None and abs(got_v - want_v) < 1e-12
        print('%-34s want=%-8s got=%-12s %s' % (label, want_v, out, 'PASS' if ok else 'FAIL'))
        if not ok:
            bad += 1
    # window edge: only samples inside [t0,t1] may be used, and a one-sample window must fail closed
    p = os.path.join(d, 'win.psf')
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u('HEADER\nSWEEP\n"time" "sweep"\nTRACE\n"a" "V"\n"b" "V"\nVALUE\n'))
        for t, av, bv in ((0.0, 3.3, 0.0), (1e-9, 0.0, 0.0), (2e-9, 3.3, 0.0)):
            f.write(u('"time" %.17e\n"a" %.17e\n"b" %.17e\n' % (t, av, bv)))
        f.write(u('END\n'))
    out = os.popen('%s %s --data %s --a a --b b --mode max --t0 1n --t1 1n --quiet 2>&1'
                   % (sys.executable, os.path.abspath(__file__), p)).read().strip()
    ok = out.startswith('TOO_FEW')
    print('%-34s got=%-14s %s' % ('single-sample window fails closed', out, 'PASS' if ok else 'FAIL'))
    if not ok:
        bad += 1
    out = os.popen('%s %s --data %s --a a --b nope --mode max --quiet 2>&1'
                   % (sys.executable, os.path.abspath(__file__), p)).read().strip()
    ok = out.startswith('NO_SIGNAL')
    print('%-34s got=%-14s %s' % ('missing signal names itself', out, 'PASS' if ok else 'FAIL'))
    if not ok:
        bad += 1
    print('VTX_SELFTEST cases=5 failures=%d' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.argv = [a for a in sys.argv if a != '--selftest']
        sys.exit(selftest())
    sys.exit(main())
