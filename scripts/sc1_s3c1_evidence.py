#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C1: turn the OA readback logs into the sc1_s3c1_* evidence tables.

Inputs (all produced by SKILL files this task ran against the real database):
  geom  -- skill/sc1_s3c1_geom_dump.il  : every shape, instance and terminal of all 16 views
  conn  -- skill/sc1_s3c1_conn_check.il : the net each instance terminal carries IN THE PARENT
                                          VIEW, plus schCheck's real error/warning counts
  ports -- skill/sc1_s3c1_readback.il   : the corrected read-only readback (cellView.terminals for
                                          both view types), taken after the direction write

What it answers, with numbers rather than adjectives:
  1. SYMBOL_GRAPHICS -- does each Symbol have a body, real pin rectangles, connector stubs and
     name labels, and on which side of the body does each pin centre sit?
  2. CONNECTIVITY     -- for every sub-instance pin, is there a wire figure of that same parent
     net whose bounding box covers the pin's connection point?  Net names are per view, which is
     why the child's net name must not be used here (measured: the top schematic carries the bank's
     bgate pin on the net named gate33).
  3. PORT_DIRECTIONS  -- the schematic and symbol terminals read back from the database against the
     48 golden declarations, not a relabelled CSV.

Mirror instances (transform MY) are flipped about the instance origin, so their absolute pin x is
origin - symbol x; assuming R0 for them was what made three pins look unattached at first.

usage: python scripts/sc1_s3c1_evidence.py <geom.log> <conn.log> <ports.log> --csv-out DIR
"""
from __future__ import print_function
import io
import os
import re
import sys

RE_V = re.compile(r'^S9\|V\|"([^"]+)"\|"([^"]+)"\|([tn])\|(\d+)\|(\d+)\|(\d+)$')
RE_S = re.compile(r'^S9\|S\|"([^"]+)"\|"([^"]+)"\|(\d+)\|"([^"]+)"\|"([^"]+)"\|"([^"]*)"'
                  r'(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|"([^"]*)"\|"([^"]*)"'
                  r'\|"([^"]*)"(\S+) (\S+)\|"([^"]*)"$')
RE_I = re.compile(r'^S9\|I\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"(-?[\d.]+) (-?[\d.]+)'
                  r'\|\(\((-?[\d.]+) (-?[\d.]+)\) "([^"]*)" ([\d.]+)\)\|"([^"]*)"'
                  r'\|(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|(\d+)$')
RE_T = re.compile(r'^S9\|T\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|(\d+)\|(.*)$')
RE_FIG = re.compile(r'^([^/@]*)/([^/@]*)/([^/@]*)@(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)$')
RE_K = re.compile(r'^S10\|K\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"$')
RE_C_OK = re.compile(r'^S10\|C\|"([^"]+)"\|"([^"]+)"\|schCheck=\(\((\d+) (\d+)\)\)$')
RE_C_NIL = re.compile(r'^S10\|C\|"([^"]+)"\|"([^"]+)"\|schCheck=nil$')
# the corrected reader prints:  S3C1-TERM "cell":"view" name="d" dir="input" net="d" objType="term"
RE_RT = re.compile(r'^S3C1-TERM "([^"]+)":"([^"]+)" name="([^"]+)" dir="([^"]+)" net="([^"]+)"')

SUPPLY_NAMES = ('vdd', 'vdd18', 'vdd33', 'vscan')
TOL = 1e-6


def clean(tok):
    if tok is None:
        return 'NONE'
    return tok.strip().strip('"')


def fnum(tok):
    tok = clean(tok)
    if tok in ('NONE', 'nil'):
        return None
    return float(tok)


def records(path, tag):
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            i = raw.find(tag)
            if i < 0:
                continue
            yield raw[i:].strip()


def parse_geom(path):
    shapes, insts, terms, views, bad = [], [], [], {}, []
    for line in records(path, 'S9|'):
        if line.startswith('S9|V|'):
            m = RE_V.match(line)
            if m:
                views[(m.group(1), m.group(2))] = dict(opened=m.group(3) == 't',
                                                       shapes=int(m.group(4)),
                                                       insts=int(m.group(5)),
                                                       terms=int(m.group(6)))
            else:
                bad.append(line[:140])
        elif line.startswith('S9|S|'):
            m = RE_S.match(line)
            if m:
                shapes.append(dict(cell=m.group(1), view=m.group(2), idx=int(m.group(3)),
                                   obj=clean(m.group(4)), layer=clean(m.group(5)),
                                   purpose=clean(m.group(6)),
                                   bbox=tuple(float(m.group(k)) for k in range(7, 11)),
                                   objname=clean(m.group(11)), net=clean(m.group(12)),
                                   just=clean(m.group(13)),
                                   xy=(fnum(m.group(14)), fnum(m.group(15))),
                                   text=clean(m.group(16))))
            else:
                bad.append(line[:140])
        elif line.startswith('S9|I|'):
            m = RE_I.match(line)
            if m:
                insts.append(dict(cell=m.group(1), view=m.group(2), cellname=m.group(3),
                                  name=m.group(4), xy=(float(m.group(5)), float(m.group(6))),
                                  rot=m.group(9), scale=float(m.group(10)),
                                  bbox=tuple(float(m.group(k)) for k in range(12, 16)),
                                  nterms=int(m.group(16))))
            else:
                bad.append(line[:140])
        elif line.startswith('S9|T|'):
            m = RE_T.match(line)
            if m:
                figs = []
                for chunk in m.group(7).split('|'):
                    fm = RE_FIG.match(chunk)
                    if fm:
                        figs.append(dict(layer=clean(fm.group(1)), purpose=clean(fm.group(2)),
                                         obj=clean(fm.group(3)),
                                         bbox=tuple(float(fm.group(k)) for k in range(4, 8))))
                    elif chunk.strip():
                        bad.append('fig chunk ' + chunk[:100])
                terms.append(dict(cell=m.group(1), view=m.group(2), name=m.group(3),
                                  direction=m.group(4), net=m.group(5), npins=int(m.group(6)),
                                  figs=figs))
            else:
                bad.append(line[:140])
    return shapes, insts, terms, views, bad


def parse_conn(path):
    instnet, checks, bad = {}, [], []
    for line in records(path, 'S10|'):
        m = RE_K.match(line)
        if m:
            instnet[(m.group(1), m.group(2), m.group(3))] = m.group(4)
            continue
        m = RE_C_OK.match(line)
        if m:
            checks.append(dict(cell=m.group(1), view=m.group(2), errors=int(m.group(3)),
                               warnings=int(m.group(4)), available='yes'))
            continue
        m = RE_C_NIL.match(line)
        if m:
            checks.append(dict(cell=m.group(1), view=m.group(2), errors=-1, warnings=-1,
                               available='no_schCheck_returns_nil_for_this_view_type'))
            continue
        bad.append(line[:140])
    return instnet, checks, bad


def parse_ports(path, cells):
    """only this task's eight cells: the readback also prints the PDK p33 reference symbol, whose
    terminals are not part of the 48 declared ports"""
    rows, bad = [], []
    for line in records(path, 'S3C1-TERM '):
        m = RE_RT.match(line)
        if m:
            if m.group(1) in cells:
                rows.append(dict(cell=m.group(1), view=m.group(2), term=m.group(3),
                                 direction=m.group(4), net=m.group(5)))
        else:
            bad.append(line[:140])
    return rows, bad


def center(bbox):
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def role_of(name, direction):
    low = name.lower()
    if low == 'vss':
        return 'vss_bottom'
    if low in SUPPLY_NAMES:
        return 'supply_top'
    if direction == 'output':
        return 'output_right'
    if direction == 'input':
        return 'input_left'
    return 'other'


def side_of(pinc, body):
    bx1, by1, bx2, by2 = body
    cx, cy = pinc
    tags = []
    if cx > bx2 + TOL:
        tags.append('right')
    if cx < bx1 - TOL:
        tags.append('left')
    if cy > by2 + TOL:
        tags.append('top')
    if cy < by1 - TOL:
        tags.append('bottom')
    return '+'.join(tags) if tags else 'inside'


def write_rows(path, header, rows):
    with io.open(path, 'wb') as fh:
        fh.write((header + u'\n').encode('utf-8'))
        for r in rows:
            fh.write((u','.join(r) + u'\n').encode('utf-8'))


def main():
    geom_p, conn_p, ports_p = sys.argv[1], sys.argv[2], sys.argv[3]
    outdir = sys.argv[sys.argv.index('--csv-out') + 1]
    shapes, insts, terms, views, bad1 = parse_geom(geom_p)
    instnet, checks, bad2 = parse_conn(conn_p)
    ports, bad3 = parse_ports(ports_p, set(k for (k, v) in views if v == 'schematic'))
    print('S3C1_GEOM views=%d shapes=%d insts=%d terms=%d'
          % (len(views), len(shapes), len(insts), len(terms)))
    print('S3C1_PARSE_FAILURES geom=%d conn=%d ports=%d' % (len(bad1), len(bad2), len(bad3)))
    for b in (bad1 + bad2 + bad3)[:8]:
        print('  BAD %s' % b)
    print('S3C1_VIEWS_OPENED %d of %d' % (sum(1 for v in views.values() if v['opened']),
                                          len(views)))
    print('S3C1_INST_NET_ROWS %d  S3C1_CHECK_ROWS %d' % (len(instnet), len(checks)))

    bodies, graphics, side_rows = {}, [], []
    for (cell, view) in sorted(views):
        if view != 'symbol':
            continue
        sf = [g for g in shapes if g['cell'] == cell and g['view'] == view]
        body = None
        for g in sf:
            if g['obj'] == 'rect' and g['layer'] == 'device' and g['purpose'] == 'drawing':
                wh = (g['bbox'][2] - g['bbox'][0]) * (g['bbox'][3] - g['bbox'][1])
                if body is None or wh > body[0]:
                    body = (wh, g['bbox'])
        bodies[cell] = body[1] if body else None
        nrect = sum(1 for g in sf if g['layer'] == 'pin' and g['purpose'] == 'drawing')
        nlab = sum(1 for g in sf if g['layer'] == 'pin' and g['purpose'] == 'label')
        nstub = sum(1 for g in sf if g['layer'] == 'device' and g['purpose'] == 'drawing'
                    and g['obj'] == 'line')
        nterm = len([t for t in terms if t['cell'] == cell and t['view'] == view])
        complete = 'yes' if (body and nrect == nterm == nlab == nstub) else 'no'
        graphics.append([cell, str(len(sf)), 'yes' if body else 'no', str(nrect), str(nstub),
                         str(nlab), str(nterm), complete])
        print('S3C1_SYM %-24s shapes=%-3s body=%-4s pinrects=%-3s stubs=%-3s labels=%-3s terms=%-3s'
              % (cell, len(sf), 'YES' if body else 'NO', nrect, nstub, nlab, nterm))

    for t in sorted(terms, key=lambda x: (x['cell'], x['name'])):
        if t['view'] != 'symbol':
            continue
        body = bodies.get(t['cell'])
        tips = [f for f in t['figs'] if f['purpose'] == 'drawing']
        side, tip = 'NO_TIP_FIG', 'NONE'
        if tips:
            tip = ' '.join('%.4f' % v for v in tips[0]['bbox'])
            if body:
                side = side_of(center(tips[0]['bbox']), body)
        role = role_of(t['name'], t['direction'])
        want = {'input_left': 'left', 'output_right': 'right', 'supply_top': 'top',
                'vss_bottom': 'bottom'}.get(role, 'any')
        ok = 'yes' if (want == 'any' or side == want) else 'no'
        side_rows.append([t['cell'], t['name'], t['direction'], t['net'], role, want, side, ok,
                          tip, str(len(t['figs']))])
    print('S3C1_SIDE_MATCHED %d of %d' % (sum(1 for r in side_rows if r[7] == 'yes'),
                                          len(side_rows)))

    attach = []
    for inst in sorted(insts, key=lambda x: (x['cell'], x['name'])):
        if inst['view'] != 'schematic':
            continue
        if (inst['cellname'], 'symbol') not in views:
            continue
        body = bodies.get(inst['cellname'])
        if not body:
            continue
        wires = [g for g in shapes if g['cell'] == inst['cell'] and g['view'] == 'schematic'
                 and g['net'] != 'NONE' and g['purpose'] == 'drawing'
                 and g['obj'] in ('line', 'ellipse', 'rect', 'path')]
        ox, oy = inst['xy']
        mirrored = inst['rot'].startswith('MY') or inst['rot'].startswith('MX')
        flip_y = inst['rot'].startswith('MX') or inst['rot'] == 'MYSN90'
        bcx, bcy = center(body)
        for t in [x for x in terms if x['cell'] == inst['cellname'] and x['view'] == 'symbol']:
            tips = [f for f in t['figs'] if f['purpose'] == 'drawing']
            if not tips:
                continue
            net = instnet.get((inst['cell'], inst['name'], t['name']), 'NONE')
            ax, ay = center(tips[0]['bbox'])
            ax, ay = ax - bcx, ay - bcy
            if mirrored:
                ax = -ax
            if flip_y:
                ay = -ay
            ax, ay = ox + ax, oy + ay
            hit = 'NONE'
            for w in wires:
                if net != 'NONE' and w['net'] != net:
                    continue
                b = w['bbox']
                inside = (b[0] - TOL <= ax <= b[2] + TOL) and (b[1] - TOL <= ay <= b[3] + TOL)
                corner = ((abs(b[0] - ax) < TOL or abs(b[2] - ax) < TOL)
                          and (abs(b[1] - ay) < TOL or abs(b[3] - ay) < TOL))
                if inside or corner:
                    hit = str(w['idx'])
                    break
            attach.append([inst['cell'], inst['name'], inst['cellname'], inst['rot'], t['name'],
                           net, '%.4f %.4f' % (ax, ay), hit, 'yes' if hit != 'NONE' else 'no'])
    print('S3C1_ATTACH rows=%d attached=%d not_attached=%d'
          % (len(attach), sum(1 for a in attach if a[8] == 'yes'),
             sum(1 for a in attach if a[8] == 'no')))
    for a in attach:
        if a[8] == 'no':
            print('  NOT-ATTACHED %s/%s (%s %s) term=%s net=%s tip=%s'
                  % (a[0], a[1], a[2], a[3], a[4], a[5], a[7]))

    golden_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                            'results', 'evidence', 'sc1_s3c_golden_ports.csv')
    golden = {}
    with io.open(golden_p, encoding='utf-8') as fh:
        fh.readline()
        for ln in fh:
            f = ln.rstrip('\n').split(',')
            # cell,ordinal,port,declared_direction,role,master_port_order
            if len(f) >= 4:
                golden[(clean(f[0]), clean(f[2]))] = clean(f[3])
    port_rows, mism = [], 0
    for r in sorted(ports, key=lambda x: (x['cell'], x['view'], x['term'])):
        want = golden.get((r['cell'], r['term']), 'NOT_IN_GOLDEN')
        ok = 'yes' if want == r['direction'] else 'no'
        if ok == 'no':
            mism += 1
            print('  DIRECTION-MISMATCH %s:%s %s got=%s want=%s'
                  % (r['cell'], r['view'], r['term'], r['direction'], want))
        port_rows.append([r['cell'], r['view'], r['term'], r['direction'], r['net'], want, ok])
    print('S3C1_PORT_ROWS %d schematic=%d symbol=%d MISMATCH %d'
          % (len(port_rows), sum(1 for r in port_rows if r[1] == 'schematic'),
             sum(1 for r in port_rows if r[1] == 'symbol'), mism))

    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    write_rows(os.path.join(outdir, 'sc1_s3c1_graphics.csv'),
               u'cell,shapes,body_rect,pin_rects,connector_stubs,pin_labels,terminals,'
               u'complete_set', graphics)
    write_rows(os.path.join(outdir, 'sc1_s3c1_symbol_side.csv'),
               u'cell,term,direction,net,role,expected_side,measured_side,matches_side,'
               u'tip_bbox,n_pin_figs', side_rows)
    write_rows(os.path.join(outdir, 'sc1_s3c1_connectivity.csv'),
               u'parent,instance,sub_cell,transform,term,parent_net,tip_abs,wire_shape_idx,'
               u'wire_reaches_pin', attach)
    write_rows(os.path.join(outdir, 'sc1_s3c1_ports.csv'),
               u'cell,view,term,direction,net,golden_direction,matches_golden', port_rows)
    write_rows(os.path.join(outdir, 'sc1_s3c1_editor_check.csv'),
               u'cell,view,check_available,errors,warnings',
               [[c['cell'], c['view'], c['available'], str(c['errors']), str(c['warnings'])]
                for c in checks])
    print('S3C1_EVIDENCE wrote 5 tables into %s' % outdir)


main()
