# -*- coding: utf-8 -*-
"""SCAN-1 R3: one scan channel's control chain, really wired and really simulated.

    python scripts/sc1_r2e3_placeholder.py --dry --expect 9        # text only, nothing runs
    RUN=1 QODER_SIM_AUTHORISED=1 python scripts/sc1_r3_chain_tt.py --expect 9

What is new here is only the CONNECTION. `spectre/sc1_r3_scan_chain.scs` instantiates the accepted
c2mos_dff, sc1_scan_gate and sc1_ls_c1_top_r2d; q, qbar and en are inter-module nodes that no source
touches, so the run answers a question the three separate单元 never did: does the chain still select
and still blank once the blocks are actually together.

Case set (fixed, from the task book): 8 normal + 1 real negative.

  r3_q0_off            Q stays 0 with the guard valid          -> en low,  gate33 high
  r3_write_q1_on       a legal clock writes 1                  -> en high, gate33 low
  r3_blank_assert      blank rises while Q stays 1             -> en low,  gate33 high, Q untouched
  r3_blank_release     blank falls again, away from an edge     -> en high, gate33 low, no rewrite
  r3_write_q0_off      a legal clock writes 0 back              -> en low,  gate33 high
  r3_repeat_101        1 -> 0 -> 1 through real clocks          -> three attributed responses
  r3_external_guard    core_ok33 pulled low and restored        -> gate33 high while en/Q stay chosen
  r3_load5p            the assert/release timeline at 5 pF      -> same logic, new timing figures
  r3_fault_blank_tied_vss  ONLY the wrapper's blank pin goes to vss; the external blank still toggles

Stimulus framework (POC_ASSUMPTION, not a setup/hold budget): clock period 100 ns, high/low 50 ns,
every edge 2 ns, a data change at least 20 ns before the rising edge that samples it, a blank or
guard change at least 20 ns from any rising edge, stop 900 ns at maxstep 0.1 ns. The DFF has no reset,
so every case starts blank high, core_ok33 low and d low and takes TWO real rising edges before
anything is judged; the established state is read back, never forced.

Every rule above is applied to the generated PWL and re-measured from the waveforms -- the deck does
not get to claim a timing it did not emit. Judgement is whole-window (a high claim needs the window
MINIMUM, a low claim the MAXIMUM, with at least 10 samples), transitions are measured in intervals
separate from those plateau windows, and each propagation is attributed by the audited tool's own 50 %
crossing plus the next crossing of either direction. Nothing sums per-block delays into an end-to-end
figure: clk -> gate33 is measured directly as well.

The three cell files, the audited reader/delay/supply tools and the shared call contract are read,
never edited; `scripts/sc1_r2e1_call_contract.py` decides every preflight and runner outcome, so no
call is judged from a pipeline's exit status again.
"""
from __future__ import print_function

import hashlib
import io
import optparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sc1_r2e1_call_contract as CC
import sc1_r2e_s2_tt as S2                    # Run, the reader/delay/vtx hooks, scrub, csv writing
import sc1_r2e1_reread as R1                  # the interpolated 50% crossing list used for samples

try:
    _text = unicode
except NameError:
    _text = str

CELLS = ('C2MOS_DFF.scs', 'sc1_scan_gate.scs', 'sc1_level_shifter_r2d.scs', 'sc1_r3_scan_chain.scs')
WRAPPER = 'sc1_r3_scan_chain.scs'
CELL_MASTER = {'C2MOS_DFF.scs': 'c2mos_dff', 'sc1_scan_gate.scs': 'sc1_scan_gate',
               'sc1_level_shifter_r2d.scs': 'sc1_ls_c1_top_r2d'}
SUPPLY_MAP = 'vdd=1.8 vdd18=1.8 vdd33=3.3 vss=0'

# ---- the framework, one place (POC_ASSUMPTION: these are stimulus choices, not a budget)
PERIOD = 100.0                 # ns
RAISE0 = 50.0                  # centre of the first rising edge
FALL0 = 100.0                  # centre of the first falling edge
EDGE_NS = 2.0                  # every edge is 2 ns, 1 ns either side of its centre
STOP_NS = 900.0
MAXSTEP_NS = 0.1
SETUP_AHEAD = 20.0             # a data change must lead its sampling rising edge by this much
GUARD_AWAY = 20.0              # blank / core_ok33 must stay this far from any rising edge
WINDOW_AHEAD = 20.0            # a judgement window starts this far after its causing edge
MIN_SAMPLES = 10               # the book's floor for a whole-window state claim
V18 = 1.8
V33 = 3.3
LO = 0.0

RISE = [RAISE0 + PERIOD * k for k in range(9)]                 # 50 .. 850 ns
FALL = [FALL0 + PERIOD * k for k in range(8)]                  # 100 .. 800 ns
CENTRES = sorted(RISE + FALL)


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def tnum(t):
    """ns -> the deck's own spelling; all framework times are multiples of 1 ns"""
    return ('%d' % int(round(t))) + 'n'


def wave(pairs):
    """[(t_ns, value)] -> 'wave=[0 0 49n 0 51n 1.8 ...]' with a 2 ns ramp centred on every step.

    The points are collapsed by time so a step landing on the run end never emits two entries for
    the same instant, and every pair stays strictly ordered -- an out-of-order PWL is accepted by
    some tools and silently wrong in others.
    """
    pts = [(0.0, pairs[0][1])]
    prev = pairs[0][1]
    for t, v in pairs[1:]:
        if abs(v - prev) < 1e-12:
            pts.append((t, v))
            continue
        pts.append((t - EDGE_NS / 2.0, prev))
        pts.append((t + EDGE_NS / 2.0, v))
        prev = v
    pts.append((STOP_NS, prev))
    clean = []
    for t, v in pts:
        t = min(max(t, 0.0), STOP_NS)
        if clean and abs(clean[-1][0] - t) < 1e-9:
            clean[-1] = (t, v)
        else:
            clean.append((t, v))
    toks = []
    for t, v in clean:
        toks.append('0' if t == 0.0 else tnum(t))
        toks.append(fmt_v(v))
    return '[' + ' '.join(toks) + ']'


def fmt_v(v):
    """voltage, current or capacitance in the deck's own spelling.

    `%.6g` keeps zero as `0` -- the earlier rstrip-of-zeros spelling turned 0.0 into an empty token,
    which silently truncated a PWL pair, so this formatter is deliberately simple.
    """
    if isinstance(v, float):
        return '%.6g' % v
    return u(v)


def step_wave(start, steps):
    """a constant level with 2 ns ramps at each declared (t_ns, value) step"""
    return wave([(0.0, start)] + list(steps))


def clk_wave():
    pts = [(0.0, 0.0)]
    hi = False
    for c in CENTRES:
        hi = not hi
        pts.append((c, V18 if hi else 0.0))
    if hi:
        pts.append((FALL[-1] + PERIOD if CENTRES[-1] < 899 else STOP_NS, V18))
    return wave(pts)


# ------------------------------------------------------------------ the case table
def case(cid, **kw):
    kw['id'] = cid
    return kw


def win(label, t0, t1, expect, cause=None, note='', refusable=False):
    out = {'label': label, 't0': t0, 't1': t1, 'expect': expect, 'cause': cause, 'note': note}
    if refusable:
        out['refusable'] = True
    return out


# every `d` change is 30 ns before a rising edge (> 20 ns), every blank/guard change sits on a falling
# edge centre (50 ns from any rising edge); the windows open 20 ns after the edge they judge.
ESTAB = win('established_Q0', 160.0, 190.0, {'q': 'low', 'qbar': 'high'}, cause=150.0,
            note='after TWO real rising edges (50 and 150 ns) with d=0, blank high and the guard low')

CASES = [
    case('r3_q0_off',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33)],
         windows=[ESTAB,
                  win('hold_off_250', 270.0, 290.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=250.0),
                  win('hold_off_450', 470.0, 490.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=450.0)],
         delays=[], edges=[], purpose='a reset-free chain that was never written must leave the gate off'),
    case('r3_write_q1_on',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('selected_350', 370.0, 390.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=350.0)],
         delays=[('clk_up', 'clk', 'rise', V18, 'q', 'rise', 245.0, 300.0),
                 ('clk_up_to_en', 'clk', 'rise', V18, 'en', 'rise', 245.0, 300.0),
                 ('clk_up_to_gate33_end_to_end', 'clk', 'rise', V18, 'gate33', 'fall', 245.0, 320.0),
                 ('en_up_to_gate33_down', 'en', 'rise', V18, 'gate33', 'fall', 245.0, 320.0)],
         edges=['fall'], purpose='one legal write selects the channel'),
    case('r3_blank_assert',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (400.0, 'blank', V18)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('blanked_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=400.0,
                      note='Q keeps its value: blank acts on the output, it does not clear the store')],
         delays=[('blank_up_to_en_down', 'blank', 'rise', V18, 'en', 'fall', 395.0, 440.0),
                 ('blank_up_to_gate33_up', 'blank', 'rise', V18, 'gate33', 'rise', 395.0, 440.0)],
         edges=['fall', 'rise'], purpose='asserting blank must switch the gate off within its own edge'),
    case('r3_blank_release',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (300.0, 'blank', V18), (500.0, 'blank', 0.0)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('blanked_350', 370.0, 390.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=300.0),
                  win('released_550', 570.0, 590.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=500.0,
                      note='no rewrite: the stored Q was kept while blank was high')],
         delays=[('blank_up_to_en_down', 'blank', 'rise', V18, 'en', 'fall', 295.0, 340.0),
                 ('blank_down_to_en_up', 'blank', 'fall', V18, 'en', 'rise', 495.0, 540.0),
                 ('blank_down_to_gate33_down', 'blank', 'fall', V18, 'gate33', 'fall', 495.0, 545.0)],
         edges=['fall', 'rise'], purpose='releasing blank away from a sampling edge must re-select'),
    case('r3_write_q0_off',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (320.0, 'd', 0.0)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('deselected_350', 370.0, 390.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=350.0)],
         delays=[('clk_up_to_q_down', 'clk', 'rise', V18, 'q', 'fall', 345.0, 400.0),
                 ('clk_up_to_gate33_up_end_to_end', 'clk', 'rise', V18, 'gate33', 'rise', 345.0, 420.0)],
         edges=['fall', 'rise'], purpose='a legal write of 0 must switch the channel back off'),
    case('r3_repeat_101',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (320.0, 'd', 0.0), (420.0, 'd', V18)],
         windows=[ESTAB,
                  win('state_1_after_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('state_0_after_350', 370.0, 390.0,
                      {'q': 'low', 'qbar': 'high', 'en': 'low', 'gate33': 'high'}, cause=350.0),
                  win('state_1_after_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=450.0)],
         delays=[('edge1_gate33_down', 'clk', 'rise', V18, 'gate33', 'fall', 245.0, 300.0),
                 ('edge2_gate33_up', 'clk', 'rise', V18, 'gate33', 'rise', 345.0, 400.0),
                 ('edge3_gate33_down', 'clk', 'rise', V18, 'gate33', 'fall', 445.0, 500.0)],
         edges=['fall', 'rise'], purpose='three cycles, each response attributed to its own edge'),
    case('r3_external_guard',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (400.0, 'core_ok33', 0.0), (600.0, 'core_ok33', V33)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('guarded_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'high'}, cause=400.0,
                      note='the guard forces the gate off WITHOUT changing Q or en'),
                  win('guard_back_650', 670.0, 690.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=600.0)],
         delays=[('guard_down_to_gate33_up', 'core_ok33', 'fall', V33, 'gate33', 'rise', 395.0, 445.0),
                 ('guard_up_to_gate33_down', 'core_ok33', 'rise', V33, 'gate33', 'fall', 595.0, 645.0)],
         edges=['fall', 'rise'],
         purpose='the EXTERNAL guard path only: no on-chip undervoltage detector is claimed'),
    case('r3_load5p', load=5.0,
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (300.0, 'blank', V18), (500.0, 'blank', 0.0)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('blanked_350', 370.0, 390.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=300.0),
                  win('released_550', 570.0, 590.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=500.0)],
         delays=[('blank_up_to_en_down', 'blank', 'rise', V18, 'en', 'fall', 295.0, 340.0),
                 ('blank_down_to_gate33_down', 'blank', 'fall', V18, 'gate33', 'fall', 495.0, 560.0)],
         edges=['fall', 'rise'], purpose='the same timeline with the heavier declared load'),
    case('r3_fault_blank_tied_vss', fault='blank_to_vss',
         actions=[(200.0, 'blank', 0.0), (200.0, 'core_ok33', V33), (220.0, 'd', V18),
                  (400.0, 'blank', V18)],
         windows=[ESTAB,
                  win('selected_250', 270.0, 290.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'high', 'gate33': 'low'}, cause=250.0),
                  win('blanked_450', 470.0, 490.0,
                      {'q': 'high', 'qbar': 'low', 'en': 'low', 'gate33': 'high'}, cause=400.0,
                      refusable=True,
                      note='the NORMAL blank assertion; with the pin tied to vss it must be refused')],
         delays=[], edges=[],
         purpose='a real wiring fault: the cell pin is at vss while the external blank still toggles'),
]


def find_case(cid):
    for c in CASES:
        if c['id'] == cid:
            return c
    return None


# ------------------------------------------------------------------ stimulus audit
def edge_times(steps):
    return [t for t, _v in steps]


def audit_frame(case_def, problems):
    """the framework's own numbers, checked against what the deck is about to emit"""
    rows = []
    acts = list(case_def['actions'])
    d_changes = [t for t, sig, _v in acts if sig == 'd']
    other = [t for t, sig, _v in acts if sig in ('blank', 'core_ok33')]
    for t in d_changes:
        ahead = min([r - t for r in RISE if r > t + 1e-9])
        rows.append(('DATA_SETUP', 'd change at %s ns leads the next rising edge by %.1f ns '
                     '(need >= %.0f)' % (tnum(t), ahead, SETUP_AHEAD),
                     'PASS' if ahead >= SETUP_AHEAD - 1e-9 else 'BLOCKED'))
        if ahead < SETUP_AHEAD - 1e-9:
            problems.append('%s: data change at %s ns is only %.1f ns before its edge'
                            % (case_def['id'], tnum(t), ahead))
    for t in other:
        away = min([abs(t - r) for r in RISE])
        rows.append(('GUARD_SPACING', '%s ns change is %.1f ns from the nearest rising edge '
                     '(need >= %.0f)' % (tnum(t), away, GUARD_AWAY),
                     'PASS' if away >= GUARD_AWAY - 1e-9 else 'BLOCKED'))
        if away < GUARD_AWAY - 1e-9:
            problems.append('%s: blank/guard change at %s ns is %.1f ns from a rising edge'
                            % (case_def['id'], tnum(t), away))
    for w in case_def['windows']:
        t0, t1 = w['t0'], w['t1']
        near = min([min(abs(t0 - c), abs(t1 - c)) for c in CENTRES])
        samples = int(round((t1 - t0) / MAXSTEP_NS)) + 1
        ramp_free = near >= EDGE_NS / 2.0 + 1.0
        ok = samples >= MIN_SAMPLES and ramp_free
        rows.append(('WINDOW', '%s [%s..%s] ns: %d samples, %.1f ns clear of any ramp'
                     % (w['label'], tnum(t0), tnum(t1), samples, near),
                     'PASS' if ok else 'BLOCKED'))
        if not ok:
            problems.append('%s: window %s is too short (%d samples) or too close to an edge'
                            % (case_def['id'], w['label'], samples))
    return rows


def stimulus_rows(case_def):
    """the framework written out as the PWL flip points the deck actually carries"""
    out = []
    for sig, net, val in (('d', 'd', V18), ('clk', 'clk', V18), ('blank', 'blank', V18),
                          ('core_ok33', 'core_ok33', V33)):
        steps = frame_steps(case_def, sig)
        flips = ', '.join('%s->%s' % (tnum(t), fmt_v(v)) for t, v in steps)
        out.append((sig, net, fmt_v(val), flips or 'constant'))
    return out


def frame_steps(case_def, sig):
    start = {'d': 0.0, 'clk': 0.0, 'blank': V18, 'core_ok33': 0.0}[sig]
    steps = []
    if sig == 'clk':
        hi = False
        for c in CENTRES:
            hi = not hi
            steps.append((c, V18 if hi else 0.0))
        return steps
    for t, s, v in sorted(case_def['actions']):
        if s == sig:
            steps.append((t, v))
    return steps


# ------------------------------------------------------------------ deck
DECK_TOP = '''simulator lang=spectre insensitive=yes
// SCAN-1 R3 single-channel control chain: %s
// model binding comes from the git-ignored spectre/pdk_local.env; run_spectre.sh refuses an
// unexpanded ${QODER_PDK_LIB}, so every deck here is bound before it runs.
include "${QODER_PDK_LIB}" section=%s
'''

CELL_INCLUDES = ''.join(['include "%s"\n' % c for c in CELLS])

SAVES = ('save d clk blank core_ok33 gate33 vdd18 vdd33 vss\n'
         'save Xchain.q Xchain.qbar Xchain.en\n'
         '// the rail branch is read at the source itself, the sign rule the R2E calibration measured:\n'
         '// a rail that DELIVERS I amps is saved as -I, so injected = -(Vx:i).\n'
         'save V18:i V33:i\n')


def build_deck(case_def, section='tt'):
    lines = [DECK_TOP % (case_def['purpose'], section)]
    lines.append(CELL_INCLUDES)
    lines.append('// temperature is read back from the produced log and psf header; the instantiation\n'
                 '// form is what this build accepts (a bare `options temp=27\' is SFE-709).\n'
                 'simopt options temp=27\n')
    lines.append('Vd (d 0) vsource dc=0 type=pwl wave=%s\n' % wave([(0.0, 0.0)] +
                                                              [(t, v) for t, s, v in
                                                               sorted(case_def['actions'])
                                                               if s == 'd']))
    lines.append('Vclk (clk 0) vsource dc=0 type=pwl wave=%s\n' % clk_wave())
    lines.append('Vbl (blank 0) vsource dc=%s type=pwl wave=%s\n' % (
        fmt_v(V18), wave([(0.0, V18)] + [(t, v) for t, s, v in sorted(case_def['actions'])
                                                    if s == 'blank'])))
    lines.append('Vok (core_ok33 0) vsource dc=0 type=pwl wave=%s\n' % wave(
        [(0.0, 0.0)] + [(t, v) for t, s, v in sorted(case_def['actions']) if s == 'core_ok33']))
    lines.append('V18 (vdd18 0) vsource dc=%s\n' % fmt_v(V18))
    lines.append('V33 (vdd33 0) vsource dc=%s\n' % fmt_v(V33))
    lines.append('Vss (vss 0) vsource dc=0\n')
    inst = 'Xchain (d clk blank core_ok33 gate33 vdd18 vdd33 vss) sc1_r3_scan_chain_1ch\n'
    if case_def.get('fault') == 'blank_to_vss':
        # the ONLY change: this instance's blank pin goes to the vss net. The external blank source
        # and its waveform stay exactly as in the reference case, so the difference is the pin.
        inst = 'Xchain (d clk vss core_ok33 gate33 vdd18 vdd33 vss) sc1_r3_scan_chain_1ch\n'
    lines.append(inst)
    lines.append('Cload (gate33 0) capacitor c=%se-12\n' % fmt_v(case_def.get('load', 1.0)))
    lines.append('sw1 tran stop=%s maxstep=%s\n' % (tnum(STOP_NS), '%sn' % MAXSTEP_NS))
    lines.append(SAVES)
    return ''.join(lines)


def fault_diff(ref_txt, fault_txt):
    """the deck-level proof that only the blank pin moved.

    Comment lines are reported separately instead of being ignored: the faulted case carries its own
    purpose line, and a reviewer should see that the difference is a comment plus exactly one
    netlist statement, not have to trust that a filter dropped nothing relevant.
    """
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


# ------------------------------------------------------------------ static identity
def parse_cell_masters():
    text = ''
    for c in CELLS:
        text += u(io.open(os.path.join(PROJ, 'spectre', c), encoding='utf-8',
                          errors='replace').read()) + '\n'
    return S2.parse_masters(text)


def chain_devices():
    """every MOS the wrapper reaches, addressed the way the simulator saves it"""
    deck = 'Xchain (d clk blank core_ok33 gate33 vdd18 vdd33 vss) sc1_r3_scan_chain_1ch\n'
    text = ''
    for c in CELLS:
        text += u(io.open(os.path.join(PROJ, 'spectre', c), encoding='utf-8',
                          errors='replace').read()) + '\n'
    return S2.resolve_devices(deck, text)


# ------------------------------------------------------------------ measurement
DOMAIN = {'d': V18, 'clk': V18, 'blank': V18, 'q': V18, 'qbar': V18, 'en': V18,
          'core_ok33': V33, 'gate33': V33}
GATE_LO, GATE_HI = 0.30, 3.135          # POC_ASSUMPTION screening pair for the 3.3 V output


def level_pair(sig):
    if sig == 'gate33':
        return GATE_LO, GATE_HI, 'POC_ASSUMPTION screening levels for the 3.3 V scan gate node'
    half = 0.5 * DOMAIN[sig]
    return half, half, 'the %.1f V domain 50%% level' % DOMAIN[sig]


def measure_window(R, cid, data, w):
    """one state claim per signal, judged over the whole window with the reader's own sample floor"""
    for sig, want in sorted(w['expect'].items()):
        # the windows are declared in ns and the reader takes seconds; mixing them up silently asks
        # for samples in a window 1e9 times too wide and every claim comes back TOO_FEW_SAMPLES
        t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
        path = sig if sig in ('gate33', 'd', 'clk', 'blank', 'core_ok33') else 'Xchain.%s' % sig
        rcn, mn = S2.read_sig(R, data, path, 'min', t0, t1, req=str(MIN_SAMPLES))
        rcx, mx = S2.read_sig(R, data, path, 'max', t0, t1, req=str(MIN_SAMPLES))
        if rcn != 0 or rcx != 0:
            R.add('R3_WINDOW_STATE', cid, '%s @ %s' % (path, w['label']),
                  'window min and max readable with >= %d samples' % MIN_SAMPLES,
                  (mn if rcn else mx)[:70], rcn or rcx, 'BLOCKED',
                  'reader exit kept; a state is never inferred from a label')
            continue
        a, b = float(mn), float(mx)
        lo_t, hi_t, how = level_pair(sig)
        ok = (a >= hi_t) if want == 'high' else (b <= lo_t)
        verdict = 'PASS' if ok else ('EXPECTED_REFUSAL' if w.get('refusable') else 'FAIL')
        R.add('R3_WINDOW_STATE', cid, '%s @ %s' % (path, w['label']),
              '%s throughout: %s (high min >= %.3f V / low max <= %.3f V)'
              % (want, how, hi_t, lo_t),
              'min=%.6g max=%.6g V' % (a, b), 0, verdict,
              'whole window %s..%s s, not one extreme sample%s'
              % (t0, t1, '; this is the assertion the wiring fault must fail'
                 if w.get('refusable') else ''))


def measure_stimulus(R, cid, data, case_def):
    """the inputs are read back from the waveforms, so the framework is not just generator text"""
    t_end = '%.9g' % (STOP_NS * 1e-9)
    for sig, net, start, flips in stimulus_rows(case_def):
        rcn, mn = S2.read_sig(R, data, net, 'min', '0', t_end, req='10')
        rcx, mx = S2.read_sig(R, data, net, 'max', '0', t_end, req='10')
        if rcn or rcx:
            R.add('R3_STIMULUS_READBACK', cid, net, 'the deck drives this net',
                  (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
                  'the source or the save is missing; the declared flip list is not evidence')
            continue
        R.add('R3_STIMULUS_READBACK', cid, net, 'declared flips %s' % flips[:70],
              'window min=%.6g max=%.6g V' % (float(mn), float(mx)), 0, 'MEASURED',
              'read over the whole run; the state rows below judge the windows')


def measure_delays(R, cid, groups, axis, data, case_def):
    """the audited tool's own attribution verdict, plus the 50 % -> 50 % number it refuses to certify

    `AMBIGUOUS_RESOLUTION` / `OUTSIDE_ATTRIBUTION` from scripts/sc1_delay.py are not circuit
    failures and are not quietly re-labelled PASS either: they say the output's 10-90 % event BEGAN
    before the input reached its own 50 % level, so the two cannot be ordered at this sampling
    resolution. That is what a latch-based master stage does on a 2 ns clock ramp, and it is a fact
    about the measurement convention. The row therefore keeps the tool's refusal, and the
    R3_PROPAGATION_50_50 row next to it reports the interpolated 50 % crossings with the attribution
    bound, flagged whenever the onset overlaps the input ramp.
    """
    for label, sin, ein, vin, sout, eout, t0, t1 in case_def['delays']:
        p_in = sin if sin in ('gate33', 'core_ok33', 'd', 'clk', 'blank') else 'Xchain.%s' % sin
        p_out = sout if sout in ('gate33', 'core_ok33', 'd', 'clk', 'blank') else 'Xchain.%s' % sout
        cmd = ('%s --data "%s" --mode propdelay --sig-in "%s" --sig-out "%s" --vdd-in %s '
               '--vdd-out %s --edge-in %s --edge-out %s --t0 %.9g --t1 %.9g'
               % (S2.delay_cmd(), data, p_in, p_out, fmt_v(vin), fmt_v(DOMAIN[sout]), ein, eout,
                  t0 * 1e-9, t1 * 1e-9))
        rc, out = CC.call(cmd)
        head = out.strip().split('\n')[0]
        answered = rc == 0 and head.startswith('PROPDELAY')
        overlap = ('AMBIGUOUS_RESOLUTION' in out) or ('OUTSIDE_ATTRIBUTION' in out)
        refused = any(k in out for k in ('NO_RESPONSE', 'NO_EDGE', 'NO_HALF_CROSSING'))
        if answered:
            verdict = 'PASS'
        elif overlap:
            verdict = 'NOT_MEASURED_OVERLAP'
        elif refused:
            verdict = 'FAIL'
        else:
            verdict = 'BLOCKED'
        R.add('R3_PROPDELAY', cid, '%s (%s..%s ns)' % (label, tnum(t0), tnum(t1)),
              'an answer attributed to this input edge, inside its own window',
              head[:150], rc, verdict, S2.scrub(out).replace('\n', ' | ')[:150])
        propagation_5050(R, cid, groups, axis, label, sin, sout, vin, DOMAIN[sout], ein, eout, t0, t1)


def _near(xs, t_ref, after_only=True):
    """the first crossing at/after t_ref, or the LAST one at/before it.

    Returning pool[0] for the 'at or before' case reads an earlier cycle's edge instead of the nearest
    one, and a non-strict lower bound makes the attribution bound equal t_in itself -- both made every
    R3_PROPAGATION_50_50 row report OUT_OF_ATTRIBUTION on a perfectly good measurement.
    """
    if after_only:
        pool = [x for x in xs if x[1] >= t_ref - 1e-18]
        return pool[0] if pool else None
    pool = [x for x in xs if x[1] <= t_ref + 1e-18]
    return pool[-1] if pool else None


def _next_after(xs, t_ref):
    for x in xs:
        if x[1] > t_ref + 1e-15:
            return x
    return None


def propagation_5050(R, cid, groups, axis, label, sin, sout, vin, vout, ein, eout, t0, t1):
    p_in = sin if sin in ('gate33', 'core_ok33', 'd', 'clk', 'blank') else 'Xchain.%s' % sin
    p_out = sout if sout in ('gate33', 'core_ok33', 'd', 'clk', 'blank') else 'Xchain.%s' % sout
    # the audited convention: an input 50 % crossing, the OUTPUT's own 50 % crossing, and the next
    # crossing of the INPUT in either direction as the attribution bound
    xs_in = R1.crossing_times(groups, axis, p_in, 0.5 * vin)
    xs_out = R1.crossing_times(groups, axis, p_out, 0.5 * vout)
    hit_in = _near(xs_in, t0 * 1e-9)
    if not hit_in:
        R.add('R3_PROPAGATION_50_50', cid, label, 'an input 50% crossing at or after %s ns'
              % tnum(t0), 'NONE_IN_WINDOW', 0, 'NOT_AVAILABLE',
              'nothing is measured from a window that contains no input edge')
        return
    tin = hit_in[1]
    nxt = _next_after(xs_in, tin)
    hit_out = _near(xs_out, tin)
    if not hit_out:
        R.add('R3_PROPAGATION_50_50', cid, label, 'an output 50% crossing at or after t_in',
              'NONE_AFTER_T_IN t_in=%.9g s' % tin, 0, 'NO_RESPONSE',
              'the output never reached its 50% level after this input edge')
        return
    tout = hit_out[1]
    # the 10 % onset of the output event, to show WHEN the overlap starts
    lo_frac = 0.10 if eout == 'rise' else 0.90
    xs_on = R1.crossing_times(groups, axis, p_out, lo_frac * vout)
    onset = _near(xs_on, tout, after_only=False)
    inside = (nxt is None) or (tout < nxt[1] - 1e-15)
    R.add('R3_PROPAGATION_50_50', cid, label,
          't_out - t_in between the two 50%% crossings, attributed inside [t_in, t_next)',
          't_in=%.9g t_out=%.9g delta=%.3f ns ; t_next=%s ; output 10%% onset=%s'
          % (tin, tout, (tout - tin) * 1e9, ('%.9g' % nxt[1]) if nxt else 'END_OF_DATA',
             ('%.9g' % onset[1]) if onset else '?'), 0,
          'MEASURED' if inside else 'OUT_OF_ATTRIBUTION',
          'interpolated from the saved samples; onset %s t_in, which is why the audited event-order '
          'test refuses a certified delay here'
          % ('precedes' if (onset and onset[1] < tin) else 'follows'))


def measure_edges(R, cid, data, case_def):
    want = set(case_def.get('edges') or [])
    for edge in ('rise', 'fall'):
        if edge not in want:
            R.add('R3_EDGE', cid, 'gate33 %s' % edge, 'not defined by this timeline',
                  'the case list declares which output edges its own stimulus produces', 0,
                  'EXPECTED_REFUSAL', 'the edge tool is not asked for an edge nobody stimulates')
            continue
        cmd = ('%s --data "%s" --sig gate33 --vdd %s --mode edge --edge %s --t0 %.9g --t1 %.9g'
               % (S2.delay_cmd(), data, fmt_v(V33), edge,
                  200e-9, STOP_NS * 1e-9))
        rc, out = CC.call(cmd)
        head = out.strip().split('\n')[0]
        ok = rc == 0 and head.startswith('EDGE')
        R.add('R3_EDGE', cid, 'gate33 %s over the run' % edge, 'a complete 10-90% event',
              head[:150], rc, 'PASS' if ok else ('FAIL' if 'NO_EDGE' in out else 'BLOCKED'),
              S2.scrub(out).replace('\n', ' | ')[:150])


def measure_plateau(R, cid, data, w):
    a, b = w['t0'], w['t1']
    lo = b - 0.25 * (b - a)
    for sig in ('en', 'gate33'):
        path = sig if sig == 'gate33' else 'Xchain.%s' % sig
        cmd = ('%s --data "%s" --mode steady --sig "%s" --t0 %.9g --t1 %.9g --require-n %d'
               % (S2.delay_cmd(), data, path, lo * 1e-9, b * 1e-9, MIN_SAMPLES))
        rc, out = CC.call(cmd)
        head = out.strip().split('\n')[0]
        ok = rc == 0 and head.startswith('STEADY')
        R.add('R3_PLATEAU', cid, '%s @ %s' % (path, w['label']),
              'a steady reading in the last quarter of the window, >= %d samples' % MIN_SAMPLES,
              head[:150], rc, 'PASS' if ok else ('FAIL' if 'TOO_FEW' in out else 'BLOCKED'),
              'the level itself is judged by the window rows; this row is about sampling coverage')


def measure_rails(R, cid, data, case_def):
    """direct source-branch current and the TIME of its extreme, from the strict tool"""
    t0, t1 = '%.9g' % (200e-9), '%.9g' % (STOP_NS * 1e-9)
    for src, rail in (('V18:i', 'vdd18'), ('V33:i', 'vdd33')):
        rcn, mn = S2.read_sig(R, data, src, 'min', t0, t1, req=str(MIN_SAMPLES))
        rcx, mx = S2.read_sig(R, data, src, 'max', t0, t1, req=str(MIN_SAMPLES))
        if rcn or rcx:
            R.add('R3_RAIL_CURRENT', cid, src, 'direct source-branch current readable',
                  (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
                  'kept as a save/read failure; no drain sum is substituted and nothing is zeroed')
            continue
        R.add('R3_RAIL_CURRENT', cid, src, 'injected into the chain = -(Vx:i)',
              'window min=%.6g max=%.6g A -> injected %.6g .. %.6g A (rail %s)'
              % (float(mn), float(mx), -float(mx), -float(mn), rail), 0, 'MEASURED',
              'no current or power budget exists for this POC, so no limit is invented')
        for mode in ('max', 'min'):
            rcd, val, txt = S2.read_diff(R, data, src, 'vss', mode, '200e-9',
                                         '%.9g' % (STOP_NS * 1e-9))
            parts = txt.split('\t')
            R.add('R3_RAIL_PEAK', cid, '%s %s over the run' % (src, mode),
                  'the extreme and the sample time it happened at, from the strict tool '
                  '(B is the 0 V reference net, so A-B is the signed source current)',
                  'value=%s A at t=%s s' % (parts[0], parts[1] if len(parts) > 1 else '?'),
                  rcd, 'MEASURED' if not rcd else 'NOT_AVAILABLE',
                  'raw signed reading kept; injected = -value')


# ------------------------------------------------------------------ sampling for the reviewer
def emit_samples(R, rows, cid, data, case_def, groups, axis):
    """the real samples around one end-to-end switching event, nothing interpolated"""
    ref = [w for w in case_def['windows'] if w['cause']]
    if not ref:
        return
    cause = ref[0]['cause']
    qs = []
    for sig, path, lvl in (('clk', 'clk', 0.9), ('q', 'Xchain.q', 0.9),
                           ('en', 'Xchain.en', 0.9), ('gate33', 'gate33', 1.65)):
        xs = R1.crossing_times(groups, axis, path, lvl)
        after = [x for x in xs if x[1] >= cause * 1e-9 - 1e-18]
        qs.append((sig, path, after[0] if after else None))
    found = [(sig, hit[1]) for sig, _p, hit in qs if hit]
    rows.append([cid, 'end_to_end_event_list', '%s' % cause,
                 ' ; '.join('%s crossing at %.9g s' % ft for ft in found),
                 'the first 50% crossing of each node at or after the declared cause time',
                 'MEASURED'])
    for sig, path, hit in qs:
        if not hit:
            rows.append([cid, 'segment', sig, '-', 'NO_CROSSING at or after %.1f ns: nothing is '
                         'invented' % cause, 'NO_CROSSING'])
            continue
        idx = hit[0]
        for i in range(max(0, idx - 2), min(len(groups), idx + 3)):
            g = groups[i]
            vals = ' '.join('%s=%.6g' % (p, g[p]) for _s, p, _h in qs if p in g)
            rows.append([cid, 'segment', '%s around its 50%% crossing' % sig, '%.9g' % g[axis],
                         vals, 'MEASURED_SAMPLE'])


# ------------------------------------------------------------------ orchestration
MAN_HDR = ['run_id', 'case', 'deck', 'deck_sha256', 'cell_sha256_16', 'section', 'temp_C', 'rails_V',
           'load_pF', 'analysis', 'preflight_rc', 'spectre_rc', 'runner_verdict', 'saved_signals',
           'window_rows', 'state_verdict']
SAMP_HDR = ['case', 'kind', 'signal_or_cause', 'time_s_or_list', 'values', 'status']
ROWS_HDR = S2.ROWS_HDR


def cell_hashes():
    out = []
    for c in CELLS:
        b = open(os.path.join(PROJ, 'spectre', c), 'rb').read()
        out.append((c, hashlib.sha256(b).hexdigest(), len(b)))
    return out


def write_cells(scratch):
    """the frozen cell bytes, copied verbatim next to the deck the simulator reads"""
    for c, sha, _n in cell_hashes():
        data = open(os.path.join(PROJ, 'spectre', c), 'rb').read()
        with open(os.path.join(scratch, c), 'wb') as f:
            f.write(data)


def run_case(R, cid, scratch, man_rows, samp_rows, opts):
    case_def = find_case(cid)
    if case_def is None:
        R.add('R3_DECK_BUILD', cid, '-', 'an id from this entry\'s own table', 'UNKNOWN_CASE', 0,
              'NOT_AVAILABLE', 'this entry does not invent cases')
        return
    deck_txt = build_deck(case_def, opts.section)
    deck = os.path.join(scratch, cid + '.scs')
    with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(deck_txt))
    sha = hashlib.sha256(deck_txt.encode('utf-8')).hexdigest()
    chash = ' '.join('%s=%s' % (c, h[:12]) for c, h, _n in cell_hashes())
    R.add('R3_CELLS_REUSED_VERBATIM', cid, 'the three accepted cells plus the new wrapper',
          'the deck copies the repository bytes; no cell body is edited',
          chash[:150], 0, 'PASS', 'sha256 of each included file as it sits in spectre/')
    devs = chain_devices()
    R.add('R3_DEVICE_COUNT', cid, '%d MOS in the chain' % len(devs),
          '32 = 18 (c2mos_dff) + 4 (sc1_scan_gate) + 10 (sc1_ls_c1_top_r2d), no power device',
          'resolved %d four-terminal devices; first paths %s'
          % (len(devs), ', '.join(p for p, _m, _n in devs[:3])), 0,
          'PASS' if len(devs) == 32 else 'BLOCKED',
          'counted by walking the master bodies, not by reading a comment')
    inter = [n for n in ('q', 'qbar', 'en')
             if re.search(r'\bV\w+\s*\(\s*%s\s+0\)' % n, deck_txt)]
    R.add('R3_NO_IDEAL_INTERPOSE', cid, 'q / qbar / en are inter-module nodes',
          'no vsource or isource touches any of them',
          'drivers found: %s' % (', '.join(inter) or 'none'), 0,
          'PASS' if not inter else 'FAIL',
          'the chain is only meaningful if the DFF output really drives the gate input')
    problems = []
    for item, detail, verdict in audit_frame(case_def, problems):
        R.add(item, cid, 'the framework this deck emits', detail, detail[:0] or 'checked', 0,
              verdict, 'POC_ASSUMPTION stimulus choices, not a setup/hold budget')
    if problems:
        R.add('R3_SETUP_INVALID', cid, 'stimulus audit', 'no framework violation',
              ' ; '.join(problems)[:150], 3, 'BLOCKED',
              'the case is refused before the simulator sees it; a timing that was never emitted '
              'cannot be measured')
        return

    pfr = None
    pf_cmd = '%s "%s" 1.8 %s "%s"' % (
        CC.hook('QODER_PF_CMD', 'bash ' + os.path.join(HERE, 'tb_preflight.sh')), deck, cid,
        SUPPLY_MAP)
    penv = dict(os.environ)
    penv.pop('PREFLIGHT_STATIC_PROBE', None)
    pfr, pftxt = CC.call(pf_cmd, env=penv)
    pf_ok, pf_reason, pf_summary = CC.preflight_verdict(pfr, pftxt)
    R.add('PREFLIGHT_FULL', cid, os.path.basename(deck),
          "the preflight own rc=0 AND exactly one TESTBENCH_PREFLIGHT: PASS",
          'rc=%s map=%s | %s' % (pfr, SUPPLY_MAP, pf_summary.replace('\n', ' | ')[:90]), pfr,
          'PASS' if pf_ok else 'BLOCKED', pf_reason)
    man = [R.run_id, cid, os.path.basename(deck), sha, chash[:120], opts.section, '27',
           '%s/%s' % (V18, V33), fmt_v(case_def.get('load', 1.0)),
           'tran stop=%sn maxstep=%sn' % (tnum(STOP_NS).rstrip('n'), MAXSTEP_NS),
           str(pfr), '', '', '', '', '']
    if not pf_ok:
        man[11:13] = ['NOT_RUN', 'BLOCKED_after_preflight']
        man_rows.append(man)
        R.log.append('=== %s preflight REFUSED rc=%s\n%s' % (cid, pfr, S2.scrub(pftxt)))
        return

    label = 'R3_%s' % cid
    renv = dict(os.environ)
    renv['LABEL'] = label
    # 900 s per deck, not the S2 entry's 240: this chain has 32 devices over 9000 sample points, and a
    # timeout here is a dependency failure that would look exactly like a slow circuit
    rc, run_out = CC.call('%s "%s" 900' % (CC.hook('QODER_RUN_CMD', 'bash ' + os.path.join(
        HERE, 'run_spectre.sh')), deck), env=renv)
    runner_ok, run_reasons, parts = CC.runner_verdict(label, deck, rc, run_out)
    err = re.search(r'ERROR \([A-Z0-9-]+\)[^\n]*', run_out)
    R.add('SIM_RUN', cid, os.path.basename(deck),
          'runner rc=0 + one PASS for this label + spectre rc=0 + error_hits=0 + own data',
          'runner_rc=%s preflight_rc=%s spectre_rc=%s error_hits=%s pass_lines=%d'
          % (rc, pfr, parts.get('spectre_rc', ''), parts.get('error_hits', ''),
             parts.get('pass_lines', 0)), rc, 'PASS' if runner_ok else 'BLOCKED',
          ('; '.join(run_reasons)[:130] or S2.scrub(err.group(0) if err else
                                                   'contract satisfied').replace('\n', ' ')[:130]))
    R.log.append('=== %s run %s\npreflight: %s\nrunner: %s\n'
                 % (cid, 'accepted' if runner_ok else 'REJECTED',
                    S2.scrub(pf_summary), S2.scrub(run_out)))
    data = parts.get('datafile', '')
    man[11] = parts.get('spectre_rc', '') or '?'
    man[12] = 'PASS' if runner_ok else 'BLOCKED'
    man[13] = traces_of(data) if data else ''
    if not runner_ok or not data or not os.path.isfile(data):
        man_rows.append(man)
        return

    measure_stimulus(R, cid, data, case_def)
    for w in case_def['windows']:
        measure_window(R, cid, data, w)
        measure_plateau(R, cid, data, w)
    groups, axis = R1.samples_of(data)
    measure_delays(R, cid, groups, axis, data, case_def)
    measure_edges(R, cid, data, case_def)
    measure_rails(R, cid, data, case_def)
    if case_def.get('fault'):
        negative_report(R, cid, data, case_def, deck_txt)
    emit_samples(R, samp_rows, cid, data, case_def, groups, axis)
    state = [r for r in R.rows if r[1] == 'R3_WINDOW_STATE' and r[2] == cid]
    man[14] = str(len(state))
    man[15] = ('PASS' if all(r[7] in ('PASS', 'EXPECTED_REFUSAL') for r in state) and state
               else 'SEE_ROWS')
    man_rows.append(man)


def traces_of(data):
    """which saved names actually reached the data file, in the simulator's own order"""
    try:
        groups, axis = R1.samples_of(data)
    except Exception:
        return 'UNPARSEABLE'
    if not groups:
        return ''
    return ','.join(sorted(groups[0].keys()))


def negative_report(R, cid, data, case_def, deck_txt):
    """the fault is only 'detected' if the faulted row refused and everything else still held"""
    ref = find_case('r3_blank_assert')
    ref_txt = build_deck(ref)
    stmts, comments = fault_diff(ref_txt, deck_txt)
    inst_changed = [l for l in stmts if l.lstrip('+-').lstrip().startswith('Xchain')]
    other_changed = [l for l in stmts if l not in inst_changed]
    R.add('R3_FAULT_DECK_DIFF', cid, 'the wrapper instance line is the only difference',
          'exactly one changed netlist statement, naming the blank pin',
          'statements: %d (instance %d, other %d) | comments: %d | %s'
          % (len(stmts), len(inst_changed), len(other_changed), len(comments),
             (inst_changed[0] if inst_changed else '')[:80]), 0,
          'PASS' if len(inst_changed) == 2 and not other_changed else 'BLOCKED',
          'the two statement lines are the -/+ pair of the same instance; the comment lines are this '
          "case's own purpose text. A different stimulus or a different cell would make the "
          'comparison meaningless')
    rows = [r for r in R.rows if r[1] == 'R3_WINDOW_STATE' and r[2] == cid]
    refused = [r for r in rows if r[7] == 'EXPECTED_REFUSAL']
    held = [r for r in rows if r[7] == 'PASS']
    blank = [r for r in R.rows if r[1] == 'R3_STIMULUS_READBACK' and r[2] == cid and r[3] == 'blank']
    R.add('R3_NEGATIVE_RESULT', cid, 'blank-tied-vss wiring fault',
          'the normal BLANK assertion refuses while the store, the write and the external blank '
          'waveform all still hold',
          'refused=%d held=%d of %d ; external blank read back %s'
          % (len(refused), len(held), len(rows), (blank[0][5][:40] if blank else 'missing')), 0,
          'DETECTED' if refused and held and not other_changed else 'BLOCKED',
          'a preflight/runner/reader failure would have stopped before this row; DETECTED here is '
          'the circuit refusing the fault, not a tool error')


def classify(rows):
    """the R2E2 split, kept identical so a summary line means the same thing in both rounds"""
    func, dep, info = [], [], []
    for r in rows:
        v = r[7]
        if v == 'FAIL':
            func.append(r)
        elif v in ('BLOCKED', 'NOT_AVAILABLE') or (v == 'PARTIAL' and r[1] != 'SAVE_PATH_AUDIT'):
            dep.append(r)
        elif v in ('NOT_MEASURED_OVERLAP',):
            info.append(r)
        elif v not in ('PASS', 'DETECTED', 'NOT_MEASURED_OVERLAP'):
            info.append(r)
    return func, dep, info


def _selftest():
    """the timing helpers on a synthetic waveform. NO simulator, NO project data, NO circuit claim.

    Two defects of this entry's own first run are pinned here: `_near` returning the earliest instead
    of the nearest at-or-before crossing, and a non-strict lower bound that made the attribution bound
    equal t_in, which turned every propagation row into a false OUT_OF_ATTRIBUTION.
    """
    g = []

    def wave_at(t, off=0.0):
        # one clean symmetric cycle per 100 ns: rise centred at 25 ns, fall at 75 ns, both 2 ns wide,
        # so every 50 % crossing sits inside the period and no wrap edge can move it
        u = (t - off) % PERIOD
        if u < 24.0 or u >= 76.0:
            return 0.0
        if u < 26.0:
            return V18 * (u - 24.0) / EDGE_NS
        if u < 74.0:
            return V18
        return V18 * (76.0 - u) / EDGE_NS

    for i in range(0, 9000):
        t = i * MAXSTEP_NS                           # ns, the deck's maxstep
        g.append({'time': t * 1e-9, 'clk': wave_at(t), 'q': wave_at(t, 3.0)})
    checks = []
    xs = R1.crossing_times(g, 'time', 'clk', 0.9)
    first = xs[0][1]
    nxt = _next_after(xs, first)
    checks.append(('the attribution bound is the NEXT crossing (75 ns), not t_in',
                   nxt is not None and abs(nxt[1] - 75e-9) < 1e-12 and nxt[1] > first))
    checks.append(('the first clock 50% crossing is at 25 ns', abs(first - 25e-9) < 1e-12))
    last = _near(xs, 60e-9, after_only=False)
    checks.append(('at-or-before resolves to the NEAREST earlier crossing',
                   last is not None and abs(last[1] - 25e-9) < 1e-12))
    qs = R1.crossing_times(g, 'time', 'q', 0.9)
    hit = _near(qs, first)
    checks.append(('the synthetic 3 ns propagation is measured as 2.9-3.1 ns',
                   hit is not None and 2.9e-9 <= hit[1] - first <= 3.1e-9))
    bad = [n for n, v in checks if not v]
    for n, v in checks:
        print('   %-58s %s' % (n, 'PASS' if v else 'FAIL'))
    print('R3_HELPER_SELFTEST cases=%d failures=%d (synthetic waveform; no simulator, no circuit '
          'claim)' % (len(checks), len(bad)))
    return 1 if bad else 0


def process_counts(scratch):
    """how many spectre processes this directory can prove, read off the files it left behind"""
    sim = os.path.join(scratch, 'sim')
    if not os.path.isdir(sim):
        return 0, 0
    dep = len([p for p in os.listdir(sim) if p.startswith('preflight_') and p.endswith('.log')])
    dut = len([p for p in os.listdir(sim)
               if not p.startswith('preflight_') and p.endswith('.log')])
    return dep, dut


def main():
    op = optparse.OptionParser()
    op.add_option('--selftest', action='store_true',
                  help='run the timing helpers against a synthetic waveform and exit (no simulator)')
    op.add_option('--scratch')
    op.add_option('--out')
    op.add_option('--manifest')
    op.add_option('--samples')
    op.add_option('--log')
    op.add_option('--dry', action='store_true')
    op.add_option('--only')
    op.add_option('--expect', type='int', default=0)
    op.add_option('--section', default='tt')
    o, _ = op.parse_args()
    if o.selftest:
        return _selftest()
    ids = [c['id'] for c in CASES]
    if o.only:
        wanted = [c for c in o.only.split(',') if c]
        unknown = [c for c in wanted if c not in ids]
        if unknown:
            print('UNKNOWN_CASE %s (this entry offers: %s)' % (','.join(unknown), ','.join(ids)))
            return 9
        ids = [c for c in ids if c in wanted]
    if o.expect and len(ids) != o.expect:
        print('SELECTION_COUNT want=%d got=%d ids=%s' % (o.expect, len(ids), ','.join(ids)))
        return 9
    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'sc1_sim', 'r3_chain')
    out_csv = o.out or os.path.join(PROJ, 'results', 'evidence', 'sc1_r3_chain_cases.csv')
    man_csv = o.manifest or os.path.join(PROJ, 'results', 'evidence', 'sc1_r3_chain_manifest.csv')
    samp_csv = o.samples or os.path.join(PROJ, 'results', 'evidence', 'sc1_r3_waveform_samples.csv')
    log_txt = o.log or os.path.join(PROJ, 'results', 'evidence', 'sc1_r3_chain_dependency_log.txt')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    write_cells(scratch)

    R = S2.Run([], [], 'R3-CHAIN-%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    man_rows, samp_rows = [], []
    print('RUN_ID %s cases=%d stop=%s maxstep=%sn load_default=1pF'
          % (R.run_id, len(ids), tnum(STOP_NS), MAXSTEP_NS))

    if o.dry:
        for cid in ids:
            case_def = find_case(cid)
            txt = build_deck(case_def, o.section)
            with io.open(os.path.join(scratch, cid + '.scs'), 'w', encoding='utf-8',
                         newline='\n') as f:
                f.write(u(txt))
            problems = []
            audit_frame(case_def, problems)
            R.add('DRY_DECK', cid, cid + '.scs', 'the deck builds and the frame audits clean',
                  'sha256=%s lines=%d problems=%s'
                  % (hashlib.sha256(txt.encode('utf-8')).hexdigest()[:16],
                     txt.count('\n'), ','.join(problems) or 'none'), 0,
                  'PASS' if not problems else 'BLOCKED',
                  'dry run only; the deck text and the cell copies are left in the scratch directory '
                  'so PREFLIGHT_STATIC_PROBE=1 can be run against exactly these files')
            devs = chain_devices()
            R.add('DRY_TOPOLOGY', cid, '%d MOS' % len(devs),
                  '32 devices, and q/qbar/en exist as inter-module nodes',
                  ' ; '.join(sorted(set(n for p, m, n in devs
                                         if p.endswith('.q') or p.endswith('.qbar')
                                         or p.endswith('.en')))[:6]), 0,
                  'PASS' if len(devs) == 32 else 'BLOCKED', 'dry run only')
        S2.write_rows(out_csv, R.rows, ROWS_HDR)
        print('DRY rows=%d decks_in=%s csv=%s' % (len(R.rows), scratch, out_csv))
        return 0

    authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
    if not authorised:
        for cid in ids:
            R.add('R3_TT_EXECUTION', cid, 'run', 'RUN=1 and QODER_SIM_AUTHORISED=1', 'refused',
                  5, 'NOT_RUN', 'this entry calls the simulator only with both flags set')
    else:
        for cid in ids:
            try:
                run_case(R, cid, scratch, man_rows, samp_rows, o)
            except Exception:
                import traceback
                tb = traceback.format_exc()
                R.log.append('=== HARNESS_ERROR %s\n%s' % (cid, tb))
                R.add('HARNESS_ERROR', cid, cid, 'no python exception in the entry',
                      tb.strip().split('\n')[-1][:120], 1, 'BLOCKED',
                      'a harness fault is never scored as a circuit result')
    dep, dut = process_counts(scratch)
    R.add('R3_PROCESS_COUNT', 'all', 'preflight dependency runs vs DUT runs',
          'counted from the files this scratch keeps', 'preflight=%d DUT=%d' % (dep, dut), 0,
          'MEASURED', 'tb_preflight.sh FULL mode runs its own operating point; this round does not '
          'claim that only the DUT ran')
    S2.write_rows(out_csv, R.rows, ROWS_HDR)
    S2.write_rows(man_csv, man_rows, MAN_HDR)
    S2.write_rows(samp_csv, samp_rows, SAMP_HDR)
    if R.log:
        with io.open(log_txt, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(S2.scrub('\n'.join(R.log))))
    func, depp, info = classify(R.rows)
    print('R3_TT cases=%d rows=%d functional_FAIL=%d dependency=%d informational=%d '
          'exit=0|1|2|3 as none|func|dep|both -> %s'
          % (len(ids), len(R.rows), len(func), len(depp), len(info), out_csv))
    for tag, lst in (('FUNCTIONAL', func), ('DEPENDENCY', depp), ('INFORMATIONAL', info)):
        for r in lst[:12]:
            print('   %-13s %s | %s | %s: %s (%s)'
                  % (tag, r[1], r[2], r[3][:36], r[5][:70], r[7]))
    if not authorised:
        return 5
    return (1 if func else 0) + (2 if depp else 0)


if __name__ == '__main__':
    sys.exit(main())
