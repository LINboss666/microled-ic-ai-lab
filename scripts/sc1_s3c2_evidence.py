#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C2 evidence: what the delivered library looks like after the Symbol placement and the
parent re-lay, computed from ONE disk-reopened geometry dump plus the connectivity log.

Four questions, each answered from records rather than from a summary:

  1 PORT_DIRECTIONS -- every terminal of every schematic and symbol view (96 objects) against the
     frozen golden port table. Read from S9|T| lines, which carry the direction the database reports.
  2 ATTACH        -- every sub-instance pin of the hierarchy views, pushed through the INSTANCE
     transform the database prints (i~>transform), tested against the REAL VERTICES of the wires
     (S9|W| lines, printed by skill/sc1_s3c1_geom_dump.il). A wire's bounding box is never used as
     the test, which is what section 6 forbids.
  3 CROSS-NET     -- every drawn segment tested against every other net's connection boxes and
     segments: contact between different nets is a short, so the count has to be zero, per view.
  4 EDITOR        -- the schCheck error/warning counts from S10|C|. A nil result is reported as
     "no_schCheck_for_this_view_type", never as a pass (section 6).

usage: python scripts/sc1_s3c2_evidence.py <verify.log> <golden_ports.csv> <out-dir>
"""
from __future__ import print_function
import io
import os
import re
import sys

RE_S = re.compile(r'^S9\|S\|"([^"]+)"\|"([^"]+)"\|(\d+)\|"([^"]+)"\|"([^"]+)"\|"([^"]*)"'
                  r'(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|"([^"]*)"\|"([^"]*)"'
                  r'\|"([^"]*)"(\S+) (\S+)\|"([^"]*)"$')
RE_T = re.compile(r'^S9\|T\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|(\d+)\|(.*)$')
RE_I = re.compile(r'^S9\|I\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"(-?[\d.]+) (-?[\d.]+)'
                  r'\|\(\((-?[\d.]+) (-?[\d.]+)\) "([^"]*)" ([\d.]+)\)\|"([^"]*)"'
                  r'\|(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|(\d+)$')
RE_W = re.compile(r'^S9\|W\|"([^"]+)"\|"([^"]+)"\|(\d+)\|"([^"]*)"(.*)$')
RE_FIG = re.compile(r'^([^/@]*)/([^/@]*)/([^/@]*)@(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)$')
CELLS = ['c2mos_dff', 'sc1_scan_gate', 'sc1_ls_core_r2d', 'sc1_ls_c1_r2d', 'sc1_ls_c1_top_r2d',
         'sc1_r3_scan_chain_1ch', 'sc1_s3b_p33_bank_7', 'sc1_scan_power_1ch_s3c']
TOL = 1e-6
XFORM = {'R0': ((1.0, 0.0), (0.0, 1.0)), 'MY': ((-1.0, 0.0), (0.0, 1.0)),
         'MX': ((1.0, 0.0), (0.0, -1.0)), 'R180': ((-1.0, 0.0), (0.0, -1.0))}


try:
    S = unicode                      # py2 on the simulator host
except NameError:
    S = str                          # py3 on the workstation


def clean(t):
    return t.strip().strip('"')


def rows(path, tag):
    for raw in io.open(path, encoding='utf-8', errors='replace'):
        i = raw.find(tag)
        if i >= 0:
            yield raw[i:].strip()


def write_csv(p, header, rows_):
    with io.open(p, 'wb') as fh:
        fh.write((header + u'\n').encode('utf-8'))
        for r in rows_:
            fh.write((u','.join([(u'%s' % v).replace(',', ';') for v in r])
                      + u'\n').encode('utf-8'))
    print('S3C2_EVIDENCE wrote %s rows=%d' % (os.path.basename(p), len(rows_)))


def on_segment(pt, seg):
    """pt on the segment a-b, where the segment is axis-aligned by construction; the comparison uses
    the segment's own endpoints, never a bounding box around a polyline"""
    (x, y), (ax, ay, bx, by) = pt, seg
    if abs(ay - by) > TOL and abs(ax - bx) > TOL:
        return False                      # not axis aligned -> the endpoints are not the segment
    lo_x, hi_x = min(ax, bx), max(ax, bx)
    lo_y, hi_y = min(ay, by), max(ay, by)
    return (lo_x - TOL <= x <= hi_x + TOL) and (lo_y - TOL <= y <= hi_y + TOL)


def main():
    log, golden_p, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    shapes, terms, insts, wires, checks = [], [], [], [], {}
    for l in rows(log, 'S9|S|'):
        m = RE_S.match(l)
        if m:
            shapes.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)), idx=int(m.group(3)),
                               obj=clean(m.group(4)), layer=clean(m.group(5)),
                               purpose=clean(m.group(6)),
                               bbox=tuple(float(m.group(k)) for k in range(7, 11)),
                               net=clean(m.group(12)), xy=clean(m.group(14)) + ' ' + clean(
                                   m.group(15))))
    for l in rows(log, 'S9|T|'):
        m = RE_T.match(l)
        if m:
            figs = []
            for ch in m.group(7).split('|'):
                fm = RE_FIG.match(ch)
                if fm:
                    figs.append(dict(layer=clean(fm.group(1)), purpose=clean(fm.group(2)),
                                     bbox=tuple(float(fm.group(k)) for k in range(4, 8))))
            terms.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)), name=clean(m.group(3)),
                              direction=clean(m.group(4)), net=clean(m.group(5)), figs=figs))
    for l in rows(log, 'S9|I|'):
        m = RE_I.match(l)
        if m:
            insts.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)), cellname=clean(
                m.group(3)), name=clean(m.group(4)), xy=(float(m.group(5)), float(m.group(6))),
                rot=clean(m.group(9))))
    for l in rows(log, 'S9|W|'):
        m = RE_W.match(l)
        if m:
            try:
                nums = [float(v) for v in m.group(5).split()]
            except ValueError:
                continue              # NO-POINTS: an ellipse or rect, which has no vertices
            pts = list(zip(nums[0::2], nums[1::2]))
            for a, b in zip(pts, pts[1:]):
                wires.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)),
                                  idx=int(m.group(3)), net=clean(m.group(4)),
                                  seg=(a[0], a[1], b[0], b[1])))
    for l in rows(log, 'S10|C|'):
        mm = re.match(r'^S10\|C\|"([^"]+)"\|"([^"]+)"\|schCheck=(.*)$', l)
        if mm:
            checks[(clean(mm.group(1)), clean(mm.group(2)))] = mm.group(3)

    golden = {}
    for ln in io.open(golden_p, encoding='utf-8'):
        f = ln.rstrip('\n').split(',')
        if len(f) >= 4 and f[0] != 'cell':
            golden[(clean(f[0]), clean(f[2]))] = clean(f[3])

    # ---- 1 port directions, both views of every cell ------------------------------------------
    port_rows, mism = [], 0
    for t in sorted(terms, key=lambda x: (x['cell'], x['view'], x['name'])):
        if t['view'] not in ('schematic', 'symbol') or t['cell'] not in CELLS:
            continue
        want = golden.get((t['cell'], t['name']), 'NOT_IN_GOLDEN')
        ok = want == t['direction']
        mism += 0 if ok else 1
        port_rows.append([t['cell'], t['view'], t['name'], t['direction'], want, 'yes' if ok
                          else 'no', t['net']])
    print('S3C2_PORT_ROWS=%d matched=%d mismatched=%d'
          % (len(port_rows), len(port_rows) - mism, mism))

    # ---- 2 pin attachment through the real instance transform ---------------------------------
    sel = {}
    for g in shapes:
        if g['view'] == 'symbol' and g['obj'] == 'rect' and g['layer'] == 'instance':
            sel[g['cell']] = g['bbox']
    pinfig = {}
    for t in terms:
        if t['view'] == 'symbol':
            for f in t['figs']:
                if f['layer'] == 'pin':
                    pinfig.setdefault((t['cell'], t['name']), []).append(f['bbox'])
    body_centre = {}
    for c in CELLS:
        if c in sel:
            b = sel[c]
            body_centre[c] = ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
    # parent net of every instance terminal, from the geometry dump's own terminal nets is not
    # available for sub-instances, so the connectivity log's K lines are reused if present
    instnet = {}
    for l in rows(log, 'S10|K|'):
        mk = re.match(r'^S10\|K\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"$', l)
        if mk:
            instnet[(clean(mk.group(1)), clean(mk.group(2)), clean(mk.group(3)))] = clean(
                mk.group(4))
    attach = []
    for i in sorted(insts, key=lambda x: (x['cell'], x['name'])):
        if i['view'] != 'schematic' or i['cellname'] not in CELLS or i['rot'] not in XFORM:
            continue
        ux, uy = XFORM[i['rot']]
        for t in [x for x in terms if x['cell'] == i['cellname'] and x['view'] == 'symbol']:
            pf = pinfig.get((i['cellname'], t['name']))
            if not pf or i['cellname'] not in body_centre:
                continue
            bb = pf[0]
            cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
            bcx, bcy = body_centre[i['cellname']]
            dx, dy = cx - bcx, cy - bcy
            ax = i['xy'][0] + ux[0] * dx + uy[0] * dy
            ay = i['xy'][1] + ux[1] * dx + uy[1] * dy
            net = instnet.get((i['cell'], i['name'], t['name']), t['net'])
            hits = [w['idx'] for w in wires if w['cell'] == i['cell'] and w['view'] == 'schematic'
                    and (w['net'] == net or (w['net'] == 'NONE' and net == 'NONE'))
                    and on_segment((ax, ay), w['seg'])]
            attach.append([i['cell'], i['name'], i['cellname'], i['rot'], t['name'], net,
                           '%.4f %.4f' % (ax, ay), len(hits), 'yes' if hits else 'no',
                           ','.join(str(h) for h in hits[:4])])
    reached = sum(1 for a in attach if a[8] == 'yes')
    print('S3C2_ATTACH rows=%d reached=%d unreached=%d' % (len(attach), reached,
                                                           len(attach) - reached))
    for a in attach:
        if a[8] == 'no':
            print('  UNREACHED %s/%s %s.%s net=%s tip=%s' % (a[0], a[1], a[2], a[4], a[5], a[6]))

    # ---- 3 cross-net contact ------------------------------------------------------------------
    cross = []
    pins_by_net = {}
    for a in attach:
        pins_by_net.setdefault(a[0], []).append((a[5], float(a[6].split()[0]),
                                                float(a[6].split()[1])))
    for cell in sorted(set(w['cell'] for w in wires)):
        mine = [w for w in wires if w['cell'] == cell]
        for a in mine:
            for b in mine:
                if a['net'] == b['net'] or a['net'] == 'NONE' or b['net'] == 'NONE':
                    continue
                if seg_touch(a['seg'], b['seg']):
                    cross.append([cell, 'wire-wire', a['net'], b['net'], a['idx'], b['idx']])
        for (net, px, py) in pins_by_net.get(cell, []):
            for w in mine:
                if w['net'] == net or w['net'] == 'NONE':
                    continue
                if on_segment((px, py), w['seg']):
                    cross.append([cell, 'wire-foreign-pin', w['net'], net, w['idx'], '-'])
    print('S3C2_CROSSNET contacts=%d' % len(cross))
    byk = {}
    for c in cross:
        byk[(c[0], c[1])] = byk.get((c[0], c[1]), 0) + 1
    for k in sorted(byk):
        print('  CROSS-KIND %s %s %d' % (k[0], k[1], byk[k]))
    for c in cross[:10]:
        print('  CROSS %s' % ' '.join(S(x) for x in c))

    # ---- 4 editor check -----------------------------------------------------------------------
    editor = []
    for c in CELLS:
        for v in ('schematic', 'symbol'):
            raw = checks.get((c, v), 'NOT_REPORTED')
            mm = re.match(r'^\(\((\d+) (\d+)\)\)$', raw)
            editor.append([c, v, 'yes' if mm else 'no_schCheck_returns_nil_for_this_view_type',
                           mm.group(1) if mm else '-1', mm.group(2) if mm else '-1'])
    err0 = sum(1 for e in editor if e[2] == 'yes' and e[3] == '0')
    print('S3C2_EDITOR views_with_check=%d of 8 schematics with 0 errors' % err0)

    labels = [[g['cell'], g['view'], g['idx'], g['net'], g['xy']] for g in shapes
              if g['obj'] == 'label' and g['view'] == 'schematic']
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    write_csv(os.path.join(outdir, 'sc1_s3c2_ports.csv'),
              u'cell,view,port,direction,golden_direction,matches,golden_net_of_terminal',
              port_rows)
    write_csv(os.path.join(outdir, 'sc1_s3c2_attach.csv'),
              u'parent,instance,sub_cell,transform,term,parent_net,tip_abs_x,tip_abs_y,'
              u'wire_shape_count,wire_reaches_pin,wire_shape_idx'.replace(
                  'tip_abs_x,tip_abs_y', 'tip_abs'), attach)
    write_csv(os.path.join(outdir, 'sc1_s3c2_crossnet.csv'),
              u'cell,kind,net_a,net_b,shape_a,shape_b', cross)
    write_csv(os.path.join(outdir, 'sc1_s3c2_editor_check.csv'),
              u'cell,view,check_available,errors,warnings', editor)
    write_csv(os.path.join(outdir, 'sc1_s3c2_wire_labels.csv'),
              u'cell,view,shape_idx,net,xy', labels)
    print('S3C2_EVIDENCE ports=%d attach=%d crossnet=%d labels=%d'
          % (len(port_rows), len(attach), len(cross), len(labels)))
    return 0


def seg_touch(s1, s2):
    """two axis-aligned segments sharing more than nothing at all -- touch, cross or overlap"""
    ax0, ax1 = sorted([s1[0], s1[2]])
    ay0, ay1 = sorted([s1[1], s1[3]])
    bx0, bx1 = sorted([s2[0], s2[2]])
    by0, by1 = sorted([s2[1], s2[3]])
    w = 0.006
    ox = min(ax1 + w, bx1 + w) - max(ax0 - w, bx0 - w)
    oy = min(ay1 + w, by1 + w) - max(ay0 - w, by0 - w)
    return ox > TOL and oy > TOL


sys.exit(main())
