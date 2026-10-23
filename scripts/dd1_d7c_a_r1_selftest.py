#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_r1_selftest.py -- negative tests for the DATA-7C-A-R1 record tools themselves.

The reviewed tip shipped comparisons that no gate consumed, so "the numbers look wrong" could not make
the run fail. These cases only exercise in-memory rows and temporary CSV files: no simulator, no
network, no VM, no repository mutation.

    python scripts/dd1_d7c_a_r1_selftest.py [--json <out.json>]

rc=0 means every declared case behaved as expected. A case that raises is reported as FAIL, not
silently counted. Each case carries its own expectation, and the JSON records the observed value, so
an aggregate rc is never the evidence.
"""

from __future__ import absolute_import, division, print_function

import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dd1_d7c_a_offline_check as CHECK      # noqa: E402
import dd1_d7c_a_verify as V                 # noqa: E402


def _base_rows():
    if not hasattr(V, '_SELFTEST_ROWS'):
        V._SELFTEST_ROWS = V.comparisons('')[0]
    import copy
    return copy.deepcopy(V._SELFTEST_ROWS)


def _rows(overrides):
    """real rows from the real index, with one named surface forced to a declared state"""
    rows = _base_rows()
    for row in rows:
        if row['surface'] in overrides:
            row['mismatched'] = overrides[row['surface']]
    return rows


def case_frozen_dut_edit():
    rows = _rows({'four_candidate_DUT_netlists': 1})
    gate = V.frozen_gate(rows, 0, 0)
    return gate['verdict_state'] == 'FAIL', 'state=%s verdict=%s' % (
        gate['verdict_state'], gate['verdict'][:120])


def case_frozen_removal():
    rows = _rows({'paths_removed_against_T': 3})
    gate = V.frozen_gate(rows, 0, 0)
    return gate['verdict_state'] == 'FAIL', 'state=%s' % gate['verdict_state']


def case_frozen_unallowed_addition():
    rows = _rows({'paths_added_not_allowed': 1})
    gate = V.frozen_gate(rows, 0, 0)
    return gate['verdict_state'] == 'FAIL', 'state=%s' % gate['verdict_state']


def case_frozen_diff_check_whitespace():
    rows = _rows({})
    gate = V.frozen_gate(rows, 1, 0)
    return gate['verdict_state'] == 'FAIL', 'state=%s' % gate['verdict_state']


def case_frozen_informational_does_not_whitewash_or_fail():
    """the two directions at once: counts in informational rows must not fail the gate, and a real
    violation in an enforced row must still fail even when the same table is full of counts"""
    rows = _rows({'whitelisted_paths_edited': 8, 'paths_added_allowed': 3})
    clean = V.frozen_gate(rows, 0, 0)
    rows = _rows({'whitelisted_paths_edited': 8, 'paths_added_allowed': 3,
                  'read_only_inputs_named_by_the_brief': 2})
    dirty = V.frozen_gate(rows, 0, 0)
    ok = clean['verdict_state'] == 'PASS' and dirty['verdict_state'] == 'FAIL'
    return ok, 'informational-only=%s plus enforced=%s' % (
        clean['verdict_state'], dirty['verdict_state'])


def case_frozen_whitelist_is_exact():
    """a directory sweep would call the whitelisted deck draft a frozen-surface violation"""
    rows, _ = V.comparisons('')
    by = dict((r['surface'], r) for r in rows)
    dut = by['four_candidate_DUT_netlists']
    draft_edit = by['whitelisted_paths_edited']
    ok = (dut['expectation'] == 'identical' and dut['enforced'] == 'yes' and
          not any(p in V.WHITELIST_MODIFIED for p in CHECK.CANDIDATE_FILES) and
          'spectre/dd1_d7c_a_tb_draft.scs' in V.WHITELIST_MODIFIED and
          draft_edit['enforced'] == 'no')
    return ok, 'dut paths=%s enforced=%s draft on whitelist=%s enforced_edit_row=%s' % (
        dut['paths_compared'], dut['enforced'],
        'spectre/dd1_d7c_a_tb_draft.scs' in V.WHITELIST_MODIFIED, draft_edit['enforced'])


def case_read_table_refuses_bad_shapes():
    """the published-byte reader must refuse, in a named way, on each of the shapes the review named"""
    header = ['a', 'b', 'c']
    bodies = {
        'empty_file': '',
        'header_only': 'a,b,c\n',
        'ragged_row': 'a,b,c\n1,2\n',
        'extra_column': 'a,b,c\n1,2,3,4\n',
        'wrong_header': 'a,b,d\n1,2,3\n',
        'duplicate_key': 'a,b,c\n1,2,3\n1,4,5\n',
        'blank_required_cell': 'a,b,c\n,2,3\n',
        'comma_inside_field_round_trips': 'a,b,c\n1,"two, with a comma",3\n',
    }
    outcomes = {}
    directory = tempfile.mkdtemp(prefix='dd1-d7c-a-selftest-')
    for name, body in bodies.items():
        path = os.path.join(directory, '%s.csv' % name)
        with io.open(path, 'wb') as handle:
            handle.write(body.encode('utf-8'))
        try:
            parsed = CHECK.read_table(path, header, 'a', optional=())
            outcomes[name] = ('accepted', len(parsed))
        except ValueError as error:
            outcomes[name] = ('refused', str(error)[:90])
    refuse = ['empty_file', 'header_only', 'ragged_row', 'extra_column', 'wrong_header',
              'duplicate_key', 'blank_required_cell']
    bad = [k for k in refuse if outcomes[k][0] != 'refused']
    bad += [k for k in ('comma_inside_field_round_trips',) if outcomes[k][:2] != ('accepted', 1)]
    return not bad, {k: outcomes[k] for k in sorted(outcomes)} if bad else 'all as expected'


def case_writer_round_trips_the_hard_content():
    """a verdict containing a comma, a quote and a semicolon list must come back as one field"""
    directory = tempfile.mkdtemp(prefix='dd1-d7c-a-selftest-')
    path = os.path.join(directory, 'hard.csv')
    text = 'verdict with, comma and "quote"; then a colon'
    CHECK.rows_write(path, ['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'],
                     [{'gate': 'g1', 'command': 'python x.py --a 1 --b 2', 'rc': 0,
                       'expected_rc': '0', 'verdict_state': 'PASS', 'verdict': text}])
    parsed = CHECK.read_table(path, ['gate', 'command', 'rc', 'expected_rc', 'verdict_state',
                                     'verdict'], 'gate')
    ok = len(parsed) == 1 and parsed[0]['verdict'] == text
    with io.open(path, encoding='utf-8', newline='') as handle:
        raw = handle.read()
    ok = ok and '\r' not in raw and raw.endswith('\n')
    return ok, 'fields back identical=%s cr_absent=%s' % (parsed[0]['verdict'] == text,
                                                          '\r' not in raw)


def case_T_published_tables_are_refused_by_the_strict_reader():
    """the reader has to refuse the real bytes the review named, and accept the one that was well-formed"""
    directory = tempfile.mkdtemp(prefix='dd1-d7c-a-selftest-')
    tables = {
        'commands.csv': (['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], True),
        'git_checks.csv': (['gate', 'command', 'rc', 'lines', 'scope'], True),
        'source_identity.csv': (['role', 'path', 'bytes', 'sha256'], True),
        'frozen_comparison.csv': (['surface', 'paths_compared', 'mismatched', 'first_mismatches'],
                                  False),
    }
    observed = {}
    bad = []
    for name, (header, must_refuse) in sorted(tables.items()):
        raw = V.git('show', '%s:%s/%s' % (V.TIP_UNDER_REVIEW, V.FIRST_ROUND_EVIDENCE, name))
        path = os.path.join(directory, 'T_' + name)
        with io.open(path, 'wb') as handle:
            handle.write(raw)
        try:
            parsed = CHECK.read_table(path, header, header[0], optional=('first_mismatches',))
            outcome = ('accepted', '%d rows' % len(parsed))
        except ValueError as error:
            outcome = ('refused', str(error)[:120])
        observed[name] = outcome
        if outcome[0] != ('refused' if must_refuse else 'accepted'):
            bad.append(name)
    detail = dict((k, observed[k][1]) for k in sorted(observed))
    return not bad, detail if bad else \
        'the three ragged T tables are refused by name and the well-formed one is accepted'


CASES = [
    ('frozen_gate_refuses_candidate_DUT_edit', case_frozen_dut_edit,
     'a modified DUT netline must fail the gate'),
    ('frozen_gate_refuses_T_path_removal', case_frozen_removal,
     'a removed T path must fail the gate'),
    ('frozen_gate_refuses_unallowed_addition', case_frozen_unallowed_addition,
     'a new path outside §9 must fail the gate'),
    ('frozen_gate_refuses_whitespace_errors', case_frozen_diff_check_whitespace,
     'git diff --check rc != 0 must fail the gate'),
    ('frozen_gate_counts_only_enforced_rows', case_frozen_informational_does_not_whitewash_or_fail,
     'informational counts neither fail the gate nor hide a real violation'),
    ('frozen_surfaces_are_exact_paths', case_frozen_whitelist_is_exact,
     'the DUT/golden surfaces are exact paths and the deck draft is on the whitelist'),
    ('read_table_refuses_seven_shapes', case_read_table_refuses_bad_shapes,
     'empty, header-only, ragged, extra-column, wrong-header, duplicate-key and blank-required are '
     'refused by name'),
    ('rows_write_round_trips_commas_and_quotes', case_writer_round_trips_the_hard_content,
     'the standard-library writer and reader agree on awkward content, LF only'),
    ('T_published_tables_refused_by_the_strict_reader', case_T_published_tables_are_refused_by_the_strict_reader,
     'commands/git_checks/source_identity as delivered at T are refused line by line, while the '
     'well-formed frozen_comparison is accepted'),
]


def repository_available():
    """seven of these cases ask Git questions, so outside a work tree they must refuse, not crash"""
    try:
        V.git('rev-parse', '%s^{commit}' % V.TIP_UNDER_REVIEW)
        V.git('rev-parse', 'HEAD')
        return True
    except Exception:                           # noqa: BLE001 - absence of a repo is the answer here
        return False


def main(argv):
    out = ''
    if '--json' in argv:
        out = os.path.abspath(argv[argv.index('--json') + 1])
    if not repository_available():
        message = ('NOT_RUN: this suite asks Git questions (frozen surfaces, the reviewed tip and '
                   'HEAD are compared by blob), so it only runs inside the repository work tree. '
                   'Replaying it from a bare git-archive extraction is not a failure of the round, '
                   'and it is not a pass either.')
        payload = {'selftest': 'DATA-7C-A-R1 record-tool negative tests', 'cases': 0,
                   'failures': ['GIT_HISTORY_UNAVAILABLE'], 'verdict': 'NOT_RUN',
                   'results': [], 'note': message, 'native_launches': 0,
                   'repository_mutated': 'NO'}
        if out:
            with io.open(out, 'wb') as handle:
                handle.write((json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                             .encode('utf-8'))
        print('D7C_A_R1_SELFTEST: %s' % message)
        return 2
    report = []
    for name, fn, expectation in CASES:
        try:
            ok, observed = fn()
            state = 'PASS' if ok else 'FAIL'
        except Exception as error:                       # noqa: BLE001 - a crash is a named FAIL
            ok, state = False, 'FAIL'
            observed = 'raised %s: %s' % (type(error).__name__, str(error)[:140])
        report.append({'case': name, 'expectation': expectation, 'observed': str(observed)[:400],
                       'state': state})
        print('CASE %-46s %s  %s' % (name, state, str(observed)[:150]))
    failed = [r['case'] for r in report if r['state'] == 'FAIL']
    payload = {'selftest': 'DATA-7C-A-R1 record-tool negative tests', 'cases': len(report),
               'failures': failed, 'verdict': 'FAIL' if failed else 'PASS',
               'results': report, 'native_launches': 0, 'repository_mutated': 'NO',
               'note': 'in-memory rows and temporary CSV files only; nothing here starts a '
                       'simulator, touches a VM, or edits the delivered tree'}
    if out:
        with io.open(out, 'wb') as handle:
            handle.write((json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                         .encode('utf-8'))
    print('D7C_A_R1_SELFTEST: %s (%d cases, failures: %s)'
          % (payload['verdict'], len(report), ', '.join(failed) or 'none'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
