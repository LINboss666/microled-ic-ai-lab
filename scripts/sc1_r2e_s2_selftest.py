#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E S2: offline self test of the new entry. NO simulator is called.

    python scripts/sc1_r2e_s2_selftest.py [--out CSV]

Each case names the defect it guards against, and a case only passes when the ROW it should produce
is actually produced with the expected verdict and reader exit code. A case that "passes" because a
helper crashed, because a signal was missing, or because the window was widened is a failure, so the
refusals are asserted as explicitly as the passes.
"""
from __future__ import print_function

import io
import optparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc1_r2e_s2_tt as E

try:
    _text = unicode
except NameError:
    _text = str

EVIDENCE = os.path.join(os.path.dirname(HERE), 'results', 'evidence',
                        'sc1_r2e_s2_entry_selftest.csv')


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)

PSF_HEAD = u('HEADER\n"simulator" "spectre"\n"version" "selftest"\nSWEEP\n"time" "sweep"\n'
             u'TRACE\n%s\nVALUE\n')
PSF_END = u('END\n')


def psf(path, sigs, samples):
    """sigs: [(name, unit)] ; samples: [(t, v1, v2, ...)] -> a psfascii shaped like the runner's"""
    trace = '\n'.join(u('"%s" "%s"') % (n, un) for n, un in sigs)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(PSF_HEAD % trace)
        for row in samples:
            f.write(u('"time" %.17e\n') % row[0])
            for (n, _un), v in zip(sigs, row[1:]):
                f.write(u('"%s" %.17e\n') % (n, v))
        f.write(PSF_END)


class Capture(object):
    """stands in for E.Run and keeps every row the entry produced"""

    def __init__(self):
        self.rows = []
        self.log = []
        self.run_id = 'SELFTEST'

    def add(self, item, case, target, expected, actual, rc, verdict, note):
        self.rows.append([item, case, target, expected, actual, str(rc), verdict, note])


def find(rows, verdict_contains=None, item=None, target=None):
    out = []
    for r in rows:
        if item is not None and r[0] != item:
            continue
        if target is not None and target not in r[2]:
            continue
        if verdict_contains is not None and verdict_contains not in r[6]:
            continue
        out.append(r)
    return out


def main():
    op = optparse.OptionParser()
    op.add_option('--out')
    o, _ = op.parse_args()
    out_csv = o.out or EVIDENCE
    scratch = os.path.join(os.environ.get('TMP', '/tmp'), 'sc1_r2e_s2_selftest')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    results = []

    def check(name, ok, detail):
        results.append([name, 'PASS' if ok else 'FAIL', detail[:180]])
        print('%-46s %-6s %s' % (name, 'PASS' if ok else 'FAIL', detail[:120]))

    # ---------------------------------------------------------------- 1. no invented cases
    missing = [c for g in E.GROUPS for c in E.GROUPS[g]
               if E.find_case(c) is None and not c.endswith('_fine')]
    check('T1 every id exists in the audited table', not missing, 'missing: %s' % (missing or 'none'))

    # ---------------------------------------------------------------- 2. deck additions
    c0 = E.find_case('st_c0_en_high')
    txt0 = E.build_r2e_deck(c0)
    ok_temp = 'simopt options temp=27' in txt0 and '\noptions temp' not in txt0
    check('T2 temperature uses the accepted instantiation form', ok_temp,
          'simopt options temp=27 present, no bare options line')
    ok_src = ('save V18:i V33:i Ven:i' in txt0)
    check('T3 the direct source branches are saved', ok_src,
          [l for l in txt0.split('\n') if l.startswith('save V')][0] if ok_src else 'not found')
    c1 = E.find_case('st_c1_enhigh_okhigh')
    txt1 = E.build_r2e_deck(c1)
    check('T4 the core_ok33 source is saved only when the port exists',
          'Vok:i' in txt1 and 'Vok:i' not in txt0, 'c1 has Vok:i, c0 does not')

    # ---------------------------------------------------------------- 5. resolver on the real decks
    nl = E.netlist_text()
    devs0 = dict((p, n) for p, _m, n in E.resolve_devices(txt0, nl))
    check('T5 every deck has its devices resolved', len(devs0) == 10,
          '%d devices' % len(devs0))
    check('T6 core ports resolve to Xt.x / Xt.y, not Xt.Xcore.x',
          devs0.get('Xt.Xcore.mp_left') == ['Xt.x', 'Xt.y', 'vdd33', 'vdd33'],
          str(devs0.get('Xt.Xcore.mp_left')))
    check('T7 a genuinely internal node keeps its instance path',
          'Xt.Xcore.enbar' in devs0.get('Xt.Xcore.mn_drv', []) and
          'Xt.Xbuf.n1' in devs0.get('Xt.Xbuf.mp_i2', []),
          str(devs0.get('Xt.Xbuf.mp_i2')))
    saved = ' '.join(l for l in txt0.split('\n') if l.startswith('save'))
    need = [n for nets in devs0.values() for n in nets]
    uncovered = sorted(set(n for n in need if (' %s ' % n) not in (' %s ' % saved)))
    check('T8 the deck saves every terminal the stress rows need', not uncovered,
          'uncovered: %s' % (uncovered or 'none'))

    neg = E.find_case('neg_output_polarity_fault')
    txtn = E.build_r2e_deck(neg)
    devsn = dict((p, n) for p, _m, n in E.resolve_devices(txtn, nl))
    check('T9 the polarity deck is resolved under its own flat instance names',
          'Xcore.mp_drv' in devsn and 'Xbuf1.mp' in devsn and 'Xt.Xcore.mp_drv' not in devsn,
          'Xbuf1.mp -> %s' % devsn.get('Xbuf1.mp'))

    # ---------------------------------------------------------------- 4. audit catches the old spelling
    missing_names, added = E.save_path_audit(c0, txt0)
    check('T10 SAVE_PATH_AUDIT names the unreachable deck spellings',
          'Xt.Xcore.x' in missing_names and 'Xt.Xcore.y' in missing_names,
          'deck-only: %s' % missing_names)

    # ---------------------------------------------------------------- screening logic on synthetic data
    # a plateau that is low for the whole window except ONE high sample must not read as high
    sigs = [('gate33', 'V'), ('vdd33', 'V')]
    bad_samples = [(t / 1e9, 0.0, 3.3) for t in range(150, 200)]
    bad_samples = [(t * 1e-9, 0.02, 3.3) for t in range(150, 200, 1)]
    bad_samples[3] = (bad_samples[3][0], 3.29, 3.3)          # one high sample inside a low plateau
    p = os.path.join(scratch, 'plateau_one_high.psf')
    psf(p, sigs, bad_samples)
    cap = Capture()
    rows = E.measure_levels(cap, 'case', 'S2_FUNCTIONAL_TT', p, '150n', '199n',
                            [('gate33', 'high')])
    r = find(cap.rows, item='S2_FUNCTIONAL_TT')
    check('T11 one high sample cannot certify a HIGH window',
          len(r) == 1 and r[0][6] == 'FAIL', r[0][5] if r else 'no row')

    good = [(t * 1e-9, 3.28, 3.3) for t in range(150, 200, 1)]
    p2 = os.path.join(scratch, 'plateau_good.psf')
    psf(p2, sigs, good)
    cap = Capture()
    E.measure_levels(cap, 'case', 'S2_FUNCTIONAL_TT', p2, '150n', '199n', [('gate33', 'high')])
    r = find(cap.rows, item='S2_FUNCTIONAL_TT')
    check('T12 a real high plateau passes', len(r) == 1 and r[0][6] == 'PASS',
          r[0][5] if r else 'no row')

    # a save the build threw away must fail closed, never read as 0 V
    cap = Capture()
    E.measure_levels(cap, 'case', 'S2_FUNCTIONAL_TT', p2, '150n', '199n',
                     [('Xt.Xcore.x', 'high')])
    r = find(cap.rows, item='S2_FUNCTIONAL_TT')
    check('T13 a missing signal is BLOCKED with its reader exit code, not 0 V',
          len(r) == 1 and r[0][6] == 'BLOCKED' and r[0][5] == '3', str(r))

    # ---------------------------------------------------------------- rail current sign
    sigs = [('V18:i', 'A'), ('V33:i', 'A'), ('Ven:i', 'A')]
    cur = [(t * 1e-9, -1.8e-4, -3.3e-4, 0.0) for t in range(150, 200, 1)]
    p3 = os.path.join(scratch, 'currents.psf')
    psf(p3, sigs, cur)
    cap = Capture()
    E.measure_rails(cap, 'case', p3, '150n', '199n', False)
    rows = find(cap.rows, item='S2_RAIL_CURRENT')
    v18 = [r for r in rows if 'V18' in r[2]]
    check('T14 a delivering rail is reported as a POSITIVE injected current',
          len(v18) == 1 and 'injected 0.00018 .. 0.00018' in v18[0][4]
          and 'min=-0.00018' in v18[0][4], v18[0][4] if v18 else 'no row')
    v33 = [r for r in rows if 'V33' in r[2]]
    check('T15 the 3.3 V branch is read in the same run',
          len(v33) == 1 and 'injected 0.00033 .. 0.00033' in v33[0][4],
          v33[0][4] if v33 else 'no row')

    # ---------------------------------------------------------------- stress peaks from nodes
    sigs = [('Xt.x', 'V'), ('Xt.y', 'V'), ('en', 'V'), ('vss', 'V'), ('vdd33', 'V'),
            ('Xt.Xcore.enbar', 'V'), ('vdd18', 'V'), ('gate33', 'V'), ('Xt.Xbuf.n1', 'V'),
            ('Xt.Xcore.mn_left:vgs', 'V'), ('Xt.Xcore.mn_left:vds', 'V'),
            ('Xt.Xcore.mn_left:vbs', 'V')]
    samples = []
    for t in range(150, 200, 1):
        x = 0.0 if t < 170 else 3.3
        samples.append((t * 1e-9, x, 3.3 if t < 170 else 0.0, 1.8 if t < 170 else 0.0, 0.0, 3.3,
                        1.8 if t < 170 else 0.0, 1.8, 3.3, x,
                        1.8 if t < 170 else 0.0,      # model vgs tracks gate-source
                        x - 0.0, 0.0))
    p4 = os.path.join(scratch, 'stress.psf')
    psf(p4, sigs, samples)
    cap = Capture()
    E.measure_stress(cap, 'st_c0_en_high', txt0, p4, '150n', '199n')
    rows = find(cap.rows, item='DEVICE_STRESS_PEAKS', target='Xt.Xcore.mn_left')
    check('T16 VGS is formed per sample from the saved nodes',
          len(rows) == 1 and 'VGS=0..1.8' in rows[0][4], rows[0][4] if rows else 'no row')
    check('T17 the stress rows are MEASURED, never an SOA signoff',
          len(rows) == 1 and rows[0][6] == 'MEASURED' and 'SOA' in rows[0][3],
          'verdict=%s expected=%s' % (rows[0][6] if rows else 'none',
                                      rows[0][3][:40] if rows else ''))
    xr = find(cap.rows, item='STRESS_CROSSCHECK')
    check('T18 the model parameter and the node difference agree',
          len(xr) >= 1 and xr[-1][6] == 'PASS', '%s | %s' % (xr[-1][5], xr[-1][6]) if xr else 'no row')

    # a device whose source node was never saved must not produce a number
    p5 = os.path.join(scratch, 'stress_missing.psf')
    psf(p5, [('Xt.x', 'V'), ('en', 'V')], [(t * 1e-9, 0.0, 1.8) for t in range(150, 200)])
    cap = Capture()
    E.measure_stress(cap, 'case', txt0, p5, '150n', '199n')
    rows = find(cap.rows, item='DEVICE_STRESS_PEAKS')
    na = [r for r in rows if r[6] == 'NOT_AVAILABLE']
    part = [r for r in rows if r[6] == 'PARTIAL']
    check('T19 unreadable terminals are named, never zeroed',
          len(rows) == 10 and na and all('terminals not saved' in r[7] for r in part) and
          all(r[6] in ('MEASURED', 'PARTIAL', 'NOT_AVAILABLE') for r in rows) and
          not any('..0' in r[4] and 'VGS=0.0..' in r[4] for r in na),
          '%d rows, %d NOT_AVAILABLE, %d PARTIAL' % (len(rows), len(na), len(part)))

    # ---------------------------------------------------------------- refusal logic for the negative
    # a stepped ramp, the way the decks sample it (maxstep 0.2 n): a single-sample jump is not an edge
    sigs = [('en', 'V'), ('gate33', 'V')]
    wave = []

    def ramp(t, t0, span, lo, hi):
        if t < t0:
            return lo
        if t >= t0 + span:
            return hi
        return lo + (hi - lo) * (t - t0) / span

    for i in range(0, 400):
        t = i * 1e-9
        en = ramp(t, 100e-9, 4e-9, 0.0, 1.8)
        gate = ramp(t, 106e-9, 6e-9, 0.0, 3.3)      # WRONG polarity: it rises with en
        wave.append((t, en, gate))
    p6 = os.path.join(scratch, 'polarity.psf')
    psf(p6, sigs, wave)
    cap = Capture()
    _a, refused = E.measure_delay(cap, 'neg', p6, '100n', '399n', 'rise', 'fall', False)
    rows = find(cap.rows, item='S2_DELAY')
    check('T20 the C0 fall-criterion refuses the wrong-polarity waveform',
          refused and len(rows) == 1 and rows[0][6] == 'EXPECTED_REFUSAL',
          rows[0][4] if rows else 'no row')
    cap = Capture()
    E.measure_delay(cap, 'neg', p6, '100n', '399n', 'rise', 'rise', True)
    rows = find(cap.rows, item='S2_DELAY')
    check('T21 the opposite pairing does answer, so the waveform really switched',
          len(rows) == 1 and rows[0][6] == 'PASS', rows[0][4] if rows else 'no row')
    cap = Capture()
    E.measure_delay(cap, 'neg', p6, '100n', '399n', 'rise', 'fall', True)
    rows = find(cap.rows, item='S2_DELAY')
    check('T22 wanting an answer where there is none is FAIL, not PASS',
          len(rows) == 1 and rows[0][6] == 'FAIL', rows[0][4] if rows else 'no row')

    # an unreadable data file must not be scored as a circuit result
    cap = Capture()
    E.measure_delay(cap, 'neg', os.path.join(scratch, 'nope.psf'), '100n', '399n',
                    'rise', 'fall', True)
    rows = find(cap.rows, item='S2_DELAY')
    check('T23 a missing data file is BLOCKED with its reader exit code',
          len(rows) == 1 and rows[0][6] == 'BLOCKED' and rows[0][4].startswith('NO_DATA'),
          '%s rc=%s' % (rows[0][4], rows[0][5]) if rows else 'no row')

    # ---------------------------------------------------------------- which edges the stimulus can make
    e_fall, why_f = E.defined_output_edges(E.find_case('load_c1_5pF'), '100n', '600n')
    check('T24 a stimulus that only rises defines only a FALLING output edge',
          e_fall == set(['fall']), '%s (%s)' % (sorted(e_fall), why_f))
    e_both, why_b = E.defined_output_edges(E.find_case('dyn_c0_rise'), '100n', '300n')
    check('T25 a stimulus that rises and falls defines both edges',
          e_both == set(['fall', 'rise']), '%s (%s)' % (sorted(e_both), why_b))
    e_none, why_n = E.defined_output_edges(E.find_case('st_c0_en_high'), '150n', '200n')
    check('T26 a dc stimulus defines no edge at all', not e_none, why_n)

    hdr = ['case', 'verdict', 'detail']
    d = os.path.dirname(out_csv)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(out_csv, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(','.join(u('"%s"') % h for h in hdr)) + u('\n'))
        for r in results:
            f.write(u(','.join(u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in r)) + u('\n'))
    fails = [r for r in results if r[1] != 'PASS']
    print('S2_ENTRY_SELFTEST cases=%d failures=%d csv=%s' % (len(results), len(fails), out_csv))
    for r in fails:
        print('   FAIL %s: %s' % (r[0], r[2][:120]))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
