#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_cases.py -- hand-computed synthetic samples that prove the measurement rules bite.

DATA-7C-B-PREP section 7. Every number below is written by hand and the expected result is a literal,
not something the code under test produced, so a pass means the arithmetic agrees with a pencil and a
fail names which of the two moved. Nothing here is measured: the module is labelled
`SYNTHETIC_NOT_MEASURED` end to end and its results never enter an electrical table. No simulator, no
old waveform replay, no circuit under test as its own checker.

The negative cases follow one shape: first prove the injected fact really exists in the bytes or the
sample list, then require the named rule to refuse it. An expectation of `[]` matched against a result
of `[]` is never counted as a detection.

    python scripts/dd1_d7c_b_prep_cases.py            # all cases
    python scripts/dd1_d7c_b_prep_cases.py --json out.json
"""

from __future__ import absolute_import, division, print_function

import argparse
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import dd1_d7c_a_r2_plan as R2PLAN              # noqa: E402
import dd1_d7c_b_prep_contract as CONTRACT      # noqa: E402
import dd1_d7c_b_prep_deckgen as DECKGEN        # noqa: E402
import dd1_d7c_b_prep_measure as MEASURE        # noqa: E402
import dd1_d7c_b_prep_r1_deck_read as DECKREAD  # noqa: E402  (the independent deck reading)
import dd1_d7c_b_prep_schedule as SCHEDULE      # noqa: E402

U = 1e-6                                        # one microampere, in amperes
N = 1e-9                                        # one nanosecond, in seconds
TOL_C = 1e-24                                   # a charge comparison bound, one yoctocoulomb
DATA = CONTRACT.contract()
NOMINAL_000 = DATA['nominal_current_A_by_code']['000']
LIMIT_ABS = DATA['rules']['shutoff_leakage']['limit_A']
BAND = DATA['rules']['settling']['band_fraction']
HOLD_NS = DATA['rules']['settling']['hold_ns']


def _near(label, got, want, problems, tol=TOL_C):
    if abs(float(got) - float(want)) > tol:
        problems.append('%s computes %r, the hand arithmetic says %r (tolerance %g)'
                        % (label, got, want, tol))


def _want_status(label, got, want, problems):
    if got != want:
        problems.append('%s says %r, the rule must say %r' % (label, got, want))


def _pair(series_in_ns, series_in_uA):
    """hand samples into the accepted core's own units: picoseconds and amperes"""
    return ([(float(t) * 1000.0, float(v) * U) for t, v in zip(series_in_ns, series_in_uA)])


def _constant_sink():
    """the TR-120 shape: enable 1120..1240 ns, integration window 1130..1230 ns, one unit current"""
    enable = _pair([0, 1110, 1130, 1230, 1250, 1480], [0, 0, 1.8, 1.8, 0, 0])
    current = _pair([0, 1120, 1240, 1480], [0, NOMINAL_000 / U, NOMINAL_000 / U, 0])
    return enable, current


# ---- positive and negative cases ----------------------------------------------------------------

def c01_positive_sink_charge():
    """SYNTHETIC: a branch sinking 1.875 uA for 100 ns delivers 1.875e-13 C and reads positive"""
    _enable, current = _constant_sink()
    problems = []
    charge = MEASURE.window_charge(current, MEASURE.ps(1130), MEASURE.ps(1230), 'TR-120#W0')
    # hand: 100 ns x 1.875 uA = 1.875e-7 s? no: 100e-9 s x 1.875e-6 A = 1.875e-13 C
    _near('Q over the flat window', charge['q'], 1.875e-13, problems)
    _near('flat mean', charge['flat_mean_A'], 1.875e-6, problems, 1e-18)
    _want_status('identity Q=Qpos+Qneg', charge['identity_holds'], True, problems)
    _want_status('sign', MEASURE.sign_check(charge)['status'], 'SINK_POSITIVE_AS_DECLARED', problems)
    return problems, ('Q=%g C over 100 ns at %g uA, sign %s'
                      % (charge['q'], NOMINAL_000 / U, MEASURE.sign_check(charge)['status']))


def c02_reversed_probe_is_refused_not_absorbed():
    """the ammeter turned around: the same magnitude must refuse, because abs() would let it pass"""
    _enable, current = _constant_sink()
    flipped = [(t, -v) for t, v in current]
    problems = []
    charge = MEASURE.window_charge(flipped, MEASURE.ps(1130), MEASURE.ps(1230), 'flipped')
    if charge['q'] >= 0:
        problems.append('the injected reversal did not happen: Q is still %r' % charge['q'])
    _near('Q of the reversed probe', charge['q'], -1.875e-13, problems)
    verdict = MEASURE.sign_check(charge)
    _want_status('sign', verdict['status'], 'PROBE_DIRECTION_SUSPECT', problems)
    if abs(charge['q']) != 1.875e-13:
        problems.append('the magnitude test is what would have hidden this')
    return problems, ('the same physics on reversed terminals gives Q=%g C; abs() would have made it '
                     'look identical to the positive case, the rule refuses instead' % charge['q'])


def c03_reversed_terminal_order_in_a_deck_is_named():
    """a deck whose iprobe line was turned around must be refused by the deck audit itself"""
    problems, detail = [], ''
    rows, _windows, _pwl, unreadable = SCHEDULE.read_delivered()
    if unreadable:
        return unreadable, ''
    row = dict((r['case_id'], r) for r in rows)['TR-120']
    path = os.path.join(ROOT, DECKGEN.DECK_DIR.replace('/', os.sep), 'TR-120.scs')
    text = io.open(path, encoding='utf-8', newline='').read()
    old = 'Ip_branch (clamp_node data_out) iprobe'
    # the statement, not the comment that quotes it: exactly one line is the iprobe declaration
    lines = [index for index, line in enumerate(text.split('\n')) if line.strip() == old]
    if len(lines) != 1:
        return ['the iprobe statement is not unique in TR-120.scs (%d lines)' % len(lines)], ''
    pieces = text.split('\n')
    pieces[lines[0]] = 'Ip_branch (data_out clamp_node) iprobe'
    mutated = '\n'.join(pieces)
    if mutated == text:
        return ['the injection changed nothing'], ''
    before = [i for i, line in enumerate(text.split('\n'), 1) if line == old]
    after = [i for i, line in enumerate(mutated.split('\n'), 1)
             if line == 'Ip_branch (data_out clamp_node) iprobe']
    refusals = DECKGEN.audit_text(mutated, row)
    named = [line for line in refusals if 'contracted terminal order' in line]
    if not named:
        problems.append('the swapped terminals produced no named refusal: %s' % refusals)
    if len(refusals) != len(named):
        problems.append('other deck rules also fired, so the case cannot be attributed: %s' % refusals)
    detail = ('line %d became (data_out clamp_node) and the deck audit answered: %s'
              % (before[0], named[0][:150]) if named else 'no refusal')
    return problems, detail


def c04_tail_that_cancels_is_not_zero_leakage():
    """SYNTHETIC: +0.5 then -0.5 uA over a tail gives net Q = 0 and still fails the leakage limit"""
    problems = []
    current = _pair([1240, 1300, 1360, 1420, 1480], [0, 0.5, 0, -0.5, 0])
    verdict = MEASURE.leakage(current, MEASURE.ps(1240), MEASURE.ps(1480), MEASURE.ps(1240))
    if abs(verdict['signed_tail_q']) > TOL_C:
        problems.append('the injected tail was supposed to cancel, it gives Q=%r'
                        % verdict['signed_tail_q'])
    _want_status('leakage', verdict['status'], 'ABOVE_LIMIT', problems)
    _near('max(abs(I))', verdict['max_abs_A'], 0.5 * U, problems, 1e-18)
    _want_status('cancellation is stated', bool(verdict['cancellation_warning']), True, problems)
    if verdict['tail_q_pos'] <= 0 or verdict['tail_q_neg'] >= 0:
        problems.append('both halves must stay visible: %r / %r'
                        % (verdict['tail_q_pos'], verdict['tail_q_neg']))
    return problems, ('net Q=%g C looks like a shut branch, the magnitude test still says %g uA '
                      'against a %g uA limit' % (verdict['signed_tail_q'], verdict['max_abs_A'] / U,
                                                 LIMIT_ABS / U))


def c05_quiet_tail_passes_and_reports_both_instants():
    """the positive control for the same rule: a quiet tail passes and names its sample instant"""
    problems = []
    current = _pair([1240, 1300, 1380, 1480], [0, 0.02, 0.01, 0.0])
    verdict = MEASURE.leakage(current, MEASURE.ps(1240), MEASURE.ps(1480), MEASURE.ps(1240))
    _want_status('leakage', verdict['status'], 'WITHIN_LIMIT', problems)
    if verdict['max_abs_A'] > LIMIT_ABS:
        problems.append('a passing verdict above the limit is the failure this rule exists to stop')
    if verdict['at_sample_ps'] is None:
        problems.append('no sample instant reported')
    return problems, ('max(abs(I))=%g uA at %g ns inside the last 100 ns, under the %g uA limit'
                      % (verdict['max_abs_A'] / U, verdict['at_sample_ps'] / 1000.0, LIMIT_ABS / U))


def c06_nonuniform_samples_match_the_pencil():
    """samples at 0/10/25/40 ns, window 5..20 ns: the interpolated trapezoid must equal 1.375e-13 C"""
    problems = []
    current = _pair([0, 10, 25, 40], [0, 10, 10, 0])
    charge = MEASURE.window_charge(current, MEASURE.ps(5), MEASURE.ps(20), 'non-uniform')
    # hand: value(5)=5 uA; 5->10 = 5 ns x (5+10)/2 uA = 3.75e-14 C; 10->20 = 10 ns x 10 uA = 1e-13 C
    _near('Q', charge['q'], 3.75e-14 + 1.0e-13, problems)
    if charge['start_ps'] != MEASURE.ps(5) or charge['stop_ps'] != MEASURE.ps(20):
        problems.append('the window bounds moved off the declared instants: %r..%r'
                        % (charge['start_ps'], charge['stop_ps']))
    if charge['points'] != 3:
        problems.append('the clipped window should hold the two interpolated bounds plus the interior '
                        'sample, it holds %d points' % charge['points'])
    return problems, 'Q=%g C, boundaries interpolated onto the enclosing pairs' % charge['q']


def c07_adaptive_precision_is_kept():
    """a simulator time like 1.999016675925999e-06 s is not a whole picosecond and must not be snapped"""
    problems = []
    times = ['1.999016675925999e-06', '2.0e-06', '2.0000000001e-06']
    samples, quantum = MEASURE.load_samples(times, ['1e-6', '2e-6', '3e-6'], 'adaptive')
    if abs(samples[0][0] - 1999016.675925999) > 1e-6:
        problems.append('the first sample was moved off its printed value: %r' % samples[0][0])
    if quantum <= 0:
        problems.append('no display quantum was returned, so the evidence cannot state its own bound')
    return problems, ('kept %g ps (quantum %g ps), which is the bound a reviewer needs beside the '
                      'number' % (samples[0][0], quantum))


def c08_garbage_samples_are_named_not_crashed():
    """NaN, a repeated time, a backwards time and a missing edge each come back as a named refusal"""
    expectations = [
        ('NaN current', ['0', '1'], ['NaN', '1'], 'not a plain finite number'),
        ('repeated time', ['1', '1'], ['1', '1'], 'repeat or step backwards'),
        ('backwards time', ['2', '1'], ['1', '1'], 'repeat or step backwards'),
        ('no samples', [], [], 'no samples'),
    ]
    problems = []
    for label, times, values, needle in expectations:
        try:
            MEASURE.load_samples(times, values, label)
            problems.append('%s was accepted instead of refused' % label)
        except MEASURE.Refuse as error:
            if needle not in str(error):
                problems.append('%s refused with "%s", which does not name %r'
                                % (label, error, needle))
    enable = _pair([0, 100], [0, 0])
    edges = MEASURE.enable_edges(enable, 1.8, MEASURE.ps(10), MEASURE.ps(90), 'no-edge case')
    _want_status('rise edge', edges['rise_status'], 'NO_REAL_EDGE_FOUND', problems)
    if 'refused' not in edges.get('refusal', ''):
        problems.append('the missing edge produced no refusal text: %r' % edges)
    return problems, 'four bad sample shapes and one edge-less window all refused by name'


def c09_left_band_before_the_deadline():
    """current inside +/-5 % and then out again before its own deadline is not SETTLED"""
    target = NOMINAL_000
    lo, hi = target * (1 - BAND), target * (1 + BAND)
    current = _pair([1130, 1150, 1180, 1200, 1215, 1230],
                    [1.9, 1.9, 1.9, 1.9, (lo + hi) / 2 / U * 0.4, 0.4 * (lo + hi) / 2 / U])
    problems = []
    verdict = MEASURE.settling(current, MEASURE.ps(1130), target, MEASURE.ps(1230))
    if verdict['status'] == 'SETTLED_HELD':
        problems.append('a curve that leaves the band before the deadline cannot be reported settled')
    _want_status('status', verdict['status'], 'LEFT_BAND_BEFORE_DEADLINE', problems)
    if verdict['band_left_at_ps'] is None:
        problems.append('the moment it left the band is the evidence and it is missing')
    return problems, ('left the band at %g ns, held only %s ns, deadline %g ns'
                      % ((verdict['band_left_at_ps'] or 0) / 1000.0,
                         verdict['held_ps'], MEASURE.ps(1230) / 1000.0))


def c10_settled_and_held_is_the_positive():
    target = NOMINAL_000
    current = _pair([1130, 1150, 1180, 1210, 1230], [1.9, 1.9, 1.9, 1.9, 1.9])
    problems = []
    verdict = MEASURE.settling(current, MEASURE.ps(1130), target, MEASURE.ps(1230))
    _want_status('status', verdict['status'], 'SETTLED_HELD', problems)
    if (verdict['held_ps'] or 0) < HOLD_NS * 1000.0:
        problems.append('held %s ps, the contract requires %g ns' % (verdict['held_ps'], HOLD_NS))
    return problems, 'in band from the edge to the deadline, held %g ns' % ((verdict['held_ps'] or 0)
                                                                           / 1000.0)


def c11_halved_array_fails_absolute_and_passes_ratio():
    """every level at half current: the ladder looks perfect and the absolute check must still fail"""
    problems = []
    halved = dict((code, 0.5 * value) for code, value in
                  DATA['nominal_current_A_by_code'].items())
    verdict = MEASURE.ladder(halved)
    _want_status('ratio', verdict['ratio_pass'], True, problems)
    _want_status('absolute', verdict['absolute_pass'], False, problems)
    _want_status('overall', verdict['overall'], 'FAIL', problems)
    exact = dict(DATA['nominal_current_A_by_code'])
    passed = MEASURE.ladder(exact)
    _want_status('exact ladder overall', passed['overall'], 'PASS', problems)
    _near('Iunit_ref from I111/8', passed['iunit_ref_A'], NOMINAL_000, problems, 1e-24)
    return problems, ('half current gives worst deviation %g units of Iunit_ref, absolute %g uA '
                      'against the band %g-%g uA'
                      % (verdict['worst_deviation_in_units'], verdict['i111_A'] / U,
                         DATA['rules']['full_scale_absolute']['lower_A'] / U,
                         DATA['rules']['full_scale_absolute']['upper_A'] / U))


def c12_code_000_is_one_branch_never_black():
    """the lowest code conducts exactly one branch; dropping it from the ladder is a named refusal"""
    problems = []
    if R2PLAN.DC_CONDUCTING['000'] != 1:
        problems.append('the delivered plan says code 000 conducts %s branches'
                        % R2PLAN.DC_CONDUCTING['000'])
    deck = io.open(os.path.join(ROOT, DECKGEN.DECK_DIR.replace('/', os.sep),
                                'DC-000.scs'), encoding='utf-8', newline='').read()
    if '1 of 8' not in deck and 'nominal for this code: 1.875 uA' not in deck:
        problems.append('DC-000.scs does not state that one branch conducts at the lowest code')
    partial = dict((code, value) for code, value in DATA['nominal_current_A_by_code'].items()
                   if code != '000')
    try:
        MEASURE.ladder(partial)
        problems.append('a ladder with code 000 left out as if it were a black code was accepted')
    except MEASURE.Refuse as error:
        if '000' not in str(error):
            problems.append('the refusal did not name the missing code: %s' % error)
    return problems, 'code 000 = 1 branch, and a ladder missing it is refused by name'


def c13_refined_pair_losing_its_history():
    """a refined case that dropped the first seven platforms is no longer the same conditions"""
    rows, windows, pwl, problems0 = SCHEDULE.read_delivered()
    if problems0:
        return problems0, ''
    by_case = dict((r['case_id'], r) for r in rows)
    base = by_case['RS-FULL']
    partner = by_case['TR-LONG']
    mutated = dict(base)
    mutated['platform_start_ns'] = partner['platform_start_ns'].split(';')[-1]
    mutated['full_window_start_ns'] = partner['full_window_start_ns'].split(';')[-1]
    mutated['full_window_stop_ns'] = partner['full_window_stop_ns'].split(';')[-1]
    mutated['flat_start_ns'] = partner['flat_start_ns'].split(';')[-1]
    mutated['flat_stop_ns'] = partner['flat_stop_ns'].split(';')[-1]
    mutated['rise_low_ns'] = partner['rise_low_ns'].split(';')[-1]
    mutated['rise_high_ns'] = partner['rise_high_ns'].split(';')[-1]
    mutated['fall_high_ns'] = partner['fall_high_ns'].split(';')[-1]
    mutated['fall_low_ns'] = partner['fall_low_ns'].split(';')[-1]
    mutated['platform_stop_ns'] = partner['platform_stop_ns'].split(';')[-1]
    mutated['tail_start_ns'] = partner['tail_start_ns'].split(';')[-1]
    mutated['tail_stop_ns'] = partner['tail_stop_ns'].split(';')[-1]
    mutated['pure_off_start_ns'] = partner['pure_off_start_ns'].split(';')[-1]
    mutated['pure_off_stop_ns'] = partner['pure_off_stop_ns'].split(';')[-1]
    mutated['leak_window_ns'] = partner['leak_window_ns'].split(';')[-1]
    mutated['code_change_ns'] = partner['code_change_ns'].split(';')[-1]
    mutated['enable_rise_50_ns'] = partner['enable_rise_50_ns'].split(';')[-1]
    mutated['enable_fall_50_ns'] = partner['enable_fall_50_ns'].split(';')[-1]
    mutated['settled_before_enable_ns'] = partner['settled_before_enable_ns'].split(';')[-1]
    if mutated['platform_start_ns'] == base['platform_start_ns']:
        return ['the injection did not change RS-FULL'], ''
    rows2 = [mutated if r['case_id'] == 'RS-FULL' else r for r in rows]
    problems = [p for p in SCHEDULE.validate(rows2, windows, pwl, DATA) if 'RS-FULL' in p]
    if not problems:
        return ['dropping seven platforms from RS-FULL produced no refusal'], ''
    return [], 'the schedule refused it: %s' % problems[0][:110]


def c14_refined_pair_changing_the_supply():
    """a refined case that also moved DATA_EN is not a time-step refinement of anything"""
    rows, windows, pwl, problems0 = SCHEDULE.read_delivered()
    if problems0:
        return problems0, ''
    base = dict((r['case_id'], r) for r in rows)['RS-LOW']
    mutated = dict(base)
    mutated['data_en_level_V'] = '1.500'
    if mutated['data_en_level_V'] == base['data_en_level_V']:
        return ['the injection did not change the level'], ''
    rows2 = [mutated if r['case_id'] == 'RS-LOW' else r for r in rows]
    problems = [p for p in SCHEDULE.validate(rows2, windows, pwl, DATA) if 'RS-LOW' in p]
    if not problems:
        return ['a refined case that also changed the enable level produced no refusal'], ''
    return [], 'the schedule refused it: %s' % problems[0][:110]


def c15_refined_pair_losing_a_transition():
    """RS-SWITCH must keep both code changes; dropping one is a different experiment"""
    rows, windows, pwl, problems0 = SCHEDULE.read_delivered()
    if problems0:
        return problems0, ''
    base = dict((r['case_id'], r) for r in rows)['RS-SWITCH']
    mutated = dict(base)
    mutated['code_change_ns'] = ';'.join(base['code_change_ns'].split(';')[:3])
    if mutated['code_change_ns'] == base['code_change_ns']:
        return ['the injection did not remove a transition'], ''
    rows2 = [mutated if r['case_id'] == 'RS-SWITCH' else r for r in rows]
    problems = [p for p in SCHEDULE.validate(rows2, windows, pwl, DATA) if 'RS-SWITCH' in p]
    if not problems:
        return ['a refined case with one code change fewer produced no refusal'], ''
    return [], 'the schedule refused it: %s' % problems[0][:110]


def c16_convergence_reports_an_absolute_difference():
    """a finer step that moves the charge says so in coulombs, not just in a status word"""
    problems = []
    context = {'sign_rule': 'I_sink = Ip_branch', 'threshold_V': 0.9,
               'window_start_ps': MEASURE.ps(1130), 'window_stop_ps': MEASURE.ps(1230),
               'reference_current_A': NOMINAL_000}
    coarse = dict(context)
    coarse.update({'q': 1.875e-13})
    refined = dict(context)
    refined.update({'q': 1.975e-13})
    verdict = MEASURE.convergence(coarse, refined, 120e-9, MEASURE.SYNTHETIC)
    _near('absolute delta', verdict['delta_q_C'], 1.0e-14, problems)
    _want_status('status', verdict['status'], 'OUTSIDE_LIMIT', problems)
    if verdict['delta_q_fC'] is None:
        problems.append('no absolute difference was reported')
    drifted = dict(refined)
    drifted['window_stop_ps'] = MEASURE.ps(1240)
    second = MEASURE.convergence(coarse, drifted, 120e-9, MEASURE.SYNTHETIC)
    _want_status('moved window', second['status'], 'REFUSED_CONTEXT_CHANGED', problems)
    return problems, ('delta Q=%g fC = %g QLSB against a %g limit; moving the window by 10 ns '
                      'refuses the comparison' % (verdict['delta_q_fC'],
                                                 verdict['abs_delta_over_qlsb'], verdict['limit']))


def c17_charge_errors_keep_the_two_expectations_apart():
    """nominal and DC expectations, both in QLSB, with the DC one refused until a native point exists"""
    problems = []
    verdict = MEASURE.charge_errors(1.875e-13, NOMINAL_000, 100e-9, None, 120e-9)
    _near('nominal expectation', verdict['qexpected_nominal_C'], 1.875e-13, problems)
    _want_status('dc expectation', verdict['idc_status'], 'NOT_RUN', problems)
    _want_status('nominal verdict', verdict['verdict_nominal'], 'WITHIN_PROPOSED_LIMIT', problems)
    _near('QLSB at a 120 ns tick', verdict['qlsb_C'], 2.25e-13, problems)
    with_dc = MEASURE.charge_errors(1.875e-13, NOMINAL_000, 100e-9, 2.0e-6, 120e-9)
    _want_status('with a DC point', with_dc['idc_status'], 'AVAILABLE', problems)
    _near('DC expectation', with_dc['qexpected_dc_C'], 2.0e-13, problems)
    return problems, ('nominal %g C vs DC %s; QLSB %g C, error %g LSB'
                      % (verdict['qexpected_nominal_C'], verdict['qexpected_dc_C'], verdict['qlsb_C'],
                         verdict['error_nominal_LSB']))


# ---- R1 cases added through the real measurement entrance (task book section 5) ------------------

RAIL_V = DATA['units']['logic_high_V']
LEAK_NS = DATA['rules']['shutoff_leakage']['tail_last_ns']
TOL_WIDE = 1e-21                                  # the same pencil arithmetic, for a longer window


def _floats(cell):
    return [float(part) for part in cell.split(';') if part]


def _codes_of(row):
    """the code sequence of a case, derived from its own table cell"""
    code = row['pam_code']
    if code == '000..111':
        return sorted(DATA['nominal_current_A_by_code'])
    return code.split(',')


def _ramps(row):
    """the four ramp endpoints of every platform, in nanoseconds, straight from the schedule row"""
    return list(zip(_floats(row['rise_low_ns']), _floats(row['rise_high_ns']),
                    _floats(row['fall_high_ns']), _floats(row['fall_low_ns'])))


def _enable_samples(row):
    """the enable as a finite-slope wave: low at the ramp start, rail at the ramp end"""
    points = [(0.0, 0.0)]
    for low, high, fall_high, fall_low in _ramps(row):
        points.extend([(low, 0.0), (high, RAIL_V), (fall_high, RAIL_V), (fall_low, 0.0)])
    return [(time_ns * 1000.0, value) for time_ns, value in points]


def _current_samples(row, leaks=None):
    """a branch that follows its own enable, plus hand-injected leak currents over named tails

    The current is zero at the ramp start and nominal at the ramp end, so every integral below is a
    trapezoid a pencil can do: the full-enable window keeps (T50 - 3/4 x edge) x I, the flat window
    keeps (T50 - edge) x I. `leaks` maps a platform index to an amperes value that is present over
    the last 100 ns of that platform's own off tail.
    """
    ramps = _ramps(row)
    codes = _codes_of(row)
    tail_stops = _floats(row['tail_stop_ns'])
    points = [(0.0, 0.0)]
    for index, code in enumerate(codes):
        nominal = DATA['nominal_current_A_by_code'][code]
        low, high, fall_high, fall_low = ramps[index]
        points.extend([(low, 0.0), (high, nominal), (fall_high, nominal), (fall_low, 0.0)])
        leak = (leaks or {}).get(index)
        if leak is not None:
            points.extend([(tail_stops[index] - LEAK_NS, float(leak)),
                           (tail_stops[index] - 0.001, float(leak))])
    if points[-1][0] < float(row['stop_ns']):
        # the last off tail runs to the analysis stop, so the wave has to say what it does there
        points.append((float(row['stop_ns']), 0.0))
    return [(time_ns * 1000.0, value) for time_ns, value in points]


def _delivered():
    rows, windows, _pwl, problems = SCHEDULE.read_delivered()
    if problems:
        return None, None, problems
    return dict((row['case_id'], row) for row in rows), windows, []


def c18_leak_only_in_the_second_tail_is_found_there():
    """eight codes measured at once: 5 uA in the second tail only, and it is the second one it names"""
    by_case, windows, problems = _delivered()
    if problems:
        return problems, ''
    row = by_case['TR-LONG']
    leaks = {1: 5.0 * U}
    samples = {'enable': _enable_samples(row), 'current': _current_samples(row, leaks)}
    entries = MEASURE.measure_case(row, windows, samples)
    codes = _codes_of(row)
    if len(entries) != 8:
        problems.append('TR-LONG declares eight platforms but the entrance returned %d entries'
                        % len(entries))
        return problems, ''
    above = [entry['index'] for entry in entries
             if entry['leakage']['status'] == 'ABOVE_LIMIT']
    if above != [1]:
        problems.append('the injected 5 uA leak reached %s, but it was written only into the tail of '
                        'platform 1' % (above,))
    for entry in entries:
        if entry['index'] == 1:
            continue
        if entry['leakage']['status'] != 'WITHIN_LIMIT':
            problems.append('platform %d reports %s although nothing was injected into its tail'
                            % (entry['index'], entry['leakage']['status']))
    _want_status('k-th emission pairs with the k-th tail',
                 entries[1]['windows']['off_tail'], 'TR-LONG#T1', problems)
    _want_status('the same entry names its own emission window',
                 entries[1]['windows']['emission'], 'TR-LONG#W1', problems)
    if entries[1]['leakage']['max_abs_A'] != 5.0 * U:
        problems.append('the second tail reports max(abs(I)) = %r, the injection was 5e-06 A exactly'
                        % (entries[1]['leakage']['max_abs_A'],))
    if entries[1]['leakage']['window_valid'] != 'INSIDE_PURE_OFF':
        problems.append('the second tail window is %s, so this is not the leakage rule but a window '
                        'problem' % entries[1]['leakage']['window_valid'])
    return problems, ('8 codes, one 5 uA leak in platform 1: ABOVE_LIMIT at index %s with max(abs(I)) '
                      '= %g A over %g ns, the other seven WITHIN_LIMIT'
                      % (above, entries[1]['leakage']['max_abs_A'],
                         entries[1]['leakage']['window_length_ns']))


def c19_full_enable_and_flat_windows_are_different_numbers():
    """TR-120 on finite edges: the full-enable charge and the flat charge both match the pencil"""
    by_case, windows, problems = _delivered()
    if problems:
        return problems, ''
    row = by_case['TR-120']
    samples = {'enable': _enable_samples(row), 'current': _current_samples(row)}
    entries = MEASURE.measure_case(row, windows, samples)
    if len(entries) != 1:
        problems.append('TR-120 has one platform but the entrance returned %d entries' % len(entries))
        return problems, ''
    entry = entries[0]
    if entry['result'] == MEASURE.REFUSE_NO_EDGE:
        problems.append('TR-120 refused its own edges: %s' % entry['refusal'])
        return problems, ''
    # hand: T50 = 1170 -> 1290 = 120 ns, edge 20 ns. The full window keeps the flat 100 ns plus the
    # two half-ramp trapezoids, each 10 ns long at an average of three quarters of the current:
    # 1.875 uA x (100 + 2 x 10 x 0.75) ns = 1.875e-6 x 115e-9 = 2.15625e-13 C
    _near('full-enable Q', entry['q_full_C'], 2.15625e-13, problems, TOL_WIDE)
    # hand: the flat part is 1180 -> 1280 at the full current: 1.875 uA x 100 ns = 1.875e-13 C
    _near('flat Q', entry['q_flat_C'], 1.875e-13, problems, TOL_WIDE)
    if abs(entry['q_full_C'] - entry['q_flat_C']) < 1e-15:
        problems.append('the two windows returned the same number, which means one of them was not '
                        'the window the table declares')
    _want_status('identity holds on the full window', entry['q_full_identity_holds'], True, problems)
    _want_status('sign on the flat window', entry['sign']['status'], 'SINK_POSITIVE_AS_DECLARED',
                 problems)
    return problems, ('full %g C over 120 ns of enable versus flat %g C over 100 ns of flat part; '
                      'the difference %g C is the two ramp trapezoids'
                      % (entry['q_full_C'], entry['q_flat_C'],
                         entry['q_full_C'] - entry['q_flat_C']))


def c20_no_window_of_the_delivered_schedule_lacks_an_edge():
    """the PREP entrance refused eight windows for want of an edge; none of them may still refuse"""
    by_case, windows, problems = _delivered()
    if problems:
        return problems, ''
    refused, total, mismatched = [], 0, []
    transient_cases = 0
    for case_id in sorted(by_case):
        row = by_case[case_id]
        if row['class'] == 'dc_sweep':
            continue
        transient_cases += 1
        samples = {'enable': _enable_samples(row), 'current': _current_samples(row)}
        for entry in MEASURE.measure_case(row, windows, samples):
            total += 1
            if entry['result'] == MEASURE.REFUSE_NO_EDGE:
                refused.append('%s: %s' % (entry['window_id'], entry['refusal']))
                continue
            for column, key in (('enable_rise_50_ns', 'rise_50_ps'),
                                ('enable_fall_50_ns', 'fall_50_ps')):
                declared = _floats(row[column])[entry['index']] * 1000.0
                if abs(entry['edges'][key] - declared) > 1e-3:
                    mismatched.append('%s %s reads %s ps, the table declares %s ps'
                                      % (entry['window_id'], key, entry['edges'][key], declared))
    if refused:
        problems.append('%d of %d windows still refuse their edges: %s'
                        % (len(refused), total, refused[0][:120]))
    if mismatched:
        problems.append('%d edges do not land on the declared instant: %s'
                        % (len(mismatched), mismatched[0][:120]))
    return (problems if problems else []), ('%d windows over %d transient cases measured through the '
                                            'entrance, edge refusals=%d, edges off their declared '
                                            'instant=%d' % (total, transient_cases, len(refused),
                                                             len(mismatched)))


def c21_convergence_refuses_a_context_it_cannot_read():
    """both sides must carry the named context: absent fields are a refusal, not an equal pair"""
    problems = []
    fields = DATA['rules']['convergence']['required_context_fields']
    base = {'q': 2.15625e-13, 'delta_q': 0.0, 'flat_mean_A': 1.875e-6, 'sign_rule': 'I_sink = Ip_branch',
            'threshold_V': 0.9, 'window_start_ps': 1170000.0, 'window_stop_ps': 1290000.0,
            'reference_current_A': NOMINAL_000}
    clean = MEASURE.convergence(base, dict(base), 120e-9)
    if clean['status'] != 'WITHIN_LIMIT':
        problems.append('a complete, identical pair should converge, it says %s (%s)'
                        % (clean['status'], clean.get('refusal', '')))
    for field in fields:
        coarse, refined = dict(base), dict(base)
        del coarse[field]
        del refined[field]
        verdict = MEASURE.convergence(coarse, refined, 120e-9)
        _want_status('both sides without %s' % field, verdict['status'], 'REFUSED_MISSING_CONTEXT',
                     problems)
        if field not in verdict['missing_context']:
            problems.append('%s was deleted from both sides and the refusal does not name it: %s'
                            % (field, verdict['missing_context']))
    backward = MEASURE.convergence(dict(base, window_start_ps=1290000.0, window_stop_ps=1170000.0),
                                   dict(base), 120e-9)
    _want_status('a backwards window', backward['status'], 'REFUSED_MISSING_CONTEXT', problems)
    if not backward['invalid_input']:
        problems.append('the backwards window was not named as an invalid input')
    not_a_number = MEASURE.convergence(dict(base, q=float('nan')), dict(base), 120e-9)
    _want_status('a NaN charge', not_a_number['status'], 'REFUSED_MISSING_CONTEXT', problems)
    return problems, ('%s context fields each refused by name when both sides omitted them; the '
                      'complete pair converges at %s' % (len(fields), clean['status']))


def c22_leakage_window_reaching_an_edge_is_refused_not_truncated():
    """a tail too short for a 100 ns sub-window, and an enable that rises inside it: both refuse"""
    by_case, windows, problems = _delivered()
    if problems:
        return problems, ''
    row = by_case['TR-120']
    samples = {'enable': _enable_samples(row), 'current': _current_samples(row)}
    short = []
    for entry in windows:
        copy = dict(entry)
        if copy['case_id'] == 'TR-120' and copy['window_id'] == 'TR-120#T0':
            copy['stop_ns'] = '1300.000'
        short.append(copy)
    entries = MEASURE.measure_case(row, short, samples)
    fact = entries[0]['leakage']['window_start_ps'] < MEASURE.ps(1300.0)
    if not fact:
        problems.append('the injected short tail does not reach outside the pure-off window, so this '
                        'case proves nothing (%s)' % entries[0]['leakage'])
    _want_status('short tail outside pure-off', entries[0]['leakage']['window_valid'],
                 'REFUSED_LEAKAGE_OUTSIDE_PURE_OFF', problems)
    _want_status('and the entrance reports the refusal', entries[0]['result'],
                 'REFUSED_LEAKAGE_OUTSIDE_PURE_OFF', problems)
    # the enable rising inside the sub-window: a second platform whose ramp starts at 1450 ns, which
    # is inside the leakage interval 1430-1530 ns of the first tail
    early = sorted(list(samples['enable']) + [(1450000.0, 0.0), (1470000.0, RAIL_V),
                                              (1570000.0, RAIL_V), (1590000.0, 0.0)])
    rising = MEASURE.leakage(samples['current'], MEASURE.ps(1290.0), MEASURE.ps(1530.0),
                             MEASURE.ps(1290.0), MEASURE.SYNTHETIC, enable_ps=early,
                             pure_off_start_ps=MEASURE.ps(1300.0))
    if not rising['enable_max_abs_V']:
        problems.append('the injected rise did not reach the leakage interval, so a pass here would '
                        'be an empty one')
    _want_status('enable not low in the leakage window', rising['enable_valid'],
                 'REFUSED_ENABLE_NOT_LOW', problems)
    return problems, ('a 10 ns tail refuses as %s and an enable that reaches %g V inside the window '
                      'refuses as %s, instead of being shortened to fit'
                      % (entries[0]['leakage']['window_valid'], rising['enable_max_abs_V'],
                         rising['enable_valid']))


def c23_dc_expectation_stays_not_run_through_the_entrance():
    """the entrance, not the helper: no IDC table means NOT_RUN, and a supplied one is its own number"""
    by_case, windows, problems = _delivered()
    if problems:
        return problems, ''
    row = by_case['TR-120']
    samples = {'enable': _enable_samples(row), 'current': _current_samples(row)}
    without = MEASURE.measure_case(row, windows, samples)[0]
    _want_status('DC expectation without a native point',
                 without['charge_error']['idc_status'], 'NOT_RUN', problems)
    if without['charge_error']['qexpected_dc_C'] != 'NOT_RUN':
        problems.append('a geometry guess would have stood in for IDC: %r'
                        % (without['charge_error']['qexpected_dc_C'],))
    _near('nominal expectation', without['charge_error']['qexpected_nominal_C'],
          NOMINAL_000 * 120e-9, problems, TOL_WIDE)
    with_dc = MEASURE.measure_case(row, windows, samples, idc_A_by_code={'000': 2.0e-6})[0]
    _want_status('DC expectation with a native point', with_dc['charge_error']['idc_status'],
                 'AVAILABLE', problems)
    # hand: IDC 2 uA over the same 120 ns T50 is 2.4e-13 C, against the nominal 1.875 uA x 120 ns
    _near('DC expectation value', with_dc['charge_error']['qexpected_dc_C'], 2.4e-13, problems,
          TOL_WIDE)
    if abs(without['charge_error']['error_nominal_LSB']
           - with_dc['charge_error']['error_nominal_LSB']) > 1e-12:
        problems.append('the nominal error moved when only the DC reference moved')
    return problems, ('nominal %g C (%g LSB) with the DC column %s; supplying IDC 2 uA makes the DC '
                      'expectation %g C, a different number reported beside it'
                      % (without['charge_error']['qexpected_nominal_C'],
                         without['charge_error']['error_nominal_LSB'],
                         without['charge_error']['qexpected_dc_C'],
                         with_dc['charge_error']['qexpected_dc_C']))


def c24_delivered_decks_read_clean():
    """the independent deck reader, on the bytes as delivered: fifteen decks, nothing to report"""
    problems, per_case, count = DECKREAD.check_all(ROOT)
    if count != 15:
        problems.append('the reader opened %d decks, the schedule has 15 cases' % count)
    if per_case.get('TR-LONG', {}).get('half_rail_crossings') != 16:
        problems.append('TR-LONG does not show sixteen half-rail crossings (%s), which is the eight '
                        'rise and eight fall edges its row declares'
                        % per_case.get('TR-LONG', {}).get('half_rail_crossings'))
    return problems, ('%d decks read from disk with the reader\'s own parser, problems=%d'
                      % (count, len(problems)))


def c25_the_reader_names_the_two_shapes_it_keeps():
    """the old long ramp and leakage over the next rise, both on copies, both refused by name"""
    scratch = os.path.join(tempfile.gettempdir(), 'd7c_b_prep_r1_cases_negative_scratch')
    shutil.rmtree(scratch, ignore_errors=True)
    results = DECKREAD.counterexamples(ROOT, scratch)
    problems = ['%s did not name the injection: %s' % (item['family'], item['detail'])
                for item in results if item['verdict'] != 'HIT']
    if os.path.isdir(scratch):
        problems.append('the scratch tree survived the run: %s' % scratch)
    named = [item['family'] for item in results if item['verdict'] == 'HIT']
    if 'delivered_bytes_control' not in named:
        problems.append('the run did not show that the delivered bytes stay clean')
    return problems, ('%d of %d shapes refused by name on temporary copies (%s)'
                      % (len(named), len(results), ', '.join(named)))


def cases():
    return [('C01_positive_sink_charge', 'POSITIVE', 'a 100 ns window at one unit current integrates '
             'to the hand-computed charge and reads positive', c01_positive_sink_charge),
            ('C02_reversed_probe_refused', 'NEGATIVE', 'turning the ammeter around cannot be '
             'rescued by abs()', c02_reversed_probe_is_refused_not_absorbed),
            ('C03_deck_probe_order_named', 'NEGATIVE', 'a deck written with the terminals swapped is '
             'refused by the deck audit', c03_reversed_terminal_order_in_a_deck_is_named),
            ('C04_cancelling_tail_fails', 'NEGATIVE', 'a tail whose positive and negative halves '
             'cancel is not zero leakage', c04_tail_that_cancels_is_not_zero_leakage),
            ('C05_quiet_tail_passes', 'POSITIVE', 'a quiet tail passes and names its sample instant',
             c05_quiet_tail_passes_and_reports_both_instants),
            ('C06_nonuniform_pencil_check', 'POSITIVE', 'interpolated boundaries over unequal spacing '
             'match the arithmetic done by hand', c06_nonuniform_samples_match_the_pencil),
            ('C07_adaptive_precision', 'POSITIVE', 'a printed simulator time is kept at its own '
             'precision with its display quantum reported', c07_adaptive_precision_is_kept),
            ('C08_garbage_named', 'NEGATIVE', 'NaN, a repeated time, a backwards time, an empty list '
             'and a missing edge each refuse by name', c08_garbage_samples_are_named_not_crashed),
            ('C09_left_band_before_deadline', 'NEGATIVE', 'entering the band and leaving early is not '
             'a settled window', c09_left_band_before_the_deadline),
            ('C10_settled_held', 'POSITIVE', 'staying in band to the deadline is the settled case',
             c10_settled_and_held_is_the_positive),
            ('C11_halved_array', 'NEGATIVE', 'eight levels at half current pass the ratio and fail '
             'the absolute target', c11_halved_array_fails_absolute_and_passes_ratio),
            ('C12_code_000_not_black', 'NEGATIVE', 'the lowest code is one conducting branch and '
             'cannot be dropped from the ladder', c12_code_000_is_one_branch_never_black),
            ('C13_refined_lost_history', 'NEGATIVE', 'a refined case that dropped the seven earlier '
             'platforms is not the same conditions', c13_refined_pair_losing_its_history),
            ('C14_refined_changed_supply', 'NEGATIVE', 'a refined case that also moved the enable '
             'level is refused', c14_refined_pair_changing_the_supply),
            ('C15_refined_lost_transition', 'NEGATIVE', 'a refined case that dropped one code change '
             'is a different experiment', c15_refined_pair_losing_a_transition),
            ('C16_convergence_absolute', 'NEGATIVE', 'convergence always carries an absolute '
             'difference, and a moved window refuses the comparison',
             c16_convergence_reports_an_absolute_difference),
            ('C17_two_charge_expectations', 'POSITIVE', 'nominal and DC expectations stay apart and '
             'the missing DC point is NOT_RUN, never a geometry guess',
             c17_charge_errors_keep_the_two_expectations_apart),
            ('C18_leak_in_second_tail', 'POSITIVE', 'eight codes measured at once find the 5 uA leak '
             'in the second tail and nowhere else', c18_leak_only_in_the_second_tail_is_found_there),
            ('C19_full_versus_flat_window', 'POSITIVE', 'the full-enable charge and the flat charge '
             'are different numbers, each matching its own pencil arithmetic',
             c19_full_enable_and_flat_windows_are_different_numbers),
            ('C20_no_edge_refusal_left', 'POSITIVE', 'every window of the delivered schedule finds '
             'its own interpolated 50% edges on the declared instant',
             c20_no_window_of_the_delivered_schedule_lacks_an_edge),
            ('C21_missing_context_refused', 'NEGATIVE', 'convergence refuses when a side does not '
             'carry the named context, instead of calling None equal to None',
             c21_convergence_refuses_a_context_it_cannot_read),
            ('C22_leakage_window_refusals', 'NEGATIVE', 'a leakage interval that reaches the pure-off '
             'start or a rising enable is refused, never shortened to fit',
             c22_leakage_window_reaching_an_edge_is_refused_not_truncated),
            ('C23_dc_expectation_via_entrance', 'NEGATIVE', 'through the entrance a missing native DC '
             'point stays NOT_RUN while the nominal error is computed',
             c23_dc_expectation_stays_not_run_through_the_entrance),
            ('C24_decks_read_clean', 'POSITIVE', 'the independent reader opens the fifteen delivered '
             'decks and finds nothing to report', c24_delivered_decks_read_clean),
            ('C25_reader_names_the_shapes', 'NEGATIVE', 'the old long ramp and leakage over the next '
             'rise are refused by name on temporary copies',
             c25_the_reader_names_the_two_shapes_it_keeps)]


def run():
    out = []
    for name, kind, meaning, body in cases():
        try:
            problems, detail = body() or ([], '')
        except Exception as error:                    # noqa: BLE001 - a crash is a named MISS
            problems, detail = ['%s: %s' % (type(error).__name__, str(error)[:140])], ''
        out.append({'case': name, 'kind': kind, 'meaning': meaning,
                    'verdict': 'HIT' if not problems else 'MISS',
                    'detail': detail, 'problems': problems,
                    'evidence_class': MEASURE.SYNTHETIC})
    return out


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default='')
    arguments = parser.parse_args(argv)
    rows = run()
    for row in rows:
        print('%-32s %-8s %-5s %s' % (row['case'], row['kind'], row['verdict'],
                                      (row['detail'] or '; '.join(row['problems']))[:110]))
    failures = [row['case'] for row in rows if row['verdict'] != 'HIT']
    payload = {'cases': len(rows), 'failures': failures, 'results': rows,
               'evidence_class': MEASURE.SYNTHETIC,
               'rule': 'every negative case first proves the injected fact exists, then requires the '
                       'named rule to refuse it; an empty expectation against an empty result is never '
                       'a detection',
               'spectre_launches': 0, 'rtl_simulations': 0, 'oa_writes': 0}
    if arguments.json:
        with io.open(arguments.json, 'wb') as handle:
            handle.write((json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                         .encode('utf-8'))
    print('D7C_B_PREP_CASES: %s (%d/%d named exactly, failures: %s, evidence %s)'
          % ('PASS' if not failures else 'FAIL', len(rows) - len(failures), len(rows),
             ','.join(failures) or 'none', MEASURE.SYNTHETIC))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
