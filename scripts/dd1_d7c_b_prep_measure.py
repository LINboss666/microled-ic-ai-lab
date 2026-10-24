#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_measure.py -- the eight-level PAM measurement rules, on the accepted primitives.

This module deliberately does NOT re-implement integration, interpolation or band logic: it imports
`dd1_d7b_measure`, the module the accepted DATA-7B round shipped and the review kept, because two
implementations of "integrate this window" is exactly how a reported number and a recomputed number
start to disagree. What is added here is only what the PAM candidate needs on top:

  * the probe sign is fixed as `I_sink = Ip_branch` for `Ip_branch (clamp_node data_out) iprobe`; the
    raw current and the total charge are never passed through abs() to make a sign look right;
  * every window of a case is measured separately: full-enable charge, flat-part mean, off tail
    magnitude with its sample instant and interpolated threshold instant kept apart, the pure-off
    window, and the settling of the current into the code's own +/-5 % band held for at least 10 ns
    all the way to that window's own deadline;
  * two charge expectations, never mixed: `Qexpected_nominal = Inominal(code) x T50` from the geometry
    ratio, and `Qexpected_dc = IDC(code) x T50` which is NOT_RUN until a native DC point exists;
  * a ladder judgement that reports the absolute full-scale result and the eight-level ratio result
    separately, so a board that is uniformly half current cannot pass by normalisation;
  * a convergence comparison that always carries an absolute difference beside its QLSB ratio, and a
    refined run that may not silently change sign, threshold, window or reference current.

What R1 changed (review F3) is the wiring, not the mathematics. `measure_case()` used to hand the flat
window bounds to the edge finder as the edge hint with a +/-5 ns search, so all eight TR-LONG windows
answered `NO_REAL_EDGE_FOUND`; it took the first off tail for every window and `break`, so a 5 uA
fault in a later tail went unreported; and it never called `sign_check` or `charge_errors` at all.
Each emission window now searches around its own 50 % points, pairs with the tail of the same index,
reports the full-enable charge and the flat mean apart, and refuses by name where the PREP version
would have continued. `convergence()` refuses two sides that both lack the context instead of calling
`None == None` a match.

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
import dd1_d7c_b_prep_schedule as SCHEDULE    # noqa: E402  (window ids and the code identity table)

NS_TO_PS = 1000.0                              # the accepted core keeps time in picoseconds
S_PER_PS = ACCEPTED.S_PER_PS
SYNTHETIC = 'SYNTHETIC_NOT_MEASURED'
NATIVE = 'NATIVE_MEASURED'
NOT_RUN = 'NOT_RUN'
REFUSE_NO_EDGE = 'REFUSED_NO_REAL_EDGE'
REFUSE_WINDOW = 'REFUSED_WINDOW_MISSING'

Refuse = ACCEPTED.Refuse          # one refusal type for the whole chain, the accepted one


def ps(nanoseconds):
    return float(nanoseconds) * NS_TO_PS


def load_samples(time_tokens, value_tokens, ctx=''):
    """strict sample list: finite values, strictly increasing time, adaptive precision kept

    The accepted core deliberately does not snap a simulator's times to a whole-picosecond grid; it
    returns the display quantum alongside so the evidence states its own resolution bound.
    """
    return ACCEPTED.float_samples(time_tokens, value_tokens, ctx)


def enable_edges(enable_ps, level_high_V, rise_hint_ps, fall_hint_ps, ctx='enable',
                 radius_ps=None):
    """the 50 % rise and fall of DATA_EN, by adjacent samples plus interpolation, or a named refusal

    The hint is where the window says its own edge is, and the search radius is that window's ramp
    half-width: the PREP version passed flat-window bounds as the hint with a fixed +/-5 ns search,
    so a real edge 10 or 50 ns away was simply not found. A missing bracket is `NO_REAL_EDGE_FOUND`
    and the caller refuses: it never falls back to the window end, because "we could not find the
    edge" and "the edge is at the end" are different facts. `ctx` keeps its old fifth position so
    callers that already pass a label keep working.
    """
    threshold = (0.0 + float(level_high_V)) / 2.0
    try:
        window = float(radius_ps) if radius_ps is not None else 5.0 * ACCEPTED.NS
    except (TypeError, ValueError):
        raise Refuse('%s: the search radius %r is not a number of picoseconds, so no edge search is '
                     'possible' % (ctx, radius_ps))
    rise = ACCEPTED.crossing(enable_ps, threshold, True, max(0.0, rise_hint_ps - window),
                             rise_hint_ps + window, '%s rise' % ctx)
    fall = ACCEPTED.crossing(enable_ps, threshold, False, max(0.0, fall_hint_ps - window),
                             fall_hint_ps + window, '%s fall' % ctx)
    out = {'threshold_V': threshold, 'threshold_is_half_of': _fmt(level_high_V),
           'hint_rise_ps': rise_hint_ps, 'hint_fall_ps': fall_hint_ps,
           'search_radius_ps': window,
           'rise_50_ps': rise, 'fall_50_ps': fall,
           'rise_status': 'FOUND' if rise is not None else 'NO_REAL_EDGE_FOUND',
           'fall_status': 'FOUND' if fall is not None else 'NO_REAL_EDGE_FOUND'}
    if rise is None or fall is None:
        out['refusal'] = ('%s: no bracketing sample pair around the declared %s edge inside %s ps of '
                          'the hint, so the window is refused instead of being measured against the '
                          'window end' % (ctx, 'rise' if rise is None else 'fall', _fmt(window)))
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
    if not (float(stop_ps) > float(start_ps)):
        raise Refuse('%s: the window ends at %s ps, at or before its start at %s ps'
                     % (ctx, _fmt(stop_ps), _fmt(start_ps)))
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


def leakage(current_ps, tail_start_ps, tail_stop_ps, fall_hint_ps, evidence_class=SYNTHETIC,
            enable_ps=None, pure_off_start_ps=None):
    """the last 100 ns of one off tail: the magnitude, and the two instants reported apart

    `max(abs(I))` is a magnitude test on a leakage limit and nothing else: it is never applied to the
    signed tail charge, and a tail that swings positive then negative is reported with both halves
    visible, because a cancelling sum is not a shut branch. R1 adds the two conditions the review said
    the entrance had not enforced: the interval must lie inside this platform's own pure-off window,
    and DATA_EN must be at 0 V across it.
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
    out = {'status': 'WITHIN_LIMIT' if value <= rules['limit_A'] else 'ABOVE_LIMIT',
           'max_abs_A': value, 'at_sample_ps': when,
           'window_start_ps': start, 'window_stop_ps': tail_stop_ps,
           'window_length_ns': (tail_stop_ps - start) / NS_TO_PS,
           'limit_A': rules['limit_A'],
           'signed_tail_q': tail['q'], 'tail_q_pos': tail['q_pos'], 'tail_q_neg': tail['q_neg'],
           'cancellation_warning': ('the tail carries both signs; its near-zero net Q is not zero '
                                    'leakage' if tail['q_pos'] and tail['q_neg'] else ''),
           'turn_off': turn, 'evidence_class': evidence_class}
    if pure_off_start_ps is not None and start < float(pure_off_start_ps):
        out['status'] = 'REFUSED_LEAKAGE_OUTSIDE_PURE_OFF'
        out['window_valid'] = 'REFUSED_LEAKAGE_OUTSIDE_PURE_OFF'
        out['refusal'] = ('the leakage interval %s-%s ps starts before the pure-off window at %s ps, '
                          'so a falling or rising enable would be measured as leakage'
                          % (_fmt(start), _fmt(tail_stop_ps), _fmt(pure_off_start_ps)))
    else:
        out['window_valid'] = 'INSIDE_PURE_OFF'
    if enable_ps is not None:
        quiet, quiet_at = ACCEPTED.tail_segment_max_abs(enable_ps, start, tail_stop_ps)
        out['enable_max_abs_V'] = quiet
        out['enable_max_at_ps'] = quiet_at
        if quiet:
            out['status'] = 'REFUSED_ENABLE_NOT_LOW'
            out['enable_valid'] = 'REFUSED_ENABLE_NOT_LOW'
            out['refusal'] = ('DATA_EN reaches %s V inside the leakage interval at %s ps, which the '
                              'PREP windows allowed and which would score the next enable as leakage'
                              % (_fmt(quiet), _fmt(quiet_at)))
        else:
            out['enable_valid'] = 'ENABLE_LOW_THROUGHOUT'
    return out


def charge_errors(measured_q_C, nominal_A, t50_s, idc_A, tick_s, evidence_class=SYNTHETIC):
    """both expectations, in coulombs and in the declared QLSB; a missing DC point stays NOT_RUN"""
    qlsb = float(CONTRACT.UNIT_CURRENT_NOMINAL_A) * float(tick_s)
    out = {'q_C': measured_q_C, 'qlsb_C': qlsb, 't50_s': t50_s, 'tick_s': tick_s,
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
    """the same window at two maxstep values, with an absolute difference always present

    R1 (review F3) added the presence test: the PREP version compared five context fields with
    `.get()`, so two sides that both omitted every field produced `None == None`, an empty drift list
    and a WITHIN_LIMIT verdict on an input that carries no context at all. Missing or non-finite or
    non-increasing window bounds is now a named refusal, and identical context is a legitimate pass.
    """
    rules = CONTRACT.contract()['rules']['convergence']
    limit = float(rules['limit'])
    context_fields = list(rules['required_context_fields'])
    missing = [field for field in context_fields
               if coarse.get(field) in (None, '') or refined.get(field) in (None, '')]
    drift = [field for field in context_fields if field not in missing
             and coarse.get(field) != refined.get(field)]
    qlsb = float(CONTRACT.UNIT_CURRENT_NOMINAL_A) * float(tick_s)
    invalid = []
    for side, label in ((coarse, 'coarse'), (refined, 'refined')):
        start, stop = side.get('window_start_ps'), side.get('window_stop_ps')
        try:
            if start is None or stop is None or not (float(stop) > float(start)):
                invalid.append('%s window %s..%s' % (label, _fmt(start), _fmt(stop)))
        except (TypeError, ValueError):
            invalid.append('%s window bounds are not numbers' % label)
        for field in ('q', 'delta_q', 'flat_mean_A'):
            value = side.get(field)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                invalid.append('%s %s is not a number' % (label, field))
                continue
            if number != number or number in (float('inf'), float('-inf')):
                invalid.append('%s %s is not finite' % (label, field))
    if missing or invalid:
        return {'status': 'REFUSED_MISSING_CONTEXT', 'missing_context': missing,
                'invalid_input': invalid, 'context_drift': drift, 'qlsb_C': qlsb,
                'limit': limit, 'absolute_difference_always_reported': True,
                'evidence_class': evidence_class,
                'refusal': ('both sides must carry the same named context (%s) and a finite, '
                            'increasing window before any difference is meaningful; here missing=%s, '
                            'invalid=%s, so the comparison is refused instead of calling None equal '
                            'to None' % (','.join(context_fields), ','.join(missing) or 'none',
                                         ','.join(invalid) or 'none'))}
    delta = float(refined['q']) - float(coarse['q'])
    relative = abs(delta) / qlsb
    return {'delta_q_C': delta, 'delta_q_fC': delta * 1e15, 'qlsb_C': qlsb,
            'abs_delta_over_qlsb': relative, 'limit': limit,
            'status': 'REFUSED_CONTEXT_CHANGED' if drift else
                      ('WITHIN_LIMIT' if relative <= limit else 'OUTSIDE_LIMIT'),
            'context_fields_checked': context_fields, 'context_drift': drift,
            'absolute_difference_always_reported': bool(rules['status_word_alone_is_not_a_pass']),
            'evidence_class': evidence_class,
            'refusal': ('the refined run changed %s, so it is not the same window at a finer step'
                        % ','.join(drift)) if drift else ''}


def _codes_for(row, contract_data):
    code = row['pam_code']
    if code == '000..111':
        return sorted(contract_data['nominal_current_A_by_code'])
    if ',' in code:
        return code.split(',')
    return [code]


def _window(windows, case_id, kind, index):
    """the window of this case, this kind and this platform, found by its own stable id"""
    suffix = dict((k, s) for k, s, _l, _h in SCHEDULE.WINDOW_FIELDS)[kind]
    wanted = '%s#%s%d' % (case_id, suffix, index)
    found = [w for w in windows if w['window_id'] == wanted]
    return found[0] if len(found) == 1 else None


def measure_case(row, windows, samples, evidence_class=SYNTHETIC, idc_A_by_code=None):
    """one case, all of its windows, through the single entrance the native re-check will use

    `samples` maps a node to an already-loaded [(ps, value)] list. A DC row needs the operating point
    instead of a time window, so it reports the sweep points and leaves the time quantities NOT_RUN.
    R1 wired the five things the review listed: the per-window edge hints, the full-enable charge
    beside the flat mean, the real calls to `sign_check` and `charge_errors`, the k-th tail paired
    with the k-th emission window, and a named refusal wherever the PREP version would have kept a
    number it could not justify.
    """
    contract_data = CONTRACT.contract()
    out = []
    if row['class'] == 'dc_sweep':
        return [{'case_id': row['case_id'], 'window_id': '%s#SWEEP' % row['case_id'],
                 'kind': 'dc_sweep_point', 'result': NOT_RUN,
                 'idc_status': (idc_A_by_code or {}).get(row['pam_code']) and 'AVAILABLE' or NOT_RUN,
                 'note': 'needs a native DC operating point; no synthetic number stands in for it',
                 'evidence_class': evidence_class}]
    codes = _codes_for(row, contract_data)
    starts = [float(v) for v in row['platform_start_ns'].split(';')]
    stops = [float(v) for v in row['platform_stop_ns'].split(';')]
    if len(codes) != len(starts):
        raise Refuse('%s names %d codes for %d platforms' % (row['case_id'], len(codes),
                                                             len(starts)))
    radius_ps = ps(float(row['edge_ns']))
    for index in range(len(starts)):
        full = _window(windows, row['case_id'], 'emission', index)
        flat = _window(windows, row['case_id'], 'emission_flat', index)
        tail = _window(windows, row['case_id'], 'off_tail', index)
        pure = _window(windows, row['case_id'], 'pure_off', index)
        leak = _window(windows, row['case_id'], 'leak_last100', index)
        missing = [kind for kind, found in (('emission', full), ('emission_flat', flat),
                                            ('off_tail', tail), ('pure_off', pure),
                                            ('leak_last100', leak)) if found is None]
        if missing:
            raise Refuse('%s platform %d has no %s window row, so the entrance cannot measure it '
                         'and will not substitute another window'
                         % (row['case_id'], index, ','.join(missing)))
        code = codes[index]
        nominal = contract_data['nominal_current_A_by_code'][code]
        edges = enable_edges(samples['enable'], row['data_en_level_V'], ps(full['start_ns']),
                             ps(full['stop_ns']), ctx=full['window_id'], radius_ps=radius_ps)
        entry = {'case_id': row['case_id'], 'window_id': full['window_id'], 'index': index,
                 'code': code, 'nominal_A': nominal,
                 'windows': {'emission': full['window_id'], 'emission_flat':
                             flat['window_id'], 'off_tail': tail['window_id'],
                             'pure_off': pure['window_id'], 'leak_last100': leak['window_id']},
                 'declared': {'rise_50_ns': full['start_ns'], 'fall_50_ns': full['stop_ns'],
                              'flat_start_ns': flat['start_ns'], 'flat_stop_ns': flat['stop_ns']},
                 'edges': edges, 'result': NOT_RUN, 'evidence_class': evidence_class}
        if edges['rise_status'] != 'FOUND' or edges['fall_status'] != 'FOUND':
            entry['result'] = REFUSE_NO_EDGE
            entry['refusal'] = edges['refusal']
            out.append(entry)
            continue
        t50_s = (edges['fall_50_ps'] - edges['rise_50_ps']) * S_PER_PS
        full_charge = window_charge(samples['current'], edges['rise_50_ps'], edges['fall_50_ps'],
                                    full['window_id'], evidence_class)
        flat_charge = window_charge(samples['current'], ps(flat['start_ns']), ps(flat['stop_ns']),
                                    flat['window_id'], evidence_class)
        entry.update({'q_full_C': full_charge['q'], 'q_full_pos_C': full_charge['q_pos'],
                      'q_full_neg_C': full_charge['q_neg'],
                      'q_full_neg_magnitude_C': full_charge['q_neg_magnitude'],
                      'q_full_identity_holds': full_charge['identity_holds'],
                      'q_full_enable_C': full_charge['q'],
                      't50_s': t50_s,
                      'q_flat_C': flat_charge['q'], 'flat_mean_A': flat_charge['flat_mean_A'],
                      'flat_identity_holds': flat_charge['identity_holds'],
                      'zero_crossings_full': full_charge['zero_crossings'],
                      'points': full_charge['points']})
        entry['sign'] = sign_check(flat_charge, contract_data['probe']['terminals'])
        entry['settling'] = settling(samples['current'], edges['rise_50_ps'], nominal,
                                     ps(flat['stop_ns']), evidence_class)
        entry['charge_error'] = charge_errors(
            full_charge['q'], nominal, t50_s, (idc_A_by_code or {}).get(code), t50_s,
            evidence_class)
        # the two names the independent instrument probes at the top level, kept beside the nested
        # dict rather than instead of it, so a reviewer reads the same number either way
        entry['error_nominal_LSB'] = entry['charge_error']['error_nominal_LSB']
        entry['idc_status'] = entry['charge_error']['idc_status']
        entry['leakage'] = leakage(samples['current'], ps(tail['start_ns']), ps(tail['stop_ns']),
                                   edges['fall_50_ps'], evidence_class,
                                   enable_ps=samples['enable'],
                                   pure_off_start_ps=ps(pure['start_ns']))
        if entry['leakage'].get('refusal'):
            entry['result'] = entry['leakage']['status']
            entry['refusal'] = entry['leakage']['refusal']
        elif entry['sign']['status'] == 'PROBE_DIRECTION_SUSPECT':
            entry['result'] = entry['sign']['status']
            entry['refusal'] = entry['sign']['note']
        out.append(entry)
    return out


def _fmt(value):
    if value is None:
        return 'None'
    return '%g' % float(value)
