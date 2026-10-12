#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2A: offline self-test of the measurement tools and the supply contract checker.

    python scripts/sc1_r2a_selftest.py [--out results/evidence/sc1_r2a_checker.csv]

Runs with no simulator and no PDK: every case is a synthetic PSF-ASCII file or a synthetic
netlist. Positive numeric results are parsed out of the tool's own output and compared with a
tolerance -- the previous suite mostly asserted that a substring appeared, which cannot tell a
correct 0.800 ns from a spliced 3.570 ns.

Cases named *_regression reproduce a defect the reviewer measured on commit 41ffbf2.
"""
from __future__ import print_function
import csv, io, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, 'sc1_read_psf.py')
DELAY = os.path.join(HERE, 'sc1_delay.py')
AWK = os.path.join(HERE, 'sc1_supply_check.awk')
PY = sys.executable
TMP = tempfile.mkdtemp(prefix='sc1_r2a_')

results = []

# python 2.6 on the guest: io.open(..., encoding=...) returns a text stream that refuses byte
# strings, so every value handed to it has to be unicode there and plain str on python 3.
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


def psf(pairs, axis='time'):
    n = len(pairs[0][1])
    out = ['"PSFversion" "1.00"', 'SWEEP', '"%s" "sweep" PROP(' % axis, '"units" "s"', ')',
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


def call(tool, args, isawk=False):
    cmd = (['awk', '-f', tool] if isawk else [PY, tool]) + args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL if hasattr(subprocess, 'DEVNULL') else None)
    out = p.communicate()[0]
    return p.returncode, (out.decode('utf-8', 'replace') if isinstance(out, bytes) else out)


def num(text, key):
    m = re.search(re.escape(key) + r'=([+-]?[0-9.]+(?:[eE][+-]?\d+)?)', text)
    return float(m.group(1)) if m else None


def check(cid, desc, tool, args, exp_rc, asserts=None, expect_in=None,
          regression=False, isawk=False, stage='measure'):
    rc, out = call(tool, args, isawk)
    ok = (rc == exp_rc)
    detail = []
    if ok and expect_in is not None:
        ok = expect_in in out
        detail.append('token[%s]%s' % (expect_in.split()[0], 'ok' if ok else 'missing'))
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
                    'PASS' if ok else 'FAIL',
                    (out.strip().replace('\n', ' | ')[:400]), ';'.join(detail)])
    print('%-30s rc=%-2s(exp %-2s) %-4s  %s' % (cid, rc, exp_rc, 'PASS' if ok else 'FAIL',
                                                 (out.strip().splitlines() or [''])[-1][:88]))
    return ok


# ============================================================ R0-A event splicing
# reviewer's reproduced waveform: rise attempt collapses, second rise is the real one
splice = psf([('time', [0, 1e-9, 2e-9, 3e-9, 4e-9, 5e-9]),
              ('out', [0.0, 1.0, 0.0, 0.0, 3.3, 3.3])])
p_splice = write('splice.psf', splice)
check('r0a_splice_first_attempt', 'incomplete first attempt must not borrow the next end',
      DELAY, ['--data', p_splice, '--sig', 'out', '--vdd', '3.3', '--mode', 'edge',
              '--edge', 'rise', '--event', 'first_attempt'], 4, expect_in='NO_EDGE',
      regression=True)
check('r0a_splice_first_complete', 'second, complete rise is 0.800 ns',
      DELAY, ['--data', p_splice, '--sig', 'out', '--vdd', '3.3', '--mode', 'edge',
              '--edge', 'rise', '--event', 'first_complete'], 0,
      asserts=[('duration_ns', 0.800, 0.010)], regression=True)
# a legal single event still measured exactly: linear ramp 0->3.3 over 10 samples
ramp = psf([('time', [i * 1e-9 for i in range(12)]),
            ('out', [0.0, 0.33, 0.66, 0.99, 1.32, 1.65, 1.98, 2.31, 2.64, 2.97, 3.3, 3.3])])
p_ramp = write('ramp.psf', ramp)
check('r0a_single_rrise_numeric', 'linear ramp 10-90 % spans 8 of 10 ns',
      DELAY, ['--data', p_ramp, '--sig', 'out', '--vdd', '3.3', '--mode', 'edge',
              '--edge', 'rise'], 0, asserts=[('duration_ns', 8.0, 0.05)])
# two-sample edge: both thresholds inside one interval -> interpolate, never crash
p_two = write('two.psf', psf([('time', [0.0, 1e-9]), ('out', [0.0, 3.3])]))
check('r0a_two_sample_no_crash', '10 % and 90 % in one interval interpolates 0.800 ns',
      DELAY, ['--data', p_two, '--sig', 'out', '--vdd', '3.3', '--mode', 'edge',
              '--edge', 'rise'], 0,
      asserts=[('duration_ns', 0.800, 0.005), ('samples_in_edge', 0.0, 0.0)], regression=True)
p_flat = write('flat.psf', psf([('time', [i * 1e-9 for i in range(6)]),
                               ('vdd', [1.8] * 6)]))
check('r0a_flat_no_edge', 'a fixed rail reports no edge',
      DELAY, ['--data', p_flat, '--sig', 'vdd', '--vdd', '1.8', '--mode', 'edge',
              '--edge', 'fall'], 4, expect_in='NO_EDGE')
# ringing: overshoot then settle; steady window min/max must not be the global extremum
p_ring = write('ring.psf', psf([('time', [i * 1e-9 for i in range(10)]),
                                ('out', [0.0, 1.0, 2.5, 3.6, 3.0, 3.35, 3.28, 3.32, 3.30, 3.31])]))
check('r0a_ring_steady_window', 'settled uses the stated window, not the 3.6 V overshoot',
      DELAY, ['--data', p_ring, '--sig', 'out', '--mode', 'steady', '--t0', '5n', '--t1', '9n',
              '--require-n', '3'], 0, asserts=[('min', 3.28, 0.001), ('max', 3.35, 0.001)],
      regression=True)
check('r0a_steady_needs_window', 'steady without a window is refused',
      DELAY, ['--data', p_ring, '--sig', 'out', '--mode', 'steady'], 9,
      expect_in='requires an explicit')

# ============================================================ R0-B inverting propdelay
# reviewer's data: en rises through 50 % at 2.5 ns; out falls through 50 % at 4.5 ns
p_inv = write('inv.psf', psf([('time', [i * 1e-9 for i in range(10)]),
                              ('en', [0.0, 0.0, 0.0, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8]),
                              ('out', [3.3, 3.3, 3.3, 3.3, 3.3, 0.0, 0.0, 0.0, 0.0, 3.3])]))
check('r0b_inverting_2ns', 'en rise -> out fall is 2.0 ns',
      DELAY, ['--data', p_inv, '--mode', 'propdelay', '--sig-in', 'en', '--sig-out', 'out',
              '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'fall'],
      0, asserts=[('delay_ns', 2.0, 0.05), ('t_in', 2.5e-9, 1e-12),
                         ('t_out', 4.5e-9, 1e-12)], regression=True)
# same-direction query on an inverting chain: it does land on the later output rise, so the tool
# must hand back the 50 % number AND mark that an opposite-direction event answered sooner
check('r0b_same_dir_on_inverting_marked',
      'a same-direction pairing must flag the earlier opposite-direction response',
      DELAY, ['--data', p_inv, '--mode', 'propdelay', '--sig-in', 'en', '--sig-out', 'out',
              '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'rise', '--edge-out', 'rise'],
      0, asserts=[('delay_ns', 6.0, 0.05)], expect_in='earlier_opposite_event=YES')
p_noresp = write('noresp.psf', psf([('time', [i * 1e-9 for i in range(8)]),
                                    ('en', [0.0, 0.0, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8]),
                                    ('gate', [0.0] * 8)]))
check('r0b_missing_response', 'an input with no output response is NO_EDGE, not 0 ns',
      DELAY, ['--data', p_noresp, '--mode', 'propdelay', '--sig-in', 'en', '--sig-out', 'gate',
              '--edge-in', 'rise', '--edge-out', 'fall'], 4, expect_in='NO_EDGE')
p_same = write('same.psf', psf([('time', [i * 1e-9 for i in range(10)]),
                               ('a', [0.0, 0.0, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8, 1.8]),
                               ('b', [0.0, 0.0, 0.0, 3.3, 3.3, 3.3, 3.3, 3.3, 3.3, 3.3])]))
check('r0b_same_phase_1ns', 'non-inverting chain measured rise->rise',
      DELAY, ['--data', p_same, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
              '--edge-in', 'rise', '--edge-out', 'rise'], 0,
      asserts=[('delay_ns', 1.0, 0.05)], expect_in='earlier_opposite_event=no')
# the old callers pass a single --edge for both signals and mean same phase; that meaning must
# survive, otherwise every existing script silently changes what it measures.
check('r0b_legacy_single_edge_same_phase', 'one --edge still applies to input and output alike',
      DELAY, ['--data', p_same, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
              '--edge', 'rise'], 0, asserts=[('delay_ns', 1.0, 0.05)],
      expect_in='legacy_edge_interface=same_direction')
check('r0b_window_selects_event', 'window picks the second of two input events',
      DELAY, ['--data', p_same, '--mode', 'propdelay', '--sig-in', 'a', '--sig-out', 'b',
              '--edge-in', 'rise', '--edge-out', 'rise', '--t0', '6n', '--t1', '9n'],
      4, expect_in='NO_EDGE')
# the other inverting direction: a falling input must pair with a rising output, not with a fall
p_inv2 = write('inv2.psf', psf([('time', [i * 1e-9 for i in range(10)]),
                               ('en', [1.8, 1.8, 1.8, 1.8, 1.8, 0.0, 0.0, 0.0, 0.0, 1.8]),
                               ('out', [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 3.3, 3.3, 3.3])]))
check('r0b_inverting_fall_to_rise_2ns', 'en fall -> out rise is 2.0 ns, measured 50% to 50%',
      DELAY, ['--data', p_inv2, '--mode', 'propdelay', '--sig-in', 'en', '--sig-out', 'out',
              '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', 'fall', '--edge-out', 'rise'],
      0, asserts=[('delay_ns', 2.0, 0.05), ('t_in', 4.5e-9, 1e-12), ('t_out', 6.5e-9, 1e-12)])

# ============================================================ R0-C reader contracts
p_small = write('small.psf', psf([('time', [0.0, 1e-9]), ('en', [0.0, 1.8])]))
check('r0c_require_n_wholefile', 'require-n applies outside the window branch too',
      READER, ['--data', p_small, '--sig', 'en', '--mode', 'max', '--require-n', '100'],
      4, expect_in='TOO_FEW_SAMPLES', regression=True)
p_sweep3 = write('sweep3.psf', psf([('dc', [0.0, 0.9, 1.8]), ('en', [3.3, 1.8, 0.0])], axis='dc'))
check('r0c_require_n_sweep', 'require-n applies to a sweep point',
      READER, ['--data', p_sweep3, '--sig', 'en', '--sweep', '0', '--require-n', '5'],
      4, expect_in='TOO_FEW_SAMPLES', regression=True)
check('r0c_require_n_negative', 'a negative require-n is refused, not ignored',
      READER, ['--data', p_sweep3, '--sig', 'en', '--sweep', '0', '--require-n', '-3'],
      9, expect_in='BAD_USAGE', regression=True)
check('r0c_unknown_mode', 'an unknown mode is refused',
      READER, ['--data', p_sweep3, '--sig', 'en', '--mode', 'median'], 9, expect_in='BAD_USAGE')
p_badaxis = write('badaxis.psf', psf([('time', [0.0, 2e-9, 1e-9]), ('en', [0.0, 0.0, 1.8])]))
check('r0c_time_not_ordered', 'a scrambled time axis cannot support a window query',
      READER, ['--data', p_badaxis, '--sig', 'en', '--t0', '0', '--t1', '3n', '--mode', 'max'],
      8, expect_in='BAD_AXIS', regression=True)
check('r0c_sig_fig_precision_kept', '1.23 nA is not printed as zero',
      READER, ['--data', write('na.psf', psf([('time', [0.0, 1e-9]), ('i', [0.0, 1.23e-9])])),
               '--sig', 'i', '--mode', 'max'], 0, None, expect_in='1.23e-09', regression=True)
check('r0c_unknown_edge_word', 'an unknown edge name is refused by the delay tool',
      DELAY, ['--data', p_ramp, '--sig', 'out', '--vdd', '3.3', '--mode', 'edge',
              '--edge', 'rising'], 9, expect_in='BAD_USAGE')

check('r0c_reversed_window_delay', 'a window that ends before it starts is refused',
      DELAY, ['--data', p_ramp, '--sig', 'out', '--vdd', '3.3', '--mode', 'edge', '--edge', 'rise',
              '--t0', '3n', '--t1', '1n'], 5, expect_in='window reversed')
check('r0c_reversed_window_reader', 'the reader refuses the same reversed window',
      READER, ['--data', p_ramp, '--sig', 'out', '--mode', 'max', '--t0', '3n', '--t1', '1n'],
      5, expect_in='window reversed')
check('r0c_rail_not_finite', 'nan / inf / overflowing VDD is refused, never coerced',
      DELAY, ['--data', p_ramp, '--sig', 'out', '--vdd', '1e400', '--mode', 'edge'], 5,
      expect_in='finite')
check('r0c_rail_unit_suffix_refused', 'a rail written as 3V3 is not silently read as 3',
      DELAY, ['--data', p_ramp, '--sig', 'out', '--vdd', '3V3', '--mode', 'edge'], 5,
      expect_in='not a number')
check('r0c_missing_signal_argument', 'a mode that needs --sig without --sig is BAD_USAGE',
      DELAY, ['--data', p_ramp, '--vdd', '3.3', '--mode', 'edge'], 9, expect_in='BAD_USAGE')

# ============================================================ R1-B supply checker (structural)
DUT = ('subckt dut (in out vdd18 vdd33 vss)\n'
       '  mp (out in vdd33 vdd33) p33 l=350n w=5u\n'
       '  mn (out in vss vss) n33 l=350n w=5u\n'
       'ends dut\n'
       'subckt buf33 (in out vdd33 vss)\n'
       '  mpb (out in vdd33 vdd33) p33 l=350n w=8u\n'
       '  mnb (out in vss vss) n33 l=350n w=4u\n'
       'ends buf33\n'
       'subckt inv18 (in out vdd vss)\n'
       '  mpq (out in vdd vdd) p18 l=200n w=4u\n'
       '  mnq (out in vss vss) n18 l=200n w=2u\n'
       'ends inv18\n')
OK_DECK = write('ok.scs', "simulator lang=spectre insensitive=yes\n" + DUT + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
""")
check('r1b_dual_rail_ok', 'correct 1.8/3.3 dual supply accepted', AWK,
      ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0', OK_DECK], 0, expect_in='SUPPLY_RESULT PASS',
      isawk=True, stage='structure')
check('r1b_unknown_master', 'an instance whose master was never read must fail, not warn',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('bad.scs', open(OK_DECK).read() + 'Xbad (a b c d e) unknown_master\n')],
      1, expect_in='SUPPLY_FAIL', regression=True, isawk=True, stage='structure')
check('r1b_garbage_contract_value', 'vss=garbage is rejected, not coerced to 0',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=garbage', OK_DECK], 1,
      expect_in='not a finite number', regression=True, isawk=True, stage='structure')
check('r1b_vss_direct_node0', 'a vss port tied straight to node 0 is legitimate',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('n0.scs', DUT + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
X1 (in out vdd18 vdd33 0) dut
""")], 0, expect_in='SUPPLY_RESULT PASS', regression=True, isawk=True, stage='structure')
check('r1b_hier_leaf_buffers', 'a high-domain-only leaf must not be asked for vdd18',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('hier.scs', DUT + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X1 (in mid vdd18 vdd33 vss) dut
X2 (mid out vdd33 vss) buf33
""")], 0, expect_in='SUPPLY_RESULT PASS', regression=True, isawk=True, stage='structure')
check('r1b_mixed_masters_per_instance', 'core inv18 plus high-domain dut via per-master entries',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0 inv18.vdd=1.8',
            write('mix.scs', DUT + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X0 (en nb vdd18 vss) inv18
X1 (nb out vdd18 vdd33 vss) dut
""")], 0, expect_in='SUPPLY_RESULT PASS', isawk=True, stage='structure')
check('r1b_contract_value_with_unit', 'vdd18=1V8 is refused, not truncated to 1',
      AWK, ['-v', 'smap=vdd18=1V8 vdd33=3.3 vss=0', OK_DECK], 1,
      expect_in='not a finite number', isawk=True, stage='structure')
check('r1b_duplicate_conflicting_entry', 'the same port mapped to two voltages is refused',
      AWK, ['-v', 'smap=vdd18=1.8 vdd18=2.5 vdd33=3.3 vss=0', OK_DECK], 1,
      expect_in='duplicate contract entry vdd18 conflicts', regression=True,
      isawk=True, stage='structure')
check('r1b_empty_contract_entry', 'an empty contract cannot certify anything',
      AWK, ['-v', 'smap=', OK_DECK], 1, expect_in='empty or malformed contract',
      isawk=True, stage='structure')
check('r1b_uncovered_supply_port', 'a supply-like port outside the contract is refused',
      AWK, ['-v', 'smap=vdd18=1.8 vss=0', OK_DECK], 1, expect_in='not covered by the contract',
      isawk=True, stage='structure')
check('r1b_entry_matching_nothing', 'a contract entry used by nothing is a contract bug',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0 vdd9=9.0', OK_DECK], 1,
      expect_in='matches no instance port', isawk=True, stage='structure')
check('r1b_zero_instances', 'a contract over an empty deck must not pass',
      AWK, ['-v', 'smap=vdd18=1.8', write('empty.scs', 'simulator lang=spectre\n')], 1,
      expect_in='no top-level instance', isawk=True, stage='structure')
check('r1b_param_source_value', 'a rail driven through a parameter is resolved, not rejected',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('par.scs', DUT + """
parameters VIO=3.3
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=VIO
Vss (vss 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
""")], 0, expect_in='SUPPLY_RESULT PASS', isawk=True, stage='structure')
check('r1b_reversed_source_terminals', 'V(0,n)=-1.8 puts the rail at +1.8 V, so it is legal',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('pol.scs', DUT + """
V18 (0 vdd18) vsource dc=-1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
""")], 0, expect_in='SUPPLY_RESULT PASS', isawk=True, stage='structure')
# the same terminals wired the other way round really is a negative rail, and must be refused
check('r1b_negative_rail_refused', 'terminals swapped without flipping the sign gives -1.8 V',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('neg.scs', DUT + """
V18 (0 vdd18) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
""")], 1, expect_in='driven -1.8 V', regression=True, isawk=True, stage='structure')
check('r1b_two_sources_conflict', 'one rail driven to two different potentials is refused',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('conflict.scs', DUT + """
V18 (vdd18 0) vsource dc=1.8
V18b (vdd18 0) vsource dc=1.2
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
""")], 1, expect_in='driven to both', isawk=True, stage='structure')

# ---- true hierarchy: the supply of a DESCENDANT instance is resolved through the parent's ports ----
NEST = DUT + """subckt mid (in out vdd18 vdd33 vss)
  Xm1 (in nb vdd18 vss) inv18
  Xm2 (nb out vdd33 vss) buf33
ends mid
"""
check('r1b_descendant_supplies_resolved', 'child instances inside a subckt are audited via the parent rail',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0 inv18.vdd=1.8',
            write('nest.scs', "simulator lang=spectre insensitive=yes\n" + NEST + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Xm (in out vdd18 vdd33 vss) mid
""")], 0, expect_in='SUPPLY_RESULT PASS',
      asserts=[('top', 1, 0), ('descendants', 2, 0), ('internal', 0, 0)],
      isawk=True, stage='structure')
# a rail driven to the wrong value must be caught even when only a descendant touches it
check('r1b_descendant_wrong_rail_refused', 'a 2.5 V global vdd33 reaches the grandchild buffer',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0 inv18.vdd=1.8',
            write('nest_bad.scs', NEST + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=2.5
Vss (vss 0) vsource dc=0
Xm (in out vdd18 vdd33 vss) mid
""")], 1, expect_in='driven 2.5 V', regression=True, isawk=True, stage='structure')
# an internal supply node is not a rail preflight can certify: reported, counted, never skipped
check('r1b_internal_supply_reported', 'a descendant rail fed by an internal node is named, not hidden',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0 inv18.vdd=1.8',
            write('nest_int.scs', DUT + """subckt mid (in out vdd18 vss)
  reg (vcc33 in) res r=1k
  Xm1 (in nb vdd18 vss) inv18
  Xm2 (nb out vcc33 vss) buf33
ends mid
""" + """
V18 (vdd18 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Xm (in out vdd18 vss) mid
""")], 0, expect_in='SUPPLY_INTERNAL',
      asserts=[('internal', 1, 0)], isawk=True, stage='structure')
# the reviewer's ambiguity: a subckt-local net that shares a top-level rail's name
check('r1b_local_net_name_collision', 'a local net named like a global rail is refused, not guessed',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('collide.scs', DUT + """subckt mid (in out vdd18 vss)
  Xm2 (nb out vdd33 vss) buf33
  mp2 (nb in vdd33 vdd33) p33 l=350n w=8u
ends mid
""" + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Xm (in out vdd18 vss) mid
""")], 1, expect_in='refusing to guess', regression=True, isawk=True, stage='structure')
# a source tying two declared rails together contradicts the contract
check('r1b_rail_tie_contradiction', 'a 0 V source between 1.8 and 3.3 rails is refused',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('tie.scs', DUT + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vx (vdd18 vdd33) vsource dc=0
X1 (in out vdd18 vdd33 vss) dut
""")], 1, expect_in='forces', regression=True, isawk=True, stage='structure')
check('r1b_rail_tie_consistent', 'a tie whose offset matches the contract is accepted',
      AWK, ['-v', 'smap=vdd18=1.8 vdd33=3.3 vss=0',
            write('tie_ok.scs', DUT + """
V18 (vdd18 0) vsource dc=1.8
V33 (vdd33 0) vsource dc=3.3
Vss (vss 0) vsource dc=0
Vx (vdd33 vdd18) vsource dc=1.5
X1 (in out vdd18 vdd33 vss) dut
""")], 0, expect_in='SUPPLY_TIE_OK', isawk=True, stage='structure')


def csvline(vals):
    # python 2.6's csv module only emits byte strings, which cannot be written to the unicode text
    # stream the evidence files are opened with, so the quoting rules are applied here directly.
    return ','.join([u('"' + u(v).replace('"', '""') + '"') for v in vals]) + u('\n')


def main():
    out = None
    a = sys.argv[1:]
    if '--out' in a:
        out = a[a.index('--out') + 1]
    npass = sum(1 for r in results if r[6] == 'PASS')
    nreg = sum(1 for r in results if r[2] == 'regression')
    print('R2A_CHECKER_VALIDATION: %s (%d/%d cases, %d regression)'
          % ('PASS' if npass == len(results) else 'FAIL', npass, len(results), nreg))
    if out:
        d = os.path.dirname(out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(out, 'w', encoding='utf-8', newline='') as f:
            f.write(csvline(['case', 'description', 'kind', 'stage', 'expected_rc', 'actual_rc',
                             'verdict', 'output_evidence', 'numeric_evidence']))
            for r in results:
                f.write(csvline(r))
        print('R2A_CSV=%s rows=%d' % (out, len(results)))
    return 0 if npass == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
