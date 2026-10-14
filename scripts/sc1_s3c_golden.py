#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3-C: the golden table, the importer copy and the OA parameter table.

Everything in this file is DERIVED, at run time, from the six byte-frozen masters named in the
S3-C task book section 3. Nothing is typed from memory: if a master changes, the golden table,
the import netlist and the parameter table all change with it, and the --selftest gate refuses
to emit a table whose counts differ from the task book's.

Sub-commands (all offline, no simulator, no OA):
  --emit-golden DIR     sc1_s3c_golden_mos.csv + sc1_s3c_golden_hier.csv + sc1_s3c_golden_ports.csv
  --emit-import PATH    the spiceIn/ASG import copy of the whole hierarchy
  --emit-params PATH    the SKILL parameter table the OA writer loads
  --selftest            structural assertions against the task book

Python 2.6 and Python 3 both run this file, and both must produce the same bytes: the golden
table is the reference the OA readback is compared against, so a platform-dependent number
format would silently change the acceptance criterion.
"""
from __future__ import print_function

import io
import os
import re
import sys

# ---- the six electrical masters (the fault deck is a historical negative, never a schematic)
MASTERS = ["spectre/C2MOS_DFF.scs",
           "spectre/sc1_scan_gate.scs",
           "spectre/sc1_level_shifter_r2d.scs",
           "spectre/sc1_r3_scan_chain.scs",
           "spectre/sc1_s3b_p33_bank.scs",
           "spectre/sc1_s3b_scan_power_1ch.scs"]

# ---- task book section 5: cell -> (port order, signal inputs, outputs, supply ports)
CELL_ORDER = ["c2mos_dff", "sc1_scan_gate", "sc1_ls_core_r2d", "sc1_ls_c1_r2d",
              "sc1_ls_c1_top_r2d", "sc1_r3_scan_chain_1ch", "sc1_s3b_p33_bank_7",
              "sc1_scan_power_1ch_s3c"]
PORTS = {
    "c2mos_dff": ["d", "clk", "q", "qbar", "vdd", "vss"],
    "sc1_scan_gate": ["qbar", "blank", "en", "vdd", "vss"],
    "sc1_ls_core_r2d": ["en", "x", "y", "vdd18", "vdd33", "vss"],
    "sc1_ls_c1_r2d": ["y", "core_ok33", "gate33", "vdd33", "vss"],
    "sc1_ls_c1_top_r2d": ["en", "core_ok33", "gate33", "vdd18", "vdd33", "vss"],
    "sc1_r3_scan_chain_1ch": ["d", "clk", "blank", "core_ok33", "gate33",
                              "vdd18", "vdd33", "vss"],
    "sc1_s3b_p33_bank_7": ["scan", "bgate", "vscan"],
    "sc1_scan_power_1ch_s3c": ["d", "clk", "blank", "core_ok33", "scan",
                               "vdd18", "vdd33", "vscan", "vss"],
}
INPUTS = {
    "c2mos_dff": ["d", "clk"],
    "sc1_scan_gate": ["qbar", "blank"],
    "sc1_ls_core_r2d": ["en"],
    "sc1_ls_c1_r2d": ["y", "core_ok33"],
    "sc1_ls_c1_top_r2d": ["en", "core_ok33"],
    "sc1_r3_scan_chain_1ch": ["d", "clk", "blank", "core_ok33"],
    "sc1_s3b_p33_bank_7": ["bgate"],
    "sc1_scan_power_1ch_s3c": ["d", "clk", "blank", "core_ok33"],
}
OUTPUTS = {
    "c2mos_dff": ["q", "qbar"],
    "sc1_scan_gate": ["en"],
    "sc1_ls_core_r2d": ["x", "y"],
    "sc1_ls_c1_r2d": ["gate33"],
    "sc1_ls_c1_top_r2d": ["gate33"],
    "sc1_r3_scan_chain_1ch": ["gate33"],
    "sc1_s3b_p33_bank_7": ["scan"],
    "sc1_scan_power_1ch_s3c": ["scan"],
}
SUPPLIES = {
    "c2mos_dff": ["vdd", "vss"],
    "sc1_scan_gate": ["vdd", "vss"],
    "sc1_ls_core_r2d": ["vdd18", "vdd33", "vss"],
    "sc1_ls_c1_r2d": ["vdd33", "vss"],
    "sc1_ls_c1_top_r2d": ["vdd18", "vdd33", "vss"],
    "sc1_r3_scan_chain_1ch": ["vdd18", "vdd33", "vss"],
    "sc1_s3b_p33_bank_7": ["vscan"],
    "sc1_scan_power_1ch_s3c": ["vdd18", "vdd33", "vscan", "vss"],
}
# the master each cell is read out of, and the name that master gives it
ORIGIN = {
    "c2mos_dff": ("spectre/C2MOS_DFF.scs", "c2mos_dff"),
    "sc1_scan_gate": ("spectre/sc1_scan_gate.scs", "sc1_scan_gate"),
    "sc1_ls_core_r2d": ("spectre/sc1_level_shifter_r2d.scs", "sc1_ls_core_r2d"),
    "sc1_ls_c1_r2d": ("spectre/sc1_level_shifter_r2d.scs", "sc1_ls_c1_r2d"),
    "sc1_ls_c1_top_r2d": ("spectre/sc1_level_shifter_r2d.scs", "sc1_ls_c1_top_r2d"),
    "sc1_r3_scan_chain_1ch": ("spectre/sc1_r3_scan_chain.scs", "sc1_r3_scan_chain_1ch"),
    "sc1_s3b_p33_bank_7": ("spectre/sc1_s3b_p33_bank.scs", "sc1_s3b_p33_bank_7"),
    "sc1_scan_power_1ch_s3c": ("spectre/sc1_s3b_scan_power_1ch.scs", "sc1_s3b_scan_power_1ch"),
}
EXPECTED_MOS = {"c2mos_dff": 18, "sc1_scan_gate": 4, "sc1_ls_core_r2d": 6,
                "sc1_ls_c1_r2d": 4, "sc1_ls_c1_top_r2d": 0, "sc1_r3_scan_chain_1ch": 0,
                "sc1_s3b_p33_bank_7": 7, "sc1_scan_power_1ch_s3c": 0}
EXPANDED_MOS = {"c2mos_dff": 18, "sc1_scan_gate": 4, "sc1_ls_core_r2d": 6,
                "sc1_ls_c1_r2d": 4, "sc1_ls_c1_top_r2d": 10, "sc1_r3_scan_chain_1ch": 32,
                "sc1_s3b_p33_bank_7": 7, "sc1_scan_power_1ch_s3c": 39}
MOS_MODELS = set(["n18", "p18", "n33", "p33"])
TOPOLOGY_SHELL = "s3c_asg_shell"          # spiceIn's topCell may not also be a subckt (SPICEIN-77)

SUBCKT_RX = re.compile(r"^subckt\s+(\S+)\s*\(([^)]*)\)", re.M)
KV_RX = re.compile(r"(\w+)\s*=\s*(\S+)")
DESIGNVAR_RX = re.compile(r"^\s*parameters\s+(\w+)\s*=\s*(\S+)", re.M)
XINST_RX = re.compile(r"^\s*(X[A-Za-z_]\w*)\s*\(\s*([^)]+?)\s*\)\s*(\w+)\s*$", re.M)
SINGLE_RX = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(\s*([^)]+?)\s*\)\s*(\w+)\s+l=(\S+)\s+w=(\S+)", re.M)


def strip_comment(line):
    out = []
    in_str = False
    for ch in line:
        if ch == '"':
            in_str = not in_str
        if not in_str and ch == '/' and len(out) and out[-1] == '/':
            out.pop()                      # drop the first slash of the // marker too
            break
        out.append(ch)
    return ''.join(out).rstrip()


def parse_subckts(path):
    """{cell: {'ports': [...], 'mos': [...], 'x': [...], 'vars': {...}}} in file order."""
    text = io.open(path, encoding='utf-8', errors='replace').read()
    lines = [strip_comment(l) for l in text.split('\n')]
    cells, cur = [], None
    for ln in lines:
        m = re.match(r"^\s*subckt\s+(\S+)\s*\(([^)]*)\)", ln)
        if m:
            cur = {'name': m.group(1), 'ports': m.group(2).split(), 'lines': [], 'vars': {}}
            cells.append(cur)
            continue
        if cur is None:
            continue
        if re.match(r"^\s*ends\b", ln):
            cur = None
            continue
        if not ln.strip():
            continue
        cur['lines'].append(ln)
    out = {}
    for cell in cells:
        mos, xs, vars_ = [], [], {}
        for ln in cell['lines']:
            if DESIGNVAR_RX.match(ln) and not re.match(r"^\s*\w+\s*\(", ln):
                # a `parameters' line may carry several design variables at once
                # (sc1_scan_gate.scs writes "parameters lg=2e-7 wn=2e-6 wp=4e-6")
                for k, v in KV_RX.findall(ln):
                    vars_[k] = v
                continue
            sm = SINGLE_RX.match(ln)
            if sm and sm.group(3) in MOS_MODELS:
                mos.append({'inst': sm.group(1), 'nets': sm.group(2).split(),
                            'model': sm.group(3), 'l_src': sm.group(4), 'w_src': sm.group(5)})
                continue
            xm = XINST_RX.match(ln)
            if xm:
                xs.append({'inst': xm.group(1), 'nets': xm.group(2).split(),
                           'child': xm.group(3)})
                continue
            if re.match(r"^\s*(iprobe|vsrc|isrc|res|cap|r|c)\b", ln) or ' iprobe' in ln:
                continue                      # measurement plumbing: never a schematic device
            raise RuntimeError('%s: unparsed line inside subckt %s: %r'
                               % (path, cell['name'], ln))
        out[cell['name']] = {'ports': cell['ports'], 'mos': mos, 'x': xs, 'vars': vars_}
    return out


def resolve(value, vars_):
    """a size token plus the subckt's own design variables -> metres"""
    token = value.strip()
    if re.match(r"^[0-9.]", token):
        return float(token)
    if token in vars_:
        return float(vars_[token])
    raise RuntimeError('size token %r is neither a number nor a design variable of this subckt '
                       '(known: %s)' % (token, ' '.join(sorted(vars_))))


def metric(value):
    """metres -> the shortest string the OA CDF parser reads back as the same number.

    The largest SI suffix that still gives a whole number wins, so 2e-07 is "200n" and 1e-04 is
    "100u" -- the spellings a reviewer recognises, and the ones SCH-2/SCH-3 measured the CDF
    parser accepts (it normalises 1e-06 to "1u" on its own).
    """
    for scale, suffix in ((1e-3, 'm'), (1e-6, 'u'), (1e-9, 'n'), (1e-12, 'p'), (1e-15, 'f')):
        q = value / scale
        if abs(q - round(q)) < 1e-9 and round(q) > 0 and abs(q) < 1e9:
            return '%d%s' % (int(round(q)), suffix)
    return '%.17g' % value


def mtxt(value):
    """the shortest fixed-point/scientific token that round-trips to this exact double.

    Written by hand rather than with repr() because Python 2.6 and Python 3 pick their float
    text differently, and the golden table is the reference the OA readback is judged against --
    a platform-dependent spelling would change the acceptance criterion between the two runs.
    """
    for digits in range(1, 18):
        s = ('%.' + str(digits) + 'g') % value
        try:
            if float(s) == value:
                return s
        except ValueError:
            continue
    return '%.17g' % value


def expand(cells, cell, path_prefix=''):
    """hierarchy walk: leaf device rows with their top-anchored path"""
    rows = []
    info = cells[cell]
    for m in info['mos']:
        rows.append({'cell': cell, 'inst': m['inst'],
                     'path': path_prefix + m['inst'],
                     'model': m['model'], 'nets': m['nets'],
                     'l_m': resolve(m['l_src'], info['vars']),
                     'w_m': resolve(m['w_src'], info['vars']),
                     'l_src': m['l_src'], 'w_src': m['w_src']})
    for x in info['x']:
        rows.extend(expand(cells, x['child'], path_prefix + x['inst'] + '.'))
    return rows


def load_all(root):
    cells = {}
    for rel in MASTERS:
        for name, info in parse_subckts(os.path.join(root, rel)).items():
            info['file'] = rel
            if name in cells:
                raise RuntimeError('subckt %s is defined in two masters' % name)
            cells[name] = info
    # the formal top is the S3-B top minus its iprobe, with gate33 and bgate merged
    top = dict(cells['sc1_s3b_scan_power_1ch'])
    top['ports'] = PORTS['sc1_scan_power_1ch_s3c']
    xs = []
    for x in top['x']:
        if x['child'] == 'iprobe':
            continue
        if x['inst'] == 'Xbank':
            x = {'inst': x['inst'], 'child': x['child'],
                 'nets': ['gate33' if n == 'bgate' else n for n in x['nets']]}
        xs.append(x)
    top['x'] = xs
    cells['sc1_scan_power_1ch_s3c'] = top
    return cells


def golden_rows(cells):
    """the 39 leaf devices of the channel, each with its owning cell and its top-anchored path"""
    top_rows = expand(cells, 'sc1_scan_power_1ch_s3c')
    return top_rows


def write_text(path, text):
    """LF-exact bytes on both interpreters.

    Python 2.6's io.open in text mode refuses a str, and any platform-dependent line ending would
    break the md5 comparison that proves the guest and the workstation derived the same golden.
    """
    handle = open(path, 'wb')
    try:
        handle.write(text.encode('utf-8'))
    finally:
        handle.close()


def write_csv(path, header, rows):
    buf = [','.join(header)]
    for r in rows:
        buf.append(','.join(['"%s"' % str(v).replace('"', '""') for v in r]))
    write_text(path, '\n'.join(buf) + '\n')


def emit_golden(cells, outdir):
    top_rows = golden_rows(cells)
    h = ['cell', 'inst', 'path_from_top', 'model', 'd', 'g', 's', 'b',
         'l_m', 'w_m', 'l_src', 'w_src', 'master_file']
    rows = []
    for r in sorted(top_rows, key=lambda x: (x['path'].count('.'), x['cell'], x['inst'])):
        rows.append([r['cell'], r['inst'], r['path'], r['model'],
                     r['nets'][0], r['nets'][1], r['nets'][2], r['nets'][3],
                     mtxt(r['l_m']), mtxt(r['w_m']), r['l_src'], r['w_src'],
                     cells[r['cell']]['file']])
    write_csv(os.path.join(outdir, 'sc1_s3c_golden_mos.csv'), h, rows)

    hh = ['cell', 'direct_children', 'own_mos', 'expanded_mos', 'ports', 'master_file']
    hrows = []
    for cell in CELL_ORDER:
        info = cells[cell]
        hrows.append([cell, ' '.join([x['inst'] + ':' + x['child'] for x in info['x']]) or '-',
                      len(info['mos']), EXPANDED_MOS[cell], len(info['ports']), info['file']])
    write_csv(os.path.join(outdir, 'sc1_s3c_golden_hier.csv'), hh, hrows)

    hp = ['cell', 'ordinal', 'port', 'declared_direction', 'role', 'master_port_order']
    prow = []
    for cell in CELL_ORDER:
        order = ' '.join(cells[cell]['ports'])
        for i, p in enumerate(cells[cell]['ports']):
            direction = ('input' if p in INPUTS[cell] else
                         'output' if p in OUTPUTS[cell] else 'inputOutput')
            role = ('signal_in' if p in INPUTS[cell] else
                    'signal_out' if p in OUTPUTS[cell] else 'supply')
            prow.append([cell, i, p, direction, role, order])
    write_csv(os.path.join(outdir, 'sc1_s3c_golden_ports.csv'), hp, prow)

    # one row per pin of every sub-circuit instance: the parent cell, the instance, the child it
    # instantiates, and which parent net each of the child's own ports lands on. Readback compares
    # these against the OA bindings, which is what proves the hierarchy is wired rather than drawn.
    hs = ['cell', 'inst', 'child', 'port_ordinal', 'child_port', 'parent_net']
    srow = []
    for cell in CELL_ORDER:
        for x in cells[cell]['x']:
            child_ports = cells[x['child']]['ports']
            if len(child_ports) != len(x['nets']):
                raise RuntimeError('%s.%s connects %d nets to a %d-port child'
                                   % (cell, x['inst'], len(x['nets']), len(child_ports)))
            for i, p in enumerate(child_ports):
                srow.append([cell, x['inst'], x['child'], i, p, x['nets'][i]])
    write_csv(os.path.join(outdir, 'sc1_s3c_golden_subinst.csv'), hs, srow)
    if len(srow) != 39:
        raise RuntimeError('the sub-circuit pin table has %d rows, expected 39 (17 chain + 11 ls + 11 top)'
                           % len(srow))
    print('S3C_GOLDEN_SUBINST_ROWS: %d' % len(srow))
    return len(rows)


def emit_import(cells, path):
    """the spiceIn copy: same nets, same models, same instances; sizes resolved to literals.

    Three deliberate, recorded differences from the masters, and no others:
      1. design variables are substituted by their own values (spiceIn leaves `l=ln' as
         unevaluable text in the OA property; SCH-2 measured that);
      2. port direction declarations are added, which carry no connectivity;
      3. the formal top drops the measurement iprobe and merges its two terminals into gate33.
    """
    order = [c for c in CELL_ORDER if c != 'sc1_scan_power_1ch_s3c'] + ['sc1_scan_power_1ch_s3c']
    out = ['// S3-C import copy generated by scripts/sc1_s3c_golden.py from the six frozen masters.',
           '// Sizes are the masters\' own values with design variables substituted; nets, models',
           '// and instance names are unchanged. See reports/scan_driver_s3c_schematic_symbol.md.',
           'simulator lang=spectre insensitive=yes',
           '']
    for cell in order:
        info = cells[cell]
        out.append('subckt %s (%s)' % (cell, ' '.join(info['ports'])))
        for group, names in (('input', INPUTS[cell]), ('output', OUTPUTS[cell]),
                             ('inputOutput', SUPPLIES[cell])):
            if names:
                out.append('  parameters %s %s' % (' '.join(names), group))
        for m in info['mos']:
            out.append('  %s (%s) %s l=%s w=%s'
                       % (m['inst'], ' '.join(m['nets']), m['model'],
                          mtxt(resolve(m['l_src'], info['vars'])),
                          mtxt(resolve(m['w_src'], info['vars']))))
        for x in info['x']:
            out.append('  %s (%s) %s' % (x['inst'], ' '.join(x['nets']), x['child']))
        out.append('ends %s' % cell)
        out.append('')
    top = cells['sc1_scan_power_1ch_s3c']
    out.append('// importer shell: spiceIn refuses a topCell that is also a subckt in the file')
    out.append('// (SPICEIN-77), so the delivered top is imported as a sub-circuit and this shell')
    out.append('// is the file scope. It is plumbing, not part of the eight delivered cells.')
    out.append('parameters %s inputOutput' % ' '.join(top['ports']))
    out.append('Xtop (%s) sc1_scan_power_1ch_s3c' % ' '.join(top['ports']))
    write_text(path, '\n'.join(out) + '\n')
    return len(out)


def emit_dirs(cells, path):
    """the S3-C1 direction table: one row per (cell, port) for both views, from the same declaration

    scripts/sc1_s3c_golden.py is the only place a direction is decided, and S3-C1 section 4 says the
    OA objects must carry it. The SKILL writer loads this file and refuses to run unless the row
    count is exactly twice the number of declared ports, so a cell that lost a port cannot be
    half-fixed.
    """
    lines = [';; generated by scripts/sc1_s3c_golden.py -- the declared direction of every port,',
             ';; rows: cell port direction',
             's3c1DirTable = list(nil']
    n = 0
    for cell in CELL_ORDER:
        for p in cells[cell]['ports']:
            direction = ('input' if p in INPUTS[cell] else
                         'output' if p in OUTPUTS[cell] else 'inputOutput')
            lines.append('    list("%s" "%s" "%s")' % (cell, p, direction))
            n += 1
    lines.append(')')
    write_text(path, '\n'.join(lines) + '\n')
    return n


def emit_params(cells, path):
    """the CDF-keyed size table the OA writer loads, one row per leaf device of the whole channel"""
    top_rows = golden_rows(cells)
    lines = [';; generated by scripts/sc1_s3c_golden.py -- sizes are the masters\' values,',
             ';; written through the parameter names each master\'s own CDF defines.',
             ';; rows: cell instance l w fw m fingers',
             's3cParamTable = list(nil']
    for r in sorted(top_rows, key=lambda x: (x['cell'], x['inst'])):
        # fw (total finger width) equals w because every delivered device is one finger:
        # the task book forbids folding the seven bank fingers into a multiplier.
        l_s, w_s = metric(r['l_m']), metric(r['w_m'])
        lines.append('    list("%s" "%s" "%s" "%s" "%s" "1" "1")'
                     % (r['cell'], r['inst'], l_s, w_s, w_s))
    lines.append(')')
    write_text(path, '\n'.join(lines) + '\n')
    return len(top_rows)


def selftest(cells):
    fails = []
    top_rows = golden_rows(cells)
    if len(top_rows) != 39:
        fails.append('the formal top expands to %d devices, the task book says 39' % len(top_rows))
    for cell in CELL_ORDER:
        info = cells[cell]
        if info['ports'] != PORTS[cell]:
            fails.append('%s port order %s differs from the task book %s'
                         % (cell, info['ports'], PORTS[cell]))
        if len(info['mos']) != EXPECTED_MOS[cell]:
            fails.append('%s holds %d devices of its own, expected %d'
                         % (cell, len(info['mos']), EXPECTED_MOS[cell]))
        n = len(expand(cells, cell))
        if n != EXPANDED_MOS[cell]:
            fails.append('%s expands to %d devices, the task book says %d'
                         % (cell, n, EXPANDED_MOS[cell]))
    keys = [(r['cell'], r['inst']) for r in top_rows]
    if len(keys) != len(set(keys)):
        fails.append('a (cell, instance) pair is not unique in the 39-device expansion')
    if sorted(set(keys)) != sorted(set(sum([[(c, m['inst']) for m in cells[c]['mos']]
                                            for c in CELL_ORDER
                                            if c != 'sc1_scan_power_1ch_s3c'], []))):
        fails.append('the expansion does not consist of exactly the leaf cells\' own devices')
    per_cell = {}
    for r in top_rows:
        per_cell[r['cell']] = per_cell.get(r['cell'], 0) + 1
    if per_cell != {'c2mos_dff': 18, 'sc1_scan_gate': 4, 'sc1_ls_core_r2d': 6,
                    'sc1_ls_c1_r2d': 4, 'sc1_s3b_p33_bank_7': 7}:
        fails.append('per-cell device counts are %s' % sorted(per_cell.items()))
    paths = [r['path'] for r in top_rows]
    if len(paths) != len(set(paths)):
        fails.append('two devices share one hierarchical path')
    bank = [r for r in top_rows if r['cell'] == 'sc1_s3b_p33_bank_7']
    if len(bank) != 7 or sorted(set(r['inst'] for r in bank)) != sorted(['mp%d' % i
                                                                        for i in range(1, 8)]):
        fails.append('the bank is not seven explicit mp1..mp7 instances')
    if any(r['l_m'] != 4e-07 or r['w_m'] != 1e-04 for r in bank):
        fails.append('a bank device is not L=4e-07 W=1e-04')
    if abs(sum(r['w_m'] for r in bank) - 7e-04) > 1e-16:
        fails.append('the seven bank widths add up to %r, not 700 um'
                     % sum(r['w_m'] for r in bank))
    if any(r['nets'][2] != 'vscan' or r['nets'][3] != 'vscan' for r in bank):
        fails.append('a bank device does not tie BOTH source and body to vscan')
    nand = cells['sc1_ls_c1_r2d']
    stack = [m for m in nand['mos'] if m['inst'] == 'mn_nt'][0]
    if stack['nets'][2] != 'ns_m' or stack['nets'][3] != 'vss':
        fails.append('the stacked NMOS is not source=ns_m body=vss -- the well/source split is lost')
    top = cells['sc1_scan_power_1ch_s3c']
    if any(x['child'] == 'iprobe' for x in top['x']):
        fails.append('the formal top still carries the measurement iprobe')
    if [x for x in top['x'] if x['inst'] == 'Xbank'][0]['nets'] != ['scan', 'gate33', 'vscan']:
        fails.append('the formal top does not merge bgate into gate33')
    if metric(2e-07) != '200n' or metric(1e-04) != '100u' or metric(5e-06) != '5u':
        fails.append('metric() produced %s %s %s' % (metric(2e-07), metric(1e-04), metric(5e-06)))
    for r in top_rows:
        for v in (r['l_m'], r['w_m']):
            if float(mtxt(v)) != v:
                fails.append('mtxt(%r) does not round-trip' % v)
        if not re.match(r'^[0-9a-zA-Z.\-+]+$', metric(r['l_m'])) or \
           not re.match(r'^[0-9a-zA-Z.\-+]+$', metric(r['w_m'])):
            fails.append('metric(%r) is not a single CDF token' % r['w_m'])
    return fails


def main():
    root = os.environ.get('PROJ', '.')
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    cells = load_all(root)
    fails = selftest(cells)
    print('S3C_SELFTEST: %s' % ('PASS' if not fails else 'FAIL'))
    for f in fails:
        print('  SELFTEST-FAIL: %s' % f)
    if fails:
        return 1
    top_rows = golden_rows(cells)
    print('S3C_GOLDEN_CELLS: %d' % len(CELL_ORDER))
    print('S3C_GOLDEN_LEAF_DEVICES: %d' % len(top_rows))
    if '--emit-golden' in args:
        outdir = args[args.index('--emit-golden') + 1]
        n = emit_golden(cells, outdir)
        print('S3C_GOLDEN_ROWS: %d dir=%s' % (n, outdir))
    if '--emit-import' in args:
        p = args[args.index('--emit-import') + 1]
        n = emit_import(cells, p)
        print('S3C_IMPORT_LINES: %d file=%s' % (n, p))
    if '--emit-params' in args:
        p = args[args.index('--emit-params') + 1]
        n = emit_params(cells, p)
        print('S3C_PARAM_ROWS: %d file=%s' % (n, p))
    if '--emit-dirs' in args:
        p = args[args.index('--emit-dirs') + 1]
        n = emit_dirs(cells, p)
        if n != 48:
            print('S3C-DIR-FAIL: %d declared ports, the task book table has 48' % n)
            return 1
        print('S3C_DIR_ROWS: %d file=%s (each is written on BOTH views, so 96 objects)'
              % (n, p))
    return 0


if __name__ == '__main__':
    sys.exit(main())
