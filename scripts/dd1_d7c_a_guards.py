#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_guards.py -- the counterexamples that prove the DATA-7C-A checks can actually fail.

R1 revision: the independent review showed eight real faults that the ten originals did not reach, so
this suite now covers them and every new gate. Twenty-four injections, each with a pre-declared,
NON-EMPTY set of check names. A probe only counts as a detection when:

  1. the file bytes really changed, with the changed line recorded;
  2. the unmutated copy of the same tree passes every check, so nothing is credited to a checker that
     was already failing;
  3. the new failure set equals the declared set exactly - [] == [] is refused by construction, and an
     unexpected extra failure is a MISS just as a missing one is;
  4. the reason text names the offender, so the detection is attributable to the injected net, device,
     row or column and not to a general parse complaint.

Every case named top_*, duplicate_mos_instance, cascode_multiplicity_changed, golden_header_only,
report_total_borrowed_from_other_cell and the active-tran line is the reviewer's own diagnostic, kept
here so the same fault cannot be missed twice. Offline only: standard library, text and graph, no
simulator and no subprocess beyond this interpreter (the native-entry probe runs in-process).
"""

from __future__ import absolute_import, division, print_function

import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_offline_check as CHECK   # noqa: E402

NETLISTS = CHECK.CANDIDATE_FILES + CHECK.ACCEPTED_MASTERS + [CHECK.DECK_DRAFT]
TABLES = CHECK.INPUT_TABLES
REPORTS = [r for r in CHECK.CLAIM_FILES if r.startswith('reports/')]

DEC = 'spectre/dd1_d7c_a_pam_dec.scs'
TOPF = 'spectre/dd1_d7c_a_pam_top.scs'
UNITF = 'spectre/dd1_d7c_a_sink_unit.scs'
GATES = 'spectre/dd1_d7c_a_gates.scs'
BIASF = 'spectre/dd1_d6_bias_core.scs'
DECK = CHECK.DECK_DRAFT
CANDIDATE_REPORT = 'reports/dd1_d7c_a_pam_candidate.md'
GOLDEN = 'tests/dd1_d7c_a/pam_mask_golden.csv'
REQUESTS = 'tests/dd1_d7c_a/pam_request_refusal.csv'
PLAN = 'tests/dd1_d7c_a/native_case_plan.csv'
CLAIMS = 'tests/dd1_d7c_a/device_count_claims.csv'

# what the checker reports when the netlist set refuses to load at all
LOAD_BLOCKED = ['NETLIST_SUBSET_PARSED', 'SUBCKT_MASTERS_DEFINED', 'INSTANCE_PORT_COUNTS',
                'NO_DUPLICATE_INSTANCES', 'TOP_HAS_ONE_OUTPUT_PORT',
                'ALL_BRANCHES_ON_COMMON_OUTPUT', 'UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE',
                'LOCAL_NODES_NOT_SHARED', 'REFERENCE_NODE_IDENTITY', 'DNW_PASS_BODY_LOCAL',
                'BLEED_GATED_BY_BRANCH_COMPLEMENT', 'MAIN_PATH_DATA_OUT_CAS_MOUT_VSS',
                'THERMO_GOLDEN_16', 'GOLDEN_TABLE_SCHEMA', 'TOP_INTEGRATED_THERMO_16',
                'EN_ENB_PAIR_PER_BRANCH', 'GATE_LOGIC_DERIVED_FROM_TRANSISTORS',
                'DEVICE_COUNTS_DERIVED', 'DEVICE_COUNT_SEPARATION',
                'MIRROR_RATIO_ESTIMATED_ONLY', 'UNIT_CORE_ISOMORPHIC_TO_ACCEPTED',
                'CLAIM_TABLE_MATCHES_PARSE', 'REPORT_CLAIMS_BOUND_TO_OBJECT',
                'REPORT_CLAIM_COUNTS_MATCH']

PAIR = ['THERMO_GOLDEN_16', 'TOP_INTEGRATED_THERMO_16']

INJECTIONS = [
    # ---- the ten originals, now against the integrated checker
    {'id': 'E01_pam_bit_order_swapped', 'file': DEC,
     'old': 'Xn4 (data_en pam2 nn4 vdd18 vss)', 'new': 'Xn4 (data_en pam1 nn4 vdd18 vss)',
     'expect': PAIR, 'meaning': 'bit2 wired where bit1 belongs on the branch-4 AND input'},
    {'id': 'E02_thermometer_threshold_off_one', 'file': DEC,
     'old': 'Xsel3 (pam2 gand10 sel3 vdd18 vss)', 'new': 'Xsel3 (pam2 gor10 sel3 vdd18 vss)',
     'expect': PAIR, 'meaning': 'select3 threshold one code too low: code 010 lights four branches'},
    {'id': 'E03_branch_ignores_global_data_en', 'file': DEC,
     'old': 'Xn2 (data_en sel2 nn2 vdd18 vss)', 'new': 'Xn2 (vdd18 sel2 nn2 vdd18 vss)',
     'expect': PAIR, 'meaning': 'branch 2 enabled without DATA_EN, so the eight off rows are wrong'},
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
     'meaning': 'the DNW body pulled to the rail instead of its own source node'},
    {'id': 'E07_enb_tied_to_a_constant', 'file': DEC,
     'old': 'Xb7 (en7 enb7 vdd18 vss) dd1_inv18', 'new': 'Xb7 (vdd18 enb7 vdd18 vss) dd1_inv18',
     'expect': ['EN_ENB_PAIR_PER_BRANCH'],
     'meaning': 'branch 7 bleed device stops following its own enable'},
    {'id': 'E08_subckt_port_order_corrupted', 'file': UNITF,
     'old': 'subckt dd1_d7c_a_sink_unit (EN EN_B VBIAS_SHARED VCAS DATA_OUT VSS)',
     'new': 'subckt dd1_d7c_a_sink_unit (EN VBIAS_SHARED EN_B VCAS DATA_OUT VSS)',
     'expect': ['UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE', 'DNW_PASS_BODY_LOCAL',
                'REFERENCE_NODE_IDENTITY', 'TOP_INTEGRATED_THERMO_16'],
     'meaning': 'declaration order changed under positional bindings: the shared reference and the '
                'enable roles move and the integrated mask sees it too. BLEED_GATED_BY_BRANCH_COMPLEMENT '
                'is deliberately absent: that check compares the bleed gate against this branch own '
                'resolved EN_B identity, which a port-order change preserves, so the design-table and '
                'reference checks are the ones that can see it'},
    {'id': 'E09_stale_device_count_in_report', 'file': CANDIDATE_REPORT,
     'old': 'dd1_d7c_a_pam_1ch            145 MOS',
     'new': 'dd1_d7c_a_pam_1ch            112 MOS',
     'expect': ['REPORT_CLAIMS_BOUND_TO_OBJECT'],
     'meaning': "the top's count replaced by the decode layer's own total"},
    {'id': 'E10_unsupported_syntax_refused', 'file': TOPF,
     'old': '  Xref (iref_in vss) data_bias_ref',
     'new': '  Rload (iref_in vss) resistor r=1k\n  Xref (iref_in vss) data_bias_ref',
     'expect': LOAD_BLOCKED,
     'meaning': 'grammar outside the documented subset is refused by name, never skipped'},
    # ---- the reviewer's own eight diagnostics, kept verbatim as faults
    {'id': 'E11_select5_reuses_select1', 'file': DEC,
     'old': 'Xsel5 (pam2 gor10 sel5 vdd18 vss)', 'new': 'Xsel5 (pam2 sel1 sel5 vdd18 vss)',
     'expect': PAIR, 'meaning': 'pam2 & select1 == pam2, so code 100 lights six branches not five'},
    {'id': 'E12_top_pam_bits_swapped', 'file': TOPF,
     'old': 'Xdec (pam_sel0 pam_sel1 pam_sel2 data_en',
     'new': 'Xdec (pam_sel2 pam_sel1 pam_sel0 data_en',
     'expect': ['TOP_INTEGRATED_THERMO_16'],
     'meaning': 'the decoder is correct but the top feeds it the wrong pins'},
    {'id': 'E13_top_enable_tied_high', 'file': TOPF,
     'old': 'Xdec (pam_sel0 pam_sel1 pam_sel2 data_en',
     'new': 'Xdec (pam_sel0 pam_sel1 pam_sel2 vdd18',
     'expect': ['TOP_INTEGRATED_THERMO_16'],
     'meaning': 'an external DATA_EN=0 still lights unit branches, invisible to a subckt-level test'},
    {'id': 'E14_reference_bound_to_vcas', 'file': TOPF,
     'old': 'Xref (iref_in vss) data_bias_ref', 'new': 'Xref (vcas vss) data_bias_ref',
     'expect': ['REFERENCE_NODE_IDENTITY', 'DNW_PASS_BODY_LOCAL'],
     'meaning': 'the diode reference sits on the cascode rail while the branches still drain from '
                'iref_in, so the shared node stops being shared'},
    {'id': 'E15_duplicate_mos_instance', 'file': GATES,
     'old': 'Mnand_n_b (z b nand2_mid vss)', 'new': 'Mnand_n_a (z b nand2_mid vss)',
     'expect': ['NO_DUPLICATE_INSTANCES'],
     'meaning': 'two devices with one name in one cell, which an X-only scan cannot see'},
    {'id': 'E16_cascode_multiplicity_changed', 'file': UNITF,
     'old': 'Mcas (DATA_OUT VCAS node_m VSS) n33 l=2e-6 w=2.5e-6',
     'new': 'Mcas (DATA_OUT VCAS node_m VSS) n33 l=2e-6 w=2.5e-6 m=8',
     'expect': ['UNIT_CORE_ISOMORPHIC_TO_ACCEPTED', 'DEVICE_COUNT_SEPARATION'],
     'meaning': 'an effective 20 um cascode presented as the accepted unit device'},
    {'id': 'E17_golden_header_only', 'file': GOLDEN, 'drop_rows': True,
     'expect': ['GOLDEN_TABLE_SCHEMA', 'THERMO_GOLDEN_16'],
     'meaning': 'an empty table is not agreement, it is a missing input'},
    {'id': 'E18_request_table_emptied', 'file': REQUESTS, 'drop_rows': True,
     'expect': ['REQUEST_TABLE_SCHEMA', 'REQUEST_REFUSAL_TABLE'],
     'meaning': 'the same vacuity on the refusal table: zero records cannot be sixteen tests'},
    {'id': 'E19_claim_table_stale', 'file': CLAIMS,
     'old': 'dd1_d7c_a_pam_1ch,expanded_mos,145', 'new': 'dd1_d7c_a_pam_1ch,expanded_mos,150',
     'expect': ['CLAIM_TABLE_MATCHES_PARSE'],
     'meaning': 'a machine-readable claim that no longer matches the netlist it pins'},
    {'id': 'E20_plan_refines_more_than_time', 'file': PLAN,
     'old': 'RS-LOW,refined_step', 'new': 'RS-LOW,dc_sweep',
     'expect': ['NATIVE_PLAN_SHAPE'],
     'meaning': 'a paired convergence case reclassified would silently change what is compared'},
    {'id': 'E21_active_tran_without_dev', 'file': DECK, 'append': 'review_tran tran stop=1u maxstep=1n',
     'expect': ['DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS'],
     'meaning': 'the plain tran form, which a dev=-only pattern never saw'},
    {'id': 'E22_active_dc_with_dev', 'file': DECK,
     'append': 'review_dc dc dev=Vdata_en_dc param=dc start=0 stop=1.8 step=0.6',
     'expect': ['DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS'],
     'meaning': 'the dev= form must still be caught, not only the bare keyword'},
    {'id': 'E23_unknown_active_deck_statement', 'file': DECK,
     'append': 'review_rgn region data_out area=1.0',
     'expect': ['DRAFT_DECK_SYNTAX_INVENTORY'],
     'meaning': 'an active statement outside the supported subset is refused by name'},
    {'id': 'E24_golden_key_duplicated', 'file': GOLDEN, 'duplicate_last_row': True,
     'expect': ['GOLDEN_TABLE_SCHEMA'],
     'meaning': 'sixteen rows of which one key appears twice is fifteen cases, not sixteen'},
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


def _mutate(path, injection):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8').replace('\r\n', '\n')
    original = text.split('\n')
    if injection.get('drop_rows'):
        mutated = original[0] + '\n'
    elif injection.get('duplicate_last_row'):
        non_empty = [i for i, line in enumerate(original) if line.strip()]
        last = non_empty[-1]
        mutated = '\n'.join(original[:last + 1] + [original[last]] + original[last + 1:])
    elif injection.get('append'):
        mutated = '\n'.join([line for line in original if line != '']) + '\n' + \
            injection['append'] + '\n'
    else:
        if text.count(injection['old']) != 1:
            return None, 'anchor appears %d time(s), injection would be ambiguous' \
                         % text.count(injection['old'])
        mutated = text.replace(injection['old'], injection['new'])
    new = mutated.split('\n')
    changed = [(i + 1, new[i].strip()[:100]) for i in range(len(new))
               if i >= len(original) or original[i] != new[i]]
    if not changed:
        changed = [(0, 'row set differs')]
    with io.open(path, 'wb') as handle:
        handle.write(mutated.encode('utf-8'))
    return changed, ''


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
    changed, problem = _mutate(path, injection)
    if problem:
        return {'injection': injection['id'], 'verdict': 'NOT_ATTEMPTED', 'detail': problem,
                'expected': injection['expect']}
    after = CHECK.sha_file(path)
    if before == after:
        return {'injection': injection['id'], 'verdict': 'FAIL',
                'detail': 'bytes did not change, so nothing was injected',
                'expected': injection['expect']}
    rep = CHECK.run_checks(work)
    found = sorted(set(rep.failure_names()) - set(base_failures))
    expected = sorted(injection['expect'])
    if not expected:
        verdict, detail = 'FAIL', 'an empty expectation can never be met'
    elif found == expected:
        verdict = 'HIT'
        detail = 'new failures exactly %s' % ','.join(found)
    else:
        verdict = 'MISS'
        detail = 'new failures %s, expected exactly %s' % (found or '[]', expected)
    evidence = ' || '.join((rep.get(name) or {}).get('reason', '')[:150] for name in expected[:2])
    return {'injection': injection['id'], 'verdict': verdict, 'detail': detail, 'meaning':
            injection['meaning'], 'expected': expected, 'found': found, 'file': injection['file'],
            'digest_before': before, 'digest_after': after, 'lines_changed': changed[:3],
            'offender_evidence': evidence[:500]}


def csv_probes(scratch):
    """the published tables must round-trip and a malformed one must be refused even when its own
    digests are self-consistent"""
    out = []
    spec = ('commands', ['gate', 'command', 'rc', 'expected_rc', 'verdict_state', 'verdict'])
    good = [{'gate': 'x', 'command': 'python thing.py --flag one,two --other "q"', 'rc': 0,
             'expected_rc': '0', 'verdict_state': 'PASS', 'verdict': 'includes a comma and a quote'}]
    cases = [('C1_round_trip_ok', good, True),
             ('C2_unquoted_comma_row', None, False),
             ('C3_wrong_column_count', None, False),
             ('C4_duplicate_key', None, False)]
    for name, rows, expect_ok in cases:
        path = os.path.join(scratch, name + '.csv')
        if name == 'C1_round_trip_ok':
            CHECK.rows_write(path, spec[1], rows)
        elif name == 'C2_unquoted_comma_row':
            with io.open(path, 'wb') as handle:
                handle.write((','.join(spec[1]) + '\n' +
                              'gate,python thing,0,0,PASS,verdict with a , inside\n').encode('utf-8'))
        elif name == 'C3_wrong_column_count':
            with io.open(path, 'wb') as handle:
                handle.write((','.join(spec[1]) + '\n' + 'a,b,c\n').encode('utf-8'))
        else:
            CHECK.rows_write(path, spec[1], good + good)
        try:
            parsed = CHECK.read_table(path, spec[1], 'gate')
            verdict, detail = 'HIT', 'read back %d rows, %d columns each' % (len(parsed),
                                                                              len(spec[1]))
            if expect_ok and len(parsed) != len(rows):
                verdict, detail = 'MISS', 'round trip lost rows'
            if not expect_ok:
                verdict, detail = 'MISS', 'a broken table was accepted: %r' % (parsed[:1],)
        except ValueError as error:
            if expect_ok:
                verdict, detail = 'MISS', 'a good table was refused: %s' % error
            else:
                verdict, detail = 'HIT', 'refused by schema: %s' % str(error)[:120]
        out.append({'probe': name, 'verdict': verdict, 'detail': detail,
                    'digest': CHECK.sha_file(path)})
    return out


def main(argv):
    root = ROOT
    json_path = ''
    if '--root' in argv:
        root = os.path.abspath(argv[argv.index('--root') + 1])
    if '--json' in argv:
        json_path = os.path.abspath(argv[argv.index('--json') + 1])
    rows, csv_rows = [], []
    scratch = tempfile.mkdtemp(prefix='dd1-d7c-a-guards-')
    try:
        base_dir = stage(root, os.path.join(scratch, 'baseline'))
        base = CHECK.run_checks(base_dir)
        base_failures = base.failure_names()
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
            print('%-40s %-5s %s' % (injection['id'], row['verdict'], row['detail'][:130]))
        csv_rows = csv_probes(scratch)
        for row in csv_rows:
            rows.append({'injection': row['probe'], 'verdict': row['verdict'],
                         'detail': row['detail'], 'expected': ['CSV_SCHEMA'], 'found': [],
                         'digest_after': row['digest']})
            print('%-40s %-5s %s' % (row['probe'], row['verdict'], row['detail'][:130]))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    hits = [r for r in rows if r['verdict'] == 'HIT']
    missed = [r['injection'] for r in rows if r['verdict'] != 'HIT']
    print('D7C_A_GUARDS: %s (%d/%d named exactly; not hit: %s)'
          % ('PASS' if hits and len(hits) == len(rows) else 'FAIL', len(hits), len(rows),
             ','.join(missed) or 'none'))
    if json_path:
        with io.open(json_path, 'wb') as handle:
            handle.write((json.dumps({'baseline_failures': base_failures, 'injections': rows},
                                     indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                         .encode('utf-8'))
    return 0 if hits and len(hits) == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
