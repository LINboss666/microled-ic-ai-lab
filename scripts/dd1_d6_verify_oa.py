# -*- coding: utf-8 -*-
"""DATA-6 section 8: compare the independent OpenAccess read-back against the derived golden.

    python scripts/dd1_d6_verify_oa.py --log <oa_readback.log>

The read-back comes from a Virtuoso process of its own (skill/sc1_s3c_readback.il, run through
scripts/dd1_d6_run_oa.sh) AFTER the writing session has exited, so every row here is off the disk.
The golden comes from scripts/dd1_d6_golden.py, which derived it from the same masters the native TT
round simulated. This file asks the read-back whether it matches the golden, and reports the
differences it finds; it never edits either side.

Five things are checked, each with its own verdict, because one number hiding four questions is how
this project's earlier rounds got burned:

  device count    29 PDK devices across the eight cells, and none the golden does not name
  geometry        the CDF-parsed l and w against the master's own value; the raw property and simW
                  are shipped too (SCH-2 measured that raw and CDF can disagree)
  connectivity    every device terminal by NAME (D/G/S/B) and every sub-instance pin binding,
                  because this PDK reports terminals in different orders across device families
  ports           schematic and symbol terminal names + directions, and the schematic order
  library         every device model is a PDK model and every child instance lives in this task's lib
"""
from __future__ import print_function

import io
import optparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sc1_r2e_s2_tt as S2
import dd1_d6_unit_tt as D6
import dd1_d6_golden as G

UNITS = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
LIB = 'microled_data_d6'
TERMINALS = ('D', 'G', 'S', 'B')
ROWS_HDR = S2.ROWS_HDR
FIELD_KEY = re.compile(r'\s(\w+)=')


def parse_fields(line):
    """split `key=value' pairs whose VALUES may contain spaces (bindings, terminals lists)"""
    hits = list(FIELD_KEY.finditer(line))
    out = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(line)
        out[m.group(1)] = line[m.end():end].strip()
    return out


def unq(text):
    return (text or '').strip().strip('"')


def master_lib(master):
    """the library part of a read-back master="lib"/"cell":"view"""
    return unq((master or '').split('/')[0])


def parse_len(text):
    """'200n' / '0.2u' / '2e-06' -> metres; anything unparsable stays None, never 0"""
    s = (text or '').strip().strip('"')
    m = re.match(r'^([0-9.]+)([fpnum])?m$', s)
    if m:
        return float(m.group(1)) * UNITS.get(m.group(2) or 'm', 1.0)
    m = re.match(r'^([0-9.eE+-]+)$', s)
    if m:
        return float(s)
    return None


def read_log(path):
    """the S3CR read-back: one row per device and one per instance, both views' cell summaries"""
    mos, insts, cells, dcheck, api = [], [], {}, [], []
    for raw in io.open(path, encoding='utf-8', errors='replace'):
        line = raw.rstrip('\n')
        if not line.startswith('S3CR-'):
            continue
        head = line.split()[0]
        if head in ('S3CR_DONE', 'S3CR-BEGIN'):
            continue
        fields = parse_fields(line)
        if head == 'S3CR-MOS':
            mos.append(fields)
        elif head == 'S3CR-INST':
            insts.append(fields)
        elif head == 'S3CR-CELL':
            cells[unq(fields.get('cell'))] = line[:120]
        elif head == 'S3CR-DBCHECK':
            dcheck.append(fields)
        elif head == 'S3CR-API':
            api.append(line[:150])
    return mos, insts, cells, dcheck, api


def read_ports(path):
    """the S3C1 read-back: TERMINALS of both views, in the order the object graph reports them"""
    out = {}
    for raw in io.open(path, encoding='utf-8', errors='replace'):
        line = raw.rstrip('\n')
        if not line.startswith('S3C1-TERM '):
            continue
        f = parse_fields(line)
        cell = unq(f.get('cell'))
        view = unq(f.get('view'))
        if not cell:
            m = re.match(r'S3C1-TERM\s+"?([\w]+)"?\s*:\s*"?([\w]+)"?', line)
            if not m:
                continue
            cell, view = m.group(1), m.group(2)
        out.setdefault((cell, view), []).append((unq(f.get('name')), unq(f.get('dir'))))
    return out


def norm_pairs(text):
    """the golden spells a binding `pin=net'; a pair is a binding either way"""
    return sorted(x.strip('"') for x in (text or '').replace('(', ' ').replace(')', ' ')
                  .split() if '=' in x)


def oa_bindings(text):
    """the read-back prints bindings=(("pin" "net") ...): quoted pairs, positionally pin then net"""
    toks = re.findall(r'"([^"]*)"', text or '')
    return sorted('%s=%s' % (toks[i], toks[i + 1]) for i in range(0, len(toks) - 1, 2))


def main():
    op = optparse.OptionParser()
    op.add_option('--log')
    op.add_option('--ports')
    op.add_option('--golden-dir')
    op.add_option('--out')
    op.add_option('--rows')
    o, _ = op.parse_args()
    root = os.environ.get('PROJ', PROJ)
    gdir = o.golden_dir or os.path.join(root, 'results', 'evidence')
    rb = os.path.join(root, 'cadence_work', 'data_d6_oa', 'readback')
    log = o.log or os.path.join(rb, 'oa_readback.log')
    ports_log = o.ports or os.path.join(rb, 'oa_readback_terms.log')
    out = o.out or os.path.join(gdir, 'dd1_d6_oa_readback.csv')
    rows_csv = o.rows or os.path.join(gdir, 'dd1_d6_oa_verify.csv')
    for p, what in ((log, 'device read-back'), (ports_log, 'terminal read-back')):
        if not os.path.isfile(p):
            print('D6_OA_VERIFY: NO_READBACK_LOG (%s) %s' % (what, p))
            return 3

    R = S2.Run([], [], 'D6-OA-%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    masters = G.masters()
    table = G.dir_table(masters)
    devs_g, subs_g = G.golden_rows(masters, table)
    mos, insts, cells, dcheck, api = read_log(log)
    ports = read_ports(ports_log)
    subs_oa = dict(((unq(i.get('cell')), unq(i.get('inst'))), i) for i in insts
                   if master_lib(i.get('master')) == LIB)
    print('D6_OA_INPUT log=%s ports=%s MOS_rows=%d inst_rows=%d (of which %d inside %s) '
          'term_rows=%d cells=%d'
          % (os.path.basename(log), os.path.basename(ports_log), len(mos), len(insts),
             len(subs_oa), LIB, sum(len(v) for v in ports.values()), len(cells)))

    # ---- 1. device count, matched on (cell, instance) and not on a count alone
    got = dict(((unq(m.get('cell')), unq(m.get('inst'))), m) for m in mos)
    want = dict(((d['cell'], d['inst']), d) for d in devs_g)
    only_oa = sorted(set(got) - set(want))
    only_g = sorted(set(want) - set(got))
    ok_count = len(got) == len(want) == D6.TOTAL_DEVS and not only_oa and not only_g
    R.add('D6_OA_DEVICE_COUNT', 'all', '%d devices read back' % len(got),
          'the golden expands to %d and the read-back names exactly the same set' % len(want),
          'oa=%d golden=%d extra=%s missing=%s'
          % (len(got), len(want), ','.join('%s.%s' % c for c in only_oa) or 'none',
             ','.join('%s.%s' % c for c in only_g) or 'none'), 0,
          'PASS' if ok_count else 'FAIL',
          'a short read-back fixes the devices it knows and hides the rest, so the sets are compared')

    # ---- 2. geometry: the CDF-parsed number against the master's own value
    bad_geom, sample = [], []
    for key, g in sorted(want.items()):
        m = got.get(key)
        if not m:
            continue
        l = parse_len(m.get('num_l', m.get('cdf_l', '')))
        w = parse_len(m.get('num_w', m.get('cdf_w', '')))
        model = unq(m.get('model'))
        if (l is None or w is None or abs(l - float(g['l_m'])) > 1e-12
                or abs(w - float(g['w_m'])) > 1e-12 or model != g['model']):
            bad_geom.append('%s.%s oa=%s/%s/%s golden=%s/%s/%s'
                            % (key[0], key[1], model or '?', m.get('num_l'), m.get('num_w'),
                               g['model'], g['l_m'], g['w_m']))
        else:
            sample.append('%s.%s l=%s w=%s raw_l=%s raw_w=%s simW=%s'
                          % (key[0], key[1], m.get('num_l'), m.get('num_w'), m.get('raw_l'),
                             m.get('raw_w'), m.get('raw_simW')))
    R.add('D6_OA_GEOMETRY', 'all', '%d of %d device geometries agree'
          % (len(got) - len(bad_geom), len(want)),
          'model equal, and CDF-parsed l and w equal to the master value within 1e-12 m',
          'mismatches=%d | %s' % (len(bad_geom), ' ; '.join(bad_geom[:2])
                                  or (sample[:1] and sample[0] or 'none read back')), 0,
          'PASS' if not bad_geom and sample else 'FAIL',
          'raw property and simW are shipped in the CSV and were never written by this round')

    # ---- 3a. device terminals by name, against the net names the master body itself attaches
    bad_net = []
    checked = 0
    for key, g in sorted(want.items()):
        m = got.get(key)
        if not m:
            continue
        body = [i for i in masters[key[0]]['items'] if i[1] == key[1]]
        if not body:
            bad_net.append('%s.%s is not in the master body' % key)
            continue
        nets = body[0][2]
        for idx, t in enumerate(TERMINALS):
            oa = (m.get(t, '') or '').strip('"')
            exp = nets[idx] if idx < len(nets) else ''
            checked += 1
            if oa.upper() != exp.upper():
                bad_net.append('%s.%s.%s oa=%s master=%s' % (key[0], key[1], t, oa or 'none', exp))
    R.add('D6_OA_CONNECTIVITY', 'devices', '%d of %d device terminals agree'
          % (checked - len(bad_net), checked),
          'each of D/G/S/B read by terminal NAME and compared to the net the master attaches',
          'mismatches=%d | %s' % (len(bad_net), ' ; '.join(bad_net[:2]) or 'none'), 0,
          'PASS' if not bad_net and checked == 4 * len(want) else 'FAIL',
          'this PDK reports terminals in a different order per device family, so position is '
          'never trusted')

    # ---- 3b. sub-instance bindings: the seven X statements that make the hierarchy
    bad_bind = []
    for s in subs_g:
        row = subs_oa.get((s['cell'], s['inst']))
        if row is None:
            bad_bind.append('%s.%s missing from the read-back' % (s['cell'], s['inst']))
        elif oa_bindings(row.get('bindings')) != norm_pairs(s['bindings']):
            bad_bind.append('%s.%s oa=[%s] golden=[%s]' % (s['cell'], s['inst'],
                                                           (row.get('bindings') or '')[:44],
                                                           s['bindings'][:44]))
    R.add('D6_OA_CONNECTIVITY', 'instances', '%d of %d sub-instance bindings agree'
          % (len(subs_g) - len(bad_bind), len(subs_g)),
          'every X instance whose master is inside %s pins the nets the declaring subckt states' % LIB,
          'oa_subinst=%d golden=%d mismatches=%d | %s'
          % (len(subs_oa), len(subs_g), len(bad_bind), ' ; '.join(bad_bind[:2]) or 'none'), 0,
          'PASS' if not bad_bind and len(subs_oa) == len(subs_g) else 'FAIL',
          'seven bindings: Xff Xmask Xinv in the control cell, Xctrl Xsink in the unit, '
          'Xbias Xunit in the top; the schematic pin objects that belong to the basic library are '
          'listed by the read-back but are not child cells, so they are not counted here')

    # ---- 4. ports: names + directions against the netlist, and ONE order shared by both views
    seen = sum(1 for c in G.CELL_ORDER
               if ports.get((c, 'schematic')) or ports.get((c, 'symbol')))
    # the reused read-back also dumps one PDK reference cell (p33:symbol) to evidence the terminal
    # ORDER difference per device family. Its rows are deliberately excluded from every comparison
    # above, so counting them together with the delivered terminals made an aggregate that a reviewer
    # could not reconcile with 46 ports x 2 views -- delivered and reference are counted apart now.
    delivered = dict((k, v) for k, v in ports.items() if k[0] in G.CELL_ORDER)
    reference = sorted(set(k[0] for k in ports if k[0] not in G.CELL_ORDER))
    n_delivered = sum(len(v) for v in delivered.values())
    n_reference = sum(len(v) for k, v in ports.items() if k[0] not in G.CELL_ORDER)
    bad_port = []
    view_order = []
    seq_kept = []
    for cell in G.CELL_ORDER:
        exp = [(p, table[cell][p]) for p in masters[cell]['ports']]
        sch = ports.get((cell, 'schematic'), [])
        sym = ports.get((cell, 'symbol'), [])
        if sorted(sch) != sorted(exp):
            bad_port.append('%s schematic terminals %s != %s' % (cell, sch, exp))
        if sorted(sym) != sorted(exp):
            bad_port.append('%s symbol terminals %s != %s' % (cell, sym, exp))
        if sch and sym and sch != sym:
            view_order.append('%s schematic=%s symbol=%s' % (cell, [n for n, _d in sch],
                                                             [n for n, _d in sym]))
        if [n for n, _d in sch] == [p for p, _d in exp]:
            seq_kept.append(cell)
    verdict = 'NOT_AVAILABLE' if not seen else ('PASS' if not bad_port and not view_order
                                                else 'FAIL')
    R.add('D6_OA_PORTS', 'all', '%d of %d cells report terminals, %d delivered terminal objects'
          % (seen, len(G.CELL_ORDER), n_delivered),
          'both views carry exactly the declared port names with the declared directions, and the '
          'schematic and the symbol agree on the ORDER',
          'expected %d = 46 ports x 2 views, read %d ; reference-cell rows %d from %s ; '
          'name/direction mismatches=%d | view-order diffs=%d | %d of %d cells happen to keep the '
          'netlist textual order | %s'
          % (2 * sum(len(masters[cell]['ports']) for cell in G.CELL_ORDER), n_delivered,
             n_reference, ', '.join(reference) or 'none', len(bad_port), len(view_order),
             len(seq_kept), len(G.CELL_ORDER),
             ' ; '.join(bad_port[:1] + view_order[:1])[:80] or 'none'), 0, verdict,
          'the terminal SEQUENCE a netlist spells is a naming matter; what is claimed here is that '
          'no port is missing, wrongly directed, or ordered differently between the two views. The '
          "IL's own PDK reference dump is counted apart and compared to nothing")

    # ---- 5. library and model identity
    models = set(unq(m.get('model')) for m in mos)
    bad_model = sorted(models - set(D6.EXPECT_MIX))
    outside = sorted(set(master_lib(i.get('master')) for i in insts
                         if master_lib(i.get('master')) != LIB))
    R.add('D6_OA_LIBRARY', 'all', '%d distinct device models, %d in-library instances'
          % (len(models), len(subs_oa)),
          'every model is one of the four this task owns and the delivered hierarchy closes inside '
          '%s' % LIB,
          'models=%s | masters outside this lib=%s'
          % (' '.join(sorted(models)), ' '.join(outside) or 'none'), 0,
          'PASS' if mos and not bad_model and len(subs_oa) == len(subs_g) else 'FAIL',
          'the PDK is referenced, never written; basic/iopin are schematic pin objects, not child '
          'cells. n33_dnw_4t_ckt must stay the isolated DNW master')

    R.add('D6_OA_CHECKS', 'all', '%d cells reported dbCheck' % len(dcheck),
          'the OA object-graph check is reported as dbCheck; the Schematic Editor package (schCheck) '
          'is undefined in this batch build and is never claimed',
          'dbCheck=%s | api %s' % (' '.join('%s=%s' % (d.get('cell'), d.get('result'))
                                             for d in dcheck)[:60] or 'none',
                                   (api or [''])[0][:80]), 0,
          'MEASURED' if dcheck else 'NOT_AVAILABLE',
          'the editor\'s Check and Save could not be run in a headless batch session, and this '
          'round does not pretend otherwise')

    fails = [r for r in R.rows if r[7] == 'FAIL']
    S2.write_rows(out, [[m.get('cell'), m.get('inst'), m.get('master'), m.get('model'),
                         m.get('raw_l'), m.get('raw_w'), m.get('cdf_l'), m.get('cdf_w'),
                         m.get('num_l'), m.get('num_w'), m.get('raw_m'), m.get('raw_fingers'),
                         m.get('raw_simW'), m.get('terminals'), m.get('D'), m.get('G'), m.get('S'),
                         m.get('B')] for m in mos],
                  ['cell', 'inst', 'master', 'model', 'raw_l', 'raw_w', 'cdf_l', 'cdf_w', 'num_l',
                   'num_w', 'raw_m', 'raw_fingers', 'raw_simW', 'terminals', 'D', 'G', 'S', 'B'])
    S2.write_rows(rows_csv, R.rows, ROWS_HDR)
    for r in R.rows:
        print('  %-20s %-12s %s' % (r[1], r[2], r[7]))
    print('D6_OA_GRAPH_EQUIVALENCE: %s rows=%d failures=%d csv=%s'
          % ('PASS' if not fails else 'FAIL', len(R.rows), len(fails), rows_csv))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
