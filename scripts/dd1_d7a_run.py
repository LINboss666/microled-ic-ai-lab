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

TASK_REVISION = 'DATA-7A-R3'

MODE_PURE, MODE_HYBRID = ck.MODE_PURE, ck.MODE_HYBRID
GROUPS = (('pure_t30', MODE_PURE, 3, 30), ('pure_t50', MODE_PURE, 5, 50),
          ('hyb_t120', MODE_HYBRID, 12, 120), ('hyb_t200', MODE_HYBRID, 20, 200))
GROUP_NAMES = set(g[0] for g in GROUPS)
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
        exe = None
        for cand in (os.path.join(root, 'bin', name + '.exe'), os.path.join(root, 'bin', name)):
            if os.path.exists(cand):
                exe = cand
                break
        if exe is None:
            exe = _which(name)
        if exe is None:
            raise SystemExit('BLOCKED_TOOLCHAIN: %s is not available under %s or on PATH; this round '
                             'needs a four-state simulator and an independent synthesis front end'
                             % (name, root))
        tools[name] = exe
    return root, tools, env


def _which(name):
    """POSIX fallback so the same runner works on the reviewer's Linux box without .exe names"""
    null = open(os.devnull, 'wb')
    try:
        out = subprocess.check_output(['which', name], stderr=null)
        return out.decode('utf-8', 'replace').strip() or None
    except Exception:                                          # noqa: BLE001
        return None


def tool_versions(tools, env):
    out = {}
    for name, exe in sorted(tools.items()):
        args = [exe, '-V'] if name != 'yosys' else [exe, '-V']
        rc, txt = call(args, env, 60)
        first = (txt or '').split('\n')[0].strip()
        out[name] = {'rc': rc, 'executable': os.path.basename(exe), 'version': first,
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
    """the state and exception matrix, one scenario per named case

    Every scenario declares the stimulus it expects to see in its own trace segment. The checker
    compares that declaration against the trace before it judges the design, so a scenario cannot
    pass because it was named in a JSON file -- a case whose declared codes, PAM values, modes,
    assertion phases or stall phase never happened is reported as STIMULUS_UNATTESTED.
    """
    s = []

    def add(cid, profile, mode, tdiv, kind, name, pure=0, ht=0, pam=0, pure_b=None, ht_b=None,
            pam_b=None, p1=0, p2=0, p3=0, p4=0, windows=None, mode_values=None, abort=None,
            phase=None, pulse_width_ns=None, stall_phase=None, proto_err_bit=None,
            expect='pass', **kw):
        """windows is a list per emission window of (mode, time code, pam code) as it must read back"""
        if pulse_width_ns and not p4:
            p4 = int(pulse_width_ns)
        pb = pure if pure_b is None else pure_b
        hb = ht if ht_b is None else ht_b
        pamb = pam if pam_b is None else pam_b
        d = {'case_id': cid, 'profile': profile, 'kind': kind, 'name': name,
             'mode': ck.MODE_NAME[mode], 'tick_ns': tdiv * 10,
             'p1': p1, 'p2': p2, 'p3': p3, 'p4': p4,
             'windows': windows if windows is not None else [],
             'mode_values': mode_values if mode_values is not None else [],
             'expect': expect}
        for key, val in (('abort', abort), ('phase', phase), ('pulse_width_ns', pulse_width_ns),
                         ('stall_phase', stall_phase), ('proto_err_bit', proto_err_bit)):
            if val is not None:
                d[key] = val
        d.update(kw)
        s.append((cid, vector_line(cid, profile, mode, pure, pb, ht, hb, pam, pamb, tdiv,
                                   p1, p2, p3, p4), d))

    # --- 1. power-up, no configuration, repeated reset
    add(2001, 16, MODE_PURE, 3, 'dark_only', 'power-up, blank released, never configured',
        mode_values=[0])
    add(2002, 17, MODE_PURE, 3, 'dark_only',
        'power-on reset plus two repeated reset pulses, never configured', reset_pulses=3)
    add(2003, 4, MODE_PURE, 3, 'no_auto_resume', 'reset in the middle of a running window',
        pure=128, p1=20, abort='reset_fall',
        windows=[('PURE', 128, 7)], phase='mid_window')
    # --- 2. PWM_START: held, single, and same-edge conflicts
    add(2004, 5, MODE_PURE, 3, 'start_held_40ns_once', 'PWM_START held high through the window',
        pure=200, windows=[('PURE', 200, 7)])
    add(2005, 0, MODE_PURE, 3, 'window_ok', 'PWM_START held 40 ns, accepted as one event',
        pure=7, windows=[('PURE', 7, 7)])
    add(2006, 27, MODE_PURE, 3, 'refused_then_window',
        'LATCH while armed is refused and does not re-commit',
        pure=11, proto_err_bit=ck.E_LATCH_REJECTED, windows=[('PURE', 11, 7)])
    add(2007, 28, MODE_PURE, 3, 'start_latch_same_edge',
        'LATCH and START on the same sampling edge: LATCH wins, start refused',
        pure=18, proto_err_bit=ck.E_START_REJECTED)
    # --- 3. ticks that must not be consumed, and clock stalls
    add(2008, 6, MODE_PURE, 3, 'tick_in_blank_consumed',
        'ticks during blank and before the accepted start consume nothing',
        pure=40, windows=[('PURE', 40, 7)])
    add(2009, 11, MODE_PURE, 3, 'clock_stall', 'reference-clock stall after the window completed',
        pure=90, stall_phase='done', p1=200, windows=[('PURE', 90, 7)])
    add(2010, 26, MODE_PURE, 3, 'clock_stall', 'reference-clock stall DURING a running window',
        pure=200, stall_phase='running', p1=30, p2=200,
        windows=[('PURE', 200, 7)])
    # --- 4. asynchronous shut-off at the required phases, including the minimum pulse
    add(2011, 2, MODE_PURE, 3, 'async_off_between_edges',
        'blank asserted in the middle of a running window, held past the abort',
        pure=150, p1=60, phase='mid_window', windows=[('PURE', 150, 7)])
    add(2012, 2, MODE_PURE, 3, 'no_auto_resume',
        'blank withdrawn does not resume the aborted window', pure=150, p1=60,
        abort='blank_rise', windows=[('PURE', 150, 7)])
    add(2013, 3, MODE_PURE, 3, 'async_off_between_edges',
        'fault asserted in the middle of a running window, held past the abort',
        pure=150, p1=60, p2=1, phase='mid_window', windows=[('PURE', 150, 7)])
    add(2014, 3, MODE_PURE, 3, 'no_auto_resume',
        'fault cleared does not resume the aborted window', pure=150, p1=60, p2=1,
        abort='fault_rise', windows=[('PURE', 150, 7)])
    add(2015, 25, MODE_PURE, 3, 'async_off_between_edges',
        'blank asserted in the middle of the shortest conducting pulse',
        pure=1, p1=0, p2=0, p3=25, phase='short_pulse_middle', pulse_width_ns=20,
        windows=[('PURE', 1, 7)])
    add(2016, 25, MODE_PURE, 3, 'async_off_between_edges',
        'blank asserted in the last interval before the window endpoint',
        pure=254, p1=255, p2=0, p3=15, phase='near_window_end', pulse_width_ns=20,
        windows=[('PURE', 254, 7)])
    add(2017, 25, MODE_PURE, 3, 'async_off_between_edges',
        'blank asserted just after the window endpoint, with nothing running to abort',
        pure=254, p1=257, p2=0, p3=12, phase='after_window_end', pulse_width_ns=20,
        windows=[('PURE', 254, 7)])
    add(2018, 25, MODE_HYBRID, 12, 'async_off_between_edges',
        'fault asserted mid-window at the Hybrid tick, off the clock edge',
        ht=40, p1=20, p2=1, p3=7, phase='mid_window', pulse_width_ns=20, mode_values=[1],
        windows=[('HYBRID', 40, 0)])
    # --- 5. recovery sequences after an abort: the three incomplete ones must stay dark
    add(2019, 21, MODE_PURE, 3, 'abort_reauthorise',
        'abort, then a bare START with the old config: must stay dark',
        pure=100, p1=20, proto_err_bit=ck.E_START_REJECTED)
    add(2020, 22, MODE_PURE, 3, 'abort_reauthorise',
        'abort, then a new load but no LATCH, then START: must stay dark',
        pure=100, p1=20, p3=9, proto_err_bit=ck.E_START_REJECTED)
    add(2021, 20, MODE_PURE, 3, 'config_freshness',
        'a second LATCH with no new load is refused and does not step the version',
        pure=64, proto_err_bit=ck.E_STALE_CONFIG)
    add(2022, 23, MODE_PURE, 3, 'mode_bypass',
        'a LATCH under system_en=1 must not adopt a mode refused in the unsafe phase',
        pure=77, ht_b=63, pam_b=6, proto_err_bit=ck.E_MODE_NOT_ADOPTED, mode_values=[0, 1],
        windows=[('PURE', 77, 7)], aborted_windows=[0])
    add(2023, 24, MODE_PURE, 3, 'recover_full_sequence',
        'abort, then a complete new load / LATCH / start displays again',
        pure=100, p1=20, p3=9, windows=[('PURE', 100, 7), ('PURE', 9, 7)],
        aborted_windows=[0])
    # --- 6. display copies and code boundaries
    add(2024, 1, MODE_PURE, 3, 'display_frozen',
        'next grey code loaded during a running window changes neither waveform nor PAM hold',
        pure=120, p1=20, p2=5, windows=[('PURE', 120, 7)])
    add(2025, 13, MODE_HYBRID, 12, 'pam_toggle',
        'PAM codes 0 then 7 in consecutive windows, held through each off tail',
        ht=30, pam=0, pam_b=7, windows=[('HYBRID', 30, 0), ('HYBRID', 30, 7)])
    add(2026, 13, MODE_HYBRID, 20, 'pam_toggle',
        'PAM codes 7 then 0 in consecutive windows', ht=63, pam=7, pam_b=0,
        windows=[('HYBRID', 63, 7), ('HYBRID', 63, 0)])
    add(2027, 14, MODE_PURE, 3, 'code_edges', 'full window then the shortest pulse',
        pure=255, p3=1, windows=[('PURE', 255, 7), ('PURE', 1, 7)])
    add(2028, 14, MODE_PURE, 5, 'code_edges', 'shortest pulse then full window',
        pure=1, p3=255, windows=[('PURE', 1, 7), ('PURE', 255, 7)])
    add(2029, 14, MODE_HYBRID, 12, 'code_edges', 'Hybrid 62 then 63 at the 100 Hz tick',
        ht=62, pam=4, p3=63, windows=[('HYBRID', 62, 4), ('HYBRID', 63, 4)])
    add(2030, 14, MODE_HYBRID, 20, 'code_edges', 'Hybrid 63 then black at the 60 Hz tick',
        ht=63, pam=7, p3=0, windows=[('HYBRID', 63, 7), ('HYBRID', 0, 7)])
    add(2031, 18, MODE_PURE, 3, 'mode_switch_safe',
        'legal mode switch in the safe phase, then the new mode really displays',
        pure=77, ht_b=63, pam_b=6, p1=1, p2=77, p3=63, p4=6, mode_values=[0, 1],
        windows=[('PURE', 77, 7), ('HYBRID', 63, 6)])
    # --- 7. refusals
    add(2032, 7, MODE_PURE, 3, 'refused_then_window',
        'mode changed while a window runs is refused and the running window keeps its own mode',
        pure=60, p1=20, proto_err_bit=ck.E_MODE_WHILE_RUNNING, mode_values=[0, 1],
        windows=[('PURE', 60, 7)])
    add(2033, 8, MODE_HYBRID, 12, 'refused_dark', 'illegal mode code 2 is refused and stays dark',
        ht=20, pam=3, proto_err_bit=ck.E_ILLEGAL_MODE, mode_values=[0, 2])
    add(2034, 9, MODE_PURE, 3, 'refused_dark', 'LATCH with cfg_valid low is refused',
        pure=33, proto_err_bit=ck.E_INCOMPLETE_CFG)
    add(2035, 10, MODE_PURE, 3, 'refused_then_window',
        'LATCH on the same edge as the load is refused, the later clean sequence works',
        pure=66, proto_err_bit=ck.E_LATCH_AMBIGUOUS, windows=[('PURE', 66, 7)])
    add(2036, 19, MODE_PURE, 3, 'window_ok',
        'an unknown code bus must be refused, never converted to a number',
        xprobe='cfg_pure held X through the LATCH', expect='refusal')
    # --- 8. the next/display copies, and an abort that also revokes a prepared load
    add(2037, 29, MODE_PURE, 3, 'next_window_commit',
        'next loaded inside window A, committed only after A completes, and B really uses it',
        pure=120, p3=200, p4=7, windows=[('PURE', 120, 7), ('PURE', 200, 7)])
    add(2038, 29, MODE_PURE, 5, 'next_window_commit',
        'the same grey code re-presented as a new load still commits and still steps the version',
        pure=100, p3=100, p4=7, windows=[('PURE', 100, 7), ('PURE', 100, 7)])
    add(2039, 29, MODE_HYBRID, 12, 'next_window_commit',
        'a Hybrid next changes both the time code and the PAM select in the second window',
        ht=20, pam=2, p3=45, p4=6, mode_values=[1],
        windows=[('HYBRID', 20, 2), ('HYBRID', 45, 6)])
    add(2040, 30, MODE_PURE, 3, 'abort_pending',
        'a blank abort withdraws the load that was prepared but never consumed before it',
        pure=150, p1=60, p2=0, p3=5, p4=7, windows=[('PURE', 150, 7)])
    add(2041, 30, MODE_PURE, 3, 'abort_pending',
        'a fault abort withdraws the load that was prepared but never consumed before it',
        pure=150, p1=60, p2=1, p3=5, p4=7, windows=[('PURE', 150, 7)])
    add(2042, 32, MODE_PURE, 3, 'abort_pending_recover',
        'after the revocation an invalid request stays dark and a new load / LATCH / start recovers',
        pure=150, p1=60, p2=0, p3=5, p4=9, commit_latches=[0, 2],
        windows=[('PURE', 150, 7), ('PURE', 9, 7)], aborted_windows=[0])
    add(2043, 31, MODE_HYBRID, 12, 'abort_pending_recover',
        'a fault abort then a genuinely new Hybrid load restores the display on the new code',
        ht=40, pam=3, p1=20, p2=1, p3=5, p4=30, mode_values=[1],
        windows=[('HYBRID', 40, 3), ('HYBRID', 30, 3)], aborted_windows=[0])
    return s


def mixed_vectors():
    """two channels with different codes behind common control, reported apart from the 1536"""
    rows = []
    combos = [
        (MODE_PURE, 1, 255, 0, 0, 0, 3, 7),
        (MODE_PURE, 254, 0, 0, 0, 0, 5, 7),
        (MODE_PURE, 0, 128, 0, 0, 0, 3, 7),
        (MODE_HYBRID, 0, 0, 1, 63, 5, 12, 2),
        (MODE_HYBRID, 0, 0, 62, 0, 0, 20, 7),
        (MODE_HYBRID, 0, 0, 0, 63, 7, 12, 1),
    ]
    cid = MIXED_BASE
    for mode, pa, pb, ha, hb, pama, tdiv, pamb in combos:
        wa = ('PURE', pa, 7) if mode == MODE_PURE else ('HYBRID', ha, pama)
        wb = ('PURE', pb, 7) if mode == MODE_PURE else ('HYBRID', hb, pamb)
        rows.append((cid,
                     vector_line(cid, 15, mode, pa, pb, ha, hb, pama, pamb, tdiv),
                     {'case_id': cid, 'profile': 15, 'kind': 'mixed_codes',
                      'name': 'mixed codes %s A=%s B=%s' % (ck.MODE_NAME[mode], wa[1], wb[1]),
                      'mode': ck.MODE_NAME[mode], 'tick_ns': tdiv * 10, 'expect': 'pass',
                      'windows': [wa], 'windows_b': [wb],
                      'p1': 0, 'p2': 0, 'p3': 0, 'p4': 0}))
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
    # the bytes that were actually compiled, so a source edited while the simulations were in flight
    # cannot be recorded as if it had produced them
    at_compile = {'rtl_sha256': sha256(RTL), 'tb_sha256': sha256(TB),
                  'checker_sha256': sha256(os.path.join(HERE, 'dd1_d7a_check.py')),
                  'reader_sha256': sha256(os.path.join(HERE, 'dd1_d7a_trace.py'))}
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
        'task_revision': TASK_REVISION,
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
    }
    now_src = {'rtl_sha256': sha256(RTL), 'tb_sha256': sha256(TB),
               'checker_sha256': sha256(os.path.join(HERE, 'dd1_d7a_check.py')),
               'reader_sha256': sha256(os.path.join(HERE, 'dd1_d7a_trace.py'))}
    drift = sorted(k for k in at_compile if at_compile[k] != now_src[k])
    if drift:
        raise ck.Refuse('the sources changed while this run was in flight: %s. The traces belong to '
                        'the bytes that were compiled, so nothing is recorded under the new digests'
                        % ', '.join(drift))
    summary.update(at_compile)
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


"""failure models, split into what they actually break

The previous table called two entries "functional" while they only masked an error bit: the design
still behaved correctly, so the entry proved the diagnostic path and nothing else. Every model here
declares a category and a fault that must be *seen in the mutant's own trace* before the unchanged
checker's refusal counts. A model whose fault cannot be observed is reported as FAULT_NOT_EXERCISED
and the gate fails; that is a real bug in the model, not a pass.
"""

# category: 'functional'  the described wrong behaviour happens on the outputs
#           'diagnostic'  only a refusal bit disappears; the behaviour stays correct
MUTANTS = {
    # ------------------------------------------------------------------ original six, unchanged
    'pure255_only255': {
        'category': 'functional',
        'find': 'wire [8:0] pure_iv  = (cfg_pure == 8\'d255)    ? FULL_PURE : {1\'b0, cfg_pure};',
        'sub':  'wire [8:0] pure_iv  = {1\'b0, cfg_pure};',
        'trigger': ('main', MODE_PURE, 255, 3),
        'expect': ['ON_WIDTH', 'WIDTH_NOT_MULTIPLE'],
        'fault': {'kind': 'width_ticks_short_by', 'idx': 0, 'ticks': 1},
        'note': 'code 255 conducts 255 of 256 intervals, so the full window is one interval short',
    },
    'counter_rollover_reopens': {
        'category': 'functional',
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
        'fault': {'kind': 'segments_at_least', 'idx': 0, 'n': 2},
        'note': 'the interval counter rolls over and opens the output again after the window end',
    },
    'blank_gate_removed': {
        'category': 'functional',
        'find': "assign data_en     = run_q & ~blank & ~fault & reset_n;",
        'sub':  "assign data_en     = run_q & ~fault & reset_n;",
        'trigger': ('control', 2011),
        'expect': ['ASYNC_OFF'],
        'fault': {'kind': 'data_en_high_at_assert', 'sig': 'blank', 'idx': 0},
        'note': 'the blank assertion no longer pulls the enable down between clock edges',
    },
    'start_level_rearm': {
        'category': 'functional',
        'find': '            if (start_ok) begin',
        'sub':  '            if (pwm_start & ~fault & reset_n) begin',
        'trigger': ('control', 2004),
        'expect': ['SEGMENT_COUNT', 'ON_WIDTH', 'NO_DEASSERTION'],
        'fault': {'kind': 'segments_at_least', 'idx': 0, 'n': 2},
        'note': 'a held PWM_START re-clears the counter on every reference edge',
    },
    'instance_b_late_one_reference_cycle': {
        'category': 'functional',
        'find': 'wire tick_accept = tick & window_active & ~async_block;',
        'sub':  'reg tick_dly;\n    always_ff @(posedge clk or negedge reset_n) tick_dly <= reset_n ? tick : 1\'b0;\n'
                '    wire tick_accept = tick_dly & window_active & ~async_block;',
        'trigger': ('main', MODE_PURE, 12, 3),
        'expect': ['INSTANCES_DIFFER', 'ON_START'],
        'fault': {'kind': 'on_minus_own_t0_ps', 'idx': 1, 'ps': 10000},
        'b_module': True,
        'note': 'channel B samples the tick one reference cycle (10 ns) later, so its own first '
                'accepted tick lands one clock after channel A\'s',
    },
    'instance_b_tick_late_two_cycles': {
        'category': 'functional',
        'find': 'wire tick_accept = tick & window_active & ~async_block;',
        'sub':  'reg [2:0] tick_sr;\n    always_ff @(posedge clk or negedge reset_n) begin\n'
                '        if (!reset_n) tick_sr <= 3\'b000;\n'
                '        else tick_sr <= {tick_sr[1:0], tick};\n'
                '    end\n'
                '    wire tick_accept = tick_sr[2] & window_active & ~async_block;',
        'trigger': ('main', MODE_PURE, 12, 3),
        'expect': ['INSTANCES_DIFFER', 'ON_START'],
        'fault': {'kind': 'own_t0_late_by_ps', 'ps': 20000},
        'b_module': True,
        'note': 'the tick channel B sees is stretched over three registers, so the first tick B '
                'actually accepts is consumed two reference cycles after the one A accepts: B starts '
                'its whole window late. This is the wording the previous round used loosely as '
                '"one tick late"; the measured skew is what this row states.',
    },
    'auto_resume_after_abort': {
        'category': 'functional',
        'find': 'wire window_active = (state_q == S_ARMED) || (state_q == S_RUN);',
        'sub':  'wire window_active = (state_q == S_ARMED) || (state_q == S_RUN) ||\n'
                '                       ((state_q == S_ABORT) && !blank && !fault);',
        'trigger': ('control', 2012),
        'expect': ['AUTO_RESUME', 'NO_ABORT_RECORDED'],
        'fault': {'kind': 'light_after_abort_no_new_load', 'idx': 0},
        'note': 'withdrawing blank resumes the aborted window instead of requiring a new start',
    },
    # ------------------------------------------------------------------ new functional models
    'abort_reauthorises_display': {
        'category': 'functional',
        'find': "                state_q        <= S_ABORT;\n                run_q          <= 1'b0;\n"
                "                auth_q         <= 1'b0;\n                load_pending_q <= 1'b0;",
        'sub':  "                state_q        <= S_ABORT;\n                run_q          <= 1'b0;\n"
                "                auth_q         <= auth_q;\n                load_pending_q <= 1'b0;",
        'trigger': ('control', 2019),
        'expect': ['LIGHT_AFTER_REFUSAL', 'REFUSAL_NOT_RECORDED', 'VERSION_STEPPED'],
        'fault': {'kind': 'light_after_abort_no_new_load', 'idx': 0},
        'note': 'an abort leaves the old display authorised, so a bare start re-lights it',
    },
    'abort_keeps_pending_config': {
        'category': 'functional',
        'find': "                state_q        <= S_ABORT;\n                run_q          <= 1'b0;\n"
                "                auth_q         <= 1'b0;\n                load_pending_q <= 1'b0;",
        'sub':  "                state_q        <= S_ABORT;\n                run_q          <= 1'b0;\n"
                "                auth_q         <= 1'b0;",
        'trigger': ('control', 2040),
        'expect': ['LIGHT_AFTER_REFUSAL', 'REFUSAL_NOT_RECORDED', 'VERSION_STEPPED'],
        'fault': {'kind': 'version_and_light_after_abort', 'idx': 0},
        'note': 'the reviewed T1 behaviour: a load prepared before the abort still authorises the '
                'display afterwards, with no new load transaction anywhere after the abort',
    },
    'stale_latch_really_accepted': {
        'category': 'functional',
        'find': 'wire latch_ok  = latched & phase_ok & mode_legal & cfg_valid & load_pending_q',
        'sub':  'wire latch_ok  = latched & phase_ok & mode_legal & cfg_valid',
        'trigger': ('control', 2021),
        'expect': ['VERSION_STEPPED', 'REFUSAL_NOT_RECORDED'],
        'fault': {'kind': 'version_steps_at_least', 'idx': 0, 'n': 2},
        'note': 'a second LATCH behind one load commits again and steps the version; cfg_valid stays '
                'high in this scenario so nothing else refuses it first',
    },
    'latch_really_adopts_mode': {
        'category': 'functional',
        'find': '                   & mode_matches_accepted & ~ambiguous;',
        'sub':  '                   & ~ambiguous;\n'
                '    wire mode_via_latch = latched & ~mode_matches_accepted;',
        'trigger': ('control', 2022),
        'expect': ['MODE_ADOPTED', 'VERSION_STEPPED', 'REFUSAL_NOT_RECORDED'],
        'sub2': {'find': "                pam_q          <= (mode == M_HYB) ? cfg_hyb_pam : PAM_TOP_SYMBOL;",
                 'sub': "                pam_q          <= (mode == M_HYB) ? cfg_hyb_pam : PAM_TOP_SYMBOL;\n"
                        "                disp_mode_q    <= mode;"},
        'fault': {'kind': 'pam_shows', 'idx': 0, 'value': '110'},
        'note': 'the LATCH path takes over mode adoption that only the safe phase may do, and the '
                'adopted Hybrid PAM select appears on pam_sel',
    },
    'mixed_b_output_late_three_cycles': {
        'category': 'functional',
        'find': "    assign data_en     = run_q & ~blank & ~fault & reset_n;",
        'sub': "    logic delayed_run_q_1, delayed_run_q_2, delayed_run_q_3;\n"
               "    always_ff @(posedge clk or negedge reset_n) begin\n"
               "        if (!reset_n) begin\n"
               "            delayed_run_q_1 <= 1'b0; delayed_run_q_2 <= 1'b0; delayed_run_q_3 <= 1'b0;\n"
               "        end else begin\n"
               "            delayed_run_q_1 <= run_q; delayed_run_q_2 <= delayed_run_q_1;\n"
               "            delayed_run_q_3 <= delayed_run_q_2;\n"
               "        end\n"
               "    end\n"
               "    assign data_en     = delayed_run_q_3 & ~blank & ~fault & reset_n;",
        'trigger': ('mixed', 3001),
        'expect': ['ON_START', 'ON_WIDTH', 'MIXED_WIDTH'],
        'fault': {'kind': 'on_minus_own_t0_ps', 'idx': 1, 'ps': 30000},
        'b_module': True,
        'note': 'channel B opens three reference edges after its own t0, same width, same state path',
    },
    'mixed_b_output_late_one_cycle': {
        'category': 'functional',
        'find': "    assign data_en     = run_q & ~blank & ~fault & reset_n;",
        'sub': "    logic delayed_run_q_c;\n"
               "    always_ff @(posedge clk or negedge reset_n) delayed_run_q_c <= reset_n ? run_q : 1'b0;\n"
               "    assign data_en     = delayed_run_q_c & ~blank & ~fault & reset_n;",
        'trigger': ('mixed', 3001),
        'expect': ['ON_START', 'ON_WIDTH', 'MIXED_WIDTH'],
        'fault': {'kind': 'on_minus_own_t0_ps', 'idx': 1, 'ps': 10000},
        'b_module': True,
        'note': "the reviewer's own probe: B lights 10 ns late, which is smaller than any tick and "
                "was invisible while t0 was derived from the shared stimulus",
    },
    'mixed_b_one_interval_short': {
        'category': 'functional',
        'find': '                    run_q   <= (index_q < target_q);',
        'sub':  "                    run_q   <= (index_q + 9'd1 < target_q);",
        'trigger': ('mixed', 3001),
        'expect': ['MIXED_WIDTH', 'ON_WIDTH', 'ON_SPAN'],
        'fault': {'kind': 'width_ticks_short_by', 'idx': 1, 'ticks': 1},
        'b_module': True,
        'note': 'channel B closes one interval early, so its own width no longer matches its code',
    },
    # ------------------------------------------------------------- diagnostic-bit models, not fake
    'stale_latch_error_bit_masked': {
        'category': 'diagnostic',
        'find': "            if (latched & ~load_pending_q)               err_stale_q      <= 1'b1;",
        'sub':  "            if (1'b0)                                  err_stale_q      <= 1'b1;",
        'trigger': ('control', 2021),
        'expect': ['REFUSAL_NOT_RECORDED'],
        'fault': {'kind': 'bit_absent', 'idx': 0, 'bit': 64, 'request': 'latch_stb'},
        'note': 'only the STALE_CONFIG record disappears: the design still refuses the replay, so '
                'this model covers the diagnostic path and is not counted as a functional failure',
    },
    'mode_unset_error_bit_masked': {
        'category': 'diagnostic',
        'find': "            if (latched & ~mode_matches_accepted)        err_mode_unset_q <= 1'b1;",
        'sub':  "            if (1'b0)                                  err_mode_unset_q <= 1'b1;",
        'trigger': ('control', 2022),
        'expect': ['REFUSAL_NOT_RECORDED'],
        'fault': {'kind': 'bit_absent', 'idx': 0, 'bit': 128, 'request': 'latch_stb'},
        'note': 'only the MODE_NOT_ADOPTED record disappears; the LATCH is still refused, so this is '
                'a diagnostic-coverage model, not the functional bypass',
    },
}


def _mutant_case_id(spec):
    kind = spec['trigger'][0]
    return 501 if kind == 'main' else spec['trigger'][1]


def _scenario_rows(spec, run_id):
    """the scenario list the mutant trace has to be judged against, plus its trace file name"""
    kind = spec['trigger'][0]
    if kind == 'control':
        cid = spec['trigger'][1]
        scen = [d for c, v, d in control_scenarios() if c == cid]
        return scen, 'control'
    if kind == 'mixed':
        cid = spec['trigger'][1]
        scen = [d for c, v, d in mixed_vectors() if c == cid]
        return scen, 'mixed'
    return None, 'main'


def attest_fault(vcd, spec, case_id):
    """prove from the mutant's own trace that the failure this model claims really happened"""
    kind = spec['kind']
    idx = int(spec.get('idx', 0))
    tr = tv.Trace(vcd)
    sm = ck.SigMap(tr)
    seg = dict((cid, (cs, ce)) for cid, cs, ce in ck.cases(tr, sm))
    if case_id not in seg:
        return False, 'case %s is not in the mutant trace' % case_id
    cs, ce = seg[case_id]
    if kind == 'data_en_high_at_assert':
        rises = tr.rises(sm.i(spec['sig']), cs + 1, ce)
        if not rises:
            return False, 'no %s assertion in the case' % spec['sig']
        t = rises[0]
        v = tr.value_at(sm.o(idx, 'data_en'), t)
        return (v == '1'), '%s.data_en is %s at the %s rise (%s ns)' % (sm.tag[idx], v, spec['sig'],
                                                                        ck.fmt_ns(t))
    if kind == 'light_after_abort_no_new_load':
        aborts = tr.rises(sm.i('blank'), cs + 1, ce) + tr.rises(sm.i('fault'), cs + 1, ce)
        if not aborts:
            return False, 'no abort event in the case'
        t_abort = min(aborts)
        late = tr.rises(sm.o(idx, 'data_en'), t_abort + 1, ce)
        loads = [t for t in tr.rises(sm.i('cfg_valid'), t_abort + 1, late[0] if late else ce)]
        if not late:
            return False, 'the output never re-opened after the abort'
        return (not loads), 'output re-opened at %s ns with %d new load edge(s) before it' % (
            ck.fmt_ns(late[0]), len(loads))
    if kind == 'version_and_light_after_abort':
        aborts = tr.rises(sm.i('blank'), cs + 1, ce) + tr.rises(sm.i('fault'), cs + 1, ce)
        if not aborts:
            return False, 'no abort event in the case'
        t_abort = min(aborts)
        steps = [t for t, _v in tr.edges(sm.o(idx, 'cfg_version')) if t > t_abort]
        late = tr.rises(sm.o(idx, 'data_en'), t_abort + 1, ce)
        loads = [t for t in tr.rises(sm.i('cfg_valid'), t_abort + 1, ce)]
        ok = bool(steps) and bool(late) and not loads
        return ok, 'version edges after abort=%d, later light=%s, new load edges=%d' % (
            len(steps), bool(late), len(loads))
    if kind == 'version_steps_at_least':
        steps = [t for t, _v in tr.edges(sm.o(idx, 'cfg_version')) if cs <= t <= ce - 1]
        return (len(steps) >= int(spec['n'])), '%d cfg_version edge(s), model claims >= %d' % (
            len(steps), spec['n'])
    if kind == 'pam_shows':
        vals = set(v for _t, v in tr.edges(sm.o(idx, 'pam_sel')) if cs <= _t <= ce - 1)
        return (spec['value'] in vals), 'pam_sel values=%s, model claims %s' % (
            sorted(vals), spec['value'])
    if kind == 'on_minus_own_t0_ps':
        t_bl = tr.falls(sm.i('blank'), cs, ce)
        if not t_bl:
            return False, 'no blank release in the case'
        own_rise, own_t0 = ck._own_t0(tr, sm, idx, cs, t_bl[0], ce - 1)
        rises = tr.rises(sm.o(idx, 'data_en'), cs, ce)
        if own_t0 is None or not rises:
            return False, 'own t0=%s, first light=%s' % (own_t0, rises[:1])
        delta = rises[0] - own_t0
        return (delta == int(spec['ps'])), '%s opens %d ps after its own t0 (%s ns), model says %d' % (
            sm.tag[idx], delta, ck.fmt_ns(own_t0), spec['ps'])
    if kind == 'own_t0_late_by_ps':
        # each channel's own t0 comes from the tick THAT channel accepted: a channel whose tick
        # acceptance is late starts its whole window late, and no shared-stimulus derivation can see
        # it, so the comparison is channel B's own t0 against channel A's own t0
        t_bl = tr.falls(sm.i('blank'), cs, ce)
        if not t_bl:
            return False, 'no blank release in the case'
        _r0, t0a = ck._own_t0(tr, sm, 0, cs, t_bl[0], ce - 1)
        _r1, t0b = ck._own_t0(tr, sm, 1, cs, t_bl[0], ce - 1)
        if t0a is None or t0b is None:
            return False, 'own t0 missing (a=%s b=%s)' % (t0a, t0b)
        delta = t0b - t0a
        return (delta == int(spec['ps'])), 'u_b consumes its first tick %d ps after u_a (%s vs %s ns)' \
            % (delta, ck.fmt_ns(t0b), ck.fmt_ns(t0a))
    if kind == 'width_ticks_short_by':
        w = ck.measure_nth_window(tr, sm, idx, cs, ce, [], 0)
        if not w:
            return False, 'window unreadable'
        got = sum(1 for _a, _b in w['segs'])
        widths = ck._widths_ticks(w['segs'], w['T'])
        short = w['exp'] - (widths[0] if widths else 0)
        return (short >= int(spec['ticks']) and widths or []), 'width=%s ticks, code asks %d' % (
            widths, w['exp'])
    if kind == 'segments_at_least':
        w = ck.measure_nth_window(tr, sm, idx, cs, ce, [], 0)
        n = len(w['segs']) if w else 0
        return (n >= int(spec['n'])), '%d conducting segment(s), model claims >= %d' % (n, spec['n'])
    if kind == 'bit_absent':
        vals = set(v for _t, v in tr.edges(sm.o(idx, 'proto_err')) if cs <= _t <= ce - 1)
        shown = any((int(v, 2) >> (8 - 1 - _bit_index(spec['bit']))) & 1 for v in vals
                    if all(c not in tv.XZ for c in v))
        req = tr.rises(sm.i(spec['request']), cs, ce)
        return ((not shown) and bool(req)), 'bit %d seen=%s, %d request edge(s)' % (
            spec['bit'], shown, len(req))
    raise SystemExit('unknown fault model %r' % kind)


def _bit_index(bit):
    """the proto_err vector is MSB-first, so translate a bit value into a position"""
    for i in range(8):
        if bit == (1 << i):
            return i
    raise SystemExit('not a single proto_err bit: %r' % bit)


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
            rows.append({'class': cls, 'category': spec['category'], 'status': 'PATCH_NOT_APPLIED',
                         'detail': 'the mutation anchor is not present in the current RTL'})
            continue
        mdir = os.path.join(run_dir, 'mutant_%s' % cls)
        os.path.isdir(mdir) or os.makedirs(mdir)
        mutated = base_rtl.replace(spec['find'], spec['sub'], 1)
        if spec.get('sub2') and spec['sub2']['find'] not in mutated:
            rows.append({'class': cls, 'category': spec['category'], 'status': 'PATCH_NOT_APPLIED',
                         'detail': 'the mutation anchor for the second patch is not present'})
            continue
        if spec.get('sub2'):
            mutated = mutated.replace(spec['sub2']['find'], spec['sub2']['sub'], 1)
        tb_src = base_tb
        extra = []
        if spec.get('b_module'):
            mutated = mutated.replace('module dd1_d7a_gray_ctrl (',
                                       'module dd1_d7a_gray_ctrl_mut (', 1)
            io.open(os.path.join(mdir, 'dd1_d7a_gray_ctrl.sv'), 'w', encoding='utf-8',
                    newline='\n').write(u(base_rtl))
            tb_src = base_tb.replace('    dd1_d7a_gray_ctrl u_b (', '    dd1_d7a_gray_ctrl_mut u_b (')
            extra = [os.path.join(mdir, 'dd1_d7a_gray_ctrl.sv')]
        rtl_path = write_atomic(os.path.join(mdir, 'mutant.sv'), mutated)
        tb_path = write_atomic(os.path.join(mdir, 'tb.sv'), tb_src)
        exe, crc, cout = compile_sim(tools, env, mdir, rtl_path, tb_path, tag='mut', extra=extra)
        if crc != 0:
            rows.append({'class': cls, 'category': spec['category'], 'status': 'COMPILE_FAILED',
                         'detail': cout[-300:]})
            continue
        kind = spec['trigger'][0]
        vec_path = os.path.join(mdir, 'vec.txt')
        if kind == 'main':
            _g, mode, code, tdiv = spec['trigger']
            write_atomic(vec_path, vector_line(501, 0, mode, code, code, 0, 0, 0, 0, tdiv) + '\n')
        else:
            cid = spec['trigger'][1]
            src = control_scenarios() if kind == 'control' else mixed_vectors()
            line = [v for c, v, d in src if c == cid][0]
            write_atomic(vec_path, line + '\n')
        vcd = os.path.join(mdir, 'trace.vcd')
        case_id = _mutant_case_id(spec)
        try:
            run_vvp(exe, env, vec_path, vcd, int(args.get('timeout', '900')),
                    os.path.join(mdir, 'vvp.log'))
        except ck.Refuse as exc:
            rows.append({'class': cls, 'category': spec['category'], 'status': 'RUN_FAILED',
                         'detail': str(exc)})
            continue
        try:
            if kind == 'main':
                got = ck.check_main_trace(vcd, run_id)[0]
            else:
                scen, _g = _scenario_rows(spec, run_id)
                got = ck.check_control_trace(vcd, scen, run_id)[0]
        except (tv.VcdError, ck.Refuse) as exc:
            rows.append({'class': cls, 'category': spec['category'], 'status': 'DETECTED',
                         'trigger_case': case_id, 'refused_at_parse': True,
                         'fault_confirmed': True, 'fault_observed': 'the reader itself refused',
                         'detail': str(exc)[:200],
                         'mutant_rtl_sha256': sha256(rtl_path), 'checker': 'same checker'})
            continue
        tags = spec['expect']
        hit = [r for r in got if any(t in r['failures'] for t in tags)]
        confirmed, observed = attest_fault(vcd, spec['fault'], case_id)
        if not confirmed:
            status, detail = 'FAULT_NOT_EXERCISED', observed
        elif hit:
            status, detail = 'DETECTED', hit[0]['failures'][:200]
        else:
            status, detail = 'NOT_DETECTED', 'the original checker accepted the mutated design'
        rows.append({'class': cls, 'category': spec['category'], 'status': status,
                     'trigger_case': case_id, 'fault_confirmed': bool(confirmed),
                     'fault_kind': spec['fault']['kind'], 'fault_observed': observed,
                     'mutant_rtl_sha256': sha256(rtl_path),
                     'checker': 'same checker, unchanged judgement code', 'detail': detail})
    func = [r for r in rows if r['category'] == 'functional']
    diag = [r for r in rows if r['category'] == 'diagnostic']
    ok = len([r for r in rows if r['status'] == 'DETECTED'])
    write_atomic(os.path.join(run_dir, 'mutants.json'), json.dumps(
        {'run_id': run_id, 'detected': ok, 'total': len(MUTANTS),
         'functional_total': len(func),
         'functional_detected': len([r for r in func if r['status'] == 'DETECTED']),
         'diagnostic_total': len(diag),
         'diagnostic_detected': len([r for r in diag if r['status'] == 'DETECTED']),
         'not_exercised': [r['class'] for r in rows if r['status'] == 'FAULT_NOT_EXERCISED'],
         'rows': rows}, indent=1, sort_keys=True) + '\n')
    for r in rows:
        print('%-34s %-11s %-20s %s' % (r['class'], r['category'], r['status'],
                                        str(r.get('fault_observed') or r['detail'])[:64]))
    print('MUTATION_DETECTED=%d/%d (functional %d/%d, diagnostic %d/%d)'
          % (ok, len(MUTANTS), len([r for r in func if r['status'] == 'DETECTED']), len(func),
             len([r for r in diag if r['status'] == 'DETECTED']), len(diag)))
    return 0 if ok == len(MUTANTS) else 1



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
    st = synth_status(rc, txt)
    summary = {'rc': st['entry_rc'], 'yosys_rc': st['yosys_rc'], 'problems': st['problems'],
               'stat_parse': st['stat_parse'],
               'cells': st['cells'], 'cells_total': st['cells_total'],
               'storage': dict((k, v) for k, v in st['cells'].items() if 'ff' in k or 'latch' in k or
                               'mem' in k),
               'check_passes': st['check_passes'],
               'unresolved_modules': len(re.findall(r'module .* is not used|ERROR: Module .* not found',
                                                    txt or '')),
               'selected': st['selected'],
               'log': os.path.basename(out_path), 'rtl_sha256': sha256(RTL),
               'scope': 'front-end expansion and structure only: no cell library, no technology '
                        'mapping, no timing, no area claim, testbench not read'}
    write_atomic(os.path.join(run_dir, 'synth_summary.json'),
                 json.dumps(summary, indent=1, sort_keys=True) + '\n')
    print(json.dumps(summary, indent=1, sort_keys=True)[:1200])
    return summary['rc']


def synth_status(rc, txt):
    """this entry's verdict, formed completely BEFORE anything is written to disk

    Two different things stay separate here on purpose. What the Yosys front end itself reported is
    `yosys_rc` plus the parsed numbers; whether THIS entry is entitled to state those numbers is
    `entry_rc`. A statistics table this parser does not recognise is a failure of the entry, so it
    lands in `problems` and in `entry_rc` before the summary exists -- writing rc=0 and an empty
    problem list and only then noticing the parse failure is exactly how a broken statistics reader
    used to slip through the export gate.
    """
    txt = txt or ''
    problems = []
    if rc != 0:
        problems.append('yosys rc=%d' % rc)
    for pat, why in ((r'\bERROR\b', 'an ERROR line'), (r'multiple drivers', 'multiple drivers'),
                     (r'Wire .* is uninitialized', 'an uninitialised wire'),
                     (r'\$dlatch', 'an inferred latch')):
        if re.search(pat, txt, re.I):
            problems.append(why)
    cells = dict((m.group(2), int(m.group(1))) for m in
                 re.finditer(r'^\s+(\d+)\s+(\$\w+)\s*$', txt, re.M))
    total = None
    m = re.search(r'^\s{6}(\d+) cells\s*$', txt, re.M)
    if m:
        total = int(m.group(1))
    stat_parse = 'parsed' if (cells or total is not None) else (
        'UNPARSED_FORMAT: yosys printed a statistics table this parser does not recognise, so the '
        'cell counts are unknown rather than zero' if 'Printing statistics' in txt else
        'NO_STATISTICS_SECTION')
    if stat_parse != 'parsed':
        problems.append(stat_parse)
    elif not cells:
        problems.append('the statistics section parsed but named no cell types at all')
    return {'entry_rc': 0 if not problems else 1, 'yosys_rc': rc, 'problems': problems,
            'stat_parse': stat_parse, 'cells': cells, 'cells_total': total,
            'check_passes': len(re.findall(r'Found and reported 0 problems', txt)),
            'selected': {'errors': len(re.findall(r'\bERROR\b', txt, re.I)),
                         'warnings': len(re.findall(r'\bWarning\b', txt, re.I))}}


def synth_gate_ok(synth):
    """the export gate reads the same fields the persisted summary carries, parse status included"""
    return (not synth.get('problems') and int(synth.get('rc', 1)) == 0
            and synth.get('stat_parse') == 'parsed' and bool(synth.get('cells')))


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


def _check_identity(run_dir, summary):
    """the cached run must have been produced by the source that is on disk right now"""
    cur = {'rtl_sha256': sha256(RTL), 'tb_sha256': sha256(TB),
           'checker_sha256': sha256(os.path.join(HERE, 'dd1_d7a_check.py')),
           'reader_sha256': sha256(os.path.join(HERE, 'dd1_d7a_trace.py'))}
    bad = []
    for k, v in sorted(cur.items()):
        if summary.get(k) != v:
            bad.append('%s cached=%s now=%s' % (k, str(summary.get(k))[:12], v[:12]))
    if bad:
        raise ck.Refuse('the cached run was produced by different sources, so its PASS counts cannot '
                        'be re-stamped onto this checkout: %s' % '; '.join(bad))
    return cur


def _rejudge(run_dir, summary):
    """re-derive every row from the trace bytes; a cached count is never believed on its own"""
    scen = json.load(io.open(os.path.join(run_dir, 'scenarios.json'), encoding='utf-8'))
    main, ctl, mixed = [], [], []
    for g in summary['groups']:
        path = os.path.join(run_dir, g['vcd'])
        if not os.path.exists(path):
            raise ck.Refuse('the run directory has no %s: the trace behind these results is gone'
                            % g['vcd'])
        got = sha256(path)
        if got != g['vcd_sha256']:
            raise ck.Refuse('%s hashes to %s now, the run recorded %s'
                            % (g['vcd'], got[:12], g['vcd_sha256'][:12]))
        if g['name'] in GROUP_NAMES:
            main.extend(ck.check_main_trace(path, summary['run_id'])[0])
        elif g['name'] == 'control':
            ctl.extend(ck.check_control_trace(
                path, [s for s in scen if s['kind'] != 'mixed_codes'], summary['run_id'])[0])
        else:
            mixed.extend(ck.check_control_trace(
                path, [s for s in scen if s['kind'] == 'mixed_codes'], summary['run_id'])[0])
    return main, ctl, mixed


def _same(cached, rebuilt):
    """every field of every row must reproduce, or the cached evidence is not this run's evidence"""
    def key(r):
        return (int(r['case_id']), r.get('kind', ''), r.get('vcd', ''))
    a = sorted(cached, key=key)
    b = sorted(rebuilt, key=key)
    if len(a) != len(b):
        return 'row count %d cached vs %d rebuilt' % (len(a), len(b))
    for x, y in zip(a, b):
        for k in sorted(set(x) | set(y)):
            if k == 'run_id':
                continue
            if x.get(k) != y.get(k):
                return 'case %s field %s: cached %r vs rebuilt %r' % (x.get('case_id'), k,
                                                                       x.get(k), y.get(k))
    return None


_IN_GUARD = [False]        # the guard matrix re-enters the builder; it must not re-run itself


def build_artefacts(run_dir):
    """validate everything and produce the complete artefact set in memory -- writes nothing"""
    for name in ('run_summary.json', 'mutants.json', 'synth_summary.json', 'raw_main_rows.json',
                 'raw_control_rows.json', 'raw_mixed_rows.json', 'scenarios.json'):
        p = os.path.join(run_dir, name)
        if not os.path.exists(p):
            raise ck.Refuse('the run directory is missing %s' % name)
    summary = json.load(io.open(os.path.join(run_dir, 'run_summary.json'), encoding='utf-8'))
    mut = json.load(io.open(os.path.join(run_dir, 'mutants.json'), encoding='utf-8'))
    synth = json.load(io.open(os.path.join(run_dir, 'synth_summary.json'), encoding='utf-8'))
    cached_main = json.load(io.open(os.path.join(run_dir, 'raw_main_rows.json'), encoding='utf-8'))
    cached_ctl = json.load(io.open(os.path.join(run_dir, 'raw_control_rows.json'), encoding='utf-8'))
    cached_mix = json.load(io.open(os.path.join(run_dir, 'raw_mixed_rows.json'), encoding='utf-8'))
    scen = json.load(io.open(os.path.join(run_dir, 'scenarios.json'), encoding='utf-8'))
    identity = _check_identity(run_dir, summary)

    if summary['compile_rc'] != 0:
        raise ck.Refuse('the cached run did not compile (rc=%s)' % summary['compile_rc'])
    for g in summary['groups']:
        if g.get('vvp_rc', 0) != 0:
            raise ck.Refuse('%s exited %s in the cached run' % (g['name'], g.get('vvp_rc')))
    if summary['main_rows'] != len(cached_main) or len(cached_main) != 1536:
        raise ck.Refuse('main rows are %d, the summary says %d, the matrix requires 1536'
                        % (len(cached_main), summary['main_rows']))
    keys = set((r['mode'], r['frame_hz'], r['tick_ns'], r['time_code'], r['pam_code'])
               for r in cached_main)
    if len(keys) != 1536:
        raise ck.Refuse('the matrix holds %d unique (mode, frame, tick, code, pam) combinations, not '
                        '1536: duplicates or gaps' % len(keys))
    want_ctl = len([s for s in scen if s['kind'] != 'mixed_codes'])
    if len(cached_ctl) != want_ctl:
        raise ck.Refuse('%d control rows for %d declared scenarios' % (len(cached_ctl), want_ctl))
    if len(cached_mix) != len([s for s in scen if s['kind'] == 'mixed_codes']):
        raise ck.Refuse('mixed rows do not match the declared mixed scenarios')

    def _as_expected(r):
        if r.get('expect') == 'refusal':
            return r['verdict'] == 'FAIL'
        return r['verdict'] == 'PASS'
    unattested = [r['case_id'] for r in cached_ctl + cached_mix
                  if any(t in r['failures'] for t in ('STIMULUS_UNATTESTED', 'STIMULUS_MISMATCH'))]
    gates = {
        'PURE_MATRIX': summary['main_pass'] == len(cached_main) and len(keys) == 1536,
        'CONTROL_AND_ABORT': bool(cached_ctl) and all(_as_expected(r) for r in cached_ctl),
        'MIXED': bool(cached_mix) and all(_as_expected(r) for r in cached_mix),
        'XPROBE_REFUSED': summary['xprobe_refused'] == summary['xprobe_expected'],
        'MUTATION_DETECTION': mut['detected'] == mut['total'] and len(mut['rows']) == mut['total'],
        'SYNTHESIS_STRUCTURE': synth_gate_ok(synth),
        'STIMULUS_ATTESTED': not unattested,
    }
    if not all(gates.values()):
        raise ck.Refuse('export gates failed: %s ; unattested scenarios: %s'
                        % (json.dumps(gates, sort_keys=True), unattested or 'none'))

    rebuilt_main, rebuilt_ctl, rebuilt_mix = _rejudge(run_dir, summary)
    for label, cached, rebuilt in (('main', cached_main, rebuilt_main),
                                   ('control', cached_ctl, rebuilt_ctl),
                                   ('mixed', cached_mix, rebuilt_mix)):
        diff = _same(cached, rebuilt)
        if diff:
            raise ck.Refuse('re-judging the %s traces from their bytes disagrees with the cached rows: %s'
                            % (label, diff))
    main_order = sorted(cached_main, key=lambda r: int(r['case_id']))
    ctl_order = sorted(cached_ctl + cached_mix, key=lambda r: (int(r['case_id']), r.get('kind', '')))
    art = {}
    buf = io.StringIO()
    ck.write_csv(buf, main_order, CASES_ORDER)
    art['dd1_d7a_cases.csv'] = buf.getvalue()
    buf = io.StringIO()
    ck.write_csv(buf, ctl_order)
    art['dd1_d7a_control_cases.csv'] = buf.getvalue()
    neg = negative_rows(run_dir, mut)
    buf = io.StringIO()
    ck.write_csv(buf, neg)
    art['dd1_d7a_negative.csv'] = buf.getvalue()
    srows = _samples_or_refuse(run_dir, main_order)
    buf = io.StringIO()
    ck.write_csv(buf, srows)
    art['dd1_d7a_edge_samples.csv'] = buf.getvalue()
    st = os.path.join(run_dir, 'checker_selftest.txt')
    if os.path.exists(st):
        art['dd1_d7a_checker_selftest.txt'] = u(io.open(st, encoding='utf-8').read())
    env_json = environment_json(run_dir, summary, mut, synth, identity, gates)
    art['dd1_d7a_environment.json'] = json.dumps(env_json, indent=1, sort_keys=True) + '\n'
    if not _IN_GUARD[0]:
        art['dd1_d7a_write_guard.txt'] = write_guard_report(run_dir)
    man = manifest_json(run_dir, env_json, len(main_order), len(ctl_order), len(srows), art, gates)
    art['dd1_d7a_manifest.json'] = json.dumps(man, indent=1, sort_keys=True) + '\n'
    for name, text in sorted(art.items()):
        if not text.strip():
            raise ck.Refuse('%s would be published empty' % name)
    return art


PENDING_MARKER = 'd7a_publish.pending'
PUBLISH_BACKUP = os.path.join(PROJ, 'review', 'dd1_d7a', 'publish_backup')
# The marker is the identity of a publish transaction. A reader has to be able to tell "no
# transaction" from "transaction I cannot interpret", so the shape is written down and checked.
MARKER_SCHEMA = 'd7a-publish/2'
MARKER_PHASE = 'promoting'
REQUIRED_MARKER_FIELDS = ('schema', 'phase', 'files', 'backup', 'previous', 'absent')
SHA_RE = re.compile(r'^[0-9a-f]{64}$')


def _fsync_write(path, data):
    fp = io.open(path, 'wb')
    try:
        fp.write(data)
        fp.flush()
        os.fsync(fp.fileno())
    finally:
        fp.close()


def _record_path(path):
    """how a backup directory names itself inside a marker: repo-relative whenever it can be"""
    path = os.path.abspath(path)
    try:
        rel = os.path.relpath(path, PROJ)
    except ValueError:                       # another drive on Windows: only an absolute name works
        return path.replace('\\', '/')
    if rel.startswith('..'):
        return path.replace('\\', '/')
    return rel.replace('\\', '/')


def _resolve_recorded(rec):
    """the absolute directory a marker's `backup` field points at"""
    if os.path.isabs(rec):
        return rec
    return os.path.join(PROJ, rec.replace('/', os.sep))


def _marker_error(rec):
    """why this record cannot identify a transaction, or None when it can"""
    if not isinstance(rec, dict):
        return 'the marker is not a JSON object'
    missing = sorted(k for k in REQUIRED_MARKER_FIELDS if k not in rec)
    if missing:
        return 'the marker lacks %s' % ', '.join(missing)
    if rec['schema'] != MARKER_SCHEMA:
        return 'the marker declares schema %r, this tool writes %r' % (rec['schema'], MARKER_SCHEMA)
    if rec['phase'] != MARKER_PHASE:
        return 'the marker records an unrecognised phase %r' % (rec['phase'],)
    files, previous, absent = rec['files'], rec['previous'], rec['absent']
    if not isinstance(files, list) or not files or \
            not all(isinstance(n, _text) and n for n in files):
        return 'the marker file list is not a non-empty list of names'
    if files != sorted(files) or len(set(files)) != len(files):
        return 'the marker file list is not sorted and unique'
    if not isinstance(previous, dict) or not isinstance(absent, list):
        return 'the marker previous/absent records have the wrong types'
    if not all(isinstance(k, _text) and SHA_RE.match(str(v)) for k, v in sorted(previous.items())):
        return 'the marker records a "previous" value that is not a sha256 hex string'
    if not all(isinstance(n, _text) and n for n in absent):
        return 'the marker absent list holds entries that are not names'
    if set(previous) & set(absent):
        return 'a target is recorded both as previously present and as previously absent'
    if set(files) != set(previous) | set(absent):
        return ('the marker names %d target(s) but records a prior state for %d present + %d absent'
                % (len(files), len(previous), len(absent)))
    if not isinstance(rec['backup'], _text) or not rec['backup']:
        return 'the marker does not record where its own backup lives'
    return None


def pending_publish():
    """the outstanding publish transaction, or None when there is none

    A marker that cannot identify a transaction is reported as an invalid one, never as an empty and
    therefore already-satisfied transaction: the directory stays refused until the recorded bytes are
    really back in place.
    """
    p = os.path.join(EVIDENCE, PENDING_MARKER)
    if not os.path.exists(p):
        return None
    try:
        rec = json.load(io.open(p, encoding='utf-8'))
    except (ValueError, OSError, IOError) as exc:
        return {'unreadable_marker': True,
                'marker_invalid': 'it does not parse as JSON (%s)' % type(exc).__name__}
    err = _marker_error(rec)
    if err:
        return {'unreadable_marker': True, 'marker_invalid': err}
    return rec


def publish(art, backup_dir=None, promote=None):
    """stage every artefact, promote it atomically, and keep a readable transaction record

    Per-file replacement is atomic (`os.replace`), and that is the only atomicity a flat directory can
    offer. The SET is kept consistent for every failure this process can catch. The stages and their
    error boundaries are:

      1. backup preparation -- the bytes that are in place are copied to `backup_dir` and each copy
         is re-hashed against the file it came from;
      2. marker write -- a record naming the target set, this transaction's own backup directory and
         the prior state of every target (digest, or "did not exist"); it is validated before it is
         written, so nothing is recorded that this tool could not later read back;
      3. staging -- each new artefact is written as `<name>.new`;
      4. promotion -- `<name>.new` is replaced over the target with `os.replace`;
      5. verification and cleanup -- each target must hash to the staged bytes, then this
         transaction's own `.new` files and the marker are removed.

    A failure in 1..3 happens before the first promotion, so the published set is still intact and is
    never touched; the staging files written so far and the marker are removed and the caller still
    gets a non-zero exit. A failure in 4 or 5 rolls the whole set back from the backup, verifies every
    file and then clears the marker; if the rollback or the marker cleanup itself fails, the marker and
    the backup are KEPT and `pending_publish()` reports the transaction as outstanding, so no further
    publish is accepted until `recover_publish()` has verified the whole set. Only this transaction's
    own staging files are ever deleted.

    A SIGKILL or power loss between two promotions is NOT covered by that rollback: the pending marker
    then stays on disk and a later run restores from the backup the marker itself names. Nothing here
    claims a hardware transaction.

    `promote` exists for the fault-injection regression: it replaces the promotion primitive.
    """
    names = sorted(art)
    if not names:
        raise ck.Refuse('publish refused: there is nothing to publish')
    stale = pending_publish()
    if stale is not None:
        raise ck.Refuse('publish refused: the previous publish is still outstanding (%s); its backup '
                        'and marker are not overwritten and the evidence set is not treated as '
                        'delivered' % (stale.get('marker_invalid') or
                                       'recover it with recover_publish()'))
    backup_dir = os.path.abspath(backup_dir or PUBLISH_BACKUP)
    if not os.path.isdir(EVIDENCE):
        os.makedirs(EVIDENCE)
    marker = os.path.join(EVIDENCE, PENDING_MARKER)
    previous, absent, staged = {}, [], []

    def _discard_staging():
        """remove exactly the staging files this transaction wrote, nothing else"""
        left = []
        for path in staged:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except (OSError, IOError):
                left.append(os.path.basename(path))
        del staged[:]
        return left

    try:
        if not os.path.isdir(backup_dir):
            os.makedirs(backup_dir)
        for name in names:
            final = os.path.join(EVIDENCE, name)
            if os.path.exists(final):
                bak = os.path.join(backup_dir, name)
                shutil.copyfile(final, bak)
                want = sha256(final)
                if sha256(bak) != want:
                    raise ck.Refuse('the backup copy of %s does not match the file it was copied from'
                                    % name)
                previous[name] = want
            else:
                absent.append(name)          # a legal target that simply did not exist before
        record = {'schema': MARKER_SCHEMA, 'phase': MARKER_PHASE, 'files': names,
                  'backup': _record_path(backup_dir), 'previous': previous, 'absent': absent}
        bad_record = _marker_error(record)
        if bad_record:
            raise ck.Refuse('refusing to write a marker this tool could not read back: %s'
                            % bad_record)
        _fsync_write(marker, u(json.dumps(record, sort_keys=True)).encode('utf-8'))
        for name in names:
            tmp = os.path.join(EVIDENCE, name + '.new')
            _fsync_write(tmp, u(art[name]).encode('utf-8'))
            staged.append(tmp)
    except (Exception, SystemExit) as exc:                       # noqa: BLE001
        detail = '%s: %s' % (type(exc).__name__, exc)
        left = _discard_staging()
        marker_kept = False
        if os.path.exists(marker):
            try:
                os.remove(marker)
            except (OSError, IOError):
                marker_kept = True
        raise ck.Refuse('publish stopped before the first promotion, the published set is untouched, '
                        '%s%s; cause %s'
                        % ('the marker stays so this transaction is still identifiable'
                           if marker_kept else 'no marker survives',
                           '; staging that could not be removed: %s' % left if left else '',
                           detail))

    moved = []
    promote = promote or os.replace

    def _rollback():
        for name in names:
            final = os.path.join(EVIDENCE, name)
            if name in previous:
                bak = os.path.join(backup_dir, name)
                if not os.path.exists(bak):
                    raise ck.Refuse("the rollback cannot restore %s: this transaction's backup copy "
                                    'is gone' % name)
                if sha256(bak) != previous[name]:
                    raise ck.Refuse('the rollback cannot restore %s: its backup no longer holds the '
                                    'recorded bytes' % name)
                _fsync_write(final + '.restore', open(bak, 'rb').read())
                os.replace(final + '.restore', final)
                if sha256(final) != previous[name]:
                    raise ck.Refuse('the rollback of %s did not restore the previous bytes' % name)
            elif os.path.exists(final):
                os.remove(final)
                if os.path.exists(final):
                    raise ck.Refuse('the rollback could not put %s back to not-existing' % name)
        _discard_staging()
        for name in names:
            junk = os.path.join(EVIDENCE, name + '.restore')
            if os.path.exists(junk):
                os.remove(junk)

    try:
        for name in names:
            promote(os.path.join(EVIDENCE, name + '.new'), os.path.join(EVIDENCE, name))
            moved.append(name)
        for name in names:
            want = hashlib.sha256(u(art[name]).encode('utf-8')).hexdigest()
            got = sha256(os.path.join(EVIDENCE, name))
            if got != want:
                raise ck.Refuse('%s on disk does not match the bytes that were staged (%s vs %s)'
                                % (name, got[:12], want[:12]))
    except (Exception, SystemExit) as exc:                       # noqa: BLE001
        detail = '%s: %s' % (type(exc).__name__, exc)
        try:
            _rollback()
        except (Exception, SystemExit) as rexc:                  # noqa: BLE001
            raise ck.Refuse('publish aborted after %d/%d promotion(s) and the ROLLBACK ITSELF FAILED: '
                            '%s ; the published set is not restored, so the marker and the backup in '
                            '%s are kept and every later publish stays refused until recover_publish() '
                            'verifies the whole set; cause %s'
                            % (len(moved), len(names), rexc, _record_path(backup_dir), detail))
        try:
            os.remove(marker)
        except (OSError, IOError) as mexc:
            raise ck.Refuse('publish aborted after %d/%d promotion(s), the previous set is restored '
                            'but the marker could not be removed (%s), so this transaction still counts '
                            'as outstanding; cause %s' % (len(moved), len(names), mexc, detail))
        raise ck.Refuse('publish aborted after %d/%d promotion(s), the previous set is restored; '
                        'cause %s' % (len(moved), len(names), detail))
    _discard_staging()
    try:
        os.remove(marker)                  # the whole set is on disk and verified: transaction closed
    except (OSError, IOError) as exc:
        raise ck.Refuse('every artefact was published and verified but the marker could not be removed '
                        '(%s), so this transaction still counts as outstanding' % exc)
    return names


def recover_publish(backup_dir=None):
    """restore the generation a pending marker identifies, from the backup that marker recorded

    The marker is the transaction identity: the backup directory and the file set it names are what
    gets used and verified, whether or not a caller happens to pass a directory -- a caller that
    passes a different one is answered with a recorded mismatch rather than with a restore from the
    wrong place. The marker is removed only after every target has been checked against the prior
    state recorded before the transaction began (digest, or "did not exist"); anything else keeps the
    marker, so the next run is refused too and nothing mixed is ever reported as delivered.
    """
    state = pending_publish()
    if state is None:
        return {'needed': False}
    if state.get('marker_invalid'):
        return {'needed': True, 'complete': False, 'restored': [], 'failed': [], 'targets': 0,
                'phase': None, 'backup_used': None, 'marker_kept': True,
                'reason': 'the pending marker cannot identify a transaction (%s); nothing was '
                          'restored, the marker is kept and this evidence directory stays refused'
                          % state['marker_invalid']}
    recorded = _resolve_recorded(state['backup'])
    names, previous, absent = state['files'], state['previous'], state['absent']
    restored, failed = [], []
    if backup_dir is not None and os.path.abspath(backup_dir) != recorded:
        failed.append('the caller passed %s but this transaction recorded %s; the recorded location '
                      'is the one that was used' % (_record_path(backup_dir), state['backup']))
    for name in names:
        final = os.path.join(EVIDENCE, name)
        try:
            if name in previous:
                bak = os.path.join(recorded, name)
                if not os.path.exists(bak):
                    failed.append('%s: the backup this transaction recorded is missing' % name)
                    continue
                got = sha256(bak)
                if got != previous[name]:
                    failed.append('%s: its backup hashes to %s, the marker recorded %s'
                                  % (name, got[:12], previous[name][:12]))
                    continue
                _fsync_write(final + '.restore', open(bak, 'rb').read())
                os.replace(final + '.restore', final)
                if sha256(final) != previous[name]:
                    failed.append('%s: the bytes put back do not match the recorded digest' % name)
                    continue
            else:
                if os.path.exists(final):
                    os.remove(final)
                if os.path.exists(final):
                    failed.append('%s: still present, although this transaction recorded it as '
                                  'absent' % name)
                    continue
            restored.append(name)
        except (OSError, IOError, ck.Refuse) as exc:
            failed.append('%s: restoring it raised %s: %s' % (name, type(exc).__name__, exc))
    for name in names:                       # only this transaction is allowed to clean up
        for suffix in ('.new', '.restore'):
            junk = os.path.join(EVIDENCE, name + suffix)
            if not os.path.exists(junk):
                continue
            try:
                os.remove(junk)
            except (OSError, IOError):
                failed.append('%s%s: a staging file of this transaction could not be deleted'
                              % (name, suffix))
    complete = not failed and len(restored) == len(names)
    marker_kept = True
    if complete:
        try:
            os.remove(os.path.join(EVIDENCE, PENDING_MARKER))
            marker_kept = False
        except (OSError, IOError) as exc:
            failed.append('the whole set is restored but the marker could not be removed (%s)' % exc)
            complete = False
    out = {'needed': True, 'complete': complete, 'restored': restored, 'failed': failed,
           'targets': len(names), 'phase': state['phase'], 'backup_used': _record_path(recorded),
           'marker_recorded_backup': state['backup'], 'marker_kept': marker_kept}
    if not complete:
        out['reason'] = ('%d/%d target(s) verified and %d unresolved; the marker stays so no new '
                         'transaction can be published over this one and the mixed content is not '
                         'reported as delivered' % (len(restored), len(names), len(failed)))
    return out


def do_export(args):
    run_dir = os.path.abspath(args['out'])
    stale = pending_publish()
    if stale is not None:
        rec = recover_publish()
        print('PENDING_PUBLISH_RECOVERED: %s' % json.dumps(rec, sort_keys=True))
        if rec.get('needed') and not rec.get('complete'):
            print('EXPORT_REFUSED: an earlier publish is still outstanding and its backup cannot '
                  'restore the whole set; the evidence directory is not treated as delivered (%s)'
                  % rec.get('reason', 'see the record above'))
            return 1
    try:
        art = build_artefacts(run_dir)
    except (ck.Refuse, tv.VcdError, OSError, IOError, KeyError, ValueError) as exc:
        print('EXPORT_REFUSED before touching %s: %s' % (EVIDENCE, exc))
        left = [n for n in os.listdir(EVIDENCE) if n.endswith('.new')] if os.path.isdir(EVIDENCE) else []
        if left:
            print('STAGED_FILES_LEFT: %s (official files untouched)' % left)
        return 1
    try:
        names = publish(art, backup_dir=os.path.join(run_dir, 'publish_backup'))
    except ck.Refuse as exc:
        print('PUBLISH_FAILED_ROLLED_BACK: %s' % exc)
        return 1
    print('exported %d files: %s' % (len(names), ', '.join(names)))
    print('PUBLISH_TRANSACTION: target_files=%d backup=%s marker=cleared guarantee=caught-failure '
          'rollback (not kill/power-loss atomic) marker_schema=%s'
          % (len(names), _record_path(os.path.join(run_dir, 'publish_backup')), MARKER_SCHEMA))
    return 0

def negative_rows(run_dir, mut):
    rows = []
    path = os.path.join(run_dir, 'checker_selftest.txt')
    for d in mut['rows']:
        rows.append({'class': d['class'],
                     'category': d.get('category', MUTANTS.get(d['class'], {}).get('category', '')),
                     'mutant_rtl_sha256': d.get('mutant_rtl_sha256', ''),
                     'trigger_case': d.get('trigger_case', ''), 'simulator_rc': '0',
                     'checker_rc': '1' if d['status'] == 'DETECTED' else '0',
                     'fault_kind': d.get('fault_kind', ''),
                     'fault_confirmed': 'yes' if d.get('fault_confirmed') else 'no',
                     'fault_observed': str(d.get('fault_observed', ''))[:160],
                     'failing_assertion': d.get('detail', '')[:200],
                     'status': d['status'], 'note': MUTANTS.get(d['class'], {}).get('note', ''),
                     'run_id': mut['run_id']})
    if os.path.exists(path):
        txt = u(io.open(path, encoding='utf-8').read())
        for line in txt.split('\n'):
            if line.startswith('FAIL') or 'refused while parsing' in line:
                rows.append({'class': 'checker_selftest', 'category': 'selftest',
                             'mutant_rtl_sha256': 'synthetic trace',
                             'trigger_case': 'synthetic', 'simulator_rc': 'not_run',
                             'checker_rc': '1', 'failing_assertion': line[:200],
                             'fault_kind': 'synthetic_trace', 'fault_confirmed': 'n/a',
                             'fault_observed': 'a waveform this file writes, not a run of the design',
                             'status': 'DETECTED', 'note': 'the checker proves its own refusals',
                             'run_id': os.path.basename(run_dir)})
                break
    return rows


def _samples_or_refuse(run_dir, main_order):
    """the sampling stage on its own, so its refusal is reachable without a full re-judge"""
    srows = sample_rows(run_dir, main_order)
    if not srows:
        raise ck.Refuse('no edge samples could be extracted from these traces')
    return srows



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


def environment_json(run_dir, summary, mut, synth, identity=None, gates=None):
    root, tools, env = find_tools()
    versions = summary.get('tool_versions', {})
    return {
        'task': 'DATA-7A',
        'task_revision': TASK_REVISION,
        'run_id': os.path.basename(run_dir),
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
        'identity_verified': bool(identity),
        'source_digests_checked': sorted((identity or {}).keys()),
        'export_gates': gates or {},
        # the traces are not re-simulated by an export: say whose bytes they are, so a reused run can
        # never be read as a fresh simulation of this revision
        'waveform_provenance': {
            'run_id': os.path.basename(run_dir),
            'produced_by_task_revision': summary.get('task_revision',
                                                     'NOT_STAMPED_BY_THE_RUNNER_THAT_MADE_THIS_RUN'),
            'exported_by_task_revision': TASK_REVISION,
            'sources_that_produced_the_traces': dict(
                (k, summary.get(k)) for k in ('rtl_sha256', 'tb_sha256', 'checker_sha256',
                                              'reader_sha256')),
            'simulations_started_by_this_export': 0,
            'traces_rejudged_from_bytes_before_publish': True,
            'trace_digests': dict((g['vcd'], g['vcd_sha256']) for g in summary['groups']),
        },
        'supersedes': {'baseline_delivery': '6a1f5a192f3f1618499335c4365d717bfcadef39',
                       'previous_run_id': 'FINAL',
                       'reason': 'R1 review fixes: abort re-authorisation, configuration freshness, '
                                 'safe-phase mode adoption, export failure guard, stimulus coverage'},
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


def manifest_json(run_dir, env_json, main_n, ctl_n, sample_n, art=None, gates=None):
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
    loose = []
    names = set(n for n in (os.listdir(EVIDENCE) if os.path.isdir(EVIDENCE) else [])
                if n.startswith('dd1_d7a_'))
    names |= set(art or {})
    for name in sorted(names):
        if name == 'dd1_d7a_manifest.json':
            continue                              # a manifest cannot carry its own digest
        if name.startswith('dd1_d7a_freeze'):
            loose.append(name)          # regenerated by the handoff step, after publishing
            continue
        if art is not None and name in art:
            b = u(art[name]).encode('utf-8')      # publish() writes exactly these bytes
            ev[name] = {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest(),
                        'origin': 'the bytes this export is about to publish'}
        else:
            p = os.path.join(EVIDENCE, name)
            if os.path.isfile(p):
                ev[name] = {'bytes': os.path.getsize(p), 'sha256': sha256(p),
                            'origin': 'already in the evidence directory, not rewritten here'}
    return {'task': 'DATA-7A', 'task_revision': TASK_REVISION,
            'run_id': os.path.basename(run_dir), 'sources': src,
            'run_artifacts': files, 'evidence': ev,
            'evidence_hashed_elsewhere': {
                'files': loose,
                'reason': 'the freeze and security transcript is a command log the handoff step '
                          'regenerates after this export, so its digest belongs to the handoff JSON '
                          'rather than to a file published before it'},
            'counts': {'main_cases': main_n, 'control_cases': ctl_n, 'edge_samples': sample_n,
                       'instance_observations': main_n * 2},
            'traces_kept_local': sorted([n for n in os.listdir(run_dir) if n.endswith('.vcd')]),
            'trace_digests': dict((g['vcd'], g['vcd_sha256']) for g in env_json['groups']),
            'reproduce': 'python scripts/dd1_d7a_run.py --selftest && ... --run-rtl/--mutants/'
                        '--synth/--export --out review/dd1_d7a/<run_id>',
            'export_gates': gates or {},
            'artefact_bytes': dict((n, len(u(b).encode('utf-8'))) for n, b in sorted((art or {}).items())),
            'traces_rejudged_before_publish': True}


"""the guard regression: one clean baseline copy per mode, one injected fault per mode

The previous version copied the run once and let every later mode inherit the damage the earlier
modes had done, so three of its "PASS" rows were really refusing for somebody else's reason. Each
mode now starts from an intact, exportable copy and has to refuse for the reason its name claims,
with the whole evidence set and the leftover-file state checked afterwards.
"""

def _fresh_run_copy(fixture, src, name, private=()):
    """a per-mode copy of the baseline run: small files copied, big traces hard-linked

    Files a mode is going to modify are copied, so that editing them cannot reach the shared baseline
    through the hard link.
    """
    d = os.path.join(fixture, 'run_' + name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for fn in sorted(os.listdir(src)):
        s, t = os.path.join(src, fn), os.path.join(d, fn)
        if not os.path.isfile(s):
            continue
        if fn in private or not fn.endswith('.vcd'):
            shutil.copyfile(s, t)
        else:
            try:
                os.link(s, t)
            except OSError:
                shutil.copyfile(s, t)
    return d


def _digest_set(ev):
    return dict((n, sha256(os.path.join(ev, n))) for n in sorted(os.listdir(ev))
                if os.path.isfile(os.path.join(ev, n)))


def _leftovers(ev_dir):
    return sorted(n for n in os.listdir(ev_dir)
                  if n.endswith('.new') or n.endswith('.restore') or n == PENDING_MARKER)


def _seed_evidence(ev_dir, old_bytes):
    """pre-seed every target file with the non-empty bytes a previous export really published"""
    if os.path.isdir(ev_dir):
        shutil.rmtree(ev_dir)
    os.makedirs(ev_dir)
    for name, text in sorted(old_bytes.items()):
        with io.open(os.path.join(ev_dir, name), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(u(text))


def _promote_failing_at(k):
    """a promotion primitive that throws on the k-th file and behaves normally otherwise"""
    seen = []

    def _p(src, dst):
        seen.append(os.path.basename(dst))
        if len(seen) == k + 1:
            raise OSError('INJECTED promotion failure on %s' % os.path.basename(dst))
        os.replace(src, dst)
    return _p, seen


def guard_modes(fixture, cache_src, art, old_bytes):
    """the mode table: (name, expected refusal text, what proves that stage was reached, injector)"""
    ev = os.path.join(fixture, 'evidence')

    def cache_for(name, private=()):
        return _fresh_run_copy(fixture, cache_src, name, private=private)

    def m_empty():
        ck.write_rows(os.path.join(ev, 'dd1_d7a_cases.csv'), [])
    def m_missing_dir():
        build_artefacts(os.path.join(fixture, 'absent_run'))
    def m_dry():
        do_dry_run({'out': cache_for('dry_run')})
    def m_gates():
        d = cache_for('gates_not_met')
        p = os.path.join(d, 'mutants.json')
        m = json.load(io.open(p, encoding='utf-8'))
        m['detected'] = 1
        io.open(p, 'w', encoding='utf-8', newline='\n').write(u(json.dumps(m)))
        return build_artefacts(d)
    def m_compile():
        d = cache_for('compile_failure')
        root, tools, env = find_tools()
        bad = os.path.join(d, 'broken.sv')
        io.open(bad, 'w', encoding='utf-8', newline='\n').write(u('module x( input a ; // unterminated\n'))
        try:
            exe, crc, cout = compile_sim(tools, env, d, rtl=bad, tag='broken')
        except SystemExit as exc:                       # the entry refuses a broken source this way
            raise ck.Refuse('compile refused: %s' % str(exc)[:120])
        raise ck.Refuse('the compile entry accepted a broken source file, rc=%s' % crc)
    def m_missing_trace():
        d = cache_for('missing_trace')
        os.remove(os.path.join(d, 'trace_pure_t30.vcd'))
        return build_artefacts(d)
    def m_corrupt_trace():
        # the recorded digest is refreshed first, otherwise this mode would only ever re-run the
        # digest gate and never reach the parser, which is exactly what the old table pretended
        d = cache_for('corrupt_trace', private=('trace_pure_t50.vcd', 'run_summary.json'))
        p = os.path.join(d, 'trace_pure_t50.vcd')
        io.open(p, 'w', encoding='utf-8', newline='\n').write(
            u'$version garbage $end\n$timescale 1ps $end\n#100 1\nno such variable here\n')
        sp = os.path.join(d, 'run_summary.json')
        s = json.load(io.open(sp, encoding='utf-8'))
        for g in s['groups']:
            if g['vcd'] == 'trace_pure_t50.vcd':
                g['vcd_sha256'] = sha256(p)
        io.open(sp, 'w', encoding='utf-8', newline='\n').write(u(json.dumps(s)))
        return build_artefacts(d)
    def m_sample_extract():
        # the sampling stage sits behind a full re-judge, so it is exercised by calling the same
        # function the export calls, on a run copy whose main rows name a trace the sampler does not
        # use and whose control trace is absent: that is the state in which it has nothing to sample
        d = cache_for('sample_extract_failure', private=())
        if os.path.exists(os.path.join(d, 'trace_control.vcd')):
            os.remove(os.path.join(d, 'trace_control.vcd'))
        rows = json.load(io.open(os.path.join(d, 'raw_main_rows.json'), encoding='utf-8'))
        for r in rows:
            r['vcd'] = 'trace_unsampled.vcd'
        return _samples_or_refuse(d, rows)
    def m_stale_source():
        d = cache_for('stale_cached_source')
        p = os.path.join(d, 'run_summary.json')
        s = json.load(io.open(p, encoding='utf-8'))
        s['checker_sha256'] = 'e' * 64
        io.open(p, 'w', encoding='utf-8', newline='\n').write(u(json.dumps(s)))
        return build_artefacts(d)
    def m_row_count():
        d = cache_for('row_count_mismatch')
        p = os.path.join(d, 'raw_main_rows.json')
        rows = json.load(io.open(p, encoding='utf-8'))
        io.open(p, 'w', encoding='utf-8', newline='\n').write(u(json.dumps(rows[:1500])))
        return build_artefacts(d)
    def m_trace_digest():
        d = cache_for('trace_digest_mismatch', private=('trace_hyb_t120.vcd',))
        io.open(os.path.join(d, 'trace_hyb_t120.vcd'), 'a', encoding='utf-8',
                newline='\n').write(u('#999999999999\n'))
        return build_artefacts(d)

    def _publish_mode(at):
        def _run():
            art2 = dict((k, v + 'X\n') for k, v in sorted(art.items()))
            backup = os.path.join(fixture, 'backup_%d' % at)
            _seed_evidence(ev, old_bytes)
            before = _digest_set(ev)
            names = sorted(art2)
            promote, seen = _promote_failing_at(min(at, len(names) - 1))
            publish(art2, backup_dir=backup, promote=promote)
        return _run

    class Interrupted(BaseException):
        """an interruption that the caught-failure rollback is not allowed to see"""

    def _write_failing_mode(tag, pred, phase):
        def _run():
            art2 = dict((k, v + 'X\n') for k, v in sorted(art.items()))
            backup = os.path.join(fixture, 'backup_' + tag)
            _seed_evidence(ev, old_bytes)
            original = _fsync_write

            def fail(path, data):
                if pred(path):
                    raise OSError('INJECTED %s failure on %s' % (phase, os.path.basename(path)))
                return original(path, data)
            try:
                globals()['_fsync_write'] = fail
                publish(art2, backup_dir=backup)
            finally:
                globals()['_fsync_write'] = original
        return _run

    def _nth_staging_write(n):
        """a predicate that answers true on the n-th .new this transaction tries to write"""
        seen = []

        def pred(path):
            if not path.endswith('.new'):
                return False
            seen.append(os.path.basename(path))
            return len(seen) == n
        return pred

    def m_recover_recorded_backup():
        """the interrupted publish backed up into a non-default run directory, recovery gets no hint"""
        art2 = dict((k, v + 'X\n') for k, v in sorted(art.items()))
        backup = os.path.join(fixture, 'backup_recorded_marker')
        _seed_evidence(ev, old_bytes)
        before = _digest_set(ev)
        calls = []

        def promote(src, dst):
            calls.append(os.path.basename(dst))
            if len(calls) == 2:
                raise Interrupted('INJECTED interruption between two promotions')
            os.replace(src, dst)
        try:
            publish(art2, backup_dir=backup, promote=promote)
        except Interrupted:
            pass
        if len(calls) != 2:
            raise ck.Refuse('the injected interruption never reached the promotion boundary')
        state = pending_publish()
        if state is None or state.get('marker_invalid'):
            raise ck.Refuse('the interrupted publish left no usable transaction marker behind')
        rec = recover_publish()                      # exactly how do_export calls it: no argument
        if rec.get('backup_used') != _record_path(backup):
            raise ck.Refuse('recovery used %s instead of the %s recorded by the marker'
                            % (rec.get('backup_used'), _record_path(backup)))
        if not rec.get('complete'):
            raise ck.Refuse('recovery from the recorded backup reported incomplete: %s'
                            % json.dumps(rec, sort_keys=True)[:180])
        after = _digest_set(ev)
        if after != before:
            raise ck.Refuse('recovery did not put the previous bytes back: %s'
                            % sorted(k for k in before if before.get(k) != after.get(k)))
        if pending_publish() is not None:
            raise ck.Refuse('a completed recovery left its marker behind')

    def m_publish_ok():
        art2 = dict((k, v + 'NEWBYTES\n') for k, v in sorted(art.items()))
        backup = os.path.join(fixture, 'backup_ok')
        _seed_evidence(ev, old_bytes)
        publish(art2, backup_dir=backup)
        for name in sorted(art2):
            got = sha256(os.path.join(ev, name))
            want = hashlib.sha256(u(art2[name]).encode('utf-8')).hexdigest()
            if got != want:
                raise ck.Refuse('%s was not published as staged' % name)
            old = old_bytes.get(name)
            if old is not None and sha256(os.path.join(backup, name)) != \
                    hashlib.sha256(u(old).encode('utf-8')).hexdigest():
                raise ck.Refuse('the backup of %s does not hold the previous bytes' % name)
        if pending_publish() is not None:
            raise ck.Refuse('a successful publish left a pending marker behind')
        if _leftovers(ev):
            raise ck.Refuse('a successful publish left %s behind' % _leftovers(ev))

    def _synth_mode(tag, mutate):
        def _run():
            d = cache_for(tag)
            p = os.path.join(d, 'synth_summary.json')
            s = json.load(io.open(p, encoding='utf-8'))
            mutate(s)
            io.open(p, 'w', encoding='utf-8', newline='\n').write(u(json.dumps(s)))
            return build_artefacts(d)
        return _run

    def _unparsed_claimed_ok(s):
        s['stat_parse'] = ('UNPARSED_FORMAT: yosys printed a statistics table this parser does not '
                           'recognise, so the cell counts are unknown rather than zero')
        s['problems'] = []
        s['rc'] = 0
        s['cells'] = {}
        s['cells_total'] = None

    def _unparsed_declared(s):
        s['stat_parse'] = 'UNPARSED_FORMAT: injected'
        s['problems'] = ['UNPARSED_FORMAT: injected']
        s['rc'] = 1

    def _structure_broken(s):
        s['problems'] = ['an inferred latch']
        s['rc'] = 1

    return [
        {'mode': 'dry_run_plan_only', 'expect': None, 'inject': m_dry,
         'stage': 'the dry run must plan without touching the evidence set at all'},
        {'mode': 'empty_row_set', 'expect': 'refusing to render 0 rows', 'inject': m_empty,
         'stage': 'the CSV writer refuses an empty table'},
        {'mode': 'missing_run_dir', 'expect': 'is missing run_summary.json', 'inject': m_missing_dir,
         'stage': 'the first input check'},
        {'mode': 'compile_failure', 'expect': 'IVERILOG_FAILED', 'inject': m_compile,
         'stage': 'the simulator entry stops on a broken source'},
        {'mode': 'gates_not_met', 'expect': 'export gates failed', 'inject': m_gates,
         'stage': 'the gate block'},
        {'mode': 'missing_trace', 'expect': 'has no trace_pure_t30.vcd', 'inject': m_missing_trace,
         'stage': 'the trace-presence check inside re-judging'},
        {'mode': 'corrupt_trace', 'expect': 'REVIEW', 'inject': m_corrupt_trace,
         'stage': 'the VCD parser, reached by refreshing the recorded digest first',
         'expect_any': ('VcdError', 'Refuse')},
        {'mode': 'sample_extract_failure', 'expect': 'no edge samples could be extracted',
         'inject': m_sample_extract,
         'stage': 'the sampling stage itself, called directly because it sits behind a full re-judge'},
        {'mode': 'stale_cached_source', 'expect': 'produced by different sources',
         'inject': m_stale_source, 'stage': 'the source-identity gate'},
        {'mode': 'row_count_mismatch', 'expect': 'main rows are', 'inject': m_row_count,
         'stage': 'the row-count and unique-key block'},
        {'mode': 'trace_digest_mismatch', 'expect': 'hashes to', 'inject': m_trace_digest,
         'stage': 'the per-trace digest gate'},
        {'mode': 'synth_stats_unparsed_but_claimed_ok',
         'expect': '"SYNTHESIS_STRUCTURE": false',
         'inject': _synth_mode('synth_stats_unparsed_but_claimed_ok', _unparsed_claimed_ok),
         'stage': 'a summary that reports rc=0 and an empty problem list although the statistics were '
                  'never parsed: the gate must still refuse it'},
        {'mode': 'synth_stats_unparsed_as_written',
         'expect': '"SYNTHESIS_STRUCTURE": false',
         'inject': _synth_mode('synth_stats_unparsed_as_written', _unparsed_declared),
         'stage': 'the record do_synth now produces itself: parse failure carried in rc and problems'},
        {'mode': 'synth_structure_problem', 'expect': '"SYNTHESIS_STRUCTURE": false',
         'inject': _synth_mode('synth_structure_problem', _structure_broken),
         'stage': 'a real structural problem in the persisted summary'},
        {'mode': 'publish_first_file_fails', 'expect': 'publish aborted after 0/',
         'inject': _publish_mode(0), 'stage': 'the very first promotion', 'rollback': True},
        {'mode': 'publish_middle_file_fails', 'expect': 'promotion(s), the previous set is restored',
         'inject': _publish_mode(3), 'stage': 'a promotion in the middle of the set',
         'rollback': True},
        {'mode': 'publish_last_file_fails', 'expect': 'promotion(s), the previous set is restored',
         'inject': _publish_mode(10 ** 6), 'stage': 'the last promotion of the set',
         'rollback': True},
        {'mode': 'publish_staging_write_fails', 'expect': 'publish stopped before the first promotion',
         'inject': _write_failing_mode('staging', _nth_staging_write(2), 'staging write'),
         'stage': 'a catchable failure while writing the second staging file: the published set is '
                  'intact and neither the marker nor any .new of this transaction survives'},
        {'mode': 'publish_marker_write_fails', 'expect': 'publish stopped before the first promotion',
         'inject': _write_failing_mode('marker', lambda p: p.endswith(PENDING_MARKER), 'marker write'),
         'stage': 'a catchable failure while recording the transaction itself: nothing is promoted and '
                  'no half-written marker is left to be mistaken for an empty transaction'},
        {'mode': 'recover_uses_marker_recorded_backup', 'expect': None,
         'inject': m_recover_recorded_backup,
         'stage': 'an interruption between two promotions whose backup lives in a non-default run '
                  'directory: recovery with no argument must use the path the marker recorded and '
                  'only clear it once every target verified'},
        {'mode': 'publish_success', 'expect': None, 'inject': m_publish_ok,
         'stage': 'the normal publish path still works end to end', 'writes': True},
    ]


def write_guard_matrix(run_dir, keep=None):
    """run every mode against its own clean copy and demand the refusal it claims to test"""
    global EVIDENCE
    fixture = keep or os.path.join(PROJ, 'review', 'dd1_d7a', 'write_guard_fixture')
    if os.path.isdir(fixture):
        shutil.rmtree(fixture)
    os.makedirs(fixture)
    ev = os.path.join(fixture, 'evidence')
    real = EVIDENCE
    old_bytes = {}
    for name in sorted(os.listdir(real)) if os.path.isdir(real) else []:
        p = os.path.join(real, name)
        if os.path.isfile(p) and name.startswith('dd1_d7a_'):
            old_bytes[name] = u(io.open(p, encoding='utf-8').read())
    _IN_GUARD[0] = True
    try:
        EVIDENCE = ev
        _seed_evidence(ev, old_bytes)
        art = build_artefacts(run_dir)          # what a real export would publish, names and bytes
        for name, text in sorted(art.items()):
            old_bytes.setdefault(name, text)
        _seed_evidence(ev, old_bytes)           # every target pre-seeded, including the new names
        targets = sorted(old_bytes)
        modes = guard_modes(fixture, run_dir, art, old_bytes)
        results = []
        for spec in modes:
            _seed_evidence(ev, old_bytes)
            before = _digest_set(ev)
            raised, outcome, detail = False, 'RETURNED_WITHOUT_REFUSAL', ''
            try:
                spec['inject']()
                if spec['expect'] is not None:
                    outcome = 'RETURNED_WITHOUT_REFUSAL'
                else:
                    outcome = 'completed_without_refusal_expected'
            except (Exception, SystemExit) as exc:                          # noqa: BLE001
                raised = True
                outcome = 'refused: %s' % type(exc).__name__
                detail = str(exc)[:220]
            after = _digest_set(ev)
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            extra = sorted(set(after) - set(before))
            missing = sorted(set(before) - set(after))
            left = _leftovers(ev)
            want = spec['expect']
            hay = outcome + ' ' + detail
            if want is None:
                phrase_ok = True
            elif want == 'REVIEW':                # a real parse failure, message not fixed in advance
                phrase_ok = bool(detail) and 'has no trace' not in detail
            else:
                cands = (want,) + tuple(spec.get('expect_any') or ())
                phrase_ok = any(c in hay for c in cands)
            refused_ok = (raised if want is not None else not raised)
            if spec.get('writes'):
                # this mode publishes on purpose, and the injector itself asserts that every file
                # holds the staged bytes, that the marker is gone and that no staging file remains;
                # what the table adds is that nothing disappeared and nothing was left behind
                untouched_ok = (not missing) and (not left)
            else:
                untouched_ok = (not changed) and (not extra) and (not missing) and (not left)
            results.append({'mode': spec['mode'], 'stage': spec['stage'], 'outcome': outcome,
                            'expected_refusal': want, 'detail': detail,
                            'refusal_reason_matched': bool(phrase_ok),
                            'files_changed': changed, 'files_added': extra, 'files_missing': missing,
                            'leftover_temp_files': left, 'evidence_untouched': untouched_ok,
                            'rollback_expected': bool(spec.get('rollback')),
                            'mode_pass': bool(refused_ok and phrase_ok and untouched_ok)})
        return results, targets
    finally:
        EVIDENCE = real
        _IN_GUARD[0] = False


def write_guard_report(run_dir):
    res, targets = write_guard_matrix(run_dir)
    ok = all(r['mode_pass'] for r in res)
    lines = [u'DATA-7A write guard matrix',
             u'',
             u'Every mode below gets its own clean copy of an exportable run and its own pre-seeded',
             u'copy of the real evidence set -- %d target files, the set derived from a clean build'
             % len(targets),
             u'rather than typed -- so no mode can be stopped by the damage a previous mode did.',
             u'A mode passes only when the refusal it claims is the refusal that happened, the whole',
             u'file set is unchanged by name, content and absence, and no staging or marker file is',
             u'left behind. The official evidence path is never the target of an attempt.',
             u'',
             u'target files seeded: %s' % ', '.join(targets),
             u'',
             u'mode                     outcome              reason-hit changed/added/missing  verdict']
    for r in res:
        lines.append(u'%-26s %-20s %-10s %-24s %s'
                     % (r['mode'], r['outcome'][:20],
                        'yes' if r['refusal_reason_matched'] else 'NO',
                        '%s/%s/%s' % (','.join(r['files_changed']) or '-',
                                      ','.join(r['files_added']) or '-',
                                      ','.join(r['files_missing']) or '-')[:24],
                        'PASS' if r['mode_pass'] else 'FAIL'))
    lines.append(u'')
    lines.append(u'per-mode detail (the refusal text that was actually produced):')
    for r in res:
        lines.append((u'  %-26s expect=%-34s got=%s'
                      % (r['mode'], str(r['expected_refusal'])[:34],
                         r['detail'][:120])).rstrip())
    lines.append(u'')
    ev = os.path.join(PROJ, 'review', 'dd1_d7a', 'write_guard_fixture', 'evidence')
    lines.append(u'per-file sha256 of the fixture evidence set after the last attempt:')
    dig = _digest_set(ev)
    for name in sorted(dig):
        lines.append(u'  %-34s %s' % (name, dig[name]))
    lines.append(u'')
    lines.append(u'state after the matrix: leftover staging/marker files = %s'
                 % (_leftovers(ev) or 'none'))
    lines.append(u'publish atomicity boundary: each file is replaced by os.replace (atomic per file);')
    lines.append(u'the SET is kept consistent for any failure the process can catch, by restoring the')
    lines.append(u'bytes backed up before the first promotion. A SIGKILL or power loss between two')
    lines.append(u'promotions is not covered by that rollback: the pending marker then survives and it')
    lines.append(u'names the backup directory of its own transaction, so recover_publish() restores')
    lines.append(u'that set without being told where it is, clears the marker only after every target')
    lines.append(u'has been verified, and keeps it -- refusing the next publish as well -- whenever a')
    lines.append(u'backup is missing, hashes differently, cannot be written back, or the marker itself')
    lines.append(u'cannot be read as a transaction record.')
    lines.append(u'')
    lines.append(u'WRITE_GUARD: %s' % ('PASS' if ok else 'FAIL'))
    return u'\n'.join(lines) + u'\n'


def do_write_guard(args):
    run_dir = os.path.abspath(args['out'] if args.get('out') else os.path.join(
        PROJ, 'review', 'dd1_d7a', 'FINAL'))
    if not os.path.exists(os.path.join(run_dir, 'run_summary.json')):
        print('write guard needs a completed run directory with run_summary.json')
        return 1
    res, targets = write_guard_matrix(run_dir)
    for r in res:
        print('%-26s %-20s reason=%-5s changed=%s added=%s missing=%s left=%s pass=%s'
              % (r['mode'], r['outcome'][:20], 'yes' if r['refusal_reason_matched'] else 'NO',
                 r['files_changed'] or '-', r['files_added'] or '-', r['files_missing'] or '-',
                 r['leftover_temp_files'] or '-', r['mode_pass']))
    ok = all(r['mode_pass'] for r in res)
    print('WRITE_GUARD: %s (%d modes, %d target files)' % ('PASS' if ok else 'FAIL',
                                                           len(res), len(targets)))
    io.open(os.path.join(run_dir, 'write_guard.txt'), 'w', encoding='utf-8',
            newline='\n').write(u(json.dumps({'modes': res, 'targets': targets}, indent=1,
                                             sort_keys=True) + '\n'))
    return 0 if ok else 1


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


def entry_selftest():
    """the runner's own integrity gates, tested without a simulator, a netlist or the checker

    The checker selftest proves the waveform judgement. This proves the parts that decide whether a
    result may be published at all: the statistics parse status, the gate that reads it, the multi-file
    publish rollback and success path, and the publish transaction record -- the backup it names, the
    prior state it carries, and what has to be verified before it may be closed.
    """
    global EVIDENCE
    lines, bad = [], [0]

    def note(cond, name, detail):
        if not cond:
            bad[0] += 1
        lines.append((u'%-4s entry %-38s %s' % ('PASS' if cond else 'FAIL', name, detail)).rstrip())

    odd_table = (u'3. Printing statistics.\n\n'
                 u'   146 cells:                       1099 wires, 21 processes\n'
                 u'    38   $_AND_                       38 cells\n'
                 u'     6   $adff    6 cells (this shape is not the one parsed above)\n')
    st = synth_status(0, odd_table)
    note(st['stat_parse'].startswith('UNPARSED'), 'unparsable statistics table is noticed',
         st['stat_parse'][:70])
    note(st['entry_rc'] == 1 and bool(st['problems']),
         'unparsed statistics fails the ENTRY, not just a note', 'entry_rc=%d problems=%d'
         % (st['entry_rc'], len(st['problems'])))
    note(st['yosys_rc'] == 0, 'the tool rc is still recorded separately', 'yosys_rc=%d'
         % st['yosys_rc'])
    note(not synth_gate_ok({'rc': 0, 'problems': [], 'stat_parse': st['stat_parse'], 'cells': {}}),
         'gate refuses the stale rc=0 / empty-problems pair', 'the exact shape the old summary wrote')
    note(synth_gate_ok({'rc': 0, 'problems': [], 'stat_parse': 'parsed', 'cells': {'$_adff': 6}}),
         'gate accepts a clean parsed record', 'positive control')
    note(not synth_gate_ok({'rc': 1, 'problems': ['an inferred latch'], 'stat_parse': 'parsed',
                            'cells': {'$dlatch': 1}}), 'gate refuses a declared problem', 'negative')

    scratch = os.path.join(PROJ, 'review', 'dd1_d7a', 'entry_selftest_publish')
    old_ev = EVIDENCE
    try:
        names = ['dd1_d7a_cases.csv', 'dd1_d7a_control_cases.csv', 'dd1_d7a_manifest.json']
        for attempt in ('fail', 'ok'):
            ev = os.path.join(scratch, attempt)
            _seed_evidence(ev, dict((n, u'OLD_NONEMPTY %s\n' % n) for n in names))
            EVIDENCE = ev
            before = _digest_set(ev)
            art = dict((n, u'NEW_NONEMPTY %s\n' % n) for n in names)
            promote, seen = _promote_failing_at(1) if attempt == 'fail' else (None, None)
            raised = ''
            try:
                publish(art, backup_dir=os.path.join(scratch, 'backup_' + attempt), promote=promote)
            except ck.Refuse as exc:
                raised = str(exc)[:120]
            after = _digest_set(ev)
            if attempt == 'fail':
                note(bool(raised), 'publish with a mid-set failure raises', raised[:60])
                note(after == before, 'every previously published file kept its old bytes',
                     'changed=%s missing=%s' % (sorted(k for k in before if before.get(k) !=
                                                      after.get(k)), sorted(set(before) - set(after))))
                note(not _leftovers(ev), 'no staging or marker file survives the rollback',
                     str(_leftovers(ev)))
            else:
                want = dict((n, hashlib.sha256(u(art[n]).encode('utf-8')).hexdigest())
                            for n in names)
                note(not raised and after == want, 'a clean publish puts the new bytes in place',
                     raised[:60] or 'ok')
                note(not _leftovers(ev) and pending_publish() is None,
                     'a clean publish leaves no pending transaction behind', 'checked')

        # ---- the transaction record: who it is, and what has to be true to close it ----
        tx = os.path.join(scratch, 'transaction')
        old_bytes = dict((n, u'TX_OLD %s\n' % n) for n in names)
        new_bytes = dict((n, u'TX_NEW %s\n' % n) for n in names)

        class Interrupted(BaseException):
            """an interruption the caught-failure rollback is not allowed to see"""

        def case(name):
            """a fresh fixture with the previous generation in place, pointed at as the evidence dir"""
            ev = os.path.join(tx, name)
            _seed_evidence(ev, old_bytes)
            return ev

        def interrupt_at_second_promotion(ev, bak, after=False):
            calls = []

            def promote(src, dst):
                calls.append(os.path.basename(dst))
                os.replace(src, dst)
                if len(calls) == (3 if after else 2):
                    raise Interrupted('INJECTED interruption at the promotion boundary')
            try:
                publish(new_bytes, backup_dir=bak, promote=promote)
            except Interrupted:
                pass
            return calls

        good = {'schema': MARKER_SCHEMA, 'phase': MARKER_PHASE, 'files': names,
                'backup': 'review/x', 'previous': dict((n, 'a' * 64) for n in names), 'absent': []}
        note(_marker_error(good) is None, 'a complete transaction record validates',
             'positive control for schema %s' % MARKER_SCHEMA)
        note(_marker_error({'phase': MARKER_PHASE, 'files': names}) is not None,
             'a record without schema/backup/prior state is unusable',
             str(_marker_error({'phase': MARKER_PHASE, 'files': names}))[:70])
        contradict = dict(good, absent=['dd1_d7a_negative.csv'])
        note(_marker_error(contradict) is not None,
             'a record whose file set contradicts its prior state is unusable',
             str(_marker_error(contradict))[:70])

        ev = case('recorded_backup')
        EVIDENCE = ev
        before = _digest_set(ev)
        bak = os.path.join(tx, 'a_run_dir', 'publish_backup')
        if len(interrupt_at_second_promotion(ev, bak)) != 2:
            note(False, 'the injected interruption reached the promotion boundary', 'it did not')
        state = pending_publish()
        note(state is not None and not state.get('marker_invalid'),
             'an interrupted publish leaves a readable transaction record',
             str(state)[:70])
        rec = recover_publish()                                 # no argument, exactly like do_export
        note(rec.get('backup_used') == _record_path(bak) and rec.get('complete') is True,
             'recovery with no argument uses the backup the marker names',
             json.dumps(dict((k, rec[k]) for k in ('backup_used', 'complete', 'marker_kept')),
                        sort_keys=True)[:90])
        note(_digest_set(ev) == before, 'that recovery puts every previous byte back',
             str(sorted(k for k in before if before.get(k) != _digest_set(ev).get(k)))[:70])
        note(not _leftovers(ev) and pending_publish() is None,
             'a completed recovery cleans up its own staging files', str(_leftovers(ev)))

        ev = case('backup_missing')
        EVIDENCE = ev
        before = _digest_set(ev)
        bak = os.path.join(tx, 'another_run', 'publish_backup')
        interrupt_at_second_promotion(ev, bak)
        os.remove(os.path.join(bak, names[0]))
        first, second = recover_publish(), recover_publish()
        note(first.get('complete') is False and second.get('complete') is False,
             'an incomplete recovery stays incomplete on every retry',
             'first=%s second=%s' % (first.get('complete'), second.get('complete')))
        note(first.get('marker_kept') and second.get('marker_kept') and pending_publish() is not None,
             'the failed recoveries keep the pending marker instead of hiding the transaction',
             str(pending_publish())[:70])
        refused = ''
        try:
            publish(new_bytes, backup_dir=os.path.join(tx, 'must_not_be_used'))
        except ck.Refuse as exc:
            refused = str(exc)[:70]
        note(bool(refused), 'a new publish is refused while a transaction is outstanding', refused)
        with io.open(os.path.join(bak, names[0]), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(u(old_bytes[names[0]]))                    # the operator restores the backup
        third = recover_publish()
        note(third.get('complete') is True and pending_publish() is None,
             'once the backup is whole the same transaction recovers and closes',
             json.dumps(dict((k, third[k]) for k in ('complete', 'restored', 'marker_kept')),
                        sort_keys=True)[:90])
        note(_digest_set(ev) == before, 'the repaired recovery verified the whole set',
             str(sorted(set(before) ^ set(_digest_set(ev))))[:70])

        ev = case('corrupt_marker')
        EVIDENCE = ev
        with io.open(os.path.join(ev, names[0]), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(u(new_bytes[names[0]]))                    # the mixed content a crash can leave
        with io.open(os.path.join(ev, PENDING_MARKER), 'w', encoding='utf-8', newline='\n') as fp:
            fp.write(u('{NOT_VALID_JSON'))
        damaged = _digest_set(ev)
        state = pending_publish()
        rec = recover_publish()
        note(bool(state.get('marker_invalid')), 'a corrupt marker is noticed, not read as empty',
             str(state.get('marker_invalid'))[:70])
        note(rec.get('complete') is False and rec.get('marker_kept') is True,
             'a corrupt marker is never an already-completed recovery', str(rec)[:90])
        note(os.path.exists(os.path.join(ev, PENDING_MARKER)) and _digest_set(ev) == damaged,
             'the corrupt marker and the damaged set are both kept for the operator',
             'leftovers=%s' % _leftovers(ev))

        ev = case('bad_schema_marker')
        EVIDENCE = ev
        for text in (json.dumps({'phase': MARKER_PHASE, 'files': names}),
                     json.dumps(dict(good, files='not-a-list')),
                     json.dumps(dict(good, previous=dict((n, 'not-a-digest') for n in names))),
                     json.dumps([])):
            with io.open(os.path.join(ev, PENDING_MARKER), 'w', encoding='utf-8',
                         newline='\n') as fp:
                fp.write(u(text))
            state = pending_publish()
            rec = recover_publish()
            if not (state.get('marker_invalid') and rec.get('complete') is False
                    and rec.get('marker_kept') is True):
                note(False, 'an incomplete or ill-typed marker is refused', text[:70])
                break
        else:
            note(True, 'an incomplete or ill-typed marker is refused',
                 '4 shapes: missing fields, wrong file type, wrong digest form, not an object')

        ev = case('staging_write_fails')
        EVIDENCE = ev
        before = _digest_set(ev)
        original, seen = _fsync_write, []

        def fail_second_staging(path, data):
            if path.endswith('.new'):
                seen.append(os.path.basename(path))
                if len(seen) == 2:
                    raise OSError('INJECTED staging write failure')
            return original(path, data)
        raised = ''
        try:
            globals()['_fsync_write'] = fail_second_staging
            publish(new_bytes, backup_dir=os.path.join(tx, 'staging_backup'))
        except ck.Refuse as exc:
            raised = str(exc)[:70]
        finally:
            globals()['_fsync_write'] = original
        note(bool(raised), 'a catchable staging failure is refused, not left to escape', raised)
        note(_digest_set(ev) == before and not _leftovers(ev) and pending_publish() is None,
             'a staging failure cleans up this transaction and touches nothing else',
             'extras=%s' % sorted(set(_digest_set(ev)) - set(before)))

        ev = case('previously_absent_target')
        os.remove(os.path.join(ev, names[-1]))                  # this one legitimately did not exist
        EVIDENCE = ev
        before = _digest_set(ev)
        bak = os.path.join(tx, 'absent_backup')
        # the interruption lands after the last promotion: the new file is really published
        interrupt_at_second_promotion(ev, bak, after=True)
        rec = recover_publish()
        note(rec.get('complete') is True and pending_publish() is None,
             'a target that did not exist before is restored to not-existing', str(rec)[:90])
        note(_digest_set(ev) == before, 'the absent-target recovery verified every other file too',
             str(sorted(set(_digest_set(ev)) ^ set(before)))[:70])

        ev = case('foreign_staging_untouched')
        EVIDENCE = ev
        with io.open(os.path.join(ev, 'some_other_stage.csv.new'), 'w', encoding='utf-8',
                     newline='\n') as fp:
            fp.write(u('NOT A FILE OF THIS TRANSACTION\n'))
        interrupt_at_second_promotion(ev, os.path.join(tx, 'foreign_backup'))
        recover_publish()
        note(os.path.exists(os.path.join(ev, 'some_other_stage.csv.new')),
             'recovery cleans only its own transaction files, it never sweeps the directory',
             str(_leftovers(ev)))
    finally:
        EVIDENCE = old_ev
        for d in (scratch, tx):
            if os.path.isdir(d):
                shutil.rmtree(d)
    return bad[0], u'\n'.join(lines)


def do_selftest(args):
    bad, report = ck.selftest()
    ebad, ereport = entry_selftest()
    full = report + u'\n' + ereport + u'\n'
    print(full)
    print('CHECKER_SELFTEST: %s' % ('PASS' if bad == 0 else 'FAIL (%d)' % bad))
    print('ENTRY_SELFTEST: %s' % ('PASS' if ebad == 0 else 'FAIL (%d)' % ebad))
    run_dir = args.get('out')
    if run_dir and bad == 0 and ebad == 0:
        d = os.path.abspath(run_dir)
        os.path.isdir(d) or os.makedirs(d)
        write_atomic(os.path.join(d, 'checker_selftest.txt'), full)
    return 0 if (bad == 0 and ebad == 0) else 1


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
