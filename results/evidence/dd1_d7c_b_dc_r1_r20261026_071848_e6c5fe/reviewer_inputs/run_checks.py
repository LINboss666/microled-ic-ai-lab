from pathlib import Path
import subprocess,json,concurrent.futures,datetime
root=Path(__file__).parent; repo=root/'repo'; ev='results/evidence/dd1_d7c_b_dc_r20261026_015212_376554'
commands=[
('dc_selftest',['python3','scripts/dd1_d7c_b_dc_run.py','--selftest'],0),
('dc_masters',['python3','scripts/dd1_d7c_b_dc_run.py','--masters'],0),
('dc_plan',['python3','scripts/dd1_d7c_b_dc_run.py','--plan'],0),
('dc_account',['python3','scripts/dd1_d7c_b_dc_run.py','--account',ev+'/launch_account.csv'],0),
('dc_matrix',['python3','scripts/dd1_d7c_b_dc_matrix.py','check',ev],0),
('dc_handoff',['python3','scripts/dd1_d7c_b_dc_record.py','--handoff-check'],0),
('contract',['python3','scripts/dd1_d7c_b_prep_contract.py','--check'],0),
('schedule',['python3','scripts/dd1_d7c_b_prep_schedule.py','--check'],0),
('decks',['python3','scripts/dd1_d7c_b_prep_deckgen.py','--check'],0),
('deck_read',['python3','scripts/dd1_d7c_b_prep_r1_deck_read.py','--check'],0),
('synthetic',['python3','scripts/dd1_d7c_b_prep_cases.py'],0),
('candidate',['python3','scripts/dd1_d7c_a_offline_check.py'],0),
('candidate_guards',['python3','scripts/dd1_d7c_a_guards.py'],0),
('diff_check',['git','diff','--check','e51c5320a28bd5043e21d08a0be97e9d5612cd16..HEAD'],0),
('history',['python3','scripts/precommit_safety_check.py','--mode','history'],0),
('provenance',['python3','scripts/provenance_check.py'],0),
('status',['git','status','--porcelain'],0)]
def one(spec):
 name,cmd,expected=spec
 p=subprocess.run(cmd,cwd=repo,capture_output=True,text=True,timeout=180)
 (root/'checks'/f'{name}.txt').write_text(p.stdout+'\nSTDERR\n'+p.stderr)
 return dict(name=name,argv=cmd,rc=p.returncode,expected_rc=expected,match=p.returncode==expected)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(one,commands))
(root/'checks'/'commands.json').write_text(json.dumps(rows,indent=2))
for row in rows: print(row['name'],row['rc'],row['match'])
