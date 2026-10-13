# -*- coding: utf-8 -*-
"""SCAN-1 R2E2: the dependency transcript for the bounded native re-verification. NO SIMULATION.

    python scripts/sc1_r2e2_transcript.py

An authorised native round has to say HOW MANY processes actually ran and which of them were the
preflight's own operating-point dependency rather than the DUT. Neither entry kept a process log, so
this reads what the tools already left on disk -- deck, preflight run, DUT run, data file -- and pairs
it with the rc columns recorded in the round's own CSVs:

  * every S2/calibration deck dir contains `sim/preflight_*' artifacts: that is tb_preflight.sh's
    FULL mode running its own operating-point analysis, a dependency simulation, not a DUT result;
  * `sim/<case>.log' and `sim/<case>.raw/' are the runner's own DUT pass.

Rows are one field per line (so a reviewer can grep a value instead of trusting a paragraph), paths
are project-relative, and nothing that lives outside this project's own scratch is quoted. Verdicts
stay `PRESENT'/'ABSENT': presence of an artifact is not a circuit verdict, and the numbers already
sit in the evidence CSVs this file points at.
"""
from __future__ import print_function

import hashlib
import io
import optparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

try:
    _text = unicode
except NameError:
    _text = str

EVID = os.path.join(PROJ, 'results', 'evidence')
SIMROOT = os.path.join('cadence_work', 'sc1_sim')
HDR = ['kind', 'case', 'field_or_artifact', 'project_relative_path', 'value', 'sha256_16',
       'status', 'note']

# the fixed checklist of this round: 2 calibration benches + the 15 S2 cases, group by group
UNITS = [
    ('r2e2_cal', 'sc1_r2e2_calibration.csv', ('cal_v18_V18-i', 'cal_v33_V33-i')),
    ('r2e2_s2_static', 'sc1_r2e2_s2_static.csv',
     ('st_c0_en_low', 'st_c0_en_high', 'st_c1_enlow_okhigh', 'st_c1_enhigh_okhigh',
      'st_c1_enlow_oklow', 'st_c1_enhigh_oklow')),
    ('r2e2_s2_dynamic', 'sc1_r2e2_s2_dynamic.csv',
     ('dyn_c0_rise', 'dyn_c0_fall', 'dyn_c1_rise', 'dyn_c1_fall',
      'dyn_c0_repeat3', 'dyn_c1_repeat3')),
    ('r2e2_s2_load', 'sc1_r2e2_s2_load.csv', ('load_c1_5pF', 'load_c1_5pF_fine')),
    ('r2e2_s2_negative', 'sc1_r2e2_s2_negative.csv', ('neg_output_polarity_fault',)),
]


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def sha16(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()[:16]


def rel(path):
    return path[len(PROJ) + 1:].replace(os.sep, '/') if path.startswith(PROJ) else path.replace(
        os.sep, '/')


def csvline(vals):
    """python 2.6 has no csv writer that takes a unicode stream, so the quoting stays explicit"""
    return u(','.join([u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in vals])) + u('\n')


def first_line(text, pattern, group=0):
    m = re.search(pattern, text, re.M)
    return m.group(group).strip() if m else ''


def datafile_of(rawdir):
    """the runner's own psfascii: the file in this raw dir that has both TRACE and VALUE"""
    if not os.path.isdir(rawdir):
        return ''
    cands = []
    for name in os.listdir(rawdir):
        p = os.path.join(rawdir, name)
        if not os.path.isfile(p) or name == 'logFile':
            continue
        txt = u(io.open(p, encoding='utf-8', errors='replace').read())
        if re.search(r'^TRACE', txt, re.M) and re.search(r'^VALUE', txt, re.M):
            cands.append((os.path.getsize(p), p))
    return max(cands)[1] if cands else ''


def row(rows, kind, case, field, path, value, sh, status, note):
    rows.append([kind, case, field, path, value, sh, status, note])


def preflight_logs(simdir, case):
    """this case's own preflight operating-point log, or an empty list.

    tb_preflight.sh names the artifact `preflight_<deck stem>_<tag>.log'. For S2 the tag IS the case
    id; the calibration benches pass the shorter tag cal_v18/cal_v33 while their deck stem is
    cal_v18_V18-i. A bare substring match would let `load_c1_5pF' also claim
    `load_c1_5pF_fine', so both parts are checked and the tag has to be a prefix of the stem.
    """
    if not os.path.isdir(simdir):
        return []
    out = []
    for p in sorted(os.listdir(simdir)):
        if not os.path.isfile(os.path.join(simdir, p)) or not p.startswith('preflight_') or \
                not p.endswith('.log'):
            continue
        middle = p[len('preflight_'):-len('.log')]
        if middle == '%s_%s' % (case, case):
            out.append(p)
            continue
        if middle.startswith(case + '_'):
            tag = middle[len(case) + 1:]
            if tag and case.startswith(tag):
                out.append(p)
    return out


def redact(text):
    """the round's own CSV excerpts can carry the deck path; keep the substance, drop the prefix"""
    out = []
    for line in u(text).split('\n'):
        if re.search(r'/root/|/opt/|/home/|/etc/', line):
            line = re.sub(r'(/root|/opt|/home|/etc)/[^\s"\']*', '<path-redacted>', line)
        out.append(line)
    return '\n'.join(out)


def unit_key(raw):
    """the unit a CSV row belongs to, in the same vocabulary the decks use.

    The S2 entry has a `case' column; the calibration entry names the deck file for PREFLIGHT_FULL
    ('cal_v18_V18-i.scs') and '<name> <form>' for SIM_RUN ('V18 V18:i'), so both spellings are
    folded onto the deck stem -- otherwise the two rc rows of a bench would never join.
    """
    x = u(raw).replace('.scs', '')
    m = re.match(r'^(V(?:18|33)) V(?:18|33):i$', x)
    if m:
        return 'cal_%s_%s-i' % (m.group(1).lower(), m.group(1))
    return x


def main():
    op = optparse.OptionParser()
    op.add_option('--out')
    o, _ = op.parse_args()
    out = o.out or os.path.join(EVID, 'sc1_r2e2_dependency_transcript.csv')
    import csv
    rows = []
    dep_runs = dut_runs = 0
    for group, csvname, cases in UNITS:
        gdir = os.path.join(PROJ, SIMROOT, group)
        simdir = os.path.join(gdir, 'sim')
        # the round's own rc columns, joined by case id, so the transcript and the CSV cannot disagree
        ev = {}
        evpath = os.path.join(EVID, csvname)
        if os.path.isfile(evpath):
            hdr = list(csv.reader([io.open(evpath, encoding='utf-8', newline='').readline()]))[0]
            # the S2 rows carry run_id and a separate case column; the calibration entry's rows are
            # (item, deck, expected, actual, rc, verdict, note), so its deck column IS the case
            ii = hdr.index('item')
            ci = hdr.index('case') if 'case' in hdr else hdr.index('deck_or_target')
            ai = hdr.index('actual')
            ri = hdr.index('rc')
            vi = hdr.index('verdict')
            for r in list(csv.reader([l for l in io.open(evpath, encoding='utf-8', newline='')]))[1:]:
                if len(r) <= max(ii, ci, ai, ri, vi):
                    continue
                ev.setdefault((unit_key(r[ci]), r[ii]), []).append(r)
        for case in cases:
            deck = os.path.join(gdir, case + '.scs')
            if not os.path.isfile(deck):
                row(rows, 'ABSENT_ARTIFACT', case, 'deck', rel(deck), '-', '-', 'ABSENT',
                    'this case has no deck in %s, so nothing below can be claimed for it' % group)
                continue
            dtext = u(io.open(deck, encoding='utf-8', errors='replace').read())
            row(rows, 'DECK', case, 'sha256 / instance count', rel(deck),
                'sha256=%s lines=%d include_tt=%s' % (sha16(deck), dtext.count('\n'),
                                                      'section=tt' in dtext), sha16(deck), 'PRESENT',
                'the deck this run wrote into its own scratch directory')
            dlog = os.path.join(simdir, case + '.log')
            if os.path.isfile(dlog):
                txt = u(io.open(dlog, encoding='utf-8', errors='replace').read())
                done = first_line(txt, r'spectre completes with [^\n]*')
                row(rows, 'DUT_RUN', case, 'log', rel(dlog),
                    'temp=%s ; %s' % (first_line(txt, r'^\s*temp\s*=\s*(\S+)', 1) or '?',
                                      done or 'no completion line'), sha16(dlog), 'PRESENT',
                    'the runner pass over the DUT deck; read back from the log the process wrote')
                dut_runs += 1
            else:
                row(rows, 'DUT_RUN', case, 'log', rel(dlog), '-', '-', 'ABSENT',
                    'no DUT log: this case did not reach the runner or the runner wrote elsewhere')
            df = datafile_of(os.path.join(simdir, case + '.raw'))
            if df:
                hdr = u(io.open(df, encoding='utf-8', errors='replace').read(4000))
                row(rows, 'DUT_DATA', case, 'psfascii header', rel(df),
                    'temp=%s ; signal_count=%d' % (first_line(hdr, r'^"temp"\s+(\S+)', 1) or '?',
                                                   len(re.findall(r'^TRACE', hdr, re.M))),
                    sha16(df), 'PRESENT',
                    'the same file the readers were called with; the header temp is a measurement')
            else:
                row(rows, 'DUT_DATA', case, 'psfascii', rel(os.path.join(simdir, case + '.raw')),
                    '-', '-', 'ABSENT', 'no readable data file for this case')
            pf = preflight_logs(simdir, case)
            for p in pf:
                txt = u(io.open(os.path.join(simdir, p), encoding='utf-8',
                                errors='replace').read())
                row(rows, 'PREFLIGHT_DEPENDENCY_RUN', case, 'op-point analysis log',
                    rel(os.path.join(simdir, p)),
                    'temp=%s ; %s' % (first_line(txt, r'^\s*temp\s*=\s*(\S+)', 1) or '?',
                                      first_line(txt, r'spectre completes with [^\n]*')
                                      or 'no completion line'), sha16(os.path.join(simdir, p)),
                    'PRESENT',
                    'tb_preflight.sh FULL mode runs this analysis to certify the operating point; it '
                    'is a dependency of the gate, NOT a DUT measurement')
                dep_runs += 1
            if not pf:
                row(rows, 'PREFLIGHT_DEPENDENCY_RUN', case, 'op-point analysis log', '-', '-', '-',
                    'ABSENT', 'no preflight analysis artifact for this case in %s' % group)
            for item in ('PREFLIGHT_FULL', 'SIM_RUN'):
                for r in ev.get((case, item), []):
                    row(rows, 'RECORDED_RC', case, item, rel(evpath), 'rc=%s verdict=%s | %s'
                        % (r[ri], r[vi], redact(r[ai])[:80]), '-', 'PRESENT',
                        'the exit code this round recorded for that process')
    lines = [csvline(HDR)]
    for r in rows:
        lines.append(csvline(r))
    with io.open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(''.join(lines)))
    print('R2E2_TRANSCRIPT rows=%d dependency_preflight_runs=%d dut_runs=%d -> %s'
          % (len(rows), dep_runs, dut_runs, out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
