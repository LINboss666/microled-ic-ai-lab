# DATA-7A-R1: what the independent review found, and what this revision changed

Review input: `MicroLED_DATA7A_Independent_Review_REWORK_20261020.zip`, sha256
`312c19dcd73c2945e7d6309575115b11cab5f429c9a588a341b5363c15080cec` (the review record itself
`REVIEW_DATA7A.md` is `379dfc9bf8368311327d43c3244ae84d0323afebc8d1676409a6b8b4bd189777`; this
revision is a copy of the task book at `reports/tasks/DATA-7A-R1.md`, sha256
`3262262ef9e46d16f1bf591405da40be2f56ed466b0fdba030b62ea871992cc9`, so the instructions are readable
from the repository without the chat).

Reviewed delivery `D` = `6a1f5a192f3f1618499335c4365d717bfcadef39`, DATA-6 baseline
`B` = `731767519d1a51287eb5b7f4a6e4f9b8e613e990`, payload of the reviewed round
`P` = `ef6737d40912b91197df4c0954eee6edcff55ee0`. Branch `poc/data-gray-d7a-r1`, created from `D` in
a separate worktree; `D` and its branch were not moved, merged or rewritten.

## 0. Reproducing the review before changing anything

All five findings were reproduced locally against the **unmodified bytes of `D`** (RTL digest
`04e5aadf80dcfe0654a65a9b718b6402479101e70f7b8606ed5ffee0955a6b48`), on Windows with Icarus
14.0 (devel) and Yosys 0.70+176, i.e. different binaries from the reviewer's Linux Icarus 12 /
Yosys 0.33:

| review item | local reproduction | reviewer's own number |
|---|---|---|
| R1 abort re-authorisation | `probe_protocol` gave `A_START_ONLY t=1366000 state=2 en=1` | identical timestamp and value |
| R2 repeated LATCH accepted | `B_REPEAT_LATCH t=2566000 version=2 err=000000` | identical |
| R3 LATCH adopts a mode | `C_UNSAFE_MODE t=3776000 disp_mode=1 version=2 pam=5` | identical |
| R4 export overwrites on failure | three fixture CSVs changed, digests `f984b638…`, `57efa533…`, `8c483eaf…` | byte-for-byte identical to `evidence/export_failure_result.json` |
| R5 duplicate time marker accepted | reader counted `rezeroed=1`, checker verdict `PASS` | identical |

`PROTOCOL_COUNTEREXAMPLES=3/3` from D's RTL. The probe's own `$fatal` when the count is not 3 is
expected: it is a diagnostic of the old version, and after the fix the correct-behaviour assertions
below replace it.

## 1. R1 — an abort now withdraws the display authorisation

**Root cause.** `abort_now` moved the state machine to `S_ABORT` and cleared `run_q`, but left
`have_disp_q` set, and `start_ok` accepted a start from `S_ABORT`. So releasing blank and pulsing
`pwm_start` alone re-lit the old configuration at the old interval count, which the original task book
section 3.4 forbids ("must complete a new valid load / LATCH / start sequence in the safe phase").

**Change.** A separate `auth_q` authorisation register, set only by an accepted LATCH and cleared by
reset, by safe-phase mode adoption, and by an abort. `start_ok` now requires `auth_q`. `pam_sel` is
untouched by an abort, because contract section 2 requires the held amplitude code to survive until
the next legal LATCH.

**Regression.** Scenario 2019 (abort, then a bare start) and 2020 (abort, then a new load, no LATCH,
then a start) must stay dark and record `START_REJECTED`; 2023 (abort, then a complete load / LATCH /
start) must conduct exactly the new code's intervals. All three are in the control matrix.

## 2. R2 — a load is now a consumable transaction

**Root cause.** `cfg_valid` was read as a level, so any number of LATCHes behind a still-high
`cfg_valid` were accepted and each stepped `cfg_version`. Nothing was consumed.

**Change.** `load_pending_q` is set by the rising edge of `cfg_valid` (one load transaction) and
cleared by the accepted LATCH that consumes it. A LATCH with no pending token is refused with a new
distinct bit `STALE_CONFIG` and cannot step the version. Re-presenting the same grey code is legal
only as a new load transaction, which is what the task book allows.

**Regression.** Scenario 2021 does one load and two LATCH requests: the version must step exactly
once, `proto_err` must show `STALE_CONFIG`, and the second request must not change the display.
Version stepping is now asserted from the case's own first LATCH, so a value carried in from the
previous case cannot fake or hide a step.

## 3. R3 — a LATCH can no longer adopt a mode

**Root cause.** `latch_ok` never compared the requested mode with the accepted one and wrote
`disp_mode_q <= mode` directly, so the safe-phase rule (`system_en=0`, blank, no window) had a
bypass; worse, the accepted LATCH cleared the whole error record, erasing the evidence of the refusal
it had just performed.

**Change.** `disp_mode_q` is written only by the safe-phase adoption path. `latch_ok` additionally
requires `mode == disp_mode_q`; a LATCH asking for another mode is refused with the new
`MODE_NOT_ADOPTED` bit, and adoption clears the authorisation and the pending load so the new mode
needs its own sequence. The bitmap now clears only LATCH-family bits: a `START_REJECTED` or
`MODE_WHILE_RUNNING` sampled on the same edge as an accepted LATCH survives.

**Regression.** Scenario 2022 (mode changed under `system_en=1`, then LATCHed) must show both refusal
bits, keep the Pure symbol code on `pam_sel`, step the version once, and still run the window the
first LATCH committed. Scenario 2031 proves the legal side: switch in the safe phase, re-load, and
the second window really displays the new mode's code.

## 4. R4 — the exporter now verifies before it publishes

**Root cause.** `do_export()` wrote the main, control and negative CSVs and only then opened the VCDs
for the edge samples, so a missing or unreadable trace left partially rewritten official evidence
behind. The old "write guard" hashed only its own record file, and never exercised a failure that
happens after some files were already written.

**Change.**
* `build_artefacts()` produces the complete artefact set in memory and writes nothing: identity of the
  cached run against the sources on disk, per-trace digest verification, a full re-judgement of every
  trace with the current checker, row-by-row equality against the cached rows, matrix completeness by
  `(mode, frame, tick, code, pam)` key, scenario coverage, and the export gates.
* `publish()` stages every file as `<name>.new` and only then swaps each one into place, so a crash
  cannot leave a half-written set with no recovery path.
* `write_guard_matrix()` is the real regression: it copies the run directory, pre-seeds **all nine**
  evidence targets with non-empty content, then runs nine failure modes against that fixture
  (`empty_row_set`, `missing_run_dir`, `gates_not_met`, `missing_trace`, `compile_failure`,
  `corrupt_trace`, `stale_cached_source`, `row_count_mismatch`, `trace_digest_mismatch`) and compares
  the digest **and the file set** afterwards. `write_guard.txt` in the evidence carries the per-mode
  table and the per-file digests. The official evidence path is never the target.
* A cached run whose recorded checker/reader/RTL/TB digests differ from the files on disk is refused,
  so old results cannot be re-stamped onto new sources.
* Two holes of the same family were found by the new gate itself, after the first export of this round
  had already "passed", and are fixed here rather than glossed: the manifest used to hash whatever
  happened to be in `results/evidence/` at build time, i.e. the bytes **before** the swap, so the
  published manifest described the previous round (`EVIDENCE_DIGEST` failed on six files). It now
  hashes the exact bytes `publish()` is about to write, labels each entry with its origin, and
  explicitly lists the one file it cannot hash (itself) plus the transcript that the handoff step
  regenerates afterwards. And `--selftest` only writes its report into the run directory when `--out`
  is given, so the first R1 export silently kept the previous round's `dd1_d7a_checker_selftest.txt`;
  the chain now runs `--selftest --out <run>` and the published selftest is this checker's own output.

## 5. R5 — declared stimulus is now proven to have happened

**Root cause.** The scenario generator wrote `pure/ht/pam` into both instances' columns and kept
`pure_b/ht_b/pam_b` only in the description dictionary, so case 2018 ("PAM 0 and 7") actually ran PAM
0 twice and 2031's second window ran the old mode's code. Handlers trusted the scenario name, and the
reader never refused duplicate time markers although the contract said it would.

**Change.**
* `add()` writes per-instance columns into the vector, and every scenario now declares its windows as
  `(mode, time code, pam)` plus mode transitions, assertion phase, pulse width and stall phase.
* `attest_windows()` reads those values back out of the trace **before** judging the design; a
  mismatch is `STIMULUS_MISMATCH` and an absent one is `STIMULUS_UNATTESTED`. Case 2018 must see PAM
  0 then 7, and 2026 the reverse, with the code held through each PWM-off tail.
* Window completion is measured from each instance's own `win_state` edge, not inferred from the shared
  stimulus, and the mixed-code rows compare each channel's own start and completion.
* The reader now refuses a duplicated `#` block (still accepting many signal changes inside one
  block, and still catching a zero-width glitch at a single time), which the selftest proves.
* Abort coverage extended: mid-window blank and fault with long pulses, a 20 ns minimum pulse at the
  middle of the shortest conducting interval, just before and just after the window endpoint, plus a
  Hybrid off-edge case at the 120 ns tick; the clock stall now exists both after `DONE` (2009) and
  during a running window (2010), and the handler reports which phase it actually found.
* `attest_phase()` then checked those scenarios against the trace instead of their names, and three of
  them were not what they said: 2011/2013 asserted blank/fault on the first accepted tick (their
  `q1` was 0 and the intended delay had been put in the unused `q3` column), 2015's "middle of the
  shortest pulse" landed 455 ns into the off tail, and 2017's "after the window endpoint" fired while
  the window was still running. The scenarios now carry the tick count and the off-edge phase that the
  attestation demands (61 ticks mid-conduction, 15 ns inside the one-interval pulse, the last interval
  before the completion edge, and after it), and the checker refuses a shut-off that never put
  `win_state` into `ABORT`, or one that aborts a window that had already completed.
* The same attestation found a real testbench ordering bug: profiles 21 and 22 released `blank` and
  only then pulsed `PWM_START`, so the start was refused because the safe phase had already been left,
  not because the authorisation was withdrawn — the scenario proved nothing and the
  `abort_reauthorises_display` mutant came back `NOT_DETECTED`. Both profiles now issue the start
  while `blank` is still asserted (the only way a start can ever be accepted) and release blank
  afterwards; with that ordering the same mutant is caught and the golden design stays dark.
* The reset and unknown-bus scenarios were the last two rows with an empty declared-stimulus column,
  so 2002 now declares its three reset falls (power-on plus two pulses) and 2036 declares the X it
  applies; `ctl_dark_only` counts the reset falls from the trace and the evidence re-checker requires
  every one of the 42 control rows to carry a declaration.
* Two new protocol scenarios close the earlier gap between "withdrew blank" and "restarted without a
  new commit" (2019, 2020), and refusals while armed or on a shared edge are covered (2006, 2007).
* Mutation classes grew from six to nine: `stale_latch_accepted`, `abort_reauthorises_display` and
  `latch_adopts_mode`, each built by patching the current RTL text, recompiled and re-simulated, and
  refused by the same unchanged checker.

  **Superseded by the round after this one, and kept here as measured:** the second review showed
  that `stale_latch_accepted` and `latch_adopts_mode` removed only the *recording* of a refusal — the
  freshness gate and the mode gate were still in place, so neither model produced the functional
  failure its name claims. Both are real mutations of the diagnostic path and nothing more, and the
  `9/9` line above means "nine models were compiled, run and refused", not "nine functional failures
  were reproduced". The functional versions, each with a fault that must be observed in the mutant's
  own trace before its refusal counts, are in `reports/dd1_d7a_review_fix_r2.md` section 3. Two anchors had drifted out of the rewritten RTL (`pure_iv`
  spacing and the `data_en` assign) and the blank-gate mutant was re-targeted from 2008, which never
  conducts, to 2011, which does; all nine now compile, run and are refused (`MUTATION_DETECTED=9/9`).

## 6. Final measured state (run_id `r1_20261021`)

Every gate below was re-run from the current bytes of this revision; the chain is
`--selftest --out`, `--run-rtl`, `--mutants`, `--synth`, `--write-guard-demo`, `--export`,
then `dd1_d7a_evidence_check.py`, each step's exit code recorded in `review/dd1_d7a/r1_20261021/`
(ignored directory, full VCDs stay local).

| gate | result | rc |
|---|---|---|
| checker self-certification | 20 named-tag defects plus 4 parse refusals (duplicate `#`, Z in window, ragged rows, empty table) all refused | 0 |
| main matrix | 1536/1536 cases PASS, 3072 per-instance observations, 512 Pure + 1024 Hybrid unique `(mode, frame, tick, code, pam)` keys | 0 |
| control matrix | 36 scenarios, 35 PASS plus the one required refusal (case 2036, unknown code bus → `UNKNOWN_VALUE`) | 0 |
| mixed-code dual instance | 6/6 PASS, each channel's own start and completion measured | 0 |
| stimulus attestation | 42/42 control and mixed rows carry a declaration and 0 rows contradict it | 0 |
| RTL mutations | 9/9 DETECTED after recompiling and re-simulating each patched source | 0 |
| write guard | 9 failure modes, every one refused with the whole pre-seeded fixture unchanged by digest and by file set | 0 |
| yosys structure | rc=0, two `check -assert` passes with 0 problems, 146 cells, 21 asynchronous-reset registers (6 `$adff` + 15 `$adffe`), no latch, no memory, statistics parsed | 0 |
| evidence re-check | 40 checks, `EVIDENCE_IDENTITY: PASS (0 checks failed)`, 7/7 published evidence digests and 6/6 source digests | 0 |
| safety rules, provenance, device count | `SAFETY_RULES_TEST`, `SOURCE_PROVENANCE_CHECK` (401 files, 528 labelled lines, 0 violations), `DEVICE_COUNT_CHECK` all PASS | 0 |
| objects scan | still reports the pre-existing unreachable blob `955497fb18ac` (3,583,407 bytes) and stays FAIL for that one item, unchanged from the previous round, in this round's own worktree | as recorded |

Sources the published manifest hashes: RTL `fff22f96c15beefd…`, testbench `3e5074f712911679…`,
checker `86b1659cb155e2b5…`, reader `708c37027fb11d25…`, runner `1be5cfb3a25dddfb…`,
contract `b1053911c877629e…`. The published evidence tables hash to cases `2d89ea91f78a99e5…`,
control `f6785596885366b8…`, negative `70046203ed151e57…`, edge samples `a6951c9f717fa5b4…`,
environment `f5d4bd0ae742533c…`, selftest `192f300542c155ff…`, write guard `704fae7160e7a8ef…`.
The freeze transcript (`results/evidence/dd1_d7a_freeze_security.txt`) hashes to
`6beea277a7f5fae02169daf3027679ddc7f504fb11fe97ea745c721dc8647e9c`.

## 7. Honest scope and carried-forward items

* The toolchain is per-invocation PATH only, and tool lookup now accepts either `<name>.exe` or a
  POSIX name on `PATH`; nothing global was changed. The reviewer's Linux binaries are not the ones
  used here, and the recorded digests are of this machine's executables only.
* Yosys statistics are taken from the actual log; if a future version's table format cannot be parsed
  the summary says so instead of reporting an empty dictionary as success.
* `precommit_safety_check.py --mode objects` still reports the pre-existing unreachable blob
  `955497fb18ac` (3,583,407 bytes, pack date 2026-10-14, no content rule hit). It is not from this
  round, and it is not GCed, rewritten, printed or worked around.
* Nothing here touches MOS, the eight PAM current levels, the LUT, current integration, CDC or
  physical skew, layout, or the frozen Data-6 evidence: `NEW_SPECTRE_RUNS=0`, `NEW_OA_WRITES=0`.
* `D..D1` commit structure is described in the handoff, including the earlier lesson that a
  "metadata-only" delivery commit must not carry functional fixes: this round's functional changes all
  land in the payload commit.

## 8. Commit ranges for this repair round

```text
B  (DATA-6 baseline)          = 731767519d1a51287eb5b7f4a6e4f9b8e613e990
P  (reviewed round payload)   = ef6737d40912b91197df4c0954eee6edcff55ee0
D  (reviewed delivery, base)  = 6a1f5a192f3f1618499335c4365d717bfcadef39
P1 (this round's payload)     = b0196f995962e8098e218aabf86e5864792b7f8c
D1 (this round's handoff)     = 202f11c63d7163487af3e5f33843e4a742c9115a
branch                        = poc/data-gray-d7a-r1, ordinary push, no force, no --no-verify

B..D1   26 tracked files  = the 24 files DATA-7A already changed over B (22 new DATA-7A files plus
                            the two safety-rule files that round was allowed to touch) and the two
                            files added by this round: reports/dd1_d7a_review_fix.md and
                            reports/tasks/DATA-7A-R1.md. No shared safety tool, Spectre circuit,
                            Data-6 evidence, scan circuit, PDK, OA, CDF, symbol, cds.lib or
                            human-tidy schematic is in the range.
D..D1   22 tracked files  = rtl 1, testbench 1, scripts 5, reports 5, evidence 9, task-book copy 1.
                            `git diff --name-only D..D1` contains nothing outside the DATA-7A scope.
P1..D1   2 tracked files  = reports/agent_handoffs/DATA-7A.json and .md, metadata only.
```

`D1` is the handoff commit and carries no functional change. The remote tip after the two pushes was
read back twice (direct `git ls-remote` and `gh api`) and both gave `202f11c63d7163487af3e5f33843e4a742c9115a`;
the full history scan runs in the `pre-push` hook on every push and passed.
