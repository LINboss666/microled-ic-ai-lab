#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2A / R1-C: read back the preflight matrix and audit it as evidence.

    python scripts/sc1_csv_audit.py <matrix.csv>

The submitted matrix of the previous round had a 7-column header but a first data row that parsed
as 8 columns (an unescaped comma in the description), and its `case` column held the supply map
instead of the case id, so ids were not unique. This auditor therefore checks structure, not
appearance:

 * every record has exactly the header's column count (real CSV parsing, quotes honoured)
 * case ids are present and unique
 * the recorded verdict can be recomputed from the declared expectations and the recorded actuals
 * a refusal names a stage, a reason, and never reached the simulator
 * a PASS row carries no rejection stage
 * the expected reason token is really in the log file the row points at
"""
from __future__ import print_function
import csv, io, os, sys

COLS = ['caseid', 'class', 'mode', 'cli', 'supply_map', 'connection_changed', 'expected_rc',
        'expected_stage', 'expected_token', 'actual_rc', 'actual_stage', 'actual_reason',
        'simulator_called', 'verdict', 'evidence_note', 'log_path']


def read_rows(path):
    # python 2.6's csv module works on byte lines, python 3's on text lines: read bytes and let
    # the interpreter that runs the audit decide.
    with open(path, 'rb') as bf:
        raw = bf.read()
    lines = [l for l in raw.split(b'\n') if l.strip() != b'']
    if sys.version_info[0] >= 3:
        lines = [l.decode('utf-8', 'replace') for l in lines]
    if not lines:
        return None, []
    recs = list(csv.reader(lines))
    return recs[0], recs[1:]


def main():
    if len(sys.argv) < 2:
        print('USAGE: sc1_csv_audit.py <matrix.csv>')
        return 2
    path = sys.argv[1]
    if not os.path.isfile(path):
        print('HARNESS_ERROR csv_missing %s' % path)
        return 8
    header, rows = read_rows(path)
    if header is None:
        print('HARNESS_ERROR csv_empty %s' % path)
        return 8
    problems = []
    if [c.strip() for c in header] != COLS:
        problems.append('header mismatch: %s' % ','.join(header))
    if not rows:
        problems.append('no data rows')
    ids = []
    tally = {}
    for i, r in enumerate(rows):
        cid = r[0] if r else 'row%d' % (i + 2)
        ids.append(cid)
        if len(r) != len(COLS):
            problems.append('%s columns=%d want=%d' % (cid, len(r), len(COLS)))
            continue
        d = dict(zip(COLS, r))
        tally[d['verdict']] = tally.get(d['verdict'], 0) + 1
        if d['verdict'] not in ('PASS', 'FAIL', 'BLOCKED'):
            problems.append('%s verdict not one of PASS/FAIL/BLOCKED: %s' % (cid, d['verdict']))
        for k in ('expected_rc', 'actual_rc'):
            for part in (d[k].split(',') if k == 'expected_rc' else [d[k]]):
                try:
                    int(part)
                except ValueError:
                    problems.append('%s %s is not an integer list: %r' % (cid, k, d[k]))
        # an expected_rc may be an explicit allowed set, e.g. "1,2" for a checker crash whose exit
        # status differs between gawk versions; the actual code must be one of them.
        allowed = [x.strip() for x in d['expected_rc'].split(',')]
        refusal = not any(x == '0' for x in allowed)
        if refusal:
            if not d['expected_stage']:
                problems.append('%s negative case declares no rejection stage' % cid)
            if not d['expected_token']:
                problems.append('%s negative case declares no reason token' % cid)
            if not d['actual_reason']:
                problems.append('%s negative case recorded no actual reason' % cid)
            if d['simulator_called'] == 'yes':
                problems.append('%s static-layer refusal still reached the simulator' % cid)
            if d['connection_changed'] in ('', 'none'):
                problems.append('%s negative case does not say what was changed' % cid)
        else:
            if d['actual_stage'] in ('supply_contract', 'static_parse'):
                problems.append('%s acceptance row carries a rejection stage %s' % (cid, d['actual_stage']))
            want_sim = 'yes' if d['mode'] == 'full' else 'no'
            if d['simulator_called'] != want_sim:
                problems.append('%s acceptance row simulator_called=%s but mode=%s'
                                % (cid, d['simulator_called'], d['mode']))
        # recompute the verdict the way the runner claims it was decided
        recomputed = 'PASS'
        if d['actual_rc'] not in allowed:
            recomputed = d['verdict'] if d['verdict'] == 'BLOCKED' else 'FAIL'
        if d['expected_stage'] and d['actual_stage'] != d['expected_stage'] and recomputed == 'PASS':
            recomputed = 'FAIL'
        if recomputed == 'PASS' and d['expected_token']:
            log = d['log_path']
            if not log or not os.path.isfile(log):
                recomputed = 'FAIL'
            else:
                with io.open(log, 'r', encoding='utf-8', errors='replace') as lf:
                    text = lf.read()
                for tk in d['expected_token'].split('+'):
                    if tk and tk not in text:
                        recomputed = 'FAIL'
                        break
        if recomputed != d['verdict']:
            problems.append('%s verdict recorded %s but recomputes to %s' % (cid, d['verdict'], recomputed))
    if len(set(ids)) != len(ids):
        dup = [x for x in ids if ids.count(x) > 1]
        problems.append('case ids not unique: %s' % ','.join(sorted(set(dup))))

    print('CSV_AUDIT rows=%d columns=%d verdicts=%s' % (len(rows), len(COLS), sorted(tally.items())))
    if problems:
        for p in problems[:40]:
            print('CSV_AUDIT_PROBLEM %s' % p)
        print('CSV_AUDIT: FAIL (%d problems)' % len(problems))
        return 1
    print('CSV_AUDIT: PASS (structure, unique ids, rc/stage/reason correspondence)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
