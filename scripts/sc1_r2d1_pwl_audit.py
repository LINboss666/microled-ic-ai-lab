#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D1-B: offline PWL envelope audit of the S2 deck generator.

    python scripts/sc1_r2d1_pwl_audit.py [--out CSV]

This audits the GENERATOR, not the circuit and not the general supply gate: no Spectre, no preflight
full, no Virtuoso. For every deck it recomputes the piecewise-linear waveforms at the union of all
declared breakpoints and checks the envelope rule the review states -- a signal may never leave the
rail of its own domain at any instant:

    normal deck :  0 <= en(t) <= vdd18(t)   and   0 <= core_ok33(t) <= vdd33(t)   for every t
    every deck  :  core_ok33(t) <= vdd33(t)   (the high-domain valid is never allowed over-drive)

Decks deliberately labelled EXTERNAL_DRIVE_FAULT (an ideal source continuing to drive a node whose
rail has fallen -- something an internal driver cannot do) must actually contain that over-drive:
if the audit finds none, the label is wrong, and that is also a failure. Both situations are recorded
in the index; neither is hidden.

Two mirrored bad stimuli are injected as synthetic cases to prove the audit bites:
  mirror_core_ok  the old seq_ok_early_release waveform pair (core_ok33 to 3.3 V at 100..150 ns while
                  vdd33 only rises at 500..700 ns) -- must be REJECTED,
  mirror_en       a deck declared normal whose en PWL tops out above the vdd18 waveform -- must be
                  REJECTED.

The two real negatives (vss mis-wired, vdd33 source absent) are the audited static gate's job and are
left to it; scripts/sc1_r2d_static_run.py re-proves they are still refused.

Everything reported here is STATIC/OFFLINE; a rail envelope that passes says nothing about whether
the circuit flips.
"""
from __future__ import print_function

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_s2_r2d_gen as G          # importing writes nothing and runs no suite

SUF = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'meg': 1e6, 'g': 1e9}
TOL = 1e-9


def time_value(tok):
    t = str(tok).strip().strip('"')
    for s in ('meg', 'f', 'p', 'n', 'u', 'm', 'k', 'g'):
        if t.endswith(s):
            return float(t[:-len(s)]) * SUF[s]
    return float(t)


def to_points(wave):
    """[(time-token, value)] -> [(seconds, value)]; a single pair is a flat waveform."""
    if len(wave) == 1:
        return [(0.0, wave[0][1]), (1e-6, wave[0][1])]
    return [(time_value(t), v) for (t, v) in wave]


def at(wave, t):
    """Linear interpolation of a PWL fold at time t (clamped at both ends)."""
    if t <= wave[0][0]:
        return wave[0][1]
    if t >= wave[-1][0]:
        return wave[-1][1]
    for i in range(1, len(wave)):
        if wave[i][0] >= t:
            t0, v0 = wave[i - 1]
            t1, v1 = wave[i]
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return wave[-1][1]


def joint_times(waves):
    ts = set()
    for w in waves:
        for (t, _v) in w:
            ts.add(t)
    return sorted(ts)


def check_env(name, env, allow_en_overdrive):
    """Return (verdict, rows) for one deck's envelope set."""
    named = dict((k, to_points(v)) for (k, v) in env)
    times = joint_times(list(named.values()))
    rows = []
    worst = {'en': None, 'core_ok33': None}
    for sig, rail, mandatory in (('en', 'vdd18', not allow_en_overdrive),
                                 ('core_ok33', 'vdd33', True)):
        if sig not in named:
            continue
        bad = []
        for t in times:
            v, r = at(named[sig], t), at(named[rail], t)
            if v < -TOL or v > r + TOL:
                bad.append((t, v, r))
        overdrive_present = bool(bad)
        if allow_en_overdrive and sig == 'en':
            verdict = 'EXPECTED_OVERDRIVE' if overdrive_present else 'LABEL_WRONG'
        elif bad:
            verdict = 'VIOLATION' if (mandatory or sig == 'core_ok33') else 'EXPECTED_OVERDRIVE'
        else:
            verdict = 'INSIDE'
        worst[sig] = bad
        rows.append([name, sig, rail, '0 <= %s(t) <= %s(t)' % (sig, rail), len(times),
                     ('%.6g' % max([v - r for (_t, v, r) in bad])) if bad else '0',
                     ('%.6g' % (bad[0][0] * 1e9)) if bad else 'none',
                     verdict,
                     'declared %s' % ('EXTERNAL_DRIVE_FAULT' if allow_en_overdrive else 'normal')])
    ok = all(not r for r in worst.values()) or (allow_en_overdrive and worst['en']
                                                and not worst['core_ok33'])
    if allow_en_overdrive and not worst['en']:
        ok = False                      # the label promised an over-drive that is not in the deck
    if worst['core_ok33']:
        ok = False                      # never legal, whatever the label says
    return ('PASS' if ok else 'FAIL'), rows


def main():
    argv = sys.argv[1:]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_csv = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(
        root, 'results', 'evidence', 'sc1_r2d1_pwl_audit.csv')

    rows = []
    fails = []
    for c in G.CASES:
        over = 'EXTERNAL_DRIVE_FAULT' in c.get('en_drive', '')
        verdict, sub = check_env(c['id'], G.envelopes(c), over)
        rows.extend(sub)
        if verdict != 'PASS':
            fails.append('%s: %s' % (c['id'], [r[6] for r in sub]))
        print('%-34s %s  %s' % (c['id'], verdict, ' | '.join('%s vs %s: %s' % (r[1], r[2], r[7])
                                                             for r in sub)))
    # the wiring negatives are not envelope questions: they stay the audited supply gate's job
    for c in G.NEGATIVES:
        rows.append([c['id'], 'wiring negative', 'vdd18/vdd33', 'not an envelope question', 0,
                     '0', 'none', 'DELEGATED_TO_STATIC_GATE',
                     'refused by tb_preflight.sh with PREFLIGHT_STATIC_PROBE=1, re-checked by '
                     'sc1_r2d_static_run.py'])
        print('%-34s DELEGATED_TO_STATIC_GATE' % c['id'])

    # ---------------------------------------------------------------- the mirrors
    mirror_ok = [('vdd18', [('0', 1.8)]), ('vdd33', to_points(G.pwl_points(
        '0 0 500n 0 700n 3.3 900n 3.3'))),
        ('en', to_points(G.pwl_points('0 0 400n 0 600n 1.8 900n 1.8'))),
        ('core_ok33', to_points(G.pwl_points('0 0 100n 0 150n 3.3 900n 3.3')))]
    v_ok, sub_ok = check_env('mirror_core_ok_old_early_release',
                             [(k, v) for (k, v) in mirror_ok], False)
    rows.append(sub_ok[0])
    print('%-34s %s  (the waveform the old seq_ok_early_release actually wrote)' % (
        'mirror_core_ok_old_early_release', 'REJECTED' if v_ok == 'FAIL' else 'MISSED'))
    if v_ok != 'FAIL':
        fails.append('the audit does not detect the bad core_ok33 stimulus it was written to catch')

    mirror_en = [('vdd18', to_points(G.pwl_points('0 1.8 300n 1.8 500n 0 800n 0'))),
                 ('vdd33', [('0', 3.3)]), ('en', to_points(G.pwl_points('0 1.8 300n 1.8 800n 1.8')))]
    v_en, sub_en = check_env('mirror_en_held_over_dead_rail', [(k, vv) for (k, vv) in mirror_en],
                             False)
    rows.append(sub_en[0])
    print('%-34s %s  (a normal deck holding en at 1.8 V over a dead vdd18)' % (
        'mirror_en_held_over_dead_rail', 'REJECTED' if v_en == 'FAIL' else 'MISSED'))
    if v_en != 'FAIL':
        fails.append('the audit does not detect an over-driven en declared normal')

    # the positive control: the same pair, once en is allowed to fall with the rail
    pos = [('vdd18', to_points(G.pwl_points('0 1.8 300n 1.8 500n 0 800n 0'))),
           ('vdd33', [('0', 3.3)]),
           ('en', to_points(G.pwl_points('0 1.8 300n 1.8 400n 0 800n 0')))]
    v_pos, sub_pos = check_env('positive_en_follows_rail', [(k, vv) for (k, vv) in pos], False)
    rows.append(sub_pos[0])
    print('%-34s %s' % ('positive_en_follows_rail', v_pos))
    if v_pos != 'PASS':
        fails.append('a legitimate en-follows-rail waveform was rejected')

    hdr = ('deck_id checked_signal rail envelope_against joint_breakpoints worst_over_V '
           'worst_over_time_ns verdict declared_kind').split(' ')
    with io.open(out_csv, 'w', encoding='utf-8', newline='\n') as f:
        f.write(G.csvline(hdr))
        for r in rows:
            f.write(G.csvline(r))
    print('PWL_AUDIT checks=%d failures=%d -> %s   (%s)'
          % (len(rows), len(fails), 'PASS' if not fails else 'FAIL', out_csv))
    for x in fails:
        print('  FAIL: %s' % x)
    print('PWL_AUDIT_SCOPE: generator stimulus only; the audited supply gate is unchanged, and the '
          'vss-miswire and absent-vdd33 negatives stay its responsibility.')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
