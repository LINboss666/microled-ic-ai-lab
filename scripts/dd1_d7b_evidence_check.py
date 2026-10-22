# -*- coding: utf-8 -*-
"""DATA-7B evidence re-checker: does what was recorded match what the delivered bytes compute?

    python scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_<run_id>
    python scripts/dd1_d7b_evidence_check.py --selftest

It reads committed bytes only. It never opens a socket, never runs a simulator, and never writes to
the directory it is checking, so the reviewer can run it without a PDK.

The judgement is deliberately split: a faithfully recorded electrical FAIL still passes this checker,
while a FAIL written down as a PASS is refused. Re-computing a digest is not enough, because every
byte of a bundle can be made internally consistent while its numbers still mean something else, so
the semantics are re-derived as well:

  * the (case, window) matrix, the roles, modes, legal code domains, tick/window geometry, maxstep,
    ramp, clamp and convergence pairing are rebuilt from the frozen task tables, not read back from
    the bundle;
  * discrete fields are judged as mathematical values, so `30.5` in a whole-number column fails
    instead of being truncated into a pass, while a delivered sample time keeps its own precision;
  * charge and its positive/negative halves, the tail, the last 100 ns, the peak and its time, the
    declared crossings and the sustained-in-band verdict are recomputed from the delivered samples
    through the same measurement core the exporter uses;
  * the electrical verdict is re-derived under the frozen criteria, so no row can call a failing
    window a pass;
  * the wiring negative and the supply negative are bound to their own bytes, their own launch and
    their own deck difference;
  * the launch record is summed rather than trusted: the reconcile rows must add up to the TOTAL,
    and how many launches really have a ledger row behind them is reported instead of inferred.

`--selftest` replays the eight semantic counterfeits of the review against a disposable copy of a
committed bundle and requires each one to raise its own named failure. There is no SKIP path: a
missing fixture is a failure with rc 1.
"""
from __future__ import print_function

import decimal
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_measure as MS
import dd1_d7b_trace as TR

# the accepted DATA-7B bundle is what a re-emitted sample series is compared against, so its path is
# a fact of this repository rather than something a bundle can point at
ACCEPTED_BUNDLE_NAME = 'dd1_d7b_r11_main'
ACCEPTED_BUNDLE_DIR = os.path.join(PROJ, 'results', 'evidence', ACCEPTED_BUNDLE_NAME)
ACCEPTED_CACHE = {}
# the four-state re-verification is bounded by what the task grants and pinned to the frozen sources
MAX_RTL_SIMULATIONS = 17
RTL_SOURCE = os.path.join(PROJ, 'rtl', 'dd1_d7a_gray_ctrl.sv')
TB_SOURCE = os.path.join(PROJ, 'tests', 'dd1_d7b', 'tb_dd1_d7b_pwm.sv')
# a delivered gate transcript must not name the machine that ran it
LOCAL_PATH_RE = re.compile(r'(?i)([a-z]:[\\/]|/home/|/users/|\\\\)')

NS = 1000
FROZEN_CASE_TABLE = os.path.join(PROJ, 'tests', 'dd1_d7b', 'cases.csv')
FROZEN_GOLDEN_TABLE = os.path.join(PROJ, 'tests', 'dd1_d7b', 'golden_windows.csv')
# the criteria the task book freezes; this checker may not widen any of them
TOL_LSB = 0.5
OFF_LIMIT = 0.15e-6
ICAL_TARGET = 15e-6
ICAL_BAND_REL = 0.05
CONV_Q_LSB_REL = 0.01
CONV_EDGE_PS = 500
CEILING_TASKBOOK = 52
CEILING_GRANTED = 56
TAIL_NS = 200
# the deck's PWL is the RTL trace moved forward by this much, so a case window is the trace window
# plus it; dd1_d7b_run.py asserts its own constant equals these two
SHIFT_NS = 2500
SHIFT_PS = SHIFT_NS * NS
CAL_BAND = (3000000, 3500000)
CAL_OFF = (1500000, 1900000)
CAL_TAIL = (4400000, 4500000)
DE_50 = 0.9
# the account protocol's only legal states, spelled exactly as the writer spells them. The checker
# keeps its own copy because it must not import the tool it audits; dd1_d7b_run.py asserts in its
# self test that the two lists agree, so neither side can widen the other by accident.
ACCOUNT_STATES = ('REQUESTED', 'UNCERTAIN', 'CONFIRMED', 'COMPLETED', 'REFUSED_NO_LAUNCH')
PULSE_EDGE_TOLERANCE_PS = 50 * NS
# every time column of the case table is printed as '%.4f' of a nanosecond, so the most a printed
# claim can be away from the value the same arithmetic gives now is half of its last digit -- 0.05 ps.
# A crossing is therefore re-derived and compared in the time domain at that resolution; a value
# domain test would need a current or voltage tolerance, and a 20 mA one certified 15 uA crossings
# anywhere within 1.3 ms.
EDGE_CLAIM_TOL_PS = 0.05 + 1e-6
FORBIDDEN = ((r'/root/tech', 'the instructor PDK path'),
             (r'ms018_enhanced', 'a model card name'),
             (r'QODER_GUEST_PW', 'a credential variable'),
             (r'\.raw/psf', 'a raw PSF tree'))
NON_ELECTRICAL = ('BLOCKED', 'BLOCKED_BUDGET', 'FAIL_TOOL', 'UNCERTAIN_LAUNCH', 'REUSED')
# a re-simulated VCD is the bundle's own text: the four-state re-verification is only checkable
# if the bytes the edges came out of travel with the table that compares them
TEXT_SUFFIXES = ('.csv', '.json', '.txt', '.scs', '.md', '.log', '.vcd')


def u(s):
    if isinstance(s, str):
        return s
    return s.decode('utf-8', 'replace')


class Checks(object):
    def __init__(self):
        self.rows = []
        self.reasons = {}

    def add(self, name, ok, detail='', items=()):
        """record one check; `items' are the untruncated reasons, so a test can tell a new break

        The printed detail is cut short for a human, which is also why a counterfeit that lands on a
        check the delivered bundle already fails could otherwise hide behind the old reason.
        """
        self.rows.append((name, 'PASS' if ok else 'FAIL', detail))
        self.reasons[name] = [str(x) for x in items]
        return bool(ok)


def rows_of(path):
    if not os.path.isfile(path):
        raise MS.Refuse('%s is missing' % path)
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = [h.strip() for h in f.readline().strip().split(',')]
        out = []
        for line in f:
            if not line.strip():
                continue
            vals = [v.strip() for v in line.rstrip('\r\n').split(',')]
            if len(vals) != len(hdr):
                raise MS.Refuse('%s has a %d-field row against %d headers'
                                % (os.path.basename(path), len(vals), len(hdr)))
            out.append(dict(zip(hdr, vals)))
    if not out:
        raise MS.Refuse('%s has a header and no rows' % path)
    return out


def read_rows(path):
    """rows_of, but a missing or empty table returns [] so the caller can name the absence"""
    if not os.path.isfile(path):
        return []
    try:
        return rows_of(path)
    except MS.Refuse:
        return []


def num(txt):
    if txt is None or txt == '':
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def integer_value(txt):
    """the mathematical value of a discrete field, or None when it is not a whole number

    `int(float('30.5'))` quietly returns 30, which is how a half tick was accepted before: the value
    is decided as a decimal first and only then read as an integer.
    """
    s = str(txt or '').strip()
    if not re.match(r'^[+-]?\d+(\.\d+)?$', s):
        return None
    d = decimal.Decimal(s)
    if d != d.to_integral_value():
        return None
    return int(d)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def sci(txt):
    """a deck quantity such as `5e-10' or `1.1845e-05' in SI, or None"""
    s = str(txt or '').strip()
    if not re.match(r'^[+-]?\d*\.?\d+([eE][+-]?\d+)?$', s):
        return None
    return float(s)


def deck_field(deck_text, pattern):
    """the first statement line carrying a field, with comment lines excluded

    The delivered decks carry a comment that quotes `options temp=27' as an example of a syntax this
    build rejects, so a whole-file search reads that comment instead of the statement.
    """
    for line in (deck_text or '').split('\n'):
        s = line.strip()
        if not s or s.startswith('//'):
            continue
        m = re.search(pattern, s)
        if m:
            return m.group(1)
    return ''


def pwl_points_of(text):
    pts = []
    for line in (text or '').split('\n'):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            return None
        t, v = integer_value(parts[0]), num(parts[1])
        if t is None or v is None:
            return None
        pts.append((t, v))
    return pts


def deck_wave_points(text):
    """the `(time_ps, volt)' pairs a deck's `wave=[...]' clause really carries"""
    clause = deck_field(text, r'wave=\[([^\]]*)\]')
    if clause == '':
        return None if deck_field(text, r'type=pwl') else []
    toks = clause.split()
    pts = []
    for i in range(0, len(toks) - 1, 2):
        t, v = toks[i], num(toks[i + 1])
        if t.endswith('n'):
            base = num(t[:-1])
            ps = int(round(base * NS)) if base is not None else None
        else:
            ps = integer_value(t)
        if ps is None or v is None:
            return None
        pts.append((ps, v))
    return pts


# ---------------------------------------------------------------- the frozen contract
def contract():
    """every (case_id, window) this round must deliver, built from the frozen task tables alone"""
    case_rows = rows_of(FROZEN_CASE_TABLE)
    gold = {}
    for r in rows_of(FROZEN_GOLDEN_TABLE):
        gold[(r['case_id'], r['window'])] = r
    out = {}
    for c in case_rows:
        cid = c['case_id']
        for window in [x.strip() for x in c['windows'].split(';') if x.strip()]:
            key = (cid, window)
            g = gold.get(key)
            parent = cid
            if g is None and c['reuse_of'] and c['reuse_of'] != 'NONE':
                g = gold.get((c['reuse_of'], window))
                parent = c['reuse_of']
            if g is None:
                if c['role'] != 'calibration':
                    raise MS.Refuse('the frozen tables carry no window %s for case %s'
                                    % (window, cid))
                g = {'mode': '', 'code': '', 'pam_request': '', 'tick_ns': '', 'window_ns': '',
                     'full_intervals': '', 'expected_intervals': '', 'expected_pulses': '',
                     'expected_accepted_ticks': ''}
            out[key] = {'case_id': cid, 'window': window, 'role': c['role'], 'mode': g['mode'],
                        'code': g['code'], 'pam_request': g['pam_request'],
                        'tick_ns': g['tick_ns'], 'window_ns': g['window_ns'],
                        'full_intervals': g['full_intervals'],
                        'expected_intervals': g['expected_intervals'],
                        'expected_pulses': g['expected_pulses'],
                        'expected_accepted_ticks': g['expected_accepted_ticks'],
                        'maxstep_ns': c['maxstep_ns'], 'ramp_ns': c['ramp_ns'],
                        'vclamp_v': c['vclamp_v'], 'reuse_of': c['reuse_of'], 'parent': parent,
                        'trace_case': c['trace_case'], 'group': c['group']}
    return out


def code_in_domain(mode, code):
    """the accepted D7A code domains: pure 0..255, hybrid 0..63"""
    value = integer_value(code)
    if value is None or not mode:
        return False
    if mode.upper() == 'PURE':
        return 0 <= value <= 255
    if mode.upper() == 'HYB':
        return 0 <= value <= 63
    return False


# ---------------------------------------------------------------- delivered bytes
class Bundle(object):
    def __init__(self, ev_dir):
        self.dir = ev_dir
        self.cases = rows_of(os.path.join(ev_dir, 'cases.csv'))
        self.idx = read_rows(os.path.join(ev_dir, 'charge_index.csv'))
        self.ledger = read_rows(os.path.join(ev_dir, 'process_ledger.csv'))
        self.neg = read_rows(os.path.join(ev_dir, 'negative.csv'))
        self.conv = read_rows(os.path.join(ev_dir, 'convergence.csv'))
        self.cal = read_rows(os.path.join(ev_dir, 'calibration.csv'))
        self.contract = contract()
        self.env = self.json('environment.json')
        self.source = self.json('source_identity.json')
        self.manifest = self.json('manifest.json')
        self.account = read_rows(os.path.join(ev_dir, 'launch_account.csv'))
        self.reconcile = read_rows(os.path.join(ev_dir, 'launches_reconcile.csv'))
        self._samples = {}
        self._edges = {}
        self._pwl = {}
        self._vcd = {}

    def json(self, name):
        path = os.path.join(self.dir, name)
        if not os.path.isfile(path):
            return {}
        try:
            return json.loads(u(io.open(path, encoding='utf-8').read()))
        except ValueError as exc:
            raise MS.Refuse('%s is not readable JSON: %s' % (name, exc))

    def by_key(self):
        return dict(((r['case_id'], r['window']), r) for r in self.cases)

    def shards(self, base):
        return sorted([r for r in self.idx if r['base'] == base], key=lambda x: x['part'])

    def verify_shards(self, base):
        parts = self.shards(base)
        if not parts:
            raise MS.Refuse('no delivered shard set for %s' % base)
        seen = 0
        rows = []
        for r in parts:
            path = os.path.join(self.dir, r['part'])
            if not os.path.isfile(path):
                raise MS.Refuse('%s is listed in the index but missing' % r['part'])
            if digest(path) != r['sha256']:
                raise MS.Refuse('%s does not match its index digest' % r['part'])
            if integer_value(r['bytes']) != os.path.getsize(path):
                raise MS.Refuse('%s is %d bytes, the index says %s'
                                % (r['part'], os.path.getsize(path), r['bytes']))
            got = rows_of(path)
            if len(got) != integer_value(r['rows']):
                raise MS.Refuse('%s carries %d rows, the index says %s'
                                % (r['part'], len(got), r['rows']))
            if integer_value(r['first_row']) != seen + 1:
                raise MS.Refuse('%s starts at row %s, the previous shard ended at %d'
                                % (r['part'], r['first_row'], seen))
            if integer_value(r['last_row']) != seen + len(got):
                raise MS.Refuse('%s ends at row %s, its own rows say %d'
                                % (r['part'], r['last_row'], seen + len(got)))
            rows.extend(got)
            seen += len(got)
        if seen != integer_value(parts[0]['total_rows']):
            raise MS.Refuse('%s: the shards hold %d rows, the series says %s'
                            % (base, seen, parts[0]['total_rows']))
        return rows, parts

    def samples(self, case_id, window):
        key = (case_id, window)
        if key not in self._samples:
            rows, parts = self.verify_shards('charge_%s_%s' % key)
            series = [(float(r['t_ps']), MS.parse_value(r['iout_A'], parts[0]['part']))
                      for r in rows]
            self._samples[key] = (series, parts[0]['series_sha256'])
        return self._samples[key]

    def pwl_edges(self, case_id):
        """the binary stimulus edges of one case, in analog time, as the bundle delivered them

        This is the deck the simulator was handed, not a result it produced: the pulse a window has to
        conduct is read from here, so an edge claim is checked against the stimulus that declares it
        instead of against the row that reports it.
        """
        if case_id not in self._pwl:
            path = os.path.join(self.dir, 'pwl_edges_%s.csv' % case_id)
            rows = []
            if os.path.isfile(path):
                # a black code legitimately drives no edge at all, so a header-only file means "no
                # pulse"; a conducting window that finds nothing here is reported by the caller
                with io.open(path, encoding='utf-8', newline='') as f:
                    head = f.readline().strip().split(',')
                    for line in f:
                        if not line.strip():
                            continue
                        rows.append(dict(zip(head, line.rstrip('\r\n').split(','))))
                edges = []
                for r in rows:
                    t = num(r.get('t_analog_ns'))
                    level = integer_value(r.get('level'))
                    if t is None or level not in (0, 1):
                        raise MS.Refuse('pwl_edges_%s.csv row %r is not a binary edge at an '
                                        'integer analog time' % (case_id, r))
                    ps = int(round(t * 1000))
                    if ps != t * 1000:
                        raise MS.Refuse('pwl_edges_%s.csv places an edge at %s ns, which is not a '
                                        'whole picosecond' % (case_id, r['t_analog_ns']))
                    edges.append((ps, level))
                self._pwl[case_id] = sorted(set(edges))
                return self._pwl[case_id]
            self._pwl[case_id] = []
        return self._pwl[case_id]

    def pulse_segments(self, r, t0_ps, t1_ps):
        """the high runs of this window's own stimulus, clipped to the window"""
        edges = self.pwl_edges(r['case_id'])
        if not edges or t0_ps is None or t1_ps is None:
            return None
        return TR.segments_of(edges, t0_ps, t1_ps)

    def vcd_document(self, vcd_path, case_id, ramp_ns, shift_ns):
        """the delivered four-state bytes re-read through the frozen parser, memoised per case"""
        key = (vcd_path, case_id, ramp_ns, shift_ns)
        if key not in self._vcd:
            self._vcd[key] = TR.case_document(vcd_path, case_id, golden_table(self),
                                              shift_ns, ramp_ns)
        return self._vcd[key]

    def edges(self, case_id, window):
        key = (case_id, window)
        if key not in self._edges:
            base = 'edge_%s_%s' % key
            if not self.shards(base):
                self._edges[key] = {}
            else:
                rows, _parts = self.verify_shards(base)
                by_label = {}
                for r in rows:
                    by_label.setdefault(r['quantity'], []).append(r)
                self._edges[key] = by_label
        return self._edges[key]


def golden_table(B):
    """the frozen golden rows: the bundle's own copy when it ships one, else the repository table

    A reviewer who only has the bundle must still be able to re-derive every pulse, so the R2 export
    carries the golden table next to the rows that are checked against it; reading an older bundle
    falls back to the repository copy and the fallback is named in the check detail.
    """
    local = os.path.join(B.dir, 'golden_windows.csv')
    if os.path.isfile(local):
        want = B.env.get('golden_windows_sha256')
        if want and digest(local) != want:
            raise MS.Refuse('the bundle ships golden_windows.csv, but it does not hash to the digest '
                            'its own environment.json records')
        B.golden_src = 'the golden table delivered inside the bundle'
        return TR.load_golden(local)
    B.golden_src = 'the repository golden table (this bundle ships no copy)'
    return TR.load_golden(FROZEN_GOLDEN_TABLE)


def bundle_shift(B):
    """the deck's PWL shift, named by the bundle when it records one"""
    got = integer_value(B.env.get('shift_ns'))
    return (got or SHIFT_NS) * NS


def edge_series(rows, column):
    """(time in ps, value) for one node column of one delivered edge slice

    A slice that prints its times as four-decimal nanoseconds quantises them to 0.1 ps, which is
    coarser than the crossing it is meant to prove, so `t_ps` is used when the slice carries it and
    the quantisation is reported rather than hidden by rounding the times up to whole picoseconds.
    """
    out = []
    for r in rows:
        v, t = r.get(column), edge_time_ps(r)
        if v in (None, '') or t is None:
            continue
        out.append((t, float(v)))
    return sorted(set(out))


def edge_time_ps(r):
    """the delivered time of an edge row at the precision the slice really carries"""
    if r.get('t_ps') not in (None, ''):
        return float(r['t_ps'])
    t = num(r.get('t_ns'))
    return None if t is None else t * 1000.0


def edge_times_quantised(rows):
    """True when a slice only offers four-decimal nanosecond times"""
    return bool(rows) and rows[0].get('t_ps') in (None, '')


def window_times(r):
    t0, t1 = num(r.get('t0_ns')), num(r.get('t1_ns'))
    if t0 is None or t1 is None:
        return None, None
    return int(round(t0 * 1000)), int(round(t1 * 1000))


def calibration_value(B):
    for r in B.cal:
        if r['quantity'] == 'Ical_A':
            return num(r['value_A'])
    return None


# ---------------------------------------------------------------- checks
def check_matrix(B, C):
    keys = [(r['case_id'], r['window']) for r in B.cases]
    C.add('MATRIX_UNIQUE', len(keys) == len(set(keys)), '%d rows' % len(keys))
    want, got = set(B.contract), set(keys)
    C.add('WINDOW_SET_COMPLETE', not sorted(want - got),
          'missing %s' % (', '.join('%s/%s' % k for k in sorted(want - got)) or '-'),
          ['missing %s/%s' % k for k in sorted(want - got)])
    C.add('WINDOW_NO_EXTRAS', not sorted(got - want),
          'unexpected %s' % (', '.join('%s/%s' % k for k in sorted(got - want)) or '-'))
    bad = []
    for r in B.cases:
        c = B.contract.get((r['case_id'], r['window']))
        if not c:
            continue
        for field, col in (('role', 'role'), ('mode', 'mode'), ('code', 'code'),
                           ('tick_ns', 'tick_ns'), ('full_intervals', 'full_intervals'),
                           ('expected_intervals', 'expected_intervals'),
                           ('pam_request', 'pam_request'), ('maxstep_ns', 'maxstep_ns'),
                           ('ramp_ns', 'ramp_ns'), ('vclamp_v', 'vclamp_v')):
            want_v, got_v = c[field], r.get(col, '')
            if want_v == '':
                continue
            if got_v == '':
                bad.append('%s/%s leaves %s empty, the contract says %s'
                           % (r['case_id'], r['window'], col, want_v))
                continue
            if num(want_v) is not None and num(got_v) is not None:
                if abs(num(want_v) - num(got_v)) > 1e-12:
                    bad.append('%s/%s %s=%s but the contract says %s'
                               % (r['case_id'], r['window'], col, got_v, want_v))
            elif str(got_v) != str(want_v):
                bad.append('%s/%s %s=%s but the contract says %s'
                           % (r['case_id'], r['window'], col, got_v, want_v))
    C.add('CONTRACT_FIELDS_BOUND', not bad, '; '.join(bad[:4]) or 'every row matches the tables')


def check_discrete(B, C):
    bad = []
    for r in B.cases:
        # the calibration row has no tick, no LSB scale and no commanded intervals: its own numbers
        # are the band statistics, and those are re-derived by CALIBRATION_SAMPLES_RECOMPUTED
        numeric = ['q_win_C', 'q_expected_C', 'q_lsb_C', 'charge_error_LSB', 'q_positive_C',
                   'q_negative_C', 'q_tail_C', 'last_100ns_max_abs_A', 'window_peak_A']
        if r['role'] == 'calibration':
            numeric = ['q_win_C']
        for k in numeric:
            if r.get(k) in ('', None):
                if r['verdict'] not in NON_ELECTRICAL:
                    bad.append('%s/%s leaves %s empty on a row that is not blocked'
                               % (r['case_id'], r['window'], k))
                continue
            v = num(r[k])
            if v is None or not MS.is_finite(v):
                bad.append('%s/%s %s=%r is not a finite number'
                           % (r['case_id'], r['window'], k, r[k]))
        for k in ('tick_ns', 'full_intervals', 'code'):
            if r.get(k) not in ('', None) and integer_value(r[k]) is None:
                bad.append('%s/%s %s=%r is not a whole number'
                           % (r['case_id'], r['window'], k, r[k]))
        tick = integer_value(r.get('tick_ns'))
        full = integer_value(r.get('full_intervals'))
        wns = integer_value(r.get('window_ns'))
        if None not in (tick, full, wns) and tick * full != wns:
            bad.append('%s/%s window_ns %s is not tick %s x full %s'
                       % (r['case_id'], r['window'], wns, tick, full))
    C.add('DISCRETE_VALUES_MATHEMATICAL', not bad, '; '.join(bad[:4]), bad)
    bad = []
    for r in B.cases:
        c = B.contract.get((r['case_id'], r['window']))
        if not c or c['role'] == 'calibration' or not c['mode']:
            continue
        if not code_in_domain(c['mode'], c['code']):
            bad.append('%s/%s code %r is outside the %s domain'
                       % (r['case_id'], r['window'], r.get('code'), c['mode']))
        want, got = num(c['expected_intervals']), num(r.get('expected_intervals'))
        if want is None or got is None or abs(want - got) > 1e-12:
            bad.append('%s/%s expected_intervals %r is not the contract %r'
                       % (r['case_id'], r['window'], got, want))
    C.add('CODE_DOMAIN_LEGAL', not bad, '; '.join(bad[:4]))


def check_shards(B, C):
    bad = []
    n = 0
    for r in B.cases:
        base = 'charge_%s_%s' % (r['case_id'], r['window'])
        if not B.shards(base):
            if r['verdict'] not in NON_ELECTRICAL and r['role'] != 'calibration':
                bad.append('%s/%s is recorded as %s with no delivered samples'
                           % (r['case_id'], r['window'], r['verdict']))
            continue
        try:
            rows, _parts = B.verify_shards(base)
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        n += 1
        times = []
        for row in rows:
            # the delivered round repacked its charge shards down to two columns to fit the tracked
            # byte limit, so the per-row labels are only checked when the shard carries them; the
            # index row, the shard digest and the row counts already bind the series to this case
            for col in ('case_id', 'window'):
                if col in row and row[col] != r[col]:
                    bad.append('%s: a shard row is labelled %s/%s'
                               % (base, row.get('case_id'), row.get('window')))
                    break
            value = MS.parse_value(row['iout_A'], base)
            if not MS.is_finite(value):
                bad.append('%s: a non-finite current sample' % base)
                break
            times.append(float(row['t_ps']))
        if any(times[i + 1] <= times[i] for i in range(len(times) - 1)):
            bad.append('%s: the sample times are not strictly increasing' % base)
    # a shard file the index never names is a byte series nothing binds to a case
    listed = set(r['base'] for r in B.idx)
    on_disk = set()
    for name in bundle_files(B.dir):
        m = re.match(r'^(charge|edge)_(.+?)_([a-z0-9_]+)\.\d{4}\.csv$', os.path.basename(name))
        if m:
            on_disk.add('%s_%s_%s' % (m.group(1), m.group(2), m.group(3)))
    unindexed = sorted(on_disk - listed)
    C.add('EVERY_SHARD_IS_INDEXED', not unindexed,
          '%d unindexed shard series: %s' % (len(unindexed), ', '.join(unindexed[:4]) or '-'))
    C.add('SAMPLE_SHARDS_ORDERED', not bad and n > 0,
          '%d series verified against %d index rows; %s'
          % (n, len(B.idx), '; '.join(bad[:3]) or 'consistent'))


def series_text_digest(ev_dir, parts):
    """(rows, sha256) over the sample lines of one shard series, read straight off the files"""
    lines = []
    for name in parts:
        path = os.path.join(ev_dir, name)
        if not os.path.isfile(path):
            raise MS.Refuse('%s is named by an index but missing from %s'
                            % (name, os.path.basename(ev_dir)))
        with io.open(path, encoding='utf-8', newline='\n') as f:
            text = f.read()
        lines.extend([l for l in text.split('\n', 1)[1].split('\n') if l])
    return len(lines), hashlib.sha256(''.join(l + '\n' for l in lines).encode('utf-8')).hexdigest()


def accepted_series(base):
    """the sample lines the accepted DATA-7B bundle shipped for one series, or None"""
    if 'by_base' not in ACCEPTED_CACHE:
        by = {}
        for r in read_rows(os.path.join(ACCEPTED_BUNDLE_DIR, 'charge_index.csv')):
            by.setdefault(r['base'], []).append(r['part'])
        ACCEPTED_CACHE['by_base'] = dict((k, sorted(v)) for k, v in by.items())
        ACCEPTED_CACHE['series'] = {}
    if base not in ACCEPTED_CACHE['series']:
        parts = ACCEPTED_CACHE['by_base'].get(base)
        ACCEPTED_CACHE['series'][base] = (series_text_digest(ACCEPTED_BUNDLE_DIR, parts)
                                          if parts else None)
    return ACCEPTED_CACHE['series'][base]


def check_series_vs_accepted(B, C):
    """the samples R1 ships are the accepted run's bytes, or are named for what they add

    R1 re-emits every shard from the retained raw, so corrected numbers must never be able to mean
    re-imagined samples. Each series the accepted bundle shipped has to arrive with the same row
    count and the same digest over its sample lines; only the calibration band and the edge slices
    may be new, and anything else new has to be named rather than quietly added.
    """
    bases = {}
    for r in B.idx:
        bases.setdefault(r['base'], []).append(r['part'])
    bases = dict((k, sorted(v)) for k, v in bases.items())
    marks = {}
    for r in B.idx:
        marks.setdefault(r['base'], set()).add(r.get('series_vs_accepted_bundle'))
    if not os.path.isdir(ACCEPTED_BUNDLE_DIR):
        C.add('CHARGE_SERIES_MATCHES_ACCEPTED', False,
              'the accepted bundle %s is not on disk, so the samples cannot be compared to it'
              % ACCEPTED_BUNDLE_NAME)
        return
    here = os.path.normcase(os.path.realpath(B.dir))
    there = os.path.normcase(os.path.realpath(ACCEPTED_BUNDLE_DIR))
    if here == there:
        C.add('CHARGE_SERIES_MATCHES_ACCEPTED', True,
              '%s is the reference the re-exports are compared against; the assertion is about the '
              'copies, not about itself' % ACCEPTED_BUNDLE_NAME)
        return
    bad, identical, new, missing = [], 0, [], []
    for base in sorted(bases):
        ref = accepted_series(base)
        if ref is None:
            if not (base.startswith('charge_D7B-CAL_') or base.startswith('edge_')):
                bad.append('%s is a new series nothing in the task names' % base)
            else:
                new.append(base)
            continue
        try:
            got = series_text_digest(B.dir, bases[base])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        if got != ref:
            bad.append('%s carries %d samples / %s, the accepted run shipped %d / %s'
                       % (base, got[0], got[1][:16], ref[0], ref[1][:16]))
            continue
        if marks[base] == set([None]):
            bad.append('%s matches the accepted bytes but its index carries no statement of it'
                       % base)
            continue
        if marks[base] != set(['IDENTICAL_BYTES']):
            bad.append('%s is byte-identical to the accepted run but the index calls it %s'
                       % (base, '/'.join(sorted(str(m) for m in marks[base]))))
            continue
        identical += 1
    for base in sorted(ACCEPTED_CACHE['by_base']):
        if base not in bases:
            missing.append(base)
    reasons = bad + (['%d accepted series dropped: %s'
                      % (len(missing), ', '.join(missing[:3]))] if missing else [])
    C.add('CHARGE_SERIES_MATCHES_ACCEPTED', not reasons and identical > 0,
          '%d series byte-identical to %s, %d new (%s); %s'
          % (identical, ACCEPTED_BUNDLE_NAME, len(new), ', '.join(new[:3]) or '-',
             '; '.join(reasons[:3]) or 'consistent'))


def check_charge(B, C):
    n, bad = 0, []
    for r in B.cases:
        if r['role'] == 'calibration' or r['verdict'] in NON_ELECTRICAL:
            continue
        t0, t1 = window_times(r)
        if t0 is None:
            bad.append('%s/%s has no window times' % (r['case_id'], r['window']))
            continue
        try:
            samples, _sha = B.samples(r['case_id'], r['window'])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        n += 1
        got = MS.integrate(samples, t0, t1, '%s/%s' % (r['case_id'], r['window']))
        for label, col, value in (('net', 'q_win_C', got['q']),
                                  ('positive', 'q_positive_C', got['q_pos']),
                                  ('negative', 'q_negative_C', got['q_neg'])):
            rec = num(r.get(col))
            if rec is None or abs(rec - value) > max(1e-24, abs(value) * 1e-9):
                bad.append('%s/%s %s charge %r is not the recomputed %r'
                           % (r['case_id'], r['window'], label, rec, value))
        if abs(got['q'] - (got['q_pos'] + got['q_neg'])) > max(1e-27, abs(got['q']) * 1e-9):
            bad.append('%s/%s breaks Qwin = Qpositive + Qnegative' % (r['case_id'], r['window']))
        try:
            tail = MS.integrate(samples, t1, t1 + TAIL_NS * NS, 'tail')
        except MS.Refuse as exc:
            bad.append('%s/%s %s' % (r['case_id'], r['window'], exc))
            continue
        rec = num(r.get('q_tail_C'))
        if rec is None or abs(rec - tail['q']) > max(1e-24, abs(tail['q']) * 1e-9):
            bad.append('%s/%s tail charge %r is not the recomputed %r'
                       % (r['case_id'], r['window'], rec, tail['q']))
        err = num(r.get('charge_error_LSB'))
        ql, qe = num(r.get('q_lsb_C')), num(r.get('q_expected_C'))
        if None not in (err, ql, qe) and ql:
            want = (got['q'] - qe) / ql
            if abs(want - err) > 5e-4:
                bad.append('%s/%s charge_error_LSB %r is not (Q-Qexpected)/QLSB = %r'
                           % (r['case_id'], r['window'], err, want))
    C.add('CHARGE_RECOMPUTED', not bad and n > 0,
          '%d windows re-derived; %s' % (n, '; '.join(bad[:4]) or 'consistent'))


def check_qlsb(B, C):
    """QLSB is Ical times the tick and Qexpected is QLSB times the intervals: neither is free"""
    ical = calibration_value(B)
    if ical is None:
        C.add('QLSB_BOUND_TO_ICAL', False, 'calibration.csv carries no Ical_A row')
        return
    bad = []
    for r in B.cases:
        if r['role'] == 'calibration':
            continue
        tick, ql = integer_value(r.get('tick_ns')), num(r.get('q_lsb_C'))
        qe, n = num(r.get('q_expected_C')), num(r.get('expected_intervals'))
        if tick is None or ql is None:
            continue
        want = ical * tick * NS * 1e-12
        if abs(ql - want) > max(abs(want) * 1e-9, 1e-30):
            bad.append('%s/%s q_lsb_C %r is not Ical %r x %d ns = %r'
                       % (r['case_id'], r['window'], ql, ical, tick, want))
        if qe is not None and n is not None:
            want_e = ql * n
            if abs(qe - want_e) > max(abs(want_e) * 1e-9, 1e-30):
                bad.append('%s/%s q_expected_C %r is not q_lsb x %s intervals = %r'
                           % (r['case_id'], r['window'], qe, n, want_e))
    C.add('QLSB_BOUND_TO_ICAL', not bad, '; '.join(bad[:4]) or 'Ical=%r' % ical, bad)


def check_last100(B, C):
    n, bad, worst = 0, [], (0.0, '')
    for r in B.cases:
        if r['role'] == 'calibration' or r['verdict'] in NON_ELECTRICAL:
            continue
        t0, t1 = window_times(r)
        if t0 is None:
            continue
        try:
            samples, _s = B.samples(r['case_id'], r['window'])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        value, _at = MS.tail_segment_max_abs(samples, t1 + 100 * NS, t1 + TAIL_NS * NS)
        if value is None:
            bad.append('%s/%s delivers no sample in its last 100 ns'
                       % (r['case_id'], r['window']))
            continue
        n += 1
        rec = num(r.get('last_100ns_max_abs_A'))
        if rec is None or abs(rec - value) > max(abs(value) * 1e-9, 1e-30):
            bad.append('%s/%s last_100ns_max_abs_A %r is not the recomputed %r'
                       % (r['case_id'], r['window'], rec, value))
        if value > worst[0]:
            worst = (value, '%s/%s' % (r['case_id'], r['window']))
        if r['role'] != 'negative_wiring' and value > OFF_LIMIT:
            bad.append('%s/%s the last 100 ns carries %r A, over the 150 nA criterion'
                       % (r['case_id'], r['window'], value))
    C.add('LAST_100NS_RECOMPUTED', not bad and n > 0,
          '%d windows re-derived, worst %r A at %s; %s'
          % (n, worst[0], worst[1] or '-', '; '.join(bad[:3]) or 'consistent'), bad)


def check_peak(B, C):
    n, bad = 0, []
    for r in B.cases:
        if r['role'] == 'calibration' or r['verdict'] in NON_ELECTRICAL:
            continue
        t0, t1 = window_times(r)
        if t0 is None:
            continue
        try:
            samples, _s = B.samples(r['case_id'], r['window'])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        peak, at = MS.extreme(samples, t0, t1, True)
        rec, rect = num(r.get('window_peak_A')), num(r.get('window_peak_t_ns'))
        if peak is None or rec is None or abs(rec - peak) > max(abs(peak) * 1e-9, 1e-30):
            bad.append('%s/%s window_peak_A %r is not the recomputed %r'
                       % (r['case_id'], r['window'], rec, peak))
            continue
        # a flat top has as many maximal samples as it has points, and the shard column is printed
        # with 12 significant digits, so any earlier tie is the same peak: the claim is checked by
        # reading the delivered value at the time the row names, not by demanding one index
        if rect is not None:
            claim = rect * 1000.0
            near = [v for t, v in samples if abs(t - claim) <= 2.0]
            if not near:
                bad.append('%s/%s no delivered sample lies at its claimed peak time %s ns'
                           % (r['case_id'], r['window'], rect))
                continue
            if min(abs(v - peak) for v in near) > max(abs(peak) * 1e-9, 1e-30):
                bad.append('%s/%s the sample at the claimed peak time carries %r, not the peak %r'
                           % (r['case_id'], r['window'], max(near), peak))
                continue
        n += 1
    C.add('PEAK_AND_TIME_RECOMPUTED', not bad and n > 0,
          '%d peaks re-derived; %s' % (n, '; '.join(bad[:3]) or 'consistent'))


def check_settle(B, C):
    """sustained in-band is re-derived, with the deadline being the pulse's own declared edge"""
    ical = calibration_value(B)
    n, bad = 0, []
    for r in B.cases:
        c = B.contract.get((r['case_id'], r['window']))
        if not c or c['role'] in ('calibration', 'negative_wiring'):
            continue
        if r['verdict'] in NON_ELECTRICAL:
            continue
        intervals = num(c['expected_intervals'])
        status = r.get('settled_status', '')
        if not intervals:
            if status != 'NOT_APPLICABLE_NO_CONDUCTING_EDGE':
                bad.append('%s/%s a black window says settled_status=%s'
                           % (r['case_id'], r['window'], status))
            continue
        if status not in MS.SETTLED_STATES:
            bad.append('%s/%s settled_status %r is not a stated outcome'
                       % (r['case_id'], r['window'], status))
            continue
        if ical is None:
            bad.append('no Ical to build the band from')
            continue
        _t0, t1 = window_times(r)
        edge = num(r.get('de_rise_50_ns'))
        if edge is None:
            bad.append('%s/%s conducts but declares no rise edge' % (r['case_id'], r['window']))
            continue
        try:
            samples, _s = B.samples(r['case_id'], r['window'])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        tick = integer_value(c['tick_ns']) * NS
        pulses = integer_value(c['expected_pulses'])
        segs = B.pulse_segments(r, _t0, t1)
        if not segs:
            bad.append('%s/%s no stimulus pulse in [%s, %s] ps, so the settle deadline is unknown'
                       % (r['case_id'], r['window'], _t0, t1))
            continue
        # the deadline is the fall edge of this window's own pulse, taken from the stimulus the deck
        # was built from; the contract width is checked against it instead of being used to guess it
        anchor = int(segs[-1][1]) if pulses == 1 else t1
        if pulses == 1:
            width = int(round(float(intervals) * tick))
            if abs((int(segs[-1][1]) - int(segs[0][0])) - width) > EDGE_CLAIM_TOL_PS:
                bad.append('%s/%s the stimulus pulse is %d ps, %s interval(s) of %d ps say %d'
                           % (r['case_id'], r['window'], int(segs[-1][1]) - int(segs[0][0]),
                              c['expected_intervals'], tick, width))
                continue
            anchor = int(segs[0][0]) + width
        got = MS.sustained_in_band(samples, int(round(edge * 1000)), ical * (1 - MS.BAND_REL),
                                   ical * (1 + MS.BAND_REL), anchor)
        n += 1
        if got['status'] != status:
            bad.append('%s/%s records settled_status=%s, the delivered samples give %s (the curve '
                       'leaves the band at %s ps against a deadline of %d ps)'
                       % (r['case_id'], r['window'], status, got['status'],
                          ('%.4f' % (got['band_left_at_ps'] / 1000.0))
                          if got['band_left_at_ps'] is not None else 'never', anchor))
            continue
        settled = num(r.get('settled_ns'))
        if got['settled_ps'] is None and settled is not None:
            bad.append('%s/%s is not settled yet still reports settled_ns=%s'
                       % (r['case_id'], r['window'], r.get('settled_ns')))
        elif got['settled_ps'] is not None and settled is None:
            bad.append('%s/%s settles at %.4f ns but the row leaves settled_ns empty'
                       % (r['case_id'], r['window'], got['settled_ps'] / 1000.0))
        elif got['settled_ps'] is not None \
                and abs(settled * 1000 - got['settled_ps']) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s settled_ns=%s is not the re-derived %.4f ns'
                       % (r['case_id'], r['window'], r.get('settled_ns'), got['settled_ps'] / 1000.0))
        longest = num(r.get('longest_in_band_ns'))
        if longest is not None and abs(longest * 1000 - got['longest_in_band_ps']) > 0.05 + 1e-6:
            bad.append('%s/%s longest_in_band_ns=%s is not the sample-bounded %.4f ns'
                       % (r['case_id'], r['window'], r.get('longest_in_band_ns'),
                          got['longest_in_band_ps'] / 1000.0))
    C.add('SETTLED_RECOMPUTED', not bad and n > 0,
          '%d windows re-derived; %s' % (n, '; '.join(bad[:3]) or 'consistent'))


def check_off(B, C):
    """off_status, off_ns, the segment bound and the delay re-derived from the delivered current

    The turn-off time the task table prints is the first delivered *sample* at or below the limit, so
    it is a sample instant: the row has to name a time a sample really sits at. The continuous
    threshold crossing is a different quantity, printed beside it, and the two are never swapped.
    """
    n, bad = 0, []
    for r in B.cases:
        key = (r['case_id'], r['window'])
        c = B.contract.get(key)
        if not c or c['role'] == 'calibration':
            continue
        if r['verdict'] in NON_ELECTRICAL:
            continue
        t0, t1 = window_times(r)
        try:
            samples, _s = B.samples(*key)
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        segs = B.pulse_segments(r, t0, t1) or []
        intervals = num(c['expected_intervals'])
        fall = claim_ps(r.get('de_fall_50_ns'))
        if intervals and not segs:
            bad.append('%s/%s no stimulus pulse in [%s, %s] ps, so turn-off has no segment start'
                       % (key + (t0, t1)))
            continue
        if intervals and fall is None:
            bad.append('%s/%s conducts with no fall edge, so the off search has no start' % key)
            continue
        off_start = int(round(fall)) if intervals else t0
        want_start = r.get('off_segment_start_ns')
        if want_start not in ('', None) and abs(claim_ps(want_start) - off_start) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s off_segment_start_ns=%s is not the %s edge at %.4f ns'
                       % (key[0], key[1], want_start, 'declared fall' if intervals else
                          'window start', off_start / 1000.0))
            continue
        got = MS.turn_off(samples, float(off_start), OFF_LIMIT, t1 + TAIL_NS * NS)
        if (got.get('status') or '') != r.get('off_status', ''):
            bad.append('%s/%s records off_status=%s, the delivered current gives %s'
                       % (key[0], key[1], r.get('off_status'), got.get('status')))
            continue
        n += 1
        if r.get('off_ns') in ('', None):
            continue
        claim = claim_ps(r.get('off_ns'))
        off = got.get('off_ps')
        if off is None:
            bad.append('%s/%s off_status=%s reports no off time yet prints off_ns=%s'
                       % (key + (r.get('off_status'), r.get('off_ns'))))
            continue
        if abs(claim - off) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s off_ns=%s is not the re-derived %.4f ns'
                       % (key[0], key[1], r.get('off_ns'), off / 1000.0))
            continue
        # an off time printed as a sample instant must BE a delivered sample instant
        if not any(abs(t - claim) <= EDGE_CLAIM_TOL_PS for t, _v in samples):
            bad.append('%s/%s off_ns=%s is not one of the delivered sample times, so it cannot be a '
                       'first-sampling-point statement' % (key + (r.get('off_ns'),)))
            continue
        interp = MS.crossing(samples, OFF_LIMIT, False, off_start, t1 + TAIL_NS * NS, 'off crossing')
        printed = num(r.get('off_interp_ns'))
        if interp is not None and printed is None and 'off_interp_ns' in r:
            bad.append('%s/%s the continuous %r A crossing is %.4f ns and the row leaves it empty'
                       % (key[0], key[1], OFF_LIMIT, interp / 1000.0))
        elif printed is not None and interp is not None \
                and abs(printed * 1000 - interp) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s off_interp_ns=%s is not the adjacent-sample crossing %.4f ns'
                       % (key[0], key[1], r.get('off_interp_ns'), interp / 1000.0))
        elif printed is not None and interp is None:
            bad.append('%s/%s prints a continuous off time (%s ns) that no two delivered samples '
                       'bracket' % (key + (r.get('off_interp_ns'),)))
    C.add('OFF_TIMES_RECOMPUTED', not bad and n > 0,
          '%d turn-offs re-derived from the delivered current; %s'
          % (n, '; '.join(bad[:3]) or 'consistent'))


def claim_ps(value):
    """a printed nanosecond claim kept at the resolution the table actually prints"""
    if value in (None, '', 'NOT_FOUND', 'NOT_APPLICABLE_NO_CONDUCTING_EDGE', 'NOT_SAVED'):
        return None
    return float(value) * 1000.0


def check_edges(B, C):
    """every claimed crossing re-derived from its own samples, at the pulse the stimulus declares"""
    ical = calibration_value(B)
    n, bad = 0, []
    search = PULSE_EDGE_TOLERANCE_PS
    for r in B.cases:
        key = (r['case_id'], r['window'])
        c = B.contract.get(key)
        if not c or c['role'] == 'calibration':
            continue
        intervals = num(c['expected_intervals'])
        for col in ('de_rise_50_ns', 'de_fall_50_ns', 'current_10pct_ns', 'current_90pct_ns',
                    'de_b_fall_50_ns', 'de_b_rise_50_ns'):
            if not intervals and r.get(col, '') not in ('', 'NOT_APPLICABLE_NO_CONDUCTING_EDGE',
                                                         'NOT_SAVED'):
                bad.append('%s/%s a black window declares %s=%s' % (key[0], key[1], col, r[col]))
        if not intervals:
            continue
        if r['verdict'] in NON_ELECTRICAL:
            continue
        if ical is None:
            bad.append('no Ical to build the current thresholds from')
            continue
        t0, t1 = window_times(r)
        segs = B.pulse_segments(r, t0, t1)
        if not segs:
            bad.append('%s/%s the delivered stimulus edge list holds no pulse in [%s, %s] ps, so '
                       'none of its crossings has an anchor' % (key + (t0, t1)))
            continue
        exp_pulses = integer_value(c['expected_pulses'])
        if exp_pulses is not None and len(segs) != exp_pulses:
            bad.append('%s/%s the delivered stimulus conducts %d pulse(s) in [%d, %d) ps, the frozen '
                       'table says %d' % (key[0], key[1], len(segs), t0, t1, exp_pulses))
            continue
        if integer_value(r.get('declared_pulses')) != len(segs):
            bad.append('%s/%s records declared_pulses=%s while its own stimulus gives %d'
                       % (key[0], key[1], r.get('declared_pulses'), len(segs)))
            continue
        rise_at, fall_at = int(segs[0][0]), int(segs[-1][1])
        tick = integer_value(c['tick_ns']) * NS
        width = int(round(float(intervals) * tick))
        if exp_pulses == 1 and abs((fall_at - rise_at) - width) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s its stimulus pulse is %d ps wide while %s interval(s) of %d ps make %d'
                       % (key[0], key[1], fall_at - rise_at, c['expected_intervals'], tick, width))
            continue
        ed = B.edges(*key)
        try:
            cur, _s = B.samples(*key)
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        # (column, slice labels to try in order, node column, level, direction, lo, hi, must find,
        #  what it is). data_en_b is the inverter output, so its edge is the opposite phase: the fall
        #  of data_en is where data_en_b rises. Searching a fall there is what made a short window
        #  "find" an edge by luck while every long window reported NOT_FOUND.
        marks = (('de_rise_50_ns', ('de_rise_50',), 'data_en_V', DE_50, True, rise_at - search,
                  rise_at + search, True, 'the 50 % rise of data_en at the stimulus rise edge'),
                 ('de_fall_50_ns', ('de_fall_50',), 'data_en_V', DE_50, False, fall_at - search,
                  fall_at + search, True, 'the 50 % fall of data_en at the stimulus fall edge'),
                 ('de_b_fall_50_ns', ('de_b_fall_50', 'de_rise_50'), 'data_en_b_V', DE_50, False,
                  rise_at - search, rise_at + search, False,
                  'the 50 % fall of data_en_b where data_en rises'),
                 ('de_b_rise_50_ns', ('de_b_rise_50', 'de_fall_50'), 'data_en_b_V', DE_50, True,
                  fall_at - search, fall_at + search, False,
                  'the 50 % rise of data_en_b where data_en falls'),
                 ('current_10pct_ns', None, None, 0.1 * ical, True, rise_at - search,
                  fall_at + (TAIL_NS + search) * NS, True, 'iout rising through 10 % of Ical'),
                 ('current_90pct_ns', None, None, 0.9 * ical, True, rise_at - search,
                  fall_at + (TAIL_NS + search) * NS, True, 'iout rising through 90 % of Ical'))
        got_t = {}
        for col, labels, node, threshold, rising, lo, hi, required, what in marks:
            if col not in r:
                # the column was not part of the table this bundle was written with
                continue
            value = r[col]
            if labels is None:
                series, slice_rows = cur, []
            else:
                slice_rows = []
                for lab in labels:
                    slice_rows = ed.get(lab, [])
                    if slice_rows:
                        break
                series = edge_series(slice_rows, node)
            if value == 'NOT_SAVED':
                if series:
                    bad.append('%s/%s says %s is NOT_SAVED while the slice carries the node'
                               % (key[0], key[1], col))
                continue
            if len(series) < 2:
                if required:
                    bad.append('%s/%s %s=%r has no delivered %s samples to re-derive it from'
                               % (key[0], key[1], col, value, what))
                elif value not in ('', 'NOT_FOUND', 'NOT_APPLICABLE_NO_CONDUCTING_EDGE'):
                    bad.append('%s/%s records %s=%s although no delivered %s samples bracket it'
                               % (key[0], key[1], col, value, what))
                continue
            want = MS.crossing(series, threshold, rising, lo, hi,
                               '%s/%s %s' % (key[0], key[1], col))
            if want is None:
                if value not in ('', 'NOT_FOUND'):
                    bad.append('%s/%s records %s=%s but no two delivered samples bracket %r inside '
                               '[%d, %d] ps of the %s' % (key[0], key[1], col, value, threshold,
                                                           lo, hi, what))
                elif required:
                    bad.append('%s/%s leaves %s NOT_FOUND, yet the same %s is what the deck drives, '
                               'so the miss is evidence and not a blank' % (key + (col, what)))
                continue
            if value in ('', 'NOT_FOUND'):
                bad.append('%s/%s %s is %r while the delivered samples cross %r at %.4f ns of the %s'
                           % (key[0], key[1], col, value, threshold, want / 1000.0, what))
                continue
            got_t[col] = want
            if abs(claim_ps(value) - want) > EDGE_CLAIM_TOL_PS:
                bad.append('%s/%s %s=%s ns is not the crossing of the delivered samples (%.4f ns), '
                           'a difference of %.4f ps beyond the 0.05 ps the column can print%s'
                           % (key[0], key[1], col, value, want / 1000.0, abs(claim_ps(value) - want),
                              '' if labels is None or not edge_times_quantised(slice_rows) else
                              ' (and this slice only prints its times to 0.1 ps)'))
                continue
            n += 1
        i10, i90 = got_t.get('current_10pct_ns'), got_t.get('current_90pct_ns')
        if i10 is not None and i90 is not None and i90 <= i10:
            bad.append('%s/%s the 90 %% crossing (%.4f ns) does not follow the 10 %% one (%.4f ns)'
                       % (key + (i90 / 1000.0, i10 / 1000.0)))
        span = r.get('current_rise_10_90_ns')
        if span not in ('', None) and i10 is not None and i90 is not None \
                and abs(claim_ps(span) - (i90 - i10)) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s current_rise_10_90_ns=%s is not i90 - i10 = %.4f ns'
                       % (key + (span, (i90 - i10) / 1000.0)))
        b_fall, b_rise = got_t.get('de_b_fall_50_ns'), got_t.get('de_b_rise_50_ns')
        if b_fall is not None and got_t.get('de_rise_50_ns') is not None:
            # data_en rising is data_en_b falling: the two 50 % crossings belong to the same edge
            gap = b_fall - got_t['de_rise_50_ns']
            if abs(gap) > search:
                bad.append('%s/%s data_en_b falls %.4f ns away from the data_en rise, which is not '
                           'the complement of this edge' % (key[0], key[1], gap / 1000.0))
            rec = r.get('de_and_de_b_edge_gap_ns')
            if rec not in ('', None) and abs(claim_ps(rec) - gap) > EDGE_CLAIM_TOL_PS:
                bad.append('%s/%s the recorded data_en/data_en_b gap is %s, the samples give %.4f ns'
                           % (key + (rec, gap / 1000.0)))
        if b_rise is not None and got_t.get('de_fall_50_ns') is not None:
            gap = b_rise - got_t['de_fall_50_ns']
            if abs(gap) > search:
                bad.append('%s/%s data_en_b rises %.4f ns away from the data_en fall, which is not '
                           'the complement of this edge' % (key[0], key[1], gap / 1000.0))
            rec = r.get('de_b_rise_gap_ns')
            if rec not in ('', None) and abs(claim_ps(rec) - gap) > EDGE_CLAIM_TOL_PS:
                bad.append('%s/%s the recorded data_en_b rise gap is %s, the samples give %.4f ns'
                           % (key + (rec, gap / 1000.0)))
        fall = claim_ps(r.get('de_fall_50_ns'))
        if fall is not None and not (t0 - search <= fall <= t1 + TAIL_NS * NS + search):
            bad.append('%s/%s the fall edge %s ns is outside the window and its tail'
                       % (key[0], key[1], r.get('de_fall_50_ns')))
        if r.get('off_status') and r['off_status'] not in MS.TURN_OFF_STATES:
            bad.append('%s/%s off_status %r is not a stated outcome'
                       % (key[0], key[1], r['off_status']))
        off_start = claim_ps(r.get('off_segment_start_ns'))
        off = claim_ps(r.get('off_ns'))
        delay = claim_ps(r.get('turn_off_delay_ns'))
        if r.get('turn_off_delay_ns') not in ('', None):
            if off is None or off_start is None:
                bad.append('%s/%s reports a turn-off delay of %s ns with no off time or segment start'
                           % (key + (r['turn_off_delay_ns'],)))
            elif abs(delay - (off - off_start)) > EDGE_CLAIM_TOL_PS:
                bad.append('%s/%s turn_off_delay_ns=%s is not off_ns - off_segment_start_ns = %.4f ns'
                           % (key[0], key[1], r['turn_off_delay_ns'], (off - off_start) / 1000.0))
    C.add('EDGES_BRACKETED_BY_SAMPLES', not bad and n > 0,
          '%d crossings re-derived from their own samples at the stimulus pulse; %s'
          % (n, '; '.join(bad[:4]) or 'consistent'))


def check_electrical_verdict(B, C):
    """the frozen criteria are applied to the recomputed numbers, not to the recorded verdict"""
    n, bad = 0, []
    for r in B.cases:
        if r['role'] in ('calibration', 'negative_wiring') or r['verdict'] in NON_ELECTRICAL:
            continue
        err, last = num(r.get('charge_error_LSB')), num(r.get('last_100ns_max_abs_A'))
        if err is None or last is None:
            bad.append('%s/%s cannot be judged (charge_error=%r last100=%r)'
                       % (r['case_id'], r['window'], r.get('charge_error_LSB'),
                          r.get('last_100ns_max_abs_A')))
            continue
        n += 1
        want = 'PASS' if (abs(err) <= TOL_LSB and last <= OFF_LIMIT
                          and r.get('probe_direction_suspect') != 'True') else 'FAIL'
        if r['verdict'] != want:
            bad.append('%s/%s records %s but the criteria give %s (err=%+.4f LSB, last100=%.6g A)'
                       % (r['case_id'], r['window'], r['verdict'], want, err, last))
    C.add('ELECTRICAL_VERDICT_CONSISTENT', not bad and n > 0,
          '%d verdicts re-derived; %s' % (n, '; '.join(bad[:3]) or 'consistent'), bad)


def slice_recheck(B, window, bounds, recorded, label, row=None):
    """one calibration window re-read from the slice that is supposed to prove it

    A missing slice is reported as its own blocked state instead of being skipped: `if off:` used to
    drop the empty set and still print that everything had been re-derived.
    """
    tag = window.split('_', 1)[1].upper()
    span = '%.1f..%.1f ns' % (bounds[0] / 1000.0, bounds[1] / 1000.0)
    try:
        samples, _s = B.samples('D7B-CAL', window)
    except MS.Refuse:
        return (['BLOCKED_MISSING_CAL_%s: the bundle carries no %s slice for %s'
                 % (tag, label, span)]), '%s: no delivered bytes' % label
    inside = [p for p in samples if bounds[0] < p[0] < bounds[1]]
    if len(inside) < 1:
        return (['BLOCKED_MISSING_CAL_%s: the delivered %s slice holds %d sample(s) inside %s'
                 % (tag, label, len(inside), span)]), '%s: %d samples' % (label, len(inside))
    # the same reconstruction the builder used: the straight line through the delivered samples,
    # clipped to the window, so its two interpolated end points count as part of the window
    clipped = MS.window_curve(samples, bounds[0], bounds[1], '%s slice' % label)
    got = max(abs(v) for _t, v in clipped)
    a, b = MS.window_bounds(samples, bounds[0], bounds[1])
    integrated_s = (b - a) * MS.S_PER_PS if a is not None else None
    cover_s = ((inside[-1][0] - inside[0][0]) * MS.S_PER_PS) if inside else None
    note = '%s: %d samples inside %s, max |I| %.12g A over the %d clipped points' % (
        label, len(inside), span, got, len(clipped))
    if recorded is None:
        return (['the %s slice carries %d samples but calibration.csv asserts no value for it'
                 % (label, len(inside))]), note
    if abs(got - recorded) > max(abs(recorded) * 1e-9, 1e-30):
        return (['the %s max |I| %r is not the delivered samples\' %r (%d samples in %s)'
                 % (label, recorded, got, len(inside), span)]), note
    stated = integer_value((row or {}).get('band_samples'))
    if stated is not None and stated != len(inside):
        return (['calibration.csv says %d samples for the %s window, its delivered slice holds %d'
                 % (stated, label, len(inside))]), note
    for col, want, what in (('band_integration_s', integrated_s, 'integrated'),
                            ('integration_s', cover_s, 'covered by its own samples')):
        got_s = num((row or {}).get(col))
        if got_s is not None and want is not None and abs(got_s - want) > max(want * 1e-9, 1e-18):
            return (['the %s window says it was %s over %r s, the delivered slice is %r s'
                     % (label, what, got_s, want)]), note
    return [], note


def check_calibration(B, C):
    ical = calibration_value(B)
    rows = B.cal
    n_cal = len([r for r in B.cases if r['role'] == 'calibration'])
    C.add('CALIBRATION_PRESENT', n_cal == 1, '%d calibration row(s)' % n_cal)
    band_min = band_max = off_max = tail_max = None
    off_row = tail_row = None
    for r in rows:
        if r['quantity'] == 'Ical_A':
            band_min, band_max = num(r.get('band_min_A')), num(r.get('band_max_A'))
        elif r['quantity'] == 'OFF_baseline_max_abs_A':
            off_max = num(r['value_A'])
            off_row = r
        elif r['quantity'] == 'CAL_tail_max_abs_A':
            tail_max = num(r['value_A'])
            tail_row = r
    in_band = (ical is not None and abs(ical - ICAL_TARGET) <= ICAL_BAND_REL * ICAL_TARGET
               and off_max is not None and off_max <= OFF_LIMIT
               and tail_max is not None and tail_max <= OFF_LIMIT)
    C.add('CALIBRATION_NUMBERS_IN_BAND', in_band, 'Ical=%r off=%r tail=%r'
          % (ical, off_max, tail_max))
    bad = []
    band_bad = []
    cal_row = [r for r in B.cases if r['role'] == 'calibration']
    if cal_row:
        r = cal_row[0]
        if not r.get('section_read'):
            bad.append('the calibration row names no section')
        if not r.get('temp_read'):
            bad.append('the calibration row names no temperature')
        if r.get('temp_read') and abs(float(r['temp_read']) - 27.0) > 1e-6:
            bad.append('the calibration ran at %s C, not the 27 C the round is defined at'
                       % r['temp_read'])
        if not r.get('raw_sha256') or not r.get('deck_sha256'):
            bad.append('the calibration row carries no raw or deck digest')
    samples = None
    try:
        samples, _s = B.samples('D7B-CAL', 'cal')
    except MS.Refuse as exc:
        band_bad.append('BLOCKED_MISSING_CAL_BAND: %s' % exc)
    band_mean = None
    band_internal = 0
    if samples is not None:
        # the mean is taken over the 500 ns the window declares, with the two boundary values
        # interpolated between the samples that straddle them; the samples themselves only cover
        # 499.5 ns, and that difference is reported instead of being smoothed over
        clipped = MS.window_curve(samples, CAL_BAND[0], CAL_BAND[1], 'calibration band')
        lo_hi = MS.window_bounds(samples, CAL_BAND[0], CAL_BAND[1])
        integrated_s = (lo_hi[1] - lo_hi[0]) * MS.S_PER_PS if lo_hi[0] is not None else None
        band_internal = len([p for p in clipped if CAL_BAND[0] < p[0] < CAL_BAND[1]])
        band_mean = (MS.trapezoid(clipped) / integrated_s) if integrated_s else None
        inside = [(t, v) for t, v in clipped if CAL_BAND[0] <= t <= CAL_BAND[1]]
        if len(inside) < 2:
            band_bad.append('the delivered CAL band holds %d samples' % len(inside))
        else:
            stated_span = num((cal_row[0] if cal_row else {}).get('band_integration_s'))
            if stated_span is not None and integrated_s is not None \
                    and abs(stated_span - integrated_s) > max(integrated_s * 1e-9, 1e-18):
                band_bad.append('calibration.csv says the band was integrated over %r s, the '
                                'delivered samples cover %r s' % (stated_span, integrated_s))
            stated_cover = num((cal_row[0] if cal_row else {}).get('integration_s'))
            cover = ((inside[-1][0] - inside[0][0]) * MS.S_PER_PS)
            if stated_cover is not None and abs(stated_cover - cover) > max(cover * 1e-9, 1e-18):
                band_bad.append('calibration.csv says its own samples span %r s, they span %r s'
                                % (stated_cover, cover))
            if ical is None or band_mean is None or abs(band_mean - ical) > max(
                    abs(ical) * 1e-9, 1e-24):
                band_bad.append('Ical %r is not the mean of its own band over the declared %d ns '
                                '(%.12g)' % (ical, (CAL_BAND[1] - CAL_BAND[0]) // NS, band_mean))
            if band_min is not None and abs(min(v for _t, v in inside) - band_min) > abs(
                    band_min) * 1e-9:
                band_bad.append('the band minimum %r is not the delivered samples\' %r'
                                % (band_min, min(v for _t, v in inside)))
            if band_max is not None and abs(max(v for _t, v in inside) - band_max) > abs(
                    band_max) * 1e-9:
                band_bad.append('the band maximum %r is not the delivered samples\' %r'
                                % (band_max, max(v for _t, v in inside)))
            stated = integer_value(cal_row[0].get('band_samples')) if cal_row else None
            if stated is not None and 'band_samples' in cal_row[0] and stated != band_internal:
                band_bad.append('calibration.csv says %d band samples, the delivered shard holds %d'
                                % (stated, band_internal))
    C.add('CALIBRATION_BANDS_FROM_SAMPLES', not band_bad and samples is not None,
          '; '.join(band_bad[:3]) or 'Ical re-read as the mean of %d internal samples over the '
                                     'declared 500 ns with both bounds interpolated' % band_internal)
    # the two windows outside the band: each one is only a fact once its own bytes are in the bundle
    off_bad, off_note = slice_recheck(B, 'cal_off', CAL_OFF, off_max, 'OFF baseline', off_row)
    tail_bad, tail_note = slice_recheck(B, 'cal_tail', CAL_TAIL, tail_max, 'tail', tail_row)
    bad += off_bad + tail_bad
    blocked = [x for x in off_bad + tail_bad if x.startswith('BLOCKED_')]
    C.add('CALIBRATION_OFF_BASELINE_SAMPLES', not off_bad and not tail_bad,
          '%s; %s%s' % (off_note, tail_note,
                        '' if not blocked else '; ' + '; '.join(bad[:2])))
    bad += band_bad
    if cal_row and not in_band:
        survivors = [r for r in B.cases if r['role'] not in ('calibration', 'negative_wiring')
                     and r['verdict'] not in NON_ELECTRICAL]
        C.add('CALIBRATION_BLOCKS', not survivors,
              '%d current rows survive a failed calibration' % len(survivors))
    else:
        C.add('CALIBRATION_BLOCKS', True, 'calibration passed')


def check_artifacts(B, C):
    """every case needs its deck and its PWL, named exactly, bound to the row and to each other"""
    bad = []
    for r in B.cases:
        cid = r['case_id']
        deck = os.path.join(B.dir, 'decks', '%s.scs' % cid)
        pwl = os.path.join(B.dir, 'pwl', '%s_pwl.txt' % cid)
        if not os.path.isfile(deck):
            bad.append('%s: decks/%s.scs is missing' % (cid, cid))
            continue
        if not os.path.isfile(pwl):
            bad.append('%s: pwl/%s_pwl.txt is missing (the file is not named <case>.txt)'
                       % (cid, cid))
            continue
        if digest(deck) != r.get('deck_sha256'):
            bad.append('%s: deck digest %s, the row says %s'
                       % (cid, digest(deck)[:12], (r.get('deck_sha256') or '')[:12]))
        if digest(pwl) != r.get('pwl_sha256'):
            bad.append('%s: the PWL file hashes to %s, the row says %s'
                       % (cid, digest(pwl)[:12], (r.get('pwl_sha256') or '')[:12]))
        deck_text = u(io.open(deck, encoding='utf-8', newline='\n').read())
        pts = pwl_points_of(u(io.open(pwl, encoding='utf-8', newline='\n').read()))
        wave = deck_wave_points(deck_text)
        stop_ps = None
        stop = deck_field(deck_text, r'tran\s+(?:\w+\s+)?stop=(\S+)')
        if stop and sci(stop) is not None:
            stop_ps = sci(stop) * 1e12
        if pts is None:
            bad.append('%s: the delivered PWL file is not parsable pairs of ps and volts' % cid)
        elif wave is None:
            bad.append('%s: the deck carries no parsable PWL wave' % cid)
        elif r['role'] == 'negative_wiring':
            if wave:
                bad.append('%s: the wiring negative still drives data_en from a PWL bench node'
                           % cid)
        elif wave != pts:
            # a retained deck can predate the hold point the builder later appended: every extra
            # file point must then sit past that deck's own stop and merely repeat its last level,
            # so the stimulus the simulator actually saw is still the delivered PWL
            hold = (stop_ps is not None and len(pts) > len(wave) and pts[:len(wave)] == wave
                    and all(p[0] > stop_ps and p[1] == wave[-1][1] for p in pts[len(wave):]))
            if not hold:
                bad.append('%s: the deck wave clause (%d points, first %r) is not the delivered PWL '
                           'file (%d points, first %r)'
                           % (cid, len(wave), wave[:1], len(pts or []), (pts or [])[:1]))
        if not stop:
            bad.append('%s: the deck names no analysis stop' % cid)
        maxstep = deck_field(deck_text, r'maxstep=(\S+)')
        if not maxstep or not r.get('maxstep_ns'):
            bad.append('%s: the deck or the row names no maxstep' % cid)
        else:
            want, got = sci(maxstep), num(r['maxstep_ns'])
            if want is None or got is None or abs(want - got * 1e-9) > abs(want) * 1e-9:
                bad.append('%s: deck maxstep %s is not the row\'s %s ns'
                           % (cid, maxstep, r['maxstep_ns']))
        section = deck_field(deck_text, r'section=(\w+)')
        if not section:
            bad.append('%s: the deck names no section' % cid)
        elif not r.get('section_read'):
            bad.append('%s: the deck says section=%s but the row leaves section_read empty'
                       % (cid, section))
        elif section != r['section_read']:
            bad.append('%s: deck section %s, row %s' % (cid, section, r['section_read']))
        temp = deck_field(deck_text, r'options\s+temp=(\S+)')
        if not temp:
            bad.append('%s: the deck names no temperature' % cid)
        elif not r.get('temp_read'):
            bad.append('%s: the deck asks temp=%s but the row leaves temp_read empty'
                       % (cid, temp))
        elif num(temp) is None or abs(num(temp) - float(r['temp_read'])) > 1e-6:
            bad.append('%s: deck temp %s, read back %s' % (cid, temp, r['temp_read']))
        if 'Ip_out (clamp data_out) iprobe' not in deck_text:
            bad.append('%s: the deck lost the zero-burden ammeter' % cid)
        if r.get('vclamp_v') and ('Vclamp (clamp 0) vsource dc=%s'
                                  % r['vclamp_v']) not in deck_text:
            bad.append('%s: the clamp is not the row\'s %s V' % (cid, r['vclamp_v']))
    C.add('DECK_AND_PWL_BOUND', not bad, '; '.join(bad[:5]), bad)
    bad = []
    for r in B.cases:
        if r['role'] != 'negative_wiring':
            continue
        parent = (B.contract.get((r['case_id'], r['window'])) or {}).get('reuse_of')
        if not parent or parent == 'NONE':
            continue
        pdeck = os.path.join(B.dir, 'decks', '%s.scs' % parent)
        cdeck = os.path.join(B.dir, 'decks', '%s.scs' % r['case_id'])
        if not (os.path.isfile(pdeck) and os.path.isfile(cdeck)):
            bad.append('%s: the parent or own deck is missing, so the wiring diff cannot be read'
                       % r['case_id'])
            continue
        a = [l for l in u(io.open(pdeck, encoding='utf-8').read()).split('\n')
             if l.startswith('Xstage')]
        b = [l for l in u(io.open(cdeck, encoding='utf-8').read()).split('\n')
             if l.startswith('Xstage')]
        if len(a) != 1 or len(b) != 1:
            bad.append('%s: the stage instance line is not unique in one of the decks'
                       % r['case_id'])
        elif a == b:
            bad.append('%s: the wiring negative is identical to its parent %s'
                       % (r['case_id'], parent))
    C.add('NEGATIVE_WIRING_DIFFERS', not bad, '; '.join(bad[:3]) or 'the enable net is the diff')


def digest_of_any(B, want):
    for root, _dirs, files in os.walk(B.dir):
        for name in files:
            if name.endswith('.scs') and digest(os.path.join(root, name)) == want:
                return os.path.join(root, name)
    return None


def check_negatives(B, C):
    """N1 must be re-derived from its own samples, N2 from its own rc, stage and zero launches"""
    bad = []
    n1 = [r for r in B.neg if r['case_id'] == 'D7B-N1']
    n2 = [r for r in B.neg if r['case_id'] == 'D7B-N2']
    if len(n1) != 1:
        bad.append('negative.csv carries %d N1 rows' % len(n1))
    else:
        r = n1[0]
        row = B.by_key().get(('D7B-N1', r.get('window') or 'normal'))
        if not r.get('run_id') or not r.get('launch_id'):
            bad.append('the N1 row names no run or launch, so it cannot be bound to a native run')
        if row is None:
            bad.append('N1 has no case row to bind to')
        else:
            nid = r.get('case_id', 'D7B-N1')
            peak_row = num(row.get('window_peak_A'))
            peak_neg = num(r.get('window_peak_uA'))
            if peak_row is None or peak_neg is None:
                bad.append('%s: the peak current is missing, so the two tables cannot be compared' % nid)
            elif abs(peak_row * 1e6 - peak_neg) > max(abs(peak_neg) * 1e-6, 1e-9):
                bad.append('%s: the negative table says %s uA while its case row says %r A, so the '
                           'column that carries microampere must say so' % (nid, peak_neg, peak_row))
            q_neg, q_row = num(r.get('q_win_C')), num(row.get('q_win_C'))
            if q_neg is None or q_row is None:
                bad.append('%s: the charge is missing' % nid)
            elif abs(q_neg - q_row) > max(abs(q_row) * 1e-9, 1e-30):
                bad.append('%s: charge %r disagrees with its case row %r' % (nid, q_neg, q_row))
            try:
                samples, _s = B.samples('D7B-N1', row['window'])
                t0, t1 = window_times(row)
                got = MS.integrate(samples, t0, t1, 'N1')
                if q_row is None or abs(got['q'] - q_row) > max(abs(got['q']) * 1e-9, 1e-24):
                    bad.append('%s: the charge is not what its own delivered samples give' % nid)
                peak, _at = MS.extreme(samples, t0, t1, True)
                if peak_row is None or abs(peak - peak_row) > max(abs(peak) * 1e-9, 1e-30):
                    bad.append('%s: the peak is not what its own delivered samples give' % nid)
            except MS.Refuse as exc:
                bad.append(str(exc))
            detected = bool(peak_row and peak_row > MS.OFF_ABS and q_row and q_row > 0.0)
            if r.get('detected') != ('YES' if detected else 'NO'):
                bad.append('N1 detected=%r while its samples %s a fault'
                           % (r.get('detected'), 'show' if detected else 'do not show'))
            if r.get('verdict', '').startswith('EXPECTED_REFUSAL') != detected:
                bad.append('the N1 verdict %r does not follow from its own observation'
                           % r.get('verdict'))
            if row.get('verdict', '') == 'PASS':
                bad.append('the N1 case row was counted as an electrical pass')
            if not row.get('deck_sha256') or not row.get('raw_sha256'):
                bad.append('the N1 case row carries no deck or raw digest')
    if len(n2) != 1:
        bad.append('negative.csv carries %d N2 rows' % len(n2))
    else:
        r = n2[0]
        if r.get('rc') in ('', '0'):
            bad.append('D7B-N2: reports rc=%r, so nothing refused it' % r.get('rc'))
        if r.get('stage') != 'supply_contract':
            bad.append('D7B-N2: stopped at stage=%r' % r.get('stage'))
        if integer_value(r.get('spectre_launches')) != 0:
            bad.append('D7B-N2: started %s processes' % r.get('spectre_launches'))
        if not r.get('deck_sha256'):
            bad.append('D7B-N2: names no deck digest')
        elif not os.path.isfile(os.path.join(B.dir, 'decks', 'D7B-N2.scs')) \
                and digest_of_any(B, r['deck_sha256']) is None:
            bad.append('D7B-N2: the bytes behind its deck digest are not in the bundle')
        if not r.get('src_native_run'):
            bad.append('D7B-N2: names no native run for its refusal')
        if 'EXPECTED_REFUSAL' not in r.get('verdict', '') or r.get('detected') != 'YES':
            bad.append('D7B-N2: verdict is %r / detected=%r'
                       % (r.get('verdict'), r.get('detected')))
    C.add('NEGATIVES_BOUND_TO_BYTES', not bad, '; '.join(bad[:4]), bad)


def check_convergence(B, C):
    want = set(k for k, c in B.contract.items() if c['role'] == 'convergence')
    got = set((r['case_id'], r['window']) for r in B.conv)
    bad = ['%s/%s has no convergence row' % k for k in sorted(want - got)]
    bad += ['%s/%s is not a convergence pair' % k for k in sorted(got - want)]
    C.add('CONVERGENCE_SET_COMPLETE', bool(want) and not bad,
          '%d pairs expected; %s' % (len(want), '; '.join(bad[:3]) or 'complete'), bad)
    by = B.by_key()
    n, bad = 0, []
    for r in B.conv:
        key = (r['case_id'], r['window'])
        c = B.contract.get(key) or {}
        parent = c.get('reuse_of') or r.get('parent_case')
        a, b = by.get((parent, key[1])), by.get(key)
        if not a or not b:
            bad.append('%s/%s has no delivered parent pair' % key)
            continue
        if r.get('parent_case') != parent:
            bad.append('%s/%s names parent %s, the contract says %s'
                       % (key[0], key[1], r.get('parent_case'), parent))
            continue
        t0, t1 = window_times(b)
        try:
            sa, _x = B.samples(parent, key[1])
            sb, _y = B.samples(key[0], key[1])
        except MS.Refuse as exc:
            bad.append(str(exc))
            continue
        if t0 is None:
            bad.append('%s/%s has no window times' % key)
            continue
        qa = MS.integrate(sa, t0, t1, 'parent')['q']
        qb = MS.integrate(sb, t0, t1, 'case')['q']
        dq = abs(qb - qa)
        rec = num(r.get('delta_q_pC'))
        if rec is None or abs(dq * 1e12 - rec) > 1e-6:
            bad.append('%s/%s delta_q %r is not the recomputed %r' % (key[0], key[1], rec,
                                                                      dq * 1e12))
            continue
        qlsb = num(b.get('q_lsb_C'))
        lim = CONV_Q_LSB_REL * qlsb if qlsb else None
        # the limit column is printed with six decimals of picocoulomb, so it is compared at that
        # resolution rather than to an exact float
        if lim is None or abs(lim * 1e12 - num(r.get('limit_q_pC'))) > max(
                5e-7, abs(lim * 1e12) * 1e-6):
            bad.append('%s/%s the dQ limit is not 1 %% of one LSB (%r)' % (key[0], key[1], lim))
            continue
        pa, pb = num(a.get('window_peak_A')), num(b.get('window_peak_A'))
        dp = abs((pb or 0.0) - (pa or 0.0))
        lim_p = max(0.05 * abs(pb or 0.0), OFF_LIMIT)
        if abs(dp * 1e6 - num(r.get('delta_peak_uA'))) > 1e-6:
            bad.append('%s/%s delta_peak %r is not the recomputed %r'
                       % (key[0], key[1], r.get('delta_peak_uA'), dp * 1e6))
            continue
        if abs(lim_p * 1e6 - num(r.get('limit_peak_uA'))) > 1e-6:
            bad.append('%s/%s the peak limit is not max(5 %% of peak, 150 nA)' % key)
            continue
        ok = dq <= lim and dp <= lim_p
        ea, eb = num(a.get('de_fall_50_ns')), num(b.get('de_fall_50_ns'))
        if ea is None or eb is None:
            bad.append('%s/%s has no fall edge on both sides of the pair, so its edge delta cannot '
                       'be re-derived (a=%r b=%r)' % (key[0], key[1], a.get('de_fall_50_ns'),
                                                      b.get('de_fall_50_ns')))
            continue
        edge_ps = abs((eb - ea) * 1000)
        rec_edge = num(r.get('delta_edge_ns'))
        if rec_edge is not None and abs(edge_ps - rec_edge * 1000) > EDGE_CLAIM_TOL_PS:
            bad.append('%s/%s delta_edge_ns=%s is not the recomputed %.4f ns'
                       % (key[0], key[1], r.get('delta_edge_ns'), edge_ps / 1000.0))
            continue
        if 'limit_edge_ns' in r:
            if num(r.get('limit_edge_ns')) is None \
                    or abs(num(r['limit_edge_ns']) * 1000 - CONV_EDGE_PS) > 1e-9:
                bad.append('%s/%s the edge limit column is %r, not the frozen %d ps'
                           % (key[0], key[1], r.get('limit_edge_ns'), CONV_EDGE_PS))
                continue
        # what is compared is one physical quantity on one node: the 50 % fall of data_en, taken from
        # the delivered samples of each member of the pair. Agreement of the ideal input edges does not
        # make the analogue convergence any wider than this number says.
        if edge_ps > CONV_EDGE_PS:
            ok = False
        want_v = 'CONVERGED' if ok else 'NUMERICAL_NOT_CONVERGED'
        if r.get('verdict') != want_v:
            bad.append('%s/%s records %s while its own numbers give %s (dQ %r vs %r, dPeak %r vs %r,'
                       ' dEdge %.4f ns vs %.4f ns)'
                       % (key[0], key[1], r.get('verdict'), want_v, dq * 1e12, lim * 1e12,
                          dp * 1e6, lim_p * 1e6, edge_ps / 1000.0, CONV_EDGE_PS / 1000.0))
        n += 1
    C.add('CONVERGENCE_RECOMPUTED', not bad and n > 0,
          '%d pairs re-derived; %s' % (n, '; '.join(bad[:4]) or 'consistent'), bad)


def illegal_account_states(rows):
    """every account row must carry one of the five protocol states, spelled exactly

    A state nothing recognises is not free: the DATA-7B-R2 defect was that an unknown or empty cell
    simply fell out of every billing branch, so a reserved launch stopped costing the ceiling while the
    account still opened. This is checked over all rows, not only the seeded ones, and it is its own
    named failure so it cannot be hidden behind a roll-up mismatch or the historical budget finding.
    """
    bad = []
    for r in rows:
        cell = r.get('state')
        shown = '(missing)' if cell is None else ('(empty)' if cell == '' else cell)
        if shown not in ACCOUNT_STATES:
            bad.append('%s=%s' % (r.get('launch_id', '(no id)'), shown))
    return bad


def check_launches(B, C):
    bad = []
    per_dir = [r for r in B.reconcile if r['task_root_dir'] != 'TOTAL']
    totals = [r for r in B.reconcile if r['task_root_dir'] == 'TOTAL']
    counted = 0
    for r in per_dir:
        n = integer_value(r.get('processes_counted_against_ceiling'))
        pre = integer_value(r.get('preflight_logs'))
        dut = integer_value(r.get('dut_logs'))
        if None in (n, pre, dut):
            bad.append('%s: the counts are not whole numbers' % r['task_root_dir'])
            continue
        if pre + dut != n:
            bad.append('%s: %d preflight + %d dut logs do not sum to %d counted'
                       % (r['task_root_dir'], pre, dut, n))
        counted += n
    if len(totals) != 1:
        bad.append('launches_reconcile.csv carries %d TOTAL rows' % len(totals))
    elif not bad:
        declared = integer_value(totals[0].get('processes_counted_against_ceiling'))
        if declared != counted:
            bad.append('the directory rows sum to %d but TOTAL declares %d' % (counted, declared))
    C.add('RECONCILE_SUMS_TO_TOTAL', not bad and bool(per_dir),
          '; '.join(bad[:3]) or '%d rows sum to %d, TOTAL agrees' % (len(per_dir), counted), bad)

    launched = [r for r in B.ledger
                if r.get('spectre_line', '').startswith('SPECTRE')
                or r.get('spectre_line', '').startswith('PREFLIGHT_INNER')]
    started = counted if (totals and not bad) else None
    # a re-measurement ships a header-only ledger: that is the statement "this pass launched
    # nothing", and it has to be corroborated by the environment rather than accepted on its own
    zero_pass = (B.env.get('new_spectre_launches_this_pass') == 0
                 and B.env.get('mode') in ('remeasure', None))
    roles = {}
    for r in B.ledger:
        roles[r.get('role', '')] = roles.get(r.get('role', ''), 0) + 1
    C.add('LEDGER_ROLE_COMPOSITION', bool(roles) or zero_pass,
          'ledger rows by role: %s; %d of them show a started process%s'
          % (' '.join('%s=%d' % kv for kv in sorted(roles.items())) or 'none', len(launched),
             '' if started is None else ', %d started per the reconcile table' % started))
    if B.account:
        bad_states = illegal_account_states(B.account)
        C.add('ACCOUNT_STATES_VALID', not bad_states,
              '%d account rows, every one carrying one of %s%s'
              % (len(B.account), '|'.join(ACCOUNT_STATES),
                 '' if not bad_states else '; refused: ' + ', '.join(bad_states[:4])))
        conf = [r for r in B.account if r['state'] in ('CONFIRMED', 'COMPLETED')]
        unc = [r for r in B.account if r['state'] == 'UNCERTAIN']
        pend = [r for r in B.account if r['state'] == 'REQUESTED']
        # a reservation is a launch somebody may not have seen return; recovering it changes what can
        # be proved about it, never what it cost, so REQUESTED occupies the ceiling here too
        occupied = len(conf) + len(unc) + len(pend)
        C.add('ACCOUNT_KEEPS_HISTORY', bool(conf) or bool(unc) or bool(pend),
              '%d account rows: %d confirmed, %d uncertain, %d reserved and unreturned, '
              '%d refused without launching'
              % (len(B.account), len(conf), len(unc), len(pend),
                 len([r for r in B.account if r['state'] == 'REFUSED_NO_LAUNCH'])))
        C.add('ACCOUNT_COVERS_RECONCILE', started is None or started <= occupied,
              'the account occupies %d, the reconcile table names %s' % (occupied, started))
        # the judgement number is the authorisation, never a column in the file being judged: reading
        # it from row one is what let a forged ceiling turn 59 of 56 into a PASS
        wrong = []
        for value in sorted(set(r.get('ceiling', '') for r in B.account)):
            if value != str(CEILING_GRANTED):
                wrong.append('%d account row(s) declare a ceiling of %s'
                             % (len([r for r in B.account if r.get('ceiling', '') == value]), value
                                or '(blank)'))
        for key in ('ceiling', 'budget'):
            if B.env.get(key) not in (None, CEILING_GRANTED):
                wrong.append('environment.json %s = %s' % (key, B.env.get(key)))
        if totals and str(CEILING_GRANTED) not in (totals[0].get('note') or ''):
            wrong.append('the reconcile TOTAL note does not name the ceiling of %d' % CEILING_GRANTED)
        acc = B.env.get('launch_account') or {}
        mismatch = []
        for key, want in (('confirmed', len(conf)), ('uncertain', len(unc)),
                          ('no_launch', len([r for r in B.account
                                             if r['state'] == 'REFUSED_NO_LAUNCH'])),
                          ('occupied', occupied)):
            got = integer_value(acc.get(key))
            if got is not None and got != want:
                mismatch.append('environment.json says %s=%d, the account rows say %d'
                                % (key, got, want))
        if mismatch:
            wrong.append('; '.join(mismatch[:3]))
        C.add('BUDGET_AUTHORITY_FIXED', not wrong,
              'the judgement ceiling is the fixed authorisation %d (task book %d plus the %d the user '
              'granted on 2026-10-21), and every declaration in the bundle says the same%s'
              % (CEILING_GRANTED, CEILING_TASKBOOK, CEILING_GRANTED - CEILING_TASKBOOK,
                 '' if not wrong else '; ' + '; '.join(wrong[:3])))
        C.add('BUDGET_RESPECTED', occupied <= CEILING_GRANTED,
              '%d launches occupied against the authorised ceiling of %d (the task book %d plus the '
              '%d the user granted later); the excess is a historical fact of the delivered round, '
              'not repaired here' % (occupied, CEILING_GRANTED, CEILING_TASKBOOK,
                                     CEILING_GRANTED - CEILING_TASKBOOK))
    else:
        C.add('ACCOUNT_STATES_VALID', False,
              'launch_account.csv is missing, so no state can be verified at all')
        C.add('ACCOUNT_KEEPS_HISTORY', False,
              'launch_account.csv is missing, so the cumulative ceiling cannot be re-derived')
        C.add('ACCOUNT_COVERS_RECONCILE', False, 'no account file to compare with')
        C.add('BUDGET_AUTHORITY_FIXED', False, 'no account file, so no declaration can be verified')
        C.add('BUDGET_RESPECTED', started is not None and started <= CEILING_GRANTED,
              '%s processes started in total against a ceiling of %d'
              % ('-' if started is None else started, CEILING_GRANTED))
    bad = []
    for r in B.ledger:
        if r.get('state') in ('REQUESTED', ''):
            bad.append('%s is still %s' % (r.get('launch_id'), r.get('state') or 'blank'))
        if r.get('role') == 'dut' and r.get('state') in ('DONE', 'COMPLETED') \
                and not r.get('raw_sha256'):
            bad.append('%s completed with no raw digest' % r.get('launch_id'))
    C.add('LEDGER_ROWS_SETTLED', not bad and (bool(B.ledger) or zero_pass),
          '; '.join(bad[:4]) or ('empty per-pass ledger, corroborated by %r launches this pass'
                                 % B.env.get('new_spectre_launches_this_pass')))


def check_identity(B, C):
    bad = []
    runs = B.source.get('native_runs', {})
    traces = B.source.get('traces', {})
    if not B.env.get('run_id'):
        bad.append('environment.json names no run_id')
    if B.env.get('run_id') != B.source.get('run_id'):
        bad.append('environment.json and source_identity.json name different runs')
    if not B.env.get('measurement_source_sha256'):
        bad.append('environment.json does not record which measurement code produced the numbers')
    else:
        path = os.path.join(HERE, 'dd1_d7b_measure.py')
        if os.path.isfile(path) and digest(path) != B.env['measurement_source_sha256']:
            bad.append('the measurement core next to this checker is %s, the bundle was written by '
                       '%s' % (digest(path)[:12], B.env['measurement_source_sha256'][:12]))
    for r in B.cases:
        if not r.get('run_id'):
            bad.append('%s/%s names no run' % (r['case_id'], r['window']))
        key = (r['case_id'], r['window'])
        if key not in B.contract:
            continue
        native = B.contract[key]['trace_case']
        reused = r.get('reused_from_native_run') or ''
        entry = runs.get(r['case_id'])
        if reused:
            if entry is None:
                bad.append('%s says it came from native run %s, but source_identity lists no native '
                           'run for it' % (r['case_id'], reused))
            elif entry.get('native_run_id') != reused:
                bad.append('%s names native run %s while source_identity records %s'
                           % (r['case_id'], reused, entry.get('native_run_id')))
            elif entry.get('raw_sha256') != r.get('raw_sha256'):
                bad.append('%s: the raw digest of native run %s is not what its row carries'
                           % (r['case_id'], reused))
            elif entry.get('dut_launch_id') != r.get('src_launch_id'):
                bad.append('%s: the launch of native run %s is not what its row carries'
                           % (r['case_id'], reused))
        elif not reused and r['case_id'] not in runs \
                and r.get('trace_sha256') not in ('', 'bench') \
                and r['trace_sha256'] not in [t.get('vcd_sha256') for t in traces.values()]:
            bad.append('%s cites a trace digest no source in this bundle carries' % r['case_id'])
    C.add('IDENTITY_CHAIN', not bad, '; '.join(bad[:4]))


def check_bundle_shape(B, C):
    names = []
    for root, _dirs, files in os.walk(B.dir):
        for name in files:
            names.append(os.path.relpath(os.path.join(root, name), B.dir).replace(os.sep, '/'))
    bad = []
    for rel in names:
        if rel.startswith('/') or '..' in rel.split('/') or re.match(r'^[A-Za-z]:', rel):
            bad.append('%s is not a contained relative path' % rel)
        if not rel.endswith(TEXT_SUFFIXES):
            bad.append('%s is not a text artefact' % rel)
            continue
        text = u(io.open(os.path.join(B.dir, rel), encoding='utf-8', errors='replace').read())
        for pat, why in FORBIDDEN:
            if re.search(pat, text):
                bad.append('%s contains %s' % (rel, why))
    C.add('BUNDLE_CONTENT_CLEAN', not bad, '; '.join(bad[:4]))
    listed = [e['path'] for e in B.manifest.get('files', [])]
    missing = sorted(set(names) - set(listed) - {'manifest.json'})
    ghost = sorted(set(listed) - set(names))
    bad = []
    for entry in B.manifest.get('files', []):
        path = os.path.join(B.dir, entry['path'])
        if not os.path.isfile(path):
            bad.append('%s listed but missing' % entry['path'])
        elif integer_value(entry['bytes']) != os.path.getsize(path):
            bad.append('%s is %d bytes, the manifest says %s'
                       % (entry['path'], os.path.getsize(path), entry['bytes']))
        elif digest(path) != entry['sha256']:
            bad.append('%s digest mismatch' % entry['path'])
    C.add('MANIFEST_MATCHES_BYTES', bool(listed) and not bad, '; '.join(bad[:4]))
    C.add('MANIFEST_COVERS_FILE_SET', bool(listed) and not missing and not ghost,
          'unlisted %s; listed but absent %s' % (', '.join(missing[:4]) or '-',
                                                 ', '.join(ghost[:4]) or '-'))
    C.add('MANIFEST_NOT_SELF', bool(listed) and 'manifest.json' not in listed,
          '%d entries, none of them the manifest itself' % len(listed))
    total = sum(integer_value(e['bytes']) or 0 for e in B.manifest.get('files', []))
    C.add('TRACKED_BYTES_WITHIN_LIMIT', 0 < total <= 32 * 1024 * 1024,
          '%d bytes across %d entries' % (total, len(listed)))


def parse_segments(txt):
    """`[[[a;b;c]];[[d;e;f]]]` as one segment list per window, the way the table records it"""
    if not txt or str(txt).strip() in ('-', '[]'):
        return []
    try:
        got = json.loads(str(txt).replace(';', ','))
    except ValueError:
        raise MS.Refuse('the re-verification table records segments %r, which is not readable'
                        % (txt,))
    out = []
    for win in got:
        segs = []
        for seg in win:
            cells = [integer_value(x) for x in seg]
            if len(cells) != 3 or None in cells:
                raise MS.Refuse('the re-verification table records the segment %r, which is not '
                                'three whole picoseconds' % (seg,))
            segs.append(cells)
        out.append(segs)
    return out


def check_vcd_semantics(B, C):
    """the delivered four-state bytes read back through the frozen parser and bound to the rows

    A digest says a file is the file; it does not say the transitions inside it still mean the pulse a
    case row reads its edges from. So the same converter that turned the RTL trace into the stimulus is
    run over the delivered bytes again, and what it finds is compared with the stimulus edge list, the
    re-verification table and every case row's own window and pulse count. A flipped transition that
    keeps every hash consistent is refused here, because the golden table no longer fits the trace.
    """
    rpath = os.path.join(B.dir, 'rtl_reverify.csv')
    dpath = os.path.join(B.dir, 'rtl_reverify_delivery.csv')
    if not (os.path.isfile(rpath) and os.path.isfile(dpath)):
        C.add('RTL_VCD_SEMANTICS_REPARSED', False,
              'the bundle ships no re-verification table and delivery index, so no delivered trace '
              'can be re-read')
        return
    table = read_rows(rpath)
    delivery = dict((r['case_id'], r) for r in read_rows(dpath))
    gold = golden_table(B)
    gold = golden_table(B)
    shift_ps = bundle_shift(B)
    by_trace = dict((c['trace_case'], c) for c in B.contract.values() if c['trace_case'])
    bad = []
    parsed = 0
    shifts = set()
    B._rtl_windows = {}
    for row in table:
        cid = row['case_id']
        d = delivery.get(cid)
        if d is None:
            bad.append('%s: the re-verification table names a trace nothing delivers' % cid)
            continue
        path = os.path.join(B.dir, d['delivered_as'])
        if not os.path.isfile(path):
            bad.append('%s: %s is not in the bundle to re-parse' % (cid, d['delivered_as']))
            continue
        cdef = by_trace.get(cid)
        ramp = integer_value((cdef or {}).get('ramp_ns')) or 2
        try:
            doc = B.vcd_document(path, cid, ramp, 0)
        except TR.Refuse as exc:
            bad.append('%s: the frozen parser refuses the delivered bytes (%s)' % (cid, exc))
            continue
        except Exception as exc:
            bad.append('%s: re-parsing raised %s instead of a refusal' % (cid, exc))
            continue
        parsed += 1
        for w in doc['windows']:
            B._rtl_windows[(cid, w['window'])] = w
        recorded = parse_segments(row.get('segments_ps', ''))
        if len(recorded) != len(doc['windows']):
            bad.append('%s: the table records %d window(s) of segments, the trace gives %d'
                       % (cid, len(recorded), len(doc['windows'])))
            continue
        for w, segs in zip(doc['windows'], recorded):
            got = [[s[0], s[1], s[2]] for s in w['segments_ps']]
            if got != segs:
                bad.append('%s/%s the table records segments %s, re-parsing the delivered bytes '
                           'gives %s' % (cid, w['window'], segs, got))
    bound = 0
    for r in B.cases:
        c = B.contract.get((r['case_id'], r['window']))
        if not c or c['role'] == 'calibration':
            continue
        tc = c['trace_case']
        if tc in ('', 'NONE'):
            continue
        key = (r['case_id'], r['window'])
        w = B._rtl_windows.get((tc, r['window']))
        if w is None:
            bad.append('%s/%s names trace case %s, whose delivered bytes conduct no such window'
                       % (key + (tc,)))
            continue
        t0, t1 = window_times(r)
        shifts.add(int(round(claim_ps(r.get('t0_ns')))) - w['t0_ps'])
        if t0 != w['t0_ps'] + shift_ps or t1 != w['t1_ps'] + shift_ps:
            bad.append('%s/%s the case window is [%d, %d] ps while the delivered trace gives '
                       '[%d, %d] ps plus the %d ns shift'
                       % (key + (t0, t1, w['t0_ps'], w['t1_ps'], shift_ps // NS)))
            continue
        edges = B.pwl_edges(r['case_id']) or []
        stim = TR.segments_of(edges, t0, t1) if edges else []
        rtl = [(s[0] + shift_ps, s[1] + shift_ps, s[2]) for s in w['segments_ps']]
        if [s[:2] for s in stim] != [(s[0], s[1]) for s in rtl]:
            bad.append('%s/%s the delivered stimulus edges give %s while the trace pulses are %s'
                       % (key[0], key[1], str([s[:2] for s in stim]),
                          str([(s[0], s[1]) for s in rtl])))
            continue
        if integer_value(r.get('declared_pulses')) != len(w['segments_ps']):
            bad.append('%s/%s declares %s pulse(s); the delivered trace conducts %d'
                       % (key[0], key[1], r.get('declared_pulses'), len(w['segments_ps'])))
            continue
        bound += 1
    if len(shifts) > 1:
        bad.append('the case rows and the trace disagree about the PWL shift: %s'
                   % ', '.join(str(x) for x in sorted(shifts)))
    elif shifts and shifts != {shift_ps}:
        bad.append('the rows sit %d ps after the trace, not the %d ps the deck declares'
                   % (sorted(shifts)[0], shift_ps))
    C.add('RTL_VCD_SEMANTICS_REPARSED', not bad and parsed == len(table) and parsed > 0
          and bound > 0,
          '%d/%d delivered traces re-parsed through the frozen four-state converter and %d case '
          'window(s) bound to their pulses and stimulus edges; %s'
          % (parsed, len(table), bound, '; '.join(bad[:3]) or 'all agree')
          if not bad else '; '.join(bad[:3]))


def check_rtl_reverify(B, C):
    """the delivered trace edges really were rebuilt from the frozen RTL on this machine

    The bundle's fall times are read from pulse edges that come from the four-state run, so the
    re-verification has to be in the bundle and has to be checkable from its own bytes: one row per
    trace case the contract names, every compared field agreeing, the new VCD shipped and hashing to
    its row, and its digest kept separate from the native run's -- an identical digest would mean the
    round re-labelled an old file instead of re-simulating.
    """
    path = os.path.join(B.dir, 'rtl_reverify.csv')
    if not os.path.isfile(path):
        C.add('RTL_EDGES_REVERIFIED', False, 'the bundle ships no rtl_reverify.csv, so the pulse '
              'edges the fall times read from were never re-simulated')
        return
    rows = read_rows(path)
    delivery = {}
    dpath = os.path.join(B.dir, 'rtl_reverify_delivery.csv')
    if os.path.isfile(dpath):
        for r in read_rows(dpath):
            delivery[r['case_id']] = r
    want = sorted(set(r['trace_case'] for r in B.contract.values()
                      if r['trace_case'] not in ('', 'NONE')))
    have = sorted(set(r['case_id'] for r in rows))
    bad = []
    if not rows:
        bad.append('rtl_reverify.csv has a header and no rows')
    if len(rows) > MAX_RTL_SIMULATIONS:
        bad.append('%d rows exceed the %d RTL simulations the task grants'
                   % (len(rows), MAX_RTL_SIMULATIONS))
    if [t for t in want if t not in have]:
        bad.append('%d trace case(s) never re-simulated: %s'
                   % (len([t for t in want if t not in have]),
                      ', '.join([t for t in want if t not in have][:3])))
    if [h for h in have if h not in want]:
        bad.append('%s is not a trace case of this contract' % ', '.join(
            [h for h in have if h not in want][:3]))
    for r in rows:
        cid = r['case_id']
        if r['verdict'] != 'AGREE' or r['mismatched_fields'] not in ('', '-'):
            bad.append('%s: %s (%s)' % (cid, r['verdict'], r['mismatched_fields']))
        if not integer_value(r['fields_compared']):
            bad.append('%s: no field was compared, so AGREE proves nothing' % cid)
        if r['new_vcd_sha256'] == r['accepted_vcd_sha256']:
            bad.append('%s: the new VCD carries the native run\'s digest' % cid)
        # .gitignore holds `*.vcd` out of the repository and Git would fold CRLF to LF on commit, so
        # the bytes arrive as `<name>.vcd.txt` with both digests recorded side by side
        d = delivery.get(cid)
        vcd = None
        if d is None:
            bad.append('%s: rtl_reverify_delivery.csv names no delivery row, so the re-simulated '
                       'bytes are not in the bundle' % cid)
        else:
            if d['simulator_sha256'] != r['new_vcd_sha256']:
                bad.append('%s: the delivery index names bytes the table never hashed' % cid)
            vcd = os.path.join(B.dir, d['delivered_as'])
            if not os.path.isfile(vcd):
                bad.append('%s: %s is not in the bundle' % (cid, d['delivered_as']))
                vcd = None
            elif digest(vcd) != d['delivered_sha256']:
                bad.append('%s: %s does not hash to the delivery index' % (cid, d['delivered_as']))
            elif os.path.getsize(vcd) != integer_value(d['delivered_bytes']):
                bad.append('%s: %s is %d bytes, the delivery index says %s'
                           % (cid, d['delivered_as'], os.path.getsize(vcd), d['delivered_bytes']))
            else:
                with open(vcd, 'rb') as f:
                    blob = f.read()
                if b'\r' in blob:
                    bad.append('%s: the delivered bytes still carry CR, so committing them would '
                               'change every digest' % cid)
                elif hashlib.sha256(blob.replace(b'\n', b'\r\n')).hexdigest() != r['new_vcd_sha256']:
                    bad.append('%s: restoring the delivered bytes to CRLF does not give the '
                               'simulator\'s file the table hashed' % cid)
        listed = (B.source.get('traces') or {}).get(cid) or {}
        if listed.get('vcd_sha256') and listed['vcd_sha256'] != r['accepted_vcd_sha256']:
            bad.append('%s: the table says the delivered run was %s, source_identity says %s'
                       % (cid, r['accepted_vcd_sha256'][:12], listed['vcd_sha256'][:12]))
        head = ''
        if vcd:
            with io.open(vcd, encoding='utf-8', errors='replace') as f:
                head = ''.join([f.readline() for _ in range(4)])
        if '$date' not in head:
            bad.append('%s: the re-simulated VCD carries no $date, so its identity cannot be kept '
                       'apart from the native run' % cid)
        for name, p in (('rtl', RTL_SOURCE), ('tb', TB_SOURCE)):
            if not os.path.isfile(p):
                bad.append('%s: the frozen %s file %s is not on disk to compare' % (cid, name, p))
            elif r['%s_sha256' % name] != digest(p):
                bad.append('%s: the re-simulation ran over a %s other than the frozen one' %
                           (cid, name))
    C.add('RTL_EDGES_REVERIFIED', not bad,
          '%d/%d trace cases re-simulated from the frozen RTL and TB, %s field(s) compared, all AGREE'
          % (len(have), len(want), sum(integer_value(r['fields_compared']) or 0 for r in rows))
          if not bad else '; '.join(bad[:3]))


def check_gate_records(B, C):
    """the bundle's own claim that its tools were tested, read off the record it ships

    A round that re-measures everything still has to show the self-tests and the write-guard /
    fake-Link refusals ran, and the showing must be safe to commit: no local path, no gate carried in
    as a PASS while its recorded exit code says otherwise, and no gate that admits starting a
    simulator or opening a socket.
    """
    path = os.path.join(B.dir, 'gate_records.csv')
    if not os.path.isfile(path):
        C.add('GATE_RECORDS_SHIPPED', False, 'the bundle ships no gate_records.csv, so none of its '
              'self-tests or write-guard refusals are in the delivered bytes')
        return
    rows = read_rows(path)
    need = ('measure_selftest', 'run_entry_selftest', 'trace_selftest',
            'evidence_tamper_selftest', 'execution_guards')
    have = set(r['gate'] for r in rows)
    bad = []
    if not rows:
        bad.append('gate_records.csv has a header and no rows')
    for name in need:
        if name not in have:
            bad.append('the gate %s was not recorded' % name)
    for r in rows:
        if r['verdict'] != 'PASS' or r['rc'] != '0':
            bad.append('%s did not pass (rc=%s verdict=%s)' % (r['gate'], r['rc'], r['verdict']))
        elif not integer_value(r['printed_lines_kept']):
            bad.append('%s kept no printed line, so its PASS is uncorroborated' % r['gate'])
        for k, v in r.items():
            if LOCAL_PATH_RE.search(v):
                bad.append('%s: the field %s names a local path' % (r['gate'], k))
        for k in ('starts_spectre', 'opens_socket', 'writes_outside_ignored'):
            if r.get(k) not in ('NO',):
                bad.append('%s says it %s = %s' % (r['gate'], k, r.get(k)))
    C.add('GATE_RECORDS_SHIPPED', not bad and len(rows) >= len(need),
          '%d gates recorded, all rc=0 PASS, 0 Spectre / 0 sockets' % len(rows)
          if not bad else '; '.join(bad[:3]))


CHECKS = (check_matrix, check_discrete, check_shards, check_series_vs_accepted, check_charge,
          check_qlsb, check_last100, check_peak, check_settle, check_edges, check_off,
          check_electrical_verdict, check_calibration, check_artifacts, check_negatives,
          check_convergence, check_launches, check_identity, check_rtl_reverify,
          check_vcd_semantics, check_gate_records, check_bundle_shape)


def build_checks(ev_dir, C):
    B = Bundle(ev_dir)
    for fn in CHECKS:
        fn(B, C)
    return len([r for r in B.cases if r['verdict'] not in NON_ELECTRICAL])


def bundle_files(ev_dir):
    out = []
    for base, _dirs, names in os.walk(ev_dir):
        for name in names:
            out.append(os.path.relpath(os.path.join(base, name), ev_dir).replace(os.sep, '/'))
    return sorted(out)


def check_dir(ev_dir):
    """every semantic check of one staged bundle as data: the publisher and the tests both use this

    A structural refusal is itself a failure with a reason; it never degrades into an empty pass.
    """
    C = Checks()
    n = 0
    try:
        n = build_checks(ev_dir, C)
    except Exception as exc:
        C.add('EVIDENCE_READABLE', False, '%s: %s' % (type(exc).__name__, str(exc)[:200]))
    failures = [r[0] for r in C.rows if r[1] == 'FAIL']
    return {'checks': C.rows, 'failures': failures, 'reasons': C.reasons, 'recomputed_windows': n,
            'file_count': len(bundle_files(ev_dir)), 'rc': 1 if failures else 0}


def main_dir(ev_dir, report=True):
    res = check_dir(ev_dir)
    if report:
        for name, verdict, detail in res['checks']:
            print('%-34s %-6s %s' % (name, verdict, (detail or '')[:130]))
        print('D7B_EVIDENCE_CHECK: %s (%d checks, %d rows in scope, failures: %s)'
              % ('PASS' if not res['failures'] else 'FAIL', len(res['checks']),
                 res['recomputed_windows'], ' '.join(res['failures']) or '-'))
    return res['rc']


# ---------------------------------------------------------------- tamper self test
COUNTERFEITS = ('false_off_with_PASS',
                'wrong_calibration_scale_and_electrical_FAIL_labeled_PASS',
                'different_PWL_input', 'missing_safety_recovery', 'missing_convergence_rows',
                'false_launch_TOTAL', 'fractional_tick', 'false_N1_observations',
                # the seven DATA-7B-R2 breaks: each one is a number that stays legal to read and only
                # a re-derivation from the delivered bytes can refuse it
                'unauthorised_ceiling_60', 'off_time_zero', 'current_crossing_off_by_5ns',
                'complementary_time_zero', 'convergence_edge_delta_9999ns',
                'delivered_vcd_transition_flipped', 'cal_off_baseline_without_support',
                # the DATA-7B-R3 finding: a state nothing bills, hidden behind synced roll-ups
                'illegal_account_state_with_synced_rollup')
# each break names the check that must react and the case it touched: a check the delivered bundle
# already fails cannot count as "detected", so the new reason itself has to mention this case
EXPECTED_NEW_FAILURE = {
    'false_off_with_PASS': (('LAST_100NS_RECOMPUTED', 'ELECTRICAL_VERDICT_CONSISTENT'),
                            'D7B-P30-C001'),
    'wrong_calibration_scale_and_electrical_FAIL_labeled_PASS': (('QLSB_BOUND_TO_ICAL',
                                                                  'ELECTRICAL_VERDICT_CONSISTENT'),
                                                                 'D7B-P30-C001'),
    'different_PWL_input': (('DECK_AND_PWL_BOUND',), 'D7B-P30-C000'),
    'missing_safety_recovery': (('WINDOW_SET_COMPLETE',), 'D7B-FAULT'),
    'missing_convergence_rows': (('CONVERGENCE_SET_COMPLETE',), 'D7B-CVG'),
    'false_launch_TOTAL': (('RECONCILE_SUMS_TO_TOTAL',), 'TOTAL'),
    'fractional_tick': (('DISCRETE_VALUES_MATHEMATICAL',), 'D7B-P30-C001'),
    'false_N1_observations': (('NEGATIVES_BOUND_TO_BYTES',), 'D7B-N1'),
    'unauthorised_ceiling_60': (('BUDGET_AUTHORITY_FIXED',), 'ceiling'),
    'off_time_zero': (('OFF_TIMES_RECOMPUTED',), 'D7B-P30-C001'),
    'current_crossing_off_by_5ns': (('EDGES_BRACKETED_BY_SAMPLES',), 'D7B-P30-C001'),
    'complementary_time_zero': (('EDGES_BRACKETED_BY_SAMPLES',), 'data_en_b'),
    'convergence_edge_delta_9999ns': (('CONVERGENCE_RECOMPUTED',), 'D7B-CVG'),
    'delivered_vcd_transition_flipped': (('RTL_VCD_SEMANTICS_REPARSED',
                                          'RTL_EDGES_REVERIFIED'), 'D7B-P30-C001'),
    'cal_off_baseline_without_support': (('CALIBRATION_OFF_BASELINE_SAMPLES',), 'D7B-CAL'),
    'illegal_account_state_with_synced_rollup': (('ACCOUNT_STATES_VALID',), 'A001'),
}


def write_rows(path, hdr, rows):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(','.join(hdr) + '\n')
        for r in rows:
            f.write(','.join(str(r.get(k, '')) for k in hdr) + '\n')


def tamper(name, ev):
    """the eight semantic breaks of the review, applied to a disposable copy only"""
    def change_cases(fn):
        rows = rows_of(os.path.join(ev, 'cases.csv'))
        hdr = list(rows[0].keys())
        fn(rows)
        write_rows(os.path.join(ev, 'cases.csv'), hdr, rows)

    if name == 'false_off_with_PASS':
        def edit(rows):
            r = next(x for x in rows if x['case_id'] == 'D7B-P30-C001')
            r['last_100ns_max_abs_A'] = '1.5e-5'
            r['verdict'] = 'PASS'
        change_cases(edit)
    elif name == 'wrong_calibration_scale_and_electrical_FAIL_labeled_PASS':
        def edit(rows):
            r = next(x for x in rows if x['case_id'] == 'D7B-P30-C001')
            r['q_lsb_C'] = str(float(r['q_lsb_C']) * 2)
            r['q_expected_C'] = r['q_lsb_C']
            r['charge_error_LSB'] = str((float(r['q_win_C']) - float(r['q_expected_C']))
                                        / float(r['q_lsb_C']))
            r['verdict'] = 'PASS'
        change_cases(edit)
    elif name == 'different_PWL_input':
        with io.open(os.path.join(ev, 'pwl', 'D7B-P30-C000_pwl.txt'), 'w', encoding='utf-8',
                     newline='\n') as f:
            f.write('0 1.8\n12000000 1.8\n')
    elif name == 'missing_safety_recovery':
        rows = rows_of(os.path.join(ev, 'cases.csv'))
        hdr = list(rows[0].keys())
        write_rows(os.path.join(ev, 'cases.csv'), hdr,
                   [r for r in rows if not (r['case_id'] == 'D7B-FAULT'
                                            and r['window'] == 'recovery')])
    elif name == 'missing_convergence_rows':
        rows = rows_of(os.path.join(ev, 'convergence.csv'))
        write_rows(os.path.join(ev, 'convergence.csv'), list(rows[0].keys()), [])
    elif name == 'false_launch_TOTAL':
        rows = rows_of(os.path.join(ev, 'launches_reconcile.csv'))
        hdr = list(rows[0].keys())
        next(r for r in rows if r['task_root_dir'] == 'TOTAL')[
            'processes_counted_against_ceiling'] = '27'
        write_rows(os.path.join(ev, 'launches_reconcile.csv'), hdr, rows)
    elif name == 'fractional_tick':
        def edit(rows):
            next(x for x in rows if x['case_id'] == 'D7B-P30-C001')['tick_ns'] = '30.5'
        change_cases(edit)
    elif name == 'false_N1_observations':
        rows = rows_of(os.path.join(ev, 'negative.csv'))
        hdr = list(rows[0].keys())
        n = next(r for r in rows if r['case_id'] == 'D7B-N1')
        n['q_win_C'] = '0'
        for col in ('window_peak_uA', 'window_peak_A', 'last_100ns_max_abs_uA'):
            if col in hdr:
                n[col] = '0'
        write_rows(os.path.join(ev, 'negative.csv'), hdr, rows)
    elif name == 'unauthorised_ceiling_60':
        rows = rows_of(os.path.join(ev, 'launch_account.csv'))
        hdr = list(rows[0].keys())
        for r in rows:
            r['ceiling'] = '60'
        write_rows(os.path.join(ev, 'launch_account.csv'), hdr, rows)
    elif name == 'off_time_zero':
        def edit(rows):
            next(x for x in rows if x['case_id'] == 'D7B-P30-C001'
                 and x['window'] == 'normal')['off_ns'] = '0.0000'
        change_cases(edit)
    elif name == 'current_crossing_off_by_5ns':
        def edit(rows):
            r = next(x for x in rows if x['case_id'] == 'D7B-P30-C001'
                     and x['window'] == 'normal')
            r['current_10pct_ns'] = '%.4f' % (float(r['current_10pct_ns']) + 5.0)
        change_cases(edit)
    elif name == 'complementary_time_zero':
        def edit(rows):
            for r in rows:
                for col in ('de_b_fall_50_ns', 'de_b_rise_50_ns'):
                    if col in r and r[col] not in ('', 'NOT_SAVED', 'NOT_FOUND',
                                                   'NOT_APPLICABLE_NO_CONDUCTING_EDGE'):
                        r[col] = '0.0000'
        change_cases(edit)
    elif name == 'convergence_edge_delta_9999ns':
        rows = rows_of(os.path.join(ev, 'convergence.csv'))
        hdr = list(rows[0].keys())
        for r in rows:
            if r.get('delta_edge_ns') not in ('', 'NOT_FOUND_BOTH'):
                r['delta_edge_ns'] = '9999.0000'
        write_rows(os.path.join(ev, 'convergence.csv'), hdr, rows)
    elif name == 'delivered_vcd_transition_flipped':
        tamper_vcd_transition(ev)
    elif name == 'cal_off_baseline_without_support':
        rows = rows_of(os.path.join(ev, 'calibration.csv'))
        hdr = list(rows[0].keys())
        next(r for r in rows if r['quantity'] == 'OFF_baseline_max_abs_A')['value_A'] = '1e-07'
        write_rows(os.path.join(ev, 'calibration.csv'), hdr, rows)
    elif name == 'illegal_account_state_with_synced_rollup':
        # the row that says "no process was started" is moved to a state nothing bills, and the
        # environment roll-up is lowered to match, so no count disagrees with any other count and
        # only an enumeration of every row can see that a legal spelling was replaced by nonsense
        rows = rows_of(os.path.join(ev, 'launch_account.csv'))
        hdr = list(rows[0].keys())
        moved = None
        for r in rows:
            if r['state'] == 'REFUSED_NO_LAUNCH':
                r['state'] = 'UNRECOGNISED_STATE'
                moved = r['launch_id']
                break
        if moved is None:
            raise MS.Refuse('no REFUSED_NO_LAUNCH row to corrupt')
        write_rows(os.path.join(ev, 'launch_account.csv'), hdr, rows)
        epath = os.path.join(ev, 'environment.json')
        env = json.loads(u(io.open(epath, encoding='utf-8').read()))
        roll = env.get('launch_account') or {}
        if 'no_launch' in roll:
            roll['no_launch'] = roll['no_launch'] - 1
            with io.open(epath, 'w', encoding='utf-8', newline='\n') as f:
                f.write(json.dumps(env, indent=1, sort_keys=True) + '\n')
    else:
        raise MS.Refuse('unknown counterfeit %s' % name)


def tamper_vcd_transition(ev):
    """hold one data_en rise low inside the abort window, then forge every digest around it

    The four-state bytes still hash to what the tables say, so only a verifier that reads the
    transitions themselves can notice that the window no longer conducts the pulse its golden row and
    its case row both claim.
    """
    dpath = os.path.join(ev, 'rtl_reverify_delivery.csv')
    if not os.path.isfile(dpath):
        raise MS.Refuse('no delivery index, so the counterfeit has nothing to flip')
    delivery = rows_of(dpath)
    row = next((r for r in delivery if r['case_id'] == 'D7B-P30-C001'), None) or delivery[0]
    path = os.path.join(ev, row['delivered_as'])
    lines = u(io.open(path, encoding='utf-8', errors='replace').read()).split('\n')
    ident = {}
    for line in lines:
        if line.startswith('$var'):
            parts = line.split()
            if len(parts) >= 5 and parts[4] == 'data_en':
                ident['data_en'] = parts[3]
    if 'data_en' not in ident:
        raise MS.Refuse('%s names no data_en variable, so there is no transition to flip'
                        % row['delivered_as'])
    mark = ident['data_en']
    now, out, flipped = None, [], None
    for line in lines:
        if line.startswith('#'):
            now = float(line[1:].strip())
            out.append(line)
            continue
        if not flipped and line == '1' + mark and 1400000 <= (now or 0) <= 1600000:
            line = '0' + mark
            flipped = now
            continue
        out.append(line)
    if not flipped:
        raise MS.Refuse('no data_en rise inside 1.4..1.6 us, so this counterfeit would prove nothing')
    blob = '\n'.join(out)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(blob)
    delivered = hashlib.sha256(blob.replace('\n', '\r\n').encode('utf-8'))
    simulator = delivered.hexdigest()
    lf = hashlib.sha256(blob.encode('utf-8')).hexdigest()
    for name, pairs in ((os.path.join(ev, 'rtl_reverify.csv'),
                        (('new_vcd_sha256', simulator),)),
                        (dpath, (('delivered_sha256', lf), ('simulator_sha256', simulator),
                                 ('delivered_bytes', str(len(blob)))))):
        rows = rows_of(name)
        hdr = list(rows[0].keys())
        for r in rows:
            if r['case_id'] != row['case_id']:
                continue
            for col, value in pairs:
                r[col] = value
        write_rows(name, hdr, rows)


def reseal(ev):
    """recompute the manifest exactly as a forger would, so only semantics can catch the break"""
    path = os.path.join(ev, 'manifest.json')
    if not os.path.isfile(path):
        return
    man = json.loads(u(io.open(path, encoding='utf-8').read()))
    for item in man['files']:
        raw = io.open(os.path.join(ev, item['path']), 'rb').read()
        item['bytes'] = len(raw)
        item['sha256'] = hashlib.sha256(raw).hexdigest()
    man['total_bytes'] = sum(x['bytes'] for x in man['files'])
    man['file_count'] = len(man['files'])
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(man, indent=1, sort_keys=True) + '\n')


def selftest(base=None):
    """each counterfeit must raise its own named failure on a disposable copy of committed bytes"""
    import glob
    import shutil
    import tempfile
    if base is None:
        for pattern in ('dd1_d7b_r2_*', 'dd1_d7b_r1_*', ACCEPTED_BUNDLE_NAME):
            hits = sorted(glob.glob(os.path.join(PROJ, 'results', 'evidence', pattern)))
            hits = [h for h in hits if os.path.isfile(os.path.join(h, 'cases.csv'))]
            if hits:
                base = hits[-1]
                break
    base = base or os.path.join(PROJ, 'results', 'evidence', 'dd1_d7b_r11_main')
    if not os.path.isdir(base):
        print('D7B_EVIDENCE_SELFTEST: FAIL no committed bundle to copy at %s' % base)
        return 1
    problems = []
    res = check_dir(base)
    baseline = set(res['failures'])
    base_reasons = res['reasons']
    print('SELFTEST_BASELINE %s rc=%d failures=%s'
          % (os.path.basename(base), res['rc'], ' '.join(sorted(baseline)) or '-'))
    for name in COUNTERFEITS:
        temp = tempfile.mkdtemp(prefix='d7b-counterfeit-')
        try:
            dest = os.path.join(temp, 'evidence')
            shutil.copytree(base, dest)
            tamper(name, dest)
            reseal(dest)
            got = check_dir(dest)
            new = sorted(set(got['failures']) - baseline)
            if 'EVIDENCE_READABLE' in new:
                detail = dict((c[0], c[2]) for c in got['checks']).get('EVIDENCE_READABLE', '')
                problems.append('%s broke the checker itself: %s' % (name, detail))
            checks, mark = EXPECTED_NEW_FAILURE[name]
            caught = []
            for check in checks:
                if check in new:
                    caught.append('%s became a failing check' % check)
                    continue
                added = [x for x in got['reasons'].get(check, [])
                         if mark in x and x not in base_reasons.get(check, [])]
                if added:
                    caught.append('%s added a reason about %s: %s'
                                  % (check, mark, added[0][:90]))
            print('%-58s rc=%d caught=%s'
                  % (name, got['rc'], ' | '.join(caught) or 'ESCAPED'))
            if not caught:
                problems.append('%s escaped: %s gained neither a failure nor a new reason naming %s'
                                % (name, ' and '.join(checks), mark))
        finally:
            shutil.rmtree(temp, ignore_errors=True)
    print('D7B_EVIDENCE_SELFTEST: %s (%d counterfeits, %d problem(s))'
          % ('PASS' if not problems else 'FAIL', len(COUNTERFEITS), len(problems)))
    for pb in problems:
        print('SELFTEST_BAD %s' % pb)
    return 1 if problems else 0


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    if '--selftest' in argv:
        return selftest(args[0] if args else None)
    if not args:
        print('usage: dd1_d7b_evidence_check.py <evidence dir> [--selftest]')
        return 2
    return main_dir(args[0])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
