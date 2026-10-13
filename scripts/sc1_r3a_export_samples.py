#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R3A: re-export the delivered waveform samples from the ORIGINAL raw, offline.

    python scripts/sc1_r3a_export_samples.py --scratch <r3_chain dir> \
        --manifest <sc1_r3_chain_manifest.csv> --out <samples.csv> --identity <identity.csv>

Why this file exists: R3A must restore evidence, not make more of it. Nothing here calls the
simulator, the preflight or the runner -- it reads the psfascii data the delivered batch already left
on disk, parses it with the audited parser (scripts/sc1_read_psf.py through sc1_r2e1_reread.samples_of)
and asks the R3 entry's OWN selection function (sc1_r3_chain_tt.event_rows) which samples belong to
which declared input event. So the numbers in the restored file are the same bytes the 428 native rows
were judged from, and the corrected event anchoring cannot drift from the native path's rules.

Every row carries the deck sha256 taken from the delivered manifest and the sha256 of the raw data file
it was read from. The identity CSV additionally checks the deck file still on disk against that hash.
"""
from __future__ import print_function

import csv
import hashlib
import optparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sc1_r2e_s2_tt as S2                  # Run/csvline/write_rows/scrub, the audited shared plumbing
import sc1_r2e1_reread as R1                # samples_of() -> the audited parser's own groups/axis
import sc1_r3_chain_tt as E                 # CASES/find_case/event_rows/file_sha: one selection rule

DATA_NAME = 'sw1.tran.tran'                 # the analysis name every R3 deck uses
ID_HDR = ['run_id', 'case', 'deck_relpath', 'deck_sha256_manifest', 'deck_sha256_on_disk',
          'deck_identity', 'raw_relpath', 'raw_sha256', 'sample_rows', 'preflight_rc', 'spectre_rc',
          'runner_verdict', 'state_verdict', 'rc_columns_provenance']


def manifest_rows(path):
    with open(path, 'rb') as f:
        txt = f.read().decode('utf-8', 'replace')
    rows = list(csv.reader([l for l in txt.split('\n') if l.strip()]))
    hdr = rows[0]
    out = []
    for r in rows[1:]:
        out.append(dict(zip(hdr, r)))
    return out


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def main():
    op = optparse.OptionParser()
    # py2.6's optparse has no `required=`: the three arguments are checked below instead
    op.add_option('--scratch', help='the batch directory holding <case>.scs and sim/')
    op.add_option('--manifest', help='the delivered per-deck manifest (9 rows)')
    op.add_option('--out', help='the samples CSV to write')
    op.add_option('--identity', help='the run/deck/raw identity index to write')
    op.add_option('--data-name', default=DATA_NAME)
    op.add_option('--require-cases', type='int', default=9)
    o = op.parse_args()[0]
    missing = [n for n, v in (('--scratch', o.scratch), ('--manifest', o.manifest),
                              ('--out', o.out)) if not v]
    if missing:
        print('MISSING_ARGUMENT %s: this exporter addresses one delivered batch explicitly'
              % ' '.join(missing))
        return 9

    man = manifest_rows(o.manifest)
    if len(man) != o.require_cases:
        print('MANIFEST_COUNT want=%d got=%d -> refusing to export from a manifest that is not the '
              'delivered batch' % (o.require_cases, len(man)))
        return 9
    ids = [m['case'] for m in man]
    if len(set(ids)) != len(ids):
        print('MANIFEST_DUPLICATE_CASES %s' % ','.join(sorted(set([i for i in ids
                                                                   if ids.count(i) > 1]))))
        return 9

    rows, id_rows = [], []
    for m in man:
        cid = m['case']
        case_def = E.find_case(cid)
        if case_def is None:
            print('UNKNOWN_CASE %s is not offered by the R3 entry' % cid)
            return 9
        deck = os.path.join(o.scratch, m['deck'])
        data = os.path.join(o.scratch, 'sim', cid + '.raw', o.data_name)
        deck_disk = sha256_of(deck) if os.path.isfile(deck) else ''
        if not os.path.isfile(data):
            rows.append([cid, '-', 'RAW_MISSING', '', '', 'no %s under sim/%s.raw: nothing is '
                         'invented and nothing is re-run' % (o.data_name, cid), 'BLOCKED',
                         m['deck_sha256'], ''])
            id_rows.append([m['run_id'], cid, os.path.relpath(deck, PROJ).replace('\\', '/'),
                            m['deck_sha256'], deck_disk,
                            'OK' if deck_disk == m['deck_sha256'] else 'DIFFERS',
                            os.path.relpath(data, PROJ).replace('\\', '/'), 'MISSING', '0',
                            m['preflight_rc'], m['spectre_rc'], m['runner_verdict'],
                            m['state_verdict'], 'ORIGINAL RUN RECORD (committed manifest)'])
            continue
        groups, axis = R1.samples_of(data)
        if not groups:
            rows.append([cid, '-', 'RAW_UNPARSEABLE', '', '', '%s produced no sample groups' % data,
                         'BLOCKED', m['deck_sha256'], E.file_sha(data)])
            continue
        sub = E.event_rows(cid, case_def, groups, axis, data, m['deck_sha256'], E.file_sha(data))
        rows.extend(sub)
        id_rows.append([m['run_id'], cid, os.path.relpath(deck, PROJ).replace('\\', '/'),
                        m['deck_sha256'], deck_disk,
                        'OK' if deck_disk == m['deck_sha256'] else 'DIFFERS',
                        os.path.relpath(data, PROJ).replace('\\', '/'), E.file_sha(data),
                        str(len(sub)), m['preflight_rc'], m['spectre_rc'], m['runner_verdict'],
                        m['state_verdict'], 'ORIGINAL RUN RECORD (committed manifest)'])

    if not rows:
        print('EXPORT_EMPTY: not one raw data file was readable; the samples file stays undelivered '
              'rather than being written as a header')
        return 2
    S2.write_rows(o.out, rows, E.SAMP_HDR)
    if o.identity:
        S2.write_rows(o.identity, id_rows, ID_HDR)
    kinds = {}
    for r in rows:
        kinds[r[2]] = kinds.get(r[2], 0) + 1
    print('R3A_EXPORT cases=%d rows=%d out=%s kinds=%s'
          % (len(man), len(rows), o.out,
             ' '.join('%s=%d' % kv for kv in sorted(kinds.items()))))
    bad = [r for r in id_rows if r[5] != 'OK' or r[7] in ('', 'MISSING')]
    print('R3A_EXPORT_IDENTITY decks_match=%d/%d raws_hashed=%d/%d%s'
          % (len(id_rows) - len([r for r in id_rows if r[5] != 'OK']), len(id_rows),
             len(id_rows) - len([r for r in id_rows if r[7] in ('', 'MISSING')]), len(id_rows),
             '' if not bad else ' PROBLEMS=%s' % ','.join(r[1] for r in bad)))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
