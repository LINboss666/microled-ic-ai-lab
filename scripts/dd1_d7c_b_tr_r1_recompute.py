#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR-R1 independent recomputation, starting from the native samples.

Stdlib only, and it imports nothing from this round's own scripts: a tool is not evidence of its own
correctness. It restores the printed tokens of the native answers, integrates the charge from those
samples with endpoint interpolation and a split at every zero crossing, re-derives the two charge
targets from the frozen DC table and the per-case reference tick, re-judges the published statuses,
and refuses a table it cannot bind to the samples it names.

It starts no simulator and writes nothing. A negative electrical finding is confirmed as itself; the
run only fails when a published number cannot be re-derived, or when a number cannot be bound to a
charged launch and a delivered run copy.
"""

import base64
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys

def find_root(start):
    """the package or repository root: the directory that carries the frozen contract"""
    here = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(here, 'tests', 'dd1_d7c_b_tr', 'contract.json')):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise Refuse('no tests/dd1_d7c_b_tr/contract.json above %s, so this is not a DATA-7C-B-TR '
                         'package' % start)
        here = parent


ROOT = find_root(os.path.dirname(os.path.abspath(__file__)))
S_PER_PS = 1e-12
MIN_IN_BAND_NS = 10.0
BLACK_KINDS = ('black_64T', 'black_post_fault_hold')
NUMERIC_CELLS = ('tick_ns', 'qlsb_C', 'window_start_ns', 'window_stop_ns', 'rise50_ns',
                 'fall50_ns', 't50_ns', 'flat_start_ns', 'flat_stop_ns', 'q_full_C', 'q_flat_C',
                 'q_pos_C', 'q_neg_C', 'abs_q_neg_C', 'peak_A', 'peak_ns', 'flat_mean_A',
                 'tail_q_C', 'leak_max_abs_A', 'qtarget_nominal_C', 'qtarget_dc_C',
                 'err_nominal_LSB', 'err_dynamic_LSB')
PWL_LINE_RE = re.compile(r'^V(?P<node>[a-z0-9_]+)\s*\(\s*(?P<out>\S+)\s+0\s*\)\s+vsource\s+'
                         r'type=pwl\s+wave=\[(?P<wave>[^\]]*)\]\s*(?:\$.*)?$')
NS_TOKEN_RE = re.compile(r'^([0-9.]+)(n|u|m|p)?$', re.I)


class Refuse(Exception):
    pass


def sha_of(path):
    digest = hashlib.sha256()
    with io.open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def ns_of(token):
    found = NS_TOKEN_RE.match(token)
    if not found:
        raise Refuse('%r is not a picosecond-, nanosecond- or microsecond-stated instant' % token)
    scale = {'': 1e9, 'n': 1.0, 'u': 1e3, 'm': 1e6, 'p': 1e-3}[found.group(2) or '']
    return float(found.group(1)) * scale


def whole_bytes(path):
    """the delivered bytes of one container, rejoined from its parts when it was split

    The history gate admits no blob over 512 KiB, so a long sequence arrives as
    `<name>.part000.txt`, `<name>.part001.txt` and so on. The parts are a partition of the whole
    file, so taking them in name order rebuilds it byte for byte and the digest the manifest records
    for the whole still holds.
    """
    if os.path.isfile(path):
        return io.open(path, 'rb').read()
    stem = path[:-4] if path.endswith('.txt') else path
    directory = os.path.dirname(stem) or '.'
    names = sorted(name for name in os.listdir(directory)
                   if name.startswith(os.path.basename(stem) + '.part')
                   and name.endswith('.txt'))
    if not names:
        raise Refuse('%s is neither a delivered file nor a set of parts' % os.path.basename(path))
    return b''.join(io.open(os.path.join(directory, name), 'rb').read() for name in names)


def payload_lines(path):
    """the lines of a sequence file, bare, containerised, and whole or in parts"""
    text = whole_bytes(path).decode('utf-8', 'replace')
    if text.startswith('TR1CONTAINER 1'):
        marker = chr(10) + chr(10)
        raw = gzip.decompress(base64.b85decode(text.split(marker, 1)[1].strip()))
    else:
        raw = gzip.decompress(whole_bytes(path))
    return raw.decode('utf-8').split(chr(10))


def read_identity(path):
    """the header of a sequence file, without expanding the samples it describes"""
    identity = {}
    for line in payload_lines(path):
        line = line.strip()
        if line.startswith('column '):
            break
        if line.startswith('# ') and '=' in line:
            key, value = line[2:].split('=', 1)
            if not key.startswith('restore:'):
                identity[key] = value
    if 'native_current_column' not in identity:
        raise Refuse('%s states no native current column' % os.path.basename(path))
    return identity


def restore(path, needed):
    """expand a TR1NATIVESEQ file: a constant repeats, a run list expands, everything else is tokens

    The values are the parsed printed tokens, so the number a reviewer gets is the number the
    simulator printed, and a column this check does not use is still counted, not silently dropped.
    """
    lines = payload_lines(path)
    if not lines or lines[0] != 'TR1NATIVESEQ 1':
        raise Refuse('%s is not a TR1NATIVESEQ sequence' % path)
    identity, samples, windows = {}, None, []
    columns, units, counts = {}, {}, {}
    index = 1
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.startswith('# '):
            if '=' in line:
                key, value = line[2:].split('=', 1)
                if not key.startswith('restore:'):
                    identity[key] = value
            continue
        if line.startswith('samples '):
            samples = int(line.split()[1])
            continue
        if line.startswith('window from_ps '):
            cells = line.split()
            windows.append((float(cells[2]), float(cells[4])))
            continue
        if line.startswith('column '):
            cells = line.split()
            name = cells[1]
            meta = {}
            for pair in range(2, len(cells) - 1, 2):
                meta[cells[pair]] = cells[pair + 1]
            unit, encoding = meta.get('unit', ''), meta.get('encoding', '')
            declared = int(meta.get('count', '0'))
            counts[name] = declared
            if encoding == 'EMPTY':
                values = []
            elif encoding == 'CONSTANT':
                values = [float(lines[index])] * declared
                index += 1
            elif encoding == 'RUNS':
                values = []
                for _ in range(int(meta.get('runs', '0'))):
                    count, token = lines[index].split()
                    index += 1
                    values.extend([float(token)] * int(count))
            else:
                raise Refuse('%s: column %s declares encoding %r' % (path, name, encoding))
            if len(values) != declared:
                raise Refuse('%s: column %s expands to %d values, the file declares %d'
                             % (path, name, len(values), declared))
            units[name] = unit
            if name in needed:
                columns[name] = values
            continue
        if line.strip():
            raise Refuse('%s: unreadable line %r' % (path, line[:60]))
    if samples is None:
        raise Refuse('%s states no sample count' % path)
    return {'identity': identity, 'samples': samples, 'windows': windows, 'columns': columns,
            'units': units, 'counts': counts, 'file': os.path.basename(path)}


def value_at(pairs, t):
    for index in range(1, len(pairs)):
        t0, v0 = pairs[index - 1]
        t1, v1 = pairs[index]
        if t0 <= t <= t1:
            if t1 == t0:
                return v0
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    if pairs:
        return pairs[-1][1]
    raise Refuse('no samples to interpolate')


def clipped(pairs, lo, hi, ctx):
    if hi <= lo:
        raise Refuse('%s: window %g..%g ps is empty' % (ctx, lo, hi))
    if lo < pairs[0][0] or hi > pairs[-1][0]:
        raise Refuse('%s: %g..%g ps lies outside the delivered samples %g..%g ps, so a value would '
                     'have to be extrapolated' % (ctx, lo, hi, pairs[0][0], pairs[-1][0]))
    return ([(lo, value_at(pairs, lo))]
            + [pair for pair in pairs if lo < pair[0] < hi]
            + [(hi, value_at(pairs, hi))])


def trapezoid(pairs):
    return sum((pairs[i + 1][0] - pairs[i][0]) * (pairs[i][1] + pairs[i + 1][1]) / 2.0
               for i in range(len(pairs) - 1)) * S_PER_PS


def signed_areas(pairs):
    positive, negative, crossings = 0.0, 0.0, 0
    for index in range(len(pairs) - 1):
        t0, v0 = pairs[index]
        t1, v1 = pairs[index + 1]
        dt = t1 - t0
        if dt <= 0:
            continue
        if v0 >= 0.0 and v1 >= 0.0:
            positive += dt * (v0 + v1) / 2.0
        elif v0 <= 0.0 and v1 <= 0.0:
            negative += dt * (v0 + v1) / 2.0
        else:
            tz = t0 + dt * (v0 / (v0 - v1))
            crossings += 1
            if v0 > 0.0:
                positive += (tz - t0) * v0 / 2.0
                negative += (t1 - tz) * v1 / 2.0
            else:
                negative += (tz - t0) * v0 / 2.0
                positive += (t1 - tz) * v1 / 2.0
    return positive * S_PER_PS, negative * S_PER_PS, crossings


def integrate(pairs, lo, hi, ctx):
    pts = clipped(pairs, lo, hi, ctx)
    q = trapezoid(pts)
    qp, qn, crossings = signed_areas(pts)
    tol = max(1e-30, abs(q) * 1e-9)
    if abs(q - (qp + qn)) > tol:
        raise Refuse('%s: Q %r is not Qpos %r plus Qneg %r' % (ctx, q, qp, qn))
    return {'q': q, 'q_pos': qp, 'q_neg': qn, 'points': len(pts), 'crossings': crossings}


def crossing(pairs, level, rising, lo, hi):
    window = [pair for pair in pairs if lo <= pair[0] <= hi]
    for index in range(1, len(window)):
        t0, v0 = window[index - 1]
        t1, v1 = window[index]
        if t1 == t0:
            continue
        if rising and v0 <= level < v1:
            return t0 + (level - v0) * (t1 - t0) / (v1 - v0)
        if (not rising) and v0 >= level > v1:
            return t0 + (level - v0) * (t1 - t0) / (v1 - v0)
    return None


def extreme(pairs, lo, hi):
    window = [pair for pair in pairs if lo <= pair[0] <= hi]
    if not window:
        return None, None
    best = max(window, key=lambda pair: pair[1])
    return best[1], best[0]


def number(text, ctx):
    if text is None or str(text).strip() == '':
        return None
    try:
        value = float(text)
    except ValueError:
        raise Refuse('%s holds %r, which is not a number' % (ctx, text))
    if not math.isfinite(value):
        raise Refuse('%s holds %r, which is not finite' % (ctx, text))
    return value


def close(got, want, context, limit=1e-9):
    """relative agreement at the precision the tables export, so a unit slip still shows up"""
    scale = max(abs(got), abs(want), 1e-30)
    return abs(got - want) <= limit * scale, '%s: %r against %r' % (context, got, want)


def deck_enable_regions(text, level, tail_ns=100.0):
    """the enable pulses as the delivered run copy declares them, in nanoseconds

    The 50 % instants come from the ramps, the pure-off region is the stretch of exact zero that
    follows the fall, and the leak window is the last tail_ns of it. This is the schedule the table
    claims to have measured, read from the deck rather than from the table.
    """
    for line in text.split('\n'):
        found = PWL_LINE_RE.match(line)
        if not found or found.group('node') != 'data_en':
            continue
        cells = found.group('wave').split()
        series = [(ns_of(cells[index]), float(cells[index + 1]))
                  for index in range(0, len(cells), 2)]
        regions, index = [], 1
        while index < len(series) - 1:
            t0, v0 = series[index - 1]
            t1, v1 = series[index]
            if not (v0 < level <= v1):
                index += 1
                continue
            rise = t0 + (level - v0) * (t1 - t0) / (v1 - v0)
            walk = index
            while walk < len(series) and series[walk][1] >= level:
                walk += 1
            if walk >= len(series):
                break
            ta, va = series[walk - 1]
            tb, vb = series[walk]
            fall = ta if vb == va else ta + (level - va) * (tb - ta) / (vb - va)
            zero = walk
            while zero < len(series) and series[zero][1] > 0.0:
                zero += 1
            if zero >= len(series):
                break
            end = zero
            while end + 1 < len(series) and series[end + 1][1] == 0.0:
                end += 1
            off_start, off_end = series[zero][0], series[end][0]
            regions.append({'rise_ns': rise, 'fall_ns': fall, 'off_start_ns': off_start,
                            'off_end_ns': off_end, 'tail_stop_ns': off_end,
                            'leak_start_ns': max(off_start, off_end - tail_ns)})
            index = end + 1
        return regions
    raise Refuse('the delivered run copy drives no data_en pwl source')



class Recompute(object):
    NEW_STATUSES = ('NATIVE_SEQUENCE_REINTEGRATION', 'RTL_INPUT_PROVENANCE',
                    'BUDGET_ACCOUNTING_STATUS')

    def __init__(self, root, require_new_statuses=True):
        self.root = root
        self.evidence = self.find_evidence()
        self.contract = json.loads(io.open(os.path.join(root, 'tests', 'dd1_d7c_b_tr',
                                                         'contract.json'), encoding='utf-8').read())
        self.environment = self.contract['electrical_environment']
        self.cases = dict((row['case_id'], row) for row in self.contract['cases'])
        self.checks = []
        self.require_new_statuses = require_new_statuses
        self.rows = self.table('windows_all.csv')
        self.statuses = self.table('statuses.csv')
        self.convergence = self.table('convergence.csv')
        self.spectre = {row['launch_id']: row
                        for row in self.table('spectre_launch_account.csv', 'native')}
        self.rtl = self.table('rtl_simulation_account.csv', 'native')
        self.dc = self.dc_table()
        self.sequences = {}

    def path(self, which, *parts):
        if which not in ('r1', 'native', 'tables'):
            raise Refuse('a recompute path must name which evidence directory it reads: %r' % which)
        return os.path.join(self.evidence[which], *parts)

    def find_evidence(self):
        """the exported sequences live in this round directory, the tables they re-derive are the
        frozen ones of the native round: the delivery does not copy a published record to judge it"""
        root = os.path.join(self.root, 'results', 'evidence')
        if not os.path.isdir(root):
            raise Refuse('the package holds no results/evidence directory')
        names = sorted(name for name in os.listdir(root) if name.startswith('dd1_d7c_b_tr_r'))
        exported = [name for name in names
                    if os.path.isdir(os.path.join(root, name, 'native_sequences'))]
        published = [name for name in names
                     if os.path.isfile(os.path.join(root, name, 'windows_all.csv'))]
        if not exported:
            raise Refuse('no evidence directory in the package carries native_sequences, so the '
                         'charge cannot be re-integrated from samples')
        if not published:
            raise Refuse('no DATA-7C-B-TR evidence directory inside the package publishes the '
                         'window tables')
        r1 = os.path.join(root, exported[-1])
        native = os.path.join(root, published[-1])
        tables = r1 if os.path.isfile(os.path.join(r1, 'windows_all.csv')) else native
        return {'r1': r1, 'native': native, 'tables': tables}

    def table(self, name, which='tables'):
        # the judged tables are this round's own re-extraction when it has published them, and the
        # frozen native ones while it has not; the ledgers stay the native records either way
        path = self.path(which, name)
        if not os.path.isfile(path):
            raise Refuse('%s is not in the evidence directory' % name)
        with io.open(path, encoding='utf-8', newline='') as handle:
            return list(csv.DictReader(handle))

    def dc_table(self):
        path = self.path('r1', 'dependencies', 'dc_matrix_dut.csv')
        if not os.path.isfile(path):
            raise Refuse('the accepted DC table is not shipped inside the package, so no IDC(k) can '
                         'be re-derived and no qtarget_dc claim can be checked')
        reference = self.contract['dc_reference']
        if sha_of(path) != reference['blob_sha256_at_base']:
            raise Refuse('the shipped DC dependency is %s while the contract accepts %s'
                         % (sha_of(path)[:12], reference['blob_sha256_at_base'][:12]))
        found = {}
        for cells in csv.DictReader(io.open(path, encoding='utf-8', newline='')):
            if cells['role'] != 'dut' or cells['clamp_V'] != '1.200':
                continue
            if cells['code'] in found:
                raise Refuse('the DC table carries two 1.20 V DUT rows for code %s' % cells['code'])
            if cells['corner'] != self.environment['corner'] or \
                    float(cells['temp_C']) != 27.0 or \
                    abs(float(cells['data_out_V']) - self.environment['clamp_V']) > 1e-9:
                raise Refuse('DC code %s is not the %s/27 C row at the %g V clamp'
                             % (cells['code'], self.environment['corner'],
                                self.environment['clamp_V']))
            found[cells['code']] = float(cells['I_sink_A'])
        if len(found) != 8:
            raise Refuse('the 1.20 V slice of the DC table has %d codes, it must have 8'
                         % len(found))
        return found

    def record(self, name, ok, detail=''):
        self.checks.append((name, bool(ok), '' if ok else str(detail)[:220]))

    # ---- sequences ---------------------------------------------------------------------------

    def sequence(self, case_id, role='dut'):
        key = (case_id, role)
        if key in self.sequences:
            return self.sequences[key]
        directory = self.path('r1', 'native_sequences')
        wanted = sorted(set(name.split('.part')[0] for name in os.listdir(directory)
                            if ('_%s_%s.sequence' % (case_id, role)) in name
                            and (name.endswith('.sequence.txt') or name.endswith('.sequence.gzip')
                                 or '.sequence.part' in name)))
        if len(wanted) > 1:
            raise Refuse('two native sequences are delivered for %s %s (%s), so which one the '
                         'published rows were integrated from cannot be named'
                         % (case_id, role, ', '.join(wanted)))
        if not wanted:
            raise Refuse('%s %s: the package ships no exported native sequence, so the charge of '
                         'this case cannot be re-integrated from samples' % (case_id, role))
        identity = read_identity(self.path('r1', 'native_sequences', wanted[0]))
        current = identity['native_current_column']
        made = restore(self.path('r1', 'native_sequences', wanted[0]),
                       ('time', current, 'data_en'))
        for name in ('time', current, 'data_en'):
            if name not in made['columns']:
                raise Refuse('%s %s: the exported sequence carries no %s column, so this window '
                             'cannot be re-integrated from samples'
                             % (case_id, identity.get('role', 'dut'), name))
        made['identity'] = dict(made['identity'], **identity)
        made['current_column'] = current
        # the tokens are seconds; every window in the published tables is named in picoseconds
        times_ps = [time / S_PER_PS for time in made['columns']['time']]
        made['series'] = list(zip(times_ps, made['columns'][current]))
        made['enable'] = list(zip(times_ps, made['columns']['data_en']))
        made['t_ps'] = times_ps
        self.sequences[key] = made
        return made

    def regions(self, case_id):
        key = ('regions', case_id)
        if key not in self.sequences:
            text = io.open(os.path.join(self.root, self.cases[case_id]['run_copy']),
                           encoding='utf-8', newline='').read()
            self.sequences[key] = deck_enable_regions(text, self.environment['enable_mid_V'])
        return self.sequences[key]

    def bind_sequence(self, case_id, row):
        """the answer a published window points at, and the launch that paid for it"""
        made = self.sequence(case_id)
        named = self.spectre.get(row['launch_id'])
        problems = []
        if named is None:
            problems.append('%s %s names launch %s, the account has no such row'
                            % (case_id, row['window_id'], row['launch_id']))
        else:
            if named['case_id'] != case_id or named['role'] != row['role']:
                problems.append('%s %s: launch %s belongs to %s/%s' % (case_id, row['window_id'],
                                                                       row['launch_id'],
                                                                       named['case_id'],
                                                                       named['role']))
            if named['state'] != 'CONFIRMED' or not named['raw_sha256']:
                problems.append('%s %s: launch %s is %s, not a confirmed start with a digested answer'
                                % (case_id, row['window_id'], row['launch_id'], named['state']))
            if row['raw_sha256'] != named['raw_sha256']:
                problems.append('%s %s publishes raw %s while launch %s digests %s'
                                % (case_id, row['window_id'], row['raw_sha256'][:12],
                                   row['launch_id'], named['raw_sha256'][:12]))
            if row['deck_sha256'] != named['deck_sha256']:
                problems.append('%s %s publishes deck %s while launch %s charged %s'
                                % (case_id, row['window_id'], row['deck_sha256'][:12],
                                   row['launch_id'], named['deck_sha256'][:12]))
        if made['identity'].get('raw_sha256') != row['raw_sha256']:
            problems.append('%s: the exported sequence digests %s, the published window points at %s'
                            % (case_id, made['identity'].get('raw_sha256', '')[:12],
                               row['raw_sha256'][:12]))
        deck = os.path.join(self.root, self.cases[case_id]['run_copy'])
        if not os.path.isfile(deck):
            problems.append('%s: the delivered run copy %s is not in the package'
                            % (case_id, self.cases[case_id]['run_copy']))
        elif sha_of(deck) != row['deck_sha256']:
            problems.append('%s: the delivered run copy on disk is %s while the window publishes %s'
                            % (case_id, sha_of(deck)[:12], row['deck_sha256'][:12]))
        return made, problems

    def format_checks(self):
        for case_id in sorted(self.cases):
            entry = self.cases[case_id]
            tick = float(entry['tick_ns'])
            qlsb = 1.875e-6 * tick * 1e-9
            self.record('%s: QLSB is 1.875 uA times its own %g ns reference tick'
                        % (case_id, tick),
                        abs(float(entry['qlsb_nominal_C']) - qlsb) <= 1e-30,
                        (entry['qlsb_nominal_C'], qlsb))
            if entry['class'] != 'HYB':
                continue
        for case_id in sorted(self.cases):
            try:
                made = self.sequence(case_id)
            except Refuse as error:
                self.record('%s: a native sequence is exportable' % case_id, False, str(error))
                continue
            times = made['t_ps']
            self.record('%s: the exported answer is strictly increasing over %d samples'
                        % (case_id, len(times)),
                        all(times[index] > times[index - 1] for index in range(1, len(times))),
                        (times[:2], len(times)))
            self.record('%s: every sample of the meter current is a finite number' % case_id,
                        all(math.isfinite(value) for value in made['columns'][
                            made['current_column']]), '')
            self.record('%s: the file declares its own units, seconds on the axis and amperes on the '
                        'meter current' % case_id,
                        made['units'].get('time') == 's'
                        and made['units'].get(made['current_column']) == 'A'
                        and made['units'].get('data_en') == 'V',
                        [made['units'].get(name) for name in ('time', made['current_column'],
                                                              'data_en')])

    def window_checks(self):
        seen = set()
        emission = []
        black = []
        level = self.environment['enable_mid_V']
        edge_ns = 2.0
        for row in self.rows:
            key = (row['case_id'], row['window_id'])
            if key in seen:
                raise Refuse('the published table holds the window key %s twice' % (key,))
            seen.add(key)
            for name in NUMERIC_CELLS:
                cell = row.get(name, '')
                if str(cell).strip() == '' or str(cell).replace('_', '').isalpha():
                    continue
                try:
                    number(cell, '%s %s %s' % (key[0], key[1], name))
                except Refuse as error:
                    raise Refuse(str(error))
            entry = self.cases.get(row['case_id'])
            if entry is None:
                raise Refuse('%s is not one of the nine contract cases' % row['case_id'])
            tick = float(entry['tick_ns'])
            qlsb = 1.875e-6 * tick * 1e-9
            self.record('%s %s: the table carries the case reference tick, not its own length'
                        % (key[0], key[1]),
                        abs(float(row['tick_ns']) - tick) <= 1e-12
                        and abs(float(row['qlsb_C']) - qlsb) <= 1e-30,
                        (row['tick_ns'], tick, row['qlsb_C'], qlsb))
            made, problems = self.bind_sequence(row['case_id'], row)
            if problems:
                raise Refuse(problems[0])
            if row['kind'] == 'emission':
                emission.append(row)
                self.emission_check(made, row, level, edge_ns, qlsb, entry)
            elif row['kind'] in BLACK_KINDS:
                black.append(row)
                self.black_check(made, row, qlsb)
        fixed = [row for row in emission if not row['case_id'].startswith('HYB')]
        expected = sum(int(self.cases[case]['emission_windows_in_source'])
                       for case in self.cases
                       if self.cases[case]['emission_windows_in_source'] != 'FROM_VCD')
        self.record('the 27 emission windows of the seven prepared cases are all present and no more',
                    len(fixed) == expected == 27, (len(fixed), expected))
        self.record('the published table holds exactly 37 window keys, 34 emission and 3 black',
                    len(self.rows) == 37 and len(emission) == 34 and len(black) == 3,
                    (len(self.rows), len(emission), len(black)))
        return emission, black

    def emission_check(self, made, row, level, edge_ns, qlsb, entry):
        ctx = '%s %s' % (row['case_id'], row['window_id'])
        start = float(row['window_start_ns'])
        stop = float(row['window_stop_ns'])
        rise_hint = (start - 2 * edge_ns) * 1e3, (start + 2 * edge_ns) * 1e3
        rise = crossing(made['enable'], level, True, *rise_hint)
        self.record('%s: the rising 0.9 V edge re-derived from the samples is the published one'
                    % ctx, rise is not None
                    and close(rise * S_PER_PS * 1e9, float(row['rise50_ns']), ctx)[0],
                    (rise, row['rise50_ns']))
        if rise is None:
            return
        fall_hint_lo = max(rise + 1.0, float(row['flat_stop_ns']) * 1e3)
        fall = crossing(made['enable'], level, False, fall_hint_lo, made['t_ps'][-1])
        self.record('%s: the falling 0.9 V edge re-derived from the samples is the published one'
                    % ctx, fall is not None
                    and close(fall * S_PER_PS * 1e9, float(row['fall50_ns']), ctx)[0],
                    (fall, row['fall50_ns']))
        if fall is None:
            return
        t50 = (fall - rise) * S_PER_PS * 1e9
        self.record('%s: T50 is the interval between the two native edges' % ctx,
                    close(t50, float(row['t50_ns']), ctx)[0], (t50, row['t50_ns']))
        regions = self.regions(row['case_id'])
        matched = [item for item in regions if abs(item['rise_ns'] * 1e3 - rise) <= 2.0]
        if not matched:
            self.record('%s: the delivered run copy drives an enable pulse at the instant this '
                        'window claims to start' % ctx, False,
                        ([(item['rise_ns'], item['fall_ns']) for item in regions][:4], rise))
            return
        region = matched[0]
        self.record('%s: the delivered run copy names the same 50 %% edges as the native samples'
                    % ctx,
                    close(region['rise_ns'], float(row['rise50_ns']), ctx)[0]
                    and close(region['fall_ns'], float(row['fall50_ns']), ctx)[0],
                    (region, row['rise50_ns'], row['fall50_ns']))
        current = made['series']
        full = integrate(current, rise, fall, '%s full' % ctx)
        for name, got in (('q_full_C', full['q']), ('q_pos_C', full['q_pos']),
                          ('q_neg_C', full['q_neg'])):
            self.record('%s: %s re-integrated from the native samples matches the published table'
                        % (ctx, name), close(got, float(row[name]), ctx)[0],
                        (got, row[name]))
        flat = integrate(current, float(row['flat_start_ns']) * 1e3,
                         float(row['flat_stop_ns']) * 1e3, '%s flat' % ctx)
        self.record('%s: the flat part re-integrates to the published figure' % ctx,
                    close(flat['q'], float(row['q_flat_C']), ctx)[0], (flat['q'], row['q_flat_C']))
        tail = integrate(current, fall, region['off_end_ns'] * 1e3, '%s tail' % ctx)
        self.record('%s: the tail re-integrates from the native fall to the end of the pure-off '
                    'region the deck declares' % ctx,
                    close(tail['q'], float(row['tail_q_C']), ctx)[0],
                    (tail['q'], row['tail_q_C'], region['off_end_ns']))
        leak_max, _leak_at = extreme([(t, abs(v)) for t, v in current],
                                      region['leak_start_ns'] * 1e3, region['off_end_ns'] * 1e3)
        self.record('%s: the last 100 ns of that pure-off region holds the published leak peak'
                    % ctx, close(leak_max, float(row['leak_max_abs_A']), ctx)[0],
                    (leak_max, row['leak_max_abs_A']))
        peak, peak_at = extreme(current, rise, fall)
        self.record('%s: the peak current and its instant come from the same samples' % ctx,
                    close(peak, float(row['peak_A']), ctx)[0]
                    and close(peak_at * S_PER_PS * 1e9, float(row['peak_ns']), ctx)[0],
                    (peak, row['peak_A'], peak_at, row['peak_ns']))
        span = float(row['flat_stop_ns']) - float(row['flat_start_ns'])
        self.record('%s: the flat mean is the flat charge over the flat span' % ctx,
                    close(flat['q'] / (span * 1e-9), float(row['flat_mean_A']), ctx)[0],
                    (flat['q'] / (span * 1e-9), row['flat_mean_A']))
        code = row['code']
        inom = (int(code, 2) + 1) * 1.875e-6
        idc = self.dc[code]
        t50_s = t50 * 1e-9
        target_nominal = inom * t50_s
        target_dc = idc * t50_s
        self.record('%s: the nominal target is (code+1) x 1.875 uA x the re-derived T50' % ctx,
                    close(target_nominal, float(row['qtarget_nominal_C']), ctx)[0],
                    (target_nominal, row['qtarget_nominal_C']))
        self.record('%s: the DC target is the accepted DC table current x the re-derived T50, never '
                    'the measured charge' % ctx,
                    close(target_dc, float(row['qtarget_dc_C']), ctx)[0],
                    (target_dc, row['qtarget_dc_C'], idc))
        for name, want in (('err_nominal_LSB', (full['q'] - target_nominal) / qlsb),
                           ('err_dynamic_LSB', (full['q'] - target_dc) / qlsb)):
            self.record('%s: %s re-derived from the samples and the frozen targets is the published '
                        'one' % (ctx, name), close(want, float(row[name]), ctx, 1e-6)[0],
                        (want, row[name]))
        self.settling_check(ctx, made, row, inom, idc, level)

    def settling_check(self, ctx, made, row, inom, idc, level):
        fraction = 0.05
        deadline = float(row['flat_stop_ns'])
        rise = float(row['rise50_ns'])
        window = [(pair[0] * S_PER_PS * 1e9, pair[1]) for pair in made['series']
                  if rise * 1e3 <= pair[0] <= deadline * 1e3]
        for label, target, cells in (
                ('nominal', inom, ('settling_nominal', 'settling_nominal_start_ns',
                                   'settling_nominal_last_out_ns',
                                   'settling_nominal_left_limit_A')),
                ('DC', idc, ('settling_dc', 'settling_dc_start_ns', 'settling_dc_last_out_ns',
                             'settling_dc_left_limit_A'))):
            if cells[1] not in row:
                raise Refuse('%s: the table publishes no settling %s columns, so where the %s target '
                             'settled, when it last left the band and what it read at the deadline '
                             'are not published at all' % (ctx, cells[1], label))
            state_cell, start_cell, out_cell, limit_cell = cells
            band = fraction * abs(target)
            outside = [time for time, value in window if abs(value - target) > band]
            published = row[out_cell]
            last_out = max(outside) if outside else None
            if published == '':
                ok = last_out is None or last_out <= rise
            else:
                ok = last_out is not None and close(last_out, float(published), ctx, 1e-6)[0]
            self.record('%s: the last sample outside the %s band, re-read from the samples, is the '
                        'published one' % (ctx, label), ok, (last_out, published))
            start = row[start_cell]
            state = row[state_cell]
            if state == 'SETTLED':
                if start == '':
                    self.record('%s: a SETTLED %s claim states where it settled' % (ctx, label),
                                False, state)
                    continue
                held = [(time, value) for time, value in window if time >= float(start)]
                self.record('%s: every sample from the published settling instant to the deadline is '
                            'inside the %s band, and it is held at least %g ns'
                            % (ctx, label, MIN_IN_BAND_NS),
                            held and all(abs(value - target) <= band for _t, value in held)
                            and float(start) > (last_out if last_out is not None else rise)
                            and deadline - float(start) >= MIN_IN_BAND_NS - 1e-9,
                            (start, last_out, len(held)))
            else:
                inside = [time for time, value in window
                          if abs(value - target) <= band and deadline - time >= MIN_IN_BAND_NS]
                self.record('%s: a %s state of %s is not contradicted by a stretch that held to the '
                            'deadline' % (ctx, label, state),
                            not inside or state.startswith('NOT_') or state in
                            ('ALREADY_ABOVE_AT_RISE', 'DEADLINE_OUT_OF_BAND',
                             'NO_DATA_IN_PULSE', 'LEFT_BAND_BEFORE_DEADLINE'),
                            (state, inside[:2]))

    def black_check(self, made, row, qlsb):
        ctx = '%s %s' % (row['case_id'], row['window_id'])
        start = float(row['window_start_ns']) * 1e3
        stop = float(row['window_stop_ns']) * 1e3
        charge = integrate(made['series'], start, stop, '%s black' % ctx)
        self.record('%s: the black window charge re-integrates over the whole window' % ctx,
                    close(charge['q'], float(row['q_full_C']), ctx)[0], (charge['q'], row['q_full_C']))
        peak, _at = extreme([(t, abs(v)) for t, v in made['series']], start, stop)
        self.record('%s: max(abs(I)) over the whole black window is the published leak figure' % ctx,
                    close(peak, float(row['leak_max_abs_A']), ctx)[0], (peak, row['leak_max_abs_A']))
        self.record('%s: a black window carries no invented T50 and a zero target' % ctx,
                    row['t50_ns'] == 'NOT_DEFINED_FOR_BLACK'
                    and float(row['qtarget_dc_C']) == 0.0
                    and float(row['qtarget_nominal_C']) == 0.0, row['t50_ns'])
        self.record('%s: the black error is its own charge over the same fixed QLSB' % ctx,
                    close(charge['q'] / qlsb, float(row['err_dynamic_LSB']), ctx, 1e-6)[0],
                    (charge['q'] / qlsb, row['err_dynamic_LSB']))

    def convergence_checks(self):
        limit = self.contract['convergence']['limit_rel_qlsb']
        by_key = dict(((row['case_id'], row['window_id']), row) for row in self.rows)
        sides = {}
        for row in self.convergence:
            for cell in ('tick_ns', 'qlsb_C', 'refined_q_C', 'coarse_q_C', 'dq_C',
                         'abs_dq_over_qlsb'):
                number(row[cell], 'convergence %s %s' % (row['pair'], cell))
            for side in ('refined', 'coarse'):
                key = (row['%s_case' % side], row['window_id'])
                if key not in by_key:
                    raise Refuse('convergence pair %s points at %s %s, the published table has no '
                                 'such window' % (row['pair'], key[0], key[1]))
                entry = self.cases[key[0]]
                if abs(float(row['tick_ns']) - float(entry['tick_ns'])) > 1e-12:
                    raise Refuse('convergence pair %s states a reference tick of %s while the '
                                 'contract freezes %g ns for %s'
                                 % (row['pair'], row['tick_ns'], float(entry['tick_ns']), key[0]))
                made = self.sequence(key[0])
                row_published = by_key[key]
                if row_published['kind'] != 'emission':
                    continue
                rise = float(row_published['rise50_ns']) * 1e3
                fall = float(row_published['fall50_ns']) * 1e3
                q = integrate(made['series'], rise, fall, 'convergence %s' % (key,))['q']
                sides[key] = q
        for row in self.convergence:
            refined = sides.get((row['refined_case'], row['window_id']))
            coarse = sides.get((row['coarse_case'], row['window_id']))
            if refined is None or coarse is None:
                continue
            ok_r, why_r = close(refined, float(row['refined_q_C']), 'convergence %s refined'
                                % row['pair'], 1e-6)
            ok_c, why_c = close(coarse, float(row['coarse_q_C']), 'convergence %s coarse'
                                % row['pair'], 1e-6)
            self.record('%s %s: both sides of the pair are windows this run re-integrated from '
                        'samples' % (row['pair'], row['window_id']), ok_r and ok_c,
                        why_r if not ok_r else why_c)
            qlsb = float(row['qlsb_C'])
            self.record('%s %s: the pair divides by 1.875 uA times the reference tick of both sides'
                        % (row['pair'], row['window_id']),
                        abs(qlsb - 1.875e-6 * float(row['tick_ns']) * 1e-9) <= 1e-30,
                        (qlsb, row['tick_ns']))
            ratio = abs(refined - coarse) / qlsb
            self.record('%s %s: dQ over QLSB re-derived and judged against the frozen %g'
                        % (row['pair'], row['window_id'], limit),
                        (ratio <= limit) == (row['status'] == 'PASS')
                        and abs(ratio - float(row['abs_dq_over_qlsb'])) <= 1e-6 * max(ratio, 1e-9),
                        (ratio, row['abs_dq_over_qlsb'], row['status']))
        self.record('the published convergence table carries 13 rows over three step pairs',
                    len(self.convergence) == 13, len(self.convergence))

    def status_checks(self, emission, black):
        published = dict((row['status'], row) for row in self.statuses)
        names = ('EXECUTION_COMPLETENESS', 'EVIDENCE_INTEGRITY', 'DYNAMIC_CHARGE_STATUS',
                 'NOMINAL_CHARGE_STATUS', 'SETTLING_STATUS', 'SHUTOFF_STATUS',
                 'CONVERGENCE_STATUS') + (Recompute.NEW_STATUSES if self.require_new_statuses
                                         else ())
        names = tuple(names)
        for name in names:
            self.record('the status %s is published exactly once' % name,
                        len([row for row in self.statuses if row['status'] == name]) == 1, name)
        dynamic = [row for row in emission + black if abs(float(row['err_dynamic_LSB'])) > 0.5]
        nominal = [row for row in emission + black if abs(float(row['err_nominal_LSB'])) > 0.5]
        self.record('the dynamic verdict is FAIL exactly when a re-derived error passes half an LSB',
                    (published['DYNAMIC_CHARGE_STATUS']['verdict'] == 'FAIL') == bool(dynamic),
                    (published['DYNAMIC_CHARGE_STATUS']['verdict'],
                     [(row['case_id'], row['window_id'], row['err_dynamic_LSB'])
                      for row in dynamic]))
        self.record('the nominal verdict is FAIL exactly when a re-derived nominal error passes half an '
                    'LSB, decided on its own column',
                    (published['NOMINAL_CHARGE_STATUS']['verdict'] == 'FAIL') == bool(nominal),
                    (published['NOMINAL_CHARGE_STATUS']['verdict'], len(nominal)))
        self.record('both charge columns are published side by side for every window, each against '
                    'its own target',
                    all(row['qtarget_nominal_C'] != row['qtarget_dc_C'] for row in emission),
                    [(row['case_id'], row['window_id']) for row in emission
                     if row['qtarget_nominal_C'] == row['qtarget_dc_C']][:3])
        leak_limit = 0.15e-6
        over = [row for row in emission if float(row['leak_max_abs_A']) > leak_limit]
        dark = [row for row in black if float(row['leak_max_abs_A']) > leak_limit]
        self.record('the shutoff verdict is FAIL exactly when an off tail or a black window breaks '
                    'the frozen %g A leak limit' % leak_limit,
                    (published['SHUTOFF_STATUS']['verdict'] == 'FAIL') == bool(over or dark),
                    (published['SHUTOFF_STATUS']['verdict'], len(over), len(dark)))
        self.record('the shutoff expectation counts emission tails and black windows together',
                    int(published['SHUTOFF_STATUS']['expected']) == len(emission) + len(black),
                    (published['SHUTOFF_STATUS']['expected'], len(emission), len(black)))
        settled = [row for row in emission
                   if row['settling_dc'] != 'SETTLED' or row['settling_nominal'] != 'SETTLED']
        self.record('the settling verdict agrees with the per-window states re-read from the samples',
                    (published['SETTLING_STATUS']['verdict'] == 'FAIL') == bool(settled),
                    (published['SETTLING_STATUS']['verdict'],
                     [(row['case_id'], row['window_id'], row['settling_dc'])
                      for row in settled][:4]))
        converged = any(row['status'] != 'PASS' for row in self.convergence)
        self.record('the convergence verdict is FAIL exactly when a re-derived dQ breaks the limit',
                    (published['CONVERGENCE_STATUS']['verdict'] == 'FAIL') == converged,
                    published['CONVERGENCE_STATUS']['verdict'])

    def ledger_checks(self):
        ceiling = self.contract['authorisation']['spectre_total_limit']
        main_ceiling = self.contract['accounting']['main_ledger_ceiling'] \
            if 'main_ledger_ceiling' in self.contract.get('accounting', {}) else None
        adjustments = self.contract.get('accounting', {})
        rows = list(self.spectre.values())
        charged = len(rows)
        strays = json.loads(io.open(self.path('native', 'spectre_budget_adjustments.json'),
                                    encoding='utf-8').read())
        stray_processes = sum(int(row['processes']) for row in strays['adjustments'])
        self.record('the approved task authorises %d Spectre processes in total' % ceiling,
                    ceiling == 24, ceiling)
        self.record('the main ledger holds %d rows and the recorded strays %d processes, against the '
                    'task total of %d' % (charged, stray_processes, ceiling),
                    charged + stray_processes <= ceiling, (charged, stray_processes))
        if main_ceiling is not None:
            self.record('the main ledger never exceeds its own enforced ceiling',
                        charged <= main_ceiling, (charged, main_ceiling))
        states = ('REQUESTED', 'CONFIRMED', 'FAILED', 'UNCERTAIN')
        self.record('every launch row is in a state the account admits',
                    all(row['state'] in states for row in rows),
                    sorted(set(row['state'] for row in rows)))
        self.record('an UNCERTAIN row keeps its charge: it is counted and never refunded',
                    any(row['state'] == 'UNCERTAIN' for row in rows),
                    [(row['launch_id'], row['state']) for row in rows if row['state'] == 'UNCERTAIN'])
        ids = [row['launch_id'] for row in sorted(rows, key=lambda r: r['launch_id'])]
        self.record('the launch ids are one unbroken run of T-numbers',
                    ids == ['T%03d' % index for index in range(1, len(ids) + 1)], ids[:4])

    def rtl_checks(self):
        ceiling = self.contract['authorisation']['rtl_simulation_total_limit']
        rows = self.rtl
        evidence_keys = ('exe_sha256', 'rc', 'vcd_sha256', 'log_sha256')
        # a row is a process as soon as it carries any evidence of one; requiring all three fields
        # would let a fifth start hide behind an empty vcd column and still be counted as four
        with_evidence = [row for row in rows if any(row.get(key) for key in evidence_keys)]
        distinct = set(row['exe_sha256'] for row in with_evidence if row.get('exe_sha256'))
        self.record('the RTL account never exceeds the four starts the task authorises',
                    len(rows) <= ceiling + 1, (len(rows), ceiling))
        self.record('an RTL row is counted as a process only by the executable digest it carries, '
                    'never by subtracting one from a row count',
                    len(distinct) == len(with_evidence) or len(distinct) <= ceiling,
                    (len(rows), len(with_evidence), len(distinct)))
        provenance = self.contract.get('not_verified', {})
        self.record('the joint-control input provenance is published as it was measured',
                    rows and all(row['case_id'].startswith('HYB') for row in rows),
                    sorted(set(row['case_id'] for row in rows)))
        self.record('five rows that each carry process evidence are five starts, never four',
                    len(with_evidence) == len(distinct) and len(with_evidence) <= ceiling,
                    'rows %d, rows with evidence %d, distinct executables %d'
                    % (len(rows), len(with_evidence), len(distinct)))
        self.record('RTL_PROCESS_COUNT is only claimed where each start has its own process evidence',
                    len(distinct) <= ceiling and len(with_evidence) <= ceiling,
                    'rows %d, rows carrying evidence %d, distinct executables %d, so the count of '
                    'starts this ledger can prove is %s'
                    % (len(rows), len(with_evidence), len(distinct),
                       len(distinct) if len(with_evidence) == len(distinct)
                       else 'NOT_INDEPENDENTLY_PROVEN'))

    def area_checks(self):
        """the integrator is shown against arithmetic a reviewer can do by hand before it judges any
        measured window: a rectangle, a triangle, a crossing split and an interpolated endpoint"""
        rectangle = integrate([(0.0, 2.0), (1000.0, 2.0), (2000.0, 2.0)], 0.0, 2000.0, 'rectangle')
        self.record('hand check: 2 A held for 2 ns is 4 nC',
                    abs(rectangle['q'] - 4e-9) <= 1e-20, rectangle['q'])
        triangle = integrate([(0.0, 0.0), (1000.0, 2.0)], 0.0, 1000.0, 'triangle')
        self.record('hand check: a ramp from 0 to 2 A over 1 ns is 1 nC',
                    abs(triangle['q'] - 1e-9) <= 1e-20, triangle['q'])
        crossing = integrate([(0.0, -1.0), (2000.0, 1.0)], 0.0, 2000.0, 'crossing')
        self.record('hand check: -1 A to +1 A over 2 ns splits into plus and minus 0.5 nC at the '
                    'crossing, and the net still cancels',
                    abs(crossing['q']) <= 1e-24 and abs(crossing['q_pos'] - 5e-10) <= 1e-21
                    and abs(crossing['q_neg'] + 5e-10) <= 1e-21 and crossing['crossings'] == 1,
                    crossing)
        endpoint = integrate([(0.0, 0.0), (1000.0, 4.0), (2000.0, 4.0)], 500.0, 1500.0, 'endpoint')
        self.record('hand check: a window starting inside a segment is interpolated to 2 A first, so '
                    '500 ps to 1500 ps is 3.5 nC', abs(endpoint['q'] - 3.5e-9) <= 1e-20,
                    endpoint['q'])

    def run(self):
        self.area_checks()
        self.format_checks()
        emission, black = self.window_checks()
        self.convergence_checks()
        self.status_checks(emission, black)
        self.ledger_checks()
        self.rtl_checks()
        return self.checks


def main(argv):
    root = argv[0] if argv and not argv[0].startswith('--') else ROOT
    preflight = '--preflight' in argv
    try:
        made = Recompute(root, require_new_statuses=not preflight)
        checks = made.run()
    except Refuse as error:
        print('RECOMPUTE_R1_REFUSED %s' % error)
        return 1
    failures = [(name, detail) for name, ok, detail in checks if not ok]
    for name, ok, _detail in checks:
        print('%-4s %s' % ('PASS' if ok else 'FAIL', name))
    print('RECOMPUTE_R1 %s %d/%d' % ('preflight' if preflight else 'gate',
                                     len(checks) - len(failures), len(checks)))
    for name, detail in failures:
        print('RECOMPUTE_R1_FAIL %s <- %s' % (name, detail))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
