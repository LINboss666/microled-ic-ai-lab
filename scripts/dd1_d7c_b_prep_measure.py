#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_measure.py -- the eight-level PAM measurement rules, on the accepted primitives.

DATA-7C-B-PREP section 6. This module deliberately does NOT re-implement integration, interpolation or
band logic: it imports `dd1_d7b_measure`, the module the accepted DATA-7B round shipped and the review
kept, because two implementations of "integrate this window" is exactly how a reported number and a
recomputed number start to disagree. What is added here is only what the PAM candidate needs on top:

  * the probe sign is fixed as `I_sink = Ip_branch` for `Ip_branch (clamp_node data_out) iprobe`; the
    raw current and the total charge are never passed through abs() to make a sign look right;
  * every window of a case is measured separately: emission window (signed Q, Qpos, |Qneg|, flat-part
    mean), off tail (max(abs(I)) over its last 100 ns, the sample instant and the interpolated
      threshold instant kept apart), and the settling of the current into the code's own +/-5 % band
      held for at least 10 ns all the way to the declared deadline;
  * two charge expectations, never mixed: `Qexpected_nominal = Inominal(code) x T50` from the geometry
    ratio, and `Qexpected_dc = IDC(code) x T50` which is NOT_RUN until a native DC point exists;
  * a ladder judgement that reports the absolute full-scale result and the eight-level ratio result
    separately, so a board that is uniformly half current cannot pass by normalisation;
  * a convergence comparison that always carries an absolute difference beside its QLSB ratio, and a
    refined run that may not silently change sign, threshold, window or reference current.

Everything here is offline arithmetic. Nothing is a measurement: the caller decides whether its samples
came from a native run or from a hand-written synthetic file, and `evidence_class` travels with it.
"""

from __future__ import absolute_import, division, print_function

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import dd1_d7b_measure as ACCEPTED            # noqa: E402  (the accepted measurement core)
import dd1_d7c_b_prep_contract as CONTRACT    # noqa: E402

NS_TO_PS = 1000.0                              # the accepted core keeps time in picoseconds
S_PER_PS = ACCEPTED.S_PER_PS
SYNTHETIC = 'SYNTHETIC_NOT_MEASURED'
NATIVE = 'NATIVE_MEASURED'
NOT_RUN = 'NOT_RUN'


Refuse = ACCEPTED.Refuse          # one refusal type for the whole chain, the accepted one


def ps(nanoseconds):
    return float(nanoseconds) * NS_TO_PS


def load_samples(time_tokens, value_tokens, ctx=''):
    """strict sample list: finite values, strictly increasing time, adaptive precision kept

    The accepted core deliberately does not snap a simulator's times to a whole-picosecond grid; it
    returns the display quantum alongside so the evidence states its own resolution bound.
    """
    return ACCEPTED.float_samples(time_tokens, value_tokens, ctx)


def enable_edges(enable_ps, level_high_V, rise_hint_ps, fall_hint_ps, ctx='enable'):
    """the 50 % rise and fall of DATA_EN, by adjacent samples plus interpolation, or a named refusal

    The hint is where the deck says the edge is; the search window is around it. A missing bracket is
    NO_REAL_EDGE_FOUND and it never falls back to the window end, because "we could not find the edge"
    and "the edge is at the end" are different facts.
    """
    threshold = (0.0 + float(level_high_V)) / 2.0
    span = 5.0 * NS_TO_PS
    rise = ACCEPTED.crossing(enable_ps, threshold, True, max(0.0, rise_hint_ps - span),
                             rise_hint_ps + span, '%s rise' % ctx)
    fall = ACCEPTED.crossing(enable_ps, threshold, False, max(0.0, fall_hint_ps - span),
                             fall_hint_ps + span, '%s fall' % ctx)
    out = {'threshold_V': threshold, 'threshold_is_half_of': _fmt(level_high_V),
           'rise_50_ps': rise, 'fall_50_ps': fall,
           'rise_status': 'FOUND' if rise is not None else 'NO_REAL_EDGE_FOUND',
           'fall_status': 'FOUND' if fall is not None else 'NO_REAL_EDGE_FOUND'}
    if rise is None or fall is None:
        out['refusal'] = ('%s: no bracketing sample pair around the declared %s edge, so the window '
                          'is refused instead of being measured against the window end'
                          % (ctx, 'rise' if rise is None else 'fall'))
    return out


def sign_check(charge, orientation=None):
    """the sign verdict on one emission window, decided on the signed number and never on abs()

    `Ip_branch (clamp_node data_out) iprobe` with `I_sink = Ip_branch` means a sinking branch reads
    positive. If the emission window's mean current comes out negative, either the branch is being fed
    the wrong way or the ammeter was turned around while the plan still called the reading the sink
    current. Taking the absolute value here would hide exactly that, so the rule refuses instead.
    """
    if orientation is not None and tuple(orientation) != tuple(CONTRACT.R2PLAN.PROBE_TERMINALS):
        return {'status': 'PROBE_TERMINALS_NOT_THE_CONTRACTED_ORDER',
                'terminals': list(orientation),
                'expected': list(CONTRACT.R2PLAN.PROBE_TERMINALS)}
    mean = charge.get('flat_mean_A')
    if mean is None:
        return {'status': 'NO_WINDOW'}
    if mean > 0.0:
        return {'status': 'SINK_POSITIVE_AS_DECLARED', 'mean_A': mean}
    if mean < 0.0:
        return {'status': 'PROBE_DIRECTION_SUSPECT', 'mean_A': mean,
                'note': 'a sinking branch cannot have a negative mean over its own emission window; '
                        'abs() would hide this, so the run is refused rather than folded'}
    return {'status': 'ZERO_CURRENT_WINDOW', 'mean_A': mean,
            'note': 'zero over a window that should conduct is a missing branch, not a sign problem'}


def window_charge(current_ps, start_ps, stop_ps, ctx='window', evidence_class=SYNTHETIC):
    """signed Q with the positive and negative halves separate, over the interpolated window bounds"""
    result = ACCEPTED.integrate(current_ps, start_ps, stop_ps, ctx)
    length_s = (float(stop_ps) - float(start_ps)) * S_PER_PS
    result.update({'ctx': ctx, 'start_ps': start_ps, 'stop_ps': stop_ps, 'length_s': length_s,
                   'q_neg_magnitude': -result['q_neg'],
                   'flat_mean_A': result['q'] / length_s if length_s else None,
                   'identity': 'Q = Qpos + Qneg (Qneg signed)',
                   'identity_holds': abs(result['q'] - (result['q_pos'] + result['q_neg']))
                   <= max(1e-30, abs(result['q']) * 1e-9),
                   'evidence_class': evidence_class})
    return result


def settling(current_ps, edge_ps, target_A, deadline_ps, evidence_class=SYNTHETIC):
    """into the code's own +/-5 % band and held there until this window's own deadline"""
    rules = CONTRACT.contract()['rules']['settling']
    band = float(rules['band_fraction'])
    hold_ps = float(rules['hold_ns']) * NS_TO_PS
    result = ACCEPTED.sustained_in_band(current_ps, edge_ps, target_A * (1.0 - band),
                                       target_A * (1.0 + band), deadline_ps)
    result.update({'target_A': target_A, 'band_fraction': band, 'required_hold_ps': hold_ps,
                   'held_ps_reported': result['held_ps'],
                   'status': ('SETTLED_HELD' if result['status'] == 'SETTLED' and
                              (result['held_ps'] or 0) >= hold_ps else
                              ('LEFT_BAND_BEFORE_DEADLINE' if result['band_left_at_ps'] is not None
                               else result['status'])),
                   'statuses_allowed': list(rules['statuses']),
                   'evidence_class': evidence_class})
    if result['status'] not in rules['statuses']:
        raise Refuse('settling produced %r, outside the contracted statuses %s'
                     % (result['status'], ','.join(rules['statuses'])))
    return result


def leakage(current_ps, tail_start_ps, tail_stop_ps, fall_hint_ps, evidence_class=SYNTHETIC):
    """the last 100 ns of one off tail: the magnitude, and the two instants reported apart

    `max(abs(I))` is a magnitude test on a leakage limit and nothing else: it is never applied to the
    signed tail charge, and a tail that swings positive then negative is reported with both halves
    visible, because a cancelling sum is not a shut branch.
    """
    rules = CONTRACT.contract()['rules']['shutoff_leakage']
    last = float(rules['tail_last_ns']) * NS_TO_PS
    start = max(tail_start_ps, tail_stop_ps - last)
    value, when = ACCEPTED.tail_segment_max_abs(current_ps, start, tail_stop_ps)
    if value is None:
        return {'status': 'NO_DATA_IN_TAIL', 'window_start_ps': start, 'window_stop_ps': tail_stop_ps,
                'evidence_class': evidence_class}
    tail = window_charge(current_ps, tail_start_ps, tail_stop_ps, 'tail', evidence_class)
    turn = (ACCEPTED.turn_off(current_ps, fall_hint_ps, rules['limit_A'], tail_stop_ps)
            if fall_hint_ps is not None else {'status': 'NO_REAL_EDGE_FOUND'})
    return {'status': 'WITHIN_LIMIT' if value <= rules['limit_A'] else 'ABOVE_LIMIT',
            'max_abs_A': value, 'at_sample_ps': when,
            'window_start_ps': start, 'window_stop_ps': tail_stop_ps,
            'window_length_ns': (tail_stop_ps - start) / NS_TO_PS,
            'limit_A': rules['limit_A'],
            'signed_tail_q': tail['q'], 'tail_q_pos': tail['q_pos'], 'tail_q_neg': tail['q_neg'],
            'cancellation_warning': ('the tail carries both signs; its near-zero net Q is not zero '
                                     'leakage' if tail['q_pos'] and tail['q_neg'] else ''),
            'turn_off': turn, 'evidence_class': evidence_class}


def charge_errors(measured_q_C, nominal_A, t50_s, idc_A, tick_s, evidence_class=SYNTHETIC):
    """both expectations, in coulombs and in the declared QLSB; a missing DC point stays NOT_RUN"""
    qlsb = float(CONTRACT.UNIT_CURRENT_NOMINAL_A) * float(tick_s)
    out = {'q_C': measured_q_C, 'qlsb_C': qlsb, 't50_s': t50_s,
           'qexpected_nominal_C': float(nominal_A) * float(t50_s),
           'evidence_class': evidence_class}
    out['error_nominal_C'] = measured_q_C - out['qexpected_nominal_C']
    out['error_nominal_LSB'] = out['error_nominal_C'] / qlsb
    if idc_A is None:
        out['idc_status'] = NOT_RUN
        out['qexpected_dc_C'] = NOT_RUN
        out['error_dc_C'] = NOT_RUN
        out['error_dc_LSB'] = NOT_RUN
        out['idc_note'] = ('no native DC operating point exists for this code yet; a geometry-ratio '
                           'estimate is never substituted for IDC(k)')
    else:
        out['idc_status'] = 'AVAILABLE'
        out['qexpected_dc_C'] = float(idc_A) * float(t50_s)
        out['error_dc_C'] = measured_q_C - out['qexpected_dc_C']
        out['error_dc_LSB'] = out['error_dc_C'] / qlsb
    limit = CONTRACT.contract()['rules']['charge_error']['proposed_limit_in_LSB']
    out['limit_LSB_proposed'] = limit
    out['verdict_nominal'] = 'WITHIN_PROPOSED_LIMIT' if abs(out['error_nominal_LSB']) <= limit \
        else 'OUTSIDE_PROPOSED_LIMIT'
    out['limit_status'] = 'PROPOSED_NOT_CLAIMED'
    return out


def ladder(measurements, evidence_class=SYNTHETIC):
    """absolute full scale and the eight-level ratio, reported apart so neither can excuse the other

    `measurements` maps the eight codes to a measured current in amperes at the declared clamp. The
    ratio reference is I111/8 of the *measured* full scale, which is what makes a uniformly scaled
    array fail the absolute test while still looking perfectly linear.
    """
    data = CONTRACT.contract()
    rules = data['rules']['eight_level_ratio']
    full = data['rules']['full_scale_absolute']
    codes = sorted(data['nominal_current_A_by_code'])
    missing = [c for c in codes if c not in measurements]
    if missing:
        raise Refuse('the ladder needs all eight codes, missing %s' % ','.join(missing))
    i111 = float(measurements['111'])
    unit_ref = i111 / float(data['device_geometry'].get('branches', CONTRACT.BRANCHES))
    deviations = {}
    for index, code in enumerate(codes):
        deviations[code] = float(measurements[code]) - (index + 1) * unit_ref
    ordered = [float(measurements[code]) for code in codes]
    monotonic = all(ordered[i] < ordered[i + 1] for i in range(len(ordered) - 1))
    limit_units = float(rules['abs_deviation_limit_in_units_of_iunit_ref'])
    worst = max(deviations, key=lambda code: abs(deviations[code]))
    absolute_ok = (i111 >= full['lower_A']) and (i111 <= full['upper_A'])
    ratio_ok = monotonic and all(abs(deviations[code]) <= limit_units * unit_ref for code in codes)
    return {'i111_A': i111, 'iunit_ref_A': unit_ref, 'deviations_A': deviations,
            'worst_code': worst, 'worst_deviation_in_units': abs(deviations[worst]) / unit_ref,
            'monotonic': monotonic, 'absolute_pass': absolute_ok, 'ratio_pass': ratio_ok,
            'overall': 'PASS' if (absolute_ok and ratio_ok) else 'FAIL',
            'why_both_are_reported': ('a scaled-down array can pass the ratio test and still fail the '
                                       '15 uA absolute target; the eight-level ratio never substitutes '
                                       'for the absolute current'),
            'absolute_band_A': [full['lower_A'], full['upper_A']],
            'identity_of_nominal': data['nominal_current_identity'],
            'evidence_class': evidence_class}


def convergence(coarse, refined, tick_s, evidence_class=SYNTHETIC):
    """the same window at two maxstep values, with an absolute difference always present"""
    rules = CONTRACT.contract()['rules']['convergence']
    limit = float(rules['limit'])
    qlsb = float(CONTRACT.UNIT_CURRENT_NOMINAL_A) * float(tick_s)
    context_fields = ('sign_rule', 'threshold_V', 'window_start_ps', 'window_stop_ps',
                      'reference_current_A')
    drift = [field for field in context_fields
             if coarse.get(field) != refined.get(field)]
    delta = float(refined['q']) - float(coarse['q'])
    relative = abs(delta) / qlsb
    out = {'delta_q_C': delta, 'delta_q_fC': delta * 1e15, 'qlsb_C': qlsb,
           'abs_delta_over_qlsb': relative, 'limit': limit,
           'status': 'REFUSED_CONTEXT_CHANGED' if drift else
                     ('WITHIN_LIMIT' if relative <= limit else 'OUTSIDE_LIMIT'),
           'context_drift': drift,
           'absolute_difference_always_reported': bool(rules['status_word_alone_is_not_a_pass']),
           'evidence_class': evidence_class}
    if drift:
        out['refusal'] = ('the refined run changed %s, so it is not the same window at a finer step'
                          % ','.join(drift))
    return out


def _fmt(value):
    return '%g' % float(value)


def measure_case(row, windows, samples, evidence_class=SYNTHETIC):
    """one case, all of its windows, through the single entrance the native re-check will use

    `samples` maps a node to an already-loaded [(ps, value)] list. A DC row needs the operating point
    instead of a time window, so it reports the sweep points and leaves the time quantities NOT_RUN.
    """
    contract_data = CONTRACT.contract()
    out = []
    if row['class'] == 'dc_sweep':
        return [{'case_id': row['case_id'], 'window_id': '%s#SWEEP' % row['case_id'],
                 'kind': 'dc_sweep_point', 'result': NOT_RUN,
                 'note': 'needs a native DC operating point; no synthetic number stands in for it',
                 'evidence_class': evidence_class}]
    codes = row['pam_code'].split(',') if row['class'] != 'transient' or \
        ',' in row['pam_code'] else [row['pam_code']]
    if row['pam_code'] == '000..111':
        codes = sorted(contract_data['nominal_current_A_by_code'])
    for index, window in enumerate([w for w in windows if w['case_id'] == row['case_id'] and
                                    w['kind'] == 'emission']):
        code = codes[min(index, len(codes) - 1)]
        nominal = contract_data['nominal_current_A_by_code'][code]
        start, stop = ps(window['start_ns']), ps(window['stop_ns'])
        charge = window_charge(samples['current'], start, stop, window['window_id'], evidence_class)
        edges = enable_edges(samples['enable'], row['data_en_level_V'], start, stop,
                             window['window_id'])
        entry = {'case_id': row['case_id'], 'window_id': window['window_id'], 'kind': 'emission',
                 'code': code, 'nominal_A': nominal, 'q_C': charge['q'], 'q_pos_C': charge['q_pos'],
                 'q_neg_C': charge['q_neg'], 'flat_mean_A': charge['flat_mean_A'],
                 'zero_crossings': charge['zero_crossings'], 'points': charge['points'],
                 'edges': edges, 'settling': None, 'result': NOT_RUN,
                 'evidence_class': evidence_class}
        if edges['rise_status'] == 'FOUND':
            entry['settling'] = settling(samples['current'], edges['rise_50_ps'], nominal,
                                         ps(window['stop_ns']), evidence_class)
        for tail in [w for w in windows if w['case_id'] == row['case_id'] and w['kind'] == 'off_tail']:
            entry['leakage'] = leakage(samples['current'], ps(tail['start_ns']), ps(tail['stop_ns']),
                                       edges['fall_50_ps'], evidence_class)
            break
        out.append(entry)
    return out
