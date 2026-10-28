# DATA-7C-B-TR-R1 delivery receipt

Round `DATA-7C-B-TR-R1` on branch `poc/data-pam-d7c-b-tr-r1`, built in the worktree
`D:\ic617_d7c_b_tr_r1` on base `398c9e852c16db85cbfa4539e859534e117ff0d2` (the reviewed TR tip), with
`61621f6e3d887082ecd6a7ecc1c771f8e509a24a` as the repository base the packaging range starts from.
Written at 2026-10-28T03:26Z.

## Commits this receipt is made of

| commit | what it carries |
| --- | --- |
| `f38a8bd30d42730b4b348d30300200ccab761e93` | the payload: the repaired and new tools, the 142 delivered sequence containers, the republished tables, the reviewer instrument and the R1 task book |
| `706d6e54ce717895456a7f67e4a339d81b3af380` | the repair report, the handoff (markdown and JSON) and the input identity without the operator's user name |
| `d6ad3444d96e6577d94e10594a8dd7ec36dfd623` | the packaging closure: the package now carries what its own runnable entries import and read, and a staging tree or archive is never deleted or renamed over |
| this receipt | the read-back and the package identity. Its own SHA is the branch tip after `d6ad344` and is reported after the push, not inside this file |

Every commit went through the repository's own `precommit_safety_check.py --mode staged` in the
pre-commit hook (`222`, then `4`, then `3` objects, `SAFETY_GATE: PASS` each time) and through the
pre-push history scan; no hook was skipped, nothing was force-pushed, no object was pruned.

## Push and read-back, two paths

```text
normal push        origin 706d6e5..d6ad344  poc/data-pam-d7c-b-tr-r1 -> poc/data-pam-d7c-b-tr-r1
remote read-back   git ls-remote  d6ad3444d96e6577d94e10594a8dd7ec36dfd623  refs/heads/poc/data-pam-d7c-b-tr-r1
                              at 2026-10-28T03:16:13Z, confirmed again at 03:16:28Z
local read-back    git rev-parse HEAD  d6ad3444d96e6577d94e10594a8dd7ec36dfd623 (agrees)
main               23e471cb936b421ee97e1250c3be06edf96f9937  unchanged
poc/data-pam-d7c-b-tr        398c9e852c16db85cbfa4539e859534e117ff0d2  unchanged
poc/data-pam-d7c-b-dc-r1     61621f6e3d887082ecd6a7ecc1c771f8e509a24a  unchanged
poc/data-pam-d7c-b-prep-r2   e51c5320a28bd5043e21d08a0be97e9d5612cd16  unchanged
```

No merge, no branch move, no history rewrite: every other branch reads back at the SHA the review
recorded.

## Reviewer package

Built from committed blobs at `HEAD = d6ad344` and replayed after extraction:

```text
dd1_d7c_b_tr_package_d6ad344.zip   23,729,459 bytes
sha256 b669632e07c9805d3766cb932d9e6a8d5e72968dc4e25cb3ca96070372cbe0ee
files 325   refused 6   packaging safety gate rc 0
in-package replay:  independent_recompute.py        RECOMPUTE_R1 gate 838/838   rc=0
                    dd1_d7c_b_tr_r1_native.py --verify
                                                    TR_R1_VERIFY 19/21 problems=0 excluded=2  rc=0
```

The digest of the archive is recorded here, outside the archive; the archive does not contain this
receipt's own digest. Three earlier archives of this round were superseded rather than overwritten and
still sit beside it in `review/`, each with the defect that ended it:

* `dd1_d7c_b_tr_package_706d6e5.zip` 23,455,616 B `sha256 0b7f64f2fcd3d1ad70abd179b3c97a956b90c59a45d101ab87ce512a61a3feb9`
  — inside the extracted copy the delivered `--verify` entry could not even start:
  `ModuleNotFoundError: No module named 'dd1_d7c_b_dc_run'`, because the packaging range does not carry
  an accepted module that predates it.
* `dd1_d7c_b_tr_package_706d6e5_20261028T025049Z.zip` 23,719,144 B `sha256 293bea3ed675a087d37bad803334f37cba652dc5d267018dfb02384f1d6c8e94`
  — the imports travelled, but the contract module still could not open
  `tests/dd1_d7c_b_prep/schedule.csv`, so the README's promise was still unmet.
* `dd1_d7c_b_tr_package_706d6e5_20261028T030050Z.zip` 23,727,942 B `sha256 167e12361dd1bc83f20820e2d4566514e4d99978ae96f2d2ddee535671ff4dde`
  — the replay went green (`838/838` and `19/21 problems=0`, both rc=0), but it was built while the
  packaging fix was still uncommitted, so the tool blob inside it was not the branch tip's.

The delivered archive is built at the committed tip `d6ad344`, which is the difference that matters for
"the same bytes that were tested". The six refusals on it are the round's own `.log` members: the
packaging extension rule keeps logs in the repository, where they are committed and listed by digest in
the evidence directory.

## What was measured, not restated

```text
newly tracked bytes this round   33,093,802 B (221 added files = 32,818,620 B of evidence and
                                 tooling growth over 4 modified files, 275,182 B of scripts/tests/reports)
                                 460,630 B under the task's 32 MiB (33,554,432 B)
delivered containers             32,193,607 B against the exporter's 32,505,856 B ceiling
part and whole artifacts         142 files: 134 parts, 8 whole containers
verify at the delivered directory 19 verified, 2 named excluded (the two .vcd traces), 0 problems
native round evidence directory  54 files compared with their HEAD blobs, 0 mismatches
gate                             RECOMPUTE_R1 gate 838/838, preflight 835/835, rc=0
statuses                         10 published; DYNAMIC_CHARGE_STATUS FAIL 33/37 and
                                 NOMINAL_CHARGE_STATUS FAIL 23/37 are the native round's own
                                 electrical negatives, unchanged
selftests                        contract 35, decks 19, trace 50, run 44, measure 61, r1_native 17,
                                 record 34 — 260 records, 0 failures
budget                           task 24, main ledger ceiling 22, occupied 21, RTL_PROCESS_COUNT=4
                                 from four distinct executable digests
```

## Limits held

```text
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_ACCESS=0
NEW_GUEST_CONNECTIONS=0
CANDIDATE_DUT_CHANGED=NO
OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```

`OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO` is the state of the tree at this stop and is evidenced by the
54-file comparison above; the mid-round event that temporarily made it false, and the entry fix that
closed it, are in §9 of `reports/dd1_d7c_b_tr_review_fix_r1.md` rather than smoothed over here.
