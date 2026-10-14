#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""SCAN-1 S3C4: turn a raw Cadence session log into an evidence file with the print prefixes stripped.

Cadence writes every printf line with a `\o `, `\r `, `\a ` or `\w ` prefix; the committed S3C3 evidence
was stored without them because scripts/sc1_s3c3_verify.py only reads lines that start with its DP-
tags. Doing the strip in one named script keeps that requirement visible instead of a shell one-liner
that cannot be re-run.

    python scripts/sc1_s3c4_strip_log.py <in.log> <out.txt> [tag[,tag]]
"""
from __future__ import print_function
import io
import re
import sys

PREFIX = re.compile(u'^\\\\[orad#wvile]?\\s*')


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip().splitlines()[0])
        return 9
    src, dst = sys.argv[1], sys.argv[2]
    tags = sys.argv[3].split(',') if len(sys.argv) > 3 and sys.argv[3] else None
    kept, skipped = [], 0
    for raw in io.open(src, encoding='utf-8', errors='replace').read().splitlines():
        ln = PREFIX.sub('', raw.rstrip()).strip()
        if not ln:
            continue
        if tags and not any(ln.startswith(t) for t in tags):
            skipped += 1
            continue
        kept.append(ln)
    io.open(dst, 'wb').write(('\n'.join(kept) + '\n').encode('utf-8'))
    print('STRIP_LOG %s -> %s kept=%d filtered_out=%d' % (src, dst, len(kept), skipped))
    return 0


if __name__ == '__main__':
    sys.exit(main())
