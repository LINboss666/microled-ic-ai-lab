#!/usr/bin/env python3
"""test_safety_rules.py -- prove the gate fires on real secrets and stays quiet on prose.

A safety gate is worthless without a test of both directions, so this file pins:
  * every MUST-catch shape (real credential, vendor model card, forbidden path)
  * every MUST-NOT-catch shape (technical prose about credentials, shell `pwd=`,
    printf formats, placeholder values) -- these are the false positives that would
    otherwise get the gate disabled by annoyance.

Run: python scripts/test_safety_rules.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402

MUST_SECRET = [
    # Every fixture is built by concatenation. Written as a literal it would be a
    # real-shaped secret sitting in a tracked file, and the scanner would then block
    # its own test -- the fastest way for a safety gate to get disabled by annoyance.
    ("db_" + "password" + " = s3cretValue42", "password_assignment"),
    ("passwd" + ": Hunter2-Workstation", "password_assignment"),
    ("ghp_" + "A" * 23, "github_token"),
    ("github_pat_11" + "ABCDEFGH0123456789abcdefghij", "github_fine_grained"),
    ("-----BEGIN " + "RSA PRIVATE KEY-----", "ssh_private_key_block"),
    ("export LMD_LICENSE_FILE" + "=27020@licserver.corp", "license_server_value"),
    ("AKIA" + "IOSFODNN7EXAMPLE", "aws_key_id"),
]
MUST_NOT_SECRET = [
    'the guest ' + 'password' + ' is never committed to this repository',
    'grep -aE "VIRTUOSO_NOGRAPH|engine=|home=|pw' + 'd=" $LOG',
    'pri' + 'ntf("pw' + 'd=%s\\n"     qSv("PWD"))',
    'PASS' + 'WORD=<placeholder-from-user>',
    'PASS' + 'WORD = %s',
    'no ' + 'password' + ' stored; key authentication only',
    'QODER_GUEST_PW is read from the ignored credentials file at runtime',
]
MUST_VENDOR = [
    (".MOD" + "EL NMOS LVL=49", "spice_model_card"),
    ("+ " + "VTH0" + "=0.4 K1=0.5", "model_param_line"),
    ("DRC " + "SECTION 1", "calibre_deck_section"),
    ("LVS " + "SECTION", "calibre_deck_section"),
]
MUST_NOT_VENDOR = [
    'BSIM4 models are used; the model card itself is not committed',
    'VTH' + '0 is a threshold parameter -- we do not reproduce vendor values here',
]
MUST_PATH = [
    ("pdk/" + "smic18mmrf_teacher/models/spectre/x.lib", "pdk"),
    ("/root/microled_ai_project/pdk/" + "smic18mmrf_teacher/models/spectre/y.scs", "pdk"),
    (".ic617_agent_bridge_" + "credentials", "credentials"),
    ("id_rs" + "a_ic617", "key"),
    ("pdk_compare/" + "zip_manifest.json", "manifest"),
    ("course_source/" + "spec_v12_text.md", "course"),
    ("spectre/sim/run_ff1_fast.raw/" + "tr1.tran.tran", "sim-output"),
    ("spectre/" + "pdk_local.env", "local-config"),
    ("techfile/" + "dfI.map", "techfile"),
    ("models/" + "spectre/card.scs", "models"),
]
MUST_NOT_PATH = [
    "spectre/" + "C2MOS_DFF.scs",
    "spectre/" + "c2mos_ff1_func.scs",
    "scripts/" + "precommit_safety_check.py",
    "results/evidence/" + "c2mos_assert_ff1_envtest_1.txt",
    "spec/" + "system_requirements.md",
    "reports/" + "pdk_inventory.md",
    "model_probe/model_probe_" + "mmrf_teacher_1v8.scs",
    # the committed template must not be mistaken for the ignored local config
    "spectre/" + "pdk_local.env.example",
]

fails = []


def check(cond, label):
    if not cond:
        fails.append(label)


for text, rule in MUST_SECRET:
    hits = [n for n, _ in R.secrets_in(text)]
    check(rule in hits, "MUST catch secret %s -> got %s" % (rule, hits))
for text in MUST_NOT_SECRET:
    hits = [n for n, _ in R.secrets_in(text)]
    check(not hits, "MUST NOT fire on: %s -> got %s" % (text[:48], hits))
for text, rule in MUST_VENDOR:
    hits = [n for n, _ in R.content_denied(text)]
    check(rule in hits, "MUST catch vendor %s -> got %s" % (rule, hits))
for text in MUST_NOT_VENDOR:
    hits = [n for n, _ in R.content_denied(text)]
    check(not hits, "MUST NOT fire vendor: %s -> got %s" % (text[:48], hits))
for path, why in MUST_PATH:
    check(R.path_denied(path) is not None, "MUST block path %s (%s)" % (path, why))
for path in MUST_NOT_PATH:
    check(R.path_denied(path) is None, "MUST NOT block path %s -> %s" % (path, R.path_denied(path)))

print("safety_rules cases: secret=%d/%d vendor=%d/%d path=%d/%d" % (
    len(MUST_SECRET), len(MUST_SECRET), len(MUST_VENDOR), len(MUST_VENDOR),
    len(MUST_PATH), len(MUST_PATH)))
if fails:
    for f in fails:
        print("FAIL " + f)
    print("SAFETY_RULES_TEST: FAIL (%d)" % len(fails))
    sys.exit(1)
print("SAFETY_RULES_TEST: PASS")
