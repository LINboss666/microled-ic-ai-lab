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
THERMO_CODES = ('000', '001', '010', '011', '100', '101', '110', '111')
IPROBE_RX = re.compile(r'^\s*(\w+)\s*\(\s*(\w+)\s+(\w+)\s*\)\s*iprobe\b', re.I)
DUT_INSTANCE_RX = re.compile(r'^\s*Xdut\s*\(([^)]*)\)', re.I)
VSOURCE_RX = re.compile(r'^\s*(\w+)\s*\(\s*(\w+)\s+(\w+)\s*\)\s*vsource\b(.*)$', re.I)
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


# ---- strict reading of the tables these checks consume -------------------------------
#
# read_rows() above is a loose DictReader: a row with one cell too many loses the extra cell into
# None, a header-only file yields zero rows without complaint, and a 'NaN' in a numeric column only
# surfaces later as an unhandled int() crash. The review named exactly those three shapes, so every
# real input table now goes through strict_read below, which reports refusals as data instead of
# raising, and never hands a downstream loop a row it has not width- and domain-checked.

INT_COLUMNS = {
    'golden': {'data_en': (0, 1), 'pam_sel': tuple(range(8)), 'branches_on': tuple(range(9)),
               'en0': (0, 1), 'en1': (0, 1), 'en2': (0, 1), 'en3': (0, 1), 'en4': (0, 1),
               'en5': (0, 1), 'en6': (0, 1), 'en7': (0, 1)},
    'claims': {'count': None},                       # any finite non-negative integer, range is
}                                                   # whatever the parse says, checked elsewhere


def strict_int(value, allowed):
    """a finite base-10 integer, optionally inside an explicit set; never a float, NaN or blank"""
    text = str(value).strip()
    if not re.match(r'^-?\d+$', text):
        return None
    number = int(text)
    if number < 0:
        return None
    if allowed is not None and number not in allowed:
        return None
    return number


def strict_read(path, spec):
    """read one input table against its declared schema; returns (rows, problems) and never raises"""
    problems = []
    if not os.path.isfile(path):
        return [], ['%s is missing' % spec['label']]
    with io.open(path, encoding='utf-8', newline='') as handle:
        raw = list(csv.reader(handle))
    header = spec['header']
    if not raw:
        return [], ['%s is an empty file, not a table with zero rows' % spec['label']]
    if raw[0] != header:
        return [], ['%s header is %s, the schema declares %s'
                    % (spec['label'], raw[0], header)]
    if len(raw) - 1 != spec['rows']:
        problems.append('%s has %d data rows, the schema declares exactly %d'
                        % (spec['label'], len(raw) - 1, spec['rows']))
    rows = []
    seen = {}
    rejoined = []
    free_text = spec.get('final_column_free_text')
    for number, cells in enumerate(raw[1:], 2):
        if free_text and header and header[-1] == free_text and len(cells) > len(header):
            # The delivered, frozen request table writes its final note column as free text without
            # quoting, so two of its rows carry a comma inside that note. Re-joining keeps every
            # character of the note, still refuses a short row and any unexpected cell in an earlier
            # column, and the row numbers are named in the check reason so the serialisation defect
            # stays visible instead of being quietly tolerated.
            cells = cells[:len(header) - 1] + [','.join(cells[len(header) - 1:])]
            rejoined.append(number)
            spec['_rejoined_free_text_lines'] = list(rejoined)
        if len(cells) != len(header):
            problems.append('%s line %d has %d cells, the header declares %d'
                            % (spec['label'], number, len(cells), len(header)))
            continue
        record = dict(zip(header, cells))
        record['_line'] = number
        for column in header:
            text = str(record[column]).strip()
            if not text and column not in spec['optional']:
                problems.append('%s line %d leaves %s empty' % (spec['label'], number, column))
        for column, allowed in spec['ints'].items():
            if column not in header:
                problems.append('%s schema asks for column %s which the header does not declare'
                                % (spec['label'], column))
                continue
            parsed = strict_int(record[column], allowed)
            if parsed is None:
                problems.append('%s line %d field %s is %r, which is not a finite integer%s'
                                % (spec['label'], number, column, record[column],
                                   '' if allowed is None else ' in %s' % (list(allowed),)))
            else:
                record[column] = parsed
        if spec.get('mask_column'):
            column = spec['mask_column']
            mask = str(record.get(column, ''))
            if len(mask) != spec['mask_length'] or set(mask) - set('01'):
                problems.append('%s line %d field %s is %r, expected %d characters of 0/1'
                                % (spec['label'], number, column, mask, spec['mask_length']))
            else:
                bits = [record.get('en%d' % j) for j in range(spec['mask_length'])]
                if any(b is None for b in bits):
                    problems.append('%s line %d cannot compare en0..en%d against %r because a bit '
                                    'field was refused' % (spec['label'], number,
                                                            spec['mask_length'] - 1, mask))
                elif bits != [int(c) for c in mask[::-1]]:
                    problems.append('%s line %d en0..en7 disagree with %s=%s'
                                    % (spec['label'], number, column, mask))
                elif record.get('branches_on') is not None and \
                        record['branches_on'] != sum(bits):
                    problems.append('%s line %d branches_on=%s but the mask has %d bits set'
                                    % (spec['label'], number, record['branches_on'], sum(bits)))
        key = tuple(record.get(k) for k in spec['unique'])
        if any(part is None for part in key):
            problems.append('%s line %d has an unusable key %s' % (spec['label'], number, key))
        elif key in seen:
            problems.append('%s repeats key %s (lines %d and %d)'
                            % (spec['label'], key, seen[key], number))
        else:
            seen[key] = number
        rows.append(record)
    for key in spec.get('required_keys', ()):
        if key not in seen:
            problems.append('%s is missing the key %s the contract requires' % (spec['label'], key))
    if spec.get('required_keys'):
        for key in sorted(set(seen) - set(spec['required_keys'])):
            problems.append('%s carries key %s, which the contract does not declare'
                            % (spec['label'], key))
    return rows, problems


GOLDEN_HEADER = ['row_id', 'pam_sel', 'data_en', 'en0', 'en1', 'en2', 'en3', 'en4', 'en5', 'en6',
                 'en7', 'unit_mask_7to0', 'branches_on', 'theoretical_target_uA', 'source']
REQUEST_HEADER = ['case_id', 'raw_literal', 'kind', 'expected_refusal_code', 'note']
CLAIMS_HEADER = ['object', 'count_kind', 'count', 'note']
PLAN_HEADER = ['case_id', 'class', 'purpose', 'pam_code', 'code', 'data_en_form', 'data_en_level_V',
               'stimulus_start_TON', 'platform_TON', 'edge_TON', 'off_gap_TON', 'tail_TON',
               'window_TON', 'segments', 'maxstep_ns', 'observe_nodes', 'measure_interval',
               'reference_definition', 'failure_condition', 'probe_orientation', 'sign_convention',
               'paired_case', 'refine_only', 'draft_launch_units', 'result']
CLAIM_KEYS = None                      # filled by load_claim_keys() so the list is read once


def input_specs():
    """the four delivered input tables and what each one is declared to contain"""
    return {
        'golden': {'label': 'golden mask table', 'header': GOLDEN_HEADER, 'rows': 16,
                   'unique': ('data_en', 'pam_sel'), 'optional': (), 'ints': INT_COLUMNS['golden'],
                   'mask_column': 'unit_mask_7to0', 'mask_length': 8,
                   'path': 'tests/dd1_d7c_a/pam_mask_golden.csv',
                   'required_keys': GOLDEN_KEYS},
        'request': {'label': 'request refusal table', 'header': REQUEST_HEADER, 'rows': 16,
                    'unique': ('case_id',),
                    # the empty literal is itself a tested request, so that one cell is legitimately
                    # empty; case_id, kind and expected code stay required
                    'optional': ('note', 'raw_literal'), 'ints': {},
                    'final_column_free_text': 'note',
                    'path': 'tests/dd1_d7c_a/pam_request_refusal.csv'},
        'claims': {'label': 'device count claims', 'header': CLAIMS_HEADER, 'rows': 17,
                   'unique': ('object', 'count_kind'), 'optional': ('note',),
                   'ints': INT_COLUMNS['claims'], 'path': 'tests/dd1_d7c_a/device_count_claims.csv',
                   'required_keys': load_claim_keys()},
        'plan': {'label': 'native case plan', 'header': PLAN_HEADER, 'rows': 15,
                 'unique': ('case_id',),
                 'optional': ('segments', 'paired_case', 'refine_only'),
                 'ints': {'draft_launch_units': None}, 'path': 'tests/dd1_d7c_a/native_case_plan.csv'},
    }


def load_claim_keys():
    """the seventeen (object, count_kind) pairs this project's contract declares, written by hand

    They cannot be derived from the file being checked: a table trimmed to its header would then
    "require" nothing and a zero-row read would look correct, which is the hole the review named as
    claim_table_header_only_accepted. The list is the union of what R1 established and re-derived
    from the parser: every cell whose expanded MOS total is quoted in a report (10 objects), the
    cells whose own netlist statement lines are counted (5), and the two scopes where hierarchy
    instances are counted (2). Seventeen keys, matching the seventeen delivered rows.
    """
    expanded = ('dd1_d7c_a_pam_1ch', 'dd1_d7c_a_pam_dec', 'dd1_d7c_a_sink_unit', 'data_bias_ref',
                'data_sink_1ch', 'dd1_d7c_a_nand2', 'dd1_d7c_a_nor2', 'dd1_d7c_a_and2',
                'dd1_d7c_a_or2', 'dd1_inv18')
    statements = ('dd1_d7c_a_pam_1ch', 'dd1_d7c_a_pam_dec', 'dd1_d7c_a_sink_unit', 'data_bias_ref',
                  'dd1_d7c_a_nand2')
    instances = ('dd1_d7c_a_pam_1ch', 'dd1_d7c_a_pam_dec')
    keys = [(cell, 'expanded_mos') for cell in expanded]
    keys += [(cell, 'statements') for cell in statements]
    keys += [(cell, 'subckt_instances') for cell in instances]
    assert len(keys) == 17 and len(set(keys)) == 17, 'the contract key set itself went slack'
    return keys


def read_input_table(root, name, specs=None):
    """strictly read one delivered input table; problems are data, never an exception"""
    spec = (specs or input_specs())[name]
    path = os.path.join(root, spec['path'].replace('/', os.sep))
    return spec, strict_read(path, spec)


def input_schema_checks(root, rep, specs):
    """one named gate over the shape and value domains of every table these checks consume

    Without it a malformed row is only noticed later, by whichever loop happens to call int() on it,
    which is how a NaN in en0 became an unhandled ValueError instead of a refusal.
    """
    rows_by_name, problems_by_name, flat = {}, {}, []
    inputs = {'rows': rows_by_name, 'problems': problems_by_name, 'specs': specs}
    for name in sorted(specs):
        spec, (rows, table_problems) = read_input_table(root, name, specs)
        rows_by_name[name] = rows
        problems_by_name[name] = table_problems
        for message in table_problems:
            flat.append('%s: %s' % (name, message))
    rep.add('INPUT_TABLE_SCHEMAS', not flat,
            'four delivered tables read with declared header, per-line width, required fields, '
            'unique key, contract key set and finite integer domains%s'
            % ('' if not flat else '; %d refusals: %s' % (len(flat), '; '.join(flat[:4]))))
    return inputs


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


def supply_binding_problems(subs, top, top_ports):
    """every instance terminal that this subset calls a supply rail must sit on that top rail

    The first round proved the decoder's *logic* inputs were bound as the top says, then handed the
    subcircuit ideal rails anyway: an Xdec whose vdd18 terminal is wired to vss still evaluated
    sixteen combinations correctly, because the evaluator never asked where the real rails went. This
    is the text-and-graph answer to that, not a simulation: the rails are the ports the top declares
    as inputOutput, and the identity is read from the actual instance bindings.
    """
    rails = [p for p in top_ports if top['direction'].get(p) == 'inputOutput']
    problems = []
    if sorted(rails) != ['vdd18', 'vss']:
        return ['top declares supply rails %s, this subset expects exactly vdd18 and vss'
                % (','.join(rails) or 'none')]
    ground = 'vss'
    for entry in top['subs']:
        master = subs.get(entry['master'])
        if master is None:
            problems.append('%s has no readable master cell' % entry['inst'])
            continue
        if len(entry['nets']) != len(master['ports']):
            problems.append('%s binds %d nets to %d ports'
                            % (entry['inst'], len(entry['nets']), len(master['ports'])))
            continue
        pairs = list(zip(master['ports'], entry['nets']))
        for port, net in pairs:
            if port in rails and net != port:
                problems.append('%s binds its %s terminal to %s instead of the top rail %s'
                                % (entry['inst'], port, net, port))
        if not any(net == ground for _port, net in pairs):
            problems.append('%s has no terminal on the ground rail %s' % (entry['inst'], ground))
        tie_offs = [(port, net) for port, net in pairs if net in rails and port not in rails]
        if len([1 for _p, net in pairs if net in rails]) < 1:
            problems.append('%s reaches no top supply rail at all' % entry['inst'])
    return problems


def logic_checks(root, rep, subs, devices, instances, top, top_ports, binding, branch_resolved,
                 units, shared_reference, inputs):
    # ---- the rails first: an evaluation with ideal power is not evidence about the real binding
    supply = supply_binding_problems(subs, top, top_ports)
    rep.add('TOP_SUPPLY_BINDINGS', not supply,
            '%d top-scope instances all keep their declared vdd18/vss terminals on those rails and '
            'reach the ground rail%s'
            % (len(top['subs']), '' if not supply else '; ' + '; '.join(supply[:4])))

    # ---- golden table schema, straight from the strict reader: nothing here parses on its own
    golden = inputs['rows']['golden']
    schema = list(inputs['problems']['golden'])
    keys = set((row['data_en'], row['pam_sel']) for row in golden
               if isinstance(row.get('data_en'), int) and isinstance(row.get('pam_sel'), int))
    missing = sorted(GOLDEN_KEYS - keys)
    extra = sorted(keys - GOLDEN_KEYS)
    if missing:
        schema.append('missing keys %s' % missing[:4])
    if extra:
        schema.append('illegal keys %s' % extra[:4])
    rep.add('GOLDEN_TABLE_SCHEMA', not schema,
            'golden table has %d usable rows over the 16 unique (enable,code) keys, masks of 8 '
            'characters of 0/1, en0..en7 consistent with the mask and branches_on equal to the '
            'popcount%s' % (len(golden), '' if not schema else '; refusals: ' + '; '.join(schema[:4])))

    # ---- mask comparison, still driven by the hand-written rows
    mismatches = []
    for row in golden:
        if not usable_golden(row):
            mismatches.append('%s line %s: refused by the schema, not evaluated against the decoder'
                              % (row.get('row_id', '?'), row.get('_line', '?')))
            continue
        if (row['data_en'], row['pam_sel']) not in GOLDEN_KEYS:
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
    rep.add('THERMO_GOLDEN_16', bool(golden) and not mismatches and not schema,
            '%d hand-written golden rows compared against the decoder transistors themselves, never '
            'generated by this evaluator%s' % (len(golden),
                                               '' if (not mismatches and not schema) else '; ' +
                                               '; '.join((mismatches + schema)[:3])))

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
            if not usable_golden(row):
                integ.append('%s line %s: refused by the schema, never evaluated'
                             % (row.get('row_id', '?'), row.get('_line', '?')))
                continue
            if (row['data_en'], row['pam_sel']) not in GOLDEN_KEYS:
                continue
            cells += 1
            code, enable = row['pam_sel'], row['data_en']
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
    rep.add('TOP_INTEGRATED_THERMO_16', not integ and not schema,
            '%d top-level enable/code combinations driven from the top pins, through the actual Xdec '
            'port binding, and read back at each branch EN/EN_B terminal (decoder port map %s)%s'
            % (cells, bind if len(xdec) == 1 else '-', '' if not (integ or schema) else '; ' +
               '; '.join((integ + schema)[:2])[:300]))

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


def usable_golden(row):
    """a golden row may only be evaluated if the strict reader parsed every field it indexes"""
    fields = ['data_en', 'pam_sel', 'branches_on'] + ['en%d' % j for j in range(8)]
    if not all(isinstance(row.get(name), int) for name in fields):
        return False
    mask = str(row.get('unit_mask_7to0', ''))
    return len(mask) == 8 and not set(mask) - set('01')


def decoder_inputs(subs, row):
    code, enable = row['pam_sel'], row['data_en']
    if not (isinstance(code, int) and isinstance(enable, int)):
        return None
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


def counting_checks(rep, subs, devices, instances, root, inputs):
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
    claims = list(inputs['rows']['claims'])
    problems = list(inputs['problems']['claims'])
    seen = set()
    for row in claims:
        obj, kind = row.get('object'), row.get('count_kind')
        count = row.get('count')
        if not isinstance(count, int):
            problems.append('claim %s/%s count %r was refused by the schema, not compared'
                            % (obj, kind, count))
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
        elif actual != count:
            problems.append('%s %s is %d in the netlist, the claim table says %d'
                            % (obj, kind, actual, count))
    rep.add('CLAIM_TABLE_MATCHES_PARSE', not problems,
            '%d object-bound claims (%s) each equal to the parsed value, over the %d keys the '
            'contract declares%s'
            % (len(claims), ','.join(sorted(set(str(r.get('object', '')) for r in claims)) or ['-']),
               len(load_claim_keys()), '' if not problems else '; ' + '; '.join(problems[:4])))
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


def deck_probe_line(root):
    """the single iprobe statement in the bench draft, as (name, terminal in, terminal out)"""
    probes = [line for _number, line in deck_statements(os.path.join(root, DECK_DRAFT))
              if IPROBE_RX.match(line)]
    if len(probes) != 1:
        return None
    match = IPROBE_RX.match(probes[0])
    return match.group(1), match.group(2), match.group(3)


def deck_clamp_and_output(root):
    """derive the two nodes a sinking branch moves current between, from the deck itself

    The clamp is the grounded vsource whose dc parameter names the clamp level, and the DUT output is
    the net the top's single declared output port binds to in the Xdut line. Neither node name is
    typed into this checker, so a rename in the deck moves the requirement with it.
    """
    active = deck_statements(os.path.join(root, DECK_DRAFT))
    clamp = None
    for _number, line in active:
        match = VSOURCE_RX.match(line)
        if not match or 'VCLAMP' not in match.group(4).upper():
            continue
        nodes = (match.group(2), match.group(3))
        if '0' in nodes:
            clamp = nodes[0] if nodes[1] == '0' else nodes[1]
    if clamp is None:
        return None, None
    dut = [line for _number, line in active if DUT_INSTANCE_RX.match(line)]
    if len(dut) != 1:
        return clamp, None
    nets = DUT_INSTANCE_RX.match(dut[0]).group(1).split()
    try:
        subs, _ = load_subs(root)
    except NL.NetlistError:
        return clamp, None
    ports, direction = subs[TOP]['ports'], subs[TOP]['direction']
    if len(nets) != len(ports):
        return clamp, None
    outputs = [index for index, port in enumerate(ports)
               if direction.get(port) in ('output', 'inout')]
    if len(outputs) != 1:
        return clamp, None
    return clamp, nets[outputs[0]]


def deck_probe_orientation_problems(root, plan):
    """the deck's probe terminal order and the plan's declared positive direction must be one claim"""
    problems = []
    if len(plan) != 15:
        return ['the plan did not read as fifteen rows, so its sign claim cannot be compared']
    line = deck_probe_line(root)
    if line is None:
        return ['the bench draft does not contain exactly one iprobe statement']
    name, first, second = line
    clamp, output = deck_clamp_and_output(root)
    if clamp is None or output is None:
        return ['the probe nodes were not both identified (clamp=%s, dut_output=%s); the output net '
                'is read through the top cell, so a netlist set that does not load is a missing '
                'derivation, not an agreement' % (clamp, output)]
    if (first, second) != (clamp, output):
        problems.append('%s is written (%s %s) while a sinking branch moves current %s -> %s, so the '
                        'declared positive reading would be the negative of the sink current'
                        % (name, first, second, clamp, output))
    quoted = ['%s (%s %s)' % (name, first, second)]
    drift = [row.get('case_id') for row in plan
             if quoted[0] not in str(row.get('probe_orientation', ''))]
    if drift:
        problems.append('%d plan rows do not quote the probe terminals as the deck writes them'
                        % len(drift))
    if not all('no abs()' in str(row.get('sign_convention', '')) for row in plan):
        problems.append('a row drops the rule that the sign is declared and never taken by abs()')
    return problems


def table_and_entry_checks(root, rep, inputs):
    # ---- request refusal table schema plus the refusals themselves
    rows = list(inputs['rows']['request'])
    schema = list(inputs['problems']['request'])
    for row in rows:
        if row.get('expected_refusal_code') not in REFUSAL_CODES:
            schema.append('%s expects an unknown code %r' % (row.get('case_id'),
                                                             row.get('expected_refusal_code')))
    loose = inputs['specs']['request'].get('_rejoined_free_text_lines', [])
    rep.add('REQUEST_TABLE_SCHEMA', not schema,
            '%d request rows with unique ids and codes from the closed set %s; %s%s'
            % (len(rows), ','.join(REFUSAL_CODES),
               ('the frozen note column is unquoted free text, so lines %s were re-joined without '
                'losing a character and are reported here rather than silently accepted'
                % ','.join(str(n) for n in loose)) if loose else 'no row needed re-joining',
               '' if not schema else '; refusals: ' + '; '.join(schema[:3])))
    wrong = list(schema)
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

    # ---- the plan table: schema, code coverage, pairings, schedule arithmetic and sign
    plan = list(inputs['rows']['plan'])
    problems = list(inputs['problems']['plan'])
    counts = {}
    for row in plan:
        counts[row.get('class', '?')] = counts.get(row.get('class', '?'), 0) + 1
    if counts != {'dc_sweep': 8, 'transient': 4, 'refined_step': 3}:
        problems.append('class breakdown %s' % counts)
    for row in plan:
        if row.get('result') != 'NOT_RUN':
            problems.append('%s result is %s' % (row.get('case_id'), row.get('result')))
        if row.get('class') == 'dc_sweep' and row.get('data_en_form') != 'static_dc':
            problems.append('%s is not driven as a static DC point' % row.get('case_id'))
        if row.get('class') == 'dc_sweep' and row.get('data_en_level_V') != '1.8':
            problems.append('%s does not hold DATA_EN at the static 1.8 V' % row.get('case_id'))
        if row.get('class') == 'refined_step' and row.get('refine_only') != 'time_maxstep':
            problems.append('%s refines %s, and refined cases must refine only the time step'
                            % (row.get('case_id'), row.get('refine_only')))
    # eight DC rows must cover eight different codes, and each row must carry the code its own
    # case_id names: "every row starts with a digit" plus "there are eight rows" together still let
    # all eight hold code 000, which is the hole the review demonstrated.
    dc = [r for r in plan if r.get('class') == 'dc_sweep']
    claimed = {}
    for row in dc:
        code = str(row.get('pam_code', ''))
        if not re.match(r'^[01]{3}$', code):
            problems.append('%s pam_code %r is not a three-bit literal'
                            % (row.get('case_id'), code))
            continue
        if code in claimed:
            problems.append('code %s claimed by both %s and %s'
                            % (code, claimed[code], row.get('case_id')))
        claimed[code] = row.get('case_id')
        if code != str(row.get('case_id', '')).split('-')[-1]:
            problems.append('%s declares pam_code %s, which contradicts its own identifier'
                            % (row.get('case_id'), code))
    if sorted(claimed) != sorted(THERMO_CODES):
        problems.append('the eight DC rows cover %s, not the thermometer set %s'
                        % (','.join(sorted(claimed)), ','.join(sorted(THERMO_CODES))))
    units = [strict_int(row.get('draft_launch_units'), None) for row in plan]
    if any(unit is None or unit != 2 for unit in units):
        problems.append('each case must cost two draft units (deck plus its own preflight), found %s'
                        % units)
    orientations = set(str(row.get('probe_orientation', '')) for row in plan)
    signs = set(str(row.get('sign_convention', '')) for row in plan)
    if len(orientations) != 1 or len(signs) != 1 or '' in orientations or '' in signs:
        problems.append('all fifteen rows must declare one identical probe orientation and one sign '
                        'convention (%d/%d distinct strings)' % (len(orientations), len(signs)))
    rep.add('NATIVE_PLAN_SHAPE', not problems,
            '%d planned cases %s, all result NOT_RUN, the eight DC rows are the eight codes named by '
            'their own identifiers with DATA_EN held static at 1.8 V, draft cost 2 units per case'
            '%s' % (len(plan), sorted(counts.items()),
                    '' if not problems else '; ' + '; '.join(problems[:4])))
    problems = []
    if len(plan) == 15:
        import dd1_d7c_a_r2_plan as SCHEDULE       # the one structured source of these numbers
        problems = SCHEDULE.validate_schedule(plan)
        bad_sign = [row.get('case_id') for row in plan
                    if str(row.get('probe_orientation')) != SCHEDULE.PROBE_ORIENTATION or
                    str(row.get('sign_convention')) != SCHEDULE.SIGN_CONVENTION]
        if bad_sign:
            problems.append('%s do not quote the source sign convention verbatim'
                            % ','.join(sorted(bad_sign)))
    else:
        problems.append('%d rows read, the schedule contract needs fifteen before any window is '
                        'judged' % len(plan))
    rep.add('PLAN_SCHEDULE_ARITHMETIC', not problems,
            'TR-LONG windows, gaps, platform widths, code-change placement, short-pulse flat parts, '
            'refined-pair identity and DC code coverage recomputed from the delivered rows against '
            'the single structured source%s'
            % ('' if not problems else '; ' + '; '.join(problems[:4])))
    deck_problems = deck_probe_orientation_problems(root, plan)
    rep.add('DECK_PROBE_ORIENTATION_MATCHES_PLAN', not deck_problems,
            'the iprobe line in the bench draft and the terminal order the plan declares agree, and '
            'the first probe terminal is the one the positive sink current enters from (%s)%s'
            % (' '.join(deck_probe_line(root)[1:3]) if deck_probe_line(root) else 'no single probe',
               '' if not deck_problems else '; ' + '; '.join(deck_problems[:3])))

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


# the gates that read the loaded netlist graph, so a load failure has to name them as not evaluated
# rather than let them vanish from the report. The guards suite imports this list instead of keeping
# its own copy, so the two cannot drift apart.
NETLIST_DEPENDENT_GATES = ('SUBCKT_MASTERS_DEFINED', 'INSTANCE_PORT_COUNTS', 'NO_DUPLICATE_INSTANCES',
                           'TOP_HAS_ONE_OUTPUT_PORT', 'ALL_BRANCHES_ON_COMMON_OUTPUT',
                           'UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE', 'LOCAL_NODES_NOT_SHARED',
                           'REFERENCE_NODE_IDENTITY', 'DNW_PASS_BODY_LOCAL',
                           'BLEED_GATED_BY_BRANCH_COMPLEMENT', 'MAIN_PATH_DATA_OUT_CAS_MOUT_VSS',
                           'THERMO_GOLDEN_16', 'GOLDEN_TABLE_SCHEMA', 'TOP_INTEGRATED_THERMO_16',
                           'TOP_SUPPLY_BINDINGS', 'EN_ENB_PAIR_PER_BRANCH',
                           'GATE_LOGIC_DERIVED_FROM_TRANSISTORS', 'DEVICE_COUNTS_DERIVED',
                           'DEVICE_COUNT_SEPARATION', 'MIRROR_RATIO_ESTIMATED_ONLY',
                           'UNIT_CORE_ISOMORPHIC_TO_ACCEPTED', 'CLAIM_TABLE_MATCHES_PARSE',
                           'REPORT_CLAIMS_BOUND_TO_OBJECT', 'REPORT_CLAIM_COUNTS_MATCH')


def run_checks(root):
    rep = Report()
    digests = {}
    for rel in CANDIDATE_FILES + ACCEPTED_MASTERS + [DECK_DRAFT]:
        path = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(path):
            rep.add('NETLIST_SUBSET_PARSED', False, '%s is missing' % rel)
            return rep
        digests[rel] = sha_file(path)
    specs = input_specs()
    inputs = input_schema_checks(root, rep, specs)
    try:
        loaded = main_checks(root, rep)
    except NL.NetlistError as error:
        rep.add('NETLIST_SUBSET_PARSED', False, str(error)[:300])
        for name in NETLIST_DEPENDENT_GATES:
            rep.add(name, False, 'not evaluated: the netlist set did not load (%s)'
                    % str(error)[:80])
        # the eight request/plan/deck gates read the delivered tables and the deck text, not the
        # loaded netlist graph, so a load failure must not make them disappear from the report
        table_and_entry_checks(root, rep, inputs)
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
                 units, shared_reference, inputs)
    counting_checks(rep, subs, devices, instances, root, inputs)
    table_and_entry_checks(root, rep, inputs)
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
