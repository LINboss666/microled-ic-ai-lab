# -*- coding: utf-8 -*-
#!/usr/bin/env python
"""SCAN-1 R0: edge and delay measurement on PSF-ASCII, with the pairing rules fixed.

    sc1_delay.py --data FILE | --deck DECK.scs --sig NAME --vdd V
                  --mode edge --edge rise|fall [--t0 T --t1 T]        # 10-90% of --vdd
    sc1_delay.py ... --mode propdelay --sig-in A --sig-out B --vdd-in V --vdd-out V [--t0 --t1]
    sc1_delay.py ... --mode steady --sig NAME --t0 T --t1 T           # min/max/n in a stated window

Why each rule is here:
 * Crossings are directional. The first version treated "sample above threshold" as an edge, so a
   fall measurement grabbed the END of the preceding rise and reported 194 ns for a 4 ns edge.
 * A 10% point may only pair with the next 90% point of the SAME direction, and only inside the
  requested window. Left uncrossed, a partial transition in period 1 used to pair with period 2.
 * `settled` is no longer the extremum of the whole waveform: that could report a peak as a stable
   level. Steady state is min/max/n over an explicit window the caller must supply.
 * A non-monotonic axis, a missing signal or too few samples are errors with a non-zero exit.

Exit codes: 0 ok | 2 NO_DATA_FILE | 3 NO_SIGNAL | 4 NO_EDGE / too few | 5 BAD_NUMERIC |
            7 TRUNCATED / length mismatch | 8 BAD_AXIS (non-monotonic time) | 9 usage
"""
from __future__ import print_function
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_read_psf as R


def cols_or_die(path):
    try:
        groups, axis = R.parse(path)
    except ValueError as e:
        msg = str(e)
        code = 5 if msg.startswith('BAD_NUMERIC') else (7 if msg.startswith('TRUNCATED') else 8)
        print(msg)
        return None, None, None, code
    cols, axisv = R.as_columns(groups, axis)
    return cols, axisv, axis, 0


def crossing_times(t, v, level, direction):
    """Interpolated directional crossings; never a bare 'first sample above level'."""
    out = []
    for i in range(1, len(v)):
        a, b = v[i - 1], v[i]
        if direction == 'up' and a <= level < b:
            out.append(t[i - 1] + (level - a) / (b - a) * (t[i] - t[i - 1]))
        elif direction == 'down' and b <= level < a:
            out.append(t[i - 1] + (a - level) / (a - b) * (t[i] - t[i - 1]))
    return out


def first_pair(starts, ends):
    """Pair each start with the FIRST end after it (same event), never a later period."""
    for s in starts:
        cand = [e for e in ends if e >= s]
        if cand:
            return s, cand[0]
    return None, None


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
        print("NO_DATA_FILE")
        return 2
    cols, t, axis, rc = cols_or_die(path)
    if rc:
        return rc
    if t is None:
        print("BAD_AXIS no time/sweep column")
        return 8
    for k in range(1, len(t)):
        if t[k] <= t[k - 1]:
            print("BAD_AXIS non-monotonic at index %d (%g -> %g)" % (k, t[k - 1], t[k]))
            return 8
    mode = opt.get('mode', 'edge')
    lo_w = R.qty(opt['t0']) if opt.get('t0') else None
    hi_w = R.qty(opt['t1']) if opt.get('t1') else None

    def in_win(vals_times):
        if lo_w is None and hi_w is None:
            return vals_times
        a0 = lo_w if lo_w is not None else min(t)
        a1 = hi_w if hi_w is not None else max(t)
        return [(tt, v) for (tt, v) in vals_times if a0 <= tt <= a1]

    def series(name):
        if name not in cols:
            print("NO_SIGNAL %s (have %s)" % (name, ','.join(sorted(cols))[:160]))
            return None
        return in_win(list(zip(t, cols[name])))

    if mode == 'steady':
        if lo_w is None or hi_w is None:
            print("usage: steady requires an explicit --t0/--t1 window (settled is not the global extremum)")
            return 9
        s = series(opt.get('sig'))
        if s is None:
            return 3
        v = [x[1] for x in s]
        need = int(opt.get('require-n', '5') or 5)
        if len(v) < need:
            print("NO_EDGE too few samples in steady window n=%d need=%d" % (len(v), need))
            return 4
        print("STEADY sig=%s window=[%g,%g] n=%d min=%.6g max=%.6g mean=%.6g"
              % (opt.get('sig'), lo_w, hi_w, len(v), min(v), max(v), sum(v) / len(v)))
        return 0

    if mode == 'propdelay':
        si, so = opt.get('sig-in'), opt.get('sig-out')
        ss, so_s = series(si), series(so)
        if ss is None or so_s is None:
            return 3
        direction = 'down' if opt.get('edge') == 'fall' else 'up'
        ti = crossing_times([x[0] for x in ss], [x[1] for x in ss],
                            0.5 * float(opt.get('vdd-in', 1.8)), direction)
        to = crossing_times([x[0] for x in so_s], [x[1] for x in so_s],
                            0.5 * float(opt.get('vdd-out', 3.3)), direction)
        s, e = first_pair(ti, to)
        if s is None or e is None:
            print("NO_EDGE propdelay %s->%s dir=%s in_x=%d out_x=%d window=[%s,%s]"
                  % (si, so, direction, len(ti), len(to), opt.get('t0'), opt.get('t1')))
            return 4
        print("PROPDELAY %s->%s dir=%s t_in=%.6e t_out=%.6e delay_ns=%.3f"
              % (si, so, direction, s, e, (e - s) * 1e9))
        return 0

    # default: edge 10-90
    sig = opt.get('sig')
    s = series(sig)
    if s is None:
        return 3
    vdd = float(opt.get('vdd', 3.3))
    edge = opt.get('edge', 'fall')
    direction = 'down' if edge == 'fall' else 'up'
    lo, hi = 0.10 * vdd, 0.90 * vdd
    tt = [x[0] for x in s]
    vv = [x[1] for x in s]
    if edge == 'fall':
        starts, ends = crossing_times(tt, vv, hi, direction), crossing_times(tt, vv, lo, direction)
    else:
        starts, ends = crossing_times(tt, vv, lo, direction), crossing_times(tt, vv, hi, direction)
    t0, t1 = first_pair(starts, ends)
    if t0 is None or t1 is None:
        print("NO_EDGE sig=%s %s: start_x=%d end_x=%d range=[%.6g,%.6g] window=[%s,%s]"
              % (sig, edge, len(starts), len(ends), min(vv), max(vv), opt.get('t0'), opt.get('t1')))
        return 4
    span = [v for x, v in zip(tt, vv) if t0 <= x <= t1]
    print("EDGE %s sig=%s t_start=%.6e t_end=%.6e duration_ns=%.3f n_in_edge=%d "
          "window_level_min=%.6g window_level_max=%.6g"
          % (edge, sig, t0, t1, (t1 - t0) * 1e9, len(span), min(span), max(span)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
