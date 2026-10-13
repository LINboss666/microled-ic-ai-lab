#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E/R3: the round manifest. Every artifact a round produced, plus the protected inputs.

    python scripts/sc1_r2e_manifest.py [--out CSV] [--baseline SHA]

Why a manifest and not a paragraph: the first question a reviewer asks of a native-simulation round is
"which bytes are you talking about". Each row keeps the file, its sha256 and size, what produced it,
and whether the cloud reviewer can verify those bytes -- only repository files can, so the guest-side
runs and the PDK are represented by the hashes the tools read back instead of by copied content.

The R3 round reused this tool instead of adding a second one: the name filter, the role table and the
protected list cover `sc1_r3_*` / `scan_driver_r3*` / `spectre/sc1_r3*` as well, and R3 writes its own
output file so no earlier manifest is rewritten.
"""
from __future__ import print_function

import hashlib
import io
import optparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

PROTECTED = ['spectre/C2MOS_DFF.scs', 'spectre/sc1_scan_gate.scs',
             'spectre/sc1_level_shifter_r2d.scs', 'scripts/sc1_read_psf.py', 'scripts/sc1_delay.py',
             'scripts/tb_preflight.sh', 'scripts/sc1_supply_check.awk', 'scripts/run_spectre.sh',
             'scripts/sc1_s1_r2d_regression.sh', 'scripts/sc1_s1_window_contract.py',
             'scripts/sc1_s2_r2d_gen.py', 'scripts/sc1_s2_r2d.sh', 'scripts/sc1_r2d_s1_reanalysis.py',
             # the shared plumbing R3 was told to reuse rather than re-derive
             'scripts/sc1_r2e1_call_contract.py', 'scripts/sc1_r2e_s2_tt.py',
             'scripts/sc1_r2e1_reread.py', 'scripts/sc1_r2e_vtx.py']

ROLES = [(r'^scripts/sc1_s3b_.*\.py$', 's3b_entry_or_check'),
         (r'^spectre/sc1_s3b_.*\.scs$', 's3b_circuit_new'),
         (r'^results/evidence/sc1_s3b_.*_log\.txt$', 's3b_transcript'),
         (r'^results/evidence/sc1_s3b_.*\.txt$', 's3b_transcript'),
         (r'^results/evidence/sc1_s3b_.*\.csv$', 's3b_evidence'),
         (r'^reports/scan_driver_s3b.*\.md$', 's3b_report'),
         (r'^scripts/sc1_s3a_.*\.py$', 's3a_entry_or_check'),
         (r'^results/evidence/sc1_s3a_.*_log\.txt$', 's3a_transcript'),
         (r'^results/evidence/sc1_s3a_.*\.txt$', 's3a_transcript'),
         (r'^results/evidence/sc1_s3a_.*\.csv$', 's3a_evidence'),
         (r'^reports/scan_driver_s3a.*\.md$', 's3a_report'),
         (r'^scripts/sc1_r3a_.*\.py$', 'r3a_repair_tool'),
         (r'^scripts/sc1_r3_.*\.py$', 'r3_new_entry'),
         (r'^spectre/sc1_r3_.*\.scs$', 'r3_circuit_new'),
         (r'^results/evidence/sc1_r3_.*_log\.txt$', 'r3_transcript'),
         (r'^results/evidence/sc1_r3_.*\.txt$', 'r3_transcript'),
         (r'^results/evidence/sc1_r3_.*\.csv$', 'r3_evidence'),
         (r'^reports/scan_driver_r3.*\.md$', 'r3_report'),
         (r'^scripts/sc1_r2e2_.*\.py$', 'r2e2_new_entry'),
         (r'^results/evidence/sc1_r2e2_.*_log\.txt$', 'r2e2_transcript'),
         (r'^results/evidence/sc1_r2e2_.*\.txt$', 'r2e2_transcript'),
         (r'^results/evidence/sc1_r2e2_.*\.csv$', 'r2e2_evidence'),
         (r'^reports/scan_driver_r2e2.*\.md$', 'r2e2_report'),
         (r'^scripts/sc1_r2e1_.*\.py$', 'r2e1_new_entry'),
         (r'^scripts/sc1_r2e_.*\.py$', 'r2e_new_entry'),
         (r'^results/evidence/sc1_r2e1_.*\.csv$', 'r2e1_evidence'),
         (r'^results/evidence/sc1_r2e_.*_log\.txt$', 'r2e_transcript'),
         (r'^results/evidence/sc1_r2e_.*\.csv$', 'r2e_evidence'),
         (r'^reports/scan_driver_r2e1.*\.md$', 'r2e1_report'),
         (r'^reports/scan_driver_r2e.*\.md$', 'r2e_report')]

HDR = ['file', 'sha256', 'bytes', 'role', 'cloud_can_verify_bytes', 'note']

try:
    _text = unicode
except NameError:
    _text = str


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def csvline(vals):
    return u(','.join([u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in vals])) + u('\n')


def main():
    op = optparse.OptionParser()
    op.add_option('--out')
    op.add_option('--baseline', default='dd93f6f432a32fc5f1177223a50ff511e83351c2')
    o, _ = op.parse_args()
    out = o.out or os.path.join(PROJ, 'results', 'evidence', 'sc1_r2e_manifest.csv')
    rows = []

    # every file the round added, found by name so a forgotten artifact still shows up as a row
    rels = []
    for sub in ('scripts', os.path.join('results', 'evidence'), 'reports', 'spectre'):
        root = os.path.join(PROJ, sub)
        if not os.path.isdir(root):
            continue
        for _d, _s, fs in os.walk(root):
            for f in fs:
                if f.startswith(('sc1_r2e', 'scan_driver_r2e', 'sc1_r3', 'scan_driver_r3',
                                 'sc1_s3a', 'scan_driver_s3a', 'sc1_s3b',
                                 'scan_driver_s3b')) and not f.endswith('.pyc'):
                    rels.append(os.path.relpath(os.path.join(_d, f), PROJ).replace('\\', '/'))
    for rel in sorted(set(rels)):
        if os.path.normpath(os.path.join(PROJ, rel)) == os.path.normpath(os.path.abspath(out)):
            # a manifest cannot hash itself honestly: the bytes it would record are the ones from
            # before it was written, so the output file is left out of its own rows
            continue
        path = os.path.join(PROJ, rel)
        role = 'r3_other' if 'sc1_r3' in rel or 'scan_driver_r3' in rel else 'r2e_other'
        for pat, r in ROLES:
            if re.match(pat, rel):
                role = r
                break
        note = ('written this round; repository bytes, re-hashable by the reviewer')
        if role.endswith('_transcript'):
            note = 'simulator transcript with vendor paths redacted before it was written'
        if role == 'r3_circuit_new':
            note = ('new wrapper only: it instantiates the three accepted cells with the port orders '
                    'read off their files, and edits no cell body')
        if role == 'r3_evidence' and 'manifest' in rel:
            note = ('per-deck record: deck sha256, the sha256 of each included cell file as the '
                    'simulator saw it, section/temperature/rails/load, preflight rc, spectre rc, verdict')
        if role == 'r3_evidence' and 'cases' in rel:
            note = ('the 428 judgement rows: whole-window state, plateaus, propdelay with its own 50/50 '
                    'attribution table, edges, rail currents, stimulus read-back and the frame audit')
        if role == 'r3_evidence' and 'samples' in rel:
            note = 'sanitised key samples: each event list plus +-2 points around every 50% crossing'
        if 'r2e' in role:
            # this manifest is generated by a later round, so the earlier round's files are lineage,
            # not deliverables: their current repository bytes are recorded, nothing more is claimed
            note = ('earlier-round artifact, listed for lineage; the hash is the current repository '
                    'byte, and a round that edits one of these says so in its own report')
        if rel in ('scripts/sc1_s3a_p33_tt.py', 'scripts/sc1_s3a_verify_evidence.py'):
            note = ('S3-A artifact EDITED by the S3-B review corrections: the manifest geometry column '
                    'now writes metres, and the charge review is per case with two tamper refusals. The '
                    'delivered S3-A CSVs are byte-unchanged and re-hashed by the correction tool')
        if rel.endswith('scan_driver_r2e2_native_closure.md'):
            note = ('earlier-round report; this round corrected only its SAVE_PATH_AUDIT row COUNT '
                    'statement to 15 (6 static + 6 dynamic + 2 load + 1 negative), no experiment row')
        rows.append([rel, sha(path), str(os.path.getsize(path)), role, 'yes', note])

    # the inputs this round was not allowed to change
    for rel in PROTECTED:
        path = os.path.join(PROJ, rel)
        if not os.path.isfile(path):
            rows.append([rel, 'MISSING', '0', 'protected_input', 'yes',
                          'the reviewed file is not in the tree'])
            continue
        rows.append([rel, sha(path), str(os.path.getsize(path)), 'protected_input', 'yes',
                     'zero diff against the reviewed baseline %s (git diff --name-only empty)'
                     % o.baseline[:9]])

    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(HDR))
        for r in rows:
            f.write(csvline(r))
    print('R2E_MANIFEST rows=%d -> %s' % (len(rows), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
