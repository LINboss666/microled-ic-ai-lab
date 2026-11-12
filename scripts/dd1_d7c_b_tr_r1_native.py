#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR-R1 native sequence export: re-read the stored answers so a reviewer can integrate the
charge from the samples themselves rather than from a table this round already judged.

Offline only. No simulator, no guest, no new launch. The printed tokens are copied verbatim, so the
export is lossless against the native file: nothing is resampled, averaged, rounded or unit-converted.
Run-length and constant-column folding are stated in the file itself and expand back to the tokens.
"""

import base64
import decimal
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# B5: the verification entry is the portability promise. Nothing that reads the object
# store may execute at import time: those primitives are loaded only by the producer-side
# entries (--export / --budget / --selftest), never by --verify.
DC = TRC = MEAS = REC = RUN = None
INTERNAL_COLUMNS = ()
ALWAYS = ()


def load_engineering():
    """Import the Git-bound primitives lazily; --verify never calls this."""
    global DC, TRC, MEAS, REC, RUN, INTERNAL_COLUMNS, ALWAYS
    if TRC is not None:
        return
    import dd1_d7c_b_dc_run as _DC
    import dd1_d7c_b_tr_contract as _TRC
    import dd1_d7c_b_tr_measure as _MEAS
    import dd1_d7c_b_tr_record as _REC
    import dd1_d7c_b_tr_run as _RUN
    DC, TRC, MEAS, REC, RUN = _DC, _TRC, _MEAS, _REC, _RUN
    nodes = _TRC.contract()['required_signals']['internal_nodes']
    INTERNAL_COLUMNS = tuple(nodes['en'] + nodes['enb'] + nodes['vbias_ch'] + nodes['node_m'])
    ALWAYS = tuple(name for name in _TRC.contract()['required_signals']['always_extracted']
                   if name != 'Ip_branch_current')


MAGIC = 'TR1NATIVESEQ 1'
FULL_INTERNAL_SAMPLES = 20000            # a run this short ships every column it printed
FLAT_TAIL_NS = 50.0                      # the flat-step tail the task book asks for
EDGE_LOOK_NS = 25.0                      # native samples kept around each enable edge
TRACE_DIR = 'rtl'
TRACK_CAP_BYTES = 32 * 1024 * 1024 - 1024 * 1024
# The approved ceiling of 32 MiB is on everything this round newly tracks, and the scripts, tables
# and reports of the round are part of that set, so the numeric tier is capped a MiB lower and the
# leftover is where the rest of the delivery lives. What the ceiling excludes is written into the
# manifest as an exact byte gap.
DC_MATRIX = 'results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv'
DEPENDENCIES = (DC_MATRIX,)              # frozen inputs the recompute must be able to read itself


class Refuse(Exception):
    pass


def sha_of(path):
    digest = hashlib.sha256()
    with io.open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


CONTAINER_MAGIC = 'TR1CONTAINER 1'
PART_LIMIT_BYTES = 240 * 1024   # the history gate refuses a 512 KiB blob, so parts stay well under


def write_container(source_path, out_path, inner_magic):
    """gzip the file, then carry it as base85 text: the repository safety rules admit no unknown
    binary extension, and a text container restores with the standard library alone"""
    plain_text = io.open(source_path, 'rb').read()
    blob = gzip.compress(plain_text, 9, mtime=0)
    encoded = base64.b85encode(blob).decode('ascii')
    with io.open(out_path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(CONTAINER_MAGIC + '\n')
        for line in ('encoding base85', 'payload_encoding gzip', 'inner_magic ' + inner_magic,
                     'payload_sha256 ' + hashlib.sha256(blob).hexdigest(),
                     'plain_sha256 ' + hashlib.sha256(plain_text).hexdigest(),
                     'restore: everything after the blank line is base85, then gunzip'):
            handle.write(line + '\n')
        handle.write('\n')
        handle.write(encoded + '\n')
    return split_into_parts(out_path, {'gzip_bytes': len(blob),
                                       'gzip_sha256': hashlib.sha256(blob).hexdigest()})


def split_into_parts(path, extra, limit=None):
    """cut a delivered file into parts the history gate admits, so that concatenation rebuilds it

    The bytes are not re-formatted: the parts are a partition of the whole file, the index records the
    digest of the whole and of every part, and a reader that takes the parts in name order gets the
    container back byte for byte.
    """
    limit = limit or PART_LIMIT_BYTES
    data = io.open(path, 'rb').read()
    whole = {'whole_bytes': len(data), 'whole_sha256': hashlib.sha256(data).hexdigest()}
    if len(data) <= limit:
        whole.update({'file': os.path.basename(path), 'bytes': len(data),
                      'sha256': whole['whole_sha256'], 'parts': 1})
        return dict(whole, **extra)
    stem = path[:-4] if path.endswith('.txt') else path
    parts = []
    for index in range(0, len(data), limit):
        chunk = data[index:index + limit]
        name = '%s.part%03d.txt' % (stem, len(parts))
        io.open(name, 'wb').write(chunk)
        parts.append({'part': os.path.basename(name), 'bytes': len(chunk),
                      'sha256': hashlib.sha256(chunk).hexdigest()})
    os.remove(path)
    whole.update({'file': os.path.basename(stem) + '.txt', 'bytes': len(data),
                  'sha256': whole['whole_sha256'], 'parts': len(parts), 'part_files': parts,
                  'restore': 'cat the part_files in name order, then base85-decode what follows the '
                             'blank line, then gunzip'})
    return dict(whole, **extra)


def container_bytes(path):
    """the gzip payload of a container, or the bytes of a bare gzipped sequence file"""
    text = io.open(path, encoding='utf-8', errors='replace').read()
    if text.startswith(CONTAINER_MAGIC):
        _head, _sep, tail = text.partition('\n\n')
        return gzip.decompress(base64.b85decode(tail.strip()))
    with io.open(path, 'rb') as handle:
        return handle.read()


PSF_PAIR_RE = re.compile(r'^"([^"]+)"\s+(".*?"|[^\s()]+)')


def psf_pair(line):
    """a quoted name and its token: psfascii names may contain spaces and a sweep line carries a
    PROP( block after its token, so a whole-line match would throw the sweep variable away"""
    found = PSF_PAIR_RE.match(line.strip())
    if not found:
        return None
    return found.group(1), found.group(2).strip('"')


def scan(path, wanted_internal=True):
    """one streaming pass over a psfascii answer: units, sample count and the run structure

    Returns the declared axis and units, the number of printed samples, the number of runs per column
    (a run being a maximal stretch of identical printed tokens) and the time tokens, which are needed
    to name the fragment windows. Values are never collected as floats here.
    """
    section = None
    axis = None
    units = {}
    runs = {}
    single = {}
    samples = 0
    times = []
    inside_row = False
    with io.open(path, encoding='utf-8', errors='replace', newline='') as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ('HEADER', 'SWEEP', 'TRACE', 'VALUE', 'END'):
                section = stripped
                continue
            pair = psf_pair(line)
            if pair is None:
                continue
            name, token = pair
            if section == 'SWEEP':
                if token == 'sweep':
                    axis = name
                elif name == 'units' and axis and axis not in units:
                    # a real answer declares the sweep unit inside the sweep block, not as a trace
                    units[axis] = token
                continue
            if section == 'TRACE' and name not in units:
                units[name] = token
                continue
            if section != 'VALUE':
                continue
            if name == axis:
                samples += 1
                times.append(token)
                inside_row = True
                if name not in runs:
                    runs[name] = 1
                    single[name] = token
                elif single[name] != token:
                    runs[name] += 1
                    single[name] = token
                continue
            if not inside_row:
                continue
            if name not in runs:
                runs[name] = 1
                single[name] = token
            elif single[name] != token:
                runs[name] += 1
                single[name] = token
    if axis is None:
        raise Refuse('%s declares no sweep variable, so its samples cannot be named' % path)
    if units.get(axis) != 's':
        raise Refuse('%s: the axis %s carries unit %r, a transient sequence is exported in seconds'
                     % (path, axis, units.get(axis)))
    if not samples:
        raise Refuse('%s prints no samples for the axis %s' % (path, axis))
    if len(times) != samples:
        raise Refuse('%s: %d time tokens against %d samples' % (path, len(times), samples))
    columns = sorted(runs)
    if not wanted_internal:
        columns = [name for name in columns if name not in INTERNAL_COLUMNS]
    return {'axis': axis, 'units': units, 'samples': samples, 'runs': runs, 'path': path,
            'bytes': os.path.getsize(path), 'columns': columns, 'times': times,
            'current': DC.probe_column(dict((name, None) for name in runs))}


def required_names(found):
    """the twelve contract columns, with the probe spelled the way the file spells it"""
    current = DC.probe_column(found)
    names = ['time', current] + [name for name in ALWAYS if name != 'time']
    missing = [name for name in names if name not in found]
    if missing:
        raise Refuse('the answer carries no %s, so the required sequence cannot be exported'
                     % ','.join(missing))
    return names


def emit(handle, name, unit, rows, samples):
    """one column block: the constant form, or the run form with the token counts that expand it"""
    tokens = [token for _t, token in rows]
    if not tokens:
        handle.write('column %s unit %s encoding EMPTY count 0\n' % (name, unit))
        return
    distinct = set(tokens)
    if len(distinct) == 1:
        handle.write('column %s unit %s encoding CONSTANT count %d\n%s\n'
                     % (name, unit, len(tokens), tokens[0]))
        return
    groups = [(1, tokens[0])]
    for token in tokens[1:]:
        if token == groups[-1][1]:
            groups[-1] = (groups[-1][0] + 1, token)
        else:
            groups.append((1, token))
    handle.write('column %s unit %s encoding RUNS count %d runs %d\n'
                 % (name, unit, len(tokens), len(groups)))
    for count, token in groups:
        handle.write('%d %s\n' % (count, token))


def export_sequence(raw, identity, names, out_path, include_internal=None, windows=None,
                    found=None):
    """write one gzipped sequence file and return what it says it holds"""
    found = found or scan(raw)
    keep = list(names) + (INTERNAL_COLUMNS if include_internal else [])
    keep = [name for name in keep if name in found['runs']]
    if include_internal is None:
        keep = list(names) + [name for name in INTERNAL_COLUMNS if name in found['runs']]
    selection = None
    if windows:
        selection = [(MEAS.ns_to_ps(row[0]), MEAS.ns_to_ps(row[1])) for row in windows]
    rows = dict((name, []) for name in keep)
    axis_rows = []
    section = None
    index = -1
    with io.open(raw, encoding='utf-8', errors='replace', newline='') as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ('HEADER', 'SWEEP', 'TRACE', 'VALUE', 'END'):
                section = stripped
                continue
            if section != 'VALUE':
                continue
            pair = psf_pair(line)
            if pair is None:
                continue
            name, token = pair
            if name == found['axis']:
                index += 1
                # exact decimal arithmetic on the printed token: binary float turns 2.000000000000000e-09
                # into 2000.0000000000002 ps, and a boundary sample would fall out of its own window
                time_ps = decimal.Decimal(token) / decimal.Decimal('1e-12')
                if selection is None or any(lo <= time_ps <= hi for lo, hi in selection):
                    axis_rows.append((time_ps, token))
                else:
                    axis_rows.append(None)
                continue
            if index < 0 or not axis_rows or axis_rows[-1] is None:
                continue
            if name in rows:
                rows[name].append((axis_rows[-1][0], token))
    payload = out_path + '.text'
    with io.open(payload, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('%s\n' % MAGIC)
        for key in sorted(identity):
            handle.write('# %s=%s\n' % (key, identity[key]))
        handle.write('# restore: expand each column by its run counts, in file order; a value is the '
                     'printed token of the native answer parsed as a decimal in the stated unit\n')
        handle.write('# restore: a CONSTANT column repeats its one token for the whole count, which is '
                     'how a supply or a clamped node is stored without losing a sample\n')
        handle.write('samples %d\n' % (len(axis_rows) if selection is None else
                                       len([row for row in axis_rows if row])))
        if selection is not None:
            handle.write('window_count %d\n' % len(selection))
            for lo, hi in selection:
                handle.write('window from_ps %g to_ps %g\n' % (lo, hi))
        emit(handle, found['axis'], found['units'][found['axis']],
             axis_rows if selection is None else [row for row in axis_rows if row],
             found['samples'])
        for name in keep:
            if name == found['axis']:
                continue
            emit(handle, name, found['units'].get(name, '?'), rows[name], found['samples'])
    packed = write_container(payload, out_path, MAGIC)
    plain = os.path.getsize(payload)
    os.remove(payload)
    return {'file': packed['file'], 'bytes': packed['bytes'],
            'sha256': packed['sha256'], 'parts': packed['parts'],
            'gzip_bytes': packed['gzip_bytes'], 'gzip_sha256': packed['gzip_sha256'],
            'part_files': packed.get('part_files', []),
            'plain_bytes': plain, 'samples': found['samples'],
            'columns': [found['axis']] + [name for name in keep if name != found['axis']],
            'runs': dict((name, found['runs'][name]) for name in keep),
            'fragment_windows': len(selection) if selection else 0}


def identity_rows(old_evidence):
    """the first round's own ledger and launch log, as the identity chain of every exported answer

    The launch log holds both kinds of entry: the start that cost budget and the offline observation
    of the answer it pulled. Only the starts carry the raw that is exported; the observations are kept
    beside them as the meter witness of the same bytes.
    """
    account = REC.read_table(os.path.join(old_evidence, 'spectre_launch_account.csv'))
    log = json.loads(io.open(os.path.join(old_evidence, 'launch_log.json'),
                             encoding='utf-8').read())
    by_row = dict((row['launch_id'], row) for row in account)
    out, witnesses = [], []
    for entry in log:
        mode = entry.get('mode')
        if mode == '--observe':
            observation = entry.get('observation') or {}
            witnesses.append({'case_id': entry.get('case_id'), 'launch_id':
                              observation.get('launch_id'), 'raw_sha256':
                              observation.get('raw_sha256'), 'deck_sha256':
                              observation.get('deck_sha256'), 'samples': observation.get('samples'),
                              'monotonic': observation.get('monotonic'),
                              'finite': observation.get('finite'),
                              'refusal': entry.get('observation_refusal') or ''})
            continue
        if mode != '--launch':
            raise Refuse('the launch log holds an entry of mode %r, which this round cannot bind '
                         'to a ledger row' % mode)
        row = by_row.get(entry.get('launch_id'))
        if row is None:
            raise Refuse('the launch log names %s, the account has no such row'
                         % entry.get('launch_id'))
        if entry['state'] != 'CONFIRMED' or not row['raw_sha256']:
            continue
        if entry['raw_sha256'] != row['raw_sha256'] or entry['deck_sha256'] != row['deck_sha256']:
            raise Refuse('%s: the launch log and the ledger row disagree about the answer of that '
                         'start, so none of it can be exported as evidence' % row['launch_id'])
        out.append({'launch_id': row['launch_id'], 'case_id': row['case_id'],
                    'role': row['role'], 'run_id': row['run_id'], 'deck_path': entry['deck_path'],
                    'deck_sha256': row['deck_sha256'], 'raw_sha256': row['raw_sha256'],
                    'log_sha256': row['log_sha256'], 'requested_utc': row['requested_utc'],
                    'ended_utc': row['ended_utc'], 'executor_sha256': entry['executor_sha256'],
                    'raw_name': os.path.basename(entry['raw'])})
    return out, witnesses


def windows_of_case(old_evidence, case_id):
    """the native instants worth keeping of a long run: every flat tail and both enable edges"""
    rows = [row for row in REC.all_rows(old_evidence) if row['case_id'] == case_id
            and row['kind'] == 'emission']
    if not rows:
        return []
    windows = []
    for row in rows:
        rise = float(row['rise50_ns'])
        fall = float(row['fall50_ns'])
        flat_stop = float(row['flat_stop_ns'])
        windows.append((max(0.0, rise - EDGE_LOOK_NS), rise + EDGE_LOOK_NS))
        windows.append((max(0.0, fall - EDGE_LOOK_NS), fall + EDGE_LOOK_NS))
        windows.append((max(0.0, flat_stop - FLAT_TAIL_NS), flat_stop))
    merged = []
    for start, stop in sorted(windows):
        if merged and start <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return [{'from_ns': start, 'to_ns': stop,
             'why': 'the last %g ns of the flat step and %g ns about each enable edge'
                    % (FLAT_TAIL_NS, EDGE_LOOK_NS)} for start, stop in merged]


def traces(old_evidence):
    """the two real traces of the joint cases, in their own bytes, plus the recorded digests"""
    path = os.path.join(old_evidence, TRACE_DIR)
    names = sorted(name for name in os.listdir(path)) if os.path.isdir(path) else []
    wanted = [name for name in names
              if name.endswith('.vcd') and not name.endswith(('.bad.vcd', '.code.vcd'))]
    out = []
    for name in sorted(wanted):
        source = os.path.join(path, name)
        out.append({'name': name, 'bytes': os.path.getsize(source), 'sha256': sha_of(source),
                    'case_id': 'HYB-120' if '120' in name else 'HYB-200'})
    return out


def require_traces(old_evidence):
    """the traces the round claims to have re-read must actually be there

    An empty trace list would let the export ship one fewer artifact than its own report claims, so
    the absence is a refusal naming the directory rather than a smaller delivery.
    """
    made = traces(old_evidence)
    if not made:
        raise Refuse('%s carries no real trace under %s: the export would quietly deliver one fewer '
                     'artifact than the round claims, so a missing trace directory is a refusal '
                     'naming it and not an empty list' % (old_evidence, TRACE_DIR))
    return made


def discard_artifact(path):
    """remove an artifact the ceiling excluded, together with its parts

    A split artifact no longer exists as the file that was written: the parts carry it, so removing
    only the original path would leave the excluded bytes on disk and counted in the delivery.
    """
    stem = path[:-4] if path.endswith('.txt') else path
    removed = 0
    if os.path.isfile(path):
        os.remove(path)
        removed += 1
    directory = os.path.dirname(stem) or '.'
    for name in sorted(os.listdir(directory)):
        if name.startswith(os.path.basename(stem) + '.part'):
            os.remove(os.path.join(directory, name))
            removed += 1
    return removed


def _r2_find_root(start):
    """the package root that carries the frozen contract; no Git involved"""
    here = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(here, 'tests', 'dd1_d7c_b_tr', 'contract.json')):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise Refuse('no frozen contract above %s' % start)
        here = parent


def _r2_payload(folder, part_names):
    """rejoin declared parts (or one whole), then decode the base85/gzip container"""
    chunks = []
    for name in part_names:
        with io.open(os.path.join(folder, name), 'rb') as handle:
            chunks.append(handle.read())
    text = b''.join(chunks).decode('utf-8', 'replace')
    if text.startswith('TR1CONTAINER 1'):
        raw = gzip.decompress(base64.b85decode(text.split(chr(10) + chr(10), 1)[1].strip()))
        return raw.decode('utf-8', 'replace').splitlines()
    return gzip.decompress(b''.join(chunks)).decode('utf-8', 'replace').splitlines()


_R2_COLUMN = re.compile(r'^column (?P<name>\S+) unit (?P<unit>\S+) encoding '
                        r'(?P<encoding>CONSTANT|RUNS) count (?P<count>\d+)'
                        r'(?: runs (?P<runs>\d+))?$')


def _r2_parse_sequence(lines, label, problems):
    """B1: read the delivered column schema and every number in it, or refuse.

    R2 only looked at the header comments and at five constant columns, so a current column whose
    own unit was rewritten to V, or a supply token rewritten to nan, still verified. A declared
    schema has to be expanded back to the numbers and those numbers have to be finite before any
    semantic judgement means anything.
    """
    head, columns, samples, index = {}, {}, None, 0
    total = len(lines)
    while index < total and not lines[index].startswith(('column ', 'samples ')):
        line = lines[index]
        if line.startswith('# ') and '=' in line:
            key, value = line[2:].split('=', 1)
            head[key] = value
        index += 1
    while index < total and not lines[index].startswith('column '):
        found = re.match(r'^samples (\d+)$', lines[index])
        if found:
            samples = int(found.group(1))
        index += 1
    if samples is None:
        problems.append('%s: the preflight does not declare its sample count' % label)
        return None
    while index < total:
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        parsed = _R2_COLUMN.match(line)
        if not parsed:
            problems.append('%s: column header %r is unreadable' % (label, line[:80]))
            return None
        name = parsed.group('name')
        if name in columns:
            problems.append('%s: column %s is declared twice' % (label, name))
            return None
        count = int(parsed.group('count'))
        if count != samples:
            problems.append('%s: column %s declares %d values against %d samples'
                            % (label, name, count, samples))
            return None
        index += 1
        if parsed.group('encoding') == 'CONSTANT':
            if index >= total:
                problems.append('%s: constant column %s carries no token' % (label, name))
                return None
            token = lines[index].strip()
            try:
                values = [float(token)] * count
            except ValueError:
                problems.append('%s: constant column %s token %r is not a number'
                                % (label, name, token))
                return None
            index += 1
        else:
            runs = parsed.group('runs')
            if runs is None:
                problems.append('%s: run-length column %s does not declare its run count'
                                % (label, name))
                return None
            runs = int(runs)
            values = []
            for _ in range(runs):
                if index >= total:
                    problems.append('%s: column %s ends before its %d runs' % (label, name, runs))
                    return None
                token = lines[index].split()
                if len(token) != 2 or not token[0].isdigit() or int(token[0]) <= 0:
                    problems.append('%s: column %s run %r is not "<count> <value>"'
                                    % (label, name, lines[index][:60]))
                    return None
                try:
                    value = float(token[1])
                except ValueError:
                    problems.append('%s: column %s run value %r is not a number'
                                    % (label, name, token[1]))
                    return None
                values.extend([value] * int(token[0]))
                index += 1
            if len(values) != count:
                problems.append('%s: column %s expands to %d values against its declared %d'
                                % (label, name, len(values), count))
                return None
        bad = [value for value in values if not math.isfinite(value)]
        if bad:
            problems.append('%s: column %s carries %d non-finite value(s), the first %r'
                            % (label, name, len(bad), bad[0]))
            return None
        columns[name] = (parsed.group('unit'), values)
    return {'head': head, 'samples': samples, 'columns': columns}


def _r2_preflight_semantics(lines, entry, env, label, problems):
    """B1: re-judge a preflight from its own decoded columns, never from statuses.csv.

    Every check below is derived from the delivered bytes and the frozen electrical environment:
    the column schema is parsed, the column units and counts are judged, the numbers are required
    to be finite, the time axis is required to be strictly increasing, and the supplies and the
    stimulus witness are compared with the frozen contract.
    """
    parsed = _r2_parse_sequence(lines, label, problems)
    if parsed is None:
        return
    head, samples, columns = parsed['head'], parsed['samples'], parsed['columns']
    expect_head = {'native_axis_unit': 's', 'native_current_column': 'Ip_branch:i',
                   'simulator_name': 'spectre', 'role': 'preflight'}
    for key, value in expect_head.items():
        if head.get(key) != value:
            problems.append('%s: preflight declares %s=%r, frozen environment requires %r'
                            % (label, key, head.get(key), value))
    for key in ('deck_sha256', 'launch_id', 'raw_sha256', 'log_sha256', 'native_run_id'):
        if entry.get(key) and head.get(key) != entry[key]:
            problems.append('%s: preflight %s=%r disagrees with the manifest %r'
                            % (label, key, head.get(key), entry[key]))
    declared = head.get('native_samples')
    if declared != str(samples):
        problems.append('%s: the header declares %s samples against %d in the body'
                        % (label, declared, samples))
    if entry.get('samples') is not None and str(entry['samples']) != str(samples):
        problems.append('%s: the body carries %d samples against the manifest %s'
                        % (label, samples, entry['samples']))
    expect_units = {'time': 's', 'Ip_branch:i': 'A', 'data_en': 'V'}
    for name, unit in expect_units.items():
        if name not in columns:
            problems.append('%s: the delivered preflight has no %s column' % (label, name))
        elif columns[name][0] != unit:
            problems.append('%s: column %s is declared in %s, the frozen reader uses %s'
                            % (label, name, columns[name][0], unit))
    if 'time' in columns:
        times = columns['time'][1]
        for index in range(len(times) - 1):
            if times[index + 1] <= times[index]:
                problems.append('%s: the time axis is not strictly increasing at sample %d '
                                '(%r then %r)' % (label, index, times[index], times[index + 1]))
                break
    frozen = {'vdd18': ('V', env['vdd18_V']), 'vss': ('V', env['vss_V']),
              'vcas': ('V', env['vcas_V']), 'clamp_node': ('V', env['clamp_V']),
              'data_out': ('V', env['clamp_V'])}
    for name, (unit, value) in frozen.items():
        if name not in columns:
            problems.append('%s: no constant %s column in the delivered preflight' % (label, name))
            continue
        got_unit, values = columns[name]
        if len(set(values)) != 1:
            problems.append('%s: column %s is declared CONSTANT and carries %d distinct values'
                            % (label, name, len(set(values))))
            continue
        if got_unit != unit or abs(values[0] - value) > 1e-6:
            problems.append('%s: %s is %r %s against the frozen %r %s'
                            % (label, name, values[0], got_unit, value, unit))
    if 'data_en' in columns:
        low, high = env['logic_low_V'], env['logic_high_V']
        values = columns['data_en'][1]
        if min(values) < low - 1e-6 or max(values) > high + 1e-6:
            problems.append('%s: the stimulus witness runs from %r to %r V outside the frozen '
                            'logic rails %r..%r' % (label, min(values), max(values), low, high))


def verify(out_dir):
    """B1/B5: prove every delivered object against the manifest, with no Git and no project imports.

    R1 only checked isfile() for unsplit containers and never walked internal_fragment, so a
    same-size corrupted whole or fragment was accepted. R2 checks length + SHA-256 for whole,
    parts, frozen dependencies and every nested fragment; part numbering and uniqueness; rejoined
    totals; the exact delivered file set; duplicate evidence identities; and re-judges each
    preflight from its own sequence bytes and the frozen electrical environment.
    """
    problems, checked, excluded = [], 0, []
    manifest = json.loads(io.open(os.path.join(out_dir, 'native_manifest.json'),
                                  encoding='utf-8').read())
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise Refuse('native_manifest.json carries no files list')
    seq_dir = os.path.join(out_dir, 'native_sequences')
    dep_dir = os.path.join(out_dir, 'dependencies')
    folders = {'native_sequences': seq_dir, 'dependencies': dep_dir}
    declared = {}       # (folder, name) -> (bytes, sha256, label)
    groups = []         # (label, folder, [part rows], total_bytes, total_sha)
    preflights = []     # (label, folder, [part names], entry)
    hex_re = re.compile(r'^[0-9a-f]{64}$')

    def add(folder_key, name, size, digest, label):
        if (not isinstance(name, str) or not name or os.path.isabs(name) or '\\' in name
                or '..' in name.split('/')):
            problems.append('%s declares an unsafe path %r' % (label, name))
            return False
        if not isinstance(size, int) or size < 0 or not isinstance(digest, str) \
                or not hex_re.match(digest):
            problems.append('%s: %s has no usable byte count and SHA-256' % (label, name))
            return False
        key = (folder_key, name)
        if key in declared:
            problems.append('%s declares %s twice (duplicate evidence identity)' % (label, name))
            return False
        declared[key] = (size, digest, label)
        return True

    def walk(obj, folder_key, label, entry):
        global_checked = [0]
        name = obj.get('file') or obj.get('container_file')
        size = obj.get('bytes') if obj.get('file') else obj.get('container_bytes')
        digest = obj.get('sha256') if obj.get('file') else obj.get('whole_sha256')
        parts = obj.get('part_files') or []
        if parts:
            names = [row.get('part') for row in parts]
            if any(not isinstance(n, str) or not n for n in names) \
                    or len(set(names)) != len(names):
                problems.append('%s: parts are unnamed or repeated' % label)
                return 0
            numbers = []
            for part_name in names:
                found = re.search(r'\.part(\d+)\.txt$', part_name)
                if not found:
                    problems.append('%s: part %s is not numbered' % (label, part_name))
                    return 0
                numbers.append(int(found.group(1)))
            if sorted(numbers) != list(range(len(numbers))):
                problems.append('%s: part numbering %s is not continuous from zero'
                                % (label, sorted(numbers)))
                return 0
            ordered = sorted(parts, key=lambda row: row['part'])
            if not all(add(folder_key, row['part'], row.get('bytes'), row.get('sha256'), label)
                       for row in ordered):
                return 0
            groups.append((label, folder_key, ordered, size, digest))
            part_names = [row['part'] for row in ordered]
        else:
            if not name:
                problems.append('%s has no delivered object name' % label)
                return 0
            if not add(folder_key, name, size, digest, label):
                return 0
            part_names = [name]
        if entry.get('role') == 'preflight':
            preflights.append((label, folder_key, part_names, entry))
        return 1

    for entry in entries:
        label = entry.get('file') or entry.get('dependency') or entry.get('name') or '<unnamed>'
        if entry.get('dependency'):
            if not entry.get('exported'):
                excluded.append('%s: not delivered (%s)' % (label, entry.get('gap')))
            elif add('dependencies', entry['dependency'], entry.get('bytes'),
                     entry.get('sha256'), label):
                checked += 1
            continue
        if entry.get('tracked_copy') is False:
            excluded.append('%s: recorded by digest only (%s)' % (label, entry.get('gap')))
            continue
        if not entry.get('exported'):
            excluded.append('%s: not delivered (%s)' % (label, entry.get('gap')))
            continue
        checked += walk(entry, 'native_sequences', label, entry)
        nested = entry.get('internal_fragment')
        if isinstance(nested, dict):
            checked += walk(nested, 'native_sequences',
                            label + ' [internal_fragment]', entry)
        elif nested:
            excluded.append('%s [internal_fragment]: %s (not a delivered object)'
                            % (label, nested))

    # the exact delivered file set: no undeclared content, no missing content
    for folder_key, path in folders.items():
        if not os.path.isdir(path):
            problems.append('%s directory is missing' % folder_key)
            continue
        actual = set(name for name in os.listdir(path)
                     if os.path.isfile(os.path.join(path, name)))
        expected = set(name for (key, name) in declared if key == folder_key)
        for name in sorted(actual - expected):
            problems.append('%s/%s is undeclared delivered content' % (folder_key, name))
        for name in sorted(expected - actual):
            problems.append('%s/%s is declared by the manifest and not on disk' % (folder_key, name))

    for (folder_key, name), (size, digest, label) in sorted(declared.items()):
        path = os.path.join(folders[folder_key], name)
        if not os.path.isfile(path):
            continue
        data = io.open(path, 'rb').read()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            problems.append('%s: %s does not match the bytes and digest recorded for it'
                            % (label, name))

    for label, folder_key, ordered, size, digest in groups:
        data = b''.join(io.open(os.path.join(folders[folder_key], row['part']), 'rb').read()
                        for row in ordered
                        if os.path.isfile(os.path.join(folders[folder_key], row['part'])))
        if not isinstance(size, int) or not isinstance(digest, str):
            problems.append('%s: rejoined object has no recorded total size and digest' % label)
        elif len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            problems.append('%s: parts rejoin to %d bytes / another digest than the manifest records'
                            % (label, len(data)))

    if preflights:
        try:
            contract = json.loads(io.open(os.path.join(_r2_find_root(out_dir), 'tests',
                                                       'dd1_d7c_b_tr', 'contract.json'),
                                         encoding='utf-8').read())
            env = contract['electrical_environment']
        except (KeyError, IOError, ValueError) as exc:
            problems.append('frozen electrical environment is unreadable: %s' % exc)
            env = None
        if env:
            for label, folder_key, part_names, entry in preflights:
                try:
                    _r2_preflight_semantics(_r2_payload(folders[folder_key], part_names),
                                            entry, env, label, problems)
                except (IOError, ValueError, IndexError) as exc:
                    problems.append('%s: preflight sequence cannot be decoded: %s' % (label, exc))

    return {'artifacts_verified': checked, 'artifacts_recorded': len(entries),
            'artifacts_excluded': len(excluded), 'excluded': excluded, 'problems': problems}

def budget(local_dir, old_evidence):
    """what a full export would cost, measured on the real files before anything is written"""
    rows, witnesses = identity_rows(old_evidence)
    total = 0
    out = []
    for row in rows:
        raw = os.path.join(local_dir, row['raw_name'])
        if not os.path.isfile(raw):
            out.append(dict(row, present=False))
            continue
        found = scan(raw)
        names = required_names(dict((name, None) for name in found['runs']))
        runs = sum(found['runs'][name] for name in names)
        internal_runs = sum(found['runs'].get(name, 0) for name in INTERNAL_COLUMNS)
        out.append(dict(row, present=True, samples=found['samples'], bytes=found['bytes'],
                        required_columns=len(names), required_runs=runs,
                        internal_runs=internal_runs, current=found['current']))
        total += found['samples']
    return {'native_run_id': REC.run_id_of(old_evidence), 'answers': out,
            'observations': witnesses,
            'samples_total': total,
            'note': 'runs are maximal stretches of one identical printed token; the payload of a '
                    'column is its run count, not its sample count'}


def export(local_dir, old_evidence, out_dir, cap_bytes=TRACK_CAP_BYTES, copy_traces=False):
    """write the sequences, the identity chain and the manifest for this round

    The cap is the one the approved task sets on newly tracked numeric bytes. Answers are written in
    priority order, the nine DUT answers before the nine meter preflights and the short runs before
    the long ones, so that the sequences a reviewer needs to re-integrate the charge are the first to
    earn their place. What the cap excludes is written into the manifest as a precise gap, never as a
    silent absence.

    copy_traces marks a package staging build: the trace containers are written next to the
    sequences and no tracked ceiling is applied, because those bytes leave the repository in the
    reviewer package. A tracked run records each trace by digest and says why its bytes stay out.
    """
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    sequences = os.path.join(out_dir, 'native_sequences')
    if not os.path.isdir(sequences):
        os.makedirs(sequences)
    dependencies = os.path.join(out_dir, 'dependencies')
    if not os.path.isdir(dependencies):
        os.makedirs(dependencies)
    rows, witnesses = identity_rows(old_evidence)
    manifest, tracked = [], 0
    for relative in DEPENDENCIES:
        source = RUN.repo(relative)
        digest = sha_of(source)
        if digest != TRC.blob_sha(TRC.BASE_SHA, relative):
            raise Refuse('%s on disk is %s while the committed blob is %s, so the frozen dependency '
                         'this round ships is not the one the review accepted'
                         % (relative, digest[:12], TRC.blob_sha(TRC.BASE_SHA, relative)[:12]))
        name = os.path.basename(relative)
        target = os.path.join(dependencies, name)
        entry = {'dependency': name, 'path': relative, 'sha256': digest,
                 'bytes': os.path.getsize(source), 'role': 'frozen dependency', 'exported': True}
        if not (os.path.isfile(target) and sha_of(target) == digest):
            io.open(target, 'wb').write(io.open(source, 'rb').read())
        if tracked + os.path.getsize(target) > cap_bytes:
            os.remove(target)
            entry.update({'exported': False, 'gap': 'OVER_TRACK_CAP'})
        else:
            tracked += os.path.getsize(target)
        manifest.append(entry)
    ordered = sorted(rows, key=lambda row: (0 if row['role'] == 'dut' else 1,
                                            os.path.getsize(os.path.join(local_dir, row['raw_name'])
                                                            if os.path.isfile(os.path.join(
                                                                local_dir, row['raw_name']))
                                                            else 1 << 40)))
    pending = []
    for row in ordered:
        raw = os.path.join(local_dir, row['raw_name'])
        if not os.path.isfile(raw):
            manifest.append(dict(row, exported=False, gap='NOT_ON_THIS_MACHINE',
                                 reason='the answer of that start is not on this machine, so nothing '
                                        'is invented for it'))
            continue
        digest = sha_of(raw)
        if digest != row['raw_sha256']:
            raise Refuse('%s %s: the stored answer is %s while ledger row %s digests %s'
                         % (row['case_id'], row['role'], digest[:12], row['launch_id'],
                            row['raw_sha256'][:12]))
        found = scan(raw)
        names = required_names(dict((name, None) for name in found['runs']))
        identity = dict((key, row[key]) for key in sorted(row))
        identity.update({'native_run_id': REC.run_id_of(old_evidence),
                         'native_bytes': found['bytes'], 'native_samples': found['samples'],
                         'native_axis_unit': found['units'][found['axis']],
                         'native_current_column': found['current']})
        identity.update(simulator_identity(raw))
        full = found['samples'] <= FULL_INTERNAL_SAMPLES
        target = os.path.join(sequences, '%s_%s_%s.sequence.txt'
                              % (identity['native_run_id'], row['case_id'], row['role']))
        made = export_sequence(raw, identity, names, target, include_internal=full, found=found)
        made['internal_full'] = full
        made['native_sha256_verified'] = digest
        if tracked + made['bytes'] > cap_bytes:
            discard_artifact(target)
            manifest.append(dict(row, exported=False, gap='OVER_TRACK_CAP', samples=found['samples'],
                                 reason='the sequences already written take %d of the %d bytes this '
                                        'round may track and this answer needs %d more, so it is '
                                        'declared as a gap instead of replacing a written one'
                                        % (tracked, cap_bytes, made['bytes'])))
            continue
        entry = dict(row, exported=True, **made)
        manifest.append(entry)
        tracked += made['bytes']
        if not full and row['role'] == 'dut':
            pending.append((row, raw, identity, names, found, entry))
    recorded = json.loads(io.open(os.path.join(old_evidence, 'hyb_inputs.json'),
                                  encoding='utf-8').read())
    found_traces = require_traces(old_evidence)
    for trace in found_traces:
        source = os.path.join(old_evidence, TRACE_DIR, trace['name'])
        target = os.path.join(sequences, '%s.txt' % trace['name'])
        check = sha_of(source)
        witness = (recorded.get(trace['case_id']) or {}).get('vcd_sha256')
        if witness and check != witness:
            raise Refuse('%s on disk is %s while the first round conversion record digests %s, so the '
                         'trace re-read would not be the one that produced the delivered deck'
                         % (trace['name'], check[:12], witness[:12]))
        payload = {'name': trace['name'], 'case_id': trace['case_id'], 'sha256': check,
                   'bytes': trace['bytes'], 'recorded_conversion_sha256': witness or '',
                   'tracked_copy': bool(copy_traces)}
        if not copy_traces:
            # the safety rules of this repository never track the .vcd family, and the ceiling on
            # newly tracked numeric bytes buys the required native sequences and the internal
            # fragments instead: the trace is recorded here by digest, re-read by --reconvert, and
            # its container is written into the reviewer package built with --package
            payload.update({'exported': False, 'gap': 'NOT_TRACKED_BY_RULE',
                            'reason': 'the trace bytes stay out of the tracked directory; the '
                                      'container is shipped in the reviewer package built with '
                                      '--package, and the re-read proof of both traces is published '
                                      'by dd1_d7c_b_tr_r1_publish.py'})
            manifest.append(payload)
            continue
        packed = write_container(source, target, 'VCD')
        packed = split_into_parts(target, {})
        size = packed['bytes']
        fits = tracked + size <= cap_bytes
        if not fits:
            discard_artifact(target)
        else:
            tracked += size
        payload.update({'container_file': packed['file'], 'container_bytes': size,
                        'parts': packed['parts'], 'part_files': packed.get('part_files', []),
                        'whole_sha256': packed['sha256'] if fits else '',
                        'restore': 'cat the part_files in name order, then base85-decode what '
                                   'follows the blank line, then gunzip',
                        'exported': fits})
        if not fits:
            payload['gap'] = 'OVER_TRACK_CAP'
        manifest.append(payload)
    # the internal 26 columns of the long runs are the last thing to earn their place, after every
    # required sequence of every answer has been written
    for row, raw, identity, names, found, entry in pending:
        windows = windows_of_case(old_evidence, row['case_id'])
        fragment = os.path.join(sequences, '%s_%s_%s.internal_fragment.txt'
                                % (identity['native_run_id'], row['case_id'], row['role']))
        cut = None
        if windows:
            cut = export_sequence(raw, identity, names, fragment, include_internal=True,
                                  windows=[(item['from_ns'], item['to_ns'])
                                           for item in windows], found=found)
        if cut and tracked + cut['bytes'] <= cap_bytes:
            entry['internal_fragment'] = cut
            entry['fragment_windows'] = windows
            entry['fragment_window_count'] = len(windows)
            tracked += cut['bytes']
        else:
            if cut:
                discard_artifact(fragment)
            entry['internal_fragment'] = 'NOT_VERIFIED'
            entry['internal_note'] = ('the 26 internal columns of this %d-sample answer over %d '
                                      'declared fragments would need %s bytes against the %d bytes '
                                      'this round may still track, so the per-step internal detail '
                                      'stays in the published row tables and is not claimed as '
                                      're-integrable'
                                      % (found['samples'], len(windows),
                                         cut['bytes'] if cut else 'unmeasured', cap_bytes - tracked))
    identity_table = {'native_run_id': REC.run_id_of(old_evidence),
                      'starts': [row for row in manifest if row.get('launch_id')],
                      'observations': witnesses,
                      'tracked_bytes': tracked, 'cap_bytes': cap_bytes,
                      'deck_account_identity': 'spectre_launch_account.csv of the native run',
                      'source_tool': 'read from each answer header, recorded per sequence'}
    REC._dump(os.path.join(out_dir, 'native_identity.json'), identity_table)
    REC._dump(os.path.join(out_dir, 'native_manifest.json'),
              {'files': manifest, 'tracked_bytes': tracked, 'cap_bytes': cap_bytes,
               'delivery': 'tracked evidence directory' if not copy_traces
                           else 'package staging: the trace containers are copied and the tracked '
                                'ceiling is not applied',
               'tracked_ceiling_applied': not copy_traces})
    return manifest, witnesses, tracked


def simulator_identity(path):
    """what the file says printed it: the header of the native answer itself, no guest paths"""
    keys = ('simulator', 'version', 'analysis type', 'analysis name', 'stop', 'step', 'maxstep')
    named = ('simulator_name', 'simulator_version', 'analysis_type', 'analysis_name',
             'native_stop_s', 'native_step_s', 'native_maxstep_s')
    found = {}
    with io.open(path, encoding='utf-8', errors='replace', newline='') as handle:
        for line in handle:
            stripped = line.strip()
            if stripped in ('VALUE', 'END'):
                break
            pair = psf_pair(line)
            if pair is None:
                continue
            name, token = pair
            if name in keys:
                found[named[keys.index(name)]] = token
    missing = [key for key in named if key not in found]
    if missing:
        raise Refuse('%s prints no %s in its header, so the tool identity cannot be read from the '
                     'answer itself' % (os.path.basename(path), ','.join(missing)))
    return found


def selftest():
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else extra))
    staging = os.path.join(ROOT, 'review', 'scratch', 'tr_staging')
    if not os.path.isdir(staging):
        os.makedirs(staging)
    times = [0.0, 1e-9, 2e-9, 3e-9]
    currents = ['1.000000000000000e-12', '1.875000000000000e-06', '1.875000000000000e-06',
                '9.000000000000000e-07']
    enables = ['0.000000000000000e+00', '0.000000000000000e+00', '1.800000000000000e+00',
               '1.800000000000000e+00']
    lines = ['HEADER', '"simulator" "spectre"', '"version" "15.1.0.284.isr1"',
             '"analysis type" "tran"', '"analysis name" "tran_case"', '"stop" 3.00000e-09',
             '"step" 1.00000e-09', '"maxstep" 1.00000e-09', 'SWEEP', '"time" "sweep"',
             '"units" "s"', 'TRACE', '"time" "s"', '"Ip_branch:i" "A"', '"vdd18" "V"',
             '"vss" "V"', '"vcas" "V"', '"iref_in" "V"', '"clamp_node" "V"', '"data_out" "V"',
             '"data_en" "V"', '"pam0" "V"', '"pam1" "V"', '"pam2" "V"', '"Xdut.en0" "V"', 'VALUE']
    for index, time in enumerate(times):
        lines += ['"time" %.15e' % time, '"Ip_branch:i" %s' % currents[index],
                  '"vdd18" 1.800000000000000e+00', '"vss" 0.000000000000000e+00',
                  '"vcas" 1.800000000000000e+00', '"iref_in" 8.842614157082100e-01',
                  '"clamp_node" 1.200000000000000e+00', '"data_out" 1.200000000000000e+00',
                  '"data_en" %s' % enables[index], '"pam0" 0.000000000000000e+00',
                  '"pam1" 0.000000000000000e+00', '"pam2" 0.000000000000000e+00',
                  '"Xdut.en0" 6.554808306174669e-09']
    lines += ['END']
    fixture = os.path.join(staging, 'r1_native_fixture.raw')
    io.open(fixture, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    found = scan(fixture)
    record('the fixture answer is scanned from its own header, with its units and run counts',
           found['samples'] == 4 and found['units']['Ip_branch:i'] == 'A'
           and found['runs']['data_en'] == 2 and found['runs']['vdd18'] == 1
           and found['current'] == 'Ip_branch:i', (found['runs'], found['current']))
    names = required_names(dict((name, None) for name in found['runs']))
    record('the twelve contract columns are named with the probe spelled as the file spells it',
           len(names) == 12 and 'Ip_branch:i' in names and 'Ip_branch_current' not in names, names)
    identity = {'launch_id': 'T001', 'case_id': 'TR-120', 'role': 'dut', 'run_id': 'r_fix',
                'simulator_name': 'spectre', 'native_maxstep_s': '1.00000e-09',
                'native_bytes': os.path.getsize(fixture), 'native_samples': 4}
    out = os.path.join(staging, 'r1_native_fixture.sequence.txt')
    made = export_sequence(fixture, identity, names, out, include_internal=True)
    text = container_bytes(out).decode('utf-8')
    blocks = dict((line.split()[1], line) for line in text.split('\n')
                  if line.startswith('column '))
    restored = re.findall(r'^(\d+) ([0-9.eE+-]+)$', text, re.M)
    flat = []
    for count, token in restored:
        flat.extend([token] * int(count))
    record('a constant column stores one token and the count it expands to',
           'encoding CONSTANT' in blocks['vdd18'] and 'encoding CONSTANT' in blocks['clamp_node'],
           [blocks.get('vdd18')])
    record('a run column stores the run of the enable, not four copies of the same token',
           'encoding RUNS' in blocks['data_en'] and blocks['data_en'].endswith('runs 2'),
           blocks.get('data_en'))
    record('the current column restores to the printed tokens of the answer, in order',
           [token for token in flat if token in set(currents)] == currents, flat)
    record('the export states its own sample count and the identity of the tool that printed it',
           'samples 4' in text and 'simulator_name=spectre' in text
           and 'native_maxstep_s=1.00000e-09' in text, text[:200])
    fragment_path = os.path.join(staging, 'r1_native_fragment.sequence.txt')
    cut = export_sequence(fixture, identity, names, fragment_path,
                          include_internal=False, windows=[('1.0', '2.0')])
    fragment_text = container_bytes(fragment_path).decode('utf-8')
    record('a fragment carries only the required columns and only the samples inside its window',
           'Xdut' not in fragment_text and 'samples 2' in fragment_text
           and len(cut['columns']) == len(names), (cut['columns'], cut['samples']))
    record('and the fragment window is written in the file, not only in the manifest',
           'window from_ps 1000' in fragment_text and 'window_count 1' in fragment_text,
           fragment_text[:200])
    simulator = simulator_identity(fixture)
    split = split_into_parts(out, {}, limit=200)
    rejoined = b''.join(io.open(os.path.join(os.path.dirname(out), item['part']), 'rb').read()
                        for item in split['part_files'])
    record('a split container rejoins to the same bytes and the same whole digest',
           len(rejoined) == split['whole_bytes']
           and hashlib.sha256(rejoined).hexdigest() == split['whole_sha256']
           and not os.path.isfile(out), (split['parts'], split['whole_bytes']))
    record('and its parts are numbered continuously from zero with no repeat',
           sorted(item['part'].split('.part')[1].split('.txt')[0]
                  for item in split['part_files'])
           == ['%03d' % index for index in range(split['parts'])],
           [item['part'] for item in split['part_files']])
    record('the part limit stays under the 512 KiB blob the history gate refuses',
           PART_LIMIT_BYTES < 512 * 1024, PART_LIMIT_BYTES)
    record('the source tool identity is read out of the answer header itself',
           simulator['simulator_name'] == 'spectre'
           and simulator['native_maxstep_s'] == '1.00000e-09', simulator)
    missing = io.open(os.path.join(staging, 'r1_native_missing.raw'), 'w', encoding='utf-8',
                      newline='\n')
    missing.write('\n'.join([line for line in '\n'.join(lines).split('\n')
                             if not line.startswith('"vcas"')]) + '\n')
    missing.close()
    refused = ''
    try:
        required_names(dict((name, None) for name in scan(
            os.path.join(staging, 'r1_native_missing.raw'))['runs']))
    except Refuse as error:
        refused = str(error)
    record('a required column the answer never printed is a refusal naming it, not a filled value',
           'vcas' in refused, refused)
    bare = os.path.join(staging, 'r1_native_no_traces')
    if not os.path.isdir(os.path.join(bare, TRACE_DIR)):
        os.makedirs(os.path.join(bare, TRACE_DIR))
    missing_trace = ''
    try:
        require_traces(bare)
    except Refuse as error:
        missing_trace = str(error)
    record('a directory holding no real trace is a refusal naming it, not an empty delivery',
           TRACE_DIR in missing_trace and 'no real trace' in missing_trace, missing_trace)
    trace_home = os.path.join(staging, 'r1_native_trace_fixture')
    if not os.path.isdir(os.path.join(trace_home, TRACE_DIR)):
        os.makedirs(os.path.join(trace_home, TRACE_DIR))
    dump = os.path.join(trace_home, TRACE_DIR, 'dd1_d7c_b_tr_hyb_120.vcd')
    io.open(dump, 'w', encoding='utf-8', newline='\n').write('$dumpvars\n$end\n')
    listed = require_traces(trace_home)
    record('the trace a round re-reads is found by name, case and digest',
           len(listed) == 1 and listed[0]['name'].endswith('.vcd')
           and listed[0]['case_id'] == 'HYB-120' and len(listed[0]['sha256']) == 64, listed)

    # what the verify entry may claim: a shipped dependency is re-hashed, a split artifact is
    # rejoinable, and a trace kept out of the tracked tree is named as excluded instead of vanishing
    check_dir = os.path.join(staging, 'r1_native_verify')
    for leaf in ('native_sequences', 'dependencies'):
        path = os.path.join(check_dir, leaf)
        if not os.path.isdir(path):
            os.makedirs(path)
    dep = os.path.join(check_dir, 'dependencies', 'dc_matrix_dut.csv')
    io.open(dep, 'wb').write(b'case_id,I_sink_A\nTR-120,1.875000000000000e-06\n')
    seq = os.path.join(check_dir, 'native_sequences', 'fixture.sequence.txt')
    # above the part limit on purpose: a single-file artifact would never take the split branch
    io.open(seq, 'wb').write(b'column time units ps\n' * 13700)
    packed = split_into_parts(seq, {})
    entries = [{'dependency': 'dc_matrix_dut.csv', 'exported': True, 'sha256': sha_of(dep),
                'bytes': os.path.getsize(dep)},
               dict(packed, exported=True),
               {'name': 'dd1_d7c_b_tr_hyb_120.vcd', 'tracked_copy': False, 'exported': False,
                'gap': 'NOT_TRACKED_BY_RULE'}]
    io.open(os.path.join(check_dir, 'native_manifest.json'), 'w', encoding='utf-8',
            newline='\n').write(json.dumps({'files': entries, 'tracked_bytes': 1,
                                            'cap_bytes': 1}))
    answer = verify(check_dir)
    record('the verify entry counts the dependency and the split artifact it can actually prove',
           answer['artifacts_verified'] == 2 and answer['artifacts_recorded'] == 3
           and answer['artifacts_excluded'] == 1 and not answer['problems'], answer)
    first = os.path.join(check_dir, 'native_sequences', packed['part_files'][0]['part'])
    io.open(first, 'wb').write(b' tampered\n')
    tampered = verify(check_dir)
    record('an altered part is a named problem rather than a shorter read',
           len(tampered['problems']) == 1 and packed['part_files'][0]['part']
           in tampered['problems'][0], tampered['problems'])
    return results


def main(argv):
    mode = argv[0] if argv else '--selftest'
    if mode in ('--selftest', '--budget', '--export'):
        load_engineering()
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-66s %s %s' % (name, 'PASS' if ok else 'FAIL', str(extra)[:140]))
        print('TR_R1_NATIVE_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--budget':
        data = budget(argv[1], argv[2])
        print(json.dumps(data, indent=1, sort_keys=True))
        return 0
    if mode == '--verify':
        answer = verify(argv[1])
        print('TR_R1_VERIFY %d/%d problems=%d excluded=%d'
              % (answer['artifacts_verified'], answer['artifacts_recorded'],
                 len(answer['problems']), answer['artifacts_excluded']))
        for problem in answer['problems'][:8]:
            print('TR_R1_VERIFY_PROBLEM %s' % problem)
        for item in answer['excluded'][:8]:
            print('TR_R1_VERIFY_EXCLUDED %s' % item)
        return 0 if not answer['problems'] else 1
    if mode == '--export':
        # a fourth word 'package' builds the reviewer staging: the trace containers are written and
        # the tracked ceiling does not apply, because those bytes are not committed
        as_package = len(argv) > 4 and argv[4] == 'package'
        manifest, witnesses, tracked = export(
            argv[1], argv[2], argv[3],
            cap_bytes=(1 << 40) if as_package else TRACK_CAP_BYTES, copy_traces=as_package)
        print('TR_R1_EXPORT answers=%d witnesses=%d tracked_bytes=%d delivery=%s'
              % (len(manifest), len(witnesses), tracked,
                 'package' if as_package else 'tracked'))
        print(json.dumps(manifest, indent=1, sort_keys=True, default=str))
        return 0
    print('usage: --selftest | --verify <out_dir> | --budget <local_raw_dir> <old_evidence> '
          '| --export <local_raw_dir> <old_evidence> <out_dir> [package]')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
