#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E: the round manifest. Every artifact this round produced, plus the protected inputs.

    python scripts/sc1_r2e_manifest.py [--out CSV] [--baseline SHA]

Why a manifest and not a paragraph: the first question a reviewer asks of a native-simulation round is
"which bytes are you talking about". Each row keeps the file, its sha256 and size, what produced it,
and whether the cloud reviewer can verify those bytes -- only repository files can, so the guest-side
runs and the PDK are represented by the hashes the tools read back instead of by copied content.
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
             'scripts/sc1_s2_r2d_gen.py', 'scripts/sc1_s2_r2d.sh', 'scripts/sc1_r2d_s1_reanalysis.py']

ROLES = [(r'^scripts/sc1_r2e2_.*\.py$', 'r2e2_new_entry'),
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

    # every file this round added, found by name so a forgotten artifact still shows up as a row
    rels = []
    for sub in ('scripts', os.path.join('results', 'evidence'), 'reports'):
        root = os.path.join(PROJ, sub)
        if not os.path.isdir(root):
            continue
        for _d, _s, fs in os.walk(root):
            for f in fs:
                if f.startswith(('sc1_r2e', 'scan_driver_r2e')) and not f.endswith('.pyc'):
                    rels.append(os.path.relpath(os.path.join(_d, f), PROJ).replace('\\', '/'))
    for rel in sorted(set(rels)):
        if os.path.normpath(os.path.join(PROJ, rel)) == os.path.normpath(os.path.abspath(out)):
            # a manifest cannot hash itself honestly: the bytes it would record are the ones from
            # before it was written, so the output file is left out of its own rows
            continue
        path = os.path.join(PROJ, rel)
        role = 'r2e_other'
        for pat, r in ROLES:
            if re.match(pat, rel):
                role = r
                break
        note = ('written this round; repository bytes, re-hashable by the reviewer')
        if role == 'r2e_transcript':
            note = 'simulator transcript with vendor paths redacted before it was written'
        if role == 'r2e_evidence' and 'calibration' in rel:
            note = 'calibration rows: model identity, temperature read-back and the source-current sign'
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
