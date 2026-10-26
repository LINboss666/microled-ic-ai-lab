#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_dc_record.py -- publish this round's record tables over the bytes Git actually carries.

DATA-7C-B-DC-R1: the entry point is now the repair round's. It still publishes the ledger of commands
with their real rc, the blob-level frozen comparison, the source identity, the account reconciliation
and the rendered tables, but two things changed on purpose. Source identity is taken from a Git blob
(the committed one, or the staged one this run just added) and never from the working copy, because the
working copy may carry CRLF where the repository carries LF -- that is how two figure digests drifted
out of the previous record. And every complete-matrix PASS path now walks DC.validate_dc_matrix first.

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

TASK_ID = 'DATA-7C-B-DC-R1'
BASE = '337563fc22699e480bf7fc82890750c126a50654'     # the DC tip this repair round is cut from
OFFLINE_BASE = DC.BASE_SHA                            # e51c532, the registered offline content
MEASURED = 'results/evidence/dd1_d7c_b_dc_r20261026_015212_376554'   # the native round, read-only
BRANCH = 'poc/data-pam-d7c-b-dc-r1'
REPORT = 'reports/dd1_d7c_b_dc_review_fix_r1.md'
CONTRACT_PATH = 'tests/dd1_d7c_b_dc/contract.json'
EVIDENCE_PREFIX = 'dd1_d7c_b_dc_r1_'
COMMANDS_HEADER = ('gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict')
FROZEN_HEADER = ('surface', 'expectation', 'enforced', 'paths', 'matched', 'mismatched', 'detail')
GIT_HEADER = ('gate', 'command', 'rc', 'lines', 'scope')
IDENTITY_HEADER = ('role', 'path', 'bytes', 'sha256', 'identity_source')
RECONCILE_HEADER = ('case_id', 'preflight_rows', 'dut_rows', 'confirmed', 'failed', 'uncertain',
                    'raw_present', 'log_present', 'note')
ALLOWED_MODIFIED = ('scripts/dd1_d7c_b_dc_run.py', 'scripts/dd1_d7c_b_dc_matrix.py',
                    'scripts/dd1_d7c_b_dc_record.py')
# what the measured DC round was allowed to move on its way from the registered offline content here;
# an earlier round binding its own bytes names these, and naming them is not a new fault
MEASURED_ROUND_MODIFIED = ('scripts/dd1_d7c_b_prep_contract.py', 'reports/dd1_d7c_b_prep_contract.md')
NEW_PREFIXES = ('results/evidence/dd1_d7c_b_dc_r1_', 'reports/dd1_d7c_b_dc_review_fix_r1.md',
                'reports/agent_handoffs/DATA-7C-B-DC-R1', 'reports/tasks/DATA-7C-B-DC-R1.md')
BLOB_STAGED_SOURCE = 'git blob staged by this record run'
DISK_REJECTED = 'the working copy is never an identity: Git may normalise it before it is stored'
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
    ('the measured DC round: tables, record, report and handoff',
     (MEASURED,), 'identical'),
    ('the DC round report and handoff', ('reports/dd1_d7c_b_dc_report.md',
                                         'reports/agent_handoffs/DATA-7C-B-DC.json',
                                         'reports/agent_handoffs/DATA-7C-B-DC.md',
                                         'reports/tasks/DATA-7C-B-DC.md'), 'identical'),
    ('the six masters and eight derived preflight decks of the DC round',
     ('spectre/dd1_d7c_b_dc',), 'identical'),
    ('the DC contract of the measured round', (CONTRACT_PATH,), 'identical'),
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
            'reason_of_the_latest_move': 'this round re-exported its evidence directory without copying '
                                         'the two figures (they are referenced where they are, so the '
                                         'whitespace they carry is not moved into the range of this '
                                         'round), and the report prose gained the clarification that '
                                         '756 check output lines are the 378 flagged locations; the '
                                         'tables were therefore re-derived over the same reused '
                                         'measurements',
            'latest_move': {'into': os.path.basename(archive), 'files': kept},
            'all_previous_publishes': archives}


def rows_write(path, header, table):
    """a published table is read back by splitting on commas, so no field may carry one; and a published
    line carries no trailing space, because git diff --check reads these tables as text"""
    clean = [[str(row.get(key, '')).replace(',', ';').replace(chr(10), ' | ').replace(chr(13), '').strip()
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


def git_bytes(*args):
    return subprocess.check_output(['git', '-C', ROOT] + list(args))


def blob_of(rel):
    """the bytes the record commit will carry for this path, read out of the index. The working copy is
    deliberately not consulted: with core.autocrlf the file on disk can hold CRLF where the stored blob
    holds LF, and a digest taken from the disk is then not the digest a reviewer reproduces from Git."""
    try:
        return git_bytes('cat-file', 'blob', ':%s' % rel)
    except subprocess.CalledProcessError:
        raise SystemExit('DC_RECORD_REFUSED %s has no staged blob, so the record cannot name the bytes '
                         'it is about to commit. %s' % (rel, DISK_REJECTED))


def round_paths(evidence_name):
    """what this record may put into the index: its own evidence directory, the three files the task
    book allows, and the reports or handoff it is publishing"""
    directory = os.path.join(ROOT, 'results', 'evidence', evidence_name)
    out = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            out.append(os.path.relpath(os.path.join(root, name), ROOT).replace(os.sep, '/'))
    for rel in ('scripts/dd1_d7c_b_dc_run.py', 'scripts/dd1_d7c_b_dc_matrix.py',
                'scripts/dd1_d7c_b_dc_record.py', REPORT,
                'reports/agent_handoffs/DATA-7C-B-DC-R1.json',
                'reports/agent_handoffs/DATA-7C-B-DC-R1.md',
                'reports/tasks/DATA-7C-B-DC-R1.md'):
        target = os.path.join(ROOT, rel.replace('/', os.sep))
        if os.path.isfile(target) and rel not in out:
            out.append(rel)
    return sorted(out)


def stage(paths):
    """only this round's own new paths and the three files its task book allows may enter the index"""
    outside = [rel for rel in paths if not any(rel.startswith(prefix) for prefix in NEW_PREFIXES)
               and rel not in ALLOWED_MODIFIED]
    if outside:
        raise SystemExit('DC_RECORD_REFUSED the record would stage %s, which this round%s not allowed '
                         'to touch' % (', '.join(outside[:3]), 'is' if len(outside) == 1 else 'are'))
    if paths:
        subprocess.check_call(['git', '-C', ROOT, 'add', '--'] + list(paths))

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


def _digest_tree(directory):
    out = {}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            out[name] = sha_of(path)
    return out


def r1_gates(evidence, scratch, answers_dir, evidence_name):
    """the four gap families the independent review named, each with its positive and negative case"""
    gates = []
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    codes = DC.dc_contract()['matrix']['codes']
    dut = MATRIX.merged(evidence, 'dut')
    clean = DC.judge(dut)
    flipped = [dict(row, I_sink_A='%.9e' % -abs(float(row['I_sink_A'])),
                    I_sink_uA='%.6f' % -abs(float(row['I_sink_uA'])))
               if abs(float(row['clamp_V']) - 0.60) < 1e-9 else row for row in dut]
    signed = DC.judge(flipped)
    narrowed = [code for code in codes
                if signed['band_5_percent'][code]['lowest_verified_V'] == 0.65
                and signed['band_5_percent'][code]['adjacent_failing_V'] == 0.6]
    kept_main = signed['verdict'] == 'PASS' and clean['verdict'] == 'PASS'
    untouched_band = all(clean['band_5_percent'][code]['lowest_verified_V'] == 0.60
                         for code in codes)
    problems = [] if (len(narrowed) == 8 and kept_main and untouched_band) else [
        'codes whose 0.60 V point stayed inside the band: %s' % (','.join(
            code for code in codes if code not in narrowed) or 'none'),
        'main verdict after the flip %s, before %s' % (signed['verdict'], clean['verdict'])]
    gates.append(_gate('f1_signed_band_keeps_the_direction_of_a_reading',
                       'in process: judge the 152 published rows, then the same table with the eight '
                       '0.60 V readings signed over, point by point', 0 if not problems else 1, 0,
                       'signed criterion abs(I - I(1.2 V)) <= 0.05 * abs(I(1.2 V)): %d of eight codes '
                       'now narrow to 0.65 V with 0.60 V named as the adjacent failing point, the main '
                       '1.20 V verdict stays PASS for both tables, and the unmutated matrix still reads '
                       '0.60..1.50 V (%s)' % (len(narrowed), '; '.join(problems) or 'clean')))
    deck_sha = DC.delivered_deck('DC-000')[1]
    positive_path = os.path.join(scratch, 'complete.raw')
    DC.synthetic_psf(positive_path, [1.875e-6] * 19, omit=(), code='000')
    good_rows, good_info = DC.extract(positive_path, deck_sha, 'DC-000', 'dut', 'fixture', 'DTEST')
    refused, accepted_after, bad_unit = [], [], []
    for name in ('Ip_branch:i',) + DC.REQUIRED_SIGNALS:
        path = os.path.join(scratch, 'missing_%s.raw' % name.replace(':', '_'))
        DC.synthetic_psf(path, [1.875e-6] * 19, omit=() if name == 'Ip_branch:i' else (name,),
                         no_probe=name == 'Ip_branch:i', code='000')
        try:
            rows, _info = DC.extract(path, deck_sha, 'DC-000', 'dut', 'fixture', 'DTEST')
            accepted_after.append('%s (%d rows, %s)' % (name, len(rows),
                                                        rows[0].get('vdd18_V') if rows else ''))
        except DC.Refuse as error:
            if name.split(':')[0] not in str(error):
                refused.append('%s refused but did not name it: %s' % (name, str(error)[:60]))
        if name == 'pam1':
            wrong = os.path.join(scratch, 'bad_unit_pam1.raw')
            DC.synthetic_psf(wrong, [1.875e-6] * 19, omit=(), bad_unit='pam1', code='000')
            try:
                DC.extract(wrong, deck_sha, 'DC-000', 'dut', 'fixture', 'DTEST')
                bad_unit.append('a pam1 column without a unit was accepted')
            except DC.Refuse as error:
                if 'unit' not in str(error):
                    bad_unit.append('refused for another reason: %s' % str(error)[:80])
    sentinel = os.path.join(scratch, 'output_dir')
    os.makedirs(sentinel)
    io.open(os.path.join(sentinel, 'sentinel.txt'), 'wb').write(b'the refusal must not touch this\n')
    before = _digest_tree(sentinel)
    rc_cli, body_cli = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_run.py'), '--extract',
                            os.path.join(scratch, 'missing_vdd18.raw'), '--deck-sha', deck_sha,
                            '--case', 'DC-000', '--role', 'dut', '--run-id', 'fixture',
                            '--out', sentinel])
    after = _digest_tree(sentinel)
    problems = []
    if len(good_rows) != 19:
        problems.append('the complete fixture returned %d rows, 19 were required' % len(good_rows))
    if accepted_after:
        problems.append('missing signals still accepted: %s' % ', '.join(accepted_after))
    if refused:
        problems.extend(refused)
    if bad_unit:
        problems.extend(bad_unit)
    if good_info['code_measured'] != '000' or good_info['code_from_deck'] != '000':
        problems.append('the fixture code did not round-trip: %s' % good_info['code_measured'])
    if rc_cli != 1 or after != before or len(after) != 1:
        problems.append('a refusal through --extract wrote into the output directory (rc=%s, files '
                        'after %s, before %s)' % (rc_cli, sorted(after), sorted(before)))
    gates.append(_gate('f2_a_missing_required_signal_is_a_refusal',
                       'in process: synthetic_psf with one required column removed at a time, then '
                       'extract() against the frozen DC-000 deck, then one refusal through --extract into '
                       'a pre-populated output directory', 0 if not problems else 1, 0,
                       'complete fixture gives 19 rows, code %s from the columns and %s from the deck; '
                       '%d of %d required signals (axis probe included) refused by naming the signal, no '
                       'nominal fill-in survived, and a refusal left the output directory at %s file(s) '
                       'with identical digests (%s)'
                       % (good_info['code_measured'], good_info['code_from_deck'],
                          len(DC.REQUIRED_SIGNALS) + 1 - len(refused) - len(accepted_after),
                          len(DC.REQUIRED_SIGNALS) + 1, len(after),
                          '; '.join(problems) or 'clean')))
    eight = [row for row in dut if abs(float(row['clamp_V']) - 1.20) < 1e-9]
    short_table = os.path.join(scratch, 'eight_rows.csv')
    B7B.write_rows(short_table, [[row[key] for key in DC.ROWS_HEADER] for row in eight],
                   list(DC.ROWS_HEADER))
    rc_eight, body_eight = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_run.py'),
                                '--judge', short_table])
    rc_full, body_full = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_run.py'),
                              '--judge', os.path.join(evidence, 'dc_matrix_dut.csv')])
    mutations = {}
    for label, rows in (('one_row_short', dut[:-1]),
                        ('one_extra_point', dut + [dict(dut[0], clamp_V='1.550')]),
                        ('a_duplicate_replaces_a_missing_point',
                         [dict(row, clamp_V='0.600') if row is dut[-1] else row for row in dut]),
                        ('a_non_finite_current',
                         [dict(row, I_sink_A='nan') if row is dut[0] else row for row in dut]),
                        ('a_wrong_unit', [dict(row, unit_current='') if row is dut[0] else row
                                          for row in dut]),
                        ('a_code_not_in_the_matrix',
                         [dict(row, code='222') if row is dut[0] else row for row in dut]),
                        ('a_broken_column_set', [dict((key, value) for key, value in row.items()
                                                     if key != 'pam_bits') if row is dut[0] else row
                                                  for row in dut])):
        try:
            result = DC.judge(rows)
            mutations[label] = 'accepted with verdict %s' % result['verdict']
        except DC.Refuse as error:
            mutations[label] = str(error)[:150]
    unexpected = [label for label, answer in sorted(mutations.items())
                  if not answer.startswith('the DC matrix')]
    flipped_sign = DC.main_point_arithmetic(
        dict((code, [dict(row, I_sink_A='%.9e' % -abs(float(row['I_sink_A'])))
                    for row in dut if row['code'] == code
                    and abs(float(row['clamp_V']) - 1.2) < 1e-9]) for code in codes),
        DC.criteria()[0], codes)
    gates.append(_gate('f3_every_complete_pass_path_validates_the_matrix_first',
                       'in process: judge() over the 152 rows, over eight rows, and over seven broken '
                       'tables; plus the public --judge entry on both tables',
                       0 if (rc_eight == 1 and 'DC_JUDGE_REFUSED' in body_eight and rc_full == 0
                             and not unexpected and not flipped_sign['absolute_pass']) else 1, 0,
                       'the eight-row table is refused at the public --judge entry (rc=%s), the full '
                       'table judges PASS (rc=%s), %d of %d mutations refused at the matrix gate (%s), '
                       'and negating the eight main readings turns absolute_pass False without turning '
                       'any current positive' % (rc_eight, rc_full, len(mutations) - len(unexpected),
                                                 len(mutations),
                                                 '; '.join(unexpected) or 'all named')))
    earlier = os.path.join(ROOT, MEASURED.replace('/', os.sep))
    earlier_rows = [row for row in
                    _read_table(os.path.join(earlier, 'source_identity.csv'))
                    if row['path'].endswith('.svg')]
    published_identity = identity_rows(evidence_name)
    crlf_proof, new_rows = [], []
    for row in earlier_rows:
        data = git_bytes('cat-file', 'blob', '%s:%s' % (BASE, row['path']))
        crlf = data.replace(b'\n', b'\r\n')
        if DC.sha_bytes(crlf) != row['sha256'] or len(crlf) != int(row['bytes']):
            crlf_proof.append('%s is not the CRLF form of the committed LF blob' % row['path'])
        if DC.sha_bytes(data) == row['sha256']:
            crlf_proof.append('%s matched after all, so the earlier row was never stale' % row['path'])
        if not any(os.path.basename(item['path']) == os.path.basename(row['path'])
                   for item in published_identity):
            new_rows.append('%s is not re-declared by this record' % row['path'])
    gates.append(_gate('f4_identity_rows_are_blob_bytes_and_the_stale_two_are_named',
                       'in process: re-derive the two figure digests from the committed LF blob, take '
                       'the CRLF form, and compare both against the earlier record',
                       0 if not (crlf_proof or new_rows) else 1, 0,
                       'the two figures a reviewer cannot reproduce from Git are exactly the CRLF '
                       'rendering of the LF blob (%d paths named, %d bytes recorded against %d blob '
                       'bytes); this record publishes %d rows taken from the staged blob and re-declares '
                       'both figures (%s)'
                       % (len(earlier_rows), int(earlier_rows[0]['bytes']),
                          len(git_bytes('cat-file', 'blob', '%s:%s' % (BASE, earlier_rows[0]['path']))),
                          len(published_identity),
                          '; '.join(crlf_proof + new_rows) or 'root cause reproduced')))
    if answers_dir and os.path.isdir(answers_dir):
        replayed, mismatches, refused_here = 0, [], []
        for case_id in DC.dc_contract()['matrix']['launch_order']:
            for role in ('dut', 'preflight'):
                raw = os.path.join(answers_dir, 'r20261026_015212_376554_%s_%s.raw' % (case_id, role))
                published = MATRIX.read_rows(os.path.join(earlier, 'rows_%s_%s.csv'
                                                           % (case_id, role)))
                if not os.path.isfile(raw):
                    refused_here.append('%s %s has no saved answer on this machine' % (case_id, role))
                    continue
                try:
                    rows, _info = DC.extract(raw, published[0]['deck_sha256'], case_id, role,
                                             'r1replay', published[0]['launch_id'])
                except DC.Refuse as error:
                    refused_here.append('%s %s refused: %s' % (case_id, role, str(error)[:120]))
                    continue
                replayed += 1
                for key in DC.ROWS_HEADER:
                    if key in ('run_id',):
                        continue
                    differ = [index for index in range(19) if rows[index][key] != published[index][key]]
                    if differ:
                        mismatches.append('%s %s %s differs at points %s'
                                          % (case_id, role, key, differ[:3]))
        gates.append(_gate('f5_the_saved_answers_still_extract_to_the_published_rows',
                           'python dd1_d7c_b_dc_run.py --extract <saved raw> --deck-sha <published deck> '
                           '--case <case> --role <role> (in process, over the saved native answers of '
                           'the measured round)',
                           0 if (replayed == 16 and not mismatches and not refused_here) else 1, 0,
                           '%d of 16 case/role answers re-extracted with the hardened extractor, %d '
                           'field differences against the published rows, %d refusals (%s); the native '
                           'answers themselves are not shipped, their digests are in the account'
                           % (replayed, len(mismatches), len(refused_here),
                              '; '.join(mismatches + refused_here)[:200] or 'none')))
    else:
        gates.append(_gate('f5_the_saved_answers_still_extract_to_the_published_rows',
                           'needs the executor-saved .raw answers, given with --answers', 1, 0,
                           'NOT_RUN: no saved answer directory was given, so the hardened extractor was '
                           'not put against the real native text. This is a gap, not a pass.'))
    resolution = _identity_resolution(earlier)
    gates.append(_gate('f6_every_row_resolves_to_one_accounted_launch',
                       'in process: join (case_id, role, deck_sha256, raw_sha256) of the published rows '
                       'onto launch_account.csv', 0 if not resolution['problems'] else 1, 0,
                       '%d distinct native sources carry the 304 published rows, every one of them '
                       'exactly one accounted launch; %s'
                       % (resolution['sources'], '; '.join(resolution['problems']) or 'no gap')))
    empty = os.path.join(scratch, 'no_answers')
    os.makedirs(empty)
    rc_observe, body_observe = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_matrix.py'),
                                    'observe', empty])
    seen = json.loads(io.open(os.path.join(empty, 'observed_signals.json'),
                              encoding='utf-8').read())
    gates.append(_gate('f7_an_answer_that_is_not_here_is_not_a_pass',
                       'python dd1_d7c_b_dc_matrix.py observe <empty dir>',
                       0 if (rc_observe == 3 and seen['verdict'] == 'NOT_RUN'
                             and len(seen['not_run_because_no_answer_on_this_machine']) == 8
                             and all(case['observation_state'] == 'NOT_OBSERVED'
                                     for case in seen['cases'].values())) else 1, 0,
                       'a directory without native answers now answers verdict NOT_RUN and rc 3 with '
                       'all eight cases NOT_OBSERVED; the required signals are never inferred from a '
                       'table of nothing (%s)' % body_observe.strip().splitlines()[-1][:120]))
    worst_A = max(abs(value) for value in clean['per_code_deviation_A'].values())
    shown = '%.9e' % (worst_A * 1e6)
    exact = '%.9e' % (9.1175e-13 * 1e6)
    gates.append(_gate('f8_the_microamp_field_is_microamps',
                       'in process: format the worst residual with the published coefficient, check the '
                       'exact positive case 9.1175e-13 A, and format the same ampere value with the old '
                       '1e9 to show what changed',
                       0 if (exact == '9.117500000e-07'
                             and abs(float(shown) - worst_A * 1e6) <= 5e-10 * worst_A * 1e6
                             and '%.9e' % (worst_A * 1e9) != shown) else 1, 0,
                       'the exact positive case 9.1175e-13 A prints as %s uA; the worst residual of this '
                       'round, %.9e A, prints as %s uA, while the earlier 1e9 coefficient printed %s, '
                       'a thousand times too large. The ampere values in judgement.json are untouched'
                       % (exact, worst_A, shown, '%.9e' % (worst_A * 1e9))))
    return gates


def _read_table(path):
    lines = [line for line in io.open(path, encoding='utf-8', newline='').read().split('\n')
             if line.strip()]
    header = lines[0].split(',')
    return [dict(zip(header, line.split(','))) for line in lines[1:]]


def _identity_resolution(earlier):
    account = _read_table(os.path.join(earlier, 'launch_account.csv'))
    by_source = {}
    for row in account:
        if row['state'] in ('CONFIRMED', 'FAILED') and row['raw_sha256']:
            by_source.setdefault((row['case_id'], row['role'], row['deck_sha256'],
                                  row['raw_sha256']), []).append(
                (row['run_id'], row['launch_id']))
    problems, sources = [], set()
    for role in ('dut', 'preflight'):
        for case_id in DC.dc_contract()['matrix']['launch_order']:
            for row in _read_table(os.path.join(earlier, 'rows_%s_%s.csv' % (case_id, role))):
                key = (row['case_id'], row['role'], row['deck_sha256'], row['raw_sha256'])
                sources.add(key)
                hits = by_source.get(key)
                if not hits:
                    problems.append('%s %s has no account row for its deck and raw digests'
                                    % (case_id, role))
                elif len(hits) > 1:
                    problems.append('%s %s resolves to %d launches, which is one-to-many'
                                    % (case_id, role, len(hits)))
    return {'sources': len(sources), 'problems': problems,
            'rows': [{'case_id': key[0], 'role': key[1], 'legacy_run_id': 'manual',
                      'legacy_launch_id': 'D000', 'resolved_run_id': by_source[key][0][0],
                      'resolved_launch_id': by_source[key][0][1], 'deck_sha256': key[2],
                      'raw_sha256': key[3]} for key in sorted(sources) if by_source.get(key)]}


def build_gates(evidence, answers_dir='', evidence_name=''):
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
    moved_here_or_by_the_measured_round = set(ALLOWED_MODIFIED) | set(MEASURED_ROUND_MODIFIED)
    outside = [path for path in named if path not in moved_here_or_by_the_measured_round]
    other = [line for line in reasons
             if line and 'digest in the handoff does not match' not in line
             and 'byte count in the handoff does not match' not in line]
    ok = rc == 1 and named and not outside and not other
    gates.append({'gate': 'earlier_handoff_binds_its_own_bytes',
                  'command': 'python dd1_d7c_b_prep_r2_verify.py --handoff-check', 'rc': rc,
                  'expected_rc': '1', 'verdict_state': 'PASS' if ok else 'FAIL',
                  'verdict': 'rc=1 by design: the R2 handoff digests the bytes of its own round, and the '
                             'rounds since then legitimately moved %s. nothing else is reported (%s)'
                             % (', '.join(named) or 'no file', 'clean' if ok else text[:150])})
    observations = {'gate': 'internal_observations_recorded',
                    'command': 'in process: read observed_signals.json, written by '
                               'dd1_d7c_b_dc_matrix.py observe over the native answers this machine '
                               'still holds (see observation_provenance.json)',
                    'rc': 0, 'expected_rc': '0', 'verdict_state': 'PASS', 'verdict': 'provisional'}
    try:
        witness = json.loads(io.open(os.path.join(evidence, 'observed_signals.json'),
                                     encoding='utf-8').read())
        absent = sorted(set(sum([witness['cases'][case].get('requested_but_not_delivered', [])
                                 for case in witness['cases']], [])))
        not_run = witness.get('not_run_because_no_answer_on_this_machine', [])
        delivered = sorted(set(sum([[name for name in
                                     MATRIX.REQUESTED_SAVES
                                     if name not in case.get('requested_but_not_delivered', [])]
                                    for case in witness['cases'].values()], [])))
        problems = [] if (witness['verdict'] == 'PASS' and not not_run) else [
            'required signal missing in %s' % ', '.join(witness['required_signals_missing_in'])
            if witness['required_signals_missing_in'] else
            'no native answer was read for %s, so nothing is observed there' % ', '.join(not_run)]
        observations.update({
            'rc': len(problems), 'verdict_state': 'PASS' if not problems else 'FAIL',
            'verdict': 'every required signal (data_out, clamp_node, the supplies, the three PAM bits, '
                       'the reference node and vss) is present in all %d answers read from native text; '
                       'the deck asks for %d observation names, %d of them came back (eight en, eight '
                       'enb, eight per-unit vbias_ch, two node_m) and %d are NOT_OBSERVED under the '
                       'requested name: %s (the probe current is delivered as Ip_branch:i with :in and '
                       ':out, so the two aliases are stated rather than silently dropped); cases with no '
                       'answer on this machine: %s %s'
                       % (len(witness['cases']), len(MATRIX.REQUESTED_SAVES), len(delivered),
                          len(absent), ', '.join(absent) or 'none', ', '.join(not_run) or 'none',
                          '; '.join(problems) or '')})
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
              'deviation %.9e uA; bands contain 1.20 V for all eight codes; the matrix gate saw %d ' \
              'unique keys' % (
                  judgement['full_scale']['measured_uA'], judgement['full_scale']['band_uA'][0],
                  judgement['full_scale']['band_uA'][1], judgement['iunit_ref_uA'],
                  judgement['strict_monotonic'], judgement['ratio_pass'],
                  max(abs(judgement['per_code_deviation_A'][code]) for code in judgement[
                      'per_code_deviation_A']) * 1e6,
                  judgement.get('matrix_validation', {}).get('keys_unique', -1))
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
        gates.extend(r1_gates(evidence, os.path.join(scratch, 'r1'), answers_dir, evidence_name))
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


def staged_paths():
    out = {}
    for line in git('ls-files', '--stage').split('\n'):
        if not line.strip():
            continue
        meta, path = line.split('\t', 1)
        out[path] = meta.split()[1]
    return out


def identity_rows(evidence_name):
    """source identity is the table a reviewer binds to Git blobs, so every row is the digest of the
    blob the record commit carries, never of a working copy"""
    in_index = staged_paths()
    rows = []

    def add(role, rel):
        target = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.isfile(target):
            return
        if any(row['path'] == rel for row in rows):
            return
        if rel not in in_index:
            raise SystemExit('DC_RECORD_REFUSED source_identity would name %s, which has no staged blob, '
                             'so the record cannot state what the commit will carry. %s'
                             % (rel, DISK_REJECTED))
        data = blob_of(rel)
        rows.append({'role': role, 'path': rel, 'bytes': len(data), 'sha256': DC.sha_bytes(data),
                     'identity_source': BLOB_STAGED_SOURCE})

    for rel in ('scripts/dd1_d7c_b_dc_run.py', 'scripts/dd1_d7c_b_dc_matrix.py',
                'scripts/dd1_d7c_b_dc_record.py', CONTRACT_PATH,
                'reports/tasks/DATA-7C-B-DC.md', 'reports/tasks/DATA-7C-B-DC-R1.md',
                'reports/reviews/DATA-7C-B-PREP-R2-GO/registration.json',
                'reports/reviews/DATA-7C-B-PREP-R2-GO/package_identity.json',
                'scripts/dd1_d7c_b_prep_contract.py', 'reports/dd1_d7c_b_prep_contract.md'):
        add('delivered by this round or read by it', rel)
    for rel in sorted(path for path in in_index if path.startswith('spectre/dd1_d7c_b_dc/')):
        add('derived run copy pushed to the guest in the measured round', rel)
    for rel in sorted(path for path in in_index
                      if path.startswith('results/evidence/' + evidence_name)):
        add('record and repair evidence of this round', rel)
    add('rendered by this record run, over its own staged blob', REPORT)
    for rel in ('reports/agent_handoffs/DATA-7C-B-DC-R1.json',
                'reports/agent_handoffs/DATA-7C-B-DC-R1.md'):
        add('this round handoff, committed with the record', rel)
    for rel in ('scripts/dd1_d7b_run.py', 'scripts/run_spectre.sh', 'scripts/sc1_read_psf.py',
                'spectre/current_probe_syntax.scs', 'AGENTS.md'):
        add('tool or reference this round reads', rel)
    for surface, paths, _expectation in FROZEN_SURFACES:
        matched, _empty = expand(paths, sorted(in_index))
        for rel in matched:
            add('frozen by the task book: %s' % surface, rel)
    duplicates = sorted(set(row['path'] for row in rows
                           if [item['path'] for item in rows].count(row['path']) > 1))
    if duplicates:
        raise SystemExit('DC_RECORD_REFUSED source_identity would publish %s twice'
                         % ','.join(duplicates))
    return rows


HANDOFF = 'reports/agent_handoffs/DATA-7C-B-DC-R1.json'
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
        problems.append('base_sha is not the commit this round was cut from')
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
    native_round = not TASK_ID.endswith('-R1')
    if native_round:
        if costs.get('new_spectre_launches') != account.occupied():
            problems.append('costs.new_spectre_launches is %r, the account carries %d rows'
                            % (costs.get('new_spectre_launches'), account.occupied()))
        if costs.get('guest_connections', 0) < 1:
            problems.append('the handoff hides the guest sessions: it says %r while the round ran on '
                            'the VM' % costs.get('guest_connections'))
    else:
        if costs.get('new_spectre_launches') != 0:
            problems.append('costs.new_spectre_launches is %r: this repair round may not start a '
                            'process at all' % costs.get('new_spectre_launches'))
        if costs.get('reused_account_rows') != account.occupied():
            problems.append('costs.reused_account_rows is %r while the account it reuses carries %d '
                            'rows' % (costs.get('reused_account_rows'), account.occupied()))
        if costs.get('guest_connections', 0) != 0:
            problems.append('the repair round claims %r guest sessions, and its task book authorises '
                            'no ssh or VM action' % costs.get('guest_connections'))
        if costs.get('new_ssh_or_vm_actions') != 0:
            problems.append('costs.new_ssh_or_vm_actions is %r' % costs.get('new_ssh_or_vm_actions'))
    for key in ('new_rtl_simulations', 'new_oa_writes', 'new_transient_simulations',
                'spectre_help_or_syntax_probes'):
        if costs.get(key) != 0:
            problems.append('costs.%s is %r, this round was not authorised to spend any'
                            % (key, costs.get(key)))
    by_role = costs.get('spectre_launches_by_role' if native_round
                        else 'reused_account_rows_by_role') or {}
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
            if rel not in staged_paths():
                problems.append('source_identity names %s, which has no blob in the repository to '
                                'compare against' % rel)
                continue
            data = blob_of(rel)
            if item.get('sha256') != DC.sha_bytes(data) or int(item.get('bytes', -1)) != len(data):
                problems.append('%s digest or byte count in the handoff does not match the blob the '
                                'repository carries' % rel)
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


def reused_paths():
    """the files this round reuses from the measured round, named by their path in the repository.
    The two figures are not copied: they are referenced where they are, because a byte copy would move
    another thousand whitespace-flagged lines into the range of this round for no evidence gain."""
    names = ['launch_account.csv', 'dc_matrix_dut.csv', 'dc_matrix_preflight.csv']
    names += ['rows_%s_%s.csv' % (case_id, role)
              for case_id in DC.dc_contract()['matrix']['launch_order'] for role in ('dut', 'preflight')]
    return ['%s/%s' % (MEASURED, name) for name in names]


def export_r1(answers_dir, name=''):
    """Build the evidence directory of this repair round: reuse the measured tables exactly as Git
    stores them, recompute the judgement with the repaired tool, resolve every published row back onto
    one accounted launch, and re-observe the saved native answers. No process starts and no earlier
    byte is rewritten."""
    evidence_name = name or 'dd1_d7c_b_dc_r1_%s' % time.strftime('r%Y%m%d_%H%M%S', time.gmtime())
    directory = os.path.join(ROOT, 'results', 'evidence', evidence_name)
    if os.path.exists(directory):
        raise SystemExit('DC_R1_REFUSED %s already exists; a record directory is never reused'
                         % evidence_name)
    os.makedirs(directory)
    reused, differences = [], []
    for rel in reused_paths():
        data = git_bytes('cat-file', 'blob', '%s:%s' % (BASE, rel))
        inside = rel.replace(MEASURED + '/', '')
        target = os.path.join(directory, inside.replace('/', os.sep))
        if not os.path.isdir(os.path.dirname(target)):
            os.makedirs(os.path.dirname(target))
        io.open(target, 'wb').write(data)
        entry = {'path_in_the_measured_round': rel, 'bytes': len(data), 'sha256': DC.sha_bytes(data),
                 'identity_source': 'git blob at %s' % BASE, 'copied_byte_for_byte': True,
                 'new_name_in_this_round': 'results/evidence/%s/%s' % (evidence_name, inside)}
        reused.append(entry)
    io.open(os.path.join(directory, 'reuse_declaration.json'), 'wb').write(
        (json.dumps({'task_id': TASK_ID, 'written_utc': now(), 'base': BASE,
                     'rule': 'these are the bytes the measured round published, taken out of Git at '
                             '%s and written again unchanged. Reusing them is not a new simulation: '
                             'this round starts no process and its own task book authorises none. The '
                             'judgement recomputed over them is the new offline work of this round.'
                             % BASE[:12],
                     'files': reused}, indent=1, sort_keys=True, ensure_ascii=False)
         + chr(10)).encode('utf-8'))
    rc, body = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_matrix.py'), 'judge', directory])
    if rc != 0:
        raise SystemExit('DC_R1_REFUSED the repaired judge did not pass over the reused table (rc=%s): '
                         '%s' % (rc, body.strip().splitlines()[-1:]))
    resolution = _identity_resolution(os.path.join(ROOT, MEASURED.replace('/', os.sep)))
    rows_write(os.path.join(directory, 'extraction_identity_resolution.csv'),
               ('case_id', 'role', 'legacy_run_id', 'legacy_launch_id', 'resolved_run_id',
                'resolved_launch_id', 'deck_sha256', 'raw_sha256'), resolution['rows'])
    earlier = os.path.join(ROOT, MEASURED.replace('/', os.sep))
    stale = []
    for row in _read_table(os.path.join(earlier, 'source_identity.csv')):
        data = git_bytes('cat-file', 'blob', '%s:%s' % (BASE, row['path']))
        crlf = data.replace(b'\n', b'\r\n')
        if DC.sha_bytes(data) != row['sha256']:
            stale.append({'path': row['path'], 'recorded_bytes': int(row['bytes']),
                          'recorded_sha256': row['sha256'], 'git_blob_bytes': len(data),
                          'git_blob_sha256': DC.sha_bytes(data),
                          'recorded_value_is_the_CRLF_form_of_the_blob':
                              DC.sha_bytes(crlf) == row['sha256'] and len(crlf) == int(row['bytes']),
                          'replacement': 'referenced where it is and re-declared by this record from the '
                                         'blob at %s: %s' % (BASE, row['path'])})
    io.open(os.path.join(directory, 'stale_fields_of_the_earlier_record.json'), 'wb').write(
        (json.dumps({'task_id': TASK_ID, 'written_utc': now(),
                     'earlier_record': MEASURED,
                     'rule': 'the earlier record stays published exactly as it is. These are the fields '
                             'it cannot reproduce from Git: it hashed the working copy, which carried '
                             'CRLF, while the repository carries LF. Nothing about the figures content '
                             'or the measurements is in question, and this round does not redraw them: '
                             'the replacement rows are the committed bytes named here.',
                     'rows': stale,
                     'what_this_record_replaces': 'the source identity of the two figures and the '
                                                  'unit of the worst residual in the dc_judgement gate',
                     'what_stays_as_published': 'the 152 native rows, the eight preflight witnesses, the '
                                                'sixteen-row account and the electrical verdict'},
                    indent=1, sort_keys=True, ensure_ascii=False) + chr(10)).encode('utf-8'))
    if answers_dir and os.path.isdir(answers_dir):
        scratch = tempfile.mkdtemp(prefix='dc-r1-observe-')
        provenance = []
        for case_id in DC.dc_contract()['matrix']['launch_order']:
            source = os.path.join(answers_dir, 'r20261026_015212_376554_%s_dut.raw' % case_id)
            if os.path.isfile(source):
                data = io.open(source, 'rb').read()
                io.open(os.path.join(scratch, os.path.basename(source)), 'wb').write(data)
                provenance.append({'file': os.path.basename(source), 'bytes': len(data),
                                   'sha256': DC.sha_bytes(data),
                                   'read_from': 'the executor-saved native answer, not shipped'})
        rc_observe, observe_body = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_dc_matrix.py'),
                                        'observe', scratch])
        observed = json.loads(io.open(os.path.join(scratch, 'observed_signals.json'),
                                      encoding='utf-8').read())
        io.open(os.path.join(directory, 'observed_signals.json'), 'wb').write(
            (json.dumps(observed, indent=1, sort_keys=True, ensure_ascii=False) + chr(10)).encode('utf-8'))
        io.open(os.path.join(directory, 'observation_provenance.json'), 'wb').write(
            (json.dumps({'task_id': TASK_ID, 'written_utc': now(), 'rc': rc_observe,
                         'command': 'python scripts/dd1_d7c_b_dc_matrix.py observe <copy of the saved '
                                    'native answers>',
                         'last_line': observe_body.strip().splitlines()[-1:],
                         'answers': provenance,
                         'rule': 'the observation was read from the native answers this machine still '
                                 'holds. The answers are not in the repository, so their digests are '
                                 'listed here instead; nothing was re-simulated.'},
                        indent=1, sort_keys=True, ensure_ascii=False) + chr(10)).encode('utf-8'))
        shutil.rmtree(scratch, ignore_errors=True)
    print('DC_R1_EXPORT %s (%d reused files, %d native sources resolved, %d stale rows named, '
          'observation rc=%s) -> %s' % (evidence_name, len(reused), len(resolution['rows']),
                                        len(stale), rc_observe if answers_dir else 'NOT_RUN',
                                        directory))
    return evidence_name


def verify_committed(rev, evidence_name):
    """after the commit: every published identity row must equal the blob the commit carries"""
    problems, rows = [], _read_table(os.path.join(ROOT, 'results', 'evidence', evidence_name,
                                                  'source_identity.csv'))
    for row in rows:
        try:
            data = git_bytes('cat-file', 'blob', '%s:%s' % (rev, row['path']))
        except subprocess.CalledProcessError:
            problems.append('%s is not in %s' % (row['path'], rev[:12]))
            continue
        if len(data) != int(row['bytes']) or DC.sha_bytes(data) != row['sha256']:
            problems.append('%s: published %s bytes %s, the commit carries %d bytes %s'
                            % (row['path'], row['bytes'], row['sha256'][:12], len(data),
                               DC.sha_bytes(data)[:12]))
    print('DC_IDENTITY_VERIFIED_COMMITTED %s (%d rows against git cat-file blob %s:<path>, problems: %s)'
          % ('PASS' if not problems else 'FAIL', len(rows), rev[:12],
             '; '.join(problems[:3]) or 'none'))
    return 0 if not problems else 1


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', default='')
    parser.add_argument('--draft', default='')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--republish', action='store_true')
    parser.add_argument('--answers', default='', help='directory holding the saved native .raw answers')
    parser.add_argument('--export', action='store_true', help='build this round evidence directory')
    parser.add_argument('--new-name', default='')
    parser.add_argument('--verify-committed', default='', help='rev to compare the published identity '
                                                              'against')
    arguments = parser.parse_args(argv)
    answers_dir = os.path.abspath(arguments.answers) if arguments.answers else ''
    if arguments.verify_committed:
        return verify_committed(arguments.verify_committed,
                                os.path.basename(arguments.evidence.rstrip('/\\')))
    directory = os.path.join(ROOT, 'results', 'evidence')
    if arguments.export:
        export_r1(answers_dir, arguments.new_name)
        return 0
    candidates = sorted(name for name in os.listdir(directory) if name.startswith(EVIDENCE_PREFIX))
    if not candidates:
        raise SystemExit('DC_RECORD_REFUSED no evidence directory of this round exists yet; run '
                         '--answers <saved native answers> --export first')
    evidence_name = (os.path.basename(arguments.evidence.rstrip('/\\')) if arguments.evidence
                     else candidates[-1])
    evidence = os.path.join(directory, evidence_name)
    if not os.path.isdir(evidence):
        raise SystemExit('DC_RECORD_REFUSED %s is not a directory' % evidence_name)
    head = git('rev-parse', 'HEAD').strip()
    if not arguments.draft and not arguments.check_only:
        stage(round_paths(evidence_name))
    payload = json.loads(io.open(os.path.join(evidence, 'judgement.json'), encoding='utf-8').read())
    results, reconcile, account = build_gates(evidence, answers_dir, evidence_name)
    payload['reconcile'] = reconcile
    frozen, _problems = frozen_rows(head)
    results.append(frozen_gate(frozen))
    failures = [row['gate'] for row in results if row['verdict_state'] != 'PASS']
    ranges = {'BASE_to_HEAD_this_round': range_counts(BASE, head),
              'e51c532_to_BASE_measured_round': range_counts(OFFLINE_BASE, BASE),
              'P_to_R1_recomputed': range_counts('dcef9b336f2222d6291d266858270f7448b6bb78',
                                                 '6778535e70b139812265eba490d0a1381a1fae5c'),
              'R1_to_base': range_counts('6778535e70b139812265eba490d0a1381a1fae5c', OFFLINE_BASE)}
    git_rows = []
    for label, command, expected in (
            ('diff_check_staged_this_round', ['git', 'diff', '--check', '--cached'], 0),
            ('diff_check_BASE_to_HEAD', ['git', 'diff', '--check', '%s..HEAD' % BASE], 0),
            ('diff_check_earlier_range_disclosed_negative',
             ['git', 'diff', '--check', '%s..%s' % (OFFLINE_BASE, BASE)], 2),
            ('diff_check_P_to_HEAD', ['git', 'diff', '--check',
                                      'dcef9b336f2222d6291d266858270f7448b6bb78..HEAD'], 2)):
        rc, body = run(command)
        git_rows.append({'gate': label, 'command': ' '.join(command), 'rc': rc,
                         'lines': len([line for line in body.split('\n') if line.strip()]),
                         'scope': 'expected rc %d, got %s; the earlier range stays negative on purpose '
                                  'because archived review logs, the two figures of the measured round '
                                  'and its commands.csv were saved as they are, and none of those bytes '
                                  'is rewritten to make a check read clean. HEAD here is %s at %s'
                                  % (expected, rc, head[:12], now())})
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
    identity = None
    for name, header, table in (('commands.csv', COMMANDS_HEADER, results),
                                ('frozen_comparison.csv', FROZEN_HEADER, frozen),
                                ('git_checks.csv', GIT_HEADER, git_rows),
                                ('launches_reconcile.csv', RECONCILE_HEADER, reconcile)):
        rows_write(os.path.join(out_dir, name), header, table)
    if not arguments.draft:
        stage(round_paths(evidence_name))
        identity = identity_rows(evidence_name)
        rows_write(os.path.join(out_dir, 'source_identity.csv'), IDENTITY_HEADER, identity)
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
    summary = {'task_id': TASK_ID, 'base_sha_of_this_round': BASE, 'branch': BRANCH, 'tip': head,
               'evidence_directory': evidence_name, 'generated_utc': now(),
               'gates': len(results), 'gates_failed': failures,
               'gates_informational': [row['gate'] for row in results
                                       if row['verdict_state'] not in ('PASS', 'FAIL')],
               'report_render_fixed_point': fixed_point,
               'published_tables_recheck': {'verdict': recheck['verdict_state'], 'rc': recheck['rc'],
                                              'detail': recheck['verdict']},
               'csv_read_back': read_back,
               'published_json': json_probe, 'identity_rows': len(identity or []),
               'identity_source_rule': 'every published identity row is the digest of the blob this '
                                       'commit carries, read from the index; a working copy is never '
                                       'the identity, because Git may normalise its line endings',
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
               'registered_offline_content': OFFLINE_BASE, 'base_of_this_round': BASE,
               'spectre_launches': 0, 'reused_native_account_rows': account.occupied(),
               'rtl_simulations': 0, 'oa_writes': 0,
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
