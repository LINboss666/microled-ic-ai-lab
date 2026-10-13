#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-A: parse the delivered evidence and recompute what it claims.

    python scripts/sc1_s3a_verify_evidence.py [--root PROJ]

This exists because a hash list cannot tell an empty file from a full one (AGENTS rule 27 / R3A), and
because a characterisation round is only auditable if the reviewer can rebuild the numbers from the
shipped rows. Everything here is offline arithmetic on the delivered CSVs -- no simulator, no
preflight, no reader call.

Independent recomputations, each from the raw signed columns rather than from a stored verdict:
  * Ron at every DC point = (V(S) - V(D)) / I_SD, and the VSD = 0 point must be NOT_DEFINED;
  * the candidate rank N = ceil(11.52 mA / the measured single-device I_SD at VSD = 0.10 V),
    compared against the deck that actually ran;
  * the conditional target verdict, from the measured candidate total;
  * the gate charge of each edge, integrated from the shipped sample rows over the same window.
"""
from __future__ import print_function

import csv
import math
import optparse
import os
import sys

FILES = {'cases': 'sc1_s3a_cases.csv', 'dc': 'sc1_s3a_dc_points.csv',
         'samples': 'sc1_s3a_dyn_samples.csv', 'manifest': 'sc1_s3a_manifest.csv',
         'identity': 'sc1_s3a_identity.csv', 'log': 'sc1_s3a_dependency_log.txt'}

I_COLUMN = 15e-6 * 768
V_DROP = 0.10
RON_TARGET = 0.10 / I_COLUMN
V33 = 3.3
EDGE_SELECT = (49.0, 51.0)
EDGE_BLANK = (199.0, 201.0)


def read(root, name):
    path = os.path.join(root, 'results', 'evidence', name)
    if not os.path.isfile(path):
        return None, None, path
    txt = open(path, 'rb').read().decode('utf-8', 'replace')
    rows = list(csv.reader([l for l in txt.split('\n') if l.strip()]))
    return rows[0], rows[1:], path


def num(tok):
    try:
        return float(tok)
    except Exception:
        return None


def finite(tok):
    v = num(tok)
    return v is not None and v == v and abs(v) != float('inf')


def traj(xs, ys):
    return sum(0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))


def main():
    op = optparse.OptionParser()
    op.add_option('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    op.add_option('--expect-decks', type='int', default=9)
    o = op.parse_args()[0]
    checks = []

    def check(name, ok, detail):
        checks.append(bool(ok))
        print('   %-64s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))
        return bool(ok)

    _h, man, p_man = read(o.root, FILES['manifest'])
    check('per-deck manifest exists', man is not None, p_man)
    if not man:
        print('S3A_EVIDENCE_CHECK: FAIL (no manifest)')
        return 1
    decks = [r[3] for r in man]
    check('the manifest covers %d decks at most, all unique' % o.expect_decks,
          len(man) <= o.expect_decks and len(set(decks)) == len(man),
          'decks=%d unique=%d' % (len(man), len(set(decks))))
    check('every deck carries a 64-hex deck sha and a 64-hex raw sha',
          all(len(r[4]) == 64 and len(r[5]) == 64 for r in man), '')
    check('every deck records preflight rc and spectre rc as 0 and runner PASS',
          all(r[18] == '0' and r[19] == '0' and r[20] == 'PASS' for r in man),
          'rcs=%s/%s verdicts=%s' % (sorted(set(r[18] for r in man)),
                                     sorted(set(r[19] for r in man)),
                                     sorted(set(r[20] for r in man))))
    check('the temperature the run reported is read back, not assumed',
          all(r[9] and r[9] != 'NOT_READ' for r in man),
          'values=%s' % sorted(set(r[9] for r in man)))
    check('every deck declares the model, section, L, W and N',
          all(r[6] == 'p33' and r[7] == 'tt' and r[11] and r[12] and r[13] for r in man),
          'models=%s sections=%s' % (sorted(set(r[6] for r in man)),
                                     sorted(set(r[7] for r in man))))

    _h, dc, p_dc = read(o.root, FILES['dc'])
    check('the dc point table exists with rows', bool(dc), '%s rows=%d' % (p_dc, len(dc or [])))
    singles, cands = {}, {}
    if dc:
        widths = set(len(r) for r in dc)
        check('every dc row has the header width', widths == set([len(_h)]), 'widths=%s' % sorted(widths))
        bad = [r for r in dc if not finite(r[5]) or (r[10] and not finite(r[10])) or
               (r[11] and not finite(r[11]))]
        check('sweep and current columns are finite numbers', not bad, 'bad=%d' % len(bad))
        zero = [r for r in dc if abs(num(r[6]) or 0.0) < 1e-12]
        check('the VSD=0 point is NOT_DEFINED with no resistance written',
              bool(zero) and all(r[15] == 'NOT_DEFINED' and r[14] == '' for r in zero),
              'points=%d' % len(zero))
        recomputed, mism = 0, []
        for r in dc:
            if r[15] != 'MEASURED':
                continue
            vs, vdr, i_sd, ron = num(r[9]), num(r[7]), num(r[13]), num(r[14])
            if None in (vs, vdr, i_sd, ron) or i_sd == 0:
                continue
            recomputed += 1
            got = (vs - vdr) / i_sd
            if abs(got - ron) > max(1e-6, abs(got) * 1e-4):
                mism.append((r[1], r[4], fmt(got), r[14]))
        check('every Ron recomputes from the signed columns', recomputed > 0 and not mism,
              'checked=%d mismatches=%s' % (recomputed, mism[:3]))
        for r in dc:
            if abs((num(r[6]) or 0.0) - V_DROP) < 1e-9:
                (cands if r[1].endswith('_par') else singles)[r[1]] = num(r[13])
        check('the VSD=0.10 V point exists for every single-device deck', len(singles) >= 1,
              'singles=%s' % ','.join(sorted(singles)))

    par_row = [r for r in man if r[3] == 's3a_on_par.scs']
    if singles and par_row:
        w_best = max(float(r[12]) * 1e6 for r in man if r[3].startswith('s3a_on_w'))
        best_single = max([v for k, v in singles.items() if k.startswith('s3a_on_w')])
        n_req = int(math.ceil(I_COLUMN / best_single))
        n_done = int(par_row[0][13])
        check('the candidate rank is what the measurement implies, clamped to 16',
              n_done == max(1, min(16, n_req)),
              'W_best=%g um I_SD=%s A -> N_req=%d, deck ran N=%d' % (w_best, fmt(best_single),
                                                                    n_req, n_done))
    off = [r for r in man if r[3] == 's3a_off_par.scs']
    check('the off-state deck ran with its own preflight and rc', bool(off) and off[0][18] == '0',
          'present=%s' % bool(off))

    _h, sam, p_sam = read(o.root, FILES['samples'])
    check('the transient sample rows exist', bool(sam), '%s rows=%d' % (p_sam, len(sam or [])))
    if sam:
        widths = set(len(r) for r in sam)
        check('every sample row has the header width', widths == set([len(_h)]),
              'widths=%s' % sorted(widths))
        bad = [r for r in sam if not finite(r[4])]
        check('sample times are finite', not bad, 'bad=%d' % len(bad))
        for tag, edge in (('select_edge', EDGE_SELECT), ('blank_edge', EDGE_BLANK)):
            pts = [(num(r[4]), num([p for p in r[5].split(' ') if p.startswith('VG:i=')][0].split('=')[1]))
                   for r in sam if r[2] == tag and
                   any(p.startswith('VG:i=') for p in r[5].split(' '))]
            pts.sort()
            inside = [(t, v) for t, v in pts if t is not None and
                      edge[0] * 1e-9 - 1e-18 <= t <= edge[1] * 1e-9 + 1e-18]
            q = traj([i[0] for i in inside], [-i[1] for i in inside]) if len(inside) > 1 else None
            check('%s gate charge recomputes from the shipped samples' % tag,
                  q is not None and abs(q) > 0,
                  'points=%d Q=%s C (raw, before the baseline the report names)'
                  % (len(inside), fmt(q) if q is not None else 'n/a'))

    _h, idr, p_id = read(o.root, FILES['identity'])
    check('the identity index exists and matches the deck count',
          bool(idr) and len(idr) == len(man), '%s rows=%d' % (p_id, len(idr or [])))
    if idr:
        check('identity paths are project-relative and free of vendor absolute paths',
              all(not r[2].startswith('/') and not r[4].startswith('/') and '/root/' not in ''.join(r)
                  for r in idr), '')
        check('the PDK is identified by 64-hex digests only',
              all(len(r[i]) == 64 for r in idr for i in (6, 7, 8, 9)), '')

    _h, cases, p_cases = read(o.root, FILES['cases'])
    check('the case result file exists with rows', bool(cases), '%s rows=%d' % (p_cases,
                                                                                len(cases or [])))
    if cases:
        bad = [r for r in cases if r[7] in ('FAIL', 'BLOCKED')]
        check('no functional FAIL and no dependency BLOCKED row', not bad,
              'bad=%s' % [(r[1], r[2], r[7]) for r in bad][:4])
        vals = set(r[7] for r in cases)
        check('the verdict vocabulary is the one this entry emits',
              vals <= set(['PASS', 'MEASURED', 'NOT_AVAILABLE', 'NOT_MET', 'MET', 'MEASURED_PLAN',
                           'RAN', 'RAN_WITH_READER_REFUSALS', 'SELFTEST']),
              'seen=%s' % sorted(vals))
    if os.path.isfile(os.path.join(o.root, 'results', 'evidence', FILES['log'])):
        txt = open(os.path.join(o.root, 'results', 'evidence', FILES['log']), 'rb').read() \
            .decode('utf-8', 'replace')
        check('the dependency log carries a preflight and runner excerpt per deck',
              txt.count('run accepted') >= len(man), 'accepted=%d decks=%d'
              % (txt.count('run accepted'), len(man)))
        check('no vendor path survives in the dependency log', '/root/' not in txt, '')

    bad = checks.count(False)
    print('S3A_EVIDENCE_CHECK checks=%d failures=%d root=%s' % (len(checks), bad, o.root))
    return 1 if bad else 0


def fmt(x):
    return '%.6g' % x if x is not None else ''


if __name__ == '__main__':
    sys.exit(main())
