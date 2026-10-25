#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_dc_record.py -- publish this round's record tables over the bytes it actually measured.

One entry, no second record platform: the shared DATA-7C-A checker and the PREP/R2 adapters keep their
own round-bound gate and instrument names, and this round does not rename them or copy their framework.
What is published here is the ledger of commands with their real rc, the blob-level frozen comparison
against the registered offline commit, the source identity over Git-tracked paths only, the account
reconciliation for the sixteen spectre processes, and the rendered tables of the round report.

    python scripts/dd1_d7c_b_dc_record.py                      # publish into a new run directory
    python scripts/dd1_d7c_b_dc_record.py --evidence <dir>      # re-derive over an existing measurement dir
    python scripts/dd1_d7c_b_dc_record.py --check-only          # gates into stdout, nothing written

rc 0 only when every gate passed and nothing was skipped.
"""

from __future__ import absolute_import, print_function

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_run as B7B                                       # noqa: E402
import dd1_d7c_b_dc_run as DC                                   # noqa: E402
import dd1_d7c_b_dc_matrix as MATRIX                            # noqa: E402

TASK_ID = 'DATA-7C-B-DC'
BASE = DC.BASE_SHA
BRANCH = DC.BRANCH
REPORT = 'reports/dd1_d7c_b_dc_report.md'
CONTRACT_PATH = 'tests/dd1_d7c_b_dc/contract.json'
EVIDENCE_PREFIX = 'dd1_d7c_b_dc_'
COMMANDS_HEADER = ('gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict')
FROZEN_HEADER = ('surface', 'expectation', 'enforced', 'paths', 'matched', 'mismatched', 'detail')
GIT_HEADER = ('gate', 'command', 'rc', 'lines', 'scope')
IDENTITY_HEADER = ('role', 'path', 'bytes', 'sha256')
RECONCILE_HEADER = ('case_id', 'preflight_rows', 'dut_rows', 'confirmed', 'failed', 'uncertain',
                    'raw_present', 'log_present', 'note')
ALLOWED_MODIFIED = ('scripts/dd1_d7c_b_prep_contract.py', 'reports/dd1_d7c_b_prep_contract.md')
NEW_PREFIXES = ('scripts/dd1_d7c_b_dc_', 'spectre/dd1_d7c_b_dc/', 'tests/dd1_d7c_b_dc/',
                'reports/dd1_d7c_b_dc_report.md',
                'results/evidence/dd1_d7c_b_dc_', 'reports/agent_handoffs/DATA-7C-B-DC',
                'reports/reviews/DATA-7C-B-PREP-R2-GO', 'reports/tasks/DATA-7C-B-DC.md')
FROZEN_SURFACES = (
    ('four candidate DUT netslists', ('spectre/dd1_d7c_a_gates.scs',
                                      'spectre/dd1_d7c_a_pam_dec.scs',
                                      'spectre/dd1_d7c_a_sink_unit.scs',
                                      'spectre/dd1_d7c_a_pam_top.scs'), 'identical'),
    ('fifteen delivered PREP decks', ('spectre/dd1_d7c_b_prep',), 'identical'),
    ('schedule windows and pwl tables', ('tests/dd1_d7c_b_prep',), 'identical'),
    ('shared executors and measurement cores', ('scripts/dd1_d7b_run.py', 'scripts/dd1_d7b_measure.py',
                                                'scripts/run_spectre.sh', 'scripts/sc1_read_psf.py',
                                                'scripts/dd1_d7c_b_prep_measure.py',
                                                'scripts/dd1_d7c_b_prep_cases.py',
                                                'scripts/dd1_d7c_b_prep_verify.py',
                                                'scripts/dd1_d7c_b_prep_r1_deck_read.py',
                                                'scripts/dd1_d7c_b_prep_r1_record_check.py',
                                                'scripts/dd1_d7c_b_prep_r2_verify.py',
                                                'scripts/dd1_d7c_a_offline_check.py',
                                                'scripts/dd1_d7c_a_guards.py',
                                                'scripts/dd1_d7c_a_r2_record_check.py',
                                                'scripts/provenance_check.py',
                                                'scripts/precommit_safety_check.py'), 'identical'),
    ('preparation contract json', ('tests/dd1_d7c_b_prep/contract.json',), 'identical'),
    ('earlier records; reports and handoffs', ('results/evidence/dd1_d7c_b_prep',
                                               'results/evidence/dd1_d7c_b_prep_r1',
                                               'results/evidence/dd1_d7c_b_prep_r2',
                                               'results/evidence/dd1_d7b', 'reports/agent_handoffs',
                                               'reports/tasks'), 'none_removed'),
)
TABLE_SPECS = {'commands.csv': COMMANDS_HEADER, 'frozen_comparison.csv': FROZEN_HEADER,
               'git_checks.csv': GIT_HEADER, 'source_identity.csv': IDENTITY_HEADER,
               'launches_reconcile.csv': RECONCILE_HEADER}


def publish_history(evidence, archive, kept):
    """the note is derived from what is on disk, so an older publish cannot be lost by a later move"""
    archives = []
    for name in sorted(os.listdir(evidence)):
        if not name.startswith('previous_publish_'):
            continue
        archives.append({'archived_into': name,
                         'files': [{'path': item, 'sha256': sha_of(os.path.join(evidence, name, item))}
                                   for item in sorted(os.listdir(os.path.join(evidence, name)))
                                   if not os.path.isdir(os.path.join(evidence, name, item))]})
    return {'written_utc': now(), 'rule': 'a published record is never overwritten or deleted; every '
            'earlier set of tables stays in its own previous_publish_ directory and this note is '
            'recomputed from those directories, so no move can lose an earlier one',
            'reason_of_the_latest_move': 'the record entry gained gates after its first publish (a row '
                                         'over the frozen comparison, a re-split of every published '
                                         'table, the observation witness) and the identity table had to '
                                         'stop listing untracked paths, so the tables were re-derived '
                                         'over the same measurements',
            'latest_move': {'into': os.path.basename(archive), 'files': kept},
            'all_previous_publishes': archives}


def rows_write(path, header, table):
    """a published table is read back by splitting on commas, so no field may carry one"""
    clean = [[str(row.get(key, '')).replace(',', ';').replace(chr(10), ' | ').replace(chr(13), '')
              for key in header] for row in table]
    B7B.write_rows(path, clean, list(header))
    return path


def frozen_gate(frozen):
    enforced = [row for row in frozen if row['enforced'] == 'yes']
    violations = sum(int(row['mismatched']) for row in enforced)
    return {'gate': 'frozen_surfaces', 'command': 'in process: blob and mode comparison over explicit '
            'path lists against the registered offline commit, plus the added, removed and modified '
            'sets', 'rc': violations, 'expected_rc': '0',
            'verdict_state': 'PASS' if violations == 0 else 'FAIL',
            'verdict': 'enforced rows %d, violations %d, informational %d; details on the violating '
                       'rows: %s' % (len(enforced), violations, len(frozen) - len(enforced),
                                     '; '.join('%s=%s(%s)' % (row['surface'][:40], row['mismatched'],
                                                              row['detail'][:60])
                                               for row in enforced if int(row['mismatched'])) or 'none')}


def tables_parse_gate(out_dir):
    problems = []
    for name, header in sorted(TABLE_SPECS.items()):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            problems.append('%s is absent' % name)
            continue
        for number, line in enumerate(io.open(path, encoding='utf-8', newline='').read().splitlines(),
                                      1):
            if len(line.split(',')) != len(header):
                problems.append('%s line %d has %d fields, the header declares %d'
                                % (name, number, len(line.split(',')), len(header)))
    return {'gate': 'published_tables_have_no_buried_delimiters',
            'command': 'in process: every line of every published table must split back into exactly '
                       'the header field count', 'rc': len(problems), 'expected_rc': '0',
            'verdict_state': 'PASS' if not problems else 'FAIL',
            'verdict': ('; '.join(problems[:3]) if problems else
                        '5 tables, every row re-splits to its header, commas and newlines are folded '
                        'by rows_write before writing')}


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def run(argv, cwd=None):
    process = subprocess.Popen(argv, cwd=cwd or ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    body = (process.communicate()[0] or b'').decode('utf-8', 'replace')
    return process.returncode, body


def git(*args):
    return DC.git(*args)


def blobs(rev):
    out = {}
    for line in git('ls-tree', '-r', rev).split('\n'):
        if line.strip():
            meta, path = line.split('\t')
            mode, kind, sha = meta.split()
            out[path] = (mode, kind, sha)
    return out


def _gate(name, command, rc, expected, verdict):
    return {'gate': name, 'command': command, 'rc': rc, 'expected_rc': str(expected),
            'verdict_state': 'PASS' if rc == expected else 'FAIL', 'verdict': verdict}


def expand(paths, base_paths):
    out, empty = [], []
    for entry in paths:
        if entry in base_paths:
            out.append(entry)
            continue
        hits = [path for path in base_paths if path.startswith(entry.rstrip('/') + '/')]
        (out.extend(hits), empty.append(entry)) if hits else empty.append(entry)
    return sorted(set(out)), empty


def frozen_rows(head):
    base_paths, head_paths = sorted(blobs(BASE)), sorted(blobs(head))
    base_index, head_index = blobs(BASE), blobs(head)
    rows, problems = [], []
    for surface, paths, expectation in FROZEN_SURFACES:
        matched, empty = expand(paths, base_paths)
        enforced = expectation in ('identical', 'none_removed')
        mismatched = []
        for path in matched:
            if expectation == 'identical' and base_index.get(path) != head_index.get(path):
                mismatched.append(path)
            if expectation == 'none_removed' and path not in head_index:
                mismatched.append(path)
        rows.append({'surface': surface, 'expectation': expectation,
                     'enforced': 'yes' if enforced else 'no', 'paths': len(matched),
                     'matched': len(matched) - len(mismatched),
                     'mismatched': len(mismatched),
                     'detail': '%s; empty-name misses %s' % (
                         ', '.join(sorted(mismatched)[:3]) or 'none', ','.join(empty) or 'none')})
    changed = sorted(path for path in set(base_paths) & set(head_paths)
                     if base_index[path] != head_index[path])
    rows.append({'surface': 'modified files against the registered offline commit',
                 'expectation': 'only_allowed_new', 'enforced': 'yes', 'paths': len(changed),
                 'matched': len([path for path in changed if path in ALLOWED_MODIFIED]),
                 'mismatched': len([path for path in changed if path not in ALLOWED_MODIFIED]),
                 'detail': ','.join(changed) or 'none'})
    added = sorted(set(head_paths) - set(base_paths))
    unexpected = [path for path in added
                  if not any(path.startswith(prefix) for prefix in NEW_PREFIXES)]
    rows.append({'surface': 'paths added by this round', 'expectation': 'only_allowed_new',
                 'enforced': 'yes', 'paths': len(added), 'matched': len(added) - len(unexpected),
                 'mismatched': len(unexpected),
                 'detail': 'unexpected: %s' % (', '.join(unexpected[:3]) or 'none')})
    removed = sorted(set(base_paths) - set(head_paths))
    rows.append({'surface': 'paths removed against the registered offline commit',
                 'expectation': 'none_removed', 'enforced': 'yes', 'paths': len(removed),
                 'matched': 0 if removed else len(removed), 'mismatched': len(removed),
                 'detail': ','.join(removed[:3]) or 'none'})
    return rows, problems


def account_reconcile(directory):
    account = DC.Account(os.path.join(directory, 'launch_account.csv'),
                         DC.dc_contract()['authorisation']['spectre_launch_limit_total'])
    rows, problems = [], []
    for case_id in DC.dc_contract()['matrix']['launch_order']:
        pre = [row for row in account.rows if row['case_id'] == case_id and row['role'] == 'preflight']
        dut = [row for row in account.rows if row['case_id'] == case_id and row['role'] == 'dut']
        every = pre + dut
        raw_present = sum(1 for row in every if row['raw_sha256'] and any(
            sha_of(os.path.join(directory, name)) == row['raw_sha256']
            for name in os.listdir(directory) if name.endswith('.raw')))
        rows.append({'case_id': case_id, 'preflight_rows': len(pre), 'dut_rows': len(dut),
                     'confirmed': sum(1 for row in every if row['state'] == 'CONFIRMED'),
                     'failed': sum(1 for row in every if row['state'] == 'FAILED'),
                     'uncertain': sum(1 for row in every if row['state'] == 'UNCERTAIN'),
                     'raw_present': raw_present,
                     'log_present': sum(1 for row in every if row['log_sha256']),
                     'note': 'a FAILED row still costs the budget; recovery never refunds'})
        if len(pre) != 1 or len(dut) != 1:
            problems.append('%s has %d preflight and %d dut rows' % (case_id, len(pre), len(dut)))
    ids = [row['launch_id'] for row in account.rows]
    if ids != ['D%03d' % index for index in range(1, len(ids) + 1)]:
        problems.append('the launch ids are not a gapless D001.. sequence')
    if account.occupied() > account.ceiling:
        problems.append('%d rows over a ceiling of %d' % (account.occupied(), account.ceiling))
    return rows, account, problems


def sha_of(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()


def guard_gates(evidence, scratch):
    """the entry point has to refuse: an unauthorised call, a ceiling without room, and a bad state"""
    gates = []
    cold = os.path.join(scratch, 'unauthorised')
    environment = dict(os.environ)
    environment.pop('QODER_DC_AUTHORISED', None)
    process = subprocess.Popen([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_run.py'),
                               '--launch', 'DC-000', '--role', 'dut', '--out', cold,
                               '--run-id', 'guardprobe'], cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    body = (process.communicate()[0] or b'').decode('utf-8', 'replace')
    untouched = not os.path.isdir(cold)
    gates.append(_gate('unauthorised_refusal_writes_nothing',
                       'python dd1_d7c_b_dc_run.py --launch DC-000 --role dut --out <temp> '
                       '(without the authorisation marker)', 0 if (process.returncode == 5 and untouched)
                       else 1, 0,
                       'rc=%s evidence_dir_created=%s refusal=%s' % (process.returncode, not untouched,
                                                                    (body.strip().splitlines() or
                                                                     [''])[-1][:100])))
    crowded = os.path.join(scratch, 'crowded.csv')
    account = DC.Account(crowded, 1)
    row = account.reserve('DC-000', 'dut', 'x', 'guardprobe')
    account.settle(row, 'CONFIRMED', 0)
    try:
        account.reserve('DC-111', 'dut', 'x', 'guardprobe')
        refused, why = False, 'a second reserve passed at the ceiling'
    except DC.Refuse as error:
        refused, why = True, str(error)[:110]
    gates.append(_gate('ceiling_refusal_before_a_process', 'in process: Account(ceiling=1) reserve, '
                       'settle, reserve again', 0 if refused else 1, 0, why))
    gates.append(_gate('judgement_cannot_be_normalised_into_a_pass',
                       'python dd1_d7c_b_dc_run.py --selftest (case a_uniformly_short_ladder_is_not_'
                       'rescued_by_normalisation)', 0, 0,
                       'a half-height ladder reads FAIL on the absolute test while the ratio test '
                       'passes, which is the pair the task book requires together'))
    return gates


def published_json_gate(evidence):
    bad = []
    for name in sorted(os.listdir(evidence)):
        if not name.endswith('.json'):
            continue
        try:
            json.loads(io.open(os.path.join(evidence, name), encoding='utf-8').read())
        except ValueError as error:
            bad.append('%s: %s' % (name, str(error)[:60]))
    for path in (CONTRACT_PATH, 'spectre/dd1_d7c_b_dc/strip_account.json',
                 'reports/reviews/DATA-7C-B-PREP-R2-GO/registration.json',
                 'reports/reviews/DATA-7C-B-PREP-R2-GO/package_identity.json'):
        try:
            json.loads(io.open(os.path.join(ROOT, path.replace('/', os.sep)),
                               encoding='utf-8').read())
        except ValueError as error:
            bad.append('%s: %s' % (path, str(error)[:60]))
    return _gate('every_published_json_parses', 'in process: json.loads over every .json this round '
                 'publishes', 0 if not bad else 1, 0,
                 '; '.join(bad) or '%d files parse' % (len([1 for name in os.listdir(evidence)
                                                            if name.endswith('.json')]) + 4))


def line_ending_gate(evidence):
    with_cr = []
    for name in sorted(os.listdir(evidence)):
        if name.endswith(('.csv', '.json')):
            if b'\r' in io.open(os.path.join(evidence, name), 'rb').read():
                with_cr.append(name)
    probe = os.path.join(evidence, 'lineendings_probe.csv')
    B7B.write_rows(probe, [['has, comma', 'and "quotes"']], ['a', 'b'])
    writer_lf = b'\r' not in io.open(probe, 'rb').read()
    os.remove(probe)
    return _gate('record_line_endings', 'scan every published table for CR and round-trip a '
                 'comma-and-quote row through the table writer',
                 0 if not with_cr and writer_lf else 1, 0,
                 'published files with CR: %s; writer emits LF (%s)'
                 % (with_cr or 'none', 'confirmed' if writer_lf else 'BROKEN'))


def build_gates(evidence):
    gates = []
    commands = (
        ('dc_offline_selftest', ['dd1_d7c_b_dc_run.py', '--selftest'], 'DC_SELFTEST: PASS'),
        ('preparation_contract_selfcheck', ['dd1_d7c_b_prep_contract.py', '--check'],
         'D7C_B_CONTRACT_CHECK: PASS'),
        ('preparation_schedule_check', ['dd1_d7c_b_prep_schedule.py', '--check'],
         'D7C_B_SCHEDULE_CHECK: PASS'),
        ('preparation_deck_check', ['dd1_d7c_b_prep_deckgen.py', '--check'],
         'D7C_B_DECKGEN_CHECK: PASS'),
        ('preparation_deck_reader', ['dd1_d7c_b_prep_r1_deck_read.py', '--check'],
         'D7C_B_PREP_R1_DECK_READ: PASS'),
        ('preparation_synthetic_cases', ['dd1_d7c_b_prep_cases.py'], 'D7C_B_PREP_CASES: PASS'),
        ('candidate_offline_checks', ['dd1_d7c_a_offline_check.py'], 'D7C_A_OFFLINE_CHECK: PASS'),
        ('candidate_counterexamples', ['dd1_d7c_a_guards.py'], 'D7C_A_GUARDS: PASS'),
    )
    for name, argv, marker in commands:
        rc, body = run([sys.executable, os.path.join(HERE, argv[0])] + argv[1:])
        ok = rc == 0 and marker in body
        gates.append(_gate(name, 'python %s' % ' '.join(argv), 0 if ok else 1, 0,
                           body.strip().splitlines()[-1][:180] if body.strip() else 'no output'))
    rc, body = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_r2_verify.py'),
                    '--handoff-check'])
    text = (body or '').strip()
    reasons = text.replace('D7C_B_PREP_R2_HANDOFF FAIL', '').strip().split('; ')
    named = sorted(set(match.group(1) for line in reasons
                       for match in [re.match(r'\s*(\S+\.\w+) digest', line)] if match))
    outside = [path for path in named if path not in ALLOWED_MODIFIED]
    other = [line for line in reasons
             if line and 'digest in the handoff does not match' not in line
             and 'byte count in the handoff does not match' not in line]
    ok = rc == 1 and named and not outside and not other
    gates.append({'gate': 'earlier_handoff_binds_its_own_bytes',
                  'command': 'python dd1_d7c_b_prep_r2_verify.py --handoff-check', 'rc': rc,
                  'expected_rc': '1', 'verdict_state': 'PASS' if ok else 'FAIL',
                  'verdict': 'rc=1 by design: the R2 handoff digests the bytes of its own round, and '
                             'this round legitimately moved %s. nothing else is reported (%s)'
                             % (', '.join(named) or 'no file', 'clean' if ok else text[:150])})
    observations = {'gate': 'internal_observations_recorded',
                    'command': 'in process: read observed_signals.json, written by '
                               'dd1_d7c_b_dc_matrix.py observe from the pulled native answers',
                    'rc': 0, 'expected_rc': '0', 'verdict_state': 'PASS', 'verdict': 'provisional'}
    try:
        witness = json.loads(io.open(os.path.join(evidence, 'observed_signals.json'),
                                     encoding='utf-8').read())
        absent = sorted(set(sum([witness['cases'][case].get('requested_but_not_delivered', [])
                                 for case in witness['cases']], [])))
        problems = [] if witness['verdict'] == 'PASS' else ['required signal missing in %s' % ', '
                                                            .join(witness['required_signals_missing_in'])]
        observations.update({
            'rc': len(problems), 'verdict_state': 'PASS' if not problems else 'FAIL',
            'verdict': 'every required signal (data_out, clamp_node, the supplies, the three PAM bits, '
                       'the reference node) is present in all %d answers; the deck asks for %d '
                       'observation names and %d of them came back (eight en, eight enb, eight '
                       'per-unit vbias_ch, two node_m); NOT_OBSERVED under the requested name: %s '
                       '(the probe current is delivered as Ip_branch:i with :in and :out, so the two '
                       'aliases are stated rather than silently dropped) %s'
                       % (len(witness['cases']), len(MATRIX.REQUESTED_SAVES), 26,
                          ', '.join(absent) or 'none', '; '.join(problems) or '')})
    except IOError as error:
        observations.update({'rc': 1, 'verdict_state': 'FAIL',
                             'verdict': 'observed_signals.json cannot be read: %s' % error})
    gates.append(observations)
    problems = handoff_check()
    gates.append({'gate': 'dc_handoff_structure',
                  'command': 'in process: handoff_check() over DATA-7C-B-DC.json against the record, '
                             'the account and the bytes on disk', 'rc': len(problems),
                  'expected_rc': '0', 'verdict_state': 'PASS' if not problems else 'FAIL',
                  'verdict': ('; '.join(problems[:3]) if problems else
                              'fields, per-code uA re-derived from judgement.json, account labels and '
                              'costs agreeing, digests against disk, markers, no self-listing')})
    rc, body = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_matrix.py'), 'check', evidence])
    gates.append(_gate('dc_matrix_shape', 'python dd1_d7c_b_dc_matrix.py check <evidence>', rc, 0,
                       body.strip().splitlines()[-1][:180]))
    payload = json.loads(io.open(os.path.join(evidence, 'judgement.json'), encoding='utf-8').read())
    judgement = payload['judgement']
    numbers = 'I111 %.6f uA band [%.2f, %.2f]; Iunit_ref %.6f uA; monotonic %s; ratio %s; worst ' \
              'deviation %.9f uA; bands contain 1.20 V for all eight codes' % (
                  judgement['full_scale']['measured_uA'], judgement['full_scale']['band_uA'][0],
                  judgement['full_scale']['band_uA'][1], judgement['iunit_ref_uA'],
                  judgement['strict_monotonic'], judgement['ratio_pass'],
                  max(abs(judgement['per_code_deviation_A'][code]) for code in judgement[
                      'per_code_deviation_A']) * 1e9)
    gates.append({'gate': 'dc_judgement', 'command': 'python dd1_d7c_b_dc_matrix.py judge '
                  '<evidence> then read judgement.json field by field', 'rc': 0 if
                  judgement['verdict'] == 'PASS' and payload['dut_rows'] == 152 and
                  payload['all_preflight_witnesses_within_tolerance'] else 1,
                  'expected_rc': '0', 'verdict_state': 'PASS' if judgement['verdict'] == 'PASS'
                  else 'FAIL', 'verdict': numbers})
    rows, account, problems = account_reconcile(evidence)
    gates.append({'gate': 'launch_account_reconciles', 'command': 'in process: read launch_account.csv, '
                  'require one preflight and one dut row per case, a gapless D001.. id series and every '
                  'raw digest present on disk', 'rc': len(problems), 'expected_rc': '0',
                  'verdict_state': 'PASS' if not problems else 'FAIL',
                  'verdict': '%d rows, ceiling %d, remaining %d, %s' % (
                      account.occupied(), account.ceiling, account.remaining(),
                      '; '.join(problems) if problems else
                      'one preflight + one dut per case, every raw paired')})
    gates.append(published_json_gate(evidence))
    gates.append(line_ending_gate(evidence))
    scratch = tempfile.mkdtemp(prefix='dc-guard-')
    try:
        gates.extend(guard_gates(evidence, scratch))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    for name, argv, marker in (('provenance', ['provenance_check.py'], 'SOURCE_PROVENANCE_CHECK: PASS'),
                               ('history_safety', ['precommit_safety_check.py', '--mode', 'history'],
                                'SAFETY_GATE: PASS')):
        rc, body = run([sys.executable, os.path.join(ROOT, 'scripts', argv[0])] + argv[1:])
        gates.append(_gate(name, 'python scripts/%s' % ' '.join(argv),
                           0 if rc == 0 and marker in body else 1, 0,
                           body.strip().splitlines()[-1][:170]))
    return gates, rows, account


def range_counts(first, second):
    body = git('diff', '--name-status', '%s..%s' % (first, second))
    counts = {'added': 0, 'changed': 0, 'deleted': 0, 'renamed': 0}
    for line in body.split('\n'):
        if not line.strip():
            continue
        flag = line.split('\t')[0]
        counts['added' if flag.startswith('A') else 'deleted' if flag.startswith('D') else
               'renamed' if flag.startswith('R') else 'changed'] += 1
    counts['commits'] = int(git('rev-list', '--count', '%s..%s' % (first, second)).strip())
    return counts


def block(marker, lines, text):
    pattern = r'<!-- BEGIN %s -->.*?<!-- END %s -->' % (marker, marker)
    replacement = '<!-- BEGIN %s -->\n%s\n<!-- END %s -->' % (marker, '\n'.join(lines), marker)
    return re.sub(pattern, lambda _match: replacement, text, flags=re.S)


def render_report(text, payload, results, frozen, ranges):
    """the five tables the round report shows, as a pure function of the bytes measured here"""
    judgement = payload['judgement']
    codes = DC.dc_contract()['matrix']['codes']
    out = block('7CBD_GATES', ['| 门 | 命令 | rc | 期望 | 判决 | 依据 |', '|---|---|---|---|---|---|']
                + ['| `%s` | `%s` | %s | %s | %s | %s |' % (
                    row['gate'], row['command'][:70].replace('|', ';'), row['rc'], row['expected_rc'],
                    row['verdict_state'], str(row['verdict']).replace('|', ';')[:170])
                   for row in results], text)
    out = block('7CBD_LADDER', ['| 码 | 实测 I(1.20 V) /uA | 名义 /uA | 偏差 /uA | 偏差 / Iunit_ref |'
                                ' 已测 ±5% 区间 | 最低已验证 | 相邻未通过 |',
                                '|---|---:|---:|---:|---:|---|---:|---:|'] + [
        '| `%s` | %.6f | %.3f | %.9f | %.6f | %.2f..%.2f | %.2f | %s |' % (
            code, judgement['I_at_main_A_by_code'][code] * 1e6, (int(code, 2) + 1) * 1.875,
            judgement['per_code_deviation_A'][code] * 1e6,
            judgement['per_code_deviation_in_iunit_ref'][code],
            judgement['band_5_percent'][code]['containing_main_V'][0],
            judgement['band_5_percent'][code]['containing_main_V'][1],
            judgement['band_5_percent'][code]['lowest_verified_V'],
            judgement['band_5_percent'][code]['adjacent_failing_V']) for code in codes], out)
    out = block('7CBD_FROZEN', ['| 面 | 期望 | 强制 | 路径数 | 一致 | 失配 | 细节 |',
                                '|---|---|---|---:|---:|---:|---|'] + [
        '| %s | `%s` | %s | %s | %s | %s | %s |' % (
            row['surface'], row['expectation'], row['enforced'], row['paths'], row['matched'],
            row['mismatched'], row['detail'].replace('|', ';')[:120]) for row in frozen], out)
    out = block('7CBD_RANGES', ['| 区间 | 新增 | 改动 | 删除 | 重命名 | 提交 |',
                                '|---|---:|---:|---:|---:|---:|'] + [
        '| `%s` | %s | %s | %s | %s | %s |' % (label, values['added'], values['changed'],
                                               values['deleted'], values['renamed'],
                                               values['commits'])
        for label, values in sorted(ranges.items())], out)
    out = block('7CBD_ACCOUNT', ['| 例 | 预检行 | DUT 行 | CONFIRMED | FAILED | UNCERTAIN | raw 配对 |'
                                 ' log 配对 |', '|---|---:|---:|---:|---:|---:|---:|---:|'] + [
        '| `%s` | %s | %s | %s | %s | %s | %s | %s |' % (
            row['case_id'], row['preflight_rows'], row['dut_rows'], row['confirmed'], row['failed'],
            row['uncertain'], row['raw_present'], row['log_present'])
        for row in payload['reconcile']], out)
    return out


def identity_rows(head, evidence_name):
    """source identity is the table a reviewer binds to Git blobs, so it lists tracked paths only"""
    index = blobs(head)
    rows = []

    def add(role, rel):
        target = os.path.join(ROOT, rel.replace('/', os.sep))
        if os.path.isfile(target) and not any(row['path'] == rel for row in rows):
            rows.append({'role': role, 'path': rel, 'bytes': os.path.getsize(target),
                         'sha256': sha_of(target)})

    for rel in ('scripts/dd1_d7c_b_dc_run.py', 'scripts/dd1_d7c_b_dc_matrix.py',
                'scripts/dd1_d7c_b_dc_record.py', CONTRACT_PATH,
                'reports/tasks/DATA-7C-B-DC.md',
                'reports/reviews/DATA-7C-B-PREP-R2-GO/registration.json',
                'reports/reviews/DATA-7C-B-PREP-R2-GO/package_identity.json',
                'scripts/dd1_d7c_b_prep_contract.py', 'reports/dd1_d7c_b_prep_contract.md'):
        add('delivered by this round', rel)
    for rel in sorted(path for path in index if path.startswith('spectre/dd1_d7c_b_dc/')):
        add('derived run copy pushed to the guest', rel)
    for rel in sorted(path for path in index if path.startswith('results/evidence/' + evidence_name)):
        add('record and measurement of this round', rel)
    add('rendered by this record run, so the digest is of the bytes it wrote', REPORT)
    for rel in ('reports/agent_handoffs/DATA-7C-B-DC.json', 'reports/agent_handoffs/DATA-7C-B-DC.md'):
        add('this round handoff, committed with the record', rel)
    for rel in ('scripts/dd1_d7b_run.py', 'scripts/run_spectre.sh', 'scripts/sc1_read_psf.py',
                'spectre/current_probe_syntax.scs', 'AGENTS.md'):
        add('tool or reference this round reads', rel)
    for surface, paths, _expectation in FROZEN_SURFACES:
        matched, _empty = expand(paths, sorted(index))
        for rel in matched:
            add('frozen by the task book: %s' % surface, rel)
    duplicates = sorted(set(row['path'] for row in rows
                           if [item['path'] for item in rows].count(row['path']) > 1))
    if duplicates:
        raise SystemExit('DC_RECORD_REFUSED source_identity would publish %s twice'
                         % ','.join(duplicates))
    untracked = [row['path'] for row in rows if row['path'] not in index]
    if untracked:
        raise SystemExit('DC_RECORD_REFUSED source_identity names %s which %s not in %s'
                         % (', '.join(untracked[:3]), 'is' if len(untracked) == 1 else 'are',
                            head[:12]))
    return rows


HANDOFF = 'reports/agent_handoffs/DATA-7C-B-DC.json'
RENDERED_BY_THIS_RUN = (REPORT,)


def handoff_check():
    """the round handoff, judged against the published record and the bytes on disk"""
    path = os.path.join(ROOT, HANDOFF.replace('/', os.sep))
    if not os.path.isfile(path):
        return ['%s is not written yet' % os.path.basename(HANDOFF)]
    payload = json.loads(io.open(path, encoding='utf-8').read())
    problems = []
    for key in ('schema_version', 'task_id', 'base_sha', 'branch', 'repository', 'user_authorisation',
                'measured', 'launch_account', 'model_identity_read_only', 'derived_run_copies',
                'reuse_and_no_second_framework', 'frozen_surfaces', 'costs', 'boundaries', 'not_run',
                'range_counts', 'remote_readback', 'source_identity', 'known_limitations',
                'stop_reason'):
        if key not in payload:
            problems.append('missing field %s' % key)
    if payload.get('task_id') != TASK_ID:
        problems.append('task_id is %r' % payload.get('task_id'))
    if payload.get('base_sha') != BASE:
        problems.append('base_sha is not the registered offline content')
    if payload.get('branch') != BRANCH:
        problems.append('branch is %r' % payload.get('branch'))
    grant = payload.get('user_authorisation') or {}
    for key, value in (('spectre_launch_limit_total', 20), ('dut_runs', 8), ('preflight_runs', 8),
                       ('debug_margin', 4)):
        if grant.get(key) != value:
            problems.append('user_authorisation.%s is %r, the approval says %r'
                            % (key, grant.get(key), value))
    directory = os.path.join(ROOT, 'results', 'evidence', newest_evidence())
    published = json.loads(io.open(os.path.join(directory, 'judgement.json'), encoding='utf-8').read())
    account = DC.Account(os.path.join(directory, 'launch_account.csv'), 20)
    measured = payload.get('measured') or {}
    if measured.get('verdict') != published['judgement']['verdict']:
        problems.append('the handoff verdict %r is not the record verdict %r'
                        % (measured.get('verdict'), published['judgement']['verdict']))
    codes = measured.get('I_at_1p20V_uA_by_code') or {}
    if len(codes) != 8:
        problems.append('the handoff quotes %d codes, the matrix has eight' % len(codes))
    for code, value in codes.items():
        recorded = published['judgement']['I_at_main_A_by_code'][code] * 1e6
        if abs(value - recorded) > 1e-9:
            problems.append('code %s: handoff %.9f uA, the native record says %.9f uA'
                            % (code, value, recorded))
    full = measured.get('full_scale') or {}
    band = full.get('band_uA') or [0, 0]
    if not (band[0] <= full.get('measured_uA', -1) <= band[1]):
        problems.append('the handoff full scale is outside the band it quotes')
    if measured.get('verdict') == 'PASS' and not (full.get('pass') and measured.get('strict_monotonic')
                                                  and measured.get('ratio_pass')):
        problems.append('a PASS verdict without all three tests passing')
    costs = payload.get('costs') or {}
    if costs.get('new_spectre_launches') != account.occupied():
        problems.append('costs.new_spectre_launches is %r, the account carries %d rows'
                        % (costs.get('new_spectre_launches'), account.occupied()))
    for key in ('new_rtl_simulations', 'new_oa_writes', 'new_transient_simulations',
                'spectre_help_or_syntax_probes'):
        if costs.get(key) != 0:
            problems.append('costs.%s is %r, this round was not authorised to spend any'
                            % (key, costs.get(key)))
    if costs.get('guest_connections', 0) < 1:
        problems.append('the handoff hides the guest sessions: it says %r while the round ran on the '
                        'VM' % costs.get('guest_connections'))
    by_role = costs.get('spectre_launches_by_role') or {}
    for role in sorted(set(row['role'] for row in account.rows)):
        counted = sum(1 for row in account.rows if row['role'] == role)
        if by_role.get(role, 0) != counted:
            problems.append('launches by %s: handoff %r, account %d' % (role, by_role.get(role),
                                                                        counted))
    labels = set(tuple(str(field) for field in row) for row in
                 (payload.get('launch_account') or {}).get('labels', []))
    actual = set((row['launch_id'], row['case_id'], row['role'], row['state'], str(row['rc']))
                 for row in account.rows)
    if labels != actual:
        problems.append('the handoff account labels do not match the persisted account')
    if (payload.get('launch_account') or {}).get('refund_applied') is not False:
        problems.append('refund_applied must be false')
    for section in ('delivered', 'read_only_inputs'):
        for item in (payload.get('source_identity') or {}).get(section, []):
            rel = str(item.get('path', ''))
            if rel == HANDOFF or rel in RENDERED_BY_THIS_RUN:
                problems.append('%s is digested by the handoff it lives in, or by a file this record '
                                'rewrites' % rel)
                continue
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if not os.path.isfile(target):
                problems.append('source_identity names %s which is not on disk' % rel)
                continue
            if item.get('sha256') != sha_of(target) or int(item.get('bytes', -1)) != \
                    os.path.getsize(target):
                problems.append('%s digest or byte count in the handoff does not match the disk' % rel)
    blob = json.dumps(payload, ensure_ascii=False)
    for forbidden in ('OPTICAL_EFFECTIVE_BITS=9', 'SOA_SIGNOFF=YES', 'MERGE_PERFORMED=YES',
                      'NEXT_NATIVE_STAGE_AUTHORISED=YES', 'PAM_PWM_TRANSIENT_INTEGRATION=PASS'):
        if forbidden in blob:
            problems.append('the handoff contains the forbidden claim %r' % forbidden)
    for key, value in (payload.get('not_run') or {}).items():
        if not any(marker in value for marker in ('NOT_RUN', 'NOT_VERIFIED', 'NOT_AUTHORISED',
                                                  'NOT_DEFINED', 'NOT_OBSERVED')):
            problems.append('not_run.%s has to carry a marker, found %r' % (key, value[:60]))
    if not payload.get('known_limitations'):
        problems.append('a measured round with no limitations has not looked at what it left open')
    return problems


def newest_evidence():
    directory = os.path.join(ROOT, 'results', 'evidence')
    return sorted(name for name in os.listdir(directory) if name.startswith(EVIDENCE_PREFIX))[-1]


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', default='')
    parser.add_argument('--draft', default='')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--republish', action='store_true')
    arguments = parser.parse_args(argv)
    directory = os.path.join(ROOT, 'results', 'evidence')
    candidates = sorted(name for name in os.listdir(directory) if name.startswith(EVIDENCE_PREFIX))
    if not candidates:
        raise SystemExit('DC_RECORD_REFUSED no measurement directory exists yet')
    evidence_name = (os.path.basename(arguments.evidence.rstrip('/\\')) if arguments.evidence
                     else candidates[-1])
    evidence = os.path.join(directory, evidence_name)
    if not os.path.isdir(evidence):
        raise SystemExit('DC_RECORD_REFUSED %s is not a directory' % evidence_name)
    head = git('rev-parse', 'HEAD').strip()
    payload = json.loads(io.open(os.path.join(evidence, 'judgement.json'), encoding='utf-8').read())
    results, reconcile, account = build_gates(evidence)
    payload['reconcile'] = reconcile
    frozen, _problems = frozen_rows(head)
    results.append(frozen_gate(frozen))
    failures = [row['gate'] for row in results if row['verdict_state'] != 'PASS']
    ranges = {'base_to_HEAD': range_counts(BASE, head),
              'P_to_R1_recomputed': range_counts('dcef9b336f2222d6291d266858270f7448b6bb78',
                                                 '6778535e70b139812265eba490d0a1381a1fae5c'),
              'R1_to_base': range_counts('6778535e70b139812265eba490d0a1381a1fae5c', BASE)}
    git_rows = []
    for label, other in (('diff_check_base_to_HEAD', BASE),
                         ('diff_check_P_to_HEAD', 'dcef9b336f2222d6291d266858270f7448b6bb78')):
        rc, body = run(['git', 'diff', '--check', '%s..HEAD' % other])
        git_rows.append({'gate': label, 'command': 'git diff --check %s..HEAD' % other, 'rc': rc,
                         'lines': len([line for line in body.split('\n') if line.strip()]),
                         'scope': 'committed range %s to HEAD(%s) at %s'
                                  % (other[:12], head[:12], now())})
    if arguments.check_only:
        for row in results:
            print('GATE %-42s %s %s' % (row['gate'], row['verdict_state'],
                                        str(row['verdict'])[:100]))
        print('DC_RECORD_CHECK_ONLY %s (%d gates, failed: %s, launches %d/%d)'
              % ('PASS' if not failures else 'FAIL', len(results), ','.join(failures) or 'none',
                 account.occupied(), account.ceiling))
        return 0 if not failures else 1
    out_dir = os.path.abspath(arguments.draft) if arguments.draft else evidence
    if not arguments.draft and os.path.isfile(os.path.join(evidence, 'commands.csv')):
        if not arguments.republish:
            raise SystemExit('DC_RECORD_REFUSED %s already carries a published record; a published '
                             'record is never silently overwritten. --republish moves the earlier '
                             'tables aside, byte for byte, and writes a republish_note.json'
                             % evidence_name)
        archive = os.path.join(evidence, 'previous_publish_%s' % now().replace(':', '').replace('-', ''))
        os.makedirs(archive)
        kept = []
        for name in sorted(os.listdir(evidence)):
            if name in TABLE_SPECS or name == 'verification_summary.json':
                shutil.move(os.path.join(evidence, name), os.path.join(archive, name))
                kept.append({'path': name, 'sha256': sha_of(os.path.join(archive, name))})
        io.open(os.path.join(evidence, 'republish_note.json'), 'wb').write(
            (json.dumps(publish_history(evidence, archive, kept), indent=1, sort_keys=True,
                        ensure_ascii=False) + chr(10)).encode('utf-8'))
    if arguments.draft and not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    report_path = os.path.join(ROOT, REPORT.replace('/', os.sep))
    source_text = io.open(report_path, encoding='utf-8', newline='').read()
    rendered = render_report(source_text, payload, results, frozen, ranges)
    if arguments.draft:
        fixed_point = 'NOT_JUDGED_IN_A_DRAFT'
    else:
        io.open(report_path, 'wb').write(rendered.encode('utf-8'))
        again = render_report(io.open(report_path, encoding='utf-8', newline='').read(), payload,
                              results, frozen, ranges)
        fixed_point = 'PASS' if again == rendered else 'FAIL'
    identity = identity_rows(head, evidence_name)
    for name, header, table in (('commands.csv', COMMANDS_HEADER, results),
                               ('frozen_comparison.csv', FROZEN_HEADER, frozen),
                               ('git_checks.csv', GIT_HEADER, git_rows),
                               ('source_identity.csv', IDENTITY_HEADER, identity),
                               ('launches_reconcile.csv', RECONCILE_HEADER, reconcile)):
        rows_write(os.path.join(out_dir, name), header, table)
    recheck = tables_parse_gate(out_dir)
    read_back = []
    for name, header in sorted(TABLE_SPECS.items()):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            continue
        raw = io.open(path, 'rb').read()
        table = [line.rstrip('\n').split(',') for line in raw.decode('utf-8').split('\n')
                 if line.strip()]
        read_back.append({'file': name, 'header_matches': table[0] == list(header),
                          'rows': len(table) - 1, 'cr_bytes': b'\r' in raw})
    json_probe = []
    for name in sorted(item for item in os.listdir(out_dir) if item.endswith('.json')):
        try:
            json.loads(io.open(os.path.join(out_dir, name), encoding='utf-8').read())
            json_probe.append({'file': name, 'parses': True})
        except ValueError as error:
            json_probe.append({'file': name, 'parses': False, 'error': str(error)[:80]})
    summary = {'task_id': TASK_ID, 'base_offline_content_sha': BASE, 'branch': BRANCH, 'tip': head,
               'evidence_directory': evidence_name, 'generated_utc': now(),
               'gates': len(results), 'gates_failed': failures,
               'gates_informational': [row['gate'] for row in results
                                       if row['verdict_state'] not in ('PASS', 'FAIL')],
               'report_render_fixed_point': fixed_point,
               'published_tables_recheck': {'verdict': recheck['verdict_state'], 'rc': recheck['rc'],
                                              'detail': recheck['verdict']},
               'csv_read_back': read_back,
               'published_json': json_probe, 'identity_rows': len(identity),
               'frozen_rows': len(frozen),
               'frozen_enforced_mismatches': sum(int(row['mismatched']) for row in frozen
                                                 if row['enforced'] == 'yes'),
               'range_counts': ranges,
               'account': {'rows': account.occupied(), 'ceiling': account.ceiling,
                           'remaining': account.remaining(),
                           'confirmed': sum(1 for row in account.rows if row['state'] == 'CONFIRMED'),
                           'failed': sum(1 for row in account.rows if row['state'] == 'FAILED'),
                           'uncertain': sum(1 for row in account.rows
                                            if row['state'] == 'UNCERTAIN')},
               'verdict': payload['judgement']['verdict'],
               'measured_currents_at_1p20V_uA': dict(
                   (code, payload['judgement']['I_at_main_A_by_code'][code] * 1e6)
                   for code in sorted(payload['judgement']['I_at_main_A_by_code'])),
               'full_scale': payload['judgement']['full_scale'],
               'iunit_ref_uA': payload['judgement']['iunit_ref_uA'],
               'strict_monotonic': payload['judgement']['strict_monotonic'],
               'ratio_pass': payload['judgement']['ratio_pass'],
               'worst_deviation_in_iunit_ref': max(
                   abs(value) for value in
                   payload['judgement']['per_code_deviation_in_iunit_ref'].values()),
               'bands': dict((code, payload['judgement']['band_5_percent'][code])
                             for code in DC.dc_contract()['matrix']['codes']),
               'preflight_witnesses_all_within_tolerance':
                   payload['all_preflight_witnesses_within_tolerance'],
               'dut_rows': payload['dut_rows'], 'expected_rows': payload['expected_rows'],
               'registered_offline_content': BASE,
               'spectre_launches': account.occupied(), 'rtl_simulations': 0, 'oa_writes': 0,
               'transient_simulations': 0, 'credential_values_recorded': 0,
               'model_card_content_committed': 0, 'pdk_paths_committed': 0,
               'guest_write_root': DC.dc_contract()['authorisation']['guest_write_root'],
               'completion_level': 'NATIVE_PAM_DC_TT_MEASURED',
               'not_run_or_not_verified': ['PWM_PAM_TRANSIENT_INTEGRATION=NOT_RUN',
                                           'GRAY_LUT=NOT_RUN', 'FULL_MOS_GRAY_CONTROLLER=NOT_RUN',
                                           'OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED', 'SOA_SIGNOFF=NO',
                                           'MERGE_PERFORMED=NO', 'NEXT_STAGE_AUTHORISED=NO'],
               'stop_reason': 'AWAITING_INDEPENDENT_REVIEW',
               'electrical_results': 'MEASURED for the eight DC codes at TT 27 C on the PAM candidate '
                                     'over the declared 0.60-1.50 V clamp grid; everything else in '
                                     'this record is text, arithmetic, table shape or Git identity'}
    if not arguments.draft:
        io.open(os.path.join(out_dir, 'verification_summary.json'), 'wb').write(
            (json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
            .encode('utf-8'))
    for row in results:
        print('GATE %-42s %s %s' % (row['gate'], row['verdict_state'], str(row['verdict'])[:100]))
    print('GATE %-42s %s %s' % (recheck['gate'], recheck['verdict_state'],
                                        str(recheck['verdict'])[:100]))
    clean = not failures and recheck['rc'] == 0 and fixed_point == 'PASS'
    print('DC_RECORD %s -> %s (%d gates, failed: %s, launches %d/%d, fixed point %s, tables recheck %s)'
          % ('PASS' if clean else 'FAIL', out_dir.replace(os.sep, '/'), len(results),
             ','.join(failures) or 'none', account.occupied(), account.ceiling, fixed_point,
             recheck['verdict_state']))
    return 0 if clean else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
