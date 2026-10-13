#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D1/R2D2-A: validate the FUTURE execution path of sc1_s1_r2d_regression.sh, offline.

    python scripts/sc1_r2d1_entry_selftest.py [--out CSV]

Nothing here touches Spectre. The entry script runs from a LOCAL COPY in a scratch tree, with
preflight and the runner replaced by mocks and the data being read being SYNTHETIC PSF-ASCII written by
scripts/sc1_r2d1_reanalysis_casegen.py's waveforms (1.8 V / ns values are POC_ASSUMPTION tool-test
conditions). It is evidence about the entry's control flow and its state criteria, not an S1 circuit
regression, and the values were composed rather than measured.

R2D2 changed two things on purpose:

  * the mock reader used to be the source of every value, so a state check could only ever be
    "did the read work". The raws are now real PSF files and the audited reader answers, which lets
    the shared window contract (scripts/sc1_s1_window_contract.py) be exercised the way it will be in
    the authorised session -- including its two per-sample awk passes over blank and the clock.
  * the reviewer's repro for A (T2 declared BLANK=0 while a whole-window blank of 1.8 V was still
    accepted) is now a case, together with the release-edge, clock-edge, high-dip and low-rise cases.
    A refusal is only accepted when a *value* disagrees: MOCK_MISS, an unreadable file or an early
    crash is scored as a harness problem, never as a detection.
"""
from __future__ import print_function

import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc1_r2d1_reanalysis_casegen as CG

FUTURE = 'SYNTHETIC_MOCK_not_a_circuit_regression'

MKPF = r'''#!/bin/bash
# mock preflight: reports a stage and exits with the scripted code
NET="$1"; TAG="${3:-mock}"
echo "PREFLIGHT_STAGE=static_gate tag=$TAG"
echo "$NET" >> "${PF_CALLS:-/dev/null}"
exit "${PF_RC:-0}"
'''

MKRS = r'''#!/bin/bash
# mock runner: counts its own calls and prints the tokens a real run_spectre.sh prints
echo "$1" >> "${RUN_CALLS:-/dev/null}"
DECK="$(basename "$1")"
case "$DECK" in
  *dc_blank0*) RAW="$MOCK_RAW/raw_dc0" ;;
  *dc_blank1*) RAW="$MOCK_RAW/raw_dc18" ;;
  *fault*)     RAW="$MOCK_RAW/raw_fault" ;;
  *)           RAW="$MOCK_RAW/raw_tran" ;;
esac
[ -n "${MR_DATAFILE-1}" ] || RAW=""     # no colon: an explicitly empty value means "no data file"
echo "SPECTRE name=$DECK rc=${MR_RC:-0}"
echo "CHECK done_line='spectre completes with 0 error'"
echo "CHECK error_hits=${MR_ERRHITS:-0}"
echo "CHECK datafile='$RAW'"
LABEL="${LABEL:-SPECTRE_SMOKE_TEST}"
n=0
while [ "$n" -lt "${MR_TOKENS:-1}" ]; do echo "$LABEL: PASS"; n=$((n+1)); done
exit "${MR_RC:-0}"
'''

MKRD = r'''#!/usr/bin/env python
# delegating reader: behaves exactly like the audited reader, except for one scripted query, which it
# refuses with a scripted exit code. Without the delegation a "reader error" case would fail every
# read at once and the run would be rejected for the wrong reason.
from __future__ import print_function
import os
import sys

a = sys.argv[1:]
opt = {}
i = 0
while i < len(a):
    if a[i].startswith('--'):
        opt[a[i][2:]] = a[i + 1] if i + 1 < len(a) else ''
        i += 2
    else:
        i += 1
want = os.environ.get('REFUSE_QUERY', '')
got = '%s|%s|%s' % (os.path.basename(opt.get('data', '')), opt.get('sig', ''), opt.get('mode', 'last'))
if want and want == got:
    print('NO_POINT simulated reader refusal')
    sys.exit(int(os.environ.get('REFUSE_RC', '4')))
here = os.path.dirname(os.path.abspath(__file__))
reader = os.path.join(here, 'scripts', 'sc1_read_psf.py')
os.execv(sys.executable, [sys.executable, reader] + a)
'''


def clean(p):
    return p.replace('\\', '/')


def ns_of(t):
    return int(round(t * 1e9))


def build_tran_series(over=None):
    """The frozen synthetic transient waveforms, with per-case overrides keyed by signal name.

    An override is either a constant float or a function of the time in nanoseconds.
    """
    ts = CG.times()
    sig = {
        'en': [CG.expected_en(t) for t in ts],
        'blank': [CG.expected_blank(t) for t in ts],
        'q': [CG.expected_q(t) for t in ts],
        'qbar': [CG.V18 - CG.expected_q(t) for t in ts],
        'd': [CG.expected_d(t) for t in ts],
        'clk': [CG.expected_clk(t) for t in ts],
    }
    for name, fn in (over or {}).items():
        if name not in sig:
            raise ValueError('unknown signal %s' % name)
        if callable(fn):
            sig[name] = [fn(ns_of(t)) for t in ts]
        else:
            sig[name] = [float(fn) for t in ts]
    return ts, sig


def write_tran_psf(path, over=None, drop=(), faulted=False):
    ts = CG.times()
    if faulted:
        base = {'en': [CG.expected_en(t, True) for t in ts],
                'blank': [CG.expected_blank(t) for t in ts],   # the SOURCE keeps its PWL: the fault is
                'q': [CG.expected_q(t) for t in ts],           # at the gate's BLANK pin, inside the deck
                'qbar': [CG.V18 - CG.expected_q(t) for t in ts],
                'd': [CG.expected_d(t) for t in ts],
                'clk': [CG.expected_clk(t) for t in ts]}
        for name, fn in (over or {}).items():
            if callable(fn):
                base[name] = [fn(ns_of(t)) for t in ts]
            else:
                base[name] = [float(fn) for t in ts]
        pairs = [('time', ts)] + [(n, base[n]) for n in ('en', 'blank', 'q', 'qbar', 'd', 'clk')
                                  if n in base and n not in drop]
    else:
        _ts, sig = build_tran_series(over)
        pairs = [('time', ts)] + [(n, sig[n]) for n in ('en', 'blank', 'q', 'qbar', 'd', 'clk')
                                  if n not in drop]
    CG.write(path, CG.psf(pairs))


def write_dc_psf(path, blank_v, en_over=None, blank_override=None):
    qbar = [0.0, CG.V18]
    en = [CG.V18 if (q < 0.9 and blank_v < 0.9) else 0.0 for q in qbar]
    if en_over is not None:
        en = list(en_over)
    b = blank_override if blank_override is not None else blank_v
    CG.write(path, CG.psf([('dc', [0.0, CG.V18]), ('en', en), ('blank', [b, b]), ('qbar', qbar)],
                          axis='dc'))


class Harness(object):
    def __init__(self, proj):
        self.proj = proj
        self.root = os.path.join(proj, 'cadence_work', 'sc1_sim', 'r2d2_entry_mock')
        if os.path.isdir(self.root):
            shutil.rmtree(self.root)
        for d in ('spectre', 'scripts', 'skill', 'raw'):
            os.makedirs(os.path.join(self.root, d))
        # a COPY of the committed entry: the committed script is never pointed at mocks
        self.entry = os.path.join(self.root, 'scripts', 'sc1_s1_r2d_regression.sh')
        shutil.copyfile(os.path.join(proj, 'scripts', 'sc1_s1_r2d_regression.sh'), self.entry)
        for name in ('sc1_csv_writer.py', 'sc1_s1_window_contract.py', 'sc1_read_psf.py'):
            shutil.copyfile(os.path.join(proj, 'scripts', name),
                            os.path.join(self.root, 'scripts', name))
        for name in ('C2MOS_DFF.scs', 'sc1_scan_gate.scs'):
            shutil.copyfile(os.path.join(proj, 'spectre', name),
                            os.path.join(self.root, 'spectre', name))
        open(os.path.join(self.root, 'skill', 'cad_env.sh'), 'w').write('# mock: sets nothing\n')
        self.fake_lib = os.path.join(self.root, 'raw', 'fake_models.lib')
        open(self.fake_lib, 'w').write('*( mock model library: never opened by a simulator )*\n')
        for name, text in (('mock_pf.sh', MKPF), ('mock_rs.sh', MKRS), ('mock_rd.py', MKRD)):
            open(os.path.join(self.root, name), 'w').write(text)
        self.rawdir = os.path.join(self.root, 'raw')
        open(os.path.join(self.rawdir, 'STALE_old_result'), 'w').write('STALE 1.2345\n')

    def make_data(self, dc_blank0=None, dc_blank18=None, dc_blank0_override=None,
                  dc_blank18_override=None, tran=None, fault=None):
        for p in os.listdir(self.rawdir):
            if p.startswith('raw_'):
                os.remove(os.path.join(self.rawdir, p))
        write_dc_psf(os.path.join(self.rawdir, 'raw_dc0'), 0.0, en_over=dc_blank0,
                     blank_override=dc_blank0_override)
        write_dc_psf(os.path.join(self.rawdir, 'raw_dc18'), CG.V18, en_over=dc_blank18,
                     blank_override=dc_blank18_override)
        write_tran_psf(os.path.join(self.rawdir, 'raw_tran'), over=tran)
        write_tran_psf(os.path.join(self.rawdir, 'raw_fault'), over=fault, faulted=True)

    def invoke(self, env_extra, tag, use_mock_reader=False, refuse=None, refuse_rc='4'):
        scratch = os.path.join(self.root, 'scratch_' + tag)
        if os.path.isdir(scratch):
            shutil.rmtree(scratch)
        os.makedirs(scratch)
        calls = os.path.join(scratch, 'runner.calls')
        pfcalls = os.path.join(scratch, 'preflight.calls')
        open(calls, 'w').close()
        open(pfcalls, 'w').close()
        env = dict(os.environ)
        reader = ('%s %s' % (clean(sys.executable), clean(os.path.join(self.root, 'mock_rd.py')))
                  if use_mock_reader else 'python %s' % clean(
                      os.path.join(self.root, 'scripts', 'sc1_read_psf.py')))
        env.update({
            'PROJ': clean(self.root),
            'S1REG_DIR': clean(scratch),
            'OUT_CSV': clean(os.path.join(scratch, 'entry.csv')),
            'PF_CMD': 'bash %s' % clean(os.path.join(self.root, 'mock_pf.sh')),
            'RUN_CMD': 'bash %s' % clean(os.path.join(self.root, 'mock_rs.sh')),
            'READ_CMD': reader,
            'MOCK_RAW': clean(self.rawdir),
            'RUN_CALLS': clean(calls),
            'PF_CALLS': clean(pfcalls),
        })
        if refuse:
            env['REFUSE_QUERY'] = refuse
            env['REFUSE_RC'] = refuse_rc
        env.update(env_extra)
        p = subprocess.Popen(['bash', clean(self.entry)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=env)
        out = p.communicate()[0].decode('utf-8', 'replace')
        nrun = len([l for l in open(calls) if l.strip()])
        npf = len([l for l in open(pfcalls) if l.strip()])
        csv = os.path.join(scratch, 'entry.csv')
        return dict(rc=p.returncode, out=out, runner=nrun, preflight=npf,
                    csv=(csv if os.path.exists(csv) else None), scratch=scratch)


def split_csv(line):
    fields, cur, quoted, i = [], u'', False, 0
    line = line.strip()
    while i < len(line):
        c = line[i]
        if c == u'"':
            if quoted and i + 1 < len(line) and line[i + 1] == u'"':
                cur += u'"'
                i += 2
                continue
            quoted = not quoted
        elif c == u',' and not quoted:
            fields.append(cur)
            cur = u''
        else:
            cur += c
        i += 1
    fields.append(cur)
    return fields


def read_csv(path):
    if not path:
        return []
    rows = []
    with io.open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip(u'\n')
            if line:
                rows.append(split_csv(line))
    return rows


def main():
    proj = os.path.dirname(HERE)
    argv = sys.argv[1:]
    out_csv = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(
        proj, 'results', 'evidence', 'sc1_r2d2_entry_selftest.csv')
    H = Harness(proj)
    good = {'RUN': '1', 'QODER_SIM_AUTHORISED': '1', 'QODER_PDK_LIB': clean(H.fake_lib)}
    results = []

    def record(case, rc, runner, rows, met, note):
        results.append([case, str(rc), str(runner), str(rows), 'yes' if met else 'no',
                        'PASS' if met else 'FAIL', note, FUTURE])
        print('%-28s rc=%-4s runner_calls=%-2s rows=%-3s %s' % (case, rc, runner, rows,
                                                                'PASS' if met else 'FAIL'))
        if not met:
            print('   note: %s' % note)

    def check(case, env_extra, data_kwargs, want_ok, note, want_rows=None, want_runner=None,
              want_rowspec=None, want_absent=None, forbid_rows=None, use_mock_reader=False,
              refuse=None, refuse_rc='4', want_last_token=None):
        H.make_data(**data_kwargs)
        r = H.invoke(dict(env_extra), 's_' + case, use_mock_reader=use_mock_reader, refuse=refuse,
                     refuse_rc=refuse_rc)
        rows = read_csv(r['csv'])
        body = rows[1:] if rows else []
        reasons = []
        token = 'S1_R2D_REGRESSION: %s' % ('PASS' if want_ok else 'FAIL')
        if token not in r['out']:
            # an entry that aborts (unbound variable, lost cd) would otherwise look like a refusal
            reasons.append('the entry never printed its own "%s" line' % token)
        if 'unbound variable' in r['out'] or 'HARNESS_ERROR' in r['out']:
            reasons.append('harness error in the entry output')
        if want_last_token and want_last_token not in r['out']:
            reasons.append('expected token %s missing from the output' % want_last_token)
        if want_ok and r['rc'] != 0:
            reasons.append('expected exit 0, got %d' % r['rc'])
        if not want_ok and r['rc'] == 0:
            reasons.append('expected a non-zero exit, got 0')
        if want_runner is not None and r['runner'] != want_runner:
            reasons.append('runner called %d times, expected %d' % (r['runner'], want_runner))
        if want_rows is not None and len(body) != want_rows:
            reasons.append('CSV body rows %d, expected %d' % (len(body), want_rows))
        for (cid, cols) in (want_rowspec or []):
            hit = [row for row in body if row[0] == cid]
            if not hit:
                reasons.append('no row with case_id %s' % cid)
                continue
            for (col, want) in cols.items():
                if want not in hit[0][col]:
                    reasons.append('row %s column %d is %r, expected %r'
                                   % (cid, col, hit[0][col], want))
        for cid in (forbid_rows or []):
            if [row for row in body if row[0] == cid and row[12] == 'PASS']:
                reasons.append('row %s must not be PASS here' % cid)
        for needle in list(want_absent or []) + ['MOCK_MISS', 'REFUSER_CALLED_WITHOUT_MATCH']:
            # MOCK_MISS or an unmatched mock call would mean the case failed because of the harness
            if any(needle in ','.join(row) for row in body):
                reasons.append('%s must not appear in any row' % needle)
        met = not reasons
        if reasons:
            print('   ---- entry output ----\n%s' % r['out'])
        record(case, r['rc'], r['runner'], len(body), met,
               note + ('' if met else ' | ' + '; '.join(reasons)))
        return r, body

    def base_data(**kw):
        d = dict(tran=None, fault=None, dc_blank0=None, dc_blank18=None)
        d.update(kw)
        return d

    # ------------------------------------------------------------------ the guards
    dry = H.invoke({}, 's_guards_dry')
    decks = [x for x in os.listdir(dry['scratch']) if x.endswith('.scs')]
    met = (dry['rc'] == 0 and 'DRY_RUN' in dry['out'] and dry['runner'] == 0
           and dry['preflight'] == 0 and not decks)
    record('guards_dry', dry['rc'], dry['runner'], 0, met,
           'a dry run must neither call a mock nor write a deck')

    noauth = H.invoke({'RUN': '1'}, 's_guards_noauth')
    met = noauth['rc'] == 5 and 'QODER_SIM_AUTHORISED' in noauth['out'] and noauth['runner'] == 0
    record('guards_run_noauth', noauth['rc'], noauth['runner'], 0, met,
           'RUN=1 without the authorisation bit exits 5 and calls nothing')

    blocked = H.invoke(dict(good, QODER_PDK_LIB='/no/such/lib.file'), 's_guards_blocked')
    wrote = os.path.exists(os.path.join(blocked['scratch'], 's1reg_dc_blank0.scs'))
    met = blocked['rc'] == 7 and 'BLOCKED' in blocked['out'] and not wrote and blocked['runner'] == 0
    record('guards_pdk_blocked', blocked['rc'], blocked['runner'], 0, met,
           'an unresolved model library stops with BLOCKED before any deck is written')

    # ------------------------------------------------------- the correct historical stimulus
    # expected row count derived from the contract itself, so a rule change cannot leave a stale number
    import sc1_s1_window_contract as WC
    per_window = 0
    for wid in sorted(WC.WINDOWS):
        w = WC.WINDOWS[wid]
        per_window += 1 + len(w['states']) + len(w['pwl']) + 1
    n_rows = 4 + 1 + per_window + 2
    r, body = check('all_good', good, base_data(), True,
                    'the frozen stimulus satisfies every state, PWL and clock check and exits 0',
                    want_rows=n_rows, want_runner=4,
                    want_rowspec=[('T1_output_assertion_en', {12: 'PASS'}),
                                  ('T2_state_throughout_blank', {12: 'PASS'}),
                                  ('T3_stimulus_pwl_blank', {12: 'PASS'}),
                                  ('T4_stimulus_clock_clk', {12: 'PASS'}),
                                  ('F1_blank_clamped', {12: 'DETECTED'}),
                                  ('F1_blank_clamped_setup', {12: 'PASS'})])
    ids = [row[0] for row in body]
    widths = sorted(set(len(row) for row in read_csv(r['csv'])))
    unresolved = [row[0] for row in body if row[7] == 'NOT_MEASURED']
    met = (widths == [14] and len(ids) == len(set(ids)) == n_rows and not unresolved)
    record('csv_structure', r['rc'], r['runner'], len(ids), met,
           'header plus 14 fields, unique case ids, no unresolved measurement in a pass '
           '(widths=%s ids=%d unique=%d unresolved=%s)' % (widths, len(ids), len(set(ids)),
                                                            unresolved))

    # ---------------------------------------------------------------- refusal injections
    check('preflight_refuses', dict(good, PF_RC='1'), base_data(), False,
          'a refused preflight stops the deck and the runner is never called', want_runner=0,
          want_rows=4,
          want_rowspec=[('dc_blank0', {1: 'truth', 2: 'PRECHECK_FAIL', 12: 'FAIL'}),
                        ('dc_blank1.8', {2: 'PRECHECK_FAIL', 12: 'FAIL'}),
                        ('T1', {2: 'PRECHECK_FAIL'}),
                        ('F1_blank_clamped', {2: 'PRECHECK_FAIL', 12: 'FAIL'})])
    check('runner_bad_rc', dict(good, MR_RC='1'), base_data(), False,
          'a runner exit code is SIM_FAIL, not a verdict',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL', 10: '1', 12: 'FAIL'})])
    check('runner_two_tokens', dict(good, MR_TOKENS='2'), base_data(), False,
          'the success token must be unique, not merely present',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL', 12: 'FAIL'})])
    check('runner_no_datafile', dict(good, MR_DATAFILE=''), base_data(), False,
          'no reported data file means no row; the STALE raw is never used',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL'})], want_absent=['STALE'])
    check('runner_log_errors', dict(good, MR_ERRHITS='3'), base_data(), False,
          'error_hits != 0 is SIM_FAIL', want_rowspec=[('dc_blank0', {2: 'SIM_FAIL'})])
    check('reader_error', good, base_data(), False,
          'a reader refusal keeps its own exit code (4, not flattened to 1) and voids the row',
          use_mock_reader=True, refuse='raw_dc0|en|last', refuse_rc='3',
          want_rowspec=[('truth_Q1_BLANK0', {7: 'NOT_MEASURED', 9: '3', 12: 'FAIL',
                                             13: 'reader'})])
    # ------------------------------------------------------ stimulus and state counter-examples
    check('truth_wrong_value', good, base_data(dc_blank0=[0.12, 0.0]), False,
          'en contradicting its expected ON state fails that row and the run',
          want_rowspec=[('truth_Q1_BLANK0', {7: '0.12', 12: 'FAIL'})])
    check('stimulus_mismatch', good, base_data(dc_blank18_override=0.0), False,
          'BLANK not reading back at its label voids the row',
          want_rowspec=[('truth_Q0_BLANK1', {12: 'FAIL', 13: 'blank read 0 != label 1.8'})])
    # A: the reviewer's counter-example, expressed in the data instead of in a mock table
    check('a_t2_blank_high', good, base_data(tran={'blank': lambda t: 1.8 if 520 <= t <= 620 else
                                                  (1.8 if t <= 450 else (0.0 if t >= 460 else
                                                                         1.8 - 0.18 * (t - 450)))}),
          False,
          'R2D2-A: T2 says BLANK=0 but BLANK is 1.8 V across the window -> the state check must fail',
          want_rowspec=[('T2_state_throughout_blank', {12: 'FAIL', 13: 'low'}),
                        ('T2_output_assertion_en', {12: 'PASS'})],
          forbid_rows=['T2_state_throughout_blank'], want_last_token='FAIL')
    check('c_blank_never_releases', good, base_data(tran={'blank': 1.8}), False,
          'R2D2-C: blank stays high past 460 ns, so the release edge T3 names is missing',
          want_rowspec=[('T3_stimulus_pwl_blank', {12: 'FAIL'}),
                        ('T1_stimulus_pwl_blank', {12: 'FAIL'})])
    check('c_blank_single_spike', good,
          base_data(tran={'blank': lambda t: 1.8 if t == 410 else 0.0}), False,
          'R2D2-C: one 1.8 V sample at 410 ns cannot certify a window; the PWL check fails it',
          want_rowspec=[('T3_stimulus_pwl_blank', {12: 'FAIL'})])
    check('c_high_state_dips', good,
          base_data(tran={'q': lambda t: 0.4 if t == 420 else CG.expected_q(t * 1e-9)}),
          False, 'a one-sample dip inside a state that must hold high fails that state',
          want_rowspec=[('T1_state_throughout_q', {12: 'FAIL'})])
    check('c_low_state_rises', good,
          base_data(tran={'qbar': lambda t: 1.2 if t == 560 else
                          (CG.V18 - CG.expected_q(t * 1e-9))}), False,
          'a one-sample rise inside a state that must stay low fails that state',
          want_rowspec=[('T2_state_throughout_qbar', {12: 'FAIL'})])
    check('c_clock_stuck_high', good, base_data(tran={'clk': 1.8}), False,
          'a clock that never falls inside the window is not the frozen stimulus, so the clock check '
          'fails rather than "max was high once" passing it',
          want_rowspec=[('T2_stimulus_clock_clk', {12: 'FAIL'})])
    check('window_fail', good, base_data(tran={'en': lambda t: 0.0 if 520 <= t <= 620 else
                                              (CG.expected_en(t * 1e-9))}), False,
          'a failing transient output assertion fails the run',
          want_rowspec=[('T2_output_assertion_en', {12: 'FAIL'})])
    check('fault_cannot_mask_truth', good, base_data(dc_blank0=[1.7, 1.6]), False,
          'a detected fault elsewhere must not hide a failing normal truth row',
          want_rowspec=[('truth_Q0_BLANK0', {12: 'FAIL'}), ('F1_blank_clamped', {12: 'DETECTED'})])
    check('toothless_fault', good, base_data(fault={'en': lambda t: 0.0 if 400 <= t <= 455 else
                                                   CG.expected_en(t * 1e-9, True)}), False,
          'T1 passing on the BLANK-rewired data means the checker cannot fail',
          want_rowspec=[('F1_blank_clamped', {12: 'CHECKER_TOOTHLESS'})])
    check('fault_setup_invalid', good, base_data(fault={'q': lambda t: 0.0 if 400 <= t <= 455 else
                                                      CG.expected_q(t * 1e-9)}), False,
          'if Q is not 1 through the T1 window the faulted bench is not the T1 experiment, so no '
          'detection may be claimed',
          want_rowspec=[('F1_blank_clamped', {12: 'FAULT_SETUP_INVALID'}),
                        ('F1_blank_clamped_setup', {12: 'FAIL'})])

    # ------------------------------------------------------------------- write the evidence
    with io.open(out_csv, 'w', encoding='utf-8', newline='\n') as f:
        f.write(CG.u(','.join('"%s"' % h for h in
                              ['case_id', 'entry_rc', 'runner_calls', 'csv_rows', 'expectation_met',
                               'verdict', 'note', 'data_class'])) + '\n')
        for row in results:
            f.write(CG.u(','.join('"%s"' % str(c).replace('"', '""') for c in row)) + '\n')
    bad = [r for r in results if r[5] != 'PASS']
    print('ENTRY_SELFTEST cases=%d failed=%d -> %s   (%s)'
          % (len(results), len(bad), 'PASS' if not bad else 'FAIL', out_csv))
    print('NOTE: every value above is SYNTHETIC/MOCK; no simulator was called and this is not an S1 '
          'circuit regression.')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
