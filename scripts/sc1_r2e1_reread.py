#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E1: re-read what R2E already measured. NO SIMULATOR IS CALLED.

    python scripts/sc1_r2e1_reread.py --what stress   # C1: strict re-read of the stress rows
    python scripts/sc1_r2e1_reread.py --what samples  # C2: sampled waveform excerpts, no resampling

Both modes open the SAME files the R2E runs produced, under
`cadence_work/sc1_sim/r2e_s2_<group>/`, and go through the audited parser
(scripts/sc1_read_psf.parse) plus the strict difference tool (scripts/sc1_r2e_vtx.py). Nothing is
re-simulated, nothing is interpolated or resampled, and no old CSV is rewritten: if a re-read
contradicts the original, the original row stays and the new row says so.

Why the file is found this way and not "the newest raw in the tree": each case's deck path is known,
and scripts/run_spectre.sh always writes <deck dir>/sim/<deck stem>.raw/, so the candidate is that
directory's psfascii that carries both a TRACE and a VALUE section -- the same rule the runner itself
uses, with the directory fixed per case so a neighbouring run cannot be picked up.
"""
from __future__ import print_function

import hashlib
import io
import math
import optparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sc1_read_psf as RD                    # audited parser
import sc1_r2e_s2_tt as S2                   # for the frozen-cell connectivity resolver only
import csv as _csv

try:
    _text = unicode
except NameError:
    _text = str

VTX = os.path.join(HERE, 'sc1_r2e_vtx.py')
EVID = os.path.join(PROJ, 'results', 'evidence')
GROUPS = ('static', 'dynamic', 'dynamic_repeat3', 'load', 'negative')
QUANT = 6                      # the audited reader prints %.6g; comparison uses that display band


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def rows_of(path):
    if not os.path.isfile(path):
        return []
    return list(_csv.reader([l for l in io.open(path, encoding='utf-8', newline='')]))[1:]


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def datafile_for(case):
    """this case's own psfascii, or None -- never a neighbour's or an older directory's file"""
    for g in GROUPS:
        base = os.path.join(PROJ, 'cadence_work', 'sc1_sim', 'r2e_s2_' + g)
        deck = os.path.join(base, case + '.scs')
        if not os.path.isfile(deck):
            continue
        raw = os.path.join(base, 'sim', case + '.raw')
        if not os.path.isdir(raw):
            continue
        cands = []
        for name in os.listdir(raw):
            p = os.path.join(raw, name)
            if not os.path.isfile(p) or name == 'logFile':
                continue
            txt = u(io.open(p, encoding='utf-8', errors='replace').read())
            if re.search(r'^TRACE', txt, re.M) and re.search(r'^VALUE', txt, re.M):
                cands.append((os.path.getsize(p), p))
        if cands:
            return deck, max(cands)[1]
    return None, None


def band(v):
    """half of one step of the printed 6-significant-digit display, the same rule R2D2 used"""
    v = abs(float(v))
    if v == 0.0:
        return 0.0
    return 0.5 * 10 ** (math.floor(math.log10(v)) - (QUANT - 1))


def strict_diff(path, a, b, mode, t0=None, t1=None):
    """one call to the strict tool; returns (rc, value, time, raw_text)"""
    cmd = [sys.executable, VTX, '--data', path, '--a', a, '--b', b, '--mode', mode, '--quiet']
    if t0:
        cmd += ['--t0', t0]
    if t1:
        cmd += ['--t1', t1]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = u(p.communicate()[0]).strip()
    parts = out.split('\t')
    try:
        val = float(parts[0])
    except (ValueError, IndexError):
        val = None
    try:
        tsec = float(parts[1])
    except (ValueError, IndexError):
        tsec = None
    return p.returncode, val, tsec, out


def ns(seconds):
    return '%.4g ns' % (float(seconds) * 1e9)


# ------------------------------------------------------------------ C1
STRESS_ROWS = ('DEVICE_STRESS_PEAKS', 'STRESS_CROSSCHECK')
QUANT_PAIRS = {'VGS': (1, 2), 'VGD': (1, 3), 'VDS': (0, 2), 'VGB': (1, 4)}


def do_stress():
    rows = []
    src = {'static': 'sc1_r2e_s2_static.csv', 'load': 'sc1_r2e_s2_load.csv'}
    for group, fname in src.items():
        for r in rows_of(os.path.join(EVID, fname)):
            if len(r) < 9 or r[1] not in STRESS_ROWS:
                continue
            run_id, item, case, target = r[0], r[1], r[2], r[3]
            deck, data = datafile_for(case)
            if not data:
                rows.append([run_id, case, item, target, '-', '-', '-', '-', '-', '-',
                             'BLOCKED', 'the raw of THIS case is not on disk any more; the original '
                             'row stands and is not re-simulated'])
                continue
            net = S2.netlist_text()
            deck_txt = u(io.open(deck, encoding='utf-8', errors='replace').read())
            devs = dict((p, n) for p, _m, n in S2.resolve_devices(deck_txt, net))
            m = re.match(r'^(\S+?) \((\S+)\)$', target)
            if item == 'STRESS_CROSSCHECK':
                dev = S2.XCHECK_DEVICE
                pairs = [('VGS', None)]
                orig = r[5]
            elif m:
                dev = m.group(1)
                pairs = [(q, None) for q in ('VGS', 'VGD', 'VDS', 'VGB')]
                orig = r[5]
            else:
                continue
            if dev not in devs:
                rows.append([run_id, case, item, target, sha(data)[:16], '-', '-', '-', '-', '-',
                             'BLOCKED', 'the device is not resolvable in this deck'])
                continue
            d, g, s, b = devs[dev]
            # the SAME window the original row was judged in: the R2E entry used the case's first
            # declared window, and a whole-file extreme of the same node pair is a different question
            case_def = S2.find_case(re.sub(r'_fine$', '', case))
            w = (case_def.get('windows') or [None])[0]
            t0 = '%.9g' % w[1] if w else None
            t1 = '%.9g' % w[2] if w else None
            try:
                _gr, _ax = RD.parse(data)
                n_in = len([q for q in _gr if (t0 is None or q[_ax] >= float(t0))
                            and (t1 is None or q[_ax] <= float(t1))])
            except Exception:
                n_in = '?'
            win_txt = '%s..%s s (%d groups)' % (t0, t1, n_in) if t0 else 'whole file'
            for q, _x in pairs:
                a, bb = {'VGS': (g, s), 'VGD': (g, d), 'VDS': (d, s), 'VGB': (g, b)}[q]
                win = re.findall(r'%s=(-?[0-9.eE+-]+)\.\.(-?[0-9.eE+-]+)' % q, orig)
                old_lo = old_hi = None
                if win:
                    old_lo, old_hi = float(win[0][0]), float(win[0][1])
                rcx, vx, tx, rawx = strict_diff(data, a, bb, 'max', t0, t1)
                rcn, vn, tn, rawn = strict_diff(data, a, bb, 'min', t0, t1)
                if rcx or rcn or vx is None or vn is None:
                    rows.append([run_id, case, item, '%s %s' % (target, q), sha(data)[:16],
                                 '%s - %s' % (a, bb), win_txt, '-', '%s / %s' % (old_lo, old_hi),
                                 '-', 'rc=%s/%s %s' % (rcx, rcn, rawx[:40]), 'BLOCKED',
                                 'strict parsing refuses this data; the original value is kept, not '
                                 'silently replaced'])
                    continue
                if item == 'STRESS_CROSSCHECK':
                    # the original row states a comparison in prose, not a value pair, so it is
                    # RE-PERFORMED under strict parsing rather than diffed against a sentence: the
                    # device's own exported terminal voltage against the node difference
                    mv = mh = None
                    sig = '%s:vgs' % dev
                    try:
                        grp, ax = RD.parse(data)
                        vals = [g[sig] for g in grp if sig in g
                                and (t0 is None or float(t0) <= g[ax] <= float(t1))]
                        if vals:
                            mv, mh = min(vals), max(vals)
                    except Exception:
                        pass
                    if mv is None:
                        rows.append([run_id, case, item, '%s %s' % (target, q), sha(data)[:16],
                                     '%s vs %s - %s' % (sig, a, bb), win_txt,
                                     'absent from this file', '%.6g / %.6g' % (vn, vx), '-',
                                     'the model parameter could not be read', 'BLOCKED',
                                     'the original row is kept unchanged'])
                        continue
                    agree = max(abs(mv - vn), abs(mh - vx))
                    rows.append([run_id, case, item, '%s %s' % (target, q), sha(data)[:16],
                                 '%s vs %s - %s' % (sig, a, bb), win_txt,
                                 'model %.6g / %.6g' % (mv, mh), '%.6g / %.6g' % (vn, vx),
                                 'worst model-vs-node diff %.3g V' % agree,
                                 'max rc=0 at %s, min rc=0 at %s' % (ns(tx), ns(tn)),
                                 'PASS' if agree <= 1e-3 else 'FAIL',
                                 'cross-check re-performed under strict parsing; 1 mV is the original '
                                 "row's stated agreement rule. MEASURED, SOA stays NO"])
                    continue
                same = (abs(vx - old_hi) <= band(old_hi) + band(vx) and
                        abs(vn - old_lo) <= band(old_lo) + band(vn)) if win else None
                rows.append([run_id, case, item, '%s %s' % (target, q), sha(data)[:16],
                             '%s - %s' % (a, bb), win_txt,
                             '%.6g / %.6g' % (old_lo, old_hi) if win else 'no original pair',
                             '%.6g / %.6g' % (vn, vx),
                             ('%.6g / %.6g worst diff %.3g V'
                              % (vx - old_hi, vn - old_lo,
                                 max(abs(vx - old_hi), abs(vn - old_lo)))) if win
                             else 'not comparable to a prose row',
                             'max rc=0 at %s, min rc=0 at %s' % (ns(tx), ns(tn)),
                             'PASS' if same else ('PARTIAL' if same is None else 'FAIL'),
                             'compared at the %d-significant-digit display band of the original '
                             'output (+/-%.3g V at 3.3 V); MEASURED, SOA stays NO' % (QUANT, band(3.3))])
    return rows


# ------------------------------------------------------------------ C2
def samples_of(data):
    groups, axis = RD.parse(data)
    return groups, axis


def first_crossing(groups, axis, sig, thr, rising, lo=None, hi=None):
    for i in range(1, len(groups)):
        t0, t1 = groups[i - 1][axis], groups[i][axis]
        if lo is not None and (t0 < lo or t1 < lo):
            continue
        if hi is not None and t1 > hi:
            break
        v0, v1 = groups[i - 1].get(sig), groups[i].get(sig)
        if v0 is None or v1 is None:
            continue
        if rising and v0 < thr <= v1:
            return i
        if (not rising) and v0 >= thr > v1:
            return i
    return None


def emit_segment(rows, run_id, case, data, label, sigs, idx, span=2, extra=''):
    """the real samples around index idx, in file order, nothing interpolated"""
    groups, axis = samples_of(data)
    lo = max(0, idx - span)
    hi = min(len(groups), idx + span + 1)
    for i in range(lo, hi):
        g = groups[i]
        vals = ' '.join('%s=%s' % (s, '%.6g' % g[s]) for s in sigs if s in g)
        rows.append([run_id, case, label, sha(data)[:16], str(i), '%.9g' % g[axis],
                     ns(g[axis]), vals, 'group %d..%d of the original sampling' % (lo, hi - 1),
                     extra, 'MEASURED_SAMPLE'])


def do_samples():
    rows = []
    PLAN = [
        # (case, signals to print, [(sig, thr, rising, window_lo, window_hi, what)], note)
        ('dyn_c0_rise', ['en', 'gate33', 'Xt.x', 'Xt.y'],
         [('en', 0.9, True, None, None, 'input 50% rise'),
          ('gate33', 0.33, False, None, None, 'output 90->10 fall band top'),
          ('gate33', 1.65, False, None, None, 'output 50% fall'),
          ('gate33', 2.97, False, None, None, 'output 10% of the fall')], '1 pF load'),
        ('dyn_c0_fall', ['en', 'gate33', 'Xt.x', 'Xt.y'],
         [('en', 0.9, False, None, None, 'input 50% fall'),
          ('gate33', 1.65, True, None, None, 'output 50% rise')], '1 pF load'),
        ('dyn_c1_rise', ['en', 'core_ok33', 'gate33', 'Xt.x', 'Xt.y', 'Xt.Xnand.ns_m'],
         [('en', 0.9, True, None, None, 'input 50% rise'),
          ('gate33', 1.65, False, None, None, 'output 50% fall')], 'guarded C1, 1 pF'),
        ('dyn_c1_fall', ['en', 'core_ok33', 'gate33', 'Xt.y'],
         [('en', 0.9, False, None, None, 'input 50% fall'),
          ('gate33', 1.65, True, None, None, 'output 50% rise')], 'guarded C1, 1 pF'),
        ('load_c1_5pF', ['en', 'core_ok33', 'gate33'],
         [('gate33', 1.65, False, None, None, 'output 50% fall, 5 pF coarse step')],
         'the heaviest prepared load'),
        ('load_c1_5pF_fine', ['en', 'core_ok33', 'gate33'],
         [('gate33', 1.65, False, None, None, 'output 50% fall, same case at maxstep 0.05 ns')],
         'step-size re-check of the same deck'),
        ('neg_output_polarity_fault', ['en', 'gate33', 'x', 'y'],
         [('en', 0.9, True, None, None, 'input 50% rise'),
          ('gate33', 1.65, True, None, None, 'the WRONG polarity answers with a RISE')],
         'normal C0 expects a fall here, so it refused'),
    ]
    for case, sigs, crossings, note in PLAN:
        deck, data = datafile_for(case)
        if not data:
            rows.append([case, case, 'segment', '-', '-', '-', '-', '-', '-',
                         'BLOCKED: this case raw is no longer on disk (%s)' % note, 'BLOCKED'])
            continue
        run_id = sha(deck)[:8]
        groups, axis = samples_of(data)
        for sig, thr, rising, lo, hi, what in crossings:
            i = first_crossing(groups, axis, sig, thr, rising,
                               RD.qty(lo) if lo else None, RD.qty(hi) if hi else None)
            if i is None:
                rows.append([run_id, case, what, sha(data)[:16], '-', '-', '-',
                             'sig=%s thr=%s' % (sig, thr), '-',
                             'NO_CROSSING in this file: the original row is kept, nothing is '
                             'invented', 'NO_CROSSING'])
                continue
            emit_segment(rows, run_id, case, data, '%s (%s)' % (what, note), sigs, i, 2,
                         'crossing at group %d: %s crosses %.3g' % (i, sig, thr))
    # repeat3: the 12 attributed pairs, each with its owning input edge and the next input boundary
    for case in ('dyn_c0_repeat3', 'dyn_c1_repeat3'):
        deck, data = datafile_for(case)
        if not data:
            continue
        run_id = sha(deck)[:8]
        groups, axis = samples_of(data)
        for r in rows_of(os.path.join(EVID, 'sc1_r2e_s2_dynamic_repeat3.csv')):
            if len(r) < 9 or r[1] != 'S2_DELAY' or r[2] != case:
                continue
            m = re.search(r't_in=(\S+) t_out=(\S+)', r[5])
            if not m:
                continue
            t_in, t_out = float(m.group(1)), float(m.group(2))
            # the next input crossing of EITHER direction after this event's input edge: that is the
            # boundary past which the audited tool refuses to credit an answer
            edge = None
            for i in range(1, len(groups)):
                a, b = groups[i - 1]['en'], groups[i]['en']
                if groups[i][axis] <= t_in:
                    continue
                if (a < 0.9 <= b) or (a >= 0.9 > b):
                    edge = groups[i][axis]
                    break
            for sig, thr, rising, tref, role in (('en', 0.9, None, t_in, 'owning input 50% edge'),
                                                 ('gate33', 1.65, None, t_out, 'answered output '
                                                  '50% edge')):
                idx = min(range(len(groups)), key=lambda k: abs(groups[k][axis] - tref))
                emit_segment(rows, run_id, case, data, role, [sig, 'gate33', 'en'], idx, 2,
                             't_ref=%.9g s; next input 50%% boundary=%s'
                             % (tref, ('%.9g' % edge) if edge else 'none'))
    # one per-device stress extreme with its four node voltages at that same sample
    deck, data = datafile_for('st_c1_enhigh_okhigh')
    if data:
        groups, axis = samples_of(data)
        dev = S2.XCHECK_DEVICE
        nets = dict((p, n) for p, _m, n in S2.resolve_devices(
            u(io.open(deck, encoding='utf-8', errors='replace').read()),
            S2.netlist_text())).get(dev)
        if nets:
            d, g, s, b = nets
            best = max(groups, key=lambda q: abs(q.get(g, 0.0) - q.get(s, 0.0)))
            i = groups.index(best)
            emit_segment(rows, sha(deck)[:8], 'st_c1_enhigh_okhigh', data,
                         '%s VGS extreme, same-sample D/G/S/B' % dev, [d, g, s, b, 'gate33'], i, 1,
                         'VGS = %s - %s at this one sample' % (g, s))
    # one dynamic rail-current peak with its neighbours
    deck, data = datafile_for('load_c1_5pF')
    if data:
        groups, axis = samples_of(data)
        if all(('%s' % x) in groups[0] for x in ('V18:i', 'V33:i')):
            best = min(groups, key=lambda q: q.get('V33:i', 0.0))
            i = groups.index(best)
            emit_segment(rows, sha(deck)[:8], 'load_c1_5pF', data,
                         'vdd33 source-branch peak (injected = -V33:i)',
                         ['V18:i', 'V33:i', 'Ven:i', 'Vok:i', 'gate33'], i, 1,
                         'raw signed readings kept; no drain sum is substituted')
    return rows


def main():
    op = optparse.OptionParser()
    op.add_option('--what', default='stress')
    op.add_option('--out')
    o, _ = op.parse_args()
    if o.what == 'stress':
        hdr = ['original_run_id', 'case', 'original_item', 'original_target', 'datafile_sha256_16',
               'nodes_A_minus_B', 'window', 'original_min_max_V', 'strict_min_max_V',
               'difference_V', 'reader_rc_and_extreme_time', 'verdict', 'note']
        rows = do_stress()
        out = o.out or os.path.join(EVID, 'sc1_r2e1_vtx_reanalysis.csv')
    else:
        hdr = ['run_id', 'case', 'segment', 'datafile_sha256_16', 'sample_group_index', 'time_s',
               'time_ns', 'values_at_this_sample', 'window_note', 'why_this_segment', 'status']
        rows = do_samples()
        out = o.out or os.path.join(EVID, 'sc1_r2e1_waveform_samples.csv')
    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(',').join(u('"%s"') % h for h in hdr) + u('\n'))
        for r in rows:
            f.write(u(',').join(u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in r)
                    + u('\n'))
    col = -2 if o.what == 'stress' else -1
    bad = [r for r in rows if 'FAIL' in r[col] or 'BLOCKED' in r[col] or 'NO_CROSSING' in r[col]]
    print('R2E1_REREAD what=%s rows=%d refused_or_worse=%d -> %s' % (o.what, len(rows), len(bad),
                                                                    out))
    for r in bad[:12]:
        if o.what == 'stress':
            print('   %s | %s | %s | orig=%s new=%s | %s'
                  % (r[1], r[3][:34], r[6][:26], r[7], r[8], r[col]))
        else:
            print('   %s | %s | %s' % (r[0], r[2][:46], r[col]))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
