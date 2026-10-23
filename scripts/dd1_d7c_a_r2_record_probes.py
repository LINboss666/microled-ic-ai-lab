#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_r2_record_probes.py -- negative tests for the record-semantics layer itself.

R1 published a record whose final read-back only checked shape, so a row reading
`rc=99, expected_rc=0, verdict_state=PASS` was accepted and a missing mandatory gate was invisible.
This module builds ONE small but completely self-consistent record in a temporary directory, proves
the semantic layer accepts it (a positive control, otherwise every refusal below could be an artifact
of a broken fixture), and then applies one semantic tamper at a time and requires the named refusal
that the tamper deserves.

Nothing here touches the repository: the fixture lives under tempfile.mkdtemp, no published record is
read or rewritten, and no simulator, VM, credential or network is involved.

    python scripts/dd1_d7c_a_r2_record_probes.py
"""

from __future__ import absolute_import, division, print_function

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dd1_d7c_a_offline_check as CHECK      # noqa: E402
import dd1_d7c_a_r2_record_check as RECORD   # noqa: E402

BASE_FILES = ['spectre/dd1_d7c_a_pam_top.scs', 'tests/dd1_d7c_a/pam_mask_golden.csv']
# every mandatory gate, with the numbers a passing round would publish
GATE_ROWS = [
    ('reviewer_instrument_on_T', 0, '0', 'PASS', 'all eight reviewed defects reproduce on the tip'),
    ('reviewer_instrument_on_fixed_bytes', 1, '1', 'PASS', 'each of the eight is now refused by name'),
    ('offline_checks', 0, '0', 'PASS', 'D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none)'),
    ('counterexamples', 0, '0', 'PASS', 'D7C_A_GUARDS: PASS (41/41 named exactly; not hit: none)'),
    ('record_tool_selftest', 0, '0', 'PASS', 'cases=9 verdict=PASS failures=none'),
    ('fresh_extraction_replay', 0, '0', 'PASS', 'offline rc=0 guards rc=0 validator rc=0 selftest 0'),
    ('handoff_structure', 0, '0', 'PASS', 'D7C_A_HANDOFF_CHECK: PASS (0 problems)'),
    ('native_entry_refused', 0, '0', 'PASS', 'refused in all four environments, nothing written'),
    ('provenance', 0, '0', 'PASS', 'SOURCE_PROVENANCE_CHECK: PASS'),
    ('history_safety', 0, '0', 'PASS', 'SAFETY_GATE: PASS'),
    ('netlist_stats_scope_limit', '1/1', 'INFORMATIONAL: single-cell scope, not a PASS',
     'INFORMATIONAL_NOT_PASS', 'the frozen tool compares one cell total and already fails at base'),
    ('frozen_surfaces', 0, '0', 'PASS', 'enforced rows 24, violations none; git diff --check all 0'),
    ('record_line_endings', 0, '0', 'PASS', 'published files still carrying CR: none'),
    ('render_fixed_point', 1, 'last pass stable with both gates rc=0', 'PASS',
     'passes [{attempt: 1, reports_stable: True}]'),
    ('record_semantics', 0, '0', 'PASS', 'rules over the published tables and sub-results'),
]
FROZEN_ROWS = [
    {'comparison': 'B_tracked_paths', 'surface': 'every_B_tracked_path', 'paths_compared': 2533,
     'mismatched': 0, 'first_mismatches': '-', 'expectation': 'identical', 'enforced': 'yes'},
    {'comparison': 'H_frozen_surfaces', 'surface': 'four_candidate_DUT_netlists',
     'paths_compared': 4, 'mismatched': 0, 'first_mismatches': '-', 'expectation': 'identical',
     'enforced': 'yes'},
    {'comparison': 'H_to_tip_whitelist', 'surface': 'whitelisted_paths_edited', 'paths_compared': 12,
     'mismatched': 9, 'first_mismatches': 'scripts/x.py', 'expectation': 'editable',
     'enforced': 'no'},
]
GIT_ROWS = [
    {'gate': 'diff_check_H_to_HEAD', 'command': 'git diff --check %s..HEAD' % RECORD.BASE_SHA,
     'rc': 0, 'lines': 'see rc', 'scope': 'this round adds'},
    {'gate': 'diff_check_T_to_HEAD', 'command': 'git diff --check 89b3dd8e244eaf14bd3bdb7d93b4c7'
     '71a28fbb79..HEAD', 'rc': 0, 'lines': 'see rc', 'scope': 'both repair rounds'},
    {'gate': 'diff_check_B_to_HEAD', 'command': 'git diff --check 272d6de6d2f2fc8a82d5038d73d6b3'
     'e4c656f683..HEAD', 'rc': 0, 'lines': 'see rc', 'scope': 'from the development base'},
]


def instrument_payload(reproduced, named):
    cases = []
    for index in range(8):
        cases.append({'case': 'fault_%d' % index, 'sha256_before': 'b%d' % index,
                      'sha256_after': 'a%d' % index,
                      'defect_reproduced': reproduced,
                      'failures': ['SOME_CHECK'] if named else []})
    return {'baseline_checks': 34, 'baseline_failures': [], 'cases': cases,
            'all_defects_reproduced': reproduced}


def build_record(directory):
    """write the fixture: gate rows, tables, sub-results and the summary, all agreeing"""
    os.makedirs(directory)
    # GATE_ROWS carries (gate, rc, expected_rc, verdict_state, verdict); the command text is derived
    # so the fixture cannot disagree with itself about what was run
    commands = [{'gate': gate, 'command': 'python scripts/dd1_d7c_a_offline_check.py' if gate ==
                 'offline_checks' else 'fixture command for %s' % gate, 'rc': rc,
                 'expected_rc': expected, 'verdict_state': state, 'verdict': verdict}
                for gate, rc, expected, state, verdict in GATE_ROWS]
    CHECK.rows_write(os.path.join(directory, 'commands.csv'), RECORD.COMMANDS_HEADER, commands)
    CHECK.rows_write(os.path.join(directory, 'frozen_comparison.csv'), RECORD.FROZEN_HEADER,
                     FROZEN_ROWS)
    CHECK.rows_write(os.path.join(directory, 'git_checks.csv'), RECORD.GIT_HEADER, GIT_ROWS)
    identity = []
    for rel in BASE_FILES:
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        identity.append({'role': 'delivered', 'path': rel, 'bytes': os.path.getsize(path),
                         'sha256': CHECK.sha_file(path)})
    CHECK.rows_write(os.path.join(directory, 'source_identity.csv'), RECORD.IDENTITY_HEADER,
                     identity)
    checks = [{'check': 'CHECK_%02d' % index, 'result': 'PASS', 'reason': 'fixture'}
              for index in range(34)]
    _json(os.path.join(directory, 'offline_checks.json'), {'checks': checks, 'failures': []})
    _json(os.path.join(directory, 'counterexamples.json'),
          {'baseline_failures': [],
           'injections': ([{'injection': 'E%02d' % index, 'verdict': 'HIT',
                            'expected': ['SOME_CHECK'], 'found': ['SOME_CHECK']}
                           for index in range(1, 42)] +
                          [{'injection': 'S%d_synthetic' % index, 'verdict': 'HIT',
                            'expected': ['SYNTHETIC_SIGN'], 'found': [],
                            'evidence_class': 'SYNTHETIC_NOT_MEASURED'}
                           for index in range(1, 8)])})
    _json(os.path.join(directory, 'selftest.json'),
          {'cases': 9, 'failures': [], 'verdict': 'PASS',
           'results': [{'case': 'c%d' % index, 'state': 'PASS'} for index in range(9)]})
    _json(os.path.join(directory, 'instrument_T.json'), instrument_payload(True, False))
    _json(os.path.join(directory, 'instrument_fixed.json'), instrument_payload(False, True))
    _json(os.path.join(directory, 'verification_summary.json'),
          {'gates': len(commands), 'gates_failed': [],
           'gates_informational': ['netlist_stats_scope_limit'],
           'csv_read_back': [{'file': 'commands.csv', 'result': 'columns and keys verified',
                              'rows': len(commands)}],
           'published_files_with_cr': [], 'frozen_rows_enforced': len(FROZEN_ROWS) - 1,
           'frozen_enforced_mismatches': 0, 'paths_added_after_T': 1, 'native_launches': 0,
           'rtl_simulations': 0, 'oa_writes': 0, 'verdict':
               'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES'})
    return directory


def _json(path, payload):
    with io.open(path, 'wb') as handle:
        handle.write((json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))


def _read(directory, name, header, key):
    return CHECK.read_table(os.path.join(directory, name), header, key,
                            optional=('first_mismatches',))


def _edit(directory, name, header, key, mutate):
    rows = _read(directory, name, header, key)
    mutate(rows)
    CHECK.rows_write(os.path.join(directory, name), header, rows)


TAMPERS = [
    ('R1_rc99_marked_PASS', 'a row whose rc contradicts its own expected_rc cannot read PASS',
     lambda d: _edit(d, 'commands.csv', RECORD.COMMANDS_HEADER, 'gate', lambda rows: rows[2].update(
         {'rc': '99', 'verdict_state': 'PASS'})),
     'declares PASS with rc different from its numeric expectation'),
    ('R2_mandatory_gate_absent', 'dropping a gate has to be visible, not just a smaller count',
     lambda d: _edit(d, 'commands.csv', RECORD.COMMANDS_HEADER, 'gate', lambda rows: rows.pop(
         [i for i, r in enumerate(rows) if r['gate'] == 'provenance'][0])),
     'mandatory gate(s) absent from commands.csv'),
    ('R3_invented_status_word', 'a verdict outside the declared enum is refused',
     lambda d: _edit(d, 'commands.csv', RECORD.COMMANDS_HEADER, 'gate', lambda rows: rows[7].update(
         {'verdict_state': 'LOOKED_FINE'})),
     'not one of the allowed verdict states'),
    ('R4_summary_passes_a_failed_gate', 'a sub-check failure cannot be washed by the summary line',
     lambda d: (wash_failure_as_pass(d)),
     'the summary says'),
    ('R5_stale_digest_in_identity', 'the record may not quote bytes that are no longer there',
     lambda d: _edit(d, 'source_identity.csv', RECORD.IDENTITY_HEADER, 'path', lambda rows:
                     rows[0].update({'sha256': '0' * 64})),
     'digest on disk is'),
    ('R6_identity_names_an_absent_file', 'a path that does not exist is not a delivered file',
     lambda d: _edit(d, 'source_identity.csv', RECORD.IDENTITY_HEADER, 'path', lambda rows:
                     rows[1].update({'path': 'spectre/never_delivered.scs'})),
     'which is not on disk'),
    ('R7_enforced_row_with_a_violation', 'the frozen gate has to agree with the enforced rows',
     lambda d: _edit(d, 'frozen_comparison.csv', RECORD.FROZEN_HEADER, 'surface', lambda rows:
                     rows[1].update({'mismatched': 3, 'first_mismatches': 'spectre/x.scs'})),
     'enforced frozen rows with a non-zero count'),
    ('R8_counterexample_never_hit', 'a HIT label over a MISS row is refused',
     lambda d: _rewrite_json(d, 'counterexamples.json', lambda payload: payload['injections'][3].update(
         {'verdict': 'MISS'})),
     'probes that did not hit'),
    ('R9_empty_expectation_set', 'an injection with no expected failure can never detect anything',
     lambda d: _rewrite_json(d, 'counterexamples.json', lambda payload: payload['injections'][5].update(
         {'expected': [], 'found': []})),
     'declare an empty expectation set'),
    ('R10_selftest_refusal_reported_as_pass', 'NOT_RUN for want of Git history is not nine passes',
     lambda d: (_rewrite_json(d, 'selftest.json', lambda payload: payload.update(
         {'verdict': 'NOT_RUN', 'cases': 0, 'failures': ['GIT_HISTORY_UNAVAILABLE']})),
        _edit(d, 'commands.csv', RECORD.COMMANDS_HEADER, 'gate', lambda rows: rows[4].update(
            {'verdict_state': 'PASS', 'verdict': 'cases=0 verdict=NOT_RUN failures=none',
             'rc': 0, 'expected_rc': '0'}))),
     'for want of Git history'),
    ('R11_offline_failures_but_gate_pass', 'the gate text listing failures contradicts its PASS',
     lambda d: _edit(d, 'commands.csv', RECORD.COMMANDS_HEADER, 'gate', lambda rows: rows[2].update(
         {'verdict': 'D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: CHECK_07)'})),
     'lists failures'),
    ('R12_instrument_case_unchanged_bytes', 'a diagnosis that changed no bytes proves nothing',
     lambda d: _rewrite_json(d, 'instrument_T.json', lambda payload: payload['cases'][2].update(
         {'sha256_after': payload['cases'][2]['sha256_before']})),
     'changed no bytes'),
    ('R13_synthetic_sign_case_unlabelled', 'a hand-written number must not read as a measurement',
     lambda d: _rewrite_json(d, 'counterexamples.json', lambda payload: payload['injections'][
         41].pop('evidence_class')),
     'SYNTHETIC_NOT_MEASURED'),
]


def wash_failure_as_pass(directory):
    """one gate really fails, and the summary still reports a passing verdict"""
    _edit(directory, 'commands.csv', RECORD.COMMANDS_HEADER, 'gate', lambda rows: rows[8].update(
        {'verdict_state': 'FAIL', 'rc': '1', 'verdict': 'SOURCE_PROVENANCE_CHECK: FAIL'}))
    _rewrite_summary(directory, {'gates_failed': [], 'verdict':
                                'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES'})


def _rewrite_summary(directory, updates):
    path = os.path.join(directory, 'verification_summary.json')
    payload = json.loads(io.open(path, encoding='utf-8').read())
    payload.update(updates)
    _json(path, payload)


def _rewrite_json(directory, name, mutate):
    path = os.path.join(directory, name)
    payload = json.loads(io.open(path, encoding='utf-8').read())
    mutate(payload)
    _json(path, payload)


def run():
    """returns a list of {'probe', 'verdict', 'detail'} rows for the guard suite"""
    out = []
    parent = tempfile.mkdtemp(prefix='dd1-d7c-a-recordprobe-')
    try:
        control = build_record(os.path.join(parent, 'control'))
        problems, facts = RECORD.check_record(control)
        ok = not problems
        out.append({'probe': 'R0_control_record_is_accepted',
                    'verdict': 'HIT' if ok else 'MISS',
                    'detail': 'fixture accepted (%s)%s' % (
                        ', '.join('%s=%s' % kv for kv in sorted(facts.items())),
                        '' if ok else '; unexpectedly refused: ' + '; '.join(problems[:2]))[:180],
                    'digest': RECORD.__file__ and 'fixture in %s' % parent})
        for name, expectation, tamper, needle in TAMPERS:
            directory = build_record(os.path.join(parent, name))
            tamper(directory)
            problems, _facts = RECORD.check_record(directory)
            hits = [p for p in problems if needle.lower() in p.lower()]
            verdict = 'HIT' if hits else 'MISS'
            detail = 'refused as declared: %s' % hits[0][:150] if hits else \
                'accepted or refused for the wrong reason (%d problems, none naming %r)' % (
                    len(problems), needle)
            out.append({'probe': name, 'verdict': verdict,
                        'detail': '%s | %s' % (expectation[:60], detail)[:180],
                        'digest': 'fixture in %s' % name})
    finally:
        shutil.rmtree(parent, ignore_errors=True)
    return out


if __name__ == '__main__':
    rows = run()
    for row in rows:
        print('%-40s %-5s %s' % (row['probe'], row['verdict'], row['detail'][:130]))
    missed = [r['probe'] for r in rows if r['verdict'] != 'HIT']
    print('D7C_A_R2_RECORD_PROBES: %s (%d/%d; not hit: %s)'
          % ('FAIL' if missed else 'PASS', len(rows) - len(missed), len(rows),
             ','.join(missed) or 'none'))
    sys.exit(1 if missed else 0)
