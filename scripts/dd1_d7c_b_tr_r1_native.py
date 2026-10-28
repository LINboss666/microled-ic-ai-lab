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
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7c_b_dc_run as DC
import dd1_d7c_b_tr_contract as TRC
import dd1_d7c_b_tr_measure as MEAS
import dd1_d7c_b_tr_record as REC
import dd1_d7c_b_tr_run as RUN

MAGIC = 'TR1NATIVESEQ 1'
INTERNAL = TRC.contract()['required_signals']['internal_nodes']
INTERNAL_COLUMNS = (INTERNAL['en'] + INTERNAL['enb'] + INTERNAL['vbias_ch'] + INTERNAL['node_m'])
ALWAYS = [name for name in TRC.contract()['required_signals']['always_extracted']
          if name != 'Ip_branch_current']
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


def verify(out_dir):
    """re-join every split artifact this round wrote and prove the parts rebuild it byte for byte

    The parts exist only to fit the history gate, so the property that matters is that the numbering
    is continuous without a gap or a repeat and that the concatenation matches the whole-file bytes
    and digest the manifest records. A part that is missing, duplicated or altered is a problem, not
    a smaller file to read.
    """
    manifest = json.loads(io.open(os.path.join(out_dir, 'native_manifest.json'),
                                  encoding='utf-8').read())
    directory = os.path.join(out_dir, 'native_sequences')
    dependencies = os.path.join(out_dir, 'dependencies')
    problems, checked, excluded = [], 0, []
    for entry in manifest['files']:
        if entry.get('dependency'):
            # a frozen dependency is shipped as its own bytes, so the property to prove is that the
            # copy on disk is the digest the manifest and the committed blob both claim
            name = entry['dependency']
            path = os.path.join(dependencies, name)
            if not entry.get('exported'):
                excluded.append('%s: not delivered (%s)' % (name, entry.get('gap')))
            elif not os.path.isfile(path):
                problems.append('%s is recorded as an exported dependency but is not on disk' % name)
            elif (os.path.getsize(path) != entry['bytes']
                  or sha_of(path) != entry['sha256']):
                problems.append('%s is not the digest and byte count the manifest records' % name)
            else:
                checked += 1
            continue
        # a sequence names its own container; a delivered trace keeps the container under the
        # 'container_' prefix because its own 'sha256' is the digest of the uncompressed trace
        name = entry.get('file') or entry.get('container_file')
        size = entry.get('bytes') if entry.get('file') else entry.get('container_bytes')
        digest = entry.get('sha256') if entry.get('file') else entry.get('whole_sha256')
        if entry.get('tracked_copy') is False:
            excluded.append('%s: recorded by digest only (%s)' % (entry.get('name'),
                                                                  entry.get('gap')))
            continue
        if not entry.get('part_files'):
            if entry.get('exported') and name:
                if os.path.isfile(os.path.join(directory, name)):
                    checked += 1
                else:
                    problems.append('%s is recorded as exported but is not on disk' % name)
            elif not entry.get('exported'):
                excluded.append('%s: not delivered (%s)' % (name or entry.get('name'),
                                                            entry.get('gap')))
            continue
        names = [item['part'] for item in entry['part_files']]
        numbers = sorted(int(name.split('.part')[1].split('.txt')[0]) for name in names)
        if len(set(names)) != len(names):
            problems.append('%s lists the same part twice' % name)
            continue
        if numbers != list(range(len(numbers))):
            problems.append('%s parts are numbered %s, not a continuous run from zero'
                            % (name, numbers))
            continue
        data = b''
        for item in sorted(entry['part_files'], key=lambda row: row['part']):
            path = os.path.join(directory, item['part'])
            if not os.path.isfile(path):
                problems.append('%s is named by the manifest and not on disk' % item['part'])
                break
            chunk = io.open(path, 'rb').read()
            if len(chunk) != item['bytes'] or hashlib.sha256(chunk).hexdigest() != item['sha256']:
                problems.append('%s does not match the bytes and digest recorded for it'
                                % item['part'])
                break
            data += chunk
        else:
            if len(data) != size:
                problems.append('%s rejoins to %d bytes against the recorded %s'
                                % (name, len(data), size))
            elif hashlib.sha256(data).hexdigest() != digest:
                problems.append('%s rejoins to another digest than the manifest records' % name)
            else:
                checked += 1
    return {'artifacts_verified': checked, 'artifacts_recorded': len(manifest['files']),
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
