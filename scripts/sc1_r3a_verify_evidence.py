#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R3A: parse the delivered R3 evidence and refuse to call a header a delivery.

    python scripts/sc1_r3a_verify_evidence.py [--root PROJ]

R3 reached the repository with two of its four CSVs reduced to a header row, and the round manifest and
the report both asserted "9 rows" and "177 rows". Nothing in the pipeline noticed, because every check
up to now compared FILE HASHES. This tool reads the actual rows, so a future round cannot report a
number its own file does not contain:

  * the per-deck manifest holds exactly 9 data rows, 9 unique case ids, one run_id, and every
    preflight_rc / spectre_rc / verdict column is populated;
  * every case the 428-row result file judges appears in the manifest and vice versa;
  * the waveform sample file has data rows, one consistent column count, finite sample times and finite
    signal values, and its deck hashes equal the manifest's;
  * the identity index reports every deck hash matching what is on disk and every raw hashed;
  * each propagation event's delay recomputes from the exported crossing times to within the row's own
    print precision, and its attribution bound agrees with the exported bound.

It runs offline on either environment and calls nothing: no simulator, no preflight, no runner.
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
EVID = ('results', 'evidence')

FILES = {'cases': 'sc1_r3_chain_cases.csv',
         'man': 'sc1_r3_chain_manifest.csv',
         'samples': 'sc1_r3_waveform_samples.csv',
         'identity': 'sc1_r3_delivery_identity.csv'}


def read_rows(root, name):
    path = os.path.join(root, *(EVID + (name,)))
    if not os.path.isfile(path):
        return None, None, path
    with open(path, 'rb') as f:
        txt = f.read().decode('utf-8', 'replace')
    rows = list(csv.reader([l for l in txt.split('\n') if l.strip()]))
    return rows[0], rows[1:], path


def sha_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def finite(tok):
    try:
        v = float(tok)
    except Exception:
        return False
    return v == v and abs(v) != float('inf')


def main():
    op = optparse.OptionParser()
    op.add_option('--root', default=PROJ)
    op.add_option('--expect-cases', type='int', default=9)
    o = op.parse_args()[0]
    checks = []

    def check(name, ok, detail):
        checks.append(bool(ok))
        print('   %-62s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))

    hdr_m, man, p_man = read_rows(o.root, FILES['man'])
    check('per-deck manifest exists', man is not None, p_man)
    if not man:
        print('R3A_EVIDENCE_CHECK: FAIL (no manifest to read)')
        return 1
    check('manifest has %d data rows, not a header alone' % o.expect_cases,
          len(man) == o.expect_cases, 'rows=%d bytes=%d' % (len(man), os.path.getsize(p_man)))
    cases = [r[1] for r in man]
    check('the manifest cases are unique', len(set(cases)) == len(cases),
          'unique=%d' % len(set(cases)))
    check('one run_id across the delivered batch', len(set(r[0] for r in man)) == 1,
          ','.join(sorted(set(r[0] for r in man))))
    cols = [10, 11, 12, 15]
    check('preflight/spectre/runner/verdict columns are populated',
          all(all(r[i] for i in cols) for r in man),
          'rc=%s/%s verdicts=%s' % (sorted(set(r[10] for r in man)),
                                    sorted(set(r[11] for r in man)),
                                    sorted(set(r[15] for r in man))))

    _h, cres, _p = read_rows(o.root, FILES['cases'])
    check('the 428-row result file exists', cres is not None, '')
    if cres:
        judged = set(r[2] for r in cres if r[1] == 'R3_WINDOW_STATE')
        check('every judged case is in the manifest and vice versa', judged == set(cases),
              'judged=%d manifest=%d diff=%s' % (len(judged), len(set(cases)),
                                                 ','.join(sorted(judged ^ set(cases))) or 'none'))

    hdr_s, sam, p_sam = read_rows(o.root, FILES['samples'])
    check('waveform samples exist with data rows', bool(sam), '%s rows=%d' % (p_sam, len(sam or [])))
    if sam:
        widths = set(len(r) for r in sam)
        # set([...], not {...}): the guest's python 2.6 old parser rejects a set literal in this
        # position, and this file must run on both environments
        check('every sample row has the %d-column header width' % len(hdr_s),
              widths == set([len(hdr_s)]), 'widths=%s' % sorted(widths))
        times = [r[4] for r in sam if r[4]]
        check('sample times are present and finite', bool(times) and all(finite(t) for t in times),
              'times=%d' % len(times))
        vals = [kv.split('=', 1)[1] for r in sam if r[2] in ('segment', 'window_samples')
                for kv in r[5].split(' ') if '=' in kv]
        check('sampled signal values parse to finite numbers', bool(vals) and
              all(finite(v) for v in vals),
              'values=%d non-finite=%d' % (len(vals), len([v for v in vals if not finite(v)])))
        check('sample deck hashes equal the manifest deck hashes',
              set(r[7] for r in sam if r[7]) == set(r[3] for r in man), '')

    _h, ident, p_id = read_rows(o.root, FILES['identity'])
    check('identity index exists and covers the batch', bool(ident) and len(ident) == len(man),
          'rows=%d' % len(ident or []))
    if ident:
        # the identity column is the guest-measured fact; where a copy also holds the deck files, this
        # check re-reads them. A review bundle ships the CSVs but not cadence_work/, so "absent here"
        # is a different fact from "different bytes" and must not be reported as a mismatch.
        by_sha = dict((r[1], r[3]) for r in man)
        on_disk, shipped, absent = 0, 0, 0
        for r in ident:
            path = os.path.join(o.root, *r[2].split('/'))
            if not os.path.isfile(path):
                absent += 1
                continue
            shipped += 1
            on_disk += 1 if sha_of(path) == by_sha.get(r[1]) else 0
        check('the identity index records every delivered deck as hash-matched',
              all(r[5] == 'OK' for r in ident),
              'not-OK=%s' % (','.join(r[1] for r in ident if r[5] != 'OK') or 'none'))
        check('decks present in this copy re-hash to their manifest values',
              shipped == 0 or on_disk == shipped,
              're-hashed=%d present=%d absent-in-this-copy=%d' % (on_disk, shipped, absent))
        check('every raw data file is hashed, none missing',
              all(r[7] not in ('', 'MISSING') for r in ident), '')

    # the recomputation a reviewer would do: the exported crossing times must give the native delay
    prop = {}
    for r in (cres or []):
        if r[1] != 'R3_PROPAGATION_50_50':
            continue
        m = re.search(r't_in=([\d.e+-]+) t_out=([\d.e+-]+) delta=([\d.]+) ns'
                      r'.*?t_next=([\d.e+-]+|END_OF_DATA)', r[5])
        if m:
            prop[r[2] + '|' + r[3]] = (float(m.group(1)), float(m.group(2)), float(m.group(3)),
                                       m.group(4))
    n = agree = 0
    for r in (sam or []):
        if r[2] != 'event_crossing_list':
            continue
        key = r[0] + '|' + r[1]
        if key not in prop:
            continue
        n += 1
        tin, tout, delta, tnext = prop[key]
        found = dict([(k, float(v)) for k, v in re.findall(r'([A-Za-z0-9_]+) at ([\d.e+-]+) s', r[5])])
        mb = re.search(r't_next=([\d.e+-]+) s|t_next=(END_OF_DATA)', r[5])
        exp_bound = (mb.group(1) or mb.group(2)) if mb else None
        bound_ok = (tnext == 'END_OF_DATA' and exp_bound == 'END_OF_DATA') or (
            tnext != 'END_OF_DATA' and exp_bound not in (None, 'END_OF_DATA', False) and
            exp_bound and abs(float(exp_bound) - float(tnext)) < 1e-15)
        if any(abs(t - tin) < 1e-15 for t in found.values()) and \
           any(abs(t - tout) < 1e-15 for t in found.values()) and \
           abs((tout - tin) * 1e9 - delta) <= 5e-4 and bound_ok:
            agree += 1
    check('each exported event list recomputes its native delay and bound',
          n > 0 and agree == n, 'events=%d agree=%d (tolerance 0.0005 ns = the row precision)' % (n, agree))

    bad = checks.count(False)
    print('R3A_EVIDENCE_CHECK checks=%d failures=%d root=%s' % (len(checks), bad, o.root))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
