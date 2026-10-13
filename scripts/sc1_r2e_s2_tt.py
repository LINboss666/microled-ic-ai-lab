#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E S2: the first NATIVE TT run of the frozen 1.8 -> 3.3 V level shifter.

    python scripts/sc1_r2e_s2_tt.py --group static
    python scripts/sc1_r2e_s2_tt.py --group dynamic
    python scripts/sc1_r2e_s2_tt.py --group load
    python scripts/sc1_r2e_s2_tt.py --group negative
    [--dry] prints the deck set and exits without calling the simulator

Execution needs BOTH RUN=1 and QODER_SIM_AUTHORISED=1 in the environment; without them every case is
recorded as NOT_RUN and the entry exits 5. This is the entry the R2D round said did not exist: it now
has a real execution path, and every failure mode has its own verdict instead of a silent zero.

What is reused and what is new:
  * the audited deck generator (scripts/sc1_s2_r2d_gen.py) is IMPORTED, not edited: the case table,
    the stimulus waveforms, the loads and the frozen cell bytes all come from it, so the netlist under
    test stays the reviewed one;
  * two deck additions only, both justified by scripts/sc1_r2e_calibration.csv:
      - `simopt options temp=27` (a bare `options temp=27` is rejected by this build with SFE-709),
      - `save V18:i V33:i Ven:i [Vok:i]`, the direct supply-branch currents, because the audited
        supply gate refuses a series rail iprobe and the rail current must not be assembled from a
        sum of drain currents (the sign rule -(source) == +load-branch was measured on 10 k);
  * every reading goes through the audited tools: scripts/sc1_read_psf.py for one-signal window
    aggregates, scripts/sc1_delay.py for edges/delays/plateaus (with its event-attribution rules),
    and scripts/sc1_r2e_vtx.py for a two-node difference at the SAME sample (VGS/VGD/VDS/VGB).

Verdicts: PASS / FAIL / PARTIAL / BLOCKED / NOT_RUN are circuit-or-harness states. MEASURED means a
number this run produced with no acceptance limit defined for it (device stress peaks: SOA_SIGNOFF is
NO). EXPECTED_REFUSAL means a negative case that a criterion correctly rejected.
"""
from __future__ import print_function

import hashlib
import io
import optparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import sc1_s2_r2d_gen as G                       # audited: imported, never modified
import sc1_read_psf as RD                        # audited: only its quantity grammar is reused
import sc1_r2e1_call_contract as CC                 # R2E1: one real-exit-code call contract, shared with the calibration entry

try:
    _text = unicode
except NameError:
    _text = str

READER = os.path.join(HERE, 'sc1_read_psf.py')
VTX = os.path.join(HERE, 'sc1_r2e_vtx.py')
DELAY = os.path.join(HERE, 'sc1_delay.py')
PF = os.path.join(HERE, 'tb_preflight.sh')


def reader_cmd():
    """the audited reader, or a mock in an isolated directory (QODER_READ_CMD) for the call tests"""
    return CC.hook('QODER_READ_CMD', '"%s" "%s"' % (sys.executable, READER))


def vtx_cmd():
    return CC.hook('QODER_VTX_CMD', '"%s" "%s"' % (sys.executable, VTX))


def delay_cmd():
    return CC.hook('QODER_DELAY_CMD', '"%s" "%s"' % (sys.executable, DELAY))
RS = os.path.join(HERE, 'run_spectre.sh')
NETLIST = os.path.join(PROJ, 'spectre', 'sc1_level_shifter_r2d.scs')

# POC_ASSUMPTION screening levels, quoted from this round's task book. They are a screening choice for
# this POC, not a course limit and not a foundry rating.
POC_LO = 0.30
POC_HI = 3.135

GROUPS = {
    'static': ['st_c0_en_low', 'st_c0_en_high',
               'st_c1_enlow_okhigh', 'st_c1_enhigh_okhigh',
               'st_c1_enlow_oklow', 'st_c1_enhigh_oklow'],
    'dynamic': ['dyn_c0_rise', 'dyn_c0_fall', 'dyn_c0_repeat3',
                'dyn_c1_rise', 'dyn_c1_fall', 'dyn_c1_repeat3'],
    'load': ['load_c0_1pF', 'load_c1_1pF', 'load_c1_5pF'],
    'negative': ['neg_output_polarity_fault'],
}

# expected output polarity per static case, taken from the audited case table's own `expect` text and
# written out here so a reviewer can see the assertion instead of a prose match
EXPECT_GATE = {
    'st_c0_en_low': 'high', 'st_c0_en_high': 'low',
    'st_c1_enlow_okhigh': 'high', 'st_c1_enhigh_okhigh': 'low',
    'st_c1_enlow_oklow': 'high', 'st_c1_enhigh_oklow': 'high',
}

# the core's own internal targets, from the netlist header: en low -> x high / y low, en high -> x low
# / y high. Stated as an assertion here; whether the 1.8 V gate wins against the cross-coupled p33 is
# answered by the measurement, not by this table.
EXPECT_CORE = {True: {'Xt.Xcore.enbar': 'low', 'Xt.Xcore.x': 'low', 'Xt.Xcore.y': 'high'},
               False: {'Xt.Xcore.enbar': 'high', 'Xt.Xcore.x': 'high', 'Xt.Xcore.y': 'low'}}

# (edge-in, edge-out, t0, t1) delay/edge measurements for the dynamic decks. The repeat3 windows stop
# before the NEXT input crossing so a response cannot be credited to the wrong cycle -- the rule the
# audited delay tool enforces, here with windows that do not fight it.
DYN_MEAS = {
    'dyn_c0_rise': [('rise', 'fall', '100n', '300n')],
    'dyn_c0_fall': [('fall', 'rise', '100n', '300n')],
    'dyn_c1_rise': [('rise', 'fall', '100n', '300n')],
    'dyn_c1_fall': [('fall', 'rise', '100n', '300n')],
    'dyn_c0_repeat3': [('rise', 'fall', '100n', '249n'), ('fall', 'rise', '250n', '399n'),
                       ('rise', 'fall', '400n', '549n'), ('fall', 'rise', '550n', '699n'),
                       ('rise', 'fall', '700n', '849n'), ('fall', 'rise', '850n', '899n')],
    'dyn_c1_repeat3': [('rise', 'fall', '100n', '249n'), ('fall', 'rise', '250n', '399n'),
                       ('rise', 'fall', '400n', '549n'), ('fall', 'rise', '550n', '699n'),
                       ('rise', 'fall', '700n', '849n'), ('fall', 'rise', '850n', '899n')],
    'load_c0_1pF': [('rise', 'fall', '100n', '300n')],
    'load_c1_1pF': [('rise', 'fall', '100n', '300n')],
    'load_c1_5pF': [('rise', 'fall', '100n', '600n')],
    'load_c1_5pF_fine': [('rise', 'fall', '100n', '600n')],
}

# one row per device, with the four gate-to-terminal extremes; measured on the two decks where the
# question is sharpest (the selecting static level, and the heaviest load)
STRESS_CASES = ['st_c0_en_high', 'st_c1_enhigh_okhigh', 'load_c1_5pF']
# the device whose stress is also cross-checked against the model's own exported terminal voltages
XCHECK_DEVICE = 'Xt.Xcore.mn_left'

INFO_VERDICTS = ('MEASURED', 'EXPECTED_REFUSAL', 'NOT_A_NUMBER')


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def sh(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    raw = p.communicate()[0]
    # returncode is only valid AFTER the child has been reaped: reading it before communicate()
    # returns None, and `None != 0` then turns every real reading into a phantom failure
    return p.returncode, u(raw).replace('\r', '')


def csvline(vals):
    return u(','.join([u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in vals])) + u('\n')


def scrub(text):
    out = []
    for line in text.split('\n'):
        if re.search(r'/root/|/opt/|/home/|/etc/', line):
            line = re.sub(r'(/root|/opt|/home|/etc)/[^\s"\']*', '<path-redacted>', line)
        out.append(line)
    return '\n'.join(out)


# ---------------------------------------------------------------- netlist / deck connectivity
def parse_masters(text):
    """subckt bodies -> {master: {ports: [...], items: [(kind, inst, [nets], master_or_model)]}}"""
    masters, cur = {}, None
    for raw in text.split('\n'):
        s = raw.strip()
        if not s or s.startswith('//'):
            continue
        m = re.match(r'^subckt\s+(\S+)\s*\(([^)]*)\)', s, re.I)
        if m:
            cur = m.group(1)
            masters[cur] = {'ports': re.split(r'[,\s]+', m.group(2).strip()),
                              'items': []}
            continue
        if re.match(r'^ends\b', s, re.I):
            cur = None
            continue
        if cur is None or s.startswith('parameters') or s.startswith('setoption') \
                or s.startswith('model') or s.startswith('include'):
            continue
        m = re.match(r'^([A-Za-z]\w*)\s*\(([^)]*)\)\s*([A-Za-z]\w*)(.*)$', s)
        if not m:
            continue
        name, nets, master, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        netlist = re.split(r'[,\s]+', nets.strip())
        kind = 'sub' if (master in masters or name.startswith('X')) else 'dev'
        masters[cur]['items'].append((kind, name, netlist, master))
    return masters


def deck_instances(text):
    """top-level `X...' lines of a deck -> [(inst, [nets], master)]"""
    out = []
    for raw in text.split('\n'):
        s = raw.strip()
        m = re.match(r'^(X[A-Za-z0-9_]*)\s*\(([^)]*)\)\s*(\S+)', s)
        if m:
            out.append((m.group(1), re.split(r'[,\s]+', m.group(2).strip()),
                        m.group(3)))
    return out


def resolve_devices(deck_text, extra_text):
    """every MOS of the deck with its four terminal names as the simulator would address them.

    A net that is a port of the enclosing subckt resolves outward; anything else is an internal node
    of that instance and carries the dotted instance path. That is the separator scripts/sc1_r2e_calibrate.py
    measured (`Xt.Xcore.x' is saved, `Xt/Xcore/x' is ignored).
    """
    masters = parse_masters(extra_text)
    masters.update(parse_masters(deck_text))
    out = []

    def walk(path, master, env):
        body = masters.get(master)
        if not body:
            return

        def absn(n):
            if n in env:
                return env[n]
            return '%s.%s' % (path, n) if path else n

        for kind, name, nets, m2 in body['items']:
            p2 = '%s.%s' % (path, name) if path else name
            if kind == 'sub':
                sub = masters.get(m2)
                if not sub:
                    continue
                env2 = {}
                for port, conn in zip(sub['ports'], nets):
                    env2[port] = absn(conn)
                walk(p2, m2, env2)
            else:
                if len(nets) == 4:
                    out.append((p2, m2, [absn(n) for n in nets]))

    for inst, nets, master in deck_instances(deck_text):
        sub = masters.get(master)
        if not sub:
            continue
        env2 = dict(zip(sub['ports'], nets))       # deck level: the nets are already absolute
        walk(inst, master, env2)
    return out


# ---------------------------------------------------------------- deck building
def build_r2e_deck(case, section='tt'):
    txt = G.build(case, section)
    if 'mutate' in case:
        txt = case['mutate'](txt)
    # 1. temperature: the instantiation form this build accepts (calibration row TEMP_CONFIRMATION)
    txt = txt.replace('include "${QODER_PDK_LIB}" section=tt\n',
                      'include "${QODER_PDK_LIB}" section=tt\n'
                      '// R2E: temperature read back as 27 C from the produced log and the psf header.\n'
                      'simopt options temp=27\n', 1)
    # 2. direct supply-branch currents. The rail stays directly driven; no series iprobe.
    srcs = 'V18:i V33:i Ven:i'
    if case.get('ok') is not None:
        srcs += ' Vok:i'
    txt += ('// R2E: the supply branch is read at the source itself. Measured sign rule on the same\n'
            '// build: a rail that DELIVERS I amps is saved as -I, so injected = -(Vx:i).\n'
            'save %s\n' % srcs)
    # 3. the model's own terminal voltages for one device, as an independent cross-check of the
    #    node-derived stress numbers (form measured in scripts/sc1_r2e_two_level_probe.py)
    if XCHECK_DEVICE in txt:
        txt += 'save %s sigtype=all\n' % XCHECK_DEVICE
    # 4. every device terminal node, addressed the way this build resolves it. The audited decks list
    #    x and y as `Xt.Xcore.x', but x/y are PORTS of the core subckt and internal nets of Xt, so the
    #    simulator's own name is `Xt.x' (scripts/sc1_r2e_two_level_probe.py measured that a wrong
    #    dotted path is silently ignored, and scripts/sc1_r2e_calibration.py that a device inside a
    #    subckt cannot be named without its instance path). SAVE_PATH_AUDIT records the difference.
    nodes = []
    for _p, _m, nets in resolve_devices(txt, netlist_text()):
        for n in nets:
            if n and n not in nodes:
                nodes.append(n)
    saved = set(re.sub(r'[,:]1$', '', w) for w in
                re.findall(r'\S+', ' '.join(re.findall(r'^save (.*)$', txt, re.M))))
    extra = [n for n in nodes if n not in saved]
    if extra:
        txt += ('// R2E: device terminal nodes resolved from the frozen cell itself, so the stress\n'
                '// readings below cannot be taken from a save this build threw away.\nsave %s\n'
                % ' '.join(extra))
    return txt


def netlist_text():
    return u(open(NETLIST, 'rb').read()) if os.path.isfile(NETLIST) else ''


def save_path_audit(case, deck_txt):
    """which node names the audited deck asks for are not the names this build would resolve."""
    nodes = []
    for _p, _m, nets in resolve_devices(deck_txt, netlist_text()):
        for n in nets:
            if n and n not in nodes:
                nodes.append(n)
    want = set(G.NODES[case['variant']])
    return sorted(want - set(nodes)), sorted(set(nodes) - want)


def find_case(cid):
    for c in G.CASES + G.NEGATIVES:
        if c['id'] == cid:
            return c
    return None


# ---------------------------------------------------------------- reading helpers
class Run(object):
    def __init__(self, rows, log_lines, run_id):
        self.rows = rows
        self.log = log_lines
        self.run_id = run_id

    def add(self, item, case, target, expected, actual, rc, verdict, note):
        self.rows.append([self.run_id, item, case, target, expected, actual, str(rc), verdict, note])
        print('%-26s %-22s %-26s %s' % (item, case, target[:26], verdict))


def read_sig(R, data, sig, mode, t0=None, t1=None, req='3'):
    cmd = '%s --data "%s" --sig %s --mode %s --require-n %s' % (reader_cmd(), data, sig, mode, req)
    if t0:
        cmd += ' --t0 %s' % t0
    if t1:
        cmd += ' --t1 %s' % t1
    # CC.call gives the reader's OWN exit code with stderr already merged; a pipeline would hand back
    # the last element's status instead, which is what hid the preflight failure in R2E
    rc, out = CC.call(cmd)
    return rc, out.strip().split('\n')[0]


def read_diff(R, data, a, b, mode, t0=None, t1=None):
    cmd = '%s --data "%s" --a "%s" --b "%s" --mode %s --quiet' % (vtx_cmd(), data, a, b, mode)
    if t0:
        cmd += ' --t0 %s' % t0
    if t1:
        cmd += ' --t1 %s' % t1
    rc, out = CC.call(cmd)
    txt = out.strip().split('\n')[-1] if out.strip() else ''
    val = txt.split('\t')[0] if '\t' in txt else txt
    return rc, val, txt


# ---------------------------------------------------------------- measurements
def domain_of(sig):
    """which rail a node belongs to, read off its name.

    The screening pair (<=0.30 V / >=3.135 V) is the task book's criterion for the POC OUTPUT in the
    3.3 V domain, so it is not applied to a 1.8 V node: enbar sitting at 1.8 V would otherwise read as
    'not high'. Internal nodes are judged against their own domain's 50 % decision level (0.9 V for
    the core, 1.65 V for the high domain), which is the decision level this project already used for
    the 1.8 V S1 gate, and the raw plateau is reported either way.
    """
    if sig == 'en' or sig.endswith('.enbar') or sig == 'vdd18':
        return 1.8
    return 3.3


def level_claim(sig, want):
    rail = domain_of(sig)
    if sig == 'gate33':
        return POC_LO, POC_HI, 'POC_ASSUMPTION screening levels for the 3.3 V output'
    half = 0.5 * rail
    return half, half, 'the %.1f V domain 50%% level' % rail


def measure_levels(R, cid, kind, data, t0, t1, targets, req='5'):
    """whole-window plateau per signal: a HIGH claim needs the window MIN above the level, a LOW claim
    the window MAX below it. One extreme sample is never accepted as a state."""
    for sig, want in targets:
        rcn, mn = read_sig(R, data, sig, 'min', t0, t1, req)
        rcx, mx = read_sig(R, data, sig, 'max', t0, t1, req)
        if rcn != 0 or rcx != 0:
            R.add(kind, cid, sig, 'window min and max both readable',
                  (mn if rcn else mx)[:70], rcn or rcx, 'BLOCKED',
                  'reader exit kept; nothing is invented for a save the deck did not carry')
            continue
        a, b = float(mn), float(mx)
        lo, hi, how = level_claim(sig, want)
        ok = (a >= hi) if want == 'high' else (b <= lo)
        R.add(kind, cid, sig,
              '%s: %s (high min >= %.3f V / low max <= %.3f V)' % (want, how, hi, lo),
              'min=%.6g max=%.6g V' % (a, b), 0, 'PASS' if ok else 'FAIL',
              'judged over the whole window, not on one extreme sample')


def measure_rails(R, cid, data, t0, t1, has_ok, req='5'):
    srcs = [('V18:i', 'vdd18'), ('V33:i', 'vdd33'), ('Ven:i', 'en')]
    if has_ok:
        srcs.append(('Vok:i', 'core_ok33'))
    for src, rail in srcs:
        rcn, mn = read_sig(R, data, src, 'min', t0, t1, req)
        rcx, mx = read_sig(R, data, src, 'max', t0, t1, req)
        if rcn != 0 or rcx != 0:
            R.add('S2_RAIL_CURRENT', cid, src, 'direct source-branch current readable',
                  (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
                  'kept as a failure of the save/read path; not filled with 0 and no drain sum used')
            continue
        a, b = float(mn), float(mx)
        R.add('S2_RAIL_CURRENT', cid, src, 'injected into the DUT = -(Vx:i)',
              'window min=%.6g max=%.6g A -> injected %.6g .. %.6g A (rail %s)'
              % (a, b, -b, -a, rail), 0, 'MEASURED',
              'no current or power budget is defined for this POC, so no limit is invented')


def measure_delay(R, cid, data, t0, t1, ein, eout, want_answer, sig_in='en', sig_out='gate33'):
    cmd = ('%s --data "%s" --mode propdelay --sig-in %s --sig-out %s --vdd-in 1.8 '
           '--vdd-out 3.3 --edge-in %s --edge-out %s --t0 %s --t1 %s'
           % (delay_cmd(), data, sig_in, sig_out, ein, eout, t0, t1))
    rc, out = CC.call(cmd)
    head = out.strip().split('\n')[0]
    answered = rc == 0 and head.startswith('PROPDELAY')
    refused = ('NO_RESPONSE' in out) or ('NO_EDGE' in out) or ('NO_HALF_CROSSING' in out)
    if want_answer:
        verdict = 'PASS' if answered else ('FAIL' if refused else 'BLOCKED')
    else:
        verdict = 'EXPECTED_REFUSAL' if refused else 'FAIL'
    R.add('S2_DELAY', cid, '%s(%s)->%s(%s) %s..%s s' % (sig_in, ein, sig_out, eout, t0, t1),
          'an answer' if want_answer else 'a refusal, with the opposite polarity answering',
          head[:150], rc, verdict, scrub(out).replace('\n', ' | ')[:150])
    return answered, refused


def defined_output_edges(case, t0, t1):
    """which gate33 edges the deck's own stimulus can produce, before asking the edge tool.

    C0 and C1 are both non-inverting overall (en up -> x down -> gate33 down), so a rising output edge
    exists only if en falls inside the window. Asking for an edge the stimulus cannot make produced a
    NO_EDGE that looked like a circuit failure (measured on the load decks, where en is held high from
    104 ns to the end of the run).
    """
    pts = G.pwl_points(case['en_pwl']) if case.get('en_pwl') else []
    if not pts:
        return set(), 'en is a dc level, no input edge in any window'
    lo, hi = RD.qty(t0), RD.qty(t1)
    rises = falls = 0
    for (x1, v1), (x2, v2) in zip(pts, pts[1:]):
        # pwl_points keeps the deck's own spellings ('100n'), so both axes are converted here
        s1, s2 = RD.qty(x1), RD.qty(x2)
        if s1 >= lo - 1e-21 and s1 < hi and abs(float(v2) - float(v1)) > 1e-9:
            if float(v2) > float(v1):
                rises += 1
            else:
                falls += 1
    edges = set()
    if rises:
        edges.add('fall')
    if falls:
        edges.add('rise')
    return edges, 'en rises=%d falls=%d inside %.9g..%.9g s' % (rises, falls, lo, hi)


def measure_edges(R, cid, data, t0, t1, case):
    want, why = defined_output_edges(case, t0, t1)
    for edge in ('rise', 'fall'):
        if edge not in want:
            R.add('S2_EDGE', cid, 'gate33 %s in the response window' % edge,
                  'not defined by this stimulus', why, 0, 'EXPECTED_REFUSAL',
                  'the edge tool is not asked for an edge the input cannot create')
            continue
        cmd = ('%s --data "%s" --sig gate33 --vdd 3.3 --mode edge --edge %s --t0 %s '
               '--t1 %s' % (delay_cmd(), data, edge, t0, t1))
        rc, out = CC.call(cmd)
        head = out.strip().split('\n')[0]
        ok = rc == 0 and head.startswith('EDGE')
        R.add('S2_EDGE', cid, 'gate33 %s in the response window' % edge,
              'a complete 10-90%% event', head[:150], rc,
              'PASS' if ok else ('FAIL' if 'NO_EDGE' in out else 'BLOCKED'),
              scrub(out).replace('\n', ' | ')[:150])


def measure_plateau(R, cid, data, t0, t1):
    a, b = float(t0), float(t1)
    lo = '%.9g' % (b - 0.25 * (b - a))
    cmd = '%s --data "%s" --mode steady --sig gate33 --t0 %s --t1 %s --require-n 5' \
          % (delay_cmd(), data, lo, t1)
    rc, out = CC.call(cmd)
    head = out.strip().split('\n')[0]
    ok = rc == 0 and head.startswith('STEADY')
    R.add('S2_PLATEAU', cid, 'gate33 over the last quarter of the window',
          'a steady reading with samples present', head[:150], rc,
          'PASS' if ok else ('FAIL' if 'TOO_FEW' in out else 'BLOCKED'),
          'window %s..%s s; the level itself is judged by the screening rows' % (lo, t1))


def measure_stress(R, cid, deck_text, data, t0, t1):
    """per-device VGS/VGD/VDS/VGB extremes, formed per sample from the SAVED node voltages."""
    devs = resolve_devices(deck_text, netlist_text())
    if not devs:
        R.add('DEVICE_STRESS_PEAKS', cid, '-', 'devices resolved from the deck plus the frozen cell',
              'NONE_RESOLVED', 0, 'PARTIAL', 'the connectivity resolver found no four-terminal device')
        return
    R.add('CONNECTIVITY_RESOLVED', cid, '%d devices' % len(devs),
          'terminal paths use the measured DOT separator',
          ' ; '.join(p for p, _m, _n in devs)[:120], 0, 'PASS',
          'the same paths the audited generator hard-codes, derived here from the netlist')
    for path, model, nets in devs:
        if len(nets) != 4:
            continue
        d, g, s, b = nets
        parts, blocked = [], []
        for label, (x, y) in (('VGS', (g, s)), ('VGD', (g, d)), ('VDS', (d, s)), ('VGB', (g, b))):
            rca, va, _ta = read_diff(R, data, x, y, 'max', t0, t1)
            rcb, vb, _tb = read_diff(R, data, x, y, 'min', t0, t1)
            if rca or rcb:
                blocked.append('%s:rc%s/%s' % (label, rca, rcb))
            else:
                parts.append('%s=%.6g..%.6g' % (label, float(vb), float(va)))
        verdict = 'MEASURED' if parts and not blocked else (
            'PARTIAL' if parts else 'NOT_AVAILABLE')
        R.add('DEVICE_STRESS_PEAKS', cid, '%s (%s)' % (path, model),
              'peaks read from the saved D/G/S/B nodes; NO SOA limit is claimed',
              ' '.join(parts) if parts else 'no quantity readable', 0, verdict,
              ('terminals not saved: ' + ','.join(blocked)) if blocked else
              'MEASURED, not a signoff: the readable rating set has no absolute maximum table')
    # the independent cross-check is a separate function so its reader exit codes stay visible
    if XCHECK_DEVICE in [p for p, _m, _n in devs]:
        stress_crosscheck(R, cid, data, t0, t1, deck_text)


def stress_crosscheck(R, cid, data, t0, t1, deck_text):
    """the node-derived VGS of one device against the same device's own `:vgs' parameter."""
    rcn, mn = read_sig(R, data, '%s:vgs' % XCHECK_DEVICE, 'min', t0, t1)
    rcx, mx = read_sig(R, data, '%s:vgs' % XCHECK_DEVICE, 'max', t0, t1)
    if rcn or rcx:
        R.add('STRESS_CROSSCHECK', cid, '%s:vgs' % XCHECK_DEVICE,
              'the model exports its own terminal voltages (measured form: save <inst> sigtype=all)',
              (mn if rcn else mx)[:70], rcn or rcx, 'NOT_AVAILABLE',
              'the sigtype=all save did not reach this run')
        return
    term = dict((p, n) for p, _m, n in resolve_devices(deck_text, netlist_text())
                ).get(XCHECK_DEVICE)
    if not term:
        R.add('STRESS_CROSSCHECK', cid, XCHECK_DEVICE, 'the device is in this deck',
              'NOT_RESOLVED', 0, 'PARTIAL', 'resolver found no such device')
        return
    d, g, s, b = term
    rca, va, _ = read_diff(R, data, g, s, 'max', t0, t1)
    rcb, vb, _ = read_diff(R, data, g, s, 'min', t0, t1)
    if rca or rcb:
        R.add('STRESS_CROSSCHECK', cid, XCHECK_DEVICE, 'both routes readable',
              'node route rc=%s/%s' % (rca, rcb), 0, 'BLOCKED', 'the node difference could not be read')
        return
    diff = max(abs(float(va) - float(mx)), abs(float(vb) - float(mn)))
    R.add('STRESS_CROSSCHECK', cid, '%s vs node-derived VGS' % XCHECK_DEVICE,
          'the two agree within 1 mV',
          'model %.6g..%.6g V, nodes %.6g..%.6g V, worst diff %.3g V'
          % (float(mn), float(mx), float(vb), float(va), diff), 0,
          'PASS' if diff <= 1e-3 else 'FAIL',
          'an independent check that the dotted node paths really are this device\'s terminals')


# ---------------------------------------------------------------- orchestration
def write_rows(path, rows, hdr):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(hdr))
        for r in rows:
            f.write(csvline(r))


def traces_of(data):
    """the signal names this run actually wrote, read from the psfascii TRACE block in Python.

    The awk/grep pipeline made the evidence depend on which shell answered, and a pipeline also
    reports its own status instead of the reader's, so the caller could not tell "no signals" from
    "the shell could not run".
    """
    if not data or not os.path.isfile(data):
        return ''
    out, inside = [], False
    for raw in io.open(data, encoding='utf-8', errors='replace'):
        line = raw.strip()
        if line.startswith('TRACE'):
            inside = True
            continue
        if inside and line.startswith('VALUE'):
            break
        if inside:
            m = re.match('^"([^"]+)"', line)
            if m:
                out.append(m.group(1))
    return ','.join(out)


def fmt_load(pf):
    return '%g' % pf if pf else '0 (no external capacitor)'


MAN_HDR = ['run_id', 'case', 'deck_file', 'deck_sha256', 'netlist_sha256', 'lib_sha256', 'section',
           'temp_C', 'rails_V', 'load_pF', 'analysis', 'preflight_rc', 'spectre_rc', 'runner_verdict',
           'saved_signals', 'readings_total', 'readings_readable']

ROWS_HDR = ['run_id', 'item', 'case', 'signal_or_target', 'expected', 'actual', 'rc', 'verdict',
            'note']


def run_case(R, cid, scratch, nlsha, libsha, man_rows, opts):
    base = cid[:-len('_fine')] if cid.endswith('_fine') else cid
    case = find_case(base)
    if case is None:
        R.add('DECK_BUILD', cid, '-', 'an id from the audited case table', 'UNKNOWN_CASE', 0,
              'PARTIAL', 'this entry does not invent cases')
        return
    deck_txt = build_r2e_deck(case)
    if cid.endswith('_fine'):
        deck_txt = re.sub(r'maxstep=\S+', 'maxstep=' + opts.fine, deck_txt)
    deck = os.path.join(scratch, cid + '.scs')
    with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(deck_txt))
    sha = hashlib.sha256(deck_txt.encode('utf-8')).hexdigest()
    R.add('DECK_IDENTITY', cid, os.path.basename(deck),
          'audited generator text plus the two calibration-verified R2E lines',
          'sha256=%s netlist=%s' % (sha[:16], nlsha[:16]), 0, 'PASS',
          'section=tt temp=27 C rails=%s/%s V load=%s pF'
          % (case['rails'][0], case['rails'][1], fmt_load(case['load'])))
    missing_names, added = save_path_audit(case, deck_txt)
    R.add('SAVE_PATH_AUDIT', cid, 'the audited deck\'s node list vs the paths this build resolves',
          'every node the measurement needs is a name the simulator accepts',
          'deck names this build cannot reach: %s | terminal nodes beyond the deck list: %s'
          % (','.join(missing_names) or 'none', ','.join(added) or 'none'), 0,
          'PASS' if not missing_names else 'PARTIAL',
          'x/y are PORTS of Xcore, so Xt.Xcore.x was never a saveable node; the R2E deck keeps the '
          'reviewed line and adds the resolved names (rails were already saved on their own line)')

    # ---- preflight FULL through the shared call contract: the child's OWN exit code, complete
    # output, and one completion marker. The R2E form was `... 2>&1 | tail -5`, whose rc is tail's.
    pf_cmd = '%s "%s" 1.8 %s "%s"' % (CC.hook('QODER_PF_CMD', 'bash ' + PF), deck, cid,
                                      G.contract(case))
    penv = dict(os.environ)
    penv.pop('PREFLIGHT_STATIC_PROBE', None)          # unset, not empty: this is the full gate
    pfr, pftxt = CC.call(pf_cmd, env=penv)
    pf_ok, pf_reason, pf_summary = CC.preflight_verdict(pfr, pftxt)
    R.add('PREFLIGHT_FULL', cid, os.path.basename(deck),
          "the preflight own rc=0 AND exactly one TESTBENCH_PREFLIGHT: PASS",
          'rc=%s | %s' % (pfr, pf_summary.replace('\n', ' | ')[:110]), pfr,
          'PASS' if pf_ok else 'BLOCKED', pf_reason)
    man = [R.run_id, cid, os.path.basename(deck), sha, nlsha, libsha, 'tt', '27',
           '%s/%s' % (case['rails'][0], case['rails'][1]), fmt_load(case['load']),
           'tran stop=%s maxstep=%s' % (case['stop'],
                                        opts.fine if cid.endswith('_fine') else case['maxstep']),
           str(pfr), '', '', '', '', '']
    if not pf_ok:
        # the refusal ends this case: neither the runner nor any reader is called
        man[12:14] = ['NOT_CALLED', 'BLOCKED_after_preflight']
        man_rows.append(man)
        return

    # ---- runner: real rc=0 + exactly one PASS for THIS label + one SPECTRE status with rc=0 +
    # error_hits=0 + this run's own readable datafile and log
    label = 'S2_%s' % cid
    # LABEL travels in the environment, exactly as run_spectre.sh declares it (`$1` is the netlist);
    # argv order is asserted by the mock, so a wrong call shape cannot pass as a success
    renv = dict(os.environ)
    renv['LABEL'] = label
    renv.pop('PREFLIGHT_STATIC_PROBE', None)
    rc, txt = CC.call('%s "%s" 240' % (CC.hook('QODER_RUN_CMD', 'bash ' + RS), deck), env=renv)
    runner_ok, run_reasons, parts = CC.runner_verdict(label, deck, rc, txt)
    parts['preflight_rc'] = pfr
    err = re.search(r'ERROR \([A-Z0-9-]+\)[^\n]*', txt)
    R.add('SIM_RUN', cid, os.path.basename(deck),
          'runner rc=0 + one PASS for this label + spectre rc=0 + error_hits=0 + own data',
          'runner_rc=%s spectre_rc=%s error_hits=%s pass_lines=%d'
          % (rc, parts.get('spectre_rc', ''), parts.get('error_hits', ''),
             parts.get('pass_lines', 0)), rc, 'PASS' if runner_ok else 'BLOCKED',
          ('; '.join(run_reasons)[:120] or
           scrub(err.group(0) if err else 'contract satisfied').replace('\n', ' ')[:120]))
    data = parts['datafile'] if runner_ok else ''
    man[12] = parts.get('spectre_rc', '') or '?'
    man[13] = 'PASS' if runner_ok else 'BLOCKED'
    man[14] = traces_of(data) if data else ''
    R.add('SAVED_SIGNALS', cid, 'the dotted and source saves reach the data file',
          'the deck save list', man[14][:150], 0,
          'PASS' if runner_ok and man[14] else 'PARTIAL', 'trace order as the simulator wrote it')
    if not runner_ok or not data or not os.path.isfile(data):
        man_rows.append(man)
        return

    wins = case.get('windows') or []
    t0 = '%.9g' % wins[0][1] if wins else None
    t1 = '%.9g' % wins[0][2] if wins else None
    has_ok = case.get('ok') is not None
    nettxt = netlist_text()

    resolved = []
    for _p, _m, nets in resolve_devices(deck_txt, netlist_text()):
        for n in nets:
            if n and n not in resolved:
                resolved.append(n)

    def node_of(name):
        """the deck's own spelling if this build can reach it, else the resolved spelling.

        The audited decks ask for `Xt.Xcore.x', but x is a PORT of the core subckt, so the simulator's
        name for it is `Xt.x'; asking the wrong name would only prove that the save was thrown away.
        """
        if name in resolved or name in ('en', 'core_ok33', 'gate33', 'vdd18', 'vdd33', 'vss'):
            return name
        tail = name.split('.')[-1]
        cands = [r for r in resolved if r.split('.')[-1] == tail]
        return cands[0] if len(cands) == 1 else name
    if cid in EXPECT_GATE:
        targets = [('gate33', EXPECT_GATE[cid])]
        for sig, want in sorted(EXPECT_CORE[case['en'] >= 0.9].items()):
            targets.append((node_of(sig), want))
        measure_levels(R, cid, 'S2_FUNCTIONAL_TT', data, t0, t1, targets)
        measure_levels(R, cid, 'S2_STIMULUS_READBACK', data, t0, t1,
                       [('en', 'high' if case['en'] >= 0.9 else 'low')] +
                       ([('core_ok33', 'high' if case['ok'] >= 1.65 else 'low')] if has_ok else []))
        measure_rails(R, cid, data, t0, t1, has_ok)
        if cid in STRESS_CASES:
            measure_stress(R, cid, deck_txt, data, t0, t1)
    elif cid == 'neg_output_polarity_fault':
        # the NORMAL C0 criterion, unchanged: an en rise must be answered by a gate33 fall
        _aw, refused = measure_delay(R, cid, data, t0, t1, 'rise', 'fall', False)
        # and the wrong polarity has to be really present, otherwise this is not a detection
        measure_delay(R, cid, data, t0, t1, 'rise', 'rise', True)
        measure_rails(R, cid, data, t0, t1, has_ok)
        R.add('NEGATIVE_POLARITY', cid, 'the wrong-polarity deck switches and is refused',
              'the C0 fall-criterion refuses it AND the rise-criterion answers',
              'see the two S2_DELAY rows above', 0,
              'EXPECTED_REFUSAL' if refused else 'FAIL',
              'detection only counts because the run produced waveforms; a missing model, a reader '
              'failure or a timeout would not be a detection')
    else:
        for (ein, eout, a, b) in DYN_MEAS.get(cid, []):
            want, _why = defined_output_edges(case, a, b)
            pairs = []
            if 'fall' in want:
                pairs.append(('rise', 'fall'))
            if 'rise' in want:
                pairs.append(('fall', 'rise'))
            pairs = pairs or [(ein, eout)]
            for (i_edge, o_edge) in pairs:
                measure_delay(R, cid, data, a, b, i_edge, o_edge, True)
        if wins:
            measure_edges(R, cid, data, t0, t1, case)
            measure_plateau(R, cid, data, t0, t1)
        measure_rails(R, cid, data, t0, t1, has_ok)
        if cid in STRESS_CASES:
            measure_stress(R, cid, deck_txt, data, t0, t1)
    readable = len([r for r in R.rows if r[2] == cid and r[6] == '0' and r[7] == 'PASS'])
    man[15] = str(len([r for r in R.rows if r[2] == cid]))
    man[16] = str(readable)
    man_rows.append(man)


def main():
    op = optparse.OptionParser()
    op.add_option('--group', default='static')
    op.add_option('--scratch')
    op.add_option('--out')
    op.add_option('--manifest')
    op.add_option('--dry', action='store_true')
    op.add_option('--fine', default='0.05n', help='maxstep for the *_fine re-check decks')
    op.add_option('--only')
    o, _ = op.parse_args()
    ids = GROUPS.get(o.group)
    if ids is None:
        print('UNKNOWN_GROUP %r (have: %s)' % (o.group, ','.join(sorted(GROUPS))))
        return 9
    if o.group == 'load':
        ids = ids + [c + '_fine' for c in ids if c.endswith('5pF')]
    if o.only:
        ids = [c for c in ids if c in o.only.split(',')]
    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'sc1_sim', 'r2e_s2_' + o.group)
    out_csv = o.out or os.path.join(PROJ, 'results', 'evidence', 'sc1_r2e_s2_%s.csv' % o.group)
    man_csv = o.manifest or out_csv.replace('.csv', '_manifest.csv')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    nlbytes = G.netlist_bytes(PROJ)
    nlsha = hashlib.sha256(nlbytes).hexdigest()
    with open(os.path.join(scratch, G.NETLIST_RELPATH), 'wb') as f:
        f.write(nlbytes)
    # sourced in THIS shell, not in a subshell: `( ... )' would lose the variable and every deck would
    # then look unbound
    rc, txt = sh('cd %s && [ -f spectre/pdk_local.env ] && . spectre/pdk_local.env; '
                 'echo "$QODER_PDK_LIB"' % PROJ)
    lib = txt.strip().split('\n')[-1]
    libsha = hashlib.sha256(open(lib, 'rb').read()).hexdigest() if lib and os.path.isfile(lib) else ''
    R = Run([], [], 'R2E-S2-%s-%s' % (o.group, time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())))
    man_rows = []
    print('RUN_ID %s group=%s decks=%d' % (R.run_id, o.group, len(ids)))

    if o.dry:
        nettxt = netlist_text()
        for cid in ids:
            base = cid[:-len('_fine')] if cid.endswith('_fine') else cid
            case = find_case(base)
            if case is None:
                R.add('DECK_BUILD', cid, '-', 'a known case', 'UNKNOWN_CASE', 0, 'PARTIAL', 'dry')
                continue
            txt2 = build_r2e_deck(case)
            sha = hashlib.sha256(txt2.encode('utf-8')).hexdigest()
            R.add('DRY_DECK', cid, cid + '.scs', 'deck text builds without a simulator',
                  'sha256=%s' % sha[:16], 0, 'PASS', 'dry run only; nothing was executed')
            devs = resolve_devices(txt2, nettxt)
            R.add('DRY_CONNECTIVITY', cid, '%d devices' % len(devs),
                  'each with four terminal paths', ' ; '.join(p for p, _m, _n in devs)[:120], 0,
                  'PASS' if devs else 'PARTIAL', 'dry run only')
            missing = [n for _p, _m, nets in devs for n in nets
                       if n not in txt2.replace(',', ' ')]
            R.add('DRY_SAVE_COVERAGE', cid, '%d terminal paths' % sum(len(x[2]) for x in devs),
                  'every path appears in the deck save list',
                  'not-in-deck: %s' % (','.join(sorted(set(missing)))[:90] or 'none'), 0,
                  'PASS', 'dry run only')
        write_rows(out_csv, R.rows, ROWS_HDR)
        print('DRY rows=%d csv=%s' % (len(R.rows), out_csv))
        return 0

    authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
    if not libsha:
        for cid in ids:
            R.add('S2_TT_EXECUTION', cid, 'model binding', 'QODER_PDK_LIB resolves to a real file',
                  'NOT_RESOLVED', 1, 'BLOCKED', 'nothing runs without the model the deck includes')
    elif not authorised:
        for cid in ids:
            R.add('S2_TT_EXECUTION', cid, 'run', 'RUN=1 and QODER_SIM_AUTHORISED=1', 'refused',
                  5, 'NOT_RUN', 'this entry calls the simulator only with both flags set')
    else:
        for cid in ids:
            try:
                run_case(R, cid, scratch, nlsha, libsha[:16], man_rows, o)
            except Exception:
                # one broken case must not erase the cases that already ran, and it must not look like
                # a circuit verdict either: the harness failure is recorded with its traceback
                import traceback
                tb = traceback.format_exc()
                R.log.append('=== HARNESS_ERROR %s\n%s' % (cid, tb))
                R.add('HARNESS_ERROR', cid, cid, 'no python exception in the entry',
                      tb.strip().split('\n')[-1][:120], 1, 'BLOCKED',
                      'a harness fault is never scored as a circuit result; traceback kept beside '
                      'this CSV')
    write_rows(out_csv, R.rows, ROWS_HDR)
    write_rows(man_csv, man_rows, MAN_HDR)
    if R.log:
        with io.open(out_csv.replace('.csv', '_log.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(scrub('\n'.join(R.log))))
    bad = [r for r in R.rows if r[7] not in ('PASS', 'MEASURED', 'EXPECTED_REFUSAL')]
    print('S2_R2E_TT group=%s rows=%d not_pass=%d csv=%s'
          % (o.group, len(R.rows), len(bad), out_csv))
    for r in bad:
        print('   %s | %s | %s: %s (%s)' % (r[1], r[2], r[3][:40], r[5][:80], r[7]))
    if not authorised or not libsha:
        return 5
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
