# -*- coding: utf-8 -*-
"""DATA-7B entry point: frozen RTL trace -> finite-slope PWL -> 7-device MOS stage -> Spectre.

    python scripts/dd1_d7b_run.py --selftest
    python scripts/dd1_d7b_run.py --dry --expect 24
    python scripts/dd1_d7b_run.py --supply-negative
    RUN=1 QODER_SIM_AUTHORISED=1 python scripts/dd1_d7b_run.py --run --expect 24
    python scripts/dd1_d7b_run.py --check-evidence results/evidence/dd1_d7b_<run_id>

Design rules this file enforces:

  * every circuit byte it uses is taken from the accepted Git blob at BASE_SHA, never from whatever the
    working tree happens to hold, and each of the four masters is written next to the deck it belongs to;
  * `parameters <port> <direction>` comment lines are the only normalisation the simulator gets (this
    build reads them as repeated parameter definitions, SFE-59). Every stripped line is counted per file
    and the device/subckt statement digest of the normalised text must equal the repository text's;
  * the supply contract is the frozen `sc1_supply_check.awk` semantics through the frozen
  `tb_preflight.sh`, with `vdd18=1.8 vdd=1.8 vss=0 VSS=0` covering both spellings, and every non-PDK
  level is expanded before the check;
  * all static gates run before the first Spectre launch; each DUT is preceded by its own dynamic rail
  preflight; each launch is written to a persistent ledger before it happens and fails are counted;
  * `--dry`, refusals and unauthorised calls may only touch ignored scratch (rule 27): nothing in
  `results/evidence/` is written, and the formal directory is published by moving a fully validated
  bundle into a path that must not already exist.
"""
from __future__ import print_function

import hashlib
import io
import json
import optparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_trace as TR                     # this round's trace/PWL converter
import dd1_d7b_measure as MS                   # this round's measurement core
import sc1_r2e1_call_contract as CC              # frozen: real exit codes, never a pipeline status
import sc1_read_psf as RD                         # frozen PSF-ASCII parser

BASE_SHA = 'c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37'
ACCEPTED_SHA = 'f68449672774ac9266ba9e4893024e4f3027dd9d'
TASK_ID = 'DATA-7B'
# DATA-7B-R1: this build repairs the tools of the delivered round. T is the reviewed tip the retained
# raw bytes come from; every reused number is labelled with it instead of being passed off as new.
REPAIR_TASK_ID = 'DATA-7B-R1'
REPAIR_BASE_SHA = 'adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50'
REPAIR_PAYLOAD_SHA = '9d73cc184a266e646ae827f0350f7c931d9faa25'
BRANCH = 'poc/data-pwm-d7b-r1'

V18 = 1.8
VCAS_V = 1.8
IREF_TXT = '15u'
I_NOMINAL = 15e-6
VCLAMP_DEFAULT = 1.2
SECTION = 'tt'
TEMP_C = 27
SHIFT_NS = 2500            # reference pre-establishment: the first RTL edge never sits at t = 0
TAIL_NS = 200              # every window is simulated 200 ns past its logical end
EDGE_SEARCH_NS = 50        # how far around an expected edge the 50 % crossings may be found
STOP_MARGIN_NS = 50        # the simulated stop runs this far past the last measured bound, so every
                           # integration edge has a clamping sample on both sides (measured: this
                           # build's last accepted point sits a fraction of a ps short of the stop)
MAXSTEP_BASE_NS = '0.5'
RAMP_BASE_NS = 2
CAL_PWL = [(0, 0.0), (1999000, 0.0), (2001000, 1.8), (3999000, 1.8),
           (4001000, 0.0), (4500000, 0.0)]     # ps: low, up at 2 us, down at 4 us, stop 4.5 us
CAL_STOP_PS = 4500000
CAL_BAND = (3000000, 3500000)          # Ical window, 3.0 us .. 3.5 us
CAL_OFF = (1500000, 1900000)           # OFF baseline before the calibration pulse
CAL_TAIL = (4400000, 4500000)          # end-of-conduction check

GUEST_ROOT = '/root/microled_ai_project/cadence_work/dd1_d7b'
GUEST_HOST = os.environ.get('QODER_GUEST_IP', '192.168.3.128')
GUEST_USER = 'root'
SSH_KEY = os.path.expanduser('~/.ssh/id_rsa_ic617')
SSH_COMPAT = ['-oBatchMode=yes', '-oConnectTimeout=20', '-oStrictHostKeyChecking=accept-new',
              '-oHostKeyAlgorithms=+ssh-rsa', '-oPubkeyAcceptedKeyTypes=+ssh-rsa']
GUEST_PDK_ENV = '/root/microled_ai_project/spectre/pdk_local.env'   # read only, never copied
SUPPLY_MAP = 'vdd18=1.8 vdd=1.8 vss=0 VSS=0'
NS = 1000                                  # picoseconds per nanosecond
NL = chr(10)                              # remote payloads are assembled without shell heredocs
EXPECTED_VDD = '1.8'
# The task book authorises 52 launches. Seven were spent on reproducing this round's own two
# tool defects (see the report's failed-attempt table); on 2026-10-21 the user granted four more
# for this round only, so the ceiling this run enforces is 56 and every launch is still counted.
LAUNCH_BUDGET = 56
LAUNCH_BUDGET_TASKBOOK = 52
LAUNCH_BUDGET_USER_GRANTED_EXTRA = 4
PREFLIGHT_PER_DUT = 1

# DATA-7B-R1 execution guards. The modes are a closed list: a call that names none of them, or more
# than one, is refused before a single byte of preparation happens, because in the delivered build a
# bare call fell through to the native branch with both authorisation variables unset.
MODES = ('selftest', 'dry', 'run', 'supply_negative', 'check_evidence', 'static_probe',
         'write_manifest', 'remeasure', 'account')
NATIVE_MODES = ('run', 'supply_negative', 'static_probe')
AUTH_VARS = ('RUN', 'QODER_SIM_AUTHORISED')
# the delivered DATA-7B bundle is the only source of the historical launch count; the account is
# rebuilt from its reconcile table so a fresh checkout cannot quietly start from zero
HISTORICAL_EVIDENCE = os.path.join(PROJ, 'results', 'evidence', 'dd1_d7b_r11_main')
ACCEPTED_BUNDLE_NAME = 'dd1_d7b_r11_main'
NEW_SERIES_MARK = 'NEW_IN_R1_NOT_IN_ACCEPTED_BUNDLE'
RTL_PATH = os.path.join(PROJ, 'rtl', 'dd1_d7a_gray_ctrl.sv')
TB_PATH = os.path.join(PROJ, 'tests', 'dd1_d7b', 'tb_dd1_d7b_pwm.sv')
MAX_RTL_SIMULATIONS = 17           # the four-state re-verifications TASK_DATA7B_R1 grants, at most
ACCOUNT_PATH = os.environ.get('DD1_D7B_ACCOUNT') or os.path.join(
    PROJ, 'review', 'scratch', 'dd1_d7b_launch_account.csv')
RUN_ID_RE = re.compile(r'^r[0-9]{8}_[0-9]{6}_[0-9a-f]{6}$')
PUBLISHED_PREFIX = 'dd1_d7b_r1_'          # DATA-7B-R1 evidence is named dd1_d7b_r1_<run_id>

MASTER_FILES = ('dd1_d6_bias_core.scs', 'dd1_d6_sink_core.scs', 'dd1_d6_inv18.scs',
               'dd1_d7b_pwm_stage.scs')
FROZEN_RUNNER = ('scripts/run_spectre.sh', 'scripts/tb_preflight.sh', 'scripts/sc1_supply_check.awk')
DIRECTION_RE = re.compile(r'^\s*parameters\s+[A-Za-z_]\w*\s+(?:input|output|inputOutput|inout)'
                          r'\s*$')


def u(s):
    if isinstance(s, str):
        return s
    return s.decode('utf-8', 'replace')


def sha_txt(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def sha_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def _source_sha(name):
    p = os.path.join(HERE, name)
    return sha_file(p) if os.path.isfile(p) else ''


# Three identities are kept apart, because the delivered round reported them under one word and a
# re-measurement then looked like a re-run: the native run that produced the bytes, the measurement
# source that turned them into numbers, and this round's export.
MS_SOURCE_SHA = _source_sha('dd1_d7b_measure.py')
RUN_SOURCE_SHA = _source_sha('dd1_d7b_run.py')
TRACE_SOURCE_SHA = _source_sha('dd1_d7b_trace.py')


def git_blob(ref, path):
    """the accepted bytes, straight out of the object store"""
    p = subprocess.Popen(['git', 'cat-file', 'blob', '%s:%s' % (ref, path)], cwd=PROJ,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError('git cat-file blob %s:%s failed: %s' % (ref, path, u(err).strip()))
    return u(raw)


def strip_direction_annotations(txt):
    kept, removed = [], []
    for line in txt.split('\n'):
        if DIRECTION_RE.match(line):
            removed.append(line.strip())
            continue
        kept.append(line)
    return '\n'.join(kept), removed


def device_digest(txt):
    """digest over electrical content only: device and subckt-instance statements"""
    body = [l.strip() for l in txt.split('\n')
            if re.match(r'^\s*[A-Za-z]\w*\s*\(', l) and not re.search(r'vsource|isource|capacitor|'
                                                                     r'resistor|inductor', l)]
    return sha_txt('\n'.join(body))[:16]


def port_order_digest(txt):
    """subckt port lists plus every device terminal list -- catches what a device-only digest misses"""
    rows = []
    for l in txt.split('\n'):
        s = l.strip()
        if s.lower().startswith('subckt ') or re.match(r'^[A-Za-z]\w*\s*\(', s):
            rows.append(re.sub(r'\s+', ' ', s))
    return sha_txt('\n'.join(rows))[:16]


def masters():
    """the four masters as the simulator will receive them, with per-file stripping accounts"""
    out = []
    for name in MASTER_FILES:
        if name.startswith('dd1_d7b_'):
            # this round's own wrapper: read from the working tree and bind its digest in the manifest
            raw = u(io.open(os.path.join(PROJ, 'spectre', name), encoding='utf-8',
                            errors='replace').read())
        else:
            raw = git_blob(BASE_SHA, 'spectre/' + name)
        norm, removed = strip_direction_annotations(raw)
        if device_digest(raw) != device_digest(norm):
            raise RuntimeError('%s: normalisation changed the device statements' % name)
        if port_order_digest(raw) != port_order_digest(norm):
            raise RuntimeError('%s: normalisation changed a port or terminal list' % name)
        out.append({'name': name, 'repo_sha256': sha_txt(raw), 'sent_sha256': sha_txt(norm),
                    'removed': removed, 'text': norm, 'bytes_repo': len(raw.encode('utf-8')),
                    'bytes_sent': len(norm.encode('utf-8'))})
    return out


def fmt_t(ps):
    return '%.12g' % (ps * 1e-12)


def fmt_v(v):
    return '%.6g' % v


def pwl_clause(points):
    """the accepted deck spelling: one flat bracket list, whole-nanosecond times

    DATA-6 established `type=pwl wave=[t v t v ...]` with `n` suffixed times; the parenthesised
    per-pair form is refused by this build's circuit read-in (measured: SFE-874 "Unexpected integer",
    and it cost one preflight launch to learn it). A time that is not a whole number of ns is refused
    rather than rounded, because rounding would move the ramp off the real RTL edge.
    """
    toks = []
    for t, v in points:
        if t % 1000:
            raise RuntimeError('PWL time %d ps is not a whole number of nanoseconds' % t)
        toks.append('0' if t == 0 else '%dn' % (t // 1000))
        toks.append(fmt_v(v))
    return '[' + ' '.join(toks) + ']'


DECK_HEAD = '''simulator lang=spectre insensitive=yes
// DATA-7B %s -- %s
// model binding comes from the git-ignored spectre/pdk_local.env on the guest; run_spectre.sh refuses
// an unexpanded ${QODER_PDK_LIB}, so this deck is only runnable where that file exists.
include "${QODER_PDK_LIB}" section=%s
'''


def build_deck(case, points, mst, note=''):
    """one deck per DUT launch: PWL enable, frozen 7-device stage, zero-burden ammeter"""
    stop_ps = points[-1][0]
    lines = [DECK_HEAD % (case['case_id'], note or case['role'], SECTION)]
    lines.append(''.join('include "%s"\n' % m['name'] for m in mst))
    lines.append('// temperature is read back from the produced log and psf header; the instantiation\n'
                 '// form is what this build accepts (a bare `options temp=27\' is SFE-709).\n'
                 'simopt options temp=%d\n' % TEMP_C)
    lines.append('// TESTBENCH_ASSUMPTION: IREF is injected into the diode-connected reference node and\n'
                 '// VCAS is a bench rail. No autonomous reference, no PAM ladder, no LED model.\n'
                 'Iref (0 iref_in) isource dc=%s\n' % IREF_TXT)
    lines.append('Vcas (vcas 0) vsource dc=%s\n' % fmt_v(VCAS_V))
    lines.append('V18 (vdd18 0) vsource dc=%s\n' % fmt_v(V18))
    lines.append('// rule 19: every rail has an explicit source to the reference node, including 0 V\n'
                 'Vss (vss 0) vsource dc=0\n')
    lines.append('// the pixel is a clamp, not a load: DATA_OUT is held at %s V\n'
                 % fmt_v(float(case['vclamp_v'])))
    lines.append('Vclamp (clamp 0) vsource dc=%s\n' % fmt_v(float(case['vclamp_v'])))
    if case['role'] == 'negative_wiring':
        lines.append('// WIRING FAULT DECK: only this instance statement differs from the positive\n'
                     '// case, by one net -- the enable pin is tied to vdd18 instead of the PWL node.\n')
        lines.append('Xstage (vdd18 iref_in vcas data_out vdd18 vss) dd1_d7b_pwm_stage\n')
    else:
        lines.append('Vde (data_en 0) vsource type=pwl wave=%s\n' % pwl_clause(points))
        lines.append('Xstage (data_en iref_in vcas data_out vdd18 vss) dd1_d7b_pwm_stage\n')
    lines.append('// zero-burden ammeter; positive means current from the clamp into the DUT pin\n'
                 'Ip_out (clamp data_out) iprobe\n')
    lines.append('sw1 tran stop=%s maxstep=%s method=gear2only\n'
                 % (fmt_t(stop_ps), fmt_t(int(float(case['maxstep_ns']) * 1000))))
    lines.append('save data_en iref_in vcas vdd18 vss clamp data_out Xstage.data_en_b '
                 'Xstage.Xsink.vbias_ch Xstage.Xsink.node_m\nsave Ip_out:i\n')
    return ''.join(lines), points, stop_ps


def combined_pwl(doc, window_ids, shift_ps, ramp_ps):
    """one PWL over several windows of the same trace, with the level carried in from before them"""
    wins = [w for w in doc['windows'] if w['window'] in window_ids]
    if not wins:
        raise RuntimeError('no window %s in %s' % (window_ids, doc['case_id']))
    t_from = min(w['t0_ps'] for w in wins) - 50 * 1000
    t_to = max(w['t_stop_ps'] for w in wins)
    edges = [(t, v) for t, v in doc['facts']['data_en_edges'] if t_from <= t <= t_to]
    pts, _cur = TR.build_pwl(edges, t_from, t_to, shift_ps, ramp_ps)
    # hold the last level 50 ns longer than the last measured bound: the simulator's final accepted
    # sample can land a fraction of a ps short of the requested stop, and an integration bound must
    # have a clamping sample on both sides rather than being extrapolated
    return pts + [(pts[-1][0] + STOP_MARGIN_NS * 1000, pts[-1][1])]


def load_cases(path):
    rows = []
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = [h.strip() for h in f.readline().strip().split(',')]
        for line in f:
            if not line.strip():
                continue
            vals = [v.strip() for v in line.rstrip('\r\n').split(',')]
            if len(vals) != len(hdr):
                raise RuntimeError('case row has %d fields against a %d field header: %s'
                                  % (len(vals), len(hdr), line.strip()))
            rows.append(dict(zip(hdr, vals)))
    return rows

# ------------------------------------------------------------------ guest channel
def _b64(s):
    import base64
    return base64.b64encode(s.encode('utf-8')).decode('ascii')


class Link(object):
    """ssh/scp through an argv list; the child's own exit code is what counts.

    The payload travels base64-encoded, so neither Windows quoting nor bash can rewrite it, and the
    remote side cats its own output back before exiting with the payload's status -- there is no
    pipeline here whose last element could hide a failure.
    """

    def __init__(self, host, root, log_dir):
        self.host = host
        self.root = root
        self.log_dir = log_dir
        self.seq = 0

    def _opts(self):
        return ['-i', SSH_KEY] + SSH_COMPAT

    def run(self, script, timeout=900, label='cmd'):
        self.seq += 1
        tag = 'l%d_%d' % (self.seq, int(time.time()) % 1000000)
        remote = '/tmp/dd1_d7b_%s.sh' % tag
        out = '/tmp/dd1_d7b_%s.out' % tag
        wrap = ("umask 077; printf %%s '%s' | base64 -d > %s; timeout %d bash -l %s > %s 2>&1; "
                "rc=$?; cat %s; rm -f %s %s; exit $rc"
                % (_b64(script), remote, timeout, remote, out, out, remote, out))
        argv = ['ssh'] + self._opts() + ['%s@%s' % (GUEST_USER, self.host), wrap]
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = u(p.communicate()[0]).replace('\r\n', '\n')
        with io.open(os.path.join(self.log_dir, 'guest_%03d_%s.txt' % (self.seq, label)),
                     'w', encoding='utf-8', newline='\n') as f:
            f.write(u('ssh payload %d bytes, timeout %d s\n' % (len(script), timeout)))
            f.write(u(text))
        return p.returncode, text

    def push(self, local, remote, label='push'):
        argv = ['scp'] + self._opts() + ['-B', local.replace('\\', '/'),
                                         '%s@%s:%s' % (GUEST_USER, self.host, remote)]
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw = p.communicate()[0]
        if p.returncode != 0:
            raise RuntimeError('scp push %s -> %s failed rc=%d: %s'
                               % (local, remote, p.returncode, u(raw).strip()[:200]))
        rc, out = self.run('sha256sum %s' % remote, 120, label + '-verify')
        want = sha_file(local)
        if rc != 0 or want not in (out or ''):
            raise RuntimeError('the pushed copy of %s does not match the local bytes (%s, rc=%d)'
                               % (remote, want[:16], rc))
        return want

    def pull(self, remote, local):
        argv = ['scp'] + self._opts() + ['-B', '%s@%s:%s' % (GUEST_USER, self.host, remote),
                                         local.replace('\\', '/')]
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        raw = p.communicate()[0]
        if p.returncode != 0 or not os.path.isfile(local):
            raise RuntimeError('scp pull %s failed rc=%d: %s'
                               % (remote, p.returncode, u(raw).strip()[:200]))
        return sha_file(local)


# ------------------------------------------------------------------ process ledger
class AppendCSV(object):
    """a file that already exists is read back before anything is written, and only ever grows

    The DATA-7B-R1 defect was the opposite: `__init__` ignored the bytes on disk and `write()` used
    mode `w`, so re-opening the same path in a new process reset the count to zero and deleted the
    history. Both the per-run ledger and the task-level account now load first, keep every row they
    did not create, and refuse to write a file that has lost rows. A file whose own id series has a
    hole in it is refused on read, so an external edit cannot quietly remove a launch.
    """

    HDR = []
    PREFIX = ''

    def __init__(self, path):
        self.path = path
        self.rows = []
        self.loaded_ids = set()
        if os.path.isfile(path):
            with io.open(path, encoding='utf-8', newline='') as f:
                hdr = f.readline().strip().split(',')
                if hdr and hdr != self.HDR:
                    raise RuntimeError('%s was written with a different header: %s'
                                       % (os.path.basename(path), ','.join(hdr)))
                for line in f:
                    if not line.strip():
                        continue
                    vals = line.rstrip('\r\n').split(',')
                    if len(vals) != len(self.HDR):
                        raise RuntimeError('%s has a %d-field row, the header has %d'
                                           % (os.path.basename(path), len(vals), len(self.HDR)))
                    self.rows.append(dict(zip(self.HDR, vals)))
            self.loaded_ids = set(r['launch_id'] for r in self.rows)
            if self.PREFIX:
                self.check_ids()

    def check_ids(self):
        nums = []
        for r in self.rows:
            lid = r['launch_id']
            if not lid.startswith(self.PREFIX):
                continue
            if not re.match(r'^%s\d+$' % self.PREFIX, lid):
                raise RuntimeError('%s has a malformed launch id %r' % (self.path, lid))
            nums.append(int(lid[len(self.PREFIX):]))
        if sorted(nums) != list(range(1, len(nums) + 1)):
            raise RuntimeError('%s lost a row: its %s ids are %s, not a gapless 1..%d series'
                               % (os.path.basename(self.path), self.PREFIX,
                                  ','.join(str(n) for n in sorted(nums)[:6]), len(nums)))

    def _next_id(self):
        """the next id in this file's own series, whatever other prefixes it also carries"""
        used = [int(r['launch_id'][len(self.PREFIX):]) for r in self.rows
                if re.match(r'^%s\d+$' % self.PREFIX, r['launch_id'])]
        return '%s%03d' % (self.PREFIX, max(used) + 1 if used else 1)

    def flush(self):
        for r in self.rows:
            for k, v in r.items():
                if ',' in str(v) or '\n' in str(v):
                    raise RuntimeError('%s: field %s carries a comma or newline' % (self.path, k))
        ids = [r['launch_id'] for r in self.rows]
        if len(set(ids)) != len(ids):
            raise RuntimeError('%s: launch_id repeats' % self.path)
        lost = self.loaded_ids - set(ids)
        if lost:
            raise RuntimeError('%s refuses to drop %d previously recorded row(s)'
                               % (self.path, len(lost)))
        tmp = self.path + '.tmp'
        with io.open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write(','.join(self.HDR) + '\n')
            for r in self.rows:
                f.write(','.join(str(r.get(k, '')) for k in self.HDR) + '\n')
        if os.path.isfile(self.path):
            os.remove(self.path)
        os.rename(tmp, self.path)


class Ledger(AppendCSV):
    """a row exists before the launch; a failed launch still costs one"""

    HDR = ['launch_id', 'case_id', 'role', 'state', 'requested_utc', 'ended_utc', 'rc',
           'spectre_line', 'deck_sha256', 'pwl_sha256', 'raw_sha256', 'log_sha256', 'refusal',
           'launches_used_after']
    PREFIX = 'L'

    def __init__(self, path):
        AppendCSV.__init__(self, path)
        # a reopened ledger starts where the file left off, never at zero
        self.used = max([int(r['launches_used_after'] or 0) for r in self.rows] or [0])

    def begin(self, case_id, role, deck_sha, pwl_sha):
        self.rows.append({'launch_id': self._next_id(), 'case_id': case_id,
                          'role': role, 'state': 'REQUESTED',
                          'requested_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          'ended_utc': '', 'rc': '', 'spectre_line': '', 'deck_sha256': deck_sha,
                          'pwl_sha256': pwl_sha, 'raw_sha256': '', 'log_sha256': '',
                          'refusal': '', 'launches_used_after': str(self.used)})
        self.flush()
        return self.rows[-1]

    def finish(self, row, rc, text, raw_sha='', log_sha='', refusal='', launched=None):
        row['state'] = 'DONE'
        row['ended_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        row['rc'] = str(rc)
        m = re.search(r'^SPECTRE name=\S+ rc=\S+', text or '', re.M)
        row['spectre_line'] = (m.group(0).replace(',', ';').replace(' ', '_') if m
                               else 'NO_SPECTRE_LINE')
        if launched is None:
            launched = 1 if m else 0
        if launched:
            self.used += 1
        row['spectre_line'] = row['spectre_line'] or ('PREFLIGHT_INNER_spectre_rc_seen' if launched
                                                     else 'NO_SPECTRE_LINE')
        row['raw_sha256'] = raw_sha
        row['log_sha256'] = log_sha
        row['refusal'] = (refusal or '').replace(',', ';')[:180]
        row['launches_used_after'] = str(self.used)
        self.flush()
        return launched

    def write(self):
        self.flush()


# ------------------------------------------------------------------ task level launch account
class OverBudget(Exception):
    """the ceiling is reached before the process starts, so it can never be spent by the refusal"""


class Account(AppendCSV):
    """the task-level cumulative account of every Spectre process this task has asked for

    Three facts are kept apart, because collapsing them is what let the DATA-7B round overrun:
      * requested  -- a row was written before the process started;
      * confirmed  -- the returned text proves a simulator really ran (a SPECTRE line or the
        preflight's own `spectre_rc=`), which is the honest count of executed launches;
      * uncertain  -- a row left in REQUESTED by a crash or a lost connection. It is never counted as
        executed, and it still occupies the ceiling, because nobody can prove it did not start.
    The file is seeded from the delivered reconcile table, so a fresh checkout cannot reset the
    history to zero and a new run_id cannot start a fresh budget.
    """

    HDR = ['launch_id', 'task_id', 'run_id', 'case_id', 'role', 'state', 'requested_utc',
           'ended_utc', 'rc', 'launch_evidence', 'deck_sha256', 'pwl_sha256', 'raw_sha256',
           'log_sha256', 'refusal', 'ceiling', 'confirmed_after', 'occupied_after']
    PREFIX = 'A'

    def __init__(self, path, ceiling, seed):
        existed = os.path.isfile(path)
        AppendCSV.__init__(self, path)
        self.ceiling = ceiling
        self.seed_origin = seed['origin']
        if not existed:
            for row in seed['rows']:
                self.rows.append(row)
        else:
            have = set(r['launch_id'] for r in self.rows)
            want = set(r['launch_id'] for r in seed['rows'])
            if not want <= have:
                raise RuntimeError('%s lost %d seeded historical row(s); the account is not trusted'
                                   % (os.path.basename(path), len(want - have)))
        self.recover()
        self._restamp()
        self.flush()

    def recover(self):
        """a REQUESTED row with no outcome is an uncertain launch, not a free one"""
        for r in self.rows:
            if r['state'] == 'REQUESTED':
                r['state'] = 'UNCERTAIN'
                r['refusal'] = ('recovered: the process ended before this row could be settled; '
                                'it occupies the ceiling but is not claimed as executed'
                                )[:180].replace(',', ';')
                r['launch_evidence'] = 'NO_OUTCOME_AT_RECOVERY'

    def counts(self):
        conf = [r for r in self.rows if r['state'] in ('CONFIRMED', 'COMPLETED')]
        unc = [r for r in self.rows if r['state'] == 'UNCERTAIN']
        return {'requested': len(self.rows), 'confirmed': len(conf), 'uncertain': len(unc),
                'occupied': len(conf) + len(unc),
                'no_launch': len([r for r in self.rows if r['state'] == 'REFUSED_NO_LAUNCH'])}

    def remaining(self):
        return self.ceiling - self.counts()['occupied']

    def _restamp(self):
        """running totals, recomputed over the whole file, so no row can carry a friendlier number"""
        conf = occ = 0
        for r in self.rows:
            if r['state'] in ('CONFIRMED', 'COMPLETED'):
                conf += 1
                occ += 1
            elif r['state'] == 'UNCERTAIN':
                occ += 1
            r['ceiling'] = str(self.ceiling)
            r['confirmed_after'] = str(conf)
            r['occupied_after'] = str(occ)

    def reserve(self, case_id, role, deck_sha, pwl_sha, run_id):
        """write the row and charge the ceiling before the process is started"""
        c = self.counts()
        if c['occupied'] + 1 > self.ceiling:
            raise OverBudget('%s/%s needs a launch: %d confirmed + %d uncertain = %d occupied of a '
                             '%d ceiling (history seeded from %s)'
                             % (case_id, role, c['confirmed'], c['uncertain'], c['occupied'],
                                self.ceiling, self.seed_origin))
        row = {'launch_id': self._next_id(), 'task_id': TASK_ID, 'run_id': run_id,
               'case_id': case_id, 'role': role, 'state': 'REQUESTED',
               'requested_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'ended_utc': '', 'rc': '', 'launch_evidence': '', 'deck_sha256': deck_sha,
               'pwl_sha256': pwl_sha, 'raw_sha256': '', 'log_sha256': '', 'refusal': ''}
        self.rows.append(row)
        self._restamp()
        self.flush()
        return row

    def settle(self, row, rc, text, launched, evidence, raw_sha='', log_sha='', refusal=''):
        row['state'] = ('COMPLETED' if launched else 'REFUSED_NO_LAUNCH')
        row['ended_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        row['rc'] = str(rc)
        row['launch_evidence'] = (evidence or 'NO_LAUNCH_EVIDENCE').replace(',', ';')[:180]
        row['raw_sha256'] = raw_sha
        row['log_sha256'] = log_sha
        row['refusal'] = (refusal or '').replace(',', ';')[:180]
        self._restamp()
        self.flush()
        return launched

    def mark_uncertain(self, row, why):
        """contact was lost: the process may or may not have run, so the ceiling pays for it

        Turning an unproven launch into zero is how an overrun hides. The row keeps state UNCERTAIN,
        is never counted as executed, and is always counted against the ceiling.
        """
        row['state'] = 'UNCERTAIN'
        row['ended_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        row['launch_evidence'] = 'NO_OUTCOME_RECORD'
        row['refusal'] = why.replace(',', ';')[:180]
        self._restamp()
        self.flush()
        return row

    def note(self, case_id, role, run_id, detail, rc=''):
        """a fact that costs no launch at all (a reused measurement, a refused offline gate)"""
        now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        row = {'launch_id': self._next_id(), 'task_id': TASK_ID, 'run_id': run_id,
               'case_id': case_id, 'role': role, 'state': 'REFUSED_NO_LAUNCH',
               'requested_utc': now, 'ended_utc': now, 'rc': str(rc),
               'launch_evidence': 'NO_PROCESS_STARTED', 'deck_sha256': '', 'pwl_sha256': '',
               'raw_sha256': '', 'log_sha256': '', 'refusal': detail.replace(',', ';')[:180]}
        self.rows.append(row)
        self._restamp()
        self.flush()
        return row

    def flush_account(self):
        self._restamp()
        self.flush()


def launch_evidence_of(text):
    """(launched, evidence) from what the runner or the preflight actually printed"""
    m = re.search(r'^SPECTRE name=\S+ rc=\S+', text or '', re.M)
    if m:
        return 1, m.group(0).replace(' ', '_')
    if re.search(r'^spectre_rc=', text or '', re.M):
        return 1, 'PREFLIGHT_INNER_spectre_rc_seen'
    return 0, 'NO_SPECTRE_LINE'


def seed_account_rows(ev_dir):
    """the delivered reconcile table is the historical fact the ceiling is measured against"""
    path = os.path.join(ev_dir, 'launches_reconcile.csv')
    if not os.path.isfile(path):
        raise RuntimeError('%s is missing, so the historical launch count cannot be rebuilt' % path)
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = f.readline().strip().split(',')
        recs = [dict(zip(hdr, l.rstrip('\r\n').split(','))) for l in f if l.strip()]
    dirs = [r for r in recs if r['task_root_dir'] != 'TOTAL']
    total = [r for r in recs if r['task_root_dir'] == 'TOTAL']
    if len(total) != 1:
        raise RuntimeError('%s must carry exactly one TOTAL row' % path)
    per_dir = sum(int(r['processes_counted_against_ceiling']) for r in dirs)
    if per_dir != int(total[0]['processes_counted_against_ceiling']):
        raise RuntimeError('the reconcile rows sum to %d but TOTAL says %d'
                           % (per_dir, int(total[0]['processes_counted_against_ceiling'])))
    rows = []
    for r in dirs:
        n_pre = int(r['preflight_logs'])
        n_dut = int(r['dut_logs'])
        n_all = int(r['processes_counted_against_ceiling'])
        if n_pre + n_dut != n_all:
            raise RuntimeError('%s: %d preflight + %d dut logs do not sum to %d counted'
                               % (r['task_root_dir'], n_pre, n_dut, n_all))
        for i in range(n_pre):
            rows.append({'launch_id': 'H%03d' % (len(rows) + 1), 'task_id': TASK_ID,
                         'run_id': r['task_root_dir'], 'case_id': '(per-directory record)',
                         'role': 'preflight', 'state': 'CONFIRMED',
                         'requested_utc': '', 'ended_utc': '', 'rc': '',
                         'launch_evidence': 'reconcile_log_count',
                         'deck_sha256': '', 'pwl_sha256': '', 'raw_sha256': '', 'log_sha256': '',
                         'refusal': 'seeded from %s: %s' % (os.path.basename(path),
                                                            r['note'].replace(',', ';'))})
        for i in range(n_dut):
            rows.append({'launch_id': 'H%03d' % (len(rows) + 1), 'task_id': TASK_ID,
                         'run_id': r['task_root_dir'], 'case_id': '(per-directory record)',
                         'role': 'dut', 'state': 'CONFIRMED',
                         'requested_utc': '', 'ended_utc': '', 'rc': '',
                         'launch_evidence': 'reconcile_log_count',
                         'deck_sha256': '', 'pwl_sha256': '', 'raw_sha256': '', 'log_sha256': '',
                         'refusal': 'seeded from %s: %s' % (os.path.basename(path),
                                                            r['note'].replace(',', ';'))})
    return {'origin': '%s (TOTAL=%d, %d directory row(s))' % (path.replace(os.sep, '/'),
                                                              per_dir, len(dirs)),
            'rows': rows, 'confirmed': len(rows)}


def parse_runner(text):
    out = {}
    for key, pat in (('rc', r'^SPECTRE name=\S+ rc=(\S+)'),
                     ('datafile', r"^CHECK datafile='([^']*)'"),
                     ('logfile', r'^LOGFILE (\S+)'),
                     ('done', r"^CHECK done_line='([^']*)'"),
                     ('errors', r'^CHECK error_hits=(\S+)')):
        m = re.search(pat, text or '', re.M)
        out[key] = m.group(1) if m else ''
    return out


# ------------------------------------------------------------------ task root
def prepare(link, mst, scratch, log_dir):
    """create the task root and land the frozen tools and masters, each verified byte for byte"""
    rc, out = link.run('mkdir -p %s/scripts %s/spectre && echo MKDIR_OK && ls -d %s'
                       % (link.root, link.root, link.root), 120, 'mkdir')
    if rc != 0 or 'MKDIR_OK' not in out:
        raise RuntimeError('the task root could not be prepared (rc=%d): %s' % (rc, out[:200]))
    frozen = {}
    for rel in FROZEN_RUNNER:
        blob = git_blob(BASE_SHA, rel)
        name = os.path.basename(rel)
        local = os.path.join(scratch, 'runner', name)
        if not os.path.isdir(os.path.dirname(local)):
            os.makedirs(os.path.dirname(local))
        with io.open(local, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(blob))
        want = sha_txt(blob)
        link.push(local, '%s/scripts/%s' % (link.root, name), 'runner')
        link.run('chmod 755 %s/scripts/%s' % (link.root, name), 60, 'chmod')
        frozen[name] = want
    for m in mst:
        local = os.path.join(scratch, 'masters', m['name'])
        if not os.path.isdir(os.path.dirname(local)):
            os.makedirs(os.path.dirname(local))
        with io.open(local, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(m['text']))
        got = link.push(local, '%s/spectre/%s' % (link.root, m['name']), 'master')
        if got != m['sent_sha256']:
            raise RuntimeError('%s did not land byte-identical' % m['name'])
    return frozen


def stage_deck(case, deck, points, scratch):
    d = os.path.join(scratch, 'decks', case['case_id'])
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, '%s.scs' % case['case_id'])
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(deck))
    ppath = os.path.join(scratch, 'pwl', '%s_pwl.txt' % case['case_id'])
    if not os.path.isdir(os.path.dirname(ppath)):
        os.makedirs(os.path.dirname(ppath))
    with io.open(ppath, 'w', encoding='utf-8', newline='\n') as f:
        for t, v in points:
            f.write('%d %.6g\n' % (t, v))
    return path, ppath


def load_trace_docs(trace_dir, case, tr):
    """the trace document for a case, rebuilt from the VCD bytes still held on this machine"""
    path = os.path.join(trace_dir, 'trace_%s.json' % case['trace_case'])
    if not os.path.isfile(path):
        raise RuntimeError('trace document %s is missing' % path)
    doc = json.loads(u(io.open(path, encoding='utf-8').read()))
    vcd = os.path.join(os.path.dirname(trace_dir), 'trace_%s.vcd' % case['trace_case'])
    if os.path.isfile(vcd) and sha256_of(vcd) != doc['facts']['vcd_sha256']:
        raise RuntimeError('the VCD behind %s no longer matches its document' % case['case_id'])
    ids = case['windows'].split(';')
    return doc, ids


def sha256_of(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------------ gates that run first
def static_gates(cases, mst, docs, expect_rows=24):
    """every structural check that must close before the first launch"""
    problems = []
    ids = [c['case_id'] for c in cases]
    try:
        MS.validate_case_ids(ids, ids if len(ids) == 24 else ids[:24])
    except MS.Refuse as exc:
        problems.append('case table: %s' % exc)
    if len(ids) != expect_rows:
        problems.append('case table has %d rows, this pass expects %d' % (len(ids), expect_rows))
    for c in cases:
        if c['role'] == 'negative_wiring' and 'data_en' in c['note']:
            problems.append('%s: the negative case must not be described as a positive run' % c['case_id'])
    names = [m['name'] for m in mst]
    for need in ('dd1_d6_bias_core.scs', 'dd1_d6_sink_core.scs', 'dd1_d6_inv18.scs',
                 'dd1_d7b_pwm_stage.scs'):
        if need not in names:
            problems.append('missing master %s' % need)
    stage = [m for m in mst if m['name'] == 'dd1_d7b_pwm_stage.scs'][0]
    for stmt in ('Xbias (iref_in vss) data_bias_ref',
                 'Xinv (data_en data_en_b vdd18 vss) dd1_inv18',
                 'Xsink (data_en data_en_b iref_in vcas data_out vss) data_sink_1ch'):
        if stmt not in stage['text']:
            problems.append('the wrapper lost its instance line: %s' % stmt)
    dev = re.findall(r'^\s*M\w+\s*\(', stage['text'] + ''.join(m['text'] for m in mst), re.M)
    if len(dev) != 7:
        problems.append('expanded MOS count is %d, not 7' % len(dev))
    # the PWL of every normal case must start and end low, and its ramps must be inside the span
    for cid, doc in docs.items():
        for w in doc['windows']:
            pts = w['pwl_points']
            if pts[0][1] != 0.0 or pts[-1][1] != 0.0:
                problems.append('%s window %s: the enable does not begin and end at 0 V'
                                % (cid, w['window']))
            if pts[0][0] != 0:
                problems.append('%s window %s: the PWL does not start at t = 0' % (cid, w['window']))
    return problems


# ------------------------------------------------------------------ evidence
SHARD_LIMIT = 170 * 1024

CASE_HDR = ['run_id', 'launch_id', 'case_id', 'group', 'role', 'window', 'mode', 'code',
            'pam_request', 'tick_ns', 'full_intervals', 'expected_intervals', 'maxstep_ns',
            'ramp_ns', 'vclamp_v', 'deck_sha256', 'pwl_sha256', 'trace_sha256', 'raw_sha256',
            'log_sha256', 'section_read', 'temp_read', 't0_ns', 't1_ns', 'q_win_C', 'q_expected_C',
            'q_lsb_C', 'charge_error_LSB', 'charge_error_pC', 'gain_error_vs_15uA', 'q_positive_C',
            'q_negative_C', 'q_tail_C', 'window_peak_A', 'window_peak_t_ns', 'de_rise_50_ns',
            'de_fall_50_ns', 'de_b_fall_50_ns', 'de_fall_delay_ns', 'declared_pulses',
            'pulse_edges_missing', 'current_10pct_ns', 'current_90pct_ns', 'current_rise_10_90_ns',
            'settled_status', 'settled_ns', 'longest_in_band_ns', 'off_status', 'off_ns',
            'off_segment_start_ns', 'turn_off_delay_ns', 'last_100ns_max_abs_A',
            'probe_direction_suspect', 'reused_from_native_run', 'src_launch_id',
            'measurement_source_sha256', 'verdict', 'reasons']

EDGE_HDR = ['run_id', 'case_id', 'window', 'quantity', 't_ns', 'data_en_V', 'data_en_b_V',
            'vbias_ch_V', 'node_m_V', 'iref_in_V', 'iout_A']


def write_rows(path, rows, hdr):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(','.join(hdr) + '\n')
        for r in rows:
            f.write(','.join('' if c is None else str(c) for c in r) + '\n')


def shard_samples(rows, hdr, base, out_dir, max_bytes=168 * 1024):
    """full-resolution slices that stay under the repository blob limit

    The rows are wide (a 17-significant-digit time plus two display columns), so the split is decided
    by measured bytes, not by a guessed row count: the first row is written and its length tells how
    many fit, and a shard is closed before it can cross the limit.
    """
    if not rows:
        raise RuntimeError('%s has no samples to deliver' % base)
    series = sha_txt(''.join(','.join(str(c) for c in r) + '\n' for r in rows))
    parts = []
    idx = 0
    i = 0
    while i < len(rows):
        idx += 1
        name = '%s.%04d.csv' % (base, idx)
        path = os.path.join(out_dir, name)
        head = ','.join(hdr) + '\n'
        est = max(len(','.join(str(c) for c in rows[i])) + 1, 1)
        budget = max((max_bytes - len(head)) // est, 50)
        chunk = rows[i:i + budget]
        write_rows(path, chunk, hdr)
        size = os.path.getsize(path)
        while size >= max_bytes and len(chunk) > 50:
            chunk = chunk[:-max(1, len(chunk) // 8)]
            write_rows(path, chunk, hdr)
            size = os.path.getsize(path)
        if size >= max_bytes:
            raise RuntimeError('%s is %d bytes with %d rows, over the 180 KiB limit'
                               % (name, size, len(chunk)))
        parts.append({'part': name, 'rows': len(chunk), 'bytes': size, 'first_row': 1 + i,
                      'last_row': i + len(chunk), 'sha256': sha_file(path)})
        i += len(chunk)
    return {'base': base, 'header': ','.join(hdr), 'total_rows': len(rows),
            'series_sha256': series, 'parts': parts}


def fmt_num(v, scale, digits='%.10g'):
    if v is None or isinstance(v, str):
        return ''
    return digits % (float(v) * scale)


def temp_and_section(link, log_text):
    tsec = re.search(r'^"temp"\s+([0-9.eE+-]+)', log_text or '', re.M)
    return tsec.group(1) if tsec else ''


# ------------------------------------------------------------------ the main flow
def build_all(cases, mst, trace_dir, out_root, run_id):
    docs = {}
    decks = {}
    for c in cases:
        if c['role'] == 'calibration':
            continue
        path = os.path.join(trace_dir, 'trace_%s.json' % c['trace_case'])
        doc = json.loads(u(io.open(path, encoding='utf-8').read()))
        docs[c['case_id']] = doc
    for c in cases:
        if c['role'] == 'calibration':
            points = CAL_PWL + [(CAL_PWL[-1][0] + STOP_MARGIN_NS * 1000, 0.0)]
            doc = None
        else:
            doc = docs[c['case_id']]
            points = combined_pwl(doc, c['windows'].split(';'), SHIFT_NS * 1000,
                                  int(c['ramp_ns']) * 1000)
            doc['_points'] = points
        deck, _pts, stop_ps = build_deck(c, points, mst, note=run_id)
        decks[c['case_id']] = {'deck': deck, 'points': points, 'stop_ps': stop_ps,
                               'deck_sha256': sha_txt(deck), 'pwl_sha256':
                               sha_txt('\n'.join('%d %.6g' % (t, v) for t, v in points))}
    return docs, decks


# ------------------------------------------------------------------ reading the run back
def psf_series(path):
    """(columns, times_ps) from one psfascii file, with the frozen parser and integer ps times"""
    groups, axis = RD.parse(path)
    cols, times = RD.as_columns(groups, axis)
    if times is None:
        raise RuntimeError('%s has no %s axis' % (path, axis))
    out = {}
    # the bound must come from the printed tokens, not from a Python repr of the parsed float:
    # this build writes 16 significant digits ('1.493190564271745e-05'), while repr() would shorten
    # the same value and invent a much coarser grid than the data really has.
    txt = u(io.open(path, encoding='utf-8', errors='replace').read())
    axis_tokens = re.findall(r'^"%s"\s+([-+0-9.][-+0-9.eE]*)' % re.escape(axis), txt, re.M)
    if len(axis_tokens) != len(times):
        raise RuntimeError('%s: %d printed axis tokens against %d parsed samples'
                           % (path, len(axis_tokens), len(times)))
    bound = MS.time_quantum_ps(axis_tokens)
    for name, vals in cols.items():
        series, _q = MS.float_samples([str(t) for t in times], [str(v) for v in vals], name)
        out[name] = series
    out['_time_quantum_ps'] = bound
    return out, [t for t, _v in out.get(axis, [])]


def readback_env(log_text, raw_text):
    sec = re.search(r'section=(\w+)', log_text or '')
    tsec = re.search(r'^"temp"\s+([0-9.eE+-]+)', raw_text or '', re.M)
    tlog = re.search(r'temp\s*=\s*([0-9.eE+-]+)', log_text or '')
    return {'section_in_log': sec.group(1) if sec else '',
            'temp_log_C': tlog.group(1) if tlog else '',
            'temp_header_C': tsec.group(1) if tsec else ''}


def window_axis(series, name, t0_ps, t1_ps):
    """the named trace clipped to a window with room on both sides for its crossings"""
    s = series.get(name)
    if not s:
        # the wiring-fault deck never connects the bench enable, so its data_en node does not exist
        # in the results. The declared stimulus for that window is flat zero (a black code), and the
        # row says so; nothing is invented from the faulted run itself.
        flat = series.get('time') or series.get('Ip_out:i')
        if not flat:
            raise RuntimeError('trace %s is missing and the run has no time axis to fall back on'
                               % name)
        return [(t, 0.0) for t, _v in flat]
    lo = t0_ps - EDGE_SEARCH_NS * NS
    hi = t1_ps + (TAIL_NS + EDGE_SEARCH_NS) * NS
    return [(t, v) for t, v in s if lo <= t <= hi]


def measure_one(c, w, series, ical, launch_id, ids, run_id):
    """the 6.2 quantities for one window of one run, with the delivered samples sliced for re-use"""
    tick_ps = int(w['tick_ns']) * NS
    t0 = int(w['t0_ps']) + SHIFT_NS * NS
    t1 = int(w['t1_ps']) + SHIFT_NS * NS
    cur = window_axis(series, 'Ip_out:i', t0, t1)
    den = window_axis(series, 'data_en', t0, t1)
    deb = [(t, v) for t, v in series.get('Xstage.data_en_b', [])]
    # the pulse this window is supposed to conduct comes from the accepted RTL trace, shifted exactly
    # like the PWL was: an edge is searched at the pulse, never at the end of the window
    segs = [[int(s[0]) + SHIFT_NS * NS, int(s[1]) + SHIFT_NS * NS]
            for s in (w.get('segments_ps') or [])]
    win = {'current': cur, 'de': den, 'de_b': deb, 't0_ps': t0, 't1_ps': t1,
           'de_declared_flat_zero': (series.get('data_en') is None),
           'pulse_segments_ps': segs,
           'expected_intervals': float(w['expected_intervals'])}
    out = MS.measure_window(win, ical, tick_ps, tail_ns=TAIL_NS,
                            ctx='%s/%s' % (c['case_id'], w['window']))
    out['analog_t0_ps'] = t0
    out['analog_t1_ps'] = t1
    if c['role'] == 'negative_wiring':
        out['de_and_de_b_edge_gap_ps'] = None
    return out


def selftest_main():
    """offline gates and named break tests; nothing here starts a simulator"""
    bad = []
    n = 0
    cases = load_cases(os.path.join(PROJ, 'tests', 'dd1_d7b', 'cases.csv'))
    mst = masters()
    # 1 the four masters strip only direction comments, and their electrical text is unchanged
    n += 1
    try:
        if not mst or any(m['bytes_sent'] >= m['bytes_repo'] for m in mst):
            bad.append('masters did not shrink by exactly the stripped lines')
    except RuntimeError as exc:
        bad.append('master normalisation refused: %s' % exc)
    # 2 the wrapper expands to exactly seven MOS with the frozen master mix
    n += 1
    text = ''.join(m['text'] for m in mst)
    mix = {}
    for line in text.split('\n'):
        m = re.match(r'^\s*M\w+\s*\([^)]*\)\s*(\w+)', line)
        if m:
            mix[m.group(1)] = mix.get(m.group(1), 0) + 1
    if mix != {'n33': 4, 'n33_dnw_4t_ckt': 1, 'n18': 1, 'p18': 1}:
        bad.append('master mix %r is not the frozen 7-device mix' % (mix,))
    # 3 deck build is deterministic and every deck carries the supply contract ports
    n += 1
    doc = selftest_doc('D7B-P30-C001')
    c = [x for x in cases if x['case_id'] == 'D7B-P30-C001'][0]
    pts = combined_pwl(doc, ['normal'], SHIFT_NS * 1000, int(c['ramp_ns']) * 1000)
    d1, p1, s1 = build_deck(c, pts, mst)
    d2, p2, s2 = build_deck(c, pts, mst)
    if d1 != d2 or s1 != s2:
        bad.append('the deck builder is not deterministic')
    for need in ('dd1_d7b_pwm_stage', 'Ip_out (clamp data_out) iprobe', 'method=gear2only',
                 'section=tt', 'options temp=27', 'Vss (vss 0) vsource dc=0'):
        if need not in d1:
            bad.append('the deck lost %r' % need)
    # break test 1: shift a PWL fall edge by one tick and the golden check must refuse
    n += 1
    shifted = [(t, v) for t, v in doc['facts']['data_en_edges']]
    for i in range(len(shifted) - 1, -1, -1):
        if shifted[i][1] == 0 and shifted[i][0] > doc['windows'][0]['t0_ps']:
            shifted[i] = (shifted[i][0] + 30000, 0)
            break
    segs = TR.segments_of(shifted, doc['windows'][0]['t0_ps'], doc['windows'][0]['t1_ps'])
    if sum(s[2] for s in segs) == doc['windows'][0]['conducted_ps']:
        bad.append('a fall edge moved by one tick did not change the conducted width')
    # break test 2: the ammeter reversed is caught by the measurement core, not honoured
    n += 1
    cur = [[0, -15e-6], [30000, -15e-6], [31000, 0.0], [230000, 0.0]]
    out = MS.measure_window({'current': [(int(t), v) for t, v in cur],
                             'de': [(0, 0.0), (500, 1.8), (29500, 1.8), (30000, 0.0)],
                             't0_ps': 0, 't1_ps': 30000, 'expected_intervals': 1.0,
                             'pulse_segments_ps': [[0, 30000]]},
                            15e-6, 30000, ctx='break2')
    if not out['probe_direction_suspect'] or MS.judge(out)[0] != 'FAIL':
        bad.append('a flipped ammeter was not caught')
    # break test 3: an integration range whose tail was never delivered must refuse
    n += 1
    try:
        MS.integrate([(0, 1.0), (1000, 1.0)], 0, 480000, 'break3')
        bad.append('a truncated integration range was accepted')
    except MS.Refuse:
        pass
    # break test 4: a duplicated or missing case key must refuse
    n += 1
    for args in ((['A', 'A'], ['A']), (['A'], ['A', 'B'])):
        try:
            MS.validate_case_ids(args[0], args[1])
            bad.append('the case table defect %r was accepted' % (args,))
        except MS.Refuse:
            pass
    # 6 the negative deck differs from its positive twin by exactly one instance line
    n += 1
    pos = [x for x in cases if x['case_id'] == 'D7B-P30-C000'][0]
    neg = [x for x in cases if x['role'] == 'negative_wiring'][0]
    pts0 = combined_pwl(doc, ['normal'], SHIFT_NS * 1000, 2000)
    dp, _, _ = build_deck(pos, pts0, mst)
    dn, _, _ = build_deck(neg, pts0, mst)
    dp_lines = [l for l in dp.split('\n') if l.startswith('Xstage')]
    dn_lines = [l for l in dn.split('\n') if l.startswith('Xstage')]
    if len(dp_lines) != 1 or len(dn_lines) != 1:
        bad.append('the stage instance line is not unique in one of the decks')
    elif dn_lines[0] != 'Xstage (vdd18 iref_in vcas data_out vdd18 vss) dd1_d7b_pwm_stage':
        bad.append('the wiring fault is not the single enable net: %r' % (dn_lines,))
    if 'Vde (data_en 0) vsource' in dn:
        bad.append('the negative deck still drives the enable from the PWL node')
    # 7 the supply-negative deck really loses its VSS source
    n += 1
    n2 = dp.replace('Vss (vss 0) vsource dc=0\n', '')
    if 'Vss (vss 0)' in n2 or n2.count('vsource') != dp.count('vsource') - 1:
        bad.append('the static negative deck is not a single-statement removal')
    # 8 the mode list is closed, and the native entry is refused before any preparation
    n += 1
    import optparse
    for argv, want in (([], []), (['--dry'], ['dry']), (['--run'], ['run']),
                       (['--run', '--dry'], ['dry', 'run']),
                       (['--check-evidence', 'x'], ['check_evidence'])):
        ap = optparse.OptionParser()
        for flag in ('--selftest', '--dry', '--run', '--supply-negative', '--static-probe',
                     '--remeasure', '--account'):
            ap.add_option(flag, action='store_true')
        ap.add_option('--check-evidence', default='')
        ap.add_option('--write-manifest', default='')
        got = chosen_modes(ap.parse_args(argv)[0])
        if got != want:
            bad.append('the mode table read %r from %r, expected %r' % (got, argv, want))
    if authorisation_problem() and os.environ.get('RUN') == '1':
        bad.append('the authorisation gate reports a problem it should not')
    # 9 an append-only account: reopening keeps the count, a lost row is refused, and an abandoned
    #   launch occupies the ceiling instead of being quietly written off
    n += 1
    import tempfile
    temp = tempfile.mkdtemp(prefix='d7b-run-selftest-')
    try:
        path = os.path.join(temp, 'ledger.csv')
        first = Ledger(path)
        row = first.begin('SYN', 'dut', 'deck', 'pwl')
        first.finish(row, 0, 'SPECTRE name=x.scs rc=0', launched=1)
        if Ledger(path).used != 1 or not any(r['case_id'] == 'SYN' for r in Ledger(path).rows):
            bad.append('reopening the ledger lost its count or its history')
        acct = Account(os.path.join(temp, 'account.csv'), 2,
                       {'origin': 'selftest', 'rows': []})
        live = acct.reserve('SYN', 'preflight', 'd', 'p', 'r_selftest')
        acct.settle(live, 0, 'spectre_rc=0', *launch_evidence_of('spectre_rc=0'))
        second = acct.reserve('SYN', 'dut', 'd', 'p', 'r_selftest')
        acct.settle(second, 0, 'SPECTRE name=x.scs rc=0', *launch_evidence_of(
            'SPECTRE name=x.scs rc=0'))
        try:
            acct.reserve('SYN', 'dut', 'd', 'p', 'r_selftest_third')
            bad.append('the ceiling stayed open after 2 of 2 launches')
        except OverBudget:
            pass
        abandoned = Account(os.path.join(temp, 'crash.csv'), 1, {'origin': 'selftest', 'rows': []})
        abandoned.reserve('SYN', 'dut', 'd', 'p', 'r_crash')
        recovered = Account(os.path.join(temp, 'crash.csv'), 1, {'origin': 'selftest', 'rows': []})
        c = recovered.counts()
        if c['uncertain'] != 1 or c['occupied'] != 1 or c['confirmed'] != 0:
            bad.append('an abandoned launch recovered as %r' % c)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    print('D7B_RUN_SELFTEST: %s (%d checks)' % ('FAIL' if bad else 'PASS', n))
    for b in bad:
        print('SELFTEST_BAD %s' % b)
    return 1 if bad else 0


def selftest_doc(cid, ev_dir=HISTORICAL_EVIDENCE):
    """a trace document rebuilt from the delivered bundle's own committed bytes

    The delivered self test read `review/scratch/traceout/trace_<case>.json`, which is generated and
    never committed, so a fresh checkout could not run it at all (the review reported exactly that
    FileNotFoundError). The edges and the window bounds of this case are inside the frozen bundle, so
    the fixture is re-derived from them instead: same geometry, committed bytes, no skip-with-rc-0.
    """
    if not os.path.isdir(ev_dir):
        raise RuntimeError('the self test fixture needs the delivered bundle at %s' % ev_dir)
    edges = []
    for r in read_csv_rows(os.path.join(ev_dir, 'pwl_edges_%s.csv' % cid)):
        edges.append((int(r['t_ps']), int(float(r['level']))))
    edges = sorted(set(edges))
    if not edges:
        raise RuntimeError('the delivered bundle carries no PWL edges for %s' % cid)
    rows = [r for r in read_csv_rows(os.path.join(ev_dir, 'cases.csv')) if r['case_id'] == cid]
    if not rows:
        raise RuntimeError('the delivered case table has no %s row' % cid)
    windows = []
    for r in rows:
        t0 = int(float(r['t0_ns']) * 1000) - SHIFT_NS * NS
        t1 = int(float(r['t1_ns']) * 1000) - SHIFT_NS * NS
        windows.append(synth_window_from(r, t0, t1, edges))
    segs = TR.segments_of(edges, windows[0]['t0_ps'], windows[0]['t1_ps'])
    windows[0]['segments_ps'] = [[s[0], s[1]] for s in segs]
    windows[0]['conducted_ps'] = sum(s[2] for s in segs)
    return {'case_id': cid, 'shift_ps': SHIFT_NS * NS, 'windows': windows,
            'facts': {'data_en_edges': edges, 'vcd_sha256': rows[0]['trace_sha256'],
                      'vcd': 'derived from %s' % os.path.basename(ev_dir), 'header': 0,
                      'end_ps': max(t for t, _v in edges), 'tick_lead_ps': 5, 'tick_count': 1}}


def synth_window_from(r, t0, t1, edges):
    tick = int(float(r['tick_ns'])) * NS
    segments = [[s[0], s[1]] for s in TR.segments_of(edges, t0, t1)]
    stop = t1 + TAIL_NS * NS
    pts, _cur = TR.build_pwl(TR.window_edges(edges, t0, stop), t0, stop, SHIFT_NS * NS,
                             int(float(r['ramp_ns'])) * NS)
    return {'window': r['window'], 'seq': 1, 'role': r['role'], 'mode': r['mode'],
            'code': r['code'], 'pam_request': r['pam_request'], 'tick_ns': r['tick_ns'],
            'window_ns': str((t1 - t0) // NS), 'full_intervals': r['full_intervals'],
            'expected_intervals': r['expected_intervals'], 'expected_conducting_ns': '',
            'expected_pulses': str(len(segments)), 't0_ps': t0, 't1_ps': t1,
            'accepted_ticks_in_window': str(len(segments)), 'expected_accepted_ticks': '',
            'first_tick_ps': t0, 'tick_lead_ps': 5, 'segments_ps': segments,
            'conducted_ps': sum(s[1] - s[0] for s in segments), 't_stop_ps': stop,
            'pwl_points': pts,
            'pwl_sha256': sha_txt('\n'.join('%d %.6g' % (t, v) for t, v in pts))}


def chosen_modes(opts):
    """the mode list is closed: none of them, or more than one, is a refusal rather than a default"""
    table = [('selftest', opts.selftest), ('dry', opts.dry), ('run', opts.run),
             ('supply_negative', opts.supply_negative),
             ('check_evidence', bool(opts.check_evidence)), ('static_probe', opts.static_probe),
             ('write_manifest', bool(opts.write_manifest)), ('remeasure', opts.remeasure),
             ('account', opts.account)]
    return [name for name, on in table if on]


def authorisation_problem():
    bad = [k for k in AUTH_VARS if os.environ.get(k) != '1']
    if bad:
        return ('RUN=1 AND QODER_SIM_AUTHORISED=1 are both required before any remote preparation; '
                'unset or not 1: %s' % ', '.join(bad))
    return ''


def run_id_taken(run_id, out_root):
    return (os.path.exists(os.path.join(PROJ, 'results', 'evidence', PUBLISHED_PREFIX + run_id))
            or os.path.exists(os.path.join(out_root, 'evidence', run_id)))


def make_run_id(opts, out_root):
    """a real unique id, and an existing directory is a refusal -- never an overwrite

    The delivered default was `r%%Y%%m%%d_%%H%%M%%S`, which kept literal percent signs and so was the
    same string on every call: two passes could not be told apart and the second could reach the first.
    """
    if opts.run_id:
        if not RUN_ID_RE.match(opts.run_id):
            raise RuntimeError('--run-id %r is not rYYYYMMDD_HHMMSS_xxxxxx' % opts.run_id)
        if run_id_taken(opts.run_id, out_root):
            raise RuntimeError('run id %s already has an evidence directory; nothing is overwritten'
                               % opts.run_id)
        return opts.run_id
    for _ in range(12):
        cand = 'r%s_%s' % (time.strftime('%Y%m%d_%H%M%S', time.gmtime()),
                           hashlib.sha256(os.urandom(32)).hexdigest()[:6])
        if not run_id_taken(cand, out_root):
            return cand
    raise RuntimeError('no unique run id could be made in twelve attempts')


def account_report(account):
    c = account.counts()
    roles = {}
    for r in account.rows:
        roles[r['role']] = roles.get(r['role'], 0) + 1
    print('ACCOUNT_FILE %s' % account.path)
    print('ACCOUNT_SEEDED_FROM %s' % account.seed_origin)
    print('ACCOUNT_ROWS %d roles=%s' % (len(account.rows),
                                        ' '.join('%s=%d' % kv for kv in sorted(roles.items()))))
    print('ACCOUNT_CONFIRMED %d UNCERTAIN %d OCCUPIED %d CEILING %d REMAINING %d'
          % (c['confirmed'], c['uncertain'], c['occupied'], account.ceiling,
             account.remaining()))
    print('ACCOUNT_NO_LAUNCH_ROWS %d' % c['no_launch'])
    if c['occupied'] > account.ceiling:
        print('HISTORICAL_BUDGET_STATUS VIOLATED_BY_%d_NOT_RETROACTIVELY_AUTHORISED'
              % (c['occupied'] - account.ceiling))
        return 1
    return 0


def main(argv):
    ap = optparse.OptionParser(usage='%prog MODE [options]\n'
                                     '  MODE is exactly one of --selftest --dry --run '
                                     '--supply-negative --static-probe --remeasure '
                                     '--check-evidence=DIR --write-manifest=DIR --account\n'
                                     '  native modes (--run --static-probe --supply-negative) need '
                                     'RUN=1 and QODER_SIM_AUTHORISED=1 and launch only inside the '
                                     'task launch ceiling')
    ap.add_option('--selftest', action='store_true')
    ap.add_option('--dry', action='store_true')
    ap.add_option('--run', action='store_true')
    ap.add_option('--supply-negative', action='store_true')
    ap.add_option('--check-evidence', default='')
    ap.add_option('--publish', action='store_true')
    ap.add_option('--static-probe', action='store_true')
    ap.add_option('--remeasure', action='store_true')
    ap.add_option('--account', action='store_true')
    ap.add_option('--only', default='')
    ap.add_option('--cal-from', default='')
    ap.add_option('--n2-from', default='')
    ap.add_option('--rtl-verify', default='')
    ap.add_option('--gate-records', default='')
    ap.add_option('--reuse', default='')
    ap.add_option('--write-manifest', default='')
    ap.add_option('--expect', type='int', default=24)
    ap.add_option('--run-id', default='')
    ap.add_option('--trace-dir', default=os.path.join(PROJ, 'review', 'scratch', 'traceout'))
    ap.add_option('--out', default=os.path.join(PROJ, 'review', 'scratch', 'd7b_stage'))
    ap.add_option('--account-file', default=ACCOUNT_PATH)
    ap.add_option('--seed-from', default=HISTORICAL_EVIDENCE)
    ap.add_option('--published-dir', default=HISTORICAL_EVIDENCE)
    opts, _args = ap.parse_args(argv)
    modes = chosen_modes(opts)
    if not modes:
        ap.print_usage()
        print('D7B_REFUSED no mode was named; nothing was prepared and no process was started')
        return 5
    if len(modes) > 1:
        print('D7B_REFUSED modes %s conflict: name exactly one' % ','.join(modes))
        return 5
    mode = modes[0]
    if opts.publish and mode not in ('run', 'remeasure'):
        print('D7B_REFUSED --publish only follows --run or --remeasure')
        return 5
    if opts.cal_from:
        print('D7B_REFUSED --cal-from is removed: a calibration copied out of another bundle\'s '
              'table is a number without bytes. Reuse the calibration case itself '
              '(--reuse D7B-CAL=<stage dir>) so Ical is recomputed from the retained psf, log and '
              'deck that produced it')
        return 5
    if opts.write_manifest:
        return write_manifest_main(opts.write_manifest)
    if mode == 'selftest':
        return selftest_main()
    if mode == 'check_evidence':
        import dd1_d7b_evidence_check as EC
        return EC.main_dir(opts.check_evidence)
    if mode == 'account':
        return account_report(Account(opts.account_file, LAUNCH_BUDGET,
                                      seed_account_rows(opts.seed_from)))
    cases = load_cases(os.path.join(PROJ, 'tests', 'dd1_d7b', 'cases.csv'))
    table_rows = len(cases)
    if opts.only:
        keep = [x.strip() for x in opts.only.split(',') if x.strip()]
        cases = [c for c in cases if c['case_id'] in keep]
        if len(cases) != len(keep):
            print('D7B_REFUSED --only names %d known case(s), asked for %s'
                  % (len(cases), ', '.join(sorted(keep))))
            return 5
    if table_rows != opts.expect:
        print('D7B_REFUSED case table has %d rows, --expect says %d' % (table_rows, opts.expect))
        return 5
    # the native entry is refused here, before the masters are read and long before a task root is
    # prepared: no mode argument and no authorisation may not fall through to the simulator
    account = None
    if mode in NATIVE_MODES or mode == 'remeasure':
        account = Account(opts.account_file, LAUNCH_BUDGET, seed_account_rows(opts.seed_from))
        c = account.counts()
        print('LAUNCH_ACCOUNT confirmed=%d uncertain=%d occupied=%d ceiling=%d remaining=%d'
              % (c['confirmed'], c['uncertain'], c['occupied'], account.ceiling,
                 account.remaining()))
    if mode in NATIVE_MODES:
        problem = authorisation_problem()
        if problem:
            print('D7B_REFUSED %s' % problem)
            return 5
        if c['occupied'] > account.ceiling:
            print('D7B_REFUSED %s: the task already shows %d occupied launches against a ceiling of '
                  '%d (seeded from %s). This repair round authorises 0 new launches; producing '
                  'evidence here needs a user decision about the historical overrun, not a process.'
                  % (OVERBUDGET_REFUSAL, c['occupied'], account.ceiling, account.seed_origin))
            print('NO_PROCESS_WAS_STARTED')
            return 5
        if mode == 'run':
            need = plan_launches(cases, resolve_reuse_count(opts.reuse))
            if need > account.remaining():
                print('D7B_REFUSED %s: the plan needs %d launches, %d of %d remain'
                      % (OVERBUDGET_REFUSAL, need, account.remaining(), account.ceiling))
                print('NO_PROCESS_WAS_STARTED')
                return 5
    if 2 * len(cases) > LAUNCH_BUDGET:
        print('D7B_REFUSED the plan needs %d launches, the ceiling is %d'
              % (2 * len(cases), LAUNCH_BUDGET))
        return 5
    mst = masters()
    out_root = os.path.abspath(opts.out)
    run_id = make_run_id(opts, out_root)
    if not os.path.isdir(out_root):
        os.makedirs(out_root)
    log_dir = os.path.join(out_root, 'transcripts')
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    docs = {}
    for c in cases:
        if c['role'] == 'calibration':
            continue
        path = os.path.join(opts.trace_dir, 'trace_%s.json' % c['trace_case'])
        docs[c['case_id']] = json.loads(u(io.open(path, encoding='utf-8').read()))
    problems = static_gates(cases, mst, docs, expect_rows=len(cases))
    if problems:
        for p in problems:
            print('STATIC_GATE_FAIL %s' % p)
        print('D7B_REFUSED static gates: %d problem(s); no simulator was started' % len(problems))
        return 5
    print('STATIC_GATES: PASS (%d cases, %d masters, 7 devices, %d launched processes of a %d '
          'ceiling)' % (len(cases), len(mst), 2 * len(cases), LAUNCH_BUDGET))
    _d, decks = build_all(cases, mst, opts.trace_dir, out_root, run_id)
    for cid in sorted(decks):
        stage_deck({'case_id': cid}, decks[cid]['deck'], decks[cid]['points'], out_root)
    print('DECKS_BUILT %d decks in %s' % (len(decks), os.path.join(out_root, 'decks')))
    for cid in sorted(decks):
        print('  %s deck=%s stop_ns=%.1f pwl_points=%d'
              % (cid, decks[cid]['deck_sha256'][:12], decks[cid]['stop_ps'] / 1000.0,
                 len(decks[cid]['points'])))
    if mode == 'dry':
        print('D7B_DRY: PASS (decks and gates only, 0 Spectre launches, 0 remote calls)')
        return 0
    if mode == 'supply_negative':
        return supply_negative(mst, decks, run_id, out_root, log_dir, account)
    if mode == 'static_probe':
        return static_probe(cases, mst, decks, run_id, out_root, log_dir, account)
    try:
        if mode == 'remeasure':
            res = remeasure_run(cases, mst, docs, decks, opts, run_id, out_root, account)
        else:
            res = native_run(cases, mst, docs, decks, opts, run_id, out_root, log_dir, account)
    except RuntimeError as exc:
        # a refusal raised while staging is still a refusal: it must not reach the caller as a
        # traceback, and the half-staged bundle stays in ignored scratch
        print('D7B_REFUSED %s' % exc)
        return 5
    rows = res['rows']
    verdicts = {}
    for r in rows:
        v = r[CASE_HDR.index('verdict')]
        verdicts[v] = verdicts.get(v, 0) + 1
    c = res['account'].counts()
    print('RUN_ID %s' % res['run_id'])
    print('LEDGER_LAUNCHES_THIS_PASS %d' % res['ledger'].used)
    print('LAUNCH_ACCOUNT confirmed=%d uncertain=%d occupied=%d ceiling=%d'
          % (c['confirmed'], c['uncertain'], c['occupied'], res['account'].ceiling))
    print('EVIDENCE_ROWS %d %s' % (len(rows), ' '.join('%s=%d' % kv for kv in
                                                       sorted(verdicts.items()))))
    elec = [r for r in rows if r[CASE_HDR.index('role')] in
            ('normal', 'safety', 'convergence', 'sensitivity')]
    fails = [r for r in elec if r[CASE_HDR.index('verdict')] == 'FAIL']
    print('PWM_CURRENT_FEASIBILITY_TT %s'
          % ('REWORK_REQUIRED' if fails else ('PASS' if elec else 'NOT_VERIFIED')))
    print('EVIDENCE_STATUS %s' % ('STAGED' if not res['stopped'] else 'PARTIAL'))
    if res['stopped']:
        print('STOPPED %s' % res['stopped'])
    if opts.publish:
        try:
            write_manifest_main(res['ev_dir'])
            print('PUBLISHED %s' % publish(res['ev_dir'], res['run_id']))
        except RuntimeError as exc:
            print('PUBLISH_REFUSED %s' % exc)
            return 6
    else:
        print('PUBLISHED no (--publish was not given; the bundle stays in ignored scratch)')
    return 0


def resolve_reuse_count(spec):
    """how many cases the reuse claim covers, without verifying the bytes twice"""
    return dict((p.split('=', 1)[0], True) for p in [x for x in (spec or '').split(',') if x.strip()])


def supply_negative(mst, decks, run_id, out_root, log_dir, account):
    """N2 on the guest: the deck loses its VSS source and the frozen checker must refuse it"""
    root = '%s/neg_%s' % (GUEST_ROOT, run_id)
    link = Link(GUEST_HOST, root, log_dir)
    ledger = Ledger(os.path.join(out_root, 'negative_ledger_%s.csv' % run_id))
    prepare(link, mst, out_root, log_dir)
    n2 = build_static_negative(mst, decks, out_root, run_id)
    row = run_static_negative(link, ledger, n2, run_id, mst, out_root, account)
    print('N2 %s' % row['verdict'])
    print('N2_LAUNCHES %d' % row['spectre_launches'])
    return 0 if row['detected'] == 'YES' and row['spectre_launches'] == 0 else 1

# ------------------------------------------------------------------ calibration and evidence
def calibrate(series, run_id, ids):
    """6.1: the calibration current, its band, the OFF baseline and the end-of-conduction sample"""
    cur = series['Ip_out:i']
    band = [(t, v) for t, v in cur if CAL_BAND[0] <= t <= CAL_BAND[1]]
    if len(band) < 2:
        raise RuntimeError('the calibration window has %d samples' % len(band))
    q = MS.trapezoid(band)
    dt = (band[-1][0] - band[0][0]) * MS.S_PER_PS
    ical = q / dt if dt else None
    bmin = min(v for _t, v in band)
    bmax = max(v for _t, v in band)
    off = [(t, v) for t, v in cur if CAL_OFF[0] <= t <= CAL_OFF[1]]
    tail = [(t, v) for t, v in cur if CAL_TAIL[0] <= t <= CAL_TAIL[1]]
    off_max = max(abs(v) for _t, v in off) if off else None
    tail_max = max(abs(v) for _t, v in tail) if tail else None
    rows = [{'run_id': run_id, 'quantity': 'Ical_A', 'value': ical,
             'window_ns': '%.1f..%.1f' % (CAL_BAND[0] / 1000.0, CAL_BAND[1] / 1000.0),
             'band_min_A': bmin, 'band_max_A': bmax, 'band_samples': len(band),
             'integration_s': dt},
            {'run_id': run_id, 'quantity': 'OFF_baseline_max_abs_A', 'value': off_max,
             'window_ns': '%.1f..%.1f' % (CAL_OFF[0] / 1000.0, CAL_OFF[1] / 1000.0)},
            {'run_id': run_id, 'quantity': 'CAL_tail_max_abs_A', 'value': tail_max,
             'window_ns': '%.1f..%.1f' % (CAL_TAIL[0] / 1000.0, CAL_TAIL[1] / 1000.0)}]
    tol = abs(15e-6) * 0.05
    ok = (ical is not None and abs(ical - 15e-6) <= tol and off_max is not None
          and off_max <= 0.15e-6 and tail_max is not None and tail_max <= 0.15e-6)
    reason = []
    if ical is None or abs(ical - 15e-6) > tol:
        reason.append('Ical %r is outside 15 uA +/- 5 %%' % ical)
    if off_max is None or off_max > 0.15e-6:
        reason.append('the OFF baseline max |I| is %r' % off_max)
    if tail_max is None or tail_max > 0.15e-6:
        reason.append('the end-of-conduction max |I| is %r' % tail_max)
    return {'ical_A': ical, 'band_min_A': bmin, 'band_max_A': bmax, 'off_max_abs_A': off_max,
            'tail_max_abs_A': tail_max, 'ok': ok, 'reasons': reason, 'rows': rows, 'ids': ids}


# The full native series is tens of millions of digits, so the shards carry only what no other byte
# in the bundle states: the sample time and the sampled current. The part -> case/deck/raw/run
# binding lives in charge_index.csv, whose series digest is compared to the delivered DATA-7B
# bundle's, so a reviewer can see the samples are the same bytes rather than a re-imagined series.
CHARGE_HDR = ['t_ps', 'iout_A']
EDGE_COLS = {'data_en': 'data_en', 'Xstage.data_en_b': 'data_en_b',
             'Xstage.Xsink.vbias_ch': 'vbias_ch', 'Xstage.Xsink.node_m': 'node_m',
             'iref_in': 'iref_in'}


def emit_charge_slice(series, c, w, out, run_id, ids, ev_dir):
    t0 = out['analog_t0_ps']
    t1 = out['analog_t1_ps']
    lo = t0 - EDGE_SEARCH_NS * NS
    hi = t1 + (TAIL_NS + EDGE_SEARCH_NS) * NS
    cur = [(t, v) for t, v in series['Ip_out:i'] if lo <= t <= hi]
    if not cur:
        raise RuntimeError('%s/%s: no samples inside the delivered slice' % (c['case_id'],
                                                                            w['window']))
    rows = [['%.17g' % t, '%.12g' % v] for t, v in cur]
    meta = shard_samples(rows, CHARGE_HDR, 'charge_%s_%s' % (c['case_id'], w['window']),
                         ev_dir)
    # the delivered slice must reproduce the same charge on its own bytes
    chk = MS.integrate([(float(r[0]), float(r[1])) for r in rows], t0, t1, 'slice re-read')
    if abs(chk['q'] - out['q_win']['q']) > max(1e-30, abs(out['q_win']['q']) * 1e-9):
        raise RuntimeError('%s/%s: the delivered samples do not reproduce the reported charge'
                           % (c['case_id'], w['window']))
    meta['recompute_q_win_C'] = chk['q']
    return meta


def around_rows(samples, centre_ps, span=4):
    """the samples on both sides of a claimed crossing or peak, so the claim can be re-verified"""
    if centre_ps is None or isinstance(centre_ps, str):
        return []
    idx = [i for i, (t, _v) in enumerate(samples) if t <= centre_ps]
    if not idx:
        return []
    i = idx[-1]
    lo, hi = max(0, i - span), min(len(samples), i + span + 1)
    return samples[lo:hi]


def emit_edge_slice(series, c, w, out, run_id, ev_dir):
    marks = [('de_rise_50', out.get('de_rise_50_ps')), ('de_fall_50', out.get('de_fall_50_ps')),
             ('i10', out.get('current_10pct_ps')), ('i90', out.get('current_90pct_ps')),
             ('peak', (out.get('window_peak') or {}).get('t_ps')),
             ('settled', (out.get('settled') or {}).get('settled_ps')),
             ('off', (out.get('turn_off') or {}).get('off_ps'))]
    rows = []
    for label, centre in marks:
        if centre is None or isinstance(centre, str):
            continue
        gathered = {}
        for name in list(EDGE_COLS) + ['Ip_out:i']:
            s = series.get(name, [])
            for t, v in around_rows(s, centre, 4):
                gathered.setdefault(t, {})[EDGE_COLS.get(name, 'iout')] = v
        for t in sorted(gathered):
            d = gathered[t]
            rows.append([run_id, c['case_id'], w['window'], label, '%.4f' % (t * 1e-3),
                         d.get('data_en', ''), d.get('data_en_b', ''), d.get('vbias_ch', ''),
                         d.get('node_m', ''), d.get('iref_in', ''), d.get('iout', '')])
    if not rows:
        return None
    return shard_samples(rows, EDGE_HDR, 'edge_%s_%s' % (c['case_id'], w['window']),
                         ev_dir)


def case_row(run_id, c, w, out, verdict, reasons, ids, launch_id):
    tick_ps = int(w['tick_ns']) * NS if w.get('tick_ns') else 0
    r = {'run_id': run_id, 'launch_id': launch_id, 'case_id': c['case_id'], 'group': c['group'],
         'role': c['role'], 'window': w.get('window', ''), 'mode': w.get('mode', ''),
         'code': w.get('code', ''), 'pam_request': w.get('pam_request', ''),
         'tick_ns': w.get('tick_ns', ''), 'full_intervals': w.get('full_intervals', ''),
         'expected_intervals': w.get('expected_intervals', ''), 'maxstep_ns': c['maxstep_ns'],
         'ramp_ns': c['ramp_ns'], 'vclamp_v': c['vclamp_v'],
         'deck_sha256': ids.get('deck_sha256', ''), 'pwl_sha256': ids.get('pwl_sha256', ''),
         'trace_sha256': ids.get('trace_sha256', ''), 'raw_sha256': ids.get('raw_sha256', ''),
         'log_sha256': ids.get('log_sha256', ''), 'section_read': ids.get('section', ''),
         'temp_read': ids.get('temp', ''),
         't0_ns': fmt_num(out.get('analog_t0_ps'), 1e-3), 't1_ns': fmt_num(out.get('analog_t1_ps'),
                                                                            1e-3),
         'q_win_C': fmt_num((out.get('q_win') or {}).get('q'), 1.0),
         'q_expected_C': fmt_num(out.get('q_expected_C'), 1.0),
         'q_lsb_C': fmt_num(out.get('q_lsb_C'), 1.0),
         'charge_error_LSB': fmt_num(out.get('charge_error_LSB'), 1.0, '%.6f'),
         'charge_error_pC': fmt_num(out.get('charge_error_pC'), 1.0, '%.6f'),
         'gain_error_vs_15uA': fmt_num(out.get('gain_error_vs_15uA'), 1.0, '%.8f'),
         'q_positive_C': fmt_num((out.get('q_win') or {}).get('q_pos'), 1.0),
         'q_negative_C': fmt_num((out.get('q_win') or {}).get('q_neg'), 1.0),
         'q_tail_C': fmt_num((out.get('q_tail') or {}).get('q'), 1.0),
         'window_peak_A': fmt_num((out.get('window_peak') or {}).get('value'), 1.0),
         'window_peak_t_ns': fmt_num((out.get('window_peak') or {}).get('t_ps'), 1e-3),
         'de_rise_50_ns': fmt_edge(out.get('de_rise_50_ps')),
         'de_fall_50_ns': fmt_edge(out.get('de_fall_50_ps')),
         'de_b_fall_50_ns': fmt_edge(out.get('de_b_fall_50_ps')),
         'de_fall_delay_ns': fmt_edge(out.get('de_fall_delay_ps')),
         'declared_pulses': out.get('declared_pulses', ''),
         'pulse_edges_missing': fmt_missing_edges(out.get('pulse_edges_missing_ps')),
         'current_10pct_ns': fmt_edge(out.get('current_10pct_ps')),
         'current_90pct_ns': fmt_edge(out.get('current_90pct_ps')),
         'current_rise_10_90_ns': fmt_edge(out.get('current_rise_10_90_ps')),
         'settled_status': (out.get('settled') or {}).get('status', ''),
         'settled_ns': fmt_edge((out.get('settled') or {}).get('settled_ps')),
         'longest_in_band_ns': fmt_edge((out.get('settled') or {}).get('longest_in_band_ps')),
         'off_status': (out.get('turn_off') or {}).get('status', ''),
         'off_ns': fmt_edge((out.get('turn_off') or {}).get('off_ps')),
         'off_segment_start_ns': fmt_edge(out.get('off_segment_start_ps')),
         'turn_off_delay_ns': fmt_edge(out.get('turn_off_delay_ps')),
         'last_100ns_max_abs_A': fmt_num(out.get('last_100ns_max_abs_A'), 1.0),
         'probe_direction_suspect': str(bool(out.get('probe_direction_suspect'))),
         'reused_from_native_run': ids.get('src_native_run', '') if ids.get('reused_from') else '',
         'src_launch_id': ids.get('src_launch_id', ''),
         'measurement_source_sha256': MS_SOURCE_SHA,
         'verdict': verdict, 'reasons': '; '.join(reasons).replace(',', ';')[:220]}
    return [r.get(k, '') for k in CASE_HDR]


def fmt_edge(v, scale=1e-3):
    """a time column that spells out NOT_FOUND / NOT_APPLICABLE instead of leaving them blank"""
    if v is None:
        return ''
    if isinstance(v, str):
        return v.replace(',', ';')
    return '%.4f' % (float(v) * scale)


def fmt_missing_edges(missing):
    if not missing:
        return ''
    return ';'.join('%d:%s' % (t, which) for t, which in missing)[:120]


def trace_edge_table(ev_dir, run_id, doc, c):
    rows = []
    for w in doc['windows']:
        for i, (t, v) in enumerate(doc['facts']['data_en_edges']):
            if not (w['t0_ps'] - 60 * NS <= t <= w['t_stop_ps'] + NS):
                continue
            rows.append([run_id, c['case_id'], w['window'], i, t, '%.4f' % (t * 1e-3), v,
                         '%.4f' % ((t + SHIFT_NS * NS) * 1e-3), doc['facts']['vcd_sha256'],
                         doc['facts']['tick_lead_ps'], c['ramp_ns']])
    write_rows(os.path.join(ev_dir, 'pwl_edges_%s.csv' % c['case_id']), rows,
               ['run_id', 'case_id', 'window', 'index', 't_ps', 't_ns', 'level',
                't_analog_ns', 'vcd_sha256', 'tick_lead_ps', 'ramp_ns'])
    return len(rows)

def push_case_dir(link, mst, decks, cid, out_root, remote_dir):
    """the deck, its PWL record and the master bytes the simulator reads, all in one private directory"""
    link.run('mkdir -p %s' % remote_dir, 120, 'mkdir-' + cid)
    c = dict((x['case_id'], x) for x in load_cases(os.path.join(PROJ, 'tests', 'dd1_d7b',
                                                                'cases.csv')))[cid]
    deck_local, pwl_local = stage_deck(c, decks[cid]['deck'], decks[cid]['points'], out_root)
    for m in mst:
        local = os.path.join(out_root, 'masters', m['name'])
        link.push(local, '%s/%s' % (remote_dir, m['name']), 'master')
    link.push(deck_local, '%s/%s.scs' % (remote_dir, cid), 'deck')
    link.push(pwl_local, '%s/%s_pwl.txt' % (remote_dir, cid), 'pwl')
    return deck_local, pwl_local


def static_probe(cases, mst, decks, run_id, out_root, log_dir, account):
    """every deck through the frozen static gates; this must start zero simulators"""
    root = '%s/static_%s' % (GUEST_ROOT, run_id)
    link = Link(GUEST_HOST, root, log_dir)
    ledger = Ledger(os.path.join(out_root, 'static_probe_ledger_%s.csv' % run_id))
    before = account.counts()
    prepare(link, mst, out_root, log_dir)
    n2 = build_static_negative(mst, decks, out_root, run_id)
    link.run('mkdir -p %s/neg_static' % root, 120, 'mkdir-N2')
    for m in mst:
        link.push(os.path.join(out_root, 'masters', m['name']),
                  '%s/neg_static/%s' % (root, m['name']), 'master')
    link.push(n2['local'], '%s/neg_static/D7B-N2.scs' % root, 'deck')
    row = ledger.begin('D7B-N2', 'static_negative', n2['sha256'], '')
    rc, text = link.run(('export PROJ=%s PDK_ENV=%s PREFLIGHT_STATIC_PROBE=1' + NL +
                         'bash %s/scripts/tb_preflight.sh %s/neg_static/D7B-N2.scs %s n2 "%s"')
                        % (root, GUEST_PDK_ENV, root, root, EXPECTED_VDD, SUPPLY_MAP),
                        600, 'n2-static')
    ledger.finish(row, rc, text, refusal=tail_reason(text))
    refused = (rc != 0 and 'PREFLIGHT_STAGE=supply_contract' in (text or '')
               and 'SUPPLY_FAIL' in (text or ''))
    print('N2_STATIC rc=%s refused=%s launches=%d' % (rc, refused, ledger.used))
    bad = []
    for c in cases:
        cid = c['case_id']
        rd = '%s/cases/%s' % (root, cid)
        push_case_dir(link, mst, decks, cid, out_root, rd)
        r = ledger.begin(cid, 'static_probe', decks[cid]['deck_sha256'], decks[cid]['pwl_sha256'])
        rc, text = link.run(('export PROJ=%s PDK_ENV=%s PREFLIGHT_STATIC_PROBE=1' + NL +
                             'bash %s/scripts/tb_preflight.sh %s/%s.scs %s sp_%s "%s"')
                            % (root, GUEST_PDK_ENV, root, rd, cid, EXPECTED_VDD, cid, SUPPLY_MAP),
                            600, 'sp-' + cid)
        ledger.finish(r, rc, text, refusal='' if rc == 7 else tail_reason(text))
        tok = 'SUPPLY_GATE: PASS' in (text or '') and rc == 7
        print('  %-20s rc=%s static=%s' % (cid, rc, 'PASS' if tok else 'REFUSED'))
        if not tok:
            bad.append('%s: %s' % (cid, tail_reason(text)))
    after = account.counts()
    spent = after['confirmed'] - before['confirmed']
    print('STATIC_PROBE %s (%d decks, %d Spectre launches, account launches spent=%d, N2 refused=%s)'
          % ('FAIL' if (bad or spent) else 'PASS', len(cases), ledger.used, spent, refused))
    for b in bad[:6]:
        print('  STATIC_BAD %s' % b)
    return 1 if (bad or spent or not refused or ledger.used != 0) else 0


def write_manifest_main(ev_dir):
    # the manifest describes the bytes that will be committed; it never hashes itself
    files = []
    for root, _dirs, names in os.walk(ev_dir):
        for name in sorted(names):
            if name == 'manifest.json':
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, ev_dir).replace(os.sep, '/')
            files.append({'path': rel, 'bytes': os.path.getsize(path),
                          'sha256': sha_file(path)})
    files.sort(key=lambda x: x['path'])
    cases = []
    cp = os.path.join(ev_dir, 'cases.csv')
    if os.path.isfile(cp):
        with io.open(cp, encoding='utf-8', newline='') as f:
            hdr = f.readline().strip().split(',')
            for line in f:
                if not line.strip():
                    continue
                d = dict(zip(hdr, line.rstrip('\r\n').split(',')))
                cases.append({'case_id': d['case_id'], 'window': d['window'],
                              'run_id': d['run_id'], 'launch_id': d['launch_id'],
                              'role': d['role'], 'verdict': d['verdict'],
                              'deck_sha256': d['deck_sha256'], 'pwl_sha256': d['pwl_sha256'],
                              'trace_sha256': d['trace_sha256'], 'raw_sha256': d['raw_sha256']})
    total = sum(x['bytes'] for x in files)
    doc = {'run_scope': 'DATA-7B evidence bundle', 'base_sha': BASE_SHA,
           'accepted_rtl_sha': ACCEPTED_SHA, 'files': files, 'file_count': len(files),
           'total_bytes': total, 'case_window_links': cases,
           'note': 'manifest.json is deliberately not listed: a file cannot carry its own final '
                   'digest. The bundle identity is read from the Git blobs after the commit.'}
    out = os.path.join(ev_dir, 'manifest.json')
    write_json(out, doc)
    print('MANIFEST_WRITTEN %s files=%d bytes=%d' % (out, len(files), total))
    if total > 32 * 1024 * 1024:
        print('MANIFEST_TRACKED_BYTES_OVER_LIMIT %d > %d' % (total, 32 * 1024 * 1024))
        return 6
    return 0


def read_csv_rows(path):
    if not os.path.isfile(path):
        raise RuntimeError('%s is missing' % path)
    with io.open(path, encoding='utf-8', newline='') as f:
        hdr = f.readline().strip().split(',')
        return [dict(zip(hdr, l.rstrip('\r\n').split(','))) for l in f if l.strip()]


def mirror_target_of(guest_path, cid, stage_dir):
    """the local mirrored file a printed guest path stands for, and the native run it names

    The layout is the one `native_run` produced: everything from `/cases/<cid>/` down is repeated
    under `<stage>/mirror`, and the path component in front of it is the guest task root's run id.
    Nothing is guessed from a glob, so a second pass that left a same-named file behind cannot be
    silently chosen for it.
    """
    key = '/cases/%s/' % cid
    i = (guest_path or '').rfind(key)
    if i < 0:
        return None, ''
    rel = guest_path[i + 1:].strip("'").split('?')[0]
    return os.path.join(stage_dir, 'mirror', *rel.split('/')), guest_path[:i].rsplit('/', 1)[-1]


def condition_readback(deck_text, log_text, raw_head):
    """where the section and the temperature of a run really come from

    This build's Spectre log does not echo the `section=` word, so the only byte that states it is the
    deck's own include line, and the only byte that states the temperature the analysis actually used
    is the psf header's `"temp"` column. Both are read here and made to agree with each other and with
    the 27 C the round is defined at; neither is copied from a file name or hard-coded.
    """
    conds = deck_conditions(deck_text)
    env = readback_env(log_text, raw_head)
    section = conds['deck_section']
    src = {'section': 'deck include line', 'temp': 'psf header temp column'}
    if not section:
        raise RuntimeError('the deck carries no section= word, so the corner is unknown')
    if not conds['temp']:
        raise RuntimeError('the deck carries no simopt options temp=, so the temperature is unknown')
    header_temp = env['temp_header_C']
    if not header_temp:
        raise RuntimeError('the produced psf names no "temp" column, so the analysed temperature '
                           'cannot be read back')
    if abs(float(header_temp) - float(conds['temp'])) > 1e-6:
        raise RuntimeError('the deck asks for temp=%s but the psf header reports %s'
                           % (conds['temp'], header_temp))
    if abs(float(header_temp) - TEMP_C) > 1e-6:
        raise RuntimeError('the run analysed at %s C, not the %d C this round is defined at'
                           % (header_temp, TEMP_C))
    return section, header_temp, src, conds


def wave_points(wave):
    """the PWL `(time_ps, volt)` pairs out of a deck's `wave=[...]` clause"""
    toks = (wave or '').split()
    pts = []
    for i in range(0, len(toks) - 1, 2):
        t = toks[i]
        ps = float(t[:-1]) * NS if t.endswith('n') else float(t)
        pts.append((ps, float(toks[i + 1])))
    return pts


def deck_identity_compare(cid, retained_deck, rebuilt_deck):
    """what must not differ between a retained run and this round's rebuild, and what is explained

    The circuit and every declared condition have to be identical, because a reused number is only the
    same measurement if it came off the same seven devices at the same bias. The one difference the
    delivered round really carries is the simulation stop: the calibration ran in `r5_cal`, before the
    builder learned to append the STOP_MARGIN hold point that keeps an integration bound from sitting
    on the last sample. That difference is reported, not hidden, and it must be exactly the hold point.
    """
    notes = []
    if device_digest(retained_deck) != device_digest(rebuilt_deck):
        raise RuntimeError('%s: the retained run is not the same circuit as this round rebuilds '
                           '(%s vs %s)' % (cid, device_digest(retained_deck),
                                           device_digest(rebuilt_deck)))
    for line in ('Xstage (data_en iref_in vcas data_out vdd18 vss) dd1_d7b_pwm_stage',
                 'Ip_out (clamp data_out) iprobe'):
        if (line in retained_deck) != (line in rebuilt_deck):
            raise RuntimeError('%s: the stage or the ammeter instance line is not the same in the '
                               'retained deck: %r' % (cid, line))
    c1 = deck_conditions(retained_deck)
    c2 = deck_conditions(rebuilt_deck)
    for k in ('temp', 'deck_section', 'iref_A', 'vcas_V', 'vclamp_V', 'maxstep', 'method', 'iprobe'):
        if c1[k] != c2[k]:
            raise RuntimeError('%s: the retained deck declares %s=%s, this round declares %s'
                               % (cid, k, c1[k], c2[k]))
    w1, w2 = wave_points(c1['pwl_wave']), wave_points(c2['pwl_wave'])
    if bool(w1) != bool(w2):
        raise RuntimeError('%s: one deck drives data_en from a PWL clause and the other does not'
                           % cid)
    if not w1:
        notes.append('neither deck carries a PWL wave: this case drives the enable from a bench '
                     'source, which is the wiring fault under test')
        return c1, notes
    if not c1['stop'] or not c2['stop']:
        raise RuntimeError('%s: a deck carries no tran stop=, so the stimulus span cannot be '
                           'compared' % cid)
    stop1 = float(c1['stop'].rstrip('s')) if c1['stop'].endswith('s') else float(c1['stop'])
    stop2 = float(c2['stop'].rstrip('s')) if c2['stop'].endswith('s') else float(c2['stop'])
    inside = [p for p in w1 if p[0] <= stop1 * 1e12]
    rebuilt_inside = [p for p in w2 if p[0] <= stop1 * 1e12]
    if inside != rebuilt_inside:
        raise RuntimeError('%s: the stimulus up to the retained stop differs: %r vs %r'
                           % (cid, inside[-2:], rebuilt_inside[-2:]))
    if stop2 != stop1:
        extra_ps = (stop2 - stop1) * 1e12
        if abs(extra_ps - STOP_MARGIN_NS * NS) > 1.0:
            raise RuntimeError('%s: the retained run stopped at %.12g s and this round at %.12g s, '
                               'which is not the documented %d ns hold point'
                               % (cid, stop1, stop2, STOP_MARGIN_NS))
        notes.append('stop: retained %.12g s, this round %.12g s (+%d ns hold point added to the '
                     'builder after the retained run; the measured windows are inside the retained '
                     'stop)' % (stop1, stop2, STOP_MARGIN_NS))
    return c1, notes


def resolve_reuse(spec, decks, mst, published_dir=HISTORICAL_EVIDENCE):
    """`case_id=<retained stage dir>` pairs, verified byte for byte before anything is measured

    The retained ledger is treated as an index, never as proof. For every reused case this recomputes
    the digest of the raw, the log, the deck and the PWL that are really still on this machine, binds
    them to a transcript whose printed datafile path leads to exactly those bytes, requires the native
    rc of both the preflight and the DUT launch to be zero, and requires the deck and PWL to be the
    same bytes this round rebuilds from the frozen Git blobs and the same bytes the delivered bundle
    published. A glob hit, an ambiguous transcript, a missing twin or a drifted deck is a refusal.
    """
    out = {}
    published_cases = {}
    for r in read_csv_rows(os.path.join(published_dir, 'cases.csv')):
        published_cases.setdefault(r['case_id'], r)
    for pair in [x for x in (spec or '').split(',') if x.strip()]:
        if '=' not in pair:
            raise RuntimeError('--reuse wants case_id=stage_dir, got %r' % pair)
        cid, base = pair.split('=', 1)
        base = os.path.abspath(base)
        if not os.path.isdir(base):
            raise RuntimeError('%s: the retained directory %s is not there' % (cid, base))
        if cid not in decks:
            raise RuntimeError('%s: this round builds no deck for it, so it cannot be reused' % cid)
        pub = published_cases.get(cid)
        if pub is None:
            raise RuntimeError('%s is not in the delivered case table, so nothing about it is fixed'
                               % cid)
        # the delivered bundle is the committed index of the native run: it names the launch, its rc
        # and the digests the numbers were made from. The retained stage only has to prove that those
        # same bytes are still here.
        led_key = '%s/%s' % (pub['run_id'], pub['launch_id'])
        pub_led = read_csv_rows(os.path.join(published_dir, 'process_ledger.csv'))
        d = [r for r in pub_led if r['launch_id'] == led_key and r['role'] == 'dut']
        launched_by = led_key
        if len(d) == 1:
            pre = [r for r in pub_led if r['case_id'] == cid and r['role'] == 'preflight'
                   and r['launch_id'].startswith('%s/' % pub['run_id'])]
            if len(pre) != 1 or pre[0]['rc'] != '0':
                raise RuntimeError('%s: the delivered ledger has %d rail-preflight twin(s) for run '
                                   '%s with rc 0' % (cid, len(pre), pub['run_id']))
            pre_row = pre[0]
        else:
            # the delivered round recorded its own reused calibration as run `r11_main<-r5_cal`,
            # launch `REUSED`, which is a note rather than a ledger row: the native rc then has to come
            # from the transcript of the run that produced the bytes, and the pass must be unambiguous
            if d and len(d) > 1:
                raise RuntimeError('%s: %d delivered ledger rows are named %s' % (cid, len(d),
                                                                                  led_key))
            d = [{}]
            pre_row = {'launch_id': ''}
            launched_by = ''
        d = d[0]
        if d:
            if d.get('state') not in ('DONE', 'COMPLETED') or d.get('rc') != '0':
                raise RuntimeError('%s: the delivered dut row %s is %s rc=%s'
                                   % (cid, led_key, d.get('state'), d.get('rc')))
            if not d['spectre_line'].startswith('SPECTRE_name=') or not d['spectre_line'].endswith(
                    '_rc=0'):
                raise RuntimeError('%s: the delivered dut row carries no native rc=0 evidence (%s)'
                                   % (cid, d['spectre_line'][:60]))
        raw_want, log_want = pub['raw_sha256'], pub['log_sha256']
        deck_want, pwl_want = pub['deck_sha256'], pub['pwl_sha256']
        # when the delivered ledger names the launch, it also names the native run, and a transcript
        # of another run is not evidence about these bytes even if the mirror path still holds them
        want_run = pub['run_id'] if d else ''
        tdir = os.path.join(base, 'transcripts')
        cands = sorted(x for x in os.listdir(tdir) if x.endswith('_dut-%s.txt' % cid))
        if not cands:
            raise RuntimeError('%s: no retained dut transcript under %s' % (cid, tdir))
        picked = []
        for name in cands:
            text = u(io.open(os.path.join(tdir, name), encoding='utf-8',
                             errors='replace').read())
            parts = parse_runner(text)
            if parts['rc'] != '0' or not re.search(r'^SPECTRE name=\S+ rc=0', text, re.M):
                continue
            raw_local, src_run = mirror_target_of(parts['datafile'], cid, base)
            log_local, _ = mirror_target_of(parts['logfile'], cid, base)
            if not raw_local or not os.path.isfile(raw_local):
                continue
            if want_run and src_run != want_run:
                continue
            if sha_file(raw_local) != raw_want:
                continue
            if not log_local or not os.path.isfile(log_local):
                continue
            if sha_file(log_local) != log_want:
                continue
            if parts['datafile'] not in text or parts['logfile'] not in text:
                continue
            picked.append((name, raw_local, log_local, src_run, parts, text))
        if not picked:
            raise RuntimeError('%s: none of the %d retained transcripts leads to the bytes the '
                               'delivered bundle hashes to %s' % (cid, len(cands), raw_want[:12]))
        runs = sorted(set(p[3] for p in picked))
        if len(runs) > 1:
            raise RuntimeError('%s: the retained transcripts name %d different native runs (%s) for '
                               'the same bytes; the reuse is ambiguous and is refused'
                               % (cid, len(runs), ', '.join(runs)))
        if len(picked) > 1:
            raise RuntimeError('%s: %d transcripts of run %s lead to the same bytes; nothing is '
                               'chosen by taking the first' % (cid, len(picked), runs[0]))
        name, raw_local, log_local, src_run, parts, text = picked[0]
        deck_local = os.path.join(base, 'mirror', 'cases', cid, '%s.scs' % cid)
        pwl_local = os.path.join(base, 'pwl', '%s_pwl.txt' % cid)
        for label, path in (('deck', deck_local), ('pwl', pwl_local)):
            if not os.path.isfile(path):
                raise RuntimeError('%s: the retained %s %s is gone' % (cid, label, path))
        got_deck = sha_file(deck_local)
        got_pwl = sha_file(pwl_local)
        if got_deck != deck_want:
            raise RuntimeError('%s: the retained deck bytes are %s, the delivered table says %s'
                               % (cid, got_deck[:12], deck_want[:12]))
        want_pwl = sha_txt(pwl_text(decks[cid]['points']))
        if got_pwl != want_pwl:
            raise RuntimeError('%s: the retained PWL bytes hash to %s, this round rebuilds %s'
                               % (cid, got_pwl[:12], want_pwl[:12]))
        retained_deck = u(io.open(deck_local, encoding='utf-8', newline='\n').read())
        rebuilt = u(decks[cid]['deck'])
        conds, identity_notes = deck_identity_compare(cid, retained_deck, rebuilt)
        for m in mst:
            ml = os.path.join(base, 'masters', m['name'])
            if not os.path.isfile(ml):
                raise RuntimeError('%s: the master %s the retained run read is gone (%s)'
                                   % (cid, m['name'], ml))
            if sha_file(ml) != m['sent_sha256']:
                raise RuntimeError('%s: master %s hashes to %s, this round sends %s'
                                   % (cid, m['name'], sha_file(ml)[:12], m['sent_sha256'][:12]))
        log_text = u(io.open(log_local, encoding='utf-8', errors='replace').read())
        head = u(io.open(raw_local, encoding='utf-8', errors='replace').read())[:4000]
        section, temp, cond_src, _c = condition_readback(retained_deck, log_text, head)
        out[cid] = {'src_dir': base, 'src_native_run': src_run,
                    'src_run': '%s/%s' % (src_run, launched_by or 'delivered note %s' % pub['run_id']),
                    'launch_id': d.get('launch_id') or pub['launch_id'],
                    'preflight_launch_id': pre_row['launch_id'],
                    'psf': raw_local, 'log': log_local, 'deck': deck_local, 'pwl': pwl_local,
                    'transcript': os.path.join(tdir, name),
                    'deck_sha256': got_deck, 'pwl_sha256': got_pwl,
                    'raw_sha256': raw_want, 'log_sha256': log_want,
                    'native_rc': d.get('rc') or parts['rc'],
                    'preflight_rc': pre_row.get('rc', ''),
                    'section': section, 'temp': temp, 'condition_sources': cond_src,
                    'conditions': conds, 'identity_notes': identity_notes,
                    'published_row': pub}
        for wkey, col in (('section', 'section_read'), ('temp', 'temp_read')):
            if pub[col] and out[cid][wkey] != pub[col]:
                # the delivered calibration row left these two columns empty, which is one of the
                # corrections this round makes; an empty old cell is not a disagreement
                raise RuntimeError('%s: the retained run reads %s=%s, the delivered table says %s'
                                   % (cid, wkey, out[cid][wkey], pub[col]))
    return out


def pwl_text(points):
    """the one serialisation a PWL file is allowed to have, so its bytes and its digest agree

    The delivered bundle recorded a digest over a newline-joined text while the file on disk carried a
    trailing newline on the last line, so no checker could recompute the delivered number from the
    delivered bytes. Here the table digest is the digest of exactly these bytes.
    """
    return ''.join('%d %.6g\n' % (t, v) for t, v in points)


def deck_conditions(deck_text):
    """the electrical conditions a deck really carries, read out of the bytes it was run with"""
    out = {}
    m = re.search(r'^\s*simopt\s+options\s+temp=(\S+)', deck_text, re.M)
    out['temp'] = m.group(1) if m else ''
    m = re.search(r'section=(\w+)', deck_text)
    out['deck_section'] = m.group(1) if m else ''
    m = re.search(r'^\s*Iref\s*\([^)]*\)\s*isource\s+dc=(\S+)', deck_text, re.M)
    out['iref_A'] = m.group(1) if m else ''
    m = re.search(r'^\s*Vcas\s*\(\s*(\S+)\s+\S+\s*\)\s*vsource\s+dc=(\S+)', deck_text, re.M)
    out['vcas_V'] = m.group(2) if m else ''
    m = re.search(r'^\s*Vclamp\s*\(\s*(\S+)\s+\S+\s*\)\s*vsource\s+dc=(\S+)', deck_text, re.M)
    out['vclamp_V'] = m.group(2) if m else ''
    m = re.search(r'^\s*\w+\s+tran\s+stop=(\S+)\s+maxstep=(\S+)', deck_text, re.M)
    out['stop'] = m.group(1) if m else ''
    out['maxstep'] = m.group(2) if m else ''
    out['method'] = (re.search(r'tran\s+stop=\S+\s+maxstep=\S+\s+method=(\S+)', deck_text)
                     or [None, ''])[1]
    out['iprobe'] = ('Ip_out (clamp data_out) iprobe' in deck_text)
    m = re.search(r'Vde\s*\(data_en 0\)\s*vsource\s+type=pwl\s+wave=\[([^\]]*)\]', deck_text)
    out['pwl_wave'] = re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''
    return out


def emit_case_windows(c, series, ids, cal, docs, run_id, ev_dir, rows, charge_index, results,
                      negative_rows, launch_id, note=''):
    """measure every declared window of one delivered current series and stage its evidence

    Both entrances call this: a native launch and an offline re-measurement of retained bytes. That
    is deliberate -- a reused row and a freshly measured row must mean the same arithmetic, and the
    only difference allowed between them is the note that says where the bytes came from.
    """
    cid = c['case_id']
    doc = docs.get(cid)
    if doc is None:
        rows.append(case_row(run_id, c, {'window': ''}, {}, 'FAIL_TOOL',
                             ['no trace document for %s' % cid], ids, launch_id))
        return
    by_window = dict((w['window'], w) for w in doc['windows'])
    for wname in c['windows'].split(';'):
        w = by_window.get(wname)
        if w is None:
            rows.append(case_row(run_id, c, {'window': wname}, {}, 'FAIL_TOOL',
                                 ['the trace document declares no window %s' % wname], ids,
                                 launch_id))
            continue
        out = measure_one(c, w, series, cal['ical_A'], launch_id, ids, run_id)
        verdict, reasons = MS.judge(out)
        if c['role'] == 'negative_wiring':
            # a dark window is a fault when the port really carries current above the OFF criterion
            # in the direction that lights the pixel -- not by a charge-scale accident
            det = ((out['window_peak']['value'] or 0.0) > MS.OFF_ABS and out['q_win']['q'] > 0.0)
            neg = {'case_id': cid, 'window': wname, 'detected': 'YES' if det else 'NO',
                   'q_win_C': out['q_win']['q'], 'expected_dark_C': 0.0,
                   'window_peak_A': out['window_peak']['value'],
                   'last_100ns_max_abs_A': out['last_100ns_max_abs_A'],
                   'verdict': 'EXPECTED_REFUSAL / WIRING_FAULT_DETECTED' if det
                              else 'NOT_DETECTED',
                   'deck_sha256': ids['deck_sha256'], 'raw_sha256': ids['raw_sha256'],
                   'run_id': run_id, 'launch_id': launch_id,
                   'src_native_run': ids.get('src_native_run', ''),
                   'transcript_sha256': ids.get('transcript_sha256', '')}
            negative_rows.append(neg)
            verdict, reasons = ('EXPECTED_REFUSAL' if det else 'NEGATIVE_NOT_DETECTED',
                                ['the black window carries %r A of peak current'
                                 % out['window_peak']['value']])
        if note:
            reasons = reasons + [note]
        results[(cid, wname)] = out
        rows.append(case_row(run_id, c, w, out, verdict, reasons, ids, launch_id))
        charge_index.append(emit_charge_slice(series, c, w, out, run_id, ids, ev_dir))
        edge_meta = emit_edge_slice(series, c, w, out, run_id, ev_dir)
        if edge_meta:
            # an unindexed shard set is bytes nobody can bind: the delivered bundle shipped 26
            # edge_*.csv files that its own charge_index.csv never named
            charge_index.append(edge_meta)
        trace_edge_table(ev_dir, run_id, doc, c)
        print('  %s q_win=%.6g C err=%+.4f LSB settled=%s off=%s %s'
              % (wname, out['q_win']['q'], out['charge_error_LSB'] or 0.0,
                 out['settled']['status'], out['turn_off']['status'], verdict))


def reused_ids(info, trace_sha):
    """the identity columns of a reused run: native identity, deck bytes and this export's code"""
    return {'deck_sha256': info['deck_sha256'], 'pwl_sha256': info['pwl_sha256'],
            'trace_sha256': trace_sha, 'raw_sha256': info['raw_sha256'],
            'log_sha256': info['log_sha256'], 'section': info['section'], 'temp': info['temp'],
            'condition_sources': info['condition_sources'],
            'src_native_run': info['src_native_run'], 'src_launch_id': info['launch_id'],
            'transcript_sha256': sha_file(info['transcript']),
            'reused_from': info['src_dir'].replace(os.sep, '/')}


def native_run(cases, mst, docs, decks, opts, run_id, out_root, log_dir, account):
    root = '%s/%s' % (GUEST_ROOT, run_id)
    link = Link(GUEST_HOST, root, log_dir)
    ev_dir = os.path.join(out_root, 'evidence', run_id)
    for sub in ('', 'pwl', 'decks', 'transcripts'):
        if not os.path.isdir(os.path.join(ev_dir, sub)):
            os.makedirs(os.path.join(ev_dir, sub))
    ledger = stage_ledger(ev_dir)
    frozen = prepare(link, mst, out_root, log_dir)
    print('TASK_ROOT %s' % root)
    print('FROZEN_TOOLS ' + ' '.join('%s=%s' % (k, v[:12]) for k, v in sorted(frozen.items())))

    rows = []
    charge_index = []
    results = {}
    # the reuse split happens here, before the loop can reach a single preflight: a reused case is
    # never pushed, never preflighted and never launched, and its bytes are verified first
    reuse_map = resolve_reuse(opts.reuse, decks, mst, opts.published_dir)
    if reuse_map:
        print('REUSE_CASES %s' % ' '.join('%s<-%s/%s' % (k, v['src_native_run'], v['launch_id'])
                                          for k, v in sorted(reuse_map.items())))
        for cid in sorted(reuse_map):
            account.note(cid, 'reused_measurement', run_id,
                         'measured offline from native run %s launch %s'
                         % (reuse_map[cid]['src_native_run'], reuse_map[cid]['launch_id']))
    cal = None
    negative_rows = []
    stopped = ''

    # static negative N2 first: it must refuse without ever starting the simulator
    if 'D7B-P30-C001' in decks:
        n2 = build_static_negative(mst, decks, out_root, run_id)
        negative_rows.append(run_static_negative(link, ledger, n2, run_id, mst, out_root, account))
    else:
        print('N2_SKIPPED this pass does not carry its source deck')

    for c in cases:
        cid = c['case_id']
        # the ceiling is checked before the case is pushed, preflighted or launched, so a plan that
        # has run out can never spend one more process on its way to the refusal
        if cid not in reuse_map and account.remaining() < PREFLIGHT_PER_DUT + 1:
            stopped = ('the launch ceiling leaves %d of %d occupied; %s was not started'
                       % (account.remaining(), account.ceiling, cid))
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'BLOCKED_BUDGET',
                                 [stopped], decks[cid], ''))
            break
        if cal is not None and not cal['ok'] and c['role'] != 'calibration':
            rows.append(case_row(run_id, c, {'window': 'normal'}, {}, 'BLOCKED',
                                 ['the calibration current never met its own window, so no other '
                                  'current conclusion is admissible'], decks[cid], ''))
            continue
        if cid in reuse_map:
            cal, why = remeasure_case(c, reuse_map[cid], cal, docs, run_id, ev_dir, rows,
                                      charge_index, results, negative_rows)
            if why:
                stopped = why
                break
            print('DUT %s REUSED from %s/%s launches=%d/%d'
                  % (cid, reuse_map[cid]['src_native_run'], reuse_map[cid]['launch_id'],
                     account.counts()['confirmed'], account.ceiling))
            continue
        remote_dir = '%s/cases/%s' % (root, cid)
        push_case_dir(link, mst, decks, cid, out_root, remote_dir)
        tag = '%s__%s' % (cid, run_id)
        pf = ('export PROJ=%s PDK_ENV=%s\nbash %s/scripts/tb_preflight.sh %s/%s.scs %s %s "%s"\n'
              % (root, GUEST_PDK_ENV, root, remote_dir, cid, EXPECTED_VDD, tag, SUPPLY_MAP))
        prow = ledger.begin(cid, 'preflight', decks[cid]['deck_sha256'], decks[cid]['pwl_sha256'])
        arow = account.reserve(cid, 'preflight', decks[cid]['deck_sha256'],
                               decks[cid]['pwl_sha256'], run_id)
        try:
            rc, text = link.run(pf, 900, 'preflight-' + cid)
        except Exception as exc:
            account.mark_uncertain(arow, 'rail preflight outcome unknown: %s' % exc)
            stopped = 'rail preflight of %s lost contact; the launch stays uncertain' % cid
            rows.append(case_row(run_id, c, {'window': 'preflight'}, {}, 'UNCERTAIN_LAUNCH',
                                 [str(exc)], decks[cid], prow['launch_id']))
            break
        launched, evidence = launch_evidence_of(text)
        p_ok = (rc == 0 and len(re.findall(r'^TESTBENCH_PREFLIGHT: PASS$', text or '', re.M)) == 1)
        account.settle(arow, rc, text, launched, evidence,
                       refusal='' if p_ok else tail_reason(text))
        p_launched = launched if re.search(r'^spectre_rc=', text or '', re.M) else 0
        ledger.finish(prow, rc, text, refusal='' if p_ok else tail_reason(text),
                      launched=p_launched)
        if not p_ok:
            rows.append(case_row(run_id, c, {'window': 'preflight'}, {}, 'BLOCKED',
                                 ['rail preflight refused: %s' % tail_reason(text)], decks[cid],
                                 prow['launch_id']))
            print('PREFLIGHT_FAIL %s rc=%s' % (cid, rc))
            continue
        label = 'D7B_' + cid.replace('-', '_')
        script = ('export PROJ=%s PDK_ENV=%s\nLABEL=%s bash %s/scripts/run_spectre.sh '
                  '%s/%s.scs %d\n' % (root, GUEST_PDK_ENV, label, root, remote_dir, cid, 1800))
        drow = ledger.begin(cid, 'dut', decks[cid]['deck_sha256'], decks[cid]['pwl_sha256'])
        arow = account.reserve(cid, 'dut', decks[cid]['deck_sha256'], decks[cid]['pwl_sha256'],
                               run_id)
        try:
            rc, text = link.run(script, 2000, 'dut-' + cid)
        except Exception as exc:
            account.mark_uncertain(arow, 'dut launch outcome unknown: %s' % exc)
            stopped = 'the DUT launch of %s lost contact; the launch stays uncertain' % cid
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'UNCERTAIN_LAUNCH', [str(exc)],
                                 decks[cid], drow['launch_id']))
            break
        parts = parse_runner(text)
        ids = {'deck_sha256': decks[cid]['deck_sha256'], 'pwl_sha256': decks[cid]['pwl_sha256'],
               'trace_sha256': docs[cid]['facts']['vcd_sha256'] if cid in docs else 'bench',
               'raw_sha256': '', 'log_sha256': '', 'section': '', 'temp': '',
               'src_native_run': run_id, 'src_launch_id': drow['launch_id'], 'reused_from': ''}
        mirror_dir = os.path.join(out_root, 'mirror', 'cases', cid)
        mirror_sim = os.path.join(mirror_dir, 'sim')
        if not os.path.isdir(mirror_sim):
            os.makedirs(mirror_sim)
        shutil.copyfile(os.path.join(out_root, 'decks', cid, '%s.scs' % cid),
                        os.path.join(mirror_dir, '%s.scs' % cid))
        mirror_posix = os.path.join(out_root, 'mirror').replace(os.sep, '/')

        def mirrored(guest_path):
            """one produced file, pulled back onto a mirrored layout so the frozen contract can open
            the exact paths the runner printed; only the root prefix changes"""
            if not guest_path or not guest_path.startswith(root + '/'):
                return None
            local = os.path.join(out_root, 'mirror', *guest_path[len(root) + 1:].split('/'))
            d = os.path.dirname(local)
            if not os.path.isdir(d):
                os.makedirs(d)
            return local

        raw_local = mirrored(parts['datafile'])
        log_local = mirrored(parts['logfile'])
        if raw_local:
            ids['raw_sha256'] = link.pull(parts['datafile'], raw_local)
            ids['raw_local'] = raw_local
        if log_local:
            ids['log_sha256'] = link.pull(parts['logfile'], log_local)
            ids['log_text'] = u(io.open(log_local, encoding='utf-8', errors='replace').read())
        local_text = (text or '').replace(root, mirror_posix)
        ok, reasons, got = CC.runner_verdict(label, '%s/%s.scs' % (mirror_dir, cid), rc, local_text)
        launched, evidence = launch_evidence_of(text)
        account.settle(arow, rc, text, launched, evidence, ids['raw_sha256'], ids['log_sha256'],
                       refusal='' if ok else tail_reason('; '.join(reasons)))
        ledger.finish(drow, rc, text, ids['raw_sha256'], ids['log_sha256'],
                      refusal='' if ok else tail_reason('; '.join(reasons)))
        print('DUT %s rc=%s verdict=%s launches=%d/%d' % (cid, rc, 'OK' if ok else 'REFUSED',
                                                          account.counts()['confirmed'],
                                                          account.ceiling))
        if not ok:
            print('  REFUSED ' + '; '.join(reasons)[:400])
            for wname in c['windows'].split(';'):
                rows.append(case_row(run_id, c, {'window': wname}, {}, 'FAIL_TOOL', reasons, ids,
                                     drow['launch_id']))
            continue
        if not ids['raw_sha256']:
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'FAIL_TOOL',
                                 ['no datafile was reported'], ids, drow['launch_id']))
            continue
        series, _times = psf_series(ids['raw_local'])
        head = u(io.open(raw_local, encoding='utf-8', errors='replace').read())[:4000]
        try:
            section, temp, cond_src, _c = condition_readback(u(decks[cid]['deck']),
                                                             ids.get('log_text', ''), head)
        except RuntimeError as exc:
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'FAIL_TOOL', [str(exc)], ids,
                                 drow['launch_id']))
            continue
        ids['section'] = section
        ids['temp'] = temp
        ids['condition_sources'] = cond_src
        if c['role'] == 'calibration':
            cal = calibrate(series, run_id, ids)
            write_calibration_rows(ev_dir, cal)
            out = cal_measure(series)
            cal_slice(series, c, out, run_id, ids, ev_dir, charge_index)
            print('CAL Ical=%r ok=%s %s' % (cal['ical_A'], cal['ok'], '; '.join(cal['reasons'])))
            rows.append(case_row(run_id, c, {'window': 'cal'}, out,
                                 'PASS' if cal['ok'] else 'FAIL', cal['reasons'], ids,
                                 drow['launch_id']))
            if not cal['ok']:
                stopped = 'the calibration current failed; every other current conclusion is BLOCKED'
                break
            continue
        if cal is None:
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'BLOCKED',
                                 ['no calibration current is available yet'], ids,
                                 drow['launch_id']))
            continue
        emit_case_windows(c, series, ids, cal, docs, run_id, ev_dir, rows, charge_index, results,
                          negative_rows, drow['launch_id'])

    return write_bundle(run_id, cases, mst, docs, decks, out_root, ev_dir, rows, charge_index,
                        results, negative_rows, reuse_map, cal, ledger, account, mode='run',
                        root=root, stopped=stopped, reused=False, frozen=frozen)


def refuse_overbudget(case_id, role, why, run_id, out_root):
    """the native entry point is closed while the historical account is over its ceiling"""
    print('D7B_REFUSED %s of %s: %s' % (OVERBUDGET_REFUSAL, role, why))
    print('NO_PROCESS_WAS_STARTED run_id=%s out=%s' % (run_id, out_root))
    return 5


def write_calibration_rows(ev_dir, cal):
    """6.1: the calibration table, with the temperature and corner it was read out of, not assumed

    The delivered bundle left `section` and `temp` empty here while asserting they had been read from
    the products, which is what DATA-7B-R1 had to correct.
    """
    ids = cal.get('ids') or {}
    src = ids.get('condition_sources') or {}
    rows = []
    for r in cal['rows']:
        rows.append([r['run_id'], r['quantity'], fmt_num(r.get('value'), 1.0),
                     r.get('window_ns', ''), fmt_num(r.get('band_min_A'), 1.0),
                     fmt_num(r.get('band_max_A'), 1.0), r.get('band_samples', ''),
                     r.get('integration_s', ''), ids.get('section', ''), ids.get('temp', ''),
                     '; '.join('%s from %s' % (k, v) for k, v in sorted(src.items()))])
    write_rows(os.path.join(ev_dir, 'calibration.csv'), rows,
               ['run_id', 'quantity', 'value_A', 'window_ns', 'band_min_A', 'band_max_A',
                'band_samples', 'integration_s', 'section_read', 'temp_read_C', 'condition_source'])


def cal_measure(series):
    """the calibration window as a measurable row: the band integral over the delivered samples"""
    t0, t1 = CAL_BAND
    return {'analog_t0_ps': t0, 'analog_t1_ps': t1,
            'q_win': {'q': MS.integrate(series['Ip_out:i'], t0, t1, 'calibration band')['q']},
            'settled': {'status': 'MEASURED'}, 'turn_off': {'status': 'OFF'}}


def cal_slice(series, c, out, run_id, ids, ev_dir, charge_index):
    """the calibration band samples, delivered as their own shard series

    The delivered bundle asserted an Ical it could not show the bytes of, which is why an independent
    reviewer had to take the calibration table on trust and could not recompute 3.0..3.5 us at all.
    """
    w = {'window': 'cal', 'tick_ns': '', 'full_intervals': '', 'expected_intervals': '',
         'mode': '', 'code': '', 'pam_request': ''}
    meta = emit_charge_slice(series, c, w, out, run_id, ids, ev_dir)
    if meta:
        charge_index.append(meta)
    return meta


def remeasure_case(c, info, cal, docs, run_id, ev_dir, rows, charge_index, results,
                   negative_rows):
    """one case measured from bytes a previous native run already produced; returns (cal, stop)

    The same `emit_case_windows` and the same `calibrate` serve a live launch and a retained file, so
    a reused row cannot quietly mean a different arithmetic than a fresh one.
    """
    cid = c['case_id']
    ids = reused_ids(info, docs[cid]['facts']['vcd_sha256'] if cid in docs else 'bench')
    series, _t = psf_series(info['psf'])
    note = ('reused: measured offline from native run %s launch %s (retained bytes under %s); no '
            'process was started for it this pass' % (info['src_native_run'], info['launch_id'],
                                                      info['src_dir'].replace(os.sep, '/')))
    if c['role'] == 'calibration':
        cal = calibrate(series, run_id, ids)
        write_calibration_rows(ev_dir, cal)
        out = cal_measure(series)
        cal_slice(series, c, out, run_id, ids, ev_dir, charge_index)
        rows.append(case_row(run_id, c, {'window': 'cal'}, out,
                             'PASS' if cal['ok'] else 'FAIL', cal['reasons'] + [note], ids,
                             info['launch_id']))
        print('CAL_REUSED Ical=%r ok=%s %s' % (cal['ical_A'], cal['ok'], '; '.join(cal['reasons'])))
        return cal, ('' if cal['ok'] else
                     'the reused calibration current failed; every other current conclusion is '
                     'BLOCKED')
    if cal is None or not cal.get('ok'):
        rows.append(case_row(run_id, c, {'window': ''}, {}, 'BLOCKED',
                             ['no admissible calibration current was available when this case was '
                              're-measured'] + [note], ids, info['launch_id']))
        return cal, ''
    emit_case_windows(c, series, ids, cal, docs, run_id, ev_dir, rows, charge_index, results,
                      negative_rows, info['launch_id'], note=note)
    return cal, ''


def carried_negative(stage_dir, published_dir):
    """the N2 supply refusal carried forward from bytes, with its own digests re-verified

    Re-measuring offline cannot re-refuse a deck on a guest that is not being touched, so the fact is
    taken from the retained transcript of the run that really refused it -- and only after the deck
    bytes behind that transcript still hash to what the delivered bundle published.
    """
    pub_rows = [r for r in read_csv_rows(os.path.join(published_dir, 'negative.csv'))
                if r['case_id'] == 'D7B-N2']
    if len(pub_rows) != 1:
        raise RuntimeError('the delivered bundle has %d N2 row(s)' % len(pub_rows))
    pub = pub_rows[0]
    cands = sorted(x for x in os.listdir(os.path.join(stage_dir, 'transcripts'))
                   if x.endswith('_n2.txt'))
    if len(cands) != 1:
        raise RuntimeError('%d retained N2 transcripts: the refusal cannot be bound to one run'
                           % len(cands))
    text = u(io.open(os.path.join(stage_dir, 'transcripts', cands[0]), encoding='utf-8',
                     errors='replace').read())
    stage = re.search(r'^PREFLIGHT_STAGE=(\S+)', text, re.M)
    fail = re.search(r'^\s*SUPPLY_FAIL (.*)', text, re.M)
    launched, evidence = launch_evidence_of(text)
    if launched or not stage or stage.group(1) != 'supply_contract' or not fail:
        raise RuntimeError('the retained N2 transcript is not a zero-launch supply_contract refusal')
    n2_local = os.path.join(stage_dir, 'neg_static', 'D7B-N2.scs')
    if not os.path.isfile(n2_local):
        raise RuntimeError('the retained N2 deck %s is gone' % n2_local)
    got = sha_file(n2_local)
    if got != pub['deck_sha256']:
        raise RuntimeError('the retained N2 deck hashes to %s, the bundle says %s'
                           % (got[:12], pub['deck_sha256'][:12]))
    n2_text = u(io.open(n2_local, encoding='utf-8', newline='\n').read())
    parent_path = os.path.join(published_dir, 'decks', 'D7B-P30-C001.scs')
    parent = u(io.open(parent_path, encoding='utf-8', newline='\n').read())
    if 'Vss (vss 0) vsource dc=0' in n2_text:
        raise RuntimeError('the retained N2 deck still carries the VSS source it is meant to lose')
    if device_digest(n2_text) != device_digest(parent):
        raise RuntimeError('the retained N2 deck is not the delivered circuit: %s vs %s'
                           % (device_digest(n2_text), device_digest(parent)))
    if n2_text.count('vsource') != parent.count('vsource') - 1:
        raise RuntimeError('the N2 deck is not a single-statement removal from its positive twin')
    return {'run_id': '', 'case_id': 'D7B-N2', 'kind': 'static_supply_negative',
            'deck': n2_local,
            'detected': pub['detected'], 'rc': pub['rc'], 'stage': stage.group(1),
            'supply_fail': fail.group(1).replace(',', ';'), 'spectre_launches': 0,
            'deck_sha256': got, 'raw_sha256': '', 'verdict': pub['verdict'],
            'window': '', 'q_win_C': None, 'expected_dark_C': None, 'window_peak_A': None,
            'last_100ns_max_abs_A': None,
            'src_native_run': run_of_n2(text),
            'transcript': os.path.join(stage_dir, 'transcripts', cands[0]),
            'transcript_sha256': sha_file(os.path.join(stage_dir, 'transcripts', cands[0]))}


def run_of_n2(text):
    """the native run a carried refusal really came from, read out of the paths it printed"""
    m = re.search(r'/dd1_d7b/([^/\s]+)/neg_static', text or '')
    return m.group(1) if m else ''


def stage_ledger(ev_dir):
    """the per-pass ledger lives inside the pass's own staging directory

    Sharing one ledger file between passes is how the delivered round let a second run overwrite the
    first: the task-level cumulative record is `Account`, and a per-pass record must be able to say
    zero without erasing anybody else's history.
    """
    ledger = Ledger(os.path.join(ev_dir, 'process_ledger.csv'))
    ledger.flush()
    return ledger


def carry_rtl_reverify(dir_path, ev_dir):
    """the four-state re-verification of the trace edges, proved over before it is copied in

    The reviewer had to take the pulse edges the fall times were read from on the delivered document.
    Re-running the frozen RTL and the frozen testbench on this machine is the one way to show those
    edges come out of the design again, so the bundle ships the new VCDs and the table that compares
    them -- and a table that did not actually agree, or was built over a different RTL, is refused
    here rather than published and argued about later.
    """
    path = os.path.join(dir_path, 'rtl_reverify.csv')
    if not os.path.isfile(path):
        raise RuntimeError('--rtl-verify has no rtl_reverify.csv; run '
                           'scripts/dd1_d7b_r1_rtl_reverify.py first')
    rows = read_csv_rows(path)
    if not rows:
        raise RuntimeError('%s has a header and no rows' % path)
    if len(rows) > MAX_RTL_SIMULATIONS:
        raise RuntimeError('%s re-simulated %d trace cases, the task grants at most %d'
                           % (path, len(rows), MAX_RTL_SIMULATIONS))
    rtl, tb = sha256_of(RTL_PATH), sha256_of(TB_PATH)
    delivery_rows = []
    for r in rows:
        cid = r['case_id']
        if r['verdict'] != 'AGREE':
            raise RuntimeError('%s: the frozen RTL does not reproduce the delivered edges (%s)'
                               % (cid, r['mismatched_fields']))
        if r['rtl_sha256'] != rtl or r['tb_sha256'] != tb:
            raise RuntimeError('%s: the re-simulation ran over a different RTL or testbench than the '
                               'frozen one on disk' % cid)
        if not int(r['fields_compared']):
            raise RuntimeError('%s: the comparison names no field, so AGREE would prove nothing'
                               % cid)
        if r['new_vcd_sha256'] == r['accepted_vcd_sha256']:
            raise RuntimeError('%s: the new VCD is labelled with the native run\'s digest' % cid)
        src = os.path.join(dir_path, r['new_vcd'])
        if not os.path.isfile(src) or sha256_of(src) != r['new_vcd_sha256']:
            raise RuntimeError('%s: %s is missing or no longer hashes to the table\'s digest'
                               % (cid, r['new_vcd']))
        # .gitignore keeps `*.vcd` out of the repository, but the re-simulated bytes are the point of
        # the re-verification, so they are delivered under their own name plus `.txt`. iverilog writes
        # them with CRLF and Git normalises CRLF to LF on commit, which would leave every delivered
        # digest matching only the working copy and nothing matching a fresh checkout: the bytes are
        # delivered already normalised, and the two digests are recorded side by side so the
        # normalisation is a stated fact instead of a silent one.
        delivered = r['new_vcd'] + '.txt'
        with io.open(src, encoding='utf-8', newline='') as f:
            raw_text = f.read()
        normalised = raw_text.replace('\r\n', '\n')
        with io.open(os.path.join(ev_dir, delivered), 'w', encoding='utf-8', newline='') as f:
            f.write(normalised)
        raw_sha = sha256_of(src)
        if raw_sha != r['new_vcd_sha256']:
            raise RuntimeError('%s: %s is missing or no longer hashes to the table\'s digest'
                               % (cid, r['new_vcd']))
        if sha256_of(os.path.join(ev_dir, delivered)) != sha_txt(normalised):
            raise RuntimeError('%s: the delivered %s is not the bytes this pass wrote' % (cid,
                                                                                         delivered))
        if sha_txt(normalised.replace('\n', '\r\n')) != raw_sha:
            raise RuntimeError('%s: restoring the delivered bytes to CRLF does not give the '
                               'simulator\'s own file back' % cid)
        delivery_rows.append([cid, r['new_vcd'], delivered, raw_sha, sha_txt(normalised),
                              os.path.getsize(os.path.join(ev_dir, delivered)),
                              len(raw_text) - len(normalised), 'CRLF to LF (Git normalises this)'])
    shutil.copyfile(path, os.path.join(ev_dir, 'rtl_reverify.csv'))
    write_rows(os.path.join(ev_dir, 'rtl_reverify_delivery.csv'), delivery_rows,
               ['case_id', 'simulator_file', 'delivered_as', 'simulator_sha256',
                'delivered_sha256', 'delivered_bytes', 'bytes_removed', 'normalisation'])
    return len(rows)


GATE_RECORD_NAMES = ('measure_selftest', 'run_entry_selftest', 'trace_selftest',
                     'evidence_tamper_selftest', 'execution_guards')
LOCAL_PATH_RE = re.compile(r'(?i)([a-z]:[\\/]|/home/|/users/|\\\\)')


def carry_gate_records(dir_path, ev_dir):
    """the self-tests and the write-guard / fake-Link refusals, as the gates actually printed them

    A published bundle that claims its tools were tested has to carry the record of that testing,
    and the record has to be safe to commit: a gate whose transcript still names a local path would
    put this machine into the repository, and a gate that did not pass cannot be delivered as a pass.
    """
    path = os.path.join(dir_path, 'gate_records.csv')
    if not os.path.isfile(path):
        raise RuntimeError('--gate-records has no gate_records.csv; run '
                           'scripts/dd1_d7b_r1_gate_records.py first')
    rows = read_csv_rows(path)
    if len(rows) < len(GATE_RECORD_NAMES):
        raise RuntimeError('%s carries %d gate rows, the offline gates are %d'
                           % (path, len(rows), len(GATE_RECORD_NAMES)))
    named = set(r['gate'] for r in rows)
    if not set(GATE_RECORD_NAMES) <= named:
        raise RuntimeError('%s is missing the gates %s'
                           % (path, ', '.join(sorted(set(GATE_RECORD_NAMES) - named))))
    for r in rows:
        if r['verdict'] != 'PASS' or r['rc'] != '0':
            raise RuntimeError('gate %s did not pass (rc=%s, verdict=%s); a refused round cannot '
                               'deliver its own transcript as evidence' % (r['gate'], r['rc'],
                                                                           r['verdict']))
        if not int(r['printed_lines_kept']):
            raise RuntimeError('gate %s kept no printed line, so the PASS is not corroborated'
                               % r['gate'])
        for k, v in r.items():
            if LOCAL_PATH_RE.search(str(v)):
                raise RuntimeError('gate %s: the field %s still names a local path' % (r['gate'], k))
        for k in ('starts_spectre', 'opens_socket', 'writes_outside_ignored'):
            if r[k] != 'NO':
                raise RuntimeError('gate %s claims it %s, which this round forbids' % (r['gate'], k))
    shutil.copyfile(path, os.path.join(ev_dir, 'gate_records.csv'))
    return len(rows)


def remeasure_run(cases, mst, docs, decks, opts, run_id, out_root, account):
    """the whole round re-exported from retained bytes: this path never builds a Link at all"""
    before = account.counts()['confirmed']
    # the plan is proved to need no launch *before* any directory is created, so a refusal cannot
    # leave a half-built bundle sitting where a reviewer might read it as an export
    reuse_map = resolve_reuse(opts.reuse, decks, mst, opts.published_dir)
    need = set(c['case_id'] for c in cases)
    if not need <= set(reuse_map):
        raise RuntimeError('--remeasure has no retained bytes for %s; the case would need a launch, '
                           'which this round does not authorise'
                           % ', '.join(sorted(need - set(reuse_map))))
    ev_dir = os.path.join(out_root, 'evidence', run_id)
    for sub in ('', 'pwl', 'decks', 'transcripts'):
        if not os.path.isdir(os.path.join(ev_dir, sub)):
            os.makedirs(os.path.join(ev_dir, sub))
    ledger = stage_ledger(ev_dir)
    rows = []
    charge_index = []
    results = {}
    negative_rows = []
    for cid in sorted(reuse_map):
        account.note(cid, 'reused_measurement', run_id,
                     're-measured offline from native run %s launch %s'
                     % (reuse_map[cid]['src_native_run'], reuse_map[cid]['launch_id']))
    print('REMEASURE_CASES %d, all from retained bytes' % len(reuse_map))
    cal = None
    stopped = ''
    for c in cases:
        cal, why = remeasure_case(c, reuse_map[c['case_id']], cal, docs, run_id, ev_dir, rows,
                                  charge_index, results, negative_rows)
        if why:
            stopped = why
            break
    if opts.n2_from:
        n2 = carried_negative(opts.n2_from, opts.published_dir)
        n2['run_id'] = run_id
        negative_rows.append(n2)
        shutil.copyfile(n2['deck'], os.path.join(ev_dir, 'decks', 'D7B-N2.scs'))
        shutil.copyfile(n2['transcript'], os.path.join(
            ev_dir, 'transcripts', 'carried_%s_%s' % (n2['src_native_run'],
                                                      os.path.basename(n2['transcript']))))
        account.note('D7B-N2', 'static_negative_carried', run_id,
                     'refusal carried from the retained transcript, 0 launches')
    else:
        print('N2_NOT_CARRIED --n2-from was not given; the supply refusal of this round is not '
              'claimed')
    if opts.rtl_verify:
        n = carry_rtl_reverify(opts.rtl_verify, ev_dir)
        print('RTL_REVERIFY_CARRIED %d trace case(s), byte-for-byte from %s' % (n, opts.rtl_verify))
    else:
        print('RTL_REVERIFY_NOT_CARRIED no --rtl-verify table; the published bundle will be refused '
              'until the frozen RTL has been re-run over the trace edges')
    if opts.gate_records:
        n = carry_gate_records(opts.gate_records, ev_dir)
        print('GATE_RECORDS_CARRIED %d gate row(s), all PASS, from %s' % (n, opts.gate_records))
    else:
        print('GATE_RECORDS_NOT_CARRIED no --gate-records table; the bundle cannot claim its '
              'self-tests and write-guard refusals were run')
    res = write_bundle(run_id, cases, mst, docs, decks, out_root, ev_dir, rows, charge_index,
                       results, negative_rows, reuse_map, cal, ledger, account,
                       mode='remeasure',
                       root='<none: offline re-measurement, no guest was touched>',
                       stopped=stopped, reused=True, frozen=local_frozen_digests())
    after = account.counts()['confirmed']
    print('REMEASURE_ACCOUNT before=%d after=%d' % (before, after))
    if after != before or ledger.used:
        raise RuntimeError('the offline re-measurement spent %d launch(es); it is authorised for none'
                           % (after - before))
    print('NEW_SPECTRE_LAUNCHES 0')
    return res


def local_frozen_digests():
    """the frozen runner tools as the object store holds them, without touching a guest"""
    out = {}
    for rel in FROZEN_RUNNER:
        out[os.path.basename(rel)] = sha_txt(git_blob(BASE_SHA, rel))
    return out


def write_bundle(run_id, cases, mst, docs, decks, out_root, ev_dir, rows, charge_index, results,
                 negative_rows, reuse_map, cal, ledger, account, mode, root, stopped, reused,
                 frozen=None):
    """the one place a staged bundle is written, so a live run and a re-measurement cannot drift"""
    write_rows(os.path.join(ev_dir, 'cases.csv'), rows, CASE_HDR)
    write_convergence(os.path.join(ev_dir, 'convergence.csv'), results, cases, run_id)
    write_negative(os.path.join(ev_dir, 'negative.csv'), negative_rows)
    write_index(os.path.join(ev_dir, 'charge_index.csv'), charge_index, run_id,
                enforce_accepted_identity=(mode == 'remeasure'))
    account.flush_account()
    shutil.copyfile(account.path, os.path.join(ev_dir, 'launch_account.csv'))
    environment = {'run_id': run_id, 'mode': mode, 'task_root': root,
                   'guest_host': ('<not touched>' if mode == 'remeasure' else '<redacted>'),
                   'python_local': sys.version.split()[0], 'base_sha': BASE_SHA,
                   'accepted_sha': ACCEPTED_SHA, 'repair_base_sha': REPAIR_BASE_SHA,
                   'repair_payload_sha': REPAIR_PAYLOAD_SHA,
                   'frozen_tools': (frozen or {}),
                   'masters': [{'name': m['name'], 'repo_sha256': m['repo_sha256'],
                                'sent_sha256': m['sent_sha256'], 'stripped': len(m['removed']),
                                'stripped_lines': m['removed']} for m in mst],
                   'launches_used': ledger.used, 'budget': LAUNCH_BUDGET, 'stopped': stopped,
                   'launch_account': account.counts(),
                   'launch_account_origin': account.seed_origin,
                   'ceiling': account.ceiling,
                   'new_spectre_launches_this_pass': ledger.used,
                   'reused_cases': sorted(reuse_map),
                   'reused_from': (REPAIR_BASE_SHA if reused else ''),
                   'measurement_source_sha256': MS_SOURCE_SHA,
                   'runner_source_sha256': RUN_SOURCE_SHA,
                   'trace_source_sha256': TRACE_SOURCE_SHA,
                   # which re-checker the bundle was written to be read by, so a later reviewer can
                   # tell whether a passing report came from these bytes or from a changed checker
                   'evidence_check_source_sha256': _source_sha('dd1_d7b_evidence_check.py')}
    write_json(os.path.join(ev_dir, 'environment.json'), environment)
    traces = {}
    for cid, d in docs.items():
        traces[cid] = {'vcd': d['facts']['vcd'], 'vcd_sha256': d['facts']['vcd_sha256'],
                       'header': d['facts']['header'], 'shift_ps': d['shift_ps'],
                       'end_ps': d['facts']['end_ps'], 'tick_lead_ps': d['facts']['tick_lead_ps'],
                       'ramp_ns': dict((c2['case_id'], c2['ramp_ns']) for c2 in cases
                                       if c2.get('trace_case') == cid)}
    write_json(os.path.join(ev_dir, 'source_identity.json'),
               {'run_id': run_id, 'base_sha': BASE_SHA, 'accepted_rtl_sha': ACCEPTED_SHA,
                'repair_base_sha': REPAIR_BASE_SHA, 'traces': traces,
                'native_runs': dict((cid, {'native_run_id': v['src_native_run'],
                                           'dut_launch_id': v['launch_id'],
                                           'preflight_launch_id': v['preflight_launch_id'],
                                           'deck_sha256': v['deck_sha256'],
                                           'pwl_sha256': v['pwl_sha256'],
                                           'raw_sha256': v['raw_sha256'],
                                           'log_sha256': v['log_sha256'],
                                           'transcript_sha256': sha_file(v['transcript']),
                                           'conditions': v['conditions'],
                                           'identity_notes': v['identity_notes'],
                                           'retained_dir': v['src_dir'].replace(os.sep, '/')})
                                    for cid, v in reuse_map.items()),
                'measurement_source_sha256': MS_SOURCE_SHA,
                'runner_source_sha256': RUN_SOURCE_SHA})
    log_dir = os.path.join(out_root, 'transcripts')
    if mode == 'remeasure':
        # a re-measurement touches no guest, so it carries no transcripts of its own. The transcripts
        # that prove where each reused number came from are copied in under the native run they name.
        for cid in sorted(reuse_map):
            src = reuse_map[cid]['transcript']
            shutil.copyfile(src, os.path.join(ev_dir, 'transcripts',
                                              'reused_%s_%s' % (reuse_map[cid]['src_native_run'],
                                                                os.path.basename(src))))
    elif os.path.isdir(log_dir):
        for src in os.listdir(log_dir):
            shutil.copyfile(os.path.join(log_dir, src), os.path.join(ev_dir, 'transcripts', src))
    for cid in sorted(decks):
        # a reused row ships the deck and PWL bytes that actually produced its samples: the rebuilt
        # text differs only by the run identity comment, and a bundle that swapped those bytes would
        # no longer describe the run it claims to
        info = reuse_map.get(cid)
        if info:
            shutil.copyfile(info['deck'], os.path.join(ev_dir, 'decks', '%s.scs' % cid))
            shutil.copyfile(info['pwl'], os.path.join(ev_dir, 'pwl', '%s_pwl.txt' % cid))
            continue
        with io.open(os.path.join(ev_dir, 'decks', '%s.scs' % cid), 'w', encoding='utf-8',
                     newline='\n') as f:
            f.write(u(decks[cid]['deck']))
        with io.open(os.path.join(ev_dir, 'pwl', '%s_pwl.txt' % cid), 'w', encoding='utf-8',
                     newline='\n') as f:
            f.write(u(pwl_text(decks[cid]['points'])))
    write_reconcile(ev_dir, account)
    print('EVIDENCE_STAGED %s mode=%s rows=%d launches_this_pass=%d account=%s'
          % (ev_dir, mode, len(rows), ledger.used, account.counts()))
    return {'ev_dir': ev_dir, 'run_id': run_id, 'rows': rows, 'cal': cal, 'ledger': ledger,
            'account': account, 'stopped': stopped}


def write_reconcile(ev_dir, account):
    """launches_reconcile.csv rebuilt from the account, so the sum can be checked not asserted

    A re-measurement starts no process, so its own row is all zeroes. The history comes from the
    account file, which is seeded from the delivered bundle's own reconcile table, and each run
    keeps the preflight/DUT split it was recorded with.
    """
    per = {}
    for r in account.rows:
        if r['state'] not in ('CONFIRMED', 'COMPLETED', 'UNCERTAIN'):
            continue
        key = r['run_id'] or 'unattributed'
        slot = per.setdefault(key, {'preflight': 0, 'dut': 0, 'other': 0})
        slot[r['role'] if r['role'] in ('preflight', 'dut') else 'other'] += 1
    rows = []
    for key in sorted(per):
        s = per[key]
        n = s['preflight'] + s['dut'] + s['other']
        rows.append([key, s['preflight'], n, s['dut'], 'YES', n, 'carried in the task account'])
    rows.append([os.path.basename(ev_dir), 0, 0, 0, 'YES', 0,
                 'this pass started no process: an offline re-measurement of retained bytes'])
    total = sum(int(r[5]) for r in rows)
    rows.append(['TOTAL', sum(int(r[1]) for r in rows), total, sum(int(r[3]) for r in rows), '',
                 total, '%d launches accounted against a ceiling of %d'
                 % (total, account.ceiling)])
    # the accepted bundle called this column in_delivered_set and said YES for probe directories
    # that were never delivered; what is actually true of every row here is that the task account
    # carries its processes toward the 59
    write_rows(os.path.join(ev_dir, 'launches_reconcile.csv'), rows,
               ['task_root_dir', 'preflight_logs', 'total_logs', 'dut_logs',
                'carried_in_task_account', 'processes_counted_against_ceiling', 'note'])
    return total


OVERBUDGET_REFUSAL = 'LAUNCH_CEILING_REACHED'


def plan_launches(cases, reuse_map=None):
    """how many processes the plan still needs: one rail preflight plus one DUT per live case"""
    reuse_map = reuse_map or {}
    return (PREFLIGHT_PER_DUT + 1) * len([c for c in cases if c['case_id'] not in reuse_map])


def build_static_negative(mst, decks, out_root, run_id):
    """N2: a legal deck with its VSS independent source removed, in its own directory"""
    base = decks['D7B-P30-C001']['deck']
    removed = base.replace('Vss (vss 0) vsource dc=0\n', '')
    if removed == base:
        raise RuntimeError('the static negative found no VSS source to remove')
    d = os.path.join(out_root, 'neg_static')
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, 'D7B-N2.scs')
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(removed))
    return {'local': path, 'sha256': sha_txt(removed), 'run_id': run_id}


def run_static_negative(link, ledger, n2, run_id, mst, out_root, account=None):
    remote_dir = '%s/neg_static' % link.root
    link.run('mkdir -p %s' % remote_dir, 120, 'mkdir-N2')
    for m in mst:
        link.push(os.path.join(out_root, 'masters', m['name']),
                  '%s/%s' % (remote_dir, m['name']), 'master')
    link.push(n2['local'], '%s/D7B-N2.scs' % remote_dir, 'deck')
    row = ledger.begin('D7B-N2', 'static_negative', n2['sha256'], '')
    before = ledger.used
    script = ('export PROJ=%s PDK_ENV=%s\nbash %s/scripts/tb_preflight.sh %s/D7B-N2.scs %s n2 "%s"\n'
              % (link.root, GUEST_PDK_ENV, link.root, remote_dir, EXPECTED_VDD, SUPPLY_MAP))
    rc, text = link.run(script, 600, 'n2')
    launched = ledger.finish(row, rc, text, refusal=tail_reason(text))
    stage = re.search(r'^PREFLIGHT_STAGE=(\S+)', text or '', re.M)
    res = re.search(r'^SUPPLY_FAIL (.*)', text or '', re.M)
    ok = (rc != 0 and stage and stage.group(1) == 'supply_contract' and launched == 0
          and ledger.used == before)
    if account is not None:
        # a refusal that started nothing is a fact about the gate, not a launch: it is recorded in the
        # same account so nobody can read the row count as a spent process
        account.note('D7B-N2', 'static_negative', run_id,
                     'supply_contract refusal rc=%s, launched=%d' % (rc, launched), rc=rc)
    return {'run_id': run_id, 'case_id': 'D7B-N2', 'kind': 'static_supply_negative',
            'detected': 'YES' if ok else 'NO', 'rc': rc, 'stage': stage.group(1) if stage else '',
            'supply_fail': (res.group(1) if res else '').replace(',', ';'),
            'spectre_launches': launched, 'deck_sha256': n2['sha256'],
            'verdict': 'EXPECTED_REFUSAL / SUPPLY_CONTRACT_DETECTED' if ok else 'NOT_DETECTED'}


def tail_reason(text):
    keep = [l for l in (text or '').strip().split('\n') if l.strip()][-3:]
    return ' | '.join(keep)[:180].replace(',', ';')


def write_json(path, obj):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, indent=1, sort_keys=True, default=str))


def write_index(path, metas, run_id, enforce_accepted_identity=True):
    rows = []
    tally = {}
    for m in metas:
        if not m:
            continue
        ref = accepted_bundle_series(m['base'])
        if ref is None:
            verdict = NEW_SERIES_MARK
        elif ref == (int(m['total_rows']), m['series_sha256']):
            verdict = 'IDENTICAL_BYTES'
        else:
            verdict = 'DIFFERENT_SAMPLES'
            if enforce_accepted_identity:
                raise RuntimeError('%s: the re-emitted samples are not the accepted bundle%s (%d '
                                   'rows / %s against %d rows / %s)'
                                   % (m['base'], ACCEPTED_BUNDLE_NAME, int(m['total_rows']),
                                      m['series_sha256'][:16], ref[0], ref[1][:16]))
        tally[verdict] = tally.get(verdict, 0) + 1
        for p in m['parts']:
            rows.append([run_id, m['base'], p['part'], p['rows'], p['bytes'], p['first_row'],
                         p['last_row'], p['sha256'], m['total_rows'], m['series_sha256'],
                         m.get('recompute_q_win_C', ''),
                         (ACCEPTED_BUNDLE_NAME if ref is not None else ''),
                         ('' if ref is None else str(ref[0])),
                         ('' if ref is None else ref[1]), verdict])
    write_rows(path, rows, ['run_id', 'base', 'part', 'rows', 'bytes', 'first_row', 'last_row',
                            'sha256', 'total_rows', 'series_sha256', 'recompute_q_win_C',
                            'accepted_bundle', 'accepted_series_rows', 'accepted_series_sha256',
                            'series_vs_accepted_bundle'])
    print('CHARGE_SERIES_VS_ACCEPTED %s'
          % ' '.join('%s=%d' % kv for kv in sorted(tally.items())))


ACCEPTED_BUNDLE = {}


def accepted_bundle_series(base):
    """the accepted DATA-7B bundle's own sample lines for one series, as (rows, sha256)

    R1 re-emits its shards from the retained raw, so the bundle has to say whether those are the same
    bytes the accepted run already shipped or new ones. The answer is read off dd1_d7b_r11_main's
    index order and file text, so any reviewer comparing the two directories gets the same digest.
    """
    if 'by_base' not in ACCEPTED_BUNDLE:
        by = {}
        idx = os.path.join(HISTORICAL_EVIDENCE, 'charge_index.csv')
        if os.path.isfile(idx):
            for r in read_csv_rows(idx):
                by.setdefault(r['base'], []).append(r)
            for base2 in by:
                by[base2].sort(key=lambda r: r['part'])
        ACCEPTED_BUNDLE['by_base'] = by
        ACCEPTED_BUNDLE['series'] = {}
    if base in ACCEPTED_BUNDLE['series']:
        return ACCEPTED_BUNDLE['series'][base]
    parts = ACCEPTED_BUNDLE['by_base'].get(base)
    out = None
    if parts:
        lines = []
        for r in parts:
            path = os.path.join(HISTORICAL_EVIDENCE, r['part'])
            if not os.path.isfile(path):
                raise RuntimeError('%s is listed by the accepted bundle but missing from it'
                                   % r['part'])
            with io.open(path, encoding='utf-8', newline='\n') as f:
                text = f.read()
            lines.extend([l for l in text.split('\n', 1)[1].split('\n') if l])
        out = (len(lines), sha_txt(''.join(l + '\n' for l in lines)))
    ACCEPTED_BUNDLE['series'][base] = out
    return out


def write_convergence(path, results, cases, run_id):
    rows = []
    for c in cases:
        if c['role'] != 'convergence':
            continue
        parent = c['reuse_of']
        for wname in c['windows'].split(';'):
            a = results.get((parent, wname))
            b = results.get((c['case_id'], wname))
            if not a or not b:
                rows.append([run_id, c['case_id'], wname, parent, '', '', '', '', '',
                             'BLOCKED_MISSING_PARENT'])
                continue
            dq = abs(b['q_win']['q'] - a['q_win']['q'])
            lim_q = 0.01 * b['q_lsb_C']
            dp = abs((b['window_peak']['value'] or 0.0) - (a['window_peak']['value'] or 0.0))
            lim_p = max(0.05 * abs(b['window_peak']['value'] or 0.0), 0.15e-6)
            dt = None
            if isinstance(a['de_fall_50_ps'], (int, float)) and isinstance(
                    b['de_fall_50_ps'], (int, float)):
                dt = abs(b['de_fall_50_ps'] - a['de_fall_50_ps'])
            ok = dq <= lim_q and dp <= lim_p and (dt is None or dt <= 500)
            rows.append([run_id, c['case_id'], wname, parent, fmt_num(dq, 1e12, '%.6f'),
                         fmt_num(lim_q, 1e12, '%.6f'), fmt_num(dp, 1e6, '%.6f'),
                         fmt_num(lim_p, 1e6, '%.6f'),
                         fmt_num(dt, 1e-3, '%.4f') if dt is not None else 'NOT_FOUND_BOTH',
                         'CONVERGED' if ok else 'NUMERICAL_NOT_CONVERGED'])
    write_rows(path, rows, ['run_id', 'case_id', 'window', 'parent_case', 'delta_q_pC',
                            'limit_q_pC', 'delta_peak_uA', 'limit_peak_uA', 'delta_edge_ns',
                            'verdict'])


def write_negative(path, rows):
    # the peak columns are microampere and are named that way: the delivered table printed a microamp
    # value under an `_A` header, which is the unit error DATA-7B-R1 was told to correct
    hdr = ['run_id', 'case_id', 'kind', 'window', 'detected', 'q_win_C', 'expected_dark_C',
           'window_peak_uA', 'last_100ns_max_abs_uA', 'rc', 'stage', 'supply_fail',
           'spectre_launches', 'deck_sha256', 'raw_sha256', 'launch_id', 'src_native_run',
           'transcript_sha256', 'verdict']
    out = []
    for r in rows:
        out.append([r.get('run_id', ''), r.get('case_id', ''), r.get('kind', 'dynamic_wiring'),
                    r.get('window', ''), r.get('detected', ''), fmt_num(r.get('q_win_C'), 1.0),
                    fmt_num(r.get('expected_dark_C'), 1.0), fmt_num(r.get('window_peak_A'), 1e6),
                    fmt_num(r.get('last_100ns_max_abs_A'), 1e6), r.get('rc', ''),
                    r.get('stage', ''), r.get('supply_fail', ''), r.get('spectre_launches', ''),
                    r.get('deck_sha256', ''), r.get('raw_sha256', ''), r.get('launch_id', ''),
                    r.get('src_native_run', ''), r.get('transcript_sha256', ''),
                    r.get('verdict', '')])
    write_rows(path, out, hdr)


PUBLISH_BUDGET_ONLY = ('BUDGET_RESPECTED',)


def listing_of(root):
    out = {}
    for base, _dirs, names in os.walk(root):
        for name in names:
            p = os.path.join(base, name)
            out[os.path.relpath(p, root).replace(os.sep, '/')] = sha_file(p)
    return out


def publish(ev_dir, run_id):
    """move a fully validated bundle into a path that must not exist yet; nothing is overwritten

    The gate is the complete semantic re-check of the staged bytes, not a file-existence glance. A
    bundle with any non-budget failure stays exactly where it is, and the formal directory is
    re-listed to prove the refusal changed nothing in it. The historical budget violation keeps its
    own failing status and is the single check allowed to be red here -- it cannot hide behind being
    red, and it cannot be made green by widening the ceiling.
    """
    import dd1_d7b_evidence_check as EC
    if not RUN_ID_RE.match(run_id or ''):
        raise RuntimeError('run id %r is not rYYYYMMDD_HHMMSS_xxxxxx' % run_id)
    ev_dir = os.path.abspath(ev_dir)
    if not os.path.isdir(ev_dir):
        raise RuntimeError('%s is not a staged bundle' % ev_dir)
    res = EC.check_dir(ev_dir)
    blocking = [f for f in res['failures'] if f not in PUBLISH_BUDGET_ONLY]
    if res['failures']:
        print('PUBLISH_CHECK_FAILURES %s' % ' '.join(res['failures']))
    if blocking:
        raise RuntimeError('the staged bundle %s is refused: %s' % (ev_dir, ', '.join(blocking)))
    if not res['file_count']:
        raise RuntimeError('%s holds no files, so publishing it would publish nothing' % ev_dir)
    target = os.path.join(PROJ, 'results', 'evidence', PUBLISHED_PREFIX + run_id)
    if os.path.exists(target):
        raise RuntimeError('%s already exists: refusing to overwrite published evidence' % target)
    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    before = listing_of(parent)
    want = listing_of(ev_dir)
    shutil.move(ev_dir, target)
    got = listing_of(target)
    if got != want:
        raise RuntimeError('%d file(s) changed while being published; the bundle is not trusted'
                           % len([k for k in set(got) | set(want) if got.get(k) != want.get(k)]))
    added = [k for k in got if k not in before]
    print('PUBLISHED_TARGET %s files=%d bytes=%d new_under_results=%d'
          % (target, len(got), sum(os.path.getsize(os.path.join(target, k.replace('/', os.sep)))
                                   for k in got), len(added)))
    if res['failures']:
        print('PUBLISHED_WITH_DISCLOSED_FAILURE %s (kept as an independent status, not repaired)'
              % ' '.join(res['failures']))
    return target

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
