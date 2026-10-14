#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C1: fail-closed checks over the corrected read-back tables.

Every claim this round makes in prose is asserted here against the repository bytes, so a reviewer
runs one command instead of re-reading logs. It also pins the UNWANTED state on purpose: the symbol
pins are measured to sit on the right, so if a later round moves them the check tells the reader the
table was regenerated rather than silently agreeing.

No simulator, no preflight, no operating point. Nothing is written.

usage: python scripts/sc1_s3c1_check.py [--root DIR]
"""
from __future__ import print_function
import io
import os
import re
import sys

EXPECTED = {'sc1_s3c1_ports.csv': 96, 'sc1_s3c1_graphics.csv': 8,
            'sc1_s3c1_symbol_side.csv': 48, 'sc1_s3c1_connectivity.csv': 39,
            'sc1_s3c1_editor_check.csv': 16, 'sc1_s3c1_oa_readback.csv': 16,
            'sc1_s3c1_equivalence.csv': 13}
PRIVATE = re.compile(r'/root/[a-z0-9_]+')


def read_lines(path):
    return [l for l in io.open(path, encoding='utf-8', errors='replace').read().split('\n')
            if l.strip() != '']


def rows(path):
    lines = read_lines(path)
    hdr = [h.strip().strip('"') for h in lines[0].split(',')]
    out = []
    for l in lines[1:]:
        f = [c.strip().strip('"') for c in l.split(',')]
        if len(f) != len(hdr):
            raise ValueError('field count %d != header %d in %s' % (len(f), len(hdr), path))
        out.append(dict(zip(hdr, f)))
    return out


def main():
    args = sys.argv[1:]
    root = args[args.index('--root') + 1] if '--root' in args else '.'
    ev = os.path.join(root, 'results', 'evidence')
    fails = []
    n = 0

    tables = {}
    for name, want in sorted(EXPECTED.items()):
        p = os.path.join(ev, name)
        n += 1
        if not os.path.isfile(p):
            fails.append('%s is missing' % name)
            continue
        try:
            r = rows(p)
        except ValueError as exc:
            fails.append(str(exc))
            continue
        tables[name] = r
        n += 1
        if len(r) != want:
            fails.append('%s has %d rows, expected %d' % (name, len(r), want))

    # --- port directions: read from the database, compared to the golden table there ------------
    if 'sc1_s3c1_ports.csv' in tables:
        r = tables['sc1_s3c1_ports.csv']
        n += 1
        if sum(1 for x in r if x['matches_golden'] != 'yes') != 0:
            fails.append('a terminal does not carry the golden direction in the OA database')
        n += 1
        if (sum(1 for x in r if x['view'] == 'schematic'),
                sum(1 for x in r if x['view'] == 'symbol')) != (48, 48):
            fails.append('ports.csv is not 48 schematic + 48 symbol terminals')
        n += 1
        want_by_view = {'signal_in': 'input', 'signal_out': 'output', 'supply': 'inputOutput'}
        gold = rows(os.path.join(ev, 'sc1_s3c_golden_ports.csv'))
        goldmap = dict(((g['cell'], g['port']), g['declared_direction']) for g in gold)
        bad = [x for x in r if goldmap.get((x['cell'], x['term'])) != x['golden_direction']]
        if bad:
            fails.append('%d read-back rows disagree with the golden declaration itself' % len(bad))

    # --- symbol graphics: content exists, placement is the measured gap -------------------------
    if 'sc1_s3c1_graphics.csv' in tables:
        r = tables['sc1_s3c1_graphics.csv']
        n += 1
        if any(x['body_rect'] != 'yes' or x['complete_set'] != 'yes' for x in r):
            fails.append('a symbol lacks a body rect or has pin/stub/label counts that do not '
                         'match its terminal count -- the S3-C "0 figures" claim must not return')
    if 'sc1_s3c1_symbol_side.csv' in tables:
        r = tables['sc1_s3c1_symbol_side.csv']
        n += 1
        sides = set(x['measured_side'] for x in r)
        if sides != set(['right']):
            fails.append('pin sides changed from the recorded state (%s): the placement tables were '
                         'regenerated and every downstream claim must be re-read'
                         % ','.join(sorted(sides)))
        n += 1
        if sum(1 for x in r if x['matches_side'] == 'yes') != 10:
            fails.append('the role match is not the measured 10 of 48')

    # --- parents: no detached pin, and the check that exists ------------------------------------
    if 'sc1_s3c1_connectivity.csv' in tables:
        r = tables['sc1_s3c1_connectivity.csv']
        n += 1
        if any(x['wire_reaches_pin'] != 'yes' for x in r):
            fails.append('a sub-instance pin has no wire reaching it')
        n += 1
        if any(x['parent_net'] in ('NONE', '') for x in r):
            fails.append('an instance terminal has no net name in the parent view')
    if 'sc1_s3c1_editor_check.csv' in tables:
        r = tables['sc1_s3c1_editor_check.csv']
        n += 1
        sch = [x for x in r if x['view'] == 'schematic']
        if len(sch) != 8 or any(int(x['errors']) != 0 for x in sch):
            fails.append('schCheck is not 0 errors on all eight schematics')
        n += 1
        sym = [x for x in r if x['view'] == 'symbol']
        if len(sym) != 8 or any(x['check_available'] != 'no_schCheck_returns_nil_for_this_view_type'
                                for x in sym):
            fails.append('the symbol views are not recorded as the nil-schCheck case they are')

    # --- the corrected fields themselves --------------------------------------------------------
    if 'sc1_s3c1_oa_readback.csv' in tables:
        r = tables['sc1_s3c1_oa_readback.csv']
        n += 1
        if any(not x['cv_terminals'].startswith('COUNT=') for x in r):
            fails.append('cv->terminals did not return a count for every view')
        n += 1
        if any(not x['cv_terms'].startswith('EMPTY') for x in r):
            fails.append('cv->terms is not the supported-but-empty attribute the S3-C reader '
                         'mistook for "no ports"')

    # --- graph equivalence verdict rows ---------------------------------------------------------
    if 'sc1_s3c1_equivalence.csv' in tables:
        d = dict((x['verdict'], x['value']) for x in tables['sc1_s3c1_equivalence.csv'])
        for k, want in (('S3C_OA_DEVICE_COUNT', '39'), ('S3C_OA_PORT_PINS', '48'),
                        ('S3C_OA_SYMBOL_TERMINALS', '48'), ('S3C_CONNECTIVITY_MATCH', '46'),
                        ('S3C_EQUIVALENCE_MATCH', '8'), ('S3C_OA_GRAPH_EQUIVALENCE', 'PASS'),
                        ('S3C_VERDICT_COUNTS', 'failures=0 notes=3')):
            n += 1
            if k not in d or not d[k].startswith(want):
                fails.append('comparator row %s is %r, expected %r' % (k, d.get(k, 'MISSING'), want))

    # --- no private path in a committed log, and the report retraction is present ---------------
    logs = [f for f in os.listdir(ev) if f.startswith('sc1_s3c1_') and f.endswith('.log')]
    n += 1
    hits = []
    for f in logs:
        for l in read_lines(os.path.join(ev, f)):
            if PRIVATE.search(l):
                hits.append('%s: %s' % (f, PRIVATE.search(l).group(0)))
                break
    if hits:
        fails.append('a committed log still carries a private home path: %s' % hits[:3])
    rep = os.path.join(root, 'reports', 'scan_driver_s3c_schematic_symbol.md')
    n += 1
    if 'Retracted in S3C1' not in io.open(rep, encoding='utf-8').read():
        fails.append('the S3-C report no longer carries the retraction of its own attributions')

    print('S3C1_CHECKS: %d' % n)
    for f in fails:
        print('S3C1-FAIL: %s' % f)
    print('S3C1_CHECK: %s' % ('PASS' if not fails else 'FAIL'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
