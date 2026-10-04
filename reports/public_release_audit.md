# Pre-public release audit (Part E evidence)

Generated against the repository in this state, then read together with the machine
transcript `results/public_release_audit.txt`:

| item | value |
|---|---|
| branch / HEAD at audit time | `poc/c2mos-dff` @ `6058efe` |
| remote `main` | `11446f5c26730416692ec79615cf86e11aa76dc5` |
| repository | `LINboss666/microled-ic-ai-lab` |
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
