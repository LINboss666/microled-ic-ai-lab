#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R2E-C2 probe: can a save reach TWO hierarchy levels, the way the S2 decks need?

The S2 cell is Xt (top master) -> Xcore / Xbuf (second master) -> the MOS devices, so a per-device
terminal current and an internal node both sit two levels below the deck. scripts/sc1_r2e_saveprobe.py
measured that one level works with a DOT separator; this probe repeats the question at two levels and
on a real PDS device, so the S2 entry is written against measured syntax only.

    python scripts/sc1_r2e_two_level_probe.py
"""
from __future__ import print_function

import io
import optparse
import os
import re
import subprocess

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
// two-level save probe. lvl1 holds Rd and the instance of lvl2, lvl2 holds the devices, so the dotted
// paths below are exactly the depth the S2 decks need (deck -> Xt -> Xcore/Xbuf -> MOS).
simopt options temp=27
include "{lib}" section=tt
subckt lvl2 (out gate vdd vss)
  Mn  (x2  gate vss vss ) n18 l=2e-7 w=2e-6
  Ip2 (x2  out         ) iprobe
ends lvl2
subckt lvl1 (out gate vdd vss)
  Rd  (out x1          ) resistor r=1000
  X2  (x1    gate vdd vss) lvl2
ends lvl1
Vd (out 0) vsource dc=1.8
Vg (gate 0) vsource dc=1.8
Vdd (vdd 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Xt (out gate vdd vss) lvl1
sw1 tran stop=20n maxstep=1n
save out gate vdd vss
{saves}
'''

CANDS = [
    ('one_level_node',  'save Xt.x1'),
    ('two_level_node',  'save Xt.X2.x2'),
    ('one_level_dev_1', 'save Xt.Rd:1'),
    ('two_level_dev_1', 'save Xt.X2.Mn:1'),
    ('two_level_dev_i', 'save Xt.X2.Mn:i'),
    ('two_level_iprobe', 'save Xt.X2.Ip2:i'),
    ('two_level_dev_all', 'save Xt.X2.Mn sigtype=all'),
    ('slash_form',      'save Xt/X2/Mn:1'),
    ('master_path',     'save lvl2/x2'),
]


def sh(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, u(p.communicate()[0])


def main():
    op = optparse.OptionParser()
    op.add_option('--scratch')
    o, _ = op.parse_args()
    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'sc1_sim', 'r2e_two_level')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    for name, saves in CANDS:
        deck = os.path.join(scratch, 'tl_%s.scs' % name)
        with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(DECK.format(lib='${QODER_PDK_LIB}', saves=saves)))
        rc, txt = sh('LABEL=TL bash %s %s 90 2>&1' % (os.path.join(HERE, 'run_spectre.sh'), deck))
        txt = txt.replace('\r', '')
        m = re.search(r'LOGFILE (\S+)', txt)
        log = m.group(1) if m else ''
        m = re.search(r"CHECK datafile='([^']*)'", txt)
        data = m.group(1) if m else ''
        trace = ''
        if data and os.path.isfile(data):
            _r2, trace = sh("awk '/^TRACE/,/^VALUE/' %s | tr -d '\\n' | cut -c1-220" % data)
        msgs = ''
        if log and os.path.isfile(log):
            _r3, msgs = sh("grep -E 'ERROR|WARNING' %s | head -3" % log)
        print('=== %-16s %s' % (name, saves))
        print('    run  : %s' % ('RUN_OK' if re.search(r'^TL: PASS$', txt, re.M) else 'RUN_FAIL'))
        print('    trace: %s' % trace.strip()[:220])
        print('    msg  : %s' % msgs.strip().replace('\n', ' / ')[:200])


if __name__ == '__main__':
    main()
