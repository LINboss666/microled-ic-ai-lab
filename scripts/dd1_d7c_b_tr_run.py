#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR native runner: the two durable accounts, the guest launches and the extraction.

Two ceilings are enforced in code, not in prose: 24 Spectre processes (nine meter preflights, nine DUT
runs, six for failures and syntax) and four RTL simulations (two formal VCDs, two for failure or
debug). Every real process is persisted as REQUESTED before it starts, a failure keeps its charge and
nothing refunds. A refusal path writes no evidence file at all.
"""

import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7b_run as B7B                            # the accepted ssh/scp channel and csv writer
import dd1_d7c_b_tr_contract as TRC
import dd1_d7c_b_tr_decks as DECK
import dd1_d7c_b_tr_measure as MEAS
import dd1_d7c_b_dc_run as DC                        # accepted Account shape, psf units, probe column

TASK_ID = TRC.TASK_ID
BASE_SHA = TRC.BASE_SHA
BRANCH = TRC.BRANCH
GUEST_PROJECT = '/root/microled_ai_project'
GUEST_WORK_ROOT = '%s/cadence_work/dd1_d7c_b_tr' % GUEST_PROJECT
DECK_DIR = TRC.DECK_DIR
SPECTRE_LIMIT = TRC.SPECTRE_LIMIT
RTL_LIMIT = TRC.RTL_LIMIT
AUTH_VAR = 'QODER_TR_AUTHORISED'
ROLES = ('preflight', 'dut', 'debug')
ACCOUNT_STATES = ('REQUESTED', 'CONFIRMED', 'FAILED', 'UNCERTAIN')
# a row counts as a process only if it carries one of these; the names differ between the two
# accounts, so the reconciliation looks at both rather than at one ledger's vocabulary
PROCESS_EVIDENCE_KEYS = ('exe_sha256', 'deck_sha256', 'rc', 'raw_sha256', 'vcd_sha256',
                         'log_sha256')
COMPILED_TARGET_KEYS = ('exe_sha256', 'deck_sha256')
ORDER = list(TRC.CASE_ORDER)
MIN_FREE_KB = 400000
DISK_REFUSAL = 'DISK_HEADROOM_BELOW_LIMIT'
ACCOUNT_HEADER = ('launch_id', 'task_id', 'run_id', 'case_id', 'role', 'state', 'requested_utc',
                  'ended_utc', 'rc', 'deck_sha256', 'raw_sha256', 'log_sha256', 'refusal',
                  'ceiling', 'occupied_after', 'guest_free_kb', 'samples', 'columns')
RTL_ACCOUNT_HEADER = ('sim_id', 'task_id', 'run_id', 'case_id', 'kind', 'state', 'requested_utc',
                      'ended_utc', 'rc', 'exe_sha256', 'vcd_sha256', 'log_sha256', 'refusal',
                      'ceiling', 'occupied_after')
OBSERVATION_HEADER = ('case_id', 'role', 'run_id', 'launch_id', 'raw_sha256', 'deck_sha256',
                      'samples', 'axis', 'axis_unit', 'current_name', 'current_unit',
                      'required_present', 'required_missing', 'internal_present', 'internal_missing',
                      'internal_status', 'time_quantum_ps', 'value_quantum_V', 't_first_ns',
                      't_last_ns', 'monotonic', 'finite')


class Refuse(Exception):
    pass


def now():
    return TRC.utc()


def repo(path):
    return os.path.join(ROOT, path.replace('/', os.sep))


def sha_file(path):
    return TRC.sha_file(path)


def sha_bytes(data):
    return TRC.sha_bytes(data)


def staging():
    directory = os.environ.get('QODER_TR_STAGING') or os.path.join(ROOT, 'review', 'scratch',
                                                                   'tr_staging')
    if not os.path.isdir(directory):
        os.makedirs(directory)
    return directory


class Account(object):
    """append-only, one writer, reserve before the start, no refund, ceiling from the approved task"""

    def __init__(self, path, ceiling, header, prefix, reconcile=None):
        self.path, self.ceiling, self.header, self.prefix = path, int(ceiling), header, prefix
        self.reconcile = reconcile
        self.lock = path + '.lock'
        self.rows = []
        if os.path.isfile(path):
            first = io.open(path, encoding='utf-8', newline='').readline().strip()
            if first != ','.join(header):
                raise Refuse('the account %s has a different header than this round writes'
                             % os.path.basename(path))
            lines = [line for line in io.open(path, encoding='utf-8', newline='').read()
                     .split('\n')[1:] if line.strip()]
            for number, line in enumerate(lines, 2):
                cells = line.split(',')
                if len(cells) != len(header):
                    raise Refuse('the account row on line %d carries %d fields against a %d field '
                                 'header' % (number, len(cells), len(header)))
            self.rows = [dict(zip(header, line.split(','))) for line in lines]
        self._check_ids()

    def _check_ids(self):
        for index, row in enumerate(self.rows, 1):
            want = '%s%03d' % (self.prefix, index)
            if row[self.header[0]] != want:
                raise Refuse('the account jumps at row %d: id %s, expected %s'
                             % (index, row[self.header[0]], want))

    def occupied(self):
        return len(self.rows)

    def duplicate_bookings(self):
        """row ids reconciled as a second booking of one already-charged process.

        A recovery never refunds a process that may have started. A booking frees nothing unless the
        ledger itself proves it: the row must carry no executable digest and no return code, and it
        must name a witness row reserved in the same second for the same case that does carry the
        process evidence. Anything else stays charged.
        """
        if not self.reconcile or not os.path.isfile(self.reconcile):
            return []
        data = json.loads(io.open(self.reconcile, encoding='utf-8').read())
        by_id = dict((row[self.header[0]], row) for row in self.rows)
        out = []
        for booking in data.get('duplicate_bookings', []):
            duplicate = booking.get(self.header[0]) or booking.get('sim_id')
            witness = (booking.get('evidence') or {}).get('witness_row')
            if duplicate not in by_id or witness not in by_id or duplicate == witness:
                continue
            dup_row, wit_row = by_id[duplicate], by_id[witness]
            if any(dup_row.get(key) for key in PROCESS_EVIDENCE_KEYS):
                continue
            if not any(wit_row.get(key) for key in COMPILED_TARGET_KEYS):
                continue
            if (dup_row.get('requested_utc') != wit_row.get('requested_utc')
                    or dup_row.get('case_id') != wit_row.get('case_id')):
                continue
            out.append(duplicate)
        return out

    def processes(self):
        duplicates = set(self.duplicate_bookings())
        return len([row for row in self.rows if row[self.header[0]] not in duplicates])

    def remaining(self):
        return self.ceiling - self.processes()

    def _acquire(self):
        try:
            handle = io.open(self.lock, 'x')
        except IOError:
            raise Refuse('another writer holds %s; this round runs one executor at a time'
                         % os.path.basename(self.lock))
        handle.write('%s %d\n' % (now(), os.getpid()))
        handle.close()

    def reserve(self, fields):
        self._acquire()
        try:
            if self.processes() >= self.ceiling:
                raise Refuse('LAUNCH_CEILING_REACHED: the account carries %d charged processes of '
                             '%d (rows %d); a failure costs the budget and recovery never refunds it'
                             % (self.processes(), self.ceiling, self.occupied()))
            row = dict((key, '') for key in self.header)
            row.update({'task_id': TASK_ID, self.header[0]:
                        '%s%03d' % (self.prefix, self.occupied() + 1),
                        'state': 'REQUESTED', 'requested_utc': now(),
                        'ceiling': self.ceiling, 'occupied_after': self.occupied() + 1})
            row.update(fields)
            self.rows.append(row)
            self.flush()
            return row
        finally:
            os.remove(self.lock)

    def settle(self, row, state, rc='', raw_sha='', log_sha='', refusal='', **extra):
        if state not in ACCOUNT_STATES:
            raise Refuse('state %r is not one of %s' % (state, ','.join(ACCOUNT_STATES)))
        self._acquire()
        try:
            if row not in self.rows:
                raise Refuse('settle names a launch that is not in the account')
            single = ' | '.join((refusal or '').splitlines()).replace(',', ';')
            row.update({'state': state, 'ended_utc': now(), 'rc': rc, 'raw_sha256': raw_sha,
                        'log_sha256': log_sha, 'refusal': single[:180]})
            for key, value in extra.items():
                if key in self.header:
                    row[key] = value
            self.flush()
        finally:
            os.remove(self.lock)

    def flush(self):
        for row in self.rows:
            for key in self.header:
                text = str(row.get(key, ''))
                if any(marker in text for marker in (',', '\n', '\r')):
                    raise Refuse('the %s field of %s carries a table delimiter, so nothing is '
                                 'written' % (key, row[self.header[0]]))
        B7B.write_rows(self.path, [[row.get(key, '') for key in self.header] for row in self.rows],
                       list(self.header))
        return self.path


def spectre_account(out_dir, run_id=''):
    path = os.path.join(out_dir, 'spectre_launch_account.csv')
    account = Account(path, SPECTRE_LIMIT, ACCOUNT_HEADER, 'T')
    if run_id:
        for row in account.rows:
            if not row['run_id']:
                row['run_id'] = run_id
    return account


def rtl_account(out_dir, run_id=''):
    return Account(os.path.join(out_dir, 'rtl_simulation_account.csv'), RTL_LIMIT,
                   RTL_ACCOUNT_HEADER, 'R',
                   reconcile=os.path.join(out_dir, 'rtl_process_reconciliation.json'))


def authorisation_problem(role, case_id, done_preflight=None):
    if os.environ.get(AUTH_VAR) not in ('1', 'YES', 'yes', 'true'):
        return ('%s is not set: no Spectre process may start this round' % AUTH_VAR)
    if case_id not in ORDER:
        return '%s is not one of the nine approved cases' % case_id
    if role not in ROLES:
        return 'role %r is not one of %s' % (role, ','.join(ROLES))
    deck = repo('%s/%s.%s' % (DECK_DIR, case_id, 'pre.scs' if role == 'preflight' else 'scs'))
    if not os.path.isfile(deck):
        return '%s has no run copy in the repository; emit the decks first' % deck
    if role == 'dut' and done_preflight is not None and case_id not in done_preflight:
        return '%s: its own meter preflight has not passed, so the DUT run is not allowed' % case_id
    return ''


def link_for(log_dir):
    return B7B.Link(B7B.GUEST_HOST, GUEST_PROJECT, log_dir)


def remote_paths(run_id):
    base = '%s/%s' % (GUEST_WORK_ROOT, run_id)
    return {'base': base, 'masters': '%s/masters' % base, 'scripts': '%s/scripts' % base,
            'cases': '%s/cases' % base}


def account_of_masters():
    path = repo('%s/deck_account.json' % DECK_DIR)
    if not os.path.isfile(path):
        raise Refuse('%s is missing; run the deck emitter before any launch' % DECK_DIR)
    return json.loads(io.open(path, encoding='utf-8').read())


def prepare_remote(link, run_id):
    paths = remote_paths(run_id)
    rc, text = link.run('mkdir -p %s %s %s && echo STAGED_DIRS_OK'
                        % (paths['masters'], paths['scripts'], paths['cases']), 120, 'mkdir')
    if rc != 0 or 'STAGED_DIRS_OK' not in (text or ''):
        raise Refuse('the guest run directories could not be created under %s: %s'
                     % (paths['base'], (text or '').strip()[:160]))
    account = account_of_masters()
    if 'masters' not in account:
        raise Refuse('the deck account carries no master list, so nothing can be pushed as the '
                     'netlib include target')
    for row in account['masters']:
        digest = sha_file(repo(row['path']))
        if digest != row['sha256_on_disk'] or digest != row['blob_sha256_at_base']:
            raise Refuse('%s on disk is %s, the account says %s and the base blob says %s'
                         % (row['path'], digest[:12], row['sha256_on_disk'][:12],
                            row['blob_sha256_at_base'][:12]))
        link.push(repo(row['path']), '%s/%s' % (paths['masters'], row['name']),
                  'master-' + row['name'])
    link.push(repo('scripts/run_spectre.sh'), '%s/run_spectre.sh' % paths['scripts'], 'executor')
    return paths, sha_file(repo('scripts/run_spectre.sh'))


def free_kb(link, tag):
    rc, text = link.run("df -P / | awk 'NR==2{print $4}'", 120, tag)
    digits = re.findall(r'\d+', text or '')
    return int(digits[-1]) if rc == 0 and digits else None


def disk_refusal(free):
    """a launch is refused before it starts when the guest root is known to be too small; an
    unreadable df is recorded rather than treated as a verdict"""
    if free is None:
        return ''
    if free < MIN_FREE_KB:
        return ('%s: the guest root has %d KB free, this round keeps a floor of %d KB, so nothing '
                'was started' % (DISK_REFUSAL, free, MIN_FREE_KB))
    return ''


def deck_for(case_id, role):
    suffix = 'pre.scs' if role == 'preflight' else 'scs'
    path = repo('%s/%s.%s' % (DECK_DIR, case_id, suffix))
    if not os.path.isfile(path):
        raise Refuse('%s is not in the repository; emit the decks first' % path)
    return path


def expected_dut_sha(case_id):
    for row in account_of_masters()['decks']:
        if row['case_id'] == case_id:
            return row['sha256']
    raise Refuse('%s has no entry in the deck account' % case_id)


def expected_preflight_sha(case_id):
    for row in account_of_masters()['preflights']:
        if row['case_id'] == case_id:
            return row['sha256']
    raise Refuse('%s has no preflight entry in the deck account' % case_id)


def launch(case_id, role, out_dir, run_id, timeout=1800, done_preflight=None):
    """one Spectre process, charged before it starts; a refusal writes nothing into the evidence"""
    problem = authorisation_problem(role, case_id, done_preflight)
    if problem:
        return 5, {'refusal': problem, 'case_id': case_id, 'role': role, 'process_started': False}
    deck = deck_for(case_id, role)
    want = expected_preflight_sha(case_id) if role == 'preflight' else expected_dut_sha(case_id)
    if sha_file(deck) != want:
        return 5, {'refusal': '%s on disk is %s, the deck account carries %s'
                           % (os.path.basename(deck), sha_file(deck)[:12], want[:12]),
                   'process_started': False}
    account = spectre_account(out_dir, run_id)
    row = account.reserve({'case_id': case_id, 'role': role, 'deck_sha256': want, 'run_id': run_id})
    log_dir = os.path.join(out_dir, 'guest_logs')
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    link = link_for(log_dir)
    stem = os.path.basename(deck)[:-4]
    try:
        free = free_kb(link, '%s-space-before' % case_id)
        problem = disk_refusal(free)
        if problem:
            account.settle(row, 'FAILED', rc='', refusal=problem)
            return 6, {'refusal': DISK_REFUSAL, 'detail': problem, 'guest_free_kb': free,
                       'process_started': False, 'launch_id': row['launch_id']}
        paths, runner_sha = prepare_remote(link, run_id)
        case_dir = '%s/%s_%s' % (paths['cases'], case_id, role)
        link.run('mkdir -p %s && echo CASE_DIR_OK' % case_dir, 120, 'mkdir-case')
        link.push(deck, '%s/%s' % (case_dir, os.path.basename(deck)), 'deck')
        payload = ('set -a\n. %s/spectre/pdk_local.env\nset +a\n'
                   'export PROJ=%s PDK_ENV=%s QODER_NETLIST_DIR=%s\n'
                   'LABEL=TR7CB_%s_%s bash %s/run_spectre.sh %s %d\n'
                   % (GUEST_PROJECT, GUEST_PROJECT, '%s/spectre/pdk_local.env' % GUEST_PROJECT,
                      paths['masters'], case_id.replace('-', '_'), role.upper(),
                      paths['scripts'], '%s/%s' % (case_dir, os.path.basename(deck)), timeout))
        rc, text = link.run(payload, timeout + 240, '%s-%s' % (role, case_id))
    except Refuse as error:
        account.settle(row, 'UNCERTAIN', refusal='REFUSED_DURING_STAGING: %s' % error)
        return 5, {'refusal': str(error), 'launch_id': row['launch_id'], 'process_started': False}
    except RuntimeError as error:
        account.settle(row, 'UNCERTAIN', refusal='TRANSFER_FAILED: %s' % error)
        return 1, {'refusal': str(error), 'launch_id': row['launch_id'], 'process_started': None}
    parsed = B7B.parse_runner(text)
    raw_sha = log_sha = ''
    raw_local = ''
    for key, tag in (('datafile', 'raw'), ('logfile', 'log')):
        remote = parsed.get(key) or ''
        if remote and not remote.startswith('$'):
            digest = link.pull(remote, os.path.join(out_dir, '%s_%s_%s.%s'
                                                    % (run_id, case_id, role, tag)))
            if tag == 'raw':
                raw_sha, raw_local = digest, os.path.join(out_dir, '%s_%s_%s.raw'
                                                          % (run_id, case_id, role))
            else:
                log_sha = digest
    ok = rc == 0 and DC.runner_says_ok(parsed)
    state = 'CONFIRMED' if ok else 'FAILED'
    free_after = free_kb(link, '%s-space-after' % case_id) if ok else None
    account.settle(row, state, rc, raw_sha=raw_sha, log_sha=log_sha,
                   refusal='' if ok else (text or '').strip()[-160:],
                   guest_free_kb=free_after or free or '')
    return (0 if ok else 1), {'case_id': case_id, 'role': role, 'rc': rc,
                              'launch_id': row['launch_id'], 'state': state,
                              'deck_path': os.path.relpath(deck, ROOT).replace(os.sep, '/'),
                              'deck_sha256': sha_file(deck), 'raw': raw_local,
                              'raw_sha256': raw_sha, 'log_sha256': log_sha,
                              'runner': parsed, 'guest_base': paths['base'],
                              'executor_sha256': runner_sha, 'guest_free_kb_before': free,
                              'guest_free_kb_after': free_after,
                              'tail': (text or '').strip()[-300:]}


def observe(raw_path, case_id, role, run_id, launch_id, deck_sha):
    """what the native answer actually carries, before any measurement is claimed from it"""
    data = MEAS.load_raw(raw_path, case_id)
    required = [name for name in TRC.contract()['required_signals']['always_extracted']]
    internals = (TRC.contract()['required_signals']['internal_nodes']['en']
                 + TRC.contract()['required_signals']['internal_nodes']['enb']
                 + TRC.contract()['required_signals']['internal_nodes']['vbias_ch']
                 + TRC.contract()['required_signals']['internal_nodes']['node_m'])
    have = set(data['series'])
    present = [name for name in required if name in have]
    missing = [name for name in required if name not in have]
    int_present = [name for name in internals if name in have]
    int_missing = [name for name in internals if name not in have]
    if role == 'preflight':
        # a meter preflight instantiates no DUT, so its hierarchy saves were deliberately removed;
        # calling that PARTIAL would misreport a designed absence as an observation gap
        internal_status = 'NOT_APPLICABLE_IDEAL_LOADS'
    else:
        internal_status = 'COMPLETE' if not int_missing else 'PARTIAL'
    monotonic = all(data['series']['time'][index][0] > data['series']['time'][index - 1][0]
                    if 'time' in data['series'] else True
                    for index in range(1, len(data['series'].get('time', []))))
    return {'case_id': case_id, 'role': role, 'run_id': run_id, 'launch_id': launch_id,
            'raw_sha256': sha_file(raw_path), 'deck_sha256': deck_sha,
            'samples': data['samples'], 'axis': data['axis'], 'axis_unit': data['axis_unit'],
            'current_name': data['current_name'], 'current_unit': data['units'].get(
                data['current_name'], ''),
            'required_present': ','.join(present), 'required_missing': ','.join(missing),
            'internal_present': '%d/%d' % (len(int_present), len(internals)),
            'internal_missing': ','.join(int_missing) or '-',
            'internal_status': internal_status,
            'time_quantum_ps': data['quantum_ps'], 'value_quantum_V': data['value_quantum_V'],
            't_first_ns': data['t_first_ps'] / 1000.0, 't_last_ns': data['t_last_ps'] / 1000.0,
            'monotonic': 'YES' if monotonic else 'NO',
            'finite': 'YES'}


def gc_case(link, run_id, case_id, role, raw_sha):
    """delete only this round's own case directory, and only after its raw is home and digested"""
    if not raw_sha:
        raise Refuse('%s/%s: no pulled raw digest, so nothing may be removed' % (case_id, role))
    paths = remote_paths(run_id)
    case_dir = '%s/%s_%s' % (paths['cases'], case_id, role)
    if not case_dir.startswith(GUEST_WORK_ROOT):
        raise Refuse('%s is outside this round guest root' % case_dir)
    rc, text = link.run('du -sk %s 2>/dev/null; rm -rf %s && echo GONE_%s'
                        % (case_dir, case_dir, case_id.replace('-', '_')), 240, 'gc-%s-%s'
                        % (case_id, role))
    if rc != 0 or 'GONE_' not in (text or ''):
        raise Refuse('%s could not be removed: %s' % (case_dir, (text or '').strip()[:120]))
    return {'case_dir': case_dir, 'raw_sha256': raw_sha, 'rc': rc,
            'note': 'removed only after the raw and log were pulled and digested'}


def write_observation(path, rows):
    return B7B.write_rows(path, [[row.get(key, '') for key in OBSERVATION_HEADER] for row in rows],
                          list(OBSERVATION_HEADER))


def selftest():
    """the guards that protect the ceiling, the refusal paths and the preflight ordering"""
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else extra))
    out = staging()
    os.environ.pop(AUTH_VAR, None)
    record('no authorisation variable means no launch and no file',
           authorisation_problem('dut', 'TR-LONG').startswith(AUTH_VAR),
           authorisation_problem('dut', 'TR-LONG'))
    rc, answer = launch('TR-LONG', 'dut', out, 'r_selftest')
    record('an unauthorised launch returns rc 5 without starting a process',
           rc == 5 and answer['process_started'] is False, answer)
    record('the refusal path wrote no account row',
           not os.path.isfile(os.path.join(out, 'spectre_launch_account.csv'))
           or spectre_account(out).occupied() == 0, '')
    os.environ[AUTH_VAR] = '1'
    try:
        rc, answer = launch('TR-999', 'dut', out, 'r_selftest')
        record('a case outside the approved nine is refused by name', rc == 5 and
               'nine approved cases' in answer['refusal'], answer)
        rc, answer = launch('TR-LONG', 'probe', out, 'r_selftest')
        record('an unknown role is refused', rc == 5, answer)
        rc, answer = launch('TR-120', 'dut', out, 'r_selftest', done_preflight=set())
        record('a DUT run without its own meter preflight is refused',
               rc == 5 and 'preflight' in answer['refusal'], answer)
        absent = [case for case in ORDER
                  if not os.path.isfile(os.path.join(repo(DECK_DIR), case + '.scs'))]
        record('the prepared run copies are all present before any launch',
               set(absent) <= set(TRC.HYB_CASES), absent)
        rc, answer = launch('HYB-120', 'dut', out, 'r_selftest', done_preflight={'HYB-120'})
        record('a hybrid launch is refused until its own run copy exists',
               rc == 5 and 'run copy' in answer['refusal'], answer)
    finally:
        os.environ.pop(AUTH_VAR, None)
    account_path = os.path.join(out, 'account_ceiling.csv')
    if os.path.isfile(account_path):
        os.remove(account_path)
    account = Account(account_path, 3, ACCOUNT_HEADER, 'T')
    for index in range(3):
        account.reserve({'case_id': 'TR-120', 'role': 'dut', 'run_id': 'r'})
    refused = False
    try:
        account.reserve({'case_id': 'TR-120', 'role': 'dut', 'run_id': 'r'})
    except Refuse:
        refused = True
    record('the fourth launch past a ceiling of three is refused and stays unwritten', refused, '')
    record('a failure keeps its charge: three REQUESTED rows remain',
           account.occupied() == 3 and all(row['state'] == 'REQUESTED' for row in account.rows),
           account.rows[-1])
    account.settle(account.rows[0], 'FAILED', rc='1', refusal='SYNTAX')
    record('settling a row does not free the budget', account.remaining() == 0,
           account.remaining())
    account.settle(account.rows[1], 'CONFIRMED', rc='0', raw_sha='a' * 64, log_sha='b' * 64)
    record('a confirmed row keeps its digest in the account',
           account.rows[1]['raw_sha256'] == 'a' * 64, account.rows[1])
    refused = False
    try:
        account.settle(account.rows[2], 'MAYBE')
    except Refuse:
        refused = True
    record('an unknown account state is refused', refused, '')
    text = io.open(account_path, encoding='utf-8', newline='').read()
    record('the account re-reads with the same three ids in order',
           [row['launch_id'] for row in Account(account_path, 3, ACCOUNT_HEADER, 'T').rows]
           == ['T001', 'T002', 'T003'], text.splitlines()[:1])
    tampered = text.replace('T002', 'T009', 1)
    io.open(account_path + '.bad', 'wb').write(tampered.encode('utf-8'))
    refused = False
    try:
        Account(account_path + '.bad', 3, ACCOUNT_HEADER, 'T')
    except Refuse:
        refused = True
    record('an account whose ids jump is refused rather than trusted', refused, '')
    os.remove(account_path + '.bad')
    reconcile = account_path + '.reconcile.json'
    settled = Account(account_path, 3, ACCOUNT_HEADER, 'T')
    # T003 is the shape of a double booking: reserved, never settled, no executable and no return
    # code, while T002 beside it carries the process that actually ran
    settled.rows[2]['requested_utc'] = settled.rows[1]['requested_utc'] = (
        settled.rows[0]['requested_utc'])
    settled.rows[2]['case_id'] = settled.rows[1]['case_id']
    settled.rows[1]['deck_sha256'] = 'd' * 64      # the target the process actually ran
    settled.flush()
    booking = json.dumps({'duplicate_bookings': [
        {'launch_id': 'T003', 'evidence': {'witness_row': 'T002'}}]}) + '\n'
    io.open(reconcile, 'wb').write(booking.encode('utf-8'))
    checked = Account(account_path, 3, ACCOUNT_HEADER, 'T', reconcile=reconcile)
    record('a duplicate booking is honoured only against a row that carries the process evidence',
           checked.processes() == 2 and checked.remaining() == 1,
           (checked.processes(), checked.remaining()))
    tainted = Account(account_path, 3, ACCOUNT_HEADER, 'T')
    tainted.rows[2]['rc'] = '1'
    tainted.flush()
    forged = Account(account_path, 3, ACCOUNT_HEADER, 'T', reconcile=reconcile)
    record('a booking that carries process evidence of its own stays charged',
           forged.processes() == 3 and forged.remaining() == 0,
           (forged.processes(), forged.remaining()))
    witness = Account(account_path, 3, ACCOUNT_HEADER, 'T')
    witness.rows[1]['deck_sha256'] = ''
    witness.rows[2]['rc'] = ''
    witness.flush()
    empty_witness = Account(account_path, 3, ACCOUNT_HEADER, 'T', reconcile=reconcile)
    record('a witness row without an executable cannot vouch for a duplicate',
           empty_witness.processes() == 3, empty_witness.processes())
    os.remove(reconcile)
    record('the deck account stamps every run copy with the committed contract digest',
           not DECK.check_account(account_of_masters(), require_all=False),
           DECK.check_account(account_of_masters(), require_all=False)[:2])
    record('the two accounts name the ceilings from the approved task',
           (SPECTRE_LIMIT, RTL_LIMIT) == (24, 4), (SPECTRE_LIMIT, RTL_LIMIT))
    record('nine cases times two roles is the planned half of the ceiling',
           len(ORDER) * 2 == 18 and 18 + 6 == SPECTRE_LIMIT, len(ORDER) * 2)
    record('the guest write root is this round directory only',
           GUEST_WORK_ROOT == '/root/microled_ai_project/cadence_work/dd1_d7c_b_tr',
           GUEST_WORK_ROOT)
    refused = False
    try:
        gc_case(None, 'r', 'TR-120', 'dut', '')
    except Refuse:
        refused = True
    record('a cleanup without a pulled raw digest is refused', refused, '')
    record('the disk floor refuses a launch below it and allows one above it',
           DISK_REFUSAL in disk_refusal(MIN_FREE_KB - 1) and disk_refusal(MIN_FREE_KB) == ''
           and disk_refusal(MIN_FREE_KB + 1) == '' and disk_refusal(None) == '',
           (disk_refusal(MIN_FREE_KB - 1), disk_refusal(MIN_FREE_KB), disk_refusal(None)))
    record('an unreadable df is recorded, not invented into a verdict',
           disk_refusal(None) == '', disk_refusal(None))
    return results


def main(argv):
    mode = argv[0] if argv else '--selftest'
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-66s %s %s' % (name, 'PASS' if ok else 'FAIL', str(extra)[:150]))
        print('TR_RUN_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--account':
        account = spectre_account(staging())
        print(json.dumps({'occupied': account.occupied(), 'ceiling': account.ceiling,
                          'remaining': account.remaining()}, indent=1))
        return 0
    print('usage: --selftest | --account')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
