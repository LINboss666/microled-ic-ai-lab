#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-C section 4: the consolidated offline corrections to the S3-B record.

Zero simulations. Every number below is recomputed from bytes the reviewed commit already
carries: the fifteen waveform-sample parts plus their digest index, the delivered case table,
and the dependency log. The originals are never rewritten -- this writes one new table whose rows
name the case, the deck digest and the raw digest each statement belongs to.

Three things are corrected:

  A  sign convention. `injected = -(Vsource:i)' is the supply rule calibrated in R2E and it stays
     right for VSCAN:i, V33:i and V18:i. It was also printed on the row for `Xtop.Ip_gate:i',
     where it is wrong: an iprobe is not a supply, so its own signed reading is the branch
     current, positive from gate33 towards the bank gates (charging them) and negative on the way
     back (discharging into the driver). The raw signed values are kept exactly as delivered.

  B  precision. The delivered Ron figures were built from a source-drain drop that had already
     been rounded to six significant digits, and then printed with six more. Recomputing per
     sample from the shipped 17-digit values moves the light-load plateau from the printed
     8.00029 ohm to 7.7407 ohm and leaves the heavy-load figure at 7.9291 ohm. The declared
     conditional target (a drop below 0.10 V) is unaffected.

  C  text and state. The edge table's per-case verdicts, the R3 manual gate load (1 pF by
     default, 5 pF in r3_load5p -- not 0.2 pF), and the process accounting split into what the
     cloud can verify (the delivered batch: nine full preflights and nine DUT runs) and what only
     a local directory can say.

Usage:
  python scripts/sc1_s3c_s3b_corrections.py [--evidence DIR] [--out DIR] [--local-count N]
"""
from __future__ import print_function

import hashlib
import io
import os
import re
import sys

VSCAN_RAIL = 3.3
DROP_TARGET_V = 0.10
PARTS_RX = re.compile(r'^sc1_s3b_waveform_samples_p(\d+)\.csv$')


def read_text(path):
    return io.open(path, encoding='utf-8', errors='replace').read()


def split_row(line):
    """the delivered CSVs quote every field and never nest quotes beyond doubling"""
    out, cur, i, n, inq = [], '', 0, len(line), False
    while i < n:
        c = line[i]
        if inq:
            if c == '"' and i + 1 < n and line[i + 1] == '"':
                cur += '"'
                i += 2
                continue
            if c == '"':
                inq = False
                i += 1
                continue
            cur += c
            i += 1
            continue
        if c == '"':
            inq = True
            i += 1
            continue
        if c == ',':
            out.append(cur)
            cur = ''
            i += 1
            continue
        cur += c
        i += 1
    out.append(cur)
    return out


def read_table(path):
    lines = [l for l in read_text(path).split('\n') if l.strip() != '']
    hdr = split_row(lines[0])          # these CSVs quote the header too
    return hdr, [dict(zip(hdr, split_row(l))) for l in lines[1:]]


def numbers(payload):
    out = {}
    for k, v in re.findall(r'(\w+)=(-?[0-9][0-9.eE+-]*)', payload):
        try:
            out[k] = float(v)
        except ValueError:
            pass
    return out


def fmt(x):
    return '%.17g' % x


def rejoin_samples(ev):
    """put the fifteen delivered parts back together with the audited splitter's own rule.

    scripts/sc1_s3b_split_samples.py is the tool that cut the file and that the reviewed commit
    already vouches for, so its header/body/records helpers are reused rather than re-derived:
    a second implementation of the same split rule could disagree with the first and the whole
    point of this table is that the bytes are identical.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import sc1_s3b_split_samples as SP
    rc = SP.verify(ev)                     # per-part size and sha256 against the index
    print('S3C_PARTS_VERIFY_RC %d' % rc)
    if rc != 0:
        return None
    _, index = read_table(os.path.join(ev, SP.IDX_NAME))
    whole = dict((r['source_name'], r) for r in index)['sc1_s3b_waveform_samples.csv']
    names = sorted([n for n in os.listdir(ev) if PARTS_RX.match(n)],
                   key=lambda n: int(PARTS_RX.match(n).group(1)))
    blobs = [open(os.path.join(ev, n), 'rb').read() for n in names]
    joined = SP.header_of(blobs) + b''.join(SP.body_of(b) for b in blobs)
    return names, joined, SP.sha(joined), whole


def sample_rows(joined_text):
    lines = [l for l in joined_text.split('\n') if l.strip() != '']
    hdr = split_row(lines[0])
    return [dict(zip(hdr, split_row(l))) for l in lines[1:]]


def edge_key(actual):
    """the delivered table writes an edge two ways depending on its verdict:
         EDGE rise sig=scan t_start=...          (a measured event, direction first)
         NO_EDGE sig=scan rise: no complete ...  (no event, direction after the signal)
    Both shapes have to be read, or the per-case verdict table comes out incomplete."""
    m = re.search(r'EDGE (\w+) sig=(\S+)', actual)
    if m:
        return m.group(2), m.group(1)
    m = re.search(r'NO_EDGE sig=(\S+)\s+(rise|fall)', actual)
    if m:
        return m.group(1), m.group(2)
    return None


def main():
    args = sys.argv[1:]

    def arg(name, default):
        return args[args.index(name) + 1] if name in args else default

    root = os.environ.get('PROJ', '.')
    ev = arg('--evidence', os.path.join(root, 'results/evidence'))
    out_dir = arg('--out', ev)
    local_count = arg('--local-count', 'NOT_RECOUNTED')
    local_basis = arg('--local-basis', 'not measured this round')

    parts, joined, digest, whole = rejoin_samples(ev)
    if parts is None:
        print('S3C_CORRECTIONS: REFUSED -- the delivered sample parts do not verify, so nothing is recomputed')
        return 1
    if digest != whole['whole_sha256'] or len(joined) != int(whole['whole_bytes']):
        print('S3C_CORRECTIONS: REFUSED -- rejoining gives %s/%d bytes, the index declares %s/%s'
              % (digest[:16], len(joined), whole['whole_sha256'][:16], whole['whole_bytes']))
        return 1
    S = sample_rows(joined.decode('utf-8', 'replace'))
    _, cases = read_table(os.path.join(ev, 'sc1_s3b_cases.csv'))

    rows = []
    fails = []

    def add(kind, case, target, statement, delivered, corrected, identity, verdict):
        rows.append([kind, case, target, statement, delivered, corrected, identity, verdict])

    identity_of = {}
    for r in S:
        identity_of.setdefault(r['case'], (r['deck_sha256'], r['raw_sha256']))

    # ---- A: the iprobe sign convention
    n_probe, n_rail = 0, 0
    for r in cases:
        if r['item'] != 'S3B_BRANCH_CURRENT':
            continue
        if 'injected = -(Vsource:i)' not in r['expected']:
            continue
        is_probe = r['signal_or_target'] == 'Xtop.Ip_gate:i'
        ident = '%s/%s' % (identity_of.get(r['case'], ('?', '?'))[0][:16],
                           identity_of.get(r['case'], ('?', '?'))[1][:16])
        if is_probe:
            n_probe += 1
            add('A_IPROBE_DIRECTION', r['case'], r['signal_or_target'],
                'an iprobe is a zero-drop meter in one branch, not a supply; its signed reading is'
                ' already the branch current and positive means gate33 -> bank gate (charging the'
                ' seven gates), negative means bank gate -> gate33 (discharging back into the driver)',
                r['expected'],
                'raw signed branch current, positive = charging the bank gates, negative ='
                ' discharging into the driver; integral kept with this sign',
                'deck_raw=%s actual=%s' % (ident, r['actual']),
                'LABEL_CORRECTED')
        else:
            n_rail += 1
            add('A_RAIL_INJECTION_KEPT', r['case'], r['signal_or_target'],
                'the -Vsource:i rule is a supply-source convention and stays as delivered',
                r['expected'], 'unchanged', ident, 'KEPT')
    if n_probe != 9 or n_rail != 27:
        fails.append('expected 9 iprobe rows and 27 rail rows to relabel, got %d and %d'
                     % (n_probe, n_rail))

    # ---- B: full-precision source-drain drop and plateau Ron, per sample
    plateau = {}
    for r in S:
        if r['kind'] != 'window_tail_block':
            continue
        f = numbers(r['values'])
        if 'scan' not in f or 'VSCAN_i' not in f:
            continue
        plateau.setdefault((r['case'], r['event']), []).append((f['scan'], abs(f['VSCAN_i'])))
    ron_by_case = {}
    for key in sorted(plateau):
        pts = plateau[key]
        rons = [(VSCAN_RAIL - s) / i for s, i in pts if i > 0.0]
        if not rons:
            continue
        mean_scan = sum(s for s, _ in pts) / len(pts)
        mean_i = sum(i for _, i in pts) / len(pts)
        vsd_mean = VSCAN_RAIL - mean_scan
        ron_mean = vsd_mean / mean_i
        drop = max(VSCAN_RAIL - s for s, _ in pts)
        delivered = [r for r in cases
                     if r['item'] == 'Ron over %s' % key[1] and r['case'] == key[0]]
        ident = 'deck_sha16=%s raw_sha16=%s samples=%d..%d' % (
            identity_of.get(key[0], ('?', '?'))[0][:16],
            identity_of.get(key[0], ('?', '?'))[1][:16],
            min(int(r['sample_group_index']) for r in S
                if r['case'] == key[0] and r['event'] == key[1] and r['kind'] == 'window_tail_block'),
            max(int(r['sample_group_index']) for r in S
                if r['case'] == key[0] and r['event'] == key[1] and r['kind'] == 'window_tail_block'))
        add('B_VSD_RON_FULL_PRECISION', key[0], key[1],
            'VSD = 3.3 - scan and Ron = VSD / |VSCAN:i| computed per sample from the shipped'
            ' 17-digit values, never from a pre-rounded node voltage',
            delivered[0]['actual'] if delivered else 'NO_DELIVERED_ROW',
            'scan_mean=%s VSD_mean=%s I_mean=%s Ron_plateau=%s ohm ; per-sample Ron %s..%s ;'
            ' max drop over the plateau=%s V (target %s V)'
            % (fmt(mean_scan), fmt(vsd_mean), fmt(mean_i), fmt(ron_mean),
               fmt(min(rons)), fmt(max(rons)), fmt(drop), fmt(DROP_TARGET_V)),
            ident, 'PASS' if drop < DROP_TARGET_V else 'FAIL')
        if key[0] == 's3b_write_q1_column' and key[1] == 'selected_350':
            ron_by_case['column'] = ron_mean
        if key[0] == 's3b_write_q1_light' and key[1] == 'selected_350':
            ron_by_case['light'] = ron_mean

    # the neighbourhood of the scan extreme, stated as a recomputation reference only
    ref_current = {}
    for (case, window), pts in plateau.items():
        if window != 'selected_350':
            continue
        cond = [i for _, i in pts if i > 0]
        if cond:
            ref_current[case] = sum(cond) / len(cond)
    for case, ref in (('s3b_write_q1_light', 'light'), ('s3b_write_q1_column', 'column')):
        pts = []
        for r in S:
            if r['case'] != case:
                continue
            f = numbers(r['values'])
            if 'scan' in f and 'VSCAN_i' in f:
                pts.append((f['scan'], abs(f['VSCAN_i'])))
        mx = max(s for s, _ in pts)
        i0 = ref_current[case]
        near = [(s, i) for s, i in pts if s >= mx - 1e-6 and abs(i - i0) <= 0.2 * i0]
        rons = [(VSCAN_RAIL - s) / i for s, i in near]
        add('B_EXTREME_NEIGHBOURHOOD', case, 'scan within 1e-6 V of its maximum AND |I| within'
            ' 20 %% of the plateau current %s A' % fmt(i0),
            'recomputation reference only: NOT the range the whole-window figure has to land in,'
            ' and not a pass criterion. Samples near the extreme but still carrying the '
            'capacitive charging current are excluded by the current band, because for them the '
            'ratio is the charging path, not the on-resistance',
            'light 8.00029 / column 7.92883 as delivered',
            'Ron %s..%s ohm over %d samples (scan max %s, plateau current %s A)'
            % (fmt(min(rons)), fmt(max(rons)), len(near), fmt(mx), fmt(i0)),
            'deck_raw=%s/%s' % (identity_of[case][0][:16], identity_of[case][1][:16]), 'REFERENCE')

    # ---- C: the per-case edge verdicts the report must state
    for r in cases:
        if r['item'] != 'S3B_EDGE':
            continue
        key = edge_key(r['actual'])
        if key is None:
            continue
        add('C_EDGE_VERDICT', r['case'], '%s %s' % key,
            'what the delivered table actually says for this case and direction',
            r['verdict'], r['actual'][:220],
            'deck_raw=%s' % identity_of.get(r['case'], ('?', '?'))[0][:16] + '/'
            + identity_of.get(r['case'], ('?', '?'))[1][:16],
            'AS_DELIVERED')

    add('C_R3_GATE_LOAD', 'all R3 cases', 'the manual gate capacitance on gate33',
        'read out of the R3 entry, not from memory: scripts/sc1_r3_chain_tt.py line 411 writes'
        ' "Cload (gate33 0) capacitor c=1e-12" from the default load=1.0, line 1066 prints'
        ' load_default=1pF, and case r3_load5p (line 266) sets load=5.0',
        'the S3-B report said 0.2 pF',
        'default manual gate load 1 pF; the heavier declared load is 5 pF (r3_load5p)',
        'sc1_r3_chain_tt.py:411 :1066 :266', 'CORRECTED')

    dep = [l for l in read_text(os.path.join(ev, 'sc1_s3b_dependency_log.txt')).split('\n')
           if l.startswith('=== ')]
    kinds = {}
    for l in dep:
        kinds[re.sub(r'^=== \S+ ', '', l).split(' rc=')[0]] = \
            kinds.get(re.sub(r'^=== \S+ ', '', l).split(' rc=')[0], 0) + 1
    add('C_PROCESS_ACCOUNTING', 'delivered batch', 'cloud-verifiable process records',
        'counted in results/evidence/sc1_s3b_dependency_log.txt, which is in the reviewed commit',
        'local-side tally (readable only on the machine that ran it): %s' % local_basis,
        '%d records: %s' % (len(dep), ', '.join('%s=%d' % kv for kv in sorted(kinds.items()))),
        'sc1_s3b_dependency_log.txt sha256=%s' % hashlib.sha256(
            open(os.path.join(ev, 'sc1_s3b_dependency_log.txt'), 'rb').read()).hexdigest()[:16],
        'SPLIT')

    buf = ['kind,case,target,statement,delivered_bytes,corrected,identity,verdict']
    for r in rows:
        buf.append(','.join('"%s"' % str(v).replace('"', '""') for v in r))
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    handle = open(os.path.join(out_dir, 'sc1_s3c_s3b_corrections.csv'), 'wb')
    try:
        handle.write(('\n'.join(buf) + '\n').encode('utf-8'))
    finally:
        handle.close()

    # ---- the checks that make this table worth shipping
    if len(ron_by_case) != 2:
        fails.append('the plateau recomputation did not produce both the light and the column figure')
    if not (7.6 < ron_by_case.get('light', 0) < 7.9):
        fails.append('recomputed light plateau Ron = %r, expected inside 7.6..7.9'
                     % ron_by_case.get('light'))
    if not (7.92 < ron_by_case.get('column', 0) < 7.94):
        fails.append('recomputed column plateau Ron = %r, expected about 7.929'
                     % ron_by_case.get('column'))
    edges = {}
    for r in cases:
        if r['item'] != 'S3B_EDGE':
            continue
        key = edge_key(r['actual'])
        if key is not None:
            edges[(r['case'], '%s %s' % key)] = r['verdict']
    for want_case, want_sig, want_verdict in (
            ('s3b_write_q1_light', 'scan rise', 'PASS'),
            ('s3b_write_q1_column', 'scan fall', 'NOT_MEASURED'),
            ('s3b_blank_assert_column', 'scan fall', 'PASS')):
        got = [v for (c, s), v in edges.items() if c == want_case and s == want_sig]
        if got != [want_verdict]:
            fails.append('%s %s should read %s in the delivered table, got %r'
                         % (want_case, want_sig, want_verdict, got))

    print('S3C_CORRECTIONS_ROWS: %d' % len(rows))
    print('S3C_SAMPLE_PARTS: %d rejoined=%d bytes digest=%s index_declares=%s'
          % (len(parts), len(joined), digest[:16], whole['whole_sha256'][:16]))
    print('S3C_IPROBE_ROWS_RELABELLED: %d  S3C_RAIL_ROWS_KEPT: %d' % (n_probe, n_rail))
    print('S3C_RON_LIGHT_FULL_PRECISION: %s ohm (delivered text said 8.00029)'
          % fmt(ron_by_case.get('light', -1)))
    print('S3C_RON_COLUMN_FULL_PRECISION: %s ohm (delivered text said 7.92883)'
          % fmt(ron_by_case.get('column', -1)))
    conducting = [(VSCAN_RAIL - s) for pts in plateau.values() for s, i in pts if i > 1e-6]
    print('S3C_DROP_TARGET_MAX_V: %s over %d conducting plateau samples (conditional target %s V)'
          % (fmt(max(conducting)), len(conducting), fmt(DROP_TARGET_V)))
    print('S3C_DELIVERED_PROCESS_RECORDS: %d' % len(dep))
    for f in fails:
        print('S3C-CORRECTION-FAIL: %s' % f)
    print('S3C_S3B_CORRECTIONS: %s' % ('PASS' if not fails else 'FAIL'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
