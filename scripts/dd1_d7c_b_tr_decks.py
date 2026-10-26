#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-7C-B-TR run-copy decks.

The seven prepared cases keep their frozen text: a run copy is that text plus a block of comment
lines carrying this round's identity, and removing that block must give the base blob back
byte for byte. The two hybrid cases are generated from the frozen TR-120 body by substituting the
four PWL waves and the tran line only, and every other statement line is compared with the frozen
deck, so an accidental physical change cannot hide inside a new file.
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import dd1_d7c_b_tr_contract as TRC
from dd1_d7c_b_tr_contract import (BASE_SHA, CASE_ORDER, CONTRACT_PATH, DECK_DIR, PREP_DECK_DIR,
                                   MAXSTEP_NS, SHIFT_NS, EDGE_NS, LOGIC_HIGH_V, LOGIC_LOW_V,
                                   SOURCE, TASK_ID)

IDENT_PREFIX = '// TR-IDENTITY:'
HYB_TEMPLATE_CASE = 'TR-LONG'
HYB_FIRST_LINE = ('// %s.scs -- DATA-7C-B-TR run copy generated from the accepted RTL four-state '
                  'VCD. THIS CASE RUNS, accounted against the approved limit.')
PWL_LINE_RE = re.compile(r'^(?P<head>V(?P<inst>\w+)\s*\(\s*(?P<node>\w+)\s+0\)\s*vsource\s+'
                         r'type=pwl\s+wave=\[)(?P<wave>.*)(?P<tail>\])$')
SOURCE_LINE_RE = re.compile(r'^V(?P<inst>\w+)\s*\(\s*(?P<node>\w+)\s+0\)\s*vsource\s+(?P<rest>.*)$')
HYB_SIGNALS = ('data_en', 'pam0', 'pam1', 'pam2')
HYB_REQUIRED_INPUTS = ('vcd_sha256', 'rtl_blob_sha256', 'tick_ps', 'frame_count', 'stop_ns',
                       'waves')


class Refuse(Exception):
    pass


def repo(path):
    return os.path.join(ROOT, path.replace('/', os.sep))


def sha_bytes(data):
    return TRC.sha_bytes(data)


def sha_file(path):
    return TRC.sha_file(path)


def body(text):
    """statement lines only: comments are excluded, so a comment rewrite cannot mask a real one"""
    return [line for line in text.split('\n') if not line.startswith('//')]


def strip_identity(text):
    return '\n'.join(line for line in text.split('\n') if not line.startswith(IDENT_PREFIX))


def blob_text(relpath, rev=BASE_SHA):
    text = TRC.blob(rev, relpath).decode('utf-8')
    return text if text.endswith('\n') else text + '\n'


def identity_lines(case_id, role, facts):
    out = []
    add = lambda key, value: out.append('%s %s=%s' % (IDENT_PREFIX, key, value))
    add('task', TASK_ID)
    add('base_sha', BASE_SHA)
    add('branch', TRC.BRANCH)
    add('case', case_id)
    add('role', role)
    add('contract', CONTRACT_PATH)
    add('contract_sha256', sha_bytes(TRC.contract_text().encode('utf-8')))
    add('authorisation', 'USER_APPROVED_SPECTRE_LIMIT_%d_RTL_LIMIT_%d'
        % (TRC.SPECTRE_LIMIT, TRC.RTL_LIMIT))
    add('approval', '%s_YES' % TRC.APPROVAL_DATE)
    for key in sorted(facts):
        if key != 'masters':
            add(key, facts[key])
    for master in facts.get('masters', []):
        add('master', '%s=%s' % (master['name'], master['blob_sha256_at_base']))
    add('geometry_body_and_reference_unchanged', 'YES')
    add('pdk_library_and_schematic_untouched', 'YES')
    add('this_copy_runs', 'YES: the approved DATA-7C-B-TR accounts this case against the limit of '
                          '%d processes, so an inherited TEXT ONLY banner in the frozen first line '
                          'describes the preparation round only' % TRC.SPECTRE_LIMIT)
    return out


def master_facts():
    return TRC.contract()['deck_rules']['masters']


def _volts(value):
    return '%.3f' % value


def time_token(t_ps):
    return '%dn' % (t_ps // 1000) if t_ps % 1000 == 0 else '%.3fn' % (t_ps / 1000.0)


def format_wave(points):
    """PWL points given in ps become ns text at their own instant, never rounded to a coarser grid"""
    return ' '.join('%s %s' % (time_token(t_ps), _volts(value)) for t_ps, value in points)


def apply_waves(text, waves):
    out, seen = [], []
    for line in text.split('\n'):
        found = PWL_LINE_RE.match(line)
        if found and found.group('node') in waves:
            out.append('%s%s%s' % (found.group('head'), format_wave(waves[found.group('node')]),
                                   found.group('tail')))
            seen.append(found.group('node'))
        else:
            out.append(line)
    missing = [node for node in waves if node not in seen]
    if missing:
        raise Refuse('the template deck drives no pwl source for %s' % ','.join(missing))
    return '\n'.join(out)


def apply_tran(text, stop_ns, maxstep_ns):
    lines, hits = [], 0
    for line in text.split('\n'):
        if line.startswith('tran_case tran '):
            line = 'tran_case tran stop=%.3fn maxstep=%.3fn' % (stop_ns, maxstep_ns)
            hits += 1
        lines.append(line)
    if hits != 1:
        raise Refuse('the deck must declare exactly one tran line, found %d' % hits)
    return '\n'.join(lines)


def preflight(text, case_id):
    """the meter preflight: same supplies, same PWL, same span and maxstep, no DUT"""
    internal = set()
    for group in ('en', 'enb', 'vbias_ch', 'node_m'):
        internal.update(TRC.contract()['required_signals']['internal_nodes'][group])
    lines, replaced, dropped = [], 0, 0
    for line in text.split('\n'):
        if line.startswith(IDENT_PREFIX + ' role=dut'):
            lines.append(IDENT_PREFIX + ' role=preflight')
            lines.append(IDENT_PREFIX + ' preflight_derivation=the same supplies, the same PWL '
                         'inputs, the same span and the same maxstep; the DUT is replaced by the '
                         'ideal meter loads and its hierarchy saves are dropped because no DUT '
                         'exists here')
            lines.append(IDENT_PREFIX + ' preflight_may_not_be_read_as='
                         'a shut-off or ladder result, an ideal resistive preflight does not switch '
                         'off with DATA_EN')
            continue
        if re.match(r'^Xdut\s*\(', line):
            lines.append('Rload_meter (data_out vss) resistor r=80e3')
            lines.append('Rref_meter (iref_in vss) resistor r=50e3')
            replaced += 1
            continue
        if line.startswith('save ') and any(name in internal for name in line.split()[1:]):
            kept = [name for name in line.split()[1:] if name not in internal]
            dropped += len(line.split()[1:]) - len(kept)
            if kept:
                lines.append('save ' + ' '.join(kept))
            continue
        lines.append(line)
    if replaced != 1:
        raise Refuse('%s: the preflight found %d Xdut lines, exactly one is expected'
                     % (case_id, replaced))
    if dropped == 0:
        raise Refuse('%s: the preflight dropped no DUT hierarchy save, so the run copy never named '
                     'one and the internal observation would silently be missing' % case_id)
    return '\n'.join(lines), {'dut_line_replaced': replaced, 'hierarchical_saves_dropped': dropped,
                              'load_ohms': TRC.PREFLIGHT_LOAD_OHMS,
                              'reference_ohms': TRC.PREFLIGHT_REF_OHMS}


def deck_text(case_id, hyb=None):
    """the DUT run copy of one case, exactly as it is written to the repository"""
    facts = {'tick_ns': '%g' % TRC.TICK_NS[case_id], 'maxstep_ns': '%g' % TRC.MAXSTEP_NS[case_id],
             'masters': master_facts()}
    if SOURCE[case_id] == 'frozen_PREP':
        frozen = blob_text('%s/%s.scs' % (PREP_DECK_DIR, case_id))
        facts['source_deck'] = '%s/%s.scs' % (PREP_DECK_DIR, case_id)
        facts['source_deck_sha256'] = sha_bytes(frozen.encode('utf-8'))
        facts['derivation'] = ('the frozen deck text plus this identity block and nothing else')
        lines = frozen.split('\n')
        text = '\n'.join([lines[0]] + identity_lines(case_id, 'dut', facts) + lines[1:])
        return text, facts, frozen
    if hyb is None:
        raise Refuse('%s needs the converted waves and the span before its deck is written'
                     % case_id)
    for key in HYB_REQUIRED_INPUTS:
        if key not in hyb:
            raise Refuse('%s: the hybrid input carries no %s' % (case_id, key))
    template = blob_text('%s/%s.scs' % (PREP_DECK_DIR, HYB_TEMPLATE_CASE))
    text = apply_tran(apply_waves(template, hyb['waves']), hyb['stop_ns'], MAXSTEP_NS[case_id])
    lines = text.split('\n')
    facts['template_deck'] = '%s/%s.scs' % (PREP_DECK_DIR, HYB_TEMPLATE_CASE)
    facts['template_deck_sha256'] = sha_bytes(template.encode('utf-8'))
    facts['template_first_line_replaced'] = 'YES'
    facts['vcd_sha256'] = hyb['vcd_sha256']
    facts['rtl_blob_sha256'] = hyb['rtl_blob_sha256']
    facts['tick_ps'] = hyb['tick_ps']
    facts['frame_count'] = hyb['frame_count']
    facts['stop_ns'] = '%g' % hyb['stop_ns']
    facts['substituted_lines'] = 'the four logic pwl waves, the tran line and the first comment'
    for node in HYB_SIGNALS:
        pts = hyb['waves'][node]
        if not pts:
            raise Refuse('%s: the converted wave for %s is empty' % (case_id, node))
        facts['wave_%s_points' % node] = len(pts)
        facts['wave_%s_span_ns' % node] = '%.3f..%.3f' % (pts[0][0] / 1000.0, pts[-1][0] / 1000.0)
        facts['wave_%s_initial_V' % node] = '%.3f' % pts[0][1]
    facts['derivation'] = ('generated from the accepted RTL four-state VCD; every statement line '
                           'other than those is byte-identical to the template body')
    new_first = (HYB_FIRST_LINE % case_id)
    text = '\n'.join([new_first] + identity_lines(case_id, 'dut', facts) + lines[1:])
    return text, facts, template


def write_all(hyb=None):
    hyb = hyb or {}
    if not os.path.isdir(repo(DECK_DIR)):
        os.makedirs(repo(DECK_DIR))
    account = {'task_id': TASK_ID, 'base_sha': BASE_SHA,
               'rule': ('a prepared run copy is the frozen deck text plus TR-IDENTITY comment '
                        'lines; a hybrid run copy substitutes only the four logic waves, the tran '
                        'stop and the first comment line of the frozen TR-120 body'),
               'decks': [], 'preflights': [], 'not_written': []}
    for case_id in CASE_ORDER:
        given = hyb.get(case_id)
        if SOURCE[case_id] != 'frozen_PREP' and given is None:
            account['not_written'].append({'case_id': case_id, 'state': 'AWAITING_ACCEPTED_RTL_VCD'})
            continue
        text, facts, frozen = deck_text(case_id, given)
        path = repo('%s/%s.scs' % (DECK_DIR, case_id))
        with io.open(path, 'wb') as handle:
            handle.write(text.encode('utf-8'))
        row = {'case_id': case_id, 'role': 'dut', 'path': '%s/%s.scs' % (DECK_DIR, case_id),
               'sha256': sha_bytes(text.encode('utf-8')),
               'identity_lines_added': len(identity_lines(case_id, 'dut', facts)),
               'tick_ns': '%g' % TRC.TICK_NS[case_id], 'maxstep_ns': '%g' % MAXSTEP_NS[case_id],
               'source_sha256': sha_bytes(frozen.encode('utf-8'))}
        if SOURCE[case_id] == 'frozen_PREP':
            row['body_equal_after_removing_identity_block'] = (strip_identity(text) == frozen)
            row['statement_lines_equal_to_source'] = body(text) == body(frozen)
        else:
            row['template_case'] = HYB_TEMPLATE_CASE
            row['vcd_sha256'] = given['vcd_sha256']
            template_body, this_body = body(frozen), body(text)
            row['statement_line_count_equal'] = len(template_body) == len(this_body)
            row['statement_lines_differing'] = [[index, template_body[index], this_body[index]]
                                                for index in range(min(len(template_body),
                                                                       len(this_body)))
                                                if template_body[index] != this_body[index]]
        account['decks'].append(row)
        pre, meta = preflight(text, case_id)
        pre_path = repo('%s/%s.pre.scs' % (DECK_DIR, case_id))
        with io.open(pre_path, 'wb') as handle:
            handle.write(pre.encode('utf-8'))
        merged = dict(row)
        merged.update({'role': 'preflight', 'path': '%s/%s.pre.scs' % (DECK_DIR, case_id),
                       'sha256': sha_bytes(pre.encode('utf-8')),
                       'expected_clamp_current_A': TRC.CLAMP_V / TRC.PREFLIGHT_LOAD_OHMS,
                       'expected_reference_node_V': (TRC.CLAMP_V / TRC.PREFLIGHT_LOAD_OHMS)
                       * TRC.PREFLIGHT_REF_OHMS})
        merged.update(meta)
        merged.pop('statement_lines_differing', None)
        account['preflights'].append(merged)
    with io.open(repo('%s/deck_account.json' % DECK_DIR), 'wb') as handle:
        account['masters'] = [{'name': os.path.basename(master['path']),
                               'path': master['path'],
                               'sha256_on_disk': sha_file(repo(master['path'])),
                               'blob_sha256_at_base': master['blob_sha256_at_base'],
                               'equal_to_base_blob': (sha_file(repo(master['path']))
                                                      == master['blob_sha256_at_base'])}
                              for master in TRC.contract()['deck_rules']['masters']]
        handle.write((json.dumps(account, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
                     .encode('utf-8'))
    return account


# ---- the PWL shape is verified against the delivered bytes, not against the generator ------------

def parse_waves(text):
    out = {}
    for line in text.split('\n'):
        found = PWL_LINE_RE.match(line)
        if found:
            cells = found.group('wave').split()
            if len(cells) % 2:
                raise Refuse('the %s wave has an odd token count' % found.group('node'))
            series = []
            for index in range(0, len(cells), 2):
                series.append((TRC.ns_of(cells[index]), float(cells[index + 1])))
            out[found.group('node')] = series
    return out


def driven_logics(text):
    """how each of the four logic nodes is driven in this deck: a dc level or a pwl wave"""
    out = {}
    for line in text.split('\n'):
        found = SOURCE_LINE_RE.match(line)
        if not found or found.group('node') not in HYB_SIGNALS:
            continue
        rest = found.group('rest')
        dc = re.match(r'^dc=([0-9.]+)', rest)
        if dc:
            out[found.group('node')] = ('dc', float(dc.group(1)), None)
        elif rest.startswith('type=pwl'):
            out[found.group('node')] = ('pwl', None, parse_waves(line).get(found.group('node')))
    return out


def verify_pwl(text, edges_by_node, level=LOGIC_HIGH_V, ramp_ns=EDGE_NS, shift_ns=SHIFT_NS,
               ctx=''):
    """re-read the delivered wave text and confirm every original edge, its 50 % point, the ramp
    width, the rail levels and the initial value; an overlapping or missing edge is refused"""
    problems = []
    waves = parse_waves(text)
    for node, edges in sorted(edges_by_node.items()):
        if node not in waves:
            problems.append('%s: the delivered deck drives no pwl source for %s' % (ctx, node))
            continue
        series = waves[node]
        if series[0][0] != 0.0:
            problems.append('%s: %s starts at %g ns, the wave must start at t=0 with its hold point'
                            % (ctx, node, series[0][0]))
        if abs(series[0][1] - LOGIC_LOW_V) > 1e-9:
            problems.append('%s: %s starts at %r V, the conversion always starts at the low rail'
                            % (ctx, node, series[0][1]))
        for index in range(1, len(series)):
            if series[index][0] <= series[index - 1][0]:
                problems.append('%s: %s is not strictly increasing at point %d'
                                % (ctx, node, index))
        ramps = []
        for index in range(1, len(series)):
            t0, v0 = series[index - 1]
            t1, v1 = series[index]
            if abs(v1 - v0) > 1e-9:
                ramps.append((t0, t1, v0, v1))
        # only a change of level is an edge: a trace may record a value the node already held, and
        # the converter starts from the low rail, exactly as the accepted PWL builder does
        wanted, held = [], 0
        for t, v in sorted(edges):
            if v != held:
                wanted.append(t / 1000.0 + shift_ns)
                held = v
        got = sorted((start + end) / 2.0 for start, end, _v0, _v1 in ramps)
        if len(got) != len(wanted):
            problems.append('%s: %s carries %d ramps for %d converted edges'
                            % (ctx, node, len(got), len(wanted)))
        for index in range(min(len(got), len(wanted))):
            if abs(got[index] - wanted[index]) > 1e-9:
                problems.append('%s: %s ramp %d is centred at %g ns, the shifted edge is at %g ns'
                                % (ctx, node, index, got[index], wanted[index]))
        for start, end, v0, v1 in ramps:
            if abs((end - start) - ramp_ns) > 1e-9:
                problems.append('%s: %s has a ramp of %g ns, the contract fixes the total edge '
                                'width at %g ns' % (ctx, node, end - start, ramp_ns))
            for value in (v0, v1):
                if min(abs(value - LOGIC_LOW_V), abs(value - level)) > 1e-9:
                    problems.append('%s: %s ramps through %r V, only the two logic rails are used'
                                    % (ctx, node, value))
        for _time, value in series:
            if min(abs(value - LOGIC_LOW_V), abs(value - level)) > 1e-9:
                problems.append('%s: %s holds %r V, only the two logic rails are converted'
                                % (ctx, node, value))
    return problems, waves


def check_account(account, require_all=True):
    problems = []
    for row in account['decks']:
        path = repo(row['path'])
        if not os.path.isfile(path):
            problems.append('%s is missing' % row['path'])
            continue
        text = io.open(path, encoding='utf-8', newline='').read()
        if '%s this_copy_runs=' % IDENT_PREFIX not in text:
            problems.append('%s: the run copy does not state that it runs, so an inherited TEXT '
                            'ONLY banner could be read as this round\'s status' % row['case_id'])
        if sha_bytes(text.encode('utf-8')) != row['sha256']:
            problems.append('%s is not the byte string the account digests' % row['path'])
        if row.get('body_equal_after_removing_identity_block') is False:
            problems.append('%s: removing the identity block does not return the frozen deck'
                            % row['case_id'])
        if row.get('statement_lines_equal_to_source') is False:
            problems.append('%s: a statement line changed against the frozen deck' % row['case_id'])
        stamped = re.search(r'^%s contract_sha256=([0-9a-f]{64})$' % re.escape(IDENT_PREFIX),
                            text, re.M)
        want = sha_bytes(io.open(repo(CONTRACT_PATH), 'rb').read())
        if not stamped:
            problems.append('%s: the run copy stamps no contract digest' % row['case_id'])
        elif stamped.group(1) != want:
            problems.append('%s: the run copy stamps contract digest %s but %s is %s, so the decks '
                            'were emitted before the last contract change'
                            % (row['case_id'], stamped.group(1)[:12], CONTRACT_PATH, want[:12]))
        for index, before, after in row.get('statement_lines_differing', []):
            if not (after.startswith('tran_case') or PWL_LINE_RE.match(after)):
                problems.append('%s: statement line %d is not a wave or tran rewrite: %r'
                                % (row['case_id'], index + 1, before[:60]))
        analysis = re.findall(r'^tran_case tran stop=(\S+) maxstep=(\S+)$', text, re.M)
        if len(analysis) != 1:
            problems.append('%s declares %d tran lines' % (row['case_id'], len(analysis)))
        elif abs(float(analysis[0][1][:-1]) - float(row['maxstep_ns'])) > 1e-12:
            problems.append('%s: the deck maxstep is %s, the plan says %s'
                            % (row['case_id'], analysis[0][1], row['maxstep_ns']))
        saves = ' '.join(re.findall(r'^save\s+(.*)$', text, re.M)).split()
        need = (['vss', 'data_out', 'clamp_node', 'iref_in', 'vcas', 'vdd18', 'data_en', 'pam0',
                 'pam1', 'pam2', 'Ip_branch']
                + [name for group in ('en', 'enb', 'vbias_ch', 'node_m')
                   for name in TRC.contract()['required_signals']['internal_nodes'][group]])
        missing = [name for name in need if name not in saves]
        if missing:
            problems.append('%s: the run copy saves no %s' % (row['case_id'], ','.join(missing[:5])))
        waves = parse_waves(text)
        driven = driven_logics(text)
        absent = [node for node in HYB_SIGNALS if node not in driven]
        if absent:
            problems.append('%s: the run copy drives no source for %s'
                            % (row['case_id'], ','.join(absent)))
        if SOURCE[row['case_id']] != 'frozen_PREP' and sorted(waves) != sorted(HYB_SIGNALS):
            problems.append('%s: a hybrid copy must drive all four logic signals from the VCD, it '
                            'drives pwl waves for %s' % (row['case_id'],
                                                          ','.join(sorted(waves)) or 'nothing'))
        for node, (form, dc_value, series) in driven.items():
            values = [dc_value] if form == 'dc' else [pair[1] for pair in series]
            for value in values:
                if min(abs(value - LOGIC_LOW_V), abs(value - LOGIC_HIGH_V)) > 1e-9:
                    problems.append('%s: the %s source is driven to %r V, outside the two logic '
                                    'rails' % (row['case_id'], node, value))
            if node == 'data_en':
                rises, _falls = TRC.half_crossings(series or [])
                if not rises:
                    problems.append('%s: the enable is never pulsed, so no emission window can be '
                                    'measured from it' % row['case_id'])
    for row in account['preflights']:
        text = io.open(repo(row['path']), encoding='utf-8', newline='').read()
        if sha_bytes(text.encode('utf-8')) != row['sha256']:
            problems.append('%s is not the byte string the account digests' % row['path'])
        stamped = re.search(r'^%s contract_sha256=([0-9a-f]{64})$' % re.escape(IDENT_PREFIX),
                            text, re.M)
        want = sha_bytes(io.open(repo(CONTRACT_PATH), 'rb').read())
        if not stamped or stamped.group(1) != want:
            problems.append('%s: the preflight copy does not stamp the committed contract digest'
                            % row['case_id'])
        if 'Xdut (' in text:
            problems.append('%s: the preflight still instantiates the DUT' % row['case_id'])
        if '%s role=preflight' % IDENT_PREFIX not in text or '%s role=dut' % IDENT_PREFIX in text:
            problems.append('%s: the preflight copy is still stamped as a DUT run' % row['case_id'])
        for load in ('Rload_meter (data_out vss) resistor r=80e3',
                     'Rref_meter (iref_in vss) resistor r=50e3'):
            if load not in text:
                problems.append('%s: the preflight is missing %s' % (row['case_id'], load))
        if re.search(r'^save\s+.*Xdut\.', text, re.M):
            problems.append('%s: the preflight saves a DUT hierarchy node that is not there'
                            % row['case_id'])
        dut = io.open(repo('%s/%s.scs' % (DECK_DIR, row['case_id'])),
                      encoding='utf-8', newline='').read()
        pre_waves, dut_waves = parse_waves(text), parse_waves(dut)
        if sorted(pre_waves) != sorted(dut_waves):
            problems.append('%s: the preflight drives a different signal set than the DUT run'
                            % row['case_id'])
        for node in pre_waves:
            if pre_waves[node] != dut_waves[node]:
                problems.append('%s: the %s wave differs between the two roles of %s'
                                % (row['case_id'], node, row['case_id']))
        if re.findall(r'^tran_case tran .*$', text, re.M) != \
                re.findall(r'^tran_case tran .*$', dut, re.M):
            problems.append('%s: the preflight does not keep the DUT analysis line' % row['case_id'])
        for supply in ('Vdd18 (vdd18 0) vsource dc=1.8', 'Vss (vss 0) vsource dc=0',
                       'Vcas (vcas 0) vsource dc=1.8', 'Vclamp (clamp_node 0) vsource dc=1.2',
                       'Iref_in (irefbus iref_in) isource dc=15u'):
            if supply not in text or supply not in dut:
                problems.append('%s: the supply line %r is not identical in both roles'
                                % (row['case_id'], supply))
        if row.get('dut_line_replaced') != 1 or not row.get('hierarchical_saves_dropped'):
            problems.append('%s: the preflight derivation is not recorded' % row['case_id'])
    if require_all:
        names = set(row['case_id'] for row in account['decks'])
        absent = [case for case in CASE_ORDER if case not in names]
        if absent:
            problems.append('no run copy for %s' % ','.join(absent))
    return problems


def selftest():
    results = []
    record = lambda name, ok, extra='': results.append((name, bool(ok), '' if ok else extra))
    path = repo('%s/deck_account.json' % DECK_DIR)
    if not os.path.isfile(path):
        return [('the deck account exists', False, 'run --emit first')]
    account = json.loads(io.open(path, encoding='utf-8').read())
    prepared = [row for row in account['decks'] if row['case_id'] in SOURCE
                and SOURCE[row['case_id']] == 'frozen_PREP']
    record('the seven prepared run copies are present', len(prepared) == 7, len(prepared))
    record('every prepared run copy is the frozen text plus the identity block',
           all(row['body_equal_after_removing_identity_block']
               and row['statement_lines_equal_to_source'] for row in prepared),
           [row['case_id'] for row in prepared
            if not row['body_equal_after_removing_identity_block']])
    hyb = [row for row in account['decks'] if row['case_id'].startswith('HYB')]
    if hyb:
        record('a hybrid copy rewrites only waves and the tran line',
               all(not [item for item in row['statement_lines_differing']
                        if not (item[1].startswith('tran_case') or PWL_LINE_RE.match(item[1]))]
                   for row in hyb), [row['case_id'] for row in hyb])
    else:
        record('the hybrid decks are still awaited (not yet generated, no claim made)',
               [row['case_id'] for row in account['not_written']] == ['HYB-120', 'HYB-200'],
               account['not_written'])
    record('every run copy states that this round runs it',
           all('%s this_copy_runs=' % IDENT_PREFIX in io.open(repo(row['path']),
                                                              encoding='utf-8').read()
               for row in account['decks']),
           [row['case_id'] for row in account['decks']
            if '%s this_copy_runs=' % IDENT_PREFIX not in io.open(repo(row['path']),
                                                                  encoding='utf-8').read()])
    record('both roles exist for every written case',
           len(account['preflights']) == len(account['decks']),
           (len(account['decks']), len(account['preflights'])))
    record('the account checks clean against the bytes on disk',
           not check_account(account, require_all=bool(hyb)),
           check_account(account, require_all=bool(hyb))[:2])
    edges = {'data_en': [(1500000, 1), (2500000, 0)], 'pam0': [(1500000, 1)]}
    shift_ps = int(SHIFT_NS * 1000)

    def synth(series):
        """the same shape build_pwl produces: a hold point, a ramp point, the whole wave shifted"""
        pts, cur = [(0, 0.0)], 0
        for t, v in series:
            pts.append((t - int(EDGE_NS * 500) + shift_ps, cur * LOGIC_HIGH_V))
            pts.append((t + int(EDGE_NS * 500) + shift_ps, v * LOGIC_HIGH_V))
            cur = v
        pts.append((4000000 + shift_ps, cur * LOGIC_HIGH_V))
        return pts

    built = dict((node, synth(series)) for node, series in edges.items())
    text = ''.join('V%s (%s 0) vsource type=pwl wave=[%s]\n'
                   % (node, node, format_wave(built[node])) for node in ('data_en', 'pam0'))
    problems, _waves = verify_pwl(text, edges)
    record('a 2 ns ramp centred on the shifted edge passes the delivered-text check',
           not problems, problems[:1])
    ramp = '%s 0.000 %s 1.800' % (time_token(2499000), time_token(2501000))
    record('the synthetic text carries the ramp the checker is meant to read', ramp in text, text)
    record('an edge whose 50 % point is off the original instant is caught',
           bool(verify_pwl(text.replace(ramp, '%s 0.000 %s 1.800'
                                        % (time_token(2500000), time_token(2502000))), edges)[0]),
           '')
    record('a ramp wider than the frozen 2 ns is caught',
           bool(verify_pwl(text.replace(ramp, '%s 0.000 %s 1.800'
                                        % (time_token(2499000), time_token(2503000))), edges)[0]),
           '')
    record('a ramp moved off the original edge instant is caught',
           bool(verify_pwl(text.replace(ramp, '%s 0.000 %s 1.800'
                                        % (time_token(2498000), time_token(2500000))), edges)[0]),
           '')
    record('a mid-rail value stored as a level is caught',
           bool(verify_pwl(text.replace('%s 1.800' % time_token(2501000),
                                        '%s 0.900' % time_token(2501000), 1), edges)[0]), '')
    record('a signal the conversion produced but the deck does not drive is named',
           any('pam0' in text for text in verify_pwl(
               text.replace('Vpam0 (pam0 0)', 'VpamX (pamX 0)'), edges)[0]), '')
    record('a wave that starts high loses its first edge and is caught',
           bool(verify_pwl(text.replace('wave=[0n 0.000', 'wave=[0n 1.800'), edges)[0]), '')
    record('a wave that is not shifted as a whole is caught',
           bool(verify_pwl(text.replace(ramp, '%s 0.000 %s 1.800'
                                        % (time_token(1499000), time_token(2501000))), edges)[0]),
           '')
    record('a sub-nanosecond edge instant is emitted at its own precision',
           time_token(1200500) == '1200.500n', time_token(1200500))
    refused = False
    try:
        verify_pwl(text.replace(' %s' % time_token(2499000), '', 1), edges)
    except Refuse:
        refused = True
    record('a wave with an odd token count is refused rather than half read', refused, '')
    pre, meta = preflight(io.open(repo('%s/TR-LONG.scs' % DECK_DIR), encoding='utf-8').read(),
                          'TR-LONG')
    record('the preflight replaces the DUT and drops its hierarchy saves',
           meta['dut_line_replaced'] == 1 and meta['hierarchical_saves_dropped'] == 26, meta)
    refused = False
    try:
        preflight('nothing here', 'XX')
    except Refuse:
        refused = True
    record('a preflight over a deck without exactly one DUT line is refused', refused, '')
    return results


def main(argv):
    mode = argv[0] if argv else '--emit'
    if mode in ('--emit', '--write'):
        account = write_all()
        print('TR_DECKS_EMITTED %d decks %d preflights awaiting=%d'
              % (len(account['decks']), len(account['preflights']), len(account['not_written'])))
        return 0
    if mode == '--selftest':
        results = selftest()
        failures = [name for name, ok, extra in results if not ok]
        for name, ok, extra in results:
            print('%-64s %s %s' % (name, 'PASS' if ok else 'FAIL', extra))
        print('TR_DECK_SELFTEST %d/%d' % (len(results) - len(failures), len(results)))
        return 0 if not failures else 1
    if mode == '--check':
        account = json.loads(io.open(repo('%s/deck_account.json' % DECK_DIR),
                                     encoding='utf-8').read())
        problems = check_account(account)
        for text in problems:
            print('TR_DECK_PROBLEM: %s' % text)
        print('TR_DECK_CHECK %s (%d decks, %d preflights)'
              % ('PASS' if not problems else 'FAIL', len(account['decks']),
                 len(account['preflights'])))
        return 0 if not problems else 1
    print('usage: --emit | --check | --selftest')
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
