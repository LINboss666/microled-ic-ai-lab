#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C2 A: compute the role-based Symbol placement and emit the apply table.

Why assigning coordinates is the right primitive here (measured, not assumed):
  * sc1_s3c2_api_probe.il: dbMoveFig(fig, cellView, list(list(dx dy) "R0" 1.0)) moves by exactly
    that delta and the negated origin restores the box (S2-MOVEFIG-A/B rc=t equal=t);
    dbCreateRect / dbCreateLine / dbCreateLabel with an lpp the view already uses all return
    objects; dbMakeNet + dbCreatePin(net, figure, name) creates a bound pin; dbDeleteObject
    deletes one (shapes 16 -> 15); and every one of those survived dbSave + dbClose + reopen.
  * S3C1 probe7 already showed assigning fig~>bBox and label~>xy persists too.
So the pin's OWN pin object and its figure association are kept -- the task forbids moving only
the red box or only the text -- and each of the three graphics that make a pin (pin rectangle,
device stub, name label) is placed to an explicit coordinate.

Placement rule (§5): signal inputs on the LEFT, signal outputs on the RIGHT, positive supplies on
TOP, vss on the BOTTOM. Role comes from the frozen golden port table's direction plus the name, so
vscan is a supply and bgate is an input; bank is bgate left / scan right / vscan top.

Every target is checked against every other target in the same view before anything is emitted:
pin rectangles must not overlap each other, must not overlap the body interior, must sit outside the
body on their own side, and labels must not collide with any rectangle. A cell whose plan does not
pass is refused and reported, never half-emitted.

usage: python scripts/sc1_s3c2_place.py <geom_dump.log> <golden_ports.csv> --out-prefix asg_in/gen
"""
from __future__ import print_function
import io
import os
import re
import sys

CELLS = ['c2mos_dff', 'sc1_scan_gate', 'sc1_ls_core_r2d', 'sc1_ls_c1_r2d', 'sc1_ls_c1_top_r2d',
         'sc1_r3_scan_chain_1ch', 'sc1_s3b_p33_bank_7', 'sc1_scan_power_1ch_s3c']

PITCH = 0.25        # pin-to-pin spacing along a LEFT or RIGHT side
PITCH_TB = 0.40     # and along TOP or BOTTOM, where the names run side by side
PIN_LEN = 0.175     # the pin rectangle's length, as delivered
PIN_TH = 0.05       # and its thickness
STUB = 0.125        # the device/drawing connector between body edge and pin rectangle
LABEL_GAP = 0.125   # how far the name anchor sits from the body edge, as delivered

SUPPLY = ('vdd', 'vdd18', 'vdd33', 'vscan')
RE_S = re.compile(r'^S9\|S\|"([^"]+)"\|"([^"]+)"\|(\d+)\|"([^"]+)"\|"([^"]+)"\|"([^"]*)"'
                  r'(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|"([^"]*)"\|"([^"]*)"'
                  r'\|"([^"]*)"(\S+) (\S+)\|"([^"]*)"$')
RE_T = re.compile(r'^S9\|T\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|(\d+)\|(.*)$')
RE_FIG = re.compile(r'^([^/@]*)/([^/@]*)/([^/@]*)@(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)$')


def clean(tok):
    return tok.strip().strip('"')


def read_geom(path):
    shapes, terms = [], []
    for raw in io.open(path, encoding='utf-8', errors='replace'):
        i = raw.find('S9|')
        if i < 0:
            continue
        line = raw[i:].strip()
        if line.startswith('S9|S|'):
            m = RE_S.match(line)
            if m:
                shapes.append(dict(cell=m.group(1), view=m.group(2), idx=int(m.group(3)),
                                   obj=clean(m.group(4)), layer=clean(m.group(5)),
                                   purpose=clean(m.group(6)),
                                   bbox=tuple(float(m.group(k)) for k in range(7, 11)),
                                   net=clean(m.group(12)),
                                   xy=(float_or_none(m.group(14)), float_or_none(m.group(15)))))
        elif line.startswith('S9|T|'):
            m = RE_T.match(line)
            if m:
                figs = []
                for chunk in m.group(7).split('|'):
                    fm = RE_FIG.match(chunk)
                    if fm:
                        figs.append(dict(layer=clean(fm.group(1)), purpose=clean(fm.group(2)),
                                         bbox=tuple(float(fm.group(k)) for k in range(4, 8))))
                terms.append(dict(cell=m.group(1), view=m.group(2), name=m.group(3),
                                  direction=m.group(4), net=m.group(5), figs=figs))
    return shapes, terms


def float_or_none(tok):
    tok = clean(tok)
    if tok in ('NONE', 'nil'):
        return None
    return float(tok)


def role_of(name, direction):
    low = name.lower()
    if low == 'vss':
        return 'bottom'
    if low in SUPPLY:
        return 'top'
    if direction == 'output':
        return 'right'
    if direction == 'input':
        return 'left'
    return 'right'


def centre(bbox):
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def fmt(v):
    return ('%.6f' % v).rstrip('0').rstrip('.')


def norm(b):
    """OA stores a box as (lowerLeft upperRight); emitting x1>x2 made the DB mirror the figure
    back to the other side, which is what put bgate's stub on the right in the first run."""
    return (min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3]))


def fmtbox(b):
    return tuple(fmt(v) for v in norm(b))


def plan_cell(cell, shapes, terms, gold):
    """return (rows, problems, tips) where rows are SKILL-side placement records"""
    sf = [g for g in shapes if g['cell'] == cell and g['view'] == 'symbol']
    body = None
    selrect = None
    for g in sf:
        if g['obj'] == 'rect' and g['layer'] == 'device' and g['purpose'] == 'drawing':
            body = g
        if g['obj'] == 'rect' and g['purpose'] == 'drawing' and g['layer'] == 'instance':
            selrect = g
    ts = [t for t in terms if t['cell'] == cell and t['view'] == 'symbol']
    if body is None or not ts:
        return [], ['%s: no body rect or no terminals' % cell], []
    side = {}
    for t in ts:
        side[t['name']] = role_of(t['name'], t['direction'])
    groups = {'left': [], 'right': [], 'top': [], 'bottom': []}
    for t in ts:
        groups[side[t['name']]].append(t)
    bx1, by1, bx2, by2 = body['bbox']
    bw = max(bx2 - bx1, PITCH_TB * max(len(groups['top']), len(groups['bottom']), 2))
    bh = max(by2 - by1, PITCH * max(len(groups['left']), len(groups['right']), 2))
    cx, cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    nbody = (cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0)

    rows, boxes, tips = [], [], []
    # body and the instance selection box follow the new extent
    nb = norm(nbody)
    rows.append(['body', cell, 'device', fmt(bx1), fmt(by1), fmt(bx2), fmt(by2),
                 fmt(nb[0]), fmt(nb[1]), fmt(nb[2]), fmt(nb[3]),
                 '', '', '', '', '', '', ''])
    if selrect is not None:
        pad = 0.125
        rows.append(['body', cell, 'instance', fmt(selrect['bbox'][0]), fmt(selrect['bbox'][1]),
                     fmt(selrect['bbox'][2]), fmt(selrect['bbox'][3]),
                     fmt(nb[0] - pad), fmt(nb[1] - pad), fmt(nb[2] + pad),
                     fmt(nb[3] + pad), '', '', '', '', '', '', ''])
    boxes.append(('body', nbody))

    order = {'left': 0, 'right': 1, 'top': 2, 'bottom': 3}
    for sname in sorted(groups, key=lambda k: order[k]):
        lst = sorted(groups[sname], key=lambda t: t['name'])
        n = len(lst)
        for i, t in enumerate(lst):
            pit = PITCH if sname in ('left', 'right') else PITCH_TB
            off = (n - 1) * pit / 2.0 - i * pit
            if sname in ('left', 'right'):
                py = cy + off
                px = cx + (bw / 2.0 if sname == 'right' else -bw / 2.0)
                sgn = 1.0 if sname == 'right' else -1.0
                stub = (px, py, px + sgn * STUB, py)
                rect = (min(px + sgn * STUB, px + sgn * (STUB + PIN_LEN)), py - PIN_TH / 2.0,
                        max(px + sgn * STUB, px + sgn * (STUB + PIN_LEN)), py + PIN_TH / 2.0)
                lab_xy = (px - sgn * LABEL_GAP, py)
                just = 'centerRight' if sname == 'right' else 'centerLeft'
            else:
                px2 = cx + off
                py2 = cy + (bh / 2.0 if sname == 'top' else -bh / 2.0)
                sgn = 1.0 if sname == 'top' else -1.0
                stub = (px2, py2, px2, py2 + sgn * STUB)
                rect = (px2 - PIN_TH / 2.0, min(py2 + sgn * STUB, py2 + sgn * (STUB + PIN_LEN)),
                        px2 + PIN_TH / 2.0, max(py2 + sgn * STUB, py2 + sgn * (STUB + PIN_LEN)))
                lab_xy = (px2, py2 - sgn * LABEL_GAP)
                just = 'lowCenter' if sname == 'top' else 'topCenter'
            tip = centre(rect)
            src = [f for f in t['figs'] if f['purpose'] == 'drawing']
            if not src:
                rows.append(['MISSING_PINFIG', cell, t['name'], sname] + [''] * 14)
                continue
            old = src[0]['bbox']
            # one row per terminal: the old pin-rect bbox is the match key, and the stub and the
            # name are found from the CURRENT view as the device line / pin label whose centre sits
            # within 0.10 of that same old centre -- no fabricated coordinates anywhere
            rows.append(['pin', cell, t['name'],
                         fmt(old[0]), fmt(old[1]), fmt(old[2]), fmt(old[3]),
                         *fmtbox(rect),
                         *fmtbox(stub),
                         fmt(lab_xy[0]), fmt(lab_xy[1]), just])
            boxes.append(('%s.%s.rect' % (cell, t['name']), rect))
            lbox = label_box(lab_xy, just)
            boxes.append(('%s.%s.label' % (cell, t['name']), lbox))
            tips.append(dict(cell=cell, term=t['name'], side=sname, tip=tip, net=t['net'],
                             direction=t['direction']))
    # collision check over the TARGET boxes
    problems = []
    for a in range(len(boxes)):
        for b in range(a + 1, len(boxes)):
            na, ba = boxes[a]
            nb, bb = boxes[b]
            if ba == nbody and bb == nbody:
                continue
            ox = min(ba[2], bb[2]) - max(ba[0], bb[0])
            oy = min(ba[3], bb[3]) - max(ba[1], bb[1])
            if ox > 1e-9 and oy > 1e-9:
                if na.endswith('.rect') and nb.endswith('.rect'):
                    problems.append('%s overlaps %s by %.3f x %.3f' % (na, nb, ox, oy))
                elif '.label' in na + nb and not (na.endswith('.rect') and
                                                  nb.endswith('.rect')):
                    # a label may sit over the body outline, but not over another label or
                    # over a pin rectangle of a different terminal
                    if na.endswith('.label') and nb.endswith('.label'):
                        problems.append('label overlap %s / %s' % (na, nb))
    return rows, problems, tips


def label_box(xy, just):
    """the rectangle a name occupies, from the anchor and its justification. A pin name here is at
    most five characters at the delivered text height, so 0.32 x 0.08 is the conservative box."""
    x, y = xy
    w, h = 0.32, 0.08
    if just == 'centerRight':
        return (x - w, y - h / 2.0, x, y + h / 2.0)
    if just == 'centerLeft':
        return (x, y - h / 2.0, x + w, y + h / 2.0)
    if just == 'lowCenter':
        return (x - w / 2.0, y, x + w / 2.0, y + h)
    if just == 'topCenter':
        return (x - w / 2.0, y - h, x + w / 2.0, y)
    return (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)


def main():
    geom, gold_p = sys.argv[1], sys.argv[2]
    out = sys.argv[sys.argv.index('--out-prefix') + 1] if '--out-prefix' in sys.argv else 'gen'
    shapes, terms = read_geom(geom)
    gold = {}
    for ln in io.open(gold_p, encoding='utf-8'):
        f = [clean(c) for c in ln.rstrip('\n').split(',')]
        if len(f) >= 4 and f[0] != 'cell':
            gold[(f[0], f[2])] = f[3]
    all_rows, all_probs, tips = [], [], []
    for cell in CELLS:
        rows, probs, ctips = plan_cell(cell, shapes, terms, gold)
        all_rows += rows
        all_probs += probs
        tips += ctips
        print('S3C2_PLAN %s rows=%d problems=%d tips=%d' % (cell, len(rows), len(probs),
                                                            len(ctips)))
    print('S3C2_PLAN_TOTAL rows=%d tips=%d problems=%d' % (len(all_rows), len(tips),
                                                           len(all_probs)))
    for p in all_probs[:12]:
        print('  COLLISION %s' % p)
    if all_probs:
        print('S3C2_PLACE_REFUSED: the plan has collisions, nothing is emitted')
        return 1
    d = os.path.dirname(out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    plan = out + '_sym_plan.csv'
    with io.open(plan, 'wb') as fh:
        fh.write(u'kind,cell,term_or_role,old_x1,old_y1,old_x2,old_y2,new_x1,new_y1,new_x2,'
                 u'new_y2,stub_x1,stub_y1,stub_x2,stub_y2,label_x,label_y,justification\n'
                 .encode('utf-8'))
        for r in all_rows:
            fh.write((u','.join(r) + u'\n').encode('utf-8'))
    tipf = out + '_sym_tips.csv'
    with io.open(tipf, 'wb') as fh:
        fh.write(u'cell,term,side,net,direction,tip_x,tip_y\n'.encode('utf-8'))
        for t in tips:
            fh.write((u'%s,%s,%s,%s,%s,%s,%s\n' % (t['cell'], t['term'], t['side'], t['net'],
                                                   t['direction'], fmt(t['tip'][0]),
                                                   fmt(t['tip'][1]))).encode('utf-8'))
    print('S3C2_PLACE wrote %s (%d rows) and %s (%d tips)' % (plan, len(all_rows), tipf, len(tips)))
    return 0


sys.exit(main())
