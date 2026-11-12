#!/usr/bin/env python3
"""Read-only PDK ZIP auditor used for environment_audit.md.

Prints only capability conclusions and aggregate counts. It NEVER prints the
full private member list, model-card contents, license addresses, credentials
or a user-directory absolute path into a repository report.

Usage: python checks/pdk_zip_audit.py --zip <pdk archive> [--json <output>]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import zipfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    p = args.zip
    raw = open(p, "rb").read()
    out = {
        "exists": os.path.isfile(p),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    z = zipfile.ZipFile(p)
    infos = z.infolist()
    out["entry_count"] = len(infos)
    out["crc_test"] = z.testzip()  # None means all CRCs verified
    out["total_uncompressed_bytes"] = sum(i.file_size for i in infos)

    bad = []
    for i in infos:
        n = i.filename.replace("\\", "/")
        if (n.startswith("/") or (len(n) > 1 and n[1] == ":")
                or ".." in n.split("/")):
            bad.append("PATH")
        mode = (i.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            bad.append("SYMLINK")
    out["suspicious_entries"] = len(bad)
    out["suspicious_kinds"] = sorted(set(bad))

    names = [i.filename.replace("\\", "/") for i in infos]
    out["top_level_counts"] = dict(collections.Counter(
        (n.split("/")[0] or "<root>") for n in names).most_common(10))
    out["file_entries"] = sum(1 for i in infos if not i.is_dir())

    for key, label in [("smic18", "smic18_hits"), ("tsmc", "tsmc_hits"),
                       ("spectre", "spectre_hits"), ("techfile", "techfile_hits")]:
        out[label] = sum(1 for n in names if key in n.lower())

    # statistical capability scan in memory; contents are never emitted
    pats = {
        "statistics_block": rb"(?im)^\s*statistics\s*\{",
        "process_block": rb"(?im)^\s*process\s*\{",
        "mismatch_block": rb"(?im)^\s*mismatch\s*\{",
        "vary_stmt": rb"(?im)^\s*vary\s+",
    }
    agg = collections.Counter()
    files_with = collections.Counter()
    candidates = [n for n in names if n.startswith("models/")
                  and n.lower().endswith((".mdl", ".lib", ".scs", ".ckt", ".txt"))]
    for n in candidates:
        try:
            b = z.read(n)
        except Exception:
            continue
        if len(b) > 8_000_000:
            continue
        for k, pat in pats.items():
            c = len(re.findall(pat, b))
            if c:
                agg[k] += c
                files_with[k] += 1
    out["model_files_scanned"] = len(candidates)
    out["stat_syntax_hits"] = dict(agg)
    out["stat_syntax_files"] = dict(files_with)
    out["stat_model_verdict"] = (
        "STAT_MODEL_PRESENT" if agg["statistics_block"] or agg["vary_stmt"]
        else "NO_STAT_MODEL_SYNTAX_FOUND")

    print(json.dumps(out, indent=2, ensure_ascii=False))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")


if __name__ == "__main__":
    main()
