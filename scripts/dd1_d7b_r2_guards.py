#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DATA-7B-R2: one suite that first reproduces the review's findings, then proves they are closed

TASK_DATA7B_R2 section 1 requires each defect to be reproduced on the base commit's own bytes before
anything is modified, and section 7 requires the reproduction to keep its command, reason and return
code. The same assertions are then re-run with ``--phase fixed`` to show the tools close them, so a
claim of repair is the same script the reproduction was, not a friendlier new one.

Nothing here starts a simulator or opens a socket: the account probes write synthetic files under a
temporary directory, and the tamper probes run against a disposable copy of a published bundle whose
manifest is re-sealed exactly as a forger would, so only semantics can catch the break.

usage: python scripts/dd1_d7b_r2_guards.py [--phase reproduce|fixed] [--bundle <published bundle>]
"""
from __future__ import print_function

import argparse
import glob
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_evidence_check as EC                          # noqa: E402
import dd1_d7b_measure as MS                                  # noqa: E402
import dd1_d7b_run as R                                       # noqa: E402

NS = 1000
ACCEPTED_AUTHORITY = 56          # task book 52 plus the 4 the user granted, and nothing else
FIXED_SEED = {'origin': 'synthetic seed', 'rows': []}


def u(text):
    return text if isinstance(text, str) else text.decode('utf-8', 'replace')


def account_rows(confirmed, uncertain=0, requested=0, ceiling=ACCEPTED_AUTHORITY):
    """a synthetic account with a known occupancy, no process ever started"""
    rows = []

    def add(prefix, n, state):
        for i in range(n):
            rows.append({'launch_id': '%s%03d' % (prefix, len(rows) + 1), 'task_id': 'SYNTH',
                         'run_id': 'synthetic', 'case_id': 'SYN-%03d' % len(rows), 'role': 'dut',
                         'state': state, 'requested_utc': '', 'ended_utc': '', 'rc': '',
                         'launch_evidence': 'synthetic', 'deck_sha256': '', 'pwl_sha256': '',
                         'raw_sha256': '', 'log_sha256': '', 'refusal': '',
                         'ceiling': str(ceiling), 'confirmed_after': '', 'occupied_after': ''})
    add('C', confirmed, 'CONFIRMED')
    add('U', uncertain, 'UNCERTAIN')
    add('Q', requested, 'REQUESTED')
    return rows


def write_account(path, rows):
    hdr = R.Account.HDR
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(','.join(hdr) + '\n')
        for r in rows:
            f.write(','.join(str(r.get(k, '')) for k in hdr) + '\n')


def read_account(path):
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = f.readline().strip().split(',')
        return [dict(zip(hdr, l.rstrip('\r\n').split(','))) for l in f if l.strip()]


class RenamerFails(OSError):
    pass


# ------------------------------------------------------------------ A: the account and the budget
def probe_a1(keep, phase):
    """the ceiling must come from the fixed authorisation, not from the file being checked"""
    src = newest_bundle(keep)
    dest = os.path.join(keep, 'a1_ceiling_60')
    shutil.copytree(src, dest)
    path = os.path.join(dest, 'launch_account.csv')
    rows = read_account(path)
    for r in rows:
        r['ceiling'] = '60'
    write_account(path, rows)
    EC.reseal(dest)
    res = EC.check_dir(dest)
    failures = set(res['failures'])
    if phase == 'reproduce':
        ok = 'BUDGET_RESPECTED' not in failures
        detail = 'with a self-declared 60 the checker passed BUDGET_RESPECTED (failures=%s)' % (
            ' '.join(sorted(failures)) or '-')
    else:
        ok = ('BUDGET_RESPECTED' in failures and 'BUDGET_AUTHORITY_FIXED' in failures)
        detail = 'BUDGET_RESPECTED=%s BUDGET_AUTHORITY_FIXED=%s' % (
            'BUDGET_RESPECTED' in failures, 'BUDGET_AUTHORITY_FIXED' in failures)
    return ok, detail


def probe_a2_reserve(keep, phase):
    """a reservation has to occupy the ceiling the moment it is written"""
    path = os.path.join(keep, 'a2_reserve.csv')
    write_account(path, account_rows(ACCEPTED_AUTHORITY - 1))
    acct = R.Account(path, ACCEPTED_AUTHORITY, FIXED_SEED)
    first = acct.reserve('SYN-A2', 'dut', 'd', 'p', 'synthetic')
    occupied_after_first = acct.counts()['occupied']
    refused = False
    try:
        acct.reserve('SYN-A2B', 'dut', 'd', 'p', 'synthetic')
    except R.OverBudget:
        refused = True
    counts = acct.counts()
    pending = len([r for r in acct.rows if r['state'] == 'REQUESTED'])
    if phase == 'reproduce':
        ok = not refused and occupied_after_first == ACCEPTED_AUTHORITY - 1
        detail = ('occupied stayed %d of %d while %d confirmed row(s) and %d REQUESTED row(s) were '
                  'in the file, so the second reserve was accepted'
                  % (occupied_after_first, ACCEPTED_AUTHORITY, counts['confirmed'], pending))
    else:
        ok = refused and occupied_after_first == ACCEPTED_AUTHORITY and pending == 1
        detail = 'first reserve occupied %d of %d, second refused; the %d REQUESTED row still costs' % (
            occupied_after_first, ACCEPTED_AUTHORITY, pending)
    return ok, detail


def probe_a2_seed(keep, phase):
    """the seeded history is a fact: state, role and run bind it, not just the id series"""
    hist = account_rows(59)
    for i, r in enumerate(hist):
        r['launch_id'] = 'H%03d' % (i + 1)
        r['task_id'] = R.TASK_ID
        r['run_id'] = 'r11_main' if i < 42 else 'r5_cal'
        r['case_id'] = '(per-directory record)'
        r['role'] = 'preflight' if i % 2 else 'dut'
        r['launch_evidence'] = 'reconcile_log_count'
        r['refusal'] = 'seeded from launches_reconcile.csv: carried in the task account'
    seed = {'origin': 'synthetic seed (TOTAL=59, 2 directory row(s))', 'rows': hist, 'confirmed': 59}
    path = os.path.join(keep, 'a2_seed.csv')
    write_account(path, hist)
    broken = [dict(r) for r in hist]
    for r in broken:
        r['state'] = 'REFUSED_NO_LAUNCH'
    write_account(path, broken)
    accepted = True
    detail = ''
    try:
        R.Account(path, ACCEPTED_AUTHORITY, seed)
    except Exception as exc:
        accepted = False
        detail = '%s: %s' % (type(exc).__name__, u(str(exc))[:140])
    if phase == 'reproduce':
        return accepted, 'rewrote all 59 history rows to REFUSED_NO_LAUNCH and the account still ' \
                         'opened (only the id series is compared)'
    return (not accepted), ('refused the rewritten history: %s' % detail) if detail else detail


def probe_a2_recovery(keep, phase):
    """recovering a crashed reservation changes its proven, never its price"""
    path = os.path.join(keep, 'a2_recovery.csv')
    write_account(path, account_rows(ACCEPTED_AUTHORITY - 2) + account_rows(0)[:0]
                  + [{'launch_id': 'Q001', 'task_id': 'SYN', 'run_id': 'synthetic',
                      'case_id': 'SYN-C', 'role': 'dut', 'state': 'REQUESTED', 'requested_utc': '',
                      'ended_utc': '', 'rc': '', 'launch_evidence': '', 'deck_sha256': '',
                      'pwl_sha256': '', 'raw_sha256': '', 'log_sha256': '', 'refusal': '',
                      'ceiling': str(ACCEPTED_AUTHORITY), 'confirmed_after': '',
                      'occupied_after': ''}])
    acct = R.Account(path, ACCEPTED_AUTHORITY, FIXED_SEED)
    counts = acct.counts()
    occupied_after_recovery = counts['occupied']
    third_refused = False
    try:
        acct.reserve('SYN-D', 'dut', 'd', 'p', 'synthetic')
    except R.OverBudget:
        third_refused = True
    occupied_after_third = acct.counts()['occupied']
    fourth_refused = False
    try:
        acct.reserve('SYN-E', 'dut', 'd', 'p', 'synthetic')
    except R.OverBudget:
        fourth_refused = True
    if phase == 'reproduce':
        # the 54 confirmed plus the recovered reservation cost 55 in the base build too, so a crash did
        # not refund the ceiling here; what broke is that a new reservation is free until it returns,
        # which let the file grow past the ceiling it is supposed to enforce
        return (not fourth_refused), \
            'recovery kept %d of %d, then SYN-D and SYN-E were both accepted: occupied went %d -> %d ' \
            'while 2 more rows were written, so the file holds %d rows against a ceiling of %d' % (
                occupied_after_recovery, ACCEPTED_AUTHORITY, occupied_after_recovery,
                occupied_after_third, len(acct.rows), ACCEPTED_AUTHORITY)
    return (occupied_after_recovery == ACCEPTED_AUTHORITY - 1 and not third_refused
            and occupied_after_third == ACCEPTED_AUTHORITY and fourth_refused), \
        'the recovered row occupies (%d of %d), SYN-D took it to %d and SYN-E was refused' % (
            occupied_after_recovery, ACCEPTED_AUTHORITY, occupied_after_third)


def probe_a3_flush(keep, phase):
    """a failed replacement must not delete the history it was replacing"""
    path = os.path.join(keep, 'a3_flush.csv')
    write_account(path, account_rows(1))
    before = read_account(path)
    acct = R.Account(path, ACCEPTED_AUTHORITY, FIXED_SEED)
    acct.note('SYN-E', 'reused_measurement', 'synthetic', 'note added by the flush probe')
    real_rename = os.rename
    real_replace = getattr(os, 'replace', None)
    calls = []

    def failing_swap(src, dst):
        calls.append(dst)
        raise RenamerFails(28, 'synthetic ENOSPC on the replacement')

    # the base build replaced the file with remove + rename and the fixed build with a single
    # os.replace, so the injected failure has to cover whichever primitive is in charge
    os.rename = failing_swap
    os.replace = failing_swap
    try:
        acct.flush()
        raised = None
    except Exception as exc:
        raised = '%s: %s' % (type(exc).__name__, u(str(exc))[:120])
    finally:
        os.rename = real_rename
        if real_replace is not None:
            os.replace = real_replace
    gone = not os.path.isfile(path)
    rows_after = read_account(path) if os.path.isfile(path) else []
    tmp_left = os.path.isfile(path + '.tmp')
    reopened = None
    if gone:
        try:
            reopened = len(read_account(path)) if os.path.isfile(path) else 0
        except Exception as exc:
            reopened = 'refused: %s' % u(str(exc))[:100]
    if phase == 'reproduce':
        ok = gone or (raised is None and tmp_left)
        return ok, ('replacement failed and the account file %s (%s left behind, raised=%s); '
                    'reopening reads %d rows' % ('disappeared' if gone else 'stayed',
                                                 os.path.basename(path) + '.tmp' if tmp_left
                                                 else 'no temporary file',
                                                 str(raised)[:60], len(rows_after)))
    return ((not gone) and len(rows_after) >= len(before) and raised is not None), \
        'old file kept (%d rows), error surfaced: %s' % (len(rows_after), str(raised)[:120])


def probe_a3_stale(keep, phase):
    """an older writer must not overwrite history a newer writer already recorded"""
    path = os.path.join(keep, 'a3_stale.csv')
    write_account(path, account_rows(1))
    older = R.Account(path, ACCEPTED_AUTHORITY, FIXED_SEED)
    newer = R.Account(path, ACCEPTED_AUTHORITY, FIXED_SEED)
    newer.note('SYN-F', 'reused_measurement', 'synthetic', 'written by the second instance')
    refused = False
    detail = ''
    try:
        older.note('SYN-G', 'reused_measurement', 'synthetic', 'written by the stale instance')
    except Exception as exc:
        refused = True
        detail = '%s: %s' % (type(exc).__name__, u(str(exc))[:140])
    if phase == 'reproduce':
        return (not refused), 'both instances started from the same 1-row file and the stale one ' \
                              'flushed last without any version or digest check'
    return refused and detail, 'stale writer refused: %s' % detail


# ------------------------------------------------------------------ B: the measurement edges
def probe_b1_deadline(keep, phase):
    """a deadline that falls inside a ramp must be checked at its left limit"""
    # hand: value 1 at 0/10/20 ns, 0.5 at 30 ns; band 0.95..1.05, deadline 25 ns. The straight line
    # leaves the band at 21 ns, so nothing is sustained up to the deadline.
    samples = [(0, 1.0), (10 * NS, 1.0), (20 * NS, 1.0), (30 * NS, 0.5), (40 * NS, 0.5)]
    got = MS.sustained_in_band(samples, 0, 0.95, 1.05, 25 * NS)
    if phase == 'reproduce':
        return got['status'] == 'SETTLED', \
            'the tool answered %s with held=%s ns across a segment that leaves the band at 21 ns' % (
                got['status'], ('%.1f' % (got.get('held_ps', 0) / 1000.0)) if got.get('held_ps')
                else '-')
    return got['status'] == 'NOT_SETTLED_WITHIN_PULSE', \
        'status=%s longest_interpolated=%s ns' % (got['status'],
                                                  '%.1f' % (got.get('longest_in_band_interp_ps',
                                                                    0) / 1000.0))


def probe_b2_phase(keep, phase):
    """data_en falling is data_en_b rising; the old code searched the wrong edge"""
    # hand: a 200 ns tick so the +-50 ns search cannot reach the open edge by luck
    rise, fall = 500 * NS, 500 * NS + 200 * NS
    de = [(0, 0.0), (rise - NS, 0.0), (rise + NS, 1.8), (fall - NS, 1.8), (fall + NS, 0.0),
          (fall + 400 * NS, 0.0)]
    deb = [(t, 1.8 - v) for t, v in de]
    cur = [(0, 0.0), (rise, 15e-6), (fall, 15e-6), (fall + 400 * NS, 0.0)]
    win = MS._win(cur, de, 0, fall + 200 * NS, 1.0, tick_ps=200 * NS, pulse=(rise, fall))
    win['de_b'] = MS.samples([str(t * 1e-12) for t, _ in deb], ['%.9g' % v for _, v in deb], 'deb')
    out = MS.measure_window(win, 15e-6, 200 * NS, ctx='R2-B2')
    if phase == 'reproduce':
        return out.get('de_b_fall_50_ps') == 'NOT_FOUND', \
            'the complementary node reported %r, because the search looked for a fall at the edge ' \
            'where data_en_b actually rises' % (out.get('de_b_fall_50_ps'),)
    got = out.get('de_b_rise_50_ps')
    return (isinstance(got, float) and abs(got - (fall + NS)) <= 2 * NS), \
        'de_b_rise_50_ps=%r expected ~%d ps' % (got, fall + NS)


def probe_b3_units(keep, phase):
    """a current tolerance cannot be 20 mA"""
    src = newest_bundle(keep)
    dest = os.path.join(keep, 'b3_current_sample')
    shutil.copytree(src, dest)
    path = os.path.join(dest, 'cases.csv')
    rows = u(io.open(path, encoding='utf-8').read()).split('\n')
    hdr = rows[0].split(',')
    col = hdr.index('current_10pct_ns')
    moved = 0
    for i, line in enumerate(rows[1:]):
        if not line.strip():
            continue
        cells = line.split(',')
        if cells[col] not in ('', '-', 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'):
            cells[col] = '%.4f' % (float(cells[col]) + 5.0)
            rows[i + 1] = ','.join(cells)
            moved += 1
    io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(rows))
    EC.reseal(dest)
    res = EC.check_dir(dest)
    new = set(res['failures'])
    if phase == 'reproduce':
        return (moved > 0 and 'CURRENT_EDGES_BRACKETED' not in new and 'EDGE_BINDINGS_RECOMPUTED'
                not in new), '%d claimed 10%% crossings were each moved 5 ns and nothing named it' \
                             % moved
    return (moved > 0 and bool(new & set(['EDGES_BRACKETED_BY_SAMPLES',
                                          'CURRENT_EDGES_BRACKETED', 'EDGE_BINDINGS_RECOMPUTED']))), \
        'named by %s' % ' '.join(sorted(new - set(['BUDGET_RESPECTED'])))


# ------------------------------------------------------------------ C: the remaining counterfeits
def tamper_copy(keep, name, src):
    dest = os.path.join(keep, name)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def edit_csv(dest, name, columns, row_filter, values):
    """set named columns on the rows a filter selects; returns how many rows changed"""
    path = os.path.join(dest, name)
    lines = u(io.open(path, encoding='utf-8').read()).split('\n')
    hdr = lines[0].split(',')
    changed = 0
    for i, line in enumerate(lines[1:]):
        if not line.strip():
            continue
        cells = line.split(',')
        row = dict(zip(hdr, cells))
        if not row_filter(row):
            continue
        for col, val in values.items():
            if col in hdr:
                cells[hdr.index(col)] = val
        lines[i + 1] = ','.join(cells)
        changed += 1
    io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    return changed


def probe_c_off(keep, phase):
    src = newest_bundle(keep)
    dest = tamper_copy(keep, 'c2_off_zero', src)
    n = edit_csv(dest, 'cases.csv', ['off_ns'],
                 lambda r: r['case_id'] == 'D7B-P30-C001' and r['window'] == 'normal',
                 {'off_ns': '0.0000'})
    EC.reseal(dest)
    new = set(EC.check_dir(dest)['failures'])
    if phase == 'reproduce':
        return n == 1 and not (new - set(['BUDGET_RESPECTED'])), \
            'off_ns of P30-C001 set to 0 ns changed no verdict'
    return bool(new & set(['LAST_100NS_RECOMPUTED', 'TURN_OFF_RECOMPUTED', 'OFF_TIMES_RECOMPUTED'])), \
        'named by %s' % ' '.join(sorted(new - set(['BUDGET_RESPECTED'])))


def probe_c_deb(keep, phase):
    src = newest_bundle(keep)
    dest = tamper_copy(keep, 'c4_deb_zero', src)
    n = edit_csv(dest, 'cases.csv', ['de_b_fall_50_ns'], lambda r: True, {'de_b_fall_50_ns': '0.0'})
    if n == 0:
        n = edit_csv(dest, 'cases.csv', ['de_b_rise_50_ns'], lambda r: True,
                     {'de_b_rise_50_ns': '0.0'})
    EC.reseal(dest)
    new = set(EC.check_dir(dest)['failures'])
    if phase == 'reproduce':
        return n and not (new - set(['BUDGET_RESPECTED'])), \
            '%d complementary-node times set to 0 ns changed nothing' % n
    return bool(new & set(['EDGES_BRACKETED_BY_SAMPLES', 'EDGE_BINDINGS_RECOMPUTED'])), \
        'named by %s' % ' '.join(sorted(new - set(['BUDGET_RESPECTED'])))


def probe_c_edge(keep, phase):
    src = newest_bundle(keep)
    dest = tamper_copy(keep, 'c5_delta_edge', src)
    n = edit_csv(dest, 'convergence.csv', ['delta_edge_ns'], lambda r: True,
                 {'delta_edge_ns': '9999.0000'})
    EC.reseal(dest)
    new = set(EC.check_dir(dest)['failures'])
    if phase == 'reproduce':
        return n and 'CONVERGENCE_RECOMPUTED' not in new, \
            'every convergence delta_edge_ns set to 9999 ns still reported CONVERGED'
    return 'CONVERGENCE_RECOMPUTED' in new, 'named by %s' % ' '.join(sorted(new))


def probe_c_vcd(keep, phase):
    """flip a delivered four-state transition and re-parse it; the frozen parser must refuse"""
    import dd1_d7b_trace as TR
    src = newest_bundle(keep)
    dest = tamper_copy(keep, 'c6_vcd_flip', src)
    table = os.path.join(dest, 'rtl_reverify.csv')
    rows = EC.read_rows(table)
    victim = [r for r in rows if r['case_id'] == 'D7B-P30-C001'][0]
    name = victim['new_vcd']
    candidates = [os.path.join(dest, name + '.txt'), os.path.join(dest, name)]
    path = [p for p in candidates if os.path.isfile(p)]
    if not path:
        return False, 'no delivered VCD for %s in the bundle (%s)' % (name, candidates)
    path = path[0]
    text = u(io.open(path, encoding='utf-8', errors='replace').read()).split('\n')
    ident = {}
    for line in text:
        if line.startswith('$var'):
            parts = line.split()
            # iverilog writes `$var <kind> <width> <id> <name> [[h:l]] $end`
            if len(parts) >= 5 and parts[4] in ('data_en', 'data_en_b'):
                ident[parts[4]] = parts[3]
    # iverilog writes a scalar change as `<value><id>` with no separator: `1&` for data_en's id
    if 'data_en' not in ident:
        return False, 'the delivered VCD names no data_en variable, so the probe cannot flip it'
    mark = ident['data_en']
    now = None
    flipped = []
    out = []
    for line in text:
        if line.startswith('#'):
            now = float(line[1:].strip())
            out.append(line)
            continue
        if (line and line[0] == '1' and line[1:] == mark and not flipped
                and 1400000 <= (now or 0) <= 1600000):
            # data_en's first rise inside the abort window is held low: data_en and data_en_b stop
            # being complements, which is what the frozen parser refuses
            line = '0' + line[1:]
            flipped.append(now)
            continue
        out.append(line)
    if not flipped:
        return False, 'no data_en transition was found in 1.4..1.6 us, so the probe proves nothing'
    io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
    parser_refused = False
    why = ''
    try:
        TR.read_trace(path)
        gold = TR.load_golden(os.path.join(PROJ, 'tests', 'dd1_d7b', 'golden_windows.csv'))
        TR.case_document(path, victim['case_id'], gold, str(2500), str(2))
    except Exception as exc:
        parser_refused = True
        why = '%s: %s' % (type(exc).__name__, u(str(exc))[:120])
    digest_vcd(path, table, victim['case_id'])
    EC.reseal(dest)
    keep_copy = os.path.join(keep, 'c6_vcd_baseline_copy')
    if not os.path.isdir(keep_copy):
        shutil.copytree(src, keep_copy)
        EC.reseal(keep_copy)
    baseline = set(EC.check_dir(keep_copy)['failures'])
    new = set(EC.check_dir(dest)['failures']) - baseline
    if phase == 'reproduce':
        return (parser_refused and not new), \
            'the frozen parser rejects the flip (%s) while the verifier passed the bundle' % why
    return (bool(new & set(['RTL_VCD_SEMANTICS_REPARSED', 'RTL_EDGES_REVERIFIED']))), \
        'named by %s (parser said %s)' % (' '.join(sorted(new)) or '-', why or 'accepted')


def digest_vcd(path, table, case_id):
    """re-point every digest that describes this VCD at the tampered bytes, the way a forger would

    The delivered file is LF-normalised, so the simulator's own digest is what the bytes look like with
    CRLF restored. Both layers and the manifest are updated: after this, no hash mismatch is left to
    blame, and only a verifier that reads the transitions semantically can catch the break.
    """
    blob = io.open(path, 'rb').read()
    delivered = hashlib.sha256(blob).hexdigest()
    simulator = hashlib.sha256(blob.replace(b'\n', b'\r\n')).hexdigest()
    for target, column, value in ((table, 'new_vcd_sha256', simulator),
                                  (os.path.join(os.path.dirname(table), 'rtl_reverify_delivery.csv'),
                                   'delivered_sha256', delivered),
                                  (os.path.join(os.path.dirname(table), 'rtl_reverify_delivery.csv'),
                                   'simulator_sha256', simulator),
                                  (os.path.join(os.path.dirname(table), 'rtl_reverify_delivery.csv'),
                                   'delivered_bytes', str(len(blob)))):
        if not os.path.isfile(target):
            continue
        lines = u(io.open(target, encoding='utf-8').read()).split('\n')
        hdr = lines[0].split(',')
        if column not in hdr:
            continue
        idx = hdr.index(column)
        for i, line in enumerate(lines[1:]):
            if not line.strip():
                continue
            cells = line.split(',')
            if cells[hdr.index('case_id')] == case_id:
                cells[idx] = value
                lines[i + 1] = ','.join(cells)
        io.open(target, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))


def probe_c_cal(keep, phase):
    src = newest_bundle(keep)
    dest = tamper_copy(keep, 'c7_cal_off', src)
    n = edit_csv(dest, 'calibration.csv', ['value_A'],
                 lambda r: r['quantity'] == 'OFF_baseline_max_abs_A', {'value_A': '1.000000e-07'})
    EC.reseal(dest)
    new = set(EC.check_dir(dest)['failures'])
    named = new & set(['CALIBRATION_OFF_BASELINE_SAMPLES', 'CALIBRATION_SAMPLES_RECOMPUTED',
                       'CALIBRATION_BANDS_FROM_SAMPLES'])
    if phase == 'reproduce':
        return (n == 1 and not named), 'the OFF baseline was set to 100 nA while the bundle ships no ' \
                                       'samples for 1.5..1.9 us, and the checker still claimed a ' \
                                       're-derivation'
    return (n == 1 and bool(named)), 'named by %s' % ' '.join(sorted(new - set(['BUDGET_RESPECTED'])))


# ------------------------------------------------------------------ driver
NEWEST = ''


def newest_bundle(keep):
    """a published bundle whose only failure is the disclosed historical one

    The current round's package wins outright: replaying a semantic break against an older bundle that
    already fails the same check for a different reason would prove nothing.
    """
    if NEWEST:
        return NEWEST
    for pattern in ('results/evidence/dd1_d7b_r2_*', 'results/evidence/dd1_d7b_r1_*',
                    'results/evidence/dd1_d7b_r11_main'):
        hits = [c for c in sorted(glob.glob(os.path.join(PROJ, pattern)))
                if os.path.isfile(os.path.join(c, 'cases.csv'))]
        if hits:
            return hits[-1]
    return os.path.join(PROJ, 'results', 'evidence', 'dd1_d7b_r11_main')


PROBES = (('A1 ceiling from the file', probe_a1),
          ('A2a reserve occupies', probe_a2_reserve),
          ('A2b seeded history binds', probe_a2_seed),
          ('A2c recovery keeps the cost', probe_a2_recovery),
          ('A3a failed replace keeps the file', probe_a3_flush),
          ('A3b stale writer refused', probe_a3_stale),
          ('B1 deadline left limit', probe_b1_deadline),
          ('B2 complementary phase', probe_b2_phase),
          ('B3 current tolerance and bracketing', probe_b3_units),
          ('C2 off time recomputed', probe_c_off),
          ('C4 complementary time bound', probe_c_deb),
          ('C5 convergence delta_edge', probe_c_edge),
          ('C6 delivered VCD semantics', probe_c_vcd),
          ('C7 CAL OFF and tail samples', probe_c_cal))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase', default='reproduce', choices=('reproduce', 'fixed'))
    ap.add_argument('--bundle', default='')
    ap.add_argument('--keep', default='')
    opts = ap.parse_args(argv)
    if opts.bundle:
        globals()['NEWEST'] = os.path.abspath(opts.bundle)
    keep = opts.keep or tempfile.mkdtemp(prefix='d7b-r2-%s-' % opts.phase)
    bad = []
    print('D7B_R2_GUARDS phase=%s base=%s scratch=%s'
          % (opts.phase, newest_bundle(keep), keep))
    for name, fn in PROBES:
        try:
            ok, detail = fn(keep, opts.phase)
        except Exception as exc:
            ok, detail = False, 'probe crashed: %s: %s' % (type(exc).__name__, u(str(exc))[:200])
        print('%-42s %-4s %s' % (name, 'HIT' if ok else 'MISS', detail))
        if not ok:
            bad.append(name)
    print('D7B_R2_GUARDS: %s (%d probes, %d %s)'
          % ('PASS' if not bad else 'FAIL', len(PROBES), len(bad),
             'not reproduced' if opts.phase == 'reproduce' else 'still open'))
    if bad:
        print('D7B_R2_GUARDS_%s %s' % ('UNCLOSED' if opts.phase == 'fixed' else 'NOT_REPRODUCED',
                                       '; '.join(bad)))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
