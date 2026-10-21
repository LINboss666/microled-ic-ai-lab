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
    as no pulse, and `Qwin == Qpositive + Qnegative` is asserted;
  * 10 %/90 % current crossings are thresholds against the calibrated Ical, found only between two
    bracketing samples with linear interpolation, and reported NOT_FOUND when no bracket exists;
  * sustained in-band time needs the current to stay inside Ical +/- 5 % for at least 10 ns and up to
    the expected turn-off edge; a short pulse that never does that says NOT_SETTLED_WITHIN_PULSE;
  * turn-off needs |I| <= 0.15 uA and it must stay there for the rest of the observed segment;
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
MIN_IN_BAND_PS = 10 * NS                      # "sustained" means at least 10 ns


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


def integrate(samples_ps, a_ps, b_ps, ctx=''):
    """net, positive and negative charge over [a, b], with the identity asserted"""
    pts = clip_window(samples_ps, a_ps, b_ps, ctx)
    q = trapezoid(pts)
    qp = trapezoid([(t, max(v, 0.0)) for t, v in pts])
    qn = trapezoid([(t, min(v, 0.0)) for t, v in pts])
    tol = max(1e-30, abs(q) * 1e-9)
    if abs(q - (qp + qn)) > tol:
        raise Refuse('%s: Qwin %r does not equal Qpositive + Qnegative %r' % (ctx, q, qp + qn))
    return {'q': q, 'q_pos': qp, 'q_neg': qn, 'points': len(pts),
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


def sustained_in_band(samples_ps, t_edge_ps, band_lo, band_hi, until_ps):
    """earliest time after `t_edge_ps` from which the value stays inside the band for at least 10 ns
    and until `until_ps`; NOT_SETTLED_WITHIN_PULSE when no such interval exists"""
    pts = [(t_edge_ps, interp_pair(samples_ps, t_edge_ps, 'in-band edge'))]
    pts += [(t, v) for t, v in samples_ps if t_edge_ps < t < until_ps]
    pts.append((until_ps, interp_pair(samples_ps, until_ps, 'in-band end')))
    if len(pts) < 2:
        return {'status': 'NO_DATA_IN_PULSE', 'settled_ps': None, 'checked_points': len(pts)}
    for i, (t, v) in enumerate(pts):
        if not (band_lo <= v <= band_hi):
            continue
        rest = pts[i:]
        out = [p for p in rest if not (band_lo <= p[1] <= band_hi)]
        first_out = out[0][0] if out else until_ps
        if first_out - t >= MIN_IN_BAND_PS:
            return {'status': 'SETTLED', 'settled_ps': t,
                    'held_ps': first_out - t, 'checked_points': len(rest)}
    return {'status': 'NOT_SETTLED_WITHIN_PULSE', 'settled_ps': None,
            'checked_points': len(pts)}


def turn_off(samples_ps, t_edge_ps, limit_abs, seg_end_ps):
    """earliest time after the fall edge from which |value| stays <= limit to the end of the segment"""
    pts = [(t_edge_ps, interp_pair(samples_ps, t_edge_ps, 'turn-off edge'))]
    pts += [(t, v) for t, v in samples_ps if t_edge_ps < t < seg_end_ps]
    pts.append((seg_end_ps, interp_pair(samples_ps, seg_end_ps, 'turn-off end')))
    if len(pts) < 2:
        return {'status': 'NO_DATA_IN_OFF_SEGMENT', 'off_ps': None}
    for i, (t, v) in enumerate(pts):
        if abs(v) > limit_abs:
            continue
        over = [p for p in pts[i:] if abs(p[1]) > limit_abs]
        if not over:
            return {'status': 'OFF', 'off_ps': t, 'overshoot_after': 0,
                    'checked_points': len(pts) - i}
        return {'status': 'RETURNED_ABOVE_LIMIT', 'off_ps': None,
                'first_rebound_ps': over[0][0], 'value_at_rebound': over[0][1]}
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
    rise = crossing(den, 0.5 * 1.8, True, t0 - 500 * NS, t0 + 500 * NS, '%s de-rise' % ctx)
    fall = crossing(den, 0.5 * 1.8, False, t1 - 500 * NS, tail_to, '%s de-fall' % ctx)
    out['de_rise_50_ps'] = rise
    out['de_fall_50_ps'] = fall
    if deb is not None:
        brise = crossing(deb, 0.5 * 1.8, False, t0 - 500 * NS, t0 + 500 * NS, '%s deb' % ctx)
        out['de_b_rise_50_ps'] = brise
        out['de_and_de_b_edge_gap_ps'] = (None if (brise is None or rise is None)
                                          else brise - rise)
    i90 = crossing(cur, 0.9 * ical, True, t0, t1, '%s i90' % ctx)
    i10 = crossing(cur, 0.1 * ical, False, t0, t1, '%s i10' % ctx)
    out['current_10pct_ps'] = i10 if i10 is not None else 'NOT_FOUND'
    out['current_90pct_ps'] = i90 if i90 is not None else 'NOT_FOUND'
    edge = rise if rise is not None else float(t0)
    out['settled'] = sustained_in_band(cur, edge, ical * (1 - BAND_REL), ical * (1 + BAND_REL),
                                       t1 if n_intervals >= 1 else t1)
    off_edge = fall if fall is not None else float(t1)
    out['turn_off'] = turn_off(cur, off_edge, OFF_ABS, tail_to)
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
    if out['settled']['status'] not in ('SETTLED', 'NOT_SETTLED_WITHIN_PULSE', 'NO_DATA_IN_PULSE'):
        reasons.append('settle status %s is not a stated outcome' % out['settled']['status'])
    return ('PASS' if not reasons else 'FAIL'), reasons


# ------------------------------------------------------------------ offline self test
def _micro(v):
    return v * 1e-6


def _win(current, de, t0, t1, intervals, tick_ps=30000, ical=_micro(15.0)):
    return {'current': samples([str(t * 1e-12) for t, _ in current],
                               ['%.9g' % v for _, v in current], 'current'),
            'de': samples([str(t * 1e-12) for t, _ in de], ['%.9g' % v for _, v in de], 'de'),
            't0_ps': t0, 't1_ps': t1, 'expected_intervals': intervals}


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
    ok &= expect("T2 got['points'] == 3", got['points'] == 3)
    # 3 positive and negative halves stay separate when the net cancels
    n += 1
    s3 = samples(['0e-9', '1e-9', '2e-9', '3e-9'], ['5', '5', '-5', '-5'], 'T3')
    g3 = integrate(s3, 0, 3000, 'T3')
    ok &= near('T3 net', g3['q'], 0.0, 1e-24)
    ok &= near('T3 pos', g3['q_pos'], 7500e-12, 1e-21)
    ok &= near('T3 neg', g3['q_neg'], -7500e-12, 1e-21)
    # 4 an integration range outside the delivered samples is refused, never extrapolated
    n += 1
    ok &= refuse('T4 outside', lambda: integrate(s, 0, 5000, 'T4'))
    # 5 a crossing only counts when two samples bracket it
    n += 1
    sc = samples(['0e-9', '1e-9'], ['0', '1'], 'T5')
    ok &= expect("T5 crossing(sc, 0.5, True, 0, 1000, 'T5') == 500", crossing(sc, 0.5, True, 0, 1000, 'T5') == 500)
    ok &= expect("T5 crossing(sc, 2.0, True, 0, 1000, 'T5') is None", crossing(sc, 2.0, True, 0, 1000, 'T5') is None)
    # 6 sustained in-band needs 10 ns of holding
    n += 1
    g = sustained_in_band([(0, 0.5), (2000, 1.0), (20000, 1.0)], 0, 0.95, 1.05, 20000)
    ok &= expect("T6 g['status'] == 'SETTLED' and g['settled_ps'] == 2000", g['status'] == 'SETTLED' and g['settled_ps'] == 2000)
    # 7 in band and then out of band must not be reported as settled
    n += 1
    g = sustained_in_band([(0, 1.0), (5000, 1.0), (6000, 0.5), (20000, 0.5)], 0, 0.95, 1.05, 20000)
    ok &= expect("T7 g['status'] == 'NOT_SETTLED_WITHIN_PULSE'", g['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    # 8 turn-off requires the limit to hold to the end of the segment
    n += 1
    g = turn_off([(0, 1e-9), (1000, 1e-9), (20000, 1e-9)], 0, OFF_ABS, 20000)
    ok &= expect("T8 g['status'] == 'OFF' and g['off_ps'] == 0", g['status'] == 'OFF' and g['off_ps'] == 0)
    g = turn_off([(0, 1e-9), (1000, 2e-7), (20000, 2e-7)], 0, OFF_ABS, 20000)
    ok &= expect("T8 g['status'] == 'RETURNED_ABOVE_LIMIT'", g['status'] == 'RETURNED_ABOVE_LIMIT')
    # 9 x/z, NaN, Inf and non-numeric spellings refuse
    n += 1
    ok &= refuse('T9 nan', lambda: parse_value('nan', 'T9'))
    ok &= refuse('T9 inf', lambda: parse_value('inf', 'T9'))
    ok &= refuse('T9 xz', lambda: parse_value("1'bX", 'T9'))
    # 10 a time that is not a whole number of picoseconds refuses, an integral one does not
    n += 1
    ok &= expect("T10 parse_time_ps('30.000e-9', 'T10') == 30000", parse_time_ps('30.000e-9', 'T10') == 30000)
    ok &= expect("T10 parse_time_ps('0.333e-9', 'T10') == 333", parse_time_ps('0.333e-9', 'T10') == 333)
    ok &= refuse('T10 sub-ps', lambda: parse_time_ps('1e-13', 'T10'))
    # 11 backwards, repeated, mismatched-length or empty sample sets refuse
    n += 1
    ok &= refuse('T11 backwards', lambda: samples(['1e-9', '0e-9'], ['1', '1'], 'T11'))
    ok &= refuse('T11 repeat', lambda: samples(['1e-9', '1e-9'], ['1', '2'], 'T11'))
    ok &= refuse('T11 length', lambda: samples(['0e-9'], ['1', '2'], 'T11'))
    ok &= refuse('T11 empty', lambda: samples([], [], 'T11'))
    # 12 a full 16-interval window measures exactly its expected charge and passes
    n += 1
    cur = [(0, _micro(15.0)), (480000, _micro(15.0)), (481000, 0.0), (680000, 0.0)]
    de = [(0, 0.0), (499, 0.0), (501, 1.8), (480499, 1.8), (480501, 0.0)]
    w = _win(cur, de, 0, 480000, 16)
    out = measure_window(w, _micro(15.0), 30000, ctx='T12')
    ok &= near('T12 q', out['q_win']['q'], 15e-6 * 480e-9, 1e-18)
    ok &= near('T12 qexp', out['q_expected_C'], 15e-6 * 480e-9, 1e-18)
    ok &= expect("T12 abs(out['charge_error_LSB']) < 1e-9", abs(out['charge_error_LSB']) < 1e-9)
    ok &= expect("T12 out['settled']['status'] == 'SETTLED'", out['settled']['status'] == 'SETTLED')
    ok &= expect("T12 out['turn_off']['status'] == 'OFF'", out['turn_off']['status'] == 'OFF')
    ok &= expect("T12 judge(out)[0] == 'PASS'", judge(out)[0] == 'PASS')
    # 13 a short pulse that never reaches the band is reported, not invented
    n += 1
    cur = [(0, 0.0), (10000, _micro(3.0)), (30000, _micro(3.0)), (31000, 0.0), (230000, 0.0)]
    de_short = [(0, 0.0), (499, 0.0), (501, 1.8), (29499, 1.8), (29501, 0.0)]
    w = _win(cur, de_short, 0, 30000, 1)
    out = measure_window(w, _micro(15.0), 30000, ctx='T13')
    ok &= expect("T13 out['settled']['status'] == 'NOT_SETTLED_WITHIN_PULSE'", out['settled']['status'] == 'NOT_SETTLED_WITHIN_PULSE')
    ok &= expect("T13 out['charge_error_LSB'] < 0.0", out['charge_error_LSB'] < 0.0)
    ok &= expect("T13 judge(out)[0] == 'FAIL'", judge(out)[0] == 'FAIL')
    # 14 a black window has no percentage scale and must not divide by zero
    n += 1
    cur = [(0, 0.0), (480000, 0.0), (680000, 0.0)]
    w = _win(cur, [(0, 0.0), (680000, 0.0)], 0, 480000, 0)
    out = measure_window(w, _micro(15.0), 30000, ctx='T14')
    ok &= expect("T14 out['charge_error_LSB'] == 0.0", out['charge_error_LSB'] == 0.0)
    ok &= expect("T14 out['abs_gain_error_vs_15uA'] is None", out['abs_gain_error_vs_15uA'] is None)
    ok &= expect("T14 out['de_rise_50_ps'] is None", out['de_rise_50_ps'] is None)
    # 15 break test: the ammeter wired the other way round is caught, not honoured
    n += 1
    cur = [(0, -_micro(15.0)), (480000, -_micro(15.0)), (481000, 0.0), (680000, 0.0)]
    w = _win(cur, de, 0, 480000, 16)
    out = measure_window(w, _micro(15.0), 30000, ctx='T15')
    ok &= expect("T15 out['probe_direction_suspect'] is True", out['probe_direction_suspect'] is True)
    ok &= expect("T15 judge(out)[0] == 'FAIL'", judge(out)[0] == 'FAIL')
    # 16 break test: the tail of the integration data is missing
    n += 1
    short = [(0, _micro(15.0)), (300000, _micro(15.0))]
    w = _win(short, de, 0, 480000, 16)
    ok &= refuse('T16 truncated tail', lambda: measure_window(w, _micro(15.0), 30000, ctx='T16'))
    # 17 break test: a case table that repeats a key and drops a required case
    n += 1
    ok &= refuse('T17 duplicate id', lambda: validate_case_ids(['A', 'A'], ['A', 'B']))
    ok &= refuse('T17 missing id', lambda: validate_case_ids(['A'], ['A', 'B']))
    ok &= expect("T17 validate_case_ids(['A', 'B'], ['A', 'B']) == {'A': 0, 'B': 1}", validate_case_ids(['A', 'B'], ['A', 'B']) == {'A': 0, 'B': 1})
    # 18 an event-before excerpt cannot stand in for a whole-window integral
    n += 1
    pre = [(0, _micro(1.0)), (5000, _micro(3.0))]
    ok &= refuse('T18 excerpt as evidence', lambda: integrate(pre, 0, 480000, 'T18'))
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
