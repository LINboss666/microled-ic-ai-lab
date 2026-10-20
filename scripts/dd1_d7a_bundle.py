# -*- coding: utf-8 -*-
"""DATA-7A supplementary review packer.

    python scripts/dd1_d7a_bundle.py --base 731767519d1a51287eb5b7f4a6e4f9b8e613e990 [--head HEAD]

The shared `make_review_bundle.py` only recognises its own extension set, which has no SystemVerilog,
so it silently drops `rtl/*.sv` and `tests/dd1_d7a/*.sv` -- the exact deliverable a DATA-7A reviewer
has to read. This script adds those files without touching the shared scanner or the shared bundle:

* every byte is taken from the **git blob**, not from the working tree, so the manifest describes
  what the remote actually holds rather than what the local checkout happens to have;
* each file passes the original `repo_safety_rules` content and path rules before it is packed;
* a MUST_IGNORE verdict stops the bundle; a NEEDS_REVIEW verdict is recorded in the manifest.

Run: python scripts/dd1_d7a_bundle.py --base <sha> --head <sha>
"""
from __future__ import print_function

import argparse
import hashlib
import io
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import repo_safety_rules as R                                    # noqa: E402

D7A_PREFIXES = ('rtl/dd1_d7a_', 'tests/dd1_d7a/', 'scripts/dd1_d7a_',
                'reports/dd1_d7a_', 'reports/agent_handoffs/DATA-7A.',
                'results/evidence/dd1_d7a_')
# the two shared files this round was explicitly allowed to touch, plus the constraints a reviewer
# needs next to the new code
ALSO = ('scripts/repo_safety_rules.py', 'scripts/test_safety_rules.py', 'AGENTS.md',
        'CONTRIBUTING_AI.md', '.gitignore', 'spec/system_requirements.md',
        'reports/agent_handoffs/DATA-6.md')


def git(rev):
    out = subprocess.check_output(['git', '-C', PROJ, 'cat-file', 'blob', rev])
    return out


def names(rev):
    out = subprocess.check_output(['git', '-C', PROJ, 'ls-tree', '-r', '--name-only', rev])
    return [l for l in out.decode('utf-8', 'replace').split('\n') if l.strip()]


def scan(rel, data):
    reasons = []
    pat = R.path_denied(rel)
    if pat:
        reasons.append('path_matches:' + pat)
    text = data.decode('utf-8', 'replace')
    hits = [n for n, _ in R.content_denied(text)] + [n for n, _ in R.secrets_in(text)]
    if hits:
        reasons.append('content:' + ','.join(hits))
    if len(data) > R.SIZE_REVIEW_BYTES:
        reasons.append('large_file:%d' % len(data))
    ext = os.path.splitext(rel)[1].lower()
    if ext and ext not in R.EXTENSIONS_ALLOWED:
        reasons.append('unknown_extension:' + ext)
    if pat or 'content' in ' '.join(reasons):
        return 'MUST_IGNORE', reasons
    return ('NEEDS_REVIEW', reasons) if reasons else ('SAFE_TO_TRACK', reasons)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True)
    ap.add_argument('--head', default='HEAD')
    a = ap.parse_args()
    for rev in (a.base, a.head):
        subprocess.check_call(['git', '-C', PROJ, 'rev-parse', '--verify', rev + '^{commit}'])
    head_files = names(a.head)
    pick = [p for p in head_files if p.startswith(D7A_PREFIXES) or p in ALSO]
    if not any(p.startswith('rtl/dd1_d7a_') for p in pick):
        print('BUNDLE: FAIL — no RTL selected, the prefix list is wrong')
        return 1
    changed = []
    for p in pick:
        try:
            out = subprocess.check_output(['git', '-C', PROJ, 'diff', '--name-only', a.base, a.head,
                                           '--', p])
        except subprocess.CalledProcessError:
            out = b''
        if out.strip():
            changed.append(p)
    dest_dir = os.path.join(PROJ, 'review')
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    short = subprocess.check_output(['git', '-C', PROJ, 'rev-parse', '--short', a.head]).strip()
    dest = os.path.join(dest_dir, 'dd1_d7a_bundle_%s.zip' % short)
    rows = []
    blocked = []
    z = zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED)
    try:
        for rel in pick:
            data = git('%s:%s' % (a.head, rel))
            bucket, reasons = scan(rel, data)
            rows.append((rel, len(data), hashlib.sha256(data).hexdigest(), bucket,
                         ';'.join(reasons) or 'none'))
            if bucket == 'MUST_IGNORE':
                blocked.append(rel)
                continue
            z.writestr('dd1_d7a/%s' % rel, data)
        man = ['path,bytes,sha256,bucket,reasons']
        for r in rows:
            man.append('%s,%d,%s,%s,%s' % r)
        z.writestr('dd1_d7a/MANIFEST.csv', '\n'.join(man) + '\n')
        meta = ['DATA-7A supplementary review bundle',
                'base=%s' % a.base,
                'head=%s' % a.head,
                'files=%d' % len(rows),
                'changed_since_base=%d' % len(changed),
                'safety_rules=%s' % hashlib.sha256(git('%s:scripts/repo_safety_rules.py'
                                                       % a.head)).hexdigest(),
                'bytes are read from the git blob at head, not from the working tree',
                'the shared scripts/make_review_bundle.py is not modified and does not recognise .sv',
                '', 'changed files in this range:']
        meta += ['  ' + c for c in changed]
        z.writestr('dd1_d7a/BUNDLE_INFO.txt', '\n'.join(meta) + '\n')
    finally:
        z.close()
    print('\n'.join('%-6s %s' % (r[3], r[0]) for r in rows))
    print('files=%d blocked=%d zip=%s' % (len(rows), len(blocked), dest))
    if blocked:
        print('DD1_D7A_BUNDLE: FAIL — MUST_IGNORE content would have been packed: %s'
              % ', '.join(blocked))
        return 1
    print('DD1_D7A_BUNDLE: PASS (contents come from head=%s; reviewer still has to read them)'
          % a.head[:12])
    return 0


if __name__ == '__main__':
    sys.exit(main())
