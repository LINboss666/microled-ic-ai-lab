#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D1-C: synthetic PSF-ASCII inputs for sc1_r2d1_reanalysis_selftest.py.

    python scripts/sc1_r2d1_reanalysis_casegen.py --outdir DIR

Standalone on purpose: importing it executes nothing, and it does not call a simulator. 1.8 V and the
ns values are POC_ASSUMPTION tool-test conditions.

The waveforms follow the STRUCTURE of the historical stimulus in scripts/sc1_s1r.sh -- clock pulsing
from 50 ns, data high 270..620 ns, blank high until 450 ns, and en = NOR(qbar, blank), which is the
S1 gate truth table -- so the five window labels name states that really are in the file. What these
numbers are NOT is a measurement: they are composed, at a 10 ns sample interval, to exercise the
re-analysis logic. Nothing here re-reads or replaces the historical S1 data.

History CSVs are generated from the same composed waveforms through a separate code path
(expected_* below), so a matching case proves the comparison machinery, not a tautology.
"""
from __future__ import print_function
import io
import os
import sys

try:
    _text = unicode
except NameError:
    _text = str

STEP_NS = 1     # the historical transient ran with maxstep=1n; a 10 ns grid cannot even see
              # the 450..460 ns release ramp that the T1 and T3 labels name
V18 = 1.8


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def times():
    return [i * STEP_NS * 1e-9 for i in range(0, 900 // STEP_NS + 1)]


def ns(t):
    return int(round(t * 1e9))


def pwl_eval(t_ns, points):
    """Linear interpolation of a `wave=[t v t v ...]` stimulus, exactly as vsource would produce it.

    The step approximation used before could not be compared against the frozen PWL: at 1 ns sampling
    the historical release ramps 1.8 V -> 0 V across 450..460 ns, and a step at 450 ns is a different
    stimulus. These breakpoints are copied from scripts/sc1_s1r.sh.
    """
    if t_ns <= points[0][0]:
        return points[0][1]
    for i in range(1, len(points)):
        if t_ns <= points[i][0]:
            t0, v0 = points[i - 1]
            t1, v1 = points[i]
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * (t_ns - t0) / (t1 - t0)
    return points[-1][1]


BLANK_POINTS = [(0, 1.8), (450, 1.8), (460, 0.0), (900, 0.0)]      # Vbl wave=[0 1.8 450n 1.8 460n 0 900n 0]
DATA_POINTS = [(0, 0.0), (260, 0.0), (270, 1.8), (620, 1.8), (630, 0.0), (900, 0.0)]


def expected_q(t):
    return V18 if 400 <= ns(t) <= 650 else 0.0


def expected_clk(t):
    # Vclk type=pulse val0=0 val1=1.8 delay=50n rise=1n fall=1n period=100n width=50n
    n = ns(t)
    if n < 50:
        return 0.0
    phase = (n - 50) % 100
    if phase < 1:
        return V18 * phase
    if phase < 50:
        return V18
    if phase < 51:
        return V18 * (51 - phase)
    return 0.0


def expected_d(t):
    return pwl_eval(ns(t), DATA_POINTS)


def expected_blank(t, faulted=False):
    if faulted:
        return 0.0
    return pwl_eval(ns(t), BLANK_POINTS)


def expected_en(t, faulted=False):
    qbar = V18 - expected_q(t)
    blank = expected_blank(t, faulted)
    return V18 if (qbar < 0.9 and blank < 0.9) else 0.0


def psf(pairs, axis='time'):
    n = len(pairs[0][1])
    out = ['"PSFversion" "1.00"', 'SWEEP', '"%s" "sweep" PROP(' % axis, '  "units" "s"', ')',
           'TRACE', 'VALUE']
    for i in range(n):
        for name, vals in pairs:
            out.append('"%s" %.17e' % (name, vals[i]))
    out.append('END')
    return '\n'.join(out) + '\n'


def write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(text))


def write_dc_runs(sim, blank_override=None):
    """Two DC sweep runs, axis 'dc' with the swept source qbar at 0 and 1.8 V."""
    blank_override = blank_override or {}
    for blank_v, run in ((0.0, 's1r_dc_blank0'), (V18, 's1r_dc_blank1.8')):
        b = blank_override.get(blank_v, blank_v)
        qbar = [0.0, V18]
        en = [V18 if (q < 0.9 and b < 0.9) else 0.0 for q in qbar]
        text = psf([('dc', [0.0, V18]), ('en', en), ('blank', [b, b]), ('qbar', qbar)], axis='dc')
        write(os.path.join(sim, run + '.raw', 'sw.dc'), text)
    return blank_override


def write_tran_run(sim, signals=None, fault=True, over=None):
    """The transient run, plus the BLANK-rewired negative unless the case drops it.

    `over` mutates individual signals of the NORMAL run (a constant or a function of the time in ns) so
    a self-test can express "the label says X, the recorded waveform says Y" without touching the decks,
    the history or the faulted run.
    """
    want = signals or ('en', 'blank', 'q', 'qbar', 'd', 'clk')
    ts = times()
    wave = {'time': ts, 'en': [expected_en(t) for t in ts],
            'blank': [expected_blank(t) for t in ts],
            'q': [expected_q(t) for t in ts],
            'qbar': [V18 - expected_q(t) for t in ts],
            'd': [expected_d(t) for t in ts],
            'clk': [expected_clk(t) for t in ts]}
    for name, fn in (over or {}).items():
        if name not in wave:
            raise ValueError('unknown signal %s' % name)
        wave[name] = ([fn(ns(t)) for t in ts] if callable(fn)
                      else [float(fn) for t in ts])
    order = ['time', 'en', 'blank', 'q', 'qbar', 'd', 'clk']
    chosen = [(name, wave[name]) for name in order if name == 'time' or name in want]
    write(os.path.join(sim, 's1r_dff.raw', 'sw1.tran.tran'), psf(chosen))
    if fault:
        fwave = dict(chosen)
        fwave['en'] = [expected_en(t, True) for t in ts]
        # the negative rewires the GATE'S BLANK PIN to vss; the blank NODE keeps its historical PWL,
        # exactly as the sed in scripts/sc1_s1r.sh left it. Zeroing the node here would describe a
        # different fault and would make the T1 stimulus check fail for the wrong reason.
        fwave['blank'] = [expected_blank(t, False) for t in ts]
        for name in ('q', 'qbar', 'd', 'clk', 'time'):
            fwave.setdefault(name, wave[name])
        fchosen = [(name, fwave[name]) for name in order if name in fwave]
        write(os.path.join(sim, 's1r_fault_blank_clamped.raw', 'sw1.tran.tran'), psf(fchosen))


def fault_history_value():
    """What the faulted run's en maximum in the T1 window is, from the composed waveform."""
    vals = [expected_en(t, True) for t in times() if 400 <= ns(t) <= 455]
    return '%.6g' % max(vals)


def window_worst(sig, t0, t1, mode):
    """Independent oracle for one window: computed straight from the waveform functions."""
    vals = []
    for t in times():
        if t0 <= ns(t) <= t1:
            if sig == 'en':
                vals.append(expected_en(t, False))
            elif sig == 'q':
                vals.append(expected_q(t))
            else:
                raise ValueError(sig)
    if not vals:
        raise ValueError('empty window')
    return max(vals) if mode == 'max' else min(vals)


def write_decks(dk):
    """Deck identities, including the line that makes the negative a real fault: the gate's BLANK pin
    tied to vss instead of to the blank node."""
    pins = {'s1r_dc_blank0': 'blank', 's1r_dc_blank1.8': 'blank', 's1r_dff': 'blank',
            's1r_fault_blank_clamped': 'vss'}
    for name, blankpin in sorted(pins.items()):
        # the negative differs from the positive in ONE line -- the gate's BLANK pin. The blank SOURCE
        # keeps its historical PWL, which is what the re-analysis has to see to accept the bench as the
        # T1 experiment at all.
        write(os.path.join(dk, name + '.scs'),
              'simulator lang=spectre insensitive=yes\n'
              '// synthetic deck identity for %s\n'
              'Vbl (blank 0) vsource type=pwl wave=[0 1.8 450n 1.8 460n 0 900n 0]\n'
              'X2 (qbar %s en vdd vss) sc1_scan_gate\n' % (name, blankpin))


def truth_history():
    """(Q, BLANK, en) as the composed DC runs would have reported them, 6 significant digits."""
    rows = []
    for blank_v, lab in ((0.0, '0'), (V18, '1')):
        for qbar in (0.0, V18):
            q = '1' if qbar == 0.0 else '0'
            en = V18 if (qbar < 0.9 and blank_v < 0.9) else 0.0
            rows.append((q, lab, '%.6g' % en))
    return rows


def write_history(truth_csv, transient_csv):
    lines = ['"Q","BLANK","en_measured_V","row_expected","assert_verdict"']
    for (q, b, en) in truth_history():
        lines.append('"%s","%s","%s","x","PASS"' % (q, b, en))
    write(truth_csv, '\n'.join(lines) + '\n')
    out = ['"check","worst_case_in_window_V","verdict"']
    for (tid, sig, t0, t1, mode) in (('T1', 'en', 400, 455, 'max'), ('T2', 'en', 520, 620, 'min'),
                                     ('T3', 'q', 410, 520, 'min'), ('T4', 'en', 700, 860, 'max'),
                                     ('T5', 'q', 700, 860, 'max')):
        out.append('"%s %.6g","%.6g","PASS"' % (tid, window_worst(sig, t0, t1, mode),
                                                window_worst(sig, t0, t1, mode)))
    write(transient_csv, '\n'.join(out) + '\n')


def main():
    argv = sys.argv[1:]
    if '--outdir' not in argv:
        print('USAGE: sc1_r2d1_reanalysis_casegen.py --outdir DIR')
        return 2
    out = argv[argv.index('--outdir') + 1]
    sim = os.path.join(out, 'sim')
    dk = os.path.join(out, 'deck')
    write_dc_runs(sim)
    write_tran_run(sim)
    write_decks(dk)
    write_history(os.path.join(out, 's1r_truth.csv'), os.path.join(out, 's1r_transient.csv'))
    print('R2D1_CASEGEN sim=%s deck=%s history=%s' % (sim, dk, out))
    print('R2D1_CASEGEN_STATUS: synthetic files only; no simulator, no historical data touched')
    return 0


if __name__ == '__main__':
    sys.exit(main())
