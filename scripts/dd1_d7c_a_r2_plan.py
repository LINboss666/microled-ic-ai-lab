#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_r2_plan.py -- one structured source for the fifteen draft native cases.

R1 wrote the plan table, the plan report and the bench draft in three separate places, and they
disagreed: the table said the off gap between TR-LONG windows was 0.5 TON while its own window list
spaced them 1.5 TON apart, and the bench probe terminals contradicted the sign the table declared.
This module is the only place those numbers are written down. `validate_schedule()` is run by
dd1_d7c_a_offline_check.py against the delivered table, so a drift between this source and the bytes
in the repository fails by name instead of surviving as prose.

Everything here is arithmetic over declared draft conditions. Nothing is simulated: no Spectre, no
ngspice/Xyce, no Icarus, no RTL, no OA, no VM. Every case result stays NOT_RUN and the 30/36 unit
count remains a proposal, not an authorisation.

    python scripts/dd1_d7c_a_r2_plan.py --emit tests/dd1_d7c_a/native_case_plan.csv
    python scripts/dd1_d7c_a_r2_plan.py --check
"""

from __future__ import absolute_import, division, print_function

import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import dd1_d7c_a_offline_check as CHECK      # noqa: E402   (rows_write, strict_read)

PLAN_HEADER = list(CHECK.PLAN_HEADER)
TON_NS = 1000                                 # one TON in ns, the draft frame unit
PLAN_TABLE = 'tests/dd1_d7c_a/native_case_plan.csv'

# ---- the sign convention, stated once ----------------------------------------------------------
#
# The physical positive pull-down path is clamp_node -> data_out -> the conducting branch -> vss, so
# an iprobe written as Ip_branch (clamp_node data_out) reads positive when the branch sinks current.
# That is also the orientation the accepted DATA-7B bench uses (scripts/dd1_d7b_run.py writes
# `Ip_out (clamp data_out) iprobe` and calls current from the clamp into the DUT pin positive), and
# it is the terminal order that spectral probe syntax was proven against in spectre/
# current_probe_syntax.scs, where the probe sits between the switching node and the output.
PROBE_INST = 'Ip_branch'
PROBE_TERMINALS = ('clamp_node', 'data_out')           # (in, out) for a sinking branch
PROBE_ORIENTATION = ('iprobe %s (%s %s), positive terminal first: a positive reading IS the branch '
                     'sinking current out of data_out' % ((PROBE_INST,) + PROBE_TERMINALS))
SIGN_CONVENTION = ('I_sink = Ip_branch with no negation and no abs(); Q = integral of I_sink over the '
                   'declared window, positive charge accumulating during the conducting window; the '
                   'off-window tail is integrated as its own negative area and never cancels against '
                   'it to claim a shut branch; declared before any run, not chosen after a sign')
MAXSTEP_WIDE_NS = 2.0
MAXSTEP_FINE_NS = 0.1

# ---- the long-pulse schedule: eight windows in ONE deck ---------------------------------------
#
# pitch = platform + off gap = 1.0 + 0.5 = 1.5 TON. The code changes inside the off gap, so no
# measurement ever straddles a switching edge, and the gap the prose quotes is the gap the numbers
# contain. Segment k: platform [1.5k, 1.5k+1.0], measurement window inset by the edge time.
LONG_PLATFORM_TON = 1.0
LONG_OFF_GAP_TON = 0.5
LONG_EDGE_TON = 0.05
LONG_TAIL_TON = 0.5
LONG_STOP_TON = 8 * (LONG_PLATFORM_TON + LONG_OFF_GAP_TON) + LONG_TAIL_TON

# ---- the short-pulse cases, with explicit edges and tails -------------------------------------
SHORT_CASES = (
    # case_id,   platform_TON, off_gap_TON, edge_TON, tail_TON, code, spacing note
    ('TR-120', 0.12, 0.12, 0.01, 0.24, '000', 'two pulses per 120 ns slot at the Hybrid 100 Hz pitch'),
    ('TR-200', 0.20, 0.12, 0.01, 0.24, '000', 'two pulses per 200 ns slot at the Hybrid 60 Hz pitch'),
)
OFFCODE_CASE = ('TR-OFFCODE', 0.30, 0.30, 0.02, 0.30, None,
                'code changes only inside the off windows: 011->100 then 000->111')

# ---- refined pairs: same stimulus, finer time step only ----------------------------------------
PARTNER_CONTRACT = {'RS-LOW': 'TR-120', 'RS-FULL': 'TR-LONG', 'RS-SWITCH': 'TR-OFFCODE'}
# every one of these must be byte-identical between a refined case and its partner
PAIR_IDENTITY_FIELDS = (
    ('pam_code', 'the code under test'),
    ('data_en_form', 'how the enable is driven'),
    ('data_en_level_V', 'the static enable level'),
    ('observe_nodes', 'what is saved'),
    ('measure_interval', 'the integration window in TON'),
    ('reference_definition', 'the external reference and its value'),
    ('failure_condition', 'what would count as a failure'),
    ('probe_orientation', 'the probe terminals and their positive direction'),
    ('sign_convention', 'the current and charge sign convention'),
    ('platform_TON', 'the pulse platform length'),
    ('off_gap_TON', 'the off window between platforms'),
    ('edge_TON', 'the finite edge time'),
    ('tail_TON', 'the shut-down tail window after the platform'),
    ('stimulus_start_TON', 'where the stimulus begins'),
)
DC_CODES = ('000', '001', '010', '011', '100', '101', '110', '111')
DC_CONDUCTING = dict((c, int(c, 2) + 1) for c in DC_CODES)

# PLAN_HEADER comes from the checker at line 32, so this module and the schema gate cannot drift


def _dc_row(index, code):
    conducting = DC_CONDUCTING[code]
    return {
        'case_id': 'DC-%s' % code, 'class': 'dc_sweep',
        'purpose': 'absolute sink current per conducting branch, decoded levels, shared reference and '
                   'each local bias node at the static operating point',
        'pam_code': code,
        'code': '%d (pam_sel=%s, %d of 8 branches on)' % (int(code, 2), code, conducting),
        'data_en_form': 'static_dc', 'data_en_level_V': '1.8',
        'stimulus_start_TON': '0', 'platform_TON': 'steady', 'edge_TON': 'not_applicable',
        'off_gap_TON': 'not_applicable', 'tail_TON': 'not_applicable', 'window_TON': 'sweep',
        'segments': 'clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read '
                    'off the same sweep',
        'maxstep_ns': 'not_applicable',
        'observe_nodes': 'iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, '
                         'Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes',
        'measure_interval': 'the DC operating point at each sweep step, no time window',
        'reference_definition': 'Iref = 15u injected into the diode-connected Mref; theoretical unit '
                                'current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY',
        'failure_condition': 'the %d branch(es) named by code %s are not the only ones conducting, the '
                             'sunk current leaves the candidate band, or a non-selected branch keeps '
                             'its local bias charged' % (conducting, code),
        'probe_orientation': PROBE_ORIENTATION, 'sign_convention': SIGN_CONVENTION,
        'paired_case': '', 'refine_only': '', 'draft_launch_units': '2', 'result': 'NOT_RUN'}


def _transient_rows():
    rows = []
    # the eight-window long pulse, in one deck
    segments, windows = [], []
    for index, code in enumerate(DC_CODES):
        start = index * (LONG_PLATFORM_TON + LONG_OFF_GAP_TON)
        stop = start + LONG_PLATFORM_TON
        segments.append('%s@%s-%s' % (code, _fmt(start), _fmt(stop)))
        windows.append((_fmt(start + LONG_EDGE_TON), _fmt(stop - LONG_EDGE_TON)))
    rows.append({
        'case_id': 'TR-LONG', 'class': 'transient',
        'purpose': 'eight long platforms in one deck, one per thermometer code, each measured inside '
                   'its own window and separated by an off window in which the code changes',
        'pam_code': '000..111', 'code': 'all eight codes, in ascending order, one platform each',
        'data_en_form': 'pwl_single_pulse_per_code', 'data_en_level_V': '1.8',
        'stimulus_start_TON': '0', 'platform_TON': _fmt(LONG_PLATFORM_TON),
        'edge_TON': _fmt(LONG_EDGE_TON), 'off_gap_TON': _fmt(LONG_OFF_GAP_TON),
        'tail_TON': _fmt(LONG_TAIL_TON),
        'window_TON': '%s; per-platform window is the platform inset by the edge time'
                      % ';'.join('%s-%s' % w for w in windows),
        'segments': ';'.join(segments), 'maxstep_ns': _fmt(MAXSTEP_WIDE_NS),
        'observe_nodes': 'iprobe current, data_out, iref_in, vcas, the eight Xdut.XuN.vbias_ch nodes, '
                         'Xdut.en0..en7 and Xdut.enb0..en7',
        'measure_interval': 'each listed platform window, integrated separately, no window straddles a '
                            'code change',
        'reference_definition': 'Iref = 15u into Mref; per-level charge compared against the estimated '
                                'unit current, never against a measured value in this round',
        'failure_condition': 'a platform whose integral does not match its code weight, a code change '
                            'landing inside a window, two adjacent windows overlapping, or a branch '
                            'conducting while its select term is off',
        'probe_orientation': PROBE_ORIENTATION, 'sign_convention': SIGN_CONVENTION,
        'paired_case': '', 'refine_only': '', 'draft_launch_units': '2', 'result': 'NOT_RUN'})
    for case_id, platform, gap, edge, tail, code, note in SHORT_CASES:
        rows.append({
            'case_id': case_id, 'class': 'transient',
            'purpose': 'short platform at the LOWEST code so the low-current short window is really '
                       'covered; %s' % note,
            'pam_code': code, 'code': '%d (pam_sel=%s, one branch)' % (int(code, 2), code),
            'data_en_form': 'pwl', 'data_en_level_V': '1.8',
            'stimulus_start_TON': _fmt(gap), 'platform_TON': _fmt(platform),
            'edge_TON': _fmt(edge), 'off_gap_TON': _fmt(gap), 'tail_TON': _fmt(tail),
            'window_TON': '%s-%s' % (_fmt(gap + edge), _fmt(gap + platform - edge)),
            'segments': '', 'maxstep_ns': _fmt(MAXSTEP_WIDE_NS),
            'observe_nodes': 'iprobe current, data_out, the selected branch local bias node, '
                             'iref_in, vcas',
            'measure_interval': 'the flat part of the platform only, between the two declared edges',
            'reference_definition': 'Iref = 15u into Mref; single-branch estimate 1.875 u '
                                    'ESTIMATED_MIRROR_RATIO_ONLY',
            'failure_condition': 'the platform collapsing before the window opens, current flowing '
                                'during the off window, or the tail failing to return to zero',
            'probe_orientation': PROBE_ORIENTATION, 'sign_convention': SIGN_CONVENTION,
            'paired_case': '', 'refine_only': '', 'draft_launch_units': '2', 'result': 'NOT_RUN'})
    case_id, platform, gap, edge, tail, _code, note = OFFCODE_CASE
    rows.append({
        'case_id': case_id, 'class': 'transient',
        'purpose': 'code changes only while the branch is off: 011 -> 100 then 000 -> 111, so the '
                   'shut-down, the local bias discharge and the next turn-on are separated; %s' % note,
        'pam_code': '011,100,000,111', 'code': '011 then 100, then 000 then 111, always inside a gap',
        'data_en_form': 'pwl', 'data_en_level_V': '1.8',
        'stimulus_start_TON': _fmt(gap), 'platform_TON': _fmt(platform),
        'edge_TON': _fmt(edge), 'off_gap_TON': _fmt(gap), 'tail_TON': _fmt(tail),
        'window_TON': '%s-%s; then %s-%s' % (_fmt(gap + edge), _fmt(gap + platform - edge),
                                             _fmt(2 * gap + platform + edge),
                                             _fmt(2 * gap + 2 * platform - edge)),
        'segments': '011@%s-%s;100@%s-%s;000@%s-%s;111@%s-%s' % (
            _fmt(gap), _fmt(gap + platform), _fmt(2 * gap + platform),
            _fmt(2 * gap + 2 * platform), _fmt(3 * gap + 2 * platform),
            _fmt(3 * gap + 3 * platform), _fmt(4 * gap + 3 * platform),
            _fmt(4 * gap + 4 * platform)),
        'maxstep_ns': _fmt(MAXSTEP_WIDE_NS),
        'observe_nodes': 'iprobe current, data_out, the eight Xdut.XuN.vbias_ch nodes, iref_in, vcas',
        'measure_interval': 'the second platform window, after one observed shut-down and discharge',
        'reference_definition': 'Iref = 15u into Mref; the discharge itself is a native quantity and '
                                'stays NOT_RUN here',
        'failure_condition': 'a code change landing inside a window, a still-charged local bias node at '
                            'the next turn-on, or current during an off window',
        'probe_orientation': PROBE_ORIENTATION, 'sign_convention': SIGN_CONVENTION,
        'paired_case': '', 'refine_only': '', 'draft_launch_units': '2', 'result': 'NOT_RUN'})
    return rows


def _refined_rows(partners):
    rows = []
    for case_id, partner in sorted(PARTNER_CONTRACT.items()):
        base = partners[partner]
        row = dict((f, base.get(f, '')) for f in PLAN_HEADER)
        row.update({'case_id': case_id, 'class': 'refined_step',
                    'purpose': 'the same stimulus as %s with only the time step refined' % partner,
                    'maxstep_ns': _fmt(MAXSTEP_FINE_NS),
                    'paired_case': partner, 'refine_only': 'time_maxstep',
                    'draft_launch_units': '2', 'result': 'NOT_RUN'})
        if case_id == 'RS-FULL':
            # the partner's eight-window schedule is copied whole: the refinement is only the time
            # step, so the last platform is measured at the fine step *with* the seven before it,
            # never by restarting the deck at the window of interest
            row['window_TON'] = base['window_TON']
            row['segments'] = base['segments']
        rows.append(row)
    return rows


def _fmt(value):
    return ('%g' % value) if isinstance(value, float) else str(value)


def cases():
    """the fifteen draft cases, in delivered order"""
    rows = [_dc_row(index, code) for index, code in enumerate(DC_CODES)]
    transients = _transient_rows()
    rows.extend(transients)
    partners = dict((r['case_id'], r) for r in transients)
    rows.extend(_refined_rows(partners))
    return rows


def windows_of(segments):
    """parse 'code@start-end;...' into the numeric platform windows it declares"""
    out = []
    for piece in [p for p in segments.split(';') if p.strip()]:
        match = re.match(r'^([01]{3})@([-\d.]+)-([-\d.]+)$', piece.strip())
        if not match:
            raise ValueError('segment %r is not code@start-end' % piece)
        out.append((match.group(1), float(match.group(2)), float(match.group(3))))
    return out


def validate_schedule(rows):
    """arithmetic over the delivered schedule; every problem is a string naming the case"""
    problems = []
    by_id = dict((r['case_id'], r) for r in rows)
    long_row = by_id.get('TR-LONG')
    if long_row is None:
        return ['TR-LONG is missing from the plan']
    declared_gap = long_row.get('off_gap_TON')
    declared_platform = long_row.get('platform_TON')
    try:
        windows = windows_of(long_row.get('segments', ''))
    except ValueError as error:
        return ['TR-LONG segments unreadable: %s' % error]
    if len(windows) != 8:
        problems.append('TR-LONG declares %d windows, the eight codes need eight' % len(windows))
    codes = [w[0] for w in windows]
    if sorted(codes) != sorted(DC_CODES):
        problems.append('TR-LONG windows carry codes %s, not the eight thermometer codes' % codes)
    for index in range(1, len(windows)):
        code, start, stop = windows[index]
        previous = windows[index - 1]
        if start < previous[2]:
            problems.append('TR-LONG window %s overlaps the window before it (%s-%s vs %s-%s)'
                            % (code, previous[1], previous[2], start, stop))
            continue
        gap = round(start - previous[2], 9)
        if _fmt(gap) != declared_gap:
            problems.append('TR-LONG gap before %s is %s TON while the table declares %s TON'
                            % (code, _fmt(gap), declared_gap))
        width = round(stop - start, 9)
        if _fmt(width) != declared_platform:
            problems.append('TR-LONG platform %s is %s TON wide while the table declares %s TON'
                            % (code, _fmt(width), declared_platform))
        if not previous[2] <= start:
            problems.append('TR-LONG changes to %s before the previous platform ended' % code)
    if windows:
        tail_after = float(long_row.get('tail_TON', 0) or 0)
        if tail_after <= 0 or windows[-1][2] + tail_after <= windows[-1][2]:
            problems.append('TR-LONG tail window %s TON does not extend past the last platform'
                            % _fmt(tail_after))
    for case_id, platform, gap, edge, tail, code, _note in SHORT_CASES:
        row = by_id.get(case_id)
        if row is None:
            problems.append('%s is missing' % case_id)
            continue
        if row.get('pam_code') != code:
            problems.append('%s carries code %s, the draft fixes the lowest code %s'
                            % (case_id, row.get('pam_code'), code))
        window = str(row.get('window_TON', '')).split('-')
        if len(window) != 2:
            problems.append('%s window %r is not one start-end pair' % (case_id, row.get('window_TON')))
            continue
        low, high = float(window[0]), float(window[1])
        start, flat = float(row.get('stimulus_start_TON', 0)), float(row.get('platform_TON', 0))
        edge_time = float(row.get('edge_TON', 0))
        if not (start + edge_time <= low < high <= start + flat - edge_time + 1e-12):
            problems.append('%s window %s-%s is not the flat part of platform %s..%s inset by %s'
                            % (case_id, window[0], window[1], start, start + flat, edge_time))
    for case_id, partner in sorted(PARTNER_CONTRACT.items()):
        refined, base = by_id.get(case_id), by_id.get(partner)
        if refined is None or base is None:
            problems.append('%s or its partner %s is missing' % (case_id, partner))
            continue
        drift = [f for f, _ in PAIR_IDENTITY_FIELDS if str(refined.get(f)) != str(base.get(f))]
        if drift:
            problems.append('%s differs from %s outside the time step: %s'
                            % (case_id, partner, ','.join(drift)))
        if str(refined.get('maxstep_ns')) == str(base.get('maxstep_ns')):
            problems.append('%s repeats the maxstep of %s, so it refines nothing' % (case_id, partner))
    dc = [r for r in rows if r.get('class') == 'dc_sweep']
    seen = sorted(str(r.get('pam_code')) for r in dc)
    if seen != sorted(DC_CODES):
        problems.append('the eight DC rows carry codes %s, not one per thermometer code' % seen)
    for row in dc:
        suffix = str(row.get('case_id', '')).split('-')[-1]
        if suffix != str(row.get('pam_code')):
            problems.append('%s names code %s in its own identifier but declares %s'
                            % (row.get('case_id'), suffix, row.get('pam_code')))
        # the human-readable code column has to be the exact restatement of the machine column, so a
        # generator cannot rewrite the prose half of a row and leave the code claiming another level
        weight = int(str(row.get('pam_code')), 2) if re.match(r'^[01]{3}$',
                                                              str(row.get('pam_code') or '')) else -1
        expected = '%d (pam_sel=%s, %d of 8 branches on)' % (weight, row.get('pam_code'),
                                                             weight + 1)
        if str(row.get('code')) != expected:
            problems.append('%s code column %r is not the expected restatement %r'
                            % (row.get('case_id'), row.get('code'), expected))
    return problems


def emit(path):
    rows = CHECK.rows_write(path, PLAN_HEADER, cases())
    return rows


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--emit', nargs='?', const=PLAN_TABLE, default='')
    parser.add_argument('--check', action='store_true')
    arguments = parser.parse_args(argv)
    rows = cases()
    problems = validate_schedule(rows)
    if arguments.emit:
        target = arguments.emit if os.path.isabs(arguments.emit) else os.path.join(ROOT,
                                                                                   arguments.emit)
        emit(target)
        print('PLAN_EMITTED %s (%d rows, %d columns)' % (target.replace(os.sep, '/'), len(rows),
                                                         len(PLAN_HEADER)))
    if arguments.check:
        absolute = os.path.join(ROOT, PLAN_TABLE.replace('/', os.sep))
        spec = dict(CHECK.input_specs()['plan'])
        delivered, table_problems = CHECK.strict_read(absolute, spec)
        schedule = validate_schedule(delivered)
        print('PLAN_CHECK delivered_rows=%d schema_refusals=%d schedule_problems=%d'
              % (len(delivered), len(table_problems), len(schedule)))
        for line in (table_problems + schedule)[:12]:
            print('  PROBLEM ' + line)
        return 1 if (table_problems or schedule) else 0
    for line in problems:
        print('  SOURCE_PROBLEM ' + line)
    print('D7C_A_R2_PLAN: %s (%d cases, schedule problems: %d)'
          % ('FAIL' if problems else 'PASS', len(rows), len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
