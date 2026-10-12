#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D: re-read the ORIGINAL S1 waveforms with the audited tools. No simulation.

    python scripts/sc1_r2d_s1_reanalysis.py --sim-dir DIR --deck-dir DIR --out CSV \
            [--history-truth CSV --history-transient CSV --fault-raw F --fault-deck F]

Why this exists: S1 has historical PASS results, but they predate the fixed reader and delay tool and
the corrected tools have never looked at that data. This script reads the raw PSF-ASCII of the runs
still on disk -- never the old summary CSV as its input source -- records the real signal values,
sample counts, windows and exit codes, and only then compares against the historical summary in a
separate column. Success is S1_HISTORICAL_REANALYSIS: it is not a fresh regression, and it does not
re-prove the golden C2MOS cell.

Sample counts come from the audited reader itself: --require-n is probed (doubling then bisecting)
until the read refuses, so the reported n is what the tool actually accepted, without modifying it.

Decision level 0.9 V, the five windows and the four truth rows are the historical ones from
scripts/sc1_s1r.sh, kept identical on purpose so any difference means something.
"""
from __future__ import print_function
import csv, hashlib, io, optparse, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, 'sc1_read_psf.py')
VOL = 0.9                      # historical decision level, unchanged on purpose

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


def read_value(data, extra_args):
    cmd = [sys.executable, READER, '--data', data] + extra_args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    return p.returncode, txt.strip()


def probe_n(data, value_args):
    """Largest --require-n K the reader accepts for this read: the sample count it really saw.

    Doubling finds an upper bound that FAILS, then the answer is bisected between the last passing
    and the first failing K. Bisecting from the last passing value alone returns that value and
    under-reports the count -- an early version of this function reported 128 where the raw window
    holds 157 samples.
    """
    def ok(k):
        return read_value(data, value_args + ['--require-n', str(k)])[0] == 0
    if not ok(1):
        return 0
    lo, hi = 1, 2
    while hi <= 8192 and ok(hi):
        lo, hi = hi, hi * 2
    if hi > 8192:                       # never found a failing bound: report the proven floor
        return lo
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo


def si(txt):
    txt = txt.strip()
    mult = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'M': 1e6}
    if txt and txt[-1] in mult:
        return float(txt[:-1]) * mult[txt[-1]]
    return float(txt)


def awk_val(crosscheck, mode):
    """Full-precision value from the awk cross-check, so the comparison against history is not
    dominated by the reader's 6-significant-digit display."""
    m = re.search(r'awk_%s=([-+0-9.eE]+)' % ('max' if mode == 'max' else 'min'), crosscheck or '')
    return float(m.group(1)) if m else None


def as_float(txt):
    try:
        return float(txt.split('\n')[0])
    except (ValueError, IndexError):
        return None


def judge(value, kind):
    if value is None:
        return 'FAIL', None
    return (('PASS' if value < VOL else 'FAIL') if kind == 'lt'
            else ('PASS' if value > VOL else 'FAIL')), value


# transient windows exactly as scripts/sc1_s1r.sh measured them. The mode follows the assertion, not
# convenience: a "must stay above 0.9 V" check is only violated by the window MINIMUM, and a "must
# stay below" check by the maximum. Using max for a gt assertion (an early draft did that for T2)
# compares against the wrong sample and cannot reproduce the historical worst case.
WINDOWS = [
    ('T1', 'T1_blank_high_while_Q1_en_low', 'en', '400n', '455n', 'max', 'lt',
     'T1 BLANK=1 while Q=1 : en must stay low'),
    ('T2', 'T2_blank_low_while_Q1_en_high', 'en', '520n', '620n', 'min', 'gt',
     'T2 BLANK=0 while Q=1 : en must be high'),
    ('T3', 'T3_q_undisturbed_on_release', 'q', '410n', '520n', 'min', 'gt',
     'T3 q undisturbed across BLANK release'),
    ('T4', 'T4_blank_low_while_Q0_en_low', 'en', '700n', '860n', 'max', 'lt',
     'T4 BLANK=0 while Q=0 : en must be low'),
    ('T5', 'T5_q_follows_falling_data_edge', 'q', '700n', '860n', 'max', 'lt',
     'T5 q follows the falling-data clock edge'),
]

# (label, dc deck, blank source dc, swept qbar, expected state, historical (Q,BLANK) key)
TRUTH = [
    ('Q1_BLANK0_en_high', 's1r_dc_blank0',   0.0, 0.0, 'ON',  ('1', '0')),
    ('Q0_BLANK0_en_low',  's1r_dc_blank0',   0.0, 1.8, 'OFF', ('0', '0')),
    ('Q1_BLANK1_en_low',  's1r_dc_blank1.8', 1.8, 0.0, 'OFF', ('1', '1')),
    ('Q0_BLANK1_en_low',  's1r_dc_blank1.8', 1.8, 1.8, 'OFF', ('0', '1')),
]

HEADERS = ['case_id', 'kind', 'raw_file', 'raw_sha256', 'deck_file', 'deck_sha256',
           'signals_read_back', 'window_or_sweep', 'decision_level_V', 'measured_value_V',
           'samples_accepted_by_reader', 'independent_awk_crosscheck', 'reader_rc', 'verdict',
           'historical_value_V', 'abs_difference_V', 'labels', 'note']


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
        return 'awk_failed_rc%d' % p.returncode
    return txt.strip()

LABELS = 'HISTORICAL_DATA,OFFLINE_REREAD'


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
              'fault-raw', 'fault-deck'):
        op.add_option('--' + n)
    o, _ = op.parse_args()
    if not (o.sim_dir and o.deck_dir and o.out):
        print('USAGE: sc1_r2d_s1_reanalysis.py --sim-dir D --deck-dir D --out CSV '
              '[--history-truth C --history-transient C --fault-raw F --fault-deck F]')
        return 2
    hist_truth = load_history_truth(o.history_truth)
    hist_win = load_history_windows(o.history_transient)
    rows = []

    def deck_hash(name):
        p = os.path.join(o.deck_dir, name)
        return sha256(p) if os.path.isfile(p) else 'MISSING'

    # ---- truth rows from the DC sweeps ---------------------------------------
    for (label, run, blank_v, qbar, expect, hkey) in TRUTH:
        raw = os.path.join(o.sim_dir, run + '.raw', 'sw.dc')
        if not os.path.isfile(raw):
            rows.append([label, 'truth_row', run + '.raw/sw.dc', 'MISSING', run + '.scs',
                         deck_hash(run + '.scs'), 'en,blank,qbar', 'sweep qbar=%g' % qbar, VOL,
                         'NOT_AVAILABLE', 0, 'not_read', 'NOT_RUN', 'NOT_AVAILABLE',
                         hist_truth.get(hkey, ''),
                         '', LABELS, 'raw PSF-ASCII not on disk'])
            continue
        vals, rcs = {}, []
        for sig in ('en', 'blank', 'qbar'):
            rc, txt = read_value(raw, ['--sig', sig, '--sweep', '%g' % qbar, '--mode', 'last'])
            vals[sig] = txt
            rcs.append('%s=%s' % (sig, rc))
        en = as_float(vals['en'])
        n = probe_n(raw, ['--sig', 'en', '--sweep', '%g' % qbar, '--mode', 'last'])
        got = None if en is None else ('ON' if en > VOL else 'OFF')
        verdict = 'FAIL' if got is None else ('PASS' if got == expect else 'FAIL')
        hist = hist_truth.get(hkey, '')
        diff = '' if (en is None or not hist) else '%.6g' % abs(en - float(hist))
        rows.append([label, 'truth_row', os.path.relpath(raw, o.sim_dir), sha256(raw),
                     run + '.scs', deck_hash(run + '.scs'),
                     ' ; '.join('%s=%s' % (k, v) for k, v in sorted(vals.items())),
                     'swept qbar=%g V at dc=%g V' % (qbar, qbar), VOL,
                     'NOT_MEASURED' if en is None else '%.6g' % en, n,
                     awk_scan(raw, 'dc', 'en', qbar, qbar), ','.join(rcs), verdict,
                     hist, diff, LABELS,
                     'the swept source is qbar, so the row is Q=%g as the historical table labels it;'
                     ' expected %s, read %s' % (1.8 - qbar, expect, got)])

    # ---- the five transient windows -----------------------------------------
    raw = os.path.join(o.sim_dir, 's1r_dff.raw', 'sw1.tran.tran')
    for (tid, label, sig, t0, t1, mode, kind, desc) in WINDOWS:
        if not os.path.isfile(raw):
            rows.append([label, 'transient_window', 's1r_dff.raw/sw1.tran.tran', 'MISSING',
                         's1r_dff.scs', deck_hash('s1r_dff.scs'), sig, '%s..%s' % (t0, t1), VOL,
                         'NOT_AVAILABLE', 0, 'not_read', 'NOT_RUN', 'NOT_AVAILABLE',
                         hist_win.get(tid, ''), '',
                         LABELS, desc])
            continue
        args = ['--sig', sig, '--t0', t0, '--t1', t1, '--mode', mode]
        rc, txt = read_value(raw, args + ['--require-n', '3'])
        n = probe_n(raw, args)
        val = as_float(txt)
        verdict, value = judge(val, kind)
        hist = hist_win.get(tid, '')
        full = awk_val(awk_scan(raw, 'time', sig, si(t0), si(t1)), mode)
        base = full if full is not None else value
        diff = '' if (base is None or not hist) else '%.6g' % abs(base - float(hist))
        rows.append([label, 'transient_window', os.path.relpath(raw, o.sim_dir), sha256(raw),
                     's1r_dff.scs', deck_hash('s1r_dff.scs'),
                     '%s=%s' % (sig, txt.replace('\n', ' | ')[:60]),
                     '%s..%s ns, mode=%s' % (t0, t1, mode), VOL,
                     'NOT_MEASURED' if value is None else '%.6g' % value, n,
                     awk_scan(raw, 'time', sig, si(t0), si(t1)), str(rc), verdict, hist, diff,
                     LABELS, desc + ' ; assertion kept verbatim: %s %g V ; difference against '
                     'history uses the full-precision awk value (the reader prints 6 significant '
                     'digits)' ])

    # ---- BLANK-clamped fault injection --------------------------------------
    fr = o.fault_raw or os.path.join(o.sim_dir, 's1r_fault_blank_clamped.raw', 'sw1.tran.tran')
    fd = o.fault_deck or os.path.join(o.deck_dir, 's1r_fault_blank_clamped.scs')
    label = 'F1_blank_clamped_rejected_by_T1_assertion'
    if os.path.isfile(fr):
        args = ['--sig', 'en', '--t0', '400n', '--t1', '455n', '--mode', 'max']
        rc, txt = read_value(fr, args + ['--require-n', '3'])
        n = probe_n(fr, args)
        xchk = awk_scan(fr, 'time', 'en', si('400n'), si('455n'))
        full = awk_val(xchk, 'max')
        val = as_float(txt)
        verdict = 'FAIL' if val is None else ('DETECTED' if val > VOL else 'NOT_DETECTED')
        rows.append([label, 'fault_injection', os.path.relpath(fr, o.sim_dir), sha256(fr),
                     os.path.basename(fd), sha256(fd) if os.path.isfile(fd) else 'MISSING',
                     'en=%s' % txt.replace('\n', ' | ')[:60], '400n..455n ns, mode=max', VOL,
                     'NOT_MEASURED' if val is None else '%.6g' % val, n, xchk, str(rc), verdict,
                     '1.800096', '' if full is None else '%.6g' % abs(full - 1.800096), LABELS,
                     'DETECTED means the unchanged T1 assertion rejected the faulted deck; no '
                     'threshold was moved to make that happen'])
    else:
        rows.append([label, 'fault_injection', 's1r_fault_blank_clamped.raw/sw1.tran.tran',
                     'MISSING', os.path.basename(fd), 'MISSING', 'en', '400n..455n', VOL,
                     'NOT_AVAILABLE', 0, 'not_read', 'NOT_RUN', 'NOT_AVAILABLE', '1.800096', '',
                     LABELS,
                     'faulted run is not on disk; nothing is claimed for it'])

    d = os.path.dirname(o.out)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(o.out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(HEADERS))
        for r in rows:
            f.write(csvline(r))
    good = ('PASS', 'DETECTED')
    npass = sum(1 for r in rows if r[13] in good)
    nna = sum(1 for r in rows if r[13] == 'NOT_AVAILABLE')
    print('R2D_S1_REANALYSIS rows=%d pass_or_detected=%d not_available=%d -> %s'
          % (len(rows), npass, nna,
             'PASS' if npass == len(rows) else ('PARTIAL' if npass else 'FAIL')))
    for r in rows:
        print('  %-34s %-16s %-13s n=%-5s %-28s val=%s hist=%s' %
              (r[0], r[1], r[13], r[10], r[11], r[9], r[14]))
    print('R2D_S1_CSV=%s' % o.out)
    return 0 if npass == len(rows) else 1


if __name__ == '__main__':
    sys.exit(main())
