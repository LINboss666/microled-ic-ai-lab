#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_validate_handoff.py -- structural gate for DATA-7C-A.json, plus on-disk digest checks.

The frozen DATA-7B validator cannot be extended this round (shared validator, out of scope), so this
new tool checks the DATA-7C-A handoff against its own documented structure. It verifies fields and
bytes; it does NOT verify remote truth or any electrical claim, and it says so in its own output line.

Rules that exist because of a real finding in an earlier round:
  * an identity field may not be blank or shorter than a full SHA;
  * every source_identity entry must equal the bytes on disk right now, so a handoff cannot cite a
    file it did not read;
  * costs must be integers and must be 0, because this round authorises no launch;
  * anything under `not_run` must be one of the honest markers, never a number;
  * no field may say the eight levels are measured or implemented as PASS.
"""

from __future__ import absolute_import, division, print_function

import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHA_RX = re.compile(r'^[0-9a-f]{40}$')          # a Git object id
DIGEST_RX = re.compile(r'^[0-9a-f]{64}$')      # a SHA-256 file digest
MARKERS = ('NOT_RUN', 'NOT_VERIFIED', 'NOT_DEFINED', 'NOT_FROZEN', 'NOT_AUTHORISED',
           'PENDING_INDEPENDENT_REVIEW')
REQUIRED = ('schema_version', 'task_id', 'base_sha', 'accepted_data7b_content_sha', 'branch',
            'repository', 'scope', 'completion_level', 'source_identity', 'candidate',
            'offline_verification', 'native_plan', 'costs', 'boundaries', 'not_run',
            'stop_reason', 'known_limitations', 'remote_readback', 'head_sha_role')
# a repair round names the tip it repairs, and the review it answers, instead of editing the
# first round's fields into the shape of a passing answer
REPAIR_REQUIRED = ('repair_of', 'repair_baseline_sha', 'review_input', 'evidence_dir',
                   'path_counts')
TASK_IDS = ('DATA-7C-A', 'DATA-7C-A-R1')
ELECTRICAL_FORBIDDEN = ('PAM_IMPLEMENTED=PASS', 'CURRENT_MEASURED=PASS', 'MEASURED_PASS')


def sha256(path):
    with io.open(path, 'rb') as handle:
        return __import__('hashlib').sha256(handle.read()).hexdigest()


def validate(payload, root=ROOT):
    problems = []
    for key in REQUIRED:
        if key not in payload:
            problems.append('missing field %s' % key)
    for key in ('base_sha', 'accepted_data7b_content_sha'):
        value = payload.get(key, '')
        if not SHA_RX.match(str(value)):
            problems.append('%s is not a full 40-hex SHA: %r' % (key, value))
    if payload.get('task_id') not in TASK_IDS:
        problems.append('task_id must be one of %s, found %r' % (TASK_IDS, payload.get('task_id')))
    if str(payload.get('task_id', '')).endswith('-R1'):
        for key in REPAIR_REQUIRED:
            if key not in payload:
                problems.append('a repair round must carry %s' % key)
        if not SHA_RX.match(str(payload.get('repair_baseline_sha', ''))):
            problems.append('repair_baseline_sha is not a full 40-hex SHA')
        review = payload.get('review_input') or {}
        instrument = review.get('instrument') or {}
        if instrument.get('modified_by_this_round') != 'NO':
            problems.append('the reviewer instrument must be recorded as unmodified')
        if not DIGEST_RX.match(str(instrument.get('sha256', ''))):
            problems.append('review_input.instrument.sha256 is not a 64-hex SHA-256 digest')
        if not DIGEST_RX.match(str(review.get('sha256', ''))):
            problems.append('review_input.sha256 (the review package) is not a 64-hex digest')
    identity = payload.get('source_identity') or {}
    for entry in identity.get('delivered', []) + identity.get('read_only_inputs', []):
        for field in ('path', 'sha256', 'bytes'):
            if field not in entry:
                problems.append('source_identity entry without %s: %r' % (field, entry))
        path = os.path.join(root, str(entry.get('path', '')).replace('/', os.sep))
        if not os.path.isfile(path):
            problems.append('source_identity names a file that is not on disk: %s' % entry.get('path'))
            continue
        if entry.get('sha256') != sha256(path):
            problems.append('%s digest in the handoff does not match the bytes on disk'
                            % entry.get('path'))
        if int(entry.get('bytes', -1)) != os.path.getsize(path):
            problems.append('%s byte count in the handoff does not match the bytes on disk'
                            % entry.get('path'))
    costs = payload.get('costs') or {}
    for key in ('new_spectre_launches', 'new_rtl_simulations', 'new_oa_writes'):
        value = costs.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            problems.append('costs.%s must be an integer, found %r' % (key, value))
        elif value != 0:
            problems.append('costs.%s must be 0 this round, found %r' % (key, value))
    for key, value in (payload.get('not_run') or {}).items():
        if value not in MARKERS:
            problems.append('not_run.%s must be one of %s, found %r' % (key, ','.join(MARKERS), value))
    blob = json.dumps(payload, ensure_ascii=False)
    for forbidden in ELECTRICAL_FORBIDDEN:
        if forbidden in blob:
            problems.append('the handoff contains the forbidden electrical claim %r' % forbidden)
    if (payload.get('native_plan') or {}).get('cases') != 15:
        problems.append('native_plan.cases must stay 15 while nothing is authorised')
    if (payload.get('native_plan') or {}).get('authorised_this_round') != 0:
        problems.append('native_plan.authorised_this_round must be 0')
    if (payload.get('candidate') or {}).get('levels_status') != 'POC_CANDIDATE_NOT_FORMAL_SPEC':
        problems.append('candidate.levels_status must stay POC_CANDIDATE_NOT_FORMAL_SPEC')
    if not payload.get('known_limitations'):
        problems.append('known_limitations must not be empty')
    return problems


def main(argv):
    path = argv[0] if argv else os.path.join('reports', 'agent_handoffs', 'DATA-7C-A.json')
    absolute = path if os.path.isabs(path) else os.path.join(ROOT, path)
    payload = json.loads(io.open(absolute, encoding='utf-8').read())
    problems = validate(payload)
    for line in problems[:20]:
        print('  PROBLEM ' + line)
    print('D7C_A_HANDOFF_CHECK: %s (%d base fields%s, %d problems; evidence and remote truth are '
          'NOT verified here)' % ('PASS' if not problems else 'FAIL', len(REQUIRED),
                                  '+%d repair fields' % len(REPAIR_REQUIRED)
                                  if str(payload.get('task_id', '')).endswith('-R1') else '',
                                  len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
