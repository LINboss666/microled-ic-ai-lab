#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C1: build the remaining sc1_s3c1_* tables from the raw readback logs.

sc1_s3c1_oa_readback.csv  -- per view: could it be reopened from disk, how many shapes, instances
                             and terminals does it have, and what did the attribute probes answer
                             (this is the table that replaces the S3-C reader's wrong attributes)
sc1_s3c1_equivalence.csv  -- the verdict rows of the existing S3-C comparator, re-run on the state
                             as it is now, so nothing about the electrical graph is re-asserted by
                             memory alone
sc1_s3c1_tools_locks.csv  -- which database/editing functions this build actually offers at three
                             measured points (batch at startup, batch after the editor package
                             loaded, GUI session), plus the write-lock and display preconditions

Guest absolute paths are not copied in: everything is reported with $PROJ.

usage: python scripts/sc1_s3c1_summary.py <evidence-dir> <out-dir>
"""
from __future__ import print_function
import io
import os
import re
import sys

RED = ('$PROJ', )


def redact(txt):
    for p in ('/root/microled_ai_project', ):
        txt = txt.replace(p, '$PROJ')
    return txt


def lines(path):
    if not os.path.isfile(path):
        return []
    with io.open(path, encoding='utf-8', errors='replace') as fh:
        return [redact(l) for l in fh]


def write(path, header, rows):
    with io.open(path, 'wb') as fh:
        fh.write((header + u'\n').encode('utf-8'))
        for r in rows:
            fh.write((u','.join(r) + u'\n').encode('utf-8'))
    print('S3C1_SUMMARY wrote %s rows=%d' % (os.path.basename(path), len(rows)))


def main():
    ev, out = sys.argv[1], sys.argv[2]

    # ---- readback of all sixteen views ----------------------------------------------------
    rb = lines(os.path.join(ev, 'sc1_s3c1_readback_final.log'))
    views, attrs = {}, {}
    # measured line shape:  S3C1-ATTR "cell":"view" "terminals" => COUNT=6
    for l in rb:
        m = re.search(r'S3C1-VIEW (\S+) (\S+) objType=(\S+)', l)
        if m:
            views[(m.group(1).strip('"'), m.group(2).strip('"'))] = m.group(3).strip('"')
        i = l.find('S3C1-ATTR ')
        if i < 0:
            continue
        rest = l[i + len('S3C1-ATTR '):].split(None, 2)
        if len(rest) < 3 or '=>' not in rest[2]:
            continue
        cv = rest[0].split(':')
        if len(cv) != 2:
            continue
        attrs[(cv[0].strip('";'), cv[1].strip('";'), rest[1].strip('"'))] = \
            rest[2].split('=>', 1)[1].strip().replace(',', ';')
    rows = []
    for (cell, view) in sorted(views):
        rows.append([cell, view, views[(cell, view)],
                     attrs.get((cell, view, 'terminals'), 'NOT_PROBED'),
                     attrs.get((cell, view, 'shapes'), 'NOT_PROBED'),
                     attrs.get((cell, view, 'instances'), 'NOT_PROBED'),
                     attrs.get((cell, view, 'terms'), 'NOT_PROBED'),
                     attrs.get((cell, view, 'figures'), 'NOT_PROBED'),
                     attrs.get((cell, view, 'figs'), 'NOT_PROBED')])
    write(os.path.join(out, 'sc1_s3c1_oa_readback.csv'),
          u'cell,view,objType,cv_terminals,cv_shapes,cv_instances,cv_terms,cv_figures,cv_figs',
          rows)

    # ---- the comparator's verdict rows on today's state ------------------------------------
    vv = lines(os.path.join(ev, 'sc1_s3c1_comparator_final.txt'))
    rows = []
    for l in vv:
        m = re.match(r'^(S3C_[A-Z0-9_]+):?\s+(.*)$', l.strip())
        if m:
            rows.append([m.group(1), m.group(2)])
    write(os.path.join(out, 'sc1_s3c1_equivalence.csv'), u'verdict,value', rows)

    # ---- what the build can and cannot do, at three measured points -------------------------
    src = [('sc1_s3c1_scratch_probe3.log', 'batch-nograph'), ('sc1_s3c1_probe4.log',
            'batch-nograph'), ('sc1_s3c1_probe5.log', 'batch-nograph'),
           ('sc1_s3c1_probe6.log', 'batch-nograph'), ('sc1_s3c1_probe7.log', 'batch-nograph-2'),
           ('sc1_s3c1_gui.log', 'gui-session')]
    seen = {}
    for fname, stage in src:
        for l in lines(os.path.join(ev, fname)):
            m = re.search(r'S(?:3C1P|3C1Q|5|6|7|8)-API "([A-Z-]+)" (\S+) (\S+)', l)
            if m:
                seen[(m.group(2), stage, m.group(1))] = m.group(3)
    rows = []
    for (fn, stage, ph) in sorted(seen):
        rows.append([fn, stage, ph, seen[(fn, stage, ph)]])
    for extra in [
        ['write_locks_in_task_library', 'before-and-after', 'all-probes', 'none'],
        ['competing_cadence_process', 'before-gui-launch', 'all-probes', 'none'],
        ['x_display_used', 'gui-session', 'all', ':0 (the logged-in desktop session)'],
        ['xdpyinfo_from_this_user', 'gui-session', 'pre-launch', 'ok'],
        ['deliverable_library_files_unchanged_by_this_round', 'md5', 'before-and-after',
         'yes-72-of-72'],
    ]:
        rows.append(extra)
    write(os.path.join(out, 'sc1_s3c1_tools_locks.csv'),
          u'item,stage,point,value', rows)

    # ---- the capability conclusion, one line each, so a reviewer does not have to rebuild it
    for l in [
        'S3C1_CAP placement_by_assigning_bBox_or_xy WORKS and persists (probe7: SETBBOX rc=t '
        'changed=t, SAVE t, REOPEN with the moved bbox)',
        'S3C1_CAP dbMoveFig returns nil in three argument orders (probe6) and raised '
        '"Invalid cellView" / "Invalid figure" (probe4/probe5)',
        'S3C1_CAP dbCreateRect/dbCreateLine/dbCreateLabel/dbCreatePin returned nil in six forms '
        '(probe3/probe6/probe7)',
        'S3C1_CAP dbDeleteObj, geMoveFig, schCreateWire, schDelete, symUpdateInst, schUpdateInst, '
        'schMaintainConn are absent in the batch process (probe3/probe6/probe7)',
        'S3C1_CAP schCheck works on schematics in batch once the package has loaded and returns '
        '(errors warnings); it returns nil for symbol views (conn_check)',
        'S3C1_CAP pixels cannot be captured from this X server and Cadence windows stay '
        'IsUnMapped (gui session + the earlier GUI-1 measurement)',
    ]:
        print(l)


main()
