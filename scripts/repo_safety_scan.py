#!/usr/bin/env python3
"""repo_safety_scan.py -- classify the working tree before any `git init`.

    python scripts/repo_safety_scan.py                 # classify the repo root
    python scripts/repo_safety_scan.py --show-reasons  # default
    python scripts/repo_safety_scan.py --json

Buckets:
    SAFE_TO_TRACK   our own authored content, no deny rule fired
    MUST_IGNORE     a path/content rule fired: PDK, deck, credential, key, bulk sim
                    output, archive, or actual vendor model text
    NEEDS_REVIEW    not blocked, but a human should look: a PDK name appearing in
                    prose, an unknown extension, or a file over 200 KB

This is a report, not a gate: exit status is 0 unless --fail-on-ignore is given.
The gate is scripts/precommit_safety_check.py.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    fail_on_ignore = "--fail-on-ignore" in args
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for i, a in enumerate(args):
        if a == "--root" and i + 1 < len(args):
            root = os.path.abspath(args[i + 1])

    buckets = {"SAFE_TO_TRACK": [], "MUST_IGNORE": [], "NEEDS_REVIEW": []}
    for full, rel in R.walk_root(root):
        info = R.classify_file(full, rel)
        buckets[info["bucket"]].append((rel, info["reasons"]))

    if as_json:
        print(json.dumps({k: [{"path": p, "reasons": r} for p, r in v]
                          for k, v in buckets.items()}, indent=1))
    else:
        for name in ("MUST_IGNORE", "NEEDS_REVIEW", "SAFE_TO_TRACK"):
            lst = buckets[name]
            print("== %s: %d" % (name, len(lst)))
            for rel, reasons in sorted(lst):
                print("   %-56s %s" % (rel, ";".join(reasons) if reasons else ""))
        print("SUMMARY total=%d safe=%d ignore=%d review=%d" % (
            sum(len(v) for v in buckets.values()),
            len(buckets["SAFE_TO_TRACK"]), len(buckets["MUST_IGNORE"]),
            len(buckets["NEEDS_REVIEW"])))
    if fail_on_ignore and buckets["MUST_IGNORE"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
