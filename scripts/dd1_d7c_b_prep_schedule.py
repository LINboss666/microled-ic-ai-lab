#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_schedule.py -- absolute, reviewable timing for the fifteen decks.

The delivered R2 plan (scripts/dd1_d7c_a_r2_plan.py) supplies the *relative* times; this module turns
them into absolute nanoseconds and is the only place those numbers are written down.

R1 rebuilt the timing model because the independent review of the PREP bytes (tip dcef9b3) read the
delivered decks and found three things the PREP columns could not express:

  * a code string written left-to-right into pam0/pam1/pam2 is the reverse of the delivered decoder's
    bit weights, and the bit itself was used as the level, so four DC decks carried another code's
    identity and twelve high pins sat at 1.0 V inside a 1.8 V domain (F1);
  * one PWL point per code change is a straight line between two far-apart targets, and that line
    crosses the emission windows: 36 such ramps in the delivered transients (F2);
  * the first enable ramp held an extra ``(lead, 0)`` point, so its interpolated 50 % was 1025 ns
    (TR-LONG) or 1010 ns (TR-OFFCODE) while the table declared 1000 ns (F2).

The model now used, and checked against the waveform rows themselves rather than against the columns
that produced them:

    pure-off preparation ends   units.lead_off_ns           = 1000 ns
    half-edge (Emax)            units.edge_ns               =   50 ns
    uniform transient offset    units.transient_offset_ns   = 1050 ns = lead + edge
    code-change edge            units.code_edge_ns          =    2 ns total, inside a pure-off window

Five separately named windows per platform: emission (rise50 -> fall50), emission_flat
(rise_end -> fall_start), off_tail (fall50 -> the next ramp start, or the declared stop),
pure_off (the fall endpoint -> the next ramp start) and leak_last100 (the last 100 ns of the tail,
which must lie wholly inside the pure-off window or the configuration is refused).

The row also carries `off_window_ns`, the pure-off interval in the pair spelling the independent review
instrument selects on, so the reviewer's own unchanged tool can read the repaired bytes. It is a copy of
pure_off_start_ns/pure_off_stop_ns and nothing else: `validate` refuses the day the two spellings
disagree, and so does `dd1_d7c_b_prep_r1_deck_read`.

Offline only: this writes text and arithmetic, never starts a simulator, and every electrical result
stays NOT_RUN.
"""

from __future__ import absolute_import, division, print_function

import argparse
import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import dd1_d7c_a_offline_check as CHECK        # noqa: E402  (rows_write)
import dd1_d7c_a_r2_plan as R2PLAN             # noqa: E402  (the delivered relative schedule)
import dd1_d7c_b_prep_contract as CONTRACT     # noqa: E402

SCHEDULE_TABLE = 'tests/dd1_d7c_b_prep/schedule.csv'
WINDOWS_TABLE = 'tests/dd1_d7c_b_prep/windows.csv'
PWL_TABLE = 'tests/dd1_d7c_b_prep/pwl.csv'

# 38 columns. Each of the five window kinds owns its own pair of instants: one word that means the
# platform, the flat part and the integration interval at once is the ambiguity this round removes.
SCHEDULE_HEADER = ['case_id', 'class', 'pam_code', 'data_en_form', 'data_en_level_V', 'logic_high_V',
                   'lead_off_ns', 'edge_ns', 'offset_applied_ns', 'platform_start_ns',
                   'platform_stop_ns', 'enable_rise_50_ns', 'enable_fall_50_ns', 'rise_low_ns',
                   'rise_high_ns', 'fall_high_ns', 'fall_low_ns', 'full_window_start_ns',
                   'full_window_stop_ns', 'flat_start_ns', 'flat_stop_ns', 'tail_start_ns',
                   'tail_stop_ns', 'pure_off_start_ns', 'pure_off_stop_ns', 'off_window_ns',
                   'leak_window_ns',
                   'code_change_ns', 'code_change_rule', 'settled_before_enable_ns', 'stop_ns',
                   'maxstep_ns', 'paired_case', 'clamp_sweep_V', 'analysis_name', 'analysis_line',
                   'launch_processes_dut', 'launch_processes_preflight', 'result']
WINDOWS_HEADER = ['case_id', 'window_id', 'kind', 'start_ns', 'stop_ns', 'length_ns', 'quantity',
                  'measure_together_with', 'state_at_start', 'result']
PWL_HEADER = ['case_id', 'signal', 'node', 't_ns', 'value_V', 'role', 'result']

DC_NO_TIME = 'dc_no_time_window'
LEAK_WINDOW_NS = 100.0
ENABLE_LOW_V = 0.0
# every time column prints three decimals of a nanosecond, so the display resolves at 0.1 ps and a
# tolerance claiming finer than that would be a quantisation artefact
TIME_DISPLAY_DECIMALS = 3
TIME_DISPLAY_LSB_NS = 10 ** -TIME_DISPLAY_DECIMALS
KINDS = ('emission', 'emission_flat', 'off_tail', 'pure_off', 'leak_last100')
# (kind, window-id suffix, the schedule column(s) declaring it)
WINDOW_FIELDS = (('emission', 'W', 'full_window_start_ns', 'full_window_stop_ns'),
                 ('emission_flat', 'F', 'flat_start_ns', 'flat_stop_ns'),
                 ('off_tail', 'T', 'tail_start_ns', 'tail_stop_ns'),
                 ('pure_off', 'O', 'pure_off_start_ns', 'pure_off_stop_ns'),
                 ('leak_last100', 'L', 'leak_window_ns', 'leak_window_ns'))
STATIC = 'static_from_t0'


def _ns(value_ton):
    return float(value_ton) * R2PLAN.TON_NS


def _g(value):
    return '%.*f' % (TIME_DISPLAY_DECIMALS, round(float(value), TIME_DISPLAY_DECIMALS))


def _n(text):
    return '%sn' % text


def _units():
    return CONTRACT.contract()['units']


def code_bits(code, logic_high_V=None):
    """pam0 is bit 0 (weight 1), pam1 is bit 1 (weight 2), pam2 is bit 2 (weight 4)

    A logical bit is multiplied by the declared rail and never used as a volt.
    """
    if logic_high_V is None:
        logic_high_V = _units()['logic_high_V']
    value = int(code, 2)
    return {'pam0': float((value >> 0) & 1) * float(logic_high_V),
            'pam1': float((value >> 1) & 1) * float(logic_high_V),
            'pam2': float((value >> 2) & 1) * float(logic_high_V)}


def cross_at(pairs, level, near_ns=None, within_ns=None):
    """the interpolated crossing of a piecewise line with `level`, nearest to `near_ns`

    This is the reviewer's own method: the number is read off the waveform that was written, not off
    the column that claims it. With `near_ns` and no crossing inside `within_ns` it answers None, and
    the caller refuses instead of borrowing a neighbouring edge.
    """
    found = []
    for index in range(1, len(pairs)):
        (t0, v0), (t1, v1) = pairs[index - 1], pairs[index]
        if v1 == v0 or not (min(v0, v1) <= level <= max(v0, v1)):
            continue
        found.append(t0 + (t1 - t0) * (level - v0) / float(v1 - v0))
    if not found:
        return None
    if near_ns is None:
        return found[0]
    best = min(found, key=lambda t: abs(t - near_ns))
    if within_ns is not None and abs(best - near_ns) > within_ns:
        return None
    return best


def _platform(rise50_ns, platform_ns, edge_ns, code, code_change_ns=None):
    """one emission platform, every instant measured from its own two 50 % points"""
    fall50_ns = rise50_ns + platform_ns
    edge = _units()['code_edge_ns']
    return {
        'pam_code': code,
        'platform_start_ns': _g(rise50_ns), 'platform_stop_ns': _g(fall50_ns),
        'enable_rise_50_ns': _g(rise50_ns), 'enable_fall_50_ns': _g(fall50_ns),
        'rise_low_ns': _g(rise50_ns - edge_ns), 'rise_high_ns': _g(rise50_ns + edge_ns),
        'fall_high_ns': _g(fall50_ns - edge_ns), 'fall_low_ns': _g(fall50_ns + edge_ns),
        'full_window_start_ns': _g(rise50_ns), 'full_window_stop_ns': _g(fall50_ns),
        'flat_start_ns': _g(rise50_ns + edge_ns), 'flat_stop_ns': _g(fall50_ns - edge_ns),
        'edge_ns': _g(edge_ns),
        # tail and pure-off belong to the pair of platforms, so _close_platforms fills them in
        'tail_start_ns': _g(fall50_ns), 'tail_stop_ns': None,
        'pure_off_start_ns': _g(fall50_ns + edge_ns), 'pure_off_stop_ns': None,
        'leak_window_ns': None,
        'code_change_ns': _g(code_change_ns) if code_change_ns is not None else STATIC,
        # a code that never changes has been constant since t=0, so it is settled for the whole time
        # from t=0 up to this platform's ramp start
        'settled_before_enable_ns': (_g((rise50_ns - edge_ns) - (code_change_ns + edge / 2.0))
                                     if code_change_ns is not None else _g(rise50_ns - edge_ns))}


def _close_platforms(segments, stop_ns, tail_ns):
    """give every platform its own tail, pure-off and leakage interval; the last one ends at stop"""
    for index, segment in enumerate(segments):
        next_low = (float(segments[index + 1]['rise_low_ns']) if index + 1 < len(segments)
                    else stop_ns)
        tail_stop = min(float(segment['enable_fall_50_ns']) + tail_ns, next_low) \
            if index + 1 < len(segments) else stop_ns
        # a tail that reaches into the next ramp start is what lets the next enable hide inside it
        tail_stop = min(tail_stop, next_low)
        segment['tail_stop_ns'] = _g(tail_stop)
        segment['pure_off_stop_ns'] = _g(next_low)
        segment['leak_window_ns'] = '%s-%s' % (_g(tail_stop - LEAK_WINDOW_NS), _g(tail_stop))
    return segments


def _multi(row, segments, field):
    row[field] = ';'.join(segment[field] for segment in segments)


def _dc_rows(contract_data):
    units = contract_data['units']
    sweep = ','.join(_g(v) for v in contract_data['clamp_sweep_points_V'])
    clamp = contract_data['rules']['clamp']
    analysis = 'dc_case dc dev=Vclamp param=dc start=%s stop=%s step=%s' % (
        _g(clamp['sweep_start_V']), _g(clamp['sweep_stop_V']), _g(clamp['sweep_step_V']))
    rows, windows, pwl = [], [], []
    for code in R2PLAN.DC_CODES:
        nominal = contract_data['nominal_current_A_by_code'][code]
        row = dict((field, DC_NO_TIME) for field in SCHEDULE_HEADER)
        row.update({'case_id': 'DC-%s' % code, 'class': 'dc_sweep', 'pam_code': code,
                    'data_en_form': 'static_dc', 'data_en_level_V': _g(units['logic_high_V']),
                    'logic_high_V': _g(units['logic_high_V']),
                    'lead_off_ns': _g(0), 'edge_ns': _g(0), 'offset_applied_ns': _g(0),
                    'code_change_ns': STATIC,
                    'code_change_rule': 'the three PAM bits are static levels for the whole sweep, so '
                                        'this case has no code change to place',
                    'maxstep_ns': 'not_applicable_dc_analysis', 'paired_case': '',
                    'clamp_sweep_V': sweep, 'analysis_name': 'dc_case', 'analysis_line': analysis,
                    'launch_processes_dut': '1', 'launch_processes_preflight': '1',
                    'result': 'NOT_RUN'})
        rows.append(row)
        windows.append({'case_id': row['case_id'], 'window_id': '%s#SWEEP' % row['case_id'],
                        'kind': 'dc_sweep_point', 'start_ns': DC_NO_TIME, 'stop_ns': DC_NO_TIME,
                        'length_ns': DC_NO_TIME,
                        'quantity': 'I_sink at each of the %d clamp points, nominal %s uA over %d '
                                    'conducting branch(es)'
                                    % (len(contract_data['clamp_sweep_points_V']),
                                       _g(nominal * 1e6), int(code, 2) + 1),
                        'measure_together_with': 'data_out, iref_in, vcas, vdd18, vss, en0..en7, '
                                                 'enb0..en7, the eight local bias nodes',
                        'state_at_start': 'static enable %s V, the branches in the state code %s '
                                          'declares' % (_g(units['logic_high_V']), code),
                        'result': 'NOT_RUN'})
        pwl.append({'case_id': row['case_id'], 'signal': 'DATA_EN', 'node': 'data_en',
                    't_ns': _g(0), 'value_V': _g(units['logic_high_V']), 'role': 'static_dc_level',
                    'result': 'NOT_RUN'})
        for bit, value in sorted(code_bits(code, units['logic_high_V']).items()):
            pwl.append({'case_id': row['case_id'], 'signal': 'PAM bit', 'node': bit, 't_ns': _g(0),
                        'value_V': _g(value), 'role': 'static_dc_level', 'result': 'NOT_RUN'})
    return rows, windows, pwl


def _enable_pwl(case_id, segments, high, prep_end_ns, stop_ns=None):
    """the enable as adjacent time/value pairs, with no point inside a ramp

    The leading flat runs from t=0 to the first ramp start; each ramp is exactly the two points
    around its own 50 %, so the interpolated crossing is the number in the table.
    """
    points = [(_g(0), _g(ENABLE_LOW_V), 'initial_off_start')]
    for segment in segments:
        points.extend([(segment['rise_low_ns'], _g(ENABLE_LOW_V), 'rise_start'),
                       (segment['rise_high_ns'], _g(high), 'rise_end'),
                       (segment['fall_high_ns'], _g(high), 'fall_start'),
                       (segment['fall_low_ns'], _g(ENABLE_LOW_V), 'fall_end')])
    by_time = {}
    for time, value, role in points:
        if time in by_time and by_time[time][0] != value:
            raise SystemExit('D7C_B_SCHEDULE_REFUSED %s writes two DATA_EN values at %s ns'
                             % (case_id, time))
        by_time.setdefault(time, (value, role))
    if _g(prep_end_ns) not in by_time and min(float(t) for t in by_time) < prep_end_ns:
        # the preparation is a fact about the waveform, so it becomes a point -- but only at an
        # instant that is not already a ramp endpoint, never inside a ramp
        by_time[_g(prep_end_ns)] = (_g(ENABLE_LOW_V), 'pure_off_preparation_end')
    ramps = []
    for segment in segments:
        ramps.extend([(float(segment['rise_low_ns']), float(segment['rise_high_ns'])),
                      (float(segment['fall_high_ns']), float(segment['fall_low_ns']))])
    if stop_ns is not None:
        # the envelope of the wave has to reach the analysis stop, so a reader can see from the deck
        # alone that the enable stays low until the case ends
        if any(low < float(stop_ns) < high for low, high in ramps):
            raise SystemExit('D7C_B_SCHEDULE_REFUSED %s would put the stop point %s ns inside a ramp'
                             % (case_id, _g(stop_ns)))
        by_time.setdefault(_g(stop_ns), (_g(ENABLE_LOW_V), 'analysis_stop_hold'))
    return [{'case_id': case_id, 'signal': 'DATA_EN', 'node': 'data_en', 't_ns': time,
             'value_V': by_time[time][0], 'role': by_time[time][1], 'result': 'NOT_RUN'}
            for time in sorted(by_time, key=float)]


def _code_pwl(case_id, segments, initial_code, high):
    """each PAM bit holds its old value, then changes with a finite edge inside a pure-off window"""
    edge = _units()['code_edge_ns']
    rows = []
    for bit in ('pam0', 'pam1', 'pam2'):
        series = [(_g(0), _g(code_bits(initial_code, high)[bit]), 'initial_code_at_t0')]
        for segment in segments:
            if segment['code_change_ns'] == STATIC:
                continue
            centre = float(segment['code_change_ns'])
            # hold the old value up to the edge, then the new value after it: between two changes the
            # line is flat, because its endpoints carry the same number
            series.append((_g(centre - edge / 2.0), series[-1][1], 'hold_until_code_edge'))
            series.append((_g(centre + edge / 2.0), _g(code_bits(segment['pam_code'], high)[bit]),
                           'code_edge_settled'))
        times = [float(item[0]) for item in series]
        if len(set(times)) != len(times):
            raise SystemExit('D7C_B_SCHEDULE_REFUSED %s.%s repeats an instant, which is two values at '
                             'one time' % (case_id, bit))
        for index, (time, value, role) in enumerate(series):
            rows.append({'case_id': case_id, 'signal': 'PAM bit', 'node': bit, 't_ns': time,
                         'value_V': value, 'role': '%s_%d_of_%d' % (role, index + 1, len(series)),
                         'result': 'NOT_RUN'})
    return rows


def _transient_row(case_id, code, form, segments, stop_ns, change_rule, clamp_text, contract_data):
    units = contract_data['units']
    # the half-edge belongs to the case, not to the contract: R2 planned 50 / 10 / 20 ns for the
    # three families, and the contract's edge_ns is only the maximum any of them may use
    edges = sorted(set(segment['edge_ns'] for segment in segments))
    if len(edges) != 1:
        raise SystemExit('D7C_B_SCHEDULE_REFUSED %s mixes half-edges %s in one case'
                         % (case_id, ','.join(edges)))
    if float(edges[0]) > units['edge_ns']:
        raise SystemExit('D7C_B_SCHEDULE_REFUSED %s uses a %s ns half-edge above the declared maximum '
                         '%s ns' % (case_id, edges[0], _g(units['edge_ns'])))
    row = {'case_id': case_id, 'class': 'transient', 'pam_code': code, 'data_en_form': form,
           'data_en_level_V': _g(units['logic_high_V']), 'logic_high_V': _g(units['logic_high_V']),
           'lead_off_ns': _g(units['lead_off_ns']), 'edge_ns': edges[0],
           'offset_applied_ns': _g(units['transient_offset_ns']), 'code_change_rule': change_rule,
           'stop_ns': _g(stop_ns), 'maxstep_ns': _g(R2PLAN.MAXSTEP_WIDE_NS), 'paired_case': '',
           'clamp_sweep_V': clamp_text, 'analysis_name': 'tran_case',
           'analysis_line': 'tran_case tran stop=%s maxstep=%s'
                            % (_n(_g(stop_ns)), _n(_g(R2PLAN.MAXSTEP_WIDE_NS))),
           'launch_processes_dut': '1', 'launch_processes_preflight': '1', 'result': 'NOT_RUN'}
    for field in ('platform_start_ns', 'platform_stop_ns', 'enable_rise_50_ns', 'enable_fall_50_ns',
                  'rise_low_ns', 'rise_high_ns', 'fall_high_ns', 'fall_low_ns',
                  'full_window_start_ns', 'full_window_stop_ns', 'flat_start_ns', 'flat_stop_ns',
                  'tail_start_ns', 'tail_stop_ns', 'pure_off_start_ns', 'pure_off_stop_ns',
                  'leak_window_ns', 'code_change_ns', 'settled_before_enable_ns'):
        _multi(row, segments, field)
    # the pure-off interval again in the single-cell pair spelling, because the independent review
    # instrument reads `off_window_ns`; the schedule checks and dd1_d7c_b_prep_r1_deck_read both
    # refuse the day the two spellings disagree, so the column cannot drift away from its source
    row['off_window_ns'] = ';'.join('%s-%s' % (segment['pure_off_start_ns'],
                                                segment['pure_off_stop_ns']) for segment in segments)
    return row


def _window_rows(case_id, index, segment, contract_data, code):
    """five named windows per platform, each carrying the platform it belongs to inside its own id"""
    nominal = _g(contract_data['nominal_current_A_by_code'][code] * 1e6)
    rules = contract_data['rules']
    leak_lo, leak_hi = segment['leak_window_ns'].split('-')

    def build(kind, suffix, start, stop, quantity, together, state):
        return {'case_id': case_id, 'window_id': '%s#%s%d' % (case_id, suffix, index),
                'kind': kind, 'start_ns': start, 'stop_ns': stop,
                'length_ns': _g(float(stop) - float(start)), 'quantity': quantity,
                'measure_together_with': together, 'state_at_start': state, 'result': 'NOT_RUN'}
    return [
        build('emission', 'W', segment['full_window_start_ns'],
              segment['full_window_stop_ns'],
              'signed Q, Qpos, |Qneg| and the settling of code %s across the whole enable window '
              '(rise50 to fall50, nominal %s uA); this is the charge convergence compares'
              % (code, nominal),
              'Ip_branch, data_out, this window own 50%% edges, the local bias nodes of the '
              'conducting branches',
              'enable crosses 50%% at %s ns; the code settled %s ns before the ramp started'
              % (segment['enable_rise_50_ns'], segment['settled_before_enable_ns'])),
        build('emission_flat', 'F', segment['flat_start_ns'], segment['flat_stop_ns'],
              'flat-part mean current for code %s, the number the sign rule is judged on' % code,
              'its full-enable partner %s#W%d; never averaged across a ramp' % (case_id, index),
              'enable is at its %s V platform for the whole window'
              % _g(contract_data['units']['logic_high_V'])),
        build('off_tail', 'T', segment['tail_start_ns'], segment['tail_stop_ns'],
              'signed tail Q of code %s, kept apart from the emission charge' % code,
              'its own leakage sub-window %s and the turn-off instants'
              % segment['leak_window_ns'],
              'enable falls to 50%% at %s ns and reaches %s V at %s ns'
              % (segment['enable_fall_50_ns'], _g(ENABLE_LOW_V), segment['fall_low_ns'])),
        build('pure_off', 'O', segment['pure_off_start_ns'], segment['pure_off_stop_ns'],
              'the only region a code change or a leakage measurement may live in; DATA_EN is 0 V '
              'across all of it',
              'the code-change edge inside it, if this platform has one',
              'enable finished falling at %s ns; the next rise starts at %s ns'
              % (segment['fall_low_ns'], segment['pure_off_stop_ns'])),
        build('leak_last100', 'L', leak_lo, leak_hi,
              'max(abs(I_sink)) over the last %s ns against %s A for code %s'
              % (_g(LEAK_WINDOW_NS), rules['shutoff_leakage']['limit_A'], code),
              'the tail window %s#T%d it belongs to; a positive and a negative half never cancel into '
              'a claim of zero leakage' % (case_id, index),
              'inside the pure-off window that starts at %s ns' % segment['pure_off_start_ns'])]


def _transient_rows(contract_data):
    units = contract_data['units']
    prep, offset = units['lead_off_ns'], units['transient_offset_ns']
    clamp = contract_data['rules']['clamp']
    rows, windows, pwl = [], [], []

    # TR-LONG: eight platforms at R2 relative 1500*k, shifted by the single recorded offset
    segments = []
    for index, code in enumerate(R2PLAN.DC_CODES):
        start = index * (_ns(R2PLAN.LONG_PLATFORM_TON) + _ns(R2PLAN.LONG_OFF_GAP_TON)) + offset
        change = None
        if index:
            previous = segments[-1]
            change = (float(previous['pure_off_start_ns'])
                      + start - _ns(R2PLAN.LONG_EDGE_TON)) / 2.0
        segments.append(_platform(start, _ns(R2PLAN.LONG_PLATFORM_TON), _ns(R2PLAN.LONG_EDGE_TON),
                                  code, code_change_ns=change))
    tail_ns = _ns(R2PLAN.LONG_TAIL_TON)
    stop_ns = float(segments[-1]['enable_fall_50_ns']) + tail_ns
    _close_platforms(segments, stop_ns, tail_ns)
    rows.append(_transient_row('TR-LONG', '000..111', 'pwl_per_platform', segments, stop_ns,
                               'each code changes with a %g ns edge in the middle of the %g ns '
                               'pure-off window before its own rising edge, so no change coincides '
                               'with an enable edge and none interpolates across a window'
                               % (units['code_edge_ns'], _ns(R2PLAN.LONG_OFF_GAP_TON)),
                               'fixed %s' % _g(clamp['main_eval_V']), contract_data))
    for index, segment in enumerate(segments):
        windows.extend(_window_rows('TR-LONG', index, segment, contract_data, R2PLAN.DC_CODES[index]))
    pwl.extend(_enable_pwl('TR-LONG', segments, units['logic_high_V'], prep, stop_ns))
    pwl.extend(_code_pwl('TR-LONG', segments, R2PLAN.DC_CODES[0], units['logic_high_V']))

    # the two short platforms: the R2 relative start is the gap, and that interval is preserved
    for case_id, platform_ton, gap_ton, edge_ton, tail_ton, code, note in R2PLAN.SHORT_CASES:
        platform, edge, tail = _ns(platform_ton), _ns(edge_ton), _ns(tail_ton)
        segment = _platform(_ns(gap_ton) + offset, platform, edge, code)
        stop_ns = float(segment['enable_fall_50_ns']) + tail
        _close_platforms([segment], stop_ns, tail)
        rows.append(_transient_row(
            case_id, code, 'pwl_single_platform', [segment], stop_ns,
            'the code is static from t=0 and settled %s ns before the only rising edge; the R2 '
            'relative %g ns start interval is kept and shifted by the same %g ns [%s]'
            % (segment['settled_before_enable_ns'], _ns(gap_ton), offset, note),
            'fixed %s' % _g(clamp['main_eval_V']), contract_data))
        windows.extend(_window_rows(case_id, 0, segment, contract_data, code))
        pwl.extend(_enable_pwl(case_id, [segment], units['logic_high_V'], prep, stop_ns))
        for bit, value in sorted(code_bits(code, units['logic_high_V']).items()):
            pwl.append({'case_id': case_id, 'signal': 'PAM bit', 'node': bit, 't_ns': _g(0),
                        'value_V': _g(value), 'role': 'static_dc_level', 'result': 'NOT_RUN'})

    # TR-OFFCODE: four platforms at relative gap + k*(platform+gap), both changes inside off windows
    _case_id, platform_ton, gap_ton, edge_ton, tail_ton, _code, _note = R2PLAN.OFFCODE_CASE
    platform, gap, edge, tail = _ns(platform_ton), _ns(gap_ton), _ns(edge_ton), _ns(tail_ton)
    codes = ['011', '100', '000', '111']
    segments = []
    for index, code in enumerate(codes):
        start = gap + index * (platform + gap) + offset
        change = None
        if index:
            previous = segments[-1]
            change = (float(previous['pure_off_start_ns']) + start - edge) / 2.0
        segments.append(_platform(start, platform, edge, code, code_change_ns=change))
    stop_ns = float(segments[-1]['enable_fall_50_ns']) + tail
    _close_platforms(segments, stop_ns, tail)
    rows.append(_transient_row('TR-OFFCODE', ','.join(codes), 'pwl_four_platforms', segments, stop_ns,
                               'both transitions (011->100 and 000->111) are %g ns edges in the '
                               'middle of the pure-off window before their own platform; the first '
                               'code is static from t=0 and the %g ns start interval is kept'
                               % (units['code_edge_ns'], gap),
                               'fixed %s' % _g(clamp['main_eval_V']), contract_data))
    for index, segment in enumerate(segments):
        windows.extend(_window_rows('TR-OFFCODE', index, segment, contract_data, codes[index]))
    pwl.extend(_enable_pwl('TR-OFFCODE', segments, units['logic_high_V'], prep, stop_ns))
    pwl.extend(_code_pwl('TR-OFFCODE', segments, codes[0], units['logic_high_V']))
    return rows, windows, pwl, dict((r['case_id'], r) for r in rows)


def _refined_rows(by_id):
    rows = []
    for case_id, partner in sorted(R2PLAN.PARTNER_CONTRACT.items()):
        base = by_id[partner]
        row = dict((field, base.get(field, '')) for field in SCHEDULE_HEADER)
        row.update({'case_id': case_id, 'class': 'refined_step',
                    'maxstep_ns': _g(R2PLAN.MAXSTEP_FINE_NS), 'paired_case': partner,
                    'analysis_line': 'tran_case tran stop=%s maxstep=%s'
                                      % (_n(base['stop_ns']), _n(_g(R2PLAN.MAXSTEP_FINE_NS)))})
        rows.append(row)
    return rows


def _refined_windows(base_windows):
    """a refined case owns its own window rows: same instants as its partner, its own identity"""
    out = []
    for case_id, partner in sorted(dict(R2PLAN.PARTNER_CONTRACT).items()):
        for window in base_windows:
            if window['case_id'] != partner:
                continue
            clone = dict(window)
            clone['window_id'] = window['window_id'].replace('%s#' % partner, '%s#' % case_id, 1)
            clone['case_id'] = case_id
            clone['quantity'] = '%s [refined from %s, same instants, maxstep %s ns instead of %s]' \
                                % (window['quantity'], partner, _g(R2PLAN.MAXSTEP_FINE_NS),
                                   _g(R2PLAN.MAXSTEP_WIDE_NS))
            out.append(clone)
    return out


def _refined_pwl(base_pwl):
    out = []
    for case_id, partner in sorted(dict(R2PLAN.PARTNER_CONTRACT).items()):
        for item in base_pwl:
            if item['case_id'] != partner:
                continue
            clone = dict(item)
            clone['case_id'] = case_id
            clone['role'] = '%s [refined from %s]' % (item['role'], partner)
            out.append(clone)
    return out


def build():
    contract_data = CONTRACT.contract()
    dc_rows, dc_windows, dc_pwl = _dc_rows(contract_data)
    tr_rows, tr_windows, tr_pwl, by_id = _transient_rows(contract_data)
    rows = dc_rows + tr_rows + _refined_rows(by_id)
    windows = dc_windows + tr_windows + _refined_windows(tr_windows)
    # the DC static levels are waveform rows too: they belong in pwl.csv, where the PREP build dropped
    # them, so a reviewer reading one table sees the level of every source in every case
    return rows, windows, dc_pwl + tr_pwl + _refined_pwl(tr_pwl), contract_data


def _floats(text):
    return [float(part) for part in str(text).split(';') if part not in ('', DC_NO_TIME)]


def _parts(text):
    return [part for part in str(text).split(';') if part != DC_NO_TIME]


def _pairs(pwl, case_id, node):
    items = [item for item in pwl if item['case_id'] == case_id and item['node'] == node]
    items.sort(key=lambda item: float(item['t_ns']))
    return [(float(item['t_ns']), float(item['value_V'])) for item in items]


def value_at(pairs, at_ns):
    """the piecewise-linear value of a waveform row at one instant

    A PWL source holds its last value to the end of the run, so an instant after the final point reads
    back that final value; answering "no interval" there would be a fault of this reader, not of the
    waveform, and the reader is the thing under test.
    """
    if not pairs:
        return None
    if at_ns <= pairs[0][0]:
        return pairs[0][1]
    for (t0, v0), (t1, v1) in zip(pairs, pairs[1:]):
        if t0 <= at_ns <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (at_ns - t0) / float(t1 - t0)
    return pairs[-1][1]


def _pairs_of(cell):
    return [(float(part.split('-')[0]), float(part.split('-')[1]))
            for part in _parts(cell) if '-' in part]


def _leak_bounds(row):
    return _pairs_of(row['leak_window_ns'])


def validate(rows, windows, pwl, contract_data):
    """arithmetic over the schedule, over the waveform rows it produced, and over the five windows

    Nothing here trusts a column because the same code wrote it: the 50 % edges are re-interpolated
    from the DATA_EN pairs, the PAM ramps are tested against the enable-active regions, and every
    window row is compared with the instants its own schedule row declares.
    """
    problems = []
    units = contract_data['units']
    by_id = dict((r['case_id'], r) for r in rows)
    if len(rows) != 15:
        problems.append('the schedule has %d rows, the plan is 8 DC + 4 transient + 3 refined'
                        % len(rows))
    dc = [r for r in rows if r['class'] == 'dc_sweep']
    if sorted(r['pam_code'] for r in dc) != sorted(R2PLAN.DC_CODES):
        problems.append('the DC rows do not carry exactly one row per thermometer code')
    for row in dc:
        if row['data_en_form'] != 'static_dc':
            problems.append('%s is a DC case driven with %s; an absolute-current point needs the '
                            'static enable, not a pulse that starts at zero'
                            % (row['case_id'], row['data_en_form']))
        if row['platform_start_ns'] != DC_NO_TIME:
            problems.append('%s gives a DC case a time window' % row['case_id'])
        if 'step=%s' % _g(contract_data['rules']['clamp']['sweep_step_V']) not in row['analysis_line']:
            problems.append('%s does not sweep with the contracted %s V step'
                            % (row['case_id'], _g(contract_data['rules']['clamp']['sweep_step_V'])))
        if not row['analysis_line'].startswith('dc_case dc '):
            problems.append('%s analysis line has no instance name before the analysis type'
                            % row['case_id'])
        expected = code_bits(row['pam_code'], units['logic_high_V'])
        written = dict((item['node'], float(item['value_V'])) for item in pwl
                       if item['case_id'] == row['case_id'] and item['node'] in expected)
        for bit in sorted(expected):
            if abs(written.get(bit, -1.0) - expected[bit]) > 1e-12:
                problems.append('%s writes %s = %s V, but bit-weight arithmetic on code %s says %s V '
                                '(the PREP rows wrote the code string left-to-right)'
                                % (row['case_id'], bit, written.get(bit), row['pam_code'],
                                   _g(expected[bit])))
    for row in rows:
        if row['class'] != 'dc_sweep':
            problems.extend(_validate_transient(row, pwl, units))
    problems.extend(_validate_pwl_lines(rows, pwl, units))
    problems.extend(_validate_pairs(by_id, rows, pwl, units, contract_data))
    for case_id, partner in sorted(R2PLAN.PARTNER_CONTRACT.items()):
        refined, base = by_id.get(case_id), by_id.get(partner)
        if refined is None or base is None:
            problems.append('%s or its partner %s is missing' % (case_id, partner))
            continue
        drift = [field for field in SCHEDULE_HEADER
                 if field not in ('case_id', 'class', 'maxstep_ns', 'paired_case', 'analysis_line',
                                  'result') and str(refined.get(field)) != str(base.get(field))]
        if drift:
            problems.append('%s differs from %s outside the time step: %s'
                            % (case_id, partner, ','.join(sorted(drift))))
        if refined['maxstep_ns'] == base['maxstep_ns']:
            problems.append('%s repeats the maxstep of %s, so it refines nothing' % (case_id, partner))
        if refined['class'] != 'refined_step' or refined['paired_case'] != partner:
            problems.append('%s is not declared as a refinement of %s' % (case_id, partner))
    budget = contract_data['launch_budget']
    total_dut = sum(int(r['launch_processes_dut']) for r in rows)
    total_pre = sum(int(r['launch_processes_preflight']) for r in rows)
    if (total_dut, total_pre) != (budget['dut_runs'], budget['preflight_runs']):
        problems.append('the per-case plan adds to %d DUT + %d preflight, the contract proposes %d '
                        '+ %d' % (total_dut, total_pre, budget['dut_runs'], budget['preflight_runs']))
    for row in rows:
        if (int(row['launch_processes_dut']), int(row['launch_processes_preflight'])) != (1, 1):
            problems.append('%s plans %s DUT and %s preflight processes; each case is one of each'
                            % (row['case_id'], row['launch_processes_dut'],
                               row['launch_processes_preflight']))
    problems.extend(_validate_windows(rows, windows))
    problems.extend(_validate_waveform_rows(by_id, pwl))
    return problems


def _validate_transient(row, pwl, units):
    """one transient row, its own columns, and the enable waveform that must agree with them"""
    problems = []
    starts, stops = _floats(row['platform_start_ns']), _floats(row['platform_stop_ns'])
    rise_low, rise_high = _floats(row['rise_low_ns']), _floats(row['rise_high_ns'])
    fall_high, fall_low = _floats(row['fall_high_ns']), _floats(row['fall_low_ns'])
    full_lo, full_hi = _floats(row['full_window_start_ns']), _floats(row['full_window_stop_ns'])
    flat_lo, flat_hi = _floats(row['flat_start_ns']), _floats(row['flat_stop_ns'])
    tail_s, tail_e = _floats(row['tail_start_ns']), _floats(row['tail_stop_ns'])
    off_s, off_e = _floats(row['pure_off_start_ns']), _floats(row['pure_off_stop_ns'])
    leak = _leak_bounds(row)
    settle = _floats(row['settled_before_enable_ns'])
    counts = set(len(x) for x in (starts, stops, rise_low, rise_high, fall_high, fall_low, full_lo,
                                  full_hi, flat_lo, flat_hi, tail_s, tail_e, off_s, off_e, settle,
                                  leak))
    if counts != {len(starts)}:
        problems.append('%s gives a different number of instants per column: %s'
                        % (row['case_id'], sorted(counts)))
        return problems
    if row['lead_off_ns'] != _g(units['lead_off_ns']) or \
            row['offset_applied_ns'] != _g(units['transient_offset_ns']):
        problems.append('%s does not record the %s ns preparation and the %s ns offset the contract '
                        'declares' % (row['case_id'], _g(units['lead_off_ns']),
                                      _g(units['transient_offset_ns'])))
    if _pairs_of(row['off_window_ns']) != list(zip(off_s, off_e)):
        problems.append('%s writes off_window_ns %s, which is not the pure-off interval its own '
                        'pure_off_start_ns/pure_off_stop_ns columns declare'
                        % (row['case_id'], row['off_window_ns']))
    enable = _pairs(pwl, row['case_id'], 'data_en')
    edge = float(row['edge_ns'])
    if edge > units['edge_ns']:
        problems.append('%s uses a %s ns half-edge above the declared maximum %s ns'
                        % (row['case_id'], _g(edge), _g(units['edge_ns'])))
    for index in range(len(starts)):
        if not (rise_low[index] < starts[index] < rise_high[index]):
            problems.append('%s platform %d is not between its own ramp endpoints'
                            % (row['case_id'], index))
        for width, what in (((rise_high[index] - rise_low[index]) / 2.0, 'rise'),
                            ((fall_low[index] - fall_high[index]) / 2.0, 'fall')):
            if abs(width - edge) > 1e-9:
                problems.append('%s %s ramp %d is a %s ns half-edge, not the declared %s ns'
                                % (row['case_id'], what, index, _g(width), _g(edge)))
        if full_lo[index] != starts[index] or full_hi[index] != stops[index]:
            problems.append('%s window %d: the full-enable bounds are not the two 50%% points'
                            % (row['case_id'], index))
        if not (starts[index] <= flat_lo[index] < flat_hi[index] <= stops[index]):
            problems.append('%s window %d: the flat part %s-%s is not inside the platform %s-%s'
                            % (row['case_id'], index, _g(flat_lo[index]), _g(flat_hi[index]),
                               _g(starts[index]), _g(stops[index])))
        if tail_s[index] != stops[index] or tail_e[index] <= stops[index]:
            problems.append('%s tail %d does not start at this platform fall50 and run past it'
                            % (row['case_id'], index))
        if not (off_s[index] < off_e[index]) or off_s[index] != fall_low[index]:
            problems.append('%s pure-off window %d is %s-%s, which is not the fall endpoint up to the '
                            'next ramp start' % (row['case_id'], index, _g(off_s[index]),
                                                 _g(off_e[index])))
        if abs((leak[index][1] - leak[index][0]) - LEAK_WINDOW_NS) > 1e-9:
            problems.append('%s leakage window %d is %s ns, not the contracted %s ns'
                            % (row['case_id'], index, _g(leak[index][1] - leak[index][0]),
                               _g(LEAK_WINDOW_NS)))
        if leak[index][1] != tail_e[index]:
            problems.append('%s leakage window %d does not end where its tail window ends'
                            % (row['case_id'], index))
        if leak[index][0] < off_s[index] or leak[index][1] > off_e[index]:
            problems.append('%s leakage window %d is %s-%s ns, outside its pure-off window %s-%s ns, '
                            'so a falling or rising enable would be measured as leakage'
                            % (row['case_id'], index, _g(leak[index][0]), _g(leak[index][1]),
                               _g(off_s[index]), _g(off_e[index])))
        if index and stops[index - 1] >= starts[index]:
            problems.append('%s platforms %d and %d overlap' % (row['case_id'], index - 1, index))
        if settle[index] <= 0:
            problems.append('%s platform %d has no settle time between its code edge and its ramp'
                            % (row['case_id'], index))
        # the reviewer's own reading of the waveform, against the number the table claims: the level
        # is half the enable's high, the time is only where to look for it
        tolerance = edge + TIME_DISPLAY_LSB_NS
        half_rail = float(row['logic_high_V']) / 2.0
        rise_found = cross_at(enable, half_rail, starts[index], tolerance)
        if rise_found is None or _g(rise_found) != _g(starts[index]):
            problems.append('%s platform %d: the delivered DATA_EN pairs cross 50%% (%s V) at %s, '
                            'while the table declares its rise at %s ns'
                            % (row['case_id'], index, _g(half_rail),
                               _g(rise_found) if rise_found is not None
                               else 'no crossing within the ramp', _g(starts[index])))
        fall_found = cross_at(enable, half_rail, stops[index], tolerance)
        if fall_found is None or _g(fall_found) != _g(stops[index]):
            problems.append('%s platform %d: the delivered DATA_EN pairs cross 50%% (%s V) at %s, '
                            'while the table declares its fall at %s ns'
                            % (row['case_id'], index, _g(half_rail),
                               _g(fall_found) if fall_found is not None
                               else 'no crossing within the ramp', _g(stops[index])))
    changes = _parts(row['code_change_ns'])
    numeric = [part for part in changes if part != STATIC]
    if len(numeric) and len(changes) != len(starts):
        problems.append('%s declares %d code-change entries for %d platforms'
                        % (row['case_id'], len(changes), len(starts)))
    for index, part in enumerate(changes):
        if part == STATIC:
            continue
        change = float(part)
        owner = index - 1
        if owner < 0 or owner >= len(off_s):
            problems.append('%s code change %s ns has no pure-off window to sit in'
                            % (row['case_id'], part))
            continue
        half = units['code_edge_ns'] / 2.0
        if not (off_s[owner] < change - half and change + half < off_e[owner]):
            problems.append('%s changes code for platform %d at %s ns with a %g ns edge that does not '
                            'fit inside the pure-off window %s-%s ns'
                            % (row['case_id'], index, _g(change), units['code_edge_ns'],
                               _g(off_s[owner]), _g(off_e[owner])))
    if float(row['stop_ns']) <= stops[-1]:
        problems.append('%s stops at %s ns, before its last platform ends at %s ns'
                        % (row['case_id'], row['stop_ns'], row['platform_stop_ns']))
    if not row['analysis_line'].startswith('%s tran ' % row['analysis_name']):
        problems.append('%s analysis line %r has no instance name before the analysis type'
                        % (row['case_id'], row['analysis_line']))
    if 'stop=%sn' % row['stop_ns'] not in row['analysis_line'] or \
            'maxstep=%sn' % row['maxstep_ns'] not in row['analysis_line']:
        problems.append('%s analysis line does not carry its own stop and maxstep' % row['case_id'])
    return problems


def _validate_pwl_lines(rows, pwl, units):
    """no PAM segment may interpolate across a region where DATA_EN is not at its low level"""
    problems = []
    by_id = dict((r['case_id'], r) for r in rows)
    cases = sorted(set(item['case_id'] for item in pwl
                       if item['node'] in ('pam0', 'pam1', 'pam2')))
    for case_id in cases:
        row = by_id.get(case_id)
        if row is None or row['class'] == 'dc_sweep':
            continue
        active = list(zip(_floats(row['rise_low_ns']), _floats(row['fall_low_ns'])))
        for node in ('pam0', 'pam1', 'pam2'):
            pairs = _pairs(pwl, case_id, node)
            for index in range(1, len(pairs)):
                (t0, v0), (t1, v1) = pairs[index - 1], pairs[index]
                if v0 == v1:
                    continue
                for low, high in active:
                    if max(t0, low) < min(t1, high):
                        problems.append('%s.%s ramps %s V -> %s V over %s-%s ns, a line that '
                                        'interpolates across %s-%s ns where DATA_EN is not low (the '
                                        'PREP rows did this 36 times)'
                                        % (case_id, node, _g(v0), _g(v1), _g(t0), _g(t1), _g(low),
                                           _g(high)))
                        break
                width = t1 - t0
                if width > units['code_edge_ns'] + TIME_DISPLAY_LSB_NS:
                    problems.append('%s.%s changes value across %s ns, wider than the declared %g ns '
                                    'code edge, so the bit moves during a window rather than between '
                                    'windows' % (case_id, node, _g(width), units['code_edge_ns']))
    return problems


def _validate_pairs(by_id, rows, pwl, units, contract_data):
    """the code identity read back off the waveform rows, platform by platform"""
    problems = []
    logic_high = contract_data['units']['logic_high_V']
    for row in rows:
        if row['class'] == 'dc_sweep':
            continue
        codes = [row['pam_code']] if row['pam_code'] != '000..111' else sorted(
            contract_data['nominal_current_A_by_code'])
        if ',' in row['pam_code']:
            codes = row['pam_code'].split(',')
        starts = _floats(row['platform_start_ns'])
        if len(codes) != len(starts):
            problems.append('%s names %d codes for %d platforms' % (row['case_id'], len(codes),
                                                                    len(starts)))
            continue
        for index, code in enumerate(codes):
            sample = float(starts[index]) + 1.0     # inside the platform, past its code edge
            written = dict((node, value_at(_pairs(pwl, row['case_id'], node), sample))
                           for node in ('pam0', 'pam1', 'pam2'))
            expected = code_bits(code, logic_high)
            for node in sorted(expected):
                if written.get(node) is None or abs(written[node] - expected[node]) > 1e-12:
                    problems.append('%s platform %d (code %s) drives %s = %s, bit-weight arithmetic '
                                    'says %s V' % (row['case_id'], index, code, node,
                                                   _g(written.get(node)) if written.get(node)
                                                   is not None else 'no waveform at all',
                                                   _g(expected[node])))
    return problems


def _validate_windows(rows, windows):
    problems = []
    for window in windows:
        if window['result'] != 'NOT_RUN':
            problems.append('window %s reports a result instead of NOT_RUN' % window['window_id'])
        if window['kind'] == 'dc_sweep_point':
            continue
        if float(window['start_ns']) >= float(window['stop_ns']):
            problems.append('window %s (%s) runs backwards: %s-%s'
                            % (window['window_id'], window['kind'], window['start_ns'],
                               window['stop_ns']))
        elif _g(float(window['stop_ns']) - float(window['start_ns'])) != window['length_ns']:
            problems.append('window %s states length %s for %s-%s'
                            % (window['window_id'], window['length_ns'], window['start_ns'],
                               window['stop_ns']))
    if not any(w['kind'] == 'dc_sweep_point' for w in windows):
        problems.append('no DC sweep window is declared')
    for row in rows:
        expected = 0 if row['class'] == 'dc_sweep' else len(_floats(row['platform_start_ns']))
        for kind, suffix, low_field, high_field in WINDOW_FIELDS:
            found = [w for w in windows if w['case_id'] == row['case_id'] and w['kind'] == kind]
            if len(found) != expected:
                problems.append('%s declares %d platforms but has %d %s window rows'
                                % (row['case_id'], expected, len(found), kind))
            declared_lo = ([part.split('-')[0] for part in _parts(row[low_field])]
                           if kind == 'leak_last100' else _floats(row[low_field]))
            declared_hi = ([part.split('-')[1] for part in _parts(row[high_field])]
                           if kind == 'leak_last100' else _floats(row[high_field]))
            for index, window in enumerate(sorted(found, key=lambda w: w['window_id'])):
                if window['window_id'] != '%s#%s%d' % (row['case_id'], suffix, index):
                    problems.append('%s window %s is not stably numbered #%s%d, so a later pass could '
                                    'pair it with the wrong platform'
                                    % (row['case_id'], window['window_id'], suffix, index))
                if index >= len(declared_lo):
                    problems.append('%s has more %s rows than its row declares instants'
                                    % (row['case_id'], kind))
                    break
                if _g(float(window['start_ns'])) != _g(float(declared_lo[index])) or \
                        _g(float(window['stop_ns'])) != _g(float(declared_hi[index])):
                    problems.append('%s %s window %s does not repeat the instants the schedule row '
                                    'declares' % (row['case_id'], kind, window['window_id']))
    return problems


def _validate_waveform_rows(by_id, pwl):
    problems = []
    by_case = {}
    for item in pwl:
        by_case.setdefault(item['case_id'], []).append(item)
    for case_id in sorted(by_case):
        row = by_id.get(case_id)
        if row is None:
            problems.append('%s has waveform rows but no schedule row' % case_id)
            continue
        items = by_case[case_id]
        if row['class'] == 'dc_sweep':
            if any(float(item['t_ns']) != 0 for item in items):
                problems.append('%s is a DC case but carries a waveform away from t=0' % case_id)
            continue
        enables = sorted([i for i in items if i['node'] == 'data_en'], key=lambda i: float(i['t_ns']))
        if not enables:
            problems.append('%s has no DATA_EN waveform' % case_id)
            continue
        times = [float(i['t_ns']) for i in enables]
        if len(set(times)) != len(times):
            problems.append('%s repeats a DATA_EN time, which is two values at one instant' % case_id)
        if float(enables[0]['value_V']) != ENABLE_LOW_V:
            problems.append('%s starts its enable at %s V, so the first rise is not a real edge'
                            % (case_id, enables[0]['value_V']))
        if any(float(item['t_ns']) > float(row['stop_ns']) for item in items):
            problems.append('%s has a waveform point past its declared stop' % case_id)
    return problems


def emit(directory=ROOT):
    rows, windows, pwl, contract_data = build()
    problems = validate(rows, windows, pwl, contract_data)
    if problems:
        for line in problems[:12]:
            print('  SCHEDULE_REFUSED ' + line)
        raise SystemExit('D7C_B_SCHEDULE: refused to emit, %d problem(s)' % len(problems))
    outputs = {}
    for name, header, data in ((SCHEDULE_TABLE, SCHEDULE_HEADER, rows),
                               (WINDOWS_TABLE, WINDOWS_HEADER, windows),
                               (PWL_TABLE, PWL_HEADER, pwl)):
        target = os.path.join(directory, name.replace('/', os.sep))
        CHECK.rows_write(target, header, data)
        outputs[name] = target
    return outputs, rows, windows, pwl, contract_data


def _read_strict(target, header, name):
    """header must match, every row must have exactly the declared width; refusals are data"""
    if not os.path.isfile(target):
        return None, ['%s is missing' % name]
    with io.open(target, encoding='utf-8', newline='') as handle:
        table = list(csv.reader(handle))
    if not table:
        return None, ['%s is an empty file, not a table with zero rows' % name]
    if table[0] != list(header):
        return None, ['%s header is %s, the schema declares %s' % (name, table[0], list(header))]
    if len(table) - 1 == 0:
        return None, ['%s has a header and no rows, which is a missing input, not an empty result'
                      % name]
    rows, problems = [], []
    for number, cells in enumerate(table[1:], 2):
        if len(cells) != len(header):
            problems.append('%s line %d has %d cells, the header declares %d'
                            % (name, number, len(cells), len(header)))
            continue
        rows.append(dict(zip(header, cells)))
    return rows, problems


def read_delivered(directory=ROOT):
    rows, windows, pwl = [], [], []
    problems = []
    for name, header, sink in ((SCHEDULE_TABLE, SCHEDULE_HEADER, rows),
                               (WINDOWS_TABLE, WINDOWS_HEADER, windows),
                               (PWL_TABLE, PWL_HEADER, pwl)):
        target = os.path.join(directory, name.replace('/', os.sep))
        loaded, table_problems = _read_strict(target, header, name)
        problems.extend(table_problems)
        if loaded is not None:
            sink.extend(loaded)
    if problems:
        return None, None, None, problems
    return rows, windows, pwl, []


def check(directory=ROOT):
    """judge the delivered bytes, not the in-memory build"""
    rows, windows, pwl, problems = read_delivered(directory)
    if problems:
        return problems
    contract_data = CONTRACT.load(os.path.join(directory,
                                               CONTRACT.CONTRACT_PATH.replace('/', os.sep)))
    return validate(rows, windows, pwl, contract_data)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--emit', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', default=ROOT)
    arguments = parser.parse_args(argv)
    directory = os.path.abspath(arguments.root)
    if arguments.emit:
        outputs, rows, windows, pwl, contract_data = emit(directory)
        print('D7C_B_SCHEDULE_EMITTED rows=%d windows=%d pwl_points=%d files=%s'
              % (len(rows), len(windows), len(pwl),
                 ','.join(sorted(os.path.basename(p) for p in outputs.values()))))
        return 0
    if arguments.check:
        problems = check(directory)
        rows, windows, pwl, unreadable = read_delivered(directory)
        print('D7C_B_SCHEDULE_CHECK: %s (rows=%s windows=%s pwl=%s problems=%d)'
              % ('PASS' if not (problems or unreadable) else 'FAIL',
                 len(rows) if rows else 'unreadable', len(windows) if windows else 'unreadable',
                 len(pwl) if pwl else 'unreadable', len(problems) + len(unreadable)))
        for line in (problems + unreadable)[:12]:
            print('  PROBLEM ' + line)
        return 1 if (problems or unreadable) else 0
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
