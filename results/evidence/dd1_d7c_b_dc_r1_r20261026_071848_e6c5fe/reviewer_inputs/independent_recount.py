from pathlib import Path
import csv,json,hashlib,subprocess,math
from decimal import Decimal as D
R=Path(__file__).parent; repo=R/'repo'; ev=repo/'results/evidence/dd1_d7c_b_dc_r20261026_015212_376554'; base='e51c5320a28bd5043e21d08a0be97e9d5612cd16'
def table(p):
 with p.open(newline='') as f: return list(csv.DictReader(f))
def git(*args): return subprocess.check_output(['git','-C',str(repo),*args])
def sha(b): return hashlib.sha256(b).hexdigest()
checks=[]
def check(name,ok,detail=None): checks.append(dict(name=name,pass_=bool(ok),detail=detail))
codes=[format(k,'03b') for k in range(8)]; grid=[D('0.60')+D('0.05')*k for k in range(19)]
account=table(ev/'launch_account.csv'); join={(r['case_id'],r['role']):r for r in account}
rows=table(ev/'dc_matrix_dut.csv'); pre=table(ev/'dc_matrix_preflight.csv')
check('unique_expected_152_dut_keys',len(rows)==152 and len({(r['code'],D(r['clamp_V'])) for r in rows})==152 and {(r['code'],D(r['clamp_V'])) for r in rows}=={(c,v) for c in codes for v in grid})
check('preflight_expected_152',len(pre)==152 and {(r['code'],D(r['clamp_V'])) for r in pre}=={(c,v) for c in codes for v in grid})
check('actual_conditions_finite_signed_units',all(r['code']==r['pam_bits']==r['case_id'][3:] and D(r['data_out_V'])==D(r['clamp_V']) and D(r['I_sink_A'])>0 and all(D(r[k])==v for k,v in [('vdd18_V',D('1.8')),('vcas_V',D('1.8')),('data_en_V',D('1.8')),('iref_source_A',D('15e-6')),('temp_C',D('27'))]) and r['unit_clamp']=='V' and r['unit_current']=='A' and r['corner']=='TT' and all(math.isfinite(float(r[k])) for k in ['I_sink_A','I_sink_uA','iref_node_V','data_out_V']) for r in rows+pre))
check('microamp_display_rounding',all(abs(D(r['I_sink_uA'])-D(r['I_sink_A'])*D(10)**6)<=D('0.00000051') for r in rows+pre))
check('per_case_merged_tables_equal',all([r for r in (rows if role=='dut' else pre) if r['case_id']=='DC-'+code]==table(ev/f'rows_DC-{code}_{role}.csv') for code in codes for role in ['dut','preflight']))
check('deck_and_raw_hash_join_to_account',all(r['deck_sha256']==join[(r['case_id'],r['role'])]['deck_sha256'] and r['raw_sha256']==join[(r['case_id'],r['role'])]['raw_sha256'] for r in rows+pre))
check('all_account_decks_match_git_bytes',all(sha((repo/('spectre/dd1_d7c_b_prep/'+r['case_id']+'.scs' if r['role']=='dut' else 'spectre/dd1_d7c_b_dc/'+r['case_id']+'.pre.scs')).read_bytes())==r['deck_sha256'] for r in account))
check('sixteen_account_rows',len(account)==16 and [r['launch_id'] for r in account]==['D%03d'%k for k in range(1,17)] and len(join)==16 and all(r['role'] in ['preflight','dut'] and r['state'] in ['CONFIRMED','FAILED','UNCERTAIN','REQUESTED'] and int(r['ceiling'])==20 and r['rc']=='0' and int(r['occupied_after'])==i for i,r in enumerate(account,1)))
check('ideal_witness_all_152_points',all(abs(D(r['I_sink_A'])-D(r['clamp_V'])/D(80000))<D('1e-12') and abs(D(r['iref_node_V'])-D('.75'))<D('1e-6') for r in pre))
I={c:D(next(r['I_sink_A'] for r in rows if r['code']==c and D(r['clamp_V'])==D('1.2'))) for c in codes}; unit=I['111']/8
err={c:I[c]-(int(c,2)+1)*unit for c in codes}; ratio={c:err[c]/unit for c in codes}
check('fullscale_15uA_plus_minus_5pct',D('14.25e-6')<=I['111']<=D('15.75e-6'))
check('strictly_increasing',all(I[a]<I[b] for a,b in zip(codes,codes[1:])))
check('ratio_within_quarter_unit',all(abs(x)<=D('.25')*unit for x in err.values()))
variation={c:max(abs(D(r['I_sink_A'])-I[c])/I[c] for r in rows if r['code']==c) for c in codes}
check('signed_5pct_band_all_measured_points',all(x<=D('.05') for x in variation.values()))
published=json.loads((ev/'judgement.json').read_text())['judgement']
check('judgement_matches_independent_decimal_arithmetic',all(abs(D(str(published['I_at_main_A_by_code'][c]))-I[c])<D('1e-20') and abs(D(str(published['per_code_deviation_A'][c]))-err[c])<D('1e-19') for c in codes))
ident=table(ev/'source_identity.csv'); mismatch=[]
for row in ident:
 b=git('show','HEAD:'+row['path'])
 if len(b)!=int(row['bytes']) or sha(b)!=row['sha256']: mismatch.append(row['path'])
check('131_source_identities_match_tip_git_blobs',len(ident)==131 and len({r['path'] for r in ident})==131 and not mismatch,mismatch)
def tree(rev): return {line.split('\t',1)[1]:line.split('\t',1)[0] for line in git('ls-tree','-r',rev).decode().splitlines()}
a,b=tree(base),tree('HEAD'); mod=[p for p in a.keys()&b.keys() if a[p]!=b[p]]; adds=sorted(b.keys()-a.keys()); dels=sorted(a.keys()-b.keys())
check('only_two_allowed_existing_paths_modified',sorted(mod)==['reports/dd1_d7c_b_prep_contract.md','scripts/dd1_d7c_b_prep_contract.py'] and not dels,dict(modified=mod,added=len(adds),deleted=len(dels),frozen_unchanged=len(a)-len(mod)))
# Reconstruct all stripped includes independently from the exact permitted annotation line grammar.
import re
removed=0
for p in (repo/'spectre/dd1_d7c_b_dc/masters').glob('*.scs'):
 original=git('show',base+':spectre/'+p.name).decode(); lines=original.splitlines(keepends=True)
 keep=[line for line in lines if not re.match(r'^\s*parameters\s+\S+\s+(?:input|output|inputOutput)\s*$',line.strip(),re.I)]
 removed+=len(lines)-len(keep)
 check('derived_master_'+p.name,''.join(keep).encode()==p.read_bytes())
check('63_direction_annotations_only',removed==63,removed)
summary=dict(checks=checks,failed=[x for x in checks if not x['pass_']],main_currents_uA={c:str(I[c]*D(10)**6) for c in codes},unit_uA=str(unit*D(10)**6),fullscale_error_percent=str((I['111']/D('15e-6')-1)*100),worst_deviation_A=str(max(map(abs,err.values()))),worst_deviation_uA=str(max(map(abs,err.values()))*D(10)**6),worst_deviation_in_units=str(max(map(abs,ratio.values()))),max_scan_fraction_by_code={c:str(v) for c,v in variation.items()},metadata_limit=dict(row_run_ids=sorted(set(r['run_id'] for r in rows+pre)),row_launch_ids=sorted(set(r['launch_id'] for r in rows+pre)),raw_join_possible=True,raw_outputs_present=False))
(R/'checks/independent_recount.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
