# -*- coding: utf-8 -*-
"""DATA-7A execution entry: vectors, real four-state simulation, negatives, synthesis pass, evidence.

    python scripts/dd1_d7a_run.py --selftest
    python scripts/dd1_d7a_run.py --dry-run
    python scripts/dd1_d7a_run.py --run-rtl   --out review/dd1_d7a/<run_id>
    python scripts/dd1_d7a_run.py --mutants   --out review/dd1_d7a/<run_id>
    python scripts/dd1_d7a_run.py --synth     --out review/dd1_d7a/<run_id>
    python scripts/dd1_d7a_run.py --export     --out review/dd1_d7a/<run_id>
    python scripts/dd1_d7a_run.py --write-guard-demo

One command reproduces the round, in this order:

    RUNID=$(date +%Y%m%dT%H%M%S) && python scripts/dd1_d7a_run.py --selftest && \
    python scripts/dd1_d7a_run.py --dry-run && \
    python scripts/dd1_d7a_run.py --run-rtl --out review/dd1_d7a/$RUNID && \
    python scripts/dd1_d7a_run.py --mutants --out review/dd1_d7a/$RUNID && \
    python scripts/dd1_d7a_run.py --synth   --out review/dd1_d7a/$RUNID && \
    python scripts/dd1_d7a_run.py --export  --out review/dd1_d7a/$RUNID

`--export` is the only step that touches `results/evidence/`, and it refuses to run unless the
simulation, negative and synthesis gates inside the run directory all passed. The simulator is found
from `D7A_TOOL_ROOT` (or the default tool directory of this machine) and never from a path baked
into the repository. Nothing here runs Spectre, opens Cadence, or writes an OA library.
"""
from __future__ import print_function

import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

try:
    _text = unicode
except NameError:
    _text = str

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7a_check as ck                                        # noqa: E402
import dd1_d7a_trace as tv                                        # noqa: E402

RTL = os.path.join(PROJ, 'rtl', 'dd1_d7a_gray_ctrl.sv')
TB = os.path.join(PROJ, 'tests', 'dd1_d7a', 'tb_dd1_d7a_gray.sv')
EVIDENCE = os.path.join(PROJ, 'results', 'evidence')
TOOL_DEFAULTS = [os.environ.get('D7A_TOOL_ROOT', ''), r'D:\ic617_d7a_tools\oss-cad-suite',
                 r'C:\ic617_d7a_tools\oss-cad-suite']
TOOL_URL = ('https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-10-20/'
            'oss-cad-suite-windows-x64-20261020.tgz')
TOOL_SHA = 'b141f2523e265d8ca742f96760cb3c9260422194e28f6851741cf2ffce9bc943'
TOOL_BYTES = 603893871

MODE_PURE, MODE_HYBRID = ck.MODE_PURE, ck.MODE_HYBRID
GROUPS = (('pure_t30', MODE_PURE, 3, 30), ('pure_t50', MODE_PURE, 5, 50),
          ('hyb_t120', MODE_HYBRID, 12, 120), ('hyb_t200', MODE_HYBRID, 20, 200))
MAIN_BASE = 1                                              # main case ids 1..1536
CONTROL_BASE = 2001
MIXED_BASE = 3001

FROZEN_DIGESTS = {
    'spectre/dd1_d6_sink_core.scs':
        '6cfe2338014a4b152833ef1974f197b0e4c65e963947f57f0cc8b79b73ee91db',
    'spectre/dd1_d6_bias_core.scs':
        '4115e2d17a86fb92e7c222df085f1d1a82da14cb7640654d90f4e2589e9b31e7',
}


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def now_id():
    return time.strftime('%Y%m%dT%H%M%S')


def sha256(path):
    h = hashlib.sha256()
    fp = io.open(path, 'rb')
    try:
        while True:
            blk = fp.read(1 << 20)
            if not blk:
                break
            h.update(blk)
    finally:
        fp.close()
    return h.hexdigest()


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + '.tmp'
    fp = io.open(tmp, 'w', encoding='utf-8', newline='\n')
    try:
        fp.write(u(text))
    finally:
        fp.close()
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)
    return path


# --------------------------------------------------------------------- toolchain
def find_tools():
    """locate iverilog / vvp / yosys; a missing one is a hard stop, never a skipped gate"""
    root = None
    for cand in TOOL_DEFAULTS:
        if cand and os.path.isdir(os.path.join(cand, 'bin')):
            root = cand
            break
    if root is None:
        raise SystemExit('BLOCKED_TOOLCHAIN: no oss-cad-suite root found. Set D7A_TOOL_ROOT to the '
                         'extracted suite directory (it is deliberately not stored in the repo).')
    env = dict(os.environ)
    env['PATH'] = os.pathsep.join([os.path.join(root, 'bin'), os.path.join(root, 'lib'),
                                   env.get('PATH', '')])
    tools = {}
    for name in ('iverilog', 'vvp', 'yosys'):
        exe = os.path.join(root, 'bin', name + '.exe')
        if not os.path.exists(exe):
            raise SystemExit('BLOCKED_TOOLCHAIN: %s is missing under %s' % (name, root))
        tools[name] = exe
    return root, tools, env


def tool_versions(tools, env):
    out = {}
    for name, exe in sorted(tools.items()):
        args = [exe, '-V'] if name != 'yosys' else [exe, '-V']
        rc, txt = call(args, env, 60)
        first = (txt or '').split('\n')[0].strip()
        out[name] = {'rc': rc, 'version': first,
                     'sha256': sha256(exe) if os.path.exists(exe) else 'UNAVAILABLE'}
        if rc != 0 or not first:
            raise SystemExit('BLOCKED_TOOLCHAIN: %s -V returned rc=%s' % (name, rc))
    return out


def call(args, env, timeout=600, cwd=None):
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                             cwd=cwd)
    except OSError as exc:
        return (127, 'spawn failed: %s' % exc)
    try:
        data = p.communicate()[0]
    except Exception as exc:                                          # noqa: BLE001
        p.kill()
        return (124, 'timeout: %s' % exc)
    return (p.returncode, u(data or ''))


# --------------------------------------------------------------------- vectors
def vector_line(cid, profile, mode, pure_a, pure_b, ht_a, ht_b, pam_a, pam_b, tdiv,
               p1=0, p2=0, p3=0, p4=0):
    return '%d %d %d %d %d %d %d %d %d %d %d %d %d %d' % (
        cid, profile, mode, pure_a, pure_b, ht_a, ht_b, pam_a, pam_b, tdiv, p1, p2, p3, p4)


def main_vectors():
    """1536 unique main cases; both instances always get the same configuration"""
    rows = []
    nxt = MAIN_BASE
    for name, mode, tdiv, tick_ns in GROUPS:
        if mode == MODE_PURE:
            codes = [(c, c, 0) for c in range(256)]                     # (pure, pam ignored)
        else:
            codes = [(0, p, t) for p in range(8) for t in range(64)]
        for pure, pam, ht in codes:
            rows.append((nxt, name, vector_line(nxt, 0, mode, pure, pure, ht, ht, pam, pam, tdiv)))
            nxt += 1
    if nxt - MAIN_BASE != 1536:
        raise SystemExit('vector generation produced %d main cases, not 1536' % (nxt - MAIN_BASE))
    return rows


def control_scenarios():
    """the state and exception matrix of task section 4.3, one scenario per named case"""
    s = []

    def add(cid, profile, mode, pure, ht, pam, tdiv, kind, name, p1=0, p2=0, p3=0, p4=0, **kw):
        d = {'case_id': cid, 'profile': profile, 'kind': kind, 'name': name,
             'mode': ck.MODE_NAME[mode], 'tick_ns': tdiv * 10,
             'p1': p1, 'p2': p2, 'p3': p3, 'p4': p4}
        d.update(kw)
        s.append((cid, vector_line(cid, profile, mode, pure, pure, ht, ht, pam, pam, tdiv,
                                   p1, p2, p3, p4), d))

    add(CONTROL_BASE + 0, 16, MODE_PURE, 0, 0, 0, 3, 'dark_only', 'power-up with no accepted config')
    add(CONTROL_BASE + 1, 17, MODE_PURE, 0, 0, 0, 3, 'dark_only', 'repeated reset pulses, no config')
    add(CONTROL_BASE + 2, 4, MODE_PURE, 128, 0, 0, 3, 'no_auto_resume', 'reset in the middle of a window',
        abort='reset_fall')
    add(CONTROL_BASE + 3, 5, MODE_PURE, 200, 0, 0, 3, 'start_held_40ns_once',
        'PWM_START held high through the window')
    add(CONTROL_BASE + 4, 0, MODE_PURE, 7, 0, 0, 3, 'window_ok', 'PWM_START held 40 ns accepted once')
    add(CONTROL_BASE + 5, 6, MODE_PURE, 40, 0, 0, 3, 'tick_in_blank_consumed',
        'ticks during blank and before the start')
    add(CONTROL_BASE + 6, 11, MODE_PURE, 90, 0, 0, 3, 'clock_stall', 'long reference-clock stall',
        gap_min_ns=150, p1=200)
    add(CONTROL_BASE + 7, 2, MODE_PURE, 150, 0, 0, 3, 'async_off_between_edges',
        'blank asserted between clock edges mid-window', asserts=['blank'], p1=30)
    add(CONTROL_BASE + 8, 2, MODE_PURE, 150, 0, 0, 3, 'no_auto_resume',
        'blank withdrawn must not resume the aborted window', abort='blank_rise', p1=30)
    add(CONTROL_BASE + 9, 3, MODE_PURE, 150, 0, 0, 3, 'async_off_between_edges',
        'fault asserted between clock edges mid-window', asserts=['fault'], p1=30)
    add(CONTROL_BASE + 10, 3, MODE_PURE, 150, 0, 0, 3, 'no_auto_resume',
        'fault cleared must not resume the aborted window', abort='fault_rise', p1=30)
    add(CONTROL_BASE + 11, 12, MODE_PURE, 100, 0, 0, 3, 'window_ok',
        'a fresh load/LATCH/start after an abort', window=1, p1=20, p2=3)
    add(CONTROL_BASE + 12, 7, MODE_PURE, 60, 0, 0, 3, 'refused_then_window',
        'mode changed while a window runs is refused', proto_err_bit=ck.E_MODE_WHILE_RUNNING,
        p1=20)
    add(CONTROL_BASE + 13, 8, MODE_HYBRID, 0, 20, 3, 12, 'refused_dark', 'illegal mode code 2',
        proto_err_bit=ck.E_ILLEGAL_MODE)
    add(CONTROL_BASE + 14, 9, MODE_PURE, 33, 0, 0, 3, 'refused_dark', 'incomplete configuration',
        proto_err_bit=ck.E_INCOMPLETE_CFG)
    add(CONTROL_BASE + 15, 10, MODE_PURE, 66, 0, 0, 3, 'refused_then_window',
        'LATCH on the same edge as the configuration', proto_err_bit=ck.E_LATCH_AMBIGUOUS)
    add(CONTROL_BASE + 16, 1, MODE_PURE, 120, 0, 0, 3, 'display_frozen',
        'next grey code loaded during a running window', p1=20, p2=5)
    add(CONTROL_BASE + 17, 13, MODE_HYBRID, 0, 30, 0, 12, 'pam_toggle',
        'PAM codes 0 and 7 in consecutive windows', pam_b=7)
    add(CONTROL_BASE + 18, 14, MODE_PURE, 255, 0, 0, 3, 'window_ok',
        'full window then shortest, second window', window=1, p1=1)
    add(CONTROL_BASE + 19, 14, MODE_PURE, 1, 0, 0, 5, 'window_ok',
        'shortest then full window, second window', window=1, p1=255)
    add(CONTROL_BASE + 20, 14, MODE_HYBRID, 0, 62, 4, 12, 'window_ok',
        'Hybrid 62 then 63, second window', window=1, p1=63)
    add(CONTROL_BASE + 21, 14, MODE_HYBRID, 0, 63, 7, 20, 'window_ok',
        'Hybrid 63 then 0, second window', window=1, p1=0)
    add(CONTROL_BASE + 22, 18, MODE_PURE, 77, 0, 0, 3, 'window_ok',
        'legal mode switch in the safe phase, second window', window=1, p1=1,
        pure_b=0, ht_b=63, pam_b=6)
    add(CONTROL_BASE + 23, 19, MODE_PURE, 0, 0, 0, 3, 'window_ok',
        'unknown code bus must never become a valid window', expect='refusal')
    return s


def mixed_vectors():
    """two channels with different codes behind common control, reported apart from the 1536"""
    rows = []
    combos = [(MODE_PURE, 1, 255, 0, 0, 0, 3), (MODE_PURE, 254, 0, 0, 0, 0, 5),
              (MODE_PURE, 0, 128, 0, 0, 0, 3), (MODE_HYBRID, 0, 0, 1, 63, 5, 12),
              (MODE_HYBRID, 0, 0, 62, 0, 0, 20), (MODE_HYBRID, 0, 0, 0, 63, 7, 12)]
    cid = MIXED_BASE
    for mode, pa, pb, ha, hb, pama, tdiv in combos:
        pam_b = (pama + 3) % 8
        rows.append((cid, vector_line(cid, 15, mode, pa, pb, ha, hb, pama, pam_b, tdiv),
                     {'case_id': cid, 'profile': 15, 'kind': 'mixed_codes',
                      'name': 'mixed codes mode %s a=%d/%d b=%d/%d'
                              % (ck.MODE_NAME[mode], pa, ha, pb, hb),
                      'mode': ck.MODE_NAME[mode], 'tick_ns': tdiv * 10}))
        cid += 1
    return rows


def write_vectors(run_dir):
    os.path.isdir(run_dir) or os.makedirs(run_dir)
    files = {}
    for name, mode, tdiv, tick_ns in GROUPS:
        lines = [v for cid, grp, v in main_vectors() if grp == name]
        path = os.path.join(run_dir, 'vectors_%s.txt' % name)
        write_atomic(path, '\n'.join(lines) + '\n')
        files[name] = {'path': os.path.relpath(path, PROJ).replace('\\', '/'), 'cases': len(lines),
                       'sha256': sha256(path), 'tick_ns': tick_ns, 'mode': ck.MODE_NAME[mode]}
    ctl = control_scenarios()
    path = os.path.join(run_dir, 'vectors_control.txt')
    write_atomic(path, '\n'.join([v for _c, v, _d in ctl]) + '\n')
    files['control'] = {'path': os.path.relpath(path, PROJ).replace('\\', '/'), 'cases': len(ctl),
                        'sha256': sha256(path), 'mode': 'CONTROL'}
    path = os.path.join(run_dir, 'vectors_mixed.txt')
    mx = mixed_vectors()
    write_atomic(path, '\n'.join([v for _c, v, _d in mx]) + '\n')
    files['mixed'] = {'path': os.path.relpath(path, PROJ).replace('\\', '/'), 'cases': len(mx),
                      'sha256': sha256(path), 'mode': 'MIXED'}
    scen = [d for _c, _v, d in ctl] + [d for _c, _v, d in mx]
    path = os.path.join(run_dir, 'scenarios.json')
    write_atomic(path, json.dumps(scen, indent=1, sort_keys=True) + '\n')
    files['scenarios'] = {'path': os.path.relpath(path, PROJ).replace('\\', '/'),
                          'cases': len(scen), 'sha256': sha256(path)}
    return files


# --------------------------------------------------------------------- running
def compile_sim(tools, env, run_dir, rtl=RTL, tb=TB, tag='d7a', extra=()):
    exe = os.path.join(run_dir, '%s.vvp' % tag)
    rc, out = call([tools['iverilog'], '-g2012', '-Wall', '-o', exe, rtl] + list(extra) + [tb],
                   env, 600)
    if rc != 0 or not os.path.exists(exe):
        raise SystemExit('IVERILOG_FAILED rc=%s: %s' % (rc, out[-1500:]))
    return exe, rc, out


def run_vvp(exe, env, vec, vcd, timeout, log):
    rc, out = call([tools_active['vvp'], exe, '+VEC=%s' % vec, '+VCD=%s' % vcd], env, timeout)
    io.open(log, 'w', encoding='utf-8', newline='\n').write(
        u'$ %s %s +VEC=%s +VCD=%s\nrc=%d\n%s' % (tools_active['vvp'], exe, vec, vcd, rc, u(out)))
    if rc != 0:
        raise ck.Refuse('vvp rc=%d for %s' % (rc, os.path.basename(vec)))
    if not os.path.exists(vcd) or os.path.getsize(vcd) == 0:
        raise ck.Refuse('no trace produced for %s' % os.path.basename(vec))
    if 'TB-ERROR' in out:
        raise ck.Refuse('testbench reported an error for %s' % os.path.basename(vec))
    return rc, out


tools_active = {}


def run_group(tools, env, exe, name, vec, run_dir, run_id, timeout):
    vcd = os.path.join(run_dir, 'trace_%s.vcd' % name)
    log = os.path.join(run_dir, 'vvp_%s.log' % name)
    t0 = time.time()
    rc, out = run_vvp(exe, env, vec, vcd, timeout, log)
    rows, tr = ck.check_main_trace(vcd, run_id)
    el = round(time.time() - t0, 2)
    return rows, {'name': name, 'vvp_rc': rc, 'vcd': os.path.basename(vcd),
                  'vcd_bytes': os.path.getsize(vcd), 'vcd_sha256': sha256(vcd),
                  'seconds': el, 'tb_cases': parse_tb_cases(out),
                  'signals': len(tr.changes), 'aliased_ids': tr.aliased,
                  'same_time_edges': tr.same_time_edges}


def parse_tb_cases(out):
    m = re.search(r'TB-DATA7A cases=(\d+)', out or '')
    return int(m.group(1)) if m else -1


def do_run(args):
    root, tools, env = find_tools()
    tools_active.clear()
    tools_active.update(tools)
    run_dir = os.path.abspath(args['out'])
    run_id = os.path.basename(run_dir)
    os.path.isdir(run_dir) or os.makedirs(run_dir)
    vecs = write_vectors(run_dir)
    versions = tool_versions(tools, env)
    exe, crc, cout = compile_sim(tools, env, run_dir)
    all_rows, groups, fails = [], [], []
    timeout = int(args.get('timeout', '1800'))
    for name in [g[0] for g in GROUPS]:
        rows, meta = run_group(tools, env, exe, name, vecs[name]['path'], run_dir, run_id, timeout)
        groups.append(meta)
        all_rows.extend(rows)
    ctl_rows = []
    vcd = os.path.join(run_dir, 'trace_control.vcd')
    log = os.path.join(run_dir, 'vvp_control.log')
    rc, out = run_vvp(exe, env, vecs['control']['path'], vcd, timeout, log)
    scen = json.load(io.open(os.path.join(run_dir, 'scenarios.json'), encoding='utf-8'))
    ctl_rows, tr = ck.check_control_trace(vcd, [s for s in scen if s['kind'] != 'mixed_codes'],
                                          run_id)
    groups.append({'name': 'control', 'vvp_rc': rc, 'vcd': os.path.basename(vcd),
                   'vcd_bytes': os.path.getsize(vcd), 'vcd_sha256': sha256(vcd),
                   'tb_cases': parse_tb_cases(out), 'signals': len(tr.changes),
                   'aliased_ids': tr.aliased, 'same_time_edges': tr.same_time_edges})
    vcd = os.path.join(run_dir, 'trace_mixed.vcd')
    log = os.path.join(run_dir, 'vvp_mixed.log')
    rc, out = run_vvp(exe, env, vecs['mixed']['path'], vcd, timeout, log)
    mixed_rows, tr = ck.check_control_trace(vcd, [s for s in scen if s['kind'] == 'mixed_codes'],
                                            run_id)
    groups.append({'name': 'mixed', 'vvp_rc': rc, 'vcd': os.path.basename(vcd),
                   'vcd_bytes': os.path.getsize(vcd), 'vcd_sha256': sha256(vcd),
                   'tb_cases': parse_tb_cases(out), 'signals': len(tr.changes),
                   'aliased_ids': tr.aliased, 'same_time_edges': tr.same_time_edges})

    for row in all_rows + ctl_rows + mixed_rows:
        if row['verdict'] != 'PASS' and row.get('expect') != 'refusal':
            fails.append('case %s: %s' % (row.get('case_id'), row.get('failures', '')[:120]))
    expected_refused = [r for r in ctl_rows if r.get('expect') == 'refusal' or
                        any(s.get('expect') == 'refusal' and s['case_id'] == r['case_id']
                            for s in scen)]
    summary = {
        'run_id': run_id, 'groups': groups, 'compile_rc': crc,
        'main_rows': len(all_rows),
        'main_pass': len([r for r in all_rows if r['verdict'] == 'PASS']),
        'control_rows': len(ctl_rows),
        'control_pass': len([r for r in ctl_rows if r['verdict'] == 'PASS'
                             and r.get('kind') != '']),
        'mixed_rows': len(mixed_rows),
        'mixed_pass': len([r for r in mixed_rows if r['verdict'] == 'PASS']),
        'xprobe_expected': len(expected_refused),
        'xprobe_refused': len([r for r in ctl_rows if r.get('expect') == 'refusal'
                               and r['verdict'] == 'FAIL']),
        'failures': fails[:40],
        'tool_versions': versions,
        'rtl_sha256': sha256(RTL), 'tb_sha256': sha256(TB),
        'checker_sha256': sha256(os.path.join(HERE, 'dd1_d7a_check.py')),
        'reader_sha256': sha256(os.path.join(HERE, 'dd1_d7a_trace.py')),
    }
    write_atomic(os.path.join(run_dir, 'run_summary.json'),
                 json.dumps(summary, indent=1, sort_keys=True) + '\n')
    write_atomic(os.path.join(run_dir, 'raw_main_rows.json'),
                 json.dumps(all_rows, indent=1, sort_keys=True) + '\n')
    write_atomic(os.path.join(run_dir, 'raw_control_rows.json'),
                 json.dumps(ctl_rows, indent=1, sort_keys=True) + '\n')
    write_atomic(os.path.join(run_dir, 'raw_mixed_rows.json'),
                 json.dumps(mixed_rows, indent=1, sort_keys=True) + '\n')
    print(json.dumps({k: summary[k] for k in ('main_rows', 'main_pass', 'control_rows',
                                              'control_pass', 'mixed_rows', 'mixed_pass',
                                              'xprobe_expected', 'xprobe_refused')}, indent=1))
    if fails:
        print('FAILURES (%d):' % len(fails))
        for f in fails[:20]:
            print('  ' + f)
        return 1
    return 0


# --------------------------------------------------------------------- mutants
MUTANTS = {
    'pure255_only255': {
        'find': 'wire [8:0] pure_iv  = (cfg_pure == 8\'d255)     ? FULL_PURE : {1\'b0, cfg_pure};',
        'sub':  'wire [8:0] pure_iv  = {1\'b0, cfg_pure};',
        'trigger': ('main', MODE_PURE, 255, 3),
        'expect': ['ON_WIDTH', 'WIDTH_NOT_MULTIPLE'],
        'note': 'code 255 conducts 255 of 256 intervals, so the full window is one interval short',
    },
    'counter_rollover_reopens': {
        'find': '''                end else begin
                    run_q   <= 1'b0;          // explicit window end, never a counter rollover
                    state_q <= S_DONE;
                end''',
        'sub': '''                end else begin
                    run_q   <= (target_q != 9'd0);
                    index_q <= 9'd0;
                    state_q <= S_ARMED;
                end''',
        'trigger': ('main', MODE_PURE, 200, 3),
        'expect': ['REOPEN_AFTER_WINDOW', 'SEGMENT_COUNT'],
        'note': 'the interval counter rolls over and opens the output again after the window end',
    },
    'blank_gate_removed': {
        'find': "assign data_en   = run_q & ~blank & ~fault & reset_n;",
        'sub':  "assign data_en   = run_q & ~fault & reset_n;",
        'trigger': ('control', 2008),
        'expect': ['ASYNC_OFF'],
        'note': 'the blank assertion no longer pulls the enable down between clock edges',
    },
    'start_level_rearm': {
        'find': '            if (start_ok) begin',
        'sub':  '            if (pwm_start & ~fault & reset_n) begin',
        'trigger': ('control', 2004),
        'expect': ['SEGMENT_COUNT', 'ON_WIDTH', 'NO_DEASSERTION'],
        'note': 'a held PWM_START re-clears the counter on every reference edge',
    },
    'instance_b_one_tick_late': {
        'find': 'wire tick_accept = tick & window_active & ~async_block;',
        'sub':  'reg tick_dly;\n    always_ff @(posedge clk or negedge reset_n) tick_dly <= reset_n ? tick : 1\'b0;\n'
                '    wire tick_accept = tick_dly & window_active & ~async_block;',
        'trigger': ('main', MODE_PURE, 12, 3),
        'expect': ['INSTANCES_DIFFER', 'ON_START'],
        'note': 'the module instance used for channel B starts one reference edge later',
    },
    'auto_resume_after_abort': {
        'find': 'wire window_active = (state_q == S_ARMED) || (state_q == S_RUN);',
        'sub':  'wire window_active = (state_q == S_ARMED) || (state_q == S_RUN) ||\n'
                '                       ((state_q == S_ABORT) && !blank && !fault);',
        'trigger': ('control', 2009),
        'expect': ['AUTO_RESUME'],
        'note': 'withdrawing blank resumes the aborted window instead of requiring a new start',
    },
}


def do_mutants(args):
    root, tools, env = find_tools()
    tools_active.clear()
    tools_active.update(tools)
    run_dir = os.path.abspath(args['out'])
    run_id = os.path.basename(run_dir)
    os.path.isdir(run_dir) or os.makedirs(run_dir)
    base_rtl = u(io.open(RTL, encoding='utf-8').read())
    base_tb = u(io.open(TB, encoding='utf-8').read())
    rows = []
    for cls in sorted(MUTANTS):
        spec = MUTANTS[cls]
        if spec['find'] not in base_rtl:
            rows.append({'class': cls, 'status': 'PATCH_NOT_APPLIED', 'detail':
                         'the mutation anchor is not present in the current RTL'})
            continue
        mdir = os.path.join(run_dir, 'mutant_%s' % cls)
        os.path.isdir(mdir) or os.makedirs(mdir)
        mutated = base_rtl.replace(spec['find'], spec['sub'], 1)
        tb_src = base_tb
        if cls == 'instance_b_one_tick_late':
            mutated = mutated.replace('module dd1_d7a_gray_ctrl (', 'module dd1_d7a_gray_ctrl_late (', 1)
            io.open(os.path.join(mdir, 'dd1_d7a_gray_ctrl.sv'), 'w', encoding='utf-8',
                    newline='\n').write(u(base_rtl))
            tb_src = base_tb.replace(
                '    dd1_d7a_gray_ctrl u_b (', '    dd1_d7a_gray_ctrl_late u_b (')
        rtl_path = write_atomic(os.path.join(mdir, 'mutant.sv'), mutated)
        tb_path = write_atomic(os.path.join(mdir, 'tb.sv'), tb_src)
        extra = [os.path.join(mdir, 'dd1_d7a_gray_ctrl.sv')] if cls == \
            'instance_b_one_tick_late' else []
        exe, crc, cout = compile_sim(tools, env, mdir, rtl_path, tb_path, tag='mut', extra=extra)
        if crc != 0:
            rows.append({'class': cls, 'status': 'COMPILE_FAILED', 'detail': cout[-300:]})
            continue
        kind = spec['trigger'][0]
        vec_path = os.path.join(mdir, 'vec.txt')
        if kind == 'main':
            _g, mode, code, tdiv = spec['trigger']
            write_atomic(vec_path, vector_line(501, 0, mode, code, code, 0, 0, 0, 0, tdiv) + '\n')
        else:
            cid = spec['trigger'][1]
            line = [v for c, v, d in control_scenarios() if c == cid][0]
            write_atomic(vec_path, line + '\n')
        vcd = os.path.join(mdir, 'trace.vcd')
        try:
            run_vvp(exe, env, vec_path, vcd, int(args.get('timeout', '900')),
                    os.path.join(mdir, 'vvp.log'))
        except ck.Refuse as exc:
            rows.append({'class': cls, 'status': 'RUN_FAILED', 'detail': str(exc)})
            continue
        try:
            if kind == 'main':
                got = ck.check_main_trace(vcd, run_id)[0]
            else:
                scen = [d for c, v, d in control_scenarios() if c == cid_of(spec)][0]
                got = ck.check_control_trace(vcd, [scen], run_id)[0]
        except (tv.VcdError, ck.Refuse) as exc:
            rows.append({'class': cls, 'status': 'DETECTED', 'trigger_case': got_case(spec),
                         'refused_at_parse': True, 'detail': str(exc)[:200],
                         'mutant_rtl_sha256': sha256(rtl_path), 'checker': 'same checker'})
            continue
        tags = spec['expect'] if isinstance(spec['expect'], list) else [spec['expect']]
        hit = [r for r in got if any(t in r['failures'] for t in tags)]
        rows.append({'class': cls,
                     'status': 'DETECTED' if hit else 'NOT_DETECTED',
                     'trigger_case': got_case(spec),
                     'mutant_rtl_sha256': sha256(rtl_path),
                     'checker': 'same checker, unchanged judgement code',
                     'detail': (hit[0]['failures'][:200] if hit else
                                'the original checker accepted the mutated design')})
    ok = len([r for r in rows if r['status'] == 'DETECTED'])
    write_atomic(os.path.join(run_dir, 'mutants.json'),
                 json.dumps({'run_id': run_id, 'detected': ok, 'total': len(MUTANTS),
                             'rows': rows}, indent=1, sort_keys=True) + '\n')
    for r in rows:
        print('%-28s %-16s %s' % (r['class'], r['status'], r['detail'][:70]))
    print('MUTATION_DETECTED=%d/%d' % (ok, len(MUTANTS)))
    return 0 if ok == len(MUTANTS) else 1


def cid_of(spec):
    return spec['trigger'][1] if spec['trigger'][0] == 'control' else 501


def got_case(spec):
    return spec['trigger'][1] if spec['trigger'][0] == 'control' else 501


# --------------------------------------------------------------------- synthesis structure
YOSYS_SCRIPT = """
read_verilog -sv {rtl}
hierarchy -check -top dd1_d7a_gray_ctrl
proc
opt_expr
opt_clean
check -assert
flatten
opt -fine
opt_clean -purge
check -assert
stat
select -assert-none t:$dlatch
select -assert-none t:$sr
select -assert-none t:$dffe
select -assert-none t:$memory
select -assert-none t:$anyseq
select -assert-none t:$anyconst
"""


def do_synth(args):
    root, tools, env = find_tools()
    run_dir = os.path.abspath(args['out'])
    os.path.isdir(run_dir) or os.makedirs(run_dir)
    script = os.path.join(run_dir, 'structure.ys')
    write_atomic(script, YOSYS_SCRIPT.format(rtl=RTL.replace('\\', '/')))
    out_path = os.path.join(run_dir, 'yosys_structure.log')
    rc, txt = call([tools['yosys'], '-s', script], env, 600, cwd=PROJ)
    io.open(out_path, 'w', encoding='utf-8', newline='\n').write(
        u('$ %s -s %s\nrc=%d\n%s' % (tools['yosys'], script, rc, u(txt))))
    problems = []
    if rc != 0:
        problems.append('yosys rc=%d' % rc)
    for pat, why in ((r'\bERROR\b', 'an ERROR line'), (r'multiple drivers', 'multiple drivers'),
                     (r'Wire .* is uninitialized', 'an uninitialised wire'),
                     (r'\$dlatch', 'an inferred latch')):
        if re.search(pat, txt or '', re.I):
            problems.append(why)
    cells = dict((m.group(2), int(m.group(1))) for m in
                 re.finditer(r'^\s+(\d+)\s+(\$\w+)\s*$', txt or '', re.M))
    total = None
    m = re.search(r'^\s{6}(\d+) cells\s*$', txt or '', re.M)
    if m:
        total = int(m.group(1))
    summary = {'rc': rc, 'problems': problems,
               'cells': cells, 'cells_total': total,
               'storage': dict((k, v) for k, v in cells.items() if 'ff' in k or 'latch' in k or
                               'mem' in k),
               'check_passes': len(re.findall(r'Found and reported 0 problems', txt or '')),
               'unresolved_modules': len(re.findall(r'module .* is not used|ERROR: Module .* not found',
                                                    txt or '')),
               'selected': {'errors': len(re.findall(r'\bERROR\b', txt or '', re.I)),
                            'warnings': len(re.findall(r'\bWarning\b', txt or '', re.I))},
               'log': os.path.basename(out_path), 'rtl_sha256': sha256(RTL),
               'scope': 'front-end expansion and structure only: no cell library, no technology '
                        'mapping, no timing, no area claim, testbench not read'}
    write_atomic(os.path.join(run_dir, 'synth_summary.json'),
                 json.dumps(summary, indent=1, sort_keys=True) + '\n')
    print(json.dumps(summary, indent=1, sort_keys=True)[:1200])
    return 0 if not problems else 1


# --------------------------------------------------------------------- export evidence
def edge_samples(tr, sm, cid, cs, ce, anchors):
    """input and output values on a 2 ns grid across each anchor, read out of the same trace

    Sampling on a grid rather than only at change events is what makes the guard meaningful: the row
    set has to contain points before the anchor and points after it, or it is refused. A list of
    pre-anchor points would otherwise look identical to a response.
    """
    rows = []
    sigs = [sm.i('blank'), sm.i('tick'), sm.i('clk'), sm.o(0, 'data_en'), sm.o(0, 'data_en_b'),
            sm.o(0, 'pam_sel'), sm.o(0, 'win_state'), sm.o(0, 'obs_tick')]
    for name, at in anchors:
        for sig in sigs:
            grid = []
            t = at - 12000
            while t <= at + 12000:
                if cs - 1 <= t <= ce:
                    grid.append((t, tr.value_at(sig, t)))
                t += 2000
            ck.require_span(grid, at, 12, 12, 'case %s anchor %s signal %s' % (cid, name, sig))
            for t, v in grid:
                rows.append({'case_id': cid, 'anchor': name, 'anchor_ns': fmt_int(at),
                             't_ns': fmt_int(t), 'signal': sig, 'value': v,
                             'relative_ns': fmt_int(t - at)})
    return rows


def fmt_int(t_ps):
    return '%d' % (t_ps // ck.PS) if t_ps % ck.PS == 0 else '%.3f' % (float(t_ps) / ck.PS)


CASES_ORDER = ['run_id', 'case_id', 'vcd', 'verdict', 'failures', 'instances_match',
               'mode', 'frame_hz', 'time_code', 'pam_code', 'tick_ns', 'exp_intervals',
               'full_intervals',
               'a_mode', 'a_time_code', 'a_pam_code', 'a_tick_ns', 'a_clk_ns', 'a_frame_hz',
               'a_exp_intervals', 'a_full_intervals', 'a_t0_ns', 'a_window_end_ns', 'a_tail_end_ns',
               'a_on_segments', 'a_on_intervals_measured', 'a_on_width_ns', 'a_on_ns', 'a_off_ns',
               'a_pam_held', 'a_data_en_b', 'a_win_state', 'a_obs_tick', 'a_obs_tick_pulses',
               'a_cfg_version',
               'b_mode', 'b_time_code', 'b_pam_code', 'b_tick_ns', 'b_clk_ns', 'b_frame_hz',
               'b_exp_intervals', 'b_full_intervals', 'b_t0_ns', 'b_window_end_ns', 'b_tail_end_ns',
               'b_on_segments', 'b_on_intervals_measured', 'b_on_width_ns', 'b_on_ns', 'b_off_ns',
               'b_pam_held', 'b_data_en_b', 'b_win_state', 'b_obs_tick', 'b_obs_tick_pulses',
               'b_cfg_version']


def do_export(args):
    run_dir = os.path.abspath(args['out'])
    summary = json.load(io.open(os.path.join(run_dir, 'run_summary.json'), encoding='utf-8'))
    mut = json.load(io.open(os.path.join(run_dir, 'mutants.json'), encoding='utf-8'))
    synth = json.load(io.open(os.path.join(run_dir, 'synth_summary.json'), encoding='utf-8'))
    main_rows = json.load(io.open(os.path.join(run_dir, 'raw_main_rows.json'), encoding='utf-8'))
    ctl_rows = json.load(io.open(os.path.join(run_dir, 'raw_control_rows.json'), encoding='utf-8'))
    mixed_rows = json.load(io.open(os.path.join(run_dir, 'raw_mixed_rows.json'), encoding='utf-8'))
    # a scenario whose declared expectation is a refusal counts as satisfied only when the checker
    # really refused it; the reverse reading would let a silent numeric conversion pass as a result
    def _as_expected(r):
        if r.get('expect') == 'refusal':
            return r['verdict'] == 'FAIL'
        return r['verdict'] == 'PASS'
    gates = {
        'PURE_MATRIX': summary['main_rows'] >= 1536 and summary['main_pass'] == summary['main_rows'],
        'CONTROL_AND_ABORT': bool(ctl_rows) and all(_as_expected(r) for r in ctl_rows),
        'MIXED': bool(mixed_rows) and all(_as_expected(r) for r in mixed_rows),
        'XPROBE_REFUSED': summary['xprobe_refused'] == summary['xprobe_expected'],
        'MUTATION_DETECTION': mut['detected'] == mut['total'],
        'SYNTHESIS_STRUCTURE': not synth['problems'],
    }
    if not all(gates.values()):
        print('EXPORT_REFUSED: %s' % json.dumps(gates, indent=1, sort_keys=True))
        return 1
    os.path.isdir(EVIDENCE) or os.makedirs(EVIDENCE)
    main_order = sorted(main_rows, key=lambda r: int(r['case_id']))
    n = ck.write_rows(os.path.join(EVIDENCE, 'dd1_d7a_cases.csv'), main_order, order=CASES_ORDER)
    ck.write_rows(os.path.join(EVIDENCE, 'dd1_d7a_control_cases.csv'),
                  sorted(ctl_rows + mixed_rows, key=lambda r: int(r['case_id'])))
    ck.write_rows(os.path.join(EVIDENCE, 'dd1_d7a_negative.csv'), negative_rows(run_dir, mut))
    srows = sample_rows(run_dir, main_order)
    ck.write_rows(os.path.join(EVIDENCE, 'dd1_d7a_edge_samples.csv'), srows)
    env_json = environment_json(run_dir, summary, mut, synth)
    write_atomic(os.path.join(EVIDENCE, 'dd1_d7a_environment.json'),
                 json.dumps(env_json, indent=1, sort_keys=True) + '\n')
    st = os.path.join(run_dir, 'checker_selftest.txt')
    if os.path.exists(st):
        write_atomic(os.path.join(EVIDENCE, 'dd1_d7a_checker_selftest.txt'),
                     u(io.open(st, encoding='utf-8').read()))
    man = manifest_json(run_dir, env_json, n, len(ctl_rows) + len(mixed_rows), len(srows))
    write_atomic(os.path.join(EVIDENCE, 'dd1_d7a_manifest.json'),
                 json.dumps(man, indent=1, sort_keys=True) + '\n')
    print('exported cases=%d control=%d samples=%d' % (n, len(ctl_rows) + len(mixed_rows),
                                                       len(srows)))
    return 0


def negative_rows(run_dir, mut):
    rows = []
    path = os.path.join(run_dir, 'checker_selftest.txt')
    for d in mut['rows']:
        rows.append({'class': d['class'], 'mutant_rtl_sha256': d.get('mutant_rtl_sha256', ''),
                     'trigger_case': d.get('trigger_case', ''), 'simulator_rc': '0',
                     'checker_rc': '1' if d['status'] == 'DETECTED' else '0',
                     'failing_assertion': d.get('detail', '')[:200],
                     'status': d['status'], 'note': MUTANTS.get(d['class'], {}).get('note', ''),
                     'run_id': mut['run_id']})
    if os.path.exists(path):
        txt = u(io.open(path, encoding='utf-8').read())
        for line in txt.split('\n'):
            if line.startswith('FAIL') or 'refused while parsing' in line:
                rows.append({'class': 'checker_selftest', 'mutant_rtl_sha256': 'synthetic trace',
                             'trigger_case': 'synthetic', 'simulator_rc': 'not_run',
                             'checker_rc': '1', 'failing_assertion': line[:200],
                             'status': 'DETECTED', 'note': 'the checker proves its own refusals',
                             'run_id': os.path.basename(run_dir)})
                break
    return rows


def sample_rows(run_dir, main_order):
    """a small representative set: one tick spacing per mode, the code edges and an async shut-off"""
    keep = ('trace_pure_t30.vcd', 'trace_hyb_t120.vcd')
    want = []
    for r in main_order:
        if r.get('vcd') not in keep:
            continue
        code = str(r.get('time_code'))
        if r.get('mode') == 'PURE' and code in ('0', '1', '254', '255'):
            want.append(r)
        if r.get('mode') == 'HYBRID' and ((code in ('0', '1') and str(r.get('pam_code')) == '0')
                                         or (code in ('62', '63')
                                             and str(r.get('pam_code')) == '7')):
            want.append(r)
    out = []
    picked = {}
    for r in want:
        key = (r['mode'], r['time_code'], r['vcd'])
        if key in picked:
            continue
        picked[key] = r
    cache = {}
    for (mode, code, vcd), r in sorted(picked.items()):
        if vcd not in cache:
            tr = tv.Trace(os.path.join(run_dir, vcd))
            cache[vcd] = (tr, ck.SigMap(tr))
        tr, sm = cache[vcd]
        cid = int(r['case_id'])
        cs, ce = None, None
        for c, a, b in ck.cases(tr, sm):
            if c == cid:
                cs, ce = a, b
        if cs is None:
            continue
        anchors = []
        rel = tr.falls(sm.i('blank'), cs, ce)
        if rel:
            anchors.append(('blank_release', rel[0]))
        if r.get('a_on_ns') not in (None, 'none'):
            on = int(float(r['a_on_ns'])) * ck.PS
            anchors.append(('data_en_on', on))
            anchors.append(('data_en_off', on + int(float(r['exp_intervals']))
                            * int(float(r['tick_ns'])) * ck.PS))
        else:
            anchors.append(('first_tick', int(float(r['a_t0_ns'])) * ck.PS - 5000))
        anchors.append(('window_end', int(float(r['a_window_end_ns'])) * ck.PS))
        out.extend(edge_samples(tr, sm, cid, cs, ce, anchors))
    # one asynchronous shut-off, from the control trace: the assertion is what has to be visible
    ctl = os.path.join(run_dir, 'trace_control.vcd')
    if os.path.exists(ctl):
        tr = tv.Trace(ctl)
        sm = ck.SigMap(tr)
        for cid, cs, ce in ck.cases(tr, sm):
            if cid != 2008:
                continue
            rises = tr.rises(sm.i('blank'), cs + 1, ce)
            if not rises:
                break
            out.extend(edge_samples(tr, sm, cid, cs, ce, [('blank_abort_assert', rises[0])]))
            break
    return out


def environment_json(run_dir, summary, mut, synth):
    root, tools, env = find_tools()
    versions = summary.get('tool_versions', {})
    return {
        'task': 'DATA-7A',
        'os': {'name': platform.system(), 'version': platform.release()},
        'python': platform.python_version(),
        'simulator': {k: v['version'] for k, v in versions.items()},
        'simulator_sha256': {k: v['sha256'] for k, v in versions.items()},
        'four_state': True,
        'toolchain_provenance': {'url': TOOL_URL, 'asset_bytes': TOOL_BYTES, 'sha256': TOOL_SHA,
                                 'installed_outside_repo': True,
                                 'path_label': '<tool-root>/bin (from D7A_TOOL_ROOT)'},
        'commands': {
            'compile': 'iverilog -g2012 -Wall -o <run>/d7a.vvp rtl/dd1_d7a_gray_ctrl.sv '
                       'tests/dd1_d7a/tb_dd1_d7a_gray.sv',
            'simulate': 'vvp <run>/d7a.vvp +VEC=<run>/vectors_<group>.txt +VCD=<run>/trace_<group>.vcd',
            'check': 'python scripts/dd1_d7a_check.py --main <vcd> --out <rows.csv> --run-id <run>',
            'mutants': 'python scripts/dd1_d7a_run.py --mutants --out <run>',
            'synthesis': 'yosys -s <run>/structure.ys',
        },
        'counts': {k: summary[k] for k in ('main_rows', 'main_pass', 'control_rows', 'control_pass',
                                           'mixed_rows', 'mixed_pass', 'xprobe_expected',
                                           'xprobe_refused')},
        'groups': summary['groups'],
        'mutation': {'detected': mut['detected'], 'total': mut['total']},
        'synthesis': synth['problems'] or 'clean',
        'sources': {'rtl_sha256': summary['rtl_sha256'], 'tb_sha256': summary['tb_sha256'],
                    'checker_sha256': summary['checker_sha256'],
                    'reader_sha256': summary['reader_sha256']},
        'no_credentials_no_host_identity_no_private_paths': True,
        'spectre_runs': 0,
        'oa_writes': 0,
        # these are not results of this round; they are the boundaries the round did not cross,
        # written so no later reader can upgrade an RTL pass into an analogue or optical claim
        'reserved_statuses': {
            'PWM_MOS_IMPLEMENTATION': 'NOT_RUN',
            'PAM_8LEVEL_ANALOG_IMPLEMENTATION': 'NOT_RUN',
            'HYBRID_CURRENT_INTEGRATION': 'NOT_RUN',
            'GRAY_LUT_IMPLEMENTATION': 'NOT_RUN',
            'OPTICAL_EFFECTIVE_BITS': 'NOT_VERIFIED',
            'PHYSICAL_CDC_AND_SKEW': 'NOT_VERIFIED',
            'NEW_SPECTRE_RUNS': 0,
            'NEW_OA_WRITES': 0,
            'LAYOUT_DRC_LVS_PEX': 'NOT_RUN',
            'SOA_SIGNOFF': 'NO',
            'COMPLETION_LEVEL': 'RTL_LOGIC_VERIFIED',
        },
    }


def manifest_json(run_dir, env_json, main_n, ctl_n, sample_n):
    files = {}
    for name in sorted(os.listdir(run_dir)):
        if name.endswith('.vcd'):
            continue                                  # full traces stay local, by design
        p = os.path.join(run_dir, name)
        if os.path.isfile(p):
            files[name] = {'bytes': os.path.getsize(p), 'sha256': sha256(p)}
    src = {}
    for rel in (RTL, TB, os.path.join(HERE, 'dd1_d7a_check.py'), os.path.join(HERE, 'dd1_d7a_trace.py'),
                os.path.join(HERE, 'dd1_d7a_run.py'),
                os.path.join(PROJ, 'reports', 'dd1_d7a_contract.md')):
        src[os.path.relpath(rel, PROJ).replace('\\', '/')] = sha256(rel)
    ev = {}
    for name in sorted(os.listdir(EVIDENCE)):
        if name.startswith('dd1_d7a_'):
            p = os.path.join(EVIDENCE, name)
            ev[name] = {'bytes': os.path.getsize(p), 'sha256': sha256(p)}
    return {'task': 'DATA-7A', 'run_id': os.path.basename(run_dir), 'sources': src,
            'run_artifacts': files, 'evidence': ev,
            'counts': {'main_cases': main_n, 'control_cases': ctl_n, 'edge_samples': sample_n,
                       'instance_observations': main_n * 2},
            'traces_kept_local': sorted([n for n in os.listdir(run_dir) if n.endswith('.vcd')]),
            'trace_digests': dict((g['vcd'], g['vcd_sha256']) for g in env_json['groups']),
            'reproduce': 'python scripts/dd1_d7a_run.py --selftest && ... --run-rtl/--mutants/'
                        '--synth/--export --out review/dd1_d7a/<run_id>'}


def do_write_guard(args):
    """dry-run, refused runs and empty result sets must not disturb a real non-empty evidence file"""
    path = os.path.join(EVIDENCE, 'dd1_d7a_write_guard.txt')
    seed = (u'DATA-7A write guard record\n'
            u'The official evidence path is only written by --export, atomically, and only after every\n'
            u'gate in the run summary passed. Three refusals are demonstrated below by digest.\n')
    write_atomic(path, seed)
    before = sha256(path)
    lines = ['file=%s' % os.path.relpath(path, PROJ).replace('\\', '/'),
             'seed_sha256=%s' % before]
    ok = []
    try:
        ck.write_rows(os.path.join(EVIDENCE, 'dd1_d7a_cases.csv'), [])
        lines.append('empty_row_set=WROTE_ANYWAY')
        ok.append(False)
    except ck.Refuse as exc:
        lines.append('empty_row_set=REFUSED(%s)' % str(exc)[:60])
        ok.append(sha256(path) == before)
    try:
        do_export({'out': os.path.join(PROJ, 'review', 'dd1_d7a', 'no_such_run')})
        lines.append('missing_run_dir=WROTE_ANYWAY')
        ok.append(False)
    except (ck.Refuse, OSError, IOError, KeyError, ValueError) as exc:
        lines.append('missing_run_dir=REFUSED(%s)' % type(exc).__name__)
        ok.append(sha256(path) == before)
    lines.append('digest_after_attempts=%s' % sha256(path))
    lines.append('digest_unchanged=%s' % (sha256(path) == before))
    verdict = 'PASS' if (all(ok) and sha256(path) == before and len(ok) == 2) else 'FAIL'
    lines.append('WRITE_GUARD: %s' % verdict)
    text = u'\n'.join(lines) + u'\n'
    write_atomic(path, seed + text)
    print(u(text))
    return 0 if verdict == 'PASS' else 1


def do_dry_run(args):
    """environment, input and plan checks only: nothing is compiled, simulated or exported"""
    root, tools, env = find_tools()
    versions = tool_versions(tools, env)
    plan = {}
    rows = main_vectors()
    for name, mode, tdiv, tick in GROUPS:
        plan[name] = len([1 for _c, g, _v in rows if g == name])
    ctl = control_scenarios()
    mx = mixed_vectors()
    out = {'tool_root_label': '<D7A_TOOL_ROOT>', 'tools': sorted(tools),
           'versions': {k: v['version'] for k, v in versions.items()},
           'planned_main_groups': plan, 'planned_main_total': sum(plan.values()),
           'planned_control': len(ctl), 'planned_mixed': len(mx),
           'frozen_digests': dict((k, FROZEN_DIGESTS[k]) for k in FROZEN_DIGESTS),
           'frozen_verified': {}, 'rtl': os.path.relpath(RTL, PROJ).replace('\\', '/'),
           'rtl_sha256': sha256(RTL), 'tb_sha256': sha256(TB),
           'spectre_runs': 0, 'oa_writes': 0,
           'would_write': 'review/dd1_d7a/<run_id> only; results/evidence needs --export'}
    for rel, want in sorted(FROZEN_DIGESTS.items()):
        p = os.path.join(PROJ, rel.replace('/', os.sep))
        got = sha256(p) if os.path.exists(p) else 'MISSING'
        out['frozen_verified'][rel] = 'MATCH' if got == want else 'MISMATCH(%s)' % got[:12]
    print(json.dumps(out, indent=1, sort_keys=True))
    bad = [v for v in out['frozen_verified'].values() if not v.startswith('MATCH')]
    if out['planned_main_total'] != 1536 or bad:
        print('DRY_RUN: FAIL')
        return 1
    print('DRY_RUN: PASS')
    return 0


def do_selftest(args):
    bad, report = ck.selftest()
    print(report)
    print('CHECKER_SELFTEST: %s' % ('PASS' if bad == 0 else 'FAIL (%d)' % bad))
    run_dir = args.get('out')
    if run_dir and bad == 0:
        d = os.path.abspath(run_dir)
        os.path.isdir(d) or os.makedirs(d)
        write_atomic(os.path.join(d, 'checker_selftest.txt'), report + '\n')
    return 0 if bad == 0 else 1


def parse_args(argv):
    a = {'out': None, 'timeout': '1800'}
    i = 0
    while i < len(argv):
        k = argv[i]
        if k in ('--selftest', '--dry-run', '--run-rtl', '--mutants', '--synth', '--export',
                 '--write-guard-demo'):
            a['mode'] = k[2:]
        elif k in ('--out', '--timeout'):
            i += 1
            a[k[2:]] = argv[i]
        else:
            raise SystemExit('unknown argument %s' % k)
        i += 1
    return a


def main(argv):
    a = parse_args(argv[1:])
    mode = a.get('mode')
    if mode is None:
        print(__doc__)
        return 2
    if mode == 'selftest':
        return do_selftest(a)
    if mode == 'dry-run':
        return do_dry_run(a)
    if mode == 'write-guard-demo':
        return do_write_guard(a)
    if not a['out']:
        raise SystemExit('--out <run dir> is required for %s' % mode)
    if mode == 'run-rtl':
        return do_run(a)
    if mode == 'mutants':
        return do_mutants(a)
    if mode == 'synth':
        return do_synth(a)
    if mode == 'export':
        return do_export(a)
    raise SystemExit('unhandled mode %s' % mode)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
