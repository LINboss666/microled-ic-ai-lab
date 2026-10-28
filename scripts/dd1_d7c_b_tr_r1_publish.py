#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR-R1 publish: re-extract the tables from the stored answers with the patched tools,
judge them again, and publish what this round adds beside the sequences it exported.

Offline only: the answers were pulled by the native round and are read from where they live. No
simulator is started, nothing of the native round is rewritten, and every number published here is
re-derived from the same samples the independent recomputer reads.
"""

import csv
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7c_b_tr_contract as TRC
import dd1_d7c_b_tr_measure as MEAS
import dd1_d7c_b_tr_record as REC
import dd1_d7c_b_tr_run as RUN
import dd1_d7c_b_tr_trace as TRACE
import dd1_d7c_b_tr_r1_native as NAT

TASK_ID = TRC.TASK_ID
RECOMPUTE = os.path.join(HERE, 'dd1_d7c_b_tr_r1_recompute.py')
DIFF_HEADER = ('case_id', 'window_id', 'cell', 'native_value', 'r1_value', 'kind_of_change',
               'reason')
NEW_STATUS_ORDER = ('NATIVE_SEQUENCE_REINTEGRATION', 'RTL_INPUT_PROVENANCE',
                    'BUDGET_ACCOUNTING_STATUS')


Refuse = TRC.Refuse


def reconvert(vcd_dir, out_dir, native_dir):
    """re-read the two stored traces with the patched converter and answer against the delivered deck"""
    made_by_case = {}
    records = []
    for case_id in TRACE.CASES:
        dump = os.path.join(vcd_dir, TRACE.dump_name(case_id))
        if not os.path.isfile(dump):
            records.append({'case_id': case_id, 'reconverted': False,
                            'reason': 'the trace of that start is not on this machine'})
            continue
        deck = RUN.deck_for(case_id, 'dut')
        made = TRACE.reconvert(case_id, dump, deck)
        windows = TRACE.measurement_windows(made)
        payload = {'case_id': case_id, 'vcd': os.path.basename(dump),
                   'vcd_sha256': made['vcd_sha256'], 'frame_count': made['frame_count'],
                   'deck_comparison': made['deck_comparison'],
                   'deck_problems': made['deck_problems'],
                   'endpoints': [{'frame': row['frame'], 'kind': row['kind'],
                                  't0_ps': row['t0_ps'],
                                  'enable_rises_ps': row['enable_rises_ps'],
                                  'enable_falls_ps': row['enable_falls_ps'],
                                  'expected_intervals': row['expected_intervals'],
                                  'tick_lead_ps': row['tick_lead_ps'],
                                  'fault_rise_ps': row['fault_rise_ps'],
                                  'fault_fall_ps': row['fault_fall_ps'],
                                  'pwm_start_rise_ps': row['pwm_start_rise_ps'],
                                  'tick_rises_after_withdrawal':
                                      [t for t in row['tick_rise_ps']
                                       if row['fault_fall_ps'] and t > row['fault_fall_ps']]}
                                 for row in made['frames']],
                   'black_windows': windows,
                   'stop_ns': made['stop_ns'], 'shift_ns': made['shift_ns'],
                   'edge_total_ns': made['edge_total_ns'],
                   'source': 'SYNTHETIC_NOT_MEASURED' if 'fixture' in dump else 'MEASURED_TRACE',
                   'not_a_claim': made['not_a_claim']}
        REC._dump(os.path.join(out_dir, 'reconversion_%s.json' % case_id), payload)
        made_by_case[case_id] = payload
        records.append({'case_id': case_id, 'reconverted': True, 'vcd_sha256': made['vcd_sha256'],
                        'deck_sha256': made['deck_comparison']['deck_sha256'],
                        'deck_problems': made['deck_problems'], 'frames': made['frame_count'],
                        'black_windows': len(windows)})
    REC._dump(os.path.join(out_dir, 'reconversion_summary.json'),
              {'runs': records, 'native_evidence': os.path.basename(native_dir),
               'note': 'the converter re-read the trace bytes whose digest the native round recorded '
                       'and the four PWL sources of the delivered run copy, without starting vvp'})
    return made_by_case, records


def extract(local_dir, native_dir, out_dir, made_by_case):
    """every published row of every case, re-derived from the stored answer it names"""
    rows, witnesses = NAT.identity_rows(native_dir)
    written, all_rows = [], []
    for case_id in TRC.CASE_ORDER:
        named = [row for row in rows if row['case_id'] == case_id and row['role'] == 'dut']
        if len(named) != 1:
            raise Refuse('%s: the native account holds %d confirmed dut starts for this case'
                         % (case_id, len(named)))
        row = named[0]
        raw = os.path.join(local_dir, row['raw_name'])
        if not os.path.isfile(raw):
            raise Refuse('%s: the answer of launch %s is not on this machine, so nothing can be '
                         're-extracted' % (case_id, row['launch_id']))
        if NAT.sha_of(raw) != row['raw_sha256']:
            raise Refuse('%s: the stored answer no longer matches ledger row %s'
                         % (case_id, row['launch_id']))
        deck = RUN.deck_for(case_id, 'dut')
        if REC.sha_of(deck) != row['deck_sha256']:
            raise Refuse('%s: the delivered run copy is %s while launch %s charged %s'
                         % (case_id, REC.sha_of(deck)[:12], row['launch_id'],
                            row['deck_sha256'][:12]))
        meta = {'case_id': case_id, 'role': 'dut', 'run_id': row['run_id'],
                'launch_id': row['launch_id'], 'raw_sha256': row['raw_sha256'],
                'deck_sha256': row['deck_sha256']}
        extra = tuple((made_by_case.get(case_id) or {}).get('black_windows', ()))
        made, data = MEAS.measure_case(case_id, raw, io.open(deck, encoding='utf-8',
                                                            newline='').read(), meta,
                                       extra_windows=extra)
        path = os.path.join(out_dir, 'rows_%s_%s.csv' % (case_id, 'dut'))
        MEAS.write_rows(path, made, MEAS.HEADER)
        REC._dump(os.path.join(out_dir, 'iprobe_consistency_%s_dut.json' % case_id),
                  MEAS.iprobe_consistency(data, case_id))
        deck_text = io.open(deck, encoding='utf-8', newline='').read()
        REC._dump(os.path.join(out_dir, 'internal_nodes_%s_dut.json' % case_id),
                  MEAS.internal_nodes(data, MEAS.windows_of(case_id, deck_text),
                                      MEAS.codes_of(case_id, deck_text)))
        written.append({'case_id': case_id, 'file': os.path.basename(path), 'rows': len(made)})
        all_rows.extend(made)
    return written, all_rows


def diff_tables(native_dir, out_dir):
    """every cell that moved between the native table and this re-extraction, with its reason"""
    def read(path):
        with io.open(path, encoding='utf-8', newline='') as handle:
            return dict(((row['case_id'], row['window_id']), row)
                        for row in csv.DictReader(handle))

    before = read(os.path.join(native_dir, 'windows_all.csv'))
    after = read(os.path.join(out_dir, 'windows_all.csv'))
    changes, added_columns = [], []
    new_cells = [name for name in MEAS.HEADER if name not in before[list(before)[0]]]
    missing = [key for key in before if key not in after] + [key for key in after
                                                             if key not in before]
    if missing:
        raise Refuse('the re-extraction does not cover the same 37 window keys: %s'
                     % ','.join('%s %s' % key for key in missing))
    for key in sorted(before):
        for cell in MEAS.HEADER:
            old = before[key].get(cell, '')
            new = after[key].get(cell, '')
            if cell in new_cells:
                added_columns.append(cell)
                changes.append(dict(zip(DIFF_HEADER[:2], key),
                                      **{'cell': cell, 'native_value': '', 'r1_value': new,
                                         'kind_of_change': 'ADDED_COLUMN',
                                         'reason': 'the two settling targets are now published as '
                                                   'their own columns'}))
            elif str(old) != str(new):
                changes.append(dict(zip(DIFF_HEADER[:2], key),
                                      **{'cell': cell, 'native_value': old, 'r1_value': new,
                                         'kind_of_change': 'VALUE',
                                         'reason': 're-extracted from the same answer with the '
                                                   'patched importer and window derivation'}))
    MEAS.write_rows(os.path.join(out_dir, 'window_diff_r1.csv'), changes, DIFF_HEADER)
    REC._dump(os.path.join(out_dir, 'window_diff_r1.json'),
              {'changed_cells': len(changes), 'added_columns': sorted(set(added_columns)),
               'keys_compared': len(before), 'same_value_cells':
                   len(before) * len(MEAS.HEADER) - len(changes),
               'note': 'a negative electrical finding stays published as itself: this table is the '
                       'only place a number may move, and every move names its reason'})
    return changes


def run_recompute(out_dir, preflight):
    argv = [sys.executable, RECOMPUTE, ROOT] + (['--preflight'] if preflight else [])
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = process.stdout.read().decode('utf-8', 'replace')
    process.wait()
    lines = text.splitlines()
    summary = [line for line in lines if line.startswith('RECOMPUTE_R1 ')]
    failed = [line for line in lines if line.startswith('RECOMPUTE_R1_FAIL')
              or line.startswith('RECOMPUTE_R1_REFUSED')]
    return {'rc': process.returncode, 'summary': summary[0] if summary else '',
            'refused': text.splitlines()[0] if text.startswith('RECOMPUTE_R1_REFUSED') else '',
            'failures': failed, 'lines': len([line for line in lines if line[:4] in ('PASS',
                                                                                    'FAIL')]),
            'preflight': preflight}


def statuses(out_dir, native_dir, sequence, provenance, budget, note_extra):
    rows = REC.all_rows(out_dir)
    conv, _pairs, _problems = REC.convergence_table(out_dir)
    table = MEAS.statuses(rows, conv, REC.integrity(native_dir), REC.completeness(native_dir))
    for row in table:
        row['note'] = '%s; the seven verdicts are judged on the rows re-extracted by this round and ' \
                      'the integrity and completeness figures are the native record\'s own' \
                      % row['note'] if row['status'] in ('EVIDENCE_INTEGRITY',
                                                         'EXECUTION_COMPLETENESS') else row['note']
    table.append({'status': 'NATIVE_SEQUENCE_REINTEGRATION', 'verdict': sequence['verdict'],
                  'measured': sequence['measured'], 'expected': sequence['expected'],
                  'note': sequence['note']})
    table.append({'status': 'RTL_INPUT_PROVENANCE', 'verdict': provenance['verdict'],
                  'measured': provenance['measured'], 'expected': provenance['expected'],
                  'note': provenance['note']})
    table.append({'status': 'BUDGET_ACCOUNTING_STATUS', 'verdict': budget['verdict'],
                  'measured': budget['measured'], 'expected': budget['expected'],
                  'note': budget['note'] + ' ' + note_extra})
    MEAS.write_rows(os.path.join(out_dir, 'statuses.csv'), table, MEAS.STATUS_HEADER)
    return table


def budget_accounting(native_dir):
    """the three budget numbers, stated apart instead of merged into one claim"""
    spectre, rtl = REC.ledgers(native_dir)
    strays = json.loads(io.open(os.path.join(native_dir, 'spectre_budget_adjustments.json'),
                                encoding='utf-8').read())
    stray_processes = sum(int(row['processes']) for row in strays['adjustments'])
    task_total = TRC.SPECTRE_LIMIT
    main_ceiling = task_total - stray_processes
    occupied = len(spectre)
    reconciliation = REC.rtl_reconciliation(native_dir)
    evidence = [row for row in rtl if row.get('exe_sha256') and row.get('rc')]
    distinct = sorted(set(row['exe_sha256'] for row in evidence))
    proven = len(distinct) == len(evidence) and len(distinct) <= TRC.RTL_LIMIT
    return {'task_total': task_total, 'main_ledger_ceiling': main_ceiling,
            'main_ledger_rows': occupied, 'recorded_stray_processes': stray_processes,
            'total_occupied': occupied + stray_processes,
            'remaining_before_next_stage': task_total - occupied - stray_processes,
            'rtl_rows': len(rtl), 'rtl_rows_with_process_evidence': len(evidence),
            'rtl_distinct_executables': len(distinct),
            'rtl_process_count': len(distinct) if proven else 'NOT_INDEPENDENTLY_PROVEN',
            'rtl_reconciliation_problems': reconciliation['problems'],
            'rtl_reconciliation_processes': reconciliation['processes'],
            'uncertain_rows': [row['launch_id'] for row in spectre if row['state'] == 'UNCERTAIN'],
            'claim_limit': 'the 19 booked rows are not 19 independently proven starts; T001 stays '
                           'charged as UNCERTAIN and the two escaped processes are charged as '
                           'recorded strays'}


def publish(local_dir, native_dir, out_dir, vcd_dir):
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    made_by_case, records = reconvert(vcd_dir, out_dir, native_dir)
    written, rows = extract(local_dir, native_dir, out_dir, made_by_case)
    _rows, conv, pairs, problems, delta, internals, files = REC.publish(
        out_dir, raw_dir=local_dir, trace_delivery=False)
    changes = diff_tables(native_dir, out_dir)
    preflight = run_recompute(out_dir, True)
    counts = preflight['summary'].split()[-1] if preflight['summary'] else '0/0'
    done, total = counts.split('/')
    sequence = {'verdict': 'PASS' if preflight['rc'] == 0 else 'PARTIAL',
                'measured': int(done), 'expected': int(total),
                'note': 'the standalone recomputer re-integrated every published window from the '
                        'exported native samples and re-derived both charge columns'}
    reconverted = [item for item in records if item.get('reconverted')]
    clean = reconverted and not any(item['deck_problems'] for item in reconverted)
    provenance = {'verdict': 'PASS' if clean and len(reconverted) == 2 else 'PARTIAL',
                  'measured': len(reconverted), 'expected': len(TRACE.CASES),
                  'note': 'both stored traces were re-read with the patched converter and answer '
                          'against the four PWL sources of the delivered run copy'
                          if clean else 'the traces or their deck agreement are incomplete'}
    budget = budget_accounting(native_dir)
    budget_status = {'verdict': 'PASS' if budget['total_occupied'] <= budget['task_total']
                     and budget['main_ledger_rows'] <= budget['main_ledger_ceiling']
                     and budget['rtl_process_count'] != 'NOT_INDEPENDENTLY_PROVEN' else 'PARTIAL',
                    'measured': budget['total_occupied'], 'expected': budget['task_total'],
                    'note': 'the approved task allows %d Spectre processes, the main ledger is '
                            'enforced at %d after the %d recorded stray processes, and the %d '
                            'booked rows plus those strays occupy %d of %d; RTL starts are counted '
                            'by the %d distinct executable digests on their own rows'
                            % (budget['task_total'], budget['main_ledger_ceiling'],
                               budget['recorded_stray_processes'], budget['main_ledger_rows'],
                               budget['total_occupied'], budget['task_total'],
                               budget['rtl_distinct_executables'])}
    table = statuses(out_dir, native_dir, sequence, provenance, budget_status, '')
    gate = run_recompute(out_dir, False)
    REC._dump(os.path.join(out_dir, 'recompute_r1.json'),
              {'preflight': preflight, 'delivery_gate': gate, 'budget_accounting': budget,
               'statuses': [dict((key, row[key]) for key in MEAS.STATUS_HEADER) for row in table],
               'native_evidence': os.path.basename(native_dir),
               'shipped_by': 'scripts/dd1_d7c_b_tr_r1_recompute.py'})
    REC._dump(os.path.join(out_dir, 'publish_summary.json'),
              {'task_id': TASK_ID, 'extracted': written, 'reconversion': records,
               'diff_cells': len(changes), 'diff_added_columns': sorted(set(
                   item['cell'] for item in changes if item['kind_of_change'] == 'ADDED_COLUMN')),
               'published_tables': sorted(files), 'convergence_pairs': len(pairs),
               'convergence_context_problems': problems, 'delay_rows': len(delta),
               'internal_node_rows': len(internals),
               'gate': {'rc': gate['rc'], 'summary': gate['summary'],
                        'failures': gate['failures'][:8],
                        'refused': gate['refused']},
               'simulator_launches': 0, 'guest_connections': 0, 'oa_access': 0})
    return table, gate, budget


def restatus(local_dir, native_dir, out_dir):
    """re-judge and re-gate the tables that are already published, without re-reading the answers"""
    changes = diff_tables(native_dir, out_dir)
    preflight = run_recompute(out_dir, True)
    counts = preflight['summary'].split()[-1] if preflight['summary'] else '0/0'
    done, total = counts.split('/')
    sequence = {'verdict': 'PASS' if preflight['rc'] == 0 else 'PARTIAL',
                'measured': int(done), 'expected': int(total),
                'note': 'the standalone recomputer re-integrated every published window from the '
                        'exported native samples and re-derived both charge columns'}
    records = json.loads(io.open(os.path.join(out_dir, 'reconversion_summary.json'),
                                 encoding='utf-8').read())['runs']
    reconverted = [item for item in records if item.get('reconverted')]
    clean = reconverted and not any(item['deck_problems'] for item in reconverted)
    provenance = {'verdict': 'PASS' if clean and len(reconverted) == 2 else 'PARTIAL',
                  'measured': len(reconverted), 'expected': len(TRACE.CASES),
                  'note': 'both stored traces were re-read with the patched converter and answer '
                          'against the four PWL sources of the delivered run copy'
                          if clean else 'the traces or their deck agreement are incomplete'}
    budget = budget_accounting(native_dir)
    budget_status = {'verdict': 'PASS' if budget['total_occupied'] <= budget['task_total']
                     and budget['main_ledger_rows'] <= budget['main_ledger_ceiling']
                     and budget['rtl_process_count'] != 'NOT_INDEPENDENTLY_PROVEN' else 'PARTIAL',
                     'measured': budget['total_occupied'], 'expected': budget['task_total'],
                     'note': 'the approved task allows %d Spectre processes, the main ledger is '
                             'enforced at %d after the %d recorded stray processes, and the %d '
                             'booked rows plus those strays occupy %d of %d; RTL starts are counted '
                             'by the %d distinct executable digests on their own rows, never by '
                             'subtracting one from a row count'
                             % (budget['task_total'], budget['main_ledger_ceiling'],
                                budget['recorded_stray_processes'], budget['main_ledger_rows'],
                                budget['total_occupied'], budget['task_total'],
                                budget['rtl_distinct_executables'])}
    table = statuses(out_dir, native_dir, sequence, provenance, budget_status, '')
    gate = run_recompute(out_dir, False)
    REC._dump(os.path.join(out_dir, 'recompute_r1.json'),
              {'preflight': preflight, 'delivery_gate': gate, 'budget_accounting': budget,
               'statuses': [dict((key, row[key]) for key in MEAS.STATUS_HEADER) for row in table],
               'native_evidence': os.path.basename(native_dir),
               'shipped_by': 'scripts/dd1_d7c_b_tr_r1_recompute.py'})
    return table, gate, budget, changes


def main(argv):
    if argv and argv[0] == '--restatus':
        table, gate, budget, changes = restatus(argv[1], argv[2], argv[3])
        for row in table:
            print('TR_R1_STATUS %-32s %-8s %s/%s' % (row['status'], row['verdict'],
                                                     row['measured'], row['expected']))
        print('TR_R1_GATE rc=%s %s rtl_process_count=%s diff_cells=%d'
              % (gate['rc'], gate['summary'], budget['rtl_process_count'], len(changes)))
        for line in gate['failures'][:10]:
            print('TR_R1_GATE_%s' % line.replace('RECOMPUTE_R1_', ''))
        return 0 if gate['rc'] == 0 else 1
    if not argv or argv[0] != '--publish':
        print('usage: --publish <local_answer_dir> <native_evidence_dir> <out_dir> <vcd_dir> '
              '| --restatus <local_answer_dir> <native_evidence_dir> <out_dir>')
        return 2
    table, gate, budget = publish(argv[1], argv[2], argv[3], argv[4])
    for row in table:
        print('TR_R1_STATUS %-32s %-8s %s/%s' % (row['status'], row['verdict'], row['measured'],
                                                 row['expected']))
    print('TR_R1_GATE rc=%s %s rtl_process_count=%s' % (gate['rc'], gate['summary'],
                                                       budget['rtl_process_count']))
    for line in gate['failures'][:10]:
        print('TR_R1_GATE_%s' % line.replace('RECOMPUTE_R1_', ''))
    return 0 if gate['rc'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
