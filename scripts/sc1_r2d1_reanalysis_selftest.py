#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D1-C: prove the re-analysis cannot certify without lineage. Synthetic only.

    python scripts/sc1_r2d1_reanalysis_selftest.py [--out CSV]

The cloud reviewer showed that the first version of sc1_r2d_s1_reanalysis.py returned rc=0 and
"rows 10 pass_or_detected 10 PASS" while every deck hash was MISSING, with two DC raws whose BLANK
was 0.7 V (satisfying neither row label), a transient raw carrying only time/en/q, and no history CSV
at all. That is the hole this self-test closes, with the four case families the review asked for and
nothing beyond them -- it is not a general PSF parser project.

Every input here is a SYNTHETIC PSF-ASCII file written by scripts/sc1_r2d1_reanalysis_casegen.py
(1.8 V and the ns values are POC_ASSUMPTION tool-test conditions, not circuit results). No simulator
is involved. The waveforms are built from the historical stimulus structure of scripts/sc1_s1r.sh
(clock 50 ns pulse, data high 270..620, blank high to 450, en = NOR(qbar, blank)) so that the five
window labels name states that are actually present in the file; the difference to the real S1 data is
that these numbers were composed, not measured.

Cases and what each must prove:
  all_matching        complete lineage (decks + history) and a consistent stimulus -> CERTIFIED, rc 0
  wrong_blank         DC row labelled BLANK=0 reads 0.7 V            -> FAIL, rc 1, never certified
  missing_deck        deck files removed, raws intact                 -> PARTIAL/NOT_VERIFIED, rc 3
  missing_history     no history CSVs                                 -> PARTIAL + ASSERTION_CHECK_ONLY
  unreadable_evidence transient raw holds only time/en/q              -> FAIL, rc 1
  no_fault_run        the negative run is not on disk                 -> PARTIAL, rc 3
"""
from __future__ import print_function

import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sc1_r2d1_reanalysis_casegen as CG

REANALYSIS = os.path.join(HERE, 'sc1_r2d_s1_reanalysis.py')


def build_tree(root, decks=True, history=True, blank_defect=False, evidence_signals=True,
               fault_raw=True):
    """Write one synthetic input tree and return the argument list for the re-analysis."""
    sim = os.path.join(root, 'sim')
    dk = os.path.join(root, 'deck')
    for p in (sim, dk):
        if not os.path.isdir(p):
            os.makedirs(p)
    blank_override = {0.0: 0.7} if blank_defect else None
    tran_signals = ('en', 'q') if not evidence_signals else None
    CG.write_dc_runs(sim, blank_override=blank_override)
    CG.write_tran_run(sim, signals=tran_signals, fault=fault_raw)
    if decks:
        CG.write_decks(dk)
    hp, hn, fh = None, None, None
    if history:
        hp = os.path.join(root, 's1r_truth.csv')
        hn = os.path.join(root, 's1r_transient.csv')
        CG.write_history(hp, hn)
        fh = CG.fault_history_value() if fault_raw else None
    return sim, dk, hp, hn, fh


def run_reanalysis(root, sim, dk, hp, hn, out, fault_history=None):
    cmd = [sys.executable, REANALYSIS, '--sim-dir', sim, '--deck-dir', dk, '--out', out]
    if hp:
        cmd += ['--history-truth', hp, '--history-transient', hn]
    if fault_history:
        cmd += ['--fault-history', fault_history]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=root)
    raw = p.communicate()[0]
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    return p.returncode, txt


def csv_field_count(path):
    with io.open(path, encoding='utf-8') as f:
        first = f.readline().strip()
    n, quoted = 0, False
    for ch in first:
        if ch == '"':
            quoted = not quoted
        elif ch == ',' and not quoted:
            n += 1
    return n + 1


def main():
    argv = sys.argv[1:]
    root = os.path.dirname(HERE)
    out_csv = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(
        root, 'results', 'evidence', 'sc1_r2d1_reanalysis_selftest.csv')
    work = os.path.join(root, 'cadence_work', 'sc1_sim', 'r2d1_reanalysis_mock')
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

    results = []

    def case(name, kwargs, want_rc, want_tokens, forbid_tokens, note):
        d = os.path.join(work, name)
        os.makedirs(d)
        decks = kwargs.pop('decks', True)
        history = kwargs.pop('history', True)
        fault = kwargs.pop('fault_raw', True)
        sim, dk, hp, hn, fh = build_tree(d, decks=decks, history=history, fault_raw=fault,
                                         **kwargs)
        out = os.path.join(d, 'reanalysis.csv')
        rc, txt = run_reanalysis(d, sim, dk, hp, hn, out, fault_history=fh)
        # a token may live in the console summary or in the CSV column it belongs to; both are the
        # artifact under test, so the search covers them together
        hay = txt
        if os.path.exists(out):
            with io.open(out, encoding='utf-8') as f:
                hay = txt + f.read()
        met, reasons = True, []
        if rc != want_rc:
            met = False
            reasons.append('rc=%s want %s' % (rc, want_rc))
        for tok in want_tokens:
            if tok not in hay:
                met = False
                reasons.append('missing token %s' % tok)
        for tok in forbid_tokens:
            if tok in hay:
                met = False
                reasons.append('forbidden token present: %s' % tok)
        if os.path.exists(out):
            n = csv_field_count(out)
            if n != 24:
                met = False
                reasons.append('CSV has %d columns, expected 24' % n)
        else:
            met = False
            reasons.append('no CSV written')
        results.append([name, str(rc), ';'.join(reasons) or 'as expected',
                        'PASS' if met else 'FAIL', note, 'SYNTHETIC_MOCK_not_historical_data'])
        print('%-22s rc=%-3s %s  %s' % (name, rc, 'PASS' if met else 'FAIL',
                                         ';'.join(reasons) or note))
        if not met:
            print('   ---- output ----\n%s' % txt)
        return rc, txt

    # the reference case: everything on disk and consistent
    case('all_matching', {}, 0, ['S1_HISTORICAL_REANALYSIS: CERTIFIED'],
         ['S1_HISTORICAL_REANALYSIS: PARTIAL', 'S1_HISTORICAL_REANALYSIS: FAIL'],
         'complete lineage and consistent stimulus certifies the re-read')

    # a DC row whose BLANK is 0.7 V satisfies neither label
    case('wrong_blank', {'blank_defect': True}, 1,
         ['S1_HISTORICAL_REANALYSIS: FAIL', 'stimulus'], ['S1_HISTORICAL_REANALYSIS: CERTIFIED'],
         'a row whose own stimulus does not read back at its label cannot be evidence')

    case('missing_deck', {'decks': False}, 3,
         ['S1_HISTORICAL_REANALYSIS: PARTIAL_NOT_VERIFIED', 'deck MISSING'], ['S1_HISTORICAL_REANALYSIS: CERTIFIED'],
         'raw values without their decks are a re-read, not a certification')

    case('missing_history', {'history': False}, 3,
         ['S1_HISTORICAL_REANALYSIS: PARTIAL_NOT_VERIFIED', 'ASSERTION_CHECK_ONLY'], ['S1_HISTORICAL_REANALYSIS: CERTIFIED'],
         'with no historical values there is nothing to agree with, so agreement is not claimed')

    case('unreadable_evidence', {'evidence_signals': False}, 1,
         ['S1_HISTORICAL_REANALYSIS: FAIL', 'UNREADABLE'], ['S1_HISTORICAL_REANALYSIS: CERTIFIED'],
         'a transient raw without the states its window names cannot verify the stimulus')

    case('no_fault_run', {'fault_raw': False}, 3,
         ['S1_HISTORICAL_REANALYSIS: PARTIAL_NOT_VERIFIED'], ['S1_HISTORICAL_REANALYSIS: CERTIFIED'],
         'a missing negative leaves the checker uncertified; it is never skipped into a pass')

    hdr = ['case_id', 'reanalysis_rc', 'reasons', 'verdict', 'note', 'data_class']
    import sc1_r2d_s1_reanalysis as R
    with io.open(out_csv, 'w', encoding='utf-8', newline='\n') as f:
        f.write(R.csvline(hdr))
        for r in results:
            f.write(R.csvline(r))
    bad = [r for r in results if r[3] != 'PASS']
    print('REANALYSIS_SELFTEST cases=%d failed=%d -> %s   (%s)'
          % (len(results), len(bad), 'PASS' if not bad else 'FAIL', out_csv))
    print('NOTE: every input above is SYNTHETIC; no simulator was called and this is not a re-read of '
          'the historical S1 waveforms.')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
