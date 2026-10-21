# -*- coding: utf-8 -*-
"""DATA-7B: turn one accepted DATA-7A controller trace into PWL stimulus for the analog bench.

    python scripts/dd1_d7b_trace.py --selftest
    python scripts/dd1_d7b_trace.py --vcd <path> --case D7B-P30-C016 --golden <csv> --out <dir>

The DUT bytes are the accepted DATA-7A RTL; this module never re-implements its behaviour. It reads
the four-state dump with the frozen reader (`dd1_d7a_trace`), measures the real edges, and compares
them against an independent hand-written golden table: the expected interval count comes from the
contract's code mapping in `tests/dd1_d7b/golden_windows.csv`, never from the DUT's own target_q.

Everything downstream of this file is verification stimulus, not a product output path: the PWL is an
offline bench source and the finite ramp is this round's POC_ASSUMPTION.

Refusal rules, never relaxed (task book 5.5, 5.6):
  * x or z anywhere on a signal this round reads;
  * a negative time, a fractional count, a time that goes backwards or repeats;
  * a conducting segment that does not match the golden width, or a pulse count that does not match
    the golden pulse count;
  * two transitions closer together than the requested ramp, which would make the ramps overlap -- a
    short glitch is refused and reported, never dropped, rounded, stretched or merged.
"""
from __future__ import print_function

import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7a_trace as TD                     # frozen four-state reader: imported, never modified

NS = 1000                                     # picoseconds per nanosecond
LEVEL_V = 1.8                                 # the 0 / 1.8 V bench levels (POC_ASSUMPTION)
TAIL_NS = 200                                 # the simulated window must run 200 ns past t1


class Refuse(Exception):
    """a refusal is a verdict, not a crash: the caller records it and stops"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def header_facts(path):
    """the VCD's own declared date, version and timescale, verbatim"""
    facts = {'date': '', 'version': '', 'timescale': '', 'first_scope': ''}
    with io.open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            s = line.strip()
            for key in ('date', 'version', 'timescale'):
                if s.startswith('$' + key) and not facts[key]:
                    parts = s.split(None, 1)
                    facts[key] = parts[1].strip() if len(parts) > 1 else ''
            if s.startswith('$scope') and not facts['first_scope']:
                facts['first_scope'] = s
            if s.startswith('$enddefinitions'):
                break
    return facts


def whole_int(txt, field):
    """discrete values stay integers: a fractional spelling is refused, never truncated"""
    if txt is None or not re.match(r'^-?\d+$', str(txt)):
        raise Refuse('%s is %r, which is not an integer count' % (field, txt))
    return int(txt)


def checked_edges(series, name):
    """validate [(t_ps, value)]: no negative time, no step backwards, no duplicate timestamp"""
    out = []
    prev = None
    for t, v in series:
        t = int(t)
        if t < 0:
            raise Refuse('%s changes at a negative time %d ps' % (name, t))
        if prev is not None:
            if t < prev:
                raise Refuse('%s goes backwards: %d ps after %d ps' % (name, t, prev))
            if t == prev:
                raise Refuse('%s repeats the timestamp %d ps with a different value' % (name, t))
        out.append((t, v))
        prev = t
    return out


def defined_bits(trace, name):
    """[(t_ps, int)] for one scalar signal, refusing on any x/z value it ever holds"""
    key = trace.resolve(name)
    out = []
    for t_ps, val in trace.changes[key]:
        ok, num = TD.bits(val)
        if not ok:
            raise Refuse('%s holds a four-state x/z value %r at %d ps: the trace is not usable as '
                         'stimulus' % (name, val, int(t_ps)))
        if len(val) != 1:
            raise Refuse('%s is %r, not a scalar bit' % (name, val))
        out.append((int(t_ps), num))
    return checked_edges(out, name)


def bus_values(trace, name, defined_from_ps=None):
    """[(t_ps, int)] for a multi-bit signal.

    A state or counter bus is an attestation record, not stimulus: the accepted RTL legitimately
    holds x on it until the reset edge. So x is refused anywhere at or after `defined_from_ps` (the
    first accepted tick of the trace), and counted and reported before it.
    """
    key = trace.resolve(name)
    out = []
    undefined_before = 0
    for t_ps, val in trace.changes[key]:
        ok, num = TD.bits(val)
        if not ok:
            if defined_from_ps is None or int(t_ps) >= defined_from_ps:
                raise Refuse('%s holds x/z %r at %d ps, inside the measured span'
                             % (name, val, int(t_ps)))
            undefined_before += 1
            continue
        out.append((int(t_ps), num))
    return checked_edges(out, name), undefined_before


def value_at(series, t_ps, default=0):
    v = default
    for t, val in series:
        if t <= t_ps:
            v = val
        else:
            break
    return v


def segments_of(edges, t_from, t_to):
    """maximal high runs of `edges` clipped to [t_from, t_to), as (start, end, width) ps"""
    edges = checked_edges(edges, 'segment source')
    segs = []
    cur = None
    for t, val in edges:
        if val == 1 and cur is None:
            cur = max(t, t_from)
        elif val == 0 and cur is not None:
            end = min(t, t_to)
            if end > cur:
                segs.append((cur, end, end - cur))
            cur = None
    if cur is not None and t_to > cur:
        segs.append((cur, t_to, t_to - cur))
    return segs


def sampling_edges(clk_edges, obs_rises):
    """the reference-clock edge that consumed each accepted tick

    obs_tick is `tick_accept`, a combinational audit node: it rises when the enable rises, which the
    accepted DATA-7A testbench places TICK_LEAD ns *ahead* of the edge that samples it. The window
    boundary that the RTL acts on is that sampling edge, so t0 is defined here as the first reference
    rising edge at or after the first obs_tick rise, and the lead is recorded rather than assumed.
    """
    out = []
    for t in obs_rises:
        later = [c for c in clk_edges if c >= t]
        if not later:
            raise Refuse('the accepted tick at %d ps has no reference edge after it' % t)
        out.append(later[0])
    return out


def read_trace(vcd_path, scope='tb_dd1_d7b_pwm'):
    """every quantity the PWL conversion needs, measured off the real edges"""
    if not os.path.isfile(vcd_path):
        raise Refuse('trace %s does not exist' % vcd_path)
    trace = TD.Trace(vcd_path)
    q = lambda n: '%s/%s' % (scope, n)
    ck = defined_bits(trace, q('clk'))
    de = defined_bits(trace, q('data_en'))
    deb = defined_bits(trace, q('data_en_b'))
    ot = defined_bits(trace, q('obs_tick'))
    bl = defined_bits(trace, q('blank'))
    fl = defined_bits(trace, q('fault'))
    tk = defined_bits(trace, q('tick'))

    obs_rises = [t for t, v in ot if v == 1]
    if not obs_rises:
        raise Refuse('no accepted tick anywhere in %s: the protocol never armed a window' % vcd_path)
    clk_rises = [t for t, v in ck if v == 1]
    sampled = sampling_edges(clk_rises, obs_rises)
    leads = sorted(set(sampled[i] - obs_rises[i] for i in range(len(obs_rises))))
    if len(leads) != 1 or leads[0] <= 0 or leads[0] >= 10000:
        raise Refuse('the accepted ticks are consumed at inconsistent distances %s ps from the '
                     'enable: the trace cannot be re-based on one t0' % (leads,))
    for t, v in de:
        if value_at(deb, t, 1 - v) == v:
            raise Refuse('data_en_b is not the complement of data_en at %d ps' % t)
    # attestation buses: x is allowed only before the first consuming edge (the reset edge)
    att_from = sampled[0]
    st, st_x = bus_values(trace, q('win_state'), att_from)
    pm, pm_x = bus_values(trace, q('pam_sel'), att_from)
    cv, cv_x = bus_values(trace, q('cfg_version'), att_from)
    pe, pe_x = bus_values(trace, q('proto_err'), att_from)
    return {
        'vcd': os.path.basename(vcd_path),
        'vcd_sha256': sha256(vcd_path),
        'header': header_facts(vcd_path),
        'end_ps': int(trace.end_time),
        't0_ps': sampled[0],
        'tick_rises_ps': obs_rises,
        'tick_sampling_ps': sampled,
        'tick_lead_ps': leads[0],
        'tick_count': len(obs_rises),
        'clk_period_ps': clk_rises[1] - clk_rises[0] if len(clk_rises) > 1 else None,
        'data_en_edges': de,
        'data_en_b_edges': deb,
        'blank_edges': bl,
        'fault_edges': fl,
        'tb_tick_edges': tk,
        'win_state': st,
        'pam_sel': pm,
        'cfg_version': cv,
        'proto_err_last': pe[-1][1] if pe else None,
        'attestation_x_before_t0': {'win_state': st_x, 'pam_sel': pm_x,
                                    'cfg_version': cv_x, 'proto_err': pe_x},
    }


def load_golden(path):
    rows = []
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = [h.strip() for h in f.readline().strip().split(',')]
        for line in f:
            if not line.strip():
                continue
            vals = [v.strip() for v in line.rstrip('\r\n').split(',')]
            if len(vals) != len(hdr):
                raise Refuse('golden row %s has %d fields against a %d field header'
                             % (line.strip(), len(vals), len(hdr)))
            rows.append(dict(zip(hdr, vals)))
    if not rows:
        raise Refuse('golden table %s is empty' % path)
    return rows


def golden_for(rows, case_id, window):
    hits = [r for r in rows if r['case_id'] == case_id and r['window'] == window]
    if len(hits) != 1:
        raise Refuse('golden table has %d row(s) for case %s window %s, need exactly 1'
                     % (len(hits), case_id, window))
    return hits[0]


def check_window(facts, gold, hint_ps=None):
    """one window's real edges against its golden row; the window's own first accepted tick is t0"""
    tick_ps = whole_int(gold['tick_ns'], 'tick_ns') * NS
    window_ps = whole_int(gold['window_ns'], 'window_ns') * NS
    full = whole_int(gold['full_intervals'], 'full_intervals')
    exp_width_ps = whole_int(gold['expected_conducting_ns'], 'expected_conducting_ns') * NS
    exp_pulses = whole_int(gold['expected_pulses'], 'expected_pulses')

    rises = facts['tick_sampling_ps']
    if hint_ps is None:
        t0 = rises[0]
    else:
        later = [t for t in rises if t >= hint_ps]
        if not later:
            raise Refuse('window %s of %s has no accepted tick at or after %d ps'
                         % (gold['window'], gold['case_id'], hint_ps))
        t0 = later[0]
    t1 = t0 + window_ps
    ticks = [t for t in rises if t0 - 1 <= t < t1]
    if not ticks:
        raise Refuse('window %s of %s has no accepted tick in [%d, %d) ps'
                     % (gold['window'], gold['case_id'], t0, t1))
    spacings = set(ticks[i + 1] - ticks[i] for i in range(len(ticks) - 1))
    if spacings - {tick_ps}:
        raise Refuse('accepted tick spacings %s ps are not the golden %d ps'
                     % (sorted(spacings), tick_ps))
    if len(ticks) != whole_int(gold['expected_accepted_ticks'], 'expected_accepted_ticks'):
        raise Refuse('window %s of %s accepted %d tick(s) inside its own span, the golden table '
                     'says %d' % (gold['window'], gold['case_id'], len(ticks),
                                  gold['expected_accepted_ticks']))
    segs = segments_of(facts['data_en_edges'], t0, t1)
    if len(segs) != exp_pulses:
        raise Refuse('window %s of %s shows %d conducting pulse(s) in [%d, %d) ps, the golden table '
                     'says %d' % (gold['window'], gold['case_id'], len(segs), t0, t1, exp_pulses))
    total = sum(s[2] for s in segs)
    if total != exp_width_ps:
        raise Refuse('window %s of %s conducts %d ps in total, the golden table says %d ps'
                     % (gold['window'], gold['case_id'], total, exp_width_ps))
    if window_ps != full * tick_ps:
        raise Refuse('golden window %d ps is not full_intervals %d x tick %d ps'
                     % (window_ps, full, tick_ps))
    return {
        'window': gold['window'],
        'seq': whole_int(gold['seq'], 'seq'),
        'role': gold['role'],
        'mode': gold['mode'],
        'code': gold['code'],
        'pam_request': gold['pam_request'],
        'tick_ns': gold['tick_ns'],
        'window_ns': gold['window_ns'],
        'full_intervals': full,
        'expected_intervals': gold['expected_intervals'],
        'expected_conducting_ns': gold['expected_conducting_ns'],
        'expected_pulses': exp_pulses,
        't0_ps': t0,
        't1_ps': t1,
        'accepted_ticks_in_window': len(ticks),
        'expected_accepted_ticks': gold['expected_accepted_ticks'],
        'first_tick_ps': t0,
        'tick_lead_ps': facts['tick_lead_ps'],
        'segments_ps': [[s[0], s[1], s[2]] for s in segs],
        'conducted_ps': total,
    }


def window_edges(edges, t0_ps, t_stop_ps):
    """the data_en transitions of one window, plus the level carried in just before it

    A rise that lands exactly on t0 is a transition of this window, not the level the window starts
    at: the carried-in value is read one ps earlier, or the PWL would begin high and lose its edge.
    """
    before = [v for t, v in edges if t < t0_ps]
    initial = before[-1] if before else 0
    trans = [(int(t), int(v)) for t, v in edges if t0_ps <= t <= t_stop_ps]
    return [(t0_ps - 1, int(initial))] + trans


def build_pwl(edges, t_start_ps, t_stop_ps, shift_ps, ramp_ps, level=LEVEL_V):
    """finite-slope PWL: each real edge becomes the 50 % point of a ramp `ramp_ps` wide

    Never shortens, stretches, rounds or drops a transition; overlapping ramps are refused.
    """
    if ramp_ps <= 0 or ramp_ps % 2:
        raise Refuse('ramp %d ps must be a positive even number of picoseconds' % ramp_ps)
    if t_stop_ps <= t_start_ps:
        raise Refuse('PWL span %d..%d ps is empty' % (t_start_ps, t_stop_ps))
    # the level the span starts at is the value strictly *before* it: an edge sitting exactly on
    # t_start_ps is a transition of this window, not its initial level
    cur = value_at(edges, t_start_ps - 1, 0)
    pts = [(0, float(cur) * level)]
    prev_t = 0
    half = ramp_ps // 2
    for t, v in edges:
        if t < t_start_ps or t > t_stop_ps:
            continue
        if v == cur:
            continue
        lo, hi = t - half + shift_ps, t + half + shift_ps
        if lo <= prev_t:
            raise Refuse('the ramp for the edge at %d ps would overlap the previous PWL point at '
                         '%d ps: this trace cannot become finite-slope stimulus without dropping, '
                         'rounding or stretching a pulse' % (t, prev_t))
        if hi > t_stop_ps + shift_ps:
            raise Refuse('the ramp for the edge at %d ps runs past the requested stop %d ps'
                         % (t, t_stop_ps))
        pts.append((lo, float(cur) * level))
        pts.append((hi, float(v) * level))
        prev_t = hi
        cur = v
    pts.append((t_stop_ps + shift_ps, float(cur) * level))
    times = [p[0] for p in pts]
    if any(times[i + 1] <= times[i] for i in range(len(times) - 1)):
        raise Refuse('PWL times are not strictly increasing')
    return pts, cur


def case_document(vcd_path, case_id, gold_rows, shift_ns, ramp_ns, scope='tb_dd1_d7b_pwm',
                  tail_ns=TAIL_NS):
    facts = read_trace(vcd_path, scope)
    mine = [r for r in gold_rows if r['case_id'] == case_id]
    if not mine:
        raise Refuse('golden table has no window for case %s' % case_id)
    mine = sorted(mine, key=lambda r: whole_int(r['seq'], 'seq'))
    docs = []
    hint = None
    for gold in mine:
        w = check_window(facts, gold, hint)
        hint = w['t1_ps']
        docs.append(w)
    shift_ps = whole_int(shift_ns, 'shift_ns') * NS
    ramp_ps = whole_int(ramp_ns, 'ramp_ns') * NS
    tail_ps = whole_int(tail_ns, 'tail_ns') * NS
    for w in docs:
        t_stop = w['t1_ps'] + tail_ps
        pts, _ = build_pwl(window_edges(facts['data_en_edges'], w['t0_ps'], t_stop),
                           w['t0_ps'], t_stop, shift_ps, ramp_ps)
        w['t_stop_ps'] = t_stop
        w['pwl_points'] = pts
        w['pwl_sha256'] = hashlib.sha256(
            '\n'.join('%d %.6g' % (t, v) for t, v in pts).encode('utf-8')).hexdigest()
    return {'case_id': case_id, 'shift_ps': shift_ps, 'ramp_ps': ramp_ps, 'level_v': LEVEL_V,
            'facts': facts, 'windows': docs}


# ------------------------------------------------------------------ offline self test
def _synthetic():
    """hand-comparable refusals; the circuit under test is never the checker's own test case"""
    bad = []

    def expect_refuse(name, fn):
        try:
            fn()
        except Refuse:
            return True
        except Exception as exc:                       # some other exception is not a refusal
            bad.append('%s raised %s instead of refusing' % (name, exc))
            return False
        bad.append('%s did not refuse' % name)
        return False

    ok = True
    n = 0
    # 1 two edges closer than the ramp must refuse rather than drop one of them
    n += 1
    ok &= expect_refuse('ramp_overlap', lambda: build_pwl(
        [(0, 0), (1000, 1), (3000, 0)], 0, 200000, 0, 2000))
    # 2 a ramp that would run past the requested stop must refuse
    n += 1
    ok &= expect_refuse('ramp_past_stop', lambda: build_pwl(
        [(0, 0), (199000, 1)], 0, 200000, 0, 4000))
    # 3 times that step backwards must refuse
    n += 1
    ok &= expect_refuse('backwards_time', lambda: build_pwl(
        [(5000, 1), (4000, 0)], 0, 200000, 0, 2000))
    # 4 a fractional discrete count must refuse, not truncate
    n += 1
    ok &= expect_refuse('fractional_count', lambda: whole_int('30.5', 'tick_ns'))
    # 5 a missing golden row must refuse
    n += 1
    ok &= expect_refuse('missing_golden', lambda: golden_for(
        [{'case_id': 'X', 'window': 'normal'}], 'Y', 'normal'))
    # 6 a negative edge time must refuse
    n += 1
    ok &= expect_refuse('negative_time', lambda: segments_of([(-5, 1), (10, 0)], 0, 100))
    # 7 a duplicate timestamp with a conflicting value must refuse
    n += 1
    ok &= expect_refuse('duplicate_time', lambda: checked_edges([(10, 1), (10, 0)], 'x'))
    # 8 a rise outside the window contributes nothing (never a clipped-in fake pulse)
    n += 1
    got = segments_of([(0, 0), (200, 1), (300, 0)], 0, 100)
    if got:
        bad.append('clipping produced a pulse outside the window: %r' % (got,))
        ok = False
    # 9 a segment that starts before t0 is clipped to t0
    n += 1
    got = segments_of([(0, 1), (100, 0)], 0, 100)
    if got != [(0, 100, 100)]:
        bad.append('a segment starting before t0 was not clipped: %r' % (got,))
        ok = False
    # 10 a flat window keeps two points and ends exactly at the requested stop
    n += 1
    pts, cur = build_pwl([], 0, 100000, 5000000, 2000)
    if pts != [(0, 0.0), (5100000, 0.0)] or cur != 0:
        bad.append('flat PWL points wrong: %r' % (pts,))
        ok = False
    # 11 one 2 ns ramp centred on its own edge, hold levels explicit
    n += 1
    pts, cur = build_pwl([(0, 0), (5000, 1), (9000, 0)], 0, 20000, 0, 2000)
    want = [(0, 0.0), (4000, 0.0), (6000, 1.8), (8000, 1.8), (10000, 0.0), (20000, 0.0)]
    if pts != want:
        bad.append('ramp points wrong: %r' % (pts,))
        ok = False
    # 12 a shift moves the whole ramp and its midpoint stays on the real edge
    n += 1
    pts, cur = build_pwl([(0, 0), (5000, 1)], 0, 20000, 2500000, 10000)
    want = [(0, 0.0), (2500000, 0.0), (2510000, 1.8), (2520000, 1.8)]
    if pts != want or cur != 1:
        bad.append('shifted ramp wrong: %r' % (pts,))
        ok = False
    elif (pts[1][0] + pts[2][0]) // 2 != 5000 + 2500000:
        bad.append('the ramp midpoint is not the shifted edge')
        ok = False
    # 13 a rise that lands exactly on the window start is a transition, not the carried-in level
    n += 1
    pts, cur = build_pwl(window_edges([(0, 0), (1000000, 1), (1030000, 0)], 1000000, 1100000),
                         1000000, 1100000, 0, 2000)
    want = [(0, 0.0), (999000, 0.0), (1001000, 1.8), (1029000, 1.8), (1031000, 0.0),
            (1100000, 0.0)]
    if pts != want or cur != 0:
        bad.append('a window that rises on its own t0 came out wrong: %r' % (pts,))
        ok = False
    return ok, bad, n


def main(argv):
    opt = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith('--'):
            key = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                opt[key] = argv[i + 1]
                i += 2
            else:
                opt[key] = '1'
                i += 1
        else:
            i += 1
    if 'selftest' in opt:
        ok, bad, n = _synthetic()
        for b in bad:
            print('SELFTEST_BAD %s' % b)
        print('D7B_TRACE_SELFTEST: %s (%d/%d)' % ('PASS' if ok and not bad else 'FAIL', n - len(bad), n))
        return 0 if ok and not bad else 1
    for need in ('vcd', 'case', 'golden'):
        if need not in opt:
            print('D7B_TRACE_REFUSED --vcd, --case and --golden are required')
            return 2
    rows = load_golden(opt['golden'])
    doc = case_document(opt['vcd'], opt['case'], rows, opt.get('shift-ns', '2500'),
                        opt.get('ramp-ns', '2'))
    out = opt.get('out')
    if out:
        if not os.path.isdir(out):
            os.makedirs(out)
        path = os.path.join(out, 'trace_%s.json' % opt['case'])
        with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(doc, indent=1, sort_keys=True))
        for w in doc['windows']:
            pp = os.path.join(out, 'pwl_%s_%s.txt' % (opt['case'], w['window']))
            with io.open(pp, 'w', encoding='utf-8', newline='\n') as f:
                for t, v in w['pwl_points']:
                    f.write('%d %.6g\n' % (t, v))
        print('D7B_TRACE_WRITTEN %s (%d window(s))' % (path, len(doc['windows'])))
    print('D7B_TRACE_OK case=%s t0_ps=%d ticks=%d pulses=%d'
          % (opt['case'], doc['windows'][0]['t0_ps'], doc['facts']['tick_count'],
             sum(len(w['segments_ps']) for w in doc['windows'])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
