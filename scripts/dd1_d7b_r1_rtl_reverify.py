#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DATA-7B-R1: re-verify the delivered trace edges on the frozen four-state RTL

The reviewer's edge defects were about which edge a window's fall time was read from, so the pulse
edges the bundle depends on have to be shown to come out of the frozen RTL and the frozen testbench
again, on this machine, now. TASK_DATA7B_R1 section 7.3 allows up to 17 new RTL simulations and says
what may and may not be compared: the new VCD's date and digest stay their own identity, separate
from the native run's source identity, and only the reproducible edges and the PWL they imply have to
agree. The testbench is not edited to make them agree.

Nothing here starts Spectre or touches a guest: iverilog and vvp run locally, and the parsing goes
through the frozen scripts/dd1_d7b_trace.py, so a defect in the re-verification would also be a
defect in the document the evidence was built from.

usage: python scripts/dd1_d7b_r1_rtl_reverify.py --trace-dir <accepted traceout> --out <scratch>
       [--cases tests/dd1_d7b/cases.csv] [--golden tests/dd1_d7b/golden_windows.csv]
"""
from __future__ import print_function

import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7b_trace as TR                                    # noqa: E402  (the frozen parser)

RTL = os.path.join(PROJ, 'rtl', 'dd1_d7a_gray_ctrl.sv')
TB = os.path.join(PROJ, 'tests', 'dd1_d7b', 'tb_dd1_d7b_pwm.sv')
TOOL_ROOTS = (r'D:\ic617_d7a_tools\oss-cad-suite', r'C:\ic617_d7a_tools\oss-cad-suite')
MAX_RTL_SIMULATIONS = 17                                       # the ceiling the task book grants
COMPARED_FACTS = ('data_en_edges', 'data_en_b_edges', 'tick_rises_ps', 'tb_tick_edges',
                  'clk_period_ps', 'tick_count', 'tick_lead_ps', 'end_ps', 'blank_edges',
                  'fault_edges', 'cfg_version', 'pam_sel', 'proto_err', 'win_state',
                  'attestation_x_before_t0')
COMPARED_WINDOWS = ('segments_ps', 't0_ps', 't1_ps', 't_stop_ps', 'conducted_ps', 'full_intervals',
                    'expected_intervals', 'expected_accepted_ticks', 'accepted_ticks_in_window',
                    'expected_pulses', 'code', 'mode', 'role', 'window', 'pwl_points',
                    'pwl_sha256')


class Refused(Exception):
    """a re-verification that cannot be trusted says so and writes nothing"""


def sha256_of(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def u(text):
    if isinstance(text, bytes):
        return text.decode('utf-8', 'replace')
    return text


def tools():
    """iverilog and vvp, with the runtime library directory on PATH

    The oss-cad-suite Windows drop puts libgcc/libstdc++ next to the vvp shared library under lib/,
    not bin/, so launching vvp from bin alone fails with a missing libvvp-1.dll.
    """
    for root in TOOL_ROOTS:
        bin_dir = os.path.join(root, 'bin')
        if os.path.isfile(os.path.join(bin_dir, 'iverilog.exe')):
            env = dict(os.environ)
            env['PATH'] = os.pathsep.join([bin_dir, os.path.join(root, 'lib'),
                                           env.get('PATH', '')])
            return {'iverilog': os.path.join(bin_dir, 'iverilog.exe'),
                    'vvp': os.path.join(bin_dir, 'vvp.exe'), 'env': env, 'root': root}
    raise Refused('no oss-cad-suite iverilog under %s' % ' or '.join(TOOL_ROOTS))


def call(cmd, env, out_dir):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                         cwd=out_dir)
    text = u(p.communicate()[0] or '')
    return p.returncode, text


def version(tool, env, out_dir):
    rc, text = call([tool, '-V'], env, out_dir)
    for line in text.split('\n'):
        if 'version' in line:
            return '%s%s' % (line.strip(), ' [rc=%d]' % rc)
    return 'rc=%d %s' % (rc, text.strip()[:80] or '-')


def trace_cases(path):
    """the trace cases the delivered case table asks for, and the case rows that share each

    The ramp is a PWL parameter, not an RTL one: D7B-P30-C001 and its slow-edge sibling read the same
    four-state run with different ramps, so a trace case is re-simulated once and its ramps are
    reported rather than required to agree.
    """
    out = {}
    for r in csv.DictReader(io.open(path, encoding='utf-8')):
        tc = r['trace_case']
        if tc in ('', 'NONE'):
            continue
        out.setdefault(tc, []).append('%s ramp_ns=%s' % (r['case_id'], r['ramp_ns']))
    if len(out) > MAX_RTL_SIMULATIONS:
        raise Refused('%d trace cases exceed the %d RTL simulations the task grants'
                      % (len(out), MAX_RTL_SIMULATIONS))
    return out


def compare(old, new):
    """the reproducible fields of one accepted document against the rebuilt one"""
    bad = []
    for field in COMPARED_FACTS:
        if field not in old['facts']:
            continue
        if json.dumps(old['facts'][field], sort_keys=True) != \
                json.dumps(new['facts'].get(field), sort_keys=True):
            bad.append('facts.%s' % field)
    ow = dict((w['window'], w) for w in old['windows'])
    nw = dict((w['window'], w) for w in new['windows'])
    if sorted(ow) != sorted(nw):
        bad.append('window set %s vs %s' % (sorted(ow), sorted(nw)))
        return bad, 0
    checked = 0
    for name in sorted(ow):
        for field in COMPARED_WINDOWS:
            if field not in ow[name]:
                continue
            checked += 1
            if json.dumps(ow[name][field], sort_keys=True) != \
                    json.dumps(nw[name].get(field), sort_keys=True):
                bad.append('%s.%s' % (name, field))
    return bad, checked


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trace-dir', required=True, help='where the accepted trace_*.json live')
    ap.add_argument('--out', required=True, help='ignored scratch directory for the new bytes')
    ap.add_argument('--cases', default=os.path.join(PROJ, 'tests', 'dd1_d7b', 'cases.csv'))
    ap.add_argument('--golden', default=os.path.join(PROJ, 'tests', 'dd1_d7b', 'golden_windows.csv'))
    opts = ap.parse_args(argv)

    if not os.path.isfile(RTL) or not os.path.isfile(TB):
        raise Refused('the frozen RTL or testbench is missing')
    want = trace_cases(opts.cases)
    gold = TR.load_golden(opts.golden)
    out_dir = os.path.abspath(opts.out)
    if os.path.exists(out_dir):
        stale = [n for n in os.listdir(out_dir) if n.startswith('r1rtl_')]
        if stale:
            raise Refused('%s already holds %d r1rtl_ artefacts; re-verify into a fresh directory so '
                          'one table cannot describe two different sets of bytes'
                          % (out_dir, len(stale)))
    else:
        os.makedirs(out_dir)

    t = tools()
    exe = os.path.join(out_dir, 'r1rtl_tb.vvp')
    rc, text = call([t['iverilog'], '-g2012', '-Wall', '-o', exe, TB, RTL], t['env'], out_dir)
    if rc != 0 or not os.path.isfile(exe):
        raise Refused('the frozen RTL/testbench did not compile: %s' % text.strip()[:200])
    rtl_sha, tb_sha = sha256_of(RTL), sha256_of(TB)
    rows = []
    sims = 0
    for case in sorted(want):
        accepted_path = os.path.join(opts.trace_dir, 'trace_%s.json' % case)
        if not os.path.isfile(accepted_path):
            raise Refused('the accepted trace document %s is missing' % accepted_path)
        accepted = json.loads(u(io.open(accepted_path, encoding='utf-8').read()))
        vcd = os.path.join(out_dir, 'r1rtl_%s.vcd' % case)
        rc, text = call([t['vvp'], exe, '+CASE=%s' % case, '+VCD=%s' % vcd], t['env'], out_dir)
        sims += 1
        if rc != 0 or not os.path.isfile(vcd):
            raise Refused('%s: the re-simulation exited %d: %s'
                          % (case, rc, text.strip()[:160] or 'no output'))
        doc = TR.case_document(vcd, case, gold, str(accepted['shift_ps'] // 1000),
                               str(accepted['ramp_ps'] // 1000))
        bad, checked = compare(accepted, doc)
        old_vcd = os.path.join(os.path.dirname(opts.trace_dir), 'trace_%s.vcd' % case)
        rows.append({'case_id': case, 'rtl_sha256': rtl_sha, 'tb_sha256': tb_sha,
                     'iverilog': version(t['iverilog'], t['env'], out_dir),
                     'vvp': version(t['vvp'], t['env'], out_dir),
                     'new_vcd': os.path.basename(vcd), 'new_vcd_sha256': sha256_of(vcd),
                     'new_vcd_bytes': os.path.getsize(vcd),
                     'new_vcd_mtime_ns': os.stat(vcd).st_mtime_ns,
                     'accepted_vcd_sha256': accepted['facts']['vcd_sha256'],
                     'accepted_vcd_on_disk_sha256': (sha256_of(old_vcd)
                                                     if os.path.isfile(old_vcd) else 'ABSENT'),
                     'fields_compared': checked,
                     'verdict': 'AGREE' if not bad else 'MISMATCH',
                     'mismatched_fields': ';'.join(bad[:6]) or '-',
                     'case_rows': ';'.join(want[case]),
                     'windows': len(doc['windows']),
                     'segments_ps': json.dumps([w['segments_ps'] for w in doc['windows']]).replace(' ', '')})
    hdr = ['case_id', 'rtl_sha256', 'tb_sha256', 'iverilog', 'vvp', 'new_vcd', 'new_vcd_sha256',
           'new_vcd_bytes', 'new_vcd_mtime_ns', 'accepted_vcd_sha256', 'accepted_vcd_on_disk_sha256',
           'case_rows', 'windows', 'fields_compared', 'verdict', 'mismatched_fields', 'segments_ps']
    # the evidence tables are read by a plain split on commas, so no cell may carry one
    for r in rows:
        for k in r:
            r[k] = str(r[k]).replace(',', ';')
    path = os.path.join(out_dir, 'rtl_reverify.csv')
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=hdr, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    agree = len([r for r in rows if r['verdict'] == 'AGREE'])
    print('RTL_REVERIFY_TABLE %s' % path)
    print('NEW_RTL_SIMULATIONS %d (ceiling %d)' % (sims, MAX_RTL_SIMULATIONS))
    print('RTL_REVERIFY_CASES %d AGREE=%d MISMATCH=%d'
          % (len(rows), agree, len(rows) - agree))
    for r in rows:
        if r['verdict'] != 'AGREE':
            print('RTL_REVERIFY_MISMATCH %s %s' % (r['case_id'], r['mismatched_fields']))
    print('D7B_RTL_REVERIFY: %s' % ('PASS' if agree == len(rows) and sims <= MAX_RTL_SIMULATIONS
                                    else 'FAIL'))
    return 0 if agree == len(rows) and sims <= MAX_RTL_SIMULATIONS else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Refused as exc:
        print('D7B_RTL_REVERIFY_REFUSED %s' % exc)
        sys.exit(5)
