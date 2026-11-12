#!/usr/bin/env python3
"""DATA-7C-B-TR-R3 counterexamples for the residual semantic gaps.

Usage: python -B dd1_d7c_b_tr_r3_probe.py SOURCE_ROOT NEW_OUTPUT_DIR

Every mutation is applied to a disposable copy of the delivered evidence, never to the audited
tree and never to a frozen table. Each corrupted input must be refused by name; the clean
controls in the same run must stay green, so a refusal can never come from a broken fixture.
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
CONTROLS = ('clean_verify', 'clean_recompute', 'verify_no_subprocess')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def build(source, root):
    for folder in FOLDERS:
        src = os.path.join(source, folder.replace('/', os.sep))
        if not os.path.isdir(src):
            raise SystemExit('missing fixture folder %s' % folder)
        shutil.copytree(src, os.path.join(root, folder.replace('/', os.sep)))
    # the two byte-bound real VCDs are not tracked; they travel with the checkout and the package
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


def make_runner(root, out, block=False):
    env = dict((k, v) for k, v in os.environ.items() if not k.startswith('GIT_'))
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    prefix = [sys.executable, '-B']
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
        prefix = [sys.executable, '-B', wrapper]
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
        proc = subprocess.run(prefix + tail, cwd=root, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
        text = proc.stdout
        with open(os.path.join(out, tag + '.txt'), 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        said = [line for line in text.splitlines()
                if line.startswith(('TR_R1_VERIFY ', 'TR_R1_VERIFY_PROBLEM', 'RECOMPUTE_R1 gate',
                                    'RECOMPUTE_R1_FAIL', 'RECOMPUTE_R1_REFUSED'))]
        results[tag] = {'rc': proc.returncode,
                        'summary': said[:1],
                        'named': [line for line in said if 'PROBLEM' in line or 'REFUSED' in line][:2]}
        return results[tag]

    return run, results


def container_mutation(root, run, seq, man, seq_bytes, man_bytes, plain, tag, transform):
    """rewrite one delivered container and its manifest digests, then judge the result"""
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


def table_mutation(root, run, relative, tag, mutate):
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
        result = run('recompute', tag)
    finally:
        open(path, 'wb').write(original)
    if result['rc'] == 0:
        raise SystemExit('%s was accepted: the gap is open' % tag)
    return result


def bookkeeping_mock(RUN, REC, out):
    """B4: what a transcript must say before one charge is released"""
    mock_dir = os.path.join(out, 'mock')
    os.makedirs(mock_dir)
    rows = [{'sim_id': 'R001', 'case_id': 'HYB-120', 'requested_utc': '2026-01-01T00:00:00Z',
             'state': 'UNCERTAIN', 'refusal': 'UNIQUE_START_TRANSCRIPT:invented_label'},
            {'sim_id': 'R002', 'case_id': 'HYB-120', 'requested_utc': '2026-01-01T00:00:00Z',
             'state': 'CONFIRMED', 'exe_sha256': 'a' * 64, 'rc': '0', 'log_sha256': 'b' * 64,
             'refusal': 'UNIQUE_START_TRANSCRIPT:invented_label'}]
    link = os.path.join(mock_dir, 'reconcile.json')

    def account(rows_now):
        holder = object.__new__(RUN.Account)
        holder.rows = rows_now
        holder.header = ('sim_id',)
        holder.reconcile = link
        holder.ceiling = 4
        return holder

    def write(transcript_text, digest):
        path = os.path.join(mock_dir, 'start.txt')
        with open(path, 'wb') as handle:
            handle.write(transcript_text)
        rows[1]['log_sha256'] = digest
        with open(link, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump({'duplicate_bookings': [{'sim_id': 'R001', 'evidence': {
                'witness_row': 'R002', 'unique_start_transcript': digest,
                'transcript': 'start.txt'}}]}, handle)

    with open(link, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump({'duplicate_bookings': [{'sim_id': 'R001', 'evidence': {
            'witness_row': 'R002', 'unique_start_transcript': 'b' * 64}}]}, handle)
    label_only = {'transcript_file_supplied': False,
                  'account_duplicates': account(rows).duplicate_bookings(),
                  'account_processes': account(rows).processes(),
                  'record_derived_duplicates': REC.derive_duplicates(rows)}
    if label_only['account_duplicates'] or label_only['account_processes'] != 2:
        raise SystemExit('an unverified label still released a charge')
    if label_only['record_derived_duplicates']:
        raise SystemExit('the record path still derived a duplicate from a label')

    contradictory = (b'HYB-120: R001 started pid=101; R002 started pid=102; '
                     b'two distinct executions completed.\n')
    write(contradictory, sha(contradictory))
    two_starts = {'transcript': contradictory.decode().strip(),
                  'account_duplicates': account(rows).duplicate_bookings(),
                  'account_processes': account(rows).processes()}
    if two_starts['account_duplicates'] or two_starts['account_processes'] != 2:
        raise SystemExit('a transcript recording two starts still released a charge')

    proven_text = (b'HYB-120: R001 stayed in the reserved queue\n'
                   b'NOT_STARTED R001\n'
                   b'STARTED R002 pid=4242 rc=0\n')
    write(proven_text, sha(proven_text))
    capability = {'account_duplicates': account(rows).duplicate_bookings(),
                  'account_processes': account(rows).processes()}
    if capability['account_duplicates'] != ['R001'] or capability['account_processes'] != 1:
        raise SystemExit('a transcript declaring NOT_STARTED no longer releases one charge')
    return {'label_only': label_only, 'two_starts': two_starts, 'not_started': capability}


def main():
    source = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2])
    if os.path.exists(out):
        raise SystemExit('output directory must be brand new: %s' % out)
    os.makedirs(out)
    root = os.path.join(out, 'fixture')
    os.makedirs(root)
    build(source, root)
    run, results = make_runner(root, out)
    blocked, blocked_results = make_runner(root, out, block=True)
    run('verify', 'clean_verify')
    run('recompute', 'clean_recompute')
    blocked('verify', 'verify_no_subprocess')
    results.update(blocked_results)
    for name in CONTROLS:
        if results[name]['rc'] != 0:
            raise SystemExit('control %s returned rc=%d' % (name, results[name]['rc']))

    cases = []
    seq = os.path.join(root, R1.replace('/', os.sep),
                       'native_sequences/r20261026_132228_3fc148_TR-120_preflight.sequence.txt')
    man = os.path.join(root, R1.replace('/', os.sep), 'native_manifest.json')
    seq_bytes, man_bytes = open(seq, 'rb').read(), open(man, 'rb').read()
    plain = gzip.decompress(base64.b85decode(seq_bytes.split(b'\n\n', 1)[1].strip())).decode()

    def container(tag, transform):
        cases.append((tag, container_mutation(root, run, seq, man, seq_bytes, man_bytes,
                                              plain, tag, transform)))

    container('A1_current_unit_V',
              lambda text: text.replace('column Ip_branch:i unit A ',
                                        'column Ip_branch:i unit V ', 1))
    container('A2_vdd18_nan',
              lambda text: re.sub(r'(column vdd18 unit V encoding CONSTANT count \d+\n)[^\n]+',
                                  r'\g<1>nan', text, count=1))
    container('A3_sample_count_short',
              lambda text: text.replace('samples 780', 'samples 779', 1))
    container('A4_time_not_ordered',
              lambda text: text.replace('1 1.530000000000000e-09\n1 3.530000000000000e-09',
                                        '1 3.530000000000000e-09\n1 1.530000000000000e-09', 1))

    def zero_current(text):
        return re.sub(r'(column Ip_branch:i unit A encoding CONSTANT count \d+\n)[^\n]+',
                      r'\g<1>0.000000000000000e+00', text, count=1)

    def zero_enable(text):
        line = re.search(r'column data_en unit V encoding RUNS count (\d+) runs (\d+)\n', text)
        if not line:
            return text
        count, runs = int(line.group(1)), int(line.group(2))
        end = line.end()
        for _ in range(runs):
            end = text.index('\n', end) + 1
        return (text[:line.start()]
                + 'column data_en unit V encoding RUNS count %d runs 1\n' % count
                + '%d 0.000000000000000e+00\n' % count
                + text[end:])

    container('A5_current_all_zero', zero_current)
    container('A6_enable_all_zero', zero_enable)

    ledger_path = os.path.join(root, OLD.replace('/', os.sep), 'spectre_launch_account.csv')
    ledger_bytes = open(ledger_path, 'rb').read()
    with open(ledger_path, newline='', encoding='utf-8') as handle:
        ledger_rows = list(csv.DictReader(handle))
    fields = list(ledger_rows[0])
    target = next(item for item in ledger_rows
                  if item['case_id'] == 'TR-120' and item['role'] == 'preflight')
    target['raw_sha256'] = '0' * 64
    with open(ledger_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(ledger_rows)
    try:
        results['C2_ledger_raw_zero_verify'] = run('verify', 'C2_ledger_raw_zero_verify')
        results['C2_ledger_raw_zero_recompute'] = run('recompute', 'C2_ledger_raw_zero_recompute')
    finally:
        open(ledger_path, 'wb').write(ledger_bytes)
    for tag in ('C2_ledger_raw_zero_verify', 'C2_ledger_raw_zero_recompute'):
        if results[tag]['rc'] == 0:
            raise SystemExit('%s was accepted: the identity is still unbound' % tag)
        cases.append((tag, results[tag]))

    def flip_ledger(rows):
        row = next(item for item in rows
                   if item['case_id'] == 'TR-120' and item['role'] == 'preflight')
        if row['state'] != 'CONFIRMED':
            raise SystemExit('the clean ledger no longer holds T004 as CONFIRMED')
        row['state'] = 'UNCERTAIN'
        row['rc'] = ''

    cases.append(('B1_ledger_uncertain',
                  table_mutation(root, run, OLD + '/spectre_launch_account.csv',
                                 'B1_ledger_uncertain', flip_ledger)))

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
    cases.append(('B2_budget_occupied_22', results['B2_budget_occupied_22']))

    def push_limit(rows):
        target = next(item for item in rows
                      if item['case_id'] == 'TR-120' and item['kind'] == 'emission')
        target['settling_dc_left_limit_A'] = '1000'

    cases.append(('B3_settling_left_limit_1000A',
                  table_mutation(root, run, R3 + '/windows_all.csv',
                                 'B3_settling_left_limit_1000A', push_limit)))

    def clear_context(rows):
        rows[0]['context_match'] = 'NO'

    cases.append(('C1_convergence_context_NO',
                  table_mutation(root, run, R3 + '/convergence.csv',
                                 'C1_convergence_context_NO', clear_context)))

    # the bookkeeping modules read the object store by design, so a Git-less tree cannot import
    # them; that is reported rather than hidden, and the checkout run exercises them fully
    sys.path.insert(0, os.path.join(source, 'scripts'))
    mock_reason = ''
    try:
        RUN = importlib.import_module('dd1_d7c_b_tr_run')
        REC = importlib.import_module('dd1_d7c_b_tr_record')
    except Exception as error:                                   # noqa: BLE001 - reported below
        RUN = REC = None
        mock_reason = ('the bookkeeping modules read the object store by design and are not '
                       'importable in a Git-less tree: %s: %s'
                       % (type(error).__name__, str(error)[:140]))
    if RUN is not None:
        mock = bookkeeping_mock(RUN, REC, out)
        for tag in ('D1_label_without_transcript', 'D2_transcript_two_starts'):
            cases.append((tag, {'rc': 1, 'summary': ['no charge released'],
                                'named': ['the transcript did not prove a single start']}))
    else:
        mock = {'label_only': {'status': 'NOT_APPLICABLE', 'reason': mock_reason},
                'two_starts': {'status': 'NOT_APPLICABLE'},
                'not_started': {'status': 'NOT_APPLICABLE'}}

    report = {'probe': 'R3', 'fixture': 'copy of the audited checkout; mutations only in the copy',
              'controls': dict((name, results[name]['rc']) for name in CONTROLS),
              'counterexamples': [{'case': name, 'rc': result['rc'],
                                   'named': result['named']} for name, result in cases],
              'all_refused': all(result['rc'] != 0 for _n, result in cases),
              'mock_label_without_transcript': mock['label_only'],
              'mock_transcript_two_starts': mock['two_starts'],
              'mock_transcript_not_started': mock['not_started']}
    with open(os.path.join(out, 'counterexamples.json'), 'w', encoding='utf-8',
              newline='\n') as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({'controls': report['controls'],
                      'counterexamples': len(cases),
                      'all_refused': report['all_refused'],
                      'mock_label_without_transcript': mock['label_only'],
                      'mock_transcript_two_starts': mock['two_starts'],
                      'mock_transcript_not_started': mock['not_started']}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
