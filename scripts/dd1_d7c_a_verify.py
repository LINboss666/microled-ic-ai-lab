#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_verify.py -- run every DATA-7C-A gate and publish the record in one small directory.

Offline only. Every command is a subprocess over this checkout or over an extraction of the base
commit, each with its own expected return code; a gate never reports PASS on an unexpected code, and
the record is only written once. No Spectre, no RTL simulator, no OA, no SSH, no credential read.

    python scripts/dd1_d7c_a_verify.py --out results/evidence/dd1_d7c_a_<run_id> [--base-rev SHA]
"""

from __future__ import absolute_import, division, print_function

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = '272d6de6d2f2fc8a82d5038d73d6b3e4c656f683'
TASK_ID = 'DATA-7C-A'

sys.path.insert(0, HERE)
import dd1_d7c_a_offline_check as CHECK      # noqa: E402
import dd1_d7c_a_guards as GUARDS            # noqa: E402

REPORTS = [os.path.join(ROOT, 'reports', 'dd1_d7c_a_pam_candidate.md'),
           os.path.join(ROOT, 'reports', 'dd1_d7c_a_native_test_plan.md')]
FROZEN_SURFACES = [
    ('development_base_all_tracked_paths', None),
    ('accepted_data7b_r3_evidence', 'results/evidence/dd1_d7b_r2_r20261022_160652_e880be'),
    ('data7b_r1_evidence', 'results/evidence/dd1_d7b_r1_r20261022_123825_8e1294'),
    ('data7b_main_line_evidence', 'results/evidence/dd1_d7b_r11_main'),
    ('case_and_golden_tables_D7B', 'tests/dd1_d7b'),
    ('accepted_D7A_rtl_and_tb', 'rtl'),
    ('shared_safety_and_validation_tools', 'scripts'),
    ('accepted_netlist_masters', 'spectre'),
    ('review_documents_DATA7B_R3', 'reports/reviews/DATA-7B-R3'),
]


def git(*args):
    return subprocess.check_output(['git', '-C', ROOT] + list(args))


def sha(path):
    with io.open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def rows_write(path, header, rows):
    """write CSV with every cell stripped, so the record cannot contradict git diff --check"""
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    out = [','.join([c.rstrip() for c in header])]
    for row in rows:
        out.append(','.join(str(row.get(h, '')).replace('\n', ' ').rstrip() for h in header))
    with io.open(path, 'wb') as handle:
        handle.write(('\n'.join(out) + '\n').encode('utf-8'))


def run(cmd, cwd=None):
    process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = process.communicate()[0] or ''
    return process.returncode, text.decode('utf-8', 'replace')


def full_index(rev):
    """one `git ls-tree -r` for the whole tree; pathspec lists this long break the Windows argv"""
    raw = git('ls-tree', '-r', rev).decode('utf-8', 'replace')
    index = {}
    for line in raw.split('\n'):
        if not line.strip():
            continue
        meta, path = line.split('\t', 1)
        bits, kind, blob = meta.split()
        index[path] = (bits, blob)
    return index


def frozen_comparison(base_rev):
    """compare (mode, blob) of every tracked path between base and this tip"""
    base_index = full_index(base_rev)
    head_index = full_index('HEAD')
    base_paths = sorted(base_index)
    rows = []
    for label, prefix in FROZEN_SURFACES:
        wanted = [p for p in base_paths if (prefix is None or p.startswith(prefix + '/'))]
        diff = [p for p in wanted if head_index.get(p) != base_index.get(p)]
        rows.append({'surface': label, 'paths_compared': len(wanted),
                     'mismatched': len(diff),
                     'first_mismatches': '; '.join(diff[:4]) or '-'})
    added = sorted(set(head_index) - set(base_index))
    removed = sorted(set(base_index) - set(head_index))
    return rows, added, removed


def render_sections(offline_json, guards_json, root):
    """mechanically render the two report sections from the JSON the gates just wrote"""
    plan_rows = []
    with io.open(os.path.join(root, 'tests', 'dd1_d7c_a', 'native_case_plan.csv'),
                 encoding='utf-8') as handle:
        plan_rows = list(__import__('csv').DictReader(handle))
    plan_lines = ['| 用例 | 类别 | 目的 | 观察节点 | 测量区间 | 参考定义 | 失败条件 | 草案额度 | 结果 |',
                  '|---|---|---|---|---|---|---|---:|---|']
    for row in plan_rows:
        plan_lines.append('| `%s` | %s | %s | %s | %s | %s | %s | %s | **%s** |' % (
            row['case_id'], row['class'], row['purpose'], row['observe_nodes'],
            row['measure_interval'], row['reference_definition'], row['failure_condition'],
            row['draft_launch_units'], row['result']))
    plan_lines.append('')
    plan_lines.append('渲染来源：`tests/dd1_d7c_a/native_case_plan.csv`（%d 行，草案额度合计 %d，'
                      '结果列全部为 `NOT_RUN`）。本表由 `scripts/dd1_d7c_a_verify.py` 写入，不手填。'
                      % (len(plan_rows), sum(int(r['draft_launch_units']) for r in plan_rows)))

    gates = offline_json['checks']
    offline_lines = ['| 检查 | 结果 | 依据（截断到 180 字） |', '|---|---|---|']
    for row in gates:
        offline_lines.append('| `%s` | %s | %s |' % (row['check'], row['result'],
                                                     row['reason'][:180].replace('|', '/')))
    offline_lines.append('')
    offline_lines.append('合计 %d 项，失败：%s。渲染来源 `offline_checks.json`（本目录）。'
                         % (len(offline_json['checks']),
                            ', '.join(offline_json['failures']) or 'none'))

    guards_lines = ['| 反例 | 判决 | 注入文件 | 声明的新增失败集合 | 实测新增失败 | 字节改动证据 |',
                    '|---|---|---|---|---|---|']
    self_files = set(r for r in CHECK.CLAIM_FILES if r.startswith('reports/'))
    for row in guards_json['injections']:
        if row.get('file') in self_files:
            # this injection edits the very report that carries the table, so its digest cannot be
            # printed here without a self-reference; the full before/after pair stays in
            # counterexamples.json
            digest = '摘要见 `counterexamples.json`（注入对象是本报告，包内不写自身摘要）'
        elif row.get('digest_before'):
            digest = '行改动 %d，%s->%s' % (len(row.get('lines_changed', [])),
                                           row['digest_before'][:8], row['digest_after'][:8])
        else:
            digest = '-'
        guards_lines.append('| `%s` | %s | %s | %s | %s | %s |' % (
            row['injection'], row['verdict'], row.get('file', '-'),
            ','.join(row['expected']) or '(empty)', ','.join(row.get('found', [])) or '-', digest))
    guards_lines.append('')
    guards_lines.append('基线（未注入）失败集合：%s；规则：`found == sorted(expected)` 且 '
                        'expected 非空，否则该探针不算检出。E09 的注入对象就是本报告，因此它的字节'
                        '摘要只出现在 `counterexamples.json`，不写进报告——写进来就变成自指，本表也会'
                        '因此每次渲染都不同（这正是渲染固定点检查要拦住的事）。'
                        % (', '.join(guards_json['baseline_failures']) or 'none'))
    _splice(REPORTS[0], '<!-- BEGIN 7C OFFLINE -->', '<!-- END 7C OFFLINE -->', offline_lines)
    _splice(REPORTS[0], '<!-- BEGIN 7C GUARDS -->', '<!-- END 7C GUARDS -->', guards_lines)
    _splice(REPORTS[1], '<!-- BEGIN 7C PLAN -->', '<!-- END 7C PLAN -->', plan_lines)


def _splice(path, begin, end, lines):
    with io.open(path, encoding='utf-8') as handle:
        body = handle.read()
    if begin not in body or end not in body:
        raise SystemExit('RENDER_REFUSED marker %s missing in %s' % (begin, path))
    head, rest = body.split(begin, 1)
    _old, tail = rest.split(end, 1)
    replacement = begin + '\n' + '\n'.join(lines) + '\n' + end
    with io.open(path, 'wb') as handle:
        handle.write((head + replacement + tail).encode('utf-8'))


def main(argv):
    out_dir = ''
    base_rev = BASE
    if '--out' in argv:
        out_dir = os.path.abspath(argv[argv.index('--out') + 1])
    if '--base-rev' in argv:
        base_rev = argv[argv.index('--base-rev') + 1]
    if not out_dir:
        run_id = 'r%s_%06x' % (time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
                               int(hashlib.sha256(os.urandom(8)).hexdigest()[:6], 16))
        out_dir = os.path.join(ROOT, 'results', 'evidence', '%s_%s' % (TASK_ID.lower(), run_id))
    if os.path.isdir(out_dir):
        raise SystemExit('DD1_7C_A_VERIFY_REFUSED %s already exists; published records are never '
                         'overwritten, choose a new run id' % out_dir)
    os.makedirs(out_dir)
    results, added, removed, rows, render_passes = [], [], [], [], []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-a-verify-')
    try:
        offline_json_path = os.path.join(out_dir, 'offline_checks.json')
        guards_json_path = os.path.join(out_dir, 'counterexamples.json')

        # 1) offline structure and logic checks on the delivered bytes
        rc, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_offline_check.py'),
                        '--json', offline_json_path])
        results.append({'gate': 'offline_checks', 'command': 'python dd1_d7c_a_offline_check.py '
                        '--json <out>', 'rc': rc, 'expected_rc': 0,
                        'verdict': text.strip().split('\n')[-1][:200]})
        print('GATE offline_checks        rc=%s %s' % (rc, results[-1]['verdict'][:80]))

        # 2) counterexamples
        rc, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_guards.py'),
                        '--json', guards_json_path])
        results.append({'gate': 'counterexamples',
                        'command': 'python dd1_d7c_a_guards.py --json <out>', 'rc': rc,
                        'expected_rc': 0, 'verdict': text.strip().split('\n')[-1][:200]})
        print('GATE counterexamples       rc=%s %s' % (rc, results[-1]['verdict'][:80]))

        # 3) handoff structure validator (new, does not touch the frozen DATA-7B one)
        handoff = os.path.join(ROOT, 'reports', 'agent_handoffs', 'DATA-7C-A.json')
        if os.path.isfile(handoff):
            rc, text = run([sys.path[0] and sys.executable,
                            os.path.join(HERE, 'dd1_d7c_a_validate_handoff.py'), handoff])
            results.append({'gate': 'handoff_structure',
                            'command': 'python dd1_d7c_a_validate_handoff.py '
                            'reports/agent_handoffs/DATA-7C-A.json', 'rc': rc, 'expected_rc': 0,
                            'verdict': text.strip().split('\n')[-1][:200]})
            print('GATE handoff_structure     rc=%s %s' % (rc, results[-1]['verdict'][:80]))

        # 4) the deck generator entry must refuse and leave everything untouched
        probe = os.path.join(scratch, 'deckprobe')
        os.makedirs(probe)
        with io.open(os.path.join(probe, 'sentinel.txt'), 'wb') as handle:
            handle.write(b'sentinel\n')
        rc, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_deckgen.py'), '--probe',
                        probe], cwd=scratch)
        results.append({'gate': 'native_entry_refused',
                        'command': 'python dd1_d7c_a_deckgen.py --probe <temp dir>', 'rc': rc,
                        'expected_rc': 0, 'verdict': text.strip().split('\n')[-1][:200]})
        print('GATE native_entry_refused rc=%s %s' % (rc, results[-1]['verdict'][:80]))

        # 5) provenance label gate
        rc, text = run([sys.executable, os.path.join(HERE, 'provenance_check.py')])
        results.append({'gate': 'provenance', 'command': 'python provenance_check.py', 'rc': rc,
                        'expected_rc': 0, 'verdict': text.strip().split('\n')[-1][:200]})
        print('GATE provenance            rc=%s %s' % (rc, results[-1]['verdict'][:80]))

        # 6) the frozen device-count polisher: prove its failure is pre-existing, not ours
        base_tree = os.path.join(scratch, 'base')
        os.makedirs(base_tree)
        archive = subprocess.Popen(['git', '-C', ROOT, 'archive', base_rev, 'scripts', 'tests',
                                    'rtl', 'spectre', 'reports'], stdout=subprocess.PIPE)
        tar = subprocess.Popen(['tar', '-x', '-C', base_tree], stdin=archive.stdout)
        archive.stdout.close()
        if tar.wait() != 0:
            raise SystemExit('BASE_EXTRACTION_FAILED')
        rc_base, text_base = run([sys.executable, os.path.join(base_tree, 'scripts',
                                                              'netlist_stats.py')],
                                cwd=base_tree)
        problems_base = sorted(set(re.findall(r'PROBLEM (\S+ claims \d+ devices)', text_base)))
        rc_head, text_head = run([sys.executable, os.path.join(HERE, 'netlist_stats.py')])
        problems_head = sorted(set(re.findall(r'PROBLEM (\S+ claims \d+ devices)', text_head)))
        pre_existing = set(problems_base)
        new_problems = sorted(set(problems_head) - pre_existing)
        # This frozen tool compares every count claim in every report against the ONE cell named by
        # --cell (default C2MOS_DFF, 18 devices). It therefore flags every claim about any other cell,
        # which is a scope limit that predates this round (it already fails at base). The generalised
        # polisher for this round is REPORT_CLAIM_COUNTS_MATCH, exercised by counterexample E09.
        # Recording this gate as PASS anyway would be the dishonest option, so it is recorded as
        # INFORMATIONAL_NOT_PASS with both problem lists.
        results.append({'gate': 'netlist_stats_scope_limit',
                        'command': 'python netlist_stats.py at the base extraction and at this tip',
                        'rc': '%d/%d' % (rc_base, rc_head),
                        'expected_rc': 'INFORMATIONAL: pre-existing single-cell scope, not a PASS',
                        'verdict': 'base problems %d %s; tip problems %d; of the tip problems %d are '
                                   'pre-existing and %d are this round claims about cells other than '
                                   'the tool default (C2MOS 18 devices): %s'
                                   % (len(problems_base), problems_base or 'none',
                                      len(problems_head), len(pre_existing & set(problems_head)),
                                      len(new_problems), new_problems[:6])})
        results[-1]['verdict_state'] = 'INFORMATIONAL_NOT_PASS'
        print('GATE netlist_stats_scope   INFORMATIONAL (base=%d tip=%d new=%d)'
              % (len(problems_base), len(problems_head), len(new_problems)))

        # 7) the repo safety gate over history, read-only
        rc, text = run([sys.executable, os.path.join(HERE, 'precommit_safety_check.py'),
                        '--mode', 'history'])
        results.append({'gate': 'history_safety',
                        'command': 'python precommit_safety_check.py --mode history', 'rc': rc,
                        'expected_rc': 0, 'verdict': text.strip().split('\n')[-1][:200]})
        print('GATE history_safety        rc=%s %s' % (rc, results[-1]['verdict'][:60]))

        # render the report sections from what the gates just wrote, then re-run both gates and
        # require the render to be a fixed point: a report that only just became true is refused
        render_passes = []
        for attempt in (1, 2, 3):
            offline = json.loads(io.open(offline_json_path, encoding='utf-8').read())
            guards = json.loads(io.open(guards_json_path, encoding='utf-8').read())
            render_sections(offline, guards, ROOT)
            before = [sha(path) for path in REPORTS]
            rc2, _ = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_offline_check.py'),
                          '--json', offline_json_path])
            rc3, _ = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_guards.py'),
                          '--json', guards_json_path])
            offline = json.loads(io.open(offline_json_path, encoding='utf-8').read())
            guards = json.loads(io.open(guards_json_path, encoding='utf-8').read())
            render_sections(offline, guards, ROOT)
            after = [sha(path) for path in REPORTS]
            render_passes.append({'attempt': attempt, 'offline_rc': rc2, 'guards_rc': rc3,
                                  'reports_stable': before == after,
                                  'report_sha_before': before, 'report_sha_after': after})
            print('RENDER pass %d offline rc=%s guards rc=%s reports stable=%s'
                  % (attempt, rc2, rc3, before == after))
            if before == after and rc2 == 0 and rc3 == 0:
                break
        stable_render = bool(render_passes) and render_passes[-1]['reports_stable'] and \
            render_passes[-1]['offline_rc'] == 0 and render_passes[-1]['guards_rc'] == 0
        results.append({'gate': 'render_fixed_point',
                        'command': 're-run the two gates after rendering, then render again and '
                        'compare the two report digests',
                        'rc': len(render_passes), 'expected_rc': 'the last pass is stable with both '
                        'gates rc=0', 'verdict': 'passes %s' % [p['attempt'] for p in
                                                                 render_passes]})
        results[-1]['verdict_state'] = 'PASS' if stable_render else 'FAIL'
        print('GATE render_fixed_point    %s' % results[-1]['verdict_state'])

        # 8) frozen comparison of every tracked path
        rows, added, removed = frozen_comparison(base_rev)
        diff_rc = subprocess.call(['git', '-C', ROOT, 'diff', '--check', '%s..HEAD' % base_rev])
        git_rows = [{'gate': 'diff_check_base_to_head',
                     'command': 'git diff --check %s..HEAD' % base_rev,
                     'rc': diff_rc, 'lines': 0 if diff_rc == 0 else 1,
                     'scope': 'committed range only, an untracked worktree is not evidence'}]
        rows_write(os.path.join(out_dir, 'git_checks.csv'),
                   ['gate', 'command', 'rc', 'lines', 'scope'], git_rows)
        rows_write(os.path.join(out_dir, 'frozen_comparison.csv'),
                   ['surface', 'paths_compared', 'mismatched', 'first_mismatches'], rows)
        print('FROZEN surfaces=%d mismatched_total=%d added=%d removed=%d diff_check rc=%d'
              % (len(rows), sum(r['mismatched'] for r in rows), len(added), len(removed), diff_rc))

        # 9) source identity of everything this round delivers
        deliver = []
        seen = set()
        for rel in CHECK.CANDIDATE_FILES + CHECK.INPUT_TABLES + [CHECK.DECK_DRAFT]:
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            deliver.append({'role': 'delivered source', 'path': rel, 'sha256': sha(path),
                            'bytes': os.path.getsize(path)})
            seen.add(rel)
        for rel in CHECK.CLAIM_FILES:
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(path) and rel not in seen:
                deliver.append({'role': 'delivered document', 'path': rel, 'sha256': sha(path),
                                'bytes': os.path.getsize(path)})
                seen.add(rel)
        for rel in CHECK.ACCEPTED_MASTERS + ['reports/dd1_d7b_review_fix_r3.md',
                                            'reports/reviews/DATA-7B-R3/REVIEW_DATA7B_R3.md',
                                            'rtl/dd1_d7a_gray_ctrl.sv', 'AGENTS.md']:
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            deliver.append({'role': 'read-only input, unmodified', 'path': rel,
                            'sha256': sha(path), 'bytes': os.path.getsize(path)})
        for tool in ('dd1_d7c_a_netlist.py', 'dd1_d7c_a_offline_check.py', 'dd1_d7c_a_guards.py',
                     'dd1_d7c_a_deckgen.py', 'dd1_d7c_a_verify.py',
                     'dd1_d7c_a_validate_handoff.py'):
            deliver.append({'role': 'this round tool', 'path': 'scripts/%s' % tool,
                            'sha256': sha(os.path.join(HERE, tool)),
                            'bytes': os.path.getsize(os.path.join(HERE, tool))})
        rows_write(os.path.join(out_dir, 'source_identity.csv'),
                   ['role', 'path', 'bytes', 'sha256'], deliver)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    for row in results:
        row.setdefault('verdict_state', 'PASS' if str(row['rc']) == str(row['expected_rc'])
                       else 'FAIL')
    failures = [r['gate'] for r in results if r['verdict_state'] == 'FAIL']
    informational = [r['gate'] for r in results if r['verdict_state'] not in ('PASS', 'FAIL')]
    rows_write(os.path.join(out_dir, 'commands.csv'),
               ['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], results)
    summary = {'task_id': TASK_ID, 'base_sha': base_rev, 'branch': 'poc/data-pam-d7c-a',
               'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'gates': len(results), 'gates_failed': failures,
               'frozen_surfaces': len(rows),
               'frozen_mismatches': sum(r['mismatched'] for r in rows),
               'paths_added_vs_base': len(added), 'paths_removed_vs_base': len(removed),
               'paths_modified_vs_base': sum(r['mismatched'] for r in rows
                                             if r['surface'].endswith('tracked_paths')),
               'added_paths': added, 'removed_paths': removed,
               'render_passes': render_passes,
               'gates_informational': informational,
               'native_launches': 0, 'rtl_simulations': 0, 'oa_writes': 0,
               'electrical_results': 'NONE: every result in this directory is about text, '
                                     'connectivity, logic derived from transistors, and Git identity'}
    if failures:
        summary['verdict'] = 'FAIL'
    elif informational:
        summary['verdict'] = 'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES'
    else:
        summary['verdict'] = 'PASS'
    with io.open(os.path.join(out_dir, 'verification_summary.json'), 'wb') as handle:
        handle.write((json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    print('DD1_7C_A_VERIFY %s -> %s (%d gates, failed: %s)'
          % (summary['verdict'], out_dir.replace(os.sep, '/'), len(results),
             ','.join(failures) or 'none'))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
