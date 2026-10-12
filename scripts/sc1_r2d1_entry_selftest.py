#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D1-A: validate the FUTURE execution path of sc1_s1_r2d_regression.sh without a simulator.

    python scripts/sc1_r2d1_entry_selftest.py [--out CSV]

Nothing here touches Spectre. The entry script runs from a LOCAL COPY inside a scratch tree, with its
three command hooks replaced by mocks (PF_CMD / RUN_CMD / READ_CMD) and a dummy "model library" file,
so every number below is SYNTHETIC/MOCK -- it is evidence about the entry script's control flow, not
an S1 circuit regression.

What each case has to prove, taken from the review items it was written against:
  guards_*          dry run executes nothing and writes no deck; RUN=1 without the authorisation bit
                    exits 5; authorised with an unresolved model library exits BLOCKED (7) before any
                    deck file is created
  preflight_refuses non-zero preflight => the runner is called 0 times (counted by the mock itself)
  runner_*          a bad exit code, a duplicated success token, a non-zero error_hits or a missing
                    data file are SIM_FAIL, and a STALE raw in the scratch tree is never used
  reader_error      a reader exit code is judged before any numeric conversion: READ_FAIL, NOT_MEASURED
  truth_wrong       an en that contradicts its own expected state fails that row and the run
  stimulus_mismatch a BLANK that does not read back at its label voids the row even when en is right
  window_fail       one failing transient window fails the run
  toothless_fault   if the untouched T1 assertion PASSES on the BLANK-rewired data, the checker is
                    reported as unable to fail -- which is a failure, never a skip
  all_good          correct synthetic data walks every assertion and exits 0
  csv_structure     the produced CSV is re-parsed: 14 fields per row, expected row count, unique ids
"""
from __future__ import print_function

import io
import os
import shutil
import subprocess
import sys

FUTURE = 'SYNTHETIC_MOCK_not_a_circuit_regression'

MKPF = r'''#!/bin/bash
# mock preflight: reports a stage and exits with the scripted code
NET="$1"; TAG="${3:-mock}"
echo "PREFLIGHT_STAGE=static_gate tag=$TAG"
echo "mock preflight called for $NET"
echo "$NET" >> "${PF_CALLS:-/dev/null}"
exit "${PF_RC:-0}"
'''

MKRS = r'''#!/bin/bash
# mock runner: counts its own calls and prints the tokens a real run_spectre.sh prints
echo "$1" >> "${RUN_CALLS:-/dev/null}"
DECK="$1"
case "$(basename "$DECK")" in        # basename only: a scratch directory named *fault* must not
  *dc_blank0*) RAW="$MOCK_RAW/raw_dc0" ;;   # redirect every deck to the faulted data set
  *dc_blank1*) RAW="$MOCK_RAW/raw_dc18" ;;
  *fault*)     RAW="$MOCK_RAW/raw_fault" ;;
  *)           RAW="$MOCK_RAW/raw_tran" ;;
esac
[ -n "${MR_DATAFILE-1}" ] || RAW=""     # no colon: an explicitly empty value means "no data file"
echo "SPECTRE name=$(basename "$DECK") rc=${MR_RC:-0}"
echo "CHECK done_line='spectre completes with 0 error'"
echo "CHECK error_hits=${MR_ERRHITS:-0}"
echo "CHECK datafile='$RAW'"
LABEL="${LABEL:-SPECTRE_SMOKE_TEST}"
n=0
while [ "$n" -lt "${MR_TOKENS:-1}" ]; do echo "$LABEL: PASS"; n=$((n+1)); done
exit "${MR_RC:-0}"
'''

MKRD = r'''#!/usr/bin/env python
# mock reader: same flag surface as sc1_read_psf.py, values and exit codes from a table
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
data = os.path.basename(opt.get('data', ''))
if 'sweep' in opt:
    query = 'sweep=' + opt['sweep']
elif 't0' in opt or 't1' in opt:
    query = 'win=%s..%s:%s' % (opt.get('t0', ''), opt.get('t1', ''), opt.get('mode', 'last'))
else:
    query = 'plain'
sig = opt.get('sig', '')
for line in open(os.environ['MOCK_VALUES']):
    parts = line.rstrip('\n').split('\t')
    if len(parts) != 4:
        continue
    d, q, s, val = parts
    if (d, q, s) == (data, query, sig):
        if val.startswith('rc:'):
            print('%s simulated reader refusal' % val[3:])
            sys.exit(int(val[3:]))
        print(val)
        sys.exit(0)
print('MOCK_MISS data=%s query=%s sig=%s' % (data, query, sig))
sys.exit(9)
'''

TRUTH = [('raw_dc0', 'sweep=0', 'en', '1.7'), ('raw_dc0', 'sweep=1.8', 'en', '0.05'),
         ('raw_dc18', 'sweep=0', 'en', '0.04'), ('raw_dc18', 'sweep=1.8', 'en', '0.03')]


def clean(path):
    return path.replace('\\', '/')


def good_values():
    """(data file, query, signal) -> value, chosen so every historical threshold assertion holds."""
    t = {}
    # DC truth decks: qbar is the swept source, so sweep=0 means Q=1 and sweep=1.8 means Q=0
    t[('raw_dc0', 'sweep=0', 'en')] = '1.7'
    t[('raw_dc0', 'sweep=1.8', 'en')] = '0.05'
    t[('raw_dc0', 'sweep=0', 'blank')] = '0'
    t[('raw_dc0', 'sweep=1.8', 'blank')] = '0'
    t[('raw_dc0', 'sweep=0', 'qbar')] = '0'
    t[('raw_dc0', 'sweep=1.8', 'qbar')] = '1.8'
    t[('raw_dc18', 'sweep=0', 'en')] = '0.04'
    t[('raw_dc18', 'sweep=1.8', 'en')] = '0.03'
    t[('raw_dc18', 'sweep=0', 'blank')] = '1.8'
    t[('raw_dc18', 'sweep=1.8', 'blank')] = '1.8'
    t[('raw_dc18', 'sweep=0', 'qbar')] = '0'
    t[('raw_dc18', 'sweep=1.8', 'qbar')] = '1.8'
    # transient: the five windows in their own worst-case modes, with the states that were actually
    # applied in each of them (a min of 1.77 V and a max of 1.2 V in one window would be a mock bug
    # pretending to be a circuit result, so the fill values are kept physically consistent)
    fill = {'400n..455n': {'blank': '1.8', 'qbar': '0', 'q': '1.8', 'd': '1.8', 'clk': '1.8'},
            '520n..620n': {'blank': '0', 'qbar': '0', 'q': '1.8', 'd': '1.8', 'clk': '1.8'},
            '410n..520n': {'blank': '1.8', 'qbar': '0', 'q': '1.8', 'd': '1.8', 'clk': '1.8'},
            '700n..860n': {'blank': '0', 'qbar': '1.8', 'q': '0.002', 'd': '0', 'clk': '1.8'}}
    for w in sorted(fill):
        for sig in sorted(fill[w]):
            t[('raw_tran', 'win=%s:max' % w, sig)] = fill[w][sig]
    t[('raw_tran', 'win=60n..90n:max', 'clk')] = '1.8'
    t[('raw_tran', 'win=400n..455n:max', 'en')] = '0.02'
    t[('raw_tran', 'win=520n..620n:min', 'en')] = '1.79'
    t[('raw_tran', 'win=410n..520n:min', 'q')] = '1.77'
    t[('raw_tran', 'win=700n..860n:max', 'en')] = '3.66e-06'
    t[('raw_tran', 'win=700n..860n:max', 'q')] = '0.002'
    # the faulted bench: BLANK never reaches the gate, so en goes high inside T1's window
    t[('raw_fault', 'win=400n..455n:max', 'en')] = '1.8'
    return t


def write_values(path, table):
    out = io.open(path, 'w', encoding='utf-8', newline='\n')
    try:
        for (d, q, s), v in sorted(table.items()):
            out.write(u'%s\t%s\t%s\t%s\n' % (d, q, s, v))
    finally:
        out.close()


def split_csv(line):
    """Minimal quoted-CSV splitter: the py2.6 csv module hands back byte strings, this does not."""
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


class Harness(object):
    def __init__(self, proj):
        self.proj = proj
        self.root = os.path.join(proj, 'cadence_work', 'sc1_sim', 'r2d1_entry_mock')
        if os.path.isdir(self.root):
            shutil.rmtree(self.root)
        for d in ('spectre', 'scripts', 'skill', 'raw'):
            os.makedirs(os.path.join(self.root, d))
        # a COPY of the committed entry: the committed script is never pointed at mocks
        self.entry = os.path.join(self.root, 'scripts', 'sc1_s1_r2d_regression.sh')
        shutil.copyfile(os.path.join(proj, 'scripts', 'sc1_s1_r2d_regression.sh'), self.entry)
        shutil.copyfile(os.path.join(proj, 'scripts', 'sc1_csv_writer.py'),
                        os.path.join(self.root, 'scripts', 'sc1_csv_writer.py'))
        for name in ('C2MOS_DFF.scs', 'sc1_scan_gate.scs'):
            shutil.copyfile(os.path.join(proj, 'spectre', name),
                            os.path.join(self.root, 'spectre', name))
        open(os.path.join(self.root, 'skill', 'cad_env.sh'), 'w').write('# mock: sets nothing\n')
        self.fake_lib = os.path.join(self.root, 'raw', 'fake_models.lib')
        open(self.fake_lib, 'w').write('*( mock model library: never opened by a simulator )*\n')
        for name, text in (('mock_pf.sh', MKPF), ('mock_rs.sh', MKRS)):
            open(os.path.join(self.root, name), 'w').write(text)
        open(os.path.join(self.root, 'mock_rd.py'), 'w').write(MKRD)
        for stem in ('raw_dc0', 'raw_dc18', 'raw_tran', 'raw_fault'):
            open(os.path.join(self.root, 'raw', stem), 'w').write('TRACE\nVALUE\n')
        # an old result that must never be mistaken for a fresh one
        open(os.path.join(self.root, 'raw', 'STALE_old_result'), 'w').write('STALE 1.2345\n')
        self.rawdir = os.path.join(self.root, 'raw')

    def base_env(self, scratch):
        return {
            'PROJ': clean(self.root),
            'S1REG_DIR': clean(scratch),
            'OUT_CSV': clean(os.path.join(scratch, 'entry.csv')),
            'PF_CMD': 'bash %s' % clean(os.path.join(self.root, 'mock_pf.sh')),
            'RUN_CMD': 'bash %s' % clean(os.path.join(self.root, 'mock_rs.sh')),
            'READ_CMD': '%s %s' % (clean(sys.executable),
                                   clean(os.path.join(self.root, 'mock_rd.py'))),
            'MOCK_RAW': clean(self.rawdir),
        }

    def invoke(self, env_extra, tag):
        scratch = os.path.join(self.root, 'scratch_' + tag)
        if os.path.isdir(scratch):
            shutil.rmtree(scratch)
        os.makedirs(scratch)
        calls = os.path.join(scratch, 'runner.calls')
        pfcalls = os.path.join(scratch, 'preflight.calls')
        open(calls, 'w').close()
        open(pfcalls, 'w').close()
        vpath = os.path.join(scratch, 'values.tsv')
        env_extra = dict(env_extra)
        if 'values' in env_extra:
            write_values(vpath, env_extra.pop('values'))
        env = dict(os.environ)
        env.update(self.base_env(scratch))
        env['MOCK_VALUES'] = clean(vpath)
        env['RUN_CALLS'] = clean(calls)
        env['PF_CALLS'] = clean(pfcalls)
        env.update(env_extra)
        p = subprocess.Popen(['bash', clean(self.entry)], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=env)
        out = p.communicate()[0].decode('utf-8', 'replace')
        nrun = len([l for l in open(calls) if l.strip()])
        npf = len([l for l in open(pfcalls) if l.strip()])
        csv = os.path.join(scratch, 'entry.csv')
        return dict(rc=p.returncode, out=out, runner=nrun, preflight=npf,
                    csv=(csv if os.path.exists(csv) else None), scratch=scratch)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    proj = os.path.dirname(here)
    argv = sys.argv[1:]
    out_csv = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(
        proj, 'results', 'evidence', 'sc1_r2d1_entry_selftest.csv')

    H = Harness(proj)
    base = good_values()
    good = {'RUN': '1', 'QODER_SIM_AUTHORISED': '1', 'QODER_PDK_LIB': clean(H.fake_lib)}
    results = []

    def record(case, rc, runner, rows, met, note):
        results.append([case, str(rc), str(runner), str(rows), 'yes' if met else 'no',
                        'PASS' if met else 'FAIL', note, FUTURE])
        print('%-26s rc=%-4s runner_calls=%-2s rows=%-3s %s' % (case, rc, runner, rows,
                                                                'PASS' if met else 'FAIL'))
        if not met:
            print('   note: %s' % note)

    def check(case, env_extra, table, want_ok, note, want_rows=None, want_runner=None,
              want_rowspec=None, want_absent=None):
        r = H.invoke(dict(env_extra, values=table), 's_' + case)
        rows = read_csv(r['csv'])
        body = rows[1:] if rows else []
        reasons = []
        token = 'S1_R2D_REGRESSION: %s' % ('PASS' if want_ok else 'FAIL')
        if token not in r['out']:
            # an entry that aborts (unbound variable, lost cd, ...) would otherwise look like a
            # refusal: the script has to have reached its own verdict line for the case to mean
            # anything, and it must not have printed a harness error on the way.
            reasons.append('the entry never printed its own "%s" line' % token)
        if 'unbound variable' in r['out'] or 'HARNESS_ERROR' in r['out']:
            reasons.append('harness error in the entry output')
        if want_ok and r['rc'] != 0:
            reasons.append('expected exit 0, got %d' % r['rc'])
        if not want_ok and r['rc'] == 0:
            reasons.append('expected a non-zero exit, got 0')
        if want_runner is not None and r['runner'] != want_runner:
            reasons.append('runner called %d times, expected %d' % (r['runner'], want_runner))
        if want_rows is not None and len(body) != want_rows:
            reasons.append('CSV body rows %d, expected %d' % (len(body), want_rows))
        # every failure case must fail for the reason it claims, not because something else broke
        for (cid, cols) in (want_rowspec or []):
            hit = [row for row in body if row[0] == cid]
            if not hit:
                reasons.append('no row with case_id %s' % cid)
                continue
            for (col, want) in cols.items():
                if want not in hit[0][col]:
                    reasons.append('row %s column %d is %r, expected %r'
                                   % (cid, col, hit[0][col], want))
        for needle in list(want_absent or []) + ['MOCK_MISS']:
            # MOCK_MISS would mean the mock table itself was incomplete: the case would then be
            # failing because of the harness, not because of the assertion under test.
            if any(needle in ','.join(row) for row in body):
                reasons.append('%s must not appear in any row' % needle)
        met = not reasons
        if reasons:
            print('   ---- entry output ----\n%s' % r['out'])
        record(case, r['rc'], r['runner'], len(body), met, note + ('' if met else ' | ' + '; '.join(reasons)))
        return r, body

    # ------------------------------------------------------------------ the guards
    dry = H.invoke({}, 's_guards_dry')
    decks = os.listdir(dry['scratch'])
    met = ('DRY_RUN' in dry['out'] and dry['rc'] == 0 and dry['runner'] == 0 and dry['preflight'] == 0
           and not [d for d in decks if d.endswith('.scs')])
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

    # ------------------------------------------------------------- the happy mock path
    n_expect = 4 + 1 + 5 + 5 + 1
    r, body = check('all_good', good, base, True,
                    'correct synthetic data reaches every assertion and exits 0',
                    want_rows=n_expect, want_runner=4)
    ids = [row[0] for row in body]
    widths = sorted(set(len(row) for row in read_csv(r['csv'])))
    unresolved = [row[0] for row in body if row[7] == 'NOT_MEASURED']
    verdicts = dict((row[0], row[12]) for row in body)
    met = (widths == [14] and len(ids) == len(set(ids)) == n_expect and not unresolved
           and verdicts.get('F1_blank_clamped') == 'DETECTED'
           and verdicts.get('stimulus_sanity') == 'PASS'
           and all(v == 'PASS' for k, v in verdicts.items()
                   if k.startswith('truth_') or k.startswith('T')))
    print('csv_structure: widths=%s unique_ids=%s/%s unresolved=%s' % (widths, len(set(ids)),
                                                                       len(ids), unresolved))
    record('csv_structure', r['rc'], r['runner'], len(body), met,
           'header plus 14 fields per row, unique case ids, every assertion actually evaluated')

    # -------------------------------------------------------------- failure injections
    check('preflight_refuses', dict(good, PF_RC='1'), base, False,
          'a refused preflight stops the deck and the runner is never called', want_runner=0,
          want_rows=4,
          want_rowspec=[('dc_blank0', {1: 'truth', 2: 'PRECHECK_FAIL', 7: 'NOT_MEASURED',
                                        11: '1', 12: 'FAIL'}),
                        ('dc_blank1.8', {2: 'PRECHECK_FAIL', 12: 'FAIL'}),
                        ('T1', {2: 'PRECHECK_FAIL'}),
                        ('F1_blank_clamped', {2: 'PRECHECK_FAIL', 12: 'FAIL'})])
    check('runner_bad_rc', dict(good, MR_RC='1'), base, False,
          'a runner exit code is SIM_FAIL, not a verdict',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL', 10: '1', 12: 'FAIL'})])
    check('runner_two_tokens', dict(good, MR_TOKENS='2'), base, False,
          'the success token must be unique, not merely present',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL', 12: 'FAIL'})])
    check('runner_no_datafile', dict(good, MR_DATAFILE=''), base, False,
          'no reported data file means no row; the STALE raw is never used',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL'})], want_absent=['STALE'])
    check('runner_log_errors', dict(good, MR_ERRHITS='3'), base, False,
          'error_hits != 0 is SIM_FAIL',
          want_rowspec=[('dc_blank0', {2: 'SIM_FAIL'})])

    t = dict(base)
    t[('raw_dc0', 'sweep=0', 'en')] = 'rc:3'
    check('reader_error', good, t, False,
          'reader exit 3 on a truth row gives READ_FAIL + NOT_MEASURED, no number is parsed',
          want_rowspec=[('truth_Q1_BLANK0', {7: 'NOT_MEASURED', 9: '1', 12: 'FAIL',
                                             13: 'reader refused'})])

    t = dict(base)
    t[('raw_dc18', 'sweep=0', 'blank')] = 'rc:4'
    check('stimulus_read_fail', good, t, False,
          'a row whose own stimulus cannot be read is not evidence, even when en is right',
          want_rowspec=[('truth_Q1_BLANK1', {7: '0.04', 12: 'FAIL', 13: 'blank unreadable'})])

    t = dict(base)
    t[('raw_dc0', 'sweep=0', 'en')] = '0.12'
    check('truth_wrong_value', good, t, False,
          'en contradicting its expected ON state fails that row and the run',
          want_rowspec=[('truth_Q1_BLANK0', {7: '0.12', 12: 'FAIL'})])

    t = dict(base)
    t[('raw_dc18', 'sweep=1.8', 'blank')] = '0'
    check('stimulus_mismatch', good, t, False,
          'BLANK not reading back at its label voids the row',
          want_rowspec=[('truth_Q0_BLANK1', {12: 'FAIL', 13: 'blank read 0 != label 1.8'})])

    t = dict(base)
    t[('raw_tran', 'win=520n..620n:min', 'en')] = '0.31'
    check('window_fail', good, t, False, 'a failing transient window fails the run',
          want_rowspec=[('T2', {7: '0.31', 12: 'FAIL'}), ('T1', {12: 'PASS'})])

    t = dict(base)
    t[('raw_tran', 'win=520n..620n:max', 'q')] = 'rc:3'
    check('window_states_read_fail', good, t, False,
          'window evidence signals must be readable or the row is incomplete',
          want_rowspec=[('T2_states', {9: '1', 12: 'FAIL', 13: 'READ_FAIL'})])

    t = dict(base)
    t[('raw_fault', 'win=400n..455n:max', 'en')] = '0.02'
    check('toothless_fault', good, t, False,
          'T1 passing on the BLANK-rewired data means the checker cannot fail',
          want_rowspec=[('F1_blank_clamped', {12: 'CHECKER_TOOTHLESS'})])

    t = dict(base)
    t[('raw_dc0', 'sweep=1.8', 'en')] = '1.6'
    check('fault_cannot_mask_truth', good, t, False,
          'a detected fault elsewhere must not hide a failing normal truth row',
          want_rowspec=[('truth_Q0_BLANK0', {12: 'FAIL'}), ('F1_blank_clamped', {12: 'DETECTED'})])

    hdr = ('case_id entry_rc runner_calls csv_rows expectation_met verdict note data_class').split(' ')
    with io.open(out_csv, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u','.join(u'"%s"' % h for h in hdr) + u'\n')
        for row in results:
            f.write(u','.join(u'"%s"' % c for c in row) + u'\n')
    bad = [r for r in results if r[5] != 'PASS']
    print('ENTRY_SELFTEST cases=%d failed=%d -> %s   (%s)'
          % (len(results), len(bad), 'PASS' if not bad else 'FAIL', out_csv))
    print('NOTE: every value above is SYNTHETIC/MOCK; no simulator was called and this is not an S1 '
          'circuit regression.')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
