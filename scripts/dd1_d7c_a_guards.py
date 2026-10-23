#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_guards.py -- the counterexamples that prove the DATA-7C-A checks can actually fail.

Ten faults, each injected into a temporary copy of the delivered bytes (the repository is never
mutated), each with a pre-declared set of check names. A probe only passes when:

  1. the file bytes really changed, and which line changed is recorded;
  2. the baseline copy of the same tree still passes every check, so a fault cannot be credited to a
     checker that was already failing;
  3. the failure set that appears is EXACTLY the declared one -- and the declared set is never empty,
     so `[] == []` cannot be read as a detection (the mistake the DATA-7B-R3 review left as a
     follow-up, done right here instead of deferred);
  4. the reason text names the offender, so the detection is attributable to the injected net or
     device and not to a general parse complaint.

Offline only: standard library, text, no simulator, no process beyond this Python interpreter.
"""

from __future__ import absolute_import, division, print_function

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_offline_check as CHECK   # noqa: E402
import dd1_d7c_a_netlist as NL            # noqa: E402

NETLISTS = CHECK.CANDIDATE_FILES + CHECK.ACCEPTED_MASTERS + [CHECK.DECK_DRAFT]
TABLES = CHECK.INPUT_TABLES
REPORTS = [r for r in CHECK.CLAIM_FILES if r.startswith('reports/')]

# the checks that report "not evaluated" when the netlist set refuses to load
LOAD_BLOCKED = ['NETLIST_SUBSET_PARSED', 'SUBCKT_MASTERS_DEFINED', 'INSTANCE_PORT_COUNTS',
                'NO_DUPLICATE_INSTANCES', 'TOP_HAS_ONE_OUTPUT_PORT',
                'ALL_BRANCHES_ON_COMMON_OUTPUT', 'LOCAL_NODES_NOT_SHARED', 'DNW_PASS_BODY_LOCAL',
                'BLEED_GATED_BY_BRANCH_COMPLEMENT', 'MAIN_PATH_DATA_OUT_CAS_MOUT_VSS',
                'THERMO_GOLDEN_16', 'GATE_LOGIC_DERIVED_FROM_TRANSISTORS',
                'EN_ENB_PAIR_PER_BRANCH', 'DEVICE_COUNTS_DERIVED']

DEC = 'spectre/dd1_d7c_a_pam_dec.scs'
TOPF = 'spectre/dd1_d7c_a_pam_top.scs'
UNITF = 'spectre/dd1_d7c_a_sink_unit.scs'
BIASF = 'spectre/dd1_d6_bias_core.scs'
CANDIDATE_REPORT = 'reports/dd1_d7c_a_pam_candidate.md'

INJECTIONS = [
    {'id': 'E01_pam_bit_order_swapped', 'file': DEC,
     'old': 'Xn4 (data_en pam2 nn4 vdd18 vss)', 'new': 'Xn4 (data_en pam1 nn4 vdd18 vss)',
     'expect': ['THERMO_GOLDEN_16'],
     'meaning': 'bit2 wired where bit1 belongs on the always-selected branch 4 mask gate'},
    {'id': 'E02_thermometer_threshold_off_one', 'file': DEC,
     'old': 'Xsel3 (pam2 gand10 sel3 vdd18 vss)', 'new': 'Xsel3 (pam2 gor10 sel3 vdd18 vss)',
     'expect': ['THERMO_GOLDEN_16'],
     'meaning': 'select3 threshold one code too low: pam=010 would light four branches'},
    {'id': 'E03_branch_ignores_global_data_en', 'file': DEC,
     'old': 'Xn2 (data_en sel2 nn2 vdd18 vss)', 'new': 'Xn2 (vdd18 sel2 nn2 vdd18 vss)',
     'expect': ['THERMO_GOLDEN_16'],
     'meaning': 'branch 2 enabled without DATA_EN, so the eight off rows are wrong'},
    {'id': 'E04_branch_left_the_common_output', 'file': TOPF,
     'old': 'Xu7 (en7 enb7 iref_in vcas data_out vss) dd1_d7c_a_sink_unit',
     'new': 'Xu7 (en7 enb7 iref_in vcas data_out_dangling vss) dd1_d7c_a_sink_unit',
     'expect': ['ALL_BRANCHES_ON_COMMON_OUTPUT'],
     'meaning': 'one branch drains a private net: eight outputs dressed as one'},
    {'id': 'E05_shared_reference_ratio_wrong', 'file': BIASF,
     'old': 'Mref (VBIAS_SHARED VBIAS_SHARED VSS VSS) n33 l=2e-6 w=2e-5',
     'new': 'Mref (VBIAS_SHARED VBIAS_SHARED VSS VSS) n33 l=2e-6 w=2.5e-6',
     'expect': ['MIRROR_RATIO_ESTIMATED_ONLY'],
     'meaning': 'reference copied to unit width, so the 1:8 estimate silently became 1:1'},
    {'id': 'E06_dnw_pass_body_tied_to_vss', 'file': UNITF,
     'old': 'Mpass_local (VBIAS_SHARED EN vbias_ch vbias_ch) n33_dnw_4t_ckt l=2e-6 w=5e-6',
     'new': 'Mpass_local (VBIAS_SHARED EN vbias_ch VSS) n33_dnw_4t_ckt l=2e-6 w=5e-6',
     'expect': ['DNW_PASS_BODY_LOCAL', 'UNIT_CORE_ISOMORPHIC_TO_ACCEPTED'],
     'meaning': 'the DNW body pulled to the rail instead of its own source node, which is both a '
                'body-rule break and a departure from the accepted core'},
    {'id': 'E07_enb_tied_to_a_constant', 'file': DEC,
     'old': 'Xb7 (en7 enb7 vdd18 vss) dd1_inv18', 'new': 'Xb7 (vdd18 enb7 vdd18 vss) dd1_inv18',
     'expect': ['EN_ENB_PAIR_PER_BRANCH'],
     'meaning': 'branch 7 bleed device stops following its own enable'},
    {'id': 'E08_subckt_port_order_corrupted', 'file': UNITF,
     'old': 'subckt dd1_d7c_a_sink_unit (EN EN_B VBIAS_SHARED VCAS DATA_OUT VSS)',
     'new': 'subckt dd1_d7c_a_sink_unit (EN VBIAS_SHARED EN_B VCAS DATA_OUT VSS)',
     'expect': ['UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE', 'DNW_PASS_BODY_LOCAL',
                'BLEED_GATED_BY_BRANCH_COMPLEMENT'],
     'meaning': 'declaration order changed under positional bindings'},
    {'id': 'E09_stale_device_count_in_report', 'file': CANDIDATE_REPORT,
     'old': 'dd1_d7c_a_pam_1ch            145 MOS（展开）',
     'new': 'dd1_d7c_a_pam_1ch            154 MOS（展开）',
     'expect': ['REPORT_CLAIM_COUNTS_MATCH'],
     'meaning': 'a prose device count that no parse of the netlist produces'},
    {'id': 'E10_unsupported_syntax_refused', 'file': TOPF,
     'old': '  Xref (iref_in vss) data_bias_ref',
     'new': '  Rload (iref_in vss) resistor r=1k\n  Xref (iref_in vss) data_bias_ref',
     'expect': LOAD_BLOCKED,
     'meaning': 'grammar outside the documented subset is refused by name, never skipped'},
]


def stage(root, target):
    """copy the delivered bytes that the checker reads into a temp tree"""
    for rel in NETLISTS + TABLES + REPORTS:
        source = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(source):
            continue
        destination = os.path.join(target, rel.replace('/', os.sep))
        if not os.path.isdir(os.path.dirname(destination)):
            os.makedirs(os.path.dirname(destination))
        shutil.copyfile(source, destination)
    return target


def names(rep):
    return rep.failure_names()


def main(argv):
    root = ROOT
    json_path = ''
    if '--root' in argv:
        root = os.path.abspath(argv[argv.index('--root') + 1])
    if '--json' in argv:
        json_path = os.path.abspath(argv[argv.index('--json') + 1])
    rows = []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-a-guards-')
    try:
        base_dir = stage(root, os.path.join(scratch, 'baseline'))
        base = CHECK.run_checks(base_dir)
        base_failures = names(base)
        print('D7C_A_GUARDS baseline delivered_bytes_failures=%s' % (base_failures or 'none'))
        if base_failures:
            print('D7C_A_GUARDS: ABORT the baseline must pass before a fault can be credited')
            for row in base.rows:
                if row['result'] == 'FAIL':
                    print('  BASE_FAIL %s %s' % (row['check'], row['reason'][:180]))
            return 2
        for injection in INJECTIONS:
            row = probe(root, scratch, injection, base_failures)
            rows.append(row)
            print('%-38s %-5s %s' % (injection['id'], row['verdict'], row['detail'][:150]))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    hits = [r for r in rows if r['verdict'] == 'HIT']
    missed = [r['injection'] for r in rows if r['verdict'] != 'HIT']
    print('D7C_A_GUARDS: %s (%d/%d injections named exactly; not hit: %s)'
          % ('PASS' if len(hits) == len(rows) and rows else 'FAIL', len(hits), len(rows),
             ','.join(missed) or 'none'))
    if json_path:
        with io.open(json_path, 'wb') as handle:
            handle.write((json.dumps({'baseline_failures': base_failures, 'injections': rows},
                                     indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                         .encode('utf-8'))
    return 0 if len(hits) == len(rows) and rows else 1


def probe(root, scratch, injection, base_failures):
    work = os.path.join(scratch, injection['id'])
    if os.path.isdir(work):
        shutil.rmtree(work)
    stage(root, work)
    path = os.path.join(work, injection['file'].replace('/', os.sep))
    if not os.path.isfile(path):
        return {'injection': injection['id'], 'verdict': 'NOT_ATTEMPTED',
                'detail': '%s is not part of the delivered set yet' % injection['file'],
                'expected': injection['expect']}
    before = CHECK.sha_file(path)
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8').replace('\r\n', '\n')
    if text.count(injection['old']) != 1:
        return {'injection': injection['id'], 'verdict': 'NOT_ATTEMPTED',
                'detail': 'anchor appears %d time(s), injection would be ambiguous'
                          % text.count(injection['old']),
                'expected': injection['expect']}
    mutated = text.replace(injection['old'], injection['new'])
    with io.open(path, 'wb') as handle:
        handle.write(mutated.encode('utf-8'))
    after = CHECK.sha_file(path)
    original_lines = text.split('\n')
    mutated_lines = mutated.split('\n')
    width = max(len(original_lines), len(mutated_lines))
    changed_lines = [(i + 1, mutated_lines[i].strip()[:120] if i < len(mutated_lines) else '(line '
                     'removed)') for i in range(width)
                     if i >= len(original_lines) or i >= len(mutated_lines) or
                     original_lines[i] != mutated_lines[i]]
    if before == after:
        return {'injection': injection['id'], 'verdict': 'FAIL',
                'detail': 'bytes did not change, so nothing was injected',
                'expected': injection['expect']}
    rep = CHECK.run_checks(work)
    found = sorted(set(names(rep)) - set(base_failures))
    expected = sorted(injection['expect'])
    if not expected:
        verdict, detail = 'FAIL', 'an empty expectation can never be met'
    elif found == expected:
        verdict, detail = 'HIT', 'new failures exactly %s' % ','.join(found)
    else:
        verdict = 'MISS'
        detail = 'new failures %s, expected exactly %s' % (found or '[]', expected)
    reasons = ' || '.join((rep.get(name) or {}).get('reason', '')[:120] for name in expected[:2])
    return {'injection': injection['id'], 'verdict': verdict, 'detail': detail,
            'expected': expected, 'found': found, 'meaning': injection['meaning'],
            'file': injection['file'], 'digest_before': before, 'digest_after': after,
            'lines_changed': changed_lines[:3], 'offender_evidence': reasons[:400]}


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
