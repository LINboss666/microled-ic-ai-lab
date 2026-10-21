# -*- coding: utf-8 -*-
"""DATA-7A evidence identity check -- recompute the claims from the bytes that will be committed.

    python scripts/dd1_d7a_evidence_check.py

This reads only `results/evidence/dd1_d7a_*` and the source files the manifest names. It does not
run the simulator and it does not trust any report text: it re-counts rows, re-hashes every file,
refuses empty tables, non-finite numbers, blank required fields and any digest that no longer matches
the bytes on disk -- and, because a matching hash proves nothing about meaning, it also rebuilds the
contract's expected (mode, frame, tick, code, pam) combination set, recomputes every interval,
endpoint and accepted-tick count from mode + code + tick, checks that each control scenario kind was
executed and that an expected refusal failed for the reason it declares, and checks that a failure
model filed as functional was actually seen to break the design.

Counts and times are parsed as the two different kinds of quantity they are: a code, a segment count,
a configuration version or an accepted-tick count has to be written as an integer, and a time is
compared as an exact number of picoseconds (a fraction is a legal way to write a time, and 30.5 ns is
a different time from 30 ns, so nothing is truncated before the comparison).

`--selftest` runs the re-checker over isolated copies of the delivered evidence that are hash
consistent but semantically wrong; each must be refused by the named check, and a legal fractional
representation of a correct time must still pass.

A PASS here means the delivered evidence is internally consistent and traceable to the delivered
source. It does not mean the circuit is correct -- that is the reviewer's judgement.
"""
from __future__ import print_function

import csv
import io
import json
import math
import os
import re
import sys
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
EV = os.path.join(PROJ, 'results', 'evidence')
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import dd1_d7a_run as R                                            # noqa: E402

REQUIRED_EVIDENCE = ['dd1_d7a_cases.csv', 'dd1_d7a_control_cases.csv', 'dd1_d7a_negative.csv',
                     'dd1_d7a_edge_samples.csv', 'dd1_d7a_manifest.json',
                     'dd1_d7a_environment.json', 'dd1_d7a_checker_selftest.txt',
                     'dd1_d7a_write_guard.txt']
NUMERIC = re.compile(r'^-?\d+(\.\d+)?$')
# Two different kinds of number arrive in these tables, and quietly turning one into the other is
# exactly the mistake this file used to make: a count is an integer, while a time is an exact quantity
# in a declared unit. `int(float("257.5"))` produced a legal-looking 257 boundary events and
# `int(float("30.5"))` matched a 30 ns contract, so both are refused here rather than rounded into
# agreement.
INTEGER_RE = re.compile(r'^\d+$')                        # discrete: codes, segments, versions, pulses
PS_RE = re.compile(r'^-?\d+(\.\d{1,3})?$')               # times: whole ns down to whole picoseconds
PS_PER_NS = 1000
COUNT_FIELDS = ('case_id', 'frame_hz', 'time_code', 'pam_code', 'tick_ns', 'exp_intervals',
                'full_intervals', 'a_on_intervals_measured', 'b_on_intervals_measured',
                'a_on_segments', 'b_on_segments', 'a_cfg_version', 'b_cfg_version',
                'a_obs_tick_pulses', 'b_obs_tick_pulses')
TIME_FIELDS = ('a_on_width_ns', 'b_on_width_ns', 'a_t0_ns', 'b_t0_ns', 'a_window_end_ns',
               'b_window_end_ns')
NUMERIC_FIELDS = list(COUNT_FIELDS) + list(TIME_FIELDS)


def int_value(text):
    """the integer a discrete field states, or None when the cell is not written as an integer"""
    if text is None or not INTEGER_RE.match(text):
        return None
    return int(text)


def ps_value(text):
    """an exact time in picoseconds, or None when the cell is not a representable time

    A fraction is a legal way to write a time -- the delivered checker reports picoseconds -- so this
    accepts 30, 30.5 and 30.500 alike and refuses only a cell that is not a plain decimal, or one that
    claims a fraction of a picosecond the measurement cannot carry. Refusing a *wrong* value is the
    comparison's job, never the parser's.
    """
    if text is None or not PS_RE.match(text):
        return None
    try:
        d = Decimal(text) * PS_PER_NS
    except InvalidOperation:
        return None
    if d != d.to_integral_value():
        return None
    return int(d)


def as_count(row, key):
    return int_value(row.get(key, ''))


def as_time(row, key):
    return ps_value(row.get(key, ''))


# The contract of reports/dd1_d7a_contract.md, restated here as data. It is deliberately NOT read
# back out of the CSV columns it is used to check, and not derived from the RTL either: a verifier
# that recomputes its expectations from the artefact it is auditing proves nothing.
CONTRACT_GROUPS = (('PURE', '100', '30'), ('PURE', '60', '50'),
                   ('HYBRID', '100', '120'), ('HYBRID', '60', '200'))
CONTRACT_FULL = {'PURE': 256, 'HYBRID': 64}
CONTRACT_PAM_PURE = '7'                       # a symbol code in Pure mode, not a current level


def contract_intervals(mode, code):
    code = int_value(code)
    if code is None:
        return None
    if mode == 'PURE':
        if code == 255:
            return 256
        return code if 0 <= code <= 254 else None
    if mode == 'HYBRID':
        if code == 63:
            return 64
        return code if 0 <= code <= 62 else None
    return None


def expected_combinations():
    """the exact (mode, frame, tick, time code, pam) set the matrix has to contain, no more, no less"""
    out = set()
    for mode, hz, tick in CONTRACT_GROUPS:
        if mode == 'PURE':
            for code in range(256):
                out.add((mode, hz, tick, str(code), CONTRACT_PAM_PURE))
        else:
            for code in range(64):
                for pam in range(8):
                    out.add((mode, hz, tick, str(code), str(pam)))
    return out


# every control scenario kind the delivered suite has to have executed
REQUIRED_KINDS = ['abort_pending', 'abort_pending_recover', 'abort_reauthorise',
                  'async_off_between_edges', 'clock_stall', 'code_edges', 'config_freshness',
                  'dark_only', 'display_frozen', 'mixed_codes', 'mode_bypass', 'mode_switch_safe',
                  'next_window_commit', 'no_auto_resume', 'pam_toggle', 'refused_dark',
                  'refused_then_window', 'recover_full_sequence', 'start_held_40ns_once',
                  'start_latch_same_edge', 'tick_in_blank_consumed', 'window_ok']
# an expected refusal has to fail for the reason that was declared, not merely fail
EXPECTED_REFUSALS = {'2036': 'UNKNOWN_VALUE'}

# failure models split by what they claim to break; a functional model must be seen to break something
FUNCTIONAL_MODELS = ['abort_keeps_pending_config', 'abort_reauthorises_display',
                     'auto_resume_after_abort', 'blank_gate_removed', 'counter_rollover_reopens',
                     'instance_b_late_one_reference_cycle', 'instance_b_tick_late_two_cycles',
                     'latch_really_adopts_mode', 'mixed_b_output_late_one_cycle',
                     'mixed_b_output_late_three_cycles', 'mixed_b_one_interval_short',
                     'pure255_only255', 'stale_latch_really_accepted', 'start_level_rearm']
DIAGNOSTIC_MODELS = ['mode_unset_error_bit_masked', 'stale_latch_error_bit_masked']
MUTATION_CLASSES = sorted(FUNCTIONAL_MODELS + DIAGNOSTIC_MODELS)
RESERVED = ['PWM_MOS_IMPLEMENTATION', 'PAM_8LEVEL_ANALOG_IMPLEMENTATION',
            'HYBRID_CURRENT_INTEGRATION', 'GRAY_LUT_IMPLEMENTATION', 'OPTICAL_EFFECTIVE_BITS',
            'PHYSICAL_CDC_AND_SKEW', 'NEW_SPECTRE_RUNS', 'NEW_OA_WRITES', 'LAYOUT_DRC_LVS_PEX',
            'SOA_SIGNOFF']

fails = []


def note(cond, label, detail):
    print('%-6s %s: %s' % ('PASS' if cond else 'FAIL', label, detail))
    if not cond:
        fails.append(label)


def rows_of(path):
    txt = io.open(path, encoding='utf-8').read()
    lines = [l for l in txt.split('\n') if l.strip()]
    if len(lines) < 2:
        note(False, 'EMPTY_TABLE', '%s has only a header' % os.path.basename(path))
        return []
    head = lines[0].split(',')
    out = []
    for ln in lines[1:]:
        cells = split_csv(ln)
        if len(cells) != len(head):
            note(False, 'RAGGED_ROW', '%s row %s has %d cells, header has %d'
                 % (os.path.basename(path), cells[0] if cells else '?', len(cells), len(head)))
            continue
        out.append(dict(zip(head, cells)))
    return out


def split_csv(line):
    cells, cur, quoted = [], '', False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            quoted = not quoted
        elif c == ',' and not quoted:
            cells.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    cells.append(cur)
    return cells


def main():
    for name in REQUIRED_EVIDENCE:
        p = os.path.join(EV, name)
        note(os.path.exists(p) and os.path.getsize(p) > 0, 'MISSING_EVIDENCE',
             '%s exists and is non-empty' % name)
    if fails:
        print('EVIDENCE_IDENTITY: FAIL')
        return 1

    man = json.load(io.open(os.path.join(EV, 'dd1_d7a_manifest.json'), encoding='utf-8'))
    env = json.load(io.open(os.path.join(EV, 'dd1_d7a_environment.json'), encoding='utf-8'))

    # 1. every committed byte the manifest describes is still the byte it hashed
    bad = []
    for rel, h in sorted(man['sources'].items()):
        p = os.path.join(PROJ, rel.replace('/', os.sep))
        if not os.path.exists(p) or R.sha256(p) != h:
            bad.append(rel)
    note(not bad, 'SOURCE_DIGEST', '%d source files hash-match the manifest' % len(man['sources'])
         + ('' if not bad else ' ; mismatched: %s' % bad))
    bad = []
    checked = [n for n in man['evidence'] if n != 'dd1_d7a_manifest.json']
    for name in sorted(checked):
        d = man['evidence'][name]
        p = os.path.join(EV, name)
        if not os.path.exists(p) or R.sha256(p) != d['sha256']:
            bad.append(name)
    note(not bad, 'EVIDENCE_DIGEST', '%d/%d evidence files hash-match the manifest'
         % (len(checked) - len(bad), len(checked)) + ('' if not bad else ' ; mismatched: %s' % bad)
         + ' ; manifest is not self-hashed and the freeze transcript is hashed by the handoff')

    # 2. the main matrix: row count, uniqueness, finiteness, verdicts, both instances
    rows = rows_of(os.path.join(EV, 'dd1_d7a_cases.csv'))
    ids = [r['case_id'] for r in rows]
    note(len(rows) == 1536, 'ROW_COUNT', 'main matrix rows=%d (want 1536)' % len(rows))
    note(len(set(ids)) == len(ids), 'UNIQUE_CASES', 'unique case ids=%d' % len(set(ids)))
    nones = [r['case_id'] for r in rows if r['verdict'] != 'PASS']
    note(not nones, 'VERDICT_ALL_PASS', 'non-PASS main rows=%d' % len(nones))
    pure = [r for r in rows if r['mode'] == 'PURE']
    hyb = [r for r in rows if r['mode'] == 'HYBRID']
    note(len(pure) == 512 and len(hyb) == 1024, 'MODE_SPLIT', 'PURE=%d HYBRID=%d' % (len(pure),
                                                                                     len(hyb)))
    ticks = sorted(set(r['tick_ns'] for r in rows))
    note(ticks == ['120', '200', '30', '50'], 'TICK_SET', 'tick spacings present: %s' % ticks)
    hz = sorted(set(r['frame_hz'] for r in rows))
    note(hz == ['100', '60'], 'FRAME_HZ_SET', 'example frame rates: %s' % hz)
    # a code->interval statement must be recomputable from the row itself
    bad = []
    for r in rows:
        for k in NUMERIC_FIELDS:
            v = r.get(k, '')
            if v == '' or not NUMERIC.match(v) or (float(v) != float(v)) or \
                    math.isinf(float(v)):
                bad.append('%s:%s=%r' % (r['case_id'], k, v))
        if len(bad) > 5:
            break
    note(not bad, 'FINITE_FIELDS', 'every measured field parses as a finite number'
         + ('' if not bad else ' ; first %s' % bad[:3]))
    # ... and a number is not yet the right *kind* of number: discrete quantities must be written as
    # integers, times must land on a whole picosecond. 257.5 boundary events and 30.5005 ns fail here.
    bad = []
    for r in rows:
        for k in COUNT_FIELDS:
            if as_count(r, k) is None:
                bad.append('%s:%s=%r is not an integer count' % (r['case_id'], k, r.get(k, '')))
        if len(bad) > 5:
            break
    note(not bad, 'INTEGER_COUNTS',
         'codes, frame rates, segments, versions and accepted-tick counts are written as integers'
         + ('' if not bad else ' ; first %s' % bad[:3]))
    bad = []
    for r in rows:
        for k in TIME_FIELDS:
            if as_time(r, k) is None:
                bad.append('%s:%s=%r is not a time on a whole picosecond'
                           % (r['case_id'], k, r.get(k, '')))
        if len(bad) > 5:
            break
    note(not bad, 'TIME_PICSECOND', 'every time field parses as an exact picosecond value in ns; a '
         'fraction is allowed, a truncated comparison is not'
         + ('' if not bad else ' ; first %s' % bad[:3]))
    bad = []
    for r in rows:
        T, exp, full = as_count(r, 'tick_ns'), as_count(r, 'exp_intervals'), as_count(r,
                                                                                      'full_intervals')
        if T is None or exp is None or full is None:
            bad.append('%s tick/exp/full is not an integer count' % r['case_id'])
            continue
        for pre in ('a_', 'b_'):
            segs = as_count(r, pre + 'on_segments')
            width = as_time(r, pre + 'on_width_ns')
            meas = as_count(r, pre + 'on_intervals_measured')
            t0, end = as_time(r, pre + 't0_ns'), as_time(r, pre + 'window_end_ns')
            want_seg = 1 if exp else 0
            if segs != want_seg or width != exp * T * PS_PER_NS or meas != exp:
                bad.append('%s%s exp=%d segs=%s width=%s meas=%s ns (want %d x %d ns)'
                           % (r['case_id'], pre, exp, r[pre + 'on_segments'],
                              r[pre + 'on_width_ns'], r[pre + 'on_intervals_measured'], exp, T))
            if None in (t0, end) or end - t0 != full * T * PS_PER_NS:
                bad.append('%s%s window endpoint %s-%s is not %d x %d ns'
                           % (r['case_id'], pre, r[pre + 'window_end_ns'], r[pre + 't0_ns'], full, T))
        if len(bad) > 5:
            break
    note(not bad, 'WIDTH_RECOMPUTABLE', 'on-width == intervals x measured tick for both instances, '
         'compared in picoseconds' + ('' if not bad else ' ; %s' % bad[:2]))
    note(len(rows) * 2 == man['counts']['instance_observations'], 'INSTANCE_OBSERVATIONS',
         'rows x 2 = %d matches manifest %d' % (len(rows) * 2, man['counts']['instance_observations']))
    matches = len([r for r in rows if r['instances_match'] == 'PASS'])
    note(matches == len(rows), 'INSTANCES_MATCH', '%d/%d rows agree between the two channels'
         % (matches, len(rows)))

    # 2b. the combination set straight off the contract: unique, legal, complete. 1536 unique case ids
    #     is a different claim: two rows can carry different ids and the same combination, which is
    #     exactly what the reviewed version accepted.
    keys = [(r['mode'], r['frame_hz'], r['tick_ns'], r['time_code'], r['pam_code']) for r in rows]
    seen = set()
    dupes = sorted(set(k for k in keys if k in seen or seen.add(k)))
    note(len(keys) == len(set(keys)), 'COMBINATION_UNIQUE',
         '%d rows carry %d distinct (mode, frame, tick, code, pam) combinations'
         % (len(rows), len(set(keys))) + ('' if not dupes else ' ; duplicated: %s' % (dupes[:3],)))
    want = expected_combinations()
    got = set(keys)
    extra = sorted(got - want)
    note(not extra, 'COMBINATION_LEGAL', '%d combination(s) outside the contract table' % len(extra)
         + ('' if not extra else ' ; e.g. %s' % (extra[:3],)))
    missing = sorted(want - got)
    note(not missing, 'COMBINATION_COMPLETE',
         'the contract asks for %d combinations, the table is missing %d' % (len(want), len(missing))
         + ('' if not missing else ' ; e.g. %s' % (missing[:3],)))

    # 2c. intervals, full window, endpoints, accepted-tick counts and PAM recomputed from
    #     mode + code + tick, never from the row's own exp_intervals claim. Times are compared as whole
    #     picoseconds and counts as integers, so a fractional cell contradicts the contract instead of
    #     being truncated into agreement with it.
    bad = []
    for r in rows:
        exp = contract_intervals(r['mode'], r['time_code'])
        full = CONTRACT_FULL.get(r['mode'])
        T = as_count(r, 'tick_ns')
        if exp is None or full is None:
            bad.append('%s is not a legal %s code %s' % (r['case_id'], r['mode'], r['time_code']))
            continue
        if T is None:
            bad.append('%s tick_ns %s is not an integer number of ns' % (r['case_id'], r['tick_ns']))
            continue
        if as_count(r, 'exp_intervals') != exp:
            bad.append('%s says exp_intervals=%s, the contract says %d for code %s'
                       % (r['case_id'], r['exp_intervals'], exp, r['time_code']))
        if as_count(r, 'full_intervals') != full:
            bad.append('%s says full_intervals=%s, the contract says %d'
                       % (r['case_id'], r['full_intervals'], full))
        for pre in ('a_', 'b_'):
            if as_count(r, pre + 'on_segments') != (1 if exp else 0):
                bad.append('%s%s shows %s segments for %d conducting intervals'
                           % (r['case_id'], pre, r[pre + 'on_segments'], exp))
            if as_time(r, pre + 'on_width_ns') != exp * T * PS_PER_NS:
                bad.append('%s%s width %s != %d x %d ns'
                           % (r['case_id'], pre, r[pre + 'on_width_ns'], exp, T))
            if as_count(r, pre + 'on_intervals_measured') != exp:
                bad.append('%s%s measured %s intervals, the contract says %d'
                           % (r['case_id'], pre, r[pre + 'on_intervals_measured'], exp))
            t0, end = as_time(r, pre + 't0_ns'), as_time(r, pre + 'window_end_ns')
            if None in (t0, end) or end - t0 != full * T * PS_PER_NS:
                bad.append('%s%s endpoint %s - %s is not t0 + %d x %d ns'
                           % (r['case_id'], pre, r[pre + 'window_end_ns'], r[pre + 't0_ns'], full, T))
            if as_count(r, pre + 'obs_tick_pulses') != full + 1:
                bad.append('%s%s accepted %s ticks, the window needs %d boundary events'
                           % (r['case_id'], pre, r[pre + 'obs_tick_pulses'], full + 1))
        pam = as_count(r, 'pam_code')
        if (r['mode'] == 'PURE' and r['pam_code'] != CONTRACT_PAM_PURE) or \
                (r['mode'] == 'HYBRID' and (pam is None or not 0 <= pam <= 7)):
            bad.append('%s pam_code %s is not a legal %s select' % (r['case_id'], r['pam_code'],
                                                                    r['mode']))
        if len(bad) > 5:
            break
    note(not bad, 'CONTRACT_RECOMPUTED',
         'intervals, full window, endpoints, accepted-tick counts and PAM recomputed from '
         'mode+code+tick' + ('' if not bad else ' ; %s' % bad[:2]))

    # 3. black code and full-window behaviour must appear in the table at all
    note(any(as_count(r, 'exp_intervals') == 0 for r in rows) and
         any(as_count(r, 'exp_intervals') == 256 for r in rows) and
         any(as_count(r, 'exp_intervals') == 64 for r in rows),
         'EDGE_CODES', 'the table contains code-0, Pure-full and Hybrid-full rows')

    # 4. control and negative tables
    ctl = rows_of(os.path.join(EV, 'dd1_d7a_control_cases.csv'))
    kinds = sorted(set(r['kind'] for r in ctl if r['kind']))
    note(len(ctl) >= 42, 'CONTROL_ROWS', 'control/mixed rows=%d over %d scenario kinds (want >= 42)'
         % (len(ctl), len(kinds)))
    unexpected = [r for r in ctl if r['verdict'] not in ('PASS',) and r['expect'] != 'refusal']
    note(not unexpected, 'CONTROL_VERDICTS',
         'control rows that failed without being declared as a required refusal: %d'
         % len(unexpected))
    ran = set(r['case_id'] for r in ctl)
    note(len(ran) >= 42, 'CONTROL_COVERAGE', '%d distinct control case ids actually executed'
         % len(ran))
    attested = [r for r in ctl if r.get('stimulus', '').strip()]
    note(len(attested) == len(ctl), 'STIMULUS_DECLARED',
         '%d/%d control rows carry their declared stimulus alongside what was observed'
         % (len(attested), len(ctl)))
    unattested = [r['case_id'] for r in ctl
                  if 'STIMULUS_UNATTESTED' in r['failures'] or 'STIMULUS_MISMATCH' in r['failures']]
    note(not unattested, 'STIMULUS_MATCHES', 'rows whose declared stimulus the trace contradicts: %s'
         % (unattested or 'none'))
    absent_kinds = sorted(set(REQUIRED_KINDS) - set(kinds))
    note(not absent_kinds, 'SCENARIOS_REQUIRED',
         '%d/%d required scenario kinds executed' % (len(set(REQUIRED_KINDS)) - len(absent_kinds),
                                                    len(REQUIRED_KINDS))
         + ('' if not absent_kinds else ' ; never executed: %s' % absent_kinds))
    wrong_reason = []
    for cid, tag in sorted(EXPECTED_REFUSALS.items()):
        row = [r for r in ctl if r['case_id'] == cid]
        if not row:
            wrong_reason.append('%s is absent' % cid)
        elif row[0]['verdict'] != 'FAIL' or tag not in row[0]['failures']:
            wrong_reason.append('%s verdict=%s failures=%s (needs %s)'
                                % (cid, row[0]['verdict'], row[0]['failures'][:60], tag))
    note(not wrong_reason, 'REFUSAL_REASON', 'every declared expected refusal fails for the reason it '
         'declares' + ('' if not wrong_reason else ' ; %s' % wrong_reason))
    thin = [k for k in ('abort_pending', 'abort_pending_recover', 'next_window_commit')
            if len([r for r in ctl if r['kind'] == k]) < 2]
    note(not thin, 'SCENARIO_PRESENT', 'the new F1/F4 kinds are each covered by at least two cases '
         '(a blank and a fault path, or both code and PAM changing)'
         + ('' if not thin else ' ; thin: %s' % thin))
    neg = rows_of(os.path.join(EV, 'dd1_d7a_negative.csv'))
    det = [r for r in neg if r['status'] == 'DETECTED' and r['class'] != 'checker_selftest']
    note(len(det) == len(MUTATION_CLASSES), 'MUTATION_CLASSES',
         '%d of %d mutation classes DETECTED' % (len(det), len(MUTATION_CLASSES)))
    note(sorted(r['class'] for r in det) == sorted(MUTATION_CLASSES), 'MUTATION_SET',
         'the %d functional and %d diagnostic failure models are all represented'
         % (len(FUNCTIONAL_MODELS), len(DIAGNOSTIC_MODELS)))
    cat_bad = []
    for r in neg:
        if r['class'] == 'checker_selftest':
            continue
        want = 'functional' if r['class'] in FUNCTIONAL_MODELS else \
            ('diagnostic' if r['class'] in DIAGNOSTIC_MODELS else None)
        if want is None:
            cat_bad.append('%s is not a declared model' % r['class'])
        elif r.get('category') != want:
            cat_bad.append('%s filed as %s, the table says %s'
                           % (r['class'], r.get('category'), want))
    note(not cat_bad, 'MUTATION_CATEGORY_HONEST',
         'each model is filed under the category its patch really changes'
         + ('' if not cat_bad else ' ; %s' % cat_bad[:3]))
    unconf = [r['class'] for r in neg if r.get('category') == 'functional'
              and r.get('fault_confirmed') != 'yes']
    note(not unconf, 'MUTATION_FAULT_OBSERVED', 'every functional model had its wrong behaviour seen '
         'in its own trace before the refusal' + ('' if not unconf else ' ; not exercised: %s' % unconf))
    fake = [r['class'] for r in neg if r.get('status') != 'DETECTED'
            and r.get('fault_confirmed') == 'yes']
    note(not fake, 'MUTATION_REFUSED_AFTER_FAULT', 'a model whose fault was observed must also be '
         'refused by the checker' + ('' if not fake else ' ; %s' % fake))
    notdet = [r['class'] for r in neg if r['status'] not in ('DETECTED',)]
    note(not notdet, 'MUTATION_ALL_DETECTED', 'not detected: %s' % (notdet or 'none'))
    nodigest = [r['class'] for r in neg if r['class'] != 'checker_selftest'
                and not re.match(r'^[0-9a-f]{64}$', r.get('mutant_rtl_sha256', ''))]
    note(not nodigest, 'MUTANT_SOURCE_DIGEST', 'each mutation records the sha256 of its real source'
         + ('' if not nodigest else ' ; missing: %s' % nodigest))

    # 4b. one run, one identity: the same run_id must appear in every table and both JSON records
    ids = set([r.get('run_id') for r in rows] + [r.get('run_id') for r in ctl] +
              [r.get('run_id') for r in neg])
    ids.discard(None)
    ids.discard('')
    note(len(ids) == 1 and ids == set([env.get('run_id'), man.get('run_id')]), 'RUN_ID_CHAIN',
         'run_id %s in the tables and in both JSON records' % (sorted(ids) or 'none'))
    tds = man.get('trace_digests') or {}
    note(bool(tds) and all(re.match(r'^[0-9a-f]{64}$', str(v)) for v in tds.values()),
         'TRACE_DIGESTS', '%d trace digests recorded in the manifest' % len(tds))
    note(man.get('traces_rejudged_before_publish') is True and env.get('identity_verified') is True,
         'REJUDGE_CHAIN', 'the export states that it re-judged the traces and verified the sources')

    # 5. edge samples must straddle their anchors, from the bytes alone
    smp = rows_of(os.path.join(EV, 'dd1_d7a_edge_samples.csv'))
    by, unread = {}, []
    for r in smp:
        rel = ps_value(r.get('relative_ns', ''))
        if rel is None:
            unread.append('%s:%s relative_ns=%r' % (r['case_id'], r['anchor'], r.get('relative_ns')))
            continue
        by.setdefault((r['case_id'], r['anchor'], r['signal']), []).append(rel)
    bad = []
    for k, rels in sorted(by.items()):
        if not any(x < 0 for x in rels) or not any(x > 0 for x in rels) or len(rels) < 3:
            bad.append('%s' % (k,))
    note(not unread, 'SAMPLE_TIMES_EXACT', '%d sample offsets are not exact picosecond times'
         % len(unread) + ('' if not unread else ' ; %s' % unread[:3]))
    note(len(by) > 0 and not bad, 'SAMPLES_STRADDLE',
         '%d (case, anchor, signal) sample sets, all with points before and after the anchor'
         % len(by) + ('' if not bad else ' ; failing: %s' % bad[:3]))
    anchors = set(r['anchor'] for r in smp)
    note('blank_abort_assert' in anchors, 'SAMPLE_ASYNC_SHUTOFF',
         'anchors present: %s' % ','.join(sorted(anchors)))
    xsig = [r for r in smp if any(c in r['value'] for c in 'xzXZ')]
    note(not xsig, 'SAMPLES_DEFINED', '%d sampled values are x/z (%s)' % (len(xsig),
                                                                          'must be none'))

    # 6. reserved statuses and the no-analog-run claim
    txt = io.open(os.path.join(EV, 'dd1_d7a_environment.json'), encoding='utf-8').read()
    for k in ('PWM_MOS_IMPLEMENTATION', 'PAM_8LEVEL_ANALOG_IMPLEMENTATION', 'NEW_SPECTRE_RUNS',
              'NEW_OA_WRITES'):
        note(k in env.get('reserved_statuses', {}) or k in txt, 'RESERVED_STATUS',
             '%s is stated in the delivered environment record' % k)
    note(env.get('spectre_runs') == 0 and env.get('oa_writes') == 0, 'NO_ANALOG_RUNS',
         'environment says spectre_runs=%s oa_writes=%s' % (env.get('spectre_runs'),
                                                            env.get('oa_writes')))
    note(env.get('four_state') is True, 'FOUR_STATE', 'the simulator is declared four-state')
    note(str(env.get('toolchain_provenance', {}).get('sha256')) == R.TOOL_SHA, 'TOOL_PROVENANCE',
         'toolchain digest recorded matches the pinned asset digest')

    print('')
    print('EVIDENCE_IDENTITY: %s (%d checks failed)' % ('PASS' if not fails else 'FAIL', len(fails)))
    return 0 if not fails else 1


def _write_rows(path, fields, rows):
    with io.open(path, 'w', encoding='utf-8', newline='') as fp:
        wr = csv.DictWriter(fp, fields, lineterminator='\n')
        wr.writeheader()
        wr.writerows(rows)


def _read_rows(path):
    with io.open(path, encoding='utf-8', newline='') as fp:
        rd = csv.DictReader(fp)
        return rd.fieldnames, list(rd)


def _retab(ev_dir, name, rows, fields):
    _write_rows(os.path.join(ev_dir, name), fields, rows)
    mp = os.path.join(ev_dir, 'dd1_d7a_manifest.json')
    man = json.load(io.open(mp, encoding='utf-8'))
    p = os.path.join(ev_dir, name)
    if name in man.get('evidence', {}):
        man['evidence'][name] = {'bytes': os.path.getsize(p), 'sha256': R.sha256(p)}
    with io.open(mp, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(man, indent=1, sort_keys=True) + '\n')


def selftest():
    """hash-consistent but semantically wrong evidence must still be refused

    Each case copies the delivered evidence into an isolated fixture, changes one thing that a digest
    comparison cannot see, refreshes that file's manifest digest so the hash gate stays satisfied, and
    then requires the named check to fail. An untouched copy must pass. Matching hashes are not a
    functional judgement, which is what the review said the delivered re-checker still got wrong.
    """
    import contextlib
    import shutil
    global EV
    real_ev = EV
    fixture = os.path.join(PROJ, 'review', 'dd1_d7a', 'evidence_selftest')
    cases = []

    def fresh(name):
        d = os.path.join(fixture, name)
        if os.path.isdir(d):
            shutil.rmtree(d)
        shutil.copytree(real_ev, d)
        return d

    def run(dirpath):
        global EV
        del fails[:]
        EV = dirpath
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main()
        got = list(fails)
        del fails[:]
        return rc, got

    try:
        rc, got = run(fresh('clean'))
        cases.append(('clean_evidence_passes', rc == 0 and not got, 'rc=%s fails=%s' % (rc, got)))

        d = fresh('duplicate_tuple')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_cases.csv'))
        rows[1] = dict(rows[0])
        rows[1]['case_id'] = '2'
        _retab(d, 'dd1_d7a_cases.csv', rows, fields)
        rc, got = run(d)
        cases.append(('duplicate_tuple_refused',
                      rc == 1 and 'COMBINATION_UNIQUE' in got and 'COMBINATION_COMPLETE' in got,
                      'fails=%s' % got[:3]))

        d = fresh('wrong_exp_intervals')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_cases.csv'))
        r = rows[5]
        r['exp_intervals'] = str(int_value(r['exp_intervals']) + 1)
        for pre in ('a_', 'b_'):
            r[pre + 'on_intervals_measured'] = r['exp_intervals']
            r[pre + 'on_width_ns'] = str(int_value(r['exp_intervals']) * int_value(r['tick_ns']))
        _retab(d, 'dd1_d7a_cases.csv', rows, fields)
        rc, got = run(d)
        cases.append(('wrong_exp_intervals_refused',
                      rc == 1 and 'CONTRACT_RECOMPUTED' in got, 'fails=%s' % got[:3]))

        # --- the numeric kind gates: a fraction must contradict the contract, never be truncated
        #     into agreement with it (the two corruptions the review reproduced, plus their neighbours)
        def contract_row(rows):
            for i, r in enumerate(rows):
                if r['mode'] == 'PURE' and r['time_code'] == '1' and r['tick_ns'] == '30':
                    return i
            raise AssertionError('no PURE code-1 tick-30 row to corrupt')

        def numeric_case(label, field, value, expect, forbidden=()):
            d = fresh(label)
            fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_cases.csv'))
            rows[contract_row(rows)][field] = value
            _retab(d, 'dd1_d7a_cases.csv', rows, fields)
            rc, got = run(d)
            cases.append((label, rc == 1 and all(x in got for x in expect)
                          and not any(x in got for x in forbidden),
                          '%s=%s rc=%s hit=%s' % (field, value, rc, got[:3])))

        numeric_case('fractional_width_refused', 'a_on_width_ns', '30.5',
                     ('WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED'),
                     ('FINITE_FIELDS', 'INTEGER_COUNTS', 'TIME_PICSECOND'))
        numeric_case('sub_picosecond_time_refused', 'a_on_width_ns', '30.5005',
                     ('TIME_PICSECOND', 'WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED'))
        numeric_case('fractional_boundary_count_refused', 'a_obs_tick_pulses', '257.5',
                     ('INTEGER_COUNTS', 'CONTRACT_RECOMPUTED'))
        numeric_case('fractional_segments_refused', 'a_on_segments', '1.5',
                     ('INTEGER_COUNTS', 'WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED'))
        numeric_case('fractional_tick_refused', 'tick_ns', '30.5',
                     ('INTEGER_COUNTS',))
        numeric_case('fractional_endpoint_refused', 'a_window_end_ns', '18545.5',
                     ('WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED'),
                     ('INTEGER_COUNTS', 'TIME_PICSECOND'))
        numeric_case('fractional_code_refused', 'time_code', '1.5',
                     ('INTEGER_COUNTS', 'CONTRACT_RECOMPUTED'))

        # ... while a time written as a fraction of the same value is a legal representation and must
        # still pass: the gate is about the quantity, not about the presence of a decimal point.
        d = fresh('legal_fractional_times')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_cases.csv'))
        r = rows[contract_row(rows)]
        for f in ('a_on_width_ns', 'a_t0_ns', 'a_window_end_ns'):
            r[f] = '%s.000' % r[f]
        _retab(d, 'dd1_d7a_cases.csv', rows, fields)
        rc, got = run(d)
        cases.append(('legal_fractional_time_representation_passes', rc == 0 and not got,
                      'rc=%s fails=%s' % (rc, got[:3])))

        d = fresh('missing_required_scenario')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_control_cases.csv'))
        rows = [r for r in rows if r['kind'] != 'next_window_commit']
        _retab(d, 'dd1_d7a_control_cases.csv', rows, fields)
        rc, got = run(d)
        cases.append(('missing_required_scenario_refused',
                      rc == 1 and 'SCENARIOS_REQUIRED' in got, 'fails=%s' % got[:3]))

        d = fresh('refusal_now_passing')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_control_cases.csv'))
        for r in rows:
            if r['case_id'] == '2036':
                r['verdict'], r['failures'] = 'PASS', 'none'
        _retab(d, 'dd1_d7a_control_cases.csv', rows, fields)
        rc, got = run(d)
        cases.append(('refusal_reason_enforced',
                      rc == 1 and 'REFUSAL_REASON' in got, 'fails=%s' % got[:3]))

        d = fresh('functional_model_without_fault')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_negative.csv'))
        for r in rows:
            if r.get('category') == 'functional':
                r['fault_confirmed'] = 'no'
        _retab(d, 'dd1_d7a_negative.csv', rows, fields)
        rc, got = run(d)
        cases.append(('functional_model_without_fault_refused',
                      rc == 1 and 'MUTATION_FAULT_OBSERVED' in got, 'fails=%s' % got[:3]))

        d = fresh('stale_run_id')
        fields, rows = _read_rows(os.path.join(d, 'dd1_d7a_cases.csv'))
        for r in rows:
            r['run_id'] = 'some_other_run'
        _retab(d, 'dd1_d7a_cases.csv', rows, fields)
        rc, got = run(d)
        cases.append(('run_id_chain_enforced', rc == 1 and 'RUN_ID_CHAIN' in got,
                      'fails=%s' % got[:3]))
    finally:
        EV = real_ev
        del fails[:]
    bad = 0
    for name, ok, detail in cases:
        print('%-4s EVIDENCE_SELFTEST %-38s %s' % ('PASS' if ok else 'FAIL', name, detail[:90]))
        if not ok:
            bad += 1
    print('EVIDENCE_SELFTEST: %s (%d cases)' % ('PASS' if not bad else 'FAIL (%d)' % bad, len(cases)))
    return 0 if not bad else 1


if __name__ == '__main__':
    if '--selftest' in sys.argv[1:]:
        sys.exit(selftest())
    sys.exit(main())
