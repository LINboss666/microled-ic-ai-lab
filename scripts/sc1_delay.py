#!/usr/bin/env python
"""SCAN-1: edge timing from a psfascii file, reusing sc1_read_psf's own parser.

    sc1_delay.py --deck <deck.scs> --sig out --edge rise|fall [--vdd 3.3] [--ref 0.5]

Reports the 10 % -> 90 % crossing instants and the interval between them, plus the settled
level. Percentages are of --vdd, because "20 % of a swing" is meaningless before the rail is
fixed. Prints a token and exits non-zero when the edge never happens, so a stuck node cannot
be reported as a slow edge.
"""
from __future__ import print_function
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_read_psf as R   # same parser that produced the S1 numbers


def crossings(t, v, level, direction):
    """Interpolated crossings of `level` in the requested direction only.

    Direction matters: on a rising-then-falling waveform the 90 % point is crossed twice, and
    taking "the first crossing above the threshold" for a FALL measurement silently measures the
    end of the rise instead. That bug produced a 194 ns 'fall' on a waveform whose fall is 4 ns.
    """
    out = []
    for i in range(1, len(v)):
        a, b = v[i - 1], v[i]
        if direction == 'up' and a <= level < b:
            out.append(t[i - 1] + (level - a) / (b - a) * (t[i] - t[i - 1]))
        elif direction == 'down' and b <= level < a:
            out.append(t[i - 1] + (a - level) / (a - b) * (t[i] - t[i - 1]))
    return out


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
    path = R.locate(opt.get('data'), opt.get('deck'))
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        print("NO_DATA_FILE"); return 2
    sigs, _ = R.parse(path)
    sig = opt.get('sig')
    if sig not in sigs or 'time' not in sigs:
        print("NO_SIGNAL %s (have %s)" % (sig, ','.join(sorted(sigs))[:120])); return 3
    t = sigs['time']; v = sigs[sig]
    vdd = float(opt.get('vdd', 3.3))
    edge = opt.get('edge', 'fall')
    lo, hi = 0.10 * vdd, 0.90 * vdd
    if edge == 'fall':
        d = 'down'
        t_start_list, t_end_list = crossings(t, v, hi, d), crossings(t, v, lo, d)
        settled = min(v)
    else:
        d = 'up'
        t_start_list, t_end_list = crossings(t, v, lo, d), crossings(t, v, hi, d)
        settled = max(v)
    if not t_start_list or not t_end_list:
        print("NO_EDGE sig=%s %s: start_x=%d end_x=%d range=[%.4f,%.4f]"
              % (sig, edge, len(t_start_list), len(t_end_list), min(v), max(v)))
        return 4
    # pair them in order: the first start that has a later end
    pair = [(s, e) for s in t_start_list for e in t_end_list if e > s]
    if not pair:
        print("NO_EDGE ordering (%s) start=%s end=%s" % (edge, t_start_list[:3], t_end_list[:3]))
        return 4
    t0, t1 = pair[0]
    print("EDGE %s sig=%s t_start=%.6e t_end=%.6e duration_ns=%.3f settled=%.4f n=%d"
          % (edge, sig, t0, t1, (t1 - t0) * 1e9, settled, len(v)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
