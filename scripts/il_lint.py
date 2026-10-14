#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""SCAN-1 S3C3: cheap structural lint for generated and hand-written SKILL files.

Why: three rounds of failures came from a paren or a quote, not from Cadence. The reader cannot know
what the session will say about a file that never parses, so balance is checked before the file is
pushed to the guest. This checks only structure -- bracket balance outside string literals and
comments, and per-line quote parity.

usage: python scripts/il_lint.py <file.il> [more.il ...]
"""
from __future__ import print_function
import io
import sys


def strip(line, in_str):
    out = []
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == ';' and i + 1 < len(line) and line[i + 1] == ';':
            break
        if c == '"':
            in_str = True
            i += 1
            continue
        out.append(c)
        i += 1
    return ''.join(out), in_str


def lint(path):
    text = io.open(path, encoding='utf-8', errors='replace').read()
    depth = 0
    in_str = False
    problems = []
    for n, raw in enumerate(text.splitlines(), 1):
        code, in_str = strip(raw, in_str)
        if in_str:
            problems.append('line %d: string literal still open at end of line' % n)
        depth += code.count('(') - code.count(')')
        if depth < 0:
            problems.append('line %d: closes more than it opens (depth %d)' % (n, depth))
    if in_str:
        problems.append('file ends inside a string literal')
    if depth != 0:
        problems.append('final paren depth %d (expected 0)' % depth)
    return problems, depth


def main():
    files = sys.argv[1:]
    if not files:
        print('usage: il_lint.py <file.il> [...]')
        return 9
    bad = 0
    for f in files:
        problems, depth = lint(f)
        for p in problems:
            print('LINT-FAIL %s %s' % (f, p))
        if not problems:
            print('LINT-PASS %s depth=%d' % (f, depth))
        else:
            bad += 1
    print('IL_LINT files=%d failures=%d' % (len(files), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
