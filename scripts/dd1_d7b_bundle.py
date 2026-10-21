# -*- coding: utf-8 -*-
"""DATA-7B review bundle: the full dependency set, taken from committed Git blobs.

    python scripts/dd1_d7b_bundle.py <base-sha> <tip-sha> [--out review/xxx.zip]

The shared `make_review_bundle.py` is not modified and does not collect `.sv` sources, so this round's
packer adds them. Every byte comes from `git cat-file blob <tip>:<path>`, never from the working tree,
and the manifest carries the full source SHA of the commit those bytes belong to. The manifest is not
inside its own file list, and the ZIP digest is reported outside the package.
"""
from __future__ import print_function

import hashlib
import io
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import repo_safety_rules as RULES          # frozen single source of the safety rules

MAX_BLOB = 512 * 1024

ROUNDED = [
    'reports/tasks/DATA-7B.md',
    'reports/dd1_d7b_contract.md',
    'reports/dd1_d7b_pwm_current.md',
    'reports/agent_handoffs/DATA-7B.md',
    'reports/agent_handoffs/DATA-7B.json',
    'tests/dd1_d7b/tb_dd1_d7b_pwm.sv',
    'tests/dd1_d7b/golden_windows.csv',
    'tests/dd1_d7b/cases.csv',
    'spectre/dd1_d7b_pwm_stage.scs',
    'scripts/dd1_d7b_trace.py',
    'scripts/dd1_d7b_measure.py',
    'scripts/dd1_d7b_run.py',
    'scripts/dd1_d7b_evidence_check.py',
    'scripts/dd1_d7b_validate_handoff.py',
    'scripts/dd1_d7b_bundle.py',
]

CALLEDD = [
    'rtl/dd1_d7a_gray_ctrl.sv',
    'reports/dd1_d7a_contract.md',
    'spectre/dd1_d6_bias_core.scs',
    'spectre/dd1_d6_sink_core.scs',
    'spectre/dd1_d6_inv18.scs',
    'scripts/run_spectre.sh',
    'scripts/tb_preflight.sh',
    'scripts/sc1_supply_check.awk',
    'scripts/sc1_read_psf.py',
    'scripts/sc1_r2e1_call_contract.py',
    'scripts/repo_safety_rules.py',
    'scripts/test_safety_rules.py',
    'scripts/precommit_safety_check.py',
    'scripts/provenance_check.py',
    'scripts/netlist_stats.py',
    'scripts/make_review_bundle.py',
    'scripts/dd1_d7a_bundle.py',
    'README.md',
    'AGENTS.md',
    'CONTRIBUTING_AI.md',
    '.gitignore',
]


def git(ref, path):
    p = subprocess.Popen(['git', 'cat-file', 'blob', '%s:%s' % (ref, path)], cwd=PROJ,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError('git cat-file blob %s:%s failed: %s' % (ref, path, err.decode()[:120]))
    return raw


def main(argv):
    if len(argv) < 2:
        print('usage: dd1_d7b_bundle.py <base-sha> <tip-sha> [--out path]')
        return 2
    base, tip = argv[0], argv[1]
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(
        PROJ, 'review', 'dd1_d7b_bundle_%s.zip' % tip[:7])
    if not os.path.isdir(os.path.dirname(out)):
        os.makedirs(os.path.dirname(out))
    # the evidence tree is enumerated from the commit, so nothing on disk can leak into the package
    listing = subprocess.Popen(['git', 'ls-tree', '-r', '--name-only', tip], cwd=PROJ,
                               stdout=subprocess.PIPE).communicate()[0].decode('utf-8', 'replace')
    evidence = [l for l in listing.split('\n')
                if l.startswith('results/evidence/dd1_d7b_') and not l.endswith('manifest.json')]
    want = []
    for p in ROUNDED + CALLEDD:
        if p in evidence:
            continue
        want.append(p)
    want += sorted(evidence)
    seen = set()
    entries = []
    problems = []
    for path in want:
        if path in seen:
            continue
        seen.add(path)
        try:
            blob = git(tip, path)
        except RuntimeError as exc:
            problems.append(str(exc))
            continue
        if len(blob) > MAX_BLOB:
            problems.append('%s is %d bytes, over the %d KiB blob limit'
                            % (path, len(blob), MAX_BLOB // 1024))
            continue
        blocked = RULES.scan_content(path, blob) if hasattr(RULES, 'scan_content') else []
        if blocked:
            problems.append('%s refused by the safety rules: %s' % (path, blocked))
            continue
        entries.append((path, blob))
    manifest = ['path,bytes,sha256,source_sha', ]
    for path, blob in entries:
        manifest.append('%s,%d,%s,%s' % (path, len(blob),
                                          hashlib.sha256(blob).hexdigest(), tip))
    mbytes = ('\n'.join(manifest) + '\n').encode('utf-8')
    zmode = 0o644
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, blob in entries:
            zi = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            zi.external_attr = (zmode & 0o777) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, blob)
        zi = zipfile.ZipInfo('MANIFEST.csv', date_time=(1980, 1, 1, 0, 0, 0))
        zi.external_attr = (zmode & 0o777) << 16
        z.writestr(zi, mbytes)
    # read the package back and compare against the same blobs
    bad = []
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        for path, blob in entries:
            if path not in names:
                bad.append('%s missing from the zip' % path)
            elif hashlib.sha256(z.read(path)).hexdigest() != hashlib.sha256(blob).hexdigest():
                bad.append('%s bytes differ inside the zip' % path)
        for path, blob in entries:
            if path in names and path not in [e[0] for e in entries]:
                bad.append('%s inside the zip was never an entry' % path)
    print('BUNDLE %s' % out)
    print('BUNDLE_BASE_SHA %s' % base)
    print('BUNDLE_SOURCE_SHA %s (every packaged byte is this commit\'s blob)' % tip)
    print('BUNDLE_FILES %d + MANIFEST.csv' % len(entries))
    print('BUNDLE_EVIDENCE_FILES %d' % len(evidence))
    print('BUNDLE_ZIP_BYTES %d' % os.path.getsize(out))
    print('BUNDLE_ZIP_SHA256 %s   (recorded outside the package)'
          % hashlib.sha256(open(out, 'rb').read()).hexdigest())
    for b in bad + problems:
        print('BUNDLE_PROBLEM %s' % b)
    print('BUNDLE_RESULT %s' % ('PASS' if not (bad or problems) else 'FAIL'))
    return 0 if not (bad or problems) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
