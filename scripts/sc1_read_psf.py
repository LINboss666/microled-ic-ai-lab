#!/usr/bin/env python
"""SCAN-1: read one value out of a Spectre PSF-ASCII file, or fail loudly.

    sc1_read_psf.py --data <file> --sig en [--sweep 1.8 | --t0 500n --t1 595n] [--mode max|min|last]

Why this exists as its own tool: the S1 evidence CSV first stored the *threshold text*
("want>0.9") instead of the measured voltage, because the shell picked the value out of a
diagnostic line with tr/grep. A value in a report has to come from the waveform data.

Failure is a first-class result here, not a silent empty string:

    exit 2  NO_DATA_FILE     path missing or empty file
    exit 3  NO_SIGNAL        the signal is not in the TRACE section
    exit 4  NO_POINT         the sweep point / time window has no samples
    exit 5  BAD_NUMERIC      a sample is not parseable

An empty CSV or a crashed simulation therefore cannot be mistaken for a pass.
Time and sweep matching uses a relative window because psfascii samples are not exact.
"""
from __future__ import print_function
import io, os, re, sys

SUF = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'meg': 1e6, 'g': 1e9}


def qty(tok, default_scale=1.0):
    """Parse '1.8', '500n', '1e-6', '20meg'. Time args come in seconds, volts as-is."""
    t = str(tok).strip()
    if not t:
        raise ValueError('empty')
    m = re.match(r'^([+-]?[0-9.]+)\s*([a-zA-Z]*)$', t)
    if not m:
        raise ValueError('bad number: %r' % tok)
    v = float(m.group(1))
    unit = m.group(2).lower()
    if not unit:
        return v * default_scale
    if unit in SUF:
        return v * SUF[unit]
    raise ValueError('unknown unit %r in %r' % (unit, tok))


def locate(explicit=None, deck=None):
    """Find the psfascii data file. Spectre writes sim/<stem>.raw/<something> where the real
    data file is the one carrying both VALUE and TRACE sections (the logFile does not)."""
    if explicit:
        return explicit
    if deck:
        base = os.path.splitext(deck)[0]
        cand_dir = os.path.join(os.path.dirname(deck), 'sim', os.path.basename(base) + '.raw')
        if os.path.isdir(cand_dir):
            for name in sorted(os.listdir(cand_dir)):
                p = os.path.join(cand_dir, name)
                try:
                    with io.open(p, encoding='utf-8', errors='replace') as f:
                        txt = f.read()
                except IOError:
                    continue
                if re.search(r'^VALUE', txt, re.M) and re.search(r'^TRACE', txt, re.M):
                    return p
    return None


def parse(path):
    with io.open(path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    sweep_name = None
    sigs = {}
    sec = None
    order = []
    for line in lines:
        m = re.match(r'^"([A-Za-z0-9_.:\\[\]-]+)"\s+(TIME|VOLT|CURR)', line)
        if m:
            sec = None
            name, kind = m.group(1), m.group(2)
            if kind == 'TIME':
                sigs.setdefault('time', [])
            else:
                sigs.setdefault(name, [])
                if name not in order:
                    order.append(name)
            cur = name
            continue
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
            sec = None
            continue
        if sec == 'sweep':
            t = line.split()
            # this build writes:   SWEEP \n "dc" "sweep" PROP(   -> axis name is field 1
            if t and sweep_name is None and not t[0].startswith('!'):
                cand = t[0].strip('"')
                if re.match(r'^[A-Za-z_][A-Za-z0-9_.]*$', cand):
                    sweep_name = cand
            continue
        if sec == 'value':
            t = line.split()
            if len(t) >= 2:
                k = t[0].strip('"')
                try:
                    sigs.setdefault(k, []).append(float(t[1]))
                except ValueError:
                    pass
    return sigs, sweep_name


def main():
    args = sys.argv[1:]
    opt = {}
    i = 0
    while i < len(args):
        if args[i].startswith('--'):
            opt[args[i][2:]] = args[i + 1] if i + 1 < len(args) else ''
            i += 2
        else:
            i += 1
    path = locate(opt.get('data'), opt.get('deck'))
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        print("NO_DATA_FILE %s" % (path or 'not-located'))
        return 2
    sigs, sweep_name = parse(path)
    sig = opt.get('sig')
    if sig not in sigs or not sigs[sig]:
        print("NO_SIGNAL %s (have: %s)" % (sig, ','.join(sorted(sigs))[:200]))
        return 3
    vals = sigs[sig]
    mode = opt.get('mode', 'last')

    if 'sweep' in opt:
        if not sweep_name or sweep_name not in sigs:
            print("NO_SWEEP_AXIS")
            return 4
        want = qty(opt['sweep'])
        axis = sigs[sweep_name]
        idx = [k for k, a in enumerate(axis) if abs(a - want) <= max(1e-9, abs(want) * 1e-6)]
        if not idx:
            print("NO_POINT sweep=%g not in axis (n=%d)" % (want, len(axis)))
            return 4
        picked = [vals[k] for k in idx]
    elif 't0' in opt or 't1' in opt:
        if 'time' not in sigs or not sigs['time']:
            print("NO_TIME_AXIS")
            return 4
        t = sigs['time']
        t0 = qty(opt['t0']) if 't0' in opt else min(t)
        t1 = qty(opt['t1']) if 't1' in opt else max(t)
        picked = [v for (tt, v) in zip(t, vals) if t0 <= tt <= t1]
        need = int(opt.get('require-n', '1') or 1)
        if len(picked) < need:
            print("TOO_FEW_SAMPLES %d<%d window=[%g,%g]" % (len(picked), need, t0, t1))
            return 4
    else:
        picked = [vals[-1]]

    if not picked:
        print("NO_POINT empty selection")
        return 4
    need = int(opt.get('require_n', 1))
    if len(picked) < need:
        # an assertion over a window with too few samples proves nothing; refuse to answer
        print("TOO_FEW_SAMPLES n=%d need=%d" % (len(picked), need))
        return 6
    try:
        if mode == 'max':
            out = max(picked)
        elif mode == 'min':
            out = min(picked)
        elif mode == 'mean':
            out = sum(picked) / float(len(picked))
        else:
            out = picked[-1]
    except TypeError:
        print("BAD_NUMERIC")
        return 5
    print("%.6f" % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
