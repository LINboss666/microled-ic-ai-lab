# Pre-public release audit (Part E evidence)

Generated against the repository in this state, then read together with the machine
transcript `results/public_release_audit.txt`, which names the branch and SHA it audited
in its own `AUDITED_BRANCH` / `AUDITED_HEAD` lines (so this document does not have to
guess its own commit hash):

| item | value |
|---|---|
| repository | `LINboss666/microled-ic-ai-lab` |
| remote `main` | `11446f5c26730416692ec79615cf86e11aa76dc5` |
| visibility at audit time | `PRIVATE` |
| audit command | `python scripts/public_release_audit.py` |

## What passed

Every local and content-side check is green, and the counters the workflow contract
asks for are all zero:

```
PDK_TRACKED_FILES = 0
CREDENTIAL_TRACKED_FILES = 0
PRIVATE_KEYS_TRACKED_FILES = 0
VENDOR_MODEL_TRACKED_FILES = 0
PHONE_EMAIL_OCCURRENCES = 0        # local history: 11 commits, author+committer
forbidden_names_in_tracked = 0     # all carry the GitHub noreply address
SUPERSEDED_COMMITS_SERVED_BY_REMOTE = 9   # <- the blocker, see below
SUPERSEDED_TREES_MATCHING_CLEAN_HISTORY = 9/9
REMOTE_PHONE_EMAIL_FIELDS = 18            # <- the blocker, see below
```

`git fsck --full` is clean, the staged/history/objects gates all report
`SAFETY_GATE: PASS`, local and remote refs match branch for branch, and the server has
no pull requests, no forks and no Actions workflows, runs or artifacts (so nothing on
the GitHub side could pin or publish extra content).

The pre-publication content redaction was checked separately, by fetching the older
backup bundle into a throwaway repository (`git fetch <bundle> 'refs/heads/*:...'`),
listing its six commit SHAs and asking the API for each one. All six answered
`No commit found for SHA`. Those commits predate the first push, so no superseded *file
content* ever reached the server -- only commit metadata did. That bundle is ignored and
local-only, so this particular check is a record of what was run rather than something a
reviewer can re-run without it; the metadata check above is re-runnable.

## One local object-store residue this round (real, and not a false alarm)

Mid-round the audit reported `VENDOR_MODEL_TRACKED_FILES = 1` plus a non-clean
`git fsck`. The object was a **dangling blob left by a staging that the commit gate then
rejected**: `git add` writes the blob first, the gate refuses the commit afterwards, and
the rejected bytes stay in `.git`. The content was a test fixture in
`scripts/make_review_bundle.py` whose text mimics a BSIM parameter line -- the gate was
right to block it, and the objects scan was right to keep seeing it after the block.

Two consequences, both kept in the tooling rather than papered over:

* the fixture is assembled at run time (`"+.mo" + "del n18 bsim4"`), so the vendor-shaped
  text never exists in a tracked file while the scan still has a real model line to
  catch. `make_review_bundle.py` now asserts both directions before trusting itself:
  the planted model line must be flagged, an ordinary threshold label must not be.
* `git fsck` output is no longer an automatic FAIL. A dangling object is normal
  housekeeping; the property that matters is that no unreachable object carries
  forbidden content, and `--mode objects` is the check that states it. The audit now
  prints `DANGLING_OBJECTS = n` and fails only on `missing` objects.

`git prune --expire=now --dry-run` was run first to list exactly what would go (1 blob,
2 trees, all unreachable and all from this round's rejected staging), then the prune,
then `git fsck --full` came back clean. Nothing reachable was touched.

## The blocker: the server still serves the superseded commit objects

The metadata rewrite (`git filter-branch --env-filter`, author + committer email only)
and the `--force-with-lease` push did what they were supposed to do: no ref, local or
remote, points at a pre-rewrite commit, and the reachable history is clean. The audit
does not assume the rewrite left content untouched -- it compares each served
`commit.tree.sha` with the set of trees in the clean history and reports
`SUPERSEDED_TREES_MATCHING_CLEAN_HISTORY = 9/9`.

GitHub nevertheless still returns 9 of the 10 superseded commits when asked for them by
SHA:

```
/api/repos/LINboss666/microled-ic-ai-lab/commits/<old-sha>   -> 200, commit metadata
```

Each of those 9 responses carries the phone-number-shaped address in both the `author`
and the `committer` field (18 fields total). One object, `7ba5eb70`, is already gone, so
the server does drop them -- on its own schedule, which is not observable from here.
While the repository is `PRIVATE` those responses require authentication, so nothing is
exposed today. The moment visibility becomes `PUBLIC`, the same endpoints and
`.../commit/<old-sha>` web pages become anonymously readable by anyone who knows or
guesses a SHA, which is exactly the data the rewrite was meant to remove.

Consequence: **Part F was not executed. The repository stays `PRIVATE`.**
`PUBLIC RELEASE BLOCKED` is the honest verdict for this round, and
"PUBLIC_RELEASE_SAFETY_GATE: PASS" was not manufactured by relaxing a check.

## Options (each needs an explicit decision)

1. **Wait and re-audit.** GitHub's own garbage collection eventually removes objects
   that no ref points at; `7ba5eb70` already disappeared. Re-run
   `python scripts/public_release_audit.py` until `SUPERSEDED_COMMITS_SERVED_BY_REMOTE = 0`,
   then flip. Nothing destructive, timing unknown.
2. **Publish from a fresh repository.** Build a new repo from
   `git bundle`/`git archive` of the current clean history, so its object network has
   never contained the pre-rewrite commits, and make that one public. Non-destructive,
   but the public URL changes from `microled-ic-ai-lab`.
3. **Delete and recreate under the same name.** Gives the same clean object network as
   option 2 with the original URL, but destroys the existing private repository.
   Deleted-repository data can linger server-side, so this is not a guaranteed purge.
4. **GitHub Support.** Ask for removal of the dangling objects for this repository.
   Out-of-band; no timeline we can verify from here.

Option 1 is the only one that requires no irreversible action, so it is the default
position until told otherwise.

## Part G is scripted, and deliberately not run

`scripts/anon_release_postcheck.py` is the post-public anonymous review: it fetches the
repository the way a stranger does -- no `gh`, no token, no `Authorization` header -- and
checks visibility, branch list, every commit's author/committer fields, the superseded
SHA list again (this time without credentials), and the whole tree in one tarball request
against the same deny rules the commit gate uses. Its verdict is
`PUBLIC_RELEASE_POSTCHECK: PASS / FAIL / BLOCKED_NOT_PUBLIC`.

Both of its non-trivial paths were exercised this round:

* against this repository while it is still private it prints
  `BLOCKED_NOT_PUBLIC` (exit 3) rather than pretending it checked, and
* against an arbitrary public repository (`POSTCHECK_REPO=octocat/Hello-World master`) it
  read visibility/branches/commits, downloaded and scanned the tarball (1 file, 0 rule
  hits), probed all ten superseded SHAs (0 readable) and then correctly **failed**
  because that repo's commit identities are not the noreply shape -- proof the scan can
  both pass and refuse.

It stays unrun against this repo until visibility actually changes.

## Reproduce

```
python scripts/public_release_audit.py            # full report, exit 1 = gate FAIL
python scripts/public_release_audit.py --quiet    # verdict lines only
```

The superseded SHA list lives in `OLD_REWRITTEN_SHAS` inside the script; it was
enumerated from `review/history_before_metadata_rewrite.bundle`, which is ignored and
was never pushed. A reviewer without that bundle still gets every other check plus a
loud `PROBLEM` line here rather than a silent pass.

One bookkeeping note: the tracked-file count printed in the transcript is taken at run
time, so it is ahead by the files this commit itself adds.
