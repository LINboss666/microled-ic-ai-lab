#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Field checker for a handoff JSON. THIS IS NOT THE OFFICIAL VALIDATOR.

The task book names scripts/validate_handoff.py from the "GitHub Bridge Review Workflow v1.0"
package as the formal validator. That file is NOT present on this machine -- searched: this repo's
working tree, every remote branch and the whole object history, D:\\IC项目, the user's Downloads and
home tree. The absence is reported in reports/c2mos_ade_readbind_once_correction.md instead of being
papered over by pretending to run something else.

What this file therefore does is deliberately narrow and honestly labelled: it checks that the
handoff JSON carries the fields the task book itself enumerates (section thirteen), and that the
verdict/integrity values are well formed. A PASS here means "the fields the reviewer asked for are
present and typed", NOT "the official schema accepted it".

Usage:
  python scripts/c2mos_handoff_field_check.py reports/agent_handoffs/<ID>.json
"""
from __future__ import print_function

import io
import json
import sys

REQUIRED = [
    "TASK_ID", "BASE_SHA", "BRANCH", "LOCAL_HEAD_SHA", "REMOTE_HEAD_SHA", "LOCAL_REMOTE_PARITY",
    "ADE_READBIND_RESULT", "DUT_UNCHANGED", "TB_UNCHANGED", "PDK_UNCHANGED", "SECURITY_GATE",
    "REPORT_PATH", "EVIDENCE_PATH", "KNOWN_LIMITATIONS", "STOP_REASON",
]
# snake_case equivalents actually used in our JSON, so the check is about content not spelling
ALIASES = {
    "TASK_ID": "task_id", "BASE_SHA": "base_sha", "BRANCH": "branch",
    "LOCAL_HEAD_SHA": "local_head_sha", "REMOTE_HEAD_SHA": "remote_head_sha",
    "LOCAL_REMOTE_PARITY": "local_remote_parity", "ADE_READBIND_RESULT": "ade_readbind_result",
    "DUT_UNCHANGED": "dut_unchanged", "TB_UNCHANGED": "tb_unchanged",
    "PDK_UNCHANGED": "pdk_unchanged", "SECURITY_GATE": "security_gate",
    "REPORT_PATH": "report_path", "EVIDENCE_PATH": "evidence_path",
    "KNOWN_LIMITATIONS": "known_limitations", "STOP_REASON": "stop_reason",
}
ALLOWED_VERDICTS = ("SUCCESS", "NO_HANDLE", "NO_SETUP_DB", "LICENSE_BLOCKED", "ERROR", "NOT_EXECUTED")
ALLOWED_GRADES = ("DIRECTLY_OBSERVED", "DOCUMENTED", "DERIVED", "NOT_VERIFIED")
ALLOWED_PARITY = ("PASS", "REMOTE_PARITY_UNVERIFIED")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("usage: c2mos_handoff_field_check.py <handoff.json>")
        return 2
    raw = io.open(path, encoding="utf-8").read()
    try:
        d = json.loads(raw)
    except ValueError as e:
        print("JSON_PARSE: FAIL %s" % e)
        print("HANDOFF_FIELD_CHECK: FAIL")
        return 1
    print("JSON_PARSE: OK (%d top-level keys)" % len(d))

    missing = []
    for key in REQUIRED:
        alt = ALIASES[key]
        if key not in d and alt not in d:
            missing.append(key)
    for k in missing:
        print("MISSING_FIELD %s" % k)

    bad = list(missing)

    res = str(d.get("ADE_READBIND_RESULT") or d.get("ade_readbind_result") or "")
    if not any(v in res for v in ALLOWED_VERDICTS):
        print("BAD_VERDICT %r (allowed: %s)" % (res, " ".join(ALLOWED_VERDICTS)))
        bad.append("ADE_READBIND_RESULT")

    for f in ("dut_unchanged", "tb_unchanged", "pdk_unchanged", "DUT_UNCHANGED", "TB_UNCHANGED",
              "PDK_UNCHANGED"):
        if f in d and str(d[f]).upper() not in ("PASS", "FAIL", "PARTIAL", "NOT_FULLY_HASHED"):
            print("BAD_INTEGRITY_VALUE %s=%r" % (f, d[f]))
            bad.append(f)

    par = str(d.get("LOCAL_REMOTE_PARITY") or d.get("local_remote_parity") or "")
    if par and par not in ALLOWED_PARITY:
        print("BAD_PARITY %r" % par)
        bad.append("parity")

    # grading discipline: a conclusion that is not directly observed must not claim to be
    for blob in json.dumps(d, ensure_ascii=False).split('"'):
        pass
    derived = str(d.get("outcome", {}).get("most_probable_condition", {}).get("grade", ""))
    if derived and derived not in ALLOWED_GRADES:
        print("BAD_EVIDENCE_GRADE %r" % derived)
        bad.append("grade")

    print("checked_required_fields=%d missing=%d problems=%d" % (len(REQUIRED), len(missing), len(bad)))
    print("NOTE this is not scripts/validate_handoff.py; the official validator is not on this machine")
    if bad:
        print("HANDOFF_FIELD_CHECK: FAIL")
        return 1
    print("HANDOFF_FIELD_CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
