#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DATA-7B-R3: run the verification of this round's fix over the frozen R2 evidence and record it

The R3 evidence directory carries no simulated samples: the R2 bundle is the input, is not written to,
and is identified here by its manifest digest and file set. What this script adds is the small record
TASK_DATA7B_R3 section 3 asks for -- the tool identities, the verification input identity, every
command with its own return code, the illegal-state positive and negative results, the earlier
regressions, and the frozen-path comparison.

Nothing here starts Spectre, Icarus or a remote connection. The reproduce leg extracts the base commit
into a temporary directory with `git archive` and runs the same read-only checks over it, so a reviewer
with the repository can repeat both directions from one command.

usage: python scripts/dd1_d7b_r3_verify.py --out results/evidence/dd1_d7b_r3_<unique_run_id>
"""
from __future__ import print_function

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
PROJ = os.path.dirname(HERE)
BASE_SHA = 'b3fe93c17de014cb16031438ce28c7152dd0020f'
P2_SHA = '6abe1bf5b93dc4bb12ba179cea0ab26929f33a90'
R2_BUNDLE = os.path.join('results', 'evidence', 'dd1_d7b_r2_r20261022_160652_e880be')
ACCEPTED = os.path.join('results', 'evidence', 'dd1_d7b_r11_main')
R1_BUNDLE = os.path.join('results', 'evidence', 'dd1_d7b_r1_r20261022_123825_8e1294')
TOOLS = ('dd1_d7b_run.py', 'dd1_d7b_measure.py', 'dd1_d7b_evidence_check.py', 'dd1_d7b_trace.py',
         'dd1_d7b_r1_guards.py', 'dd1_d7b_r1_gate_records.py', 'dd1_d7b_r2_guards.py',
         'dd1_d7b_r2_result_set.py', 'dd1_d7b_r3_guards.py', 'dd1_d7b_r3_verify.py')
# (record name, argv, the substring its success line must contain)
GATES = (
    ('measure_selftest', ('scripts/dd1_d7b_measure.py', '--selftest'),
     'D7B_MEASURE_SELFTEST: PASS'),
    ('run_selftest', ('scripts/dd1_d7b_run.py', '--selftest'), 'D7B_RUN_SELFTEST: PASS'),
    ('trace_selftest', ('scripts/dd1_d7b_trace.py', '--selftest'), 'D7B_TRACE_SELFTEST: PASS'),
    # rc 1 is the expected outcome here: the only failure is the disclosed historical budget one,
    # and a checker that returned 0 over this bundle would have whitelisted it
    ('r2_bundle_recheck', ('scripts/dd1_d7b_evidence_check.py', R2_BUNDLE.replace(os.sep, '/')),
     'failures: BUDGET_RESPECTED', 1),
    ('r2_evidence_selftest', ('scripts/dd1_d7b_evidence_check.py', '--selftest',
                              R2_BUNDLE.replace(os.sep, '/')), 'D7B_EVIDENCE_SELFTEST: PASS'),
    ('r1_guards', ('scripts/dd1_d7b_r1_guards.py',), 'D7B_R1_GUARDS: PASS'),
    ('r2_guards_closed', ('scripts/dd1_d7b_r2_guards.py', '--phase', 'fixed', '--bundle',
                          R2_BUNDLE.replace(os.sep, '/')), 'D7B_R2_GUARDS: PASS'),
    ('r3_guards_closed', ('scripts/dd1_d7b_r3_guards.py', '--phase', 'fixed'),
     'D7B_R3_GUARDS: PASS'),
    ('safety_gate', ('scripts/precommit_safety_check.py',), 'SAFETY_GATE: PASS'),
    ('provenance_gate', ('scripts/provenance_check.py',), 'SOURCE_PROVENANCE_CHECK: PASS'),
    ('handoff_structure', ('scripts/dd1_d7b_validate_handoff.py',
                           'reports/agent_handoffs/DATA-7B.json'), 'HANDOFF_STRUCTURE: PASS'),
)
LOCAL = re.compile(r'(?i)([a-z]:[\\/]|/dev/|/home/|/users/|\\\\)')


def u(text):
    if isinstance(text, bytes):
        return text.decode('utf-8', 'replace')
    return text


def sha(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()


def rows_write(path, hdr, rows):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(','.join(hdr) + '\n')
        for r in rows:
            # a captured transcript can end in spaces, and git's whitespace check over the committed
            # range then contradicts the git_checks.csv row this same run writes, so cells are trimmed
            f.write(','.join(str(r.get(k, '')).replace(',', ';').rstrip() for k in hdr) + '\n')


def run(cmd, cwd=PROJ):
    """one command: rc, the verdict line it printed, and how many lines were dropped for local paths"""
    p = subprocess.Popen([sys.executable] + list(cmd), cwd=cwd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    text = u(p.communicate()[0] or '')
    kept, dropped = [], 0
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if LOCAL.search(line):
            dropped += 1
            continue
        kept.append(line[:200])
    verdict = ''
    for line in reversed(kept):
        if re.match(r'^(D7B_|SAFETY_GATE|SOURCE_PROVENANCE|HANDOFF_|GUARD_)', line):
            verdict = line
            break
    return {'rc': p.returncode, 'verdict': verdict[:200], 'lines_kept': len(kept),
            'lines_dropped_for_local_path': dropped, 'tail': ' | '.join(kept[-3:])[:260]}


def bundle_identity(rel):
    """the R2 input as bytes: file count, manifest coverage and the manifest digest itself"""
    root = os.path.join(PROJ, rel)
    files = []
    for dir_path, _dirs, names in os.walk(root):
        for n in names:
            files.append(os.path.relpath(os.path.join(dir_path, n), root).replace(os.sep, '/'))
    man = json.loads(u(io.open(os.path.join(root, 'manifest.json'), encoding='utf-8').read()))
    return {'bundle': rel.replace(os.sep, '/'), 'files_on_disk': len(files),
            'bytes_on_disk': sum(os.path.getsize(os.path.join(root, p)) for p in files),
            'manifest_entries': len(man['files']), 'manifest_total_bytes': man['total_bytes'],
            'manifest_sha256': sha(os.path.join(root, 'manifest.json')),
            'manifest_self_referential': 'manifest.json' in [e['path'] for e in man['files']]}


def extract_base(dest):
    """the base commit's read-only tree, so the reproduce leg judges the bytes it started from"""
    subprocess.check_call(['git', '-C', PROJ, 'archive', BASE_SHA, 'scripts', 'tests', 'rtl',
                           'results/evidence'], stdout=open(os.path.join(dest, '.archive.tar'), 'wb'))
    subprocess.check_call(['tar', '-x', '-C', dest, '-f', os.path.join(dest, '.archive.tar')])
    os.remove(os.path.join(dest, '.archive.tar'))
    return dest


def ls_tree(rev):
    """{(path): (mode, blob)} for one revision, from a single `git ls-tree`"""
    out = subprocess.check_output(['git', '-C', PROJ, 'ls-tree', '-r', rev])
    res = {}
    for line in u(out).split('\n'):
        if not line.strip():
            continue
        meta, path = line.split('\t', 1)
        mode, _type, blob = meta.split()
        res[path] = '%s %s' % (mode, blob)
    return res


def compare_paths(rev_a, rev_b, prefix=None, paths=None):
    a, b = ls_tree(rev_a), ls_tree(rev_b)
    keys = paths if paths is not None else [k for k in a
                                            if prefix is None or k.startswith(prefix)]
    bad = ['%s: %s against %s' % (k, a[k], b.get(k, 'absent')) for k in sorted(keys)
           if b.get(k) != a[k]]
    return {'paths_compared': len(keys), 'mismatched': len(bad),
            'first_mismatches': ' '.join(bad[:2]) or '-'}


def diff_check():
    """whitespace and eof over the committed range, not over an untracked working copy"""
    p = subprocess.Popen(['git', '-C', PROJ, 'diff', '--check', '%s..HEAD' % BASE_SHA],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = u(p.communicate()[0] or '')
    return {'rc': p.returncode, 'lines': len([x for x in out.split('\n') if x.strip()])}


SHARED_TOOLS = ('scripts/repo_safety_rules.py', 'scripts/repo_safety_scan.py',
                'scripts/precommit_safety_check.py', 'scripts/provenance_check.py',
                'scripts/test_safety_rules.py', 'scripts/dd1_d7a_validate_handoff.py',
                'scripts/dd1_d7b_validate_handoff.py', 'scripts/sc1_read_psf.py',
                'scripts/sc1_r2e1_call_contract.py', 'scripts/run_spectre.sh',
                'scripts/sc1_supply_check.awk', 'scripts/tb_preflight.sh')


def frozen_comparison():
    """the frozen surfaces compared by mode and blob, not by file names alone"""
    out = []
    checks = (('development_base_b_all_tracked_paths',
               ('c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37', 'HEAD', None, None)),
              ('accepted_d7b_bundle', (BASE_SHA, 'HEAD', ACCEPTED.replace(os.sep, '/') + '/', None)),
              ('r1_bundle', (BASE_SHA, 'HEAD', R1_BUNDLE.replace(os.sep, '/') + '/', None)),
              ('r2_bundle', (BASE_SHA, 'HEAD', R2_BUNDLE.replace(os.sep, '/') + '/', None)),
              ('frozen_case_and_golden_tables', (BASE_SHA, 'HEAD', 'tests/dd1_d7b/', None)),
              ('measure_core_and_trace_parser',
               (BASE_SHA, 'HEAD', None, ['scripts/dd1_d7b_measure.py', 'scripts/dd1_d7b_trace.py',
                                         'scripts/dd1_d7a_trace.py'])),
              ('shared_safety_runner_and_handoff_validators',
               (BASE_SHA, 'HEAD', None, list(SHARED_TOOLS))))
    for label, (a, b, prefix, paths) in checks:
        got = compare_paths(a, b, prefix, paths)
        got['surface'] = label
        got['rc'] = 0 if not got['mismatched'] else 1
        out.append(got)
    return out


def make_run_id(root):
    while True:
        rid = 'r%s_%s' % (time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
                          hashlib.sha1(os.urandom(8)).hexdigest()[:6])
        if not os.path.exists(os.path.join(root, 'dd1_d7b_r3_%s' % rid)):
            return rid


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, help='new results/evidence/dd1_d7b_r3_<run_id> directory')
    ap.add_argument('--diagnostic', default='', help="replay the reviewer's account-state "
                        'diagnostic over this checkout; recorded as NOT_ATTEMPTED when absent')
    opts = ap.parse_args(argv)
    ev = os.path.abspath(opts.out)
    if os.path.exists(ev):
        raise SystemExit('D7B_R3_VERIFY_REFUSED %s already exists; nothing is overwritten' % ev)
    for sub in ('', 'diagnostics'):
        os.makedirs(os.path.join(ev, sub))
    results = []
    for entry in GATES:
        name, cmd, expect = entry[0], entry[1], entry[2]
        want_rc = entry[3] if len(entry) > 3 else 0
        r = run(cmd)
        r.update({'gate': name, 'command': ' '.join(cmd),
                  'expected_line': '%s (rc=%d expected)' % (expect, want_rc),
                  'verdict_state': 'PASS' if (r['rc'] == want_rc
                                            and expect in r['verdict'] + r['tail'])
                  else 'FAIL'})
        results.append(r)
        print('GATE %-22s rc=%s %s' % (name, r['rc'], r['verdict_state']))
    # the illegal-state finding, both directions, over disposable copies only
    tmp = tempfile.mkdtemp(prefix='d7b-r3-base-')
    try:
        base = extract_base(tmp)
        rep = run(['scripts/dd1_d7b_r3_guards.py', '--phase', 'reproduce', '--scripts-dir',
                   os.path.join(base, 'scripts'), '--repo', base], cwd=PROJ)
        rep.update({'gate': 'r3_guards_reproduce_on_base',
                    'command': 'python scripts/dd1_d7b_r3_guards.py --phase reproduce '
                               '--scripts-dir <base ' + BASE_SHA[:8] + ' extract> '
                               '--repo <base extract>',
                    'expected_line': 'D7B_R3_GUARDS: PASS',
                    'verdict_state': 'PASS' if rep['rc'] == 0 else 'FAIL'})
        results.append(rep)
        print('GATE r3_guards_reproduce    rc=%s %s' % (rep['rc'], rep['verdict_state']))
        diag = os.path.join(ev, 'diagnostics', 'account_states_after.json')
        script = os.path.abspath(opts.diagnostic) if opts.diagnostic else ''
        if script and os.path.isfile(script):
            d = subprocess.Popen([sys.executable, script, PROJ.replace(os.sep, '/'),
                                  diag.replace(os.sep, '/')],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            dtxt = u(d.communicate()[0] or '')
            state = 'PASS' if d.returncode == 1 else 'FAIL'
            results.append({'gate': 'reviewer_account_states_after_fix',
                            'command': 'python reviewer_account_states.py <this checkout> '
                                       '<diagnostic>',
                            'rc': d.returncode, 'verdict': dtxt.strip().split('\n')[-1][:200],
                            'lines_kept': 0, 'lines_dropped_for_local_path': 0, 'tail': '',
                            'expected_line': 'rc=1 with all_requirements_met true',
                            'verdict_state': state})
            print('GATE reviewer_diagnostic rc=%s %s' % (d.returncode, state))
        else:
            results.append({'gate': 'reviewer_account_states_after_fix',
                            'command': 'python reviewer_account_states.py <this checkout> '
                                       '<diagnostic>',
                            'rc': '', 'verdict': 'NOT_ATTEMPTED: pass --diagnostic to replay the '
                                                 "reviewer's own instrument over this checkout",
                            'lines_kept': 0, 'lines_dropped_for_local_path': 0, 'tail': '',
                            'expected_line': 'rc=1 with all_requirements_met true',
                            'verdict_state': 'NOT_ATTEMPTED'})
            print('GATE reviewer_diagnostic NOT_ATTEMPTED (recorded, never counted as a pass)')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows_write(os.path.join(ev, 'commands.csv'),
               ['gate', 'command', 'rc', 'verdict_state', 'expected_line', 'verdict',
                'lines_kept', 'lines_dropped_for_local_path', 'tail'], results)
    rows_write(os.path.join(ev, 'tools_identity.csv'),
               ['role', 'path', 'sha256'],
               [{'role': 'R3 tool under test', 'path': 'scripts/%s' % t,
                 'sha256': sha(os.path.join(HERE, t))} for t in TOOLS
                if os.path.isfile(os.path.join(HERE, t))])
    ident = bundle_identity(R2_BUNDLE)
    r2_env = json.loads(u(io.open(os.path.join(PROJ, R2_BUNDLE, 'environment.json'),
                                  encoding='utf-8').read()))
    rows_write(os.path.join(ev, 'verification_input.csv'),
               ['item', 'value'],
               [{'item': 'R2 bundle (frozen, read only)', 'value': ident['bundle']},
                {'item': 'R2 files on disk (includes manifest.json)',
                 'value': ident['files_on_disk']},
                {'item': 'R2 bytes on disk (includes manifest.json)',
                 'value': ident['bytes_on_disk']},
                {'item': 'R2 manifest entries (excludes manifest.json)',
                 'value': ident['manifest_entries']},
                {'item': 'R2 manifest covered bytes (excludes manifest.json)',
                 'value': ident['manifest_total_bytes']},
                {'item': 'R2 manifest.json sha256', 'value': ident['manifest_sha256']},
                {'item': 'R2 manifest lists itself', 'value': str(ident['manifest_self_referential'])},
                {'item': 'R2 exporter measurement_source_sha256',
                 'value': r2_env.get('measurement_source_sha256')},
                {'item': 'R2 exporter runner_source_sha256',
                 'value': r2_env.get('runner_source_sha256')},
                {'item': 'R2 exporter evidence_check_source_sha256',
                 'value': r2_env.get('evidence_check_source_sha256')},
                {'item': 'R2 base_sha (this round\'s base)', 'value': r2_env.get('base_sha')},
                {'item': 'R2 run_id', 'value': r2_env.get('run_id')},
                {'item': 'base commit verified by this round', 'value': BASE_SHA},
                {'item': 'R2 payload commit P2', 'value': P2_SHA}])
    rows_write(os.path.join(ev, 'frozen_comparison.csv'),
               ['surface', 'rc', 'paths_compared', 'mismatched', 'first_mismatches'],
               frozen_comparison())
    rows_write(os.path.join(ev, 'account_states.csv'),
               ['state', 'billed_by_the_protocol', 'occupies_the_ceiling', 'note'],
               [{'state': 'REQUESTED', 'billed_by_the_protocol': 'YES',
                 'occupies_the_ceiling': 'YES',
                 'note': 'reserved before the process starts; costs the ceiling when written'},
                {'state': 'UNCERTAIN', 'billed_by_the_protocol': 'YES',
                 'occupies_the_ceiling': 'YES',
                 'note': 'a recovered REQUESTED row; provenance changes, price does not'},
                {'state': 'CONFIRMED', 'billed_by_the_protocol': 'YES',
                 'occupies_the_ceiling': 'YES', 'note': 'returned text proves a process ran'},
                {'state': 'COMPLETED', 'billed_by_the_protocol': 'YES',
                 'occupies_the_ceiling': 'YES', 'note': 'same billing as CONFIRMED, counted once'},
                {'state': 'REFUSED_NO_LAUNCH', 'billed_by_the_protocol': 'YES',
                 'occupies_the_ceiling': 'NO', 'note': 'no process was ever started for this row'},
                {'state': '(empty) / (missing) / any other spelling',
                 'billed_by_the_protocol': 'NO', 'occupies_the_ceiling': 'REFUSED',
                 'note': 'Account raises before recover/_restamp/flush, so the bytes stay; '
                        'counts() and reserve() refuse the same row in memory; the re-checker adds '
                        'ACCOUNT_STATES_VALID over every row'}])
    rows_write(os.path.join(ev, 'git_checks.csv'), ['check', 'rc', 'detail'],
               [{'check': 'git diff --check %s..HEAD' % BASE_SHA[:8],
                 'rc': diff_check()['rc'],
                 'detail': '%d whitespace lines over the committed range' % diff_check()['lines']}])
    fails = [r['gate'] for r in results if r['verdict_state'] != 'PASS']
    summary = {'run_id': os.path.basename(ev), 'base_sha': BASE_SHA, 'p2_sha': P2_SHA,
               'commands': len(results), 'failures': fails,
               'new_spectre_launches': 0, 'new_rtl_simulations': 0, 'new_oa_writes': 0,
               'r2_bundle_rewritten': 'NO -- read only',
               'scope': 'account state enumeration plus the documentation corrections'}
    with io.open(os.path.join(ev, 'verification_summary.json'), 'w', encoding='utf-8',
                 newline='\n') as f:
        f.write(json.dumps(summary, indent=1, sort_keys=True) + '\n')
    print('D7B_R3_VERIFY: %s (%d commands, %d failure(s): %s)'
          % ('PASS' if not fails else 'FAIL', len(results), len(fails), ' '.join(fails) or '-'))
    print('R3_EVIDENCE %s' % ev.replace(os.sep, '/'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
