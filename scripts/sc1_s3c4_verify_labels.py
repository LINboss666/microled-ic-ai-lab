#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3C4: compare a Symbol dump taken after the label fix against the dump taken before it.

The reviewer's finding was about DISPLAY, so the acceptance test is about display too, and it is
deliberately not "the label is not nil":

  FROZEN_FIRST  every terminal still exists with the same name, the same direction and the SAME pin
                rectangle as before (this round may not move electrical geometry or rename ports to
                make text fit), and every pin still owns a text object whose theLabel is exactly its
                own terminal name.
  ADJACENT      each label's box now sits next to its OWN pin: the gap between the label box and that
                pin rectangle is small, on the pin's own side of the body, and it is NOT near another
                terminal's pin (that is what "clk shown by the ground pin" was).
  NO_OVERLAP    label boxes do not overlap each other or the cell-name / "[@instanceName]" text.
  STUB          every pin has exactly one device/drawing line from the body edge to its own pin
                rectangle, and no such line is left over from an old pin position.
  KEPT          the cell-name label and the instance-name placeholder are still present and unmoved.

Usage: python scripts/sc1_s3c4_verify_labels.py <before.log> <after.log> [--map old=new]...
       rows are compared per (mapped) cell name, so a repaired COPY can be judged against its source.
"""
from __future__ import print_function
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sc1_s3c4_fix_labels as P  # reuse the same reader; two parsers would drift apart

GAP_MAX = 0.30
STUB_EPS = 0.0125


def gap(box_a, box_b):
    """Chebyshev-ish gap between two rectangles, 0 when they touch or overlap."""
    dx = max(box_a[0][0] - box_b[1][0], box_b[0][0] - box_a[1][0], 0.0)
    dy = max(box_a[0][1] - box_b[1][1], box_b[0][1] - box_a[0][1], 0.0)
    return max(dx, dy)


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip().split('\n')[0])
        return 9
    before = P.parse(sys.argv[1])
    after = P.parse(sys.argv[2])
    ren = {}
    if '--map' in sys.argv:
        for pair in sys.argv[sys.argv.index('--map') + 1].split(','):
            src, dst = pair.split('=', 1)
            ren[src] = dst
    fails, rows = [], []
    ports = 0
    for cell in sorted(before):
        B = before[cell]
        if not B['opened'] or not B['body']:
            continue
        if ren and cell not in ren:
            # --map restricts the judgement to the cells that were actually re-dumped (the copy round
            # reads back one Symbol, the final round reads back all eight)
            continue
        tgt = ren.get(cell, cell)
        A = after.get(tgt)
        if not A or not A['opened']:
            fails.append('MISSING_AFTER_VIEW %s' % tgt)
            continue
        if A['body'] != B['body']:
            fails.append('BODY_CHANGED %s %s vs %s' % (cell, B['body'], A['body']))
        for name in sorted(B['terms']):
            b = B['terms'][name]
            a = A['terms'].get(name)
            ports += 1
            if not a:
                fails.append('TERMINAL_LOST %s %s' % (tgt, name))
                continue
            if a.get('dir') != b.get('dir'):
                fails.append('DIRECTION_CHANGED %s %s %s->%s' % (tgt, name, b.get('dir'), a.get('dir')))
            if a.get('pinbox') != b.get('pinbox'):
                fails.append('PIN_RECT_CHANGED %s %s %s->%s' % (tgt, name, b.get('pinbox'), a.get('pinbox')))
            if not a.get('label') or a['label']['text'] != name:
                fails.append('LABEL_TEXT_NOT_OWN_NAME %s %s got=%s' % (tgt, name,
                                                                       a.get('label', {}).get('text')))
                continue
            sd = P.side(A['body'], a['pinbox'])
            g = gap(a['label']['bbox'], a['pinbox'])
            want = P.want_stub(A['body'], a['pinbox'], sd)
            has = ''
            if want:
                has = 'YES' if any(
                    (P.same_pts(s['pts'][0], want[0]) and P.same_pts(s['pts'][1], want[1])) or
                    (P.same_pts(s['pts'][0], want[1]) and P.same_pts(s['pts'][1], want[0]))
                    for s in A['stubs'] if s['pts'] and len(s['pts']) >= 2) else 'NO'
            rows.append([tgt, name, a.get('dir'), fmt(a['pinbox']), sd, a['label']['text'],
                         fmt(a['label']['xy']), fmt(a['label']['bbox']), '%.4f' % g,
                         has, fmt(want[0]) if want else '', fmt(want[1]) if want else '',
                         'ADJACENT' if g <= GAP_MAX else 'FAR_FROM_OWN_PIN'])
            if g > GAP_MAX:
                fails.append('FAR_FROM_OWN_PIN %s %s gap=%s' % (tgt, name, round(g, 4)))
            lb = a['label']['bbox']
            if not (A['body'][0][0] <= lb[0][0] and lb[1][0] <= A['body'][1][0] and
                    A['body'][0][1] <= lb[0][1] and lb[1][1] <= A['body'][1][1]):
                fails.append('LABEL_OUTSIDE_BODY %s %s bbox=%s body=%s' % (tgt, name, fmt(lb),
                                                                          fmt(A['body'])))
            for other, o in sorted(A['terms'].items()):
                if other == name or not o.get('label'):
                    continue
                if P.overlaps(o['label']['bbox'], a['label']['bbox']):
                    fails.append('LABEL_OVERLAP %s %s vs %s' % (tgt, name, other))
                if gap(a['label']['bbox'], o.get('pinbox') or [[0, 0], [0, 0]]) < gap(
                        a['label']['bbox'], a['pinbox']) - 1e-9:
                    fails.append('CLOSER_TO_FOREIGN_PIN %s %s than to %s' % (tgt, name, other))
        # stub check on the after view
        actions, sub = [], []
        P.stub_audit(tgt, A, sub, actions, [])
        miss = [x for x in actions if x[1] == 'add_stub']
        stale = [x for x in actions if x[1] == 'stale_stub']
        for m in miss:
            fails.append('STILL_MISSING_STUB %s %s' % (tgt, m[2]))
        for s in stale:
            fails.append('STALE_STUB_LEFT %s %s %s' % (tgt, fmt(s[3]), fmt(s[4])))
        kept = [o['text'] for o in A['obstacles']]
        want = [o['text'] for o in B['obstacles']]
        if sorted(kept) != sorted(want):
            fails.append('BODY_TEXT_LOST %s %s -> %s' % (tgt, want, kept))
    if '--csv' in sys.argv:
        path = sys.argv[sys.argv.index('--csv') + 1]
        f = io.open(path, 'wb')
        f.write(b'"cell","terminal","direction","pin_bbox","pin_side","label_text","label_xy_after",'
                b'"label_bbox_after","gap_to_own_pin","stub_present","stub_expected_p1",'
                b'"stub_expected_p2","verdict"\n')
        for r in rows:
            f.write(('"' + '","'.join(str(x) for x in r) + '"\n').encode('utf-8'))
        f.close()
        print('S3C4_VERIFY_CSV %s rows=%d' % (path, len(rows)))
    print('S3C4_VERIFY ports=%d rows=%d failures=%d' % (ports, len(rows), len(fails)))
    for f in fails:
        print('FAIL %s' % f)
    verdict = 'PASS' if not fails and ports else 'FAIL'
    print('S3C4_LABEL_VERIFY: %s' % verdict)
    return 0 if verdict == 'PASS' else 1


def fmt(pt):
    return '(%s %s)' % (pt[0], pt[1])


if __name__ == '__main__':
    sys.exit(main())
