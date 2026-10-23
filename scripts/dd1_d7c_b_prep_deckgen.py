#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_deckgen.py -- render the fifteen decks as text, from the contract and the schedule.

DATA-7C-B-PREP section 5. This writes files and nothing else: it starts no simulator, reads no model
card and touches no published artefact. The decks are the reviewable object of this round, so every
timing number in them comes from `tests/dd1_d7c_b_prep/schedule.csv` and `pwl.csv`, which in turn come
from the contract and the delivered R2 plan source. Times are written as absolute nanoseconds, never
as a bare `TON` expression: the R2 deck defined TON as 4 us while the R2 table used TON as 1000 ns, and
one symbol with two values is exactly what a reviewer cannot check (recorded as difference D2).

Each deck carries, in its own text: the supplies, the DATA_EN form, the three PAM bits, the initial off
lead and the offset actually applied, the finite rise and fall, the code-change instants, the PWL
envelope, the flat integration window, the 50% enable edges, the tail and last-100 ns leakage window,
the stop, the maxstep, the paired source case, the probe instance with its terminal order and the sign
rule, and the launch plan for that case. Hierarchical saves and the pwl spelling on decoder inputs stay
`NOT_VERIFIED`.

    python scripts/dd1_d7c_b_prep_deckgen.py --emit
    python scripts/dd1_d7c_b_prep_deckgen.py --check     # delivered bytes must be a fixed point
"""

from __future__ import absolute_import, division, print_function

import argparse
import io
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import dd1_d7c_b_prep_contract as CONTRACT     # noqa: E402
import dd1_d7c_b_prep_schedule as SCHEDULE     # noqa: E402

DECK_DIR = 'spectre/dd1_d7c_b_prep'
# the iprobe statement itself, matched only on non-comment lines: a comment that quotes the correct
# order must not be able to vouch for a deck whose statement line was turned around
PROBE_STATEMENT = re.compile(r'^Ip_branch\s+\(([^)]*)\)\s+iprobe\b')
PROBE_TERMINALS = CONTRACT.R2PLAN.PROBE_TERMINALS
INCLUDES = ('dd1_d6_inv18.scs', 'dd1_d6_bias_core.scs', 'dd1_d7c_a_gates.scs',
            'dd1_d7c_a_pam_dec.scs', 'dd1_d7c_a_sink_unit.scs', 'dd1_d7c_a_pam_top.scs')
NET_DECLARATIONS = ['data_en', 'pam0', 'pam1', 'pam2', 'irefbus', 'iref_in', 'vcas', 'data_out',
                    'vdd18', 'vss', 'clamp_node']


def audit_text(text, row):
    """the rules one delivered deck has to satisfy; the negative cases call this same function

    Kept separate from `check()` so a counterexample exercises the code that guards the real files,
    not a copy of the rules written for the counterexample alone.
    """
    name = '%s.scs' % row['case_id']
    problems = []
    if '\r' in text:
        problems.append('%s carries CR bytes' % name)
    statements = [line.strip() for line in text.split('\n') if not line.strip().startswith('//')]
    probes = [line for line in statements if PROBE_STATEMENT.match(line)]
    if len(probes) != 1:
        problems.append('%s declares %d iprobe statements, one case needs exactly one'
                        % (name, len(probes)))
    elif PROBE_STATEMENT.match(probes[0]).group(1).split()[0:2] != list(PROBE_TERMINALS):
        problems.append('%s writes the probe as "%s", which is not the contracted terminal order '
                        'Ip_branch (%s %s) iprobe' % ((name, probes[0]) + PROBE_TERMINALS))
    active = [line for line in statements if line.startswith('tran ') or ' dev=' in line]
    if len(active) != 1:
        problems.append('%s declares %d active analysis lines, one case needs exactly one: %s'
                        % (name, len(active), ' | '.join(active[:2])))
    pulsed = [line for line in statements if 'type=pwl' in line]
    if row['class'] == 'dc_sweep':
        if pulsed:
            problems.append('%s is a DC case carrying a pulsed enable: %s' % (name, pulsed[0][:60]))
        if 'Vdata_en (data_en 0) vsource dc=%s' % row['data_en_level_V'] not in statements:
            problems.append('%s does not drive DATA_EN statically at its declared level' % name)
        if not any(' param=dc ' in line for line in active):
            problems.append('%s has no dc analysis statement' % name)
    else:
        if not pulsed:
            problems.append('%s is a transient case with no finite-slope enable statement' % name)
        for field in ('stop_ns', 'maxstep_ns'):
            if row[field] not in text:
                problems.append('%s does not state its own %s' % (name, field))
        if row['analysis_line'].strip() not in statements:
            problems.append('%s does not run the analysis line its row declares' % name)
    if 'I_sink = Ip_branch' not in text or 'no abs()' not in text:
        problems.append('%s does not state the sign rule beside the probe' % name)
    if 'include "${QODER_PDK_LIB}" section=tt' not in statements:
        problems.append('%s does not keep the PDK path configurable' % name)
    if 'Vss (vss 0) vsource dc=0' not in statements:
        problems.append('%s has no explicit ground return for vss, which is how every NMOS path '
                        'disappears' % name)
    if 'schedule.csv: NOT_RUN' not in text:
        problems.append('%s does not carry the NOT_RUN result state of its own row' % name)
    return problems


def _n(value):
    """a nanosecond column, written with its own unit so no symbol can mean two times"""
    return '%sn' % value


def _rows(directory):
    rows, windows, pwl, problems = SCHEDULE.read_delivered(directory)
    if problems:
        raise SystemExit('D7C_B_DECKGEN_REFUSED the schedule it must render is not readable: %s'
                         % problems[0])
    return rows, windows, pwl


def _series(pwl, case_id, node):
    points = [item for item in pwl if item['case_id'] == case_id and item['node'] == node]
    points.sort(key=lambda item: float(item['t_ns']))
    return points


def _pwl_statement(points):
    times = ' '.join(_n(item['t_ns']) for item in points)
    values = ' '.join(item['value_V'] for item in points)
    return 'time={%s} value={%s}' % (times, values)


def _envelope(points):
    return '%s ns .. %s ns (%d points)' % (points[0]['t_ns'], points[-1]['t_ns'], len(points))


def render(row, windows_for_case, pwl, contract_data):
    case_id = row['case_id']
    clamp = contract_data['rules']['clamp']
    code = row['pam_code']
    dc = row['class'] == 'dc_sweep'
    nominal = contract_data['nominal_current_A_by_code'].get(code) if dc else None
    lines = []
    add = lines.append
    add('// %s.scs -- DATA-7C-B-PREP deck for case %s. TEXT ONLY, NEVER RUN.' % (case_id, case_id))
    add('//')
    add('// Generated by scripts/dd1_d7c_b_prep_deckgen.py from tests/dd1_d7c_b_prep/contract.json and')
    add('// tests/dd1_d7c_b_prep/schedule.csv. Do not edit this file by hand: change the source and')
    add('// regenerate, otherwise the schedule and the deck disagree, which is the defect this round')
    add('// exists to remove. Contract state: %s (not USER_APPROVED).'
        % contract_data['contract_state'])
    add('// Authorisation: NEW_SPECTRE_LAUNCH_LIMIT=0, NATIVE_PREFLIGHT_AUTHORISED=NO,')
    add('// NEXT_NATIVE_STAGE_AUTHORISED=NO. Nothing in this file has been run, and running it is not')
    add('// authorised by this round. NATIVE_NETLIST_SYNTAX=NOT_VERIFIED, so the pwl spelling below and')
    add('// the hierarchical saves are text a reviewer reads, not a proven feature of this build.')
    add('//')
    add('// ---- this case, in numbers ' + '-' * 55)
    add('// class                : %s' % row['class'])
    add('// pam_sel               : %s  (bit0=pam0 weight 1, bit1=pam1 weight 2, bit2=pam2 weight 4)'
        % code)
    add('// DATA_EN form          : %s at %s V' % (row['data_en_form'], row['data_en_level_V']))
    supplies = contract_data['rules']['supplies']
    add('// supplies              : vdd18=%s V, vcas=%s V, vss=explicit 0 V source, Iref=%s A '
        '(the deck writes it as %s)'
        % (_fmt(supplies['vdd18_V']), _fmt(supplies['vcas_V']),
           _sci_full(supplies['iref_A']), _sci(supplies['iref_A'])))
    add('// output clamp          : %s V (POC condition, not VLED, not VSCAN, not SOA)'
        % _fmt(clamp['main_eval_V']))
    if dc:
        add('// clamp sweep         : %s' % row['clamp_sweep_V'])
        add('// analysis            : %s' % row['analysis_line'])
        add('// nominal for this code: %s uA, identity ESTIMATED_MIRROR_RATIO_ONLY'
            % _fmt(nominal * 1e6))
    else:
        add('// initial off lead    : %s ns, offset applied to every instant of this case: %s ns'
            % (row['lead_off_ns'], row['offset_applied_ns']))
        add('// platform start/stop : %s / %s' % (row['platform_start_ns'], row['platform_stop_ns']))
        add('// 50%% enable edges    : rise %s / fall %s' % (row['enable_rise_50_ns'],
                                                            row['enable_fall_50_ns']))
        add('// integration window  : %s -> %s (the flat part, inset by the ramp time)'
            % (row['window_start_ns'], row['window_stop_ns']))
        add('// off window          : %s' % row['off_window_ns'])
        add('// tail window         : %s -> %s' % (row['tail_start_ns'], row['tail_stop_ns']))
        add('// leakage sub-window  : last %g ns from %s ns (criterion: max(abs(I_sink)) <= %s A, '
            'the deck spells it %s)'
            % (100.0, row['leak_last100_start_ns'],
               _sci_full(contract_data['rules']['shutoff_leakage']['limit_A']),
               _sci(contract_data['rules']['shutoff_leakage']['limit_A'])))
        add('// code change rule    : %s' % row['code_change_rule'])
        add('// settled before edge : %s ns' % row['settled_before_enable_ns'])
        add('// stop / maxstep      : %s ns / %s ns' % (row['stop_ns'], row['maxstep_ns']))
        add('// analysis            : %s' % row['analysis_line'])
        if row['paired_case']:
            add('// paired with         : %s, identical stimulus and windows, only maxstep differs'
                % row['paired_case'])
        add('// launch plan         : %s DUT process + %s preflight process'
            % (row['launch_processes_dut'], row['launch_processes_preflight']))
    add('// windows declared for this case: %s'
        % ', '.join(sorted(w['window_id'] for w in windows_for_case)))
    add('//')
    add('// ---- probe and sign, fixed before any run --------------------------------------------------')
    add('// Ip_branch (clamp_node data_out) iprobe, so a positive reading IS the selected branches')
    add('// sinking current out of data_out: I_sink = Ip_branch, with no negation and no abs(). The')
    add('// physical positive path is clamp_node -> data_out -> the conducting branch(es) -> vss, which')
    add('// is the same terminal order the accepted DATA-7B bench uses. A shutoff tail keeps its own')
    add('// sign: Q, Qpos and the magnitude of Qneg are reported separately and never cancel.')
    add('simulator lang=spectre insensitive=yes')
    add('')
    add('// PDK path and model section come from the environment; no model card is copied into this')
    add('// repository and none was read this round.')
    add('include "${QODER_PDK_LIB}" section=tt')
    add('')
    for name in INCLUDES:
        add('include "${QODER_NETLIST_DIR}/%s"' % name)
    add('')
    add('// ---- the device under test: one output, eight selectable branches (delivered, unmodified)')
    add('Xdut (data_en pam0 pam1 pam2 iref_in vcas data_out vdd18 vss) dd1_d7c_a_pam_1ch')
    add('')
    add('// ---- testbench side: reference and supplies, every node referenced to a real 0 V')
    add('Iref_in (irefbus iref_in) isource dc=%s' % _sci(contract_data['rules']['supplies']['iref_A']))
    add('Viref (irefbus 0) vsource dc=0')
    add('Vdd18 (vdd18 0) vsource dc=%s' % _fmt(contract_data['rules']['supplies']['vdd18_V']))
    add('Vss (vss 0) vsource dc=0')
    add('Vcas (vcas 0) vsource dc=%s' % _fmt(contract_data['rules']['supplies']['vcas_V']))
    if dc:
        add('// The swept node. The %s V evaluation point has to be one of these points, and it is:'
            % _fmt(clamp['main_eval_V']))
        add('// %s is an exact member of the grid.'
            % _fmt(clamp['main_eval_V']))
        add('Vclamp (clamp_node 0) vsource dc=%s' % _fmt(clamp['main_eval_V']))
        add('// DATA_EN is a static level here: an absolute-current point measured with the branches')
        add('// off would be a point about nothing.')
        add('Vdata_en (data_en 0) vsource dc=%s' % row['data_en_level_V'])
        bits = {'pam0': float(int(code[0])), 'pam1': float(int(code[1])), 'pam2': float(int(code[2]))}
        for node in ('pam0', 'pam1', 'pam2'):
            add('V%s (%s 0) vsource dc=%s' % (node.upper(), node, _fmt(bits[node])))
    else:
        add('Vclamp (clamp_node 0) vsource dc=%s' % _fmt(clamp['main_eval_V']))
        enable = _series(pwl, row['case_id'], 'data_en')
        add('// Finite-slope enable written as absolute times, low at t=0 so the first rise is a real')
        add('// edge. Envelope %s. Ramp is symmetric about its 50%% point, so the flat part between'
            % _envelope(enable))
        add('// the ramps is exactly the integration window declared above.')
        add('Vdata_en (data_en 0) vsource type=pwl %s' % _pwl_statement(enable))
        for node in ('pam0', 'pam1', 'pam2'):
            series = _series(pwl, row['case_id'], node)
            if len(series) == 1:
                add('V%s (%s 0) vsource dc=%s   // static from t=0, settled before the first edge'
                    % (node.upper(), node, series[0]['value_V']))
            else:
                add('// %s changes only inside an off window: %s' % (node, _envelope(series)))
                add('V%s (%s 0) vsource type=pwl %s'
                    % (node.upper(), node, _pwl_statement(series)))
        add('// A second analysis form is deliberately absent: this deck declares one tran line, so a')
        add('// reviewer can tell which stop and maxstep the case was planned with.')
    add('')
    add('// ---- observation points. Hierarchical saves are NOT_VERIFIED on this build; if the native')
    add('// stage refuses them the fallback is to lift the node in a draft copy of the unit subckt, never')
    add('// to edit the delivered candidate.')
    add('Ip_branch (clamp_node data_out) iprobe')
    add('save vdd18 vss iref_in vcas data_out clamp_node irefbus data_en pam0 pam1 pam2')
    add('save Xdut.en0 Xdut.en1 Xdut.en2 Xdut.en3 Xdut.en4 Xdut.en5 Xdut.en6 Xdut.en7')
    add('save Xdut.enb0 Xdut.enb1 Xdut.enb2 Xdut.enb3 Xdut.enb4 Xdut.enb5 Xdut.enb6 Xdut.enb7')
    add('save Xdut.Xu0.vbias_ch Xdut.Xu1.vbias_ch Xdut.Xu2.vbias_ch Xdut.Xu3.vbias_ch')
    add('save Xdut.Xu4.vbias_ch Xdut.Xu5.vbias_ch Xdut.Xu6.vbias_ch Xdut.Xu7.vbias_ch')
    add('save Ip_branch Ip_branch:current')
    add('')
    if dc:
        add(row['analysis_line'])
    else:
        add(row['analysis_line'])
    add('')
    add('// result column for this case in tests/dd1_d7c_b_prep/schedule.csv: %s' % row['result'])
    add('')
    return '\n'.join(lines)


def _fmt(value):
    return '%g' % float(value)


def _sci_full(value):
    """an SI value written in amperes with its exponent, so the deck and the contract agree"""
    return '%g' % float(value)


def _sci(value):
    """an SI value written the way a deck spells it: 1.875e-6 A becomes 1.875u"""
    value = float(value)
    for scale, suffix in ((1e-15, 'f'), (1e-12, 'p'), (1e-9, 'n'), (1e-6, 'u'), (1e-3, 'm')):
        if abs(value) >= scale and abs(value) < scale * 1000:
            return ('%g' % (value / scale)) + suffix
    return '%g' % value


def render_all(directory=ROOT):
    rows, windows, pwl = _rows(directory)
    contract_data = CONTRACT.load(os.path.join(directory,
                                               CONTRACT.CONTRACT_PATH.replace('/', os.sep)))
    outputs = {}
    for row in rows:
        name = '%s.scs' % row['case_id']
        case_windows = [w for w in windows if w['case_id'] == row['case_id']]
        outputs[name] = render(row, case_windows, pwl, contract_data)
    return outputs


def emit(directory=ROOT):
    outputs = render_all(directory)
    target = os.path.join(directory, DECK_DIR.replace('/', os.sep))
    if not os.path.isdir(target):
        os.makedirs(target)
    written = []
    for name, text in sorted(outputs.items()):
        path = os.path.join(target, name)
        with io.open(path, 'wb') as handle:
            handle.write((text.rstrip('\n') + '\n').encode('utf-8'))
        written.append(path)
    return written


def check(directory=ROOT):
    """the delivered decks must be exactly what the sources render: a fixed point, in both directions"""
    problems = []
    outputs = render_all(directory)
    target = os.path.join(directory, DECK_DIR.replace('/', os.sep))
    present = sorted(name for name in os.listdir(target)) if os.path.isdir(target) else []
    expected = sorted(outputs)
    if present != expected:
        problems.append('the deck directory carries %s, the schedule renders %s'
                        % (','.join(present), ','.join(expected)))
    rows, _windows, _pwl = _rows(directory)
    by_case = dict((row['case_id'], row) for row in rows)
    for name, text in sorted(outputs.items()):
        path = os.path.join(target, name)
        if not os.path.isfile(path):
            problems.append('%s is missing' % name)
            continue
        with io.open(path, encoding='utf-8', newline='') as handle:
            delivered = handle.read()
        if delivered.rstrip('\n') + '\n' != text.rstrip('\n') + '\n':
            problems.append('%s is not the text the contract and schedule produce' % name)
        case_id = name.split('.')[0]
        problems.extend(audit_text(delivered, by_case[case_id]))
    stray = [entry for entry in os.listdir(target)
             if entry.endswith(('.log', '.raw', '.psf', '.txt'))] if os.path.isdir(target) else []
    if stray:
        problems.append('run artefacts sit next to the decks, which this round cannot have produced: %s'
                        % ','.join(stray))
    return problems, len(outputs)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--emit', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--root', default=ROOT)
    parser.add_argument('--to', default='')
    arguments = parser.parse_args(argv)
    directory = os.path.abspath(arguments.root)
    if arguments.to:
        scratch = os.path.abspath(arguments.to)
        if os.path.isdir(scratch):
            shutil.rmtree(scratch)
        os.makedirs(os.path.join(scratch, DECK_DIR.replace('/', os.sep)))
        for name in (SCHEDULE.SCHEDULE_TABLE, SCHEDULE.WINDOWS_TABLE, SCHEDULE.PWL_TABLE,
                     CONTRACT.CONTRACT_PATH):
            source = os.path.join(directory, name.replace('/', os.sep))
            destination = os.path.join(scratch, name.replace('/', os.sep))
            if not os.path.isdir(os.path.dirname(destination)):
                os.makedirs(os.path.dirname(destination))
            shutil.copyfile(source, destination)
        written = emit(scratch)
        problems, count = check(scratch)
        shutil.rmtree(scratch, ignore_errors=True)
        print('D7C_B_DECKGEN_REGENERATED %d decks in a scratch tree, comparison problems=%d'
              % (count, len(problems)))
        for line in problems[:8]:
            print('  PROBLEM ' + line)
        return 1 if problems else 0
    if arguments.emit:
        written = emit(directory)
        print('D7C_B_DECKGEN_EMITTED %d decks into %s' % (len(written),
                                                          DECK_DIR))
        return 0
    if arguments.check:
        problems, count = check(directory)
        print('D7C_B_DECKGEN_CHECK: %s (%d decks, problems=%d)'
              % ('PASS' if not problems else 'FAIL', count, len(problems)))
        for line in problems[:10]:
            print('  PROBLEM ' + line)
        return 1 if problems else 0
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
