#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reviewer-only counterexamples against the real recomputation entry of DATA-7C-B-TR-R1.

No simulator, no guest. Each case is applied to a freshly built package copy outside the repository:
first the clean copy must re-derive everything, then exactly one fact is forged and the same entry
must refuse it by name. The forged table also refreshes every digest the copy itself carries, so a
refusal cannot be bought by keeping a stale manifest.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

PARSER = argparse.ArgumentParser()
PARSER.add_argument('repo')
PARSER.add_argument('--out', required=True)
SKIP_DIRS = ('guest_logs', 'selftest_stray_launches')
EVIDENCE = os.path.join('results', 'evidence')


def sha_of(path):
    digest = hashlib.sha256()
    with io.open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    return rows, handle and list(rows[0].keys())


def write_rows(path, rows, header):
    with io.open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator='\n',
                                quoting=csv.QUOTE_MINIMAL, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def evidence_names(repo):
    listed = sorted(os.listdir(os.path.join(repo, EVIDENCE)))
    r1 = [name for name in listed if name.startswith('dd1_d7c_b_tr_r1_')]
    native = [name for name in listed if name.startswith('dd1_d7c_b_tr_r2026')]
    if not r1 or not native:
        raise SystemExit('REVIEW_INPUT_MISSING this round publishes %s and the native round %s'
                         % (r1, native))
    return r1[-1], native[-1]


def build(root, repo, r1_name, native_name):
    """a package copy: the two evidence trees, the frozen contract, the decks and the recomputer"""
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root)
    os.makedirs(os.path.join(root, 'scripts'))
    shutil.copyfile(os.path.join(repo, 'scripts', 'dd1_d7c_b_tr_r1_recompute.py'),
                    os.path.join(root, 'scripts', 'dd1_d7c_b_tr_r1_recompute.py'))
    for directory in ('tests', EVIDENCE, os.path.join('spectre', 'dd1_d7c_b_tr')):
        target = os.path.join(root, directory)
        os.makedirs(target)
    os.makedirs(os.path.join(root, 'tests', 'dd1_d7c_b_tr'))
    shutil.copyfile(os.path.join(repo, 'tests', 'dd1_d7c_b_tr', 'contract.json'),
                    os.path.join(root, 'tests', 'dd1_d7c_b_tr', 'contract.json'))
    for name in sorted(os.listdir(os.path.join(repo, 'spectre', 'dd1_d7c_b_tr'))):
        if name.endswith('.scs'):
            shutil.copyfile(os.path.join(repo, 'spectre', 'dd1_d7c_b_tr', name),
                            os.path.join(root, 'spectre', 'dd1_d7c_b_tr', name))
    for name in (r1_name, native_name):
        shutil.copytree(os.path.join(repo, EVIDENCE, name), os.path.join(root, EVIDENCE, name),
                        ignore=shutil.ignore_patterns(*SKIP_DIRS, '*.raw', '*.log'))
    return root


def replay(root):
    script = os.path.join(root, 'scripts', 'dd1_d7c_b_tr_r1_recompute.py')
    process = subprocess.Popen([sys.executable, script, root], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    text = process.stdout.read().decode('utf-8', 'replace')
    process.wait()
    lines = text.splitlines()
    summary = [line for line in lines if line.startswith('RECOMPUTE_R1 ')]
    failed = [line for line in lines if line.startswith('RECOMPUTE_R1_FAIL')]
    refused = [line for line in lines if line.startswith('RECOMPUTE_R1_REFUSED')]
    log = os.path.join(root, 'replay.log')
    io.open(log, 'w', encoding='utf-8', newline='\n').write(text + '\n')
    return {'rc': process.returncode, 'summary': summary[0] if summary else '',
            'refused': refused[0] if refused else '', 'failed': failed[:6],
            'failed_lines': len(failed), 'log': log}


def touch_digests(root, r1_name):
    """a forger who also updates the copy's own manifest digests must still be refused"""
    path = os.path.join(root, EVIDENCE, r1_name, 'native_manifest.json')
    data = json.loads(io.open(path, encoding='utf-8').read())
    for entry in data['files']:
        for key in ('sha256', 'gzip_sha256', 'whole_sha256'):
            if entry.get(key):
                name = entry.get('dependency') or entry.get('name') or entry.get('file')
                for folder in ('dependencies', 'native_sequences', ''):
                    candidate = os.path.join(root, EVIDENCE, r1_name, folder, name or '')
                    if os.path.isfile(candidate):
                        entry[key] = sha_of(candidate)
                        break
        # a split artifact is carried by its parts, so a forger that only re-digests the whole name
        # has not made the copy self-consistent: every part keeps its own recorded digest too
        directory = os.path.join(root, EVIDENCE, r1_name, 'native_sequences')
        for item in entry.get('part_files') or []:
            candidate = os.path.join(directory, item['part'])
            if os.path.isfile(candidate):
                item['sha256'] = sha_of(candidate)
                item['bytes'] = os.path.getsize(candidate)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(data, indent=1, sort_keys=True) + '\n')


def forge_dc(root, r1_name):
    path = os.path.join(root, EVIDENCE, r1_name, 'windows_all.csv')
    rows, header = read_rows(path)
    for row in rows:
        if row['kind'] == 'emission':
            row['qtarget_dc_C'] = row['q_full_C']
            row['err_dynamic_LSB'] = '0'
    write_rows(path, rows, header)
    status = os.path.join(root, EVIDENCE, r1_name, 'statuses.csv')
    rows, header = read_rows(status)
    for row in rows:
        if row['status'] == 'DYNAMIC_CHARGE_STATUS':
            row['verdict'] = 'PASS'
    write_rows(status, rows, header)
    return 'every DC target replaced by the measured charge and the dynamic verdict written as PASS'


def forge_tick(root, r1_name):
    path = os.path.join(root, EVIDENCE, r1_name, 'windows_all.csv')
    rows, header = read_rows(path)
    for row in rows:
        if row['case_id'] != 'TR-120':
            continue
        tick = 1000.0
        qlsb = 1.875e-6 * tick * 1e-9
        charge = float(row['q_full_C'])
        row['tick_ns'] = repr(tick)
        row['qlsb_C'] = repr(qlsb)
        for target, cell in (('qtarget_dc_C', 'err_dynamic_LSB'),
                             ('qtarget_nominal_C', 'err_nominal_LSB')):
            row[cell] = repr((charge - float(row[target])) / qlsb)
    write_rows(path, rows, header)
    return 'the TR-120 denominator moved to a 1000 ns tick and both errors recomputed for it'


def forge_rtl(root, native_name):
    path = os.path.join(root, EVIDENCE, native_name, 'rtl_simulation_account.csv')
    rows, header = read_rows(path)
    rows[0]['exe_sha256'] = 'f' * 64
    rows[0]['rc'] = '99'
    rows[0]['state'] = 'FAILED'
    write_rows(path, rows, header)
    return 'the fifth RTL row was given an executable digest and a return code of its own'


def main():
    args = PARSER.parse_args()
    repo = os.path.abspath(args.repo)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    r1_name, native_name = evidence_names(repo)
    answer = {'repo': repo, 'r1_evidence': r1_name, 'native_evidence': native_name,
              'simulator_launches': 0, 'rtl_simulations': 0, 'cases': {}}
    clean = build(os.path.join(out, 'clean'), repo, r1_name, native_name)
    base = replay(clean)
    answer['clean_package'] = base
    for name, forger in (('forged_dc_target_and_dynamic_PASS', forge_dc),
                         ('wrong_reference_tick_1000ns', forge_tick),
                         ('five_process_evidence_rows_as_four', forge_rtl)):
        root = build(os.path.join(out, name), repo, r1_name, native_name)
        which = r1_name if name != 'five_process_evidence_rows_as_four' else native_name
        reason = forger(root, which)
        touch_digests(root, r1_name)
        result = replay(root)
        result['injected'] = reason
        result['refused_by_name'] = bool(result['refused'] or result['failed_lines'])
        result['reproduced'] = base['rc'] == 0 and result['rc'] != 0
        answer['cases'][name] = result
    answer['clean_recomputes'] = base['rc'] == 0
    answer['all_three_refused'] = all(item['reproduced'] and item['refused_by_name']
                                      for item in answer['cases'].values())
    dest = os.path.join(out, 'r1_recompute_forgery.json')
    io.open(dest, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(answer, indent=1, sort_keys=True) + '\n')
    print(json.dumps({'clean': base['summary'],
                      'cases': dict((key, {'rc': value['rc'], 'refused': value['refused'][:180],
                                           'failed_lines': value['failed_lines'],
                                           'reproduced': value['reproduced']})
                                    for key, value in answer['cases'].items()),
                      'all_three_refused': answer['all_three_refused'],
                      'result': dest}, indent=1, sort_keys=True))
    return 0 if answer['all_three_refused'] and answer['clean_recomputes'] else 1


if __name__ == '__main__':
    sys.exit(main())
