#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-A: parse the delivered evidence and recompute what it claims.

    python scripts/sc1_s3a_verify_evidence.py [--root PROJ]
    python scripts/sc1_s3a_verify_evidence.py --negatives    # two tamper cases, offline copy only

This exists because a hash list cannot tell an empty file from a full one (AGENTS rule 27 / R3A), and
because a characterisation round is only auditable if the reviewer can rebuild the numbers from the
shipped rows. Everything here is offline arithmetic on the delivered CSVs -- no simulator, no
preflight, no reader call.

Independent recomputations, each from the raw signed columns rather than from a stored verdict:
  * Ron at every DC point = (V(S) - V(D)) / I_SD, and the VSD = 0 point must be NOT_DEFINED;
  * the candidate rank N = ceil(11.52 mA / the measured single-device I_SD at VSD = 0.10 V),
    compared against the deck that actually ran;
  * the conditional target verdict, from the measured candidate total;
  * the gate charge of each edge, integrated PER CASE from that case's own contiguous sample block and
    compared against that case's declared raw_Q, net_Q and C_eff,Q.

What this script used to get wrong, and why the wording around S3-A had to be withdrawn. The previous
version collected the `select_edge` rows of BOTH dynamic cases into one list sorted by time, integrated
the mixture, and only asserted the result was non-zero. A reviewer who changed a declared charge from
-4.97349 pC to -9999 pC still got rc=0 and 27/27, so "27/27 certifies the four charges" was never a
true statement. The checks below are scoped by run_id + case + window + deck/raw identity, they demand
contiguous samples and covered endpoints, they subtract only that case's own stated baseline, and the
allowed difference is derived from the export precision of the shipped tokens propagated through the
trapezoid -- not from a percentage picked to pass. `--negatives` proves the two ways this round could
still be faked are now refused.
"""
from __future__ import print_function

import csv
import math
import optparse
import os
import re
import shutil
import sys
import tempfile

FILES = {'cases': 'sc1_s3a_cases.csv', 'dc': 'sc1_s3a_dc_points.csv',
         'samples': 'sc1_s3a_dyn_samples.csv', 'manifest': 'sc1_s3a_manifest.csv',
         'identity': 'sc1_s3a_identity.csv', 'log': 'sc1_s3a_dependency_log.txt'}

I_COLUMN = 15e-6 * 768
V_DROP = 0.10
RON_TARGET = 0.10 / I_COLUMN
V33 = 3.3
# the edge windows come from the frozen VG schedule of the deck (49..51 ns down, 199..201 ns up), not
# from the row being checked; a declaration that names a different window is a finding, not a licence
EDGE_SELECT = (49.0, 51.0)
EDGE_BLANK = (199.0, 201.0)
EDGE_OF = {'select_on': ('select_edge', EDGE_SELECT), 'blank_off': ('blank_edge', EDGE_BLANK)}
NUM_RE = r'(?:-?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?|-?[0-9]*\.?[0-9]+)'


def read(root, name):
    path = os.path.join(root, 'results', 'evidence', name)
    if not os.path.isfile(path):
        return None, None, path
    rows = list(csv.reader([l for l in open(path, 'rb').read().decode('utf-8', 'replace').split('\n')
                            if l.strip()]))
    return rows[0], rows[1:], path


def num(tok):
    try:
        return float(tok)
    except Exception:
        return None


def finite(tok):
    v = num(tok)
    return v is not None and v == v and abs(v) != float('inf')


def traj(xs, ys):
    return sum(0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))


def half_ulp(tok):
    """one half-step of the grid the export really wrote: `fmt_v` is `%.6g`, six significant digits

    The delivered sample text is 6 s.f. (0.00116552, 4.90167e-08). The last digit kept of a value whose
    leading digit sits at 10^E is 10^(E-5), so a shipped token represents its true value within
    +-0.5*10^(E-5). This is a property of the file, not a tolerance chosen here.
    """
    v = abs(num(tok))
    if not v:
        return 0.0
    e = math.floor(math.log10(v) + 1e-9)
    return 0.5 * 10.0 ** (e - 5)


def fmt(x):
    return '%.6g' % x if x is not None else ''


# ---------------------------------------------------------------- gate charge, one case at a time
def declared_charges(cases):
    out = {}
    for r in cases or []:
        if r[1] != 'S3A_GATE_CHARGE':
            continue
        m = re.match(r'^(\w+) edge ([0-9.]+)\.\.([0-9.]+) ns$', r[3])
        if not m or m.group(1) not in EDGE_OF:
            continue
        d = dict(re.findall(r'([A-Za-z_][\w,]*)=(' + NUM_RE + r')', r[5]))
        out[(r[2], m.group(1))] = {'edge_ns': (float(m.group(2)), float(m.group(3))),
                                   'points': d.get('points'), 't': d.get('t'),
                                   'span': d.get('span'), 'raw_Q': d.get('raw_Q'),
                                   'net_Q': d.get('net_Q'), 'c_eff': d.get('C_eff,Q'),
                                   'run_id': r[0]}
    return out


def declared_baselines(cases):
    out = {}
    for r in cases or []:
        if r[1] != 'S3A_DYN_BASELINE':
            continue
        m = re.search(r'band=(' + NUM_RE + r')\.\.(' + NUM_RE + r')', r[5])
        p = re.search(r'points=(\d+)', r[5])
        if m:
            out[r[2]] = (num(m.group(1)), num(m.group(2)), int(p.group(1)) if p else 0)
    return out


def sample_block(sam, cid, tag):
    """every shipped row of THIS case and THIS window, carrying a parseable VG:i"""
    rows, seen_run, seen_deck, seen_raw = [], set(), set(), set()
    missing = 0
    for r in sam:
        if r[1] != cid or r[2] != tag:
            continue
        rows.append(r)
        seen_run.add(r[0])
        seen_deck.add(r[7])
        seen_raw.add(r[8])
        m = re.search(r'(?:^|\s)VG:i=(' + NUM_RE + r')', r[5])
        if not m or not finite(m.group(1)):
            missing += 1
    return rows, seen_run, seen_deck, seen_raw, missing


def vg_of(row):
    m = re.search(r'(?:^|\s)VG:i=(' + NUM_RE + r')', row[5])
    return m.group(1) if m else None


def charge_checks(check, man, cases, sam):
    """four edges x (identity, contiguity, endpoints, raw_Q, net_Q + C_eff), each scoped to one case"""
    dec = declared_charges(cases)
    bas = declared_baselines(cases)
    man_by_deck = dict((r[3], r) for r in man)
    ceffs = []
    for key in sorted(dec):
        cid, edge = key
        d = dec[key]
        tag, win_ns = EDGE_OF[edge]
        w0, w1 = win_ns
        rows, runs, decks, raws, missing = sample_block(sam, cid, tag)
        mrow = man_by_deck.get(cid + '.scs')
        # --- identity: one run, one deck, one raw file, and it must be this case's own deck
        ident_ok = (len(runs) == 1 and len(decks) == 1 and len(raws) == 1 and rows and
                    mrow is not None and decks == set([mrow[4]]) and raws == set([mrow[5]]) and
                    runs == set([d['run_id']]))
        check('%s %s: samples belong to one run, one case and this deck/raw identity' % (cid, edge),
              ident_ok, 'rows=%d runs=%s deck_shas=%s expected=%s raw_shas=%d'
              % (len(rows), sorted(runs), sorted(x[:8] for x in decks),
                 (mrow[4][:8] if mrow else 'NO_MANIFEST_ROW'), len(raws)))
        if not rows or missing:
            check('%s %s: every sample of the block carries a finite VG:i' % (cid, edge), False,
                  'missing_or_unparseable=%d of %d rows' % (missing, len(rows)))
            continue
        check('%s %s: every sample of the block carries a finite VG:i' % (cid, edge), True,
              'rows=%d' % len(rows))
        # --- ordering, contiguity and time validity
        order = sorted(rows, key=lambda r: num(r[4]))
        times = [num(r[4]) for r in order]
        idx = [int(r[3]) for r in order]
        inside = [i for i, t in enumerate(times) if w0 * 1e-9 - 1e-18 <= t <= w1 * 1e-9 + 1e-18]
        sub = [order[i] for i in inside]
        st = [times[i] for i in inside]
        si = [idx[i] for i in inside]
        check('%s %s: the integrated points are adjacent rows in the file, in increasing time'
              % (cid, edge), len(sub) >= 2 and all(si[i + 1] - si[i] == 1 for i in range(len(si) - 1))
              and all(st[i + 1] > st[i] for i in range(len(st) - 1))
              and all(0 < st[i + 1] - st[i] < 1e-9 for i in range(len(st) - 1)),
              'points=%d index_gap_max=%d dt_max=%.3g s'
              % (len(sub), max([si[i + 1] - si[i] for i in range(len(si) - 1)] or [0]),
                 max([st[i + 1] - st[i] for i in range(len(st) - 1)] or [0])))
        # --- the declared window is the deck's schedule, and the block must cover it
        check('%s %s: the declared edge window is the frozen 49..51 / 199..201 ns schedule'
              % (cid, edge), d['edge_ns'] == (w0, w1), 'declared=%s..%s ns' % d['edge_ns'])
        span = d['span'] and num(d['span'])
        check('%s %s: the block spans the declared endpoints, so no part of the edge is cut'
              % (cid, edge), sub and st[0] <= w0 * 1e-9 + 1e-18 and st[-1] >= w1 * 1e-9 - 1e-18 and
              span is not None and abs((st[-1] - st[0]) - span) <= 2 * half_ulp('%g' % st[-1]) and
              len(sub) == int(d['points']),
              't=%.6g..%.6g s declared=%s pts=%d/%s' % (st[0] if sub else 0, st[-1] if sub else 0,
                                                        d['t'], len(sub), d['points']))
        if len(sub) < 2:
            continue
        ys = [-num(vg_of(r)) for r in sub]
        raw = traj(st, ys)
        # --- tolerance: the shipped tokens' own half-steps, propagated through the trapezoid
        yt = [vg_of(r) for r in sub]
        xt = [r[4] for r in sub]
        n = len(sub)
        dt = [st[i] - st[i - 1] for i in range(1, n)]
        dy = [half_ulp(v) for v in yt]
        dx = [half_ulp(t) for t in xt]
        tol_y = sum(dy[k] * ((dt[k - 1] / 2 if k else 0.0) + (dt[k] / 2 if k < n - 1 else 0.0))
                    for k in range(n))
        tol_x = sum(dx[k] * (0.5 * abs(ys[0] + ys[1]) if k == 0 else
                             0.5 * abs(ys[n - 2] + ys[n - 1]) if k == n - 1 else
                             0.5 * abs(ys[k - 1] - ys[k + 1])) for k in range(n))
        tol_decl = half_ulp(d['raw_Q'])
        tol = tol_y + tol_x + tol_decl
        check('%s %s: raw_Q rebuilds from this case alone inside the export-precision band'
              % (cid, edge), abs(raw - num(d['raw_Q'])) <= tol,
              'rebuilt=%.10g declared=%s |d|=%.3g tol=%.3g (samples %.3g + time %.3g + declared %.3g)'
              % (raw, d['raw_Q'], abs(raw - num(d['raw_Q'])), tol, tol_y, tol_x, tol_decl))
        # --- baseline: only this case's own stated band, never a borrowed one
        if cid not in bas:
            check('%s %s: net_Q and C_eff,Q use THIS case baseline' % (cid, edge), False,
                  'LIMITATION: this case declares no 10..40 ns baseline band, so the shipped copy '
                  'cannot support net_Q; raw_Q above is the only certified figure and no other '
                  "case's number was borrowed")
            continue
        blo, bhi, _bp = bas[cid]
        mid = 0.5 * (blo + bhi) * (span or (st[-1] - st[0]))
        tol_band = 0.5 * (bhi - blo) * (span or (st[-1] - st[0]))
        net = raw - mid
        ceff = abs(net) / V33
        tol_net = tol + tol_band
        check('%s %s: net_Q = raw_Q - this case baseline x span, inside the band' % (cid, edge),
              abs(net - num(d['net_Q'])) <= tol_net,
              'net=%.10g declared=%s |d|=%.3g tol=%.3g (baseline term %.3g, band %.3g..%.3g A)'
              % (net, d['net_Q'], abs(net - num(d['net_Q'])), tol_net, mid, blo, bhi))
        check('%s %s: C_eff,Q = |net_Q| / 3.3 V rebuilds inside the band' % (cid, edge),
              abs(ceff - num(d['c_eff'])) <= tol_net / V33,
              'C_eff=%.10g F declared=%s |d|=%.3g' % (ceff, d['c_eff'],
                                                      abs(ceff - num(d['c_eff']))), )
        ceffs.append(ceff * 1e12)
    if len(ceffs) == 4:
        check('the four certified edges are the charge load of the candidate, stated as a range',
              all(c is not None for c in ceffs),
              'C_eff,Q = %.3f..%.3f pF over select+blank x light+column (an equivalent load for the '
              'measured edge, not a fixed Cgg)' % (min(ceffs), max(ceffs)))
    else:
        check('all four edges certified', False, 'certified=%d of 4' % len(ceffs))


# ---------------------------------------------------------------- the checks
def run_checks(root, expect_decks, quiet=False):
    failed = []
    done = [0]

    def check(name, ok, detail):
        done[0] += 1
        if not ok:
            failed.append(name)
        if not quiet:
            print('   %-64s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))
        return bool(ok)

    _h, man, p_man = read(root, FILES['manifest'])
    check('per-deck manifest exists', man is not None, p_man)
    if not man:
        print('S3A_EVIDENCE_CHECK: FAIL (no manifest)')
        return 1, failed, done[0]
    decks = [r[3] for r in man]
    check('the manifest covers %d decks at most, all unique' % expect_decks,
          len(man) <= expect_decks and len(set(decks)) == len(man),
          'decks=%d unique=%d' % (len(man), len(set(decks))))
    check('every deck carries a 64-hex deck sha and a 64-hex raw sha',
          all(len(r[4]) == 64 and len(r[5]) == 64 for r in man), '')
    check('every deck records preflight rc and spectre rc as 0 and runner PASS',
          all(r[18] == '0' and r[19] == '0' and r[20] == 'PASS' for r in man),
          'rcs=%s/%s verdicts=%s' % (sorted(set(r[18] for r in man)),
                                     sorted(set(r[19] for r in man)),
                                     sorted(set(r[20] for r in man))))
    check('the temperature the run reported is read back, not assumed',
          all(r[9] and r[9] != 'NOT_READ' for r in man),
          'values=%s' % sorted(set(r[9] for r in man)))
    check('every deck declares the model, section, L, W and N',
          all(r[6] == 'p33' and r[7] == 'tt' and r[11] and r[12] and r[13] for r in man),
          'models=%s sections=%s' % (sorted(set(r[6] for r in man)),
                                     sorted(set(r[7] for r in man))))

    _h, dc, p_dc = read(root, FILES['dc'])
    check('the dc point table exists with rows', bool(dc), '%s rows=%d' % (p_dc, len(dc or [])))
    singles, cands = {}, {}
    if dc:
        widths = set(len(r) for r in dc)
        check('every dc row has the header width', widths == set([len(_h)]), 'widths=%s' % sorted(widths))
        bad = [r for r in dc if not finite(r[5]) or (r[10] and not finite(r[10])) or
               (r[11] and not finite(r[11]))]
        check('sweep and current columns are finite numbers', not bad, 'bad=%d' % len(bad))
        zero = [r for r in dc if abs(num(r[6]) or 0.0) < 1e-12]
        check('the VSD=0 point is NOT_DEFINED with no resistance written',
              bool(zero) and all(r[15] == 'NOT_DEFINED' and r[14] == '' for r in zero),
              'points=%d' % len(zero))
        recomputed, mism = 0, []
        for r in dc:
            if r[15] != 'MEASURED':
                continue
            vs, vdr, i_sd, ron = num(r[9]), num(r[7]), num(r[13]), num(r[14])
            if None in (vs, vdr, i_sd, ron) or i_sd == 0:
                continue
            recomputed += 1
            got = (vs - vdr) / i_sd
            if abs(got - ron) > max(1e-6, abs(got) * 1e-4):
                mism.append((r[1], r[4], fmt(got), r[14]))
        check('every Ron recomputes from the signed columns', recomputed > 0 and not mism,
              'checked=%d mismatches=%s' % (recomputed, mism[:3]))
        for r in dc:
            if abs((num(r[6]) or 0.0) - V_DROP) < 1e-9:
                (cands if r[1].endswith('_par') else singles)[r[1]] = num(r[13])
        check('the VSD=0.10 V point exists for every single-device deck', len(singles) >= 1,
              'singles=%s' % ','.join(sorted(singles)))

    par_row = [r for r in man if r[3] == 's3a_on_par.scs']
    if singles and par_row:
        # W comes from the two columns whose unit is unambiguous (w_total_m / n_devices). The delivered
        # S3-A copy stored a micrometre figure under the name W_m; the generator now writes metres, and
        # results/evidence/sc1_s3b_s3a_manifest_correction.csv proves the per-device width against the
        # hash of each rebuilt deck. Reading r[12] * 1e6 is what printed W_best=1e+08 um.
        w_um_of = dict((r[3], num(r[14]) / int(r[13]) * 1e6) for r in man if r[13])
        w_best = max(w_um_of[r[3]] for r in man if r[3].startswith('s3a_on_w'))
        best_single = max([v for k, v in singles.items() if k.startswith('s3a_on_w')])
        n_req = int(math.ceil(I_COLUMN / best_single))
        n_done = int(par_row[0][13])
        check('the candidate rank is what the measurement implies, clamped to 16',
              n_done == max(1, min(16, n_req)),
              'W_best=%g um (from w_total_m/n_devices) I_SD=%s A -> N_req=%d, deck ran N=%d'
              % (w_best, fmt(best_single), n_req, n_done))
        unit_ok, unit_seen = True, set()
        for r in man:
            w = w_um_of.get(r[3])
            tok = num(r[12])
            if w is None or tok is None:
                unit_ok = False
                continue
            as_um = abs(tok - w) <= max(1e-12, w * 1e-9)
            as_m = abs(tok - w * 1e-6) <= max(1e-18, w * 1e-15)
            unit_ok = unit_ok and (as_um or as_m)
            unit_seen.add('um' if as_um and not as_m else ('m' if as_m else 'either'))
        check('W_m is either the corrected metre figure or the delivered micrometre figure, and '
              'consistent with w_total_m', unit_ok, 'per-row reading=%s' % sorted(unit_seen))

    off = [r for r in man if r[3] == 's3a_off_par.scs']
    check('the off-state deck ran with its own preflight and rc', bool(off) and off[0][18] == '0',
          'present=%s' % bool(off))

    _hs, sam, p_sam = read(root, FILES['samples'])
    check('the transient sample rows exist', bool(sam), '%s rows=%d' % (p_sam, len(sam or [])))
    _h, cases, p_cases = read(root, FILES['cases'])
    check('the case result file exists with rows', bool(cases), '%s rows=%d' % (p_cases,
                                                                                len(cases or [])))
    if sam and cases and man:
        charge_checks(check, man, cases, sam)

    if sam:
        widths = set(len(r) for r in sam)
        check('every sample row has the header width', widths == set([len(_hs)]),
              'widths=%s' % sorted(widths))
        bad = [r for r in sam if not finite(r[4])]
        check('sample times are finite', not bad, 'bad=%d' % len(bad))

    _h, idr, p_id = read(root, FILES['identity'])
    check('the identity index exists and matches the deck count',
          bool(idr) and len(idr) == len(man), '%s rows=%d' % (p_id, len(idr or [])))
    if idr:
        check('identity paths are project-relative and free of vendor absolute paths',
              all(not r[2].startswith('/') and not r[4].startswith('/') and '/root/' not in ''.join(r)
                  for r in idr), '')
        check('the PDK is identified by 64-hex digests only',
              all(len(r[i]) == 64 for r in idr for i in (6, 7, 8, 9)), '')

    if cases:
        bad = [r for r in cases if r[7] in ('FAIL', 'BLOCKED')]
        check('no functional FAIL and no dependency BLOCKED row', not bad,
              'bad=%s' % [(r[1], r[2], r[7]) for r in bad][:4])
        vals = set(r[7] for r in cases)
        check('the verdict vocabulary is the one this entry emits',
              vals <= set(['PASS', 'MEASURED', 'NOT_AVAILABLE', 'NOT_MET', 'MET', 'MEASURED_PLAN',
                           'RAN', 'RAN_WITH_READER_REFUSALS', 'SELFTEST']),
              'seen=%s' % sorted(vals))
    if os.path.isfile(os.path.join(root, 'results', 'evidence', FILES['log'])):
        txt = open(os.path.join(root, 'results', 'evidence', FILES['log']), 'rb').read() \
            .decode('utf-8', 'replace')
        check('the dependency log carries a preflight and runner excerpt per deck',
              txt.count('run accepted') >= len(man), 'accepted=%d decks=%d'
              % (txt.count('run accepted'), len(man)))
        check('no vendor path survives in the dependency log', '/root/' not in txt, '')
    return (1 if failed else 0), failed, done[0]


def negatives():
    """the two ways this round could still be faked, each run against a private copy of the evidence"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = tempfile.mkdtemp(prefix='s3a_neg_')
    ev = os.path.join(tmp, 'results', 'evidence')
    os.makedirs(ev)
    for name in FILES.values():
        shutil.copyfile(os.path.join(root, 'results', 'evidence', name), os.path.join(ev, name))
    print('   (copies of the delivered evidence live in %s; nothing official is written)' % tmp)
    ok = True
    try:
        # A. a tampered charge declaration: the integral is untouched, the stated number is not
        p = os.path.join(ev, FILES['cases'])
        txt = open(p, 'rb').read().decode('utf-8')
        hit = txt.count('net_Q=-4.97349e-12')
        txt2 = txt.replace('net_Q=-4.97349e-12', 'net_Q=-9.999e-09', 1)
        open(p, 'wb').write(txt2.encode('utf-8'))
        rc, failed, n = run_checks(tmp, 9, quiet=True)
        caught = [f for f in failed if 'select_on' in f and 'net_Q' in f]
        print('   A tampered net_Q (-4.97349 pC -> -9999 pC), declaration hit=%d' % hit)
        print('     failures=%d caught_by=%s' % (len(failed), caught or failed[:2]))
        ok = ok and rc == 1 and bool(caught)
        open(p, 'wb').write(txt.encode('utf-8'))

        # B. another case's current samples pasted into this case's block, identity fields left alone
        p = os.path.join(ev, FILES['samples'])
        txt = open(p, 'rb').read().decode('utf-8')
        rows = list(csv.reader([l for l in txt.split('\n') if l.strip()]))
        hdr, body = rows[0], rows[1:]
        col = [(i, r) for i, r in enumerate(body)
               if r[1] == 's3a_dyn_column' and r[2] == 'select_edge']
        li = [(i, r) for i, r in enumerate(body)
              if r[1] == 's3a_dyn_light' and r[2] == 'select_edge']
        splice = 0
        for k in range(min(len(col), len(li))):
            j, lr = li[k]
            cr = col[k][1]
            if re.search(r'VG:i=', lr[5]) and re.search(r'VG:i=', cr[5]):
                body[j] = lr[:5] + [cr[5]] + lr[6:]
                splice += 1
        with open(p, 'wb') as f:
            f.write((''.join(S3A_CSVLINE(hdr)) + ''.join(S3A_CSVLINE(r) for r in body)).encode('utf-8'))
        rc, failed, n = run_checks(tmp, 9, quiet=True)
        caught = [f for f in failed if 's3a_dyn_light' in f and ('raw_Q' in f or 'C_eff' in f
                                                                or 'endpoints' in f)]
        print('   B %d of the light block rows carry the column case VG:i values' % splice)
        print('     failures=%d caught_by=%s' % (len(failed), caught or failed[:2]))
        ok = ok and rc == 1 and bool(caught)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    rc, failed, n = run_checks(root, 9, quiet=True)
    print('   C the delivered bytes as they are: rc=%d checks=%d failures=%s' % (rc, n, failed or 'none'))
    ok = ok and rc == 0
    print('S3A_NEGATIVE_SELFTEST: %s (a tampered charge and a cross-case splice must both be refused, '
          'the intact delivery must pass)' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def S3A_CSVLINE(vals):
    return ','.join('"%s"' % str(v).replace('"', '""') for v in vals) + '\n'


def main():
    op = optparse.OptionParser()
    op.add_option('--root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    op.add_option('--expect-decks', type='int', default=9)
    op.add_option('--negatives', action='store_true',
                  help='tamper a private copy of the evidence and require both refusals')
    o = op.parse_args()[0]
    if o.negatives:
        return negatives()
    rc, failed, n = run_checks(o.root, o.expect_decks)
    print('S3A_EVIDENCE_CHECK checks=%d failures=%d root=%s' % (n, len(failed), o.root))
    return rc


if __name__ == '__main__':
    sys.exit(main())
