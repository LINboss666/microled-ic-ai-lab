#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D1-B: measure whether a supply-branch iprobe can survive the audited supply gate.

    python scripts/sc1_r2d1_iprobe_probe.py --scratch DIR --preflight FILE --out CSV

Why this exists instead of a sentence in the report: the review asks for real source-current saves, and
the obvious way to get one is a zero-burden `iprobe` in series with the rail. That syntax IS verified in
this project (`Ip1 (vsw data_out) iprobe` + `save Ip1:i`, reports/data_driver_candidate_E.md), but it was
only ever verified in a LOAD branch. The audited static gate requires each declared supply port net to
be driven by an independent source referenced to node 0, and a series element puts the probe between the
source and that net.

So this is measured with PREFLIGHT_STATIC_PROBE=1 only -- no simulator, no preflight full. Whatever the
answer, the committed checker is not edited: if the arrangement is refused, the decks keep their directly
driven rails and the rail current is derived from the per-device `save <inst>:1` currents instead.
"""
from __future__ import print_function

import io
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_s2_r2d_gen as G

BASE = dict(id='probe_iprobe_series', variant='c1', rails=(1.8, 3.3), en=0.0, ok=3.3, load=1.0,
            stop='200n', maxstep='1n', windows=[], expect='n/a (syntax probe)',
            why='probe only')


def deck_with_probes():
    txt = G.build(BASE)
    # break each rail between its source and the DUT net, with a zero-volt probe in the gap
    txt = txt.replace('V18 (vdd18 0) vsource dc=1.8\n',
                      'V18 (v18src 0) vsource dc=1.8\nIp18 (v18src vdd18) iprobe\n')
    txt = txt.replace('V33 (vdd33 0) vsource dc=3.3\n',
                      'V33 (v33src 0) vsource dc=3.3\nIp33 (v33src vdd33) iprobe\n')
    txt += 'save Ip18:i Ip33:i\n'
    return txt


def main():
    a = sys.argv[1:]

    def arg(n):
        return a[a.index(n) + 1] if n in a else None
    scratch, pf, out = arg('--scratch'), arg('--preflight'), arg('--out')
    if not all([scratch, pf, out]):
        print('USAGE: sc1_r2d1_iprobe_probe.py --scratch DIR --preflight FILE --out CSV')
        return 2
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    # the decks include the cell by relative name, so the cell has to sit beside this deck too --
    # otherwise the gate refuses it for a missing port list and says nothing about the probe
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'spectre', G.NETLIST_RELPATH), 'rb') as src:
        with open(os.path.join(scratch, G.NETLIST_RELPATH), 'wb') as dst:
            dst.write(src.read())
    deck = os.path.abspath(os.path.join(scratch, 'probe_iprobe_series.scs'))
    with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
        f.write(G.u(deck_with_probes()))
    env = dict(os.environ)
    env['PREFLIGHT_STATIC_PROBE'] = '1'
    p = subprocess.Popen(['bash', pf, deck, '1.8', 'iprobe_series',
                          'vdd18=1.8 vdd33=3.3 vss=0'], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    rc = p.returncode

    def field(prefix):
        for ln in text.split('\n'):
            if ln.startswith(prefix):
                return ln[len(prefix):].strip()
        return ''

    stage = field('PREFLIGHT_STAGE=')
    reason = (field('PREFLIGHT_REJECT:') or field('PREFLIGHT_HARNESS_ERROR:')
              or field('CIRCUIT_VERDICT:'))
    fails = [ln.strip() for ln in text.split('\n') if ln.strip().startswith('SUPPLY_FAIL')]
    sim = 'yes' if 'spectre_rc=' in text else 'no'
    verdict = ('REFUSED_BY_STATIC_GATE' if rc != 7 else 'ACCEPTED_BY_STATIC_GATE')
    rows = [[rc, stage, verdict, sim, len(fails), reason[:220],
             'deck keeps a series iprobe in each rail branch; syntax from '
             'spectre/current_probe_syntax.scs, contract vdd18=1.8 vdd33=3.3 vss=0']]
    hdr = ['actual_rc', 'actual_stage', 'verdict', 'simulator_called', 'supply_fail_lines',
           'first_reason', 'note']
    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(G.csvline(hdr))
        for r in rows:
            f.write(G.csvline(r))
    print('IPROBE_SERIES_RAIL rc=%s stage=%s verdict=%s sim=%s supply_fail_lines=%d'
          % (rc, stage or 'none', verdict, sim, len(fails)))
    for ln in fails[:4]:
        print('  %s' % ln)
    print('CONSEQUENCE: %s' % (
        'the S2 decks must NOT break a rail with a probe; rail current comes from the per-device '
        'save <inst>:1 currents (verified form), and the checker is left unchanged'
        if verdict == 'REFUSED_BY_STATIC_GATE' else
        'a series iprobe survives the static gate; a future run still has to prove it at the '
        'operating point before any deck uses it'))
    print('IPROBE_PROBE_CSV=%s   (PREFLIGHT_STATIC_PROBE=1 only, no simulator)' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
