#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DATA-7B-R2: one machine-generated result set that every R2 document has to agree with

TASK_DATA7B_R2 section 6 refuses a report that repeats numbers by hand: the old round's failure
count, this round's bundle name, its row and file counts, its source digests and its electrical
summaries all have to come out of one fixed result set. This script reads a published bundle, runs
the re-checker over it exactly once, and writes what it finds; the repair report and the handoff are
generated from that file, so a document that disagrees with the bytes fails a gate rather than
passing a reader.

Nothing here starts a simulator, opens a socket or writes inside the bundle: the only output is the
result file and the standard output.

usage: python scripts/dd1_d7b_r2_result_set.py <published bundle> [--out <file>]
"""
from __future__ import print_function

import argparse
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_evidence_check as EC                       # noqa: E402
import dd1_d7b_measure as MS                              # noqa: E402

TOOLS = ('dd1_d7b_run.py', 'dd1_d7b_measure.py', 'dd1_d7b_evidence_check.py')


def u(text):
    return text if isinstance(text, str) else text.decode('utf-8', 'replace')


def sha(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()


def digest(path):
    return sha(path)


def tally(rows, key):
    out = {}
    for r in rows:
        out[r.get(key, '')] = out.get(r.get(key, ''), 0) + 1
    return out


def total_counted(reconcile):
    """the historical launch count as the reconcile table's own TOTAL row states it"""
    for r in reconcile:
        if r.get('task_root_dir') == 'TOTAL':
            return EC.integer_value(r.get('processes_counted_against_ceiling'))
    return None


def collect(ev_dir):
    B = EC.Bundle(ev_dir)
    C = EC.Checks()
    EC.build_checks(ev_dir, C)
    rows = list(C.rows)
    failures = sorted(set(r[0] for r in rows if r[1] == 'FAIL'))
    files = EC.bundle_files(ev_dir)
    idx = B.idx
    # the index has one row per shard part, but "is this series the accepted bundle's bytes" is a
    # statement about a series, so the tally is taken over each base once and split by kind
    by_base = {}
    for r in idx:
        by_base[r['base']] = r['series_vs_accepted_bundle']
    series = {}
    kind = {}
    for base, verdict in by_base.items():
        series[verdict] = series.get(verdict, 0) + 1
        key = ('charge' if base.startswith('charge_') else
               'edge' if base.startswith('edge_') else 'other')
        kind.setdefault(key, {})
        kind[key][verdict] = kind[key].get(verdict, 0) + 1
    settle = tally(B.cases, 'settled_status')
    off = tally(B.cases, 'off_status')
    verdict = tally(B.cases, 'verdict')
    cal = dict((r['quantity'], r) for r in B.cal)
    ical = EC.num((cal.get('Ical_A') or {}).get('value_A'))
    errs = [abs(EC.num(r['charge_error_LSB'])) for r in B.cases
            if r['role'] not in ('calibration', 'negative_wiring')
            and EC.num(r.get('charge_error_LSB')) is not None]
    out = {
        'bundle': os.path.basename(ev_dir).replace(os.sep, '/'),
        'bundle_rel': os.path.relpath(ev_dir, PROJ).replace(os.sep, '/'),
        'run_id': B.env.get('run_id'),
        'mode': B.env.get('mode'),
        'base_sha': B.env.get('base_sha'),
        'repair_task_id': 'DATA-7B-R2',
        'file_count': len(files),
        'total_bytes': sum(os.path.getsize(os.path.join(ev_dir, p)) for p in files),
        'checks_run': len(rows),
        'checks_passed': len([r for r in rows if r[1] == 'PASS']),
        'failures': failures,
        'account_rows': len(B.account),
        'account_states': tally(B.account, 'state'),
        'account_occupied': len([r for r in B.account if r['state'] in
                                 ('CONFIRMED', 'COMPLETED', 'UNCERTAIN', 'REQUESTED')]),
        'authorised_ceiling': EC.CEILING_GRANTED,
        'taskbook_ceiling': EC.CEILING_TASKBOOK,
        'granted_extra': EC.CEILING_GRANTED - EC.CEILING_TASKBOOK,
        'historical_launches': total_counted(B.reconcile),
        'case_rows': len(B.cases),
        'case_verdicts': verdict,
        'settled_states': settle,
        'off_states': off,
        'charge_series_vs_accepted': series,
        'series_count': len(by_base),
        'index_rows': len(idx),
        'series_by_kind': kind,
        'ical_A': ical,
        'max_abs_charge_error_LSB': max(errs) if errs else None,
        'delivered_traces': len([r for r in EC.read_rows(
            os.path.join(ev_dir, 'rtl_reverify.csv'))]) if os.path.isfile(
            os.path.join(ev_dir, 'rtl_reverify.csv')) else 0,
        'delivered_vcd_bytes': sum(os.path.getsize(os.path.join(ev_dir, p)) for p in files
                                   if p.endswith('.vcd.txt')),
        'cal_slices': {k: (EC.integer_value((v or {}).get('band_samples')),
                           (v or {}).get('slice_series'))
                       for k, v in ((q, cal.get(q)) for q in
                                    ('Ical_A', 'OFF_baseline_max_abs_A',
                                     'CAL_tail_max_abs_A'))},
        'gate_records': len(EC.read_rows(os.path.join(ev_dir, 'gate_records.csv')))
                        if os.path.isfile(os.path.join(ev_dir, 'gate_records.csv')) else 0,
        'tool_sha256': dict((t, digest(os.path.join(HERE, t))) for t in TOOLS),
        'measurement_source_sha256': B.env.get('measurement_source_sha256'),
        'evidence_check_source_sha256': B.env.get('evidence_check_source_sha256'),
        'shift_ns': B.env.get('shift_ns'),
        'tail_ns': B.env.get('tail_ns'),
        'new_launch_grant': B.env.get('new_launch_grant'),
        'spectre_launches_this_pass': B.env.get('new_spectre_launches_this_pass'),
    }
    return out


MARK_BEGIN = '<!-- BEGIN R2 RESULT SET -->'
MARK_END = '<!-- END R2 RESULT SET -->'


def table(pairs):
    out = ['| 项 | 本轮值 |', '|---|---|']
    for name, value in pairs:
        out.append('| %s | %s |' % (name, value))
    return '\n'.join(out)


def flat(d):
    return ' / '.join('%s=%s' % kv for kv in sorted(d.items())) if d else '-'


def section(got, gates):
    kind = got['series_by_kind']
    rows = [('包目录', '`%s`' % got['bundle_rel']),
            ('run_id / mode', '`%s` / `%s`' % (got['run_id'], got['mode'])),
            ('本轮基线 H', '`%s`' % got['base_sha']),
            ('文件数 / 字节数', '%d / %d B（上限 33,554,432 B）'
             % (got['file_count'], got['total_bytes'])),
            ('复核项', '%d 项，PASS %d，FAIL %d'
             % (got['checks_run'], got['checks_passed'], got['checks_run'] - got['checks_passed'])),
            ('失败清单', ' '.join('`%s`' % f for f in got['failures']) or '-'),
            ('账户行数 / 组成', '%d 行：%s' % (got['account_rows'], flat(got['account_states']))),
            ('占额度 / 固定授权 / 超', '%d / %d（任务书 %d + 追加 %d）/ +%d 历史超支'
             % (got['account_occupied'], got['authorised_ceiling'], got['taskbook_ceiling'],
                got['granted_extra'], got['historical_launches'] - got['authorised_ceiling'])),
            ('本轮新增成本', 'Spectre %d；RTL 仿真 0；OA 写入 0；追加授权额度 %d'
             % (got['spectre_launches_this_pass'], got['new_launch_grant'])),
            ('case 行 / 判决', '%d 行：%s' % (got['case_rows'], flat(got['case_verdicts']))),
            ('settled 分布', flat(got['settled_states'])),
            ('off 分布', flat(got['off_states'])),
            ('Ical', '%.16g A（内部样点 %d，切片 `%s`）'
             % (got['ical_A'], got['cal_slices']['Ical_A'][0], got['cal_slices']['Ical_A'][1])),
            ('CAL 两段切片', 'OFF %d 样点 `%s`；尾段 %d 样点 `%s`'
             % (got['cal_slices']['OFF_baseline_max_abs_A'][0],
                got['cal_slices']['OFF_baseline_max_abs_A'][1],
                got['cal_slices']['CAL_tail_max_abs_A'][0],
                got['cal_slices']['CAL_tail_max_abs_A'][1])),
            ('|电荷误差| 最大', '%.6f LSB' % got['max_abs_charge_error_LSB']),
            ('交付四态字节', '%d 份 VCD，%d B（LF 交付字节，CRLF 摘要另表）'
             % (got['delivered_traces'], got['delivered_vcd_bytes'])),
            ('gate_records', '%d 行（全部 PASS 才允许入包）' % got['gate_records'])]
    body = [table(rows), '',
            '切片系列共 %d 条（索引行 %d 条，一条系列可分多个切片文件），按种类分列它与接受包的逐字节'
            '关系；不用一个 `new_in_r1` 计数混指两类含义：'
            % (got['series_count'], got['index_rows']),
            '',
            '| 系列种类 | 与接受包的关系 |', '|---|---|']
    for key in sorted(kind):
        body.append('| `%s_*` | %s |' % (key, flat(kind[key])))
    body += ['', '本轮三份主工具的 SHA-256（包内 `environment.json` 记录的是导出时的同一摘要）：',
             '', '| 工具 | SHA-256 |', '|---|---|']
    for tool in TOOLS:
        body.append('| `%s` | `%s` |' % (tool, got['tool_sha256'][tool]))
    body += ['', '包内 `environment.json` 记录的导出源码身份：measure `%s`，evidence_check `%s`。'
             % (got['measurement_source_sha256'], got['evidence_check_source_sha256']), '',
             '包内 gate 记录：', '', '| gate | 判决 | rc | 命令 |', '|---|---|---|---|']
    for g in gates:
        body.append('| `%s` | %s | %s | `%s` |' % (g['gate'], g['verdict'], g['rc'], g['command']))
    return '\n'.join(body)


def embed(path, got, gates):
    text = u(io.open(path, encoding='utf-8', newline='').read())
    if MARK_BEGIN not in text or MARK_END not in text:
        raise SystemExit('D7B_R2_RESULT_SET: %s carries no result-set markers' % path)
    head, rest = text.split(MARK_BEGIN, 1)
    _old, tail = rest.split(MARK_END, 1)
    new = head + MARK_BEGIN + '\n' + section(got, gates) + '\n' + MARK_END + tail
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new)
    print('RESULT_SET_EMBEDDED %s' % path)


def gate_rows(ev_dir):
    path = os.path.join(ev_dir, 'gate_records.csv')
    if not os.path.isfile(path):
        return []
    return EC.read_rows(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bundle')
    ap.add_argument('--out', default='')
    ap.add_argument('--embed', default='', help='rewrite the marked section of a report')
    ap.add_argument('--json-only', action='store_true', help='print the result set and nothing else')
    opts = ap.parse_args(argv)
    ev = os.path.abspath(opts.bundle)
    got = collect(ev)
    gates = gate_rows(ev)
    text = json.dumps(got, indent=1, sort_keys=True) + '\n'
    if opts.out:
        with io.open(opts.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    if opts.embed:
        embed(opts.embed, got, gates)
    if opts.json_only:
        sys.stdout.write(text)
        return 0 if 'EVIDENCE_READABLE' not in got['failures'] else 1
    if opts.out:
        print('RESULT_SET %s' % opts.out)
    print(text)
    # the result set is only useful as a gate if the checker it reports really ran to completion
    if 'EVIDENCE_READABLE' in got['failures']:
        print('D7B_R2_RESULT_SET: FAIL the re-checker itself could not read the bundle')
        return 1
    print('D7B_R2_RESULT_SET: %s (%d checks, %d failure(s): %s)'
          % ('PASS' if got['failures'] == ['BUDGET_RESPECTED'] else 'NOTED', got['checks_run'],
             len(got['failures']), ' '.join(got['failures'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
