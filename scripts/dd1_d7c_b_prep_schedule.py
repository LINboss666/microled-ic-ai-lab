#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_schedule.py -- absolute, reviewable timing for the fifteen decks.

DATA-7C-B-PREP section 5. The delivered R2 schedule (scripts/dd1_d7c_a_r2_plan.py) is the input for
the *relative* times; this module adds the two things the review asked for and nothing else:

  * one uniform 1 us initial-off lead (LEAD_OFF_NS), recorded per case as the offset actually applied,
    so every platform, code change, integration window and stop shifts by the same amount and the
    first enable really has a rising edge to find (R2 started TR-LONG already conducting at t=0);
  * the instants named apart: platform start/stop, the 50% enable edges, the integration window, the
    off window, the tail window and the last-100 ns leakage sub-window are separate columns. "A 120 ns
    platform" is no longer one phrase covering two different pairs of times.

The enable ramp is symmetric about its 50% point: the rise runs over [start-edge, start+edge] and the
fall over [stop-edge, stop+edge], so the flat part between the ramps is exactly the integration window
the R2 table declares. The PAM bits change at the middle of the off window instead of at the same
instant the enable starts to rise, which makes "the code changes while the branch is off" a fact a
reviewer can re-derive from the columns rather than a boundary coincidence; the rule and the settle
time are emitted beside the numbers.

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

SCHEDULE_HEADER = ['case_id', 'class', 'pam_code', 'data_en_form', 'data_en_level_V', 'lead_off_ns',
                   'offset_applied_ns', 'platform_start_ns', 'platform_stop_ns', 'enable_rise_50_ns',
                   'enable_fall_50_ns', 'window_start_ns', 'window_stop_ns', 'off_window_ns',
                   'tail_start_ns', 'tail_stop_ns', 'leak_last100_start_ns', 'code_change_ns',
                   'code_change_rule', 'settled_before_enable_ns', 'stop_ns', 'maxstep_ns',
                   'paired_case', 'clamp_sweep_V', 'analysis_line', 'launch_processes_dut',
                   'launch_processes_preflight', 'result']
WINDOWS_HEADER = ['case_id', 'window_id', 'kind', 'start_ns', 'stop_ns', 'length_ns', 'quantity',
                  'measure_together_with', 'state_at_start', 'result']
PWL_HEADER = ['case_id', 'signal', 'node', 't_ns', 'value_V', 'role', 'result']

DC_NO_TIME = 'dc_no_time_window'
LEAK_WINDOW_NS = 100.0
ENABLE_LOW_V = 0.0
# every time column is printed with three decimals of a nanosecond, so the display resolves at
# 0.1 ps and a tolerance that claims finer than that would be a quantisation artefact
TIME_DISPLAY_DECIMALS = 3
TIME_DISPLAY_LSB_NS = 10 ** -TIME_DISPLAY_DECIMALS


def _ns(value_ton):
    return float(value_ton) * R2PLAN.TON_NS


def _g(value):
    return ('%.*f' % (TIME_DISPLAY_DECIMALS, round(float(value), TIME_DISPLAY_DECIMALS)))


def _n(text):
    return '%sn' % text


def _code_bits(code):
    return {'pam0': float(int(code[0])), 'pam1': float(int(code[1])), 'pam2': float(int(code[2]))}


def _platform(start_ns, platform_ns, edge_ns, tail_ns, code, code_change_ns=None):
    """one emission platform: its ramps, its flat integration window and its tail"""
    stop_ns = start_ns + platform_ns
    return {
        'pam_code': code,
        'platform_start_ns': _g(start_ns), 'platform_stop_ns': _g(stop_ns),
        'enable_rise_50_ns': _g(start_ns), 'enable_fall_50_ns': _g(stop_ns),
        'window_start_ns': _g(start_ns + edge_ns), 'window_stop_ns': _g(stop_ns - edge_ns),
        'tail_start_ns': _g(stop_ns), 'tail_stop_ns': _g(stop_ns + tail_ns),
        'leak_last100_start_ns': _g(max(stop_ns, stop_ns + tail_ns - LEAK_WINDOW_NS)),
        'edge_ns': _g(edge_ns), 'rise_low_ns': _g(start_ns - edge_ns),
        'rise_high_ns': _g(start_ns + edge_ns), 'fall_high_ns': _g(stop_ns - edge_ns),
        'fall_low_ns': _g(stop_ns + edge_ns),
        'code_change_ns': _g(code_change_ns) if code_change_ns is not None else 'static_from_t0',
        # a code that never changes has been constant since t=0, so it is settled for the whole
        # time from t=0 up to this platform's ramp
        'settled_before_enable_ns': (_g(start_ns - code_change_ns)
                                     if code_change_ns is not None else _g(start_ns))}


def _multi(row, segments, field):
    row[field] = ';'.join(segment[field] for segment in segments)


def _dc_rows(contract_data):
    sweep = ','.join(_g(v) for v in contract_data['clamp_sweep_points_V'])
    clamp = contract_data['rules']['clamp']
    analysis = 'dc dev=Vclamp param=dc start=%s stop=%s step=%s' % (
        _g(clamp['sweep_start_V']), _g(clamp['sweep_stop_V']), _g(clamp['sweep_step_V']))
    rows, windows, pwl = [], [], []
    for code in R2PLAN.DC_CODES:
        nominal = contract_data['nominal_current_A_by_code'][code]
        row = {'case_id': 'DC-%s' % code, 'class': 'dc_sweep', 'pam_code': code,
               'data_en_form': 'static_dc', 'data_en_level_V': _g(1.8),
               'lead_off_ns': _g(0), 'offset_applied_ns': _g(0),
               'platform_start_ns': DC_NO_TIME, 'platform_stop_ns': DC_NO_TIME,
               'enable_rise_50_ns': DC_NO_TIME, 'enable_fall_50_ns': DC_NO_TIME,
               'window_start_ns': DC_NO_TIME, 'window_stop_ns': DC_NO_TIME,
               'off_window_ns': DC_NO_TIME, 'tail_start_ns': DC_NO_TIME,
               'tail_stop_ns': DC_NO_TIME, 'leak_last100_start_ns': DC_NO_TIME,
               'code_change_ns': 'static_from_t0',
               'code_change_rule': 'the three PAM bits are static levels for the whole sweep, so this '
                                   'case has no code change to place',
               'settled_before_enable_ns': DC_NO_TIME, 'stop_ns': DC_NO_TIME,
               'maxstep_ns': 'not_applicable_dc_analysis', 'paired_case': '',
               'clamp_sweep_V': sweep, 'analysis_line': analysis,
               'launch_processes_dut': '1', 'launch_processes_preflight': '1', 'result': 'NOT_RUN'}
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
                                          'declares' % (_g(1.8), code), 'result': 'NOT_RUN'})
        pwl.append({'case_id': row['case_id'], 'signal': 'DATA_EN', 'node': 'data_en',
                    't_ns': _g(0), 'value_V': _g(1.8), 'role': 'static_dc_level',
                    'result': 'NOT_RUN'})
        for bit, value in sorted(_code_bits(code).items()):
            pwl.append({'case_id': row['case_id'], 'signal': 'PAM bit', 'node': bit, 't_ns': _g(0),
                        'value_V': _g(value), 'role': 'static_dc_level', 'result': 'NOT_RUN'})
    return rows, windows, pwl


def _enable_pwl(case_id, segments, high, lead):
    """the enable as adjacent time/value pairs; symmetric ramps, so the 50% point is the platform edge"""
    points = [(_g(0), _g(ENABLE_LOW_V), 'initial_off_start'), (_g(lead), _g(ENABLE_LOW_V), 'lead_end')]
    for segment in segments:
        points.extend([
            (segment['rise_low_ns'], _g(ENABLE_LOW_V), 'rise_start'),
            (segment['rise_high_ns'], _g(high), 'rise_end_50pct_plus_edge'),
            (segment['fall_high_ns'], _g(high), 'fall_start_minus_edge'),
            (segment['fall_low_ns'], _g(ENABLE_LOW_V), 'fall_end')])
    ordered, seen = [], set()
    for time, value, role in points:
        key = (time, value)
        if key in seen:
            continue
        seen.add(key)
        ordered.append((time, value, role))
    ordered.sort(key=lambda item: float(item[0]))
    return [{'case_id': case_id, 'signal': 'DATA_EN', 'node': 'data_en', 't_ns': time,
             'value_V': value, 'role': role, 'result': 'NOT_RUN'}
            for time, value, role in ordered]


def _code_pwl(case_id, segments, lead):
    """the three PAM bits as their own piecewise line, changing only inside an off window"""
    rows = []
    for bit in ('pam0', 'pam1', 'pam2'):
        points = [(_g(0), _g(_code_bits(segments[0]['pam_code'])[bit]), 'initial_code_before_lead')]
        for segment in segments:
            points.append((segment['code_change_ns'],
                           _g(_code_bits(segment['pam_code'])[bit]), 'code_change_in_off_window'))
        seen, ordered = set(), []
        for time, value, role in points:
            if (time, value) in seen:
                continue
            seen.add((time, value))
            ordered.append((time, value, role))
        for index, (time, value, role) in enumerate(ordered):
            rows.append({'case_id': case_id, 'signal': 'PAM bit', 'node': bit, 't_ns': time,
                         'value_V': value,
                         'role': '%s_%d_of_%d' % (role, index + 1, len(ordered)),
                         'result': 'NOT_RUN'})
    return rows


def _transient_rows(contract_data):
    rows, windows, pwl = [], [], []
    lead = float(contract_data['units']['lead_off_ns'])
    clamp = contract_data['rules']['clamp']
    segments = []
    previous = None
    settle_long = _ns(R2PLAN.LONG_OFF_GAP_TON) / 2.0
    for index, code in enumerate(R2PLAN.DC_CODES):
        start = lead + index * (_ns(R2PLAN.LONG_PLATFORM_TON) + _ns(R2PLAN.LONG_OFF_GAP_TON))
        segments.append(_platform(start, _ns(R2PLAN.LONG_PLATFORM_TON), _ns(R2PLAN.LONG_EDGE_TON),
                                  _ns(R2PLAN.LONG_TAIL_TON), code,
                                  code_change_ns=start - settle_long))
        previous = start + _ns(R2PLAN.LONG_PLATFORM_TON)
    stop_ns = lead + _ns(R2PLAN.LONG_STOP_TON)
    long_row = _transient_row('TR-LONG', '000..111', 'pwl_per_platform', lead, segments, stop_ns,
                              'each code changes %s ns before its own rising edge, the middle of the '
                              '%s ns off window, so no change coincides with an enable edge'
                              % (_g(settle_long), _g(_ns(R2PLAN.LONG_OFF_GAP_TON))),
                              'fixed %s' % _g(clamp['main_eval_V']))
    rows.append(long_row)
    for index, segment in enumerate(segments):
        code = R2PLAN.DC_CODES[index]
        windows.extend(_window_rows('TR-LONG', index, segment, contract_data, code))
    pwl.extend(_enable_pwl('TR-LONG', segments, 1.8, lead))
    pwl.extend(_code_pwl('TR-LONG', segments, lead))

    for case_id, platform_ton, gap_ton, edge_ton, tail_ton, code, note in R2PLAN.SHORT_CASES:
        gap, platform, edge, tail = _ns(gap_ton), _ns(platform_ton), _ns(edge_ton), _ns(tail_ton)
        start = lead + gap
        segment = _platform(start, platform, edge, tail, code)
        row = _transient_row(case_id, code, 'pwl_single_platform', lead, [segment],
                             float(segment['tail_stop_ns']),
                             'the code is static from t=0 and settled %s ns before the only rising '
                             'edge, so the first enable is a real edge [inherited R2 note, recorded '
                             'as difference D3 in the contract: %s]' % (_g(start), note),
                             'fixed %s' % _g(clamp['main_eval_V']))
        row['off_window_ns'] = '%s-%s' % (_g(0), segment['rise_low_ns'])
        rows.append(row)
        windows.extend(_window_rows(case_id, 0, segment, contract_data, code))
        pwl.extend(_enable_pwl(case_id, [segment], 1.8, lead))
        for bit, value in sorted(_code_bits(code).items()):
            pwl.append({'case_id': case_id, 'signal': 'PAM bit', 'node': bit, 't_ns': _g(0),
                        'value_V': _g(value), 'role': 'static_dc_level', 'result': 'NOT_RUN'})

    _case_id, platform_ton, gap_ton, edge_ton, tail_ton, _code, _note = R2PLAN.OFFCODE_CASE
    gap, platform, edge, tail = _ns(gap_ton), _ns(platform_ton), _ns(edge_ton), _ns(tail_ton)
    codes = ['011', '100', '000', '111']
    segments = []
    for index, code in enumerate(codes):
        start = lead + index * (platform + gap)
        segments.append(_platform(start, platform, edge, tail, code,
                                  code_change_ns=start - round(gap / 2.0, 9)))
    row = _transient_row('TR-OFFCODE', ','.join(codes), 'pwl_four_platforms', lead, segments,
                         float(segments[-1]['tail_stop_ns']),
                         'both transitions (011->100 and 000->111) land %s ns before their edge, the '
                         'middle of the %s ns off window; the first code is static from t=0'
                         % (_g(round(gap / 2.0, 9)), _g(gap)),
                         'fixed %s' % _g(clamp['main_eval_V']))
    rows.append(row)
    for index, segment in enumerate(segments):
        windows.extend(_window_rows('TR-OFFCODE', index, segment, contract_data, codes[index]))
    pwl.extend(_enable_pwl('TR-OFFCODE', segments, 1.8, lead))
    pwl.extend(_code_pwl('TR-OFFCODE', segments, lead))
    return rows, windows, pwl, dict((r['case_id'], r) for r in rows)


def _transient_row(case_id, code, form, lead, segments, stop_ns, change_rule, clamp_text):
    row = {'case_id': case_id, 'class': 'transient', 'pam_code': code, 'data_en_form': form,
           'data_en_level_V': _g(1.8), 'lead_off_ns': _g(lead), 'offset_applied_ns': _g(lead),
           'off_window_ns': ';'.join('%s-%s' % (segments[i]['tail_stop_ns'],
                                                segments[i + 1]['rise_low_ns'])
                                     for i in range(len(segments) - 1)) or '0-%s' % _g(lead),
           'code_change_rule': change_rule, 'stop_ns': _g(stop_ns),
           'maxstep_ns': _g(R2PLAN.MAXSTEP_WIDE_NS), 'paired_case': '',
           'clamp_sweep_V': clamp_text,
           'analysis_line': 'tran stop=%s maxstep=%s' % (_n(_g(stop_ns)),
                                                         _n(_g(R2PLAN.MAXSTEP_WIDE_NS))),
           'launch_processes_dut': '1', 'launch_processes_preflight': '1', 'result': 'NOT_RUN'}
    for field in ('platform_start_ns', 'platform_stop_ns', 'enable_rise_50_ns', 'enable_fall_50_ns',
                  'window_start_ns', 'window_stop_ns', 'tail_start_ns', 'tail_stop_ns',
                  'leak_last100_start_ns', 'code_change_ns', 'settled_before_enable_ns'):
        _multi(row, segments, field)
    return row


def _window_rows(case_id, index, segment, contract_data, code):
    nominal = _g(contract_data['nominal_current_A_by_code'][code] * 1e6)
    emission = {
        'case_id': case_id, 'window_id': '%s#W%d' % (case_id, index), 'kind': 'emission',
        'start_ns': segment['window_start_ns'], 'stop_ns': segment['window_stop_ns'],
        'length_ns': _g(float(segment['window_stop_ns']) - float(segment['window_start_ns'])),
        'quantity': 'signed Q, Qpos, |Qneg|, flat-part mean current and the 50%%-edge-to-deadline '
                    'settling for code %s (nominal %s uA)' % (code, nominal),
        'measure_together_with': 'Ip_branch, data_out, the local bias nodes of the conducting '
                                 'branches',
        'state_at_start': 'enable 50%% rising at %s ns, code settled at %s ns'
                          % (segment['enable_rise_50_ns'], segment['code_change_ns']),
        'result': 'NOT_RUN'}
    tail = {
        'case_id': case_id, 'window_id': '%s#T%d' % (case_id, index), 'kind': 'off_tail',
        'start_ns': segment['tail_start_ns'], 'stop_ns': segment['tail_stop_ns'],
        'length_ns': _g(float(segment['tail_stop_ns']) - float(segment['tail_start_ns'])),
        'quantity': 'max(abs(I_sink)) over the last %s ns from %s ns, with the signed tail Q beside '
                    'it' % (_g(LEAK_WINDOW_NS), segment['leak_last100_start_ns']),
        'measure_together_with': 'the same tail window turn-off state, never folded into the '
                                 'emission charge',
        'state_at_start': 'enable falling to %s V at %s ns' % (_g(ENABLE_LOW_V),
                                                               segment['enable_fall_50_ns']),
        'result': 'NOT_RUN'}
    return [emission, tail]


def _refined_rows(by_id):
    rows = []
    for case_id, partner in sorted(R2PLAN.PARTNER_CONTRACT.items()):
        base = by_id[partner]
        row = dict((field, base.get(field, '')) for field in SCHEDULE_HEADER)
        row.update({'case_id': case_id, 'class': 'refined_step',
                    'maxstep_ns': _g(R2PLAN.MAXSTEP_FINE_NS), 'paired_case': partner,
                    'analysis_line': base['analysis_line'].replace(
                        'maxstep=%s' % _g(R2PLAN.MAXSTEP_WIDE_NS),
                        'maxstep=%s' % _g(R2PLAN.MAXSTEP_FINE_NS))})
        rows.append(row)
    return rows


def build():
    contract_data = CONTRACT.contract()
    dc_rows, dc_windows, dc_pwl = _dc_rows(contract_data)
    tr_rows, tr_windows, tr_pwl, by_id = _transient_rows(contract_data)
    rows = dc_rows + tr_rows + _refined_rows(by_id)
    windows = dc_windows + tr_windows + _refined_windows(tr_windows, tr_rows)
    return rows, windows, tr_pwl + _refined_pwl(tr_pwl, tr_rows), contract_data


def _refined_windows(base_windows, base_rows):
    """a refined case owns its own window rows: same instants as its partner, its own identity"""
    partner_of = dict(R2PLAN.PARTNER_CONTRACT)
    out = []
    for case_id, partner in sorted(partner_of.items()):
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


def _refined_pwl(base_pwl, base_rows):
    partner_of = dict(R2PLAN.PARTNER_CONTRACT)
    out = []
    for case_id, partner in sorted(partner_of.items()):
        for item in base_pwl:
            if item['case_id'] != partner:
                continue
            clone = dict(item)
            clone['case_id'] = case_id
            clone['role'] = '%s [refined from %s]' % (item['role'], partner)
            out.append(clone)
    return out


def _floats(text):
    return [float(part) for part in str(text).split(';') if part not in ('', DC_NO_TIME)]


def validate(rows, windows, pwl, contract_data):
    """arithmetic over the schedule; every problem names its case and its column"""
    problems = []
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
    lead = float(contract_data['units']['lead_off_ns'])
    for row in rows:
        if row['class'] == 'dc_sweep':
            continue
        if _g(lead) != row['lead_off_ns'] or row['offset_applied_ns'] != row['lead_off_ns']:
            problems.append('%s does not record the uniform %s ns lead it claims to shift by'
                            % (row['case_id'], _g(lead)))
        starts, stops = _floats(row['platform_start_ns']), _floats(row['platform_stop_ns'])
        low, high = _floats(row['window_start_ns']), _floats(row['window_stop_ns'])
        rise50, fall50 = _floats(row['enable_rise_50_ns']), _floats(row['enable_fall_50_ns'])
        tail_s, tail_e = _floats(row['tail_start_ns']), _floats(row['tail_stop_ns'])
        leak = _floats(row['leak_last100_start_ns'])
        if not (len(starts) == len(stops) == len(low) == len(high) == len(rise50) == len(fall50)
                == len(tail_s) == len(tail_e) == len(leak)):
            problems.append('%s gives a different number of platform, window, edge and tail instants'
                            % row['case_id'])
            continue
        for index in range(len(starts)):
            if not (starts[index] < low[index] < high[index] < stops[index]):
                problems.append('%s window %d is not strictly inside its own platform %d..%d'
                                % (row['case_id'], index, starts[index], stops[index]))
            if rise50[index] != starts[index] or fall50[index] != stops[index]:
                problems.append('%s window %d names a 50%% edge that is not its platform boundary'
                                % (row['case_id'], index))
            if tail_s[index] != stops[index] or tail_e[index] <= stops[index]:
                problems.append('%s tail %d does not start at the platform stop and run past it'
                                % (row['case_id'], index))
            if tail_e[index] - leak[index] != LEAK_WINDOW_NS:
                problems.append('%s tail %d does not hold a last-%g ns leakage window'
                                % (row['case_id'], index, LEAK_WINDOW_NS))
            if index and stops[index - 1] >= starts[index]:
                problems.append('%s platforms %d and %d overlap' % (row['case_id'], index - 1, index))
        changes = row['code_change_ns'].split(';')
        if changes != ['static_from_t0']:
            for index, value in enumerate(changes):
                change = float(value)
                previous_stop = 0.0 if index == 0 else stops[index - 1]
                if not (previous_stop < change < starts[index]):
                    problems.append('%s changes code at %s ns, outside the off window %s..%s'
                                    % (row['case_id'], value, _g(previous_stop), _g(starts[index])))
            settle = _floats(row['settled_before_enable_ns'])
            if any(value <= 0 for value in settle):
                problems.append('%s has a code change that does not settle before its rising edge'
                                % row['case_id'])
        if starts[0] - lead < 0:
            problems.append('%s starts before the lead ends, so the initial code never settles'
                            % row['case_id'])
        if float(row['stop_ns']) <= stops[-1]:
            problems.append('%s stops at %s ns, before its last platform ends at %s ns'
                            % (row['case_id'], row['stop_ns'], row['platform_stop_ns']))
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
    for row in rows:
        if (int(row['launch_processes_dut']), int(row['launch_processes_preflight'])) != (1, 1):
            problems.append('%s plans %s DUT and %s preflight processes; each case is one of each'
                            % (row['case_id'], row['launch_processes_dut'],
                               row['launch_processes_preflight']))
    budget = contract_data['launch_budget']
    total_dut = sum(int(r['launch_processes_dut']) for r in rows)
    total_pre = sum(int(r['launch_processes_preflight']) for r in rows)
    if (total_dut, total_pre) != (budget['dut_runs'], budget['preflight_runs']):
        problems.append('the per-case plan adds to %d DUT + %d preflight, the contract proposes %d '
                        '+ %d' % (total_dut, total_pre, budget['dut_runs'],
                                  budget['preflight_runs']))
    for window in windows:
        if window['result'] != 'NOT_RUN':
            problems.append('window %s reports a result instead of NOT_RUN' % window['window_id'])
        if window['kind'] == 'emission' and float(window['length_ns']) <= 0:
            problems.append('emission window %s has no length' % window['window_id'])
    if not any(w['kind'] == 'dc_sweep_point' for w in windows):
        problems.append('no DC sweep window is declared')
    for row in rows:
        if row['class'] == 'dc_sweep':
            expected = 0
        else:
            expected = len(_floats(row['platform_start_ns']))
        emissions = [w for w in windows if w['case_id'] == row['case_id'] and w['kind'] == 'emission']
        tails = [w for w in windows if w['case_id'] == row['case_id'] and w['kind'] == 'off_tail']
        if len(emissions) != expected or len(tails) != expected:
            problems.append('%s declares %d platform(s) but has %d emission and %d tail window rows'
                            % (row['case_id'], expected, len(emissions), len(tails)))
        for index, window in enumerate(sorted(emissions, key=lambda w: w['window_id'])):
            declared_low, declared_high = _floats(row['window_start_ns']), _floats(row['window_stop_ns'])
            if index >= len(declared_low) or index >= len(declared_high):
                problems.append('%s has more emission window rows than the %d windows its row '
                                'declares' % (row['case_id'], len(declared_low)))
                break
            if _g(float(window['start_ns'])) != _g(declared_low[index]) or \
                    _g(float(window['stop_ns'])) != _g(declared_high[index]):
                problems.append('%s window %s does not repeat the instants the schedule row declares'
                                % (row['case_id'], window['window_id']))
    by_case = {}
    for item in pwl:
        by_case.setdefault(item['case_id'], []).append(item)
    for case_id, items in sorted(by_case.items()):
        row = by_id[case_id]
        enables = sorted([i for i in items if i['signal'] == 'DATA_EN'], key=lambda i: float(i['t_ns']))
        if row['class'] != 'dc_sweep':
            if not enables:
                problems.append('%s has no DATA_EN waveform' % case_id)
                continue
            times = [float(i['t_ns']) for i in enables]
            if len(set(times)) != len(times):
                problems.append('%s repeats a DATA_EN time, which is two values at one instant'
                                % case_id)
            if float(enables[0]['value_V']) != ENABLE_LOW_V:
                problems.append('%s starts its enable at %s V, so the first rise is not a real edge'
                                % (case_id, enables[0]['value_V']))
            if any(float(item['t_ns']) > float(row['stop_ns']) for item in items):
                problems.append('%s has a waveform point past its declared stop' % case_id)
            for node in set(i['node'] for i in items):
                series = sorted([i for i in items if i['node'] == node],
                                key=lambda i: float(i['t_ns']))
                times = [float(i['t_ns']) for i in series]
                if len(set(times)) != len(times):
                    problems.append('%s repeats one instant on node %s, which is two values at the '
                                    'same time' % (case_id, node))
                if node in ('pam0', 'pam1', 'pam2') and len(set(times)) != len(series):
                    problems.append('%s drives %s with a repeated step' % (case_id, node))
        else:
            if any(float(item['t_ns']) != 0 for item in items):
                problems.append('%s is a DC case but carries a waveform away from t=0' % case_id)
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
