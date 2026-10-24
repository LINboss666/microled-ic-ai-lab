#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_r1_record_check.py -- the frozen record rules, with this round's ledger vocabulary.

`scripts/dd1_d7c_a_r2_record_check.py` is the record checker the accepted rounds share, and section 7
freezes it: the PREP record that is already published is judged by its constants, so editing them would
move an artefact another round depends on. Two of its constants are round-bound rather than rules:
`MANDATORY_GATES`, which names the DATA-7C-B-PREP gate set (including `reviewer_instrument_on_T`, whose
T is that round's reviewed tip), and `BASE_SHA`, which is that round's reviewed commit and is used only
to require that every git_checks row names the revision its range starts at.

So this entry does not rewrite the rules. It calls the same five rule functions, in the same order, on
the same tables, and replaces exactly one class of output: the mandatory-gate line. It removes the
frozen line, re-derives the same class of problem from this round's own gate list, and prints both
counts so a reviewer can see what was substituted and can re-run the frozen CLI and compare:

    python scripts/dd1_d7c_a_r2_record_check.py --record results/evidence/<R1 run> --source-root .
        -> reports the two DATA-7C-B-PREP instrument gate names absent and the PREP base SHA not in the
           git ranges; that is the round binding, disclosed here rather than worked around
    python scripts/dd1_d7c_b_prep_r1_record_check.py --record results/evidence/<R1 run> --source-root .
        -> the same rules with this round's vocabulary

Nothing is relaxed: every other problem the shared rules raise is reported unchanged, and the shared
module stays byte-identical (the R1 record proves that in its `frozen_surfaces` row).
"""

from __future__ import absolute_import, print_function

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_r2_record_check as RECORD       # noqa: E402  (the frozen rules, imported not edited)

INSTRUMENT_FILES = ('instrument_P.json', 'instrument_r1.json')
FAMILIES = ('F1_PAM_bit_order_and_high_level', 'F2_PWL_and_window_physics',
            'F3_measurement_entry_wiring', 'F4_native_deck_known_contract')

MANDATORY_GATES_R1 = (
    'reviewer_instrument_on_P_base', 'reviewer_instrument_on_r1_bytes',
    'reviewer_instrument_bytes_unchanged', 'deck_read_refuses_the_base_tree',
    'deck_read_on_delivered_bytes', 'deck_read_negatives_named', 'deck_regenerated_from_sources',
    'schedule_check', 'deck_check', 'contract_selfcheck', 'synthetic_measure_cases',
    'git_range_counts',
    # the vocabulary the shared checker already demands, kept because this round genuinely runs them
    'offline_checks', 'counterexamples', 'record_tool_selftest', 'fresh_extraction_replay',
    'handoff_structure', 'native_entry_refused', 'provenance', 'history_safety', 'frozen_surfaces',
    'record_line_endings')
BASE_SHA_R1 = 'dcef9b336f2222d6291d266858270f7448b6bb78'


def _rows(path, problems):
    if not os.path.isfile(path):
        problems.append('%s is missing' % os.path.basename(path))
        return []
    return RECORD._rows(path, RECORD.COMMANDS_HEADER, 'gate', problems)


def _json_rules(directory, gate_rows, problems):
    """the shared sub-result rules, with this round's instrument files standing in for the last one's

    `json_semantics` demands `instrument_T.json` and `instrument_fixed.json` with eight cases each:
    those are the DATA-7C-A review's eight-gap instrument and the two revisions it judged. This round's
    instrument is the DATA-7C-B-PREP four-family probe run against P and against the repaired bytes, so
    the two "is absent" lines are removed -- only those two, and the count is reported -- and the
    equivalent requirement is re-derived here: four families on each side, the base reproducing all four
    and the repaired bytes closing all four, both files quoting the same instrument digest, and every
    cost field on the repaired run still zero. Every other sub-result rule runs unchanged from the
    frozen module.
    """
    before = len(problems)
    loaded = RECORD.json_semantics(directory, gate_rows, problems)
    absent = ['%s is absent' % name for name in ('instrument_T.json', 'instrument_fixed.json')]
    removed = 0
    for line in list(problems):
        if line in absent:
            problems.remove(line)
            removed += 1
    digests = {}
    for name, expect_reproduced in ((INSTRUMENT_FILES[0], True), (INSTRUMENT_FILES[1], False)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            problems.append('%s is absent, and this round has no instrument evidence without it'
                            % name)
            continue
        try:
            payload = json.loads(io.open(path, encoding='utf-8').read())
        except ValueError as error:
            problems.append('%s does not parse: %s' % (name, str(error)[:90]))
            continue
        findings = payload.get('findings') or {}
        if sorted(findings) != sorted(FAMILIES):
            problems.append('%s reports families %s, the review lists four'
                            % (name, ','.join(sorted(findings)) or 'none'))
        open_families = sorted(key for key in findings if findings[key].get('reproduced'))
        want = sorted(FAMILIES) if expect_reproduced else []
        if open_families != want:
            problems.append('%s reproduces %s, this round expects %s'
                            % (name, ','.join(open_families) or 'none',
                               ','.join(want) or 'none'))
        for key in ('NEW_SPECTRE_LAUNCHES', 'NEW_RTL_SIMULATIONS', 'NEW_OA_WRITES'):
            if payload.get(key) != 0:
                problems.append('%s says %s=%r, the instrument is not allowed to spend any'
                                % (name, key, payload.get(key)))
        digest = payload.get('instrument_sha256')
        if not digest:
            problems.append('%s does not quote the instrument digest' % name)
        digests[name] = digest
    if len(set(digest for digest in digests.values() if digest)) > 1:
        problems.append('the two instrument runs quote different instrument bytes')
    return loaded, removed, before


def rules(directory, git_ref=None, source_root=None, summary_exists=True):
    """the shared rules over the published tables, with the mandatory-gate line re-derived in R1 words"""
    problems = []
    gates = _rows(os.path.join(directory, 'commands.csv'), problems)
    frozen = RECORD._rows(os.path.join(directory, 'frozen_comparison.csv'), RECORD.FROZEN_HEADER,
                          'surface', problems, optional=('first_mismatches',))
    git_rows = RECORD._rows(os.path.join(directory, 'git_checks.csv'), RECORD.GIT_HEADER, 'gate',
                            problems)
    identity = RECORD._rows(os.path.join(directory, 'source_identity.csv'), RECORD.IDENTITY_HEADER,
                            'path', problems)
    names = []
    if gates:
        names = RECORD.gate_semantics(gates, problems)
        removed = [line for line in problems
                   if line.startswith('mandatory gate(s) absent from commands.csv:')]
        for line in removed:
            problems.remove(line)
        missing = [gate for gate in MANDATORY_GATES_R1 if gate not in names]
        if missing:
            problems.append('mandatory gate(s) absent from commands.csv (the R1 list, which contains '
                            'every gate the shared list demands except its two round-bound '
                            'instrument names): %s' % ','.join(missing))
        RECORD.frozen_semantics(frozen, gates, problems)
        _loaded, replaced, _before = _json_rules(directory, gates, problems)
        if summary_exists:
            RECORD.summary_semantics(directory, gates, problems)
    RECORD.identity_semantics(identity, directory, problems, git_ref, source_root)
    for row in git_rows:
        if BASE_SHA_R1 not in str(row['command']) and 'HEAD' not in str(row['command']):
            problems.append('git_checks %s does not name the revision its range starts at'
                            % row['gate'])
        if not str(row['rc']).lstrip('-').isdigit():
            problems.append('git_checks %s rc=%r is not a number' % (row['gate'], row['rc']))
    return problems, {'gates': len(names), 'frozen_rows': len(frozen),
                      'identity_rows': len(identity), 'git_checks': len(git_rows),
                      'mandatory_gates_r1': len(MANDATORY_GATES_R1),
                      'frozen_mandatory_line_replaced': 1 if gates else 0,
                      'instrument_vocabulary_lines_replaced': replaced}


def check_rows(gate_rows, frozen_rows, git_rows, identity_rows, directory, git_ref=None,
               summary_exists=True):
    """the in-memory form, for the publisher to judge its own rows before they are written"""
    problems = []
    names = RECORD.gate_semantics(gate_rows, problems)
    removed = [line for line in problems if line.startswith('mandatory gate(s) absent from '
                                                             'commands.csv:')]
    for line in removed:
        problems.remove(line)
    missing = [gate for gate in MANDATORY_GATES_R1 if gate not in names]
    if missing:
        problems.append('mandatory gate(s) absent from commands.csv (the R1 list): %s'
                        % ','.join(missing))
    if gate_rows:
        RECORD.frozen_semantics(frozen_rows, gate_rows, problems)
        _loaded, replaced, _before = _json_rules(directory, gate_rows, problems)
        if summary_exists:
            RECORD.summary_semantics(directory, gate_rows, problems)
    RECORD.identity_semantics(identity_rows, directory, problems, git_ref, None)
    for row in git_rows:
        if BASE_SHA_R1 not in str(row['command']) and 'HEAD' not in str(row['command']):
            problems.append('git_checks %s does not name the revision its range starts at'
                            % row['gate'])
        if not str(row['rc']).lstrip('-').isdigit():
            problems.append('git_checks %s rc=%r is not a number' % (row['gate'], row['rc']))
    return problems, {'gates': len(names), 'frozen_rows': len(frozen_rows),
                      'identity_rows': len(identity_rows), 'git_checks': len(git_rows),
                      'instrument_vocabulary_lines_replaced': replaced}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', required=True)
    parser.add_argument('--git-ref', default='')
    parser.add_argument('--source-root', default='')
    arguments = parser.parse_args(argv)
    directory = arguments.record if os.path.isabs(arguments.record) else os.path.join(
        ROOT, arguments.record)
    if not os.path.isdir(directory):
        print('D7C_B_PREP_R1_RECORD_CHECK: FAIL (%s is not a directory)' % directory)
        return 1
    problems, facts = rules(directory, arguments.git_ref or None,
                            source_root=arguments.source_root or None)
    for line in problems[:24]:
        print('  PROBLEM ' + line)
    print('D7C_B_PREP_R1_RECORD_CHECK: %s (%s, %d semantic problems; the shared checker\'s '
          'mandatory-gate line was replaced by the R1 list, its rules were not changed)'
          % ('PASS' if not problems else 'FAIL',
             ', '.join('%s=%s' % item for item in sorted(facts.items())), len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
