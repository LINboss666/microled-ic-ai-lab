# -*- coding: utf-8 -*-
"""SCAN-1 S3-B: the accepted control chain really driving the seven-device output bank.

    python scripts/sc1_s3b_chain_power_tt.py --selftest          # arithmetic only, nothing runs
    python scripts/sc1_s3b_chain_power_tt.py --dry --expect 9    # deck text + plan, scratch only
    python scripts/sc1_s3b_chain_power_tt.py --probe --scratch cadence_work/sc1_sim/s3b_probe
    RUN=1 QODER_SIM_AUTHORISED=1 python scripts/sc1_s3b_chain_power_tt.py --expect 9

The one circuit question: does the whole single-channel scan output still select, blank and re-select
when `gate33` is no longer a capacitor but the gates of seven real p33 devices, and does the external
guard switch it off again. Nine TT cases, one channel, 39 MOS each: the 32 accepted control devices
plus the 7-device bank S3-A measured and picked.

What is NOT done here, and stays undone: no ideal source drives q, qbar, en, gate33, bgate or scan;
no separate VG replaces the chain; no m=/nf=; no artificial 1.5 pF or reused 1/5 pF gate capacitor on
`gate33`; no 5 V, no stack, no LED, no electrode model, no array, no second channel, no corner, no
temperature sweep, no power-fail matrix, no layout. P1/P2/P3 (final VSCAN/VLED, LED Vf or I-V,
N_active) are NOT_DEFINED and cannot be inferred from anything this round measures.

The rules are inherited, not re-invented: the stimulus framework, the window-shape audit and the
10/90 % state convention come from `scripts/sc1_r3_chain_tt.py`, the reader/delay/vtx/call-contract
come from the audited tools, and the bank geometry and the two proxy loads come from the delivered
S3-A deck generator. What is new is only the S3-B gate steady target -- low window max < 0.33 V, high
window min > 2.97 V (10/90 % of 3.3 V, POC_WINDOW_STATE_TARGET, not a rating) -- and the measurement
of three separate current branches plus the real gate-edge charge.

`--probe` exists because the preferred gate current is the sum of the MOS gate terminal currents, but
only terminal 1 has ever been confirmed on this build; assuming another index, or a deeper hierarchical
level, works because :1 did is exactly the kind of guess this project has been burned by. The probe
writes to its own scratch directory, runs one deck, and reports which current names the data file
actually carries. Nothing is claimed from a name that was never read.
"""
from __future__ import print_function

import hashlib
import io
import math
import optparse
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sc1_r2e1_call_contract as CC
import sc1_r2e_s2_tt as S2                      # Run, read_sig, read_diff, delay_cmd, scrub, write_rows
import sc1_r2e1_reread as R1                    # samples_of / crossing_times, the audited interpolator
import sc1_r3_chain_tt as R3                    # the accepted stimulus framework and window rules
import sc1_s3a_p33_tt as S3A                    # the measured candidate: geometry, loads, proxy values

try:
    _text = unicode
except NameError:
    _text = str

V18, V33 = R3.V18, R3.V33
VSCAN = 3.3
STOP_NS = R3.STOP_NS
MAXSTEP_NS = R3.MAXSTEP_NS
MIN_SAMPLES = R3.MIN_SAMPLES
SECTION = 'tt'

# the four reviewed circuit files, byte-for-byte, plus the two new S3-B masters
FROZEN = ('C2MOS_DFF.scs', 'sc1_scan_gate.scs', 'sc1_level_shifter_r2d.scs', 'sc1_r3_scan_chain.scs')
BANK_FILE = 'sc1_s3b_p33_bank.scs'
TOP_FILE = 'sc1_s3b_scan_power_1ch.scs'
FAULT_FILE = 'sc1_s3b_scan_power_1ch_fault.scs'
TOP_MASTER = 'sc1_s3b_scan_power_1ch'
FAULT_MASTER = 'sc1_s3b_scan_power_1ch_fault'
FAULT_CHAIN = 'sc1_s3b_fault_chain_1ch'
CONTROL_DEVS = 32
BANK_DEVS = 7
TOTAL_DEVS = CONTROL_DEVS + BANK_DEVS

# the port name `vscan' is not supply-like to the frozen checker, so it has to be declared explicitly
# and the static gate then has to reach it -- an entry that matches no port is refused by the checker
SUPPLY_MAP = 'vdd=1.8 vdd18=1.8 vdd33=3.3 vscan=3.3 vss=0'
EXPECTED_VDD = '1.8'

# POC_WINDOW_STATE_TARGET for the real gate node, 10/90 % of 3.3 V -- this round's screening pair,
# not a device rating and not a panel requirement
GATE_LO_MAX = 0.33
GATE_HI_MIN = 2.97
# the conditional drop figure S3-A already names; kept conditional, never promoted to a requirement
V_DROP_DRAFT = S3A.V_DROP_DRAFT
RON_TARGET = S3A.RON_TARGET
I_PIXEL = S3A.I_PIXEL
I_COLUMN = S3A.I_COLUMN
N_ACTIVE_ASSUMED = S3A.N_ACTIVE_ASSUMED
LOADS = {'light': S3A.DYN_LOADS[0], 'column': S3A.DYN_LOADS[1]}
EDGE_MARGIN_NS = 20.0            # how far a charge window may reach around a gate33 transition
# a sample counts as "displaced" when its current leaves the baseline band by more than this. The
# psfascii currents this build reads carry noise near 1e-12 A, so a 1 nA floor is three decades of
# margin over the noise and five under the mA-scale peaks it has to catch.
CHARGE_FLOOR_A = 1e-9
RECOVER_NS = 5.0                 # how far to look for the current to settle after the 90 % point
PRE_EDGE_NS = 3.0                # how far before the 10 % point the integration starts
PRE_BAND_NS = 3.0                # the stretch inside it that gives the pre level, and at the end of
                                 # the recovery the post level
POST_SETTLE_NS = 8.0             # the first stretch offered as the post level before extending
# a stretch is only a level when its own range is small against the peak this edge produced; 2 % of
# a mA-scale peak is 20 uA, two decades above the psfascii noise floor and well under the decay the
# bank gates cause, so the criterion catches a still-moving tail without inventing a time constant.
SETTLE_FRACTION = 0.02


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def fmt_v(v):
    return R3.fmt_v(v)


def tnum(t):
    return R3.tnum(t)


def fmt17(v):
    """17 significant digits: a shipped sample must be re-computable, not re-rounded for display"""
    return '%.17g' % v


def win(label, t0, t1, expect, cause=None, plateau=False, off=False, note='', refusable=False):
    w = R3.win(label, t0, t1, expect, cause=cause, note=note, refusable=refusable)
    w['plateau'] = plateau
    w['off'] = off
    return w


def case(cid, **kw):
    kw['id'] = cid
    kw.setdefault('load', 'column')
    kw.setdefault('fault', False)
    kw.setdefault('delays', [])
    kw.setdefault('edges', ['fall', 'rise'])
    return kw


ESTAB = win('established_Q0', 160.0, 190.0, {'q': 'low', 'qbar': 'high'}, cause=150.0, off=True,
            note='after TWO real rising edges (50 and 150 ns) with d=0, blank high, guard low; the '
                 'initialisation is never forced and never rewritten by an ic')

GUARD_ON = [(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33)]
WRITE_1 = [(220.0, 'd', V18)]

CASES = [
    case('s3b_q0_off_light', load='light', actions=GUARD_ON,
         windows=[ESTAB,
                  win('hold_off_250', 270.0, 290.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=250.0,
                      off=True),
                  win('hold_off_450', 470.0, 490.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=450.0,
                      off=True)],
         delays=[], edges=[],
         purpose='the bank off baseline: an initialised Q=0 holds gate33 high with seven real gates '
                 'and a proxy load hanging off the scan node'),
    case('s3b_write_q1_light', load='light', actions=GUARD_ON + WRITE_1,
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('selected_350', 370.0, 390.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=350.0,
                      plateau=True)],
         delays=[('clk_up_to_gate33_down', 'clk', 'rise', V18, 'gate33', 'fall', 245.0, 320.0),
                 ('en_up_to_gate33_down', 'en', 'rise', V18, 'gate33', 'fall', 245.0, 320.0),
                 ('clk_up_to_scan_up', 'clk', 'rise', V18, 'scan', 'rise', 245.0, 340.0)],
         purpose='the light load selected by the real chain: the bank turns on and holds the pixel '
                 'proxy current'),
    case('s3b_write_q1_column', load='column', actions=GUARD_ON + WRITE_1,
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('selected_350', 370.0, 390.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=350.0,
                      plateau=True)],
         delays=[('clk_up_to_gate33_down', 'clk', 'rise', V18, 'gate33', 'fall', 245.0, 320.0),
                 ('clk_up_to_scan_up', 'clk', 'rise', V18, 'scan', 'rise', 245.0, 340.0)],
         purpose='the conditional column proxy selected: the actual drop, the real drive edge and the '
                 'switching-rail current are read together'),
    case('s3b_blank_assert_column', load='column', actions=GUARD_ON + WRITE_1 + [(400.0, 'blank', V18)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('blanked_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=400.0,
                      off=True,
                      note='Q keeps its value: blank acts on the output, it does not clear the store')],
         delays=[('blank_up_to_en_down', 'blank', 'rise', V18, 'en', 'fall', 395.0, 440.0),
                 ('blank_up_to_gate33_up', 'blank', 'rise', V18, 'gate33', 'rise', 395.0, 445.0),
                 ('blank_up_to_scan_down', 'blank', 'rise', V18, 'scan', 'fall', 395.0, 460.0)],
         purpose='blanking a selected channel with the bank present: Q stays 1, gate33 is pulled high, '
                 'the bank turns off'),
    case('s3b_blank_release_column', load='column',
         actions=GUARD_ON + WRITE_1 + [(300.0, 'blank', V18), (500.0, 'blank', 0.0)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('blanked_350', 370.0, 390.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=300.0,
                      off=True),
                  win('released_550', 570.0, 590.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=500.0,
                      plateau=True,
                      note='re-selected without any rewrite: the stored Q was kept while blank was high')],
         delays=[('blank_up_to_gate33_up', 'blank', 'rise', V18, 'gate33', 'rise', 295.0, 345.0),
                 ('blank_down_to_gate33_down', 'blank', 'fall', V18, 'gate33', 'fall', 495.0, 545.0),
                 ('blank_down_to_scan_up', 'blank', 'fall', V18, 'scan', 'rise', 495.0, 560.0)],
         edges=['fall', 'rise'],
         purpose='blank release away from a sampling edge must re-select the real output'),
    case('s3b_write_q0_column', load='column',
         actions=GUARD_ON + [(220.0, 'd', V18), (320.0, 'd', 0.0)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('deselected_350', 370.0, 390.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=350.0,
                      off=True)],
         delays=[('clk_up_to_gate33_up', 'clk', 'rise', V18, 'gate33', 'rise', 345.0, 420.0),
                 ('clk_up_to_scan_down', 'clk', 'rise', V18, 'scan', 'fall', 345.0, 430.0)],
         purpose='a legal write of 0 must carry the real output back off through the whole chain'),
    case('s3b_repeat101_column', load='column',
         actions=GUARD_ON + [(220.0, 'd', V18), (320.0, 'd', 0.0), (420.0, 'd', V18)],
         windows=[ESTAB,
                  win('state_1_after_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('state_0_after_350', 370.0, 390.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=350.0,
                      off=True),
                  win('state_1_after_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=450.0,
                      plateau=True)],
         delays=[('edge1_gate33_down', 'clk', 'rise', V18, 'gate33', 'fall', 245.0, 300.0),
                 ('edge2_gate33_up', 'clk', 'rise', V18, 'gate33', 'rise', 345.0, 400.0),
                 ('edge3_gate33_down', 'clk', 'rise', V18, 'gate33', 'fall', 445.0, 500.0),
                 ('edge1_scan_up', 'clk', 'rise', V18, 'scan', 'rise', 245.0, 320.0),
                 ('edge2_scan_down', 'clk', 'rise', V18, 'scan', 'fall', 345.0, 420.0),
                 ('edge3_scan_up', 'clk', 'rise', V18, 'scan', 'rise', 445.0, 520.0)],
         purpose='three consecutive writes 1 -> 0 -> 1, each output response attributed to its own '
                 'sampling edge and never to the next cycle'),
    case('s3b_guard_cycle_column', load='column',
         actions=GUARD_ON + WRITE_1 + [(400.0, 'core_ok33', 0.0), (600.0, 'core_ok33', V33)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('guarded_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'high'}, cause=400.0,
                      off=True, note='the EXTERNAL guard forces the real gate off WITHOUT changing Q '
                                     'or en'),
                  win('guard_back_650', 670.0, 690.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=600.0,
                      plateau=True)],
         delays=[('guard_down_to_gate33_up', 'core_ok33', 'fall', V33, 'gate33', 'rise', 395.0, 445.0),
                 ('guard_down_to_scan_down', 'core_ok33', 'fall', V33, 'scan', 'fall', 395.0, 460.0),
                 ('guard_up_to_gate33_down', 'core_ok33', 'rise', V33, 'gate33', 'fall', 595.0, 645.0),
                 ('guard_up_to_scan_up', 'core_ok33', 'rise', V33, 'scan', 'rise', 595.0, 660.0)],
         purpose='the external guard closing and reopening a real output current, Q untouched'),
    case('s3b_fault_blank_to_vss_column', load='column', fault=True,
         actions=GUARD_ON + [(220.0, 'd', V18), (400.0, 'blank', V18)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0,
                      plateau=True),
                  win('blanked_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=400.0,
                      off=True, refusable=True,
                      note='the NORMAL blank assertion; with the cell pin tied to vss it must be '
                           'refused by the state numbers')],
         delays=[], edges=[],
         purpose='one functional connection moved: the gate cell BLANK pin sits at vss while the '
                 'external blank source still toggles exactly as in s3b_blank_assert_column'),
]


def find_case(cid):
    for c in CASES:
        if c['id'] == cid:
            return c
    return None


def load_of(case_def):
    name, r, c, why = LOADS[case_def['load']]
    return r, c, why


# ------------------------------------------------------------------ deck
def include_order(case_def):
    files = list(FROZEN) + [BANK_FILE]
    files.append(FAULT_FILE if case_def['fault'] else TOP_FILE)
    return files


DECK_TOP = '''simulator lang=spectre insensitive=yes
// SCAN-1 S3-B one scan channel, control chain plus the 7 x p33 output bank: %s
// model binding comes from the git-ignored spectre/pdk_local.env; run_spectre.sh refuses an
// unexpanded ${QODER_PDK_LIB}, so every deck here is bound before it runs.
include "${QODER_PDK_LIB}" section=%s
'''


def top_instance_line(case_def):
    master = FAULT_MASTER if case_def['fault'] else TOP_MASTER
    return 'Xtop (d clk blank core_ok33 scan vdd18 vdd33 vscan vss) %s\n' % master


def build_deck(case_def, section=SECTION, extra_saves=(), gate_term=False, gate_all=False):
    r, c, _why = load_of(case_def)
    lines = [DECK_TOP % (case_def['purpose'], section)]
    for f in include_order(case_def):
        lines.append('include "%s"\n' % f)
    lines.append('// temperature is read back from the produced log and the psf header; the instantiation\n'
                 '// form is what this build accepts (a bare `options temp=27\' is SFE-709).\n'
                 'simopt options temp=%s\n' % S3A.TEMP_C)
    # ---- the accepted R3 stimulus, generated by the accepted R3 functions
    lines.append('Vd (d 0) vsource dc=0 type=pwl wave=%s\n' % R3.wave(
        [(0.0, 0.0)] + [(t, v) for t, s, v in sorted(case_def['actions']) if s == 'd']))
    lines.append('Vclk (clk 0) vsource dc=0 type=pwl wave=%s\n' % R3.clk_wave())
    lines.append('Vbl (blank 0) vsource dc=%s type=pwl wave=%s\n' % (
        fmt_v(V18), R3.wave([(0.0, V18)] + [(t, v) for t, s, v in sorted(case_def['actions'])
                                                       if s == 'blank'])))
    lines.append('Vok (core_ok33 0) vsource dc=0 type=pwl wave=%s\n' % R3.wave(
        [(0.0, 0.0)] + [(t, v) for t, s, v in sorted(case_def['actions']) if s == 'core_ok33']))
    # ---- three independent measurement rails at two declared potentials; see the deck comment
    lines.append('// V18 drives the 1.8 V domain, V33 the control chain\'s high domain, VSCAN the bank\n'
                 '// source/body rail. V33 and VSCAN are BOTH 3.3 V: this is one testbench potential\n'
                 '// split into two branches so switching current and control current can be counted\n'
                 '// apart -- it does not add a product voltage. Every rail is a direct source to the 0 V\n'
                 '// reference (Vss(vss 0) dc=0), which is what the supply contract certifies.\n')
    lines.append('V18 (vdd18 0) vsource dc=%s\n' % fmt_v(V18))
    lines.append('V33 (vdd33 0) vsource dc=%s\n' % fmt_v(V33))
    lines.append('VSCAN (vscan 0) vsource dc=%s\n' % fmt_v(VSCAN))
    lines.append('Vss (vss 0) vsource dc=0\n')
    lines.append('// the real chain, and nothing else, drives gate33 -> bgate -> the seven device gates;\n'
                 '// no ideal source touches q, qbar, en, gate33, bgate or the scan node, and no separate\n'
                 '// VG instrument replaces the level shifter. No capacitor hangs on gate33 either: the\n'
                 '// gate load is the bank plus the zero-drop measurement branch inside the top.\n')
    lines.append(top_instance_line(case_def))
    lines.append('// TESTBENCH_ASSUMPTION proxy load on the SCAN node (not an electrode): r=%s ohm,\n'
                 '// c=%s F from scan to vss, the same two values S3-A wrote.\n' % (fmt_v(r), fmt_v(c)))
    lines.append('Rload (scan vss) resistor r=%s\n' % fmt_v(r))
    lines.append('Cload (scan vss) capacitor c=%s\n' % fmt_v(c))
    lines.append('\nsw1 tran stop=%s maxstep=%sn\n' % (tnum(STOP_NS), fmt_v(MAXSTEP_NS)))
    lines.append('save d clk blank core_ok33 scan vdd18 vdd33 vss\n')
    lines.append('save Xtop.Xchain.q Xtop.Xchain.qbar Xtop.Xchain.en Xtop.gate33 Xtop.bgate\n')
    lines.append('// injected = -(Vsource:i) is the sign rule this build calibrated in R2E; the three\n'
                 '// branches are kept apart: VSCAN:i switches the bank, V33:i feeds the control chain\'s\n'
                 '// high domain, V18:i the 1.8 V domain.\n')
    lines.append('save VSCAN:i V33:i V18:i\n')
    lines.append('// the gate branch current: the iprobe inside the top. The drain currents of the seven\n'
                 '// devices are the confirmed `mp<k>:1'
                 "' form from S3-A; anything else is only saved once the probe has read it.\n")
    lines.append('save Xtop.Ip_gate:i\n')
    for k in range(1, BANK_DEVS + 1):
        lines.append('save Xtop.Xbank.mp%d:1\n' % k)
    if gate_term:
        for k in (1, 2):
            lines.append('save Xtop.Xbank.mp%d:2\n' % k)
    if gate_all:
        for k in range(1, BANK_DEVS + 1):
            lines.append('save Xtop.Xbank.mp%d:2\n' % k)
    for s in extra_saves:
        lines.append('save %s\n' % s)
    return ''.join(lines)


def deck_diff(ref_txt, fault_txt):
    """the deck-level proof: only the included master and its instance name differ"""
    import difflib
    a, b = ref_txt.split('\n'), fault_txt.split('\n')
    stmts, comments = [], []
    for l in difflib.unified_diff(a, b, lineterm='', n=0):
        if l.startswith('---') or l.startswith('+++'):
            continue
        if not (l.startswith('-') or l.startswith('+')):
            continue
        body = l[1:].strip()
        if body.startswith('//') or body == '':
            comments.append(l)
        else:
            stmts.append(l)
    return stmts, comments


def instance_lines(text):
    """{instance: (nets, master)} for the subckt body of a master file"""
    out = {}
    for m in re.finditer(r'^\s*(X\w+)\s*\(([^)]*)\)\s*(\w+)', text, re.M):
        out[m.group(1)] = ([n.strip() for n in m.group(2).split() if n.strip()], m.group(3))
    return out


def fault_proof():
    """compare the faulted top's three chain instances with the reviewed wrapper's own three lines

    This is the strongest statement the wiring fault admits at netlist level: the same three instances,
    the same masters, the same port counts, and exactly one argument changed from `blank' to `vss'.
    """
    ref = instance_lines(masters_text(['sc1_r3_scan_chain.scs'])
                         .split('subckt sc1_r3_scan_chain_1ch')[-1])
    fault = instance_lines(masters_text([FAULT_FILE]).split('subckt %s' % FAULT_CHAIN)[-1])
    want = {'Xff': ('c2mos_dff', 6), 'Xgate': ('sc1_scan_gate', 5),
            'Xls': ('sc1_ls_c1_top_r2d', 6)}
    diffs, problems = [], []
    for inst, (master, np) in want.items():
        if inst not in ref or inst not in fault:
            problems.append('%s missing from ref=%s fault=%s' % (inst, ref.keys(), fault.keys()))
            continue
        rn, rm = ref[inst]
        fn, fm = fault[inst]
        if rm != master or fm != master or len(rn) != np or len(fn) != np:
            problems.append('%s master/port-count changed (%s/%s vs %s/%s)' % (inst, rm, len(rn),
                                                                              fm, len(fn)))
            continue
        changed = [(k, rn[k], fn[k]) for k in range(np) if rn[k] != fn[k]]
        if changed:
            diffs.append((inst, changed))
    one = (len(diffs) == 1 and diffs[0][0] == 'Xgate' and len(diffs[0][1]) == 1
           and diffs[0][1][0][1:] == ('blank', 'vss'))
    return diffs, problems, one


# ------------------------------------------------------------------ static identity
def masters_text(files):
    txt = ''
    for f in files:
        txt += u(io.open(os.path.join(PROJ, 'spectre', f), encoding='utf-8', errors='replace').read()) \
            + '\n'
    return txt


def cell_hashes(case_def):
    out = []
    for f in include_order(case_def):
        b = open(os.path.join(PROJ, 'spectre', f), 'rb').read()
        out.append((f, hashlib.sha256(b).hexdigest(), len(b)))
    return out


def bank_geometry():
    """read the bank's own device lines back out of the file the simulator includes"""
    txt = masters_text([BANK_FILE])
    widths = re.findall(r'^\s*mp\d+\s*\([^)]*\)\s*p33\b[^/\n]*?\bw=([0-9.eE+-]+)', txt, re.M)
    lens = re.findall(r'^\s*mp\d+\s*\([^)]*\)\s*p33\b[^/\n]*?\bl=([0-9.eE+-]+)', txt, re.M)
    return widths, lens


# ------------------------------------------------------------------ measurement
def sig_path(sig):
    """the saved name of a signal in an S3-B deck

    q, qbar and en are one level deeper than the top here: the probe deck proved the data file carries
    `Xtop.Xchain.q` and no `Xtop.q` at all, so the chain nets have to be named through Xchain while
    gate33 / bgate / scan are nets of the top itself.
    """
    if sig in ('d', 'clk', 'blank', 'core_ok33', 'scan', 'vdd18', 'vdd33', 'vscan', 'vss'):
        return sig
    if sig in ('q', 'qbar', 'en'):
        return 'Xtop.Xchain.%s' % sig
    return 'Xtop.%s' % sig


def level_pair(sig):
    """the screening pair a whole-window claim is judged against"""
    if sig == 'gate33':
        return GATE_LO_MAX, GATE_HI_MIN, ('S3-B POC_WINDOW_STATE_TARGET: 10/90 %% of the 3.3 V gate '
                                          '(%s V high min / %s V low max), a this-round window target '
                                          'and not a device rating' % (fmt_v(GATE_HI_MIN),
                                                                       fmt_v(GATE_LO_MAX)))
    if sig == 'bgate':
        return GATE_LO_MAX, GATE_HI_MIN, 'same target as gate33: the iprobe is zero-drop, and the ' \
                                        'deck shows the two nets agree'
    dom = R3.DOMAIN.get(sig, V18)
    return 0.5 * dom, 0.5 * dom, 'the %.1f V domain 50%% level' % dom


def measure_window(R, cid, data, w):
    """the audited R3 rule -- whole window, min for a high claim, max for a low claim -- new paths"""
    for sig, want in sorted(w['expect'].items()):
        t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
        path = sig_path(sig)
        rcn, mn = S2.read_sig(R, data, path, 'min', t0, t1, req=str(MIN_SAMPLES))
        rcx, mx = S2.read_sig(R, data, path, 'max', t0, t1, req=str(MIN_SAMPLES))
        if rcn != 0 or rcx != 0:
            R.add('S3B_WINDOW_STATE', cid, '%s @ %s' % (path, w['label']),
                  'window min and max readable with >= %d samples' % MIN_SAMPLES,
                  (mn if rcn else mx)[:70], rcn or rcx, 'BLOCKED',
                  'reader exit kept; a state is never inferred from a label')
            continue
        a, b = float(mn), float(mx)
        lo_t, hi_t, how = level_pair(sig)
        ok = (a >= hi_t) if want == 'high' else (b <= lo_t)
        verdict = 'PASS' if ok else ('EXPECTED_REFUSAL' if w.get('refusable') else 'FAIL')
        R.add('S3B_WINDOW_STATE', cid, '%s @ %s' % (path, w['label']),
              '%s throughout: %s' % (want, how), 'min=%.6g max=%.6g V' % (a, b), 0, verdict,
              'whole window %s..%s s over every sample in it, not one extreme frame%s'
              % (t0, t1, '; this is the claim the wiring fault must fail'
                 if w.get('refusable') else ''))


def measure_plateau(R, cid, data, w, case_def):
    """the output platform: the scan node, the switch's own VSD, the current it really carries"""
    r, _c, _why = load_of(case_def)
    t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
    rcn, mn = S2.read_sig(R, data, 'scan', 'min', t0, t1, req=str(MIN_SAMPLES))
    rcx, mx = S2.read_sig(R, data, 'scan', 'max', t0, t1, req=str(MIN_SAMPLES))
    if rcn or rcx:
        R.add('S3B_PLATEAU', cid, 'scan @ %s' % w['label'], 'the selected platform readable',
              (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
              'no plateau is written from a window the reader refused')
        return
    vlo, vhi = float(mn), float(mx)
    vsd_lo, vsd_hi = VSCAN - vhi, VSCAN - vlo
    i_lo, i_hi = vlo / r, vhi / r
    on = vsd_lo > 1e-9 and i_lo > 0.0
    R.add('S3B_PLATEAU', cid, 'scan @ %s' % w['label'],
          'scan min/max, the device own VSD = VSCAN - V(scan), and the load current V(scan)/R',
          'scan=%.6g..%.6g V ; VSD=%.6g..%.6g V ; I_load=%.6g..%.6g A (R=%s)'
          % (vlo, vhi, vsd_lo, vsd_hi, i_lo, i_hi, fmt_v(r)), 0, 'MEASURED',
          'I_load is the declared bench resistor reading, derived from the measured node voltage; '
          'the branch currents are separate rows')
    if on:
        ron_lo, ron_hi = vsd_lo / i_hi, vsd_hi / i_lo
        R.add('S3B_RON_PLATFORM', cid, 'Ron over %s' % w['label'],
              'the switch own source-drain drop divided by its own current, only while the current '
              'is nonzero and the plateau is flat',
              'Ron=%.6g..%.6g ohm (VSD=%.6g V, I=%.6g..%.6g A)'
              % (ron_lo, ron_hi, vsd_lo, i_lo, i_hi), 0, 'MEASURED',
              'zero-current windows are NOT_DEFINED here, never 0 ohm; this excludes the load '
              'resistor and the rail drop')
    else:
        R.add('S3B_RON_PLATFORM', cid, 'Ron over %s' % w['label'],
              'a nonzero plateau current is needed to form a resistance',
              'VSD=%.6g V I=%.6g A' % (vsd_lo, i_lo), 0, 'NOT_DEFINED',
              'no current, no resistance: left undefined instead of filled in')
    if case_def['load'] == 'column':
        drop = vsd_hi
        ok = drop < V_DROP_DRAFT
        R.add('S3B_DROP_TARGET', cid, 'platform drop vs the conditional 0.10 V figure @ %s' % w['label'],
              'CONDITIONAL_DRAFT_TARGET: 0.10 V under the assumed %s mA column current (768 pixels '
              'is an architecture assumption, 15 uA is one pixel)' % fmt_v(I_COLUMN * 1e3),
              'VSD_max=%.6g V ; target %.6g V ; one pixel would be %.6g A'
              % (drop, V_DROP_DRAFT, I_PIXEL), 0,
              'PASS' if ok else 'CONDITIONAL_DROP_TARGET_NOT_MET',
              'the logical result stands either way; this round cannot turn a draft figure into a '
              'requirement, and 11.52 mA is not a decided N_active')


def measure_off(R, cid, data, w, case_def):
    """off state: the control state first, then whatever branch current is actually readable"""
    r, _c, _why = load_of(case_def)
    t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
    rcn, mn = S2.read_sig(R, data, 'scan', 'min', t0, t1, req=str(MIN_SAMPLES))
    rcx, mx = S2.read_sig(R, data, 'scan', 'max', t0, t1, req=str(MIN_SAMPLES))
    if rcn or rcx:
        R.add('S3B_OFF_STATE', cid, 'scan @ %s' % w['label'], 'the off window readable',
              (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE', 'nothing reported from a '
                                                                    'window the reader refused')
        return
    vlo, vhi = float(mn), float(mx)
    i_lo, i_hi = vlo / r, vhi / r
    R.add('S3B_OFF_STATE', cid, 'scan @ %s' % w['label'],
          'the gate and control state is judged by the window rows; the node voltage and the '
          'load-branch current are read here',
          'scan=%.6g..%.6g V ; I(scan->vss through R)=%.6g..%.6g A ; VSD=%.6g..%.6g V'
          % (vlo, vhi, i_lo, i_hi, VSCAN - vhi, VSCAN - vlo), 0, 'MEASURED',
          'a transient branch current during a transition is NOT channel leakage, and no leakage '
          'budget exists (the draft 0.1 uA is a reference, not a signoff line); a node that is still '
          'floating or discharging is not required to be at 0 V')


def measure_delays(R, cid, groups, axis, data, case_def):
    """clk/blank/guard -> gate33 and -> scan, measured directly; never a sum of block delays"""
    for label, sin, ein, vin, sout, eout, t0, t1 in case_def['delays']:
        p_in, p_out = sig_path(sin), sig_path(sout)
        vout_dom = R3.DOMAIN.get(sout, V33 if sout == 'gate33' else V18)
        if sout == 'scan':
            vout_dom = VSCAN
        cmd = ('%s --data "%s" --mode propdelay --sig-in "%s" --sig-out "%s" --vdd-in %s '
               '--vdd-out %s --edge-in %s --edge-out %s --t0 %.9g --t1 %.9g'
               % (S2.delay_cmd(), data, p_in, p_out, fmt_v(vin), fmt_v(vout_dom), ein, eout,
                  t0 * 1e-9, t1 * 1e-9))
        rc, out = CC.call(cmd)
        head = S2.scrub(out.strip().split('\n')[0]).replace('\n', ' | ')
        answered = rc == 0 and head.startswith('PROPDELAY')
        overlap = ('AMBIGUOUS_RESOLUTION' in out) or ('OUTSIDE_ATTRIBUTION' in out)
        refused = any(k in out for k in ('NO_RESPONSE', 'NO_EDGE', 'NO_HALF_CROSSING'))
        verdict = ('PASS' if answered else ('NOT_MEASURED_OVERLAP' if overlap
                                           else ('NOT_MEASURED' if refused else 'BLOCKED')))
        R.add('S3B_PROPDELAY', cid, '%s (%s..%s ns)' % (label, tnum(t0), tnum(t1)),
              'an answer attributed to this input edge, inside its own window', head, rc,
              verdict, S2.scrub(out).replace('\n', ' | '))
        propagation_5050(R, cid, groups, axis, label, sin, sout, vin, vout_dom, ein, eout, t0, t1)


def propagation_5050(R, cid, groups, axis, label, sin, sout, vin, vout, ein, eout, t0, t1):
    p_in, p_out = sig_path(sin), sig_path(sout)
    xs_in = R1.crossing_times(groups, axis, p_in, 0.5 * vin)
    xs_out = R1.crossing_times(groups, axis, p_out, 0.5 * vout)
    hit_in = R3._near(xs_in, t0 * 1e-9)
    if not hit_in:
        R.add('S3B_PROPAGATION_50_50', cid, label, 'an input 50% crossing at or after %s ns'
              % tnum(t0), 'NONE_IN_WINDOW', 0, 'NOT_MEASURED',
              'nothing is measured from a window that contains no input edge')
        return
    tin = hit_in[1]
    nxt = R3._next_after(xs_in, tin)
    hit_out = R3._near(xs_out, tin)
    if not hit_out:
        R.add('S3B_PROPAGATION_50_50', cid, label, 'an output 50% crossing at or after t_in',
              'NONE_AFTER_T_IN t_in=%.9g s ; the output never reached its 50%% level after this '
              'input edge' % tin, 0, 'NOT_MEASURED',
              'for the scan node this is charge behaviour (the proxy RC), not a logic failure, and '
              'no delay is invented for it')
        return
    tout = hit_out[1]
    lo_frac = 0.10 if eout == 'rise' else 0.90
    xs_on = R1.crossing_times(groups, axis, p_out, lo_frac * vout)
    onset = R3._near(xs_on, tout, after_only=False)
    inside = (nxt is None) or (tout < nxt[1] - 1e-15)
    R.add('S3B_PROPAGATION_50_50', cid, label,
          't_out - t_in between the two 50 % crossings, attributed inside [t_in, t_next)',
          't_in=%.9g t_out=%.9g delta=%.3f ns ; t_next=%s ; output 10%% onset=%s'
          % (tin, tout, (tout - tin) * 1e9, ('%.9g' % nxt[1]) if nxt else 'END_OF_DATA',
             ('%.9g' % onset[1]) if onset else '?'), 0,
          'MEASURED' if inside else 'OUT_OF_ATTRIBUTION',
          'interpolated from the saved samples; onset %s t_in, which is why the audited event-order '
          'test refuses a certified delay here' % ('precedes' if (onset and onset[1] < tin)
                                                   else 'follows'))


def measure_edges(R, cid, data, case_def):
    """the real 10-90% times of gate33 in both directions, plus the scan node where it truly swings"""
    want = set(case_def.get('edges') or [])
    for sig, dom in (('gate33', V33), ('scan', VSCAN)):
        for edge in ('rise', 'fall'):
            if sig == 'gate33' and edge not in want:
                R.add('S3B_EDGE', cid, '%s %s' % (sig, edge),
                      'not defined by this timeline',
                      'the case list declares which output edges its own stimulus produces', 0,
                      'EXPECTED_REFUSAL', 'the edge tool is not asked for an edge nobody stimulates')
                continue
            cmd = ('%s --data "%s" --sig "%s" --vdd %s --mode edge --edge %s --t0 %.9g --t1 %.9g'
                   % (S2.delay_cmd(), data, sig_path(sig), fmt_v(dom), edge, 200e-9, STOP_NS * 1e-9))
            rc, out = CC.call(cmd)
            head = S2.scrub(out.strip().split('\n')[0]).replace('\n', ' | ')
            ok = rc == 0 and head.startswith('EDGE')
            nodata = ('NO_EDGE' in out) or ('NO_RESPONSE' in out) or ('NO_EDGE' in head)
            R.add('S3B_EDGE', cid, '%s %s over the run' % (sig_path(sig), edge),
                  'a complete 10-90 % event', head, rc,
                  'PASS' if ok else ('NOT_MEASURED' if nodata else 'BLOCKED'),
                  S2.scrub(out).replace('\n', ' | '))


def measure_branches(R, cid, data):
    """three separate current branches, with the instant of each extreme"""
    t0, t1 = '%.9g' % (200e-9), '%.9g' % (STOP_NS * 1e-9)
    names = (('VSCAN:i', 'bank source/body rail: the switching current itself'),
             ('V33:i', 'control chain high domain'),
             ('V18:i', 'the 1.8 V domain'),
             ('Xtop.Ip_gate:i', 'the gate33 -> bank gate branch'))
    for src, why in names:
        rcn, mn = S2.read_sig(R, data, src, 'min', t0, t1, req=str(MIN_SAMPLES))
        rcx, mx = S2.read_sig(R, data, src, 'max', t0, t1, req=str(MIN_SAMPLES))
        if rcn or rcx:
            R.add('S3B_BRANCH_CURRENT', cid, src, 'direct source-branch current readable',
                  (mn if rcn else mx)[:70], rcn or rcx, 'NOT_MEASURED',
                  'kept as a save/read failure; %s. Nothing is substituted and nothing is zeroed'
                  % why)
            continue
        R.add('S3B_BRANCH_CURRENT', cid, src, 'injected = -(Vsource:i); %s' % why,
              'min=%.6g max=%.6g A ; injected %.6g..%.6g A'
              % (float(mn), float(mx), -float(mx), -float(mn)), 0, 'MEASURED',
              'raw signed readings kept; no current or power budget exists for this POC, so no '
              'limit is invented and the switching peak is never charged to gate33')
        for mode in ('max', 'min'):
            rcd, val, txt = S2.read_diff(R, data, src, 'vss', mode, t0, t1)
            parts = (txt or '').split('\t')
            R.add('S3B_BRANCH_PEAK', cid, '%s %s over the run' % (src, mode),
                  'the extreme and the sample time it happened at, from the strict tool',
                  'value=%s A at t=%s s' % (parts[0], parts[1] if len(parts) > 1 else '?'), rcd,
                  'MEASURED' if not rcd else 'NOT_MEASURED',
                  'raw signed reading; injected = -value')


def gate_current_names(groups):
    """which current traces the data file really carries -- read off the parsed groups, not assumed"""
    keys = set(groups[0].keys()) if groups else set()
    probe = {'iprobe': 'Xtop.Ip_gate:i', 'drain1': 'Xtop.Xbank.mp1:1', 'gate2_1': 'Xtop.Xbank.mp1:2'}
    seen = dict((k, (v in keys)) for k, v in probe.items())
    seen['drains'] = all(('Xtop.Xbank.mp%d:1' % i) in keys for i in range(1, BANK_DEVS + 1))
    return seen, sorted(keys)


def traj(xs, ys):
    return sum(0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))


def getter_for(key):
    """how to read one gate-current source out of a parsed sample group"""
    if key == 'terminal_sum':
        drains = ['Xtop.Xbank.mp%d:2' % k for k in range(1, BANK_DEVS + 1)]

        def g_(g):
            vals = [g.get(d) for d in drains]
            return sum(vals) if all(v is not None for v in vals) else None
        return g_
    return lambda g: g.get(key)


def band_of(groups, times, key, t0, t1):
    """(n, min, max, mean) of one current source over a stretch, or None when too few samples

    The mean is the level the displacement sits on; the min and max are kept because a stretch whose
    own range is still wide is not a level at all, and the caller has to say so.
    """
    get = getter_for(key)
    vals = [get(g) for g, t in zip(groups, times) if t0 - 1e-18 <= t <= t1 + 1e-18]
    vals = [v for v in vals if v is not None]
    if len(vals) < 3:
        return None
    return (len(vals), min(vals), max(vals), sum(vals) / len(vals))


def level_crossings(groups, axis, path, lvl):
    """every crossing of one level, tagged with the direction it happened in: (t, 'up'|'down', i)"""
    out = []
    for i, t in R1.crossing_times(groups, axis, path, lvl):
        cur = groups[i].get(path)
        prev = groups[i - 1].get(path) if i > 0 else cur
        if cur is None or prev is None:
            continue
        out.append((t, 'up' if cur > prev else 'down', i))
    return out


def gate_edge_events(groups, axis, lvl):
    """every real 50% crossing of gate33 in the run, with its direction, from the saved samples"""
    xs = R1.crossing_times(groups, axis, 'Xtop.gate33', lvl)
    out = []
    for i, t in xs:
        prev = groups[i - 1]['Xtop.gate33'] if i > 0 else groups[i]['Xtop.gate33']
        out.append((t, 'fall' if groups[i]['Xtop.gate33'] < prev else 'rise', i))
    return out


def measure_device_voltages(R, cid, groups, axis, case_def):
    """VGS/VGD/VDS/VGB from D/G/S/B at the same instants; a range check, never an SOA claim"""
    if not groups or 'Xtop.bgate' not in groups[0] or 'scan' not in groups[0]:
        R.add('S3B_DEVICE_VOLTAGES', cid, 'the bank device terminals',
              'D/G/S/B all saved', 'MISSING_NETS', 0, 'NOT_MEASURED',
              'no terminal voltage is reported from nets that were not saved')
        return
    vgs = [(g[axis], g['Xtop.bgate'] - VSCAN) for g in groups if g.get('Xtop.bgate') is not None]
    vgd = [(g[axis], g['Xtop.bgate'] - g['scan']) for g in groups
           if g.get('Xtop.bgate') is not None and g.get('scan') is not None]
    vds = [(g[axis], g['scan'] - VSCAN) for g in groups if g.get('scan') is not None]
    vgb = vgs                                   # S and B are the same net in this bank
    same = [(g[axis], g['Xtop.gate33'] - g['Xtop.bgate']) for g in groups
            if g.get('Xtop.gate33') is not None and g.get('Xtop.bgate') is not None]
    worst = max([abs(v) for _t, v in same] or [0.0])
    R.add('S3B_IPROBE_ZERO_DROP', cid, 'Xtop.gate33 minus Xtop.bgate over the run',
          'the measurement branch drops no voltage, so the bank sees what the chain drives',
          'max|V(gate33)-V(bgate)|=%.6g V over %d samples' % (worst, len(same)), 0,
          'PASS' if worst < 1e-6 else 'FAIL',
          'the iprobe is a current meter, not a logic level; if the two nets disagreed the branch '
          'would not be neutral and the reading would be withdrawn')
    for name, series in (('VGS', vgs), ('VGD', vgd), ('VDS', vds), ('VGB', vgb)):
        if not series:
            R.add('S3B_DEVICE_VOLTAGES', cid, name, 'a readable terminal difference', 'NO_SAMPLES',
                  0, 'NOT_MEASURED', 'nothing reported')
            continue
        vs = [v for _t, v in series]
        R.add('S3B_DEVICE_VOLTAGES', cid, '%s over the run (representative device)' % name,
              'min/max of the terminal difference; all seven share the four nets, so they are '
              'equal by connection and the per-device currents above test the sharing',
              'min=%.6g V max=%.6g V' % (min(vs), max(vs)), 0, 'MEASURED',
              'a geometry/voltage range inside the model limits is NOT an absolute-rating check; '
              'SOA_SIGNOFF stays NO')


# ------------------------------------------------------------------ the wiring fault
REF_BLANK_CASE = 's3b_blank_assert_column'


def datafile_for(scratch, cid):
    p = os.path.join(scratch, 'sim', '%s.raw' % cid, 'sw1.tran.tran')
    return p if os.path.isfile(p) else ''


def negative_report(R, cid, data, case_def, scratch):
    """the fault must be caught by state numbers while preflight, Spectre and the reader all succeed

    A reader crash, a model error or a blocked run is not a detection: this row only says DETECTED
    when the reference case's window would pass and this deck's same window demonstrably does not,
    with every rc on this case still zero.
    """
    ws = [w for w in case_def['windows'] if w.get('refusable')]
    if not ws:
        return
    w = ws[0]
    t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
    reads = (('Xtop.gate33', 'min'), ('Xtop.gate33', 'max'), ('blank', 'min'), ('blank', 'max'),
             (sig_path('q'), 'min'), (sig_path('q'), 'max'),
             (sig_path('qbar'), 'min'), (sig_path('qbar'), 'max'),
             (sig_path('en'), 'min'), (sig_path('en'), 'max'))
    vals, bad = {}, []
    for path, mode in reads:
        rc, txt = S2.read_sig(R, data, path, mode, t0, t1, req=str(MIN_SAMPLES))
        if rc != 0:
            bad.append('%s %s rc=%s' % (path, mode, rc))
            continue
        vals[(path, mode)] = txt
    if bad:
        R.add('S3B_FAULT_NEGATIVE', cid, w['label'], 'every signal of the judgement readable',
              'unreadable: %s' % ' ; '.join(bad), 1, 'BLOCKED',
              'the fault cannot be claimed detected from numbers that were not read; naming the '
              'failed read is the point, not hiding it behind a generic message')
        return
    gmn = float(vals[('Xtop.gate33', 'min')])
    gmx = float(vals[('Xtop.gate33', 'max')])
    bmn = float(vals[('blank', 'min')])
    bmx = float(vals[('blank', 'max')])
    qmin = float(vals[(sig_path('q'), 'min')])
    qmax = float(vals[(sig_path('q'), 'max')])
    emin = float(vals[(sig_path('en'), 'min')])
    emax = float(vals[(sig_path('en'), 'max')])
    ref = datafile_for(scratch, REF_BLANK_CASE)
    if not ref:
        R.add('S3B_FAULT_NEGATIVE', cid, '%s @ %s' % ('Xtop.gate33', w['label']),
              'the same window read from the accepted %s deck, so the fault is a difference and not '
              'an absolute level' % REF_BLANK_CASE,
              'reference deck not present in this scratch: %s' % REF_BLANK_CASE, 1, 'BLOCKED',
              'without the reference window there is nothing to be different from, and a fault is '
              'never claimed from an uncontrasted reading')
        return
    rr1, rgmn = S2.read_sig(R, ref, 'Xtop.gate33', 'min', t0, t1, req=str(MIN_SAMPLES))
    rr2, rgmx = S2.read_sig(R, ref, 'Xtop.gate33', 'max', t0, t1, req=str(MIN_SAMPLES))
    if rr1 != 0 or rr2 != 0:
        R.add('S3B_FAULT_NEGATIVE', cid, '%s @ %s' % ('Xtop.gate33', w['label']),
              'gate33 of the reference %s deck over the same window, readable with the same strict '
              'reader' % REF_BLANK_CASE, 'reference read rc=%s/%s' % (rr1, rr2), 1, 'BLOCKED',
              'the contrast is part of the claim, so a failed reference read blocks the verdict')
        return
    rgmn, rgmx = float(rgmn), float(rgmx)
    # the polarity the accepted cells force: en = NOR(qbar, blank), so a pin tied to vss means the
    # blank never reaches the gate -- en follows q, and gate33 stays at the conducting level while
    # the reference deck, whose pin does see the blank, holds gate33 high.
    blank_held = bmn >= 0.5 * V18 and bmx >= 0.5 * V18
    q_written = qmin >= 0.5 * V18
    en_follows_q = emin >= 0.5 * V18
    gate_conducting = gmx < GATE_LO_MAX
    ref_blocked = rgmn >= GATE_HI_MIN
    conds = [('the external blank source is held at its blanking level over the window', blank_held),
             ('the stored bit is still written', q_written),
             ('en is not suppressed, because the pin never sees the blank', en_follows_q),
             ('gate33 sits at the conducting level', gate_conducting),
             ('the same window of %s holds gate33 high' % REF_BLANK_CASE, ref_blocked)]
    detected = all(v for _k, v in conds)
    R.add('S3B_FAULT_NEGATIVE', cid, '%s @ %s' % ('Xtop.gate33', w['label']),
          'the external blank source stays at %s V across the window while the cell pin is tied to '
          'vss, so the blank cannot reach the gate: gate33 must stay conducting and Q/en must stay '
          'written, which is the opposite of the accepted %s deck at the same window'
          % (fmt_v(bmn), REF_BLANK_CASE),
          'gate33 min=%.6g max=%.6g V ; blank min=%.6g max=%s V ; q min=%.6g max=%.6g V ; '
          'en min=%.6g max=%.6g V ; %s gate33 min=%.6g max=%.6g V ; %s'
          % (gmn, gmx, bmn, fmt_v(bmx), qmin, qmax, emin, emax, REF_BLANK_CASE, rgmn, rgmx,
             ' ; '.join('%s=%s' % (k, 'yes' if v else 'NO') for (k, v) in conds)), 0,
          'DETECTED' if detected else 'NOT_DETECTED',
          'read with the same strict reader as every other case; preflight rc, spectre rc and reader '
          'rc are all zero here, so this is a circuit result and not a harness artefact. Every '
          'condition is printed with its verdict so the decision can be re-made from the numbers')


# ------------------------------------------------------------------ reviewer samples
SHIP_NODES = (('scan', 'scan', VSCAN), ('gate33', 'Xtop.gate33', V33),
              ('bgate', 'Xtop.bgate', V33), ('en', 'Xtop.Xchain.en', V18),
              ('q', 'Xtop.Xchain.q', V18), ('qbar', 'Xtop.Xchain.qbar', V18),
              ('blank', 'blank', V18), ('clk', 'clk', V18),
              ('core_ok33', 'core_ok33', V33), ('vscan', 'vscan', VSCAN),
              ('Ip_gate', 'Xtop.Ip_gate:i', None), ('VSCAN_i', 'VSCAN:i', None),
              ('V33_i', 'V33:i', None), ('V18_i', 'V18:i', None))
# every finger's gate current is shipped, because that sum is the preferred charge reading and the
# reviewer has to be able to rebuild it from the rows rather than from a single branch meter
SHIP_NODES += tuple(('mp%d_g' % k, 'Xtop.Xbank.mp%d:2' % k, None) for k in
                    range(1, BANK_DEVS + 1))
SHIP_NODES += (('mp1_d', 'Xtop.Xbank.mp1:1', None), ('mp7_d', 'Xtop.Xbank.mp7:1', None))


def vals_of(g, nodes):
    return ' '.join('%s=%s' % (n, fmt17(g[p])) for (n, p, _l) in nodes if g.get(p) is not None)


V_NODES = tuple(nd for nd in SHIP_NODES if nd[2] is not None)
G_NODES = tuple(nd for nd in SHIP_NODES if nd[1].endswith(':2'))
I_NODES = tuple(nd for nd in SHIP_NODES if nd[2] is None)


def nodes_for(kind):
    """each block carries the signals its own claim needs, so the file stays re-computable and small"""
    if kind == 'charge':
        return tuple([nd for nd in V_NODES if nd[0] in ('gate33', 'bgate')] + list(G_NODES) +
                     [nd for nd in I_NODES if nd[0] in ('Ip_gate', 'VSCAN_i')])
    if kind == 'event':
        return tuple([nd for nd in V_NODES if nd[0] != 'vscan'] +
                     [nd for nd in I_NODES if nd[0] in ('Ip_gate', 'VSCAN_i')])
    # a plateau window carries the state, the three rails and the seven device currents that form the
    # Ron and sharing claims; the gate-terminal currents belong to the charge blocks, not here
    return tuple(list(V_NODES) + [nd for nd in I_NODES
                                  if nd[0] in ('VSCAN_i', 'V33_i', 'V18_i')
                                  or (nd[0].startswith('mp') and nd[1].endswith(':1'))])


def event_rows(cid, case_def, groups, axis, data, deck_sha='', raw_sha='', charge_windows=None):
    """the original adjacent samples behind every claim this case makes, in per-event blocks

    Nothing is interpolated, nothing is smoothed, no node is invented: each block is bounded by the
    input event's own next crossing of either direction, exactly as the audited attribution rule
    demands, and the charge blocks are the integration windows themselves.
    """
    rows = []
    if not groups:
        return rows
    nodes = [(n, p, l) for (n, p, l) in SHIP_NODES if p in groups[0]]
    ev_nodes = [(n, p, l) for (n, p, l) in nodes_for('event') if p in groups[0]]
    wn_nodes = [(n, p, l) for (n, p, l) in nodes_for('window') if p in groups[0]]
    ch_nodes = [(n, p, l) for (n, p, l) in nodes_for('charge') if p in groups[0]]
    times = [g[axis] for g in groups]

    def row(event, kind, idx, t, values, status):
        rows.append([cid, event, kind, ('' if idx is None else str(idx)),
                     ('' if t is None else fmt17(t)), values, status, deck_sha, raw_sha])

    # 1 -- the reset-free initialisation, labelled as what it is
    xs = R1.crossing_times(groups, axis, 'clk', 0.5 * V18)
    h = R3._hit_in_window(xs, 150.0 * 1e-9) if xs else None
    row('priming_two_rising_edges', 'initialisation_crossing', h[0] if h else None,
        h[1] if h else None,
        'clk only: d=0 and blank high through both priming edges, so q stays low and no other node '
        'crosses because of it. NOT a cause of any judged response.', 'MEASURED')

    # 2 -- one block per declared propagation event
    for lab, sin, ein, vin, sout, eout, t0, t1 in case_def['delays']:
        p_in, p_out = sig_path(sin), sig_path(sout)
        vdom = VSCAN if sout == 'scan' else R3.DOMAIN.get(sout, V18)
        xs_in = R1.crossing_times(groups, axis, p_in, 0.5 * vin)
        t_in = R3._hit_in_window(xs_in, t0 * 1e-9, t1 * 1e-9)
        if not t_in:
            row(lab, 'event_crossing_list', None, None,
                'no 50%% crossing of %s inside [%s, %s] ns' % (sin, tnum(t0), tnum(t1)),
                'NO_INPUT_EDGE')
            continue
        bound = R3._next_after(xs_in, t_in[1])
        t_end = bound[1] if bound else (t1 * 1e-9)
        found = []
        for name, path, lvl in nodes:
            if lvl is None:
                continue
            xs = R1.crossing_times(groups, axis, path, 0.5 * (lvl if name != 'scan' else VSCAN))
            hh = R3._hit_in_window(xs, t_in[1], t_end)
            if hh:
                found.append((name, hh))
        row(lab, 'event_crossing_list', t_in[0], t_in[1],
            'input %s at %s s ; %s ; attribution bound t_next=%s'
            % (sin, fmt17(t_in[1]),
               ' ; '.join('%s at %s s' % (n, fmt17(t)) for n, (i, t) in found if n != sin),
               fmt17(bound[1]) if bound else 'END_OF_DATA'), 'MEASURED')
        for name, h2 in found:
            for i in range(max(0, h2[0] - 2), min(len(groups), h2[0] + 3)):
                row('%s/%s' % (lab, name), 'segment', i, times[i], vals_of(groups[i], ev_nodes),
                    'MEASURED_SAMPLE')

    # 3 -- the judged windows: the fault case gets its whole window, the rest their steady tail plus
    #      the two extreme samples with their neighbours, all original adjacent points
    for w in case_def['windows']:
        if w['label'] == 'established_Q0':
            continue
        idxs = [i for i, t in enumerate(times)
                if w['t0'] * 1e-9 - 1e-18 <= t <= w['t1'] * 1e-9 + 1e-18]
        if not idxs:
            continue
        if w.get('refusable'):
            for i in idxs:
                row(w['label'], 'window_full', i, times[i], vals_of(groups[i], wn_nodes),
                    'MEASURED_SAMPLE')
            continue
        tail = idxs[-10:]
        for i in tail:
            row(w['label'], 'window_tail_block', i, times[i], vals_of(groups[i], wn_nodes),
                'MEASURED_SAMPLE')
        for sig in ('gate33', 'scan'):
            series = [(i, groups[i].get(sig_path(sig))) for i in idxs
                      if groups[i].get(sig_path(sig)) is not None]
            if not series:
                continue
            for which in ('min', 'max'):
                pick = (min if which == 'min' else max)(series, key=lambda x: x[1])[0]
                lo_i = idxs.index(pick)
                for i in idxs[max(0, lo_i - 2):lo_i + 3]:
                    row('%s/%s_%s' % (w['label'], sig, which), 'window_extreme', i, times[i],
                        vals_of(groups[i], wn_nodes), 'MEASURED_SAMPLE')

    # 4 -- the gate-charge integration windows, sample for sample, so the trapezoid is re-computable
    for (label, lo, hi, _src) in (charge_windows or []):
        idxs = [i for i, t in enumerate(times) if lo - 1e-18 <= t <= hi + 1e-18]
        if len(idxs) < 2:
            continue
        for i in idxs:
            row(label, 'charge_window', i, times[i], vals_of(groups[i], nodes), 'MEASURED_SAMPLE')
    return rows


# ------------------------------------------------------------------ evidence shapes
MAN_HDR = ['run_id', 'case', 'deck', 'deck_sha256', 'top_master', 'cell_sha256_16', 'section',
           'temp_written', 'temp_read_back', 'rails_V', 'load_R_ohm', 'load_C_F', 'analysis',
           'preflight_static_rc', 'preflight_rc', 'spectre_rc', 'runner_verdict', 'refusal_rows',
           'device_count', 'gate_current_names', 'saved_traces', 'window_rows', 'state_verdict']
ID_HDR = ['run_id', 'case', 'deck_relpath', 'deck_sha256', 'raw_relpath', 'raw_sha256',
          'lib_sha256', 'mdl_sha256', 'readme_sha256', 'mis_sha256', 'geometry_source', 'provenance']
SAMP_HDR = ['case', 'event', 'kind', 'sample_group_index', 'time_s', 'values', 'status',
            'deck_sha256', 'raw_sha256']
ROWS_HDR = S2.ROWS_HDR
DUT_TIMEOUT = '1200'      # R3 gave 900 s to 32 devices over 9000 points; this has 39 plus six currents


def sha256_file(path):
    try:
        return hashlib.sha256(open(path, 'rb').read()).hexdigest()
    except Exception:
        return ''


def rel(path):
    return os.path.relpath(path, PROJ).replace('\\', '/')


def write_cells(scratch):
    """the repository bytes of every master a deck can include, copied next to that deck"""
    all_files = list(FROZEN) + [BANK_FILE, TOP_FILE, FAULT_FILE]
    out = {}
    for f in all_files:
        data = open(os.path.join(PROJ, 'spectre', f), 'rb').read()
        with open(os.path.join(scratch, f), 'wb') as fh:
            fh.write(data)
        out[f] = hashlib.sha256(data).hexdigest()
    return out


def supply_hits(out_txt):
    """which contract entries the static gate really reached, read off its own tokens"""
    ok = [l for l in (out_txt or '').split('\n') if l.strip().startswith('SUPPLY_OK')]
    got = set()
    for l in ok:
        m = re.search(r'\.(\w+)\s*=', l)
        if m:
            got.add(m.group(1))
        if 'reference node 0' in l:
            got.add('vss')
    return got, len(ok)


def state_verdict_of(rows):
    bad = [r for r in rows if r[7] == 'FAIL']
    blocked = [r for r in rows if r[7] in ('BLOCKED', 'NOT_DETECTED')]
    if bad:
        return 'FUNCTIONAL_FAIL(%d)' % len(bad)
    if blocked:
        return 'DEPENDENCY_OR_UNDETECTED(%d)' % len(blocked)
    ref = len([r for r in rows if r[7] == 'EXPECTED_REFUSAL'])
    return 'PASS%s' % ('_with_expected_refusal' if ref else '')


def measure_stimulus(R, cid, data, case_def):
    """the inputs are read back from the waveforms, so the framework is not just generator text"""
    t_end = '%.9g' % (STOP_NS * 1e-9)
    for sig, net, val, flips in R3.stimulus_rows(case_def):
        rcn, mn = S2.read_sig(R, data, net, 'min', '0', t_end, req='10')
        rcx, mx = S2.read_sig(R, data, net, 'max', '0', t_end, req='10')
        if rcn or rcx:
            R.add('S3B_STIMULUS_READBACK', cid, net, 'the deck drives this net',
                  (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
                  'the declared flip list is not evidence of a waveform')
            continue
        R.add('S3B_STIMULUS_READBACK', cid, net, 'declared flips %s' % flips[:70],
              'window min=%.6g max=%.6g V' % (float(mn), float(mx)), 0, 'MEASURED',
              'read over the whole run; the state rows judge the windows')


# ------------------------------------------------------------------ one case
def run_case(R, cid, scratch, man_rows, samp_rows, id_rows, o, gate_term=False, dry=False,
             gate_all=False):
    case_def = find_case(cid)
    if case_def is None:
        R.add('S3B_DECK_BUILD', cid, '-', 'an id from this entry\'s own table', 'UNKNOWN_CASE', 0,
              'NOT_AVAILABLE', 'this entry does not invent cases')
        return
    deck_txt = build_deck(case_def, o.section, gate_term=gate_term, gate_all=gate_all)
    deck = os.path.abspath(os.path.join(scratch, cid + '.scs'))
    with io.open(deck, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(u(deck_txt))
    sha = hashlib.sha256(deck_txt.encode('utf-8')).hexdigest()
    hashes = dict((name, h) for name, h, _n in cell_hashes(case_def))
    chash = ' '.join('%s=%s' % (name, hashes[name][:12]) for name in include_order(case_def))
    R.add('S3B_CELLS_REUSED_VERBATIM', cid, 'the four reviewed files plus the bank and this top',
          'the deck includes the repository bytes; no reviewed cell body is edited',
          chash, 0, 'PASS', 'sha256 of each included master as it sits in spectre/')
    master = FAULT_MASTER if case_def['fault'] else TOP_MASTER
    R.add('S3B_TOP_VARIANT', cid, master, 'the deck instantiates one named top master',
          'fault=%s ; port order (d clk blank core_ok33 scan vdd18 vdd33 vscan vss)'
          % ('BLANK pin at vss' if case_def['fault'] else 'no'), 0, 'PASS',
          'the normal and faulted tops are separate files; neither edits the reviewed wrapper')
    if case_def['fault']:
        stmts, comments = deck_diff(build_deck(find_case(REF_BLANK_CASE), o.section), deck_txt)
        diffs, fprobs, exactly_one = fault_proof()
        R.add('S3B_FAULT_DIFF', cid, 'the faulted top vs the reviewed wrapper, instance by instance',
              'the same three instances and masters with ONE argument moved: Xgate blank -> vss',
              'changed=%s ; port/master problems=%s ; deck statements=%d (include + instance master '
              'name) comments=%d'
              % (['%s %s %s->%s' % (i, a[0], a[1], a[2]) for i, ch in diffs for a in ch] or 'NONE',
                 fprobs or 'none', len(stmts), len(comments)), 0,
              'PASS' if exactly_one and not fprobs else 'FAIL',
              'the deck text cannot show the pin move because it lives in the master, so the master '
              'bodies are compared directly; the deck diff is reported too rather than hidden')
    devs = S2.resolve_devices(top_instance_line(case_def), masters_text(include_order(case_def)))
    R.add('S3B_DEVICE_COUNT', cid, '%d MOS in the channel' % len(devs),
          '%d control + %d bank = %d, counted from the master bodies the simulator reads'
          % (CONTROL_DEVS, BANK_DEVS, TOTAL_DEVS),
          'resolved=%d ; first paths %s' % (len(devs), ', '.join(p for p, _m, _n in devs[:3])), 0,
          'PASS' if len(devs) == TOTAL_DEVS else 'BLOCKED',
          'the task-book number is not copied here: it is recomputed from the netlist expansion')
    driven = [n for n in ('q', 'qbar', 'en', 'gate33', 'bgate', 'scan')
              if re.search(r'\bV\w+\s*\(\s*%s\s+0\s*\)' % n, deck_txt)]
    R.add('S3B_NO_IDEAL_INTERPOSE', cid, 'q / qbar / en / gate33 / bgate / scan',
          'no ideal source drives any chain or gate node; scan carries only the declared proxy load',
          'drivers found: %s' % (', '.join(driven) or 'none'), 0, 'PASS' if not driven else 'FAIL',
          'the point of S3-B is that the real level shifter, not an instrument, moves the bank')
    widths, lens = bank_geometry()
    R.add('S3B_BANK_GEOMETRY', cid, '%d bank devices l=%s w=%s'
          % (len(widths), lens[0] if lens else '?', widths[0] if widths else '?'),
          'seven explicit p33 at L=0.4 um, W=100 um (700 um total), inside the read model limits',
          'w_total=%s m ; limits lmin=%s lmax=%s wmin=%s wmax=%s'
          % (fmt_v(len(widths) * float(widths[0])) if widths else 'NONE',
             fmt_v(S3A.GEOM['lmin']), fmt_v(S3A.GEOM['lmax']), fmt_v(S3A.GEOM['wmin']),
             fmt_v(S3A.GEOM['wmax'])), 0,
          'PASS' if (len(widths) == BANK_DEVS and len(set(widths)) == 1
                     and len(set(lens)) == 1) else 'BLOCKED',
          S3A.GEOM_SOURCE + ' -- a model range is not an absolute rating (SOA_SIGNOFF: NO)')
    r, c, why = load_of(case_def)
    R.add('S3B_LOAD_DECLARED', cid, 'R||C from scan to vss',
          'TESTBENCH_ASSUMPTION proxy, not an electrode RC',
          'R=%s ohm C=%s F tau=%s s ; %s' % (fmt_v(r), fmt_v(c), fmt_v(r * c), why), 0, 'PASS',
          'the same two values S3-A wrote; the column resistor only absorbs its 11.52 mA figure at '
          'the full 3.3 V, so a measured drop while selected is expected, not a failure')
    problems = []
    for item, detail, verdict in R3.audit_frame(case_def, problems):
        R.add('S3B_FRAME', cid, item, 'the inherited stimulus framework', detail[:120], 0, verdict,
              'POC_ASSUMPTION stimulus choices, not a setup/hold budget')
    if problems:
        R.add('S3B_SETUP_INVALID', cid, 'stimulus audit', 'no framework violation',
              ' ; '.join(problems), 3, 'BLOCKED',
              'the case is refused before the simulator sees it')
        return
    if dry:
        return

    pf_base = '%s "%s" %s %s "%s"' % (
        CC.hook('QODER_PF_CMD', 'bash ' + os.path.join(HERE, 'tb_preflight.sh')), deck,
        EXPECTED_VDD, cid, SUPPLY_MAP)
    senv = dict(os.environ)
    senv['PREFLIGHT_STATIC_PROBE'] = '1'
    sr, stxt = CC.call(pf_base, env=senv)
    hits, n_ok = supply_hits(stxt)
    missing = [k for k in re.findall(r'(\w+)=', SUPPLY_MAP) if k not in hits]
    # the static layer exits 7 on purpose: it certifies structure and declares CIRCUIT_VERDICT NOT_RUN.
    # A pass therefore means rc=7 AND the three accepted tokens AND every declared entry hit, never
    # "rc was non-zero, so something is wrong".
    accepted = (sr == 7 and 'STATIC_PROBE: accepted' in stxt and 'SUPPLY_RESULT PASS' in stxt
                and 'STATIC_RESULT PASS' in stxt)
    R.add('S3B_SUPPLY_STATIC', cid, os.path.basename(deck),
          'every declared contract entry is reached by at least one instance port (static layer, '
          'rc=7 by design: structure only, circuit not evaluated)',
          'rc=%s SUPPLY_OK=%d hit=%s missing=%s' % (sr, n_ok, ','.join(sorted(hits)) or 'none',
                                                    ','.join(missing) or 'none'), sr,
          'PASS' if accepted and not missing else 'BLOCKED',
          'the top-level netlist has a port, not a device, so its own rail is checked on every '
          'instance inside it; `vscan` is not supply-like to the frozen checker, so it must be '
          'declared and then hit, and the checker itself refuses a declared entry that matches no '
          'port')
    man = [R.run_id, cid, os.path.basename(deck), sha, master, chash, o.section, S3A.TEMP_C,
           '', 'vdd18=1.8 vdd33=3.3 vscan=3.3 vss=0 (vdd=1.8 for the two 1.8 V sub-masters)',
           fmt_v(r), fmt_v(c),
           'tran stop=%s maxstep=%sn' % (tnum(STOP_NS), fmt_v(MAXSTEP_NS)),
           str(sr), '', '', '', '', '', '', '', '', '']
    if not accepted or missing:
        man[15], man[16], man[22] = 'NOT_RUN', 'BLOCKED_after_static', 'BLOCKED_after_static'
        man_rows.append(man)
        R.log.append('=== %s static supply REFUSED rc=%s\n%s' % (cid, sr, S2.scrub(stxt)))
        return

    penv = dict(os.environ)
    penv.pop('PREFLIGHT_STATIC_PROBE', None)
    pfr, pftxt = CC.call(pf_base, env=penv)
    pf_ok, pf_reason, pf_summary = CC.preflight_verdict(pfr, pftxt)
    R.add('PREFLIGHT_FULL', cid, os.path.basename(deck),
          "the preflight own rc=0 AND exactly one TESTBENCH_PREFLIGHT: PASS",
          'rc=%s map=%s | %s' % (pfr, SUPPLY_MAP, pf_summary.replace('\n', ' | ')[:90]), pfr,
          'PASS' if pf_ok else 'BLOCKED', pf_reason)
    man[14] = str(pfr)
    R.log.append('=== %s full preflight rc=%s\n%s' % (cid, pfr, S2.scrub(pftxt)))
    if not pf_ok:
        man[15], man[16], man[22] = 'NOT_RUN', 'BLOCKED_after_preflight', 'BLOCKED_after_preflight'
        man_rows.append(man)
        return

    label = 'S3B_%s' % cid
    renv = dict(os.environ)
    renv['LABEL'] = label
    rc, run_out = CC.call('%s "%s" %s' % (CC.hook('QODER_RUN_CMD', 'bash ' + os.path.join(
        HERE, 'run_spectre.sh')), deck, DUT_TIMEOUT), env=renv)
    run_ok, run_reasons, parts = CC.runner_verdict(label, deck, rc, run_out)
    err = re.search(r'ERROR \([A-Z0-9-]+\)[^\n]*', run_out)
    R.add('SIM_RUN', cid, os.path.basename(deck),
          'runner rc=0 + one PASS for this label + spectre rc=0 + error_hits=0 + own data',
          'runner_rc=%s preflight_rc=%s spectre_rc=%s error_hits=%s pass_lines=%d'
          % (rc, pfr, parts.get('spectre_rc', ''), parts.get('error_hits', ''),
             parts.get('pass_lines', 0)), rc, 'PASS' if run_ok else 'BLOCKED',
          ('; '.join(run_reasons)[:130] or S2.scrub(err.group(0) if err else
                                                    'contract satisfied').replace('\n', ' ')[:130]))
    R.log.append('=== %s run %s\nrunner: %s\n' % (cid, 'accepted' if run_ok else 'REJECTED',
                                                  S2.scrub(run_out)))
    data = parts.get('datafile', '')
    man[15] = parts.get('spectre_rc', '') or '?'
    man[16] = 'PASS' if run_ok else 'BLOCKED'
    if not run_ok or not data or not os.path.isfile(data):
        man_rows.append(man)
        return
    man[8] = S3A.read_temp(run_out, data)
    raw_sha, deck_sha = sha256_file(data), sha

    before = len(R.rows)
    measure_stimulus(R, cid, data, case_def)
    groups, axis = R1.samples_of(data)
    seen, keys = (gate_current_names(groups) if groups else ({}, []))
    term_all = all(('Xtop.Xbank.mp%d:2' % k) in keys for k in range(1, BANK_DEVS + 1))
    cur_keys = []
    if term_all:
        cur_keys.append('terminal_sum')
    if seen.get('iprobe'):
        cur_keys.append('Xtop.Ip_gate:i')
    R.add('S3B_GATE_CURRENT_SOURCE', cid, 'which gate-current names this data file carries',
          'the MOS gate terminal sum is preferred; the zero-drop iprobe branch is the independent '
          'check, and neither is used before the trace is read back',
          'iprobe=%s mp1:1=%s mp1:2=%s all_seven_drains=%s all_seven_gate_terminals=%s used=%s ; '
          '%d trace names'
          % (seen.get('iprobe'), seen.get('drain1'), seen.get('gate2_1'), seen.get('drains'),
             term_all, '+'.join(cur_keys) or 'NONE_NOT_MEASURED', len(keys)), 0,
          'MEASURED' if cur_keys else 'NOT_MEASURED',
          'nothing was assumed from the fact that terminal 1 worked in S3-A: terminal 2 had to be '
          'read back first, which is what the probe batch was for')
    windows_rows = 0
    for w in case_def['windows']:
        measure_window(R, cid, data, w)
        windows_rows += len(w['expect'])
        if w.get('plateau'):
            measure_plateau(R, cid, data, w, case_def)
        if w.get('off'):
            measure_off(R, cid, data, w, case_def)
    measure_delays(R, cid, groups, axis, data, case_def)
    measure_edges(R, cid, data, case_def)
    measure_branches(R, cid, data)
    charge_windows = measure_gate_charge(R, cid, groups, axis, data, case_def, cur_keys, seen)
    measure_device_voltages(R, cid, groups, axis, case_def)
    if case_def['fault']:
        negative_report(R, cid, data, case_def, scratch)
    new_rows = R.rows[before:]
    # the count of this deck's own judgement rows that a strict tool refused to answer, so a zero in
    # this column is a claim that every read was answered, not the absence of a failure. The static
    # supply probe is excluded: its accepted exit is 7 by design (the R1-A static probe never simulates).
    refusals = [r for r in new_rows
                if r[6] not in ('0', '') and r[0] != 'S3B_SUPPLY_STATIC']
    man[17] = str(len(refusals))
    man[18] = str(len(devs))
    man[19] = '+'.join(cur_keys) or 'none'
    man[20] = ','.join(sorted(keys))
    man[21] = str(windows_rows)
    man[22] = state_verdict_of(new_rows)
    man_rows.append(man)
    samp_rows.extend(event_rows(cid, case_def, groups, axis, data, deck_sha, raw_sha,
                                charge_windows=charge_windows))
    id_rows.append([R.run_id, cid, rel(deck), deck_sha, rel(os.path.dirname(data)), raw_sha,
                    o.lib_sha, o.mdl_sha, o.readme_sha, o.mis_sha, S3A.GEOM_SOURCE,
                    'deck and raw written by this run into this scratch directory; the included '
                    'masters are the repository bytes named in the manifest row'])


def device_sharing(R, cid, groups, times):
    """the seven drain currents, read per device, against the rail that feeds them

    Identical D/G/S/B nets make the devices equal by connection, but the currents are still read from
    each one: a parallel bank whose fingers disagree would say so here, and the plateau rows use the
    same per-device numbers instead of assuming them.
    """
    drains = ['Xtop.Xbank.mp%d:1' % k for k in range(1, BANK_DEVS + 1)]
    if not groups or not all(d in groups[0] for d in drains):
        R.add('S3B_DEVICE_SHARING', cid, 'the seven drain currents',
              'the per-device terminal current saved as mp<k>:1 (the form S3-A confirmed)',
              'MISSING_TRACES', 0, 'NOT_MEASURED', 'no sharing claim without the device currents')
        return
    worst, at, worst_rel, worst_rel_t = 0.0, None, 0.0, None
    for g, t in zip(groups, times):
        vals = [g.get(d) for d in drains]
        if any(v is None for v in vals):
            continue
        spread = max(vals) - min(vals)
        if abs(spread) > worst:
            worst, at = abs(spread), t
        inj = -g.get('VSCAN:i') if g.get('VSCAN:i') is not None else None
        if inj is not None and abs(inj) > 1e-9:
            rel = abs(sum(vals) - inj) / abs(inj)
            if rel > worst_rel:
                worst_rel, worst_rel_t = rel, t
    R.add('S3B_DEVICE_SHARING', cid, 'seven drain currents over the run',
          'the parallel fingers share the current and their sum tracks the switching rail',
          'worst |max-min| between fingers = %.6g A at t=%s s ; worst |sum - (-VSCAN:i)| / |VSCAN:i| '
          '= %.4g at t=%s s' % (worst, fmt17(at) if at else '?', worst_rel,
                                 fmt17(worst_rel_t) if worst_rel_t else '?'), 0, 'MEASURED',
          'the same D/G/S/B nets make the devices equal by connection; these two figures are reported '
          'whatever they are, so a mismatch is a reading and not a pass condition')


def measure_gate_charge(R, cid, groups, axis, data, case_def, cur_keys, seen=None):
    """one integral per real gate33 transition, over its own change-and-recovery interval

    The window is the transition plus its recovery, never the 10-90 % span alone, and it is clipped at
    the neighbouring gate33 event: an integral that crosses two events is not an edge charge. Every
    readable gate-current source is integrated -- the seven device gate terminal currents summed (the
    preferred reading) and the branch iprobe -- and the two are compared instead of being picked
    silently. Returns the preferred source's windows so the sample exporter ships exactly the points
    the trapezoid used.
    """
    cur_keys = list(cur_keys or [])
    if not cur_keys or not groups or axis not in groups[0]:
        R.add('S3B_GATE_CHARGE', cid, 'gate branch', 'a readable gate branch current',
              'NOT_MEASURED: this data file carries no gate current that was confirmed readable', 0,
              'NOT_MEASURED', 'the voltages and the function are still delivered as measured; no '
                              'charge is certified from a current that cannot be read')
        return []
    times = [g[axis] for g in groups]

    def getter(key):
        if key == 'terminal_sum':
            drains = ['Xtop.Xbank.mp%d:2' % k for k in range(1, BANK_DEVS + 1)]

            def g_(g):
                vals = [g.get(d) for d in drains]
                return sum(vals) if all(v is not None for v in vals) else None
            return g_
        return lambda g: g.get(key)

    def label(key):
        return ('sum(Xtop.Xbank.mp1..mp7:2)' if key == 'terminal_sum' else key)
    get0, name0 = getter(cur_keys[0]), label(cur_keys[0])
    events = gate_edge_events(groups, axis, 0.5 * V33)
    other = [t for (t, _d, _i) in events]
    windows = []
    for (tc, direction, _i) in events:
        near_prev = max([t for t in other if t < tc - 1e-15] + [times[0]])
        near_next = min([t for t in other if t > tc + 1e-15] + [times[-1]])
        # ---- the voltage event: the two ends of THIS transition's 10-90 % interval, taken as the
        # level crossings that lie on either side of its own 50 % instant. The first sample that has
        # left 90 % anywhere in the neighbour-bounded segment is not enough: after a slow fall the
        # node can still be above 10 % when the next rise starts, and that instant belongs to the
        # earlier edge, so an integral from there is not this edge's charge.
        hi_lvl, lo_lvl = 0.90 * V33, 0.10 * V33
        if direction == 'fall':
            enter, leave, want = hi_lvl, lo_lvl, 'down'
        else:
            enter, leave, want = lo_lvl, hi_lvl, 'up'
        start_hits = [t for (t, d, _i) in level_crossings(groups, axis, 'Xtop.gate33', enter)
                      if d == want and near_prev - 1e-18 <= t <= tc + 1e-18]
        stop_hits = [t for (t, d, _i) in level_crossings(groups, axis, 'Xtop.gate33', leave)
                     if d == want and tc - 1e-18 <= t <= near_next + 1e-18]
        start_t = max(start_hits) if start_hits else None
        stop_t = min(stop_hits) if stop_hits else None
        if start_t is None or stop_t is None or stop_t <= start_t:
            R.add('S3B_GATE_CHARGE', cid, 'gate33 %s at %.6g ns' % (direction, tc * 1e9),
                  'both the 10 % and the 90 % crossing of this transition, on its own side of its '
                  '50 % instant and inside its neighbour bounds',
                  't10=%s t90=%s' % (fmt17(start_t) if start_t else 'NONE',
                                     fmt17(stop_t) if stop_t else 'NONE'), 0, 'NOT_MEASURED',
                  'without both ends of the voltage swing there is no edge to charge-integrate')
            continue
        lo = max(near_prev, start_t - (PRE_EDGE_NS + PRE_BAND_NS) * 1e-9)
        partial = lo > start_t - (PRE_EDGE_NS + PRE_BAND_NS) * 1e-9 + 1e-18
        # ---- how far the window runs. A stretch is only a level once the branch current has
        # flattened, and "flattened" is judged against the peak this very edge produced, not against
        # a chosen number: the bank gates charge for tens of ns after the 90 % instant. The bounds
        # are anchored on real sample instants so every number printed here is re-computable from
        # the shipped window, and each source gets its own stretch means rather than borrowing the
        # first source's.
        get0 = getter(cur_keys[0])
        hi = min(near_next, stop_t + POST_SETTLE_NS * 1e-9)
        seg0, pre0, post0, thresh = [], None, None, CHARGE_FLOOR_A
        for _k in range(40):
            seg0 = [(t, v) for g, t in zip(groups, times)
                    if lo - 1e-18 <= t <= hi + 1e-18 for v in [get0(g)] if v is not None]
            if len(seg0) < 4:
                break
            thresh = max(CHARGE_FLOOR_A, SETTLE_FRACTION * max(abs(v) for _t, v in seg0))
            pre0 = band_of(groups, times, cur_keys[0], seg0[0][0], seg0[0][0] + PRE_BAND_NS * 1e-9)
            post0 = band_of(groups, times, cur_keys[0], seg0[-1][0] - PRE_BAND_NS * 1e-9,
                            seg0[-1][0])
            if pre0 is None or post0 is None or post0[2] - post0[1] <= thresh:
                break
            nxt = min(near_next, hi + RECOVER_NS * 1e-9)
            if nxt <= hi + 1e-18:
                partial = True                    # the next gate33 event is where the window ends
                break
            hi = nxt
        if len(seg0) < 4 or pre0 is None or post0 is None:
            R.add('S3B_GATE_CHARGE', cid, 'gate33 %s at %.6g ns' % (direction, tc * 1e9),
                  'a settled stretch before the 10 % point and another at the end of the recovery',
                  'window_points=%d pre_samples=%s post_samples=%s'
                  % (len(seg0), 'none' if pre0 is None else pre0[0],
                     'none' if post0 is None else post0[0]), 0, 'NOT_MEASURED',
                  'no baseline can be formed from a stretch too short to average')
            continue
        if post0[2] - post0[1] > thresh:
            partial = True                        # still moving at the neighbour bound
        t_start, t_end = seg0[0][0], seg0[-1][0]
        window_peak = max(abs(v) for _t, v in seg0)
        nets = {}
        for key in cur_keys:
            get = getter(key)
            seg = [(t, get(g)) for g, t in zip(groups, times)
                   if t_start - 1e-18 <= t <= t_end + 1e-18 and get(g) is not None]
            if len(seg) < 4:
                R.add('S3B_GATE_CHARGE', cid, 'gate33 %s at %.6g ns [%s]'
                      % (direction, tc * 1e9, label(key)),
                      'at least four adjacent samples of this source across the transition',
                      'points=%d' % len(seg), 0, 'NOT_MEASURED',
                      'this source is not readable over the interval it should certify')
                continue
            ts = [t for t, _v in seg]
            ys = [v for _t, v in seg]
            pre_k = pre0 if key == cur_keys[0] else band_of(groups, times, key, t_start,
                                                            t_start + PRE_BAND_NS * 1e-9)
            post_k = post0 if key == cur_keys[0] else band_of(groups, times, key,
                                                              t_end - PRE_BAND_NS * 1e-9, t_end)
            if pre_k is None or post_k is None:
                R.add('S3B_GATE_CHARGE', cid, 'gate33 %s at %.6g ns via %s'
                      % (direction, tc * 1e9, label(key)),
                      'three adjacent samples of this source at each end of the window',
                      'pre_samples=%s post_samples=%s' % ('none' if pre_k is None else pre_k[0],
                                                           'none' if post_k is None else post_k[0]),
                      0, 'NOT_MEASURED', 'this source has no stretch to take a level from')
                continue
            raw = traj(ts, ys)
            mid_t = min(tc, ts[-1])
            step = pre_k[3] * (mid_t - ts[0]) + post_k[3] * (ts[-1] - mid_t)
            net = raw - step
            row_partial = partial or post_k[2] - post_k[1] > thresh
            nets[key] = net
            if key == cur_keys[0]:
                windows.append(('gate33_%s_at_%.3fns' % (direction, tc * 1e9), ts[0], ts[-1], name0))
            gv = [g.get('Xtop.gate33') for g, t in zip(groups, times)
                  if ts[0] - 1e-18 <= t <= ts[-1] + 1e-18 and g.get('Xtop.gate33') is not None]
            swing = (max(gv) - min(gv)) if len(gv) > 1 else 0.0
            load = (abs(net) / swing) if swing > 0.1 else None
            R.add('S3B_GATE_CHARGE', cid, 'gate33 %s at %.6g ns via %s'
                  % (direction, tc * 1e9, label(key)),
                  'trapezoid of this gate-current source over the transition plus its recovery, with '
                  'the mean level of each settled stretch subtracted as a step at the 50 % instant; '
                  'the window never crosses the next gate33 event',
                  'points=%d window=%s..%s s span=%.6g s t10=%s t50=%s t90=%s s pre_n=%d '
                  'pre_band=%.6g..%.6g A pre_mean=%.6g A post_n=%d post_band=%.6g..%.6g A '
                  'post_mean=%.6g A window_peak=%.6g A settle_thresh=%.6g A raw_Q=%.6g C '
                  'net_Q=%.6g C gate_swing=%.6g V edge_equiv_load=%s F'
                  % (len(seg), fmt17(ts[0]), fmt17(ts[-1]), ts[-1] - ts[0], fmt17(start_t),
                     fmt17(tc), fmt17(stop_t), pre_k[0], pre_k[1], pre_k[2], pre_k[3], post_k[0],
                     post_k[1], post_k[2], post_k[3], window_peak, thresh, raw, net, swing,
                     fmt_v(load) if load is not None else 'NOT_DEFINED'), 0,
                  'PARTIAL_EDGE_CHARGE' if row_partial else 'MEASURED',
                  ('the pre-edge stretch, the recovery, or this source still moving at the end of it: '
                   'the window ran into the neighbouring gate33 event (%s set it), so this is part of '
                   'an edge and is not presented as a complete one' % name0) if row_partial else
                  ('edge equivalent charge load = |net_Q| / the measured gate swing: the displacement '
                   'this edge needed, including the nonlinearity of the transition, not a fixed Cgg. '
                   'raw_Q is kept beside it because the branch total also carries whatever the two '
                   'stretches were doing, and this source\'s own stretch means, ranges and counts are '
                   'printed so the subtraction can be re-done or dropped. The window bounds and the '
                   'threshold are the ones %s settled, and they are sample instants, so both are '
                   're-computable from the shipped block' % name0)
                  )
        if len(nets) > 1:
            ks = sorted(nets)
            worst = max(abs(nets[ks[i]] - nets[ks[j]]) for i in range(len(ks))
                        for j in range(i + 1, len(ks)))
            R.add('S3B_GATE_CURRENT_CROSSCHECK', cid,
                  'gate33 %s at %.6g ns' % (direction, tc * 1e9),
                  'the summed device gate currents and the branch iprobe integrate to the same charge',
                  'sources=%s ; max |difference| = %.6g C ; %s'
                  % (','.join(label(k) for k in ks), worst,
                     ','.join('%s=%.6g C' % (label(k), nets[k]) for k in ks)), 0, 'MEASURED',
                  'both readings are reported; the terminal sum is the preferred one and the iprobe is '
                  'the independent check, not a substitute for it')
    device_sharing(R, cid, groups, times)
    return windows


# ------------------------------------------------------------------ harness guards
def safe_run(R, cid, scratch, man_rows, samp_rows, id_rows, o, gate_term=False, dry=False,
             gate_all=False):
    """a harness fault becomes a dependency row, never a circuit result

    S3-A lost a whole batch to one tuple-index slip in a late deck; the guard means a mistake in the
    measurement code of one case cannot discard the nine cases of work that already ran.
    """
    try:
        run_case(R, cid, scratch, man_rows, samp_rows, id_rows, o, gate_term=gate_term, dry=dry,
                 gate_all=gate_all)
    except Exception:
        R.add('S3B_HARNESS_ERROR', cid, 'run_case raised', 'no exception is scored as a circuit '
              'outcome', traceback.format_exc().replace('\n', ' | ')[-200:], 2, 'BLOCKED',
              'kept as a dependency failure with the traceback tail; nothing is filled in')


def process_counts(scratch):
    sim = os.path.join(scratch, 'sim')
    if not os.path.isdir(sim):
        return 0, 0
    dep = len([p for p in os.listdir(sim) if p.startswith('preflight_') and p.endswith('.log')])
    dut = len([p for p in os.listdir(sim)
               if not p.startswith('preflight_') and p.endswith('.log')])
    return dep, dut


# ------------------------------------------------------------------ selftest
def _selftest():
    """the arithmetic and the netlist invariants this round leans on, against the repository bytes

    Every item here exists because a delivered batch once found a path this code could get wrong: the
    trapezoid and its step baseline, the deck's geometry, the nested signal paths, the negative report
    and the sample exporter. The synthetic waveform below is a *tool* test, not a circuit result: no
    number in it is quoted anywhere as a measurement.
    """
    checks = []
    xs = [i * 1e-6 for i in range(11)]
    checks.append(('a constant 1 uA over 10 us integrates to 1e-11 C',
                   abs(traj(xs, [1e-6] * 11) - 1e-11) < 1e-24))
    checks.append(('the declared matrix is nine cases and unique',
                   len(CASES) == 9 and len(set(c['id'] for c in CASES)) == 9))

    ok_top = ok_cap = ok_rails = True
    for c in CASES:
        txt = build_deck(c, SECTION)
        if len(re.findall(r'^Xtop \(', txt, re.M)) != 1:
            ok_top = False
        if re.search(r'Cload \(gate33', txt) or 'capacitor c=1.5' in txt:
            ok_cap = False
        for need in ('V18 (vdd18 0)', 'V33 (vdd33 0)', 'VSCAN (vscan 0)', 'Vss (vss 0)'):
            if need not in txt:
                ok_rails = False
    checks.append(('every deck instantiates exactly one top master', ok_top))
    checks.append(('no artificial capacitance sits on gate33 in any deck', ok_cap))
    checks.append(('every deck carries the four independent rails to the 0 V reference', ok_rails))

    for c in (find_case('s3b_write_q1_column'), find_case('s3b_fault_blank_to_vss_column')):
        devs = S2.resolve_devices(top_instance_line(c), masters_text(include_order(c)))
        checks.append(('%s expands to %d MOS (32 control + 7 bank)' % (c['id'], TOTAL_DEVS),
                       len(devs) == TOTAL_DEVS))
    ports = set()
    for _m, d in S2.parse_masters(masters_text(list(FROZEN) + [BANK_FILE, TOP_FILE,
                                                                FAULT_FILE])).items():
        ports.update(d['ports'])
    checks.append(('every declared supply-map entry names a real port of the master set',
                   all(k in ports for k in re.findall(r'(\w+)=', SUPPLY_MAP))))
    problems = []
    for c in CASES:
        R3.audit_frame(c, problems)
    checks.append(('the inherited framework passes for all nine timelines', not problems))
    driven = [n for c in CASES for n in ('q', 'qbar', 'en', 'gate33', 'bgate', 'scan')
              if re.search(r'\bV\w+\s*\(\s*%s\s+0\s*\)' % n, build_deck(c, SECTION))]
    checks.append(('no deck drives a chain, gate or scan node from an ideal source', not driven))

    diffs, fprobs, one = fault_proof()
    checks.append(('the faulted chain differs from the reviewed wrapper by exactly one argument: '
                   'Xgate blank -> vss', one and not fprobs and bool(diffs)))
    stmts, _com = deck_diff(build_deck(find_case(REF_BLANK_CASE), SECTION),
                            build_deck(find_case('s3b_fault_blank_to_vss_column'), SECTION))
    checks.append(('the fault deck text changes only the included master and its instance name',
                   len(stmts) == 4 and all('sc1_s3b_scan_power_1ch' in s for s in stmts)))
    probes = masters_text([TOP_FILE]) + masters_text([FAULT_FILE])
    checks.append(('the measurement iprobe sits in the gate branch and never on a rail',
                   'Ip_gate (gate33 bgate) iprobe' in probes
                   and not re.search(r'iprobe[^/\n]*\b(vscan|vdd33|vdd18|vss)\b', probes)))

    class _R(object):
        run_id = 'SELFTEST'

        def __init__(self):
            self.rows = []          # per instance: one rehearsal must not read another's rows

        def add(self, *a, **k):
            self.rows.append(a)

    # 1 -- a 2 mA displacement pulse over three 1 ns samples with both standing levels at zero, one
    #      transition event, and one integration window that stops at the neighbour bound
    grp = [{'time': i * 1e-9,
            'Xtop.gate33': (3.3 if i < 49 else (0.0 if i > 53 else 3.3 * (1 - (i - 49) / 4.0))),
            'Xtop.Ip_gate:i': (2e-3 if 50 <= i <= 52 else 0.0)} for i in range(101)]
    ev = gate_edge_events(grp, 'time', 0.5 * V33)
    checks.append(('a single falling gate33 edge yields exactly one transition event',
                   len(ev) == 1 and ev[0][1] == 'fall'))
    r1 = _R()
    cw1 = measure_gate_charge(r1, 'self', grp, 'time', '', find_case('s3b_write_q1_light'),
                              ['Xtop.Ip_gate:i'])
    q1 = [a[4] for a in r1.rows if isinstance(a[4], str) and 'net_Q=' in a[4]]
    got1 = float(re.search(r'net_Q=([-0-9.eE+]+) C', q1[0]).group(1)) if q1 else None
    raw1 = float(re.search(r'raw_Q=([-0-9.eE+]+) C', q1[0]).group(1)) if q1 else None
    checks.append(('a 2 mA pulse held over three 1 ns samples integrates to 6e-12 C in one shipped '
                   'window, and with both standing levels at zero the step baseline leaves it alone',
                   len(cw1) == 1 and got1 is not None and raw1 is not None
                   and abs(got1 - 6e-12) < 1e-20 and abs(raw1 - got1) < 1e-20
                   and q1[0].find('pre_mean=0 A') >= 0 and q1[0].find('post_mean=0 A') >= 0))

    # 1b -- a slow fall that never reaches 10 % before the next rise starts: the rise's 10 % instant
    #       must be its OWN crossing, not the previous edge's tail, or the integral spans two events
    slow = []
    for i in range(1001):
        t = i * 1e-10
        if t < 20e-9:
            v = 3.3
        elif t < 40e-9:
            v = 3.3 - 3.2 * (t - 20e-9) / 20e-9
        elif t < 45e-9:
            v = 0.1
        elif t < 65e-9:
            v = 0.1 + 3.2 * (t - 45e-9) / 20e-9
        else:
            v = 3.3
        slow.append({'time': t, 'Xtop.gate33': v, 'Xtop.Ip_gate:i': 1e-3})
    r1b = _R()
    measure_gate_charge(r1b, 'self', slow, 'time', '', find_case('s3b_write_q1_light'),
                        ['Xtop.Ip_gate:i'])
    ends = {}
    for a in r1b.rows:
        m = re.search(r'gate33 (fall|rise) at ([0-9.]+) ns', a[2])
        n = re.search(r't10=([-0-9.eE+]+) t50', a[4])
        if m and n:
            ends[m.group(1)] = (float(m.group(2)) * 1e-9, float(n.group(1)))
    checks.append(('a rise whose previous edge is still settling takes its own 10 % crossing, so no '
                   'charge window reaches back over the earlier 50 % instant',
                   len(ends) == 2 and abs(ends['rise'][0] - 54.6875e-9) < 0.2e-9
                   and abs(ends['rise'][1] - 46.4375e-9) < 0.2e-9
                   and ends['rise'][1] > ends['fall'][0]
                   and abs(ends['fall'][1] - 22.0625e-9) < 0.2e-9))

    # 2 -- the standing level-shifter current steps sign across the edge: the step baseline has to
    # remove it, or the "edge charge" would mostly be the hold current of the state before it
    step = []
    for i in range(2001):
        t = i * 1e-10
        v = 3.3 if t < 100e-9 else (0.0 if t > 102e-9 else 3.3 * (1 - (t - 100e-9) / 2e-9))
        hold = -0.8e-3 if t < 101e-9 else 0.94e-3
        disp = 2e-3 * (1 - abs(t - 101e-9) / 1e-9) if 100e-9 <= t <= 102e-9 else 0.0
        step.append({'time': t, 'Xtop.gate33': v, 'Xtop.Ip_gate:i': hold + disp})
    r2 = _R()
    cw2 = measure_gate_charge(r2, 'self', step, 'time', '', find_case('s3b_write_q1_light'),
                              ['Xtop.Ip_gate:i'])
    txt2 = [a[4] for a in r2.rows if isinstance(a[4], str) and 'net_Q=' in a[4]]
    got2 = float(re.search(r'net_Q=([-0-9.eE+]+) C', txt2[0]).group(1)) if txt2 else None
    raw2 = float(re.search(r'raw_Q=([-0-9.eE+]+) C', txt2[0]).group(1)) if txt2 else None
    inj = 0.5 * 2e-9 * 2e-3
    checks.append(('a step in the standing current is subtracted as a step: the displacement comes '
                   'back within 10 %% of the injected %.3g C while the branch total still carries it'
                   % inj,
                   len(cw2) == 1 and got2 is not None and raw2 is not None
                   and abs(abs(got2) - inj) <= 0.1 * inj and abs(raw2) > 1.5 * inj))
    checks.append(('the charge row prints both stretch means with their bands, counts, the window '
                   'peak, its threshold and both edge ends',
                   bool(txt2) and all(k in txt2[0] for k in ('pre_mean=', 'post_mean=', 't10=',
                                                             't50=', 't90=', 'window_peak=',
                                                             'settle_thresh='))))

    # 3 -- the negative report: DETECTED only when its five printed conditions all hold, BLOCKED when
    #      the reference window it contrasts against is missing or unreadable
    neg_scratch = os.path.join(PROJ, 'cadence_work', 's3b_neg_selftest')
    ref_dir = os.path.join(neg_scratch, 'sim', REF_BLANK_CASE + '.raw')
    if not os.path.isdir(ref_dir):
        os.makedirs(ref_dir)
    io.open(os.path.join(ref_dir, 'sw1.tran.tran'), 'w').close()
    ref_tail = os.path.join(REF_BLANK_CASE + '.raw', 'sw1.tran.tran')

    def make_read(en_low=False, ref_gate='3.3', ref_rc=0):
        def fake_read(_R_, data, sig, mode, t0=None, t1=None, req='3'):
            if str(data).endswith(ref_tail):
                return ref_rc, ref_gate
            if sig == 'Xtop.gate33':
                return 0, ('0.0' if mode == 'min' else '0.02')
            if sig == 'blank':
                return 0, '1.8'
            if sig == sig_path('qbar'):
                return 0, '0.0'
            if sig == sig_path('en') and en_low:
                return 0, '0.0'
            return 0, '1.8'
        return fake_read

    def run_neg(read, scratch=None):
        saved = S2.read_sig
        S2.read_sig = read
        try:
            rr = _R()
            negative_report(rr, 'self', '', find_case('s3b_fault_blank_to_vss_column'),
                            scratch or neg_scratch)
            rows = [a for a in rr.rows if a[0] == 'S3B_FAULT_NEGATIVE']
        finally:
            S2.read_sig = saved
        return rows[0] if rows else ['', '', '', '', '', '', 'ABSENT', '']

    neg = run_neg(make_read())
    checks.append(('the negative report decides DETECTED from five named conditions, prints each one, '
                   'and names the window whose blank claim failed',
                   neg[6] == 'DETECTED' and 'blanked_450' in neg[2] and 'blank=' in neg[4] and
                   neg[4].count('=yes') == 5 and neg[4].count('=NO') == 0))
    checks.append(('the same report blocks instead of deciding when the reference deck or its read is '
                   'missing, and says NOT_DETECTED when the pin did see the blank or the reference '
                   'window was not high',
                   run_neg(make_read(), os.path.join(PROJ, 'cadence_work'))[6] == 'BLOCKED' and
                   run_neg(make_read(ref_rc=1))[6] == 'BLOCKED' and
                   run_neg(make_read(ref_gate='0.0'))[6] == 'NOT_DETECTED' and
                   run_neg(make_read(en_low=True))[6] == 'NOT_DETECTED'))

    # 4 -- the sample exporter over a miniature waveform of one selected write
    wave = []
    for i in range(5001):
        t = i * 1e-10
        cyc = t % (R3.PERIOD * 1e-9)
        q = V18 if t >= 250.167e-9 else 0.0
        g = (V33 if t < 251.4e-9 else (0.0 if t > 253.4e-9
                                       else V33 * (1 - (t - 251.4e-9) / 2e-9)))
        hold = -0.8e-3 if t < 252.4e-9 else 0.94e-3
        disp = 2e-3 * (1 - abs(t - 252.4e-9) / 1e-9) if 251.4e-9 <= t <= 253.4e-9 else 0.0
        row = {'time': t, 'clk': (V18 if 51e-9 <= cyc <= 99e-9 else 0.0),
               'd': (V18 if t >= 220e-9 else 0.0),
               'blank': (0.0 if 200e-9 <= t < 400e-9 else V18),
               'core_ok33': (V33 if t >= 200e-9 else 0.0),
               sig_path('q'): q, sig_path('qbar'): V18 - q,
               sig_path('en'): (V18 if t >= 250.356e-9 else 0.0),
               'Xtop.gate33': g, 'Xtop.bgate': g,
               'scan': (0.0 if t < 252.5e-9 else VSCAN - 0.089), 'vscan': VSCAN,
               'VSCAN:i': hold + disp, 'V33:i': -1e-6, 'V18:i': -2e-6,
               'Xtop.Ip_gate:i': hold + disp}
        for k in range(1, BANK_DEVS + 1):
            row['Xtop.Xbank.mp%d:2' % k] = (hold + disp) / BANK_DEVS
            row['Xtop.Xbank.mp%d:1' % k] = -1.6e-3 / BANK_DEVS
        wave.append(row)
    shipped = []
    for cid in ('s3b_fault_blank_to_vss_column', 's3b_repeat101_column'):
        shipped.extend(event_rows(cid, find_case(cid), wave, 'time', '', 'd' * 64, 'r' * 64,
                                  charge_windows=[('gate33_fall_at_252.400ns', 246e-9, 261e-9,
                                                   'Xtop.Ip_gate:i')]))
    kinds = set(r[2] for r in shipped)
    needed = ('initialisation_crossing', 'event_crossing_list', 'segment', 'window_full',
              'window_tail_block', 'window_extreme', 'charge_window')
    checks.append(('the sample exporter emits every block kind the delivery promises ('
                   + ','.join(needed) + ')', all(k in kinds for k in needed)))

    grid = [g['time'] for g in wave]
    SAMPLE_KINDS = ('segment', 'window_full', 'window_tail_block', 'window_extreme',
                    'charge_window')
    round_trip, on_grid = [], []
    for r in shipped:
        if r[4] != '':
            round_trip.append(fmt17(float(r[4])) == r[4])
            if r[2] in SAMPLE_KINDS:
                on_grid.append(float(r[4]) == grid[int(r[3])])
    checks.append(('every shipped row carries both 64-hex digests, every shipped time is the full '
                   'precision instant and not a rounded display value, and every pure sample row '
                   're-reads to the exact double its own sample index holds',
                   bool(shipped) and all(len(r[7]) == 64 and len(r[8]) == 64 for r in shipped)
                   and all(round_trip) and all(on_grid)
                   and len(on_grid) > 500 and len(round_trip) == len(shipped)))

    def _m(x):
        return '%.17g' % x
    checks.append(('a 17-digit round trip keeps the double exactly', float(_m(1.0 / 3.0)) == 1.0 / 3.0))
    checks.append(('the manifest row template has the header width', len(MAN_HDR) == 23))

    bad = [n for n, v in checks if not v]
    for name, v in checks:
        print('   %-70s %s' % (name, 'PASS' if v else 'FAIL'))
    print('S3B_HELPER_SELFTEST cases=%d failures=%d (repository bytes and synthetic numbers; no '
          'simulator, no circuit claim)' % (len(checks), len(bad)))
    return 1 if bad else 0

def main():
    op = optparse.OptionParser()
    op.add_option('--selftest', action='store_true')
    op.add_option('--dry', action='store_true')
    op.add_option('--probe', action='store_true',
                  help='run ONE deck with the extra gate-terminal saves to see which names exist')
    op.add_option('--scratch')
    op.add_option('--out')
    op.add_option('--manifest')
    op.add_option('--samples')
    op.add_option('--identity')
    op.add_option('--log')
    op.add_option('--only')
    op.add_option('--expect', type='int', default=0)
    op.add_option('--section', default=SECTION)
    op.add_option('--gate-term', action='store_true')
    op.add_option('--gate-all', action='store_true',
                  help='save all seven gate terminal currents (use only after a probe read them)')
    op.add_option('--lib-sha', default='')
    op.add_option('--mdl-sha', default='')
    op.add_option('--readme-sha', default='')
    op.add_option('--mis-sha', default='')
    o = op.parse_args()[0]
    if o.selftest:
        return _selftest()

    ids = [c['id'] for c in CASES]
    selected = CASES
    if o.only:
        wanted = [c for c in o.only.split(',') if c]
        unknown = [c for c in wanted if c not in ids]
        if unknown:
            print('UNKNOWN_CASE %s (this entry offers: %s)' % (','.join(unknown), ','.join(ids)))
            return 9
        selected = [c for c in CASES if c['id'] in wanted]
    if o.expect and len(selected) != o.expect:
        print('SELECTION_COUNT want=%d got=%d ids=%s' % (o.expect, len(selected),
                                                         ','.join(c['id'] for c in selected)))
        return 9

    sub = 's3b_probe' if o.probe else 's3b_chain'
    scratch = os.path.abspath(o.scratch or os.path.join(PROJ, 'cadence_work', 'sc1_sim', sub))
    ev = os.path.join(PROJ, 'results', 'evidence')
    out_csv = o.out or os.path.join(ev, 'sc1_s3b_cases.csv')
    man_csv = o.manifest or os.path.join(ev, 'sc1_s3b_manifest.csv')
    samp_csv = o.samples or os.path.join(ev, 'sc1_s3b_waveform_samples.csv')
    id_csv = o.identity or os.path.join(ev, 'sc1_s3b_identity.csv')
    log_txt = o.log or os.path.join(ev, 'sc1_s3b_dependency_log.txt')
    if o.dry or o.probe:
        # a probe is a debug batch: its rows belong to its own scratch directory, never to the
        # official evidence paths a later delivery would otherwise have to overwrite (AGENTS rule 27)
        out_csv = os.path.join(scratch, 'dry_rows.csv') if o.dry else \
            os.path.join(scratch, 'probe_rows.csv')
        man_csv = os.path.join(scratch, 'probe_manifest.csv')
        samp_csv = os.path.join(scratch, 'probe_samples.csv')
        id_csv = os.path.join(scratch, 'probe_identity.csv')
        log_txt = os.path.join(scratch, 'probe_log.txt')
    if o.out:
        out_csv = o.out
    if o.manifest:
        man_csv = o.manifest
    if o.samples:
        samp_csv = o.samples
    if o.identity:
        id_csv = o.identity
    if o.log:
        log_txt = o.log

    authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
    if not authorised and not o.dry:
        # AGENTS rule 27: refuse BEFORE every write, including the probe's own scratch decks
        print('S3B_REFUSED run=%s authorisation=%s: RUN=1 AND QODER_SIM_AUTHORISED=1 are both '
              'required. No file under results/evidence is created, truncated or replaced, and no '
              'scratch deck is written.'
              % (os.environ.get('RUN') or 'unset', os.environ.get('QODER_SIM_AUTHORISED') or 'unset'))
        print('S3B_REFUSED would_have_been=%s' % ','.join(c['id'] for c in selected))
        return 5

    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    shas = write_cells(scratch)
    R = S2.Run([], [], 'S3B-%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    print('RUN_ID %s section=%s rails=1.8/3.3/3.3(vscan) stop=%s maxstep=%sn cases=%d '
          'gate_target_low<%s high>%s POC_WINDOW_STATE_TARGET'
          % (R.run_id, o.section, tnum(STOP_NS), fmt_v(MAXSTEP_NS), len(selected),
             fmt_v(GATE_LO_MAX), fmt_v(GATE_HI_MIN)))
    if o.probe:
        R.add('S3B_PROBE', 'all', 'one deck with the extra gate-terminal saves',
              'which hierarchical current names this build can read',
              'deck=%s.scs with mp1:2 and mp2:2 added; scratch=%s'
              % ('s3b_write_q1_light', scratch), 0, 'MEASURED_PLAN',
              'a probe is a measurement of the tool chain, not of the circuit')
    man_rows, samp_rows, id_rows = [], [], []
    for c in (find_case('s3b_write_q1_light'),) if o.probe else selected:
        safe_run(R, c['id'], scratch, man_rows, samp_rows, id_rows, o,
                 gate_term=o.probe or o.gate_term, dry=o.dry, gate_all=o.gate_all)

    if o.dry:
        for c in selected:
            R.add('DRY_DECK', c['id'], c['id'] + '.scs',
                  'the deck builds from the repository masters and the framework audits clean',
                  'sha256=%s lines=%d load=%s top=%s'
                  % (hashlib.sha256(build_deck(c, o.section).encode('utf-8')).hexdigest()[:16],
                     build_deck(c, o.section).count('\n'), c['load'],
                     FAULT_MASTER if c['fault'] else TOP_MASTER), 0, 'MEASURED_PLAN',
                  'dry only: nothing ran and no official evidence file was touched')
        R.add('DRY_PLAN', 'all', 'the nine declared cases', 'named by this entry, not by hand',
              ','.join(c['id'] for c in selected), 0, 'MEASURED_PLAN',
              'the fault case is the ninth and needs the reference deck in the same scratch')
        S2.write_rows(out_csv, R.rows, ROWS_HDR)
        dry_bad = [r for r in R.rows if r[7] in ('BLOCKED', 'FAIL')]
        print('DRY rows=%d blocked_or_fail=%d decks_in=%s csv=%s'
              % (len(R.rows), len(dry_bad), scratch, out_csv))
        for r in dry_bad[:4]:
            print('DRY_PROBLEM %s | %s | %s' % (r[1], r[2], r[5][:150]))
        return 0 if not dry_bad else 8

    dep, dut = process_counts(scratch)
    R.add('S3B_PROCESS_COUNT', 'all', 'preflight dependency runs vs DUT runs in this scratch',
          'counted from the files this directory keeps', 'preflight=%d DUT=%d' % (dep, dut), 0,
          'MEASURED', 'tb_preflight.sh FULL mode runs its own operating point, which is a dependency '
                      'process and not a circuit run; debug retries live in other directories')
    R.add('S3B_MASTER_BYTES', 'all', 'the masters this run placed next to its decks',
          'sha256 of each repository file, so the reviewer can compare with the Git blob',
          ' '.join('%s=%s' % (f, shas[f][:12]) for f in sorted(shas)), 0, 'MEASURED',
          'the four reviewed files must hash the same as the accepted round; the two new masters are '
          'this round\'s own bytes')
    if o.lib_sha or o.mdl_sha:
        R.add('S3B_PDK_IDENTITY', 'all', 'the PDK digests passed on the command line',
              'lib / mdl / README / the mis mdl the tt section pulls, as hashes only',
              'lib=%s mdl=%s readme=%s mis=%s' % (o.lib_sha[:16] or 'NOT_PASSED',
                                                  o.mdl_sha[:16] or 'NOT_PASSED',
                                                  o.readme_sha[:16] or 'NOT_PASSED',
                                                  o.mis_sha[:16] or 'NOT_PASSED'), 0, 'MEASURED',
              'identity by hash; no PDK content, model card or vendor path is committed')

    S2.write_rows(out_csv, R.rows, ROWS_HDR)
    S2.write_rows(man_csv, man_rows, MAN_HDR)
    S2.write_rows(samp_csv, samp_rows, SAMP_HDR)
    S2.write_rows(id_csv, id_rows, ID_HDR)
    with io.open(log_txt, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u('\n'.join(S2.scrub(l) for l in R.log)) + u('\n'))
    func_fail = len([r for r in R.rows if r[7] == 'FAIL'])
    dep_fail = len([r for r in R.rows if r[7] in ('BLOCKED', 'NOT_AVAILABLE')])
    detected = len([r for r in R.rows if r[7] == 'DETECTED'])
    print('S3B_TT run_id=%s rows=%d decks=%d samples=%d functional_FAIL=%d dependency=%d '
          'fault_detected=%d' % (R.run_id, len(R.rows), len(man_rows), len(samp_rows), func_fail,
                                 dep_fail, detected))
    print('S3B_TT cases=%s out=%s' % (','.join(c['id'] for c in selected), rel(out_csv)))
    return 0 if man_rows else 8


if __name__ == '__main__':
    sys.exit(main())

