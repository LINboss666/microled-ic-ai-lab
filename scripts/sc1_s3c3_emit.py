#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C3: splice the validated wiring plan into the SKILL body and write the runnable file.

The body lives in skill/sc1_s3c3_apply_tpl.il and is hand-written; this script only substitutes the
four data tables at the `;; ---- TABLES ----` marker. One file, no nested `load`, because an inner
load leaves its procedures unbound in this build (measured in S3C2).

Table shapes the template expects:
  s3Jobs    (view copyCell)
  s3Moves   (view label x y)          label = sub-instance name or port name
  s3Segs    (view net x1 y1 x2 y2)
  s3Labels  (view net x y justification)

Only nets that are not ports of the view get a name label: a port's net is named by its terminal,
while an internal net that loses its last figure is renamed by the database, so it needs a label
anchored on the wire (both measured).

usage: python scripts/sc1_s3c3_emit.py [plan.csv]
"""
from __future__ import print_function
import csv
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, 'results', 'evidence')
TPL = os.path.join(ROOT, 'skill', 'sc1_s3c3_apply_tpl.il')
OUT = os.path.join(ROOT, 'skill', 'sc1_s3c3_apply.il')
MARKER = u';; ---- TABLES ----'
COPIES = {'sc1_ls_c1_top_r2d': 's3c3_ls_copy', 'sc1_r3_scan_chain_1ch': 's3c3_chain_copy'}
PORT_ORIGIN_DY = 0.0969     # measured: the iopin pin-box centre sits this far above its xy


def num(v):
    return ('%.6f' % float(v)).rstrip('0').rstrip('.')


def lit(v):
    try:
        return num(v)
    except (TypeError, ValueError):
        return u'"%s"' % v


def table(name, rows):
    if not rows:
        return u'%s = nil\n' % name
    out = [u'%s = nil' % name]
    for r in rows:
        out.append(u'\n%s = cons(list(%s) %s)' % (name, u' '.join(lit(c) for c in r), name))
    return u''.join(out) + u'\n'


def _opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1]
    return default


def main():
    direct = '--direct' in sys.argv
    if direct:
        sys.argv.remove('--direct')
    only_arg = _opt('--only', '')
    if '--only' in sys.argv:
        i = sys.argv.index('--only')
        del sys.argv[i:i + 2]
    plan_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        EV, '_incoming', 'sc1_s3c3_wire_plan.csv')
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    import sc1_s3c3_plan as P

    moves, segs, labels, jobs = [], [], [], []
    port_of = {}
    only = [v.strip() for v in only_arg.split(',') if v.strip()]
    for view in sorted(P.VIEWS):
        if only and view not in only:
            continue
        spec = P.VIEWS[view]
        port_of[view] = set(p[0] for p in spec['ports'])
        for name, master, ox, oy in spec['insts']:
            moves.append([view, name, num(ox), num(oy)])
        for pname, pdir, px, py in spec['ports']:
            moves.append([view, pname, num(px), num(py - PORT_ORIGIN_DY)])
        jobs.append([view, view if direct else COPIES[view]])

    rows = list(csv.DictReader(io.open(plan_path, encoding='utf-8')))
    if not rows:
        raise SystemExit('EMPTY_PLAN %s' % plan_path)
    for r in rows:
        view, net, kind = r['view'], r['net'], r['kind']
        if only and view not in only:
            continue
        segs.append([view, net, r['x1'], r['y1'], r['x2'], r['y2']])
        at_port = r['owners'].startswith('PORT.') or '|PORT.' in r['owners']
        internal = net not in port_of[view]
        # Every segment carries its own name label. Measured on this round's copies: a wire that only
        # touches pins geometrically stays on its own unnamed net (schCheck then reports the pin as
        # floating), while a wire that carries a name label joins the net of that name -- so the
        # label is what makes the connection, and the geometry is what makes it honest. Nets that are
        # ports are labelled too: the terminal's own name does not propagate onto a touching wire.
        if kind == 'wire':
            mx = (float(r['x1']) + float(r['x2'])) / 2.0
            my = (float(r['y1']) + float(r['y2'])) / 2.0
            horiz = abs(float(r['x2']) - float(r['x1'])) >= abs(float(r['y2']) - float(r['y1']))
            labels.append([view, net, num(mx), num(my),
                           'lowerLeft' if horiz else 'lowerCenter'])
        elif r['label_x']:
            labels.append([view, net, r['label_x'], r['label_y'], r['justification']])

    text = io.open(TPL, encoding='utf-8').read()
    if MARKER not in text:
        raise SystemExit('TEMPLATE_HAS_NO_TABLE_MARKER %s' % TPL)
    head, tail = text.split(MARKER, 1)
    block = (MARKER + u' (written by scripts/sc1_s3c3_emit.py from %s)\n'
             % os.path.basename(plan_path))
    block += table('s3Jobs', jobs) + u'\n' + table('s3Moves', moves) + u'\n'
    block += table('s3Segs', segs) + u'\n' + table('s3Labels', labels) + u'\n'
    if direct:
        # written after the template's default, so a delivery run is unmistakable in the file
        block += u's3Direct = t\n'
    block += u'\n'
    io.open(OUT, 'w', encoding='utf-8', newline='\n').write(head + block + tail)
    print('S3C3_EMIT jobs=%d moves=%d segs=%d labels=%d internal_only=%s file=%s'
          % (len(jobs), len(moves), len(segs), len(labels), 'yes', OUT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
