#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3C4: pair every Symbol port name with the text that must sit next to it, then emit the
local fix script. Nothing here moves geometry by guessing coordinates.

What the read-only dump (skill/sc1_s3c4_dump_symbols.il -> logs/s3c4_dump_symbols.log) measured:
  * 8 Symbol views, 48 terminals, and EVERY pin figure has exactly one child object which is a
    label on layer "pin" purpose "label" whose theLabel equals that terminal's name. So the
    name<->pin correspondence already exists in the database as an object relationship; S3C2's
    s2aFindAxis ignored it and matched by nearest coordinate, which is why 48/48 positions could
    pass while the text next to a pin named something else.
  * what is wrong is placement: in sc1_scan_power_1ch_s3c the vss pin is at the bottom edge
    (bbox y -0.925..-0.75) while its label anchor sits at (1.125 0.5), and "clk"'s label sits at
    (0.0 -0.5) -- i.e. the bottom pin's area shows another port's name. Exactly the reviewer finding.
  * the only other text in each view is the cell-name label and the instance-name placeholder
    "[@instanceName]", so there are no orphan duplicate labels to reconcile, and both of those are
    obstacles that must stay readable.

Method, in the order the task book requires (build ALL pairings, prove uniqueness, only then move):
  1. take terminals and directions from cv~>terminals (frozen);
  2. take the pin rectangle from term~>pins~>figs and keep pinFig~>pin name as the ownership proof;
  3. take the attached label from the pin figure's children, read its text with theLabel;
  4. accept a pairing only when one label belongs to one terminal and the text equals that name;
     a missing, duplicated or unparsable pairing is reported and that view is refused -- the real
     terminal is never renamed to fit the text;
  5. compute where the label's bounding box has to be: inside the Symbol body, next to its own pin,
     on the pin's side, and not overlapping any other text; a same-edge collision is resolved by
     staggering the inset depth, never by moving the pin;
  6. emit the delta as a relative move (dbMoveFig with "R0" 1.0), which preserves each label's own
     justification, and verify per Symbol that every device/drawing stub really spans body->pin;
  7. write the plan (what will move) plus the BEFORE table (48 rows) so the post-fix readback can be
     compared item by item, and only the views with a defect are touched.

Usage: python scripts/sc1_s3c4_fix_labels.py <dump.log> <out-prefix> [--apply-il path]
"""
from __future__ import print_function
import io
import os
import re
import sys

LINE = re.compile(r'^\\?[or#]*\s*(SD-[A-Z]+)\s+(.*)$')
GRID = 0.00625
EDGE_TOL = 0.02
ALREADY_MAX = 0.20


def val(tok):
    if tok is None:
        return None
    tok = tok.strip()
    if tok == 'NONE' or tok == 'nil':
        return None
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    if tok.startswith('('):
        inner = tok[1:-1].strip()
        if inner.startswith('('):
            return [val(p) for p in split_points(inner)]
        return [float(x) for x in inner.split()]
    try:
        return float(tok)
    except ValueError:
        return tok


def split_points(s):
    """Split '((x1 y1) (x2 y2))' into its two top-level groups."""
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth == 0 and ch == ')':
            out.append(cur + ')')
            cur = ''
        elif depth > 0:
            cur += ch
        elif ch != ' ':
            cur += ch
    return out


def parse_kv(rest):
    """(positional tokens, {key: raw value}) -- a scanner, not a regex.

    `%L` prints a bbox as ((x y) (x y)), and no regex alternation can match balanced parentheses, so
    the naive key=value regex silently truncated every box to one point. That is why this walks the
    string and counts depth instead.
    """
    pos, out, i, n = [], {}, 0, len(rest)
    while i < n:
        while i < n and rest[i] == ' ':
            i += 1
        if i >= n:
            break
        if rest[i] == '"':
            end = rest.find('"', i + 1)
            end = end if end >= 0 else n - 1
            pos.append(rest[i:end + 1])
            i = end + 1
            continue
        if rest[i] == '(':
            end, depth = i, 0
            while end < n:
                c = rest[end]
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            pos.append(rest[i:end + 1])
            i = end + 1
            continue
        j = rest.find('=', i)
        if j < 0:
            pos.append(rest[i:])
            break
        tok = rest[i:j]
        if ' ' in tok:
            pos.extend(tok.split()[:-1])
            tok = tok.split()[-1]
        i = j + 1
        if rest[i] == '(':
            depth, k = 0, i
            while k < n:
                if rest[k] == '(':
                    depth += 1
                elif rest[k] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            out[tok] = rest[i:k + 1]
            i = k + 1
        elif rest[i] == '"':
            k = rest.find('"', i + 1)
            out[tok] = rest[i:k + 1]
            i = k + 1
        else:
            k = rest.find(' ', i)
            k = k if k >= 0 else n
            out[tok] = rest[i:k]
            i = k
    return pos, out
def parse(log):
    """symbols[cell] = {'terms': {name: {'dir', 'pinbox', 'label': {...}}}, 'body': box, 'obstacles': [], 'stubs': []}"""
    syms = {}
    for raw in io.open(log, encoding='utf-8', errors='replace').read().splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        tag, rest = m.group(1), m.group(2)
        pos, kv = parse_kv(rest)
        cell = val(pos[0]) if pos else None
        if tag == 'SD-VIEW':
            syms.setdefault(cell, {'terms': {}, 'body': None, 'obstacles': [], 'stubs': [],
                                   'opened': kv.get('opened') == 't'})
        elif tag == 'SD-TERM':
            syms[cell]['terms'].setdefault(val(kv['name']), {})['dir'] = val(kv['direction'])
        elif tag == 'SD-PINFIG':
            t = syms[cell]['terms'].setdefault(val(kv['term']), {})
            t['pinbox'] = val(kv['bbox'])
            t['owner'] = val(kv['owner'])
            t['layer'] = val(kv['layer'])
        elif tag == 'SD-CHILD':
            # printed as: SD-CHILD "<cell>" "<term>" objType=... (the term is a bare token, not key=value)
            term = val(pos[1]) if len(pos) > 1 else None
            t = syms[cell]['terms'].setdefault(term, {})
            t['label'] = {'xy': val(kv['xy']), 'bbox': val(kv['bbox']),
                          'text': val(kv['theLabel']), 'just': val(kv['just']),
                          'objType': val(kv['objType']), 'attached': True}
        elif tag == 'SD-TXT':
            if val(kv['objType']) == 'label' and val(kv['layer']) in ('device', 'instance'):
                syms[cell]['obstacles'].append({'xy': val(kv['xy']), 'bbox': val(kv['bbox']),
                                                'text': val(kv['theLabel']),
                                                'keep': 'CELL_NAME' if val(kv['layer']) == 'device'
                                                else 'INSTANCE_NAME'})
        elif tag == 'SD-GRAPH':
            if val(kv['objType']) == 'rect' and val(kv['purpose']) == 'drawing':
                syms[cell]['body'] = val(kv['bbox'])
            elif val(kv['objType']) == 'line':
                syms[cell]['stubs'].append({'pts': val(kv['pts'])})
    return syms


def centre(box):
    return ((box[0][0] + box[1][0]) / 2.0, (box[0][1] + box[1][1]) / 2.0)


def size(box):
    return (abs(box[1][0] - box[0][0]), abs(box[1][1] - box[0][1]))


def side(body, pin):
    if pin[0][1] >= body[1][1] - EDGE_TOL:
        return 'top'
    if pin[1][1] <= body[0][1] + EDGE_TOL:
        return 'bottom'
    if pin[1][0] <= body[0][0] + EDGE_TOL:
        return 'left'
    if pin[0][0] >= body[1][0] - EDGE_TOL:
        return 'right'
    return 'inside'


def snap(v):
    return round(round(v / GRID) * GRID, 5)


def overlaps(a, b, pad=0.005):
    return not (a[1][0] <= b[0][0] - pad or a[0][0] >= b[1][0] + pad or
                a[1][1] <= b[0][1] - pad or a[0][1] >= b[1][1] + pad)


def place(body, pin, sd, s, placed, depth, along=0.0):
    """bbox centre for a label so the whole text box sits inside the body next to its own pin."""
    w, h = s
    cx, cy = centre(pin)
    if sd == 'top':
        target = (cx + along, body[1][1] - depth - h / 2.0)
    elif sd == 'bottom':
        target = (cx + along, body[0][1] + depth + h / 2.0)
    elif sd == 'left':
        target = (body[0][0] + depth + w / 2.0, cy + along)
    elif sd == 'right':
        target = (body[1][0] - depth - w / 2.0, cy + along)
    else:
        target = (cx, cy)
    return (snap(target[0]), snap(target[1]))


def fits(body, c, w, h):
    box = [(c[0] - w / 2.0, c[1] - h / 2.0), (c[0] + w / 2.0, c[1] + h / 2.0)]
    if not (body[0][0] <= box[0][0] and box[1][0] <= body[1][0] and
            body[0][1] <= box[0][1] and box[1][1] <= body[1][1]):
        return None
    return box


def box_gap(a, b):
    dx = max(a[0][0] - b[1][0], b[0][0] - a[1][0], 0.0)
    dy = max(a[0][1] - b[1][1], b[0][1] - a[0][1], 0.0)
    return max(dx, dy)


def fit(body, pin, sd, w, h, taken, obstacles):
    """Smallest edge inset that clears every other text, then the smallest slide along the edge.

    Measured: [@instanceName] sits across the middle of these bodies (sc1_ls_c1_r2d spans x -0.35625
    ..0.60625 at y 0.20625..0.29375), so a fixed 0.04 inset collides with it and a coarse stagger
    pushed the top pin's name 0.3 into the body -- which is exactly the "far from its own pin" result
    the verifier rejects. Scanning the inset in grid steps finds the narrow free band between the text
    and the body edge instead.
    """
    alongs = [0.0, 0.125, -0.125, 0.25, -0.25, 0.375, -0.375]
    depths = []
    d = GRID
    while d <= 0.30001:
        depths.append(round(d, 5))
        d = round(d + GRID, 5)
    for depth in depths:
        best = None
        for al in alongs:
            c = place(body, pin, sd, (w, h), None, depth, al)
            box = fits(body, c, w, h)
            if box is None:
                continue
            if any(overlaps(box, p) for p in taken + obstacles):
                continue
            cost = abs(al)
            if best is None or cost < best[0]:
                best = (cost, c, box)
        if best:
            return best[1], best[2]
    return None, None


def want_stub(body, pin, sd):
    """The two endpoints the non-electrical stub of this pin must have, or None.

    Measured on sc1_scan_power_1ch_s3c: the vss pin rect is (-0.025 -0.925)..(0.025 -0.75) and the
    body is (-1.25 -0.625)..(1.25 0.625), and its stub is the line (0.0 -0.75)..(0.0 -0.625) -- i.e.
    body edge -> the pin rect's own facing edge. Not the pin centre: an earlier version of this audit
    compared against the centre and therefore called 43 of 48 stubs unverified, which was the checker
    being wrong, not the data.
    """
    cx, cy = centre(pin)
    if sd == 'top':
        return [(cx, body[1][1]), (cx, pin[0][1])]
    if sd == 'bottom':
        return [(cx, body[0][1]), (cx, pin[1][1])]
    if sd == 'left':
        return [(body[0][0], cy), (pin[1][0], cy)]
    if sd == 'right':
        return [(body[1][0], cy), (pin[0][0], cy)]
    return None


def same_pts(a, b, eps=0.0125):
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def stub_audit(cell, S, rows, actions, problems):
    """One connecting stub per pin; stale stubs left at an old pin position are listed, not deleted blind."""
    body = S['body']
    used = set()
    for name in sorted(S['terms']):
        pin = S['terms'][name].get('pinbox')
        if not pin:
            continue
        sd = side(body, pin)
        want = want_stub(body, pin, sd)
        if want is None:
            rows.append([cell, name, S['terms'][name].get('dir'), pin, sd,
                         S['terms'][name].get('label', {}).get('text'), '', '', '', '', '', '',
                         '', 'PIN_INSIDE_BODY'])
            problems.append('PIN_INSIDE_BODY %s %s (pin is not on a body edge, stub rule undefined)'
                            % (cell, name))
            continue
        hit = None
        for i, st in enumerate(S['stubs']):
            pts = st['pts']
            if not pts or len(pts) < 2:
                continue
            if (same_pts(pts[0], want[0]) and same_pts(pts[1], want[1])) or \
               (same_pts(pts[0], want[1]) and same_pts(pts[1], want[0])):
                hit = i
                break
        if hit is None:
            actions.append([cell, 'add_stub', name, want[0], want[1]])
            rows.append([cell, name, S['terms'][name].get('dir'), pin, sd,
                         S['terms'][name].get('label', {}).get('text'), '', '', '', '', '', '',
                         '', 'STUB_MISSING'])
        else:
            used.add(hit)
    for i, st in enumerate(S['stubs']):
        if i in used or not st['pts'] or len(st['pts']) < 2:
            continue
        p, q = st['pts'][0], st['pts'][1]
        length = ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5
        aligned = same_pts((p[0], q[1]), (p[0], p[1])) or same_pts((q[0], p[1]), (p[0], p[1]))
        on_body = any(abs(pt[0] - body[0][0]) <= 0.001 or abs(pt[0] - body[1][0]) <= 0.001 or
                      abs(pt[1] - body[0][1]) <= 0.001 or abs(pt[1] - body[1][1]) <= 0.001
                      for pt in (p, q))
        std = [(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5)
               for j, s2 in enumerate(S['stubs']) if j in used and s2['pts'] and len(s2['pts']) >= 2
               for a, b in [(s2['pts'][0], s2['pts'][1])]]
        is_stub_shape = aligned and on_body and length > 0.02 and (
            not std or min(abs(length - s) for s in std) < 0.005)
        if is_stub_shape:
            actions.append([cell, 'stale_stub', '', p, q])
        else:
            actions.append([cell, 'keep_line_not_a_stub', '', p, q])
    return actions


def plan(syms):
    rows, moves, actions, problems = [], [], [], []
    for cell in sorted(syms):
        S = syms[cell]
        if not S['opened'] or not S['body']:
            # s3c_asg_shell is a cell without a Symbol view in this library; the dump says opened=NONE
            continue
        body = S['body']
        obstacles = [o['bbox'] for o in S['obstacles'] if o['bbox']]
        placed = []
        for name in sorted(S['terms']):
            t = S['terms'][name]
            pin, lab = t.get('pinbox'), t.get('label')
            if not pin:
                problems.append('NO_PIN_RECT %s %s' % (cell, name))
                continue
            if not lab:
                problems.append('NO_ATTACHED_LABEL %s %s' % (cell, name))
                continue
            if lab['text'] != name:
                problems.append('TEXT_NOT_OWN_NAME %s pin=%s label=%s (terminal is NOT renamed)'
                                % (cell, name, lab['text']))
                continue
            if t.get('owner') not in (None, name):
                problems.append('OWNER_MISMATCH %s %s owner=%s' % (cell, name, t.get('owner')))
                continue
            sd = side(body, pin)
            w, h = size(lab['bbox'])
            cur = lab['bbox']
            foreign = [o.get('pinbox') for k, o in S['terms'].items() if k != name and o.get('pinbox')]
            already = (box_gap(cur, pin) <= ALREADY_MAX and fits(body, centre(cur), w, h)
                       and not any(overlaps(cur, p) for p in placed + obstacles)
                       and all(box_gap(cur, pin) <= box_gap(cur, f) for f in foreign))
            if already:
                newc, box = centre(cur), cur
            else:
                newc, box = fit(body, pin, sd, w, h, placed, obstacles)
                if newc is None:
                    problems.append('UNRESOLVED_OVERLAP %s %s' % (cell, name))
                    continue
            placed.append(box)
            oldc = centre(cur)
            dx, dy = snap(newc[0] - oldc[0]), snap(newc[1] - oldc[1])
            dist = max(abs(dx), abs(dy))
            verdict = 'MISPLACED' if dist > 0.05 else 'ALREADY_OK'
            rows.append([cell, name, t.get('dir'), pin, sd, lab['text'], lab['just'], lab['xy'],
                         lab['bbox'], newc, dx, dy, '%.4f' % dist, verdict])
            if verdict == 'MISPLACED':
                moves.append([cell, name, dx, dy, lab['text']])
        stub_audit(cell, S, rows, actions, problems)
    return rows, moves, actions, problems


HEADER = ['cell', 'terminal', 'direction', 'pin_bbox', 'pin_side', 'label_text', 'justification',
          'label_xy_before', 'label_bbox_before', 'label_center_after', 'dx', 'dy',
          'move_distance', 'verdict']


def fmt(x):
    if x is None:
        return ''
    if isinstance(x, (list, tuple)) and x and isinstance(x[0], (list, tuple)):
        return ' '.join('%s %s' % (p[0], p[1]) for p in x)
    if isinstance(x, (list, tuple)):
        return ' '.join('%s' % v for v in x)
    if isinstance(x, float):
        return '%.5f' % x
    return str(x)


def emit_il(moves, actions, path, renames=None, only=None):
    """Write the local fix script.

    renames maps a planned Symbol cell to the view that is actually opened (used for the copy-first
    proof); only is the set of cells this run touches, so the proof round can be one Symbol.
    """
    renames = renames or {}
    cells = sorted(set([m[0] for m in moves] + [a[0] for a in actions]))
    if only:
        cells = [c for c in cells if c in only]
    jobs = [(c, renames.get(c, c)) for c in cells]
    rows_m = [m for m in moves if (not only) or m[0] in only]
    rows_s = [a for a in actions if (not only) or a[0] in only
              and a[1] in ('add_stub', 'stale_stub')]
    il = [u';; %s -- GENERATED by scripts/sc1_s3c4_fix_labels.py; do not hand-edit.'
          % os.path.basename(path),
          u';;',
          u';; Rows come from the pairing table, and every object is found by DATABASE RELATIONSHIP,',
          u';; not by coordinate guessing: the label to move is the child of this terminal\'s own pin',
          u';; figure whose theLabel equals the terminal name; the stale stub to delete is the line on',
          u';; device/drawing whose endpoints equal the recorded old ones. Pin rectangles, terminals,',
          u';; directions, nets, the cell-name label and the "[@instanceName]" text are never touched.',
          u';; NEW_SIMULATION_RUNS = 0.',
          u'',
          u's4Lib = "microled_scan_s3c"',
          u's4Copies = nil',
          u's4Jobs = list(']
    for plan_cell, target in jobs:
        il.append(u'  list("%s" "%s")' % (plan_cell, target))
    il += [u')', u's4Moves = list(']
    for cell, name, dx, dy, text in rows_m:
        il.append(u'  list("%s" "%s" %s %s)' % (cell, name, dx, dy))
    il += [u')', u's4Stubs = list(']
    for cell, act, name, p, q in rows_s:
        il.append(u'  list("%s" "%s" %s %s %s %s)' % (
            cell, 'del' if act == 'stale_stub' else 'add',
            fmt(p[0]), fmt(p[1]), fmt(q[0]), fmt(q[1])))
    il += [u')', u'']
    if renames:
        il += [u';; copy-first proof: the planned cells name the SOURCE view, s4Jobs then targets the',
               u';; copies, so the delivered Symbol views are not opened for write in this run',
               u's4Copies = list(']
        for c, t in jobs:
            il.append(u'  list("%s" "%s")' % (c, t))
        il += [u')']
    il += [u'',
           u'procedure(s4Val(v) if(v v "NONE"))',
           u'procedure(s4Target(job) nth(1 job))',
           u'',
           u'procedure(s4FindLabel(cv term)',
           u'  let((res p f ch) ;; the text object drawn for this terminal\'s own pin figure',
           u'    res = nil',
           u'    foreach(tm cv~>terminals',
           u'      when(equal(tm~>name term)',
           u'        foreach(p tm~>pins',
           u'          foreach(f p~>figs',
           u'            foreach(ch dbGet(f \'children)',
           u'              when(and(res == nil equal(s4Val(dbGet(ch \'theLabel)) term)',
           u'                       or(equal(ch~>objType "label") equal(ch~>objType "textDisplay")))',
           u'                res = ch',
           u'              )',
           u'            )',
           u'          )',
           u'        )',
           u'      )',
           u'    )',
           u'    res',
           u'  )',
           u')',
           u'',
           u'procedure(s4FindLine(cv a b)',
           u'  let((res pts) ;; exact endpoint match, either order; the SKILL side does no arithmetic',
           u'    res = nil',
           u'    foreach(s cv~>shapes',
           u'      when(and(res == nil equal(s~>objType "line")',
           u'               equal(s4Val(dbGet(s \'layerName)) "device")',
           u'               equal(s4Val(dbGet(s \'purpose)) "drawing"))',
           u'        pts = dbGet(s \'points)',
           u'        when(and(pts equal(pts list(a b))) res = s)',
           u'        when(and(pts res == nil equal(pts list(b a))) res = s)',
           u'      )',
           u'    )',
           u'    res',
           u'  )',
           u')',
           u'',
           u'printf("S4-BEGIN jobs=%L moves=%L stubs=%L\\n" length(s4Jobs) length(s4Moves) length(s4Stubs))',
           u'when(s4Copies',
           u'  foreach(cp s4Copies',
           u'    src = car(errset(dbOpenCellViewByType(s4Lib nth(0 cp) "symbol" nil "r")))',
           u'    new = car(errset(dbCopyCellView(src s4Lib nth(1 cp) "symbol" "symbol")))',
           u'    printf("S4-COPY %L -> %L made=%L\\n" nth(0 cp) nth(1 cp) s4Val(new != nil))',
           u'    errset(dbClose(src))',
           u'  )',
           u')',
           u'foreach(job s4Jobs',
           u'  cell = s4Target(job)',
           u'  plan = nth(0 job)',
           u'  cv = car(errset(dbOpenCellViewByType(s4Lib cell "symbol" nil "a")))',
           u'  when(cv',
           u'    foreach(st s4Stubs',
           u'      when(and(equal(nth(0 st) plan) equal(nth(1 st) "del"))',
           u'        a = list(nth(2 st) nth(3 st))',
           u'        b = list(nth(4 st) nth(5 st))',
           u'        f = s4FindLine(cv a b)',
           u'        printf("S4-STUB-DEL %L pts=(%L %L %L %L) found=%L deleted=%L\\n"',
           u'               cell nth(2 st) nth(3 st) nth(4 st) nth(5 st) s4Val(f != nil)',
           u'               s4Val(if(f car(errset(dbDeleteObject(f))) nil)))',
           u'      )',
           u'    )',
           u'    foreach(st s4Stubs',
           u'      when(and(equal(nth(0 st) plan) equal(nth(1 st) "add"))',
           u'        g = car(errset(dbCreateLine(cv list("device" "drawing")',
           u'                                    list(list(nth(2 st) nth(3 st)) list(nth(4 st) nth(5 st))))))',
           u'        printf("S4-STUB-ADD %L pts=(%L %L %L %L) made=%L bbox=%L\\n"',
           u'               cell nth(2 st) nth(3 st) nth(4 st) nth(5 st) s4Val(g != nil)',
           u'               s4Val(dbGet(g \'bBox)))',
           u'      )',
           u'    )',
           u'    foreach(mv s4Moves',
           u'      when(equal(nth(0 mv) plan)',
           u'        lab = s4FindLabel(cv nth(1 mv))',
           u'        when(lab',
           u'          before = dbGet(lab \'xy)',
           u'          ok = car(errset(dbMoveFig(lab cv list(list(nth(2 mv) nth(3 mv)) "R0" 1.0))))',
           u'          printf("S4-MOVE %L %L from=%L delta=(%L %L) moved=%L text=%L now=%L\\n"',
           u'                 cell nth(1 mv) s4Val(before) nth(2 mv) nth(3 mv) s4Val(ok)',
           u'                 s4Val(dbGet(lab \'theLabel)) s4Val(dbGet(lab \'xy)))',
           u'        )',
           u'        unless(lab printf("S4-SKIP %L %L no owned label found\\n" cell nth(1 mv)))',
           u'      )',
           u'    )',
           u'    errset(dbSave(cv))',
           u'    printf("S4-SAVED %L\\n" cell)',
           u'    errset(dbClose(cv))',
           u'    printf("S4-CLOSED %L\\n" cell)',
           u'  )',
           u'  unless(cv printf("S4-OPENFAIL %L\\n" cell))',
           u')',
           u'printf("S4-DONE\\n")',
           u'nil',
           u'']
    io.open(path, 'wb').write(u'\n'.join(il).encode('utf-8'))
    return len(jobs)


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip().splitlines()[-1])
        return 9
    log, prefix = sys.argv[1], sys.argv[2]
    apply_il = sys.argv[sys.argv.index('--apply-il') + 1] if '--apply-il' in sys.argv else None
    syms = parse(log)
    rows, moves, actions, problems = plan(syms)
    hdr = io.open(prefix + '_labels_before.csv', 'wb')
    hdr.write(('"' + '","'.join(HEADER) + '"\n').encode('utf-8'))
    for r in rows:
        cells = [fmt(v).replace('"', "'") for v in r]
        hdr.write(('"' + '","'.join(cells) + '"\n').encode('utf-8'))
    hdr.close()
    ph = io.open(prefix + '_label_plan.csv', 'wb')
    ph.write('"cell","terminal","dx","dy","label_text"\n'.encode('utf-8'))
    for m in moves:
        ph.write(('"%s","%s","%s","%s","%s"\n' % (m[0], m[1], m[2], m[3], m[4])).encode('utf-8'))
    ph.close()
    ah = io.open(prefix + '_stub_actions.csv', 'wb')
    ah.write('"cell","action","terminal","x1","y1","x2","y2"\n'.encode('utf-8'))
    for a in actions:
        ah.write(('"%s","%s","%s","%s","%s","%s","%s"\n' % (
            a[0], a[1], a[2], fmt(a[3][0]), fmt(a[3][1]), fmt(a[4][0]), fmt(a[4][1]))).encode('utf-8'))
    ah.close()
    paired = len([r for r in rows if r[5] and r[13] in ('ALREADY_OK', 'MISPLACED')])
    missing = len([a for a in actions if a[1] == 'add_stub'])
    stale = len([a for a in actions if a[1] == 'stale_stub'])
    keep = len([a for a in actions if a[1] == 'keep_line_not_a_stub'])
    rep = io.open(prefix + '_plan_report.txt', 'wb')
    for line in [
        'S3C4_PLAN symbol_views=%d cells_seen=%d pairing_rows=%d paired_by_ownership=%d' % (
            len([c for c in syms if syms[c]['opened']]), len(syms), len(rows), paired),
        'S3C4_PLAN labels_misplaced=%d labels_already_next_to_pin=%d' % (
            len(moves), paired - len(moves)),
        'S3C4_PLAN stub_missing=%d stub_stale_to_delete=%d body_lines_kept=%d' % (missing, stale, keep),
        'S3C4_PLAN pairing_problems=%d' % len(problems),
        'S3C4_PLAN views_needing_label_moves=%d' % len(set(m[0] for m in moves)),
    ]:
        rep.write((line + '\n').encode('utf-8'))
        print(line)
    for p in problems:
        rep.write(('PROBLEM %s\n' % p).encode('utf-8'))
        print('PROBLEM %s' % p)
    rep.close()
    if apply_il:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(',')) if '--only' in sys.argv else None
        ren = {}
        if '--copies' in sys.argv:
            for pair in sys.argv[sys.argv.index('--copies') + 1].split(','):
                if '=' in pair:
                    src, dst = pair.split('=', 1)
                    ren[src] = dst
        jobs = emit_il(moves, actions, apply_il, ren, only)
        print('S3C4_APPLY_IL %s jobs=%d moves=%d stubs=%d copies=%s' % (
            apply_il, jobs, len([m for m in moves if not only or m[0] in only]),
            len([a for a in actions if not only or (a[0] in only and a[1] in ('add_stub', 'stale_stub'))]),
            ','.join('%s=%s' % kv for kv in sorted(ren.items())) or 'none'))
    if problems:
        print('S3C4_FIX_LABELS: REFUSED (pairing not unique/provable; terminals are never renamed)')
        return 1
    print('S3C4_FIX_LABELS: PLAN_OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
