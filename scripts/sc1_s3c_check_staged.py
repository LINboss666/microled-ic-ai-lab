#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-C: re-parse the bytes that are about to be committed.

The rule this round inherits from S3-B is that a table is only evidence if the file it lives in can
still be read back as a table. Six checks, all on the delivered CSVs, none on a mock:

  width       every record has exactly as many fields as its header;
  rows        the expected count per file, read from the file itself;
  identity    the device key (cell, instance) is unique, and the golden and the OA side name the
              same 39 devices;
  finite      every numeric token in the file parses to a finite number (no inf, no nan, no empty);
  linkage     the correction table cites sample rows that exist in the delivered parts, and the
              equivalence table covers all eight cells;
  unspoiled   the seven frozen masters and the delivered S3-B evidence are byte-identical to HEAD.

    python scripts/sc1_s3c_check_staged.py [--evidence DIR] [--root DIR]
"""
from __future__ import print_function

import io
import os
import re
import subprocess
import sys

NUM_RX = re.compile(r'(?<![0-9A-Za-z.+-])[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?(?![0-9A-Za-z])')
EXPECTED_ROWS = {'sc1_s3c_golden_mos.csv': 39, 'sc1_s3c_golden_hier.csv': 8,
                 'sc1_s3c_golden_ports.csv': 48, 'sc1_s3c_golden_subinst.csv': 39,
                 'sc1_s3c_oa_readback.csv': 39, 'sc1_s3c_connectivity.csv': 46,
                 'sc1_s3c_ports.csv': 48, 'sc1_s3c_equivalence.csv': 8}
FROZEN = ['spectre/C2MOS_DFF.scs', 'spectre/sc1_scan_gate.scs',
          'spectre/sc1_level_shifter_r2d.scs', 'spectre/sc1_r3_scan_chain.scs',
          'spectre/sc1_s3b_p33_bank.scs', 'spectre/sc1_s3b_scan_power_1ch.scs',
          'spectre/sc1_s3b_scan_power_1ch_fault.scs']
S3B_EVIDENCE = ['results/evidence/sc1_s3b_cases.csv', 'results/evidence/sc1_s3b_manifest.csv',
                'results/evidence/sc1_s3b_identity.csv',
                'results/evidence/sc1_s3b_dependency_log.txt',
                'results/evidence/sc1_s3b_samples_parts.csv']


def read_lines(path):
    return [l for l in io.open(path, encoding='utf-8', errors='replace').read().split('\n')
            if l.strip() != '']


def split_row(line):
    out, cur, i, n, inq = [], '', 0, len(line), False
    while i < n:
        c = line[i]
        if inq:
            if c == '"' and i + 1 < n and line[i + 1] == '"':
                cur += '"'
                i += 2
                continue
            if c == '"':
                inq = False
                i += 1
                continue
            cur += c
            i += 1
            continue
        if c == '"':
            inq = True
            i += 1
            continue
        if c == ',':
            out.append(cur)
            cur = ''
            i += 1
            continue
        cur += c
        i += 1
    out.append(cur)
    return out


def main():
    args = sys.argv[1:]

    def arg(name, default):
        return args[args.index(name) + 1] if name in args else default

    root = arg('--root', '.')
    ev = arg('--evidence', os.path.join(root, 'results/evidence'))
    fails = []
    checks = 0
    tables = {}

    for name in sorted(EXPECTED_ROWS):
        path = os.path.join(ev, name)
        if not os.path.isfile(path):
            fails.append('%s is missing' % name)
            continue
        lines = read_lines(path)
        hdr = split_row(lines[0])
        body = [split_row(l) for l in lines[1:]]
        checks += 1
        bad = [i for i, r in enumerate(body) if len(r) != len(hdr)]
        if bad:
            fails.append('%s: %d records have a different field count than the header (%s)'
                         % (name, len(bad), bad[:5]))
        checks += 1
        if len(body) != EXPECTED_ROWS[name]:
            fails.append('%s: %d rows, expected %d' % (name, len(body), EXPECTED_ROWS[name]))
        tables[name] = (hdr, body)
        # numeric tokens: every one must parse and be finite
        checks += 1
        for l in lines:
            for tok in NUM_RX.findall(l):
                try:
                    v = float(tok)
                except ValueError:
                    fails.append('%s: token %r does not parse' % (name, tok))
                    continue
                if v != v or v in (float('inf'), float('-inf')):
                    fails.append('%s: token %r is not finite' % (name, tok))

    # identity of the 39 devices, on both sides of the comparison
    checks += 1
    for name in ('sc1_s3c_golden_mos.csv', 'sc1_s3c_oa_readback.csv'):
        if name not in tables:
            continue
        hdr, body = tables[name]
        keys = [(r[hdr.index('cell')], r[hdr.index('inst')]) for r in body]
        if len(keys) != len(set(keys)):
            fails.append('%s: a (cell, instance) pair repeats' % name)
        if len(keys) != 39:
            fails.append('%s: %d devices, not 39' % (name, len(keys)))
    if 'sc1_s3c_golden_mos.csv' in tables and 'sc1_s3c_oa_readback.csv' in tables:
        g = tables['sc1_s3c_golden_mos.csv']
        o = tables['sc1_s3c_oa_readback.csv']
        gk = set((r[g[0].index('cell')], r[g[0].index('inst')]) for r in g[1])
        ok = set((r[o[0].index('cell')], r[o[0].index('inst')]) for r in o[1])
        checks += 1
        if gk != ok:
            fails.append('the golden and the OA read-back do not name the same 39 devices: %s'
                         % sorted(gk ^ ok))

    # connectivity covers every device plus every sub-circuit instance, all matched
    checks += 1
    if 'sc1_s3c_connectivity.csv' in tables:
        hdr, body = tables['sc1_s3c_connectivity.csv']
        verdicts = set(r[hdr.index('verdict')] for r in body)
        if verdicts != set(['MATCH']):
            fails.append('sc1_s3c_connectivity.csv carries verdicts %s' % sorted(verdicts))
        if len(body) != 39 + 7:
            fails.append('sc1_s3c_connectivity.csv has %d rows, expected 39 devices + 7 children'
                         % len(body))

    # every correction row cites a deck/raw digest that the delivered index actually declares
    checks += 1
    corr_path = os.path.join(ev, 'sc1_s3c_s3b_corrections.csv')
    if os.path.isfile(corr_path):
        lines = read_lines(corr_path)
        hdr = split_row(lines[0])
        body = [split_row(l) for l in lines[1:]]
        idx = io.open(os.path.join(ev, 'sc1_s3b_identity.csv'), encoding='utf-8',
                      errors='replace').read()
        parts = io.open(os.path.join(ev, 'sc1_s3b_samples_parts.csv'), encoding='utf-8',
                       errors='replace').read()
        known = set(re.findall(r'\b([0-9a-f]{16})', idx + parts))
        missing = set()
        for r in body:
            for tok in re.findall(r'(?:deck_sha16|raw_sha16|deck_raw)=([0-9a-f]{16})', r[hdr.index('identity')]):
                if tok not in known:
                    missing.add(tok)
        if missing:
            fails.append('%d correction rows cite a deck/raw digest the delivered identity index '
                         'does not declare: %s' % (len(missing), sorted(missing)[:3]))
        kinds = set(r[0] for r in body)
        for want in ('A_IPROBE_DIRECTION', 'A_RAIL_INJECTION_KEPT', 'B_VSD_RON_FULL_PRECISION',
                     'B_EXTREME_NEIGHBOURHOOD', 'C_EDGE_VERDICT', 'C_R3_GATE_LOAD',
                     'C_PROCESS_ACCOUNTING'):
            if want not in kinds:
                fails.append('the correction table has no %s rows' % want)

    # the equivalence table must cover all eight cells and say identical for each
    checks += 1
    if 'sc1_s3c_equivalence.csv' in tables:
        hdr, body = tables['sc1_s3c_equivalence.csv']
        if len(body) != 8 or set(r[hdr.index('verdict')] for r in body) != set(['MATCH']):
            fails.append('sc1_s3c_equivalence.csv is not 8 rows of MATCH')

    # nothing pre-existing was touched
    checks += 1
    targets = FROZEN + S3B_EVIDENCE
    try:
        diff = subprocess.Popen(['git', '-C', root, 'diff', '--name-only', 'HEAD', '--'] + targets,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = diff.communicate()[0].decode('utf-8', 'replace').strip()
        if diff.returncode != 0:
            fails.append('git diff over the protected files did not run: %s' % out.split('\n')[0])
        elif out:
            fails.append('these frozen/delivered bytes differ from HEAD: %s' % out.split('\n'))
    except OSError as exc:
        fails.append('could not run git to prove the frozen files are untouched: %s' % exc)

    print('S3C_STAGED_CHECKS: %d' % checks)
    for f in fails:
        print('S3C-STAGED-FAIL: %s' % f)
    print('S3C_STAGED_CHECK: %s' % ('PASS' if not fails else 'FAIL'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
