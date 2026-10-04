#!/usr/bin/env python3
"""precommit_safety_check.py -- the hard gate. Run before any commit and any push.

    python scripts/precommit_safety_check.py                  # --mode staged
    python scripts/precommit_safety_check.py --mode history    # every blob in history
    python scripts/precommit_safety_check.py --mode worktree   # files on disk

staged  : reads each staged blob with `git cat-file blob :path`, so it checks the
          content that is ACTUALLY going into the commit, not the working file.
history : walks every commit and checks every unique blob, which is what must be
          clean before a push (a secret deleted in a later commit is still in history).

Any finding is fatal (exit 1) and prints path + rule + line number only. Secret and
vendor values are never echoed, because this script's own stdout lands in logs.

Install as a hook with scripts/install_hooks.sh; the hook is not part of the repo,
so `--mode history` is also wired into scripts/make_review_bundle.py and the push path.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PDK_PATH_RULES = ("pdk/*", "*/pdk/*", "smic18mmrf_teacher/*", "*/*smic18mmrf_teacher*/*",
                  "models/*", "*/models/*", "techfile/*", "*/techfile/*", "*.lib",
                  "*.vloga", "*.vams", "cds.lib", "lib.defs", "cdsinfo.*", "*.oax", "*.oa",
                  "*.rvc", "*.svrf", "*.layermap", "*.tech", "pdk_compare/*",
                  "course_source/*", "*/sim/*", "sim/*", "*.raw/*", "psf/*", "*/psf/*",
                  "raw/*", "pdk_local.env", "*/pdk_local.env",
                  "logs/pdk_inventory_raw.txt", "logs/TD-MM18-SP-2004.txt")
CRED_PATH_RULES = (".ic617_agent_bridge_credentials", "*credentials*", "*.pem", "*.ppk",
                   "known_hosts*", "authorized_keys", "*.netrc", ".env", ".env.*",
                   "*_token*", "*secret*")
KEY_PATH_RULES = ("id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.key")
VENDOR_CONTENT_RULES = ("spice_model_card", "spice_param_block", "model_param_line",
                        "bsim_vth0_parameter", "calibre_deck_section", "oa_binary_marker")
KEY_CONTENT_RULES = ("ssh_private_key_block",)


def git(*args):
    out = subprocess.run(("git", "-c", "core.quotePath=false") + tuple(args),
                         cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if out.returncode != 0:
        sys.stderr.write("git %s failed: %s\n" %
                         (" ".join(args), out.stderr.decode("utf-8", "replace").strip()))
        sys.exit(2)
    return out.stdout


def staged_paths():
    raw = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    return [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]


def staged_blob(path):
    return git("cat-file", "blob", ":" + path)


def history_blobs():
    """-> {path: set(blob sha)} over every commit on every ref."""
    commits = git("rev-list", "--all").decode().split()
    seen = {}
    for c in commits:
        raw = git("ls-tree", "-r", "-z", c)
        for chunk in raw.split(b"\0"):
            if not chunk:
                continue
            meta, _, path = chunk.partition(b"\t")
            parts = meta.split()
            if len(parts) < 3 or parts[1] != b"blob":
                continue
            p = path.decode("utf-8", "replace")
            if p not in seen:
                seen[p] = []
            sha = parts[2].decode()
            if sha not in seen[p]:
                seen[p].append(sha)
    return seen, len(commits)


def check_one(path, data):
    """-> (severity, [finding strings]) with no value ever echoed."""
    findings = []
    pat = R.path_denied(path)
    if pat:
        findings.append("PATH deny rule '%s'" % pat)
    text = data.decode("latin-1")
    for name, line in R.content_denied(text):
        findings.append("VENDOR CONTENT '%s' at line %d" % (name, line))
    for name, line in R.secrets_in(text):
        findings.append("SECRET '%s' at line %d" % (name, line))
    if len(data) > R.HISTORY_SCAN_BYTES:
        findings.append("LARGE blob %d bytes (bulk output does not belong in history)" % len(data))
    ext = os.path.splitext(path)[1].lower()
    base = os.path.basename(path)
    if ext and ext not in R.EXTENSIONS_ALLOWED and not base.startswith("."):
        findings.append("UNKNOWN extension %s" % ext)
    return findings


def tally(items):
    """The four counters the final report must state.

    Derived from the SAME precise matcher that blocks a file, so a counter can never
    disagree with the block list (an earlier substring version counted
    pdk_local.env.example as a secret because of its '.env').
    """
    counters = {"PDK_TRACKED_FILES": 0, "CREDENTIAL_TRACKED_FILES": 0,
                "PRIVATE_KEYS_TRACKED_FILES": 0, "VENDOR_MODEL_TRACKED_FILES": 0}
    for path, data in items:
        clean = path.split("@")[0]
        pat = R.path_denied(clean)
        if pat:
            if pat in PDK_PATH_RULES:
                counters["PDK_TRACKED_FILES"] += 1
            if pat in CRED_PATH_RULES:
                counters["CREDENTIAL_TRACKED_FILES"] += 1
            if pat in KEY_PATH_RULES:
                counters["PRIVATE_KEYS_TRACKED_FILES"] += 1
        if data:
            text = data.decode("latin-1")
            names = [n for n, _ in R.content_denied(text)]
            if any(n in VENDOR_CONTENT_RULES for n in names):
                counters["VENDOR_MODEL_TRACKED_FILES"] += 1
            if any(n in KEY_CONTENT_RULES for n, _ in R.secrets_in(text)):
                counters["PRIVATE_KEYS_TRACKED_FILES"] += 1
    return counters


def main():
    args = sys.argv[1:]
    mode = "staged"
    if "--mode" in args:
        mode = args[args.index("--mode") + 1]
    if mode not in ("staged", "history", "worktree"):
        print("usage: precommit_safety_check.py [--mode staged|history|worktree]")
        return 9

    items = []          # (path, bytes)
    if mode == "staged":
        for p in staged_paths():
            items.append((p, staged_blob(p)))
    elif mode == "worktree":
        for full, rel in R.walk_root(ROOT):
            with open(full, "rb") as fh:
                items.append((rel, fh.read()))
    else:
        blobs, ncommits = history_blobs()
        for path, shas in sorted(blobs.items()):
            blob = None
            for sha in shas:
                data = git("cat-file", "blob", sha)
                f = check_one(path, data)
                if f:
                    items.append((path + "@" + sha[:8], data))
                    blob = "bad"
                    break
            if blob is None:
                items.append((path, b""))      # counted for tallies, clean
        print("history: %d commits scanned" % ncommits)

    bad = []
    for path, data in items:
        f = check_one(path, data)
        if f:
            bad.append((path, f))

    print("mode=%s objects_checked=%d" % (mode, len(items)))
    counters = tally(items)
    for path, f in bad:
        print("BLOCKED %s" % path)
        for x in f:
            print("          %s" % x)
    for k in ("PDK_TRACKED_FILES", "CREDENTIAL_TRACKED_FILES",
              "PRIVATE_KEYS_TRACKED_FILES", "VENDOR_MODEL_TRACKED_FILES"):
        print("%s = %d" % (k, counters[k]))

    if bad:
        print("SAFETY_GATE: FAIL  (%d object(s) blocked -- nothing was committed)" % len(bad))
        return 1
    if counters["PDK_TRACKED_FILES"] or counters["CREDENTIAL_TRACKED_FILES"] or \
       counters["PRIVATE_KEYS_TRACKED_FILES"] or counters["VENDOR_MODEL_TRACKED_FILES"]:
        print("SAFETY_GATE: FAIL  (counter above zero)")
        return 1
    print("SAFETY_GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
