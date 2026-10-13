#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-B: parse the delivered chain+bank evidence and recompute what it claims.

    python scripts/sc1_s3b_verify_evidence.py [--root PROJ]
    python scripts/sc1_s3b_verify_evidence.py --negatives    # tamper a private copy, offline

Everything here is offline arithmetic on the delivered CSVs plus the deck text this repository's own
generator rebuilds: no simulator, no preflight, no reader call. The point is the same as in R3A and
S3-A -- a hash list cannot tell a full file from an empty one, and a verdict is only worth anything if
the reviewer can re-form it from the shipped numbers.

What is checked, and why each one matters for this round specifically:

  * the nine declared cases exist, once each, from one run, with the deck each run really read;
  * the deck bytes are rebuilt from the generator and hashed: a row that claims 39 devices and a
    particular gate source has to be tied to the exact netlist, not to prose;
  * the supply contract: nine decks, the static layer accepted (its own rc 7 means "structure passed,
    circuit not evaluated"), the full preflight rc 0, and every declared rail entry reached;
  * the 39-MOS expansion and the fact that gate33 is driven by the chain, with no capacitor on it and
    no ideal source on q/qbar/en/gate33/bgate/scan;
  * every state claim in every window, judged from the shipped whole-window min/max the row carries,
    plus the negative case re-formed from its FULL shipped window;
  * each gate edge charge, integrated per case from that case's own contiguous charge block, against
    that case's declared raw_Q / net_Q / edge-equivalent load, inside a band derived from the 17-digit
    export precision -- the S3-A lesson, applied from the start;
  * the 50 % -> 50 % delay numbers, re-interpolated from the sample pairs the shipped blocks carry;
  * the three current branches kept apart, and the claimed peak re-formed where the block covers it.

`--negatives` refuses two fabrications: a tampered charge declaration, and one case's gate-current
samples pasted into another case's block.
"""
from __future__ import print_function

import csv
import hashlib
import io
import math
import optparse
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import sc1_s3b_chain_power_tt as B        # the same generator that wrote the decks

FILES = {'cases': 'sc1_s3b_cases.csv', 'manifest': 'sc1_s3b_manifest.csv',
         'samples': 'sc1_s3b_waveform_samples.csv', 'identity': 'sc1_s3b_identity.csv',
         'log': 'sc1_s3b_dependency_log.txt'}
EXPECTED_CASES = ['s3b_q0_off_light', 's3b_write_q1_light', 's3b_write_q1_column',
                  's3b_blank_assert_column', 's3b_blank_release_column', 's3b_write_q0_column',
                  's3b_repeat101_column', 's3b_guard_cycle_column', 's3b_fault_blank_to_vss_column']
VERDICTS = set(['PASS', 'MEASURED', 'NOT_AVAILABLE', 'NOT_MEASURED', 'NOT_DEFINED', 'MEASURED_PLAN',
                'EXPECTED_REFUSAL', 'DETECTED', 'PARTIAL_EDGE_CHARGE', 'CONDITIONAL_DROP_TARGET_NOT_MET',
                'NOT_MEASURED_OVERLAP', 'OUT_OF_ATTRIBUTION', 'NO_RESPONSE', 'SELFTEST', 'RAN',
                # emitted when the fault fails to show up as a difference; a delivery must not carry it
                'NOT_DETECTED',
                # these two are emitted by the entry itself; the check above is what reports them
                'FAIL', 'BLOCKED'])
GATE_FRACTIONS = (0.10, 0.90)


PART_INDEX = 'sc1_s3b_samples_parts.csv'
PART_PROBLEMS = []


def parts_rejoin(root):
    """the sample export as ordered parts, rejoined to bytes

    `precommit_safety_check.py` refuses any staged blob over 512 KiB, and this round's export is
    3 583 407 bytes because every gate-charge window ships point by point at 17 digits, so the
    delivery is the part list plus an index that records each part's digest and the whole file's.
    Every part repeats the header so it is readable on its own, which is why the rejoin keeps one
    header and drops the rest.
    """
    ev = os.path.join(root, 'results', 'evidence')
    ip = os.path.join(ev, PART_INDEX)
    if not os.path.isfile(ip):
        return None
    rows = list(csv.reader([l for l in open(ip, 'rb').read().decode('utf-8', 'replace').split('\n')
                            if l.strip()]))
    header, blob, whole, want = None, b'', '', 0
    for f in rows[1:]:
        name, nbytes, digest, src_whole, src_bytes = f[0], int(f[1]), f[2], f[6], int(f[7])
        p = os.path.join(ev, name)
        whole, want = src_whole, src_bytes
        if not os.path.isfile(p):
            PART_PROBLEMS.append('missing part %s' % name)
            continue
        one = open(p, 'rb').read()
        if len(one) != nbytes or hashlib.sha256(one).hexdigest() != digest:
            PART_PROBLEMS.append('%s does not match the bytes its index row records' % name)
            continue
        lines = one.split(b'\n')
        if header is None:
            header = lines[0]
        elif lines[0] != header:
            PART_PROBLEMS.append('%s repeats a different header than the first part' % name)
        blob += b'\n'.join(lines[1:])
    if header is None:
        PART_PROBLEMS.append('no part readable')
        return None
    joined = header + b'\n' + blob
    if hashlib.sha256(joined).hexdigest() != whole or len(joined) != want:
        PART_PROBLEMS.append('the parts rejoin to %d bytes sha %s, not the delivered %d bytes sha %s'
                            % (len(joined), joined and hashlib.sha256(joined).hexdigest()[:12],
                               want, whole[:12]))
    return [l for l in joined.decode('utf-8', 'replace').split('\n') if l.strip()]


def read(root, name):
    path = os.path.join(root, 'results', 'evidence', name)
    if not os.path.isfile(path):
        if name == FILES['samples']:
            lines = parts_rejoin(root)
            if lines:
                rows = list(csv.reader(lines))
                return rows[0], rows[1:], '%s (rejoined from the ordered parts)' % path
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


def half_ulp(tok, sig=17):
    """half of the last digit the text really carries, at the precision that text was written in

    The sample blocks are 17 significant digits; the declared numbers in the judgement rows are the
    entry's own %.6g. Using the tighter grid for both would demand agreement the file never promised.
    """
    v = abs(num(tok))
    if not v:
        return 0.0
    e = math.floor(math.log10(v) + 1e-9)
    return 0.5 * 10.0 ** (e - (sig - 1))


def traj(xs, ys):
    return sum(0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))


def value(row, key):
    m = re.search(r'(?:^|\s)%s=([^ ]+)' % re.escape(key), row[5])
    return m.group(1) if m else None


def rows_of_kind(samples, kind, cid=None):
    return [r for r in samples if r[2] == kind and (cid is None or r[0] == cid)]


def declared_actual(cases, item, cid, target_part):
    out = []
    for r in cases or []:
        if r[1] == item and r[2] == cid and target_part in r[3]:
            out.append(r)
    return out


def parse_kv(text):
    return dict(re.findall(r'([A-Za-z_][\w,.]*)=([^ ]+)', text or ''))


def rebuild_deck(cid):
    cs = B.find_case(cid)
    if cs is None:
        return None
    return B.build_deck(cs, B.SECTION, gate_all=True)


def run_checks(root, quiet=False):
    failed = []
    count = [0]
    del PART_PROBLEMS[:]

    def check(name, ok, detail):
        count[0] += 1
        if not ok:
            failed.append(name)
        if not quiet:
            print('   %-66s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))
        return bool(ok)

    _h, man, p_man = read(root, FILES['manifest'])
    check('per-deck manifest exists', man is not None, p_man)
    if not man:
        print('S3B_EVIDENCE_CHECK: FAIL (no manifest)')
        return 1, failed, count[0]
    _h2, cases, p_cases = read(root, FILES['cases'])
    check('the judgement rows exist', bool(cases), '%s rows=%d' % (p_cases, len(cases or [])))
    _h3, sam, p_sam = read(root, FILES['samples'])
    check('the shipped sample blocks exist', bool(sam), '%s rows=%d' % (p_sam, len(sam or [])))
    if os.path.isfile(os.path.join(root, 'results', 'evidence', PART_INDEX)):
        check('the sample parts are the delivered bytes: each part matches its index digest and the '
              'rejoin matches the recorded whole-file digest', not PART_PROBLEMS,
              'problems=%s' % (PART_PROBLEMS[:2] or 'none'))
    _h4, idr, p_id = read(root, FILES['identity'])
    check('the identity index exists', bool(idr), '%s rows=%d' % (p_id, len(idr or [])))

    # ---------------------------------------------------------------- the case set
    decks = [r[1] for r in man]
    check('the nine declared cases are all present, exactly once',
          sorted(decks) == sorted(EXPECTED_CASES),
          'decks=%d missing=%s extra=%s' % (len(man),
                                            sorted(set(EXPECTED_CASES) - set(decks)) or 'none',
                                            sorted(set(decks) - set(EXPECTED_CASES)) or 'none'))
    runs = set(r[0] for r in man)
    check('one run_id across the batch', len(runs) == 1, 'runs=%s' % sorted(runs))
    check('the case judgement rows come from that same run',
          set(r[0] for r in cases or []) == runs, 'case_runs=%s' % sorted(set(r[0] for r in cases)))
    fault_rows = [r for r in man if r[4] == B.FAULT_MASTER]
    check('exactly one deck uses the faulted top, and it is the negative case',
          len(fault_rows) == 1 and fault_rows[0][1] == 's3b_fault_blank_to_vss_column',
          'fault_decks=%s' % [r[1] for r in fault_rows])
    check('every other deck uses the accepted top master',
          all(r[4] == B.TOP_MASTER for r in man if r[4] != B.FAULT_MASTER),
          'masters=%s' % sorted(set(r[4] for r in man)))

    # ---------------------------------------------------------------- identity and rebuilt decks
    check('every manifest row carries a 64-hex deck digest and a 12-hex digest per named master',
          all(len(r[3]) == 64 and
              all(re.match(r'^[0-9a-f]{12}$', x.split('=')[-1]) for x in r[5].split())
              for r in man), '')
    match, mismatch = 0, []
    for r in man:
        txt = rebuild_deck(r[1])
        if txt is None:
            mismatch.append((r[1], 'NO_SUCH_CASE'))
            continue
        got = hashlib.sha256(txt.encode('utf-8')).hexdigest()
        if got == r[3]:
            match += 1
        else:
            mismatch.append((r[1], got[:12] + '!=' + r[3][:12]))
    check('each deck rebuilds from the generator to the delivered hash',
          match == len(man) and not mismatch,
          'rebuilt_matched=%d/%d mismatch=%s' % (match, len(man), mismatch[:3] or 'none'))
    id_by_case = dict((r[1], r) for r in idr or [])
    check('the identity index pairs each deck with a 64-hex deck sha and a 64-hex raw sha',
          len(id_by_case) == len(man) and
          all(len(r[3]) == 64 and len(r[5]) == 64 for r in idr or []),
          'rows=%d' % len(id_by_case))
    idr_ok = all(r[1] in id_by_case and id_by_case[r[1]][3] == r[3] for r in man)
    check('the identity index agrees with the manifest on the deck digest', idr_ok,
          'rows=%d' % len(id_by_case))
    if sam:
        unlinked = [r for r in sam if r[7] != id_by_case.get(r[0], [''] * 9)[3] or
                    r[8] != id_by_case.get(r[0], [''] * 9)[5]]
        check('every sample row carries the deck and raw digests its own case was indexed with',
              bool(id_by_case) and not unlinked, 'rows=%d unlinked=%d' % (len(sam), len(unlinked)))
    check('identity paths are project-relative and free of vendor absolute paths',
          all(not r[2].startswith('/') and not r[4].startswith('/') and '/root/' not in ''.join(r)
              for r in idr or []), '')
    check('the PDK is identified by 64-hex digests only',
          bool(idr) and all(len(r[i]) == 64 for r in idr for i in (6, 7, 8, 9)),
          'digests=%s' % sorted(set(r[6][:8] for r in idr or [])))

    # ---------------------------------------------------------------- the contract, from the deck text
    gate_from_chain, no_cap, no_ideal, rails = True, True, True, True
    for r in man:
        txt = rebuild_deck(r[1]) or ''
        if 'Xtop (' not in txt or 'sc1_r3_scan_chain.scs' not in txt:
            gate_from_chain = False
        if re.search(r'Cload \(gate33', txt) or 'capacitor c=1.5' in txt:
            no_cap = False
        for n in ('q', 'qbar', 'en', 'gate33', 'bgate', 'scan'):
            if re.search(r'\bV\w+\s*\(\s*%s\s+0\s*\)' % n, txt):
                no_ideal = False
        for src in ('V18 (vdd18 0)', 'V33 (vdd33 0)', 'VSCAN (vscan 0)', 'Vss (vss 0)'):
            if src not in txt:
                rails = False
    check('gate33 exists only because the accepted chain is instantiated; nothing else drives it',
          gate_from_chain and no_ideal, 'gate_from_chain=%s no_ideal_source=%s'
          % (gate_from_chain, no_ideal))
    check('no artificial capacitance on gate33 in any delivered deck', no_cap,
          'the gate load is the seven real devices plus the measurement branch')
    check('every deck carries the four independent rails, VSCAN and V33 kept apart', rails,
          'V18/V33/VSCAN/Vss all present in all nine')
    bank_txt = B.masters_text([B.BANK_FILE])
    seven = len(re.findall(r'^\s*mp\d+ ', bank_txt, re.M))
    shapes = len(re.findall(r'^\s*mp\d+ \(scan bgate vscan vscan\) p33 l=4e-07 w=0.0001\s*$',
                            bank_txt, re.M))
    deck_ok = all(len(re.findall(r'^\s*mp\d+ ', rebuild_deck(r[1]) or '', re.M)) == 0
                  and len(re.findall(r'^Xtop ', rebuild_deck(r[1]) or '', re.M)) == 1
                  and not re.search(r'(^|\s)(nf=|m=)\d', rebuild_deck(r[1]) or '')
                  and not re.search(r'(^|\s)(nf=|m=)\d', bank_txt)
                  for r in man)
    check('the bank is seven explicit single-finger p33 at L=0.4 um, W=100 um, with no m/nf anywhere',
          seven == 7 and shapes == 7 and deck_ok,
          'bank_lines=%d exact_shape=%d ; decks hold one top instance and no device lines'
          % (seven, shapes))
    check('the device tree expands to 39 MOS (32 control + 7 bank) in every deck',
          all(r[18] == '39' for r in man), 'device_count=%s' % sorted(set(r[18] for r in man)))

    # ---------------------------------------------------------------- the dependency rcs
    check('the static supply layer accepted every deck (its own rc 7 means structure passed)',
          all(r[13] == '7' for r in man), 'static_rcs=%s' % sorted(set(r[13] for r in man)))
    check('the full preflight ran with rc 0 for every deck', all(r[14] == '0' for r in man),
          'preflight_rcs=%s' % sorted(set(r[14] for r in man)))
    check('spectre exited 0 and the runner verdict is PASS for every deck',
          all(r[15] == '0' and r[16] == 'PASS' for r in man),
          'spectre=%s runner=%s' % (sorted(set(r[15] for r in man)),
                                    sorted(set(r[16] for r in man))))
    check('the temperature the run reported is read back from the data header, not assumed',
          all(r[8] and r[8] != 'NOT_READ' for r in man),
          'values=%s' % sorted(set(r[8] for r in man)))
    check('every manifest row has the header width',
          set(len(r) for r in man) == set([len(_h)]), 'widths=%s' % sorted(set(len(r) for r in man)))
    # nothing in the delivery may be a printing artefact: no cell carries an unexpanded %% escape and
    # the saved-traces column must still name every trace this round promises, which a cut would drop
    leak = [i for i, r in enumerate([_h] + man + (cases or []) + (idr or []))
            for c in r if isinstance(c, str) and '%%' in c]
    check('no delivered cell carries an unescaped percent artefact', not leak,
          'cells=%d' % len(leak))
    promises = (['V18:i', 'V33:i', 'VSCAN:i', 'Xtop.Ip_gate:i', 'Xtop.gate33', 'Xtop.bgate',
                 'Xtop.Xchain.q', 'Xtop.Xchain.qbar', 'Xtop.Xchain.en', 'scan', 'd', 'clk',
                 'blank', 'core_ok33', 'vdd18', 'vdd33', 'vss'] +
                ['Xtop.Xbank.mp%d:%s' % (k, t) for k in range(1, B.BANK_DEVS + 1) for t in '12'])
    short = [(r[1], [p for p in promises if p not in r[20].split(',')]) for r in man]
    check('the saved-traces column is complete: every trace this delivery promises is named',
          all(not miss for _c, miss in short),
          'missing=%s' % ([x for x in short if x[1]][:1] or 'none'))
    # the refusal count must be the count of the rows that were actually refused, read across files
    if cases:
        counted = {}
        for r in cases:
            if r[6] not in ('0', '') and r[1] != 'S3B_SUPPLY_STATIC':
                counted[r[2]] = counted.get(r[2], 0) + 1
        mism = [(r[1], r[17], str(counted.get(r[1], 0))) for r in man if r[17] !=
                str(counted.get(r[1], 0))]
        check('the manifest refusal count is the number of that deck\'s own rows a strict tool '
              'refused, recomputed from the judgement file', not mism,
              'mismatch=%s deck_values=%s' % (mism[:2] or 'none',
                                              sorted(set(r[17] for r in man))))
    if cases:
        widths = set(len(r) for r in cases)
        check('every judgement row has the header width', widths == set([len(_h2)]),
              'widths=%s' % sorted(widths))
        bad = [r for r in cases if r[7] in ('FAIL', 'BLOCKED', 'NOT_DETECTED')]
        check('no functional FAIL and no dependency BLOCKED row', not bad,
              'bad=%s' % [(r[1], r[2], r[7]) for r in bad][:4])
        seen = set(r[7] for r in cases)
        check('the verdict vocabulary is the one this entry emits', seen <= VERDICTS,
              'unknown=%s' % (sorted(seen - VERDICTS) or 'none'))
    if sam:
        widths = set(len(r) for r in sam)
        check('every sample row has the header width', widths == set([len(_h3)]),
              'widths=%s' % sorted(widths))
        SAMPLE_KINDS = ('segment', 'window_full', 'window_tail_block', 'window_extreme',
                        'charge_window')
        inc, digits = True, 0
        by_block = {}
        for r in sam:
            if r[2] in SAMPLE_KINDS:
                by_block.setdefault((r[0], r[1], r[2]), []).append(r)
        for _k, blk in by_block.items():
            ts = [num(x[4]) for x in blk]
            if any(t is None for t in ts):
                inc = False
                continue
            if any(ts[i + 1] <= ts[i] for i in range(len(ts) - 1)):
                inc = False
        for r in sam:
            mant = re.sub(r'^[-+]?0*', '', r[4].split('e')[0].split('E')[0]).replace('.', '')
            digits = max(digits, len(mant))
        check('sample times are finite and strictly increasing inside every shipped block', inc,
              'blocks=%d' % len(by_block))
        check('key samples are written at full precision (>= 15 significant digits, not 6)',
              digits >= 15, 'max significant digits seen in a time token=%d' % digits)

    # ---------------------------------------------------------------- the negative case
    neg = [r for r in cases or [] if r[1] == 'S3B_FAULT_NEGATIVE']
    check('the wiring fault is recorded as DETECTED with numbers, not as a crash',
          len(neg) == 1 and neg[0][7] == 'DETECTED',
          'rows=%d verdict=%s' % (len(neg), neg[0][7] if neg else 'ABSENT'))
    refuse = [r for r in cases or [] if r[1] == 'S3B_WINDOW_STATE' and r[7] == 'EXPECTED_REFUSAL']
    check('the refused blank claim is exactly the negative case window',
          len(refuse) >= 1 and all(r[2] == 's3b_fault_blank_to_vss_column' for r in refuse),
          'refusals=%d cases=%s' % (len(refuse), sorted(set(r[2] for r in refuse))))
    full = rows_of_kind(sam or [], 'window_full', 's3b_fault_blank_to_vss_column')
    ok_full = False
    detail = 'no full window block shipped'
    if full and neg:
        vals = [num(value(r, 'gate33')) for r in full]
        vals = [v for v in vals if v is not None]
        idx = [int(r[3]) for r in full]
        want_max = num(re.search(r'max=([-0-9.eE+]+) V', neg[0][5]).group(1)) \
            if re.search(r'max=([-0-9.eE+]+) V', neg[0][5]) else None
        # the declared extreme is the judgement row's own %.6g, so its half-step is the agreement
        # the file promised -- the shipped samples are 17 digits and are not what is being compared
        tol_max = half_ulp('%g' % want_max, 6) if want_max is not None else 0.0
        ok_full = (bool(vals) and all(idx[i + 1] - idx[i] == 1 for i in range(len(idx) - 1))
                   and want_max is not None and abs(max(vals) - want_max) <= tol_max
                   and max(vals) < B.GATE_LO_MAX)
        detail = ('points=%d adjacent=%s recomputed gate33 max=%.6g V vs declared %.6g V (tol %.3g), '
                  'below the %s V conducting target so the bank really stayed on'
                  % (len(vals), all(idx[i + 1] - idx[i] == 1 for i in range(len(idx) - 1)),
                     max(vals) if vals else float('nan'), want_max or float('nan'), tol_max,
                     B.GATE_LO_MAX))
    check('the negative case re-forms from its own shipped whole window', ok_full, detail)

    # ---------------------------------------------------------------- gate charge, per case and edge
    charge_rows = [r for r in cases or [] if r[1] == 'S3B_GATE_CHARGE']
    blocks = {}
    for r in sam or []:
        if r[2] == 'charge_window':
            blocks.setdefault((r[0], r[1]), []).append(r)
    cert, problems, settle_bad = 0, [], []
    for r in charge_rows:
        cid, target = r[2], r[3]
        d = parse_kv(r[5])
        if 'via sum' not in target and 'via Xtop' not in target:
            continue
        m = re.search(r'at ([0-9.]+) ns', target)
        if not m:
            continue
        tc = float(m.group(1)) * 1e-9
        key = (cid, 'gate33_%s_at_%.3fns' % ('fall' if 'fall' in target else 'rise', tc * 1e9))
        blk = sorted(blocks.get(key, []), key=lambda x: num(x[4]))
        if len(blk) < 2:
            problems.append('%s %s: no shipped block for this charge row' % (cid, target[:40]))
            continue
        idx = [int(x[3]) for x in blk]
        ts = [num(x[4]) for x in blk]
        contiguous = all(idx[i + 1] - idx[i] == 1 for i in range(len(idx) - 1))
        increasing = all(ts[i + 1] > ts[i] for i in range(len(ts) - 1))
        covers = (ts[0] <= float(d['window'].split('..')[0]) + 1e-18 and
                  ts[-1] >= float(d['window'].split('..')[1]) - 1e-18)
        if 'sum(' in target:
            toks = [[value(x, 'mp%d_g' % k) for k in range(1, 8)] for x in blk]
            ok_sig = all(not any(g is None or not finite(g) for g in t) for t in toks)
            ys = [sum(float(g) for g in t) for t in toks] if ok_sig else []
            dy_tok = [sum(half_ulp(g) for g in t) for t in toks] if ok_sig else []
        else:
            toks = [[value(x, 'Ip_gate')] for x in blk]
            ok_sig = all(t[0] is not None and finite(t[0]) for t in toks)
            ys = [float(t[0]) for t in toks] if ok_sig else []
            dy_tok = [half_ulp(t[0]) for t in toks] if ok_sig else []
        if not ok_sig or not contiguous or not increasing or not covers:
            problems.append('%s %s: block unusable (signal=%s contiguous=%s increasing=%s covers=%s)'
                            % (cid, target[:40], ok_sig, contiguous, increasing, covers))
            continue
        raw = traj(ts, ys)
        span = ts[-1] - ts[0]
        # the same two stretch means the entry used: the first PRE_BAND of the block gives the pre
        # level, the last PRE_BAND of it gives the post level, and the step sits at t50
        pre_b = [v for (t, v) in zip(ts, ys) if t <= ts[0] + B.PRE_BAND_NS * 1e-9 + 1e-18]
        post_b = [v for (t, v) in zip(ts, ys) if t >= ts[-1] - B.PRE_BAND_NS * 1e-9 - 1e-18]
        pre_mean = sum(pre_b) / len(pre_b) if len(pre_b) >= 3 else num(d.get('pre_mean'))
        post_mean = sum(post_b) / len(post_b) if len(post_b) >= 3 else num(d.get('post_mean'))
        t50 = num(d.get('t50')) or ts[0]
        net = raw - (pre_mean * (min(t50, ts[-1]) - ts[0]) + post_mean * (ts[-1] - min(t50, ts[-1])))
        # the settle criterion behind MEASURED vs PARTIAL_EDGE_CHARGE, re-decided from the block. The
        # window and its threshold belong to the source that settled it, so the threshold is read
        # from the row and checked against the peak it names; the tail is this row's own.
        thresh = num(d.get('settle_thresh'))
        wpeak = num(d.get('window_peak'))
        if thresh is not None and wpeak is not None:
            want_thresh = max(B.CHARGE_FLOOR_A, B.SETTLE_FRACTION * wpeak)
            if abs(thresh - want_thresh) > half_ulp(d['settle_thresh'], 6) + \
                    B.SETTLE_FRACTION * half_ulp(d['window_peak'], 6):
                settle_bad.append('%s %s: settle_thresh=%.6g is not 2 %% of its own window_peak=%.6g'
                                  % (cid, target[:40], thresh, wpeak))
        tail_range = (max(post_b) - min(post_b)) if len(post_b) >= 3 else float('inf')
        settled = thresh is not None and tail_range <= thresh
        if len(pre_b) < 3 or len(post_b) < 3:
            settle_bad.append('%s %s: the shipped block has no 3-sample stretch at one end'
                              % (cid, target[:40]))
        # tolerance: the shipped tokens' own half-steps, propagated through the trapezoid, plus the
        # declared value's own printed precision -- derived from the file, not chosen to pass
        dy = dy_tok
        dx = [half_ulp(x[4]) for x in blk]
        n = len(ts)
        dt = [ts[i] - ts[i - 1] for i in range(1, n)]
        tol_y = sum(dy[k] * ((dt[k - 1] / 2 if k else 0.0) + (dt[k] / 2 if k < n - 1 else 0.0))
                    for k in range(n))
        tol_x = sum(dx[k] * (0.5 * abs(ys[0] + ys[1]) if k == 0 else
                             0.5 * abs(ys[n - 2] + ys[n - 1]) if k == n - 1 else
                             0.5 * abs(ys[k - 1] - ys[k + 1])) for k in range(n))
        base_term = (half_ulp(d.get('pre_mean', '0'), 6) + half_ulp(d.get('post_mean', '0'), 6)) * span
        tol_raw = tol_y + tol_x + half_ulp(d.get('raw_Q', '0'), 6)
        tol = tol_y + tol_x + half_ulp(d.get('net_Q', '0'), 6) + base_term
        d_raw = abs(raw - num(d['raw_Q']))
        d_net = abs(net - num(d['net_Q']))
        ceff = abs(net) / num(d['gate_swing']) if num(d.get('gate_swing')) else None
        d_ceff = abs(ceff - num(d['edge_equiv_load'])) if ceff is not None and \
            num(d.get('edge_equiv_load')) is not None else None
        if d_raw > tol_raw or d_net > tol or (d_ceff is not None and num(d.get('edge_equiv_load'))
                                              and d_ceff > tol / min(1.0, num(d['gate_swing']))):
            problems.append('%s %s: rebuilt raw=%.6g net=%.6g vs declared %.6g/%.6g tol=%.3g '
                            '(|d|=%.3g/%.3g)' % (cid, target[:40], raw, net, num(d['raw_Q']),
                                                 num(d['net_Q']), tol, d_raw, d_net))
            continue
        if r[7] == 'MEASURED' and not settled:
            settle_bad.append('%s %s: declared MEASURED while the last %g ns of its own window spans '
                              '%.3g A against a %s A threshold'
                              % (cid, target[:40], B.PRE_BAND_NS, tail_range,
                                 d.get('settle_thresh')))
        cert += 1
    check('every declared gate-edge charge rebuilds from its own case block inside the export band',
          cert > 0 and not problems,
          'certified=%d problems=%s' % (cert, problems[:3] or 'none'))
    check('a charge only claims MEASURED when the end of its own window really has settled, at the '
          'threshold the shipped peak implies', not settle_bad, 'bad=%s' % (settle_bad[:3] or 'none'))
    cross = [r for r in cases or [] if r[1] == 'S3B_GATE_CURRENT_CROSSCHECK']
    check('the terminal sum and the branch iprobe are compared, not silently swapped',
          len(cross) > 0, 'crosscheck_rows=%d' % len(cross))
    drop = [r for r in cases or [] if r[1] == 'S3B_DROP_TARGET']
    check('the conditional 0.10 V column figure is stated as conditional and reported either way',
          len(drop) >= 1 and all('CONDITIONAL' in r[4] for r in drop),
          'rows=%d verdicts=%s' % (len(drop), sorted(set(r[7] for r in drop))))
    sharing = [r for r in cases or [] if r[1] == 'S3B_DEVICE_SHARING']
    check('per-device currents are read, so the seven fingers are not assumed equal',
          len(sharing) >= 1 and all(r[7] == 'MEASURED' for r in sharing),
          'rows=%d' % len(sharing))
    zero = [r for r in cases or [] if r[1] == 'S3B_IPROBE_ZERO_DROP']
    check('the measurement branch is shown to drop no voltage (gate33 equals bgate)',
          len(zero) >= 1 and all(r[7] == 'PASS' for r in zero),
          'rows=%d verdicts=%s' % (len(zero), sorted(set(r[7] for r in zero))))
    branches = {}
    for r in cases or []:
        if r[1] == 'S3B_BRANCH_CURRENT':
            branches.setdefault(r[2], set()).add(r[3])
    three = all(set(['VSCAN:i', 'V33:i', 'V18:i']) <= v for v in branches.values())
    check('the switching rail, the control high domain and the 1.8 V domain are recorded apart',
          three and len(branches) == 9, 'cases=%d' % len(branches))
    delay_rows = [r for r in cases or [] if r[1] == 'S3B_PROPAGATION_50_50']
    ok_delay, det = recompute_delays(cases, sam)
    check('the 50%->50% numbers re-interpolate from the shipped sample pairs', ok_delay, det)
    if os.path.isfile(os.path.join(root, 'results', 'evidence', FILES['log'])):
        txt = open(os.path.join(root, 'results', 'evidence', FILES['log']), 'rb').read() \
            .decode('utf-8', 'replace')
        check('the dependency log carries a runner excerpt per deck',
              txt.count('run accepted') >= len(man), 'accepted=%d decks=%d'
              % (txt.count('run accepted'), len(man)))
        check('no vendor path survives in the dependency log', '/root/' not in txt, '')
    return (1 if failed else 0), failed, count[0]


def level_of(sig):
    if sig == 'scan':
        return B.VSCAN
    return B.R3.DOMAIN.get(sig, B.V33 if sig in ('gate33', 'bgate') else B.V18)


def crossings(rows, sig, level):
    """every interpolated crossing of `level` in the shipped adjacent samples of one signal"""
    pts = [(num(r[4]), num(value(r, sig))) for r in rows if value(r, sig) is not None]
    out = []
    for k in range(1, len(pts)):
        (t0, v0), (t1, v1) = pts[k - 1], pts[k]
        if None in (t0, v0, t1, v1) or v0 == v1:
            continue
        if (v0 - level) * (v1 - level) <= 0:
            out.append(t0 + (t1 - t0) * (level - v0) / (v1 - v0))
    return out


def _cross_matches(blk, sig, level, want):
    """does some adjacent pair in this block put `sig`'s 50% level at the declared time?"""
    cs = crossings(blk, sig, level)
    if not cs or want is None:
        return False
    near = min(cs, key=lambda c: abs(c - want))
    return abs(near - want) <= max(half_ulp('%s' % want, 9), 1e-15)


def level_of_node(sig):
    return level_of(sig)


def recompute_delays(cases, sam):
    """the two 50 % times of each judged event, re-interpolated from the adjacent samples shipped
    around them, compared with the declared time at the precision the row itself was written in"""
    rows = [r for r in (cases or []) if r[1] == 'S3B_PROPAGATION_50_50']
    if not rows or not sam:
        return False, 'no propagation rows or no samples'
    seg = {}
    lists = {}
    for r in sam:
        if r[2] == 'segment':
            seg.setdefault(r[1].split('/')[0], []).append(r)
        elif r[2] == 'event_crossing_list':
            lists[r[1]] = r
    done, bad, not_claimed = 0, [], 0
    for r in rows:
        label = r[3]
        d = parse_kv(r[5])
        t_in, t_out = num(d.get('t_in')), num(d.get('t_out'))
        delta_m = re.search(r'delta=([0-9.]+) ns', r[5])
        cl = lists.get(label)
        blk = sorted(seg.get(label, []), key=lambda x: num(x[4]))
        if t_in is None or t_out is None or not delta_m:
            not_claimed += 1        # the row refused a number; there is nothing to rebuild
            continue
        if cl is None or len(blk) < 4:
            bad.append('%s: a number is claimed but no sample block was shipped to rebuild it'
                       % label[:34])
            continue
        m = re.search(r'input (\w+) at ([^ ]+) s', cl[5])
        if not m:
            bad.append('%s: the crossing list names no input' % label[:34])
            continue
        sin = m.group(1)
        # the crossing list names several signals that crossed inside the same interval, so the output
        # is whichever shipped signal really has a 50% crossing at the row's own t_out
        present = set(re.findall(r'(?:^|\s)(\w+)=', blk[0][5]))
        levels = [(n, lv) for (n, _p, lv) in B.SHIP_NODES if n in present and lv is not None]
        ok_in = _cross_matches(blk, sin, 0.5 * level_of(sin), t_in)
        ok_out = any(n != sin and _cross_matches(blk, n, 0.5 * lv, t_out) for n, lv in levels)
        if not ok_in:
            bad.append('%s: the input %s 50%% crossing does not rebuild from the shipped pair'
                       % (label[:34], sin))
            continue
        if not ok_out:
            bad.append('%s: no shipped signal crosses its 50%% level at the declared t_out=%s'
                       % (label[:34], d.get('t_out')))
            continue
        rebuilt = (t_out - t_in) * 1e9
        if abs(rebuilt - num(delta_m.group(1))) > 5.1e-4:      # the row prints three decimals of a ns
            bad.append('%s: delta %s vs rebuilt %.4f ns' % (label[:34], delta_m.group(1), rebuilt))
            continue
        done += 1
    return done > 0 and not bad, 'rebuilt=%d refused=%d unrebuilt=%d bad=%s' % (
        done, not_claimed, len(rows) - done - not_claimed, bad[:3] or 'none')


def negatives(root=None):
    root = root or PROJ
    tmp = tempfile.mkdtemp(prefix='s3b_neg_')
    ev = os.path.join(tmp, 'results', 'evidence')
    os.makedirs(ev)
    src_dir = os.path.join(root, 'results', 'evidence')
    for name in sorted(os.listdir(src_dir)):
        if os.path.isfile(os.path.join(src_dir, name)):
            shutil.copyfile(os.path.join(src_dir, name), os.path.join(ev, name))
    ok = True
    try:
        p = os.path.join(ev, FILES['cases'])
        txt = open(p, 'rb').read().decode('utf-8')
        m = re.search(r'net_Q=([-0-9.eE+]+) C', txt)
        if not m:
            print('   A skipped: no charge row to tamper')
            ok = False
        else:
            txt2 = txt.replace(m.group(0), 'net_Q=-9.999e-09 C', 1)
            open(p, 'wb').write(txt2.encode('utf-8'))
            rc, failed, n = run_checks(tmp, quiet=True)
            caught = [f for f in failed if 'charge' in f]
            print('   A tampered net_Q %s -> -9.999e-09 C : failures=%d caught_by=%s'
                  % (m.group(1), len(failed), caught or failed[:2]))
            ok = ok and rc == 1 and bool(caught)
            open(p, 'wb').write(txt.encode('utf-8'))

        # B: one WHOLE charge block replaced by another case's block, edited inside the part that
        # carries it so every other byte of the delivery stays exactly as delivered. The realistic
        # tamper is "this case's edge charge is really somebody else's samples"; the donor has to be
        # a block whose own integral differs materially, because several cases here repeat the
        # identical first write edge and a copy of that is nothing any check could be asked to see.
        _h2, srows, _p2 = read(tmp, FILES['samples'])
        ip = os.path.join(ev, PART_INDEX)
        parts = []
        if os.path.isfile(ip):
            for line in [l for l in io.open(ip, encoding='utf-8').read().split(u'\n') if l.strip()][1:]:
                parts.append([x.strip().strip('"') for x in line.split(',')])
        plines, ptouched = {}, {}
        for f in parts:
            plines[f[0]] = io.open(os.path.join(ev, f[0]), encoding='utf-8').read().split(u'\n')
        loc = {}
        for f in parts:
            for n in range(int(f[4]), int(f[5]) + 1):
                loc[n] = (f[0], n - int(f[4]) + 1)

        def peak(idxs):
            out = [abs(v) for v in (num(value(srows[i], 'Ip_gate')) for i in idxs) if v is not None]
            return max(out) if out else 0.0

        def charge(idxs):
            pts = [(num(srows[i][4]), num(value(srows[i], 'Ip_gate'))) for i in idxs]
            pts = [p for p in pts if p[1] is not None and p[0] is not None]
            return traj([p[0] for p in pts], [p[1] for p in pts]) if len(pts) > 3 else 0.0

        groups = {}
        for i, r in enumerate(srows):
            if r[2] == 'charge_window':
                groups.setdefault((r[0], r[1]), []).append(i)
        keys = sorted(groups)
        pair = None
        for tk in keys:
            for dk in keys:
                if dk[0] == tk[0]:
                    continue
                qt, qd = charge(groups[tk]), charge(groups[dk])
                if abs(qt) > 0 and abs(qd) > 0 and abs(qd - qt) >= 0.5 * max(abs(qt), abs(qd)):
                    pair = (tk, dk, abs(peak(groups[tk])), abs(peak(groups[dk])))
                    break
            if pair:
                break
        if not pair or not loc:
            print('   B skipped: no materially different charge block pair, or no part index')
            ok = False
        else:
            (tk, dk, pt, pd) = pair
            ti, di = groups[tk], groups[dk]
            for k in range(len(ti)):
                src = loc.get(ti[k])
                donor = loc.get(di[k % len(di)])
                if not src or not donor:
                    continue
                pname, pos = src
                dname, dpos = donor
                plines[pname][pos] = plines[dname][dpos]
                ptouched[pname] = True
            for pname in ptouched:
                with io.open(os.path.join(ev, pname), 'w', encoding='utf-8', newline='') as f:
                    f.write(u'\n'.join(plines[pname]))
            rc, failed, n = run_checks(tmp, quiet=True)
            caught = [f for f in failed if 'charge' in f or 'identity' in f or 'parts' in f]
            print('   B the whole %s/%s block (%d rows, target peak %.3g A) now carries the values '
                  'of %s/%s (donor peak %.3g A), written into %s : failures=%d caught_by=%s'
                  % (tk[0], tk[1], len(ti), pt, dk[0], dk[1], pd, ','.join(sorted(ptouched)) or '-',
                     len(failed), caught or failed[:2]))
            ok = ok and rc == 1 and bool(caught)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rc, failed, n = run_checks(root, quiet=True)
    print('   C the delivered bytes as they are: rc=%d checks=%d failures=%s'
          % (rc, n, failed or 'none'))
    ok = ok and rc == 0
    print('S3B_NEGATIVE_SELFTEST: %s (a tampered charge and a cross-case splice must both be refused,'
          ' the intact delivery must pass)' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


def main():
    op = optparse.OptionParser()
    op.add_option('--root', default=PROJ)
    op.add_option('--negatives', action='store_true')
    o = op.parse_args()[0]
    if o.negatives:
        return negatives(o.root)
    rc, failed, n = run_checks(o.root)
    print('S3B_EVIDENCE_CHECK checks=%d failures=%d root=%s' % (n, len(failed), o.root))
    return rc


if __name__ == '__main__':
    sys.exit(main())
