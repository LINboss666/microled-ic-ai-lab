# -*- coding: utf-8 -*-
"""DATA-7A independent grey-scale timing checker (four-state trace -> verdicts and CSV rows).

    python scripts/dd1_d7a_check.py --selftest
    python scripts/dd1_d7a_check.py --main    <file.vcd> --out <rows.csv> [--run-id <id>]
    python scripts/dd1_d7a_check.py --control <file.vcd> --scenarios <cases.json> --out <rows.csv>

Independence rules, fixed in `reports/dd1_d7a_contract.md` section 7 before the RTL was written:

* every number comes out of the trace. The applied mode and code values are read back from the
  stimulus signals, the tick period and the reference-clock period are measured from the clock and
  tick edges, and the conducting segments are measured from `data_en` edges;
* the expected interval count comes from the hand-typed table below, never from the design's own
  arithmetic, and never from multiplying a grey code by a compile-time tick constant;
* the testbench's own verdict is never read;
* anything the trace does not actually show is a refusal (`Refuse`) or a failure (`Fail`), not a
  default value, and never an absent row.
"""
from __future__ import print_function

import hashlib
import io
import os
import sys

try:
    _text = unicode
except NameError:
    _text = str

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7a_trace as tv                                        # noqa: E402

PS = 1000                                                         # one nanosecond in picoseconds
MODE_PURE, MODE_HYBRID = 0, 1
MODE_NAME = {MODE_PURE: 'PURE', MODE_HYBRID: 'HYBRID'}
FULL = {MODE_PURE: 256, MODE_HYBRID: 64}                          # intervals in a full window
MAX_CODE = {MODE_PURE: 255, MODE_HYBRID: 63}
PAM_PURE_SYMBOL = 7                                               # a code value, not a current claim
ST = {0: 'IDLE', 1: 'ARMED', 2: 'RUNNING', 3: 'DONE', 4: 'ABORT'}
PURE_100HZ, PURE_60HZ = 30, 50
HYB_100HZ, HYB_60HZ = 120, 200
FRAME_HZ = {(MODE_PURE, PURE_100HZ): 100, (MODE_PURE, PURE_60HZ): 60,
            (MODE_HYBRID, HYB_100HZ): 100, (MODE_HYBRID, HYB_60HZ): 60}
CLK_NS = 10


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def format_vec(value, width):
    return bin(int(value))[2:].zfill(width)[-width:]


def fmt_ns(t_ps):
    if t_ps % PS == 0:
        return '%d' % (t_ps // PS)
    return '%.3f' % (float(t_ps) / PS)


# ------------------------------------------------------------------- expectation table
# Hand-typed literals, spelled out one by one so a reviewer can read the number. --selftest
# compares them against expected_intervals(), so a wrong formula cannot pass unnoticed.
HAND_INTERVALS = {
    (MODE_PURE, 0): 0,
    (MODE_PURE, 1): 1,
    (MODE_PURE, 2): 2,
    (MODE_PURE, 7): 7,
    (MODE_PURE, 128): 128,
    (MODE_PURE, 254): 254,
    (MODE_PURE, 255): 256,
    (MODE_HYBRID, 0): 0,
    (MODE_HYBRID, 1): 1,
    (MODE_HYBRID, 2): 2,
    (MODE_HYBRID, 32): 32,
    (MODE_HYBRID, 62): 62,
    (MODE_HYBRID, 63): 64,
}


def expected_intervals(mode, code):
    """contract section 2. None means the mode/code pair is not a legal configuration."""
    if mode == MODE_PURE:
        if code == 255:
            return 256
        if 0 <= code <= 254:
            return code
        return None
    if mode == MODE_HYBRID:
        if code == 63:
            return 64
        if 0 <= code <= 62:
            return code
        return None
    return None


class Refuse(Exception):
    """the trace cannot be judged at all: structural problem, missing signal, bad time base"""


class Fail(object):
    def __init__(self, tag, detail):
        self.tag = tag
        self.detail = detail

    def __str__(self):
        return '%s(%s)' % (self.tag, self.detail)


# ------------------------------------------------------------------- trace helpers
def sig_bits(tr, name, t_ps, why, fails):
    raw = tr.value_at(name, t_ps)
    ok, val = tv.bits(raw)
    if not ok:
        fails.append(Fail('UNKNOWN_VALUE', '%s is %s at %s ns where %s'
                          % (name, raw, fmt_ns(t_ps), why)))
    return (ok, val, raw)


def read_stable_code(tr, name, t_from, t_to, what, fails):
    vals = tr.values_in(name, t_from, t_to)
    bad = sorted(v for v in vals if any(c in tv.XZ for c in v))
    if bad:
        fails.append(Fail('UNKNOWN_VALUE', '%s holds %s inside %s' % (name, bad, what)))
        return (False, None, bad)
    if len(vals) != 1:
        fails.append(Fail('NOT_STABLE', '%s changes inside %s: %s' % (what, name, sorted(vals))))
        return (False, None, sorted(vals))
    return (True, int(list(vals)[0], 2), sorted(vals))


def uniform(steps):
    if not steps:
        return None
    if min(steps) != max(steps):
        return ('JITTER', sorted(set(fmt_ns(s) for s in steps)))
    return steps[0]


# ------------------------------------------------------------------- signal map
TBI = ('clk', 'tick', 'blank', 'fault', 'reset_n', 'system_en', 'latch_stb', 'pwm_start',
       'cfg_valid', 'case_id', 'mode')
DUTO = ('data_en', 'data_en_b', 'pam_sel', 'win_state', 'cfg_version', 'proto_err', 'obs_tick',
        'cfg_pure', 'cfg_hyb_time', 'cfg_hyb_pam')
PROTO_ERR_W = 8
REF_PERIOD_PS = 10 * PS                    # the contract's fixed digital POC reference clock


class SigMap(object):
    """locate the testbench scope and the two data-channel instances from the dump itself"""

    def __init__(self, tr):
        cid = [k for k in tr.changes if k.endswith('/case_id')]
        if len(cid) != 1:
            raise Refuse('expected exactly one */case_id marker, found %d' % len(cid))
        self.tb = cid[0][:-len('/case_id')]
        duts = sorted(set(k[:-len('/data_en')] for k in tr.changes if k.endswith('/data_en')))
        if len(duts) != 2:
            raise Refuse('this task verifies two logical data channels behind common control: expected '
                         'exactly two */data_en, found %d (%s)' % (len(duts), ', '.join(duts) or 'none'))
        self.dut = duts
        self.tag = [d.rsplit('/', 1)[-1] for d in duts]
        for nm in TBI:
            tr.resolve(self.i(nm))
        for d in duts:
            for nm in DUTO:
                tr.resolve(d + '/' + nm)

    def i(self, name):
        return self.tb + '/' + name

    def o(self, idx, name):
        return self.dut[idx] + '/' + name


def cases(tr, sm):
    hist = tr.edges(sm.i('case_id'))
    if not hist:
        raise Refuse('the case marker never changes: there is no case to judge')
    out = []
    for k, (t, v) in enumerate(hist):
        end = hist[k + 1][0] if k + 1 < len(hist) else tr.end_time
        ok, val = tv.bits(v)
        if not ok:
            continue
        if end <= t:
            raise Refuse('case %s has zero length at %s ns' % (val, fmt_ns(t)))
        out.append((val, t, end))
    if not out:
        raise Refuse('every case marker value is unknown or unresolved: no case can be identified')
    ids = [c[0] for c in out]
    if len(set(ids)) != len(ids):
        raise Refuse('a case id repeats inside one trace: %s'
                     % sorted(set(x for x in ids if ids.count(x) > 1)))
    return out


# ------------------------------------------------------------------- main-matrix judgement
def judge_main(tr, sm, idx, cs, ce, fails):
    """measure one instance of one main-matrix case; returns a row fragment or None"""
    blank_f = tr.falls(sm.i('blank'), cs, ce)
    if len(blank_f) != 1:
        raise Refuse('a main case releases blank exactly once, saw %d falls in [%s, %s] ns'
                     % (len(blank_f), fmt_ns(cs), fmt_ns(ce)))
    t_bl = blank_f[0]
    latch_r = tr.rises(sm.i('latch_stb'), cs, ce)
    start_r = tr.rises(sm.i('pwm_start'), cs, ce)
    if len(latch_r) != 1 or len(start_r) != 1:
        raise Refuse('a main case latches once (%d) and starts once (%d)' % (len(latch_r), len(start_r)))
    t_lat, t_str = latch_r[0], start_r[0]
    if not (cs <= t_lat < t_str < t_bl):
        raise Refuse('main-case order must be LATCH, PWM_START, blank release; saw %s %s %s ns'
                     % (fmt_ns(t_lat), fmt_ns(t_str), fmt_ns(t_bl)))
    ok_m, mode, raw_mode = sig_bits(tr, sm.i('mode'), t_lat, 'is the mode read at LATCH', fails)
    if not ok_m:
        return None
    if mode not in FULL:
        fails.append(Fail('ILLEGAL_MODE_IN_MAIN', 'mode=%s is not Pure or Hybrid, so this case cannot '
                                                  'claim a legal configuration' % raw_mode))
        return None

    if tr.value_at(sm.i('cfg_valid'), t_lat) != '1':
        fails.append(Fail('LATCH_WITHOUT_VALID_CFG', 'cfg_valid is not high at the LATCH edge'))
    if tr.value_at(sm.i('blank'), t_lat) != '1':
        fails.append(Fail('LATCH_OUTSIDE_BLANK', 'LATCH happened while blank was already released'))

    full = FULL[mode]
    tick_r = tr.rises(sm.i('tick'), cs, ce)
    clk_all = tr.rises(sm.i('clk'), cs, ce)
    if t_bl in tick_r:
        raise Refuse('a tick rises exactly at the blank release: t0 would be ambiguous')
    if [t for t in tick_r if t < t_bl and tr.value_at(sm.i('blank'), t) != '1']:
        raise Refuse('a tick was applied before the blank release at a time blank was not asserted')
    after = [t for t in tick_r if t > t_bl]
    if not after:
        fails.append(Fail('NO_T0', 'no tick after the blank release: the window never started'))
        return None
    # t0 is the reference edge that consumes the first tick presented after the blank release
    edge_after = [t for t in clk_all if t > after[0]]
    if not edge_after:
        fails.append(Fail('NO_T0', 'no reference edge after the first tick following the blank '
                                   'release: nothing could consume it'))
        return None
    t0 = edge_after[0]
    need = full + 2                                             # through the window end plus two ticks
    dif = [after[k] - after[k - 1] for k in range(1, len(after))]
    if not dif:
        fails.append(Fail('TICK_TOO_FEW', 'no second tick after the blank release: the window cannot '
                                          'be timed'))
        return None
    T = uniform(dif[:min(need, len(dif))])
    if isinstance(T, tuple):
        fails.append(Fail('TICK_SPACING_UNSTABLE', 'tick steps inside the window %s' % (T[1],)))
        return None
    window_end = t0 + full * T
    tail_end = window_end + 2 * T
    if ce < tail_end:
        fails.append(Fail('TRUNCATED_TRACE', 'the case stops at %s ns, before the window end %s ns plus '
                                            'two idle ticks' % (fmt_ns(ce), fmt_ns(window_end))))
        return None
    if len(dif) < need:
        fails.append(Fail('TICK_TOO_FEW', 'the judged window needs %d tick steps, the trace only shows %d'
                                             % (need, len(dif))))
        return None
    if after[0] - t_bl > T:
        fails.append(Fail('T0_LATE', 'the first tick after the blank release arrives %s ns later, so it '
                                     'is not the first valid tick' % fmt_ns(after[0] - t_bl)))
    clk_r = tr.rises(sm.i('clk'), t0, tail_end)
    if len(clk_r) < 3:
        fails.append(Fail('CLK_TOO_FEW', 'only %d reference edge(s) inside the judged window'
                          % len(clk_r)))
        return None
    tclk = uniform([clk_r[k + 1] - clk_r[k] for k in range(len(clk_r) - 1)])
    if isinstance(tclk, tuple):
        fails.append(Fail('CLK_SPACING_UNSTABLE', 'reference period inside the window is %s'
                          % (tclk[1],)))
        return None
    if tclk != REF_PERIOD_PS:
        fails.append(Fail('TIME_BASE_MISMATCH', 'the measured reference period is %s ns, the contract '
                                                'fixes the digital POC clock at %s ns'
                          % (fmt_ns(tclk), fmt_ns(REF_PERIOD_PS))))
    if T % tclk != 0:
        fails.append(Fail('TICK_NOT_ALIGNED', 'measured tick spacing %s ns is not an integer multiple of '
                                             'the measured reference period %s ns'
                          % (fmt_ns(T), fmt_ns(tclk))))

    if mode == MODE_PURE:
        ok_c, code, _ = read_stable_code(tr, sm.o(idx, 'cfg_pure'), t_lat, tail_end,
                                         'LATCH through the window tail', fails)
        pam_exp = PAM_PURE_SYMBOL
    else:
        ok_c, code, _ = read_stable_code(tr, sm.o(idx, 'cfg_hyb_time'), t_lat, tail_end,
                                         'LATCH through the window tail', fails)
        ok_p, pam_read, _ = read_stable_code(tr, sm.o(idx, 'cfg_hyb_pam'), t_lat, tail_end,
                                             'LATCH through the window tail', fails)
        pam_exp = pam_read
        if not ok_p:
            ok_c = False
    if not ok_c:
        return None
    exp = expected_intervals(mode, code)
    if exp is None:
        fails.append(Fail('CODE_OUT_OF_CONTRACT', 'mode=%s code=%d is not in the contract table'
                          % (MODE_NAME[mode], code)))
        return None

    r = {'mode': MODE_NAME[mode], 'time_code': code, 'pam_code': pam_exp, 'tick_ns': fmt_ns(T),
         'frame_hz': FRAME_HZ.get((mode, T // PS), 'UNMATCHED'), 'exp_intervals': exp,
         'full_intervals': full, 'clk_ns': fmt_ns(tclk), 't0_ns': fmt_ns(t0),
         'window_end_ns': fmt_ns(window_end), 'tail_end_ns': fmt_ns(tail_end)}

    early = [t for t in tr.rises(sm.o(idx, 'data_en'), cs, t0 - 1)]
    if early:
        fails.append(Fail('LIGHT_BEFORE_T0', '%d data_en rise(s) before t0, first at %s ns'
                                          % (len(early), fmt_ns(early[0]))))
    if tr.value_at(sm.o(idx, 'data_en'), t_bl) != '0':
        fails.append(Fail('LIGHT_DURING_BLANK', 'data_en is %s at the blank release'
                                             % tr.value_at(sm.o(idx, 'data_en'), t_bl)))

    if tr.value_at(sm.o(idx, 'data_en'), ce) == '1':
        fails.append(Fail('NO_DEASSERTION', 'data_en is still high at the end of the case: the window '
                                            'endpoint is missing'))
        return None
    segs = tr.segments(sm.o(idx, 'data_en'), t0, ce)
    if exp == 0:
        if segs:
            fails.append(Fail('SEGMENT_COUNT', 'code %d must stay dark, measured %d segment(s), first '
                                              '(%s, %s) ns' % (code, len(segs), fmt_ns(segs[0][0]),
                                                               fmt_ns(segs[0][1]))))
    elif len(segs) != 1:
        fails.append(Fail('SEGMENT_COUNT', 'expected exactly one conducting segment, measured %d: %s'
                          % (len(segs), ['(%s,%s)' % (fmt_ns(a), fmt_ns(b)) for a, b in segs[:4]])))
    else:
        on, off = segs[0]
        if on != t0:
            fails.append(Fail('ON_START', 'conduction starts at %s ns, contract says t0 = %s ns'
                              % (fmt_ns(on), fmt_ns(t0))))
        if off != t0 + exp * T:
            fails.append(Fail('ON_WIDTH', 'conduction ends at %s ns, %s ticks after t0; contract wants '
                                          '%d intervals -> %s ns'
                              % (fmt_ns(off), fmt_ns(off - t0), exp, fmt_ns(t0 + exp * T))))
    width = sum(b - a for a, b in segs)
    r['on_segments'] = len(segs)
    r['on_width_ns'] = fmt_ns(width)
    r['on_intervals_measured'] = width // T if T else 0
    if width % T != 0:
        fails.append(Fail('WIDTH_NOT_MULTIPLE', 'measured width %s ns is not an integer number of the '
                                                'measured %s ns tick' % (fmt_ns(width), fmt_ns(T))))
    r['on_ns'] = fmt_ns(segs[0][0]) if segs else 'none'
    r['off_ns'] = fmt_ns(segs[0][1]) if len(segs) == 1 else 'none'

    late = [t for t in tr.rises(sm.o(idx, 'data_en'), window_end, ce)]
    if late:
        fails.append(Fail('REOPEN_AFTER_WINDOW', 'data_en opens again at %s ns, past the window end '
                                                 '%s ns' % (fmt_ns(late[0]), fmt_ns(window_end))))
    if tr.value_at(sm.o(idx, 'data_en'), window_end) != '0' or \
            [t for t, v in tr.edges(sm.o(idx, 'data_en')) if window_end <= t <= tail_end and v == '1']:
        fails.append(Fail('NO_OFF_TAIL', 'data_en is not held off for the two ticks after the window end'))

    vals = tr.values_in(sm.o(idx, 'pam_sel'), t_bl, tail_end)
    bad = sorted(v for v in vals if any(c in tv.XZ for c in v))
    if bad:
        fails.append(Fail('UNKNOWN_VALUE', 'pam_sel holds %s inside the judged window' % bad))
        r['pam_held'] = 'UNKNOWN'
    elif vals != set([format_vec(pam_exp, 3)]):
        fails.append(Fail('PAM_NOT_HELD', 'pam_sel is %s between the blank release and two ticks past '
                                          'the window end; contract holds %s'
                          % (sorted(vals), format_vec(pam_exp, 3))))
        r['pam_held'] = 'FAIL'
    else:
        r['pam_held'] = 'PASS'

    times = sorted(set([t for t, _v in tr.edges(sm.o(idx, 'data_en')) if t_bl <= t <= tail_end]
                       + [t for t, _v in tr.edges(sm.o(idx, 'data_en_b')) if t_bl <= t <= tail_end]))
    bad_b = []
    for t in times:
        a = tr.value_at(sm.o(idx, 'data_en'), t)
        b = tr.value_at(sm.o(idx, 'data_en_b'), t)
        if a in tv.XZ or b in tv.XZ:
            bad_b.append('%s ns %s/%s unknown' % (fmt_ns(t), a, b))
        elif (a == '1') == (b == '1'):
            bad_b.append('%s ns data_en=%s data_en_b=%s' % (fmt_ns(t), a, b))
    if bad_b:
        fails.append(Fail('DATA_EN_B_COMPLEMENT', '%d of %d sampled edges are not complementary, first %s'
                                            % (len(bad_b), len(times), bad_b[0])))
    r['data_en_b'] = 'PASS' if not bad_b else 'FAIL'

    bad_s = []
    for t, want in ((t_bl, ST[1]), (t0, ST[2]), (window_end, ST[3])):
        ok_s, val, raw = sig_bits(tr, sm.o(idx, 'win_state'), t, 'is win_state at %s ns' % fmt_ns(t), fails)
        if ok_s and ST.get(val) != want:
            bad_s.append('%s ns: %s want %s' % (fmt_ns(t), ST.get(val, raw), want))
    if set([format_vec(4, 3)]) & tr.values_in(sm.o(idx, 'win_state'), cs, ce):
        bad_s.append('ABORT reached inside a legal main case')
    if bad_s:
        fails.append(Fail('WIN_STATE', ' ; '.join(bad_s[:3])))
    r['win_state'] = 'PASS' if not bad_s else 'FAIL'
    # the completion boundary is read out of this instance's own state trace, not computed from the
    # shared stimulus, so a late channel cannot hide behind the common t0
    done_e = [t for t, v in tr.edges(sm.o(idx, 'win_state'))
              if t0 <= t <= min(ce + T, window_end + 4 * T) and v == format_vec(3, 3)]
    if not done_e:
        fails.append(Fail('DONE_MISSING', '%s.win_state never reaches DONE inside the case, so this '
                                          'channel did not finish the window' % sm.tag[idx]))
        r['done_ns'] = 'none'
    elif done_e[0] != window_end:
        fails.append(Fail('DONE_EDGE', '%s.win_state reaches DONE at %s ns, contract says the window '
                                       'end %s ns' % (sm.tag[idx], fmt_ns(done_e[0]),
                                                      fmt_ns(window_end))))
        r['done_ns'] = fmt_ns(done_e[0])
    else:
        r['done_ns'] = fmt_ns(done_e[0])

    vers = tr.values_in(sm.o(idx, 'cfg_version'), cs, ce)
    ok_v0, v0, _ = sig_bits(tr, sm.o(idx, 'cfg_version'), cs, 'is cfg_version at the case start', fails)
    ok_v1, v1, _ = sig_bits(tr, sm.o(idx, 'cfg_version'), tail_end, 'is cfg_version after the window',
                            fails)
    if any(any(c in tv.XZ for c in v) for v in vers):
        fails.append(Fail('CFG_VERSION', 'cfg_version contains an unknown value inside the case'))
    elif len(vers) != 2 or not (ok_v0 and ok_v1 and v1 == v0 + 1):
        fails.append(Fail('CFG_VERSION', 'one accepted LATCH must move cfg_version by exactly one, saw %s'
                          % sorted(vers)))
    r['cfg_version'] = str(v1) if ok_v1 else 'UNKNOWN'

    errs = tr.values_in(sm.o(idx, 'proto_err'), cs, ce)
    if errs - set(['0' * PROTO_ERR_W]):
        fails.append(Fail('PROTO_ERR_IN_MAIN', 'a legal main case recorded %s'
                          % sorted(errs - set(['0' * PROTO_ERR_W]))))

    obs = tr.rises(sm.o(idx, 'obs_tick'), cs, ce)
    obs_bad = []
    for t in obs:
        if t not in tick_r:
            obs_bad.append('%s ns is not a tick edge' % fmt_ns(t))
        elif not (t_bl <= t <= window_end):
            obs_bad.append('%s ns is outside the accepted tick span [%s, %s]'
                           % (fmt_ns(t), fmt_ns(t_bl), fmt_ns(window_end)))
    if obs_bad:
        fails.append(Fail('OBS_TICK_MISMATCH', '%d obs_tick edge(s) are not accepted window ticks, '
                                               'first %s' % (len(obs_bad), obs_bad[0])))
    if len(obs) != full + 1:
        fails.append(Fail('OBS_TICK_COUNT', 'the controller accepted %d ticks but the window has %d '
                                            'intervals plus its end event' % (len(obs), full)))
    r['obs_tick'] = 'PASS' if not obs_bad else 'FAIL'
    r['obs_tick_pulses'] = len(obs)

    for nm in [sm.i('mode'), sm.i('blank'), sm.i('tick'), sm.i('clk'), sm.i('case_id')] + \
              [sm.o(idx, k) for k in ('data_en', 'data_en_b', 'pam_sel', 'win_state', 'obs_tick')]:
        sp = tr.unknown_spans(nm, t_bl, tail_end)
        if sp:
            fails.append(Fail('UNKNOWN_IN_WINDOW', '%s is x/z over %d span(s), first (%s, %s) ns'
                              % (nm, len(sp), fmt_ns(sp[0][0]), fmt_ns(sp[0][1]))))
            break
    return r


def check_main_trace(path, run_id=''):
    tr = tv.Trace(path)
    sm = SigMap(tr)
    rows = []
    for cid, cs, ce in cases(tr, sm):
        fails = []
        parts = [judge_main(tr, sm, idx, cs, ce, fails) for idx in (0, 1)]
        for idx in (0, 1):
            if parts[idx] is None and not any(str(f).startswith('UNKNOWN') for f in fails):
                fails.append(Fail('UNJUDGED', '%s could not be measured' % sm.tag[idx]))
        row = {'case_id': cid, 'vcd': os.path.basename(path), 'run_id': run_id}
        for idx, pre in ((0, 'a_'), (1, 'b_')):
            if parts[idx] is not None:
                for k, v in parts[idx].items():
                    row[pre + k] = v
        if parts[0] is not None and parts[1] is not None:
            diff = sorted(k for k in parts[0] if parts[0][k] != parts[1][k])
            if diff:
                fails.append(Fail('INSTANCES_DIFFER', 'behind identical control and configuration the two '
                                                      'channels disagree on %s (%s vs %s)'
                                  % (diff[0], parts[0][diff[0]], parts[1][diff[0]])))
            row['instances_match'] = 'PASS' if not diff else 'FAIL'
            for k in ('mode', 'frame_hz', 'time_code', 'pam_code', 'tick_ns', 'exp_intervals',
                      'full_intervals'):
                row[k] = parts[0][k]
        else:
            row['instances_match'] = 'UNJUDGED'
        row['verdict'] = 'PASS' if not fails else 'FAIL'
        row['failures'] = ' ; '.join(str(f) for f in fails)[:500] if fails else 'none'
        rows.append(row)
    return rows, tr


# ------------------------------------------------------------------- control / abort judgement
CONTROL_REQUIREMENT = {
    'async_off_between_edges': 'blank or fault asserted between clock edges pulls data_en low at that '
                               'same simulation time, on both channels, and the declared pulse width '
                               'and phase are what the trace actually shows',
    'no_auto_resume': 'withdrawing blank, clearing fault or releasing reset does not re-open the aborted '
                      'window, and the abort is recorded',
    'start_held_40ns_once': 'PWM_START held 40 ns is accepted once; the window keeps the code width',
    'tick_in_blank_consumed': 'a tick inside blank or before an accepted start consumes nothing, and the '
                              'first armed window still matches its code',
    'window_ok': 'this window is exactly as many conducting intervals as the displayed code, measured on '
                 'both channels, with the stimulus attested first',
    'mixed_codes': 'the two channels carry different codes but share one window start and completion '
                   'edge, each measured from that channel\'s own output',
    'pam_toggle': 'each window holds its own latched PAM code and never falls back at PWM off',
    'refused_dark': 'the request is refused, recorded in proto_err, and produces no light at all',
    'refused_then_window': 'the refused request is recorded and does not disturb the window that the '
                           'accepted request already committed',
    'dark_only': 'with no accepted configuration nothing may light and the window state never runs',
    'clock_stall': 'a frozen reference domain consumes no tick and holds the output state, in the phase '
                   'the scenario declares',
    'display_frozen': 'loading the next grey code during a running window moves neither the waveform nor '
                      'the held PAM code',
    'config_freshness': 'one complete load feeds exactly one accepted LATCH; a replayed LATCH is refused '
                        'and does not step the version',
    'abort_reauthorise': 'after an abort neither a bare start nor a load without a LATCH re-lights the '
                         'old configuration',
    'mode_bypass': 'a mode refused in the unsafe phase cannot be adopted through a LATCH, and the '
                   'refusal is not erased',
    'mode_switch_safe': 'a mode adopted in the safe phase is what the following window really displays',
    'recover_full_sequence': 'a complete new load / LATCH / start after an abort displays the new code',
    'abort_pending': 'an abort revokes a load that was prepared but unconsumed before it: the '
                     'post-abort LATCH and START stay dark, record the refusal and do not step the version',
    'abort_pending_recover': 'only a load transaction that arrives after the abort can restore the '
                             'display, and it then conducts its own code',
    'next_window_commit': 'a next load prepared inside window A leaves A untouched, is committed by the '
                          'first LATCH after A completes, drives window B with its own code and PAM, and '
                          'is consumed exactly once',
    'code_edges': 'the code boundary values keep their contract widths on both channels in both windows',
    'start_latch_same_edge': 'LATCH and START on one sampling edge: the LATCH commits, the start is '
                            'refused, and nothing lights',
}

E_LATCH_REJECTED = 1
E_INCOMPLETE_CFG = 2
E_ILLEGAL_MODE = 4
E_MODE_WHILE_RUNNING = 8
E_START_REJECTED = 16
E_LATCH_AMBIGUOUS = 32
E_STALE_CONFIG = 64
E_MODE_NOT_ADOPTED = 128


def bits_set(tr, name, cs, ce, want, fails, who):
    vals = sorted(tr.values_in(name, cs, ce))
    hit = [v for v in vals if not any(c in tv.XZ for c in v) and (int(v, 2) & want) == want]
    if not hit:
        fails.append(Fail('REFUSAL_NOT_RECORDED', '%s never shows bit %d in %s' % (who, want, vals)))
    return hit


def no_light(tr, sm, cs, ce, fails, t_from=None, t_to=None, who=''):
    """this channel must not conduct from t_from (default: case start) to t_to (default: case end)"""
    start = cs if t_from is None else t_from
    stop = ce if t_to is None else t_to
    out = []
    for idx in (0, 1):
        rises = tr.rises(sm.o(idx, 'data_en'), start, stop)
        if rises:
            fails.append(Fail('LIGHT_AFTER_REFUSAL', '%s.data_en opens at %s ns%s'
                              % (sm.tag[idx], fmt_ns(rises[0]), who)))
        out.append('%s=%d' % (sm.tag[idx], len(rises)))
    return ' '.join(out)


def attest_windows(tr, sm, cs, ce, sc, fails, idx=0, stable_codes=True):
    """check the scenario's declared (mode, code, pam) per window against the trace it claims to show"""
    declared = sc.get('windows', [])
    measured = []
    blank_f = tr.falls(sm.i('blank'), cs, ce)
    if declared and len(blank_f) < len(declared):
        fails.append(Fail('STIMULUS_UNATTESTED', 'the scenario declares %d window(s) but the trace shows '
                                                 '%d blank release(s)' % (len(declared), len(blank_f))))
    want = sc.get('mode_values', [])
    if want:
        vals = sorted(set(int(v, 2) for _t, v in tr.edges(sm.i('mode'))
                          if v and not any(c in tv.XZ for c in v)))
        missing = [m for m in want if m not in vals]
        if missing:
            fails.append(Fail('STIMULUS_UNATTESTED', 'the mode bus never shows %s (saw %s)'
                              % (missing, vals)))
    for n in range(len(declared)):
        lats = sc.get('commit_latches')
        w = measure_nth_window(tr, sm, idx, cs, ce, fails, n, stable_codes=stable_codes,
                               lat_idx=(lats[n] if lats else None))
        measured.append(w)
        if not w:
            continue
        dm, dc, dp = list(declared[n])[:3]
        if w['mode'] != dm or w['code'] != dc or w['pam_exp'] != dp:
            fails.append(Fail('STIMULUS_MISMATCH', 'window %d was declared %s code=%s pam=%s but the '
                                                   'trace reads %s code=%s pam=%s'
                              % (n, dm, dc, dp, w['mode'], w['code'], w['pam_exp'])))
    return measured


def w_abort(n):
    """is this window declared as deliberately aborted?"""
    return n in getattr(judge_windows, 'abort_windows', set())


def judge_windows(tr, sm, cs, ce, sc, fails, measured, start_at=0):
    """after attestation, every declared window must conduct exactly its own interval count"""
    out = []
    judge_windows.abort_windows = set(int(x) for x in sc.get('aborted_windows', []))
    for n in range(start_at, len(measured)):
        w = measured[n]
        if not w:
            continue
        for idx in (0, 1):
            lats = sc.get('commit_latches')
            one = w if idx == 0 else measure_nth_window(
                tr, sm, idx, cs, ce, fails, n, stable_codes=sc.get('stable_codes', True),
                lat_idx=(lats[n] if lats else None))
            if not one:
                continue
            got = _widths_ticks(one['segs'], one['T'])
            want = [one['exp']] if one['exp'] else []
            if sc.get('stall_phase'):
                # a frozen domain stretches the elapsed width, so claim the boundaries this channel
                # actually consumed rather than the wall time between them
                got = [len([t for t in tr.rises(sm.i('tick'), a, b) if a < t <= b])
                       for a, b in one['segs']]
            if w_abort(n):
                if len(one['segs']) > 1 or (one['segs'] and one['segs'][0][0] != one['t0']):
                    fails.append(Fail('ABORTED_WINDOW_SHAPE', 'window %d on %s was meant to be aborted '
                                                             'but does not show one segment from its own '
                                                             't0: %s' % (n, sm.tag[idx], got)))
            elif got != want:
                fails.append(Fail('ON_WIDTH', 'window %d on %s conducted %s ticks, the displayed code '
                                  'asks %s' % (n, sm.tag[idx], got, want)))
            if one['segs'] and one['segs'][0][0] != one['t0']:
                fails.append(Fail('ON_START', 'window %d on %s starts at %s ns, its own t0 is %s ns'
                                  % (n, sm.tag[idx], fmt_ns(one['segs'][0][0]), fmt_ns(one['t0']))))
            stall = _stall_total(tr, sm, cs, ce, one)
            done = [t for t, v in tr.edges(sm.o(idx, 'win_state'))
                    if one['t0'] <= t <= one['window_end'] + stall + 4 * one['T']
                    and v == format_vec(3, 3)]
            want_done = one['window_end'] + stall
            if sc.get('stall_phase') and done:
                used = len([t for t in tr.rises(sm.i('tick'), one['t0'], done[0])
                            if one['t0'] <= t <= done[0]]) + 1
                if used != one['full'] + 1:
                    fails.append(Fail('DONE_BOUNDARIES', 'window %d on %s closed after %s accepted '
                                      'boundaries; its full window needs %d'
                                      % (n, sm.tag[idx], used, one['full'] + 1)))
                else:
                    done = [want_done]
            if w_abort(n):
                done = done or [want_done]
            if not done or done[0] != want_done:
                fails.append(Fail('DONE_EDGE', 'window %d on %s reaches DONE at %s, expected %s ns '
                                                 '(window end %s plus %s ns of clock stall)'
                                  % (n, sm.tag[idx], fmt_ns(done[0]) if done else 'never',
                                     fmt_ns(want_done), fmt_ns(one['window_end']), fmt_ns(stall))))
            hold_to = min(one['window_end'] + 2 * one['T'], one['t_to'])
            vals = tr.values_in(sm.o(idx, 'pam_sel'), one['t_bl'], hold_to)
            if vals != set([format_vec(one['pam_exp'], 3)]):
                fails.append(Fail('PAM_NOT_HELD', 'window %d on %s holds %s between release and the off '
                                                  'tail, expected %s'
                                  % (n, sm.tag[idx], sorted(vals), format_vec(one['pam_exp'], 3))))
            out.append('%s w%d=%s/%d' % (sm.tag[idx], n, got, one['exp']))
    return ' '.join(out)


def measure_nth_window(tr, sm, idx, cs, ce, fails, n=0, stable_codes=True, lat_idx=None):
    """read the n-th emission window of a control case entirely out of the trace

    Everything is measured from edges: the LATCH and blank-release events, the mode and code values
    carried at that LATCH, the tick and reference periods, t0 as the reference edge that consumes the
    first tick after the release, and this instance's own conducting segments. Nothing is taken from
    the testbench's own report.

    `lat_idx` is the index of the LATCH that committed this window when the case also contains refused
    LATCH requests: a refused request is still a rising edge on that bus, and reading the code at it
    would describe a window the controller never committed. It defaults to the window number.

    `stable_codes` is False for the scenario whose whole point is that a next code is loaded while
    the window runs: there the expectation comes from the code carried in at the LATCH instant, and
    the measured width proves the display copy did not follow the load bus.
    """
    blank_f = tr.falls(sm.i('blank'), cs, ce)
    latch_r = tr.rises(sm.i('latch_stb'), cs, ce)
    which = n if lat_idx is None else int(lat_idx)
    if len(blank_f) <= n or len(latch_r) <= which:
        fails.append(Fail('WINDOW_MISSING', 'window %d needs a LATCH and a blank release, the trace has '
                                           '%d latch / %d release' % (n, len(latch_r), len(blank_f))))
        return None
    t_lat, t_bl = latch_r[which], blank_f[n]
    stop_r = [t for t in tr.rises(sm.i('blank'), cs, ce) if t > t_bl]
    t_to = (stop_r[0] - 1) if stop_r else ce - 1
    ok_m, mode, raw = sig_bits(tr, sm.i('mode'), t_lat, 'is the mode at LATCH %d' % n, fails)
    if not ok_m:
        return None
    if mode not in FULL:
        fails.append(Fail('ILLEGAL_MODE', 'mode=%s at LATCH %d' % (raw, n)))
        return None
    full = FULL[mode]
    span = 'LATCH %d through the next blanking' % n
    if mode == MODE_PURE:
        if stable_codes:
            ok_c, code, _ = read_stable_code(tr, sm.o(idx, 'cfg_pure'), t_lat, t_to, span, fails)
        else:
            ok_c, code, _ = sig_bits(tr, sm.o(idx, 'cfg_pure'), t_lat,
                                     'the code carried in at LATCH %d' % n, fails)
        pam_exp = PAM_PURE_SYMBOL
    else:
        if stable_codes:
            ok_c, code, _ = read_stable_code(tr, sm.o(idx, 'cfg_hyb_time'), t_lat, t_to, span, fails)
            ok_p, pam_exp, _ = read_stable_code(tr, sm.o(idx, 'cfg_hyb_pam'), t_lat, t_to, span, fails)
        else:
            ok_c, code, _ = sig_bits(tr, sm.o(idx, 'cfg_hyb_time'), t_lat,
                                    'the time code carried in at LATCH %d' % n, fails)
            ok_p, pam_exp, _ = sig_bits(tr, sm.o(idx, 'cfg_hyb_pam'), t_lat,
                                        'the PAM code carried in at LATCH %d' % n, fails)
        if not ok_p:
            ok_c = False
    if not ok_c:
        return None
    exp = expected_intervals(mode, code)
    if exp is None:
        fails.append(Fail('CODE_OUT_OF_CONTRACT', 'mode=%s code=%d is not in the contract table'
                          % (MODE_NAME[mode], code)))
        return None
    tick_r = tr.rises(sm.i('tick'), cs, ce)
    after = [t for t in tick_r if t > t_bl and t <= t_to]
    if len(after) < 2:
        fails.append(Fail('NO_T0', 'window %d has no tick stream inside its own blanked range' % n))
        return None
    clk_all = tr.rises(sm.i('clk'), cs, ce)
    edge_after = [t for t in clk_all if t > after[0]]
    if not edge_after:
        fails.append(Fail('NO_T0', 'window %d has no reference edge that could consume the first tick'
                          % n))
        return None
    t0 = edge_after[0]
    dif = [after[k] - after[k - 1] for k in range(1, len(after))]
    T = min(dif)
    clk_rise = tr.rises(sm.i('clk'), cs, ce)
    clk_gaps = [(clk_rise[k - 1], clk_rise[k]) for k in range(1, len(clk_rise))
                if clk_rise[k] - clk_rise[k - 1] > T]
    for k in range(len(dif)):
        if dif[k] == T:
            continue
        gap_start, gap_end = after[k], after[k + 1]
        # the enable lives in the reference domain, so a longer gap is legitimate only while that
        # domain was frozen, and the freeze has to sit inside the gap rather than merely nearby
        stalled = [g for g in clk_gaps if gap_start <= g[0] < gap_end]
        if not stalled:
            fails.append(Fail('TICK_SPACING_UNSTABLE', 'window %d tick step %s ns at %s ns is not the '
                                                      'uniform %s ns and the clock kept running through '
                                                      'it' % (n, fmt_ns(dif[k]), fmt_ns(gap_start),
                                                             fmt_ns(T))))
            return None
    if after[0] - t_bl > T:
        fails.append(Fail('T0_LATE', 'window %d starts %s ns after the release, later than one tick'
                          % (n, fmt_ns(after[0] - t_bl))))
    segs = [seg for seg in tr.segments(sm.o(idx, 'data_en'), t0, t_to) if seg[1] > seg[0]]
    return {'n': n, 'mode': MODE_NAME[mode], 'code': code, 'exp': exp, 'full': full, 't_bl': t_bl,
            't_lat': t_lat, 't0': t0, 'T': T, 'window_end': t0 + full * T, 'segs': segs,
            't_to': t_to, 'pam_exp': pam_exp}


def _version_steps(tr, sm, cs, ce, fails, why):
    return _version_steps_count(tr, sm, cs, ce, fails, 1, why)


def _version_steps_count(tr, sm, cs, ce, fails, want, why):
    """cfg_version must step exactly `want` time(s) in this case, counted from its first LATCH"""
    lat = tr.rises(sm.i('latch_stb'), cs, ce)
    from_t = lat[0] if lat else cs
    out = []
    for idx in (0, 1):
        v0 = tr.value_at(sm.o(idx, 'cfg_version'), from_t - 1)
        v1 = tr.value_at(sm.o(idx, 'cfg_version'), ce - 1)
        ok0, a, _ = sig_bits(tr, sm.o(idx, 'cfg_version'), from_t - 1, 'is cfg_version before the LATCH',
                             [])
        ok1, b, _ = sig_bits(tr, sm.o(idx, 'cfg_version'), ce - 1, 'is cfg_version at the case end', [])
        steps = [t for t, v in tr.edges(sm.o(idx, 'cfg_version')) if from_t <= t <= ce - 1]
        if not (ok0 and ok1):
            fails.append(Fail('UNKNOWN_VALUE', '%s.cfg_version is unknown inside this case'
                              % sm.tag[idx]))
        elif b - a != want or len(steps) != want:
            fails.append(Fail('VERSION_STEPPED', '%s.cfg_version went %d -> %d over %d edge(s); it may '
                                                 'step %d time(s): %s'
                              % (sm.tag[idx], a, b, len(steps), want, why)))
        out.append('%s=%d->%d/%d' % (sm.tag[idx], a if ok0 else -1, b if ok1 else -1, len(steps)))
    return ' '.join(out)


def _stall_total(tr, sm, cs, ce, one):
    """extra wall time the window spent frozen, measured from gaps in the reference clock itself"""
    rises = tr.rises(sm.i('clk'), cs, ce)
    total = 0
    for k in range(1, len(rises)):
        gap = rises[k] - rises[k - 1]
        if gap > one['T'] and rises[k - 1] < one['window_end']:
            total += gap - one['T']
    return total


def _widths_ticks(segs, T):
    return [int((b - a) // T) for a, b in segs if T and b > a]


def ctl_window_ok(tr, sm, cs, ce, sc, fails):
    measured = attest_windows(tr, sm, cs, ce, sc, fails,
                              stable_codes=sc.get('stable_codes', True))
    if not measured:
        w = measure_nth_window(tr, sm, 0, cs, ce, fails, int(sc.get('window', 0)),
                               stable_codes=sc.get('stable_codes', True))
        measured = [w] if w else []
    return judge_windows(tr, sm, cs, ce, sc, fails, measured)


def _own_t0(tr, sm, idx, cs, t_from, t_to):
    """this instance's own t0: the reference edge that consumes the first tick IT accepted

    obs_tick is the controller's audit of an accepted tick, and the tick enable is raised ahead of
    the edge that consumes it, so the first clock rise after the first accepted-tick rise is the edge
    this channel actually acted on. Deriving t0 from the shared stimulus instead would compare two
    numbers computed from the same inputs and could never see a channel whose output is late.
    """
    rises = tr.rises(sm.o(idx, 'obs_tick'), t_from, t_to)
    if not rises:
        return None, None
    edges = [t for t in tr.rises(sm.i('clk'), rises[0], t_to)]
    return rises[0], (edges[0] if edges else None)


def ctl_mixed_codes(tr, sm, cs, ce, sc, fails):
    """different codes per channel: each start and completion edge is measured on that channel"""
    da = sc.get('windows', [])
    db = sc.get('windows_b', da)
    a = measure_nth_window(tr, sm, 0, cs, ce, fails, 0)
    b = measure_nth_window(tr, sm, 1, cs, ce, fails, 0)
    if not a or not b:
        return 'unmeasured'
    for w, decl, tag in ((a, da, sm.tag[0]), (b, db, sm.tag[1])):
        if decl and [w['mode'], w['code'], w['pam_exp']] != list(decl[0])[:3]:
            fails.append(Fail('STIMULUS_MISMATCH', '%s window reads %s code=%s pam=%s, the vector '
                               'declared %s' % (tag, w['mode'], w['code'], w['pam_exp'], decl[0])))
    if (a['code'], a['pam_exp']) == (b['code'], b['pam_exp']):
        fails.append(Fail('MIXED_NOT_INDEPENDENT', 'both channels were handed the same code and PAM '
                                                   'value, so independence was not exercised'))
    out = []
    for w, tag in ((a, sm.tag[0]), (b, sm.tag[1])):
        idx = 0 if tag == sm.tag[0] else 1
        own_rise, own_t0 = _own_t0(tr, sm, idx, cs, w['t_bl'], w['t_to'])
        if own_t0 is None:
            fails.append(Fail('NO_T0', '%s never shows an accepted tick whose consuming reference edge '
                                       'can be located' % tag))
            continue
        if own_t0 != w['t0']:
            fails.append(Fail('MIXED_EDGES', '%s consumes its first tick at %s ns, the shared tick '
                                             'stream puts that edge at %s ns'
                             % (tag, fmt_ns(own_t0), fmt_ns(w['t0']))))
        got = _widths_ticks(w['segs'], w['T'])
        want = [w['exp']] if w['exp'] else []
        if got != want:
            fails.append(Fail('MIXED_WIDTH', '%s conducted %s ticks, its own code asks %s'
                              % (tag, got, want)))
        if w['exp']:
            # a non-zero code must open exactly at this channel's own t0 and close exactly exp periods
            # later; a whole-tick rounding of the width would hide a start that is late by less than
            # one tick, so the edges themselves are compared in picoseconds
            if not w['segs'] or w['segs'][0][0] != own_t0:
                fails.append(Fail('ON_START', '%s.data_en opens at %s, this channel\'s own t0 is %s ns'
                                  % (tag, fmt_ns(w['segs'][0][0]) if w['segs'] else 'never',
                                     fmt_ns(own_t0))))
            off = w['segs'][-1][1] if w['segs'] else None
            want_off = own_t0 + w['exp'] * w['T']
            if off != want_off:
                fails.append(Fail('ON_WIDTH', '%s closes at %s, the contract endpoint for %d intervals '
                                              'of %s ns is %s ns'
                                  % (tag, fmt_ns(off), w['exp'], fmt_ns(w['T']), fmt_ns(want_off))))
            span = sum(x[1] - x[0] for x in w['segs'])
            if span != w['exp'] * w['T']:
                fails.append(Fail('ON_SPAN', '%s conducted %s ps in total across %d segment(s); %d '
                                                 'intervals of %s ps is %s ps'
                                  % (tag, span, len(w['segs']), w['exp'], w['T'], w['exp'] * w['T'])))
        elif w['segs']:
            fails.append(Fail('BLACK_CONDUCTS', '%s shows code 0 yet data_en conducted %s'
                              % (tag, w['segs'])))
        want_done = own_t0 + w['full'] * w['T']
        done = [t for t, v in tr.edges(sm.o(idx, 'win_state'))
                if own_t0 <= t <= own_t0 + (w['full'] + 4) * w['T'] and v == format_vec(3, 3)]
        if not done or done[0] != want_done:
            fails.append(Fail('DONE_EDGE', '%s completes at %s, its own window end is %s ns'
                              % (tag, fmt_ns(done[0]) if done else 'never', fmt_ns(want_done))))
        out.append('%s t0=%s on=%s done=%s %s=%s/%d'
                   % (tag, fmt_ns(own_t0),
                      fmt_ns(w['segs'][0][0]) if w['segs'] else 'dark',
                      fmt_ns(done[0]) if done else 'none', tag, got, w['exp']))
    return ' '.join(out)


def ctl_pam_toggle(tr, sm, cs, ce, sc, fails):
    return ctl_window_ok(tr, sm, cs, ce, sc, fails)


def ctl_display_frozen(tr, sm, cs, ce, sc, fails):
    """the running window keeps its own code while a next code is loaded, and PAM does not move"""
    sc = dict(sc)
    sc['stable_codes'] = False
    measured = ctl_window_ok(tr, sm, cs, ce, sc, fails)
    w = measure_nth_window(tr, sm, 0, cs, ce, [], 0, stable_codes=False)
    if not w:
        return measured + ' | window unreadable'
    loads = sorted(set([t for nm in ('cfg_pure', 'cfg_hyb_time', 'cfg_hyb_pam')
                        for t, _v in tr.edges(sm.o(0, nm))
                        if w['t0'] < t < min(w['window_end'], w['t_to'])]))
    if not loads:
        fails.append(Fail('STIMULUS_UNATTESTED', 'no next-code load happened inside the running window, '
                                                 'so the scenario proved nothing'))
    for t in loads:
        for idx in (0, 1):
            before = tr.value_at(sm.o(idx, 'pam_sel'), t - 1)
            after = tr.value_at(sm.o(idx, 'pam_sel'), min(t + 29000, w['t_to']))
            if before != after:
                fails.append(Fail('DISPLAY_MOVED', '%s.pam_sel went %s -> %s around the load at %s ns'
                                  % (sm.tag[idx], before, after, fmt_ns(t))))
    return '%s | next-code loads at %s ns' % (measured, ','.join(fmt_ns(t) for t in loads) or 'none')


def _declared_window(sc):
    """the grey code the scenario says it is interrupting: (conducting intervals, full window)"""
    w = sc.get('windows') or []
    if not w:
        raise Refuse('an asynchronous shut-off scenario has to declare the window it interrupts')
    mode_name, code = w[0][0], int(w[0][1])
    mode = MODE_PURE if mode_name == 'PURE' else MODE_HYBRID
    exp = expected_intervals(mode, code)
    if exp is None:
        raise Refuse('scenario declares an illegal window code %s %d' % (mode_name, code))
    return exp, (256 if mode == MODE_PURE else 64)


def attest_phase(tr, sm, cs, ce, t, sc, exp, full, fails):
    """prove from the trace that the assertion really happened in the phase the name claims"""
    phase = sc.get('phase')
    if not phase:
        return None
    st = tr.value_at(sm.o(0, 'win_state'), t - 1)
    lit = tr.value_at(sm.o(0, 'data_en'), t - 1)
    n = len(tr.rises(sm.o(0, 'obs_tick'), cs, t - 1))
    rules = {
        'mid_window': (st == '010' and lit == '1' and 1 <= n <= exp,
                       'the window running and conducting, so win_state=010, data_en=1 and 1..%d '
                       'accepted ticks before the assertion' % exp),
        'short_pulse_middle': (st == '010' and lit == '1' and exp == 1 and n == 1,
                               'the one-interval pulse of code 1 still lit, so exactly one accepted '
                               'tick before the assertion'),
        'near_window_end': (st == '010' and n == full,
                            'the last interval before the endpoint, so %d accepted ticks with the '
                            'window still running' % full),
        'after_window_end': (st == '011' and lit == '0' and n >= full + 1,
                             'the completed window, so %d accepted ticks and win_state=011'
                             % (full + 1)),
    }
    if phase not in rules:
        raise Refuse('unknown declared phase %r' % phase)
    ok, why = rules[phase]
    if not ok:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the assertion at %s ns is not in the declared phase '
                                                 '%s: this needs %s, the trace shows win_state=%s '
                                                 'data_en=%s accepted_ticks=%d for a code with %d '
                                                 'conducting intervals'
                          % (fmt_ns(t), phase, why, st, lit, n, exp)))
    aborted = [x for x, v in tr.edges(sm.o(0, 'win_state')) if t <= x <= ce and v == '100']
    if phase == 'after_window_end':
        if aborted:
            fails.append(Fail('STIMULUS_UNATTESTED', 'a shut-off after the window endpoint must find '
                                                    'nothing to abort, but %s entered ABORT at %s ns'
                              % (sm.tag[0], fmt_ns(aborted[0]))))
    elif not aborted:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the %s assertion at %s ns never put %s into ABORT, so '
                                                 'it did not interrupt a window'
                          % ('fault' if sc.get('p2') == 1 else 'blank', fmt_ns(t), sm.tag[0])))
    return phase, n, st, lit, (fmt_ns(aborted[0]) if aborted else 'none')


def ctl_async_off(tr, sm, cs, ce, sc, fails):
    """the assertion must be off the clock edge, of the declared width, in the declared phase"""
    clk_rises = set(tr.rises(sm.i('clk'), cs, ce))
    tick_rises = set(tr.rises(sm.i('tick'), cs, ce))
    exp, full = _declared_window(sc)
    sigs = sc.get('asserts')
    if sigs is None:
        sigs = ['fault'] if sc.get('p2') == 1 else ['blank']
    seen = []
    for nm in sigs:
        for j, t in enumerate(tr.rises(sm.i(nm), cs + 1, ce)):
            width = None
            falls = [x for x in tr.falls(sm.i(nm), t, ce) if x > t]
            if falls:
                width = falls[0] - t
            if t in clk_rises or t in tick_rises:
                fails.append(Fail('STIMULUS_UNATTESTED', '%s is asserted exactly on a reference tick at '
                                                         '%s ns, so this is not an off-edge test'
                                  % (nm, fmt_ns(t))))
            if sc.get('pulse_width_ns') and j == 0 and width not in (None,
                                                                     sc['pulse_width_ns'] * PS):
                fails.append(Fail('STIMULUS_UNATTESTED', '%s pulse is %s ns wide, the scenario declared '
                                                         '%d ns' % (nm, fmt_ns(width),
                                                                    sc['pulse_width_ns'])))
            for idx in (0, 1):
                v = tr.value_at(sm.o(idx, 'data_en'), t)
                if v != '0':
                    fails.append(Fail('ASYNC_OFF', '%s asserted at %s ns but %s.data_en is %s at that '
                                                   'same time' % (nm, fmt_ns(t), sm.tag[idx], v)))
            # only the first assertion is the shut-off under test; the trailing one is the case-end
            # blanking that closes the segment
            att = attest_phase(tr, sm, cs, ce, t, sc, exp, full, fails) if j == 0 else None
            seen.append('%s@%s/%sns%s' % (nm, fmt_ns(t), fmt_ns(width) if width else '?',
                                          '(case-end blanking)' if not att and j else
                                          ('' if not att else '(%s,ticks=%d,abort=%s)'
                                           % (att[0], att[1], att[4]))))
    if not seen:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the scenario never asserted blank or fault'))
    return 'assertions=%s' % (','.join(seen) or 'none')


def ctl_no_resume(tr, sm, cs, ce, sc, fails):
    key = sc.get('abort', 'blank_rise')
    if key == 'reset_fall':
        events = tr.falls(sm.i('reset_n'), cs, ce)
    elif key.endswith('_rise'):
        events = tr.rises(sm.i(key[:-5]), cs, ce)
    else:
        raise Refuse('unknown abort event %r' % key)
    events = [t for t in events if t > cs]
    if not events:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the scenario never produced the %s event' % key))
        return 'none'
    t_abort = events[0]
    st = tr.value_at(sm.o(0, 'win_state'), t_abort - 1)
    if key != 'reset_fall' and st != '010':
        fails.append(Fail('STIMULUS_UNATTESTED', 'the %s at %s ns does not interrupt a running window: '
                                                 'win_state before it was %s' % (key, fmt_ns(t_abort), st)))
    if not tr.rises(sm.o(0, 'data_en'), cs, t_abort - 1):
        fails.append(Fail('STIMULUS_UNATTESTED', 'nothing conducted before the %s at %s ns, so refusing '
                                                 'to resume it would prove nothing'
                         % (key, fmt_ns(t_abort))))
    out = []
    for idx in (0, 1):
        late = tr.rises(sm.o(idx, 'data_en'), t_abort + 1, ce)
        if late:
            fails.append(Fail('AUTO_RESUME', '%s.data_en re-opened at %s ns after the %s at %s ns, with '
                                             'no new LATCH or start in between'
                              % (sm.tag[idx], fmt_ns(late[0]), key, fmt_ns(t_abort))))
        ok_s, val, _raw = sig_bits(tr, sm.o(idx, 'win_state'), ce - 1,
                                   'is win_state at the case end', fails)
        allowed = (ST[3], ST[4]) + ((ST[0],) if key == 'reset_fall' else ())
        if ok_s and ST.get(val) not in allowed:
            fails.append(Fail('NO_ABORT_RECORDED', '%s.win_state is %s at the case end after the %s at '
                                                   '%s ns' % (sm.tag[idx], ST.get(val), key,
                                                               fmt_ns(t_abort))))
        out.append('%s:dark_from=%s' % (sm.tag[idx], fmt_ns(t_abort)))
    return ' '.join(out)


def ctl_start_once(tr, sm, cs, ce, sc, fails):
    rises = tr.rises(sm.i('pwm_start'), cs, ce)
    if len(rises) != 1:
        fails.append(Fail('START_PULSES', 'the scenario presents exactly one PWM_START rise, saw %d'
                          % len(rises)))
    return 'start_rises=%d %s' % (len(rises), ctl_window_ok(tr, sm, cs, ce, sc, fails))


def ctl_ticks_in_blank(tr, sm, cs, ce, sc, fails):
    bad = []
    for idx in (0, 1):
        for t in tr.rises(sm.o(idx, 'obs_tick'), cs, ce):
            if tr.value_at(sm.i('blank'), t) == '1':
                bad.append('%s at %s ns' % (sm.tag[idx], fmt_ns(t)))
    if bad:
        fails.append(Fail('TICK_CONSUMED_IN_BLANK', 'obs_tick accepted a tick while blanked: %s'
                          % ', '.join(bad[:3])))
    before = []
    lat = tr.rises(sm.i('latch_stb'), cs, ce)
    for idx in (0, 1):
        for t in tr.rises(sm.o(idx, 'obs_tick'), cs, ce):
            if lat and t < lat[0]:
                before.append('%s at %s ns' % (sm.tag[idx], fmt_ns(t)))
    if before:
        fails.append(Fail('TICK_CONSUMED_BEFORE_START', 'a tick was accepted before the first LATCH: %s'
                          % ', '.join(before[:3])))
    return 'accepted_in_blank=%s | %s' % (bad or 'none', ctl_window_ok(tr, sm, cs, ce, sc, fails))


def ctl_refused_dark(tr, sm, cs, ce, sc, fails):
    hits = []
    for idx in (0, 1):
        who = '%s.proto_err' % sm.tag[idx]
        hits += bits_set(tr, sm.o(idx, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails, who)
    want = sc.get('mode_values', [])
    if want:
        vals = sorted(set(int(v, 2) for _t, v in tr.edges(sm.i('mode')) if v
                          and not any(c in tv.XZ for c in v)))
        missing = [m for m in want if m not in vals]
        if missing:
            fails.append(Fail('STIMULUS_UNATTESTED', 'the mode bus never shows %s (saw %s)'
                              % (missing, vals)))
    dark = no_light(tr, sm, cs, ce, fails, who=' although the request was refused')
    for idx in (0, 1):
        runs = tr.values_in(sm.o(idx, 'win_state'), cs, ce)
        if set([format_vec(2, 3)]) & runs:
            fails.append(Fail('RAN_AFTER_REFUSAL', '%s.win_state reached RUNNING although the request was '
                                             'refused' % sm.tag[idx]))
    return 'proto_err %s dark %s' % (' '.join(hits), dark)


def ctl_refused_then_window(tr, sm, cs, ce, sc, fails):
    sc = dict(sc)
    sc.setdefault('stable_codes', False)
    hits = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
                    '%s.proto_err' % sm.tag[0])
    hits += bits_set(tr, sm.o(1, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
                     '%s.proto_err' % sm.tag[1])
    return 'refusal %s | %s' % (' '.join(hits), ctl_window_ok(tr, sm, cs, ce, sc, fails))


def ctl_dark_only(tr, sm, cs, ce, sc, fails):
    out = no_light(tr, sm, cs, ce, fails)
    want = sc.get('reset_pulses')
    if want:
        got = len(tr.falls(sm.i('reset_n'), cs, ce - 1))
        if got != int(want):
            fails.append(Fail('STIMULUS_UNATTESTED', 'the scenario declares %s reset pulses, the trace '
                                                     'shows %d reset falls' % (want, got)))
        else:
            out += ' resets=%d' % got
    for idx in (0, 1):
        runs = tr.values_in(sm.o(idx, 'win_state'), cs, ce)
        if set([format_vec(2, 3)]) & runs:
            fails.append(Fail('RAN_WITHOUT_CONFIG', '%s.win_state shows RUNNING with nothing displayed'
                              % sm.tag[idx]))
        if any(any(c in tv.XZ for c in v) for v in runs):
            fails.append(Fail('UNKNOWN_STATE', '%s.win_state keeps an unknown value in this case'
                              % sm.tag[idx]))
    return out


def ctl_config_freshness(tr, sm, cs, ce, sc, fails):
    """one load may feed exactly one LATCH: the replay is refused and the version does not step"""
    latches = tr.rises(sm.i('latch_stb'), cs, ce)
    loads = tr.rises(sm.i('cfg_valid'), cs, ce)
    if len(latches) != 2:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the scenario needs two LATCH requests behind one load, '
                                                 'saw %d LATCH and %d load' % (len(latches), len(loads))))
    if len(loads) != 1:
        fails.append(Fail('STIMULUS_UNATTESTED', 'expected exactly one load transaction, saw %d'
                          % len(loads)))
    hits = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
                    '%s.proto_err' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails, '%s.proto_err' % sm.tag[1])
    out = _version_steps(tr, sm, cs, ce, fails, 'one load may only step it once')
    return 'refusal %s version %s' % (' '.join(hits), ' '.join(out))


def ctl_abort_reauthorise(tr, sm, cs, ce, sc, fails):
    """the withdrawn condition and a bare start must not re-light; only a full sequence may"""
    t_bl = tr.falls(sm.i('blank'), cs, ce)
    if len(t_bl) < 2:
        fails.append(Fail('STIMULUS_UNATTESTED', 'this scenario needs a second blank release after the '
                                                 'abort, saw %d' % len(t_bl)))
        return 'none'
    aborts = [t for t in tr.rises(sm.i('blank'), cs + 1, ce)]
    if not aborts:
        fails.append(Fail('STIMULUS_UNATTESTED', 'no blank assertion aborted the first window'))
        return 'none'
    t_abort = aborts[0]
    if tr.value_at(sm.o(0, 'win_state'), t_abort - 1) != '010' or \
            not tr.rises(sm.o(0, 'data_en'), cs, t_abort - 1):
        fails.append(Fail('STIMULUS_UNATTESTED', 'the blank rise at %s ns did not abort a lit, running '
                                                 'window, so the recovery refusal would prove nothing'
                         % fmt_ns(t_abort)))
    hits = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
                    '%s.proto_err' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
             '%s.proto_err' % sm.tag[1])
    dark = no_light(tr, sm, cs, ce, fails, t_from=t_abort + 1, who=' after the abort')
    vers = _version_steps(tr, sm, cs, ce, fails, 'the aborted window must not re-commit')
    state = [ST.get(int(tr.value_at(sm.o(i, 'win_state'), ce - 1), 2), '?') for i in (0, 1)]
    return 'abort@%s refusal %s dark %s version %s end_state %s' % (
        fmt_ns(t_abort), ' '.join(hits), dark, ' '.join(vers), '/'.join(state))


def ctl_mode_bypass(tr, sm, cs, ce, sc, fails):
    """a mode refused in the unsafe phase must not arrive through a LATCH"""
    hits = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
                    '%s.proto_err' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
             '%s.proto_err' % sm.tag[1])
    mode_r = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, E_MODE_WHILE_RUNNING, fails,
                      '%s.proto_err (unsafe mode change)' % sm.tag[0])
    vals = sorted(set(int(v, 2) for _t, v in tr.edges(sm.i('mode')) if v
                      and not any(c in tv.XZ for c in v)))
    if [0, 1] != [m for m in vals if m in (0, 1)]:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the mode bus must show Pure then Hybrid, saw %s' % vals))
    lat = tr.rises(sm.i('latch_stb'), cs, ce)
    from_t = lat[0] if lat else cs
    pam = sorted(set(v for t, v in tr.edges(sm.o(0, 'pam_sel'))
                     if from_t <= t <= ce - 1 and not any(c in tv.XZ for c in v)))
    if pam != [format_vec(7, 3)]:
        fails.append(Fail('MODE_ADOPTED', '%s.pam_sel shows %s from its own LATCH on: the refused Hybrid '
                                          'code was adopted' % (sm.tag[0], pam)))
    _version_steps(tr, sm, cs, ce, fails, 'the bypassing LATCH must not commit')
    # refusing a mode is not refusing the display: the window that the accepted LATCH committed must
    # still run with its own Pure code, and it is that judgement which proves nothing was adopted
    judged = ctl_window_ok(tr, sm, cs, ce, dict(sc, stable_codes=False), fails)
    return 'refusal %s/%s pam %s | %s' % (' '.join(hits), ' '.join(mode_r), pam, judged)


def ctl_recover(tr, sm, cs, ce, sc, fails):
    measured = ctl_window_ok(tr, sm, cs, ce, sc, fails)
    aborts = tr.rises(sm.i('blank'), cs + 1, ce)
    if not aborts:
        fails.append(Fail('STIMULUS_UNATTESTED', 'nothing aborted the first window, so recovery was not '
                                                 'exercised'))
    return 'abort@%s | %s' % (fmt_ns(aborts[0]) if aborts else 'none', measured)


def _pending_before_abort(tr, sm, cs, ce, sc, fails):
    """prove the trace carried an unconsumed load transaction into the abort it declares"""
    key = 'fault' if sc.get('p2') == 1 else 'blank'
    aborts = tr.rises(sm.i(key), cs + 1, ce)
    if not aborts:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the scenario wants a pending load sitting in front of '
                                                 'an abort, but %s is never asserted' % key))
        return None, []
    t_abort = aborts[0]
    lat = tr.rises(sm.i('latch_stb'), cs, ce)
    if not lat:
        fails.append(Fail('STIMULUS_UNATTESTED', 'no LATCH at all in this case'))
        return None, []
    loads = [t for t in tr.rises(sm.i('cfg_valid'), lat[0], t_abort - 1)]
    if not loads:
        fails.append(Fail('STIMULUS_UNATTESTED', 'no load transaction was raised between the first LATCH '
                                                 'and the abort at %s ns, so there was no pending config '
                                                 'to revoke' % fmt_ns(t_abort)))
    if tr.value_at(sm.o(0, 'win_state'), t_abort - 1) != '010' or \
            not tr.rises(sm.o(0, 'data_en'), cs, t_abort - 1):
        fails.append(Fail('STIMULUS_UNATTESTED', 'the abort at %s ns did not interrupt a lit, running '
                                                 'window, so revoking a pending load would prove nothing'
                         % fmt_ns(t_abort)))
    return t_abort, loads


def ctl_abort_pending(tr, sm, cs, ce, sc, fails):
    """an abort revokes the pending load too: the post-abort LATCH and START must stay dark"""
    t_abort, loads = _pending_before_abort(tr, sm, cs, ce, sc, fails)
    if t_abort is None:
        return 'none'
    stale = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, E_STALE_CONFIG, fails,
                     '%s.proto_err (stale)' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, E_STALE_CONFIG, fails,
             '%s.proto_err (stale)' % sm.tag[1])
    refused = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, E_START_REJECTED, fails,
                       '%s.proto_err (start)' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, E_START_REJECTED, fails,
             '%s.proto_err (start)' % sm.tag[1])
    dark = no_light(tr, sm, cs, ce, fails, t_from=t_abort + 1,
                    who=' after an abort that revoked a pending load')
    vers = _version_steps_count(tr, sm, cs, ce, fails, 1,
                                'only the pre-abort LATCH may commit; the revoked pending load may not')
    state = [ST.get(int(tr.value_at(sm.o(i, 'win_state'), ce - 1), 2), '?') for i in (0, 1)]
    return 'pending@%s abort@%s stale %s start %s dark %s version %s end %s' % (
        fmt_ns(loads[0]) if loads else 'none', fmt_ns(t_abort), ' '.join(stale), ' '.join(refused),
        dark, vers, '/'.join(state))


def ctl_abort_pending_recover(tr, sm, cs, ce, sc, fails):
    """after the revocation, a load that really arrives later restores the display"""
    t_abort, _loads = _pending_before_abort(tr, sm, cs, ce, sc, fails)
    if t_abort is None:
        return 'none'
    late = [t for t in tr.rises(sm.i('cfg_valid'), t_abort + 1, ce)]
    if not late:
        fails.append(Fail('STIMULUS_UNATTESTED', 'recovery was claimed but no load transaction arrives '
                                                 'after the abort at %s ns' % fmt_ns(t_abort)))
    dark_before = no_light(tr, sm, cs, ce, fails, t_from=t_abort + 1, t_to=late[0] if late else ce - 1,
                           who=' between the abort and the first post-abort load')
    judged = ctl_window_ok(tr, sm, cs, ce, dict(sc, stable_codes=False), fails)
    vers = _version_steps_count(tr, sm, cs, ce, fails, 2,
                                'one commit before the abort and one commit after the new load')
    return 'abort@%s post_load@%s dark %s | %s | version %s' % (
        fmt_ns(t_abort), fmt_ns(late[0]) if late else 'none', dark_before, judged, vers)


def ctl_next_window(tr, sm, cs, ce, sc, fails):
    """a next load prepared inside window A is committed only after A ends, used by B, once"""
    a = measure_nth_window(tr, sm, 0, cs, ce, [], 0, stable_codes=False)
    if not a:
        return 'window A unreadable'
    loads = [t for t in tr.rises(sm.i('cfg_valid'), cs, ce) if a['t0'] < t < a['window_end']]
    if not loads:
        fails.append(Fail('STIMULUS_UNATTESTED', 'no load transaction was presented while window A was '
                                                 'running, so the next/display copies were not exercised'))
    for t in loads:
        for idx in (0, 1):
            hold = min(t + a['T'], a['window_end'])
            if tr.value_at(sm.o(idx, 'pam_sel'), t - 1) != tr.value_at(sm.o(idx, 'pam_sel'), hold):
                fails.append(Fail('DISPLAY_MOVED', '%s.pam_sel moved around the next load at %s ns while '
                                                   'A was still conducting' % (sm.tag[idx], fmt_ns(t))))
    judged = ctl_window_ok(tr, sm, cs, ce, dict(sc, stable_codes=False), fails)
    stale = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, E_STALE_CONFIG, fails,
                     '%s.proto_err (replayed LATCH)' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, E_STALE_CONFIG, fails,
             '%s.proto_err (replayed LATCH)' % sm.tag[1])
    vers = _version_steps_count(tr, sm, cs, ce, fails, 2,
                                'A commits once, B commits once, the replay behind the consumed load '
                                'may not commit')
    return 'next_load@%s | %s | replay refused %s | version %s' % (
        ','.join(fmt_ns(t) for t in loads) or 'none', judged, ' '.join(stale), vers)


def ctl_clock_stall(tr, sm, cs, ce, sc, fails):
    """find the frozen stretch in the trace, then check nothing moved in it, in the declared phase"""
    measured = ctl_window_ok(tr, sm, cs, ce, sc, fails)
    gap_min = int(sc.get('gap_min_ns', 60)) * PS
    rises = tr.rises(sm.i('clk'), cs, ce)
    if len(rises) < 2:
        fails.append(Fail('NO_CLOCK', 'the reference clock never toggles in this case'))
        return 'no clock'
    gaps = [(rises[k - 1], rises[k]) for k in range(1, len(rises))
            if rises[k] - rises[k - 1] >= gap_min]
    if not gaps:
        fails.append(Fail('STIMULUS_UNATTESTED', 'the reference domain never stalled by at least %d ns'
                          % (gap_min // PS)))
        return '%s | no stall found' % measured
    w = measure_nth_window(tr, sm, 0, cs, ce, [], 0)
    out = []
    for a, b in gaps:
        inside_tick = [t for t in tr.rises(sm.i('tick'), a + 1, b - 1)]
        if inside_tick:
            fails.append(Fail('TICK_IN_STALL', 'a tick was presented at %s ns while the domain was '
                                               'frozen' % fmt_ns(inside_tick[0])))
        for idx in (0, 1):
            before = tr.value_at(sm.o(idx, 'data_en'), a)
            after = tr.value_at(sm.o(idx, 'data_en'), b)
            if after != before:
                fails.append(Fail('STATE_MOVED_IN_STALL', '%s.data_en went %s -> %s across the stall '
                                  '(%s, %s) ns' % (sm.tag[idx], before, after, fmt_ns(a), fmt_ns(b))))
            st_a = tr.value_at(sm.o(idx, 'win_state'), a)
            st_b = tr.value_at(sm.o(idx, 'win_state'), b)
            if st_a != st_b:
                fails.append(Fail('STATE_MOVED_IN_STALL', '%s.win_state went %s -> %s across the stall'
                                  % (sm.tag[idx], st_a, st_b)))
        phase = 'unknown'
        if w:
            if a < w['t0']:
                phase = 'before_t0'
            elif a < w['window_end']:
                phase = 'running'
            else:
                phase = 'done'
        if sc.get('stall_phase') and phase != sc['stall_phase']:
            fails.append(Fail('STIMULUS_UNATTESTED', 'the stall happened in phase %s, the scenario '
                                                     'declares %s' % (phase, sc['stall_phase'])))
        out.append('(%s,%s)%s' % (fmt_ns(a), fmt_ns(b), phase))
    return '%s | stalls=%s' % (measured, ' '.join(out))


def ctl_start_latch_same_edge(tr, sm, cs, ce, sc, fails):
    """one edge carrying both requests: the LATCH commits, the start is refused, nothing lights"""
    lr = tr.rises(sm.i('latch_stb'), cs, ce)
    sr = tr.rises(sm.i('pwm_start'), cs, ce)
    if len(lr) != 1 or len(sr) != 1 or lr[0] != sr[0]:
        fails.append(Fail('STIMULUS_UNATTESTED', 'LATCH and START must rise on the same sampling edge '
                                                 '(%s vs %s)' % ([fmt_ns(t) for t in lr],
                                                                 [fmt_ns(t) for t in sr])))
        return 'none'
    hits = bits_set(tr, sm.o(0, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
                    '%s.proto_err' % sm.tag[0])
    bits_set(tr, sm.o(1, 'proto_err'), cs, ce, int(sc['proto_err_bit']), fails,
             '%s.proto_err' % sm.tag[1])
    dark = no_light(tr, sm, cs, ce, fails, who=' although the start was refused')
    vers = _version_steps(tr, sm, cs, ce, fails, 'the accepted LATCH must be the only step')
    return 'same_edge=%s ns refusal %s version %s dark %s' % (fmt_ns(lr[0]), ' '.join(hits),
                                                              ' '.join(vers), dark)


CONTROL_HANDLERS = {
    'async_off_between_edges': ctl_async_off,
    'no_auto_resume': ctl_no_resume,
    'start_held_40ns_once': ctl_start_once,
    'tick_in_blank_consumed': ctl_ticks_in_blank,
    'window_ok': ctl_window_ok,
    'mixed_codes': ctl_mixed_codes,
    'pam_toggle': ctl_pam_toggle,
    'display_frozen': ctl_display_frozen,
    'refused_dark': ctl_refused_dark,
    'refused_then_window': ctl_refused_then_window,
    'dark_only': ctl_dark_only,
    'clock_stall': ctl_clock_stall,
    'config_freshness': ctl_config_freshness,
    'abort_reauthorise': ctl_abort_reauthorise,
    'mode_bypass': ctl_mode_bypass,
    'mode_switch_safe': ctl_window_ok,
    'recover_full_sequence': ctl_recover,
    'next_window_commit': ctl_next_window,
    'abort_pending': ctl_abort_pending,
    'abort_pending_recover': ctl_abort_pending_recover,
    'code_edges': ctl_window_ok,
    'start_latch_same_edge': ctl_start_latch_same_edge,
}


def check_control_trace(path, scenarios, run_id=''):
    """judge every named control scenario against its case segment, then report uncovered cases"""
    tr = tv.Trace(path)
    sm = SigMap(tr)
    seg = dict((cid, (cs, ce)) for cid, cs, ce in cases(tr, sm))
    rows = []
    used = set()
    for sc in scenarios:
        cid = int(sc['case_id'])
        if cid not in seg:
            rows.append({'case_id': cid, 'scenario': sc['name'], 'kind': sc['kind'],
                         'verdict': 'NOT_RUN', 'observed': 'absent',
                         'requirement': CONTROL_REQUIREMENT.get(sc['kind'], ''),
                         'expect': sc.get('expect', 'pass'), 'tick_ns': sc.get('tick_ns', ''),
                         'mode': sc.get('mode', ''), 'profile': sc.get('profile', ''),
                         'stimulus': _stim_summary(sc),
                         'failures': 'the trace contains no case %d: this scenario was not executed'
                                      % cid, 'vcd': os.path.basename(path), 'run_id': run_id})
            continue
        used.add(cid)
        cs, ce = seg[cid]
        fails = []
        try:
            observed = CONTROL_HANDLERS[sc['kind']](tr, sm, cs, ce, sc, fails)
        except Refuse as exc:
            fails.append(Fail('SCENARIO_REFUSED', str(exc)))
            observed = 'refused'
        rows.append({'case_id': cid, 'scenario': sc['name'], 'kind': sc['kind'],
                     'verdict': 'PASS' if not fails else 'FAIL', 'observed': observed,
                     'requirement': CONTROL_REQUIREMENT.get(sc['kind'], ''),
                     'expect': sc.get('expect', 'pass'),
                     'tick_ns': sc.get('tick_ns', ''), 'mode': sc.get('mode', ''),
                     'profile': sc.get('profile', ''), 'stimulus': _stim_summary(sc),
                     'failures': ' ; '.join(str(f) for f in fails)[:500] if fails else 'none',
                     'vcd': os.path.basename(path), 'run_id': run_id})
    for cid in sorted(set(seg) - used):
        rows.append({'case_id': cid, 'scenario': 'UNCOVERED_CASE', 'kind': '',
                     'verdict': 'FAIL', 'observed': 'no scenario',
                     'requirement': 'every case in a control trace has to be named by the vector file',
                     'expect': 'pass', 'tick_ns': '', 'mode': '', 'profile': '', 'stimulus': '',
                     'failures': 'case %d is present in the trace but no scenario judges it' % cid,
                     'vcd': os.path.basename(path), 'run_id': run_id})
    return rows, tr


def _stim_summary(sc):
    """the declared stimulus, written out so a reviewer can compare it with the observed column"""
    parts = []
    for w in sc.get('windows', []):
        parts.append('w:%s/%s/%s' % tuple(w))
    for w in sc.get('windows_b', []):
        parts.append('wB:%s/%s/%s' % tuple(w))
    for key in ('mode_values', 'phase', 'pulse_width_ns', 'stall_phase', 'abort', 'proto_err_bit',
                'reset_pulses', 'xprobe'):
        if sc.get(key) not in (None, []):
            parts.append('%s=%s' % (key, sc[key]))
    return ' '.join(parts)
# ------------------------------------------------------------------- edge-sample straddle guard
def require_span(samples, anchor_ps, pre_ns, post_ns, what):
    """a sample set must actually straddle its event anchor: pre-event points alone are not a response

    samples: [(t_ps, value)] already read out of the trace.
    """
    if not samples:
        raise Refuse('%s: no samples at all' % what)
    lo = anchor_ps - pre_ns * PS
    hi = anchor_ps + post_ns * PS
    if any(any(c in tv.XZ for c in v) for _t, v in samples):
        raise Refuse('%s: a sample value is x/z' % what)
    pre = [t for t, _v in samples if lo <= t < anchor_ps]
    post = [t for t, _v in samples if anchor_ps < t <= hi]
    if not pre:
        raise Refuse('%s: nothing sampled in [%s, %s) ns before the anchor, so the excerpt cannot show '
                     'a change' % (what, fmt_ns(lo), fmt_ns(anchor_ps)))
    if not post:
        raise Refuse('%s: every point is taken before the anchor at %s ns; a pre-event sample is not a '
                     'response' % (what, fmt_ns(anchor_ps)))
    if len(post) < 2:
        raise Refuse('%s: only %d point(s) after the anchor, cannot tell a response from one sample'
                     % (what, len(post)))
    return (len(pre), len(post))


# ------------------------------------------------------------------- CSV / atomic write / hashes
def sha256_file(path):
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


def csv_cell(v):
    s = v if isinstance(v, _text) else u(v)
    if any(c in s for c in (u',', u'"', u'\n')):
        return u'"' + s.replace(u'"', u'""') + u'"'
    return s


TEXT_NONFINITE = ('nan', 'NaN', 'inf', '-inf', 'Infinity', '-Infinity', 'None', 'none_')


def csv_text(rows, order=None, what='an in-memory table'):
    """render rows as CSV text, refusing an empty set, a ragged row and a non-finite value

    Refusing before anything is written is what lets the exporter build the whole artefact set in
    memory and publish it only once every table is known good.
    """
    if not rows:
        raise Refuse('refusing to render 0 rows for %s: an empty result is not evidence' % what)
    keys = list(order) if order else list(rows[0].keys())
    for r in rows:
        miss = [k for k in keys if k not in r]
        if miss:
            raise Refuse('case %s lacks fields %s: the CSV would be ragged' % (r.get('case_id'), miss))
        for k in keys:
            v = r[k]
            if isinstance(v, float) and (v != v or v in (float('inf'), float('-inf'))):
                raise Refuse('case %s field %s is not finite' % (r.get('case_id'), k))
            if v is None:
                raise Refuse('case %s field %s is None' % (r.get('case_id'), k))
            if isinstance(v, _text) and v.strip() in ('nan', 'NaN', 'inf', '-inf', 'Infinity',
                                                     '-Infinity'):
                raise Refuse('case %s field %s is not finite' % (r.get('case_id'), k))
            if isinstance(v, _text) and any(c in v for c in (u'\x00',)):
                raise Refuse('case %s field %s carries a NUL' % (r.get('case_id'), k))
    out = [u','.join(keys) + u'\n']
    for r in rows:
        out.append(u','.join(csv_cell(r[k]) for k in keys) + u'\n')
    return u''.join(out)


def write_csv(stream, rows, order=None):
    stream.write(csv_text(rows, order))
    return len(rows)


def write_rows(path, rows, order=None):
    """atomic CSV write that refuses an empty row set instead of clearing real evidence"""
    text = csv_text(rows, order, path)
    d = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + '.tmp'
    fp = io.open(tmp, 'w', encoding='utf-8', newline='\n')
    try:
        fp.write(text)
    finally:
        fp.close()
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)
    return len(rows)


# ------------------------------------------------------------------- synthetic traces (selftest only)
class Synth(object):
    """a small VCD writer used only by --selftest; it builds the short hand-calculated waveforms"""

    def __init__(self):
        self.sigs = []
        self.id_of = {}
        self.events = []
        self.timescale = '1ns'
        self.unit_ps = PS         # timestamps are stored in ps and written in timescale units

    def add(self, name, width=1):
        if name in self.id_of:
            return self
        self.id_of[name] = chr(33 + len(self.sigs))
        self.sigs.append((name, width, self.id_of[name]))
        return self

    def width(self, name):
        for n, w, _i in self.sigs:
            if n == name:
                return w
        raise KeyError(name)

    def set(self, t_ns, name, value):
        w = self.width(name)
        if isinstance(value, _text) and set(value) <= set('01xz'):
            v = value
        else:
            v = format_vec(int(value), w)
        self.events.append((int(round(t_ns * PS / 1)), name, v))
        return self

    def drop(self, name):
        self.sigs = [s for s in self.sigs if s[0] != name]
        self.events = [e for e in self.events if e[1] != name]
        return self

    def emit(self, path):
        d = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(d):
            os.makedirs(d)
        order = {}
        for t, name, v in self.events:
            order.setdefault(t, []).append((name, v))
        out = ['$date DATA-7A checker selftest $end',
               '$version synthetic $end',
               '$timescale %s $end' % self.timescale,
               '$scope module tb $end']
        for nm, w, i in self.sigs:
            if '/' not in nm:
                out.append('$var wire %d %s %s $end' % (w, i, nm))
        out.append('$upscope $end')
        insts = sorted(set(nm.split('/')[0] for nm, _w, _i in self.sigs if '/' in nm))
        for inst in insts:
            out.append('$scope module %s $end' % inst)
            for nm, w, i in self.sigs:
                if nm.startswith(inst + '/'):
                    out.append('$var wire %d %s %s $end' % (w, i, nm.split('/')[1]))
            out.append('$upscope $end')
        out.append('$enddefinitions $end')
        for t in sorted(order):
            out.append('#%d' % (t // self.unit_ps))
            for nm, v in order[t]:
                if self.width(nm) == 1:
                    out.append('%s %s' % (v, self.id_of[nm]))
                else:
                    out.append('b%s %s' % (v, self.id_of[nm]))
        fp = io.open(path, 'w', encoding='utf-8', newline='\n')
        try:
            fp.write(u'\n'.join(out) + u'\n')
        finally:
            fp.close()
        return path

    def rewrite_time(self, path, delta):
        """move the last timestamp below the one before it: a malformed-dump refusal test"""
        txt = u(io.open(path, encoding='utf-8').read()).split('\n')
        marks = [k for k, ln in enumerate(txt) if ln.startswith('#')]
        if len(marks) < 2:
            raise Refuse('the synthetic trace is too short to reorder')
        prev = int(txt[marks[-2]][1:])
        txt[marks[-1]] = '#' + str(max(0, prev - 5))
        if int(txt[marks[-1]][1:]) >= prev:
            raise Refuse('cannot build a backwards timestamp from this trace')
        fp = io.open(path, 'w', encoding='utf-8', newline='\n')
        try:
            fp.write(u'\n'.join(txt))
        finally:
            fp.close()
        return path


REVIEW = os.path.normpath(os.path.join(HERE, '..', 'review'))

TBV = [('case_id', 32), ('clk', 1), ('tick', 1), ('blank', 1), ('fault', 1), ('reset_n', 1),
       ('system_en', 1), ('latch_stb', 1), ('pwm_start', 1), ('cfg_valid', 1), ('mode', 2)]
OUTV = [('data_en', 1), ('data_en_b', 1), ('pam_sel', 3), ('win_state', 3), ('cfg_version', 8),
        ('proto_err', 8), ('obs_tick', 1), ('cfg_pure', 8), ('cfg_hyb_time', 6), ('cfg_hyb_pam', 3)]


def declare(s, insts=('u_a', 'u_b')):
    for nm, w in TBV:
        s.add(nm, w)
    for d in insts:
        for nm, w in OUTV:
            s.add('%s/%s' % (d, nm), w)
    return s


def synth_main_case(mode, code, tick_ns, pam_code=0, cid=7, defect=None, clk_ns=CLK_NS,
                    code_b=None, pam_b=None):
    """build one legal main-case waveform from the hand table, then optionally break it

    The timing convention matches the real testbench: the reference clock rises every clk_ns, the
    tick enable is raised 5 ns ahead of the edge that consumes it and stays up 1 ns past it, so t0
    is a reference edge and every output transition is on one too.
    """
    m_int = expected_intervals(mode, code)
    code_b = code if code_b is None else code_b
    pam_b = pam_code if pam_b is None else pam_b
    full = FULL[mode]
    s = declare(Synth())

    s.set(0, 'case_id', cid)
    s.set(0, 'clk', 0)
    s.set(0, 'tick', 0)
    s.set(0, 'blank', 1)
    s.set(0, 'fault', 0)
    s.set(0, 'reset_n', 0)
    s.set(0, 'system_en', 1)
    s.set(0, 'latch_stb', 0)
    s.set(0, 'pwm_start', 0)
    s.set(0, 'cfg_valid', 0)
    s.set(0, 'mode', mode)
    for d in ('u_a', 'u_b'):
        s.set(0, '%s/data_en' % d, 0)
        s.set(0, '%s/data_en_b' % d, 1)
        s.set(0, '%s/pam_sel' % d, 0)
        s.set(0, '%s/win_state' % d, 0)
        s.set(0, '%s/cfg_version' % d, 0)
        s.set(0, '%s/proto_err' % d, 0)
        s.set(0, '%s/obs_tick' % d, 0)
        s.set(0, '%s/cfg_pure' % d, 0)
        s.set(0, '%s/cfg_hyb_time' % d, 0)
        s.set(0, '%s/cfg_hyb_pam' % d, 0)
    s.set(20, 'reset_n', 1)
    for d, c, p in (('u_a', code, pam_code), ('u_b', code_b, pam_b)):
        s.set(40, '%s/cfg_pure' % d, c if mode == MODE_PURE else 0)
        s.set(40, '%s/cfg_hyb_time' % d, c if mode == MODE_HYBRID else 0)
        s.set(40, '%s/cfg_hyb_pam' % d, p)
    s.set(40, 'cfg_valid', 1)
    s.set(60, 'latch_stb', 1)
    for d, c, p in (('u_a', code, pam_code), ('u_b', code_b, pam_b)):
        s.set(64, '%s/cfg_version' % d, 1)
        s.set(64, '%s/pam_sel' % d, PAM_PURE_SYMBOL if mode == MODE_PURE else p)
    s.set(70, 'latch_stb', 0)
    s.set(80, 'pwm_start', 1)
    for d in ('u_a', 'u_b'):
        s.set(84, '%s/win_state' % d, 1)
    s.set(120, 'pwm_start', 0)                                    # held 40 ns
    t_bl = 150
    t0 = 160                                                       # the edge that consumes the 155 tick
    s.set(t_bl, 'blank', 0)
    window_end = t0 + full * tick_ns
    off = t0 + m_int * tick_ns
    end = window_end + 6 * tick_ns + 50

    t = 0
    while t <= end:
        s.set(t, 'clk', 1)
        s.set(t + clk_ns // 2, 'clk', 0)
        t += clk_ns

    T = tick_ns
    if defect == 'tick_off_grid':
        T = tick_ns + 1

    def emit_stream(spacing, jitter_from=None, jitter=0):
        k = 0
        while k <= full + 5:
            base = t0 + k * spacing + (jitter if (jitter_from is not None and k >= jitter_from) else 0)
            s.set(base - 5, 'tick', 1)
            s.set(base + 1, 'tick', 0)
            k += 1
    if defect == 'tick_jitter':
        emit_stream(tick_ns, jitter_from=3, jitter=2)
    else:
        emit_stream(T)

    for d, c in (('u_a', code), ('u_b', code_b)):
        held = PAM_PURE_SYMBOL if mode == MODE_PURE else (pam_code if d == 'u_a' else pam_b)
        skew = tick_ns if (defect == 'late_instance' and d == 'u_b') else 0
        m_d = expected_intervals(mode, c)
        s.set(t0 + skew, '%s/win_state' % d, 2)
        if m_d > 0:
            s.set(t0 + skew, '%s/data_en' % d, 1)
            s.set(t0 + skew, '%s/data_en_b' % d, 0)
        if m_d > 0 and not (defect == 'no_end' and d == 'u_a'):
            s.set(t0 + m_d * T + skew, '%s/data_en' % d, 0)
            s.set(t0 + m_d * T + skew, '%s/data_en_b' % d, 1)
        if defect == 'pam_drops' and d == 'u_a':
            s.set(window_end, '%s/pam_sel' % d, 0)
        if defect == 'x_in_window' and d == 'u_a':
            s.set(t0 + tick_ns, '%s/pam_sel' % d, 'xxx')
            s.set(t0 + 2 * tick_ns, '%s/pam_sel' % d, format_vec(held, 3))
        s.set(t0 + full * T, '%s/win_state' % d, 3)
        k = 0
        while k <= full:                                        # accepted ticks: intervals plus the end
            s.set(t0 + k * T - 5 + skew, '%s/obs_tick' % d, 1)
            s.set(t0 + k * T + 1 + skew, '%s/obs_tick' % d, 0)
            k += 1

    if defect == 'off_by_one':
        s.events = [(t + tick_ns * PS, n, v)
                    if n in ('u_a/data_en', 'u_a/data_en_b') and t == off * PS else (t, n, v)
                    for (t, n, v) in s.events]
    if defect == 'narrow_pulse':
        mid = (off if m_int else t0 + tick_ns) + tick_ns // 2
        s.set(mid, 'u_a/data_en', 1)
        s.set(mid, 'u_a/data_en_b', 0)
        s.set(mid + 1, 'u_a/data_en', 0)
        s.set(mid + 1, 'u_a/data_en_b', 1)
    if defect == 'zero_width_glitch':
        tt = (off if m_int else t0) + tick_ns
        s.set(tt, 'u_a/data_en', '1')
        s.set(tt, 'u_a/data_en', '0')
        s.set(tt, 'u_a/data_en_b', '0')
        s.set(tt, 'u_a/data_en_b', '1')
    if defect == 'reopen':
        s.set(window_end + tick_ns, 'u_a/data_en', 1)
        s.set(window_end + tick_ns, 'u_a/data_en_b', 0)
        s.set(window_end + 2 * tick_ns, 'u_a/data_en', 0)
        s.set(window_end + 2 * tick_ns, 'u_a/data_en_b', 1)
    if defect == 'b_is_qbar':
        # the old DFF's qbar behaviour: data_en_b falls when blank is released, data_en stays low
        s.set(t_bl, 'u_a/data_en_b', '0')
    if defect == 'x_on_code':
        nm = 'u_a/cfg_pure' if mode == MODE_PURE else 'u_a/cfg_hyb_time'
        w = 8 if mode == MODE_PURE else 6
        s.set(58, nm, 'x' * w)
        s.set(66, nm, format_vec(code, w))
    if defect == 'z_in_window':
        held_a = PAM_PURE_SYMBOL if mode == MODE_PURE else pam_code
        s.set(t0 + tick_ns, 'u_a/pam_sel', 'zzz')
        s.set(t0 + 2 * tick_ns, 'u_a/pam_sel', format_vec(held_a, 3))
    if defect == 'proto_err_set':
        s.set(90, 'u_a/proto_err', 1)
    if defect == 'version_double':
        s.set(90, 'u_a/cfg_version', 3)
    if defect == 'abort_state':
        s.set(t0 + tick_ns, 'u_a/win_state', 4)
    if defect == 'light_in_blank':
        s.set(100, 'u_a/data_en', 1)
        s.set(140, 'u_a/data_en', 0)
    if defect == 'obs_tick_in_blank':
        s.set(100, 'u_a/obs_tick', 1)
        s.set(110, 'u_a/obs_tick', 0)

    cut = end
    if defect == 'truncated':
        cut = window_end + tick_ns
    s.events = [e for e in s.events if e[0] <= cut * PS]

    path = os.path.join(REVIEW, 'dd1_d7a_selftest_%s_%d_%d.vcd' % (defect or 'legal', mode, code))
    if defect == 'bad_timescale':
        s.timescale = '10ns'
    if defect == 'missing_signal':
        s.drop('u_a/data_en_b')
    s.emit(path)
    if defect == 'backwards_time':
        s.rewrite_time(path, -5)
    if defect == 'duplicate_time_marker':
        txt = u(io.open(path, encoding='utf-8').read()).split('\n')
        marks = [k for k, ln in enumerate(txt) if ln.startswith('#')]
        k = marks[len(marks) // 2]
        txt.insert(k, txt[k])          # the same time block announced twice
        io.open(path, 'w', encoding='utf-8', newline='\n').write(u('\n'.join(txt)))
    return path, {'mode': MODE_NAME[mode], 'code': code, 'intervals': m_int, 'tick_ns': T,
                  't0': t0, 'window_end': window_end, 'off': off, 'end': cut,
                  'pam': PAM_PURE_SYMBOL if mode == MODE_PURE else pam_code}


def synth_marker_unknown():
    """a well-formed dump whose case marker never resolves: there is no case to judge, so no row"""
    s = declare(Synth())
    s.set(0, 'case_id', 'x' * 32)
    s.set(0, 'clk', 0)
    s.set(10, 'clk', 1)
    s.set(20, 'clk', 0)
    s.set(30, 'clk', 1)
    return s.emit(os.path.join(REVIEW, 'dd1_d7a_selftest_marker_unknown.vcd'))


def synth_two_cases():
    """two legal cases in one dump, to prove the marker really segments a run"""
    joined = Synth()
    base = 0
    for cid, (mode, code, tick) in ((11, (MODE_PURE, 3, PURE_100HZ)),
                                    (12, (MODE_HYBRID, 63, HYB_100HZ))):
        p, _spec = synth_main_case(mode, code, tick, pam_code=6, cid=cid)
        tr = tv.Trace(p)
        for nm in sorted(tr.changes):
            joined.add(nm, tr.widths[nm])
        for nm in sorted(tr.changes):
            for (t, v) in tr.changes[nm]:
                joined.set((base + t) // PS, nm, v)
        base += tr.end_time + 100 * PS
    return joined.emit(os.path.join(REVIEW, 'dd1_d7a_selftest_two.vcd'))


# ------------------------------------------------------------------- selftest
def selftest():
    report = []
    bad = [0]

    def note(ok, name, detail):
        report.append('%-4s %-38s %s' % ('PASS' if ok else 'FAIL', name, detail))
        if not ok:
            bad[0] += 1

    for (mode, code), want in sorted(HAND_INTERVALS.items()):
        got = expected_intervals(mode, code)
        note(got == want, 'table %s code %d' % (MODE_NAME[mode], code),
             'hand-typed %d, function says %s' % (want, got))
    for mode in (MODE_PURE, MODE_HYBRID):
        miss = [c for c in range(0, MAX_CODE[mode] + 1) if expected_intervals(mode, c) is None]
        note(not miss, 'table covers all %s codes' % MODE_NAME[mode], 'gaps=%s' % (miss or 'none'))
        over = [c for c in (MAX_CODE[mode] + 1, MAX_CODE[mode] + 2)
                if expected_intervals(mode, c) is not None]
        note(not over, 'table rejects codes above %s' % MAX_CODE[mode], 'accepted=%s' % (over or 'none'))
    note(expected_intervals(2, 0) is None and expected_intervals(3, 0) is None,
         'table rejects illegal modes', 'mode 2 and 3 have no interval count')

    def run(path):
        try:
            rows, tr = check_main_trace(path, 'selftest')
            return rows, None
        except (tv.VcdError, Refuse) as exc:
            return None, str(exc)

    legal_cases = ((MODE_PURE, 1, PURE_100HZ, 'exactly one interval'),
                   (MODE_PURE, 255, PURE_60HZ, 'full window at code 255'),
                   (MODE_PURE, 0, PURE_100HZ, 'black code 0 stays dark'),
                   (MODE_HYBRID, 63, HYB_100HZ, 'full window at code 63'),
                   (MODE_HYBRID, 0, HYB_60HZ, 'hybrid black with a PAM code'),
                   (MODE_HYBRID, 5, HYB_60HZ, 'short hybrid interval count'),
                   (MODE_PURE, 254, PURE_100HZ, 'one interval short of full'))
    for mode, code, tick, label in legal_cases:
        p, spec = synth_main_case(mode, code, tick, pam_code=code % 8)
        rows, err = run(p)
        if err:
            note(False, 'legal: %s' % label, 'refused: %s' % err[:90])
            continue
        row = rows[0]
        want_w = spec['intervals'] * spec['tick_ns']
        ok = (len(rows) == 1 and row['verdict'] == 'PASS' and row['a_pam_code'] == spec['pam']
              and row['a_on_width_ns'] == str(want_w) and row['instances_match'] == 'PASS')
        note(ok, 'legal: %s' % label,
             'width=%s ns want=%d segments=%s pam=%s match=%s verdict=%s %s'
             % (row['a_on_width_ns'], want_w, row['a_on_segments'], row['a_pam_code'],
                row['instances_match'], row['verdict'], row['failures'][:70]))

    defects = [
        ('off-by-one wide', (MODE_PURE, 7), 'off_by_one', 'ON_WIDTH'),
        ('full window one tick short', (MODE_PURE, 255), 'off_by_one', 'ON_WIDTH'),
        ('missing window end point', (MODE_PURE, 200), 'no_end', 'NO_DEASSERTION'),
        ('narrow pulse after PWM off', (MODE_HYBRID, 30), 'narrow_pulse', 'SEGMENT_COUNT'),
        ('zero-width glitch at one timestamp', (MODE_HYBRID, 8), 'zero_width_glitch', 'SEGMENT_COUNT'),
        ('PAM code falls back at PWM off', (MODE_HYBRID, 12), 'pam_drops', 'PAM_NOT_HELD'),
        ('data_en_b is not the complement', (MODE_PURE, 9), 'b_is_qbar', 'DATA_EN_B_COMPLEMENT'),
        ('one instance one tick late', (MODE_HYBRID, 40), 'late_instance', 'INSTANCES_DIFFER'),
        ('x inside the judged window', (MODE_PURE, 60), 'x_in_window', 'UNKNOWN_VALUE'),
        ('z inside the judged window', (MODE_PURE, 60), 'z_in_window', 'UNKNOWN_VALUE'),
        ('x on the code bus at LATCH', (MODE_PURE, 60), 'x_on_code', 'UNKNOWN_VALUE'),
        ('tick spacing jitter', (MODE_PURE, 30), 'tick_jitter', 'TICK_SPACING_UNSTABLE'),
        ('tick off the reference grid', (MODE_HYBRID, 20), 'tick_off_grid', 'TICK_NOT_ALIGNED'),
        ('re-open after the window end', (MODE_PURE, 12), 'reopen', 'REOPEN_AFTER_WINDOW'),
        ('proto_err recorded in a legal case', (MODE_PURE, 12), 'proto_err_set', 'PROTO_ERR_IN_MAIN'),
        ('cfg_version moved twice', (MODE_HYBRID, 12), 'version_double', 'CFG_VERSION'),
        ('abort state inside a main case', (MODE_HYBRID, 12), 'abort_state', 'WIN_STATE'),
        ('light while blank is asserted', (MODE_PURE, 20), 'light_in_blank', 'LIGHT_BEFORE_T0'),
        ('obs_tick pulses inside blank', (MODE_PURE, 20), 'obs_tick_in_blank', 'OBS_TICK_MISMATCH'),
        ('excerpt stops before the tail', (MODE_PURE, 3), 'truncated', 'TRUNCATED_TRACE'),
    ]
    tag_hits = [0]
    parse_hits = [0]
    for label, (mode, code), defect, tag in defects:
        p, _spec = synth_main_case(mode, code, PURE_100HZ if mode == MODE_PURE else HYB_100HZ,
                                  pam_code=code % 8, defect=defect)
        rows, err = run(p)
        tagged = bool(rows) and rows[0]['verdict'] == 'FAIL' and tag in rows[0]['failures']
        detail = ('refused while parsing: %s' % err[:70]) if err else \
            ('%s -> %s' % (tag, rows[0]['failures'][:100] if rows else 'no row'))
        note(bool(err) or tagged, label, detail)
        if tagged:
            tag_hits[0] += 1
        if err:
            parse_hits[0] += 1
    note(tag_hits[0] >= len(defects) - 2, 'defect tags judged inside the checker',
         'named-tag hits=%d, outright parse refusals=%d of %d defects'
         % (tag_hits[0], parse_hits[0], len(defects)))

    for label, defect, tag in (('time base is not 1 ns', 'bad_timescale', 'time base'),
                               ('judged signal missing', 'missing_signal', 'is not in the trace'),
                               ('timestamp goes backwards', 'backwards_time', 'backwards'),
                               ('timestamp announced twice', 'duplicate_time_marker',
                                'duplicate timestamp')):
        p, _spec = synth_main_case(MODE_PURE, 8, PURE_100HZ, defect=defect)
        rows, err = run(p)
        note(bool(err) and tag in (err or ''), 'refused while parsing: %s' % label,
             '%s -> %s' % (tag, (err or 'parsed without a refusal')[:80]))

    empty = synth_marker_unknown()
    rows, err = run(empty)
    note(bool(err) and 'unknown' in (err or ''), 'refused: empty case set, marker never resolves',
         (err or 'accepted')[:90])

    two = synth_two_cases()
    rows, err = run(two)
    note(not err and len(rows) == 2 and all(x['verdict'] == 'PASS' for x in rows),
         'legal: two cases segmented by the marker', 'rows=%d %s' % (len(rows) if rows else 0,
                                                                     (err or '')[:60]))

    # ---- the pre-event-sampling guard
    anchor = 5000 * PS
    good = [(t, '1') for t in (4990, 4995, 4998, 5002, 5006, 5010)]
    try:
        pre, post = require_span([(t * PS, v) for t, v in good], anchor, 20, 20, 'guard good')
        note(post >= 2, 'sample guard accepts a straddling excerpt', 'pre=%d post=%d' % (pre, post))
    except Refuse as exc:
        note(False, 'sample guard accepts a straddling excerpt', str(exc)[:80])
    before_only = [(t, '0') for t in (4980, 4985, 4990, 4995, 4999)]
    try:
        require_span([(t * PS, v) for t, v in before_only], anchor, 20, 20, 'pre-event only')
        note(False, 'sample guard refuses pre-event-only points', 'accepted')
    except Refuse as exc:
        note('pre-event sample is not a response' in str(exc),
             'sample guard refuses pre-event-only points', str(exc)[:90])
    try:
        require_span([], anchor, 20, 20, 'nothing')
        note(False, 'sample guard refuses an empty sample set', 'accepted')
    except Refuse as exc:
        note('no samples' in str(exc), 'sample guard refuses an empty sample set', str(exc)[:60])
    try:
        require_span([(t * PS, 'x' if t >= 5002 else '0') for t in (4990, 4998, 5002, 5006)],
                     anchor, 20, 20, 'x sample')
        note(False, 'sample guard refuses an unknown sampled value', 'accepted')
    except Refuse as exc:
        note('x/z' in str(exc), 'sample guard refuses an unknown sampled value', str(exc)[:60])

    # ---- the write guard: refusing must leave a real non-empty evidence file untouched
    guard = os.path.join(REVIEW, 'dd1_d7a_selftest_write_guard.csv')
    io.open(guard, 'w', encoding='utf-8', newline='\n').write(u'case_id,verdict\n1,PASS\n2,PASS\n')
    before = sha256_file(guard)
    for label, rows in (('empty row set', []), ('ragged row', [{'case_id': 1, 'verdict': 'PASS'}])):
        try:
            write_rows(guard, rows, order=['case_id', 'verdict', 'run_id'])
            after = 'WROTE_ANYWAY'
        except Refuse:
            after = sha256_file(guard)
        note(after == before, 'write guard refuses %s' % label,
             'digest unchanged=%s' % (after == before))
    try:
        write_rows(guard, [{'case_id': 1, 'verdict': 'PASS', 'run_id': 'x'}],
                   order=['case_id', 'verdict', 'run_id'])
        note(sha256_file(guard) != before, 'write guard still writes when rows are complete',
             'official write path not blocked')
    except Refuse as exc:
        note(False, 'write guard still writes when rows are complete', str(exc)[:60])

    report.append('')
    report.append('synthetic traces written under %s' % REVIEW)
    return bad[0], '\n'.join(report)


def main(argv):
    if '--selftest' in argv:
        bad, report = selftest()
        print(report)
        print('CHECKER_SELFTEST: %s' % ('PASS' if bad == 0 else 'FAIL (%d refused items missed)' % bad))
        return 0 if bad == 0 else 1
    kind = None
    path = out = run_id = scen = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ('--main', '--control'):
            kind = a[2:]
        elif a == '--out':
            i += 1
            out = argv[i]
        elif a == '--run-id':
            i += 1
            run_id = argv[i]
        elif a == '--scenarios':
            i += 1
            scen = argv[i]
        elif a.startswith('-'):
            return 2 if print('unknown option %s' % a) is None else 2
        else:
            path = a
        i += 1
    if not kind or not path:
        print('usage: dd1_d7a_check.py --selftest | --main|--control <vcd> --out <csv> '
              '[--scenarios <json>] [--run-id <id>]')
        return 2
    if kind == 'main':
        rows, _tr = check_main_trace(path, run_id or '')
    else:
        import json
        if not scen:
            print('--control needs --scenarios <json>')
            return 2
        rows, _tr = check_control_trace(path, json.load(io.open(scen, encoding='utf-8')), run_id or '')
    npass = len([x for x in rows if x['verdict'] == 'PASS'])
    print('%s: cases=%d pass=%d fail=%d' % (kind, len(rows), npass, len(rows) - npass))
    for x in rows:
        if x['verdict'] != 'PASS':
            print('  case %s FAIL %s' % (x['case_id'], x['failures'][:140]))
    if out:
        n = write_rows(out, rows)
        print('rows=%d written=%s' % (n, out))
    return 0 if rows and npass == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
