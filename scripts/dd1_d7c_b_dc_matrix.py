#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_dc_matrix.py -- merge the extracted rows, recompute the eight-level judgement, and draw
the two figures. Small on purpose: it reads the row files the extraction entry point wrote and does
nothing else, so a reviewer can re-run the arithmetic on the same bytes.

    python scripts/dd1_d7c_b_dc_matrix.py --merge <evidence dir>       # writes dc_matrix_dut.csv and _preflight.csv
    python scripts/dd1_d7c_b_dc_matrix.py --judge <evidence dir>       # writes judgement.json and preflight_witnesses.json
    python scripts/dd1_d7c_b_dc_matrix.py --plot <evidence dir>        # writes figures/*.png from the merged table
    python scripts/dd1_d7c_b_dc_matrix.py --check <evidence dir>       # the refusals: shape, duplicates, missing points

rc: 0 pass, 1 failure or refusal. No process is started by any mode; nothing here costs budget.
"""

from __future__ import absolute_import, print_function

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import dd1_d7b_run as B7B                                     # noqa: E402  the accepted table writer
import dd1_d7c_b_dc_run as DC                                 # noqa: E402  extraction and judgement

CASES = DC.dc_contract()['matrix']['launch_order']
CODES = DC.dc_contract()['matrix']['codes']
HEADER = DC.ROWS_HEADER


def read_rows(path):
    if not os.path.isfile(path):
        raise DC.Refuse('%s is not there; the extraction step did not run for it' % path)
    table = [line.rstrip('\n').split(',') for line in
             io.open(path, encoding='utf-8', newline='').read().split('\n') if line.strip()]
    if table[0] != list(HEADER):
        raise DC.Refuse('%s has header %s, the entry point writes %s'
                        % (os.path.basename(path), ','.join(table[0])[:60], ','.join(HEADER)[:60]))
    return [dict(zip(table[0], cells)) for cells in table[1:]]


def merged(directory, role):
    rows = []
    for case_id in CASES:
        rows.extend(read_rows(os.path.join(directory, 'rows_%s_%s.csv' % (case_id, role))))
    return rows


def check(directory):
    problems = []
    dut = merged(directory, 'dut')
    pre = merged(directory, 'preflight')
    if len(dut) != 152:
        problems.append('%d DUT rows, the matrix declares 8 codes x 19 points = 152' % len(dut))
    if len(pre) != 152:
        problems.append('%d preflight rows, the same 8 x 19 grid is expected' % len(pre))
    keys = [(row['case_id'], row['clamp_V']) for row in dut]
    if len(set(keys)) != len(keys):
        problems.append('a case and clamp point appears twice in the DUT matrix')
    for case_id in CASES:
        points = sorted(float(row['clamp_V']) for row in dut if row['case_id'] == case_id)
        if points != DC.sweep_points():
            problems.append('%s answered %d points that are not the declared 19-point grid'
                            % (case_id, len(points)))
    if any(row['role'] != 'dut' for row in dut) or any(row['role'] != 'preflight' for row in pre):
        problems.append('a role column disagrees with the file it was read from')
    if any(not row['raw_sha256'] or not row['deck_sha256'] for row in dut + pre):
        problems.append('a row carries no deck or raw digest, so its identity cannot be checked')
    if any(row['unit_clamp'] != 'V' or row['unit_current'] != 'A' for row in dut + pre):
        problems.append('a row was published without the units the native file declared')
    for row in dut:
        if row['code'] not in CODES:
            problems.append('%s: code %s is not one of the eight' % (row['case_id'], row['code']))
    pairs = set((row['code'], row['raw_sha256']) for row in dut)
    if len(pairs) != len(CASES):
        problems.append('the eight codes do not sit on eight distinct native answers (%d)'
                        % len(pairs))
    print('DC_MATRIX_CHECK: %s (%d dut rows, %d preflight rows, problems: %s)'
          % ('PASS' if not problems else 'FAIL', len(dut), len(pre),
             '; '.join(problems) if problems else 'none'))
    return 0 if not problems else 1


def merge(directory):
    for role in ('dut', 'preflight'):
        rows = merged(directory, role)
        target = os.path.join(directory, 'dc_matrix_%s.csv' % role)
        B7B.write_rows(target, [[row[key] for key in HEADER] for row in rows], list(HEADER))
        print('DC_MATRIX_MERGE %s rows=%d -> %s' % (role, len(rows), os.path.basename(target)))
    return 0


def judge(directory):
    rows = merged(directory, 'dut')
    result = DC.judge(rows)
    witnesses = {}
    for case_id in CASES:
        pre = [row for row in merged(directory, 'preflight') if row['case_id'] == case_id]
        deck_text, _digest = DC.delivered_deck(case_id)
        witnesses[case_id] = DC.preflight_witness(pre, deck_text)
    passed = all(item['load_within_tolerance'] and item['reference_within_tolerance']
                 for item in witnesses.values())
    payload = {'task_id': DC.TASK_ID, 'judged_utc': DC.now(), 'dut_rows': len(rows),
               'expected_rows': DC.dc_contract()['matrix']['rows_expected'],
               'evidence_class': 'NATIVE_MEASURED',
               'account': {'ceiling': DC.dc_contract()['authorisation']['spectre_launch_limit_total'],
                           'rows': []},
               'preflight_witnesses': witnesses,
               'all_preflight_witnesses_within_tolerance': passed,
               'judgement': result,
               'not_claimed': ['PAM and PWM joint charge', 'optical effective bits', 'layout',
                               'SOA sign-off', 'a full MOS grey-scale controller',
                               'a LUT', 'transient behaviour of any kind'],
               'time_domain_qlsb': 'NOT_APPLICABLE_DC_HAS_NO_TIME_DOMAIN'}
    account = DC.Account(os.path.join(directory, 'launch_account.csv'),
                         payload['account']['ceiling'])
    payload['account']['rows'] = [{key: row[key] for key in DC.ACCOUNT_HEADER} for row in account.rows]
    payload['account']['occupied'] = account.occupied()
    payload['account']['remaining'] = account.remaining()
    target = os.path.join(directory, 'judgement.json')
    io.open(target, 'wb').write(
        (json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
    print('DC_JUDGE %s verdict=%s full_scale_uA=%.6f iunit_ref_uA=%.6f monotonic=%s '
          'ratio_pass=%s worst_deviation=%.4f iunit_ref preflight_witnesses_all_within=%s -> %s'
          % (DC.TASK_ID, result['verdict'], result['full_scale']['measured_uA'],
             result['iunit_ref_uA'], result['strict_monotonic'], result['ratio_pass'],
             max(abs(result['per_code_deviation_in_iunit_ref'][code]) for code in CODES),
             passed, os.path.basename(target)))
    return 0 if (result['verdict'] == 'PASS' and passed) else 1


def plot(directory):
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams['svg.fonttype'] = 'none'
    import matplotlib.pyplot as plt
    rows = merged(directory, 'dut')
    figures = os.path.join(directory, 'figures')
    if not os.path.isdir(figures):
        os.makedirs(figures)
    colours = ['tab:blue', 'tab:orange', 'tab:green', 'tab:red', 'tab:purple', 'tab:brown',
               'tab:pink', 'tab:gray']
    axes = plt.subplots(figsize=(7.2, 4.8))[1]
    axes.set_xlabel('clamp voltage V')
    axes.set_ylabel('I_sink uA')
    axes.set_title('DATA-7C-B-DC  I-V per PAM code, one output channel, TT 27 C, SMIC18 models')
    for index, code in enumerate(CODES):
        case_id = 'DC-%s' % code
        points = [(float(row['clamp_V']), float(row['I_sink_uA'])) for row in rows
                  if row['case_id'] == case_id]
        points.sort()
        axes.plot([p[0] for p in points], [p[1] for p in points], marker='o', markersize=3,
                  color=colours[index], label='code %s' % code)
    axes.grid(True, alpha=0.3)
    axes.legend(fontsize=7, ncol=2)
    first = os.path.join(figures, 'dc_iv_curves.svg')
    axes.figure.savefig(first, dpi=140)
    plt.close(axes.figure)
    verdict = json.loads(io.open(os.path.join(directory, 'judgement.json'),
                                 encoding='utf-8').read())['judgement']
    axes = plt.subplots(figsize=(7.2, 4.2))[1]
    axes.bar(range(len(CODES)), [verdict['I_at_main_A_by_code'][code] * 1e6 for code in CODES],
             color=colours)
    axes.set_xticks(range(len(CODES)))
    axes.set_xticklabels(CODES)
    axes.set_xlabel('PAM code (000 is the lowest non-zero level)')
    axes.set_ylabel('I_sink at 1.20 V, uA')
    axes.set_title('measured eight-level ladder at the 1.20 V evaluation point')
    for index, code in enumerate(CODES):
        axes.annotate('%.3f' % (verdict['I_at_main_A_by_code'][code] * 1e6),
                      (index, verdict['I_at_main_A_by_code'][code] * 1e6), ha='center',
                      va='bottom', fontsize=7)
    axes.grid(True, axis='y', alpha=0.3)
    second = os.path.join(figures, 'dc_ladder_at_1p20V.svg')
    axes.figure.savefig(second, dpi=140)
    plt.close(axes.figure)
    print('DC_PLOT two figures from the merged native table: %s (%d bytes), %s (%d bytes)'
          % (os.path.basename(first), os.path.getsize(first), os.path.basename(second),
             os.path.getsize(second)))
    return 0


REQUESTED_SAVES = (['vdd18', 'vss', 'iref_in', 'vcas', 'data_out', 'clamp_node', 'irefbus',
                   'data_en', 'pam0', 'pam1', 'pam2'] + ['Xdut.en%d' % index for index in range(8)]
                  + ['Xdut.enb%d' % index for index in range(8)]
                  + ['Xdut.Xu%d.vbias_ch' % index for index in range(8)]
                  + ['Xdut.Xu0.node_m', 'Xdut.Xu4.node_m', 'Ip_branch', 'Ip_branch:current'])
REQUIRED_SIGNALS = ('data_out', 'clamp_node', 'vdd18', 'vcas', 'data_en', 'pam0', 'pam1', 'pam2',
                    'iref_in')


def observe(directory):
    """what the build actually delivered per case, so an optional internal observation that came back
    under another name is stated instead of quietly assumed away"""
    import sc1_read_psf as PSF
    report = {'task_id': DC.TASK_ID, 'written_utc': DC.now(),
              'rule': 'the deck asks for these signals; a name the answer does not carry is '
                      'NOT_OBSERVED under that name, and the required set is never optional',
              'cases': {}}
    missing_required = []
    for case_id in CASES:
        raw = os.path.join(directory, 'r20261026_015212_376554_%s_dut.raw' % case_id)
        if not os.path.isfile(raw):
            report['cases'][case_id] = {'state': 'NO_RAW_ON_THIS_MACHINE'}
            continue
        groups, axis = PSF.parse(raw)
        columns, _axis_values = PSF.as_columns(groups, axis)
        delivered = sorted(columns)
        absent = [name for name in REQUESTED_SAVES if name not in columns]
        extra = [name for name in delivered if name not in REQUESTED_SAVES and name != axis]
        report['cases'][case_id] = {'axis': axis, 'delivered': len(delivered),
                                   'requested_but_not_delivered': absent,
                                   'delivered_under_other_names': extra,
                                   'required_present': all(name in columns for name in
                                                           REQUIRED_SIGNALS)}
        if not all(name in columns for name in REQUIRED_SIGNALS):
            missing_required.append(case_id)
    report['verdict'] = ('PASS' if not missing_required else 'FAIL')
    report['required_signals_missing_in'] = missing_required
    report['not_observed_overall'] = sorted(set(sum([report['cases'][case].get(
        'requested_but_not_delivered', []) for case in CASES], [])))
    target = os.path.join(directory, 'observed_signals.json')
    io.open(target, 'wb').write((json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + chr(10)).encode('utf-8'))
    print('DC_OBSERVE %s cases=%d not_observed=%s required_missing=%s -> %s'
          % (report['verdict'], len(CASES), ','.join(report['not_observed_overall']) or 'none',
             ','.join(missing_required) or 'none', os.path.basename(target)))
    return 0 if not missing_required else 1


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('merge', 'judge', 'plot', 'check', 'observe'))
    parser.add_argument('directory')
    arguments = parser.parse_args(argv)
    directory = os.path.abspath(arguments.directory)
    try:
        return {'merge': merge, 'judge': judge, 'plot': plot, 'check': check,
                'observe': observe}[arguments.mode](directory)
    except DC.Refuse as error:
        print('DC_MATRIX_REFUSED %s' % error)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
