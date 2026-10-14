# -*- coding: utf-8 -*-
"""DATA-6 section 8: the OA inputs, derived from the same masters the native TT round ran.

    python scripts/dd1_d6_golden.py --emit-all --out-dir cadence_work/data_d6_oa/asg_in

Nothing is typed in here that the netlists do not already say: the eight cells, their ports, their
instance bindings and all twenty-nine device geometries come out of `dd1_d6_unit_tt`'s own audited
walkers (S2.parse_masters / S2.resolve_devices over the repository bytes). Four files are written:

  dd1_d6_import.scs          the spiceIn copy: same nets, same models, same instances, sizes with
                             design variables substituted, port directions declared
  dd1_d6_param_table.gen.il  the CDF-keyed size table the accepted sc1_s3c_build_oa.il loads
  dd1_d6_dir_table.gen.il    one row per (cell, port) for both views
  dd1_d6_golden_*.csv         the golden the independent read-back is compared against

The one judgement this file makes is the port DIRECTION: the two copied Data subckts and the four new
masters declare it, so those cells are read off their own declarations; the two frozen Scan masters
declare nothing and are not edited, so their directions are given here and the disagreement with any
declaration is refused. `--selftest` re-parses the emitted import copy and requires the same 29
devices with the same nets, so a substitution bug cannot survive into the tool.
"""
from __future__ import print_function

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sc1_r2e_s2_tt as S2
import dd1_d6_unit_tt as D6

CELL_ORDER = ('c2mos_dff', 'sc1_scan_gate', 'dd1_inv18', 'dd1_control_1ch', 'data_sink_1ch',
              'data_bias_ref', 'dd1_sink_unit_1ch', 'dd1_data_top_1ch')
# the pairing is written out, not zipped: the two lists are in different orders (the delivered cell
# order is leaf-first through the hierarchy, D6.CELLS is the include order of the deck), and a zip
# here would silently hand each master the wrong file
CELL_FILE = {'c2mos_dff': 'C2MOS_DFF.scs', 'sc1_scan_gate': 'sc1_scan_gate.scs',
             'dd1_inv18': 'dd1_d6_inv18.scs', 'dd1_control_1ch': 'dd1_d6_control.scs',
             'data_sink_1ch': 'dd1_d6_sink_core.scs', 'data_bias_ref': 'dd1_d6_bias_core.scs',
             'dd1_sink_unit_1ch': 'dd1_d6_sink_unit.scs', 'dd1_data_top_1ch': 'dd1_d6_top.scs'}
FILE_CELLS = dict((v, k) for k, v in CELL_FILE.items())
TOP = 'dd1_data_top_1ch'
SHELL = 'dd1_d6_asg_shell'
TOTAL = 29
u = D6.u

# the directions the two frozen masters do not declare (POC_ASSUMPTION naming, read off the netlist's
# own use of each port: d/clk/blank are driven in, q/qbar are the store's outputs)
DECLARED_ELSEWHERE = {
    'c2mos_dff': {'d': 'input', 'clk': 'input', 'q': 'output', 'qbar': 'output',
                  'vdd': 'inputOutput', 'vss': 'inputOutput'},
    'sc1_scan_gate': {'qbar': 'input', 'blank': 'input', 'en': 'output',
                      'vdd': 'inputOutput', 'vss': 'inputOutput'},
}


def metric(value):
    """metres -> the shortest string the OA CDF parser reads back as the same number"""
    v = float(value)
    for scale, suffix in ((1e-3, 'm'), (1e-6, 'u'), (1e-9, 'n'), (1e-12, 'p'), (1e-15, 'f')):
        q = v / scale
        if abs(q - round(q)) < 1e-9 and round(q) > 0:
            return '%dm' % round(q) if suffix == 'm' else '%d%s' % (round(q), suffix)
    return '%.6g' % v


def masters():
    return S2.parse_masters(''.join(t for _n, t in D6.cell_texts()) + '\n' + D6.TOP_INST)


def declared_directions():
    """every `parameters <ports> <direction>' line in the repository bytes, per cell"""
    out = {}
    for name, txt in [(FILE_CELLS[c], u(io.open(os.path.join(PROJ, 'spectre', c),
                                                encoding='utf-8', errors='replace').read()))
                      for c in D6.CELLS]:
        for raw in txt.split('\n'):
            toks = raw.split()
            if len(toks) >= 3 and toks[0].lower() == 'parameters':
                direction = toks[-1].lower()
                if direction in ('input', 'output', 'inputoutput', 'inout'):
                    for p in toks[1:-1]:
                        out.setdefault(name, {})[p] = ('inputOutput'
                                                       if direction in ('inputoutput', 'inout')
                                                       else direction)
    return out


def dir_table(masters_):
    declared = declared_directions()
    table = {}
    for cell in CELL_ORDER:
        ports = masters_[cell]['ports']
        got = dict(DECLARED_ELSEWHERE.get(cell, {}))
        conflict = []
        for p, d in declared.get(cell, {}).items():
            if p in got and got[p] != d:
                conflict.append('%s.%s' % (cell, p))
            got[p] = d
        if conflict:
            raise SystemExit('DIRECTION_CONFLICT %s: the netlist and this file disagree'
                             % ', '.join(conflict))
        missing = [p for p in ports if p not in got]
        if missing:
            raise SystemExit('DIRECTION_MISSING %s: %s' % (cell, ' '.join(missing)))
        table[cell] = dict((p, got[p]) for p in ports)
    return table


def golden_rows(masters_, table):
    """the 29 leaf devices at their OA-addressed paths, plus every sub-circuit instance"""
    devs = []
    for path, model, nets in D6.devices_of():
        cell = D6.owner(path)
        leaf = path.split('.')[-1]
        row = [r for r in D6.device_size_rows() if r[0] == path][0]
        devs.append({'cell': cell, 'inst': leaf, 'model': model, 'path': path,
                     'l_m': row[3], 'w_m': row[5], 'm': row[6], 'l_raw': row[2], 'w_raw': row[4],
                     'nets': list(nets), 'file': CELL_FILE[cell]})
    subs = []
    for cell in CELL_ORDER:
        for kind, name, nets, m2 in masters_[cell]['items']:
            if kind == 'sub':
                binds = ' '.join('%s=%s' % (p, n) for p, n in zip(masters_[m2]['ports'], nets))
                subs.append({'cell': cell, 'inst': name, 'child': m2, 'nets': ' '.join(nets),
                             'bindings': binds})
    return devs, subs


def emit_import(devs_by_cell, masters_, table, path):
    out = ['// DATA-6 dd1 import copy, generated by scripts/dd1_d6_golden.py from the eight masters',
           '// the native TT round ran. Nets, models and instance names are unchanged; design',
           '// variables are substituted by their own values and port directions are declared.',
           'simulator lang=spectre insensitive=yes', '']
    sizes = {}
    for d in devs_by_cell:
        sizes[(d['cell'], d['inst'])] = d
    for cell in CELL_ORDER:
        info = masters_[cell]
        out.append('subckt %s (%s)' % (cell, ' '.join(info['ports'])))
        for group in ('input', 'output', 'inputOutput'):
            names = [p for p in info['ports'] if table[cell][p] == group]
            if names:
                out.append('  parameters %s %s' % (' '.join(names), group))
        for kind, name, nets, m2 in info['items']:
            if kind == 'sub':
                out.append('  %s (%s) %s' % (name, ' '.join(nets), m2))
            else:
                d = sizes[(cell, name)]
                out.append('  %s (%s) %s l=%s w=%s'
                           % (name, ' '.join(nets), m2, metric(d['l_m']), metric(d['w_m'])))
        out.append('ends %s' % cell)
        out.append('')
    out.append('// importer shell: spiceIn refuses a topCell that is also a subckt in the file')
    out.append('// (SPICEIN-77), so the delivered top is imported as a sub-circuit and this shell is')
    out.append('// the file scope. It is plumbing, not part of the eight delivered cells.')
    out.append('parameters %s inputOutput' % ' '.join(masters_[TOP]['ports']))
    out.append('Xtop (%s) %s' % (' '.join(masters_[TOP]['ports']), TOP))
    write(path, '\n'.join(out) + '\n')
    return len(out)


def emit_params(devs_by_cell, path):
    lines = [';; generated by scripts/dd1_d6_golden.py -- sizes are the masters\' own values,',
             ';; written through the parameter names each master\'s CDF defines.',
             ';; rows: cell instance l w fw m fingers',
             's3cParamTable = list(nil']
    for d in sorted(devs_by_cell, key=lambda x: (x['cell'], x['inst'])):
        lines.append('    list("%s" "%s" "%s" "%s" "%s" "1" "1")'
                     % (d['cell'], d['inst'], metric(d['l_m']), metric(d['w_m']), metric(d['w_m'])))
    lines.append(')')
    write(path, '\n'.join(lines) + '\n')
    return len(devs_by_cell)


def emit_dirs(table, path):
    lines = [';; generated by scripts/dd1_d6_golden.py -- the declared direction of every port,',
             ';; rows: cell port direction',
             's3c1DirTable = list(nil']
    n = 0
    for cell in CELL_ORDER:
        for p in masters()[cell]['ports']:
            lines.append('    list("%s" "%s" "%s")' % (cell, p, table[cell][p]))
            n += 1
    lines.append(')')
    write(path, '\n'.join(lines) + '\n')
    return n


def emit_golden_csvs(devs_by_cell, subs, table, masters_, evdir):
    S2.write_rows(os.path.join(evdir, 'dd1_d6_oa_golden_devices.csv'),
                  [[d['cell'], d['inst'], d['model'], d['path'], d['l_m'], d['w_m'], d['m'],
                    d['l_raw'], d['w_raw'], d['file']] + d['nets'] for d in devs_by_cell],
                  ['cell', 'inst', 'model', 'path_from_top', 'l_m', 'w_m', 'm', 'l_raw', 'w_raw',
                   'master_file', 'D', 'G', 'S', 'B'])
    S2.write_rows(os.path.join(evdir, 'dd1_d6_oa_golden_subinst.csv'),
                  [[s['cell'], s['inst'], s['child'], s['nets'], s['bindings']] for s in subs],
                  ['cell', 'inst', 'child_master', 'nets', 'bindings'])
    rows = []
    for cell in CELL_ORDER:
        for i, p in enumerate(masters_[cell]['ports']):
            rows.append([cell, i, p, table[cell][p]])
    S2.write_rows(os.path.join(evdir, 'dd1_d6_oa_golden_ports.csv'), rows,
                  ['cell', 'ordinal', 'port', 'direction'])
    return len(devs_by_cell), len(subs), len(rows)


def write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(D6.u(text))


def selftest(devs_by_cell, subs, table, masters_, import_path):
    fails = []
    if len(devs_by_cell) != TOTAL:
        fails.append('%d devices, the task book says %d' % (len(devs_by_cell), TOTAL))
    mix = {}
    for d in devs_by_cell:
        mix[d['model']] = mix.get(d['model'], 0) + 1
    if mix != D6.EXPECT_MIX:
        fails.append('model mix %s differs from %s' % (mix, D6.EXPECT_MIX))
    # the round trip: resolve the same deck over the masters and over the emitted copy, and require
    # the identical circuit. One shared deck line is what makes this a comparison rather than two
    # unrelated namings -- the file-scope shell gives its own net names, exactly as a testbench does.
    again = S2.parse_masters(u(io.open(import_path, encoding='utf-8', errors='replace').read()))
    if sorted(again.keys()) != sorted(CELL_ORDER):
        fails.append('the import copy parses to %s, expected the eight delivered cells'
                     % ' '.join(sorted(again.keys())))
    deck = 'Xtop (%s) %s\n' % (' '.join(masters_[TOP]['ports']), TOP)
    from_masters = S2.resolve_devices(deck, ''.join(t for _n, t in D6.cell_texts()))
    from_copy = S2.resolve_devices(deck, u(io.open(import_path, encoding='utf-8',
                                                   errors='replace').read()))
    got = sorted((p, m, tuple(n)) for p, m, n in from_copy)
    want = sorted((p, m, tuple(n)) for p, m, n in from_masters)
    if got != want:
        diff = [x for x in want if x not in got][:3]
        fails.append('the import copy does not round-trip: %d devices differ, first %s'
                     % (len([x for x in want if x not in got]), diff))
    for cell in CELL_ORDER:
        if again.get(cell, {}).get('ports') != masters_[cell]['ports']:
            fails.append('%s port order changed in the import copy' % cell)
        text = u(io.open(os.path.join(PROJ, 'spectre', CELL_FILE[cell]), encoding='utf-8',
                         errors='replace').read())
        if not re.search(r'^\s*subckt\s+%s\b' % cell, text, re.M):
            fails.append('%s is not the subckt in %s -- the cell/file pairing is wrong'
                         % (cell, CELL_FILE[cell]))
    if len(subs) != 7:
        fails.append('%d sub-circuit instances, expected 7 (Xff Xmask Xinv Xctrl Xsink Xbias Xunit)'
                     % len(subs))
    return fails


def main():
    root = os.environ.get('PROJ', PROJ)
    out_dir = os.path.join(root, 'cadence_work', 'data_d6_oa', 'asg_in')
    evdir = os.path.join(root, 'results', 'evidence')
    masters_ = masters()
    table = dir_table(masters_)
    devs, subs = golden_rows(masters_, table)
    imp = os.path.join(out_dir, 'dd1_d6_import.scs')
    emit_import(devs, masters_, table, imp)
    nparam = emit_params(devs, os.path.join(out_dir, 'dd1_d6_param_table.gen.il'))
    ndir = emit_dirs(table, os.path.join(out_dir, 'dd1_d6_dir_table.gen.il'))
    g = emit_golden_csvs(devs, subs, table, masters_, evdir)
    fails = selftest(devs, subs, table, masters_, imp)
    print('D6_GOLDEN devices=%d subinst=%d ports=%d params=%d dirs=%d import=%s'
          % (len(devs), len(subs), g[2], nparam, ndir, imp))
    for f in fails:
        print('  SELFTEST-FAIL: %s' % f)
    print('D6_SELFTEST_OA: %s' % ('PASS' if not fails else 'FAIL'))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
