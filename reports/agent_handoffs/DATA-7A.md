# DATA-7A — dual-mode grey-scale timing controller: RTL logic verification (checkpoint / handoff)

Task book: `reports/tasks/DATA-7A.md` (copy of the delivered package). Update rule: rewritten at every
test milestone with the real commands, rc, counts, failures and what is still unknown.

## Where this round stands

| milestone | state |
|---|---|
| A baseline, branch, toolchain | done (see below) |
| B contract + checker self-certification | contract written; checker in progress |
| C RTL + dual-instance TB | not started |
| D matrices | not started |
| E mutations + write guard | not started |
| F synthesis structure | not started |
| G evidence, safety exception, commits, push | not started |

`NEW_SPECTRE_RUNS=0`, `NEW_OA_WRITES=0` for the whole round: no Cadence, no VM, no guest write. The
previous round's 19/20 Spectre process budget is an old record and is not consumed or extended here.

## A — identity actually read (not assumed)

* Repo `https://github.com/LINboss666/microled-ic-ai-lab`; base = `731767519d1a51287eb5b7f4a6e4f9b8e613e990`
  on `poc/data-unit-1ch`, read back twice: local `origin/poc/data-unit-1ch` ref and
  `gh api repos/.../git/refs/heads/poc/data-unit-1ch` (both = that SHA, 2026-10-20).
* A direct `git fetch origin` at the same moment failed with `RPC failed; curl 28 Recv failure:
  Connection was reset` — the known instability of this host's direct `github.com:443` (see
  `reports/git_network_diagnosis.md`), not a baseline problem. Later pushes therefore go through
  `scripts/git_push_reliable.ps1`, which measures transports at run time.
* `poc/data-gray-d7a` existed neither locally nor on the remote → no conflict, nothing to reconcile;
  created as a new branch at the base SHA in an **isolated worktree**
  (`D:/ic617_d7a`, `git worktree list` confirms it), so `D:/ic617_agent_bridge` stays checked out on
  the previous branch with its own history untouched. Teammate branches (`gexing321/*`), `main`,
  `poc/data-unit-1ch` and `poc/scan-driver-1ch` are read-only this round.
* Frozen digests re-verified against `SOURCE_AUDIT.json`: `spectre/dd1_d6_sink_core.scs` =
  `6cfe2338…7ee91db`, `spectre/dd1_d6_bias_core.scs` = `4115e2d1…e9b31e7`,
  plus the five other baseline files named by the package. No tracked file is modified except the two
  safety-tool edits §§2.3 allows.

## A — machine and toolchain, measured rather than assumed

* Windows 10.0.26100 x64 (Git Bash / MSYS), `python 3.12.5`, `git 2.49.0.windows.1`.
* Before this round: **no RTL tool at all** on PATH — `iverilog`, `vvp`, `verilator`, `yosys`,
  `gtkwave` all MISSING; no WSL distro installed (`wsl.exe -l -v` says none); only a Dev-Cpp MinGW gcc
  elsewhere on the disk, which is not a Verilog front end.
* Therefore, per §2.4, an isolated copy of the official **oss-cad-suite** Windows x64 nightly
  (release tag `2026-10-20`, asset `oss-cad-suite-windows-x64-20261020.tgz`) was downloaded through the
  machine's existing user proxy to `D:/ic617_d7a_tools/` — **outside the repository**, so no tool binary
  can be committed by accident. No installer was run, no system PATH, registry or licence touched, no
  global package manager. Provenance (URL, size, sha256, versions actually executed) is recorded in
  `results/evidence/dd1_d7a_environment.json` once extracted; a two-state-only simulator would not be
  accepted, and Icarus Verilog is four-state.

## Commands used so far (reproducible)

```bash
git rev-parse origin/poc/data-unit-1ch
gh api repos/LINboss666/microled-ic-ai-lab/git/refs/heads/poc/data-unit-1ch --jq '.object.sha'
git worktree add -b poc/data-gray-d7a /d/ic617_d7a 731767519d1a51287eb5b7f4a6e4f9b8e613e990
sha256sum spectre/dd1_d6_sink_core.scs spectre/dd1_d6_bias_core.scs      # matches SOURCE_AUDIT.json
```

## Open items / risks being carried honestly

* `poc/data-gray-d7a` must be pushed with the safety rules knowing `.sv` is not in
  `EXTENSIONS_ALLOWED`; §§2.3 permits exactly adding `.sv` plus a positive test, and nothing else.
  `.vcd` stays unwhitelisted, so all committed trace evidence will be CSV/JSON, never a raw VCD.
* The checker is being written before the RTL so it cannot be tuned to the RTL's own internals; the
  selftest must refuse a deliberately wrong trace before the 1536-case matrix is trusted.
* Icarus Verilog implements a subset of SystemVerilog, so the RTL is written in a conservative
  synthesisable subset (`logic`, `always_ff/always_comb`, `localparam` integers; no interfaces,
  classes or assertions). Any deviation must be caught by the yosys structure pass, not hidden.


## Milestone B and C status (2026-10-20, later same round)

Toolchain: `oss-cad-suite-windows-x64-20261020.tgz` finished at 603,893,871 bytes, sha256
`b141f2523e265d8ca742f96760cb3c9260422194e28f6851741cf2ffce9bc943`, which equals the digest the
GitHub release asset reports. Extracted outside the repository; actually executed versions:
Icarus Verilog 14.0 (devel, s20260301-626-g7e3d0c6bd) for `iverilog` and `vvp`, Yosys 0.70+176
(git sha1 365bb887b). `yosys.exe` and `vvp.exe` need the suite `lib` directory on the process PATH
(a per-invocation setting only); without it they fail on `libreadline8.dll`, rc=127.

Phase B closed: `reports/dd1_d7a_contract.md` plus `scripts/dd1_d7a_trace.py` (four-state reader)
and `scripts/dd1_d7a_check.py` (independent checker). `--selftest` reports
`CHECKER_SELFTEST: PASS`: the hand-typed interval table, 7 legal synthetic waveforms, 19
deliberately wrong waveforms each refused with the named failure tag, plus parse-level refusals for
a non-1 ns/1 ps time base, a missing judged signal and a backwards timestamp, an empty case set, the
pre-event-sampling guard and the write guard.

Phase C in progress: `rtl/dd1_d7a_gray_ctrl.sv` plus `tests/dd1_d7a/tb_dd1_d7a_gray.sv`. Four real
cases (Pure 1@30 ns, Pure 255@50 ns, Hybrid 63/pam5@120 ns, Hybrid 63/pam7@200 ns) compiled with
`iverilog -g2012 -Wall` rc=0 and ran in `vvp`; the checker judged all four PASS with measured
widths 30 / 12800 / 7680 / 12800 ns, one segment each, `obs_tick` counts 257 / 257 / 65 / 65, PAM
held, `data_en_b` complementary, both instances identical.

Three real defects were found and fixed while doing this, all recorded rather than hidden:

* the reader assumed one VCD id per signal; Icarus aliases a module port with the driving net, so
  24 ids covered 214 declarations. The reader now records every name sharing an id, and refuses an
  id shared by different widths.
* the reader assumed a one-line `$timescale`; Icarus writes multi-line keyword blocks, a 1 ps base
  and unpadded vector values. Both are handled, and the checker now proves the time base by
  measuring the reference period (must be 10 ns) instead of trusting the header.
* the first abort condition aborted the *armed* state, which by contract is entered while blank is
  still asserted, so no window ever started; blank now aborts only a running window and fault
  aborts armed or running. The testbench also raced its input drives against the clock edge until
  every drive was moved to 2 ns after an edge.

`t0` is defined in the trace as the reference edge that consumes the first tick presented after the
blank release, so every judged output edge is a clock edge; the tick is generated in the same domain
by the testbench and is never used as a clock.


## Milestone D status (same round, later)

`scripts/dd1_d7a_run.py` is the single entry point (`--selftest`, `--dry-run`, `--run-rtl`,
`--mutants`, `--synth`, `--export`, `--write-guard-demo`). `--dry-run` passes: 1536 planned main
cases (Pure 256 @30 ns + Pure 256 @50 ns + Hybrid 512 @120 ns + Hybrid 512 @200 ns), 24 control
scenarios, 6 mixed-code cases, both frozen master digests MATCH, `NEW_SPECTRE_RUNS=0`,
`NEW_OA_WRITES=0`.

Synthesis structure pass (`--synth`, yosys on the RTL only, testbench not read, no cell library):
rc=0, `check -assert` twice with 0 problems, 134 cells, storage = 6 `$adff` + 12 `$adffe` async-reset
flip-flops, and `select -assert-none` passes for `$dlatch`, `$sr`, `$dffe`, `$memory`, `$anyseq`,
`$anyconst`. No latch, no memory array, no unresolved hierarchy, no multiple drivers.

Mutation gate (`--mutants`, six real source mutations recompiled and re-simulated, judged by the same
unchanged checker): 5/6 DETECTED on the first pass. `blank_gate_removed` → ASYNC_OFF,
`counter_rollover_reopens` → SEGMENT_COUNT, `instance_b_one_tick_late` → ON_START,
`pure255_only255` → ON_WIDTH, `start_level_rearm` → SEGMENT_COUNT. The sixth,
`auto_resume_after_abort`, was **NOT_DETECTED and the cause was my own stimulus, not the RTL**:
testbench profile 2/3 stopped the tick stream at the abort, so a design that resumes after the
withdrawal had nothing to resume with. The profile now keeps the tick stream running through the
blank/fault assertion and its withdrawal, which is also the more realistic frame condition.

Control/matrix bookkeeping corrections found while running the real traces (all checker-side, none
weakening a judgement):

* the code-stability range for control cases now stops at the blanking of that same window, so the
  next window's load and the next case's reset are not misread as instabilities;
* `display_frozen` deliberately reads the code at the LATCH instant instead of demanding a stable
  load bus — a mid-window next-code load is the stimulus being tested — and the check is that the
  measured width still equals the latched code and `pam_sel` does not move;
* the clock-stall scenario no longer uses absolute nanosecond parameters (they landed in the wrong
  case): the stall is found in the trace as a gap in the reference clock, then tick silence and state
  holding are asserted across that gap;
* `control` rows now carry `expect`, so the intentional X/Z probe (case 2024) is recorded as a
  required refusal: the checker refuses to convert an unknown code bus into a number and reports
  `UNKNOWN_VALUE`, which is the wanted outcome, not a pass.

With those corrections the control suite is 23 PASS plus the 1 required refusal, and mixed-code is
6/6 PASS, on a dedicated re-run; the final numbers below come from the full re-run of everything.


## Gates (verified against the delivered run directory `review/dd1_d7a/FINAL`)

| gate | result | what the reviewer can recompute |
|---|---|---|
| BASELINE_IDENTITY | PASS | base read twice (`git ls-remote` + `gh api`), both master digests MATCH in `--dry-run`, no teammate commit merged in |
| CHECKER_SELFTEST | PASS | hand-typed table, 7 legal waveforms, 19 wrong waveforms each refused by name, plus parse refusals, sample guard and write guard |
| SYNTHESIS_STRUCTURE | PASS | yosys rc=0, `check -assert` twice with 0 problems, 134 cells, no latch/memory/multiple driver, testbench not read |
| PURE_MATRIX | PASS | 512 cases (256 codes x {30, 50} ns) |
| HYBRID_TIMING_MATRIX | PASS | 1024 cases (64 time codes x 8 PAM codes x {120, 200} ns) |
| CONTROL_AND_ABORT | PASS | 24 scenarios: 23 judged PASS, the X/Z probe judged as the required refusal |
| MIXED_CODES (apart) | PASS | 6 cases, different codes per channel, common t0 and window end |
| INSTANCE_OBSERVATIONS | PASS | 1536 cases x 2 instances = 3072 measurements, compared field by field |
| MUTATION_DETECTION | PASS 6/6 | real mutated RTL recompiled and re-simulated, refused by the unchanged checker |
| WRITE_GUARD | PASS | refusals leave a pre-seeded non-empty evidence file byte-identical |
| EVIDENCE_IDENTITY | PASS | row counts, case ids, digests recomputed from the committed bytes |
| FREEZE_AND_SECURITY | PASS (with one carried-forward object, see below) | `git diff` touches only the two files section 2.3 allows |
| REMOTE_READBACK | see the receipt block | |

Mutation classes actually built and refused: `pure255_only255` (ON_WIDTH), `counter_rollover_reopens`
(SEGMENT_COUNT after the window), `blank_gate_removed` (ASYNC_OFF at the assertion time),
`start_level_rearm` (262 conducting segments instead of one window), `instance_b_one_tick_late`
(ON_START plus INSTANCES_DIFFER), `auto_resume_after_abort` (AUTO_RESUME after the withdrawal).

## Freeze, safety and the one carried-forward object

* `git diff` against the baseline: only `scripts/repo_safety_rules.py` (one added `.sv` entry) and
  `scripts/test_safety_rules.py` (its positive case plus refusal cases). Every pre-existing tracked
  byte, including all `spectre/` netlists and all earlier evidence, is unchanged; both master digests
  are re-verified by `--dry-run`.
* `SAFETY_RULES_TEST: PASS` (secret 7/7, vendor 4/4, path 10/10, accept-extension 2/2,
  refuse-extension 6/6, and `.v .vcd .exe .raw .lib .db` verified still outside the whitelist).
* `precommit_safety_check.py --mode history`: 141 commits, 1337 objects, four counters 0, PASS.
* `precommit_safety_check.py --mode objects`: 1690 objects, **one** blocked object, and it is not
  from this round — `<blob:955497fb18ac>`, 3,583,407 bytes, no content rule hit, blocked only as a
  large unreachable blob, with a pack-file date of 2026-10-14, six days before this round started.
  It is left exactly as found: no GC, no history rewrite, no content printed. Its digest is recorded
  here so a later round can tell whether it is still the same object.
* `.vcd` is not whitelisted, so the six full traces (16 MB to 38 MB) stay in the ignored `review/`
  tree; the manifest carries their digests, and every number in the committed CSVs is a measurement
  out of those traces.

## Interface risks the next (MOS) round has to decide, not this one

1. `dd1_data_top_1ch` exposes only `d/clk/blank`. Feeding this controller's request into `d` would
   still be sampled by the frozen C^2MOS DFF, so it is not direct control. Either a new grey-scale
   top reuses the frozen analogue core with an explicitly timed interface, or the latch interface
   changes; both are MOS decisions and neither was made here.
2. `pam_sel` in Pure mode is the symbol value 7. It is a code, not 15 uA: the eight current levels,
   their trimming and the reference relationship are still `NOT DEFINED`.
3. The tick is a same-domain clock-enable supplied by the test reference domain here. The divider,
   the TCON 976/977 column schedule and the 50 MHz-to-PWM domain crossing are `NOT_IMPLEMENTED`;
   nothing in this round supports a skew or maximum-frequency claim.
4. Asynchronous shut-off is proven as logic priority only (zero-delay simulation). MOS propagation,
   metastability, safe reset release and real device glitches are unmeasured, and the two-cycle
   minimum pulse width for `blank`/`fault` is a POC assumption, not a chip input specification.

## Delivered run numbers (`review/dd1_d7a/FINAL`, one compile, six traces)

| trace | cases | trace bytes | trace sha256 (first 12) |
|---|---:|---:|---|
| `trace_pure_t30.vcd` | 256 | 16,286,320 | `cdbe40512cab` |
| `trace_pure_t50.vcd` | 256 | 21,929,630 | `211f32705d52` |
| `trace_hyb_t120.vcd` | 512 | 25,134,665 | `76257b00177a` |
| `trace_hyb_t200.vcd` | 512 | 38,145,761 | `43570dc2e3e4` |
| `trace_control.vcd` | 24 | 1,386,597 | `d2f564e5c67b` |
| `trace_mixed.vcd` | 6 | 360,358 | `ca09c55eb220` |

Main matrix: 1536 rows, 1536 PASS, 1536 unique case ids, 3072 instance observations, all rows agree
between the two channels, every measured on-width equals `intervals x measured tick` exactly, and
`EVIDENCE_IDENTITY: PASS (0 checks failed)` from `python scripts/dd1_d7a_evidence_check.py`.

Representative rows, quoted straight out of `results/evidence/dd1_d7a_cases.csv`:

| case | mode | code | pam | tick ns | intervals | measured width ns | segments | accepted ticks |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | PURE | 0 | 7 | 30 | 0 | 0 | 0 | 257 |
| 256 | PURE | 255 | 7 | 30 | 256 | 7680 | 1 | 257 |
| 512 | PURE | 255 | 7 | 50 | 256 | 12800 | 1 | 257 |
| 513 | HYBRID | 0 | 0 | 120 | 0 | 0 | 0 | 65 |
| 1024 | HYBRID | 63 | 7 | 120 | 64 | 7680 | 1 | 65 |
| 1536 | HYBRID | 63 | 7 | 200 | 64 | 12800 | 1 | 65 |

The accepted-tick column is the contract's boundary-event count: 257 for a 256-interval Pure window
and 65 for a 64-interval Hybrid window, i.e. the start event plus one per interval boundary, measured
on the `obs_tick` audit node rather than asserted.

Control suite: 24 scenarios, 23 PASS, and the one X/Z probe (case 2024, LATCH presented with an
unknown code bus) is refused by the checker with `UNKNOWN_VALUE` exactly as required; it is recorded
as `expect=refusal`, not as a pass. Mixed-code: 6/6 PASS with different codes per channel on a shared
start and window end.

Edge samples: 3,224 rows over 248 (case, anchor, signal) sets, each with points both before and after
its anchor, covering black, shortest, last step, full window and an asynchronous blank shut-off; no
sampled value is x/z.

## 9. Commit structure and remote read-back

Two commits are used so no tracked file has to contain its own commit SHA.

```text
BASE_SHA          = 731767519d1a51287eb5b7f4a6e4f9b8e613e990   (poc/data-unit-1ch, read back twice)
BRANCH            = poc/data-gray-d7a                          (new, own branch, ordinary push)
PAYLOAD_SHA (P)   = ef6737d40912b91197df4c0954eee6edcff55ee0
P contents        = RTL, testbench, reader, checker, runner, bundle/evidence checkers, contract,
                    implementation note, task-book copy, 9 evidence files, the two safety-rule
                    files section 2.3 allows to change
P remote read-back  git ls-remote (direct) : ef6737d40912b91197df4c0954eee6edcff55ee0
                    gh api (api.github.com) : ef6737d40912b91197df4c0954eee6edcff55ee0
                    LOCAL_REMOTE_PARITY    = PASS, push transport = proxy, attempts = 1,
                    no force, no --no-verify, main and the teammate branches untouched
DELIVERY_SHA (D)  = aa1f981a7522f78b372f2dd0d0bc69eaeb7ac334, the commit that added this JSON and
                    this section, and the commit the independent review read.
ACTUAL TIP AT REVIEW TIME = 6a1f5a192f3f1618499335c4365d717bfcadef39. The review was right to point
                    this out: P..D was the two metadata files, but the branch then received a third
                    commit, a one-line functional fix to scripts/dd1_d7a_bundle.py whose bytes-literal
                    bug produced the filename `dd1_d7a_bundle_b'aa1f981'.zip`. So the range the
                    reviewer actually had to read was P..6a1f5a1 = three files, not two, and calling
                    D the delivery commit while a functional fix followed it was sloppy. The
                    correction is stated here rather than rewritten into history.
```

`reports/agent_handoffs/DATA-7A.json` follows schema 1.0 and was run through the copied validator
byte-for-byte (`scripts/dd1_d7a_validate_handoff.py`, sha256 `3c150d54…`, semantics unmodified):

```text
HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified)
```

Its `head_sha` points at P with `head_sha_semantics = payload_commit`, and its `push_status` is
scoped in the same file: the read-back it records is P's, taken before those bytes were written.

## 10. Reserved statuses (unchanged by any result above)

```text
PWM_MOS_IMPLEMENTATION=NOT_RUN
PAM_8LEVEL_ANALOG_IMPLEMENTATION=NOT_RUN
HYBRID_CURRENT_INTEGRATION=NOT_RUN
GRAY_LUT_IMPLEMENTATION=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
PHYSICAL_CDC_AND_SKEW=NOT_VERIFIED
NEW_SPECTRE_RUNS=0
NEW_OA_WRITES=0
LAYOUT_DRC_LVS_PEX=NOT_RUN
SOA_SIGNOFF=NO
COMPLETION_LEVEL=RTL_LOGIC_VERIFIED
```

The old Data-6 reservations (first-in-band settle wording, non-recomputable 210-row excerpts, the
92-vs-96 terminal-object correction) keep their original records; this round did not re-run or rewrite
them. DATA-7A stops here and waits for independent review of the delivery commit.


---

# DATA-7A-R1 — repair round after the independent review

Sources for this section: the review package quoted in `reports/dd1_d7a_review_fix.md` (zip sha256
`312c19dc…`, task book copy `326226…`), the reviewed commit `6a1f5a192f3f1618499335c4365d717bfcadef39`,
and this worktree. No chat history was available or assumed.

Everything above this heading describes the reviewed round as it was delivered, and is kept
byte-for-byte as that round's record. The numbers it quotes are no longer the current suite: this
revision runs 36 control scenarios plus 6 mixed-code rows, 9 mutation classes, 146 cells with 21
async-reset registers, and the evidence set re-exported under run_id `r1_20261021`.

## Remote read-back before touching anything

```text
poc/data-gray-d7a tip  git ls-remote via proxy : 6a1f5a192f3f1618499335c4365d717bfcadef39
                       gh api                  : 6a1f5a192f3f1618499335c4365d717bfcadef39
                       git ls-remote direct    : fatal: Recv failure: Connection was reset
```

Direct git transport failed as it has before on this host; the proxy path and the API agree, so the
reviewed tip is confirmed by two independent reads and no unreviewed commit was found on it. New
branch `poc/data-gray-d7a-r1` created from that commit in `D:/ic617_d7a_r1`; the reviewed worktree
`D:/ic617_d7a` was left untouched.

## Reproduced against the reviewed bytes, before changing anything

The reviewer's three-protocol probe, compiled with D's unmodified RTL (`04e5aadf…`) on Windows /
Icarus 14.0, printed the same counterexamples at the same timestamps as the Linux run
(`A_START_ONLY … en=1` at 1366 ns, `B_REPEAT_LATCH … version=2` at 2566 ns, `C_UNSAFE_MODE …
disp_mode=1 pam=5` at 3776 ns, `PROTOCOL_COUNTEREXAMPLES=3/3`). The export probe changed three
pre-seeded fixture CSVs to digests identical to the reviewer's record (`f984b638…`, `57efa533…`,
`8c483eaf…`), and the duplicate-`#` probe still came back `verdict: PASS`. All five findings are real
and local, not a transcription of the review.

## What changed

R1 a separate `auth_q` authorisation is cleared by an abort, so a bare start cannot re-light;
R2 `load_pending_q` makes one load consumable by exactly one LATCH and a replayed LATCH is refused as
`STALE_CONFIG` without stepping the version; R3 `disp_mode_q` is written only by safe-phase adoption,
a LATCH asking for another mode is refused as `MODE_NOT_ADOPTED`, and an accepted LATCH no longer
erases a concurrent start or mode refusal; R4 the exporter builds and validates the whole artefact
set in memory (identity of cached run against current sources, trace digests, full re-judgement,
row-for-row equality, matrix completeness by content key, scenario coverage, gates) before staging
`<name>.new` files and swapping them, and the new write-guard matrix exercises nine failure modes
against a pre-seeded fixture of every real evidence file and compares the whole set by digest;
R5 vector columns now carry the per-instance codes, every scenario declares the stimulus it must show
and the checker verifies that declaration from the trace before judging the design, window
completion is measured from each instance's own state edge, duplicate time markers are refused, an
explicit Z negative joins the X negative, and abort coverage gained the shortest-pulse middle, both
sides of the window endpoint, a 20 ns minimum pulse at an off-edge phase, a stall during a running
window, four incomplete recovery sequences and three new mutation classes.

## Gate status, final (run_id `r1_20261021`, whole chain re-run from the current bytes)

| check | result |
|---|---|
| checker self-certification | PASS, 20 named-tag defects plus 4 parse refusals including duplicate timestamp and Z in window |
| main matrix on the revised RTL | 1536/1536 PASS, 3072 instance observations, 1536 unique `(mode, frame, tick, code, pam)` keys |
| control matrix on the revised RTL | 36 scenarios, 35 PASS, plus the one required refusal (unknown code bus) |
| stimulus attestation | 42/42 control and mixed rows declare their stimulus and none contradicts it; the shut-off phase, pulse width, tick count and ABORT transition are read back from the trace |
| mixed-code rows | 6/6 PASS, each channel measured on its own start and completion |
| RTL mutations | 9/9 DETECTED, each mutant recompiled and re-simulated, judged by the unchanged checker |
| write guard | 9 failure modes, each refused with the pre-seeded fixture unchanged by digest and by file set |
| yosys structure on the revised RTL | rc=0, 2 check passes with 0 problems, 146 cells, 21 async-reset FFs, no latch/memory, statistics parsed |
| evidence re-check | `EVIDENCE_IDENTITY: PASS (0 checks failed)` over 40 checks, 7/7 evidence digests, 6/6 source digests |
| `SOURCE_PROVENANCE_CHECK` | PASS (401 files, 528 labelled lines, 0 violations) |
| `DEVICE_COUNT_CHECK` | PASS |
| `SAFETY_RULES_TEST` | PASS (unchanged shared rules, no new exception this round) |
| history scan | PASS, 1359 objects, 0 tracked PDK/credential/key/vendor files |
| objects scan | the pre-existing unreachable blob `955497fb18ac` (3,583,407 bytes) is still reported and that gate still says FAIL: no GC, no content printed, no rule relaxed |

The chain that produced these numbers, and every exit code, is written out in
`reports/dd1_d7a_review_fix.md` section 6 and echoed by the command transcript in
`results/evidence/dd1_d7a_freeze_security.txt`.

## R1 commit structure and remote read-back

Two commits again, so no file has to contain its own SHA, and this time the metadata commit really is
metadata: every functional change is inside the payload commit.

```text
BRANCH            = poc/data-gray-d7a-r1                          (new, own branch, ordinary push)
BASE (reviewed D) = 6a1f5a192f3f1618499335c4365d717bfcadef39      (not moved, not merged, not rewritten)
PAYLOAD_SHA (P1)  = b0196f995962e8098e218aabf86e5864792b7f8c
P1 contents       = 21 files: rtl, testbench, runner, checker, reader, evidence checker, bundle
                    packer, contract, implementation note, this handoff MD, the R1 report, the R1
                    task-book copy, and the nine published evidence files. No shared safety tool, no
                    old Spectre/Data-6/Scan/PDK/OA file.
P1 remote read-back  git ls-remote (direct)  : b0196f995962e8098e218aabf86e5864792b7f8c
                     gh api (api.github.com) : b0196f995962e8098e218aabf86e5864792b7f8c
                     LOCAL_REMOTE_PARITY     = PASS
                     push transport = proxy, attempts = 1, dry-run first, no force, no --no-verify,
                     main and the teammate branches untouched, no visibility change, no merge
pre-push hook        scripts/precommit_safety_check.py --mode history : SAFETY_GATE: PASS
DELIVERY_SHA (D1)  = the commit that adds this JSON and this paragraph and changes nothing else.
                     It is deliberately not written into any tracked file: a commit cannot carry its
                     own SHA. Read it as the branch tip (`git rev-parse origin/poc/data-gray-d7a-r1`)
                     or from the remote ref; it is also quoted in the chat receipt and in the review
                     bundle manifest, which are outside the repository.
D1 AS PUSHED       = 202f11c63d7163487af3e5f33843e4a742c9115a (this JSON plus this section; the
                     read-back pair above was taken at this commit)
FOLLOW-UP COMMIT   = 07ae78c0b03f7bbf58e6f2534587404db8e0e40c, one file, reports/dd1_d7a_review_fix.md
                     section 8, the B..D1 and D..D1 range table. The ranges could only be written once
                     the SHAs existed, so this is a second metadata commit; no functional file was
                     touched after P1, which is the point the previous round got wrong and this
                     paragraph is here to keep honest.
```

`reports/agent_handoffs/DATA-7A.json` (12,431 bytes, sha256
`d65c0d2227d87f9f95bdf5d8ab537be690429282c715c9bba04eda03c7a90cef`) was produced from the published
evidence tables rather than typed, and run through the unchanged byte-for-byte validator:

```text
$ python scripts/dd1_d7a_validate_handoff.py reports/agent_handoffs/DATA-7A.json
HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified)   rc=0
```

Its `head_sha` names P1 with `head_sha_semantics = payload_commit`; `objects_scan` is written as FAIL
with the pre-existing blob named, and `scope_status = COMPLETE` is scoped in the same file to the
digital-logic repair only. A schema PASS is a statement about fields, not about the silicon.


---

# DATA-7A-R2 — limited repair round after the second independent review

Task package: `MicroLED_DATA7A_R1_Review_and_R2_Task_20261021.zip`, sha256
`fa0080b488d25191a3f0413f6d0e2b70a4248f2e6192ffbf103e5c910673ab48`; the review record inside it is
`REVIEW_DATA7A_R1.md`, the task book is kept byte-for-byte as `reports/tasks/DATA-7A-R2.md`
(sha256 `3a73977d60355b23a0c12ea11f88d1c9b2f7dff7f19fb62f3a52de108184fdac`). As before, no chat
history was available or assumed.

## Remote read-back and branch

```text
poc/data-gray-d7a-r1 tip  git ls-remote (proxy) : 0b64d1d62b851ac46e03a4d0250c8014984f2ef5
                          gh api                : 0b64d1d62b851ac46e03a4d0250c8014984f2ef5
                          -> matches the reviewed T1 exactly; no unreviewed commit was merged
new worktree              D:\ic617_d7a_r2, branch poc/data-gray-d7a-r2, created from T1
                          the R1 worktree and branch were not moved, reset, merged or rewritten
```

## Reproduced against the reviewed bytes before changing anything

| finding | local reproduction on this machine |
|---|---|
| F1 pending load survives an abort | `probe_abort_pending` on T1's own RTL: after the abort `pending=1`, the post-abort LATCH takes `version 1→2` with `auth=1`, the first tick lights (`REVIEW_DIAGNOSTIC_REPRODUCED=2/2`, blank and fault paths) |
| F2 publish is not a set transaction | `probe_publish_failure.py`: first file replaced, second deleted, manifest untouched, two `.new` left (`contract_violation_reproduced: true`) |
| F2 guard modes contaminate each other | T1 guard code over a full T1 run: `corrupt_trace` refused with *the missing-trace message*, `row_count_mismatch` and `trace_digest_mismatch` with *the stale-source message*; also the fixture really seeds 8 targets while the report said nine |
| F2 synthesis status ordering | `do_synth` writes `synth_summary.json` before appending the parse failure to `problems`, so the persisted record says `rc=0, problems=[]` while the entry returns 1; `probe_synth_gate.py` shows the export gate passing that record and reaching the re-judge |
| F3 two "functional" mutants were bit-mask only | T1 mutant chain: `stale_latch_accepted` shows one `cfg_version` edge and `proto_err=…0010` (incomplete), `latch_adopts_mode` shows one edge and `proto_err=…1000` (mode-while-running) — neither committed anything wrong |
| F4 mixed checker misses a late channel | `probe_mixed_start.py`: contract t0 1435 ns, A opens 1435, B opens 1445, same width, and the delivered mixed checker still reports 6/6 PASS |
| F5 re-checker accepts a duplicate combination | `probe_evidence_duplicate.py`: 1536 unique ids, 1535 unique combinations, main CSV digest refreshed, checker still `PASS (0 checks failed)` |

Every one of the five findings is real here as well, not only in the reviewer's environment.

## What R2 changed, per finding

```text
F1  the abort branch is now the highest-priority sampled event: it records S_ABORT, clears run_q,
    withdraws auth_q AND clears load_pending_q, and the load / mode-adoption / LATCH / start branches
    moved into the else arm of the same edge, so nothing sampled with the abort can re-authorise.
    pam_q is still untouched, as the hold rule requires. Contract section 5 states the revocation and
    the same-edge priority. Seven new scenarios: 2040/2041 (blank and fault abort over a pending load
    must stay dark and record STALE_CONFIG + START_REJECTED), 2042/2043 (invalid request then real
    recovery, and fault-abort recovery), 2037-2039 (a next load prepared inside window A, committed
    only after A's own completion, used by window B with its own code and PAM, consumed exactly once).
    measure_nth_window gained commit_latches because a refused LATCH is still a rising edge.
F2  publish() now backs up, writes a d7a_publish.pending marker, promotes with os.replace, verifies
    each published digest, and on any catchable failure restores the whole previous set and removes
    the staging and marker files; pending_publish()/recover_publish() expose an outstanding
    transaction and --export refuses to call such a directory delivered. The guarantee is stated as
    per-file atomicity plus caught-failure rollback, explicitly not SIGKILL/power-loss atomicity.
    write_guard_matrix gives every mode its own fresh copy of an exportable run (one injected fault
    each), derives the target list from a real build, requires the refusal text it claims, and now
    covers 18 modes including dry-run, sample-extraction, three synthesis-status modes and
    publish-first/middle/last failures plus a publish-success path. synth_status() decides the entry
    verdict before synth_summary.json is written, and synth_gate_ok() is the one predicate shared by
    the persisted record, the export gate and the new entry selftest.
F3  the mutation table is split into functional and diagnostic categories and every model declares a
    fault that must be observed in the mutant's own VCD before its refusal counts; FAULT_NOT_EXERCISED
    fails the gate. The two bit-mask models are kept and renamed as diagnostic, and the R1 report
    carries a supersession note instead of being rewritten.
F4  _own_t0() derives each channel's t0 from that channel's own obs_tick audit, and ctl_mixed_codes
    now checks own-t0 vs the shared edge, the exact on-edge, the exact off-edge, the summed conduction
    span in picoseconds and the completion edge per channel, with code 0 treated as no conduction.
    Three mixed-path models (10 ns late, 30 ns late, one interval short) and two main-matrix channel
    delay models are refused. Logic edges only: no physical skew claim.
F5  the evidence re-checker rebuilds the exact 1536-element contract combination set, recomputes
    intervals, full window, endpoints, accepted-tick counts and PAM legality from mode+code+tick,
    demands every required scenario kind, demands that a declared expected refusal fails for that
    reason, checks the run-id chain and trace digests, separates functional from diagnostic models,
    and gained --selftest over isolated hash-consistent-but-wrong fixtures (7 cases).
```

## R2 gate status, final (run_id `r2_20261021`)

| check | result |
|---|---|
| checker self-certification | PASS, 20 defects + 4 parse refusals refused |
| entry self-certification | PASS, 11 assertions about statistics status and publish rollback |
| main matrix | 1536/1536 PASS, 3072 instance observations, contract-recomputed intervals and endpoints |
| control matrix | 43 scenarios: 42 PASS + the one required refusal (unknown code bus) |
| mixed-code rows | 6/6 PASS with per-channel own-edge measurement |
| stimulus attestation | 49/49 rows declare their stimulus, none contradicted |
| failure models | 16/16 refused: 14 functional with the fault observed first, 2 diagnostic; none unexercised |
| write and publish guard | 18 modes from independent clean copies, 9 derived target files, all pass |
| yosys structure | rc=0, 0 problems twice, 151 cells, 21 async-reset registers, statistics parsed |
| evidence re-check | `EVIDENCE_IDENTITY: PASS (0 checks failed)` over 55 checks |
| evidence semantic self-test | `EVIDENCE_SELFTEST: PASS (7 cases)` |
| safety rules / provenance / device count | PASS, shared tools byte-identical to T1 |
| staged + history scans | PASS (history scan also runs in the pre-push hook) |
| objects scan | FAIL on the pre-existing unreachable blob `955497fb18ac`, unchanged and not worked around |

Full root causes, the T1 negatives, and every command with its exit code are in
`reports/dd1_d7a_review_fix_r2.md`; the command transcript is
`results/evidence/dd1_d7a_freeze_security.txt` (sha256
`36c8c5e58bc7d46a14bd584ae8ab97afc7eb2406f8052b04c114d9b216b873ba`).
