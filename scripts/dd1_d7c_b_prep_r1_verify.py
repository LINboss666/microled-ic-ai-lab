#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_r1_verify.py -- the R1 gates over the repaired bytes, published as a new record.

DATA-7C-B-PREP-R1 sections 7 and 8. This is a separate entry point on purpose. The PREP round's
`dd1_d7c_b_prep_verify.py` renders its tables into `reports/dd1_d7c_b_prep_report.md` and digests
`reports/agent_handoffs/DATA-7C-B-PREP.{json,md}`; running it again here would rewrite a report and a
handoff that an independent review has already judged and that section 7 freezes. The brief says to add
an explicit R1 entry and use a new handoff rather than rewriting history, which is what this file does:
it shares the PREP round's *mechanics* (its git helpers, its frozen-row comparison, its throw-away
clone, its record checker) and replaces its *evidence set* with the four repair families, the frozen
reviewer instrument run twice on the same bytes it was written for, and the independent deck reading.

The ordering is deliberate: the repair is committed first, so every range and blob this record measures
is a real committed range, and only then is the record directory written. Nothing here starts a
simulator, an RTL simulation, an OA write or a preflight; every electrical result stays NOT_RUN and
every sample in the synthetic family stays labelled SYNTHETIC_NOT_MEASURED.

    python scripts/dd1_d7c_b_prep_r1_verify.py                     # publish a new record
    python scripts/dd1_d7c_b_prep_r1_verify.py --handoff-check      # judge the R1 handoff alone
    python scripts/dd1_d7c_b_prep_r1_verify.py --out <new directory>
"""

from __future__ import absolute_import, print_function

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_offline_check as CHECK                 # noqa: E402  (rows_write, sha_file)
import dd1_d7c_a_r2_record_check as RECORD             # noqa: E402  (the published-record reader)
import dd1_d7c_a_verify as A_VERIFY                    # noqa: E402  (the record tool's own whitelist)
import dd1_d7c_b_prep_cases as CASES                   # noqa: E402
import dd1_d7c_b_prep_contract as CONTRACT             # noqa: E402
import dd1_d7c_b_prep_deckgen as DECKGEN               # noqa: E402
import dd1_d7c_b_prep_r1_deck_read as DECKREAD         # noqa: E402
import dd1_d7c_b_prep_schedule as SCHEDULE             # noqa: E402
import dd1_d7c_b_prep_verify as PREP                   # noqa: E402  (mechanics only, shared)

TASK_ID = 'DATA-7C-B-PREP-R1'
BASE_P = CONTRACT.BASE_PREP
BASE_R2 = CONTRACT.BASE_R2
BRANCH = 'poc/data-pam-d7c-b-prep-r1'
REVIEW_DIR = os.path.join(ROOT, 'review', CONTRACT.REVIEW_ID, 'reviewer')
INSTRUMENT = os.path.join(REVIEW_DIR, 'probe_prep_gaps.py')
FAMILIES = ('F1_PAM_bit_order_and_high_level', 'F2_PWL_and_window_physics',
            'F3_measurement_entry_wiring', 'F4_native_deck_known_contract')
# the record this round inherits from, kept exactly as it was published and judged
PREP_RECORD = 'results/evidence/dd1_d7c_b_prep_20261023_185017_03cccc'
PREP_ABORTED = PREP.SUPERSEDED_RECORD
R1_REPORT = 'reports/dd1_d7c_b_prep_review_fix_r1.md'
HANDOFF_SELF = ('reports/agent_handoffs/DATA-7C-B-PREP-R1.json',
                'reports/agent_handoffs/DATA-7C-B-PREP-R1.md')
RENDERED_BY_THIS_RUN = (R1_REPORT,)
# section 7: the six PREP scripts, the four input tables, the fifteen decks, the contract document
ALLOWED_MODIFIED = ('scripts/dd1_d7c_b_prep_', 'tests/dd1_d7c_b_prep/', 'spectre/dd1_d7c_b_prep/',
                    'reports/dd1_d7c_b_prep_contract.md')
NEW_PREFIXES = ('scripts/dd1_d7c_b_prep_r1_', 'results/evidence/dd1_d7c_b_prep_r1_')
NEW_EXACT = ['reports/tasks/DATA-7C-B-PREP-R1.md', R1_REPORT,
             'reports/agent_handoffs/DATA-7C-B-PREP-R1.md',
             'reports/agent_handoffs/DATA-7C-B-PREP-R1.json']
# surfaces section 7 freezes, each named so a reviewer can see what was compared rather than trusting
# a directory sweep
FROZEN_SURFACES = (
    ('four_candidate_DUT_netlists', list(CONTRACT.FROZEN_CANDIDATE_DUT)),
    ('accepted_DATA7B_measurement_and_run_core', ['scripts/dd1_d7b_measure.py',
                                                   'scripts/dd1_d7b_run.py',
                                                   'spectre/current_probe_syntax.scs']),
    ('shared_tools_safety_and_provenance', list(PREP.SHARED_TOOLS)),
    ('PREP_record_as_published', [PREP_RECORD, PREP_ABORTED]),
    ('earlier_round_record_dirs', list(PREP.PREVIOUS_RECORDS)),
    ('PREP_report_handoff_and_task_book', ['reports/dd1_d7c_b_prep_report.md',
                                           'reports/agent_handoffs/DATA-7C-B-PREP.md',
                                           'reports/agent_handoffs/DATA-7C-B-PREP.json',
                                           'reports/tasks/DATA-7C-B-PREP.md']),
    ('R2_and_earlier_plan_and_decks', ['tests/dd1_d7c_a/native_case_plan.csv',
                                       'scripts/dd1_d7c_a_r2_plan.py']),
)
TABLE_SPECS = {
    'commands.csv': (['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], 'gate', ()),
    'frozen_comparison.csv': (['comparison', 'surface', 'paths_compared', 'mismatched',
                               'first_mismatches', 'expectation', 'enforced'], 'surface',
                              ('first_mismatches',)),
    'git_checks.csv': (['gate', 'command', 'rc', 'lines', 'scope'], 'gate', ()),
    'source_identity.csv': (['role', 'path', 'bytes', 'sha256'], 'path', ()),
    'instrument_P.json': None, 'instrument_r1.json': None, 'synthetic_cases.json': None,
    'deck_read.json': None, 'deck_read_on_P.json': None, 'deck_observe.json': None,
    'selftest.json': None, 'selftest_this_tree.json': None, 'ranges.json': None,
    'verification_summary.json': None,
}


def probe_gate(name, root, out_json, expect_reproduced):
    """run the reviewer's instrument unmodified and read the four families item by item

    The aggregate `rc` is never the verdict: rc=0 means all four reproduce, rc=1 means at least one
    does not, rc=2 means the instrument itself failed. A repaired tree must give rc=1 with every
    family individually not reproduced and with a non-empty field set, and a refusal to parse is
    reported as such rather than as a fix.
    """
    expected_rc = 0 if expect_reproduced else 1
    label = 'the P extraction' if root.endswith('P') else 'this tree'
    command = 'python review/%s/reviewer/probe_prep_gaps.py --root %s --out <json>' % (
        CONTRACT.REVIEW_ID, label)
    if not (os.path.isfile(INSTRUMENT) and os.path.isdir(root)):
        return {'gate': name, 'command': command, 'rc': 'not_run', 'expected_rc': str(expected_rc),
                'verdict': 'NOT_ATTEMPTED: the instrument or its target tree is absent',
                'verdict_state': 'NOT_ATTEMPTED'}, {}
    code, _text = PREP.run([sys.executable, INSTRUMENT, '--root', root, '--out', out_json])
    normalised = PREP._lf_in_place(out_json)
    try:
        payload = json.loads(io.open(out_json, encoding='utf-8').read())
    except (ValueError, IOError) as error:
        return {'gate': name, 'command': command, 'rc': code, 'expected_rc': str(expected_rc),
                'verdict': 'no readable JSON: %s' % str(error)[:120], 'verdict_state': 'FAIL'}, {}
    findings = payload.get('findings') or {}
    items, bad = [], []
    for family in sorted(findings):
        reproduced = bool(findings[family].get('reproduced'))
        empty = sorted(key for key, value in findings[family].items()
                       if isinstance(value, list) and not value)
        meets = reproduced == expect_reproduced
        items.append({'family': family, 'reproduced': reproduced, 'meets_expectation': meets,
                      'empty_lists': empty})
        if not meets:
            bad.append(family)
    complete = sorted(findings) == sorted(FAMILIES)
    zero_costs = all(payload.get(key) == 0 for key in ('NEW_SPECTRE_LAUNCHES', 'NEW_RTL_SIMULATIONS',
                                                       'NEW_OA_WRITES'))
    aggregate = payload.get('all_four_families_reproduced')
    state = ('PASS' if (code == expected_rc and not bad and complete and zero_costs
                        and aggregate is expect_reproduced and payload.get('instrument_sha256'))
             else 'FAIL')
    return {'gate': name, 'command': 'python %s --root %s --out %s'
            % (os.path.basename(INSTRUMENT), label, os.path.basename(out_json)),
            'rc': code, 'expected_rc': str(expected_rc),
            'verdict': 'four families read individually: %s; aggregate all_four=%s expected %s; '
                       'instrument bytes sha256=%s; zero costs=%s; output newlines normalised=%s'
                       % (';'.join('%s=%s' % (item['family'][1:3],
                                               'reproduced' if item['reproduced'] else 'closed')
                                   for item in items), aggregate, expect_reproduced,
                          (payload.get('instrument_sha256') or 'missing')[:12], zero_costs, normalised),
            'verdict_state': state, 'families': items}, payload


def deck_read_gate(name, arguments, out_json, expected_rc):
    """the independent reader, run as a command so the reviewer can re-run it verbatim"""
    command = 'python dd1_d7c_b_prep_r1_deck_read.py %s%s' % (
        ' '.join('--%s' % flag for flag in arguments), ' --json <out>' if out_json else '')
    argv = [sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_r1_deck_read.py')] + \
           ['--%s' % flag for flag in arguments]
    if out_json:
        argv.extend(['--json', out_json])
    code, text = PREP.run(argv)
    tail = text.strip().split('\n')[-1][:200] if text.strip() else ''
    return {'gate': name, 'command': command, 'rc': code, 'expected_rc': str(expected_rc),
            'verdict': tail, 'verdict_state': 'PASS' if code == expected_rc else 'FAIL'}, text


def range_counts(from_rev, to_rev):
    """added / changed / deleted paths and commits over a real committed range"""
    body = PREP.git('diff', '--name-status', '%s..%s' % (from_rev, to_rev)).decode('utf-8', 'replace')
    counts = {'added': 0, 'changed': 0, 'deleted': 0, 'renamed': 0}
    for line in body.split('\n'):
        if not line.strip():
            continue
        flag = line.split('\t')[0]
        if flag.startswith('A'):
            counts['added'] += 1
        elif flag.startswith('D'):
            counts['deleted'] += 1
        elif flag.startswith('R'):
            counts['renamed'] += 1
        elif flag.startswith('M'):
            counts['changed'] += 1
    commits = int(PREP.git('rev-list', '--count', '%s..%s' % (from_rev, to_rev)).decode().strip())
    counts['commits'] = commits
    return counts


def comparisons_r1(tip):
    """the frozen surfaces against the base the review judged, over explicit path lists"""
    base = PREP.blob_index(BASE_P)
    head = PREP.blob_index(tip)
    p_paths = sorted(base)
    added = sorted(set(head) - set(base))
    removed = sorted(set(base) - set(head))
    modified = sorted(path for path in p_paths if path in head and base[path] != head[path])
    editable = [path for path in p_paths
                if path.startswith(ALLOWED_MODIFIED) or path in ('reports/dd1_d7c_b_prep_contract.md',)]
    outside = [path for path in p_paths if path not in editable]
    unexpected_new = [path for path in added
                      if not path.startswith(NEW_PREFIXES) and path not in NEW_EXACT]
    rows = [PREP._compare('r1', 'every_P_path_outside_the_allowed_edit_surface', outside, base, head,
                          'identical'),
           PREP._compare('r1', 'allowed_edit_surface_modified_this_round',
                         [path for path in editable if path in modified], base, head,
                         'informational_listing')]
    for surface, paths in FROZEN_SURFACES:
        rows.append(PREP._compare('r1', surface, paths, base, head, 'identical'))
    rows.append({'comparison': 'r1', 'surface': 'paths_added_this_round',
                 'paths_compared': len(added), 'mismatched': len(unexpected_new),
                 'first_mismatches': ';'.join(unexpected_new[:3]),
                 'expectation': 'only_allowed_new', 'enforced': 'yes'})
    rows.append({'comparison': 'r1', 'surface': 'paths_removed_vs_P',
                 'paths_compared': len(removed), 'mismatched': len(removed),
                 'first_mismatches': ';'.join(removed[:3]), 'expectation': 'none_removed',
                 'enforced': 'yes'})
    rows.append({'comparison': 'r1', 'surface': 'paths_modified_vs_P',
                 'paths_compared': len(modified), 'mismatched': 0,
                 'first_mismatches': ';'.join(modified[:3]), 'expectation': 'informational_listing',
                 'enforced': 'no'})
    counts = {'added': added, 'removed': removed, 'modified': modified, 'base': len(p_paths),
              'tip': len(head)}
    return rows, counts


def record_selftest_r1(out_dir, scratch):
    """the record tool's own selftest, read in the tree it was written for and again here

    Its `frozen_gate_counts_only_enforced_rows` case builds clean and dirty tables from the real
    comparison rows of the tree it runs in, and the A-round whitelist has never heard of the paths
    this round adds. So the gate measures both readings and passes only when the clone-at-P reading
    is PASS and the in-tree failure is fully attributed to paths section 7 allows.
    """
    command = ('python dd1_d7c_a_r1_selftest.py --json <out>/selftest.json run in a throw-away shared '
               'clone checked out at %s, and again with --json <out>/selftest_this_tree.json in this '
               'work tree' % BASE_P[:12])
    clone = os.path.join(scratch, 'clone_p')
    refs_before = PREP._refs_digest()
    ready, _text = PREP._clone_at(BASE_P, clone)
    refs_after = PREP._refs_digest()
    if not ready:
        return {'gate': 'record_tool_selftest', 'command': command, 'rc': 'abort',
                'expected_rc': '0',
                'verdict': 'NOT_ATTEMPTED: the throw-away clone at %s could not be prepared'
                           % BASE_P[:12], 'verdict_state': 'NOT_ATTEMPTED'}
    clone_json = os.path.join(out_dir, 'selftest.json')
    tree_json = os.path.join(out_dir, 'selftest_this_tree.json')
    clone_code, _clone_text = PREP.run([sys.executable, os.path.join(clone, 'scripts',
                                                                     'dd1_d7c_a_r1_selftest.py'),
                                        '--json', clone_json])
    tree_code, _tree_text = PREP.run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_r1_selftest.py'),
                                      '--json', tree_json])
    normalised = [PREP._lf_in_place(clone_json), PREP._lf_in_place(tree_json)]
    clone_payload = json.loads(io.open(clone_json, encoding='utf-8').read())
    tree_payload = json.loads(io.open(tree_json, encoding='utf-8').read())
    base_index = PREP.blob_index(BASE_P)
    head_index = PREP.blob_index(PREP.git('rev-parse', 'HEAD').decode().strip())
    same_tool = base_index.get('scripts/dd1_d7c_a_r1_selftest.py') == \
        head_index.get('scripts/dd1_d7c_a_r1_selftest.py')
    offenders = [row['case'] for row in tree_payload.get('results', []) if row['state'] != 'PASS']
    added = sorted(set(head_index) - set(PREP.blob_index(PREP.REVIEWED_T)))
    refused = [path for path in added
               if path not in A_VERIFY.ALLOWED_NEW_EXACT and
               not any(path.startswith(pre) for pre in A_VERIFY.ALLOWED_NEW_PREFIX)]
    allowed_here = [path for path in refused
                    if path.startswith(PREP.NEW_PREFIXES) or path in PREP.NEW_EXACT
                    or path.startswith(NEW_PREFIXES) or path in NEW_EXACT]
    attributed = bool(refused) and len(refused) == len(allowed_here) and \
        offenders == ['frozen_gate_counts_only_enforced_rows']
    good = (clone_code == 0 and clone_payload.get('verdict') == 'PASS' and same_tool and attributed
            and refs_before == refs_after and len(clone_payload.get('results', [])) == 9)
    return {'gate': 'record_tool_selftest', 'command': command, 'rc': clone_code,
            'expected_rc': '0',
            'verdict': 'clone_at_P %s (%d cases, failures: %s); this_tree rc=%d %s, failing cases %s, '
                       'all %d paths the A-round whitelist refuses here are paths the PREP or R1 '
                       'brief allows=%s; same tool bytes=%s; source refs unchanged=%s; newlines '
                       'normalised=%s'
                       % (clone_payload.get('verdict'), len(clone_payload.get('results', [])),
                          ','.join(clone_payload.get('failures', [])) or 'none', tree_code,
                          tree_payload.get('verdict'), ','.join(offenders) or 'none', len(refused),
                          bool(attributed), same_tool, refs_before == refs_after,
                          [entry.get('crlf_before') for entry in normalised]),
            'verdict_state': 'PASS' if good else 'FAIL'}


def replay_r1(directory):
    """the whole chain, run in a fresh `git archive` extraction of the tip"""
    plan = [('contract_check', 'dd1_d7c_b_prep_contract.py', ('--check',), (0,)),
            ('schedule_check', 'dd1_d7c_b_prep_schedule.py', ('--check',), (0,)),
            ('deck_check', 'dd1_d7c_b_prep_deckgen.py', ('--check',), (0,)),
            ('deck_regenerate', 'dd1_d7c_b_prep_deckgen.py', ('--to', 'regen'), (0,)),
            ('synthetic_cases', 'dd1_d7c_b_prep_cases.py', (), (0,)),
            ('deck_read_check', 'dd1_d7c_b_prep_r1_deck_read.py', ('--check',), (0,)),
            ('deck_read_negatives', 'dd1_d7c_b_prep_r1_deck_read.py', ('--counterexample',), (0,)),
            ('deck_read_observe', 'dd1_d7c_b_prep_r1_deck_read.py', ('--observe',), (0,)),
            ('offline', 'dd1_d7c_a_offline_check.py', ('--json', 'out.json'), (0,)),
            ('guards', 'dd1_d7c_a_guards.py', ('--json', 'out.json'), (0,)),
            ('r2_plan_check', 'dd1_d7c_a_r2_plan.py', ('--check',), (0,)),
            ('sign_check', 'dd1_d7c_a_r2_sign_check.py', (), (0,)),
            ('record_probes', 'dd1_d7c_a_r2_record_probes.py', (), (0,)),
            ('record_selftest', 'dd1_d7c_a_r1_selftest.py', ('--json', 'self.json'), (0, 2)),
            ('reviewer_instrument', INSTRUMENT, ('--root', '.'), (1,))]
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


def handoff_check_r1():
    """the R1 handoff is judged against its own structure, and cannot digest what it rewrites"""
    path = os.path.join(ROOT, 'reports', 'agent_handoffs', 'DATA-7C-B-PREP-R1.json')
    if not os.path.isfile(path):
        return ['DATA-7C-B-PREP-R1.json is not written yet']
    payload = json.loads(io.open(path, encoding='utf-8').read())
    problems = []
    for key in ('schema_version', 'task_id', 'base_sha', 'branch', 'repository', 'scope',
                'contract_state', 'review_verdict', 'repairs', 'instrument_reproduction',
                'source_identity', 'costs', 'boundaries', 'not_run', 'stop_reason',
                'known_limitations', 'remote_readback', 'range_counts_correction'):
        if key not in payload:
            problems.append('missing field %s' % key)
    if payload.get('task_id') != TASK_ID:
        problems.append('task_id is %r, not %r' % (payload.get('task_id'), TASK_ID))
    if payload.get('base_sha') != BASE_P:
        problems.append('base_sha is not the PREP tip the review judged')
    if payload.get('branch') != BRANCH:
        problems.append('branch is %r, not %r' % (payload.get('branch'), BRANCH))
    if payload.get('contract_state') != CONTRACT.CONTRACT_STATE:
        problems.append('the handoff moved the contract state off %s' % CONTRACT.CONTRACT_STATE)
    for key in ('new_spectre_launches', 'new_rtl_simulations', 'new_oa_writes',
                'new_native_preflights'):
        value = (payload.get('costs') or {}).get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            problems.append('costs.%s must be an integer 0, found %r' % (key, value))
    if len(payload.get('repairs') or ()) != len(FAMILIES):
        problems.append('the handoff lists %r repairs for %d families'
                        % (sorted(payload.get('repairs') or ()), len(FAMILIES)))
    for entry in (payload.get('source_identity') or {}).get('delivered', []) + \
            (payload.get('source_identity') or {}).get('read_only_inputs', []):
        rel = str(entry.get('path', ''))
        if rel in HANDOFF_SELF:
            problems.append('%s is listed inside the handoff it lives in' % rel)
            continue
        if rel in RENDERED_BY_THIS_RUN:
            problems.append('%s is digested by the handoff, but this run rewrites that file after the '
                            'handoff is written' % rel)
            continue
        target = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.isfile(target):
            problems.append('source_identity names %s which is not on disk' % rel)
            continue
        if entry.get('sha256') != CHECK.sha_file(target):
            problems.append('%s digest in the handoff does not match the bytes on disk' % rel)
        if int(entry.get('bytes', -1)) != os.path.getsize(target):
            problems.append('%s byte count in the handoff does not match the bytes on disk' % rel)
    blob = json.dumps(payload, ensure_ascii=False)
    for forbidden in ('PAM_IMPLEMENTED=PASS', 'CURRENT_MEASURED=PASS', 'MEASURED_PASS',
                      'CONTRACT_STATE=USER_APPROVED', 'NATIVE_GO'):
        if forbidden in blob:
            problems.append('the handoff contains the forbidden claim %r' % forbidden)
    for key, value in (payload.get('not_run') or {}).items():
        if value not in ('NOT_RUN', 'NOT_VERIFIED', 'NOT_DEFINED', 'NOT_FROZEN', 'NOT_AUTHORISED'):
            problems.append('not_run.%s must be a marker, found %r' % (key, value))
    if not (payload.get('known_limitations') and payload.get('instrument_reproduction')):
        problems.append('a repair handoff that lists no limitation and no instrument reading has not '
                        'looked at what it changed')
    return problems


def _table(lines, header, rows):
    lines.append('| ' + ' | '.join(header) + ' |')
    lines.append('|' + '|'.join(['---'] * len(header)) + '|')
    for row in rows:
        lines.append('| ' + ' | '.join(str(value).replace('|', '/') for value in row) + ' |')


def render_report(out_dir, results, rows, git_rows, counts, ranges, schedule_rows, case_rows,
                  observation, families_before, families_after, tip):
    """seven machine-written tables in the R1 report; the prose above them stays hand-written"""
    report = os.path.join(ROOT, R1_REPORT.replace('/', os.sep))
    lines = ['| 门 | 命令 | rc | 期望 | 判决 | 依据 |', '|---|---|---|---|---|---|']
    for row in results:
        lines.append('| `%s` | `%s` | %s | %s | %s | %s |'
                     % (row['gate'], row['command'][:72].replace('|', '/'), row['rc'],
                        row['expected_rc'], row['verdict_state'],
                        str(row['verdict'])[:150].replace('|', '/')))
    lines.append('')
    lines.append('渲染发生在 `%s` 之后、`record_semantics` 与 `published_record_recheck` 判定之前；'
                  '本表不含本轮记录的摘要（它写于本文件之后）。' % tip[:12])
    PREP._splice(report, '<!-- BEGIN 7CB_R1 GATES -->', '<!-- END 7CB_R1 GATES -->', lines)

    rlines = []
    _table(rlines, ['族', '评审读到的事实', '本轮改法', 'P 上复现', 'R1 上复现', 'R1 判据'],
           [(entry['id'], entry['reviewer_fact'][:90], entry['repair'][:90],
             'yes' if families_before.get(entry['id']) else 'no',
             'yes' if families_after.get(entry['id']) else 'no',
             {'F1': 'deck_read 独立读回 8 码与三级电平',
              'F2': 'deck_read 独立插值 50% 沿、码变段全低、漏流子窗',
              'F3': '25 例合成正反例全走真实入口',
              'F4': 'deck_read 按语句解析 temp/analysis/PWL/probe'}[entry['id']])
            for entry in CONTRACT.REPAIRS_R1])
    PREP._splice(report, '<!-- BEGIN 7CB_R1 REPAIRS -->', '<!-- END 7CB_R1 REPAIRS -->', rlines)

    dlines = ['| 例 | 类型 | 码 | 半沿 (ns) | 偏移 (ns) | 平台首 (ns) | 全窗 (ns) | 平坦 (ns) | '
              '纯关 (ns) | 漏流子窗 | 换码 (ns) | stop | maxstep | 配对 | 结果 |',
              '|---|---|---|---:|---:|---|---|---|---|---|---|---:|---:|---|---|']
    for row in schedule_rows:
        dlines.append('| `%s` | %s | `%s` | %s | %s | %s | %s | %s-%s | %s | %s | %s | %s | %s | %s '
                      '| %s |' % (row['case_id'], row['class'], row['pam_code'], row['edge_ns'],
                                  row['offset_applied_ns'], row['platform_start_ns'].split(';')[0],
                                  row['full_window_start_ns'].split(';')[0],
                                  row['flat_start_ns'].split(';')[0], row['flat_stop_ns'].split(';')[0],
                                  row['pure_off_start_ns'].split(';')[0], row['leak_window_ns'],
                                  row['code_change_ns'], row['stop_ns'], row['maxstep_ns'],
                                  row['paired_case'] or '-', row['result']))
    PREP._splice(report, '<!-- BEGIN 7CB_R1 DECKS -->', '<!-- END 7CB_R1 DECKS -->', dlines)

    clines = []
    _table(clines, ['例', '类型', '判决', '观察到的依据', '说明'],
           [(row['case'], row['kind'], row['verdict'],
             (row['detail'] or '; '.join(row['problems']))[:120], row['meaning'][:110])
            for row in case_rows])
    PREP._splice(report, '<!-- BEGIN 7CB_R1 CASES -->', '<!-- END 7CB_R1 CASES -->', clines)

    olines = []
    _table(olines, ['读数', '值'],
           [('deck 数', observation['decks_read']),
            ('窗类型计数', json.dumps(observation['windows_by_kind'], sort_keys=True)),
            ('PAM 变化段总数', observation['pam_changing_segments_total']),
            ('半轨交叉总数', observation['half_rail_crossings_total']),
            ('读到的 PWL 信号', ', '.join(observation['pwl_signals_read']))])
    olines.append('')
    olines.append('独立读盘由 `scripts/dd1_d7c_b_prep_r1_deck_read.py` 完成：它自带解析器，不 '
                  'import 生成器与测量核，位权按 `pam0=1/pam1=2/pam2=4` 的字面常量写死。空问题表是'
                  '在 %d 个 emission 窗与 %d 个 PAM 变化段上量出来的，不是沉默。'
                  % (observation['windows_by_kind'].get('emission', 0),
                     observation['pam_changing_segments_total']))
    PREP._splice(report, '<!-- BEGIN 7CB_R1 READ -->', '<!-- END 7CB_R1 READ -->', olines)

    glines = []
    _table(glines, ['区间', '新增', '变更', '删除', '重命名', '提交数', '说明'],
           [('`%s..%s`' % (BASE_R2[:12], BASE_P[:12]), ranges['R2..P']['added'],
             ranges['R2..P']['changed'], ranges['R2..P']['deleted'], ranges['R2..P']['renamed'],
             ranges['R2..P']['commits'],
             '本轮基线区间，由 Git 重算；PREP 回执写的 68 新增在此更正为 %d'
             % ranges['R2..P']['added']),
            ('`%s..HEAD`' % BASE_P[:12], ranges['P..HEAD']['added'], ranges['P..HEAD']['changed'],
             ranges['P..HEAD']['deleted'], ranges['P..HEAD']['renamed'], ranges['P..HEAD']['commits'],
             'R1 修补区间，度量于运行本入口时已提交的 HEAD=%s；记录目录本身在下一个提交里'
             % tip[:12])])
    PREP._splice(report, '<!-- BEGIN 7CB_R1 RANGES -->', '<!-- END 7CB_R1 RANGES -->', glines)

    flines = ['| 比较 | 面 | 路径数 | 计数 | 前若干 | 期望 | 计入闸 |',
              '|---|---|---:|---:|---|---|---|']
    for row in rows:
        flines.append('| %s | `%s` | %s | %s | %s | `%s` | %s |'
                      % (row['comparison'], row['surface'], row['paths_compared'], row['mismatched'],
                         str(row['first_mismatches'])[:90].replace('|', '/'), row['expectation'],
                         row['enforced']))
    PREP._splice(report, '<!-- BEGIN 7CB_R1 FROZEN -->', '<!-- END 7CB_R1 FROZEN -->', flines)
    return report


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--handoff-check', action='store_true')
    parser.add_argument('--out', default='')
    parser.add_argument('--json', default='')
    arguments = parser.parse_args(argv)
    if arguments.handoff_check:
        problems = handoff_check_r1()
        print('D7C_B_PREP_R1_HANDOFF %s %s' % ('PASS' if not problems else 'FAIL',
                                               '; '.join(problems[:4]) if problems else
                                               'fields, digests against disk, zero costs, no self-'
                                               'listing and no forbidden claim'))
        return 0 if not problems else 1
    out_dir = os.path.abspath(arguments.out) if arguments.out else os.path.join(
        ROOT, 'results', 'evidence', '%s_%s_%06x' % (
            TASK_ID.lower().replace('-', '_'),
            time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
            int(hashlib.sha256(os.urandom(8)).hexdigest()[:6], 16)))
    if os.path.isdir(out_dir):
        raise SystemExit('D7C_B_PREP_R1_VERIFY_REFUSED %s already exists; published records are never '
                         'overwritten, choose a new run id' % out_dir)
    tip = PREP.git('rev-parse', 'HEAD').decode().strip()
    os.makedirs(out_dir)
    results = []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-b-r1-')
    try:
        p_dir = os.path.join(scratch, 'P')
        os.makedirs(p_dir)
        extracted_p = PREP.extract(BASE_P, p_dir)
        first, before = probe_gate('reviewer_instrument_on_P_base', p_dir,
                                   os.path.join(out_dir, 'instrument_P.json'), True)
        results.append(first)
        second, after = probe_gate('reviewer_instrument_on_r1_bytes', ROOT,
                                   os.path.join(out_dir, 'instrument_r1.json'), False)
        results.append(second)
        same_bytes = (before.get('instrument_sha256') == after.get('instrument_sha256') ==
                      hashlib.sha256(io.open(INSTRUMENT, 'rb').read()).hexdigest())
        results.append({'gate': 'reviewer_instrument_bytes_unchanged',
                        'command': 'sha256 of review/%s/reviewer/probe_prep_gaps.py and of the two '
                                   'runs' % CONTRACT.REVIEW_ID,
                        'rc': 0 if same_bytes else 1, 'expected_rc': '0',
                        'verdict': 'the instrument that judged the PREP bytes is the instrument that '
                                   'judged these; sha256=%s'
                                   % (after.get('instrument_sha256') or 'missing'),
                        'verdict_state': 'PASS' if same_bytes else 'FAIL'})
        for row in results:
            print('GATE %-38s %s %s' % (row['gate'], row['verdict_state'], str(row['verdict'])[:90]))

        gate, text = deck_read_gate('deck_read_on_delivered_bytes', ('check', 'observe'),
                                    os.path.join(out_dir, 'deck_read.json'), 0)
        results.append(gate)
        print('GATE %-38s %s %s' % (gate['gate'], gate['verdict_state'], gate['verdict'][:90]))
        gate, _text = deck_read_gate('deck_read_negatives_named', ('counterexample',), '', 0)
        results.append(gate)
        print('GATE %-38s %s %s' % (gate['gate'], gate['verdict_state'], gate['verdict'][:90]))
        observation = DECKREAD.observe(ROOT)
        with io.open(os.path.join(out_dir, 'deck_observe.json'), 'wb') as handle:
            handle.write((json.dumps(observation, indent=1, sort_keys=True) + '\n').encode('utf-8'))
        gate, _text = deck_read_gate('deck_read_refuses_the_base_tree', ('check',),
                                     os.path.join(out_dir, 'deck_read_on_P.json'), 1)
        gate['command'] = 'python dd1_d7c_b_prep_r1_deck_read.py --check --root <P extraction>'
        problems = (json.loads(io.open(os.path.join(out_dir, 'deck_read_on_P.json'),
                                       encoding='utf-8').read()) or {}).get('problems', [])
        names_missing = bool(problems) and 'contract of this tree does not declare' in problems[0]
        gate['verdict'] = '%s; the reader states what it cannot read instead of inventing it: %s' % (
            gate['verdict'][:120], problems[0][:150] if problems else 'no problem reported')
        gate['verdict_state'] = 'PASS' if gate['rc'] == 1 and names_missing else 'FAIL'
        results.append(gate)
        print('GATE %-38s %s %s' % (gate['gate'], gate['verdict_state'], gate['verdict'][:90]))

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
                                        results[-1]['verdict'][:90]))
        code, body = PREP.run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_deckgen.py'),
                               '--to', os.path.join(scratch, 'regen')])
        results.append(PREP._gate('deck_regenerated_from_sources',
                                  'python dd1_d7c_b_prep_deckgen.py --to <scratch>', code, '0', body))
        print('GATE %-38s %s %s' % ('deck_regenerated_from_sources',
                                    results[-1]['verdict_state'], results[-1]['verdict'][:90]))
        code, body = PREP.run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_cases.py'),
                               '--json', os.path.join(out_dir, 'synthetic_cases.json')])
        results.append(PREP._gate('synthetic_measure_cases',
                                  'python dd1_d7c_b_prep_cases.py --json <out>', code, '0', body))
        print('GATE %-38s %s %s' % ('synthetic_measure_cases', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        results.append(record_selftest_r1(out_dir, scratch))
        print('GATE %-38s %s %s' % ('record_tool_selftest', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        directory = os.path.join(scratch, 'extract')
        os.makedirs(directory)
        extracted = PREP.extract(tip, directory)
        outcomes = replay_r1(directory) if extracted else []
        bad = [o for o in outcomes if not o['accepted']]
        results.append({'gate': 'fresh_extraction_replay',
                        'command': 'git archive %s | tar -x, then run every suite and the reviewer '
                                   'instrument there' % tip[:12],
                        'rc': len(bad), 'expected_rc': '0',
                        'verdict': ('; '.join('%s rc=%s %s' % (o['suite'], o['rc'], o['note'])
                                               for o in outcomes)[:400] if extracted
                                   else 'EXTRACTION_FAILED'),
                        'verdict_state': 'PASS' if extracted and not bad else 'FAIL'})
        print('GATE %-38s %s %s' % ('fresh_extraction_replay', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        problems = handoff_check_r1()
        results.append({'gate': 'handoff_structure',
                        'command': 'python dd1_d7c_b_prep_r1_verify.py --handoff-check (in process)',
                        'rc': len(problems), 'expected_rc': '0',
                        'verdict': '; '.join(problems[:3]) if problems else
                                   'fields, digests against disk, four repairs, zero costs, markers '
                                   'and forbidden claims all checked',
                        'verdict_state': 'PASS' if not problems else 'FAIL'})
        print('GATE %-38s %s %s' % ('handoff_structure', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        code, body = PREP.run([sys.executable, os.path.join(ROOT, 'scripts', 'provenance_check.py')])
        results.append(PREP._gate('provenance', 'python scripts/provenance_check.py', code, '0', body))
        print('GATE %-38s %s %s' % ('provenance', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        code, body = PREP.run([sys.executable, os.path.join(ROOT, 'scripts',
                                                            'precommit_safety_check.py'),
                               '--mode', 'history'])
        counters = {}
        for line in body.split('\n'):
            for key in ('PDK_TRACKED_FILES', 'CREDENTIAL_TRACKED_FILES'):
                if line.strip().startswith(key):
                    counters[key] = line.strip().split()[-1]
        results.append(PREP._gate('history_safety', 'python scripts/precommit_safety_check.py '
                                                    '--mode history', code, '0', body))
        results[-1]['verdict'] = '%s; counters=%s' % (results[-1]['verdict'][:150], counters or 'none')
        print('GATE %-38s %s %s' % ('history_safety', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))

        ranges = {'R2..P': range_counts(BASE_R2, BASE_P), 'P..HEAD': range_counts(BASE_P, tip)}
        with io.open(os.path.join(out_dir, 'ranges.json'), 'wb') as handle:
            handle.write((json.dumps(ranges, indent=1, sort_keys=True) + '\n').encode('utf-8'))
        git_rows = []
        for label, other in (('diff_check_P_to_HEAD', BASE_P), ('diff_check_R2_to_HEAD', BASE_R2),
                             ('diff_check_T_to_HEAD', PREP.REVIEWED_T)):
            check_code, check_body = PREP.run(['git', '-C', ROOT, 'diff', '--check',
                                               '%s..HEAD' % other])
            git_rows.append({'gate': label, 'command': 'git diff --check %s..HEAD' % other,
                             'rc': check_code,
                             'lines': len([b for b in check_body.split('\n') if b.strip()]),
                             'scope': 'committed range from %s to HEAD(%s) at %s'
                                      % (other[:12], tip[:12],
                                         time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))})
        expected_R2_P = {'added': 83, 'changed': 0, 'deleted': 0, 'commits': 15}
        measured = ranges['R2..P']
        matches = all(measured.get(key) == value for key, value in expected_R2_P.items())
        results.append({'gate': 'git_range_counts',
                        'command': 'git diff --name-status R2..P, git rev-list --count R2..P and the '
                                   'same over P..HEAD',
                        'rc': 0 if matches else 1, 'expected_rc': '0',
                        'verdict': 'R2..P added=%d changed=%d deleted=%d commits=%d (the PREP receipt '
                                   'stated 68 added, corrected here to %d); P..HEAD added=%d '
                                   'changed=%d deleted=%d commits=%d'
                                   % (measured['added'], measured['changed'], measured['deleted'],
                                      measured['commits'], measured['added'],
                                      ranges['P..HEAD']['added'], ranges['P..HEAD']['changed'],
                                      ranges['P..HEAD']['deleted'], ranges['P..HEAD']['commits']),
                        'verdict_state': 'PASS' if matches else 'FAIL'})
        print('GATE %-38s %s %s' % ('git_range_counts', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        rows, counts = comparisons_r1(tip)
        CHECK.rows_write(os.path.join(out_dir, 'frozen_comparison.csv'), RECORD.FROZEN_HEADER, rows)
        CHECK.rows_write(os.path.join(out_dir, 'git_checks.csv'), RECORD.GIT_HEADER, git_rows)
        enforced = [r for r in rows if r['enforced'] == 'yes']
        violations = sum(int(r['mismatched']) for r in enforced)
        diff_rc = max(int(r['rc']) for r in git_rows)
        results.append({'gate': 'frozen_surfaces', 'command': 'git ls-tree -r blob/mode comparison '
                            'over explicit path lists, plus git diff --check on the committed ranges',
                        'rc': violations + diff_rc, 'expected_rc': '0',
                        'verdict': 'enforced rows %d, violations %d, informational %d; added vs P %d, '
                                   'removed %d, modified %d; git diff --check P..HEAD=%s R2..HEAD=%s '
                                   'T..HEAD=%s'
                                   % (len(enforced), violations, len(rows) - len(enforced),
                                      len(counts['added']), len(counts['removed']),
                                      len(counts['modified']), git_rows[0]['rc'], git_rows[1]['rc'],
                                      git_rows[2]['rc']),
                        'verdict_state': 'PASS' if violations == 0 and diff_rc == 0 else 'FAIL'})
        print('GATE %-38s %s %s' % ('frozen_surfaces', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

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
                                   '(%s); instrument JSONs are normalised only after the parsed '
                                   'object is proven identical' % (with_cr or 'none',
                                                                   'confirmed' if writer_lf
                                                                   else 'BROKEN'),
                        'verdict_state': 'PASS' if not with_cr and writer_lf else 'FAIL'})
        print('GATE %-38s %s %s' % ('record_line_endings', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        case_rows = json.loads(io.open(os.path.join(out_dir, 'synthetic_cases.json'),
                                       encoding='utf-8').read())['results']
        families_before = dict((item['family'], item['reproduced'])
                               for item in first.get('families', []))
        families_after = dict((item['family'], item['reproduced'])
                              for item in second.get('families', []))
        schedule_rows = SCHEDULE.read_delivered()[0]
        before_text = io.open(os.path.join(ROOT, R1_REPORT.replace('/', os.sep)),
                              encoding='utf-8', newline='').read()
        render_report(out_dir, results, rows, git_rows, counts, ranges, schedule_rows, case_rows,
                      observation, families_before, families_after, tip)
        middle = io.open(os.path.join(ROOT, R1_REPORT.replace('/', os.sep)),
                        encoding='utf-8', newline='').read()
        render_report(out_dir, results, rows, git_rows, counts, ranges, schedule_rows, case_rows,
                      observation, families_before, families_after, tip)
        after_text = io.open(os.path.join(ROOT, R1_REPORT.replace('/', os.sep)),
                            encoding='utf-8', newline='').read()
        results.append({'gate': 'report_render_fixed_point',
                        'command': 'python dd1_d7c_b_prep_r1_verify.py (renders the seven tables '
                                   'twice and compares)',
                        'rc': 0 if middle == after_text else 1, 'expected_rc': '0',
                        'verdict': 'first render %s (length %+d bytes), second left it byte-identical '
                                   '(%s; length %+d bytes); the R1 report is a function of the sources '
                                   'and of the moment this run measured them'
                                   % ('changed the file' if middle != before_text else 'no change',
                                      len(middle) - len(before_text),
                                      'changed bytes' if after_text != middle else 'no change',
                                      len(after_text) - len(middle)),
                        'verdict_state': 'PASS' if middle == after_text else 'FAIL'})
        print('GATE %-38s %s %s' % ('report_render_fixed_point', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        identity = []
        for rel in sorted(counts['added']):
            if rel in HANDOFF_SELF or rel.startswith(os.path.basename(out_dir)):
                continue
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'added by R1' if rel in NEW_EXACT or
                                 any(rel.startswith(pre) for pre in NEW_PREFIXES) else
                                 'added by R1 (record)',
                                 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': CHECK.sha_file(target)})
        for rel in sorted(counts['modified']):
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'rewritten by this round; the blob at %s is the PREP form '
                                 % tip[:12] if rel in RENDERED_BY_THIS_RUN else
                                 'modified from P within the allowed edit surface',
                                 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': CHECK.sha_file(target)})
        for surface, paths in FROZEN_SURFACES:
            for rel in paths:
                target = os.path.join(ROOT, rel.replace('/', os.sep))
                if any(row['path'] == rel for row in identity) or not os.path.isfile(target):
                    continue
                if os.path.isdir(target):
                    continue
                identity.append({'role': 'frozen by section 7 (%s)' % surface, 'path': rel,
                                 'bytes': os.path.getsize(target), 'sha256': CHECK.sha_file(target)})
        for rel in HANDOFF_SELF:
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'R1 handoff, written before this record and committed with it',
                                 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': CHECK.sha_file(target)})
        for rel in PREP.SHARED_TOOLS:
            if any(row['path'] == rel for row in identity):
                continue
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'tool this round reads or reuses', 'path': rel,
                                 'bytes': os.path.getsize(target), 'sha256': CHECK.sha_file(target)})
        duplicated = sorted(set(row['path'] for row in identity
                                if [r['path'] for r in identity].count(row['path']) > 1))
        if duplicated:
            raise SystemExit('D7C_B_PREP_R1_VERIFY_REFUSED source_identity would publish %s twice'
                             % ','.join(duplicated))
        pending = [dict(row) for row in results] + [
            {'gate': 'record_semantics', 'command': 'python scripts/dd1_d7c_a_r2_record_check.py '
             '--record <this directory>', 'rc': 0, 'expected_rc': '0', 'verdict_state': 'PASS',
             'verdict': 'provisional: the semantic layer below decides this row'}]
        problems, _facts = RECORD.check_rows(pending, rows, git_rows, identity, out_dir,
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
    summary = {'task_id': TASK_ID, 'base_prep': BASE_P, 'base_r2': BASE_R2,
               'reviewed_tip_T': PREP.REVIEWED_T, 'branch': BRANCH, 'tip': tip,
               'review_package': CONTRACT.REVIEW_ID,
               'review_verdict': 'REWORK / NO_GO_PENDING_OFFLINE_REPAIR / '
                                 'CANDIDATE_DUT_REDESIGN_REQUIRED=NO',
               'identity_paths_rewritten_by_this_run': [rel for rel in RENDERED_BY_THIS_RUN],
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
               'range_counts_correction': 'the PREP receipt stated 68 added paths for R2..P; '
                                         'recomputed from Git as %d added / %d changed / %d deleted '
                                         'over %d commits'
                                         % (ranges['R2..P']['added'], ranges['R2..P']['changed'],
                                            ranges['R2..P']['deleted'], ranges['R2..P']['commits']),
               'paths_added_vs_P': counts['added'], 'paths_removed_vs_P': counts['removed'],
               'paths_modified_vs_P': counts['modified'],
               'decks': len(DECKGEN.render_all()), 'deck_directory': DECKGEN.DECK_DIR,
               'cases_in_schedule': len(SCHEDULE.read_delivered()[0]),
               'synthetic_cases': len(CASES.run()),
               'windows_declared': len(SCHEDULE.read_delivered()[1]),
               'native_launches': 0, 'rtl_simulations': 0, 'oa_writes': 0,
               'native_preflights': 0, 'credential_reads': 0, 'guest_connections': 0,
               'electrical_results': 'NONE: every number in this record is text, arithmetic, table '
                                     'shape or Git identity; the synthetic measurement results are '
                                     'labelled SYNTHETIC_NOT_MEASURED'}
    recheck, recheck_facts = RECORD.check_record(out_dir, summary_exists=False)
    summary['published_record_recheck'] = {
        'problems': recheck[:12], 'facts': recheck_facts,
        'verdict': 'PASS' if not recheck else 'FAIL',
        'note': 'judged over the bytes as published, before this summary existed, and with no '
                'revision binding: this run rewrites the R1 report after measuring the tip. A reviewer '
                'who wants the Git binding re-runs: python scripts/dd1_d7c_a_r2_record_check.py '
                '--record results/evidence/<run_id> --git-ref <the commit that publishes it> '
                '--source-root <that work tree>'}
    print('GATE %-38s %s %s' % ('published_record_recheck',
                                summary['published_record_recheck']['verdict'],
                                (recheck[:1] or ['no semantic problem'])[0][:110]))
    summary['verdict'] = 'FAIL' if (failures or recheck) else (
        'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES' if informational else 'PASS')
    with io.open(os.path.join(out_dir, 'verification_summary.json'), 'wb') as handle:
        handle.write((json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    if arguments.json:
        with io.open(arguments.json, 'wb') as handle:
            handle.write((json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                         .encode('utf-8'))
    print('D7C_B_PREP_R1_VERIFY %s -> %s (%d gates, failed: %s, read back: %d)'
          % (summary['verdict'], out_dir.replace(os.sep, '/'), len(results),
             ','.join(failures) or 'none', len(read_back)))
    return 1 if (failures or recheck) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
