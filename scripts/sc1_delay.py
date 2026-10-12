#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2A: edge and delay measurement that identifies real events.

    sc1_delay.py --data FILE | --deck DECK.scs --sig NAME --vdd V
                 --mode edge --edge rise|fall [--t0 T --t1 T]
                 [--event first_attempt|first_complete] [--require-n K]
    sc1_delay.py ... --mode propdelay --sig-in A --sig-out B --vdd-in V --vdd-out V
                 [--edge-in rise|fall] [--edge-out rise|fall]
                 [--in-event first|second|N] [--pairing accept|diagnose] [--t0 T --t1 T]
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
 4. (R2B) Attribution. Choosing "the first complete input event" was not enough: the old code then
    paired it with ANY later output event, so a first pulse that was never answered could borrow the
    second cycle's response (12.000 ns for a chain whose real delay is 2.000 ns). An output event is
    now credited to the selected input event only while no further input crossing of either direction
    has happened; outside that window the answer is NO_RESPONSE with a non-zero code. A same-direction
    pairing that is beaten by the opposite-direction event is refused in acceptance mode, and a
    missing 50 % crossing fails instead of falling back to the 10 % point.
"""
from __future__ import print_function
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_read_psf as R

E = {'ok': 0, 'nodata': 2, 'nosig': 3, 'noedge': 4, 'badnum': 5, 'diag': 6,
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
    if opt.get('pairing', 'accept') not in ('accept', 'diagnose'):
        print("BAD_USAGE --pairing must be accept or diagnose")
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
        # what it still means; an inverting chain must say so with --edge-in/--edge-out.
        eout = opt.get('edge-out') or ein
        legacy_iface_note = ('' if (opt.get('edge-in') or opt.get('edge-out'))
                            else ' legacy_edge_interface=same_direction')
        pairing = opt.get('pairing', 'accept')
        ssr, sor = series(si), series(so)
        if ssr is None or sor is None:
            return E['nosig']
        ti_ = [x[0] for x in ssr]
        vi_ = [x[1] for x in ssr]
        to_ = [x[0] for x in sor]
        vo_ = [x[1] for x in sor]
        ci, _ai = attempts(ti_, vi_, vdi, ein)
        co, ao = attempts(to_, vo_, vdo, eout)
        if not ci:
            print("NO_EDGE propdelay input %s %s produced no complete event" % (si, ein))
            print("MEASUREMENT_VALID=NO")
            return E['noedge']

        # Propagation delay is defined at 50 % of each rail, not at the 10/90 % slew endpoints.
        # half() looks only inside the one event span it is given: a missing 50 % crossing is a
        # failure, never a silent fallback to the 10 % point.
        def half(tt, vv, vdd, direction, span):
            lvl = 0.5 * vdd
            s0, s1 = span
            for i in range(1, len(vv)):
                # the sample interval must OVERLAP the event span: requiring a sample inside it
                # loses a fast edge that crosses every threshold within one interval
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

        sel_pol = opt.get('in-event', 'first')
        if sel_pol == 'first':
            k = 0
        elif sel_pol == 'second':
            k = 1
        else:
            try:
                k = int(sel_pol) - 1
            except ValueError:
                print("BAD_USAGE --in-event must be first, second or a 1-based index, got %r" % sel_pol)
                return E['usage']
        if k < 0 or k >= len(ci):
            print("NO_EDGE propdelay requested input event %r but %s has only %d complete %s event(s)"
                  % (sel_pol, si, len(ci), ein))
            print("MEASUREMENT_VALID=NO")
            return E['noedge']
        ev = ci[k]
        tin = half(ti_, vi_, vdi, 'up' if ein == 'rise' else 'down', (ev[0], ev[1]))
        if tin is None:
            print("NO_HALF_CROSSING input %s event %d spans %.6e..%.6e s with no 50%% crossing of "
                  "%.6g V; refusing to quote the 10%% point as a timing reference"
                  % (si, k + 1, ev[0], ev[1], 0.5 * vdi))
            print("MEASUREMENT_VALID=NO")
            return E['noedge']

        # Event attribution. The bound is the next crossing of the input's OWN 50 % level, in either
        # direction -- not the next complete 10-90 % event. A partial excursion that stops above the
        # 10 % threshold is invisible to attempts(), and that is how the reviewer's a1 deck let an
        # unanswered first pulse borrow the second cycle's response and still report 12.000 ns.
        def crossings(tt, vv, vdd):
            lvl = 0.5 * vdd
            xs = []
            for i in range(1, len(vv)):
                a, b = vv[i - 1], vv[i]
                if a == lvl and b != lvl:
                    continue            # a plateau at the level was counted when it was reached
                if b == lvl:
                    xs.append(tt[i])
                elif (a < lvl < b) or (b < lvl < a):
                    xs.append(interp(tt[i - 1], a, tt[i], b, lvl))
            return sorted(xs)

        in_cross = crossings(ti_, vi_, vdi)
        after = [c for c in in_cross if c > tin + 1e-15]
        t_next = after[0] if after else None

        # The candidate is chosen by the time that will actually be reported: the output's 50 % point.
        # Filtering on the event START let a2 keep t_out=8.125 ns while its own printed window closed
        # at 5.1 ns.
        pts = []
        for e in co:
            tv = half(to_, vo_, vdo, 'up' if eout == 'rise' else 'down', (e[0], e[1]))
            if tv is not None and tv >= tin - 1e-15:
                pts.append((e, tv))
        pts.sort(key=lambda x: x[1])
        if not pts:
            overlapping = [e for e in co if e[0] < tin < e[1]]
            if overlapping:
                print("AMBIGUOUS_RESOLUTION %s event %d (t_in=%.6e) falls inside the output event "
                      "span %.6e..%.6e: the sample interval cannot order input against output, so no "
                      "propagation delay is reported (re-run with a finer maxstep)"
                      % (si, k + 1, tin, overlapping[0][0], overlapping[0][1]))
                print("MEASUREMENT_VALID=NO")
                return E['diag']
            print("NO_RESPONSE %s event %d (t_in=%.6e) has no complete %s output event at or after it "
                  "(out_complete=%d out_abandoned=%d); use --in-event to pick the event the waveform "
                  "actually answers, or --pairing diagnose for a non-acceptance look"
                  % (si, k + 1, tin, eout, len(co), len(ao)))
            print("MEASUREMENT_VALID=NO")
            return E['noedge']
        sel, to = pts[0]
        if sel[0] < tin - 1e-15 and pairing != 'diagnose':
            print("AMBIGUOUS_RESOLUTION %s event %d (t_in=%.6e) is measured at t_out=%.6e inside an "
                  "output event that began at %.6e, before the input crossed its own 50 %% level: the "
                  "two edges cannot be ordered at this sampling resolution"
                  % (si, k + 1, tin, to, sel[0]))
            print("MEASUREMENT_VALID=NO")
            return E['diag']
        # t_in <= t_out < t_next, strictly: an output that reaches its measurement point exactly when
        # the input changes again is a race, and it cannot be credited to the earlier event.
        if pairing == 'accept' and t_next is not None and to >= t_next - 1e-15:
            print("OUTSIDE_ATTRIBUTION %s event %d: candidate t_out=%.6e (candidate_delay_ns=%.3f) "
                  "is not inside "
                  "[t_in=%.6e, t_next=%.6e) -- the input crossed its 50 %% level again before the "
                  "output reached its measurement point, so this pairing is NOT_MEASURED; use "
                  "--in-event for the event the waveform answers, or --pairing diagnose to see the "
                  "candidate without certifying it" % (si, k + 1, to, (to - tin) * 1e9, tin, t_next))
            print("MEASUREMENT_VALID=NO")
            return E['noedge']
        # A same-direction pairing on an inverting chain is ambiguous, not merely untidy: the
        # opposite-direction event is the one the input edge actually produced.
        eopp = 'fall' if eout == 'rise' else 'rise'
        co_o, _ = attempts(to_, vo_, vdo, eopp)
        earlier = [x for x in co_o if tin <= x[0] < sel[0]]
        marker = ('earlier_opposite_event=%s' % ('YES' if earlier else 'no'))
        attribution = ('attribution_window=[%.6e,%.6e) t_next=input 50%% crossing' % (tin, t_next)
                       if t_next is not None else 'attribution_window=[%.6e, end_of_data]' % tin)
        valid = 'MEASUREMENT_VALID=NO' if (earlier or pairing == 'diagnose') else 'MEASUREMENT_VALID=YES'
        print("PROPDELAY %s(%s)->%s(%s) event=%d t_in=%.6e t_out=%.6e delay_ns=%.3f in_ev=%d "
              "out_ev=%d %s %s %s%s" % (si, ein, so, eout, k + 1, tin, to, (to - tin) * 1e9,
                                        len(ci), len(co), marker, valid, attribution,
                                        legacy_iface_note))
        if pairing == 'diagnose':
            print('mode=diagnose (informational pairing only, never a circuit verdict)')
            return E['diag']
        if earlier:
            print("%s AMBIGUOUS_POLARITY output %s has a complete %s event at %.6e before the "
                  "same-direction one at %.6e; acceptance mode refuses to call that pair a "
                  "propagation delay (re-run with --edge-out %s, or --pairing diagnose to print it "
                  "as a diagnostic)" % (valid, so, eopp, earlier[0][0], sel[0], eopp))
            return E['diag']
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
