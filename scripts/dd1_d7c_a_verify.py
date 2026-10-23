#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_verify.py -- run every DATA-7C-A gate and publish the record in one small directory.

R1 revision. Offline only: subprocesses are this round's own Python tools and Git. Nothing starts a
simulator, nothing reads a credential, nothing touches a VM, and the published directory is never
overwritten.

What changed after the review:

  * tables are written with the standard CSV writer and then read back with read_table, so a row whose
    comma or quote broke the column count cannot be published at all;
  * the reviewer's own diagnostic is run twice and recorded as a gate: once against an extraction of the
    reviewed tip T, where all eight gaps must reproduce, and once against this tree, where each of the
    eight must be named. A single aggregate rc is never the evidence, so the JSON fields are read item
    by item and each item's verdict is stored;
  * three separate comparisons are reported instead of one: every B tracked path against this tip, the
    T frozen surfaces, and the T..tip path whitelist.

    python scripts/dd1_d7c_a_verify.py --out results/evidence/<run_id> [--pristine-root <T tree>]
                                       [--instrument <reviewer probe_review_gaps.py>]
"""

from __future__ import absolute_import, division, print_function

import csv
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
import dd1_d7c_a_offline_check as CHECK      # noqa: E402

TASK_ID = 'DATA-7C-A-R1'
TIP_UNDER_REVIEW = '89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79'
DEVELOPMENT_BASE = '272d6de6d2f2fc8a82d5038d73d6b3e4c656f683'
BRANCH = 'poc/data-pam-d7c-a-r1'

# §9 of the repair brief, read as exact paths. A whole directory is never called frozen when part of
# it is on the whitelist: the first version of this script swept spectre/ and reports/, counted the
# whitelisted deck draft and the two whitelisted reports as frozen-surface mismatches, and had no gate
# that used the numbers at all.
B_SURFACES = [
    ('data7b_r3_evidence_bundle', 'results/evidence/dd1_d7b_r2_r20261022_160652_e880be'),
    ('data7b_r1_evidence', 'results/evidence/dd1_d7b_r1_r20261022_123825_8e1294'),
    ('data7b_main_line_evidence', 'results/evidence/dd1_d7b_r11_main'),
    ('data7b_r3_review_documents', 'reports/reviews/DATA-7B-R3'),
    ('case_and_golden_tables_D7B', 'tests/dd1_d7b'),
    ('accepted_D7A_rtl_and_tb', 'rtl'),
    ('shared_safety_and_validation_tools', 'scripts'),
    ('accepted_netlist_masters', 'spectre'),
]
WHITELIST_MODIFIED = [
    'scripts/dd1_d7c_a_netlist.py', 'scripts/dd1_d7c_a_offline_check.py',
    'scripts/dd1_d7c_a_guards.py', 'scripts/dd1_d7c_a_verify.py',
    'scripts/dd1_d7c_a_validate_handoff.py', 'scripts/dd1_d7c_a_deckgen.py',
    'reports/dd1_d7c_a_pam_candidate.md', 'reports/dd1_d7c_a_native_test_plan.md',
    'reports/agent_handoffs/DATA-7C-A.md', 'reports/agent_handoffs/DATA-7C-A.json',
    'tests/dd1_d7c_a/native_case_plan.csv', 'spectre/dd1_d7c_a_tb_draft.scs',
]
# §9 also lists what this round may add. The evidence directory is a new unique run id, so it is
# matched by prefix; anything else that appears is a violation rather than a surprise.
ALLOWED_NEW_EXACT = ['reports/tasks/DATA-7C-A-R1.md', 'reports/dd1_d7c_a_review_fix_r1.md',
                     'tests/dd1_d7c_a/device_count_claims.csv']
ALLOWED_NEW_PREFIX = ['results/evidence/dd1_d7c_a_r1_', 'scripts/dd1_d7c_a_r1_']
FIRST_ROUND_EVIDENCE = 'results/evidence/dd1_d7c_a_r20261023_062341_cb1bd0'
FIRST_ROUND_UNTOUCHED = ['reports/tasks/DATA-7C-A.md']
# dd1_d7c_a_r1_selftest.py declares its cases in one list; this number has to agree with it, so adding
# a case on one side without the other makes the gate fail instead of quietly shrinking the suite.
SELFTEST_CASES = 9
DELIVERED = ['spectre/dd1_d7c_a_gates.scs', 'spectre/dd1_d7c_a_pam_dec.scs',
             'spectre/dd1_d7c_a_sink_unit.scs', 'spectre/dd1_d7c_a_pam_top.scs',
             CHECK.DECK_DRAFT] + CHECK.INPUT_TABLES + [
                 'scripts/dd1_d7c_a_netlist.py', 'scripts/dd1_d7c_a_offline_check.py',
                 'scripts/dd1_d7c_a_guards.py', 'scripts/dd1_d7c_a_deckgen.py',
                 'scripts/dd1_d7c_a_verify.py', 'scripts/dd1_d7c_a_validate_handoff.py',
                 'scripts/dd1_d7c_a_r1_selftest.py',
                 'reports/tasks/DATA-7C-A-R1.md', 'reports/dd1_d7c_a_pam_candidate.md',
                 'reports/dd1_d7c_a_native_test_plan.md', 'reports/dd1_d7c_a_review_fix_r1.md']
READ_ONLY_INPUTS = ['spectre/dd1_d6_inv18.scs', 'spectre/dd1_d6_bias_core.scs',
                    'spectre/dd1_d6_sink_core.scs', 'spectre/dd1_d7b_pwm_stage.scs',
                    'rtl/dd1_d7a_gray_ctrl.sv', 'reports/dd1_d7a_contract.md',
                    'reports/dd1_d7b_contract.md', 'reports/tasks/DATA-7C-A.md',
                    'reports/tasks/DATA-7B.md', 'reports/tasks/DATA-7B-R3.md',
                    'reports/agent_handoffs/DATA-7B.md',
                    'reports/reviews/DATA-7B-R3/REVIEW_DATA7B_R3.md',
                    'reports/reviews/DATA-7B-R3/source_identity.json',
                    'spec/system_requirements.md', 'AGENTS.md']
TABLE_SPECS = {
    'commands.csv': (['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], 'gate',
                     ()),
    'frozen_comparison.csv': (['comparison', 'surface', 'paths_compared', 'mismatched',
                               'first_mismatches', 'expectation', 'enforced'], 'surface',
                              ('first_mismatches',)),
    'git_checks.csv': (['gate', 'command', 'rc', 'lines', 'scope'], 'gate', ()),
    'source_identity.csv': (['role', 'path', 'bytes', 'sha256'], 'path', ()),
    'instrument_T.json': None,
    'instrument_fixed.json': None,
    'offline_checks.json': None,
    'counterexamples.json': None,
    'selftest.json': None,
    'verification_summary.json': None,
}


def git(*args):
    return subprocess.check_output(['git', '-C', ROOT] + list(args))


def run(cmd, cwd=None):
    process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = (process.communicate()[0] or '').decode('utf-8', 'replace')
    return process.returncode, text


def full_index(rev):
    raw = git('ls-tree', '-r', rev).decode('utf-8', 'replace')
    index = {}
    for line in raw.split('\n'):
        if not line.strip():
            continue
        meta, path = line.split('\t', 1)
        bits, kind, blob = meta.split()
        index[path] = (bits, kind, blob)
    return index


ENFORCED_EXPECTATIONS = ('identical', 'none_removed', 'none_modified', 'only_allowed_new')


def _row(comparison, surface, paths, base_index, head_index, expectation, kind='differs'):
    """one named question over exact paths, with what this round expects written next to the number"""
    paths = list(paths)
    allowed_new = set(ALLOWED_NEW_EXACT)

    def is_allowed(p):
        return p in allowed_new or any(p.startswith(pre) for pre in ALLOWED_NEW_PREFIX)

    if kind == 'removed':
        bad = [p for p in paths if p not in head_index]
    elif kind == 'not_allowed':
        bad = [p for p in paths if not is_allowed(p)]
    elif kind == 'listed':
        bad = list(paths)
    else:
        bad = [p for p in paths if head_index.get(p) != base_index.get(p)]
    return {'comparison': comparison, 'surface': surface, 'paths_compared': len(paths),
            'mismatched': len(bad), 'first_mismatches': '; '.join(sorted(bad)[:4]) or '-',
            'expectation': expectation,
            'enforced': 'yes' if expectation in ENFORCED_EXPECTATIONS else 'no'}


def comparisons(pristine_root):
    """three separate questions, reported apart rather than collapsed into one green mark"""
    rows = []
    b_index, head_index = full_index(DEVELOPMENT_BASE), full_index('HEAD')
    b_paths = sorted(b_index)
    for label, prefix in B_SURFACES:
        rows.append(_row('B_tracked_paths', label,
                         [p for p in b_paths if p.startswith(prefix + '/')], b_index, head_index,
                         'identical'))
    rows.append(_row('B_tracked_paths', 'every_B_tracked_path', b_paths, b_index, head_index,
                     'identical'))
    rows.append(_row('B_tracked_paths', 'paths_removed_against_B', b_paths, b_index, head_index,
                     'none_removed', kind='removed'))
    t_index = full_index(TIP_UNDER_REVIEW)
    t_paths = sorted(t_index)
    whitelisted = [p for p in t_paths if p in WHITELIST_MODIFIED]
    off_whitelist = [p for p in t_paths if p not in WHITELIST_MODIFIED]
    rows.append(_row('T_frozen_surfaces', 'four_candidate_DUT_netlists', CANDIDATE_DUT, t_index,
                     head_index, 'identical'))
    rows.append(_row('T_frozen_surfaces', 'golden_and_request_tables', GOLDEN_FROZEN, t_index,
                     head_index, 'identical'))
    rows.append(_row('T_frozen_surfaces', 'first_round_evidence_dir',
                     [p for p in t_paths if p.startswith(FIRST_ROUND_EVIDENCE + '/')], t_index,
                     head_index, 'identical'))
    rows.append(_row('T_frozen_surfaces', 'first_round_task_book', FIRST_ROUND_UNTOUCHED, t_index,
                     head_index, 'identical'))
    rows.append(_row('T_frozen_surfaces', 'read_only_inputs_named_by_the_brief', READ_ONLY_INPUTS,
                     t_index, head_index, 'identical'))
    rows.append(_row('T_frozen_surfaces', 'every_T_path_off_the_whitelist', off_whitelist, t_index,
                     head_index, 'identical'))
    rows.append(_row('T_to_tip_whitelist', 'whitelisted_paths_edited', whitelisted, t_index,
                     head_index, 'editable'))
    rows.append(_row('T_to_tip_whitelist', 'T_paths_modified_off_whitelist', off_whitelist, t_index,
                     head_index, 'none_modified'))
    rows.append(_row('T_to_tip_whitelist', 'paths_removed_against_T', t_paths, t_index, head_index,
                     'none_removed', kind='removed'))
    added_t = sorted(set(head_index) - set(t_index))
    rows.append(_row('T_to_tip_whitelist', 'paths_added_not_allowed', added_t, t_index, head_index,
                     'only_allowed_new', kind='not_allowed'))
    rows.append(_row('T_to_tip_whitelist', 'paths_added_allowed', added_t, t_index, head_index,
                     'informational', kind='listed'))
    # the reviewed tip's own byte-level identity, against a pristine extraction rather than Git alone
    dut_changed, inputs_changed, edited = [], [], []
    if pristine_root and os.path.isdir(pristine_root):
        must_stay = set(CANDIDATE_DUT) | set(GOLDEN_FROZEN) | set(READ_ONLY_INPUTS)
        for rel, state in _tree_hashes(pristine_root):
            if not state['differed']:
                continue
            if rel in must_stay:
                (dut_changed if rel in set(CANDIDATE_DUT) | set(GOLDEN_FROZEN) else inputs_changed) \
                    .append(rel)
            else:
                edited.append(rel)
    rows.append({'comparison': 'working_tree_vs_T_extraction',
                 'surface': 'candidate_DUT_and_golden_tables_must_be_identical',
                 'paths_compared': len(CANDIDATE_DUT) + len(GOLDEN_FROZEN),
                 'mismatched': len(dut_changed), 'first_mismatches': '; '.join(dut_changed[:4]) or
                 '-', 'expectation': 'identical', 'enforced': 'yes'})
    rows.append({'comparison': 'working_tree_vs_T_extraction',
                 'surface': 'read_only_inputs_must_be_identical',
                 'paths_compared': len(READ_ONLY_INPUTS), 'mismatched': len(inputs_changed),
                 'first_mismatches': '; '.join(inputs_changed[:4]) or '-',
                 'expectation': 'identical', 'enforced': 'yes'})
    rows.append({'comparison': 'working_tree_vs_T_extraction',
                 'surface': 'editable_files_actually_changed',
                 'paths_compared': len(EDITABLE_EXPECTED_TO_CHANGE),
                 'mismatched': 0, 'first_mismatches': '%d of %d edited'
                                 % (len(edited), len(EDITABLE_EXPECTED_TO_CHANGE)),
                 'expectation': 'informational', 'enforced': 'no'})
    return rows, added_t


def frozen_gate(rows, diff_rc, b_diff_rc):
    """the comparison numbers are only a gate once the expectation column decides which ones count"""
    enforced = [r for r in rows if r['enforced'] == 'yes']
    hits = [r['surface'] for r in enforced if int(r['mismatched']) > 0]
    return {'gate': 'frozen_surfaces',
            'command': 'git ls-tree -r at B, T and HEAD plus a digest walk against the T extraction; '
                       'rows marked informational are excluded from the count',
            'rc': sum(int(r['mismatched']) for r in enforced), 'expected_rc': '0',
            'verdict': 'enforced rows %d, violations %s; git diff --check T..HEAD=%d B..HEAD=%d'
                       % (len(enforced), hits or 'none', diff_rc, b_diff_rc),
            'verdict_state': 'PASS' if not hits and diff_rc == 0 and b_diff_rc == 0 else 'FAIL'}


CANDIDATE_DUT = list(CHECK.CANDIDATE_FILES)
GOLDEN_FROZEN = ['tests/dd1_d7c_a/pam_mask_golden.csv', 'tests/dd1_d7c_a/pam_request_refusal.csv']
EDITABLE_EXPECTED_TO_CHANGE = [CHECK.DECK_DRAFT] + CHECK.INPUT_TABLES[2:] + [
    'scripts/dd1_d7c_a_netlist.py', 'scripts/dd1_d7c_a_offline_check.py',
    'scripts/dd1_d7c_a_guards.py', 'scripts/dd1_d7c_a_verify.py',
    'scripts/dd1_d7c_a_validate_handoff.py', 'reports/dd1_d7c_a_pam_candidate.md',
    'reports/dd1_d7c_a_native_test_plan.md', 'reports/agent_handoffs/DATA-7C-A.md']


def _tree_hashes(pristine_root):
    for rel in CANDIDATE_DUT + GOLDEN_FROZEN + EDITABLE_EXPECTED_TO_CHANGE + READ_ONLY_INPUTS:
        old = os.path.join(pristine_root, rel.replace('/', os.sep))
        mine = os.path.join(ROOT, rel.replace('/', os.sep))
        if not (os.path.isfile(old) and os.path.isfile(mine)):
            continue
        yield rel, {'differed': CHECK.sha_file(old) != CHECK.sha_file(mine)}


def instrument_gate(name, root, script, out_json, expect_reproduced):
    """run the reviewer's own diagnostic and record every case, not just the exit code"""
    if not (script and os.path.isfile(script) and root and os.path.isdir(root)):
        return {'gate': name, 'command': 'python %s --root %s --out <json>' % (script, root),
                'rc': 'not_run', 'expected_rc': str(0 if expect_reproduced else 1),
                'verdict': 'NOT_ATTEMPTED: give --pristine-root and --instrument to replay it',
                'verdict_state': 'NOT_ATTEMPTED', 'cases': []}
    code, text = run([sys.executable, script, '--root', root, '--out', out_json])
    try:
        payload = json.loads(io.open(out_json, encoding='utf-8').read())
    except (ValueError, IOError) as error:
        return {'gate': name, 'command': 'python %s --root %s --out %s' % (script, root, out_json),
                'rc': code, 'expected_rc': str(0 if expect_reproduced else 1),
                'verdict': 'instrument produced no readable JSON: %s' % str(error)[:120],
                'verdict_state': 'FAIL', 'cases': []}
    cases = []
    for case in payload.get('cases', []):
        changed = case.get('sha256_before') != case.get('sha256_after')
        named = bool(case.get('failures'))
        cases.append({'case': case.get('case'), 'bytes_changed': changed,
                      'failures': case.get('failures'), 'reproduced': case.get('defect_reproduced')})
        if expect_reproduced:
            ok = changed and not named and case.get('defect_reproduced')
        else:
            ok = changed and named and not case.get('defect_reproduced')
        cases[-1]['meets_expectation'] = bool(ok)
    all_ok = bool(cases) and all(c['meets_expectation'] for c in cases)
    baseline_ok = payload.get('baseline_failures') == []
    return {'gate': name, 'command': 'python %s --root %s --out %s' % (script, root, out_json),
            'rc': code, 'expected_rc': str(0 if expect_reproduced else 1),
            'verdict': 'baseline_checks=%s baseline_failures=%s all_reproduced=%s cases_named=%d/%d'
                       % (payload.get('baseline_checks'), payload.get('baseline_failures') or 'none',
                          payload.get('all_defects_reproduced'),
                          sum(1 for c in cases if c['meets_expectation']), len(cases)),
            'verdict_state': 'PASS' if (all_ok and baseline_ok and
                                        (code == (0 if expect_reproduced else 1))) else 'FAIL',
            'cases': cases}


def render(root, offline_json, guards_json, plan_rows):
    offline = json.loads(io.open(offline_json, encoding='utf-8').read())
    guards = json.loads(io.open(guards_json, encoding='utf-8').read())
    lines = ['| 检查 | 结果 | 依据（截断到 180 字） |', '|---|---|---|']
    for row in offline['checks']:
        lines.append('| `%s` | %s | %s |' % (row['check'], row['result'],
                                             row['reason'][:180].replace('|', '/')))
    lines.append('')
    lines.append('合计 %d 项，失败：%s。渲染来源 `offline_checks.json`（本目录）。'
                 % (len(offline['checks']), ', '.join(offline['failures']) or 'none'))
    _splice(os.path.join(root, 'reports', 'dd1_d7c_a_pam_candidate.md'),
            '<!-- BEGIN 7C OFFLINE -->', '<!-- END 7C OFFLINE -->', lines)
    glines = ['| 反例 | 判决 | 注入文件 | 声明的新增失败集合 | 实测新增失败 | 字节改动证据 |',
              '|---|---|---|---|---|---|']
    self_files = set(r for r in CHECK.CLAIM_FILES if r.startswith('reports/'))
    for row in guards['injections']:
        if row.get('file') in self_files:
            digest = '摘要见 `counterexamples.json`（注入对象是本报告，包内不写自身摘要）'
        elif row.get('digest_before'):
            digest = '%d 行改动，改前 %s…' % (len(row.get('lines_changed', [])),
                                             row['digest_before'][:8])
        else:
            digest = '-'
        glines.append('| `%s` | %s | %s | %s | %s | %s |'
                      % (row['injection'], row['verdict'], row.get('file', '-'),
                         ','.join(row.get('expected', [])) or '(empty)',
                         ','.join(row.get('found', [])) or '-', digest))
    glines.append('')
    glines.append('基线（未注入）失败集合：%s；规则：`found == sorted(expected)` 且 expected 非空。'
                  'E09/E17/E19 一类注入对象就是承载本表的文件或表本身，其改前改后摘要只出现在 '
                  '`counterexamples.json`：把摘要写进被注入的文件会让每次渲染都不同。'
                  % (', '.join(guards['baseline_failures']) or 'none'))
    _splice(os.path.join(root, 'reports', 'dd1_d7c_a_pam_candidate.md'),
            '<!-- BEGIN 7C GUARDS -->', '<!-- END 7C GUARDS -->', glines)
    plines = ['| 用例 | 类别 | 码与使能 | 观察节点 | 测量区间 | 参考定义 | 失败条件 | 分段/配对 | '
              '细化对象 | 额度 | 结果 |',
              '|---|---|---|---|---|---|---|---|---|---:|---|']
    for row in plan_rows:
        plines.append('| `%s` | %s | %s / DATA_EN=%s V | %s | %s | %s | %s | %s | %s | %s | %s |'
                      % (row['case_id'], row['class'], row['code'], row['data_en_level_V'],
                         row['observe_nodes'], row['measure_interval'], row['reference_definition'],
                         row['failure_condition'],
                         row['segments'] if not row['paired_case'] else 'paired with ' +
                         row['paired_case'], row['refine_only'] or '-', row['draft_launch_units'],
                         row['result']))
    plines.append('')
    plines.append('渲染来源：`tests/dd1_d7c_a/native_case_plan.csv`，%d 例，草案额度合计 %d；'
                  '探针方向与取号在每一行相同且先于任何运行声明：`%s`。'
                  % (len(plan_rows), sum(int(r['draft_launch_units']) for r in plan_rows),
                     plan_rows[0]['probe_orientation']))
    _splice(os.path.join(root, 'reports', 'dd1_d7c_a_native_test_plan.md'),
            '<!-- BEGIN 7C PLAN -->', '<!-- END 7C PLAN -->', plines)


def _splice(path, begin, end, lines):
    if not os.path.isfile(path):
        return
    with io.open(path, encoding='utf-8') as handle:
        body = handle.read()
    if begin not in body or end not in body:
        raise SystemExit('RENDER_REFUSED marker %s missing in %s' % (begin, path))
    head, rest = body.split(begin, 1)
    _old, tail = rest.split(end, 1)
    with io.open(path, 'wb') as handle:
        handle.write((head + begin + '\n' + '\n'.join(lines) + '\n' + end + tail).encode('utf-8'))


def render_fix(root, results, rows, instrument_rows, selftest_rows):
    """three machine-written sections in the fix report: gates, instrument, frozen surfaces"""
    lines = ['| 门 | 命令 | rc | 期望 | 判决 | 依据 |', '|---|---|---|---|---|---|']
    for row in results:
        lines.append('| `%s` | `%s` | %s | %s | %s | %s |'
                     % (row['gate'], row['command'][:70], row['rc'], row['expected_rc'],
                        row['verdict_state'], str(row['verdict'])[:150].replace('|', '/')))
    lines.append('')
    lines.append('每条命令的完整文本与原始尾行见 `commands.csv`（本目录）；`INFORMATIONAL_NOT_PASS` '
                 '不是失败也不是通过，它是"这台工具的范围不支持这个结论"的记录。')
    _splice(os.path.join(root, 'reports', 'dd1_d7c_a_review_fix_r1.md'),
            '<!-- BEGIN R1 GATES -->', '<!-- END R1 GATES -->', lines)
    if selftest_rows:
        slines = ['| 自测例 | 判决 | 声明的期望 | 实测观察 |', '|---|---|---|---|']
        for row in selftest_rows['results']:
            slines.append('| `%s` | %s | %s | %s |'
                          % (row['case'], row['state'],
                             str(row['expectation'])[:90].replace('|', '/'),
                             str(row['observed'])[:150].replace('|', '/')))
        slines.append('')
        slines.append('`scripts/dd1_d7c_a_r1_selftest.py` 的用例是**这一轮验收工具自己的反例**：'
                      '冻结面闸在四种真违规下各必须 FAIL、在只有 informational 计数时必须 PASS、'
                      '掺入一条 enforced 违规时必须再次 FAIL；严格读表器对七种破损形状逐一拒收，'
                      '并且把 T 已交付的三张坏 CSV 从 Git 取回后逐一拒收、把形状本来就合法的 '
                      '`frozen_comparison.csv` 接受。合计 %d 例，失败：%s。'
                      % (selftest_rows['cases'], ', '.join(selftest_rows['failures']) or 'none'))
        _splice(os.path.join(root, 'reports', 'dd1_d7c_a_review_fix_r1.md'),
                '<!-- BEGIN R1 SELFTEST -->', '<!-- END R1 SELFTEST -->', slines)
    ilines = ['| 诊断 | 对 T（必须复现） | 对修复后字节（必须具名拒收） | 修复后新增失败 | 字节确变 |',
              '|---|---|---|---|---|']
    by_t = dict((c['case'], c) for c in instrument_rows['on_T'])
    by_f = dict((c['case'], c) for c in instrument_rows['on_fixed'])
    for name in list(by_t):
        t_row, f_row = by_t.get(name, {}), by_f.get(name, {})
        ilines.append('| `%s` | reproduced=%s | reproduced=%s | %s | %s |'
                      % (name, t_row.get('reproduced'), f_row.get('reproduced'),
                         ','.join(f_row.get('failures', [])) or '(none)',
                         'yes' if (t_row.get('bytes_changed') and f_row.get('bytes_changed')) else 'NO'))
    ilines.append('')
    ilines.append('同一件未修改的审核方仪器（`reviewer/probe_review_gaps.py`，摘要与包内 '
                  '`MANIFEST.csv` 相同）分别对 T 的只读提取与对修复后字节运行：'
                  '前者 `all_defects_reproduced=true`、后者 `false`，逐项失败集合见上；'
                  '两次运行的 `baseline_checks` 与 `baseline_failures` 记在 '
                  '`instrument_T.json` / `instrument_fixed.json`。逐项读，不看聚合 rc。')
    _splice(os.path.join(root, 'reports', 'dd1_d7c_a_review_fix_r1.md'),
            '<!-- BEGIN R1 INSTRUMENT -->', '<!-- END R1 INSTRUMENT -->', ilines)
    flines = ['| 比较 | 面 | 路径数 | 计数 | 前若干路径 | 本轮期望 | 计入闸 |',
              '|---|---|---:|---:|---|---|---|']
    for row in rows:
        flines.append('| %s | `%s` | %s | %s | %s | `%s` | %s |'
                      % (row['comparison'], row['surface'], row['paths_compared'],
                         row['mismatched'], str(row['first_mismatches'])[:110].replace('|', '/'),
                         row['expectation'], row['enforced']))
    flines.append('')
    flines.append('三件事分开核，并且每一行都写明本轮的期望与是否计入闸：B 的全部 tracked 路径与本 '
                  'tip 的 (mode, type, blob) 对照（期望 identical/none_removed）；T 的冻结面按 §9 的'
                  '确切路径列出（四个候选 DUT、黄金与请求表、首轮证据目录与任务书、只读输入、以及'
                  '"白名单之外的每一条 T 路径"）；T..tip 的白名单单独回答"改的是不是白名单内的、有没有'
                  '删、新增的是不是允许的"。上一版本把 `spectre/`、`reports/` 整目录当冻结面扫，于是'
                  '白名单内的 `dd1_d7c_a_tb_draft.scs` 与两份白名单报告被记成 11 条"失配"，而这张表'
                  '当时没有任何闸使用它。现在 `whitelisted_paths_edited`、`paths_added_allowed` 与'
                  '`editable_files_actually_changed` 三行明确是 informational（计入闸=no），其余 enforced '
                  '行的计数由 `frozen_surfaces` 闸求和并要求为 0。')
    _splice(os.path.join(root, 'reports', 'dd1_d7c_a_review_fix_r1.md'),
            '<!-- BEGIN R1 FROZEN -->', '<!-- END R1 FROZEN -->', flines)


def main(argv):
    out_dir, pristine, script = '', '', ''
    if '--out' in argv:
        out_dir = os.path.abspath(argv[argv.index('--out') + 1])
    if '--pristine-root' in argv:
        pristine = os.path.abspath(argv[argv.index('--pristine-root') + 1])
    if '--instrument' in argv:
        script = os.path.abspath(argv[argv.index('--instrument') + 1])
    if not out_dir:
        out_dir = os.path.join(ROOT, 'results', 'evidence', '%s_r%s_%06x' % (
            TASK_ID.lower().replace('-', '_'), time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
            int(hashlib.sha256(os.urandom(8)).hexdigest()[:6], 16)))
    if os.path.isdir(out_dir):
        raise SystemExit('DD1_7C_A_R1_VERIFY_REFUSED %s already exists; published records are never '
                         'overwritten, choose a new run id' % out_dir)
    os.makedirs(out_dir)
    results = []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-a-verify-')
    try:
        first = instrument_gate('reviewer_instrument_on_T', pristine, script,
                                os.path.join(out_dir, 'instrument_T.json'), True)
        results.append(first)
        print('GATE %-32s %s %s' % (first['gate'], first['verdict_state'], first['verdict'][:90]))

        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_offline_check.py'),
                          '--json', os.path.join(out_dir, 'offline_checks.json')])
        results.append(_gate('offline_checks', 'python dd1_d7c_a_offline_check.py --json <out>',
                             code, '0', text))
        print('GATE %-32s %s %s' % ('offline_checks', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))

        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_guards.py'),
                          '--json', os.path.join(out_dir, 'counterexamples.json')])
        results.append(_gate('counterexamples', 'python dd1_d7c_a_guards.py --json <out>', code, '0',
                             text))
        print('GATE %-32s %s %s' % ('counterexamples', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))

        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_r1_selftest.py'),
                          '--json', os.path.join(out_dir, 'selftest.json')])
        row = _gate('record_tool_selftest', 'python dd1_d7c_a_r1_selftest.py --json <out>', code,
                    '0', text)
        # rc alone is not the evidence: the JSON has to carry every declared case and no failure
        try:
            selftest = json.loads(io.open(os.path.join(out_dir, 'selftest.json'),
                                          encoding='utf-8').read())
            row['verdict'] = 'cases=%d verdict=%s failures=%s | %s' % (
                selftest['cases'], selftest['verdict'], selftest['failures'] or 'none',
                row['verdict'])
            if selftest['failures'] or selftest['verdict'] != 'PASS' or \
                    selftest['cases'] != SELFTEST_CASES:
                row['verdict_state'] = 'FAIL'
        except (ValueError, KeyError, IOError) as error:
            row['verdict'] = 'selftest JSON unreadable: %s' % str(error)[:120]
            row['verdict_state'] = 'FAIL'
        results.append(row)
        print('GATE %-32s %s %s' % ('record_tool_selftest', row['verdict_state'],
                                    row['verdict'][:90]))

        handoff = os.path.join(ROOT, 'reports', 'agent_handoffs', 'DATA-7C-A.json')
        handoff_payload = {}
        if os.path.isfile(handoff):
            handoff_payload = json.loads(io.open(handoff, encoding='utf-8').read())
        if str(handoff_payload.get('task_id', '')).endswith('-R1'):
            code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_validate_handoff.py'),
                              handoff])
            results.append(_gate('handoff_structure', 'python dd1_d7c_a_validate_handoff.py '
                                 'reports/agent_handoffs/DATA-7C-A.json', code, '0', text))
        else:
            # this record is one of the inputs the next handoff revision cites, so the handoff on disk
            # still describes the first round. Calling that a failure would be wrong and calling it a
            # pass would be worse, so the skip and its reason are recorded.
            results.append({'gate': 'handoff_structure',
                            'command': 'python dd1_d7c_a_validate_handoff.py '
                                       'reports/agent_handoffs/DATA-7C-A.json',
                            'rc': 'skipped',
                            'expected_rc': '0 once the handoff carries task_id DATA-7C-A-R1',
                            'verdict': 'SKIPPED at the record commit: the handoff on disk still '
                                       'describes task_id=%s' % handoff_payload.get('task_id', 'absent'),
                            'verdict_state': 'SKIPPED_WITH_REASON'})
        print('GATE %-32s %s %s' % ('handoff_structure', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:80]))

        probe_dir = os.path.join(scratch, 'deckprobe')
        os.makedirs(probe_dir)
        with io.open(os.path.join(probe_dir, 'sentinel.txt'), 'wb') as handle:
            handle.write(b'sentinel\n')
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_deckgen.py'), '--probe',
                          probe_dir], cwd=scratch)
        results.append(_gate('native_entry_refused', 'python dd1_d7c_a_deckgen.py --probe <temp>',
                             code, '0', text))
        print('GATE %-32s %s %s' % ('native_entry_refused', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:80]))

        code, text = run([sys.executable, os.path.join(HERE, 'provenance_check.py')])
        results.append(_gate('provenance', 'python provenance_check.py', code, '0', text))
        print('GATE %-32s %s %s' % ('provenance', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:80]))

        base_tree = os.path.join(scratch, 'base')
        os.makedirs(base_tree)
        archive = subprocess.Popen(['git', '-C', ROOT, 'archive', DEVELOPMENT_BASE, 'scripts',
                                    'tests', 'rtl', 'spectre', 'reports'], stdout=subprocess.PIPE)
        tar = subprocess.Popen(['tar', '-x', '-C', base_tree], stdin=archive.stdout)
        archive.stdout.close()
        if tar.wait() != 0:
            raise SystemExit('BASE_EXTRACTION_FAILED')
        rc_base, text_base = run([sys.executable, os.path.join(base_tree, 'scripts',
                                                              'netlist_stats.py')], cwd=base_tree)
        rc_head, text_head = run([sys.executable, os.path.join(HERE, 'netlist_stats.py')])
        problems_base = sorted(set(re.findall(r'PROBLEM (\S+ claims \d+ devices)', text_base)))
        problems_head = sorted(set(re.findall(r'PROBLEM (\S+ claims \d+ devices)', text_head)))
        new_problems = sorted(set(problems_head) - set(problems_base))
        results.append({'gate': 'netlist_stats_scope_limit', 'command':
                        'python netlist_stats.py at the B extraction and at this tip',
                        'rc': '%d/%d' % (rc_base, rc_head),
                        'expected_rc': 'INFORMATIONAL: single-cell scope, not a PASS',
                        'verdict': 'base problems %d %s; tip problems %d; new %d %s'
                                   % (len(problems_base), problems_base or 'none', len(problems_head),
                                      len(new_problems), new_problems[:4]),
                        'verdict_state': 'INFORMATIONAL_NOT_PASS'})
        print('GATE %-32s %s (base=%d tip=%d)' % ('netlist_stats_scope',
                                                  'INFORMATIONAL', len(problems_base),
                                                  len(problems_head)))

        code, text = run([sys.executable, os.path.join(HERE, 'precommit_safety_check.py'),
                          '--mode', 'history'])
        results.append(_gate('history_safety', 'python precommit_safety_check.py --mode history',
                             code, '0', text))
        print('GATE %-32s %s %s' % ('history_safety', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:60]))

        second = instrument_gate('reviewer_instrument_on_fixed_bytes', ROOT, script,
                                 os.path.join(out_dir, 'instrument_fixed.json'), False)
        results.append(second)
        print('GATE %-32s %s %s' % (second['gate'], second['verdict_state'],
                                    second['verdict'][:90]))

        # the frozen comparisons and the two committed-range whitespace checks are inputs to the
        # rendered report, so they are computed before rendering and refreshed inside the loop
        diff_rc = subprocess.call(['git', '-C', ROOT, 'diff', '--check',
                                   '%s..HEAD' % TIP_UNDER_REVIEW])
        b_diff_rc = subprocess.call(['git', '-C', ROOT, 'diff', '--check',
                                     '%s..HEAD' % DEVELOPMENT_BASE])
        rows, added_t = comparisons(pristine)
        results.append(frozen_gate(rows, diff_rc, b_diff_rc))
        print('GATE %-32s %s %s' % ('frozen_surfaces', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        selftest_rows = {}
        selftest_path = os.path.join(out_dir, 'selftest.json')
        if os.path.isfile(selftest_path):
            selftest_rows = json.loads(io.open(selftest_path, encoding='utf-8').read())

        # render, then re-run both gates and require the render to be a fixed point
        plan_rows = CHECK.read_table(os.path.join(ROOT, 'tests', 'dd1_d7c_a',
                                                  'native_case_plan.csv'),
                                     ['case_id', 'class', 'purpose', 'code', 'data_en_level_V',
                                      'observe_nodes', 'measure_interval', 'reference_definition',
                                      'failure_condition', 'segments', 'paired_case', 'refine_only',
                                      'probe_orientation', 'sign_convention', 'draft_launch_units',
                                      'result'], 'case_id',
                                     optional=('segments', 'paired_case', 'refine_only'))
        passes = []
        for attempt in (1, 2, 3):
            render(ROOT, os.path.join(out_dir, 'offline_checks.json'),
                   os.path.join(out_dir, 'counterexamples.json'), plan_rows)
            render_fix(ROOT, results, rows,
                       {'on_T': first.get('cases', []), 'on_fixed': second.get('cases', [])},
                       selftest_rows)
            watched = ('dd1_d7c_a_pam_candidate.md', 'dd1_d7c_a_native_test_plan.md',
                       'dd1_d7c_a_review_fix_r1.md')
            before = [CHECK.sha_file(os.path.join(ROOT, 'reports', w)) for w in watched]
            rc2, _ = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_offline_check.py'),
                          '--json', os.path.join(out_dir, 'offline_checks.json')])
            rc3, _ = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_guards.py'),
                          '--json', os.path.join(out_dir, 'counterexamples.json')])
            render(ROOT, os.path.join(out_dir, 'offline_checks.json'),
                   os.path.join(out_dir, 'counterexamples.json'), plan_rows)
            render_fix(ROOT, results, rows,
                       {'on_T': first.get('cases', []), 'on_fixed': second.get('cases', [])},
                       selftest_rows)
            after = [CHECK.sha_file(os.path.join(ROOT, 'reports', w)) for w in watched]
            passes.append({'attempt': attempt, 'offline_rc': rc2, 'guards_rc': rc3,
                           'reports_stable': before == after})
            print('RENDER pass %d offline=%s guards=%s stable=%s'
                  % (attempt, rc2, rc3, before == after))
            if before == after and rc2 == 0 and rc3 == 0:
                break
        stable = passes[-1]['reports_stable'] and passes[-1]['offline_rc'] == 0 and \
            passes[-1]['guards_rc'] == 0
        results.append({'gate': 'render_fixed_point', 'command': 're-run both gates after rendering, '
                        'render again and compare the two report digests', 'rc': len(passes),
                        'expected_rc': 'last pass stable with both gates rc=0',
                        'verdict': 'passes %s' % passes,
                        'verdict_state': 'PASS' if stable else 'FAIL'})
        print('GATE %-32s %s' % ('render_fixed_point', results[-1]['verdict_state']))

        CHECK.rows_write(os.path.join(out_dir, 'frozen_comparison.csv'),
                         ['comparison', 'surface', 'paths_compared', 'mismatched',
                          'first_mismatches', 'expectation', 'enforced'], rows)
        CHECK.rows_write(os.path.join(out_dir, 'git_checks.csv'),
                         ['gate', 'command', 'rc', 'lines', 'scope'],
                         [{'gate': 'diff_check_T_to_HEAD',
                           'command': 'git diff --check %s..HEAD' % TIP_UNDER_REVIEW,
                           'rc': diff_rc, 'lines': 'see rc',
                           'scope': 'committed range over the reviewed tip only'},
                          {'gate': 'diff_check_B_to_HEAD',
                           'command': 'git diff --check %s..HEAD' % DEVELOPMENT_BASE,
                           'rc': b_diff_rc, 'lines': 'see rc',
                           'scope': 'committed range over the development base as well'}])
        enforced = [r for r in rows if r['enforced'] == 'yes']
        removed_row = [r for r in rows if r['surface'] == 'paths_removed_against_T']
        print('FROZEN rows=%d enforced=%d enforced_mismatches=%d informational_rows=%d '
              'added_after_T=%d removed_vs_T=%d diff T=%d B=%d'
              % (len(rows), len(enforced), sum(int(r['mismatched']) for r in enforced),
                 len(rows) - len(enforced), len(added_t),
                 removed_row[0]['mismatched'] if removed_row else -1, diff_rc, b_diff_rc))

        identity = []
        for rel in DELIVERED:
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(path):
                identity.append({'role': 'delivered this round', 'path': rel,
                                 'bytes': os.path.getsize(path), 'sha256': CHECK.sha_file(path)})
        for rel in ('reports/agent_handoffs/DATA-7C-A.md', 'reports/agent_handoffs/DATA-7C-A.json'):
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(path):
                identity.append({'role': 'handoff, rewritten after this record', 'path': rel,
                                 'bytes': os.path.getsize(path), 'sha256': CHECK.sha_file(path)})
        for rel in READ_ONLY_INPUTS:
            path = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(path):
                identity.append({'role': 'read-only input', 'path': rel,
                                 'bytes': os.path.getsize(path), 'sha256': CHECK.sha_file(path)})
        listed = set(row['path'] for row in identity)
        for tool in ('dd1_d7c_a_netlist.py', 'dd1_d7c_a_offline_check.py', 'dd1_d7c_a_guards.py',
                     'dd1_d7c_a_deckgen.py', 'dd1_d7c_a_verify.py', 'dd1_d7c_a_validate_handoff.py'):
            rel = 'scripts/%s' % tool
            if rel in listed:
                continue                      # one row per path, or the unique-key gate refuses it
            path = os.path.join(HERE, tool)
            identity.append({'role': 'this round tool', 'path': rel,
                             'bytes': os.path.getsize(path), 'sha256': CHECK.sha_file(path)})
            listed.add(rel)
        CHECK.rows_write(os.path.join(out_dir, 'source_identity.csv'),
                         ['role', 'path', 'bytes', 'sha256'], identity)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # commands.csv last, then every published table is read back strictly before the verdict
    CHECK.rows_write(os.path.join(out_dir, 'commands.csv'),
                     ['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], results)
    read_back = []
    for name, spec in TABLE_SPECS.items():
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            continue
        if spec is None:
            with io.open(path, encoding='utf-8') as handle:
                json.load(handle)
            read_back.append({'file': name, 'result': 'JSON parses', 'rows': ''})
            continue
        header, key, optional = spec
        parsed = CHECK.read_table(path, header, key, optional=optional)
        read_back.append({'file': name, 'result': 'columns and keys verified',
                          'rows': len(parsed)})
    enforced = [r for r in rows if r['enforced'] == 'yes']
    failures = [r['gate'] for r in results if r['verdict_state'] == 'FAIL']
    informational = [r['gate'] for r in results if r['verdict_state'] not in ('PASS', 'FAIL')]
    summary = {'task_id': TASK_ID, 'reviewed_tip': TIP_UNDER_REVIEW, 'development_base':
               DEVELOPMENT_BASE, 'branch': BRANCH,
               'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'gates': len(results), 'gates_failed': failures,
               'gates_informational': informational,
               'csv_read_back': read_back,
               'frozen_rows': len(rows), 'frozen_rows_enforced': len(enforced),
               'frozen_rows_informational': len(rows) - len(enforced),
               'frozen_enforced_mismatches': sum(int(r['mismatched']) for r in enforced),
               'frozen_violating_surfaces': [r['surface'] for r in enforced
                                             if int(r['mismatched']) > 0],
               'paths_added_after_T': len(added_t), 'added_paths_after_T': added_t,
               'native_launches': 0, 'rtl_simulations': 0, 'oa_writes': 0,
               'electrical_results': 'NONE: every result here is about text, connectivity, logic '
                                     'derived from transistors, table schemas and Git identity'}
    summary['verdict'] = 'FAIL' if failures else (
        'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES' if informational else 'PASS')
    with io.open(os.path.join(out_dir, 'verification_summary.json'), 'wb') as handle:
        handle.write((json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    print('DD1_7C_A_R1_VERIFY %s -> %s (%d gates, failed: %s, csv read back: %d)'
          % (summary['verdict'], out_dir.replace(os.sep, '/'), len(results),
             ','.join(failures) or 'none', len(read_back)))
    return 1 if failures else 0


def _gate(name, command, code, expected, text):
    verdict = text.strip().split('\n')[-1][:200] if text.strip() else ''
    return {'gate': name, 'command': command, 'rc': code, 'expected_rc': expected,
            'verdict': verdict, 'verdict_state': 'PASS' if str(code) == str(expected) else 'FAIL'}


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
