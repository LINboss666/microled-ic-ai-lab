#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 S3C3: judge the six MANUAL screenshots the visual review gate is waiting on.

Screenshots are a human deliverable from S3C3 on (measured in results/evidence/
sc1_s3c3_gui_capture_attempts.txt: the Qt top level yields a 134-byte uniform PNG, the largest child is
an unmapped helper, the windows carry no WM_NAME, and _NET_CLIENT_LIST_STACKING does not follow
hiRaiseWindow -- so no automated capture can be trusted here). This script does not capture anything.
It answers the one question the gate needs: are the six named files real, distinct, and non-blank?

The six expected names come from results/evidence/sc1_s3c3_gui_manual_checklist.csv, which is written
by scripts/s3c3_gui_manual_session.sh from the window list the SKILL script itself printed -- so the
row set cannot drift from what the session actually opened.

A stub passes "exists" and fails here. Rejects:
  * missing file, or under --min-bytes (a 600x450 window is never a few hundred bytes)
  * the same SHA-256 twice (one window screenshotted six times)
  * zero variance, which --variance checks with ImageMagick's `convert -format %?[fx:standard_deviation]`
    when that tool is reachable; without it the row is marked UNVERIFIED_BLANK rather than passed.

    python scripts/sc1_s3c3_shots_verify.py [--evdir results/evidence] [--min-bytes 20000]
"""
from __future__ import print_function
import hashlib
import os
import subprocess
import sys

CHECKLIST = 'sc1_s3c3_gui_manual_checklist.csv'


def read(path):
    f = open(path, 'rb')
    try:
        return f.read()
    finally:
        f.close()


def rows(evdir):
    src = os.path.join(evdir, CHECKLIST)
    if not os.path.isfile(src):
        return None
    out = []
    for line in read(src).decode('utf-8', 'replace').splitlines()[1:]:
        cols = [c.strip().strip('"') for c in line.split(',')]
        if len(cols) >= 3 and cols[1] and cols[2]:
            out.append((cols[0], cols[1], cols[2], cols[3], cols[4]))
    return out


def variance(png):
    try:
        p = subprocess.Popen(['convert', png, '-format', '%[fx:standard_deviation]', 'info:'],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError:
        return None
    out = p.communicate()[0].decode('utf-8', 'replace').strip()
    if p.returncode != 0 or not out:
        return None
    try:
        return float(out)
    except ValueError:
        return None


def main():
    args = sys.argv[1:]
    evdir = args[args.index('--evdir') + 1] if '--evdir' in args else os.path.join('results', 'evidence')
    min_bytes = int(args[args.index('--min-bytes') + 1]) if '--min-bytes' in args else 20000

    want = rows(evdir)
    if want is None:
        print('NO_CHECKLIST %s -- run scripts/s3c3_gui_manual_session.sh first' % CHECKLIST)
        return 2
    pairs = [(r[1], r[2]) for r in want]
    if len(pairs) != 6 or len(set(pairs)) != 6:
        # tightened per the S3C4 review note: the checklist IS the expectation, so a short, long or
        # duplicated list can certify nothing
        print('CHECKLIST_BAD rows=%d unique=%d -- must be exactly 6 unique cell/view pairs' % (
            len(pairs), len(set(pairs))))
        print('S3C3_SHOTS_VERIFY: FAIL')
        return 1
    seen = {}
    present = 0
    bad = []
    for idx, cell, view, wid, geom in want:
        name = 'sc1_s3c3_shot_%s_%s.png' % (cell, view)
        path = os.path.join(evdir, name)
        if not os.path.isfile(path):
            bad.append('MISSING %s (window %s %s)' % (name, wid, geom))
            print('SHOT %s %s:%s = MISSING' % (idx, cell, view))
            continue
        data = read(path)
        present += 1
        sha = hashlib.sha256(data).hexdigest()
        std = variance(path)
        note = ''
        if len(data) < min_bytes:
            bad.append('TOO_SMALL %s bytes=%d want>=%d' % (name, len(data), min_bytes))
            note = ' TOO_SMALL'
        if sha in seen:
            bad.append('DUPLICATE %s same bytes as %s' % (name, seen[sha]))
            note += ' DUPLICATE'
        if std is None:
            # tightened per the S3C4 review note: an unreadable variance must not fall through to a
            # "non-blank" verdict, it is a failure of the evidence
            bad.append('VARIANCE_UNREADABLE %s (convert gave no standard deviation)' % name)
            note += ' VARIANCE_UNREADABLE'
        elif not (-1e30 < std < 1e30) or std <= 0.0:
            bad.append('BLANK %s standard_deviation=%s' % (name, std))
            note += ' BLANK'
        seen[sha] = name
        print('SHOT %s %s:%s bytes=%d sha=%s std=%s%s' % (
            idx, cell, view, len(data), sha[:12], '-' if std is None else '%.4f' % std, note))
    print('S3C3_SHOTS_VERIFY expected=%d present=%d distinct=%d problems=%d' % (
        len(want), present, len(seen), len(bad)))
    for b in bad:
        print('FAIL %s' % b)
    if present < len(want) or bad:
        print('S3C3_SHOTS_VERIFY: FAIL -- VISUAL_REVIEW stays open')
        return 1
    print('S3C3_SHOTS_VERIFY: PASS -- six distinct non-blank manual screenshots')
    return 0


if __name__ == '__main__':
    sys.exit(main())
