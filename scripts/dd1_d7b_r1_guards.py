# -*- coding: utf-8 -*-
"""DATA-7B-R1 execution guards: the mock proof that the entry points cannot spend a launch.

    python scripts/dd1_d7b_r1_guards.py

Nothing here starts a simulator, opens a socket or reads a PDK. Every remote call goes through
`FakeLink`, which records what was asked and can be told to raise the moment anything is attempted.
The launch account used by the loop tests is a synthetic one in a temporary directory, so the real
59-process history is never spent, cleared or imitated; the history-seeded refusal is tested by
reading the delivered reconcile table, which is never written to.

Each group names the defect from REVIEW_DATA7B.md it closes:

  A1  no mode, ambiguous mode and missing authorisation must not reach native preparation;
  A2  re-opening a ledger must not zero the count or drop history; the ceiling is cumulative across
      run ids, across processes and across a crash; a literal-percent run id and an existing evidence
      directory are refused;
  A3  reuse must split before any preflight or DUT launch and must be byte-verified, and publish must
      run the full semantic check first;
  3.1 the boundaries 55/56/59, the rail preflight's own inner launch, refused launches, lost contact.

The synthetic native pass is written in exactly the layout the real runner produces (mirrored psf,
transcript with the printed guest paths, delivered ledger and case table), because a fixture that
only the test understands would prove nothing about the reuse path.
"""
from __future__ import print_function

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_run as R

NS = 1000
u = R.u
CASE_VERDICT = R.CASE_HDR.index('verdict')
CASE_REASONS = R.CASE_HDR.index('reasons')
CAL_ID = 'D7B-CAL'
LIVE_ID = 'D7B-P30-C000'          # a black code: one window, no conducting pulse
REUSED_ID = 'D7B-P30-C002'


class RemoteAttempt(Exception):
    """raised by a fake that is not supposed to be reached at all"""


class FakeLink(object):
    """records every remote call and answers it with the smallest text the code accepts"""

    made = []

    def __init__(self, host, root, log_dir, fail_at=None):
        self.host = host
        self.root = root
        self.log_dir = log_dir
        self.seq = 0
        self.calls = []
        self.fail_at = fail_at
        FakeLink.made.append(self)

    def _touch(self, label):
        self.seq += 1
        self.calls.append(label)
        if self.fail_at and label.startswith(self.fail_at):
            raise IOError('ssh: connection closed by remote host (%s)' % label)

    def run(self, script, timeout=900, label='cmd'):
        self._touch(label)
        case = label.split('-', 1)[1] if '-' in label else ''
        if label.startswith('preflight'):
            return 0, 'TESTBENCH_PREFLIGHT: PASS\nspectre_rc=0\nSUPPLY_RESULT PASS\n'
        if label.startswith('dut'):
            datafile = '%s/cases/%s/sim/%s.raw/sw1.tran.tran' % (self.root, case, case)
            logfile = '%s/cases/%s/sim/%s.log' % (self.root, case, case)
            return 0, ('SPECTRE name=%s.scs rc=0\nCHECK datafile=\'%s\'\nLOGFILE %s\n'
                       'CHECK done_line=\'0 errors\'\nCHECK error_hits=0\n'
                       % (case, datafile, logfile))
        if label.startswith('n2'):
            return 7, ('PREFLIGHT_STAGE=supply_contract\n   SUPPLY_FAIL net vss has no source\n'
                       'TESTBENCH_PREFLIGHT: FAIL\n')
        return 0, 'OK\n'

    def push(self, local, remote, label='push'):
        self._touch(label)
        return R.sha_file(local)

    def pull(self, remote, local):
        self._touch('pull')
        d = os.path.dirname(local)
        if not os.path.isdir(d):
            os.makedirs(d)
        write_text(local, psf_content(local))
        return R.sha_file(local)


class Boom(object):
    """a stand-in that reports the moment the code path touches it"""

    def __init__(self, what):
        self.what = what

    def __call__(self, *a, **k):
        raise RemoteAttempt('%s was reached' % self.what)

    def __getattr__(self, name):
        raise RemoteAttempt('%s.%s was reached' % (self.what, name))


# ---------------------------------------------------------------- synthetic native bytes
def psf_content(dst):
    """the bytes a mirrored pull of that name should bring back"""
    if 'CAL' in os.path.basename(dst):
        return synth_psf(synth_cal_samples())
    return synth_psf(synth_dut_samples())


def synth_cal_samples():
    """0..4.5 us at 10 ns: OFF before 2 us, 15 uA through the band, off again after 4 us"""
    rows = []
    t = 0.0
    while t <= 4.5e-6 + 1e-15:
        on = 2.0e-6 <= t <= 4.0e-6
        rows.append((t, 15e-6 if on else 1e-13, 1.8 if on else 0.0))
        t += 10e-9
    return rows


def synth_dut_samples():
    """the analog-domain pulse: data_en high from 2.5 us to 2.53 us, 15 uA while it is"""
    rows = []
    t = 2.45e-6
    while t <= 2.75e-6 + 1e-15:
        on = 2.5e-6 <= t < 2.53e-6
        rows.append((t, 15e-6 if on else 1e-13, 1.8 if on else 0.0))
        t += 1e-9
    return rows


def synth_psf(rows):
    head = ['HEADER', '"PSFversion" "1.00"', '"simulator" "spectre"',
            '"analysis type" "tran"', '"analysis name" "sw1"', '"temp" 27.0000', 'SWEEP',
            '"time" "sweep" PROP(', '"units" "s"', ')', 'TRACE', '"Ip_out:i" "A"',
            '"data_en" "V"', 'VALUE']
    for t, i, de in rows:
        head.append('"time" %.15e' % t)
        head.append('"Ip_out:i" %.15e' % i)
        head.append('"data_en" %.15e' % de)
    head.append('END')
    return '\n'.join(head) + '\n'


def write_text(path, text):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return path


def deck_text(points, cid, vdd='1.8'):
    wave = ' '.join('%dn %g' % (int(t // NS), v) for t, v in points)
    stop = points[-1][0] + R.STOP_MARGIN_NS * NS
    return ('simulator lang=spectre insensitive=yes\n'
            '// synthetic guard deck for %s\n'
            'include "${QODER_PDK_LIB}" section=tt\n'
            'simopt options temp=27\n'
            'Iref (0 iref_in) isource dc=15u\n'
            'Vcas (vcas 0) vsource dc=1.8\n'
            'V18 (vdd18 0) vsource dc=%s\n'
            'Vss (vss 0) vsource dc=0\n'
            'Vclamp (clamp 0) vsource dc=1.2\n'
            'Vde (data_en 0) vsource type=pwl wave=[%s]\n'
            'Xstage (data_en iref_in vcas data_out vdd18 vss) dd1_d7b_pwm_stage\n'
            'Ip_out (clamp data_out) iprobe\n'
            'sw1 tran stop=%.6e maxstep=5e-10 method=gear2only\n'
            'save data_en Ip_out:i\n' % (cid, vdd, wave, stop * 1e-12))


def synth_window(cid, window='normal', t0=0, t1=30000, tick='30', intervals='1',
                 segments=None):
    if segments is None:
        segments = [[t0, t1]] if float(intervals) > 0 else []
    stop = t1 + R.TAIL_NS * NS
    pts = [(0, 0.0), (t0, 0.0), (t0 + NS, 1.8), (t1, 1.8), (t1 + NS, 0.0), (stop, 0.0)]
    return {'window': window, 'seq': 1, 'role': 'normal', 'mode': 'PURE', 'code': '2',
            'pam_request': 'NONE', 'tick_ns': tick, 'window_ns': str((t1 - t0) // NS),
            'full_intervals': str(int((t1 - t0) / (int(tick) * NS))),
            'expected_intervals': intervals, 'expected_conducting_ns': '30',
            'expected_pulses': str(len(segments)), 't0_ps': t0, 't1_ps': t1,
            'accepted_ticks_in_window': '1', 'expected_accepted_ticks': '1',
            'first_tick_ps': t0, 'tick_lead_ps': 5, 'segments_ps': segments,
            'conducted_ps': str(sum(s[1] - s[0] for s in segments)), 't_stop_ps': stop,
            'pwl_points': pts,
            'pwl_sha256': R.sha_txt('\n'.join('%d %.6g' % (t, v) for t, v in pts))}


def synth_doc(cid, window):
    return {'facts': {'vcd': 'synthetic.vcd', 'vcd_sha256': 'syntheticvcdsha256',
                      'header': 0, 'end_ps': 2000000, 'tick_lead_ps': 5,
                      'tick_count': 1,
                      'data_en_edges': [(window['t0_ps'] + NS, 1), (window['t1_ps'] + NS, 0)]},
            'shift_ps': R.SHIFT_NS * NS, 'windows': [window],
            'case_id': cid}


def synth_case(cid, role='normal', windows='normal'):
    return {'case_id': cid, 'group': 'synthetic', 'trace_case': cid, 'windows': windows,
            'maxstep_ns': '0.5', 'ramp_ns': '2', 'vclamp_v': '1.2', 'reuse_of': 'NONE',
            'role': role, 'note': 'synthetic guard case'}


def synth_deck(cid, points):
    deck = deck_text(points, cid)
    return {'deck': deck, 'points': points, 'stop_ps': points[-1][0],
            'deck_sha256': R.sha_txt(deck), 'pwl_sha256': R.sha_txt(R.pwl_text(points))}


def build_synthetic_run(stage, published, decks, docs, mst, ids, run_name='r_synth'):
    """one synthetic native pass, in the layout the real runner produces

    `stage` holds the mirrored psf and log, the transcripts naming the guest paths, the PWL, the deck
    and the masters; `published` holds the ledger and case table that name those same digests. No
    byte of the delivered round is copied here, so a fixture bug cannot be mistaken for history.
    """
    for sub in ('transcripts', 'pwl', 'masters', 'decks'):
        p = os.path.join(stage, sub)
        if not os.path.isdir(p):
            os.makedirs(p)
    for m in mst:
        write_text(os.path.join(stage, 'masters', m['name']), u(m['text']))
    if not os.path.isdir(published):
        os.makedirs(published)
    led_rows, case_rows = [], []
    root = '%s/%s' % (R.GUEST_ROOT, run_name)
    for i, cid in enumerate(ids):
        deck = u(decks[cid]['deck'])
        points = decks[cid]['points']
        base = os.path.join(stage, 'mirror', 'cases', cid)
        psf = os.path.join(base, 'sim', '%s.raw' % cid, 'sw1.tran.tran')
        rows = (synth_cal_samples() if cid == CAL_ID else synth_dut_samples())
        write_text(psf, synth_psf(rows))
        log = os.path.join(base, 'sim', '%s.log' % cid)
        write_text(log, 'simulation temp = 27 C\nsection=tt\n')
        write_text(os.path.join(base, '%s.scs' % cid), deck)
        write_text(os.path.join(stage, 'pwl', '%s_pwl.txt' % cid), R.pwl_text(points))
        write_text(os.path.join(stage, 'decks', cid, '%s.scs' % cid), deck)
        write_text(os.path.join(stage, 'transcripts', 'guest_%03d_dut-%s.txt' % (i * 3 + 3, cid)),
                   ('ssh payload\nSPECTRE name=%s.scs rc=0\n'
                    'CHECK datafile=\'%s/cases/%s/sim/%s.raw/sw1.tran.tran\'\n'
                    'LOGFILE %s/cases/%s/sim/%s.log\nCHECK done_line=\'0 errors\'\n'
                    'CHECK error_hits=0\n' % (cid, root, cid, cid, root, cid, cid)))
        write_text(os.path.join(stage, 'transcripts', 'guest_%03d_preflight-%s.txt'
                                % (i * 3 + 2, cid)),
                   'TESTBENCH_PREFLIGHT: PASS\nspectre_rc=0\n')
        led_rows.append(['%s/L%03d' % (run_name, i * 2 + 1), cid, 'preflight', 'DONE', '', '', '0',
                         'NO_SPECTRE_LINE', R.sha_txt(deck), R.sha_txt(R.pwl_text(points)), '', '',
                         '', '1'])
        led_rows.append(['%s/L%03d' % (run_name, i * 2 + 2), cid, 'dut', 'DONE', '', '', '0',
                         'SPECTRE_name=%s.scs_rc=0' % cid, R.sha_txt(deck),
                         R.sha_txt(R.pwl_text(points)), R.sha_file(psf), R.sha_file(log), '', '1'])
        case_rows.append(['%s' % run_name, 'L%03d' % (i * 2 + 2), cid, R.sha_txt(deck),
                          R.sha_txt(R.pwl_text(points)),
                          (docs[cid]['facts']['vcd_sha256'] if cid in docs else 'bench'),
                          R.sha_file(psf), R.sha_file(log), 'tt', '27.0000'])
    write_text(os.path.join(published, 'process_ledger.csv'),
               ','.join(R.Ledger.HDR) + '\n' + ''.join(','.join(r) + '\n' for r in led_rows))
    write_text(os.path.join(published, 'cases.csv'),
               ','.join(['run_id', 'launch_id', 'case_id', 'deck_sha256', 'pwl_sha256',
                         'trace_sha256', 'raw_sha256', 'log_sha256', 'section_read',
                         'temp_read']) + '\n'
               + ''.join(','.join(r) + '\n' for r in case_rows))
    write_text(os.path.join(published, 'negative.csv'),
               'run_id,case_id,kind,detected,rc,stage,supply_fail,spectre_launches,deck_sha256,'
               'verdict\n%s,D7B-N2,static_supply_negative,YES,7,supply_contract,net vss has no '
               'source,0,%s,EXPECTED_REFUSAL / SUPPLY_CONTRACT_DETECTED\n'
               % (run_name, R.sha_txt('n2')))
    return stage, published


# ---------------------------------------------------------------- fixtures for reuse only
def reuse_fixture(temp):
    mst = [{'name': 'm.scs', 'text': 'subckt x\n', 'removed': [], 'repo_sha256': 'r',
            'sent_sha256': R.sha_txt('subckt x\n'), 'bytes_sent': 8, 'bytes_repo': 9}]
    points = [(0, 0.0), (2500000, 0.0), (2501000, 1.8), (2530000, 1.8), (2531000, 0.0),
              (2730000, 0.0), (2780000, 0.0)]
    decks = {REUSED_ID: synth_deck(REUSED_ID, points)}
    docs = {REUSED_ID: synth_doc(REUSED_ID, synth_window(REUSED_ID))}
    stage = os.path.join(temp, 'stage')
    published = os.path.join(temp, 'published')
    build_synthetic_run(stage, published, decks, docs, mst, [REUSED_ID])
    return mst, decks, docs, stage, published, points


def opts(reuse='', n2='', publish=False, published=None):
    class O(object):
        pass
    o = O()
    o.reuse, o.n2_from, o.cal_from, o.publish = reuse, n2, '', publish
    o.published_dir = published or R.HISTORICAL_EVIDENCE
    o.trace_dir = ''
    o.expect = 24
    return o


# ---------------------------------------------------------------- groups
def group_routing(bad):
    """A1: the entry point decides before it prepares"""
    old_masters, old_link = R.masters, R.Link
    old_env = dict((k, os.environ.get(k)) for k in R.AUTH_VARS)
    temp = tempfile.mkdtemp(prefix='d7b-guards-route-')
    try:
        R.masters = Boom('masters (the native preparation step)')
        R.Link = Boom('Link (the remote channel)')
        trials = [('no_mode', [], {'RUN': '0', 'QODER_SIM_AUTHORISED': '0'}),
                  ('conflict_dry_run', ['--dry', '--run'],
                   {'RUN': '1', 'QODER_SIM_AUTHORISED': '1'}),
                  ('conflict_account_dry', ['--account', '--dry'], {'RUN': '0',
                                                                    'QODER_SIM_AUTHORISED': '0'}),
                  ('run_without_auth', ['--run'], {'RUN': '0', 'QODER_SIM_AUTHORISED': '0'}),
                  ('run_half_auth', ['--run'], {'RUN': '1', 'QODER_SIM_AUTHORISED': '0'}),
                  ('static_probe_without_auth', ['--static-probe'],
                   {'RUN': '0', 'QODER_SIM_AUTHORISED': '0'}),
                  ('supply_negative_without_auth', ['--supply-negative'],
                   {'RUN': '0', 'QODER_SIM_AUTHORISED': '0'}),
                  ('publish_without_mode', ['--publish'],
                   {'RUN': '1', 'QODER_SIM_AUTHORISED': '1'}),
                  ('cal_from_removed', ['--dry', '--cal-from', temp],
                   {'RUN': '0', 'QODER_SIM_AUTHORISED': '0'}),
                  ('reuse_all_but_zero_auth', ['--run', '--reuse', ''],
                   {'RUN': '0', 'QODER_SIM_AUTHORISED': '0'})]
        for name, argv, env in trials:
            os.environ.update(env)
            out = os.path.join(temp, 'out_' + name)
            args = argv + ['--out', out, '--account-file', os.path.join(temp, name + '_acct.csv')]
            try:
                rc = R.main(args)
            except RemoteAttempt as exc:
                bad.append('A1 %s reached the remote path: %s' % (name, exc))
                continue
            finally:
                for k, v in old_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            if rc != 5:
                bad.append('A1 %s returned rc=%s, expected the refusal 5' % (name, rc))
            if os.path.exists(out):
                bad.append('A1 %s created %s before refusing' % (name, out))
        # the delivered state: authorised, but 59 of 56 already occupied
        R.masters = Boom('masters (the native preparation step)')
        os.environ.update({'RUN': '1', 'QODER_SIM_AUTHORISED': '1'})
        out = os.path.join(temp, 'out_history')
        rc = R.main(['--run', '--out', out,
                     '--account-file', os.path.join(temp, 'history_acct.csv'),
                     '--seed-from', R.HISTORICAL_EVIDENCE])
        if rc != 5:
            bad.append('A1 the 59/56 history did not close the native entry (rc=%s)' % rc)
        if os.path.exists(out):
            bad.append('A1 the ceiling refusal still created its staging directory')
    finally:
        R.masters, R.Link = old_masters, old_link
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(temp, ignore_errors=True)


def group_offline(bad):
    """3.2: the offline modes cannot reach the remote channel"""
    temp = tempfile.mkdtemp(prefix='d7b-guards-offline-')
    old_link, old_masters = R.Link, R.masters
    old_env = dict((k, os.environ.get(k)) for k in R.AUTH_VARS)
    try:
        os.environ.update({'RUN': '1', 'QODER_SIM_AUTHORISED': '1'})
        R.Link = Boom('Link (the remote channel)')
        for name, argv in (('remeasure', ['--remeasure', '--only', CAL_ID]),
                           ('dry', ['--dry', '--only', CAL_ID]),
                           ('account', ['--account'])):
            args = argv + ['--out', os.path.join(temp, name),
                           '--account-file', os.path.join(temp, name + '_acct.csv'),
                           '--seed-from', R.HISTORICAL_EVIDENCE]
            try:
                rc = R.main(args)
            except RemoteAttempt as exc:
                bad.append('3.2 --%s reached the remote channel: %s' % (name, exc))
                continue
            if os.path.exists(os.path.join(temp, name, 'evidence')) and name == 'remeasure':
                bad.append('3.2 --%s staged a bundle without any retained bytes' % name)
            print('   offline --%s rc=%s' % (name, rc))
        try:
            rc = R.main(['--check-evidence', os.path.join(temp, 'nowhere')])
        except RemoteAttempt as exc:
            bad.append('3.2 --check-evidence reached the remote channel: %s' % exc)
        if rc == 0:
            bad.append('3.2 --check-evidence on a missing directory returned 0')
    except RemoteAttempt as exc:
        bad.append('3.2 an offline mode reached the remote channel: %s' % exc)
    finally:
        R.Link, R.masters = old_link, old_masters
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(temp, ignore_errors=True)


def group_ledger(bad):
    """A2: reopening a ledger neither forgets the count nor loses a row"""
    temp = tempfile.mkdtemp(prefix='d7b-guards-ledger-')
    try:
        path = os.path.join(temp, 'process_ledger.csv')
        first = R.Ledger(path)
        row = first.begin('SYN-1', 'dut', 'deck', 'pwl')
        first.finish(row, 0, 'SPECTRE name=x.scs rc=0', launched=1)
        if first.used != 1:
            bad.append('A2 the first pass counted %r' % first.used)
        reopened = R.Ledger(path)
        if reopened.used != 1:
            bad.append('A2 reopening reset the launch count to %r' % reopened.used)
        if not any(r['case_id'] == 'SYN-1' for r in reopened.rows):
            bad.append('A2 reopening lost the historical row')
        before = io.open(path, encoding='utf-8').read()
        again = R.Ledger(path)
        again.begin('SYN-2', 'preflight', 'deck', 'pwl')
        after = io.open(path, encoding='utf-8').read()
        if not after.startswith(before):
            bad.append('A2 a second pass rewrote the rows it inherited')
        two = io.open(path, encoding='utf-8').read().splitlines(True)
        if not any('L002' in l for l in two):
            bad.append('A2 the second pass did not add a row to the file it inherited')
        write_text(path, ''.join([two[0]] + two[2:]))   # header plus L002: L001 is gone
        refuse(bad, 'A2 a ledger whose first row was stolen',
               lambda: R.Ledger(path).begin('SYN-3', 'dut', 'd', 'p'), RuntimeError)
        write_text(path, 'launch_id,case_id\nL001,X\n')
        try:
            R.Ledger(path)
            bad.append('A2 a ledger with the wrong header was read as if it matched')
        except RuntimeError:
            pass
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def group_account(bad):
    """3.1: the ceiling is cumulative, conservative and blind to the run id"""
    temp = tempfile.mkdtemp(prefix='d7b-guards-account-')
    try:
        write_reconcile(os.path.join(temp, 'published'), [('runA', 1, 1), ('runB', 2, 2)])
        path = os.path.join(temp, 'account.csv')
        acct = R.Account(path, 56, synth_seed(55))
        if acct.remaining() != 1:
            bad.append('3.1 remaining at 55 of 56 is %r' % acct.remaining())
        row = acct.reserve('SYN-56', 'dut', 'd', 'p', 'r_one')
        acct.settle(row, 0, 'SPECTRE name=x rc=0', 1, 'SPECTRE_name=x_rc=0')
        if acct.remaining() != 0:
            bad.append('3.1 the 56th launch did not exhaust the ceiling')
        refuse(bad, '3.1 a 57th launch at ceiling 56',
               lambda: acct.reserve('SYN-57', 'dut', 'd', 'p', 'r_two'), R.OverBudget)
        again = R.Account(path, 56, synth_seed(55))
        if again.counts()['occupied'] != 56:
            bad.append('3.1 a new process re-counted the ceiling as %r' % again.counts())
        refuse(bad, '3.1 a different run id was given a fresh budget',
               lambda: again.reserve('SYN-58', 'dut', 'd', 'p', 'r_three'), R.OverBudget)
        crashed = R.Account(os.path.join(temp, 'crash.csv'), 5, synth_seed(3))
        crashed.reserve('SYN-C', 'dut', 'd', 'p', 'r_crash')
        orphan = R.Account(os.path.join(temp, 'crash.csv'), 5, synth_seed(3))
        c = orphan.counts()
        if c['uncertain'] != 1 or c['occupied'] != 4:
            bad.append('3.1 the abandoned launch recovered as %r' % c)
        if c['confirmed'] != 3:
            bad.append('3.1 an uncertain launch was claimed as executed (%r)' % c)
        if orphan.rows[-1]['state'] != 'UNCERTAIN':
            bad.append('3.1 recovery left the row as %s' % orphan.rows[-1]['state'])
        pf = R.Account(os.path.join(temp, 'pf.csv'), 5, synth_seed(0))
        row = pf.reserve('SYN-P', 'preflight', 'd', 'p', 'r_pf')
        launched, evidence = R.launch_evidence_of('spectre_rc=0\n')
        pf.settle(row, 0, 'spectre_rc=0', launched, evidence)
        if pf.counts()['confirmed'] != 1 or evidence != 'PREFLIGHT_INNER_spectre_rc_seen':
            bad.append('3.1 the rail preflight inner launch accounted as %r / %s'
                       % (pf.counts(), evidence))
        row = pf.reserve('SYN-S', 'static_probe', 'd', 'p', 'r_sp')
        launched, evidence = R.launch_evidence_of('PREFLIGHT_STAGE=supply_contract\n')
        pf.settle(row, 7, 'PREFLIGHT_STAGE=supply_contract', launched, evidence)
        if pf.counts()['confirmed'] != 1:
            bad.append('3.1 a zero-launch refusal was counted as a launch (%r)' % pf.counts())
        hist = R.Account(os.path.join(temp, 'hist.csv'), R.LAUNCH_BUDGET,
                         R.seed_account_rows(R.HISTORICAL_EVIDENCE))
        c = hist.counts()
        if c['confirmed'] != 59 or c['occupied'] != 59:
            bad.append('3.1 the delivered history seeded as %r' % c)
        if hist.remaining() >= 0:
            bad.append('3.1 the 59/56 history still leaves room for a launch')
        refuse(bad, '3.1 the native entry accepted a launch on top of the 59/56 history',
               lambda: hist.reserve('SYN-N', 'dut', 'd', 'p', 'r_hist'), R.OverBudget)
        rebuilt = R.Account(os.path.join(temp, 'hist_rebuilt.csv'), R.LAUNCH_BUDGET,
                            R.seed_account_rows(R.HISTORICAL_EVIDENCE))
        if rebuilt.counts()['confirmed'] != 59:
            bad.append('3.1 rebuilding from the reconcile table gave %r' % rebuilt.counts())
        hist_path = os.path.join(temp, 'hist.csv')
        keep = io.open(hist_path, encoding='utf-8').read().splitlines(True)
        write_text(hist_path, ''.join(keep[:1] + keep[2:]))     # the first seeded row is gone
        refuse(bad, '3.1 an account that lost its seeded rows',
               lambda: R.Account(hist_path, R.LAUNCH_BUDGET,
                                 R.seed_account_rows(R.HISTORICAL_EVIDENCE)), RuntimeError)
        bad_recon = write_reconcile(os.path.join(temp, 'bad'), [('runA', 1, 1)], total=9)
        refuse(bad, '3.1 a reconcile TOTAL the rows contradict',
               lambda: R.seed_account_rows(bad_recon), RuntimeError)
        roles = {}
        for r in R.seed_account_rows(R.HISTORICAL_EVIDENCE)['rows']:
            roles[r['role']] = roles.get(r['role'], 0) + 1
        if roles != {'preflight': 30, 'dut': 29}:
            bad.append('3.1 the seeded role split is %r, expected 30 preflight and 29 dut' % roles)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def refuse(bad, name, fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception as e:
        bad.append('%s: raised %s instead of %s' % (name, type(e).__name__, exc.__name__))
        return False
    bad.append('%s was accepted' % name)
    return False


def synth_seed(n):
    rows = []
    for i in range(n):
        rows.append({'launch_id': 'H%03d' % (i + 1), 'task_id': 'DATA-7B', 'run_id': 'synthetic',
                     'case_id': 'SYN-%03d' % (i + 1), 'role': 'dut', 'state': 'CONFIRMED',
                     'requested_utc': '', 'ended_utc': '', 'rc': '',
                     'launch_evidence': 'synthetic_fixture', 'deck_sha256': '', 'pwl_sha256': '',
                     'raw_sha256': '', 'log_sha256': '', 'refusal': ''})
    return {'origin': 'synthetic fixture (%d confirmed)' % n, 'rows': rows}


def write_reconcile(dir_path, per_dir, total=None):
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)
    total = sum(n for _p, _d, n in per_dir) if total is None else total
    lines = ['task_root_dir,preflight_logs,total_logs,dut_logs,in_delivered_set,'
             'processes_counted_against_ceiling,note']
    for name, pre, n in per_dir:
        lines.append('%s,%d,%d,%d,no,%d,synthetic fixture' % (name, pre, n, n - pre, n))
    lines.append('TOTAL,%d,%d,%d,,%d,synthetic fixture'
                 % (sum(p for _n, p, _c in per_dir), total,
                    sum(c for _n, _p, c in per_dir), total))
    write_text(os.path.join(dir_path, 'launches_reconcile.csv'), '\n'.join(lines) + '\n')
    return dir_path


def group_loop(bad):
    """3.1/A3: the loop stops at the ceiling, keeps its accounting on failure, and reuses first"""
    temp = tempfile.mkdtemp(prefix='d7b-guards-loop-')
    old_link, old_prepare, old_static = R.Link, R.prepare, R.static_gates
    try:
        mst, decks, docs, stage, published, points = reuse_fixture(temp)
        decks[CAL_ID] = synth_deck(CAL_ID, [(0, 0.0), (1999000, 0.0), (2001000, 1.8),
                                            (3999000, 1.8), (4001000, 0.0), (4500000, 0.0),
                                            (4550000, 0.0)])
        decks[LIVE_ID] = synth_deck(LIVE_ID, points)
        # the two-case pass is a second, separate native run: adding it to the first stage would
        # leave two transcripts naming two passes for the same case, which is what A3 must refuse
        stage2 = os.path.join(temp, 'stage2')
        published2 = os.path.join(temp, 'published2')
        build_synthetic_run(stage2, published2, decks, docs, mst, [CAL_ID, REUSED_ID])
        stage, published = stage2, published2
        cases = [synth_case(CAL_ID, 'calibration', 'cal'), synth_case(REUSED_ID),
                 synth_case(LIVE_ID)]
        out_root = os.path.join(temp, 'stage_root')
        log_dir = os.path.join(out_root, 'transcripts')
        if not os.path.isdir(log_dir):
            os.makedirs(log_dir)
        def fake_prepare(link, m, scratch, logs):
            # the real prepare lands the frozen tools and the masters locally before pushing them;
            # the loop reads those local copies, so the fake has to leave them in place
            for one in m:
                write_text(os.path.join(scratch, 'masters', one['name']), u(one['text']))
            return {'run_spectre.sh': 'sha', 'tb_preflight.sh': 'sha',
                    'sc1_supply_check.awk': 'sha'}
        R.prepare = fake_prepare
        R.static_gates = lambda c, m, d, expect_rows=24: []
        # every remote call in this group goes through the recording fake, and the guest address is
        # pointed at a host that cannot answer, so a forgotten patch shows up as a refusal rather
        # than as traffic
        R.Link = FakeLink
        R.GUEST_HOST = '127.0.0.1'
        R.SSH_COMPAT = ['-oBatchMode=yes', '-oConnectTimeout=1']

        # (1) reuse first: the reused case is never pushed, preflighted or launched
        FakeLink.made = []
        acct = R.Account(os.path.join(temp, 'acct_reuse.csv'), 40, synth_seed(0))
        res = R.native_run(cases[:2], mst, docs, decks,
                           opts(reuse=','.join('%s=%s' % (cid, stage)
                                                for cid in (CAL_ID, REUSED_ID)),
                                published=published),
                           'r_reuse_000000_aaaaaa', out_root, log_dir, acct)
        link = FakeLink.made[-1]
        started = [c for c in link.calls if c.startswith('preflight-') or c.startswith('dut-')]
        if started:
            bad.append('A3 a fully reused pass still started %r' % started)
        if acct.counts()['confirmed'] or res['ledger'].used:
            bad.append('A3 the reused pass spent the ceiling (%r / %d)'
                       % (acct.counts(), res['ledger'].used))
        if not res['rows'] or not all('reused:' in r[CASE_REASONS] for r in res['rows']):
            bad.append('A3 a reused row does not say where its bytes came from')
        ical = res['cal']['ical_A']
        if abs(ical - 15e-6) > 1e-12:
            bad.append('A3 the reused calibration recomputed Ical=%r, expected 15 uA' % ical)

        # (2) a mixed pass: the live case is launched, the reused one is not
        FakeLink.made = []
        acct2 = R.Account(os.path.join(temp, 'acct_mixed.csv'), 40, synth_seed(0))
        res2 = R.native_run(cases, mst, docs, decks,
                            opts(reuse='%s=%s,%s=%s' % (CAL_ID, stage, REUSED_ID, stage),
                                 published=published),
                            'r_mixed_000000_bbbbbb', out_root, log_dir, acct2)
        link2 = FakeLink.made[-1]
        started = sorted(set(c for c in link2.calls
                             if c.startswith('preflight-') or c.startswith('dut-')))
        if started != ['dut-%s' % LIVE_ID, 'preflight-%s' % LIVE_ID]:
            bad.append('A3 the mixed pass started the wrong cases (%r)' % started)
        c = acct2.counts()
        if c['confirmed'] != 2 or c['occupied'] != 2:
            bad.append('A3 the mixed pass accounted %r' % c)
        if res2['ledger'].used != 2:
            bad.append('A3 the per-pass ledger counted %r' % res2['ledger'].used)

        # (3) the ceiling is checked before the next case is pushed
        FakeLink.made = []
        acct3 = R.Account(os.path.join(temp, 'acct_ceiling.csv'), 4, synth_seed(2))
        res3 = R.native_run([synth_case(LIVE_ID), synth_case(REUSED_ID)], mst, docs, decks,
                            opts(published=published), 'r_ceiling_000_cccc', out_root, log_dir,
                            acct3)
        link3 = FakeLink.made[-1]
        started = [c for c in link3.calls if c.startswith('preflight-') or c.startswith('dut-')]
        if started != ['preflight-%s' % LIVE_ID, 'dut-%s' % LIVE_ID]:
            bad.append('3.1 the loop kept starting cases after the ceiling (%r)' % started)
        verdicts = [r[CASE_VERDICT] for r in res3['rows']]
        if 'BLOCKED_BUDGET' not in verdicts:
            bad.append('3.1 the case that could not be launched is %r' % verdicts)
        c = res3['account'].counts()
        if c['occupied'] != 4 or c['confirmed'] != 4 or c['requested'] != 4:
            bad.append('3.1 the loop accounted %r' % c)

        # (4) a refused launch is still a launch
        FakeLink.made = []
        acct4 = R.Account(os.path.join(temp, 'acct_fail.csv'), 6, synth_seed(0))
        res4 = R.native_run([synth_case(LIVE_ID)], mst, docs, decks, opts(),
                            'r_fail_000000_dddd', out_root, log_dir, acct4)
        c = res4['account'].counts()
        if c['confirmed'] != 2 or c['occupied'] != 2:
            bad.append('3.1 a refused DUT launch was not occupied (%r)' % c)
        verdicts = set(r[CASE_VERDICT] for r in res4['rows'])
        if 'FAIL_TOOL' not in verdicts:
            bad.append('3.1 a refused launch produced %r' % verdicts)
        for r in res4['rows']:
            if any(',' in str(f) for f in r):
                bad.append('3.1 an evidence row carries a comma')
                break

        # (5) losing contact is uncertain, occupies the ceiling, and is not claimed as executed
        FakeLink.made = []
        acct5 = R.Account(os.path.join(temp, 'acct_lost.csv'), 6, synth_seed(0))
        R.Link = lambda host, root, logdir: FakeLink(host, root, logdir, fail_at='preflight-')
        res5 = R.native_run([synth_case(LIVE_ID)], mst, docs, decks, opts(),
                            'r_lost_000000_eeee', out_root, log_dir, acct5)
        c = res5['account'].counts()
        if c['uncertain'] != 1 or c['occupied'] != 1 or c['confirmed'] != 0:
            bad.append('3.1 the lost contact was booked as %r' % c)
        if res5['rows'][0][CASE_VERDICT] != 'UNCERTAIN_LAUNCH':
            bad.append('3.1 a lost launch was recorded as %s' % res5['rows'][0][CASE_VERDICT])
        if res5['stopped'] == '':
            bad.append('3.1 the pass did not report why it stopped')
    finally:
        R.Link, R.prepare, R.static_gates = old_link, old_prepare, old_static
        shutil.rmtree(temp, ignore_errors=True)


def group_reuse(bad):
    """A3: reuse is byte-verified; the shortcuts that hid the defect are refused"""
    temp = tempfile.mkdtemp(prefix='d7b-guards-reuse-')
    try:
        mst, decks, docs, stage, published, points = reuse_fixture(temp)
        spec = '%s=%s' % (REUSED_ID, stage)
        got = R.resolve_reuse(spec, decks, mst, published)
        if REUSED_ID not in got:
            bad.append('A3 a byte-identical retained run was not accepted')
        else:
            v = got[REUSED_ID]
            if v['src_native_run'] != 'r_synth':
                bad.append('A3 the reused native run is %r' % v['src_native_run'])
            if v['section'] != 'tt' or v['temp'] != '27.0000':
                bad.append('A3 the reused conditions are %r / %r' % (v['section'], v['temp']))
            if not v['preflight_launch_id'].endswith('L001'):
                bad.append('A3 the reused preflight twin is %r' % v['preflight_launch_id'])

        def path(*p):
            return os.path.join(stage, *p)

        psf = path('mirror', 'cases', REUSED_ID, 'sim', '%s.raw' % REUSED_ID, 'sw1.tran.tran')
        keep_psf = io.open(psf, encoding='utf-8').read()
        swap(bad, 'a raw file that no longer hashes to the delivered digest', mst, decks, spec,
             published, stage, psf, keep_psf + '"x" 1.0\n', REUSED_ID)

        led = os.path.join(published, 'process_ledger.csv')
        keep_led = io.open(led, encoding='utf-8').read()
        dropped = ''.join(l + '\n' for l in keep_led.splitlines() if ',preflight,' not in l)
        swap(bad, 'a case whose rail preflight twin is missing', mst, decks, spec, published,
             stage, led, keep_led, REUSED_ID, new=dropped)

        # a second transcript naming a different native run for the same bytes
        t2 = path('transcripts', 'guest_900_dut-%s.txt' % REUSED_ID)
        write_text(t2, ('SPECTRE name=%s.scs rc=0\nCHECK datafile=\'%s/cases/%s/sim/%s.raw/'
                        'sw1.tran.tran\'\nLOGFILE %s/cases/%s/sim/%s.log\n'
                        % (REUSED_ID, '%s/r_other' % R.GUEST_ROOT, REUSED_ID, REUSED_ID,
                           '%s/r_other' % R.GUEST_ROOT, REUSED_ID, REUSED_ID)))
        refuse(bad, 'A3 two transcripts naming two different native runs for one byte stream',
               lambda: R.resolve_reuse(spec, decks, mst, published), RuntimeError)
        os.remove(t2)

        # a drifted stimulus, circuit, master or unknown case
        other = {REUSED_ID: synth_deck(REUSED_ID, [(0, 0.0), (2500000, 0.0), (2501000, 1.8),
                                                   (2532000, 1.8), (2533000, 0.0),
                                                   (2730000, 0.0), (2780000, 0.0)])}
        refuse(bad, 'A3 a PWL that is not the one that ran',
               lambda: R.resolve_reuse(spec, other, mst, published), RuntimeError)
        circuit = {REUSED_ID: synth_deck(REUSED_ID, points)}
        circuit[REUSED_ID]['deck'] = R.u(circuit[REUSED_ID]['deck']).replace('data_en iref_in',
                                                                          'data_en iref_other')
        refuse(bad, 'A3 a different netlist presented as the same device source',
               lambda: R.resolve_reuse(spec, circuit, mst, published), RuntimeError)
        changed_mst = [dict(mst[0])]
        changed_mst[0]['sent_sha256'] = R.sha_txt('changed\n')
        refuse(bad, 'A3 a swapped master',
               lambda: R.resolve_reuse(spec, decks, changed_mst, published), RuntimeError)
        refuse(bad, 'A3 a case the delivered table does not carry',
               lambda: R.resolve_reuse('SYN-Z=%s' % stage,
                                       {'SYN-Z': decks[REUSED_ID]}, mst, published), RuntimeError)
        for s in ('%s' % REUSED_ID, '%s=%s/nope' % (REUSED_ID, stage),
                  '%s=%s' % ('SYN-NOPE', stage)):
            refuse(bad, 'A3 the reuse spec %r' % s,
                   lambda: R.resolve_reuse(s, decks, mst, published), RuntimeError)
        # a ledger naming two dut launches is refused rather than resolved by taking the last
        dup = keep_led + keep_led.splitlines()[-1] + '\n'
        write_text(led, dup.replace('r_synth/L002', 'r_synth/L004'))
        refuse(bad, 'A3 two dut launches for one case, decided by taking the last',
               lambda: R.resolve_reuse(spec, decks, mst, published), RuntimeError)
        write_text(led, keep_led)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def swap(bad, name, mst, decks, spec, published, stage, path, restore, cid, new=None):
    write_text(path, new if new is not None else restore)
    try:
        R.resolve_reuse(spec, decks, mst, published)
        bad.append('A3 %s was accepted as a valid reuse' % name)
    except RuntimeError:
        pass
    finally:
        write_text(path, restore)


def group_run_id(bad):
    """A2: the default id is really unique, and an existing directory is never overwritten"""
    temp = tempfile.mkdtemp(prefix='d7b-guards-runid-')
    try:
        class O(object):
            run_id = ''
        o = O()
        first = R.make_run_id(o, temp)
        if '%' in first or not R.RUN_ID_RE.match(first):
            bad.append('A2 the default run id %r is not a real unique timestamp' % first)
        second = R.make_run_id(o, temp)
        if second == first:
            bad.append('A2 the default run id repeated itself: %s' % first)
        o.run_id = first
        os.makedirs(os.path.join(temp, 'evidence', first))
        refuse(bad, 'A2 an existing evidence directory was accepted',
               lambda: R.make_run_id(o, temp), RuntimeError)
        for wrong in ('r%%Y%%m%%d_%%H%%M%%S', 'r1', 'r2026102_000000_abcdef',
                      'r20261022_000000_ABCDEF', 'r20261022_000000_abcdef extra'):
            o.run_id = wrong
            refuse(bad, 'A2 the run id %r was accepted' % wrong,
                   lambda: R.make_run_id(o, temp), RuntimeError)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def group_publish(bad):
    """A3: the semantic check runs before anything moves, and a refusal changes nothing

    The checker itself is stood in for here, because what is under test is the *gate*: that a
    blocking failure stops the move, that only the disclosed budget failure may travel, and that
    nothing in the formal directory changes on the way out. R1-C's own tamper suite tests the
    checker behind this interface.
    """
    import types
    temp = tempfile.mkdtemp(prefix='d7b-guards-publish-')
    old_proj, old_mod = R.PROJ, sys.modules.get('dd1_d7b_evidence_check')
    try:
        fake = os.path.join(temp, 'proj')
        formal = os.path.join(fake, 'results', 'evidence')
        if not os.path.isdir(formal):
            os.makedirs(formal)
        R.PROJ = fake
        stub = types.ModuleType('dd1_d7b_evidence_check')
        sys.modules['dd1_d7b_evidence_check'] = stub
        verdict = {'failures': [], 'file_count': 1}
        stub.check_dir = lambda d: {'failures': list(verdict['failures']),
                                    'file_count': verdict['file_count'], 'checks': [],
                                    'rc': 0 if not verdict['failures'] else 1}

        def staged(name):
            d = os.path.join(temp, 'stage', 'evidence', name)
            write_text(os.path.join(d, 'cases.csv'), 'case_id\nsynthetic\n')
            write_text(os.path.join(d, 'charge_index.csv'), 'x\n')
            return d

        before = R.listing_of(formal)
        verdict['failures'] = ['MATRIX_COMPLETE', 'CHARGE_RECOMPUTED']
        stage = staged('r20261022_000000_abcdef')
        listing = R.listing_of(stage)
        refuse(bad, 'A3 a bundle the semantic check refuses was still published',
               lambda: R.publish(stage, 'r20261022_000000_abcdef'), RuntimeError)
        if R.listing_of(formal) != before:
            bad.append('A3 the refusal changed the formal directory')
        if R.listing_of(stage) != listing:
            bad.append('A3 the refusal deleted, moved or rewrote the staged bundle')
        verdict['failures'] = []
        refuse(bad, 'A3 a run id that is not a real timestamp was published',
               lambda: R.publish(staged('r20261022_000000_abcdef'), 'r%%Y'), RuntimeError)
        if R.listing_of(formal) != before:
            bad.append('A3 the malformed run id refusal touched the formal directory')
        # the disclosed historical budget violation is the one failure allowed to travel with a
        # bundle: it stays red, and it does not excuse any other check
        stage = staged('r20261022_000001_ffeedd')
        verdict['failures'] = ['BUDGET_RESPECTED']
        target = R.publish(stage, 'r20261022_000001_ffeedd')
        if not os.path.isdir(target):
            bad.append('A3 the bundle the checker accepted did not reach the formal directory')
        if os.path.exists(stage):
            bad.append('A3 the staged copy survived the move')
        if not os.path.isfile(os.path.join(target, 'cases.csv')):
            bad.append('A3 the published bytes are not what was staged')
        refuse(bad, 'A3 publishing the same run id twice overwrote the formal set',
               lambda: R.publish(staged('r20261022_000001_ffeedd'), 'r20261022_000001_ffeedd'),
               RuntimeError)
        empty = os.path.join(temp, 'empty', 'evidence', 'r20261022_000002_112233')
        if not os.path.isdir(empty):
            os.makedirs(empty)
        verdict['failures'] = []
        verdict['file_count'] = 0
        refuse(bad, 'A3 an empty bundle was published',
               lambda: R.publish(empty, 'r20261022_000002_112233'), RuntimeError)
    finally:
        R.PROJ = old_proj
        if old_mod is None:
            sys.modules.pop('dd1_d7b_evidence_check', None)
        else:
            sys.modules['dd1_d7b_evidence_check'] = old_mod
        shutil.rmtree(temp, ignore_errors=True)


def run():
    groups = [('A1 entry routing', group_routing), ('A2 ledger reopen', group_ledger),
              ('3.1 launch account', group_account), ('3.1/A3 native loop', group_loop),
              ('A3 byte-verified reuse', group_reuse), ('A2 run id', group_run_id),
              ('A3 publish gate', group_publish), ('3.2 offline modes', group_offline)]
    bad = []
    for name, fn in groups:
        before = len(bad)
        try:
            fn(bad)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            bad.append('%s raised %s: %s' % (name, type(exc).__name__, exc))
        print('%-26s %s' % (name, 'PASS' if len(bad) == before else 'FAIL'))
    for b in bad:
        print('GUARD_BAD %s' % b)
    print('D7B_R1_GUARDS: %s (%d groups, %d problem(s))'
          % ('PASS' if not bad else 'FAIL', len(groups), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(run())
