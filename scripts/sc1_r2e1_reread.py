#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E1: re-read what R2E already measured. NO SIMULATOR IS CALLED.

    python scripts/sc1_r2e1_reread.py --what stress    # C1: strict re-read of the stress rows
    python scripts/sc1_r2e1_reread.py --what samples   # C2: sampled waveform excerpts
    python scripts/sc1_r2e1_reread.py --what boundary  # R2E2 2.2: the next-boundary rule, offline

Both re-read modes open the SAME files the R2E runs produced, under
`cadence_work/sc1_sim/r2e_s2_<group>/`, and go through the audited parser
(scripts/sc1_read_psf.parse) plus the strict difference tool (scripts/sc1_r2e_vtx.py). Nothing is
re-simulated, nothing is interpolated inside a printed segment, and no old CSV is rewritten: if a
re-read contradicts the original, the original row stays and the new row says so.

R2E2 changed the samples extraction in two ways, both of them in THIS new file rather than in the
frozen tools: the next input boundary of a repeat3 answer is now a real interpolated 50 % crossing of
either direction after the owning edge (with END_OF_DATA where no later edge exists), and the 90 %/10 %
labels of the C0 fall band are put back the right way round. The corrected output is written to
sc1_r2e2_waveform_samples.csv; sc1_r2e1_waveform_samples.csv keeps R2E1's rows as delivered.

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


def crossing_times(groups, axis, sig, lvl):
    """EVERY crossing of `lvl' in either direction, interpolated between its two samples.

    -> [(right-hand sample index, crossing time)] in file order.

    The three rules are the audited tool's own (the `crossings' helper inside sc1_delay.py's
    propdelay mode, which is where the reported t_next boundary comes from): a sample that sits
    exactly on the level is credited when it is REACHED, so a left-hand plateau value is skipped;
    a right-hand exact level is taken at that sample time; anything strictly between is linearly
    interpolated. R2E1's extractor instead searched for the first SAMPLE whose time was later than
    t_in, so it reported the current edge's own right-hand sample as the next boundary -- 102.01 ns
    where the audited tool gives 252 ns. This file is the new extraction layer; sc1_delay.py itself
    is frozen and untouched.
    """
    xs = []
    for i in range(1, len(groups)):
        a, b = groups[i - 1].get(sig), groups[i].get(sig)
        if a is None or b is None:
            continue
        t0, t1 = groups[i - 1][axis], groups[i][axis]
        if a == lvl and b != lvl:
            continue
        if b == lvl:
            xs.append((i, t1))
        elif (a < lvl < b) or (b < lvl < a):
            xs.append((i, t0 + (lvl - a) * (t1 - t0) / (b - a)))
    return xs


def owning_crossing(xs, t_in):
    """the input edge an answer belongs to, and the one after it.

    -> (k, t_own, t_next, t_before) where t_next is None for the last edge (no boundary exists,
       which is written as END_OF_DATA rather than invented) and t_before is the edge just before
       the owning one, i.e. the lower bound of the attribution window.

    Matching uses the crossing itself, not the rounded t_in from the old CSV: t_in is quoted to
    6 significant digits, so the owning edge is the last crossing at or before t_in plus ONE
    display step of that value.
    """
    tol = band(t_in)
    k = None
    for i, (_idx, t) in enumerate(xs):
        if t <= t_in + tol:
            k = i
        else:
            break
    if k is None:
        return None, None, (xs[0][1] if xs else None), None
    return (k, xs[k][1], xs[k + 1][1] if k + 1 < len(xs) else None,
            xs[k - 1][1] if k else None)


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


def emit_crossing_segment(rows, run_id, case, data, xs, k, sigs, span=2, extra=''):
    """the real samples straddling CROSSING k, addressed by the crossing's own sample index.

    R2E1 located the neighbourhood by nearest-sample-to-t_in, which mixes up a crossing with the
    point its boundary was reported at; here the index comes from crossing_times().
    """
    if k is None or k >= len(xs):
        return
    emit_segment(rows, run_id, case, data, extra[0], sigs, xs[k][0], span, extra[1])


def do_samples():
    rows = []
    PLAN = [
        # (case, signals to print, [(sig, thr, rising, window_lo, window_hi, what)], note)
        ('dyn_c0_rise', ['en', 'gate33', 'Xt.x', 'Xt.y'],
         [('en', 0.9, True, None, None, 'input 50% rise'),
          ('gate33', 2.97, False, None, None, 'output 90% high end of the fall (2.97 = 0.9 x 3.3)'),
          ('gate33', 1.65, False, None, None, 'output 50% fall'),
          ('gate33', 0.33, False, None, None, 'output 10% low end of the fall (0.33 = 0.1 x 3.3)')],
         '1 pF load'),
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
         [('en', 0.9, 'any', None, None, 'input 50% crossing'),
          ('gate33', 1.65, False, None, None, 'output 50% fall, 5 pF coarse step')],
         'the heaviest prepared load; the input neighbourhood was missing in R2E1 and is read from '
         'THIS raw, not borrowed from the 1 pF deck'),
        ('load_c1_5pF_fine', ['en', 'core_ok33', 'gate33'],
         [('en', 0.9, 'any', None, None, 'input 50% crossing'),
          ('gate33', 1.65, False, None, None, 'output 50% fall, same case at maxstep 0.05 ns')],
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
            if rising == 'any':
                # whichever edges THIS deck's own stimulus actually produces, one segment per
                # direction: R2E1 asked for a fall the load decks never stimulate and reported the
                # absence as a refusal, which is a question error, not a circuit fact
                xs = crossing_times(groups, axis, sig, thr)
                seen = set()
                for j, (idx, tc) in enumerate(xs):
                    a, b = groups[idx - 1][sig], groups[idx][sig]
                    d = 'rise' if b > a else 'fall'
                    if d in seen:
                        continue
                    seen.add(d)
                    emit_segment(rows, run_id, case, data,
                                 '%s (%s at %.9g s) [%s]' % (what, d, tc, note),
                                 sigs, idx, 2, 'crossing %d of this raw: %s crosses %.3g on a %s'
                                 % (j + 1, sig, thr, d))
                if not seen:
                    rows.append([run_id, case, what, sha(data)[:16], '-', '-', '-',
                                 'sig=%s thr=%s' % (sig, thr), '-',
                                 'NO_CROSSING in this file: the original row is kept, nothing is '
                                 'invented', 'NO_CROSSING'])
                continue
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
    # repeat3: the 12 attributed pairs, each with its owning input edge and the NEXT true input crossing
    boundary_rows = []
    for case in ('dyn_c0_repeat3', 'dyn_c1_repeat3'):
        deck, data = datafile_for(case)
        if not data:
            rows.append(['-', case, 'attribution boundary', '-', '-', '-', '-', '-', '-',
                         'BLOCKED: this case raw is no longer on disk', 'BLOCKED'])
            continue
        run_id = sha(deck)[:8]
        groups, axis = samples_of(data)
        in_xs = crossing_times(groups, axis, 'en', 0.9)
        out_xs = crossing_times(groups, axis, 'gate33', 1.65)
        for r in rows_of(os.path.join(EVID, 'sc1_r2e_s2_dynamic_repeat3.csv')):
            if len(r) < 9 or r[1] != 'S2_DELAY' or r[2] != case:
                continue
            m = re.search(r't_in=(\S+) t_out=(\S+)', r[5])
            if not m:
                continue
            t_in, t_out = float(m.group(1)), float(m.group(2))
            # the boundary is the NEXT 50 % crossing of the input waveform of either direction, after
            # the crossing this answer belongs to -- not the sample that happens to sit right of t_in
            k, t_own, t_next, t_prev = owning_crossing(in_xs, t_in)
            nxt = '%.9g' % t_next if t_next is not None else 'END_OF_DATA'
            own = '%.9g' % t_own if t_own is not None else 'BEFORE_FIRST_EDGE'
            ordered = t_in <= t_out + band(t_out)
            inside = ordered and (t_next is None or t_out < t_next - 1e-15)
            status = ('END_OF_DATA' if t_next is None else
                      ('BOUNDARY_OK' if inside else 'BOUNDARY_FAIL'))
            rows.append([run_id, case, 'attribution boundary of input edge %s of %s'
                         % (k + 1 if k is not None else '?', len(in_xs)), sha(data)[:16],
                         str(in_xs[k][0]) if k is not None else '-', own, ns(t_own) if t_own else '-',
                         't_in=%.9g t_out=%.9g t_next=%s' % (t_in, t_out, nxt),
                         'attribution window [%s, %s)' % (own, nxt),
                         't_in <= t_out %s t_next: %s' % ('<' if ordered else '>=',
                                                           'HOLDS' if inside else 'VIOLATED')
                         + ('' if t_next is not None else ' (no later input edge exists in this data)'),
                         status])
            boundary_rows.append((case, t_in, t_out, nxt, status))
            # the samples themselves, addressed by the crossing index rather than by the rounded t_in
            ko = None
            if out_xs:
                cand = min(range(len(out_xs)), key=lambda j: abs(out_xs[j][1] - t_out))
                if abs(out_xs[cand][1] - t_out) <= band(t_out):
                    ko = cand
            for xs, kk, sig, role in ((in_xs, k, 'en', 'owning input 50%% edge (crossing %s of %s)'
                                       % (k + 1 if k is not None else '?', len(in_xs))),
                                      (out_xs, ko, 'gate33', 'answered output 50% edge')):
                if kk is None:
                    rows.append([run_id, case, role, sha(data)[:16], '-', '-', '-', 'sig=%s' % sig,
                                 '-', 'NO_CROSSING matches this reference time; the original row is '
                                 'kept and nothing is invented', 'NO_CROSSING'])
                    continue
                emit_segment(rows, run_id, case, data, role, [sig, 'en', 'gate33'], xs[kk][0], 2,
                             't_in=%.9g t_out=%.9g; next input 50%% boundary=%s'
                             % (t_in, t_out, nxt))
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
    for case, t_in, t_out, nxt, status in boundary_rows:
        print('REPEAT3_BOUNDARY %-16s t_in=%.9g t_out=%.9g t_next=%-12s t_in<=t_out<t_next '
              '-> %s' % (case, t_in, t_out, nxt, status))
    return rows


# ------------------------------------------------------------------ the one bounded offline case
def do_boundary_selftest():
    """R2E2 2.2: one synthetic fragment, no simulator and no project raw involved.

    Two adjacent input crossings whose right-hand SAMPLE is later than the owning crossing time --
    exactly the shape R2E1 got wrong. The extractor has to report the interpolated next crossing
    (300 ns), not the sample at 202 ns, and END_OF_DATA after the last one.
    """
    rows = []
    frag = [(0.0, 0.0), (200e-9, 0.0), (202e-9, 1.8), (250e-9, 1.8), (300e-9, 0.0),
            (350e-9, 0.0), (400e-9, 1.8)]
    groups = [{'time': t, 'en': v} for t, v in frag]
    xs = crossing_times(groups, 'time', 'en', 0.9)
    # expectation built by hand, not by calling the code under test again
    want = [200e-9 + (0.9 / 1.8) * (202e-9 - 200e-9),   # rise 200->202 ns: 201 ns
            250e-9 + (0.9 / 1.8) * (300e-9 - 250e-9),     # fall 250->300 ns: 275 ns
            350e-9 + (0.9 / 1.8) * (400e-9 - 350e-9)]     # rise 350->400 ns: 375 ns
    got = [t for _i, t in xs]
    ok = len(got) == len(want) and all(abs(a - b) <= 1e-15 for a, b in zip(got, want))
    rows.append(['synthetic', 'crossing list of both directions', str(len(xs)),
                 ' ; '.join('%.9g' % t for t in got), ' ; '.join('%.9g' % t for t in want),
                 'PASS' if ok else 'FAIL'])
    for t_in, want_own, want_next in ((201e-9, 201e-9, 275e-9), (275e-9, 275e-9, 375e-9),
                                      (375e-9, 375e-9, None)):
        k, own, nxt, _prev = owning_crossing(xs, t_in)
        hit = (abs(own - want_own) <= 1e-15 and
               ((nxt is None and want_next is None) or (nxt is not None and
                                                        abs(nxt - want_next) <= 1e-15)))
        rows.append(['synthetic', 'owning/next for t_in=%.9g' % t_in,
                     str(k), 'own=%.9g next=%s' % (own, '%.9g' % nxt if nxt is not None
                                                   else 'END_OF_DATA'),
                     'own=%.9g next=%s' % (want_own, '%.9g' % want_next if want_next is not None
                                           else 'END_OF_DATA'),
                     'PASS' if hit else 'FAIL'])
    # the last edge has no boundary: reported as END_OF_DATA, never as a made-up time
    k, own, nxt, _prev = owning_crossing(xs, 500e-9)
    rows.append(['synthetic', 't_in after the last input edge', str(k),
                 'next=%s' % ('END_OF_DATA' if nxt is None else '%.9g' % nxt),
                 'the owning edge is the 375 ns one and no next edge exists',
                 'PASS' if (nxt is None and abs(own - 375e-9) <= 1e-15) else 'FAIL'])
    # and the R2E1 mistake explicitly: the right-hand SAMPLE of the owning crossing is 202 ns
    k, own, nxt, _prev = owning_crossing(xs, 201e-9)
    sample_right = groups[xs[k][0]]['time']
    rows.append(['synthetic', 'R2E1 shape: right-hand sample vs true next', str(xs[k][0]),
                 'sample=%.9g next=%.9g' % (sample_right, nxt),
                 'the boundary must be the interpolated 275 ns crossing, not the 202 ns sample',
                 'PASS' if abs(nxt - 275e-9) <= 1e-15 and sample_right < nxt else 'FAIL'])
    return rows


def main():
    op = optparse.OptionParser()
    op.add_option('--what', default='stress')
    op.add_option('--out')
    o, _ = op.parse_args()
    SAMPLE_HDR = ['run_id', 'case', 'segment', 'datafile_sha256_16', 'sample_group_index', 'time_s',
                  'time_ns', 'values_at_this_sample', 'window_note', 'why_this_segment', 'status']
    if o.what == 'stress':
        hdr = ['original_run_id', 'case', 'original_item', 'original_target', 'datafile_sha256_16',
               'nodes_A_minus_B', 'window', 'original_min_max_V', 'strict_min_max_V',
               'difference_V', 'reader_rc_and_extreme_time', 'verdict', 'note']
        rows = do_stress()
        out = o.out or os.path.join(EVID, 'sc1_r2e1_vtx_reanalysis.csv')
    elif o.what == 'boundary':
        hdr = ['kind', 'what_is_checked', 'crossing_index', 'this_code_gives', 'built_by_hand',
               'verdict']
        rows = do_boundary_selftest()
        out = o.out or os.path.join(EVID, 'sc1_r2e2_boundary_selftest.csv')
    else:
        hdr = SAMPLE_HDR
        rows = do_samples()
        # R2E1 wrote sc1_r2e1_waveform_samples.csv with the wrong next-boundary field; that file is a
        # delivered record and is NOT rewritten, so the corrected extraction gets its own name.
        out = o.out or os.path.join(EVID, 'sc1_r2e2_waveform_samples.csv')
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
