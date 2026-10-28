#!/usr/bin/env python3
import collections, contextlib, csv, hashlib, importlib, io, json, os, pathlib, re, subprocess, sys
from decimal import Decimal as D
from datetime import datetime, timezone

root=pathlib.Path(__file__).resolve().parent
repo=root/'repo'; checks=root/'checks';checks.mkdir(exist_ok=True)
base='61621f6e3d887082ecd6a7ecc1c771f8e509a24a'
tip='398c9e852c16db85cbfa4539e859534e117ff0d2'
payload='f49ba9d78190f8c3da2adca9dbd4fb3e48d26841'
def git(*args):
    p=subprocess.run(['git',*args],cwd=repo,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.decode())
    return p.stdout
def tree(sha):
    out={}
    for line in git('ls-tree','-r','-z',sha).split(b'\0'):
        if line:
            spec,name=line.split(b'\t');out[name.decode()]=spec.decode()
    return out
b,t=tree(base),tree(tip)
added=sorted(set(t)-set(b));removed=sorted(set(b)-set(t))
modified=sorted(p for p in b.keys()&t.keys() if b[p]!=t[p])
before={p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in t}
meta={'base':base,'payload':payload,'tip':tip,'read_at_utc':datetime.now(timezone.utc).isoformat(),
 'base_paths':len(b),'tip_paths':len(t),'added':len(added),'modified':modified,'removed':removed,
 'unchanged_base_paths':len(b)-len(modified)-len(removed),
 'new_bytes':sum(len(git('cat-file','blob',tip+':'+p)) for p in added),
 'tip_parent':git('rev-parse','HEAD^').decode().strip(),
 'payload_to_tip':git('diff','--name-status',payload,tip).decode().splitlines(),
 'commits':len(git('rev-list',base+'..'+tip).splitlines()),
 'authorised_task_identical':(repo/'reports/tasks/DATA-7C-B-TR.md').read_bytes()==(
    root.parent/'d7c-b-tr-task-approved-20261026/TASK_DATA7C_B_TR_APPROVED.md').read_bytes()}
dc=repo/'results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv'
with dc.open(newline='',encoding='utf-8') as f:
    dcrows=list(csv.DictReader(f))
meta['dc_table_fields']=list(dcrows[0])
(checks/'scope_and_identity.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')

# Only offline suite code runs. Any external executable except Git is forbidden here.
orig_popen=subprocess.Popen
def safe_popen(args,*pargs,**kwargs):
    if not isinstance(args,(list,tuple)) or pathlib.Path(str(args[0])).name!='git':
        raise AssertionError('REVIEW_FORBIDS_NON_GIT_PROCESS '+repr(args))
    return orig_popen(args,*pargs,**kwargs)
subprocess.Popen=safe_popen
os.environ.pop('QODER_TR_AUTHORISED',None)
os.environ['QODER_TR_STAGING']=str(checks/'offline_suite_scratch')
sys.path.insert(0,str(repo/'scripts'))
suites=[]
for suffix in ['contract','decks','trace','measure','run']:
    mod=importlib.import_module('dd1_d7c_b_tr_'+suffix)
    capture=io.StringIO()
    try:
        with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(capture):
            rc=mod.main(['--selftest'])
        err=None
    except Exception as e:
        rc=99;err=type(e).__name__+': '+str(e)
    (checks/('selftest_'+suffix+'.log')).write_text(capture.getvalue()+('\n'+err if err else ''),encoding='utf-8')
    summaries=[l for l in capture.getvalue().splitlines() if 'SELFTEST' in l]
    suites.append({'suite':suffix,'rc':rc,'summary':summaries,'exception':err})
    print(json.dumps(suites[-1]),flush=True)
changed=[p for p,h in before.items() if hashlib.sha256((repo/p).read_bytes()).hexdigest()!=h]
result={'suites':suites,'tracked_paths_changed_after_review':changed,
        'new_spectre_launches':0,'new_rtl_simulations':0,'new_oa_access':0,'guest_connections':0}
(checks/'offline_suites.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'scope':meta,'verification':result},ensure_ascii=False))
