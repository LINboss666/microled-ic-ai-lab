# SCAN-1R2D1 — test-preparation fixes on top of the accepted S2 topology (no simulation)

Date 2026-10-13. Baseline: `34d5125a4dfd5c7423776547d6eab4f8fb616fee` on `poc/scan-driver-1ch`
(re-read with `git ls-remote` before editing). The new S2 cell netlist
`spectre/sc1_level_shifter_r2d.scs` is **kept exactly as reviewed** — connectivity, sizes and the
audited tools are untouched (`git diff --name-only 34d5125 HEAD -- spectre/ scripts/sc1_read_psf.py
scripts/sc1_delay.py scripts/tb_preflight.sh scripts/sc1_supply_check.awk scripts/run_spectre.sh
scripts/sc1_s1r.sh scripts/sc1_s2.sh` → 0 lines).

What this round is: the review accepted the S2 **connections** statically and rejected the *test
preparation*. `reports/scan_driver_r2d_static_review.md` stays as the previous round's record; its
S1 "10/10" style reading is superseded by §C below.

**No simulator was called.** Everything here is source preparation, offline re-reads of files already
on disk, local mock/synthetic data, and `PREFLIGHT_STATIC_PROBE=1`. `S1_FRESH_REGRESSION`,
`S2_FUNCTIONAL_TT`, preflight full, C²MOS re-simulation and the new PDK stay NOT_RUN / PAUSED_BY_USER.

---

## A. S1 future regression entry — `scripts/sc1_s1_r2d_regression.sh`

Each item was reproduced against the draft, then fixed. No item was "fixed" by starting a simulator.

| # | defect the reviewer named | measured before | what it does now |
|---|---|---|---|
| A1 | `[ -d "$PROJ/spectre/C2MOS_DFF.scs" ]` tests a directory | `-d` → exit 1, `-f` → exit 0 | `-f` + readability on every required input; a missing one is `HARNESS_ERROR` exit 8 |
| A2 | `v=$(read_number ...); rc=$READ_RC` — the assignment lives in a command-substitution child shell | mock reader exiting 3 → `READ_RC: unbound variable`, rc **127** | `run_read` runs in this shell, returns the reader's status directly, and the status is judged **before** any numeric conversion (`scripts/sc1_csv_writer.py` also refuses a ragged row) |
| A3 | preflight rc captured but not enforced | runner reached after a failed preflight | non-zero preflight = `PRECHECK_FAIL`, runner call count 0; `SIM_FAIL` needs exit 0 **and** exactly one `S1REG_<tag>: PASS` line **and** `CHECK error_hits=0` **and** a readable `CHECK datafile=`; an older raw is never used |
| A4 | DC rows wrote MEASURED + ON/OFF without comparing | a wrong polarity did not fail the run | per-row expectation, plus blank/qbar read back against the row's own label; any mismatch sets `fail=1`; the fault row can no longer mask a failing normal row |
| A5 | stimulus was not the historical one | data held at 0 V, clock period 200 n, blank released 400..450 n while T1..T5 were kept | stimulus copied verbatim from `sc1_s1r.sh` (clock `delay=50n rise=1n fall=1n period=100n width=50n`, data `wave=[0 0 260n 0 270n 1.8 620n 1.8 630n 0 900n 0]`, blank `wave=[0 1.8 450n 1.8 460n 0 900n 0]`, `stop=900n maxstep=1n method=traponly`); DC truth decks drive the gate only (no DFF with floating d/clk behind an ideal source); the negative is the historical BLANK-pin-to-vss rewire |
| A6 | WINDOW string with literal backslashes, `row()` missing a closing quote | invalid extra cases, unparseable CSV | windows as a plain multi-line list; rows accumulated TAB-separated and written by `sc1_csv_writer.py`; the self-test re-parses the CSV (14 fields per row, unique case ids) |
| A7 | printed `$QODER_PDK_LIB` with nothing defining it | deck carried an undefined include | `cad_env.sh` then the git-ignored `spectre/pdk_local.env` are sourced **in this shell** (a `$( ... )` would throw the value away); unresolved → `BLOCKED`, exit 7, before any deck is written. `run_spectre.sh` expands the variable and refuses it with exit 9 if unset, which is the same convention the 139 decks that have run use |

Guards kept: dry run by default (`run_rc=0`, nothing executed, no deck written), `RUN=1` without
`QODER_SIM_AUTHORISED=1` → **5**, authorised but unresolved model library → **7**.

`scripts/sc1_r2d1_entry_selftest.py` runs a **local copy** of the entry with mocked preflight/runner/
reader over synthetic raws. 18/18 cases, on guest Python 2.6.6 / bash 4.1.2 and Windows Python 3.12 /
bash 5.2.37: `guards_dry`, `guards_run_noauth`, `guards_pdk_blocked`, `all_good` (16 rows, 4 runner
calls, exit 0), `csv_structure`, and the refusals `preflight_refuses` (runner calls **0**),
`runner_bad_rc`, `runner_two_tokens`, `runner_no_datafile` (a `STALE_old_result` file is present and
never used), `runner_log_errors`, `reader_error`, `stimulus_read_fail`, `truth_wrong_value`,
`stimulus_mismatch`, `window_fail`, `window_states_read_fail`, `toothless_fault`,
`fault_cannot_mask_truth`. Evidence: `results/evidence/sc1_r2d1_entry_selftest.csv`, every row
labelled `SYNTHETIC_MOCK_not_a_circuit_regression`.

Two defects of my own that the mocks caught, because they only report what they check:
`row()` used `$10..$14`, which bash reads as `$1` followed by a digit (fields silently merged) — now
braced; and a failure case could "pass" merely because the script aborted early, so each injection now
also requires the entry's own verdict line, the expected row and the expected column value, and
rejects `MOCK_MISS` in the output.

## B. S2 decks and measurement preparation — `scripts/sc1_s2_r2d_gen.py`

| # | defect | before | after |
|---|---|---|---|
| B1 | `seq_ok_early_release` drove 3.3 V into a 0 V rail, contradicting the report's claim that no deck does that | `core_ok33` 100..150 n → 3.3 V while `vdd33` rose only 500..700 n | `vdd33` is 3.3 V from t=0, the **core** ramps 500..700 n, and `core_ok33` is asserted early at 100..150 n — still the premature-release case, inside the rail that exists. An external high-domain over-drive would be a separate `EXTERNAL_OVERDRIVE` case and is not part of this round |
| B2 | three decks held `en` at an ideal 1.8 V after `vdd18` fell to 0 | labelled as if the core driver failed with its supply | `seq_core_down`, `seq_core_down_ok_held`, `seq_ok_delayed_drop` are marked `EXTERNAL_DRIVE_FAULT`, and each has an `en_follows` twin whose `en` falls with the low rail (never above `vdd18` at any joint breakpoint). Both situations are in the index; the over-drive is not hidden |
| B3 | decks included only the cell, saved only voltages, and the report claimed a source-current path | no model include, no current save | `include "${QODER_PDK_LIB}" section=tt` (verified form, value from the git-ignored local env, never committed) with `DECK_BINDING_PENDING` in every index row and `BLOCKED` if the env file is absent; TT is a measured section name, 27 °C is a `POC_ASSUMPTION` and **no `temp=` line is emitted** because no deck in this project has ever run with one (`TEMP_LINE_SYNTAX_PENDING` → see that column). A series rail `iprobe` was **measured**, not assumed: `PREFLIGHT_STATIC_PROBE=1` gives rc **1**, stage `supply_contract`, 5 `SUPPLY_FAIL` lines (`results/evidence/sc1_r2d1_iprobe_static_probe.csv`), so rails stay directly driven and the decks save the per-device `save <inst>:1` currents (the two verified save forms) plus every terminal node; the sum's sign convention stays PENDING. The audited checker was not touched |
| B4 | dynamic and load cases existed only for C0 | 0 C1 dynamic decks | `dyn_c1_rise`, `dyn_c1_fall`, `dyn_c1_repeat3`, `load_c1_0pF/0.2pF/1pF/5pF` on the final `gate33` net — the same finite shape C0 had, no S3/S4 expansion |
| B5 | `load_pF` stored `1p`-style text; static acceptance was read as covering the ramp | `load_pF='1p'` | numeric `0 / 0.2 / 1 / 5`; OP contract, ramp **target** and stimulus stay separate columns; every row carries `future_verdict=NOT_RUN` and `static_certifies_dynamic_rail_range=no` |
| extra | two decks in the committed matrix were byte-identical while presented as different cases | `st_c1_enhigh_no_guard` == `st_c1_enhigh_okhigh` == `rail_18_33`, all sha `5da1fac7a6fd2732` | merged into declared roles on one deck; the generator now refuses any duplicate (`DUPLICATE_DECK`, exit 3) — this is what surfaced the problem |

All PWL is the flat `wave=[t v t v ...]` form that passed on this build; the parenthesised pair form is
gone. 37 decks, 37 distinct sha256.

`scripts/sc1_r2d1_pwl_audit.py` recomputes each fold at the union of its breakpoints: **64 checks,
0 failures** — every normal deck keeps `en` inside `0..vdd18(t)` and `core_ok33` inside `0..vdd33(t)`;
the three `EXTERNAL_DRIVE_FAULT` decks do contain the over-drive they declare (first breach at 500 ns);
two mirrored bad stimuli (`mirror_core_ok_old_early_release` = the waveform the old B1 deck actually
wrote, and `mirror_en_held_over_dead_rail`) are **REJECTED**; and `positive_en_follows_rail` still
passes, so the audit is not a machine that always says no. It audits the generator only; the general
supply gate is unchanged and the vss-miswire / absent-vdd33 negatives stay its responsibility.

Static matrix over the regenerated decks (`PREFLIGHT_STATIC_PROBE=1`,
`results/evidence/sc1_r2d1_static_matrix.csv`): 37 rows, **37/37 as the index promises**, every row
`simulator_called=no` — 34 accepted at rc 7 with `CIRCUIT_VERDICT: NOT_RUN`, `neg_vss_miswire` and
`neg_vdd33_source_absent` refused at rc 1 / stage `supply_contract`, `neg_output_polarity_fault`
deliberately accepted (legal wiring; a wrong polarity is a circuit verdict, and this round does not
claim any detector caught it). Note: the runner must be given **absolute** deck paths — with a
relative `--decks` all 37 rows returned rc 9 `netlist_outside_project`, which is a harness fault and
was scored as such, not as a circuit result.

## C. S1 historical re-analysis — `scripts/sc1_r2d_s1_reanalysis.py`

The reviewer's synthetic probe (two DC raws with `blank=0.7 V`, `en` deliberately matching the labels,
a tran/fault raw with only `time/en/q`, no decks, no history CSVs) returned rc 0 / rows 10 /
pass_or_detected 10 / **PASS** with every deck hash `MISSING`. That showed the verdict was made from
output values alone; it did not show the historical data to be wrong.

Now: **25 columns** with the assertion result, the stimulus check, the traceability and the historical
difference kept apart (the difference is its own `historical_difference_V` column, next to the band it
was judged against); a truth row must read back its own `blank` and swept `qbar` at their labels; a
transient row must read `blank/q/qbar/d/clk` in the same window and an unreadable one makes the row
incomplete, not green; a reader exit code is never parsed into a number and non-finite values are
rejected; the independent awk cross-check now *participates* (failure, zero samples or disagreement
beyond the display band count against the row); a sample count that reaches the probe ceiling is
labelled `lower_bound`; and without decks or history the overall result is `PARTIAL_NOT_VERIFIED` /
`ASSERTION_CHECK_ONLY` — `10/10` is not reachable. Exit codes 0 CERTIFIED / 3 PARTIAL / 1 FAIL, and a
row that does not match the header stops the run as `HARNESS_ERROR`.

Tolerance now has a stated source, in a per-row column: the history CSVs are 6-**decimal** text
(half step 5e-7, which is why a genuine 5.38288e-09 legitimately printed as `0.000000`), and
`sc1_read_psf.py` prints 6-**significant** digits — the band is the sum of the two. "Inside the band"
is a display-precision statement; "the threshold still passes" is a different column.

Adding the `historical_difference_V` column made this concrete in a way I have to report: the summary
counted row statuses with hard-coded indices, so after the insertion every case silently became
PARTIAL (the index was reading the agreement column). The synthetic self-test is what showed it — a
case that must return 1 was returning 3 — and the counts now derive their positions from `HEADERS`.

`scripts/sc1_r2d1_reanalysis_casegen.py` + `sc1_r2d1_reanalysis_selftest.py` add exactly the six
synthetic cases asked for (no general PSF-parser work): `all_matching` CERTIFIED rc 0, `wrong_blank`
FAIL rc 1, `missing_deck` PARTIAL rc 3, `missing_history` PARTIAL + `ASSERTION_CHECK_ONLY` rc 3,
`unreadable_evidence` FAIL rc 1, `no_fault_run` PARTIAL rc 3 — **6/6** on guest Python 2.6.6 and
Windows Python 3.12 (`results/evidence/sc1_r2d1_reanalysis_selftest.csv`).

The re-read of the **local** original data (raws `cadence_work/sc1_sim/sim/s1r_*.raw`, decks
`cadence_work/sc1_sim/s1r_*.scs`, history `s1r_truth.csv` / `s1r_transient.csv` — all local, not
committed, and not available to the cloud reviewer):

| row | re-read value | n | assertion | stimulus | vs history |
|---|---|---|---|---|---|
| Q1 BLANK0 | 1.8 V | 1 | PASS | PASS | diff 0, band 5.5e-06 → WITHIN |
| Q0 BLANK0 | 5.38288e-09 V | 1 | PASS | PASS | diff 5.38e-09, band 5.0e-07 → WITHIN |
| Q1 BLANK1 | 6.47156e-09 V | 1 | PASS | PASS | diff 6.47e-09, band 5.0e-07 → WITHIN |
| Q0 BLANK1 | 1.03846e-09 V | 1 | PASS | PASS | diff 1.04e-09, band 5.0e-07 → WITHIN |
| T1 en max 400..455 n | 0.0753447 V | 117 | PASS | PASS | diff 3.00e-07, band 5.5e-07 → WITHIN |
| T2 en min 520..620 n | 1.79991 V | 157 | PASS | PASS | diff 4.40e-07, band 5.5e-06 → WITHIN |
| T3 q min 410..520 n | 1.76555 V | 192 | PASS | PASS | diff 4.80e-07, band 5.5e-06 → WITHIN |
| T4 en max 700..860 n | 3.66477e-06 V | 275 | PASS | PASS | diff 3.35e-07, band 5.0e-07 → WITHIN |
| T5 q max 700..860 n | 0.00200669 V | 275 | PASS | PASS | diff 3.07e-07, band 5.1e-07 → WITHIN |
| F1 BLANK→vss | en max 1.8001 V | 116 | **DETECTED** | PASS | **NO_HISTORY** (no band exists to compare against) |

**S1_HISTORICAL_REANALYSIS = PARTIAL_NOT_VERIFIED** (rc 3, 9 of 10 rows certified, 0 failing). The one
non-certified row is the fault injection: no committed CSV records a historical numeric for it, and the
`1.800096` the previous round quoted was this machine's own re-read of the same raw, not history — so
the row states `NO_HISTORY` instead of inventing an agreement. The detection itself is real: the
unchanged T1 assertion rejects `en = 1.8001 V` inside 400..455 n. Evidence:
`results/evidence/sc1_r2d1_s1_historical_reanalysis.csv` (sanitised: relative raw names, sha256, rc,
values — no raw PSF bytes committed).

One defect of my own surfaced while writing these checks: the F1 row required the faulted raw's
**blank node** to sit at 0 V. The historical negative does not clamp the node — it ties the gate's
BLANK *pin* to vss in the deck while the blank source keeps its PWL — so the row failed the real
historical run. It now verifies the rewire in the deck text and Q=1 inside the window.

---

## Known limits and failures of this round

* The A-section is proof about **control flow with mocks**. The S1 circuit has not been re-simulated;
  `S1_FRESH_REGRESSION = NOT_RUN / PAUSED_BY_USER`.
* Deck model binding is unresolved *by design* here: no PDK path is committed, `QODER_PDK_LIB` is only
  defined in the git-ignored local env, and every deck therefore ends the round at
  `DECK_BINDING_PENDING`. Nothing in this report says a deck can be run yet.
* `temp=27` was not invented into 37 decks: no deck in this project has ever carried a temperature
  line, so the syntax is `PENDING` and 27 °C stays a `POC_ASSUMPTION`.
* Rail current is **not** measured by a probe: the series `iprobe` is refused by the static gate, and
  the per-device `:1` sum's sign convention is unconfirmed → `PENDING`.
* The offline PWL audit reads the generator's declared breakpoints. It cannot see a waveform the
  generator does not declare, and it is not a general Spectre parser.
* Guest SSH is down (no guest IP; `vmrun getGuestIPAddress` fails, `tcp/22` unreachable) while the
  VMware Tools channel works, so file transfer this round went through an untracked local helper
  `scripts/push_chunked.sh` (base64 chunks + md5 read-back). No network or VM configuration was
  changed; the interface was not brought up because that needs the user's approval.
* Deck bodies are regenerated, not committed (only the index, the generator and the evidence CSVs are).
  PDK/raw sha256 values in the manifest are **local traceability only** — the cloud has no bytes, so
  nothing here claims cloud verification of them.

## States

| item | this round |
|---|---|
| S2_TOPOLOGY_STATIC_ACCEPTED | accepted in the previous round, unchanged here (`git diff` clean) |
| R2D1_ENTRY_PREPARATION | COMPLETE for A (18/18 mock cases) and B (37 decks, 64 envelope checks, static 37/37 as promised) |
| S1_HISTORICAL_REANALYSIS | PARTIAL_NOT_VERIFIED — 9/10 rows certified against the local raws, F1 has no historical numeric |
| S1_FRESH_REGRESSION | NOT_RUN / PAUSED_BY_USER |
| S2_DECK_STATIC_VALIDATION | static matrix only; CIRCUIT_VERDICT=NOT_RUN on every accepted row |
| S2_FUNCTIONAL_TT / dynamic / power-fail / stress | NOT_RUN |
| preflight full, Virtuoso, C²MOS re-simulation, new-PDK simulation | NOT_RUN / PAUSED_BY_USER |
| R2 full circuit acceptance, R3 chaining | NOT_COMPLETED / NOT_STARTED |
| S3, S4 | NOT_STARTED |
| SOA_SIGNOFF / GEOMETRY_RANGE | NO / NOT_VERIFIED (no W/L range or rating table read from the model) |
| S2 autonomous power-fail protection | NOT_IMPLEMENTED (best future case remains SAFE_OFF_WITH_ASSUMED_CORE_OK) |

Next step is **not** an automatic S3 or a simulation: it is the cloud/owner review of this preparation,
then, under a separate explicit authorisation, the first real TT run of the S2 decks with the model
binding resolved.

Commands actually run this round (all offline):

```bash
bash -n scripts/sc1_s1_r2d_regression.sh
PROJ=/d/ic617_agent_bridge bash scripts/sc1_s1_r2d_regression.sh                    # dry run rc 0
PROJ=/d/ic617_agent_bridge RUN=1 bash scripts/sc1_s1_r2d_regression.sh              # rc 5
PROJ=/d/ic617_agent_bridge RUN=1 QODER_SIM_AUTHORISED=1 \
     bash scripts/sc1_s1_r2d_regression.sh                                          # rc 7 BLOCKED
python scripts/sc1_r2d1_entry_selftest.py            # 18/18 (Windows py3.12; guest py2.6.6 likewise)
python scripts/sc1_s2_r2d_gen.py --outdir <scratch>  # 37 decks, duplicate gate active
python scripts/sc1_r2d1_pwl_audit.py                 # 64 checks, 0 failures, both mirrors rejected
bash scripts/sc1_s2_r2d.sh                           # generate + audit + static + iprobe probe, rc 0
python scripts/sc1_r2d_static_run.py --index ... --decks <abs> --preflight ... # 37/37
python scripts/sc1_r2d1_iprobe_probe.py              # rc 1 / supply_contract (measured, not assumed)
python scripts/sc1_r2d1_reanalysis_selftest.py       # 6/6
python scripts/sc1_r2d_s1_reanalysis.py --sim-dir ... --deck-dir ... \
       --history-truth ... --history-transient ...    # rc 3 PARTIAL_NOT_VERIFIED
```
