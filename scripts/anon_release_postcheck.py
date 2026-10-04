#!/usr/bin/env python3
"""anon_release_postcheck.py -- Part G: review the repository the way a stranger does.

Everything here is fetched WITHOUT credentials (no gh, no token, no netrc), because the
question is not "can I see it" but "can anybody see it". The tarball route is deliberate:
one request gives the whole tree, where the REST API would need ~150 calls and anonymous
rate limits are 60/hour.

    python scripts/anon_release_postcheck.py [branch]

Exit 0 = PUBLIC_RELEASE_POSTCHECK: PASS. A still-private repository reports
BLOCKED_NOT_PUBLIC rather than pretending the check ran.
"""

import io
import json
import os
import re
import sys
import tarfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_safety_rules as R  # noqa: E402

PHONE = re.compile(r"1[3-9][0-9]\d{8}@(163|qq|126|139)\.com")
NOREPLY = re.compile(r"^\d+\+[\w-]+@users\.noreply\.github\.com$")
# Every commit the metadata rewrite replaced (same list as public_release_audit.py,
# which documents where it comes from). None of them may resolve anonymously.
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


def get(url):
    """Anonymous GET. No Authorization header can exist here: this process holds no
    token and never reads one from the environment."""
    req = urllib.request.Request(url, headers={"User-Agent": "release-postcheck",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                    # noqa: BLE001
        return -1, str(e).encode()


def json_get(url):
    code, body = get(url)
    try:
        return code, json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return code, None


def main():
    branch = sys.argv[1] if len(sys.argv) > 1 else "main"
    problems = []

    # owner/repo comes from the local git remote so this file carries no literal either.
    # POSTCHECK_REPO overrides it, which is how the PASS path gets exercised against some
    # other public repository before this one is ever flipped.
    OWNER_REPO = os.environ.get("POSTCHECK_REPO", "").strip()
    if not OWNER_REPO:
        import subprocess
        url = subprocess.run(("git", "config", "--get", "remote.origin.url"),
                             cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             stdout=subprocess.PIPE).stdout.decode().strip()
        m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url, re.I)
        if not m:
            print("POSTCHECK: cannot derive owner/repo from " + url)
            return 2
        OWNER_REPO = "%s/%s" % (m.group(1), m.group(2))
    print("== audit target (anonymous): " + OWNER_REPO + " branch " + branch)
    api = "https://api.github.com/repos/" + OWNER_REPO

    code, info = json_get(api)
    if code == 404:
        print("REPOSITORY_VISIBILITY: NOT PUBLIC (anonymous GET /repos -> 404, which is "
              "what GitHub answers for a private repository)")
        print("PUBLIC_RELEASE_POSTCHECK: BLOCKED_NOT_PUBLIC")
        return 3
    if code != 200:
        print("POSTCHECK: anonymous repo lookup failed http=%d" % code)
        return 2
    vis = str(info.get("visibility") or "").lower()
    print("== anonymous repo: visibility=%s private=%s default_branch=%s size_kb=%s"
          % (vis, info.get("private"), info.get("default_branch"), info.get("size")))
    if vis != "public" or info.get("private") is not False:
        problems.append("anonymous caller sees visibility=%s private=%s" % (vis, info.get("private")))
    desc = info.get("description") or ""
    print("== anonymous description: " + (desc.strip() or "(empty)"))
    desc_hits = R.content_denied(desc) + R.secrets_in(desc)
    if desc_hits:
        problems.append("description trips %d rule(s): %s"
                        % (len(desc_hits), ", ".join(sorted(set(n for n, _ in desc_hits)))))

    code, refs = json_get(api + "/git/refs/heads")
    if code == 200:
        print("== anonymous branch list: " + ", ".join(
            "%s@%s" % (r["ref"].split("/")[-1], r["object"]["sha"][:8]) for r in refs))
    else:
        problems.append("branches not readable anonymously (http=%d)" % code)

    # Commit metadata as a stranger sees it.
    code, commits = json_get(api + "/commits?sha=%s&per_page=100" % branch)
    bad_ids = 0
    if code == 200:
        for c in commits:
            cm = c.get("commit") or {}
            for k in ("author", "committer"):
                addr = (cm.get(k) or {}).get("email") or ""
                if PHONE.search(addr) or not NOREPLY.match(addr):
                    bad_ids += 1
        print("== anonymous commits on %s: %d, author/committer fields not matching the "
              "noreply shape: %d" % (branch, len(commits), bad_ids))
    else:
        problems.append("commit list not readable anonymously (http=%d)" % code)
    if bad_ids:
        problems.append("%d anonymously-visible commit identity fields are not the "
                        "noreply address" % bad_ids)

    # Superseded objects must be gone for a stranger too.
    still = 0
    for sha in OLD_REWRITTEN_SHAS:
        code, _ = json_get(api + "/commits/" + sha)
        if code == 200:
            still += 1
            print("   superseded %s -> ANONYMOUSLY READABLE" % sha[:8])
    print("== superseded commits readable without credentials: %d/%d"
          % (still, len(OLD_REWRITTEN_SHAS)))
    if still:
        problems.append("%d superseded commits are readable anonymously" % still)

    # Whole tree, one request, then the same rules as the commit gate over every byte.
    code, blob = get("https://codeload.github.com/%s/tar.gz/refs/heads/%s"
                     % (OWNER_REPO, branch))
    if code != 200:
        problems.append("tarball not fetchable anonymously (http=%d)" % code)
        blob = b""
    files = []
    if blob:
        try:
            with tarfile.open(fileobj=io.BytesIO(blob)) as t:
                for ti in t.getmembers():
                    if ti.isfile() and ti.size <= 4 * 1024 * 1024:
                        rel = "/".join(ti.name.split("/")[1:])
                        files.append((rel, t.extractfile(ti).read()))
        except Exception as e:                                # noqa: BLE001
            problems.append("tarball unreadable: %s" % e)
    path_hits = [rel for rel, _ in files if R.path_denied(rel)]
    content_hits = []
    for rel, data in files:
        text = data.decode("latin-1")
        for name, line in R.content_denied(text):
            content_hits.append("%s: %s at line %d" % (rel, name, line))
        for name, line in R.secrets_in(text):
            content_hits.append("%s: %s at line %d" % (rel, name, line))
    print("== anonymous tarball: %d files, forbidden paths=%d, rule hits=%d"
          % (len(files), len(path_hits), len(content_hits)))
    for h in (path_hits + content_hits)[:15]:
        print("   " + h)      # rule names and paths only, never the matched value
    if path_hits:
        problems.append("%d anonymously reachable paths trip the deny rules" % len(path_hits))
    if content_hits:
        problems.append("%d anonymously reachable files trip the deny/secret rules"
                        % len(content_hits))

    print("")
    print("ANONYMOUS_SUPERSEEDED_READABLE = %d" % still)
    print("ANONYMOUS_BAD_IDENTITY_FIELDS = %d" % bad_ids)
    print("ANONYMOUS_FORBIDDEN_PATHS = %d" % len(path_hits))
    print("ANONYMOUS_CONTENT_RULE_HITS = %d" % len(content_hits))
    for p in problems:
        print("PROBLEM " + p)
    if problems:
        print("PUBLIC_RELEASE_POSTCHECK: FAIL")
        return 1
    print("PUBLIC_RELEASE_POSTCHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
