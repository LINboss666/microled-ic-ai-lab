#!/usr/bin/env python3
"""Reviewer diagnostics. Offline synthetic/copy mutations only; zero native launches.
rc 0=at least one defect reproduced, 1=all probes refused/detected, 2=instrument error.
Read JSON fields, not rc alone. Published input bytes are never modified.
"""
import argparse,csv,hashlib,json,sys,tempfile,copy,subprocess
from pathlib import Path

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);ap.add_argument('--out',required=True);ap.add_argument('--evidence',default='results/evidence/dd1_d7c_b_dc_r20261026_015212_376554');a=ap.parse_args()
 repo=Path(a.repo).resolve();sys.path.insert(0,str(repo/'scripts'))
 import dd1_d7c_b_dc_run as dc
 import dd1_d7c_b_dc_matrix as matrix
 ev=repo/a.evidence
 rows=list(csv.DictReader((ev/'dc_matrix_dut.csv').open()))
 cases=[]
 # Correct expected behaviour: opposite current is outside the signed band, not an equal current.
 mutated=copy.deepcopy(rows)
 for r in mutated:
  if r['clamp_V']=='0.600':
   r['I_sink_A']=str(-float(r['I_sink_A']));r['I_sink_uA']=str(-float(r['I_sink_uA']))
 answer=dc.judge(mutated)
 bad_bands=[c for c,b in answer.get('band_5_percent',{}).items() if b.get('lowest_verified_V')==0.6]
 cases.append(dict(name='opposite_sign_at_0p60V_counted_inside_signed_5pct_band',defect_reproduced=len(bad_bands)==8,judge_verdict=answer.get('verdict'),bad_band_codes=bad_bands,expected='each 0.60 V point is outside signed +/-5% band; main-point judgement can stay PASS separately'))
 # Direct supported --judge route must not mark an eight-row file as a complete DC matrix.
 mainonly=[r for r in rows if r['clamp_V']=='1.200']
 try:
  answer=dc.judge(mainonly);reproduced=answer.get('verdict')=='PASS'
  fact=dict(verdict=answer.get('verdict'),rows=answer.get('rows'))
 except Exception as e: reproduced=False;fact={'refusal':str(e)}
 cases.append(dict(name='eight_rows_accepted_by_judge_as_PASS',defect_reproduced=reproduced,expected='refuse incomplete 8x19 matrix before PASS',observed=fact))
 # Test the actual extraction entry, not a mock parser; delete named signals from its PSF fixture.
 with tempfile.TemporaryDirectory(prefix='review-dc-') as scratch:
  scratch=Path(scratch);p=scratch/'base.raw';dc.synthetic_psf(str(p),[1.875e-6]*19)
  source=p.read_text()
  # Complete the fixture independently so a repaired extractor cannot reject all cases merely
  # because an unrelated required signal or unit was absent in the older fixture helper.
  source=source.replace('\"data_out\" \"V\"', '\"data_out\" \"V\"\n\"vss\" \"V\"')
  for n in ['pam0','pam1','pam2','iref_in']:
   source=source.replace('\"'+n+'\" \"\"', '\"'+n+'\" \"V\"')
  lines=[]
  for line in source.splitlines():
   lines.append(line)
   if line.startswith('\"data_out\" ') and not line.endswith('\"V\"'):lines.append('\"vss\" 0.000000000000000e+00')
  source='\n'.join(lines)+'\n';p.write_text(source)
  _,decksha=dc.delivered_deck('DC-000')
  positive,_=dc.extract(str(p),decksha,'DC-000','dut','review','DTEST')
  positive_control={'complete_required_signal_fixture_accepted':len(positive)==19}
  for signal,key in [('vdd18','vdd18_V'),('vcas','vcas_V'),('data_en','data_en_V'),('pam0','pam_bits')]:
   raw=scratch/(signal+'.raw');raw.write_text('\n'.join(line for line in source.splitlines() if not line.startswith('"'+signal+'"'))+'\n')
   try:
    answer,info=dc.extract(str(raw),decksha,'DC-000','dut','review','DTEST')
    reproduced=True;fact={'rows':len(answer),'substituted_or_marked_value':answer[0].get(key),'code':answer[0].get('code')}
   except dc.Refuse as e:
    reproduced=signal not in str(e);fact={'refusal':str(e),'named_expected_missing_signal':signal in str(e)}
   cases.append(dict(name='missing_required_'+signal+'_accepted_by_extraction',defect_reproduced=reproduced,expected='refuse missing measured signal; never substitute contract nominal or case-name bits',observed=fact))
 # Independent whole-source identity comparison: captured recorder success is not this check.
 mismatches=[]
 for r in csv.DictReader((ev/'source_identity.csv').open()):
  blob=subprocess.check_output(['git','-C',str(repo),'show','HEAD:'+r['path']])
  if len(blob)!=int(r['bytes']) or hashlib.sha256(blob).hexdigest()!=r['sha256']:mismatches.append(r['path'])
 cases.append(dict(name='published_source_identity_does_not_match_committed_blobs',defect_reproduced=bool(mismatches),mismatches=mismatches,expected='all published identities equal delivered Git bytes or explicitly mark stale historical record and publish a current replacement'))
 payload={'instrument':'probe_dc_review_gaps.py','native_launches':0,'published_bytes_modified':False,'positive_control':positive_control,'cases':cases,'reproduced_count':sum(x['defect_reproduced'] for x in cases),'any_defect_reproduced':any(x['defect_reproduced'] for x in cases)}
 Path(a.out).write_text(json.dumps(payload,indent=2));print(json.dumps(payload,indent=2));return 0 if payload['any_defect_reproduced'] else 1
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:print('INSTRUMENT_ERROR:',repr(e));sys.exit(2)
