#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_offline_check.py -- DATA-7C-A offline structure, connectivity and logic checks.

R1 revision. Standard library only: nothing here starts Spectre, ngspice, Xyce, Icarus or Virtuoso, and
a PASS below is a statement about the delivered TEXT, never an electrical claim.

What changed after the independent review, and why each change has its own counterexample:

  * integration. The mask check used to drive the decoder subckt's own ports, which cannot see a wrong
    top-level binding, so three real faults (Xdec bit swap, Xdec enable tied high, Xref moved onto vcas)
    stayed invisible. TOP_INTEGRATED_THERMO_16 now feeds the top's pins, follows the ACTUAL Xdec port
    binding, and reads the en/enb nets back out to the branch terminals; REFERENCE_NODE_IDENTITY expands
    Xref and compares the diode node against the net every unit pass device actually shares. The
    per-subcell checks stay, they are just no longer mistaken for integration.
  * identity. Duplicate detection used to walk X instances only; now M devices and X instances are both
    checked per cell scope, since one identifier space is what the netlist syntax has.
  * parameters. The isomorphism check compared model/L/terminals but not m, so an m=8 on the cascode was
    invisible. It now compares every effective parameter (implicit m normalises to 1) and the counting
    report separates netlist statements, hierarchy instances, multiplicity, finger parameters and
    effective width instead of mixing them.
  * empty tables. A golden file reduced to its header used to satisfy the mask check with "0 rows, no
    mismatch". Both the golden table and the request table now have a schema gate: exactly 16 unique
    keys, closed alphabet and value domains, named refusals for empty, missing, duplicate, extra and
    illegal rows.
  * report numbers. A device count used to pass if its number equalled ANY cell's total, so the top's
    145 could be replaced by the decoder's 112. Claims are now bound to the object they name, in both
    directions on the line, and a machine-readable claim table pins object, counting kind and value.
  * the deck. The active-analysis test required `dev=`, which is only one of the accepted forms, so a
    plain `review_tran tran stop=1u maxstep=1n` was invisible. Analysis detection no longer depends on
    dev=, and a second gate inventories every active statement so anything unrecognised is refused
    rather than skipped. The wording stays at "the draft has no active analysis statements": whether a
    process would start is controlled by the entry authorisation gate, not by a comment.
"""

from __future__ import absolute_import, division, print_function

import csv
import hashlib
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

import dd1_d7c_a_netlist as NL          # noqa: E402
import dd1_d7c_a_deckgen as DECKGEN     # noqa: E402

CANDIDATE_FILES = ['spectre/dd1_d7c_a_gates.scs', 'spectre/dd1_d7c_a_pam_dec.scs',
                   'spectre/dd1_d7c_a_sink_unit.scs', 'spectre/dd1_d7c_a_pam_top.scs']
ACCEPTED_MASTERS = ['spectre/dd1_d6_inv18.scs', 'spectre/dd1_d6_bias_core.scs',
                    'spectre/dd1_d6_sink_core.scs']
INPUT_TABLES = ['tests/dd1_d7c_a/pam_mask_golden.csv', 'tests/dd1_d7c_a/pam_request_refusal.csv',
                'tests/dd1_d7c_a/native_case_plan.csv',
                'tests/dd1_d7c_a/device_count_claims.csv']
CLAIM_FILES = ['reports/dd1_d7c_a_pam_candidate.md', 'reports/dd1_d7c_a_native_test_plan.md',
               'reports/agent_handoffs/DATA-7C-A.md', 'reports/dd1_d7c_a_review_fix_r1.md'] + \
    CANDIDATE_FILES
TOP = 'dd1_d7c_a_pam_1ch'
DECODER = 'dd1_d7c_a_pam_dec'
UNIT = 'dd1_d7c_a_sink_unit'
ACCEPTED_CORE = 'data_sink_1ch'
REFERENCE = 'data_bias_ref'
DECK_DRAFT = 'spectre/dd1_d7c_a_tb_draft.scs'
BRANCH_COUNT = 8
CLAIM_RX = re.compile(r'(?<![A-Za-z0-9])(\d+)\s*(?:MOS\b|管|transistors?\b)')
ANALYSIS_WORDS = ('dc', 'tran', 'ac', 'dcop', 'pss', 'psf', 'noise', 'gx', 'pss1')
ANALYSIS_RX = re.compile(r'^\s*[A-Za-z_]\w*\s+(?:%s)(?:\s|$)' % '|'.join(ANALYSIS_WORDS), re.I)
DECK_STATEMENT_RX = {
    'simulator': re.compile(r'^\s*simulator\b', re.I),
    'include': re.compile(r'^\s*include\b', re.I),
    'parameters': re.compile(r'^\s*parameters\b', re.I),
    'save': re.compile(r'^\s*save\b', re.I),
    'source': re.compile(r'^\s*[vViI]\w*\s*\(', re.I),
    'probe': re.compile(r'^\s*I\w*\s*\([^)]*\)\s*iprobe\b', re.I),
    'instance': re.compile(r'^\s*[xX]\w*\s*\([^)]*\)\s*\w+\s*$', re.I),
}
GOLDEN_KEYS = set((e, c) for e in (0, 1) for c in range(8))
REFUSAL_CODES = ('REQUEST_UNPARSED', 'REQUEST_OUT_OF_RANGE', 'REQUEST_NOT_INT',
                 'REQUEST_NOT_FINITE', 'ACCEPTED')


def sha_file(path):
    with io.open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def rows_write(path, header, rows):
    """the one CSV writer this round uses: standard library, real quoting, LF line endings

    The published R1 tables were built by joining strings with commas, so a verdict containing a comma
    silently became extra columns and the file no longer matched its own header. Nothing may bypass
    this writer, and read_table below is what proves the result.
    """
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(list(header))
        for row in rows:
            writer.writerow([str(row.get(column, '')).replace('\n', ' ').strip()
                             for column in header])
    return path


def read_table(path, header, unique_key=None, optional=(), allow_empty=False):
    """read a published table back strictly and refuse anything that does not match its schema

    Empty is refused everywhere except in the columns a caller declares genuinely optional, so
    "paired_case is empty for a DC row" is legal while "a whole column went missing" is not. A table
    that is nothing but its header is refused too: that is the shape the review pointed at when a
    golden table with zero rows still reported "16 combinations tested".
    """
    if not os.path.isfile(path):
        raise ValueError('%s is missing' % path)
    with io.open(path, encoding='utf-8', newline='') as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError('%s is empty, which is not a table with zero rows' % path)
    if rows[0] != list(header):
        raise ValueError('%s header is %s, expected %s' % (path, rows[0], list(header)))
    if len(rows) == 1 and not allow_empty:
        raise ValueError('%s declares the header %s and has no data rows at all'
                         % (path, ','.join(header)))
    parsed = []
    seen = set()
    for number, row in enumerate(rows[1:], 2):
        if len(row) != len(header):
            raise ValueError('%s line %d has %d columns, the header declares %d'
                             % (path, number, len(row), len(header)))
        record = dict(zip(header, row))
        for column in header:
            if not str(record[column]).strip() and column not in optional:
                raise ValueError('%s line %d leaves %s empty' % (path, number, column))
        if unique_key:
            key = record.get(unique_key)
            if key in seen:
                raise ValueError('%s repeats %s=%s' % (path, unique_key, key))
            seen.add(key)
        parsed.append(record)
    return parsed


def read_rows(path):
    if not os.path.isfile(path):
        return None, 'missing'
    with io.open(path, encoding='utf-8') as handle:
        text = handle.read()
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows, text


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


def load_subs(root):
    return NL.load([os.path.join(root, p) for p in CANDIDATE_FILES + ACCEPTED_MASTERS])


def net_id(top_ports, name):
    """how the flattener names a net written inside the top cell"""
    return name if name in top_ports else '%s/%s' % (TOP, name)


def deck_statements(path):
    """classify every active (non-comment) line of the deck draft"""
    with io.open(path, encoding='utf-8') as handle:
        lines = handle.read().replace('\r\n', '\n').split('\n')
    active = []
    for number, raw in enumerate(lines, 1):
        line = NL.strip_comment(raw)
        if not line.strip():
            continue
        active.append((number, line))
    return active


def main_checks(root, rep):
    subs, files = load_subs(root)
    devices, instances = NL.expand(subs, TOP)
    top = subs[TOP]
    top_ports = top['ports']

    # ---- identifiers: one namespace per cell, both M and X
    identifiers = {}
    dup = []
    for cell in sorted(subs):
        seen = [device['inst'] for device in subs[cell]['mos']] + \
               [instance['inst'] for instance in subs[cell]['subs']]
        for name in seen:
            key = (cell, name)
            if key in identifiers:
                dup.append('%s/%s' % (cell, name))
            identifiers[key] = True
    rep.add('NO_DUPLICATE_INSTANCES', not dup,
            '%d (cell,identifier) pairs across M devices and X instances in %d definitions%s'
            % (len(identifiers), len(subs),
               '' if not dup else '; duplicates ' + ','.join(sorted(set(dup))[:4])))

    # ---- the top's one output and the branch bindings
    outputs = [p for p in top_ports if top['direction'].get(p) == 'output']
    rep.add('TOP_HAS_ONE_OUTPUT_PORT', outputs == ['data_out'],
            'output ports of %s: %s (this is not eight channels)' % (TOP, outputs or 'none'))
    binding, branch_resolved, units = {}, {}, {}
    for instance in instances:
        if instance['scope_path'] == '' and instance['master'] == UNIT:
            binding[instance['inst']] = dict(zip(subs[UNIT]['ports'], instance['nets']))
            branch_resolved[instance['inst']] = instance['resolved']
            units[instance['inst']] = instance
    off_common = [i for i, ports in sorted(binding.items()) if ports.get('DATA_OUT') != 'data_out']
    rep.add('ALL_BRANCHES_ON_COMMON_OUTPUT', len(binding) == BRANCH_COUNT and not off_common,
            '%d unit branches instantiated, DATA_OUT of every one on net data_out%s'
            % (len(binding), '' if not off_common else '; off-net: ' + ','.join(off_common)))
    expected_binding = {}
    for index in range(BRANCH_COUNT):
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
            'reference node, VCAS to vcas%s' % (len(binding),
                                                '' if not misplaced else '; ' +
                                                '; '.join(misplaced[:4])))

    # ---- local nodes
    all_nets = set()
    for device in devices:
        all_nets.update([device['d'], device['g'], device['s'], device['b']])
    leaked = sorted(set(n for n in all_nets
                        if n.split('/')[-1] in ('vbias_ch', 'node_m') and '/' not in n and
                        n not in top_ports))
    per_branch = {}
    for index in range(BRANCH_COUNT):
        per_branch[index] = set(n for n in all_nets if n.startswith('Xu%d/' % index))
    overlap = [(i, j) for i in range(BRANCH_COUNT) for j in range(i + 1, BRANCH_COUNT)
               if per_branch[i] & per_branch[j]]
    rep.add('LOCAL_NODES_NOT_SHARED', not leaked and len(per_branch[0]) >= 2,
            'vbias_ch/node_m exist only inside instance scopes (branch 0 holds %d local net(s)), no '
            'local name at top level, cross-branch overlap %d' % (len(per_branch[0]), len(overlap)))

    # ---- the shared reference identity, read from the real top expansion
    xref = [i for i in instances if i['scope_path'] == '' and i['master'] == REFERENCE]
    ref_devices = [d for d in devices if d['inst'] == 'Xref.Mref']
    ref_problems = []
    shared = None
    if len(xref) != 1 or len(ref_devices) != 1:
        ref_problems.append('Xref/Mref count %d/%d' % (len(xref), len(ref_devices)))
    else:
        mref = ref_devices[0]
        if mref['d'] != mref['g']:
            ref_problems.append('Mref is not diode connected (d=%s g=%s)' % (mref['d'], mref['g']))
        shared = mref['d']
        if mref['s'] != 'vss' or mref['b'] != 'vss':
            ref_problems.append('Mref S=%s B=%s, both must be vss' % (mref['s'], mref['b']))
        expected_ref = net_id(top_ports, binding.get('Xu0', {}).get('VBIAS_SHARED', ''))
        if shared != expected_ref:
            ref_problems.append('the diode node is %s while the top binds VBIAS_SHARED to %s'
                                % (shared, expected_ref))
        drift = [i for i in sorted(binding) if net_id(top_ports, binding[i]['VBIAS_SHARED'])
                 != shared]
        if drift:
            ref_problems.append('branches %s do not share that reference node' % ','.join(drift))
    if ref_problems:
        reason = 'reference identity broken: %s' % '; '.join(ref_problems[:3])
    else:
        reason = ('Xref expands to one diode-connected Mref whose D=G node is the net every unit '
                  'pass device drains from (%s), with S=B=vss' % shared)
    rep.add('REFERENCE_NODE_IDENTITY', not ref_problems, reason)
    return subs, devices, instances, top, top_ports, binding, branch_resolved, units, shared


def logic_checks(root, rep, subs, devices, instances, top, top_ports, binding, branch_resolved,
                 units, shared_reference):
    # ---- golden table schema first: an empty or partial table must not read as agreement
    golden, _ = read_rows(os.path.join(root, 'tests', 'dd1_d7c_a', 'pam_mask_golden.csv'))
    schema = []
    keys = set()
    if golden is None:
        schema.append('golden table file missing')
        golden = []
    if len(golden) != 16:
        schema.append('%d data rows, the schema is exactly 16 (2 enables x 8 codes)' % len(golden))
    for row in golden:
        try:
            enable, code = int(row['data_en']), int(row['pam_sel'])
        except (TypeError, ValueError, KeyError):
            schema.append('%s has a non-integer enable or code' % row.get('row_id', '?'))
            continue
        if enable not in (0, 1) or code not in range(8):
            schema.append('%s carries enable=%s code=%s outside {0,1} x {0..7}'
                          % (row.get('row_id', '?'), enable, code))
            continue
        key = (enable, code)
        if key in keys:
            schema.append('duplicate key %s' % (key,))
        keys.add(key)
        mask = row.get('unit_mask_7to0', '')
        if len(mask) != 8 or set(mask) - set('01'):
            schema.append('%s mask %r is not 8 characters of 0/1' % (row.get('row_id', '?'), mask))
            continue
        bits = [int(row.get('en%d' % j, -1)) for j in range(8)]
        if any(b not in (0, 1) for b in bits) or bits != [int(c) for c in mask[::-1]]:
            schema.append('%s en0..en7 disagree with its own mask column' % row.get('row_id', '?'))
        if int(row.get('branches_on', -1)) != sum(bits):
            schema.append('%s branches_on %s != popcount %d'
                          % (row.get('row_id', '?'), row.get('branches_on'), sum(bits)))
    missing = sorted(GOLDEN_KEYS - keys)
    extra = sorted(keys - GOLDEN_KEYS)
    if missing:
        schema.append('missing keys %s' % missing[:4])
    if extra:
        schema.append('illegal keys %s' % extra[:4])
    rep.add('GOLDEN_TABLE_SCHEMA', not schema,
            'golden table has %d rows over the 16 unique (enable,code) keys, masks of 8 characters of '
            '0/1, en0..en7 consistent with the mask and branches_on equal to the popcount%s'
            % (len(golden), '' if not schema else '; refusals: ' + '; '.join(schema[:4])))

    # ---- mask comparison, still driven by the hand-written rows
    mismatches = []
    for row in golden:
        if (int(row['data_en']), int(row['pam_sel'])) not in GOLDEN_KEYS:
            continue
        given = decoder_inputs(subs, row)
        if given is None:
            mismatches.append('%s: decoder port binding unreadable' % row['row_id'])
            continue
        values = NL.evaluate(subs, DECODER, given)['net_value']
        got = ''.join(str(values.get('en%d' % j, '?')) for j in range(8))
        want = row['unit_mask_7to0'][::-1]
        shorts = sorted(k for k, v in values.items() if v == 'SHORT')
        if got != want or shorts:
            mismatches.append('%s code%s en=%s golden=%s short=%s'
                              % (row['row_id'], row['pam_sel'], got, want, ','.join(shorts) or '-'))
    rep.add('THERMO_GOLDEN_16', bool(golden) and not mismatches,
            '%d hand-written golden rows compared against the decoder transistors themselves, never '
            'generated by this evaluator%s' % (len(golden),
                                               '' if not mismatches else '; ' +
                                               '; '.join(mismatches[:3])))

    # ---- integration: the top's own pins, through the actual Xdec binding, back to the branches
    xdec = [i for i in top['subs'] if i['master'] == DECODER]
    integ = []
    cells = 0
    if len(xdec) != 1:
        integ.append('top has %d Xdec instances' % len(xdec))
    else:
        bind = dict(zip(subs[DECODER]['ports'], xdec[0]['nets']))
        rails = {'vdd18': 1, 'vss': 0}
        for row in golden:
            if (int(row['data_en']), int(row['pam_sel'])) not in GOLDEN_KEYS:
                continue
            cells += 1
            code, enable = int(row['pam_sel']), int(row['data_en'])
            level = dict(rails, **{'data_en': enable, 'pam_sel0': code & 1,
                                   'pam_sel1': (code >> 1) & 1, 'pam_sel2': (code >> 2) & 1})
            given = {}
            for port in ('pam0', 'pam1', 'pam2', 'data_en'):
                net = bind.get(port)
                if net not in level:
                    integ.append('%s: decoder port %s is bound to %s, which is not a top pin or rail'
                                 % (row['row_id'], port, net))
                    given = None
                    break
                given[port] = level[net]
            if given is None:
                continue
            values = NL.evaluate(subs, DECODER, given)['net_value']
            mask = ''.join(str(values.get('en%d' % j, '?')) for j in range(8))
            want = row['unit_mask_7to0'][::-1]
            if mask != want:
                integ.append('%s through the real Xdec binding (top pin map %s) gives %s, golden says '
                             '%s' % (row['row_id'], bind, mask, want))
                continue
            for index in range(8):
                want_net = net_id(top_ports, bind['en%d' % index])
                want_b = net_id(top_ports, bind['enb%d' % index])
                if binding['Xu%d' % index]['EN'] != bind['en%d' % index] or \
                        binding['Xu%d' % index]['EN_B'] != bind['enb%d' % index]:
                    integ.append('Xu%d EN/EN_B are not the decoder outputs of branch %d'
                                 % (index, index))
                if branch_resolved['Xu%d' % index].get('EN') != want_net or \
                        branch_resolved['Xu%d' % index].get('EN_B') != want_b:
                    integ.append('Xu%d resolves EN to %s, expected %s'
                                 % (index, branch_resolved['Xu%d' % index].get('EN'), want_net))
    rep.add('TOP_INTEGRATED_THERMO_16', not integ,
            '%d top-level enable/code combinations driven from the top pins, through the actual Xdec '
            'port binding, and read back at each branch EN/EN_B terminal (decoder port map %s)%s'
            % (cells, bind if len(xdec) == 1 else '-', '' if not integ else '; ' +
               '; '.join(integ[:2])[:300]))

    # ---- gate cells derive to their claimed function, from transistors
    rep_gate = derive_gate_logic(rep, subs)

    # ---- EN / EN_B pairing, structural and evaluated
    struct = []
    for index in range(BRANCH_COUNT):
        drivers = [i for i in instances if i['scope'] == DECODER and i['master'] == 'dd1_inv18' and
                   i['nets'][1] == 'enb%d' % index and i['nets'][0] == 'en%d' % index]
        if len(drivers) != 1:
            struct.append('enb%d driven by %d inverter(s) of en%d' % (index, len(drivers), index))
    eval_off = []
    for code in range(8):
        for enable in (0, 1):
            values = NL.evaluate(subs, DECODER, {'pam0': code & 1, 'pam1': (code >> 1) & 1,
                                                 'pam2': (code >> 2) & 1,
                                                 'data_en': enable})['net_value']
            for index in range(8):
                en, enb = values.get('en%d' % index), values.get('enb%d' % index)
                if en not in (0, 1) or enb not in (0, 1) or en + enb != 1:
                    eval_off.append('code%d en%d=%s enb%d=%s' % (code, index, en, index, enb))
    rep.add('EN_ENB_PAIR_PER_BRANCH', not struct and not eval_off,
            'every branch enb is one dd1_inv18 driven by that branch own en, and 16x8 pairs evaluate '
            'as exact complements%s' % ('' if not (struct + eval_off) else '; ' +
                                        '; '.join((struct + eval_off)[:3])))

    # ---- per-branch terminal walk on the expanded netlist
    def branch_devices(index):
        prefix = 'Xu%d.' % index
        return dict((d['inst'].split('.')[-1], d) for d in devices if d['inst'].startswith(prefix))

    body_off, bleed_off, path_off = [], [], []
    for index in range(BRANCH_COUNT):
        prefix = 'Xu%d.' % index
        devs = branch_devices(index)
        if len(devs) != 4:
            body_off.append('%s holds %d device(s), expected the 4 of %s' % (prefix, len(devs), UNIT))
            continue
        pas, bleed, cas, out = devs['Mpass_local'], devs['Mbleed_local'], devs['Mcas'], devs['Mout']
        bias = 'Xu%d/vbias_ch' % index
        node = 'Xu%d/node_m' % index
        if not (pas['model'] == 'n33_dnw_4t_ckt' and pas['s'] == bias and pas['b'] == bias and
                pas['b'] != 'vss' and pas['d'] == shared_reference and
                pas['g'] == branch_resolved['Xu%d' % index]['EN']):
            body_off.append('%s Mpass_local d=%s g=%s s=%s b=%s model=%s'
                            % (prefix, pas['d'], pas['g'], pas['s'], pas['b'], pas['model']))
        if not (bleed['g'] == branch_resolved['Xu%d' % index]['EN_B'] and bleed['d'] == bias and
                bleed['s'] == 'vss' and bleed['b'] == 'vss'):
            bleed_off.append('%s Mbleed_local d=%s g=%s s=%s b=%s'
                             % (prefix, bleed['d'], bleed['g'], bleed['s'], bleed['b']))
        drain = branch_resolved['Xu%d' % index]['DATA_OUT']
        if not (cas['d'] == drain and cas['g'] == branch_resolved['Xu%d' % index]['VCAS'] and
                cas['s'] == node and out['d'] == node and out['g'] == bias and out['s'] == 'vss'):
            path_off.append('%s Mcas(d=%s g=%s s=%s) Mout(d=%s g=%s s=%s)'
                            % (prefix, cas['d'], cas['g'], cas['s'], out['d'], out['g'], out['s']))
    rep.add('DNW_PASS_BODY_LOCAL', not body_off,
            'all %d Mpass_local: drain on the shared reference node, gate on this branch en, source '
            'AND DNW body on this branch vbias_ch, never vss%s'
            % (BRANCH_COUNT, '' if not body_off else '; offenders ' + '; '.join(body_off[:3])))
    rep.add('BLEED_GATED_BY_BRANCH_COMPLEMENT', not bleed_off,
            'all %d Mbleed_local discharge vbias_ch to vss and are gated by this branch enb%s'
            % (BRANCH_COUNT, '' if not bleed_off else '; offenders ' + '; '.join(bleed_off[:3])))
    rep.add('MAIN_PATH_DATA_OUT_CAS_MOUT_VSS', not path_off,
            'main path DATA_OUT -> Mcas -> node_m -> Mout -> vss per branch, gate of Mout is the local '
            'bias, gate of Mcas is the branch VCAS terminal%s'
            % ('' if not path_off else '; offenders ' + '; '.join(path_off[:3])))
    return rep_gate


def decoder_inputs(subs, row):
    code, enable = int(row['pam_sel']), int(row['data_en'])
    return {'pam0': code & 1, 'pam1': (code >> 1) & 1, 'pam2': (code >> 2) & 1,
            'data_en': enable}


def derive_gate_logic(rep, subs):
    derived, wrong = {}, []
    cells = (('dd1_inv18', ('a',)), ('dd1_d7c_a_nand2', ('a', 'b')),
             ('dd1_d7c_a_nor2', ('a', 'b')), ('dd1_d7c_a_and2', ('a', 'b')),
             ('dd1_d7c_a_or2', ('a', 'b')))
    for cell, ports in cells:
        table = []
        for combo in _combos(len(ports)):
            values = NL.evaluate(subs, cell, dict(zip(ports, combo)))['net_value']
            if 'z' not in values:
                wrong.append('%s has no z net' % cell)
                break
            if values['z'] in ('SHORT', 'FLOAT'):
                wrong.append('%s %s -> %s' % (cell, combo, values['z']))
                break
            table.append(values['z'])
        derived[cell] = ''.join(str(v) for v in table)
    truth = {'dd1_inv18': {(0,): 1, (1,): 0},
             'dd1_d7c_a_nand2': {(0, 0): 1, (1, 0): 1, (0, 1): 1, (1, 1): 0},
             'dd1_d7c_a_nor2': {(0, 0): 1, (1, 0): 0, (0, 1): 0, (1, 1): 0},
             'dd1_d7c_a_and2': {(0, 0): 0, (1, 0): 0, (0, 1): 0, (1, 1): 1},
             'dd1_d7c_a_or2': {(0, 0): 0, (1, 0): 1, (0, 1): 1, (1, 1): 1}}
    disagree = []
    for cell, ports in cells:
        if len(derived[cell]) != 1 << len(ports):
            continue
        for index, combo in enumerate(_combos(len(ports))):
            if int(derived[cell][index]) != truth[cell][combo]:
                disagree.append('%s(%s) derived %s, boolean algebra says %s'
                                % (cell, combo, derived[cell][index], truth[cell][combo]))
    rep.add('GATE_LOGIC_DERIVED_FROM_TRANSISTORS', not wrong and not disagree,
            'pull-up/pull-down graphs give %s against hand-written boolean algebra%s'
            % ('; '.join('%s=%s' % (k, v) for k, v in sorted(derived.items())),
               '' if not (wrong or disagree) else '; MISMATCH ' + '; '.join((wrong + disagree)[:3])))
    return derived


def counting_checks(rep, subs, devices, instances, root):
    per_cell = dict((name, len(NL.expand(subs, name)[0])) for name in subs)
    statement_count = sum(len(subs[c]['mos']) for c in subs)
    multiplicity = sum(int(NL.resolve_symbol(subs[d['scope']], d['m'])) for d in devices)
    explicit_m = sorted(set('%s.%s' % (cell, device['inst'])
                           for cell in subs for device in subs[cell]['mos'] if device['m'] != '1'))
    effective = {}
    for device in devices:
        model = device['model']
        effective[model] = effective.get(model, 0.0) + \
            NL.si(device['w']) * float(NL.resolve_symbol(subs[device['scope']], device['m']))
    counts_ok = (per_cell[DECODER] == 112 and per_cell[TOP] == 145 and per_cell[UNIT] == 4 and
                 per_cell[REFERENCE] == 1 and len(instances) == 58)
    rep.add('DEVICE_COUNTS_DERIVED', counts_ok,
            'expanded MOS per cell %s; subckt instances %d%s'
            % (' '.join('%s=%d' % (k, per_cell[k]) for k in sorted(per_cell)), len(instances),
               '' if counts_ok else '; expected 145/112/4/1 and 58 instances'))
    rep.add('DEVICE_COUNT_SEPARATION', multiplicity == len(devices) and not explicit_m,
            'netlist statements %d, expanded devices at the top %d, hierarchy subckt instances %d, '
            'multiplicity sum %d (m is unset on every device, so it contributes one each), finger '
            'parameters written %s, effective width per model %s -- statements, instances, '
            'multiplicity and width are four different numbers and are not exchanged for each other'
            % (statement_count, len(devices), len(instances), multiplicity, explicit_m or 'none',
               ' '.join('%s=%.3e' % (k, v) for k, v in sorted(effective.items()))))

    # ---- mirror ratio
    ref = [d for d in NL.expand(subs, REFERENCE)[0] if d['inst'].split('.')[-1] == 'Mref'][0]
    unit = [d for d in NL.expand(subs, UNIT)[0] if d['inst'].split('.')[-1] == 'Mout'][0]
    ratio = (NL.si(ref['w']) / NL.si(ref['l'])) / (NL.si(unit['w']) / NL.si(unit['l']))
    rep.add('MIRROR_RATIO_ESTIMATED_ONLY', abs(ratio - BRANCH_COUNT) < 1e-9,
            'reference Mref W=%s L=%s over unit Mout W=%s L=%s gives %g, tagged '
            'ESTIMATED_MIRROR_RATIO_ONLY: no short-channel, output-resistance, body-effect or '
            'matching behaviour is claimed' % (ref['w'], ref['l'], unit['w'], unit['l'], ratio))

    # ---- isomorphism against the accepted core, over every effective parameter
    port_alias = {'DATA_EN': 'EN', 'DATA_EN_B': 'EN_B'}

    def role(token, ports):
        base = token.split('/')[-1]
        return port_alias.get(base, base) if base in ports else 'LOCAL:' + base
    accepted = dict((d['inst'].split('.')[-1], d) for d in NL.expand(subs, ACCEPTED_CORE)[0])
    candidate = dict((d['inst'].split('.')[-1], d) for d in NL.expand(subs, UNIT)[0])
    accepted_ports, candidate_ports = subs[ACCEPTED_CORE]['ports'], subs[UNIT]['ports']
    diffs = []
    for name in sorted(set(accepted) | set(candidate)):
        if name not in accepted or name not in candidate:
            diffs.append('%s only in one core' % name)
            continue
        a, b = accepted[name], candidate[name]
        if a['model'] != b['model']:
            diffs.append('%s model %s!=%s' % (name, a['model'], b['model']))
        try:
            for field in ('l', 'm'):
                if NL.si(a[field]) != NL.si(b[field]):
                    diffs.append('%s %s %s!=%s (implicit m is 1)'
                                 % (name, field, a[field], b[field]))
        except NL.NetlistError as error:
            diffs.append('%s parameter not comparable: %s' % (name, error))
        for terminal in ('d', 'g', 's', 'b'):
            left = role(a[terminal], accepted_ports)
            right = role(b[terminal], candidate_ports)
            if left != right:
                diffs.append('%s.%s is %s in the accepted core, %s in the candidate'
                             % (name, terminal, left, right))
        allowed = {'Mcas': NL.si('2e-5') / BRANCH_COUNT, 'Mout': NL.si('2e-5') / BRANCH_COUNT}
        if name in allowed:
            if abs(NL.si(b['w']) - allowed[name]) > 1e-12:
                diffs.append('%s w=%s, expected the accepted 2e-5 divided by %d'
                             % (name, b['w'], BRANCH_COUNT))
        elif a['w'] != b['w']:
            diffs.append('%s w=%s changed to %s although only Mcas/Mout may scale'
                         % (name, a['w'], b['w']))
    rep.add('UNIT_CORE_ISOMORPHIC_TO_ACCEPTED', not diffs,
            'device by device %s matches %s in model, L, multiplicity m and D/G/S/B role; only Mcas '
            'and Mout widths scale by 1/%d, pass and bleed keep the accepted widths%s'
            % (UNIT, ACCEPTED_CORE, BRANCH_COUNT, '' if not diffs else '; ' +
               '; '.join(diffs[:4])))

    # ---- machine-readable device count claims, then the prose claims bound to their object
    claims, _ = read_rows(os.path.join(root, 'tests', 'dd1_d7c_a', 'device_count_claims.csv'))
    problems = []
    if claims is None:
        problems.append('claim table missing')
        claims = []
    seen = set()
    for row in claims:
        obj, kind = row.get('object'), row.get('count_kind')
        if not obj or not kind:
            problems.append('claim row without object or count_kind: %s' % row)
            continue
        if (obj, kind) in seen:
            problems.append('duplicate claim key %s/%s' % (obj, kind))
        seen.add((obj, kind))
        if obj not in subs:
            problems.append('claim names %s, which is not a defined cell' % obj)
            continue
        actual = {'expanded_mos': len(NL.expand(subs, obj)[0]),
                  'statements': len(subs[obj]['mos']),
                  'subckt_instances': len(subs[obj]['subs'])}.get(kind)
        if actual is None:
            problems.append('unknown count_kind %s' % kind)
        elif str(actual) != str(row.get('count')):
            problems.append('%s %s is %d in the netlist, the claim table says %s'
                            % (obj, kind, actual, row.get('count')))
    rep.add('CLAIM_TABLE_MATCHES_PARSE', not problems,
            '%d object-bound claims (%s) each equal to the parsed value%s'
            % (len(claims), ','.join(sorted(set(r.get('object', '') for r in claims)) or ['-']),
               '' if not problems else '; ' + '; '.join(problems[:4])))
    totals = dict((cell, len(NL.expand(subs, cell)[0])) for cell in subs)
    stale = []
    for rel in CLAIM_FILES:
        path = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding='utf-8') as handle:
            body = handle.read()
        for line in body.split('\n'):
            if 'check:skip' in line:
                continue
            for match in CLAIM_RX.finditer(line):
                start = match.start()
                window = line[max(0, start - 60):start + 60]
                offset = max(0, start - 60)
                anchors = []
                for cell in totals:
                    position = line.find(cell)
                    while position >= 0:
                        distance = min(abs(position - start),
                                       abs(position + len(cell) - start))
                        anchors.append((distance, cell))
                        position = line.find(cell, position + 1)
                if not anchors:
                    stale.append('%s: "%s" has no cell name on the line' % (rel, match.group(0)))
                    continue
                anchors.sort()
                near = anchors[0][1]
                if int(match.group(1)) != totals[near]:
                    stale.append('%s: "%s" is bound to %s (%d characters away) whose parsed total '
                                 'is %d' % (rel, match.group(0), near, anchors[0][0], totals[near]))
    rep.add('REPORT_CLAIMS_BOUND_TO_OBJECT', not stale,
            'every N MOS / N 管 / N transistors claim names the cell it counts and equals that '
            'cell-parsed total%s' % ('' if not stale else '; ' + '; '.join(stale[:3])))
    membership = []
    numbers = set(str(v) for v in totals.values())
    for rel in CLAIM_FILES:
        path = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding='utf-8') as handle:
            body = handle.read()
        for line in body.split('\n'):
            if 'check:skip' in line:
                continue
            for match in CLAIM_RX.finditer(line):
                if match.group(1) not in numbers:
                    membership.append('%s claims %s devices' % (rel, match.group(1)))
    rep.add('REPORT_CLAIM_COUNTS_MATCH', not membership,
            'secondary membership test: no claim equals a total parsed from some cell%s'
            % ('' if not membership else '; ' + '; '.join(membership[:3])))
    return per_cell


def table_and_entry_checks(root, rep):
    # ---- request refusal table schema plus the refusals themselves
    rows, _ = read_rows(os.path.join(root, 'tests', 'dd1_d7c_a', 'pam_request_refusal.csv'))
    schema = []
    if rows is None:
        schema.append('request table missing')
        rows = []
    if len(rows) != 16:
        schema.append('%d rows, the schema is exactly 16' % len(rows))
    ids = [r.get('case_id') for r in rows]
    if len(set(ids)) != len(ids) or None in ids or '' in ids:
        schema.append('case_id values are not %d unique non-empty ids' % len(rows))
    for row in rows:
        if row.get('expected_refusal_code') not in REFUSAL_CODES:
            schema.append('%s expects an unknown code %r' % (row.get('case_id'),
                                                             row.get('expected_refusal_code')))
    rep.add('REQUEST_TABLE_SCHEMA', not schema,
            '%d request rows with unique ids and codes from the closed set %s%s'
            % (len(rows), ','.join(REFUSAL_CODES),
               '' if not schema else '; refusals: ' + '; '.join(schema[:3])))
    wrong = []
    for row in rows:
        state, code = NL.validate_request(_coerce(row['raw_literal'], row['kind']))
        want = row['expected_refusal_code']
        if want == 'ACCEPTED':
            if state != 'ACCEPTED':
                wrong.append('%s %r refused as %s' % (row['case_id'], row['raw_literal'], code))
        elif (state, code) != ('REFUSED', want):
            wrong.append('%s %r -> %s/%s, expected %s' % (row['case_id'], row['raw_literal'], state,
                                                          code, want))
    rep.add('REQUEST_REFUSAL_TABLE', rows and not wrong,
            '%d request shapes tried, including X/Z, empty, non-numeric, out of range, non-integer, '
            'non-finite and bool; this is a software boundary and no MOS branch can see X/Z%s'
            % (len(rows), '' if not wrong else '; ' + '; '.join(wrong[:4])))

    # ---- the native entry refuses before it can write or connect
    probe_root = tempfile.mkdtemp(prefix='dd1-d7c-a-deckprobe-')
    try:
        target = os.path.join(probe_root, 'out')
        os.makedirs(target)
        with io.open(os.path.join(target, 'sentinel.txt'), 'wb') as handle:
            handle.write(b'sentinel\n')
        outcomes = [DECKGEN.probe(target, dict(env)) for env in
                    ({'QODER_SIM_AUTHORISED': '0', 'DATA7C_NATIVE_RUN': '0'},
                     {'QODER_SIM_AUTHORISED': '1', 'DATA7C_NATIVE_RUN': '1'},
                     {'QODER_SIM_AUTHORISED': '1'},
                     {'DATA7C_NATIVE_RUN': '1'})]
        rep.add('NATIVE_ENTRY_REFUSED', all(o['refused'] for o in outcomes) and
                all(o['untouched'] for o in outcomes) and
                os.path.isfile(os.path.join(target, 'sentinel.txt')),
                '%d environment combinations, entry refused in each before writing, directory digest '
                'unchanged and sentinel present' % len(outcomes))
    finally:
        shutil.rmtree(probe_root, ignore_errors=True)

    # ---- the plan table: shape, static enable, pairings and sign convention
    plan, _ = read_rows(os.path.join(root, 'tests', 'dd1_d7c_a', 'native_case_plan.csv'))
    problems = []
    if plan is None:
        problems.append('plan table missing')
        plan = []
    if len(plan) != 15:
        problems.append('%d cases, the draft is 8 DC + 4 transient + 3 refined = 15' % len(plan))
    ids = [r.get('case_id') for r in plan]
    if len(set(ids)) != len(ids):
        problems.append('case_id values are not unique')
    counts = {}
    for row in plan:
        counts[row.get('class', '?')] = counts.get(row.get('class', '?'), 0) + 1
    if counts != {'dc_sweep': 8, 'transient': 4, 'refined_step': 3}:
        problems.append('class breakdown %s' % counts)
    for row in plan:
        if row.get('result') != 'NOT_RUN':
            problems.append('%s result is %s' % (row.get('case_id'), row.get('result')))
        if row.get('class') == 'dc_sweep' and row.get('data_en_level_V') != '1.8':
            problems.append('%s does not hold DATA_EN at the static 1.8 V' % row.get('case_id'))
        if row.get('class') == 'dc_sweep' and not (row.get('code', '').strip()[:1] in '01234567'):
            problems.append('%s does not name its PAM code as a leading digit' % row.get('case_id'))
        if row.get('class') == 'refined_step':
            if row.get('refine_only') != 'time_maxstep':
                problems.append('%s refines %s, and refined cases must refine only the time step'
                                % (row.get('case_id'), row.get('refine_only')))
            if row.get('paired_case') not in ids:
                problems.append('%s pairs with unknown case %s' % (row.get('case_id'),
                                                                  row.get('paired_case')))
    long_rows = [r for r in plan if r.get('case_id') == 'TR-LONG']
    if not long_rows or len(long_rows[0].get('segments', '').split(';')) != 8:
        problems.append('TR-LONG must list eight code segments in one deck, not claim eight levels '
                        'while running code 111 only')
    if sum(int(r.get('draft_launch_units', 0)) for r in plan) != 30:
        problems.append('draft launch units must total 30 (15 DUT + 15 paired preflight)')
    probe_dir = set(r.get('probe_orientation', '') for r in plan)
    if probe_dir != {plan[0].get('probe_orientation', '')} or not plan[0].get('probe_orientation'):
        problems.append('every case must declare the same probe orientation and sign convention')
    rep.add('NATIVE_PLAN_SHAPE', not problems,
            '%d planned cases %s, all result NOT_RUN, DC rows hold DATA_EN=1.8 V with a named code, '
            'TR-LONG carries eight segments in one deck, refined pairs differ only in maxstep, draft '
            'units 30%s' % (len(plan), sorted(counts.items()),
                            '' if not problems else '; ' + '; '.join(problems[:4])))

    # ---- deck draft: active analysis and statement inventory
    deck_path = os.path.join(root, DECK_DRAFT)
    with io.open(deck_path, encoding='utf-8') as handle:
        raw_lines = handle.read().replace('\r\n', '\n').split('\n')
    active = deck_statements(deck_path)
    analysis = [(number, line) for number, line in active if ANALYSIS_RX.match(line)]
    unknown = []
    for number, line in active:
        if ANALYSIS_RX.match(line):
            continue
        if any(rx.match(line) for rx in DECK_STATEMENT_RX.values()):
            continue
        unknown.append((number, line[:80]))
    rep.add('DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS', not analysis,
            '%d active (non-comment) lines in the deck draft, analysis statements recognised by the '
            'keyword position with or without dev=: %d%s. This states only that the draft carries no '
            'analysis to run; it is not a claim that pointing Spectre at the file would not start a '
            'process -- that is guarded by the entry authorisation above.'
            % (len(active), len(analysis), '' if not analysis else '; found ' +
               '; '.join('line %d: %s' % (n, l[:40]) for n, l in analysis[:2])))
    rep.add('DRAFT_DECK_SYNTAX_INVENTORY', not unknown,
            'every active deck line classifies into simulator/include/parameters/save/source/probe/'
            'instance/analysis; unrecognised active statements would be refused by name%s'
            % ('' if not unknown else '; unclassified ' +
               '; '.join('line %d: %s' % (n, l) for n, l in unknown[:3])))
    return plan


def run_checks(root):
    rep = Report()
    digests = {}
    for rel in CANDIDATE_FILES + ACCEPTED_MASTERS + [DECK_DRAFT]:
        path = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(path):
            rep.add('NETLIST_SUBSET_PARSED', False, '%s is missing' % rel)
            return rep
        digests[rel] = sha_file(path)
    try:
        loaded = main_checks(root, rep)
    except NL.NetlistError as error:
        rep.add('NETLIST_SUBSET_PARSED', False, str(error)[:300])
        for name in ('SUBCKT_MASTERS_DEFINED', 'INSTANCE_PORT_COUNTS', 'NO_DUPLICATE_INSTANCES',
                     'TOP_HAS_ONE_OUTPUT_PORT', 'ALL_BRANCHES_ON_COMMON_OUTPUT',
                     'UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE', 'LOCAL_NODES_NOT_SHARED',
                     'REFERENCE_NODE_IDENTITY', 'DNW_PASS_BODY_LOCAL',
                     'BLEED_GATED_BY_BRANCH_COMPLEMENT', 'MAIN_PATH_DATA_OUT_CAS_MOUT_VSS',
                     'THERMO_GOLDEN_16', 'GOLDEN_TABLE_SCHEMA', 'TOP_INTEGRATED_THERMO_16',
                     'EN_ENB_PAIR_PER_BRANCH', 'GATE_LOGIC_DERIVED_FROM_TRANSISTORS',
                     'DEVICE_COUNTS_DERIVED', 'DEVICE_COUNT_SEPARATION', 'MIRROR_RATIO_ESTIMATED_ONLY',
                     'UNIT_CORE_ISOMORPHIC_TO_ACCEPTED', 'CLAIM_TABLE_MATCHES_PARSE',
                     'REPORT_CLAIMS_BOUND_TO_OBJECT', 'REPORT_CLAIM_COUNTS_MATCH'):
            rep.add(name, False, 'not evaluated: the netlist set did not load (%s)'
                    % str(error)[:80])
        return rep
    (subs, devices, instances, top, top_ports, binding, branch_resolved, units,
     shared_reference) = loaded
    statement_count = len(devices)
    rep.add('NETLIST_SUBSET_PARSED', True,
            '%d files parsed, %d subckt definitions, %d expanded devices at %s, unsupported '
            'statements 0; candidate digests %s'
            % (len(CANDIDATE_FILES) + len(ACCEPTED_MASTERS), len(subs), statement_count, TOP,
               ','.join('%s=%s' % (os.path.basename(k)[:12], v[:8])
                        for k, v in sorted(digests.items()) if k in CANDIDATE_FILES)))
    unknown = ['%s->%s' % (i['inst'], i['master']) for i in instances if i['master'] not in subs]
    models = sorted(set(d['model'] for d in devices))
    rep.add('SUBCKT_MASTERS_DEFINED', not unknown,
            '%d subckt instances all resolve; models %s against whitelist %s'
            % (len(instances), ','.join(models), ','.join(NL.MODEL_WHITELIST)))
    bad_counts = [i['inst'] for i in instances
                  if len(i['nets']) != len(subs[i['master']]['ports'])]
    rep.add('INSTANCE_PORT_COUNTS', not bad_counts,
            '%d instance bindings, each with exactly its master port count and order%s'
            % (len(instances), '' if not bad_counts else '; ' + ','.join(bad_counts[:3])))
    logic_checks(root, rep, subs, devices, instances, top, top_ports, binding, branch_resolved,
                 units, shared_reference)
    counting_checks(rep, subs, devices, instances, root)
    table_and_entry_checks(root, rep)
    return rep


def _combos(count):
    for value in range(1 << count):
        yield tuple((value >> bit) & 1 for bit in range(count))


def _coerce(text, kind):
    if kind == 'integer_out_of_range':
        return int(text)
    if kind in ('float_non_integer', 'float_integral_value', 'float_non_finite'):
        return float(text)
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
        print('%-40s %s   %s' % (row['check'], row['result'], row['reason'][:200]))
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
