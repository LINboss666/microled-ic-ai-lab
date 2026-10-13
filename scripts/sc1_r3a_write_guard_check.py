#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R3A: a refusal must not be able to rewrite delivered evidence.

    python scripts/sc1_r3a_write_guard_check.py            # both entries
    python scripts/sc1_r3a_write_guard_check.py r3 s3b     # named entries

Two checks per entry, both inside a fresh temporary directory, neither of which calls anything but
python:

  1. pre-seed cases/manifest/samples/(identity)/log with sentinel data rows, hash them, then invoke
     the entry for a real (non-dry) case WITHOUT RUN / QODER_SIM_AUTHORISED. The entry must return 5
     AND all hashes must still match, AND no sim/ directory may appear (the runner never ran). This is
     the regression that R3A exists for: before the fix the same invocation wrote back an empty
     manifest and an empty samples file, which is how two delivered CSVs reached the repository as
     headers only.
  2. run the same entry with --dry and NO --out, pointed at an isolated scratch, and require that the
     dry rows land inside that scratch and the seeded official-format files are untouched.

It is deliberately small: a handful of files, one unknown-id call and one wrong-count call, no mock
matrix and no new framework. S3-B joined because it is a new entry with the same write paths, not
because the harness needed rewriting.
"""
from __future__ import print_function

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

SENTINEL = {
    'cases.csv': ['run_id,item,case,signal_or_target,expected,actual,rc,verdict,note',
                  'SENTINEL-BATCH,R3_WINDOW_STATE,r3_q0_off,gate33,high,min=3.3,max=3.3 V,0,PASS,'
                  'pre-seeded data, must survive'],
    'sc1_r3_chain_manifest.csv': ['run_id,case,deck,deck_sha256,cell_sha256_16,section,temp_C,'
                                  'rails_V,load_pF,analysis,preflight_rc,spectre_rc,runner_verdict,'
                                  'saved_signals,window_rows,state_verdict',
                                  'SENTINEL-BATCH,r3_q0_off,r3_q0_off.scs,deadbeef,cafe,tt,27,'
                                  '1.8/3.3,1,tran,0,0,PASS,time,10,PASS'],
    'sc1_r3_waveform_samples.csv': ['case,event,kind,sample_group_index,time_s,values,status,'
                                    'deck_sha256,raw_sha256',
                                    'r3_q0_off,priming_two_rising_edges,initialisation_crossing,42,'
                                    '1.5e-07,clk=0.9,MEASURED,deadbeef,cafebabe'],
    'dependency_log.txt': ['=== SENTINEL run accepted', 'runner: SPECTRE name=r3_q0_off.scs rc=0'],
}

# the same harness pointed at the S3-B entry: one refusal path is worth checking per entry, not per
# round, and the S3-B entry writes four official files plus the log
SENTINEL_S3B = {
    'cases.csv': ['run_id,item,case,signal_or_target,expected,actual,rc,verdict,note',
                  'SENTINEL-BATCH,S3B_WINDOW_STATE,s3b_q0_off_light,Xtop.gate33,high,'
                  'min=3.3,max=3.3 V,0,PASS,pre-seeded data, must survive'],
    'sc1_s3b_manifest.csv': ['run_id,case,deck,deck_sha256,top_master,cell_sha256_16,section,'
                             'temp_written,temp_read_back,rails_V,load_R_ohm,load_C_F,analysis,'
                             'preflight_static_rc,preflight_rc,spectre_rc,runner_verdict,refusal_rows,'
                             'device_count,gate_current_names,saved_traces,window_rows,state_verdict',
                             'SENTINEL-BATCH,s3b_q0_off_light,s3b_q0_off_light.scs,deadbeef,'
                             'sc1_s3b_scan_power_1ch,cafe,tt,27,psf=27.0000,3.3/3.3/1.8,220000,1e-12,'
                             'tran,0,0,0,PASS,0,39,iprobe,time,12,PASS'],
    'sc1_s3b_waveform_samples.csv': ['case,event,kind,sample_group_index,time_s,values,status,'
                                     'deck_sha256,raw_sha256',
                                     's3b_q0_off_light,priming_two_rising_edges,'
                                     'initialisation_crossing,42,1.5e-07,gate33=3.3,MEASURED,'
                                     'deadbeef,cafebabe'],
    'sc1_s3b_identity.csv': ['run_id,case,deck_relpath,deck_sha256,raw_relpath,raw_sha256,'
                             'lib_sha256,mdl_sha256,readme_sha256,mis_sha256,geometry_source,'
                             'provenance',
                             'SENTINEL-BATCH,s3b_q0_off_light,deck.scs,deadbeef,raw,cafebabe,'
                             'a' * 64, 'b' * 64, 'c' * 64, 'd' * 64, 'model record', 'sentinel'],
    'dependency_log.txt': ['=== SENTINEL run accepted',
                           'runner: SPECTRE name=s3b_q0_off_light.scs rc=0'],
}

ENTRIES = {
    'r3': dict(script='sc1_r3_chain_tt.py', sentinel=SENTINEL, token='R3_TT_REFUSED',
               case='r3_q0_off', would='would_have_been=r3_q0_off'),
    's3b': dict(script='sc1_s3b_chain_power_tt.py', sentinel=SENTINEL_S3B, token='S3B_REFUSED',
                case='s3b_q0_off_light', would='would_have_been=s3b_q0_off_light'),
}
FILES = sorted(SENTINEL)


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def seed(dirpath, sentinel):
    for name, lines in sentinel.items():
        with open(os.path.join(dirpath, name), 'wb') as f:
            f.write(('\n'.join(lines) + '\n').encode('utf-8'))
    return dict((n, sha(os.path.join(dirpath, n))) for n in sorted(sentinel))


def run(entry_path, env_extra, args, workdir):
    env = dict(os.environ)
    for k in ('RUN', 'QODER_SIM_AUTHORISED'):
        env.pop(k, None)
    env.update(env_extra)
    p = subprocess.Popen([sys.executable, entry_path] + args, env=env,
                         cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.read().decode('utf-8', 'replace')
    p.wait()
    return p.returncode, out


def check(name, ok, detail):
    print('   %-58s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))
    return bool(ok)


def one_entry(key, base):
    e = ENTRIES[key]
    entry = os.path.join(HERE, e['script'])
    files = sorted(e['sentinel'])
    ev = os.path.join(base, key, 'evidence')
    sc = os.path.join(base, key, 'scratch')
    os.makedirs(ev)
    os.makedirs(sc)
    checks = []
    official = ['--out', os.path.join(ev, 'cases.csv'),
                '--manifest', os.path.join(ev, [f for f in files if 'manifest' in f][0]),
                '--samples', os.path.join(ev, [f for f in files if 'samples' in f][0]),
                '--log', os.path.join(ev, 'dependency_log.txt')]
    if 'identity' in ' '.join(files):
        official += ['--identity', os.path.join(ev, [f for f in files if 'identity' in f][0])]
    before = seed(ev, e['sentinel'])
    args = ['--only', e['case']] + official + ['--scratch', sc]
    rc, out = run(entry, {}, args, base)
    after = dict((n, sha(os.path.join(ev, n))) for n in files)
    changed = [n for n in files if before[n] != after[n]]
    checks.append(check('%s: unauthorised real run returns 5' % key, rc == 5, 'rc=%s' % rc))
    checks.append(check('%s: the refusal is printed, not stored over a record' % key,
                        e['token'] in out and e['would'] in out,
                        'first line: %s' % out.strip().split('\n')[0][:60]))
    checks.append(check('%s: every evidence file byte-identical after the refusal' % key,
                        not changed, 'changed=%s' % (','.join(changed) or 'none')))
    simdir = os.path.join(sc, 'sim')
    logs = [d for d in os.listdir(simdir)] if os.path.isdir(simdir) else []
    checks.append(check('%s: no runner was invoked (no sim/ artifacts appear)' % key, not logs,
                        'sim/=%s' % (','.join(sorted(logs))[:60] or 'absent')))

    # dry must stay inside the scratch it was given
    rc2, out2 = run(entry, {}, ['--dry', '--only', e['case'], '--scratch', sc], base)
    dry_csv = os.path.join(sc, 'dry_rows.csv')
    checks.append(check('%s: dry without --out writes only inside the scratch' % key,
                        rc2 == 0 and os.path.isfile(dry_csv),
                        'rc=%s dry_rows=%s' % (rc2, os.path.isfile(dry_csv))))
    after2 = dict((n, sha(os.path.join(ev, n))) for n in files)
    changed2 = [n for n in files if before[n] != after2[n]]
    checks.append(check('%s: the official-format files are untouched after the dry build' % key,
                        not changed2, 'changed=%s' % (','.join(changed2) or 'none')))

    # the two selection refusals still return BEFORE any write
    for extra, want in ((['--only', 'no_such_case'], 9), (['--expect', '3'], 9)):
        rc3, out3 = run(entry, {}, extra + official + ['--scratch', sc], base)
        checks.append(check('%s: %s %s still refuses with rc %d' % (key, extra[0], extra[1], want),
                            rc3 == want, 'rc=%s' % rc3))
    after3 = dict((n, sha(os.path.join(ev, n))) for n in files)
    changed3 = [n for n in files if before[n] != after3[n]]
    checks.append(check('%s: a bad selection also leaves every evidence file identical' % key,
                        not changed3, 'changed=%s' % (','.join(changed3) or 'none')))
    return checks


def main():
    which = [a for a in sys.argv[1:] if a in ENTRIES] or ['r3', 's3b']
    base = tempfile.mkdtemp(prefix='r3a_guard_')
    checks = []
    try:
        for key in which:
            checks.extend(one_entry(key, base))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    bad = [c for c in checks if not c]
    print('R3A_WRITE_GUARD checks=%d failures=%d entries=%s (isolated temporary directory; no '
          'simulator, no preflight, no circuit claim)'
          % (len(checks), len(bad), ','.join(which)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
