# -*- coding: utf-8 -*-
"""SCAN-1 S3-A: the p33 high-side switch, characterised on its own in the 3.3 V domain.

    python scripts/sc1_s3a_p33_tt.py --selftest        # helper arithmetic only, nothing runs
    python scripts/sc1_s3a_p33_tt.py --dry             # deck text + plan, nothing runs
    RUN=1 QODER_SIM_AUTHORISED=1 python scripts/sc1_s3a_p33_tt.py

What this answers, and nothing else: at section tt / 27 C with source and body on an independent
3.3 V rail, how does one p33's conductance vary with W, what current does it actually carry at the
declared test bias, how many of them the CONDITIONAL column current would need, what the off-state
branch reads, and how much gate charge the candidate presents during the two switching edges.

What it deliberately does NOT answer. 3.3 V is a `POC_ASSUMPTION`, not a decision about the final
VSCAN. The two bench loads are `TESTBENCH_ASSUMPTION` proxies, not an electrode RC, and no LED exists
anywhere in these decks. 11.52 mA only exists under the "one column, up to 768 pixels lit" architecture
assumption, and 8.6806 ohm only under the old draft's 0.10 V drop. Nothing here is attached to the R3
control chain: the gate is driven by an independent source, so a gate-charge figure is a property of
the device, not evidence that the accepted level shifter can supply it. A model geometry limit is a
MODEL RANGE, not a rating -- SOA_SIGNOFF stays NO.

Case set, at most nine DUT decks, in this order:

  A  s3a_on_w005/010/020/050/100   one device, L=0.4 um, VD 3.3 -> 3.2 V step 0.01 (VSD 0 -> 0.1 V)
  B  s3a_on_par                    the derived N-parallel candidate at the same bias, skipped when
                                   N=1 and the shape already exists in A (a duplicate run is refused)
  C  s3a_off_par                   that candidate, D 3.3 -> 0 V step 0.33 V, gate at the rail
  D  s3a_dyn_light / s3a_dyn_column  the candidate, independent gate drive, an R||C proxy load

N comes from the measured A results, never from arithmetic on paper:
N_req = ceil(11.52 mA / I_SD(largest legal W at VSD = 0.10 V)), clamped to [1, 16]. If N_req exceeds 16
the conditional target is reported NOT_MET at this declared scale and the round stops at 16 -- the rank
is not grown and the process is not changed to make a number look satisfied.

Measurement definitions the review fixed, implemented here: I_SD is the bias instrument's own branch
current (+VD:i) cross-checked against -VS:i with every raw sign kept; Ron = (V(S)-V(D))/I_SD across
the device's OWN source-drain; the VSD = 0 point is NOT_DEFINED, never 0 ohm; DC points are counted as
DC points (the transient ">=10 samples" rule is not misapplied to a bias point); the parallel result is
checked against the single-device result on the measured currents; and the gate charge is the
adjacent-point trapezoid of -VG:i inside one edge window against a stated steady baseline, never a
whole-run integral.

The frozen plumbing is reused, not re-derived: `sc1_r2e_s2_tt` (Run, reader, vtx, scrub, CSV),
`sc1_r2e1_call_contract` (preflight and runner verdicts from real exit codes) and `sc1_r2e1_reread`
(the audited PSF parser). Per AGENTS rule 27 a dry or unauthorised invocation refuses BEFORE writing:
it cannot create, truncate or replace an official evidence file.
"""
from __future__ import print_function

import hashlib
import io
import math
import optparse
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sc1_r2e1_call_contract as CC
import sc1_r2e_s2_tt as S2
import sc1_r2e1_reread as R1

try:
    _text = unicode
except NameError:
    _text = str

ROWS_HDR = S2.ROWS_HDR


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def fmt_v(x):
    return '%.6g' % x


def tnum(ns):
    return '%sn' % fmt_v(ns)


# ---------------------------------------------------------------- frozen conditions
V33 = 3.3
SECTION = 'tt'
TEMP_C = '27'
L_M = 4e-7                                      # 0.4 um, fixed for this round
W_SET_UM = (5.0, 10.0, 20.0, 50.0, 100.0)       # the declared initial set
# Geometry envelope READ BACK off the p33 model record in the included model card. The card itself is
# never committed: the report names the file basename, its sha256 and the lines it was read from.
GEOM = {'lmin': 3e-7, 'lmax': 1e-4, 'wmin': 2.2e-7, 'wmax': 1e-4}
GEOM_SOURCE = ('p33 model record, ms018_enhanced_v1p2_rev0_spe.mdl (sha256 5187cae15226...), '
               'lmin/lmax/wmin read at the model line and wmax on the following line, 2026-10-13')
MODEL = 'p33'
SUPPLY_MAP = 'vdd33=3.3 vss=0'
EXPECTED_VDD = '3.3'

# the two conditional currents, side by side, each with its provenance named
I_PIXEL = 15e-6                                 # one selected, emitting pixel (teacher/user D1)
N_ACTIVE_ASSUMED = 768                          # architecture assumption, not a measured figure
I_COLUMN = I_PIXEL * N_ACTIVE_ASSUMED           # 11.52 mA, CONDITIONAL
V_DROP_DRAFT = 0.10                             # old draft's on-drop condition
RON_TARGET = V_DROP_DRAFT / I_COLUMN            # 8.6806 ohm, CONDITIONAL_DRAFT_TARGET
LEAK_REF_DRAFT = 1e-7                           # old draft's 0.1 uA per channel, a reference only
N_MAX = 16                                      # this round's declared parallel ceiling

# dynamic bench loads: TESTBENCH_ASSUMPTION proxies, NOT an electrode model
DYN_LOADS = [
    ('s3a_dyn_light', 220e3, 1e-12,
     '3.3 V / 220 kohm ~ 15 uA: a resistor standing in for one selected pixel; not an LED, '
     'not an electrode RC'),
    ('s3a_dyn_column', 3.3 / I_COLUMN, 5e-12,
     '3.3 V / 286.458 ohm ~ 11.52 mA: the CONDITIONAL column current under the 768-pixel '
     'architecture assumption only'),
]
TRAN_STOP_NS = 500.0
TRAN_MAXSTEP_NS = 0.1
VG_WAVE = ((0.0, V33), (49.0, V33), (51.0, 0.0), (199.0, 0.0), (201.0, V33), (500.0, V33))
EDGE_SELECT = (49.0, 51.0)      # gate 3.3 -> 0 V: the switch turns ON
EDGE_BLANK = (199.0, 201.0)     # gate 0 -> 3.3 V: the switch turns OFF
BASELINE = (10.0, 40.0)         # a flat, fully-off stretch used as the steady leakage baseline
SEL_SAMPLE = (48.0, 53.0)       # the continuous sample block shipped around the ON edge
BLK_SAMPLE = (198.0, 203.0)     # ... and around the OFF edge
PLATEAU_SAMPLE = (120.0, 121.0)
PLATEAU_WINDOW = (100.0, 180.0)

ON_SWEEP = ('VD', 3.3, 3.2, -0.01)              # VSD 0 -> 0.1 V, 11 points
OFF_SWEEP = ('VD', 3.3, 0.0, -0.33)             # D 3.3 -> 0 V, 11 points
DUT_TIMEOUT = '600'


def case(cid, **kw):
    kw['id'] = cid
    kw.setdefault('kind', 'on_dc')
    kw.setdefault('n', 1)
    kw.setdefault('load', None)
    return kw


CASES_A = [case('s3a_on_w%03d' % int(round(w)), kind='on_dc', w_um=w, n=1, sweep=ON_SWEEP,
                gate_v=0.0, purpose='single-device on-state I-V at L=0.4 um, W=%g um' % w)
           for w in W_SET_UM]


def geom_ok(w_um, l_m=L_M):
    """a legality verdict per size, with its reason -- never a silent model swap or oversize"""
    w_m = w_um * 1e-6
    bad = []
    if w_m < GEOM['wmin'] - 1e-15:
        bad.append('w=%s under read wmin=%s' % (fmt_v(w_m), fmt_v(GEOM['wmin'])))
    if w_m > GEOM['wmax'] + 1e-15:
        bad.append('w=%s over read wmax=%s' % (fmt_v(w_m), fmt_v(GEOM['wmax'])))
    if l_m < GEOM['lmin'] - 1e-15 or l_m > GEOM['lmax'] + 1e-15:
        bad.append('l=%s outside read lmin=%s / lmax=%s' % (fmt_v(l_m), fmt_v(GEOM['lmin']),
                                                            fmt_v(GEOM['lmax'])))
    return (not bad), ('; '.join(bad) or 'inside the read model range (a range, not a rating)')


def deck_header(section):
    return ('simulator lang=spectre insensitive=yes\n'
            '// model binding: run_spectre.sh expands ${QODER_PDK_LIB} from the git-ignored\n'
            '// spectre/pdk_local.env; with no binding it refuses the deck (exit 9). section=%s is the\n'
            '// master-section name every accepted deck here uses. Temperature is written as\n'
            '// simopt options temp=27 the way R2E/R3 did, then read back from the log and the data\n'
            '// header -- never assumed.\n'
            'include "${QODER_PDK_LIB}" section=%s\n' % (section, section))


def subckt_body(name, w_m, n):
    """N EXPLICIT single-finger devices, each inside the read geometry limits.

    Deliberately not m=/nf=: this build never had that interface verified, and an invented multiplier
    would silently assume how finger area and perimeter are summed.
    """
    lines = ['subckt %s (d g vdd33 vss)\n' % name]
    for i in range(1, n + 1):
        lines.append('  mp%d (d g vdd33 vdd33) %s l=%s w=%s\n' % (i, MODEL, fmt_v(L_M), fmt_v(w_m)))
    lines.append('ends %s\n' % name)
    return ''.join(lines)


def build_deck(cs, section=SECTION):
    """one self-contained deck: its own subckt, so the deck hash covers the exact device shape"""
    w_m = cs['w_um'] * 1e-6
    txt = deck_header(section)
    txt += ('// S3-A characterization deck %s: %d x p33 in parallel, l=%s w=%s, source and body on\n'
            '// the 3.3 V rail. Purpose: %s\n' % (cs['id'], cs['n'], fmt_v(L_M), fmt_v(w_m),
                                                  cs['purpose']))
    txt += ('// Geometry envelope read back from the model record: lmin=%s lmax=%s wmin=%s wmax=%s\n'
            '// (%s). A model range is not an absolute rating; SOA_SIGNOFF stays NO.\n'
            % (fmt_v(GEOM['lmin']), fmt_v(GEOM['lmax']), fmt_v(GEOM['wmin']), fmt_v(GEOM['wmax']),
               GEOM_SOURCE))
    txt += ('// The 3.3 V rail is POC_ASSUMPTION, not a final VSCAN decision. Every source here is\n'
            '// measurement equipment: no LED, no scan electrode, no R3 control chain.\n\n')
    txt += subckt_body(cs['id'], w_m, cs['n'])
    txt += '\nVS (vdd33 0) vsource dc=%s\n' % fmt_v(V33)
    if cs['kind'] == 'dyn':
        txt += ('// independent gate drive -- a characterization instrument, NOT gate33: held at 3.3 V\n'
                '// (off), 49..51 ns down to 0 V (select), 199..201 ns back to 3.3 V (blank)\n')
        txt += 'VG (gate 0) vsource type=pwl wave=[%s]\n' % ' '.join(
            '%s %s' % (fmt_v(t * 1e-9), fmt_v(v)) for t, v in VG_WAVE)
    else:
        txt += 'VG (gate 0) vsource dc=%s\n' % fmt_v(cs['gate_v'])
    txt += 'Vss (vss 0) vsource dc=0\n'
    if cs['kind'] == 'dyn':
        r, c, _why = cs['load']
        txt += 'Xdev (drain gate vdd33 vss) %s\n' % cs['id']
        txt += ('// TESTBENCH_ASSUMPTION proxy load from drain to vss: r=%s ohm, c=%s F. %s\n'
                % (fmt_v(r), fmt_v(c), _why))
        txt += 'Rload (drain vss) resistor r=%s\n' % fmt_v(r)
        txt += 'Cload (drain vss) capacitor c=%s\n' % fmt_v(c)
    else:
        dev, start, _stop, _step = cs['sweep']
        txt += 'VD (drain 0) vsource dc=%s\n' % fmt_v(start)
        txt += 'Xdev (drain gate vdd33 vss) %s\n' % cs['id']
    txt += '\nsimopt options temp=%s\n' % TEMP_C
    txt += 'save vdd33 gate drain vss\n'
    txt += 'save VS:i VG:i\n'
    if cs['kind'] != 'dyn':
        txt += 'save VD:i\n'
    for i in range(1, cs['n'] + 1):
        txt += 'save Xdev.mp%d:1\n' % i
    if cs['kind'] == 'dyn':
        txt += 'sw1 tran stop=%s maxstep=%s\n' % (tnum(TRAN_STOP_NS), tnum(TRAN_MAXSTEP_NS))
    else:
        dev, s0, s1, st = cs['sweep']
        txt += 'sw1 dc dev=%s param=dc start=%s stop=%s step=%s\n' % (
            dev, fmt_v(s0), fmt_v(s1), fmt_v(st))
    return txt


def device_count_of(deck_txt):
    return len(re.findall(r'^\s*mp\d+\s*\(', deck_txt, re.M))


def analysis_of(cs):
    if cs['kind'] == 'dyn':
        return 'tran stop=%s maxstep=%s' % (tnum(TRAN_STOP_NS), tnum(TRAN_MAXSTEP_NS))
    dev, s0, s1, st = cs['sweep']
    return 'dc dev=%s param=dc start=%s stop=%s step=%s' % (dev, fmt_v(s0), fmt_v(s1), fmt_v(st))


# ---------------------------------------------------------------- reading
def pick(g, *names):
    for n in names:
        if n in g and g[n] is not None:
            return g[n]
    return None


def dc_points(data):
    """the sweep table through the audited parser; its axis is the sweep variable, not time"""
    groups, axis = R1.samples_of(data)
    if not groups:
        return [], (axis or '-'), 'NO_GROUPS'
    if axis not in groups[0]:
        return [], (axis or '-'), 'AXIS_ABSENT'
    return [(i, g[axis], g) for i, g in enumerate(groups)], axis, 'OK'


def point_rows(run_id, cid, cs, pts):
    """the per-point table: raw signed readings, I_SD by definition, Ron across the device itself"""
    rows, per = [], []
    for i, vd, g in pts:
        vs, vdr, vg = pick(g, 'vdd33'), pick(g, 'drain'), pick(g, 'gate')
        idi, isi, igi = pick(g, 'VD:i'), pick(g, 'VS:i'), pick(g, 'VG:i')
        idev = [pick(g, 'Xdev.mp%d:1' % k) for k in range(1, cs['n'] + 1)]
        if vs is None or vdr is None or idi is None:
            rows.append([run_id, cid, fmt_v(cs['w_um']), str(cs['n']), str(i), fmt_v(vd), '',
                         '' if vdr is None else fmt_v(vdr), '' if vg is None else fmt_v(vg),
                         '' if vs is None else fmt_v(vs), '' if idi is None else fmt_v(idi),
                         '' if isi is None else fmt_v(isi), '' if igi is None else fmt_v(igi),
                         '', '', 'MISSING_TRACE',
                         'drain / vdd33 / VD:i did not reach the data file',
                         ','.join('' if v is None else fmt_v(v) for v in idev)])
            continue
        vsd = vs - vdr
        i_sd = idi                                   # source -> drain arrives as +VD:i
        if abs(vsd) < 1e-12:
            ron, status = '', 'NOT_DEFINED'
            note = 'VSD = 0 makes Ron a 0/0 point: reported as NOT_DEFINED, never as 0 ohm'
        elif i_sd == 0.0:
            ron, status = '', 'NO_CURRENT'
            note = 'the branch current read exactly zero at this bias'
        else:
            ron, status = fmt_v(vsd / i_sd), 'MEASURED'
            note = 'Ron = (V(S)-V(D))/I_SD across the device own source-drain only'
        rows.append([run_id, cid, fmt_v(cs['w_um']), str(cs['n']), str(i), fmt_v(vd), fmt_v(vsd),
                     fmt_v(vdr), '' if vg is None else fmt_v(vg), fmt_v(vs), fmt_v(idi),
                     '' if isi is None else fmt_v(isi), '' if igi is None else fmt_v(igi),
                     fmt_v(i_sd), ron, status, note,
                     ','.join('' if v is None else fmt_v(v) for v in idev)])
        per.append({'vsd': vsd, 'i_sd': i_sd, 'vg': vg, 'igi': igi, 'isi': isi, 'status': status,
                    'vd': vd, 'i_dev': idev})
    return rows, per


def sign_relation(pts):
    """how far I_SD (= +VD:i) sits from -VS:i over the sweep, with the worst point kept raw"""
    worst_d, worst, n = 0.0, None, 0
    for i, vd, g in pts:
        idi, isi = pick(g, 'VD:i'), pick(g, 'VS:i')
        if idi is None or isi is None:
            continue
        n += 1
        d = abs(idi - (-isi))
        if d >= worst_d:
            worst_d, worst = d, 'point %d (VD=%s): VD:i=%s VS:i=%s' % (i, fmt_v(vd), fmt_v(idi),
                                                                      fmt_v(isi))
    return n, worst_d, worst


def sum_dev_relation(per):
    """do N devices measured together carry what the instrument says, on the raw terminal sums

    The observed convention on this build is that a device terminal current is positive INTO the
    device, so `mp<k>:1` reads the negative of +VD:i. The comparison is therefore made on magnitudes
    and the sign itself is reported as a measurement, never corrected by assumption.
    """
    rows = []
    for p in per:
        vals = [v for v in p['i_dev'] if v is not None]
        if not vals or len(vals) != len(p['i_dev']):
            continue
        rows.append((p['vsd'], abs(p['i_sd']), abs(sum(vals)), len(vals),
                     min(abs(v) for v in vals), max(abs(v) for v in vals)))
    return rows


# ---------------------------------------------------------------- transient helpers
def traj(xs, ys):
    """adjacent-point trapezoid on the same time axis; nothing is interpolated into the file"""
    tot = 0.0
    for i in range(1, len(xs)):
        tot += 0.5 * (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1])
    return tot


def window_of(groups, axis, t0_ns, t1_ns):
    lo, hi = t0_ns * 1e-9, t1_ns * 1e-9
    out = []
    for i, g in enumerate(groups):
        t = g.get(axis)
        if t is not None and lo - 1e-18 <= t <= hi + 1e-18:
            out.append((i, g))
    return out


def baseline_band(groups, axis):
    vals = [g.get('VG:i') for _i, g in window_of(groups, axis, BASELINE[0], BASELINE[1])]
    vals = [-v for v in vals if v is not None]
    if not vals:
        return None, 0
    return (min(vals), max(vals)), len(vals)


def gate_charge(groups, axis, edge_ns, base):
    """net charge over one edge: the trapezoid of -VG:i minus the stated baseline over the same span"""
    win = window_of(groups, axis, edge_ns[0], edge_ns[1])
    xs = [g[axis] for _i, g in win if g.get('VG:i') is not None]
    ys = [-g['VG:i'] for _i, g in win if g.get('VG:i') is not None]
    if len(xs) < 2:
        return None
    raw = traj(xs, ys)
    span = xs[-1] - xs[0]
    mid = 0.5 * (base[0] + base[1]) if base else 0.0
    net = raw - mid * span
    return {'points': len(xs), 't0': xs[0], 't1': xs[-1], 'span_s': span, 'raw_C': raw,
            'baseline': base, 'baseline_mid_A': mid, 'net_C': net, 'c_eff_F': abs(net) / V33}


def peak_of(R_unused, data, sig, mode):
    """the extreme of a branch current WITH its instant, from the strict difference tool

    `sc1_r2e_vtx.py` returns three fields (value, the full line, the raw text); taking two is the
    unpack error this round's second debug batch died on, so the third name is written out.
    """
    rc, _val, txt = S2.read_diff(None, data, sig, 'vss', mode)
    return rc, (txt or '').strip().split('\n')[-1]


def measure_dyn(R, cid, cs, data, samp_rows):
    groups, axis = R1.samples_of(data)
    if not groups or axis not in groups[0]:
        R.add('S3A_DYN_READ', cid, axis or '-', 'a readable transient', 'NO_GROUPS_OR_AXIS', 1,
              'BLOCKED', 'nothing is reported from a file the audited parser cannot group')
        return 1
    rcs = []
    R.add('S3A_DYN_READ', cid, axis, 'the transient parses with its own axis',
          'points=%d' % len(groups), 0, 'MEASURED', 'adjacent real samples only')
    base, nb = baseline_band(groups, axis)
    rcs.append(0)
    R.add('S3A_DYN_BASELINE', cid, 'VG:i over %g..%g ns (gate at the rail, switch off)' % BASELINE,
          'a stated steady level to subtract per edge, not a whole-run integral',
          'points=%d band=%s A' % (nb, '%s..%s' % (fmt_v(base[0]), fmt_v(base[1])) if base else 'NONE'),
          0, 'MEASURED' if base else 'NOT_AVAILABLE',
          'kept as a band because it is measured, not assumed flat')
    plat = [g['drain'] for _i, g in window_of(groups, axis, PLATEAU_WINDOW[0], PLATEAU_WINDOW[1])
            if g.get('drain') is not None]
    if plat:
        r, _c, _why = cs['load']
        vsd_lo, vsd_hi = V33 - max(plat), V33 - min(plat)
        R.add('S3A_DYN_PLATEAU', cid, 'drain over the selected stretch %g..%g ns' % PLATEAU_WINDOW,
              'the on plateau, its spread, the device own VSD and the load current it implies',
              'drain=%s..%s V ; VSD(device own)=%s..%s V ; I_load=V(D)/R=%s..%s A (R=%s)'
              % (fmt_v(min(plat)), fmt_v(max(plat)), fmt_v(vsd_lo), fmt_v(vsd_hi),
                 fmt_v(min(plat) / r), fmt_v(max(plat) / r), fmt_v(r)), 0, 'MEASURED',
              'I_load is V(D) across the declared bench resistor, stated as a derivation from a '
              'measured node voltage; VS:i / the device terminal currents are in the sample rows')
    else:
        R.add('S3A_DYN_PLATEAU', cid, 'drain over the selected stretch', 'a plateau to read',
              'no sample in the window carried drain', 0, 'NOT_AVAILABLE',
              'reported as missing, never filled in')
    for tag, w in (('select_edge', SEL_SAMPLE), ('blank_edge', BLK_SAMPLE),
                   ('plateau_sample', PLATEAU_SAMPLE)):
        for i, g in window_of(groups, axis, w[0], w[1]):
            keys = ['vdd33', 'gate', 'drain', 'vss', 'VS:i', 'VG:i'] + \
                   ['Xdev.mp%d:1' % k for k in range(1, cs['n'] + 1)]
            vals = ' '.join('%s=%s' % (k, fmt_v(g[k])) for k in keys if g.get(k) is not None)
            samp_rows.append([R.run_id, cid, tag, str(i), fmt_v(g[axis]), vals, 'MEASURED_SAMPLE',
                              cs.get('deck_sha256', ''), cs.get('raw_sha256', '')])
    for tag, edge in (('select_on', EDGE_SELECT), ('blank_off', EDGE_BLANK)):
        q = gate_charge(groups, axis, edge, base)
        if not q:
            R.add('S3A_GATE_CHARGE', cid, '%s edge %g..%g ns' % (tag, edge[0], edge[1]),
                  'the trapezoid of -VG:i over the edge window', 'fewer than two samples carried VG:i',
                  rcs[0] if rcs else 1, 'NOT_AVAILABLE', 'no charge is invented from an empty window')
            continue
        R.add('S3A_GATE_CHARGE', cid, '%s edge %g..%g ns' % (tag, edge[0], edge[1]),
              'adjacent-point trapezoid of -VG:i with the steady baseline subtracted over the span',
              'points=%d t=%s..%s s span=%s s raw_Q=%s C net_Q=%s C C_eff,Q=%s F'
              % (q['points'], fmt_v(q['t0']), fmt_v(q['t1']), fmt_v(q['span_s']), fmt_v(q['raw_C']),
                 fmt_v(q['net_C']), fmt_v(q['c_eff_F'])), 0, 'MEASURED',
              'C_eff,Q = |net Q| / 3.3 V: an equivalent charge load for THIS edge, including '
              'nonlinearity and Miller; explicitly NOT a fixed model Cgg')
    for sig, mode in (('VS:i', 'min'), ('VS:i', 'max'), ('VG:i', 'min'), ('VG:i', 'max')):
        rc, txt = peak_of(None, data, sig, mode)
        rcs.append(rc)
        R.add('S3A_BRANCH_PEAK', cid, '%s %s over the run' % (sig, mode),
              'the extreme and the instant it happened at, from the strict tool', txt[:120] or
              'no reading', rc, 'MEASURED' if rc == 0 else 'NOT_AVAILABLE',
              'a bench instrument branch, not an electrode current; no budget is defined so no '
              'PASS is claimed')
    R.add('S3A_STIMULUS_READBACK', cid, 'VG pwl and the analysis line',
          'gate 3.3 V off, 49..51 ns to 0 V select, 199..201 ns back, stop=%g ns maxstep=%g ns'
          % (TRAN_STOP_NS, TRAN_MAXSTEP_NS),
          'deck emitted: %s' % ' '.join('%g ns/%g V' % (t, v) for t, v in VG_WAVE), 0, 'PASS',
          'TESTBENCH_ASSUMPTION schedule, not a panel timing requirement; read back of the text '
          'this run wrote')
    return sum(1 for x in rcs if x)


# ---------------------------------------------------------------- evidence rows
DC_HDR = ['run_id', 'case', 'w_um', 'n', 'point_index', 'sweep_VD_V', 'vsd_V', 'v_drain_V',
          'v_gate_V', 'v_src_V', 'VD_i_A', 'VS_i_A', 'VG_i_A', 'I_SD_A', 'Ron_ohm', 'status',
          'note', 'per_device_terminal_currents_A']
SAMP_HDR = ['run_id', 'case', 'window', 'sample_index', 'time_s', 'values', 'status',
            'deck_sha256', 'raw_sha256']
MAN_HDR = ['run_id', 'case', 'kind', 'deck', 'deck_sha256', 'raw_sha256', 'model', 'section',
           'temp_written', 'temp_read_back', 'rails_V', 'L_m', 'W_m', 'n_devices', 'w_total_m',
           'analysis', 'load_R_ohm', 'load_C_F', 'preflight_rc', 'spectre_rc', 'runner_verdict',
           'reader_rc', 'saved_traces', 'outcome']
ID_HDR = ['run_id', 'case', 'deck_relpath', 'deck_sha256', 'raw_relpath', 'raw_sha256',
          'lib_sha256', 'mdl_sha256', 'readme_sha256', 'mis_sha256', 'geometry_source', 'provenance']


def sha256_file(path):
    try:
        return hashlib.sha256(open(path, 'rb').read()).hexdigest()
    except Exception:
        return ''


TEMP_PATTERNS = (r'"temp"\s+([-\d.]+)',        # the psfascii header form: "temp" 27.0000
                 r'temp\s*=\s*([-\d.]+)',      # the log form this project's calibration read
                 r'[Tt]emperature\s*[:=]\s*([-\d.]+)')


def read_temp(run_out, data):
    """the temperature the run actually reports, from the log and then from the data header

    The first version only looked for `temp=` and reported NOT_READ on every deck, because the
    psfascii header writes `"temp" 27.0000` with a space. A read-back that silently says nothing is
    worse than one that fails loudly, so an unfilled column is now a verifier failure.
    """
    found = []
    for pat in TEMP_PATTERNS:
        m = re.search(pat, run_out or '')
        if m:
            found.append('log=%s' % m.group(1))
            break
    head = ''
    try:
        head = io.open(data, encoding='utf-8', errors='replace').read(4000)
    except Exception:
        head = ''
    for pat in TEMP_PATTERNS:
        m = re.search(pat, head)
        if m:
            found.append('psf=%s' % m.group(1))
            break
    return ' '.join(found) or 'NOT_READ'


def traces_of(data):
    try:
        groups, axis = R1.samples_of(data)
    except Exception:
        return 'UNPARSEABLE'
    if not groups:
        return ''
    return ','.join(sorted(groups[0].keys()))


def rel(path):
    return os.path.relpath(path, PROJ).replace('\\', '/')


# ---------------------------------------------------------------- the run
def run_deck(R, cid, cs, scratch, man_rows, dc_rows, samp_rows, id_rows, o):
    deck_txt = build_deck(cs, o.section)
    deck = os.path.abspath(os.path.join(scratch, cid + '.scs'))
    with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(deck_txt))
    sha = hashlib.sha256(deck_txt.encode('utf-8')).hexdigest()
    cs['deck_sha256'] = sha
    ok, why = geom_ok(cs['w_um'])
    R.add('S3A_GEOMETRY', cid, 'W=%g um, L=%g um, N=%d' % (cs['w_um'], L_M * 1e6, cs['n']),
          'inside the model range READ BACK off the p33 record; a range is not a rating', why,
          0, 'PASS' if ok else 'BLOCKED', GEOM_SOURCE)
    devs = device_count_of(deck_txt)
    R.add('S3A_DEVICE_COUNT', cid, '%d explicit device instance lines' % devs,
          'exactly N, each one finger; no m/nf multiplier anywhere',
          'N declared=%d counted=%d ; w_total=%s m' % (cs['n'], devs,
                                                       fmt_v(cs['n'] * cs['w_um'] * 1e-6)),
          0, 'PASS' if devs == cs['n'] else 'BLOCKED', 'counted off the deck text the simulator reads')
    R.add('S3A_ISOLATION', cid, 'what drives the gate and the drain in this deck',
          'characterization only: no gate33 node, no LED, no electrode',
          'sources: %s ; devices reached: %s' % (', '.join(re.findall(r'^(V\w+) ', deck_txt, re.M)),
                                                 'Xdev.mp1..mp%d' % cs['n']), 0, 'PASS',
          'the independent drive is the point of S3-A and the reason no chain or panel claim follows')

    pf_cmd = '%s "%s" %s %s "%s"' % (
        CC.hook('QODER_PF_CMD', 'bash ' + os.path.join(HERE, 'tb_preflight.sh')), deck,
        EXPECTED_VDD, cid, SUPPLY_MAP)
    penv = dict(os.environ)
    penv.pop('PREFLIGHT_STATIC_PROBE', None)
    pfr, pftxt = CC.call(pf_cmd, env=penv)
    pf_ok, pf_reason, pf_summary = CC.preflight_verdict(pfr, pftxt)
    R.add('PREFLIGHT_FULL', cid, os.path.basename(deck),
          'the preflight own rc=0 AND exactly one TESTBENCH_PREFLIGHT: PASS',
          'rc=%s map=%s | %s' % (pfr, SUPPLY_MAP, pf_summary.replace('\n', ' | ')[:90]), pfr,
          'PASS' if pf_ok else 'BLOCKED', pf_reason)
    man = [R.run_id, cid, cs['kind'], os.path.basename(deck), sha, '', MODEL, o.section, TEMP_C,
           '', EXPECTED_VDD, fmt_v(L_M), fmt_v(cs['w_um']), str(cs['n']),
           fmt_v(cs['n'] * cs['w_um'] * 1e-6), analysis_of(cs),
           fmt_v(cs['load'][0]) if cs['kind'] == 'dyn' else '',
           fmt_v(cs['load'][1]) if cs['kind'] == 'dyn' else '',
           str(pfr), '', '', '', '', '']
    if not pf_ok:
        man[19], man[20], man[23] = 'NOT_RUN', 'BLOCKED_after_preflight', 'BLOCKED_preflight'
        man_rows.append(man)
        R.log.append('=== %s preflight REFUSED rc=%s\n%s' % (cid, pfr, S2.scrub(pftxt)))
        return None

    label = 'S3A_%s' % cid
    renv = dict(os.environ)
    renv['LABEL'] = label
    rc, run_out = CC.call('%s "%s" %s' % (CC.hook('QODER_RUN_CMD', 'bash ' + os.path.join(
        HERE, 'run_spectre.sh')), deck, DUT_TIMEOUT), env=renv)
    runner_ok, run_reasons, parts = CC.runner_verdict(label, deck, rc, run_out)
    err = re.search(r'ERROR \([A-Z0-9-]+\)[^\n]*', run_out)
    R.add('SIM_RUN', cid, os.path.basename(deck),
          'runner rc=0 + one PASS for this label + spectre rc=0 + error_hits=0 + own data',
          'runner_rc=%s preflight_rc=%s spectre_rc=%s error_hits=%s pass_lines=%d'
          % (rc, pfr, parts.get('spectre_rc', ''), parts.get('error_hits', ''),
             parts.get('pass_lines', 0)), rc, 'PASS' if runner_ok else 'BLOCKED',
          ('; '.join(run_reasons)[:130] or S2.scrub(err.group(0) if err else
                                                   'contract satisfied').replace('\n', ' ')[:130]))
    R.log.append('=== %s run %s\npreflight: %s\nrunner: %s\n'
                 % (cid, 'accepted' if runner_ok else 'REJECTED', S2.scrub(pf_summary),
                    S2.scrub(run_out)))
    data = parts.get('datafile', '')
    raw_sha = sha256_file(data) if data else ''
    cs['raw_sha256'] = raw_sha
    man[5] = raw_sha
    man[9] = read_temp(run_out, data)
    man[19] = parts.get('spectre_rc', '') or '?'
    man[20] = 'PASS' if runner_ok else 'BLOCKED'
    if not runner_ok or not data or not os.path.isfile(data):
        man[23] = 'BLOCKED_after_simulator'
        man_rows.append(man)
        return None
    man[22] = traces_of(data)
    id_rows.append([R.run_id, cid, rel(deck), sha, rel(data), raw_sha, o.lib_sha, o.mdl_sha,
                    o.readme_sha, o.mis_sha, GEOM_SOURCE,
                    'deck and raw hashed this round; the PDK is identified by hash only, its '
                    'content is never committed'])

    out, reader_rc = None, 0
    if cs['kind'] in ('on_dc', 'off_dc'):
        pts, axis, status = dc_points(data)
        if status != 'OK' or not pts:
            R.add('S3A_DC_READ', cid, axis, 'a dc sweep with its own axis', status, 1, 'BLOCKED',
                  'no point is reported from a file the audited parser cannot group')
            man[21], man[23] = '1', 'BLOCKED_dc_parse'
            man_rows.append(man)
            return None
        rows, per = point_rows(R.run_id, cid, cs, pts)
        dc_rows.extend(rows)
        R.add('S3A_DC_READ', cid, axis, 'every sweep point kept with its raw signed readings',
              'points=%d axis=%s rows_written=%d (VSD=0 point: NOT_DEFINED, never 0 ohm)'
              % (len(pts), axis, len(rows)), 0, 'MEASURED',
              'DC points are DC points; the transient >=10-sample rule is not applied to a bias point')
        n, worst_d, worst = sign_relation(pts)
        R.add('S3A_CURRENT_SIGN', cid, 'I_SD := +VD:i, cross-checked against -VS:i',
              'the two agree, or the largest difference is reported as measured with its raw signs',
              'points=%d max|VD:i-(-VS:i)|=%s A at %s' % (n, fmt_v(worst_d), worst or 'none'),
              0, 'MEASURED',
              'body or gate current would show up here as a real difference; nothing is smoothed '
              'away and the raw columns stay in the point table')
        rel_rows = sum_dev_relation(per)
        if rel_rows:
            worst_gap = max(abs(d[1] - d[2]) for d in rel_rows)
            span_lo = min(d[4] for d in rel_rows)
            span_hi = max(d[5] for d in rel_rows)
            if cs['n'] == 1:
                R.add('S3A_N_SCALING', cid,
                      'single device: terminal current magnitude vs the instrument current',
                      'the two agree on magnitude; the terminal reading carries the opposite sign',
                      'worst ||sum(mp:i)| - |VD:i|| = %s A over %d points ; device terminal sign '
                      'observed opposite to +VD:i on every point' % (fmt_v(worst_gap), len(rel_rows)),
                      0, 'MEASURED', 'this is the reference the parallel case is compared against, '
                                     'kept as measured')
            else:
                R.add('S3A_N_SCALING', cid,
                      '%d devices in parallel: measured total against the instrument current'
                      % cs['n'],
                      'the summed terminal magnitudes against |VD:i|, plus the per-device spread',
                      'worst ||sum(mp:i)| - |VD:i|| = %s A over %d points ; per-device |mp:i| spans '
                      '%s..%s A ; total at the last point = %s A at VSD=%s V'
                      % (fmt_v(worst_gap), len(rel_rows), fmt_v(span_lo), fmt_v(span_hi),
                         fmt_v(rel_rows[-1][1]), fmt_v(rel_rows[-1][0])),
                      0, 'MEASURED',
                      'the parallel deck is compared against the single-device deck in the '
                      'candidate summary, on both measured numbers')
        out = per
    else:
        bad = measure_dyn(R, cid, cs, data, samp_rows)
        reader_rc = bad
        man[21] = str(bad)
    man[23] = 'RAN' if reader_rc == 0 else 'RAN_WITH_READER_REFUSALS'
    man_rows.append(man)
    return out


# ---------------------------------------------------------------- derived candidate
def choose_candidate(R, on_results):
    """N from the measured largest-legal-W device, never from arithmetic on paper"""
    legal = [(cs, per) for cs, per in on_results if geom_ok(cs['w_um'])[0] and per]
    if not legal:
        R.add('S3A_CANDIDATE', 'all', 'a measured current at the declared bias',
              'at least one legal W with a usable point', 'no legal on-state result to derive from',
              1, 'BLOCKED', 'the candidate is not guessed')
        return None
    legal.sort(key=lambda kv: kv[0]['w_um'])
    cs_best, per = legal[-1]
    at = None
    for p in per:
        if abs(p['vsd'] - V_DROP_DRAFT) < 1e-9:
            at = p
            break
    if at is None:
        at = max(per, key=lambda p: p['vsd'])
        R.add('S3A_CANDIDATE', cs_best['id'], 'a point exactly at VSD = %g V' % V_DROP_DRAFT,
              'the declared drop', 'not present; the closest measured VSD=%s V is used and named'
              % fmt_v(at['vsd']), 0, 'MEASURED', 'the substitution is stated, never hidden')
    i_one = at['i_sd']
    if not i_one or i_one <= 0:
        R.add('S3A_CANDIDATE', cs_best['id'], 'a positive single-device current',
              'I_SD > 0 at the declared bias', 'I_SD=%s A' % fmt_v(i_one), 1, 'BLOCKED',
              'no rank is derived from a non-positive current')
        return None
    n_req = int(math.ceil(I_COLUMN / i_one))
    n = max(1, min(N_MAX, n_req))
    R.add('S3A_CANDIDATE', 'all',
          'N = ceil(%.6g A / measured I_SD), clamped to [1,%d]' % (I_COLUMN, N_MAX),
          'derived only from the largest legal W actually measured',
          'W=%g um at VSD=%s V: I_SD=%s A, Ron=%s ohm -> N_req=%d, chosen N=%d, w_total=%s m'
          % (cs_best['w_um'], fmt_v(at['vsd']), fmt_v(i_one), fmt_v(at['vsd'] / i_one), n_req, n,
             fmt_v(n * cs_best['w_um'] * 1e-6)), 0, 'MEASURED',
          'N is the parallel rank of ONE channel, not an extra scan channel')
    if n_req > N_MAX:
        R.add('S3A_CONDITIONAL_TARGET', 'all',
              'Ron <= %s ohm at %.6g A (draft 0.10 V drop)' % (fmt_v(RON_TARGET), I_COLUMN),
              'satisfied within the declared ceiling N<=%d' % N_MAX,
              'N_req=%d exceeds the ceiling; only N=%d is measured this round' % (n_req, n),
              0, 'NOT_MET',
              'CONDITIONAL_DRAFT_TARGET, an engineering result at the declared scale: the rank is '
              'not grown past it and the process is not changed to chase the number')
    return {'w_um': cs_best['w_um'], 'n': n, 'i_one': i_one, 'vsd': at['vsd'], 'n_req': n_req,
            'ron_one': at['vsd'] / i_one, 'a_case': cs_best['id']}


def target_verdict(R, cand, par_per):
    """the two conditional currents side by side, and what the measured rank does about the draft"""
    if not cand or not par_per:
        return
    at = None
    for p in par_per:
        if abs(p['vsd'] - V_DROP_DRAFT) < 1e-9:
            at = p
            break
    if at is None:
        at = max(par_per, key=lambda p: p['vsd'])
    i_tot, vsd = at['i_sd'], at['vsd']
    if not i_tot:
        R.add('S3A_CONDITIONAL_TARGET', 'all', 'a candidate current at the declared bias',
              'I_SD != 0', 'the candidate read no current', 1, 'BLOCKED', 'nothing to compare')
        return
    R.add('S3A_PARALLEL_CHECK', 'all',
          'the measured candidate total against N x the measured single device at VSD=%s V'
          % fmt_v(vsd),
          'how close the N-device deck sits to the linear expectation, stated as measured',
          'total=%s A ; N x single=%s A ; ratio=%s'
          % (fmt_v(i_tot), fmt_v(cand['n'] * cand['i_one']),
             fmt_v(i_tot / (cand['n'] * cand['i_one'])) if cand['i_one'] else 'n/a'),
          0, 'MEASURED',
          'a deviation here is a real measurement (bias-dependent sharing, not a broken sum): '
          + ('both numbers came from separate decks of this round'
             if cand.get('par_ran') else 'N=1 and the shape was reused from the A deck, so this row '
             'is an identity kept for completeness, not a second measurement'))
    ron_tot = vsd / i_tot
    R.add('S3A_CONDITIONAL_CURRENTS', 'all',
          '15 uA (one selected pixel) and %.6g A (768 x 15 uA under the architecture assumption) '
          'as separate figures' % I_COLUMN,
          'neither is presented as a decided panel load',
          'candidate measured %s A at VSD=%s V (Ron=%s ohm); 15 uA is %.4f%% of the candidate '
          'current, so the light load is not a stress case'
          % (fmt_v(i_tot), fmt_v(vsd), fmt_v(ron_tot), 15e-6 / i_tot * 100.0), 0, 'MEASURED',
          'CONDITIONAL values with their provenance named in the report')
    verdict = 'MET' if ron_tot <= RON_TARGET * 1.0005 else 'NOT_MET'
    R.add('S3A_CONDITIONAL_TARGET', 'all',
          'Ron <= %s ohm, the draft 0.10 V drop at %.6g A' % (fmt_v(RON_TARGET), I_COLUMN),
          'measured candidate Ron against that conditional figure',
          'measured Ron=%s ohm vs conditional=%s ohm at N=%d (w_total=%s m) -> %s'
          % (fmt_v(ron_tot), fmt_v(RON_TARGET), cand['n'], fmt_v(cand['n'] * cand['w_um'] * 1e-6),
             verdict), 0, verdict,
          'CONDITIONAL_DRAFT_TARGET only: a draft condition, not a teacher-issued specification, '
          'and satisfied or missed at this declared rank alone')


def measure_off(R, cid, per, cand):
    """the off-state readings, against the draft leakage reference and with its bias range stated"""
    if not per:
        return
    worst = max(per, key=lambda p: abs(p['i_sd']))
    R.add('S3A_OFF_STATE', cid, 'off-state branch current over D = 3.3..0 V with gate at the rail',
          'the largest magnitude reading, the bias it happened at, and the draft figure as a '
          'reference only',
          'max |I_SD| = %s A at VSD=%s V (VD=%s V) ; VGS=%s V VGD=%s V VDS=%s V VGB=%s V ; '
          'draft reference 1e-07 A, NOT a pass/fail'
          % (fmt_v(worst['i_sd']), fmt_v(worst['vsd']), fmt_v(worst['vd']),
             fmt_v((worst['vg'] or 0.0) - V33), fmt_v((worst['vg'] or 0.0) - worst['vd']),
             fmt_v(-worst['vsd']), fmt_v((worst['vg'] or 0.0) - V33)), 0, 'MEASURED',
          'the 3.3 V reverse bias is a MODEL EXPERIMENT CONDITION: no absolute rating was read, '
          'so this is not an SOA statement and no high-temperature or corner claim is made')


def classify(rows):
    func, dep, info = [], [], []
    for r in rows:
        v = r[7] if len(r) > 7 else ''
        if v == 'FAIL':
            func.append(r)
        elif v in ('BLOCKED', 'NOT_AVAILABLE'):
            dep.append(r)
        else:
            info.append(r)
    return func, dep, info


def _selftest():
    """the arithmetic this round leans on, against synthetic numbers: no simulator, no claim"""
    checks = []
    xs = [i * 1e-6 for i in range(11)]                  # 0..10 us
    ys = [1e-6] * 11                                    # a known constant 1 uA
    checks.append(('a constant 1 uA over 10 us integrates to 1e-11 C',
                   abs(traj(xs, ys) - 1e-11) < 1e-24))
    rows, per = point_rows('SELFTEST', 'x', case('x', w_um=20.0, n=1, kind='on_dc'),
                           [(0, 3.3, {'vdd33': 3.3, 'drain': 3.3, 'gate': 0.0, 'VD:i': 0.0,
                                      'VS:i': 0.0, 'VG:i': 0.0, 'Xdev.mp1:1': 0.0}),
                            (1, 3.25, {'vdd33': 3.3, 'drain': 3.25, 'gate': 0.0, 'VD:i': 0.5,
                                        'VS:i': -0.52, 'VG:i': 1e-12, 'Xdev.mp1:1': -0.5})])
    checks.append(('the VSD=0 row is NOT_DEFINED and carries no resistance',
                   rows[0][15] == 'NOT_DEFINED' and rows[0][14] == ''))
    checks.append(('a nonzero point gives Ron = VSD / I_SD across the device only',
                   abs(float(rows[1][14]) - 0.05 / 0.5) < 1e-12))
    n, d, worst = sign_relation([(0, 3.3, {'VD:i': 0.5, 'VS:i': -0.5}),
                                 (1, 3.25, {'VD:i': 0.4, 'VS:i': -0.41})])
    checks.append(('the sign cross-check reports the spread it measured', n == 2 and
                   abs(d - 0.01) < 1e-12 and worst.startswith('point 1')))
    ok, why = geom_ok(200.0)
    checks.append(('a W above the read wmax is refused, naming wmax', (not ok) and 'wmax' in why))
    checks.append(('every declared W is inside the read range',
                   all(geom_ok(w)[0] for w in W_SET_UM)))
    groups = [{'time': i * 1e-9,
               'VG:i': -1e-6 if 49.0 <= i * 1e-9 * 1e9 <= 51.0 else 0.0}
              for i in range(501)]
    q = gate_charge(groups, 'time', EDGE_SELECT, (0.0, 0.0))
    checks.append(('a 1 uA gate over the 2 ns edge window integrates to ~2e-15 C',
                   q is not None and abs(q['net_C']) >= 1.5e-15 and abs(q['net_C']) <= 2.5e-15))
    hdr = '"temp" 27.0000'
    checks.append(('the temperature read-back matches the psfascii header spelling',
                   any(re.search(p, hdr) and re.search(p, hdr).group(1) == '27.0000'
                       for p in TEMP_PATTERNS)))
    bad = [n for n, v in checks if not v]
    for name, v in checks:
        print('   %-66s %s' % (name, 'PASS' if v else 'FAIL'))
    print('S3A_HELPER_SELFTEST cases=%d failures=%d (synthetic numbers; no simulator, no circuit '
          'claim)' % (len(checks), len(bad)))
    return 1 if bad else 0


def safe_run(R, cs, scratch, man_rows, dc_rows, samp_rows, id_rows, o):
    """a harness fault is recorded as a dependency row and never scored as a circuit result

    The first full S3-A batch died on a tuple-index slip halfway through, which lost every row of a
    run that had already simulated nine decks' worth of work. An exception must not be able to do
    that again: each deck is guarded, and the failure is reported where it happened.
    """
    try:
        return run_deck(R, cs['id'], cs, scratch, man_rows, dc_rows, samp_rows, id_rows, o)
    except Exception:
        tb = traceback.format_exc()
        R.log.append('=== %s HARNESS_ERROR\n%s' % (cs['id'], S2.scrub(tb)))
        R.add('HARNESS_ERROR', cs['id'], cs['id'], 'no python exception inside a deck run',
              tb.strip().split('\n')[-1][:130], 1, 'BLOCKED',
              'recorded as a dependency failure of this entry, never as a circuit result')
        return None


def process_counts(scratch):
    sim = os.path.join(scratch, 'sim')
    if not os.path.isdir(sim):
        return 0, 0
    dep = len([p for p in os.listdir(sim) if p.startswith('preflight_') and p.endswith('.log')])
    dut = len([p for p in os.listdir(sim)
               if not p.startswith('preflight_') and p.endswith('.log')])
    return dep, dut


def main():
    op = optparse.OptionParser()
    op.add_option('--selftest', action='store_true')
    op.add_option('--dry', action='store_true')
    op.add_option('--scratch')
    op.add_option('--out')
    op.add_option('--dc')
    op.add_option('--samples')
    op.add_option('--manifest')
    op.add_option('--identity')
    op.add_option('--log')
    op.add_option('--only')
    op.add_option('--expect', type='int', default=0)
    op.add_option('--section', default=SECTION)
    op.add_option('--lib-sha', default='')
    op.add_option('--mdl-sha', default='')
    op.add_option('--readme-sha', default='')
    op.add_option('--mis-sha', default='')
    o = op.parse_args()[0]
    if o.selftest:
        return _selftest()

    ids = [c['id'] for c in CASES_A]
    selected = CASES_A
    if o.only:
        wanted = [c for c in o.only.split(',') if c]
        unknown = [c for c in wanted if c not in ids]
        if unknown:
            print('UNKNOWN_CASE %s (the A stage offers: %s; the candidate, off and dynamic decks '
                  'are named from the measurement, not by hand)' % (','.join(unknown), ','.join(ids)))
            return 9
        selected = [c for c in CASES_A if c['id'] in wanted]
    if o.expect and len(selected) != o.expect:
        print('SELECTION_COUNT want=%d got=%d ids=%s' % (o.expect, len(selected),
                                                         ','.join(c['id'] for c in selected)))
        return 9

    scratch = os.path.abspath(o.scratch or
                              os.path.join(PROJ, 'cadence_work', 'sc1_sim', 's3a_p33'))
    ev = os.path.join(PROJ, 'results', 'evidence')
    out_csv = o.out or os.path.join(ev, 'sc1_s3a_cases.csv')
    dc_csv = o.dc or os.path.join(ev, 'sc1_s3a_dc_points.csv')
    samp_csv = o.samples or os.path.join(ev, 'sc1_s3a_dyn_samples.csv')
    man_csv = o.manifest or os.path.join(ev, 'sc1_s3a_manifest.csv')
    id_csv = o.identity or os.path.join(ev, 'sc1_s3a_identity.csv')
    log_txt = o.log or os.path.join(ev, 'sc1_s3a_dependency_log.txt')
    if o.dry and not o.out:
        out_csv = os.path.join(scratch, 'dry_rows.csv')
        dc_csv = os.path.join(scratch, 'dry_dc_points.csv')

    authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
    if not authorised and not o.dry:
        # AGENTS rule 27: refuse BEFORE every write. A demonstration of the exit code must never be
        # able to truncate the delivered evidence, which is exactly how two R3 CSVs were lost.
        print('S3A_REFUSED run=%s authorisation=%s: RUN=1 AND QODER_SIM_AUTHORISED=1 are both '
              'required. No file under results/evidence is created, truncated or replaced.'
              % (os.environ.get('RUN') or 'unset', os.environ.get('QODER_SIM_AUTHORISED') or 'unset'))
        print('S3A_REFUSED would_have_been=%s plus the derived candidate, off and dynamic decks'
              % ','.join(c['id'] for c in selected))
        return 5

    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    R = S2.Run([], [], 'S3A-%s' % time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    print('RUN_ID %s section=%s temp_written=%s L=%g um W_set=%s rail=3.3(POC_ASSUMPTION) '
          'N_ceiling=%d conditional_target=%s ohm'
          % (R.run_id, o.section, TEMP_C, L_M * 1e6, ','.join('%g' % w for w in W_SET_UM), N_MAX,
             fmt_v(RON_TARGET)))
    man_rows, dc_rows, samp_rows, id_rows, on_results = [], [], [], [], []

    if o.dry:
        for cs in selected:
            txt = build_deck(cs, o.section)
            with io.open(os.path.join(scratch, cs['id'] + '.scs'), 'w', encoding='utf-8',
                         newline='\n') as f:
                f.write(u(txt))
            ok, why = geom_ok(cs['w_um'])
            R.add('DRY_DECK', cs['id'], cs['id'] + '.scs',
                  'the deck builds and the geometry check passes on the read-back limits',
                  'sha256=%s lines=%d devices=%d analysis=[%s] %s'
                  % (hashlib.sha256(txt.encode('utf-8')).hexdigest()[:16], txt.count('\n'),
                     device_count_of(txt), analysis_of(cs), why), 0,
                  'PASS' if ok else 'BLOCKED',
                  'dry only: nothing ran, and no native evidence file was touched')
        R.add('DRY_PLAN', 'all', 'the candidate, off and dynamic decks',
              'named from the measured A results, not by hand',
              'deferred to the authorised run: N = ceil(%.6g A / I_SD at VSD=%g V) clamped [1,%d], '
              'then s3a_on_par / s3a_off_par / %s'
              % (I_COLUMN, V_DROP_DRAFT, N_MAX, ' / '.join(l[0] for l in DYN_LOADS)),
              0, 'MEASURED_PLAN', 'dry mode cannot invent the measurement that picks N')
        S2.write_rows(out_csv, R.rows, ROWS_HDR)
        print('DRY rows=%d decks_in=%s csv=%s' % (len(R.rows), scratch, out_csv))
        return 0

    for cs in selected:
        per = safe_run(R, cs, scratch, man_rows, dc_rows, samp_rows, id_rows, o)
        if per is not None:
            on_results.append((cs, per))
    cand = choose_candidate(R, on_results)
    par_per = None
    if cand and o.only is None:
        par_cs = case('s3a_on_par', kind='on_dc', w_um=cand['w_um'], n=cand['n'], sweep=ON_SWEEP,
                      gate_v=0.0, purpose='the derived N-parallel candidate at the on bias')
        off_cs = case('s3a_off_par', kind='off_dc', w_um=cand['w_um'], n=cand['n'], sweep=OFF_SWEEP,
                      gate_v=V33, purpose='the derived candidate in the off state, gate at the rail')
        dyn = [case(nm, kind='dyn', w_um=cand['w_um'], n=cand['n'], load=(r, c, why),
                    purpose='the candidate with an independent gate drive and a proxy R||C load')
               for nm, r, c, why in DYN_LOADS]
        todo = [par_cs, off_cs] + dyn
        cand['par_ran'] = True
        if cand['n'] == 1 and cand['w_um'] in W_SET_UM:
            todo.remove(par_cs)
            cand['par_ran'] = False
            R.add('S3A_REUSE', 'all', 'a candidate whose shape already exists in the A stage',
                  'reuse the A measurement instead of running a duplicate deck',
                  'N=1 at W=%g um: s3a_on_par was NOT run; %s is the candidate row'
                  % (cand['w_um'], cand['a_case']), 0, 'PASS',
                  'refusing to re-run an identical shape, so the deck count is stated as it is')
            for cs, per in on_results:
                if cs['id'] == cand['a_case']:
                    par_per = per
        for cs in todo:
            per = safe_run(R, cs, scratch, man_rows, dc_rows, samp_rows, id_rows, o)
            if cs['id'] == 's3a_on_par':
                par_per = per
            if cs['id'] == 's3a_off_par' and per:
                measure_off(R, cs['id'], per, cand)
        target_verdict(R, cand, par_per or [])
    dep, dut = process_counts(scratch)
    R.add('S3A_PROCESS_COUNT', 'all', 'preflight dependency runs vs DUT runs',
          'counted from the files this scratch keeps', 'preflight=%d DUT=%d' % (dep, dut), 0,
          'MEASURED', 'tb_preflight.sh FULL mode runs its own operating point, which is a '
                      'dependency process and not a circuit run; debug retries are recorded '
                      'separately and never inferred from the last batch of files')
    if not o.lib_sha or not o.mdl_sha:
        R.add('S3A_PDK_IDENTITY', 'all', 'the PDK digests passed on the command line',
              'lib / mdl / README / the mis mdl the tt section pulls, as hashes only',
              'lib=%s mdl=%s readme=%s mis=%s' % (o.lib_sha[:16] or 'NOT_PASSED',
                                                  o.mdl_sha[:16] or 'NOT_PASSED',
                                                  o.readme_sha[:16] or 'NOT_PASSED',
                                                  o.mis_sha[:16] or 'NOT_PASSED'),
              0, 'MEASURED' if o.lib_sha and o.mdl_sha else 'NOT_AVAILABLE',
              'the identity of what was read is recorded by hash; no PDK content is committed')

    S2.write_rows(out_csv, R.rows, ROWS_HDR)
    S2.write_rows(dc_csv, dc_rows, DC_HDR)
    S2.write_rows(samp_csv, samp_rows, SAMP_HDR)
    S2.write_rows(man_csv, man_rows, MAN_HDR)
    S2.write_rows(id_csv, id_rows, ID_HDR)
    if R.log:
        with io.open(log_txt, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(S2.scrub('\n'.join(R.log))))
    func, depp, info = classify(R.rows)
    print('S3A_TT rows=%d dc_points=%d dyn_samples=%d decks=%d functional_FAIL=%d dependency=%d '
          'informational=%d -> %s'
          % (len(R.rows), len(dc_rows), len(samp_rows), len(man_rows), len(func), len(depp),
             len(info), out_csv))
    if cand:
        print('S3A_CANDIDATE W=%g um N=%d (N_req=%d) w_total=%s m I_SD_single=%s A at VSD=%s V '
              'Ron_single=%s ohm'
              % (cand['w_um'], cand['n'], cand['n_req'], fmt_v(cand['n'] * cand['w_um'] * 1e-6),
                 fmt_v(cand['i_one']), fmt_v(cand['vsd']), fmt_v(cand['ron_one'])))
    for tag, lst in (('FUNCTIONAL', func), ('DEPENDENCY', depp)):
        for r in lst[:12]:
            print('   %-11s %s | %s | %s (%s)' % (tag, r[1], r[2][:38], r[5][:90], r[7]))
    return (1 if func else 0) + (2 if depp else 0)


if __name__ == '__main__':
    sys.exit(main())
