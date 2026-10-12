#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2C: numerical regression for the propdelay attribution boundary.

    python scripts/sc1_r2c_selftest.py --out FILE [--version-label L] [--casegen DIR]

Two holes in the R2B rule are closed here. attempts() only reports complete 10-90 % events, so an
input that moves back through its own 50 % level between two complete events produced NO bound at
all (case a1: the low plateau sits above the 10 % threshold, and the 12 ns borrow came back). And the
candidate filter looked at the output event's START, never at the 50 % point that is actually
reported, so a response that begins inside the window but is measured outside it was still certified
(case a2: window ends at 5.1 ns, t_out printed as 8.125 ns with rc 0).

The oracle below computes the next input 50 % crossing of either direction independently of the tool,
so the expectation is not "whatever the tool claims". Refused rows record NOT_MEASURED and keep the
tool's candidate number in the diagnostic column; no refused case is allowed to print
MEASUREMENT_VALID=YES, and "any non-zero rc" is never treated as a pass -- each row declares its
allowed exit-code set, the reason token and the validity flag.
"""
from __future__ import print_function
import io, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc1_r2c_casegen as G

DELAY = os.path.join(HERE, 'sc1_delay.py')
PY = sys.executable
TMP = tempfile_dir = None

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


def cross50(t, v, rail):
    """Independent oracle: every time the waveform crosses 0.5*rail in either direction.

    A sample that lands exactly on the level counts once, at the moment it is reached; the interval
    that leaves a plateau of such samples is not counted again. Deliberately conservative: a touch
    and return still forms a bound.
    """
    lvl = 0.5 * rail
    out = []
    i = 1
    n = len(v)
    while i < n:
        a, b = v[i - 1], v[i]
        if a == lvl and b != lvl:
            i += 1
            continue                      # the crossing was recorded when the level was reached
        if b == lvl:
            out.append(t[i])
        elif (a < lvl < b) or (b < lvl < a):
            out.append(t[i - 1] + (lvl - a) / (b - a) * (t[i] - t[i - 1]))
        i += 1
    return out


def get(text, key):
    m = re.search(re.escape(key) + r'=([+-]?[0-9.]+(?:[eE][+-]?\d+)?)', text)
    return float(m.group(1)) if m else None


results = []


def run_case(name, mode, allowed_rc, need_token, expect_valid, asserts, note, deckdir,
             extra_args=None, forbid=None):
    t, en, out_sig, ein, eout = G.CASES[name]
    deck = os.path.join(deckdir, name + '.psf')
    cmd = [PY, DELAY, '--data', deck, '--mode', 'propdelay', '--sig-in', 'en', '--sig-out', 'out',
           '--vdd-in', '1.8', '--vdd-out', '3.3', '--edge-in', ein, '--edge-out', eout]
    if mode == 'diagnose':
        cmd += ['--pairing', 'diagnose']
    if extra_args:
        cmd += extra_args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    rc = p.returncode

    t_in = get(text, 't_in')
    t_out = get(text, 't_out')
    delay = get(text, 'delay_ns')
    valid = 'MEASUREMENT_VALID=NO' if 'MEASUREMENT_VALID=NO' in text else (
        'MEASUREMENT_VALID=YES' if 'MEASUREMENT_VALID=YES' in text else 'absent')
    # oracle bound: the next input 50 % crossing after this event's own 50 % point
    crosses = sorted(cross50(t, en, 1.8))
    after = [c for c in crosses if (t_in is None or c > t_in + 1e-15)]
    t_next = after[0] if after else None

    ok = (rc in allowed_rc)
    why = []
    if ok and need_token and need_token not in text:
        ok = False
        why.append('token missing: %s' % need_token)
    for f in (forbid or []):
        if f in text:
            ok = False
            why.append('forbidden present: %s' % f)
    if ok and valid != expect_valid:
        ok = False
        why.append('validity %s want %s' % (valid, expect_valid))
    if ok:
        for key, want, tol in (asserts or []):
            got = {'t_in': t_in, 't_out': t_out, 'delay_ns': delay, 't_next': t_next}[key]
            if got is None:
                ok = False
                why.append('%s absent' % key)
            elif abs(got - want) > tol:
                ok = False
                why.append('%s=%.9g want %.9g +/- %.3g' % (key, got, want, tol))
    results.append([name, mode, VERSION, ','.join([str(x) for x in sorted(allowed_rc)]), rc,
                    need_token or '', valid,
                    '' if t_in is None else '%.6f' % (t_in * 1e9),
                    'NONE' if t_next is None else '%.6f' % (t_next * 1e9),
                    'NOT_MEASURED' if (mode == 'accept' and rc != 0) else
                    ('' if t_out is None else '%.6f' % (t_out * 1e9)),
                    'NOT_MEASURED' if (mode == 'accept' and rc != 0) else
                    ('' if delay is None else '%.6f' % delay),
                    '' if delay is None else '%.6f' % delay,
                    'PASS' if ok else 'FAIL', ';'.join(why), note])
    print('%-12s %-8s rc=%-2s exp %-6s valid=%-19s %s  t_next(oracle)=%s  %s'
          % (name, mode, rc, '/'.join([str(x) for x in sorted(allowed_rc)]), valid,
             'PASS' if ok else 'FAIL',
             'NONE' if t_next is None else '%.6f' % (t_next * 1e9), (text.strip().splitlines() or [''])[0][:64]))
    return ok


def main():
    global VERSION
    a = sys.argv[1:]
    out = a[a.index('--out') + 1] if '--out' in a else None
    VERSION = a[a.index('--version-label') + 1] if '--version-label' in a else 'unlabelled'
    if '--decks' not in a:
        print('USAGE: sc1_r2c_selftest.py --decks DIR --out FILE [--version-label L]')
        return 2
    deckdir = a[a.index('--decks') + 1]
    missing = [n for n in G.CASES if not os.path.isfile(os.path.join(deckdir, n + '.psf'))]
    if missing:
        print('HARNESS_ERROR missing decks: %s (run sc1_r2c_casegen.py --outdir %s)'
              % (','.join(missing), deckdir))
        return 8

    R4, R6, R0 = (4,), (6,), (0,)
    NO = 'MEASUREMENT_VALID=NO'
    YES = 'MEASUREMENT_VALID=YES'
    # 1) the two reviewer counterexamples, mirrored twins, and the boundary race: all refuse
    run_case('a1', 'accept', R4, 'OUTSIDE_ATTRIBUTION', NO,
             [('t_in', 2.5e-9, 1e-12)],
             'input falls back through 50 % at 5.642857 ns; 12 ns must not be certified',
             deckdir, forbid=['PROPDELAY'])
    run_case('a1_mirror', 'accept', R4, 'OUTSIDE_ATTRIBUTION', NO,
             [('t_in', 2.5e-9, 1e-12)],
             'mirrored polarity of a1 must refuse for the same reason',
             deckdir, forbid=['PROPDELAY'])
    run_case('a2', 'accept', R4, 'OUTSIDE_ATTRIBUTION', NO,
             [('t_in', 1.5e-9, 1e-12)],
             'output starts inside the window but its 50 % point (8.125 ns) is outside',
             deckdir, forbid=['PROPDELAY'])
    run_case('a2_mirror', 'accept', R4, 'OUTSIDE_ATTRIBUTION', NO,
             [('t_in', 1.5e-9, 1e-12), ('t_next', 5.5e-9, 1e-12)],
             'mirrored a2: the mirrored input falls through 50 % at 1.5 ns and rises again at '
             '5.5 ns, so a t_out of 8.125 ns cannot belong to event 1',
             deckdir, forbid=['PROPDELAY'])
    run_case('boundary', 'accept', R4, 'OUTSIDE_ATTRIBUTION', NO,
             [('t_in', 1.5e-9, 1e-12)],
             'output 50 % lands exactly on the next input 50 % crossing: not creditable to the '
             'earlier event', deckdir, forbid=['PROPDELAY'])
    run_case('r2b_two', 'accept', R4, None, NO,
             [('t_in', 2.5e-9, 1e-12)],
             'the R2B reviewer deck still refuses event 1 (complete fall event gives the bound)',
             deckdir, forbid=['PROPDELAY'])
    # 2) diagnostic mode may show the candidate but never claims validity
    run_case('a1', 'diagnose', R6, 'mode=diagnose', NO,
             [('delay_ns', 12.0, 0.02)],
             'diagnostic pairing of a1 stays non-zero and invalid', deckdir)
    run_case('r2b_two', 'diagnose', R6, 'mode=diagnose', NO,
             [('delay_ns', 12.0, 0.02)],
             'the R2B diagnostic row keeps rc 6 / MEASUREMENT_VALID=NO', deckdir)
    run_case('r2b_two', 'accept', R0, 'MEASUREMENT_VALID=YES', YES,
             [('t_in', 12.5e-9, 1e-12), ('t_out', 14.5e-9, 1e-12), ('delay_ns', 2.0, 0.02)],
             'selecting the event the waveform answers still measures 2.000 ns',
             deckdir, extra_args=['--in-event', 'second'])
    # 3) positives that prove the fix is not "refuse everything"
    run_case('a1_perturb', 'accept', R0, 'MEASUREMENT_VALID=YES', YES,
             [('t_in', 2.5e-9, 1e-12), ('t_out', 14.5e-9, 1e-12), ('delay_ns', 12.0, 0.02)],
             'a dip to 1.2 V never crosses the input 50 % level, so it is not a logic change and '
             'the first event remains measurable', deckdir)
    run_case('inside', 'accept', R0, 'MEASUREMENT_VALID=YES', YES,
             [('t_in', 1.5e-9, 1e-12), ('t_out', 10.125e-9, 1e-12), ('delay_ns', 8.625, 0.02)],
             'complete response measured at 10.125 ns, strictly before the input bound at 12.5 ns: '
             'certified', deckdir)

    npass = sum(1 for r in results if r[12] == 'PASS')   # column 13 is the verdict
    verdict = 'PASS' if npass == len(results) else 'FAIL'
    print('R2C_ATTRIBUTION_VALIDATION: %s (%d/%d cases, version=%s)'
          % (verdict, npass, len(results), VERSION))
    if out:
        d = os.path.dirname(out)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(csvline(['case_id', 'mode', 'tool_version', 'expected_rc_set', 'actual_rc',
                             'reason_token_expected', 'measurement_valid_actual', 't_in_ns',
                             't_next_ns_oracle', 't_out_ns', 'delay_ns',
                             'diagnostic_candidate_delay_ns', 'verdict', 'evidence_note',
                             'criterion']))
            for r in results:
                f.write(csvline(r))
        print('R2C_CSV=%s rows=%d' % (out, len(results)))
    return 0 if npass == len(results) else 1


VERSION = 'unlabelled'

if __name__ == '__main__':
    sys.exit(main())
