# Pre-public release audit (Part E evidence, and what actually happened)

| item | value |
|---|---|
| repository | `LINboss666/microled-ic-ai-lab` |
| remote `main` (default branch) | `11446f5c26730416692ec79615cf86e11aa76dc5` |
| `poc/c2mos-dff` (all Phase-4 work) | `45c7254aa2a4b4d05bef1faf1e87792b7843a891` |
| audit before the flip | `PUBLIC_RELEASE_SAFETY_GATE: FAIL` (transcript below) |
| visibility now | `PUBLIC` -- by the owner's explicit instruction, with the exposure below acknowledged |
| audit command | `python scripts/public_release_audit.py` |

Read the two parts of this document in order: the audit findings stand on their own, and
the last section records the decision that overrode the gate plus what the anonymous
re-check then saw.

## Status, kept in two separate dimensions

`scripts/public_release_audit.py` reads these tokens back out of this file, so they are
the machine-visible statement of the repository's state:

```
SOURCE_RELEASE_SAFETY      = PASS
IDENTITY_PRIVACY_CLEANUP   = PENDING_OWNER_ACCEPTED
```

`SOURCE_RELEASE_SAFETY` is the design-material question: PDK files, vendor model cards,
Calibre decks, credentials, private keys and raw PSF databases -- none of them are
tracked, in history, in a dangling object, or reachable anonymously.
`IDENTITY_PRIVACY_CLEANUP` is the person question, and it is open: 9 unreachable commit
objects still carry the old address in their author/committer fields. The original gate
line `PUBLIC_RELEASE_SAFETY_GATE: FAIL` and the original
`PUBLIC_RELEASE_POSTCHECK: FAIL` stay FAIL while that is true, on purpose.

The circuit's own status is unaffected by either line:

```
C2MOS design status = POC FUNCTIONAL IMPLEMENTATION / WAITING FOR SECOND INDEPENDENT SOURCE REVIEW
```

## What passed

Every local and content-side check is green, and the counters the workflow contract
asks for are all zero:

```
PDK_TRACKED_FILES = 0
CREDENTIAL_TRACKED_FILES = 0
PRIVATE_KEYS_TRACKED_FILES = 0
VENDOR_MODEL_TRACKED_FILES = 0
PHONE_EMAIL_OCCURRENCES = 0        # reachable history on both branches, author+committer
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
While the repository is `PRIVATE` those responses require authentication, so the gate's
verdict at that moment was:

> **Part F was not executed, the repository stayed `PRIVATE`, and
> `PUBLIC_RELEASE_SAFETY_GATE: FAIL` was reported rather than manufactured away by
> relaxing a check.**

## The decision that overrode the gate (2026-10-05)

After that verdict the owner was shown the exact exposure -- 9 unreachable commit objects
whose author/committer fields still hold the phone-number address, readable by SHA -- and
instructed to publish anyway, deferring the address problem to themselves. So
`gh repo edit --visibility public --accept-visibility-change-consequences` was run, and
the state is now:

```
REPOSITORY_VISIBILITY = PUBLIC        (gh: visibility=PUBLIC; anonymous GET /repos -> 200,
                                       private=false, forks=0, watchers=0)
```

Two things follow, and both are recorded rather than smoothed over:

* the gate **still reports FAIL** and the script says so out loud (`NOTE the repository is
  ALREADY PUBLIC ...`). Clearing `SUPERSEDED_COMMITS_SERVED_BY_REMOTE` remains open work,
  tracked by re-running the audit, not a closed item.
* changing visibility back would not undo it: GitHub's own visibility-change warning says
  public history data can stay accessible afterwards. So the routes below are about
  *removing* the objects, not about re-hiding the repository.

## Routes that would clear the exposure

1. **Wait and re-audit.** GitHub's garbage collection eventually removes objects no ref
   points at; `7ba5eb70` already disappeared. Re-run the audit until
   `SUPERSEDED_COMMITS_SERVED_BY_REMOTE = 0`. Nothing destructive, timing unknown.
2. **Publish from a fresh repository.** Build a new repo from `git bundle`/`git archive`
   of the clean history, so its object network never contained the pre-rewrite commits,
   and point people there. Non-destructive, but the URL changes.
3. **Delete and recreate under the same name.** Same clean object network with the
   original URL, but destroys the current repository; deleted-repository data can linger
   server-side, so this is not a purge one can verify from here.
4. **GitHub Support.** Ask for removal of the unreachable objects. Out-of-band, no
   verifiable timeline.

## Part G: the anonymous re-check, as run after the flip

`scripts/anon_release_postcheck.py` reviews the repository the way a stranger does -- no
`gh`, no token, no `Authorization` header -- over visibility, branch list, every commit's
author/committer fields, the superseded SHA list again, and the whole tree in one tarball
request (the REST API would need ~150 calls and anonymous limits are 60/hour).

Run anonymously against both branches after publishing:

| anonymous observation | `main` | `poc/c2mos-dff` |
|---|---|---|
| visibility / private | `public` / `false` | same repository |
| branches a stranger can list | `main@11446f5c`, `poc/c2mos-dff@45c7254a` | same |
| commit identity fields not the noreply shape | 0 | 0 |
| tree files fetched | 58 | 157 |
| forbidden paths / content-or-secret rule hits | 0 / 0 | 0 / 0 |
| superseded commits readable without credentials | **9 of 10** | **9 of 10** |

```
ANONYMOUS_BAD_IDENTITY_FIELDS = 0
ANONYMOUS_FORBIDDEN_PATHS = 0
ANONYMOUS_CONTENT_RULE_HITS = 0
ANONYMOUS_SUPERSEEDED_READABLE = 9
PUBLIC_RELEASE_POSTCHECK: FAIL      # solely the 9 objects above; everything else is clean
```

No PDK file, model card, deck, credential, private key, local privacy path or raw PSF
database is reachable anonymously -- the tree scan covers all 157 files that way, and it
is the same rule set the commit gate uses. The single FAIL reason is the accepted
exposure, and its counter is the number to watch down to 0.

Before the flip, the same script's two other paths had already been exercised: against
this repository while private it prints `BLOCKED_NOT_PUBLIC` (exit 3) instead of pretending
it checked, and against an unrelated public repository (`POSTCHECK_REPO=octocat/Hello-World
master`) it read branches/commits, scanned the tarball, probed all ten SHAs and then
correctly **refused** because that repository's commit identities are not the noreply shape.

## Reproduce

```
python scripts/public_release_audit.py            # full report, exit 1 = gate FAIL
python scripts/public_release_audit.py --quiet    # verdict lines only
python scripts/anon_release_postcheck.py main     # anonymous view of the default branch
python scripts/anon_release_postcheck.py poc/c2mos-dff   # anonymous view of the work branch
```

The superseded SHA list lives in `OLD_REWRITTEN_SHAS` inside the script; it was
enumerated from `review/history_before_metadata_rewrite.bundle`, which is ignored and
was never pushed. A reviewer without that bundle still gets every other check plus a
loud `PROBLEM` line here rather than a silent pass.

One bookkeeping note: the tracked-file count printed in the transcript is taken at run
time, so it reads lower than the repository after this document and the transcript
themselves became tracked. The transcript's `AUDITED_HEAD` is the last *content* commit;
the commits after it add only this transcript and one AGENTS note, and each of those
passed the staged gate plus the full `--mode history` scan that the push hook runs, so
the content verdict carries over without another transcript run.
