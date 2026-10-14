#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C2: audit a round manifest against the bytes Git actually serves.

The S3C1 manifest was reported as 194/194 self-consistent, and that was wrong: it hashed the
WORKING tree while a reviewer fetches the COMMITTED blob, so (a) rows for files that were never
tracked -- the untracked results/evidence/_incoming/ scratch copies the walker picked up -- have no
remote bytes at all, and (b) a file written with CRLF on Windows is stored normalised to LF, so the
recorded sha256 and length do not match the blob the remote serves.

This tool classifies every row of a manifest into one of:
  ok              committed blob sha and bytes both equal the recorded values
  sha_wrong       the file is tracked but the recorded sha differs from the committed blob
  bytes_wrong     the file is tracked but the recorded length differs from the committed blob
  eol_normalised  the recorded sha/length are the CRLF working copy's, the blob is the LF version
  stale_row       the row matches neither the working copy nor the blob, which agree with each other
  not_in_git      the recorded path is not in the commit at all (untracked / scratch)
  missing         the recorded path is not present in the working tree either

usage: python scripts/sc1_s3c2_manifest_audit.py <manifest.csv> [--ref HEAD]
"""
from __future__ import print_function
import hashlib
import io
import os
import subprocess
import sys


def clean(tok):
    return tok.strip().strip('"')


def eol_variants(rel):
    """sha256/length of the working file as it stands and with CRLF collapsed to LF -- what git
    stores for it."""
    d = io.open(rel, 'rb').read()
    n = d.replace(b'\r\n', b'\n')
    return (hashlib.sha256(d).hexdigest(), len(d), hashlib.sha256(n).hexdigest(), len(n),
            d.count(b'\r\n'))


def main():
    args = sys.argv[1:]
    if not args:
        print('usage: sc1_s3c2_manifest_audit.py <manifest.csv> [--ref HEAD]')
        return 9
    path = args[0]
    ref = args[args.index('--ref') + 1] if '--ref' in args else 'HEAD'
    lines = [l.rstrip('\n') for l in io.open(path, encoding='utf-8') if l.strip()]
    hdr = [clean(h) for h in lines[0].split(',')]
    fi, si, bi = hdr.index('file'), hdr.index('sha256'), hdr.index('bytes')

    counts = {'ok': 0, 'sha_wrong': 0, 'bytes_wrong': 0, 'not_in_git': 0, 'missing': 0,
              'eol_normalised': 0, 'stale_row': 0}
    detail = []
    for l in lines[1:]:
        f = [clean(c) for c in l.split(',')]
        rel, want_sha, want_bytes = f[fi], f[si], int(f[bi])
        if not os.path.isfile(rel):
            counts['missing'] += 1
            detail.append('MISSING %s' % rel)
            continue
        # what Git would serve at this commit, not what the working tree happens to hold
        p = subprocess.Popen(['git', 'cat-file', '-s', '%s:%s' % (ref, rel)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        size_out = p.communicate()[0].decode('utf-8', 'replace').strip()
        if p.returncode != 0:
            counts['not_in_git'] += 1
            detail.append('NOT_IN_GIT %s' % rel)
            continue
        p = subprocess.Popen(['git', 'rev-parse', '%s:%s' % (ref, rel)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        blob = p.communicate()[0].decode('utf-8', 'replace').strip()
        # git's blob id is sha1; the manifest records sha256 of the bytes, so hash the served bytes
        p = subprocess.Popen(['git', 'cat-file', 'blob', blob],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data = p.communicate()[0]
        got_sha = hashlib.sha256(data).hexdigest()
        got_bytes = len(data)
        if got_sha != want_sha or got_bytes != want_bytes:
            # two distinct, separately verifiable root causes -- saying "the row is wrong" hides which
            r_sha, r_bytes, n_sha, n_bytes, crlf = eol_variants(rel)
            if (r_sha == want_sha and r_bytes == want_bytes and crlf and n_sha == got_sha
                    and n_bytes == got_bytes):
                # the manifest hashed the Windows CRLF working copy; `* text=auto eol=lf` commits LF
                counts['eol_normalised'] += 1
                detail.append('EOL_NORMALISED %s recorded=%s/%d actual=%s/%d crlf_lines=%d'
                              % (rel, want_sha[:12], want_bytes, got_sha[:12], got_bytes, crlf))
                continue
            if r_sha == got_sha and r_bytes == got_bytes:
                # working copy and commit agree now, so the row was written against other bytes
                counts['stale_row'] += 1
                detail.append('STALE_ROW %s recorded=%s/%d actual=%s/%d working_matches_commit=yes'
                              % (rel, want_sha[:12], want_bytes, got_sha[:12], got_bytes))
                continue
        if got_sha != want_sha and got_bytes != want_bytes:
            counts['sha_wrong'] += 1
            detail.append('BOTH_WRONG %s recorded=%s/%d actual=%s/%d'
                          % (rel, want_sha[:12], want_bytes, got_sha[:12], got_bytes))
        elif got_sha != want_sha:
            counts['sha_wrong'] += 1
            detail.append('SHA_WRONG %s recorded=%s actual=%s (%d bytes both)'
                          % (rel, want_sha[:12], got_sha[:12], got_bytes))
        elif got_bytes != want_bytes:
            counts['bytes_wrong'] += 1
            detail.append('BYTES_WRONG %s recorded=%d actual=%d' % (rel, want_bytes, got_bytes))
        else:
            counts['ok'] += 1

    print('MANIFEST_AUDIT file=%s ref=%s rows=%d %s'
          % (os.path.basename(path), ref, len(lines) - 1,
             ' '.join('%s=%d' % (k, counts[k]) for k in sorted(counts))))
    for d in detail:
        print('  %s' % d)
    verifiable = counts['ok']
    print('CLOUD_VERIFIABLE_ROWS %d of %d' % (verifiable, len(lines) - 1))
    return 0 if verifiable == len(lines) - 1 else 1


if __name__ == '__main__':
    sys.exit(main())
