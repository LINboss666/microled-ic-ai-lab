#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-A: read the end-of-run tail of the delivered dynamic decks, offline.

    python scripts/sc1_s3a_tail_read.py [--cases s3a_dyn_light,s3a_dyn_column]

Why a separate tool: S3-A must not simulate twice. The two dynamic decks already ran, and the question
the report is not allowed to guess at -- did the light bench load ever discharge inside the declared
stop? -- is answered by asking the audited strict reader about the delivered data file. No simulator,
no preflight and no runner is invoked here; the only thing written is this small CSV, and each row
names the raw file's sha256 so the reading is tied to the delivered batch.

It also records the last sample time the file actually carries, so nobody reads "500 ns" into a file
that ends earlier.
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

import sc1_r2e_s2_tt as S2
import sc1_r2e1_call_contract as CC
import sc1_r2e1_reread as R1

WIN = (480.0, 500.0)                      # ns: the stretch after the blank edge
HDR = ['run_id', 'case', 'signal', 'window_ns', 'mode', 'value', 'unit', 'raw_sha256',
       'provenance']


def main():
    op = optparse.OptionParser()
    op.add_option('--scratch', default=os.path.join(PROJ, 'cadence_work', 'sc1_sim', 's3a_p33'))
    op.add_option('--identity', default=os.path.join(PROJ, 'results', 'evidence',
                                                     'sc1_s3a_identity.csv'))
    op.add_option('--out', default=os.path.join(PROJ, 'results', 'evidence',
                                                 'sc1_s3a_tail_readings.csv'))
    op.add_option('--cases', default='s3a_dyn_light,s3a_dyn_column')
    o = op.parse_args()[0]

    if not os.path.isfile(o.identity):
        print('S3A_TAIL_NO_IDENTITY %s: the readings are only meaningful against the delivered '
              'batch identity' % o.identity)
        return 9
    with open(o.identity, 'rb') as f:
        idr = list(csv.reader([l for l in f.read().decode('utf-8', 'replace').split('\n') if l.strip()]))
    head, rows = idr[0], idr[1:]
    want = dict((r[1], r) for r in rows)

    out = []
    for cid in [c for c in o.cases.split(',') if c]:
        if cid not in want:
            print('S3A_TAIL_UNKNOWN_CASE %s (the identity index offers %s)'
                  % (cid, ','.join(sorted(want))))
            return 9
        run_id, raw_rel, raw_sha = want[cid][0], want[cid][4], want[cid][5]
        data = os.path.join(PROJ, *raw_rel.split('/'))
        if not os.path.isfile(data):
            print('S3A_TAIL_NO_DATA %s: %s (this tool reads the delivered file, it never re-runs '
                  'the simulator)' % (cid, data))
            return 9
        if hashlib.sha256(open(data, 'rb').read()).hexdigest() != raw_sha:
            print('S3A_TAIL_RAW_MISMATCH %s: the file underfoot is not the delivered one' % cid)
            return 9
        groups, axis = R1.samples_of(data)
        last_t = groups[-1][axis] if groups else None
        for mode in ('last', 'min', 'max'):
            rc, line = S2.read_sig(None, data, 'drain', mode, t0='%dn' % WIN[0],
                                   t1='%dn' % WIN[1], req='3')
            out.append([run_id, cid, 'drain', '%g..%g' % WIN, mode, line.split('\t')[0], 'V',
                        raw_sha, 'strict reader on the delivered data file; no simulation'])
            if rc:
                print('S3A_TAIL_READER_RC %s %s rc=%s %s' % (cid, mode, rc, line))
        out.append([run_id, cid, axis or 'time', 'file extent', 'last_sample',
                    '%.9g' % last_t if last_t is not None else 'NONE', 's', raw_sha,
                    'the largest sample time the delivered file actually carries'])
    S2.write_rows(o.out, out, HDR)
    print('S3A_TAIL_READINGS rows=%d -> %s' % (len(out), o.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
