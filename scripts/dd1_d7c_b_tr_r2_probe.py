#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR-R2 counterexample harness.

Stdlib only. Works on a brand-new isolated copy, never on the delivered tree. It proves the clean
inputs succeed first, then changes exactly one fact per case and records the real rc, the entry's
absolute path and the named refusal. A traceback, a missing file or a missing module is NOT counted
as a successful detection: every case names an expected semantic token.
"""
import base64
import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

GIT_OVERRIDES = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
                 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
                 'GIT_CEILING_DIRECTORIES', 'GIT_DISCOVERY_ACROSS_FILESYSTEM',
                 'GIT_NAMESPACE', 'GIT_PREFIX')

SUBDIRS = ('scripts', 'tests/dd1_d7c_b_tr', 'tests/dd1_d7c_b_prep',
           'tests/dd1_d7c_b_dc', 'spectre/dd1_d7c_b_tr')
NATIVE = 'results/evidence/dd1_d7c_b_tr_r20261026_132228_3fc148'
R1 = 'results/evidence/dd1_d7c_b_tr_r1_r20261027_143223_4c8a81'


def clean_env():
    env = dict(os.environ)
    present = {}
    for key in GIT_OVERRIDES:
        present[key] = key in env
        env.pop(key, None)
    return env, present


def read(path):
    with io.open(path, 'rb') as handle:
        return handle.read()


def write(path, data):
    with io.open(path, 'wb') as handle:
        handle.write(data)


def rows_of(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames)


def save_rows(path, rows, fields):
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def decode_container(data):
    text = data.decode('utf-8', 'replace')
    if text.startswith('TR1CONTAINER 1'):
        return gzip.decompress(base64.b85decode(text.split('\n\n', 1)[1].strip()))
    return gzip.decompress(data)


def encode_container(raw):
    return ('TR1CONTAINER 1\n\n' + base64.b85encode(gzip.compress(raw, 9, mtime=0)).decode()).encode()


def corrupt(path):
    data = read(path)
    write(path, b'X' + data[1:])


def main(argv):
    source = os.path.abspath(argv[0])
    out_dir = os.path.abspath(argv[1])
    assert not os.path.exists(out_dir), 'output directory must not already exist'
    os.makedirs(out_dir)
    root = os.path.join(tempfile.mkdtemp(prefix='r2_probe_'), 'copy')
    os.makedirs(root)
    r2_name = sorted(name for name in os.listdir(os.path.join(source, 'results', 'evidence'))
                     if name.startswith('dd1_d7c_b_tr_r2_'))[-1]
    r2_rel = 'results/evidence/' + r2_name
    for rel in SUBDIRS + (NATIVE, R1, r2_rel):
        src = os.path.join(source, rel)
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(src, dst)
    env, cleared = clean_env()
    verifier = os.path.join(root, 'scripts', 'dd1_d7c_b_tr_r1_native.py')
    recompute = os.path.join(root, 'scripts', 'dd1_d7c_b_tr_r1_recompute.py')
    descriptor = os.path.join(root, r2_rel, 'r2_inputs.json')
    r1dir = os.path.join(root, R1)
    seq = os.path.join(r1dir, 'native_sequences')
    tables = os.path.join(root, r2_rel)

    def invoke(kind):
        if kind == 'verify':
            args = [sys.executable, '-B', verifier, '--verify', r1dir]
        else:
            args = [sys.executable, '-B', recompute, root, '--inputs', descriptor]
        proc = subprocess.run(args, cwd=root, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        text = (proc.stdout + proc.stderr).decode('utf-8', 'replace')
        return {'entry_abs': args[2], 'cwd': root, 'rc': proc.returncode,
                'stdout': proc.stdout.decode('utf-8', 'replace'),
                'stderr': proc.stderr.decode('utf-8', 'replace'),
                'summary': [line for line in text.splitlines()
                            if line.startswith(('TR_R1_VERIFY', 'RECOMPUTE_R1',
                                                'RECOMPUTE_R1_REFUSED'))
                            ][:8]}

    manifest_path = os.path.join(r1dir, 'native_manifest.json')
    original_manifest = read(manifest_path)
    results = {'isolated_copy': root, 'git_env_overrides_cleared': cleared,
               'git_env_values_printed': False, 'cases': []}

    def snapshot(*paths):
        return {path: read(path) for path in paths}

    def restore(snap):
        for path, data in snap.items():
            write(path, data)

    def add_case(name, blocker, kind, expectation, mutate, extra_paths=()):
        targets = [manifest_path, os.path.join(tables, 'statuses.csv'),
                   os.path.join(tables, 'convergence.csv')] + list(extra_paths)
        snap = snapshot(*[p for p in targets if os.path.isfile(p)])
        created = []
        try:
            mutate(snap, created)
            got = invoke(kind)
            hit = expectation.lower() in (got['stdout'] + got['stderr']).lower()
            results['cases'].append({'case': name, 'blocker': blocker, 'entry': kind,
                                     'expected_named_token': expectation,
                                     'named_rejection': hit,
                                     'passed': got['rc'] != 0 and hit,
                                     **got})
        finally:
            restore(snap)
            for path in created:
                if os.path.isfile(path):
                    os.remove(path)

    # clean controls: both entries must succeed before any mutation
    for kind in ('verify', 'recompute'):
        got = invoke(kind)
        results['cases'].append({'case': 'clean_' + kind, 'blocker': 'control',
                                 'entry': kind, 'expected_named_token': 'rc=0',
                                 'named_rejection': got['rc'] == 0,
                                 'passed': got['rc'] == 0, **got})

    def whole_file(name):
        path = os.path.join(seq, name)
        return path if os.path.isfile(path) else None

    tr120 = next(n for n in os.listdir(seq)
                 if 'TR-120_dut' in n and '.part' not in n and 'internal' not in n)
    pre = next(n for n in os.listdir(seq)
               if 'TR-120_preflight' in n and '.part' not in n)
    frag = next(n for n in os.listdir(seq)
                if 'RS-SWITCH_dut.internal_fragment' in n and n.endswith('part000.txt'))
    hyb = next(n for n in os.listdir(seq)
               if 'HYB-120_dut' in n and n.endswith('part000.txt'))

    def corrupt_one(filename, token):
        def mutate(snap, created):
            corrupt(os.path.join(seq, filename))
        add_case(*token, mutate=mutate, extra_paths=[os.path.join(seq, filename)])

    corrupt_one(tr120, ('B1_whole_TR120_dut_corrupt', 'B1', 'verify',
                        'does not match the bytes and digest'))
    corrupt_one(pre, ('B1_whole_TR120_preflight_corrupt', 'B1', 'verify',
                      'does not match the bytes and digest'))
    corrupt_one(frag, ('B1_internal_fragment_part000_corrupt', 'B1', 'verify',
                       'does not match the bytes and digest'))
    corrupt_one(hyb, ('B1_hyb120_part000_control', 'B1', 'verify',
                      'does not match the bytes and digest'))

    def missing_part(snap, created):
        os.remove(os.path.join(seq, hyb))
    add_case('B1_missing_declared_part', 'B1', 'verify',
             'declared by the manifest and not on disk', missing_part,
             extra_paths=[os.path.join(seq, hyb)])

    def extra_file(snap, created):
        path = os.path.join(seq, 'undeclared_extra.txt')
        write(path, b'undeclared\n')
        created.append(path)
    add_case('B1_undeclared_delivered_content', 'B1', 'verify',
             'undeclared delivered content', extra_file)

    def preflight_unit(snap, created):
        path = os.path.join(seq, pre)
        raw = decode_container(read(path)).decode('utf-8', 'replace')
        lines = raw.splitlines()
        lines = [('# native_axis_unit=ms' if line == '# native_axis_unit=s' else line)
                 for line in lines]
        new_container = encode_container(('\n'.join(lines) + '\n').encode())
        write(path, new_container)
        manifest = json.loads(original_manifest)
        for entry in manifest['files']:
            if entry.get('file') == pre:
                entry['bytes'] = len(new_container)
                entry['sha256'] = hashlib.sha256(new_container).hexdigest()
        write(manifest_path, (json.dumps(manifest, indent=1, sort_keys=True) + '\n').encode())
    add_case('B1_preflight_unit_semantic_mutation', 'B1', 'verify',
             'frozen environment requires', preflight_unit,
             extra_paths=[os.path.join(seq, pre)])

    statuses = os.path.join(tables, 'statuses.csv')
    convergence = os.path.join(tables, 'convergence.csv')

    def budget_forged(snap, created):
        rows, fields = rows_of(statuses)
        for row in rows:
            if row['status'] == 'BUDGET_ACCOUNTING_STATUS':
                row.update(verdict='FAIL', measured='999', expected='1')
        save_rows(statuses, rows, fields)
    add_case('B2_budget_status_forged', 'B2', 'recompute', 'B2: status', budget_forged)

    def verdict_flip(snap, created):
        rows, fields = rows_of(statuses)
        for row in rows:
            if row['status'] == 'SETTLING_STATUS':
                row['verdict'] = 'FAIL'
        save_rows(statuses, rows, fields)
    add_case('B2_pass_verdict_flipped', 'B2', 'recompute', 'B2: status', verdict_flip)

    def measured_mutation(snap, created):
        rows, fields = rows_of(statuses)
        for row in rows:
            if row['status'] == 'DYNAMIC_CHARGE_STATUS':
                row['measured'] = '34'
        save_rows(statuses, rows, fields)
    add_case('B2_measured_mutated', 'B2', 'recompute', 'B2: status', measured_mutation)

    def extra_status(snap, created):
        rows, fields = rows_of(statuses)
        rows.append(dict(rows[0], status='EXTRA_STATUS'))
        save_rows(statuses, rows, fields)
    add_case('B2_extra_status_name', 'B2', 'recompute', 'B2: status set differs', extra_status)

    def delete_status(snap, created):
        rows, fields = rows_of(statuses)
        save_rows(statuses, [r for r in rows if r['status'] != 'SHUTOFF_STATUS'], fields)
    add_case('B2_deleted_status_name', 'B2', 'recompute', 'B2: status set differs', delete_status)

    def duplicate_status(snap, created):
        rows, fields = rows_of(statuses)
        rows.append(dict(rows[0]))
        save_rows(statuses, rows, fields)
    add_case('B2_duplicated_status_name', 'B2', 'recompute', 'B2: the status table repeats',
             duplicate_status)

    def duplicate_13(snap, created):
        rows, fields = rows_of(convergence)
        save_rows(convergence, [dict(rows[0]) for _ in range(13)], fields)
    add_case('B3_first_row_copied_13_times', 'B3', 'recompute', 'B3:', duplicate_13)

    def wrong_code(snap, created):
        rows, fields = rows_of(convergence)
        rows[0]['code'] = '001'
        save_rows(convergence, rows, fields)
    add_case('B3_wrong_window_code', 'B3', 'recompute', 'B3:', wrong_code)

    def signed_dq(snap, created):
        rows, fields = rows_of(convergence)
        value = float(rows[0]['dq_C'])
        rows[0]['dq_C'] = repr(-value if value else 1e-17)
        save_rows(convergence, rows, fields)
    add_case('B3_signed_dQ_flipped', 'B3', 'recompute', 'B3:', signed_dq)

    with io.open(os.path.join(out_dir, 'counterexamples.json'), 'w', encoding='utf-8',
                 newline='\n') as handle:
        json.dump(results, handle, ensure_ascii=False, indent=1)
        handle.write('\n')
    failures = [c for c in results['cases'] if not c['passed']]
    print('R2_PROBE cases=%d passed=%d failed=%d'
          % (len(results['cases']), len(results['cases']) - len(failures), len(failures)))
    for case in results['cases']:
        print('%-42s %-9s rc=%d named=%s %s'
              % (case['case'], case['entry'], case['rc'], case['named_rejection'],
                 (case['summary'] or [''])[0][:110]))
    for case in failures:
        print('FAILED %s -> %r' % (case['case'], case['stdout'][-300:] + case['stderr'][-300:]))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
