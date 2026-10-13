#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R2E-C1 probe: which save form does THIS Spectre build accept for a source/branch current,
and can it reach a node or a device that lives INSIDE a subckt instance?

One candidate per deck, because a fatal save kills the whole file. For every run the probe keeps the
simulator's own ERROR/WARNING lines and the exact TRACE signal list of the produced psfascii, so the
answer is this build's behaviour rather than a remembered syntax.

    python scripts/sc1_r2e_saveprobe.py
"""
from __future__ import print_function

import io
import optparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

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


DECK = '''simulator lang=spectre insensitive=yes
// save-syntax probe only. rail is driven directly by a vsource; the iprobe sits in the LOAD branch,
// never in the rail ({note}).
{inst}
sw1 tran stop=20n maxstep=1n
save rail vss
{saves}
'''

FLAT = '''V1 (rail 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
R1 (rail node_mid) resistor r=10000
Ip1 (node_mid vss) iprobe'''

# the master name is a project-style name, not a shell word, so a rejection cannot be blamed on a
# reserved token
HIER = '''V1 (rail 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
subckt sc1_probe_load (rail vss)
  R1 (rail node_mid) resistor r=10000
  Ip1 (node_mid vss) iprobe
ends sc1_probe_load
Xcal (rail vss) sc1_probe_load'''

CANDS = [
    ('flat_V1_i',           FLAT, 'save V1:i',             'reference: top-level vsource :i'),
    ('hier_sigtype_all',    HIER, 'save Xcal sigtype=all', 'instance with sigtype=all'),
    ('hier_dot_node',       HIER, 'save Xcal.node_mid',    'dot separator for the internal node'),
    ('root_star',           HIER, 'save /*',               'pattern from the root'),
    ('root_star_all',       HIER, 'save /* sigtype=all',   'root pattern, all signal types'),
    ('hier_star_depth',     HIER, 'save Xcal/* sigtype=all depth=2', 'instance pattern with depth'),
    ('hier_qmark',          HIER, 'save Xcal?node_mid',    'wildcard separator character'),
    ('inst_param_save',     HIER, 'save Xcal:i',           'instance :i at the subckt level'),
]


def sh(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    return p.returncode, u(raw)


def main():
    op = optparse.OptionParser()
    op.add_option('--scratch')
    o, _ = op.parse_args()
    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'sc1_sim', 'r2e_saveprobe')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    for name, inst, saves, note in CANDS:
        deck = os.path.join(scratch, 'probe_%s.scs' % name)
        with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(DECK.format(inst=inst, saves=saves, note=note)))
        rc, txt = sh('LABEL=PROBE bash %s %s 90 2>&1' % (os.path.join(HERE, 'run_spectre.sh'), deck))
        txt = txt.replace('\r', '')
        log = ''
        m = re.search(r'LOGFILE (\S+)', txt)
        if m:
            log = m.group(1)
        data = ''
        m = re.search(r"CHECK datafile='([^']*)'", txt)
        if m:
            data = m.group(1)
        trace = ''
        if data and os.path.isfile(data):
            _r2, trace = sh("awk '/^TRACE/,/^VALUE/' %s | tr -d '\\n' | cut -c1-200" % data)
        msgs = []
        if log and os.path.isfile(log):
            _r3, msgs_raw = sh("grep -E 'ERROR|WARNING' %s | head -4" % log)
            msgs = [l.strip()[:150] for l in msgs_raw.split('\n') if l.strip()]
        verdict = 'RUN_OK' if re.search(r'^PROBE: PASS$', txt, re.M) else 'RUN_FAIL'
        print('=== %-18s %-24s %s' % (name, saves, verdict))
        print('    trace: %s' % trace.strip()[:200])
        for mm in msgs:
            print('    msg  : %s' % mm)
        if not msgs:
            print('    msg  : (no ERROR/WARNING in the log)')


if __name__ == '__main__':
    main()
