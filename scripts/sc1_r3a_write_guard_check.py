#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R3A: a refusal must not be able to rewrite delivered evidence.

    python scripts/sc1_r3a_write_guard_check.py

Two checks, both inside a fresh temporary directory, neither of which calls anything but python:

  1. pre-seed cases/manifest/samples/log with sentinel data rows, hash them, then invoke
     `sc1_r3_chain_tt.py` for a real (non-dry) case WITHOUT RUN / QODER_SIM_AUTHORISED. The entry must
     return 5 AND all four hashes must still match, AND no sim/ directory may appear (the runner never
     ran). This is the regression that R3A exists for: before the fix the same invocation wrote back
     an empty manifest and an empty samples file, which is how two delivered CSVs reached the
     repository as headers only.
  2. run the same entry with --dry and NO --out, pointed at an isolated scratch, and require that the
     dry rows land inside that scratch and the seeded official-format cases file is untouched.

It is deliberately small: three files plus a log, one unknown-id call and one wrong-count call, no
mock matrix and no new framework.
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
ENTRY = os.path.join(HERE, 'sc1_r3_chain_tt.py')

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
FILES = sorted(SENTINEL)


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def seed(dirpath):
    for name, lines in SENTINEL.items():
        with open(os.path.join(dirpath, name), 'wb') as f:
            f.write(('\n'.join(lines) + '\n').encode('utf-8'))
    return dict((n, sha(os.path.join(dirpath, n))) for n in FILES)


def run(env_extra, args, workdir):
    env = dict(os.environ)
    for k in ('RUN', 'QODER_SIM_AUTHORISED'):
        env.pop(k, None)
    env.update(env_extra)
    p = subprocess.Popen([sys.executable, ENTRY] + args, env=env, cwd=workdir,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.read().decode('utf-8', 'replace')
    p.wait()
    return p.returncode, out


def check(name, ok, detail):
    print('   %-58s %s  %s' % (name, 'PASS' if ok else 'FAIL', detail))
    return bool(ok)


def main():
    base = tempfile.mkdtemp(prefix='r3a_guard_')
    ev = os.path.join(base, 'evidence')
    sc = os.path.join(base, 'scratch')
    os.makedirs(ev)
    os.makedirs(sc)
    checks = []
    try:
        before = seed(ev)
        args = ['--only', 'r3_q0_off',
                '--out', os.path.join(ev, 'cases.csv'),
                '--manifest', os.path.join(ev, 'sc1_r3_chain_manifest.csv'),
                '--samples', os.path.join(ev, 'sc1_r3_waveform_samples.csv'),
                '--log', os.path.join(ev, 'dependency_log.txt'),
                '--scratch', sc]
        rc, out = run({}, args, base)
        after = dict((n, sha(os.path.join(ev, n))) for n in FILES)
        changed = [n for n in FILES if before[n] != after[n]]
        checks.append(check('unauthorised real run returns 5', rc == 5, 'rc=%s' % rc))
        checks.append(check('the refusal is printed, not stored over a record',
                            'R3_TT_REFUSED' in out and 'would_have_been=r3_q0_off' in out,
                            'first line: %s' % out.strip().split('\n')[0][:60]))
        checks.append(check('all four evidence files byte-identical after the refusal',
                            not changed, 'changed=%s' % (','.join(changed) or 'none')))
        simdir = os.path.join(sc, 'sim')
        logs = [d for d in os.listdir(simdir)] if os.path.isdir(simdir) else []
        checks.append(check('no runner was invoked (no sim/ artifacts appear)', not logs,
                            'sim/=%s' % (','.join(sorted(logs))[:60] or 'absent')))

        # 2 -- dry must stay inside the scratch it was given
        rc2, out2 = run({}, ['--dry', '--only', 'r3_q0_off', '--scratch', sc], base)
        dry_csv = os.path.join(sc, 'dry_rows.csv')
        checks.append(check('dry without --out writes only inside the scratch', rc2 == 0 and
                            os.path.isfile(dry_csv), 'rc=%s dry_rows=%s' % (rc2,
                                                                            os.path.isfile(dry_csv))))
        after2 = dict((n, sha(os.path.join(ev, n))) for n in FILES)
        changed2 = [n for n in FILES if before[n] != after2[n]]
        checks.append(check('the official-format files are still untouched after the dry build',
                            not changed2, 'changed=%s' % (','.join(changed2) or 'none')))

        # 3 -- the two refusal codes still refuse BEFORE writing anything
        for extra, want in ((['--only', 'no_such_case'], 9), (['--expect', '3'], 9)):
            rc3, out3 = run({}, extra + ['--out', os.path.join(ev, 'cases.csv'),
                                         '--manifest', os.path.join(ev, 'sc1_r3_chain_manifest.csv'),
                                         '--samples', os.path.join(ev, 'sc1_r3_waveform_samples.csv'),
                                         '--log', os.path.join(ev, 'dependency_log.txt'),
                                         '--scratch', sc], base)
            checks.append(check('%s still refuses with rc %d' % (extra[0] + ' ' + extra[1], want),
                                rc3 == want, 'rc=%s' % rc3))
        after3 = dict((n, sha(os.path.join(ev, n))) for n in FILES)
        changed3 = [n for n in FILES if before[n] != after3[n]]
        checks.append(check('a bad selection also leaves every evidence file identical',
                            not changed3, 'changed=%s' % (','.join(changed3) or 'none')))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    bad = [c for c in checks if not c]
    print('R3A_WRITE_GUARD checks=%d failures=%d (isolated temporary directory; no simulator, '
          'no preflight, no circuit claim)' % (len(checks), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
