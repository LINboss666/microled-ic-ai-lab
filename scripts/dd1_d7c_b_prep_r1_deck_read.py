#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_b_prep_r1_deck_read.py -- read the delivered decks the way a reviewer would.

DATA-7C-B-PREP-R1 sections 3 and 4.3. The PREP round's deck audit lived inside the generator, so every
expectation it checked came from the same module that wrote the bytes: the review could call it green
while the decks still ramped a PAM code across the emission window and still measured "leakage" over a
stretch where DATA_EN sat at 0.9 V. This module keeps nothing of that. It opens the files under
`spectre/dd1_d7c_b_prep/`, parses them with its own regexes, and its only other inputs are the tables
the reviewer also has (`schedule.csv`, `windows.csv`, `contract.json`) as *claims to be tested*. It
does not import the generator, the measurement core or `dd1_d7c_b_prep_deckgen`, and it spells the bit
weights out as a literal: pam0 weight 1, pam1 weight 2, pam2 weight 4, each multiplied by the declared
1.8 V domain.

What it proves per deck:

  * a condition is a statement, not a comment: `simopt options temp=27`, exactly one named `dc` or
    `tran` analysis whose numbers are parsed and compared to the row, one iprobe with the contracted
    terminal order, the configurable PDK include, the explicit 0 V return for vss;
  * the eight codes map one-to-one onto three rail levels read off the deck -- as `vsource dc=` for a
    DC case and as the level the deck's own PWL holds during each platform for a transient one;
  * every linear segment of the enable is measured: the 50% points are interpolated from the wave and
    must be exactly the platform edges the table declares, one-to-one and in order, with the ramp a
    single segment between the two declared ramp endpoints;
  * every segment in which a PAM level changes must lie wholly inside a stretch where DATA_EN is 0 at
    both endpoints and at every vertex in between, must not overlap a declared emission window or a
    declared off-tail window, and must be a 2 ns edge centred on its declared code-change instant;
  * every leakage sub-window must be fully inside a zero-DATA_EN stretch and must not contain the next
    rising ramp, because a window that reaches an edge has to refuse the configuration rather than be
    truncated to fit.

The two counterexamples section 4.3 keeps are run on copies: a TR-LONG deck rewritten with the old long
ramp (the PREP shape, where the wave crosses half rail 25 ns away from the declared edge) and a coherent
schedule+windows copy whose first leakage window reaches into the next enable. Neither touches the
delivered tree, and the scratch directory is refused if it resolves inside the repository.
"""

from __future__ import absolute_import, print_function

import argparse
import csv
import io
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DECK_DIR = 'spectre/dd1_d7c_b_prep'
SCHEDULE_TABLE = 'tests/dd1_d7c_b_prep/schedule.csv'
WINDOWS_TABLE = 'tests/dd1_d7c_b_prep/windows.csv'
CONTRACT_JSON = 'tests/dd1_d7c_b_prep/contract.json'

# the bit weights spelled out here rather than imported: this module is the independent reading
BIT_WEIGHT = {'pam0': 1, 'pam1': 2, 'pam2': 4}
SHIFT = {1: 0, 2: 1, 4: 2}
CODES = ('000', '001', '010', '011', '100', '101', '110', '111')
WINDOW_LETTER = {'W': 'emission', 'F': 'emission_flat', 'T': 'off_tail',
                 'O': 'pure_off', 'L': 'leak_last100'}
DECLARED_COLUMN = {'W': ('full_window_start_ns', 'full_window_stop_ns'),
                   'F': ('flat_start_ns', 'flat_stop_ns'),
                   'T': ('tail_start_ns', 'tail_stop_ns'),
                   'O': ('pure_off_start_ns', 'pure_off_stop_ns'),
                   'L': ('leak_window_ns', 'leak_window_ns')}
# the four candidate masters section 7 freezes; a deck that drops one of them loses its provenance
CANDIDATE_MASTERS = ('dd1_d7c_a_gates.scs', 'dd1_d7c_a_pam_dec.scs', 'dd1_d7c_a_sink_unit.scs',
                     'dd1_d7c_a_pam_top.scs')
# the columns each of these rules reads: a tree whose table lacks them cannot be read at all, and
# saying which ones moved is the honest answer rather than a crash or an empty problem list
REQUIRED_COLUMNS = ('pam_code', 'data_en_level_V', 'edge_ns', 'rise_low_ns', 'rise_high_ns',
                    'fall_high_ns', 'fall_low_ns', 'enable_rise_50_ns', 'enable_fall_50_ns',
                    'full_window_start_ns', 'full_window_stop_ns', 'flat_start_ns', 'flat_stop_ns',
                    'tail_start_ns', 'tail_stop_ns', 'pure_off_start_ns', 'pure_off_stop_ns',
                    'off_window_ns',
                    'leak_window_ns', 'code_change_ns', 'stop_ns', 'maxstep_ns', 'analysis_name')
# the contract fields every expectation of this reader is stated in; a tree whose contract does not
# carry them is refused by name instead of being judged against expectations the reader invented
REQUIRED_CONTRACT = ('units.logic_high_V', 'units.edge_ns', 'units.lead_off_ns',
                     'units.transient_offset_ns', 'rules.enable_edges.code_change_edge_total_ns',
                     'rules.process_corner.temperature_C', 'rules.supplies.vdd18_V',
                     'rules.supplies.vcas_V', 'rules.supplies.iref_A', 'rules.clamp.main_eval_V',
                     'rules.clamp.sweep_start_V', 'rules.clamp.sweep_stop_V',
                     'rules.clamp.sweep_step_V', 'rules.shutoff_leakage.tail_last_ns',
                     'clamp_sweep_points_V', 'frozen_candidate_dut')


def missing_fields(contract):
    out = []
    for path in REQUIRED_CONTRACT:
        node = contract
        for part in path.split('.'):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                out.append(path)
                break
    return out

STATEMENT_PWL = re.compile(r'^(\w+)\s+\((\w+)\s+(\w+)\)\s+vsource\s+type=pwl\s+wave=\[(.*)\]\s*$')
STATEMENT_DC = re.compile(r'^(\w+)\s+\((\w+)\s+(\w+)\)\s+vsource\s+dc=(\S+)$')
STATEMENT_ISOURCE = re.compile(r'^(\w+)\s+\((\w+)\s+(\w+)\)\s+isource\s+dc=(\S+)$')
STATEMENT_TEMP = re.compile(r'^simopt\s+options\s+temp=(-?\d+(?:\.\d+)?)\s*$')
STATEMENT_ANALYSIS = re.compile(r'^(\w+)\s+(dc|tran)\s+(.*\S)\s*$')
STATEMENT_PROBE = re.compile(r'^Ip_branch\s+\(([^)]*)\)\s+iprobe\b')
STATEMENT_INCLUDE = re.compile(r'^include\s+"([^"]+)"(?:\s+(\S+))?\s*$')
STATEMENT_SAVE = re.compile(r'^save\s+(.*\S)\s*$')
STATEMENT_INSTANCE = re.compile(r'^(\w+)\s+\(([^)]*)\)\s+(\w+)\s*$')
TIME_TOKEN = re.compile(r'^\d+n$')

TOLERANCE_NS = 1e-6
TOLERANCE_V = 1e-9
TOLERANCE_S = 1e-15


def statements(text):
    """executable lines only: a comment never becomes a condition in this reading"""
    out = []
    for line in text.split('\n'):
        body = line.split('//')[0].strip()
        if body:
            out.append(body)
    return out


def parse_wave(body):
    """`0n 0.000 1000n 0.000 ...` -> [(ns, V)], refusing anything but pairs of whole nanoseconds"""
    tokens = body.split()
    if len(tokens) % 2:
        raise ValueError('the wave list holds %d tokens, not pairs of (time, value)' % len(tokens))
    pairs = []
    for index in range(0, len(tokens), 2):
        raw = tokens[index]
        if not TIME_TOKEN.match(raw):
            raise ValueError('PWL time %r is not a whole number of nanoseconds written as <int>n' % raw)
        pairs.append((float(raw[:-1]), float(tokens[index + 1])))
    return pairs


def segments(pairs):
    return [(t0, v0, t1, v1) for (t0, v0), (t1, v1) in zip(pairs, pairs[1:])]


def value_at(pairs, at_ns):
    """the level the deck's own waveform holds at an instant; the last vertex holds to infinity"""
    if not pairs or at_ns < pairs[0][0]:
        return None
    for t0, v0, t1, v1 in segments(pairs):
        if t0 <= at_ns <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (at_ns - t0) / (t1 - t0)
    return pairs[-1][1]


def crossings(pairs, level):
    """every interpolated crossing of `level`, with its direction, in time order"""
    found = []
    for t0, v0, t1, v1 in segments(pairs):
        if v0 == v1 or (v0 - level) * (v1 - level) > 0:
            continue
        found.append((t0 + (level - v0) * (t1 - t0) / (v1 - v0), 'rise' if v1 > v0 else 'fall'))
    return found


def rail_spans(pairs, low, high):
    """(start, stop, width) of every single segment that runs rail to rail"""
    return [(t0, t1, t1 - t0) for t0, v0, t1, v1 in segments(pairs)
            if v0 != v1 and {v0, v1} == {low, high}]


def is_low_throughout(pairs, start, stop, low=0.0):
    """(ok, reason): the waveform sits at `low` over the whole closed interval, read vertex by vertex"""
    if not pairs:
        return False, 'the waveform does not exist'
    if start > stop:
        return False, 'the interval %s-%s ns runs backwards' % (_g(start), _g(stop))
    before = value_at(pairs, start)
    after = value_at(pairs, stop)
    if before != low or after != low:
        return False, 'it holds %s V at %s ns and %s V at %s ns' % (_g(before), _g(start),
                                                                   _g(after), _g(stop))
    for t0, v0, t1, v1 in segments(pairs):
        if t1 <= start or t0 >= stop:
            continue
        if v0 != low or v1 != low:
            return False, 'the segment %s-%s ns carries %s V -> %s V across it' % (
                _g(t0), _g(t1), _g(v0), _g(v1))
    return True, ''


def adjacent(pairs, t0, t1):
    """the two instants are consecutive vertices of the wave, so nothing bends the line between them"""
    return any(a == t0 and b == t1 for a, _v0, b, _v1 in segments(pairs))


def split_list(cell):
    return [part for part in cell.split(';') if part]


def split_times(cell):
    """`2400.000-2500.000;3900.000-4000.000` -> [(2400.0, 2500.0), ...]"""
    out = []
    for part in split_list(cell):
        if '-' not in part:
            raise ValueError('the time interval %r has no dash' % part)
        low, high = part.split('-', 1)
        out.append((float(low), float(high)))
    return out


def _floats(cell):
    return [float(part) for part in split_list(cell)]


def _g(value):
    return 'nothing' if value is None else '%g' % float(value)


def deck_codes(row):
    """the code list of a case as the table declares it, resolved without asking the generator"""
    cell = row['pam_code']
    if cell == '000..111':
        return list(CODES)
    return cell.split(',')


def parse_arguments(text):
    """`stop=1530.000n maxstep=2.000n` -> {'stop': '1530.000n', 'maxstep': '2.000n'}"""
    out = {}
    for part in text.split():
        if '=' not in part:
            out[part] = True
            continue
        key, value = part.split('=', 1)
        if not re.match(r'^\w+$', key):
            raise ValueError('the analysis argument %r has no readable key' % part)
        out[key] = value
    return out


def read_deck(path):
    """the deck as delivered, classified by statement kind with nothing inferred"""
    with io.open(path, encoding='utf-8', newline='') as handle:
        text = handle.read()
    reader = {'path': path, 'text': text, 'has_cr': '\r' in text, 'waves': {}, 'dc': {},
              'isources': {}, 'temps': [], 'analyses': [], 'probes': [], 'includes': [],
              'saves': [], 'instances': [], 'unclassified': []}
    for line in statements(text):
        match = STATEMENT_PWL.match(line)
        if match:
            reader['waves'][match.group(2)] = parse_wave(match.group(4))
            continue
        match = STATEMENT_DC.match(line)
        if match:
            reader['dc'][match.group(2)] = float(match.group(4))
            continue
        match = STATEMENT_ISOURCE.match(line)
        if match:
            reader['isources'][match.group(2)] = match.group(4)
            reader['isources'][match.group(3)] = match.group(4)
            continue
        match = STATEMENT_TEMP.match(line)
        if match:
            reader['temps'].append(float(match.group(1)))
            continue
        match = STATEMENT_ANALYSIS.match(line)
        if match:
            reader['analyses'].append((match.group(1), match.group(2),
                                       parse_arguments(match.group(3))))
            continue
        match = STATEMENT_PROBE.match(line)
        if match:
            reader['probes'].append(match.group(1).split())
            continue
        match = STATEMENT_INCLUDE.match(line)
        if match:
            reader['includes'].append((match.group(1), match.group(2) or ''))
            continue
        match = STATEMENT_SAVE.match(line)
        if match:
            reader['saves'].append(match.group(1).split())
            continue
        match = STATEMENT_INSTANCE.match(line)
        if match:
            reader['instances'].append((match.group(1), match.group(2).split(), match.group(3)))
            continue
        if line.startswith('simulator'):
            continue
        reader['unclassified'].append(line)
    return reader


def bit_level(code, weight, rail):
    """the voltage a bit has to carry: its weight of the code, times the declared logic domain"""
    return (((int(code, 2) >> SHIFT[weight]) & 1) * rail)


def number_from_token(token):
    """a deck value with its own unit suffix resolved: 1530.000n becomes seconds, 0.600 stays volts"""
    for suffix, scale in (('f', 1e-15), ('p', 1e-12), ('n', 1e-9), ('u', 1e-6), ('m', 1e-3)):
        if token.endswith(suffix):
            return float(token[:-1]) * scale
    return float(token)


def _check_statements(case_id, reader, contract, directory):
    """the condition statements, read without needing any timing column from the schedule"""
    problems = []
    temperature = float(contract['rules']['process_corner']['temperature_C'])
    deck = '%s.scs' % case_id
    problems.extend(check_provenance(deck, reader, contract, directory))
    if reader['has_cr']:
        problems.append('%s carries CR bytes' % deck)
    if reader['unclassified']:
        problems.append('%s has %d statement lines this reader cannot classify, starting with %r'
                        % (deck, len(reader['unclassified']), reader['unclassified'][0][:70]))
    if reader['temps'] != [temperature]:
        problems.append('%s declares the temperature statements %s; the contract wants exactly one '
                        '`simopt options temp=%g`' % (deck, reader['temps'], temperature))
    if len(reader['probes']) != 1:
        problems.append('%s declares %d iprobe statements, one case needs exactly one'
                        % (deck, len(reader['probes'])))
    elif reader['probes'][0] != ['clamp_node', 'data_out']:
        problems.append('%s writes the probe terminals %s; the contracted order is (clamp_node '
                        'data_out)' % (deck, ' '.join(reader['probes'][0])))
    if ('${QODER_PDK_LIB}', 'section=tt') not in reader['includes']:
        problems.append('%s does not keep the PDK path and model section configurable' % deck)
    if reader['dc'].get('vss') != 0.0:
        problems.append('%s has no explicit `Vss (vss 0) vsource dc=0`, which is how every NMOS path '
                        'disappears' % deck)
    if reader['isources'].get('iref_in') != _si(contract['rules']['supplies']['iref_A']):
        problems.append('%s biases the reference with dc=%s, the contract declares %s A'
                        % (deck, reader['isources'].get('iref_in'),
                           contract['rules']['supplies']['iref_A']))
    for node, want in (('vdd18', contract['rules']['supplies']['vdd18_V']),
                       ('vcas', contract['rules']['supplies']['vcas_V']),
                       ('clamp_node', contract['rules']['clamp']['main_eval_V'])):
        if reader['dc'].get(node) != float(want):
            problems.append('%s ties %s to %s V, the contract says %s V'
                            % (deck, node, _g(reader['dc'].get(node)), want))
    if len(reader['analyses']) != 1:
        problems.append('%s declares %d active analysis lines: %s'
                        % (deck, len(reader['analyses']), [item[1] for item in reader['analyses']]))
    return problems


def check_deck(case_id, reader, row, windows, contract, directory):
    """one delivered deck against the three tables; every problem names the file and the rule"""
    problems = []
    rail = float(contract['units']['logic_high_V'])
    deck = '%s.scs' % case_id
    problems.extend(_check_statements(case_id, reader, contract, directory))
    if len(reader['analyses']) != 1:
        return problems
    instance, kind, arguments = reader['analyses'][0]
    if instance != row['analysis_name']:
        problems.append('%s runs the analysis named %s, the schedule row names it %s'
                        % (deck, instance, row['analysis_name']))
    wanted_kind = 'dc' if row['class'] == 'dc_sweep' else 'tran'
    if kind != wanted_kind:
        problems.append('%s is a %s case written as a %s analysis' % (deck, row['class'], kind))
        return problems
    if kind == 'dc':
        problems.extend(_check_dc(deck, reader, row, arguments, contract, rail))
    else:
        problems.extend(_check_transient(deck, reader, row, windows, arguments, contract, rail))
    return problems


def _si(value):
    """the contract's ampere written the way a deck spells it: 1.5e-05 A becomes 15u"""
    value = float(value)
    for scale, suffix in ((1e-15, 'f'), (1e-12, 'p'), (1e-9, 'n'), (1e-6, 'u'), (1e-3, 'm')):
        if scale <= abs(value) < scale * 1000:
            return ('%g' % (value / scale)) + suffix
    return '%g' % value


def _check_dc(deck, reader, row, arguments, contract, rail):
    problems = []
    rules = contract['rules']
    for key, want in (('dev', 'Vclamp'), ('param', 'dc')):
        if arguments.get(key) != want:
            problems.append('%s sweep reads %s=%s, it has to be %s=%s'
                            % (deck, key, arguments.get(key), key, want))
    sweep = rules['clamp']
    for key, want in (('start', sweep['sweep_start_V']), ('stop', sweep['sweep_stop_V']),
                      ('step', sweep['sweep_step_V'])):
        token = arguments.get(key)
        if token is None:
            problems.append('%s sweep states no %s' % (deck, key))
        elif abs(float(token) - float(want)) > 1e-12:
            problems.append('%s sweep has %s=%s, the contract declares %s' % (deck, key, token, want))
    grid = [float(point) for point in contract['clamp_sweep_points_V']]
    if not any(abs(point - float(sweep['main_eval_V'])) < 1e-12 for point in grid):
        problems.append('%s: the main evaluation clamp %s V is not on the sweep grid the contract '
                        'lists' % (deck, sweep['main_eval_V']))
    if 'data_en' in reader['waves']:
        problems.append('%s is a DC case whose DATA_EN is pulsed' % deck)
    if reader['dc'].get('data_en') != rail:
        problems.append('%s statically drives DATA_EN with %s V; the row declares %s V, which is the '
                        '%s V domain and never the bit itself'
                        % (deck, _g(reader['dc'].get('data_en')), row['data_en_level_V'], _g(rail)))
    codes = deck_codes(row)
    if len(codes) != 1:
        problems.append('%s is a DC case naming %d codes' % (deck, len(codes)))
        return problems
    code = codes[0]
    if code not in CODES:
        problems.append('%s declares code %r, which is not one of the eight PAM codes' % (deck, code))
        return problems
    for bit, weight in sorted(BIT_WEIGHT.items()):
        if bit not in reader['dc']:
            problems.append('%s never drives %s' % (deck, bit))
            continue
        want = bit_level(code, weight, rail)
        got = reader['dc'][bit]
        if abs(got - want) > TOLERANCE_V:
            problems.append('%s sets %s = %s V for code %s; %s carries weight %d, so code %s means '
                            '%s V in the %s V domain'
                            % (deck, bit, _g(got), code, bit, weight, code, _g(want), _g(rail)))
    return problems


def _check_transient(deck, reader, row, windows, arguments, contract, rail):
    problems = []
    units = contract['units']
    enable = reader['waves'].get('data_en')
    if enable is None:
        return ['%s is a transient case with no finite-slope DATA_EN statement' % deck]
    for key, column in (('stop', 'stop_ns'), ('maxstep', 'maxstep_ns')):
        token = arguments.get(key)
        if token is None:
            problems.append('%s analysis states no %s' % (deck, key))
            continue
        try:
            got = number_from_token(token)
        except ValueError:
            problems.append('%s analysis has an unreadable %s=%s' % (deck, key, token))
            continue
        if abs(got - float(row[column]) * 1e-9) > TOLERANCE_S:
            problems.append('%s analysis reads %s=%s, the row declares %s ns'
                            % (deck, key, token, row[column]))
    if value_at(enable, 0.0) != 0.0:
        problems.append('%s leaves DATA_EN at %s V at t=0, so the first rise has no edge to find'
                        % (deck, _g(value_at(enable, 0.0))))
    if enable[-1][0] < float(row['stop_ns']):
        problems.append('%s stops its DATA_EN waveform at %s ns but the analysis runs to %s ns'
                        % (deck, _g(enable[-1][0]), row['stop_ns']))
    # each ramp is one straight line between the two declared ramp endpoints, and one half-edge wide
    half = float(row['edge_ns'])
    ramp_columns = (('rise', 'rise_low_ns', 'rise_high_ns'), ('fall', 'fall_high_ns', 'fall_low_ns'))
    for label, low_column, high_column in ramp_columns:
        for index, (low, high) in enumerate(zip(_floats(row[low_column]), _floats(row[high_column]))):
            if not adjacent(enable, low, high):
                problems.append('%s has no single DATA_EN segment %s -> %s ns for its %s edge %d, so '
                                'the wave carries an extra vertex inside the ramp'
                                % (deck, _g(low), _g(high), label, index))
            elif abs(abs(high - low) / 2.0 - half) > TOLERANCE_NS:
                problems.append('%s runs its %s edge %d over %s ns while the row declares a half-edge '
                                'of %s ns' % (deck, label, index, _g(abs(high - low)), _g(half)))
    for start, stop, width in rail_spans(enable, 0.0, rail):
        if width / 2.0 > float(units['edge_ns']) + TOLERANCE_NS:
            problems.append('%s has a DATA_EN ramp %s -> %s ns, a half-edge of %s ns over the '
                            'contract limit of %s ns'
                            % (deck, _g(start), _g(stop), _g(width / 2.0), _g(units['edge_ns'])))
    # the 50% points interpolated from the deck, against the platform edges the table declares
    half_rail = rail / 2.0
    found = crossings(enable, half_rail)
    rising = [point for point, direction in found if direction == 'rise']
    falling = [point for point, direction in found if direction == 'fall']
    if len(rising) != len(falling):
        problems.append('%s interpolates %d rising and %d falling half-rail crossings, which is not a '
                        'whole number of platforms' % (deck, len(rising), len(falling)))
    for column, points in (('enable_rise_50_ns', rising), ('enable_fall_50_ns', falling)):
        declared = _floats(row[column])
        if len(declared) != len(points):
            problems.append('%s interpolates %d %s points from its own wave (%s) while the row declares '
                            '%d (%s)' % (deck, len(points), column, _join(points), len(declared),
                                         _join(declared)))
            continue
        for want, got in zip(declared, points):
            if abs(want - got) > TOLERANCE_NS:
                problems.append('%s: its own DATA_EN wave crosses half of the %s V rail at %s ns, the '
                                'row declares that edge at %s ns'
                                % (deck, _g(rail), _g(got), _g(want)))
    intervals = window_intervals(windows, row['case_id'])
    codes = deck_codes(row)
    starts = _floats(row['platform_start_ns'])
    if len(codes) != len(starts):
        problems.append('%s declares %d codes for %d platforms' % (deck, len(codes), len(starts)))
    changes = [float(part) for part in split_list(row['code_change_ns'])
               if not part.startswith('static')]
    static_only = (not changes and row['code_change_ns'].startswith('static_from_t0'))
    edge = float(contract['rules']['enable_edges']['code_change_edge_total_ns'])
    for bit, weight in sorted(BIT_WEIGHT.items()):
        pairs = reader['waves'].get(bit)
        if pairs is None:
            if bit not in reader['dc']:
                problems.append('%s never drives %s' % (deck, bit))
                continue
            pairs = [(0.0, reader['dc'][bit])]
        if pairs[0][0] != 0.0:
            problems.append('%s starts its %s waveform at %s ns instead of t=0, so the initial code is '
                            'not stable from the first sample' % (deck, bit, _g(pairs[0][0])))
        if len(codes) == len(starts):
            for index, code in enumerate(codes):
                if code not in CODES:
                    problems.append('%s names code %r, which is not one of the eight' % (deck, code))
                    continue
                want = bit_level(code, weight, rail)
                got = value_at(pairs, starts[index] + 1.0)
                if got is None or abs(got - want) > TOLERANCE_V:
                    problems.append('%s drives %s = %s V during platform %d (code %s); weight %d of '
                                    'the %s V domain says %s V'
                                    % (deck, bit, _g(got), index, code, weight, _g(rail), _g(want)))
        if static_only:
            moving = [item for item in segments(pairs) if item[1] != item[3]]
            if moving:
                problems.append('%s declares a code that is static from t=0 but its %s wave changes '
                                'over %s-%s ns' % (deck, bit, _g(moving[0][0]), _g(moving[0][2])))
            continue
        if len(changes) + 1 != len(codes):
            problems.append('%s declares %d code changes for %d codes, so the code sequence cannot be '
                            're-derived from the row' % (deck, len(changes), len(codes)))
            continue
        for index, instant in enumerate(changes):
            before = value_at(pairs, instant - edge / 2.0)
            after = value_at(pairs, instant + edge / 2.0)
            want_before = bit_level(codes[index], weight, rail)
            want_after = bit_level(codes[index + 1], weight, rail)
            if before is None or after is None:
                problems.append('%s has no %s value around the declared code change at %s ns'
                                % (deck, bit, _g(instant)))
                continue
            if abs(before - want_before) > TOLERANCE_V or abs(after - want_after) > TOLERANCE_V:
                problems.append('%s at code change %d (%s ns) reads %s V before and %s V after, but '
                                'code %s -> %s with weight %d means %s V -> %s V'
                                % (deck, bit, _g(instant), _g(before), _g(after), codes[index],
                                   codes[index + 1], weight, _g(want_before), _g(want_after)))
            if want_before != want_after:
                ok, reason = is_low_throughout(enable, instant - edge / 2.0, instant + edge / 2.0)
                if not ok:
                    problems.append('%s changes %s across %s-%s ns, where DATA_EN is not held at 0 V: %s'
                                    % (deck, bit, _g(instant - edge / 2.0), _g(instant + edge / 2.0),
                                       reason))
                if not adjacent(pairs, instant - edge / 2.0, instant + edge / 2.0):
                    problems.append('%s changes %s without a single %g ns segment centred on the '
                                    'declared code change at %s ns'
                                    % (deck, bit, edge, _g(instant)))
            else:
                for t0, v0, t1, v1 in segments(pairs):
                    if t1 <= instant - edge / 2.0 or t0 >= instant + edge / 2.0:
                        continue
                    if v0 != want_before or v1 != want_before:
                        problems.append('%s holds %s across code change %d but its segment %s-%s ns '
                                        'moves to %s V there'
                                        % (deck, bit, index + 1, _g(t0), _g(t1), _g(v1)))
        # a code change may never touch an emission window, and it has to sit inside a pure-off window
        for t0, v0, t1, v1 in [item for item in segments(
                reader['waves'].get(bit, [])) if item[1] != item[3]]:
            ok, reason = is_low_throughout(enable, t0, t1)
            if not ok:
                problems.append('%s moves %s over %s-%s ns, outside a fully-off DATA_EN stretch: %s'
                                % (deck, bit, _g(t0), _g(t1), reason))
            for letter, prefix in (('W', 'emission'), ('F', 'flat emission')):
                for low, high in intervals.get(letter, []):
                    if max(t0, low) < min(t1, high):
                        problems.append('%s moves %s over %s-%s ns, which overlaps the declared %s '
                                        'window %s-%s ns' % (deck, bit, _g(t0), _g(t1), prefix,
                                                             _g(low), _g(high)))
            if not any(low <= t0 and t1 <= high for low, high in intervals.get('O', [])):
                problems.append('%s moves %s over %s-%s ns, which no declared pure-off window of this '
                                'case contains (the tail window reaches back over the fall ramp, so '
                                'being inside it is not the condition)' % (deck, bit, _g(t0), _g(t1)))
    # a leakage window is a stretch the deck keeps at 0 V and it never reaches the next rise
    rise_starts = [t0 for t0, v0, t1, v1 in segments(enable) if v0 == 0.0 and v1 == rail]
    for low, high in split_times(row['leak_window_ns']):
        ok, reason = is_low_throughout(enable, low, high)
        if not ok:
            problems.append('%s measures leakage over %s-%s ns but its own DATA_EN is not 0 V across '
                            'it: %s' % (deck, _g(low), _g(high), reason))
        inside = [point for point in rise_starts if low < point < high]
        if inside:
            problems.append('%s puts the leakage window %s-%s ns over a DATA_EN rise that starts at '
                            '%s ns; the rule refuses that configuration instead of truncating the '
                            'window' % (deck, _g(low), _g(high), _g(inside[0])))
    for letter, pairs_list in sorted(intervals.items()):
        if letter not in WINDOW_LETTER:
            problems.append('%s declares a window %s whose id letter no window kind uses'
                            % (deck, pairs_list[0]))
        for low, high in pairs_list:
            if low >= high:
                problems.append('%s declares a %s window %s-%s ns that runs backwards'
                                % (deck, WINDOW_LETTER.get(letter, letter), _g(low), _g(high)))
    return problems


def _join(values):
    return ';'.join(_g(value) for value in values)


def window_intervals(windows, case_id):
    """the timed windows.csv rows of one case, keyed by the letter its window id starts with"""
    out = {}
    for row in windows:
        if row['case_id'] != case_id:
            continue
        if not _is_number(row['start_ns']) or not _is_number(row['stop_ns']):
            continue
        letter = row['window_id'].rsplit('#', 1)[1][0]
        out.setdefault(letter, []).append((float(row['start_ns']), float(row['stop_ns'])))
    for letter in out:
        out[letter].sort()
    return out


def _is_number(text):
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def subckt_ports(directory, model):
    """the port list of a subckt as the delivered candidate master declares it, or None"""
    pattern = re.compile(r'^subckt\s+%s\s+\((.*)\)\s*$' % re.escape(model))
    for basename in CANDIDATE_MASTERS:
        path = os.path.join(directory, 'spectre', basename)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding='utf-8', newline='') as handle:
            for line in statements(handle.read()):
                match = pattern.match(line)
                if match:
                    return match.group(1).split()
    return None


def check_provenance(deck, reader, contract, directory):
    """the deck's includes and its DUT instance, read back against the delivered masters"""
    problems = []
    listed = [os.path.basename(name) for name, _section in reader['includes']
              if 'QODER_NETLIST_DIR' in name]
    for basename in listed:
        if not os.path.isfile(os.path.join(directory, 'spectre', basename)):
            problems.append('%s includes %s, which is not delivered under spectre/' % (deck, basename))
    wanted = sorted(os.path.basename(path) for path in contract['frozen_candidate_dut'])
    if wanted != sorted(CANDIDATE_MASTERS):
        problems.append('this reader checks %s while the contract freezes %s, so the frozen list moved'
                        % (', '.join(sorted(CANDIDATE_MASTERS)), ', '.join(wanted)))
    for basename in wanted:
        if basename not in listed:
            problems.append('%s does not include the frozen candidate master %s' % (deck, basename))
    if len(reader['instances']) != 1:
        problems.append('%s instantiates %d subckt instances, a case needs exactly one DUT: %s'
                        % (deck, len(reader['instances']),
                           [item[0] for item in reader['instances']][:3]))
        return problems
    label, terminals, model = reader['instances'][0]
    ports = subckt_ports(directory, model)
    if ports is None:
        problems.append('%s instantiates %s, which no delivered master declares as a subckt'
                        % (deck, model))
    elif len(ports) != len(terminals):
        problems.append('%s connects %d terminals to %s, whose subckt declares %d ports (%s)'
                        % (deck, len(terminals), model, len(ports), ' '.join(ports)))
    return problems


def check_tables(rows, windows, contract):
    """the two tables the decks are read against have to say the same thing as each other"""
    problems = []
    by_case = {}
    for row in windows:
        by_case.setdefault(row['window_id'].rsplit('#', 1)[0], []).append(row)
    for row in sorted(rows, key=lambda item: item['case_id']):
        if row['class'] == 'dc_sweep':
            entries = by_case.get(row['case_id'], [])
            kinds = sorted(set(item['kind'] for item in entries))
            timed = [item for item in entries if _is_number(item['start_ns'])]
            if kinds != ['dc_sweep_point'] or timed or len(entries) != 1:
                problems.append('%s is a DC case: windows.csv gives it %d rows of kind %s and %d of '
                                'them carry a timed window, which a DC sweep has none of'
                                % (row['case_id'], len(entries), ','.join(kinds) or 'none', len(timed)))
            continue
        declared = {}
        for letter, (low_column, high_column) in DECLARED_COLUMN.items():
            if low_column == high_column:
                declared[letter] = split_times(row[low_column])
            else:
                declared[letter] = list(zip(_floats(row[low_column]), _floats(row[high_column])))
        present = window_intervals(windows, row['case_id'])
        for letter in sorted(WINDOW_LETTER):
            got = sorted(present.get(letter, []))
            want = sorted(declared[letter])
            if got != want:
                problems.append('%s: windows.csv %s windows are %s, the schedule row declares %s'
                                % (row['case_id'], WINDOW_LETTER[letter], _join_intervals(got),
                                   _join_intervals(want)))
        leak_length = float(contract['rules']['shutoff_leakage']['tail_last_ns'])
        for low, high in declared['L']:
            if abs((high - low) - leak_length) > TOLERANCE_NS:
                problems.append('%s: the leakage window %s-%s ns is %s ns, not the %g ns the '
                                'contract names'
                                % (row['case_id'], _g(low), _g(high), _g(high - low), leak_length))
        if split_times(row['off_window_ns']) != sorted(declared['O']):
            problems.append('%s: its off_window_ns pairs are %s, which is not the pure-off interval '
                            'the same row spells as start and stop columns (%s)'
                            % (row['case_id'], row['off_window_ns'], _join_intervals(declared['O'])))
    return problems


def _join_intervals(intervals):
    return ';'.join('%s-%s' % (_g(low), _g(high)) for low, high in intervals) or 'none'


def load(directory):
    with io.open(os.path.join(directory, CONTRACT_JSON.replace('/', os.sep)), encoding='utf-8') as \
            handle:
        contract = json.load(handle)
    tables = {}
    for key, path in (('schedule', SCHEDULE_TABLE), ('windows', WINDOWS_TABLE)):
        with io.open(os.path.join(directory, path.replace('/', os.sep)), encoding='utf-8',
                     newline='') as handle:
            tables[key] = [dict(row) for row in csv.DictReader(handle)]
    return contract, tables['schedule'], tables['windows']


def check_all(directory):
    """every delivered deck, read independently: (problems, per-case observations, decks read)"""
    contract, rows, windows = load(directory)
    directory_path = os.path.join(directory, DECK_DIR.replace('/', os.sep))
    names = sorted(name for name in os.listdir(directory_path) if name.endswith('.scs'))
    absent = missing_fields(contract)
    if absent:
        problems = ['the contract of this tree does not declare %s, so this reader has no expectation '
                    'to read the decks against' % ', '.join(absent)]
        if len(names) != 15:
            problems.append('the deck directory holds %d .scs files, the schedule has 15 cases'
                            % len(names))
        return problems, {'contract_fields_missing': absent, 'decks_present': len(names)}, len(names)
    header = set(rows[0]) if rows else set()
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    per_case = {}
    count = 0
    rail = float(contract['units']['logic_high_V'])
    if missing:
        # the window rules read those columns; a tree that does not name them apart is unreadable
        # for this round, which is stated here instead of raising or reporting an empty problem list
        problems = ['the schedule table declares %d columns and not %s, so the five separately named '
                    'windows cannot be read from it' % (len(header), ', '.join(missing))]
        for row in sorted(rows, key=lambda item: item['case_id']):
            path = os.path.join(directory, DECK_DIR.replace('/', os.sep), '%s.scs' % row['case_id'])
            if not os.path.isfile(path):
                problems.append('%s is not delivered' % path)
                continue
            count += 1
            reader = read_deck(path)
            problems.extend(_check_statements(row['case_id'], reader, contract, directory))
            per_case[row['case_id']] = {'unreadable_columns': len(missing)}
        return problems, per_case, count
    problems = check_tables(rows, windows, contract)
    for row in sorted(rows, key=lambda item: item['case_id']):
        path = os.path.join(directory, DECK_DIR.replace('/', os.sep), '%s.scs' % row['case_id'])
        if not os.path.isfile(path):
            problems.append('%s is not delivered' % path)
            continue
        count += 1
        reader = read_deck(path)
        found = check_deck(row['case_id'], reader, row, windows, contract, directory)
        problems.extend(found)
        enable = reader['waves'].get('data_en', [])
        per_case[row['case_id']] = {
            'pwl_signals': sorted(reader['waves']),
            'enable_vertices': len(enable),
            'enable_rails_to_rail_ramps': len(rail_spans(enable, 0.0, rail)),
            'half_rail_crossings': len(crossings(enable, rail / 2.0)),
            'code_segments_moving': sum(len([item for item in segments(reader['waves'].get(bit, []))
                                             if item[1] != item[3]])
                                        for bit in BIT_WEIGHT)}
    directory_path = os.path.join(directory, DECK_DIR.replace('/', os.sep))
    names = sorted(name for name in os.listdir(directory_path) if name.endswith('.scs'))
    if len(names) != 15:
        problems.append('the deck directory holds %d .scs files, the schedule has 15 cases'
                        % len(names))
    return problems, per_case, count


def _scratch(requested, directory):
    root = os.path.abspath(directory)
    path = os.path.abspath(requested) if requested else os.path.join(
        os.path.dirname(root), 'd7c_b_prep_r1_deck_read_scratch')
    if path == root or path.startswith(root + os.sep):
        raise ValueError('the scratch tree has to sit outside the repository, not at %s' % path)
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)
    return path


def counterexamples(directory, requested_scratch=''):
    """the two copies section 4.3 keeps, plus the control that the delivered bytes do not trigger them"""
    contract, rows, windows = load(directory)
    absent = missing_fields(contract)
    if absent:
        return [{'family': 'this_tree', 'verdict': 'MISS',
                 'detail': 'the contract does not declare %s, so no injection can be judged against it'
                           % ', '.join(absent)}]
    rail = float(contract['units']['logic_high_V'])
    by_case = dict((row['case_id'], row) for row in rows)
    results = []
    scratch = _scratch(requested_scratch, directory)
    try:
        # (a) the old long ramp: the first DATA_EN ramp keeps its start and stretches its top, so the
        #     half-rail point read off the wave is no longer the edge the table declares
        target = 'TR-LONG'
        source = os.path.join(directory, DECK_DIR.replace('/', os.sep), '%s.scs' % target)
        with io.open(source, encoding='utf-8', newline='') as handle:
            text = handle.read()
        original = [line for line in statements(text) if STATEMENT_PWL.match(line)
                    and STATEMENT_PWL.match(line).group(2) == 'data_en'][0]
        row = by_case[target]
        top = _floats(row['rise_high_ns'])[0]
        declared_rise = _floats(row['enable_rise_50_ns'])[0]
        old_shape = re.sub(r'(?<![\d.])%dn (\d+\.\d+)' % int(top),
                           '%dn \\1' % int(top + 50), original, count=1)
        if old_shape == original:
            results.append({'family': 'old_long_ramp', 'verdict': 'MISS',
                            'detail': 'the injection did not change the copy: %s' % original[:90]})
        else:
            copy = os.path.join(scratch, '%s.scs' % target)
            with io.open(copy, 'wb') as handle:
                handle.write(text.replace(original, old_shape).encode('utf-8'))
            mutated = read_deck(copy)
            observed = crossings(mutated['waves']['data_en'], rail / 2.0)
            problems = check_deck(target, mutated, row, windows, contract, directory)
            named = [item for item in problems if 'crosses half of the' in item]
            fact = bool(observed) and abs(observed[0][0] - declared_rise) > TOLERANCE_NS
            results.append({'family': 'old_long_ramp',
                            'verdict': 'HIT' if fact and named else 'MISS',
                            'injected': 'the first ramp now ends at %s ns instead of %s ns, so the '
                                        'copy crosses %s V at %s ns while the table declares its 50%% '
                                        'point at %s ns (measured by this reader, not assumed)'
                                        % (_g(top + 50), _g(top), _g(rail / 2.0),
                                           _g(observed[0][0]) if observed else 'nothing',
                                           _g(declared_rise)),
                            'detail': (named[0][:170] if named else
                                       'no half-rail refusal; problems=%s'
                                       % [item[:70] for item in problems[:3]]),
                            'problem_count': len(problems)})
        # (b) a coherent copy of both tables whose first leakage window reaches into the next enable
        target = 'TR-OFFCODE'
        row = dict(by_case[target])
        low, high = 1850.0, 1950.0
        row['leak_window_ns'] = ';'.join(['%s-%s' % (_g(low), _g(high))]
                                         + split_list(row['leak_window_ns'])[1:])
        if not any(item['case_id'] == target and item['window_id'].endswith('#L0')
                   for item in windows):
            results.append({'family': 'leak_window_over_next_rise', 'verdict': 'MISS',
                            'detail': 'windows.csv has no TR-OFFCODE#L0 row to move'})
        else:
            moved = []
            for item in windows:
                copy_row = dict(item)
                if copy_row['case_id'] == target and copy_row['window_id'].endswith('#L0'):
                    copy_row['start_ns'] = _g(low)
                    copy_row['stop_ns'] = _g(high)
                moved.append(copy_row)
            path = os.path.join(directory, DECK_DIR.replace('/', os.sep), '%s.scs' % target)
            reader = read_deck(path)
            rise_starts = [t0 for t0, v0, t1, v1 in segments(reader['waves']['data_en'])
                           if v0 == 0.0 and v1 == rail]
            inside = [point for point in rise_starts if low < point < high]
            problems = check_deck(target, reader, row, moved, contract, directory)
            named = [item for item in problems if 'leakage' in item]
            results.append({'family': 'leak_window_over_next_rise',
                            'verdict': 'HIT' if inside and named else 'MISS',
                            'injected': 'a leak window %s-%s ns in both tables, which the deck\'s own '
                                        'wave shows contains the next rising ramp start at %s ns'
                                        % (_g(low), _g(high), _g(inside[0]) if inside else 'nothing'),
                            'detail': (named[0][:170] if named else
                                       'no leakage refusal; problems=%s'
                                       % [item[:70] for item in problems[:3]]),
                            'problem_count': len(problems)})
        # the control: the delivered bytes must not raise either refusal
        controls = {}
        for target in ('TR-LONG', 'TR-OFFCODE'):
            path = os.path.join(directory, DECK_DIR.replace('/', os.sep), '%s.scs' % target)
            problems = check_deck(target, read_deck(path), by_case[target], windows, contract, directory)
            controls[target] = [item for item in problems if 'leakage' in item
                               or 'crosses half of the' in item]
        results.append({'family': 'delivered_bytes_control',
                        'verdict': 'HIT' if not any(controls.values()) else 'MISS',
                        'detail': 'delivered TR-LONG and TR-OFFCODE raise %d edge or leakage refusals: %s'
                                  % (sum(len(value) for value in controls.values()),
                                     [item[:60] for items in controls.values() for item in items][:2])})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return results


def observe(directory):
    """the counts that make an empty problem list mean something: what the reader actually looked at"""
    contract, rows, windows = load(directory)
    kinds = {}
    for row in windows:
        kinds[row['kind']] = kinds.get(row['kind'], 0) + 1
    _problems, per_case, count = check_all(directory)
    return {'decks_read': count, 'windows_by_kind': kinds,
            'pwl_signals_read': sorted(set(name for item in per_case.values()
                                           for name in item.get('pwl_signals', []))),
            'pam_changing_segments_total': sum(item.get('code_segments_moving', 0)
                                               for item in per_case.values()),
            'half_rail_crossings_total': sum(item.get('half_rail_crossings', 0)
                                             for item in per_case.values()),
            'note': 'an empty problem list over %d emission windows and %d PAM changing segments is a '
                    'measurement, not a silence'
                    % (kinds.get('emission', 0), sum(item.get('code_segments_moving', 0)
                                                     for item in per_case.values()))}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--counterexample', action='store_true')
    parser.add_argument('--observe', action='store_true')
    parser.add_argument('--root', default=ROOT)
    parser.add_argument('--scratch', default='')
    parser.add_argument('--json', default='')
    arguments = parser.parse_args(argv)
    directory = os.path.abspath(arguments.root)
    payload = {'reader': os.path.basename(__file__), 'root': directory, 'verdict': 'PASS',
               'rule': 'the deck bytes are the evidence and the tables are claims tested against them; '
                       'this module imports neither the generator nor the measurement core'}
    if not (arguments.check or arguments.counterexample or arguments.observe):
        parser.print_help()
        return 0
    if arguments.check:
        problems, per_case, count = check_all(directory)
        payload['decks_read'] = count
        payload['problems'] = problems
        payload['per_case'] = per_case
        payload['check_verdict'] = 'PASS' if not problems and count == 15 else 'FAIL'
        print('D7C_B_PREP_R1_DECK_READ: %s (%d decks, problems=%d)'
              % (payload['check_verdict'], count, len(problems)))
        for line in problems[:12]:
            print('  PROBLEM ' + line)
    if arguments.counterexample:
        results = counterexamples(directory, arguments.scratch)
        payload['counterexamples'] = results
        missing = [item['family'] for item in results if item['verdict'] != 'HIT']
        payload['counterexample_verdict'] = 'PASS' if not missing else 'FAIL'
        print('D7C_B_PREP_R1_DECK_READ_NEGATIVES: %s (%d/%d named)'
              % (payload['counterexample_verdict'], len(results) - len(missing), len(results)))
        for item in results:
            print('  %-30s %-5s %s' % (item['family'], item['verdict'], item['detail'][:130]))
    if arguments.observe:
        observation = observe(directory)
        payload['observation'] = observation
        enough = (observation['decks_read'] == 15
                  and observation['windows_by_kind'].get('emission', 0) >= 27
                  and observation['pam_changing_segments_total'] > 0)
        payload['observation_verdict'] = 'PASS' if enough else 'FAIL'
        print('D7C_B_PREP_R1_DECK_READ_OBSERVE: %s (%s)'
              % (payload['observation_verdict'],
                 json.dumps({key: value for key, value in sorted(observation.items())
                             if key != 'note'}, sort_keys=True)[:260]))
    payload['verdict'] = 'PASS' if 'FAIL' not in [payload.get('check_verdict'),
                                                 payload.get('counterexample_verdict'),
                                                 payload.get('observation_verdict')] else 'FAIL'
    if arguments.json:
        with io.open(arguments.json, 'wb') as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True).encode('utf-8') + b'\n')
    return 0 if payload['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
