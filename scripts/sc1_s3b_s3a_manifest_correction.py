#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-B 2.1: the S3-A manifest's W_m column, corrected from the bytes that ran.

    python scripts/sc1_s3b_s3a_manifest_correction.py                 # write the correction CSV
    python scripts/sc1_s3b_s3a_manifest_correction.py --selftest       # arithmetic only
    python scripts/sc1_s3b_s3a_manifest_correction.py --stdout         # print, write nothing

What was wrong. `sc1_s3a_manifest.csv` names a column `W_m` but each of its nine rows stores the
micrometre figure (5/10/20/50/100). Nothing about the devices themselves was wrong: `build_deck()`
multiplies by 1e-6 before writing `w=`, so the decks that ran are in metres, and `w_total_m` was
already written in metres. The defect is one column of the manifest, and the visible symptom was this
project's own verifier printing `W_best=1e+08 um` -- it multiplied an already-micrometre token by 1e6.

Why the correction is provable rather than asserted. Each of the nine decks is rebuilt offline from
the generator, and a rebuild only hashes to the delivered `deck_sha256` if the width, the device count
and the whole rest of the file are the ones that ran. So the per-device width used here is taken from
the two columns that are unit-correct (`w_total_m / n_devices`), and the hash equality is the proof
that this reconstruction is the delivered circuit. The shipped text is never edited.

No simulator, no preflight, no reader call, and no write to any delivered S3-A file: the six evidence
files are hashed before and after, and the output name must start with `sc1_s3b_`.
"""
from __future__ import print_function

import csv
import hashlib
import optparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import sc1_s3a_p33_tt as S3A          # noqa: E402  (the generator whose build_deck() defines the decks)

EV = os.path.join('results', 'evidence')
MANIFEST = 'sc1_s3a_manifest.csv'
IDENTITY = 'sc1_s3a_identity.csv'
OUT_NAME = 'sc1_s3b_s3a_manifest_correction.csv'
# every file this round must leave byte-identical; a delivered copy is never rewritten
PROTECTED = ['sc1_s3a_cases.csv', 'sc1_s3a_dc_points.csv', 'sc1_s3a_dyn_samples.csv',
             'sc1_s3a_manifest.csv', 'sc1_s3a_identity.csv', 'sc1_s3a_tail_readings.csv']

HDR = ['run_id', 'case', 'kind', 'deck', 'deck_sha256', 'raw_sha256',
       'original_W_m_token', 'original_token_unit_as_written', 'corrected_W_m', 'W_um',
       'n_devices', 'w_total_m_manifest', 'w_total_m_from_corrected', 'w_total_relation_ok',
       'rebuilt_deck_sha256', 'deck_sha_matches_delivered', 'rebuilt_w_token_m',
       'rebuilt_device_count', 'verdict', 'note']

# the four decks main() derives after the candidate is picked; purpose strings are part of the deck
# text, so they are quoted from scripts/sc1_s3a_p33_tt.py rather than paraphrased
DERIVED = {
    's3a_on_par': dict(kind='on_dc', sweep='ON', gate_v='0.0',
                       purpose='the derived N-parallel candidate at the on bias'),
    's3a_off_par': dict(kind='off_dc', sweep='OFF', gate_v='V33',
                        purpose='the derived candidate in the off state, gate at the rail'),
}


def sha256_file(path):
    try:
        return hashlib.sha256(open(path, 'rb').read()).hexdigest()
    except Exception:
        return 'UNREADABLE'


def read_csv(root, name):
    path = os.path.join(root, EV, name)
    if not os.path.isfile(path):
        return None, path
    rows = list(csv.reader([l for l in open(path, 'rb').read().decode('utf-8', 'replace').split('\n')
                            if l.strip()]))
    return rows, path


def case_for(cid, man_row, w_um, n):
    """the S3-A case dict that produces this deck, or None when the manifest row is not reproducible"""
    known = [c for c in S3A.CASES_A if c['id'] == cid]
    if known:
        return known[0]
    if cid in DERIVED:
        d = DERIVED[cid]
        gate = S3A.V33 if d['gate_v'] == 'V33' else 0.0
        sweep = S3A.ON_SWEEP if d['sweep'] == 'ON' else S3A.OFF_SWEEP
        return S3A.case(cid, kind=d['kind'], w_um=w_um, n=n, sweep=sweep, gate_v=gate,
                        purpose=d['purpose'])
    for nm, r, c, why in S3A.DYN_LOADS:
        if nm == cid:
            return S3A.case(cid, kind='dyn', w_um=w_um, n=n, load=(r, c, why),
                            purpose='the candidate with an independent gate drive and a proxy '
                                    'R||C load')
    return None


def device_widths(deck_txt):
    """the w= token of every mp line in the deck text, not of the comments that describe it"""
    out = []
    for line in deck_txt.split('\n'):
        if re.match(r'^\s*mp\d+\s*\(', line):
            m = re.search(r'\bw=([0-9.eE+-]+)', line)
            if m:
                out.append(m.group(1))
    return out


def correct_rows(root):
    """one row per delivered deck, with the rebuilt-deck proof attached"""
    m = read_csv(root, MANIFEST)[0]
    if not m:
        return [], 'manifest missing'
    idr = read_csv(root, IDENTITY)[0]
    id_by_case = dict((r[1], r) for r in (idr[1:] if idr else []))
    rows, problems = [], []
    for r in m[1:]:
        run_id, cid, kind, deck, dsha, rsha = r[0], r[1], r[2], r[3], r[4], r[5]
        token, n_tok, wtot_tok = r[12], r[13], r[14]
        n = int(float(n_tok))
        wtot = float(wtot_tok)
        w_um = wtot / n * 1e6                    # from the two unit-correct columns
        w_m = wtot / n
        cs = case_for(cid, r, w_um, n)
        if cs is None:
            problems.append('%s: no reproducible case for this row' % cid)
            continue
        txt = S3A.build_deck(cs, 'tt')
        rebuilt = hashlib.sha256(txt.encode('utf-8')).hexdigest()
        wtoks = device_widths(txt)
        dev_count = len(wtoks)
        match = (rebuilt == dsha)
        rel_ok = abs(w_m * n - wtot) <= max(1e-18, abs(wtot) * 1e-9)
        tok_unit = ('um (the defect: the header says metres, the stored figure is micrometres)'
                    if abs(float(token) - w_um) <= max(1e-12, w_um * 1e-9) else
                    ('m (already metres: no correction needed for this row)'
                     if abs(float(token) - w_m) <= max(1e-18, w_m * 1e-9) else 'AMBIGUOUS'))
        if not match:
            problems.append('%s: rebuilt deck hash %s does not equal the delivered %s' %
                            (cid, rebuilt[:16], dsha[:16]))
        if (dev_count != n or S3A.device_count_of(txt) != n or not wtoks
                or len(set(wtoks)) != 1 or abs(float(wtoks[0]) - w_m) > w_m * 1e-9):
            problems.append('%s: rebuilt deck width/count %s/%s disagrees with the manifest %s/%s'
                            % (cid, wtoks[0] if wtoks else '-', dev_count, w_m, n))
        idrow = id_by_case.get(cid)
        if idrow and (idrow[3] != dsha or idrow[5] != rsha):
            problems.append('%s: identity index shas disagree with the manifest row' % cid)
        rows.append([run_id, cid, kind, deck, dsha, rsha,
                     token, tok_unit, S3A.fmt_v(w_m), S3A.fmt_v(w_um), str(n), wtot_tok,
                     S3A.fmt_v(w_m * n), 'PASS' if rel_ok else 'FAIL',
                     rebuilt, 'PASS' if match else 'FAIL', wtoks[0] if wtoks else '',
                     str(dev_count),
                     'CORRECTED_AND_PROVEN' if (match and rel_ok) else 'PROBLEM',
                     'w_total_m = corrected_W_m x n_devices; the deck that ran is reproduced by hash, '
                     'so the geometry is the delivered one and no shipped row was edited'])
    return rows, '; '.join(problems) or 'none'


def selftest():
    ok = True
    # 1. the relation the book demands is arithmetically what the delivered rows hold
    for wtot, n, token in ((5e-06, 1, '5'), (1e-05, 1, '10'), (2e-05, 1, '20'), (5e-05, 1, '50'),
                           (1e-04, 1, '100'), (7e-04, 7, '100')):
        w_m = wtot / n
        good = abs(w_m * n - wtot) < 1e-18 and abs(float(token) - w_m * 1e6) < 1e-9
        print('   relation W=%s n=%d token=%s -> %s' % (wtot, n, token, 'ok' if good else 'BAD'))
        ok = ok and good
    # 2. the old verifier display that started this: token x 1e6 on a 100 um row
    bad_old = 100.0 * 1e6
    new = 7e-04 / 7 * 1e6
    print('   old display would read W_best=%g um; corrected reads W_best=%g um' % (bad_old, new))
    ok = ok and new == 100.0
    # 3. the width written into the device lines is always metres, which is why the decks were never wrong
    txt = S3A.build_deck(S3A.CASES_A[-1], 'tt')
    wt = device_widths(txt)[0]
    print('   deck token for the 100 um case: w=%s (metres) -> %s' % (wt, float(wt) == 1e-04))
    ok = ok and float(wt) == 1e-04 and len(device_widths(txt)) == 1
    print('S3B_UNIT_SELFTEST: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main():
    op = optparse.OptionParser()
    op.add_option('--root', default=PROJ)
    op.add_option('--out', default=os.path.join(PROJ, EV, OUT_NAME))
    op.add_option('--selftest', action='store_true')
    op.add_option('--stdout', action='store_true')
    o = op.parse_args()[0]
    if o.selftest:
        return selftest()

    before = dict((n, sha256_file(os.path.join(o.root, EV, n))) for n in PROTECTED)
    rows, problems = correct_rows(o.root)
    if not rows:
        print('S3B_UNIT_CORRECTION: REFUSED (%s)' % problems)
        return 3
    after = dict((n, sha256_file(os.path.join(o.root, EV, n))) for n in PROTECTED)
    changed = [n for n in PROTECTED if before[n] != after[n] or after[n] == 'UNREADABLE']
    if changed:
        print('S3B_UNIT_CORRECTION: REFUSED (delivered evidence changed under this run: %s)' %
              ','.join(changed))
        return 4
    if problems != 'none':
        print('S3B_UNIT_CORRECTION: REFUSED (%s)' % problems)
        return 5
    base = os.path.basename(o.out)
    if not base.startswith('sc1_s3b_') or base in PROTECTED:
        print('S3B_UNIT_CORRECTION: REFUSED (output %s is not an sc1_s3b_ new file)' % base)
        return 6

    lines = [S3A.S2.csvline(HDR)] + [S3A.S2.csvline(r) for r in rows]
    if o.stdout:
        for line in lines:
            print(line, end='')
        print('# rows=%d problems=%s  (nothing written, --stdout)' % (len(rows), problems))
        return 0
    S3A.S2.write_rows(o.out, rows, HDR)
    before_out = sha256_file(o.out)
    again, _ = correct_rows(o.root)
    same = (again == rows)
    after2 = dict((n, sha256_file(os.path.join(o.root, EV, n))) for n in PROTECTED)
    touched = [n for n in PROTECTED if after2[n] != before[n]]
    print('S3B_UNIT_CORRECTION: OK rows=%d out=%s sha256=%s'
          % (len(rows), os.path.relpath(o.out, PROJ).replace('\\', '/'), before_out[:16]))
    print('S3B_UNIT_CORRECTION: rebuild is deterministic on re-read=%s ; delivered S3-A evidence '
          'touched after the write=%s (%d files re-hashed)' % (same, touched or 'none',
                                                              len(PROTECTED)))
    return 0 if (same and not touched) else 7


if __name__ == '__main__':
    sys.exit(main())
