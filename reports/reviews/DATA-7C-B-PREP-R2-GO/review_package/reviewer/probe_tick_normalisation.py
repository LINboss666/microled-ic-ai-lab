#!/usr/bin/env python3
"""Independent SYNTHETIC check: a full enable window is not a grey-code tick.

rc=0: reviewed normalisation defect reproduced. rc=1: not reproduced; inspect facts.
rc=2: instrument could not complete. No simulator or tracked writes.
"""
import argparse
import csv
import hashlib
import importlib
import json
import re
import sys
from pathlib import Path


def table(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def run(root):
    sys.path.insert(0, str(root/'scripts'))
    measure=importlib.import_module('dd1_d7c_b_prep_measure')
    contract=json.loads((root/'tests/dd1_d7c_b_prep/contract.json').read_text())
    rows=table(root/'tests/dd1_d7c_b_prep/schedule.csv')
    windows=table(root/'tests/dd1_d7c_b_prep/windows.csv')
    row=next(r for r in rows if r['case_id']=='TR-LONG')
    text=(root/'spectre/dd1_d7c_b_prep/TR-LONG.scs').read_text()
    line=next(x for x in text.splitlines() if re.match(r'^Vdata_en\s', x))
    wave=re.search(r'\bwave=\[([^]]+)\]',line)
    if not wave:
        raise ValueError('reviewer expects the R1 wave=[...] PWL spelling')
    tokens=wave.group(1).split()
    enable=[(float(t.removesuffix('n'))*1000.0,float(v))
            for t,v in zip(tokens[::2],tokens[1::2])]
    starts=[float(x) for x in row['platform_start_ns'].split(';')]
    stops=[float(x) for x in row['platform_stop_ns'].split(';')]
    extra_charge_C=0.5e-12
    current=[(0.0,0.0)]
    for index,(a,b) in enumerate(zip(starts,stops)):
        nominal=(index+1)*1.875e-6   # independent hand arithmetic, not the design's table
        height=nominal+(extra_charge_C/((b-a)*1e-9) if index==7 else 0.0)
        current += [((a-1)*1000,0.0),(a*1000,height),(b*1000,height),((b+1)*1000,0.0)]
    current.append((float(row['stop_ns'])*1000,0.0))
    records=measure.measure_case(row,windows,{'enable':enable,'current':current})
    entry=next(x for x in records if x['code']=='111')
    got=entry['charge_error']
    error_C=entry['q_full_C']-15e-6*((stops[7]-starts[7])*1e-9)
    declared_ticks=contract['rules']['charge_error']['nominal_ticks_s']
    expected=[]
    for tick in declared_ticks:
        qlsb=1.875e-6*float(tick)
        error=error_C/qlsb
        expected.append({'contract_tick_s':tick,'qlsb_C':qlsb,'error_LSB':error,
                         'outside_half_LSB':abs(error)>0.5})
    differs=all(abs(got['qlsb_C']-x['qlsb_C'])>1e-24 for x in expected)
    washed=(got['verdict_nominal']=='WITHIN_PROPOSED_LIMIT'
            and all(x['outside_half_LSB'] for x in expected))
    return {'evidence_class':'SYNTHETIC_NOT_MEASURED',
            'native_launches':0,'case_id':'TR-LONG','code':'111',
            'actual_full_window_s':entry['t50_s'],'expected_extra_charge_C':extra_charge_C,
            'observed_extra_charge_C':error_C,'delivered_entry':{
                'q_full_C':entry['q_full_C'],'tick_s':got['tick_s'],'qlsb_C':got['qlsb_C'],
                'error_nominal_LSB':got['error_nominal_LSB'],
                'verdict_nominal':got['verdict_nominal']},
            'independent_contract_references':expected,
            'reported_denominator_is_neither_declared_tick':differs,
            'over_half_LSB_error_accepted_by_window_denominator':washed,
            'defect_reproduced':bool(differs and washed)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    try:
        data=run(args.root.resolve())
        data['instrument_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        rc=0 if data['defect_reproduced'] else 1
    except Exception as e:
        data={'instrument_error':type(e).__name__+': '+str(e),'defect_reproduced':False};rc=2
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(data,ensure_ascii=False))
    return rc


if __name__=='__main__':
    raise SystemExit(main())
