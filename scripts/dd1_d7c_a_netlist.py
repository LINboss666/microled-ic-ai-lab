#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_netlist.py -- the netlist subset parser and the static-CMOS evaluator for DATA-7C-A.

Python standard library only. This module deliberately does NOT contain a SPICE simulator, does not
evaluate an analog operating point, and does not open a socket or start a process: it reads text,
builds a connectivity graph, and answers structure questions about it.

Supported grammar is the exact subset the delivered candidate files use, and anything else is
refused by name rather than skipped, because a silently ignored line is how a broken netlist looks
clean:

    // comment to end of line, whole-line comment
    subckt NAME ( port port ... )
    parameters NAME=VALUE                 (symbol values, as sc1_scan_gate.scs uses)
    parameters NAME DIRECTION             (port directions, as the accepted cores use)
    ends NAME
    Mname ( d g s b ) MODEL l=... w=... [m=...]
    Xname ( net net ... ) MASTERNAME
    blank line

A MOS line whose terminals are not exactly four, or whose parameters are not in `l= w= [m=]` order,
is UNSUPPORTED_MOS_FORM rather than guessed at. PDK devices are used as black boxes through the
explicit model whitelist, and no model card is read.

The evaluator answers one question and nothing more: for a given cell and a given assignment of its
input ports, is each internal net pulled up to vdd through conducting PMOS, pulled down to vss
through conducting NMOS, both, or neither. That is enough to derive a gate's logic from its
transistors instead of from its name, which is what the task brief asks for, and it is strictly
digital: no threshold, no current, no delay.
"""

from __future__ import absolute_import, division, print_function

import io
import os
import re

SUBCKT_RX = re.compile(r'^\s*subckt\s+(\w+)\s*\(([^)]*)\)\s*(?://.*)?$', re.I)
ENDS_RX = re.compile(r'^\s*ends(?:\s+(\w+))?\s*(?://.*)?$', re.I)
PARAM_VAL_RX = re.compile(r'^\s*parameters\s+(\w+)\s*=\s*(\S+)\s*(?://.*)?$', re.I)
PARAM_DIR_RX = re.compile(r'^\s*parameters\s+(\w+)\s+(input|output|inputOutput|inout)\s*$', re.I)
MOS_RX = re.compile(r'^\s*(?P<inst>[mM]\w*)\s*\(\s*(?P<d>\S+)\s+(?P<g>\S+)\s+(?P<s>\S+)\s+'
                    r'(?P<b>\S+)\s*\)\s*(?P<model>\w+)\s+l=(?P<l>\S+)(?:\s+w=(?P<w>\S+))?'
                    r'(?:\s+m=(?P<m>\S+))?\s*$', re.I)
MOS_LOOSE_RX = re.compile(r'^\s*[mM]\w*\s*\(', re.I)
SUB_RX = re.compile(r'^\s*(?P<inst>[xX]\w*)\s*\(\s*(?P<nets>[^)]*)\)\s*(?P<master>\w+)\s*$', re.I)
SUB_LOOSE_RX = re.compile(r'^\s*[xX]\w*\s*\(', re.I)
BLANK_RX = re.compile(r'^\s*$')

MODEL_WHITELIST = ('n18', 'p18', 'n33', 'n33_dnw_4t_ckt')
DIRECTIONS = ('input', 'output', 'inputOutput', 'inout')


class NetlistError(Exception):
    """a refusal the caller must not swallow: unsupported syntax, bad definition, missing master"""


def strip_comment(line):
    cut = line.find('//')
    return (line if cut < 0 else line[:cut]).rstrip()


def parse(text, origin='<memory>'):
    """parse one file of the supported subset into subckt definitions plus unsupported lines"""
    subs, unsupported, order = {}, [], []
    current = None
    for number, raw in enumerate(text.replace('\r\n', '\n').replace('\r', '\n').split('\n'), 1):
        line = strip_comment(raw)
        if BLANK_RX.match(line):
            continue
        where = '%s:%d' % (origin, number)
        m = SUBCKT_RX.match(line)
        if m:
            name = m.group(1)
            if name in subs:
                raise NetlistError('DUPLICATE_SUBCKT %s at %s' % (name, where))
            ports = m.group(2).split()
            if not ports:
                raise NetlistError('SUBCKT_WITHOUT_PORTS %s at %s' % (name, where))
            current = {'name': name, 'ports': ports, 'direction': {}, 'param_values': {},
                       'mos': [], 'subs': [], 'lines': []}
            subs[name] = current
            order.append(name)
            continue
        m = ENDS_RX.match(line)
        if m:
            if current is None:
                raise NetlistError('ENDS_WITHOUT_SUBCKT at %s' % where)
            if m.group(1) and m.group(1) != current['name']:
                raise NetlistError('ENDS_NAME_MISMATCH %s closes %s at %s'
                                   % (m.group(1), current['name'], where))
            current = None
            continue
        if current is None:
            # a statement outside a subckt: the deck level. Only inventory is taken of it.
            unsupported.append({'where': where, 'kind': 'TOP_LEVEL_STATEMENT', 'text': line})
            continue
        m = PARAM_DIR_RX.match(line)
        if m:
            current['direction'][m.group(1)] = m.group(2)
            continue
        m = PARAM_VAL_RX.match(line)
        if m:
            current['param_values'][m.group(1)] = m.group(2)
            continue
        m = MOS_RX.match(line)
        if m:
            current['mos'].append({'inst': m.group('inst'), 'model': m.group('model'),
                                   'd': m.group('d'), 'g': m.group('g'), 's': m.group('s'),
                                   'b': m.group('b'), 'l': m.group('l'), 'w': m.group('w'),
                                   'm': m.group('m') or '1', 'where': where})
            continue
        if MOS_LOOSE_RX.match(line):
            raise NetlistError('UNSUPPORTED_MOS_FORM at %s: %s' % (where, line))
        m = SUB_RX.match(line)
        if m:
            nets = m.group('nets').split()
            current['subs'].append({'inst': m.group('inst'), 'master': m.group('master'),
                                    'nets': nets, 'where': where})
            continue
        if SUB_LOOSE_RX.match(line):
            raise NetlistError('UNSUPPORTED_SUBCKT_INSTANCE_FORM at %s: %s' % (where, line))
        unsupported.append({'where': where, 'kind': 'UNSUPPORTED_STATEMENT', 'text': line})
    if current is not None:
        raise NetlistError('UNTERMINATED_SUBCKT %s' % current['name'])
    return {'subs': subs, 'unsupported': unsupported, 'order': order}


def load(paths):
    """merge several files into one definition space; a name defined twice is a refusal"""
    subs, files = {}, []
    for path in paths:
        with io.open(path, 'rb') as handle:
            result = parse(handle.read().decode('utf-8', 'replace'), os.path.basename(path))
        if result['unsupported']:
            kinds = ', '.join('%s(%s)' % (u['kind'], u['where']) for u in result['unsupported'])
            raise NetlistError('UNSUPPORTED_SYNTAX in %s: %s' % (os.path.basename(path), kinds))
        for name, body in result['subs'].items():
            if name in subs:
                raise NetlistError('DUPLICATE_SUBCKT_DEFINITION %s in %s and %s'
                                  % (name, os.path.basename(path),
                                     os.path.basename(subs[name]['file'])))
            body['file'] = path
            subs[name] = body
        files.append(path)
    return subs, files


def resolve_symbol(sub, token):
    return sub['param_values'].get(token, token)


def si(value):
    """the handful of unit suffixes these netlists use; anything else is a refusal"""
    text = str(value).strip()
    match = re.match(r'^(-?\d+(?:\.\d+)?(?:e-?\d+)?)([a-zA-Z]*)$', text)
    if not match:
        raise NetlistError('UNPARSED_NUMBER %r' % value)
    number = float(match.group(1))
    scale = {'': 1.0, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'm': 1e-3, 'k': 1e3, 'meg': 1e6}[
        match.group(2).lower()]
    return number * scale


def expand(subs, top):
    """flatten the hierarchy; every terminal becomes one global net identity

    A top-level port keeps its written name, and any net that only exists inside a subckt instance
    gets that instance's path in front of it. Two branches therefore hold two different `vbias_ch`,
    which is exactly the distinction LOCAL_NODES_SCOPED reads, and a net written at the top is never
    confused with a child's internal node.
    """
    if top not in subs:
        raise NetlistError('MASTER_NOT_DEFINED %s' % top)
    devices, instances = [], []

    def walk(cell, path, port_map):
        sub = subs[cell]

        def net(token):
            token = resolve_symbol(sub, token)
            if token in port_map:
                return port_map[token]
            return '%s/%s' % (path or cell, token)

        for device in sub['mos']:
            if device['model'] not in MODEL_WHITELIST:
                raise NetlistError('MODEL_NOT_WHITELISTED %s uses %s at %s'
                                   % (device['inst'], device['model'], device['where']))
            prefix = '%s.' % path if path else ''
            devices.append({'inst': '%s%s' % (prefix, device['inst']),
                            'scope': cell, 'scope_path': path, 'model': device['model'],
                            'd': net(device['d']), 'g': net(device['g']),
                            's': net(device['s']), 'b': net(device['b']),
                            'l': resolve_symbol(sub, device['l']),
                            'w': resolve_symbol(sub, device['w']),
                            'm': resolve_symbol(sub, device['m']), 'where': device['where']})
        for instance in sub['subs']:
            master = instance['master']
            if master not in subs:
                raise NetlistError('MASTER_NOT_DEFINED %s (%s) at %s'
                                   % (master, instance['inst'], instance['where']))
            if len(instance['nets']) != len(subs[master]['ports']):
                raise NetlistError('PORT_COUNT %s connects %d net(s) to %s which has %d port(s) '
                                   'at %s' % (instance['inst'], len(instance['nets']), master,
                                              len(subs[master]['ports']), instance['where']))
            child_path = '%s.%s' % (path, instance['inst']) if path else instance['inst']
            child_map = {}
            for port_name, connected in zip(subs[master]['ports'], instance['nets']):
                child_map[port_name] = net(connected)
            instances.append({'inst': instance['inst'], 'master': master, 'scope': cell,
                              'scope_path': path, 'nets': instance['nets'], 'path': child_path,
                              'resolved': dict(child_map), 'binding': zip(subs[master]['ports'],
                                                                          instance['nets']),
                              'where': instance['where']})
            walk(master, child_path, child_map)

    walk(top, '', dict((p, p) for p in subs[top]['ports']))
    return devices, instances


def _reaches(devices, start, target, wanted, active, value, decided):
    """is `start` connected to `target` through conducting devices of one transistor polarity"""
    if start == target:
        return True
    seen, queue = set([start]), [start]
    while queue:
        node = queue.pop()
        for device in devices:
            if not device['model'].lower().startswith(wanted):
                continue
            ends = (device['d'], device['s'])
            if node not in ends:
                continue
            gate = device['g']
            if gate not in decided:
                continue
            if value.get(gate) != active:
                continue
            other = ends[0] if ends[1] == node else ends[1]
            if other == target:
                return True
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return False


def evaluate(subs, cell, inputs, rails=None):
    """derive every net of one cell from its pull-up / pull-down transistors

    `inputs` maps port names to 0 or 1; the rails default to the ports called vdd/vss or vdd18/vss.
    A net is 1 if only the PMOS network reaches vdd, 0 if only the NMOS network reaches vss, and the
    string 'SHORT' or 'FLOAT' when both or neither do -- those two are refused by the caller rather
    than reported as a logic level. Nothing in here knows what a NAND is: the answer comes from the
    transistors, so a cell named nand2 that is wired as a buffer is seen as a buffer.
    """
    sub = subs[cell]
    rails = dict(rails or {})
    vdd = rails.get('vdd') or next((p for p in ('vdd', 'vdd18') if p in sub['ports']), None)
    vss = rails.get('vss') or ('vss' if 'vss' in sub['ports'] else None)
    if vdd is None or vss is None:
        raise NetlistError('RAIL_PORTS_NOT_FOUND in %s (ports %s)' % (cell, sub['ports']))
    devices, _ = expand(subs, cell)
    value = {vdd: 1, vss: 0}
    decided = set([vdd, vss])
    for port, given in inputs.items():
        if port not in sub['ports']:
            raise NetlistError('EVALUATOR_INPUT_UNKNOWN %s of %s' % (port, cell))
        if int(given) not in (0, 1):
            raise NetlistError('EVALUATOR_INPUT_NOT_BINARY %s=%r of %s' % (port, given, cell))
        value[port] = int(given)
        decided.add(port)
    missing = [p for p in sub['ports'] if p not in decided and
               sub['direction'].get(p) in (None, 'input', 'inout')]
    if missing:
        raise NetlistError('EVALUATOR_INPUT_MISSING %s of %s' % (','.join(missing), cell))
    nets = set()
    for device in devices:
        nets.update([device['d'], device['s'], device['g']])
    unresolved = {}
    for _round in range(len(nets) + 4):
        changed = False
        for net in sorted(nets):
            if net in decided:
                continue
            up = _reaches(devices, net, vdd, 'p', 0, value, decided)
            down = _reaches(devices, net, vss, 'n', 1, value, decided)
            if not up and not down:
                continue                       # may still become decidable through a gate
            new = 'SHORT' if (up and down) else (1 if up else 0)
            if value.get(net) != new or net not in decided:
                value[net] = new
                decided.add(net)
                changed = True
        if not changed:
            break
    for net in sorted(nets):
        if net not in decided:
            unresolved[net] = 'FLOAT'
    return {'net_value': value, 'unresolved': unresolved, 'device_count': len(devices),
            'vdd': vdd, 'vss': vss, 'cell': cell}


def thermometer(code):
    """the amplitude mask the task brief table defines: code k lights k+1 branches"""
    if not isinstance(code, int) or isinstance(code, bool):
        raise NetlistError('REQUEST_NOT_INT')
    if code < 0 or code > 7:
        raise NetlistError('REQUEST_OUT_OF_RANGE')
    return ['1' if j <= code else '0' for j in range(8)]


def validate_request(value):
    """the one accepted shape is an int in 0..7; everything else is a named refusal

    This is a software boundary. A MOS branch cannot detect X or Z, and refusing a bad request here
    is not evidence about the analogue circuit.
    """
    if isinstance(value, bool):
        return 'REFUSED', 'REQUEST_NOT_INT'
    if isinstance(value, int):
        if 0 <= value <= 7:
            return 'ACCEPTED', None
        return 'REFUSED', 'REQUEST_OUT_OF_RANGE'
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            return 'REFUSED', 'REQUEST_NOT_FINITE'
        return 'REFUSED', 'REQUEST_NOT_INT'
    if isinstance(value, str):
        text = value.strip()
        if not re.match(r'^-?\d+$', text):
            if re.match(r'^(nan|inf|-inf|infinity)$', text, re.I):
                return 'REFUSED', 'REQUEST_NOT_FINITE'
            return 'REFUSED', 'REQUEST_UNPARSED'
        number = int(text)
        return ('ACCEPTED', None) if 0 <= number <= 7 else ('REFUSED', 'REQUEST_OUT_OF_RANGE')
    return 'REFUSED', 'REQUEST_NOT_INT'
