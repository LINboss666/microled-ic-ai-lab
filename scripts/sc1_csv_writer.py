#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scan TAB-separated lines on stdin and write them out as properly quoted CSV.

    printf 'a\tb\n1\t2\n' | python scripts/sc1_csv_writer.py --out FILE [--header]

Exists because the bash entry points built their evidence rows with hand-written printf quoting and
one of them dropped the closing quote of the last column -- a defect that a CSV reader only reports as
a wrong column count, several rows later.
"""
from __future__ import print_function
import io, sys

try:
    _text = unicode
except NameError:
    _text = str


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def main():
    argv = sys.argv[1:]
    out = argv[argv.index('--out') + 1] if '--out' in argv else None
    ncol = None
    lines = []
    for raw in sys.stdin.read().split('\n'):
        if raw.strip() == '':
            continue
        fields = raw.split('\t')
        if ncol is None:
            ncol = len(fields)
        elif len(fields) != ncol:
            print('CSV_WRITER_ERROR: row has %d fields, first row had %d: %r'
                  % (len(fields), ncol, raw[:400]))
            return 1
        lines.append(fields)
    body = u('')
    for fields in lines:
        body += u(','.join([u('"') + u(f).replace(u('"'), u('""')) + u('"') for f in fields])) + u('\n')
    if out:
        with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(body)
        print('CSV_WRITER rows=%d columns=%d -> %s' % (len(lines), ncol, out))
    else:
        sys.stdout.write(body.encode('utf-8') if str is bytes else body)
    return 0


if __name__ == '__main__':
    sys.exit(main())
