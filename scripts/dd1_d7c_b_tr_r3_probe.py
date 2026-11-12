#!/usr/bin/env python3
"""DATA-7C-B-TR-R3 counterexamples for the residual semantic gaps.

Usage: python -B dd1_d7c_b_tr_r3_probe.py SOURCE_ROOT NEW_OUTPUT_DIR

Every mutation is applied to a disposable copy of the delivered evidence, never to the audited
tree and never to a frozen table. Each corrupted input must be refused by name; the clean
controls in the same process must stay green, so a refusal can never come from a broken fixture.
"""
import base64
import csv
import gzip
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys

R1 = 'results/evidence/dd1_d7c_b_tr_r1_r20261027_143223_4c8a81'
R2 = 'results/evidence/dd1_d7c_b_tr_r2_20261112_144123_c4e480'
OLD = 'results/evidence/dd1_d7c_b_tr_r20261026_132228_3fc148'
R3 = 'results/evidence/dd1_d7c_b_tr_r3_20261112_175259_3c2950'
FOLDERS = ('scripts', 'tests/dd1_d7c_b_tr', 'tests/dd1_d7c_b_prep', 'tests/dd1_d7c_b_dc',
           'spectre/dd1_d7c_b_tr', R1, R2, OLD, R3,
           'results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def build(source, root, out):
    for folder in FOLDERS:
        src = os.path.join(source, folder.replace('/', os.sep))
        if not os.path.isdir(src):
            raise SystemExit('missing fixture folder %s' % folder)
        shutil.copytree(src, os.path.join(root, folder.replace('/', os.sep)))
    # the two byte-bound real VCDs are not tracked; they are copied from this checkout
    for tag in ('120', '200'):
        name = 'dd1_d7c_b_tr_hyb_%s.vcd.gz' % tag
        candidates = [os.path.join(source, R3.replace('/', os.sep), 'rtl', name),
                      os.path.join(source, R2.replace('/', os.sep), 'rtl', name)]
        src = next((path for path in candidates if os.path.isfile(path)), None)
        if src is None:
            raise SystemExit('missing VCD %s in the source checkout' % name)
        dst = os.path.join(root, R3.replace('/', os.sep), 'rtl', name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def runner(root, out, block=None):
    guard = ''
    env = dict((k, v) for k, v in os.environ.items() if not k.startswith('GIT_'))
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if block:
        wrapper = os.path.join(out, 'block_subprocess.py')
        with open(wrapper, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write('import sys, runpy\n'
                         'def block(event, args):\n'
                         '    if event in ("subprocess.Popen", "os.system", "os.posix_spawn"):\n'
                         '        raise RuntimeError("SUBPROCESS_FORBIDDEN")\n'
                         'sys.addaudithook(block)\n'
                         'sys.argv = sys.argv[1:]\n'
                         'runpy.run_path(sys.argv[0], run_name="__main__")\n')
        guard = [sys.executable, '-B', wrapper]
    results = {}

    def run(kind, tag):
        script = os.path.join(root, 'scripts',
                              'dd1_d7c_b_tr_r1_native.py' if kind == 'verify'
                              else 'dd1_d7c_b_tr_r1_recompute.py')
        if kind == 'verify':
            tail = [script, '--verify', os.path.join(root, R1.replace('/', os.sep))]
        else:
            tail = [script, root, '--inputs',
                    os.path.join(root, R3.replace('/', os.sep), 'r3_inputs.json')]
        args = (guard + tail) if guard else ([sys.executable, '-B'] + tail)
        proc = subprocess.run(args, cwd=root, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        text = proc.stdout
        with open(os.path.join(out, tag + '.txt'), 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        said = [line for line in text.splitlines()
                if line.startswith(('TR_R1_VERIFY_FAIL', 'TR_R1_VERIFY ', 'RECOMPUTE_R1_FAIL',
                                    'RECOMPUTE_R1_REFUSED', 'RECOMPUTE_R1 gate'))]
        results[tag] = {'rc': proc.returncode, 'summary': said[:2],
                        'named': [line for line in said
                                  if 'FAIL' in line or 'REFUSED' in line][:2]}
        return results[tag]

    return run, results


def main():
    source = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    if os.path.exists(out):
        raise SystemExit('output directory must be brand new: %s' % out)
    os.makedirs(out)
    root = os.path.join(out, 'fixture')
    os.makedirs(root)
    build(source, root, out)
    run, results = runner(root, out)
    blocked_run, blocked_results = runner(root, out, block=True)
    cases = []
    cases.append(('clean_verify', run('verify', 'clean_verify'), True))
    cases.append(('clean_recompute', run('recompute', 'clean_recompute'), True))
    cases.append(('verify_no_subprocess', blocked_run('verify', 'verify_no_subprocess'), True))
    results['verify_no_subprocess'] = blocked_results['verify_no_subprocess']
    for name, result, must_pass in cases:
        if (result['rc'] == 0) != must_pass:
            raise SystemExit('control %s returned rc=%d' % (name, result['rc']))

    seq = os.path.join(root, R1.replace('/', os.sep),
                       'native_sequences/r20261026_132228_3fc148_TR-120_preflight.sequence.txt')
    man = os.path.join(root, R1.replace('/', os.sep), 'native_manifest.json')
    seq_bytes, man_bytes = open(seq, 'rb').read(), open(man, 'rb').read()
    plain = gzip.decompress(base64.b85decode(seq_bytes.split(b'\n\n', 1)[1].strip())).decode()

    def container_case(tag, transform):
        text = transform(plain)
        if text == plain:
            raise SystemExit('mutation %s changed nothing' % tag)
        raw = text.encode()
        comp = gzip.compress(raw, compresslevel=9, mtime=0)
        blob = b'TR1CONTAINER 1\n\n' + base64.b85encode(comp)
        manifest = json.loads(man_bytes)
        for entry in manifest['files']:
            if entry.get('file') == os.path.basename(seq):
                entry.update(bytes=len(blob), sha256=sha(blob), gzip_bytes=len(comp),
                             gzip_sha256=sha(comp), plain_bytes=len(raw))
        with open(seq, 'wb') as handle:
            handle.write(blob)
        with open(man, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(manifest, indent=1) + '\n')
        try:
            result = run('verify', tag)
        finally:
            open(seq, 'wb').write(seq_bytes)
            open(man, 'wb').write(man_bytes)
        if result['rc'] == 0:
            raise SystemExit('%s was accepted by verify: the gap is open' % tag)
        return result

    cases.append(('A1_current_unit_V', container_case(
        'A1_current_unit_V',
        lambda text: text.replace('column Ip_branch:i unit A ',
                                  'column Ip_branch:i unit V ', 1)), False))
    cases.append(('A2_vdd18_nan', container_case(
        'A2_vdd18_nan',
        lambda text: re.sub(r'(column vdd18 unit V encoding CONSTANT count \d+\n)[^\n]+',
                            r'\g<1>nan', text, count=1)), False))
    cases.append(('A3_sample_count_short', container_case(
        'A3_sample_count_short',
        lambda text: text.replace('samples 780', 'samples 779', 1)), False))
    cases.append(('A4_time_not_ordered', container_case(
        'A4_time_not_ordered',
        lambda text: text.replace('1 1.530000000000000e-09\n1 3.530000000000000e-09',
                                  '1 3.530000000000000e-09\n1 1.530000000000000e-09', 1)), False))

    def table_case(tag, relative, mutate, kind='recompute'):
        path = os.path.join(root, relative.replace('/', os.sep))
        original = open(path, 'rb').read()
        with open(path, newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        mutate(rows)
        with open(path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        try:
            result = run(kind, tag)
        finally:
            open(path, 'wb').write(original)
        if result['rc'] == 0:
            raise SystemExit('%s was accepted: the gap is open' % tag)
        return result

    def flip_ledger(rows):
        row = next(item for item in rows
                   if item['case_id'] == 'TR-120' and item['role'] == 'preflight')
        if row['state'] != 'CONFIRMED':
            raise SystemExit('the clean ledger no longer holds T004 as CONFIRMED')
        row['state'] = 'UNCERTAIN'
        row['rc'] = ''

    cases.append(('B1_ledger_uncertain',
                  table_case('B1_ledger_uncertain', OLD + '/spectre_launch_account.csv',
                             flip_ledger), False))

    budget = os.path.join(root, OLD.replace('/', os.sep), 'spectre_budget_adjustments.json')
    budget_bytes = open(budget, 'rb').read()
    document = json.loads(budget_bytes)
    first = document['adjustments'][0]
    extra = dict(first['launches'][0])
    extra['launch_id'] = 'T900'
    first['launches'] = list(first['launches']) + [extra]
    first['processes'] = len(first['launches'])
    with open(budget, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(document, indent=1) + '\n')
    try:
        results['B2_budget_occupied_22'] = run('recompute', 'B2_budget_occupied_22')
    finally:
        open(budget, 'wb').write(budget_bytes)
    if results['B2_budget_occupied_22']['rc'] == 0:
        raise SystemExit('B2_budget_occupied_22 was accepted: the gap is open')
    cases.append(('B2_budget_occupied_22', results['B2_budget_occupied_22'], False))

    def push_limit(rows):
        target = next(item for item in rows
                      if item['case_id'] == 'TR-120' and item['kind'] == 'emission')
        target['settling_dc_left_limit_A'] = '1000'

    cases.append(('B3_settling_left_limit_1000A',
                  table_case('B3_settling_left_limit_1000A', R3 + '/windows_all.csv',
                             push_limit), False))

    def clear_context(rows):
        rows[0]['context_match'] = 'NO'

    cases.append(('C1_convergence_context_NO',
                  table_case('C1_convergence_context_NO', R3 + '/convergence.csv',
                             clear_context), False))

    # the bookkeeping mocks import the audited modules directly: they are Git-bound by design and
    # the fixture is deliberately Git-less, so running them there would test the wrong thing
    sys.path.insert(0, os.path.join(source, 'scripts'))
    RUN = importlib.import_module('dd1_d7c_b_tr_run')
    REC = importlib.import_module('dd1_d7c_b_tr_record')
    mock_dir = os.path.join(out, 'mock')
    os.makedirs(mock_dir)
    rows = [{'sim_id': 'R001', 'case_id': 'HYB-120', 'requested_utc': '2026-01-01T00:00:00Z',
             'state': 'UNCERTAIN', 'refusal': 'UNIQUE_START_TRANSCRIPT:invented_label'},
            {'sim_id': 'R002', 'case_id': 'HYB-120', 'requested_utc': '2026-01-01T00:00:00Z',
             'state': 'CONFIRMED', 'exe_sha256': 'a' * 64, 'rc': '0', 'log_sha256': 'b' * 64,
             'refusal': 'UNIQUE_START_TRANSCRIPT:invented_label'}]
    link = os.path.join(mock_dir, 'reconcile.json')
    with open(link, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump({'duplicate_bookings': [{'sim_id': 'R001', 'evidence': {
            'witness_row': 'R002', 'unique_start_transcript': 'b' * 64}}]}, handle)
    account = object.__new__(RUN.Account)
    account.rows = rows
    account.header = ('sim_id',)
    account.reconcile = link
    account.ceiling = 4
    label_only = {'files': sorted(os.listdir(mock_dir)),
                  'transcript_file_supplied': False,
                  'account_duplicates': account.duplicate_bookings(),
                  'account_processes': account.processes(),
                  'record_derived_duplicates': REC.derive_duplicates(rows)}
    if label_only['account_duplicates'] or label_only['account_processes'] != 2:
        raise SystemExit('an unverified label still released a charge')
    if label_only['record_derived_duplicates']:
        raise SystemExit('the record path still derived a duplicate from a label')
    cases.append(('D1_label_without_transcript', {'rc': 1, 'named': ['refused: no transcript'],
                                                  'summary': ['label freed nothing']}, False))

    body = b'HYB-120: R001 reserved; R002 started; nothing else refused\n'
    transcript = os.path.join(mock_dir, 'start.txt')
    open(transcript, 'wb').write(body)
    digest = sha(body)
    rows[1]['log_sha256'] = digest
    with open(link, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump({'duplicate_bookings': [{'sim_id': 'R001', 'evidence': {
            'witness_row': 'R002', 'unique_start_transcript': digest,
            'transcript': 'start.txt'}}]}, handle)
    proven = object.__new__(RUN.Account)
    proven.rows = rows
    proven.header = ('sim_id',)
    proven.reconcile = link
    proven.ceiling = 4
    capability = {'account_duplicates': proven.duplicate_bookings(),
                  'account_processes': proven.processes()}
    if capability['account_duplicates'] != ['R001'] or capability['account_processes'] != 1:
        raise SystemExit('a verified transcript no longer releases exactly one charge')

    report = {'tip_fixture': 'copy of the audited checkout, mutations only in the copy',
              'controls': unit_controls(results),
              'counterexamples': [{'case': name, 'rc': result['rc'],
                                   'named': result['named']} for name, result, _p in cases
                                  if not _p],
              'mock_label_without_transcript': label_only,
              'mock_verified_transcript': capability}
    with open(os.path.join(out, 'counterexamples.json'), 'w', encoding='utf-8',
              newline='\n') as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'controls': report['controls'],
                      'counterexamples': len(report['counterexamples']),
                      'all_refused': all(item['rc'] != 0 for item in report['counterexamples']),
                      'label_without_transcript_refused': True,
                      'verified_transcript_capability': capability}, ensure_ascii=False, indent=1))


def unit_controls(results):
    return dict((name, results[name]['rc']) for name in
                ('clean_verify', 'clean_recompute', 'verify_no_subprocess'))


if __name__ == '__main__':
    main()
