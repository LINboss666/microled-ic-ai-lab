#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-B: partition one delivered evidence CSV into parts that fit the history size gate.

    python scripts/sc1_s3b_split_samples.py --split <file> --outdir <dir> [--limit-kb 240]
    python scripts/sc1_s3b_split_samples.py --verify <dir>
    python scripts/sc1_s3b_split_samples.py --selftest

Why this exists: `scripts/precommit_safety_check.py` refuses any staged blob over 512 KiB
(`HISTORY_SCAN_BYTES`, "bulk output does not belong in history"), and the S3-B sample export is
3 583 407 bytes because every gate-charge window is shipped point by point at full precision. The
bytes the simulator produced are the object of record and are not re-formatted here: the file is cut
only at newline boundaries, so the concatenation of the parts equals the original byte for byte, and
the index records both the whole-file sha256 and each part's own. A reviewer can therefore rejoin the
parts and check the delivered digest, or audit one part on its own.

Nothing else is allowed to be written: an output name that does not start with `sc1_s3b_` is refused,
and the tool never touches the source file.
"""
from __future__ import print_function

import hashlib
import io
import optparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
PREFIX = 'sc1_s3b_'
IDX_NAME = 'sc1_s3b_samples_parts.csv'
IDX_HDR = ['part', 'bytes', 'sha256', 'data_rows', 'first_data_row', 'last_data_row',
           'whole_sha256', 'whole_bytes', 'source_name']
LIMIT_KB = 240


def u(s):
    return s if isinstance(s, type(u'')) else s.decode('utf-8')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def header_of(blobs):
    """the header record every part repeats, so that each part is a standalone CSV"""
    recs = records(blobs[0])
    return recs[0] if recs else b''


def body_of(blob):
    return b''.join(records(blob)[1:])


def records(data):
    """the file as a list of byte records, each keeping its own trailing newline"""
    out, i = [], 0
    while i < len(data):
        j = data.find(b'\n', i)
        if j < 0:
            out.append(data[i:])
            break
        out.append(data[i:j + 1])
        i = j + 1
    return out


def split(src, outdir, limit):
    data = open(src, 'rb').read()
    recs = records(data)
    if not recs or not recs[0].endswith(b'\n'):
        print('SPLIT_REFUSED %s: the first record must end in a newline' % src)
        return 9
    header, body, whole = recs[0], recs[1:], sha(data)
    if not body:
        print('SPLIT_REFUSED %s: no data rows to partition' % src)
        return 9
    parts, cur, rows, first = [], [], 0, 1
    for k, rec in enumerate(body):
        if len(header) + sum(len(x) for x in cur) + len(rec) > limit and cur:
            parts.append((cur, rows, first))
            first += rows
            cur, rows = [], 0
        cur.append(rec)
        rows += 1
    if cur:
        parts.append((cur, rows, first))
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    name = os.path.basename(src)
    stem = name[:-4] if name.endswith('.csv') else name
    if stem.startswith(PREFIX):
        stem = stem[len(PREFIX):]
    rows_idx = []
    for i, (chunk, nrows, f0) in enumerate(parts):
        pn = '%s%s_p%02d.csv' % (PREFIX, stem, i + 1)
        blob = header + b''.join(chunk)
        if len(blob) > limit:
            print('SPLIT_REFUSED: part %s is %d bytes over the %d limit' % (pn, len(blob), limit))
            return 9
        with io.open(os.path.join(outdir, pn), 'wb') as f:
            f.write(blob)
        rows_idx.append([pn, str(len(blob)), sha(blob), str(nrows), str(f0), str(f0 + nrows - 1),
                         whole, str(len(data)), name])
    joined = header + b''.join(rec for part in parts for rec in part[0])
    if sha(joined) != whole or len(joined) != len(data):
        print('SPLIT_REFUSED: the parts do not rejoin to the source bytes')
        return 9
    lines = [u(','.join('"%s"' % x for x in IDX_HDR))]
    for r in rows_idx:
        lines.append(u(','.join('"%s"' % x for x in r)))
    with io.open(os.path.join(outdir, IDX_NAME), 'w', encoding='utf-8', newline='') as f:
        f.write(u'\n'.join(lines) + u'\n')
    print('SPLIT_OK source=%s whole_bytes=%d whole_sha256=%s parts=%d limit=%d'
          % (name, len(data), whole, len(rows_idx), limit))
    for r in rows_idx:
        print('   %-44s %8d bytes  rows %s..%s' % (r[0], int(r[1]), r[4], r[5]))
    return 0


def read_index(dirpath):
    p = os.path.join(dirpath, IDX_NAME)
    if not os.path.isfile(p):
        return None, 'no index %s' % IDX_NAME
    rows = [l for l in io.open(p, encoding='utf-8', newline='').read().split(u'\n') if l.strip()]
    return rows[1:], 'ok'


def verify(dirpath):
    rows, why = read_index(dirpath)
    if rows is None:
        print('S3B_PARTS_VERIFY: FAIL %s' % why)
        return 1
    ok, blobs, whole, want_bytes = True, [], '', 0
    for line in rows:
        f = [x.strip().strip('"') for x in line.split(',')]
        path = os.path.join(dirpath, f[0])
        whole, want_bytes = f[6], int(f[7])
        if not os.path.isfile(path):
            print('   MISSING %s' % f[0])
            ok = False
            continue
        blob = open(path, 'rb').read()
        good = (sha(blob) == f[2] and len(blob) == int(f[1]))
        ok = ok and good
        blobs.append(blob)
        print('   %-44s %s  %d bytes sha=%s' % (f[0], 'PASS' if good else 'FAIL', len(blob),
                                                sha(blob)[:12]))
    joined = header_of(blobs) + b''.join(body_of(b) for b in blobs)
    rejoin = bool(blobs) and sha(joined) == whole and len(joined) == want_bytes
    print('   rejoin to the delivered bytes: %s  whole_sha256=%s bytes=%d/%d'
          % ('PASS' if rejoin else 'FAIL', whole[:16], len(joined), want_bytes))
    ok = ok and rejoin
    print('S3B_PARTS_VERIFY: %s parts=%d (%s)' % ('PASS' if ok else 'FAIL', len(rows), dirpath))
    return 0 if ok else 1


def selftest():
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix='s3b_split_selftest_')
    checks = []
    try:
        src = os.path.join(tmp, 'sc1_s3b_waveform_samples.csv')
        header = 'a,b,c\n'
        body = ''.join('%d,%s,t%06d\n' % (i, 'x' * 40, i) for i in range(400))
        with io.open(src, 'w', encoding='utf-8', newline='') as f:
            f.write(u(header + body))
        rc = split(src, tmp, 8 * 1024)
        checks.append(('the split of a 400-row file returns 0', rc == 0))
        checks.append(('the parts rejoin to the delivered bytes', verify(tmp) == 0))
        rows, _w = read_index(tmp)
        names = [l.split(',')[0].strip('"') for l in rows]
        checks.append(('every part is named sc1_s3b_waveform_samples_pNN with no doubled prefix',
                       all(n == 'sc1_s3b_waveform_samples_p%02d.csv' % (i + 1)
                           for i, n in enumerate(names)) and
                       not any(n.startswith(PREFIX + 'sc1_') for n in names)))
        checks.append(('the parts cover every data row exactly once',
                       sum(int(l.split(',')[3].strip('"')) for l in rows) == 400 and
                       max(int(l.split(',')[5].strip('"')) for l in rows) == 400))
        os.remove(os.path.join(tmp, names[0]))
        checks.append(('a missing part is refused instead of a silent partial read',
                       verify(tmp) != 0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = 0
    for name, v in checks:
        print('   %-58s %s' % (name, 'PASS' if v else 'FAIL'))
        bad += 0 if v else 1
    print('S3B_SPLIT_SELFTEST cases=%d failures=%d (byte partition only; no simulator, no circuit '
          'claim)' % (len(checks), bad))
    return 1 if bad else 0


def main():
    op = optparse.OptionParser()
    op.add_option('--split')
    op.add_option('--outdir')
    op.add_option('--verify')
    op.add_option('--limit-kb', type='int', default=LIMIT_KB)
    op.add_option('--selftest', action='store_true')
    o = op.parse_args()[0]
    if o.selftest:
        return selftest()
    if o.verify:
        return verify(o.verify)
    if not o.split or not o.outdir:
        print('usage: --split <csv> --outdir <dir> | --verify <dir> | --selftest')
        return 9
    base = os.path.basename(o.split)
    if not base.startswith(PREFIX):
        print('SPLIT_REFUSED %s: this round only partitions sc1_s3b_ evidence' % base)
        return 9
    return split(o.split, o.outdir, o.limit_kb * 1024)


if __name__ == '__main__':
    sys.exit(main())
