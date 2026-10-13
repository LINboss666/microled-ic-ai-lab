# -*- coding: utf-8 -*-
"""SCAN-1 R2E2: does the re-verification reproduce R2E's own recorded numbers? NO SIMULATION.

    python scripts/sc1_r2e2_reproduce_compare.py [--out CSV]

The round re-ran the same 15 decks of the same frozen netlist, so the interesting question is not
"did it pass again" but "is it the SAME measurement". This joins the two rounds' evidence CSVs on
(item, case, signal_or_target) and compares the numeric part of the `actual` column literally:

  * EXACT      the digit text is identical, so the simulator reproduced the same value;
  * SAME       the numbers agree inside the display band of the printed 6 significant digits;
  * DIFFERS    they do not -- reported as a finding, the old row is never overwritten;
  * ONLY_R2E / ONLY_R2E2 the question was asked in one round only (the repeated 1 pF loads and the
    two extra save forms, which R2E2 deliberately does not re-run).

Rows carrying no number (paths, node lists, prose) are compared as text. Anything that is not a
circuit measurement -- the run id, the deck path -- is skipped, because those legitimately differ.
"""
from __future__ import print_function

import csv
import io
import math
import optparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
EVID = os.path.join(PROJ, 'results', 'evidence')
QUANT = 6

PAIRS = [
    ('sc1_r2e_s2_static.csv', 'sc1_r2e2_s2_static.csv'),
    ('sc1_r2e_s2_dynamic.csv', 'sc1_r2e2_s2_dynamic.csv'),
    ('sc1_r2e_s2_dynamic_repeat3.csv', 'sc1_r2e2_s2_dynamic.csv'),
    ('sc1_r2e_s2_load.csv', 'sc1_r2e2_s2_load.csv'),
    ('sc1_r2e_s2_negative.csv', 'sc1_r2e2_s2_negative.csv'),
    ('sc1_r2e_calibration.csv', 'sc1_r2e2_calibration.csv'),
]
# the columns differ between the two entries: calibration rows are
# [item, deck, expected, actual, rc, verdict, note], S2 rows carry run_id and case as well
SKIP_ITEMS = ('DECK_IDENTITY', 'PREFLIGHT_FULL', 'SIM_RUN', 'SAVED_SIGNALS', 'SAVE_PATH_AUDIT',
              'MODEL_BINDING', 'MODEL_INCLUDE_GRAPH', 'UPLOAD_HASH_COMPARISON', 'TEMP_SYNTAX_SOURCE')
NUM = re.compile(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?')


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


def rows_of(path):
    if not os.path.isfile(path):
        return []
    return list(csv.reader([l for l in io.open(path, encoding='utf-8', newline='')]))[1:]


def shape(hdr):
    """(item, case, target, actual, verdict) column indexes for either entry's header"""
    if 'run_id' in hdr:
        return (hdr.index('item'), hdr.index('case'), hdr.index('signal_or_target'),
                hdr.index('actual'), hdr.index('verdict'))
    return (0, 1, 1, 3, 5)


def band(v):
    v = abs(float(v))
    if v == 0.0:
        return 0.0
    return 0.5 * 10 ** (math.floor(math.log10(v)) - (QUANT - 1))


def nums(text):
    out = []
    for t in NUM.findall(text or ''):
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def compare(a_old, a_new):
    """-> (verdict, detail)"""
    if a_old == a_new:
        return 'EXACT', 'digit text identical'
    n_old, n_new = nums(a_old), nums(a_new)
    if not n_old or not n_new or len(n_old) != len(n_new):
        return 'TEXT', '%s || %s' % (a_old[:40], a_new[:40])
    worst = 0.0
    for x, y in zip(n_old, n_new):
        tol = max(band(x), band(y))
        d = abs(x - y)
        if d > tol:
            worst = max(worst, d)
        else:
            worst = max(worst, 0.0)
    if worst == 0.0:
        return 'SAME', 'all %d numbers inside the %.6g display band' % (len(n_old), band(n_new[0]))
    return 'DIFFERS', 'worst absolute diff %.6g (old %s | new %s)' % (worst, a_old[:50], a_new[:50])


def key_of(item, case, target):
    """one key space for both rounds.

    R2E1 changed the calibration deck to one FILE per save form (cal_v18.scs became
    cal_v18_V18-i.scs), and R2E2 runs only the adopted form, so the bench identity is the deck stem
    without the form suffix; everything else is already addressed by (item, case, target).
    """
    c = re.sub(r'_V(18|33)-i(?=\.scs|$)', '', case)
    return (item, c, re.sub(r'_V(18|33)-i(?=\.scs|$)', '', target))


def main():
    op = optparse.OptionParser()
    op.add_option('--out')
    o, _ = op.parse_args()
    out = o.out or os.path.join(EVID, 'sc1_r2e2_native_reproduction.csv')
    hdr_out = ['item', 'case', 'signal_or_target', 'r2e_actual', 'r2e2_actual', 'comparison',
               'detail', 'r2e_verdict', 'r2e2_verdict', 'verdict']
    old, new = {}, {}
    for old_name, new_name in PAIRS:
        for fname, store in ((old_name, old), (new_name, new)):
            path = os.path.join(EVID, fname)
            if not os.path.isfile(path):
                continue
            hdr = list(csv.reader([io.open(path, encoding='utf-8', newline='').readline()]))[0]
            ii, ic, it, ia, iv = shape(hdr)
            for r in rows_of(path):
                if len(r) <= max(ii, ic, it, ia, iv) or r[ii] in SKIP_ITEMS:
                    continue
                store.setdefault(key_of(r[ii], r[ic], r[it]), []).append(
                    (r[ia], r[iv], fname))
    rows = []
    counts = {}
    for key in sorted(set(old) | set(new)):
        item, case, target = key
        if key not in new:
            rows.append([item, case, target, old[key][0][0][:90], '-', 'ONLY_R2E',
                         'a question this round deliberately does not re-run (see the 15-case list); '
                         'recorded in %s' % old[key][0][2], old[key][0][1], '-', 'NOT_RERUN'])
            counts['ONLY_R2E'] = counts.get('ONLY_R2E', 0) + 1
            continue
        if key not in old:
            rows.append([item, case, target, '-', new[key][0][0][:90], 'ONLY_R2E2',
                         'this round records it and R2E did not, under the same key', '-',
                         new[key][0][1], 'INFO'])
            counts['ONLY_R2E2'] = counts.get('ONLY_R2E2', 0) + 1
            continue
        a_old, a_new = old[key][0][0], new[key][0][0]
        v, d = compare(a_old, a_new)
        verdict = {'EXACT': 'PASS', 'SAME': 'PASS', 'TEXT': 'INFO', 'DIFFERS': 'FAIL'}[v]
        rows.append([item, case, target, a_old[:90], a_new[:90], v, d, old[key][0][1],
                     new[key][0][1], verdict])
        counts[v] = counts.get(v, 0) + 1
    lines = ['"' + '","'.join(hdr_out) + '"\n']
    for r in rows:
        lines.append('"' + '","'.join(u(x).replace('"', '""') for x in r) + '"\n')
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(''.join(lines)))
    print('R2E2_REPRODUCE %s' % ' '.join('%s=%d' % kv for kv in sorted(counts.items())))
    print('R2E2_REPRODUCE csv=%s rows=%d' % (out, len(rows)))
    for r in rows:
        if r[9] == 'FAIL':
            print('   DIFFERS %s | %s | %s: old=%s new=%s (%s)'
                  % (r[0], r[1], r[2], r[3][:44], r[4][:44], r[6][:70]))
    return 1 if any(r[9] == 'FAIL' for r in rows) else 0
    print('R2E2_REPRODUCE %s' % ' '.join('%s=%d' % kv for kv in sorted(counts.items())))
    print('R2E2_REPRODUCE csv=%s rows=%d' % (out, len(rows)))
    for r in rows:
        if r[9] == 'FAIL':
            print('   DIFFERS %s | %s | %s: old=%s new=%s (%s)'
                  % (r[0], r[1], r[2], r[3][:44], r[4][:44], r[6][:70]))
    return 1 if any(r[9] == 'FAIL' for r in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
