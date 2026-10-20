# DATA-7A-R2: what the second independent review found, and what this revision changed

Review input: `MicroLED_DATA7A_R1_Review_and_R2_Task_20261021.zip`, sha256
`fa0080b488d25191a3f0413f6d0e2b70a4248f2e6192ffbf103e5c910673ab48`, whose `REVIEW_DATA7A_R1.md`
reviews the R1 tip and whose task book is stored byte-for-byte as
`reports/tasks/DATA-7A-R2.md` (sha256 `3a73977d60355b23a0c12ea11f88d1c9b2f7dff7f19fb62f3a52de108184fdac`).
The previous review is kept at `original/REVIEW_DATA7A.md` in that package and the R1 task book at
`reports/tasks/DATA-7A-R1.md`; both stay unchanged in the repository.

Fixed sources: reviewed R1 tip `T1 = 0b64d1d62b851ac46e03a4d0250c8014984f2ef5`, R1 payload
`P1 = b0196f995962e8098e218aabf86e5864792b7f8c`, R1 handoff `D1 = 202f11c63d7163487af3e5f33843e4a742c9115a`,
previous delivery `D = 6a1f5a192f3f1618499335c4365d717bfcadef39`, DATA-6 baseline
`B = 731767519d1a51287eb5b7f4a6e4f9b8e613e990`. This round works in `D:\ic617_d7a_r2` on the new
branch `poc/data-gray-d7a-r2`, created from `T1`; `T1`, its branch and the older branches were not
moved, merged or rewritten.

## 0. Reproducing the review before changing anything

All five findings were reproduced on this machine (Windows, Icarus 14.0 devel s20260301-626 and
Yosys 0.70+176 — different binaries from the reviewer's Linux Icarus 12 / Yosys 0.33) against the
**unmodified bytes of `T1`**, using the reviewer's own diagnostic sources from the package. For every
probe, exit code 0 means the defect was reproduced, never that the design passed.

| finding | local measurement on T1 |
|---|---|
| F1 pending config survives the abort | `probe_abort_pending` on T1's RTL: after the abort `pending=1`; the post-abort LATCH takes `version 1→2`, `auth=1`, and the first tick gives `data_en=1`, for the blank and the fault path (`REVIEW_DIAGNOSTIC_REPRODUCED=2/2`) |
| F2 publish loses files mid-set | `probe_publish_failure.py`: file 1 replaced with new bytes, file 2 **deleted and not restored**, manifest still old, two `.new` left behind |
| F2 guard modes contaminate each other | T1 guard code over a full T1 run copy: `corrupt_trace` refused with the *missing-trace* message, `row_count_mismatch` and `trace_digest_mismatch` with the *stale-source* message; the fixture really seeds 8 targets while the report claimed nine |
| F2 synthesis status ordering | `probe_synth_gate.py`: a `synth_summary.json` with `stat_parse=UNPARSED_FORMAT…` but `rc=0, problems=[]` passes the export gate and reaches the re-judge; `do_synth` appends the parse failure **after** writing the file |
| F3 two "functional" mutants were bit-masks | T1 mutant chain: `stale_latch_accepted` shows exactly one `cfg_version` edge and `proto_err=…0010`; `latch_adopts_mode` shows one edge and `proto_err=…1000` with `disp_mode_q` never moving |
| F4 mixed checker misses a late channel | `probe_mixed_start.py`: contract t0 1435 ns, A opens 1435 ns, B opens **1445 ns**, same 7680 ns width, and the delivered mixed checker still says 6/6 PASS |
| F5 re-checker accepts a duplicate combination | `probe_evidence_duplicate.py`: 1536 unique ids but 1535 unique combinations after copying row 1 onto row 2 and refreshing that file's manifest digest — the delivered re-checker returned `PASS (0 checks failed)` |

## 1. F1 — an abort now also revokes the prepared load, and the next copy is proven in a second window

**Root cause.** The abort branch cleared `auth_q` but left `load_pending_q` set. A load presented
before the abort and never consumed therefore stayed valid, so a LATCH after the abort — still
showing the same `cfg_valid`, with no new load edge anywhere — committed that pre-abort configuration,
stepped the version and re-authorised the display. The first review's rule "the recovery must not use
an old pending marker as its new configuration" was therefore only half implemented: the bare-START
path was closed, the pending-load path was not.

**Change.** In `rtl/dd1_d7a_gray_ctrl.sv` the abort branch is now the highest-priority sampled event:
it sets `S_ABORT`, clears `run_q`, withdraws `auth_q` **and** clears `load_pending_q`, and the load,
mode-adoption, LATCH and start branches moved into the `else` arm of the same edge, so nothing sampled
with the abort can re-authorise. `pam_q` is untouched, as contract section 2 still requires the held
amplitude code to survive until the next legal LATCH. `reports/dd1_d7a_contract.md` section 5 now
states the revocation and the same-edge priority explicitly.

**Regression.** Seven new control scenarios (43 in total, up from 36, none removed):

* `2040` blank abort, `2041` fault abort — each with a load prepared *before* the abort and
  `cfg_valid` still high: the post-abort LATCH must record `STALE_CONFIG`, the start must record
  `START_REJECTED`, the version must not step again and both channels must stay dark from the abort
  onwards (`ctl_abort_pending`).
* `2042` abort, then an incomplete LATCH request, then a genuinely new load / LATCH / start;
  `2043` fault abort then a new Hybrid load. Both must stay dark up to the first post-abort load edge
  and then conduct exactly the new code (`ctl_abort_pending_recover`, `aborted_windows=[0]`).
* `2037`–`2039` prove the next/display copies with two real windows instead of "current value
  unchanged": a load is raised inside window A, A still conducts its own code and holds its own PAM,
  the first LATCH after A's completion commits the prepared copy, window B conducts *that* code and
  PAM (Pure 120→200 at 30 ns, Pure 100→100 as a new load at 50 ns, Hybrid (20, pam 2)→(45, pam 6) at
  120 ns), and a replayed LATCH behind the consumed load is refused. `ctl_next_window` reads the load
  edge, both windows, both versions and the refusal out of the trace.
* The `abort_reauthorises_display` model was re-targeted after the R1 discovery that a start presented
  after blank release is refused for the phase, not the authorisation; `2019`/`2020` issue the start
  while blank is still asserted.

`measure_nth_window` gained a `lat_idx`/`commit_latches` argument because a refused LATCH is still a
rising edge on that bus: without it, window 1 of the recovery scenarios read the code carried at the
*refused* request and the judgement described a window the controller never committed.

## 2. F2 — publish is now a set transaction, every guard mode gets a clean run, and the synthesis status is ordered

**Root cause.** `publish()` staged `.new` files and then did `remove(final)` + `rename(tmp, final)`
per file: a failure between the two left a *deleted* target, and a failure later in the loop left new
and old files mixed with no recovery. The guard matrix copied the run directory **once** and let later
modes inherit the damage of earlier ones, so three of its nine rows refused for somebody else's
reason. `do_synth` appended the statistics-parse failure to `problems` *after* writing
`synth_summary.json`, so the persisted record said `rc=0, problems=[]` and the export gate accepted it.

**Change.**
* `publish()` backs up the bytes that are in place, writes a `d7a_publish.pending` marker, promotes
  with `os.replace` (atomic per file), verifies each published digest against what it staged, and on
  any **catchable** failure restores every promoted file from the backup, removes the staging and
  marker files and reports the failure. `pending_publish()` and `recover_publish()` make an
  outstanding transaction visible and restorable, and `--export` refuses to treat the directory as
  delivered while an incomplete one is marked. The guarantee boundary is written where it can be
  read: per-file replacement is atomic, the set is consistent under caught failures, **a SIGKILL or
  power loss between two promotions is not covered** and is instead detected by the marker.
* `write_guard_matrix()` now derives the target list from a real clean build instead of typing a
  number, gives every mode its own fresh copy of the run (small files copied, traces hard-linked,
  files a mode damages copied so the shared baseline is safe), injects exactly one fault, and
  requires the refusal it claims: `expected_refusal` text, plus the changed / added / **missing** file
  lists and any leftover staging or marker file. `dry_run_plan_only`, `sample_extract_failure`,
  three synthesis-state modes and `publish_first/middle/last_file_fails` plus `publish_success` were
  added; `corrupt_trace` now refreshes the recorded trace digest first, otherwise it could only ever
  re-test the digest gate, which is exactly the false coverage the review named.
* `synth_status()` forms the entry's verdict — parse status included — *before* anything is written;
  `synth_gate_ok()` is the single predicate the export gate and the selftest share, so
  `UNPARSED_FORMAT` cannot be washed out by an empty `problems` list. The raw Yosys return code and
  the cell numbers stay recorded separately as `yosys_rc`, so a front-end pass on a table this parser
  does not read is still reported as a pass of the tool and a failure of this entry.
* `entry_selftest()` proves those two things without a simulator: an unparsable statistics table must
  set `entry_rc=1` while `yosys_rc=0`, the gate must refuse the stale
  `rc=0 / problems=[] / stat_parse=UNPARSED` shape, and a publish whose second promotion throws must
  leave every old byte in place with no leftovers, while a clean publish must land the new bytes and
  clear its marker.

## 3. F3 — functional failure models now have to be seen breaking something

**Root cause.** `stale_latch_accepted` only deleted the `err_stale_q` set and `latch_adopts_mode` only
deleted `err_mode_unset_q`; both left the freshness and mode gates intact, so the mutants proved the
diagnostic path while being reported as functional models.

**Change.** The table is split by `category`, and each model declares a `fault` that is evaluated on
the mutant's **own** VCD before the refusal counts. A model whose fault is not observed is reported
`FAULT_NOT_EXERCISED` and fails the gate — that is treated as a bug in the model, not a pass; two of
them were caught exactly that way while this round was being written (a one-tick delay turned out to
move the channel's own t0 rather than its output edge, and the wording was corrected to what the
trace shows). New functional models: `stale_latch_really_accepted` (the freshness requirement removed
from `latch_ok`, with `cfg_valid` held high in `profile 20` so an incompleteness refusal cannot
pre-empt it — the version is then seen to step twice), `latch_really_adopts_mode` (the mode comparison
removed and the LATCH branch writing `disp_mode_q`, with the adopted Hybrid PAM `110` seen on
`pam_sel`), and `abort_keeps_pending_config` (the aborted-pending revocation removed, i.e. the
reviewed T1 behaviour, with a version step *and* light after the abort and no new load edge). The two
bit-mask models are kept as `mode_unset_error_bit_masked` and `stale_latch_error_bit_masked`,
category `diagnostic`, and the R1 report's claim about them is corrected here rather than rewritten
in the frozen R1 file.

**Measured:** see section 6 — 16 models, each with its fault observed and its refusal produced by the
same unchanged checker.

## 4. F4 — each mixed-code channel is measured on its own output edges

**Root cause.** `ctl_mixed_codes` compared `a['t0']` with `b['t0']`, but both came from the *shared*
tick and clock edges in `measure_nth_window`, so the comparison was between two derivations of the
same input; a channel whose `data_en` is late by less than a tick passed, together with its width
(counted in whole ticks) and its completion edge.

**Change.** `_own_t0()` derives each channel's t0 from **that channel's own** `obs_tick` audit output
and the reference edge that consumes it. `ctl_mixed_codes` now checks, per channel: own t0 against
the shared stream's edge (`MIXED_EDGES`), the first `data_en` rise against own t0 in exact
picoseconds (`ON_START`), the last fall against `own t0 + exp x T` (`ON_WIDTH`), the summed
conduction span against the same product (`ON_SPAN`, so a fractional-tick shift cannot hide inside
integer tick rounding), and `DONE` against `own t0 + full x T`. Code 0 is treated as "no conduction
at all" (`BLACK_CONDUCTS` if it lights) with its completion still checked, and the whole thing is
stated as logic-edge verification, not physical skew.

**Models:** `mixed_b_output_late_one_cycle` (10 ns, the reviewer's probe),
`mixed_b_output_late_three_cycles` (30 ns), `mixed_b_one_interval_short` (one interval short), plus
the main-matrix `instance_b_late_one_reference_cycle` and `instance_b_tick_late_two_cycles`. The six
legal mixed scenarios are unchanged.

## 5. F5 — the re-checker now verifies the contract, not just the hashes

**Root cause.** It checked row count, unique *case ids*, finiteness and digests, but never the
combination set, and it read `exp_intervals` from the very row it was auditing. Hash-consistent but
semantically wrong evidence therefore passed.

**Change.** `dd1_d7a_evidence_check.py` now carries the contract as data (`CONTRACT_GROUPS`,
`contract_intervals()`, `expected_combinations()` — restated from `reports/dd1_d7a_contract.md`, not
derived from the RTL or from the CSV) and adds: `COMBINATION_UNIQUE` / `COMBINATION_LEGAL` /
`COMBINATION_COMPLETE` over the exact 1536-element
`(mode, frame_hz, tick_ns, time_code, pam_code)` set; `CONTRACT_RECOMPUTED`, which recomputes
`exp_intervals`, `full_intervals`, both instances' segment count, width, measured intervals, endpoint
`t0 + full x T`, the accepted-tick boundary count `full + 1`, and the PAM legality, from
mode + code + tick; `SCENARIOS_REQUIRED` / `SCENARIO_PRESENT` over the delivered kinds;
`REFUSAL_REASON`, which demands that a declared expected refusal fails **for that reason** rather than
accepting any FAIL, `NOT_RUN` or missing stimulus; `MUTATION_CATEGORY_HONEST`,
`MUTATION_FAULT_OBSERVED` and `MUTATION_REFUSED_AFTER_FAULT`; and `RUN_ID_CHAIN`, `TRACE_DIGESTS`,
`REJUDGE_CHAIN` for the identity path.

`--selftest` runs it over isolated copies of the delivered evidence with the manifest digest of the
touched file recomputed, so each case is hash-consistent by construction: clean copy passes,
duplicate combination, contradicting `exp_intervals` (with the widths made to agree), missing
required scenario kind, an expected refusal flipped to PASS, a functional model whose fault was never
observed, and a foreign `run_id` must each be refused by the named check.

## 6. Final measured state (run_id `r2_20261021`)

All of it comes from one byte-set: `--selftest --out`, `--run-rtl`, `--mutants`, `--synth`,
`--write-guard-demo`, `--export`, then `dd1_d7a_evidence_check.py` and its `--selftest`, with every
exit code in `review/dd1_d7a/r2_20261021/` (ignored directory; full VCDs stay local, digests in the
manifest). Two intermediate batches were discarded on the way and are described in section 8.

| gate | result | rc |
|---|---|---|
| checker self-certification | 20 named-tag defects + 4 parse refusals refused, by the same checker | 0 |
| entry self-certification (new) | 11 assertions: unparsable statistics fails the entry while `yosys_rc=0` is kept, the gate refuses the stale `rc=0 / problems=[] / UNPARSED` shape, publish rollback restores every byte and leaves no staging or marker, clean publish lands the new bytes | 0 |
| main matrix | 1536/1536 PASS (Pure 512, Hybrid 1024), 3072 per-instance observations, all intervals/endpoints/accepted-tick counts recomputed from mode+code+tick | 0 |
| control matrix | 43 scenarios (36 kept, 7 added): 42 PASS + 1 required refusal (unknown code bus, `UNKNOWN_VALUE`) | 0 |
| mixed-code dual instance | 6/6 PASS, each channel's own t0, on/off edges, span and DONE measured from its own trace | 0 |
| stimulus attestation | 49/49 control and mixed rows carry a declaration and none contradicts it | 0 |
| failure models | 16/16 DETECTED: 14 functional (each with its wrong behaviour observed in its own trace first) + 2 diagnostic; `not_exercised = []` | 0 |
| write and publish guard | 18 modes, each from a fresh copy of an exportable run with one injected fault, all refusing for the reason they claim; 9 target files derived from a real build, not typed | 0 |
| yosys structure | rc=0, two `check -assert` passes with 0 problems, 151 cells, 21 async-reset registers (6 `$adff` + 15 `$adffe`), no latch or memory, statistics parsed | 0 |
| evidence re-check | 53 checks, `EVIDENCE_IDENTITY: PASS (0 checks failed)` | 0 |
| evidence semantic self-test (new) | 7 cases: clean copy passes, and duplicate combination, contradicting `exp_intervals`, missing scenario kind, flipped expected refusal, functional model without an observed fault and a foreign run id are each refused by the named check, with the manifest digest recomputed so hashes stay consistent | 0 |
| safety rules, provenance, device count | all PASS; shared rules unchanged, no new exception this round | 0 |
| staged and history scans | PASS (the pre-push history scan runs on every push) | 0 |
| objects scan | still FAIL on the pre-existing unreachable blob `955497fb18ac` (3,583,407 bytes): reported as found, no GC, no content printed, no rule relaxed | as recorded |

The published tables hash to: cases `53e4c829d2cf…`, control `08b04d55c57d…`, negative `7f39a3041138…`,
edge samples `a6951c9f717f…`, environment `987b3d649d10…`, write guard `3b2cd5e5c19d…`, self-test
`71a525e0429b…`. Sources recorded by the manifest: RTL `6dbf464a49e4…`, testbench `426f93275faa…`,
checker `4b5197948ec2…`, reader `708c37027fb1…`, runner `19a13810e02f…`, contract `37f55cb9f078…`.
The freeze transcript `results/evidence/dd1_d7a_freeze_security.txt` (126 lines) hashes to
`36c8c5e58bc7d46a14bd584ae8ab97afc7eb2406f8052b04c114d9b216b873ba`.

The cell count moved from 146 to 151 with the abort branch now clearing the pending token as its own
statement; the register count is unchanged at 21. This is a front-end structural count only, with no
library, no timing and no area meaning.

## 7. Commit ranges for this round

```text
B   (DATA-6 baseline)        = 731767519d1a51287eb5b7f4a6e4f9b8e613e990
D   (first reviewed delivery) = 6a1f5a192f3f1618499335c4365d717bfcadef39
P1  (R1 payload)              = b0196f995962e8098e218aabf86e5864792b7f8c
D1  (R1 handoff)              = 202f11c63d7163487af3e5f33843e4a742c9115a
T1  (reviewed R1 tip, this base) = 0b64d1d62b851ac46e03a4d0250c8014984f2ef5
P2  (this round's payload)    = e151ebca59bc60df5e6e4d16fd6907e9787ded0a   (20 files)
D2  (this round's handoff)    = the commit that adds reports/agent_handoffs/DATA-7A.json and this
                                section; it carries no source, script, RTL, testbench or evidence-table
                                change, and its own SHA is not written into any tracked file because a
                                commit cannot contain its own SHA. Read it as the branch tip:
                                git rev-parse origin/poc/data-gray-d7a-r2
branch / push                 = poc/data-gray-d7a-r2, ordinary push (proxy transport, dry-run first,
                                attempt 1), no force, no --no-verify, no merge, no visibility change

T1..P2  20 tracked files = rtl 1, testbench 1, scripts 4 (runner, checker, evidence re-checker,
                           bundle packer), reports 5 (contract, implementation note, R1 report's
                           supersession note, this report, the R2 task-book copy), handoff MD 1,
                           evidence 8 (the seventh published table plus the freeze transcript, which
                           the manifest deliberately does not self-hash).
T1..D2  21 tracked files = the 20 of P2 plus reports/agent_handoffs/DATA-7A.json; this section
                          lives in the already-counted handoff MD. Measured with
                          `git diff --name-only 0b64d1d6..HEAD | wc -l` after the handoff commit.
B..D2   28 tracked files = everything DATA-7A has ever touched across the three rounds: the 26 of
                           the first two rounds plus this report and the R2 task-book copy. Nothing
                           outside the DATA-7A prefix appears in any of the three ranges, and the
                           frozen originals (both earlier task books, the copied handoff validator,
                           the two shared safety-rule files, all Spectre / Scan / Data-6 evidence)
                           are byte-identical to T1 and B respectively.
```

`P2` is the payload in the strict sense used since the first review: every functional change, the
regression suite, the new evidence and this report are inside it. `D2` adds only the machine handoff
and the commit table, and one measured number in section 6 and the handoff table (the evidence
re-checker's check count, 53, which had been written as 55 by counting log lines instead of checks) —
a correction of report text, not of code, recorded here rather than smuggled into an earlier commit.

## 8. Honest scope and carried-forward items

* The toolchain is this machine's, discovered per invocation (`D7A_TOOL_ROOT` or the default root)
  with the suite `lib` on that call's `PATH` only; the reviewer's Linux Icarus 12 / Yosys 0.33 are
  different binaries, and the recorded digests belong to these executables alone. No global
  configuration, license or system path was changed, and no VM, Spectre, Cadence or OA access happened.
* `precommit_safety_check.py --mode objects` still reports the pre-existing unreachable blob
  `955497fb18ac` (3,583,407 bytes, pack date 2026-10-14) that no rule reaches, and that gate still
  says FAIL. It was not from this round, it is not GCed, its content is not printed, and no rule was
  relaxed or worked around. `--mode history` and the staged scan pass.
* The publish rollback covers failures this process can catch. It is not a hardware transaction: a
  SIGKILL or power loss between two promotions leaves a mix of old and new files, which is why the
  pending marker exists, why it is reported, and why the claim is written that way here and in the
  guard report rather than as "atomic".
* Two process flaws of this round's own are recorded rather than hidden. First, a baseline batch was
  started in the new worktree and finished **after** the RTL had been edited, so its
  `run_summary.json` claimed a source digest that had not produced its traces; that batch was
  discarded, is not cited anywhere, and `do_run` now records the digests of the sources it actually
  compiled and refuses if any of them changes while the simulations are in flight. Second, the first
  two guard/export batches failed loudly and left the official evidence untouched — one because the
  new negative-table columns made the CSV writer refuse a ragged table, one because the guard's
  compile mode let a `SystemExit` escape the mode loop, and one because the guard's
  publish-success mode was scored with the "nothing changed" rule that belongs to the refusal modes.
  Those are recorded here as the reasons, with the exit codes, not smoothed into a first-try pass.
* `sample_extract_failure` is a direct call into the function the export uses, on a run copy with no
  control trace and no samplable main row. It is not a full end-to-end export refusal, and the mode
  row says so: the sampling stage sits behind a complete re-judge of ~100 MB of VCD, so a whole-export
  version of that case would cost more than it proves.
* Nothing here touches MOS, the eight PAM current levels, the LUT, current integration, physical CDC or
  skew, layout, or the frozen Data-6 / Scan evidence: `NEW_SPECTRE_RUNS=0`, `NEW_OA_WRITES=0`.
* What the R1 round already corrected stays corrected: the R1 report keeps its own text, and where a
  claim in it has been superseded (the two mutants that were bit-mask only, the "nine" write-guard
  target count) this report says so instead of editing that frozen file.
