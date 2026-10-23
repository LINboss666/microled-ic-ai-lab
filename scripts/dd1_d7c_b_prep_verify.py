#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_verify.py -- run this round's gates and publish one small offline evidence record.

DATA-7C-B-PREP section 10. Everything here is text, arithmetic and Git reads: the record proves that
the contract renders the schedule, the schedule renders the decks, the decks and the schedule agree
byte for byte, the synthetic measurement cases refuse the counterfeit shapes, the four candidate DUT
netlists and every other pre-existing path are unchanged from the delivered R2 bytes, and both
reviewer instruments still answer the same way on this tree as they did on R2. Nothing launches a
simulator, and the published directory is never overwritten.

The semantic layer is the one the previous round shipped (`dd1_d7c_a_r2_record_check.py`): the same
rules judge this record before it is written and again after it is on disk, so a row whose rc
contradicts its own expectation, a missing mandatory gate, an enforced frozen row with a violation, a
stale identity digest or a summary that washes a failed sub-check is refused here too.

    python scripts/dd1_d7c_b_prep_verify.py --out results/evidence/dd1_d7c_b_prep_<run_id>
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
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_offline_check as CHECK            # noqa: E402
import dd1_d7c_a_r2_record_check as RECORD         # noqa: E402
import dd1_d7c_b_prep_cases as CASES               # noqa: E402
import dd1_d7c_b_prep_contract as CONTRACT         # noqa: E402
import dd1_d7c_b_prep_deckgen as DECKGEN           # noqa: E402
import dd1_d7c_b_prep_schedule as SCHEDULE         # noqa: E402

TASK_ID = 'DATA-7C-B-PREP'
BASE_R2 = '3e4703f1763223024f442c0826e95055782bca13'
REVIEWED_T = '89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79'
DEVELOPMENT_BASE = '272d6de6d2f2fc8a82d5038d73d6b3e4c656f683'
BRANCH = 'poc/data-pam-d7c-b-prep'
NEW_PREFIXES = ('scripts/dd1_d7c_b_prep_', 'tests/dd1_d7c_b_prep/', 'spectre/dd1_d7c_b_prep/',
                'results/evidence/dd1_d7c_b_prep_')
NEW_EXACT = ['reports/tasks/DATA-7C-B-PREP.md', 'reports/dd1_d7c_b_prep_contract.md',
             'reports/dd1_d7c_b_prep_report.md', 'reports/agent_handoffs/DATA-7C-B-PREP.md',
             'reports/agent_handoffs/DATA-7C-B-PREP.json']
CANDIDATE_DUT = CONTRACT.FROZEN_CANDIDATE_DUT
SHARED_TOOLS = ['scripts/dd1_d7c_a_netlist.py', 'scripts/dd1_d7c_a_offline_check.py',
                'scripts/dd1_d7c_a_guards.py', 'scripts/dd1_d7c_a_verify.py',
                'scripts/dd1_d7c_a_deckgen.py', 'scripts/dd1_d7c_a_validate_handoff.py',
                'scripts/dd1_d7c_a_r1_selftest.py', 'scripts/dd1_d7c_a_r2_plan.py',
                'scripts/dd1_d7c_a_r2_record_check.py', 'scripts/dd1_d7c_a_r2_record_probes.py',
                'scripts/dd1_d7c_a_r2_sign_check.py', 'scripts/precommit_safety_check.py',
                'scripts/netlist_stats.py', 'scripts/provenance_check.py']
PREVIOUS_RECORDS = ['results/evidence/dd1_d7c_a_r20261023_062341_cb1bd0',
                    'results/evidence/dd1_d7c_a_r1_20261023_093439_d160e5',
                    'results/evidence/dd1_d7c_a_r1_20261023_094649_c80c08',
                    'results/evidence/dd1_d7c_a_r2_20261023_134109_00c811',
                    'results/evidence/dd1_d7c_a_r2_20261023_135600_10e307']
REVIEW_DIR = os.path.join(ROOT, 'review', 'MicroLED_DATA7C_A_R1_Review_20261023', 'reviewer')
OPEN_BY_DESIGN = 'published_record_reader_accepts_rc99_as_PASS'
TABLE_SPECS = {
    'commands.csv': (['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'], 'gate', ()),
    'frozen_comparison.csv': (['comparison', 'surface', 'paths_compared', 'mismatched',
                               'first_mismatches', 'expectation', 'enforced'], 'surface',
                              ('first_mismatches',)),
    'git_checks.csv': (['gate', 'command', 'rc', 'lines', 'scope'], 'gate', ()),
    'source_identity.csv': (['role', 'path', 'bytes', 'sha256'], 'path', ()),
    'offline_checks.json': None, 'counterexamples.json': None, 'selftest.json': None,
    'synthetic_cases.json': None, 'instrument_T.json': None, 'instrument_fixed.json': None,
    'instrument_remaining_H.json': None, 'instrument_remaining_fixed.json': None,
    'verification_summary.json': None,
}


def git(*args):
    return subprocess.check_output(['git', '-C', ROOT] + list(args))


def run(cmd, cwd=None):
    process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = (process.communicate()[0] or '').decode('utf-8', 'replace')
    return process.returncode, text


def _gate(name, command, code, expected, text):
    verdict = text.strip().split('\n')[-1][:220] if text.strip() else ''
    return {'gate': name, 'command': command, 'rc': code, 'expected_rc': expected,
            'verdict': verdict, 'verdict_state': 'PASS' if str(code) == str(expected) else 'FAIL'}


def extract(rev, directory):
    archive = subprocess.Popen(['git', '-C', ROOT, 'archive', rev], stdout=subprocess.PIPE)
    tar = subprocess.Popen(['tar', '-x', '-C', directory], stdin=archive.stdout)
    archive.stdout.close()
    return tar.wait() == 0 and archive.wait() == 0


def blob_index(rev):
    raw = git('ls-tree', '-r', '-z', rev).decode('utf-8', 'replace')
    index = {}
    for line in raw.split('\0'):
        if not line.strip():
            continue
        meta, path = line.split('\t', 1)
        mode, kind, blob = meta.split()
        index[path] = (mode, kind, blob)
    return index


def _compare(name, surface, paths, base_index, tip_index, expectation):
    """one frozen row: (mode, type, blob) equality over an explicit path list, never a directory sweep"""
    enforced = expectation in RECORD.VERIFY.ENFORCED_EXPECTATIONS
    mismatched = []
    for rel in paths:
        if rel not in base_index:
            mismatched.append('%s absent at the base revision' % rel)
        elif rel not in tip_index:
            mismatched.append('%s removed' % rel)
        elif base_index[rel] != tip_index[rel]:
            mismatched.append('%s %s->%s' % (rel, base_index[rel][2][:8], tip_index[rel][2][:8]))
    return {'comparison': name, 'surface': surface, 'paths_compared': len(paths),
            'mismatched': len(mismatched), 'first_mismatches': ';'.join(mismatched[:3]),
            'expectation': expectation, 'enforced': 'yes' if enforced else 'no'}


def comparisons(tip):
    base = blob_index(BASE_R2)
    head = blob_index(tip)
    r2_paths = sorted(base)
    added = sorted(set(head) - set(base))
    removed = sorted(set(base) - set(head))
    modified = sorted(p for p in r2_paths if p in head and base[p] != head[p])
    unexpected_new = [p for p in added if not p.startswith(NEW_PREFIXES) and p not in NEW_EXACT]
    rows = [
        _compare('this_round', 'every_R2_tracked_path_vs_tip', r2_paths, base, head, 'identical'),
        _compare('this_round', 'four_candidate_DUT_netlists', CANDIDATE_DUT, base, head, 'identical'),
        _compare('this_round', 'shared_tools_and_safety_rules', SHARED_TOOLS, base, head, 'identical'),
        _compare('this_round', 'previous_round_record_dirs',
                 [p for p in r2_paths if any(p.startswith(d + '/') for d in PREVIOUS_RECORDS)],
                 base, head, 'identical'),
        {'comparison': 'this_round', 'surface': 'paths_added_this_round',
         'paths_compared': len(added), 'mismatched': len(unexpected_new),
         'first_mismatches': ';'.join(unexpected_new[:3]),
         'expectation': 'only_allowed_new', 'enforced': 'yes'},
        {'comparison': 'this_round', 'surface': 'paths_removed_or_modified_vs_R2',
         'paths_compared': len(removed) + len(modified), 'mismatched': len(removed) + len(modified),
         'first_mismatches': ';'.join((removed + modified)[:3]),
         'expectation': 'none_removed', 'enforced': 'yes'},
        {'comparison': 'this_round', 'surface': 'added_paths_listed_for_the_reviewer',
         'paths_compared': len(added), 'mismatched': 0,
         'first_mismatches': ';'.join(added[:3]), 'expectation': 'informational_listing',
         'enforced': 'no'},
    ]
    counts = {'added': added, 'removed': removed, 'modified': modified, 'base': len(r2_paths),
              'tip': len(head)}
    return rows, counts


def instrument_gate(name, script, root, out_json, expect, key, open_allowed=()):
    """run a reviewer instrument unmodified and read it item by item, never off the aggregate rc"""
    shown = '<extraction of %s>' % ('T' if root.endswith('T') else
                                    'R2' if root.endswith('R2') else 'this tree')
    command = 'python %s --root %s --out <json>' % (os.path.relpath(script, ROOT), shown)
    if not (os.path.isfile(script) and os.path.isdir(root)):
        return {'gate': name, 'command': command, 'rc': 'not_run', 'expected_rc': str(expect),
                'verdict': 'NOT_ATTEMPTED: the instrument or its target tree is absent',
                'verdict_state': 'NOT_ATTEMPTED', 'cases': []}, {}
    code, _text = run([sys.executable, script, '--root', root, '--out', out_json])
    normalised = _lf_in_place(out_json)
    try:
        payload = json.loads(io.open(out_json, encoding='utf-8').read())
    except (ValueError, IOError) as error:
        return {'gate': name, 'command': command, 'rc': code, 'expected_rc': str(expect),
                'verdict': 'no readable JSON: %s' % str(error)[:120], 'verdict_state': 'FAIL',
                'cases': []}, {}
    items = payload.get(key, [])
    cases, bad = [], []
    for case in items:
        reproduced = case.get('reproduced', case.get('defect_reproduced'))
        failures = case.get('failures') or []
        if expect == 0:
            meets = bool(reproduced)
        else:
            meets = (not reproduced) or (case.get('case') in open_allowed)
        cases.append({'case': case.get('case'), 'reproduced': reproduced, 'failures': failures,
                      'checks': case.get('checks'), 'exception': case.get('exception'),
                      'sha256_before': case.get('sha256_before'),
                      'sha256_after': case.get('sha256_after'), 'meets_expectation': meets})
        if not meets or case.get('exception'):
            bad.append(case.get('case'))
    still_open = [c['case'] for c in cases if c['reproduced']]
    baseline_ok = payload.get('baseline_failures') == []
    state = 'PASS' if (code == expect and not bad and baseline_ok and cases and
                       payload.get('spectre_launches', 0) == 0) else 'FAIL'
    return {'gate': name, 'command': 'python %s --root %s --out %s'
            % (os.path.relpath(script, ROOT), shown, os.path.relpath(out_json, ROOT)),
            'rc': code, 'expected_rc': str(expect),
            'verdict': 'baseline_checks=%s baseline_failures=%s items=%d/%d expected_rc=%s %s%s'
                       % (payload.get('baseline_checks'), payload.get('baseline_failures') or 'none',
                          len(cases) - len(bad), len(cases), expect,
                          'all_gaps_reproduced=%s' % payload.get('all_gaps_reproduced', 'n/a')
                          if key == 'results' else 'all_defects_reproduced=%s'
                          % payload.get('all_defects_reproduced', 'n/a'),
                          '; still reporting reproduced: %s' % ','.join(still_open)
                          if still_open else ''),
            'verdict_state': state, 'instrument_output_newlines': normalised, 'cases': cases}, payload


def _lf_in_place(path):
    """the instruments write platform newlines; the repository stores LF, so normalise only after
    proving the parsed object is identical, and say so in the record instead of editing silently"""
    with io.open(path, 'rb') as handle:
        raw = handle.read()
    if b'\r\n' not in raw:
        return {'crlf_before': False, 'bytes': len(raw)}
    before = json.loads(raw.decode('utf-8'))
    body = raw.replace(b'\r\n', b'\n')
    if json.loads(body.decode('utf-8')) != before:
        raise SystemExit('NORMALISATION_REFUSED %s would change a value' % path)
    with io.open(path, 'wb') as handle:
        handle.write(body)
    return {'crlf_before': True, 'bytes': len(body), 'digest_before': hashlib.sha256(raw).hexdigest(),
            'digest_after': hashlib.sha256(body).hexdigest()}


def replay_in_extraction(directory):
    plan = [('contract_check', 'dd1_d7c_b_prep_contract.py', ('--check',), (0,)),
            ('schedule_check', 'dd1_d7c_b_prep_schedule.py', ('--check',), (0,)),
            ('deck_check', 'dd1_d7c_b_prep_deckgen.py', ('--check',), (0,)),
            ('synthetic_cases', 'dd1_d7c_b_prep_cases.py', (), (0,)),
            ('offline', 'dd1_d7c_a_offline_check.py', ('--json', 'out.json'), (0,)),
            ('guards', 'dd1_d7c_a_guards.py', ('--json', 'out.json'), (0,)),
            ('r2_plan_check', 'dd1_d7c_a_r2_plan.py', ('--check',), (0,)),
            ('sign_check', 'dd1_d7c_a_r2_sign_check.py', (), (0,)),
            ('record_probes', 'dd1_d7c_a_r2_record_probes.py', (), (0,)),
            ('record_selftest', 'dd1_d7c_a_r1_selftest.py', ('--json', 'self.json'), (0, 2))]
    out = []
    for suite, script, args, accepted in plan:
        cmd = [sys.executable, os.path.join(directory, 'scripts', script)] + \
              [os.path.join(directory, a) if a.endswith('.json') and '/' not in a else a
               for a in args]
        code, text = run(cmd, cwd=directory)
        tail = text.strip().split('\n')[-1][:110] if text.strip() else ''
        out.append({'suite': suite, 'rc': code, 'accepted': code in accepted, 'note': tail})
    return out


def handoff_check():
    """the new handoff is judged by this round, against its own documented structure and its own bytes"""
    path = os.path.join(ROOT, 'reports', 'agent_handoffs', 'DATA-7C-B-PREP.json')
    problems = []
    if not os.path.isfile(path):
        return ['DATA-7C-B-PREP.json is not written yet']
    payload = json.loads(io.open(path, encoding='utf-8').read())
    for key in ('schema_version', 'task_id', 'base_sha', 'branch', 'repository', 'scope',
                'contract_state', 'source_identity', 'deck_inventory', 'measurement_evidence',
                'launch_plan', 'costs', 'boundaries', 'not_run', 'stop_reason',
                'known_limitations', 'remote_readback', 'differences_vs_R2'):
        if key not in payload:
            problems.append('missing field %s' % key)
    if payload.get('task_id') != TASK_ID:
        problems.append('task_id is %r, not %r' % (payload.get('task_id'), TASK_ID))
    if payload.get('contract_state') != CONTRACT.CONTRACT_STATE:
        problems.append('the handoff moved the contract state off PROPOSED_FOR_REVIEW')
    if payload.get('base_sha') != BASE_R2:
        problems.append('base_sha is not the delivered R2 commit')
    for key in ('new_spectre_launches', 'new_rtl_simulations', 'new_oa_writes'):
        value = (payload.get('costs') or {}).get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            problems.append('costs.%s must be an integer 0, found %r' % (key, value))
    for entry in (payload.get('source_identity') or {}).get('delivered', []) + \
            (payload.get('source_identity') or {}).get('read_only_inputs', []):
        target = os.path.join(ROOT, str(entry.get('path', '')).replace('/', os.sep))
        if not os.path.isfile(target):
            problems.append('source_identity names %s which is not on disk' % entry.get('path'))
            continue
        if entry.get('sha256') != CHECK.sha_file(target):
            problems.append('%s digest in the handoff does not match the bytes on disk'
                            % entry.get('path'))
        if int(entry.get('bytes', -1)) != os.path.getsize(target):
            problems.append('%s byte count in the handoff does not match the bytes on disk'
                            % entry.get('path'))
    blob = json.dumps(payload, ensure_ascii=False)
    for forbidden in ('PAM_IMPLEMENTED=PASS', 'CURRENT_MEASURED=PASS', 'MEASURED_PASS',
                      'CONTRACT_STATE=USER_APPROVED'):
        if forbidden in blob:
            problems.append('the handoff contains the forbidden claim %r' % forbidden)
    if not (payload.get('known_limitations') and payload.get('differences_vs_R2')):
        problems.append('a preparation round that lists no limitation and no difference has not '
                        'looked at what it changed')
    for key, value in (payload.get('not_run') or {}).items():
        if value not in ('NOT_RUN', 'NOT_VERIFIED', 'NOT_DEFINED', 'NOT_FROZEN', 'NOT_AUTHORISED'):
            problems.append('not_run.%s must be a marker, found %r' % (key, value))
    return problems


def _splice(path, begin, end, lines):
    if not os.path.isfile(path):
        return False
    with io.open(path, encoding='utf-8', newline='') as handle:
        body = handle.read()
    if begin not in body or end not in body:
        return False
    head, rest = body.split(begin, 1)
    _old, tail = rest.split(end, 1)
    updated = head + begin + '\n' + '\n'.join(lines).strip('\n') + '\n' + end + tail
    if updated.endswith('\n\n'):
        updated = updated.rstrip('\n') + '\n'
    with io.open(path, 'wb') as handle:
        handle.write(updated.encode('utf-8'))
    return True


def render_report(out_dir, results, rows, git_rows, counts, schedule_rows, case_rows, tip):
    """four machine-written tables in the preparation report; the prose above them stays hand-written"""
    report = os.path.join(ROOT, 'reports', 'dd1_d7c_b_prep_report.md')
    lines = ['| 门 | 命令 | rc | 期望 | 判决 | 依据 |', '|---|---|---|---|---|---|']
    for row in results:
        lines.append('| `%s` | `%s` | %s | %s | %s | %s |'
                     % (row['gate'], row['command'][:72].replace('|', '/'), row['rc'],
                        row['expected_rc'], row['verdict_state'],
                        str(row['verdict'])[:150].replace('|', '/')))
    lines.append('')
    lines.append('渲染发生在 `%s` 之后、`record_semantics` 与 `published_record_recheck` 判定之前；'
                  '最后两门的最终值与每条命令的完整文本在 `commands.csv`。本表不含本轮记录的摘要，'
                  '摘要写在本目录的 `verification_summary.json`（它写于本文件之后，故不进摘要）。'
                  % tip[:12])
    _splice(report, '<!-- BEGIN 7CB GATES -->', '<!-- END 7CB GATES -->', lines)
    dlines = ['| 用例 | 类别 | 码 | 使能形态 | 平台 / 窗 / 尾 / 漏流子窗 (ns) | 换码 | stop | maxstep '
              '| 配对 | 进程 DUT+preflight | 结果 |',
              '|---|---|---|---|---|---|---:|---:|---|---|---|']
    for row in schedule_rows:
        dlines.append('| `%s` | %s | `%s` | %s | %s / %s / %s / %s | %s | %s | %s | %s | %s+%s | %s |'
                      % (row['case_id'], row['class'], row['pam_code'], row['data_en_form'],
                         row['platform_start_ns'], row['window_start_ns'], row['tail_start_ns'],
                         row['leak_last100_start_ns'], row['code_change_ns'], row['stop_ns'],
                         row['maxstep_ns'], row['paired_case'] or '-',
                         row['launch_processes_dut'], row['launch_processes_preflight'],
                         row['result']))
    dlines.append('')
    dlines.append('文本由 `spectre/dd1_d7c_b_prep/%s.scs` 承载，逐例一份；`--to <scratch>` 重新生成一次'
                  '并与交付字节比较（门 `deck_regenerated_from_sources`）。' % 'DC-000')
    _splice(report, '<!-- BEGIN 7CB DECKS -->', '<!-- END 7CB DECKS -->', dlines)
    clines = ['| 例 | 类型 | 判决 | 观察到的依据 | 说明 |', '|---|---|---|---|---|']
    for row in case_rows:
        clines.append('| `%s` | %s | %s | %s | %s |'
                      % (row['case'], row['kind'], row['verdict'],
                         (row['detail'] or '; '.join(row['problems']))[:120].replace('|', '/'),
                         row['meaning'][:110].replace('|', '/')))
    clines.append('')
    clines.append('每一例都是手算合成样点（`SYNTHETIC_NOT_MEASURED`）：验的是测量算法，不是电路性能；'
                  '负例先证明注入的事实存在，再要求规则点名拒收，空期望对空结果不算检出。')
    _splice(report, '<!-- BEGIN 7CB CASES -->', '<!-- END 7CB CASES -->', clines)
    flines = ['| 比较 | 面 | 路径数 | 计数 | 前若干 | 期望 | 计入闸 |',
              '|---|---|---:|---:|---|---|---|']
    for row in rows:
        flines.append('| %s | `%s` | %s | %s | %s | `%s` | %s |'
                      % (row['comparison'], row['surface'], row['paths_compared'], row['mismatched'],
                         str(row['first_mismatches'])[:90].replace('|', '/'), row['expectation'],
                         row['enforced']))
    flines.append('')
    for row in git_rows:
        flines.append('* `%s` → rc=%s，%s，%s' % (row['command'], row['rc'], row['lines'],
                                                  row['scope']))
    flines.append('')
    flines.append('R2 的全部 %d 条跟踪路径逐条比 (mode, type, blob)；四份候选 DUT、共享工具、安全闸脚本'
                  '与全部旧证据目录各成一行为 enforced；本轮新增 %d 条路径由 §9 的白名单前缀允许，'
                  '删除与修改计数为 0。' % (counts['base'], len(counts['added'])))
    _splice(report, '<!-- BEGIN 7CB FROZEN -->', '<!-- END 7CB FROZEN -->', flines)
    return report


def main(argv):
    out_dir = ''
    if '--out' in argv:
        out_dir = os.path.abspath(argv[argv.index('--out') + 1])
    if not out_dir:
        out_dir = os.path.join(ROOT, 'results', 'evidence', '%s_r%s_%06x' % (
            TASK_ID.lower().replace('-', '_'), time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
            int(hashlib.sha256(os.urandom(8)).hexdigest()[:6], 16)))
    if os.path.isdir(out_dir):
        raise SystemExit('D7C_B_PREP_VERIFY_REFUSED %s already exists; published records are never '
                         'overwritten, choose a new run id' % out_dir)
    tip = git('rev-parse', 'HEAD').decode().strip()
    os.makedirs(out_dir)
    results = []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-b-')
    try:
        t_dir = os.path.join(scratch, 'T')
        r2_dir = os.path.join(scratch, 'R2')
        os.makedirs(t_dir)
        os.makedirs(r2_dir)
        extract(REVIEWED_T, t_dir)
        extract(BASE_R2, r2_dir)
        gap_script = os.path.join(REVIEW_DIR, 'probe_review_gaps.py')
        remain_script = os.path.join(REVIEW_DIR, 'probe_r1_remaining.py')
        first, payload_t = instrument_gate('reviewer_instrument_on_T', gap_script, t_dir,
                                           os.path.join(out_dir, 'instrument_T.json'), 0, 'cases')
        results.append(first)
        second, payload_f = instrument_gate('reviewer_instrument_on_fixed_bytes', gap_script, ROOT,
                                           os.path.join(out_dir, 'instrument_fixed.json'), 1, 'cases')
        results.append(second)
        third, _ = instrument_gate('reviewer_remaining_on_H', remain_script, r2_dir,
                                   os.path.join(out_dir, 'instrument_remaining_H.json'), 0, 'results')
        results.append(third)
        fourth, _ = instrument_gate('reviewer_remaining_on_fixed_bytes', remain_script, ROOT,
                                    os.path.join(out_dir, 'instrument_remaining_fixed.json'), 1,
                                    'results', open_allowed=(OPEN_BY_DESIGN,))
        results.append(fourth)
        for row in results:
            print('GATE %-38s %s %s' % (row['gate'], row['verdict_state'], row['verdict'][:90]))

        for name, script, args, expected in (
                ('offline_checks', 'dd1_d7c_a_offline_check.py',
                 ('--json', 'offline_checks.json'), '0'),
                ('counterexamples', 'dd1_d7c_a_guards.py',
                 ('--json', 'counterexamples.json'), '0'),
                ('record_tool_selftest', 'dd1_d7c_a_r1_selftest.py',
                 ('--json', 'selftest.json'), '0')):
            code, text = run([sys.executable, os.path.join(HERE, script)] +
                             [os.path.join(out_dir, a) if a.endswith('.json') and '/' not in a
                              else a for a in args])
            results.append(_gate(name, 'python %s --json <out>' % script, code, expected, text))
            print('GATE %-38s %s %s' % (name, results[-1]['verdict_state'],
                                        results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_cases.py'),
                          '--json', os.path.join(out_dir, 'synthetic_cases.json')])
        results.append(_gate('synthetic_measure_cases',
                             'python dd1_d7c_b_prep_cases.py --json <out>', code, '0', text))
        print('GATE %-38s %s %s' % ('synthetic_measure_cases', results[-1]['verdict_state'],
                                     results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_contract.py'),
                          '--check'])
        results.append(_gate('contract_selfcheck', 'python dd1_d7c_b_prep_contract.py --check',
                             code, '0', text))
        print('GATE %-38s %s %s' % ('contract_selfcheck', results[-1]['verdict_state'],
                                     results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_schedule.py'),
                          '--check'])
        results.append(_gate('schedule_check', 'python dd1_d7c_b_prep_schedule.py --check', code,
                             '0', text))
        print('GATE %-38s %s %s' % ('schedule_check', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_deckgen.py'),
                          '--check'])
        results.append(_gate('deck_check', 'python dd1_d7c_b_prep_deckgen.py --check', code, '0',
                             text))
        print('GATE %-38s %s %s' % ('deck_check', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_b_prep_deckgen.py'),
                          '--to', os.path.join(scratch, 'regen')])
        results.append(_gate('deck_regenerated_from_sources',
                             'python dd1_d7c_b_prep_deckgen.py --to <scratch>', code, '0', text))
        print('GATE %-38s %s %s' % ('deck_regenerated_from_sources', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))

        directory = os.path.join(scratch, 'extract')
        os.makedirs(directory)
        extracted = extract(tip, directory)
        outcomes = replay_in_extraction(directory) if extracted else []
        bad = [o for o in outcomes if not o['accepted']]
        results.append({'gate': 'fresh_extraction_replay',
                        'command': 'git archive %s | tar -x, then run the suites there'
                                   % tip[:12],
                        'rc': len(bad), 'expected_rc': '0',
                        'verdict': ('; '.join('%s rc=%s %s' % (o['suite'], o['rc'], o['note'])
                                               for o in outcomes)[:400] if extracted
                                    else 'EXTRACTION_FAILED'),
                        'verdict_state': 'PASS' if extracted and not bad else 'FAIL'})
        print('GATE %-38s %s %s' % ('fresh_extraction_replay', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        previous_problems, previous_facts = RECORD.check_record(
            os.path.join(r2_dir, 'results', 'evidence', 'dd1_d7c_a_r1_20261023_094649_c80c08'),
            BASE_R2, source_root=r2_dir)
        offenders = sorted(set(str(p).split(' ')[0] for p in previous_problems))
        unexpected = [o for o in offenders if o not in
                      ('reports/dd1_d7c_a_review_fix_r1.md', 'reports/agent_handoffs/DATA-7C-A.md',
                       'reports/agent_handoffs/DATA-7C-A.json')]
        results.append({'gate': 'previous_record_reader_finds_its_own_staleness',
                        'command': 'python dd1_d7c_a_r2_record_check.py --record '
                                   'results/evidence/dd1_d7c_a_r1_20261023_094649_c80c08 '
                                   '--git-ref %s --source-root <that extraction>' % BASE_R2[:12],
                        'rc': len(unexpected), 'expected_rc': '0',
                        'verdict': '%d semantic problems over %d paths (%s); paths outside the three '
                                   'R1 disclosed: %d' % (len(previous_problems), len(offenders),
                                                         ','.join(o.rsplit('/', 1)[-1]
                                                                  for o in offenders),
                                                         len(unexpected)),
                        'verdict_state': 'PASS' if previous_problems and not unexpected else 'FAIL'})
        print('GATE %-38s %s %s' % ('previous_record_reader_finds_its_own_staleness',
                                    results[-1]['verdict_state'], results[-1]['verdict'][:110]))

        problems = handoff_check()
        results.append({'gate': 'handoff_structure',
                        'command': 'python dd1_d7c_b_prep_verify.py --handoff-check (in process)',
                        'rc': len(problems), 'expected_rc': '0',
                        'verdict': '; '.join(problems[:3]) if problems else
                                   'fields, digests against disk, zero costs, markers and forbidden '
                                   'claims all checked',
                        'verdict_state': 'PASS' if not problems else 'FAIL'})
        print('GATE %-38s %s %s' % ('handoff_structure', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        probe_dir = os.path.join(scratch, 'deckprobe')
        os.makedirs(probe_dir)
        with io.open(os.path.join(probe_dir, 'placeholder.txt'), 'wb') as handle:
            handle.write(b'probe content\n')
        code, text = run([sys.executable, os.path.join(HERE, 'dd1_d7c_a_deckgen.py'), '--probe',
                          probe_dir], cwd=scratch)
        results.append(_gate('native_entry_refused', 'python dd1_d7c_a_deckgen.py --probe <temp>',
                             code, '0', text))
        print('GATE %-38s %s %s' % ('native_entry_refused', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(ROOT, 'scripts', 'provenance_check.py')])
        results.append(_gate('provenance', 'python scripts/provenance_check.py', code, '0', text))
        print('GATE %-38s %s %s' % ('provenance', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(ROOT, 'scripts', 'netlist_stats.py'),
                          '--check'])
        results.append({'gate': 'netlist_stats_scope', 'command':
                        'python scripts/netlist_stats.py --check', 'rc': code,
                        'expected_rc': 'INFORMATIONAL: this tool counts MOS lines, it does not judge '
                                       'this round', 'verdict': text.strip().split('\n')[-1][:200],
                        'verdict_state': 'INFORMATIONAL_NOT_PASS'})
        print('GATE %-38s %s %s' % ('netlist_stats_scope', 'INFORMATIONAL_NOT_PASS',
                                    results[-1]['verdict'][:90]))
        code, text = run([sys.executable, os.path.join(ROOT, 'scripts', 'precommit_safety_check.py'),
                          '--mode', 'history'])
        results.append(_gate('history_safety', 'python scripts/precommit_safety_check.py '
                             '--mode history', code, '0', text))
        print('GATE %-38s %s %s' % ('history_safety', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:90]))

        git_rows = []
        for label, other in (('diff_check_R2_to_HEAD', BASE_R2), ('diff_check_T_to_HEAD', REVIEWED_T),
                             ('diff_check_base_to_HEAD', DEVELOPMENT_BASE)):
            process = subprocess.Popen(['git', '-C', ROOT, 'diff', '--check', '%s..HEAD' % other],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            body = (process.communicate()[0] or '').decode('utf-8', 'replace')
            git_rows.append({'gate': label,
                             'command': 'git diff --check %s..HEAD' % other,
                             'rc': process.returncode, 'lines': len([b for b in body.split('\n')
                                                                     if b.strip()]),
                             'scope': 'committed range from %s to HEAD at %s'
                                      % (other[:12],
                                         time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))})
        rows, counts = comparisons(tip)
        CHECK.rows_write(os.path.join(out_dir, 'frozen_comparison.csv'), RECORD.FROZEN_HEADER, rows)
        CHECK.rows_write(os.path.join(out_dir, 'git_checks.csv'), RECORD.GIT_HEADER, git_rows)
        enforced = [r for r in rows if r['enforced'] == 'yes']
        violations = sum(int(r['mismatched']) for r in enforced)
        diff_rc = max(int(r['rc']) for r in git_rows)
        results.append({'gate': 'frozen_surfaces', 'command': 'git ls-tree -r, blob and mode '
                        'comparison over explicit path lists, plus git diff --check on HEAD ranges',
                        'rc': violations + diff_rc, 'expected_rc': '0',
                        'verdict': 'enforced rows %d, violations %d, informational rows %d, added %d, '
                                   'removed %d, modified %d; git diff --check R2..HEAD=%s T..HEAD=%s '
                                   'base..HEAD=%s'
                                   % (len(enforced), violations, len(rows) - len(enforced),
                                      len(counts['added']), len(counts['removed']),
                                      len(counts['modified']), git_rows[0]['rc'], git_rows[1]['rc'],
                                      git_rows[2]['rc']),
                        'verdict_state': 'PASS' if violations == 0 and diff_rc == 0 else 'FAIL'})
        print('GATE %-38s %s %s' % ('frozen_surfaces', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        case_rows = json.loads(io.open(os.path.join(out_dir, 'synthetic_cases.json'),
                                       encoding='utf-8').read())['results']
        before = io.open(os.path.join(ROOT, 'reports', 'dd1_d7c_b_prep_report.md'),
                         encoding='utf-8', newline='').read()
        render_report(out_dir, results, rows, git_rows, counts, SCHEDULE.read_delivered()[0],
                      case_rows, tip)
        middle = io.open(os.path.join(ROOT, 'reports', 'dd1_d7c_b_prep_report.md'),
                         encoding='utf-8', newline='').read()
        render_report(out_dir, results, rows, git_rows, counts, SCHEDULE.read_delivered()[0],
                      case_rows, tip)
        after = io.open(os.path.join(ROOT, 'reports', 'dd1_d7c_b_prep_report.md'),
                        encoding='utf-8', newline='').read()
        results.append({'gate': 'report_render_fixed_point',
                        'command': 'python dd1_d7c_b_prep_verify.py (renders the four tables twice '
                                   'and compares)', 'rc': 0 if middle == after else 1,
                        'expected_rc': '0',
                        'verdict': 'first render changed the report by %d bytes, the second changed it '
                                   'by %d bytes; the tables are a function of the sources, not of the '
                                   'moment' % (len(middle) - len(before), len(after) - len(middle)),
                        'verdict_state': 'PASS' if middle == after else 'FAIL'})
        print('GATE %-38s %s %s' % ('report_render_fixed_point', results[-1]['verdict_state'],
                                    results[-1]['verdict'][:110]))

        identity = []
        for rel in sorted(counts['added']) + [p for p in sorted(blob_index(tip))
                                              if p.startswith('spectre/dd1_d7c_a_')]:
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'delivered this round' if rel in counts['added']
                                 else 'frozen candidate netlist',
                                 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': CHECK.sha_file(target)})
        for rel in ('reports/agent_handoffs/DATA-7C-B-PREP.md',
                    'reports/agent_handoffs/DATA-7C-B-PREP.json'):
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'handoff, written before this record and committed with it',
                                 'path': rel, 'bytes': os.path.getsize(target),
                                 'sha256': CHECK.sha_file(target)})
        for rel in [p for p in sorted(blob_index(BASE_R2))
                    if p.startswith(('spectre/dd1_d6_', 'spectre/current_probe_syntax.scs',
                                      'rtl/dd1_d7a_', 'reports/dd1_d7a_contract.md',
                                      'reports/dd1_d7b_contract.md', 'spec/', 'AGENTS.md',
                                      'reports/tasks/DATA-7C-A'))]:
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'read-only input', 'path': rel,
                                 'bytes': os.path.getsize(target), 'sha256': CHECK.sha_file(target)})
        for rel in SHARED_TOOLS + ['scripts/dd1_d7c_b_prep_contract.py',
                                   'scripts/dd1_d7c_b_prep_schedule.py',
                                   'scripts/dd1_d7c_b_prep_deckgen.py',
                                   'scripts/dd1_d7c_b_prep_measure.py',
                                   'scripts/dd1_d7c_b_prep_cases.py',
                                   'scripts/dd1_d7c_b_prep_verify.py']:
            if any(row['path'] == rel for row in identity):
                continue
            target = os.path.join(ROOT, rel.replace('/', os.sep))
            if os.path.isfile(target):
                identity.append({'role': 'tool this round reads or reuses', 'path': rel,
                                 'bytes': os.path.getsize(target), 'sha256': CHECK.sha_file(target)})
        pending = [dict(row) for row in results] + [
            {'gate': 'record_semantics', 'command': 'python scripts/dd1_d7c_a_r2_record_check.py '
             '--record <this directory>', 'rc': 0, 'expected_rc': '0', 'verdict_state': 'PASS',
             'verdict': 'provisional: the semantic layer below decides this row'}]
        problems, facts = RECORD.check_rows(pending, rows, git_rows, identity, out_dir,
                                            summary_exists=False)
        verdict_state = 'PASS' if not problems else 'FAIL'
        pending[-1].update({'verdict_state': verdict_state, 'rc': len(problems),
                            'verdict': 'rules over the gate rows, the frozen table, the git ranges, '
                                       'the source identity and every sub-result JSON; %s'
                                       % ('no semantic problem' if not problems else
                                          '; '.join(problems[:3]))})
        results.extend(pending[len(results):])
        print('GATE %-38s %s %s' % ('record_semantics', verdict_state,
                                    pending[-1]['verdict'][:110]))
        CHECK.rows_write(os.path.join(out_dir, 'source_identity.csv'), RECORD.IDENTITY_HEADER,
                         identity)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    CHECK.rows_write(os.path.join(out_dir, 'commands.csv'), RECORD.COMMANDS_HEADER, results)
    read_back, crlf_found = [], []
    for name, spec in sorted(TABLE_SPECS.items()):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            continue
        with io.open(path, 'rb') as handle:
            if b'\r' in handle.read():
                crlf_found.append(name)
        if spec is None:
            json.loads(io.open(path, encoding='utf-8').read())
            read_back.append({'file': name, 'result': 'JSON parses, no CR byte', 'rows': ''})
            continue
        header, key, optional = spec
        parsed = CHECK.read_table(path, header, key, optional=optional)
        read_back.append({'file': name, 'result': 'columns and keys verified, no CR byte',
                          'rows': len(parsed)})
    enforced = [r for r in rows if r['enforced'] == 'yes']
    failures = [r['gate'] for r in results if r['verdict_state'] == 'FAIL']
    informational = [r['gate'] for r in results if r['verdict_state'] not in ('PASS', 'FAIL')]
    summary = {'task_id': TASK_ID, 'base_r2': BASE_R2, 'reviewed_tip_T': REVIEWED_T,
               'development_base': DEVELOPMENT_BASE, 'branch': BRANCH, 'tip': tip,
               'contract_state': CONTRACT.CONTRACT_STATE,
               'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'gates': len(results), 'gates_failed': failures,
               'gates_informational': informational, 'csv_read_back': read_back,
               'published_files_with_cr': crlf_found,
               'frozen_rows': len(rows), 'frozen_rows_enforced': len(enforced),
               'frozen_rows_informational': len(rows) - len(enforced),
               'frozen_enforced_mismatches': sum(int(r['mismatched']) for r in enforced),
               'frozen_violating_surfaces': [r['surface'] for r in enforced
                                             if int(r['mismatched']) > 0],
               'paths_added_after_R2': counts['added'], 'paths_removed_after_R2': counts['removed'],
               'paths_modified_after_R2': counts['modified'],
               'decks': len(DECKGEN.render_all()), 'deck_directory': DECKGEN.DECK_DIR,
               'cases_in_schedule': len(SCHEDULE.read_delivered()[0]),
               'synthetic_cases': len(CASES.run()),
               'native_launches': 0, 'rtl_simulations': 0, 'oa_writes': 0,
               'electrical_results': 'NONE: every number in this record is text, arithmetic, table '
                                     'shape or Git identity; the synthetic measurement results are '
                                     'labelled SYNTHETIC_NOT_MEASURED'}
    recheck, recheck_facts = RECORD.check_record(out_dir, BASE_R2, summary_exists=False)
    summary['published_record_recheck'] = {
        'problems': recheck[:12], 'facts': recheck_facts,
        'verdict': 'PASS' if not recheck else 'FAIL',
        'note': 'judged over the bytes as published, before this summary line existed; a reviewer '
                're-runs it with: python scripts/dd1_d7c_a_r2_record_check.py --record '
                'results/evidence/<run_id> --git-ref <tip> --source-root <worktree>'}
    print('GATE %-38s %s %s' % ('published_record_recheck',
                                summary['published_record_recheck']['verdict'],
                                (recheck[:1] or ['no semantic problem'])[0][:110]))
    summary['verdict'] = 'FAIL' if (failures or recheck) else (
        'PASS_WITH_DISCLOSED_INFORMATIONAL_GATES' if informational else 'PASS')
    with io.open(os.path.join(out_dir, 'verification_summary.json'), 'wb') as handle:
        handle.write((json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    print('D7C_B_PREP_VERIFY %s -> %s (%d gates, failed: %s, read back: %d)'
          % (summary['verdict'], out_dir.replace(os.sep, '/'), len(results),
             ','.join(failures) or 'none', len(read_back)))
    return 1 if (failures or recheck) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
