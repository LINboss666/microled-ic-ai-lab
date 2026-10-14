#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-C section 4: compare the OpenAccess readback against the derived golden.

Inputs are two independent sources that share no code path:

  golden   results/evidence/sc1_s3c_golden_{mos,ports,hier,subinst}.csv, produced by
           scripts/sc1_s3c_golden.py from the six frozen Spectre masters;
  readback cadence_work/s3c_oa/readback/oa_readback_pass1.log, the stdout of
           skill/sc1_s3c_readback.il, i.e. rows read out of the saved cellviews by a Virtuoso
           process that started AFTER the writing session had exited.

Everything the task book section 6 asks for is decided here, in one direction only: the OA side is
asked whether it matches the golden, never the other way round. The verdict vocabulary is
OA_GRAPH_EQUIVALENCE -- an object-graph agreement between the shipped schematic and the shipped
netlist. It is not LVS (no layout exists), not a netlister output (asiNetlist was measured absent
in batch), and emphatically not a new functional pass (this round ran zero simulators).

--negatives adds the one counter-example the task book asks for: a temporary copy of the exported
table with one MOS gate net changed must be refused, while the intact export must pass. The OA
database itself is never touched by that test.

Runs on Python 2.6.6 (guest) and Python 3.12 (workstation).
"""
from __future__ import print_function

import io
import os
import re
import sys

TERMINALS = ['D', 'G', 'S', 'B']
# SCAN_UNIT_TEAM_BEAUTIFY local adaptation (the only one this round makes to a shared tool):
# the source build recognised its own sub-circuits by the literal library name below, which is
# correct for microled_scan_s3c and silently wrong for any other library -- it would read a whole
# hierarchy as missing. The name is now taken from S3C_LIB and defaults to the original value, so
# nothing changes for the source build. Golden tables, thresholds and every comparison are as-is.
LIB_NAME = os.environ.get('S3C_LIB', 'microled_scan_s3c')
LIB_HINT = '%s (this task\'s own OA library)' % LIB_NAME
CELL_ORDER = ['c2mos_dff', 'sc1_scan_gate', 'sc1_ls_core_r2d', 'sc1_ls_c1_r2d',
              'sc1_ls_c1_top_r2d', 'sc1_r3_scan_chain_1ch', 'sc1_s3b_p33_bank_7',
              'sc1_scan_power_1ch_s3c']
UNITS = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
REL_TOL = 1e-9
PTR_RX = re.compile(r'db:0x[0-9a-fA-F]+')
QUOTED_RX = re.compile(r'"([^"]*)"')


def parse_len(token):
    """'200n' / '100u' / '2e-07' / '0.0001' -> metres; anything else -> None"""
    if token is None:
        return None
    s = token.strip().strip('"')
    if not s or not re.match(r'^[0-9.].*$', s):
        return None
    if s[-1] in UNITS:
        try:
            return float(s[:-1]) * UNITS[s[-1]]
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def same_num(a, b):
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= REL_TOL * scale


def read_value(text, i):
    """one value starting at i: a quoted string, a balanced paren group, or a bare token.

    A value may be several of those glued together without a space, which is exactly how the
    master field is printed ("smic18mmrf"/"p18":"symbol"), so the reader keeps consuming until it
    reaches a space that is outside quotes and outside parentheses.
    """
    n, depth, inq = len(text), 0, False
    start = i
    while i < n:
        c = text[i]
        if c == '"':
            inq = not inq
        elif not inq:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            elif c == ' ' and depth == 0 and i > start:
                break
        i += 1
    return text[start:i], i


def scan_kv(text):
    """key=value scanner; balanced parens keep spaces inside lists"""
    out = {}
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] == ' ':
            i += 1
        j = text.find('=', i)
        if j < 0:
            break
        key = text[i:j].strip()
        if ' ' in key or '"' in key:
            break                      # not a key= boundary: stop rather than mis-attribute
        i = j + 1
        if i >= n:
            out[key] = ''
            break
        val, i = read_value(text, i)
        out[key] = val.strip() if not val.startswith('"') else val.strip('"')
    return out


def split_csv_line(line):
    """one record per line, every field quoted, "" for an embedded quote.

    Written by hand instead of with the csv module because Python 2's csv refuses unicode input,
    and this file has to give the same verdict on the guest's 2.6 and on the workstation's 3.12.
    """
    out, cur, i = [], '', 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == '"':
            i += 1
            while i < n:
                if line[i] == '"' and i + 1 < n and line[i + 1] == '"':
                    cur += '"'
                    i += 2
                    continue
                if line[i] == '"':
                    i += 1
                    break
                cur += line[i]
                i += 1
            out.append(cur)
            cur = ''
            if i < n and line[i] == ',':
                i += 1
        elif ch == ',':
            out.append(cur)
            cur = ''
            i += 1
        else:
            cur += ch
            i += 1
    if cur != '' or line.endswith(','):
        out.append(cur)
    return out


def read_csv(path):
    data = open(path, 'rb').read().decode('utf-8')
    lines = [l for l in data.splitlines() if l.strip() != '']
    return split_csv_line(lines[0]), [split_csv_line(l) for l in lines[1:]]


def load_golden(golden_dir):
    hdr, mos = read_csv(os.path.join(golden_dir, 'sc1_s3c_golden_mos.csv'))
    idx = dict((k, i) for i, k in enumerate(hdr))
    devices = {}
    for r in mos:
        devices[(r[idx['cell']], r[idx['inst']])] = {
            'path': r[idx['path_from_top']], 'model': r[idx['model']],
            'nets': [r[idx[c.lower()]] for c in TERMINALS],
            'l': float(r[idx['l_m']]), 'w': float(r[idx['w_m']]),
            'l_src': r[idx['l_src']], 'w_src': r[idx['w_src']],
            'file': r[idx['master_file']]}
    _, ports = read_csv(os.path.join(golden_dir, 'sc1_s3c_golden_ports.csv'))
    # positional on purpose: these are the columns scripts/sc1_s3c_golden.py writes, in that order
    pi = dict((k, i) for i, k in enumerate(['cell', 'ordinal', 'port', 'direction', 'role', 'order']))
    port_list = {}
    port_dir = {}
    for r in ports:
        port_list.setdefault(r[pi['cell']], []).append((int(r[pi['ordinal']]), r[pi['port']]))
        port_dir[(r[pi['cell']], r[pi['port']])] = (r[pi['direction']], r[pi['role']])
    for c in port_list:
        port_list[c] = [p for _, p in sorted(port_list[c])]
    hhier, hier = read_csv(os.path.join(golden_dir, 'sc1_s3c_golden_hier.csv'))
    hi = dict((k, i) for i, k in enumerate(hhier))
    cells = {}
    for r in hier:
        cells[r[hi['cell']]] = {'own_mos': int(r[hi['own_mos']]),
                                'expanded_mos': int(r[hi['expanded_mos']]),
                                'ports': int(r[hi['ports']]), 'file': r[hi['master_file']]}
    _, sub = read_csv(os.path.join(golden_dir, 'sc1_s3c_golden_subinst.csv'))
    si = dict((k, i) for i, k in enumerate(['cell', 'inst', 'child', 'ordinal', 'port', 'net']))
    subinst = {}
    for r in sub:
        subinst.setdefault((r[si['cell']], r[si['inst']]), {'child': r[si['child']], 'map': {}})
        subinst[(r[si['cell']], r[si['inst']])]['map'][r[si['port']]] = r[si['net']]
    return devices, port_list, port_dir, cells, subinst


def load_readback(path):
    text = io.open(path, encoding='utf-8', errors='replace').read()
    text = PTR_RX.sub('db:PTR', text)          # a rendered object handle is not persisted data
    devices, insts, nets, pins, sym, symt, cells, dbcheck, api = {}, {}, {}, [], {}, {}, {}, {}, []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('\\o'):
            line = line[2:].strip()
        m = re.match(r'^(S3CR-[A-Z]+)\s+(.*)$', line)
        if not m:
            continue
        kind, rest = m.group(1), m.group(2)
        f = scan_kv(rest)
        cell = f.get('cell', '')
        if kind == 'S3CR-CELL':
            cells[cell] = {'instances': int(f['instances']), 'nets': int(f['nets']),
                           'shapes': int(f['shapes']), 'terms': int(f['terms'])}
        elif kind == 'S3CR-DBCHECK':
            dbcheck[cell] = f.get('result', '')
        elif kind == 'S3CR-MOS':
            devices[(cell, f['inst'])] = f
        elif kind == 'S3CR-INST':
            insts[(cell, f['inst'])] = f
        elif kind == 'S3CR-NET':
            nets[(cell, f['name'])] = {'pins': int(f['pins']),
                                       'instTerms': int(f['instTerms']),
                                       'termViews': int(f.get('termViews', 0))}
        elif kind == 'S3CR-PIN':
            pins.append((cell, f.get('net', ''), f.get('figTerm', ''), f.get('objType', '')))
        elif kind == 'S3CR-SYM':
            sym[cell] = {'figures': int(f['figures']), 'terms': int(f['terms']),
                         'terminals': int(f['terminals'])}
        elif kind == 'S3CR-SYMT':
            symt.setdefault(cell, []).append((f.get('name', ''), f.get('dir', '')))
        elif kind == 'S3CR-API':
            api.append(line)
    return devices, insts, nets, pins, sym, symt, cells, dbcheck, api


def canon_devices(devices):
    """canonical circuit text from the OA rows, keyed by owning cell"""
    out = {}
    for (cell, inst), f in devices.items():
        l = parse_len(f.get('num_l', f.get('cdf_l', '')))
        w = parse_len(f.get('num_w', f.get('cdf_w', '')))
        out.setdefault(cell, []).append('M %s %s l=%.12g w=%.12g %s' % (
            inst, f.get('model', ''), l if l is not None else -1,
            w if w is not None else -1,
            ' '.join('%s=%s' % (t, f.get(t, '?')) for t in TERMINALS)))
    return dict((c, sorted(v)) for c, v in out.items())


def canon_golden(golden_devices):
    out = {}
    for (cell, inst), g in golden_devices.items():
        out.setdefault(cell, []).append('M %s %s l=%.12g w=%.12g %s' % (
            inst, g['model'], g['l'], g['w'],
            ' '.join('%s=%s' % (t, n) for t, n in zip(TERMINALS, g['nets']))))
    return dict((c, sorted(v)) for c, v in out.items())


def add_hierarchy_lines(canon, subinst, port_list, port_net_sets):
    """extend the per-cell text with the sub-circuit instances and the port nets.

    Without these three kinds of line a composite cell (which owns no device) would contribute
    nothing to the comparison, and the whole point of the hierarchical cells is how their children
    are wired and which nets are ports.
    """
    for (cell, inst), g in subinst.items():
        canon.setdefault(cell, []).append('X %s %s %s' % (
            inst, g['child'], ' '.join('%s=%s' % kv for kv in sorted(g['map'].items()))))
    for cell, nets in port_net_sets.items():
        for net in sorted(nets):
            canon.setdefault(cell, []).append('PORT %s' % net)
    for cell in canon:
        canon[cell] = sorted(canon[cell])
    for cell in port_list:
        canon.setdefault(cell, [])
        canon[cell] = sorted(canon[cell])
    return canon


def emit_netlist(devices, subinst, port_list, order, path):
    """the text circuit table rebuilt FROM the schematic rows -- an extraction, not a simulation.

    Instance names, models, sizes and every net come out of the OpenAccess readback. The only thing
    taken from the golden side is the ORDER in which each cell's ports are listed, because a symbol
    terminal set is unordered in the database and a netlist needs one; the names themselves are
    checked for equality against the readback before this function writes anything.
    """
    out = ['; SCAN-1 S3-C: circuit table rebuilt from the OpenAccess readback of',
           '; %s -- every instance, model, size and net below is a row the database' % LIB_HINT,
           '; reported. No line was copied from the frozen masters, and no simulator was run to',
           '; produce this file: it is netlist EXTRACTION from the schematic, the artifact a',
           '; reviewer compares against spectre/*.scs by eye.',
           'simulator lang=spectre insensitive=yes',
           '']
    for cell in order:
        want = port_list.get(cell, [])
        out.append('subckt %s (%s)' % (cell, ' '.join(want)))
        for (dcell, inst), f in sorted(devices.items()):
            if dcell != cell:
                continue
            out.append('  %s (%s %s %s %s) %s l=%s w=%s m=%s'
                       % (inst, f.get('D', '?'), f.get('G', '?'), f.get('S', '?'), f.get('B', '?'),
                          f.get('model', '?'), f.get('num_l', '?'), f.get('num_w', '?'),
                          f.get('raw_m', '?')))
        for (scell, inst), f in sorted(subinst.items()):
            if scell != cell:
                continue
            child_ports = port_list.get(f['child'], [])
            missing = [p for p in child_ports if p not in f['map']]
            if missing:
                raise RuntimeError('%s.%s has no OA binding for child port(s) %s'
                                   % (cell, inst, missing))
            out.append('  %s (%s) %s' % (inst, ' '.join(f['map'][p] for p in child_ports),
                                         f['child']))
        out.append('ends %s' % cell)
        out.append('')
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    handle = open(path, 'wb')
    try:
        handle.write('\n'.join(out).encode('utf-8'))
    finally:
        handle.close()
    return len(out)


def reopen_compare(path_a, path_b):
    """two independent readback sessions must report the same database rows"""
    def rows(path):
        text = open(path, 'rb').read().decode('utf-8', 'replace')
        text = PTR_RX.sub('db:PTR', text)
        return sorted(l.strip()[2:].strip() if l.startswith('\\o') else l.strip()
                      for l in text.split('\n') if 'S3CR-' in l)
    a, b = rows(path_a), rows(path_b)
    only_a = [x for x in a if x not in b]
    only_b = [x for x in b if x not in a]
    return len(a), len(b), only_a, only_b


def main():
    args = sys.argv[1:]

    def arg(name, default):
        return args[args.index(name) + 1] if name in args else default

    root = os.environ.get('PROJ', '.')
    golden_dir = arg('--golden', os.path.join(root, 'results/evidence'))
    rb_path = arg('--readback', os.path.join(root, 'cadence_work/s3c_oa/readback/oa_readback_pass1.log'))
    out_dir = arg('--out', os.path.join(root, 'results/evidence'))
    netlist_path = arg('--netlist', os.path.join(root, 'spectre/generated/sc1_s3c_channel_from_schematic.scs'))
    reopen_path = arg('--reopen', '')
    negatives = '--negatives' in args
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    devices_g, ports_g, pdir_g, cells_g, subinst_g = load_golden(golden_dir)
    (devices_o, insts_o, nets_o, pins_o, sym_o, symt_o, cells_o, dbcheck_o,
     api_o) = load_readback(rb_path)

    fails = []
    notes = []
    rows_conn = []
    rows_ports = []
    rows_read = []
    rows_equiv = []

    # ---- 1. eight cells, reopened from disk, each with a schematic and a symbol
    if sorted(cells_o) != sorted(cells_g):
        fails.append('readback covers cells %s, golden expects %s'
                     % (sorted(cells_o), sorted(cells_g)))
    for cell in sorted(cells_g):
        if cell not in sym_o:
            fails.append('%s has no symbol view in the readback' % cell)
        if cell not in dbcheck_o or dbcheck_o[cell] != 't':
            fails.append('%s dbCheck did not return t -- got %r' % (cell, dbcheck_o.get(cell)))

    # ---- 2. thirty-nine device rows, and no device row that is not in the golden
    if len(devices_o) != 39:
        fails.append('the readback holds %d PDK device rows, the golden expands to 39'
                     % len(devices_o))
    only_o = sorted(set(devices_o) - set(devices_g))
    only_g = sorted(set(devices_g) - set(devices_o))
    if only_o:
        fails.append('devices in OA but not in the golden: %s' % only_o)
    if only_g:
        fails.append('devices in the golden but not in OA: %s' % only_g)

    for (cell, inst) in sorted(devices_g):
        g = devices_g[(cell, inst)]
        f = devices_o.get((cell, inst))
        if f is None:
            continue
        verdicts = []
        if f.get('model', '') != g['model']:
            verdicts.append('model')
        if f.get('master', '').split('/')[0].strip('"') != 'smic18mmrf':
            verdicts.append('master_lib')
        # the master cell must be the model the golden names, and the OA terminal set must be
        # exactly D/G/S/B -- read BY NAME, because this PDK orders the symbol terminals differently
        # per family (measured: n18/p18 = S G B D, n33 = D G B S, p33 = B D G S)
        terms = QUOTED_RX.findall(f.get('terminals', ''))
        if sorted(terms) != sorted(TERMINALS):
            verdicts.append('terminals')
        if f.get('cdf_model', '').strip('"') != g['model']:
            verdicts.append('cdf_model')
        for k, t in enumerate(TERMINALS):
            if f.get(t, '') != g['nets'][k]:
                verdicts.append('net_' + t)
        for key, want in (('num_l', g['l']), ('num_w', g['w'])):
            got = parse_len(f.get(key, ''))
            if not same_num(got, want):
                verdicts.append(key)
        # the raw property and the CDF value must agree with each other as well as with the golden:
        # SCH-2 measured an imported cell whose raw size and CDF size disagreed
        for key in ('raw_l', 'raw_w', 'cdf_l', 'cdf_w', 'raw_fw', 'cdf_fw'):
            got = parse_len(f.get(key, ''))
            want = g['l'] if key.endswith('_l') else g['w']
            if not same_num(got, want):
                verdicts.append(key)
        for key in ('raw_m', 'raw_fingers', 'cdf_m', 'cdf_fingers'):
            if f.get(key, '').strip('"') != '1':
                verdicts.append(key)
        # simW is the PDK's own derived field (iPar("w")); it is reported, and it must not disagree
        simw = parse_len(f.get('raw_simW', ''))
        if not same_num(simw, g['w']):
            verdicts.append('raw_simW')
        rows_read.append([cell, inst, f.get('path', ''), f.get('master', ''), g['model'],
                          f.get('raw_l', ''), f.get('raw_w', ''), f.get('raw_fw', ''),
                          f.get('cdf_l', ''), f.get('cdf_w', ''), f.get('cdf_fw', ''),
                          f.get('num_l', ''), f.get('num_w', ''), f.get('raw_m', ''),
                          f.get('raw_fingers', ''), f.get('raw_simW', ''),
                          ','.join(terms),
                          f.get('D', ''), f.get('G', ''), f.get('S', ''), f.get('B', ''),
                          '%.17g' % g['l'], '%.17g' % g['w'], ' '.join(g['nets']),
                          'MATCH' if not verdicts else 'DIFF:' + ','.join(verdicts)])
        rows_conn.append([cell, inst, g['path'], g['model'],
                          ' '.join(g['nets']), ' '.join(f.get(t, '') for t in TERMINALS),
                          'MATCH' if not any(v.startswith('net_') or v in ('model', 'terminals')
                                            for v in verdicts) else 'DIFF:' + ','.join(verdicts)])
        if verdicts:
            fails.append('%s.%s differs from the golden in %s' % (cell, inst, verdicts))

    # ---- 3. the hierarchy: every sub-circuit instance points at the right child and every child
    #         port lands on the parent net the masters name
    oa_sub = {}
    for (cell, inst), f in insts_o.items():
        master = f.get('master', '')
        if LIB_NAME not in master:
            continue
        oa_sub[(cell, inst)] = {'child': f.get('model', '').strip('"'),
                                'map': dict((a, b.strip('"')) for a, b in
                                            re.findall(r'\("([^"]+)" "([^"]+)"\)',
                                                       f.get('bindings', '')))}
    if sorted(oa_sub) != sorted(subinst_g):
        fails.append('OA sub-circuit instances %s differ from the golden %s'
                     % (sorted(oa_sub), sorted(subinst_g)))
    for key in sorted(subinst_g):
        g = subinst_g[key]
        f = oa_sub.get(key)
        if f is None:
            fails.append('%s.%s is missing from the OA hierarchy' % key)
            continue
        if f['child'] != g['child']:
            fails.append('%s.%s instantiates %s, the golden says %s' % (key[0], key[1],
                                                                        f['child'], g['child']))
        if f['map'] != g['map']:
            fails.append('%s.%s pin bindings %s differ from the golden %s'
                         % (key[0], key[1], sorted(f['map'].items()), sorted(g['map'].items())))
        rows_conn.append([key[0], key[1], '%s.%s' % (key[0], key[1]), 'child:' + g['child'],
                          ' '.join('%s=%s' % kv for kv in sorted(g['map'].items())),
                          ' '.join('%s=%s' % kv for kv in sorted(f['map'].items())),
                          'MATCH' if f['child'] == g['child'] and f['map'] == g['map'] else 'DIFF'])

    # ---- 4. ports: schematic port nets, symbol terminals and the golden port order
    port_nets = {}
    for cell, net, fig, objtype in pins_o:
        port_nets.setdefault(cell, []).append((net, fig))
    for cell in sorted(cells_g):
        want = ports_g.get(cell, [])
        got_nets = sorted(set(n for n, _ in port_nets.get(cell, [])))
        got_sym = sorted(set(n for n, _ in symt_o.get(cell, [])))
        if got_nets != sorted(want):
            fails.append('%s schematic port nets %s differ from the golden %s'
                         % (cell, got_nets, sorted(want)))
        if got_sym != sorted(want):
            fails.append('%s symbol terminals %s differ from the schematic ports %s'
                         % (cell, got_sym, sorted(want)))
        if len(port_nets.get(cell, [])) != len(want):
            fails.append('%s carries %d port pins for %d ports'
                         % (cell, len(port_nets.get(cell, [])), len(want)))
        if cells_o.get(cell, {}).get('terms', -1) != 0:
            notes.append('%s reports %d schematic term objects (batch sessions normally show 0)'
                         % (cell, cells_o[cell]['terms']))
        for i, p in enumerate(want):
            direction, role = pdir_g.get((cell, p), ('?', '?'))
            oadir = dict(symt_o.get(cell, [])).get(p, '-')
            rows_ports.append([cell, i, p, direction, role, oadir,
                               'PRESENT' if p in got_nets else 'MISSING',
                               'PRESENT' if p in got_sym else 'MISSING'])
    if len(ports_g.get('sc1_scan_power_1ch_s3c', [])) != 9:
        fails.append('the formal top has %d golden ports, the task book says 9'
                     % len(ports_g.get('sc1_scan_power_1ch_s3c', [])))

    # ---- 5. no floating terminal, no stray net, and q/qbar/en really internal
    for (cell, inst), f in sorted(devices_o.items()):
        for t in TERMINALS:
            if f.get(t, '') in ('', 'UNCONNECTED', 'NO-SUCH-TERMINAL', 'nil'):
                fails.append('%s.%s terminal %s is not bound (%r)' % (cell, inst, t, f.get(t)))
    for (cell, net), f in sorted(nets_o.items()):
        if f['pins'] == 0 and f['instTerms'] == 0:
            fails.append('%s: net %s connects nothing (a floating net)' % (cell, net))
    top = 'sc1_scan_power_1ch_s3c'
    if ('%s' % top, 'bgate') in nets_o:
        fails.append('the formal top still carries a separate bgate net -- the iprobe merge did not hold')
    for cell, net in [('sc1_r3_scan_chain_1ch', 'q'), ('sc1_r3_scan_chain_1ch', 'qbar'),
                      ('sc1_r3_scan_chain_1ch', 'en')]:
        f = nets_o.get((cell, net))
        # >=1 connection, not >=2: inside the chain the golden itself wires q only to Xff's q pin
        # (the gate cell takes qbar), and q stays accessible as Xchain.q -- demanding a second
        # reader here would be inventing a load the masters do not have.
        if f is None or f['instTerms'] < 1 or f['pins'] != 0:
            fails.append('%s.%s is not a real internal net (instTerms=%s pins=%s)'
                         % (cell, net, f and f['instTerms'], f and f['pins']))
        else:
            notes.append('%s.%s is an internal net with %d terminal connections and no port pin'
                         % (cell, net, f['instTerms']))

    # ---- 6. the canonical comparison: OA-derived circuit text versus golden circuit text
    oa_canon = add_hierarchy_lines(canon_devices(devices_o), oa_sub, ports_g,
                                   dict((c, set(n for n, _ in port_nets.get(c, [])))
                                        for c in cells_g))
    g_canon = add_hierarchy_lines(canon_golden(devices_g), subinst_g, ports_g,
                                  dict((c, set(v)) for c, v in ports_g.items()))
    for cell in sorted(set(list(oa_canon) + list(g_canon))):
        a, b = g_canon.get(cell, []), oa_canon.get(cell, [])
        if a != b:
            miss = [x for x in a if x not in b]
            extra = [x for x in b if x not in a]
            fails.append('%s canonical circuit text differs: golden-only=%s oa-only=%s'
                         % (cell, miss, extra))
        rows_equiv.append([cell, len(a), len(b), len(a) == len(b) and a == b and 1 or 0,
                           'MATCH' if a == b else 'DIFF'])

    # ---- evidence files
    write(out_dir, 'sc1_s3c_oa_readback.csv',
          ['cell', 'inst', 'path_from_top', 'master', 'golden_model', 'raw_l', 'raw_w', 'raw_fw',
           'cdf_l', 'cdf_w', 'cdf_fw', 'num_l', 'num_w', 'raw_m', 'raw_fingers', 'raw_simW',
           'oa_terminals', 'oa_D', 'oa_G', 'oa_S', 'oa_B', 'golden_l_m', 'golden_w_m',
           'golden_D_G_S_B', 'verdict'], rows_read)
    write(out_dir, 'sc1_s3c_connectivity.csv',
          ['cell', 'inst', 'path_from_top', 'identity', 'golden_nets', 'oa_nets', 'verdict'],
          rows_conn)
    write(out_dir, 'sc1_s3c_ports.csv',
          ['cell', 'ordinal', 'port', 'declared_direction', 'role', 'oa_symbol_direction',
           'schematic_port', 'symbol_terminal'], rows_ports)
    write(out_dir, 'sc1_s3c_equivalence.csv',
          ['cell', 'golden_device_lines', 'oa_device_lines', 'identical', 'verdict'], rows_equiv)

    # ---- the circuit table rebuilt from the schematic rows
    if sorted(cells_o) != sorted(CELL_ORDER):
        fails.append('readback cells %s are not the eight the task book names' % sorted(cells_o))
    else:
        n = emit_netlist(devices_o, oa_sub, ports_g, CELL_ORDER, netlist_path)
        print('S3C_EXTRACTED_NETLIST: %s lines=%d' % (netlist_path, n))

    # ---- two independent readback sessions must agree, row for row
    if reopen_path:
        na, nb, only_a, only_b = reopen_compare(rb_path, reopen_path)
        print('S3C_REOPEN_ROWS pass1=%d pass2=%d only_in_pass1=%d only_in_pass2=%d'
              % (na, nb, len(only_a), len(only_b)))
        if only_a or only_b:
            fails.append('the two readback sessions disagree: %s / %s'
                         % (only_a[:3], only_b[:3]))
        else:
            print('S3C_REOPEN_CONSISTENT: PASS (the saved views reopen identically; object handles'
                  ' are process-local and are masked before the comparison)')

    # ---- the one counter-example the task book asks for
    if negatives:
        ok = counterexample(rb_path, golden_dir)
        if not ok:
            fails.append('the gate-net counter-example was not refused, or the intact export failed')

    print('S3C_READBACK_ROWS cell=%d device=%d inst=%d net=%d pin=%d symbol=%d symterm=%d'
          % (len(cells_o), len(devices_o), len(insts_o), len(nets_o), len(pins_o), len(sym_o),
             sum(len(v) for v in symt_o.values())))
    print('S3C_OA_DEVICE_COUNT: %d' % len(devices_o))
    print('S3C_OA_SUBINSTANCES: %d' % len(oa_sub))
    print('S3C_OA_PORT_PINS: %d' % len(pins_o))
    print('S3C_OA_SYMBOL_TERMINALS: %d' % sum(len(v) for v in symt_o.values()))
    print('S3C_DBCHECK_ALL_T: %s' % ('yes' if all(v == 't' for v in dbcheck_o.values()) else 'NO'))
    print('S3C_CONNECTIVITY_ROWS: %d' % len(rows_conn))
    print('S3C_CONNECTIVITY_MATCH: %d' % len([r for r in rows_conn if r[-1] == 'MATCH']))
    print('S3C_EQUIVALENCE_CELLS: %d' % len(rows_equiv))
    print('S3C_EQUIVALENCE_MATCH: %d' % len([r for r in rows_equiv if r[-1] == 'MATCH']))
    for n in notes:
        print('S3C-NOTE: %s' % n)
    for f in fails:
        print('S3C-FAIL: %s' % f)
    print('S3C_OA_GRAPH_EQUIVALENCE: %s' % ('PASS' if not fails else 'FAIL'))
    print('S3C_VERDICT_COUNTS failures=%d notes=%d' % (len(fails), len(notes)))
    return 1 if fails else 0


def write(outdir, name, header, rows):
    buf = [','.join(header)]
    for r in rows:
        buf.append(','.join('"%s"' % str(v).replace('"', '""') for v in r))
    handle = open(os.path.join(outdir, name), 'wb')
    try:
        handle.write(('\n'.join(buf) + '\n').encode('utf-8'))
    finally:
        handle.close()


def counterexample(rb_path, golden_dir):
    """change ONE mos gate net in a temporary copy of the exported table and require rejection.

    The OpenAccess database, the shipped netlists and the delivered evidence are never modified:
    this copies the readback log to a scratch file, rewrites one row, and re-runs the same
    comparison code on it. The intact delivered table must still pass.
    """
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix='s3c_neg_')
    ok = True
    try:
        for other in ('sc1_s3c_golden_mos.csv', 'sc1_s3c_golden_ports.csv',
                      'sc1_s3c_golden_hier.csv', 'sc1_s3c_golden_subinst.csv'):
            shutil.copyfile(os.path.join(golden_dir, other), os.path.join(tmp, other))
        rb = os.path.join(tmp, 'readback.log')
        text = open(rb_path, 'rb').read().decode('utf-8', 'replace')
        rows = text.split('\n')
        target = None
        for i, line in enumerate(rows):
            if 'S3CR-MOS cell="sc1_s3b_p33_bank_7" inst="mp1"' in line:
                target = i
        if target is None:
            print('S3C-NEG: the bank row to tamper with was not found')
            return False
        if 'G="bgate"' not in rows[target]:
            print('S3C-NEG: the bank row does not carry the gate net the counter-example needs')
            return False
        rows[target] = rows[target].replace('G="bgate"', 'G="gate33_faked"')
        handle = open(rb, 'wb')
        try:
            handle.write('\n'.join(rows).encode('utf-8'))
        finally:
            handle.close()
        rc_tampered = run_quiet(tmp, rb, os.path.join(tmp, 'out_tampered'))
        rc_intact = run_quiet(golden_dir, rb_path,
                              os.path.join(tmp, 'out_intact'))
        print('S3C_NEGATIVE rc_tampered=%s (1 must mean refused) rc_intact=%s (0 must mean pass)'
              % (rc_tampered, rc_intact))
        ok = rc_tampered == 1 and rc_intact == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def run_quiet(golden_dir, rb_path, out_dir):
    """re-enter main() with different inputs, swallowing its report lines"""
    keep = sys.stdout
    devnull = open(os.devnull, 'w')
    argv_save = sys.argv
    try:
        sys.stdout = devnull
        # every path main() needs is passed absolutely; the nested runs write their extracted
        # netlist into their own output directory so they can never touch the delivered one
        nested_netlist = os.path.join(out_dir, 'netlist_extracted_under_test.scs')
        sys.argv = ['sc1_s3c_verify_oa.py', '--golden', golden_dir,
                    '--readback', rb_path, '--out', out_dir, '--netlist', nested_netlist]
        return main()
    finally:
        sys.argv = argv_save
        sys.stdout = keep
        devnull.close()


if __name__ == '__main__':
    sys.exit(main())
