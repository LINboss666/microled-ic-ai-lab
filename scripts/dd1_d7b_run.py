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
BRANCH = 'poc/data-pwm-d7b'

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
class Ledger(object):
    """a row exists before the launch; a failed launch still costs one"""

    HDR = ['launch_id', 'case_id', 'role', 'state', 'requested_utc', 'ended_utc', 'rc',
           'spectre_line', 'deck_sha256', 'pwl_sha256', 'raw_sha256', 'log_sha256', 'refusal',
           'launches_used_after']

    def __init__(self, path):
        self.path = path
        self.rows = []
        self.used = 0

    def begin(self, case_id, role, deck_sha, pwl_sha):
        self.rows.append({'launch_id': 'L%03d' % (len(self.rows) + 1), 'case_id': case_id,
                          'role': role, 'state': 'REQUESTED',
                          'requested_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                          'ended_utc': '', 'rc': '', 'spectre_line': '', 'deck_sha256': deck_sha,
                          'pwl_sha256': pwl_sha, 'raw_sha256': '', 'log_sha256': '',
                          'refusal': '', 'launches_used_after': str(self.used)})
        self.write()
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
        self.write()
        return launched

    def write(self):
        with io.open(self.path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(','.join(self.HDR) + '\n')
            for r in self.rows:
                f.write(','.join(str(r.get(k, '')) for k in self.HDR) + '\n')


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
            'de_fall_50_ns', 'de_b_fall_50_ns', 'settled_status', 'settled_ns', 'off_status',
            'off_ns', 'last_100ns_max_abs_A', 'probe_direction_suspect', 'verdict', 'reasons']

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
    win = {'current': cur, 'de': den, 'de_b': deb, 't0_ps': t0, 't1_ps': t1,
           'de_declared_flat_zero': (series.get('data_en') is None),
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
    doc = json.loads(u(io.open(os.path.join(PROJ, 'review', 'scratch', 'traceout',
                                            'trace_D7B-P30-C001.json'), encoding='utf-8').read()))
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
                             't0_ps': 0, 't1_ps': 30000, 'expected_intervals': 1.0},
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
    print('D7B_RUN_SELFTEST: %s (%d checks)' % ('FAIL' if bad else 'PASS', n))
    for b in bad:
        print('SELFTEST_BAD %s' % b)
    return 1 if bad else 0


def main(argv):
    ap = optparse.OptionParser(usage='%prog [--selftest|--dry|--run|--supply-negative] [options]')
    ap.add_option('--selftest', action='store_true')
    ap.add_option('--dry', action='store_true')
    ap.add_option('--run', action='store_true')
    ap.add_option('--supply-negative', action='store_true')
    ap.add_option('--check-evidence', default='')
    ap.add_option('--publish', action='store_true')
    ap.add_option('--static-probe', action='store_true')
    ap.add_option('--only', default='')
    ap.add_option('--cal-from', default='')
    ap.add_option('--reuse', default='')
    ap.add_option('--write-manifest', default='')
    ap.add_option('--expect', type='int', default=24)
    ap.add_option('--run-id', default='')
    ap.add_option('--trace-dir', default=os.path.join(PROJ, 'review', 'scratch', 'traceout'))
    ap.add_option('--out', default=os.path.join(PROJ, 'review', 'scratch', 'd7b_stage'))
    opts, _args = ap.parse_args(argv)
    if opts.write_manifest:
        return write_manifest_main(opts.write_manifest)
    if opts.selftest:
        return selftest_main()
    if opts.check_evidence:
        import dd1_d7b_evidence_check as EC
        return EC.main_dir(opts.check_evidence)
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
    if opts.run and not (os.environ.get('RUN') == '1' and
                         os.environ.get('QODER_SIM_AUTHORISED') == '1'):
        print('D7B_REFUSED run=%s authorisation=%s: RUN=1 AND QODER_SIM_AUTHORISED=1 are both '
              'required before any Spectre launch'
              % (os.environ.get('RUN') or 'unset', os.environ.get('QODER_SIM_AUTHORISED') or 'unset'))
        return 5
    if 2 * len(cases) > LAUNCH_BUDGET:
        print('D7B_REFUSED the plan needs %d launches, the budget is %d'
              % (2 * len(cases), LAUNCH_BUDGET))
        return 5
    mst = masters()
    run_id = opts.run_id or time.strftime('r%%Y%%m%%d_%%H%%M%%S', time.localtime())
    out_root = os.path.abspath(opts.out)
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
    print('STATIC_GATES: PASS (%d cases, %d masters, 7 devices, %d launches planned of a %d budget)'
          % (len(cases), len(mst), 2 * len(cases), LAUNCH_BUDGET))
    _d, decks = build_all(cases, mst, opts.trace_dir, out_root, run_id)
    for cid in sorted(decks):
        stage_deck({'case_id': cid}, decks[cid]['deck'], decks[cid]['points'], out_root)
    print('DECKS_BUILT %d decks in %s' % (len(decks), os.path.join(out_root, 'decks')))
    for cid in sorted(decks):
        print('  %s deck=%s stop_ns=%.1f pwl_points=%d'
              % (cid, decks[cid]['deck_sha256'][:12], decks[cid]['stop_ps'] / 1000.0,
                 len(decks[cid]['points'])))
    if opts.supply_negative:
        print('D7B_SUPPLY_NEGATIVE use --supply-negative on the guest path: it stages the deck with '
              'the VSS source removed in its own directory and runs the frozen checker only')
        return 0
    if opts.dry:
        print('D7B_DRY: PASS (decks and gates only, 0 Spectre launches)')
        return 0
    if opts.static_probe:
        return static_probe(cases, mst, decks, run_id, out_root, log_dir)
    res = native_run(cases, mst, docs, decks, opts, run_id, out_root, log_dir)
    rows = res['rows']
    verdicts = {}
    for r in rows:
        v = r[CASE_HDR.index('verdict')]
        verdicts[v] = verdicts.get(v, 0) + 1
    print('RUN_ID %s' % res['run_id'])
    print('LEDGER_LAUNCHES %d of %d' % (res['ledger'].used, LAUNCH_BUDGET))
    print('EVIDENCE_ROWS %d %s' % (len(rows), ' '.join('%s=%d' % kv for kv in sorted(verdicts.items()))))
    elec = [r for r in rows if r[CASE_HDR.index('role')] in
            ('normal', 'safety', 'convergence', 'sensitivity')]
    fails = [r for r in elec if r[CASE_HDR.index('verdict')] == 'FAIL']
    print('PWM_CURRENT_FEASIBILITY_TT %s'
          % ('REWORK_REQUIRED' if fails else ('PASS' if elec else 'NOT_VERIFIED')))
    print('EVIDENCE_STATUS %s' % ('COMPLETE' if res['ledger'].used and not res['stopped'] else
                                 'PARTIAL'))
    if res['stopped']:
        print('STOPPED %s' % res['stopped'])
    if opts.publish:
        try:
            print('PUBLISHED %s' % publish(res['ev_dir'], res['run_id']))
        except RuntimeError as exc:
            print('PUBLISH_REFUSED %s' % exc)
            return 6
    else:
        print('PUBLISHED no (--publish was not given; the bundle stays in ignored scratch)')
    return 0

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
             'band_min_A': bmin, 'band_max_A': bmax},
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


CHARGE_HDR = ['run_id', 'case_id', 'window', 't_ps', 'iout_A', 't_ns', 'iout_uA',
              'time_quantum_ps']   # part -> case/deck/raw binding lives in charge_index.csv
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
    rows = [[run_id, c['case_id'], w['window'], '%.17g' % t, '%.12g' % v, '%.6f' % (t * 1e-3),
             '%.6f' % (v * 1e6), '%.6g' % series.get('_time_quantum_ps', 0.0)]
            for t, v in cur]
    meta = shard_samples(rows, CHARGE_HDR, 'charge_%s_%s' % (c['case_id'], w['window']),
                         ev_dir)
    # the delivered slice must reproduce the same charge on its own bytes
    chk = MS.integrate([(float(r[3]), float(r[4])) for r in rows], t0, t1, 'slice re-read')
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
         'de_rise_50_ns': fmt_num(out.get('de_rise_50_ps'), 1e-3),
         'de_fall_50_ns': fmt_num(out.get('de_fall_50_ps'), 1e-3),
         'de_b_fall_50_ns': fmt_num(out.get('de_b_rise_50_ps'), 1e-3),
         'settled_status': (out.get('settled') or {}).get('status', ''),
         'settled_ns': fmt_num((out.get('settled') or {}).get('settled_ps'), 1e-3),
         'off_status': (out.get('turn_off') or {}).get('status', ''),
         'off_ns': fmt_num((out.get('turn_off') or {}).get('off_ps'), 1e-3),
         'last_100ns_max_abs_A': fmt_num(out.get('last_100ns_max_abs_A'), 1.0),
         'probe_direction_suspect': str(bool(out.get('probe_direction_suspect'))),
         'verdict': verdict, 'reasons': '; '.join(reasons).replace(',', ';')[:220]}
    return [r.get(k, '') for k in CASE_HDR]


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


def static_probe(cases, mst, decks, run_id, out_root, log_dir):
    """every deck through the frozen static gates; this must start zero simulators"""
    root = '%s/static_%s' % (GUEST_ROOT, run_id)
    link = Link(GUEST_HOST, root, log_dir)
    ledger = Ledger(os.path.join(out_root, 'static_probe_ledger.csv'))
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
        if cid in reuse_map:
            info = reuse_map[cid]
            ids = {'deck_sha256': info['deck_sha256'], 'pwl_sha256': info['pwl_sha256'],
                   'trace_sha256': docs[cid]['facts']['vcd_sha256'], 'raw_sha256': info['raw_sha256'],
                   'log_sha256': info['log_sha256'], 'section': 'tt', 'temp': '27.0'}
            series, _t = psf_series(info['psf'])
            by_window = dict((x['window'], x) for x in docs[cid]['windows'])
            for wname in c['windows'].split(';'):
                w = by_window[wname]
                out = measure_one(c, w, series, cal['ical_A'], 'REUSED', ids, run_id)
                verdict, reasons = MS.judge(out)
                results[(cid, wname)] = out
                rows.append(case_row(run_id, c, w, out, verdict,
                                     reasons + ['measured from the retained run %s at %s; no process '
                                                'was started for it this pass'
                                                % (info['src_run'], info['psf'].replace(os.sep, '/'))],
                                     ids, 'REUSED'))
                charge_index.append(emit_charge_slice(series, c, w, out, run_id, ids, ev_dir))
                emit_edge_slice(series, c, w, out, run_id, ev_dir)
                trace_edge_table(ev_dir, run_id, docs[cid], c)
            print('DUT %s REUSED from %s launches=%d/%d'
                  % (cid, info['src_run'], ledger.used, LAUNCH_BUDGET))
            continue
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
    print('STATIC_PROBE %s (%d decks, %d Spectre launches, N2 refused=%s)'
          % ('FAIL' if bad else 'PASS', len(cases), ledger.used, refused))
    for b in bad[:6]:
        print('  STATIC_BAD %s' % b)
    return 1 if (bad or not refused or ledger.used != 0) else 0


def reuse_calibration(src_dir, run_id):
    """reuse a calibration that really ran, keeping its own run_id and digests visible"""
    rows = {}
    with io.open(os.path.join(src_dir, 'calibration.csv'), encoding='utf-8', newline='') as f:
        hdr = f.readline().strip().split(',')
        for line in f:
            if line.strip():
                d = dict(zip(hdr, [v.strip() for v in line.rstrip('\r\n').split(',')]))
                rows[d['quantity']] = d
    picked = None
    with io.open(os.path.join(src_dir, 'cases.csv'), encoding='utf-8', newline='') as f:
        hdr = f.readline().strip().split(',')
        for line in f:
            if line.strip():
                d = dict(zip(hdr, [v.strip() for v in line.rstrip('\r\n').split(',')]))
                if d['role'] == 'calibration':
                    picked = d
    if not picked:
        raise RuntimeError('no calibration row in %s' % src_dir)
    ical = float(rows['Ical_A']['value_A'])
    off = float(rows['OFF_baseline_max_abs_A']['value_A'])
    tail = float(rows['CAL_tail_max_abs_A']['value_A'])
    reasons = []
    if abs(ical - 15e-6) > 15e-6 * 0.05:
        reasons.append('Ical %r is outside 15 uA +/- 5 pct' % ical)
    if off > 0.15e-6:
        reasons.append('the OFF baseline max |I| is %r' % off)
    if tail > 0.15e-6:
        reasons.append('the calibration tail max |I| is %r' % tail)
    return {'ical_A': ical, 'ok': not reasons, 'reasons': reasons, 'rows': [],
            'band_min_A': float(rows['Ical_A']['band_min_A']),
            'band_max_A': float(rows['Ical_A']['band_max_A']),
            'off_max_abs_A': off, 'tail_max_abs_A': tail,
            'reused_from_run': picked['run_id'],
            'reused_from_dir': src_dir.replace(os.sep, '/'),
            'ids': {'deck_sha256': picked['deck_sha256'], 'pwl_sha256': picked['pwl_sha256'],
                    'raw_sha256': picked['raw_sha256'], 'log_sha256': picked['log_sha256'],
                    'trace_sha256': 'declared static long-pulse calibration bench - not an RTL trace'},
            'launches': 0, 'run_id': run_id}


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


def parse_reuse(spec):
    # case_id=<dir> pairs: a real earlier run whose bytes are still on disk, re-measured offline
    out = {}
    for pair in [x for x in (spec or '').split(',') if x.strip()]:
        cid, base = pair.split('=', 1)
        led = os.path.join(base, 'process_ledger.csv')
        rows = []
        with io.open(led, encoding='utf-8', newline='') as f:
            hdr = f.readline().strip().split(',')
            for line in f:
                if line.strip():
                    rows.append(dict(zip(hdr, line.rstrip('\r\n').split(','))))
        dut = [r for r in rows if r['case_id'] == cid and r['role'] == 'dut'
               and r.get('raw_sha256')]
        if not dut:
            raise RuntimeError('no retained dut launch with a raw digest for %s in %s' % (cid, led))
        r = dut[-1]
        import glob as _glob
        psf = _glob.glob(os.path.join(base, cid, 'sim', '*', 'sw1.tran.tran'))
        if not psf:
            raise RuntimeError('the retained psf for %s is not under %s' % (cid, base))
        out[cid] = {'deck_sha256': r['deck_sha256'], 'pwl_sha256': r['pwl_sha256'],
                    'raw_sha256': r['raw_sha256'], 'log_sha256': r['log_sha256'],
                    'src_run': '%s/%s' % (r['launch_id'], r.get('requested_utc', '')),
                    'psf': psf[0]}
    return out

def reused_cal_row(cal, run_id):
    c = {'case_id': 'D7B-CAL', 'group': 'cal', 'role': 'calibration', 'maxstep_ns': '0.5',
         'ramp_ns': '2', 'vclamp_v': '1.2'}
    w = {'window': 'cal', 'tick_ns': '', 'full_intervals': '', 'expected_intervals': '',
         'mode': '', 'code': '', 'pam_request': ''}
    out = {'analog_t0_ps': CAL_BAND[0], 'analog_t1_ps': CAL_BAND[1],
           'q_win': {'q': cal['ical_A'] * (CAL_BAND[1] - CAL_BAND[0]) * 1e-12},
           'settled': {'status': 'MEASURED'}, 'turn_off': {'status': 'OFF'}}
    row = case_row(run_id, c, w, out, 'REUSED', ['the calibration ran in run %s and is reused here '
                   'with its own deck/raw digests; it is not presented as a new measurement'
                   % cal['reused_from_run']], cal['ids'], 'REUSED')
    row[CASE_HDR.index('run_id')] = '%s<-%s' % (run_id, cal['reused_from_run'])
    return row


def native_run(cases, mst, docs, decks, opts, run_id, out_root, log_dir):
    root = '%s/%s' % (GUEST_ROOT, run_id)
    link = Link(GUEST_HOST, root, log_dir)
    ledger = Ledger(os.path.join(out_root, 'process_ledger.csv'))
    ev_dir = os.path.join(out_root, 'evidence', run_id)
    for sub in ('', 'pwl', 'decks', 'transcripts'):
        if not os.path.isdir(os.path.join(ev_dir, sub)):
            os.makedirs(os.path.join(ev_dir, sub))
    frozen = prepare(link, mst, out_root, log_dir)
    print('TASK_ROOT %s' % root)
    print('FROZEN_TOOLS ' + ' '.join('%s=%s' % (k, v[:12]) for k, v in sorted(frozen.items())))

    rows = []
    charge_index = []
    results = {}
    reuse_map = parse_reuse(opts.reuse)
    if reuse_map:
        print('REUSE_CASES ' + ' '.join('%s<-%s' % (k, v['src_run'])
                                          for k, v in sorted(reuse_map.items())))
    cal = None
    if opts.cal_from:
        cal = reuse_calibration(opts.cal_from, run_id)
        print('CAL_REUSED from %s Ical=%.6g ok=%s' % (opts.cal_from, cal['ical_A'], cal['ok']))
        rows.append(reused_cal_row(cal, run_id))
    negative_rows = []
    stopped = ''

    # static negative N2 first: it must refuse without ever starting the simulator
    if 'D7B-P30-C001' in decks:
        n2 = build_static_negative(mst, decks, out_root, run_id)
        negative_rows.append(run_static_negative(link, ledger, n2, run_id, mst, out_root))
    else:
        print('N2_SKIPPED this pass does not carry its source deck')

    for c in cases:
        cid = c['case_id']
        if cal is not None and not cal['ok'] and c['role'] != 'calibration':
            rows.append(case_row(run_id, c, {'window': 'normal'}, {}, 'BLOCKED',
                                 ['the calibration current never met its own window, so no other '
                                  'current conclusion is admissible'], decks[cid], ''))
            continue
        remote_dir = '%s/cases/%s' % (root, cid)
        push_case_dir(link, mst, decks, cid, out_root, remote_dir)
        tag = '%s__%s' % (cid, run_id)
        pf = ('export PROJ=%s PDK_ENV=%s\nbash %s/scripts/tb_preflight.sh %s/%s.scs %s %s "%s"\n'
              % (root, GUEST_PDK_ENV, root, remote_dir, cid, EXPECTED_VDD, tag, SUPPLY_MAP))
        prow = ledger.begin(cid, 'preflight', decks[cid]['deck_sha256'], decks[cid]['pwl_sha256'])
        rc, text = link.run(pf, 900, 'preflight-' + cid)
        p_ok = (rc == 0 and len(re.findall(r'^TESTBENCH_PREFLIGHT: PASS$', text or '', re.M)) == 1)
        p_launched = 1 if re.search(r'^spectre_rc=', text or '', re.M) else 0
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
        rc, text = link.run(script, 2000, 'dut-' + cid)
        parts = parse_runner(text)
        ids = {'deck_sha256': decks[cid]['deck_sha256'], 'pwl_sha256': decks[cid]['pwl_sha256'],
               'trace_sha256': docs[cid]['facts']['vcd_sha256'] if cid in docs else 'bench',
               'raw_sha256': '', 'log_sha256': '', 'section': '', 'temp': ''}
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
        ledger.finish(drow, rc, text, ids['raw_sha256'], ids['log_sha256'],
                      refusal='' if ok else tail_reason('; '.join(reasons)))
        print('DUT %s rc=%s verdict=%s launches=%d/%d' % (cid, rc, 'OK' if ok else 'REFUSED',
                                                           ledger.used, LAUNCH_BUDGET))
        if not ok:
            print('  REFUSED ' + '; '.join(reasons)[:400])
            for wname in c['windows'].split(';'):
                rows.append(case_row(run_id, c, {'window': wname}, {}, 'FAIL_TOOL', reasons, ids,
                                     drow['launch_id']))
            if ledger.used >= LAUNCH_BUDGET:
                stopped = 'budget exhausted after %s' % cid
                break
            continue
        if not ids['raw_sha256']:
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'FAIL_TOOL',
                                 ['no datafile was reported'], ids, drow['launch_id']))
            continue
        series, _times = psf_series(ids['raw_local'])
        env = readback_env(ids.get('log_text', ''),
                           u(io.open(raw_local, encoding='utf-8', errors='replace').read())[:4000])
        ids['section'] = 'tt'
        ids['temp'] = env['temp_header_C'] or env['temp_log_C']
        if env['temp_header_C'] and abs(float(env['temp_header_C']) - TEMP_C) > 1e-6:
            rows.append(case_row(run_id, c, {'window': ''}, {}, 'FAIL_TOOL',
                                 ['the run reports temp=%s, not 27 C' % env['temp_header_C']], ids,
                                 drow['launch_id']))
            continue
        if c['role'] == 'calibration':
            cal = calibrate(series, run_id, ids)
            write_rows(os.path.join(ev_dir, 'calibration.csv'),
                       [[r['run_id'], r['quantity'], fmt_num(r.get('value'), 1.0),
                         r.get('window_ns', ''), fmt_num(r.get('band_min_A'), 1.0),
                         fmt_num(r.get('band_max_A'), 1.0)] for r in cal['rows']],
                       ['run_id', 'quantity', 'value_A', 'window_ns', 'band_min_A', 'band_max_A'])
            print('CAL Ical=%r ok=%s %s' % (cal['ical_A'], cal['ok'], '; '.join(cal['reasons'])))
            rows.append(case_row(run_id, c, {'window': 'cal'},
                                 {'analog_t0_ps': CAL_BAND[0], 'analog_t1_ps': CAL_BAND[1],
                                  'q_win': {'q': cal['ical_A'] * 0.5e-6},
                                  'settled': {'status': 'MEASURED'}, 'turn_off': {'status': 'OFF'}},
                                 'PASS' if cal['ok'] else 'FAIL', cal['reasons'], ids,
                                 drow['launch_id']))
            if not cal['ok']:
                stopped = 'the calibration current failed; every other current conclusion is BLOCKED'
                break
            continue
        doc = docs[cid]
        by_window = dict((w['window'], w) for w in doc['windows'])
        for wname in c['windows'].split(';'):
            w = by_window[wname]
            out = measure_one(c, w, series, cal['ical_A'], drow['launch_id'], ids, run_id)
            verdict, reasons = MS.judge(out)
            if c['role'] == 'negative_wiring':
                # a dark window is a fault when the port really carries current above the OFF
                # criterion in the direction that lights the pixel -- not by a charge-scale accident
                det = ((out['window_peak']['value'] or 0.0) > MS.OFF_ABS
                       and out['q_win']['q'] > 0.0)
                neg = {'case_id': cid, 'window': wname, 'detected': 'YES' if det else 'NO',
                       'q_win_C': out['q_win']['q'], 'expected_dark_C': 0.0,
                       'window_peak_A': out['window_peak']['value'],
                       'last_100ns_max_abs_A': out['last_100ns_max_abs_A'],
                       'verdict': 'EXPECTED_REFUSAL / WIRING_FAULT_DETECTED' if det
                                  else 'NOT_DETECTED',
                       'deck_sha256': ids['deck_sha256'], 'raw_sha256': ids['raw_sha256']}
                negative_rows.append(neg)
                verdict, reasons = ('EXPECTED_REFUSAL' if det else 'NEGATIVE_NOT_DETECTED',
                                    ['the black window carries %r A of peak current'
                                     % out['window_peak']['value']])
            results[(cid, wname)] = out
            rows.append(case_row(run_id, c, w, out, verdict, reasons, ids, drow['launch_id']))
            charge_index.append(emit_charge_slice(series, c, w, out, run_id, ids, ev_dir))
            emit_edge_slice(series, c, w, out, run_id, ev_dir)
            trace_edge_table(ev_dir, run_id, doc, c)
            print('  %s q_win=%.6g C err=%+.4f LSB settled=%s off=%s %s'
                  % (wname, out['q_win']['q'], out['charge_error_LSB'] or 0.0,
                     out['settled']['status'], out['turn_off']['status'], verdict))
        if ledger.used >= LAUNCH_BUDGET:
            stopped = 'budget exhausted after %s' % cid
            break

    write_rows(os.path.join(ev_dir, 'cases.csv'), rows, CASE_HDR)
    write_convergence(os.path.join(ev_dir, 'convergence.csv'), results, cases, run_id)
    write_negative(os.path.join(ev_dir, 'negative.csv'), negative_rows)
    write_index(os.path.join(ev_dir, 'charge_index.csv'), charge_index, run_id)
    environment = {'run_id': run_id, 'task_root': root, 'guest_host': '<redacted>',
                   'python_local': sys.version.split()[0], 'base_sha': BASE_SHA,
                   'accepted_sha': ACCEPTED_SHA, 'frozen_tools': frozen,
                   'masters': [{'name': m['name'], 'repo_sha256': m['repo_sha256'],
                               'sent_sha256': m['sent_sha256'], 'stripped': len(m['removed']),
                               'stripped_lines': m['removed']} for m in mst],
                   'launches_used': ledger.used, 'budget': LAUNCH_BUDGET, 'stopped': stopped}
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
                'traces': traces})
    shutil.copyfile(os.path.join(out_root, 'process_ledger.csv'),
                    os.path.join(ev_dir, 'process_ledger.csv'))
    for src in os.listdir(log_dir):
        shutil.copyfile(os.path.join(log_dir, src), os.path.join(ev_dir, 'transcripts', src))
    for cid in sorted(decks):
        with io.open(os.path.join(ev_dir, 'decks', '%s.scs' % cid), 'w', encoding='utf-8',
                     newline='\n') as f:
            f.write(u(decks[cid]['deck']))
        with io.open(os.path.join(ev_dir, 'pwl', '%s_pwl.txt' % cid), 'w', encoding='utf-8',
                     newline='\n') as f:
            for t, v in decks[cid]['points']:
                f.write('%d %.6g\n' % (t, v))
    print('EVIDENCE_STAGED %s rows=%d launches=%d' % (ev_dir, len(rows), ledger.used))
    return {'ev_dir': ev_dir, 'run_id': run_id, 'rows': rows, 'cal': cal, 'ledger': ledger,
            'stopped': stopped}


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


def run_static_negative(link, ledger, n2, run_id, mst, out_root):
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


def write_index(path, metas, run_id):
    rows = []
    for m in metas:
        if not m:
            continue
        for p in m['parts']:
            rows.append([run_id, m['base'], p['part'], p['rows'], p['bytes'], p['first_row'],
                         p['last_row'], p['sha256'], m['total_rows'], m['series_sha256'],
                         m.get('recompute_q_win_C', '')])
    write_rows(path, rows, ['run_id', 'base', 'part', 'rows', 'bytes', 'first_row', 'last_row',
                            'sha256', 'total_rows', 'series_sha256', 'recompute_q_win_C'])


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
    hdr = ['run_id', 'case_id', 'kind', 'window', 'detected', 'q_win_C', 'expected_dark_C',
           'window_peak_A', 'last_100ns_max_abs_A', 'rc', 'stage', 'supply_fail',
           'spectre_launches', 'deck_sha256', 'raw_sha256', 'verdict']
    out = []
    for r in rows:
        out.append([r.get('run_id', ''), r.get('case_id', ''), r.get('kind', 'dynamic_wiring'),
                    r.get('window', ''), r.get('detected', ''), fmt_num(r.get('q_win_C'), 1.0),
                    fmt_num(r.get('expected_dark_C'), 1.0), fmt_num(r.get('window_peak_A'), 1e6),
                    fmt_num(r.get('last_100ns_max_abs_A'), 1e6), r.get('rc', ''),
                    r.get('stage', ''), r.get('supply_fail', ''), r.get('spectre_launches', ''),
                    r.get('deck_sha256', ''), r.get('raw_sha256', ''), r.get('verdict', '')])
    write_rows(path, out, hdr)


def publish(ev_dir, run_id):
    """move the validated bundle into a path that must not exist yet; nothing is overwritten"""
    target = os.path.join(PROJ, 'results', 'evidence', 'dd1_d7b_' + run_id)
    if os.path.exists(target):
        raise RuntimeError('%s already exists: refusing to overwrite published evidence' % target)
    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.dirname(os.path.abspath(ev_dir)) != os.path.abspath(parent):
        raise RuntimeError('the staging directory %s is not next to %s' % (ev_dir, parent))
    shutil.move(ev_dir, target)
    return target

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
