#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR hybrid path: compile and simulate the accepted controller, then turn the real
four-state VCD into the PWL stimulus of the two joint cases.

The expectation for every frame is rebuilt from the input codes recorded in the VCD plus the measured
tick stream. It is never copied from the DUT's own target counter. A trace that holds x or z after the
controller's first reference edge, or that breaks the accepted protocol, is refused here and never
reaches the analogue bench.
"""

import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7a_trace as TD                      # frozen four-state reader: imported, never modified
import dd1_d7b_trace as B7T                     # frozen VCD facts and the finite-slope PWL builder
import dd1_d7c_b_tr_contract as TRC
import dd1_d7c_b_tr_decks as DECK
import dd1_d7a_run as D7A

SCOPE = 'tb_dd1_d7c_b_tr_hyb'
TB_PATH = 'tests/dd1_d7c_b_tr/tb_dd1_d7c_b_tr_hyb.sv'
RTL_PATH = TRC.RTL_PATH
CASES = ('HYB-120', 'HYB-200')
SCALARS = ('clk', 'reset_n', 'system_en', 'tick', 'blank', 'fault', 'cfg_valid', 'latch_stb',
           'pwm_start', 'data_en', 'data_en_b', 'obs_tick')
BUSES = ('mode', 'cfg_pure', 'cfg_hyb_time', 'cfg_hyb_pam', 'pam_sel', 'win_state', 'cfg_version',
         'proto_err')
CONVERTED = ('data_en', 'pam0', 'pam1', 'pam2')
TICK_NS = {'HYB-120': 120.0, 'HYB-200': 200.0}
RAMP_PS = int(TRC.EDGE_NS * 1000)               # 2000 ps total edge width
SHIFT_PS = int(TRC.SHIFT_NS * 1000)             # the whole wave moves right by 1000 ns
BOUNDARY_TICKS = 65                             # 64 intervals plus the tick that ends the window
T5_TOLERANCE_NS = 1.0
LEAD_NS = 5.0                                   # the accepted bench raises the tick 5 ns early


Refuse = B7T.Refuse        # one refusal type across the accepted converter and this one, so a caller
                           # that catches one catches the other instead of missing it


def refuse_on_parse_error(trace_path, action):
    try:
        return action()
    except TD.VcdError as error:
        raise Refuse('%s cannot be read as a four-state trace: %s' % (trace_path, error))


def repo(path):
    return os.path.join(ROOT, path.replace('/', os.sep))


def sha_file(path):
    return TRC.sha_file(path)


def group_for(case_id):
    if case_id == 'HYB-120':
        return {'case_id': case_id, 'tick_ns': 120.0, 'plusargs': ['+GROUP120'], 'safety': True}
    if case_id == 'HYB-200':
        return {'case_id': case_id, 'tick_ns': 200.0, 'plusargs': ['+GROUP200'], 'safety': False}
    raise Refuse('%s is not one of the two hybrid cases' % case_id)


def plan_for(case_id):
    """the frames this case must show, taken from the contract, with the interval count it expects"""
    group = group_for(case_id)
    frames = []
    for row in TRC.contract()['hybrid']['frames']:
        frames.append({'frame': row['frame'], 'cfg_hyb_time': row['cfg_hyb_time'],
                       'cfg_hyb_pam': row['cfg_hyb_pam'],
                       'expected_intervals': row['expected_conducting_intervals'],
                       'kind': 'normal'})
    if group['safety']:
        safety = TRC.contract()['hybrid']['safety_frame']
        frames.append({'frame': safety['frame'], 'cfg_hyb_time': safety['cfg_hyb_time'],
                       'cfg_hyb_pam': safety['cfg_hyb_pam'],
                       'expected_intervals': safety['planned_intervals'], 'kind': 'safety'})
    return frames


def series(trace, name, defined_from_ps):
    """x or z is refused at or after the controller's first reference edge and counted before it"""
    edges, undefined = B7T.bus_values(trace, '%s/%s' % (SCOPE, name), defined_from_ps)
    return edges, undefined


def read_vcd(vcd_path):
    """everything the frame analysis needs, measured off the real dump"""
    if not os.path.isfile(vcd_path):
        raise Refuse('trace %s does not exist' % vcd_path)
    if os.path.getsize(vcd_path) == 0:
        raise Refuse('trace %s is empty: nothing was dumped' % vcd_path)
    trace = refuse_on_parse_error(vcd_path, lambda: TD.Trace(vcd_path))
    missing = [name for name in SCALARS + BUSES if not trace.has('%s/%s' % (SCOPE, name))]
    if missing:
        raise Refuse('the dump carries no %s under scope %s; the testbench was asked to record all '
                     'twenty of them' % (','.join(missing), SCOPE))
    clk_edges, _clk_x = series(trace, 'clk', 0)
    rises = [t for t, v in clk_edges if v == 1]
    if len(rises) < 3:
        raise Refuse('the reference clock has %d rising edges, which is not a 100 MHz run'
                     % len(rises))
    if any((rises[i + 1] - rises[i]) != (rises[1] - rises[0]) for i in range(len(rises) - 1)):
        raise Refuse('the reference clock period is not uniform, so no tick interval can be named')
    period_ps = rises[1] - rises[0]
    if period_ps != 10000:
        raise Refuse('the reference period reads %d ps, the contract fixes a 100 MHz domain'
                     % period_ps)
    gate = rises[0]                            # the first edge that clears the controller registers
    out = {'edges': {}, 'xz_before_first_reference_edge': {}}
    for name in SCALARS + BUSES:
        edges, undefined = series(trace, name, gate)
        out['edges'][name] = edges
        out['xz_before_first_reference_edge'][name] = undefined
    out['vcd'] = os.path.basename(vcd_path)
    out['vcd_sha256'] = sha_file(vcd_path)
    out['vcd_bytes'] = os.path.getsize(vcd_path)
    out['header'] = B7T.header_facts(vcd_path)
    out['clk_rises_ps'] = rises
    out['clk_period_ps'] = period_ps
    out['end_ps'] = int(trace.end_time)
    out['aliased_ids'] = trace.aliased
    out['same_time_edges'] = trace.same_time_edges
    return out


def _value_at(edges, t_ps):
    return B7T.value_at(edges, t_ps, 0)


def _falls(edges, value=0):
    return [t for t, v in edges if v == value]


def segment_frames(vcd):
    """reset events delimit the frames: the testbench walks the whole protocol once per frame"""
    edges = vcd['edges']
    starts = _falls(edges['reset_n'])
    if not starts:
        raise Refuse('the trace shows no reset fall, so the frames cannot be delimited')
    ends = starts[1:] + [vcd['end_ps']]
    out = []
    for index, (start, end) in enumerate(zip(starts, ends)):
        out.append({'index': index, 'start_ps': start, 'end_ps': end})
    return out


def frame_details(vcd, frame, plan, tick_ps):
    """one frame: the loaded code, t0, the measured conduction and the protocol evidence"""
    edges = vcd['edges']
    window = lambda name: [(t, v) for t, v in edges[name] if frame['start_ps'] <= t <= frame['end_ps']]
    latch_rises = [t for t, v in window('latch_stb') if v == 1]
    if len(latch_rises) != 1:
        raise Refuse('frame %d shows %d latch requests, the protocol allows exactly one'
                     % (frame['index'], len(latch_rises)))
    # the frame opens with the input at its rest level, so the fall that bounds the request is the
    # first one after its rise, not the first zero recorded inside the window
    latch_falls = [t for t, v in window('latch_stb') if v == 0 and t > latch_rises[0]]
    if not latch_falls:
        raise Refuse('frame %d: the latch request never falls again, so it spans the rest of the '
                     'frame and the sampling edge cannot be named' % frame['index'])
    after = [t for t in vcd['clk_rises_ps'] if latch_rises[0] < t <= latch_falls[0]]
    if not after:
        raise Refuse('frame %d: the latch request falls again before any reference edge samples it, '
                     'so no LATCH edge exists' % frame['index'])
    # the accepted RTL keys on the request edge, so the LATCH is taken at the first rising edge after
    # the request rises; holding the request up across later edges cannot latch twice, and the version
    # step below is what proves that
    latch_edge = after[0]
    version_before = _value_at(edges['cfg_version'], latch_edge - 1)
    # the value in effect at the sampling edge comes from the whole series: a bus that does not change
    # between two frames is not re-dumped, so reading only inside the window would lose it
    ht = _value_at(edges['cfg_hyb_time'], latch_edge - 1)
    pam = _value_at(edges['cfg_hyb_pam'], latch_edge - 1)
    # the code is three separate wires: pam0 is bit 0 with weight 1, so the text form is the bit
    # pattern, never the decimal digits of the bus value
    code = format(pam, '03b')
    obs = [t for t, v in window('obs_tick') if v == 1]
    tick_rises = [t for t, v in window('tick') if v == 1]
    if not obs:
        raise Refuse('frame %d accepts no tick at all: the controller never armed a window'
                     % frame['index'])
    t0 = [t for t in vcd['clk_rises_ps'] if t >= obs[0]][0]
    lead = t0 - obs[0]
    de = [(t, v) for t, v in edges['data_en'] if t >= t0 and t <= frame['end_ps']]
    segments = B7T.segments_of(de, t0, frame['end_ps'])
    mode = _value_at(edges['mode'], latch_edge - 1)
    version = _value_at(edges['cfg_version'], latch_edge)
    fault_rises = [t for t, v in window('fault') if v == 1]
    fault_falls = [t for t, v in window('fault') if v == 0
                   and (not fault_rises or t > fault_rises[0])]
    return {'index': frame['index'], 'frame': plan['frame'], 'kind': plan['kind'],
            'start_ps': frame['start_ps'], 'end_ps': frame['end_ps'],
            'cfg_hyb_time': ht, 'cfg_hyb_pam': code, 'cfg_hyb_pam_value': pam,
            'mode_at_latch': mode,
            'latch_edge_ps': latch_edge, 'cfg_version_after_latch': version,
            'cfg_version_before_latch': version_before,
            'latch_edges_spanned': len(after),
            't0_ps': t0, 'tick_lead_ps': lead,
            'accepted_tick_ps': obs, 'accepted_ticks': len(obs),
            'tick_pulses_raised': len(tick_rises),
            'conducting_segments': [[a, b, b - a] for a, b, _w in segments],
            'conduct_ns': [round((b - a) / 1000.0, 3) for a, b, _w in segments],
            'pam_held_ps': [[t, v] for t, v in window('pam_sel') if t >= t0],
            'fault_rise_ps': fault_rises[0] if fault_rises else None,
            'fault_fall_ps': fault_falls[0] if fault_falls else None,
            'expected_intervals': plan['expected_intervals'],
            'expected_conduction_ns': round(plan['expected_intervals'] * tick_ps / 1000.0, 3),
            'expected_pam': plan['cfg_hyb_pam'],
            'expected_tick_ns': tick_ps / 1000.0}


def check_frames(vcd, frames, case_id):
    """the protocol and the conduction of each frame against the independent expectation"""
    problems = []
    tick_ps = int(TICK_NS[case_id] * 1000)
    for row in frames:
        tag = '%s frame %s' % (case_id, row['frame'])
        if row['cfg_hyb_time'] != (63 if row['expected_intervals'] == 64
                                   else row['expected_intervals']):
            problems.append('%s: cfg_hyb_time reads %d, the contract loads %d for %d intervals'
                            % (tag, row['cfg_hyb_time'],
                               63 if row['expected_intervals'] == 64 else row['expected_intervals'],
                               row['expected_intervals']))
        if row['cfg_hyb_pam'] != row['expected_pam']:
            problems.append('%s: cfg_hyb_pam reads %s, the contract loads %s'
                            % (tag, row['cfg_hyb_pam'], row['expected_pam']))
        if row['mode_at_latch'] != 1:
            problems.append('%s: the mode sampled at the latch edge is %d, Hybrid needs 1'
                            % (tag, row['mode_at_latch']))
        if row['cfg_version_after_latch'] != row['cfg_version_before_latch'] + 1:
            problems.append('%s: cfg_version reads %d at the latch edge and was %d before it, one '
                            'accepted LATCH steps it by exactly one'
                            % (tag, row['cfg_version_after_latch'], row['cfg_version_before_latch']))
        steps = [pair for pair in vcd['edges']['cfg_version']
                 if row['latch_edge_ps'] <= pair[0] <= row['end_ps']]
        if len(steps) != 1 or steps[0][0] != row['latch_edge_ps']:
            problems.append('%s: cfg_version moves %d time(s) after its latch edge (%s), a frame may '
                            'carry exactly one accepted LATCH and the recovery after an abort may '
                            'not add a second one' % (tag, len(steps), steps[:3]))
        if row['tick_lead_ps'] != int(LEAD_NS * 1000):
            problems.append('%s: the accepted tick is %d ps before its consuming edge, the bench '
                            'convention is %d ps' % (tag, row['tick_lead_ps'],
                                                     int(LEAD_NS * 1000)))
        if row['kind'] == 'normal':
            gaps = sorted(set(row['accepted_tick_ps'][index] - row['accepted_tick_ps'][index - 1]
                              for index in range(1, len(row['accepted_tick_ps']))))
            if gaps != [tick_ps]:
                problems.append('%s: the accepted ticks are %s ps apart, the case names one %d ps '
                                'tick interval' % (tag, gaps, tick_ps))
            if row['accepted_ticks'] != BOUNDARY_TICKS:
                problems.append('%s: %d accepted ticks, the window ends with %d boundary events'
                                % (tag, row['accepted_ticks'], BOUNDARY_TICKS))
            if row['tick_pulses_raised'] < BOUNDARY_TICKS + 2:
                problems.append('%s: the tick stream stopped after %d pulses, at least %d must '
                                'follow win_state DONE'
                                % (tag, row['tick_pulses_raised'], BOUNDARY_TICKS + 2))
            want_ns = row['expected_conduction_ns']
            got = row['conducting_segments']
            if row['expected_intervals'] == 0:
                if got:
                    problems.append('%s: a zero code must stay black, it conducted %s ns'
                                    % (tag, [round(w / 1000.0, 3) for _a, _b, w in got]))
            elif len(got) != 1 or abs(got[0][2] / 1000.0 - want_ns) > 1e-9:
                problems.append('%s: conduction reads %s ns, the code and the measured tick ask for '
                                '%g ns' % (tag, [round(w / 1000.0, 3) for _a, _b, w in got],
                                           want_ns))
            if row['pam_held_ps']:
                problems.append('%s: pam_sel moves inside the frame (%s), the contract holds it for '
                                'the whole frame and its tail'
                                % (tag, row['pam_held_ps'][:2]))
        else:
            if row['fault_rise_ps'] is None or row['fault_fall_ps'] is None:
                problems.append('%s: the safety frame shows no complete fault event' % tag)
            else:
                want_ps = row['t0_ps'] + (5 * tick_ps) // 2 + 3000
                drift = (row['fault_rise_ps'] - want_ps) / 1000.0
                if abs(drift) > T5_TOLERANCE_NS:
                    problems.append('%s: the fault rises %g ns away from t0 + 2.5T + 3 ns'
                                    % (tag, drift))
                hold = (row['fault_fall_ps'] - row['fault_rise_ps']) / 1000.0
                if hold < TRC.SAFETY_HOLD_NS:
                    problems.append('%s: the fault is held %g ns, at least %g ns is required'
                                    % (tag, hold, TRC.SAFETY_HOLD_NS))
                after = [pair for pair in row['conducting_segments']
                         if pair[0] > row['fault_fall_ps']]
                if after:
                    problems.append('%s: the enable re-lights after the fault is withdrawn (%s), '
                                    'the aborted window must stay black'
                                    % (tag, after[:1]))
                black_ns = (row['end_ps'] - row['fault_fall_ps']) / 1000.0
                if black_ns < TRC.SAFETY_BLACK_NS:
                    problems.append('%s: only %g ns of black is observed after the withdrawal, the '
                                    'contract asks for %g ns'
                                    % (tag, black_ns, TRC.SAFETY_BLACK_NS))
                if len(row['conducting_segments']) != 1:
                    problems.append('%s: the safety frame gives %d conducting segments, exactly one '
                                    'aborted segment is expected'
                                    % (tag, len(row['conducting_segments'])))
    # inter-frame rules, from the recorded inputs
    for index in range(1, len(frames)):
        before, after = frames[index - 1], frames[index]
        gap_ns = (after['t0_ps'] - before['t0_ps']) / 1000.0
        last_edge = max([pair[1] for pair in before['pam_held_ps']]
                        + [before['end_ps']])
        lead_ns = (after['t0_ps'] - last_edge) / 1000.0
        if lead_ns < TRC.CODE_CHANGE_LEAD_NS:
            problems.append('%s: the code of frame %s settles %g ns before the next enable rise, '
                            'the contract asks for %g ns'
                            % (case_id, after['frame'], lead_ns, TRC.CODE_CHANGE_LEAD_NS))
        black_ns = gap_ns - before['expected_conduction_ns']
        if black_ns < TRC.INTER_FRAME_PREP_NS:
            problems.append('%s: only %g ns of enable-low preparation between frame %s and %s'
                            % (case_id, black_ns, before['frame'], after['frame']))
    return problems


def pam_bit_edges(vcd, index):
    """the pam_sel bus split into the three single-bit series the bench drives"""
    out = []
    previous = None
    for t, value in vcd['edges']['pam_sel']:
        bit = (value >> index) & 1
        if previous is None:
            previous = bit
            continue
        if bit != previous:
            out.append((t, bit))
            previous = bit
    return out


def convert(case_id, vcd_path):
    """the delivered PWL for one hybrid case, with the frame evidence that justifies it"""
    group = group_for(case_id)
    plan = plan_for(case_id)
    vcd = read_vcd(vcd_path)
    frames = segment_frames(vcd)
    if len(frames) != len(plan):
        raise Refuse('%s: the trace holds %d frames, the contract plans %d'
                     % (case_id, len(frames), len(plan)))
    tick_ps = int(group['tick_ns'] * 1000)
    details = [frame_details(vcd, frame, row, tick_ps)
               for frame, row in zip(frames, plan)]
    problems = check_frames(vcd, details, case_id)
    if problems:
        raise Refuse('%s: the accepted protocol is not met: %s' % (case_id, ' | '.join(problems)))
    t_start = 0
    t_stop = vcd['end_ps']
    waves, edge_sets = {}, {}
    edge_sets['data_en'] = [(t, v) for t, v in vcd['edges']['data_en'] if t_start <= t <= t_stop]
    for index in range(3):
        edge_sets['pam%d' % index] = pam_bit_edges(vcd, index)
    for node, edges in sorted(edge_sets.items()):
        points, _cur = B7T.build_pwl(edges, t_start, t_stop, SHIFT_PS, RAMP_PS,
                                     level=TRC.LOGIC_HIGH_V)
        waves[node] = points
    check_text = ''.join('V%s (%s 0) vsource type=pwl wave=[%s]\n'
                         % (node, node, DECK.format_wave(waves[node])) for node in CONVERTED)
    shape_problems, _parsed = DECK.verify_pwl(check_text, edge_sets, ctx=case_id)
    if shape_problems:
        raise Refuse('%s: the delivered PWL does not re-read as the conversion it claims: %s'
                     % (case_id, ' | '.join(shape_problems)))
    stop_ns = (t_stop + SHIFT_PS) / 1000.0
    return {'case_id': case_id, 'group': group, 'waves': waves, 'stop_ns': stop_ns,
            'edges': edge_sets, 'frames': details, 'vcd_sha256': vcd['vcd_sha256'],
            'vcd_bytes': vcd['vcd_bytes'], 'vcd_header': vcd['header'],
            'rtl_blob_sha256': TRC.blob_sha(TRC.BASE_SHA, RTL_PATH),
            'tick_ps': tick_ps, 'frame_count': len(details),
            'end_ps': vcd['end_ps'], 'aliased_ids': vcd['aliased_ids'],
            'same_time_edges': vcd['same_time_edges'],
            'xz_before_first_reference_edge': vcd['xz_before_first_reference_edge'],
            'converted_signals': list(CONVERTED), 'edge_total_ns': TRC.EDGE_NS,
            'shift_ns': TRC.SHIFT_NS,
            'not_a_claim': TRC.contract()['hybrid']['not_a_claim']}


# ---- the simulator runs ---------------------------------------------------------------------------

def tools():
    return D7A.find_tools()


def tb_declared(text):
    """the identifiers a $dumpvars(1, tb) run can record: the declarations in the TB scope"""
    names = set()
    for line in text.split('\n'):
        found = re.match(r"^\s*(?:reg|wire)\s+(?:\[\s*\d+\s*:\s*\d+\s*\]\s*)?(.*?)\s*;", line)
        if not found or 'function' in line or 'task' in line:
            continue
        for part in found.group(1).split(','):
            identifier = re.match(r"\s*([A-Za-z_]\w*)", part)
            if identifier:
                names.add(identifier.group(1))
    return names


def tb_missing_signals(tb_text):
    return [name for name in SCALARS + BUSES if name not in tb_declared(tb_text)]


def compile_tb(run_dir, tag='trhyb'):
    """iverilog is a compilation, not an RTL simulation: it is recorded and never charged"""
    tb_text = io.open(repo(TB_PATH), encoding='utf-8', newline='').read()
    missing = tb_missing_signals(tb_text)
    if missing:
        raise Refuse('the testbench scope declares no %s, so $dumpvars(1, tb) cannot record the '
                     'signals this round converts from; a missing dump name is a defect, not a '
                     'reason to spend a simulation' % ','.join(missing))
    root, tools_map, env = tools()
    exe, rc, out = D7A.compile_sim(tools_map, env, run_dir, rtl=repo(RTL_PATH), tb=repo(TB_PATH),
                                   tag=tag)
    return {'root': root, 'exe': exe, 'rc': rc, 'out': (out or '').strip(),
            'iverilog_sha256': sha_file(tools_map['iverilog']),
            'rtl_sha256': sha_file(repo(RTL_PATH)), 'tb_sha256': sha_file(repo(TB_PATH)),
            'charged_as_rtl_simulation': False}


def dump_name(case_id):
    """the testbench names its own dump after the group, because this iverilog build has no runtime
    $valueplusarg; the runner must look for exactly that name"""
    return 'dd1_d7c_b_tr_hyb_%s.vcd' % ('120' if case_id == 'HYB-120' else '200')


def run_vvp(case_id, exe, run_dir, account=None, run_id='', timeout=600):
    """one vvp start, charged before it runs; a failure keeps its charge"""
    root, tools_map, env = tools()
    group = group_for(case_id)
    vcd = os.path.join(run_dir, dump_name(case_id))
    log = os.path.join(run_dir, '%s.vvp.log' % case_id)
    args = [tools_map['vvp'], exe] + group['plusargs']
    row = None
    if account is not None:
        row = account.reserve({'case_id': case_id, 'kind': 'vvp', 'run_id': run_id,
                               'exe_sha256': sha_file(exe)})
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                cwd=run_dir)
    except OSError as error:
        if account is not None:
            account.settle(row, 'UNCERTAIN', '', refusal='SPAWN_FAILED: %s' % error)
        raise Refuse('vvp could not be started for %s: %s' % (case_id, error))
    try:
        out = proc.communicate()[0].decode('utf-8', 'replace')
    except Exception as error:                                  # noqa: BLE001
        proc.kill()
        if account is not None:
            account.settle(row, 'UNCERTAIN', '', refusal='TIMEOUT_OR_INTERRUPT: %s' % error)
        raise Refuse('vvp for %s did not finish cleanly: %s' % (case_id, error))
    rc = proc.returncode
    io.open(log, 'w', encoding='utf-8', newline='\n').write(
        '$ %s\nrc=%d\n%s' % (' '.join(args), rc, out))
    if rc != 0 or 'TB-ERROR' in out:
        if account is not None:
            account.settle(row, 'FAILED', rc, refusal='VVP_RC_OR_TB_ERROR')
        raise Refuse('vvp failed for %s rc=%d: %s' % (case_id, rc, out[-200:]))
    if not os.path.isfile(vcd) or os.path.getsize(vcd) == 0:
        if account is not None:
            account.settle(row, 'FAILED', rc, refusal='NO_TRACE_PRODUCED')
        raise Refuse('vvp produced no trace for %s' % case_id)
    if account is not None:
        account.settle(row, 'CONFIRMED', rc, raw_sha=sha_file(vcd), log_sha=sha_file(log))
    return {'case_id': case_id, 'rc': rc, 'vcd': vcd, 'vcd_sha256': sha_file(vcd),
            'vcd_bytes': os.path.getsize(vcd), 'log': log, 'log_sha256': sha_file(log),
            'markers': re.findall(r'^MARK .*$', out, re.M), 'launch_id':
            row['launch_id'] if row else 'NOT_CHARGED'}


def selftest():
    """synthetic fixtures: the converter is tested against traces, not against itself"""
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else extra))
    fixture = os.path.join(ROOT, 'review', 'scratch', 'tr_rtl', 'synthetic_hyb.vcd')
    if not os.path.isdir(os.path.dirname(fixture)):
        os.makedirs(os.path.dirname(fixture))
    signals = synthetic_signals(group_ns=200, safety=False)
    write_vcd(fixture, signals)
    made = convert('HYB-200', fixture)
    record('a synthetic four-state trace converts to four PWL waves',
           sorted(made['waves']) == sorted(CONVERTED), sorted(made['waves']))
    record('the synthetic frame count matches the plan', made['frame_count'] == 4,
           made['frame_count'])
    record('the F63 frame conducts 64 intervals, not 63',
           [row['conduct_ns'][0] for row in made['frames'] if row['frame'] == 'F63'] == [12800.0],
           [row['conduct_ns'] for row in made['frames'] if row['frame'] == 'F63'])
    record('the black frame has no conducting segment and is kept as a window',
           [row['frame'] for row in made['frames'] if not row['conducting_segments']] == ['B0'],
           [(row['frame'], row['conducting_segments']) for row in made['frames']])
    record('t0 is the consuming clock edge, never the leading tick',
           all(row['tick_lead_ps'] == 5000 for row in made['frames']),
           [row['tick_lead_ps'] for row in made['frames']])
    shape_text = ''.join('V%s (%s 0) vsource type=pwl wave=[%s]\n'
                         % (node, node, DECK.format_wave(made['waves'][node]))
                         for node in CONVERTED)
    shape, _parsed = DECK.verify_pwl(shape_text, made['edges'], ctx='fixture')
    record('every converted edge sits on its own 50 % point with the frozen 2 ns width',
           not shape, shape[:1])
    record('the converted wave of the black frame still carries its two rail levels only',
           sorted(set(value for _t, value in made['waves']['pam2'])) == [0.0, 1.8],
           sorted(set(value for _t, value in made['waves']['pam2'])))
    bad = dict((key, list(value)) for key, value in signals.items())
    bad['data_en'] = list(bad['data_en'])
    bad['data_en'][4] = (bad['data_en'][4][0], 'x')
    write_vcd(fixture + '.x.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.x.vcd')
    except Refuse:
        refused = True
    record('an x on the enable after the first reference edge is refused before the bench',
           refused, '')
    bad = dict((key, list(value)) for key, value in signals.items())
    bad['pam_sel'] = list(bad['pam_sel']) + [(signals['data_en'][-1][0] - 1000000, 7)]
    write_vcd(fixture + '.pam.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.pam.vcd')
    except Refuse:
        refused = True
    record('a pam move inside a frame is refused, not interpolated across the window', refused, '')
    bad = dict((key, list(value)) for key, value in signals.items())
    bad['obs_tick'] = [pair for pair in bad['obs_tick']][:-2]
    write_vcd(fixture + '.tick.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.tick.vcd')
    except Refuse:
        refused = True
    record('a frame that stops short of its 65 boundary events is refused', refused, '')
    bad = dict((key, list(value)) for key, value in signals.items())
    bad['reset_n'] = bad['reset_n'][:2]
    write_vcd(fixture + '.frame.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.frame.vcd')
    except Refuse:
        refused = True
    record('a trace with the wrong number of frames is refused', refused, '')
    bad = dict((key, list(value)) for key, value in signals.items())
    bad['cfg_hyb_pam'] = [(t, 0) for t, _v in bad['cfg_hyb_pam']]
    write_vcd(fixture + '.code.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.code.vcd')
    except Refuse:
        refused = True
    record('a loaded code that disagrees with the contract is refused', refused, '')
    bad = dict((key, list(value)) for key, value in signals.items())
    obs = list(bad['obs_tick'])
    rises = [index for index, (_t, value) in enumerate(obs) if value == 1]
    move = rises[3]                                   # the fourth accepted tick of the first frame
    obs[move] = (obs[move][0] + 1000, 1)
    obs[move + 1] = (obs[move][0] + 6000, 0)
    bad['obs_tick'] = obs
    write_vcd(fixture + '.gap.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.gap.vcd')
    except Refuse:
        refused = True
    record('an accepted tick that is not one tick period after its neighbour is refused',
           refused, '')
    bad = dict((key, list(value)) for key, value in signals.items())
    extra = [(row['latch_edge_ps'], row['cfg_version_after_latch']) for row in
              convert('HYB-200', fixture)['frames']]
    record('one accepted LATCH per frame steps cfg_version by exactly one at its latch edge',
           extra == [(row['latch_edge_ps'], index + 1) for index, row in
                     enumerate(convert('HYB-200', fixture)['frames'])], extra)
    bad = dict((key, list(value)) for key, value in signals.items())
    first = [row for row in convert('HYB-200', fixture)['frames']][0]
    bad['cfg_version'] = list(bad['cfg_version']) + [(first['end_ps'] - 20000, 9)]
    write_vcd(fixture + '.ver.vcd', bad)
    refused = False
    try:
        convert('HYB-200', fixture + '.ver.vcd')
    except Refuse:
        refused = True
    record('a second cfg_version step inside one frame is refused, not read as a harmless re-latch',
           refused, '')
    safety = synthetic_signals(group_ns=120, safety=True)
    write_vcd(fixture + '.safe.vcd', safety)
    made_s = convert('HYB-120', fixture + '.safe.vcd')
    record('the safety frame is measured by its actual fault edge, not the planned 64T',
           made_s['frames'][-1]['kind'] == 'safety'
           and made_s['frames'][-1]['conduct_ns'] == [303.0],
           [(row['kind'], row['conduct_ns']) for row in made_s['frames']][-1:])
    bad = dict((key, list(value)) for key, value in safety.items())
    late = [(t, v) for t, v in bad['fault']]
    late[1] = (late[1][0] - 2000, late[1][1])             # the fault rises 2 ns late
    bad['fault'] = late
    write_vcd(fixture + '.safe.bad.vcd', bad)
    refused = False
    try:
        convert('HYB-120', fixture + '.safe.bad.vcd')
    except Refuse:
        refused = True
    record('a safety fault that is not at t0 + 2.5T + 3 ns is refused', refused, '')
    record('the converter refuses a case it does not own', _raises(lambda: group_for('TR-120')),
           '')
    tb_text = io.open(repo(TB_PATH), encoding='utf-8', newline='').read()
    record('the testbench scope declares all twenty signals the conversion reads',
           not tb_missing_signals(tb_text), tb_missing_signals(tb_text))
    renamed = tb_text.replace('cfg_hyb_time', 'cfg_ht_port')
    record('a recorded name the converter cannot find is caught before any simulation',
           'cfg_hyb_time' in tb_missing_signals(renamed), tb_missing_signals(renamed)[:3])
    record('the compile entry refuses a testbench with a missing recorded signal',
           _raises(lambda: compile_guard(renamed)) and not _raises(lambda: compile_guard(tb_text)),
           '')
    return results


def compile_guard(tb_text):
    """the guard compile_tb applies, exercised against an edited testbench text without iverilog"""
    missing = tb_missing_signals(tb_text)
    if missing:
        raise Refuse('missing %s' % ','.join(missing))


def _raises(action):
    try:
        action()
    except Refuse:
        return True
    return False


# ---- a small VCD writer, only for the offline fixtures --------------------------------------------

def synthetic_signals(group_ns=200, safety=False):
    """a trace that satisfies the accepted protocol, built by hand so the converter can be tested

    Times are picoseconds and a signal keeps its value until it changes, exactly as a real dump
    behaves: the two 63/111 frames share one change record, which is why the converter reads the
    code in effect at the sampling edge instead of looking for a change inside the window.
    """
    tick = group_ns * 1000
    names = ('clk', 'reset_n', 'system_en', 'tick', 'blank', 'fault', 'cfg_valid', 'latch_stb',
             'pwm_start', 'data_en', 'data_en_b', 'obs_tick', 'mode', 'cfg_pure', 'cfg_hyb_time',
             'cfg_hyb_pam', 'pam_sel', 'win_state', 'cfg_version', 'proto_err')
    sig = dict((name, []) for name in names)

    def put(name, time, value):
        series = sig[name]
        if series:
            last_time, last_value = series[-1]
            if time < last_time:
                raise Refuse('fixture emits %s backwards' % name)
            if time == last_time and last_value != value:
                raise Refuse('fixture asks for two values of %s at %d ps' % (name, time))
            if last_value == value:
                return
        series.append((int(time), int(value)))

    edge = 5000
    while edge <= 900000000:
        sig['clk'].append((edge, 1))
        sig['clk'].append((edge + 5000, 0))
        edge += 10000
    rises = [pair[0] for pair in sig['clk'] if pair[1] == 1]
    next_rise = lambda after: [value for value in rises if value >= after][0]

    frames = [(0, 0, 0, 'normal'), (1, 0, 1, 'normal'), (2, 3, 2, 'normal'),
              (63, 7, 64, 'normal')]
    if safety:
        frames.append((63, 7, 64, 'safety'))
    cursor, version = 5000, 0
    for ht_value, code, intervals, kind in frames:
        down = cursor + 2000
        put('reset_n', down, 0)
        put('mode', down, 0)
        put('cfg_valid', down, 0)
        put('latch_stb', down, 0)
        put('tick', down, 0)
        put('obs_tick', down, 0)
        put('fault', down, 0)
        put('system_en', down, 0)
        put('data_en', down, 0)
        put('win_state', down, 0)
        put('blank', down, 1)
        reset_off = down + 1100000
        put('reset_n', reset_off, 1)
        mode_on = next_rise(reset_off) + 12000
        put('mode', mode_on, 1)
        put('system_en', mode_on + 20000, 1)
        load = mode_on + 40000
        put('cfg_hyb_time', load, ht_value)
        put('cfg_hyb_pam', load, code)
        put('cfg_valid', load, 1)
        latch_rise = next_rise(load) + 2000
        put('latch_stb', latch_rise, 1)
        # the accepted bench holds the request across several reference edges: the RTL takes one
        # LATCH, at the first edge that sees it, which is what the version step proves
        sample = next_rise(latch_rise)
        put('latch_stb', next_rise(sample + 20000) + 2000, 0)
        put('cfg_valid', sample + 2000, 0)
        version += 1
        put('cfg_version', sample, version)
        put('pam_sel', sample, code)
        start_rise = next_rise(sample + 12000) + 2000
        put('pwm_start', start_rise, 1)
        put('pwm_start', next_rise(start_rise + 40000), 0)
        blank_off = next_rise(start_rise + 60000) + 2000
        put('blank', blank_off, 0)
        t0 = next_rise(blank_off + 3000)
        accepted = 3 if kind == 'safety' else BOUNDARY_TICKS
        pulses = BOUNDARY_TICKS + 2 if kind == 'normal' else accepted + 6
        for index in range(pulses):
            put('tick', t0 + index * tick - 5000, 1)
            put('tick', t0 + index * tick + 1000, 0)
        for index in range(accepted):
            put('obs_tick', t0 + index * tick - 5000, 1)
            put('obs_tick', t0 + index * tick + 1000, 0)
        put('win_state', t0, 2)
        if intervals:
            put('data_en', t0, 1)
        if kind == 'normal':
            if intervals:
                put('data_en', t0 + intervals * tick, 0)
            put('win_state', t0 + BOUNDARY_TICKS * tick, 3)
            cursor = t0 + pulses * tick + 20000
        else:
            fault_on = t0 + (5 * tick) // 2 + 3000
            put('fault', fault_on, 1)
            put('data_en', fault_on, 0)
            put('win_state', fault_on, 4)
            fault_off = fault_on + 40000
            put('fault', fault_off, 0)
            put('blank', fault_off + 2000, 1)
            put('pwm_start', next_rise(fault_off + 20000), 1)
            put('pwm_start', next_rise(fault_off + 60000), 0)
            put('proto_err', next_rise(fault_off + 60000), 0x10)
            cursor = fault_off + int(TRC.SAFETY_BLACK_NS * 1000) + 20000
    level = 1
    for time, value in list(sig['data_en']):
        put('data_en_b', time, level)
        level = 1 - level
    put('data_en_b', sig['clk'][-1][0], level)
    return sig


def write_vcd(path, signals):
    names = list(signals)
    ids = {}
    for index, name in enumerate(names):
        ids[name] = chr(ord('!') + index)
    width = {'mode': 2, 'cfg_pure': 8, 'cfg_hyb_time': 6, 'cfg_hyb_pam': 3, 'pam_sel': 3,
             'win_state': 3, 'cfg_version': 8, 'proto_err': 8}
    lines = ['$date now $end', '$version iverilog-fixture $end', '$timescale 1ps $end',
             '$scope module %s $end' % SCOPE]
    for name in names:
        size = width.get(name, 1)
        lines.append('$var wire %d %s %s $end' % (size, ids[name], name))
    lines += ['$upscope $end', '$enddefinitions $end']
    stream = []
    for name in names:
        size = width.get(name, 1)
        for t, value in signals[name]:
            stream.append((int(t), name, size, value))
    stream.sort(key=lambda item: (item[0], item[1]))
    last = None
    for t, name, size, value in stream:
        if t != last:
            lines.append('#%d' % t)
            last = t
        if size == 1:
            lines.append('%s%s' % (value if isinstance(value, str) else int(value), ids[name]))
        else:
            text = value if isinstance(value, str) else format(int(value), '0%db' % size)
            lines.append('b%s %s' % (text, ids[name]))
    io.open(path, 'wb').write(('\n'.join(lines) + '\n').encode('utf-8'))
    return path


def main(argv):
    mode = argv[0] if argv else '--selftest'
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-66s %s %s' % (name, 'PASS' if ok else 'FAIL', str(extra)[:150]))
        print('TR_TRACE_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--compile':
        run_dir = argv[1] if len(argv) > 1 else os.path.join(ROOT, 'review', 'scratch', 'tr_rtl')
        if not os.path.isdir(run_dir):
            os.makedirs(run_dir)
        facts = compile_tb(run_dir)
        print(json.dumps(facts, indent=1, sort_keys=True))
        return 0 if facts['rc'] == 0 else 1
    if mode == '--convert':
        case_id, vcd = argv[1], argv[2]
        made = convert(case_id, vcd)
        out = os.path.join(ROOT, 'review', 'scratch', 'tr_rtl', '%s_conversion.json' % case_id)
        io.open(out, 'wb').write((json.dumps(made, indent=1, sort_keys=True, default=str) + '\n')
                                 .encode('utf-8'))
        print('TR_CONVERT %s frames=%d stop_ns=%.3f vcd=%s'
              % (case_id, made['frame_count'], made['stop_ns'], made['vcd_sha256'][:12]))
        return 0
    print('usage: --selftest | --compile [dir] | --convert <case> <vcd>')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
