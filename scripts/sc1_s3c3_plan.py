#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C3: a fixed-placement wiring plan for the two parent schematics.

Why this exists instead of more router: section 4 says do not extend the 928-line S3C2 router, and a
plan a reviewer can read is cheaper than a search. Every coordinate here is parsed out of
`results/evidence/sc1_s3c3_dump_pins.txt` -- this round's database read-back where each sub-instance
pin rectangle was pushed through dbTransformPoint with the instance's own transform -- so no pin
position is typed by hand, and the symbol-box-centre subtraction S3C2 was criticised for is gone:
the pin point IS the transformed pin rectangle's centre.

Placement (origins and port positions) is chosen by hand, in the grid the views already use, then
each segment is checked against every foreign pin box, every instance body and every already-placed
net geometry; a segment that would touch another net is refused, not routed around. Nets with exactly
two endpoints whose pin centres share a row get one straight wire; everything else gets an outward
stub plus a name label, the idiom the netlist importer itself used in these views and what section 4
allows.

usage: python scripts/sc1_s3c3_plan.py [--dump PATH] [--out-csv PATH] [--report PATH]
"""
from __future__ import print_function
import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, 'results', 'evidence')
GRID = 0.0125
STUB = 0.30
PAD = 0.006            # how close foreign geometry may come before the plan refuses the segment

# hand-chosen placement: (instance, master, origin_x, origin_y) and (port, direction, x, centre_y)
VIEWS = {
    'sc1_ls_c1_top_r2d': {
        'insts': [('Xcore', 'sc1_ls_core_r2d', 1.0, 1.0), ('Xnand', 'sc1_ls_c1_r2d', 4.4, 1.0)],
        'ports': [('en', 'input', -1.6, 1.0), ('core_ok33', 'input', 3.2, 1.375),
                  ('gate33', 'output', 6.6, 1.0), ('vdd18', 'inout', 1.2, 2.6),
                  ('vdd33', 'inout', 0.6, 2.9), ('vss', 'inout', 1.0, -1.0)],
        'straight': ['en', 'y', 'core_ok33', 'gate33'],
    },
    'sc1_r3_scan_chain_1ch': {
        'insts': [('Xff', 'c2mos_dff', 1.0, 1.0), ('Xgate', 'sc1_scan_gate', 4.0, 1.0),
                  ('Xls', 'sc1_ls_c1_top_r2d', 7.5, 1.125)],
        'ports': [('d', 'input', -0.6, 0.875), ('clk', 'input', -0.6, 1.125),
                  ('blank', 'input', 2.5, 1.125), ('core_ok33', 'input', 5.9, 1.25),
                  ('gate33', 'output', 9.6, 1.125), ('vdd18', 'inout', 1.2, 2.6),
                  ('vdd33', 'inout', 0.6, 2.9), ('vss', 'inout', 1.0, -1.0)],
        'straight': ['qbar', 'en', 'blank', 'core_ok33', 'gate33', 'd', 'clk'],
    },
}
FDIRECTION = {'input': 'input', 'output': 'output', 'inout': 'inputOutput'}


def snap(v):
    return round(round(float(v) / GRID) * GRID, 4)


def corners(text):
    return [(float(m[0]), float(m[1])) for m in
            re.findall(r'\((-?[\d.]+)[ ,]+(-?[\d.]+)\)', text)]


def parse_dump(path):
    """pin rectangles in SYMBOL coordinates per master, plus the port box offsets"""
    pins, bodies, port_off, master_of = {}, {}, None, {}
    for ln in io.open(path, encoding='utf-8', errors='replace'):
        ln = ln.strip()
        if ln.startswith('DP-INST '):
            q = ln.split('"')
            view, inst, master = q[1], q[3], q[5]
            master_of[(view, inst)] = master
            m = re.search(r'bBox=\(\(([^)]+)\) \(([^)]+)\)', ln)
            if m and master != 'iopin':
                c = [[float(v) for v in g.split()] for g in m.groups()]
                bodies.setdefault(master, (abs(c[1][0] - c[0][0]) / 2.0,
                                           abs(c[1][1] - c[0][1]) / 2.0))
        elif ln.startswith('DP-PIN '):
            q = ln.split('"')
            view, inst, term = q[1], q[3], q[5]
            master = master_of.get((view, inst))
            if master is None:
                continue
            seg = ln.split(' RAW ')[1].split(' XFORMED ')[0]
            c = corners(seg)
            if len(c) != 2:
                continue
            pins.setdefault(master, {})[term] = c[0] + c[1]
        elif ln.startswith('DP-PORT '):
            q = ln.split('"')
            m = re.search(r'bBox=\(\(([^)]+)\) \(([^)]+)\)', ln)
            if m and port_off is None:
                c = [[float(v) for v in g.split()] for g in m.groups()]
                port_off = ((c[1][0] - c[0][0]) / 2.0, (c[1][1] - c[0][1]) / 2.0,
                            (c[0][1] + c[1][1]) / 2.0)
    return pins, bodies, port_off


def outward(box, master_half):
    """which face of the pin rectangle the wire leaves from: the long axis, away from the origin"""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    if abs(x2 - x1) >= abs(y2 - y1):
        return ('left' if cx <= 0 else 'right'), cx, cy, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0
    return ('up' if cy >= 0 else 'down'), cx, cy, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0


def endpoints(view, pins, bodies, port_off, golden):
    """one entry per drawn pin. The NET is the parent net the golden binding table gives for
    (view, instance, child port) -- the symbol's own terminal name is only the child port."""
    spec = VIEWS[view]
    bind = {(cell, inst, port): pnet for cell, inst, child, port, pnet in golden if cell == view}
    out = []
    for name, master, ox, oy in spec['insts']:
        mp = pins.get(master)
        if not mp:
            raise SystemExit('dump has no pin rectangles for master %s' % master)
        for term, box in sorted(mp.items()):
            d, cx, cy, hx, hy = outward(box, bodies.get(master))
            net = bind.get((view, name, term), term)
            out.append(dict(net=net, child_port=term, owner='%s.%s' % (name, term),
                            x=snap(ox + cx), y=snap(oy + cy), hx=hx, hy=hy, outward=d,
                            kind='instpin', master=master, body=bodies.get(master),
                            origin=(snap(ox), snap(oy))))
    for p in spec['ports']:
        pname, pdir, px, py = p
        out.append(dict(net=pname, child_port=pname, owner='PORT.%s' % pname, x=snap(px), y=snap(py),
                        hx=port_off[0], hy=port_off[1],
                        outward='right' if pdir == 'output' else 'left', kind='port',
                        direction=FDIRECTION[pdir], master='iopin', body=port_off,
                        origin=(snap(px), snap(py))))
    return out


def seg_box(seg, w=0.0):
    return (min(seg[0], seg[2]) - w, min(seg[1], seg[3]) - w,
            max(seg[0], seg[2]) + w, max(seg[1], seg[3]) + w)


def ep_box(ep, w=0.0):
    return (ep['x'] - ep['hx'] - w, ep['y'] - ep['hy'] - w,
            ep['x'] + ep['hx'] + w, ep['y'] + ep['hy'] + w)


def body_box(ep):
    """the instance body in parent coordinates, from the ORIGIN the plan places it at -- not from
    the pin, which sits on the body edge"""
    if ep['kind'] == 'port' or not ep['body']:
        return None
    hx, hy = ep['body']
    ox, oy = ep['origin']
    return (snap(ox - hx), snap(oy - hy), snap(ox + hx), snap(oy + hy))


def touch(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


PORT_OVERSHOOT = 0.175   # measured iopin box half-width is 0.1125; run past the far edge


def reach(ep):
    """how far a wire must go to be sure it crosses the port's own pin figure. The iopin's electrical
    pin is a rectangle inside the instance box, and schCheck reported `floating input/output` for a
    wire that stopped at the box centre, so a port end is pushed through the whole arrow."""
    return PORT_OVERSHOOT if ep['kind'] == 'port' else 0.0


def stub_of(ep):
    """starts at the pin centre, so the wire really overlaps the pin figure"""
    x, y = ep['x'], ep['y']
    if ep['outward'] == 'left':
        return (snap(x - ep['hx'] - STUB - reach(ep)), y, x, y)
    if ep['outward'] == 'right':
        return (x, y, snap(x + ep['hx'] + STUB + reach(ep)), y)
    if ep['outward'] == 'up':
        return (x, y, x, snap(y + ep['hy'] + STUB))
    return (x, snap(y - ep['hy'] - STUB), x, y)


def label_at(ep, seg):
    """the label sits on the wire's own free end -- a name label only holds a net when it touches
    that wire (measured in S3C2), so it is anchored at the endpoint, not beside it"""
    if ep['outward'] == 'right':
        return (seg[2], seg[1], 'lowerLeft')
    if ep['outward'] == 'left':
        return (seg[0], seg[1], 'lowerRight')
    if ep['outward'] == 'up':
        return (seg[0], seg[3], 'lowerCenter')
    return (seg[0], seg[1], 'upperCenter')


def plan_view(view, pins, bodies, port_off, golden):
    spec = VIEWS[view]
    eps = endpoints(view, pins, bodies, port_off, golden)
    by_net = {}
    for ep in eps:
        by_net.setdefault(ep['net'], []).append(ep)
    rows, problems, placed = [], [], []
    # instance bodies, for the "a wire must not run through a body" rule
    body_boxes = []
    for ep in eps:
        bb = body_box(ep)
        if bb:
            body_boxes.append((ep['owner'].split('.')[0], bb))
    for net in sorted(by_net):
        epset = by_net[net]
        if net in spec['straight'] and len(epset) == 2 and \
                abs(epset[0]['y'] - epset[1]['y']) < 1e-9:
            # endpoints are the pin CENTRES: a segment that only reaches the box edge measured as
            # unconnected by schCheck ("floating pin"), which is the failure this round is fixing
            a, b = sorted(epset, key=lambda e: e['x'])
            seg = (snap(a['x'] - reach(a)), a['y'], snap(b['x'] + reach(b)), b['y'])
            if seg[2] <= seg[0]:
                problems.append('%s %s straight wire has no length' % (view, net))
                continue
            corridor = seg_box(seg, PAD)
            bad = [nm for nm, bx in body_boxes
                   if touch(corridor, bx) and nm not in (a['owner'].split('.')[0],
                                                         b['owner'].split('.')[0])]
            bad += ['%s/%s' % (n2, r2['kind']) for n2, r2 in placed if n2 != net
                    and touch(corridor, r2['box'])]
            for other in eps:
                if other['net'] != net and touch(corridor, ep_box(other, PAD)):
                    bad.append('pin %s' % other['owner'])
            if bad:
                problems.append('%s %s straight wire blocked by %s'
                                % (view, net, sorted(set(bad))))
                continue
            rows.append(dict(view=view, net=net, kind='wire', seg=seg,
                             owners='%s|%s' % (a['owner'], b['owner'])))
            placed.append((net, dict(kind='wire', box=corridor)))
            continue
        for ep in epset:
            seg = stub_of(ep)
            box = seg_box(seg, PAD)
            own = ep['owner'].split('.')[0]
            bad = [nm for nm, bx in body_boxes if touch(box, bx) and nm != own]
            bad += ['%s/%s' % (n2, r2['kind']) for n2, r2 in placed if n2 != net
                    and touch(box, r2['box'])]
            for other in eps:
                if other['net'] != net and touch(box, ep_box(other, PAD)):
                    bad.append('pin %s' % other['owner'])
            if bad:
                problems.append('%s %s stub for %s blocked by %s'
                                % (view, net, ep['owner'], sorted(set(bad))))
                continue
            rows.append(dict(view=view, net=net, kind='stub', seg=seg, owners=ep['owner'],
                             label=label_at(ep, seg)))
            placed.append((net, dict(kind='stub', box=box)))
    return rows, problems, eps


def check_bindings(view, eps, golden):
    want = dict(('%s.%s' % (inst, port), pnet) for cell, inst, child, port, pnet in golden
                if cell == view)
    got = dict((e['owner'], e['net']) for e in eps if e['kind'] == 'instpin')
    assert all(e['child_port'] == e['owner'].split('.')[1] for e in eps)
    return ['%s golden=%s plan=%s' % (k, want.get(k), got.get(k))
            for k in sorted(set(list(want) + list(got))) if want.get(k) != got.get(k)]


def load_golden(path):
    rows = []
    for ln in io.open(path, encoding='utf-8').read().splitlines()[1:]:
        if ln.strip():
            f = [c.strip('"') for c in ln.split(',')]
            rows.append((f[0], f[1], f[2], f[4], f[5]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', default=os.path.join(EV, 'sc1_s3c3_dump_pins.txt'))
    ap.add_argument('--out-csv', default=os.path.join(EV, '_incoming', 'sc1_s3c3_wire_plan.csv'))
    ap.add_argument('--report', default='')
    args = ap.parse_args()
    pins, bodies, port_off = parse_dump(args.dump)
    if not port_off:
        raise SystemExit('dump has no port pin boxes')
    golden = load_golden(os.path.join(EV, 'sc1_s3c_golden_subinst.csv'))
    all_rows, all_problems = [], []
    for view in sorted(VIEWS):
        rows, problems, eps = plan_view(view, pins, bodies, port_off, golden)
        all_rows += rows
        all_problems += problems
        all_problems += ['%s binding %s' % (view, p) for p in check_bindings(view, eps, golden)]
        ports = set(e['net'] for e in eps if e['kind'] == 'port')
        wired = set(r['net'] for r in rows if r['view'] == view)
        if ports - wired:
            all_problems.append('%s ports with no geometry: %s' % (view, sorted(ports - wired)))
        for p in sorted(ports):
            if not any(e['owner'] == 'PORT.%s' % p and
                       any(r['owners'].find('PORT.%s' % p) >= 0 for r in rows)
                       for e in eps):
                all_problems.append('%s port %s has no drawn segment' % (view, p))
    with io.open(args.out_csv, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('view,net,kind,x1,y1,x2,y2,owners,label_x,label_y,justification\n')
        for r in all_rows:
            s = r['seg']
            lab = r.get('label') or ('', '', '')
            fh.write(u'"%s","%s","%s","%.4f","%.4f","%.4f","%.4f","%s","%s","%s","%s"\n'
                     % (r['view'], r['net'], r['kind'], s[0], s[1], s[2], s[3], r['owners'],
                        lab[0], lab[1], lab[2]))
    lines = ['S3C3_PLAN rows=%d views=%d' % (len(all_rows), len(VIEWS))]
    per = {}
    for r in all_rows:
        per[(r['view'], r['kind'])] = per.get((r['view'], r['kind']), 0) + 1
    for k in sorted(per):
        lines.append('  %s %s rows=%d' % (k[0], k[1], per[k]))
    for p in all_problems:
        lines.append('PROBLEM %s' % p)
    lines.append('S3C3_PLAN_PROBLEMS %d' % len(all_problems))
    text = '\n'.join(lines) + '\n'
    if args.report:
        io.open(args.report, 'w', encoding='utf-8', newline='\n').write(text)
    print(text)
    return 1 if all_problems else 0


if __name__ == '__main__':
    sys.exit(main())
