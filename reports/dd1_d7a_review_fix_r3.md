# DATA-7A-R3: the two tool repairs the third review asked for

Review input: `MicroLED_DATA7A_R2_Review_and_R3_Task_20261021.zip`, sha256
`e31cdfe918cfa54a8960f7d3e0b96c89b36ae4d5cb5e1a6ea7225491ff7cf444`, whose `REVIEW_DATA7A_R2.md`
judges the R2 tip and whose task book is stored byte-for-byte as
`reports/tasks/DATA-7A-R3.md` (sha256 `1e22f6ec768db0e812e62e5370b0f702e8a57ab22d8b32766bb08ec510f34e3a`,
10,026 bytes, identical to the file in the package).

Fixed sources: reviewed R2 tip `T2 = 01e078bbf545b9191539dc1c0de228a6d8e7749b`, R2 payload
`P2 = e151ebca59bc60df5e6e4d16fd6907e9787ded0a`, R2 handoff `D2 = ff477ae7996a6efe74bdd60d971443810daf485d`,
R1 tip `T1 = 0b64d1d62b851ac46e03a4d0250c8014984f2ef5`, DATA-6 baseline
`B = 731767519d1a51287eb5b7f4a6e4f9b8e613e990`. This round works in `D:\ic617_d7a_r3` on the new
branch `poc/data-gray-d7a-r3`, created from `T2`; `main`, `poc/data-gray-d7a`, `poc/data-gray-d7a-r1`
and `poc/data-gray-d7a-r2` were read back and then left exactly where they were — no reset, no
stash, no merge, no force, no branch moved, visibility unchanged.

Remote read-back before starting (both paths actually executed):

| path | command | result |
|---|---|---|
| Git protocol | `git -c http.proxy=http://127.0.0.1:7892 ls-remote origin` | `poc/data-gray-d7a-r2 = 01e078bb…`, `main = 23e471cb…`, `poc/data-gray-d7a = 6a1f5a19…`, `poc/data-gray-d7a-r1 = 0b64d1d6…`; no `poc/data-gray-d7a-r3` existed |
| GitHub API | `gh api repos/…/git/refs/heads` | the same four SHAs, and `poc/data-unit-1ch = 7317675…` |

The direct `git ls-remote origin` without that flag fails on this machine with `Recv failure:
Connection was reset` / `Failed to connect to github.com port 443` (three attempts, recorded), while
`api.github.com` answers — the machine's own system proxy (`127.0.0.1:7892`, read from the Windows
proxy setting, not installed or changed by this round) is what makes the Git protocol reach GitHub.
The proxy was passed per-command with `-c`, so no repository configuration was written. Every push
and read-back in this round uses the same per-invocation flag and says so.

## 0. Reproducing both findings before changing anything

Both of the reviewer's diagnostics were run against the **unmodified bytes of T2**, in a fresh copy of
the package (the fixture directories did not exist before the run, because the probes refuse to reuse
them). For both probes **rc=0 means the defect was reproduced, not that anything passed**.

Before running them, the package's `reviewer/repo/` snapshot was compared with the T2 worktree
file-by-file: `33/33 byte-identical, DIFFERENT: none, ABSENT: none`, so the diagnostics ran on the
delivered bytes and not on a paraphrase of them.

| finding | local measurement on T2 (rc=0 = reproduced) |
|---|---|
| A1 recovery ignores the backup it should read | `probe_publish_recovery.py` → `recorded_backup_ignored`: `publish()` interrupted before the second replacement with its backup complete in `<run>/publish_backup`; `recover_publish()` with no argument returned `complete=false, restored=[]`, left `dd1_d7a_cases.csv` holding the new bytes, **deleted the pending marker**, and a second call answered `needed=false` |
| A2 incomplete recovery still clears the transaction | same run, `one_backup_missing`: with one backup file removed, recovery restored the other two, answered `complete=false` and **still removed the marker**, leaving two old + one new file |
| A3 a corrupt marker reads as an empty, finished transaction | `unreadable_marker`: `{NOT_VALID_JSON` was detected (`unreadable_marker=true`) and then `recover_publish()` answered `complete=true`, restored nothing over a mixed directory and deleted the marker |
| A4 a catchable staging failure escapes without cleanup | `staging_write_failure`: the second `.new` write raised an `OSError` that escaped `publish()`; the old targets were undamaged (this is not lost data) but `d7a_publish.pending` and one `.new` were left behind |
| B a fractional number is truncated before the comparison | `probe_numeric_precision.py`: in two hash-self-consistent copies of the delivered evidence, with that file's manifest digest refreshed, `a_on_width_ns` 30 → **30.5** and `a_obs_tick_pulses` 257 → **257.5** both left the delivered re-checker at `EVIDENCE_IDENTITY: PASS (0 checks failed)`, 53 PASS lines, rc=0 |

The two corrupt copies under `review/` are diagnostics only. The committed R2 tables contain neither
30.5 ns nor 257.5 pulses, and nothing in this round says the circuit is 0.5 ns late: the defect is in
the verifier, which is exactly how the review filed it.

## 1. A — publish/recover is now a transaction with a readable identity

**Root causes.** Four separate shortcuts in `scripts/dd1_d7a_run.py` compounded:

1. `publish()` recorded the backup directory inside the marker, but `recover_publish()` ignored that
   field and defaulted to the global `PUBLISH_BACKUP`. Whenever the export passed
   `backup_dir=<run_dir>/publish_backup` — which `do_export()` always does — recovery looked in the
   wrong place, found nothing, restored nothing, and reported `complete=false`.
2. `recover_publish()` deleted the marker unconditionally, so the failed recovery above also erased
   the evidence that a transaction was unfinished; the next call said `needed=false` and a new export
   happily started a second transaction over a half-published set.
3. `pending_publish()` turned an unparseable marker into `{'unreadable_marker': True}`, and recovery
   read `state.get('previous') or {}` from it — an empty set compared as `0 == 0`, i.e. *complete*.
   A crash that damages the record also destroys the claim that anything needs recovering.
4. The backup copies, the marker write and the staging writes sat **outside** `publish()`'s `try`, so
   a catchable I/O error in any of them escaped as a raw exception, leaving the marker and `.new`
   files behind instead of either rolling back or recording an open transaction.

**Change.** The marker is now the transaction record, `d7a-publish/2`, and says everything a later
process needs without being told: `schema`, `phase`, the sorted `files` set, its own `backup`
directory (repo-relative when it can be), the digest of every file that existed before
(`previous`) and the names that did **not** (`absent`).

- `publish()` refuses to start while a transaction is outstanding, so an unfinished set cannot be
  papered over by a newer publish.
- `publish()` validates its own record with the same function the recovery uses before writing it,
  so nothing is recorded that this tool could not read back.
- every stage (backup, marker, staging, promotion, verify, cleanup) is inside the error boundary.
  A failure before the first promotion leaves the published set untouched, deletes this
  transaction's own `.new` files and its marker, and raises a `Refuse` that names the stage.
- a failure during or after promotion rolls back from the recorded backup, re-hashes every target
  against the digest the marker carries, and only then clears the marker. If the rollback or the
  marker removal itself fails, the message says `the ROLLBACK ITSELF FAILED`, the marker and the
  backup stay, and the transaction stays open.
- `recover_publish()` reads the backup location **from the marker**; a caller that passes a
  different directory gets a recorded disagreement and `complete=false` rather than a restore from
  somewhere else. A file the marker lists as previously absent is restored by deleting it, and no
  digest is ever taken of a file that does not exist.
- a marker that is not JSON, not an object, missing a field, wrongly typed, carries a non-sha256
  digest, contradicts its own file set, or declares a schema this tool does not write, is reported
  as `marker_invalid` and refused: nothing is restored, the marker stays, and a new publish is
  refused. It is never treated as an empty, already-satisfied transaction.
- cleanup is scoped to the transaction's own file names. `recover_publish()` no longer sweeps every
  `*.new`/`*.restore` in the directory, which used to be able to delete another phase's staged file.

`do_export()` keeps the same order — recover first, refuse to build while a transaction is
unfinished — and now prints the recovery record's `reason`, so the refusal says which target could
not be verified instead of only that something failed.

## 2. B — counts are integers, times are exact picoseconds

**Root cause.** `scripts/dd1_d7a_evidence_check.py` compared everything through `int(float(value))`,
which truncates before comparing: `30.5` became `30` and satisfied the 30 ns contract, and `257.5`
became `257` and satisfied the boundary-event count while never being checked as an integer at all.
The `FINITE_FIELDS` gate only asked "does this parse as a number".

**Change.** Two parse functions with different jobs, used by every comparison:

- `int_value()` / `as_count()` — `^\d+$` only. `case_id`, `frame_hz`, `time_code`, `pam_code`,
  `tick_ns`, `exp_intervals`, `full_intervals`, both `on_segments`, both `on_intervals_measured`,
  both `cfg_version` and both `obs_tick_pulses` are discrete quantities: a fraction is not a
  count, and a new `INTEGER_COUNTS` check refuses a cell that is written as one.
- `ps_value()` / `as_time()` — a plain decimal with at most three fractional digits, scaled by
  `Decimal(text) × 1000` into whole picoseconds. `a_on_width_ns`, `b_on_width_ns`, `a_t0_ns`,
  `b_t0_ns`, `a_window_end_ns`, `b_window_end_ns` and the sample `relative_ns` are compared as
  integers of ps. `TIME_PICSECOND` refuses a cell that is not a representable time (including a
  sub-picosecond claim like `30.5005`), and `SAMPLE_TIMES_EXACT` does the same for the sample
  offsets.
- the recomputations now say `width_ps == intervals × tick_ps` and `end_ps − t0_ps ==
  full × tick_ps` and `pulses == full + 1`, so a real 0.5 ns error contradicts the contract
  instead of being rounded into agreement with it.
- `contract_intervals()` takes the strict integer parse too, so a fractional code is reported as an
  illegal combination rather than crashing or being truncated.

The format is deliberately still permissive: `30`, `30.5` and `30.000` all parse, because a
fraction is a legal way to write a measurement — the delivered checker reports picoseconds. What is
no longer legal is a *value* that disagrees with the contract, and a selftest case asserts that a
correct time written with a fractional representation still passes all checks. Nothing was
re-derived from the CSV's own expectation columns and no threshold, tolerance or time endpoint was
loosened to make a tool pass.

## 3. The regressions that keep both repairs honest

Two places now exercise the repaired code, and they do different jobs.

**`scripts/dd1_d7a_publish_test.py` (new, 23 cases).** Every case builds its own fixture under
`review/dd1_d7a/publish_recovery_test/`, protects the targets plus an unrelated file and an unrelated
`.new`, and prints the stage reached, the refusal text, the process return code equivalent, the marker
and backup state and the file set. It covers, in this order:

| group | cases |
|---|---|
| positive path | `normal_publish` (new bytes in place, backups hold the old bytes, no marker, no staging file, foreign file untouched) |
| caught promotion failures | `publish_fail_first`, `publish_fail_middle`, `publish_fail_last` (each refuses with its promotion count, restores every byte, clears the marker) |
| pre-promotion failures | `staging_write_fails` (second `.new`), `marker_write_fails`, `backup_prepare_fails` — each refuses, leaves the published set intact, cleans its own staging, and leaves nothing outstanding |
| rollback that also fails | `rollback_write_fails` — the refusal says `the ROLLBACK ITSELF FAILED`, the marker stays, a new publish is refused, and once the write fault is gone `recover_publish()` completes the same transaction |
| the four T2 violations, as positives now | `interrupt_nondefault_backup` (no argument, restores from the recorded backup, byte-exact), `one_backup_missing` (two retries both refuse, then a repaired backup completes), `backup_digest_wrong`, `restore_write_fails` |
| unusable records | `marker_bad_json`, `marker_missing_fields`, `marker_wrong_types`, `marker_not_an_object`, `marker_contradicts`, `marker_bad_digest_form`, `marker_unknown_schema` — each refused, marker kept, mixed content preserved, publish refused, and a readable record for the same transaction then recovers it |
| prior state and cleanup scope | `previously_absent_target` (a target that did not exist is restored to non-existence, and no digest is taken of a missing file), `caller_backup_disagrees` (the recorded directory wins and the disagreement itself keeps the transaction open), `foreign_staging_untouched` is asserted inside the two recovery cases: a `.new` belonging to another phase survives |
| the real entry | `entry_export_refused`, `entry_export_proceeds` — labelled **BOUNDARY_DIAGNOSTIC**: `do_export()` is called with `build_artefacts` replaced by a stub, so they prove the entry refuses while a transaction is outstanding and proceeds only after a completed recovery. They are not a build and are not an export PASS. |

The script also takes a digest map of the official `results/evidence/` before and after the whole run
and fails if any file moved, and `entry_selftest()` in the runner grew from 11 to 32 assertions over
the same transaction record, so the runner's own gate covers it too.

**The write-guard matrix grew from 18 to 21 modes.** `publish_staging_write_fails`,
`publish_marker_write_fails` and `recover_uses_marker_recorded_backup` join it under the same scoring
as before — the mode passes only when the refusal it claims is the refusal that happened, the whole
evidence set is unchanged by name, content and absence, and no staging or marker file is left behind.
The recovery mode uses a non-default backup directory inside the fixture and then calls
`recover_publish()` with no argument, exactly like the export, so the T2 behaviour (recorded backup
ignored, marker deleted, `needed=false` afterwards) now fails the mode rather than passing it.

**The evidence semantic selftest grew from 7 to 15 cases.** Seven of them corrupt one cell of a
hash-consistent, digest-refreshed copy and require the named refusal:

| case | corrupted cell | refused by |
|---|---|---|
| `fractional_width_refused` | `a_on_width_ns` 30 → `30.5` | `WIDTH_RECOMPUTABLE`, `CONTRACT_RECOMPUTED` — and it asserts `FINITE_FIELDS`, `INTEGER_COUNTS` and `TIME_PICSECOND` do **not** fire, because 30.5 is a well-formed time that is simply the wrong time |
| `sub_picosecond_time_refused` | `a_on_width_ns` → `30.5005` | `TIME_PICSECOND` (a claim below the measurement's own unit) plus both recomputations |
| `fractional_boundary_count_refused` | `a_obs_tick_pulses` 257 → `257.5` | `INTEGER_COUNTS`, `CONTRACT_RECOMPUTED` |
| `fractional_segments_refused` | `a_on_segments` 1 → `1.5` | `INTEGER_COUNTS` and both recomputations |
| `fractional_tick_refused` | `tick_ns` 30 → `30.5` | `INTEGER_COUNTS` (the contract's tick is an integer count of ns) |
| `fractional_endpoint_refused` | `a_window_end_ns` → `18545.5` | `WIDTH_RECOMPUTABLE`, `CONTRACT_RECOMPUTED`, not the parse gates |
| `fractional_code_refused` | `time_code` 1 → `1.5` | `INTEGER_COUNTS`, `CONTRACT_RECOMPUTED` |
| `legal_fractional_time_representation_passes` | `30` → `30.000`, `10865` → `10865.000`, `18545` → `18545.000` | must still be **rc=0, no failure** — the format is not the crime |

Each case reports the checks it hit, not merely "non-zero".

## 4. What was frozen, and what the waveforms in this round actually are

`git diff --name-only 01e078bb… -- rtl tests scripts/dd1_d7a_check.py scripts/dd1_d7a_trace.py
reports/dd1_d7a_contract.md scripts/repo_safety_rules.py scripts/test_safety_rules.py
reports/tasks/DATA-7A.md reports/tasks/DATA-7A-R1.md reports/tasks/DATA-7A-R2.md
scripts/dd1_d7a_validate_handoff.py` prints nothing: the circuit, the testbench, the waveform
checker and reader, the contract, both shared safety tools, the original task books and the handoff
validator are byte-for-byte T2. Only `scripts/dd1_d7a_run.py` and
`scripts/dd1_d7a_evidence_check.py` changed, plus the new `scripts/dd1_d7a_publish_test.py`, the R3
report, the R3 task-book copy and the re-published evidence tables.

**No new simulation was started for R3.**

```text
NEW_RTL_SIMULATIONS = 0
REUSED_RTL_RUN      = r2_20261021
```

The run directory in `review/dd1_d7a/r2_20261021` keeps the R2 run_id on purpose: `--export` derives
the environment and manifest `run_id` from the directory name and `RUN_ID_CHAIN` requires the tables,
the environment and the manifest to agree, so renaming an old run to a new id would be exactly the
thing this round must not do. The traces are the six files whose digests the export verifies before
judging anything:

| trace | sha256 |
|---|---|
| trace_pure_t30.vcd | see `trace_digests` in `results/evidence/dd1_d7a_manifest.json` |
| trace_pure_t50.vcd | ibid |
| trace_hyb_t120.vcd | ibid |
| trace_hyb_t200.vcd | ibid |
| trace_control.vcd | ibid |
| trace_mixed.vcd | ibid |

They were **re-judged, not re-labelled**: `_check_identity()` compares the cached run's
RTL/TB/checker/reader digests against the bytes on disk (all four are the frozen T2 digests, so the
cached PASS counts are attributable), and `_rejudge()` re-derives all 1536 main rows, 43 control and 6
mixed rows from the trace bytes with `_same()` demanding field-by-field agreement before anything is
published. `dd1_d7a_environment.json` now carries a `waveform_provenance` block that states
`simulations_started_by_this_export: 0`, which revision produced the traces and which revision
exported them, and the R2 run summary was written before the runner stamped a revision, so the block
says `NOT_STAMPED_BY_THE_RUNNER_THAT_MADE_THIS_RUN` rather than inventing an attribution.

The four measured tables did not move at all:

```text
git diff --numstat 01e078b… -- results/evidence/dd1_d7a_cases.csv
                                      results/evidence/dd1_d7a_control_cases.csv
                                      results/evidence/dd1_d7a_negative.csv
                                      results/evidence/dd1_d7a_edge_samples.csv
-> no output: byte-identical to T2
```

Only the identity records changed (`dd1_d7a_manifest.json`, `dd1_d7a_environment.json`,
`dd1_d7a_write_guard.txt`, `dd1_d7a_checker_selftest.txt`), plus the new
`dd1_d7a_publish_test.txt` transcript and the regenerated freeze transcript. A tool repair that
changed a measured value would have been visible here as a diff in the first four files.

## 5. Repair verification on the repaired bytes

Every step below was re-run after the final byte set, and the whole command transcript is committed
as `results/evidence/dd1_d7a_freeze_security.txt` (14,807 bytes, sha256
`f6f703c570324856951e1f25fe6323a29b12fec537a12137b9c02b54d06c127b`).

| step | command | rc | result |
|---|---|---|---|
| 0a frozen set | `git diff --name-only 01e078b… -- <7 frozen paths>` | 0 | no output |
| 1 selftest | `python scripts/dd1_d7a_run.py --selftest --out review/dd1_d7a/r2_20261021` | 0 | `CHECKER_SELFTEST: PASS`, `ENTRY_SELFTEST: PASS` — 32 entry assertions (was 11) |
| 2 dry run | `python scripts/dd1_d7a_run.py --dry-run` | 0 | `DRY_RUN: PASS`, 1536 planned, both Spectre digests MATCH |
| 3 safety rules | `python scripts/test_safety_rules.py` | 0 | `SAFETY_RULES_TEST: PASS` (secret 7/7, vendor 4/4, path 10/10, ext 2/2, reject 6/6) |
| 4 provenance | `python scripts/provenance_check.py` | 0 | 406 files, 528 labelled lines, 0 violations |
| 5 device count | `python scripts/netlist_stats.py` | 0 | `DEVICE_COUNT_CHECK: PASS` |
| 6 evidence re-check | `python scripts/dd1_d7a_evidence_check.py` | 0 | `EVIDENCE_IDENTITY: PASS (0 checks failed)` over **56** checks (was 53; `INTEGER_COUNTS`, `TIME_PICSECOND`, `SAMPLE_TIMES_EXACT` are new) |
| 6b numeric semantics | `python scripts/dd1_d7a_evidence_check.py --selftest` | 0 | `EVIDENCE_SELFTEST: PASS (15 cases)` — each corruption names the checks that fired |
| 7 transaction regression | `python scripts/dd1_d7a_publish_test.py` | 0 | `PUBLISH_RECOVERY_TEST: PASS (23 cases, 0 failed checks)`, official evidence directory `changed=none` |
| export | `python scripts/dd1_d7a_run.py --export --out review/dd1_d7a/r2_20261021` | 0 | 8 files published, `PUBLISH_TRANSACTION: … marker=cleared … marker_schema=d7a-publish/2` |
| guard matrix | `python scripts/dd1_d7a_run.py --write-guard-demo --out review/dd1_d7a/r2_20261021` | 0 | `WRITE_GUARD: PASS (21 modes, 10 target files)` |
| synthesis (reused record) | `review/dd1_d7a/r2_20261021/synth_summary.json` | 0 | entry rc=0, 151 cells, 6 `$adff` + 15 `$adffe` = 21 async-reset registers, `stat_parse=parsed` |
| mutation (reused record) | `review/dd1_d7a/r2_20261021/mutants.json` | — | 16/16 detected: 14 functional (each fault observed in its own trace first), 2 diagnostic, `not_exercised=[]` |
| 8b/8c reviewer probes on the repaired tools | `probe_publish_recovery.py`, `probe_numeric_precision.py` | 1, 1 | all four A violations `violation_reproduced=false`; both B cases `verifier_rc=1` |
| 8d/8e same probes on unmodified T2 | same two scripts in `review/r3_repro_t2/` | 0, 0 | defects still reproduce there, which is the starting state of this round, not a result |
| history scan | `python scripts/precommit_safety_check.py --mode history` | 0 | `SAFETY_GATE: PASS`, 1363 objects |
| objects scan | `python scripts/precommit_safety_check.py --mode objects` | 1 | `BLOCKED <blob:955497fb18ac>` — pre-existing, reported as found |

What the repaired re-checker now answers to the two corruptions the review used, in the delivered
selftest fixtures (whole-evidence copies, digest refreshed):

```text
fractional_width              a_on_width_ns=30.5       rc=1 hit=['WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED']
                              and FINITE_FIELDS / INTEGER_COUNTS / TIME_PICSECOND deliberately NOT fired
sub_picosecond_time_refused   a_on_width_ns=30.5005    rc=1 hit=['TIME_PICSECOND', 'WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED']
fractional_boundary_count     a_obs_tick_pulses=257.5  rc=1 hit=['INTEGER_COUNTS', 'CONTRACT_RECOMPUTED']
fractional_segments           a_on_segments=1.5        rc=1 hit=['INTEGER_COUNTS', 'WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED']
fractional_tick               tick_ns=30.5             rc=1 hit=['TICK_SET', 'INTEGER_COUNTS', 'WIDTH_RECOMPUTABLE']
fractional_endpoint           a_window_end_ns=18545.5  rc=1 hit=['WIDTH_RECOMPUTABLE', 'CONTRACT_RECOMPUTED']
fractional_code               time_code=1.5            rc=1 hit=['INTEGER_COUNTS', 'COMBINATION_LEGAL', 'COMBINATION_COMPLETE']
legal_fractional_time         30 -> 30.000 etc.        rc=0 fails=[]            (a legal representation, not an error)
```

**One disclosure about the reviewer's own probe harness.** `probe_numeric_precision.py` copies only
its `REQUIRED_EVIDENCE` list (8 files) into the fixture, while the delivered manifest now also hashes
the 9th published file `dd1_d7a_publish_test.txt`. So when that probe runs against the R3 evidence it
reports `verifier_rc=1` with `EVIDENCE_DIGEST` alongside the numeric labels — i.e. one of its failure
reasons is the probe's own incomplete copy, not the corruption. The clean statement of the same
corruption is the delivered `--selftest` above, which copies the whole evidence directory and is
refused by the numeric gates only. Both are quoted so the reader can tell them apart.

## 6. Commands, in order, that reproduce this round

```text
python scripts/dd1_d7a_run.py --selftest    --out review/dd1_d7a/<run_id>
python scripts/dd1_d7a_run.py --dry-run
python scripts/dd1_d7a_publish_test.py
python scripts/dd1_d7a_run.py --export      --out review/dd1_d7a/<run_id>
python scripts/dd1_d7a_run.py --write-guard-demo --out review/dd1_d7a/<run_id>
python scripts/dd1_d7a_evidence_check.py
python scripts/dd1_d7a_evidence_check.py --selftest
python scripts/test_safety_rules.py && python scripts/provenance_check.py && python scripts/netlist_stats.py
```

with `<run_id>` = `r2_20261021` for this round (the reused frozen run, §4). `--run-rtl`, `--mutants`
and `--synth` were **not** re-run: no circuit source changed and the reuse is declared rather than
relaunched; a reviewer who wants fresh waveforms runs those three against this same directory name.

## 7. Files this round delivered

Tracked and changed: `scripts/dd1_d7a_run.py` (141,171 bytes, sha256
`f868f763104b16637f959b2902b5a7bcb63b261dc8333c32052021673f8a039b`),
`scripts/dd1_d7a_evidence_check.py` (36,405, `d4369e80413e5f014ba9821223e11a121ac01663dc1dc025a6b6de3c479da80a`),
`scripts/dd1_d7a_bundle.py` (7,892, `f34e7ce8f6ac5445b251e42a9d471d6953e9f8261ed3bb49565495e1c457f454`),
and the four re-published identity records plus the freeze transcript.

New: `scripts/dd1_d7a_publish_test.py` (32,596, `77780ac7bd76758b847610367ff7142c91af21772c0284826448bcc6df7080d5`),
`results/evidence/dd1_d7a_publish_test.txt` (7,335, `5e7c5d3aa4a8bc6c860028f67dd57f5cc7f2e2755014e26403385eb9c3c0a143`),
`reports/tasks/DATA-7A-R3.md` (10,026, byte-identical to the task book in the package), and this
report.

`git diff --name-only 01e078b… -- scripts rtl tests reports` lists only the three tracked scripts
above; the new files are untracked until the payload commit, which is why they appear in
`git status` and not in that diff. No Spectre, Scan, Data-6, PDK, OA, CDF, symbol or `cds.lib` file
was touched, and no VM/Cadence/Spectre/OA tool was started.

**Line endings, and why it mattered here.** This machine has `core.autocrlf=true`, so a file whose
working copy contains CRLF is normalised to LF when it is staged — the bytes a reviewer reads out of
git would then no longer hash to the value the manifest recorded for that file. The first version of
the publish transcript was assembled from a subprocess pipe and carried 40 CRLF pairs, so the export
hashed bytes that git would not store. It was rewritten with LF, the export re-run, and before
committing the staged set is compared against the objects git actually holds:

```text
python review/verify_blobs_vs_manifest.py     # manifest digest vs `git cat-file blob :<path>`
```

The transcript builder now normalises CRLF before writing, and the check above is part of the
delivery sequence rather than an assumption.

## 8. Open items this round did not close

* The reused run's `run_summary.json` predates the runner stamping `task_revision`, so
  `waveform_provenance.produced_by_task_revision` reads `NOT_STAMPED_BY_THE_RUNNER_THAT_MADE_THIS_RUN`
  instead of naming `DATA-7A-R2`. The four source digests in that record do identify the frozen
  bytes, and the export refuses any cached run whose digests differ; a fresh `--run-rtl` would carry
  the stamp.
* Multi-file power-loss / SIGKILL atomicity is still not provided and is still not claimed: the
  guarantee is a caught-failure rollback plus a marker that a later process can use, and the marker
  mechanism is now what this round proves works.
* The unreachable blob `955497fb18ac` keeps the `--mode objects` scan at FAIL on this machine,
  exactly as in the two previous rounds. Nothing was GCed, printed or exempted.
* Yosys statistics parsing for the reviewer's Linux 0.33 format is unchanged and still refused by
  `synth_gate_ok()`; the task said not to rewrite it for a foreign format, so it stays.
* The `do_export()` coverage is a labelled boundary diagnostic with a stubbed builder. A full
  end-to-end export on the real builder is the `--export` step in §5, which did run for real; the
  boundary cases only cover the recovery precondition in the entry.
* Nothing in this round is an analogue, optical, layout or timing-closure claim; `pam_sel` remains a
  select code.


