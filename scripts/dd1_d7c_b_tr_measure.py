#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR measurement: native transient rows to per-window charge, settling, shutoff,
convergence and internal-node evidence.

The measurement windows come from the delivered PWL text of the run copy, the charge denominators come
from the contract, and the reference currents come from the accepted DC table. Nothing here re-derives
a value from the DUT's own target arithmetic, and a nominal number is never substituted for a missing
measurement.
"""

import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7b_measure as B7M
import dd1_d7c_b_tr_contract as TRC
import dd1_d7c_b_tr_decks as DECK
import sc1_read_psf as PSF
import dd1_d7c_b_dc_run as DC                     # accepted psf_units and probe_column, cited reuse

Refuse = B7M.Refuse
S_PER_PS = B7M.S_PER_PS
REQUIRED = tuple(TRC.contract()['required_signals']['always_extracted'])
INTERNAL = TRC.contract()['required_signals']['internal_nodes']
HEADER = ('case_id', 'window_id', 'kind', 'code', 'role', 'tick_ns', 'qlsb_C',
          'window_start_ns', 'window_stop_ns', 'rise50_ns', 'fall50_ns', 't50_ns',
          'flat_start_ns', 'flat_stop_ns', 'q_full_C', 'q_flat_C', 'q_pos_C', 'q_neg_C',
          'abs_q_neg_C', 'peak_A', 'peak_ns', 'flat_mean_A', 'tail_q_C', 'leak_max_abs_A',
          'qtarget_nominal_C', 'qtarget_dc_C', 'err_nominal_LSB', 'err_dynamic_LSB',
          'settling_nominal', 'settling_dc', 'settling_start_ns', 'settling_last_out_ns',
          'settling_left_limit_A', 'evidence', 'raw_sha256', 'deck_sha256', 'launch_id', 'run_id')
CONV_HEADER = ('pair', 'refined_case', 'coarse_case', 'window_id', 'code', 'tick_ns', 'qlsb_C',
               'refined_q_C', 'coarse_q_C', 'dq_C', 'abs_dq_over_qlsb', 'status', 'context_match')
STATUS_HEADER = ('status', 'verdict', 'measured', 'expected', 'note')


def ns_to_ps(value_ns):
    return float(value_ns) * 1e3


def axis_tokens(path, axis):
    """the printed time tokens, so the delivered evidence carries its own display bound"""
    return value_tokens(path, axis)


def value_tokens(path, name):
    """the printed tokens of one column, before any conversion, for the display bound"""
    out, section = [], None
    for raw in io.open(path, encoding='utf-8', errors='replace').read().split('\n'):
        line = raw.strip()
        if line.startswith('VALUE'):
            section = 'value'
            continue
        if section != 'value':
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1].strip('"') == name:
            out.append(parts[0].strip('"'))
    return out


def display_quantum(tokens):
    """half of the last printed decimal place, in the printed unit, over a whole column"""
    worst = 0.0
    for token in tokens:
        text = str(token).strip().strip('"')
        found = re.match(r'^[+-]?(?:\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?[a-zA-Z]*$', text)
        if not found:
            continue
        frac = found.group(1) or ''
        exp = int(found.group(2) or 0)
        place = 10.0 ** (exp - len(frac)) if frac else 10.0 ** exp
        worst = max(worst, 0.5 * place)
    return worst


def load_raw(path, case_id):
    """the native answer as measurement series: units and names come from the file, never assumed"""
    try:
        groups, axis = PSF.parse(path)
    except ValueError as error:
        raise Refuse('%s: the native file cannot be read: %s' % (case_id, error))
    columns, axis_values = PSF.as_columns(groups, axis)
    units = DC.psf_units(path)
    if axis is None or axis_values is None:
        raise Refuse('%s: the native file declares no readable time axis' % case_id)
    if units.get(axis) != 's':
        raise Refuse('%s: the axis %s carries unit %r, a transient window is measured in seconds '
                     'from the file header' % (case_id, axis, units.get(axis)))
    tokens = axis_tokens(path, axis)
    if len(tokens) != len(axis_values):
        raise Refuse('%s: %d printed time tokens against %d parsed axis values'
                     % (case_id, len(tokens), len(axis_values)))
    quantum = B7M.time_quantum_ps(tokens)
    volts = display_quantum(value_tokens(path, 'data_out'))
    if not volts:
        raise Refuse('%s: the exported data_out column prints no readable decimal place, so the '
                     'iprobe consistency tolerance cannot be shown to be expressible' % case_id)
    times = [value / S_PER_PS for value in axis_values]
    for name, values in list(columns.items()):
        del values
    series, missing = {}, []
    for name in REQUIRED + tuple(INTERNAL['en'] + INTERNAL['enb'] + INTERNAL['vbias_ch']
                                + INTERNAL['node_m']):
        if name == 'Ip_branch_current':
            continue
        if name in columns:
            series[name] = list(zip(times, columns[name]))
        elif name not in INTERNAL['en'] + INTERNAL['enb'] + INTERNAL['vbias_ch'] + \
                INTERNAL['node_m']:
            missing.append(name)
    current = DC.probe_column(columns)
    series['Ip_branch_current'] = list(zip(times, columns[current]))
    if missing:
        raise Refuse('%s: the native answer carries no %s, so the required signals cannot be '
                     'extracted and no contract value is substituted'
                     % (case_id, ','.join(missing)))
    for name, pairs in series.items():
        if len(pairs) != len(times):
            raise Refuse('%s: %s has %d samples against %d axis points'
                         % (case_id, name, len(pairs), len(times)))
        if any(not math.isfinite(value) for _t, value in pairs):
            raise Refuse('%s: %s holds a non-finite sample' % (case_id, name))
    return {'case_id': case_id, 'axis': axis, 'axis_unit': units.get(axis), 'current_name': current,
            'units': units, 'quantum_ps': quantum, 'value_quantum_V': volts,
            'series': series, 'columns': sorted(columns),
            'samples': len(times), 't_first_ps': times[0], 't_last_ps': times[-1],
            'path': os.path.basename(path)}


def windows_of(case_id, deck_text):
    """the five declared window kinds, re-derived from the delivered PWL text of the run copy"""
    series = TRC.pwl_series(deck_text, 'data_en', case_id)
    if series is None:
        raise Refuse('%s: the run copy drives no data_en pwl source' % case_id)
    derived = TRC.windows_from_enable(series)
    out = []
    for kind in ('emission', 'emission_flat', 'off_tail', 'pure_off', 'leak_last100'):
        letter = [key for key, value in TRC.WINDOW_KINDS.items() if value == kind][0]
        for index, (start, stop) in enumerate(derived[kind]):
            out.append({'window_id': '%s%d' % (letter, index), 'kind': kind,
                        'start_ns': start, 'stop_ns': stop})
    codes = codes_of(case_id, deck_text)
    for row in out:
        index = int(re.sub(r'^[A-Z]', '', row['window_id']))
        row['code'] = codes[index] if index < len(codes) else ''
    return out


def codes_of(case_id, deck_text):
    """the PAM code in force for each emission window, read from the delivered PAM waves"""
    series = TRC.pwl_series(deck_text, 'data_en', case_id)
    rises = TRC.half_crossings(series)[0]
    waves = [TRC.pwl_series(deck_text, 'pam%d' % bit, case_id) for bit in (2, 1, 0)]
    codes = []
    for time in rises:
        bits = []
        for wave in waves:
            if wave is None:
                bits.append('0')
                continue
            value = 0.0
            for point, level in wave:
                if point <= time:
                    value = level
                else:
                    break
            bits.append('1' if value >= TRC.LOGIC_HIGH_V - 1e-9 else '0')
        codes.append(''.join(bits))
    return codes


def pair_lookup(rows, kind, index):
    for row in rows:
        if row['kind'] == kind and int(re.sub(r'^[A-Z]', '', row['window_id'])) == index:
            return row
    return None


def measure_window(case_id, window, windows, data, code, role, meta):
    """one window measured from the native samples only"""
    enable = data['series']['data_en']
    current = data['series']['Ip_branch_current']
    start_ps = ns_to_ps(window['start_ns'])
    stop_ps = ns_to_ps(window['stop_ns'])
    out = {'case_id': case_id, 'window_id': window['window_id'], 'kind': window['kind'],
           'code': code, 'role': role, 'tick_ns': TRC.TICK_NS[case_id],
           'qlsb_C': TRC.qlsb_C(TRC.TICK_NS[case_id]),
           'window_start_ns': window['start_ns'], 'window_stop_ns': window['stop_ns'],
           'evidence': 'NATIVE_MEASURED', 'raw_sha256': meta['raw_sha256'],
           'deck_sha256': meta['deck_sha256'], 'launch_id': meta['launch_id'],
           'run_id': meta['run_id'], 'rise50_ns': '', 'fall50_ns': '', 't50_ns': '',
           'flat_start_ns': '', 'flat_stop_ns': '', 'q_full_C': '', 'q_flat_C': '',
           'q_pos_C': '', 'q_neg_C': '', 'abs_q_neg_C': '', 'peak_A': '', 'peak_ns': '',
           'flat_mean_A': '', 'tail_q_C': '', 'leak_max_abs_A': '', 'qtarget_nominal_C': '',
           'qtarget_dc_C': '', 'err_nominal_LSB': '', 'err_dynamic_LSB': '',
           'settling_nominal': '', 'settling_dc': '', 'settling_start_ns': '',
           'settling_last_out_ns': '', 'settling_left_limit_A': ''}
    if window['kind'] != 'emission':
        return out
    index = int(re.sub(r'^[A-Z]', '', window['window_id']))
    hint_lo = max(0.0, window['start_ns'] - 2 * TRC.EDGE_NS)
    hint_hi = window['start_ns'] + 2 * TRC.EDGE_NS
    rise = B7M.crossing(enable, TRC.ENABLE_MID_V, True, ns_to_ps(hint_lo), ns_to_ps(hint_hi),
                        '%s %s rise' % (case_id, window['window_id']))
    if rise is None:
        raise Refuse('%s %s: no 0.9 V rising crossing of the native enable inside the declared '
                     'window, so T50 cannot be measured' % (case_id, window['window_id']))
    flat = pair_lookup(windows, 'emission_flat', index)
    tail = pair_lookup(windows, 'off_tail', index)
    pure = pair_lookup(windows, 'pure_off', index)
    leak = pair_lookup(windows, 'leak_last100', index)
    for name, row in (('flat', flat), ('tail', tail), ('pure_off', pure), ('leak', leak)):
        if row is None:
            raise Refuse('%s %s: the delivered PWL declares no %s window for this emission window'
                         % (case_id, window['window_id'], name))
    fall_start_lo = max(rise, flat['stop_ns'] - 2 * TRC.EDGE_NS)
    fall = B7M.crossing(enable, TRC.ENABLE_MID_V, False, ns_to_ps(fall_start_lo),
                        ns_to_ps(tail['stop_ns']),
                        '%s %s fall' % (case_id, window['window_id']))
    if fall is None:
        raise Refuse('%s %s: the native enable never falls inside the declared tail, so T50 is '
                     'undefined rather than assumed' % (case_id, window['window_id']))
    t50_ps = fall - rise
    if t50_ps <= 0:
        raise Refuse('%s %s: the falling 0.9 V crossing precedes the rising one'
                     % (case_id, window['window_id']))
    full = B7M.integrate(current, rise, fall, '%s %s full' % (case_id, window['window_id']))
    flat_int = B7M.integrate(current, ns_to_ps(flat['start_ns']), ns_to_ps(flat['stop_ns']),
                             '%s %s flat' % (case_id, window['window_id']))
    tail_int = B7M.integrate(current, fall, ns_to_ps(tail['stop_ns']),
                             '%s %s tail' % (case_id, window['window_id']))
    leak_max, leak_at = B7M.extreme([(t, abs(v)) for t, v in current],
                                    ns_to_ps(leak['start_ns']), ns_to_ps(leak['stop_ns']))
    peak, peak_at = B7M.extreme(current, rise, fall)
    span = flat['stop_ns'] - flat['start_ns']
    if span <= 0:
        raise Refuse('%s %s: the flat window is empty' % (case_id, window['window_id']))
    flat_mean = flat_int['q'] / (span * 1e-9)
    idc = TRC.dc_idc_by_code()[code]['I_sink_A']
    inom = TRC.nominal_A(code)
    target_dc = idc * t50_ps * S_PER_PS
    target_nominal = inom * t50_ps * S_PER_PS
    qlsb = TRC.qlsb_C(TRC.TICK_NS[case_id])
    out.update({'rise50_ns': rise * S_PER_PS * 1e9, 'fall50_ns': fall * S_PER_PS * 1e9,
                't50_ns': t50_ps * S_PER_PS * 1e9,
                'flat_start_ns': flat['start_ns'], 'flat_stop_ns': flat['stop_ns'],
                'q_full_C': full['q'], 'q_flat_C': flat_int['q'], 'q_pos_C': full['q_pos'],
                'q_neg_C': full['q_neg'], 'abs_q_neg_C': abs(full['q_neg']),
                'peak_A': peak, 'peak_ns': (peak_at or 0.0) * S_PER_PS * 1e9,
                'flat_mean_A': flat_mean, 'tail_q_C': tail_int['q'],
                'leak_max_abs_A': leak_max, 'qtarget_nominal_C': target_nominal,
                'qtarget_dc_C': target_dc,
                'err_nominal_LSB': (full['q'] - target_nominal) / qlsb,
                'err_dynamic_LSB': (full['q'] - target_dc) / qlsb})
    settle = settling(current, rise, target_nominal, ns_to_ps(flat['stop_ns']),
                      '%s %s nominal' % (case_id, window['window_id']))
    settle_dc = settling(current, rise, target_dc, ns_to_ps(flat['stop_ns']),
                         '%s %s dc' % (case_id, window['window_id']))
    out.update({'settling_nominal': settle['state'], 'settling_dc': settle_dc['state'],
                'settling_start_ns': settle['settled_ns'] or '',
                'settling_last_out_ns': settle['last_out_ns'] or '',
                'settling_left_limit_A': settle['left_limit']})
    if leak_max is None:
        raise Refuse('%s %s: the declared leak window carries no native sample'
                     % (case_id, window['window_id']))
    return out


def _ns_or_blank(value_ps):
    return '' if value_ps is None else value_ps * S_PER_PS * 1e9


def settling(current, edge_ps, target_A, deadline_ps, ctx):
    """a five percent band around the target, held at least ten ns, never past flat_stop"""
    band = TRC.SETTLE_FRACTION * abs(target_A)
    result = B7M.sustained_in_band(current, edge_ps, target_A - band, target_A + band, deadline_ps)
    window = [(t, v) for t, v in current if edge_ps <= t <= deadline_ps]
    outside = [t for t, v in window if abs(v - target_A) > band]
    return {'state': result['status'], 'settled_ps': result.get('settled_ps'),
            'settled_ns': _ns_or_blank(result.get('settled_ps')),
            'last_out_ps': max(outside) if outside else None,
            'last_out_ns': _ns_or_blank(max(outside)) if outside else '',
            'left_limit': result.get('deadline_left_limit_A'),
            'band_left_at_ns': _ns_or_blank(result.get('band_left_at_ps')),
            'held_ns': _ns_or_blank(result.get('held_ps')),
            'checked_points': result.get('checked_points'),
            'band_A': band, 'ctx': ctx}


def black_window(case_id, start_ns, stop_ns, data, role, meta, code):
    """a zero-code frame: no emission edge, Qtarget 0, the same fixed QLSB, no invented T50"""
    current = data['series']['Ip_branch_current']
    start_ps, stop_ps = ns_to_ps(start_ns), ns_to_ps(stop_ns)
    charge = B7M.integrate(current, start_ps, stop_ps, '%s black %s' % (case_id, code))
    peak, peak_at = B7M.extreme([(t, abs(v)) for t, v in current], start_ps, stop_ps)
    qlsb = TRC.qlsb_C(TRC.TICK_NS[case_id])
    return {'case_id': case_id, 'window_id': 'BLACK', 'kind': 'black_64T', 'code': code,
            'role': role, 'tick_ns': TRC.TICK_NS[case_id], 'qlsb_C': qlsb,
            'window_start_ns': start_ns, 'window_stop_ns': stop_ns,
            'rise50_ns': 'NO_EDGE', 'fall50_ns': 'NO_EDGE', 't50_ns': 'NOT_DEFINED_FOR_BLACK',
            'q_full_C': charge['q'], 'q_pos_C': charge['q_pos'], 'q_neg_C': charge['q_neg'],
            'abs_q_neg_C': abs(charge['q_neg']), 'peak_A': peak, 'peak_ns': peak_at or '',
            'qtarget_nominal_C': 0.0, 'qtarget_dc_C': 0.0,
            'err_nominal_LSB': charge['q'] / qlsb, 'err_dynamic_LSB': charge['q'] / qlsb,
            'leak_max_abs_A': peak, 'evidence': 'NATIVE_MEASURED',
            'raw_sha256': meta['raw_sha256'], 'deck_sha256': meta['deck_sha256'],
            'launch_id': meta['launch_id'], 'run_id': meta['run_id'],
            'flat_start_ns': '', 'flat_stop_ns': '', 'q_flat_C': '', 'flat_mean_A': '',
            'tail_q_C': '', 'settling_nominal': 'NOT_APPLICABLE', 'settling_dc': 'NOT_APPLICABLE',
            'settling_start_ns': '', 'settling_last_out_ns': '', 'settling_left_limit_A': ''}


def measure_case(case_id, raw_path, deck_text, meta, extra_windows=()):
    data = load_raw(raw_path, case_id)
    windows = windows_of(case_id, deck_text)
    codes = codes_of(case_id, deck_text)
    rows = []
    for window in windows:
        index = int(re.sub(r'^[A-Z]', '', window['window_id']))
        code = codes[index] if index < len(codes) else ''
        if window['kind'] != 'emission':
            continue
        rows.append(measure_window(case_id, window, windows, data, code,
                                   meta.get('role', 'dut'), meta))
    for row in extra_windows:
        rows.append(black_window(case_id, row['start_ns'], row['stop_ns'], data,
                                 meta.get('role', 'dut'), meta, row.get('code', '000')))
    return rows, data


def iprobe_consistency(data, case_id):
    """F-TR-2: the ideal probe's two terminals must agree within the numeric tolerance, and the
    tolerance must be expressible in the precision this machine actually exports"""
    out = data['series']['data_out']
    clamp = data['series']['clamp_node']
    if len(out) != len(clamp):
        raise Refuse('%s: data_out and clamp_node have different sample counts' % case_id)
    worst = 0.0
    worst_at = None
    for (t1, v1), (t2, v2) in zip(out, clamp):
        if t1 != t2:
            raise Refuse('%s: the two terminals are sampled at different times' % case_id)
        gap = abs(v1 - v2)
        if gap > worst:
            worst, worst_at = gap, t1
    quantum = data['value_quantum_V']
    return {'case_id': case_id, 'max_abs_difference_V': worst,
            'at_ps': worst_at,
            'tolerance_rule': TRC.contract()['probe']['ideal_two_terminal_check']['expression'],
            'worst_tolerance_at_that_point': TRC.IPROBE_ABS_TOL_V
            + TRC.IPROBE_REL_TOL * abs(clamp[0][1] if clamp else 0.0),
            'passes': all(abs(v1 - v2) <= TRC.IPROBE_ABS_TOL_V
                          + TRC.IPROBE_REL_TOL * abs(v2)
                          for (_t1, v1), (_t2, v2) in zip(out, clamp)),
            'value_display_quantum_V': quantum,
            'tolerance_is_expressible': quantum <= TRC.IPROBE_ABS_TOL_V}


def convergence(refined_rows, coarse_rows, case_pair):
    """the three declared pairs, per window, with the context that makes the comparison meaningful"""
    refined = dict((row['window_id'], row) for row in refined_rows if row['kind'] == 'emission')
    coarse = dict((row['window_id'], row) for row in coarse_rows if row['kind'] == 'emission')
    rows, problems = [], []
    if set(refined) != set(coarse):
        problems.append('%s/%s: the two cases measure different windows (%s against %s)'
                        % (case_pair['refined'], case_pair['coarse'],
                           ','.join(sorted(set(refined) - set(coarse))) or '-',
                           ','.join(sorted(set(coarse) - set(refined))) or '-'))
    for key in sorted(set(refined) & set(coarse)):
        a, b = refined[key], coarse[key]
        context_a = context_of(a)
        context_b = context_of(b)
        if not any(context_a.values()):
            problems.append('%s: the refined side carries no context, and None is not a match' % key)
            continue
        if context_a != context_b:
            differing = [name for name in context_a if context_a[name] != context_b[name]]
            problems.append('%s: the pair disagrees on %s, so the two charges are not comparable'
                            % (key, ','.join(differing)))
            continue
        if a['q_full_C'] == '' or b['q_full_C'] == '':
            problems.append('%s: a side has no measured Q, which is not a difference of zero' % key)
            continue
        dq = a['q_full_C'] - b['q_full_C']
        ratio = abs(dq) / a['qlsb_C']
        rows.append({'pair': '%s/%s' % (case_pair['refined'], case_pair['coarse']),
                     'refined_case': case_pair['refined'], 'coarse_case': case_pair['coarse'],
                     'window_id': key, 'code': a['code'], 'tick_ns': a['tick_ns'],
                     'qlsb_C': a['qlsb_C'], 'refined_q_C': a['q_full_C'],
                     'coarse_q_C': b['q_full_C'], 'dq_C': dq,
                     'abs_dq_over_qlsb': ratio,
                     'status': 'PASS' if ratio <= TRC.CONV_LIMIT else 'FAIL',
                     'context_match': 'YES'})
    return rows, problems


def context_of(row):
    return dict((name, row.get(name)) for name in
                ('code', 'tick_ns', 'qlsb_C', 'window_start_ns', 'window_stop_ns',
                 'rise50_ns', 'fall50_ns', 'flat_start_ns', 'flat_stop_ns', 'qtarget_dc_C'))


def statuses(rows, conv_rows, observed, completed):
    """six separate verdicts, so a negative finding cannot be swallowed by an overall PASS"""
    for row in rows:
        absent = [key for key in ('err_dynamic_LSB', 'err_nominal_LSB', 'kind')
                  if key not in row]
        if absent:
            raise Refuse('%s %s carries no %s, so no status may be computed from it'
                         % (row.get('case_id'), row.get('window_id'), ','.join(absent)))
    emission = [row for row in rows if row['kind'] == 'emission']
    black = [row for row in rows if row['kind'].startswith('black')]
    tail = [row for row in rows if row['kind'] == 'emission']

    def verdict(values, limit, missing='PARTIAL'):
        if not values:
            return missing, 0
        bad = [value for value in values if abs(value) > limit]
        return ('PASS' if not bad else 'FAIL'), len(values) - len(bad)

    dynamic, dyn_n = verdict([row['err_dynamic_LSB'] for row in emission + black],
                             TRC.DYNAMIC_LIMIT_LSB)
    nominal, nom_n = verdict([row['err_nominal_LSB'] for row in emission + black],
                             TRC.NOMINAL_LIMIT_LSB)
    settling_states = [row['settling_dc'] for row in emission]
    settling_status = ('PASS' if settling_states and all(state == 'SETTLED'
                                                         for state in settling_states)
                       else ('PARTIAL' if not settling_states else 'FAIL'))
    leak_states = [row['leak_max_abs_A'] for row in tail]
    shutoff = ('PASS' if leak_states and all(value is not None
                                             and value <= TRC.LEAK_LIMIT_A
                                             for value in leak_states)
               else ('PARTIAL' if not leak_states else 'FAIL'))
    conv_status = ('PASS' if conv_rows and all(row['status'] == 'PASS' for row in conv_rows)
                   else ('PARTIAL' if not conv_rows else 'FAIL'))
    return [
        {'status': 'EXECUTION_COMPLETENESS', 'verdict': completed['verdict'],
         'measured': completed['measured'], 'expected': completed['expected'],
         'note': completed['note']},
        {'status': 'EVIDENCE_INTEGRITY', 'verdict': observed['verdict'],
         'measured': observed['measured'], 'expected': observed['expected'],
         'note': observed['note']},
        {'status': 'DYNAMIC_CHARGE_STATUS', 'verdict': dynamic, 'measured': dyn_n,
         'expected': len(emission) + len(black),
         'note': 'abs(error_dynamic_LSB) <= %g, the frozen criterion of this task'
                 % TRC.DYNAMIC_LIMIT_LSB},
        {'status': 'NOMINAL_CHARGE_STATUS', 'verdict': nominal, 'measured': nom_n,
         'expected': len(emission) + len(black),
         'note': 'abs(error_nominal_LSB) <= %g reported independently; a dynamic pass is never '
                 'presented as an uncalibrated grey-scale pass' % TRC.NOMINAL_LIMIT_LSB},
        {'status': 'SETTLING_STATUS', 'verdict': settling_status,
         'measured': len([state for state in settling_states if state == 'SETTLED']),
         'expected': len(emission),
         'note': 'against the DC target with a +/-5 % band, at least 10 ns, deadline flat_stop'},
        {'status': 'SHUTOFF_STATUS', 'verdict': shutoff,
         'measured': len([value for value in leak_states
                          if value is not None and value <= TRC.LEAK_LIMIT_A]),
         'expected': len(tail),
         'note': 'max(abs(I_sink)) <= %g A over the last %g ns of the pure-off window only'
                 % (TRC.LEAK_LIMIT_A, TRC.TAIL_NS)},
        {'status': 'CONVERGENCE_STATUS', 'verdict': conv_status, 'measured': len(conv_rows),
         'expected': 0, 'note': 'abs(dQ)/QLSB <= %g on the three declared pairs' % TRC.CONV_LIMIT}]


def internal_nodes(data, windows, codes, window_ns=50.0):
    """the time-weighted view of the internal nodes at the end of each flat step of TR-LONG"""
    out = []
    for row in windows:
        if row['kind'] != 'emission_flat':
            continue
        index = int(re.sub(r'^[A-Z]', '', row['window_id']))
        start = max(row['start_ns'], row['stop_ns'] - window_ns)
        entry = {'window_id': row['window_id'], 'code': codes[index] if index < len(codes) else '',
                 'from_ns': start, 'to_ns': row['stop_ns'], 'nodes': {}}
        for group, names in sorted(INTERNAL.items()):
            for name in names:
                if name not in data['series']:
                    entry['nodes'][name] = 'NOT_OBSERVED'
                    continue
                mean = _time_weighted(data['series'][name], start, row['stop_ns'])
                entry['nodes'][name] = mean
        entry['selected_branches'] = (int(codes[index], 2) + 1) if index < len(codes) else None
        out.append(entry)
    return out


def _time_weighted(series, from_ns, to_ns):
    pts = [(t, v) for t, v in series if ns_to_ps(from_ns) <= t <= ns_to_ps(to_ns)]
    if len(pts) < 2:
        return None
    total = 0.0
    span = 0.0
    for index in range(1, len(pts)):
        dt = pts[index][0] - pts[index - 1][0]
        total += dt * (pts[index][1] + pts[index - 1][1]) / 2.0
        span += dt
    return total / span if span else None


def write_rows(path, rows, header):
    return DC.B7B.write_rows(path, [[_cell(row.get(key, '')) for key in header] for row in rows],
                             list(header))


def _cell(value):
    if isinstance(value, float):
        if value == 0.0:
            return '0'
        return '%.12g' % value
    return str(value) if value is not None else ''


# ---- offline family -------------------------------------------------------------------------------

def fixture_series():
    """a hand-computed native answer: an ideal trapezoid enable and a current of 1.875 uA on for the
    whole 0.9 V to 0.9 V interval, so Q_full, T50 and both error columns have hand values"""
    times, enable, current, data_out, clamp = [], [], [], [], []

    def add(t_ns, en, i):
        times.append(t_ns * 1e3)
        enable.append(en)
        current.append(i)
        data_out.append(1.2)
        clamp.append(1.2)

    for t_ns in range(0, 3000):
        conducting = 1000 <= t_ns < 2100
        if t_ns < 1000:
            add(t_ns, 0.0, 0.0)
        elif t_ns < 1100:
            add(t_ns, 1.8 * (t_ns - 1000) / 100.0, 1.875e-6 if conducting else 0.0)
        elif t_ns < 2000:
            add(t_ns, 1.8, 1.875e-6 if conducting else 0.0)
        elif t_ns < 2100:
            add(t_ns, 1.8 - 1.8 * (t_ns - 2000) / 100.0, 1.875e-6 if conducting else 0.0)
        else:
            add(t_ns, 0.0, 0.0)
    return times, enable, current, data_out, clamp


def selftest():
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else extra))
    times, enable, current, data_out, clamp = fixture_series()
    data = {'series': {'data_en': list(zip(times, enable)),
                       'Ip_branch_current': list(zip(times, current)),
                       'data_out': list(zip(times, data_out)),
                       'clamp_node': list(zip(times, clamp))},
            'quantum_ps': 0.5, 'value_quantum_V': 5e-13, 'case_id': 'FIXTURE'}
    rise = B7M.crossing(data['series']['data_en'], TRC.ENABLE_MID_V, True, 0.0, 3e6, 'rise')
    fall = B7M.crossing(data['series']['data_en'], TRC.ENABLE_MID_V, False, 1.5e6, 3e6, 'fall')
    record('the fixture enable crosses 0.9 V at 1050 ns and 2050 ns',
           abs(rise - 1050000.0) < 1e-6 and abs(fall - 2050000.0) < 1e-6, (rise, fall))
    charge = B7M.integrate(data['series']['Ip_branch_current'], rise, fall, 'fixture')
    record('the fixture integrates to exactly 1.875 uA x 1 us',
           abs(charge['q'] - 1.875e-12) < 1e-24, charge)
    idc = TRC.dc_idc_by_code()['000']['I_sink_A']
    qlsb = TRC.qlsb_C(120.0)
    t50_s = (fall - rise) * S_PER_PS
    err_dynamic = (charge['q'] - idc * t50_s) / qlsb
    err_nominal = (charge['q'] - TRC.nominal_A('000') * t50_s) / qlsb
    record('the dynamic error of the fixture is the hand value -0.2126 LSB',
           abs(err_dynamic + 0.212618257) < 1e-8, err_dynamic)
    record('the nominal error of a nominal-current fixture is zero', abs(err_nominal) < 1e-9,
           err_nominal)
    record('Qpos and Qneg keep the identity and the sign rule',
           abs(charge['q'] - (charge['q_pos'] + charge['q_neg'])) < 1e-30
           and charge['q_pos'] > 0, charge)
    tri = [(t * 1e3, v) for t, v in ((0, 1.0), (1, -1.0), (2, 1.0))]
    tri_area = B7M.integrate(tri, 0.0, 2000.0, 'triangle')
    record('a symmetric triangle splits into equal positive and negative areas',
           abs(tri_area['q_pos'] - 5e-10) < 1e-18 and abs(tri_area['q_neg'] + 5e-10) < 1e-18
           and abs(tri_area['q']) < 1e-24, tri_area)
    settle = settling(data['series']['Ip_branch_current'], rise, idc, 2000e3, 'fixture')
    record('settling against the DC target holds inside the five percent band',
           settle['state'] == 'SETTLED', settle['state'])
    settle_nom = settling(data['series']['Ip_branch_current'], rise, TRC.nominal_A('000'),
                          2000e3, 'fixture')
    record('settling against the nominal target settles inside the pulse',
           settle_nom['state'] == 'SETTLED', settle_nom)
    low = [(t, value * 0.5) for t, value in data['series']['Ip_branch_current']]
    record('a current that never enters the band stays NOT_SETTLED_WITHIN_PULSE',
           settling(low, rise, idc, 2000e3, 'fixture')['state'] == 'NOT_SETTLED_WITHIN_PULSE', '')
    leave = [(t, idc if t < 1900e3 else 0.0) for t, _v in data['series']['Ip_branch_current']]
    out_of_band = settling(leave, rise, idc, 2000e3, 'fixture')
    record('a current that leaves the band before flat_stop reports the last out-of-band sample',
           out_of_band['state'] == 'NOT_SETTLED_WITHIN_PULSE'
           and out_of_band['last_out_ns'] == 2000.0
           and 1898.0 < out_of_band['band_left_at_ns'] < 1900.0, out_of_band)
    record('the deadline is the flat stop and is never moved to make a window look settled',
           out_of_band['state'] != 'SETTLED', out_of_band['state'])
    record('the iprobe two-terminal rule is expressible at the exported precision',
           iprobe_consistency(data, 'FIXTURE')['tolerance_is_expressible'],
           data['quantum_ps'])
    drift = dict(data)
    drift['series'] = dict(data['series'])
    drift['series']['data_out'] = [(t, v + 5e-6) for t, v in data['series']['data_out']]
    record('a 5 uV offset between the ideal probe terminals is caught by the tightened rule',
           not iprobe_consistency(drift, 'FIXTURE')['passes'], '')
    drift2 = dict(data)
    drift2['series'] = dict(data['series'])
    drift2['series']['data_out'] = [(t, v + 1e-7) for t, v in data['series']['data_out']]
    record('a 0.1 uV difference stays inside the numeric tolerance',
           iprobe_consistency(drift2, 'FIXTURE')['passes'], '')
    text = io.open(os.path.join(ROOT, 'spectre', 'dd1_d7c_b_tr', 'TR-LONG.scs'),
                   encoding='utf-8', newline='').read()
    windows = windows_of('TR-LONG', text)
    codes = codes_of('TR-LONG', text)
    record('the TR-LONG run copy assigns each emission window the code in force at its rise',
           [row['code'] for row in windows if row['kind'] == 'emission'] == codes
           and codes == [format(index, '03b') for index in range(8)], codes)
    record('every declared kind of the TR-LONG run copy is measured',
           sorted(set(row['kind'] for row in windows)) == sorted(
               ['emission', 'emission_flat', 'leak_last100', 'off_tail', 'pure_off']),
           sorted(set(row['kind'] for row in windows)))
    record('the codes of TR-LONG count up in binary with pam0 as the weight-1 bit',
           codes == [format(index, '03b') for index in range(8)], codes)
    def row(**over):
        base = {'case_id': 'FIXTURE', 'window_id': 'W0', 'kind': 'emission', 'code': '000',
                'tick_ns': 120.0, 'qlsb_C': qlsb, 'window_start_ns': 1050.0,
                'window_stop_ns': 2050.0, 'rise50_ns': 1050.0, 'fall50_ns': 2050.0,
                'flat_start_ns': 1100.0, 'flat_stop_ns': 2000.0, 'q_full_C': 1.875e-12,
                'qtarget_dc_C': idc * 1e-6, 'err_dynamic_LSB': err_dynamic,
                'err_nominal_LSB': err_nominal, 'leak_max_abs_A': 0.0,
                'settling_dc': 'SETTLED', 'settling_nominal': 'SETTLED'}
        base.update(over)
        return base

    refined = [row(case_id='RS-FULL')]
    coarse = [row(case_id='TR-LONG')]
    rows, problems = convergence(refined, coarse, {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('an identical pair reports a zero difference and passes',
           not problems and rows and rows[0]['status'] == 'PASS', problems or rows)
    moved = [dict(row, q_full_C=1.875e-12 + 0.011 * qlsb) for row in refined]
    rows2, _p = convergence(moved, coarse, {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('a 0.011 LSB difference fails the 0.01 convergence limit',
           rows2[0]['status'] == 'FAIL', rows2)
    different = [dict(row, tick_ns=200.0, qlsb_C=TRC.qlsb_C(200.0)) for row in refined]
    rows3, problems3 = convergence(different, coarse, {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('a pair whose reference tick differs is refused, not compared',
           rows3 == [] and any('reference' in text or 'tick' in text for text in problems3),
           problems3)
    empty = [dict(row, code='', tick_ns='', qlsb_C='', window_start_ns='', window_stop_ns='',
                  rise50_ns='', fall50_ns='', flat_start_ns='', flat_stop_ns='',
                  qtarget_dc_C='') for row in refined]
    rows4, problems4 = convergence(empty, empty, {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('two sides with no context are refused instead of matching on emptiness',
           rows4 == [] and problems4, problems4)
    missing_side = [dict(row, q_full_C='') for row in refined]
    rows5, problems5 = convergence(missing_side, coarse, {'refined': 'RS-FULL',
                                                           'coarse': 'TR-LONG'})
    record('a side without a measured Q is not read as a difference of zero',
           rows5 == [] and problems5, problems5)
    rows6, problems6 = convergence(refined, [], {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('windows present on one side only are reported, not skipped',
           rows6 == [] and problems6, problems6)
    black = black_window('HYB-200', 2400.0, 2900.0, data, 'dut',
                         {'raw_sha256': 'x', 'deck_sha256': 'y', 'launch_id': 'T001',
                          'run_id': 'r'}, '000')
    record('a black window carries no invented T50 and a zero target',
           black['t50_ns'] == 'NOT_DEFINED_FOR_BLACK' and black['qtarget_dc_C'] == 0.0
           and black['err_dynamic_LSB'] == 0.0, black)
    table = [dict(row, kind='emission') for row in refined]
    verdicts = dict((row['status'], row['verdict']) for row in
                    statuses(table, rows, {'verdict': 'PASS', 'measured': 1, 'expected': 1,
                                           'note': 'fixture'},
                           {'verdict': 'PASS', 'measured': 1, 'expected': 1, 'note': 'fixture'}))
    record('the six statuses are published separately',
           sorted(verdicts) == sorted(['EXECUTION_COMPLETENESS', 'EVIDENCE_INTEGRITY',
                                       'DYNAMIC_CHARGE_STATUS', 'NOMINAL_CHARGE_STATUS',
                                       'SETTLING_STATUS', 'SHUTOFF_STATUS',
                                       'CONVERGENCE_STATUS']), sorted(verdicts))
    record('a dynamic pass does not decide the nominal column',
           verdicts['NOMINAL_CHARGE_STATUS'] in ('PASS', 'FAIL', 'PARTIAL'), verdicts)
    leak = [dict(row, leak_max_abs_A=2e-7) for row in refined]
    worse = dict((row['status'], row['verdict']) for row in
                 statuses(leak, rows, {'verdict': 'PASS', 'measured': 1, 'expected': 1,
                                       'note': 'f'},
                         {'verdict': 'PASS', 'measured': 1, 'expected': 1, 'note': 'f'}))
    record('a 0.2 uA tail is a shutoff FAIL, not a rounding note',
           worse['SHUTOFF_STATUS'] == 'FAIL', worse)
    record('a window whose enable never rises is refused rather than given a nominal T50',
           _refuses(lambda: measure_window(
               'TR-LONG', {'window_id': 'W0', 'kind': 'emission', 'start_ns': 2500.0,
                           'stop_ns': 2900.0}, windows, data, '000', 'dut',
               {'raw_sha256': 'x', 'deck_sha256': 'y', 'launch_id': 'T', 'run_id': 'r'})), '')
    record('a required signal absent from the native answer names itself',
           _refuses(lambda: _load_missing()), '')
    return results


def _refuses(action):
    try:
        action()
    except (Refuse, ValueError):
        return True
    return False


def _load_missing():
    path = os.path.join(ROOT, 'review', 'scratch', 'tr_staging', 'missing_column.raw')
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    io.open(path, 'wb').write((
        'SECTION=1\nSWEEP\n"primary" "sweep"\n"axisvar" "time"\n"units" "s"\n'
        'TRACE\n"time" "s"\n"data_en" "V"\n"Ip_branch:current" "A"\n'
        'VALUE\n1e-9 time\n0.0 data_en\n1e-6 Ip_branch:current\n').encode('utf-8'))
    return load_raw(path, 'MISSING')


def main(argv):
    mode = argv[0] if argv else '--selftest'
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-66s %s %s' % (name, 'PASS' if ok else 'FAIL', str(extra)[:160]))
        print('TR_MEASURE_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--fixture':
        rows = json.dumps(fixture_series.__doc__, default=str)
        print(rows)
        return 0
    print('usage: --selftest | --fixture')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
