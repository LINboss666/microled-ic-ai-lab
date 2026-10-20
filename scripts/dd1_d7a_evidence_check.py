# -*- coding: utf-8 -*-
"""DATA-7A evidence identity check -- recompute the claims from the bytes that will be committed.

    python scripts/dd1_d7a_evidence_check.py

This reads only `results/evidence/dd1_d7a_*` and the source files the manifest names. It does not
run the simulator and it does not trust any report text: it re-counts rows, re-checks uniqueness,
re-hashes every file, and refuses empty tables, duplicate or missing case ids, non-finite numbers,
blank required fields, and any manifest digest that no longer matches the bytes on disk.

A PASS here means the delivered evidence is internally consistent and traceable to the delivered
source. It does not mean the circuit is correct -- that is the reviewer's judgement.
"""
from __future__ import print_function

import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
EV = os.path.join(PROJ, 'results', 'evidence')
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import dd1_d7a_run as R                                            # noqa: E402

REQUIRED_EVIDENCE = ['dd1_d7a_cases.csv', 'dd1_d7a_control_cases.csv', 'dd1_d7a_negative.csv',
                     'dd1_d7a_edge_samples.csv', 'dd1_d7a_manifest.json',
                     'dd1_d7a_environment.json', 'dd1_d7a_checker_selftest.txt',
                     'dd1_d7a_write_guard.txt']
NUMERIC = re.compile(r'^-?\d+(\.\d+)?$')
RESERVED = ['PWM_MOS_IMPLEMENTATION', 'PAM_8LEVEL_ANALOG_IMPLEMENTATION',
            'HYBRID_CURRENT_INTEGRATION', 'GRAY_LUT_IMPLEMENTATION', 'OPTICAL_EFFECTIVE_BITS',
            'PHYSICAL_CDC_AND_SKEW', 'NEW_SPECTRE_RUNS', 'NEW_OA_WRITES', 'LAYOUT_DRC_LVS_PEX',
            'SOA_SIGNOFF']

fails = []


def note(cond, label, detail):
    print('%-6s %s: %s' % ('PASS' if cond else 'FAIL', label, detail))
    if not cond:
        fails.append(label)


def rows_of(path):
    txt = io.open(path, encoding='utf-8').read()
    lines = [l for l in txt.split('\n') if l.strip()]
    if len(lines) < 2:
        note(False, 'EMPTY_TABLE', '%s has only a header' % os.path.basename(path))
        return []
    head = lines[0].split(',')
    out = []
    for ln in lines[1:]:
        cells = split_csv(ln)
        if len(cells) != len(head):
            note(False, 'RAGGED_ROW', '%s row %s has %d cells, header has %d'
                 % (os.path.basename(path), cells[0] if cells else '?', len(cells), len(head)))
            continue
        out.append(dict(zip(head, cells)))
    return out


def split_csv(line):
    cells, cur, quoted = [], '', False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            quoted = not quoted
        elif c == ',' and not quoted:
            cells.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    cells.append(cur)
    return cells


def main():
    for name in REQUIRED_EVIDENCE:
        p = os.path.join(EV, name)
        note(os.path.exists(p) and os.path.getsize(p) > 0, 'MISSING_EVIDENCE',
             '%s exists and is non-empty' % name)
    if fails:
        print('EVIDENCE_IDENTITY: FAIL')
        return 1

    man = json.load(io.open(os.path.join(EV, 'dd1_d7a_manifest.json'), encoding='utf-8'))
    env = json.load(io.open(os.path.join(EV, 'dd1_d7a_environment.json'), encoding='utf-8'))

    # 1. every committed byte the manifest describes is still the byte it hashed
    bad = []
    for rel, h in sorted(man['sources'].items()):
        p = os.path.join(PROJ, rel.replace('/', os.sep))
        if not os.path.exists(p) or R.sha256(p) != h:
            bad.append(rel)
    note(not bad, 'SOURCE_DIGEST', '%d source files hash-match the manifest' % len(man['sources'])
         + ('' if not bad else ' ; mismatched: %s' % bad))
    bad = []
    for name, d in sorted(man['evidence'].items()):
        p = os.path.join(EV, name)
        if name == 'dd1_d7a_manifest.json':
            continue                        # a manifest cannot hash itself
        if not os.path.exists(p) or R.sha256(p) != d['sha256']:
            bad.append(name)
    note(not bad, 'EVIDENCE_DIGEST', '%d evidence files hash-match the manifest'
         % (len(man['evidence']) - 1) + ('' if not bad else ' ; mismatched: %s' % bad))

    # 2. the main matrix: row count, uniqueness, finiteness, verdicts, both instances
    rows = rows_of(os.path.join(EV, 'dd1_d7a_cases.csv'))
    ids = [r['case_id'] for r in rows]
    note(len(rows) == 1536, 'ROW_COUNT', 'main matrix rows=%d (want 1536)' % len(rows))
    note(len(set(ids)) == len(ids), 'UNIQUE_CASES', 'unique case ids=%d' % len(set(ids)))
    nones = [r['case_id'] for r in rows if r['verdict'] != 'PASS']
    note(not nones, 'VERDICT_ALL_PASS', 'non-PASS main rows=%d' % len(nones))
    pure = [r for r in rows if r['mode'] == 'PURE']
    hyb = [r for r in rows if r['mode'] == 'HYBRID']
    note(len(pure) == 512 and len(hyb) == 1024, 'MODE_SPLIT', 'PURE=%d HYBRID=%d' % (len(pure),
                                                                                     len(hyb)))
    ticks = sorted(set(r['tick_ns'] for r in rows))
    note(ticks == ['120', '200', '30', '50'], 'TICK_SET', 'tick spacings present: %s' % ticks)
    hz = sorted(set(r['frame_hz'] for r in rows))
    note(hz == ['100', '60'], 'FRAME_HZ_SET', 'example frame rates: %s' % hz)
    # a code->interval statement must be recomputable from the row itself
    bad = []
    for r in rows:
        for k in ('time_code', 'pam_code', 'tick_ns', 'exp_intervals', 'full_intervals',
                  'a_on_intervals_measured', 'a_on_width_ns', 'a_on_segments', 'a_t0_ns',
                  'b_on_intervals_measured', 'b_on_width_ns', 'b_on_segments', 'b_t0_ns',
                  'a_cfg_version', 'b_cfg_version', 'a_obs_tick_pulses', 'b_obs_tick_pulses'):
            v = r.get(k, '')
            if v == '' or not NUMERIC.match(v) or (float(v) != float(v)) or \
                    math.isinf(float(v)):
                bad.append('%s:%s=%r' % (r['case_id'], k, v))
        if len(bad) > 5:
            break
    note(not bad, 'FINITE_FIELDS', 'every measured field parses as a finite number'
         + ('' if not bad else ' ; first %s' % bad[:3]))
    bad = []
    for r in rows:
        T = int(float(r['tick_ns']))
        exp = int(float(r['exp_intervals']))
        full = int(float(r['full_intervals']))
        for pre in ('a_', 'b_'):
            segs = int(float(r[pre + 'on_segments']))
            width = int(float(r[pre + 'on_width_ns']))
            meas = int(float(r[pre + 'on_intervals_measured']))
            want_seg = 1 if exp else 0
            if segs != want_seg or width != exp * T or meas != exp:
                bad.append('%s%s exp=%d segs=%d width=%d meas=%d' % (r['case_id'], pre, exp,
                                                                     segs, width, meas))
            if int(float(r[pre + 'window_end_ns'])) - int(float(r[pre + 't0_ns'])) != full * T:
                bad.append('%s%s window endpoint off' % (r['case_id'], pre))
        if len(bad) > 5:
            break
    note(not bad, 'WIDTH_RECOMPUTABLE', 'on-width == intervals x measured tick for both instances'
         + ('' if not bad else ' ; %s' % bad[:2]))
    note(len(rows) * 2 == man['counts']['instance_observations'], 'INSTANCE_OBSERVATIONS',
         'rows x 2 = %d matches manifest %d' % (len(rows) * 2, man['counts']['instance_observations']))
    matches = len([r for r in rows if r['instances_match'] == 'PASS'])
    note(matches == len(rows), 'INSTANCES_MATCH', '%d/%d rows agree between the two channels'
         % (matches, len(rows)))

    # 3. black code and full-window behaviour must appear in the table at all
    note(any(int(float(r['exp_intervals'])) == 0 for r in rows) and
         any(int(float(r['exp_intervals'])) == 256 for r in rows) and
         any(int(float(r['exp_intervals'])) == 64 for r in rows),
         'EDGE_CODES', 'the table contains code-0, Pure-full and Hybrid-full rows')

    # 4. control and negative tables
    ctl = rows_of(os.path.join(EV, 'dd1_d7a_control_cases.csv'))
    kinds = sorted(set(r['kind'] for r in ctl if r['kind']))
    note(len(ctl) >= 24, 'CONTROL_ROWS', 'control/mixed rows=%d over %d scenario kinds'
         % (len(ctl), len(kinds)))
    unexpected = [r for r in ctl if r['verdict'] not in ('PASS',) and r['expect'] != 'refusal']
    note(not unexpected, 'CONTROL_VERDICTS',
         'control rows that failed without being declared as a required refusal: %d'
         % len(unexpected))
    ran = set(r['case_id'] for r in ctl)
    note(len(ran) >= 24, 'CONTROL_COVERAGE', '%d distinct control case ids actually executed'
         % len(ran))
    neg = rows_of(os.path.join(EV, 'dd1_d7a_negative.csv'))
    det = [r for r in neg if r['status'] == 'DETECTED' and r['class'] != 'checker_selftest']
    note(len(det) == 6, 'MUTATION_CLASSES', '%d of six mutation classes DETECTED' % len(det))
    notdet = [r['class'] for r in neg if r['status'] not in ('DETECTED',)]
    note(not notdet, 'MUTATION_ALL_DETECTED', 'not detected: %s' % (notdet or 'none'))
    nodigest = [r['class'] for r in neg if r['class'] != 'checker_selftest'
                and not re.match(r'^[0-9a-f]{64}$', r.get('mutant_rtl_sha256', ''))]
    note(not nodigest, 'MUTANT_SOURCE_DIGEST', 'each mutation records the sha256 of its real source'
         + ('' if not nodigest else ' ; missing: %s' % nodigest))

    # 5. edge samples must straddle their anchors, from the bytes alone
    smp = rows_of(os.path.join(EV, 'dd1_d7a_edge_samples.csv'))
    by = {}
    for r in smp:
        by.setdefault((r['case_id'], r['anchor'], r['signal']), []).append(int(float(r['relative_ns'])))
    bad = []
    for k, rels in sorted(by.items()):
        if not any(x < 0 for x in rels) or not any(x > 0 for x in rels) or len(rels) < 3:
            bad.append('%s' % (k,))
    note(len(by) > 0 and not bad, 'SAMPLES_STRADDLE',
         '%d (case, anchor, signal) sample sets, all with points before and after the anchor'
         % len(by) + ('' if not bad else ' ; failing: %s' % bad[:3]))
    anchors = set(r['anchor'] for r in smp)
    note('blank_abort_assert' in anchors, 'SAMPLE_ASYNC_SHUTOFF',
         'anchors present: %s' % ','.join(sorted(anchors)))
    xsig = [r for r in smp if any(c in r['value'] for c in 'xzXZ')]
    note(not xsig, 'SAMPLES_DEFINED', '%d sampled values are x/z (%s)' % (len(xsig),
                                                                          'must be none'))

    # 6. reserved statuses and the no-analog-run claim
    txt = io.open(os.path.join(EV, 'dd1_d7a_environment.json'), encoding='utf-8').read()
    for k in ('PWM_MOS_IMPLEMENTATION', 'PAM_8LEVEL_ANALOG_IMPLEMENTATION', 'NEW_SPECTRE_RUNS',
              'NEW_OA_WRITES'):
        note(k in env.get('reserved_statuses', {}) or k in txt, 'RESERVED_STATUS',
             '%s is stated in the delivered environment record' % k)
    note(env.get('spectre_runs') == 0 and env.get('oa_writes') == 0, 'NO_ANALOG_RUNS',
         'environment says spectre_runs=%s oa_writes=%s' % (env.get('spectre_runs'),
                                                            env.get('oa_writes')))
    note(env.get('four_state') is True, 'FOUR_STATE', 'the simulator is declared four-state')
    note(str(env.get('toolchain_provenance', {}).get('sha256')) == R.TOOL_SHA, 'TOOL_PROVENANCE',
         'toolchain digest recorded matches the pinned asset digest')

    print('')
    print('EVIDENCE_IDENTITY: %s (%d checks failed)' % ('PASS' if not fails else 'FAIL', len(fails)))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
