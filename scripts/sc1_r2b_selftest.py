#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2B: regressions for the two functional holes found in b603820.

    python scripts/sc1_r2b_selftest.py [--out results/evidence/sc1_r2b_checker.csv]

A. propdelay attribution. Choosing "the first complete input event" then pairing it with ANY later
   output event let an unanswered first pulse borrow the second cycle's response: the reviewer's
   deck returned delay_ns=12.000 rc=0. A response may now only be credited to the selected input
   event while no further input crossing (either direction) has happened, the event is selectable,
   a same-direction pairing that the opposite direction beats is refused in acceptance mode, and a
   missing 50 % crossing fails instead of quoting the 10 % point.

B. Uncertified internal supply. A descendant supply port that resolves to an internal node used to
   be counted (SUPPLY_INTERNAL) and then passed. Counting is not checking: the same deck now
   refuses with SUPPLY_NOT_CERTIFIED / SUPPLY_FAIL, because a floating child substrate is precisely
   the accident this gate exists to catch.

Everything here is offline and synthetic: no simulator, no PDK, no DUT.
"""
from __future__ import print_function
import io, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DELAY = os.path.join(HERE, 'sc1_delay.py')
AWK = os.path.join(HERE, 'sc1_supply_check.awk')
PY = sys.executable
TMP = tempfile.mkdtemp(prefix='sc1_r2b_')

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


def csvline(vals):
    return u(','.join([u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in vals])) + u('\n')


def psf(pairs, axis='time'):
    n = len(pairs[0][1])
    out = ['"PSFversion" "1.00"', 'SWEEP', '"%s" "sweep" PROP(' % axis, '  "units" "s"', ')',
           'TRACE', 'VALUE']
    for i in range(n):
        for name, vals in pairs:
            out.append('"%s" %.17e' % (name, vals[i]))
    out.append('END')
    return '\n'.join(out) + '\n'


def write(name, text):
    p = os.path.join(TMP, name)
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(text))
    return p


def call(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL if hasattr(subprocess, 'DEVNULL') else None)
    out = p.communicate()[0]
    return p.returncode, (out.decode('utf-8', 'replace') if isinstance(out, bytes) else out)


def num(text, key):
    m = re.search(re.escape(key) + r'=([+-]?[0-9.]+(?:[eE][+-]?\d+)?)', text)
    return float(m.group(1)) if m else None


results = []


def check(cid, desc, cmd, exp_rc, asserts=None, tokens=None, forbidden=None,
          regression=False, stage='measure', note=''):
    rc, out = call(cmd)
    ok = (rc == exp_rc)
    detail = []
    if ok and tokens:
        for tk in tokens:
            if tk not in out:
                ok = False
                detail.append('token[%s]missing' % tk.split()[0])
    if ok and forbidden:
        for tk in forbidden:
            if tk in out:
                ok = False
                detail.append('forbidden[%s]present' % tk.split()[0])
    if ok and asserts:
        for key, want, tol in asserts:
            got = num(out, key)
            if got is None:
                ok = False
                detail.append('%s absent' % key)
            elif abs(got - want) > tol:
                ok = False
                detail.append('%s=%.6g want %.6g+/-%.3g' % (key, got, want, tol))
            else:
                detail.append('%s=%.6g ok' % (key, got))
    results.append([cid, desc, 'regression' if regression else '', stage, exp_rc, rc,
                    'PASS' if ok else 'FAIL', out.strip().replace('\n', ' | ')[:400],
                    ';'.join(detail), note])
    print('%-34s rc=%-2s(exp %-2s) %-4s  %s' % (cid, rc, exp_rc, 'PASS' if ok else 'FAIL',
                                                (out.strip().splitlines() or [''])[0][:84]))
    return ok


def awk(smap, deck):
    return ['awk', '-f', AWK, '-v', 'smap=' + smap, deck]


# =============================================== reviewer's two-input-event deck (problem A)
t = [i * 1e-9 for i in range(18)]
en = [0, 0, 0, 1.8, 1.8, 1.8, 0, 0, 0, 0, 0, 0, 0, 1.8, 1.8, 1.8, 1.8, 1.8]
o = [3.3] * 15 + [0, 0, 0]
p_ev = write('events.psf', psf([('time', t), ('en', en), ('out', o)]))
base = [PY, DELAY, '--data', p_ev, '--mode', 'propdelay', '--sig-in', 'en', '--sig-out', 'out',
        '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'fall',
        '--t0', '0', '--t1', '17n']

check('r2ba_first_event_unanswered_refused',
      'the first pulse has no response before the next input change: refuse',
      base, 4, tokens=['NO_RESPONSE'], forbidden=['delay_ns=12.000'], regression=True,
      note='b603820 returned rc=0 with delay_ns=12.000 by borrowing cycle 2')
check('r2ba_second_event_2ns',
      'explicitly selecting the second input event gives the real 2.000 ns',
      base + ['--in-event', 'second'], 0,
      asserts=[('delay_ns', 2.0, 0.05), ('t_in', 12.5e-9, 1e-12), ('t_out', 14.5e-9, 1e-12)],
      tokens=['MEASUREMENT_VALID=YES'], regression=True)
check('r2ba_event_index_out_of_range',
      'asking for an event that does not exist is a refusal, not a guess',
      base + ['--in-event', '3'], 4, tokens=['only 2 complete rise event'])
check('r2ba_diagnose_mode_never_valid',
      'the informational pairing is still printable but marked invalid and non-zero',
      base + ['--pairing', 'diagnose'], 6,
      asserts=[('delay_ns', 12.0, 0.05)], tokens=['MEASUREMENT_VALID=NO', 'mode=diagnose'])
check('r2ba_bad_pairing_word_refused', 'an unknown --pairing value is BAD_USAGE',
      base + ['--pairing', 'best'], 9, tokens=['BAD_USAGE'])
check('r2ba_bad_in_event_word_refused', 'an unknown --in-event value is BAD_USAGE',
      base + ['--in-event', 'later'], 9, tokens=['BAD_USAGE'])

# the 10 % and 50 % points are deliberately far apart: if the tool ever fell back to the 10 % point,
# t_in would read 3.0e-10 and delay 4.2 ns instead of the values asserted here
p_mid = write('mid.psf', psf([('time', [i * 1e-9 for i in range(9)]),
                             ('a', [0.0, 0.6, 1.2, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8]),
                             ('b', [3.3, 3.3, 3.3, 3.3, 3.3, 3.3, 0.0, 0.0, 0.0])]))
check('r2ba_timing_reference_is_50pct',
      't_in is the interpolated 50 % crossing (1.5 ns), not the 10 % point (0.3 ns)',
      [PY, DELAY, '--data', p_mid, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
       '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'fall'], 0,
      asserts=[('t_in', 1.5e-9, 1e-12), ('t_out', 5.5e-9, 1e-12), ('delay_ns', 4.0, 0.02)],
      tokens=['MEASUREMENT_VALID=YES'], regression=True)

# two samples only: both edges live in the same interval, so their order is unresolvable. Reporting
# 0.000 ns would be a fabricated measurement and NO_RESPONSE would be the wrong diagnosis.
p_coarse = write('coarse.psf', psf([('time', [0.0, 4e-9]),
                                    ('a', [0.0, 1.8]), ('b', [0.0, 3.3])]))
check('r2ba_coarse_sampling_ambiguous',
      'one sample interval cannot order input against output: AMBIGUOUS_RESOLUTION, non-zero',
      [PY, DELAY, '--data', p_coarse, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
       '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'rise'], 6,
      tokens=['AMBIGUOUS_RESOLUTION', 'MEASUREMENT_VALID=NO'],
      forbidden=['PROPDELAY', 'NO_RESPONSE'])

# two cycles, each answered inside its own window: attribution must accept both and keep them apart
p_two = write('two_ok.psf', psf([('time', [i * 1e-9 for i in range(14)]),
                                ('a', [0, 0, 1.8, 1.8, 1.8, 0, 0, 0, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8]),
                                ('b', [3.3, 3.3, 3.3, 0, 0, 0, 3.3, 3.3, 3.3, 3.3, 0, 0, 0, 0])]))
check('r2ba_first_of_two_answered_events',
      'cycle 1 is answered inside its own window: 1.000 ns at event 1',
      [PY, DELAY, '--data', p_two, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
       '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'fall'], 0,
      asserts=[('delay_ns', 1.0, 0.05), ('event', 1, 0), ('t_in', 1.5e-9, 1e-12),
               ('t_out', 2.5e-9, 1e-12)], tokens=['MEASUREMENT_VALID=YES'])
check('r2ba_second_of_two_answered_events',
      'the same deck at input event 2 answers 2.000 ns, not the first cycle',
      [PY, DELAY, '--data', p_two, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
       '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'fall',
       '--in-event', 'second'], 0,
      asserts=[('delay_ns', 2.0, 0.05), ('event', 2, 0), ('t_in', 7.5e-9, 1e-12),
               ('t_out', 9.5e-9, 1e-12)])

# ================================================ internal supply decks (problem B)
LEAF = ('subckt leaf (in out vdd33 vss)\n'
        '  mp (out in vdd33 vdd33) p33 l=350n w=5u\n'
        '  mn (out in vss vss) n33 l=350n w=5u\n'
        'ends leaf\n')
SRC = ('V18 (vdd18 0) vsource dc=1.8\n'
       'V33 (vdd33 0) vsource dc=3.3\n'
       'Vss (vss 0) vsource dc=0\n')

d_float = write('float_child_ground.scs', "simulator lang=spectre insensitive=yes\n" + LEAF + """
subckt top (in out vdd18 vdd33 vss)
  Xchild (in out vdd33 floating_ground) leaf
ends top
""" + SRC + """
X1 (in out vdd18 vdd33 vss) top
sw1 tran stop=1.5n maxstep=0.5n
""")
check('r2bb_floating_child_ground_refused',
      "the reviewer's deck: a child vss on an internal node is not certified",
      awk('vdd18=1.8 vdd33=3.3 vss=0', d_float), 1,
      tokens=['SUPPLY_NOT_CERTIFIED', 'is not certified', 'SUPPLY_RESULT FAIL'],
      forbidden=['SUPPLY_RESULT PASS'], regression=True, stage='structure',
      note='b603820 counted internal=1 and still printed SUPPLY_RESULT PASS')

d_mapped = write('mapped_child.scs', "simulator lang=spectre insensitive=yes\n" + LEAF + """
subckt top (in out vdd18 vdd33 vss)
  Xchild (in out vdd33 vss) leaf
ends top
""" + SRC + """
X1 (in out vdd18 vdd33 vss) top
sw1 tran stop=1.5n maxstep=0.5n
""")
check('r2bb_parent_port_mapping_certified',
      'the same deck with the child tied to the parent vss port passes',
      awk('vdd18=1.8 vdd33=3.3 vss=0', d_mapped), 0,
      tokens=['SUPPLY_RESULT PASS'],
      asserts=[('descendants', 1, 0), ('checked', 5, 0), ('internal', 0, 0)],
      regression=True, stage='structure')

d_int_vdd = write('internal_vdd.scs', "simulator lang=spectre insensitive=yes\n" + LEAF + """
subckt top (in out vdd18 vdd33 vss)
  Xchild (in out derived_vdd vss) leaf
  rdrop (derived_vdd vdd33) res r=1k
ends top
""" + SRC + """
X1 (in out vdd18 vdd33 vss) top
sw1 tran stop=1.5n maxstep=0.5n
""")
check('r2bb_internal_vdd_refused',
      'a child rail derived on an internal node is refused, not noted',
      awk('vdd18=1.8 vdd33=3.3 vss=0', d_int_vdd), 1,
      tokens=['SUPPLY_NOT_CERTIFIED', 'SUPPLY_RESULT FAIL'], regression=True, stage='structure')

d_two = write('two_level.scs', "simulator lang=spectre insensitive=yes\n" + LEAF + """
subckt midc (in out vdd33 vss)
  Xm1 (in nb vdd33 floatg) leaf
  Xm2 (nb out vdd33 vss) leaf
ends midc
""" + SRC + """
X1 (in out vdd33 vss) midc
sw1 tran stop=1.5n maxstep=0.5n
""")
check('r2bb_two_level_deep_refused',
      'two levels deep: a grandchild on a mid-level internal node refuses',
      awk('vdd33=3.3 vss=0', d_two), 1,
      tokens=['SUPPLY_NOT_CERTIFIED', 'X1.Xm1'],
      asserts=[('descendants', 2, 0)], regression=True, stage='structure')

d_two_ok = write('two_level_ok.scs', "simulator lang=spectre insensitive=yes\n" + LEAF + """
subckt midc (in out vdd33 vss)
  Xm1 (in nb vdd33 vss) leaf
  Xm2 (nb out vdd33 vss) leaf
ends midc
""" + SRC + """
X1 (in out vdd33 vss) midc
sw1 tran stop=1.5n maxstep=0.5n
""")
check('r2bb_two_level_certified',
      'the same depth with every supply port wired through is accepted',
      awk('vdd33=3.3 vss=0', d_two_ok), 0,
      tokens=['SUPPLY_RESULT PASS'], asserts=[('descendants', 2, 0), ('checked', 6, 0),
                                              ('internal', 0, 0)],
      regression=True, stage='structure')

d_node0 = write('child_node0.scs', "simulator lang=spectre insensitive=yes\n" + LEAF + """
subckt top (in out vdd18 vdd33 vss)
  Xchild (in out vdd33 0) leaf
ends top
""" + SRC + """
X1 (in out vdd18 vdd33 vss) top
sw1 tran stop=1.5n maxstep=0.5n
""")
check('r2bb_child_reference_node0_ok',
      'a child reference tied straight to node 0 is a legal 0 V reference',
      awk('vdd18=1.8 vdd33=3.3 vss=0', d_node0), 0, tokens=['SUPPLY_RESULT PASS'],
      stage='structure')

# The same refusal is also driven through the shared preflight wrapper, as matrix row n13 in
# sc1_preflight_selftest.sh: that deck must live inside the project tree, and the wrapper only
# accepts netlists under $PROJ, so it is tested there rather than from a temporary directory here.


def main():
    out = None
    a = sys.argv[1:]
    if '--out' in a:
        out = a[a.index('--out') + 1]
    npass = sum(1 for r in results if r[6] == 'PASS')
    nreg = sum(1 for r in results if r[2] == 'regression')
    print('R2B_CHECKER_VALIDATION: %s (%d/%d cases, %d regression)'
          % ('PASS' if npass == len(results) else 'FAIL', npass, len(results), nreg))
    if out:
        d = os.path.dirname(out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(csvline(['case', 'description', 'kind', 'stage', 'expected_rc', 'actual_rc',
                             'verdict', 'output_evidence', 'numeric_evidence', 'note']))
            for r in results:
                f.write(csvline(r))
        print('R2B_CSV=%s rows=%d' % (out, len(results)))
    return 0 if npass == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
