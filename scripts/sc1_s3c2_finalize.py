#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C2 delivery finisher: place this round's evidence in results/evidence/, write the
corrections table the audit produced, and emit ONE authoritative round manifest over the bytes that
are about to be committed.

Rules this honours (task book section 7):
  * the manifest lists an explicit file set -- only files tracked by git plus the files this script
    just wrote; nothing under results/evidence/_incoming/ (those are the unverified pull staging);
  * the manifest excludes itself, so no manifest hashes another manifest in a circle;
  * every row carries sha256 + byte count + whether the cloud can re-verify those bytes (yes = the
    bytes are in this repository at this path; no = the artifact is a local/guest-side copy).
  * the corrections table repeats what scripts/sc1_s3c2_manifest_audit.py measured on the previous
    round's manifests, because those rows are the evidence for the retraction in the report.

usage: python scripts/sc1_s3c2_finalize.py
"""
from __future__ import print_function
import hashlib
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, 'results', 'evidence')
IN = os.path.join(EV, '_incoming')
LOGS = os.path.join(IN, 's3c2_logs')
# the sessions that carry a verdict this round depends on; the rest stay in the pull staging area
KEEP = {
    's3c_oa_20261014_164855.log': 'sc1_s3c2_log_apply_sym_placement_pass.txt',
    's3c_oa_20261014_165429.log': 'sc1_s3c2_log_loop_moves_and_text_follow.txt',
    's3c_oa_20261014_165722.log': 'sc1_s3c2_log_loop_closed_pass.txt',
    's3c_oa_20261014_165821.log': 'sc1_s3c2_log_attribute_types.txt',
    's3c_oa_20261014_171246.log': 'sc1_s3c2_log_relay_attempt_errors.txt',
    's3c_oa_20261014_172648.log': 'sc1_s3c2_log_relay_keep_attempt_errors.txt',
    's3c_oa_20261014_172946.log': 'sc1_s3c2_log_relay_stub_attempt_errors.txt',
    's3c_oa_20261014_173007.log': 'sc1_s3c2_log_final_verify_disk_reopen.txt',
}
CSV = ['sc1_s3c2_ports.csv', 'sc1_s3c2_attach.csv', 'sc1_s3c2_crossnet.csv',
       'sc1_s3c2_editor_check.csv', 'sc1_s3c2_wire_labels.csv']
# the routing plans, kept under their round name: they are the input the re-lay was drawn from
PLAN = [('s3c2_relay_plan.csv', 'sc1_s3c2_relay_plan.csv'),
        ('s3c2_loop_plan.csv', 'sc1_s3c2_loop_plan.csv'),
        ('s3c2_chain_plan.csv', 'sc1_s3c2_chain_plan.csv'),
        ('s3c2_lsc1_plan.csv', 'sc1_s3c2_lsc1_plan.csv')]


def lf(b):
    # .gitattributes is `* text=auto eol=lf`, so the bytes git stores for a CRLF file are the
    # LF-normalised ones. A manifest that hashed the Windows working copy would then disagree with
    # every checkout -- exactly the defect class this round documents, so hash what gets committed.
    return b.replace(b'\r\n', b'\n')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    return io.open(p, 'rb').read()


def write(p, data):
    d = os.path.dirname(p)
    if not os.path.isdir(d):
        os.makedirs(d)
    io.open(p, 'wb').write(lf(data))
    print('WROTE %s bytes=%d' % (os.path.relpath(p, ROOT).replace('\\', '/'), len(lf(data))))


def redact(path):
    t = io.open(path, encoding='utf-8', errors='replace').read()
    return t.replace('/root/microled_ai_project', '$PROJ').encode('utf-8')


BASE = os.environ.get('S3C2_BASE', '22af9d025457c077aeeb7ca10ace08049550de9e')


def git_files():
    """every path this round delivers: the diff between the audit base and the index, so a round
    that lands as two commits still gets one authoritative list. Taken from staged content, not
    from whatever happens to sit in the working tree."""
    out = subprocess.Popen(['git', '-C', ROOT, 'diff', '--cached', '--name-only', '-M', BASE],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).communicate()[0].decode('utf-8', 'replace')
    files = set()
    for line in out.splitlines():
        p = line.strip().replace('\\', '/')
        if not p:
            continue
        if p.startswith('results/evidence/_incoming/') or p.endswith('.bundle'):
            continue
        files.add(p)
    return sorted(files)


def main():
    for src, dst in sorted(KEEP.items()):
        sp = os.path.join(LOGS, src)
        if not os.path.isfile(sp):
            print('MISSING-SOURCE %s' % src)
            continue
        write(os.path.join(EV, dst), redact(sp))
    for c in CSV:
        sp = os.path.join(IN, c)
        if not os.path.isfile(sp):
            print('MISSING-CSV %s' % c)
            continue
        write(os.path.join(EV, c), read(sp))
    for src, dst in PLAN:
        sp = os.path.join(IN, src)
        if os.path.isfile(sp):
            write(os.path.join(EV, dst), read(sp))

    out = []
    # each old manifest is audited against HEAD and against the last commit that touched it, so a
    # row a later round legitimately revised reads as SUPERSEDED instead of being called a defect
    for old in ('sc1_s3c1_round_manifest.csv', 'sc1_s3c_round_manifest.csv'):
        origin = subprocess.Popen(['git', '-C', ROOT, 'log', '-1', '--format=%H', '--',
                                   'results/evidence/' + old],
                                  stdout=subprocess.PIPE).communicate()[0].decode().strip()
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'scripts',
                                                           'sc1_s3c2_manifest_audit.py'),
                              os.path.join(EV, old), '--origin', origin],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0]
        out.append(p.decode('utf-8', 'replace'))
    audit = u'\n'.join(out)
    io.open(os.path.join(EV, 'sc1_s3c2_manifest_audit_output.txt'), 'wb').write(lf(audit.encode(
        'utf-8')))
    corr = [[u'old_manifest', u'row_file', u'classification', u'recorded_sha',
             u'recorded_bytes', u'actual_sha', u'actual_bytes', u'correction']]
    current = ''
    for ln in audit.splitlines():
        f = ln.split()
        if not f:
            continue
        if f[0] == 'MANIFEST_AUDIT':
            current = [x.split('=', 1)[1] for x in f if x.startswith('file=')][0]
            continue
        if f[0] in ('NOT_IN_GIT', 'SHA_WRONG', 'BYTES_WRONG', 'BOTH_WRONG', 'MISSING',
                    'EOL_NORMALISED', 'STALE_ROW', 'SUPERSEDED'):
            row = [current, f[1], f[0], '', '', '', '']
            for kv in f[2:]:
                k, v = kv.split('=', 1)
                if k == 'recorded':
                    row[3], row[4] = v.split('/')
                if k == 'actual':
                    row[5], row[6] = v.split('/')
                if k == 'want':
                    row[3] = v
                if k == 'have':
                    row[5] = v
            row[1] = row[1] if row[1] != current else row[1]
            why = (u'the recorded values are the sha256/length of the CRLF working copy; '
                   u'.gitattributes (`* text=auto eol=lf`) commits the LF-normalised bytes, so the '
                   u'row describes bytes that were never committed. Content is not wrong.'
                   if f[0] == 'EOL_NORMALISED' else
                   u'the row names a file that is neither in the working tree nor in the commit; the '
                   u'path is the untracked results/evidence/_incoming/ scratch area, so no remote byte '
                   u'can verify it. Where a tracked twin exists (sc1_s3c1_symbol_side.csv is at '
                   u'results/evidence/sc1_s3c1_symbol_side.csv) the row simply pointed at the wrong '
                   u'path. This is the defect, not a formatting issue.'
                   if f[0] == 'NOT_IN_GIT' else
                   u'NOT A DEFECT: the row matched the committed bytes of the round that delivered '
                   u'the manifest; this round revised the file, so it no longer matches HEAD. '
                   u'The origin commit is the `correct_at=` field of the same row in '
                   u'sc1_s3c2_manifest_audit_output.txt.'
                   if f[0] == 'SUPERSEDED' else
                   u'the working copy and the committed blob agree now, so this row was written '
                   u'against a different earlier content; it is stale, not a byte-level mismatch.'
                   if f[0] == 'STALE_ROW' else
                   u'row is wrong against the bytes committed at HEAD; this table is the '
                   u'authoritative correction and the old manifest is left untouched')
            corr.append(row + [why])
        if f[0] == 'CLOUD_VERIFIABLE_ROWS':
            corr.append([current, '(summary)', 'CLOUD_VERIFIABLE_ROWS', '', '', '', '',
                         '%s of %s rows re-hash to the bytes committed at HEAD' % (f[1], f[3])])
        if f[0] == 'VERIFIABLE_AT_ORIGIN_ROWS':
            corr.append([current, '(summary)', 'VERIFIABLE_AT_ORIGIN_ROWS', '', '', '', '',
                         '%s of %s rows re-hash at the commit that delivered the manifest '
                         '(the rest were revised by a later round or name a path that was never '
                         'committed)' % (f[1], f[3])])
    with io.open(os.path.join(EV, 'sc1_s3c2_manifest_corrections.csv'), 'wb') as fh:
        for r in corr:
            fh.write((u','.join([u'"%s"' % c for c in r]) + u'\n').encode('utf-8'))
    print('S3C2_CORRECTIONS rows=%d' % (len(corr) - 1))

    rows = []
    skip = 'results/evidence/sc1_s3c2_round_manifest.csv'
    for p in git_files():
        if p == skip:
            continue
        # hash what the index will commit, not what the working tree holds: those differ for any
        # file edited after staging, and the reviewable artefact is the commit
        proc = subprocess.Popen(['git', '-C', ROOT, 'cat-file', 'blob', ':%s' % p],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        b = proc.communicate()[0]
        if proc.returncode != 0:
            print('MANIFEST-SKIP-NOSTAGED %s' % p)
            continue
        rows.append([p, sha(b), len(b), 'yes'])
    with io.open(os.path.join(EV, 'sc1_s3c2_round_manifest.csv'), 'wb') as fh:
        fh.write(u'"file","sha256","bytes","role","cloud_can_verify_bytes","note"\n'.encode(
            'utf-8'))
        for p, h, n, ok in rows:
            role = p.split('/')[1] if '/' in p and p.split('/')[0] in ('reports', 'results',
                                                                        'scripts', 'skill') else p
            fh.write((u'"%s","%s","%d","s3c2_%s","%s","hashed from the staged blob, which is what '
                      u'this round commits; excluded row: the manifest itself"\n'
                      % (p, h, n, role, ok)).encode('utf-8'))
    print('S3C2_ROUND_MANIFEST rows=%d' % len(rows))
    return 0


sys.exit(main())
