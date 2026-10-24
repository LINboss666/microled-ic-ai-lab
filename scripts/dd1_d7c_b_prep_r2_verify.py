#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_r2_verify.py -- the R2 gates over the reference-tick repair, published as a record.

DATA-7C-B-PREP-R2 sections 2 to 7. The round is deliberately narrow: one defect (the charge error was
normalised on the window length instead of on the contract's reference tick), five editable files, and
an explicit instruction not to rebuild anything the earlier rounds already settled. So this entry runs
only what the change can affect, and it says so in the ledger rather than padding a gate list:

  * both reviewer instruments, byte for byte as they arrived, are run against an unmodified archive copy
    of the reviewed R1 commit and against these bytes. rc is never the verdict: every field the review
    quoted is read back, and the repaired answer has to show the actual reference tick, QLSB, T50 and
    verdict -- not an empty return or a blanket refusal;
  * the four old families are re-checked for regression, because the review closed them and this round
    must not reopen them;
  * the frozen comparison is against R1, and it has to show that only the five allowed files moved: the
    fifteen decks, the three timing tables, the 1050 ns offsets and the four candidate DUTs stay blobs
    of the reviewed commit, which is what section 3 of the brief requires and what
    `deckgen --to <scratch>` alone cannot prove;
  * the Git ranges are recomputed from the real endpoints, and the numbers the R1 record measured at its
    own moment are quoted as that, not passed off as the final range;
  * one row is `SKIPPED_WITH_REASON` on purpose: the DATA-7C-A record-tool selftest and the T/H history
    evidence are not re-run, because this round changes no shared tool, and `frozen_surfaces` is the
    row that proves that claim instead.

The record's semantic rules come from the shared checker through `dd1_d7c_b_prep_r1_record_check.py`,
which substitutes only round-bound names and reports that it did; no second record framework is built.

    python scripts/dd1_d7c_b_prep_r2_verify.py                      # publish a new record
    python scripts/dd1_d7c_b_prep_r2_verify.py --handoff-check      # judge the R2 handoff alone
"""

from __future__ import absolute_import, print_function

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_offline_check as CHECK                    # noqa: E402
import dd1_d7c_a_r2_record_check as RECORD                # noqa: E402  (the frozen rules)
import dd1_d7c_b_prep_cases as CASES                      # noqa: E402
import dd1_d7c_b_prep_contract as CONTRACT               # noqa: E402
import dd1_d7c_b_prep_measure as MEASURE                  # noqa: E402
import dd1_d7c_b_prep_r1_deck_read as DECKREAD            # noqa: E402  (unchanged this round)
import dd1_d7c_b_prep_r1_record_check as R1REC            # noqa: E402  (rules, R1 vocabulary)
import dd1_d7c_b_prep_schedule as SCHEDULE                # noqa: E402
import dd1_d7c_b_prep_verify as PREP                      # noqa: E402  (git helpers)

TASK_ID = 'DATA-7C-B-PREP-R2'
BASE_R1 = '6778535e70b139812265eba490d0a1381a1fae5c'
BASE_P = CONTRACT.BASE_PREP
BASE_R2 = CONTRACT.BASE_R2
BRANCH = 'poc/data-pam-d7c-b-prep-r2'
REVIEW_ID = 'MicroLED_DATA7C_B_PREP_R1_Independent_Review_20261024'
REVIEW_DIR = os.path.join(ROOT, 'review', REVIEW_ID, 'reviewer')
TICK_PROBE = os.path.join(REVIEW_DIR, 'probe_tick_normalisation.py')
TICK_SHA = '3b970d0fcff5d3f6582d467baf51f5af3eaa59a79d7355d8148023c6a56425ad'
OLD_PROBE = os.path.join(REVIEW_DIR, 'probe_prep_gaps.py')
OLD_SHA = 'd981ff190a627ae70bb8e8a5656226b1b2a2d35e65b6539d99b13768dbe69b7c'
FAMILIES = ('F1_PAM_bit_order_and_high_level', 'F2_PWL_and_window_physics',
            'F3_measurement_entry_wiring', 'F4_native_deck_known_contract')
R2_REPORT = 'reports/dd1_d7c_b_prep_review_fix_r2.md'
PREP_RECORD = 'results/evidence/dd1_d7c_b_prep_20261023_185017_03cccc'
R1_RECORD = 'results/evidence/dd1_d7c_b_prep_r1_20261024_072222_365ef1'
HANDOFF_SELF = ('reports/agent_handoffs/DATA-7C-B-PREP-R2.json',
                'reports/agent_handoffs/DATA-7C-B-PREP-R2.md')
RENDERED_BY_THIS_RUN = (R2_REPORT,)
# section 7, verbatim: five editable paths and nothing else
ALLOWED_MODIFIED = ('scripts/dd1_d7c_b_prep_measure.py', 'scripts/dd1_d7c_b_prep_contract.py',
                    'scripts/dd1_d7c_b_prep_cases.py', 'tests/dd1_d7c_b_prep/contract.json',
                    'reports/dd1_d7c_b_prep_contract.md')
NEW_PREFIXES = ('scripts/dd1_d7c_b_prep_r2_', 'results/evidence/dd1_d7c_b_prep_r2_')
NEW_EXACT = ['reports/tasks/DATA-7C-B-PREP-R2.md', R2_REPORT,
             'reports/agent_handoffs/DATA-7C-B-PREP-R2.md',
             'reports/agent_handoffs/DATA-7C-B-PREP-R2.json']
DECKS = tuple('spectre/dd1_d7c_b_prep/%s' % name for name in sorted(
    os.listdir(os.path.join(ROOT, 'spectre', 'dd1_d7c_b_prep'))) if name.endswith('.scs'))
TIMING_TABLES = ('tests/dd1_d7c_b_prep/schedule.csv', 'tests/dd1_d7c_b_prep/windows.csv',
                 'tests/dd1_d7c_b_prep/pwl.csv')
FROZEN_SURFACES = (
    ('four_candidate_DUT_netlists', list(CONTRACT.FROZEN_CANDIDATE_DUT)),
    ('fifteen_delivered_decks', list(DECKS)),
    ('schedule_windows_and_pwl_tables', list(TIMING_TABLES)),
    ('accepted_DATA7B_measurement_and_run_core', ['scripts/dd1_d7b_measure.py',
                                                 'scripts/dd1_d7b_run.py',
                                                 'spectre/current_probe_syntax.scs']),
    ('shared_tools_safety_and_provenance', list(PREP.SHARED_TOOLS)),
    ('R1_and_PREP_records_reports_and_handoffs', [R1_RECORD, PREP_RECORD]),
    ('earlier_task_books_and_reports', ['reports/dd1_d7c_b_prep_report.md',
                                        'reports/agent_handoffs/DATA-7C-B-PREP-R1.json',
                                        'reports/agent_handoffs/DATA-7C-B-PREP-R1.md',
                                        'reports/tasks/DATA-7C-B-PREP-R1.md',
                                        'reports/tasks/DATA-7C-B-PREP.md']),
)
MANDATORY_GATES_R2 = ('reviewer_tick_probe_on_R1_base', 'reviewer_tick_probe_on_r2_bytes',
                      'reviewer_instrument_bytes_unchanged', 'old_four_families_still_closed',
                      'contract_selfcheck', 'schedule_check', 'deck_check', 'deck_regenerated',
                      'decks_and_tables_identical_to_R1', 'synthetic_measure_cases',
                      'reference_tick_read_back', 'deck_read_still_clean', 'frozen_surfaces',
                      'git_range_counts', 'handoff_structure', 'native_entry_refused', 'provenance',
                      'history_safety', 'record_line_endings', 'offline_checks', 'counterexamples',
                      'fresh_extraction_replay', 'record_tool_selftest')
TABLE_SPECS = {
    'commands.csv': (['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], 'gate', ()),
    'frozen_comparison.csv': (['comparison', 'surface', 'paths_compared', 'mismatched',
                              'first_mismatches', 'expectation', 'enforced'], 'surface',
                             ('first_mismatches',)),
    'git_checks.csv': (['gate', 'command', 'rc', 'lines', 'scope'], 'gate', ()),
    'source_identity.csv': (['role', 'path', 'bytes', 'sha256'], 'path', ()),
    'tick_probe_R1.json': None, 'tick_probe_r2.json': None, 'old_probe_r2.json': None,
    'synthetic_cases.json': None, 'deck_read.json': None, 'ranges.json': None,
    'offline_checks.json': None, 'counterexamples.json': None,
    'verification_summary.json': None,
}


def rows_of(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def sha_of(path):
    return CHECK.sha_file(path)


def probe_gate(name, script, sha_expected, root, out_json, facts_key, want):
    """run one reviewer instrument unmodified and read the fields the review quoted

    `facts_key` is `defect_reproduced` for the tick probe and `all_four_families_reproduced` for the
    old one. The aggregate rc is only ever a summary: the per-family booleans, the delivered entry and
    the instrument digest are all reported in the row, and an instrument that could not run is a FAIL
    rather than an empty result.
    """
    label = 'the R1 archive copy' if str(root).rstrip('/\\\\').endswith('R1') else 'this tree'
    command = 'python review/%s/reviewer/%s.py --root %s --out <json>' % (REVIEW_ID,
                                                                         os.path.basename(script)[:-3],
                                                                         label)
    if not (os.path.isfile(script) and os.path.isdir(root)):
        return {'gate': name, 'command': command, 'rc': 'not_run',
                'expected_rc': '0' if want else '1',
                'verdict': 'NOT_ATTEMPTED: the instrument or its target tree is absent',
                'verdict_state': 'NOT_ATTEMPTED'}, {}
    expected_rc = '0' if want else '1'
    code, _text = PREP.run([sys.executable, script, '--root', root, '--out', out_json])
    normalised = PREP._lf_in_place(out_json)
    try:
        payload = json.loads(io.open(out_json, encoding='utf-8').read())
    except (ValueError, IOError) as error:
        return {'gate': name, 'command': command, 'rc': code, 'expected_rc': expected_rc,
                'verdict': 'no readable JSON: %s' % str(error)[:120],
                'verdict_state': 'FAIL'}, {}
    fact = payload.get(facts_key)
    if payload.get('instrument_error'):
        return {'gate': name, 'command': command, 'rc': code, 'expected_rc': expected_rc,
                'verdict': 'the instrument itself failed: %s' % payload['instrument_error'][:120],
                'verdict_state': 'FAIL'}, payload
    quoted = sha_of(script)
    parts = []
    if facts_key == 'defect_reproduced':
        entry = (payload.get('delivered_entry') or {})
        parts.append('tick=%s qlsb=%s error_LSB=%s verdict=%s'
                     % (entry.get('tick_s'), entry.get('qlsb_C'), entry.get('error_nominal_LSB'),
                        entry.get('verdict_nominal')))
        references = payload.get('independent_contract_references') or []
        parts.append('contract_ticks=%s' % ','.join('%g LSB%s' % (
            item.get('error_LSB'), '' if item.get('outside_half_LSB') else '(within)')
            for item in references))
    else:
        findings = payload.get('findings') or {}
        parts.append('families=%s' % ','.join('%s=%s' % (key[1:3], 'open' if findings[key].get(
            'reproduced') else 'closed') for key in sorted(findings)))
        parts.append('all_four=%s' % payload.get(facts_key))
    good = (str(code) == expected_rc and fact is want and quoted == sha_expected
            and payload.get('instrument_sha256') == sha_expected)
    return {'gate': name, 'command': command, 'rc': code, 'expected_rc': expected_rc,
            'verdict': '%s; %s; instrument sha256 matches the copy in the review package=%s; '
                       'normalised=%s' % (facts_key, '; '.join(parts), quoted == sha_expected,
                                          normalised),
            'verdict_state': 'PASS' if good else 'FAIL'}, payload


def comparisons_r2(tip):
    """the frozen comparison this round actually needs: only five files may have moved"""
    base = PREP.blob_index(BASE_R1)
    head = PREP.blob_index(tip)
    r1_paths = sorted(base)
    added = sorted(set(head) - set(base))
    removed = sorted(set(base) - set(head))
    modified = sorted(path for path in r1_paths if path in head and base[path] != head[path])
    outside = [path for path in r1_paths if path not in ALLOWED_MODIFIED]
    unexpected_new = [path for path in added
                      if not path.startswith(NEW_PREFIXES) and path not in NEW_EXACT]
    rows = [PREP._compare('r2', 'every_R1_path_outside_the_five_editable_files', outside, base, head,
                          'identical')]
    for surface, paths in FROZEN_SURFACES:
        expanded, empty = R1REC.expand_frozen(paths, r1_paths) if hasattr(R1REC, 'expand_frozen') \
            else _expand(paths, r1_paths)
        row = PREP._compare('r2', surface, expanded, base, head, 'identical')
        if empty:
            row['mismatched'] = int(row['mismatched']) + len(empty)
            row['first_mismatches'] = ';'.join(['%s tracks no file at R1' % path for path in empty]
                                               + [row['first_mismatches']])
        rows.append(row)
    rows.append({'comparison': 'r2', 'surface': 'paths_added_this_round',
                 'paths_compared': len(added), 'mismatched': len(unexpected_new),
                 'first_mismatches': ';'.join(unexpected_new[:3]),
                 'expectation': 'only_allowed_new', 'enforced': 'yes'})
    rows.append({'comparison': 'r2', 'surface': 'paths_removed_vs_R1', 'paths_compared': len(removed),
                 'mismatched': len(removed), 'first_mismatches': ';'.join(removed[:3]),
                 'expectation': 'none_removed', 'enforced': 'yes'})
    rows.append({'comparison': 'r2', 'surface': 'paths_modified_vs_R1',
                 'paths_compared': len(modified), 'mismatched': 0,
                 'first_mismatches': ';'.join(modified[:3]), 'expectation': 'informational_listing',
                 'enforced': 'no'})
    counts = {'added': added, 'removed': removed, 'modified': modified, 'base': len(r1_paths),
              'tip': len(head)}
    return rows, counts


def _expand(paths, r1_paths):
    expanded, empty = [], []
    for path in paths:
        if path.startswith('results/evidence/'):
            hits = [found for found in r1_paths if found.startswith(path + '/')]
            if not hits:
                empty.append(path)
            expanded.extend(hits)
        else:
            expanded.append(path)
    return expanded, empty


def range_counts(from_rev, to_rev):
    body = PREP.git('diff', '--name-status', '%s..%s' % (from_rev, to_rev)).decode('utf-8', 'replace')
    counts = {'added': 0, 'changed': 0, 'deleted': 0, 'renamed': 0}
    for line in body.split('\n'):
        if not line.strip():
            continue
        flag = line.split('\t')[0]
        key = ('added' if flag.startswith('A') else 'deleted' if flag.startswith('D') else
               'renamed' if flag.startswith('R') else 'changed' if flag.startswith('M') else None)
        if key:
            counts[key] += 1
    counts['commits'] = int(PREP.git('rev-list', '--count', '%s..%s' % (from_rev, to_rev))
                            .decode('utf-8').strip())
    return counts


def reference_tick_read_back():
    """read the contract map and the entrance numbers side by side, as a gate not as prose"""
    contract_data = CONTRACT.contract()
    table = contract_data['rules']['charge_error']['reference_tick_s_by_case']
    rows, windows, pwl, problems = SCHEDULE.read_delivered()
    observations, bad = [], []
    if problems:
        return problems, observations
    by_case = dict((row['case_id'], row) for row in rows)
    for case_id in sorted(table):
        if case_id not in by_case:
            bad.append('%s is in the map but not in the schedule' % case_id)
            continue
        entries = MEASURE.measure_case(by_case[case_id], windows,
                                        CASES._samples_for(by_case[case_id]))
        rulers = set(entry['charge_error']['qlsb_C'] for entry in entries)
        want = float(CONTRACT.UNIT_CURRENT_NOMINAL_A) * float(table[case_id])
        if rulers and max(abs(value - want) for value in rulers) > 1e-30:
            bad.append('%s measured QLSB %s, the contract says %g'
                       % (case_id, rulers, want))
        observations.append({'case_id': case_id, 'reference_tick_s': float(table[case_id]),
                            'qlsb_C': want, 'windows': len(entries),
                            't50_s_per_window': sorted(set(entry['charge_error']['t50_s']
                                                           for entry in entries))})
    for case_id in ('DC-000', 'DC-111'):
        try:
            MEASURE.reference_tick_for_case(case_id, contract_data)
            bad.append('%s has no time-domain tick and should have been refused' % case_id)
        except MEASURE.Refuse:
            pass
    return bad, observations


def handoff_check_r2():
    """the R2 handoff, judged against its own structure and the bytes on disk"""
    path = os.path.join(ROOT, 'reports', 'agent_handoffs', 'DATA-7C-B-PREP-R2.json')
    if not os.path.isfile(path):
        return ['DATA-7C-B-PREP-R2.json is not written yet']
    payload = json.loads(io.open(path, encoding='utf-8').read())
    problems = []
    for key in ('schema_version', 'task_id', 'base_sha', 'branch', 'repository', 'scope',
                'contract_state', 'review_verdict', 'repair', 'instrument_readings',
                'frozen_surfaces', 'source_identity', 'costs', 'boundaries', 'not_run',
                'stop_reason', 'known_limitations', 'remote_readback', 'range_counts'):
        if key not in payload:
            problems.append('missing field %s' % key)
    if payload.get('task_id') != TASK_ID:
        problems.append('task_id is %r, not %r' % (payload.get('task_id'), TASK_ID))
    if payload.get('base_sha') != BASE_R1:
        problems.append('base_sha is not the R1 tip the review judged')
    if payload.get('branch') != BRANCH:
        problems.append('branch is %r, not %r' % (payload.get('branch'), BRANCH))
    if payload.get('contract_state') != CONTRACT.CONTRACT_STATE:
        problems.append('the handoff moved the contract state off %s' % CONTRACT.CONTRACT_STATE)
    for key in ('new_spectre_launches', 'new_rtl_simulations', 'new_oa_writes',
                'new_native_preflights'):
        value = (payload.get('costs') or {}).get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            problems.append('costs.%s must be an integer 0, found %r' % (key, value))
    editable = (payload.get('frozen_surfaces') or {}).get('editable_files')
    if sorted(editable or ()) != sorted(ALLOWED_MODIFIED):
        problems.append('the handoff names %s as editable, the brief allows exactly %s'
                        % (sorted(editable or ()), sorted(ALLOWED_MODIFIED)))
    for entry in (payload.get('source_identity') or {}).get('delivered', []) + \
            (payload.get('source_identity') or {}).get('read_only_inputs', []):
        rel = str(entry.get('path', ''))
        if rel in HANDOFF_SELF:
            problems.append('%s is listed inside the handoff it lives in' % rel)
            continue
        if rel in RENDERED_BY_THIS_RUN:
            problems.append('%s is digested by the handoff, but this run rewrites that file' % rel)
            continue
        target = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.isfile(target):
            problems.append('source_identity names %s which is not on disk' % rel)
            continue
        if entry.get('sha256') != sha_of(target):
            problems.append('%s digest in the handoff does not match the bytes on disk' % rel)
        if int(entry.get('bytes', -1)) != os.path.getsize(target):
            problems.append('%s byte count in the handoff does not match the bytes on disk' % rel)
    blob = json.dumps(payload, ensure_ascii=False)
    for forbidden in ('PAM_IMPLEMENTED=PASS', 'CURRENT_MEASURED=PASS', 'MEASURED_PASS',
                      'CONTRACT_STATE=USER_APPROVED', 'NATIVE_GO'):
        if forbidden in blob:
            problems.append('the handoff contains the forbidden claim %r' % forbidden)
    readings = payload.get('instrument_readings') or {}
    for name in ('tick_probe_on_R1', 'tick_probe_on_R2', 'old_probe_on_R2'):
        if name not in readings:
            problems.append('instrument_readings has no %s' % name)
    for key, value in (payload.get('not_run') or {}).items():
        if value not in ('NOT_RUN', 'NOT_VERIFIED', 'NOT_DEFINED', 'NOT_FROZEN', 'NOT_AUTHORISED'):
            problems.append('not_run.%s must be a marker, found %r' % (key, value))
    if not payload.get('known_limitations'):
        problems.append('a repair handoff with no limitations has not looked at what it left open')
    return problems


def replay_r2(directory):
    """the whole chain inside a fresh `git archive` extraction of the tip"""
    plan = [('contract_check', 'dd1_d7c_b_prep_contract.py', ('--check',), (0,)),
            ('schedule_check', 'dd1_d7c_b_prep_schedule.py', ('--check',), (0,)),
            ('deck_check', 'dd1_d7c_b_prep_deckgen.py', ('--check',), (0,)),
            ('deck_regenerate', 'dd1_d7c_b_prep_deckgen.py', ('--to', 'regen'), (0,)),
            ('synthetic_cases', 'dd1_d7c_b_prep_cases.py', (), (0,)),
            ('deck_read_check', 'dd1_d7c_b_prep_r1_deck_read.py', ('--check',), (0,)),
            ('deck_read_negatives', 'dd1_d7c_b_prep_r1_deck_read.py', ('--counterexample',), (0,)),
            ('offline', 'dd1_d7c_a_offline_check.py', ('--json', 'out.json'), (0,)),
            ('guards', 'dd1_d7c_a_guards.py', ('--json', 'out.json'), (0,)),
            ('tick_probe_here', TICK_PROBE, ('--root', '.', '--out', 'tick_in_extraction.json'),
             (1,)),
            ('old_probe_here', OLD_PROBE, ('--root', '.', '--out', 'old_in_extraction.json'), (1,)),
            ('selftest_needs_history', 'dd1_d7c_a_r1_selftest.py', ('--json', 'self.json'), (0, 2))]
    out = []
    for suite, script, args, accepted in plan:
        target = script if os.path.isabs(script) else os.path.join(directory, 'scripts', script)
        cmd = [sys.executable, target] + [os.path.join(directory, arg)
                                          if arg.endswith('.json') and '/' not in arg
                                          else (directory if arg == '.' else arg) for arg in args]
        code, text = PREP.run(cmd, cwd=directory)
        tail = text.strip().split('\n')[-1][:110] if text.strip() else ''
        out.append({'suite': suite, 'rc': code, 'accepted': code in accepted, 'note': tail})
    return out


def _table(lines, header, rows):
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('|' + '|'.join(['---'] * len(header)) + '|')
    for row in rows:
        lines.append('| ' + ' | '.join(str(value).replace('|', '/') for value in row) + ' |')


def render_report(results, rows, git_rows, ranges, case_rows, tick_after, tick_before, observations,
                  tip):
    """five machine-written tables in the R2 report; the prose above them stays hand-written"""
    report = os.path.join(ROOT, R2_REPORT.replace('/', os.sep))
    lines = ['| 门 | 命令 | rc | 期望 | 判决 | 依据 |', '|---|---|---|---|---|---|']
    for row in results:
        lines.append('| `%s` | `%s` | %s | %s | %s | %s |'
                     % (row['gate'], row['command'][:70].replace('|', '/'), row['rc'],
                        row['expected_rc'], row['verdict_state'],
                        str(row['verdict'])[:150].replace('|', '/')))
    lines.append('')
    lines.append('渲染发生在 `%s` 之后、`record_semantics` 与 `published_record_recheck` 判定之前；'
                  '本表不含本轮记录的摘要。' % tip[:12])
    PREP._splice(report, '<!-- BEGIN 7CB_R2 GATES -->', '<!-- END 7CB_R2 GATES -->', lines)

    def entry_of(read):
        return (read.get('payload') or {}).get('delivered_entry') or {}

    def field(read, key, default='?'):
        value = entry_of(read).get(key, default)
        if isinstance(value, float):
            return '%g' % value
        return value

    before_entry, after_entry = entry_of(tick_before), entry_of(tick_after)
    tlines = []
    _table(tlines, ['读数（逐项来自仪器 JSON）', 'R1 基线（未修）', 'R2 字节（已修）'],
           [('仪器 rc', tick_before.get('rc'), tick_after.get('rc')),
            ('defect_reproduced', (tick_before.get('payload') or {}).get('defect_reproduced'),
             (tick_after.get('payload') or {}).get('defect_reproduced')),
            ('入口实际采用的分母 tick (s)', field(tick_before, 'tick_s'), field(tick_after, 'tick_s')),
            ('QLSB (C)', field(tick_before, 'qlsb_C'), field(tick_after, 'qlsb_C')),
            ('T50 全使能窗 (s)', (tick_before.get('payload') or {}).get('actual_full_window_s'),
             (tick_after.get('payload') or {}).get('actual_full_window_s')),
            ('注入的多余电荷 (C)', (tick_before.get('payload') or {}).get('observed_extra_charge_C'),
             (tick_after.get('payload') or {}).get('observed_extra_charge_C')),
            ('误差 (LSB) / 判决', '%s / %s' % (field(tick_before, 'error_nominal_LSB'),
                                                field(tick_before, 'verdict_nominal')),
             '%s / %s' % (field(tick_after, 'error_nominal_LSB'), field(tick_after, 'verdict_nominal'))),
            ('合同两个名义 tick 下应为',
             '; '.join('%g LSB @ %g s' % (item.get('error_LSB', 0.0), item.get('contract_tick_s', 0.0))
                       for item in (tick_before.get('payload') or {}).get(
                           'independent_contract_references', [])),
             '同一个 120 ns 参考，即交付值'),
            ])
    tlines.append('')
    tlines.append('两份仪器都按原字节运行（`%s` / `%s`），rc 只是摘要；上表逐项读自 JSON 字段，'
                  '修补的判据是 tick/QLSB 真变了并且判决越限，而不是空返回或整片拒收。'
                  % (TICK_SHA[:12], OLD_SHA[:12]))
    PREP._splice(report, '<!-- BEGIN 7CB_R2 TICK -->', '<!-- END 7CB_R2 TICK -->', tlines)

    olines = []
    _table(olines, ['case_id', '参考 Ttick (ns)', 'QLSB (C)', '发光窗数', '该例各窗 T50 (s)'],
           [(item['case_id'], item['reference_tick_s'] * 1e9, item['qlsb_C'], item['windows'],
             ', '.join('%g' % (value * 1e9,) for value in item['t50_s_per_window']))
            for item in observations])
    olines.append('')
    olines.append('DC 八例不在表内：合同规定其时域 QLSB 不适用，入口对该情形返回 '
                  '`NOT_APPLICABLE_DC_HAS_NO_TIME_DOMAIN`。')
    PREP._splice(report, '<!-- BEGIN 7CB_R2 TICKMAP -->', '<!-- END 7CB_R2 TICKMAP -->', olines)

    clines = []
    _table(clines, ['例', '类型', '判决', '观察到的依据', '说明'],
           [(row['case'], row['kind'], row['verdict'],
             (row['detail'] or '; '.join(row['problems']))[:120], row['meaning'][:110])
            for row in case_rows])
    PREP._splice(report, '<!-- BEGIN 7CB_R2 CASES -->', '<!-- END 7CB_R2 CASES -->', clines)

    glines = []
    _table(glines, ['区间', '新增', '变更', '删除', '重命名', '提交数', '说明'],
           [('`%s..%s`（P..R1，本轮基线区间）' % (BASE_P[:12], BASE_R1[:12]),
             ranges['P..R1']['added'], ranges['P..R1']['changed'], ranges['P..R1']['deleted'],
             ranges['P..R1']['renamed'], ranges['P..R1']['commits'],
             '按实际两端 SHA 重算；R1 记录里那次测量（%d 新增 / %d 提交）只属于它自己的时刻，'
             '不能当作最终范围' % (ranges['P..R1_at_R1_record']['added'],
                                  ranges['P..R1_at_R1_record']['commits'])),
            ('`%s..HEAD`（R1..本轮）' % BASE_R1[:12], ranges['R1..HEAD']['added'],
             ranges['R1..HEAD']['changed'], ranges['R1..HEAD']['deleted'],
             ranges['R1..HEAD']['renamed'], ranges['R1..HEAD']['commits'],
             '度量于运行本入口时已提交的 HEAD=%s；记录目录本身在下一个提交里' % tip[:12])])
    PREP._splice(report, '<!-- BEGIN 7CB_R2 RANGES -->', '<!-- END 7CB_R2 RANGES -->', glines)

    flines = ['| 比较 | 面 | 路径数 | 计数 | 前若干 | 期望 | 计入闸 |',
              '|---|---|---:|---:|---|---|---|']
    for row in rows:
        flines.append('| %s | `%s` | %s | %s | %s | `%s` | %s |'
                      % (row['comparison'], row['surface'], row['paths_compared'], row['mismatched'],
                         str(row['first_mismatches'])[:90].replace('|', '/'), row['expectation'],
                         row['enforced']))
    PREP._splice(report, '<!-- BEGIN 7CB_R2 FROZEN -->', '<!-- END 7CB_R2 FROZEN -->', flines)
    return report


def record_rules(gate_rows, frozen_rows, git_rows, identity_rows, directory, summary_exists=True):
    """the shared rules, with the round-bound vocabulary replaced by this round's and reported"""
    problems = []
    names = RECORD.gate_semantics(gate_rows, problems)
    replaced = 0
    for line in list(problems):
        if line.startswith('mandatory gate(s) absent from commands.csv:') or \
                line in ('instrument_T.json is absent', 'instrument_fixed.json is absent'):
            problems.remove(line)
            replaced += 1
    missing = [gate for gate in MANDATORY_GATES_R2 if gate not in names]
    if missing:
        problems.append('mandatory gate(s) absent from commands.csv (the R2 list, which keeps every '
                        'rule of the shared checker and only renames what belonged to earlier '
                        'rounds): %s' % ','.join(missing))
    if gate_rows:
        RECORD.frozen_semantics(frozen_rows, gate_rows, problems)
        R1REC._json_rules(directory, gate_rows, problems)
        if summary_exists:
            RECORD.summary_semantics(directory, gate_rows, problems)
    RECORD.identity_semantics(identity_rows, directory, problems, None, None)
    for row in git_rows:
        if BASE_R1 not in str(row['command']) and 'HEAD' not in str(row['command']):
            problems.append('git_checks %s does not name the revision its range starts at'
                            % row['gate'])
        if not str(row['rc']).lstrip('-').isdigit():
            problems.append('git_checks %s rc=%r is not a number' % (row['gate'], row['rc']))
    return problems, {'gates': len(names), 'frozen_rows': len(frozen_rows),
                      'identity_rows': len(identity_rows), 'git_checks': len(git_rows),
                      'mandatory_gates_r2': len(MANDATORY_GATES_R2),
                      'frozen_vocabulary_lines_replaced': replaced}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--handoff-check', action='store_true')
    parser.add_argument('--out', default='')
    arguments = parser.parse_args(argv)
    if arguments.handoff_check:
        problems = handoff_check_r2()
        print('D7C_B_PREP_R2_HANDOFF %s %s' % ('PASS' if not problems else 'FAIL',
                                               '; '.join(problems[:4]) if problems else
                                               'fields, digests against disk, the five editable files, '
                                               'zero costs and no self-listing'))
        return 0 if not problems else 1
    out_dir = os.path.abspath(arguments.out) if arguments.out else os.path.join(
        ROOT, 'results', 'evidence', 'dd1_d7c_b_prep_r2_%s_%06x' % (
            time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
            int(hashlib.sha256(os.urandom(8)).hexdigest()[:6], 16)))
    if os.path.isdir(out_dir):
        raise SystemExit('D7C_B_PREP_R2_VERIFY_REFUSED %s already exists; published records are never '
                         'overwritten, choose a new run id' % out_dir)
    tip = PREP.git('rev-parse', 'HEAD').decode().strip()
    os.makedirs(out_dir)
    results = []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-b-r2-')
    try:
        r1_dir = os.path.join(scratch, 'R1')
        os.makedirs(r1_dir)
        extracted_r1 = PREP.extract(BASE_R1, r1_dir)
        before_code, before = probe_gate('reviewer_tick_probe_on_R1_base', TICK_PROBE, TICK_SHA,
                                         r1_dir, os.path.join(out_dir, 'tick_probe_R1.json'),
                                         'defect_reproduced', True)
        after_code, after = probe_gate('reviewer_tick_probe_on_r2_bytes', TICK_PROBE, TICK_SHA,
                                       ROOT, os.path.join(out_dir, 'tick_probe_r2.json'),
                                       'defect_reproduced', False)
        results.append(before_code)
        results.append(after_code)
        old_code, old = probe_gate('old_four_families_still_closed', OLD_PROBE, OLD_SHA, ROOT,
                                   os.path.join(out_dir, 'old_probe_r2.json'),
                                   'all_four_families_reproduced', False)
        results.append(old_code)
        same_bytes = (sha_of(TICK_PROBE) == TICK_SHA and sha_of(OLD_PROBE) == OLD_SHA
                      and (after.get('instrument_sha256') == TICK_SHA
                           and old.get('instrument_sha256') == OLD_SHA))
        results.append({'gate': 'reviewer_instrument_bytes_unchanged',
                        'command': 'sha256 of the two instruments on disk against the digests the '
                                   'review package published',
                        'rc': 0 if same_bytes else 1, 'expected_rc': '0',
                        'verdict': 'probe_tick_normalisation.py=%s, probe_prep_gaps.py=%s; both runs '
                                   'quote the same digests they computed for themselves'
                                   % (TICK_SHA[:16], OLD_SHA[:16]),
                        'verdict_state': 'PASS' if same_bytes else 'FAIL'})
        for row in results:
            print('GATE %-38s %s %s' % (row['gate'], row['verdict_state'],
                                        str(row['verdict'])[:95]))

        for name, script, args, expected in (
                ('contract_selfcheck', 'dd1_d7c_b_prep_contract.py', ('--check',), '0'),
                ('schedule_check', 'dd1_d7c_b_prep_schedule.py', ('--check',), '0'),
                ('deck_check', 'dd1_d7c_b_prep_deckgen.py', ('--check',), '0'),
                ('offline_checks', 'dd1_d7c_a_offline_check.py',
                 ('--json', os.path.join(out_dir, 'offline_checks.json')), '0'),
                ('counterexamples', 'dd1_d7c_a_guards.py',
                 ('--json', os.path.join(out_dir, 'counterexamples.json')), '0')):
            code, body = PREP.run([sys.executable, os.path.join(HERE, script)] + list(args))
            results.append(PREP._gate(name, 'python %s %s' % (script, ' '.join(
                arg for arg in args if not arg.endswith('.json'))), code, expected, body))
            print('GATE %-38s %s %s' % (name, results[-1]['verdict_state'],
                                        results[-1]['verdict'][:95]))
        code, body = PREP.run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_deckgen.py'),
                               '--to', os.path.join(scratch, 'regen')])
        results.append(PREP._gate('deck_regenerated', 'python dd1_d7c_b_prep_deckgen.py --to <scratch>',
                                  code, '0', body))
        code, body = PREP.run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_cases.py'),
                               '--json', os.path.join(out_dir, 'synthetic_cases.json')])
        results.append(PREP._gate('synthetic_measure_cases',
                                  'python dd1_d7c_b_prep_cases.py --json <out>', code, '0', body))
        print('GATE %-38s %s %s' % ('synthetic_measure_cases', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))
        gate, _text = _deck_read_gate(os.path.join(out_dir, 'deck_read.json'))
        results.append(gate)
        print('GATE %-38s %s %s' % (gate['gate'], gate['verdict_state'], gate['verdict'][:95]))

        deck_bad, observations = reference_tick_read_back()
        results.append({'gate': 'reference_tick_read_back',
                        'command': 'python -c reference_tick_read_back() in process: measure every '
                                   'transient case and compare its QLSB with the contract map',
                        'rc': len(deck_bad), 'expected_rc': '0',
                        'verdict': '%d cases mapped, %d windows read, %d disagreements; DC cases refuse '
                                   'a tick by name'
                                   % (len(observations), sum(item['windows'] for item in observations),
                                      len(deck_bad)),
                        'verdict_state': 'PASS' if not deck_bad else 'FAIL'})
        results[-1]['verdict'] = '%s; %s' % (results[-1]['verdict'],
                                             '; '.join(deck_bad[:2]) if deck_bad else 'none')
        print('GATE %-38s %s %s' % ('reference_tick_read_back', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        r1_blobs = PREP.blob_index(BASE_R1)
        head_blobs = PREP.blob_index(tip)
        untouched = [path for path in list(DECKS) + list(TIMING_TABLES)
                     if r1_blobs.get(path) != head_blobs.get(path)]
        results.append({'gate': 'decks_and_tables_identical_to_R1',
                        'command': 'git ls-tree -r blob+mode comparison of the 15 decks and the three '
                                   'timing tables between %s and HEAD' % BASE_R1[:12],
                        'rc': len(untouched), 'expected_rc': '0',
                        'verdict': '%d decks + %d tables compared, %d differ; the reference tick is '
                                   'measurement metadata, so no stimulus, window or 1050 ns offset moved'
                                   % (len(DECKS), len(TIMING_TABLES), len(untouched)),
                        'verdict_state': 'PASS' if not untouched else 'FAIL'})
        print('GATE %-38s %s %s' % ('decks_and_tables_identical_to_R1',
                                    results[-1]['verdict_state'], results[-1]['verdict'][:95]))

        directory = os.path.join(scratch, 'extract')
        os.makedirs(directory)
        extracted = PREP.extract(tip, directory)
        outcomes = replay_r2(directory) if extracted else []
        bad = [o for o in outcomes if not o['accepted']]
        results.append({'gate': 'fresh_extraction_replay',
                        'command': 'git archive %s | tar -x, then run every suite and both reviewer '
                                   'instruments there' % tip[:12],
                        'rc': len(bad), 'expected_rc': '0',
                        'verdict': ('; '.join('%s rc=%s %s' % (o['suite'], o['rc'], o['note'])
                                               for o in outcomes)[:400] if extracted
                                    else 'EXTRACTION_FAILED'),
                        'verdict_state': 'PASS' if extracted and not bad else 'FAIL'})
        print('GATE %-38s %s %s' % ('fresh_extraction_replay', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        problems = handoff_check_r2()
        results.append({'gate': 'handoff_structure',
                        'command': 'python dd1_d7c_b_prep_r2_verify.py --handoff-check (in process)',
                        'rc': len(problems), 'expected_rc': '0',
                        'verdict': '; '.join(problems[:3]) if problems else
                                   'fields, digests against disk, five editable files, four repairs '
                                   'named, zero costs and no self-listing',
                        'verdict_state': 'PASS' if not problems else 'FAIL'})
        print('GATE %-38s %s %s' % ('handoff_structure', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        probe_dir = os.path.join(scratch, 'nativeprobe')
        os.makedirs(probe_dir)
        with io.open(os.path.join(probe_dir, 'placeholder.txt'), 'wb') as handle:
            handle.write(b'probe content\n')
        code, body = PREP.run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_deckgen.py'), '--probe',
                               probe_dir], cwd=scratch)
        results.append(PREP._gate('native_entry_refused',
                                  'python dd1_d7c_a_deckgen.py --probe <temp>', code, '0', body))
        code, body = PREP.run([sys.executable, os.path.join(ROOT, 'scripts',
                                                           'provenance_check.py')])
        results.append(PREP._gate('provenance', 'python scripts/provenance_check.py', code, '0', body))
        code, body = PREP.run([sys.executable, os.path.join(ROOT, 'scripts',
                                                            'precommit_safety_check.py'),
                               '--mode', 'history'])
        results.append(PREP._gate('history_safety', 'python scripts/precommit_safety_check.py '
                                                    '--mode history', code, '0', body))
        results.append({'gate': 'record_tool_selftest',
                        'command': 'python dd1_d7c_a_r1_selftest.py --json <out>/selftest.json in a '
                                   'throw-away clone at the accepted R2 commit',
                        'rc': 'not_run', 'expected_rc': 'not re-run this round',
                        'verdict': 'SKIPPED_WITH_REASON: this round edits none of the shared tools, so '
                                   'the A-round selftest and the T/H history evidence are not rebuilt; '
                                   'frozen_surfaces is the row that shows the shared tools are the same '
                                   'blobs as R1',
                        'verdict_state': 'SKIPPED_WITH_REASON'})
        for name in ('native_entry_refused', 'provenance', 'history_safety', 'record_tool_selftest'):
            row = [r for r in results if r['gate'] == name][0]
            print('GATE %-38s %s %s' % (name, row['verdict_state'], str(row['verdict'])[:95]))

        ranges = {'P..R1': range_counts(BASE_P, BASE_R1), 'R1..HEAD': range_counts(BASE_R1, tip)}
        r1_summary_path = os.path.join(ROOT, R1_RECORD.replace('/', os.sep),
                                       'verification_summary.json')
        r1_measured = json.loads(io.open(r1_summary_path, encoding='utf-8').read()
                                 ).get('range_counts', {}).get('P..HEAD', {})
        ranges['P..R1_at_R1_record'] = {'added': r1_measured.get('added'),
                                        'changed': r1_measured.get('changed'),
                                        'deleted': r1_measured.get('deleted'),
                                        'renamed': 0, 'commits': r1_measured.get('commits')}
        with io.open(os.path.join(out_dir, 'ranges.json'), 'wb') as handle:
            handle.write((json.dumps(ranges, indent=1, sort_keys=True) + '\n').encode('utf-8'))
        expected_range = {'added': 23, 'changed': 26, 'deleted': 0, 'commits': 5}
        matches = all(ranges['P..R1'].get(key) == value for key, value in expected_range.items())
        git_rows = []
        for label, other in (('diff_check_R1_to_HEAD', BASE_R1), ('diff_check_P_to_HEAD', BASE_P)):
            check_code, check_body = PREP.run(['git', '-C', ROOT, 'diff', '--check',
                                               '%s..HEAD' % other])
            git_rows.append({'gate': label, 'command': 'git diff --check %s..HEAD' % other,
                             'rc': check_code,
                             'lines': len([b for b in check_body.split('\n') if b.strip()]),
                             'scope': 'committed range from %s to HEAD(%s) at %s'
                                      % (other[:12], tip[:12],
                                         time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))})
        results.append({'gate': 'git_range_counts',
                        'command': 'git diff --name-status and git rev-list --count over P..R1 and '
                                   'R1..HEAD, plus git diff --check on the committed ranges',
                        'rc': 0 if matches else 1, 'expected_rc': '0',
                        'verdict': 'P..R1 %d added / %d changed / %d deleted / %d commits, which is '
                                   'what the review of R1 recomputed (its own record measured %d added '
                                   'over %d commits at that moment and that number is kept as a '
                                   'moment-bound figure); R1..HEAD %d added / %d changed / %d deleted '
                                   'over %d commits; diff --check R1..HEAD=%s P..HEAD=%s'
                                   % (ranges['P..R1']['added'], ranges['P..R1']['changed'],
                                      ranges['P..R1']['deleted'], ranges['P..R1']['commits'],
                                      ranges['P..R1_at_R1_record']['added'],
                                      ranges['P..R1_at_R1_record']['commits'],
                                      ranges['R1..HEAD']['added'], ranges['R1..HEAD']['changed'],
                                      ranges['R1..HEAD']['deleted'], ranges['R1..HEAD']['commits'],
                                      git_rows[0]['rc'], git_rows[1]['rc']),
                        'verdict_state': 'PASS' if matches and not any(
                            int(row['rc']) for row in git_rows) else 'FAIL'})
        print('GATE %-38s %s %s' % ('git_range_counts', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        rows, counts = comparisons_r2(tip)
        CHECK.rows_write(os.path.join(out_dir, 'frozen_comparison.csv'), RECORD.FROZEN_HEADER, rows)
        CHECK.rows_write(os.path.join(out_dir, 'git_checks.csv'), RECORD.GIT_HEADER, git_rows)
        enforced = [r for r in rows if r['enforced'] == 'yes']
        violations = sum(int(r['mismatched']) for r in enforced)
        diff_rc = max(int(r['rc']) for r in git_rows)
        results.append({'gate': 'frozen_surfaces', 'command': 'git ls-tree -r blob and mode comparison '
                            'over explicit path lists against the reviewed R1 commit',
                        'rc': violations + diff_rc, 'expected_rc': '0',
                        'verdict': 'enforced rows %d, violations %d, informational %d; added vs R1 %d, '
                                   'removed %d, modified %d (the five editable files); git diff --check '
                                   'max rc=%d'
                                   % (len(enforced), violations, len(rows) - len(enforced),
                                      len(counts['added']), len(counts['removed']),
                                      len(counts['modified']), diff_rc),
                        'verdict_state': 'PASS' if violations == 0 and diff_rc == 0 else 'FAIL'})
        print('GATE %-38s %s %s' % ('frozen_surfaces', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        with_cr = []
        for name in sorted(TABLE_SPECS):
            path = os.path.join(out_dir, name)
            if os.path.isfile(path) and b'\r' in io.open(path, 'rb').read():
                with_cr.append(name)
        probe_csv = os.path.join(scratch, 'lineendings.csv')
        CHECK.rows_write(probe_csv, ['a', 'b'], [{'a': 'has, comma', 'b': 'and "quotes"'}])
        writer_lf = b'\r' not in io.open(probe_csv, 'rb').read()
        results.append({'gate': 'record_line_endings',
                        'command': 'scan every published file for CR and round-trip a comma-and-quote '
                                   'row through rows_write',
                        'rc': len(with_cr), 'expected_rc': '0',
                        'verdict': 'published files still carrying CR: %s; the table writer emits LF '
                                   '(%s); instrument JSONs are normalised only after the parsed object '
                                   'is proven identical' % (with_cr or 'none',
                                                            'confirmed' if writer_lf else 'BROKEN'),
                        'verdict_state': 'PASS' if not with_cr and writer_lf else 'FAIL'})
        print('GATE %-38s %s %s' % ('record_line_endings', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        case_rows = json.loads(io.open(os.path.join(out_dir, 'synthetic_cases.json'),
                                       encoding='utf-8').read())['results']
        before_text = io.open(os.path.join(ROOT, R2_REPORT.replace('/', os.sep)),
                              encoding='utf-8', newline='').read()
        tick_before = {'rc': before_code['rc'], 'payload': before}
        tick_after = {'rc': after_code['rc'], 'payload': after}
        render_report(results, rows, git_rows, ranges, case_rows, tick_after, tick_before,
                      observations, tip)
        middle = io.open(os.path.join(ROOT, R2_REPORT.replace('/', os.sep)),
                        encoding='utf-8', newline='').read()
        render_report(results, rows, git_rows, ranges, case_rows, tick_after, tick_before,
                      observations, tip)
        after_text = io.open(os.path.join(ROOT, R2_REPORT.replace('/', os.sep)),
                            encoding='utf-8', newline='').read()
        results.append({'gate': 'report_render_fixed_point',
                        'command': 'python dd1_d7c_b_prep_r2_verify.py (renders the five tables twice '
                                   'and compares)',
                        'rc': 0 if middle == after_text else 1, 'expected_rc': '0',
                        'verdict': 'first render %s (length %+d bytes), second left it byte-identical '
                                   '(%s); the tables are a function of the sources and of the moment '
                                   'this run measured them'
                                   % ('changed the file' if middle != before_text else 'no change',
                                      len(middle) - len(before_text),
                                      'changed bytes' if after_text != middle else 'no change'),
                        'verdict_state': 'PASS' if middle == after_text else 'FAIL'})
        print('GATE %-38s %s %s' % ('report_render_fixed_point', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:95]))

        identity = []
        base_paths = sorted(PREP.blob_index(BASE_R1))
        for rel in sorted(counts['added']):
            if rel in HANDOFF_SELF:
                continue
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'added by R2', 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': sha_of(target)})
        for rel in sorted(counts['modified']):
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'rendered by this run after measuring the tip, so the digest '
                                 'is of the bytes it wrote' if rel in RENDERED_BY_THIS_RUN
                                 else 'one of the five editable files',
                                 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': sha_of(target)})
        for surface, paths in FROZEN_SURFACES:
            expanded, _empty = _expand(paths, base_paths)
            for rel in expanded:
                target = os.path.join(ROOT, rel.replace('/', os.sep))
                if any(row['path'] == rel for row in identity) or not os.path.isfile(target):
                    continue
                identity.append({'role': 'frozen by section 7 (%s)' % surface, 'path': rel,
                                 'bytes': os.path.getsize(target), 'sha256': sha_of(target)})
        for rel in HANDOFF_SELF:
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'R2 handoff, written before this record and committed with it',
                                 'path': rel, 'bytes': os.path.getsize(target), 'sha256': sha_of(target)})
        for rel in (PREP.SHARED_TOOLS + [TICK_PROBE.replace(ROOT + os.sep, '').replace(os.sep, '/'),
                                         OLD_PROBE.replace(ROOT + os.sep, '').replace(os.sep, '/')]):
            if not os.path.isfile(os.path.join(ROOT, rel.replace('/', os.sep))) or \
                    any(row['path'] == rel for row in identity):
                continue
            identity.append({'role': 'tool or instrument this round reads', 'path': rel,
                             'bytes': os.path.getsize(os.path.join(ROOT, rel.replace('/', os.sep))),
                             'sha256': sha_of(os.path.join(ROOT, rel.replace('/', os.sep)))})
        duplicated = sorted(set(row['path'] for row in identity
                                if [r['path'] for r in identity].count(row['path']) > 1))
        if duplicated:
            raise SystemExit('D7C_B_PREP_R2_VERIFY_REFUSED source_identity would publish %s twice'
                             % ','.join(duplicated))
        pending = [dict(row) for row in results] + [
            {'gate': 'record_semantics', 'command': 'python scripts/dd1_d7c_b_prep_r2_verify.py '
             'record_rules() over the published tables', 'rc': 0, 'expected_rc': '0',
             'verdict_state': 'PASS',
             'verdict': 'provisional: the semantic layer below decides this row'}]
        problems, _facts = record_rules(pending, rows, git_rows, identity, out_dir,
                                        summary_exists=False)
        verdict_state = 'PASS' if not problems else 'FAIL'
        pending[-1].update({'verdict_state': verdict_state, 'rc': len(problems),
                            'verdict': 'rules over the gate rows, the frozen table, the git ranges, '
                                       'the source identity and every sub-result JSON; %s'
                                       % ('no semantic problem' if not problems
                                          else '; '.join(problems[:3]))})
        results.extend(pending[len(results):])
        print('GATE %-38s %s %s' % ('record_semantics', verdict_state,
                                    pending[-1]['verdict'][:110]))
        CHECK.rows_write(os.path.join(out_dir, 'source_identity.csv'), RECORD.IDENTITY_HEADER,
                         identity)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    CHECK.rows_write(os.path.join(out_dir, 'commands.csv'), RECORD.COMMANDS_HEADER, results)
    read_back, crlf_found = [], []
    for name, spec in sorted(TABLE_SPECS.items()):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            continue
        if b'\r' in io.open(path, 'rb').read():
            crlf_found.append(name)
        if spec is None:
            json.loads(io.open(path, encoding='utf-8').read())
            read_back.append({'file': name, 'result': 'JSON parses, no CR byte', 'rows': ''})
            continue
        header, key, optional = spec
        parsed = CHECK.read_table(path, header, key, optional=optional)
        read_back.append({'file': name, 'result': 'columns and keys verified, no CR byte',
                          'rows': len(parsed)})
    enforced = [r for r in rows if r['enforced'] == 'yes']
    failures = [r['gate'] for r in results if r['verdict_state'] == 'FAIL']
    informational = [r['gate'] for r in results if r['verdict_state'] not in ('PASS', 'FAIL')]
    summary = {'task_id': TASK_ID, 'base_r1': BASE_R1, 'base_prep': BASE_P, 'base_r2': BASE_R2,
               'branch': BRANCH, 'tip': tip, 'review_package': REVIEW_ID,
               'review_verdict': 'REWORK / REPAIR_SCOPE=TRANSIENT_Q_LSB_REFERENCE_ONLY / '
                                 'PREVIOUS_F1_TO_F4_DIAGNOSTICS=CLOSED / NATIVE_EXECUTION_AUTHORISED=NO',
               'editable_files': list(ALLOWED_MODIFIED),
               'identity_paths_rewritten_by_this_run': list(RENDERED_BY_THIS_RUN),
               'contract_state': CONTRACT.CONTRACT_STATE,
               'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'gates': len(results), 'gates_failed': failures,
               'gates_informational': informational, 'csv_read_back': read_back,
               'published_files_with_cr': crlf_found,
               'frozen_rows': len(rows), 'frozen_rows_enforced': len(enforced),
               'frozen_rows_informational': len(rows) - len(enforced),
               'frozen_enforced_mismatches': sum(int(r['mismatched']) for r in enforced),
               'frozen_violating_surfaces': [r['surface'] for r in enforced
                                             if int(r['mismatched']) > 0],
               'range_counts': ranges,
               'range_counts_note': 'P..R1 is recomputed from the two real endpoints; the numbers the '
                                    'R1 record measured are kept in ranges.json as the moment they '
                                    'belong to, not as the final range',
               'paths_added_vs_R1': counts['added'], 'paths_removed_vs_R1': counts['removed'],
               'paths_modified_vs_R1': counts['modified'],
               'reference_tick_table': CONTRACT.contract()['rules']['charge_error']
                                       ['reference_tick_s_by_case'],
               'decks': len(DECKS), 'deck_directory': 'spectre/dd1_d7c_b_prep',
               'cases_in_schedule': len(SCHEDULE.read_delivered()[0]),
               'synthetic_cases': len(CASES.run()),
               'windows_declared': len(SCHEDULE.read_delivered()[1]),
               'native_launches': 0, 'rtl_simulations': 0, 'oa_writes': 0, 'native_preflights': 0,
               'credential_reads': 0, 'guest_connections': 0,
               'electrical_results': 'NONE: every number in this record is text, arithmetic, table '
                                     'shape or Git identity; the synthetic measurement results are '
                                     'labelled SYNTHETIC_NOT_MEASURED'}
    disk_gates, disk_frozen, disk_git, disk_identity = tables_on_disk(out_dir)
    recheck, recheck_facts = record_rules(disk_gates, disk_frozen, disk_git, disk_identity, out_dir,
                                          summary_exists=False)
    summary['published_record_recheck'] = {
        'problems': recheck[:12], 'facts': recheck_facts,
        'verdict': 'PASS' if not recheck else 'FAIL',
        'note': 'judged over the bytes as published, before this summary existed, and with no revision '
                'binding: this run rewrites the R2 report after measuring the tip. A reviewer who wants '
                'the Git binding re-runs: python scripts/dd1_d7c_b_prep_r2_verify.py is the entry, or '
                'python scripts/dd1_d7c_a_r2_record_check.py --record results/evidence/<run_id> '
                '--git-ref <that commit> --source-root <work tree at that commit>, which will report the '
                'round-bound names this round renamed and nothing else'}
    print('GATE %-38s %s %s' % ('published_record_recheck',
                                summary['published_record_recheck']['verdict'],
                                (recheck[:1] or ['no semantic problem'])[0][:110]))
    summary['verdict'] = 'FAIL' if (failures or recheck) else (
        'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES' if informational else 'PASS')
    with io.open(os.path.join(out_dir, 'verification_summary.json'), 'wb') as handle:
        handle.write((json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    print('D7C_B_PREP_R2_VERIFY %s -> %s (%d gates, failed: %s, skipped: %s, read back: %d)'
          % (summary['verdict'], out_dir.replace(os.sep, '/'), len(results),
             ','.join(failures) or 'none', ','.join(informational) or 'none', len(read_back)))
    return 1 if (failures or recheck) else 0


def _deck_read_gate(out_json):
    """the independent deck reading is unchanged this round, so it is re-run, not re-written"""
    argv = [sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_r1_deck_read.py'), '--check',
            '--counterexample', '--json', out_json]
    code, text = PREP.run(argv)
    tail = text.strip().split('\n')[-1][:200] if text.strip() else ''
    return {'gate': 'deck_read_still_clean',
            'command': 'python dd1_d7c_b_prep_r1_deck_read.py --check --counterexample --json <out>',
            'rc': code, 'expected_rc': '0', 'verdict': tail,
            'verdict_state': 'PASS' if code == 0 else 'FAIL'}, text


def tables_on_disk(directory):
    """the published-bytes form of the four tables, for the recheck over what was written"""
    return (rows_of(os.path.join(directory, 'commands.csv')),
            rows_of(os.path.join(directory, 'frozen_comparison.csv')),
            rows_of(os.path.join(directory, 'git_checks.csv')),
            rows_of(os.path.join(directory, 'source_identity.csv')))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
