#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D2: the S1 transient window STATE contract, in one place.

    python scripts/sc1_s1_window_contract.py --data FILE --window T1 [--reader CMD] [--quiet]

Why this module exists: the future regression entry (scripts/sc1_s1_r2d_regression.sh) and the
historical re-analysis (scripts/sc1_r2d_s1_reanalysis.py) both needed to answer "were the states this
window's label names actually present?", and each had grown its own half-answer. Two reproduced holes:

  * the entry only asked whether an evidence signal could be READ. The reviewer set the T2 window's
    blank to 1.8 V -- T2 is defined as "BLANK=0 while Q=1" -- and the row still reported PASS with the
    whole run at rc 0, because nothing compared the value to the label.
  * the re-analysis judged a high state with the window MAXIMUM and a low state with the MINIMUM, which
    proves only that a value APPEARED once. With blank = 1.8 V at 410 ns and 0 V at every other sample,
    it still certified 10/10.

So a state is now judged over the whole window:

    high throughout  -> window MINIMUM must be above the decision level
    low  throughout  -> window MAXIMUM must be below it

and the two signals that are not constant inside their windows get stimulus-specific treatment:

    blank  compared sample by sample against the frozen historical PWL (it is defined to fall through
           0.9 V at 455 ns, so no single min/max can express it and no threshold may be quietly moved)
    clk    judged by its real transitions and legal high/low segments: the historical clock toggles
           every 100 ns, so "it was high once" says nothing about the stimulus being applied

Exit codes: 0 every check passed, 1 at least one state or assertion check failed, 2 the window or the
data file could not be evaluated at all (a harness problem, never reported as a circuit result).
Every check row carries the real reader exit code -- a refusal is recorded as rc 3 or 4, not flattened
to 1.

Nothing here is a simulator: the reads go through the audited scripts/sc1_read_psf.py, and the two
per-sample passes are small awk programs tied to THIS frozen stimulus, not a general PSF parser. The
supply/rail gate, the reader, the delay tool and the preflight are untouched.

Provenance of the numbers (labels per the repository rules):
  VOL = 0.9 V                  historical decision level from scripts/sc1_s1r.sh  (kept unchanged)
  stimulus breakpoints below   copied verbatim from scripts/sc1_s1r.sh            (HISTORICAL_STIMULUS)
  PWL_TOL = 0.09 V             POC_ASSUMPTION: half of one 1 ns sample step of the 1.8 V over 10 ns
                               release ramp at maxstep=1n -- 0.09 V is 10 % of the swing and stays far
                               from the 0.9 V threshold, while still catching a missing or misplaced
                               release edge (a whole-ramp plateau error is 1.8 V, orders of magnitude
                               larger)
  high/low comparison          strict > / < against VOL, the same sign convention as the historical
                               gt/lt assertions
"""
from __future__ import print_function

import os
import subprocess
import sys

VOL = 0.9
PWL_TOL = 0.09

# ---- the frozen transient stimulus, copied from scripts/sc1_s1r.sh ------------------------------
# Vbl (blank 0) vsource type=pwl wave=[0 1.8 450n 1.8 460n 0 900n 0]
BLANK_PWL = '0 1.8 450e-9 1.8 460e-9 0 900e-9 0'
# Vd  (d 0)     vsource type=pwl wave=[0 0 260n 0 270n 1.8 620n 1.8 630n 0 900n 0]
DATA_PWL = '0 0 260e-9 0 270e-9 1.8 620e-9 1.8 630e-9 0 900e-9 0'
# Vclk delay=50n rise=1n fall=1n period=100n width=50n -> rising edges at 50+100k ns, falling at 100+100k
CLK_RISE_FIRST = 50e-9
CLK_PERIOD = 100e-9
CLK_WIDTH = 50e-9

# ---- window definitions -------------------------------------------------------------------------
# out      : the historical output assertion (signal, mode, kind) -- unchanged, threshold not moved
# states   : whole-window state claims: (signal, 'high'|'low') -> min for high, max for low
# pwl      : signals compared sample by sample against a frozen PWL: (signal, breakpoint string)
# clk      : minimum (rises, falls) expected inside the window, derived from the frozen clock above
WINDOWS = {
    'T1': dict(t0='400n', t1='455n', out=('en', 'max', 'lt'),
               states=[('q', 'high'), ('qbar', 'low')],
               pwl=[('blank', BLANK_PWL)],
               clk=(1, 0),
               label='T1 BLANK=1 while Q=1 : en must stay low'),
    'T2': dict(t0='520n', t1='620n', out=('en', 'min', 'gt'),
               states=[('blank', 'low'), ('q', 'high'), ('qbar', 'low'), ('d', 'high')],
               pwl=[],
               clk=(1, 1),
               label='T2 BLANK=0 while Q=1 : en must be high'),
    'T3': dict(t0='410n', t1='520n', out=('q', 'min', 'gt'),
               states=[('qbar', 'low')],
               # the release event itself: blank must be high BEFORE and low AFTER, sample by sample
               pwl=[('blank', BLANK_PWL)],
               clk=(1, 1),
               label='T3 q undisturbed across BLANK release'),
    'T4': dict(t0='700n', t1='860n', out=('en', 'max', 'lt'),
               states=[('blank', 'low'), ('d', 'low'), ('q', 'low'), ('qbar', 'high')],
               pwl=[],
               clk=(1, 1),
               label='T4 BLANK=0 while Q=0 : en must be low'),
    'T5': dict(t0='700n', t1='860n', out=('q', 'max', 'lt'),
               states=[('blank', 'low'), ('qbar', 'high')],
               pwl=[],
               clk=(1, 1),
               label='T5 q follows the falling-data clock edge'),
}

TAB = '\t'


def _run(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    return p.returncode, txt.strip()


SI = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'meg': 1e6, 'g': 1e9}


def to_seconds(tok):
    """'400n' -> 4e-7. awk has no SI suffix support: handing it "400n" would compare against 400."""
    t = str(tok).strip()
    for suffix in ('meg', 'f', 'p', 'n', 'u', 'm', 'k', 'g'):
        if t.endswith(suffix):
            return float(t[:-len(suffix)]) * SI[suffix]
    return float(t)


def read_value(reader_cmd, data, args):
    """One read through the audited reader. The exit code is returned untouched."""
    cmd = reader_cmd.split(' ') + ['--data', data] + args
    return _run(cmd)


def _awk(prog, assigns, path):
    cmd = ['awk']
    for k, v in assigns:
        cmd += ['-v', '%s=%s' % (k, v)]
    cmd += [prog, path]
    rc, txt = _run(cmd)
    if rc != 0:
        return rc, 'awk_failed_rc%d' % rc
    return 0, txt


# an awk program shared by both per-sample checks: it walks the VALUE block group by group (the axis
# line first, then the signal lines), which is how PSF-ASCII stores one sample per group
_PWL_PROG = r'''
function expected(t,   i) {
  if (t <= T[1]) return V[1]
  for (i = 2; i <= NB; i++) {
    if (t <= T[i]) {
      if (T[i] == T[i-1]) return V[i]
      return V[i-1] + (V[i] - V[i-1]) * (t - T[i-1]) / (T[i] - T[i-1])
    }
  }
  return V[NB]
}
BEGIN { nb = split(bp, raw, " "); for (i = 1; i <= nb; i++) { j = int((i + 1) / 2); if (i % 2 == 1) { T[j] = raw[i] + 0 } else { V[j] = raw[i] + 0 } } NB = int(nb / 2); worst = -1 }
/^VALUE/ { inv = 1; next }
/^END/   { inv = 0 }
inv && NF >= 2 {
  k = $1; gsub(/"/, "", k); v = $2 + 0
  if (k == ax) { t = v; havet = 1 }
  else if (k == sg && havet && t >= lo - 1e-15 && t <= hi + 1e-15) {
    n++; e = expected(t); d = v - e; if (d < 0) d = -d
    if (d > tol) { bad++; if (bad == 1) { bt = t; bv = v; be = e } }
    if (d > worst) { worst = d; wt = t }
  }
}
END { printf "pwl_samples=%d pwl_violations=%d pwl_worst_diff=%.6g pwl_worst_t=%.6g", n + 0, bad + 0,
      worst, wt; if (bad) printf " first_bad_t=%.6g first_bad_value=%.6g first_bad_expected=%.6g",
      bt, bv, be }'''

_TRANS_PROG = r'''
/^VALUE/ { inv = 1; next }
/^END/   { inv = 0 }
inv && NF >= 2 {
  k = $1; gsub(/"/, "", k); v = $2 + 0
  if (k == ax) { t = v; havet = 1 }
  else if (k == sg && havet && t >= lo - 1e-15 && t <= hi + 1e-15) {
    n++
    if (have) { if (prev < lvl && v >= lvl) rise++; else if (prev >= lvl && v < lvl) fall++ }
    prev = v; have = 1
  }
}
END { printf "clk_samples=%d clk_rises=%d clk_falls=%d", n + 0, rise + 0, fall + 0 }'''


def pwl_check(data, sig, t0, t1, breakpoints, tol=PWL_TOL):
    rc, txt = _awk(_PWL_PROG, [('bp', breakpoints), ('ax', 'time'), ('sg', sig),
                               ('lo', '%.9e' % to_seconds(t0)), ('hi', '%.9e' % to_seconds(t1)),
                               ('tol', tol)], data)
    if rc != 0:
        return 'FAIL', txt, {'awk_rc': rc}
    fields = dict()
    for pair in txt.split(' '):
        if '=' in pair:
            k, v = pair.split('=', 1)
            fields[k] = v
    if int(fields.get('pwl_samples', 0) or 0) == 0:
        return 'FAIL', 'no samples of %s inside the window' % sig, fields
    if int(fields.get('pwl_violations', 0) or 0) > 0:
        return ('FAIL', '%s leaves the frozen PWL at %.9g s: read %.6g, stimulus says %.6g '
                       '(violations=%d, tol=%g)'
                % (sig, float(fields.get('first_bad_t', 0)), float(fields.get('first_bad_value', 0)),
                   float(fields.get('first_bad_expected', 0)),
                   int(fields['pwl_violations']), tol), fields)
    return 'PASS', '%s follows the frozen PWL (%d samples, worst diff %.6g <= %g)' % (
        sig, int(fields['pwl_samples']), float(fields.get('pwl_worst_diff', 0) or 0), tol), fields


def clk_check(data, sig, t0, t1, want):
    rc, txt = _awk(_TRANS_PROG, [('ax', 'time'), ('sg', sig), ('lo', '%.9e' % to_seconds(t0)),
                                 ('hi', '%.9e' % to_seconds(t1)), ('lvl', VOL)], data)
    if rc != 0:
        return 'FAIL', txt, {'awk_rc': rc}
    fields = dict()
    for pair in txt.split(' '):
        if '=' in pair:
            k, v = pair.split('=', 1)
            fields[k] = v
    rises = int(fields.get('clk_rises', 0) or 0)
    falls = int(fields.get('clk_falls', 0) or 0)
    if int(fields.get('clk_samples', 0) or 0) == 0:
        return 'FAIL', 'no clock samples inside the window', fields
    if rises < want[0] or falls < want[1]:
        # no wrapping parentheses here: `return 'FAIL', ('text' % args, fields)` builds a 2-tuple whose
        # second element is itself a tuple, and the caller unpacks three (this is the path a clock that
        # never falls takes)
        why = ('clock shows %d rise(s) and %d fall(s), the frozen pulse (delay=50n period=100n '
               'width=50n) requires >=%d/>=%d in this window' % (rises, falls, want[0], want[1]))
        return 'FAIL', why, fields
    return 'PASS', 'clock segments present (%d rises, %d falls)' % (rises, falls), fields


def state_check(reader_cmd, data, sig, t0, t1, claim):
    """A state is judged over the WHOLE window: high -> minimum, low -> maximum."""
    mode = 'min' if claim == 'high' else 'max'
    rc, txt = read_value(reader_cmd, data, ['--sig', sig, '--t0', t0, '--t1', t1, '--mode', mode,
                                            '--require-n', '3'])
    if rc != 0:
        return 'FAIL', '%s (%s) unreadable: rc=%d %s' % (sig, mode, rc, txt.split('\n')[0]), rc, txt
    try:
        v = float(txt.split('\n')[0])
    except ValueError:
        return 'FAIL', '%s (%s) returned a non-number %r' % (sig, mode, txt), rc, txt
    if v != v or v in (float('inf'), float('-inf')):
        return 'FAIL', '%s (%s) is not finite: %r' % (sig, mode, txt), rc, txt
    ok = (v > VOL) if claim == 'high' else (v < VOL)
    verdict = 'PASS' if ok else 'FAIL'
    return verdict, '%s %s throughout the window: %s(%s)=%.6g vs threshold %g V' % (
        sig, claim, mode, 'gt' if claim == 'high' else 'lt', v, VOL), rc, txt


def output_check(reader_cmd, data, t0, t1, out):
    sig, mode, kind = out
    rc, txt = read_value(reader_cmd, data, ['--sig', sig, '--t0', t0, '--t1', t1, '--mode', mode,
                                            '--require-n', '3'])
    if rc != 0:
        return 'FAIL', 'output %s (%s) unreadable: rc=%d %s' % (sig, mode, rc, txt.split('\n')[0]), rc
    try:
        v = float(txt.split('\n')[0])
    except ValueError:
        return 'FAIL', 'output %s returned a non-number %r' % (sig, txt), rc
    ok = (v < VOL) if kind == 'lt' else (v > VOL)
    return ('PASS' if ok else 'FAIL'), 'assertion %s(%s) %s %g V -> %.6g' % (
        sig, mode, kind, VOL, v), rc


def evaluate(data, window_id, reader_cmd=None, awk_capable=True):
    """Return (verdict, rows). rows are TAB-free lists: [window, kind, signal, rule, detail, rc, verdict]."""
    reader_cmd = reader_cmd or '%s %s' % (sys.executable,
                                          os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       'sc1_read_psf.py'))
    w = WINDOWS.get(window_id)
    rows = []
    if w is None:
        return 'FAIL', [[window_id, 'contract', '-', 'unknown window',
                         'no such window in the frozen contract', 'NOT_RUN', 'FAIL']]
    t0, t1 = w['t0'], w['t1']
    rows.append([window_id, 'output_assertion', w['out'][0],
                 '%s(%s) %s %g V' % (w['out'][0], w['out'][1], w['out'][2], VOL),
                 '', 'NOT_RUN', 'NOT_RUN'])
    rows.append([window_id, 'window', '-', '%s..%s' % (t0, t1), w['label'], '', ''])
    verdict = 'PASS'
    ov, odetail, orc = output_check(reader_cmd, data, t0, t1, w['out'])
    rows[0][4], rows[0][5], rows[0][6] = odetail, str(orc), ov
    if ov != 'PASS':
        verdict = 'FAIL'
    for (sig, claim) in w['states']:
        sv, detail, src, _txt = state_check(reader_cmd, data, sig, t0, t1, claim)
        rows.append([window_id, 'state_throughout', sig,
                     '%s over %s..%s must stay %s the %g V level' % (
                         'min' if claim == 'high' else 'max', t0, t1, 'above' if claim == 'high' else 'below',
                         VOL),
                     detail, str(src), sv])
        if sv != 'PASS':
            verdict = 'FAIL'
    for (sig, bp) in w['pwl']:
        pv, detail, _f = pwl_check(data, sig, t0, t1, bp)
        rows.append([window_id, 'stimulus_pwl', sig,
                     'every sample in %s..%s must follow the frozen PWL within %g V' % (t0, t1, PWL_TOL),
                     detail, 'awk', pv])
        if pv != 'PASS':
            verdict = 'FAIL'
    cv, cdetail, _f = clk_check(data, 'clk', t0, t1, w['clk'])
    rows.append([window_id, 'stimulus_clock', 'clk',
                 'at least %d rising and %d falling edge(s) inside the window' % w['clk'],
                 cdetail, 'awk', cv])
    if cv != 'PASS':
        verdict = 'FAIL'
    return verdict, rows


def main():
    argv = sys.argv[1:]

    def arg(name):
        return argv[argv.index(name) + 1] if name in argv else None
    data, window = arg('--data'), arg('--window')
    reader, quiet = arg('--reader'), ('--quiet' in argv)
    if not data or not window:
        print('USAGE: sc1_s1_window_contract.py --data FILE --window T1..T5 [--reader CMD] [--quiet]')
        return 2
    if not os.path.isfile(data):
        print('CONTRACT_HARNESS_ERROR data_missing:%s' % data)
        return 2
    verdict, rows = evaluate(data, window, reader_cmd=reader)
    if not quiet:
        # written to the binary stream with an explicit '\n': a Windows text-mode stdout translates
        # that to '\r\n', and the bash caller then carries a stray carriage return into its CSV field
        # (measured: the audited CSV writer split the row at the '\r' and reported 13 fields)
        lines = [TAB.join([str(x) for x in r]) for r in rows]
        lines.append('WINDOW_CONTRACT %s %s' % (window, verdict))
        text = '\n'.join(lines) + '\n'
        stream = getattr(sys.stdout, 'buffer', None)
        if stream is None:
            sys.stdout.write(text)
        else:
            stream.write(text.encode('utf-8'))
            stream.flush()
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
