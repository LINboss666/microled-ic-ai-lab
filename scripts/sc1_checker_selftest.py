# -*- coding: utf-8 -*-
#!/usr/bin/env python
"""SCAN-1 R0: offline self-test of sc1_read_psf.py and sc1_delay.py.

Runs entirely on synthetic PSF-ASCII files -- a DUT simulation is never the proof that the
measuring tool is correct. Emits a machine-readable CSV and a short transcript.

    python scripts/sc1_checker_selftest.py [--out results/evidence/sc1_r2_checker.csv]

Every case declares the expected exit code and, where the tool returns a number, the expected
value. Cases marked REGRESSION reproduce a defect the SCAN-1R2 review found in the previous
version, so their passing is meaningful.
"""
from __future__ import print_function
import io, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, 'sc1_read_psf.py')
DELAY = os.path.join(HERE, 'sc1_delay.py')
PY = sys.executable

# The guest runs python 2.6, where io.open(..., encoding=) yields a text stream that refuses byte
# strings, and the csv module only emits byte strings. Convert explicitly and quote by hand.
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
    return u(','.join([u('"' + u(v).replace('"', '""') + '"') for v in vals])) + u('\n')


def psf(signals, axis='time', header='tran'):
    """signals: (name, [values]) with equal lengths. Build a valid psfascii body."""
    n = len(signals[0][1])
    for name, v in signals:
        if len(v) != n:
            raise ValueError('test bug: ragged input for %s' % name)
    out = ['"PSFversion" "1.00"', '"analysis type" "%s"' % header, 'SWEEP',
           '"%s" "sweep" PROP(' % axis, '"units" "s"', ')', 'TRACE']
    for name, _ in signals:
        out.append('"%s" PROP()' % name)
    out.append('VALUE')
    for i in range(n):
        for name, v in signals:
            out.append('"%s" %.17e' % (name, v[i]))
    out.append('END')
    return '\n'.join(out) + '\n'


def raw(text_lines):
    return '\n'.join(text_lines) + '\n'


def run(tool, args):
    p = subprocess.Popen([PY, tool] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.communicate()[0]
    if isinstance(out, bytes):
        out = out.decode('utf-8', 'replace')
    return p.returncode, out.strip()


CASES = []


def case(name, tool, build, expect_rc=None, expect_in=None, regression=False, note=''):
    CASES.append((name, tool, build, expect_rc, expect_in, regression, note))


def series(values, step=1e-9):
    return [('time', [i * step for i in range(len(values))]), ('out', list(values))]

t = [0.0, 1e-9, 2e-9, 3e-9, 4e-9]
v = [0.0, 0.5, 1.0, 1.5, 1.8]

# ---------------------------------------------------------------- reader: positive
case('reader_point_basic', READER,
     lambda f: (['--data', f, '--sig', 'en', '--mode', 'last'],
                psf([('time', t), ('en', v)]), 0, '1.8'),
     note='last point of a 5-point transient')
case('reader_sweep_scientific', READER,
     lambda f: (['--data', f, '--sig', 'en', '--sweep', '2e-9'],
                psf([('dc', [0.0, 1e-9, 2e-9, 3e-9]), ('en', [0.0, 0.9, 1.8, 1.8])], axis='dc'), 0, '1.8'),
     note='scientific notation on the sweep point (the old qty() rejected 1e-6)')
case('reader_window_si_suffix', READER,
     lambda f: (['--data', f, '--sig', 'en', '--t0', '1n', '--t1', '3n', '--mode', 'max'],
                psf([('time', t), ('en', v)]), 0, '1.5'),
     note='SI suffix window bounds')
case('reader_negative_value', READER,
     lambda f: (['--data', f, '--sig', 'i', '--mode', 'min'],
                psf([('time', t), ('i', [-1e-6, -2.5e-6, -1e-7, 0.0, 3e-9])]), 0, '-2.5e-06'),
     note='negative current must survive')
case('reader_nanopere_no_round_to_zero', READER,
     lambda f: (['--data', f, '--sig', 'i', '--mode', 'max'],
                psf([('time', t), ('i', [0.0, 1.23e-9, 0.0, 0.0, 0.0])]), 0, '1.23e-09'),
     regression=True,
     note='6 decimals used to print this as 0.000000; must keep significant digits')
case('reader_hierarchical_name', READER,
     lambda f: (['--data', f, '--sig', 'X1:mpls:1', '--mode', 'max'],
                psf([('time', t), ('X1:mpls:1', [0.0, 1e-5, 2e-5, 1e-5, 0.0])]), 0, '2e-05'),
     note='hierarchical device terminal currents are legal signal names')

# ---------------------------------------------------------------- reader: negatives
case('reader_missing_file', READER,
     lambda f: (['--data', f + '.nope', '--sig', 'en'], None, 2, 'NO_DATA_FILE'))
case('reader_empty_file', READER,
     lambda f: (['--data', f, '--sig', 'en'], '', 2, 'NO_DATA_FILE'))
case('reader_unknown_signal', READER,
     lambda f: (['--data', f, '--sig', 'does_not_exist', '--t0', '0', '--t1', '4n'],
                psf([('time', t), ('en', v)]), 3, 'NO_SIGNAL'))
case('reader_empty_window', READER,
     lambda f: (['--data', f, '--sig', 'en', '--t0', '100n', '--t1', '200n'],
                psf([('time', t), ('en', v)]), 4, 'TOO_FEW_SAMPLES'))
case('reader_too_few_samples', READER,
     lambda f: (['--data', f, '--sig', 'en', '--t0', '0', '--t1', '1n', '--require-n', '9'],
                psf([('time', t), ('en', v)]), 4, 'TOO_FEW_SAMPLES'))
case('reader_nan_rejected', READER,
     lambda f: (['--data', f, '--sig', 'en', '--t0', '0', '--t1', '4n', '--mode', 'max'],
                raw(['SWEEP', '"time" "sweep" PROP(', ')', 'TRACE', 'VALUE',
                     '"time" 0.0', '"en" 0.0', '"time" 1e-9', '"en" nan',
                     '"time" 2e-9', '"en" 0.0', 'END']), 5, 'BAD_NUMERIC'),
     regression=True, note='old version reported window max 0 with rc=0 for 0,NaN,0')
case('reader_inf_rejected', READER,
     lambda f: (['--data', f, '--sig', 'en', '--mode', 'max'],
                raw(['SWEEP', '"time" "sweep" PROP(', ')', 'TRACE', 'VALUE',
                     '"time" 0.0', '"en" 1e999', 'END']), 5, 'BAD_NUMERIC'))
case('reader_illegal_token', READER,
     lambda f: (['--data', f, '--sig', 'en', '--mode', 'max'],
                raw(['SWEEP', '"time" "sweep" PROP(', ')', 'TRACE', 'VALUE',
                     '"time" 0.0', '"en" 0h5', 'END']), 5, 'BAD_NUMERIC'))
case('reader_truncated_group', READER,
     lambda f: (['--data', f, '--sig', 'en', '--mode', 'max'],
                raw(['SWEEP', '"time" "sweep" PROP(', ')', 'TRACE', 'VALUE',
                     '"time" 0.0', '"en" 1.0', '"time" 1e-9']), 7, 'TRUNCATED'),
     note='file ends mid-group')
case('reader_ragged_group', READER,
     lambda f: (['--data', f, '--sig', 'en', '--mode', 'max'],
                raw(['SWEEP', '"time" "sweep" PROP(', ')', 'TRACE', 'VALUE',
                     '"time" 0.0', '"en" 1.0', '"time" 1e-9', 'END']), 7, 'TRUNCATED'),
     note='second group is missing en -> would have desynchronised time against signal')
case('reader_value_before_axis', READER,
     lambda f: (['--data', f, '--sig', 'en'],
                raw(['SWEEP', '"time" "sweep" PROP(', ')', 'TRACE', 'VALUE',
                     '"en" 1.0', '"time" 0.0', 'END']), 8, 'BAD_AXIS'))

# ---------------------------------------------------------------- delay
ramp = [0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0]
tt = [i * 1e-9 for i in range(len(ramp))]


def scaled(seq, full):
    return [x * full for x in seq]


case('delay_rise_10_90', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--vdd', '1.0', '--mode', 'edge', '--edge', 'rise'],
                psf([('time', tt), ('out', scaled(ramp, 1.0))]), 0, 'duration_ns=8.000'))
case('delay_fall_not_previous_rise', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--vdd', '1.0', '--mode', 'edge', '--edge', 'fall',
                 '--t0', '12n', '--t1', '30n'],
                psf(series([0.0, 0.3, 0.6, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
                            1.0, 1.0, 1.0, 1.0, 1.0, 0.7, 0.4, 0.2, 0.05, 0.0])),
                0, 'EDGE fall'),
     regression=True, note='fall must not reuse the end of the preceding rise (194 ns bug)')
case('delay_flat_no_edge', DELAY,
     lambda f: (['--data', f, '--sig', 'vdd', '--vdd', '1.8', '--mode', 'edge', '--edge', 'fall'],
                psf([('time', tt), ('vdd', [1.8] * len(tt))]), 4, 'NO_EDGE'))
case('delay_window_selects_period', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--vdd', '1.0', '--mode', 'edge', '--edge', 'rise',
                 '--t0', '27n', '--t1', '34n'],
                psf(series([0.0] * 10 + [0.05, 0.5, 0.95, 1.0] + [1.0] * 6 +
                           [0.9, 0.5, 0.1, 0.0] + [0.0] * 4 + [0.05, 0.5, 0.95, 1.0] + [1.0] * 5)),
                0, 'duration_ns'),
     note='multiple periods: window picks exactly one event')
case('delay_partial_only_holds_low', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--vdd', '1.0', '--mode', 'edge', '--edge', 'rise',
                 '--t0', '0', '--t1', '12n'],
                psf([('time', [i * 1e-9 for i in range(20)]),
                     ('out', [0.0, 0.15, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3,
                              0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3])]), 4, 'NO_EDGE'),
     note='a partial 0->30 % excursion that then holds must not be reported as an edge. Renamed on '
          'R2A: it was called delay_partial_then_full but contains no second, complete transition -- '
          'the real double-event counterexample is r0a_splice_first_complete in sc1_r2a_selftest.py')
case('delay_nonmonotonic_axis', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--vdd', '1.0', '--mode', 'edge', '--edge', 'rise'],
                psf([('time', [0.0, 2e-9, 1e-9, 3e-9]), ('out', [0.0, 0.2, 0.5, 1.0])]), 8, 'BAD_AXIS'))
case('delay_steady_requires_window', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--mode', 'steady'],
                psf([('time', tt), ('out', ramp)]), 9, 'requires an explicit'),
     regression=True, note='settled must not be the global extremum of the waveform')
case('delay_steady_window_minmax', DELAY,
     lambda f: (['--data', f, '--sig', 'out', '--mode', 'steady', '--t0', '10n', '--t1', '12n', '--require-n', '3'],
                psf([('time', tt), ('out', [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
                                            0.9, 1.05, 0.98, 1.02, 0.99])]), 0, 'min=0.98'),
     note='ringing after the edge: steady min/max inside the window, not the 1.05 overshoot')
case('delay_propdelay_same_phase_legacy_edge', DELAY,
     lambda f: (['--data', f, '--sig-out', 'out', '--sig-in', 'en', '--vdd-in', '1.8',
                 '--vdd-out', '3.3', '--mode', 'propdelay', '--edge', 'rise'],
                psf([('time', [i * 1e-9 for i in range(30)]),
                     ('en', [0.0] * 5 + [0.9, 1.8] + [1.8] * 23),
                     ('out', [0.0] * 10 + [1.65, 3.3] + [3.3] * 18)]), 0, 'delay_ns=5.000'),
     note='input 50 % at t=5 ns, output 50 % at t=10 ns -> 5.000 ns. The case was named "10ns" '
          'while asserting 5 ns, and 10 ns is only the absolute arrival time, not the delay')
case('delay_signal_missing', DELAY,
     lambda f: (['--data', f, '--sig', 'absent', '--vdd', '1.0', '--mode', 'edge'],
                psf([('time', tt), ('out', ramp)]), 3, 'NO_SIGNAL'))


def main():
    out = None
    args = sys.argv[1:]
    if '--out' in args:
        out = args[args.index('--out') + 1]
    tmp = tempfile.mkdtemp(prefix='sc1_selftest_')
    rows = []
    npass = nfail = 0
    for (name, tool, build, exp_rc, exp_in, regr, note) in CASES:
        path = os.path.join(tmp, name + '.psf')
        try:
            res = build(path)
            if len(res) == 4:
                a, body, exp_rc, exp_in = res
            else:
                a, body = res
            with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(u(body) if body is not None else u('x'))
            if body is None:
                pass  # negative case that must not find the file
            rc, got = run(tool, a)
        except Exception as e:
            rc, got = 99, 'HARNESS EXCEPTION %s' % e
        ok = (rc == exp_rc) and (exp_in is None or exp_in in got)
        if ok:
            npass += 1
        else:
            nfail += 1
        rows.append([name, os.path.basename(tool), exp_rc, rc, 'PASS' if ok else 'FAIL',
                     (got[:400] if got else ''), 'YES' if regr else '', note])
        print('%-34s expect_rc=%-2s rc=%-2s %s  %s' % (name, exp_rc, rc,
                                                       'PASS' if ok else 'FAIL', got[:70]))
    print('CHECKER_VALIDATION: %s (%d/%d cases, %d regression cases)'
          % ('PASS' if nfail == 0 else 'FAIL', npass, npass + nfail,
             sum(1 for c in CASES if c[5])))
    if out:
        d = os.path.dirname(out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(csvline(['case', 'tool', 'expected_rc', 'actual_rc', 'verdict',
                             'output_evidence', 'regression_case', 'criterion']))
            for r in rows:
                f.write(csvline(r))
        print('CHECKER_CSV=%s' % out)
    return 0 if nfail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
