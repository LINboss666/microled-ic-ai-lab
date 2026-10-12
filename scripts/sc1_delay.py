#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2A: edge and delay measurement that identifies real events.

    sc1_delay.py --data FILE | --deck DECK.scs --sig NAME --vdd V
                 --mode edge --edge rise|fall [--t0 T --t1 T]
                 [--event first_attempt|first_complete] [--require-n K]
    sc1_delay.py ... --mode propdelay --sig-in A --sig-out B --vdd-in V --vdd-out V
                 [--edge-in rise|fall] [--edge-out rise|fall] [--t0 T --t1 T]
    sc1_delay.py ... --mode steady --sig NAME --t0 T --t1 T [--require-n K]

Three reproduced defects drove this rewrite:

 1. Splicing. The previous version paired each start with "the next end" without testing they
    belong to the same excursion. For t=0..5 ns with out = 0,1,0,0,3.3,3.3 it returned
    duration_ns=3.570 for an event that never happened: the first attempt falls back below the low
    threshold and must be abandoned, and the real second rise is 0.800 ns. Attempts are now a state
    machine; --event first_attempt reports NO_EDGE on an incomplete first attempt, --event
    first_complete (default) skips to the next complete one. Both report attempt counts.
 2. Inverting chains. propdelay forced input and output into one direction, so it could not measure
    en -> gate33 (rise in, fall out) and paired an input rise with an unrelated later output rise,
    giving 6.0 ns where 2.0 ns is correct. --edge-in/--edge-out are independent and the output must
    be a complete event beginning at or after the input crossing.
 3. Two-sample edges. When 10 % and 90 % both fall inside one interval the old code took an empty
    span and crashed in min(span). Both crossings are interpolated from that interval and reported
    as samples_in_edge=0 instead of crashing or inventing samples.
"""
from __future__ import print_function
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_read_psf as R

E = {'ok': 0, 'nodata': 2, 'nosig': 3, 'noedge': 4, 'badnum': 5,
     'trunc': 7, 'badaxis': 8, 'usage': 9}


def load(opt):
    path = R.locate(opt.get('data'), opt.get('deck'))
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        print("NO_DATA_FILE")
        return None, None, E['nodata']
    try:
        groups, axis = R.parse(path)
    except ValueError as e:
        msg = str(e)
        code = E['badnum'] if msg.startswith('BAD_NUMERIC') else (
            E['trunc'] if msg.startswith('TRUNCATED') else E['badaxis'])
        print(msg)
        return None, None, code
    cols, axisv = R.as_columns(groups, axis)
    if axisv is None:
        print("BAD_AXIS no time column")
        return None, None, E['badaxis']
    for k in range(1, len(axisv)):
        if not (axisv[k] > axisv[k - 1]):
            print("BAD_AXIS time not strictly increasing at index %d (%g -> %g)"
                  % (k, axisv[k - 1], axisv[k]))
            return None, None, E['badaxis']
    return cols, axisv, 0


def interp(ta, va, tb, vb, level):
    return ta + (level - va) / (vb - va) * (tb - ta)


def attempts(tt, vv, vdd, edge, lo_frac=0.10, hi_frac=0.90):
    """Complete and abandoned 10-90 % attempts, as a state machine.

    A rise opens on an upward crossing of the low threshold and is abandoned if the waveform falls
    back through it before reaching the high threshold; a fall mirrors that about the high
    threshold. Abandonment is what stops one event borrowing another's end point.
    """
    lo, hi = lo_frac * vdd, hi_frac * vdd
    complete, abandoned = [], []
    cur = None
    for i in range(1, len(vv)):
        a, b = vv[i - 1], vv[i]
        if b == a:
            continue
        ta, tb = tt[i - 1], tt[i]
        if edge == 'rise':
            up_lo, up_hi = a < lo <= b, a < hi <= b
            dn_lo = b < lo <= a
        else:
            up_hi = a <= hi < b
            dn_hi, dn_lo = b <= hi < a, b <= lo < a
        if cur is None:
            opened = None
            if edge == 'rise' and up_lo:
                opened = interp(ta, a, tb, b, lo)
            elif edge == 'fall' and dn_hi:
                opened = interp(ta, a, tb, b, hi)
            if opened is not None:
                # both thresholds can live inside ONE interval (a two-sample edge, or the real rise
                # of the splicing case). If this same interval also crosses the far threshold the
                # attempt completes here; not doing that lost every fast edge and made propdelay
                # report "no complete event" for a perfectly good transition.
                if edge == 'rise' and up_hi:
                    te = interp(ta, a, tb, b, hi)
                    if te > opened:
                        complete.append((opened, te))
                elif edge == 'fall' and dn_lo:
                    te = interp(ta, a, tb, b, lo)
                    if te > opened:
                        complete.append((opened, te))
                else:
                    cur = [opened, None]
            continue
        if edge == 'rise' and up_hi:
            te = interp(ta, a, tb, b, hi)
            if te > cur[0]:
                complete.append((cur[0], te))
            cur = None
        elif edge == 'fall' and dn_lo:
            te = interp(ta, a, tb, b, lo)
            if te > cur[0]:
                complete.append((cur[0], te))
            cur = None
        elif edge == 'rise' and dn_lo:
            abandoned.append(tuple(cur)); cur = None
        elif edge == 'fall' and up_hi:
            abandoned.append(tuple(cur)); cur = None
    return complete, abandoned


def main():
    argv = sys.argv[1:]
    opt = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith('--'):
            opt[argv[i][2:]] = argv[i + 1] if i + 1 < len(argv) else ''
            i += 2
        else:
            i += 1
    cols, t, rc = load(opt)
    if rc:
        return rc
    mode = opt.get('mode', 'edge')
    if mode not in ('edge', 'propdelay', 'steady'):
        print("BAD_USAGE unknown mode %r" % mode)
        return E['usage']
    for key in ('edge', 'edge-in', 'edge-out'):
        if opt.get(key) is not None and opt[key] not in ('rise', 'fall'):
            print("BAD_USAGE unknown %s %r" % (key, opt[key]))
            return E['usage']
    ev_pol = opt.get('event', 'first_complete')
    if ev_pol not in ('first_attempt', 'first_complete'):
        print("BAD_USAGE --event must be first_attempt or first_complete")
        return E['usage']
    try:
        need = int(opt.get('require-n', '1') or 1)
    except ValueError:
        print("BAD_USAGE --require-n must be an integer")
        return E['usage']
    if need < 1:
        print("BAD_USAGE --require-n must be >= 1")
        return E['usage']
    try:
        lo_w = R.qty(opt['t0']) if opt.get('t0') is not None else None
        hi_w = R.qty(opt['t1']) if opt.get('t1') is not None else None
    except ValueError as e:
        print("BAD_NUMERIC %s" % e)
        return E['badnum']
    if lo_w is not None and hi_w is not None and hi_w < lo_w:
        print("BAD_NUMERIC window reversed t0 > t1")
        return E['badnum']

    def rail(name, default):
        try:
            v = float(opt.get(name, default))
        except (TypeError, ValueError):
            print("BAD_NUMERIC %s is not a number" % name)
            return None
        if not (0.0 < v < 1e6):
            print("BAD_NUMERIC %s must be a finite positive rail voltage" % name)
            return None
        return v

    def series(name):
        if name not in cols:
            print("NO_SIGNAL %s (have %s)" % (name, ','.join(sorted(cols))[:160]))
            return None
        if lo_w is None and hi_w is None:
            return list(zip(t, cols[name]))
        return [(x, y) for (x, y) in zip(t, cols[name])
                if (lo_w is None or x >= lo_w) and (hi_w is None or x <= hi_w)]

    if mode == 'steady':
        if lo_w is None or hi_w is None:
            print("BAD_USAGE steady requires an explicit --t0/--t1 window "
                  "(settled must not be the extremum of the whole waveform)")
            return E['usage']
        sig = opt.get('sig')
        s = series(sig)
        if s is None:
            return E['nosig']
        v = [x[1] for x in s]
        if len(v) < need:
            print("TOO_FEW_SAMPLES n=%d need=%d" % (len(v), need))
            return E['noedge']
        print("STEADY sig=%s n=%d min=%.6g max=%.6g mean=%.6g"
              % (sig, len(v), min(v), max(v), sum(v) / len(v)))
        return 0

    if mode == 'propdelay':
        si, so = opt.get('sig-in'), opt.get('sig-out')
        if not si or not so:
            print("BAD_USAGE propdelay needs --sig-in and --sig-out")
            return E['usage']
        vdi, vdo = rail('vdd-in', 1.8), rail('vdd-out', 3.3)
        if vdi is None or vdo is None:
            return E['badnum']
        ein = opt.get('edge-in') or opt.get('edge') or 'rise'
        # The legacy interface took one --edge for BOTH signals and meant "same phase", so that is
        # what it still means; an inverting chain must say so with --edge-in/--edge-out. Defaulting
        # the output to the opposite direction silently re-judged every existing same-phase caller.
        eout = opt.get('edge-out') or ein
        if not opt.get('edge-out') and not opt.get('edge-in'):
            legacy_iface_note = ' legacy_edge_interface=same_direction'
        else:
            legacy_iface_note = ''
        ssr, sor = series(si), series(so)
        if ssr is None or sor is None:
            return E['nosig']
        ci, _ai = attempts([x[0] for x in ssr], [x[1] for x in ssr], vdi, ein)
        co, ao = attempts([x[0] for x in sor], [x[1] for x in sor], vdo, eout)
        if not ci:
            print("NO_EDGE propdelay input %s %s produced no complete event" % (si, ein))
            return E['noedge']
        # Propagation delay is defined at 50 % of each rail, not at the 10/90 % slew endpoints.
        # Complete attempts (above) say WHICH excursion is a real event; the 50 % crossing inside it
        # says WHEN. Using the 10 % point as the timing reference reported t_in=2.1 ns for a 50 %
        # crossing that is really at 2.5 ns.
        def half(tt, vv, vdd, direction, spans):
            lvl = 0.5 * vdd
            for (s0, s1) in spans:
                for i in range(1, len(vv)):
                    # the sample interval must OVERLAP the attempt span; requiring a sample to lie
                    # inside it fails for a fast edge that crosses every threshold within one
                    # interval, which silently left the 10 % point being reported as t_in/t_out
                    if tt[i] < s0 or tt[i - 1] > s1:
                        continue
                    a, b = vv[i - 1], vv[i]
                    if b == a:
                        continue
                    if direction == 'up' and a < lvl <= b:
                        return interp(tt[i - 1], a, tt[i], b, lvl)
                    if direction == 'down' and b < lvl <= a:
                        return interp(tt[i - 1], a, tt[i], b, lvl)
            return None
        spans_i = [(x[0], x[1]) for x in ci]
        spans_o = [(x[0], x[1]) for x in co]
        ti = half([x[0] for x in ssr], [x[1] for x in ssr], vdi,
                  'up' if ein == 'rise' else 'down', [(ci[0][0], ci[0][1])])
        tin = ci[0][0] if ti is None else ti
        cand = [e for e in co if e[0] >= tin]
        if not cand:
            print("NO_EDGE propdelay output %s %s has no complete event at or after the input "
                  "crossing (out_complete=%d out_abandoned=%d)" % (so, eout, len(co), len(ao)))
            return E['noedge']
        sel = cand[0]
        to = half([x[0] for x in sor], [x[1] for x in sor], vdo,
                  'up' if eout == 'rise' else 'down', [(sel[0], sel[1])])
        if to is None:
            to = sel[0]
        # A same-direction query can pair with a LATER, unrelated response. The opposite-direction
        # event that begins sooner is the actual answer to this input edge, so say so rather than
        # returning a number that looks like a propagation delay.
        eopp = 'fall' if eout == 'rise' else 'rise'
        co_o, _ = attempts([x[0] for x in sor], [x[1] for x in sor], vdo, eopp)
        earlier = [x for x in co_o if tin <= x[0] < sel[0]]
        marker = ('earlier_opposite_event=%s' % ('YES' if earlier else 'no'))
        print("PROPDELAY %s(%s)->%s(%s) t_in=%.6e t_out=%.6e delay_ns=%.3f in_ev=%d out_ev=%d %s%s"
              % (si, ein, so, eout, tin, to, (to - tin) * 1e9, len(ci), len(co), marker,
                 legacy_iface_note))
        return 0

    sig = opt.get('sig')
    if not sig:
        print("BAD_USAGE edge needs --sig")
        return E['usage']
    vdd = rail('vdd', 3.3)
    if vdd is None:
        return E['badnum']
    edge = opt.get('edge', 'fall')
    s = series(sig)
    if s is None:
        return E['nosig']
    tt = [x[0] for x in s]
    vv = [x[1] for x in s]
    if len(tt) < 2:
        print("NO_EDGE sig=%s fewer than two samples in window (n=%d)" % (sig, len(tt)))
        return E['noedge']
    if len(vv) < need:
        print("TOO_FEW_SAMPLES n=%d need=%d" % (len(vv), need))
        return E['noedge']
    comp, aband = attempts(tt, vv, vdd, edge)
    first_complete_start = comp[0][0] if comp else None
    if ev_pol == 'first_attempt' and aband and (
            first_complete_start is None or aband[0][0] < first_complete_start):
        print("NO_EDGE sig=%s %s: first attempt starting %.6e collapsed before the far threshold "
              "(complete=%d abandoned=%d policy=%s)"
              % (sig, edge, aband[0][0], len(comp), len(aband), ev_pol))
        return E['noedge']
    if not comp:
        print("NO_EDGE sig=%s %s: no complete 10-90%% event (range=[%.6g,%.6g] abandoned=%d)"
              % (sig, edge, min(vv), max(vv), len(aband)))
        return E['noedge']
    t0, t1 = comp[0][0], comp[0][1]
    inside = [v for (x, v) in zip(tt, vv) if t0 <= x <= t1]
    seq = 1 + len([c for c in comp if c[0] < t0]) + len([x for x in aband if x[0] < t0])
    print("EDGE %s sig=%s t_start=%.6e t_end=%.6e duration_ns=%.3f samples_in_edge=%d "
          "event=%d policy=%s level_min=%.6g level_max=%.6g"
          % (edge, sig, t0, t1, (t1 - t0) * 1e9, len(inside), seq, ev_pol, min(vv), max(vv)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
