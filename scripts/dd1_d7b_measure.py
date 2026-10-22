# -*- coding: utf-8 -*-
"""DATA-7B measurement core: charge, crossings, sustained in-band and turn-off.

    python scripts/dd1_d7b_measure.py --selftest

One implementation on purpose. The native run and the offline evidence re-check both call this module,
so a reported number and a recomputed number cannot mean different things (the S1 lesson: two
entrances each "knowing" their own window rule both went green).

Every rule the task book freezes in 6.2 is implemented here:

  * trapezoid integration over the real, unequal sample spacing, with both window boundaries
    interpolated onto the enclosing sample pair -- never "mean of a few points x width";
  * positive and negative halves integrated separately, so a cancelling transient cannot be presented
    as no pulse, and `Qwin == Qpositive + Qnegative` is asserted. Every linear segment that changes
    sign is split at its interpolated zero crossing first: clamping both halves to the segment ends
    doubles each area while the net still looks perfect;
  * 10 %/90 % current crossings are thresholds against the calibrated Ical, found only between two
    bracketing samples with linear interpolation, and reported NOT_FOUND when no bracket exists;
  * every voltage edge is searched around the pulse's own declared RTL/PWL segment edges, never around
    the end of the full window: a short code falls tens of ns after t0 while t1 is the window
    boundary. A declared edge with no bracketing pair stays NOT_FOUND and fails the judgement, and a
    window that conducts without declaring its segments is refused rather than measured against t1;
  * sustained in-band time needs the current to stay inside Ical +/- 5 % for at least 10 ns all the way
    up to this pulse's declared off edge; a run that satisfies 10 ns and then leaves the band says
    NOT_SETTLED_WITHIN_PULSE, and the longest in-band run is reported beside it as a separate,
    sample-bounded quantity;
  * turn-off needs |I| <= 0.15 uA and it must stay there for the rest of the observed segment; a dip
    that comes back above the limit is reported as a transient, and the search continues to the end of
    the segment because a later permanent turn-off is still a real fact;
  * times are whole picoseconds and values are finite; SI is the only internal unit.
"""
from __future__ import print_function

import math
import re

NS = 1000                                     # ps per ns
S_PER_PS = 1e-12                              # the internal time unit is seconds
BAND_REL = 0.05                               # Ical +/- 5 %  (POC_ASSUMPTION, inherited tolerance)
OFF_ABS = 0.15e-6                             # 0.15 uA        (POC_ASSUMPTION, inherited tolerance)
I_REF = 15e-6                                 # the nominal pixel current this project is built on
MIN_IN_BAND_PS = 10 * NS                        # "sustained" means at least 10 ns of in-band time
DE_50_V = 0.9                                   # 50 % of the 1.8 V data_en rail, the edge reference
SETTLED_STATES = ('SETTLED', 'NOT_SETTLED_WITHIN_PULSE',
                  'NO_DATA_IN_PULSE', 'NOT_APPLICABLE_NO_CONDUCTING_EDGE')
TURN_OFF_STATES = ('OFF', 'NOT_PERMANENTLY_OFF_BY_SEGMENT_END', 'NEVER_WITHIN_LIMIT',
                   'NO_DATA_IN_OFF_SEGMENT')


class Refuse(Exception):
    """a refusal is a verdict with a reason, never a silently missing number"""


def parse_time_ps(txt, ctx=''):
    """accept only whole picoseconds; a value that is not an integer number of ps is refused"""
    s = str(txt).strip()
    if not re.match(r'^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$', s):
        raise Refuse('%s: time %r is not a plain number' % (ctx, txt))
    try:
        v = float(s)
    except ValueError:
        raise Refuse('%s: time %r cannot be parsed' % (ctx, txt))
    if not is_finite(v):
        raise Refuse('%s: time %r is not finite' % (ctx, txt))
    ps = v / S_PER_PS
    if abs(ps - round(ps)) > 1e-6:
        raise Refuse('%s: time %r is not a whole number of picoseconds (%r ps): the sample grid '
                     'cannot be trusted for charge integration' % (ctx, txt, ps))
    return int(round(ps))


def parse_value(txt, ctx=''):
    s = str(txt).strip()
    if not re.match(r'^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$', s):
        raise Refuse('%s: value %r is not a plain finite number (x/z, NaN or Inf cannot be '
                     'integrated)' % (ctx, txt))
    v = float(s)
    if not is_finite(v):
        raise Refuse('%s: value %r is not finite' % (ctx, txt))
    return v


def is_finite(v):
    return not (math.isnan(v) or math.isinf(v))


def samples(times_txt, values_txt, ctx=''):
    """[(t_ps, value)] with a strictly increasing, whole-picosecond time axis"""
    if len(times_txt) != len(values_txt):
        raise Refuse('%s: %d times against %d values' % (ctx, len(times_txt), len(values_txt)))
    if not times_txt:
        raise Refuse('%s: no samples at all, which is not evidence of anything' % ctx)
    out = []
    for t, v in zip(times_txt, values_txt):
        tp = parse_time_ps(t, ctx)
        if tp < 0:
            raise Refuse('%s: a negative sample time %d ps' % (ctx, tp))
        if out and tp <= out[-1][0]:
            raise Refuse('%s: sample times repeat or step backwards at %d ps (previous %d ps)'
                         % (ctx, tp, out[-1][0]))
        out.append((tp, parse_value(v, ctx)))
    return out


def parse_time_float_ps(txt, ctx=''):
    """a simulator sample instant: finite, increasing, kept at the precision it was printed with.

    The integer-picosecond rule belongs to declared discrete quantities (PWL edges, tick counts, code
    values), not to a transient grid: this build prints times such as 1.999016675925999e-06 s, which is
    not a whole number of ps. Refusing that would throw away real measurements; silently rounding it
    would invent a grid that does not exist. Instead the caller also records time_quantum_ps, the
    largest half-step of the printed display, so the delivered evidence carries its own bound.
    """
    sv = str(txt).strip()
    if not re.match(r'^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$', sv):
        raise Refuse('%s: sample time %r is not a plain finite number' % (ctx, txt))
    v = float(sv)
    if not is_finite(v):
        raise Refuse('%s: sample time %r is not finite' % (ctx, txt))
    return v / S_PER_PS


def time_quantum_ps(tokens):
    """half of the last printed decimal place, in ps, over the whole time column"""
    worst = 0.0
    for tok in tokens:
        sv = str(tok).strip()
        m = re.match(r'^[+-]?(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$', sv)
        if not m:
            continue
        frac = m.group(2) or ''
        exp = int(m.group(3) or 0)
        place = 10 ** (exp - len(frac)) if frac else 10 ** exp
        worst = max(worst, 0.5 * place)
    return worst / S_PER_PS        # the bound is reported in ps


def float_samples(time_tokens, value_tokens, ctx=''):
    """[(ps float, value)] with the sample grid's own display bound returned alongside"""
    if len(time_tokens) != len(value_tokens):
        raise Refuse('%s: %d times against %d values' % (ctx, len(time_tokens), len(value_tokens)))
    if not time_tokens:
        raise Refuse('%s: no samples at all' % ctx)
    out = []
    prev = None
    for t, v in zip(time_tokens, value_tokens):
        tp = parse_time_float_ps(t, ctx)
        if tp < 0:
            raise Refuse('%s: a negative sample time %r ps' % (ctx, tp))
        if prev is not None and tp <= prev:
            raise Refuse('%s: sample times repeat or step backwards at %r ps' % (ctx, tp))
        out.append((tp, parse_value(v, ctx)))
        prev = tp
    return out, time_quantum_ps(time_tokens)


def interp_pair(samples_ps, t_ps, ctx=''):
    """the value at t_ps, linearly between the two enclosing samples; outside the data it refuses"""
    if t_ps < samples_ps[0][0] or t_ps > samples_ps[-1][0]:
        raise Refuse('%s: %d ps lies outside the delivered samples [%d, %d] ps, so its value cannot '
                     'be interpolated and must not be extrapolated' % (ctx, t_ps, samples_ps[0][0],
                                                                       samples_ps[-1][0]))
    for i in range(len(samples_ps) - 1):
        t0, v0 = samples_ps[i]
        t1, v1 = samples_ps[i + 1]
        if t0 <= t_ps <= t1:
            if t1 == t0:
                return v0
            return v0 + (v1 - v0) * (t_ps - t0) / float(t1 - t0)
    return samples_ps[-1][1]


def clip_window(samples_ps, a_ps, b_ps, ctx=''):
    """samples of [a, b] with both endpoints interpolated onto the enclosing pairs"""
    if b_ps <= a_ps:
        raise Refuse('%s: window %d..%d ps is empty' % (ctx, a_ps, b_ps))
    inside = [(t, v) for t, v in samples_ps if a_ps < t < b_ps]
    head = [(a_ps, interp_pair(samples_ps, a_ps, ctx))]
    tail = [(b_ps, interp_pair(samples_ps, b_ps, ctx))]
    pts = head + inside + tail
    for i in range(len(pts) - 1):
        if pts[i + 1][0] <= pts[i][0]:
            raise Refuse('%s: the clipped window is not strictly increasing at %d ps'
                         % (ctx, pts[i + 1][0]))
    return pts


def trapezoid(pts):
    """integral over the real unequal spacing, in (unit of x) * (unit of y); x in ps here"""
    total = 0.0
    for i in range(len(pts) - 1):
        t0, v0 = pts[i]
        t1, v1 = pts[i + 1]
        total += (t1 - t0) * (v0 + v1) / 2.0
    return total * S_PER_PS                        # ps * A -> C


def signed_areas(pts):
    """positive and negative areas of the piecewise-linear curve, split at every zero crossing

    Clipping the endpoint values and then trapezoid-ing them doubles each half when a segment crosses
    zero (a 0..2 ns ramp from -1 A to +1 A has +/-5e-10 C of area, not +/-1e-9 C), while the net still
    cancels to zero -- so the identity alone could never notice.
    """
    qp = 0.0
    qn = 0.0
    crossings = 0
    for i in range(len(pts) - 1):
        t0, v0 = pts[i]
        t1, v1 = pts[i + 1]
        dt = t1 - t0
        if dt <= 0:
            continue
        if v0 >= 0.0 and v1 >= 0.0:
            qp += dt * (v0 + v1) / 2.0
        elif v0 <= 0.0 and v1 <= 0.0:
            qn += dt * (v0 + v1) / 2.0
        else:
            tz = t0 + dt * (v0 / (v0 - v1))
            crossings += 1
            if v0 > 0.0:
                qp += (tz - t0) * v0 / 2.0
                qn += (t1 - tz) * v1 / 2.0
            else:
                qn += (tz - t0) * v0 / 2.0
                qp += (t1 - tz) * v1 / 2.0
    return qp * S_PER_PS, qn * S_PER_PS, crossings


def integrate(samples_ps, a_ps, b_ps, ctx=''):
    """net, positive and negative charge over [a, b], with the identity asserted"""
    pts = clip_window(samples_ps, a_ps, b_ps, ctx)
    q = trapezoid(pts)
    qp, qn, crossings = signed_areas(pts)
    tol = max(1e-30, abs(q) * 1e-9)
    if abs(q - (qp + qn)) > tol:
        raise Refuse('%s: Qwin %r does not equal Qpositive + Qnegative %r' % (ctx, q, qp + qn))
    return {'q': q, 'q_pos': qp, 'q_neg': qn, 'points': len(pts),
            'zero_crossings': crossings,
            'first_s': pts[0][0], 'last_s': pts[-1][0]}


def crossing(samples_ps, thr, rising, lo_ps, hi_ps, ctx=''):
    """first 50 %-style crossing of `thr` inside [lo, hi] using adjacent samples + interpolation"""
    pts = [(t, v) for t, v in samples_ps if lo_ps <= t <= hi_ps]
    if len(pts) < 2:
        return None
    for i in range(len(pts) - 1):
        t0, v0 = pts[i]
        t1, v1 = pts[i + 1]
        if t1 == t0:
            continue
        if rising and v0 <= thr < v1:
            return t0 + (thr - v0) * (t1 - t0) / (v1 - v0)
        if (not rising) and v0 >= thr > v1:
            return t0 + (thr - v0) * (t1 - t0) / (v1 - v0)
    return None


def extreme(samples_ps, lo_ps, hi_ps, want_max=True):
    pts = [(t, v) for t, v in samples_ps if lo_ps <= t <= hi_ps]
    if not pts:
        return None, None
    best = max(pts, key=lambda p: p[1]) if want_max else min(pts, key=lambda p: p[1])
    return best[1], best[0]


def _level_cross(t0, v0, t1, v1, level):
    """where the straight line between two samples equals `level`, or None if it never does"""
    if v1 == v0:
        return None
    frac = (level - v0) / (v1 - v0)
    if not 0.0 <= frac <= 1.0:
        return None
    return t0 + frac * (t1 - t0)


def _clipped_span(t0, v0, t1, v1, band_lo, band_hi):
    """the part of one sample segment on which the linear value is inside the band, or None"""
    cuts = [t0, t1]
    for level in (band_lo, band_hi):
        c = _level_cross(t0, v0, t1, v1, level)
        if c is not None:
            cuts.append(c)
    cuts = sorted(set(cuts))
    inside = []
    for a, b in zip(cuts, cuts[1:]):
        mid = v0 + (v1 - v0) * ((a + b) / 2.0 - t0) / (t1 - t0) if t1 != t0 else v0
        if band_lo <= mid <= band_hi:
            inside.append((a, b))
    if not inside:
        return None
    return inside[0][0], inside[-1][1]


def band_spans(pts, band_lo, band_hi):
    """maximal continuous spans where the piecewise-linear curve stays inside the band

    The samples are points on a curve, not the whole of it: a signal that is in band at 20 ns and
    still in band at the deadline may have left the band at 21 ns in between, which is exactly what a
    sample-only rule missed. Each segment is clipped at the level crossings and the touching pieces
    are merged, so a span's ends are where the curve really entered and left.
    """
    spans = []
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t1 <= t0:
            continue
        piece = _clipped_span(t0, v0, t1, v1, band_lo, band_hi)
        if piece is None:
            continue
        if spans and abs(piece[0] - spans[-1][1]) <= 1e-9:
            spans[-1] = (spans[-1][0], piece[1])
        else:
            spans.append(piece)
    return spans


def _in_band_runs(pts, band_lo, band_hi):
    """maximal in-band runs [first, last] over the real sample sequence

    A run is bounded by the first and last sample that are inside the band, so its span is a
    difference of delivered sample times and can be re-derived by hand from the sample list.
    """
    runs = []
    start = None
    prev = None
    for i, (t, v) in enumerate(pts):
        inside = band_lo <= v <= band_hi
        if inside:
            if start is None:
                start = t
            prev = t
        if (not inside or i == len(pts) - 1) and start is not None:
            runs.append((start, prev))
            start = None
    return runs


def sustained_in_band(samples_ps, t_edge_ps, band_lo, band_hi, until_ps):
    """the value must stay inside the band all the way up to this pulse's own expected off edge

    The deadline is the fall edge declared by the original pulse; it is never moved and the band is
    never widened to make a window look settled. Two things used to be wrong here: dropping every
    sample at or after the deadline and treating the last in-band sample as if it held until the
    deadline, and asking only for *a* 10 ns piece anywhere. The curve is now evaluated up to the
    deadline itself -- the segment that straddles it is cut at the deadline and its left limit has to
    be in band -- so leaving the band 4 ns before the edge cannot pass.

    The sample-bounded run and the continuous span are both reported and never mixed up: the first
    is a difference of delivered sample times a reviewer can re-derive from the shard, the second is
    what the interpolated curve actually held for.
    """
    if float(until_ps) <= float(t_edge_ps):
        return {'status': 'NO_DATA_IN_PULSE', 'settled_ps': None, 'settled_sample_ps': None,
                'held_ps': None, 'checked_points': 0, 'longest_in_band_ps': 0.0,
                'longest_in_band_interp_ps': 0.0, 'band_left_at_ps': None,
                'deadline_left_limit_A': None, 'until_ps': until_ps,
                'band_lo_A': band_lo, 'band_hi_A': band_hi}
    # the points the reviewer can re-derive from the shard: the pulse edge plus the delivered samples
    # strictly inside this pulse. The deadline point is added separately, because it is interpolated.
    body = [(t_edge_ps, interp_pair(samples_ps, t_edge_ps, 'in-band edge'))]
    body += [(t, v) for t, v in samples_ps if t_edge_ps < t < until_ps]
    pts = body + [(float(until_ps), interp_pair(samples_ps, until_ps, 'in-band deadline'))]
    runs = _in_band_runs(body, band_lo, band_hi)
    longest_samples = max([(e - s) for s, e in runs], default=0.0)
    spans = band_spans(pts, band_lo, band_hi)
    longest_interp = max([(e - s) for s, e in spans], default=0.0)
    left = max([e for s, e in spans if e < float(until_ps) - 1e-9], default=None)
    out = {'checked_points': len(pts), 'longest_in_band_ps': longest_samples,
           'longest_in_band_interp_ps': longest_interp, 'deadline_left_limit_A': pts[-1][1],
           'band_left_at_ps': left, 'until_ps': until_ps,
           'band_lo_A': band_lo, 'band_hi_A': band_hi}
    reached = [s for s, e in spans if abs(e - float(until_ps)) <= 1e-9]
    if reached and (float(until_ps) - min(reached)) >= MIN_IN_BAND_PS:
        start = min(reached)
        out.update({'status': 'SETTLED', 'settled_ps': start, 'held_ps': until_ps - start,
                    'settled_sample_ps': next((t for t, v in body
                                               if t >= start and band_lo <= v <= band_hi), None)})
        return out
    out.update({'status': 'NOT_SETTLED_WITHIN_PULSE', 'settled_ps': None, 'held_ps': None,
                'settled_sample_ps': None})
    return out


def window_bounds(samples_ps, lo_ps, hi_ps):
    """the part of [lo, hi] the delivered samples really cover, clamped at the simulation ends

    A window bound can legitimately be the stop of the run: there is nothing to interpolate past it,
    and extrapolating would invent a value. The clamp is returned so the caller can state the span it
    actually integrated instead of quietly reporting the declared one.
    """
    if not samples_ps:
        return None, None
    first, last = samples_ps[0][0], samples_ps[-1][0]
    a, b = max(float(lo_ps), float(first)), min(float(hi_ps), float(last))
    if b < a:
        return None, None
    return a, b


def window_curve(samples_ps, lo_ps, hi_ps, ctx=''):
    """the piecewise-linear curve clipped to the covered part of one window"""
    a, b = window_bounds(samples_ps, lo_ps, hi_ps)
    if a is None:
        return []
    return clip_window(samples_ps, a, b, ctx)


def turn_off(samples_ps, t_edge_ps, limit_abs, seg_end_ps):
    """earliest time after the fall edge from which |value| stays <= limit to the end of the segment

    A candidate that later rebounds is reported, but it does not end the search: a transient dip
    below the limit is not a permanent turn-off, and the real turn-off may still exist further on.
    """
    pts = [(t_edge_ps, interp_pair(samples_ps, t_edge_ps, 'turn-off edge'))]
    pts += [(t, v) for t, v in samples_ps if t_edge_ps < t < seg_end_ps]
    pts.append((seg_end_ps, interp_pair(samples_ps, seg_end_ps, 'turn-off end')))
    if len(pts) < 2:
        return {'status': 'NO_DATA_IN_OFF_SEGMENT', 'off_ps': None}
    first_candidate = None
    first_rebound = None
    for i, (t, v) in enumerate(pts):
        if abs(v) > limit_abs:
            continue
        if first_candidate is None:
            first_candidate = (t, v)
        over = [p for p in pts[i:] if abs(p[1]) > limit_abs]
        if not over:
            return {'status': 'OFF', 'off_ps': t, 'overshoot_after': 0,
                    'checked_points': len(pts) - i,
                    'transient_off_ps': None if first_candidate[0] == t else first_candidate[0]}
        if first_rebound is None:
            first_rebound = over[0]
    if first_candidate is not None:
        return {'status': 'NOT_PERMANENTLY_OFF_BY_SEGMENT_END', 'off_ps': None,
                'transient_off_ps': first_candidate[0],
                'first_rebound_ps': first_rebound[0], 'value_at_rebound': first_rebound[1],
                'checked_points': len(pts)}
    return {'status': 'NEVER_WITHIN_LIMIT', 'off_ps': None, 'checked_points': len(pts)}


def validate_case_ids(ids, required):
    """the case table must carry every required case exactly once (task book 8.1 break test 4)"""
    seen = {}
    for i, cid in enumerate(ids):
        if cid in seen:
            raise Refuse('case table repeats %s at rows %d and %d' % (cid, seen[cid], i))
        seen[cid] = i
    missing = [r for r in required if r not in seen]
    if missing:
        raise Refuse('case table is missing required case(s) %s' % ', '.join(sorted(missing)))
    extra = [c for c in seen if c not in set(required)]
    if extra:
        raise Refuse('case table carries unknown case(s) %s' % ', '.join(sorted(extra)))
    return seen


def tail_segment_max_abs(samples_ps, a_ps, b_ps):
    pts = [(t, abs(v)) for t, v in samples_ps if a_ps <= t <= b_ps]
    if not pts:
        return None, None
    best = max(pts, key=lambda p: p[1])
    return best[1], best[0]        # (value, time), the same order as extreme()


def measure_window(win, ical, tick_ps, tail_ns=200, ctx=''):
    """all 6.2 quantities for one simulated window"""
    cur = win['current']                      # [(t_ps, ampere)] already validated
    den = win['de']                           # data_en (the PWL node) samples
    deb = win.get('de_b')                     # the real inverter output node, when saved
    t0 = int(win['t0_ps'])
    t1 = int(win['t1_ps'])
    tail_to = t1 + int(tail_ns) * NS
    n_intervals = float(win['expected_intervals'])
    q_exp = ical * n_intervals * tick_ps * S_PER_PS
    q_lsb = ical * tick_ps * S_PER_PS
    out = {'t0_ps': t0, 't1_ps': t1, 'tail_to_ps': tail_to,
           'expected_intervals': n_intervals, 'tick_ps': tick_ps,
           'q_expected_C': q_exp, 'q_lsb_C': q_lsb}
    main = integrate(cur, t0, t1, '%s window' % ctx)
    tail = integrate(cur, t1, tail_to, '%s tail' % ctx)
    out['q_win'] = main
    out['q_tail'] = tail
    out['charge_error_LSB'] = (main['q'] - q_exp) / q_lsb if q_lsb else None
    out['charge_error_pC'] = (main['q'] - q_exp) * 1e12
    # the declared positive direction is "from the clamp into the DUT pin". A window that delivers
    # only negative current with no positive half at all is a flipped ammeter, not a dark pixel.
    tiny = abs(q_lsb) * 1e-9
    out['probe_direction_suspect'] = (main['q'] < -tiny and main['q_pos'] <= tiny)
    # a second, un-normalised view of the same charge: referenced to the nominal 15 uA, so that an
    # Ical a little off the nominal cannot hide a gain error behind the LSB scale
    if n_intervals > 0.0:
        q_ref = I_REF * n_intervals * tick_ps * S_PER_PS
        out['gain_error_vs_15uA'] = (main['q'] - q_ref) / q_ref
        out['abs_gain_error_vs_15uA'] = abs(out['gain_error_vs_15uA'])
    else:
        out['gain_error_vs_15uA'] = None
        out['abs_gain_error_vs_15uA'] = None
    peak, tpeak = extreme(cur, t0, t1, True)
    low, tlow = extreme(cur, t0, t1, False)
    out['window_peak'] = {'value': peak, 't_ps': tpeak}
    out['window_min'] = {'value': low, 't_ps': tlow}
    tpeak_tail, tpeak_tail_at = extreme(cur, t1, tail_to, True)
    out['tail_peak'] = {'value': tpeak_tail, 't_ps': tpeak_tail_at}

    # The pulse is located by its own declared RTL/PWL edges, never by the end of the full window:
    # a short code's falling edge sits tens of ns after t0 while t1 is the window boundary. Substituting
    # t1 for a missing crossing reported the window end as the turn-off instant.
    segs = win.get('pulse_segments_ps')
    if segs is None:
        segs = ([] if win.get('pulse_rise_ps') is None
                else [[int(win['pulse_rise_ps']), int(win['pulse_fall_ps'])]])
    segs = [[int(s[0]), int(s[1])] for s in segs]
    rise_at = segs[0][0] if segs else None
    fall_at = segs[-1][1] if segs else None
    search = 50 * NS
    rise = None
    fall = None
    out['declared_pulses'] = len(segs)
    # a window that is supposed to conduct must declare its own pulse edges: without them every edge
    # question would have to be answered from the window boundary, which is exactly the old defect
    if (n_intervals > 0.0) != bool(segs):
        raise Refuse('%s: %r expected interval(s) but %d declared pulse segment(s)'
                     % (ctx, n_intervals, len(segs)))
    if n_intervals <= 0.0:
        out['de_rise_50_ps'] = 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
        out['de_fall_50_ps'] = 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
        out['de_fall_delay_ps'] = None
        out['pulse_edges_missing_ps'] = []
    else:
        missing = []
        for i, (rs, fl) in enumerate(segs):
            r = crossing(den, DE_50_V, True, rs - search, rs + search,
                         '%s de-rise[%d]' % (ctx, i))
            f = crossing(den, DE_50_V, False, fl - search, fl + search,
                         '%s de-fall[%d]' % (ctx, i))
            if r is None:
                missing.append([rs, 'rise'])
            if f is None:
                missing.append([fl, 'fall'])
            if i == 0:
                rise = r
            if i == len(segs) - 1:
                fall = f
        out['de_rise_50_ps'] = rise if rise is not None else 'NOT_FOUND'
        out['de_fall_50_ps'] = fall if fall is not None else 'NOT_FOUND'
        out['de_fall_delay_ps'] = (None if (rise is None or fall is None) else fall - rise)
        out['pulse_edges_missing_ps'] = missing
    if win.get('de_b'):
        # data_en_b is the inverter's output, so its edges are the opposite phase: data_en rising is
        # data_en_b falling, data_en falling is data_en_b rising. Searching for a fall at the fall
        # edge is what made a short window "find" something by luck (the +-50 ns window happened to
        # reach the open edge) while every long window reported NOT_FOUND.
        if rise_at is None and fall_at is None:
            out['de_b_fall_50_ps'] = 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
            out['de_b_rise_50_ps'] = 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
            out['de_and_de_b_edge_gap_ps'] = None
            out['de_b_rise_gap_ps'] = None
        else:
            b_fall = b_rise = None
            if rise_at is not None:
                b_fall = crossing(win['de_b'], DE_50_V, False, int(rise_at) - search,
                                  int(rise_at) + search, '%s de_b fall' % ctx)
            if fall_at is not None:
                b_rise = crossing(win['de_b'], DE_50_V, True, int(fall_at) - search,
                                  int(fall_at) + search, '%s de_b rise' % ctx)
            out['de_b_fall_50_ps'] = b_fall if b_fall is not None else (
                'NOT_APPLICABLE_NO_CONDUCTING_EDGE' if rise is None else 'NOT_FOUND')
            out['de_b_rise_50_ps'] = b_rise if b_rise is not None else (
                'NOT_APPLICABLE_NO_CONDUCTING_EDGE' if fall is None else 'NOT_FOUND')
            out['de_and_de_b_edge_gap_ps'] = (None if (b_fall is None or rise is None)
                                              else b_fall - rise)
            out['de_b_rise_gap_ps'] = None if (b_rise is None or fall is None) else b_rise - fall
    else:
        out['de_b_fall_50_ps'] = 'NOT_SAVED'
        out['de_b_rise_50_ps'] = 'NOT_SAVED'
        out['de_and_de_b_edge_gap_ps'] = None
        out['de_b_rise_gap_ps'] = None
    if rise is None:
        out['current_10pct_ps'] = 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
        out['current_90pct_ps'] = 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
        out['current_rise_10_90_ps'] = None
        out['current_edge_order_ok'] = None
    else:
        hi = int(fall_at if fall_at is not None else t1) + int(tail_ns) * NS + search
        i90 = crossing(cur, 0.9 * ical, True, int(rise_at) - search, hi, '%s i90' % ctx)
        i10 = crossing(cur, 0.1 * ical, True, int(rise_at) - search, hi, '%s i10' % ctx)
        out['current_10pct_ps'] = i10 if i10 is not None else 'NOT_FOUND'
        out['current_90pct_ps'] = i90 if i90 is not None else 'NOT_FOUND'
        out['current_rise_10_90_ps'] = (None if (i90 is None or i10 is None) else i90 - i10)
        # the two crossings must belong to this pulse in this order; a number that happens to be a
        # legal time somewhere else is not evidence that the pulse rose through 10 % then 90 %
        out['current_edge_order_ok'] = (i10 is not None and i90 is not None and i10 < i90
                                        and i10 >= int(rise_at) - search and i90 <= hi)
    # sustained in-band is judged up to this pulse's own expected off edge
    until_band = int(fall_at) if (fall_at is not None and n_intervals > 0.0) else t1
    edge = rise if rise is not None else (int(rise_at) if rise_at is not None else float(t0))
    if n_intervals <= 0.0:
        out['settled'] = {'status': 'NOT_APPLICABLE_NO_CONDUCTING_EDGE', 'settled_ps': None,
                          'longest_in_band_ps': 0.0, 'checked_points': 0}
    else:
        out['settled'] = sustained_in_band(cur, edge, ical * (1 - BAND_REL),
                                           ical * (1 + BAND_REL), until_band)
    # with no conducting edge there is no turn-off to time, so the off segment starts at t0 and the
    # delay stays None instead of inventing a delay against the window boundary
    off_start = fall if fall is not None else (int(fall_at) if fall_at is not None else float(t0))
    out['off_segment_start_ps'] = off_start
    out['turn_off'] = turn_off(cur, off_start, OFF_ABS, tail_to)
    # the same limit read as a continuous quantity: the first place the straight line between two
    # delivered samples passes through it. It is printed beside the sample instant, never instead of
    # it, because "the first sample at or below 150 nA" and "the curve crossed 150 nA" are two
    # different precisions of one event.
    out['off_crossing_ps'] = crossing(cur, OFF_ABS, False, int(round(off_start)), tail_to,
                                      '%s off crossing' % ctx)
    out['turn_off_delay_ps'] = (None if (out['turn_off'].get('off_ps') is None or fall is None)
                                else out['turn_off']['off_ps'] - off_start)
    last100 = tail_segment_max_abs(cur, tail_to - 100 * NS, tail_to)
    out['last_100ns_max_abs_A'] = last100[0]
    out['last_100ns_ok'] = (last100[0] is not None and last100[0] <= OFF_ABS)
    return out

def judge(out, tol_lsb=0.5):
    """the 6.3 feasibility judgement for one window, separate from the evidence judgement"""
    reasons = []
    if out.get('probe_direction_suspect'):
        reasons.append('the whole window current is negative: the probe direction is suspect, '
                       'not the pixel')
    if out['charge_error_LSB'] is None:
        reasons.append('no LSB scale (zero tick or zero Ical)')
    elif abs(out['charge_error_LSB']) > tol_lsb:
        reasons.append('charge_error_LSB=%+.3f exceeds +/- %.1f'
                       % (out['charge_error_LSB'], tol_lsb))
    if not out['last_100ns_ok']:
        reasons.append('the last 100 ns of the off window carries %r A'
                       % out['last_100ns_max_abs_A'])
    if out.get('pulse_edges_missing_ps'):
        reasons.append('%d declared pulse edge(s) were not found in the delivered samples'
                       % len(out['pulse_edges_missing_ps']))
    if out['settled']['status'] not in SETTLED_STATES:
        reasons.append('settle status %s is not a stated outcome' % out['settled']['status'])
    if out['turn_off'].get('status') not in TURN_OFF_STATES:
        reasons.append('turn-off status %s is not a stated outcome'
                       % out['turn_off'].get('status'))
    return ('PASS' if not reasons else 'FAIL'), reasons


# ------------------------------------------------------------------ offline self test
def _micro(v):
    return v * 1e-6


def _win(current, de, t0, t1, intervals, tick_ps=30000, ical=_micro(15.0), pulse=None,
         segments=None):
    """a synthetic window; the declared pulse comes from `segments`, else from the data_en levels"""
    if segments is None:
        if pulse is None:
            hi = [t for t, v in de if v >= 0.9]
            lo = [t for t, v in de if v < 0.9 and t > min(hi, default=0)]
            pulse = (min(hi) if hi else None, max(lo) if (hi and lo) else None)
        segments = [] if pulse[0] is None else [[pulse[0], pulse[1]]]
    return {'current': samples([str(t * 1e-12) for t, _ in current],
                               ['%.9g' % v for _, v in current], 'current'),
            'de': samples([str(t * 1e-12) for t, _ in de], ['%.9g' % v for _, v in de], 'de'),
            't0_ps': t0, 't1_ps': t1, 'expected_intervals': intervals,
            'pulse_segments_ps': [[int(a), int(b)] for a, b in segments],
            'pulse_rise_ps': segments[0][0] if segments else None,
            'pulse_fall_ps': segments[-1][1] if segments else None}


def selftest():
    """hand-computable waveforms only; the circuit under test is never the checker's own case"""
    bad = []
    n = 0

    def expect(name, cond):
        if not cond:
            bad.append('%s did not hold' % name)
        return bool(cond)

    def refuse(name, fn):
        try:
            fn()
        except Refuse:
            return True
        except Exception as exc:
            bad.append('%s raised %r instead of refusing' % (name, exc))
            return False
        bad.append('%s did not refuse' % name)
        return False

    def near(name, got, want, tol=1e-18):
        if got is None or abs(got - want) > tol + abs(want) * 1e-9:
            bad.append('%s got %r want %r' % (name, got, want))
            return False
        return True

    ok = True
    # 1 trapezoid over unequal steps: triangle 2000 + rectangle 8000 ps*A
    n += 1
    s = samples(['0e-9', '1e-9', '3e-9'], ['0', '4', '4'], 'T1')
    ok &= near('T1 net', integrate(s, 0, 3000, 'T1')['q'], 10000 * 1e-12, 1e-21)
    # 2 window clipping interpolates both boundaries
    n += 1
    got = integrate(s, 500, 2500, 'T2')
    ok &= near('T2 clipped', got['q'], 7500 * 1e-12, 1e-21)
    ok &= expect('T2 points 3', got['points'] == 3)
    # 3 positive and negative halves, re-derived by hand with the zero crossing taken as a real
    #    vertex: +500*5/2 + 1000*5 = 6250 ps*A on each side, not the endpoint-clipped 7500.
    n += 1
    s3 = samples(['0e-9', '1e-9', '2e-9', '3e-9'], ['5', '5', '-5', '-5'], 'T3')
    g3 = integrate(s3, 0, 3000, 'T3')
    ok &= near('T3 net', g3['q'], 0.0, 1e-24)
    ok &= near('T3 pos', g3['q_pos'], 6250e-12, 1e-21)
    ok &= near('T3 neg', g3['q_neg'], -6250e-12, 1e-21)
    ok &= expect('T3 one zero crossing', g3['zero_crossings'] == 1)
    # 3b the reviewer's single ramp through zero: +/-5e-10 C, the endpoint method doubled both
    n += 1
    g3b = integrate([(0, -1.0), (2000, 1.0)], 0, 2000, 'T3b')
    ok &= near('T3b pos', g3b['q_pos'], 5e-10, 1e-24)
    ok &= near('T3b neg', g3b['q_neg'], -5e-10, 1e-24)
    ok &= near('T3b net', g3b['q'], 0.0, 1e-24)
    # 4 an integration range outside the delivered samples is refused, never extrapolated
    n += 1
    ok &= refuse('T4 outside', lambda: integrate(s, 0, 5000, 'T4'))
    # 5 a crossing only counts when two samples bracket it
    n += 1
    sc = samples(['0e-9', '1e-9'], ['0', '1'], 'T5')
    ok &= expect('T5 interpolated', crossing(sc, 0.5, True, 0, 1000, 'T5') == 500)
    ok &= expect('T5 no bracket', crossing(sc, 2.0, True, 0, 1000, 'T5') is None)
    # 6 sustained in-band must hold to the off edge: a 15 ns piece inside a 30 ns pulse is not it
    n += 1
    g = sustained_in_band([(0, 0.5), (2000, 1.0), (20000, 1.0)], 0, 0.95, 1.05, 20000)
    # hand: the rise is the straight line (0, 0.5) -> (2000, 1.0), so it enters 0.95 at
    #       0 + (0.95 - 0.5)/(1.0 - 0.5) * 2000 = 1800 ps and stays there to the 20000 ps deadline.
    #       held = 20000 - 1800 = 18200 ps >= 10 ns, so this settles at 1800 ps; the first delivered
    #       sample inside the band is still the 2000 ps one, and that is reported separately.
    ok &= expect('T6 settled', g['status'] == 'SETTLED')
    ok &= near('T6 settled at', g['settled_ps'], 1800, 1e-9)
    ok &= expect('T6 settled sample', g['settled_sample_ps'] == 2000)
    ok &= near('T6 held', g['held_ps'], 18200, 1e-9)
    n += 1
    g = sustained_in_band([(0, 1.0), (5000, 1.0), (6000, 0.5), (20000, 0.5)], 0, 0.95, 1.05, 20000)
    ok &= expect('T6b in-then-out refused', g['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    # hand: samples in band are 0 and 5000, the band is left at 6000 -> run [0, 5000] = 5000 ps
    ok &= near('T6b longest run', g['longest_in_band_ps'], 5000, 1e-9)
    # hand: the 5000 -> 6000 line crosses 0.95 at 5000 + (1.0 - 0.95)/(1.0 - 0.5) * 1000 = 5100 ps
    ok &= near('T6b band left at', g['band_left_at_ps'], 5100, 1e-9)
    n += 1
    g = sustained_in_band([(0, 1.0), (15000, 1.0), (16000, 0.5), (30000, 0.5)], 0, 0.95, 1.05,
                          30000)
    ok &= expect('T6c reviewer case', g['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    # hand: in band at 0 and 15000, out at 16000 and 30000 -> run [0, 15000] = 15000 ps
    ok &= near('T6c longest run', g['longest_in_band_ps'], 15000, 1e-9)
    # hand: the 15000 -> 16000 line crosses 0.95 at 15100 ps, 14.9 ns before the deadline
    ok &= near('T6c band left at', g['band_left_at_ps'], 15100, 1e-9)
    # 6d the reviewer's hand counter-example, kept as a permanent regression: value 1 at 0/10/20 ns,
    #    0.5 at 30 ns, band 0.95..1.05, deadline 25 ns. Every sample up to the deadline is in band,
    #    so the sample-only rule answered SETTLED; the line leaves the band at 21 ns and the deadline
    #    left limit is 0.75, so nothing is sustained up to the deadline.
    n += 1
    g = sustained_in_band([(0, 1.0), (10000, 1.0), (20000, 1.0), (30000, 0.5), (40000, 0.5)],
                          0, 0.95, 1.05, 25000)
    ok &= expect('T6d sample run alone would settle', g['longest_in_band_ps'] == 20000)
    ok &= expect('T6d deadline left limit', abs(g['deadline_left_limit_A'] - 0.75) < 1e-12)
    ok &= expect('T6d not settled', g['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    # hand: the 20000 -> 25000 line crosses 0.95 at 20000 + (1.0 - 0.95)/(1.0 - 0.75) * 5000 = 21000
    ok &= near('T6d band left at', g['band_left_at_ps'], 21000, 1e-9)
    # 7 turn-off: a rebound after a first dip does not end the search
    n += 1
    g = turn_off([(0, 1e-9), (1000, 1e-9), (20000, 1e-9)], 0, OFF_ABS, 20000)
    ok &= expect('T7 off at 0', g['status'] == 'OFF' and g['off_ps'] == 0)
    g = turn_off([(0, 0.0), (1000, 2e-7), (2000, 0.0), (10000, 0.0)], 0, OFF_ABS, 10000)
    ok &= expect('T7b later permanent off', g['status'] == 'OFF' and g['off_ps'] == 2000)
    ok &= expect('T7b transient reported', g.get('transient_off_ps') == 0)
    g = turn_off([(0, 0.0), (1000, 2e-7), (10000, 2e-7)], 0, OFF_ABS, 10000)
    ok &= expect('T7c never off', g['status'] == 'NOT_PERMANENTLY_OFF_BY_SEGMENT_END')
    # 8 a full 16-interval window measures exactly its expected charge and passes
    n += 1
    # the current now holds its top exactly to the pulse's own declared off edge (480501 ps), which is
    # what a settling window means; 8b keeps the old shape, whose top ended 451 ps before the edge
    cur = [(0, _micro(15.0)), (20000, _micro(15.0)), (480501, _micro(15.0)),
           (481000, 0.0), (680000, 0.0)]
    de = [(0, 0.0), (499, 0.0), (501, 1.8), (480499, 1.8), (480501, 0.0)]
    w = _win(cur, de, 0, 480000, 16)
    out = measure_window(w, _micro(15.0), 30000, ctx='T8')
    ok &= near('T8 q', out['q_win']['q'], 15e-6 * 480e-9, 1e-18)
    ok &= expect('T8 no charge error', abs(out['charge_error_LSB']) < 1e-6)
    # hand: the deadline is the declared segment end 480501 ps, where the delivered sample says
    #       15.0 uA, and the curve is in band at every point from the 500 ps rise edge on, so the
    #       interpolated span is [500, 480501] and held = 480001 ps.
    ok &= expect('T8 settled', out['settled']['status'] == 'SETTLED')
    ok &= near('T8 settled at', out['settled']['settled_ps'], 500, 1e-9)
    ok &= expect('T8 settled sample', out['settled']['settled_sample_ps'] == 500)
    ok &= near('T8 held', out['settled']['held_ps'], 480001, 1e-9)
    ok &= expect('T8 off', out['turn_off']['status'] == 'OFF')
    ok &= expect('T8 fall edge found', abs(out['de_fall_50_ps'] - 480500) < 1.0)
    ok &= near('T8 fall delay', out['de_fall_delay_ps'], 480000, 2.0)
    ok &= expect('T8 judge', judge(out)[0] == 'PASS')
    # 8b the shape this test used to carry: 15 uA at 480000 and 0 at 481000 with the off edge at
    #    480501. The top left the band at 480050 ps -- before its own off edge -- so under the
    #    deadline rule it is NOT_SETTLED, even though the sample-only rule called it settled.
    n += 1
    cur8b = [(0, _micro(15.0)), (20000, _micro(15.0)), (480000, _micro(15.0)),
             (481000, 0.0), (680000, 0.0)]
    out8b = measure_window(_win(cur8b, de, 0, 480000, 16), _micro(15.0), 30000, ctx='T8b')
    ok &= expect('T8b charge is still right', abs(out8b['charge_error_LSB']) < 1e-6)
    ok &= expect('T8b top ends before the edge',
                 out8b['settled']['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    ok &= near('T8b band left at', out8b['settled']['band_left_at_ps'], 480050, 1e-9)
    # hand: v(t) = 15 uA * (481000 - t)/1000 on [480000, 481000]; at 480501 it is 7.485 uA
    ok &= near('T8b deadline left limit', out8b['settled']['deadline_left_limit_A'],
               _micro(7.485), 1e-18)
    ok &= expect('T8b sample run looked long enough',
                 out8b['settled']['longest_in_band_ps'] == 479500)
    # 9 a short pulse inside the full window: its own falling edge is found at the pulse, and the
    #    window end is never substituted for a crossing. This is the P30-code1 class of defect, where
    #    the search was limited to [t1-500 ns, t1] and an empty result silently became off_ns = t1.
    n += 1
    cur = [(0, 0.0), (500, _micro(3.0)), (3944000, _micro(3.0)), (3946000, 0.0), (11795000, 0.0)]
    de_short = [(0, 0.0), (499, 0.0), (501, 1.8), (3944999, 1.8), (3945001, 0.0), (11795000, 0.0)]
    # hand: the pulse is declared to fall at 3945001 ps, t1 stays the full-window end at 11595000
    w = _win(cur, de_short, 0, 11595000, 1, pulse=(501, 3945001))
    out = measure_window(w, _micro(15.0), 30000, ctx='T9')
    # hand: 0.9 V is crossed 1 ps after the 499/501 pair and 1 ps after the 3944999/3945001 pair
    ok &= expect('T9 rise edge', abs(out['de_rise_50_ps'] - 500) < 1.0)
    ok &= expect('T9 fall edge at the pulse', abs(out['de_fall_50_ps'] - 3945000) < 1.0)
    ok &= expect('T9 fall is not the window end', out['de_fall_50_ps'] < w['t1_ps'] - 500 * NS)
    ok &= near('T9 fall delay', out['de_fall_delay_ps'], 3945000 - 500, 1.0)
    # hand: 3 uA is outside the 14.25..15.75 uA band everywhere, so nothing settles before the edge
    ok &= expect('T9 not settled', out['settled']['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    ok &= expect('T9 deadline is the pulse edge', out['settled']['until_ps'] == 3945001)
    # hand: the first sample at or below 150 nA after the edge is 3946000 and none rises after it
    ok &= expect('T9 off at the sample after the ramp',
                 out['turn_off']['status'] == 'OFF' and out['turn_off']['off_ps'] == 3946000)
    ok &= near('T9 off delay', out['turn_off_delay_ps'], 1000, 1.0)
    ok &= expect('T9 quiet off window', out['last_100ns_ok'] is True)
    ok &= expect('T9 judge fails the charge target', judge(out)[0] == 'FAIL')
    # 9d a declared edge that the delivered samples never bracket is reported NOT_FOUND, and the
    #     judgement names it; the window end is not used to make the row look complete
    n += 1
    cur = [(0, 0.0), (500, _micro(15.0)), (3944000, _micro(15.0)), (3946000, 0.0),
           (11795000, 0.0)]
    de_stuck = [(0, 0.0), (499, 0.0), (501, 1.8), (11795000, 1.8)]
    w = _win(cur, de_stuck, 0, 11595000, 1, pulse=(501, 3945001))
    out = measure_window(w, _micro(15.0), 30000, ctx='T9d')
    ok &= expect('T9d rise still found', abs(out['de_rise_50_ps'] - 500) < 1.0)
    ok &= expect('T9d fall NOT_FOUND, not t1', out['de_fall_50_ps'] == 'NOT_FOUND')
    ok &= expect('T9d the miss is recorded', out['pulse_edges_missing_ps'] == [[3945001, 'fall']])
    ok &= expect('T9d no invented delay', out['de_fall_delay_ps'] is None)
    ok &= expect('T9d the judgement names it',
                 judge(out)[0] == 'FAIL' and any('pulse edge' in r for r in judge(out)[1]))
    # 9e two declared pulses: every one of them is searched for its own edges, and a gap between
    #    pulses is a real gap -- it is not reported as sustained in-band time
    n += 1
    # the second pulse holds its top exactly to its own off edge (8890002 ps) and falls at 8891000
    cur = [(0, 0.0), (500, _micro(15.0)), (3944000, _micro(15.0)), (3946000, 0.0), (4944000, 0.0),
           (4946000, _micro(15.0)), (8890002, _micro(15.0)), (8891000, 0.0), (11795000, 0.0)]
    de_two = [(0, 0.0), (499, 0.0), (501, 1.8), (3945001, 1.8), (3945003, 0.0), (4944999, 0.0),
              (4945001, 1.8), (8890001, 1.8), (8890003, 0.0), (11795000, 0.0)]
    w = _win(cur, de_two, 0, 11595000, 2, segments=[[501, 3945002], [4945001, 8890002]])
    out = measure_window(w, _micro(15.0), 30000, ctx='T9e')
    ok &= expect('T9e two pulses', out['declared_pulses'] == 2)
    ok &= expect('T9e no edge missing', out['pulse_edges_missing_ps'] == [])
    # hand: the first rise brackets 499/501 at 500, the last fall brackets 8890001/8890003 at 8890002
    ok &= expect('T9e first rise', abs(out['de_rise_50_ps'] - 500) < 1.0)
    ok &= expect('T9e last fall', abs(out['de_fall_50_ps'] - 8890002) < 1.0)
    # hand: the deadline is the second pulse's off edge 8890002 ps and the curve is 15.0 uA there.
    #       Coming back up, the 4944000 (0 A) -> 4946000 (15 uA) line enters the band at
    #       4944000 + (14.25/15) * 2000 = 4945900 ps, so the span that reaches the deadline starts
    #       there: settled_ps = 4945900, held = 8890002 - 4945900 = 3944102 ps. The first delivered
    #       sample inside that span is 4946000 -- the sample view, kept apart from the interpolated one.
    ok &= expect('T9e settles on the second pulse', out['settled']['status'] == 'SETTLED')
    ok &= near('T9e settled at', out['settled']['settled_ps'], 4945900, 1e-9)
    ok &= expect('T9e settled sample', out['settled']['settled_sample_ps'] == 4946000)
    ok &= near('T9e held', out['settled']['held_ps'], 3944102, 1e-9)
    # hand: the first run is [500, 3944000] = 3943500 ps and the second is [4946000, 4946000] = 0 ps
    #       over the delivered samples, so the longer of the two is the first one
    ok &= near('T9e longest run', out['settled']['longest_in_band_ps'], 3943500, 1e-9)
    # hand: the continuous spans are [500, 3944100] = 3943600 ps and [4945900, 8890002] = 3944102 ps
    ok &= near('T9e longest interpolated run', out['settled']['longest_in_band_interp_ps'],
               3944102, 1e-9)
    ok &= expect('T9e off after the last pulse',
                 out['turn_off']['status'] == 'OFF' and out['turn_off']['off_ps'] == 8891000)
    # 9f the pulse declaration cannot be missing, invented or contradicted by the interval count
    n += 1
    cur = [(0, 0.0), (500, _micro(15.0)), (480000, _micro(15.0)), (481000, 0.0), (680000, 0.0)]
    ok &= refuse('T9f conducting window without declared edges',
                 lambda: measure_window({'current': [(0, 0.0), (680000, 0.0)],
                                         'de': [(0, 0.0), (680000, 0.0)], 't0_ps': 0, 't1_ps': 480000,
                                         'expected_intervals': 1.0}, _micro(15.0), 30000,
                                        ctx='T9f'))
    ok &= refuse('T9f black window with declared edges',
                 lambda: measure_window(_win(cur, de, 0, 480000, 0, pulse=(501, 480501)),
                                        _micro(15.0), 30000, ctx='T9fb'))
    # 10 a black window has no percentage scale, no held charge and no invented edges
    n += 1
    cur = [(0, 0.0), (480000, 0.0), (680000, 0.0)]
    w = _win(cur, [(0, 0.0), (680000, 0.0)], 0, 480000, 0, pulse=(None, None))
    out = measure_window(w, _micro(15.0), 30000, ctx='T10')
    ok &= expect('T10 zero LSB error', out['charge_error_LSB'] == 0.0)
    ok &= expect('T10 no gain scale', out['abs_gain_error_vs_15uA'] is None)
    ok &= expect('T10 rise N/A', out['de_rise_50_ps'] == 'NOT_APPLICABLE_NO_CONDUCTING_EDGE')
    ok &= expect('T10 fall N/A', out['de_fall_50_ps'] == 'NOT_APPLICABLE_NO_CONDUCTING_EDGE')
    ok &= expect('T10 de_b N/A', out['de_b_fall_50_ps'] == 'NOT_SAVED')
    ok &= expect('T10 current edges N/A',
                 out['current_10pct_ps'] == 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'
                 and out['current_rise_10_90_ps'] is None)
    ok &= expect('T10 no invented delay', out['de_fall_delay_ps'] is None)
    ok &= expect('T10 settle N/A', out['settled']['status'] == 'NOT_APPLICABLE_NO_CONDUCTING_EDGE')
    ok &= expect('T10 off still measured', out['turn_off']['status'] == 'OFF')
    # 11 break test: the ammeter reversed is caught, not honoured
    n += 1
    cur = [(0, -_micro(15.0)), (480000, -_micro(15.0)), (481000, 0.0), (680000, 0.0)]
    w = _win(cur, de, 0, 480000, 16)
    out = measure_window(w, _micro(15.0), 30000, ctx='T11')
    ok &= expect('T11 direction suspect', out['probe_direction_suspect'] is True)
    ok &= expect('T11 direction judged FAIL', judge(out)[0] == 'FAIL')
    # 12 break test: the tail of the integration data is missing
    n += 1
    short = [(0, _micro(15.0)), (300000, _micro(15.0))]
    w = _win(short, de, 0, 480000, 16)
    ok &= refuse('T12 truncated tail', lambda: measure_window(w, _micro(15.0), 30000, ctx='T12'))
    # 13 break test: a case table that repeats or drops a key
    n += 1
    ok &= refuse('T13 duplicate id', lambda: validate_case_ids(['A', 'A'], ['A']))
    ok &= refuse('T13 missing id', lambda: validate_case_ids(['A'], ['A', 'B']))
    ok &= expect('T13 accepted set', validate_case_ids(['A', 'B'], ['A', 'B']) == {'A': 0, 'B': 1})
    # 14 an event-before excerpt cannot stand in for a whole-window integral
    n += 1
    pre = [(0, _micro(1.0)), (5000, _micro(3.0))]
    ok &= refuse('T14 excerpt as evidence', lambda: integrate(pre, 0, 480000, 'T14'))
    # 15 x/z, NaN, Inf and non-numeric spellings refuse; whole-ps spellings do not
    n += 1
    ok &= refuse('T15 nan', lambda: parse_value('nan', 'T15'))
    ok &= refuse('T15 inf', lambda: parse_value('inf', 'T15'))
    ok &= refuse('T15 xz', lambda: parse_value("1'bX", 'T15'))
    ok &= refuse('T15 sub-ps', lambda: parse_time_ps('1e-13', 'T15'))
    ok &= expect('T15 whole ps', parse_time_ps('30.000e-9', 'T15') == 30000)
    ok &= expect('T15 ns rounding', parse_time_ps('0.333e-9', 'T15') == 333)
    # 16 a simulator sample grid is kept at its own precision, with the printed bound
    n += 1
    series, quantum = float_samples(['1.999016675925999e-06', '2.000016675926000e-06'],
                                    ['1e-5', '1e-5'], 'T16')
    ok &= near('T16 ps kept', series[0][0], 1999016.675925999, 1e-6)
    ok &= expect('T16 bound tiny', quantum < 1e-3)
    ok &= refuse('T16 backwards', lambda: float_samples(['2e-6', '1e-6'], ['1', '1'], 'T16'))
    ok &= refuse('T16 empty', lambda: float_samples([], [], 'T16'))
    return ok, bad, n


def main(argv):
    if '--selftest' in argv:
        ok, bad, n = selftest()
        for b in bad:
            print('SELFTEST_BAD %s' % b)
        print('D7B_MEASURE_SELFTEST: %s (%d/%d)'
              % ('PASS' if ok and not bad else 'FAIL', n - len(bad), n))
        return 0 if ok and not bad else 1
    print('usage: dd1_d7b_measure.py --selftest')
    return 2


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
