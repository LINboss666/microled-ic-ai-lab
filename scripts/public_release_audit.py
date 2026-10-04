#!/usr/bin/env python3
"""public_release_audit.py -- everything that must be true before PRIVATE becomes PUBLIC.

Runs the local checks, then the remote ones through `gh`, and prints the exact counter
block the workflow contract requires. Read-only against the repository: it never
mutates, never pushes, never changes visibility.

A clean local history is not enough: after a metadata rewrite plus force-push GitHub can
keep serving the superseded commit objects by SHA, and their author/committer fields are
exactly the address that was removed locally. Every superseded SHA must come back absent
before the repository is exposed.

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHONE = re.compile(r"1[3-9][0-9]\d{8}@(163|qq|126|139)\.com")
# `origin`'s description/README is prose, so a path rule is wrong for it: the sentence
# "no PDK, no credentials" is a statement of policy, not a leak. Only concrete secret or
# local-filesystem shapes count here.
TEXT_LEAK = re.compile(
    r"(?:[A-Za-z]:[\\/]{1,2}(?:Users|Documents)|/root/|/home/[A-Za-z0-9._-]+/|"
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN|"
    r"smic18mmrf|\.ic617_agent_bridge_credentials|history_[a-z_]*\.bundle"
    r"|1[3-9][0-9]\d{8}@(?:163|qq|126|139)\.com)",
    re.I)
# Every commit the metadata rewrite replaced. These are tips' ancestors from the
# ignored local backup bundle (review/history_before_metadata_rewrite.bundle), which is
# deliberately not in the repo; a reviewer without the bundle can still run every other
# check and gets a loud PROBLEM here instead of a silent pass.
OLD_REWRITTEN_SHAS = (
    "1843f1f9da7ad42ec3c011ff5e736b6952fba9f5",
    "3f33a4804ddcdeb38523817aec3f9f6d863b8bd3",
    "461567bd1f527862f6e6a51a131a81ace4dbdf67",
    "7ba5eb70f918ea2fccb3825bb41a60cce24fbc85",
    "89841c06e82dd2ccd34f1104563f97bd6ed0dd54",
    "9f5e54c3fc97f91f71169693714e9a0d85f1db90",
    "a181bb86d40856bd880df69f67cdcb84c5496e80",
    "b6f3a0e1de1fbc69e532eb24a65e6c08d2ae2fc1",
    "bdce712172e62e534359d4be204a798d678a8fc6",
    "c489b2801fa8fe33b454ac0f584a3daa71591f50",
)
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
    emails = sorted(set(git("log", "--all", "--format=%ae").split())
                    | set(git("log", "--all", "--format=%ce").split()))
    say("   author+committer emails: " + ", ".join(emails))

    # ---- 5. git objects: nothing unreachable that we care about --------------
    # A dangling object is normal housekeeping (staging something the gate then rejects
    # leaves one behind), so its mere existence is not a leak. What matters is that no
    # unreachable object carries forbidden content, and --mode objects below is the
    # check that says so; here the count is reported, not judged.
    fsck = git("fsck", "--full")
    dangling = [l for l in fsck.splitlines() if l.startswith(("dangling", "missing"))]
    say("== git fsck --full: %d dangling/missing line(s)%s"
        % (len(dangling), ": " + "; ".join(d.split()[1] + " " + d.split()[0]
                                          for d in dangling[:4]) if dangling else ""))
    for line in fsck.splitlines():
        if line.startswith("missing"):
            problems.append("git fsck reports a missing object: " + line[:80])

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
    visibility = ""
    if info:
        visibility = str(info.get("visibility") or ("PRIVATE" if info.get("private")
                                                    else "PUBLIC")).upper()
        say("== remote repo: visibility=%s private=%s default_branch=%s size_kb=%s "
            "fork=%s" % (visibility, info.get("private"),
                         (info.get("default_branch") or ""), info.get("size"),
                         info.get("fork")))
        if visibility not in ("PRIVATE", "PUBLIC"):
            problems.append("unexpected visibility value: " + visibility)
    desc = (info.get("description") or "").strip()
    say("== repo description: " + (desc or "(empty)"))
    leak = TEXT_LEAK.search(desc)
    if leak:
        problems.append("repo description contains a concrete leak pattern: "
                        + leak.group(0)[:40])

    # The server must hold exactly the rewritten refs. A PR or a fork would pin the
    # superseded commit objects open forever, so both counts belong in the gate.
    rc, refs = gh("api", "repos/%s/git/matching-refs/heads" % REPO)
    remote_refs = {}
    if rc == 0:
        try:
            remote_refs = {d["ref"]: d["object"]["sha"] for d in json.loads(refs)}
        except (ValueError, KeyError, TypeError):
            problems.append("remote refs JSON unparsable")
    else:
        problems.append("cannot read remote refs: " + refs[:120])
    local_refs = {}
    for line in git("for-each-ref", "--format=%(objectname) %(refname)",
                   "refs/heads").splitlines():
        sha, ref = line.split(" ", 1)
        local_refs[ref.strip()] = sha
    for ref in sorted(set(local_refs) | set(remote_refs)):
        same = local_refs.get(ref) == remote_refs.get(ref)
        say("   ref %-28s local=%s remote=%s %s"
            % (ref, (local_refs.get(ref) or "-")[:8], (remote_refs.get(ref) or "-")[:8],
               "match" if same else "DIFFERS"))
        if not same:
            problems.append("local and remote disagree on " + ref)
    for label, path in (("open+closed PRs", "pulls?state=all&per_page=100"),
                        ("forks", "forks?per_page=100")):
        rc, out = gh("api", "repos/%s/%s" % (REPO, path))
        try:
            n = len(json.loads(out)) if rc == 0 else -1
        except ValueError:
            n = -1
        say("== %-18s count=%s" % (label, n))
        if n != 0:
            problems.append("%s exist (%d): they pin superseded commit objects on the "
                            "server" % (label, n))

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

    # A commit the metadata rewrite replaced must not be served by the server any more.
    # What such a response exposes is its author/committer fields -- the phone-shaped
    # address that was removed locally -- and that claim is only sound if the served tree
    # is one the clean history also has, so the tree OID is checked rather than assumed.
    # Local history being clean is therefore not sufficient evidence.
    local_trees = set(git("log", "--all", "--format=%T").split())
    remote_phone = 0
    served = 0
    trees_clean = 0
    for old_sha in OLD_REWRITTEN_SHAS:
        rc, out = gh("api", "repos/%s/commits/%s" % (REPO, old_sha))
        # GitHub answers "No commit found for SHA" with HTTP 422 (not 404) for an object
        # that is not in this repository's network, so both shapes mean the same here.
        gone = rc != 0 and ("No commit found" in out or '"status":"404"' in out.replace(" ", "")
                            or "HTTP 404" in out)
        if gone:
            say("   superseded %s -> not served (object absent)" % old_sha[:8])
            continue
        if rc != 0:
            say("   superseded %s -> audit call failed: %s" % (old_sha[:8], out.strip()[:100]))
            problems.append("superseded commit %s is not confirmed unreachable (%s)"
                            % (old_sha[:8], "audit call failed"))
            continue
        served += 1
        fields = 0
        tree_ok = False
        try:
            c = json.loads(out)["commit"]
            tree_ok = c["tree"]["sha"] in local_trees
            for k in ("author", "committer"):
                addr = (c.get(k) or {}).get("email") or ""
                fields += 1 if PHONE.search(addr) else 0
        except (ValueError, KeyError, TypeError):
            problems.append("superseded commit %s served with unparsable metadata"
                            % old_sha[:8])
        if tree_ok:
            trees_clean += 1
        else:
            problems.append("superseded commit %s is served with a tree that is not in "
                            "the clean history -- its FILE CONTENT differs, not just its "
                            "identity fields" % old_sha[:8])
        remote_phone += fields
        say("   superseded %s -> SERVED BY REMOTE, phone-shaped email fields=%d, "
            "tree matches clean history=%s (not on any ref)"
            % (old_sha[:8], fields, tree_ok))
    say("== superseded: %d rewritten commits, %d still served, %d phone-shaped email "
        "fields on the server, %d/%d served trees match the clean history"
        % (len(OLD_REWRITTEN_SHAS), served, remote_phone, trees_clean, served))
    if served:
        problems.append("%d superseded commit objects are still served by the remote; "
                        "making the repository PUBLIC would make them anonymously "
                        "readable by SHA" % served)
    if remote_phone:
        problems.append("%d phone-shaped author/committer emails are readable on the "
                        "remote even though local history is clean" % remote_phone)

    # ---- verdict --------------------------------------------------------------
    head = git("rev-parse", "HEAD").strip()
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    print("")
    print("AUDITED_BRANCH = %s" % branch)
    print("AUDITED_HEAD = %s" % head)
    print("PDK_TRACKED_FILES = %d" % counters.get("PDK_TRACKED_FILES", -1))
    print("CREDENTIAL_TRACKED_FILES = %d" % counters.get("CREDENTIAL_TRACKED_FILES", -1))
    print("PRIVATE_KEYS_TRACKED_FILES = %d" % counters.get("PRIVATE_KEYS_TRACKED_FILES", -1))
    print("VENDOR_MODEL_TRACKED_FILES = %d" % counters.get("VENDOR_MODEL_TRACKED_FILES", -1))
    print("PHONE_EMAIL_OCCURRENCES = %d" % len(phone))
    print("forbidden_names_in_tracked = %d" % len(bad_names))
    print("DANGLING_OBJECTS = %d  (content scanned by --mode objects, not judged by existence)"
          % len(dangling))
    print("REPOSITORY_VISIBILITY_NOW = %s" % (visibility or "UNKNOWN"))
    print("SUPERSEDED_COMMITS_SERVED_BY_REMOTE = %d" % served)
    print("SUPERSEDED_TREES_MATCHING_CLEAN_HISTORY = %d/%d" % (trees_clean, served))
    print("REMOTE_PHONE_EMAIL_FIELDS = %d" % remote_phone)
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
