#!/usr/bin/env python3
"""Reviewer-only offline probes on fixed DATA-7C-B-TR source. No simulator/guest calls.
rc=0 means every named defect reproduced; rc=1 means a defect did not reproduce.
All modifications are confined to a newly created reviewer scratch directory.
"""
import argparse, contextlib, copy, csv, hashlib, io, json, os, pathlib, shutil, subprocess, sys, tempfile

p=argparse.ArgumentParser()
p.add_argument('repo')
p.add_argument('--out', required=True)
a=p.parse_args()
repo=pathlib.Path(a.repo).resolve()
out=pathlib.Path(a.out).resolve()
out.mkdir(parents=True, exist_ok=True)
scratch=pathlib.Path(tempfile.mkdtemp(prefix='probe_', dir=out))
sys.path.insert(0, str(repo/'scripts'))
os.environ.pop('QODER_TR_AUTHORISED', None)
os.environ['QODER_TR_STAGING']=str(scratch/'suite_staging')
original_popen=subprocess.Popen
spawned=[]
def guarded_popen(args, *pargs, **kwargs):
    first=os.path.basename(str(args[0])) if isinstance(args,(list,tuple)) else ''
    if first not in ('git',os.path.basename(sys.executable)):
        raise AssertionError('REVIEW_FORBIDS_PROCESS: '+repr(args))
    spawned.append(first)
    return original_popen(args,*pargs,**kwargs)
subprocess.Popen=guarded_popen
import dd1_d7c_b_tr_contract as C
import dd1_d7c_b_tr_decks as D
import dd1_d7c_b_tr_measure as M
import dd1_d7c_b_tr_run as U
import dd1_d7c_b_tr_trace as T
import dd1_d7c_b_tr_record as R
evidence=repo/'results/evidence/dd1_d7c_b_tr_r20261026_132228_3fc148'
result={'repo':str(repo),'scratch':str(scratch),'native_launches':0,'rtl_simulations':0,'probes':{},'positive_controls':{}}

# Sequential stale objects, not concurrent threads: the lock exists but does not reread disk.
acct_path=str(scratch/'stale_account.csv')
first=U.Account(acct_path,1,U.ACCOUNT_HEADER,'T')
stale=U.Account(acct_path,1,U.ACCOUNT_HEADER,'T')
first.reserve({'case_id':'TR-120','role':'dut','run_id':'r'})
after_first=pathlib.Path(acct_path).read_bytes()
stale_refused=False
try:
    stale.reserve({'case_id':'TR-200','role':'dut','run_id':'r'})
except U.Refuse:
    stale_refused=True
after_stale=pathlib.Path(acct_path).read_bytes()
disk=U.Account(acct_path,1,U.ACCOUNT_HEADER,'T')
result['probes']['stale_account_overwrites_a_charged_reservation']={
 'reproduced':not stale_refused and after_first!=after_stale and len(disk.rows)==1 and disk.rows[0]['case_id']=='TR-200',
 'ceiling':1,'successful_reservations':2 if not stale_refused else 1,'disk_rows':len(disk.rows),
 'disk_case':disk.rows[0]['case_id'],'refused':stale_refused}

# A complete syntactically valid tiny PSF: the unit and supply variants change only one fact.
def psf(path,current_unit='A',vdd=1.8,times=(0.0,1e-9,2e-9)):
    names=[x for x in M.REQUIRED if x not in ('time','Ip_branch_current')]+['Ip_branch:current']
    values={'data_en':0.0,'pam0':0.0,'pam1':0.0,'pam2':0.0,'vdd18':vdd,'vss':0.0,
            'vcas':1.8,'iref_in':0.75,'clamp_node':1.2,'data_out':1.2,'Ip_branch:current':1.875e-6}
    lines=['SWEEP','"time" "sweep"','"units" "s"','TRACE','"time" "s"']
    lines += ['"%s" "%s"'%(n,current_unit if n=='Ip_branch:current' else 'V') for n in names]
    lines += ['VALUE']
    for t in times:
        lines += ['"time" %.15e'%t]
        lines += ['"%s" %.15e'%(n,values[n]) for n in names]
    lines += ['END']
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return path
valid=M.load_raw(str(psf(scratch/'valid.raw')),'TR-120')
result['positive_controls']['valid_psf']={'accepted':valid['samples']==3,'unit':valid['units'][valid['current_name']]}
for name,kw in [('wrong_current_unit',{'current_unit':'V'}),('zero_vdd18',{'vdd':0.0}),
                ('nonincreasing_time',{'times':(0,2e-9,1e-9)})]:
    path=psf(scratch/(name+'.raw'),**kw)
    try:
        data=M.load_raw(str(path),'TR-120')
        obs=U.observe(str(path),'TR-120','dut','r','T001','a'*64)
        result['probes']['native_'+name+'_accepted']={'reproduced':True,'unit':data['units'][data['current_name']],
            'vdd18':[v for _,v in data['series']['vdd18']], 'times_ps':[t for t,_ in data['series']['data_en']],
            'observe_finite':obs['finite'],'observe_monotonic':obs['monotonic']}
    except Exception as e:
        result['probes']['native_'+name+'_accepted']={'reproduced':False,'refusal':type(e).__name__+': '+str(e)}

# End-to-end VCD -> accepted PWL conversion with preserved widths but 10 ns late endpoints.
sig=T.synthetic_signals(group_ns=200,safety=False)
vcd=scratch/'positive_control.vcd'
T.write_vcd(str(vcd),sig)
base=T.convert('HYB-200',str(vcd))
result['positive_controls']['synthetic_hybrid_converter']={'accepted':base['frame_count']==4,
 'source':'SYNTHETIC_NOT_MEASURED','frame_count':base['frame_count']}
mut=copy.deepcopy(sig)
mut['data_en']=[(t+10000 if value==1 or (index and mut['data_en'][index-1][1]==1) else t,value)
                for index,(t,value) in enumerate(mut['data_en'])]
mut['data_en_b']=[(t+10000 if t in {x for x,v in sig['data_en'] if v==1} or t in {
    x for index,(x,v) in enumerate(sig['data_en']) if index and sig['data_en'][index-1][1]==1} else t,value)
    for t,value in mut['data_en_b']]
T.write_vcd(str(scratch/'late_enable.vcd'),mut)
try:
    late=T.convert('HYB-200',str(scratch/'late_enable.vcd'))
    offsets=[(f['conducting_segments'][0][0]-f['t0_ps'])/1000 for f in late['frames'] if f['conducting_segments']]
    result['probes']['ten_ns_late_hybrid_enable_accepted']={'reproduced':offsets==[10.0]*3,
        'start_offsets_ns':offsets,'widths_ns':[f['conduct_ns'] for f in late['frames']],
        'source':'SYNTHETIC_NOT_MEASURED'}
except Exception as e:
    result['probes']['ten_ns_late_hybrid_enable_accepted']={'reproduced':False,'refusal':str(e)}

rows=R.all_rows(str(evidence)); conv,_,_=R.convergence_table(str(evidence))
observed=R.integrity(str(evidence)); completed=R.completeness(str(evidence))
statuses=M.statuses(rows,conv,observed,completed)
result['positive_controls']['submitted_tables']={'windows':len(rows),'integrity':observed,'statuses':statuses}
mutrows=copy.deepcopy(rows)
for row in mutrows:
    if row['kind'].startswith('black'):
        row['peak_A']=1e-6
        row['leak_max_abs_A']=1e-6
        row['q_full_C']=0.0
        row['err_nominal_LSB']=row['err_dynamic_LSB']=0.0
changed=M.statuses(mutrows,conv,observed,completed)
shutoff=next(r for r in changed if r['status']=='SHUTOFF_STATUS')
result['probes']['black_window_one_uA_peak_ignored_by_shutoff_status']={
 'reproduced':shutoff['verdict']=='PASS','black_peak_A':1e-6,'frozen_limit_A':C.LEAK_LIMIT_A,'shutoff':shutoff}

# Reconstruct the exact generated recompute source from the reviewed Git bytes.
def table_write(path,rows,fields=None):
    fields=fields or list(rows[0])
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def replay(name,mutator=None):
    root=scratch/name
    d=root/'results/evidence'/evidence.name
    shutil.copytree(evidence,d)
    (root/'tests/dd1_d7c_b_tr').mkdir(parents=True)
    shutil.copyfile(repo/'tests/dd1_d7c_b_tr/contract.json',root/'tests/dd1_d7c_b_tr/contract.json')
    (root/'independent_recompute.py').write_text(R.recompute_source(),encoding='utf-8')
    if mutator: mutator(d)
    proc=subprocess.run([sys.executable,str(root/'independent_recompute.py')],capture_output=True,text=True)
    (root/'replay.log').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    return {'rc':proc.returncode,'summary':[x for x in proc.stdout.splitlines() if x.startswith('RECOMPUTE ')],
            'log':str(root/'replay.log')}
result['positive_controls']['original_generated_recompute']=replay('recompute_original')
def rows_load(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def forge_dc(d):
    path=d/'windows_all.csv';rows=rows_load(path)
    for row in rows:
        if row['kind']=='emission':
            row['qtarget_dc_C']=row['q_full_C'];row['err_dynamic_LSB']='0'
    table_write(path,rows)
    path=d/'statuses.csv';states=rows_load(path)
    for row in states:
        if row['status']=='DYNAMIC_CHARGE_STATUS': row['verdict']='PASS';row['measured']='37'
    table_write(path,states)
def forge_tick(d):
    path=d/'windows_all.csv';rows=rows_load(path)
    for row in rows:
        if row['case_id']=='TR-120':
            qlsb=1.875e-6*1000e-9
            row['tick_ns']='1000';row['qlsb_C']=repr(qlsb)
            row['err_dynamic_LSB']=repr((float(row['q_full_C'])-float(row['qtarget_dc_C']))/qlsb)
            row['err_nominal_LSB']=repr((float(row['q_full_C'])-float(row['qtarget_nominal_C']))/qlsb)
    table_write(path,rows)
def forge_five_rtl(d):
    path=d/'rtl_simulation_account.csv';rows=rows_load(path)
    rows[0]['exe_sha256']='f'*64;rows[0]['rc']='99';rows[0]['state']='FAILED'
    table_write(path,rows)
for name,mutator in [('forged_dc_target_and_dynamic_PASS',forge_dc),('wrong_reference_tick_1000ns',forge_tick),
                     ('five_process_evidence_rows_as_four',forge_five_rtl)]:
    info=replay(name,mutator);info['reproduced']=info['rc']==0
    result['probes']['generated_recompute_accepts_'+name]=info

result['all_named_defects_reproduced']=all(v['reproduced'] for v in result['probes'].values())
result['positive_controls_pass']=all([result['positive_controls']['valid_psf']['accepted'],
 result['positive_controls']['synthetic_hybrid_converter']['accepted'],
 result['positive_controls']['original_generated_recompute']['rc']==0,
 result['positive_controls']['submitted_tables']['integrity']['verdict']=='PASS'])
result['permitted_processes']=sorted(set(spawned))
dest=out/'probe_tr_review_gaps.json'
dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'probes':{k:v['reproduced'] for k,v in result['probes'].items()},
                  'all_named_defects_reproduced':result['all_named_defects_reproduced'],
                  'positive_controls_pass':result['positive_controls_pass'],
                  'native_launches':0,'rtl_simulations':0,'result':str(dest)},ensure_ascii=False,indent=2))
sys.exit(0 if result['all_named_defects_reproduced'] and result['positive_controls_pass'] else 1)
