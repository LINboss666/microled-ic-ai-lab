#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DATA-7B-R3: the illegal-account-state finding, reproduced on base bytes and then closed

TASK_DATA7B_R3 section 2.1 asks for one thing on the code side: a state that the account protocol
does not define must be refused rather than billed as zero. Section 4 requires the same assertions to
be run over the base bytes first and over the repaired tools second, so this suite takes the tool
directory as an argument and never mixes the two:

    python scripts/dd1_d7b_r3_guards.py --phase fixed
    git -C <worktree> archive <base> scripts | tar -x -C <tmp>
    python scripts/dd1_d7b_r3_guards.py --phase reproduce --scripts-dir <tmp>/scripts

Every probe works on disposable files under a temporary directory. Nothing here starts Spectre,
touches a guest, runs Icarus or opens a socket, and the published bundles are only ever read or
copied: the counterfeit probes never edit the real evidence directory.
"""
from __future__ import print_function

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
BUNDLE_REL = os.path.join('results', 'evidence', 'dd1_d7b_r2_r20261022_160652_e880be')
CEILING = 56
LEGAL = ('REQUESTED', 'UNCERTAIN', 'CONFIRMED', 'COMPLETED', 'REFUSED_NO_LAUNCH')
R = None
EC = None


def u(text):
    return text if isinstance(text, str) else text.decode('utf-8', 'replace')


def sha(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()


def load_tools(scripts_dir):
    """import exactly one version of the tools, so a reproduce run cannot see the repaired files"""
    global R, EC
    sys.path.insert(0, scripts_dir)
    for name in ('dd1_d7b_run', 'dd1_d7b_evidence_check', 'dd1_d7b_measure', 'dd1_d7b_trace'):
        if name in sys.modules:
            del sys.modules[name]
    import dd1_d7b_evidence_check as ec_mod                # noqa: F401,E402
    import dd1_d7b_run as r_mod                            # noqa: F401,E402
    R, EC = r_mod, ec_mod


def account_rows(n, state='CONFIRMED', ceiling=CEILING, start=1):
    hdr = R.Account.HDR
    rows = []
    for i in range(n):
        row = dict((k, '') for k in hdr)
        row['launch_id'] = 'H%03d' % (start + i)
        row['task_id'] = R.TASK_ID
        row['run_id'] = 'r11_main'
        row['case_id'] = '(per-directory record)'
        row['role'] = 'dut'
        row['state'] = state
        row['launch_evidence'] = 'reconcile_log_count'
        row['ceiling'] = str(ceiling)
        rows.append(row)
    return rows


def write_account(path, rows):
    hdr = R.Account.HDR
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(','.join(hdr) + '\n')
        for r in rows:
            f.write(','.join(str(r.get(k, '')) for k in hdr) + '\n')


def read_lines(path):
    return u(io.open(path, encoding='utf-8', newline='').read()).split('\n')


def set_state_of_first_row(path, state):
    """rewrite only the state cell of the first data row, leaving every other byte alone"""
    hdr = R.Account.HDR
    lines = read_lines(path)
    for i in range(1, len(lines)):
        if not lines[i].strip():
            continue
        cells = lines[i].split(',')
        cells[hdr.index('state')] = state
        lines[i] = ','.join(cells)
        break
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))


def reopen_refused(path, ceiling, seed_rows):
    """open an Account and report the refusal instead of the counts"""
    try:
        acct = R.Account(path, ceiling, {'origin': 'synthetic seed', 'rows': seed_rows})
    except RuntimeError as exc:
        return False, u(str(exc))[:160]
    return True, acct.counts()


# ------------------------------------------------------------------ probes
def probe_state_rejected(state, keep, phase, label):
    """an unknown or empty state must be refused on read, with the file bytes untouched"""
    path = os.path.join(keep, 'state_%s.csv' % label)
    write_account(path, account_rows(1))
    set_state_of_first_row(path, state)
    before = sha(path)
    accepted, detail = reopen_refused(path, 1, [])
    after = sha(path)
    rows_left = len([l for l in read_lines(path) if l.strip()])
    bytes_kept = (before == after)
    if phase == 'reproduce':
        # the base build opens it, drops the row out of every billing branch and keeps going, and
        # because it gets that far it also rewrites the file -- both are the defect
        counts = detail if accepted else None
        occupied = counts.get('occupied') if isinstance(counts, dict) else None
        return (accepted and occupied == 0), \
            'state %r reopened the account and reported occupied=%s of 1, so the reserved launch ' \
            'stopped costing the ceiling without anybody deciding it' % (state, occupied)
    return ((not accepted) and bytes_kept and rows_left == 2), \
        'state %r refused: %s ; account bytes unchanged (%s) and the row is still there (%d lines ' \
        'with the header)' % (state, detail, before[:12], rows_left)


def probe_in_memory_injection(keep, phase):
    """a legal object whose row is corrupted in memory may not bill or reserve"""
    path = os.path.join(keep, 'inject.csv')
    write_account(path, account_rows(1))
    acct = R.Account(path, 2, {'origin': 'synthetic seed', 'rows': []})
    counts_before = acct.counts()['occupied']
    acct.rows[0]['state'] = 'NOT_A_STATE'
    counts_refused = reserved_refused = False
    counts_error = reserve_error = ''
    try:
        acct.counts()
    except Exception as exc:
        counts_refused = True
        counts_error = '%s: %s' % (type(exc).__name__, u(str(exc))[:100])
    try:
        acct.reserve('SYN', 'dut', 'd', 'p', 'synthetic')
    except Exception as exc:
        reserved_refused = True
        reserve_error = '%s: %s' % (type(exc).__name__, u(str(exc))[:100])
    if phase == 'reproduce':
        return (not counts_refused and not reserved_refused), \
            'occupied was %d before the injection; after rewriting the row in memory to NOT_A_STATE ' \
            'counts() still answered %s and reserve() still wrote a row' % (
                counts_before, str(acct.counts())[:90])
    return (counts_refused and reserved_refused), 'counts(): %s ; reserve(): %s' % (
        counts_error, reserve_error)


def probe_legal_states_keep_billing(keep, phase):
    """the five legal states must still mean exactly what DATA-7B-R2 made them mean"""
    out = {}
    path = os.path.join(keep, 'legal.csv')
    write_account(path, account_rows(CEILING - 1))
    acct = R.Account(path, CEILING, {'origin': 'synthetic seed', 'rows': []})
    out['requested_occupies'] = (acct.counts()['occupied'] == CEILING - 1)
    row = acct.reserve('SYN', 'dut', 'd', 'p', 'synthetic')
    out['reserve_to_ceiling'] = (acct.counts()['occupied'] == CEILING)
    refused = False
    try:
        acct.reserve('SYN', 'dut', 'd', 'p', 'synthetic')
    except R.OverBudget:
        refused = True
    out['over_ceiling_refused'] = refused
    path2 = os.path.join(keep, 'legal2.csv')
    write_account(path2, account_rows(3) + account_rows(1, state='UNCERTAIN', start=4)
                  + account_rows(1, state='COMPLETED', start=5)
                  + account_rows(2, state='REFUSED_NO_LAUNCH', start=6))
    a2 = R.Account(path2, CEILING, {'origin': 'synthetic seed', 'rows': []})
    c = a2.counts()
    # 3 CONFIRMED + 1 COMPLETED + 1 UNCERTAIN occupy; 2 REFUSED rows are free; the recovered
    # REQUESTED row (none here) would occupy too
    out['mixed_billing'] = (c['occupied'] == 5 and c['confirmed'] == 4 and c['uncertain'] == 1
                           and c['no_launch'] == 2 and c['pending'] == 0)
    path3 = os.path.join(keep, 'legal3.csv')
    write_account(path3, account_rows(1, state='REQUESTED'))
    a3 = R.Account(path3, CEILING, {'origin': 'synthetic seed', 'rows': []})
    c3 = a3.counts()
    out['crash_recovery_still_occupies'] = (c3['uncertain'] == 1 and c3['occupied'] == 1)
    ok = all(out.values())
    return ok, ' '.join('%s=%s' % (k, 'yes' if v else 'NO') for k, v in sorted(out.items()))


def probe_real_bundle(keep, phase):
    """the frozen R2 evidence must gain one passing check and lose nothing"""
    ev = os.path.join(PROJ, BUNDLE_REL)
    res = EC.check_dir(ev)
    failures = sorted(set(res['failures']))
    states = [c for c in res['checks'] if c[0] == 'ACCOUNT_STATES_VALID']
    if phase == 'reproduce':
        # the base checker must really have read the bundle -- an unreadable run would look like
        # "no state check" for the wrong reason
        return (not states and len(res['checks']) >= 40 and failures == ['BUDGET_RESPECTED']), \
            'the base checker runs %d checks and none of them enumerates the account states: ' \
            'failures=%s' % (len(res['checks']), ' '.join(failures) or '-')
    return (len(states) == 1 and states[0][1] == 'PASS' and failures == ['BUDGET_RESPECTED']
            and len(res['checks']) == 44), \
        '%d checks, ACCOUNT_STATES_VALID=%s, failures=%s (%s)' % (
            len(res['checks']), states[0][1] if states else 'ABSENT', ' '.join(failures),
            states[0][2][:80] if states else '-')


def probe_counterfeit(state, keep, phase, label):
    """a forged copy whose roll-up counts and manifest agree must still be caught"""
    src = os.path.join(PROJ, BUNDLE_REL)
    dest = os.path.join(keep, 'counterfeit_%s' % label)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    path = os.path.join(dest, 'launch_account.csv')
    lines = read_lines(path)
    hdr = R.Account.HDR
    changed = None
    for i in range(1, len(lines)):
        if not lines[i].strip():
            continue
        cells = lines[i].split(',')
        if cells[hdr.index('state')] == 'REFUSED_NO_LAUNCH':
            changed = (cells[hdr.index('launch_id')], cells[hdr.index('case_id')])
            cells[hdr.index('state')] = state
            lines[i] = ','.join(cells)
            break
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    env_path = os.path.join(dest, 'environment.json')
    env = json.loads(u(io.open(env_path, encoding='utf-8').read()))
    env['launch_account']['no_launch'] = env['launch_account']['no_launch'] - 1
    with io.open(env_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(env, indent=1, sort_keys=True) + '\n')
    EC.reseal(dest)
    base = set(EC.check_dir(src)['failures'])
    got = EC.check_dir(dest)
    new = sorted(set(got['failures']) - base)
    named = [n for n in new if n in ('ACCOUNT_STATES_VALID',)]
    if phase == 'reproduce':
        return (not new), 'A001 (%s) set to %r and the roll-up count synced from 274 to 273, ' \
                          'manifest re-sealed: the checker added no failure at all' % (
                              changed[0], state)
    return (new == named), 'new failures = %s (expected exactly ACCOUNT_STATES_VALID); reason: %s' % (
        ' '.join(new) or '-', [c[2] for c in got['checks'] if c[0] == 'ACCOUNT_STATES_VALID']
        [:1] or '-')


def probe_native_entry_closed(keep, phase):
    """R3 must not have reopened the production launch entry while touching the account"""
    saved = dict(os.environ)
    results = []
    try:
        for combo in ({'RUN': '1', 'QODER_SIM_AUTHORISED': '1'},
                     {'RUN': '1', 'QODER_SIM_AUTHORISED': '0'},
                     {'RUN': '0', 'QODER_SIM_AUTHORISED': '1'},
                     {}):
            os.environ.clear()
            os.environ.update(saved)
            os.environ.update(combo)
            results.append((combo, R.authorisation_problem()))
    finally:
        os.environ.clear()
        os.environ.update(saved)
    closed = all(problem for _combo, problem in results)
    return closed, 'four environment combinations, entry refused in each: %s' % ' | '.join(
        '%s->%s' % (','.join('%s=%s' % kv for kv in sorted(c.items())) or 'no vars',
                    str(p)[:40]) for c, p in results)


PROBES = (('S1 unknown state refused on read', lambda k, p: probe_state_rejected(
    'UNRECOGNISED_STATE', k, p, 'unknown')),
    ('S2 empty state refused on read', lambda k, p: probe_state_rejected('', k, p, 'empty')),
    ('S3 injected memory state not billable', probe_in_memory_injection),
    ('S4 five legal states keep their billing', probe_legal_states_keep_billing),
    ('S5 real R2 bundle: 44 checks, states PASS', probe_real_bundle),
    ('S6 counterfeit unknown state named', lambda k, p: probe_counterfeit(
        'UNRECOGNISED_STATE', k, p, 'unknown')),
    ('S7 counterfeit empty state named', lambda k, p: probe_counterfeit('', k, p, 'empty')),
    ('S8 native entry still closed in 4 combinations', probe_native_entry_closed))


def main(argv=None):
    global PROJ
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase', default='fixed', choices=('reproduce', 'fixed'))
    ap.add_argument('--scripts-dir', default=HERE, help='which version of the tools to judge')
    ap.add_argument('--repo', default=PROJ, help='worktree holding the frozen R2 evidence')
    opts = ap.parse_args(argv)
    PROJ = os.path.abspath(opts.repo)
    load_tools(os.path.abspath(opts.scripts_dir))
    keep = tempfile.mkdtemp(prefix='d7b-r3-guards-%s-' % opts.phase)
    print('D7B_R3_GUARDS phase=%s tools=%s repo=%s scratch=%s'
          % (opts.phase, os.path.abspath(opts.scripts_dir), PROJ, keep))
    print('D7B_R3_GUARDS tools_version account_states=%s' %
          '|'.join(getattr(R, 'ACCOUNT_STATES', ('<none in this version>',))))
    problems = []
    hits = 0
    try:
        for name, fn in PROBES:
            try:
                ok, detail = fn(keep, opts.phase)
            except Exception as exc:
                ok, detail = False, 'probe raised %s: %s' % (type(exc).__name__, u(str(exc))[:160])
            hits += 1 if ok else 0
            if not ok:
                problems.append(name)
            print('%-46s %s  %s' % (name, 'HIT ' if ok else 'MISS', u(str(detail))[:220]))
    finally:
        shutil.rmtree(keep, ignore_errors=True)
    print('D7B_R3_GUARDS: %s (%d probes, %d %s)'
          % ('PASS' if not problems else 'FAIL', len(PROBES), len(problems),
             'still open' if opts.phase == 'fixed' else 'not reproduced'))
    for p in problems:
        print('D7B_R3_GUARDS_%s %s' % ('UNCLOSED' if opts.phase == 'fixed' else 'NOT_REPRODUCED', p))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
