#!/usr/bin/env python3
"""Validate the *structure* of an agent's handoff manifest.

No GitHub access and no execution of project tests. PASS here does not verify
actual push parity, technical results, or the correctness of evidence contents.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SHA = re.compile(r"^[0-9a-fA-F]{40}$")
STATES = {"COMPLETE", "PARTIAL", "BLOCKED"}
PUSH_STATES = {"REMOTE_VERIFIED", "PUSH_PENDING", "REMOTE_UNVERIFIED", "NOT_ATTEMPTED"}
TEST_STATES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "UNVERIFIED"}


def rel_path(value):
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return False
    p = Path(value)
    return not p.is_absolute() and all(part not in {"..", ""} for part in p.parts)


def validate(obj):
    errors = []
    if not isinstance(obj, dict):
        return ["handoff root must be JSON object"]
    for name in ("project_id", "task_id", "repository", "branch", "stop_reason"):
        if not isinstance(obj.get(name), str) or not obj[name].strip():
            errors.append(f"missing or empty field: {name}")
    if obj.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    for name in ("base_sha", "head_sha"):
        if not isinstance(obj.get(name), str) or not SHA.fullmatch(obj[name]):
            errors.append(f"{name} must be a full 40-hex SHA")
    if obj.get("push_status") not in PUSH_STATES:
        errors.append(f"push_status must be one of {sorted(PUSH_STATES)}")
    if obj.get("scope_status") not in STATES:
        errors.append(f"scope_status must be one of {sorted(STATES)}")
    if obj.get("security_gate") not in {"PASS", "FAIL", "NOT_RUN"}:
        errors.append("security_gate must be PASS/FAIL/NOT_RUN")
    if obj.get("push_status") == "REMOTE_VERIFIED" and obj.get("security_gate") != "PASS":
        errors.append("REMOTE_VERIFIED requires security_gate PASS (not proof of parity)")
    tests = obj.get("tests")
    if not isinstance(tests, list) or not tests:
        errors.append("tests must be a nonempty list (use NOT_RUN if necessary)")
    else:
        for i, item in enumerate(tests):
            if not isinstance(item, dict):
                errors.append(f"tests[{i}] must be object")
                continue
            if not isinstance(item.get("name"), str) or not item["name"].strip():
                errors.append(f"tests[{i}].name missing")
            if item.get("status") not in TEST_STATES:
                errors.append(f"tests[{i}].status invalid")
            if item.get("status") == "PASS" and not rel_path(item.get("evidence_path")):
                errors.append(f"tests[{i}]: PASS needs relative evidence_path")
    paths = obj.get("evidence_paths")
    if not isinstance(paths, list) or any(not rel_path(p) for p in paths):
        errors.append("evidence_paths must be a list of relative non-traversing paths")
    if not isinstance(obj.get("known_limitations"), list):
        errors.append("known_limitations must be a list (may be empty)")
    if obj.get("scope_status") == "COMPLETE" and tests and any(isinstance(x, dict) and x.get("status") == "FAIL" for x in tests):
        errors.append("scope_status COMPLETE conflicts with a FAIL test")
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    args = ap.parse_args()
    try:
        obj = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"HANDOFF_STRUCTURE: FAIL — cannot read JSON: {exc}")
        return 2
    problems = validate(obj)
    if problems:
        print("HANDOFF_STRUCTURE: FAIL")
        for issue in problems:
            print(f"- {issue}")
        return 1
    print("HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
