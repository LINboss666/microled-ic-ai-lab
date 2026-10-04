#!/usr/bin/env python3
"""Shared safety rules for this repository: PDK and secret detection.

One rule source, two consumers:
  scripts/repo_safety_scan.py        -- classify the working tree (three buckets)
  scripts/precommit_safety_check.py  -- refuse a commit / refuse a push

Design notes
------------
* PATH rules are what enforce "no PDK in history". Content rules are a backstop for
  a vendor file renamed into an allowed directory.
* `.gitignore` alone is NOT a gate (it only hides files from `git status`), so every
  rule here is applied to the actual staged blob, and again to the whole history
  before a push.
* Secret matching is shape-based, on purpose: a line like
  "the password is never committed" must not fire, while `password = ab12xy` must.
  Nothing here ever prints a matched value -- only path, rule name and line number.
"""

import os
import re

# ---------------------------------------------------------------- path rules ----
# Anything matching these is NEVER allowed to be tracked, in any commit.
DENY_PATH = [
    # foundry / instructor PDK and its deliverables
    "pdk/*", "*/pdk/*", "**/pdk/*",
    "smic18mmrf_teacher/*", "*/smic18mmrf_teacher/*",
    "*/*smic18mmrf_teacher*/*",
    "models/*", "*/models/*",
    "techfile/*", "*/techfile/*",
    "*.lib", "*.vloga", "*.vams",
    "cds.lib", "lib.defs", "cdsinfo.*", "*.oax", "*.oa",
    "*.rvc", "*.svrf", "*.layermap", "*.tech",
    # OA library internals (schematic/layout/symbol directories of a design lib)
    "*/layout/*", "*/symbol/*", "*/celledit/*",
    # credentials and keys
    ".ic617_agent_bridge_credentials", "*credentials*",
    "*.pem", "*.key", "*.ppk", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    "known_hosts*", "authorized_keys", "*.netrc",
    ".env", ".env.*", "*_token*", "*secret*",
    # local machine configuration that points at a PDK
    "*/pdk_local.env", "pdk_local.env",
    # simulator bulk output and runtime scratch
    "*/sim/*", "sim/*", "*.raw/*", "psf/*", "*/psf/*", "raw/*",
    "*.vcd", "*.psf", "*.awave", "CDS.log*", "*.cdslck",
    ".cadence/*", ".vnc-cds/*", "home/*", "skill_run/*",
    # archives and VM images (the instructor PDK arrived as a zip)
    "*.zip", "*.7z", "*.rar", "*.tar", "*.gz", "*.bz2",
    "*.vmx", "*.vmdk", "*.ova", "*.ovf",
    # third-party course delivery (documents the instructor gave, not our content)
    "course_source/*",
    # machine-generated PDK inventory dumps
    "pdk_compare/*", "logs/pdk_inventory_raw.txt", "logs/TD-MM18-SP-2004.txt",
]

# ------------------------------------------------------------------ content -----
# Hard blocks: text that only exists inside a vendor model card / deck.
DENY_CONTENT = [
    ("spice_model_card",     re.compile(r"^\s*\.\s*model[\s.]", re.I | re.M)),
    ("spice_param_block",    re.compile(r"^\s*\.\s*param[\s.]", re.I | re.M)),
    ("model_param_line",     re.compile(r"^\s*\+\s*[A-Za-z][A-Za-z0-9_]{1,14}\s*=\s*[-+0-9.eE]", re.M)),
    ("bsim_vth0_parameter",  re.compile(r"\bVTH0\s*=", re.I)),
    ("calibre_deck_section", re.compile(r"^\s*(primary keywords|lvs section|drc section|syntax check)\b", re.I | re.M)),
    ("oa_binary_marker",     re.compile(r"\x00OA(\x00|STREAM)")),
]

# Secret-shaped text. Value is never echoed.
SECRET_CONTENT = [
    ("ssh_private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token",          re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b")),
    ("github_fine_grained",   re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("aws_key_id",            re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token",           re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("google_api_key",        re.compile(r"\bAIza[0-9A-Za-z_]{30,}\b")),
    ("bearer_token",          re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9_\-\.]{20,}")),
    ("license_server_value",  re.compile(r"\b(LMD_LICENSE_FILE|LM_LICENSE_FILE|CDS_LIC_FILE)\s*=\s*\d{4,5}@\S")),
    ("password_assignment",   re.compile(
        r"(?i)\b(?:[a-z0-9]+[_.])?(password|passwd|passphrase)\b\s*[:=]\s*(\S+)")),
]

# Lines where a "password =" shape is not a credential: log-grep pattern lists,
# printf formats, env indirection. Bare `pwd` is deliberately NOT a secret key -- in
# shell code it is the working directory; two real false positives here were
# `grep -aE "pwd="` over a log and SKILL `printf("pwd=%s" getShellEnvVar("PWD"))`.
PASSWORD_OK = re.compile(
    r"(?i)(not\s|no\s|never|none|null|redact|masked|placeholder|example|hidden|"
    r"omitted|<|\bsee\b|\bavoid\b|\bblock\b|\bfail\b|"
    r"\bgrep\b|\bsed\b|\bawk\b|printf|\becho\b|getshenv|qsv)")
PASSWORD_OK_VALUE = re.compile(r"^[%$<>\"'`(|*]|\{|\.{2,}")

# Mentions of a PDK name or install path in prose: allowed, but surfaced for review.
VENDOR_NAME_RE = re.compile(
    r"(smic18mmrf_teacher|/root/tech[^\s\"',)]*|ms018_enhanced\w*|e2r018_v1p8|"
    r"cr018gpii_v1d0|tsmc18-OA|smic18ee_OA|SMIC_018_MMRF)")

SIZE_REVIEW_BYTES = 200 * 1024
HISTORY_SCAN_BYTES = 512 * 1024

EXTENSIONS_ALLOWED = {
    ".scs", ".il", ".sp", ".cir", ".awk", ".py", ".sh", ".ps1", ".mjs", ".md",
    ".json", ".csv", ".txt", ".yaml", ".yml", ".gitignore", ".gitattributes",
    ".example", ".env.example", ".sql", ".svg", ".log", ".out",
}


def norm(rel):
    return rel.replace("\\", "/").lstrip("./")


def path_denied(rel):
    """Return the deny pattern that matches rel, or None."""
    from fnmatch import fnmatch
    p = norm(rel)
    parts = p.split("/")
    for pat in DENY_PATH:
        if fnmatch(p, pat):
            return pat
        # 'pdk/*' must also catch 'a/pdk/b' and a leading 'pdk/' directory itself
        if "*" not in pat and pat in parts:
            return pat
        for i in range(1, len(parts)):
            if fnmatch("/".join(parts[i:]), pat):
                return pat
    return None


def content_denied(text):
    """Return [(rule, first line number)] for vendor-content matches."""
    hits = []
    for name, rx in DENY_CONTENT:
        m = rx.search(text)
        if m:
            hits.append((name, text[:m.start()].count("\n") + 1))
    return hits


def secrets_in(text):
    """Return [(rule, line number)] for secret-shaped matches, values never kept."""
    hits = []
    for name, rx in SECRET_CONTENT:
        for m in rx.finditer(text):
            line = text[:m.start()].count("\n") + 1
            if name == "password_assignment":
                value = m.group(2) or ""
                lines = text.splitlines()
                rest = lines[line - 1] if line - 1 < len(lines) else ""
                if PASSWORD_OK.search(rest):
                    continue
                if PASSWORD_OK_VALUE.search(value):
                    continue
                if len(value) < 4 or not re.search(r"[A-Za-z0-9]", value):
                    continue
            hits.append((name, line))
    return hits


def vendor_mentions(text):
    found = set()
    for m in VENDOR_NAME_RE.finditer(text):
        found.add(m.group(1))
    return sorted(found)


def read_text(path, limit=4 * 1024 * 1024):
    try:
        with open(path, "rb") as fh:
            raw = fh.read(limit)
    except (OSError, IOError):
        return None
    if b"\x00" in raw[:4096]:
        return raw.decode("latin-1")      # binary: rules still run, size check applies
    return raw.decode("utf-8", "replace")


def classify_file(abspath, rel, exists_check=True):
    """-> dict(bucket=SAFE_TO_TRACK|MUST_IGNORE|NEEDS_REVIEW, reasons=[...])"""
    reasons = []
    pat = path_denied(rel)
    if pat:
        reasons.append("path_matches:" + pat)
    if os.path.islink(abspath):
        reasons.append("symlink")
    size = os.path.getsize(abspath) if os.path.exists(abspath) else 0
    if size > SIZE_REVIEW_BYTES:
        reasons.append("large_file:%d" % size)
    ext = os.path.splitext(rel)[1].lower()
    if ext and ext not in EXTENSIONS_ALLOWED and not os.path.basename(rel).startswith("."):
        reasons.append("unknown_extension:" + ext)
    if pat:
        return {"bucket": "MUST_IGNORE", "reasons": reasons, "vendor": []}

    text = read_text(abspath) if exists_check else None
    hits = []
    vendor = []
    if text is not None:
        hits = content_denied(text) + secrets_in(text)
        vendor = vendor_mentions(text)
    if hits:
        reasons.extend(["%s@line%d" % (r, l) for r, l in hits])
        return {"bucket": "MUST_IGNORE", "reasons": reasons, "vendor": vendor}
    if vendor:
        reasons.append("vendor_name_in_prose:" + ",".join(vendor[:4]))
    if reasons:
        return {"bucket": "NEEDS_REVIEW", "reasons": reasons, "vendor": vendor}
    return {"bucket": "SAFE_TO_TRACK", "reasons": reasons, "vendor": vendor}


def walk_root(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", ".vnc-cds")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            yield full, rel
