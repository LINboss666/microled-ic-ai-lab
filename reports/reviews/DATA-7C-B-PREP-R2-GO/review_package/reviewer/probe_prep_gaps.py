#!/usr/bin/env python3
"""Read-only independent DATA-7C-B-PREP diagnostics. No simulator, VM, or tracked write.

rc=0 means all four reviewed defect families reproduce, not acceptance.
rc=1 means one or more no longer reproduce: read individual JSON facts.
rc=2 means the instrument could not complete.
"""
import argparse
import bisect
import csv
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def statements(path):
    return [x.strip() for x in path.read_text(encoding='utf-8').splitlines()
            if x.strip() and not x.lstrip().startswith('//')]


def voltage_series(path):
    out = {}
    for line in statements(path):
        m = re.match(r'\S+\s+\((\w+)\s+0\)\s+vsource\s+(.*)', line)
        if not m:
            continue
        node, body = m.groups()
        dc = re.search(r'\bdc=([+\-0-9.eE]+)', body)
        if dc:
            out[node] = [(0.0, float(dc.group(1)))]
        elif 'type=pwl' in body:
            points = re.search(r'time=\{([^}]+)\}\s+value=\{([^}]+)\}', body)
            wave = re.search(r'\bwave=\[([^]]+)\]', body)
            if points:
                ts = [float(x.removesuffix('n')) for x in points.group(1).split()]
                vs = [float(x) for x in points.group(2).split()]
            elif wave:
                fields = wave.group(1).split()
                ts = [float(x.removesuffix('n')) for x in fields[::2]]
                vs = [float(x) for x in fields[1::2]]
            else:
                raise ValueError('unsupported reviewer PWL spelling at ' + node)
            if len(ts) != len(vs):
                raise ValueError('unequal PWL lengths')
            out[node] = list(zip(ts, vs))
    return out


def interp(points, t):
    times = [x[0] for x in points]
    i = bisect.bisect_right(times, t)
    if not i:
        return points[0][1]
    if i == len(points):
        return points[-1][1]
    a, va = points[i - 1]
    b, vb = points[i]
    return va + (vb - va) * (t - a) / (b - a)


def rising_edges(points, level=0.9):
    return [a + (level-va)*(b-a)/(vb-va)
            for (a, va), (b, vb) in zip(points, points[1:]) if va <= level < vb]


def run(root):
    base = root/'tests/dd1_d7c_b_prep'
    rows = read_csv(base/'schedule.csv')
    windows = read_csv(base/'windows.csv')
    decks = root/'spectre/dd1_d7c_b_prep'
    facts = {}
    code_mismatch, bad_high = [], []
    for row in rows:
        if row['class'] != 'dc_sweep':
            continue
        sources = voltage_series(decks/(row['case_id']+'.scs'))
        bits = [sources['pam'+str(i)][0][1] for i in range(3)]
        intended = int(row['pam_code'], 2)
        # Logical bit identity only, NOT analogue decoding or current measurement.
        actual_weight = sum((1 << i) for i, v in enumerate(bits) if v > 0.9)
        if actual_weight != intended:
            code_mismatch.append({'case_id':row['case_id'],'expected_code':intended,
                                  'source_levels_pam0_pam1_pam2_V':bits,
                                  'ideal_logic_code_if_1V_is_high':actual_weight})
        for i, v in enumerate(bits):
            wanted = 1.8 if (intended >> i) & 1 else 0.0
            if v not in (0.0, 1.8):
                bad_high.append({'case_id':row['case_id'],'node':'pam'+str(i),
                                 'actual_V':v,'contract_logic_rail_V':1.8})
    facts['F1_PAM_bit_order_and_high_level'] = {
        'reproduced': bool(code_mismatch and bad_high),
        'dc_code_mismatches':code_mismatch,'nonrail_highs':bad_high,
        'interpretation':'decoded code is ideal bit-weight arithmetic; no analogue current is asserted'}

    ramps, edge_errors, reversed_off, dirty_tail = [], [], [], []
    for row in rows:
        if row['class'] == 'dc_sweep':
            continue
        cid = row['case_id']
        sources = voltage_series(decks/(cid+'.scs'))
        en = sources['data_en']
        emission = [w for w in windows if w['case_id']==cid and w['kind']=='emission']
        for node in ('pam0','pam1','pam2'):
            for (a,va),(b,vb) in zip(sources[node],sources[node][1:]):
                if va == vb:
                    continue
                for w in emission:
                    lo, hi = max(a,float(w['start_ns'])), min(b,float(w['stop_ns']))
                    if hi > lo:
                        ramps.append({'case_id':cid,'node':node,'window_id':w['window_id'],
                                      'overlap_ns':[lo,hi],
                                      'values_at_overlap_V':[interp(sources[node],lo),interp(sources[node],hi)]})
        actual = rising_edges(en)
        declared = [float(x) for x in row['enable_rise_50_ns'].split(';')]
        for i,(a,b) in enumerate(zip(actual,declared)):
            if abs(a-b)>1e-6:
                edge_errors.append({'case_id':cid,'index':i,'declared_ns':b,'PWL_crossing_ns':a})
        for token in row['off_window_ns'].split(';'):
            if not token:
                continue
            m = re.fullmatch(r'([0-9.]+)-([0-9.]+)',token)
            if m and float(m[1])>float(m[2]):
                reversed_off.append({'case_id':cid,'declared_off_window_ns':token})
        for w in windows:
            if w['case_id']!=cid or w['kind']!='off_tail':
                continue
            a,b=float(w['start_ns']),float(w['stop_ns'])
            a=max(a,b-100.0)
            pts=[a,b]+[t for t,_ in en if a<t<b]
            vmax=max(interp(en,t) for t in pts)
            if vmax>0.01:
                dirty_tail.append({'case_id':cid,'window_id':w['window_id'],
                                   'last100_ns':[a,b],'max_enable_V':vmax})
    facts['F2_PWL_and_window_physics'] = {'reproduced':bool(ramps and edge_errors and dirty_tail),
        'PAM_ramps_over_emission_count':len(ramps),'PAM_ramp_examples':ramps[:8],
        'enable_50_percent_errors':edge_errors,'backwards_off_windows':reversed_off,
        'leakage_windows_with_next_enable':dirty_tail}

    sys.path.insert(0,str(root/'scripts'))
    measure=importlib.import_module('dd1_d7c_b_prep_measure')
    tr=next(r for r in rows if r['case_id']=='TR-LONG')
    sources=voltage_series(decks/'TR-LONG.scs')
    grid=list(range(0,int(float(tr['stop_ns']))+1))
    second=next(w for w in windows if w['window_id']=='TR-LONG#T1')
    bad_start=float(second['stop_ns'])-90.0
    bad_stop=float(second['stop_ns'])-60.0
    # Positive ideal current inside each real enable window; quiet first tail, bad second tail.
    # Every sample is independent SYNTHETIC arithmetic, not a MOS model or simulator output.
    en=sources['data_en']
    rises=rising_edges(en)
    falls=[a+(0.9-va)*(b-a)/(vb-va) for (a,va),(b,vb) in zip(en,en[1:]) if va>=0.9>vb]
    periods=list(zip(rises,falls))
    def synthetic_current(t):
        if bad_start<=t<=bad_stop:
            return 5e-6
        return next(((k+1)*1.875e-6 for k,(a,b) in enumerate(periods) if a<t<b),0.0)
    samples={'current':[(float(t)*1000.0,synthetic_current(t)) for t in grid],
             'enable':[(float(t)*1000.0,interp(sources['data_en'],t)) for t in grid]}
    entries=measure.measure_case(tr,windows,samples)
    reference=measure.leakage(samples['current'],float(second['start_ns'])*1000,
                              float(second['stop_ns'])*1000,None)
    summary=[{'window_id':x['window_id'],'rise_status':x['edges']['rise_status'],
              'fall_status':x['edges']['fall_status'],
              'leakage_interval_ps':[x['leakage']['window_start_ps'],x['leakage']['window_stop_ps']],
              'leakage_max_A':x['leakage']['max_abs_A'],
              'has_full_enable_window_q':'q_full_enable_C' in x,
              'has_charge_error_result':'error_nominal_LSB' in x} for x in entries]
    no_real_edges=all(x['rise_status']=='NO_REAL_EDGE_FOUND' for x in summary)
    reused_first=all(x['leakage_interval_ps']==summary[0]['leakage_interval_ps'] for x in summary)
    later_hidden=reference['status']=='ABOVE_LIMIT' and all(x['leakage_max_A']==0 for x in summary)
    try:
        empty_context=measure.convergence({'q':1e-13},{'q':1e-13},120e-9)
    except measure.Refuse as e:
        empty_context={'status':'REFUSED','reason':str(e)}
    facts['F3_measurement_entry_wiring']={'reproduced':bool(no_real_edges and reused_first and later_hidden),
        'samples_identity':'SYNTHETIC_NOT_MEASURED', 'entries':summary,
        'second_tail_independent_reference':{'status':reference['status'],'max_A':reference['max_abs_A']},
        'missing_pair_context_still_accepted':empty_context['status']=='WITHIN_LIMIT',
        'missing_pair_context_result':empty_context,
        'static_call_graph_fact':'measure_case does not call charge_errors or sign_check'}

    bad_form, no_temp = [], []
    for row in rows:
        lines=statements(decks/(row['case_id']+'.scs'))
        analysis=[l for l in lines if l.startswith(('tran ','dc '))]
        if analysis:
            bad_form.append({'case_id':row['case_id'],'actual':analysis,
                             'repository_proven_form':'<instance> tran ... or <instance> dc ...'})
        if not any(re.search(r'\btemp\s*=\s*27(?:\.0)?\b',l) for l in lines):
            no_temp.append(row['case_id'])
    facts['F4_native_deck_known_contract']={'reproduced':bool(len(bad_form)==15 and len(no_temp)==15),
        'unnamed_analysis_lines':bad_form,'no_explicit_27C':no_temp,
        'native_syntax_verdict':'NOT_RUN; textual mismatch against already-proven project syntax, not a simulator result'}
    return {'instrument':'probe_prep_gaps.py','source_root':str(root),
            'contract_identity':'PROPOSED_FOR_REVIEW',
            'NEW_SPECTRE_LAUNCHES':0,'NEW_RTL_SIMULATIONS':0,'NEW_OA_WRITES':0,
            'findings':facts,'all_four_families_reproduced':all(x['reproduced'] for x in facts.values())}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:
        data=run(args.root.resolve())
        data['instrument_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        rc=0 if data['all_four_families_reproduced'] else 1
    except Exception as e:
        data={'instrument_error':type(e).__name__+': '+str(e),'all_four_families_reproduced':False}
        rc=2
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rc_meaning':'0=all_four_families_reproduced; 1=not_all; 2=instrument_error',
                     'result':data.get('all_four_families_reproduced'),
                     'individual':{k:v['reproduced'] for k,v in data.get('findings',{}).items()},
                     'error':data.get('instrument_error'),'out':str(args.out)},ensure_ascii=False))
    return rc


if __name__=='__main__':
    raise SystemExit(main())
