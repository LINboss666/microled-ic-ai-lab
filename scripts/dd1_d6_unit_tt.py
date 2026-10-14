# -*- coding: utf-8 -*-
"""DATA-6 dd1: one stored bit really gating one 15 uA current sink.

    python scripts/dd1_d6_unit_tt.py --selftest                  # helper arithmetic only
    python scripts/dd1_d6_unit_tt.py --dry --expect 8            # decks + frame audit, no sim
    python scripts/dd1_d6_unit_tt.py --devices                   # 29-row per-device readback
    python scripts/dd1_d6_unit_tt.py --supply-negative           # static vss-disconnect refusal
    RUN=1 QODER_SIM_AUTHORISED=1 python scripts/dd1_d6_unit_tt.py --only D6-03 --expect 1
    RUN=1 QODER_SIM_AUTHORISED=1 python scripts/dd1_d6_unit_tt.py --expect 7 --append

The one circuit question: does a bit written by a real clock edge, held with the clock stopped, keep
sinking about 15 uA through the frozen four-device analog core -- and does an external blank switch
that current off without touching the stored bit. Twenty-nine MOS per channel: the accepted 18-device
C2MOS DFF, the accepted 4-device NOR gate, the 2-device inverter added this round, the accepted 4-device
sink and the shared 1-device reference.

Case set (fixed by the task book, 7 positive + 1 real circuit negative):

  D6-01  write 0, clock stops, d moves again, blank released  -> Q holds 0, output stays off
  D6-02  write 1, clock stops, d moves again                  -> Q holds 1, current held
  D6-03  the clock really samples 0 -> 1 -> 0 -> 1             -> Q updates per write only, output
                                                                  follows the stored bit  (run first)
  D6-04  Q=1, clock stopped, blank assert then release         -> off, then on again, Q never erased
  D6-05  writes continue while blank=1                         -> current off throughout, and the
                                                                  latest stored bit is used on release
  D6-06  as D6-04 with the output clamped at 0.6 V             -> lower compliance point
  D6-07  as D6-04 with the output clamped at 3.0 V             -> higher point, no extrapolation to 5 V
  D6-N1  as D6-04 with ONLY Xmask's blank pin tied to vss       -> the same functional criteria must
                                                                  refuse it

Stimulus framework (POC_ASSUMPTION, not a budget and not a course number): the measured frame time
T = 9.765625 us is divided into four 2441.40625 ns slots and every event -- a clock write or a blank
step -- sits on a slot. A write pulses clk high for 400 ns; d is set 300 ns before the rising edge it
is sampled by (the task book asks for at least 100 ns of stable data either side); input edges are
10 ns; a judgement window opens 700 ns after its event and runs 1000 ns, which lands entirely inside
the clock's low phase and is clear of every transition centre. Stop is the shortest value that covers
the last window. maxstep 1 ns, method gear2only.

What is NOT done here, and stays undone: no ideal source drives d, clk, blank, q, qbar, data_en,
data_en_b, iref_in's diode node beyond the declared reference injection, vbias_ch or node_m; no LED
model, no Vf, no VLED, no VSCAN; no array, no second channel, no corner, no temperature sweep, no
setup/hold sweep, no autonomous reference, no layout. IREF = 15 uA and VCAS = 1.8 V are
TESTBENCH_ASSUMPTION bench inputs. The 15 uA itself is the course-confirmed pixel current; the +/-5 %
and 0.15 uA tolerances, the 1.62/0.18 V level pair and every timing above are this round's POC choices.

The rules are inherited, not re-invented: `scripts/sc1_r3_chain_tt.py` supplies the whole-window state
convention, the deck-diff proof and the readers' call discipline; `scripts/sc1_r2e_s2_tt.py` the Run
row format, the strict reader and the scrubbing; `scripts/sc1_r2e1_reread.py` the audited interpolator;
`scripts/sc1_r2e1_call_contract.py` decides every preflight and runner outcome. The analog core and the
reference are the byte-for-byte copies taken from the fixed Data SHA.
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
import sc1_r2e_s2_tt as S2                    # Run, read_sig, read_diff, scrub, write_rows, walkers
import sc1_r2e1_reread as R1                  # samples_of / crossing_times, the audited interpolator
import sc1_r3_chain_tt as R3                  # fmt_v, file_sha, fault_diff, traces_of, the conventions

try:
    _text = unicode
except NameError:
    _text = str

V18 = 1.8
SECTION = 'tt'
STOP_CAP_NS = 50000.0            # the task book's ceiling for an ordinary case

# ---- the framework, one place (POC_ASSUMPTION: these are stimulus choices, not a budget)
FRAME_T_NS = 9765.625            # the measured frame time this project already ran at
SLOT = FRAME_T_NS / 4.0          # 2441.40625 ns: four event slots make exactly one frame
HIGH_NS = 400.0                  # clk stays high this long after a rising edge
EDGE_NS = 10.0                   # every input edge is 10 ns, the task book's number
SETUP_NS = 300.0                 # d leads the rising edge that samples it (>= 100 ns required)
WIN_AHEAD = 700.0                # a judgement window opens this far after its event
WIN_LEN = 1000.0                 # ... and is at least 1 us continuous
MIN_CLEAR_NS = EDGE_NS / 2.0 + 1.0
MAXSTEP_NS = 1.0
STOP_PAD_NS = 200.0
MIN_SAMPLES = 10
SETTLE_BOUND_NS = WIN_AHEAD      # how long a window's current may take to arrive inside its band

# POC criteria, quoted from the task book and NOT a course tolerance or a foundry rating
DIG_HI = 1.62                    # 90 % of 1.8 V
DIG_LO = 0.18                    # 10 % of 1.8 V
I_NOMINAL = 15e-6
I_TOL = 0.05                     # +/- 5 % of the nominal pixel current
I_ON_LO, I_ON_HI = I_NOMINAL * (1 - I_TOL), I_NOMINAL * (1 + I_TOL)
I_OFF_MAX = 0.15e-6              # |IOUT| while disabled
IREF_TXT = '15u'
VCAS_V = 1.8

# the four reviewed circuit files byte-for-byte, the two fixed Data subckts, and this round's masters
FROZEN = ('C2MOS_DFF.scs', 'sc1_scan_gate.scs')
CORE = ('dd1_d6_sink_core.scs', 'dd1_d6_bias_core.scs')
NEW = ('dd1_d6_inv18.scs', 'dd1_d6_control.scs', 'dd1_d6_sink_unit.scs', 'dd1_d6_top.scs')
CELLS = FROZEN + CORE + NEW
CONTROL_FILE = 'dd1_d6_control.scs'
TOP_MASTER = 'dd1_data_top_1ch'
TOP_INST = 'Xtop (d clk blank iref_in vcas dout vdd18 vss) dd1_data_top_1ch\n'
TOTAL_DEVS = 29
EXPECT_MIX = {'n18': 12, 'p18': 12, 'n33': 4, 'n33_dnw_4t_ckt': 1}

# `vscan' is not a port here, but the sink's port is spelled VSS and the digital one vss: the checker
# treats them as different keys, so both have to be covered.
SUPPLY_MAP = 'vdd18=1.8 vdd=1.8 vss=0 VSS=0'
EXPECTED_VDD = '1.8'

# every judged node, addressed the way the simulator saves it
NODES = {
    'd': 'd', 'clk': 'clk', 'blank': 'blank', 'vdd18': 'vdd18', 'vss': 'vss',
    'q': 'Xtop.Xunit.Xctrl.q', 'qbar': 'Xtop.Xunit.Xctrl.qbar',
    'data_en': 'Xtop.Xunit.data_en', 'data_en_b': 'Xtop.Xunit.data_en_b',
}
ANALOGUE = {
    'iref_in (VBIAS_SHARED)': 'iref_in',
    'vbias_ch': 'Xtop.Xunit.Xsink.vbias_ch',
    'node_m': 'Xtop.Xunit.Xsink.node_m',
    'dout (clamped)': 'dout',
}
IOUT = 'Ip_out:i'


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def fmt_v(v):
    return R3.fmt_v(v)


def tns(t):
    """ns -> the deck's own spelling; slot times are fractional, so keep the exact digits"""
    s = '%.9f' % t
    s = s.rstrip('0').rstrip('.')
    return (s or '0') + 'n'


def wave(start, steps, stop_ns):
    """[(t_ns, value)] -> 'wave=[0 0 2141.40625 1.8 ...]' with a 10 ns ramp centred on each step.

    Same shape as the accepted R3 generator: a step that changes nothing still gets a time point, a
    point never precedes its predecessor, and the run end closes the last level. Out-of-order PWL is
    the kind of silent defect this project has been burned by.
    """
    pts = [(0.0, start)]
    prev = start
    for t, v in sorted(steps):
        if abs(v - prev) < 1e-12:
            pts.append((t, v))
            continue
        pts.append((t - EDGE_NS / 2.0, prev))
        pts.append((t + EDGE_NS / 2.0, v))
        prev = v
    pts.append((stop_ns, prev))
    clean, last_t = [], None
    for t, v in pts:
        if last_t is not None and t <= last_t + 1e-12:
            continue
        clean.append((t, v))
        last_t = t
    return '[' + ' '.join('%s %s' % (tns(t), fmt_v(v)) for t, v in clean) + ']'


# ------------------------------------------------------------------ the case table
def wr(slot, dval):
    return {'kind': 'write', 'slot': slot, 'd': dval}


def lv(slot, sig, val):
    return {'kind': 'level', 'slot': slot, 'sig': sig, 'val': val}


def win(label, slot, expect, current=None, refusable=False, analog=False, note=''):
    out = {'label': label, 't0': slot * SLOT + WIN_AHEAD, 't1': slot * SLOT + WIN_AHEAD + WIN_LEN,
           'expect': expect, 'current': current, 'note': note, 'cause': slot * SLOT}
    if refusable:
        out['refusable'] = True
    if analog:
        out['analog'] = True
    return out


def init_win(label, t0, t1):
    """the power-up stretch, reported and never certified: this DFF has no reset"""
    return {'label': label, 't0': t0, 't1': t1, 'expect': {}, 'current': None,
            'init': True, 'note': 'no reset exists, so the initial Q is not a claim'}


def case(cid, **kw):
    kw['id'] = cid
    kw.setdefault('vout', 1.2)
    return kw


# the shared timeline of D6-04/06/07/N1: write 0, release blank, write 1, then blank out and back
BLANK_TIMELINE = [wr(1, 0.0), lv(2, 'blank', 0.0), wr(3, V18), lv(4, 'blank', V18),
                  lv(5, 'blank', 0.0)]
BLANK_WINDOWS = [
    win('primed_off', 1, {'d': 'low', 'clk': 'low', 'blank': 'high', 'q': 'low', 'qbar': 'high',
                          'data_en': 'low', 'data_en_b': 'high'}, 'off',
        note='a real clock edge wrote the 0; blank is still asserted'),
    win('released_off', 2, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'low', 'qbar': 'high',
                            'data_en': 'low', 'data_en_b': 'high'}, 'off',
        note='stored bit is 0, so releasing blank must not produce current'),
    win('written_on', 3, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high', 'qbar': 'low',
                          'data_en': 'high', 'data_en_b': 'low'}, 'on', analog=True,
        note='15 uA because a clock wrote it, not because blank was lifted'),
    win('blanked_on_Q', 4, {'d': 'high', 'clk': 'low', 'blank': 'high', 'data_en': 'low',
                            'data_en_b': 'high'}, 'off', analog=True),
    win('released_again', 5, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high', 'qbar': 'low',
                              'data_en': 'high', 'data_en_b': 'low'}, 'on',
        note='no rewrite happened: the store still holds the 1 written at slot 3')]

CASES = [
    case('D6-01',
         events=[wr(1, 0.0), lv(2, 'blank', 0.0), lv(3, 'd', V18)],
         windows=[init_win('power_up', 300.0, 1300.0),
                  win('wrote_zero', 1, {'d': 'low', 'clk': 'low', 'blank': 'high', 'q': 'low',
                                        'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'}, 'off',
                      analog=True),
                  win('blank_released', 2, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'low',
                                            'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'},
                      'off'),
                  win('d_moved_no_clock', 3, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'low',
                                              'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'},
                      'off', analog=True,
                      note='the clock is stopped: d goes high and Q must not follow')],
         purpose='a reset-free store that was written 0 keeps the output off while d changes again'),

    case('D6-02',
         events=[wr(1, 0.0), lv(2, 'blank', 0.0), wr(3, V18), lv(4, 'd', 0.0)],
         windows=[init_win('power_up', 300.0, 1300.0),
                  win('wrote_zero', 1, {'d': 'low', 'clk': 'low', 'blank': 'high', 'q': 'low',
                                        'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'}, 'off'),
                  win('blank_released', 2, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'low',
                                            'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'},
                      'off', analog=True),
                  win('wrote_one_on', 3, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high',
                                          'qbar': 'low', 'data_en': 'high', 'data_en_b': 'low'},
                      'on', analog=True),
                  win('d_moved_holds_1', 4, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'high',
                                             'qbar': 'low', 'data_en': 'high', 'data_en_b': 'low'},
                      'on', note='d falls back with the clock stopped; the held 1 still sinks 15 uA')],
         purpose='one legal write of 1 holds its current through a later change of d'),

    case('D6-03',
         events=[wr(1, 0.0), lv(2, 'blank', 0.0), wr(3, V18), wr(4, 0.0), wr(5, V18)],
         windows=[init_win('power_up', 300.0, 1300.0),
                  win('wrote_zero', 1, {'d': 'low', 'clk': 'low', 'blank': 'high', 'q': 'low',
                                        'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'}, 'off'),
                  win('blank_released_off', 2, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'low',
                                                'qbar': 'high', 'data_en': 'low',
                                                'data_en_b': 'high'}, 'off', analog=True),
                  win('sampled_1_on', 3, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high',
                                          'qbar': 'low', 'data_en': 'high', 'data_en_b': 'low'},
                      'on', analog=True),
                  win('sampled_0_off', 4, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'low',
                                           'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'},
                      'off'),
                  win('sampled_1_on_again', 5, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high',
                                                'qbar': 'low', 'data_en': 'high',
                                                'data_en_b': 'low'}, 'on', analog=True)],
         purpose='four real clock edges sample 0 1 0 1 and the current follows the stored bit'),

    case('D6-04',
         events=list(BLANK_TIMELINE),
         windows=[init_win('power_up', 300.0, 1300.0)] + BLANK_WINDOWS,
         purpose='blank switches a held 1 off and back on without erasing it'),

    case('D6-05',
         events=[wr(1, 0.0), wr(2, V18), wr(3, 0.0), wr(4, V18), lv(5, 'blank', 0.0)],
         windows=[init_win('power_up', 300.0, 1300.0),
                  win('blanked_write_0', 1, {'d': 'low', 'clk': 'low', 'blank': 'high', 'q': 'low',
                                             'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'},
                      'off'),
                  win('blanked_write_1', 2, {'d': 'high', 'clk': 'low', 'blank': 'high', 'q': 'high',
                                             'qbar': 'low', 'data_en': 'low', 'data_en_b': 'high'},
                      'off', note='Q is 1 and the channel is still off: blank masks it, not clears it'),
                  win('blanked_write_0_again', 3, {'d': 'low', 'clk': 'low', 'blank': 'high',
                                                   'q': 'low', 'qbar': 'high', 'data_en': 'low',
                                                   'data_en_b': 'high'}, 'off'),
                  win('blanked_write_1_last', 4, {'d': 'high', 'clk': 'low', 'blank': 'high',
                                                  'q': 'high', 'qbar': 'low', 'data_en': 'low',
                                                  'data_en_b': 'high'}, 'off', analog=True),
                  win('release_uses_latest', 5, {'d': 'high', 'clk': 'low', 'blank': 'low',
                                                 'q': 'high', 'qbar': 'low', 'data_en': 'high',
                                                 'data_en_b': 'low'}, 'on',
                      note='the last bit written under blank is the one that appears')],
         purpose='writes keep happening behind an asserted blank and the newest bit drives the output'),

    case('D6-06', vout=0.6,
         events=list(BLANK_TIMELINE),
         windows=[init_win('power_up', 300.0, 1300.0)] +
                  [dict(w, label=w['label'] + '_0p6') for w in BLANK_WINDOWS],
         purpose='the same timeline with the output clamped to the lower compliance point'),

    case('D6-07', vout=3.0,
         events=list(BLANK_TIMELINE),
         windows=[init_win('power_up', 300.0, 1300.0)] +
                  [dict(w, label=w['label'] + '_3p0') for w in BLANK_WINDOWS],
         purpose='the same timeline at 3.0 V: a measured point, not an extrapolation to 5 V'),

    case('D6-N1', fault='blank_pin_to_vss',
         events=list(BLANK_TIMELINE),
         windows=[init_win('power_up', 300.0, 1300.0),
                  win('primed_off', 1, {'d': 'low', 'clk': 'low', 'blank': 'high', 'q': 'low',
                                        'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'}, 'off'),
                  win('released_off', 2, {'d': 'low', 'clk': 'low', 'blank': 'low', 'q': 'low',
                                          'qbar': 'high', 'data_en': 'low', 'data_en_b': 'high'},
                      'off'),
                  win('written_on', 3, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high',
                                        'qbar': 'low', 'data_en': 'high', 'data_en_b': 'low'}, 'on',
                      analog=True),
                  win('assert_Q_not_erased', 4, {'d': 'high', 'clk': 'low', 'blank': 'high',
                                                 'q': 'high', 'qbar': 'low'},
                      note='the store survives the wiring fault: this half must still hold'),
                  win('assert_should_be_off', 4, {'data_en': 'low', 'data_en_b': 'high'}, 'off',
                      refusable=True,
                      note='with the cell pin at vss the gate never sees blank: the refusal is the '
                           'detection'),
                  win('released_again', 5, {'d': 'high', 'clk': 'low', 'blank': 'low', 'q': 'high',
                                            'qbar': 'low', 'data_en': 'high', 'data_en_b': 'low'},
                      'on', note='passes anyway: en = Q when the pin is stuck, which is exactly why '
                                 'the assert window is the detector')],
         purpose='a real wiring fault: the mask gate pin sits at vss while the external blank toggles'),
]


def find_case(cid):
    for c in CASES:
        if c['id'] == cid:
            return c
    return None


def stop_ns(case_def):
    last = max([w['t1'] for w in case_def['windows']])
    return last + STOP_PAD_NS


def event_steps(case_def):
    """the slot events expanded into the (t_ns, value) steps of each physical input source"""
    clk, dch, bl = [], [], []
    for e in case_def['events']:
        t = e['slot'] * SLOT
        if e['kind'] == 'write':
            clk.append((t, V18))
            clk.append((t + HIGH_NS, 0.0))
            dch.append((t - SETUP_NS, e['d']))
        elif e['sig'] == 'blank':
            bl.append((t, e['val']))
        else:
            dch.append((t, e['val']))
    return sorted(clk), sorted(dch), sorted(bl)


def stimulus_rows(case_def):
    """the framework as the flip points the deck actually carries, not as a comment"""
    clk, dch, bl = event_steps(case_def)
    out = [('clk', 'clk', '0', ', '.join('%s->%s' % (tns(t), fmt_v(v)) for t, v in clk)),
           ('d', 'd', '0', ', '.join('%s->%s' % (tns(t), fmt_v(v)) for t, v in dch) or 'constant'),
           ('blank', 'blank', fmt_v(V18),
            ', '.join('%s->%s' % (tns(t), fmt_v(v)) for t, v in bl) or 'constant')]
    return out


# ------------------------------------------------------------------ stimulus audit
def audit_frame(case_def, problems):
    """this entry's own framework numbers, checked against what the deck is about to emit"""
    rows = []
    clk, dch, bl = event_steps(case_def)
    rises = [t for t, v in clk if v > 0]
    centres = [t for t, _v in clk] + [t for t, _v in dch] + [t for t, _v in bl]
    writes = [(e['slot'] * SLOT, e['d']) for e in case_def['events'] if e['kind'] == 'write']
    if not writes or writes[0][1] != 0.0:
        problems.append('%s: the first event must be a real clock edge writing 0' % case_def['id'])
    rows.append(('PRIMING', 'first write is a real rising edge at %s carrying d=0, blank starts at '
                 '%s V' % (tns(writes[0][0]) if writes else '-', fmt_v(V18)),
                 'PASS' if writes and writes[0][1] == 0.0 else 'BLOCKED'))
    for t, val in writes:
        before = [s for s, v in dch if s <= t]
        lead = t - before[-1] if before else None
        after = [s for s, v in dch if s > t]
        gap = (after[0] - t) if after else None
        ok = lead is not None and lead >= SETUP_NS - 1e-9 and (gap is None or gap >= 100.0)
        rows.append(('WRITE_SETUP_HOLD', 'write at %s (d=%s): d led it by %s ns, next d change %s ns '
                     'later (need >= 100 both ways)'
                     % (tns(t), fmt_v(val), '%.1f' % lead if lead is not None else 'never',
                        '%.1f' % gap if gap is not None else 'none'),
                     'PASS' if ok else 'BLOCKED'))
        if not ok:
            problems.append('%s: write at %s ns lacks the 100 ns of stable data either side'
                            % (case_def['id'], tns(t)))
    for t, v in bl:
        away = min([abs(t - r) for r in rises]) if rises else None
        ok = away is None or away >= 100.0
        rows.append(('BLANK_SPACING', 'blank change at %s is %s ns from the nearest rising edge '
                     '(need >= 100)' % (tns(t), '%.1f' % away if away is not None else '-'),
                     'PASS' if ok else 'BLOCKED'))
        if not ok:
            problems.append('%s: blank change at %s ns is too close to a rising edge'
                            % (case_def['id'], tns(t)))
    stop = stop_ns(case_def)
    rows.append(('RUN_LENGTH', 'stop %s ns covers the last window %s ns with %s ns to spare '
                 '(cap %s ns)' % (tns(stop), tns(max(w['t1'] for w in case_def['windows'])),
                                  tns(STOP_PAD_NS), tns(STOP_CAP_NS)),
                 'PASS' if stop <= STOP_CAP_NS else 'BLOCKED'))
    if stop > STOP_CAP_NS:
        problems.append('%s: stop %s ns exceeds the ordinary-case cap' % (case_def['id'], tns(stop)))
    for w in case_def['windows']:
        t0, t1 = w['t0'], w['t1']
        clear = min(min(abs(t0 - c), abs(t1 - c), 0.0 if t0 < c < t1 else 1e9) for c in centres)
        samples = int(math.floor((t1 - t0) / MAXSTEP_NS)) + 1
        ok = samples >= MIN_SAMPLES and clear >= MIN_CLEAR_NS
        rows.append(('WINDOW', '%s [%s..%s] ns: %d samples, %s ns clear of every transition centre'
                     % (w['label'], tns(t0), tns(t1), samples, '%.1f' % clear),
                     'PASS' if ok else 'BLOCKED'))
        if not ok:
            problems.append('%s: window %s is too short (%d samples) or crosses a transition'
                            % (case_def['id'], w['label'], samples))
    return rows


# ------------------------------------------------------------------ netlist + deck
DIRECTION_RE = re.compile(r'^\s*parameters\s+[A-Za-z_]\w*\s+(?:input|output|inputOutput|inout)'
                          r'\s*$')


def strip_direction_annotations(txt):
    """drop the Verilog-AMS port-direction lines, and prove nothing else moved

    This build's circuit read-in parses `parameters DATA_EN input' as a parameter named `input' being
    defined over and over, and refuses the deck with SFE-59 (measured: 18 errors, no PSF at all, on the
    very first operating-point probe). The lines carry no device, terminal or geometry information, so
    they are removed from what the simulator is handed -- the repository bytes stay as they were read
    from the fixed SHA, and the device-statement digest below is what proves the two are the same
    circuit.
    """
    kept, removed = [], 0
    for line in txt.split('\n'):
        if DIRECTION_RE.match(line):
            removed += 1
            continue
        kept.append(line)
    return '\n'.join(kept), removed


def device_digest(txt):
    """digest over the electrical content only: device and subckt-instance lines"""
    body = [l.strip() for l in txt.split('\n')
            if re.match(r'^\s*[A-Za-z]\w*\s*\(', l) and not re.search(r'vsource|isource|capacitor',
                                                                        l)]
    return hashlib.sha256('\n'.join(body).encode('utf-8')).hexdigest()[:16]


def cell_texts(fault=None):
    """the exact bytes of every master this deck includes, with the declared normalisations applied"""
    out = []
    for c in CELLS:
        txt = u(io.open(os.path.join(PROJ, 'spectre', c), encoding='utf-8',
                        errors='replace').read())
        if fault == 'blank_pin_to_vss' and c == CONTROL_FILE:
            patched = txt.replace('Xmask (qbar blank data_en vdd vss)',
                                  'Xmask (qbar vss data_en vdd vss)')
            if patched == txt:
                raise RuntimeError('the fault patch found no Xmask statement in %s' % c)
            txt = patched
        txt, _n = strip_direction_annotations(txt)
        out.append((c, txt))
    return out


def cell_identity():
    """per file: repository bytes, what the simulator is handed, and the device digest of both"""
    rows = []
    for c in CELLS:
        raw = u(io.open(os.path.join(PROJ, 'spectre', c), encoding='utf-8',
                        errors='replace').read())
        norm, removed = strip_direction_annotations(raw)
        rows.append((c, hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12],
                     hashlib.sha256(norm.encode('utf-8')).hexdigest()[:12], removed,
                     device_digest(raw), device_digest(norm)))
    return rows


DECK_TOP = '''simulator lang=spectre insensitive=yes
// DATA-6 dd1 one-bit data unit: %s
// model binding comes from the git-ignored spectre/pdk_local.env; run_spectre.sh refuses an
// unexpanded ${QODER_PDK_LIB}, so every deck here is bound before it runs.
include "${QODER_PDK_LIB}" section=%s
'''

SAVES = ('save d clk blank iref_in vcas dout clamp vdd18 vss\n'
         'save Xtop.Xunit.Xctrl.q Xtop.Xunit.Xctrl.qbar Xtop.Xunit.data_en '
         'Xtop.Xunit.data_en_b\n'
         'save Xtop.Xunit.Xsink.vbias_ch Xtop.Xunit.Xsink.node_m\n'
         '// IOUT is read straight off the series ammeter, no burden resistor anywhere: the sign is\n'
         '// the probe itself, positive when current flows from the clamp into the DUT pin, which is\n'
         '// the sinking direction a 15 uA pixel current is defined in.\n'
         'save Ip_out:i\n')


def build_deck(case_def, section='tt'):
    clk, dch, bl = event_steps(case_def)
    stop = stop_ns(case_def)
    lines = [DECK_TOP % (case_def['purpose'], section)]
    lines.append(''.join('include "%s"\n' % c for c in CELLS))
    lines.append('// temperature is read back from the produced log and psf header; the instantiation\n'
                 '// form is what this build accepts (a bare `options temp=27\' is SFE-709).\n'
                 'simopt options temp=27\n')
    lines.append('Vd (d 0) vsource dc=0 type=pwl wave=%s\n' % wave(0.0, dch, stop))
    lines.append('Vclk (clk 0) vsource dc=0 type=pwl wave=%s\n' % wave(0.0, clk, stop))
    lines.append('// blank is an EXTERNAL guard: it starts asserted, exactly as the task book requires\n'
                 '// of a store that has no reset.\n'
                 'Vbl (blank 0) vsource dc=%s type=pwl wave=%s\n' % (fmt_v(V18),
                                                                     wave(V18, bl, stop)))
    lines.append('V18 (vdd18 0) vsource dc=%s\n' % fmt_v(V18))
    lines.append('Vss (vss 0) vsource dc=0\n')
    lines.append('// TESTBENCH_ASSUMPTION: the reference current and the cascode rail stay bench\n'
                 '// inputs this round; no autonomous reference or bandgap is claimed.\n'
                 'Iref (0 iref_in) isource dc=%s\n' % IREF_TXT)
    lines.append('Vcas (vcas 0) vsource dc=%s\n' % fmt_v(VCAS_V))
    lines.append('// the pixel is a clamp, not a load model: no LED, no Vf, no VLED exists here.\n'
                 'Vclamp (clamp 0) vsource dc=%s\n' % fmt_v(case_def['vout']))
    lines.append('Ip_out (clamp dout) iprobe\n')
    lines.append(TOP_INST)
    lines.append('sw1 tran stop=%s maxstep=%s method=gear2only\n' % (tns(stop), tns(MAXSTEP_NS)))
    lines.append(SAVES)
    return ''.join(lines)


def full_netlist(deck_txt, cells):
    """deck plus every included master: the text the wiring-fault diff is really made of"""
    out = deck_txt
    for name, txt in cells:
        out += txt
    return out


def write_case_dir(scratch, case_def):
    """one directory per case: the deck and the master bytes the simulator reads, so a faulted
    control copy can never be confused with the frozen one on disk"""
    d = os.path.join(scratch, case_def['id'])
    if not os.path.isdir(d):
        os.makedirs(d)
    cells = cell_texts(case_def.get('fault'))
    for name, txt in cells:
        with io.open(os.path.join(d, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(txt))
    deck_txt = build_deck(case_def, SECTION)
    deck = os.path.join(d, case_def['id'] + '.scs')
    with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(deck_txt))
    return deck, deck_txt, cells


def devices_of(fault=None):
    text = ''.join(t for _n, t in cell_texts(fault)) + '\n' + TOP_INST
    return S2.resolve_devices(TOP_INST, text)


def device_size_rows():
    """path, master, the geometry as spelled and as the subckt's own parameters resolve it, and the
    four terminal names of every expanded MOS

    parse_masters walks the hierarchy but keeps no geometry, and the geometry is what a reviewer has
    to compare against the golden table. The frozen digital masters size their devices through
    `parameters`, so the raw symbol and the resolved number are both kept: a resolved value with no
    raw column would be this round's own version of the simW trap.
    """
    attrs = {}
    params = {}
    cur = None
    for name, txt in cell_texts():
        for raw in txt.split('\n'):
            s = raw.strip()
            if not s or s.startswith('//'):
                continue
            m = re.match(r'^subckt\s+(\S+)', s, re.I)
            if m:
                cur = m.group(1)
                params[cur] = {}
                continue
            if re.match(r'^ends\b', s, re.I):
                cur = None
                continue
            m = re.match(r'^parameters\s+(.*)$', s, re.I)
            if m and cur is not None:
                for k, v in re.findall(r'\b([a-z]\w*)=([^\s,]+)', m.group(1)):
                    params[cur][k] = v
                continue
            m = re.match(r'^([A-Za-z]\w*)\s*\(([^)]*)\)\s*([A-Za-z]\w*)(.*)$', s)
            if not m or cur is None:
                continue
            inst, _nets, master, rest = m.groups()
            g = dict(re.findall(r'\b([a-z]+)=([^\s]+)', rest))
            attrs[(cur, inst)] = (g.get('l', ''), g.get('w', ''), g.get('m', '1'))
    build_owners()
    rows = []
    for path, model, nets in devices_of():
        leaf = path.split('.')[-1]
        body = owner(path)
        l, w, m = attrs.get((body, leaf), ('', '', ''))
        p = params.get(body, {})
        rows.append([path, model, l, p.get(l, l), w, p.get(w, w), m] + list(nets) + [body])
    return rows


_OWNERS = {}


def build_owners():
    """instance path -> the subckt definition whose body holds it"""
    global _OWNERS
    if _OWNERS:
        return _OWNERS
    masters = S2.parse_masters(''.join(t for _n, t in cell_texts()) + '\n' + TOP_INST)

    def visit(path, master):
        body = masters.get(master)
        if not body:
            return
        for kind, name, _nets, m2 in body['items']:
            p2 = '%s.%s' % (path, name) if path else name
            if kind == 'sub':
                _OWNERS[p2] = master
                visit(p2, m2)
            else:
                _OWNERS[p2] = master

    visit('Xtop', TOP_MASTER)
    _OWNERS['Xtop'] = ''
    return _OWNERS


def owner(path):
    build_owners()
    return _OWNERS.get(path, '')


# ------------------------------------------------------------------ measurement
def measure_window(R, cid, data, w):
    """one state claim per signal, over the whole window, with the reader's own sample floor"""
    if w.get('init'):
        return
    for sig, want in sorted(w['expect'].items()):
        t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
        path = NODES[sig]
        rcn, mn = S2.read_sig(R, data, path, 'min', t0, t1, req=str(MIN_SAMPLES))
        rcx, mx = S2.read_sig(R, data, path, 'max', t0, t1, req=str(MIN_SAMPLES))
        if rcn or rcx:
            R.add('D6_WINDOW_STATE', cid, '%s @ %s' % (path, w['label']),
                  'window min and max readable with >= %d samples' % MIN_SAMPLES,
                  (mn if rcn else mx)[:70], rcn or rcx, 'BLOCKED',
                  'reader exit kept; a state is never inferred from a label')
            continue
        a, b = float(mn), float(mx)
        ok = (a >= DIG_HI) if want == 'high' else (b <= DIG_LO)
        verdict = 'PASS' if ok else ('EXPECTED_REFUSAL' if w.get('refusable') else 'FAIL')
        R.add('D6_WINDOW_STATE', cid, '%s @ %s' % (path, w['label']),
              '%s throughout the whole window (high min >= %.2f V / low max <= %.2f V, the POC '
              '90/10 %% levels of 1.8 V)' % (want, DIG_HI, DIG_LO),
              'min=%.6g max=%.6g V' % (a, b), 0, verdict,
              'window %s..%s ns; %s' % (tns(w['t0']), tns(w['t1']),
                                        S2.scrub(w['note']).replace('\n', ' ')[:70] or 'this case\'s '
                                        'declared expectation'))


def measure_window_current(R, cid, data, w):
    """the signed series-ammeter reading, judged over the same window the state claims use"""
    if not w.get('current'):
        return
    t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
    rcn, mn = S2.read_sig(R, data, IOUT, 'min', t0, t1, req=str(MIN_SAMPLES))
    rcx, mx = S2.read_sig(R, data, IOUT, 'max', t0, t1, req=str(MIN_SAMPLES))
    if rcn or rcx:
        R.add('D6_WINDOW_CURRENT', cid, '%s @ %s' % (IOUT, w['label']),
              'the ammeter is readable across the window', (mn if rcn else mx)[:70], rcn or rcx,
              'BLOCKED', 'no current is ever inferred from a rail or an old file')
        return
    a, b = float(mn), float(mx)
    if w['current'] == 'on':
        exp = 'signed IOUT inside %.3g .. %.3g A (15 uA +/- 5 %%, this round\'s POC band)' % (
            I_ON_LO, I_ON_HI)
        ok = a >= I_ON_LO and b <= I_ON_HI
    else:
        exp = '|signed IOUT| <= %.3g A while disabled (POC criterion)' % I_OFF_MAX
        ok = abs(a) <= I_OFF_MAX and abs(b) <= I_OFF_MAX
    R.add('D6_WINDOW_CURRENT', cid, '%s @ %s' % (IOUT, w['label']), exp,
          'min=%.6g max=%.6g A over %s..%s ns' % (a, b, tns(w['t0']), tns(w['t1'])), 0,
          ('PASS' if ok else ('EXPECTED_REFUSAL' if w.get('refusable') else 'FAIL')),
          'whole-window extremes of one signed reading; positive means current the sink takes from '
          'the clamp')


def measure_analogue(R, cid, data, w):
    """the nodes this round must not pretend to judge: report what they actually sit at"""
    if not w.get('analog'):
        return
    t0, t1 = '%.9g' % (w['t0'] * 1e-9), '%.9g' % (w['t1'] * 1e-9)
    for label, path in sorted(ANALOGUE.items()):
        rcn, mn = S2.read_sig(R, data, path, 'min', t0, t1, req=str(MIN_SAMPLES))
        rcx, mx = S2.read_sig(R, data, path, 'max', t0, t1, req=str(MIN_SAMPLES))
        if rcn or rcx:
            R.add('D6_ANALOGUE_READBACK', cid, '%s @ %s' % (path, w['label']),
                  'readable in the window', (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
                  'the node may not exist at this level; nothing is substituted for it')
            continue
        R.add('D6_ANALOGUE_READBACK', cid, '%s @ %s' % (path, w['label']),
              'candidate value, no threshold exists for it',
              'min=%.6g max=%.6g V' % (float(mn), float(mx)), 0, 'MEASURED',
              'kept separate from the certified rows; a mirror node is not a rating')


def measure_stimulus(R, cid, data, case_def):
    t_end = '%.9g' % (stop_ns(case_def) * 1e-9)
    for sig, net, start, flips in stimulus_rows(case_def):
        rcn, mn = S2.read_sig(R, data, net, 'min', '0', t_end, req='10')
        rcx, mx = S2.read_sig(R, data, net, 'max', '0', t_end, req='10')
        if rcn or rcx:
            R.add('D6_STIMULUS_READBACK', cid, net, 'the deck drives this net',
                  (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
                  'the source or the save is missing; the declared flip list is not evidence')
            continue
        R.add('D6_STIMULUS_READBACK', cid, net, 'declared flips %s' % flips[:70],
              'start=%s V, window min=%.6g max=%.6g V' % (start, float(mn), float(mx)), 0,
              'MEASURED', 'read over the whole run; the state rows below judge the windows')


def measure_bias(R, cid, data, case_def):
    """the reference branch is only sane if the injected current lands on the diode node"""
    t_end = '%.9g' % (stop_ns(case_def) * 1e-9)
    rcn, mn = S2.read_sig(R, data, 'iref_in', 'min', '0', t_end, req='10')
    rcx, mx = S2.read_sig(R, data, 'iref_in', 'max', '0', t_end, req='10')
    if rcn or rcx:
        R.add('D6_BIAS_DIRECTION', cid, 'iref_in', 'the injection node is readable',
              (mn if rcn else mx)[:70], rcn or rcx, 'BLOCKED',
              'a bench-direction problem, not a circuit verdict')
        return
    a, b = float(mn), float(mx)
    plausible = 0.2 <= a and b <= 3.3
    R.add('D6_BIAS_DIRECTION', cid, 'iref_in (the diode node Iref feeds)',
          'a diode-connected NMOS carrying the declared 15 uA must sit above 0 V: min >= 0.2 V',
          'min=%.6g max=%.6g V over the whole run' % (a, b), 0,
          'PASS' if plausible else 'BLOCKED',
          'this row exists to catch the bench sign convention; a negative node would mean the '
          'reference current is being pulled OUT, which no functional claim could rest on')


def _half(sig):
    return 0.5 * V18


def _sample_index(groups, axis, t_ref):
    for i in range(len(groups)):
        if groups[i][axis] >= t_ref - 1e-18:
            return i
    return None


def _dir_of(groups, axis, xs, k, sig):
    """whether crossing k of `sig' goes up or down, read off the two samples it sits between"""
    i = xs[k][0]
    a, b = groups[i - 1].get(sig), groups[i].get(sig)
    if a is None or b is None:
        return ''
    return 'rise' if b > a else 'fall'


def _first_dir(groups, axis, xs, sig, t_from, t_to, want):
    for k, (i, t) in enumerate(xs):
        if t < t_from - 1e-18:
            continue
        if t_to is not None and t > t_to + 1e-18:
            break
        if _dir_of(groups, axis, xs, k, sig) == want:
            return (i, t)
    return None


def measure_responses(R, cid, groups, axis, data, case_def):
    """CLK up -> Q, blank -> data_en, data_en -> current: MEASURED, with the bound it used

    No timing budget exists for this POC, so nothing here is a pass/fail level: each row carries the
    50 % -> 50 % interval the audited interpolator gives and the boundary it was attributed inside.
    Three outcomes are distinguished, because collapsing them would be a claim in itself: a transition
    that was expected and found, one whose 50 % point is not separable from the input's own ramp
    (NOT_MEASURED_OVERLAP, the same refusal scripts/sc1_delay.py answers with), and one that this
    event was never supposed to cause (NOT_EXPECTED).
    """
    qxs = R1.crossing_times(groups, axis, NODES['q'], _half('q'))
    enxs = R1.crossing_times(groups, axis, NODES['data_en'], _half('data_en'))
    stored = None          # None until the first real edge: the store has no reset
    blank_hi = True        # the deck starts with the guard asserted
    for e in sorted(case_def['events'], key=lambda x: x['slot']):
        t = e['slot'] * SLOT
        tr = t * 1e-9
        bound = tr + WIN_AHEAD * 1e-9
        if e['kind'] == 'write':
            new_hi = e['d'] > 0.5 * V18
            want = None if stored is None else ('rise' if new_hi else 'fall')
            if stored is None:
                label = 'CLK rise(%s) -> q 50%% (first edge, no reset)' % tns(t)
                note = ('the store has no reset, so the power-up level is unknown: any q transition '
                        'at this edge is reported as observed')
            else:
                label = 'CLK rise(%s) -> q %s 50%%' % (tns(t), want)
                note = 'the stored bit goes %s -> %s' % (stored, 'high' if new_hi else 'low')
            _response_row(R, cid, label, NODES['q'], qxs, groups, axis, tr, bound, want, note)
            stored = 'high' if new_hi else 'low'
        else:
            new_blank_hi = e['val'] > 0.5 * V18
            was = stored == 'high' and not blank_hi
            now = stored == 'high' and not new_blank_hi
            want = None if was == now else ('rise' if now else 'fall')
            blank_hi = new_blank_hi
            label = 'blank edge(%s) -> data_en %s 50%%' % (tns(t), want or 'none')
            _response_row(R, cid, label, NODES['data_en'], enxs, groups, axis, tr, bound, want,
                          'en = NOR(qbar, blank): with the stored bit at %s, %s blank leaves data_en '
                          '%s; the mask gate is the only thing between the store and the sink'
                          % (stored or 'unknown', 'asserted' if new_blank_hi else 'released',
                             'high' if now else 'low'))
    for w in case_def['windows']:
        if w.get('init') or not w.get('current'):
            continue
        measure_settle(R, cid, groups, axis, w, enxs)


def _response_row(R, cid, label, sig, xs, groups, axis, tr, bound, want, note):
    """one 50 % -> 50 % attribution, or the specific reason there is no number to give"""
    if want is None:
        R.add('D6_RESPONSE', cid, label, 'a transition this event can cause',
              'no %s transition is expected here (%s)' % (sig.split('.')[-1], note), 0,
              'NOT_EXPECTED', 'reported instead of being filled in from a neighbouring edge')
        return
    hit = _first_dir(groups, axis, xs, sig, tr, bound, want)
    if hit:
        R.add('D6_RESPONSE', cid, label,
              '%s crosses %.2f V going %s between the edge and the window opening at %s'
              % (sig.split('.')[-1], _half(sig), want, tns(bound * 1e9)),
              '50%% at %.4f ns (delta %.4f ns)' % (hit[1] * 1e9, (hit[1] - tr) * 1e9), 0, 'MEASURED',
              note)
        return
    early = _last_dir_before(groups, axis, xs, sig, tr, EDGE_NS * 1e-9, want)
    if early:
        R.add('D6_RESPONSE', cid, label,
              'an ordering the sampling can resolve: the two 50 %% points must differ by more than '
              'the %.0f ns input ramp' % EDGE_NS,
              'output 50%% at %.4f ns, %.4f ns BEFORE the input 50%% point (the input ramp itself '
              'only ends at %.4f ns)' % (early[1] * 1e9, (tr - early[1]) * 1e9,
                                         (tr + EDGE_NS * 0.5e-9) * 1e9), 0, 'NOT_MEASURED_OVERLAP',
              'a fact about the measurement convention, not a circuit failure: %s' % note)
        return
    R.add('D6_RESPONSE', cid, label,
          '%s crosses %.2f V going %s between the edge and the window opening at %s'
          % (sig.split('.')[-1], _half(sig), want, tns(bound * 1e9)),
          'no %s crossing of %.2f V in %s..%s ns'
          % (sig.split('.')[-1], _half(sig), tns((tr - EDGE_NS * 1e-9) * 1e9), tns(bound * 1e9)), 0,
          'NOT_MEASURED', 'no later edge was borrowed and the window was not widened; %s' % note)


def _last_dir_before(groups, axis, xs, sig, t_from, span, want):
    best = None
    for k, (i, t) in enumerate(xs):
        if t > t_from + 1e-18:
            break
        if t >= t_from - span and _dir_of(groups, axis, xs, k, sig) == want:
            best = (i, t)
    return best


def measure_settle(R, cid, groups, axis, w, enxs):
    """real arrival time of the declared band, and the extreme the current reaches on the way

    The clock runs from the data_en 50 % transition itself, not from the window opening: a window
    that starts 700 ns later would otherwise report a settle time it never measured.
    """
    tr = w['t0'] * 1e-9
    prior = [t for k, t in enxs if t <= tr + 1e-18]
    if not prior:
        R.add('D6_SETTLE', cid, '%s @ %s' % (IOUT, w['label']),
              'a data_en transition precedes the window it explains',
              'no data_en crossing at or before %s ns' % tns(w['t0']), 0, 'NOT_MEASURED',
              'the enable never moved here, so there is nothing to attribute the current to')
        return
    ref = prior[-1]
    bound = ref + SETTLE_BOUND_NS * 1e-9
    start = _sample_index(groups, axis, ref)
    if start is None:
        R.add('D6_SETTLE', cid, '%s @ %s' % (IOUT, w['label']), 'samples exist at the transition',
              'the data does not reach t=%s' % tns(ref * 1e9), 0, 'NOT_AVAILABLE',
              'no extrapolation is made from the samples that are missing')
        return
    want = w['current']
    arrived = None
    extreme = None
    opening = groups[start].get(IOUT)
    j = start
    while j < len(groups) and groups[j][axis] <= bound + 1e-18:
        v = groups[j].get(IOUT)
        j += 1
        if v is None:
            continue
        if extreme is None or abs(v) > abs(extreme):
            extreme = v
        if arrived is None:
            inband = (I_ON_LO <= v <= I_ON_HI) if want == 'on' else (-I_OFF_MAX <= v <= I_OFF_MAX)
            if inband:
                arrived = groups[j - 1][axis]
    if arrived is None:
        R.add('D6_SETTLE', cid, '%s @ %s' % (IOUT, w['label']),
              'the reading enters its declared band within %s ns of the data_en transition'
              % tns(SETTLE_BOUND_NS),
              'never in band; at the transition=%.6g A, extreme over the bound=%.6g A'
              % (opening if opening is not None else float('nan'),
                 extreme if extreme is not None else float('nan')), 0,
              ('EXPECTED_REFUSAL' if w.get('refusable') else 'NOT_MEASURED'),
              'a wide window is not a speed claim; the band and its bound are this round\'s choice')
        return
    R.add('D6_SETTLE', cid, '%s @ %s' % (IOUT, w['label']),
          'time from the data_en 50 %% transition to the first in-band sample, plus the extreme '
          'crossed on the way',
          'settle=%.3f ns after t=%.3f ns ; at the transition=%.6g A ; extreme=%.6g A'
          % ((arrived - ref) * 1e9, ref * 1e9, opening if opening is not None else float('nan'),
             extreme if extreme is not None else float('nan')), 0, 'MEASURED',
          'reported beside the window row, never instead of it')


def emit_key_samples(R, rows, cid, data, case_def, groups, axis, deck_sha, raw_sha):
    """a handful of untouched samples around each declared event, for a reviewer to recompute from"""
    sigs = ['d', 'clk', 'blank', NODES['q'], NODES['data_en'], IOUT]
    clk, _dch, bl = event_steps(case_def)
    centres = sorted(set([t for t, v in clk if v > 0] + [t for t, v in bl]))
    for t in centres:
        idx = _sample_index(groups, axis, t * 1e-9 - 30e-9)
        if idx is None:
            continue
        for i in range(max(0, idx), min(len(groups), idx + 7)):
            g = groups[i]
            vals = ' '.join('%s=%s' % (s, '%.6g' % g[s]) for s in sigs if s in g)
            rows.append([cid, 'event_at_%s' % tns(t), 'raw_samples_around_edge', str(i),
                         '%.9g' % g[axis], vals, 'MEASURED_SAMPLE', deck_sha, raw_sha])


# ------------------------------------------------------------------ negative proof
def negative_report(R, cid, data, case_def, ref_case_id):
    ref = find_case(ref_case_id)
    ref_deck = build_deck(ref, SECTION)
    deck_txt = build_deck(case_def, SECTION)
    ref_full = full_netlist(ref_deck, cell_texts())
    fault_full = full_netlist(deck_txt, cell_texts(case_def.get('fault')))
    stmts, comments = R3.fault_diff(ref_full, fault_full)
    inst_changed = [l for l in stmts if l.lstrip('+-').lstrip().startswith('Xmask')]
    other_changed = [l for l in stmts if l not in inst_changed]
    R.add('D6_FAULT_DECK_DIFF', cid, 'the mask gate instance line is the only difference',
          'exactly one changed netlist statement, naming the blank pin, over deck plus every '
          'included master',
          'statements: %d (Xmask %d, other %d) | comments: %d | %s'
          % (len(stmts), len(inst_changed), len(other_changed), len(comments),
             (inst_changed[0] if inst_changed else '')[:80]), 0,
          'PASS' if len(inst_changed) == 2 and not other_changed else 'BLOCKED',
          'the two statement lines are the -/+ pair of the same instance. A different stimulus, '
          'a different include or a different cell would make the comparison meaningless')
    rows = [r for r in R.rows if r[1] == 'D6_WINDOW_STATE' and r[2] == cid]
    refused = [r for r in rows if r[7] == 'EXPECTED_REFUSAL']
    held = [r for r in rows if r[7] == 'PASS']
    cur = [r for r in R.rows if r[1] == 'D6_WINDOW_CURRENT' and r[2] == cid]
    cur_refused = [r for r in cur if r[7] == 'EXPECTED_REFUSAL']
    blank = [r for r in R.rows if r[1] == 'D6_STIMULUS_READBACK' and r[2] == cid and r[3] == 'blank']
    qhold = [r for r in rows if r[3].startswith(NODES['q'] + ' @ assert')]
    ok = (refused and cur_refused and held and not other_changed and blank and
          all('max=1.8' in r[5] and 'min=0' in r[5] for r in blank) and
          all(r[7] == 'PASS' for r in qhold) and qhold)
    R.add('D6_NEGATIVE_RESULT', cid, 'blank pin tied to vss inside the control cell',
          'the normal blank assertion is refused while Q holds 1, the external blank really toggled '
          '0 -> 1.8 V and only one instance statement differs',
          'state refused=%d held=%d of %d ; current refused=%d ; external blank read back %s'
          % (len(refused), len(held), len(rows), len(cur_refused),
             (blank[0][5][:60] if blank else 'missing')), 0,
          'DETECTED' if ok else 'BLOCKED',
          'a preflight/runner/reader failure would have stopped before this row; DETECTED here is the '
          'circuit refusing the fault, not a tool error')


# ------------------------------------------------------------------ per-case run
MAN_HDR = ['run_id', 'case', 'deck', 'deck_sha256', 'cell_sha256_16', 'section', 'temp_C',
           'rails_V', 'vout_clamp_V', 'analysis', 'preflight_rc', 'spectre_rc', 'runner_verdict',
           'saved_signals', 'window_rows', 'state_verdict']
SAMP_HDR = ['case', 'event', 'kind', 'sample_group_index', 'time_s', 'values', 'status',
            'deck_sha256', 'raw_sha256']
DEV_HDR = ['device_path', 'model', 'L_raw', 'L_m', 'W_raw', 'W_m', 'm', 'D', 'G', 'S', 'B',
           'source_file']
ROWS_HDR = S2.ROWS_HDR
RUN_TIMEOUT_S = 1200


def measure_temp(R, cid, log, data):
    temp_log = temp_hdr = None
    if log and os.path.isfile(log):
        for line in io.open(log, encoding='utf-8', errors='replace'):
            m = re.match(r'\s*temp\s*=\s*([0-9.eE+-]+)', line)
            if m:
                temp_log = m.group(1)
                break
    if data and os.path.isfile(data):
        for line in io.open(data, encoding='utf-8', errors='replace'):
            if line.startswith('VALUE'):
                break
            m = re.match(r'"temp"\s+([0-9.eE+-]+)', line)
            if m:
                temp_hdr = m.group(1)
    ok = temp_log is not None and temp_hdr is not None and abs(float(temp_log) - 27) < 1e-6 \
        and abs(float(temp_hdr) - 27) < 1e-6
    R.add('D6_TEMP_READBACK', cid, os.path.basename(log or '') or 'no log',
          '27 C echoed by the run, in both the log and the psf header',
          'log temp=%s ; header temp=%s' % (temp_log, temp_hdr), 0,
          'PASS' if ok else 'PARTIAL',
          'both values come from files this run produced; the simopt line is not a measurement')
    return temp_log or ''


def run_case(R, cid, scratch, man_rows, samp_rows, opts):
    case_def = find_case(cid)
    if case_def is None:
        R.add('D6_DECK_BUILD', cid, '-', 'an id from this entry\'s own table', 'UNKNOWN_CASE', 0,
              'NOT_AVAILABLE', 'this entry does not invent cases')
        return
    deck, deck_txt, cells = write_case_dir(scratch, case_def)
    sha = hashlib.sha256(deck_txt.encode('utf-8')).hexdigest()
    chash = ' '.join('%s=%s' % (c, hashlib.sha256(t.encode('utf-8')).hexdigest()[:12])
                     for c, t in cells)
    ident = cell_identity()
    same = all(r[4] == r[5] for r in ident)
    dropped = sum(r[3] for r in ident)
    R.add('D6_CELLS_REUSED_VERBATIM', cid, 'the two frozen Scan masters, the two copied Data '
          'subckts and this round\'s four new masters',
          'every device line keeps its repository digest; the only transformation is dropping the '
          'port-direction annotations this build refuses, plus the declared wiring fault',
          'device digests equal=%s | annotation lines dropped=%d | %s'
          % (same, dropped, chash[:90]), 0, 'PASS' if same else 'BLOCKED',
          'repo-sha12 -> deck-sha12 per file: %s'
          % ', '.join('%s %s->%s' % (r[0][:14], r[1], r[2]) for r in ident[:4]))
    devs = devices_of(case_def.get('fault'))
    mix = {}
    for _p, model, _n in devs:
        mix[model] = mix.get(model, 0) + 1
    R.add('D6_DEVICE_COUNT', cid, '%d MOS expanded' % len(devs),
          '29 = 18 (c2mos_dff) + 4 (sc1_scan_gate) + 2 (dd1_inv18) + 4 (data_sink_1ch) + '
          '1 (data_bias_ref), and the mix is %s'
          % ' '.join('%s x%d' % (k, EXPECT_MIX[k]) for k in sorted(EXPECT_MIX)),
          'resolved %d four-terminal devices; mix %s' % (len(devs), ' '.join(
              '%s x%d' % (k, mix[k]) for k in sorted(mix))), 0,
          'PASS' if len(devs) == TOTAL_DEVS and mix == EXPECT_MIX else 'BLOCKED',
          'counted by walking the master bodies, not by reading a comment')
    inter = [n for n in ('q', 'qbar', 'data_en', 'data_en_b', 'vbias_ch', 'node_m')
             if re.search(r'\b[VI]\w+\s*\(\s*%s\s+0\s*\)' % n, deck_txt)]
    R.add('D6_NO_IDEAL_INTERPOSE', cid, 'q / qbar / data_en / data_en_b / vbias_ch / node_m are '
          'real transistor nodes',
          'no vsource or isource is wired between one of them and the reference',
          'drivers found: %s' % (', '.join(inter) or 'none'), 0, 'PASS' if not inter else 'FAIL',
          'the only bench sources are d, clk, blank, iref_in, vcas, the clamp and the rails')
    problems = []
    for item, detail, verdict in audit_frame(case_def, problems):
        R.add(item, cid, 'the framework this deck emits', detail, detail[:0] or 'checked', 0,
              verdict, 'POC_ASSUMPTION stimulus choices, not a timing budget')
    if problems:
        R.add('D6_STIMULUS_INVALID', cid, 'stimulus audit', 'no framework violation',
              ' ; '.join(problems)[:150], 3, 'BLOCKED',
              'the case is refused before the simulator sees it; a timing that was never emitted '
              'cannot be measured')
        return

    pfr = None
    pf_cmd = '%s "%s" %s %s "%s"' % (
        CC.hook('QODER_PF_CMD', 'bash ' + os.path.join(HERE, 'tb_preflight.sh')), deck,
        EXPECTED_VDD, cid, SUPPLY_MAP)
    penv = dict(os.environ)
    penv.pop('PREFLIGHT_STATIC_PROBE', None)
    pfr, pftxt = CC.call(pf_cmd, env=penv)
    pf_ok, pf_reason, pf_summary = CC.preflight_verdict(pfr, pftxt)
    R.add('PREFLIGHT_FULL', cid, os.path.basename(deck),
          'the preflight own rc=0 AND exactly one TESTBENCH_PREFLIGHT: PASS',
          'rc=%s map=%s | %s' % (pfr, SUPPLY_MAP, pf_summary.replace('\n', ' | ')[:90]), pfr,
          'PASS' if pf_ok else 'BLOCKED', pf_reason)
    man = [R.run_id, cid, os.path.basename(deck), sha, chash[:120], SECTION, '27',
           '%s/0' % V18, fmt_v(case_def['vout']),
           'tran stop=%s maxstep=%s gear2only' % (tns(stop_ns(case_def)), tns(MAXSTEP_NS)),
           str(pfr), '', '', '', '', '']
    if not pf_ok:
        man[11:13] = ['NOT_RUN', 'BLOCKED_after_preflight']
        man_rows.append(man)
        R.log.append('=== %s preflight REFUSED rc=%s\n%s' % (cid, pfr, S2.scrub(pftxt)))
        return

    label = 'D6_%s' % cid
    renv = dict(os.environ)
    renv['LABEL'] = label
    rc, run_out = CC.call('%s "%s" %d' % (CC.hook('QODER_RUN_CMD', 'bash ' + os.path.join(
        HERE, 'run_spectre.sh')), deck, RUN_TIMEOUT_S), env=renv)
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
                 % (cid, 'accepted' if runner_ok else 'REJECTED', S2.scrub(pf_summary),
                    S2.scrub(run_out)))
    data = parts.get('datafile', '')
    man[11] = parts.get('spectre_rc', '') or '?'
    man[12] = 'PASS' if runner_ok else 'BLOCKED'
    man[13] = R3.traces_of(data) if data else ''
    if not runner_ok or not data or not os.path.isfile(data):
        man_rows.append(man)
        return

    temp = measure_temp(R, cid, parts.get('logfile', ''), data)
    man[6] = temp or '27'
    measure_stimulus(R, cid, data, case_def)
    measure_bias(R, cid, data, case_def)
    groups, axis = R1.samples_of(data)
    for w in case_def['windows']:
        measure_window(R, cid, data, w)
        measure_window_current(R, cid, data, w)
        measure_analogue(R, cid, data, w)
    measure_responses(R, cid, groups, axis, data, case_def)
    if case_def.get('fault'):
        negative_report(R, cid, data, case_def, 'D6-04')
    deck_sha = sha[:16]
    emit_key_samples(R, samp_rows, cid, data, case_def, groups, axis, deck_sha,
                     R3.file_sha(data)[:16])
    state = [r for r in R.rows if r[1] in ('D6_WINDOW_STATE', 'D6_WINDOW_CURRENT') and r[2] == cid]
    man[14] = str(len(state))
    man[15] = ('PASS' if state and all(r[7] in ('PASS', 'EXPECTED_REFUSAL') for r in state)
               else 'SEE_ROWS')
    man_rows.append(man)


def classify(rows):
    func, depp, info = [], [], []
    for r in rows:
        v = r[7]
        if v in ('PASS', 'FAIL', 'DETECTED', 'EXPECTED_REFUSAL'):
            func.append(r)
        elif v in ('BLOCKED', 'NOT_AVAILABLE'):
            depp.append(r)
        else:
            info.append(r)
    return func, depp, info


def process_counts(scratch):
    """how many spectre processes this run can prove, read off the logs it actually left"""
    dep = dut = 0
    for root, _dirs, files in os.walk(scratch):
        if os.path.basename(root) != 'sim':
            continue
        for f in files:
            if not f.endswith('.log'):
                continue
            if f.startswith('preflight_'):
                dep += 1
            else:
                dut += 1
    return dep, dut


# ------------------------------------------------------------------ static supply negative
def supply_negative(o):
    """disconnect the independent 0 V source and the supply contract must refuse, Spectre-free"""
    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'dd1_sim', 'supply_negative')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    case_def = find_case('D6-03')
    deck, deck_txt, _cells = write_case_dir(scratch, case_def)
    broken = '\n'.join(l for l in deck_txt.split('\n') if not l.startswith('Vss (vss 0)'))
    # next to the deck it came from, so its include lines still resolve: a refusal that is really
    # about a missing vss source must not be reachable by an unparseable master
    bpath = os.path.join(os.path.dirname(deck), 'D6_SN01_vss_disconnected.scs')
    with io.open(bpath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(broken))
    R = S2.Run([], [], 'D6-SN-%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    R.add('D6_SN_SETUP', 'D6_SN01', os.path.basename(bpath),
          'the SAME deck with one line removed: `Vss (vss 0) vsource dc=0\'',
          'deck lines %d -> %d' % (deck_txt.count('\n'), broken.count('\n')), 0, 'MEASURED',
          'a static refusal needs no simulator, and none was called')
    # CC.call runs argv without a shell, so the flag travels in the child's environment (the way the
    # accepted R3 entry passes its own preflight env) rather than as a shell assignment prefix
    cmd = '%s "%s" %s D6_SN01 "%s"' % (
        CC.hook('QODER_PF_CMD', 'bash ' + os.path.join(HERE, 'tb_preflight.sh')), bpath,
        EXPECTED_VDD, SUPPLY_MAP)
    env = dict(os.environ)
    env['PREFLIGHT_STATIC_PROBE'] = '1'
    rc, txt = CC.call(cmd, env=env)
    stage = re.search(r'PREFLIGHT_STAGE=(\S+)', txt or '')
    why = re.search(r'SUPPLY_FAIL[^\n]*', txt or '')
    passes = len(re.findall(r'TESTBENCH_PREFLIGHT: PASS', txt or ''))
    refused = (rc != 0 and 'supply_contract' in (stage.group(1) if stage else '')
               and passes == 0 and bool(why))
    R.add('D6_SUPPLY_NEGATIVE', 'D6_SN01', 'vss has no independent source',
          'the supply_contract stage refuses with rc!=0, no PASS marker and no Spectre call',
          'rc=%s stage=%s | %s' % (rc, stage.group(1) if stage else 'none',
                                   (why.group(0) if why else '')[:100]), rc,
          'DETECTED' if refused else 'FAIL',
          S2.scrub('the static probe exits 7 when it ACCEPTS a deck, so rc=0 here would mean the '
                   'gate opened; the refusal is at stage=supply_contract before any simulator')
                   .replace('\n', ' '))
    dep, dut = process_counts(scratch)
    R.add('D6_NO_SPECTRE_PROOF', 'D6_SN01', scratch,
          'no Spectre log exists anywhere under this mode\'s scratch directory',
          'preflight_logs=%d DUT_logs=%d' % (dep, dut), 0,
          'PASS' if dep + dut == 0 else 'FAIL',
          'the operating-point probe is the only Spectre call tb_preflight.sh makes, and '
          'PREFLIGHT_STATIC_PROBE exits before it')
    out_csv = o.out or os.path.join(PROJ, 'results', 'evidence', 'dd1_d6_supply_negative.csv')
    S2.write_rows(out_csv, R.rows, ROWS_HDR)
    for r in R.rows:
        print('%-24s %-10s %s' % (r[1], r[2], r[7]))
    print('D6_SUPPLY_NEGATIVE rows=%d verdict=%s csv=%s'
          % (len(R.rows), 'DETECTED' if refused else 'NOT_DETECTED', out_csv))
    return 0 if refused else 1


def write_device_csv(path):
    rows = device_size_rows()
    src = {}
    for name, txt in cell_texts():
        for raw in txt.split('\n'):
            m = re.match(r'^\s*subckt\s+(\S+)', raw)
            if m:
                src[m.group(1)] = name
    for r in rows:
        r[11] = src.get(r[11], '')
    S2.write_rows(path, rows, DEV_HDR)
    return rows


# ------------------------------------------------------------------ selftest
def _selftest():
    """this entry's own helpers on synthetic data. NO simulator, NO project data, NO circuit claim"""
    checks = []
    c = find_case('D6-03')
    clk, dch, bl = event_steps(c)
    checks.append(('every input signal has its flip points ordered and at least one edge apart',
                   all(all(x[0] + EDGE_NS <= y[0] for x, y in zip(seq, seq[1:]))
                       for seq in (clk, dch, bl))))
    w = wave(0.0, clk, stop_ns(c))
    pts = re.findall(r'(\S+)\s+(\S+)', w.strip('[]'))
    times = [float(p[0].rstrip('n')) for p in pts]
    checks.append(('the emitted clock wave never repeats or rewinds a time',
                   all(times[i] < times[i + 1] for i in range(len(times) - 1))))
    probs = []
    audit_frame(c, probs)
    checks.append(('the shipped D6-03 framework audits clean (%s)' % (','.join(probs) or 'no problem'),
                   not probs))
    bad = case('BAD', events=[wr(1, 0.0), lv(1, 'blank', 0.0)],
               windows=[win('x', 1, {'q': 'low'})], vout=1.2, purpose='two events on one slot')
    probs2 = []
    audit_frame(bad, probs2)
    checks.append(('a blank change on the same slot as a clock edge is refused', bool(probs2)))
    bad2 = case('BAD2', events=[wr(1, 0.0), lv(2, 'blank', 0.0)],
                windows=[win('x', 1, {'q': 'low'}, current='on')], vout=1.2,
                purpose='a window that spans the next event')
    bad2['windows'][0]['t1'] = 2 * SLOT + 100
    probs3 = []
    audit_frame(bad2, probs3)
    checks.append(('a window that reaches past its own slot is refused', bool(probs3)))
    g = []
    for i in range(0, 3000):
        t = i * MAXSTEP_NS
        den = 1.0 if t < 1500.0 else 0.0
        cur = 15e-6 if t < 1560.0 else 0.0
        g.append({'time': t * 1e-9, 'Xtop.Xunit.data_en': den * V18, 'Ip_out:i': cur})
    xs = R1.crossing_times(g, 'time', 'Xtop.Xunit.data_en', 0.9)
    checks.append(('a 1.8 V falling edge crosses 0.9 V exactly once (%d)' % len(xs), len(xs) == 1))
    R = S2.Run([], [], 'SELFTEST')
    off_win = {'label': 'syn_off', 't0': 2200.0, 't1': 3200.0, 'expect': {}, 'current': 'off'}
    measure_settle(R, 'SYN', g, 'time', off_win, xs)
    settle_ok = (R.rows and R.rows[0][7] == 'MEASURED' and 'settle=60.5' in R.rows[0][5])
    checks.append(('the settle clock starts at the data_en crossing, not at the window (row0=%s)'
                   % (R.rows[0][7] if R.rows else 'none'), settle_ok))
    on_win = {'label': 'syn_on', 't0': 2200.0, 't1': 3200.0, 'expect': {}, 'current': 'on'}
    g2 = [{'time': d['time'], 'Xtop.Xunit.data_en': d['Xtop.Xunit.data_en'], IOUT: 0.0} for d in g]
    R2 = S2.Run([], [], 'SELFTEST')
    measure_settle(R2, 'SYN', g2, 'time', on_win, xs)
    checks.append(('a current that never enters the band is reported, not widened (%s)'
                   % (R2.rows[0][7] if R2.rows else 'none'),
                   R2.rows and R2.rows[0][7] == 'NOT_MEASURED'))
    R3_ = S2.Run([], [], 'SELFTEST')
    measure_settle(R3_, 'SYN', g, 'time', off_win, [])
    checks.append(('no preceding transition is NOT_MEASURED rather than blamed on the circuit',
                   R3_.rows and R3_.rows[0][7] == 'NOT_MEASURED'))
    Rx = S2.Run([], [], 'SELFTEST')
    en = NODES['data_en']
    _response_row(Rx, 'SYN', 'syn after', en, xs, g, 'time', 1400e-9, 2100e-9, 'fall', 'n')
    _response_row(Rx, 'SYN', 'syn overlap', en, xs, g, 'time', 1500e-9, 2200e-9, 'fall', 'n')
    _response_row(Rx, 'SYN', 'syn none', en, xs, g, 'time', 1400e-9, 2100e-9, None, 'n')
    checks.append(('the three attribution outcomes stay three separate verdicts (%s/%s/%s)'
                   % tuple(r[7] for r in Rx.rows),
                   [r[7] for r in Rx.rows] == ['MEASURED', 'NOT_MEASURED_OVERLAP', 'NOT_EXPECTED']))
    ref = build_deck(find_case('D6-04'), SECTION)
    flt = build_deck(find_case('D6-N1'), SECTION)
    st, cm = R3.fault_diff(full_netlist(ref, cell_texts()), full_netlist(flt, cell_texts(
        'blank_pin_to_vss')))
    inst = [l for l in st if l.lstrip('+-').lstrip().startswith('Xmask')]
    other = [l for l in st if l not in inst]
    checks.append(('the declared fault is one instance line over the whole netlist (%d/%d)'
                   % (len(inst), len(other)), len(inst) == 2 and not other))
    raw = u(io.open(os.path.join(PROJ, 'spectre', 'dd1_d6_sink_core.scs'), encoding='utf-8',
                    errors='replace').read())
    norm, removed = strip_direction_annotations(raw)
    checks.append(('the normalisation drops %d direction lines and no device line' % removed,
                   removed > 0 and device_digest(raw) == device_digest(norm) and
                   all(k in norm for k in ('Mpass_local', 'n33_dnw_4t_ckt', 'Mcas', 'Mbleed_local'))))
    deck03 = build_deck(find_case('D6-03'), SECTION) + ''.join(t for _n, t in cell_texts())
    checks.append(('no port-direction annotation survives into what the simulator is handed',
                   not DIRECTION_RE.search(deck03)))
    devs = devices_of()
    mix = {}
    for _p, m, _n in devs:
        mix[m] = mix.get(m, 0) + 1
    checks.append(('29 devices with the declared model mix (%s)' % mix,
                   len(devs) == TOTAL_DEVS and mix == EXPECT_MIX))
    paths = set(n for _p, _m, nets in devs for n in nets)
    missing = [p for k, p in NODES.items() if k not in ('d', 'clk', 'blank', 'vdd18', 'vss')
               and p not in paths]
    checks.append(('every judged hierarchical path really exists as a device terminal (%s)'
                   % (','.join(missing) or 'all'), not missing))
    bad = [n for n, v in checks if not v]
    for n, v in checks:
        print('   %-72s %s' % (n, 'PASS' if v else 'FAIL'))
    print('D6_SELFTEST checks=%d failures=%d (synthetic data; no simulator, no circuit claim)'
          % (len(checks), len(bad)))
    return 1 if bad else 0


def load_rows(path, hdr):
    """read a previous pass back so the representative run stays in the same delivered file"""
    if not path or not os.path.isfile(path):
        return []
    import csv as _csv
    out = []
    # no encoding= here: python 2.6 on the guest hands the csv module bytes, and python 3 gets str
    f = io.open(path, 'r', newline='')
    try:
        rdr = _csv.reader(f)
        head = next(rdr, None)
        if head and [x.strip() for x in head] != [x.strip() for x in hdr]:
            raise SystemExit('HEADER_MISMATCH %s: refusing to append to a different shape' % path)
        for row in rdr:
            if row:
                out.append(row)
    finally:
        f.close()
    return out


def main():
    op = optparse.OptionParser()
    op.add_option('--selftest', action='store_true')
    op.add_option('--dry', action='store_true')
    op.add_option('--devices', action='store_true')
    op.add_option('--supply-negative', action='store_true')
    op.add_option('--append', action='store_true',
                  help='keep the rows a previous pass wrote (the D6-03-first delivery order)')
    op.add_option('--only')
    op.add_option('--expect', type='int', default=0)
    op.add_option('--scratch')
    op.add_option('--out')
    op.add_option('--manifest')
    op.add_option('--samples')
    op.add_option('--devcsv')
    op.add_option('--log')
    o, _ = op.parse_args()
    if o.selftest:
        return _selftest()
    if o.devices:
        path = o.devcsv or os.path.join(PROJ, 'results', 'evidence', 'dd1_d6_device_readback.csv')
        rows = write_device_csv(path)
        print('D6_DEVICES rows=%d expect=%d csv=%s' % (len(rows), TOTAL_DEVS, path))
        return 0 if len(rows) == TOTAL_DEVS else 1
    if o.supply_negative:
        return supply_negative(o)

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

    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'dd1_sim', 'unit_tt')
    evdir = os.path.join(PROJ, 'results', 'evidence')
    out_csv = o.out or os.path.join(evdir, 'dd1_d6_cases.csv')
    man_csv = o.manifest or os.path.join(evdir, 'dd1_d6_manifest.csv')
    samp_csv = o.samples or os.path.join(evdir, 'dd1_d6_samples.csv')
    log_txt = o.log or os.path.join(evdir, 'dd1_d6_dependency_log.txt')
    if o.dry and not o.out:
        out_csv = os.path.join(scratch, 'dry_rows.csv')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)

    R = S2.Run([], [], 'D6-UNIT-%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    man_rows, samp_rows = [], []
    print('RUN_ID %s cases=%d slot=%s ns frame=%s ns maxstep=%s'
          % (R.run_id, len(ids), tns(SLOT), tns(FRAME_T_NS), tns(MAXSTEP_NS)))

    if o.dry:
        for cid in ids:
            case_def = find_case(cid)
            deck, txt, cells = write_case_dir(scratch, case_def)
            problems = []
            audit_frame(case_def, problems)
            R.add('DRY_DECK', cid, os.path.basename(deck),
                  'the deck builds and the frame audits clean',
                  'sha256=%s lines=%d stop=%s problems=%s'
                  % (hashlib.sha256(txt.encode('utf-8')).hexdigest()[:16], txt.count('\n'),
                     tns(stop_ns(case_def)), ','.join(problems) or 'none'), 0,
                  'PASS' if not problems else 'BLOCKED',
                  'dry run only; the deck and the master bytes stay in the scratch directory so '
                  'PREFLIGHT_STATIC_PROBE=1 can be pointed at exactly these files')
            R.add('DRY_WINDOWS', cid, '%d declared windows' % len(case_def['windows']),
                  'every state/current claim is named before anything runs',
                  ' ; '.join('%s[%s..%s]%s%s' % (w['label'], tns(w['t0']), tns(w['t1']),
                                                 '/' + w['current'] if w.get('current') else '',
                                                 '/INIT' if w.get('init') else '')
                             for w in case_def['windows'])[:150], 0, 'MEASURED', 'dry run only')
        S2.write_rows(out_csv, R.rows, ROWS_HDR)
        print('DRY rows=%d decks_in=%s csv=%s' % (len(R.rows), scratch, out_csv))
        return 0

    authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
    if not authorised:
        print('D6_TT_REFUSED run=%s authorisation=%s: RUN=1 AND QODER_SIM_AUTHORISED=1 are both '
              'required. No file under results/evidence is created, truncated or replaced.'
              % (os.environ.get('RUN') or 'unset', os.environ.get('QODER_SIM_AUTHORISED') or 'unset'))
        print('D6_TT_REFUSED cases=%d would_have_been=%s' % (len(ids), ','.join(ids)))
        return 5

    if o.append:
        for r in load_rows(out_csv, ROWS_HDR):
            R.rows.append(r)
        for r in load_rows(man_csv, MAN_HDR):
            man_rows.append(r)
        for r in load_rows(samp_csv, SAMP_HDR):
            samp_rows.append(r)
        print('APPENDED previous rows=%d manifest=%d samples=%d'
              % (len(R.rows), len(man_rows), len(samp_rows)))

    for cid in ids:
        try:
            run_case(R, cid, scratch, man_rows, samp_rows, o)
        except Exception:
            tb = traceback.format_exc()
            R.log.append('=== HARNESS_ERROR %s\n%s' % (cid, tb))
            R.add('HARNESS_ERROR', cid, cid, 'no python exception in the entry',
                  tb.strip().split('\n')[-1][:120], 1, 'BLOCKED',
                  'a harness fault is never scored as a circuit result')
    dep, dut = process_counts(scratch)
    R.add('D6_PROCESS_COUNT', 'all', 'preflight dependency runs vs DUT runs',
          'counted from the logs this scratch keeps, including every attempt',
          'preflight=%d DUT=%d total_spectre=%d' % (dep, dut, dep + dut), 0, 'MEASURED',
          'tb_preflight.sh FULL mode runs its own operating point; this round does not claim that '
          'only the DUT ran')
    write_device_csv(o.devcsv or os.path.join(evdir, 'dd1_d6_device_readback.csv'))
    S2.write_rows(out_csv, R.rows, ROWS_HDR)
    S2.write_rows(man_csv, man_rows, MAN_HDR)
    S2.write_rows(samp_csv, samp_rows, SAMP_HDR)
    if R.log:
        prev = ''
        if o.append and os.path.isfile(log_txt):
            prev = u(io.open(log_txt, encoding='utf-8', errors='replace').read()) + '\n'
        with io.open(log_txt, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(S2.scrub(prev + '\n'.join(R.log))))
    func, depp, info = classify(R.rows)
    fails = [r for r in func if r[7] == 'FAIL']
    print('D6_TT cases=%d rows=%d functional_FAIL=%d dependency=%d informational=%d '
          'preflight=%d DUT=%d' % (len(ids), len(R.rows), len(fails), len(depp), len(info), dep, dut))
    print('D6_TT out=%s manifest=%s samples=%s log=%s' % (out_csv, man_csv, samp_csv, log_txt))
    if fails:
        return 1
    if depp:
        return 4
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(3)
