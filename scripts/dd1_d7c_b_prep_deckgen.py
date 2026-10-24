#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_deckgen.py -- the fifteen decks, rendered from the contract and the schedule only.

Nothing here is run. The decks are text a reviewer can read, and the audit below is the part that has
to be strict: R1 rewrote it because the PREP audit matched substrings, so a deck could satisfy a rule
by *quoting* the right text in a comment, and because the review pointed out that the project has
already proven the spellings these decks should use:

    simopt options temp=27                      scripts/dd1_d7b_run.py:288
    <name> tran stop=<t> maxstep=<h>            scripts/dd1_d7b_run.py:288
    <name> dc   dev=Vclamp param=dc ...        spectre/current_probe_syntax.scs:35
    Vnode (node 0) vsource type=pwl wave=[t v ...]   scripts/dd1_d7b_run.py:239

The audit parses the effective statements: it reads the PWL wave list, interpolates the 50 % crossings
out of them, checks the PAM levels against bit-weight arithmetic, and requires the leakage sub-window
to be a stretch where the deck's own DATA_EN is at 0 V. A comment can no longer vouch for anything.

Offline only: no simulator, no `spectre -h`, no native syntax claim. NATIVE_NETLIST_SYNTAX stays
NOT_VERIFIED, including the hierarchical saves below.
"""

from __future__ import absolute_import, print_function

import argparse
import io
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import dd1_d7c_b_prep_contract as CONTRACT     # noqa: E402
import dd1_d7c_b_prep_schedule as SCHEDULE     # noqa: E402

DECK_DIR = 'spectre/dd1_d7c_b_prep'
# the iprobe statement, matched only on non-comment lines
PROBE_STATEMENT = re.compile(r'^Ip_branch\s+\(([^)]*)\)\s+iprobe\b')
PROBE_TERMINALS = CONTRACT.R2PLAN.PROBE_TERMINALS
# one named analysis statement: `<instance> dc|tran <arguments>`
ANALYSIS_STATEMENT = re.compile(r'^(\w+)\s+(dc|tran)\s+(.*)$')
PWL_STATEMENT = re.compile(r'^(\w+)\s+\((\w+)\s+(\w+)\)\s+vsource\s+type=pwl\s+'
                           r'wave=\[(.*)\]\s*$')
DC_SOURCE = re.compile(r'^(\w+)\s+\((\w+)\s+(\w+)\)\s+vsource\s+dc=(\S+)$')
TEMP_STATEMENT = re.compile(r'^simopt\s+options\s+temp=(-?\d+)\s*$')
INCLUDES = ('dd1_d6_inv18.scs', 'dd1_d6_bias_core.scs', 'dd1_d7c_a_gates.scs',
            'dd1_d7c_a_pam_dec.scs', 'dd1_d7c_a_sink_unit.scs', 'dd1_d7c_a_pam_top.scs')
NET_DECLARATIONS = ['data_en', 'pam0', 'pam1', 'pam2', 'irefbus', 'iref_in', 'vcas', 'data_out',
                    'vdd18', 'vss', 'clamp_node']


def wave_tokens(body):
    """`[0 0 1000n 0 1100n 1.8 ...]` -> [(ns, V)], refusing a time that is not whole nanoseconds"""
    tokens = body.split()
    if len(tokens) % 2:
        raise ValueError('the wave list has %d tokens, which is not a list of (time, value) pairs'
                         % len(tokens))
    pairs = []
    for index in range(0, len(tokens), 2):
        raw = tokens[index]
        if not raw.endswith('n'):
            raise ValueError('PWL time %r has no ns suffix' % raw)
        digits = raw[:-1]
        if not re.match(r'^\d+$', digits):
            raise ValueError('PWL time %r is not a whole number of nanoseconds' % raw)
        pairs.append((float(digits), float(tokens[index + 1])))
    return pairs


def _statements(text):
    """the executable lines, with any trailing `// ...` comment removed

    The audit reads statements, so a deck may annotate a source with a comment without that comment
    becoming part of the match; the reverse reading is the one that let a PREP comment vouch for a
    probe order.
    """
    out = []
    for line in text.split('\n'):
        body = line.split('//')[0].strip()
        if body:
            out.append(body)
    return out


def _find(text, pattern):
    return [match for line in _statements(text) for match in [pattern.match(line)] if match]


def audit_text(text, row, contract_data=None):
    """the rules one delivered deck has to satisfy; the negative cases call this same function"""
    name = '%s.scs' % row['case_id']
    problems = []
    if contract_data is None:
        contract_data = CONTRACT.contract()
    units = contract_data['units']
    if '\r' in text:
        problems.append('%s carries CR bytes' % name)
    statements = _statements(text)
    # one probe, in the contracted direction, stated on a statement line and not in a comment
    probes = [line for line in statements if PROBE_STATEMENT.match(line)]
    if len(probes) != 1:
        problems.append('%s declares %d iprobe statements, one case needs exactly one'
                        % (name, len(probes)))
    else:
        terminals = PROBE_STATEMENT.match(probes[0]).group(1).split()[0:2]
        if terminals != list(PROBE_TERMINALS):
            problems.append('%s writes the probe as "%s", which is not the contracted terminal order '
                            'Ip_branch (%s %s) iprobe' % ((name, probes[0]) + PROBE_TERMINALS))
    # the temperature has to be a statement, because a contract line is not a deck condition
    temps = _find(text, TEMP_STATEMENT)
    if len(temps) != 1:
        problems.append('%s declares %d `simopt options temp=` statements; the contract says %s C and '
                        'the deck has to say it too'
                        % (name, len(temps), contract_data['rules']['process_corner']['temperature_C']))
    elif int(temps[0].group(1)) != contract_data['rules']['process_corner']['temperature_C']:
        problems.append('%s sets temp=%s, the contract declares %s'
                        % (name, temps[0].group(1),
                           contract_data['rules']['process_corner']['temperature_C']))
    # exactly one analysis statement, named, of the right type, carrying its own numbers
    analyses = [line for line in statements if ANALYSIS_STATEMENT.match(line)]
    if len(analyses) != 1:
        problems.append('%s declares %d active analysis lines, one case needs exactly one: %s'
                        % (name, len(analyses), ' | '.join(analyses[:2])))
    else:
        instance, kind, arguments = ANALYSIS_STATEMENT.match(analyses[0]).groups()
        if instance != row['analysis_name']:
            problems.append('%s names its analysis %s, the schedule row says %s'
                            % (name, instance, row['analysis_name']))
        wanted = 'dc' if row['class'] == 'dc_sweep' else 'tran'
        if kind != wanted:
            problems.append('%s runs a %s analysis, its class %s needs %s'
                            % (name, kind, row['class'], wanted))
        if row['class'] == 'dc_sweep':
            for token in ('dev=Vclamp', 'param=dc', 'start=0.600', 'stop=1.500', 'step=0.050'):
                if token not in arguments:
                    problems.append('%s sweep is missing %s (it reads %s)' % (name, token, arguments))
        else:
            for field in ('stop', 'maxstep'):
                value = row['%s_ns' % field] if field == 'stop' else row['maxstep_ns']
                if '%s=%sn' % (field, SCHEDULE._g(value)) not in arguments:
                    problems.append('%s analysis does not state its own %s=%s ns (it reads %s)'
                                    % (name, field, value, arguments))
    # the sources: explicit ground return, configurable PDK path, the sign rule beside the probe
    if 'Vss (vss 0) vsource dc=0' not in statements:
        problems.append('%s has no explicit ground return for vss, which is how every NMOS path '
                        'disappears' % name)
    if 'include "${QODER_PDK_LIB}" section=tt' not in statements:
        problems.append('%s does not keep the PDK path configurable' % name)
    if 'I_sink = Ip_branch' not in text or 'no abs()' not in text:
        problems.append('%s does not state the sign rule beside the probe' % name)
    if 'schedule.csv: NOT_RUN' not in text:
        problems.append('%s does not carry the NOT_RUN result state of its own row' % name)
    problems.extend(_audit_levels_and_windows(name, text, row, units))
    return problems


def _audit_levels_and_windows(name, text, row, units):
    """the electrical conditions read back off the deck's own statements"""
    problems = []
    dc = row['class'] == 'dc_sweep'
    pwl_lines = {}
    dc_lines = {}
    for match in _find(text, PWL_STATEMENT):
        pwl_lines[match.group(2)] = match.group(4)
    for match in _find(text, DC_SOURCE):
        dc_lines[match.group(2)] = float(match.group(4))
    if dc:
        if 'data_en' in pwl_lines:
            problems.append('%s is a DC case carrying a pulsed enable' % name)
        rail = units['logic_high_V']
        if dc_lines.get('data_en') != rail:
            problems.append('%s drives DATA_EN with %s V, the row declares %s V statically'
                            % (name, dc_lines.get('data_en'), row['data_en_level_V']))
        for bit, value in sorted(SCHEDULE.code_bits(row['pam_code'], rail).items()):
            if bit not in dc_lines:
                problems.append('%s has no dc statement for %s' % (name, bit))
            elif abs(dc_lines[bit] - value) > 1e-12:
                problems.append('%s sets %s = %s V; code %s means %s V by bit weight (pam0=1, '
                                'pam1=2, pam2=4 of the %s V domain)'
                                % (name, bit, _fmt(dc_lines[bit]), row['pam_code'], _fmt(value),
                                   _fmt(rail)))
        return problems
    if 'data_en' not in pwl_lines:
        problems.append('%s is a transient case with no finite-slope enable statement' % name)
        return problems
    enable = SCHEDULE.value_at(wave_tokens(pwl_lines['data_en']), 0.0)
    if enable != 0.0:
        problems.append('%s leaves DATA_EN at %s V at t=0, so the first rise is not a real edge'
                        % (name, _fmt(enable)))
    pairs = wave_tokens(pwl_lines['data_en'])
    rail = units['logic_high_V']
    for start, stop in zip([float(v) for v in row['platform_start_ns'].split(';')],
                           [float(v) for v in row['platform_stop_ns'].split(';')]):
        half = float(row['edge_ns'])
        for declared in (start, stop):
            found = SCHEDULE.cross_at(pairs, rail / 2.0, declared, half + 1e-6)
            if found is None or abs(found - declared) > 1e-6:
                problems.append('%s: its own DATA_EN wave crosses half of the %s V rail at %s near '
                                '%s ns, while the row declares that edge at %s ns'
                                % (name, _fmt(rail), _fmt(found) if found is not None else 'nothing',
                                   _fmt(declared), _fmt(declared)))
    for bit in ('pam0', 'pam1', 'pam2'):
        if bit not in pwl_lines and bit in dc_lines:
            pairs_bit = [(0.0, dc_lines[bit])]
        elif bit in pwl_lines:
            pairs_bit = wave_tokens(pwl_lines[bit])
        else:
            problems.append('%s never drives %s' % (name, bit))
            continue
        codes = ([row['pam_code']] if row['pam_code'] != '000..111'
                 else sorted(CONTRACT.contract()['nominal_current_A_by_code']))
        if ',' in row['pam_code']:
            codes = row['pam_code'].split(',')
        starts = [float(v) for v in row['platform_start_ns'].split(';')]
        if len(codes) != len(starts):
            problems.append('%s names %d codes for %d platforms' % (name, len(codes), len(starts)))
            continue
        for index, code in enumerate(codes):
            value = SCHEDULE.value_at(pairs_bit, starts[index] + 1.0)
            wanted = SCHEDULE.code_bits(code, rail)[bit]
            if value is None or abs(value - wanted) > 1e-12:
                problems.append('%s drives %s = %s during platform %d (code %s), bit weight says %s V'
                                % (name, bit, _fmt(value), index, code, _fmt(wanted)))
    # the leakage sub-window has to be a stretch where this deck's enable is at 0 V
    for part in row['leak_window_ns'].split(';'):
        low, high = [float(v) for v in part.split('-')]
        for a, b in zip(pairs, pairs[1:]):
            if max(low, a[0]) < min(high, b[0]) and (a[1] or b[1]):
                if not (a[1] == 0.0 and b[1] == 0.0):
                    problems.append('%s measures leakage over %s-%s ns, but its own DATA_EN wave is '
                                    'ramping there (%s V at %s ns -> %s V at %s ns)'
                                    % (name, _fmt(low), _fmt(high), _fmt(a[1]), _fmt(a[0]), _fmt(b[1]),
                                       _fmt(b[0])))
    return problems


def _fmt(value):
    return '%g' % float(value)


def _sci_full(value):
    """an SI value written in amperes with its exponent, so the deck and the contract agree"""
    return '%g' % float(value)


def _sci(value):
    """an SI value written the way a deck spells it: 1.875e-6 A becomes 1.875u"""
    value = float(value)
    for scale, suffix in ((1e-15, 'f'), (1e-12, 'p'), (1e-9, 'n'), (1e-6, 'u'), (1e-3, 'm')):
        if scale <= abs(value) < scale * 1000:
            return ('%g' % (value / scale)) + suffix
    return '%g' % value


def _series(pwl, case_id, node):
    points = [item for item in pwl if item['case_id'] == case_id and item['node'] == node]
    points.sort(key=lambda item: float(item['t_ns']))
    return points


def _pwl_statement(points):
    """the proven project spelling: one flat bracket list, whole-nanosecond `n` times"""
    tokens = []
    for item in points:
        nanoseconds = float(item['t_ns'])
        if abs(nanoseconds - round(nanoseconds)) > 1e-9:
            raise SystemExit('D7C_B_DECKGEN_REFUSED %s ns is not a whole number of nanoseconds, and '
                             'this build reads a PWL time in ns' % item['t_ns'])
        tokens.append('%dn' % int(round(nanoseconds)))
        tokens.append(SCHEDULE._g(item['value_V']))
    return 'wave=[%s]' % ' '.join(tokens)


def _envelope(pairs):
    return '%s ns .. %s ns (%d points)' % (pairs[0]['t_ns'], pairs[-1]['t_ns'], len(pairs))


def render(row, windows_for_case, pwl, contract_data):
    case_id = row['case_id']
    units = contract_data['units']
    clamp = contract_data['rules']['clamp']
    code = row['pam_code']
    dc = row['class'] == 'dc_sweep'
    nominal = contract_data['nominal_current_A_by_code'].get(code) if dc else None
    lines = []
    add = lines.append
    add('// %s.scs -- DATA-7C-B-PREP-R1 deck for case %s. TEXT ONLY, NEVER RUN.' % (case_id, case_id))
    add('//')
    add('// Generated by scripts/dd1_d7c_b_prep_deckgen.py from tests/dd1_d7c_b_prep/contract.json and')
    add('// tests/dd1_d7c_b_prep/schedule.csv. Do not edit this file by hand: change the source and')
    add('// regenerate, otherwise the schedule and the deck disagree, which is the defect this round')
    add('// exists to remove. Contract state: %s (not USER_APPROVED).'
        % contract_data['contract_state'])
    add('// Authorisation: NEW_SPECTRE_LAUNCH_LIMIT=0, NATIVE_PREFLIGHT_AUTHORISED=NO,')
    add('// NEXT_NATIVE_STAGE_AUTHORISED=NO. Nothing in this file has been run, and running it is not')
    add('// authorised by this round. NATIVE_NETLIST_SYNTAX=NOT_VERIFIED: the analysis and pwl forms')
    add('// below are the ones this project has already run (scripts/dd1_d7b_run.py:239 and :288,')
    add('// spectre/current_probe_syntax.scs:35), but hierarchical saves are still unproven on them.')
    add('//')
    add('// ---- this case, in numbers ' + '-' * 55)
    add('// class                 : %s' % row['class'])
    add('// pam_sel               : %s  (pam0=bit0 weight 1, pam1=bit1 weight 2, pam2=bit2 weight 4)'
        % code)
    add('// DATA_EN form          : %s at %s V (the %s V logic domain, never the bit itself)'
        % (row['data_en_form'], row['data_en_level_V'], row['logic_high_V']))
    add('// temperature           : simopt options temp=%s, written as a statement in this deck'
        % contract_data['rules']['process_corner']['temperature_C'])
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
        add('// pure-off preparation: ends at %s ns; offset applied to every instant of this case: '
            '%s ns; half-edge %s ns' % (row['lead_off_ns'], row['offset_applied_ns'], row['edge_ns']))
        add('// platform (rise50/fall50): %s / %s' % (row['platform_start_ns'],
                                                       row['platform_stop_ns']))
        add('// ramp endpoints      : rise %s->%s, fall %s->%s' % (row['rise_low_ns'],
                                                                   row['rise_high_ns'],
                                                                   row['fall_high_ns'],
                                                                   row['fall_low_ns']))
        add('// full-enable window  : %s -> %s (rise50 to fall50; the charge convergence compares)'
            % (row['full_window_start_ns'], row['full_window_stop_ns']))
        add('// flat part           : %s -> %s (the mean current and the sign rule)'
            % (row['flat_start_ns'], row['flat_stop_ns']))
        add('// tail charge window  : %s -> %s' % (row['tail_start_ns'], row['tail_stop_ns']))
        add('// pure-off window     : %s -> %s (DATA_EN is 0 V across all of it)'
            % (row['pure_off_start_ns'], row['pure_off_stop_ns']))
        add('// leakage sub-window  : %s (criterion: max(abs(I_sink)) <= %s A, the deck spells it %s)'
            % (row['leak_window_ns'], _sci_full(contract_data['rules']['shutoff_leakage']['limit_A']),
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
    add('// ---- probe and sign, fixed before any run -------------------------------------------------')
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
    add('// the temperature is a deck condition, not a contract adjective')
    add('simopt options temp=%s' % contract_data['rules']['process_corner']['temperature_C'])
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
    add('Vdd18 (vdd18 0) vsource dc=%s' % _fmt(supplies['vdd18_V']))
    add('Vss (vss 0) vsource dc=0')
    add('Vcas (vcas 0) vsource dc=%s' % _fmt(supplies['vcas_V']))
    if dc:
        add('// The swept node. The %s V evaluation point has to be one of these points, and it is:'
            % _fmt(clamp['main_eval_V']))
        add('// %s is an exact member of the grid.' % _fmt(clamp['main_eval_V']))
        add('Vclamp (clamp_node 0) vsource dc=%s' % _fmt(clamp['main_eval_V']))
        add('// DATA_EN is a static level here: an absolute-current point measured with the branches')
        add('// off would be a point about nothing.')
        add('Vdata_en (data_en 0) vsource dc=%s' % SCHEDULE._g(units['logic_high_V']))
        for node, value in sorted(SCHEDULE.code_bits(code, units['logic_high_V']).items()):
            add('V%s (%s 0) vsource dc=%s   // bit weight %s of code %s'
                % (node.upper(), node, SCHEDULE._g(value),
                   {'pam0': 1, 'pam1': 2, 'pam2': 4}[node], code))
    else:
        add('Vclamp (clamp_node 0) vsource dc=%s' % _fmt(clamp['main_eval_V']))
        enable = _series(pwl, case_id, 'data_en')
        add('// Finite-slope enable as absolute times, low at t=0 and with no extra point inside a')
        add('// ramp, so the interpolated 50% crossing is the edge the schedule declares. Envelope')
        add('// %s.' % _envelope(enable))
        add('Vdata_en (data_en 0) vsource type=pwl %s' % _pwl_statement(enable))
        for node in ('pam0', 'pam1', 'pam2'):
            series = _series(pwl, case_id, node)
            if len(series) == 1:
                add('V%s (%s 0) vsource dc=%s   // static from t=0, settled before the first edge'
                    % (node.upper(), node, series[0]['value_V']))
            else:
                add('// %s holds its value and changes only with the %s ns edge inside a pure-off '
                    'window: %s'
                    % (node, SCHEDULE._g(units['code_edge_ns']), _envelope(series)))
                add('V%s (%s 0) vsource type=pwl %s'
                    % (node.upper(), node, _pwl_statement(series)))
        add('// A second analysis form is deliberately absent: this deck declares one tran line, so a')
        add('// reviewer can tell which stop and maxstep the case was planned with.')
    add('')
    add('// ---- observation points. Hierarchical saves are NOT_VERIFIED on this build; if the native')
    add('// stage refuses them the fallback is to lift the node in a draft copy of the unit subckt,')
    add('// never to edit the delivered candidate.')
    add('Ip_branch (clamp_node data_out) iprobe')
    add('save vdd18 vss iref_in vcas data_out clamp_node irefbus data_en pam0 pam1 pam2')
    add('save Xdut.en0 Xdut.en1 Xdut.en2 Xdut.en3 Xdut.en4 Xdut.en5 Xdut.en6 Xdut.en7')
    add('save Xdut.enb0 Xdut.enb1 Xdut.enb2 Xdut.enb3 Xdut.enb4 Xdut.enb5 Xdut.enb6 Xdut.enb7')
    add('save Xdut.Xu0.vbias_ch Xdut.Xu1.vbias_ch Xdut.Xu2.vbias_ch Xdut.Xu3.vbias_ch')
    add('save Xdut.Xu4.vbias_ch Xdut.Xu5.vbias_ch Xdut.Xu6.vbias_ch Xdut.Xu7.vbias_ch')
    add('save Xdut.Xu0.node_m Xdut.Xu4.node_m')
    add('save Ip_branch Ip_branch:current')
    add('')
    add(row['analysis_line'])
    add('')
    add('// result column for this case in tests/dd1_d7c_b_prep/schedule.csv: %s' % row['result'])
    add('')
    return '\n'.join(lines)


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


def _rows(directory):
    rows, windows, pwl, problems = SCHEDULE.read_delivered(directory)
    if problems:
        raise SystemExit('D7C_B_DECKGEN_REFUSED the schedule it must render is not readable: %s'
                         % problems[0])
    return rows, windows, pwl


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
    """the delivered decks must be exactly what the sources render, and must satisfy the audit"""
    problems = []
    outputs = render_all(directory)
    contract_data = CONTRACT.load(os.path.join(directory,
                                               CONTRACT.CONTRACT_PATH.replace('/', os.sep)))
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
        problems.extend(audit_text(delivered, by_case[name.split('.')[0]], contract_data))
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
        print('D7C_B_DECKGEN_EMITTED %d decks into %s' % (len(written), DECK_DIR))
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
