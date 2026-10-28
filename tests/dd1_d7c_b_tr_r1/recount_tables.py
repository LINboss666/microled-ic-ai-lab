#!/usr/bin/env python3
"""Independent Decimal arithmetic and simple PWL/contract checks. Not a raw-waveform replay."""
import csv, hashlib, json, pathlib, re
from decimal import Decimal as D
root=pathlib.Path(__file__).resolve().parent;repo=root/'repo';checks=root/'checks'
e=repo/'results/evidence/dd1_d7c_b_tr_r20261026_132228_3fc148'
def table(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def close(a,b,rel='2e-10',floor='1e-24'):
    a,b=D(str(a)),D(str(b));return abs(a-b)<=max(D(floor),D(rel)*max(abs(a),abs(b)))
def qty(token):
    m=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([pnumk]?)',token)
    if not m:raise ValueError(token)
    return D(m[1])*{'':D(1),'p':D('1e-12'),'n':D('1e-9'),'u':D('1e-6'),'m':D('1e-3'),'k':D('1e3')}[m[2]]
def waves(text):
    out={}
    for m in re.finditer(r'^\s*\S+\s+\((\w+)\s+0\)\s+vsource\s+type=pwl\s+wave=\[([^\]]+)\]',text,re.M):
        parts=m[2].split();out[m[1]]=[(qty(parts[i]),qty(parts[i+1])) for i in range(0,len(parts),2)]
    for m in re.finditer(r'^\s*\S+\s+\((\w+)\s+0\)\s+vsource\s+dc=(\S+)',text,re.M):
        out.setdefault(m[1],[(D(0),qty(m[2]))])
    return out
def crosses(points,rising):
    out=[];v=D('.9')
    for (ta,va),(tb,vb) in zip(points,points[1:]):
        if ((va<v<=vb) if rising else (va>v>=vb)):
            out.append(ta+(v-va)*(tb-ta)/(vb-va))
    return out
def at(points,t):
    if t<=points[0][0]:return points[0][1]
    for (ta,va),(tb,vb) in zip(points,points[1:]):
        if ta<=t<=tb:return va+(vb-va)*(t-ta)/(tb-ta)
    return points[-1][1]
rows=table(e/'windows_all.csv')
dc=table(repo/'results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv')
dcmap={r['code']:D(r['I_sink_A']) for r in dc if D(r['clamp_V'])==D('1.2') and r['role']=='dut'}
assert len(dcmap)==8
checkrows=[]
def check(name,ok,details=None):checkrows.append({'name':name,'pass':bool(ok),'details':details})
check('37 unique complete row keys',len(rows)==37 and len({(r['case_id'],r['window_id']) for r in rows})==37)
case_order=['TR-LONG','TR-120','TR-200','TR-OFFCODE','RS-FULL','RS-LOW','RS-SWITCH','HYB-120','HYB-200']
bycase={c:[r for r in rows if r['case_id']==c] for c in case_order}
expected_counts=[8,1,1,4,8,1,4,4,3]
for case,want in zip(case_order,expected_counts):
    text=(repo/('spectre/dd1_d7c_b_tr/'+case+'.scs')).read_text()
    w=waves(text);rises=crosses(w['data_en'],True);falls=crosses(w['data_en'],False)
    rs=[r for r in bycase[case] if r['kind']=='emission']
    check(case+' expected emission count',len(rs)==len(rises)==len(falls)==want)
    deckhash=hashlib.sha256(text.encode()).hexdigest()
    for i,r in enumerate(rs):
        name=case+'/'+r['window_id'];tick=D(200 if case in ('TR-200','HYB-200') else 120)
        qlsb=D('1.875e-6')*tick*D('1e-9'); t50=(falls[i]-rises[i])
        code=''.join('1' if at(w['pam'+str(bit)],(rises[i]+falls[i])/2)>D('.9') else '0' for bit in (2,1,0))
        qnom=D(int(code,2)+1)*D('1.875e-6')*t50;qdc=dcmap[code]*t50
        check(name+' tick, QLSB, PWL crossings and code',D(r['tick_ns'])==tick and close(r['qlsb_C'],qlsb)
            and close(r['rise50_ns'],rises[i]*D('1e9'),floor='1e-5')
            and close(r['fall50_ns'],falls[i]*D('1e9'),floor='1e-5') and r['code']==code)
        check(name+' targets from independent accepted DC and code',close(r['qtarget_dc_C'],qdc)
            and close(r['qtarget_nominal_C'],qnom))
        errdyn=(D(r['q_full_C'])-qdc)/qlsb;errnom=(D(r['q_full_C'])-qnom)/qlsb
        check(name+' both derived errors',close(r['err_dynamic_LSB'],errdyn,floor='2e-8')
            and close(r['err_nominal_LSB'],errnom,floor='2e-8'))
        check(name+' signed area identity',close(r['q_full_C'],D(r['q_pos_C'])+D(r['q_neg_C']))
            and D(r['q_neg_C'])<=0 and D(r['q_pos_C'])>=0 and close(r['abs_q_neg_C'],-D(r['q_neg_C'])))
        check(name+' full deck hash',r['deck_sha256']==deckhash)
conv=table(e/'convergence.csv'); indexed={(r['case_id'],r['window_id']):r for r in rows}
check('13 convergence rows',len(conv)==13)
for r in conv:
    pair=r['pair'].split('/');x=indexed[(pair[0],r['window_id'])];y=indexed[(pair[1],r['window_id'])]
    dq=D(x['q_full_C'])-D(y['q_full_C']);ratio=abs(dq)/D(x['qlsb_C'])
    check(r['pair']+'/'+r['window_id']+' actual joined charge difference and verdict',
          close(r['refined_q_C'],x['q_full_C']) and close(r['coarse_q_C'],y['q_full_C'])
          and close(r['dq_C'],dq,floor='2e-22') and close(r['abs_dq_over_qlsb'],ratio,floor='2e-8')
          and (r['status']=='PASS')==(ratio<=D('.01')))
dynamic=[{'case':r['case_id'],'window':r['window_id'],'error_LSB':r['err_dynamic_LSB']} for r in rows if abs(D(r['err_dynamic_LSB']))>D('.5')]
nominal=[{'case':r['case_id'],'window':r['window_id'],'error_LSB':r['err_nominal_LSB']} for r in rows if abs(D(r['err_nominal_LSB']))>D('.5')]
spectre=table(e/'spectre_launch_account.csv');rtl=table(e/'rtl_simulation_account.csv')
strays=json.loads((e/'spectre_budget_adjustments.json').read_text())
stray_n=sum(int(r['processes']) for r in strays['adjustments'])
check('Spectre 21 reserved/charged of24',len(spectre)==19 and stray_n==2 and len(spectre)+stray_n==21)
for c in case_order:
    pf=[r for r in spectre if r['case_id']==c and r['role']=='preflight' and r['state']=='CONFIRMED']
    du=[r for r in spectre if r['case_id']==c and r['role']=='dut' and r['state']=='CONFIRMED']
    check(c+' confirmed PF precedes DUT in submitted account',len(pf)==len(du)==1 and pf[0]['ended_utc']<du[0]['requested_utc'])
check('four dynamic failures and14 nominal failures retained',len(dynamic)==4 and len(nominal)==14)
for r in rows:
    if r['kind'].startswith('black'):
        check(r['case_id']+'/'+r['window_id']+' black leakage published below150nA',D(r['leak_max_abs_A'])<=D('1.5e-7'))
task=(repo/'reports/tasks/DATA-7C-B-TR.md').read_bytes()
approved=(root.parent/'d7c-b-tr-task-approved-20261026/TASK_DATA7C_B_TR_APPROVED.md').read_bytes()
check('task has exact approved body after added provenance preface',task.endswith(approved))
result={'checks':len(checkrows),'failed':[r for r in checkrows if not r['pass']],
        'dynamic_failures':dynamic,'nominal_failures':nominal,
        'max_nominal_error_LSB':str(max(abs(D(r['err_nominal_LSB'])) for r in rows)),
        'max_convergence_qlsb':max((r['abs_dq_over_qlsb'] for r in conv),key=float),
        'spectre_reserved_or_charged':len(spectre)+stray_n,'spectre_ceiling':24,
        'spectre_remaining':24-len(spectre)-stray_n,'rtl_rows':len(rtl),
        'rtl_count_note':'5 rows; one duplicate booking is an executor reconciliation requiring process evidence, not proof from same-second timestamps alone.',
        'raw_waveform_reintegration':'NOT_POSSIBLE_FROM_GIT_TABLES_ONLY','details':checkrows}
(checks/'independent_table_recount.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2))
