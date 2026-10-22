#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DATA-7B-R1: run the offline gates and deliver their record, machine-generated and sanitised

TASK_DATA7B_R1 section 6 asks the new evidence directory to carry the self-tests and the
write-guard / fake-Link records, not only the numeric tables. A human pasting transcripts would
leak the machine's paths (the guard fixtures live under a Windows temp directory named for this
user) and would let a line be quietly edited, so the record is produced here: each gate is run by
subprocess, only its command, return code and the verdict lines it actually printed are kept, and
any cell that still looks like a local path is dropped rather than redacted.

Nothing here starts Spectre, opens a socket or touches a guest. The gates themselves are offline by
construction; this module only runs them and reports.

usage: python scripts/dd1_d7b_r1_gate_records.py --out <ignored dir> [--project <root>]
"""
from __future__ import print_function

import argparse
import csv
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROJ = os.path.dirname(HERE)

# (record name, arguments, the substring its success line must contain)
BUNDLE = '@EVIDENCE_BUNDLE@'   # substituted with --evidence-base, the bytes the suite is replayed on

GATES = (
    ('measure_selftest', ('scripts/dd1_d7b_measure.py', '--selftest'), 'D7B_MEASURE_SELFTEST: PASS'),
    ('run_entry_selftest', ('scripts/dd1_d7b_run.py', '--selftest'), 'D7B_RUN_SELFTEST: PASS'),
    ('trace_selftest', ('scripts/dd1_d7b_trace.py', '--selftest'), 'D7B_TRACE_SELFTEST: PASS'),
    ('evidence_tamper_selftest', ('scripts/dd1_d7b_evidence_check.py', '--selftest', BUNDLE),
     'D7B_EVIDENCE_SELFTEST: PASS'),
    ('execution_guards', ('scripts/dd1_d7b_r1_guards.py',), 'D7B_R1_GUARDS: PASS'),
    # the R2 suite is the claim of repair: the same fourteen probes that reproduced the findings on
    # the base bytes have to close, and they are run against the evidence this round exported
    ('r2_guards_closed', ('scripts/dd1_d7b_r2_guards.py', '--phase', 'fixed', '--bundle', BUNDLE),
     'D7B_R2_GUARDS: PASS'),
)
LOCAL_PATH = re.compile(r'(?i)([a-z]:[\\/]|/dev/|/home/|/users/|\\\\)')
VERDICT = re.compile(r'^(D7B_[A-Z0-9_]+|GUARD_[A-Z0-9_]+|[0-9]+\.[0-9]+ [a-z].*(PASS|FAIL)|'
                     r'PUBLISH_|SELFTEST_BASELINE|EVIDENCE_READABLE)')
MAX_LINES = 16


def u(text):
    if isinstance(text, bytes):
        return text.decode('utf-8', 'replace')
    return text


def run_gate(proj, name, argv):
    """one gate: its rc, and only the verdict lines it printed with no local path in them"""
    cmd = [sys.executable, os.path.join(proj, argv[0])] + list(argv[1:])
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=proj)
    text = u(p.communicate()[0] or '')
    lines = []
    dropped = 0
    for line in text.split('\n'):
        line = line.strip()
        if not line or not VERDICT.match(line):
            continue
        if LOCAL_PATH.search(line):
            dropped += 1
            continue
        lines.append(line[:160])
    # a gate's verdict is on its last line, so a long transcript is truncated from the middle and
    # never loses that line
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + [lines[-1]]
    return p.returncode, lines, dropped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, help='ignored directory for gate_records.csv')
    ap.add_argument('--project', default=DEFAULT_PROJ)
    ap.add_argument('--evidence-base', default='', help='the staged or published bundle the '
                        'counterfeit suite and the R2 guard suite are replayed against')
    opts = ap.parse_args(argv)
    proj = os.path.abspath(opts.project)
    base = os.path.abspath(opts.evidence_base) if opts.evidence_base else ''
    if opts.evidence_base and not os.path.isfile(os.path.join(base, 'cases.csv')):
        raise SystemExit('D7B_GATE_RECORDS_REFUSED --evidence-base %s has no cases.csv' % base)
    out_dir = os.path.abspath(opts.out)
    if os.path.exists(os.path.join(out_dir, 'gate_records.csv')):
        raise SystemExit('D7B_GATE_RECORDS_REFUSED %s already holds a record; write a fresh one '
                         'into a new directory so two runs cannot share one table' % out_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    rows = []
    for name, args, expect in GATES:
        argv = [a for a in args if a != BUNDLE] if not base else [
            (base if a == BUNDLE else a) for a in args]
        # the command cell travels inside the bundle, where no machine path may appear, so the
        # evidence base is written relative to the project root instead of as an absolute path
        shown = [os.path.relpath(a, proj).replace(os.sep, '/') if a == base else a for a in argv]
        rc, lines, dropped = run_gate(proj, name, argv)
        rows.append({'gate': name,
                     'command': ' '.join(shown),
                     'rc': rc,
                     'verdict': 'PASS' if rc == 0 and any(expect in l for l in lines) else 'FAIL',
                     'expected_line': expect,
                     'printed_lines_kept': len(lines),
                     'lines_dropped_for_local_path': dropped,
                     'printed': ' | '.join(lines),
                     'starts_spectre': 'NO', 'opens_socket': 'NO', 'writes_outside_ignored': 'NO'})
    hdr = ['gate', 'command', 'rc', 'verdict', 'expected_line', 'printed_lines_kept',
           'lines_dropped_for_local_path', 'printed', 'starts_spectre', 'opens_socket',
           'writes_outside_ignored']
    path = os.path.join(out_dir, 'gate_records.csv')
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=hdr, lineterminator='\n')
        w.writeheader()
        for r in rows:
            # the evidence tables are read by a plain split on commas
            w.writerow(dict((k, str(v).replace(',', ';')) for k, v in r.items()))
    good = len([r for r in rows if r['verdict'] == 'PASS'])
    print('GATE_RECORDS_TABLE %s' % path)
    print('GATE_RECORDS %d/%d PASS' % (good, len(rows)))
    for r in rows:
        print('GATE %s %s rc=%s' % (r['gate'], r['verdict'], r['rc']))
    print('D7B_GATE_RECORDS: %s' % ('PASS' if good == len(rows) else 'FAIL'))
    return 0 if good == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main())
