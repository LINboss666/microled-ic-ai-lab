# -*- coding: utf-8 -*-
#!/usr/bin/env python
"""SCAN-1 R0: strict PSF-ASCII reader. Rewritten after the SCAN-1R2 review found the previous
version could return a wrong number with exit code 0.

    sc1_read_psf.py --data FILE | --deck DECK.scs
                    --sig NAME  [--sweep V | --t0 T --t1 T]
                    [--mode last|max|min|mean|first] [--require-n K]

Parsing rules that exist because of specific reproduced defects:

 * The VALUE block is a sequence of groups that each start with the axis ("time" for tran, the
   sweep name for dc). Values are collected PER GROUP, so a signal can never be shifted against
   the axis. The old parser appended each value with float() inside a try and silently dropped
   unparsable rows, which desynchronised time and signal: a window whose true max was 1.8 V
   returned 0 V with rc=0.
 * A group that does not contain the requested signal is an inconsistency, not a missing sample.
 * NaN / Inf are rejected as BAD_VALUE. The old code let them through; a series 0, NaN, 0 then
   reported window max = 0 and rc = 0.
 * Length mismatch between the axis and a signal, or a file that ends mid-group, is TRUNCATED.
 * Numbers are printed with 6 significant digits (not 6 decimals) so 1.23e-9 A does not become
   0.000000. Callers state the unit; this tool reports the stored value.

Exit codes (all failures are non-zero, by contract):
    0 ok | 2 NO_DATA_FILE | 3 NO_SIGNAL | 4 NO_POINT / TOO_FEW / empty window
    5 BAD_NUMERIC | 7 TRUNCATED_OR_LENGTH_MISMATCH | 8 BAD_AXIS
"""
from __future__ import print_function
import io, math, os, re, sys

SUF = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3,
       'k': 1e3, 'meg': 1e6, 'g': 1e9, 's': 1.0, 'a': 1.0, 'v': 1.0}


def finite(v):
    return not (math.isinf(v) or math.isnan(v))


def qty(tok):
    """'1.8', '500n', '1e-6', '2.5E-12', '-40m', '20meg'. Returns a float or raises ValueError."""
    t = str(tok).strip().strip('"')
    if not t:
        raise ValueError('empty quantity')
    m = re.match(r'^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)$', t)
    if not m:
        raise ValueError('not a quantity: %r' % (tok,))
    val = float(m.group(1))
    unit = m.group(2).lower()
    if not unit:
        return val
    if unit in SUF:
        return val * SUF[unit]
    raise ValueError('unknown unit %r in %r' % (unit, tok))


def locate(explicit=None, deck=None):
    if explicit:
        return explicit
    if deck:
        stem = os.path.splitext(os.path.abspath(deck))[0]
        d = os.path.join(os.path.dirname(os.path.abspath(deck)), 'sim',
                         os.path.basename(stem) + '.raw')
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name)
                try:
                    txt = io.open(p, encoding='utf-8', errors='replace').read()
                except IOError:
                    continue
                if re.search(r'^VALUE', txt, re.M) and re.search(r'^TRACE', txt, re.M):
                    return p
    return None


def parse(path):
    """Return (groups, axis_name). groups = list of dict name->float, in file order."""
    with io.open(path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    sec = None
    axis = None
    groups = []
    cur = None
    trunc_in_group = False
    for ln, raw in enumerate(lines, 1):
        line = raw.rstrip('\n')
        if line.startswith('SWEEP'):
            sec = 'sweep'
            continue
        if line.startswith('TRACE'):
            sec = 'trace'
            continue
        if line.startswith('VALUE'):
            sec = 'value'
            continue
        if line.startswith('END'):
            if cur:
                groups.append(cur)
                cur = None
            sec = None
            continue
        if sec != 'value':
            # the SWEEP header carries the axis name on the first quoted line
            if sec == 'sweep' and axis is None:
                m = re.match(r'^"([^"]+)"', line)
                if m:
                    axis = m.group(1)
            continue
        m = re.match(r'^"([^"]+)"\s+(\S+)', line)
        if not m:
            if line.strip() and not line.startswith(')'):
                raise ValueError('BAD_NUMERIC line %d: %r' % (ln, line[:60]))
            continue
        name, txt = m.group(1), m.group(2)
        # a bare number that cannot be parsed must abort, never be dropped
        low = txt.lower()
        if low in ('nan', '1.#qnan', '-nan', 'inf', '+inf', '-infinity', '1.#inf'):
            raise ValueError('BAD_NUMERIC non-finite %s at line %d for %s' % (txt, ln, name))
        try:
            v = float(txt)
        except ValueError:
            raise ValueError('BAD_NUMERIC line %d: %r' % (ln, txt))
        if not finite(v):
            raise ValueError('BAD_NUMERIC non-finite line %d for %s' % (ln, name))
        if name == axis:
            if cur is not None:
                groups.append(cur)
            cur = {name: v}
            trunc_in_group = False
        else:
            if cur is None:
                raise ValueError('BAD_AXIS value row before first axis row (line %d)' % ln)
            if name in cur:
                raise ValueError('TRUNCATED duplicate %s inside one group (line %d)' % (name, ln))
            cur[name] = v
    if cur:
        raise ValueError('TRUNCATED file ends inside an unfinished group')
    if not groups:
        raise ValueError('TRUNCATED no complete data group parsed')
    # length consistency: every group must carry the same signal set
    ref = set(k for k in groups[0])
    for i, g in enumerate(groups):
        if set(g) != ref:
            raise ValueError('TRUNCATED group %d has signals %s, group 0 has %s'
                             % (i, sorted(set(g) - ref), sorted(ref - set(g))))
    return groups, axis


def as_columns(groups, axis):
    cols = {}
    for name in groups[0]:
        cols[name] = [g[name] for g in groups]
    return cols, (cols.get(axis) if axis in cols else None)


def main():
    a = sys.argv[1:]
    opt = {}
    i = 0
    while i < len(a):
        if a[i].startswith('--'):
            opt[a[i][2:]] = a[i + 1] if i + 1 < len(a) else ''
            i += 2
        else:
            i += 1
    path = locate(opt.get('data'), opt.get('deck'))
    if not path or not os.path.exists(path):
        print("NO_DATA_FILE %s" % (path or 'not-located'))
        return 2
    if os.path.getsize(path) == 0:
        print("NO_DATA_FILE empty")
        return 2
    try:
        groups, axis = parse(path)
    except ValueError as e:
        msg = str(e)
        code = 5 if msg.startswith('BAD_NUMERIC') else (7 if msg.startswith('TRUNCATED') else 8)
        print(msg)
        return code
    cols, axisv = as_columns(groups, axis)
    sig = opt.get('sig')
    if sig not in cols:
        print("NO_SIGNAL %s (have: %s)" % (sig, ','.join(sorted(cols))[:160]))
        return 3
    vals = cols[sig]
    mode = opt.get('mode', 'last')
    need = int(opt.get('require-n', '1') or 1)

    if 'sweep' in opt:
        if axisv is None:
            print("BAD_AXIS no axis column")
            return 8
        try:
            want = qty(opt['sweep'])
        except ValueError as e:
            print("BAD_NUMERIC %s" % e)
            return 5
        tol = max(1e-12, abs(want) * 1e-6)
        picked = [v for (s, v) in zip(axisv, vals) if abs(s - want) <= tol]
        if not picked:
            print("NO_POINT sweep=%s not on axis (n=%d)" % (opt['sweep'], len(axisv)))
            return 4
    elif 't0' in opt or 't1' in opt:
        if axisv is None:
            print("BAD_AXIS no time column for a window query")
            return 8
        try:
            t0 = qty(opt['t0']) if 't0' in opt else min(axisv)
            t1 = qty(opt['t1']) if 't1' in opt else max(axisv)
        except ValueError as e:
            print("BAD_NUMERIC %s" % e)
            return 5
        if t1 < t0:
            print("BAD_NUMERIC window reversed t0=%g > t1=%g" % (t0, t1))
            return 5
        picked = [v for (s, v) in zip(axisv, vals) if t0 <= s <= t1]
        if len(picked) < need:
            print("TOO_FEW_SAMPLES %d<%d window=[%g,%g]" % (len(picked), need, t0, t1))
            return 4
    else:
        picked = vals

    if not picked:
        print("NO_POINT empty selection")
        return 4
    if mode == 'max':
        out = max(picked)
    elif mode == 'min':
        out = min(picked)
    elif mode == 'mean':
        out = sum(picked) / float(len(picked))
    elif mode == 'first':
        out = picked[0]
    elif mode == 'absmax':
        out = max(picked, key=lambda x: abs(x))
    else:
        out = picked[-1]
    # 6 significant digits: a nanoampere must not be printed as 0.000000
    print("%.6g" % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
