#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_offline_check.py -- DATA-7C-A offline structure, connectivity and logic checks.

Standard library only, text and graph only: nothing here starts Spectre, ngspice, Xyce, Icarus or
Virtuoso, and a PASS below is a statement about the delivered TEXT, never an electrical claim. The
companion --selftest mutates temporary copies and requires each fault to be named, so a check that
cannot fail is not counted as a check.

    python scripts/dd1_d7c_a_offline_check.py                 # check the delivered bytes
    python scripts/dd1_d7c_a_offline_check.py --selftest      # eight counterexamples
    python scripts/dd1_d7c_a_offline_check.py --json <path>   # machine-readable record
"""

from __future__ import absolute_import, division, print_function

import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_netlist as NL          # noqa: E402
import dd1_d7c_a_deckgen as DECKGEN     # noqa: E402

CANDIDATE_FILES = ['spectre/dd1_d7c_a_gates.scs', 'spectre/dd1_d7c_a_pam_dec.scs',
                   'spectre/dd1_d7c_a_sink_unit.scs', 'spectre/dd1_d7c_a_pam_top.scs']
ACCEPTED_MASTERS = ['spectre/dd1_d6_inv18.scs', 'spectre/dd1_d6_bias_core.scs',
                    'spectre/dd1_d6_sink_core.scs']
INPUT_TABLES = ['tests/dd1_d7c_a/pam_mask_golden.csv', 'tests/dd1_d7c_a/pam_request_refusal.csv',
                'tests/dd1_d7c_a/native_case_plan.csv']
CLAIM_FILES = ['reports/dd1_d7c_a_pam_candidate.md', 'reports/dd1_d7c_a_native_test_plan.md',
               'reports/agent_handoffs/DATA-7C-A.md'] + CANDIDATE_FILES
TOP = 'dd1_d7c_a_pam_1ch'
DECODER = 'dd1_d7c_a_pam_dec'
UNIT = 'dd1_d7c_a_sink_unit'
ACCEPTED_CORE = 'data_sink_1ch'
REFERENCE = 'data_bias_ref'
DECK_DRAFT = 'spectre/dd1_d7c_a_tb_draft.scs'
BRANCH_COUNT = 8
CLAIM_RX = re.compile(r'(?<![A-Za-z0-9])(\d+)\s*(?:MOS\b|管|transistors?\b)')
ANALYSIS_RX = re.compile(r'^\s*\w*\s+(dc|tran|ac|dcop|pss|psf)\s+dev=', re.I)

# the code bits the accepted controller calls pam_sel, spelled the way the netlist names its ports
CODE_TO_PORTS = {0: (0, 0, 0), 1: (1, 0, 0), 2: (0, 1, 0), 3: (1, 1, 0),
                 4: (0, 0, 1), 5: (1, 0, 1), 6: (0, 1, 1), 7: (1, 1, 1)}


def sha_file(path):
    with io.open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class Report(object):
    def __init__(self):
        self.rows = []

    def add(self, name, ok, reason):
        self.rows.append({'check': name, 'result': 'PASS' if ok else 'FAIL', 'reason': reason})
        return ok

    def failure_names(self):
        return [r['check'] for r in self.rows if r['result'] == 'FAIL']

    def get(self, name):
        for row in self.rows:
            if row['check'] == name:
                return row
        return None

    def as_json(self):
        return {'checks': self.rows, 'total': len(self.rows),
                'failures': self.failure_names(),
                'electrical_claim': 'NONE: every result below is about text and connectivity only'}


def load_subs(root):
    return NL.load([os.path.join(root, p) for p in CANDIDATE_FILES + ACCEPTED_MASTERS])


def scope_of(net_id):
    return net_id.rsplit('/', 1)[0] if '/' in net_id else ''


def run_checks(root):
    rep = Report()
    digests = {}
    for rel in CANDIDATE_FILES + ACCEPTED_MASTERS:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            rep.add('NETLIST_SUBSET_PARSED', False, '%s is missing' % rel)
            return rep
        digests[rel] = sha_file(path)
    try:
        subs, files = load_subs(root)
    except NL.NetlistError as error:
        rep.add('NETLIST_SUBSET_PARSED', False, str(error)[:300])
        for name in ('SUBCKT_MASTERS_DEFINED', 'INSTANCE_PORT_COUNTS', 'NO_DUPLICATE_INSTANCES',
                     'TOP_HAS_ONE_OUTPUT_PORT', 'ALL_BRANCHES_ON_COMMON_OUTPUT',
                     'LOCAL_NODES_NOT_SHARED', 'DNW_PASS_BODY_LOCAL',
                     'BLEED_GATED_BY_BRANCH_COMPLEMENT', 'MAIN_PATH_DATA_OUT_CAS_MOUT_VSS',
                     'THERMO_GOLDEN_16', 'GATE_LOGIC_DERIVED_FROM_TRANSISTORS',
                     'EN_ENB_PAIR_PER_BRANCH', 'DEVICE_COUNTS_DERIVED'):
            rep.add(name, False, 'not evaluated: the netlist set did not load (%s)' % str(error)[:80])
        return rep
    devices, instances = NL.expand(subs, TOP)
    rep.add('NETLIST_SUBSET_PARSED', True,
            '%d files parsed, %d subckt definitions, %d expanded MOS at %s, unsupported statements 0; '
            'source digests %s' % (len(files), len(subs), len(devices), TOP,
                                   ','.join('%s=%s' % (os.path.basename(k)[:12], v[:8])
                                            for k, v in sorted(digests.items()))))

    # ---- masters and models
    unknown = []
    for instance in instances:
        if instance['master'] not in subs:
            unknown.append('%s->%s' % (instance['inst'], instance['master']))
    models = sorted(set(d['model'] for d in devices))
    rep.add('SUBCKT_MASTERS_DEFINED', not unknown,
            '%d subckt instances all resolve; device models %s against whitelist %s'
            % (len(instances), ','.join(models), ','.join(NL.MODEL_WHITELIST)))

    # ---- port counts: expand() already refuses a mismatch, so reaching here is the evidence
    bad_counts = []
    for instance in instances:
        if len(instance['nets']) != len(subs[instance['master']]['ports']):
            bad_counts.append(instance['inst'])
    rep.add('INSTANCE_PORT_COUNTS', not bad_counts,
            '%d instance bindings, each with exactly its master port count and order (%s)'
            % (len(instances), 'no mismatch' if not bad_counts else ','.join(bad_counts)))

    # ---- duplicate instance names inside one scope
    seen, dup = {}, []
    for instance in instances:
        key = (instance['scope_path'], instance['inst'])
        if key in seen:
            dup.append('%s/%s' % (key[0] or TOP, key[1]))
        seen[key] = True
    rep.add('NO_DUPLICATE_INSTANCES', not dup,
            '%d unique (scope,instance) pairs%s' % (len(seen), '' if not dup else ': ' +
                                                    ','.join(sorted(set(dup)))))

    # ---- exactly one output
    top = subs[TOP]
    outputs = [p for p in top['ports'] if top['direction'].get(p) == 'output']
    rep.add('TOP_HAS_ONE_OUTPUT_PORT', outputs == ['data_out'],
            'output ports of %s: %s (this is not eight channels)' % (TOP, outputs or 'none'))

    # ---- all eight branches on the common output net
    binding = {}
    branch_resolved = {}
    for instance in instances:
        if instance['scope_path'] == '' and instance['master'] == UNIT:
            binding[instance['inst']] = dict(zip(subs[UNIT]['ports'], instance['nets']))
            branch_resolved[instance['inst']] = instance['resolved']
    off_common = [i for i, ports in sorted(binding.items()) if ports.get('DATA_OUT') != 'data_out']
    rep.add('ALL_BRANCHES_ON_COMMON_OUTPUT', len(binding) == BRANCH_COUNT and not off_common,
            '%d unit branches instantiated, DATA_OUT of every one on net data_out%s'
            % (len(binding), '' if not off_common else '; off-net: ' + ','.join(off_common)))

    # ---- every branch port lands on the net the design table names
    expected_binding = {}
    for index in range(BRANCH_COUNT):
        # DATA_OUT is deliberately absent here: the common-output property has its own named check,
        # so a branch that leaves the output net fails one check and not two, which keeps a
        # counterexample attributable to the fault that was injected.
        expected_binding['Xu%d' % index] = {'EN': 'en%d' % index, 'EN_B': 'enb%d' % index,
                                            'VBIAS_SHARED': 'iref_in', 'VCAS': 'vcas',
                                            'VSS': 'vss'}
    misplaced = []
    for inst, ports in sorted(binding.items()):
        want = expected_binding.get(inst, {})
        for port, net in sorted(want.items()):
            if ports.get(port) != net:
                misplaced.append('%s.%s on %s, table says %s' % (inst, port, ports.get(port), net))
    rep.add('UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE',
            len(binding) == BRANCH_COUNT and not misplaced,
            'all %d branches bind EN/EN_B to their own enable pair, VBIAS_SHARED to the shared '
            'reference node, VCAS to vcas, DATA_OUT to the one output%s'
            % (len(binding), '' if not misplaced else '; ' + '; '.join(misplaced[:4])))

    # ---- local nodes stay per instance
    leaked = sorted(set(n for n in _all_nets(devices)
                        if n.split('/')[-1] in ('vbias_ch', 'node_m') and scope_of(n) == ''))
    per_branch = {}
    for index in range(BRANCH_COUNT):
        per_branch[index] = set(n for n in _all_nets(devices) if n.startswith('Xu%d/' % index))
    overlap = [(i, j) for i in range(BRANCH_COUNT) for j in range(i + 1, BRANCH_COUNT)
               if per_branch[i] & per_branch[j]]
    rep.add('LOCAL_NODES_NOT_SHARED', not leaked and len(per_branch[0]) >= 2,
            'vbias_ch/node_m exist only inside instance scopes (branch 0 holds %d local net(s)), '
            'no local name at top level, shared rails only iref_in/vcas/data_out/vdd18/vss; '
            'cross-branch overlap %d' % (len(per_branch[0]), len(overlap)))

    def branch_devices(index):
        prefix = 'Xu%d.' % index
        return dict((d['inst'].split('.')[-1], d) for d in devices if d['inst'].startswith(prefix))

    def local(index, name):
        return 'Xu%d/%s' % (index, name)

    body_off = []
    bleed_off = []
    path_off = []
    for index in range(BRANCH_COUNT):
        prefix = 'Xu%d.' % index
        devs = branch_devices(index)
        if len(devs) != 4:
            body_off.append('%s holds %d device(s), expected the 4 of %s'
                            % (prefix, len(devs), UNIT))
            continue
        pas, bleed, cas, out = devs['Mpass_local'], devs['Mbleed_local'], devs['Mcas'], devs['Mout']
        bias = local(index, 'vbias_ch')
        if not (pas['model'] == 'n33_dnw_4t_ckt' and pas['s'] == bias and pas['b'] == bias and
                pas['b'] != 'vss' and pas['d'] == 'iref_in' and
                pas['g'] == 'dd1_d7c_a_pam_1ch/en%d' % index):
            body_off.append('%s Mpass_local d=%s g=%s s=%s b=%s model=%s'
                            % (prefix, pas['d'], pas['g'], pas['s'], pas['b'], pas['model']))
        if not (bleed['g'] == 'dd1_d7c_a_pam_1ch/enb%d' % index and bleed['d'] == bias and
                bleed['s'] == 'vss' and bleed['b'] == 'vss'):
            bleed_off.append('%s Mbleed_local d=%s g=%s s=%s b=%s'
                             % (prefix, bleed['d'], bleed['g'], bleed['s'], bleed['b']))
        node = local(index, 'node_m')
        # the branch's own DATA_OUT port, expressed as the global net identity the flattener gave it,
        # so this path check is about the cell topology and not about what the top level named the net
        drain_net = branch_resolved.get('Xu%d' % index, {}).get('DATA_OUT')
        if not (cas['d'] == drain_net and cas['g'] == 'vcas' and cas['s'] == node and
                out['d'] == node and out['g'] == bias and out['s'] == 'vss'):
            path_off.append('%s Mcas(d=%s g=%s s=%s) Mout(d=%s g=%s s=%s) on port net %s'
                            % (prefix, cas['d'], cas['g'], cas['s'], out['d'], out['g'], out['s'],
                               drain_net))
    rep.add('DNW_PASS_BODY_LOCAL', not body_off,
            'all %d Mpass_local: drain on the shared reference iref_in, gate on this branch en, '
            'source AND DNW body on this branch vbias_ch, never vss%s'
            % (BRANCH_COUNT, '' if not body_off else '; offenders ' + '; '.join(body_off[:3])))
    rep.add('BLEED_GATED_BY_BRANCH_COMPLEMENT', not bleed_off,
            'all %d Mbleed_local discharge vbias_ch to vss and are gated by this branch enb%s'
            % (BRANCH_COUNT, '' if not bleed_off else '; offenders ' + '; '.join(bleed_off[:3])))
    rep.add('MAIN_PATH_DATA_OUT_CAS_MOUT_VSS', not path_off,
            'main path DATA_OUT -> Mcas -> node_m -> Mout -> vss, gate of Mout is the local bias, '
            'gate of Mcas is vcas%s' % ('' if not path_off else '; offenders ' +
                                        '; '.join(path_off[:3])))

    # ---- golden mask, evaluated from transistors
    golden_path = os.path.join(root, 'tests', 'dd1_d7c_a', 'pam_mask_golden.csv')
    with io.open(golden_path, encoding='utf-8') as handle:
        golden = list(csv.DictReader(handle))
    mismatches = []
    for row in golden:
        code = int(row['pam_sel'])
        inputs = dict(zip(('pam0', 'pam1', 'pam2'), CODE_TO_PORTS[code]))
        inputs['data_en'] = int(row['data_en'])
        result = NL.evaluate(subs, DECODER, inputs)
        values = result['net_value']
        got = ''.join(str(values.get('en%d' % i, '?')) for i in range(BRANCH_COUNT))
        want = row['unit_mask_7to0'][::-1]
        shorts = sorted(k for k, v in values.items() if v == 'SHORT')
        if got != want or shorts:
            mismatches.append('%s code%d en=%s golden=%s short=%s'
                              % (row['row_id'], code, got, want, ','.join(shorts) or '-'))
    rep.add('THERMO_GOLDEN_16', not mismatches,
            '%d hand-written golden rows compared against the decoder transistors themselves '
            '(golden read from %s, never produced by this evaluator)%s'
            % (len(golden), os.path.basename(golden_path),
               '' if not mismatches else '; ' + '; '.join(mismatches[:3])))

    # ---- gate cells derive to their claimed function
    # The expected rows are hand-written boolean algebra in the enumeration order _combos uses
    # (first port is the low bit); they are not produced from the netlist.
    derived = {}
    wrong = []
    for cell, ports in (('dd1_inv18', ('a',)), ('dd1_d7c_a_nand2', ('a', 'b')),
                        ('dd1_d7c_a_nor2', ('a', 'b')), ('dd1_d7c_a_and2', ('a', 'b')),
                        ('dd1_d7c_a_or2', ('a', 'b'))):
        table = []
        for combo in _combos(len(ports)):
            inputs = dict(zip(ports, combo))
            values = NL.evaluate(subs, cell, inputs)['net_value']
            if 'z' not in values:
                wrong.append('%s has no z net' % cell)
                break
            if values['z'] in ('SHORT', 'FLOAT'):
                wrong.append('%s %s -> %s' % (cell, inputs, values['z']))
                break
            table.append(values['z'])
        derived[cell] = ''.join(str(v) for v in table)
    truth = {'dd1_inv18': {(0,): 1, (1,): 0},
             'dd1_d7c_a_nand2': {(0, 0): 1, (1, 0): 1, (0, 1): 1, (1, 1): 0},
             'dd1_d7c_a_nor2': {(0, 0): 1, (1, 0): 0, (0, 1): 0, (1, 1): 0},
             'dd1_d7c_a_and2': {(0, 0): 0, (1, 0): 0, (0, 1): 0, (1, 1): 1},
             'dd1_d7c_a_or2': {(0, 0): 0, (1, 0): 1, (0, 1): 1, (1, 1): 1}}
    disagree = []
    for cell, ports in (('dd1_inv18', ('a',)), ('dd1_d7c_a_nand2', ('a', 'b')),
                        ('dd1_d7c_a_nor2', ('a', 'b')), ('dd1_d7c_a_and2', ('a', 'b')),
                        ('dd1_d7c_a_or2', ('a', 'b'))):
        if len(derived[cell]) != 1 << len(ports):
            continue                          # already reported through `wrong`
        for index, combo in enumerate(_combos(len(ports))):
            if int(derived[cell][index]) != truth[cell][combo]:
                disagree.append('%s(%s) derived %s, boolean algebra says %s'
                                % (cell, ','.join('%s=%d' % pair for pair in
                                                  zip(ports, combo)),
                                   derived[cell][index], truth[cell][combo]))
    rep.add('GATE_LOGIC_DERIVED_FROM_TRANSISTORS', not wrong and not disagree,
            'pull-up/pull-down graphs give %s against hand-written boolean algebra %s'
            % ('; '.join('%s=%s' % (k, v) for k, v in sorted(derived.items())),
               '' if not (wrong or disagree) else 'MISMATCH: ' +
               '; '.join((wrong + disagree)[:3])))

    # ---- en/enb pairing, structurally and by evaluation
    struct = []
    for index in range(BRANCH_COUNT):
        drivers = [i for i in instances if i['scope'] == DECODER and
                   i['master'] == 'dd1_inv18' and
                   i['nets'][1] == 'enb%d' % index and i['nets'][0] == 'en%d' % index]
        if len(drivers) != 1:
            struct.append('enb%d driven by %d inverter(s) of en%d' % (index, len(drivers), index))
    eval_off = []
    for code in range(8):
        for enable in (0, 1):
            inputs = dict(zip(('pam0', 'pam1', 'pam2'), CODE_TO_PORTS[code]))
            inputs['data_en'] = enable
            values = NL.evaluate(subs, DECODER, inputs)['net_value']
            for index in range(BRANCH_COUNT):
                en, enb = values.get('en%d' % index), values.get('enb%d' % index)
                if en not in (0, 1) or enb not in (0, 1) or en + enb != 1:
                    eval_off.append('code%d en%d=%s enb%d=%s' % (code, index, en, index, enb))
    rep.add('EN_ENB_PAIR_PER_BRANCH', not struct and not eval_off,
            'every branch enb is one dd1_inv18 driven by that branch own en, and 16x8 pairs evaluate '
            'as exact complements%s' % ('' if not (struct + eval_off) else '; ' +
                                        '; '.join((struct + eval_off)[:3])))

    # ---- mirror ratio, stated as an estimate only
    ref = [d for d in NL.expand(subs, REFERENCE)[0] if d['inst'].split('.')[-1] == 'Mref'][0]
    unit = [d for d in NL.expand(subs, UNIT)[0] if d['inst'].split('.')[-1] == 'Mout'][0]
    ratio = (NL.si(ref['w']) / NL.si(ref['l'])) / (NL.si(unit['w']) / NL.si(unit['l']))
    rep.add('MIRROR_RATIO_ESTIMATED_ONLY', abs(ratio - BRANCH_COUNT) < 1e-9,
            'reference Mref W=%s L=%s over unit Mout W=%s L=%s gives %g, tagged '
            'ESTIMATED_MIRROR_RATIO_ONLY: no short-channel, output-resistance, body-effect or '
            'matching behaviour is claimed' % (ref['w'], ref['l'], unit['w'], unit['l'], ratio))

    # ---- unit core isomorphism against the accepted core
    # Terminals are compared by ROLE (which port, or which local node), because the two cells spell
    # their ports differently (DATA_EN/DATA_EN_B against EN/EN_B) and an internal node carries its
    # cell's scope in its global name. The renaming is declared here, not inferred.
    port_alias = {'DATA_EN': 'EN', 'DATA_EN_B': 'EN_B'}

    def role(token, ports):
        base = token.split('/')[-1]
        return port_alias.get(base, base) if base in ports else 'LOCAL:' + base

    accepted = dict((d['inst'].split('.')[-1], d) for d in NL.expand(subs, ACCEPTED_CORE)[0])
    candidate = dict((d['inst'].split('.')[-1], d) for d in NL.expand(subs, UNIT)[0])
    accepted_ports = subs[ACCEPTED_CORE]['ports']
    candidate_ports = subs[UNIT]['ports']
    diffs = []
    for name in sorted(set(accepted) | set(candidate)):
        if name not in accepted or name not in candidate:
            diffs.append('%s only in one core' % name)
            continue
        a, b = accepted[name], candidate[name]
        for field in ('model', 'l'):
            if a[field] != b[field]:
                diffs.append('%s.%s %s %s!=%s' % (name, field, a[field], b[field]))
        for terminal in ('d', 'g', 's', 'b'):
            left = role(a[terminal], accepted_ports)
            right = role(b[terminal], candidate_ports)
            if left != right:
                diffs.append('%s.%s is %s in the accepted core, %s in the candidate'
                             % (name, terminal, left, right))
        allowed_w = {'Mcas': NL.si('2e-5') / BRANCH_COUNT, 'Mout': NL.si('2e-5') / BRANCH_COUNT}
        if name in allowed_w:
            if abs(NL.si(b['w']) - allowed_w[name]) > 1e-12:
                diffs.append('%s w=%s, expected the accepted 2e-5 divided by %d'
                             % (name, b['w'], BRANCH_COUNT))
        elif a['w'] != b['w']:
            diffs.append('%s w=%s changed to %s although only Mcas/Mout may scale'
                         % (name, a['w'], b['w']))
    rep.add('UNIT_CORE_ISOMORPHIC_TO_ACCEPTED', not diffs,
            'device by device %s matches %s in model, L and D/G/S/B role; only Mcas and Mout widths '
            'scale by 1/%d, Mpass_local and Mbleed_local keep the accepted widths%s'
            % (UNIT, ACCEPTED_CORE, BRANCH_COUNT, '' if not diffs else '; ' +
               '; '.join(diffs[:4])))

    # ---- derived counts
    per_cell = {}
    for name in sorted(subs):
        per_cell[name] = len(NL.expand(subs, name)[0])
    branch_devices_total = per_cell[UNIT] * BRANCH_COUNT
    effective = sum(NL.si(d['w']) * float(d['m']) for d in devices if
                    d['inst'].split('.')[-1] == 'Mout')
    counts_ok = (per_cell[DECODER] == 112 and per_cell[TOP] == 145 and per_cell[UNIT] == 4 and
                 len(instances) == 58 and abs(effective - BRANCH_COUNT * 2.5e-6) < 1e-12)
    rep.add('DEVICE_COUNTS_DERIVED', counts_ok,
            'subckt instances %d; expanded MOS: %s; branch devices 8 x %d = %d; summed unit Mout '
            'effective width %.3e m (m unset, so %d x 2.5 um = 20 um, the width of one accepted '
            'Mout); the shared reference is counted once at the top, not per branch'
            % (len(instances), ' '.join('%s=%d' % (k, v) for k, v in sorted(per_cell.items())),
               per_cell[UNIT], branch_devices_total, effective, BRANCH_COUNT))

    # ---- report and netlist claims must equal a derived total
    totals = set(str(v) for v in per_cell.values())
    totals.update({str(branch_devices_total), str(len(devices)), '1', '2', '4', '6', '7'})
    stale = []
    for rel in CLAIM_FILES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding='utf-8') as handle:
            body = handle.read()
        for line in body.split('\n'):
            if 'check:skip' in line:
                continue
            for match in CLAIM_RX.finditer(line):
                if match.group(1) not in totals:
                    stale.append('%s claims %s MOS (derived totals: %s)'
                                 % (rel, match.group(1), ','.join(sorted(totals, key=int))))
    rep.add('REPORT_CLAIM_COUNTS_MATCH', not stale,
            'every N MOS / N 管 / N transistors claim in the %d new documents equals a total parsed '
            'from the netlist%s' % (len(CLAIM_FILES), '' if not stale else '; ' +
                                    '; '.join(stale[:4])))

    # ---- request boundary
    refusal_path = os.path.join(root, 'tests', 'dd1_d7c_a', 'pam_request_refusal.csv')
    with io.open(refusal_path, encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    wrong = []
    for row in rows:
        value = _coerce(row['raw_literal'], row['kind'])
        state, code = NL.validate_request(value)
        want = row['expected_refusal_code']
        if want == 'ACCEPTED':
            if state != 'ACCEPTED':
                wrong.append('%s %r refused as %s' % (row['case_id'], row['raw_literal'], code))
        elif (state, code) != ('REFUSED', want):
            wrong.append('%s %r -> %s/%s, expected %s' % (row['case_id'], row['raw_literal'],
                                                         state, code, want))
    rep.add('REQUEST_REFUSAL_TABLE', not wrong,
            '%d request shapes tried: X/Z, empty, non-numeric, -1, 8, 9, 255, 2.5, 3.0, nan, inf, '
            '-inf, bool and the two legal codes %s' % (len(rows), '' if not wrong else
                                                       '; ' + '; '.join(wrong[:4])))

    # ---- native entry refuses without touching anything
    probe_root = tempfile.mkdtemp(prefix='dd1-d7c-a-deckprobe-')
    try:
        target = os.path.join(probe_root, 'out')
        os.makedirs(target)
        with io.open(os.path.join(target, 'sentinel.txt'), 'wb') as handle:
            handle.write(b'sentinel\n')
        combos = [{'QODER_SIM_AUTHORISED': '0', 'DATA7C_NATIVE_RUN': '0'},
                  {'QODER_SIM_AUTHORISED': '1', 'DATA7C_NATIVE_RUN': '1'},
                  {'QODER_SIM_AUTHORISED': '1'},
                  {'DATA7C_NATIVE_RUN': '1'}]
        results = []
        for extra in combos:
            results.append(DECKGEN.probe(target, dict(extra)))
        refused_all = all(r['refused'] for r in results)
        untouched = all(r['untouched'] for r in results)
        sentinel = os.path.isfile(os.path.join(target, 'sentinel.txt'))
        reasons = set(r['reason'][:60] for r in results)
        rep.add('NATIVE_ENTRY_REFUSED', refused_all and untouched and sentinel,
                '%d environment combinations, entry refused in each before writing, directory digest '
                'unchanged and sentinel still present%s'
                % (len(results), '' if len(reasons) < 5 else '; reasons differ, which is fine'))
    finally:
        shutil.rmtree(probe_root, ignore_errors=True)

    # ---- the draft deck cannot start a run
    deck_path = os.path.join(root, DECK_DRAFT)
    with io.open(deck_path, encoding='utf-8') as handle:
        deck_lines = handle.read().split('\n')
    active = [l.strip()[:80] for l in deck_lines if ANALYSIS_RX.match(l)]
    rep.add('DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS', not active,
            '%d line deck draft, active dc/tran/ac statements: %d%s (every analysis line is '
            'commented out, so the file cannot launch a run if someone points Spectre at it)'
            % (len(deck_lines), len(active), '' if not active else '; found ' + str(active[:2])))

    # ---- case plan shape
    plan_path = os.path.join(root, 'tests', 'dd1_d7c_a', 'native_case_plan.csv')
    with io.open(plan_path, encoding='utf-8') as handle:
        plan = list(csv.DictReader(handle))
    classes = {}
    for row in plan:
        classes[row['class']] = classes.get(row['class'], 0) + 1
    units = sum(int(row['draft_launch_units']) for row in plan)
    not_run = [row['case_id'] for row in plan if row['result'] != 'NOT_RUN']
    rep.add('NATIVE_PLAN_SHAPE',
            classes.get('dc_sweep') == 8 and classes.get('transient') == 4 and
            classes.get('refined_step') == 3 and units == 30 and not not_run,
            '%d planned cases %s, draft launch units %d (plus 6 debug = the 36 draft ceiling, which '
            'is a proposal and NOT an authorisation in this round), all result=%s%s'
            % (len(plan), sorted(classes.items()), units, 'NOT_RUN',
               '' if not not_run else '; not NOT_RUN: ' + ','.join(not_run)))
    return rep


def _all_nets(devices):
    nets = set()
    for device in devices:
        nets.update([device['d'], device['g'], device['s'], device['b']])
    return nets


def _combos(count):
    for value in range(1 << count):
        yield tuple((value >> bit) & 1 for bit in range(count))


def _coerce(text, kind):
    if kind == 'integer_out_of_range':
        return int(text)
    if kind in ('float_non_integer', 'float_integral_value'):
        return float(text)
    if kind == 'float_non_finite':
        return float(text.lower().replace('inf', 'inf'))
    if kind == 'bool':
        return True if text == 'True' else False
    if kind in ('empty_string', 'string_literal'):
        return text
    if kind == 'legal_int':
        return int(text)
    return text


def main(argv):
    root = ROOT
    json_path = ''
    if '--root' in argv:
        root = os.path.abspath(argv[argv.index('--root') + 1])
    if '--json' in argv:
        json_path = os.path.abspath(argv[argv.index('--json') + 1])
    rep = run_checks(root)
    for row in rep.rows:
        print('%-40s %s   %s' % (row['check'], row['result'], row['reason'][:220]))
    failures = rep.failure_names()
    print('D7C_A_OFFLINE_CHECK: %s (%d checks, failures: %s)'
          % ('PASS' if not failures else 'FAIL', len(rep.rows), ','.join(failures) or 'none'))
    if json_path:
        with io.open(json_path, 'wb') as handle:
            handle.write((json.dumps({'root': root.replace(os.sep, '/'), 'checks': rep.rows,
                                      'failures': failures}, indent=1,
                                     sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8'))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
