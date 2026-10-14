#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C2: verify a round manifest against the bytes git will actually serve.

The S3C1 round published a manifest it called 194/194 self-consistent. It had been hashed from the
Windows working tree, so a CRLF file's row disagreed with the LF blob the remote serves and a row
pointed into the untracked results/evidence/_incoming/ scratch area. This is the gate that would
have caught both before publishing: every row is re-hashed from a git blob, not from disk.

usage: python scripts/sc1_s3c2_check_round.py [manifest.csv] [--ref <commit>|index]
       default manifest: results/evidence/sc1_s3c2_round_manifest.csv, default ref: index
"""
from __future__ import print_function
import hashlib
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = 'results/evidence/sc1_s3c2_round_manifest.csv'


def blob(spec, rel):
    p = subprocess.Popen(['git', '-C', ROOT, 'cat-file', 'blob', '%s:%s' % (spec, rel)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data = p.communicate()[0]
    return None if p.returncode else data


def main():
    args = sys.argv[1:]
    path = args[0] if args and not args[0].startswith('--') else DEFAULT
    ref = args[args.index('--ref') + 1] if '--ref' in args else 'index'
    spec = '' if ref == 'index' else ref
    rel_path = os.path.relpath(path, ROOT).replace('\\', '/')
    lines = [l for l in io.open(path, encoding='utf-8').read().splitlines() if l.strip()]
    hdr = [h.strip().strip('"') for h in lines[0].split(',')]
    fi, si, bi = hdr.index('file'), hdr.index('sha256'), hdr.index('bytes')

    checks, fails = 0, []
    for line in lines[1:]:
        cols = [c.strip().strip('"') for c in line.split(',')]
        rel, want_sha, want_bytes = cols[fi], cols[si], int(cols[bi])
        checks += 1
        # a manifest must never certify its own bytes, nor anything from the scratch area
        if rel == rel_path:
            fails.append('SELF_ROW %s' % rel)
            continue
        if rel.startswith('results/evidence/_incoming/'):
            fails.append('SCRATCH_ROW %s' % rel)
            continue
        data = blob(spec, rel)
        if data is None:
            fails.append('NOT_IN_%s %s' % (ref.upper(), rel))
            continue
        got_sha, got_bytes = hashlib.sha256(data).hexdigest(), len(data)
        if got_sha != want_sha:
            fails.append('SHA %s recorded=%s blob=%s' % (rel, want_sha[:12], got_sha[:12]))
        if got_bytes != want_bytes:
            fails.append('BYTES %s recorded=%d blob=%d' % (rel, want_bytes, got_bytes))

    print('ROUND_MANIFEST_CHECK ref=%s rows=%d failures=%d' % (ref, checks, len(fails)))
    for f in fails:
        print('  FAIL %s' % f)
    print('S3C2_ROUND_MANIFEST_CHECK: %s' % ('PASS' if not fails else 'FAIL'))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
