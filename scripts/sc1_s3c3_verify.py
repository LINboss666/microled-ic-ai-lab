#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C3: judge the parent schematics from the database read-back, not from what was drawn.

Input is the log of skill/sc1_s3c3_dump_pins.il (rows DP-INST / DP-ITERM / DP-PIN / DP-PORT /
DP-WIRE / DP-NET / DP-LABEL), taken in a session that opened the views read-only after they were
saved -- so this describes the bytes on disk.

Four verdicts, each computed from the rows:
  BINDING       every sub-instance terminal sits on the parent net golden_subinst.csv says,
  ATTACHMENT    the pin's own point, obtained from its pin rectangle through the instance transform,
                lies on a wire segment that belongs to the same net. No bounding-box substitution and
                no symbol-centre subtraction (section 6).
  PORTS         every external port of the view has a same-net segment reaching its pin figure,
  SHORTS        no two segments of different nets touch or cross (section 6's cross-net check).

usage: python scripts/sc1_s3c3_verify.py --dump <log> --views <view[,...]> [--csv <out>]
"""
from __future__ import print_function
import argparse
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, 'results', 'evidence')
SINGLE_ENDPOINT_OK = set(['x', 'q'])   # section 3: these two are the view's own single-pin nets


def pairs(text):
    return [tuple(float(v) for v in m) for m in re.findall(r'\((-?[\d.]+) (-?[\d.]+)\)', text)]


def strip_q(tok):
    return tok.strip().strip('"')


def read_dump(path):
    iterm, pin, port, wire, nets, labels = {}, {}, {}, {}, {}, {}
    for ln in io.open(path, encoding='utf-8', errors='replace'):
        ln = ln.rstrip('\n')
        if not ln.startswith('DP-'):
            continue
        f = ln.split()
        view = strip_q(f[1]) if f[0] in ('DP-INST', 'DP-ITERM', 'DP-PIN', 'DP-PORT',
                                        'DP-WIRE', 'DP-NET', 'DP-LABEL', 'DP-VIEW') else ''
        if f[0] == 'DP-ITERM':
            inst, term = strip_q(f[2]), strip_q(f[3])
            m = re.search(r'net=(\S+)', ln)
            net = strip_q(m.group(1)) if m else ''
            iterm.setdefault(view, {})[(inst, term)] = net
        elif f[0] == 'DP-PIN':
            inst, term = strip_q(f[2]), strip_q(f[3])
            m = re.search(r'XFORMED (.*) purpose=', ln)
            c = pairs(m.group(1)) if m else []
            if len(c) == 2:
                pin.setdefault(view, {})[(inst, term)] = (round((c[0][0] + c[1][0]) / 2.0, 6),
                                                          round((c[0][1] + c[1][1]) / 2.0, 6))
        elif f[0] == 'DP-PORT':
            term = strip_q(f[2])
            m = re.search(r'net=(\S+)', ln)
            net = strip_q(m.group(1)) if m else ''
            b = re.search(r'bBox=\(\(([^)]+)\) \(([^)]+)\)\)', ln)
            if b:
                c = [tuple(float(v) for v in g.split()) for g in b.groups()]
                port.setdefault(view, {})[term] = (net, (round((c[0][0] + c[1][0]) / 2.0, 6),
                                                         round((c[0][1] + c[1][1]) / 2.0, 6)), c)
        elif f[0] == 'DP-WIRE':
            m = re.search(r'net=(\S+)', ln)
            net = strip_q(m.group(1)) if m else ''
            pts = pairs(ln.split('points=')[1].split(' bbox=')[0])
            wire.setdefault(view, []).append((net, pts))
        elif f[0] == 'DP-NET':
            term = strip_q(f[2])
            m = re.search(r'figs=(\S+)', ln)
            nets.setdefault(view, {})[term] = int(strip_q(m.group(1))) if m else -1
        elif f[0] == 'DP-LABEL':
            m = re.search(r'theLabel=(\S+)', ln)
            labels.setdefault(view, []).append(strip_q(m.group(1)) if m else '')
    return iterm, pin, port, wire, nets, labels


def on_segment(pt, seg):
    """axis-aligned segment only; a point that is on the segment counts as electrically reached"""
    (x, y), (p1, p2) = pt, seg
    if abs(p1[1] - p2[1]) < 1e-9 and abs(y - p1[1]) < 1e-9:
        return min(p1[0], p2[0]) - 1e-9 <= x <= max(p1[0], p2[0]) + 1e-9
    if abs(p1[0] - p2[0]) < 1e-9 and abs(x - p1[0]) < 1e-9:
        return min(p1[1], p2[1]) - 1e-9 <= y <= max(p1[1], p2[1]) + 1e-9
    return False


def box_hits_segment(box, seg):
    """axis-aligned segment against an axis-aligned rectangle, the way Virtuoso calls it a contact"""
    (x0, y0), (x1, y1) = box
    (p1, p2) = seg
    T = 1e-9
    x0, x1 = min(x0, x1) - T, max(x0, x1) + T
    y0, y1 = min(y0, y1) - T, max(y0, y1) + T
    if abs(p1[1] - p2[1]) < T:                      # horizontal
        return y0 <= p1[1] <= y1 and min(p1[0], p2[0]) - T < x1 and max(p1[0], p2[0]) + T > x0
    if abs(p1[0] - p2[0]) < T:                      # vertical
        return x0 <= p1[0] <= x1 and min(p1[1], p2[1]) - T < y1 and max(p1[1], p2[1]) + T > y0
    return on_segment((p1[0], p1[1]), seg) or on_segment((p2[0], p2[1]), seg)


def crosses(a, b):
    """true when two axis-aligned segments touch or cross -- Virtuoso calls that connected"""
    for seg1, seg2 in ((a, b), (b, a)):
        p1, p2 = seg1
        q1, q2 = seg2
        if abs(p1[0] - p2[0]) < 1e-9 and abs(q1[1] - q2[1]) < 1e-9:
            if min(q1[1], q2[1]) - 1e-9 <= p1[1] <= max(q1[1], q2[1]) + 1e-9 and \
               min(p1[0], p2[0]) - 1e-9 <= q1[0] <= max(p1[0], p2[0]) + 1e-9:
                return True
        if abs(p1[1] - p2[1]) < 1e-9 and abs(q1[0] - q2[0]) < 1e-9:
            if min(q1[0], q2[0]) - 1e-9 <= p1[0] <= max(q1[0], q2[0]) + 1e-9 and \
               min(p1[1], p2[1]) - 1e-9 <= q1[1] <= max(p1[1], p2[1]) + 1e-9:
                return True
        # collinear overlap
        if abs(p1[1] - p2[1]) < 1e-9 and abs(q1[1] - q2[1]) < 1e-9 and abs(p1[1] - q1[1]) < 1e-9:
            if min(p1[0], p2[0]) - 1e-9 < max(q1[0], q2[0]) and \
               min(q1[0], q2[0]) - 1e-9 < max(p1[0], p2[0]):
                return True
        if abs(p1[0] - p2[0]) < 1e-9 and abs(q1[0] - q2[0]) < 1e-9 and abs(p1[0] - q1[0]) < 1e-9:
            if min(p1[1], p2[1]) - 1e-9 < max(q1[1], q2[1]) and \
               min(q1[1], q2[1]) - 1e-9 < max(p1[1], p2[1]):
                return True
    return False


def load_golden(path):
    """cell -> {(instance, child_port): parent_net}. CSV columns are
    cell,inst,child,port_ordinal,child_port,parent_net"""
    out = {}
    for ln in io.open(path, encoding='utf-8').read().splitlines()[1:]:
        if not ln.strip():
            continue
        f = [strip_q(c) for c in ln.split(',')]
        out.setdefault(f[0], {})[(f[1], f[4])] = f[5]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', required=True)
    ap.add_argument('--views', required=True)
    ap.add_argument('--csv', default='')
    ap.add_argument('--expect-ports', default='1')
    args = ap.parse_args()
    views = [v.strip() for v in args.views.split(',') if v.strip()]
    iterm, pin, port, wire, nets, labels = read_dump(args.dump)
    golden = load_golden(os.path.join(EV, 'sc1_s3c_golden_subinst.csv'))
    rows, problems = [], []
    tot_bind = tot_att = tot_port = tot_port_att = 0
    for view in views:
        want = golden.get(view, {})
        got = iterm.get(view, {})
        for (inst, term), net in sorted(got.items()):
            # the parent view names each instTerm after the child port, and the golden table gives the
            # parent net for that (instance, child port) pair
            expect = want.get((inst, term), '')
            pts = pin.get(view, {}).get((inst, term))
            segs = [(n, s) for (n, s) in wire.get(view, [])]
            attached = None
            if pts:
                for (n, segpairs) in segs:
                    if n != net:
                        continue
                    for seg in zip(segpairs, segpairs[1:]):
                        if on_segment(pts, seg):
                            attached = (n, seg)
                            break
                    if attached:
                        break
            rows.append((view, inst, term, net, expect, pts, bool(attached)))
            tot_bind += 1
            if expect and net != expect:
                problems.append('%s %s.%s net=%s golden=%s' % (view, inst, term, net, expect))
            if not pts:
                problems.append('%s %s.%s has no pin point in the dump' % (view, inst, term))
            elif not attached:
                problems.append('%s %s.%s pin (%.4f,%.4f) is not on a %s segment'
                                % (view, inst, term, pts[0], pts[1], net))
            else:
                tot_att += 1
        for term, (net, centre, box) in sorted(port.get(view, {}).items()):
            tot_port += 1
            hit = False
            for (n, segpairs) in wire.get(view, []):
                if n != net:
                    continue
                for seg in zip(segpairs, segpairs[1:]):
                    if box_hits_segment(box, seg):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                tot_port_att += 1
            else:
                problems.append('%s PORT %s (net=%s) has no same-net segment reaching its pin box %s'
                                % (view, term, net, box))
        allsegs = []
        for (n, segpairs) in wire.get(view, []):
            for seg in zip(segpairs, segpairs[1:]):
                allsegs.append((n, seg))
        for i in range(len(allsegs)):
            for j in range(i + 1, len(allsegs)):
                if allsegs[i][0] != allsegs[j][0] and crosses(allsegs[i][1], allsegs[j][1]):
                    problems.append('%s SHORT net %s segment %s touches net %s segment %s'
                                    % (view, allsegs[i][0], allsegs[i][1], allsegs[j][0],
                                       allsegs[j][1]))
        single = [t for t, n in sorted(nets.get(view, {}).items()) if n == 1]
        for t in single:
            if t not in SINGLE_ENDPOINT_OK and not t.startswith('net'):
                problems.append('%s net %s has one figure and is not an allowed single-endpoint net'
                                % (view, t))
    if args.csv:
        with io.open(args.csv, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('view,instance,child_port,parent_net,golden_net,pin_x,pin_y,'
                     'on_same_net_segment\n')
            for r in rows:
                x = '%.4f' % r[5][0] if r[5] else ''
                y = '%.4f' % r[5][1] if r[5] else ''
                fh.write(u'"%s","%s","%s","%s","%s","%s","%s","%s"\n'
                         % (r[0], r[1], r[2], r[3], r[4], x, y, 'yes' if r[6] else 'no'))
    print('S3C3_VERIFY views=%s pins=%d attached=%d ports=%d ports_on_wire=%d'
          % (','.join(views), tot_bind, tot_att, tot_port, tot_port_att))
    for p in problems:
        print('  PROBLEM %s' % p)
    print('S3C3_VERIFY_PROBLEMS %d' % len(problems))
    print('S3C3_VERIFY: %s' % ('PASS' if not problems else 'FAIL'))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
