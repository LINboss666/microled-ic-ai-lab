# DATA-7A-R4: the publish cleanup boundary

Review input: `MicroLED_DATA7A_R3_Review_and_R4_Task_20261021.zip`, sha256
`5caaf213533f6e6d204d5d752c531ccbb549d3a008d817e421a42c1d7eefbcc7` (measured on this machine before
extraction), whose `REVIEW_DATA7A_R3.md` judges the R3 tip and whose task book is stored
byte-for-byte as `reports/tasks/DATA-7A-R4.md` (9,694 bytes, sha256
`2b91892a8b0e93bd336baff41d7b3dad105c663633b8e37441ee48198c2efac0`, identical to the file in the
archive).

Fixed sources: reviewed R3 tip `T3 = 33cd863093961d571aca3bd726beea32cb50ecfd`, R3 payload
`P3 = 88e7a740cb7107bba93816beb452dc42a8a10b4b`, R2 tip `T2 = 01e078bbf545b9191539dc1c0de228a6d8e7749b`,
DATA-6 baseline `B = 731767519d1a51287eb5b7f4a6e4f9b8e613e990`. This round works in `D:\ic617_d7a_r4`
on the new branch `poc/data-gray-d7a-r4`, created from `T3`. No older branch or worktree was moved,
reset, merged or rewritten.

Remote read-back before anything was written, both paths executed:

| path | command | result |
|---|---|---|
| Git protocol | `git -c http.proxy=http://127.0.0.1:7892 ls-remote origin` | `poc/data-gray-d7a-r3 = 33cd8630…`, `main = 23e471cb…`, `-r2 = 01e078bb…`, `-r1 = 0b64d1d6…`, `poc/data-gray-d7a = 6a1f5a19…`, `poc/data-unit-1ch = 7317675…`; no `poc/data-gray-d7a-r4` existed |
| GitHub API | `gh api repos/…/git/refs/heads` | the same values for all six refs |

The proxy is this machine's own existing WinINET setting (`127.0.0.1:7892`), passed per command; a
bare `git ls-remote` to `github.com:443` does not connect here. No git configuration was written.

**Scope.** The review closed the numeric truncation group in R3 and left exactly one blocker group:
publish paths that fail to finish their cleanup must not lose the transaction record. Per the task
book, `scripts/dd1_d7a_evidence_check.py` is now frozen — this round does not touch the numeric
re-checker at all.

## 0. Reproducing the three paths on unmodified T3

The package's `reviewer/repo/` snapshot was compared with the T3 worktree first: **37/37 files
byte-identical, none missing**, so the diagnostic ran on the delivered bytes rather than on a
paraphrase. A fresh copy of the package was used because `probe_cleanup_failures.py` refuses to reuse
a fixture directory (`repo/review/dd1_d7a/reviewer_r3_cleanup` did not exist beforehand).

```text
$ python reviewer/probe_cleanup_failures.py        rc=0
partial_second_staging_write   REPRODUCED=True  own_staging=['dd1_d7a_control_cases.csv.new']  marker=False  builder_reached=True
prepromotion_cleanup_denied    REPRODUCED=True  own_staging=['dd1_d7a_cases.csv.new']          marker=False  builder_reached=True
rollback_cleanup_denied        REPRODUCED=True  own_staging=['dd1_d7a_control_cases.csv.new']  marker=False  builder_reached=True
ALL_THREE_DEFECTS_REPRODUCED: True
```

rc=0 here means the three defects reproduce. It is not a pass, and nothing in these fixtures is
formal evidence. Per case, from `probe_cleanup_failures.json` on T3:

| case | what the delivered tool did | what was preserved |
|---|---|---|
| `partial_second_staging_write` | the second `.new` had bytes on disk, the write then raised `ENOSPC`; `publish()` refused, **deleted the marker** and left `dd1_d7a_control_cases.csv.new` behind | `old_targets_unchanged=true`, `foreign_unchanged=true`; both later `recover_publish()` calls answered `{'needed': False}` |
| `prepromotion_cleanup_denied` | the staging write failed and deleting the first `.new` kept raising `EACCES`; the refusal even named the leftover, but the marker was still deleted | same: old targets and foreign files intact, two `{'needed': False}` answers, so the outstanding transaction disappeared |
| `rollback_cleanup_denied` | promotion 2 failed, the rollback put the old bytes back, then deleting a remaining `.new` kept failing; the refusal said **"the previous set is restored"** and the marker was deleted | same |

In all three, the reviewer's fourth observation held on this machine too: calling the real
`do_export()` afterwards (with a builder sentinel that only raises — `BOUNDARY_DIAGNOSTIC`) reached
the builder, because the directory no longer advertised an unfinished transaction.

No old CSV was damaged and no formal export was falsely recorded as successful. The defect is that an
incomplete cleanup discarded the recoverable transaction identity.

## 1. Root causes

Three separate shortcuts in `scripts/dd1_d7a_run.py`, all inside the path R3 had just repaired:

1. `publish()` staged each artefact with `staged.append(tmp)` **after** `_fsync_write(tmp, ...)`. A
   `write()`, `flush()` or `fsync()` error can happen after the file exists and already holds bytes;
   that file was therefore not in the list `_discard_staging()` consults, so it survived while the
   marker was removed.
2. The pre-promotion handler called `_discard_staging()` and captured the list of files it could not
   delete, but only used that list to decorate the message — the marker was deleted regardless. A
   refusal that says "could not be removed" and then hides the transaction is self-contradictory.
3. `_rollback()` called `_discard_staging()` and **discarded its return value**. When the deletion of
   the transaction's own staging file failed, the rollback still returned normally, so the caller
   cleared the marker with the words "the previous set is restored" — reporting a closed transaction
   over a directory that still held this transaction's staging file.

The common shape: restoring content and closing the transaction were treated as one event, and the
cleanup result was not part of any decision.

## 2. What R4 changed

All of it is inside `scripts/dd1_d7a_run.py`'s publish/cleanup path plus its own tests, and in
`scripts/dd1_d7a_publish_test.py`.

1. **A staging file is registered before it is written.** `publish()` appends the `.new` path to the
   transaction's own list, then writes it. A partial or refused write therefore leaves a file that
   the cleanup knows about, and a file that was never created is simply skipped. Nothing outside
   this transaction's registered names is ever deleted, so another phase's `.new` is still untouched.
2. **Cleanup participates in the closing decision.** `_discard_staging()` still returns the names it
   could not delete, and both handlers now branch on it:
   * pre-promotion failure with a leftover → the refusal says `the cleanup of this transaction FAILED
     (<names>)`, and **the marker and the backup are kept**; the transaction stays outstanding;
   * promotion failure where the content rollback succeeded but cleanup failed → a separate message:
     `the previous set IS restored and verified, but the cleanup of this transaction FAILED (…)`,
     again keeping the marker. A damaged restore still takes the pre-existing
     `the ROLLBACK ITSELF FAILED` branch, which says the set is **not** restored.
   So "the bytes are back" and "the transaction is closed" are now two judgements, reported apart.
3. **Unfinished cleanup keeps refusing, and recovers when the fault goes.** While a deletion is
   denied, `recover_publish()` already records `a staging file of this transaction could not be
   deleted` in `failed`, so `complete=false` and `marker_kept=true` on every retry; `publish()`
   refuses to start a new transaction while a marker exists, and `do_export()` refuses before
   building. Once the deletion works, the **same** marker restores every target (digest for files
   that existed, deletion for files recorded as absent), verifies them, removes only this
   transaction's own temporary files, and then clears the marker.
4. **Nothing was relaxed to get there.** No exception is swallowed, no leftover comparison is
   skipped, the recovery gate is not disabled, and no "any non-zero counts as fine" rule was added.
   Hardware-level multi-file power-loss atomicity is still not claimed.

## 3. Coverage added for these paths

`scripts/dd1_d7a_publish_test.py` grew from 23 to **26 cases**, each in its own fresh fixture with
the three targets, one unrelated file and one unrelated `.new` protected, and with the stage, refusal
text, marker/backup state and file digests printed:

| new case | what it proves |
|---|---|
| `partial_staging_write` | the second `.new` really carries `PARTIAL_BYTES_BEFORE_ENOSPC` when `ENOSPC` is raised; the publish still refuses, the partial file is cleaned as the transaction's own, the published set is intact, no marker survives, the foreign `.new` is untouched, `recover_publish()` reports nothing outstanding, and the real entry legitimately gets past the recovery gate (labelled `BOUNDARY_DIAGNOSTIC`, the sentinel aborts, so this is not an export pass) |
| `prepromotion_cleanup_denied` | a staging failure whose cleanup keeps failing: the refusal names the cleanup as failed, the marker stays outstanding, **two** `recover_publish()` calls both return `complete=false` with the deletion listed in `failed`, a new `publish()` is refused, the real `do_export()` does **not** reach the builder, and the targets are intact all the while |
| `rollback_cleanup_denied` | a promotion failure whose content rollback succeeds but whose cleanup keeps failing: the refusal separates "IS restored and verified" from "cleanup FAILED", the marker is kept, two retries stay incomplete, the entry stays behind the gate, and the rolled-back targets hash equal to the old generation |

Both denial cases end with the same shared tail (`case_finish_then_recover`): after the fault is
lifted, the same transaction closes (`complete=true`, marker gone, own staging gone, targets equal to
the old generation, unrelated content unchanged) **and a normal publish works again** — so the repair
is not "fail forever". The persistent-fault requirement is honoured by keeping the injected
`os.remove` refusal installed across the whole retry sequence (`FaultWindow`), rather than letting
the first exception lift it.

`entry_selftest()` grew from 32 to **49 assertions**, covering the same three paths at the runner's own
gate: partial staging write cleaned, and for each of the two denial phases — the refusal wording, the
marker surviving, both retries staying outstanding, a new publish refused, the targets intact, the
recovery closing after the fault is lifted, and no leftover of this transaction.

The write-guard matrix grew from 21 to **22 modes** with `publish_partial_staging_write`, scored under
the same rule as every other mode: the refusal it claims is the refusal that happened, the whole
evidence set unchanged by name, content and absence, and no staging or marker file left behind. The
two *persistent*-cleanup-failure cases are deliberately not in that table: its scoring requires the
directory to end unchanged, which is the opposite of a correctly-stuck transaction, so they live in
the regression script where their expected end state can be stated.

## 4. Documentation corrections carried from R3

The review listed two non-blocking document items at T3, both handled here without erasing history:

1. **Input ZIP digest.** The first paragraph of `reports/dd1_d7a_review_fix_r3.md` ends the R2 review
   package digest with `444`. Re-hashing that archive on this machine gives
   `e31cdfe918cfa54a8960f7d3e0b96c89b36ae4d5cb5e1a6ea7225491ff7cf44e`, so the last character was
   transcribed wrong. The original sentence is kept and annotated in place, and an
   `## Erratum, added by DATA-7A-R4` section at the end of that file states the measured value, names
   the two other places that carried it at T3 (`reports/agent_handoffs/DATA-7A.md` in the R3 section
   and `review_package_sha256` in the T3 delivery JSON), and records that the byte-for-byte task-book
   copy was verified against the file inside the archive rather than against that string. The R4
   delivery JSON carries both values explicitly (`prior_review_package_sha256_erratum`).
2. **`git diff --check` at T3.** It reported rc=2 for one new blank line at the end of that report.
   This file now ends with a single newline, so the R3→R4 range is checked again below and reported
   with whatever it actually returns rather than being asserted clean.

No measurement, command result or conclusion in the R3 report changed because of this: the defect was
a transcription of a digest string, not of a number.

## 5. Frozen files, reuse and what this round did not touch

`git diff --name-only 33cd863… -- <the thirteen frozen paths of the task book>` prints nothing, so
the circuit, the testbench, the waveform checker and reader, **the numeric evidence re-checker**, the
contract, both shared safety tools, the handoff validator and the four task books up to R3 are
byte-for-byte T3. `scripts/dd1_d7a_evidence_check.py` is in that list: the numeric work the review
closed in R3 was not rewritten here, and the re-checker still reports the same 56 checks and the same
15 semantic selftest cases on the evidence this round publishes.

Changed, and all of it inside the scope the task book allows:

```text
scripts/dd1_d7a_run.py              publish/cleanup path + entry selftest + write-guard modes + revision stamp
scripts/dd1_d7a_publish_test.py     23 -> 26 cases (three new R4 cases and the shared fault-lifted tail)
scripts/dd1_d7a_bundle.py           the required-file table for the R4 deliverables
reports/dd1_d7a_review_fix_r3.md    erratum annotation + erratum section + single trailing newline
reports/dd1_d7a_review_fix_r4.md    this report
reports/tasks/DATA-7A-R4.md         byte-exact copy of the task book
results/evidence/dd1_d7a_*          re-published identity records (see the table below)
```

Reuse, stated rather than implied:

```text
NEW_RTL_SIMULATIONS = 0
REUSED_RTL_RUN      = r2_20261021
```

The run directory keeps the R2 run_id because `--export` derives the manifest and environment
`run_id` from the directory name and the re-checker's `RUN_ID_CHAIN` requires the tables, the
environment and the manifest to agree; renaming an old run to an R4 id is exactly what this round
must not do. The export re-verifies the four generating sources (`rtl/tb/checker/reader`) against the
cached run record before judging anything, then re-derives all 1536 main rows, 43 control rows and 6
mixed rows from the six VCD bytes and requires field-by-field agreement with the cached rows before
publishing. `dd1_d7a_environment.json` carries the `waveform_provenance` block with
`simulations_started_by_this_export: 0`, the six trace digests and the generating-source digests, and
it still reports `produced_by_task_revision: NOT_STAMPED_BY_THE_RUNNER_THAT_MADE_THIS_RUN` because the
R2-era `run_summary.json` predates that stamp — the report says so instead of inventing an attribution.

## 6. Measured state on the final bytes

Every step below was re-run after the last edit, and the whole command transcript is committed as
`results/evidence/dd1_d7a_freeze_security.txt` (16,595 bytes, sha256
`9476bbed6ed1837059cb37cfb14dcb7ec23fb2bdd7d2a89b9cc3aacba4e73664`, no CRLF).

| transcript step | command | rc | result |
|---|---|---|---|
| 0a frozen set | `git diff --name-only 33cd863… -- <13 frozen paths>` | 0 | no output |
| 0b scope | `git diff --name-only 33cd863… -- scripts rtl tests reports` | 0 | three tracked scripts: `dd1_d7a_run.py`, `dd1_d7a_publish_test.py`, `dd1_d7a_bundle.py` |
| 1 selftests | `python scripts/dd1_d7a_run.py --selftest --out review/dd1_d7a/r2_20261021` | 0 | `CHECKER_SELFTEST: PASS`, `ENTRY_SELFTEST: PASS` — **49** entry assertions |
| 2 dry run | `python scripts/dd1_d7a_run.py --dry-run` | 0 | `DRY_RUN: PASS`, 1536 planned, both frozen Spectre digests MATCH |
| 3 safety rules | `python scripts/test_safety_rules.py` | 0 | `SAFETY_RULES_TEST: PASS` (7/7, 4/4, 10/10, 2/2, 6/6) |
| 4 provenance | `python scripts/provenance_check.py` | 0 | 408 files, 528 labelled lines, 0 violations |
| 5 device count | `python scripts/netlist_stats.py` | 0 | `DEVICE_COUNT_CHECK: PASS` |
| 6 evidence re-check | `python scripts/dd1_d7a_evidence_check.py` | 0 | `EVIDENCE_IDENTITY: PASS (0 checks failed)`, **56** checks — the re-checker itself is the frozen T3 file |
| 6b semantic selftest | `python scripts/dd1_d7a_evidence_check.py --selftest` | 0 | `EVIDENCE_SELFTEST: PASS (15 cases)` |
| 7 transaction regression | `python scripts/dd1_d7a_publish_test.py` | 0 | `PUBLISH_RECOVERY_TEST: PASS (26 cases, 0 failed checks)`, official evidence directory unchanged |
| 7b R3 probe on R4 tools | `probe_publish_recovery.py` | 1 | the four R3 violations stay closed (no regression) |
| 8b cleanup probe on R4 tools | `probe_cleanup_failures.py` | 1 | `ALL_THREE_DEFECTS_REPRODUCED: False`; per case: partial write leaves nothing, both denial cases keep the marker with two `complete=false` retries, and the entry does not reach the builder |
| 8c same probe on unmodified T3 | `probe_cleanup_failures.py` | 0 | `ALL_THREE_DEFECTS_REPRODUCED: True` — the reproduction that opened this round, not a result |
| 8d numeric reference | `probe_numeric_full_copy.py` | 0 | `all_pass: true`: correct data and a legal `30.000` pass, `30.5` and `257.5` refused by the named numeric checks only |
| export | `python scripts/dd1_d7a_run.py --export --out review/dd1_d7a/r2_20261021` | 0 | 8 files published, `PUBLISH_TRANSACTION: … marker=cleared … marker_schema=d7a-publish/2` |
| guard matrix | `python scripts/dd1_d7a_run.py --write-guard-demo --out review/dd1_d7a/r2_20261021` | 0 | `WRITE_GUARD: PASS (22 modes, 10 target files)` |
| history scan | `python scripts/precommit_safety_check.py --mode history` | 0 | 154 commits, `SAFETY_GATE: PASS` |
| objects scan | `python scripts/precommit_safety_check.py --mode objects` | 1 | `BLOCKED <blob:955497fb18ac>` — pre-existing, reported as found |
| whitespace | `git diff --check 33cd863…` | 0 | clean, including the R3 EOF blank line |

Delivery digests (all LF, and every manifest-listed evidence file re-hashed from disk after the
transcript regeneration: 8/8 match, and the run-directory `checker_selftest.txt` is identical to the
published one, so the transcript's own selftest re-run changed nothing):

```text
scripts/dd1_d7a_run.py              151,808  dbb544f5483326e6dbe2d1319504a92675ef5d493b9ba1de0842bddb2f34f046
scripts/dd1_d7a_publish_test.py      43,617  ff7cc14cbe9272b67121788fcccdb30b94a94908b63c78a776d1cb26d24bef73
scripts/dd1_d7a_bundle.py             7,983  f51fef9edbcff244dab4352396f43030cab7324bf0c6b96479f171bb69e5f2ae
scripts/dd1_d7a_evidence_check.py    36,405  d4369e80413e5f014ba9821223e11a121ac01663dc1dc025a6b6de3c479da80a  (frozen = T3)
reports/dd1_d7a_review_fix_r4.md     14,736  29170c9289c0731fbb083cf3f320719f40e3202ad9e6bf5c5a74576f08f6bbf1
reports/dd1_d7a_review_fix_r3.md     29,643  66126f0d244dd19635fea9f4d96af9ff5c4f34d5084dac1cdf73f0ae6c0ed244  (erratum)
reports/tasks/DATA-7A-R4.md           9,694  2b91892a8b0e93bd336baff41d7b3dad105c663633b8e37441ee48198c2efac0
results/evidence/dd1_d7a_manifest.json      8,775  a8ef8fa7412546087a8efd03807a72cdb91664cadc0724ced5a8d6e915ab628d
results/evidence/dd1_d7a_environment.json   6,261  1fbde1921fb94b1cff08c107f656f8410b9dfdadeec04eb06bfbef16e1a2bf1b
results/evidence/dd1_d7a_write_guard.txt    8,656  1cde5ea616d6418bac949014b9a1278e993390d68e0fde20908657590d0c52f9
results/evidence/dd1_d7a_checker_selftest.txt 12,574  41b8f6e0fa7b51860ebfa5553e8d53e99ac9a0f8e3475a2ead6ccfed10fa7771
results/evidence/dd1_d7a_publish_test.txt    8,552  66544963d5187afd2caba00c2feea4f5e2eea0b8878e95b71bb79e6c84dad096
```

The four measured tables (`cases.csv`, `control_cases.csv`, `negative.csv`, `edge_samples.csv`) are
again byte-identical to T3, so the values in them are the same 1536 / 43 / 6 / 16-record evidence this
review already accepted; what changed is the tool identity records (manifest, environment, write
guard, checker selftest) plus the extended publish transcript.

## 7. Reproducing this round, and what it does not close

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

with `<run_id>` = `r2_20261021`, the reused frozen run described in §5. `--run-rtl`, `--mutants` and
`--synth` were not re-run: no circuit source changed, and reuse with declared digests is what the task
book allows. The reviewer's three diagnostics are re-run inside the freeze transcript with their
fixtures rebuilt each time.

Open, unchanged from before and not papered over:

* Multi-file power-loss and SIGKILL atomicity is still not provided and still not claimed. What this
  round adds is that the marker-based recovery path cannot be silently closed while its own cleanup
  is unfinished.
* The cleanup failures are reproduced by injected `EACCES`/`ENOSPC` in private fixtures. A real disk
  that refuses deletion is not reproduced here; the guarantee is about the record surviving the
  refusal, not about emulating a specific filesystem.
* The two `do_export()` cases stub the artefact builder and are labelled `BOUNDARY_DIAGNOSTIC`; they
  cover the entry gate, never a build. The real export ran for full in the row above.
* `waveform_provenance.produced_by_task_revision` still reads `NOT_STAMPED_…` for this reused run; a
  fresh `--run-rtl` would carry the stamp.
* The unreachable blob `955497fb18ac` keeps the `--mode objects` scan at FAIL on this machine, as
  reported in the three previous rounds. Nothing was GCed, printed or exempted; a clean cloud clone
  passing does not prove otherwise.
* The Linux Yosys 0.33 statistics format is still refused by `synth_gate_ok()` on this machine, which
  is the behaviour the R3 task said not to change.
* No analogue, optical, layout or timing-closure claim: `pam_sel` remains a select code, and DATA-7B,
  MOS PWM, eight-level PAM, current integration, the LUT, the array, layout and any VM/Cadence/Spectre
  or OA work were not started.


