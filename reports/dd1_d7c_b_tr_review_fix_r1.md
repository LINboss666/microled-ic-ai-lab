# DATA-7C-B-TR-R1 — offline evidence and checker repair round

TASK_ID=DATA-7C-B-TR-R1 · branch `poc/data-pam-d7c-b-tr-r1` · BASE `398c9e852c16db85cbfa4539e859534e117ff0d2`
REVIEWED_CONTENT_SHA `f49ba9d78190f8c3da2adca9dbd4fb3e48d26841` · run_id `r20261027_143223_4c8a81`
worktree `D:\ic617_d7c_b_tr_r1` · evidence `results/evidence/dd1_d7c_b_tr_r1_r20261027_143223_4c8a81/`

This round repairs evidence and rules. It changes no circuit, starts no simulator, and does not
re-simulate anything in order to obtain an electrical PASS. The circuit goal is unchanged (eight
branches, one output, minimal PAM unit; TT/27 °C deck condition, IREF=15 µA, vdd18=vcas=1.8 V,
VSS=0, ideal output clamp 1.20 V, `I_sink = Ip_branch` with no negation and no absolute value).

## 0. Ceiling and what actually happened

```text
NEW_SPECTRE_LAUNCHES=0        NEW_RTL_SIMULATIONS=0     NEW_OA_ACCESS=0
NEW_SSH_OR_GUEST_CONNECTIONS=0  NEW_PDK_LICENSE_OR_CREDENTIAL_READS=0
NEXT_NATIVE_STAGE_AUTHORISED=NO MERGE_PERFORMED=NO      ACCEPTANCE_REGISTERED=NO
CANDIDATE_DUT_CHANGED=NO      OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO  SOA_SIGNOFF=NO
```

The only processes this round spawned were `python` (itself) and `git` (read-only object lookups);
the reviewer instrument records that in its own `permitted_processes` field, twice, before and after
the fixes. `OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO` is the state at the stop point, not a claim that no
transient write ever happened: the judging entry of the shared record tool rewrote three published
files of the native round mid-round, they were parked with their mutated bytes and restored to their
HEAD blobs, and §9 keeps that event in the record with its timestamp rather than as a clean claim.

## 1. Inputs, frozen surface, registered digests

The reviewer ZIP (`MicroLED_DATA7C_B_TR_Independent_Review_and_R1_Task_20261027.zip`, 44,147 B,
sha256 `5c9b267a484aa7c1c68dbf38ce242d6bd7ef377937341f35b5a2826f508440a8`) was extracted to a
**new** directory `D:\dc_tr_review_R1_20261027_222732`; the previously existing review directory was
left untouched. 19 inputs were registered byte-for-byte (`input_identity.json`), among them

- `TASK_DATA7C_B_TR_R1.md` sha256 `86eea01c…c71b`, copied to `reports/tasks/DATA-7C-B-TR-R1.md`;
- `REVIEW_DATA7C_B_TR_REWORK_20261027.md` sha256 `38512e8a…41e22`;
- `probe_tr_review_gaps.py` sha256 `1dc6e85f…a37f`, kept **unmodified** and re-run from the copy
  registered under `tests/dd1_d7c_b_tr_r1/`.

Frozen-surface check at BASE: 2935 paths, 0 drift, 0 modified, 0 deleted
(`frozen_surface_at_base`). Only the six round-owned scripts were touched
(`dd1_d7c_b_tr_{contract,decks,trace,measure,run,record}.py` → four of them changed: measure, run,
trace, record; contract and decks needed no change), plus new files under this round's own paths.

## 2. The nine reviewer counterexamples

`probe_before/probe_tr_review_gaps.json` — the instrument against unmodified BASE bytes:
`all_named_defects_reproduced=true`, 9/9 reproduced, positive controls pass, 0 launches.

`probe_after/probe_tr_review_gaps.json` — the same instrument, same judgment criteria, against the
repaired bytes (instrument rc=1 because the defects no longer reproduce):

| counterexample | before | after | closed by |
| --- | --- | --- | --- |
| stale `Account` object overwrites a charged reservation | reproduced | refused | `Account.reserve`/`settle` re-read the disk inside the lock and validate header, sequential ids, states and the recorded ceiling; `flush` writes a temp file and `os.replace`s it |
| meter current exported in volts accepted | reproduced | refused | `check_answer_format` at `load_raw` |
| `vdd18 = 0 V` accepted | reproduced | refused | `check_answer_against_deck` through `load_for_measurement` |
| time axis that goes backwards accepted | reproduced | refused | `check_answer_format` strict increase + finite |
| Hybrid enable moved 10 ns late still converted | reproduced | refused | per-frame endpoint equality `rise(data_en)==t0`, `fall(data_en)==t0+M·T` in the trace's own integer units |
| 1 µA peak in a black window still SHUTOFF PASS | reproduced | refused | `statuses()` now ANDs the 34 off-tails and the 3 black windows over max\|I\| |
| generated recompute accepts a forged DC target + dynamic PASS | reproduced | **INSTRUMENT_NOT_APPLICABLE** | the instrument re-runs `record.recompute_source()`, the superseded table-only template; the real entry is refused — see §3 |
| generated recompute accepts a 1000 ns TR-120 denominator | reproduced | **INSTRUMENT_NOT_APPLICABLE** | same, refused at the real entry |
| generated recompute accepts five RTL rows as four processes | reproduced | **INSTRUMENT_NOT_APPLICABLE** | same, refused at the real entry |

The three recompute probes are reported as not applicable rather than as closed, because the
instrument builds a minimal copy that carries no exported sequences; a refusal caused by a missing
file would be a fake hit. The closure evidence is the round's own entry
`tests/dd1_d7c_b_tr_r1/probe_r1_recompute_forgery.py`, which copies a **complete** package (both
evidence trees, the frozen contract, the decks, the exported sequences), proves the clean copy
re-derives everything, and then injects exactly one forgery at a time while refreshing every digest
the copy itself carries (`probe_forgery/r1_recompute_forgery.json`):

```text
clean package                        RECOMPUTE_R1 gate 838/838  rc=0
forged_dc_target_and_dynamic_PASS    rc=1  68 named failures
  TR-LONG W0: the DC target is the accepted DC table current x the re-derived T50, never the measured charge
  TR-LONG W0: err_dynamic_LSB re-derived from the samples and the frozen targets is the published one
wrong_reference_tick_1000ns          rc=1  3 named failures
  TR-120 W0: the table carries the case reference tick, not its own length ('1000.0', 120.0, ...)
five_process_evidence_rows_as_four   rc=1  2 named failures
  five rows that each carry process evidence are five starts, never four (rows 5, with evidence 5, distinct 5)
```

## 3. F1 — an independent evidence chain rebuilt from the stored sequences

No Spectre was re-run. The 18 answers the native round pulled and digested were read read-only and
exported **losslessly**: the printed tokens are copied verbatim, nothing is resampled, averaged,
rounded or unit-converted. The container is a base85 text file, named in the manifest as
`native_sequences/<native_run_id>_<case>_<role>.sequence.txt` (`TR1CONTAINER 1` header, gzip payload
inside) because the repository's own
frozen safety rules admit no unknown binary extension — `*.vcd`, `*.gz` and any unlisted suffix are
blocked by the pre-commit gate, which is the gate that stopped this delivery's first commit attempt.
`restore:` states how to expand it with the standard library alone, and the recomputer reads nothing
but these containers.

* 18 sequences, 2,562,403 samples in total, all strictly increasing, units read from the file itself
  (axis `s`, meter `A`, nodes `V`); the meter column is spelled as the file spells it (`Ip_branch:i`).
* Column blocks are `CONSTANT` (one token + the count it expands to), `RUNS` (maximal stretches of an
  identical token) or `EMPTY`; the file states its own sample count, units and a restore note, so a
  reviewer expands it without any tool from this round.
* All 9 DUT and all 9 preflight answers fit, with the two internal fragments that do fit: the 18
  sequences, the frozen dependency and the RS-SWITCH and RS-FULL fragments come to **32,193,607
  delivered bytes**, which the exporter holds under its own ceiling of 32,505,856 B (the task's 32
  MiB, 33,554,432 B, minus a 1 MiB reserve for the rest of the evidence). The figure a reviewer can
  reproduce — `git diff --name-status 398c9e85..HEAD` with one `git cat-file -s` per path, which is
  what was measured here at the record commit — is: this round's evidence directory
  **32,818,620 B of newly tracked numeric evidence** (the containers plus the republished tables,
  statuses, probes and JSON) and 270,103 B of its own scripts, tests and reports, so **33,088,723 B
  added to the repository, 465,709 B under the task's 32 MiB**. The receipt restates the total after
  the packaging and receipt commits.
  A container longer than 240 KiB is cut into `<name>.part000.txt`, `<name>.part001.txt` …
  because the repository's own history gate refuses any single blob over 512 KiB;
  `native_manifest.json` records the whole-file digest and the digest and byte count of every part,
  and `--verify` rejoins each set and proves the concatenation against those figures: 19 of 21
  recorded artifacts verified, 2 named as excluded, 0 problems, over 142 files. The ceiling figure is
  therefore the bytes a reviewer actually receives, not the bytes before encoding.
* The internal 26 columns are complete for the five short runs (TR-120, TR-200, TR-OFFCODE, TR-LONG,
  RS-LOW, both roles) — TR-LONG therefore carries every flat step's last 50 ns at native sampling —
  and for two of the four long runs (RS-SWITCH 8 windows in 7 parts of 1,603,951 B, RS-FULL 24
  windows in 13 parts of 3,145,267 B) as declared native fragments: the last 50 ns of each flat step
  plus 25 ns about each enable edge. The HYB-120 and HYB-200 fragment sets (1,319,679 B and 977,397
  B) do not fit the remaining 312,249 B, so they are recorded as gaps naming the bytes each would
  need and the bytes that are left, and their per-step internal detail stays in the published row
  tables, not claimed as re-integrable. Nothing is deleted or averaged away to make room.
* Identity chain per answer: old `run_id`, `launch_id`, deck path+digest, ledger raw digest, log
  digest, request/completion times, executor digest and the simulator name/version/analysis/stop/
  step/maxstep read out of the answer's own header (`native_identity.json`,
  `native_manifest.json`). Each stored answer was hashed and compared with its ledger row before
  anything was written; a mismatch is a refusal.
* The two real traces are recorded by name, byte count and digest (`0d07a25a…`, `0798d47c…`), each
  checked against the native conversion record before anything is written, and their **bytes are not
  copied into the tracked directory**: `*.vcd` is a family this repository's own safety rules never
  track, and the 416,278 B they would take as containers is the difference between delivering the
  RS-SWITCH and RS-FULL fragments and exceeding the ceiling. They re-enter the delivery as gzip
  copies inside the reviewer package, whose builder admits them only after the same digest check, and
  both were re-read by the patched converter with the delivered deck compared token by token (§5).
  The export now refuses when the trace directory holds no real trace, instead of shipping one fewer
  artifact in silence — which is what an earlier staging run of this section did.
* Frozen dependency: `dependencies/dc_matrix_dut.csv`, byte-for-byte the accepted DC-R1 table,
  admitted only after its digest equalled the committed blob and `contract.dc_reference`.
* `scripts/dd1_d7c_b_tr_r1_recompute.py` is stdlib-only, imports nothing from this round, and starts
  from the samples: endpoint linear interpolation, a split at every zero crossing, full/flat/tail
  separately, max|I|, both settling targets and the convergence ratio. Its four hand-computed area
  controls (4 nC rectangle, 1 nC ramp, ±0.5 nC crossing, 3.5 nC interpolated start) run before any
  measured window is judged. Delivered gate: **838/838 PASS, rc=0** — 37 windows re-integrated,
  both columns re-derived, 13 convergence rows linked to real Q on both sides, 10 statuses re-judged
  by content, missing/duplicate/extra/NaN refused. The same entry was replayed on a copy of the
  package **outside** the repository, with the containers cut into their 142 parts, and re-derived
  835/835 preflight and 838/838 gate at rc=0 (rehearsal root
  `D:\d7cb_tr_r1_parts_staging\gate_rehearsal_native_export_v8_20261028_015420`, a scratch copy that
  is not part of the delivery and whose logs live beside it), so the part split is not a form the
  recomputer only tolerates inside the tree it was written in.
* The published table's own numbers did not move: `window_diff_r1.csv` records 222 changed cells, all
  of them `ADDED_COLUMN` (the six per-target settling columns over 37 rows); 1369 cells are
  byte-identical to the native table. The electrical negatives are the same negatives.

## 4. F2 — stale ledgers, budget, and one name per attempt

* `Account` re-reads the file inside the lock and validates it (`_read_rows`): header, field count,
  sequential ids, admissible states, and a recorded ceiling that may never be lower than the enforced
  one. `settle` finds its row by id and settles it once. `flush` writes `.writing` and atomically
  replaces, leaving the previous account intact on failure.
* New selftest records: an object initialised before another reserved cannot overwrite that charge;
  an older object appends in id order when the disk still has room; a second settle of a settled row
  is refused; a field that would break the table is refused before anything is written.
* Every attempt now pulls into a name carrying its own row (`r1_TR-120_dut_T007.raw`), the case
  directory is `<case>_<role>_<launch_id>`, and the log tag names the row, so a retry cannot erase
  the answer the previous row was digested from. The legacy spelling still resolves, but only where
  the ledger names it.
* A DUT launch must **read** its own passed meter preflight: the account row of that case and run in
  state `CONFIRMED` with `rc=0`, a raw digest, a completion time, the pulled raw beside it whose hash
  equals that digest, the deck digest the deck account expects, and a preflight run copy that is
  exactly `DECK.preflight(dut_deck)` — same supplies, same PWL, same span, same maxstep. The old
  `done_preflight=None` default is gone; nothing about it is optional, and the record-extraction
  entries go through the same route.
* Budget, stated as three separate numbers instead of one merged claim: the approved task allows
  **24** Spectre processes; the main ledger is enforced at **22** (24 − 2 recorded stray processes);
  the 19 booked rows plus those 2 strays occupy **21**, leaving 3. `T001` stays charged as
  `UNCERTAIN`. The 19 rows are not presented as 19 independently proven starts.
* The RTL count is derived from evidence, never from `len(rows) - 1`: 5 rows, 4 of which carry an
  executable digest and a return code, 4 distinct executables → `RTL_PROCESS_COUNT=4`; a fifth row
  given its own evidence is refused (§2).

## 5. F3 — Hybrid start, end and safety behaviour, per endpoint

`check_frames` now requires, for every frame and in the trace's own integer units with no tolerance:

```text
rise(data_en) == t0            t0 = the reference edge that consumes the first accepted tick
fall(data_en) == t0 + M*T      M = {time0:0, time1:1, time2:2, time63:64}
black frame                    no rising enable anywhere in the 64 intervals
```

`obs_tick` leading by 5 ns is still asserted as a convention and can no longer be mistaken for `t0`.
The safety frame additionally checks that the enable falls **at** the real fault edge (so a segment
cannot span the fault and be waved through as "one segment"), that the fault is at `t0 + 2.5T + 3 ns`
and held ≥ 40 ns, that ticks keep running ≥ 600 ns after the withdrawal, that the recovery is a bare
START inside blank, and that no new load (`cfg_valid`) or LATCH (`latch_stb`) appears after the fault.
PAM stays per frame, the four PWL bit order, the 2 ns total edge and the uniform +1000 ns shift are
re-read by `DECK.verify_pwl`, and `deck_wave_comparison` compares the converted waves token by token
with the delivered run copy.

Both real traces were re-read offline (`reconversion_HYB-120.json`, `reconversion_HYB-200.json`,
`reconversion_summary.json`): 5 and 4 frames, `deck_problems` empty for both, digests equal to the
native conversion record. HYB-120's safety frame reads `rise 41966000 = t0`, `fall 42269000 = fault
rise`, fault fall `42309000` (40 ns), START `42318000` inside blank, 6 tick rises to `42921000`
(612 ns of observed black). No vvp was started. Positive and negative synthetic fixtures (Python
writes them; no simulator) cover the whole-wave +10 ns case, an end-only shift, a lit zero-code frame,
an output that stays lit past the fault, a missing recovery START, a load after the fault and black
that is not observed under a running clock: 50/50 records. No claim of physical CDC behaviour or clock
skew is made anywhere.

## 6. F4 — import rules and black-window shutoff

`load_raw()` checks the format first: declared units (meter in A, nodes in V — never V read as A),
strictly increasing finite times, present and equally long columns. `load_for_measurement()` adds the
deck comparison and is the single route used by `measure_case()`, `observe()` and the record
extraction entries (`stored_answer`), so no reachable entry skips it. Levels are compared with the
wave the run copy declares at that instant, with a tolerance of twice the file's own printed quantum —
never a flat 0.9 — so an enable parked at half rail is refused instead of rounded up to high. vdd18,
vcas, vss, `clamp_node` and `data_out` must be the frozen values, VSS is required in the extraction
set and measured, and the ideal probe keeps `1e-6 + 1e-9·|clamp|`.
A format refusal writes nothing (a preset non-empty output is verified unchanged); a charge or leak
overrun under a valid format is an electrical FAIL and keeps its evidence.
Black windows: 2 zero-code 64-interval frames plus the post-fault hold, all over the whole window,
Qtarget 0, no invented T50, and `SHUTOFF_STATUS` fails on a 1 µA peak even when the net charge is 0.
Measure selftest: 61/61.

## 7. The ten statuses, with the electrical negatives intact

| status | verdict | measured/expected |
| --- | --- | --- |
| EXECUTION_COMPLETENESS | PASS | 18/18 |
| EVIDENCE_INTEGRITY | PASS | 37/37 |
| DYNAMIC_CHARGE_STATUS | **FAIL** | 33/37 |
| NOMINAL_CHARGE_STATUS | **FAIL** | 23/37 |
| SETTLING_STATUS | PASS | 34/34 |
| SHUTOFF_STATUS | PASS | 37/37 |
| CONVERGENCE_STATUS | PASS | 13/13 (published as 13 rows, limit 0.01 QLSB) |
| NATIVE_SEQUENCE_REINTEGRATION | PASS | 835/835 |
| RTL_INPUT_PROVENANCE | PASS | 2/2 |
| BUDGET_ACCOUNTING_STATUS | PASS | 21/24 |

Dynamic failures (identical to the native round, re-confirmed from the samples):
TR-OFFCODE W3 −0.5835, RS-SWITCH W3 −0.5824, HYB-120 W2 −0.5639, HYB-120 W3 −0.5421 LSB.
Nominal failures: 14 windows, largest HYB-200 W2 +12.7234 and HYB-120 W2 +12.4991 LSB. These are real
electrical findings about the candidate circuit; nothing here re-judges them as evidence damage, and
no aggregate absorbs them. `CONVERGENCE_STATUS` counts 13 rows against a frozen limit, so its
`expected` field is the row count of the pairs, not a percentage.

## 8. Delay attribution wording

The attribution no longer picks a branch by subtracting the previous glowing code: every branch that
should conduct in this window is observed on its own `en`/`enb`/`vbias_ch` trace and the earliest and
latest of them are reported with their identity, never the first row for the whole set. Boundaries are
searched within ±50 ns of the event, so a value that was already past the level reads negative and is
labelled `ALREADY_ABOVE_AT_RISE`; a level reached after the window is `CROSSING_LATE`; a level never
reached keeps `NEVER_REACHES_LEVEL_IN_WINDOW`. Reaching 95 % of the DC current is a time observation
only: no device causality and no SOA sign-off is claimed, and the native fragments limit where the
bias or decode paths could be excluded at all (`delay_attribution.csv`, 34 rows).

## 9. Record corrections

* Interval accounting, verified with `git diff --name-status`: `61621f6…` → reviewed tip `398c9e8…`
  is 89 added, 0 modified, 0 deleted, and the 2935 pre-existing paths are unchanged; `f49ba9d…` →
  `398c9e8…` adds only `reports/dd1_d7c_b_tr_delivery_receipt.md`. The `f49ba9d` package and the
  `398c9e8` package are named as different deliveries.
* The original TR task book keeps its body; it gained a provenance preface in its own round and this
  round registers a byte-for-byte copy of the R1 task book as a new file instead of rewriting it.
* The two escaped raws were deleted and the earlier log was overwritten: those events stay in the
  record with their original wording, and their digest figures are not presented as recoverable text.
* A partially built evidence directory from an aborted registration attempt was **renamed aside** to
  `D:\dc_tr_review_R1_20261027_222732\parked_abandoned_registration\` — nothing published was deleted,
  and the abandoned directory is not part of the delivery.
* The judging entry of the shared record tool was itself a defect this round found by running it:
  `dd1_d7c_b_tr_record.py --gates <dir>` called `publish(directory)` while judging, and pointed at the
  native round's directory it **rewrote three published files** (`windows_all.csv`,
  `delay_attribution.csv`, `delay_attribution.json`) — and rewrote them lossily, because that
  re-extraction could not reach the answers, so it emptied the settling columns and dropped the raw
  digest column from the delay table. Nothing was deleted: the mutated bytes plus the two files the
  same run rewrote identically are parked in
  `D:\d7cb_tr_r1_parts_staging\parked_gates_overwrite_20261028_020335`, and the committed bytes were
  restored, after which **every file under
  `results/evidence/dd1_d7c_b_tr_r20261026_132228_3fc148` hashes to its HEAD blob** (whole-directory
  comparison, 0 mismatches). `gates()` now calls `require_published()` instead: a missing derived
  table is a refusal naming it and naming the entry that creates it, and the record selftest proves
  the judging entry leaves the tree it judges byte-for-byte unchanged. No figure in this report comes
  from the mutated bytes: the export, the install, the re-judgement (838/838, `restatus rc=0`), the
  reviewer instrument and the three forgery refusals all completed between 09:48 and 09:57 on this
  machine's clock, and the write happened at 09:59:49.
* `input_identity.json` as first registered published the reviewer ZIP's machine-local absolute path,
  which contains this operator's user name. The payload commit carried it into one file
  (`results/evidence/dd1_d7c_b_tr_r1_r20261027_143223_4c8a81/input_identity.json`); the record now
  stores the file name, the byte count and the same digest with a `path_note` saying why the directory
  was dropped. The ZIP identity itself did not change: `44,147 B`,
  `sha256 5c9b267a484aa7c1c68dbf38ce242d6bd7ef377937341f35b5a2826f508440a8`. Nothing else this round
  added carries a `C:\Users\…` string — a whole-tree grep over this round's paths finds that letter
  sequence only inside base85 payload lines, where it carries no information. Earlier rounds'
  published files that do contain such paths are left as they are: rewriting another round's evidence
  is not this round's authority.
* The sequence packaging took three exports, and the two failed attempts are kept on disk rather than
  cleaned up: `native_export_v6` crashed while discarding a ceiling-excluded artifact that had
  already been split into parts (the discard removed the name that was written and then read it
  again, which no longer existed); `native_export_v7` was pointed at a worktree whose `rtl/` directory
  holds no `.vcd` at all, so it recorded 19 artifacts and dropped the whole trace set **silently** —
  a narrower delivery than its own report claimed, which is the failure mode this round was told to
  close. The fixed export, `native_export_v8`, refuses that narrowing, records 21 artifacts, verifies
  19 and names the 2 it does not copy. All three staging trees and their logs stay under
  `D:\d7cb_tr_r1_parts_staging\`. The single-file sequence set that had already been published into
  the round's evidence directory was moved aside whole (32,362,643 B in
  `parked_v5_sequences_20261028_015451`) before the verified part set was installed; nothing was
  deleted. Export, verify, install, install-verify and re-judgement ran as separate steps, each with
  its own recorded exit code, and `--restatus` ran only behind a zero from the integrity check:
  `export rc=0`, `verify rc=0`, `install rc=0`, `install verify rc=0`, `restatus rc=0`.

## 10. Entries and replay

| entry | what it does offline |
| --- | --- |
| `dd1_d7c_b_tr_r1_native.py --budget/--export` | reads the stored answers, writes the sequences, the identity chain and the manifest; `--export … package` is the package staging build, which copies the trace containers and applies no tracked ceiling |
| `dd1_d7c_b_tr_r1_native.py --verify <dir>` | rejoins every split container, checks each part digest and byte count against the manifest, re-hashes the shipped dependency and names what it did not verify |
| `dd1_d7c_b_tr_r1_publish.py --publish/--restatus` | re-extracts the tables with the patched tools, publishes the ten statuses, diffs old against new, runs the recomputer |
| `dd1_d7c_b_tr_r1_recompute.py` | standalone, stdlib-only, integrates from the exported sequences; works with no Git and no guest |
| `tests/dd1_d7c_b_tr_r1/probe_r1_recompute_forgery.py` | the three forgeries against the real entry, on a complete package copy |
| `dd1_d7c_b_tr_trace.py --reconvert` | re-reads a stored trace and compares with the delivered deck |

Module selftests on the delivered bytes: contract 35/35, decks 19/19, trace 50/50, run 44/44,
measure 61/61, r1_native 17/17, record 34/34 — 260 records, none failing. `record`'s two newest
records are this round's own defects turned into gates: the judging entry writes nothing into the
directory it judges (byte digests of the whole tree compared before and after) and a foreign schema is
reported as a verdict instead of being rewritten into the earlier round's tables. `r1_native` now also
proves the three packaging rules this delivery depends on — a split container rejoins to the same bytes
and digest, an artifact the ceiling excluded leaves no part behind, and a trace directory holding no
real trace is a refusal rather than a shorter delivery. `record`'s fixtures read the local answers and
the local vvp logs through `QODER_TR_RAW_DIR` and its evidence-directory argument (which is never
written); run without them it refuses, because the raws, logs and traces are not in the object store.
Out of the repository the recomputer replays on a copy: 838/838 clean, three named refusals. The
Git-bound packaging entry is run at the repository, and any entry that needs Git is declared NOT_RUN
inside the package copy. What the copy does run was run: `independent_recompute.py` re-derived
**838/838 at rc=0**, and `dd1_d7c_b_tr_r1_native.py --verify` on the delivered directory inside the
extracted copy rejoined every part and reported **19 verified, 2 named excluded, 0 problems at rc=0**,
with no Git and no guest. That took two packaging fixes: the range alone did not carry
`scripts/dd1_d7c_b_dc_run.py` (which the export entry imports) nor the frozen PREP schedule and window
tables and the accepted DC table that its contract module opens at their published paths, so the
package now carries the entries' import and input closure instead of a subset of a diff.

## 11. Not verified / limits kept open

* `NATIVE_SEQUENCE_REINTEGRATION` covers the 37 published windows and both charge columns for all nine
  cases. The internal 26 columns of HYB-120 and HYB-200 are not delivered as re-integrable native
  fragments — the tracked ceiling excludes them and says so in bytes — so any statement needing an
  internal instant of those two cases outside the published row tables stays `NOT_VERIFIED`.
* The two trace **bytes** are outside the tracked delivery: `*.vcd` is a family the repository's own
  safety rules never track, and as containers they would take the 416,278 B that separate the
  RS-SWITCH and RS-FULL fragments from the ceiling. What is tracked is their identity — name, byte
  count, uncompressed digest, the native conversion digest they were checked against — and the
  re-read result of each (§5). The gzip copies enter the reviewer package, and the package's own
  builder admits them only after the same digest check; a reviewer replaying only the tracked tree
  re-reads nothing from the traces and must not be told otherwise, which is why `--verify` lists them
  as excluded instead of counting them.
* The guest-side logs of the native round stay on this machine; they open with a command line that
  carries an absolute path into the tool tree, so their digests and MARK lines are published instead.
* Preflight answers are exported with the 12 required columns only for the four long runs, because
  the ideal-load preflight prints no DUT internals.
* SOA, LED, high side, array RC, LUT, full MOS controller, TCON, layout, PVT/MC are out of scope and
  unsigned. `NEXT_NATIVE_STAGE_AUTHORISED=NO`.

## 12. Delivery read-back

```text
payload commit      f38a8bd30d42730b4b348d30300200ccab761e93   (222 files: tools, evidence, task book)
record commit       706d6e54ce717895456a7f67e4a339d81b3af380   (report, handoff, nameless input path)
packaging commit    recorded in reports/dd1_d7c_b_tr_r1_delivery_receipt.md, with its own read-back
branch pushed       origin/poc/data-pam-d7c-b-tr-r1, new branch, normal push (no force, no --no-verify)
remote full SHA     706d6e54ce717895456a7f67e4a339d81b3af380 at 2026-10-28T02:42:51Z (git ls-remote)
main                23e471cb936b421ee97e1250c3be06edf96f9937 (unchanged on the remote, verified)
other branches      poc/data-pam-d7c-b-tr 398c9e8, -dc-r1 61621f6, -prep-r2 e51c532 (all unmoved)
reviewer ZIP        bytes and sha256 recorded outside the archive, in the delivery receipt
```

Both read-back paths were taken on the remote (`git ls-remote` through the machine's proxy) and at
the repository (`git rev-parse HEAD`), and they agreed; the pre-commit safety gate ran for real on
every one of these commits and reported `SAFETY_GATE: PASS` (222 objects, then 4).

## 13. Stop

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
