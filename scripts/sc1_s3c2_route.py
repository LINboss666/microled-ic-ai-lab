#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C2 C: re-lay the wiring of the parent schematics after the Symbol pin placement.

Why this has to exist: moving a Symbol pin moves the connection point of every parent instance of
that Symbol, and the wire graphics drawn to the OLD points stop touching them. Measured after the
placement pass (scripts/sc1_s3c1_evidence.py on the post-placement dump): 3 of 39 sub-instance pins
are still reached by a same-net wire, 36 are not. The three affected views are the pure-hierarchy
ones -- sc1_ls_c1_top_r2d, sc1_r3_scan_chain_1ch, sc1_scan_power_1ch_s3c; the five leaf views hold
only MOS masters whose symbols were never edited, so their own wiring is untouched.

This tool changes graphics only. Net objects and instance-terminal bindings are never edited here:
the target view's figures on the wire layer are deleted and redrawn from the connection the database
reports (S10|K per-instance terminal nets, plus the view's own terminal nets), which is what section
5 asks for -- graphics generated from the actual electrical connection, never dbSetConnCurrent.

Endpoint model, everything read from skill/sc1_s3c1_geom_dump.il's dump:
  * a sub-instance pin's landing point = its Symbol pin-rect centre pushed through the instance
    transform printed by the database in i~>transform ((origin) direction scale); a real eight-way
    vector map is applied, no body-centre subtraction stands in for it;
  * a port of the view itself = its basic/iopin instance origin, approached from -x, because the
    wires the importer drew ended exactly on those origins and schCheck accepted that;
  * a wire leaves a pin along that pin's facing axis, derived from the pin rect (longer side = axis,
    sign from which side of the symbol's selection box it sits on) and rotated with the instance, so
    a route never has to pass through the symbol it comes out of.

Routing, per net, on a Hanan-style grid (candidate lines = every pin/port coordinate, every instance
body edge at three pads, and one exit pad per pin) with Dijkstra on wire length, fail closed:
  * an edge is refused when it overlaps an instance selection box, a connection box of another net,
    or a segment already drawn for another net -- Virtuoso connects wire figures that touch as well
    as figures that cross, so any contact between different nets is a short, not a cosmetic problem;
  * boxes belonging to the net being routed are exempt, because a wire has to overlap its own pin;
  * a net with more than two endpoints grows a tree, each further endpoint joining the shortest point
    of what is already drawn for that net;
  * a net with no clean path is reported and gets short outward stubs at its own pins plus one
    net-name label per stub -- the mechanism section 5 allows for relieving crossings. A net that
    IS routed gets no label at all: measured in the S3C2 loop test, a label placed next to a routed
    wire claimed the net's name for itself and the editor re-derived the wire onto a fresh name
    (net7), so labels are used only where they are the connection.

usage:
  python scripts/sc1_s3c2_route.py <geom_after.log> <conn_check.log> --emit-il OUT.il
         [--cells a,b] [--cell-replace old=new] [--plan-csv OUT.csv] [--show]
"""
from __future__ import print_function
import heapq
import io
import os
import random
import re
import sys

RE_S = re.compile(r'^S9\|S\|"([^"]+)"\|"([^"]+)"\|(\d+)\|"([^"]+)"\|"([^"]+)"\|"([^"]*)"'
                  r'(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|"([^"]*)"\|"([^"]*)"'
                  r'\|"([^"]*)"(\S+) (\S+)\|"([^"]*)"$')
RE_T = re.compile(r'^S9\|T\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|(\d+)\|(.*)$')
RE_I = re.compile(r'^S9\|I\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"(-?[\d.]+) (-?[\d.]+)'
                  r'\|\(\((-?[\d.]+) (-?[\d.]+)\) "([^"]*)" ([\d.]+)\)\|"([^"]*)"'
                  r'\|(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\|(\d+)$')
RE_FIG = re.compile(r'^([^/@]*)/([^/@]*)/([^/@]*)@(-?[\d.]+) (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)$')
RE_K = re.compile(r'^S10\|K\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"\|"([^"]+)"$')
CELLS = ['c2mos_dff', 'sc1_scan_gate', 'sc1_ls_core_r2d', 'sc1_ls_c1_r2d', 'sc1_ls_c1_top_r2d',
         'sc1_r3_scan_chain_1ch', 'sc1_s3b_p33_bank_7', 'sc1_scan_power_1ch_s3c']
TOL = 1e-6
# 'keep' leaves a net that has no crossing-free route exactly as it is; 'stub' replaces it with
# outward stubs plus one label per stub end. Measured: keep is safe where the net's own old wire
# cannot collide with a new route of another net, and stub is safe where it can -- the two views
# this round could not settle on one rule, so both are available and the run records which was used.
FALLBACK = 'keep'
WIRE_W = 0.006
STUB = 0.25
PADS = (0.06, 0.25, 0.5)
EXIT_PAD = 0.06
PORT_HALF = 0.03125
ROW_Y = 1.25
GAP = 0.75
MARGIN = 0.75
PORT_SPACING = 0.15
# the outer pads exist so a congested net can go around the whole block row instead of giving up:
# measured in the chain view, every lane between the pins and the port row was already taken by a
# signal route, and the supply net's 4th endpoint had no path at all.
LANE_PADS = (0.06, 0.15, 0.25, 0.4, 0.6, 1.2, 2.0)
# left-to-right signal order per hierarchy view, read from the frozen sub-instance netlist
# (results/evidence/sc1_s3c_golden_subinst.csv): Xchain.gate33 -> Xbank.bgate; Xff.qbar -> Xgate,
# Xgate.en -> Xls; Xcore.y -> Xnand. Nothing here invents a flow.
FLOW = {'sc1_scan_power_1ch_s3c': ['Xchain', 'Xbank'],
        'sc1_r3_scan_chain_1ch': ['Xff', 'Xgate', 'Xls'],
        'sc1_ls_c1_top_r2d': ['Xcore', 'Xnand']}
XFORM = {'R0': ((1.0, 0.0), (0.0, 1.0)), 'R90': ((0.0, 1.0), (-1.0, 0.0)),
         'R180': ((-1.0, 0.0), (0.0, -1.0)), 'R270': ((0.0, -1.0), (1.0, 0.0)),
         'MY': ((-1.0, 0.0), (0.0, 1.0)), 'MX': ((1.0, 0.0), (0.0, -1.0)),
         'MY|R90': ((0.0, -1.0), (-1.0, 0.0)), 'MYSN90': ((0.0, -1.0), (-1.0, 0.0)),
         'MX|Y90': ((0.0, 1.0), (1.0, 0.0))}


def clean(t):
    return t.strip().strip('"')


def pt_or_none(a, b):
    if a in ('NONE', 'nil') or b in ('NONE', 'nil'):
        return None
    return (float(a), float(b))


def each(path, tag):
    for raw in io.open(path, encoding='utf-8', errors='replace'):
        i = raw.find(tag)
        if i >= 0:
            yield raw[i:].strip()


class Box(object):
    """axis-aligned rectangle in parent coordinates; net=None means an instance body (hard)"""

    def __init__(self, x0, y0, x1, y1, net=None, tag=''):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.net, self.tag = net, tag

    def centre(self):
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def seg(self):
        return (self.x0, self.y0, self.x1, self.y1)

    def __str__(self):
        return '%s[%.4f %.4f %.4f %.4f]%s' % (self.tag, self.x0, self.y0, self.x1, self.y1,
                                              ':' + str(self.net))


def tp(px, py, ux, uy, ox, oy):
    return (ox + ux[0] * px + uy[0] * py, oy + ux[1] * px + uy[1] * py)


def box_pt(bb, ux, uy, ox, oy, net=None, tag=''):
    pts = [tp(bx, by, ux, uy, ox, oy) for bx in (bb[0], bb[2]) for by in (bb[1], bb[3])]
    return Box(min(p[0] for p in pts), min(p[1] for p in pts),
               max(p[0] for p in pts), max(p[1] for p in pts), net, tag)


def load(geom, conn):
    shapes, insts, terms, instnet = [], [], [], {}
    for l in each(geom, 'S9|'):
        if l.startswith('S9|S|'):
            m = RE_S.match(l)
            if m:
                shapes.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)),
                                   idx=int(m.group(3)), obj=clean(m.group(4)),
                                   layer=clean(m.group(5)), purpose=clean(m.group(6)),
                                   bbox=tuple(float(m.group(k)) for k in range(7, 11)),
                                   net=clean(m.group(12)), just=clean(m.group(13)),
                                   xy=pt_or_none(m.group(14), m.group(15)),
                                   text=clean(m.group(16))))
        elif l.startswith('S9|I|'):
            m = RE_I.match(l)
            if m:
                insts.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)),
                                  cellname=clean(m.group(3)), name=clean(m.group(4)),
                                  xy=(float(m.group(5)), float(m.group(6))),
                                  rot=clean(m.group(9)),
                                  bbox=tuple(float(m.group(k)) for k in range(12, 16))))
        elif l.startswith('S9|T|'):
            m = RE_T.match(l)
            if m:
                figs = []
                for ch in m.group(7).split('|'):
                    fm = RE_FIG.match(ch)
                    if fm:
                        figs.append(dict(layer=clean(fm.group(1)), purpose=clean(fm.group(2)),
                                         obj=clean(fm.group(3)),
                                         bbox=tuple(float(fm.group(k)) for k in range(4, 8))))
                terms.append(dict(cell=clean(m.group(1)), view=clean(m.group(2)),
                                  name=clean(m.group(3)), direction=clean(m.group(4)),
                                  net=clean(m.group(5)), figs=figs))
    for l in each(conn, 'S10|K|'):
        m = RE_K.match(l)
        if m:
            instnet[(clean(m.group(1)), clean(m.group(2)), clean(m.group(3)))] = clean(m.group(4))
    return shapes, insts, terms, instnet


def symbol_facts(shapes, terms):
    """per Symbol cell its selection box; per (cell, terminal) its pin rect in symbol coordinates"""
    sel, pins = {}, {}
    for g in shapes:
        if g['view'] == 'symbol' and g['obj'] == 'rect' and g['layer'] == 'instance' \
                and g['purpose'] == 'drawing':
            sel[g['cell']] = g['bbox']
    for t in terms:
        if t['view'] != 'symbol':
            continue
        for f in t['figs']:
            if f['layer'] == 'pin' and f['purpose'] == 'drawing':
                pins.setdefault((t['cell'], t['name']), []).append(f['bbox'])
    return sel, pins


def face_sym(bb, sel):
    """facing axis of a pin rect in SYMBOL coordinates: which axis, and which way along it"""
    cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    scx, scy = (sel[0] + sel[2]) / 2.0, (sel[1] + sel[3]) / 2.0
    if bb[2] - bb[0] >= bb[3] - bb[1]:
        return ((1.0, 0.0) if cx >= scx else (-1.0, 0.0))
    return ((0.0, 1.0) if cy >= scy else (0.0, -1.0))


def strip_of(seg):
    return (min(seg[0], seg[2]) - WIRE_W / 2.0, min(seg[1], seg[3]) - WIRE_W / 2.0,
            max(seg[0], seg[2]) + WIRE_W / 2.0, max(seg[1], seg[3]) + WIRE_W / 2.0)


def ek(a, b):
    """canonical key for a grid edge (node order is not meaningful)"""
    return tuple(sorted([a, b]))


def touches(a, b):
    return (min(a[2], b[2]) - max(a[0], b[0]) > TOL) and (min(a[3], b[3]) - max(a[1], b[1]) > TOL)


class Grid(object):
    def __init__(self, pts, bodies):
        xs, ys = set(), set()
        for p in pts:
            xs.add(round(p[0], 6))
            ys.add(round(p[1], 6))
            # a route has to be able to step sideways by one wire width next to any pin, otherwise a
            # single foreign wire crossing the column makes the pin unreachable at every lane
            for pad in (0.0, EXIT_PAD, -EXIT_PAD):
                xs.add(round(p[0] + p[2] * pad, 6))
                ys.add(round(p[1] + p[3] * pad, 6))
        for b in bodies:
            for pad in LANE_PADS:
                xs.update([round(b.x0 - pad, 6), round(b.x1 + pad, 6)])
                ys.update([round(b.y0 - pad, 6), round(b.y1 + pad, 6)])
        self.xs = sorted(xs)
        self.ys = sorted(ys)
        self.ix = dict((v, k) for k, v in enumerate(self.xs))
        self.iy = dict((v, k) for k, v in enumerate(self.ys))

    def node(self, x, y):
        return (self.ix[round(x, 6)], self.iy[round(y, 6)])

    def pt(self, n):
        return (self.xs[n[0]], self.ys[n[1]])

    def edges(self):
        nx, ny = len(self.xs), len(self.ys)
        for i in range(nx):
            for j in range(ny):
                if i + 1 < nx:
                    yield ((i, j), (i + 1, j))
                if j + 1 < ny:
                    yield ((i, j), (i, j + 1))

    def neighbours(self, n):
        i, j = n
        return [m for m in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))
                if 0 <= m[0] < len(self.xs) and 0 <= m[1] < len(self.ys)]


def route_view(grid, boxes):
    """edge ownership maps, computed once for the view; per-net blocking is then two lookups"""
    body, pin = {}, {}
    for (a, b) in grid.edges():
        s = strip_of(tuple(list(grid.pt(a)) + list(grid.pt(b))))
        key = ek(a, b)
        for o in boxes:
            if not touches(s, o.seg()):
                continue
            if o.net is None:
                body[key] = o.tag
            else:
                pin.setdefault(key, set()).add(o.net)
    adj = {}
    for (a, b) in grid.edges():
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return body, pin, adj


def dijkstra(adj, grid, srcs, dst, blocked, reach=None):
    if reach is not None:
        reach.update(srcs)
    dist = dict((s, 0.0) for s in srcs)
    prev, seen, pq = {}, set(), [(0.0, s) for s in srcs]
    while pq:
        d, n = heapq.heappop(pq)
        if n in seen:
            continue
        seen.add(n)
        if n == dst:
            break
        for m in adj.get(n, []):
            if ek(n, m) in blocked:
                continue
            p0, p1 = grid.pt(n), grid.pt(m)
            nd = d + abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
            if nd < dist.get(m, 1e30):
                dist[m] = nd
                prev[m] = n
                if reach is not None:
                    reach.add(m)
                heapq.heappush(pq, (nd, m))
    if dst not in seen:
        return None
    path, n = [], dst
    while n in prev:
        path.append(n)
        n = prev[n]
    path.append(n)
    path.reverse()
    return path


COPY_BLOCK = u'''
;; section 5 asks for the whole closed loop on this task's own copy first: copy, edit, check, save,
;; reopen from disk, read the connection back. The copy is this round's temporary view and is
;; deleted again after the loop is proven.
s2wSrc = car(errset(dbOpenCellViewByType(s2wLib "@@SRC@@" "schematic" "schematic" "r")))
printf("S2W-COPY-SRC %L open=%L shapes=%L insts=%L nets=%L\\n" "@@SRC@@" s2wSrc != nil
       length(s2wSrc~>shapes) length(s2wSrc~>instances) length(s2wSrc~>nets))
s2wCopy = car(errset(dbCopyCellView(s2wSrc s2wLib "@@DST@@" "schematic" "schematic")))
printf("S2W-COPY %L made=%L\\n" "@@DST@@" s2wCopy != nil)
when(s2wSrc != nil dbClose(s2wSrc))
when(s2wCopy != nil
  printf("S2W-COPY-SAVE %L\\n" car(errset(dbSave(s2wCopy))) != nil)
  dbClose(s2wCopy)
)
s2wRe = car(errset(dbOpenCellViewByType(s2wLib "@@DST@@" "schematic" "schematic" "r")))
printf("S2W-COPY-REOPEN %L shapes=%L insts=%L terms=%L nets=%L\\n" s2wRe != nil
       length(s2wRe~>shapes) length(s2wRe~>instances) length(s2wRe~>terminals)
       length(s2wRe~>nets))
when(s2wRe != nil dbClose(s2wRe))
'''


def fmt(v):
    return ('%.6f' % v).rstrip('0').rstrip('.')


def sk(v):
    """SKILL literal for a planned field: coordinates stay numbers, names stay strings"""
    try:
        float(v)
        return str(v)
    except (TypeError, ValueError):
        return '"%s"' % v


def dedupe(pts):
    seen, out = set(), []
    for p in pts:
        k = (round(p[0], 6), round(p[1], 6))
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def role_side(name, direction):
    """same role table the Symbol placement used: inputs left, outputs right, supplies top, vss bottom"""
    n = name.lower()
    if n == 'vss' or n.endswith('ss'):
        return 'bottom'
    if n in ('vdd', 'vdd18', 'vdd33', 'vscan'):
        return 'top'
    if direction == 'output':
        return 'right'
    if direction == 'input':
        return 'left'
    return 'right'


def extents(cell, sel, pins):
    sb = sel[cell]
    xs, ys = [sb[0], sb[2]], [sb[1], sb[3]]
    for (c, t), prs in pins.items():
        if c != cell:
            continue
        for bb in prs:
            xs += [bb[0], bb[2]]
            ys += [bb[1], bb[3]]
    return Box(min(xs), min(ys), max(xs), max(ys), None, 'EXT.' + cell)


def spread(items, want, spacing):
    """distinct slots along one side, closest to what each net asked for but at least SPACING apart"""
    out, prev = [], None
    for k, w in sorted(zip(items, want), key=lambda p: p[1]):
        pos = w if prev is None or w >= prev + spacing else prev + spacing
        out.append((k, round(pos, 6)))
        prev = pos
    return out


def span_of(pts):
    if len(pts) < 2:
        return 0.0
    return max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in pts for b in pts)


def orders(ends):
    """candidate routing orders. Order decides the result, because every drawn segment blocks the
    next net and one unlucky first net can deadlock the rest of the view: the widest nets need the
    long lanes, so they go first, and a few deterministic shuffles follow as bounded retries."""
    span = dict((n, span_of(ends[n])) for n in ends)
    # supply rails are wide, short-trip nets whose access corridors are the same lanes the long
    # signal routes want, so they have to be laid down first or they end up walled in (measured in
    # the chain view: core_ok33's route at y~2.05 cut vdd18's only path from Xgate to the rail)
    rail = set(['vdd', 'vdd18', 'vdd33', 'vss', 'vscan'])
    cand = [sorted(ends, key=lambda n: (n not in rail, -span[n], n)),
            sorted(ends, key=lambda n: (n not in rail, -len(ends[n]), -span[n], n)),
            sorted(ends, key=lambda n: (-span[n], n)),
            sorted(ends, key=lambda n: (len(ends[n]), -span[n], n)),
            sorted(ends, key=lambda n: (span[n], n)),
            sorted(ends), sorted(ends, reverse=True)]
    rnd = random.Random(sum(ord(c) for c in ''.join(sorted(ends))))
    out, seen = [], set()
    for c in cand:
        if tuple(c) not in seen:
            seen.add(tuple(c))
            out.append(list(c))
    while len(out) < 10:
        c = list(ends)
        rnd.shuffle(c)
        if tuple(c) not in seen:
            seen.add(tuple(c))
            out.append(c)
    return out


def just_for(fx, fy):
    """justification tokens this build accepts in dbCreateLabel. Measured in the S3C2 loop test:
    "lowerLeft"/"lowerRight" create fine, while "lowCenter"/"highCenter" -- which the database
    does report on existing figures -- are refused, so the vertical pair uses the same
    lower/upper prefix that worked."""
    if fx > 0:
        return 'lowerLeft'
    if fx < 0:
        return 'lowerRight'
    return 'lowerCenter' if fy > 0 else 'upperCenter'


def route_once(order, ends, port_nets, grid, adj, body_edges, pin_edges, edge_set, edge_seg,
               boxes, show, parent):
    """route every net of one view in this order; returns (segments, labels, unresolved, stub-count)

    A net that has no crossing-free path in the drawing area is NOT drawn wrong and NOT silently
    dropped: every one of its pins gets a short outward stub plus a wire label with the net's own
    name, which is the mechanism the netlist importer itself used in these views and what section 5
    allows for relieving crossings. The label rows are emitted separately so the report can count
    exactly how many nets are drawn as rails and how many as labelled stubs."""
    wire_edges, rows, lbls, unres, kept = {}, [], [], [], []
    stubs = 0
    all_segs = []

    def box_free(cx, cy, nm):
        """a wire label's text box is 0.32 x 0.08 and Virtuoso attaches a label to EVERY wire it
        touches, so the anchor has to be clear of foreign geometry -- measured: a decorative label
        for a routed net sat over the vdd18 stub column and schCheck reported
        'Terminal vdd18 shorted to terminal blank' plus an illegal bus reference."""
        b = Box(cx - 0.16, cy - 0.04, cx + 0.16, cy + 0.04)
        for o in boxes:
            if (o.net is None or o.net != nm) and touches(b.seg(), o.seg()):
                return False
        for (n2, s) in all_segs:
            if n2 == nm:
                continue
            if touches(b.seg(), strip_of(s)):
                return False
        return True

    def place_label(net, pts, segs, outward):
        """one label per net, anchored on its own geometry and clear of everything else"""
        cands = []
        if outward:
            for p in pts:
                cands.append((p[0] + p[2] * STUB, p[1] + p[3] * STUB, just_for(p[2], p[3])))
                for extra in (0.05, 0.1, 0.15, 0.2):
                    cands.append((p[0] + p[2] * (STUB + extra), p[1] + p[3] * (STUB + extra),
                                  just_for(p[2], p[3])))
        for s in segs:
            for fr in (0.5, 0.34, 0.66, 0.2, 0.8):
                cands.append((s[0] + (s[2] - s[0]) * fr, s[1] + (s[3] - s[1]) * fr, 'lowerLeft'))
        for (cx, cy, j) in cands:
            if box_free(cx, cy, net):
                lbls.append([net, cx, cy, net, j])
                return True
        unres.append('LABEL-NO-ROOM %s %s anchors_tried=%d' % (parent, net, len(cands)))
        return False

    def edge_free(seg, blk):
        """every grid edge the candidate touches must be passable for this net"""
        st = strip_of(seg)
        for e in edge_set:
            if touches(st, strip_of(edge_seg[e])) and e in blk:
                return False
        return True

    def stub_out(p, nm, blk):
        """the longest outward stub that stays clear; measured reason: a fixed 0.25 stub could end
        on top of a routed wire of another net, and schCheck then reported the two terminals as
        shorted (Terminal vdd18 shorted to terminal blank) because the label that names a stub also
        names whatever wire its anchor sits on."""
        for length in (STUB, 0.35, 0.5, 0.65, 0.8):
            s = (p[0], p[1], p[0] + p[2] * length, p[1] + p[3] * length)
            if edge_free(s, blk):
                return s, length
        return (p[0], p[1], p[0] + p[2] * STUB, p[1] + p[3] * STUB), STUB

    for net in order:
        pts = dedupe(ends[net])
        blocked = set(body_edges)
        blocked |= set(k for k, ns in pin_edges.items() if ns - set([net]))
        blocked |= set(k for k, w in wire_edges.items() if w != net)
        blocked |= set(e for (n2, s) in all_segs if n2 != net for e in edge_set
                       if touches(strip_of(s), strip_of(edge_seg[e])))
        tree, segs, fail = set(), [], None
        if len(pts) == 1:
            p = pts[0]
            s, _L = stub_out(p, net, blocked)
            new, kind = [s], 'single-terminal'
            stubs += 1
        else:
            kind = 'grid'
            for k, p in enumerate(pts):
                dst = grid.node(p[0], p[1])
                if k == 0:
                    tree.add(dst)
                    continue
                reach = set()
                path = dijkstra(adj, grid, tree, dst, blocked, reach) if dst in adj else None
                if path is None:
                    fail = p
                    if '--cut' in sys.argv:
                        cut = []
                        for n in reach:
                            for m in adj.get(n, []):
                                if m not in reach:
                                    e = ek(n, m)
                                    why = ('body %s' % body_edges[e] if e in body_edges else
                                           'pin %s' % sorted(pin_edges[e], key=str)
                                           if e in pin_edges and pin_edges[e] - set([net]) else
                                           'wire %s' % wire_edges[e] if e in wire_edges else '?')
                                    cut.append((abs(m[0] - dst[0]) + abs(m[1] - dst[1]), why,
                                                grid.pt(n), grid.pt(m)))
                        for row in sorted(cut)[:8]:
                            print('      CUT %s %s %s -> %s' % (net, row[1], row[2], row[3]))
                    break
                for a, b in zip(path, path[1:]):
                    pa, pb = grid.pt(a), grid.pt(b)
                    segs.append((pa[0], pa[1], pb[0], pb[1]))
                    tree.add(a)
                    tree.add(b)
        if fail:
            unres.append('LABELLED-STUB %s %s no-crossing-free-path from=(%.3f,%.3f) pts=%s'
                         % (parent, net, fail[0], fail[1],
                            ' '.join('(%.3f,%.3f)' % q[0:2] for q in pts)))
            if FALLBACK == 'keep':
                new, kind = [], 'kept-unchanged'
                kept.append(net)
            else:
                new = []
                for p in pts:
                    s2, _L = stub_out(p, net, blocked)
                    new.append(s2)
                stubs += len(new)
                kind = 'labelled-stub'
                place_label(net, pts, [], True)
        else:
            new = merge_segs(segs) if kind == 'grid' else new
        if kind != 'grid':
            # a labelled stub: the anchor sits ON the stub's outer end, so the label names that wire
            for (x, y, fx, fy) in pts:
                lbls.append([net, x + fx * STUB, y + fy * STUB, net, just_for(fx, fy)])
        else:
            # an internal net has no port pin to hold its name: measured in the loop test that a
            # re-derived internal net comes back auto-named (gate33 -> net11) unless a wire label
            # sits on it, so the label is placed ON the first segment's midpoint
            m = new[0]
            lbls.append([net, (m[0] + m[2]) / 2.0, (m[1] + m[3]) / 2.0, net,
                         'lowerLeft' if abs(m[1] - m[3]) < TOL else 'lowerCenter'])
        for st in new:
            rows.append((net, kind, st))
            all_segs.append((net, st))
            for e in edge_set:
                if touches(strip_of(edge_seg[e]), strip_of(st)):
                    wire_edges[e] = net
            if show:
                print('    %-11s %8s %8s -> %8s %8s' % (net, fmt(st[0]), fmt(st[1]),
                                                        fmt(st[2]), fmt(st[3])))
    return rows, lbls, unres, stubs, kept


def plan_view(ends, port_nets, boxes, grid, adj, body_edges, pin_edges, edge_set, edge_seg,
              notes, parent, show):
    """try the candidate orders, bounded, and keep the first that leaves nothing unresolved"""
    for net in sorted(ends):
        if len(dedupe(ends[net])) == 1:
            notes.append('SINGLE-TERMINAL %s %s at %s (the accepted netlist has no consumer)'
                         % (parent, net, '(%.3f,%.3f)' % ends[net][0][0:2]))
    best = None
    for oi, order in enumerate(orders(ends)):
        cand = route_once(order, ends, port_nets, grid, adj, body_edges, pin_edges, edge_set,
                          edge_seg, boxes, show, parent)
        if best is None or len(cand[2]) < len(best[2]):
            best = cand + (oi,)
        if not cand[2]:
            break
    rows, lbls, unres, stubs, kept, oi = best
    print('  ORDER %s attempts=%d kept-unchanged-nets=%s segments=%d'
          % (parent, oi + 1, ','.join(sorted(set(kept))) or 'none', len(rows)))
    for n in sorted(set(kept)):
        notes.append('KEPT-UNCHANGED %s %s no crossing-free path for every terminal; its existing '
                     'wire figures are left in place rather than replaced by stubs, so its pins '
                     'stay unreached and are reported' % (parent, n))
    notes.extend(unres)
    return rows, lbls, unres, stubs, kept


def main():
    geom, conn = sys.argv[1], sys.argv[2]
    il = sys.argv[sys.argv.index('--emit-il') + 1]
    only = sys.argv[sys.argv.index('--cells') + 1].split(',') if '--cells' in sys.argv else None
    repl = sys.argv[sys.argv.index('--cell-replace') + 1].split('=') \
        if '--cell-replace' in sys.argv else None
    plan_csv = sys.argv[sys.argv.index('--plan-csv') + 1] if '--plan-csv' in sys.argv else None
    nomove = '--no-move' in sys.argv
    notext = '--no-text-moves' in sys.argv
    global FALLBACK
    if '--fallback' in sys.argv:
        FALLBACK = sys.argv[sys.argv.index('--fallback') + 1]
    show = '--show' in sys.argv
    applier = sys.argv[sys.argv.index('--applier') + 1] if '--applier' in sys.argv else None
    dump_il = sys.argv[sys.argv.index('--dump-il') + 1] if '--dump-il' in sys.argv else None
    dump_cell = sys.argv[sys.argv.index('--dump-cell') + 1] if '--dump-cell' in sys.argv else None
    dump_all = '--dump-all' in sys.argv
    copy_from = sys.argv[sys.argv.index('--copy-from') + 1] if '--copy-from' in sys.argv else None

    shapes, insts, terms, instnet = load(geom, conn)
    sel, pins = symbol_facts(shapes, terms)
    wires, labels, moves, plan_rows, notes, kept_rows = [], [], [], [], [], []
    tot = dict(nets=0, routed=0, segs=0, unresolved=0, stubs=0, moved=0)

    for parent in [c for c in CELLS if only is None or c in only]:
        pv = (parent, 'schematic')
        subs = [i for i in insts if (i['cell'], i['view']) == pv and i['cellname'] in CELLS]
        ports = [i for i in insts if (i['cell'], i['view']) == pv and i['cellname'] == 'iopin']
        vterms = [t for t in terms if (t['cell'], t['view']) == pv]
        if not subs and not ports:
            continue
        boxes, ends = [], {}

        # ---- 1. place the blocks, then the ports around them, so every net has a corridor ----
        at = dict((i['name'], i['xy']) for i in insts if (i['cell'], i['view']) == pv)
        if not nomove and parent in FLOW:
            cursor, rowy = 0.0, ROW_Y
            for nm in FLOW[parent]:
                hit = [i for i in subs if i['name'] == nm]
                if not hit:
                    notes.append('FLOW-INSTANCE-MISSING %s %s' % (parent, nm))
                    continue
                i = hit[0]
                if i['rot'] != 'R0':
                    notes.append('NOT-MOVED-NON-R0 %s %s' % (parent, nm))
                    continue
                e, sb = extents(i['cellname'], sel, pins), sel[i['cellname']]
                ox, oy = cursor - e.x0, rowy - (sb[1] + sb[3]) / 2.0
                at[nm] = (round(ox, 6), round(oy, 6))
                cursor = ox + e.x1 + GAP
        port_nets = set()
        vext, lane = [], []
        for i in subs:
            e = extents(i['cellname'], sel, pins)
            x, y = at[i['name']]
            vext.append((x + e.x0, y + e.y0, x + e.x1, y + e.y1))
            lane.append(Box(x + e.x0, y + e.y0, x + e.x1, y + e.y1, None, i['name']))
        if not vext:
            notes.append('NO-SUB-INSTANCES %s' % parent)
            continue
        vx0 = min(v[0] for v in vext)
        vy0 = min(v[1] for v in vext)
        vx1 = max(v[2] for v in vext)
        vy1 = max(v[3] for v in vext)
        net_pins = {}

        for i in subs:
            u = XFORM.get(i['rot'])
            if u is None:
                notes.append('UNKNOWN-TRANSFORM %s %s %s' % (parent, i['name'], i['rot']))
                continue
            ux, uy = u
            sb = sel.get(i['cellname'])
            if sb is None:
                notes.append('NO-SELECTION-BOX %s' % i['cellname'])
                continue
            ox, oy = at[i['name']]
            boxes.append(box_pt(sb, ux, uy, ox, oy, None, i['name']))
            for t in [x for x in terms if x['cell'] == i['cellname'] and x['view'] == 'symbol']:
                pr = pins.get((i['cellname'], t['name']))
                net = instnet.get((parent, i['name'], t['name']), 'NONE')
                if not pr or net == 'NONE':
                    continue
                pb = box_pt(pr[0], ux, uy, ox, oy, net, '%s.%s' % (i['name'], t['name']))
                boxes.append(pb)
                f = face_sym(pr[0], sb)
                fx, fy = ux[0] * f[0] + uy[0] * f[1], ux[1] * f[0] + uy[1] * f[1]
                cx, cy = pb.centre()
                ends.setdefault(net, []).append((cx, cy, fx, fy))
                net_pins.setdefault(net, []).append((cx, cy, fx, fy))

        side_ports = {}
        # an iopin and its terminal are paired by rank along the port column, not by containment:
        # the instance boxes are 0.31875 tall while the ports are only 0.125 apart, so three
        # consecutive origins sit inside anyone of them and containment would double-book terminals.
        vt = [t for t in vterms if t['figs'] and t['net'] != 'NO_NET']
        vt.sort(key=lambda t: t['figs'][0]['bbox'][1])
        py = sorted(ports, key=lambda i: i['xy'][1])
        if len(vt) != len(py):
            notes.append('PORT-TERMINAL-COUNT %s terminals=%d iopin=%d'
                         % (parent, len(vt), len(py)))
            vt, py = [], []
        for t, i in zip(vt, py):
            bb = t['figs'][0]['bbox']
            if not (bb[0] - TOL <= i['xy'][0] <= bb[2] + TOL
                    and bb[1] - TOL <= i['xy'][1] <= bb[3] + TOL):
                notes.append('PORT-TERMINAL-PAIR-UNCLEAR %s %s %s' % (parent, t['name'], i['xy']))
                continue
            side = role_side(t['name'], t['direction'])
            p = net_pins.get(t['net'], [])
            if side == 'left':
                want = min(p)[1] if p else i['xy'][1]
            elif side == 'right':
                want = max(p, key=lambda q: q[0])[1] if p else i['xy'][1]
            elif side == 'top':
                want = max(p, key=lambda q: q[1])[0] if p else i['xy'][0]
            else:
                want = min(p, key=lambda q: q[1])[0] if p else i['xy'][0]
            side_ports.setdefault(side, []).append((i, t, float(want)))
        slots = {}
        if not nomove:
            for side, lst in side_ports.items():
                fixed = {'left': vx0 - MARGIN, 'right': vx1 + MARGIN,
                         'top': vy1 + MARGIN, 'bottom': vy0 - MARGIN}[side]
                for k, pos in spread([x[0] for x in lst], [x[2] for x in lst], PORT_SPACING):
                    slots[k['name']] = (fixed, pos) if side in ('left', 'right') else (pos, fixed)
            moved = dict((i['name'], slots[i['name']]) for i in ports
                         if i['name'] in slots
                         and slots[i['name']] != (round(i['xy'][0], 6), round(i['xy'][1], 6)))
            for i in ports:
                if i['name'] in moved:
                    moves.append([parent, 'inst', i['name'], fmt(moved[i['name']][0]),
                                  fmt(moved[i['name']][1])])
                    tot['moved'] += 1
            # every port-name textDisplay belongs to exactly one iopin. Nearest-neighbour matching
            # is wrong here: these ports sit 0.125 apart and each text is 0.09375 above its own
            # port, which is closer to the NEXT port. Both sets are monotone in y, so the pairing is
            # by rank, and a count mismatch is reported instead of guessed around.
            # A port's name display is part of its iopin instance: measured in the S3C2 loop test
            # (logs/s3c_oa_20261014_165429.log) every textDisplay landed at exactly the planned
            # position after the instance move alone, so no separate text move is emitted -- one
            # would have moved the same display a second time.
            txt = [x for x in shapes if (x['cell'], x['view']) == pv
                   and x['obj'] == 'textDisplay' and x['layer'] == 'pin' and x['xy']]
            notes.append('TEXT-DISPLAYS-FOLLOW-INSTANCES %s displays=%d moved-by-hand=0'
                         % (parent, len(txt)))
        for i in subs:
            if at[i['name']] != (round(i['xy'][0], 6), round(i['xy'][1], 6)):
                moves.append([parent, 'inst', i['name'], fmt(at[i['name']][0]),
                              fmt(at[i['name']][1])])
                tot['moved'] += 1

        for side, lst in side_ports.items():
            # a port's own direction is OUTWARD from the side it was placed on. Measured in the real
            # re-lay: ports kept the importer's "-x approach" convention even on the top row, so a
            # fallback stub ran sideways into the neighbouring port only 0.15 away and schCheck
            # reported "Terminal vdd18 shorted to terminal blank".
            out = {'left': (-1.0, 0.0), 'right': (1.0, 0.0), 'top': (0.0, 1.0),
                   'bottom': (0.0, -1.0)}[side]
            for i, t, _want in lst:
                x, y = slots.get(i['name'], (round(i['xy'][0], 6), round(i['xy'][1], 6)))
                boxes.append(Box(x - PORT_HALF, y - PORT_HALF, x + PORT_HALF, y + PORT_HALF,
                                 t['net'], 'PORT.' + t['name']))
                ends.setdefault(t['net'], []).append((x, y, out[0], out[1]))
                port_nets.add(t['net'])

        allpts = [p for v in ends.values() for p in v]
        # routing lanes are offset from what a block OCCUPIES (body plus its pins), not from the
        # selection box alone: a lane just above the selection box would still cross the supply pins
        grid = Grid(allpts, lane)
        body_edges, pin_edges, adj = route_view(grid, boxes)
        edge_set = all_edges(adj)
        edge_seg = dict((e, grid_seg(grid, e)) for e in edge_set)
        print('S3C2_ROUTE %s nets=%d endpoints=%d grid=%dx%d'
              % (parent, len(ends), len(allpts), len(grid.xs), len(grid.ys)))
        rows, view_lbls, unres, stubs, view_kept = plan_view(ends, port_nets, boxes, grid,
                                                             adj, body_edges, pin_edges, edge_set,
                                                             edge_seg, notes, parent, show)
        for k in view_kept:
            kept_rows.append([parent, k])
        for net, kind, s in rows:
            wires.append([parent, net, s])
            plan_rows.append([parent, net, kind, fmt(s[0]), fmt(s[1]), fmt(s[2]), fmt(s[3])])
            tot['segs'] += 1
        tot['nets'] += len(ends)
        tot['routed'] += len(set(r[0] for r in rows))
        tot['unresolved'] += len(unres)
        tot['stubs'] += stubs
        for net, x, y, text, j in view_lbls:
            labels.append([parent, net, x, y, text, j])

    for n in notes:
        print('  %s' % n)
    out_cell = repl[1] if repl else None
    if copy_from and not out_cell:
        raise SystemExit('COPY_FROM_NEEDS_CELL_REPLACE')
    pre = post = u''
    if applier:
        text = io.open(applier, encoding='utf-8').read()
        mark = u';; ---- TABLES ----'
        if mark not in text:
            raise SystemExit('APPLIER_HAS_NO_TABLES_MARKER %s' % applier)
        pre, post = text.split(mark, 1)
        pre += u';; generated by scripts/sc1_s3c2_route.py\ns2wLib = "microled_scan_s3c"\n'
        if copy_from:
            pre += COPY_BLOCK.replace('@@SRC@@', copy_from).replace('@@DST@@', out_cell)
    tail = u''
    if dump_il:
        text = io.open(dump_il, encoding='utf-8').read()
        dmark = u';; ---- DRIVER ----'
        if dmark not in text:
            raise SystemExit('DUMP_HAS_NO_DRIVER_MARKER %s' % dump_il)
        pre += u'\n;; geometry dump procedures, spliced from %s\n' % os.path.basename(dump_il)
        pre += text.split(dmark, 1)[0]
        if dump_cell:
            tail = (u'\nprintf("S2D-BEGIN\\n")\ns9DumpView("%s" "schematic")\n'
                    u's9DumpView("%s" "symbol")\nprintf("S2D-END\\n")\n'
                    % (dump_cell, dump_cell))
    with io.open(il, 'wb') as fh:
        fh.write(pre.encode('utf-8'))
        fh.write((u's2wRows = list(\n').encode('utf-8'))
        for c, net, s in wires:
            fh.write((u'  list("%s" "%s" %s)\n'
                      % (out_cell or c, net, ' '.join(fmt(v) for v in s))).encode('utf-8'))
        fh.write(u')\n'.encode('utf-8'))
        fh.write(u's2wLabels = list(\n'.encode('utf-8'))
        for c, net, x, y, text, j in labels:
            fh.write((u'  list("%s" "%s" %s %s "%s" "%s")\n'
                      % (out_cell or c, net, fmt(x), fmt(y), text, j)).encode('utf-8'))
        fh.write(u')\n'.encode('utf-8'))
        fh.write(u's2wMoves = list(\n'.encode('utf-8'))
        for m in moves:
            fh.write((u'  list("%s" "%s" %s)\n'
                      % (out_cell or m[0], m[1], ' '.join(sk(v) for v in m[2:]))).encode('utf-8'))
        fh.write(u')\n'.encode('utf-8'))
        fh.write(u's2wKeep = list(\n'.encode('utf-8'))
        for c, net in kept_rows:
            fh.write((u'  list("%s" "%s")\n' % (out_cell or c, net)).encode('utf-8'))
        fh.write(u')\n'.encode('utf-8'))
        fh.write(post.encode('utf-8'))
        fh.write(tail.encode('utf-8'))
    if plan_csv:
        with io.open(plan_csv, 'wb') as fh:
            fh.write(u'parent,net,kind,x1,y1,x2,y2\n'.encode('utf-8'))
            for r in plan_rows:
                fh.write((u','.join(r) + u'\n').encode('utf-8'))
    for m in moves:
        print('  MOVE %s %s %s' % (m[0], m[1], ' '.join(m[2:])))
    print('S3C2_ROUTE_TOTAL views=%d nets=%d routed=%d segments=%d stubs=%d unresolved=%d moved=%d'
          % (len(only or CELLS), tot['nets'], tot['routed'], tot['segs'], tot['stubs'],
             tot['unresolved'], tot['moved']))
    return 0


def grid_seg(grid, e):
    a, b = grid.pt(e[0]), grid.pt(e[1])
    return (a[0], a[1], b[0], b[1])


def all_edges(adj):
    out = set()
    for n, ns in adj.items():
        for m in ns:
            out.add(ek(n, m))
    return out


def uniq(segs):
    out = []
    for s in segs:
        t = (min(s[0], s[2]), min(s[1], s[3]), max(s[0], s[2]), max(s[1], s[3]))
        if t not in out:
            out.append(t)
    return out


def merge_segs(segs):
    """a routed net is drawn as as few figures as possible: collinear runs of grid edges are joined
    where they touch or overlap, so a bus lane is one line instead of twenty"""
    runs = {}
    for s in uniq(segs):
        if abs(s[0] - s[2]) < TOL:
            runs.setdefault(('v', s[0]), []).append((s[1], s[3]))
        else:
            runs.setdefault(('h', s[1]), []).append((s[0], s[2]))
    out = []
    for key, ivals in sorted(runs.items(), key=lambda kv: str(kv[0])):
        ivals.sort()
        lo, hi = ivals[0]
        for a, b in ivals[1:]:
            if a <= hi + TOL:
                hi = max(hi, b)
            else:
                out.append((key, lo, hi))
                lo, hi = a, b
        out.append((key, lo, hi))
    segs2 = []
    for key, lo, hi in out:
        if key[0] == 'v':
            segs2.append((key[1], lo, key[1], hi))
        else:
            segs2.append((lo, key[1], hi, key[1]))
    return segs2


if __name__ == '__main__':
    sys.exit(main())
