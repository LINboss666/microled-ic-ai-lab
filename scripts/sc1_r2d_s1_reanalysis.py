#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D/R2D1: re-read the ORIGINAL S1 waveforms with the audited tools. No simulation.

    python scripts/sc1_r2d_s1_reanalysis.py --sim-dir DIR --deck-dir DIR --out CSV \
            [--history-truth CSV --history-transient CSV --fault-raw F --fault-deck F --fault-history V]

Why this exists: S1 has historical PASS results, but they predate the fixed reader and delay tool and
the corrected tools have never looked at that data. This script reads the raw PSF-ASCII still on disk
-- never the old summary CSV as its input source -- and records the real signal values, sample counts,
windows and exit codes.

R2D1-C: reading a plausible output value is not the same as certifying the historical run, and the
first version of this script conflated them. The cloud reviewer fed it two DC raws whose BLANK was
0.7 V (a value that satisfies neither label), a transient raw carrying only time/en/q, no decks and no
history CSVs at all, and it still reported 10/10 PASS with every deck hash MISSING. So:

  * traceability, the assertion result, the stimulus check and the difference against history are four
    separate columns -- "the threshold still passes" is never reported as "the values agree";
  * a truth row must read back the stimulus its label names (blank and the swept qbar) inside the
    tolerance, otherwise the row is not evidence of anything;
  * a transient row must also read the states its window names (blank/q/qbar/d/clk); a missing or
    unreadable evidence signal makes the row incomplete, not green;
  * a reader exit code is never turned into a number: no parsing, no value, and the row records which
    signal refused it;
  * the independent awk cross-check participates in the verdict -- awk failure, zero samples in the
    window, or a reader/awk disagreement beyond the display tolerance all count against the row;
  * comparing against history needs a stated tolerance with a stated source: both sides are
    6-significant-digit text written by sc1_read_psf.py ("%.6g"), so the band is half a step at each
    end, max(1e-9, 1e-5*|value|);
  * a sample count that hits the probe ceiling is reported as a LOWER BOUND, not an exact n;
  * without decks, or without the history CSVs, the overall result is PARTIAL / NOT_VERIFIED -- the
    assertion-only case is called ASSERTION_CHECK_ONLY, and 10/10 is never printed.

Exit codes: 0 CERTIFIED (every row passed its assertion, its stimulus check, its cross-check, its deck
and history traceability, and agrees with history within the stated tolerance); 3 PARTIAL (something
was read, but certification is impossible from what is on disk); 1 FAIL (an assertion, stimulus check
or cross-check failed). All offline, no simulator: this is not a fresh regression and it does not
re-prove the golden C2MOS cell.

Decision level 0.9 V, the five windows and the four truth rows are the historical ones from
scripts/sc1_s1r.sh, kept identical on purpose so any difference means something.
"""
from __future__ import print_function
import csv, hashlib, io, math, optparse, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, 'sc1_read_psf.py')
VOL = 0.9                      # historical decision level, unchanged on purpose
N_PROBE_CEIL = 8192            # doubling ceiling of probe_n: reaching it is a lower bound, not an n
DISPLAY_SIGS = 6               # sc1_read_psf.py prints "%.6g"

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


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def display_half_step(v):
    """Half a step of sc1_read_psf.py's output format: it prints "%.6g", so the last displayed digit
    of a value 1.79991... is 1e-5 wide, and of 0.0753447 it is 1e-7 wide."""
    if not finite(v) or v == 0:
        return 1e-12
    return 0.5 * 10.0 ** (math.floor(math.log10(abs(v))) - (DISPLAY_SIGS - 1))


def tol_pair(hist_value, read_value):
    """Band for comparing a re-read value against the historical CSV: the history rows are 6-DECIMAL
    text (half a step = 5e-7, so 5.4e-9 legitimately prints as 0.000000) and the reader is 6-SIGNIFICANT
    digits. The provenance is stated in the tolerance column of every row, and "inside the band" is a
    statement about display precision -- it is not the same claim as "the threshold still passes"."""
    return HISTORY_DECIMAL_HALF_STEP + display_half_step(read_value) + 1e-12


HISTORY_DECIMAL_HALF_STEP = 5e-7

TOL_SOURCE = ('history CSV is 6-decimal text (half step %g); reader prints "%%.%dg" (half step '
              '0.5*10^(exp-5)); band = the two added' % (HISTORY_DECIMAL_HALF_STEP, DISPLAY_SIGS))


def read_value(data, extra_args):
    cmd = [sys.executable, READER, '--data', data] + extra_args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    return p.returncode, txt.strip()


def finite(x):
    return x is not None and x == x and not math.isinf(x)


def read_num(data, extra_args):
    """(value, rc, token). A non-zero reader exit never becomes a number."""
    rc, txt = read_value(data, extra_args)
    if rc != 0:
        return None, rc, txt.split('\n')[0]
    val = as_float(txt)
    if not finite(val):
        return None, 500, 'NOT_FINITE %s' % txt.split('\n')[0]
    return val, rc, txt.split('\n')[0]


def probe_n(data, value_args):
    """Largest --require-n K the reader accepts, and whether that number is exact.

    Doubling finds an upper bound that FAILS, then the answer is bisected between the last passing and
    the first failing K. If the doubling reaches the ceiling without ever failing, the count is only
    known to be AT LEAST that far -- reported as a lower bound instead of a false exact n.
    """
    def ok(k):
        return read_value(data, value_args + ['--require-n', str(k)])[0] == 0
    if not ok(1):
        return 0, 'none'
    lo, hi = 1, 2
    while hi <= N_PROBE_CEIL and ok(hi):
        lo, hi = hi, hi * 2
    if hi > N_PROBE_CEIL:
        return lo, 'lower_bound'
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo, 'exact'


def si(txt):
    txt = txt.strip()
    mult = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'M': 1e6}
    if txt and txt[-1] in mult:
        return float(txt[:-1]) * mult[txt[-1]]
    return float(txt)


def as_float(txt):
    try:
        return float(txt.split('\n')[0])
    except (ValueError, IndexError):
        return None


def judge(value, kind):
    if not finite(value):
        return 'NOT_MEASURED'
    return 'PASS' if ((value < VOL) if kind == 'lt' else (value > VOL)) else 'FAIL'


# transient windows exactly as scripts/sc1_s1r.sh measured them. The mode follows the assertion, not
# convenience: a "must stay above 0.9 V" check is only violated by the window MINIMUM, and a "must
# stay below" check by the maximum.
# The last field lists the states each window label names, as sig:mode:predicate, and is checked --
# an en number alone cannot show that the window was applied to the states it claims.
WINDOWS = [
    ('T1', 'T1_blank_high_while_Q1_en_low', 'en', '400n', '455n', 'max', 'lt',
     'T1 BLANK=1 while Q=1 : en must stay low',
     [('blank', 'max', 'ge'), ('q', 'max', 'ge'), ('qbar', 'max', 'le')]),
    ('T2', 'T2_blank_low_while_Q1_en_high', 'en', '520n', '620n', 'min', 'gt',
     'T2 BLANK=0 while Q=1 : en must be high',
     [('blank', 'min', 'le'), ('q', 'max', 'ge'), ('clk', 'max', 'ge')]),
    ('T3', 'T3_q_undisturbed_on_release', 'q', '410n', '520n', 'min', 'gt',
     'T3 q undisturbed across BLANK release',
     [('blank', 'max', 'ge'), ('qbar', 'max', 'le'), ('clk', 'max', 'ge')]),
    ('T4', 'T4_blank_low_while_Q0_en_low', 'en', '700n', '860n', 'max', 'lt',
     'T4 BLANK=0 while Q=0 : en must be low',
     [('blank', 'min', 'le'), ('q', 'max', 'le'), ('d', 'max', 'le')]),
    ('T5', 'T5_q_follows_falling_data_edge', 'q', '700n', '860n', 'max', 'lt',
     'T5 q follows the falling-data clock edge',
     [('blank', 'min', 'le'), ('qbar', 'max', 'ge'), ('clk', 'max', 'ge')]),
]

# (label, dc deck, blank source dc, swept qbar, expected state, historical (Q,BLANK) key)
TRUTH = [
    ('Q1_BLANK0_en_high', 's1r_dc_blank0',   0.0, 0.0, 'ON',  ('1', '0')),
    ('Q0_BLANK0_en_low',  's1r_dc_blank0',   0.0, 1.8, 'OFF', ('0', '0')),
    ('Q1_BLANK1_en_low',  's1r_dc_blank1.8', 1.8, 0.0, 'OFF', ('1', '1')),
    ('Q0_BLANK1_en_low',  's1r_dc_blank1.8', 1.8, 1.8, 'OFF', ('0', '1')),
]

HEADERS = ['case_id', 'kind', 'raw_file', 'raw_sha256', 'deck_file', 'deck_sha256', 'traceability',
           'window_or_sweep', 'decision_level_V', 'measured_value_V', 'samples_accepted_by_reader',
           'sample_count_kind', 'reader_rc', 'independent_awk_crosscheck', 'crosscheck_status',
           'assertion_verdict', 'stimulus_check', 'signals_read_back', 'historical_value_V',
           'historical_difference_V', 'tolerance_V', 'historical_agreement', 'row_status', 'labels',
           'note']

LABELS = 'HISTORICAL_DATA,OFFLINE_REREAD'


def awk_scan(path, axis, sig, lo, hi):
    """Group-aware second opinion, without the reader: PSF-ASCII VALUE blocks hold one group per
    sample -- the axis line first, then the signal lines -- so pairing them here is independent of
    the reader's own parsing. Returns a short 'awk_samples=.. awk_max=.. awk_min=..' summary."""
    prog = r'''
      /^VALUE/ { inv = 1; next }
      /^END/   { inv = 0 }
      inv && NF >= 2 {
        k = $1; gsub(/"/, "", k); v = $2 + 0
        if (k == ax) { t = v; havet = 1; next }
        if (k == sg && havet && t >= lo - 1e-15 && t <= hi + 1e-15) {
          n++; if (!have || v > mx) mx = v; if (!have || v < mn) mn = v; have = 1
        }
      }
      END { printf "awk_samples=%d", n + 0; if (have) printf " awk_max=%.9g awk_min=%.9g", mx, mn }'''
    p = subprocess.Popen(['awk', '-v', 'ax=%s' % axis, '-v', 'sg=%s' % sig,
                          '-v', 'lo=%g' % lo, '-v', 'hi=%g' % hi, prog, path],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    if p.returncode != 0:
        return 'awk_failed_rc%d' % p.returncode, 'AWK_FAILED'
    txt = txt.strip()
    if 'awk_samples=' not in txt:
        return (txt or 'awk_empty'), 'AWK_NO_OUTPUT'
    n = int(re.search(r'awk_samples=(\d+)', txt).group(1))
    if n == 0:
        return txt, 'AWK_ZERO_SAMPLES'
    if 'awk_max=' not in txt:
        return txt, 'AWK_NO_EXTREME'
    return txt, 'OK'


def awk_value(summary, which='min'):
    m = re.search(r'awk_%s=([-+0-9.eE]+)' % which, summary or '')
    return float(m.group(1)) if m else None


def crosscheck_agrees(read_val, summary, which='min'):
    """Reader vs awk on the same sample set, so a disagreement beyond the display band means one of
    the two is not looking at what we think."""
    a = awk_value(summary, which)
    if a is None or not finite(read_val):
        return 'NOT_COMPARABLE', a
    if abs(a - read_val) <= display_half_step(read_val) + display_half_step(a) + 1e-12:
        return 'AGREES', a
    return 'MISMATCH', a


def load_history_truth(path):
    """results/evidence/s1r_truth.csv: Q,BLANK,en_measured_V,... -> {(Q,BLANK): en}."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    with io.open(path, 'r', encoding='utf-8') as f:
        rows = list(csv.reader([l for l in f]))
    if not rows:
        return out
    hdr = rows[0]
    try:
        iq, ib, iv = hdr.index('Q'), hdr.index('BLANK'), hdr.index('en_measured_V')
    except ValueError:
        return out
    for r in rows[1:]:
        if len(r) > max(iq, ib, iv):
            out[(r[iq].strip(), r[ib].strip())] = r[iv].strip()
    return out


def load_history_windows(path):
    """results/evidence/s1r_transient.csv: check,worst_case_in_window_V,verdict -> {Tn: value}."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    with io.open(path, 'r', encoding='utf-8') as f:
        rows = list(csv.reader([l for l in f]))
    for r in rows[1:]:
        if len(r) < 2:
            continue
        m = re.match(r'\s*(T\d+)', r[0])
        if m:
            out[m.group(1)] = r[1].strip()
    return out


def main():
    op = optparse.OptionParser()
    for n in ('sim-dir', 'deck-dir', 'out', 'history-truth', 'history-transient',
              'fault-raw', 'fault-deck', 'fault-history'):
        op.add_option('--' + n)
    o, _ = op.parse_args()
    if not (o.sim_dir and o.deck_dir and o.out):
        print('USAGE: sc1_r2d_s1_reanalysis.py --sim-dir D --deck-dir D --out CSV '
              '[--history-truth C --history-transient C --fault-raw F --fault-deck F '
              '--fault-history V]')
        return 2
    hist_truth = load_history_truth(o.history_truth)
    hist_win = load_history_windows(o.history_transient)
    rows = []
    trace = []                        # traceability of what this run can actually certify

    def deck_hash(name):
        p = os.path.join(o.deck_dir, name)
        return sha256(p) if os.path.isfile(p) else 'MISSING'

    trace.append('history_truth=%s' % ('present' if hist_truth else 'ABSENT'))
    trace.append('history_transient=%s' % ('present' if hist_win else 'ABSENT'))
    if not (hist_truth and hist_win):
        trace.append('ASSERTION_CHECK_ONLY: no historical values to compare against, so agreement '
                     'with history cannot be claimed for any row')

    # ---- truth rows from the DC sweeps ---------------------------------------
    for (label, run, blank_v, qbar, expect, hkey) in TRUTH:
        raw = os.path.join(o.sim_dir, run + '.raw', 'sw.dc')
        dsha = deck_hash(run + '.scs')
        if not os.path.isfile(raw):
            rows.append([label, 'truth_row', run + '.raw/sw.dc', 'MISSING', run + '.scs', dsha,
                         'raw MISSING; deck ' + ('present' if dsha != 'MISSING' else 'MISSING'),
                         'sweep qbar=%g' % qbar, VOL, 'NOT_AVAILABLE', 0, 'none', 'NOT_RUN',
                         'not_read', 'NOT_READ', 'NOT_AVAILABLE', 'NOT_READ', 'not read',
                         hist_truth.get(hkey, ''), '', '', 'NO_HISTORY', 'INCOMPLETE', LABELS,
                         'raw PSF-ASCII not on disk'])
            continue
        # the swept source is qbar, so the row's own stimulus must read back at that point and the
        # blank source at its labelled dc value -- otherwise the row describes a different circuit
        en, en_rc, en_tok = read_num(raw, ['--sig', 'en', '--sweep', '%g' % qbar, '--mode', 'last'])
        got = None if not finite(en) else ('ON' if en > VOL else 'OFF')
        assertion = judge(en, 'gt' if expect == 'ON' else 'lt')
        reads = ['en=%s(rc=%s)' % (en_tok, en_rc)]
        st_rows, st_fail = [], 0
        for (sig, want) in (('blank', blank_v), ('qbar', qbar)):
            v, rc, tok = read_num(raw, ['--sig', sig, '--sweep', '%g' % qbar, '--mode', 'last'])
            reads.append('%s=%s(rc=%s)' % (sig, tok, rc))
            if not finite(v):
                st_rows.append('%s UNREADABLE' % sig)
                st_fail = 1
            elif abs(v - want) > tol_pair(want, v):
                st_rows.append('%s=%s but label says %g' % (sig, tok, want))
                st_fail = 1
            else:
                st_rows.append('%s=%s as labelled' % (sig, tok))
        stimulus = 'FAIL' if st_fail else 'PASS'
        n, nkind = (probe_n(raw, ['--sig', 'en', '--sweep', '%g' % qbar, '--mode', 'last'])
                    if finite(en) else (0, 'none'))
        xsum, xstat = awk_scan(raw, 'dc', 'en', qbar, qbar)
        agree, xval = crosscheck_agrees(en, xsum, 'max') if xstat == 'OK' else (xstat, None)
        xstatus = '%s reader_vs_awk=%s' % (xstat, agree)
        hist = hist_truth.get(hkey, '')
        diff, agreement = '', 'NO_HISTORY'
        if hist and finite(en):
            hv = as_float(hist)
            if hv is None:
                agreement = 'HISTORY_UNPARSABLE'
            else:
                diff = '%.6g' % abs(en - hv)
                agreement = ('WITHIN_TOLERANCE' if abs(en - hv) <= tol_pair(hv, en)
                             else 'OUTSIDE_TOLERANCE')
        row_status = 'PASS_ROW'
        if assertion != 'PASS' or stimulus == 'FAIL' or xstat != 'OK' or agree == 'MISMATCH':
            row_status = 'FAIL'
        elif (dsha == 'MISSING' or agreement in ('NO_HISTORY', 'OUTSIDE_TOLERANCE',
                                                 'HISTORY_UNPARSABLE') or nkind == 'lower_bound'
              or not finite(en)):
            row_status = 'NOT_CERTIFIED'
        trace.append('deck %s: %s' % (run + '.scs', 'present' if dsha != 'MISSING' else 'MISSING'))
        rows.append([label, 'truth_row', os.path.relpath(raw, o.sim_dir), sha256(raw),
                     run + '.scs', dsha,
                     'raw present, deck ' + ('present' if dsha != 'MISSING' else 'MISSING'),
                     'swept qbar=%g V at dc=%g V' % (qbar, qbar), VOL,
                     'NOT_MEASURED' if not finite(en) else '%.6g' % en, n, nkind,
                     'en rc=%s' % en_rc, xsum, xstatus, assertion, stimulus, ' ; '.join(reads),
                     hist, diff, ('%.6g' % tol_pair(as_float(hist), en))
                     if hist and as_float(hist) is not None else '', agreement, row_status, LABELS,
                     'the swept source is qbar, so the row is Q=%g as the historical table labels it;'
                     ' expected %s, read %s ; tolerance source: %s'
                     % (1.8 - qbar, expect, got, TOL_SOURCE)])

    # ---- the five transient windows -----------------------------------------
    raw = os.path.join(o.sim_dir, 's1r_dff.raw', 'sw1.tran.tran')
    for (tid, label, sig, t0, t1, mode, kind, desc, evidence) in WINDOWS:
        dsha = deck_hash('s1r_dff.scs')
        if not os.path.isfile(raw):
            rows.append([label, 'transient_window', 's1r_dff.raw/sw1.tran.tran', 'MISSING',
                         's1r_dff.scs', dsha, 'raw MISSING; deck '
                         + ('present' if dsha != 'MISSING' else 'MISSING'),
                         '%s..%s' % (t0, t1), VOL, 'NOT_AVAILABLE', 0, 'none', 'NOT_RUN',
                         'not_read', 'NOT_READ', 'NOT_AVAILABLE', 'NOT_READ', 'not read',
                         hist_win.get(tid, ''), '', '', 'NO_HISTORY', 'INCOMPLETE', LABELS, desc])
            continue
        args = ['--sig', sig, '--t0', t0, '--t1', t1, '--mode', mode]
        val, rc, tok = read_num(raw, args + ['--require-n', '3'])
        assertion = judge(val, kind)
        n, nkind = (probe_n(raw, args) if finite(val) else (0, 'none'))
        xsum, xstat = awk_scan(raw, 'time', sig, si(t0), si(t1))
        agree, _xv = crosscheck_agrees(val, xsum, mode) if xstat == 'OK' else (xstat, None)
        # the states the window label names have to be present in the same file and consistent with
        # that label; an en number alone cannot show which circuit state the window was applied to
        reads = ['%s=%s(rc=%s)' % (sig, tok, rc)]
        st_fail = 0
        for (esig, emode, pred) in evidence:
            ev, erc, etok = read_num(raw, ['--sig', esig, '--t0', t0, '--t1', t1,
                                           '--mode', emode])
            if not finite(ev):
                reads.append('%s=UNREADABLE(rc=%s,%s): %s' % (esig, erc, emode, etok[:40]))
            else:
                reads.append('%s=%s(rc=%s,%s)' % (esig, etok, erc, emode))
            if not finite(ev):
                st_fail = 1
            elif pred == 'ge' and ev < VOL:
                st_fail = 1
            elif pred == 'le' and ev > VOL:
                st_fail = 1
        stimulus = 'FAIL' if st_fail else 'PASS'
        hist = hist_win.get(tid, '')
        base = awk_value(xsum, mode)
        base = base if finite(base) else val     # history compares against the full-precision value
        diff, agreement = '', 'NO_HISTORY'
        if hist and finite(base):
            hv = as_float(hist)
            if hv is None:
                agreement = 'HISTORY_UNPARSABLE'
            else:
                diff = '%.6g' % abs(base - hv)
                agreement = ('WITHIN_TOLERANCE' if abs(base - hv) <= tol_pair(hv, base)
                             else 'OUTSIDE_TOLERANCE')
        row_status = 'PASS_ROW'
        if (assertion != 'PASS' or stimulus == 'FAIL' or xstat != 'OK'
                or agree == 'MISMATCH'):
            row_status = 'FAIL'
        elif (dsha == 'MISSING' or agreement in ('NO_HISTORY', 'OUTSIDE_TOLERANCE',
                                                 'HISTORY_UNPARSABLE') or nkind == 'lower_bound'
              or not finite(val)):
            row_status = 'NOT_CERTIFIED'
        trace.append('window %s evidence signals: %d read, %s'
                     % (tid, 1 + len(evidence), 'all consistent' if not st_fail else 'INCONSISTENT'))
        rows.append([label, 'transient_window', os.path.relpath(raw, o.sim_dir), sha256(raw),
                     's1r_dff.scs', dsha,
                     'raw present, deck ' + ('present' if dsha != 'MISSING' else 'MISSING'),
                     '%s..%s ns, mode=%s' % (t0, t1, mode), VOL,
                     'NOT_MEASURED' if not finite(val) else '%.6g' % val, n, nkind,
                     '%s rc=%s' % (sig, rc), xsum,
                     '%s reader_vs_awk=%s' % (xstat, agree), assertion, stimulus,
                     ' ; '.join(reads), hist, diff,
                     ('%.6g' % tol_pair(as_float(hist), base))
                     if hist and as_float(hist) is not None else '',
                     agreement, row_status, LABELS,
                     desc + ' ; assertion kept verbatim: %s %g V ; difference against history uses '
                     'the full-precision awk value ; %s' % (mode, VOL, TOL_SOURCE)])

    # ---- BLANK-clamped fault injection --------------------------------------
    fr = o.fault_raw or os.path.join(o.sim_dir, 's1r_fault_blank_clamped.raw', 'sw1.tran.tran')
    fd = o.fault_deck or os.path.join(o.deck_dir, 's1r_fault_blank_clamped.scs')
    fdeck_name = os.path.basename(fd)
    label = 'F1_blank_clamped_rejected_by_T1_assertion'
    hist_f = o.fault_history or ''
    if os.path.isfile(fr):
        args = ['--sig', 'en', '--t0', '400n', '--t1', '455n', '--mode', 'max']
        val, rc, tok = read_num(fr, args + ['--require-n', '3'])
        n, nkind = (probe_n(fr, args) if finite(val) else (0, 'none'))
        xsum, xstat = awk_scan(fr, 'time', 'en', si('400n'), si('455n'))
        agree, xval = crosscheck_agrees(val, xsum, 'max') if xstat == 'OK' else (xstat, None)
        # What makes this deck the fault is the WIRING: the gate's BLANK pin is tied to vss, while the
        # blank node itself is still driven by the historical PWL. So the stimulus check is (a) the deck
        # text really contains that rewire and (b) Q was 1 in the window -- the state the blank is
        # supposed to suppress. Checking the blank node for 0 V would describe a different fault (and
        # the first version of this row did exactly that, failing the real historical negative).
        ev, erc, etok = read_num(fr, ['--sig', 'q', '--t0', '400n', '--t1', '455n', '--mode', 'max'])
        rewired = 'MISSING_DECK'
        if os.path.isfile(fd):
            with io.open(fd, 'r', encoding='utf-8', errors='replace') as fh:
                rewired = ('YES' if re.search(r'X2\s*\(qbar\s+vss\s+en', u(fh.read())) else 'NO')
        stimulus = ('NOT_VERIFIABLE' if rewired == 'MISSING_DECK'
                    else 'FAIL' if rewired == 'NO'
                    else ('PASS' if (finite(ev) and ev > VOL and finite(val) and val > VOL)
                          else 'FAIL'))
        reads = ['en=%s(rc=%s)' % (tok, rc), 'q=%s(rc=%s,max)' % (etok, erc),
                 'gate blank pin tied to vss: %s' % rewired]
        base = xval if finite(xval) else val
        diff, agreement = '', 'NO_HISTORY'
        if hist_f and finite(base):
            hv = as_float(hist_f)
            diff = '%.6g' % abs(base - hv)
            agreement = ('WITHIN_TOLERANCE' if abs(base - hv) <= tol_pair(hv, base)
                         else 'OUTSIDE_TOLERANCE')
        assertion = ('NOT_MEASURED' if not finite(val)
                     else ('DETECTED' if val > VOL else 'NOT_DETECTED'))
        dsha = sha256(fd) if os.path.isfile(fd) else 'MISSING'
        row_status = 'PASS_ROW'
        # a missing deck is a lineage gap, not a circuit failure: the fault not being verifiable demotes
        # the row to NOT_CERTIFIED, while a fault that the unchanged T1 assertion accepts is a FAIL
        if assertion != 'DETECTED' or stimulus == 'FAIL' or xstat != 'OK' or agree == 'MISMATCH':
            row_status = 'FAIL'
        elif (stimulus == 'NOT_VERIFIABLE' or dsha == 'MISSING'
              or agreement in ('NO_HISTORY', 'OUTSIDE_TOLERANCE') or nkind == 'lower_bound'):
            row_status = 'NOT_CERTIFIED'
        trace.append('fault deck %s: %s' % (fdeck_name,
                                            'present' if dsha != 'MISSING' else 'MISSING'))
        rows.append([label, 'fault_injection', os.path.relpath(fr, o.sim_dir), sha256(fr),
                     fdeck_name, dsha,
                     'raw present, deck ' + ('present' if dsha != 'MISSING' else 'MISSING'),
                     '400n..455n ns, mode=max', VOL,
                     'NOT_MEASURED' if not finite(val) else '%.6g' % val, n, nkind,
                     'en rc=%s' % rc, xsum, '%s reader_vs_awk=%s' % (xstat, agree), assertion,
                     stimulus, ' ; '.join(reads), hist_f, diff,
                     ('%.6g' % tol_pair(as_float(hist_f), base))
                     if hist_f and as_float(hist_f) is not None else '',
                     agreement, row_status, LABELS,
                     'DETECTED means the unchanged T1 assertion rejected the faulted deck; no '
                     'threshold was moved to make that happen. The historical comparison value only '
                     'exists if --fault-history was supplied; it is not assumed'])
    else:
        rows.append([label, 'fault_injection', 's1r_fault_blank_clamped.raw/sw1.tran.tran',
                     'MISSING', fdeck_name, 'MISSING', 'raw MISSING; deck '
                     + ('present' if os.path.isfile(fd) else 'MISSING'),
                     '400n..455n', VOL, 'NOT_AVAILABLE', 0, 'none', 'NOT_RUN', 'not_read',
                     'NOT_READ', 'NOT_AVAILABLE', 'NOT_READ', 'not read', hist_f, '', '', 'NO_HISTORY',
                     'INCOMPLETE', LABELS,
                     'faulted run is not on disk; without the negative the checker is uncertified, '
                     'so the overall result cannot be CERTIFIED'])

    ragged = [(r[0], len(r)) for r in rows if len(r) != len(HEADERS)]
    if ragged:
        # the same discipline the CSV writer enforces in the bash entries: a row that does not match
        # the header is a harness bug, and it must stop the run instead of quietly shifting columns
        print('HARNESS_ERROR: rows with %d fields instead of %d: %s'
              % (ragged[0][1], len(HEADERS), ragged))
        return 4
    d = os.path.dirname(o.out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    overall = [u('')] * len(HEADERS)
    overall[0] = 'OVERALL'
    overall[1] = 'traceability'
    overall[HEADERS.index('traceability')] = ' | '.join(trace)
    overall[HEADERS.index('labels')] = LABELS
    overall[HEADERS.index('note')] = ('rows=%d; a row is only certified with deck+raw present, '
                                      'stimulus verified, cross-check agreeing and history within '
                                      'tolerance' % len(rows))
    with io.open(o.out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(HEADERS))
        for r in rows:
            f.write(csvline(r))
        f.write(csvline(overall))

    # read the column positions from HEADERS: hard-coded indices silently tracked the wrong column
    # when the historical_difference_V column was added
    i_st = HEADERS.index('stimulus_check')
    i_assert = HEADERS.index('assertion_verdict')
    i_row = HEADERS.index('row_status')
    i_samp = HEADERS.index('samples_accepted_by_reader')
    i_kind = HEADERS.index('sample_count_kind')
    i_hist = HEADERS.index('historical_agreement')
    i_val = HEADERS.index('measured_value_V')
    nfail = sum(1 for r in rows if r[i_row] == 'FAIL')
    ncert = sum(1 for r in rows if r[i_row] == 'PASS_ROW')
    nnas = sum(1 for r in rows if r[i_row] in ('INCOMPLETE', 'NOT_CERTIFIED'))
    if nfail:
        status, rc = 'FAIL', 1
    elif nnas or ncert != len(rows):
        status, rc = 'PARTIAL_NOT_VERIFIED', 3
    else:
        status, rc = 'CERTIFIED', 0
    print('S1_HISTORICAL_REANALYSIS: %s rows=%d certified_rows=%d incomplete=%d failing=%d'
          % (status, len(rows), ncert, nnas, nfail))
    print('  %s' % ' | '.join(trace))
    print('  a PARTIAL result means the re-read could not be certified from what is on disk (missing '
          'deck, missing history, unreadable stimulus evidence or a lower-bound sample count); it is '
          'not a claim that the historical data is wrong, and it is never reported as 10/10.')
    for r in rows:
        print('  %-34s %-16s %-13s n=%-6s(%s) assert=%-8s stim=%-6s hist=%-18s val=%s' %
              (r[0], r[1], r[i_row], r[i_samp], r[i_kind], r[i_assert], r[i_st], r[i_hist], r[i_val]))
    print('R2D_S1_CSV=%s   (offline re-read only; no simulator was called)' % o.out)
    return rc


if __name__ == '__main__':
    sys.exit(main())
