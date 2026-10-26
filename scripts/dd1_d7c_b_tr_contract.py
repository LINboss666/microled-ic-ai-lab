#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR contract, nine-case plan and their offline checks.

Every number this round measures is derived here from a named source (the approved task book, the
frozen PREP schedule/windows/PWL tables, the accepted DC matrix table, or arithmetic on them), never
typed into a report later. ``--write`` emits the contract and the plan; ``--check`` re-derives them
and refuses on any difference, so a reviewer can prove the committed bytes are the generator output.
"""

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

TASK_ID = 'DATA-7C-B-TR'
BASE_SHA = '61621f6e3d887082ecd6a7ecc1c771f8e509a24a'
ACCEPTED_DC_SHA = 'b7509c4766a6bbfd0413749d50a5f294192b60fb'
ACCEPTED_RTL_SHA = 'f68449672774ac9266ba9e4893024e4f3027dd9d'
MAIN_SHA = '23e471cb936b421ee97e1250c3be06edf96f9937'
BRANCH = 'poc/data-pam-d7c-b-tr'
REPOSITORY = 'https://github.com/LINboss666/microled-ic-ai-lab'
APPROVAL_DATE = '2026-10-26'
APPROVAL_TIMEZONE = 'Asia/Shanghai'

CONTRACT_PATH = 'tests/dd1_d7c_b_tr/contract.json'
CASE_PLAN_PATH = 'tests/dd1_d7c_b_tr/case_plan.csv'
INTERFACE_PATH = 'tests/dd1_d7c_b_tr/source_interfaces.csv'
TASK_BOOK_PATH = 'reports/tasks/DATA-7C-B-TR.md'
CONTRACT_REPORT = 'reports/dd1_d7c_b_tr_contract.md'
PREP_SCHEDULE = 'tests/dd1_d7c_b_prep/schedule.csv'
PREP_WINDOWS = 'tests/dd1_d7c_b_prep/windows.csv'
PREP_PWL = 'tests/dd1_d7c_b_prep/pwl.csv'
PREP_DECK_DIR = 'spectre/dd1_d7c_b_prep'
DECK_DIR = 'spectre/dd1_d7c_b_tr'
DC_MASTERS = 'spectre/dd1_d7c_b_dc/masters'
DC_TABLE = 'results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv'
RTL_PATH = 'rtl/dd1_d7a_gray_ctrl.sv'

# ---- frozen electrical conditions (approved task s4) --------------------------------------------
CORNER = 'TT'
TEMP_C = 27.0
VDD18_V = 1.8
VCAS_V = 1.8
VSS_V = 0.0
IREF_A = 15e-6
CLAMP_V = 1.200
LOGIC_HIGH_V = 1.8
LOGIC_LOW_V = 0.0
ENABLE_MID_V = LOGIC_HIGH_V / 2.0       # the 50 % level of the deck logic domain
IUNIT_A = 1.875e-6
IPROBE_ABS_TOL_V = 1e-6                 # numeric consistency tolerance, NOT a device drop limit
IPROBE_REL_TOL = 1e-9

# ---- frozen measurement rules (approved task s5, s7) --------------------------------------------
TICK_NS = {'TR-LONG': 120.0, 'TR-120': 120.0, 'TR-200': 200.0, 'TR-OFFCODE': 120.0,
           'RS-FULL': 120.0, 'RS-LOW': 120.0, 'RS-SWITCH': 120.0,
           'HYB-120': 120.0, 'HYB-200': 200.0}
MAXSTEP_NS = {'TR-LONG': 2.0, 'TR-120': 2.0, 'TR-200': 2.0, 'TR-OFFCODE': 2.0,
              'RS-FULL': 0.1, 'RS-LOW': 0.1, 'RS-SWITCH': 0.1,
              'HYB-120': 0.1, 'HYB-200': 0.1}
PARENT = {'RS-FULL': 'TR-LONG', 'RS-LOW': 'TR-120', 'RS-SWITCH': 'TR-OFFCODE'}
PREP_CASES = ('TR-LONG', 'TR-120', 'TR-200', 'TR-OFFCODE', 'RS-FULL', 'RS-LOW', 'RS-SWITCH')
HYB_CASES = ('HYB-120', 'HYB-200')
SOURCE = dict((case, 'frozen_PREP') for case in PREP_CASES)
SOURCE.update(dict((case, 'accepted_RTL_new_VCD') for case in HYB_CASES))
CASE_ORDER = list(PREP_CASES) + list(HYB_CASES)
EDGE_NS = 2.0
SHIFT_NS = 1000.0
SETTLE_FRACTION = 0.05
SETTLE_MIN_NS = 10.0
TAIL_NS = 100.0
LEAK_LIMIT_A = 0.15e-6
CONV_LIMIT = 0.01
DYNAMIC_LIMIT_LSB = 0.5
NOMINAL_LIMIT_LSB = 0.5
PREFLIGHT_LOAD_OHMS = 80e3
PREFLIGHT_REF_OHMS = 50e3
SPECTRE_LIMIT = 24
RTL_LIMIT = 4
HYB_FRAMES = (('B0', 0, '000', 0), ('L1', 1, '000', 1), ('M2', 2, '011', 2), ('F63', 63, '111', 64))
SAFETY_FRAME = ('A', 63, '111', 64)
SAFETY_FAULT_T_NS = 2.5
SAFETY_FAULT_AVOID_NS = 3.0
SAFETY_HOLD_NS = 40.0
SAFETY_BLACK_NS = 600.0
INTER_FRAME_PREP_NS = 500.0
CODE_CHANGE_LEAD_NS = 100.0

CASE_PURPOSE = {
    'TR-LONG': '000..111 eight 1 us emission windows, per-step settling and tail',
    'TR-120': 'lowest non-zero code on a 120 ns pulse',
    'TR-200': 'lowest non-zero code on a 200 ns pulse',
    'TR-OFFCODE': '011 -> 100 -> 000 -> 111, code changes only inside the shutoff region',
    'RS-FULL': 'step-size convergence control for TR-LONG',
    'RS-LOW': 'step-size convergence control for TR-120',
    'RS-SWITCH': 'step-size convergence control for TR-OFFCODE',
    'HYB-120': 'joint PWM/PAM charge driven by the accepted RTL four-state VCD at a 120 ns tick',
    'HYB-200': 'joint PWM/PAM charge driven by the accepted RTL four-state VCD at a 200 ns tick',
}

# window_id letter to the kind the frozen windows table calls it
WINDOW_KINDS = {'W': 'emission', 'F': 'emission_flat', 'T': 'off_tail', 'O': 'pure_off',
                'L': 'leak_last100'}


class Refuse(Exception):
    pass


def utc():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def git(*args):
    proc = subprocess.Popen(['git'] + list(args), cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode != 0:
        raise Refuse('git %s rc=%d: %s' % (' '.join(args), proc.returncode,
                                           err.decode('utf-8', 'replace').strip()[:160]))
    return out


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b''):
            digest.update(chunk)
    return digest.hexdigest()


def blob(rev, relpath):
    return git('cat-file', 'blob', '%s:%s' % (rev, relpath))


def blob_sha(rev, relpath):
    return sha_bytes(blob(rev, relpath))


def repo(path):
    return os.path.join(ROOT, path.replace('/', os.sep))


def load(relpath):
    return io.open(repo(relpath), encoding='utf-8', newline='').read()


def table(relpath):
    """a real CSV reader: the frozen windows table quotes cells that contain commas"""
    text = load(relpath)
    reader = csv.DictReader(io.StringIO(text, newline=''))
    return list(reader)


def schedule_rows():
    return dict((row['case_id'], row) for row in table(PREP_SCHEDULE))


def windows_by_case():
    """the frozen windows table keyed by case and by the short window id after the '#'"""
    out = {}
    for row in table(PREP_WINDOWS):
        if '#' not in row['window_id']:
            continue
        out.setdefault(row['case_id'], {})[row['window_id'].split('#')[-1]] = row
    return out


def ns_of(token, ctx=''):
    found = re.match(r'^([0-9.]+)(n|u|m)?$', token.strip())
    if not found:
        raise Refuse('%s: pwl time %r is not a plain ns value' % (ctx, token))
    return float(found.group(1)) * {'': 1e3, 'n': 1.0, 'u': 1e3, 'm': 1e6}[found.group(2) or '']


def pwl_series(text, node, ctx=''):
    """the (ns, V) pairs of one pwl source, matched on the node it drives, not on the source name"""
    for line in text.splitlines():
        found = re.match(r'^V(\w+)\s*\(\s*(\w+)\s+0\)\s*vsource\s+type=pwl\s+wave=\[(.*)\]\s*$',
                         line.strip())
        if found and found.group(2) == node:
            points = found.group(3).split()
            if len(points) % 2:
                raise Refuse('%s: the %s wave has an odd number of tokens' % (ctx, node))
            return [(ns_of(points[index], ctx), float(points[index + 1]))
                    for index in range(0, len(points), 2)]
    return None


def half_crossings(series, level=ENABLE_MID_V):
    """adjacent-pair crossings with linear interpolation; the first sample past the threshold is not
    an edge and is never used."""
    rises, falls = [], []
    for index in range(1, len(series)):
        t0, v0 = series[index - 1]
        t1, v1 = series[index]
        if t1 == t0:
            raise Refuse('the enable wave holds two values at %g ns, so no 50 %% point exists' % t0)
        if v0 < level <= v1:
            rises.append(t0 + (level - v0) * (t1 - t0) / (v1 - v0))
        elif v0 >= level > v1:
            falls.append(t0 + (level - v0) * (t1 - t0) / (v1 - v0))
    if len(rises) != len(falls) and len(rises) != len(falls) + 1 and len(falls) != len(rises) + 1:
        raise Refuse('the enable wave has %d rises and %d falls, which is not a pulse train'
                     % (len(rises), len(falls)))
    return rises, falls


def level_segments(series, level, tol=1e-9):
    """maximal runs of samples at one level, returned as (start_ns, stop_ns) of the plateau"""
    out = []
    start = None
    for index, (time, value) in enumerate(series):
        at = abs(value - level) <= tol
        if at and start is None:
            start = time
        if not at and start is not None:
            out.append((start, series[index - 1][0]))
            start = None
    if start is not None:
        out.append((start, series[-1][0]))
    return out


def windows_from_enable(series):
    """the five window kinds re-derived from the PWL text alone"""
    rises, falls = half_crossings(series)
    emission = [(rises[i], falls[i]) for i in range(min(len(rises), len(falls)))]
    high = level_segments(series, LOGIC_HIGH_V)
    low = [seg for seg in level_segments(series, LOGIC_LOW_V) if seg[1] - seg[0] > 1e-9]
    flat = [seg for seg in high if seg[1] - seg[0] > 1e-9]
    # the low run that follows each fall is the pure-off region; the tail starts at the 50 % fall
    tails, pure_off, leaks = [], [], []
    for index in range(len(emission)):
        fall = emission[index][1]
        after = [seg for seg in low if seg[0] >= fall - 1e-9]
        if not after:
            raise Refuse('no pure-off region starts at or after the fall at %g ns' % fall)
        off = after[0]
        pure_off.append((off[0], off[1]))
        tails.append((fall, off[1]))
        leaks.append((max(off[0], off[1] - TAIL_NS), off[1]))
    return {'emission': emission, 'emission_flat': flat, 'off_tail': tails,
            'pure_off': pure_off, 'leak_last100': leaks}


def fmt_ns(value):
    return '%.3f' % value


def frozen_window_counts():
    """how many windows of each kind the accepted PREP table declares for the seven transient cases"""
    counts = dict((kind, 0) for kind in sorted(WINDOW_KINDS.values()))
    for case_id, rows in sorted(windows_by_case().items()):
        if case_id not in PREP_CASES:
            continue
        for row in rows.values():
            if row['kind'] in counts:
                counts[row['kind']] += 1
    return counts


# ---- the DC reference ----------------------------------------------------------------------------

def dc_idc_by_code(table_text=None):
    """IDC(k) at 1.20 V from the accepted DC table.

    The rounded I_sink_uA display column is deliberately not used: the task fixes the reference to
    the value the accepted table carries in amperes.
    """
    text = table_text if table_text is not None else load(DC_TABLE)
    reader = csv.DictReader(io.StringIO(text.replace('\r\n', '\n'), newline=''))
    found = {}
    for cells in reader:
        if cells['role'] != 'dut' or cells['clamp_V'] != '1.200':
            continue
        code = cells['code']
        if code in found:
            raise Refuse('the accepted DC table carries two 1.20 V DUT rows for code %s' % code)
        found[code] = {'code': code, 'I_sink_A': float(cells['I_sink_A']),
                       'deck_sha256': cells['deck_sha256'], 'raw_sha256': cells['raw_sha256'],
                       'corner': cells['corner'], 'temp_C': float(cells['temp_C']),
                       'data_out_V': float(cells['data_out_V'])}
    if len(found) != 8:
        raise Refuse('the 1.20 V slice of %s has %d DUT codes, it must have exactly 8'
                     % (DC_TABLE, len(found)))
    for code, row in found.items():
        if row['corner'] != CORNER or row['temp_C'] != TEMP_C:
            raise Refuse('code %s in the accepted DC table is %s/%g C, this contract is %s/%g C'
                         % (code, row['corner'], row['temp_C'], CORNER, TEMP_C))
        if abs(row['data_out_V'] - CLAMP_V) > 1e-9:
            raise Refuse('code %s is stored with data_out %r at the %r V clamp row'
                         % (code, row['data_out_V'], CLAMP_V))
    return found


def qlsb_C(tick_ns):
    return IUNIT_A * tick_ns * 1e-9


def nominal_A(code):
    return (int(code, 2) + 1) * IUNIT_A


# ---- the contract ------------------------------------------------------------------------------

def contract():
    schedule = schedule_rows()
    idc = dc_idc_by_code()
    cases = []
    for case_id in CASE_ORDER:
        tick = TICK_NS[case_id]
        row = {'case_id': case_id,
               'class': ('transient' if SOURCE[case_id] == 'frozen_PREP'
                         else 'transient_rtl_vcd_driven'),
               'purpose': CASE_PURPOSE[case_id], 'source': SOURCE[case_id],
               'tick_ns': tick, 'maxstep_ns': MAXSTEP_NS[case_id],
               'convergence_partner': PARENT.get(case_id, ''),
               'preflight_launches': 1, 'dut_launches': 1,
               'qlsb_nominal_C': qlsb_C(tick),
               'authorisation': 'USER_APPROVED',
               'run_copy': '%s/%s.scs' % (DECK_DIR, case_id)}
        if SOURCE[case_id] == 'frozen_PREP':
            source = schedule[case_id]
            row['source_deck'] = '%s/%s.scs' % (PREP_DECK_DIR, case_id)
            row['source_deck_sha256_at_base'] = blob_sha(BASE_SHA, row['source_deck'])
            row['stop_ns'] = float(source['stop_ns'])
            row['analysis_line_in_source'] = source['analysis_line']
            row['paired_case_in_source'] = source['paired_case']
            row['emission_windows_in_source'] = len(split_cell(source['platform_start_ns']))
        else:
            row['source_deck'] = 'NEW: derived from the accepted RTL four-state VCD'
            row['source_deck_sha256_at_base'] = 'NOT_IN_BASE'
            row['stop_ns'] = 'FROM_VCD'
            row['analysis_line_in_source'] = 'NOT_IN_BASE'
            row['paired_case_in_source'] = ''
            row['emission_windows_in_source'] = 'FROM_VCD'
        cases.append(row)
    return {
        'contract_state': 'USER_APPROVED_FOR_EXECUTION_DATA_7C_B_TR',
        'cases': cases,
        'task_id': TASK_ID, 'round': 'TR', 'repository': REPOSITORY, 'branch': BRANCH,
        'base_sha': BASE_SHA, 'accepted_dc_content_sha': ACCEPTED_DC_SHA,
        'accepted_rtl_sha': ACCEPTED_RTL_SHA, 'main_sha_kept': MAIN_SHA,
        'approval_note': 'the user replied YES on %s (%s) to this task book with the two ceilings '
                         'below; the same scope is not asked for again'
                         % (APPROVAL_DATE, APPROVAL_TIMEZONE),
        'authorisation': {
            'status': 'USER_APPROVED', 'approval_date': APPROVAL_DATE,
            'approval_timezone': APPROVAL_TIMEZONE, 'approval_response': 'YES',
            'approved_task_book': TASK_BOOK_PATH,
            'spectre_total_limit': SPECTRE_LIMIT, 'spectre_planned_preflights': 9,
            'spectre_planned_dut_runs': 9, 'spectre_failure_or_debug_margin': 6,
            'rtl_simulation_total_limit': RTL_LIMIT, 'rtl_planned_main_runs': 2,
            'rtl_failure_or_debug_margin': 2,
            'iverilog_compilations_count_as_rtl_simulations': False,
            'next_stage_authorised': False, 'merge_authorised': False,
            'oa_access_authorised': False, 'historical_budgets_may_be_borrowed': False,
            'existing_tracked_paths_may_be_modified': False,
            'guest_write_root': '/root/microled_ai_project/cadence_work/dd1_d7c_b_tr/<run_id>/',
        },
        'electrical_environment': {
            'corner': CORNER, 'temp_C': TEMP_C, 'vdd18_V': VDD18_V, 'vcas_V': VCAS_V,
            'vss_V': VSS_V, 'vss_form': 'explicit 0 V vsource, present in the delivered deck',
            'iref_A': IREF_A,
            'iref_form': 'external 15 uA injected into the frozen diode-connected reference',
            'clamp_V': CLAMP_V,
            'clamp_identity': 'POC_CLAMP_CONDITION_NOT_LED_NOT_VSCAN_NOT_ELECTRODE_RC',
            'logic_high_V': LOGIC_HIGH_V, 'logic_low_V': LOGIC_LOW_V,
            'enable_mid_V': ENABLE_MID_V,
            'model_source': 'the environment variables the accepted rounds already used; no model '
                            'card, vendor path or licence value is copied into this repository',
            'ideal_clamp_note': 'the clamp is an ideal test condition, not a real LED, scan high '
                                 'side or electrode RC',
        },
        'probe': {
            'instance': 'Ip_branch', 'terminals': ['clamp_node', 'data_out'],
            'definition': 'I_sink = Ip_branch with no negation and no abs()',
            'order_rule': 'Ip_branch (clamp_node data_out) iprobe, the order the accepted bench uses',
            'physical_positive_path': ['clamp_node', 'data_out', 'the conducting branch(es)', 'vss'],
            'tail_sign': 'a shutoff tail keeps its own sign; Q, Qpos and abs(Qneg) are reported '
                         'separately and never cancel',
            'ideal_two_terminal_check': {
                'expression': 'abs(data_out_V - clamp_node_V) <= %g + %g * abs(clamp_node_V)'
                              % (IPROBE_ABS_TOL_V, IPROBE_REL_TOL),
                'absolute_tol_V': IPROBE_ABS_TOL_V, 'relative_tol': IPROBE_REL_TOL,
                'identity': 'NUMERIC_CONSISTENCY_OF_THE_EXPORT_NOT_A_DEVICE_DROP_SPEC',
                'must_be_proven_readable': 'this round proves the tolerance is expressible in the '
                                           'exported precision before using it as a check',
                'earlier_round_not_rewritten': 'the accepted DC round keeps its published 20 mV '
                                               'guard and value; only this adapter carries the '
                                               'tightened rule',
            },
        },
        'required_signals': {
            'note': 'carry-over followup F-TR-1 from the DC-R1 limited GO: vss is listed as a '
                    'required signal beside the supplies at the same level in every new extraction '
                    'and observation list of this round',
            'axis': ['time'],
            'current': ['the Ip_branch current column under its real native name'],
            'always_extracted': ['time', 'Ip_branch_current', 'data_en', 'pam0', 'pam1', 'pam2',
                                 'vdd18', 'vss', 'vcas', 'iref_in', 'clamp_node', 'data_out'],
            'internal_nodes': {
                'en': ['Xdut.en%d' % index for index in range(8)],
                'enb': ['Xdut.enb%d' % index for index in range(8)],
                'vbias_ch': ['Xdut.Xu%d.vbias_ch' % index for index in range(8)],
                'node_m': ['Xdut.Xu0.node_m', 'Xdut.Xu4.node_m']},
            'missing_internal_node_rule': 'output measurements already obtained may be kept, but '
                                          'the complete internal observation status is PARTIAL and '
                                          'no full stage PASS is granted for it; the schematic is '
                                          'never redrawn for it',
            'missing_named_rule': 'a name that does not exist is named in the refusal; no contract '
                                  'value is substituted, no observation is claimed and no DUT port '
                                  'is repurposed to make an export appear',
            'pre_run_check': 'before each native launch the save list and the model naming are '
                             'checked read-only, and the first DUT run checks the internal columns '
                             'too, so nine cases are not run to discover a missing observation',
        },
        'dc_reference': {
            'path': DC_TABLE, 'blob_sha256_at_base': blob_sha(BASE_SHA, DC_TABLE),
            'rule': 'IDC(k) is the I_sink_A column of the 1.20 V DUT row of each code in the '
                    'accepted DC table, read at run time rather than copied from a display column',
            'idc_A_by_code': dict((code, idc[code]['I_sink_A']) for code in sorted(idc)),
            'deck_sha256_by_code': dict((code, idc[code]['deck_sha256']) for code in sorted(idc)),
            'raw_sha256_by_code': dict((code, idc[code]['raw_sha256']) for code in sorted(idc)),
            'nominal_A_by_code': dict((code, nominal_A(code)) for code in sorted(idc)),
            'nominal_identity': 'ESTIMATED_MIRROR_RATIO_ONLY',
            'known_dc_bias': 'the accepted DC round measures I111 at 1.20 V as %r A, %+.6f %% above '
                             'the 1.5e-05 A nominal, so a long or full-bright window may exceed '
                             '%g LSB on the nominal error and that is a reported result'
                             % (idc['111']['I_sink_A'],
                                100.0 * (idc['111']['I_sink_A'] / 1.5e-05 - 1.0),
                                NOMINAL_LIMIT_LSB)},
        'charge': {
            'qlsb_definition': 'QLSB_nominal = %g A x Ttick' % IUNIT_A,
            'qlsb_nominal_C_by_tick_ns': dict((('%g' % tick), qlsb_C(tick))
                                              for tick in sorted(set(TICK_NS.values()))),
            'forbidden_denominators': ['the length of the window under test',
                                       'the measured Q of that window',
                                       'a transient average current',
                                       'the code current of that window multiplied by its length',
                                       'I111 / 8 substituted for the nominal denominator'],
            't50_rule': 'T50 is only the interval between the actual %g V crossings of the enable '
                        'for that window; for the safety window it is the actual falling edge after '
                        'the abort' % ENABLE_MID_V,
            'qtarget_nominal': 'Inom(k) x T50', 'qtarget_dc': 'IDC(k) x T50',
            'error_nominal_LSB': '(Qmeas - Qtarget_nominal) / QLSB_nominal',
            'error_dynamic_LSB': '(Qmeas - Qtarget_dc) / QLSB_nominal',
            'dynamic_frozen_limit': DYNAMIC_LIMIT_LSB,
            'nominal_independent_limit': NOMINAL_LIMIT_LSB,
            'both_columns_kept': True,
            'nominal_pass_may_not_be_claimed_from_dynamic_pass': True,
            'limit_status': 'FROZEN_BY_APPROVED_TASK'},
        'windows': {
            'kinds': ['full', 'flat', 'tail', 'pure-off', 'leak-last-100'],
            'source_of_truth': 'the PWL text of the run copy; the five kinds are re-derived from it '
                               'and compared with the frozen windows table, so the generator is '
                               'never its own witness',
            'frozen_table_window_counts': frozen_window_counts(),
            'settling': {'targets': ['Inom(k)', 'IDC(k)'], 'fraction': SETTLE_FRACTION,
                         'min_in_band_ns': SETTLE_MIN_NS,
                         'deadline': 'flat_stop of this window, the start of the falling ramp',
                         'reports': ['start', 'left limit', 'last out-of-band sample'],
                         'short_window': 'NOT_SETTLED_WITHIN_PULSE, the deadline is never moved'},
            'tail': {'window': 'the last %g ns of the pure-off window' % TAIL_NS,
                     'criterion': 'max(abs(I_sink)) <= %g A' % LEAK_LIMIT_A,
                     'measured_only_inside_pure_off': True,
                     'never_merged_into_the_main_window': True,
                     'never_cancelled_against_positive_charge': True},
            'black_window': {
                'rule': 'a zero-code window has no emission edge: Q and max(abs(I)) are measured '
                        'over the whole 64-tick window, Qtarget is 0, the QLSB is the same fixed '
                        'one, and no T50 is invented',
                'post_fault_hold': 'the %g ns after the fault withdrawal is its own black window'
                                   % SAFETY_BLACK_NS}},
        'convergence': {
            'pairs': [{'refined': child, 'coarse': parent, 'tick_ns': TICK_NS[child],
                       'maxstep_ns': MAXSTEP_NS[child], 'coarse_maxstep_ns': MAXSTEP_NS[parent],
                       'only_maxstep_may_differ': True}
                      for child, parent in sorted(PARENT.items())],
            'limit_rel_qlsb': CONV_LIMIT,
            'also_report': 'absolute dQ in coulombs and femtocoulombs per window',
            'context_fields': ['case mapping', 'code position', 'stimulus digest',
                               'measurement window', 'threshold', 'sign rule',
                               'DC reference identity', 'reference_tick', 'QLSB'],
            'missing_context_is_a_refusal': True,
            'none_equals_none_is_not_a_match': True,
            'proves': 'nothing about whether the waveform itself meets an electrical requirement',
            'uncovered': ['TR-200 has no dedicated fine-step partner, so no claim is made that '
                          'every case has an independent fine-step check',
                          'HYB-120 and HYB-200 have no fine-step pair of their own']},
        'hybrid': {
            'driven_by': 'the real four-state VCD of the accepted rtl/dd1_d7a_gray_ctrl.sv at base',
            'rtl_path': RTL_PATH, 'rtl_blob_sha256_at_base': blob_sha(BASE_SHA, RTL_PATH),
            'rtl_equal_to_accepted_f684496': blob_sha(BASE_SHA, RTL_PATH) == blob_sha(
                ACCEPTED_RTL_SHA, RTL_PATH),
            'single_channel_instance': 'one instance only per VCD, no new RTL function, the '
                                       'controller is not modified',
            'frames': [{'frame': name, 'cfg_hyb_time': ht, 'cfg_hyb_pam': pam,
                        'expected_conducting_intervals': m}
                       for name, ht, pam, m in HYB_FRAMES],
            'frame_F63_note': 'cfg_hyb_time == 63 maps to FULL_HYB = 64 intervals in the accepted '
                              'RTL, so M = 64 and not 63',
            'safety_frame': {'frame': SAFETY_FRAME[0], 'cfg_hyb_time': SAFETY_FRAME[1],
                             'cfg_hyb_pam': SAFETY_FRAME[2], 'planned_intervals': SAFETY_FRAME[3],
                             'only_in': 'HYB-120',
                             'fault_rise': 't0 + %g*T + %g ns' % (SAFETY_FAULT_T_NS,
                                                                  SAFETY_FAULT_AVOID_NS),
                             'fault_hold_min_ns': SAFETY_HOLD_NS,
                             'after_withdrawal': 'inside blank only START is issued, no load and no '
                                                 'LATCH, ticks continue and at least %g ns must stay '
                                                 'black' % SAFETY_BLACK_NS,
                             'no_new_recovery_window': True,
                             'measured_as': 'the actual fault closing edge, never the planned 64 T'},
            'protocol': ['reset with mode 00, blank 1, system_en 0',
                         'release reset, change mode to 01 in the safe phase and hold at least two '
                         'reference periods',
                         'allow system_en',
                         'cfg_valid low then high, complete a new load, wait at least one sampling '
                         'edge, then LATCH',
                         'one more sampling edge, then START',
                         'the first tick is consumed only after blank is released',
                         'tick is set ahead on the falling edge and consumed on the rising edge; '
                         'config, latch and START never crowd onto the same edge',
                         'wait for win_state DONE every frame, including a zero code, which still '
                         'walks all 64 intervals, keep the tick at least two more times, then '
                         'prepare the next frame',
                         'at least %g ns of preparation and tail under DATA_EN = 0 between frames'
                         % INTER_FRAME_PREP_NS,
                         'a code change finishes at least %g ns before the next DATA_EN rising edge'
                         % CODE_CHANGE_LEAD_NS],
            't0': 'the reference clk rising edge that consumes the tick, never the obs_tick that '
                  'leads it',
            'vcd_signals': ['clk', 'reset_n', 'system_en', 'tick', 'mode', 'cfg_pure',
                            'cfg_hyb_time', 'cfg_hyb_pam', 'cfg_valid', 'latch_stb', 'pwm_start',
                            'blank', 'fault', 'data_en', 'data_en_b', 'obs_tick', 'pam_sel',
                            'win_state', 'cfg_version', 'proto_err'],
            'conversion': {'signals': ['data_en', 'pam0', 'pam1', 'pam2'],
                           'levels_V': [LOGIC_LOW_V, LOGIC_HIGH_V], 'edge_total_ns': EDGE_NS,
                           'edge_shape': 'a hold/ramp point pair per edge, the 50 % point aligned to '
                                         'the original VCD edge',
                           'shift_ns': SHIFT_NS,
                           'shift_rule': 'the whole waveform moves right, enable and PAM together',
                           'forbidden': 'slow interpolation across an emission window',
                           'self_recheck': 'the converted PWL is re-parsed and every original edge, '
                                           'bit order, %g ns slope and initial level is confirmed; '
                                           'overlapping edges are refused' % EDGE_NS,
                           'xz_rule': 'any X or Z, and any illegal protocol, is refused before the '
                                      'analogue run',
                           'maxstep_ns': MAXSTEP_NS['HYB-120']},
            'expectation_source': 'the independent expectation is built from the input codes and the '
                                  'measured tick stream, not copied from the DUT target arithmetic',
            'normal_frame_rule': 'data_en conducts over [t0, t0 + M*T), pam holds for the whole '
                                 'frame and its tail, and the frame ends with 65 boundary events',
            'not_a_claim': ['not a MOS implementation of the RTL controller',
                            'not a real-time mixed simulation', 'not physical CDC or skew '
                            'verification'],
            'window_count': {'logical_frame_windows': 9,
                             'rule': 'four normal frames per group plus the HYB-120 safety frame; '
                                     'the two zero codes have no emission edge and are listed as '
                                     'black windows',
                             'separately_listed_black_windows': ['the two zero-code frames',
                                                                 'the post-fault hold']}},
        'deck_rules': {
            'run_copies_only': 'this round runs only copies under %s; the frozen PREP deck text is '
                               'never edited' % DECK_DIR,
            'unchanged': ['sources', 'waveforms', 'windows', 'analysis conditions',
                          'the declared physical inputs of a step-size pair'],
            'include_target': 'the six accepted stripped masters listed below',
            'masters': [{'name': name, 'path': '%s/%s' % (DC_MASTERS, name),
                        'blob_sha256_at_base': blob_sha(BASE_SHA, '%s/%s' % (DC_MASTERS, name))}
                        for name in ('dd1_d6_inv18.scs', 'dd1_d6_bias_core.scs',
                                     'dd1_d7c_a_gates.scs', 'dd1_d7c_a_pam_dec.scs',
                                     'dd1_d7c_a_sink_unit.scs', 'dd1_d7c_a_pam_top.scs')],
            'form_proven_on_this_build': {
                'pwl': 'Vname (node 0) vsource type=pwl wave=[t1 v1 ...]',
                'tran': 'tran_case tran stop=<ns> maxstep=<ns>',
                'temp': 'simopt options temp=27',
                'netlist_dir': 'the run payload exports QODER_NETLIST_DIR; the old environment '
                               'file is not touched'},
            'native_time': 'adaptive native samples keep float precision, are strictly increasing '
                           'and finite, and carry their declared unit; they are never rounded to ps '
                           'nor assumed equally spaced',
            'display_and_algorithm_tolerance': 'reported in separate columns',
            'step_speed_may_not_be_tuned_for_pass': True,
            'preflight': {'loads': ['Rload_meter (data_out vss) resistor r=80e3',
                                   'Rref_meter (iref_in vss) resistor r=50e3',
                                   'Vclamp (clamp_node 0) vsource dc=%g' % CLAMP_V],
                          'keeps': ['supplies', 'PWL inputs', 'time range', 'maxstep'],
                          'drops': 'the hierarchical saves of a DUT that is not present',
                          'expected': {'clamp_current_A': CLAMP_V / PREFLIGHT_LOAD_OHMS,
                                       'reference_node_V': (CLAMP_V / PREFLIGHT_LOAD_OHMS)
                                           * PREFLIGHT_REF_OHMS},
                          'load_ohms': PREFLIGHT_LOAD_OHMS, 'reference_ohms': PREFLIGHT_REF_OHMS,
                          'also_read_back': 'the input PWL levels, edges and bit order from the '
                                            'native output',
                          'not_a_claim': 'an ideal resistive preflight does not switch off with '
                                         'DATA_EN, so it is never a shutoff or ladder result'}},
        'accounting': {
            'counts': 'every simulator process, including -h, version, syntax probes, failures, '
                      'crashes, aborts and sub-calls made inside the runner',
            'reserve_before_start': 'REQUESTED is persisted before the process starts',
            'no_refund': 'a failure costs the budget; recovery never refunds it',
            'single_executor': 'one executor runs at a time and re-reads the on-disk account inside '
                               'the lock',
            'uncertain_kept': 'an uncertain request keeps its charge',
            'ceiling_spectre': SPECTRE_LIMIT, 'ceiling_rtl': RTL_LIMIT,
            'old_ledgers_modified': False, 'borrowed': [],
            'not_borrowed': ['DATA-7B 59/56', 'the DC round remaining 4', 'the PREP 36 draft']},
        'publication': {
            'statuses': ['EXECUTION_COMPLETENESS', 'EVIDENCE_INTEGRITY', 'DYNAMIC_CHARGE_STATUS',
                         'NOMINAL_CHARGE_STATUS', 'SETTLING_STATUS', 'SHUTOFF_STATUS',
                         'CONVERGENCE_STATUS'],
            'one_overall_pass_may_not_absorb_a_negative_finding': True,
            'electrical_fail_still_delivers_valid_measurements': True},
        'internal_nodes': {
            'per_step_observation': 'TR-LONG reports at least 50 ns of time-weighted observation at '
                                    'the end of every flat step: the eight en/enb logics, the eight '
                                    'vbias_ch, the shared iref_in and a representative node_m',
            'time_weighted_ns': 50.0,
            'branch_count_rule': 'checked against k+1 conducting branches, with an unselected branch '
                                 'local bias distinguished from a selected one',
            'switch_and_off': 'the internal nodes and the output current are shown together and the '
                              'delay is attributed to decode, bias charge/discharge or current '
                              'build-up; where the evidence does not reach, the report says it was '
                              'not attributed',
            'no_presumed_bias_voltage': True,
            'no_device_op_parameters': 'this build saves node values only, so no MOS region, SOA or '
                                       'saturation sign-off is claimed from a node name',
            'not_done_this_round': ['no Iref/W/L change', 'no 0.3 V extension', 'no LED',
                                    'no scan high side', 'no electrode RC']},
        'carried_followups': [
            {'id': 'F-TR-1', 'origin': 'DC-R1 limited GO section 5(1)',
             'text': 'vss is a required signal alongside the supplies; this round carries it in '
                     'every new extraction and observation list'},
            {'id': 'F-TR-2', 'origin': 'DC-R1 limited GO section 5(1)',
             'text': 'the ideal iprobe two-terminal check uses %g V plus %g times the magnitude, is '
                     'proven readable in this machine export precision, and is not a device drop '
                     'spec' % (IPROBE_ABS_TOL_V, IPROBE_REL_TOL)}],
        'not_run': ['GRAY_LUT', 'FULL_MOS_GRAY_CONTROLLER', 'TCON', 'ARRAY', 'LAYOUT', 'DRC', 'LVS',
                    'PEX', 'OA_READ_OR_WRITE'],
        'not_verified': ['OPTICAL_EFFECTIVE_BITS', 'PHYSICAL_CDC_AND_SKEW', 'SOA_SIGNOFF',
                         'MISMATCH', 'PVT', 'PRODUCTION_ACCURACY'],
        'frozen': {
            'dut_geometry_body_and_reference_structure': 'unchanged; no W/L/body edit is authorised',
            'candidate_duts_and_derived_masters': 'the four candidate DUTs, the six stripped '
                                                  'masters and the fifteen PREP decks are frozen',
            'old_records_reports_handoffs_and_ledgers': 'frozen',
            'prep_contract_state': 'the PROPOSED bytes are kept byte-identical; this contract '
                                   'carries the frozen decision and its source',
            'data_and_pam_polarity': 'Data drives the LED N side and the scan high side drives the P '
                                     'side; the polarity is not changed'},
    }


def split_cell(cell):
    return [part for part in (cell or '').split(';') if part and part.strip().lower() != 'none']


CASE_PLAN_HEADER = ('case_id', 'source', 'tick_ns', 'maxstep_ns', 'convergence_partner',
                    'preflight_launches', 'dut_launches', 'authorisation', 'result', 'purpose')


# ---- reused primitives, read before writing anything new ---------------------------------------
# Each row names a symbol in a file that exists at the base commit; --interfaces resolves the line
# number out of the base blob and refuses a symbol it cannot find, so the record cannot cite code
# that is not there.
INTERFACES = (
    ('scripts/dd1_d7b_measure.py', 'float_samples', 'native adaptive samples kept as floats',
     'KEEP: this is what stops the round from rounding native time to ps or assuming a uniform step'),
    ('scripts/dd1_d7b_measure.py', 'time_quantum_ps', 'reported export quantum',
     'USE for the F-TR-2 readability proof only; a display quantum is not an algorithm tolerance'),
    ('scripts/dd1_d7b_measure.py', 'interp_pair', 'linear interpolation at a window bound',
     'KEEP'),
    ('scripts/dd1_d7b_measure.py', 'clip_window', 'window bounds that are not sample points', 'KEEP'),
    ('scripts/dd1_d7b_measure.py', 'signed_areas', 'positive and negative area kept apart',
     'KEEP: Q, Qpos and abs(Qneg) are reported separately and never cancel'),
    ('scripts/dd1_d7b_measure.py', 'integrate', 'trapezoid integral over an interpolated window',
     'KEEP; the main result is never a resampled or decimated approximation'),
    ('scripts/dd1_d7b_measure.py', 'crossing', 'adjacent-pair level crossing with interpolation',
     'KEEP for the 0.9 V T50 crossings; a first-sample-past-threshold is not a crossing'),
    ('scripts/dd1_d7b_measure.py', 'sustained_in_band', 'settling with a minimum in-band time',
     'REUSE with the deadline replaced by flat_stop of this window'),
    ('scripts/dd1_d7b_measure.py', 'band_spans', 'in-band spans used by settling',
     'KEEP, but BAND_REL is the inherited POC tolerance, not a new claim'),
    ('scripts/dd1_d7b_measure.py', 'tail_segment_max_abs', 'last-100 ns leakage magnitude',
     'KEEP with OFF_ABS replaced by the frozen 0.15 uA of this contract'),
    ('scripts/dd1_d7b_measure.py', 'measure_window', 'the DATA-7B window assembly',
     'DO NOT INHERIT: its ical, tick and threshold defaults are Pure-specific'),
    ('scripts/dd1_d7b_measure.py', 'judge', 'the DATA-7B verdict',
     'DO NOT INHERIT: this round publishes six separate statuses'),
    ('scripts/dd1_d7b_trace.py', 'read_trace', 'real four-state VCD reader',
     'SCOPE MUST BE VERIFIED: the default scope is the DATA-7B testbench, not this TB'),
    ('scripts/dd1_d7b_trace.py', 'defined_bits', 'refuse X and Z before any conversion',
     'KEEP'),
    ('scripts/dd1_d7b_trace.py', 'bus_values', 'bus words decoded with their bit order',
     'KEEP: pam0 is bit 0 weight 1'),
    ('scripts/dd1_d7b_trace.py', 'sampling_edges', 'the reference edges that consume a tick',
     'KEEP: t0 is a clk rising edge, never the leading obs_tick'),
    ('scripts/dd1_d7b_trace.py', 'window_edges', 'edges inside one logical window', 'KEEP'),
    ('scripts/dd1_d7b_trace.py', 'build_pwl', 'edges to hold/ramp PWL points',
     'REUSE with edge_total 2 ns and the whole-wave shift; its Pure ramp and TAIL_NS defaults are '
     'not adopted unverified'),
    ('scripts/dd1_d7b_trace.py', 'check_window', 'stimulus self-check',
     'REWRITE: it carries the Pure settling target, this round checks the hybrid frame windows of '
     'its own contract'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'ps', 'ns to ps without integer loss', 'KEEP'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'enable_edges', 'rise50 and fall50 of an enable series',
     'KEEP with the 0.9 V threshold of this contract'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'reference_tick_for_case', 'per-case QLSB tick',
     'SUPERSEDED: this round reads the tick from its own contract, the PREP mapping stays PROPOSED'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'window_charge', 'signed charge over a window', 'KEEP'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'settling', 'settling against a deadline',
     'IF THE TARGET IS HARD-WIRED TO THE NOMINAL CURRENT, keep that column and compute the IDC-target '
     'result with the same base functions'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'leakage', 'tail leakage inside a pure-off region',
     'KEEP, measured only inside pure-off and never across the next rise'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'charge_errors', 'nominal and dynamic LSB errors',
     'KEEP both columns; the denominator stays QLSB_nominal'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'ladder', 'per-code staircase view', 'REUSE read-only'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'convergence', 'coarse against refined with context',
     'KEEP the context refusal; None == None is not a match'),
    ('scripts/dd1_d7c_b_prep_measure.py', 'measure_case', 'the PREP synthetic measurement entry',
     'DO NOT INHERIT AS A TRANSIENT EXTRACTOR: it reads a synthetic sample set, not a native raw'),
    ('scripts/dd1_d7c_b_dc_run.py', 'Account', 'append-only reserve-before-start ledger',
     'REUSE THE DISCIPLINE with this round ceilings of 24 and 4'),
    ('scripts/dd1_d7c_b_dc_run.py', 'strip_masters', 'six stripped masters with digests',
     'READ ONLY: the masters are frozen accepted content'),
    ('scripts/dd1_d7c_b_dc_run.py', 'preflight_deck', 'ideal meter loads instead of the DUT',
     'REUSE the 80 kohm and 50 kohm witness values for the transient preflight'),
    ('scripts/dd1_d7c_b_dc_run.py', 'psf_units', 'units declared by the native file itself',
     'KEEP: units come from the answer, never assumed'),
    ('scripts/dd1_d7c_b_dc_run.py', 'probe_column', 'the real native current column name',
     'KEEP and name the column when it is absent'),
    ('scripts/dd1_d7c_b_dc_run.py', 'deck_static_sources', 'levels the deck declares',
     'REUSE: conditions are attributed to the deck, never to an observation'),
    ('scripts/dd1_d7c_b_dc_run.py', 'logic_bit', 'a level that is neither rail is refused',
     'KEEP for the PAM bit readback of a preflight'),
    ('scripts/dd1_d7c_b_dc_run.py', 'extract', 'strict required-signal extraction of DC rows',
     'DO NOT INHERIT: it is a static sweep extractor, a transient extractor is written new here'),
    ('scripts/dd1_d7c_b_dc_run.py', 'validate_dc_matrix', 'complete-matrix gate before a verdict',
     'REUSE THE PATTERN: the transient record needs its own complete-window gate'),
    ('scripts/dd1_d7b_run.py', 'Link', 'ssh plus scp channel with base64 payloads',
     'REUSE the accepted channel unchanged; no new bridge toolchain'),
    ('scripts/dd1_d7b_run.py', 'write_rows', 'the project csv writer', 'REUSE'),
    ('scripts/dd1_d7b_run.py', 'parse_runner', 'the runner answer fields read as numbers',
     'REUSE: only an explicit token plus rc 0 is success'),
    ('scripts/dd1_d7b_run.py', 'strip_direction_annotations', 'port direction annotation removal',
     'READ ONLY'),
    ('scripts/sc1_read_psf.py', 'parse', 'psfascii reader', 'REUSE'),
    ('scripts/sc1_read_psf.py', 'as_columns', 'grouped columns plus axis', 'REUSE'),
    ('scripts/dd1_d7a_run.py', 'find_tools', 'the oss-cad-suite toolchain probe',
     'REUSE, and a missing toolchain is a hard stop rather than a substitute'),
    ('scripts/dd1_d7a_run.py', 'compile_sim', 'iverilog -g2012 -Wall',
     'REUSE: a compilation is recorded but is not an RTL simulation'),
    ('scripts/dd1_d7a_run.py', 'run_vvp', 'vvp run plus VCD sanity',
     'EVERY actual vvp start, including a failure, is charged against the four simulations'),
    ('rtl/dd1_d7a_gray_ctrl.sv', 'dd1_d7a_gray_ctrl', 'the accepted controller semantics',
     'READ ONLY: 63 maps to FULL_HYB 64, tick is consumed on a clk edge, blank and fault pull the '
     'enable down combinationally'),
    ('tests/dd1_d7a/tb_dd1_d7a_gray.sv', 'run_window', 'the accepted protocol task pattern',
     'PATTERN ONLY: this round writes its own single-channel frame testbench'),
    ('reports/dd1_d7a_contract.md', '', 'the accepted RTL contract', 'READ ONLY'),
    ('tests/dd1_d7c_b_prep/contract.json', '', 'the PROPOSED preparation contract bytes',
     'FROZEN: this new contract carries the frozen decision and its source'),
    ('tests/dd1_d7c_b_prep/schedule.csv', '', 'frozen timing of the seven prepared cases',
     'FROZEN, read back independently'),
    ('tests/dd1_d7c_b_prep/windows.csv', '', 'frozen window declarations', 'FROZEN, read back'),
    ('spectre/dd1_d7c_b_dc/masters', '', 'the six stripped masters actually included',
     'FROZEN'),
    ('scripts/run_spectre.sh', '', 'the guest batch executor',
     'USED AS IS; the payload exports QODER_NETLIST_DIR itself'),
)

INTERFACE_HEADER = ('module', 'symbol', 'line_at_base', 'resolved_as', 'use', 'inheritance_rule')

# a citation is only worth anything if it points at the definition, so the definition forms are tried
# first and a bare first mention is labelled as such instead of silently passing for a definition
SYMBOL_FORMS = (('def', r'^\s*def\s+%s\s*\('),
                ('class', r'^\s*class\s+%s\b'),
                ('task', r'^\s*task\s+(?:automatic\s+)?%s\b'),
                ('function', r'^\s*function\s+(?:automatic\s+)?(?:\w+\s+)?%s\b'),
                ('module', r'^\s*module\s+%s\b'),
                ('constant', r'^\s*%s\s*='))


def find_symbol(text, symbol):
    for kind, form in SYMBOL_FORMS:
        pattern = re.compile(form % re.escape(symbol), re.M)
        for index, line in enumerate(text.split('\n'), 1):
            if pattern.match(line):
                return index, kind
    for index, line in enumerate(text.split('\n'), 1):
        if re.search(r'\b%s\b' % re.escape(symbol), line):
            return index, 'FIRST_MENTION_NOT_A_DEFINITION'
    return None, None


def interface_rows():
    """resolve every cited symbol to its line in the base blob; an unfindable symbol is a refusal"""
    out = []
    for relpath, symbol, use, rule in INTERFACES:
        if os.path.isdir(repo(relpath)):
            out.append({'module': relpath, 'symbol': '', 'line_at_base': '',
                        'resolved_as': 'PATH', 'use': use, 'inheritance_rule': rule})
            continue
        text = blob(BASE_SHA, relpath).decode('utf-8', 'replace')
        if not symbol:
            out.append({'module': relpath, 'symbol': '', 'line_at_base': '1',
                        'resolved_as': 'FILE', 'use': use, 'inheritance_rule': rule})
            continue
        line, kind = find_symbol(text, symbol)
        if not line:
            raise Refuse('%s does not mention %s at the base commit' % (relpath, symbol))
        out.append({'module': relpath, 'symbol': symbol, 'line_at_base': str(line),
                    'resolved_as': kind, 'use': use, 'inheritance_rule': rule})
    return out


def interfaces_text():
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(list(INTERFACE_HEADER))
    for row in interface_rows():
        writer.writerow([row[key] for key in INTERFACE_HEADER])
    return buffer.getvalue()


def write_interfaces():
    path = repo(INTERFACE_PATH)
    with io.open(path, 'wb') as handle:
        handle.write(interfaces_text().encode('utf-8'))
    return path



def case_plan_rows():
    out = []
    for case_id in CASE_ORDER:
        out.append({'case_id': case_id, 'source': SOURCE[case_id], 'tick_ns': '%g' % TICK_NS[case_id],
                    'maxstep_ns': '%g' % MAXSTEP_NS[case_id],
                    'convergence_partner': PARENT.get(case_id, ''),
                    'preflight_launches': '1', 'dut_launches': '1', 'authorisation': 'USER_APPROVED',
                    'result': 'NOT_RUN', 'purpose': CASE_PURPOSE[case_id]})
    return out


def case_plan_text():
    """a real CSV writer: the purpose column quotes cells that contain commas, and check() reads the
    written bytes back with the same reader so a delimiter can never go unnoticed"""
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(list(CASE_PLAN_HEADER))
    for row in case_plan_rows():
        writer.writerow([row[key] for key in CASE_PLAN_HEADER])
    return buffer.getvalue()


def contract_text():
    return json.dumps(contract(), indent=1, sort_keys=True, ensure_ascii=False) + '\n'


def write():
    for rel in (os.path.dirname(CONTRACT_PATH), DECK_DIR):
        if not os.path.isdir(repo(rel)):
            os.makedirs(repo(rel))
    with io.open(repo(CONTRACT_PATH), 'wb') as handle:
        handle.write(contract_text().encode('utf-8'))
    with io.open(repo(CASE_PLAN_PATH), 'wb') as handle:
        handle.write(case_plan_text().encode('utf-8'))
    write_interfaces()
    return {'contract': CONTRACT_PATH, 'case_plan': CASE_PLAN_PATH,
            'interfaces': INTERFACE_PATH}


# ---- checks -------------------------------------------------------------------------------------

def check_arithmetic(data):
    problems = []
    for tick in sorted(set(TICK_NS.values())):
        want = IUNIT_A * tick * 1e-9
        got = data['charge']['qlsb_nominal_C_by_tick_ns']['%g' % tick]
        if abs(got - want) > abs(want) * 1e-12:
            problems.append('QLSB for a %g ns tick is %r, arithmetic says %r' % (tick, got, want))
    if abs(data['charge']['qlsb_nominal_C_by_tick_ns']['120'] - 2.25e-13) > 2.25e-25:
        problems.append('the 120 ns QLSB is not 2.25e-13 C')
    if abs(data['charge']['qlsb_nominal_C_by_tick_ns']['200'] - 3.75e-13) > 3.75e-25:
        problems.append('the 200 ns QLSB is not 3.75e-13 C')
    for code, value in data['dc_reference']['nominal_A_by_code'].items():
        if abs(value - (int(code, 2) + 1) * IUNIT_A) > 1e-18:
            problems.append('Inom(%s) is %r, (k+1) x 1.875 uA says %r'
                            % (code, value, (int(code, 2) + 1) * IUNIT_A))
    for case in data['cases']:
        if abs(case['qlsb_nominal_C'] - IUNIT_A * case['tick_ns'] * 1e-9) > 1e-24:
            problems.append('%s carries a QLSB that is not Iunit x its own tick' % case['case_id'])
        if case['source'] == 'frozen_PREP' and case['convergence_partner']:
            parent = [row for row in data['cases']
                      if row['case_id'] == case['convergence_partner']][0]
            if case['tick_ns'] != parent['tick_ns']:
                problems.append('%s uses tick %g while its parent %s uses %g'
                                % (case['case_id'], case['tick_ns'], parent['case_id'],
                                   parent['tick_ns']))
    frame = [row for row in data['hybrid']['frames'] if row['frame'] == 'F63'][0]
    if frame['expected_conducting_intervals'] != 64:
        problems.append('F63 must conduct 64 intervals, the accepted RTL maps 63 to FULL_HYB')
    if data['hybrid']['rtl_equal_to_accepted_f684496'] is not True:
        problems.append('the RTL at base is not byte-equal to the accepted f684496 content')
    if data['probe']['ideal_two_terminal_check']['absolute_tol_V'] != 1e-6:
        problems.append('the iprobe consistency tolerance is not the carried-followup value')
    counts = data['windows']['frozen_table_window_counts']
    if counts != frozen_window_counts():
        problems.append('the stored frozen-window counts are not the table counts %s'
                        % frozen_window_counts())
    if counts.get('emission') != 27:
        problems.append('the seven PREP cases declare %r emission windows, the approved task says 27'
                        % counts.get('emission'))
    problems += check_convergence_metadata(data)
    return problems


def check_convergence_metadata(data):
    """the declared pairs must be the cases that name a partner, and every field of a pair must be
    the plan value, so a convergence claim cannot carry its own numbers."""
    problems = []
    by_case = dict((row['case_id'], row) for row in data['cases'])
    named = set(row['case_id'] for row in data['cases'] if row['convergence_partner'])
    listed = set(pair['refined'] for pair in data['convergence']['pairs'])
    if named != listed:
        problems.append('the cases naming a partner (%s) are not the declared pairs (%s)'
                        % (','.join(sorted(named)) or '-', ','.join(sorted(listed))))
    for pair in data['convergence']['pairs']:
        refined, coarse = pair['refined'], pair['coarse']
        if coarse not in by_case:
            problems.append('%s names %s as its parent, which is not a case of this plan'
                            % (refined, coarse))
            continue
        if pair['maxstep_ns'] != by_case[refined]['maxstep_ns']:
            problems.append('%s: the pair carries maxstep %g but the case carries %g'
                            % (refined, pair['maxstep_ns'], by_case[refined]['maxstep_ns']))
        if pair['coarse_maxstep_ns'] != by_case[coarse]['maxstep_ns']:
            problems.append('%s: the pair carries parent maxstep %g but %s carries %g'
                            % (refined, pair['coarse_maxstep_ns'], coarse,
                               by_case[coarse]['maxstep_ns']))
        if not pair['maxstep_ns'] < pair['coarse_maxstep_ns']:
            problems.append('%s is not a finer step than its parent %s' % (refined, coarse))
        if pair['tick_ns'] != by_case[refined]['tick_ns'] or pair['tick_ns'] != by_case[coarse]['tick_ns']:
            problems.append('%s/%s: the pair tick %g is not the tick both cases measure on'
                            % (refined, coarse, pair['tick_ns']))
    uncovered = ' '.join(data['convergence']['uncovered'])
    for case_id in ('TR-200', 'HYB-120', 'HYB-200'):
        if case_id in by_case and by_case[case_id]['convergence_partner']:
            problems.append('%s claims a convergence partner although no finer deck of it exists'
                            % case_id)
    if 'TR-200' not in uncovered:
        problems.append('the plan does not say that TR-200 has no fine-step partner')
    return problems


def check_dc_reference(data):
    """the stored DC reference must equal the accepted table re-read, so a nominal substituted for a
    measured value is caught rather than trusted."""
    problems = []
    idc = dc_idc_by_code()
    for code in sorted(idc):
        stored = data['dc_reference']['idc_A_by_code'].get(code)
        if stored is None:
            problems.append('code %s has no DC reference stored' % code)
            continue
        if abs(stored - idc[code]['I_sink_A']) > abs(idc[code]['I_sink_A']) * 1e-12:
            problems.append('the stored IDC(%s)=%r is not the accepted table value %r'
                            % (code, stored, idc[code]['I_sink_A']))
        for key in ('deck_sha256_by_code', 'raw_sha256_by_code'):
            column = 'deck_sha256' if 'deck' in key else 'raw_sha256'
            if data['dc_reference'][key].get(code) != idc[code][column]:
                problems.append('the stored %s of code %s is not the accepted table value'
                                % (column, code))
    if abs(data['dc_reference']['idc_A_by_code']['111'] - 1.5e-05) < 1e-12:
        problems.append('I111 in the DC reference is exactly the nominal 1.5e-05 A, which would mean '
                        'the measured accepted value was replaced by a nominal one')
    return problems


def check_deck_consistency(data):
    problems = []
    schedule = schedule_rows()
    for case in data['cases']:
        case_id = case['case_id']
        if case['source'] != 'frozen_PREP':
            continue
        source = schedule[case_id]
        if float(source['maxstep_ns']) != case['maxstep_ns']:
            problems.append('%s: the plan says maxstep %g but the frozen schedule says %s'
                            % (case_id, case['maxstep_ns'], source['maxstep_ns']))
        if float(source['stop_ns']) != case['stop_ns']:
            problems.append('%s: the plan stop %g disagrees with the frozen schedule %s'
                            % (case_id, case['stop_ns'], source['stop_ns']))
        text = load(case['source_deck'])
        analysis = re.findall(r'^tran_case tran stop=(\S+) maxstep=(\S+)$', text, re.M)
        if len(analysis) != 1:
            problems.append('%s declares %d tran lines, exactly one is required'
                            % (case_id, len(analysis)))
            continue
        stop, step = analysis[0]
        if stop != '%.3fn' % case['stop_ns'] or abs(float(step[:-1]) - case['maxstep_ns']) > 1e-12:
            problems.append('%s: the deck analysis line stop=%s maxstep=%s disagrees with the plan '
                            'stop=%g maxstep=%g' % (case_id, stop, step, case['stop_ns'],
                                                     case['maxstep_ns']))
        driven = re.findall(r'^V\w+\s*\(\s*(\w+)\s+\S+\)\s*vsource', text, re.M)
        for node in ('vdd18', 'vcas', 'vss', 'data_en', 'pam0', 'pam1', 'pam2', 'clamp_node'):
            if node not in driven:
                problems.append('%s: the frozen deck drives no source for %s' % (case_id, node))
        saves = ' '.join(re.findall(r'^save\s+(.*)$', text, re.M)).split()
        need = (data['required_signals']['internal_nodes']['en']
                + data['required_signals']['internal_nodes']['enb']
                + data['required_signals']['internal_nodes']['vbias_ch']
                + data['required_signals']['internal_nodes']['node_m']
                + ['vss', 'clamp_node', 'data_out', 'iref_in', 'vcas', 'vdd18', 'data_en',
                   'pam0', 'pam1', 'pam2'])
        missing = [name for name in need if name not in saves]
        if missing:
            problems.append('%s: the frozen deck saves no %s' % (case_id, ','.join(missing[:6])))
        includes = re.findall(r'^include "\$\{QODER_NETLIST_DIR\}/(\S+)"', text, re.M)
        listed = [os.path.basename(row['path']) for row in data['deck_rules']['masters']]
        if sorted(includes) != sorted(listed):
            problems.append('%s: the deck includes %s, the contract lists the six masters %s'
                            % (case_id, ','.join(includes), ','.join(listed)))
    for pair in data['convergence']['pairs']:
        parent, child = pair['coarse'], pair['refined']
        body = lambda path: [line for line in load(path).split('\n') if not line.startswith('//')]
        parent_lines = body(repo('%s/%s.scs' % (PREP_DECK_DIR, parent)))
        child_lines = body(repo('%s/%s.scs' % (PREP_DECK_DIR, child)))
        if len(parent_lines) != len(child_lines):
            problems.append('%s/%s: the decks have different numbers of statements' % (child, parent))
            continue
        diff = [(a, b) for a, b in zip(parent_lines, child_lines) if a != b]
        if not diff:
            problems.append('%s/%s: no difference at all, so the maxstep pair is not real'
                            % (child, parent))
        for a, b in diff:
            if not (a.startswith('tran_case') and b.startswith('tran_case')):
                problems.append('%s/%s: the decks differ beyond maxstep: %r against %r'
                                % (child, parent, a[:70], b[:70]))
            elif ('stop=%s' % ('%.3fn' % case_stop(data, parent))) not in a:
                problems.append('%s/%s: the stop of the pair is not the parent stop' % (child, parent))
    return problems


def case_stop(data, case_id):
    for row in data['cases']:
        if row['case_id'] == case_id:
            return row['stop_ns']
    raise Refuse('%s is not in the contract case list' % case_id)


def check_pwl_readback(data):
    """the five declared window kinds of every frozen case are re-derived from the delivered PWL."""
    problems = []
    windows = windows_by_case()
    for case in data['cases']:
        case_id = case['case_id']
        if case['source'] != 'frozen_PREP':
            continue
        text = load(case['source_deck'])
        series = pwl_series(text, 'data_en', case_id)
        if series is None:
            problems.append('%s: the delivered deck has no data_en pwl source' % case_id)
            continue
        derived = windows_from_enable(series)
        declared = windows[case_id]
        for letter, kind in sorted(WINDOW_KINDS.items()):
            want = derived[kind]
            for index in range(len(want)):
                window_id = '%s%d' % (letter, index)
                row = declared.get(window_id)
                if row is None:
                    problems.append('%s: the delivered PWL gives a %s window %s that the frozen '
                                    'windows table does not declare' % (case_id, kind, window_id))
                    continue
                if row['kind'] != kind:
                    problems.append('%s#%s: the frozen table calls it %s, the PWL derivation calls '
                                    'it %s' % (case_id, window_id, row['kind'], kind))
                for column, value in (('start_ns', want[index][0]), ('stop_ns', want[index][1])):
                    if abs(float(row[column]) - value) > 1e-9:
                        problems.append('%s#%s: %s reads %s ns from the delivered PWL, the frozen '
                                        'table says %s' % (case_id, window_id, column,
                                                           fmt_ns(value), row[column]))
            extra = [key for key in declared
                     if key.startswith(letter)
                     and int(key[len(letter):]) >= len(want)]
            for key in extra:
                problems.append('%s#%s is declared but the delivered PWL produces no such %s window'
                                % (case_id, key, kind))
        if abs(series[0][1] - LOGIC_LOW_V) > 1e-9:
            problems.append('%s: the enable pwl is not low at t=0' % case_id)
    return problems


def check_case_plan(data):
    problems = []
    rows = case_plan_rows()
    if len(rows) != 9:
        problems.append('the plan has %d cases, the approved task names nine' % len(rows))
    read = list(csv.DictReader(io.StringIO(case_plan_text(), newline='')))
    if len(read) != len(rows):
        problems.append('the written plan re-reads as %d rows, the generator made %d'
                        % (len(read), len(rows)))
    for written, back in zip(rows, read):
        for key in CASE_PLAN_HEADER:
            if written[key] != back[key]:
                problems.append('the plan field %s of %s does not survive the csv round trip'
                                % (key, written['case_id']))
    launch = sum(int(row['preflight_launches']) + int(row['dut_launches']) for row in rows)
    if launch != 18:
        problems.append('the plan asks for %d launches, nine preflights plus nine DUT runs is 18'
                        % launch)
    if data['authorisation']['spectre_total_limit'] != 24:
        problems.append('the spectre ceiling is not 24')
    if data['authorisation']['spectre_planned_preflights'] + \
            data['authorisation']['spectre_planned_dut_runs'] + \
            data['authorisation']['spectre_failure_or_debug_margin'] != 24:
        problems.append('the planned preflights, DUT runs and margin do not add up to the ceiling')
    if data['authorisation']['rtl_planned_main_runs'] + \
            data['authorisation']['rtl_failure_or_debug_margin'] != \
            data['authorisation']['rtl_simulation_total_limit']:
        problems.append('the RTL plan does not add up to the RTL ceiling')
    for row in rows:
        if row['authorisation'] != 'USER_APPROVED' or row['result'] != 'NOT_RUN':
            problems.append('%s is not USER_APPROVED/NOT_RUN before any native work' % row['case_id'])
    return problems


def check():
    data = contract()
    problems = []
    if io.open(repo(CONTRACT_PATH), encoding='utf-8').read() != contract_text():
        problems.append('%s on disk is not the generator output' % CONTRACT_PATH)
    if io.open(repo(CASE_PLAN_PATH), encoding='utf-8', newline='').read() != case_plan_text():
        problems.append('%s on disk is not the generator output' % CASE_PLAN_PATH)
    if (io.open(repo(INTERFACE_PATH), encoding='utf-8', newline='').read()
            != interfaces_text()):
        problems.append('%s on disk is not the generator output' % INTERFACE_PATH)
    for row in data['cases']:
        if row['source'] == 'frozen_PREP':
            if blob_sha(BASE_SHA, row['source_deck']) != row['source_deck_sha256_at_base']:
                problems.append('%s drifted from the base blob' % row['case_id'])
    for master in data['deck_rules']['masters']:
        if sha_file(repo(master['path'])) != master['blob_sha256_at_base']:
            problems.append('%s on disk is not its base blob (a CRLF working copy would be)'
                            % master['path'])
    if sha_file(repo(DC_TABLE)) != blob_sha(BASE_SHA, DC_TABLE):
        problems.append('the accepted DC table on disk is not its base blob')
    problems += check_arithmetic(data)
    problems += check_dc_reference(data)
    problems += check_deck_consistency(data)
    problems += check_pwl_readback(data)
    problems += check_case_plan(data)
    return problems, data


# ---- offline self test ---------------------------------------------------------------------------

def selftest():
    data = contract()
    results = []

    def record(name, ok, extra=''):
        results.append((name, bool(ok), '' if ok else extra))

    record('a clean contract has no arithmetic problems', not check_arithmetic(data),
           check_arithmetic(data))
    record('the DC reference agrees with the accepted table', not check_dc_reference(data),
           check_dc_reference(data))
    record('the seven frozen decks and three pairs are consistent', not check_deck_consistency(data),
           check_deck_consistency(data))
    record('windows read back from the delivered PWL match the frozen table',
           not check_pwl_readback(data), check_pwl_readback(data))
    record('the case plan is nine authorised NOT_RUN cases', not check_case_plan(data),
           check_case_plan(data))

    def copy():
        return json.loads(json.dumps(data))

    bad = copy()
    bad['charge']['qlsb_nominal_C_by_tick_ns']['120'] = 3.75e-13
    record('a 120 ns QLSB copied from the 200 ns tick is caught',
           any('120 ns QLSB' in text for text in check_arithmetic(bad)), check_arithmetic(bad))

    bad = copy()
    bad['hybrid']['frames'][3]['expected_conducting_intervals'] = 63
    record('F63 read as 63 intervals instead of 64 is caught',
           any('F63' in text for text in check_arithmetic(bad)), check_arithmetic(bad))

    bad = copy()
    bad['probe']['ideal_two_terminal_check']['absolute_tol_V'] = 0.02
    record('the old 20 mV guard reintroduced as the tolerance is caught',
           any('tolerance' in text for text in check_arithmetic(bad)), check_arithmetic(bad))

    bad = copy()
    bad['dc_reference']['idc_A_by_code']['111'] = 1.5e-05
    record('a nominal current substituted for the measured DC reference is caught',
           any('I111' in text for text in check_dc_reference(bad)), check_dc_reference(bad))

    bad = copy()
    bad['dc_reference']['idc_A_by_code']['000'] = 1.875e-06
    record('a rounded nominal one-LSB current in place of IDC(000) is caught',
           any('IDC(000)' in text for text in check_dc_reference(bad)), check_dc_reference(bad))

    bad = copy()
    for row in bad['cases']:
        if row['case_id'] == 'RS-FULL':
            row['maxstep_ns'] = 2.0
    record('a plan maxstep that disagrees with the frozen schedule is caught',
           any('RS-FULL' in text for text in check_deck_consistency(bad)),
           check_deck_consistency(bad))

    bad = copy()
    for row in bad['cases']:
        if row['case_id'] == 'RS-FULL':
            row['tick_ns'] = 200.0
            row['qlsb_nominal_C'] = qlsb_C(200.0)
    record('a fine-step pair that also changed its tick is caught',
           any('tick' in text for text in check_arithmetic(bad)), check_arithmetic(bad))

    bad = copy()
    bad['convergence']['pairs'][0]['maxstep_ns'] = 1.0
    record('a convergence pair carrying its own maxstep is caught',
           any('carries maxstep' in text for text in check_convergence_metadata(bad)),
           check_convergence_metadata(bad))

    bad = copy()
    bad['convergence']['pairs'][0]['refined'] = 'TR-200'
    record('a pair renamed onto the case that has no finer deck is caught',
           any('TR-200' in text for text in check_convergence_metadata(bad)),
           check_convergence_metadata(bad))

    bad = copy()
    for row in bad['cases']:
        if row['case_id'] == 'TR-200':
            row['convergence_partner'] = 'RS-LOW'
    record('TR-200 claiming a convergence partner is caught',
           any('TR-200' in text for text in check_convergence_metadata(bad)),
           check_convergence_metadata(bad))

    bad = copy()
    bad['convergence']['uncovered'] = ['HYB-120 and HYB-200 have no fine-step pair of their own']
    record('dropping the statement that TR-200 has no fine step is caught',
           any('TR-200' in text for text in check_convergence_metadata(bad)),
           check_convergence_metadata(bad))

    text = load('%s/TR-LONG.scs' % PREP_DECK_DIR)
    series = pwl_series(text, 'data_en', 'TR-LONG')
    derived = windows_from_enable(series)
    record('the TR-LONG enable gives eight emission windows',
           len(derived['emission']) == 8, len(derived['emission']))
    record('the first emission window starts at the declared 1050 ns rise50',
           abs(derived['emission'][0][0] - 1050.0) < 1e-9, derived['emission'][0])
    record('the eighth tail runs to the simulation stop',
           abs(derived['off_tail'][7][1] - 13050.0) < 1e-9, derived['off_tail'][7])
    record('every leak window is 100 ns long',
           all(abs(stop - start - TAIL_NS) < 1e-9 for start, stop in derived['leak_last100']),
           derived['leak_last100'])
    record('a pure-off window always starts after its own fall ramp ends',
           all(off[0] >= fall for off, fall in
               zip(derived['pure_off'], [e[1] for e in derived['emission']])), derived['pure_off'])

    tampered = list(series)
    tampered[2] = (tampered[2][0], 1.7999)
    record('a ramp that does not reach the deck high changes the flat readback',
           [seg for seg in level_segments(tampered, LOGIC_HIGH_V)
            if seg[1] - seg[0] > 1e-9] != derived['emission_flat'], '')

    odd = io.open(repo('%s/TR-120.scs' % PREP_DECK_DIR), encoding='utf-8').read()
    broken = odd.replace('wave=[0n 0.000', 'wave=[0n', 1)
    refused = False
    try:
        pwl_series(broken, 'data_en', 'TR-120')
    except Refuse:
        refused = True
    record('a pwl wave with an odd token count is refused, not half read', refused, '')
    upper = io.open(repo('%s/TR-LONG.scs' % PREP_DECK_DIR), encoding='utf-8').read()
    found = pwl_series(upper, 'pam0', 'TR-LONG')
    record('a pwl source is found by the node it drives, not by its instance spelling',
           found is not None and found[0][1] == LOGIC_LOW_V, found)
    record('reading the same node by its instance name returns nothing rather than a guess',
           pwl_series(upper, 'PAM0', 'TR-LONG') is None, '')

    refused = False
    try:
        ns_of('100ps', 'ctx')
    except Refuse:
        refused = True
    record('a pwl time in an undeclared suffix is refused', refused, '')

    lines = case_plan_text().split('\n')
    record('the case plan carries nine rows under a header', len(lines) == 11, len(lines))
    rows = interface_rows()
    record('every cited primitive resolves to a line of its base blob',
           all(row['line_at_base'] != '' or row['resolved_as'] == 'PATH' for row in rows), '')
    loose = ['%s:%s' % (row['module'], row['symbol']) for row in rows
             if row['resolved_as'] == 'FIRST_MENTION_NOT_A_DEFINITION']
    record('every cited symbol resolves to a definition, not a bare mention', not loose, loose[:3])
    record('the interface table covers the reused modules and the frozen sources',
           len(set(row['module'] for row in rows)) >= 10 and len(rows) >= 40,
           '%d rows over %d modules' % (len(rows), len(set(row['module'] for row in rows))))
    record('a reused Pure-specific default is named as not inherited',
           sum(1 for row in rows if row['inheritance_rule'].startswith('DO NOT INHERIT')) >= 4, '')
    global INTERFACES
    saved = list(INTERFACES)
    try:
        INTERFACES = saved + [('scripts/dd1_d7b_measure.py', 'no_such_function_here', 'x', 'y')]
        refused = False
        try:
            interface_rows()
        except Refuse:
            refused = True
        record('a cited symbol the base file does not define is refused', refused, '')
        INTERFACES = saved + [('scripts/no_such_module.py', 'x', 'y', 'z')]
        refused = False
        try:
            interface_rows()
        except Refuse:
            refused = True
        record('a cited module that is not in the base commit is refused', refused, '')
    finally:
        INTERFACES = saved
    record('every plan row is USER_APPROVED and NOT_RUN before native work',
           all('USER_APPROVED,NOT_RUN' in line for line in lines[1:] if line), lines[-1])
    record('the contract renders as valid json', isinstance(json.loads(contract_text()), dict), '')
    return results


def render(data):
    out = ['# DATA-7C-B-TR contract (rendered)', '',
           'Contract state `%s`. Base `%s`, branch `%s`, main kept at `%s`.'
           % (data['contract_state'], data['base_sha'], data['branch'], data['main_sha_kept']), '',
           '## Authorisation', '', '```text']
    out += ['%s=%s' % (key.upper(), value) for key, value in sorted(data['authorisation'].items())]
    out += ['```', '', '## Nine cases', '',
            '| case | source | tick ns | maxstep ns | partner | QLSB C | stop ns | launches |',
            '|---|---|---:|---:|---|---:|---:|---:|']
    for row in data['cases']:
        out.append('| %s | %s | %g | %g | %s | %.6g | %s | %d+%d |'
                   % (row['case_id'], row['source'], row['tick_ns'], row['maxstep_ns'],
                      row['convergence_partner'] or '-', row['qlsb_nominal_C'], row['stop_ns'],
                      row['preflight_launches'], row['dut_launches']))
    out += ['', '## Charge', '', '- `%s`' % data['charge']['qlsb_definition'],
            '- `%s`' % data['charge']['qtarget_nominal'],
            '- `%s`' % data['charge']['qtarget_dc'],
            '- `%s`, frozen limit `%g`' % (data['charge']['error_dynamic_LSB'],
                                           data['charge']['dynamic_frozen_limit']),
            '- `%s`, independent limit `%g`' % (data['charge']['error_nominal_LSB'],
                                                data['charge']['nominal_independent_limit']),
            '- forbidden denominators: ' + '; '.join(data['charge']['forbidden_denominators']),
            '', '## DC reference at 1.20 V', '', '| code | IDC A | Inom A |', '|---|---:|---:|']
    for code in sorted(data['dc_reference']['idc_A_by_code']):
        out.append('| %s | %.10g | %.10g |' % (code, data['dc_reference']['idc_A_by_code'][code],
                                               data['dc_reference']['nominal_A_by_code'][code]))
    out += ['', data['dc_reference']['known_dc_bias'], '', '## Carried followups', '']
    for item in data['carried_followups']:
        out.append('- `%s` (%s): %s' % (item['id'], item['origin'], item['text']))
    out += ['', '## Hybrid frames', '',
            '| frame | cfg_hyb_time | cfg_hyb_pam | expected intervals |', '|---|---:|---:|---:|']
    for row in data['hybrid']['frames']:
        out.append('| %s | %d | %s | %d |' % (row['frame'], row['cfg_hyb_time'], row['cfg_hyb_pam'],
                                              row['expected_conducting_intervals']))
    out.append('| %s | %d | %s | planned %d, measured by the actual fault edge |'
               % (SAFETY_FRAME[0], SAFETY_FRAME[1], SAFETY_FRAME[2], SAFETY_FRAME[3]))
    out += ['', data['hybrid']['frame_F63_note'], '', '## Six stripped masters', '']
    for master in data['deck_rules']['masters']:
        out.append('- `%s` at base `%s`' % (master['path'], master['blob_sha256_at_base']))
    out += ['', '## Convergence', '']
    for pair in data['convergence']['pairs']:
        out.append('- %s (maxstep %g ns) against %s (maxstep %g ns), same %g ns tick, '
                   'abs(dQ)/QLSB <= %g' % (pair['refined'], pair['maxstep_ns'], pair['coarse'],
                                           pair['coarse_maxstep_ns'], pair['tick_ns'], CONV_LIMIT))
    for item in data['convergence']['uncovered']:
        out.append('- not covered: %s' % item)
    out += ['', '## Published separately', '', '```text',
            '\n'.join(data['publication']['statuses']), '```']
    return '\n'.join(out) + '\n'


def main(argv):
    mode = argv[0] if argv else '--check'
    if mode == '--write':
        out = write()
        print('TR_CONTRACT_WRITTEN %s %s' % (out['contract'], out['case_plan']))
        return 0
    if mode == '--render':
        problems, data = check()
        if problems:
            for text in problems:
                print('TR_CONTRACT_REFUSED: %s' % text)
            return 1
        directory = repo(os.path.dirname(CONTRACT_REPORT))
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with io.open(repo(CONTRACT_REPORT), 'wb') as handle:
            handle.write(render(data).encode('utf-8'))
        print('TR_CONTRACT_RENDERED %s' % CONTRACT_REPORT)
        return 0
    if mode == '--interfaces':
        path = write_interfaces()
        print('TR_INTERFACES_WRITTEN %s (%d rows)' % (INTERFACE_PATH, len(interface_rows())))
        return 0
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-62s %s %s' % (name, 'PASS' if ok else 'FAIL', extra))
        print('TR_CONTRACT_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--check':
        problems, data = check()
        for text in problems:
            print('TR_CONTRACT_PROBLEM: %s' % text)
        print('TR_CONTRACT_CHECK %s (%d cases, %d masters, %d pairs)'
              % ('PASS' if not problems else 'FAIL', len(data['cases']),
                 len(data['deck_rules']['masters']), len(data['convergence']['pairs'])))
        return 0 if not problems else 1
    if mode == '--json':
        sys.stdout.write(contract_text())
        return 0
    print('usage: --write | --check | --render | --selftest | --json')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
