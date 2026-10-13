#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E1: one call contract shared by the two R2E entries.

    from sc1_r2e1_call_contract import call, preflight_verdict, runner_verdict

Why this exists: the R2E review reproduced two failure paths in the new callers only (the audited
reader/delay/preflight/supply checker and run_spectre.sh are frozen and were not reworked).

  A1  both entries ran the preflight as `... 2>&1 | tail -4`, so the exit code they recorded was
      TAIL's, and a supply_contract refusal with `TESTBENCH_PREFLIGHT: FAIL` was written as rc=0/PASS
      while the runner was still called.
  A2  both entries decided "this run worked" from the presence of a `<LABEL>: PASS` text, so a runner
      that printed that token and then exited 3 with `SPECTRE ... rc=3` was recorded as a success.

Everything here is therefore about the CALL, not about the circuit:

  * call() runs the command through subprocess with an argv list -- no shell, so no `tail`, no pipeline
    status, and no dependence on bash version or an inherited pipefail;
  * preflight_verdict() keeps the preflight's own exit code and requires exactly one
    `TESTBENCH_PREFLIGHT: PASS` with no FAIL line, otherwise it is a tool/log fault;
  * runner_verdict() requires the runner's real rc=0, exactly one final PASS for THIS label, no FAIL,
    exactly one `SPECTRE name=<this deck> rc=0`, `CHECK error_hits=0`, a `done_line` reporting zero
    errors, and this run's own datafile + log present, readable, non-empty and inside this deck's
    directory. An old raw sitting next to a failed run is refused before any reader is reached.

The three exit codes stay separate values (preflight_rc, runner_rc, spectre_rc); nothing here
re-encodes one into another, and refusal reasons are returned as a list so the caller can record the
specific one that fired.
"""
from __future__ import print_function

import os
import re
import shlex
import subprocess
import sys

try:
    _text = unicode
except NameError:
    _text = str

MISSING = object()

try:
    _uni = unicode                       # py2.6: execv() refuses a unicode argv
except NameError:
    _uni = None


def _native(s):
    """a native byte string on py2, unchanged on py3"""
    if _uni is not None and isinstance(s, _uni):
        return s.encode('utf-8')
    return s


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def hook(name, default):
    """an injectable command, the same pattern the audited S1 entry uses (PF_CMD / RUN_CMD / READ_CMD).

    A mock test sets the variable to a script in its own isolated directory; the default is the real
    project tool, so forgetting to set it can never silently test a fake against a real run.
    """
    return os.environ.get(name, default)


def call(cmd, env=MISSING, cwd=None):
    """run `cmd` (a shell-style string, split with shlex) and return (REAL exit code, full output).

    No shell is involved: the caller gets the child's status, not a pipeline's last element. The
    output is returned complete; anything shorter is the caller's display choice, never its evidence.
    """
    argv = shlex.split(_native(cmd))
    # py2.6 hands a unicode argv straight to execv(), which refuses it; the audited tools are called
    # with byte strings on both platforms
    argv = [_native(a) for a in argv]
    if not argv:
        return 9, 'BAD_USAGE: empty command'
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         cwd=cwd, env=(None if env is MISSING else env))
    raw = p.communicate()[0]
    return p.returncode, u(raw).replace('\r\n', '\n').replace('\r', '\n')


def _count(text, pattern):
    return len([l for l in text.split('\n') if re.search(pattern, l)])


def _first(text, pattern):
    for l in text.split('\n'):
        if re.search(pattern, l):
            return l.strip()
    return ''


PREFLIGHT_PASS = r'^TESTBENCH_PREFLIGHT: PASS$'
PREFLIGHT_FAIL = r'^TESTBENCH_PREFLIGHT: FAIL'
PREFLIGHT_STAGE = r'^PREFLIGHT_STAGE='
PREFLIGHT_REJECT = r'^PREFLIGHT_REJECT:|^PREFLIGHT_HARNESS_ERROR:'


def preflight_verdict(rc, text):
    """-> (ok, reason, summary). The exit code is the callee's own; it is never recomputed."""
    text = text or ''
    fails = _count(text, PREFLIGHT_FAIL)
    passes = _count(text, PREFLIGHT_PASS)
    stage = _first(text, PREFLIGHT_STAGE)
    reject = _first(text, PREFLIGHT_REJECT)
    summary = ' ; '.join([l for l in (stage or '', reject or '') if l])[:150] or text.strip()[:150]
    if rc != 0:
        return False, 'preflight_rc=%s refused (%s)' % (rc, summary.replace('\n', ' | ')), summary
    if passes != 1:
        return False, ('tool/log fault: the preflight exited 0 but printed %d completion markers '
                       '(exactly one TESTBENCH_PREFLIGHT: PASS is required)' % passes), summary
    if fails:
        return False, ('tool/log fault: rc=0 with %d TESTBENCH_PREFLIGHT: FAIL line(s) present'
                       % fails), summary
    return True, 'preflight_rc=0 with exactly one completion marker', summary


RUNNER_PASS = r'^%s: PASS$'
SPECTRE_LINE = r'^SPECTRE name=(\S+) rc=(\S+)'
ERROR_HITS = r'^CHECK error_hits=(\S+)'
DONE_LINE = r"^CHECK done_line='(.*)'"
DATAFILE = r"^CHECK datafile='(.*)'"
LOGFILE = r'^LOGFILE (\S+)'


def _usable(path):
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def runner_verdict(label, deck, rc, text):
    """-> (ok, reasons, parts). parts carries spectre_rc / error_hits / datafile / logfile verbatim.

    Every condition the R2E entries were missing is checked here, and all failures are reported
    together instead of the first one silently standing in for the rest.
    """
    text = text or ''
    parts = {
        'preflight_rc': None,
        'runner_rc': rc,
        'spectre_rc': '',
        'error_hits': '',
        'datafile': '',
        'logfile': '',
        'done_line': '',
        'pass_lines': _count(text, RUNNER_PASS % re.escape(label)),
        'fail_lines': _count(text, r'^%s: FAIL$' % re.escape(label)),
    }
    m = re.search(SPECTRE_LINE, text, re.M)
    n_spectre = _count(text, r'^SPECTRE name=')
    if m:
        parts['spectre_name'], parts['spectre_rc'] = m.group(1), m.group(2)
    m = re.search(ERROR_HITS, text, re.M)
    if m:
        parts['error_hits'] = m.group(1)
    m = re.search(DONE_LINE, text, re.M)
    if m:
        parts['done_line'] = m.group(1)
    m = re.search(DATAFILE, text, re.M)
    if m:
        parts['datafile'] = m.group(1)
    m = re.search(LOGFILE, text, re.M)
    if m:
        parts['logfile'] = m.group(1)

    reasons = []
    if rc != 0:
        reasons.append('runner_rc=%s (a PASS token in the text does not override it)' % rc)
    if parts['pass_lines'] != 1:
        reasons.append('%d final PASS lines for label %s, need exactly 1'
                       % (parts['pass_lines'], label))
    if parts['fail_lines']:
        reasons.append('%d final FAIL lines for label %s' % (parts['fail_lines'], label))
    if n_spectre != 1:
        reasons.append('%d SPECTRE status lines, need exactly 1' % n_spectre)
    elif parts['spectre_name'] != os.path.basename(deck):
        reasons.append('SPECTRE status names %s, not this deck %s'
                       % (parts['spectre_name'], os.path.basename(deck)))
    elif parts['spectre_rc'] != '0':
        reasons.append('spectre_rc=%s' % parts['spectre_rc'])
    if parts['error_hits'] != '0':
        reasons.append('CHECK error_hits=%s' % (parts['error_hits'] or 'missing'))
    if not parts['done_line'].startswith('spectre completes with 0 error'):
        reasons.append('done_line=%r' % parts['done_line'][:60])
    # the data must belong to THIS run: a failed run that leaves an older readable raw behind is
    # refused here, before any reader is called, instead of being read as if it were fresh
    if not _usable(parts['datafile']):
        reasons.append('datafile missing/unreadable/empty: %s' % (parts['datafile'] or 'none'))
    elif not os.path.normpath(parts['datafile']).startswith(
            os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(deck)), 'sim'))):
        reasons.append("datafile is outside this deck's sim directory")
    if not _usable(parts['logfile']):
        reasons.append('logfile missing/unreadable/empty: %s' % (parts['logfile'] or 'none'))
    return (not reasons), reasons, parts


def line(row, prefix):
    """first line of a captured output that starts with `prefix`, for honest evidence excerpts"""
    for l in (row or '').split('\n'):
        if l.strip().startswith(prefix):
            return l.strip()
    return ''
