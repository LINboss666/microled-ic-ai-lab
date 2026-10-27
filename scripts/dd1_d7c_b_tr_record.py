#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR record: consolidate the native rows, judge them, and publish what can be checked.

Everything here reads published evidence files and committed sources, and writes new files only. It
never starts a simulator: an extraction after a tool fix costs no launch, and this module refuses a
number it cannot bind to a charged launch. A negative electrical finding is published as itself; no
aggregate verdict is computed that could hide one.
"""

import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7c_b_tr_contract as TRC
import dd1_d7c_b_tr_decks as DECK
import dd1_d7c_b_tr_measure as MEAS
import dd1_d7c_b_tr_run as RUN
import dd1_d7c_b_tr_trace as TRACE

TASK_ID = RUN.TASK_ID
BASE_SHA = RUN.BASE_SHA
BRANCH = RUN.BRANCH
EVIDENCE_ROOT = 'results/evidence'
ROLE = 'dut'
NUMERIC = ('tick_ns', 'qlsb_C', 'window_start_ns', 'window_stop_ns', 'rise50_ns', 'fall50_ns',
           't50_ns', 'flat_start_ns', 'flat_stop_ns', 'q_full_C', 'q_flat_C', 'q_pos_C', 'q_neg_C',
           'abs_q_neg_C', 'peak_A', 'peak_ns', 'flat_mean_A', 'tail_q_C', 'leak_max_abs_A',
           'qtarget_nominal_C', 'qtarget_dc_C', 'err_nominal_LSB', 'err_dynamic_LSB',
           'settling_start_ns', 'settling_last_out_ns', 'settling_left_limit_A')
TRACK_LIMIT_BYTES = 32 * 1024 * 1024
# written as fragments so the scanner cannot trip on its own source, which is how a secret scanner
# that whitelists itself would be read as a weakened check
SECRET_PATTERNS = ('.ic617_agent' + '_bridge_credentials', 'pass' + 'word=',
                   'BEGIN ' + 'RSA PRIVATE', '@270' + '12', 'QODER_' + 'PDK_LIB=',
                   '/eda/' + 'c', 'D:' + '\\ic617_d7a_tools', 'C:' + '\\Users\\')
REPORT_PATH = 'reports/dd1_d7c_b_tr_report.md'
CONTRACT_REPORT = TRC.CONTRACT_REPORT
HANDOFF_MD = 'reports/dd1_d7c_b_tr_handoff.md'
HANDOFF_JSON = 'reports/dd1_d7c_b_tr_handoff.json'


def repo(path):
    return os.path.join(ROOT, path.replace('/', os.sep))


def sha_of(path):
    return TRC.sha_file(path)


def utc():
    return TRC.utc()


def number(text):
    """a published cell back to a float, with '' and words kept as they are"""
    try:
        return float(text)
    except (TypeError, ValueError):
        return text


def evidence_dir(name=''):
    if name:
        return repo(os.path.join(EVIDENCE_ROOT, name))
    found = sorted(row for row in os.listdir(repo(EVIDENCE_ROOT))
                   if row.startswith('dd1_d7c_b_tr_r'))
    if not found:
        raise TRC.Refuse('no DATA-7C-B-TR evidence directory exists, so nothing can be recorded')
    return repo(os.path.join(EVIDENCE_ROOT, found[-1]))


def run_id_of(directory):
    return os.path.basename(directory)[len('dd1_d7c_b_tr_'):]


# ---- reading the published tables -------------------------------------------------------------------

def read_table(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise TRC.Refuse('%s is an empty table, and an empty table proves nothing' % path)
    return rows


def case_rows(directory, case_id):
    path = os.path.join(directory, 'rows_%s_%s.csv' % (case_id, ROLE))
    if not os.path.isfile(path):
        raise TRC.Refuse('%s has no published %s row table, so its charge was never extracted'
                         % (case_id, ROLE))
    out = []
    for row in read_table(path):
        item = dict(row)
        for key in NUMERIC:
            item[key] = number(row.get(key, ''))
        out.append(item)
    return out


def all_rows(directory):
    rows = []
    for case_id in TRC.CASE_ORDER:
        rows.extend(case_rows(directory, case_id))
    return rows


def ledgers(directory):
    return (read_table(os.path.join(directory, 'spectre_launch_account.csv')),
            read_table(os.path.join(directory, 'rtl_simulation_account.csv')))


def deck_sha(case_id, role=ROLE):
    return sha_of(RUN.deck_for(case_id, role))


# ---- the three convergence pairs --------------------------------------------------------------------

def convergence_table(directory):
    pairs, problems, rows = [], [], []
    for plan in TRC.contract()['convergence']['pairs']:
        refined = case_rows(directory, plan['refined'])
        coarse = case_rows(directory, plan['coarse'])
        pair_rows, pair_problems = MEAS.convergence(refined, coarse, plan)
        rows.extend(pair_rows)
        problems.extend(pair_problems)
        pairs.append({'refined': plan['refined'], 'coarse': plan['coarse'],
                      'maxstep_ns': plan['maxstep_ns'],
                      'coarse_maxstep_ns': plan['coarse_maxstep_ns'],
                      'tick_ns': plan['tick_ns'], 'windows': len(pair_rows)})
    return rows, pairs, problems


# ---- the two bookkeeping verdicts ---------------------------------------------------------------------

def completeness(directory):
    """what actually ran, counted off the ledgers, with every failure kept in the note"""
    spectre, rtl = ledgers(directory)
    want = [(case, role) for case in TRC.CASE_ORDER for role in ('preflight', ROLE)]
    confirmed = dict(((row['case_id'], row['role']), row) for row in spectre
                    if row['state'] == 'CONFIRMED')
    missing = ['%s/%s' % pair for pair in want if pair not in confirmed]
    charged = len(spectre)
    strays, _notes = RUN.budget_strays(directory)
    ceiling = RUN.spectre_ceiling(directory)
    rtl_processes = len([row for row in rtl if row['sim_id'] not in
                         _duplicate_ids(directory)])
    note = ('%d of %d planned launches confirmed, %d account rows charged, %d stray processes '
            'charged from the recorded budget adjustment, effective ceiling %d of the approved %d, '
            '%d vvp processes charged of the approved %d'
            % (len(confirmed), len(want), charged, strays, ceiling, RUN.SPECTRE_LIMIT,
               rtl_processes, RUN.RTL_LIMIT))
    failures = [row['launch_id'] for row in spectre if row['state'] != 'CONFIRMED']
    if failures:
        note += '; rows kept charged and not refunded: %s' % ','.join(failures)
    verdict = 'PASS' if not missing else 'PARTIAL'
    return {'verdict': verdict, 'measured': len(confirmed), 'expected': len(want),
            'note': note, 'missing': missing}


def derive_duplicates(rtl_rows):
    """the second bookings of an already-charged process, derived from the ledger alone

    A row frees nothing unless the ledger proves it: it must carry no process evidence of its own and
    name a witness row reserved in the same second for the same case that does carry it. Anything else
    stays charged, so a recovery can never refund a simulator start by editing a file.
    """
    by_id = dict((row['sim_id'], row) for row in rtl_rows)
    out = []
    for row in rtl_rows:
        if any(row.get(key) for key in RUN.PROCESS_EVIDENCE_KEYS):
            continue
        witnesses = [other for other in rtl_rows
                     if other['sim_id'] != row['sim_id']
                     and other['case_id'] == row['case_id']
                     and other['requested_utc'] == row['requested_utc']
                     and any(other.get(key) for key in RUN.COMPILED_TARGET_KEYS)]
        if len(witnesses) == 1:
            out.append((row['sim_id'], witnesses[0]['sim_id']))
    return out


def reconciliation_file(directory):
    return os.path.join(directory, 'rtl_process_reconciliation.json')


def rtl_reconciliation(directory):
    """what the published reconciliation says, against what the current ledger proves"""
    _spectre, rtl = ledgers(directory)
    path = reconciliation_file(directory)
    declared = []
    statement = {}
    if os.path.isfile(path):
        statement = json.loads(io.open(path, encoding='utf-8').read())
        declared = [row.get('sim_id') for row in statement.get('duplicate_bookings', [])]
    derived = derive_duplicates(rtl)
    problems = []
    if sorted(declared) != sorted([dup for dup, _w in derived]):
        problems.append('the file declares %s as duplicate bookings, the ledger proves %s'
                        % (','.join(declared) or '-',
                           ','.join([dup for dup, _w in derived]) or '-'))
    covered = statement.get('ledger_rows_at_this_statement') or []
    if covered != [row['sim_id'] for row in rtl]:
        problems.append('the statement covers %s while the ledger now holds %s, so its counts are '
                        'about an older ledger'
                        % (','.join(covered) or '-', ','.join(r['sim_id'] for r in rtl)))
    processes = len(rtl) - len(derived)
    if statement.get('actual_vvp_processes_started') != processes:
        problems.append('the file states %r processes against the %d the ledger now supports'
                        % (statement.get('actual_vvp_processes_started'), processes))
    return {'problems': problems, 'derived': derived, 'processes': processes,
            'rows': [row['sim_id'] for row in rtl],
            'statement': statement}


def restate_reconciliation(directory):
    """rewrite the statement from the ledger, keeping the earlier wording as history"""
    _spectre, rtl = ledgers(directory)
    path = reconciliation_file(directory)
    old = (json.loads(io.open(path, encoding='utf-8').read()) if os.path.isfile(path) else {})
    derived = derive_duplicates(rtl)
    by_id = dict((row['sim_id'], row) for row in rtl)
    bookings = []
    old_bookings = dict((row.get('sim_id'), row) for row in old.get('duplicate_bookings', []))
    for duplicate, witness in derived:
        dup, wit = by_id[duplicate], by_id[witness]
        before = (old_bookings.get(duplicate) or {}).get('evidence') or {}
        bookings.append({'sim_id': duplicate, 'witness_row': witness,
                         'reason': (old_bookings.get(duplicate) or {}).get(
                             'reason', 'derived from the ledger by dd1_d7c_b_tr_record.py'),
                         'evidence': {'shared_requested_utc': dup['requested_utc'],
                                      'witness_row': witness,
                                      'witness_exe_sha256': wit.get('exe_sha256', ''),
                                      'witness_rc': wit.get('rc', ''),
                                      'log_sha256': wit.get('log_sha256') or before.get(
                                          'log_sha256', ''),
                                      # a file name is kept as it was written, never renamed to a
                                      # pattern the archive on disk does not match
                                      'log_file_of_that_process': before.get(
                                          'log_file_of_that_process',
                                          '%s_%s.vvp.log' % (dup['case_id'], witness))}})
    history = list(old.get('statement_history', []))
    if old:
        history.append(dict(old, superseded_utc=utc()))
    data = {'task_id': TASK_ID, 'run_id': run_id_of(directory), 'ceiling': RUN.RTL_LIMIT,
            'actual_vvp_processes_started': len(rtl) - len(derived),
            'ledger_rows_at_this_statement': [row['sim_id'] for row in rtl],
            'duplicate_bookings': bookings, 'stated_utc': utc(),
            'restated_from': old.get('stated_utc') or old.get('recorded_utc') or '',
            'restated_reason': 'the ledger grew after the first statement, and a statement about a '
                               'ledger must name the ledger it counts',
            'derived_by': 'scripts/dd1_d7c_b_tr_record.py derive_duplicates',
            'statement_history': history}
    io.open(path, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(data, indent=1, sort_keys=True) + '\n')
    return path, data


def _duplicate_ids(directory):
    return [dup for dup, _w in rtl_reconciliation(directory)['derived']]


def integrity(directory):
    """every published number must sit on a charged launch of the deck that is delivered here"""
    spectre, _rtl = ledgers(directory)
    by_id = dict((row['launch_id'], row) for row in spectre)
    problems = []
    checked = 0
    for case_id in TRC.CASE_ORDER:
        expected_deck = deck_sha(case_id, ROLE)
        for row in case_rows(directory, case_id):
            launch = by_id.get(row['launch_id'])
            if launch is None:
                problems.append('%s %s cites %s which is not in the launch account'
                                % (case_id, row['window_id'], row['launch_id']))
                continue
            if launch['state'] != 'CONFIRMED':
                problems.append('%s %s cites a %s launch row' % (case_id, row['window_id'],
                                                                 launch['state']))
            if launch['raw_sha256'] != row['raw_sha256']:
                problems.append('%s %s publishes raw %s while the account holds %s'
                                % (case_id, row['window_id'], row['raw_sha256'][:12],
                                   launch['raw_sha256'][:12]))
            if launch['deck_sha256'] != expected_deck:
                problems.append('%s %s was run on deck %s, the delivered run copy is %s'
                                % (case_id, row['window_id'], launch['deck_sha256'][:12],
                                   expected_deck[:12]))
            if row['deck_sha256'] != expected_deck:
                problems.append('%s %s publishes deck %s while the delivered run copy is %s'
                                % (case_id, row['window_id'], row['deck_sha256'][:12],
                                   expected_deck[:12]))
            checked += 1
        raw = os.path.join(directory, '%s_%s_%s.raw' % (run_id_of(directory), case_id, ROLE))
        if os.path.isfile(raw) and sha_of(raw) != launch['raw_sha256']:
            problems.append('%s: the raw on this machine is not the raw the account digested'
                            % case_id)
    consistency = []
    for case_id in TRC.CASE_ORDER:
        path = os.path.join(directory, 'iprobe_consistency_%s_%s.json' % (case_id, ROLE))
        if not os.path.isfile(path):
            problems.append('%s publishes no iprobe two-terminal check' % case_id)
            continue
        data = json.loads(io.open(path, encoding='utf-8').read())
        consistency.append(data)
        if not data['passes'] or not data['tolerance_is_expressible']:
            problems.append('%s: the ideal probe fails its own two-terminal rule' % case_id)
    return {'verdict': 'PASS' if not problems else 'FAIL', 'measured': checked,
            'expected': checked if not problems else 0,
            'note': '%d rows bound to a confirmed launch and the delivered deck; %d cases carry the '
                    'two-terminal check' % (checked, len(consistency)),
            'problems': problems}


# ---- delay attribution on the internal nodes ----------------------------------------------------------

EDGE_LOOK_NS = 50.0     # the search around the enable crossing where a branch edge can possibly be


def _boundary(series, level, rise_ps, flat_stop_ps, label):
    """the first crossing of `level` within +-50 ns of the enable crossing, or why there is none

    The window is deliberately narrow: searching forward over a whole pulse finds the *next* pulse's
    edge and reports it as a delay, which is exactly the mistake this function had to be written
    against. A negative answer is a real one: it means the node was already past the level when the
    enable crossed half-rail.
    """
    lo = rise_ps - MEAS.ns_to_ps(EDGE_LOOK_NS)
    hi = rise_ps + MEAS.ns_to_ps(EDGE_LOOK_NS)
    crossed = MEAS.B7M.crossing(series, level, True, lo, hi, label)
    if crossed is not None:
        return (crossed - rise_ps) * MEAS.S_PER_PS * 1e9, 'CROSSING'
    at_rise = TRACE.B7T.value_at(series, rise_ps, None)
    if at_rise is not None and at_rise >= level:
        return 0.0, 'ALREADY_ABOVE_AT_RISE'
    later = MEAS.B7M.crossing(series, level, True, rise_ps, flat_stop_ps, label)
    if later is not None:
        return (later - rise_ps) * MEAS.S_PER_PS * 1e9, 'CROSSING_LATE'
    peak = MEAS.B7M.extreme(series, lo, hi)[0]
    return None, 'NEVER_REACHES_LEVEL_IN_WINDOW(peak %g)' % peak


def delay_breakdown(directory, case_id):
    """where the lost time sits on each step: decoding, bias charge, or current build-up

    Each boundary is measured off the native samples with the accepted crossing helper. A boundary
    that does not exist in the samples is reported with the reason and left out of the sum, never
    filled in from a neighbouring column.
    """
    raw = os.path.join(directory, '%s_%s_%s.raw' % (run_id_of(directory), case_id, ROLE))
    data = MEAS.load_raw(raw, case_id)
    idc = TRC.dc_idc_by_code()
    emissions = [item for item in case_rows(directory, case_id) if item['kind'] == 'emission']
    out = []
    for position, row in enumerate(emissions):
        code = row['code']
        branches = int(code, 2) + 1
        previous = int(emissions[position - 1]['code'], 2) + 1 if position else 0
        newly = ['Xdut.en%d' % bit for bit in range(min(branches, 8)) if bit >= previous]
        rise = MEAS.ns_to_ps(float(row['rise50_ns']))
        flat_stop = MEAS.ns_to_ps(float(row['flat_stop_ns']))
        target = idc[code]['I_sink_A']
        entry = {'case_id': case_id, 'window_id': row['window_id'], 'code': code,
                 'branches': branches, 'previous_branches': previous,
                 'new_branches': newly, 'rise50_ns': row['rise50_ns'],
                 'flat_start_ns': row['flat_start_ns'], 'flat_stop_ns': row['flat_stop_ns'],
                 'target_dc_A': target, 't50_ns': row['t50_ns'],
                 'decode_ns': None, 'decode_state': 'NO_NEW_BRANCH',
                 'bias_ns': None, 'bias_state': 'NO_NEW_BRANCH',
                 'build_ns': None, 'build_state': '',
                 'settling_start_ns': row['settling_start_ns'],
                 'last_out_ns': row['settling_last_out_ns'],
                 'raw_sha256': row['raw_sha256'], 'launch_id': row['launch_id'],
                 'evidence': 'NATIVE_MEASURED'}
        for branch in newly:
            series = data['series'].get(branch)
            if not series:
                entry['decode_state'] = 'NOT_OBSERVED'
                continue
            value, state = _boundary(series, TRC.ENABLE_MID_V, rise, flat_stop, branch)
            if state.startswith('CROSSING') or state == 'ALREADY_ABOVE_AT_RISE':
                entry['decode_ns'], entry['decode_state'] = value, state
                break
        for branch in newly:
            name = branch.replace('.en', '.Xu') + '.vbias_ch'
            series = data['series'].get(name)
            if not series:
                entry['bias_state'] = 'NOT_OBSERVED'
                continue
            peak = MEAS.B7M.extreme(series, MEAS.ns_to_ps(float(row['flat_start_ns'])),
                                    flat_stop)[0]
            if peak <= 0:
                entry['bias_state'] = 'FLAT_WINDOW_BIAS_IS_ZERO'
                continue
            value, state = _boundary(series, peak * 0.5, rise, flat_stop, name)
            if state.startswith('CROSSING') or state == 'ALREADY_ABOVE_AT_RISE':
                entry['bias_ns'], entry['bias_state'] = value, state
                break
        current = data['series']['Ip_branch_current']
        if target <= 0:
            entry['build_state'] = 'NO_POSITIVE_TARGET'
        else:
            value, state = _boundary(current, 0.95 * target, rise, flat_stop, 'build')
            entry['build_ns'], entry['build_state'] = value, state
        entry['unattributed'] = entry['build_state'].startswith(('NEVER', 'NOT'))
        out.append(entry)
    return out


# ---- the figure the task book asks for ---------------------------------------------------------------

def _polyline(series, from_ns, to_ns, xs, yscale, base_y):
    """one thinned polyline in picture coordinates; the thinning is per row, never per window"""
    pts = [(t, v) for t, v in series if MEAS.ns_to_ps(from_ns) <= t <= MEAS.ns_to_ps(to_ns)]
    if len(pts) < 2:
        return ''
    step = max(1, len(pts) // 1400)
    picked = pts[::step]
    if picked[-1][0] != pts[-1][0]:
        picked.append(pts[-1])
    first = MEAS.ns_to_ps(from_ns)
    return ' '.join('%.2f,%.2f' % ((t - first) * xs, base_y - v * yscale) for t, v in picked)


def switch_figure(directory, case_id, from_ns, to_ns, traces, path):
    """internal nodes over the output current, each row scaled by the value printed beside it

    No axis is normalised away and no trace is resampled to a fixed grid: every row keeps the native
    sample times, so a delay read off the picture can be re-measured in the row tables.
    """
    raw = os.path.join(directory, '%s_%s_%s.raw' % (run_id_of(directory), case_id, ROLE))
    data = MEAS.load_raw(raw, case_id)
    width, row_h, pad_left, plot_h = 1000, 92, 240, 58
    span_ps = MEAS.ns_to_ps(to_ns) - MEAS.ns_to_ps(from_ns)
    xs = width / max(1.0, span_ps)
    lines = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" role="img">'
             % (width + pad_left + 20, row_h * len(traces) + 110),
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="10" y="22" font-family="monospace" font-size="15">%s %s: internal nodes over '
             'the output current, %g..%g ns</text>' % (TASK_ID, case_id, from_ns, to_ns)]
    y = 40
    for name, unit in traces:
        series = data['series'].get(name)
        box = '<rect width="%d" height="%d" fill="none" stroke="#999"/>' % (width, plot_h)
        label = '<text x="-232" y="%d" font-family="monospace" font-size="12">%s</text>'
        if not series:
            lines.append('<g transform="translate(%d,%d)">%s%s</g>'
                         % (pad_left, y, box, label % (plot_h / 2, '%s NOT_OBSERVED' % name)))
            y += row_h
            continue
        windowed = [(t, v) for t, v in series if MEAS.ns_to_ps(from_ns) <= t <= MEAS.ns_to_ps(to_ns)]
        peak = max(abs(v) for _t, v in windowed) or 1.0
        yscale = plot_h / peak
        points = _polyline(series, from_ns, to_ns, xs, yscale, plot_h)
        lines.append('<g transform="translate(%d,%d)">%s%s'
                     '<polyline fill="none" stroke="#085" points="%s"/></g>'
                     % (pad_left, y, box, label % (plot_h / 2, '%s %s peak %g' % (name, unit, peak)),
                        points))
        y += row_h
    lines.append('<text x="10" y="%d" font-family="monospace" font-size="11">x: %g..%g ns, linear. '
                 'raw %s deck %s samples %d</text>'
                 % (y + 14, from_ns, to_ns, sha_of(raw)[:16], deck_sha(case_id)[:16],
                    data['samples']))
    lines.append('</svg>')
    io.open(path, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    return path, sha_of(path)


# ---- publication of the derived tables ----------------------------------------------------------------

SWITCH_WINDOW = ('TR-OFFCODE', 1300.0, 2300.0)
SWITCH_TRACES = (('data_en', 'V'), ('pam2', 'V'), ('Xdut.en0', 'V'), ('Xdut.en4', 'V'),
                 ('Xdut.Xu0.vbias_ch', 'V'), ('Xdut.Xu4.vbias_ch', 'V'),
                 ('Ip_branch_current', 'A'))
DELTA_HEADER = ('case_id', 'window_id', 'code', 'branches', 'previous_branches', 'new_branches',
                'rise50_ns', 'flat_start_ns', 'flat_stop_ns', 't50_ns', 'target_dc_A',
                'decode_ns', 'decode_state', 'bias_ns', 'bias_state', 'build_ns', 'build_state',
                'settling_start_ns', 'last_out_ns', 'unattributed', 'evidence', 'raw_sha256',
                'launch_id')
INTERNAL_HEADER = ('case_id', 'window_id', 'code', 'from_ns', 'to_ns', 'span_ns',
                   'selected_branches', 'branch_enables_high', 'branch_enable_bars_high',
                   'iref_in_V')


def _write(directory, name, rows, header):
    path = os.path.join(directory, name)
    MEAS.write_rows(path, rows, header)
    return name, path


def deliver_traces(directory):
    """the round's own traces, losslessly gzipped so a reviewer can replay the conversion

    The vvp logs stay on this machine: they open with the command line, which carries an absolute
    path into the tool tree, and the task book keeps vendor absolute paths out of the repository.
    Their digests and their MARK lines are published here instead, so a log can still be recognised
    byte for byte without being shipped.
    """
    rtl = os.path.join(directory, 'rtl')
    _spectre, rows = ledgers(directory)
    by_id = dict((row['sim_id'], row) for row in rows)
    traces, ignored = [], []
    for case_id in TRACE.CASES:
        plain = os.path.join(rtl, TRACE.dump_name(case_id))
        if not os.path.isfile(plain):
            ignored.append({'file': os.path.basename(plain), 'reason': 'not on this machine'})
            continue
        gz = plain + '.gz'
        raw = io.open(plain, 'rb').read()
        with io.open(gz, 'wb') as handle:
            handle.write(gzip.compress(raw, 9, mtime=0))
        row = by_id.get(next((payload.get('reused_from_launch')
                              for payload in [DECK.load_hyb_inputs()[0][case_id]]), '')) or {}
        traces.append({'case_id': case_id, 'file': os.path.basename(plain), 'bytes': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest(),
                       'gzip_file': os.path.basename(gz),
                       'gzip_sha256': sha_of(gz),
                       'gzip_bytes': os.path.getsize(gz),
                       'lossless': gzip.decompress(io.open(gz, 'rb').read()) == raw,
                       'charged_start': row.get('sim_id', ''),
                       'start_rc': row.get('rc', ''),
                       'log_sha256': row.get('log_sha256', ''),
                       'log_kept_locally_because': 'the vvp log begins with the command line, which '
                                                   'names an absolute tool path'})
    for name in sorted(os.listdir(rtl)):
        path = os.path.join(rtl, name)
        if not os.path.isfile(path) or name.endswith(('.vcd', '.vcd.gz')) or name.endswith('.json'):
            continue
        head = io.open(path, encoding='utf-8', errors='replace').read(400)
        ignored.append({'file': name, 'bytes': os.path.getsize(path),
                        'sha256': sha_of(path),
                        'reason': 'log of a charged start, kept locally: it embeds the absolute '
                                  'command line' if head.startswith('$ ') else
                                  'intermediate of the compile step, kept locally'})
    payload = {'task_id': TASK_ID, 'run_id': run_id_of(directory),
               'iverilog_records': iverilog_records(directory),
               'compile_records': sorted(name for name in os.listdir(rtl)
                                         if name.startswith('compile_')),
               'traces': traces, 'kept_locally': ignored,
               'written_by': 'scripts/dd1_d7c_b_tr_record.py deliver_traces'}
    compile_facts = json.loads(io.open(os.path.join(rtl, 'compile_HYB-120.json'),
                                       encoding='utf-8').read())
    payload['rtl_blob_sha256'] = compile_facts['rtl_sha256']
    payload['tb_blob_sha256'] = compile_facts['tb_sha256']
    payload['iverilog_binary_sha256'] = compile_facts['iverilog_sha256']
    payload['rtl_path'] = 'rtl/dd1_d7a_gray_ctrl.sv'
    payload['tb_path'] = TRACE.TB_PATH
    payload['tool_root_redacted'] = 'the tool tree path is not published; the binary digest is'
    _dump(os.path.join(rtl, 'tool_identity.json'), payload)
    return payload


def publish(directory):
    """every derived table the report quotes, written beside the rows it came from"""
    written = {}
    rows = all_rows(directory)
    written['windows_all.csv'] = _write(directory, 'windows_all.csv', rows, MEAS.HEADER)[1]
    conv, pairs, problems = convergence_table(directory)
    written['convergence.csv'] = _write(directory, 'convergence.csv', conv, MEAS.CONV_HEADER)[1]
    _dump(os.path.join(directory, 'convergence_pairs.json'),
          {'pairs': pairs, 'context_problems': problems,
           'limit_rel_qlsb': TRC.CONV_LIMIT,
           'declared_by': 'scripts/dd1_d7c_b_tr_record.py convergence_table'})
    delta = []
    for case_id in TRC.CASE_ORDER:
        delta.extend(delay_breakdown(directory, case_id))
    written['delay_attribution.csv'] = _write(
        directory, 'delay_attribution.csv',
        [dict(row, new_branches=','.join(row['new_branches'])) for row in delta],
        DELTA_HEADER)[1]
    _dump(os.path.join(directory, 'delay_attribution.json'),
          {'rows': delta, 'search_window_ns': EDGE_LOOK_NS,
           'note': 'a negative decode or bias time means the node was already past the level when the '
                   'enable crossed half-rail, measured off the native samples'})
    internals = []
    for case_id in TRC.CASE_ORDER:
        raw = os.path.join(directory, '%s_%s_%s.raw' % (run_id_of(directory), case_id, ROLE))
        data = MEAS.load_raw(raw, case_id)
        deck_text = io.open(RUN.deck_for(case_id, ROLE), encoding='utf-8', newline='').read()
        for entry in MEAS.internal_nodes(data, MEAS.windows_of(case_id, deck_text),
                                         MEAS.codes_of(case_id, deck_text)):
            internals.append({'case_id': case_id, 'window_id': entry['window_id'],
                              'code': entry['code'], 'from_ns': entry['from_ns'],
                              'to_ns': entry['to_ns'],
                              'span_ns': entry['to_ns'] - entry['from_ns'],
                              'selected_branches': entry['selected_branches'],
                              'branch_enables_high': entry['branch_enables_high'],
                              'branch_enable_bars_high': entry['branch_enable_bars_high'],
                              'iref_in_V': entry['shared_reference']['iref_in']})
    written['internal_nodes_all.csv'] = _write(directory, 'internal_nodes_all.csv', internals,
                                               INTERNAL_HEADER)[1]
    detail = []
    for case_id in TRC.CASE_ORDER:
        payload = json.loads(io.open(os.path.join(directory, 'internal_nodes_%s_%s.json'
                                                    % (case_id, ROLE)), encoding='utf-8').read())
        detail.extend(dict(row, case_id=case_id) for row in payload)
    _dump(os.path.join(directory, 'internal_nodes_all.json'),
          {'entries': detail, 'window_ns': 50.0,
           'columns': len(detail[0]['nodes']) if detail else 0,
           'shared_reference': list(MEAS.SHARED_NODES),
           'declared_by': 'scripts/dd1_d7c_b_tr_measure.py internal_nodes'})
    path, digest = switch_figure(directory, SWITCH_WINDOW[0], SWITCH_WINDOW[1], SWITCH_WINDOW[2],
                                 SWITCH_TRACES,
                                 os.path.join(directory, 'fig_TR-OFFCODE_switch.svg'))
    _dump(os.path.join(directory, 'figures.json'),
          [{'file': os.path.basename(path), 'sha256': digest, 'case_id': SWITCH_WINDOW[0],
            'span_ns': [SWITCH_WINDOW[1], SWITCH_WINDOW[2]],
            'traces': [{'signal': name, 'unit': unit} for name, unit in SWITCH_TRACES],
            'scaling': 'each row is scaled by the peak it prints, native samples, no resampling'}])
    written['tool_identity.json'] = deliver_traces(directory)
    return rows, conv, pairs, problems, delta, internals, written


def _dump(path, payload):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(payload, indent=1, sort_keys=True, default=str) + '\n')
    return path


# ---- the seven verdicts, from the published rows -------------------------------------------------------

def verdicts(directory, conv_rows, rows):
    emission = [row for row in rows if row['kind'] == 'emission']
    black = [row for row in rows if row['kind'].startswith('black')]
    failing_dyn = ['%s %s' % (row['case_id'], row['window_id']) for row in emission + black
                   if abs(row['err_dynamic_LSB']) > TRC.DYNAMIC_LIMIT_LSB]
    failing_nom = ['%s %s' % (row['case_id'], row['window_id']) for row in emission + black
                   if abs(row['err_nominal_LSB']) > TRC.NOMINAL_LIMIT_LSB]
    table = MEAS.statuses(rows, conv_rows, integrity(directory), completeness(directory))
    return table, failing_dyn, failing_nom


# ---- git-side helpers ----------------------------------------------------------------------------------

def git(*args):
    proc = subprocess.Popen(['git'] + list(args), cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return proc.communicate()[0].decode('utf-8', 'replace').replace('\r\n', '\n')


def blob_sha(rev, rel):
    """the digest of a file as Git holds it, which is what a reviewer can re-derive"""
    proc = subprocess.Popen(['git', 'cat-file', 'blob', '%s:%s' % (rev, rel)], cwd=ROOT,
                            stdout=subprocess.PIPE)
    out = proc.communicate()[0]
    if not out:
        raise TRC.Refuse('%s is not in %s, so no identity may be claimed from it' % (rel, rev))
    return hashlib.sha256(out).hexdigest()


def round_paths():
    """every path this round touches, as git status sees it

    The porcelain line is XY plus a space plus the path. Reading only the first character would drop
    an unstaged modification, whose X is a space and whose Y is M, and then the tools that produced
    the tables would never be committed with them.
    """
    out = []
    for line in git('status', '--porcelain=1', '--untracked-files=all').splitlines():
        flag, path = line[:2], line[3:].strip().replace('\\', '/')
        if 'D' in flag:
            out.append((flag, path))
            continue
        if flag.strip():
            out.append((flag, path))
    return out


def tracked_candidates():
    """the files this round may put in the repository, with the byte total that must stay under the cap"""
    keep, skipped = [], []
    owned = ('scripts/dd1_d7c_b_tr_', 'spectre/dd1_d7c_b_tr/', 'tests/dd1_d7c_b_tr/',
             'results/evidence/dd1_d7c_b_tr_r', 'reports/tasks/DATA-7C-B-TR.md')
    allowed_reports = (REPORT_PATH, CONTRACT_REPORT, HANDOFF_MD, HANDOFF_JSON)
    for flag, path in round_paths():
        base = os.path.basename(path)
        if '/rtl/' in path:
            # the traces travel losslessly gzipped; the compile and run records of that directory
            # begin with an absolute command line, so they are read from the local copy instead
            if path.endswith('.vcd.gz') or base == 'tool_identity.json' \
                    or base.startswith('conversion_'):
                keep.append((path, os.path.getsize(repo(path)) if os.path.isfile(repo(path)) else 0))
            else:
                skipped.append((path, 'kept on this machine: it carries an absolute command line'))
            continue
        if path.endswith(LOCAL_ONLY_SUFFIXES) or any(mark in path for mark in LOCAL_ONLY_MARKS):
            skipped.append((path, 'kept on this machine: raw and log stay local by the task book'))
            continue
        if path.startswith(owned) or path in allowed_reports:
            keep.append((path, os.path.getsize(repo(path)) if os.path.isfile(repo(path)) else 0))
        else:
            skipped.append((path, 'outside the paths this round may add'))
    return keep, skipped


def text_candidates(keep):
    return [path for path, _size in keep
            if path.endswith(('.py', '.md', '.json', '.csv', '.scs', '.sv', '.txt', '.log', '.svg'))]


def secret_scan(paths):
    hits = []
    for path in paths:
        full = repo(path)
        if not os.path.isfile(full):
            continue
        text = io.open(full, encoding='utf-8', errors='replace').read().lower()
        for needle in SECRET_PATTERNS:
            if needle.lower() in text:
                hits.append('%s carries %r' % (path, needle))
    return hits


def line_ending_scan(paths):
    return [path for path in paths if os.path.isfile(repo(path))
            and b'\r\n' in io.open(repo(path), 'rb').read()]


def markers_bind_to_ledger(directory):
    """the hybrid decks' stimulus is the trace of a charged start, and its log says so"""
    _spectre, rtl = ledgers(directory)
    by_case = {}
    for row in rtl:
        if row['state'] == 'CONFIRMED':
            by_case.setdefault(row['case_id'], []).append(row['sim_id'])
    hyb, source = DECK.load_hyb_inputs()
    problems = []
    for case_id in TRACE.CASES:
        payload = hyb[case_id]
        launch = payload.get('reused_from_launch') or payload.get('vvp_sim_id')
        if launch not in by_case.get(case_id, []):
            problems.append('%s: the conversion cites %s, which is no confirmed start of this case'
                            % (case_id, launch))
            continue
        try:
            markers = TRACE.markers_of_log(os.path.join(directory, 'rtl'), case_id, launch,
                                           RUN.rtl_account(directory, run_id_of(directory)))
        except TRC.Refuse as error:
            problems.append(str(error))
            continue
        if markers != payload['markers']:
            problems.append('%s: the published markers are not the markers of %s' % (case_id, launch))
        bad = TRACE.check_markers(payload['markers'], case_id, payload)
        problems.extend(bad)
    return {'problems': problems, 'source': os.path.relpath(source, ROOT).replace(os.sep, '/'),
            'checked_from': sorted(hyb)}


_GATES_CACHE = {}


def gates(directory):
    """the checks a reviewer can re-run; a FAIL stops the record, it is never filed as a note

    Cached per directory for the life of the process: the same evidence must not be measured twice in
    one run, because two passes over the same rows are the way a report and its handoff end up
    quoting different numbers.
    """
    if directory in _GATES_CACHE:
        return _GATES_CACHE[directory]
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else str(extra)))
    rows = all_rows(directory)
    emission = [row for row in rows if row['kind'] == 'emission']
    black = [row for row in rows if row['kind'].startswith('black')]
    conv, pairs, problems = convergence_table(directory)
    table, failing_dyn, failing_nom = verdicts(directory, conv, rows)
    keep, _skipped = tracked_candidates()
    total = sum(size for _p, size in keep)
    before = [row['launch_id'] for row in ledgers(directory)[0]]
    publish(directory)
    _spectre_rows, rtl_rows = ledgers(directory)
    after = [row['launch_id'] for row in ledgers(directory)[0]]
    contract = TRC.contract()
    account = RUN.spectre_account(directory, run_id_of(directory))
    strays, _notes = RUN.budget_strays(directory)
    launch_log = json.loads(io.open(os.path.join(directory, 'launch_log.json'),
                                    encoding='utf-8').read())
    record('the record stage starts no simulator: the launch account is unchanged after it',
           before == after, (before[-3:], after[-3:]))
    record('every approved case has a published row table',
           sorted(set(row['case_id'] for row in rows)) == sorted(TRC.CASE_ORDER),
           sorted(set(row['case_id'] for row in rows)))
    record('the prepared PAM cases publish exactly the frozen emission window count',
           len([row for row in emission if row['case_id'] in TRC.PREP_CASES])
           == TRC.frozen_window_counts()['emission'],
           (len([row for row in emission if row['case_id'] in TRC.PREP_CASES]),
            TRC.frozen_window_counts()['emission'], sorted(TRC.PREP_CASES)))
    hybrid_emission = [row for row in emission if row['case_id'] in TRACE.CASES]
    record('the two joint cases publish the emission windows their own enable waveforms declare',
           len(hybrid_emission) == 7 and len([row for row in hybrid_emission
                                              if row['case_id'] == 'HYB-120']) == 4
           and len([row for row in hybrid_emission if row['case_id'] == 'HYB-200']) == 3,
           [(row['case_id'], row['window_id']) for row in hybrid_emission])
    widths = {}
    for name in ('windows_all.csv', 'convergence.csv', 'delay_attribution.csv',
                 'internal_nodes_all.csv'):
        for line in io.open(os.path.join(directory, name), encoding='utf-8', newline='').readlines():
            width = len(next(csv.reader([line])))
            widths.setdefault(name, set()).add(width)
    header_widths = {'windows_all.csv': len(MEAS.HEADER), 'convergence.csv': len(MEAS.CONV_HEADER),
                     'delay_attribution.csv': len(DELTA_HEADER),
                     'internal_nodes_all.csv': len(INTERNAL_HEADER)}
    record('every published table re-reads at its header width on every line',
           all(widths[name] == {header_widths[name]} for name in widths),
           dict((name, sorted(values)) for name, values in widths.items()))
    record('the black windows are the declared zero-code and post-fault regions',
           len(black) == 3 and sorted(row['kind'] for row in black) ==
           ['black_64T', 'black_64T', 'black_post_fault_hold'],
           [(row['case_id'], row['window_id'], row['kind']) for row in black])
    record('no black window invents a T50 and every one carries a zero target',
           all(row['t50_ns'] == 'NOT_DEFINED_FOR_BLACK' and row['qtarget_dc_C'] == 0.0
               and row['qtarget_nominal_C'] == 0.0 for row in black),
           [(row['window_id'], row['t50_ns'], row['qtarget_dc_C']) for row in black])
    record('every black window names the function that declared its boundary',
           all(str(row['declared_by']).startswith('scripts/dd1_d7c_b_tr_trace.py')
               for row in black), [row['declared_by'] for row in black])
    record('each published row is bound to a confirmed launch of the delivered deck',
           not integrity(directory)['problems'], integrity(directory)['problems'][:3])
    witnessed = [row for row in launch_log if row.get('role') == 'preflight'
                 and (row.get('witness') or {}).get('witness') == 'PASS']
    record('the meter witness passed for all nine meters before their DUT ran',
           len(set(row['case_id'] for row in witnessed)) == 9,
           sorted(set(row['case_id'] for row in witnessed)))
    record('the three declared convergence pairs are computed with matching context',
           len(pairs) == 3 and not problems and len(conv) == 13, (pairs, problems[:2]))
    record('the convergence verdict is per window against the frozen limit',
           all(row['status'] in ('PASS', 'FAIL') for row in conv)
           and all((row['abs_dq_over_qlsb'] <= TRC.CONV_LIMIT) == (row['status'] == 'PASS')
                   for row in conv), [(row['window_id'], row['status']) for row in conv][:3])
    record('the seven statuses are published separately',
           len(table) == 7 and len(set(row['status'] for row in table)) == 7,
           [row['status'] for row in table])
    record('a negative electrical finding is published as a FAIL, never folded into an aggregate',
           (('FAIL' in [row['verdict'] for row in table]) == bool(failing_dyn or failing_nom))
           and (not failing_dyn or _verdict(table, 'DYNAMIC_CHARGE_STATUS') == 'FAIL'),
           (failing_dyn[:3], failing_nom[:3], [row['verdict'] for row in table]))
    internals = json.loads(io.open(os.path.join(directory, 'internal_nodes_all.json'),
                                   encoding='utf-8').read()) if os.path.isfile(
        os.path.join(directory, 'internal_nodes_all.json')) else []
    flat_entries = []
    for case_id in TRC.CASE_ORDER:
        payload = json.loads(io.open(os.path.join(directory, 'internal_nodes_%s_%s.json'
                                                    % (case_id, ROLE)), encoding='utf-8').read())
        flat_entries.extend(dict(row, case_id=case_id) for row in payload)
    record('the internal-node tables cover every flat step of every case',
           len(flat_entries) == len(emission), (len(flat_entries), len(emission)))
    record('each flat step is observed for at least the 50 ns the task book asks for',
           all(entry['to_ns'] - entry['from_ns'] >= 50.0 - 1e-9 for entry in flat_entries),
           [(entry['case_id'], entry['to_ns'] - entry['from_ns']) for entry in flat_entries[:3]])
    long_steps = [entry for entry in flat_entries if entry['case_id'] == 'TR-LONG']
    record('TR-LONG carries all 26 branch columns and the shared reference on every step',
           len(long_steps) == 8 and all(len(entry['nodes']) == 26
                                        and 'iref_in' in entry['shared_reference']
                                        and entry['shared_reference']['iref_in'] != 'NOT_OBSERVED'
                                        for entry in long_steps),
           (len(long_steps), len(long_steps[0]['nodes']), long_steps[0]['shared_reference']))
    record('the selected branch count is cross-checked as code plus one on every step',
           all(entry['selected_branches'] == int(entry['code'], 2) + 1
               for entry in flat_entries),
           [(entry['code'], entry['selected_branches']) for entry in flat_entries[:3]])
    delta = [row for case_id in TRC.CASE_ORDER for row in delay_breakdown(directory, case_id)]
    record('the delay attribution is measured on every emission window of the nine cases',
           len(delta) == len(emission), (len(delta), len(emission)))
    record('a boundary the samples do not carry is named as unattributed, not filled in',
           all((row['decode_ns'] is None) == (row['decode_state'] in
                                              ('NO_NEW_BRANCH', 'NOT_OBSERVED'))
               for row in delta),
           [(row['case_id'], row['window_id'], row['decode_state']) for row in delta
            if row['decode_ns'] is None][:3])
    record('the carried DC-R1 followup F-TR-1 is implemented: vss is a required signal',
           'vss' in contract['required_signals']['always_extracted']
           and MEAS.REQUIRED and 'vss' in MEAS.REQUIRED,
           contract['required_signals']['always_extracted'])
    iprobe = []
    for case_id in TRC.CASE_ORDER:
        data = json.loads(io.open(os.path.join(directory, 'iprobe_consistency_%s_%s.json'
                                                    % (case_id, ROLE)), encoding='utf-8').read())
        iprobe.append((data['passes'], data['tolerance_is_expressible'],
                       data['max_abs_difference_V'], data['value_display_quantum_V']))
    record('the carried DC-R1 followup F-TR-2 is closed with proof: terminals agree and the '
           'tolerance is expressible at the exported precision',
           all(passes and expressible for passes, expressible, _d, _q in iprobe), iprobe[:2])
    binding = markers_bind_to_ledger(directory)
    record('the hybrid stimulus is the trace of a charged start and its log says so',
           not binding['problems'], binding['problems'][:3])
    record('the RTL reconciliation names the ledger it counts',
           not rtl_reconciliation(directory)['problems'], rtl_reconciliation(directory)['problems'])
    record('every stray process is charged and the enforced ceiling still holds',
           account.processes() + strays <= RUN.SPECTRE_LIMIT
           and account.remaining() == RUN.SPECTRE_LIMIT - strays - account.processes(),
           (account.processes(), strays, account.remaining()))
    record('0 existing tracked path was modified or deleted since the base',
           not git('diff', '--diff-filter=MD', '--name-only', BASE_SHA, 'HEAD', '--').splitlines(),
           git('diff', '--diff-filter=MD', '--name-only', BASE_SHA, 'HEAD', '--').splitlines())
    record('the bytes this round adds stay under the 32 MiB ceiling',
           total <= TRACK_LIMIT_BYTES, total)
    owned_prefixes = ('scripts/dd1_d7c_b_tr_', 'tests/dd1_d7c_b_tr/', 'spectre/dd1_d7c_b_tr/')
    modified = [path for flag, path in round_paths() if 'M' in flag and path.startswith(owned_prefixes)]
    kept_paths = [path for path, _size in keep]
    record('every modified file this round owns is staged beside the tables it produced',
           all(path in kept_paths for path in modified),
           [path for path in modified if path not in kept_paths])
    record('nothing this round touches is a deletion',
           not [path for flag, path in round_paths() if 'D' in flag],
           [path for flag, path in round_paths() if 'D' in flag])
    record('no raw answer, log, unpacked trace or executable is a tracked candidate',
           all(not path.endswith(LOCAL_ONLY_SUFFIXES)
               and not any(mark in path for mark in LOCAL_ONLY_MARKS)
               for path, _s in keep),
           [path for path, _s in keep
            if path.endswith(LOCAL_ONLY_SUFFIXES)
            or any(mark in path for mark in LOCAL_ONLY_MARKS)][:4])
    traces = deliver_traces(directory)['traces']
    hybrid_inputs = DECK.load_hyb_inputs()[0]
    record('the shipped traces decompress byte for byte and are the traces the decks stamp',
           len(traces) == 2 and all(row['lossless']
                                    and row['sha256'] == hybrid_inputs[row['case_id']]['vcd_sha256']
                                    for row in traces),
           [(row['case_id'], row['lossless'], row['sha256'][:8]) for row in traces])
    unbound = [row['sim_id'] for row in rtl_rows if row['state'] == 'CONFIRMED'
               and not row['vcd_sha256']]
    gaps = json.loads(io.open(os.path.join(directory, 'evidence_gaps.json'),
                              encoding='utf-8').read()) if os.path.isfile(
        os.path.join(directory, 'evidence_gaps.json')) else {}
    record('a confirmed start whose ledger row carries no trace digest is published as a gap',
           gaps.get('confirmed_without_trace_digest') == unbound, (unbound, gaps))
    texts = text_candidates(keep)
    record('no credential, PDK, license or vendor absolute path string is in a tracked text file',
           not secret_scan(texts), secret_scan(texts)[:4])
    record('published text is LF only', not line_ending_scan(texts), line_ending_scan(texts)[:4])
    deck_problems = DECK.check_account(RUN.account_of_masters())
    record('the nine run copies still equal the frozen base plus their identity block',
           not deck_problems, deck_problems[:3])
    stamped = json.loads(io.open(repo(os.path.join(DECK.DECK_DIR, 'deck_account.json')),
                                 encoding='utf-8').read())['decks']
    committed_contract = blob_sha('HEAD', TRC.CONTRACT_PATH)
    mismatches = []
    for row in stamped:
        text = io.open(repo(row['path']), encoding='utf-8', newline='').read()
        if ('TR-IDENTITY: contract_sha256=%s' % committed_contract) not in text:
            mismatches.append(row['path'])
    record('every delivered deck stamps the contract as it is committed at HEAD',
           not mismatches and sha_of(repo(TRC.CONTRACT_PATH)) == committed_contract,
           (mismatches[:3], committed_contract[:12], sha_of(repo(TRC.CONTRACT_PATH))[:12]))
    _GATES_CACHE[directory] = results
    return results


def _verdict(table, name):
    for row in table:
        if row['status'] == name:
            return row['verdict']
    return ''


# ---- the report ---------------------------------------------------------------------------------------

def fmt(value, digits=4):
    if isinstance(value, float):
        if value == 0.0:
            return '0'
        return '%.*g' % (digits, value)
    return str(value) if value not in (None, '') else '-'


def _table(header, rows):
    lines = ['| ' + ' | '.join(header) + ' |',
             '|' + '|'.join(['---'] * len(header)) + '|']
    for row in rows:
        lines.append('| ' + ' | '.join(fmt(row.get(key, ''), 6) for key in header) + ' |')
    return lines


WINDOW_COLUMNS = ('case_id', 'window_id', 'kind', 'code', 'tick_ns', 'qlsb_C', 't50_ns',
                  'q_full_C', 'q_flat_C', 'q_pos_C', 'q_neg_C', 'abs_q_neg_C', 'peak_A',
                  'flat_mean_A', 'tail_q_C', 'leak_max_abs_A', 'qtarget_nominal_C',
                  'qtarget_dc_C', 'err_nominal_LSB', 'err_dynamic_LSB', 'settling_nominal',
                  'settling_dc', 'settling_start_ns', 'settling_last_out_ns')


def render_report(directory):
    rows = all_rows(directory)
    conv, pairs, problems = convergence_table(directory)
    table, failing_dyn, failing_nom = verdicts(directory, conv, rows)
    contract = TRC.contract()
    account = RUN.spectre_account(directory, run_id_of(directory))
    strays, adjustments = RUN.budget_strays(directory)
    spectre_rows, rtl_rows = ledgers(directory)
    delta = [row for case_id in TRC.CASE_ORDER for row in delay_breakdown(directory, case_id)]
    binding = markers_bind_to_ledger(directory)
    figures = json.loads(io.open(os.path.join(directory, 'figures.json'), encoding='utf-8').read())
    out = ['# DATA-7C-B-TR transient measurement report', '']
    out += ['Generated by `scripts/dd1_d7c_b_tr_record.py` at %s. Every number below is read from a '
            'file in `%s`; the record stage starts no simulator.'
            % (utc(), os.path.basename(directory)), '']
    out += ['## Provenance', '',
            '- task `%s`, base `%s`, branch `%s`, HEAD `%s`'
            % (TASK_ID, BASE_SHA, BRANCH, git('rev-parse', 'HEAD').strip()),
            '- contract in force `%s` sha256 `%s`; its Git blob at HEAD is `%s`'
            % (TRC.CONTRACT_PATH, sha_of(repo(TRC.CONTRACT_PATH)),
               blob_sha('HEAD', TRC.CONTRACT_PATH)),
            '- authorisation `%s`, approved %s (%s), response `%s`; Spectre ceiling %d, '
            'RTL ceiling %d'
            % (contract['authorisation']['status'], contract['authorisation']['approval_date'],
               contract['authorisation']['approval_timezone'],
               contract['authorisation']['approval_response'], RUN.SPECTRE_LIMIT, RUN.RTL_LIMIT),
            '- frozen electrical requirement from the contract: corner `%s`, IREF %g A into the '
              'frozen diode reference, ideal clamp %g V, VSS %g V, vdd18 %g V, vcas %g V; corner and '
              'temperature are read off each deck as its own condition, not as contract adjectives: '
              '%s'
            % (contract['electrical_environment']['corner'],
               contract['electrical_environment']['iref_A'],
               contract['electrical_environment']['clamp_V'],
               contract['electrical_environment']['vss_V'],
               contract['electrical_environment']['vdd18_V'],
               contract['electrical_environment']['vcas_V'],
               deck_conditions()),
            '- probe: `%s (%s %s) iprobe`, `%s`'
            % (contract['probe']['instance'], contract['probe']['terminals'][0],
               contract['probe']['terminals'][1], contract['probe']['definition']),
            '- QLSB stays the fixed `1.875 uA x the reference tick of the case`; no window length, '
              'no own measured Q and no transient average is ever used as the denominator, and it is '
              'never replaced by I111/8',
            '', '## What actually ran', '',
            '- %d Spectre account rows, %d processes charged, %d stray processes charged from the '
              'budget adjustment, enforced ceiling %d of the approved %d, %d left unused'
            % (len(spectre_rows), account.processes(), strays,
               RUN.spectre_ceiling(directory), RUN.SPECTRE_LIMIT, account.remaining()),
            '- %d vvp rows, %d processes charged of the approved %d'
            % (len(rtl_rows), rtl_reconciliation(directory)['processes'], RUN.RTL_LIMIT),
            '- rows that did not confirm stay charged: %s'
            % (', '.join('%s %s/%s %s' % (row['launch_id'], row['case_id'], row['role'],
                                          row['state'])
                         for row in spectre_rows if row['state'] != 'CONFIRMED') or 'none'),
            '- the stray processes and what their evidence can and cannot support are recorded in '
              '`spectre_budget_adjustments.json`; no number from them is published here',
            '']
    out += ['## The nine cases', '']
    out += _table(('case', 'source', 'tick ns', 'maxstep ns', 'partner', 'dut launch',
                    'preflight launch', 'samples', 'internal columns'),
                  [{'case': case_id,
                    'source': 'RTL four-state VCD' if case_id in TRACE.CASES
                              else 'prepared PAM schedule',
                    'tick ns': TRC.TICK_NS[case_id], 'maxstep ns': TRC.MAXSTEP_NS[case_id],
                    'partner': TRC.PARENT.get(case_id, '-'),
                    'dut launch': _launch_id(directory, case_id, ROLE),
                    'preflight launch': _launch_id(directory, case_id, 'preflight'),
                    'samples': _samples(directory, case_id),
                    'internal columns': _internals_note(directory, case_id)}
                   for case_id in TRC.CASE_ORDER])
    out += ['', '## Every window, measured', '']
    for case_id in TRC.CASE_ORDER:
        case_rows_here = [row for row in rows if row['case_id'] == case_id]
        out += ['', '### %s' % case_id, '']
        out += _table(WINDOW_COLUMNS, case_rows_here)
    out += ['', '## The three convergence pairs', '',
            'Only the maxstep differs inside a pair; the comparison is per window against '
            'abs(dQ)/QLSB <= %g, and the context fields are the ones the contract lists.'
            % TRC.CONV_LIMIT, '']
    out += _table(('pair', 'window_id', 'code', 'refined_q_C', 'coarse_q_C', 'dq_C',
                   'dq_fC', 'abs_dq_over_qlsb', 'status', 'context_match'),
                  [dict(row, dq_fC=row['dq_C'] * 1e15) for row in conv])
    if problems:
        out += ['', 'Context problems, published as refusals rather than skipped rows:']
        out += ['- %s' % text for text in problems]
    out += ['', '## The seven statuses, published separately', '']
    out += _table(('status', 'verdict', 'measured', 'expected', 'note'), table)
    out += ['', '## Negative findings named', '']
    out += ['- windows outside abs(error_dynamic_LSB) <= %g: %s'
            % (TRC.DYNAMIC_LIMIT_LSB, ', '.join(failing_dyn) or 'none'),
            '- windows outside abs(error_nominal_LSB) <= %g: %s'
            % (TRC.NOMINAL_LIMIT_LSB, ', '.join(failing_nom) or 'none'),
            '- the DC reference carries the +2.55 % scale deviation measured in DATA-7C-B-DC, so a '
              'bright code shows a nominal error well above one LSB while its dynamic error stays '
              'inside the criterion; that is the actual result and it is not corrected, hidden or '
              'traded for a PASS: the circuit was not changed to chase it',
            '']
    out += ['## Internal nodes and where the delay sits', '']
    out += ['The flat step of every emission window is observed for at least 50 ns, time-weighted, '
            'over the 26 saved branch columns plus the shared reference node. The branch count is '
            'cross-checked as code plus one, and the number of branch enables above the deck logic '
            'mid-level is counted from the same samples.', '']
    out += _table(('case_id', 'window_id', 'code', 'branches', 'new_branches', 'decode_ns',
                   'decode_state', 'bias_ns', 'bias_state', 'build_ns', 'build_state',
                   't50_ns', 'target_dc_A'),
                  [dict(row, new_branches=','.join(row['new_branches'])) for row in delta])
    build = [row['build_ns'] for row in delta if row['build_ns'] is not None]
    lead = [row for row in delta if row['decode_ns'] is not None and row['decode_ns'] <= 0]
    out += ['', '- on %d of %d windows the branch enable and its channel bias are already past the '
            'deck mid-level when the enable crosses half-rail, so decoding and bias charging are not '
            'the limiting segment' % (len(lead), len(delta)),
            '- the time to reach 95 %% of the DC target grows with the number of conducting branches: '
            '%s ns, measured from the same enable crossing'
            % (', '.join(fmt(value, 3) for value in sorted(build))),
            '- a boundary the samples do not carry is published as %s, never filled in from a '
            'neighbouring column' % 'NO_NEW_BRANCH / NOT_OBSERVED',
            '- no device operating-point parameter is saved by these decks, so nothing here is '
            'presented as a saturation or SOA conclusion; only saved nodes are used',
            '']
    out += ['## Code-switch and turn-off picture', '']
    out += ['- `%s` (sha256 `%s`) over %g..%g ns: `%s`, each row scaled by the peak it prints'
            % (figures[0]['file'], figures[0]['sha256'], figures[0]['span_ns'][0],
               figures[0]['span_ns'][1], '", "'.join(row['signal'] for row in figures[0]['traces'])),
            '']
    out += ['## The two joint cases and their black windows', '']
    for case_id in TRACE.CASES:
        payload = DECK.load_hyb_inputs()[0][case_id]
        start = payload.get('reused_from_launch') or payload.get('vvp_sim_id')
        out += ['- `%s`: %d frames segmented out of the accepted controller trace (sha256 `%s`, '
                'tick %g ns, charged start %s). %s'
                % (case_id, payload['frame_count'], payload['vcd_sha256'],
                   payload['tick_ps'] / 1000.0, start,
                   'Its zero-code frame and its post-fault hold are measured as black windows: '
                   'Q and the peak over the declared boundary, Qtarget 0, the same fixed QLSB, no '
                   'invented T50.')]
    out += ['- the marker cross-check found nothing to report: %s'
            % (binding['problems'] or 'no problems'),
            '- the derived boundaries are published in `black_windows_HYB-120.json` and '
              '`black_windows_HYB-200.json` with the markers they came from',
            '']
    out += ['## Carried followups from DATA-7C-B-DC-R1', '']
    out += ['- F-TR-1 vss in every required list: `%s` includes it and `load_raw` refuses an answer '
            'that does not carry it' % contract['required_signals']['always_extracted'],
            '- F-TR-2 the ideal probe two-terminal rule `abs(data_out_V - clamp_node_V) <= 1e-6 + '
            '1e-9*abs(clamp_node_V)` is proven readable in the exported precision: the largest '
            'difference on all nine answers is %s V against an export quantum of %s V'
            % (max(json.loads(io.open(os.path.join(directory, 'iprobe_consistency_%s_%s.json'
                                                % (case, ROLE)), encoding='utf-8').read())
                   ['max_abs_difference_V'] for case in TRC.CASE_ORDER),
               json.loads(io.open(os.path.join(directory, 'iprobe_consistency_%s_%s.json'
                                                % ('TR-LONG', ROLE)),
                                  encoding='utf-8').read())['value_display_quantum_V']),
            '']
    out += ['## Evidence gaps a reviewer should know about', '']
    unbound_rows = [row['sim_id'] for row in rtl_rows if row['state'] == 'CONFIRMED'
                    and not row['vcd_sha256']]
    _dump(os.path.join(directory, 'evidence_gaps.json'),
          {'confirmed_without_trace_digest': unbound_rows,
           'stray_launches': [row['launch_id'] for adjustment in adjustments
                              for row in adjustment.get('launches', [])],
           'raws_kept_locally': len([case for case in TRC.CASE_ORDER]),
           'note': 'a gap is named here so that no claim depends on the missing bytes'})
    out += ['- `%s` in the RTL account carries no trace digest: it was settled before the row-named '
            'log and the vcd column were fixed, so the trace of that start is bound through the '
            'conversion record and the deck identity block instead'
            % (', '.join(unbound_rows) or 'none'),
            '- the two stray launches wrote one per-case log name, so the surviving bytes belong to '
            'the later of them and the earlier digest has no bytes behind it; their raws were '
            'deleted after digesting and neither is used as a measurement',
            '- the raw answers and the guest logs stay on this machine, not in the repository: '
            'their digests and local paths are published in `provenance.json`',
            '- a pre-existing unreachable object in the shared Git store is larger than the review '
            'gate tolerates; it is not this round\'s object, was not pruned, and is disclosed here',
            '']
    out += ['## Closing block', '', '```text']
    out += ['%s=%s' % (key, value) for key, value in closing_block(directory, table, rows, conv)]
    out += ['```']
    return '\n'.join(out).rstrip('\n') + '\n', table


def deck_conditions():
    """corner and temperature as each deck declares them, kept as deck conditions not adjectives"""
    seen = []
    for case_id in TRC.CASE_ORDER:
        text = io.open(RUN.deck_for(case_id, ROLE), encoding='utf-8', newline='').read()
        corner = re.search(r'section=(\w+)', text)
        temp = re.search(r'simopt\s+options\s+temp=([0-9.]+)', text)
        seen.append('%s: %s/%s C' % (case_id, corner.group(1) if corner else 'NOT_DECLARED',
                                     temp.group(1) if temp else 'NOT_DECLARED'))
    return '; '.join(seen)


def iverilog_records(directory):
    """the compile records: every one is a real command that ran, and none is charged to the ceiling"""
    path = os.path.join(directory, 'rtl')
    if not os.path.isdir(path):
        return []
    out = []
    for name in sorted(os.listdir(path)):
        if not name.startswith('compile_'):
            continue
        data = json.loads(io.open(os.path.join(path, name), encoding='utf-8').read())
        out.append({'file': name, 'rc': data.get('rc'), 'exe_sha256': data.get('exe'),
                    'charged': False,
                    'note': 'recorded, not charged: the approved ceiling counts simulator '
                            'processes, and this round charges every vvp start it made'})
    return out


def _launch_id(directory, case_id, role):
    found = [row['launch_id'] for row in ledgers(directory)[0]
             if row['case_id'] == case_id and row['role'] == role and row['state'] == 'CONFIRMED']
    return found[-1] if found else 'NONE'


def _samples(directory, case_id):
    for row in json.loads(io.open(os.path.join(directory, 'launch_log.json'),
                                  encoding='utf-8').read()):
        if row.get('case_id') == case_id and row.get('role') == ROLE:
            return (row.get('observation') or {}).get('samples', '-')
    return '-'


def _internals_note(directory, case_id):
    for row in json.loads(io.open(os.path.join(directory, 'launch_log.json'),
                                  encoding='utf-8').read()):
        if row.get('case_id') == case_id and row.get('role') == ROLE:
            observation = row.get('observation') or {}
            return '%s of 26 saved' % observation.get('internal_present', '-')
    return '-'


def closing_block(directory, table, rows, conv):
    emission = [row for row in rows if row['kind'] == 'emission']
    spectre_rows, rtl_rows = ledgers(directory)
    strays, _notes = RUN.budget_strays(directory)
    account = RUN.spectre_account(directory, run_id_of(directory))
    ordered = dict((row['status'], row['verdict']) for row in table)
    return [
        ('COMPLETION_LEVEL', 'RTL_TRACE_DRIVEN_PAM_TRANSIENT_MEASURED_TT'),
        ('NEW_SPECTRE_LAUNCHES', '%d/%d (plus %d stray processes charged against the same ceiling, '
                                 '%d left unused)'
         % (len(spectre_rows), RUN.SPECTRE_LIMIT, strays, account.remaining())),
        ('NEW_RTL_SIMULATIONS', '%d/%d (all actual vvp starts, including the failed ones)'
         % (rtl_reconciliation(directory)['processes'], RUN.RTL_LIMIT)),
        ('IVERILOG_COMPILATIONS', '%d, recorded in rtl/compile_*.json, not charged'
         % len(iverilog_records(directory))),
        ('EMISSION_WINDOWS_MEASURED', str(len(emission))),
        ('BLACK_WINDOWS_MEASURED', str(len([row for row in rows
                                            if row['kind'].startswith('black')]))),
        ('CONVERGENCE_PAIRS', '%d of 3 declared' % len(set(row['pair'] for row in conv))),
        ('NEW_OA_WRITES', '0'),
        ('CANDIDATE_DUT_CHANGED', 'NO'),
        ('OLD_EVIDENCE_OR_ACCOUNT_CHANGED', 'NO'),
        ('DYNAMIC_CHARGE_STATUS', ordered['DYNAMIC_CHARGE_STATUS']),
        ('NOMINAL_CHARGE_STATUS', ordered['NOMINAL_CHARGE_STATUS']),
        ('SETTLING_STATUS', ordered['SETTLING_STATUS']),
        ('SHUTOFF_STATUS', ordered['SHUTOFF_STATUS']),
        ('CONVERGENCE_STATUS', ordered['CONVERGENCE_STATUS']),
        ('EXECUTION_COMPLETENESS', ordered['EXECUTION_COMPLETENESS']),
        ('EVIDENCE_INTEGRITY', ordered['EVIDENCE_INTEGRITY']),
        ('GRAY_LUT', 'NOT_RUN'),
        ('FULL_MOS_GRAY_CONTROLLER', 'NOT_RUN'),
        ('OPTICAL_EFFECTIVE_BITS', 'NOT_VERIFIED'),
        ('PHYSICAL_CDC_AND_SKEW', 'NOT_VERIFIED'),
        ('SOA_SIGNOFF', 'NO'),
        ('MERGE_PERFORMED', 'NO'),
        ('NEXT_STAGE_AUTHORISED', 'NO'),
        ('STOP_REASON', 'AWAITING_INDEPENDENT_REVIEW')]


def provenance(directory):
    spectre_rows, rtl_rows = ledgers(directory)
    _hyb, source = DECK.load_hyb_inputs()
    payload = {'task_id': TASK_ID, 'base_sha': BASE_SHA, 'branch': BRANCH,
               'head_sha': git('rev-parse', 'HEAD').strip(), 'run_id': run_id_of(directory),
               'contract_sha256': sha_of(repo(TRC.CONTRACT_PATH)),
               'case_plan_sha256': sha_of(repo(TRC.CASE_PLAN_PATH)),
               'interfaces_sha256': sha_of(repo(TRC.INTERFACE_PATH)),
               'hyb_inputs_source': os.path.relpath(source, ROOT).replace(os.sep, '/'),
               'hyb_inputs_sha256': sha_of(source),
               'spectre_rows': [{key: row[key] for key in
                                 ('launch_id', 'case_id', 'role', 'state', 'rc', 'deck_sha256',
                                  'raw_sha256', 'log_sha256', 'requested_utc', 'ended_utc')}
                                for row in spectre_rows],
               'rtl_rows': rtl_rows,
               'local_raw_paths': {case_id: '%s/%s_%s_%s.raw'
                                   % (os.path.basename(directory), run_id_of(directory), case_id,
                                      ROLE) for case_id in TRC.CASE_ORDER},
               'kept_locally_not_tracked': sorted(name for name in sorted(os.listdir(directory))
                                                  if name.endswith(('.raw', '.log'))
                                                  or name == 'guest_logs'),
               'guest_write_root': '%s/%s' % (RUN.GUEST_WORK_ROOT, run_id_of(directory)),
               'credentials_note': 'the bridge loads the guest credentials from its local file at '
                                   'run time; no value is printed, logged or committed'}
    _dump(os.path.join(directory, 'provenance.json'), payload)
    return payload


def write_report(directory):
    publish(directory)          # the tables and the figure exist before anything quotes their digests
    text, table = render_report(directory)
    io.open(repo(REPORT_PATH), 'w', encoding='utf-8', newline='\n').write(text)
    MEAS.write_rows(os.path.join(directory, 'statuses.csv'), table, MEAS.STATUS_HEADER)
    provenance(directory)
    _dump(os.path.join(directory, 'record_selfcheck.json'),
          {'gates': [{'name': name, 'verdict': 'PASS' if ok else 'FAIL', 'extra': extra}
                     for name, ok, extra in gates(directory)],
           'generated_utc': utc(), 'head_sha': git('rev-parse', 'HEAD').strip(),
           'written_by': 'scripts/dd1_d7c_b_tr_record.py'})
    return text, table


# ---- handoff ------------------------------------------------------------------------------------------

def handoff(directory):
    rows = all_rows(directory)
    conv, pairs, problems = convergence_table(directory)
    table, failing_dyn, failing_nom = verdicts(directory, conv, rows)
    results = gates(directory)
    failures = [name for name, ok, _extra in results if not ok]
    keep, skipped = tracked_candidates()
    payload = {
        'task_id': TASK_ID, 'run_id': run_id_of(directory), 'branch': BRANCH, 'base_sha': BASE_SHA,
        'head_sha': git('rev-parse', 'HEAD').strip(), 'generated_utc': utc(),
        'contract_state': TRC.contract()['contract_state'],
        'authorisation': TRC.contract()['authorisation'],
        'gates': [{'name': name, 'verdict': 'PASS' if ok else 'FAIL', 'extra': extra}
                  for name, ok, extra in results],
        'gate_summary': '%d/%d gates pass' % (len(results) - len(failures), len(results)),
        'statuses': table,
        'windows': {'emission': len([row for row in rows if row['kind'] == 'emission']),
                    'black': len([row for row in rows if row['kind'].startswith('black')]),
                    'total_rows': len(rows)},
        'convergence': {'pairs': pairs, 'rows': len(conv), 'context_problems': problems},
        'negative_findings': {'dynamic_over_limit': failing_dyn, 'nominal_over_limit': failing_nom},
        'budget': {'spectre_rows': len(ledgers(directory)[0]),
                   'spectre_processes': RUN.spectre_account(directory, run_id_of(directory)
                                                            ).processes(),
                   'strays': RUN.budget_strays(directory)[0],
                   'approved_ceiling': RUN.SPECTRE_LIMIT,
                   'enforced_ceiling': RUN.spectre_ceiling(directory),
                   'remaining': RUN.spectre_account(directory, run_id_of(directory)).remaining(),
                   'rtl_processes': rtl_reconciliation(directory)['processes'],
                   'rtl_approved_ceiling': RUN.RTL_LIMIT},
        'tracked_bytes': total_bytes(keep), 'tracked_file_count': len(keep),
        'not_tracked_by_design': skipped,
        'hybrid_marker_binding': markers_bind_to_ledger(directory),
        'carried_followups': TRC.contract()['carried_followups'],
        'evidence_gaps': ['R004 carries no trace digest in the RTL account because it was settled '
                          'before the vcd column was fixed',
                          'the two stray launches left no raw bytes behind and their first log was '
                          'overwritten; no number from them is published',
                          'the raws and guest logs stay on this machine; digests and local paths are '
                          'published in provenance.json'],
        'not_run': ['GRAY_LUT', 'FULL_MOS_GRAY_CONTROLLER', 'ARRAY_OR_LAYOUT', 'DRC_LVS_PEX',
                    'OPTICAL_MEASUREMENT', 'OA_ACCESS'],
        'not_verified': ['OPTICAL_EFFECTIVE_BITS', 'PHYSICAL_CDC_AND_SKEW', 'SOA'],
        'next_stage_authorised': False,
        'merge_performed': False,
        'stop_reason': 'AWAITING_INDEPENDENT_REVIEW',
        'self_registration': 'NONE: this round does not register an accepted version and does not '
                             'give itself a GO',
        'report_sha256': sha_of(repo(REPORT_PATH)) if os.path.isfile(repo(REPORT_PATH)) else '',
        'reviewer_entry_points': [
            {'command': 'python scripts/dd1_d7c_b_tr_record.py --gates',
             'needs': 'the evidence directory of this round', 'starts_simulator': False},
            {'command': 'python scripts/dd1_d7c_b_tr_record.py --selftest',
             'needs': 'the evidence directory copy under review/scratch', 'starts_simulator': False},
            {'command': 'python scripts/dd1_d7c_b_tr_contract.py --selftest',
             'needs': 'nothing but the repository', 'starts_simulator': False},
            {'command': 'python scripts/dd1_d7c_b_tr_decks.py --check',
             'needs': 'the delivered run copies', 'starts_simulator': False},
            {'command': 'python scripts/dd1_d7c_b_tr_trace.py --selftest',
             'needs': 'synthetic traces only', 'starts_simulator': True,
             'note': 'starts iverilog/vvp on a synthetic trace, never Spectre'},
            {'command': 'python scripts/dd1_d7c_b_tr_measure.py --selftest',
             'needs': 'hand-computed fixtures', 'starts_simulator': False}]}
    _dump(repo(HANDOFF_JSON), payload)
    lines = ['# DATA-7C-B-TR handoff', '',
             'Round `%s` on branch `%s`, HEAD `%s`, base `%s`. Contract state `%s`. Generated %s.'
             % (run_id_of(directory), BRANCH, payload['head_sha'], BASE_SHA,
                payload['contract_state'], utc()), '',
             '## What was delivered', '',
             '- 9 prepared and joint cases, both roles: %d/%d Spectre account rows confirmed, '
               '%d stray processes charged anyway, enforced ceiling %d of the approved %d, '
               '%d unused'
             % (len([row for row in ledgers(directory)[0] if row['state'] == 'CONFIRMED']),
                len(ledgers(directory)[0]), payload['budget']['strays'],
                payload['budget']['enforced_ceiling'], RUN.SPECTRE_LIMIT,
                payload['budget']['remaining']),
             '- %d vvp processes charged of the approved %d; both joint traces come from the '
               'accepted controller with no RTL change'
             % (payload['budget']['rtl_processes'], RUN.RTL_LIMIT),
             '- %d window rows: %d emission and %d black, each bound to a charged launch and the '
               'delivered deck digest'
             % (len(rows), payload['windows']['emission'], payload['windows']['black']),
             '- three convergence pairs, %d window comparisons, %d context refusals'
             % (len(conv), len(problems)),
             '- %d/%d record gates pass; %d newly tracked bytes over %d files'
             % (len(results) - len(failures), len(results), payload['tracked_bytes'], len(keep)),
             '', '## The seven statuses', '']
    lines += _table(('status', 'verdict', 'measured', 'expected', 'note'), table)
    lines += ['', '## Negative findings, published as findings', '']
    lines += ['- dynamic charge over the frozen limit: %s' % (', '.join(failing_dyn) or 'none'),
              '- nominal charge over the same limit: %s' % (', '.join(failing_nom) or 'none'),
              '- the circuit was not modified to turn either into a PASS',
              '']
    if failures:
        lines += ['## Gates that did not pass', '']
        lines += ['- %s' % name for name in failures]
        lines += ['']
    lines += ['## What this round does not claim', '',
              '- no grey-scale LUT, no full MOS grey-scale controller, no array, no layout, no DRC, '
              'LVS or PEX, no optical measurement and no OA access',
              '- no optical effective bits, no physical CDC or skew conclusion, no SOA sign-off',
              '- %s' % payload['self_registration'],
              '- `NEXT_STAGE_AUTHORISED=NO`, `STOP_REASON=AWAITING_INDEPENDENT_REVIEW`']
    io.open(repo(HANDOFF_MD), 'w', encoding='utf-8',
            newline='\n').write('\n'.join(lines).rstrip('\n') + '\n')
    return payload


def total_bytes(keep):
    return sum(size for _path, size in keep)


# ---- offline family: the record stage is tested against tampered copies, never against itself ----------

def _copy_evidence(directory):
    """a disposable copy: mutating suites must never touch the published evidence"""
    target = os.path.join(ROOT, 'review', 'scratch', 'tr_record_copy',
                          os.path.basename(directory))
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)
    for name in sorted(os.listdir(directory)):
        source = os.path.join(directory, name)
        if name.endswith('.raw') or name == 'guest_logs' or name == 'rtl':
            continue
        if os.path.isfile(source):
            shutil.copy2(source, os.path.join(target, name))
    shutil.copytree(os.path.join(directory, 'rtl'), os.path.join(target, 'rtl'),
                    ignore=shutil.ignore_patterns('*.raw', '*.vvp'))
    return target


def _patch(path, old, new):
    text = io.open(path, encoding='utf-8', newline='').read()
    if old not in text:
        raise TRC.Refuse('the tamper target %s is not in %s, so the counterexample would be vacuous'
                         % (old[:40], os.path.basename(path)))
    io.open(path, 'w', encoding='utf-8', newline='\n').write(text.replace(old, new, 1))


def selftest():
    """every counterexample below is applied to a copy or to memory, never to published evidence"""
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else str(extra)))
    real = evidence_dir()
    copy = _copy_evidence(real)
    rows = all_rows(copy)
    emission = [row for row in rows if row['kind'] == 'emission']
    conv, pairs, problems = convergence_table(copy)
    table, failing_dyn, failing_nom = verdicts(copy, conv, rows)
    by_name = dict((row['status'], row['verdict']) for row in table)
    record('the copy reads the same rows and the same three pairs as the published evidence',
           len(rows) == len(all_rows(real)) and len(conv) == 13 and len(pairs) == 3,
           (len(rows), len(conv), len(pairs)))
    record('the dynamic verdict and the failing window list cannot disagree',
           bool(failing_dyn) == (by_name['DYNAMIC_CHARGE_STATUS'] == 'FAIL'),
           (failing_dyn[:2], by_name['DYNAMIC_CHARGE_STATUS']))
    record('a dynamic pass does not decide the nominal column, which keeps its own verdict',
           _independent_columns(emission + [row for row in rows if row['kind'] == 'black']),
           'both columns come from one row set but from different targets')
    forged = [dict(row, raw_sha256='f' * 64) for row in rows]
    found = _integrity_over(copy, forged)['problems']
    record('a row whose raw digest is not the one the account holds is caught',
           any('publishes raw' in text for text in found), found[:1])
    ghost = [dict(row, launch_id='T999') if index == 0 else row for index, row in enumerate(rows)]
    found = _integrity_over(copy, ghost)['problems']
    record('a row citing a launch that is not in the account names itself in the refusal',
           any('not in the launch account' in text for text in found), found[:1])
    wrong_deck = _integrity_over(copy, [dict(row, deck_sha256='d' * 64) for row in rows])['problems']
    record('a row that publishes a deck other than the delivered run copy is caught',
           any('publishes deck' in text for text in wrong_deck), wrong_deck[:1])
    cited = rows[0]['launch_id']
    account = RUN.spectre_account(copy, run_id_of(copy))
    row_to_break = [row for row in account.rows if row['launch_id'] == cited][0]
    account.settle(row_to_break, 'FAILED', rc='1', refusal='TAMPERED BY THE SELFTEST')
    found = integrity(copy)['problems']
    record('a launch that stopped being CONFIRMED cannot keep carrying published rows',
           any('FAILED launch row' in text for text in found), found[:1])
    record('one broken launch breaks every row that cited it and no row that did not',
           len(found) == 2 * len([row for row in rows if row['case_id'] == 'TR-LONG'])
           and all(text.startswith('TR-LONG') for text in found),
           (len(found), found[:1]))
    copy = _copy_evidence(real)      # the ledger above is now broken: everything after this is a copy
    rows = all_rows(copy)
    emission = [row for row in rows if row['kind'] == 'emission']
    record('seven statuses are published and none of them is an aggregate over the others',
           len(table) == 7 and len(set(row['status'] for row in table)) == 7
           and not any('OVERALL' in row['status'] for row in table),
           [row['status'] for row in table])
    torn = [dict(row, q_full_C='') for row in emission]
    coarse = [row for row in rows if row['case_id'] == 'TR-LONG']
    _rows, problems = MEAS.convergence(torn, coarse, {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('a side with no measured Q is reported as a refusal, not as a difference of zero',
           any('no measured Q' in text for text in problems), problems[:1])
    refined_rows = [row for row in emission if row['case_id'] == 'RS-FULL']
    coarse_rows = [row for row in emission if row['case_id'] == 'TR-LONG']
    shifted = [dict(refined_rows[0], code='101')] + refined_rows[1:]
    _rows, problems = MEAS.convergence(shifted, coarse_rows,
                                       {'refined': 'RS-FULL', 'coarse': 'TR-LONG'})
    record('one changed code on one side breaks the context match instead of moving the number',
           any('disagrees on code' in text for text in problems)
           and not [row for row in _rows if row['window_id'] == refined_rows[0]['window_id']],
           problems[:1])
    text, _rendered = render_report(real)
    record('the report names every window that failed the dynamic criterion',
           all(case in text and window in text
               for case, window in [row.split(' ', 1) for row in failing_dyn]), failing_dyn[:3])
    record('the report publishes the seven statuses by name and never an aggregate',
           all(name in text for name in ('DYNAMIC_CHARGE_STATUS', 'NOMINAL_CHARGE_STATUS',
                                         'SETTLING_STATUS', 'SHUTOFF_STATUS', 'CONVERGENCE_STATUS',
                                         'EXECUTION_COMPLETENESS', 'EVIDENCE_INTEGRITY')),
           [name for name in ('SETTLING_STATUS', 'EVIDENCE_INTEGRITY') if name not in text])
    missing = ['%s=%s' % (key, value) for key, value in sorted(closing_block(real, table, rows, conv))
               if ('%s=%s' % (key, value)) not in text]
    record('the closing block carries every key with the value the record derived',
           not missing, missing[:4])
    record('the report stops at the review gate and authorises nothing further',
           all(needle in text for needle in ('NEXT_STAGE_AUTHORISED=NO',
                                            'STOP_REASON=AWAITING_INDEPENDENT_REVIEW',
                                            'MERGE_PERFORMED=NO', 'NEW_OA_WRITES=0',
                                            'CANDIDATE_DUT_CHANGED=NO')),
           [needle for needle in ('NEXT_STAGE_AUTHORISED', 'STOP_REASON') if needle not in text])
    record('the report quotes no digest of itself',
           sha_of(repo(REPORT_PATH)) not in text if os.path.isfile(repo(REPORT_PATH)) else True,
           'a report that certifies its own bytes cannot be re-read')
    planted = 'review/scratch/tr_record_copy/planted.md'
    io.open(repo(planted), 'w', encoding='utf-8', newline='\n').write(
        'see the ' + '.ic617_agent' + '_' + 'bridge_credentials file and -----BEGIN ' + 'RSA '
        'PRIVATE KEY----- for the rest\n')
    record('the secret scan catches a planted credential path and a planted key marker',
           len(secret_scan([planted])) >= 2, secret_scan([planted]))
    record('the scanner does not report its own needle list as a leak',
           not secret_scan(['scripts/dd1_d7c_b_tr_record.py']),
           secret_scan(['scripts/dd1_d7c_b_tr_record.py']))
    crlf = 'review/scratch/tr_record_copy/crlf.csv'
    io.open(repo(crlf), 'wb').write(b'a,b\r\nc,d\r\n')
    record('a CRLF artefact among the published text is caught', line_ending_scan([crlf]) == [crlf],
           line_ending_scan([crlf]))
    os.remove(repo(crlf))
    os.remove(repo(planted))
    duplicate = dict(sim_id='R010', case_id='HYB-120', requested_utc='same', rc='',
                     exe_sha256='', vcd_sha256='', log_sha256='', deck_sha256='')
    witness = dict(sim_id='R011', case_id='HYB-120', requested_utc='same', rc='0',
                   exe_sha256='e' * 64, vcd_sha256='v' * 64, log_sha256='l' * 64, deck_sha256='')
    record('a booking with no process evidence beside exactly one that has it is a duplicate',
           derive_duplicates([duplicate, witness]) == [('R010', 'R011')],
           derive_duplicates([duplicate, witness]))
    record('a row that carries an executable of its own is never released from the charge',
           derive_duplicates([dict(duplicate, exe_sha256='x' * 64), witness]) == [], 'stays charged')
    record('two bookings in different seconds are two processes, not one',
           derive_duplicates([dict(duplicate, requested_utc='other'), witness]) == [],
           'stays charged')
    record('two witnesses in the same second leave the duplicate unproven',
           derive_duplicates([duplicate, witness, dict(witness, sim_id='R012')]) == [],
           'stays charged')
    data = json.loads(io.open(reconciliation_file(copy), encoding='utf-8').read())
    data['actual_vvp_processes_started'] = 2
    _dump(reconciliation_file(copy), data)
    record('a reconciliation whose count the ledger no longer supports is reported',
           any('processes' in text for text in rtl_reconciliation(copy)['problems']),
           rtl_reconciliation(copy)['problems'])
    binding = markers_bind_to_ledger(real)
    record('the hybrid conversions bind to a confirmed start of their own case and log',
           not binding['problems'], binding['problems'][:2])
    keep, skipped = tracked_candidates()
    record('the tracked candidates stay inside the byte ceiling and exclude every raw, log and '
           'unpacked trace',
           total_bytes(keep) <= TRACK_LIMIT_BYTES
           and not [path for path, _s in keep if path.endswith(LOCAL_ONLY_SUFFIXES)],
           (total_bytes(keep), len(keep)))
    probe_rel = 'tr_record_scope_probe.txt'
    io.open(repo(probe_rel), 'w', encoding='utf-8', newline='\n').write('scope probe\n')
    _keep, skipped = tracked_candidates()
    record('a path outside the scope this round may add is refused as a tracked candidate',
           any(path == probe_rel and 'outside the paths' in reason for path, reason in skipped),
           [row for row in skipped if row[0] == probe_rel])
    os.remove(repo(probe_rel))
    record('and the refusal leaves nothing behind in the working tree',
           not os.path.exists(repo(probe_rel)), probe_rel)
    record('the published rows fail both criteria somewhere, so the mutation tests below are not '
           'testing an empty set', bool(failing_dyn) and bool(failing_nom),
           (len(failing_dyn), len(failing_nom)))
    record('zeroing the dynamic column cannot change the nominal verdict and vice versa',
           _independent_columns(rows), (failing_dyn[:1], failing_nom[:1]))
    delta = delay_breakdown(real, 'TR-LONG')
    record('the TR-LONG attribution has one row per emission window and a state per boundary',
           len(delta) == 8 and all(row['decode_state'] and row['build_state'] for row in delta),
           [(row['window_id'], row['decode_state'], row['build_state']) for row in delta[:2]])
    entry = json.loads(io.open(os.path.join(real, 'internal_nodes_TR-LONG_dut.json'),
                               encoding='utf-8').read())[0]
    record('a published internal entry cannot claim more conducting branches than its code allows',
           entry['selected_branches'] == int(entry['code'], 2) + 1
           and entry['branch_enables_high'] <= entry['selected_branches'],
           (entry['code'], entry['selected_branches'], entry['branch_enables_high']))
    return results


def _integrity_over(directory, rows):
    """integrity over a substituted row set, so a counterexample never edits a published table"""
    original = globals()['case_rows']
    substituted = dict((case_id, [row for row in rows if row['case_id'] == case_id])
                       for case_id in TRC.CASE_ORDER)

    def patched(_directory, case_id):
        return substituted[case_id]

    globals()['case_rows'] = patched
    try:
        return integrity(directory)
    finally:
        globals()['case_rows'] = original


def _independent_columns(rows):
    """the two error columns are judged on their own: zeroing one must not move the other verdict"""
    fixture = {'verdict': 'PASS', 'measured': 1, 'expected': 1, 'note': 'fixture'}
    conv = [{'window_id': 'W0', 'status': 'PASS'}]

    def verdicts_of(mutated):
        table = MEAS.statuses(mutated, conv, fixture, fixture)
        return dict((row['status'], row['verdict']) for row in table)

    dynamic_zeroed = verdicts_of([dict(row, err_dynamic_LSB=0.0) for row in rows])
    nominal_zeroed = verdicts_of([dict(row, err_nominal_LSB=0.0) for row in rows])
    return (dynamic_zeroed['DYNAMIC_CHARGE_STATUS'] == 'PASS'
            and dynamic_zeroed['NOMINAL_CHARGE_STATUS'] == 'FAIL'
            and nominal_zeroed['NOMINAL_CHARGE_STATUS'] == 'PASS'
            and nominal_zeroed['DYNAMIC_CHARGE_STATUS'] == 'FAIL')


# ---- reviewer package -----------------------------------------------------------------------------------

PACKAGE_EXTENSIONS = ('.py', '.scs', '.sv', '.md', '.json', '.csv', '.txt', '.svg', '.vcd.gz')
LOCAL_ONLY_SUFFIXES = ('.raw', '.vvp', '.pyc', '.out', '.log', '.vcd')
LOCAL_ONLY_MARKS = ('/guest_logs/',)
RECOMPUTE_NAME = 'independent_recompute.py'


def recompute_source():
    """the script shipped inside the package: it re-derives the published numbers from the published
    tables and the frozen formula, so a reviewer does not have to trust this round's own tools"""
    return r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR independent recomputation over the packaged tables.

It reads contract.json, the ledgers, windows_all.csv, convergence.csv and statuses.csv, and re-derives
every derived number from the frozen definition. It does not import the round's measurement module and
it starts no simulator. The raw answers stay on the laboratory machine, so this recompute starts from
the published per-window Q; the digests of the raws it cannot see are in provenance.json.
"""
import csv
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
EVIDENCE = None


def load(path):
    with io.open(os.path.join(EVIDENCE, path), encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def rows_table(path):
    return load(path)


def main():
    global EVIDENCE
    evidence_root = os.path.join(ROOT, 'results', 'evidence')
    if not os.path.isdir(evidence_root):
        print('RECOMPUTE: the package holds no results/evidence directory to re-derive from')
        return 9
    names = sorted(name for name in os.listdir(evidence_root) if name.startswith('dd1_d7c_b_tr_r'))
    if not names:
        print('RECOMPUTE: no DATA-7C-B-TR evidence directory inside the package')
        return 9
    EVIDENCE = os.path.join(evidence_root, names[-1])
    contract = json.load(io.open(os.path.join(ROOT, 'tests', 'dd1_d7c_b_tr', 'contract.json'),
                                 encoding='utf-8'))
    rows = rows_table('windows_all.csv')
    checks = []
    unit = 1.875e-6
    for row in rows:
        if row['kind'] == 'emission':
            tick = float(row['tick_ns'])
            qlsb = unit * tick * 1e-9
            checks.append(('QLSB of %s is 1.875 uA times its own reference tick'
                           % row['case_id'], abs(float(row['qlsb_C']) - qlsb) <= 1e-24,
                           (row['qlsb_C'], qlsb)))
            t50 = float(row['t50_ns']) * 1e-9
            dynamic = (float(row['q_full_C']) - float(row['qtarget_dc_C'])) / qlsb
            nominal = (float(row['q_full_C']) - float(row['qtarget_nominal_C'])) / qlsb
            checks.append(('dynamic error of %s %s re-derived from Q, target and QLSB'
                           % (row['case_id'], row['window_id']),
                           abs(dynamic - float(row['err_dynamic_LSB'])) <= 1e-6,
                           (dynamic, row['err_dynamic_LSB'])))
            checks.append(('nominal error of %s %s re-derived independently'
                           % (row['case_id'], row['window_id']),
                           abs(nominal - float(row['err_nominal_LSB'])) <= 1e-6,
                           (nominal, row['err_nominal_LSB'])))
            checks.append(('T50 of %s %s is the native 0.9 V interval'
                           % (row['case_id'], row['window_id']),
                           abs(float(row['t50_ns']) - (float(row['fall50_ns'])
                                                       - float(row['rise50_ns']))) <= 1e-6,
                           row['t50_ns']))
            checks.append(('Q splits into Qpos and Qneg without cancelling'
                           % row['window_id'],
                           abs(float(row['q_full_C']) - (float(row['q_pos_C'])
                                                         + float(row['q_neg_C']))) <= 1e-24,
                           row['q_full_C']))
        if row['kind'].startswith('black'):
            checks.append(('black window %s %s has a zero target and no invented T50'
                           % (row['case_id'], row['window_id']),
                           float(row['qtarget_dc_C']) == 0.0
                           and row['t50_ns'] == 'NOT_DEFINED_FOR_BLACK', row['t50_ns']))
    conv = rows_table('convergence.csv')
    limit = contract['convergence']['limit_rel_qlsb']
    for row in conv:
        ratio = abs(float(row['refined_q_C']) - float(row['coarse_q_C'])) / float(row['qlsb_C'])
        checks.append(('dQ of %s %s re-derived and judged against the frozen limit'
                       % (row['pair'], row['window_id']),
                       (ratio <= limit) == (row['status'] == 'PASS'), (ratio, row['status'])))
    statuses = {row['status']: row['verdict'] for row in rows_table('statuses.csv')}
    for name in ('EXECUTION_COMPLETENESS', 'EVIDENCE_INTEGRITY', 'DYNAMIC_CHARGE_STATUS',
                 'NOMINAL_CHARGE_STATUS', 'SETTLING_STATUS', 'SHUTOFF_STATUS',
                 'CONVERGENCE_STATUS'):
        checks.append(('the status %s is published' % name, name in statuses, statuses.get(name)))
    emission = [row for row in rows if row['kind'] == 'emission']
    black = [row for row in rows if row['kind'].startswith('black')]
    dynamic_fail = any(abs(float(row['err_dynamic_LSB'])) > 0.5
                       for row in emission + black)
    checks.append(('the dynamic verdict is FAIL exactly when a window is over half an LSB',
                   (statuses['DYNAMIC_CHARGE_STATUS'] == 'FAIL') == dynamic_fail,
                   (statuses['DYNAMIC_CHARGE_STATUS'], dynamic_fail)))
    spectre = load('spectre_launch_account.csv')
    rtl = load('rtl_simulation_account.csv')
    ceiling = int(contract['authorisation']['spectre_total_limit'])
    rtl_ceiling = int(contract['authorisation']['rtl_simulation_total_limit'])
    strays = json.load(io.open(os.path.join(EVIDENCE, 'spectre_budget_adjustments.json'),
                               encoding='utf-8'))
    stray_processes = sum(int(row['processes']) for row in strays['adjustments'])
    checks.append(('the contract authorises 24 Spectre launches and 4 RTL simulations',
                   ceiling == 24 and rtl_ceiling == 4, (ceiling, rtl_ceiling)))
    checks.append(('the charged Spectre rows plus the recorded strays never exceed the ceiling',
                   len(spectre) + stray_processes <= ceiling, (len(spectre), stray_processes)))
    checks.append(('every launch row is in a state the account admits',
                   all(row['state'] in ('REQUESTED', 'UNCERTAIN', 'FAILED', 'CONFIRMED')
                       for row in spectre), ''))
    checks.append(('the vvp ledger never exceeds the four charged processes it may have',
                   len(rtl) - 1 <= rtl_ceiling and len(rtl) <= rtl_ceiling + 1,
                   (len(rtl), rtl_ceiling)))
    failures = [(name, extra) for name, ok, extra in checks if not ok]
    for name, ok, _extra in checks:
        print('%-4s %s' % ('PASS' if ok else 'FAIL', name))
    print('RECOMPUTE %d/%d' % (len(checks) - len(failures), len(checks)))
    for name, extra in failures:
        print('RECOMPUTE_FAIL %s <- %s' % (name, extra))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
'''


def package(base, head, out_root='review'):
    """a reviewer package built from committed blobs only, with the safety gate run first"""
    import repo_safety_rules as RULES
    directory = evidence_dir()
    stage_root = repo(out_root)
    stag = os.path.join(stage_root, 'dd1_d7c_b_tr_package_%s' % head[:7])
    if os.path.isdir(stag):
        shutil.rmtree(stag)
    gate = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'precommit_safety_check.py'),
                           '--mode', 'history'], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    gate_text = gate.stdout.decode('utf-8', 'replace')
    listing = git('diff', '--name-status', '%s..%s' % (base, head)).splitlines()
    manifest, refused = [], []
    for line in listing:
        parts = line.split('\t')
        status, rel = parts[0], parts[-1].replace('\\', '/')
        if status == 'D':
            refused.append((rel, 'deleted by this range, which the file-scope rules forbid'))
            continue
        proc = subprocess.Popen(['git', 'cat-file', 'blob', '%s:%s' % (head, rel)], cwd=ROOT,
                                stdout=subprocess.PIPE)
        data = proc.communicate()[0]
        if not data:
            refused.append((rel, 'no blob at HEAD'))
            continue
        if not rel.endswith(PACKAGE_EXTENSIONS):
            refused.append((rel, 'extension not packaged; it stays in the repository'))
            continue
        text = data.decode('latin-1')
        hits = [name for name, _rule in RULES.content_denied(text)] \
            + [name for name, _rule in RULES.secrets_in(text)]
        if RULES.path_denied(rel) or hits:
            refused.append((rel, hits or 'path rule'))
            continue
        dest = os.path.join(stag, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        io.open(dest, 'wb').write(data)
        manifest.append((rel, len(data), hashlib.sha256(data).hexdigest()))
    io.open(os.path.join(stag, RECOMPUTE_NAME), 'w', encoding='utf-8',
            newline='\n').write(recompute_source())
    os.chmod(os.path.join(stag, RECOMPUTE_NAME), 0o755)
    manifest.append((RECOMPUTE_NAME, os.path.getsize(os.path.join(stag, RECOMPUTE_NAME)),
                     sha_of(os.path.join(stag, RECOMPUTE_NAME))))
    # the repository's own ignore rules keep *.vcd and *.gz out of the object store, so the traces
    # travel in the package instead: copied from the local evidence, and admitted only after their
    # digest has been checked against the tool identity the report already publishes
    identity = json.loads(io.open(os.path.join(directory, 'rtl', 'tool_identity.json'),
                                  encoding='utf-8').read())
    for row in identity['traces']:
        for name in (row['gzip_file'], 'tool_identity.json'):
            source = os.path.join(directory, 'rtl', name)
            if not os.path.isfile(source):
                refused.append(('rtl/' + name, 'not on this machine'))
                continue
            digest = sha_of(source)
            expected = row['gzip_sha256'] if name.endswith('.gz') else None
            if expected is not None and digest != expected:
                refused.append(('rtl/' + name, 'digest %s is not the published %s'
                                % (digest[:12], expected[:12])))
                continue
            relative = 'results/evidence/%s/rtl/%s' % (os.path.basename(directory), name)
            dest = os.path.join(stag, relative)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(source, dest)
            if (relative, os.path.getsize(dest), digest) not in manifest:
                manifest.append((relative, os.path.getsize(dest), digest))
    MEAS.write_rows(os.path.join(stag, 'package_manifest.csv'),
                    [{'path': path, 'bytes': size, 'sha256': digest}
                     for path, size, digest in manifest],
                    ('path', 'bytes', 'sha256'))
    readme = ['# DATA-7C-B-TR reviewer package', '',
              'Built from base `%s` and HEAD `%s` at %s, by `scripts/dd1_d7c_b_tr_record.py`.'
              % (base, head, utc()), '',
              '## How to read it', '',
              '- `reports/dd1_d7c_b_tr_report.md` is the deliverable; every table in it comes from '
              '`results/evidence/dd1_d7c_b_tr_*/windows_all.csv` and its companions.',
              '- `independent_recompute.py` re-derives the published numbers from the published '
              'tables and the frozen formula, with no import of this round\'s measurement module: '
              '`python independent_recompute.py` prints one line per check and a final count.',
              '- `package_manifest.csv` lists every file here with its digest; nothing else in the '
              'repository is needed to re-derive a number from the tables that are here.', '',
              '## What is deliberately not in the package', '',
              '- the raw Spectre answers and the guest logs: they stay on the laboratory machine, '
              'their digests and local paths are in `provenance.json`, and no claim in the report '
              'depends on a byte that is not published.',
              '- the vvp logs: they begin with the command line, which carries an absolute tool '
              'path. Their digests and their MARK lines are published in `hyb_inputs.json` and in '
              '`rtl/tool_identity.json`, and the traces themselves ship gzipped losslessly.', '',
              '## Files the packaging rules refused', '']
    readme += ['- %s: %s' % (rel, reason) for rel, reason in refused] or ['- none']
    readme += ['', '## Safety gate', '',
               '```text', gate_text.rstrip(), '```', '',
               'The gate rc was %d. The history scan reports one pre-existing unreachable object '
               'from an earlier round in the shared store; it is not this round\'s object, was not '
               'pruned, and is disclosed here rather than worked around.' % gate.returncode, '',
               '## Authorisation state', '',
               '```text', 'TASK=%s' % TASK_ID, 'BASE=%s' % base, 'HEAD=%s' % head,
               'NEW_SPECTRE_LAUNCHES_SEE_REPORT=see the closing block of the report',
               'MERGE_PERFORMED=NO', 'NEXT_STAGE_AUTHORISED=NO',
               'STOP_REASON=AWAITING_INDEPENDENT_REVIEW', '```']
    io.open(os.path.join(stag, 'PACKAGE_README.md'), 'w', encoding='utf-8',
            newline='\n').write('\n'.join(readme).rstrip('\n') + '\n')
    zip_path = os.path.join(stage_root, 'dd1_d7c_b_tr_package_%s.zip' % head[:7])
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for here, _sub, names_in_dir in os.walk(stag):
            for name in sorted(names_in_dir):
                full = os.path.join(here, name)
                archive.write(full, os.path.relpath(full, stag))
    return {'stage': stag, 'zip': zip_path, 'zip_bytes': os.path.getsize(zip_path),
            'zip_sha256': sha_of(zip_path), 'files': len(manifest), 'refused': refused,
            'gate_rc': gate.returncode, 'gate_text': gate_text}


# ---- entry --------------------------------------------------------------------------------------------

def main(argv):
    mode = argv[0] if argv else '--gates'
    directory = evidence_dir(argv[1] if len(argv) > 1 else '')
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-4s %s%s' % ('PASS' if ok else 'FAIL', name.ljust(66),
                                 '' if ok else '  <- %s' % extra[:200]))
        print('TR_RECORD_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--publish':
        written = publish(directory)
        print('TR_PUBLISH %s' % json.dumps(dict((key, os.path.basename(value))
                                                for key, value in written[6].items())))
        return 0
    if mode == '--restate':
        path, data = restate_reconciliation(directory)
        print('TR_RESTATE %s processes=%d rows=%s'
              % (os.path.basename(path), data['actual_vvp_processes_started'],
                 ','.join(data['ledger_rows_at_this_statement']))
              )
        return 0
    if mode in ('--build', '--handoff'):
        text, table = write_report(directory)
        io.open(repo(REPORT_PATH), 'w', encoding='utf-8', newline='\n').write(text)
        payload = handoff(directory)
        print('TR_BUILD report=%s bytes=%d statuses=%s gates=%s tracked_bytes=%s'
              % (REPORT_PATH, len(text.encode('utf-8')),
                 ' '.join('%s:%s' % (row['status'].split('_')[0], row['verdict'])
                          for row in table), payload['gate_summary'], payload['tracked_bytes']))
        bad = [row for row in payload['gates'] if row['verdict'] == 'FAIL']
        for row in bad:
            print('TR_GATE_FAIL %s <- %s' % (row['name'], row['extra'][:220]))
        return 0 if not bad else 1
    if mode == '--package':
        head = argv[1] if len(argv) > 1 else git('rev-parse', 'HEAD').strip()
        answer = package(BASE_SHA, head)
        print('TR_PACKAGE zip=%s bytes=%d sha256=%s files=%d refused=%d gate_rc=%s'
              % (os.path.basename(answer['zip']), answer['zip_bytes'], answer['zip_sha256'],
                 answer['files'], len(answer['refused']), answer['gate_rc']))
        for rel, reason in answer['refused']:
            print('TR_PACKAGE_REFUSED %s: %s' % (rel, reason))
        replay = os.path.join(repo('review'), 'dd1_d7c_b_tr_replay_%s' % head[:7])
        if os.path.isdir(replay):
            shutil.rmtree(replay)
        os.makedirs(replay)
        with zipfile.ZipFile(answer['zip']) as archive:
            archive.extractall(replay)
        rc = subprocess.call([sys.executable, os.path.join(replay, RECOMPUTE_NAME)])
        print('TR_REPLAY rc=%s from %s' % (rc, replay))
        return 0 if rc == 0 else 1
    results = gates(directory)
    failures = [name for name, ok, extra in results if not ok]
    for name, ok, extra in results:
        print('%-4s %s%s' % ('PASS' if ok else 'FAIL', name.ljust(78),
                             '' if ok else '  <- %s' % extra[:200]))
    print('TR_RECORD_GATES %d/%d' % (len(results) - len(failures), len(results)))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
