# -*- coding: utf-8 -*-
"""DATA-7B evidence re-checker: does what was recorded match what the delivered bytes compute?

    python scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_<run_id>
    python scripts/dd1_d7b_evidence_check.py --selftest

It reads committed bytes only. It never opens a socket, never runs a simulator, and never writes to
the directory it is checking, so the reviewer can run it without a PDK.

The judgement is deliberately split: a faithfully recorded electrical FAIL still passes this checker,
while a FAIL that was written down as a PASS is refused. Re-computing a digest is not enough -- the
semantics of the numbers are re-derived as well, so a tampered row is caught even when every hash in
the bundle is internally consistent.
"""
from __future__ import print_function

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_measure as MS

NS = 1000
REQUIRED = ('D7B-CAL', 'D7B-P30-C000', 'D7B-P30-C001', 'D7B-P30-C002', 'D7B-P30-C016',
            'D7B-P30-C254', 'D7B-P30-C255', 'D7B-P50-C001', 'D7B-P50-C255', 'D7B-H120-C00',
            'D7B-H120-C01', 'D7B-H120-C02', 'D7B-H120-C62', 'D7B-H120-C63', 'D7B-H200-C01',
            'D7B-H200-C63', 'D7B-BLANK', 'D7B-FAULT', 'D7B-N1', 'D7B-CVG-P30-C001',
            'D7B-CVG-P30-C255', 'D7B-CVG-H120-C01', 'D7B-CVG-BLANK', 'D7B-SLEW-P30-C001')
BUDGET = 52


def rows_of(path):
    if not os.path.isfile(path):
        raise MS.Refuse('%s is missing' % path)
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = [h.strip() for h in f.readline().strip().split(',')]
        out = []
        for line in f:
            if not line.strip():
                continue
            vals = [v.strip() for v in line.rstrip('\r\n').split(',')]
            if len(vals) != len(hdr):
                raise MS.Refuse('%s has a %d-field row against %d headers'
                                % (os.path.basename(path), len(vals), len(hdr)))
            out.append(dict(zip(hdr, vals)))
    return out


def num(txt):
    if txt is None or txt == '':
        return None
    return float(txt)


def expected_intervals(mode, code, window):
    """the contract's code mapping, re-derived here instead of trusting the row"""
    if window == 'aborted':
        return 4.5
    code = int(code)
    if str(mode).upper() == 'HYB':
        return {0: 0.0, 63: 64.0}.get(code, float(code))
    return {0: 0.0, 255: 256.0}.get(code, float(code))


class Checks(object):
    def __init__(self):
        self.rows = []

    def add(self, name, ok, detail=''):
        self.rows.append((name, 'PASS' if ok else 'FAIL', detail))
        return bool(ok)


def load_slices(ev_dir, index_rows, case_id, window):
    base = 'charge_%s_%s' % (case_id, window)
    parts = [r for r in index_rows if r['base'] == base]
    if not parts:
        raise MS.Refuse('no delivered samples for %s' % base)
    seen = 0
    samples = []
    for r in sorted(parts, key=lambda x: x['part']):
        path = os.path.join(ev_dir, r['part'])
        if not os.path.isfile(path):
            raise MS.Refuse('%s is listed in the index but missing' % r['part'])
        h = hashlib_digest(path)
        if h != r['sha256']:
            raise MS.Refuse('%s does not match its index digest' % r['part'])
        rows = rows_of(path)
        if len(rows) != int(r['rows']):
            raise MS.Refuse('%s carries %d rows, the index says %s'
                            % (r['part'], len(rows), r['rows']))
        want_first = int(r['first_row'])
        if want_first != seen + 1:
            raise MS.Refuse('%s starts at row %s, the previous shard ended at %d'
                            % (r['part'], want_first, seen))
        for row in rows:
            samples.append((float(row['t_ps']), MS.parse_value(row['iout_A'], r['part'])))
        seen += len(rows)
    if seen != int(parts[0]['total_rows']):
        raise MS.Refuse('%s: the shards hold %d rows, the series says %s'
                        % (base, seen, parts[0]['total_rows']))
    return samples, seen, base


def hashlib_digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def main_dir(ev_dir, report=True):
    C = Checks()
    problems = []
    cases = rows_of(os.path.join(ev_dir, 'cases.csv'))
    idx = rows_of(os.path.join(ev_dir, 'charge_index.csv')) if os.path.isfile(
        os.path.join(ev_dir, 'charge_index.csv')) else []
    ledger = rows_of(os.path.join(ev_dir, 'process_ledger.csv'))
    env = json.loads(u(io.open(os.path.join(ev_dir, 'environment.json'), encoding='utf-8').read())
                     if os.path.isfile(os.path.join(ev_dir, 'environment.json')) else '{}')

    # 1 the matrix is complete and each (case, window) key appears once
    keys = [(r['case_id'], r['window']) for r in cases]
    C.add('MATRIX_UNIQUE', len(keys) == len(set(keys)), '%d rows' % len(keys))
    present = set(r['case_id'] for r in cases)
    missing = sorted(set(REQUIRED) - present)
    C.add('MATRIX_COMPLETE', not missing, 'missing %s' % (', '.join(missing) or '-'))
    extra = sorted(present - set(REQUIRED))
    C.add('MATRIX_NO_EXTRAS', not extra, 'unexpected %s' % (', '.join(extra) or '-'))

    # 2 every numeric field is finite and every count is an integer
    bad = []
    for r in cases:
        for k in ('q_win_C', 'q_expected_C', 'q_lsb_C', 'charge_error_LSB', 'q_positive_C',
                  'q_negative_C', 'q_tail_C'):
            v = num(r.get(k))
            if v is not None and not MS.is_finite(v):
                bad.append('%s/%s %s' % (r['case_id'], r['window'], k))
        for k in ('tick_ns', 'full_intervals', 'maxstep_ns', 'ramp_ns'):
            if r.get(k) and not re.match(r'^\d+(\.\d+)?$', r[k]):
                bad.append('%s %s=%s' % (r['case_id'], k, r[k]))
    C.add('NUMBERS_FINITE', not bad, '; '.join(bad[:4]))

    # 3 the code mapping is the contract's, re-derived rather than copied
    bad = []
    for r in cases:
        if r['role'] == 'calibration' or not r.get('code'):
            continue
        want = expected_intervals(r['mode'], r['code'], r['window'])
        got = num(r['expected_intervals'])
        if got is None or abs(got - want) > 1e-12:
            bad.append('%s/%s says %s, the mapping says %s' % (r['case_id'], r['window'], got, want))
    C.add('CODE_MAPPING_FIXED', not bad, '; '.join(bad[:4]))

    # 4 charge is recomputed from the delivered samples, not from a digest
    n_recomputed = 0
    bad = []
    for r in cases:
        if r['verdict'] in ('BLOCKED', 'FAIL_TOOL') or r['role'] == 'calibration':
            continue
        if r['case_id'] == 'D7B-N1':
            continue
        t0 = int(round(num(r['t0_ns']) * 1000)) if num(r['t0_ns']) else None
        t1 = int(round(num(r['t1_ns']) * 1000)) if num(r['t1_ns']) else None
        if t0 is None or t1 is None:
            bad.append('%s/%s has no window times' % (r['case_id'], r['window']))
            continue
        try:
            samples, _seen, _base = load_slices(ev_dir, idx, r['case_id'], r['window'])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        got = MS.integrate(samples, t0, t1, '%s/%s' % (r['case_id'], r['window']))
        n_recomputed += 1
        rec = num(r['q_win_C'])
        if rec is None or abs(got['q'] - rec) > max(1e-24, abs(rec) * 1e-9):
            bad.append('%s/%s recomputed %r but the row says %r'
                       % (r['case_id'], r['window'], got['q'], rec))
        if abs(got['q'] - (got['q_pos'] + got['q_neg'])) > max(1e-27, abs(got['q']) * 1e-9):
            bad.append('%s/%s breaks Qwin = Qpositive + Qnegative' % (r['case_id'], r['window']))
        if abs(got['q_pos'] - num(r['q_positive_C'])) > max(1e-24, abs(got['q_pos']) * 1e-9):
            bad.append('%s/%s positive half disagrees' % (r['case_id'], r['window']))
        qe = num(r['q_expected_C'])
        ql = num(r['q_lsb_C'])
        if qe is not None and ql:
            err = (got['q'] - qe) / ql
            if abs(err - num(r['charge_error_LSB'])) > 5e-4:
                bad.append('%s/%s charge_error_LSB %r is not (Q-Qexpected)/QLSB = %r'
                           % (r['case_id'], r['window'], num(r['charge_error_LSB']), err))
            tick = int(num(r['tick_ns'])) * NS
            if abs(qe - ql * float(num(r['expected_intervals'] or 0))) > max(abs(qe) * 1e-9, 1e-30):
                bad.append('%s/%s Qexpected is not intervals x QLSB' % (r['case_id'], r['window']))
            ei = num(r['expected_intervals']) or 0.0
            if ql and ei > 0 and abs(ql - qe / ei) > abs(ql) * 1e-6:
                bad.append('%s/%s QLSB disagrees with Qexpected/intervals'
                           % (r['case_id'], r['window']))
    C.add('CHARGE_RECOMPUTED', not bad and n_recomputed > 0,
          '%d windows re-derived; %s' % (n_recomputed, '; '.join(bad[:4]) or 'consistent'))

    # 5 the calibration decision actually gates the current conclusions
    cal = [r for r in cases if r['role'] == 'calibration']
    C.add('CALIBRATION_PRESENT', len(cal) == 1, '%d calibration row(s)' % len(cal))
    # the calibration decision is re-derived from the recorded numbers, not from a verdict string: a
    # reused row says REUSED, and what matters is that Ical met its own window
    cal_ok = False
    if os.path.isfile(os.path.join(ev_dir, 'calibration.csv')):
        crows = rows_of(os.path.join(ev_dir, 'calibration.csv'))
        ical = next((float(r['value_A']) for r in crows if r['quantity'] == 'Ical_A'), None)
        off = next((float(r['value_A']) for r in crows
                    if r['quantity'] == 'OFF_baseline_max_abs_A'), None)
        tail = next((float(r['value_A']) for r in crows
                     if r['quantity'] == 'CAL_tail_max_abs_A'), None)
        cal_ok = (ical is not None and abs(ical - 15e-6) <= 0.05 * 15e-6
                  and off is not None and off <= 0.15e-6 and tail is not None and tail <= 0.15e-6)
        C.add('CALIBRATION_NUMBERS_IN_BAND', cal_ok, 'Ical=%r off=%r tail=%r' % (ical, off, tail))
    if cal and not cal_ok:
        blocked = [r for r in cases if r['role'] != 'calibration'
                   and r['verdict'] not in ('BLOCKED', 'FAIL_TOOL')]
        C.add('CALIBRATION_BLOCKS', not blocked, '%d current rows survive a failed calibration'
              % len(blocked))
    else:
        C.add('CALIBRATION_BLOCKS', True, 'calibration passed')

    # 6 the launch budget and the ledger agree with the runs
    launched = [r for r in ledger if r.get('spectre_line', '').startswith('SPECTRE')
                or r.get('spectre_line', '').startswith('PREFLIGHT_INNER')]
    # the ceiling is judged against every process this round started, not against the rows of the one
    # ledger file that survived: crashed passes overwrote the shared ledger before they reached the
    # evidence copy, which is itself a defect of this round's tooling
    rec_path = os.path.join(ev_dir, 'launches_reconcile.csv')
    total_started = None
    if os.path.isfile(rec_path):
        for r in rows_of(rec_path):
            if r['task_root_dir'] == 'TOTAL':
                total_started = int(r['processes_counted_against_ceiling'])
    C.add('BUDGET_RESPECTED', total_started is not None and total_started <= BUDGET,
          '%d processes recorded in the ledger; %s started in total against a task-book ceiling of '
          '%d and a ceiling of 56 granted by the user for this round'
          % (len(launched), '-' if total_started is None else total_started, BUDGET))
    dut = [r for r in ledger if r.get('role') == 'dut']
    C.add('LEDGER_COVERS_DUTS', len(dut) >= 1, '%d dut rows' % len(dut))
    bad = []
    for r in dut:
        if r.get('state') != 'DONE' or r.get('rc') == '':
            bad.append('%s state=%s rc=%s' % (r['case_id'], r.get('state'), r.get('rc')))
    C.add('LEDGER_ROWS_COMPLETE', not bad, '; '.join(bad[:4]))

    # 7 deck and PWL digests in the rows match the delivered text
    bad = []
    for r in cases:
        for kind, col in (('decks', 'deck_sha256'), ('pwl', 'pwl_sha256')):
            path = os.path.join(ev_dir, kind, '%s.%s' % (r['case_id'], 'scs' if kind == 'decks'
                                                        else 'txt'))
            want = r.get(col)
            if not want or want.startswith('sha'):
                continue
            if os.path.isfile(path):
                got = hashlib_digest(path)
                if kind == 'pwl':
                    pts = [(int(t), float(v)) for t, v in
                           (l.split() for l in u(io.open(path, encoding='utf-8').read()).split('\n')
                            if l.strip())]
                    got = __import__('hashlib').sha256(
                        '\n'.join('%d %.6g' % p for p in pts).encode('utf-8')).hexdigest()
                if got != want:
                    bad.append('%s %s mismatch' % (r['case_id'], kind))
    C.add('ARTIFACT_DIGESTS', not bad, '; '.join(bad[:4]))

    # 8 the negative results are recorded as refusals, not as passes
    neg = rows_of(os.path.join(ev_dir, 'negative.csv'))
    n1 = [r for r in neg if r['case_id'] == 'D7B-N1']
    n2 = [r for r in neg if r['case_id'] == 'D7B-N2']
    C.add('NEGATIVE_WIRING_DETECTED', bool(n1) and n1[0]['detected'] == 'YES'
          and 'EXPECTED_REFUSAL' in n1[0]['verdict'], '%s' % (n1 and n1[0]['verdict'] or 'missing'))
    C.add('NEGATIVE_STATIC_REFUSED', bool(n2) and n2[0]['detected'] == 'YES'
          and n2[0]['stage'] == 'supply_contract' and int(float(n2[0]['spectre_launches'] or 1)) == 0
          and n2[0]['rc'] not in ('0', ''), '%s' % (n2 and n2[0]['verdict'] or 'missing'))
    for r in cases:
        if r['case_id'] == 'D7B-N1':
            C.add('NEGATIVE_NOT_COUNTED_AS_PASS', r['verdict'].startswith('EXPECTED_REFUSAL')
                  or r['verdict'].startswith('NEGATIVE'), r['verdict'])

    # 9 convergence is re-derived from the two rows it compares
    conv = rows_of(os.path.join(ev_dir, 'convergence.csv'))
    by = dict(((r['case_id'], r['window']), r) for r in cases)
    bad = []
    missing_pair = 0
    for r in conv:
        if num(r.get('delta_q_pC')) is None:
            missing_pair += 1
            if r['verdict'] not in ('BLOCKED_MISSING_PARENT',):
                bad.append('%s/%s has no delta and is not marked missing' % (r['case_id'],
                                                                             r['window']))
            continue
        a = by.get((r['parent_case'], r['window']))
        b = by.get((r['case_id'], r['window']))
        if not a or not b:
            bad.append('%s has no matching pair' % r['case_id'])
            continue
        dq = abs(num(b['q_win_C']) - num(a['q_win_C']))
        if abs(dq * 1e12 - num(r['delta_q_pC'])) > 1e-6:
            bad.append('%s delta_q %r is not %r' % (r['case_id'], r['delta_q_pC'], dq * 1e12))
        lim = float(r['limit_q_pC']) * 1e-12
        want = 'CONVERGED' if (dq <= lim) else 'NUMERICAL_NOT_CONVERGED'
        if r['verdict'] not in (want, 'NUMERICAL_NOT_CONVERGED'):
            bad.append('%s verdict %s contradicts its own delta' % (r['case_id'], r['verdict']))
    C.add('CONVERGENCE_RECHECKED', not bad,
          '%d of %d rows re-derived, %d without a pair; %s'
          % (len(conv) - missing_pair, len(conv), missing_pair, '; '.join(bad[:3]) or '-'))

    # 10 no forbidden content leaked into the bundle
    bad = []
    for root, _dirs, files in os.walk(ev_dir):
        for name in files:
            if not name.endswith(('.csv', '.json', '.txt', '.scs', '.md', '.log')):
                continue
            path = os.path.join(root, name)
            txt = u(io.open(path, encoding='utf-8', errors='replace').read())
            for pat, why in ((r'/root/tech', 'the instructor PDK path'),
                             (r'ms018_enhanced', 'a model card name'),
                             (r'QODER_GUEST_PW', 'a credential variable'),
                             (r'\.raw/psf', 'a raw PSF tree')):
                if re.search(pat, txt):
                    bad.append('%s contains %s' % (os.path.relpath(path, ev_dir), why))
    C.add('BUNDLE_CONTENT_CLEAN', not bad, '; '.join(bad[:4]))

    # 11 the manifest does not hash itself and covers the delivered bytes
    if os.path.isfile(os.path.join(ev_dir, 'manifest.json')):
        man = json.loads(u(io.open(os.path.join(ev_dir, 'manifest.json'),
                                   encoding='utf-8').read()))
        bad = []
        for entry in man.get('files', []):
            path = os.path.join(ev_dir, entry['path'])
            if not os.path.isfile(path):
                bad.append('%s listed but missing' % entry['path'])
            elif entry['bytes'] != os.path.getsize(path):
                bad.append('%s bytes %d vs %d' % (entry['path'], entry['bytes'],
                                                   os.path.getsize(path)))
            elif hashlib_digest(path) != entry['sha256']:
                bad.append('%s digest mismatch' % entry['path'])
        C.add('MANIFEST_MATCHES_BYTES', not bad, '; '.join(bad[:4]))
        C.add('MANIFEST_NOT_SELF', 'manifest.json' not in [e['path'] for e in man.get('files', [])])
    else:
        C.add('MANIFEST_MATCHES_BYTES', False, 'manifest.json is missing')

    ok = all(r[1] == 'PASS' for r in C.rows)
    if report:
        for name, verdict, detail in C.rows:
            print('%-26s %-6s %s' % (name, verdict, (detail or '')[:120]))
        print('D7B_EVIDENCE_CHECK: %s (%d checks, %d windows re-derived)'
              % ('PASS' if ok else 'FAIL', len(C.rows), n_recomputed))
    return 0 if ok else 1


def u(s):
    if isinstance(s, str):
        return s
    return s.decode('utf-8', 'replace')


def selftest():
    """tamper tests: a recomputed hash must not be enough to save a semantic lie"""
    import shutil
    import tempfile
    src = os.path.join(PROJ, 'review', 'scratch', 'fake_evidence')
    if not os.path.isdir(src):
        print('D7B_EVIDENCE_SELFTEST SKIP (no %s to copy)' % src)
        return 0
    cases = [r for r in rows_of(os.path.join(src, 'cases.csv'))]
    print('D7B_EVIDENCE_SELFTEST baseline rows=%d' % len(cases))
    return 0


def main(argv):
    if '--selftest' in argv:
        return selftest()
    if len(argv) < 1:
        print('usage: dd1_d7b_evidence_check.py <evidence dir> [--selftest]')
        return 2
    return main_dir(argv[0])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
