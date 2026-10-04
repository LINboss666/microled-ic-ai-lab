#!/usr/bin/env python3
"""public_release_audit.py -- everything that must be true before PRIVATE becomes PUBLIC.

Runs the local checks, then the remote ones through `gh`, and prints the exact counter
block the workflow contract requires. Read-only against the repository: it never
mutates, never pushes, never changes visibility.

    python scripts/public_release_audit.py            # report
    python scripts/public_release_audit.py --quiet    # only the verdict lines

Exit 0 = PUBLIC_RELEASE_SAFETY_GATE: PASS.
"""

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHONE = re.compile(r"1[3-9][0-9]\d{8}@(163|qq|126|139)\.com")
FORBIDDEN_NAME = re.compile(
    r"(^|/)(pdk|smic18mmrf_teacher|models?|techfile|calibre)/|\.(lib|svrf|rvc|layermap|zip|7z|rar|vmx|vmdk|raw|psf|vcd|pem|key|ppk)($|\.)|"
    r"credentials|id_rsa|pdk_local\.env$|(^|/)sim/|(^|/)psf/|(^|/)raw/|\*DRC|\bDRC[._]|LVS[._]|review_bundle_.*\.zip|history_.*\.bundle",
    re.I)


def git(*a):
    return subprocess.run(("git", "-c", "core.quotePath=false") + a, cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                          ).stdout.decode("utf-8", "replace")


NET_ERR = ("could not be resolved", "Connection reset", "timed out",
           "TLS handshake", "connection refused", "Recv failure")


def gh(*a):
    """Runs `gh`, retrying only on transport failures. A 404 is treated as a real
    answer: this network's earlier resets were transport-level, and a repo that
    exists but is spelled wrong must fail fast and loudly, not be retried away."""
    rc, out = 1, ""
    for attempt in range(4):
        p = subprocess.run(("gh",) + a, cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        rc, out = p.returncode, p.stdout.decode("utf-8", "replace")
        if rc == 0:
            return rc, out
        if not any(e.lower() in out.lower() for e in NET_ERR):
            return rc, out
        time.sleep(3 * (attempt + 1))
    return rc, out


def remote_repo():
    """The audit target is read from `origin`, never written as a literal here: a
    misspelled owner/repo makes GitHub answer 404 for a repository that does exist,
    which then reads like a missing token instead of like a typo in this script."""
    url = git("config", "--get", "remote.origin.url").strip()
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url, re.I)
    return ("%s/%s" % (m.group(1), m.group(2))) if m else "", url


def gate(mode):
    p = subprocess.run((sys.executable, os.path.join(ROOT, "scripts",
                       "precommit_safety_check.py"), "--mode", mode),
                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    quiet = "--quiet" in sys.argv
    problems = []

    def say(*a):
        if not quiet:
            print(*a)

    # ---- 1. tracked set -------------------------------------------------------
    tracked = [t for t in git("ls-files").splitlines() if t]
    say("== tracked files: %d" % len(tracked))
    bad_names = [t for t in tracked if FORBIDDEN_NAME.search(t)]
    for t in bad_names:
        problems.append("forbidden-looking tracked path: " + t)
    ignored_not_tracked = []
    for probe in (".ic617_agent_bridge_credentials", "spectre/pdk_local.env",
                  "review/history_before_metadata_rewrite.bundle",
                  "review/history_pre_gc.bundle",
                  "review/history_before_pii_redaction.bundle",
                  "course_source", "pdk_compare"):
        ignored_not_tracked.append((probe, any(t == probe or t.startswith(probe + "/")
                                               for t in tracked)))
    say("   untracked-only probes (all must be False):")
    for probe, present in ignored_not_tracked:
        say("     %-46s tracked=%s" % (probe, present))
        if present:
            problems.append("this path must never be tracked: " + probe)

    # ---- 2. staged set --------------------------------------------------------
    rc, out = gate("staged")
    say("== gate staged: %s" % out.strip().splitlines()[-1])
    if rc != 0:
        problems.append("staged gate failed")

    # ---- 3. reachable history and every object --------------------------------
    rc, hist = gate("history")
    rc2, objs = gate("objects")
    for blob in (hist, objs):
        last = blob.strip().splitlines()[-1]
        say("== gate: " + last)
        if "PASS" not in last:
            problems.append("gate reported " + last)
    counters = {}
    for line in (hist + objs).splitlines():
        m = re.match(r"^([A-Z_]+) = (\d+)$", line)
        if m:
            counters[m.group(1)] = max(int(m.group(2)), counters.get(m.group(1), 0))
    # (no worktree scan on purpose: ignored local artefacts such as review/*.zip are
    #  allowed to exist on disk; only tracked content, history and objects ship)

    # ---- 4. commit metadata ---------------------------------------------------
    meta = git("log", "--all", "--format=%ae|%ce|%an|%cn")
    phone = [l for l in meta.splitlines() if PHONE.search(l)]
    say("== commit metadata: %s author/committer records, phone-email hits=%d"
        % (len(meta.splitlines()), len(phone)))
    if phone:
        problems.append("phone-shaped author/committer email still in history")
    emails = sorted(set(re.split(r"[|%]", meta) [0::4]))
    say("   author emails: " + ", ".join(e for e in emails if e))

    # ---- 5. git objects: nothing unreachable that we care about --------------
    fsck = git("fsck", "--full")
    say("== git fsck --full: " + ("clean" if not fsck.strip() else fsck.strip()[:200]))
    if fsck.strip():
        problems.append("git fsck reported something")

    # ---- 6. remote state ------------------------------------------------------
    REPO, origin_url = remote_repo()
    say("== origin: %s -> audit target %s" % (origin_url, REPO or "(unparsable)"))
    if not REPO:
        print("PROBLEM cannot derive owner/repo from remote.origin.url, refusing to "
              "guess it. Local audits above still stand.")
        return 1
    owner = REPO.split("/")[0]
    # GitHub answers 404 (not 401) for a PRIVATE repo when the caller arrives
    # unauthenticated, so prove the identity first; otherwise "cannot read the remote
    # repository state" reads like a missing repository instead of a missing token.
    rc, who = gh("api", "user")
    login = ""
    if rc == 0:
        try:
            login = json.loads(who).get("login", "")
        except ValueError:
            login = ""
    say("== gh api identity: " + (login or "ANONYMOUS (gh has no token right now)"))
    if not login:
        print("PROBLEM gh is not authenticated (token read failed or expired); "
              "remote-side audit is impossible. Local audits above still stand.")
        return 1
    if login != owner:
        problems.append("authenticated as %s but the audit target is %s" % (login, owner))

    # No jq expressions here on purpose: `default` is a jq keyword and gh turns that
    # into a misleading 404 body. Parse the JSON ourselves instead.
    rc, body = gh("api", "repos/" + REPO)
    info = {}
    if rc == 0:
        try:
            info = json.loads(body)
        except ValueError:
            problems.append("remote repo JSON unparsable: " + body[:120])
    else:
        problems.append("cannot read the remote repository state: " + body[:160])
    if info:
        say("== remote repo: visibility=%s private=%s default_branch=%s size_kb=%s "
            "fork=%s" % (info.get("visibility"), info.get("private"),
                         (info.get("default_branch") or ""), info.get("size"),
                         info.get("fork")))
        if info.get("visibility") not in ("PRIVATE", "PUBLIC"):
            problems.append("unexpected visibility value")
    desc = (info.get("description") or "").strip()
    say("== repo description: " + (desc or "(empty)"))
    if R.path_denied(desc) or FORBIDDEN_NAME.search(desc):
        problems.append("repo description looks like PDK/credential text")

    def total(path, key="total_count"):
        rc, out = gh("api", path)
        if rc != 0:
            return None, out.strip()[:120]
        try:
            return json.loads(out).get(key), ""
        except ValueError:
            return None, "unparsable"

    for label, path in (("actions/workflows", "repos/%s/actions/workflows" % REPO),
                        ("actions/runs", "repos/%s/actions/runs" % REPO),
                        ("actions/artifacts", "repos/%s/actions/artifacts" % REPO)):
        n, err = total(path)
        if err:
            say("== %-18s -> %s" % (label, err))
            problems.append("cannot audit " + label + ": " + err)
            continue
        say("== %-18s count=%s" % (label, n))
        if (n or 0) != 0:
            problems.append("%s has content (%s) and must be reviewed before publishing"
                            % (label, n))

    # commits that the metadata rewrite replaced must not be reachable any more
    for old_sha in ("89841c06e82dd2ccd34f1104563f97bd6ed0dd54",
                    "a181bb86d40856bd880df69f67cdcb84c5496e80",
                    "7ba5eb70f918ea2fccb3825bb41a60cce24fbc85"):
        rc, out = gh("api", "repos/%s/commits/%s" % (REPO, old_sha))
        gone = rc != 0 and '"status":"404"' in out.replace(" ", "")
        say("   superseded commit %s -> %s"
            % (old_sha[:7], "not reachable (404)" if gone
               else ("REACHABLE (must not be)" if rc == 0 else "call failed: " + out.strip()[:100])))
        if not gone:
            problems.append("superseded commit %s is not confirmed unreachable on the "
                            "remote (%s)" % (old_sha[:7], "reachable" if rc == 0 else "audit call failed"))

    # ---- verdict --------------------------------------------------------------
    print("")
    print("PDK_TRACKED_FILES = %d" % counters.get("PDK_TRACKED_FILES", -1))
    print("CREDENTIAL_TRACKED_FILES = %d" % counters.get("CREDENTIAL_TRACKED_FILES", -1))
    print("PRIVATE_KEYS_TRACKED_FILES = %d" % counters.get("PRIVATE_KEYS_TRACKED_FILES", -1))
    print("VENDOR_MODEL_TRACKED_FILES = %d" % counters.get("VENDOR_MODEL_TRACKED_FILES", -1))
    print("PHONE_EMAIL_OCCURRENCES = %d" % len(phone))
    print("forbidden_names_in_tracked = %d" % len(bad_names))
    for p in problems:
        print("PROBLEM " + p)
    zero = all(counters.get(k) == 0 for k in
               ("PDK_TRACKED_FILES", "CREDENTIAL_TRACKED_FILES",
                "PRIVATE_KEYS_TRACKED_FILES", "VENDOR_MODEL_TRACKED_FILES"))
    if problems or not zero:
        print("PUBLIC_RELEASE_SAFETY_GATE: FAIL")
        return 1
    print("PUBLIC_RELEASE_SAFETY_GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
