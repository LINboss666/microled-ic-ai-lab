#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D: run the STATIC preflight gate over the generated S2 deck matrix.

    python scripts/sc1_r2d_static_run.py --index FILE --decks DIR --preflight FILE --out CSV

No simulator is involved and none can be reached from here: tb_preflight.sh is called with
PREFLIGHT_STATIC_PROBE=1, which stops after the structural supply/rail gates, exits with 7 and prints
CIRCUIT_VERDICT: NOT_RUN. For a deck the index declares refused, the run must instead see exit 1 with
PREFLIGHT_STAGE=supply_contract and a non-empty reason. Every row additionally asserts
simulator_called=no, so an accidental step into phase 2 would show up as a failure rather than as a
quiet acceptance. Any non-zero exit code is not treated as a pass: rc, stage and reason are all
checked against what the index promised.
"""
from __future__ import print_function
import csv, io, os, subprocess, sys

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


def csvline(vals):
    return u(','.join([u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in vals])) + u('\n')


HEADERS = ['deck_id', 'cli_form', 'supply_contract', 'expected_rc', 'actual_rc', 'actual_stage',
           'reason_or_verdict_token', 'simulator_called', 'verdict', 'deck_log']


def field(text, prefix):
    for ln in text.split('\n'):
        if ln.startswith(prefix):
            return ln[len(prefix):].strip()
    return ''


def main():
    a = sys.argv[1:]

    def arg(name):
        return a[a.index(name) + 1] if name in a else None
    index, decks, pf, out = arg('--index'), arg('--decks'), arg('--preflight'), arg('--out')
    if not all([index, decks, pf, out]):
        print('USAGE: sc1_r2d_static_run.py --index F --decks DIR --preflight F --out CSV')
        return 2
    with io.open(index, 'r', encoding='utf-8') as f:
        rows = list(csv.reader([l for l in f]))
    if not rows:
        print('HARNESS_ERROR: empty index')
        return 8
    hdr, data = rows[0], rows[1:]
    i_exp = hdr.index('static_expectation')
    i_rail = hdr.index('rail_contract_at_op_V')
    i_file = hdr.index('file')

    env = dict(os.environ)
    env['PREFLIGHT_STATIC_PROBE'] = '1'
    fails = 0
    results = []
    for r in data:
        did, deck = r[0], os.path.join(decks, r[i_file])
        contract = r[i_rail]
        expectation = r[i_exp]
        refuses = expectation.startswith('refused')
        want_rc = '1' if refuses else '7'
        p = subprocess.Popen(['bash', pf, deck, '1.8', did, contract], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw = p.communicate()[0]
        text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
        rc = str(p.returncode)
        stage = field(text, 'PREFLIGHT_STAGE=')
        reason = field(text, 'PREFLIGHT_REJECT:') or field(text, 'PREFLIGHT_HARNESS_ERROR:') \
            or field(text, 'CIRCUIT_VERDICT:')
        sim = 'yes' if 'spectre_rc=' in text else 'no'
        ok = (rc == want_rc) and sim == 'no'
        why = []
        if rc != want_rc:
            why.append('rc=%s want %s' % (rc, want_rc))
        if refuses:
            if stage != 'supply_contract':
                ok = False
                why.append('stage=%s want supply_contract' % (stage or 'none'))
            if not field(text, 'PREFLIGHT_REJECT:'):
                ok = False
                why.append('no rejection reason printed')
        else:
            if 'NOT_RUN' not in text:
                ok = False
                why.append('static probe did not print CIRCUIT_VERDICT: NOT_RUN')
            if 'TESTBENCH_PREFLIGHT: PASS' in text:
                ok = False
                why.append('static probe must never print a circuit PASS')
        if sim != 'no':
            ok = False
            why.append('simulator was reached')
        if not ok:
            fails += 1
        results.append([did, 'contract', contract, want_rc, rc, stage or 'none',
                        reason[:200] or ('' if refuses else 'NOT_RUN'), sim,
                        'PASS' if ok else 'FAIL', ';'.join(why)])
        print('%-28s exp=%s rc=%-2s stage=%-15s sim=%-3s %s %s'
              % (did, want_rc, rc, stage or 'none', sim, 'PASS' if ok else 'FAIL',
                 (';'.join(why) or reason)[:74]))
    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(HEADERS))
        for row in results:
            f.write(csvline(row))
    print('R2D_STATIC_TOTAL=%d R2D_STATIC_FAILS=%d  (all rows simulator_called=no required)'
          % (len(results), fails))
    print('R2D_STATIC_CSV=%s' % out)
    if not results:
        print('HARNESS_ERROR: no decks in index')
        return 8
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
