#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_dc_run.py -- DATA-7C-B-DC: eight PAM codes on one output channel, measured in DC.

One small entry point, as section 3 of the task book asks for. It does not build a general SPICE
interpreter, a transactional publish framework or a mutation platform. Everything it can borrow it
borrows from the accepted rounds:

  * `dd1_d7b_run.strip_direction_annotations`, `device_digest`, `port_order_digest`, `DIRECTION_RE`,
    `Link` (the ssh/scp channel that verifies the pushed bytes itself) and `parse_runner` (the runner's
    own answer line); the accepted file is imported, never edited;
  * `sc1_read_psf.parse` for the psfascii read, which already aborts on a non-finite value, a duplicate
    signal inside a group or an unfinished group;
  * the electrical criteria from `tests/dd1_d7c_b_prep/contract.json`, which is frozen this round: the
    DC contract keeps a snapshot of those rules and refuses if the frozen source drifts under it.

Budget: 20 spectre processes, persisted in this round's own append-only account before each start.
Nothing here touches DATA-7B's 56-launch account or its 59 historical seeds.

    python scripts/dd1_d7c_b_dc_run.py --selftest                 # offline, no guest, no launch
    python scripts/dd1_d7c_b_dc_run.py --masters                  # strip account + digest equality proof
    python scripts/dd1_d7c_b_dc_run.py --plan                     # what would run, costs, order
    python scripts/dd1_d7c_b_dc_run.py --launch DC-000 --role preflight --out <dir>
    python scripts/dd1_d7c_b_dc_run.py --extract <pulled raw> --deck DC-000 --role dut
    python scripts/dd1_d7c_b_dc_run.py --judge <rows.csv>
    python scripts/dd1_d7c_b_dc_run.py --account                   # the persisted account, read out

rc: 0 pass, 1 a real failure, 5 a refusal (no process started, nothing written), 2 usage.
"""

from __future__ import absolute_import, print_function

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_run as B7B                                    # noqa: E402  accepted runner primitives
import sc1_read_psf as PSF                                   # noqa: E402  accepted psfascii reader
import dd1_d7c_b_prep_contract as RENDER                     # noqa: E402  the unit row guard

TASK_ID = 'DATA-7C-B-DC'
BASE_SHA = 'e51c5320a28bd5043e21d08a0be97e9d5612cd16'
BRANCH = 'poc/data-pam-d7c-b-dc'
DC_CONTRACT = 'tests/dd1_d7c_b_dc/contract.json'
PREP_CONTRACT = 'tests/dd1_d7c_b_prep/contract.json'
DECK_DIR = 'spectre/dd1_d7c_b_prep'
RUN_DIR = 'spectre/dd1_d7c_b_dc'
GUEST_PROJECT = '/root/microled_ai_project'
GUEST_WORK_ROOT = '%s/cadence_work/dd1_d7c_b_dc' % GUEST_PROJECT
MASTERS = ('dd1_d6_inv18.scs', 'dd1_d6_bias_core.scs', 'dd1_d7c_a_gates.scs',
           'dd1_d7c_a_pam_dec.scs', 'dd1_d7c_a_sink_unit.scs', 'dd1_d7c_a_pam_top.scs')
DUT_INSTANCE_LINE = 'Xdut (data_en pam0 pam1 pam2 iref_in vcas data_out vdd18 vss) dd1_d7c_a_pam_1ch'
PREFLIGHT_LOAD = ['Rload_meter (data_out vss) resistor r=80e3',
                  'Rref_meter (iref_in vss) resistor r=50e3']
PREFLIGHT_LOAD_OHMS = 80e3     # the witness: at the 1.20 V point the probe reads 15 uA
PREFLIGHT_REF_OHMS = 50e3      # 15 uA into 50 kohm puts the reference node at 0.75 V
# DATA-7C-B-DC-R1: the signals the task book calls required, so a missing one is a refusal and never a
# nominal fill-in. The axis and the probe current are resolved separately by probe_column().
REQUIRED_SIGNALS = ('data_out', 'vss', 'vdd18', 'vcas', 'data_en', 'pam0', 'pam1', 'pam2', 'iref_in')
LOGIC_HIGH_V = 1.8             # the deck's logic domain high, from reports/tasks/DATA-7C-B-DC.md s4
LOGIC_LOW_V = 0.0
LOGIC_TOLERANCE_V = 0.05       # anything between these two windows is not accepted as a logic level
SUPPLY_TOLERANCE_V = 0.005
GROUND_TOLERANCE_V = 0.005
CLAMP_TRACKS_OUTPUT_V = 0.02   # data_out is the node the clamp source drives, so it tracks the axis
DECK_SOURCE_RE = re.compile(r'^([A-Za-z_]\w*)\s*\(\s*(\S+)\s+(\S+)\s*\)\s*(vsource|isource)'
                            r'\s+dc=([0-9.eE+-]+)([numk]?)\s*(?://.*)?$')
UNIT_SCALE = {'': 1.0, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3}
ROLES = ('preflight', 'dut', 'debug')
ACCOUNT_STATES = ('REQUESTED', 'CONFIRMED', 'FAILED', 'UNCERTAIN')
ACCOUNT_HEADER = ('launch_id', 'task_id', 'run_id', 'case_id', 'role', 'state', 'requested_utc',
                  'ended_utc', 'rc', 'deck_sha256', 'raw_sha256', 'log_sha256', 'refusal',
                  'ceiling', 'occupied_after')
ROWS_HEADER = ('case_id', 'code', 'role', 'clamp_V', 'data_out_V', 'I_sink_A', 'I_sink_uA',
               'vdd18_V', 'vcas_V', 'data_en_V', 'pam_bits', 'iref_source_A', 'iref_node_V', 'corner', 'temp_C',
               'deck_sha256', 'raw_sha256', 'run_id', 'launch_id', 'unit_clamp', 'unit_current')


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(io.open(path, 'rb').read())


def git(*args):
    return subprocess.check_output(['git', '-C', ROOT] + list(args)).decode('utf-8', 'replace')


def blob(rev, path):
    return subprocess.check_output(['git', '-C', ROOT, 'cat-file', 'blob', '%s:%s' % (rev, path)])


def dc_contract():
    return json.loads(io.open(os.path.join(ROOT, DC_CONTRACT.replace('/', os.sep)),
                              encoding='utf-8').read())


def criteria():
    """the frozen preparation contract is the single source of the numbers; the DC snapshot must agree"""
    prep = json.loads(io.open(os.path.join(ROOT, PREP_CONTRACT.replace('/', os.sep)),
                              encoding='utf-8').read())
    snap = dc_contract()['criteria_source']['snapshot']
    rules = prep['rules']
    live = {
        'clamp_main_eval_V': rules['clamp']['main_eval_V'],
        'sweep_start_V': rules['clamp']['sweep_start_V'],
        'sweep_step_V': rules['clamp']['sweep_step_V'],
        'sweep_stop_V': rules['clamp']['sweep_stop_V'],
        'sweep_points_expected': len(prep['clamp_sweep_points_V']),
        'full_scale_code': rules['full_scale_absolute']['code'],
        'full_scale_target_A': rules['full_scale_absolute']['target_A'],
        'full_scale_lower_A': rules['full_scale_absolute']['lower_A'],
        'full_scale_upper_A': rules['full_scale_absolute']['upper_A'],
        'unit_deviation_limit_in_units_of_iunit_ref':
            rules['eight_level_ratio']['abs_deviation_limit_in_units_of_iunit_ref'],
        'strict_monotonic_required': rules['eight_level_ratio']['strict_monotonic_required'],
        'iref_A': rules['supplies']['iref_A'],
        'vdd18_V': rules['supplies']['vdd18_V'],
        'vcas_V': rules['supplies']['vcas_V'],
        'vss_V': rules['supplies']['vss_V'],
        'temperature_statement': rules['process_corner']['deck_must_state_temperature'],
        'corner': rules['process_corner']['corner'],
        'nominal_current_identity': prep['nominal_current_identity']}
    def differs(key):
        expected, actual = snap.get(key), live[key]
        if isinstance(actual, str) or isinstance(expected, str):
            return expected != actual
        try:
            return abs(float(expected) - float(actual)) > max(abs(float(actual)) * 1e-12, 1e-18)
        except (TypeError, ValueError):
            return True
    drift = ['%s: snapshot %r, frozen contract %r' % (key, snap.get(key), live[key])
             for key in sorted(live) if differs(key)]
    return live, drift


def sweep_points():
    import decimal
    start, step, count = (criteria()[0]['sweep_start_V'], criteria()[0]['sweep_step_V'],
                          criteria()[0]['sweep_points_expected'])
    return [float(decimal.Decimal(str(start)) + decimal.Decimal(str(step)) * i)
            for i in range(count)]


# ---- authorisation, judged before anything is written -------------------------------------------

def authorisation_problem(want_role=None):
    """the marker has to be in the environment of the person running it, not in a file this script writes"""
    contract_limit = dc_contract()['authorisation']['spectre_launch_limit_total']
    if os.environ.get('QODER_DC_AUTHORISED') != '1':
        return ('DATA-7C-B-DC: this call is not authorised to start a spectre process; run '
                '--selftest / --plan / --stage instead')
    granted = os.environ.get('QODER_DC_SPECTRE_LIMIT')
    if granted is None or not granted.lstrip('-').isdigit():
        return 'QODER_DC_SPECTRE_LIMIT is %r, the approved ceiling has to be a number' % (granted,)
    if int(granted) > int(contract_limit):
        return ('QODER_DC_SPECTRE_LIMIT=%s exceeds the ceiling %s the task book recorded; the budget '
                'is not raised by an environment variable' % (granted, contract_limit))
    return ''


# ---- the derived run copies ----------------------------------------------------------------------

def delivered_deck(case_id):
    """the frozen deck bytes, read out of Git at the accepted offline SHA"""
    path = '%s/%s.scs' % (DECK_DIR, case_id)
    data = blob(BASE_SHA, path)
    disk = os.path.join(ROOT, path.replace('/', os.sep))
    if os.path.isfile(disk) and sha_bytes(data) != sha_file(disk):
        raise Refuse('the working copy of %s is not the accepted blob at %s' % (path, BASE_SHA[:12]))
    return data.decode('utf-8', 'replace'), sha_bytes(data)


class Refuse(Exception):
    """a named refusal: no process started, nothing written"""


def strip_masters():
    """the six masters with only the port-direction annotation lines removed, proved by digest equality"""
    out = []
    for name in MASTERS:
        text = blob(BASE_SHA, 'spectre/%s' % name).decode('utf-8', 'replace')
        kept, removed = B7B.strip_direction_annotations(text)
        for line in removed:
            if not B7B.DIRECTION_RE.match(line):
                raise Refuse('%s: strip_direction_annotations removed a line that is not a port '
                             'direction annotation: %r' % (name, line))
        out.append({'name': name, 'blob_sha256': sha_bytes(text.encode('utf-8')),
                    'stripped_sha256': sha_bytes(kept.encode('utf-8')),
                    'annotation_lines_removed': len(removed),
                    'lines_before': len(text.rstrip('\n').split('\n')),
                    'lines_after': len(kept.rstrip('\n').split('\n')),
                    'device_digest_equal': B7B.device_digest(kept) == B7B.device_digest(text),
                    'port_order_digest_equal': (B7B.port_order_digest(kept) ==
                                                B7B.port_order_digest(text)),
                    'removed': removed, 'text': kept})
    for row in out:
        if not (row['device_digest_equal'] and row['port_order_digest_equal']):
            raise Refuse('%s: stripping changed a device or port-order digest' % row['name'])
        if row['lines_before'] - row['lines_after'] != row['annotation_lines_removed']:
            raise Refuse('%s: the line count moved by %d but %d annotations were removed'
                         % (row['name'], row['lines_before'] - row['lines_after'],
                            row['annotation_lines_removed']))
    return out


def preflight_deck(deck_text, case_id):
    """the same case with the DUT replaced by two ideal meter loads; sources and grid stay identical"""
    lines = deck_text.rstrip('\n').split('\n')
    kept, removed_save, replaced = [], [], []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('Xdut ') and stripped.endswith('dd1_d7c_a_pam_1ch'):
            replaced.append(line)
            kept.extend(PREFLIGHT_LOAD)
            continue
        if stripped.startswith('save Xdut'):
            removed_save.append(line)
            continue
        kept.append(line)
    if len(replaced) != 1:
        raise Refuse('%s: the deck has %d Xdut lines, exactly one was expected'
                    % (case_id, len(replaced)))
    kept.insert(1, '// DERIVED BY DATA-7C-B-DC FOR THE PREFLIGHT OF %s: the one DUT line is replaced by '
                   'the two meter loads\n// below and the five hierarchical saves of the DUT are '
                   'dropped because no DUT exists here. Sources, the 19-point\n// clamp grid, the '
                   'analysis line and the probe are byte-identical to the delivered deck.\n'
                   '// The inherited first line describes the preparation round that only wrote the '
                   'text; under the user\n// approval of DATA-7C-B-DC this case does run, accounted '
                   'against a ceiling of 20 processes.' % case_id)
    return ('\n'.join(kept) + '\n'), {'dut_line_replaced': replaced,
                                      'save_lines_dropped': removed_save,
                                      'meter_loads_added': PREFLIGHT_LOAD,
                                      'load_ohms': PREFLIGHT_LOAD_OHMS,
                                      'reference_ohms': PREFLIGHT_REF_OHMS,
                                      'load_expected_A_at_main':
                                          1.2 / PREFLIGHT_LOAD_OHMS,
                                      'reference_expected_V': 1.5e-5 * PREFLIGHT_REF_OHMS}


# ---- this round's own account --------------------------------------------------------------------

class Account(object):
    """append-only, one writer, reserve before the start, no refund, ceiling 20"""

    def __init__(self, path, ceiling):
        self.path = path
        self.ceiling = int(ceiling)
        self.lock = path + '.lock'
        self.rows = []
        if os.path.isfile(path):
            first = io.open(path, encoding='utf-8', newline='').readline().strip()
            if first != ','.join(ACCOUNT_HEADER):
                raise Refuse('the account %s has header %r, this round writes %r'
                             % (os.path.basename(path), first[:60], ','.join(ACCOUNT_HEADER)))
            lines = [line for line in
                     io.open(path, encoding='utf-8', newline='').read().split('\n')[1:] if line.strip()]
            for number, line in enumerate(lines, 2):
                cells = line.split(',')
                if len(cells) != len(ACCOUNT_HEADER):
                    raise Refuse('the account row on line %d carries %d fields, the header declares '
                                 '%d; a field with a newline or a comma in it would be read as two rows'
                                 % (number, len(cells), len(ACCOUNT_HEADER)))
            self.rows = [dict(zip(ACCOUNT_HEADER, line.rstrip('\n').split(','))) for line in lines]
        self._check_ids()

    def _check_ids(self):
        seen = [row['launch_id'] for row in self.rows]
        for index, value in enumerate(seen, 1):
            if value != 'D%03d' % index:
                raise Refuse('the account jumps at row %d: id %s, expected D%03d'
                             % (index, value, index))

    def occupied(self):
        return len(self.rows)

    def remaining(self):
        return self.ceiling - self.occupied()

    def _acquire(self):
        try:
            handle = io.open(self.lock, 'x')
        except IOError:
            raise Refuse('another writer holds %s; this round runs one executor at a time'
                         % os.path.basename(self.lock))
        handle.write('%s %d\n' % (now(), os.getpid()))
        handle.close()

    def reserve(self, case_id, role, deck_sha, run_id):
        self._acquire()
        try:
            if self.occupied() >= self.ceiling:
                raise Refuse('LAUNCH_CEILING_REACHED: the account already carries %d of %d launches; '
                             'a failure costs the budget and recovery never refunds it'
                             % (self.occupied(), self.ceiling))
            row = {'launch_id': 'D%03d' % (self.occupied() + 1), 'task_id': TASK_ID, 'run_id': run_id,
                   'case_id': case_id, 'role': role, 'state': 'REQUESTED', 'requested_utc': now(),
                   'ended_utc': '', 'rc': '', 'deck_sha256': deck_sha, 'raw_sha256': '',
                   'log_sha256': '', 'refusal': '', 'ceiling': self.ceiling,
                   'occupied_after': self.occupied() + 1}
            self.rows.append(row)
            self.flush()
            return row
        finally:
            os.remove(self.lock)

    def settle(self, row, state, rc, raw_sha='', log_sha='', refusal=''):
        if state not in ACCOUNT_STATES:
            raise Refuse('state %r is not one of %s' % (state, ','.join(ACCOUNT_STATES)))
        self._acquire()
        try:
            if row not in self.rows:
                raise Refuse('settle names a launch that is not in the account')
            single_line = ' | '.join((refusal or '').splitlines()).replace(',', ';')
            row.update({'state': state, 'ended_utc': now(), 'rc': rc, 'raw_sha256': raw_sha,
                        'log_sha256': log_sha, 'refusal': single_line[:180]})
            self.flush()
        finally:
            os.remove(self.lock)

    def flush(self):
        for row in self.rows:
            for key in ACCOUNT_HEADER:
                value = str(row.get(key, ''))
                if any(marker in value for marker in (',', '\n', '\r')):
                    raise Refuse('the %s field of %s carries a table delimiter (%r); the account '
                                 'would be unreadable, so nothing is written'
                                 % (key, row['launch_id'], value[:40]))
        B7B.write_rows(self.path, [[row.get(key, '') for key in ACCOUNT_HEADER] for row in self.rows],
                       list(ACCOUNT_HEADER))
        return self.path


# ---- extraction ----------------------------------------------------------------------------------

def psf_units(path):
    """the units the native file itself declares: the sweep axis from SWEEP, every signal from TRACE"""
    axis, units, section = None, {}, None
    for raw in io.open(path, encoding='utf-8', errors='replace').read().split('\n'):
        line = raw.strip()
        if line.startswith('SWEEP'):
            section = 'sweep'
            continue
        if line.startswith('TRACE'):
            section = 'trace'
            continue
        if line.startswith('VALUE'):
            break
        if section == 'sweep':
            found = re.match(r'^"([^"]+)"\s+"sweep"', line)
            if found:
                axis = found.group(1)
            found = re.match(r'^"units"\s+"([^"]+)"', line)
            if found and axis:
                units[axis] = found.group(1)
        elif section == 'trace':
            found = re.match(r'^"([^"]+)"\s+"([^"]*)"', line)
            if found:
                units[found.group(1)] = found.group(2)
    return units


def probe_column(cols):
    """the accepted DATA-7B bench spells a probe current <name>:i; the saved alias is the second form"""
    for name in ('Ip_branch:i', 'Ip_branch:current', 'Ip_branch'):
        if name in cols:
            return name
    raise Refuse('the raw carries no Ip_branch current column, the columns are %s'
                 % ','.join(sorted(cols))[:160])


def iref_from_deck(deck_text):
    """the reference current the deck itself injects, read out of the isource line, with its unit"""
    for line in deck_text.splitlines():
        found = re.match(r'^\s*\S+\s*\([^)]*\)\s*isource\s+dc=([0-9.eE+-]+)([numk]?)\s*$',
                         line.strip())
        if found:
            return float(found.group(1)) * {'': 1.0, 'n': 1e-9, 'u': 1e-6, 'k': 1e3}[found.group(2)]
    raise Refuse('the deck declares no isource line, so the reference condition cannot be named')


def deck_static_sources(deck_text, case_id):
    """the levels this case's frozen deck drives, node by node; these are deck conditions, never
    described as observations"""
    levels, reference = {}, None
    for line in deck_text.splitlines():
        text = line.strip()
        if not text or text.startswith('//'):
            continue
        found = DECK_SOURCE_RE.match(text)
        if not found:
            continue
        _name, node_a, node_b, kind, value, suffix = found.groups()
        volts = float(value) * UNIT_SCALE[suffix]
        if kind == 'isource':
            reference = (node_a, node_b, volts)
            continue
        for node in (node_a, node_b):
            if node != '0':
                levels[node] = volts
    for node in ('vdd18', 'vcas', 'vss', 'data_en', 'pam0', 'pam1', 'pam2'):
        if node not in levels:
            raise Refuse('%s: the frozen deck declares no vsource for %s, so the condition of that '
                         'node cannot be named and a measured level cannot be checked against it'
                         % (case_id, node))
    if reference is None:
        raise Refuse('%s: the frozen deck declares no isource, so the reference condition is unknown'
                     % case_id)
    return levels, reference


def deck_corner_and_temp(deck_text, case_id):
    """corner and temperature are written in the deck, so they are reported as deck conditions"""
    corner = re.search(r'include\s+"\$\{QODER_PDK_LIB\}"\s+section=(\w+)', deck_text)
    temp = re.search(r'simopt\s+options\s+temp=([0-9.]+)', deck_text)
    if not corner or not temp:
        raise Refuse('%s: the deck carries no section= or simopt temp= line, so corner and temperature '
                     'cannot be attributed to the deck' % case_id)
    return corner.group(1).upper(), float(temp.group(1))


def logic_bit(volt, node, case_id):
    """the deck's logic domain is 1.8 V high and 0 V low; a level in between is refused rather than
    rounded up to the nearest rail, which is what let 0.9 V look like a one before"""
    if abs(volt - LOGIC_HIGH_V) <= LOGIC_TOLERANCE_V:
        return 1
    if abs(volt - LOGIC_LOW_V) <= LOGIC_TOLERANCE_V:
        return 0
    raise Refuse('%s: %s reads %r V, which is neither the deck high %g V nor the deck low %g V within '
                 '%g V, so no bit can be claimed from it'
                 % (case_id, node, volt, LOGIC_HIGH_V, LOGIC_LOW_V, LOGIC_TOLERANCE_V))


def measured_code(cols, levels, case_id):
    """the three PAM bits as measured, cross-checked against the same case's frozen deck"""
    bits = ''.join(str(logic_bit(cols['pam%d' % index][0], 'pam%d' % index, case_id))
                   for index in (2, 1, 0))
    declared = ''.join(str(logic_bit(levels['pam%d' % index], 'pam%d' % index, case_id))
                       for index in (2, 1, 0))
    if bits != declared or bits != case_id.split('-')[1]:
        raise Refuse('%s: the measured PAM levels read %s while the frozen deck drives %s and the case '
                     'is named %s; a mixed code is never published'
                     % (case_id, bits, declared, case_id.split('-')[1]))
    return bits, declared


def extract(raw_path, deck_sha, case_id, role, run_id, launch_id):
    """the 19 native rows, with units, sign and identity carried through; no nominal number and no case
    name is ever substituted for a signal the answer does not carry"""
    groups, axis = PSF.parse(raw_path)
    cols, axis_values = PSF.as_columns(groups, axis)
    units = psf_units(raw_path)
    if axis_values is None:
        raise Refuse('the sweep axis %r has no column, so the clamp voltage per point is unknown' % axis)
    if units.get(axis) != 'V':
        raise Refuse('%s: the sweep axis %s declares units %r, the clamp grid cannot be published '
                     'without volts' % (case_id, axis, units.get(axis)))
    if len(axis_values) != len(set(axis_values)):
        raise Refuse('duplicate clamp points in %s: %d rows, %d distinct'
                     % (case_id, len(axis_values), len(set(axis_values))))
    want = sweep_points()
    if len(axis_values) != len(want):
        raise Refuse('%s answered %d points, the frozen contract declares %d'
                     % (case_id, len(axis_values), len(want)))
    for point in want:
        if not any(abs(value - point) < 1e-9 for value in axis_values):
            raise Refuse('%s is missing the declared clamp point %g V' % (case_id, point))
    current = probe_column(cols)
    if units.get(current) != 'A':
        raise Refuse('%s: the probe column %s declares units %r, not amperes'
                     % (case_id, current, units.get(current)))
    missing = [name for name in REQUIRED_SIGNALS if name not in cols]
    if missing:
        raise Refuse('%s: the raw carries no column for %s, which this round declares required, so the '
                     'extraction is incomplete and a contract nominal cannot fill it'
                     % (case_id, ','.join(missing)))
    columns = (current,) + REQUIRED_SIGNALS
    wrong_unit = ['%s=%r' % (name, units.get(name)) for name in columns
                  if units.get(name) != ('A' if name == current else 'V')]
    if wrong_unit:
        raise Refuse('%s: a required column declares the wrong unit: %s' % (case_id, ', '.join(wrong_unit)))
    ragged = ['%s=%d' % (name, len(cols[name])) for name in columns
              if len(cols[name]) != len(axis_values)]
    if ragged:
        raise Refuse('%s: a required column does not span the sweep: %s' % (case_id, ', '.join(ragged)))
    non_finite = ['%s at point %g' % (name, axis_values[index]) for name in columns
                  for index in range(len(axis_values)) if not _finite(cols[name][index])]
    if non_finite:
        raise Refuse('%s: a required value is not finite: %s' % (case_id, '; '.join(non_finite[:3])))
    deck_text, deck_digest = delivered_deck(case_id)
    if role == 'preflight':
        derived, _detail = preflight_deck(deck_text, case_id)
        expect = sha_bytes(derived.encode('utf-8'))
        which = 'derived preflight copy'
    else:
        expect = deck_digest
        which = 'delivered deck'
    if deck_sha and deck_sha != expect:
        raise Refuse('%s: the deck digest handed to the extraction is %s while this case%s is %s, so '
                     'the answer and the deck are not the same object'
                     % (case_id, deck_sha[:12], which, expect[:12]))
    levels, reference = deck_static_sources(deck_text, case_id)
    corner, temp_C = deck_corner_and_temp(deck_text, case_id)
    bits, declared = measured_code(cols, levels, case_id)
    rows = []
    for index, clamp in enumerate(axis_values):
        row = {'case_id': case_id, 'code': bits, 'role': role, 'clamp_V': '%.3f' % clamp,
               'data_out_V': '%.6f' % cols['data_out'][index],
               'I_sink_A': '%.9e' % cols[current][index],
               'I_sink_uA': '%.6f' % (cols[current][index] * 1e6),
               'vdd18_V': '%.3f' % cols['vdd18'][index],
               'vcas_V': '%.3f' % cols['vcas'][index],
               'data_en_V': '%.3f' % cols['data_en'][index],
               'pam_bits': bits,
               'iref_source_A': '%.3e' % reference[2],
               'iref_node_V': '%.6f' % cols['iref_in'][index],
               'corner': corner, 'temp_C': '%g' % temp_C,
               'deck_sha256': deck_sha or expect, 'raw_sha256': sha_file(raw_path), 'run_id': run_id,
               'launch_id': launch_id, 'unit_clamp': units.get(axis, ''),
               'unit_current': units.get(current, '')}
        if abs(cols['data_out'][index] - clamp) > CLAMP_TRACKS_OUTPUT_V:
            raise Refuse('%s point %g V: data_out reads %.6f V, more than %g V from the swept clamp, so '
                         'the output is not the node this scan drives'
                         % (case_id, clamp, cols['data_out'][index], CLAMP_TRACKS_OUTPUT_V))
        if abs(cols['vss'][index] - levels['vss']) > GROUND_TOLERANCE_V:
            raise Refuse('%s point %g V: vss reads %.6f V, not the explicit %g V ground the deck drives'
                         % (case_id, clamp, cols['vss'][index], levels['vss']))
        for name, tolerance in (('vdd18', SUPPLY_TOLERANCE_V), ('vcas', SUPPLY_TOLERANCE_V),
                                ('data_en', LOGIC_TOLERANCE_V)):
            if abs(cols[name][index] - levels[name]) > tolerance:
                raise Refuse('%s point %g V: %s reads %.3f V against the frozen deck value %.3f V, which '
                             'is outside %g V' % (case_id, clamp, name, cols[name][index],
                                                  levels[name], tolerance))
        measured_bits = ''.join(str(logic_bit(cols['pam%d' % bit][index], 'pam%d' % bit, case_id))
                                for bit in (2, 1, 0))
        if measured_bits != bits:
            raise Refuse('%s: the PAM bits change along the scan (%s then %s), which a static-code DC '
                         'point cannot be' % (case_id, bits, measured_bits))
        for key in ('clamp_V', 'data_out_V', 'I_sink_A', 'iref_node_V'):
            if not _finite(row[key]):
                raise Refuse('%s point %s: %s is not finite' % (case_id, row['clamp_V'], key))
        if not row['unit_clamp'] or not row['unit_current']:
            raise Refuse('%s: a row without a declared unit cannot be published' % case_id)
        rows.append(row)
    return rows, {'axis': axis, 'probe_column': current, 'points': len(rows),
                  'units': dict((key, units[key]) for key in columns if key in units),
                  'code_measured': bits, 'code_from_deck': declared,
                  'deck_levels': dict((key, levels[key]) for key in sorted(levels)),
                  'reference_from_deck': {'from_node': reference[0], 'into_node': reference[1],
                                          'amps': reference[2]},
                  'field_origin': dict((key, 'native column %s' % columns[0]) for key in
                                       ('I_sink_A', 'I_sink_uA')),
                  'origin_rule': 'data_out_V, vdd18_V, vcas_V, data_en_V, pam_bits, iref_node_V and '
                                 'unit_* are native columns of this answer; iref_source_A, corner and '
                                 'temp_C are read out of the frozen deck and are deck conditions, not '
                                 'observations; code and pam_bits are the measured PAM levels, checked '
                                 'against the same deck'}


def _finite(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return False
    return value == value and abs(value) != float('inf')


# ---- judgement -----------------------------------------------------------------------------------

def preflight_witness(rows, deck_text, tolerance=0.02):
    """the meter readings a preflight has to give: they witness the sources, the probe sign and the
    parsing chain, and they are never reported as a PAM result"""
    main = main_point(rows)
    expected_load = criteria()[0]['clamp_main_eval_V'] / PREFLIGHT_LOAD_OHMS
    expected_reference = iref_from_deck(deck_text) * PREFLIGHT_REF_OHMS
    load = float(main['I_sink_A'])
    node = float(main['iref_node_V'])
    return {'clamp_V_of_main_point': float(main['clamp_V']), 'load_current_A': load,
            'expected_load_current_A': expected_load,
            'load_within_tolerance': abs(load - expected_load) <= tolerance * expected_load,
            'reference_node_V': node, 'expected_reference_node_V': expected_reference,
            'reference_within_tolerance': (node == node and
                                           abs(node - expected_reference)
                                           <= tolerance * expected_reference),
            'sign_note': 'positive means current flowing from the clamp node into the meter load, so '
                         'the probe and the parser agree on direction before any DUT is trusted',
            'witness_not_result': 'these are ideal meter readings, not PAM DUT currents'}


def band_of(pairs, target_A, main_V, step=0.05, fraction=0.05):
    """the largest continuous set of measured grid points, containing the evaluation point, whose SIGNED
    current stays within +/-5% of this code's own 1.20 V current. The difference is taken with the sign
    of the reading, so a point whose current has flipped direction is outside the band instead of being
    mistaken for an equal current. The neighbour outside the run is named as a measured point, never
    interpolated into a sharper boundary, and a near-zero target says so instead of dividing by it"""
    for value, current in pairs:
        if not (_finite(value) and _finite(current)):
            raise Refuse('the band cannot be taken over a non-finite point: clamp %r current %r'
                         % (value, current))
    if abs(target_A) < 1e-12:
        return {'status': 'DEGENERATE_TARGET_NEAR_ZERO', 'points': 0, 'lowest_verified_V': None,
                'adjacent_failing_V': None, 'containing_main_V': None}
    limit = fraction * abs(target_A)
    grid = [value for value, _current in pairs]
    good = dict((value, abs(current - target_A) <= limit) for value, current in pairs)
    main_index = [index for index, value in enumerate(grid) if abs(value - main_V) < 1e-9]
    if not main_index:
        raise Refuse('the %g V evaluation point is not in the measured grid' % main_V)
    if not good[grid[main_index[0]]]:
        raise Refuse('the %g V evaluation point itself fails its own band' % main_V)
    low = high = main_index[0]
    while high + 1 < len(grid) and good[grid[high + 1]] and \
            abs(grid[high + 1] - grid[high] - step) < 1e-9:
        high += 1
    while low - 1 >= 0 and good[grid[low - 1]] and abs(grid[low] - grid[low - 1] - step) < 1e-9:
        low -= 1
    below = [value for value in grid[:low] if not good[value]]
    return {'status': 'MEASURED_POINTS_ONLY', 'points': high - low + 1,
            'containing_main_V': [grid[low], grid[high]], 'lowest_verified_V': grid[low],
            'adjacent_failing_V': (max(below) if below else
                                   'NO_MEASURED_POINT_BELOW'),
            'criterion': 'abs(I(clamp) - I(%g V)) <= %g%% of I(%g V)'
                         % (main_V, fraction * 100, main_V),
            'no_extrapolation': True}


def main_point(rows, volts=1.2):
    hits = [row for row in rows if abs(float(row['clamp_V']) - volts) < 1e-9]
    if len(hits) != 1:
        raise Refuse('the 1.20 V evaluation point appears %d times, exactly once is required'
                     % len(hits))
    return hits[0]


def validate_dc_matrix(dut_rows, codes=None, points=None):
    """DATA-7C-B-DC-R1: the one gate every complete-phase DC PASS has to walk through first. It names
    the missing, extra, duplicated or malformed key instead of judging whatever rows happen to be
    present, so eight main points can never again be read as a finished 8 x 19 matrix"""
    contract = dc_contract()
    codes = list(codes if codes is not None else contract['matrix']['codes'])
    points = list(points if points is not None else sweep_points())
    expected = set((code, round(point, 3)) for code in codes for point in points)
    problems, seen = [], {}
    for number, row in enumerate(dut_rows, 1):
        if len(row) < len(ROWS_HEADER) or any(key not in row for key in ROWS_HEADER):
            problems.append('row %d does not carry all %d published columns' % (number, len(ROWS_HEADER)))
            continue
        if row['role'] != 'dut':
            problems.append('row %d has role %r inside the DUT matrix' % (number, row['role']))
        code = row['code']
        if code not in codes:
            problems.append('row %d carries code %r, which the matrix does not name' % (number, code))
            continue
        if row['pam_bits'] != code or row['case_id'] != 'DC-%s' % code:
            problems.append('row %d mixes identity: case %s, code %s, pam_bits %s'
                            % (number, row['case_id'], code, row['pam_bits']))
        try:
            clamp = round(float(row['clamp_V']), 3)
        except (TypeError, ValueError):
            problems.append('row %d has an unreadable clamp voltage %r' % (number, row['clamp_V']))
            continue
        if clamp not in [round(point, 3) for point in points]:
            problems.append('row %d sits at %s V, which is not on the frozen %g V grid'
                            % (number, row['clamp_V'], points[0]))
        for key in ('I_sink_A', 'I_sink_uA', 'data_out_V', 'iref_node_V', 'clamp_V'):
            if not _finite(row[key]):
                problems.append('row %d: %s is %r, which is not a finite number'
                                % (number, key, row[key]))
        if abs(float(row['I_sink_uA']) - float(row['I_sink_A']) * 1e6) > 5.1e-7:
            problems.append('row %d: the uA column is not the A column times 1e6' % number)
        if row['unit_clamp'] != 'V' or row['unit_current'] != 'A':
            problems.append('row %d declares units %r/%r instead of V/A'
                            % (number, row['unit_clamp'], row['unit_current']))
        if not row['deck_sha256'] or not row['raw_sha256']:
            problems.append('row %d carries no deck or raw digest, so its identity cannot be checked'
                            % number)
        key = (code, clamp)
        if key in seen:
            problems.append('the point %s at %s V appears twice, so the matrix has no unique row for it'
                            % (code, row['clamp_V']))
        seen[key] = row
    missing = sorted(expected - set(seen))
    extra = sorted(set(seen) - expected)
    if missing:
        problems.append('%d of the %d required keys are absent, starting with %s'
                        % (len(missing), len(expected),
                           ', '.join('%s at %s V' % (code, clamp) for code, clamp in missing[:3])))
    if extra:
        problems.append('%d keys are not in the declared matrix, starting with %s'
                        % (len(extra), ', '.join('%s at %s V' % (code, clamp) for code, clamp in extra[:3])))
    if problems:
        raise Refuse('the DC matrix is not complete and consistent: %s' % '; '.join(problems[:4]))
    return {'rows': len(dut_rows), 'codes': len(codes), 'points_per_code': len(points),
            'keys_expected': len(expected), 'keys_unique': len(seen),
            'rows_by_code': dict((code, [row for key, row in seen.items() if key[0] == code])
                                 for code in codes),
            'rule': '8 codes x %d declared clamp points, one unique finite row per key, role, case, '
                    'code, pam_bits, units and digests all consistent' % len(points)}


def main_point_arithmetic(rows_by_code, crit, codes):
    """the eight main evaluation points only. It answers the ladder arithmetic and never a phase verdict:
    a PASS here is not a statement that the 8 x 19 matrix was measured"""
    at_main = dict((code, float(main_point(rows_by_code[code])['I_sink_A'])) for code in codes)
    full = at_main[crit['full_scale_code']]
    iunit_ref = full / 8.0
    deviations = dict((code, at_main[code] - (int(code, 2) + 1) * iunit_ref) for code in codes)
    ladder = [at_main[code] for code in codes]
    return {'at_main_A': at_main, 'full_scale_A': full, 'iunit_ref_A': iunit_ref,
            'deviations_A': deviations,
            'strict_monotonic': all(ladder[index + 1] > ladder[index]
                                    for index in range(len(ladder) - 1)),
            'absolute_pass': crit['full_scale_lower_A'] <= full <= crit['full_scale_upper_A'],
            'ratio_pass': all(abs(deviations[code]) <= 0.25 * abs(iunit_ref) for code in codes),
            'scope': 'the eight 1.20 V points only'}


def judge(dut_rows):
    """every number the pass rests on; normalisation never rescues a short ladder and a short table
    never reaches a verdict at all"""
    matrix = validate_dc_matrix(dut_rows)
    crit = criteria()[0]
    codes = dc_contract()['matrix']['codes']
    arithmetic = main_point_arithmetic(matrix['rows_by_code'], crit, codes)
    published_matrix = dict(matrix)
    published_matrix.pop('rows_by_code', None)
    published_matrix['rows_per_code'] = dict(
        (code, len(matrix['rows_by_code'][code])) for code in codes)
    at_main, full = arithmetic['at_main_A'], arithmetic['full_scale_A']
    iunit_ref, deviations = arithmetic['iunit_ref_A'], arithmetic['deviations_A']
    bands = {}
    for code in codes:
        pairs = sorted((float(row['clamp_V']), float(row['I_sink_A']))
                       for row in matrix['rows_by_code'][code])
        bands[code] = band_of(pairs, at_main[code], crit['clamp_main_eval_V'])
    return {'verdict': 'PASS' if (arithmetic['absolute_pass'] and arithmetic['ratio_pass']
                                  and arithmetic['strict_monotonic']) else 'FAIL',
            'rows': len(dut_rows), 'matrix_validation': published_matrix,
            'main_eval_V': crit['clamp_main_eval_V'],
            'I_at_main_A_by_code': dict((code, at_main[code]) for code in codes),
            'full_scale': {'code': crit['full_scale_code'], 'measured_A': full,
                           'measured_uA': full * 1e6, 'target_uA': crit['full_scale_target_A'] * 1e6,
                           'band_uA': [crit['full_scale_lower_A'] * 1e6,
                                      crit['full_scale_upper_A'] * 1e6],
                           'pass': arithmetic['absolute_pass']},
            'iunit_ref_A': iunit_ref, 'iunit_ref_uA': iunit_ref * 1e6,
            'per_code_deviation_A': dict((code, deviations[code]) for code in codes),
            'per_code_deviation_in_iunit_ref': dict(
                (code, deviations[code] / iunit_ref if iunit_ref else None) for code in codes),
            'deviation_limit_in_iunit_ref': 0.25,
            'strict_monotonic': arithmetic['strict_monotonic'],
            'ratio_pass': arithmetic['ratio_pass'],
            'nominal_identity': crit['nominal_current_identity'],
            'band_5_percent': bands,
            'time_domain_qlsb': 'NOT_APPLICABLE_DC_HAS_NO_TIME_DOMAIN',
            'completion_level': 'NATIVE_PAM_DC_TT_MEASURED'}


# ---- the native path -----------------------------------------------------------------------------

def link_for(log_dir):
    """the accepted ssh/scp channel: the payload travels base64 and the child exit code is the answer"""
    return B7B.Link(B7B.GUEST_HOST, GUEST_PROJECT, log_dir)


def run_staging():
    directory = os.environ.get('QODER_DC_STAGING') or os.path.join(ROOT, 'review', 'scratch',
                                                                   'dc_staging')
    if not os.path.isdir(directory):
        os.makedirs(directory)
    return directory


def remote_paths(run_id):
    base = '%s/%s' % (GUEST_WORK_ROOT, run_id)
    return {'base': base, 'masters': '%s/masters' % base, 'scripts': '%s/scripts' % base,
            'cases': '%s/cases' % base}


def repo(path):
    return os.path.join(ROOT, path.replace('/', os.sep))


def emit_run_copies(write=True):
    """the derived run copies live in the repository, so a reviewer hashes exactly what was pushed"""
    directory = repo(RUN_DIR)
    account = {'generated_utc': now(), 'base_sha': BASE_SHA,
               'rule': 'only the port-direction annotation lines are removed from the masters; the '
                       'preflight deck replaces exactly one Xdut line with two meter loads and drops '
                       'the five hierarchical saves of the DUT; sources, the 19-point clamp grid, the '
                       'analysis line and the probe stay byte-identical to the delivered deck',
               'masters': [], 'decks': []}
    if write and not os.path.isdir(os.path.join(directory, 'masters')):
        os.makedirs(os.path.join(directory, 'masters'))
    for row in strip_masters():
        fields = dict((key, row[key]) for key in
                      ('name', 'blob_sha256', 'stripped_sha256', 'annotation_lines_removed',
                       'lines_before', 'lines_after', 'device_digest_equal',
                       'port_order_digest_equal'))
        fields['path'] = '%s/masters/%s' % (RUN_DIR, row['name'])
        if write:
            io.open(repo(fields['path']), 'wb').write(row['text'].encode('utf-8'))
            if sha_file(repo(fields['path'])) != row['stripped_sha256']:
                raise Refuse('the written copy of %s is not the bytes the stripper produced'
                             % row['name'])
        account['masters'].append(fields)
    for case_id in dc_contract()['matrix']['launch_order']:
        deck_text, digest = delivered_deck(case_id)
        preflight_text, derived = preflight_deck(deck_text, case_id)
        target = '%s/%s.pre.scs' % (RUN_DIR, case_id)
        if write:
            io.open(repo(target), 'wb').write(preflight_text.encode('utf-8'))
        account['decks'].append({'case_id': case_id, 'delivered_sha256': digest,
                                 'preflight_path': target,
                                 'preflight_sha256': sha_bytes(preflight_text.encode('utf-8')),
                                 'dut_line_replaced': derived['dut_line_replaced'],
                                 'save_lines_dropped': derived['save_lines_dropped'],
                                 'meter_loads_added': derived['meter_loads_added'],
                                 'load_ohms': derived['load_ohms'],
                                 'reference_expected_V': derived['reference_expected_V']})
    if write:
        io.open(repo('%s/strip_account.json' % RUN_DIR), 'wb').write(
            (json.dumps(account, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
            .encode('utf-8'))
    return account


def prepare_remote(link, run_id):
    """the executor and the stripped masters are pushed from committed bytes and hash-verified"""
    paths = remote_paths(run_id)
    rc, text = link.run('mkdir -p %s %s %s && echo STAGED_DIRS_OK'
                        % (paths['masters'], paths['scripts'], paths['cases']), 120, 'mkdir')
    if rc != 0 or 'STAGED_DIRS_OK' not in (text or ''):
        raise Refuse('the guest run directories could not be created under %s: %s'
                     % (paths['base'], (text or '').strip()[:160]))
    account = json.loads(io.open(repo('%s/strip_account.json' % RUN_DIR), encoding='utf-8').read())
    for row in account['masters']:
        if sha_file(repo(row['path'])) != row['stripped_sha256']:
            raise Refuse('%s on disk is not the byte string the strip account carries' % row['path'])
        link.push(repo(row['path']), '%s/%s' % (paths['masters'], row['name']),
                  'master-' + row['name'])
    link.push(repo('scripts/run_spectre.sh'), '%s/run_spectre.sh' % paths['scripts'], 'executor')
    return paths, sha_file(repo('scripts/run_spectre.sh'))


def deck_source(case_id, role):
    """the file that goes to the guest: the frozen delivered deck for a DUT run, the committed derived
    copy for a preflight, never a third variant"""
    path = ('%s/%s.scs' % (DECK_DIR, case_id)) if role in ('dut', 'debug') \
        else ('%s/%s.pre.scs' % (RUN_DIR, case_id))
    target = repo(path)
    if not os.path.isfile(target):
        raise Refuse('%s is not in the repository; run --emit before launching' % path)
    return target


def runner_says_ok(parsed):
    """the runner prints its fields as text, so an answer of rc='0' errors='0' has to be read as numbers"""
    try:
        return (int(str(parsed.get('rc', 'x'))) == 0
                and int(str(parsed.get('errors', 'x'))) == 0
                and '0 error' in (parsed.get('done') or '')
                and bool(parsed.get('datafile')))
    except (TypeError, ValueError):
        return False


def launch(case_id, role, out_dir, run_id, timeout=600):
    """one spectre process, accounted before it starts; a refusal here writes nothing"""
    contract = dc_contract()
    problem = authorisation_problem()
    if problem:
        return 5, {'refusal': problem, 'case_id': case_id, 'role': role, 'process_started': False}
    if case_id not in contract['matrix']['launch_order']:
        return 2, {'refusal': '%s is not one of the eight DC cases this round may run' % case_id}
    if role not in ROLES:
        return 2, {'refusal': 'role %r is not one of %s' % (role, ','.join(ROLES))}
    _text, deck_sha = delivered_deck(case_id)
    local_deck = deck_source(case_id, role)
    if role in ('dut', 'debug') and sha_file(local_deck) != deck_sha:
        return 5, {'refusal': '%s on disk is not the accepted blob %s' % (local_deck, deck_sha[:12])}
    stem = os.path.basename(local_deck)[:-4]
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    account = Account(os.path.join(out_dir, 'launch_account.csv'),
                      int(os.environ['QODER_DC_SPECTRE_LIMIT']))
    row = account.reserve(case_id, role, sha_file(local_deck), run_id)
    log_dir = os.path.join(out_dir, 'guest_logs')
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    link = link_for(log_dir)
    try:
        paths, runner_sha = prepare_remote(link, run_id)
        case_dir = '%s/%s' % (paths['cases'], stem)
        link.run('mkdir -p %s && echo CASE_DIR_OK' % case_dir, 120, 'mkdir-case')
        link.push(local_deck, '%s/%s' % (case_dir, os.path.basename(local_deck)), 'deck')
        payload = ('set -a\n. %s/spectre/pdk_local.env\nset +a\n'
                   'export PROJ=%s PDK_ENV=%s QODER_NETLIST_DIR=%s\n'
                   'LABEL=DC7CB_%s_%s bash %s/run_spectre.sh %s %d\n'
                   % (GUEST_PROJECT, GUEST_PROJECT,
                      '%s/spectre/pdk_local.env' % GUEST_PROJECT, paths['masters'],
                      case_id.replace('-', '_'), role.upper(), paths['scripts'],
                      '%s/%s' % (case_dir, os.path.basename(local_deck)), timeout))
        rc, text = link.run(payload, timeout + 120, '%s-%s' % (role, case_id))
    except Refuse as error:
        account.settle(row, 'UNCERTAIN', '', refusal='REFUSED_DURING_STAGING: %s' % error)
        return 5, {'refusal': str(error), 'launch_id': row['launch_id'], 'process_started': False}
    except RuntimeError as error:
        account.settle(row, 'UNCERTAIN', '', refusal='TRANSFER_FAILED: %s' % error)
        return 1, {'refusal': str(error), 'launch_id': row['launch_id'], 'process_started': None}
    parsed = B7B.parse_runner(text)
    raw_sha = log_sha = ''
    for key, tag in (('datafile', 'raw'), ('logfile', 'log')):
        remote = parsed.get(key) or ''
        if remote and not remote.startswith('$'):
            digest = link.pull(remote, os.path.join(out_dir, '%s_%s_%s.%s'
                                                    % (run_id, case_id, role, tag)))
            if tag == 'raw':
                raw_sha = digest
            else:
                log_sha = digest
    state = 'CONFIRMED' if (rc == 0 and runner_says_ok(parsed)) else 'FAILED'
    account.settle(row, state, rc, raw_sha=raw_sha, log_sha=log_sha,
                   refusal='' if state == 'CONFIRMED' else (text or '').strip()[-160:])
    return (0 if state == 'CONFIRMED' else 1), {'case_id': case_id, 'role': role, 'rc': rc,
                                                'launch_id': row['launch_id'], 'state': state,
                                                'deck_path': os.path.relpath(local_deck, ROOT)
                                                .replace(os.sep, '/'),
                                                'deck_sha256': sha_file(local_deck),
                                                'accepted_blob_sha256': deck_sha,
                                                'runner': parsed, 'raw_sha256': raw_sha,
                                                'log_sha256': log_sha, 'guest_base': paths['base'],
                                                'executor_sha256': runner_sha,
                                                'tail': (text or '').strip()[-300:]}


# ---- offline family ------------------------------------------------------------------------------

def synthetic_psf(path, currents, drop=None, duplicate=False, no_probe=False, axis_units='V',
                 omit=('vss',), levels=None, bad_unit=None, clamp_offset=0.999, code='000'):
    """a psfascii file with the section layout this build really writes, for the extraction tests only.

    The vss column is left out by default because the reviewer's own instrument completes this same
    fixture by inserting one vss column; a fixture that already carried it would be read as a duplicate
    and turn their instrument into an error. Pass omit=() for the complete answer the extractor requires.
    """
    points = sweep_points()
    value_levels = dict({'vdd18': 1.8, 'vcas': 1.8, 'data_en': 1.8, 'vss': 0.0,
                         'iref_in': 0.75}, **(levels or {}))
    for bit in (0, 1, 2):
        value_levels.setdefault('pam%d' % bit, 1.8 if code[2 - bit] == '1' else 0.0)
    signals = [('dc', list(points)), ('Ip_branch:i', list(currents)),
               ('data_out', [value * clamp_offset for value in points]),
               ('vdd18', [value_levels['vdd18']] * len(points)),
               ('vcas', [value_levels['vcas']] * len(points)),
               ('data_en', [value_levels['data_en']] * len(points)),
               ('pam2', [value_levels['pam2']] * len(points)),
               ('pam1', [value_levels['pam1']] * len(points)),
               ('pam0', [value_levels['pam0']] * len(points)),
               ('iref_in', [value_levels['iref_in']] * len(points)),
               ('vss', [value_levels['vss']] * len(points))]
    signals = [pair for pair in signals if pair[0] not in omit]
    if no_probe:
        signals = [pair for pair in signals if pair[0] != 'Ip_branch:i']
    if drop is not None:
        signals = [(name, [value for index, value in enumerate(values) if index != drop])
                   for name, values in signals]
    lines = ['ASCIIpsfplus', 'HEADER', '"PSFversion" "1.00"', '"analysis type" "dc"', 'SWEEP',
             '"dc" "sweep" PROP(', '"sweep_direction" 0', '"units" "%s"' % axis_units,
             '"plot" 0', '"grid" 1', ')', 'TRACE']
    for name, _values in signals[1:]:
        unit = 'A' if name.startswith('Ip_branch') else 'V'
        if bad_unit == name:
            unit = ''
        lines.append('"%s" "%s"' % (name, unit))
    lines.append('VALUE')
    for index in range(len(signals[0][1])):
        for name, values in signals:
            lines.append('"%s" %.15e' % (name, values[index]))
    if duplicate:
        for name, values in signals:
            lines.append('"%s" %.15e' % (name, values[0]))
    lines.append('END')
    io.open(path, 'wb').write(('\n'.join(lines) + '\n').encode('utf-8'))
    return path


def ladder(scale=1.0, knee=0.90, unit=1.875e-6):
    """the eight codes across the nineteen clamp points: flat above the knee, falling below it"""
    rows = []
    for code_index, code in enumerate(dc_contract()['matrix']['codes']):
        target = (code_index + 1) * unit * scale
        for value in sweep_points():
            if value >= knee:
                current = target
            elif value >= knee - 0.05:
                current = target * 0.6
            else:
                current = target * 0.05
            rows.append((code, value, current))
    return rows


def row_for(code, value, current, deck_sha):
    return {'case_id': 'DC-%s' % code, 'code': code, 'role': 'dut', 'clamp_V': '%.3f' % value,
            'data_out_V': '%.6f' % (value * 0.999), 'I_sink_A': '%.9e' % current,
            'I_sink_uA': '%.6f' % (current * 1e6), 'vdd18_V': '1.800', 'vcas_V': '1.800',
            'data_en_V': '1.800', 'pam_bits': code,
            'iref_source_A': '1.500e-05', 'iref_node_V': '0.750000',
            'corner': 'TT', 'temp_C': '27', 'deck_sha256': deck_sha, 'raw_sha256': 'x',
            'run_id': 'selftest', 'launch_id': 'D000', 'unit_clamp': 'V', 'unit_current': 'A'}


def selftest():
    """offline only: no guest, no process, no budget spent"""
    import shutil
    import tempfile
    scratch = tempfile.mkdtemp(prefix='dc-selftest-')
    cases, failures = [], []
    live, drift = criteria()

    def record(name, ok, note=''):
        cases.append(name)
        if not ok:
            failures.append('%s: %s' % (name, note or 'condition false'))

    record('contract_snapshot_matches_the_frozen_source', not drift, '; '.join(drift[:2]))
    record('grid_has_nineteen_points_and_the_main_point_is_on_it',
           len(sweep_points()) == 19 and any(abs(point - 1.2) < 1e-12 for point in sweep_points()))
    masters = strip_masters()
    record('masters_lose_only_port_direction_annotations',
           len(masters) == 6 and all(row['device_digest_equal'] and row['port_order_digest_equal']
                                     and row['lines_before'] - row['lines_after'] ==
                                     row['annotation_lines_removed'] for row in masters))
    record('annotation_line_count_is_the_reviewed_sixty_three',
           sum(row['annotation_lines_removed'] for row in masters) == 63,
           'removed %d' % sum(row['annotation_lines_removed'] for row in masters))
    deck_text, deck_sha = delivered_deck('DC-000')
    record('delivered_deck_bytes_are_the_accepted_blob',
           deck_sha == sha_file(os.path.join(ROOT, 'spectre', 'dd1_d7c_b_prep', 'DC-000.scs')))
    preflight_text, derived = preflight_deck(deck_text, 'DC-000')
    record('preflight_replaces_one_dut_line_and_drops_five_saves',
           len(derived['dut_line_replaced']) == 1 and len(derived['save_lines_dropped']) == 5
           and len(derived['meter_loads_added']) == 2,
           'dut %d saves %d' % (len(derived['dut_line_replaced']),
                                len(derived['save_lines_dropped'])))
    record('preflight_keeps_grid_analysis_probe_and_ground',
           all(token in preflight_text for token in
               ('dc_case dc dev=Vclamp param=dc start=0.600 stop=1.500 step=0.050',
                'simopt options temp=27', 'Ip_branch (clamp_node data_out) iprobe',
                'Vss (vss 0) vsource dc=0', 'include "${QODER_NETLIST_DIR}/dd1_d6_inv18.scs"'))
           and 'Xdut (' not in preflight_text and 'save Xdut' not in preflight_text)
    dry = emit_run_copies(write=False)
    record('run_copies_are_derivable_without_writing',
           len(dry['masters']) == 6 and len(dry['decks']) == 8
           and all(row['stripped_sha256'] for row in dry['masters'])
           and all(row['preflight_sha256'] != row['delivered_sha256'] for row in dry['decks']),
           'masters %d decks %d' % (len(dry['masters']), len(dry['decks'])))
    record('meter_witness_arithmetic',
           abs(derived['load_expected_A_at_main'] - 1.5e-5) < 1e-12
           and abs(derived['reference_expected_V'] - 0.75) < 1e-12
           and PREFLIGHT_LOAD_OHMS == 80e3 and PREFLIGHT_REF_OHMS == 50e3)
    good_rows = [row_for(code, value, current, deck_sha) for code, value, current in ladder()]
    verdict = judge(good_rows)
    record('a_perfect_ladder_passes_with_numbers',
           verdict['verdict'] == 'PASS' and abs(verdict['iunit_ref_uA'] - 1.875) < 1e-9
           and abs(verdict['full_scale']['measured_uA'] - 15.0) < 1e-9,
           json.dumps(verdict.get('full_scale'), sort_keys=True)[:140])
    band = verdict['band_5_percent']['000']
    record('band_reports_measured_points_and_the_neighbour_below',
           band['lowest_verified_V'] == 0.9 and band['adjacent_failing_V'] == 0.85
           and band['containing_main_V'] == [0.9, 1.5], json.dumps(band, sort_keys=True))
    short = [row_for(code, value, current * 0.5, deck_sha)
             for code, value, current in ladder()]
    half = judge(short)
    record('a_uniformly_short_ladder_is_not_rescued_by_normalisation',
           half['verdict'] == 'FAIL' and half['ratio_pass'] is True
           and half['full_scale']['pass'] is False,
           'verdict %s ratio %s absolute %s' % (half['verdict'], half['ratio_pass'],
                                               half['full_scale']['pass']))
    kinked = [dict(row) for row in good_rows]
    for row in kinked:
        if row['code'] == '010' and row['clamp_V'] == '1.200':
            row['I_sink_A'] = '%.9e' % 4.0e-5
            row['I_sink_uA'] = '%.6f' % (4.0e-5 * 1e6)
    record('a_non_monotonic_ladder_is_named', judge(kinked)['strict_monotonic'] is False)
    flipped = [dict(row) for row in good_rows]
    for row in flipped:
        if row['code'] == '111' and row['clamp_V'] == '1.200':
            row['I_sink_A'] = '%.9e' % -1.5e-5
            row['I_sink_uA'] = '-15.000000'
    answer = judge(flipped)
    record('a_negative_reading_stays_negative_and_is_not_abs_flipped',
           answer['I_at_main_A_by_code']['111'] == -1.5e-5 and answer['verdict'] == 'FAIL')
    extracted, info = extract(synthetic_psf(os.path.join(scratch, 'good.raw'),
                                            [1.875e-6] * 19, omit=()), deck_sha, 'DC-000', 'dut',
                              'selftest', 'D001')
    record('extraction_carries_units_and_names_the_probe_column',
           len(extracted) == 19 and extracted[0]['unit_clamp'] == 'V'
           and extracted[0]['unit_current'] == 'A'
           and info['probe_column'] == 'Ip_branch:i' and info['axis'] == 'dc'
           and extracted[0]['code'] == '000')
    record('the_reference_current_is_read_from_the_deck_not_the_voltage_column',
           abs(iref_from_deck(deck_text) - 1.5e-5) < 1e-18
           and extracted[0]['iref_source_A'] == '%.3e' % 1.5e-5
           and extracted[0]['iref_node_V'] != extracted[0]['iref_source_A'],
           'deck %s node %s' % (extracted[0]['iref_source_A'], extracted[0]['iref_node_V']))
    meter = [row_for('000', value, value / PREFLIGHT_LOAD_OHMS, deck_sha)
             for value in sweep_points()]
    for row in meter:
        row['iref_node_V'] = '%.6f' % 0.75
    witness = preflight_witness(meter, deck_text)
    flipped_witness = preflight_witness(
        [dict(row, I_sink_A='%.9e' % -abs(float(row['I_sink_A']))) for row in meter], deck_text)
    record('the_meter_witness_passes_only_with_the_right_sign',
           witness['load_within_tolerance'] and witness['reference_within_tolerance']
           and abs(witness['expected_load_current_A'] - 1.5e-5) < 1e-12
           and abs(witness['expected_reference_node_V'] - 0.75) < 1e-12
           and not flipped_witness['load_within_tolerance'],
           json.dumps(witness, sort_keys=True)[:160])
    refusals = (
        ('a_missing_point_is_refused',
         synthetic_psf(os.path.join(scratch, 'gap.raw'), [1.875e-6] * 19, drop=12), ''),
        ('a_duplicated_answer_is_refused',
         synthetic_psf(os.path.join(scratch, 'dup.raw'), [1.875e-6] * 19, duplicate=True), ''),
        ('a_raw_without_the_probe_column_is_refused',
         synthetic_psf(os.path.join(scratch, 'noprobe.raw'), [1.875e-6] * 19, no_probe=True),
         'Ip_branch'),
        ('a_sweep_without_declared_units_is_refused',
         synthetic_psf(os.path.join(scratch, 'nounits.raw'), [1.875e-6] * 19, axis_units=''), ''),
        ('a_non_finite_reading_is_refused',
         synthetic_psf(os.path.join(scratch, 'nan.raw'), [1.875e-6] * 18 + [float('nan')],
                       omit=()), ''),
    )
    for signal in REQUIRED_SIGNALS:
        refusals += (('%s_is_a_required_signal_not_a_contract_nominal' % signal,
                      synthetic_psf(os.path.join(scratch, 'no_%s.raw' % signal),
                                    [1.875e-6] * 19, omit=(signal,)), signal),)
    refusals += (
        ('a_column_without_a_unit_is_refused',
         synthetic_psf(os.path.join(scratch, 'badunit.raw'), [1.875e-6] * 19, omit=(),
                       bad_unit='pam1'), 'unit'),
        ('a_supply_that_differs_from_the_frozen_deck_is_refused',
         synthetic_psf(os.path.join(scratch, 'badvdd.raw'), [1.875e-6] * 19, omit=(),
                       levels={'vdd18': 1.2}), 'vdd18'),
        ('an_intermediate_logic_level_is_not_a_bit',
         synthetic_psf(os.path.join(scratch, 'halfbit.raw'), [1.875e-6] * 19, omit=(),
                       levels={'pam0': 0.9}), 'pam0'),
        ('a_code_that_is_not_the_case_is_refused',
         synthetic_psf(os.path.join(scratch, 'wrongcode.raw'), [1.875e-6] * 19, omit=(),
                       code='101'), 'PAM'),
        ('an_output_that_is_not_the_swept_node_is_refused',
         synthetic_psf(os.path.join(scratch, 'stuck.raw'), [1.875e-6] * 19, omit=(),
                       clamp_offset=0.5), 'data_out'),
    )
    for name, path, expected in refusals:
        try:
            extract(path, deck_sha, 'DC-000', 'dut', 'selftest', 'D002')
            record(name, False, 'it parsed')
        except (Refuse, ValueError) as error:
            text = str(error)
            record(name, (not expected) or expected.lower() in text.lower(), text[:70])
    mismatch_path = synthetic_psf(os.path.join(scratch, 'deck_mismatch.raw'),
                                  [1.875e-6] * 19, omit=())
    try:
        extract(mismatch_path, 'f' * 64, 'DC-000', 'dut', 'selftest', 'D002')
        record('an_answer_paired_with_the_wrong_deck_is_refused', False, 'it extracted')
    except Refuse as error:
        record('an_answer_paired_with_the_wrong_deck_is_refused',
               'not the same object' in str(error), str(error)[:80])
    eight_only = [row for row in good_rows if row['clamp_V'] == '1.200']
    for name, rows in (
            ('eight_main_points_are_not_a_complete_matrix', eight_only),
            ('one_row_short_of_the_matrix_is_refused', good_rows[:-1]),
            ('one_extra_point_is_refused', good_rows + [dict(good_rows[0], clamp_V='1.550')]),
            ('a_duplicate_replacing_a_missing_point_is_refused',
             [dict(row, clamp_V='0.600') if row is good_rows[-1] else row for row in good_rows]),
            ('a_row_without_a_unit_is_refused',
             [dict(row, unit_current='') if row is good_rows[0] else row for row in good_rows]),
            ('a_row_that_lost_a_column_is_refused',
             [dict((key, value) for key, value in row.items() if key != 'pam_bits')
              if row is good_rows[0] else row for row in good_rows]),
            ('a_code_not_in_the_matrix_is_refused',
             [dict(row, code='222') if row is good_rows[0] else row for row in good_rows])):
        try:
            answer = judge(rows)
            record(name, False, 'it returned verdict %s over %d rows'
                   % (answer['verdict'], len(rows)))
        except Refuse as error:
            record(name, 'matrix' in str(error).lower(), str(error)[:80])
    codes = dc_contract()['matrix']['codes']
    record('the_main_point_arithmetic_alone_is_not_a_phase_verdict',
           'verdict' not in main_point_arithmetic(
               dict((code, [row for row in good_rows if row['code'] == code
                            and row['clamp_V'] == '1.200']) for code in codes),
               criteria()[0], codes))
    flat = [row_for(code, value, (index + 1) * 1.875e-6, deck_sha)
             for index, code in enumerate(codes) for value in sweep_points()]
    signed_low = [dict(row, I_sink_A='%.9e' % -abs(float(row['I_sink_A'])),
                       I_sink_uA='%.6f' % -abs(float(row['I_sink_uA'])))
                  if row['clamp_V'] == '0.600' else row for row in flat]
    signed_answer = judge(signed_low)
    record('a_signed_over_band_point_narrows_the_measured_interval',
           all(item['lowest_verified_V'] == 0.65 and item['adjacent_failing_V'] == 0.60
               for item in signed_answer['band_5_percent'].values())
           and signed_answer['verdict'] == 'PASS'
           and all(item['lowest_verified_V'] == 0.60
                   for item in judge(flat)['band_5_percent'].values()),
           'lowest %s, neighbour %s' % (
               sorted(set(item['lowest_verified_V'] for item in
                          signed_answer['band_5_percent'].values())),
               sorted(set(str(item['adjacent_failing_V']) for item in
                          signed_answer['band_5_percent'].values()))))
    blown = [dict(row, I_sink_A='%.9e' % (float(row['I_sink_A']) * 2.0),
                  I_sink_uA='%.6f' % (float(row['I_sink_uA']) * 2.0))
             if row['clamp_V'] == '1.000' else row for row in flat]
    blown_answer = judge(blown)
    record('a_mid_scan_break_splits_the_interval_at_a_measured_point',
           all(item['containing_main_V'] == [1.05, 1.5] and item['adjacent_failing_V'] == 1.0
               for item in blown_answer['band_5_percent'].values()),
           json.dumps([blown_answer['band_5_percent']['000']['containing_main_V'],
                       blown_answer['band_5_percent']['000']['adjacent_failing_V']]))
    try:
        band_of([(0.6, float('nan')), (0.65, 1e-6)], 1e-6, 1.2)
        record('a_non_finite_point_is_not_an_ordinary_band_failure', False, 'the band accepted it')
    except Refuse as error:
        record('a_non_finite_point_is_not_an_ordinary_band_failure', 'finite' in str(error),
               str(error)[:70])
    granted = os.environ.pop('QODER_DC_AUTHORISED', None)
    record('an_unauthorised_call_refuses', bool(authorisation_problem()))
    os.environ['QODER_DC_AUTHORISED'] = '1'
    os.environ['QODER_DC_SPECTRE_LIMIT'] = '40'
    record('an_environment_variable_cannot_raise_the_ceiling',
           'ceiling' in authorisation_problem(), authorisation_problem()[:80])
    os.environ['QODER_DC_SPECTRE_LIMIT'] = '20'
    record('the_granted_ceiling_is_accepted', authorisation_problem() == '')
    cold = os.path.join(scratch, 'unauthorised')
    os.environ.pop('QODER_DC_AUTHORISED')
    code, facts = launch('DC-000', 'dut', cold, 'selftest')
    record('refusal_before_any_write', code == 5 and not os.path.isdir(cold)
           and facts.get('process_started') is False,
           'rc %s dir %s' % (code, os.path.isdir(cold)))
    os.environ['QODER_DC_AUTHORISED'] = '1'
    account = Account(os.path.join(scratch, 'account.csv'), 2)
    first = account.reserve('DC-000', 'preflight', deck_sha, 'selftest')
    account.settle(first, 'FAILED', 1, refusal='synthetic')
    second = account.reserve('DC-000', 'dut', deck_sha, 'selftest')
    try:
        account.reserve('DC-111', 'dut', deck_sha, 'selftest')
        record('a_failure_costs_the_budget_and_recovery_never_refunds', False, 'a third reserve '
               'passed')
    except Refuse as error:
        record('a_failure_costs_the_budget_and_recovery_never_refunds',
               'LAUNCH_CEILING_REACHED' in str(error), str(error)[:80])
    reopened = Account(os.path.join(scratch, 'account.csv'), 2)
    record('recovery_keeps_both_rows_and_stays_at_the_ceiling',
           reopened.occupied() == 2 and reopened.remaining() == 0)
    try:
        reopened.settle(second, 'BORROWED', 0)
        record('an_unknown_account_state_is_refused', False, 'it settled')
    except Refuse as error:
        record('an_unknown_account_state_is_refused', 'state' in str(error).lower(),
               str(error)[:60])
    tampered = os.path.join(scratch, 'gapped.csv')
    shutil.copyfile(os.path.join(scratch, 'account.csv'), tampered)
    text = io.open(tampered, encoding='utf-8', newline='').read().replace('D002,', 'D009,')
    io.open(tampered, 'wb').write(text.encode('utf-8'))
    try:
        Account(tampered, 2)
        record('a_gapped_launch_id_sequence_is_refused', False, 'it reopened')
    except Refuse as error:
        record('a_gapped_launch_id_sequence_is_refused', 'jump' in str(error).lower(),
               str(error)[:60])
    record('the_runner_answer_is_read_as_text_fields_not_objects',
           runner_says_ok({'rc': '0', 'errors': '0', 'done': 'spectre completes with 0 error',
                           'datafile': '/x/y.raw/dc_case.dc'})
           and not runner_says_ok({'rc': '0', 'errors': '2',
                                   'done': 'spectre completes with 2 errors', 'datafile': '/x'})
           and not runner_says_ok({'rc': '2', 'errors': '0', 'done': 'x 0 error',
                                   'datafile': '/x'}))
    multiline = Account(os.path.join(scratch, 'multiline.csv'), 3)
    entry = multiline.reserve('DC-000', 'preflight', deck_sha, 'selftest')
    multiline.settle(entry, 'FAILED', 0, refusal='line one\nline two, with a comma')
    reread = Account(os.path.join(scratch, 'multiline.csv'), 3)
    record('a_runner_tail_cannot_break_the_account_table',
           reread.occupied() == 1 and reread.rows[0]['refusal'].startswith('line one | line two')
           and ',' not in reread.rows[0]['refusal'], reread.rows[0]['refusal'][:60])
    poisoned = os.path.join(scratch, 'poisoned.csv')
    io.open(poisoned, 'wb').write((','.join(ACCOUNT_HEADER) + '\n' +
                                   ','.join(['D001', TASK_ID, 'r', 'DC-000', 'dut', 'REQUESTED',
                                             'x', '', '', '', '', '', 'has, a comma', '20',
                                             '1']) + '\n').encode('utf-8'))
    try:
        Account(poisoned, 20)
        record('a_row_split_by_an_extra_delimiter_is_refused_on_read', False, 'it opened')
    except Refuse as error:
        record('a_row_split_by_an_extra_delimiter_is_refused_on_read', 'fields' in str(error),
               str(error)[:60])
    try:
        reopened.rows[0]['case_id'] = 'DC-000,DC-111'
        reopened.flush()
        record('a_field_carrying_a_comma_is_refused_before_write', False, 'it flushed')
    except Refuse as error:
        record('a_field_carrying_a_comma_is_refused_before_write', 'delimiter' in str(error),
               str(error)[:60])
    ok_row = RENDER.nominal_unit_row('111', 8, 1.5e-05)
    record('the_uA_column_prints_microamperes',
           abs(RENDER.unit_field(ok_row, 'uA') - 15.0) < 1e-9)
    record('the_old_rendering_would_be_caught',
           abs(RENDER.unit_field('| `111` | 8 | 15.000 | 1.5e-05 A = 1.5e+10 fA = '
                                 '1.5e-05 uA |', 'uA') - 15.0) > 1e-9)
    shutil.rmtree(scratch, ignore_errors=True)
    print('DC_SELFTEST: %s (%d/%d named exactly, failures: %s, evidence OFFLINE_NO_PROCESS)'
          % ('PASS' if not failures else 'FAIL', len(cases), len(cases),
             '; '.join(failures) if failures else 'none'))
    for line in failures:
        print('  FAIL ' + line)
    return 0 if not failures else 1


# ---- cli -----------------------------------------------------------------------------------------

def print_masters():
    rows = strip_masters()
    total = sum(row['annotation_lines_removed'] for row in rows)
    print('DC_MASTERS %d files, %d port-direction annotation lines removed, device and port-order '
          'digests equal in every file' % (len(rows), total))
    for row in rows:
        print('  %-28s lines %d->%d removed %2d blob %s stripped %s'
              % (row['name'], row['lines_before'], row['lines_after'],
                 row['annotation_lines_removed'], row['blob_sha256'][:12],
                 row['stripped_sha256'][:12]))
    return 0


def print_plan():
    contract = dc_contract()
    authorisation = contract['authorisation']
    print('DC_PLAN ceiling %s = %s preflight + %s dut + %s debug'
          % (authorisation['spectre_launch_limit_total'], authorisation['preflight_runs'],
             authorisation['dut_runs'], authorisation['debug_margin']))
    print('DC_PLAN order %s' % ','.join(contract['matrix']['launch_order']))
    for case_id in contract['matrix']['launch_order']:
        _text, digest = delivered_deck(case_id)
        print('  %-8s deck blob %s  %d grid points  main eval 1.20 V'
              % (case_id, digest[:12], len(sweep_points())))
    return 0


def print_account(path):
    account = Account(path, dc_contract()['authorisation']['spectre_launch_limit_total'])
    print('DC_ACCOUNT %s rows=%d ceiling=%d remaining=%d %s'
          % (os.path.basename(path), account.occupied(), account.ceiling, account.remaining(),
             ' '.join('%s=%d' % (state, sum(1 for row in account.rows
                                            if row['state'] == state)) for state in ACCOUNT_STATES)))
    for row in account.rows:
        print('  %s %-8s %-9s %-10s rc=%-4s deck=%s raw=%s %s'
              % (row['launch_id'], row['case_id'], row['role'], row['state'], row['rc'],
                 (row['deck_sha256'] or '-')[:8], (row['raw_sha256'] or '-')[:8],
                 (row['refusal'] or '')[:70]))
    return 0 if account.occupied() <= account.ceiling else 1


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--selftest', action='store_true')
    parser.add_argument('--masters', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--emit', action='store_true')
    parser.add_argument('--account', default='')
    parser.add_argument('--launch', default='')
    parser.add_argument('--role', default='dut', choices=ROLES)
    parser.add_argument('--out', default='')
    parser.add_argument('--run-id', default='')
    parser.add_argument('--extract', default='')
    parser.add_argument('--case', default='')
    parser.add_argument('--deck-sha', default='')
    parser.add_argument('--judge', default='')
    arguments = parser.parse_args(argv)
    if arguments.selftest:
        return selftest()
    if arguments.masters:
        return print_masters()
    if arguments.plan:
        return print_plan()
    if arguments.emit:
        account = emit_run_copies()
        print('DC_EMIT masters %d files with %d annotation lines removed, preflight decks %d, '
              'account %s/strip_account.json (all written under the repository, all hash-verified)'
              % (len(account['masters']),
                 sum(row['annotation_lines_removed'] for row in account['masters']),
                 len(account['decks']), RUN_DIR))
        return 0
    if arguments.account:
        return print_account(arguments.account)
    if arguments.launch:
        if not arguments.out:
            print('DC_REFUSED --out is required so an account can never land on a default evidenc'
                  'e path')
            return 2
        code, facts = launch(arguments.launch, arguments.role, os.path.abspath(arguments.out),
                             arguments.run_id or time.strftime('r%Y%m%d_%H%M%S', time.gmtime()))
        print('DC_LAUNCH %s' % json.dumps(facts, sort_keys=True, default=str))
        return code
    if arguments.extract:
        try:
            rows, info = extract(arguments.extract, arguments.deck_sha, arguments.case, arguments.role,
                                 arguments.run_id or 'manual', 'D000')
        except Refuse as error:
            print('DC_EXTRACT_REFUSED %s' % error)
            return 1
        target = os.path.join(arguments.out or run_staging(),
                              'rows_%s_%s.csv' % (arguments.case, arguments.role))
        B7B.write_rows(target, [[row[key] for key in ROWS_HEADER] for row in rows],
                       list(ROWS_HEADER))
        print('DC_EXTRACT %s rows=%d axis=%s probe=%s -> %s'
              % (arguments.case, len(rows), info['axis'], info['probe_column'], target))
        return 0
    if arguments.judge:
        table = [line.rstrip('\n').split(',') for line in
                 io.open(arguments.judge, encoding='utf-8', newline='').read().split('\n')
                 if line.strip()]
        rows = [dict(zip(table[0], cells)) for cells in table[1:]]
        try:
            result = judge([row for row in rows if row['role'] == 'dut'])
        except Refuse as error:
            print('DC_JUDGE_REFUSED %s' % error)
            return 1
        print('DC_JUDGE %s' % json.dumps(result, sort_keys=True, indent=1))
        return 0 if result['verdict'] == 'PASS' else 1
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
