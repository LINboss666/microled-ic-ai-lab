#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regenerate results/evidence/sc1_s3c3_round_manifest.csv from the GIT INDEX.

Why the index and not the working copy: .gitattributes is `* text=auto eol=lf`, so a Windows working
file can differ from the blob the round actually commits. The S3C1/S3C2 manifests recorded working
copy hashes and several rows described bytes that were never committed; every row here is the sha256
and length of `git cat-file blob :<path>`, which is what a reviewer can re-derive from the push.

Rows excluded by design: the manifest itself (self-referential), results/evidence/_incoming/ (the
scratch area, not committed), and *.bundle (rebuilt per review request).

    python scripts/sc1_s3c3_manifest.py [--base <commit>]
"""
import hashlib
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join('results', 'evidence')
MANIFEST = os.path.join(EV, 'sc1_s3c3_round_manifest.csv')
BASE = os.environ.get('S3C3_BASE', '7a1fc43db9b9d7a17c5accdac2296196cb0bf709')
NOTE = (u'hashed from the staged blob, which is what this round commits; excluded row: '
        u'the manifest itself')


def git(*args):
    p = subprocess.Popen(['git', '-C', ROOT] + list(args), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    out = p.communicate()[0]
    if p.returncode != 0:
        sys.stderr.write(out.decode('utf-8', 'replace'))
        sys.exit(1)
    return out


def files():
    raw = git('diff', '--cached', '--name-only', '-M', BASE).decode('utf-8', 'replace')
    out = []
    for rel in raw.splitlines():
        rel = rel.strip().replace('\\', '/')
        if not rel or rel == MANIFEST.replace('\\', '/'):
            continue
        if rel.startswith('results/evidence/_incoming/') or rel.endswith('.bundle'):
            continue
        out.append(rel)
    return sorted(out)


def blob(rel):
    """Bytes of the staged blob, addressed by its own OID.

    `git cat-file blob :<path>` was measured to fail intermittently here (one row came out as a
    64-byte error string), and a manifest row must never be an error message, so the OID is read
    from the index first and both steps must return 0.
    """
    out = git('ls-files', '-s', '--', rel)
    oid = out.decode().split('\n')[0].split()[1] if out.strip() else ''
    if len(oid) != 40:
        sys.stderr.write('NOT_IN_INDEX %s\n' % rel)
        sys.exit(1)
    data = git('cat-file', 'blob', oid)
    if git('cat-file', '-s', oid).decode().strip() != str(len(data)):
        sys.stderr.write('TRUNCATED_BLOB %s\n' % rel)
        sys.exit(1)
    return data


def role(rel):
    if rel.startswith('results/evidence/'):
        return 's3c3_evidence'
    if rel.startswith('reports/agent_handoffs/'):
        return 's3c3_agent_handoffs'
    return 's3c3_' + os.path.basename(rel)


def main():
    rows = [[u'file', u'sha256', u'bytes', u'role', u'cloud_can_verify_bytes', u'note']]
    for rel in files():
        data = blob(rel)
        rows.append([rel, hashlib.sha256(data).hexdigest(), str(len(data)), role(rel), 'yes', NOTE])
    lines = []
    for row in rows:
        lines.append(','.join('"%s"' % c for c in row))
    io.open(os.path.join(ROOT, MANIFEST), 'wb').write(('\n'.join(lines) + '\n').encode('utf-8'))
    print('S3C3_MANIFEST rows=%d base=%s' % (len(rows) - 1, BASE[:7]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
