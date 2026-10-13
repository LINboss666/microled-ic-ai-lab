#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E1: the bounded call-path verification for the two R2E entries.

    python scripts/sc1_r2e1_callpath_selftest.py [--out CSV]

NO SIMULATOR IS REACHED. Every callee is a mock written into its own temporary directory and
addressed through the entries' injectable hooks (QODER_PF_CMD / QODER_RUN_CMD / QODER_READ_CMD /
QODER_VTX_CMD / QODER_DELAY_CMD); each row is labelled SYNTHETIC_MOCK_NOT_A_CIRCUIT_RUN. The mocks
also refuse outright if they are pointed at a path outside their own root, if RUN or
QODER_SIM_AUTHORISED is present in their environment, or if the runner is called with the label in
argv instead of the netlist -- so a mistake in the call shape fails loudly rather than quietly
touching a real project file.

The defects this list was written against (each independently reproduced by the reviewer on 593a8be):

  A1  preflight was called as `... 2>&1 | tail -4/5`, so the recorded rc was TAIL's: a mock printing
      `TESTBENCH_PREFLIGHT: FAIL` and exiting 1 was recorded rc=0 / PASS, and the runner was still
      called.
  A2  a run was accepted because a `<LABEL>: PASS` string appeared: a mock printing that token plus
      `CHECK error_hits=0` and `SPECTRE ... rc=3`, then exiting 3, was recorded as a success.

Each case asserts the concrete row (item, recorded rc, verdict, reason) AND the preflight / runner /
reader call counts read from the mock's own call log. "The script exited non-zero" is not accepted as
the evidence, and a case that ends because the driver crashed is a FAIL, not a detection.

Case list (fixed, exactly the five groups the task book asked for):
  1  preflight non-zero with a FAIL line
  2  preflight rc=0 with no / duplicated / contradicting completion marker
  3  runner non-zero while printing this label's PASS and a readable fixture (the stale-file trap)
  4  runner rc=0 but the contract is broken: duplicated PASS, another label's PASS, error_hits!=0,
     spectre rc!=0, no datafile, or a datafile outside this deck's own sim directory
  5  everything consistent -> rc 0/0/0, exactly one runner call, the reader is reached

R2E2 adds one targeted assertion to group 5 and one negative beside it, nothing else: the mock records
the supply map it actually received, the calibration control case requires the derived
`rail=1.8 vss=0', and `stale_map' hands over the pre-fix `vdd18=...' map, which the mock refuses with
the checker's own message while runner and reader stay at zero calls (2.1).
"""
from __future__ import print_function

import optparse
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sc1_r2e_s2_tt as S2                          # the real S2 caller, driven with mocks
import sc1_r2e_calibrate as CAL                     # the real calibration caller, driven with mocks

try:
    _text = unicode
except NameError:
    _text = str

MOCK_TAG = 'SYNTHETIC_MOCK_NOT_A_CIRCUIT_RUN'
PY = '"%s"' % sys.executable

PF_SRC = '''import os, re, sys
deck = sys.argv[1] if len(sys.argv) > 1 else ''
smap = sys.argv[4] if len(sys.argv) > 4 else ''
sc = os.environ.get('QODER_MOCK_SCENARIO', '')
calls = os.environ['QODER_MOCK_CALLS']
root = os.environ['QODER_MOCK_ROOT']
open(calls, 'a').write('PF ' + sc + '\\n')
open(calls, 'a').write('PFMAP ' + sc + ' ' + smap + '\\n')
if 'RUN' in os.environ or 'QODER_SIM_AUTHORISED' in os.environ:
    print('MOCK_ENV_LEAK: RUN/QODER_SIM_AUTHORISED must not reach a mock callee')
    sys.exit(9)
if not os.path.abspath(deck).startswith(os.path.abspath(root)):
    print('MOCK_REFUSED: preflight pointed outside the isolated mock root: ' + deck)
    sys.exit(9)
print('SYNTHETIC_MOCK_NOT_A_CIRCUIT_RUN preflight scenario=' + sc)
if sc == 'refused':
    print('PREFLIGHT_STAGE=supply_contract')
    print('PREFLIGHT_REJECT: net vssx has no independent source to node 0')
    print('TESTBENCH_PREFLIGHT: FAIL (stage=supply_contract reason=checker_exit=1)')
    sys.exit(1)
if sc == 'no_marker':
    print('PREFLIGHT_STAGE=static_gate')
    sys.exit(0)
if sc == 'dup_marker':
    print('TESTBENCH_PREFLIGHT: PASS')
    print('TESTBENCH_PREFLIGHT: PASS')
    sys.exit(0)
if sc == 'pass_and_fail':
    print('TESTBENCH_PREFLIGHT: PASS')
    print('TESTBENCH_PREFLIGHT: FAIL (stage=operating_point_sim)')
    sys.exit(0)
# R2E2 2.1: the audited supply checker refuses a contract entry that names no instance port, so the
# mock reproduces exactly that rule against the deck's own source lines. This is the one assertion
# the calibration map needed; the map is now derived from the deck, and a stale name cannot pass.
if os.path.isfile(deck):
    dtext = open(deck).read()
else:
    dtext = ''
driven = re.findall(r'^\\s*\\S+\\s*\\((\\S+)\\s+0\\)\\s+vsource', dtext, re.M)
for entry in smap.split():
    key = entry.split('=')[0]
    if key and key not in driven:
        print('PREFLIGHT_STAGE=supply_contract')
        print('PREFLIGHT_REJECT: contract_refused:contract entry %s matches no instance port' % key)
        print('TESTBENCH_PREFLIGHT: FAIL (stage=supply_contract reason=contract_refused)')
        sys.exit(1)
print('PREFLIGHT_CONTRACT_SATISFIED: PASS')
print('TESTBENCH_PREFLIGHT: PASS')
sys.exit(0)
'''

RS_SRC = '''import os, sys
deck = sys.argv[1] if len(sys.argv) > 1 else ''
label = os.environ.get('LABEL', '')
sc = os.environ.get('QODER_MOCK_SCENARIO', '')
calls = os.environ['QODER_MOCK_CALLS']
root = os.environ['QODER_MOCK_ROOT']
open(calls, 'a').write('RS ' + sc + '\\n')
if 'RUN' in os.environ or 'QODER_SIM_AUTHORISED' in os.environ:
    print('MOCK_ENV_LEAK: RUN/QODER_SIM_AUTHORISED must not reach a mock callee')
    sys.exit(9)
if not deck.endswith('.scs') or os.path.basename(deck).startswith(('S2_', 'CAL_')):
    print('MOCK_ARGV_ORDER_WRONG: $1 must be the netlist, LABEL travels in the environment (got '
          + repr(deck) + ')')
    sys.exit(9)
if not os.path.abspath(deck).startswith(os.path.abspath(root)):
    print('MOCK_REFUSED: runner pointed outside the isolated mock root: ' + deck)
    sys.exit(9)
sim = os.path.join(os.path.dirname(os.path.abspath(deck)), 'sim')
if not os.path.isdir(sim):
    os.makedirs(sim)
data = os.path.join(sim, 'mock.tran.tran')
if sc != 'no_data':
    with open(data, 'w') as f:
        f.write('HEADER\\nSWEEP\\n"time" "sweep"\\nTRACE\\n"gate33" "V"\\nVALUE\\n')
        f.write('"time" 0\\n"gate33" 3.3\\n"time" 1e-9\\n"gate33" 3.3\\nEND\\n')
log = os.path.join(sim, 'mock.log')
open(log, 'w').write('Global user options:\\n    temp = 27\\n'
                     'spectre completes with 0 errors, and 0 notices.\\n')
print('SYNTHETIC_MOCK_NOT_A_CIRCUIT_RUN runner scenario=' + sc)
print('SPECTRE name=' + os.path.basename(deck) + ' rc=' + ('3' if sc == 'spectre_rc' else '0'))
print('LOGFILE ' + log)
print('RAWDIR  ' + sim)
print("CHECK done_line='spectre completes with 0 errors'")
print('CHECK error_hits=' + ('2' if sc == 'error_hits' else '0'))
if sc not in ('no_data', 'stale_outside'):
    print("CHECK datafile='" + data + "'")
if sc == 'stale_outside':      # the runner points at a readable file that is NOT this run's
    outside = os.path.join(root, 'stale_from_an_earlier_run.tran.tran')
    open(outside, 'w').write('HEADER\\nSWEEP\\n"time" "sweep"\\nTRACE\\n"x" "V"\\nVALUE\\n'
                             '"time" 0\\n"x" 1\\nEND\\n')
    print("CHECK datafile='" + outside + "'")
if sc == 'dup_pass':
    print(label + ': PASS')
    print(label + ': PASS')
elif sc == 'other_label':
    print('OTHER_LABEL: PASS')
else:
    print(label + ': PASS')
if sc == 'fail_with_pass':
    print('REASON: the mock fails AFTER printing this label\\'s PASS')
    sys.exit(3)
sys.exit(0)
'''

RD_SRC = '''import os, sys
open(os.environ['QODER_MOCK_CALLS'], 'a').write('RD\\n')
if 'RUN' in os.environ or 'QODER_SIM_AUTHORISED' in os.environ:
    print('MOCK_ENV_LEAK')
    sys.exit(9)
print('1.23')
sys.exit(0)
'''

DELAY_SRC = '''import os, sys
open(os.environ['QODER_MOCK_CALLS'], 'a').write('RD\\n')
print('STEADY sig=mock n=12 min=0.10 max=3.20 mean=1.50')
sys.exit(0)
'''

HDR = ['scenario', 'entry', 'item', 'recorded_rc', 'verdict', 'reason_or_value', 'pf_calls',
       'rs_calls', 'rd_calls', 'label', 'expected', 'result']


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(text))


def counts(calls_file):
    got = {'PF': 0, 'RS': 0, 'RD': 0}
    if os.path.isfile(calls_file):
        for l in io.open(calls_file, encoding='utf-8', errors='replace'):
            k = l.split(' ')[0].strip()
            if k in got:
                got[k] += 1
    return got


def received_map(calls_file, scenario):
    """The supply map string the mock preflight actually got, as one argv element."""
    last = ''
    if os.path.isfile(calls_file):
        for l in io.open(calls_file, encoding='utf-8', errors='replace'):
            toks = l.rstrip('\n').split(' ', 2)
            if len(toks) == 3 and toks[0] == 'PFMAP' and toks[1] == scenario:
                last = toks[2]
    return last


def mock_env(scenario, root, calls):
    env = dict(os.environ)
    for k in ('RUN', 'QODER_SIM_AUTHORISED'):
        env.pop(k, None)
    env.update({
        'QODER_PF_CMD': '%s "%s"' % (PY, os.path.join(root, 'mock_pf.py')),
        'QODER_RUN_CMD': '%s "%s"' % (PY, os.path.join(root, 'mock_rs.py')),
        'QODER_READ_CMD': '%s "%s"' % (PY, os.path.join(root, 'mock_rd.py')),
        'QODER_VTX_CMD': '%s "%s"' % (PY, os.path.join(root, 'mock_rd.py')),
        'QODER_DELAY_CMD': '%s "%s"' % (PY, os.path.join(root, 'mock_delay.py')),
        'QODER_MOCK_SCENARIO': scenario, 'QODER_MOCK_CALLS': calls, 'QODER_MOCK_ROOT': root})
    return env


class mock_environment(object):
    """swap the entries' tool hooks to the isolated mocks, keeping the rest of the environment.

    os.environ is edited in place because the entries read their hooks from it; it is NOT cleared,
    since a stripped environment breaks the platform's own process layer and that would look like a
    tool failure instead of a test result. The only keys removed are RUN and QODER_SIM_AUTHORISED --
    the mocks also refuse if they ever see them, which is how "no simulation authorisation leaks into
    a mock run" is verified rather than assumed.
    """

    def __init__(self, scenario, root, calls):
        self.wanted = mock_env(scenario, root, calls)
        self.old = None

    def __enter__(self):
        self.old = dict(os.environ)
        for k in ('RUN', 'QODER_SIM_AUTHORISED'):
            os.environ.pop(k, None)
        os.environ.update(self.wanted)
        return self

    def __exit__(self, *exc):
        for k in list(self.wanted.keys()):
            os.environ.pop(k, None)
        os.environ.clear()
        os.environ.update(self.old)
        return False


def drive_s2(scenario, root, calls):
    deckroot = os.path.join(root, 'decks_s2')
    if not os.path.isdir(deckroot):
        os.makedirs(deckroot)

    class Opts(object):
        fine = '0.05n'
    R = S2.Run([], [], 'MOCK-S2')
    with mock_environment(scenario, root, calls):
        S2.run_case(R, 'st_c0_en_low', deckroot, 'nl-sha', 'lib-sha', [], Opts())
    return R.rows


CAL_DECK = '''simulator lang=spectre insensitive=yes
simopt options temp=27
subckt sc1_r2e_cal_load (rail vss)
  R1 (rail node_mid) resistor r=10000
  Ip1 (node_mid vss) iprobe
ends sc1_r2e_cal_load
V18 (rail 0) vsource dc=1.8
Vss (vss 0) vsource dc=0
Xcal (rail vss) sc1_r2e_cal_load
save rail vss Xcal.node_mid Xcal.Ip1:i
save V18:i
'''


def drive_cal(scenario, root, calls):
    """Drive the calibration caller with the isolated mocks.

    The deck is written in the bench's real shape (its rail net is called `rail'), because R2E2 2.1
    derives the supply map from the deck instead of naming it after the source instance. `stale_map'
    restores the pre-fix map through the same hook to prove the gate still refuses it and that
    nothing downstream is called.
    """
    deckroot = os.path.join(root, 'decks_cal')
    if not os.path.isdir(deckroot):
        os.makedirs(deckroot)
    deck = os.path.join(deckroot, 'cal_v18_i.scs')
    write(deck, CAL_DECK)
    got = []

    def add(item, deck_name, expected, actual, rc, verdict, note):
        got.append([item, deck_name, expected, actual, str(rc), verdict, note])
    real_map = CAL.deck_supply_map
    if scenario == 'stale_map':
        CAL.deck_supply_map = lambda p: ('vdd18=1.8 vdd33=3.3 vss=0', 'V18', 'vdd18')
    try:
        with mock_environment(scenario, root, calls):
            CAL.preflight_and_run(add, [], deck, 'V18', 'V18:i', 'V18-i', 1.8)
    finally:
        CAL.deck_supply_map = real_map
    return got


def pick(rows, item, entry):
    for r in rows:
        if (r[0] if entry == 'CAL' else r[1]) == item:
            return r
    return None


def fields(row, entry):
    """(recorded_rc, verdict, reason_text) in the two entries' different row shapes"""
    if entry == 'CAL':
        return row[4], row[5], '%s %s' % (row[3], row[6])
    return row[6], row[7], '%s %s' % (row[5], row[8])


# scenario -> (item, wanted verdict, wanted reason substring, (pf, rs, rd) where rd 0 means exactly
# zero and a positive number means at least that many)
CASES = [
    ('refused', 'PREFLIGHT_FULL', 'BLOCKED', 'preflight_rc=1', (1, 0, 0)),
    ('no_marker', 'PREFLIGHT_FULL', 'BLOCKED', 'completion marker', (1, 0, 0)),
    ('dup_marker', 'PREFLIGHT_FULL', 'BLOCKED', '2 completion markers', (1, 0, 0)),
    ('pass_and_fail', 'PREFLIGHT_FULL', 'BLOCKED', 'FAIL line', (1, 0, 0)),
    ('fail_with_pass', 'SIM_RUN', 'BLOCKED', 'runner_rc=3', (1, 1, 0)),
    ('dup_pass', 'SIM_RUN', 'BLOCKED', '2 final PASS lines', (1, 1, 0)),
    ('other_label', 'SIM_RUN', 'BLOCKED', '0 final PASS lines', (1, 1, 0)),
    ('error_hits', 'SIM_RUN', 'BLOCKED', 'error_hits=2', (1, 1, 0)),
    ('spectre_rc', 'SIM_RUN', 'BLOCKED', 'spectre_rc=3', (1, 1, 0)),
    ('no_data', 'SIM_RUN', 'BLOCKED', 'datafile', (1, 1, 0)),
    ('stale_outside', 'SIM_RUN', 'BLOCKED', 'outside this deck', (1, 1, 0)),
    ('stale_map', 'PREFLIGHT_FULL', 'BLOCKED', 'matches no instance port', (1, 0, 0)),
    ('ok', 'SIM_RUN', 'PASS', 'contract satisfied', (1, 1, 0)),
]

# R2E2 2.1: the control case also asserts the map VALUE that reached the gate. The calibration bench
# drives a net called `rail', so the derived map is `rail=<volts> vss=0'; S2's frozen generator names
# vdd18/vdd33/vss. Both must arrive as ONE argv element, with no shell splitting. `stale_map' is the
# negative: the pre-fix hand-written map is handed over, the gate refuses it, and nothing else runs.
EXPECTED_MAP = {('CAL', 'ok'): 'rail=1.8 vss=0',
                ('S2', 'ok'): 'vdd18=1.8 vdd33=3.3 vss=0',
                ('CAL', 'stale_map'): 'vdd18=1.8 vdd33=3.3 vss=0'}


def main():
    op = optparse.OptionParser()
    op.add_option('--out')
    o, _ = op.parse_args()
    out_csv = o.out or os.path.join(PROJ, 'results', 'evidence', 'sc1_r2e1_callpath_selftest.csv')
    root = os.path.join(tempfile.gettempdir(), 'sc1_r2e1_mocks')
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root)
    write(os.path.join(root, 'mock_pf.py'), PF_SRC)
    write(os.path.join(root, 'mock_rs.py'), RS_SRC)
    write(os.path.join(root, 'mock_rd.py'), RD_SRC)
    write(os.path.join(root, 'mock_delay.py'), DELAY_SRC)

    rows = []
    fails = 0
    n = 0
    for entry, driver in (('S2', drive_s2), ('CAL', drive_cal)):
        for scenario, item, want_verdict, want_reason, want_counts in CASES:
            if scenario == 'stale_map' and entry != 'CAL':
                # the stale-map negative is specific to the calibration caller; S2's contract comes
                # from the frozen generator and is already asserted by its own control case
                continue
            if scenario == 'ok' and entry == 'CAL':
                want_counts = (1, 1, 0)             # the calibration path stops after the run
            if scenario == 'ok' and entry == 'S2':
                want_counts = (1, 1, 1)             # the control case must reach the reader
            calls = os.path.join(root, 'calls_%s_%s.log' % (entry, scenario))
            if os.path.isfile(calls):
                os.remove(calls)
            n += 1
            try:
                got = driver(scenario, root, calls)
            except Exception as e:
                fails += 1
                print('%-16s %-4s CRASH %r  -> FAIL' % (scenario, entry, e))
                rows.append([scenario, entry, item, 'CRASH', 'FAIL', repr(e)[:120], '-', '-', '-',
                             MOCK_TAG, 'no exception in the caller', 'FAIL'])
                continue
            c = counts(calls)
            row = pick(got, item, entry)
            got_map = received_map(calls, scenario)
            map_want = EXPECTED_MAP.get((entry, scenario), '')
            map_ok = (not map_want) or (got_map == map_want)
            if row is None:
                hit, rec_rc, verdict, detail = (False, '-', '-',
                                                'no %s row; items=%s' % (item, ','.join(sorted(
                                                    set((r[0] if entry == 'CAL' else r[1])
                                                        for r in got)))[:80]))
            else:
                rec_rc, verdict, detail = fields(row, entry)
                hit = (verdict == want_verdict and want_reason in detail and
                       c['PF'] == want_counts[0] and c['RS'] == want_counts[1] and
                       ((c['RD'] >= want_counts[2]) if want_counts[2] else (c['RD'] == 0)) and
                       map_ok)
            fails += 0 if hit else 1
            print('%-16s %-4s %-16s rc=%-4s %-8s PF/RS/RD=%d/%d/%d map=%r %s'
                  % (scenario, entry, item, rec_rc, verdict, c['PF'], c['RS'], c['RD'], got_map,
                     'PASS' if hit else 'FAIL'))
            if not hit:
                print('        want verdict=%s reason~%r calls=%r map~%r | got %r'
                      % (want_verdict, want_reason, want_counts, map_want, detail[:150]))
            rows.append([scenario, entry, item, rec_rc, verdict, detail[:150], str(c['PF']),
                         str(c['RS']), str(c['RD']), MOCK_TAG,
                         'verdict=%s reason~%r calls=%r%s'
                         % (want_verdict, want_reason, want_counts,
                            '' if not map_want else ' map=%r' % map_want),
                         'PASS' if hit else 'FAIL'])

    d = os.path.dirname(out_csv)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(out_csv, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(','.join(u('"%s"') % h for h in HDR)) + u('\n'))
        for r in rows:
            f.write(u(','.join(u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in r))
                    + u('\n'))
    print('CALLPATH_SELFTEST cases=%d failures=%d csv=%s' % (n, fails, out_csv))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
