#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_r2_record_check.py -- what a published DATA-7C-A record has to MEAN, not just how wide it is

R1's final read-back used the shape reader: header equality, per-line column count, non-empty fields
and a unique key. That is a real gate for a table, and it was wrongly described as proof that the
record was sound: a row reading `rc=99, expected_rc=0, verdict_state=PASS` passed it, and a record
missing a mandatory gate, or with a FAIL hidden by the summary line, passed it too. This entry keeps
the shape reader where it belongs and adds the semantic layer on top of it.

It is read-only. It writes nothing into the record, starts no simulator, touches no VM, and refuses
to reinterpret a failure as a pass.

    python scripts/dd1_d7c_a_r2_record_check.py --record results/evidence/<run_id> [--git-ref HEAD]

rc=0 means every semantic rule below held for the files on disk (and, with --git-ref, for the blobs in
that revision too). rc=1 prints each refusal on its own line.
"""

from __future__ import absolute_import, division, print_function

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dd1_d7c_a_offline_check as CHECK      # noqa: E402
import dd1_d7c_a_verify as VERIFY            # noqa: E402  (the expectation vocabulary)

COMMANDS_HEADER = ['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict']
FROZEN_HEADER = ['comparison', 'surface', 'paths_compared', 'mismatched', 'first_mismatches',
                 'expectation', 'enforced']
GIT_HEADER = ['gate', 'command', 'rc', 'lines', 'scope']
IDENTITY_HEADER = ['role', 'path', 'bytes', 'sha256']
# every one of these must appear exactly once, and none of them may be missing or NOT_ATTEMPTED
MANDATORY_GATES = ('reviewer_instrument_on_T', 'reviewer_instrument_on_fixed_bytes', 'offline_checks',
                   'counterexamples', 'record_tool_selftest', 'fresh_extraction_replay',
                   'handoff_structure', 'native_entry_refused', 'provenance', 'history_safety',
                   'frozen_surfaces', 'record_line_endings')
STATUSES = ('PASS', 'FAIL', 'INFORMATIONAL_NOT_PASS', 'SKIPPED_WITH_REASON', 'NOT_ATTEMPTED')
PASS_LIKE = ('PASS', 'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES')
BASE_SHA = 'da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb'


def _shape_read(path, header, key, optional=()):
    return CHECK.read_table(path, header, key, optional=optional)


def _rows(path, header, key, problems, optional=()):
    if not os.path.isfile(path):
        problems.append('%s is absent from the record' % os.path.basename(path))
        return []
    try:
        return _shape_read(path, header, key, optional=optional)
    except ValueError as error:
        problems.append('%s fails its own shape schema: %s' % (os.path.basename(path), error))
        return []


def gate_semantics(rows, problems):
    """a row may not claim a result its own numbers contradict"""
    names = [row['gate'] for row in rows]
    duplicates = sorted(set(n for n in names if names.count(n) > 1))
    if duplicates:
        problems.append('commands.csv repeats gate(s) %s, so "gates=N" is not a count of anything'
                        % ','.join(duplicates))
    missing = [g for g in MANDATORY_GATES if g not in names]
    if missing:
        problems.append('mandatory gate(s) absent from commands.csv: %s' % ','.join(missing))
    for row in rows:
        state, rc, expected = row['verdict_state'], row['rc'], row['expected_rc']
        label = '%s (rc=%s expected=%s state=%s)' % (row['gate'], rc, expected, state)
        if state not in STATUSES:
            problems.append('%s: %r is not one of the allowed verdict states %s'
                            % (row['gate'], state, ','.join(STATUSES)))
            continue
        if state == 'PASS':
            if re.match(r'^\d+$', str(expected)):
                if str(rc) != str(expected):
                    problems.append('%s declares PASS with rc different from its numeric expectation'
                                    % label)
            elif not str(expected).strip():
                problems.append('%s declares PASS with no stated expectation at all' % row['gate'])
            if not re.match(r'^-?\d+$', str(rc)):
                problems.append('%s has a non-numeric rc, so nothing about it can be re-checked' % label)
            # a refusal is frequently the expected outcome here (the native entry must refuse), so
            # only an outright failure word at the start of the text contradicts a PASS
            if re.match(r'^(FAIL|ERROR|ABORT|TRACEBACK)', str(row['verdict']).strip(), re.I):
                problems.append('%s says PASS while its verdict text opens with a failure'
                                % row['gate'])
        elif state == 'FAIL':
            if re.match(r'^\d+$', str(expected)) and str(rc) == str(expected):
                problems.append('%s says FAIL while rc already equals expected_rc' % label)
        elif state == 'INFORMATIONAL_NOT_PASS':
            if 'INFORMATIONAL' not in str(expected).upper():
                problems.append('%s is INFORMATIONAL_NOT_PASS but expected_rc reads %r, which invites '
                                'it to be counted as a pass' % (row['gate'], expected))
        elif state in ('SKIPPED_WITH_REASON', 'NOT_ATTEMPTED'):
            if len(str(row['verdict']).strip()) < 20:
                problems.append('%s is %s without a reason that could be checked'
                                % (row['gate'], state))
        for gate, pattern, phrase in (('counterexamples', r'not hit:\s*(.*?)\)\s*$',
                                       'un-hit counterexamples'),
                                      ('offline_checks', r'failures:\s*(.*?)\)\s*$',
                                       'failures')):
            if row['gate'] == gate and state == 'PASS':
                listed = re.search(pattern, row['verdict'].strip())
                if listed and listed.group(1).strip() not in ('none', ''):
                    problems.append('%s gate passed while its own text lists %s: %s'
                                    % (gate, phrase, listed.group(1).strip()[:80]))
    return names


def frozen_semantics(rows, gate_rows, problems):
    """the enforced/informational split has to add up, and the gate has to agree with the table"""
    enforced = [r for r in rows if r['enforced'] == 'yes']
    if not enforced:
        problems.append('frozen_comparison.csv marks no row enforced, so the gate cannot be about '
                        'anything')
    for row in rows:
        if row['enforced'] not in ('yes', 'no'):
            problems.append('%s: enforced=%r is neither yes nor no' % (row['surface'], row['enforced']))
        should = 'yes' if row['expectation'] in VERIFY.ENFORCED_EXPECTATIONS else 'no'
        if row['enforced'] != should:
            problems.append('%s declares expectation %r, which the vocabulary marks enforced=%s, but '
                            'the row says enforced=%s' % (row['surface'], row['expectation'], should,
                                                          row['enforced']))
    total = sum(int(r['mismatched']) for r in enforced)
    hard = [r['surface'] for r in enforced if int(r['mismatched']) > 0]
    if hard:
        problems.append('enforced frozen rows with a non-zero count: %s' % ','.join(hard))
    gate = [r for r in gate_rows if r['gate'] == 'frozen_surfaces']
    if not gate:
        problems.append('frozen_surfaces gate is missing, so the comparison table has no consumer')
    elif int(gate[0]['rc']) != total:
        problems.append('frozen_surfaces gate rc=%s but the enforced rows sum to %d'
                        % (gate[0]['rc'], total))
    return total


def identity_semantics(rows, directory, problems, git_ref=None, source_root=None):
    """every path it names has to be there, with the bytes and digest it quotes

    The disk bytes come from `source_root`, which defaults to this working tree. Auditing a *past*
    round means pointing it at a fresh extraction of the revision that round delivered: otherwise the
    only differences reported are this round's own edits, and the record's own false statements stay
    hidden. Git blobs always come from this repository, because an extraction has no .git.
    """
    root = source_root or ROOT
    if git_ref:
        listing = subprocess.check_output(['git', '-C', ROOT, 'ls-tree', '-r', git_ref]).decode('utf-8')
        index = {}
        for line in listing.strip().split('\n'):
            meta, path = line.split('\t', 1)
            index[path] = meta.split()[2]
    else:
        index = None
    for row in rows:
        # source_identity rows are repo-relative: the record lists what it read, not what it contains
        path = os.path.join(root, row['path'].replace('/', os.sep))
        if not os.path.isfile(path):
            problems.append('source_identity names %s which is not on disk' % row['path'])
            continue
        data = io.open(path, 'rb').read()
        if len(data) != int(row['bytes']):
            problems.append('%s is %d bytes, the record says %s' % (row['path'], len(data),
                                                                    row['bytes']))
        digest = hashlib.sha256(data).hexdigest()
        if digest != row['sha256']:
            problems.append('%s digest on disk is %s, the record says %s (a stale digest is still a '
                            'false statement about the delivered bytes)'
                            % (row['path'], digest[:12], row['sha256'][:12]))
        if index is not None:
            blob = index.get(row['path'])
            if blob is None:
                problems.append('%s is in the record but not in %s' % (row['path'], git_ref))
                continue
            committed = subprocess.check_output(['git', '-C', ROOT, 'cat-file', 'blob', blob])
            if hashlib.sha256(committed).hexdigest() != row['sha256']:
                problems.append('%s blob at %s differs from the digest the record quotes'
                                % (row['path'], git_ref))


def json_semantics(directory, gate_rows, problems):
    """the sub-results have to agree with the table rows that summarise them"""
    def load(name):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            problems.append('%s is absent' % name)
            return {}
        try:
            return json.loads(io.open(path, encoding='utf-8').read())
        except ValueError as error:
            problems.append('%s does not parse: %s' % (name, str(error)[:90]))
            return {}

    offline = load('offline_checks.json')
    row = [r for r in gate_rows if r['gate'] == 'offline_checks']
    failures = offline.get('failures', [])
    if row and row[0]['verdict_state'] == 'PASS' and failures:
        problems.append('offline_checks gate says PASS while offline_checks.json lists failures %s'
                        % ','.join(failures))
    if offline and len(offline.get('checks', [])) < 30:
        problems.append('offline_checks.json carries %d checks, fewer than the 30 the round declares'
                        % len(offline.get('checks', [])))
    guards = load('counterexamples.json')
    if guards:
        probes = guards.get('injections', [])
        missed = [i['injection'] for i in probes if i.get('verdict') != 'HIT']
        if missed:
            problems.append('counterexamples.json has probes that did not hit: %s' % ','.join(missed))
        empty = [i['injection'] for i in probes if not i.get('expected')]
        if empty:
            problems.append('%d counterexamples declare an empty expectation set, which can never '
                            'detect anything' % len(empty))
        # the synthetic family is arithmetic on hand-written numbers, not a fault injected into a
        # delivered file, so it has to stay labelled as what it is
        for row in probes:
            if str(row.get('injection', '')).startswith('S') and row.get('evidence_class') != \
                    'SYNTHETIC_NOT_MEASURED':
                problems.append('%s is a synthetic sign case without evidence_class '
                                'SYNTHETIC_NOT_MEASURED, so a hand-written number could be read as a '
                                'measurement' % row.get('injection'))
    selftest = load('selftest.json')
    if selftest:
        gate = [r for r in gate_rows if r['gate'] == 'record_tool_selftest']
        if selftest.get('verdict') == 'NOT_RUN' and gate and                 gate[0]['verdict_state'] == 'PASS':
            problems.append('the selftest refused for want of Git history (rc=2) while the gate row '
                            'reads PASS: a named refusal must stay NOT_ATTEMPTED, never a pass')
        if selftest.get('verdict') == 'PASS' and selftest.get('failures'):
            problems.append('selftest.json says PASS with failures listed: %s'
                            % selftest['failures'])
        if selftest.get('verdict') == 'PASS' and selftest.get('cases') != 9:
            problems.append('selftest.json claims PASS on %s cases, not the declared 9'
                            % selftest.get('cases'))
        if selftest.get('verdict') not in ('PASS', 'NOT_RUN'):
            problems.append('selftest.json verdict %r is neither PASS nor the named NOT_RUN'
                            % selftest.get('verdict'))
    for name in ('instrument_T.json', 'instrument_fixed.json'):
        payload = load(name)
        if not payload:
            continue
        cases = payload.get('cases', [])
        if len(cases) != 8:
            problems.append('%s reports %d cases, the reviewed defect list is eight' % (name,
                                                                                        len(cases)))
        for case in cases:
            if case.get('sha256_before') == case.get('sha256_after'):
                problems.append('%s/%s changed no bytes, so it proves nothing about the checker'
                                % (name, case.get('case')))
            if name == 'instrument_T.json' and not case.get('defect_reproduced'):
                problems.append('%s/%s no longer reproduces against the reviewed tip' % (name,
                                                                                          case.get('case')))
            if name == 'instrument_fixed.json' and not case.get('failures'):
                problems.append('%s/%s still escapes detection on the delivered bytes'
                                % (name, case.get('case')))
    if any(str(r['gate']).startswith('reviewer_remaining_') for r in gate_rows):
        remaining_gate = [r for r in gate_rows
                          if r['gate'] == 'reviewer_remaining_on_fixed_bytes']
        verdict_text = str(remaining_gate[0]['verdict']) if remaining_gate else ''
        for name, want_all in (('instrument_remaining_H.json', True),
                               ('instrument_remaining_fixed.json', False)):
            payload = load(name)
            if not payload:
                continue
            results = payload.get('results', [])
            if len(results) != 7:
                problems.append('%s reports %d results, the R1 review lists seven remaining gaps'
                                % (name, len(results)))
            if payload.get('baseline_failures'):
                problems.append('%s ran with a baseline that already fails: %s'
                                % (name, ','.join(payload['baseline_failures'])))
            open_cases = [r.get('case') for r in results if r.get('reproduced')]
            for case in results:
                if case.get('exception'):
                    # on the baseline copy a crash is the finding itself: the reviewed defect was that
                    # a non-finite value reached an unhandled int(). On the repaired copy nothing may
                    # crash, because there the answer has to be a named refusal.
                    if want_all:
                        if not case.get('reproduced'):
                            problems.append('%s/%s raised and did not even report the gap, so the '
                                            'diagnostic proves nothing'
                                            % (name, case.get('case')))
                    else:
                        problems.append('%s/%s raised instead of reporting: %s'
                                        % (name, case.get('case'), str(case['exception'])[:80]))
            if want_all and len(open_cases) != 7:
                problems.append('%s is the baseline copy but only %d of 7 gaps reproduce'
                                % (name, len(open_cases)))
            if payload.get('all_gaps_reproduced') is not want_all:
                problems.append('%s says all_gaps_reproduced=%s, this run expects %s'
                                % (name, payload.get('all_gaps_reproduced'), want_all))
            if not want_all:
                # a gap may stay reported only when the gate row itself says which one it is
                for case in open_cases:
                    if case not in verdict_text:
                        problems.append('%s still reports %s reproduced but the gate verdict does not '
                                        'name it, so an unexplained gap could hide here'
                                        % (name, case))
    return offline, guards, selftest


def summary_semantics(directory, gate_rows, problems):
    path = os.path.join(directory, 'verification_summary.json')
    if not os.path.isfile(path):
        problems.append('verification_summary.json is absent')
        return {}
    summary = json.loads(io.open(path, encoding='utf-8').read())
    failed = [r['gate'] for r in gate_rows if r['verdict_state'] == 'FAIL']
    if sorted(summary.get('gates_failed', [])) != sorted(failed):
        problems.append('verification_summary gates_failed=%s but commands.csv has FAIL rows %s'
                        % (summary.get('gates_failed'), failed or 'none'))
    if summary.get('verdict') in PASS_LIKE and failed:
        problems.append('the summary says %s while %d gate(s) failed' % (summary.get('verdict'),
                                                                        len(failed)))
    if summary.get('verdict') in PASS_LIKE and \
            [r for r in gate_rows if r['verdict_state'] in ('NOT_ATTEMPTED',)]:
        problems.append('the summary says %s while a mandatory gate was not attempted'
                        % summary.get('verdict'))
    if summary.get('gates') != len(gate_rows):
        problems.append('summary gates=%s but commands.csv holds %d rows'
                        % (summary.get('gates'), len(gate_rows)))
    for row in summary.get('csv_read_back', []):
        if not os.path.isfile(os.path.join(directory, row['file'])):
            problems.append('summary read-back lists %s which is not in the directory' % row['file'])
    if summary.get('native_launches') != 0 or summary.get('rtl_simulations') != 0 or \
            summary.get('oa_writes') != 0:
        problems.append('the record asserts non-zero execution cost')
    if summary.get('published_files_with_cr'):
        problems.append('published bytes contain CR: %s' % summary['published_files_with_cr'])
    return summary


def semantic_rules(gate_rows, frozen_rows, git_rows, identity_rows, directory, problems,
                   git_ref=None, summary_exists=True, source_root=None):
    """the rules themselves, shared by the published-bytes entry and the in-memory pre-publish gate

    Keeping one implementation matters: a gate that reads in-memory rows and a reader that reads the
    published table could otherwise disagree, and the disagreement would be the interesting finding.
    """
    names = gate_semantics(gate_rows, problems) if gate_rows else []
    if gate_rows:
        frozen_semantics(frozen_rows, gate_rows, problems)
        json_semantics(directory, gate_rows, problems)
        if summary_exists:
            summary_semantics(directory, gate_rows, problems)
    identity_semantics(identity_rows, directory, problems, git_ref, source_root)
    for row in git_rows:
        if BASE_SHA not in str(row['command']) and 'HEAD' not in str(row['command']):
            problems.append('git_checks %s does not name the revision its range starts at'
                            % row['gate'])
        if not re.match(r'^-?\d+$', str(row['rc'])):
            problems.append('git_checks %s rc=%r is not a number' % (row['gate'], row['rc']))
    return {'gates': len(names), 'frozen_rows': len(frozen_rows),
            'identity_rows': len(identity_rows), 'git_checks': len(git_rows)}


def check_rows(gate_rows, frozen_rows, git_rows, identity_rows, directory, git_ref=None,
               summary_exists=True):
    """in-memory form used by the publisher, before the summary line it judges exists"""
    problems = []
    facts = semantic_rules(gate_rows, frozen_rows, git_rows, identity_rows, directory, problems,
                           git_ref, summary_exists)
    return problems, facts


def check_record(directory, git_ref=None, summary_exists=True, source_root=None):
    """published-bytes form: the tables are read back from disk, then judged by the same rules"""
    problems = []
    gates = _rows(os.path.join(directory, 'commands.csv'), COMMANDS_HEADER, 'gate', problems)
    frozen = _rows(os.path.join(directory, 'frozen_comparison.csv'), FROZEN_HEADER, 'surface',
                   problems, optional=('first_mismatches',))
    git_rows = _rows(os.path.join(directory, 'git_checks.csv'), GIT_HEADER, 'gate', problems)
    identity = _rows(os.path.join(directory, 'source_identity.csv'), IDENTITY_HEADER, 'path',
                     problems)
    facts = semantic_rules(gates, frozen, git_rows, identity, directory, problems, git_ref,
                           summary_exists, source_root)
    return problems, facts


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', required=True)
    parser.add_argument('--git-ref', default='')
    parser.add_argument('--source-root', default='',
                       help='tree to compare the record against; use a fresh extraction of the '
                            'revision that record delivered, not a worktree holding a later round')
    arguments = parser.parse_args(argv)
    directory = arguments.record if os.path.isabs(arguments.record) else os.path.join(
        ROOT, arguments.record)
    if not os.path.isdir(directory):
        print('D7C_A_R2_RECORD_CHECK: FAIL (%s is not a directory)' % directory)
        return 1
    problems, facts = check_record(directory, arguments.git_ref or None,
                                   source_root=arguments.source_root or None)
    for line in problems[:24]:
        print('  PROBLEM ' + line)
    print('D7C_A_R2_RECORD_CHECK: %s (%s, %d semantic problems)'
          % ('PASS' if not problems else 'FAIL',
             ', '.join('%s=%s' % item for item in sorted(facts.items())), len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
