# SCAN-1 agent handoff checkpoint

## CURRENT_STATUS (single authoritative table; everything below this block is history)

Updated 2026-10-13 during **SCAN-1R2E1 / gate fixes and re-read of the existing waveforms**. Start point
re-read before editing: remote `poc/scan-driver-1ch` = `593a8beb9a55840d5f3c33633abb635713af84aa` =
local HEAD (the R2E native TT round), no unknown upstream commits. Full write-up:
`reports/scan_driver_r2e1_gate_review.md`; artifacts: `results/evidence/sc1_r2e1_*`.

**No simulator was called this round** — no Spectre, no ngspice, no preflight full, no operating-point
probe, no Virtuoso, no re-run of any S1/S2 deck. Only offline tests against isolated mocks and a re-read
of files R2E already produced. `spectre/`, the audited reader/delay/preflight/supply checker, the runner,
the old S1/S2 entries and the S1 window contract are byte-identical (`git diff --name-only 593a8be HEAD`
over them → 0 files); no old CSV was rewritten.

| item | status | evidence |
|---|---|---|
| PREFLIGHT_RC_PROPAGATION | **CLOSED** | both new entries called the preflight through `... 2>&1 \| tail -4/5`, so they recorded *tail's* status: the reviewer's mock printed `TESTBENCH_PREFLIGHT: FAIL` and exited 1 and the row still read `rc=0 / PASS`, and the runner was still called. Now every call goes through `scripts/sc1_r2e1_call_contract.py`, which uses `subprocess.Popen(argv)` with **no shell**, captures the whole output before shortening anything, requires rc=0 **and** exactly one completion marker with no FAIL line, and returns straight to the caller so the runner and readers are never reached. Concretely proven from the R2E record itself: the six `PREFLIGHT_FULL` rows of `sc1_r2e_calibration.csv` carry the retained note `SUPPLY_RESULT FAIL / PREFLIGHT_REJECT: contract_refused:contract entry vdd18 matches no instance port` under `rc=0, PASS` |
| Erratum on the R2E preflight columns | **open as a record, corrected in the write-up** | that bench's rails are `rail`/`vss`, so the contract `vdd18=… vdd33=…` matched no instance port: **preflight full never passed on the calibration bench**, and R2E's §2/§3 claim is corrected in place (`scan_driver_r2e_native_tt.md` §3 correction block). The calibration *numbers* stand (their `runner_rc=0` and `SPECTRE … rc=0` came from a call with no pipeline), but "preflight full with the same legal port contract" is **not** achieved for that bench; the bench needs `rail=1.8 vss=0`, which belongs to a future authorised run. For the same reason the
`preflight_rc` column of the 15 S2 decks is void (read it as unrecorded, not 0): the retained excerpt
shows the per-net `OP_OK` contract lines but stops before the completion marker `sc1_r2e1_callpath_selftest.csv` shows the fixed rule refusing the same shape |
| RUNNER_SUCCESS_CONTRACT | **CLOSED** | accepting a run because `<LABEL>: PASS` appeared is replaced by: the runner's own rc=0, exactly one PASS for **this** label and no FAIL, exactly one `SPECTRE name=<this deck> rc=0`, `CHECK error_hits=0`, a zero-error `done_line`, and this run's own datafile + log present, non-empty and **inside this deck's own `sim/`** (so a failed run pointing at an older readable raw is refused before any reader runs). `preflight_rc` / `runner_rc` / `spectre_rc` stay three separate values. The calibration entry also writes one deck file per candidate save form, because three runs sharing a name shared one raw directory |
| VTX_STRICT_INPUT | **CLOSED** | `sc1_r2e_vtx.py` no longer has its own parser: it calls the audited `sc1_read_psf.parse()` (which already refuses non-finite values, a duplicate signal inside a group, a file ending mid-group, and any group whose signal set differs) and adds what `parse()` does not check: the axis must be `time`, times strictly increasing, both signals present per sample, the difference finite, unknown mode / reversed window / too-few samples refused. The reviewer's three counterexamples (`1 / 2e-09`, `inf / 1e-09`, reversed axis `2 / 2e-09`, all `rc=0`) now return rc 7/5/8 with no number printed. Tie rule stated: the first sample reaching the extreme wins |
| Call-path verification | **24/24 on guest 2.6.6 and Windows 3.12** | `scripts/sc1_r2e1_callpath_selftest.py` drives the **real** `sc1_r2e_s2_tt.run_case` and `sc1_r2e_calibrate.preflight_and_run` against preflight/runner/reader mocks that exist only in a temporary directory; the mocks also refuse a path outside that root, refuse if `RUN`/`QODER_SIM_AUTHORISED` is in their environment, and refuse a runner whose `$1` is not the netlist. Each case asserts the concrete row (recorded rc, verdict, reason) **and** the preflight/runner/reader call counts: 11 refusal scenarios at 1/0/0 or 1/1/0 plus the success control at 1/1/16 (S2, reader reached) and 1/1/0 (calibration stops after the run). Rows are labelled `SYNTHETIC_MOCK_NOT_A_CIRCUIT_RUN`; a driver crash is recorded as FAIL, never as a detection |
| Existing suites kept | **16/16 vtx · 26/26 S2 entry · 5/5 window contract cases unchanged** | `sc1_r2e1_vtx` list runs inside `sc1_r2e_vtx.py --selftest`; the R2E 26-case entry suite re-ran unchanged against the new plumbing (`sc1_r2e1_s2_entry_selftest.csv`). The frozen tools were not reworked because a caller had been wrong |
| C1 stress re-read | **123/123 PASS, no refusal, no change** | `sc1_r2e1_vtx_reanalysis.csv`: each original `DEVICE_STRESS_PEAKS`/`STRESS_CROSSCHECK` row recomputed with the strict tool **in the same case window**, carrying the re-read file SHA256, node pair, window with sample count, original min/max, strict min/max, difference, extreme times, exit codes. Agreement is judged at the original output's 6-significant-digit display band (±5e-7 V at 1 V), and the three cross-check rows were re-performed (model `:vgs` vs node difference, worst 4.05e-6 V). First attempt compared whole-file extremes against window values and produced four apparent FAILs; that was this tool's own mistake, fixed, not a circuit result |
| C2 sampled waveforms | **195 rows, 0 missing, 0 refused** | `sc1_r2e1_waveform_samples.csv`: real consecutive samples only (no interpolation, no resampling, no raw PSF committed) for the 1 pF C0/C1 both directions with the input 50 % and the output 90/50/10 % fall band, the 5 pF coarse and fine step at the same crossing, all 12 attributed repeat3 input/output 50 % edges with the next input boundary of either direction, the polarity negative's rise that the normal criterion refused, one device stress extreme with its same-sample D/G/S/B, and one dynamic rail-current peak with its neighbours. Currents keep the raw signed reading and the calibrated `injected = -(Vsource:i)` |
| C3 report corrections | **applied in place, experiment rows untouched** | (1) R2E §4 claimed the F1 faulted deck gave `en max=0.0753447 V` failing `< 0.9` — that value satisfies it and belongs to the normal T1 row; the CSV's F1 row is `value_V=1.8001, row_verdict=DETECTED` with its setup `PASS`, i.e. the fault holds `en` high. (2) "12/12 calibration runs" is 6 runs with 12 consistent read-back values (log + header inside the same run). (3) the `SAVE_PATH_AUDIT` finding is split into the reviewed decks' ignored save request (a warning, still `PARTIAL`) and this round's actually-read signals, and no verdict was renamed |
| Native TT results | **unchanged in substance, layered** | S1 stays the R2E native evidence and this round is **not** an S1 fresh rerun; the S2 numbers stay "already recorded native" with the re-read on top. Dynamic figures stay `MEASURED`, `budget NOT_DEFINED`, `SOA_SIGNOFF NO`, `AUTONOMOUS_POWER_FAIL NOT_IMPLEMENTED` |
| Fixed entries re-run? | **NO_RUN** | no authorisation to simulate this round, so the corrected gates have produced no new native numbers; the next authorised session re-runs calibration (with a bench-appropriate contract), S1 and S2 under them |
| Guest network | **not touched** | no `dhclient`, no ONBOOT/.vmx/service/licence/VM-power action; the VMware Tools channel carried the files |
| 37-deck supply matrix / R3 / S3 / S4 / corners / layout | **NOT_RUN / NOT_STARTED** | unchanged |

### Next step is a decision, not a continuation

The three reproduced tool defects and the missing sampled evidence are closed, and the R2E record now
says what it actually observed about its own preflight. Stopping again at the **native TT results review
gate**: a re-run of calibration/S1/S2 under the fixed gates, the power-sequence matrix, R3 chaining and
S3/S4 each need a new authorisation.

## HISTORICAL_STATUS (SCAN-1R2E round, kept for audit; superseded by the R2E1 block above)

> The numbers below are the native TT record and still stand. **Two statements in this block were
> corrected by R2E1**: the calibration entry's `PREFLIGHT_FULL` rows were a supply-contract *refusal*
> recorded as PASS (a `| tail` pipeline hid the exit code), and the F1 / "12/12 runs" wording in
> `reports/scan_driver_r2e_native_tt.md` was fixed. Read the R2E1 block above for the current state.


Updated 2026-10-13 during **SCAN-1R2E / minimal native TT verification (executed)**. Start point
re-read before editing: remote `poc/scan-driver-1ch` = `dd93f6f432a32fc5f1177223a50ff511e83351c2` =
local HEAD; `git ls-remote` showed no unknown upstream commits, so nothing was merged or overwritten.
Full write-up: `reports/scan_driver_r2e_native_tt.md`; artifact index:
`results/evidence/sc1_r2e_manifest.csv` (35 rows: this round's files plus the protected inputs).

**This round did call the local simulator**, under the authorisation the user recorded at
2026-10-13 11:39:44 (Asia/Shanghai) for exactly this scope: model/temperature/current calibration, one
fresh S1 regression, and the S2 minimal normal function + representative dynamics + the real polarity
negative at TT / 27 °C / 1.8+3.3 V. Everything ran through the VMware Tools channel (SSH is still
down). Protected inputs are byte-identical: `git diff --name-only dd93f6f HEAD --` over the two S1/S2
netlists, the C²MOS cell, the reader, the delay tool, the preflight, the supply checker, the runner and
the audited S1/S2 entries → **0 files**.

| item | status | evidence (all new files, `sc1_r2e_*`; nothing historical was overwritten) |
|---|---|---|
| MODEL_BINDING | **PASS** | the deck's include was re-hashed from the loaded path: `.lib fc8d321752f2bacf…`, `section tt` pulls `…_mis_spe.mdl 4b62b398…` and `…_spe.mdl 5187cae1…`, README `f43d2585…` — all three equal the task book's uploaded digests. Geometry limits per model record with file and line: n18/p18 lmin=1.5e-7 lmax=1e-4 wmin=1.9e-7 (lines 53/258), p33 3e-7/1e-4/2.2e-7 (866), n33 3.5e-7/1e-4/2.2e-7 (654); the frozen sizes (l18=2e-7, l33=4e-7, w 2e-6/4e-6/5e-6/1e-5) sit inside every limit |
| characterisation range vs ratings | **kept separate, `SOA_SIGNOFF: NO`** | the README states `temperature range:-40C~125C` (5 lines), so 27 °C is inside the characterisation range; **no absolute-maximum table exists in the readable files**, so nothing here is an SOA signoff |
| TEMP_CONFIRMATION | **PASS, read back** | `spectre -h options` lists `temp=27 C`, but `options` is a device master here: a bare `options temp=27` is rejected with `SFE-709 No master specified for instance 'options'`, and the accepted form is `simopt options temp=27` (the vendor's own `section tt` writes `setoption1 options gmin=1e-14`). Every calibration run echoes `temp = 27` in the log and `"temp" 27.0000` in the psf header; the S1 logs echo `temp = 27 C` |
| SOURCE_CURRENT_CALIBRATION | **PASS with the sign stated** | 10 kΩ bench, rail driven directly (no series rail iprobe — the audited gate refuses one, and the gate was not relaxed): `V18:i` / `V18:1` = **−180 µA**, `Xcal.Ip1:i` = **+180 µA**, `V33:i` = −330 µA with `Xcal.Ip1:i` = +330 µA, `Xcal.node_mid` = 0 V. The rule used everywhere is **injected = −(Vx:i)**, checked against the independent load-branch iprobe rather than asserted. `V18:current` is ignored (SPECTRE-8059/8287), `save i(V18)` is fatal (SFE-874), and a bare `Ip1:i` inside a subckt is ignored (SPECTRE-8282) — hierarchical names need a **DOT** |
| S1_FRESH_REGRESSION | **PASS (native, new data)** | `results/evidence/sc1_r2e_s1_regression.csv`, 32 rows × 14 cols: 4 truth rows (1.8 V / 5.4e-9 / 6.5e-9 / 1.0e-9 V) with the stimulus read back per label, T1..T5 whole-window contract (T1 `q min=1.76555`, `qbar max=0.00123537`, blank per-sample vs the PWL worst diff 1.93e-14 over 117 samples), and **F1 `DETECTED`** with its bench setup verified (BLANK pin to vss, blank source keeps the PWL, the other T1 checks still pass) |
| S1 historical re-analysis | **still `PARTIAL_NOT_VERIFIED`** | the 9-certified / 1-not-certified local rows are unchanged history; the cloud still has no bytes of the local raws and this round does not retrofit them |
| S2 entry | **NEW, with a real execution path** | `scripts/sc1_r2e_s2_tt.py` imports the audited generator unchanged and adds only the two calibration-verified lines plus the terminal nodes resolved from the frozen cell; it refuses (exit 5) without `RUN=1` **and** `QODER_SIM_AUTHORISED=1`, and a harness exception is recorded per case as `BLOCKED`, never as a circuit verdict |
| S2_FUNCTIONAL_TT | **PASS 6/6** | `results/evidence/sc1_r2e_s2_static.csv` (110 rows). en low → gate33 3.300 V; en high → gate33 4.2e-10 V (C0) / 3.2e-9 V (C1 with core_ok33 high); core_ok33 low → 3.300 V even while the core selects. **The 1.8 V-gated n33 does beat the cross-coupled p33 at TT/27 °C with the frozen sizes**: x=6.85e-10 V, y=3.300 V. Screening low ≤ 0.30 V / high ≥ 3.135 V (POC_ASSUMPTION), judged on whole-window min/max |
| finding in the audited decks | **`SAVE_PATH_AUDIT` = PARTIAL, one row per deck** | the generated save line asks for `Xt.Xcore.x` / `Xt.Xcore.y`, but x/y are the core's **ports**, so this build names them `Xt.x` / `Xt.y` and silently ignores the other spelling (SPECTRE-8281). The R2E deck keeps the reviewed line and adds the resolved names; `scripts/sc1_r2e_s2_selftest.py` (26/26, `sc1_r2e_s2_entry_selftest.csv`) pins that rule |
| S2_REPRESENTATIVE_DYNAMIC | **MEASURED (native)** | `sc1_r2e_s2_dynamic.csv`, `…_dynamic_repeat3.csv`, `…_load.csv`. 1 pF: en↑→gate33↓ 3.053/3.044/3.429 ns (C0 rise/fall, C1), en↓→gate33↑ 2.86/1.94 ns, fall 10–90 % 1.19–2.03 ns, rise 1.85–3.63 ns. 5 pF: delay 7.460 ns, fall 9.893 ns, and the same deck at maxstep 0.05 ns gives 7.479 ns / 9.892 ns (0.3 % / 0.01 %) — the finer-step re-check. repeat3 yields 12 delays, one per input edge, each window closing before the next edge so no cycle can borrow the next response. Rail peaks: vdd18 up to +200.9 µA, vdd33 up to +2.01 mA (1 pF) / +0.90 mA (5 pF) |
| per-device stress | **`MEASURED`, not a signoff** | VGS/VGD/VDS/VGB extremes formed per sample from the saved D/G/S/B nodes (`scripts/sc1_r2e_vtx.py`, 5/5 offline cases; taking each node's extreme separately would pair instants that never coexisted). One device cross-checked against the model's own exported `:vgs`: worst difference 0 V. `SOA_SIGNOFF: NO` |
| real polarity negative | **`EXPECTED_REFUSAL` = detected** | `sc1_r2e_s2_negative.csv`: `neg_output_polarity_fault` was simulated (preflight rc 0, Spectre rc 0, reader rc 0) and the normal C0 criterion refused it (`NO_RESPONSE … no complete fall output event`), while `en(rise)→gate33(rise)` answered with 4.015 ns — the wrong polarity is really present and really refused. The vss-miswire and missing-vdd33 cases stay static-gate refusals |
| guest network | **not touched this round** | no `dhclient`, no ONBOOT/.vmx/service/license/VM-power action: this round's task book does not authorise another lease attempt, and the Tools channel was sufficient. The three earlier exit-1 attempts stay recorded in the R2D2 block below |
| cloud C²MOS result | **`EXTERNAL_CLOUD_REPORT` / user-relayed, wording corrected** | it is a **same-phase-clock** three-stage experiment (not "non-overlapping"), ngspice 42 on the uploaded HSPICE/BSIM4 package, 1.8 V / 27 °C / 50 fF, broken by 1 ns per-stage skew — not native Spectre; the topology stayed unchanged and S4 did not start |
| R2 full acceptance / 37-deck power matrix / R3 / S3 / S4 | **NOT_RUN / NOT_STARTED** | not authorised: no brownout or supply-sequence matrix, no chaining, no corners |
| `core_ok33`, autonomous power-fail | assumed control only; **NOT_IMPLEMENTED** | still a testbench high-domain assumption, not on-chip protection |

### What this round does **not** claim

One corner is not a signoff: every number above is TT / 27 °C / 1.8+3.3 V, all POC_ASSUMPTION, with no
layout, no DRC/LVS/PEX, no absolute-rating table and no power budget. `MEASURED` rows are readings. A
passing calibration, preflight or self-test proves the bench, not the circuit; the circuit statements
are the S1/S2 rows that had a real waveform and a real refusal.

### Next step is a decision, not a continuation

The native TT scope of the authorisation is finished. Stopping at the **native TT results review
gate**: the power-off / supply-sequence matrix, R3 chaining and S3/S4 each need a new authorisation.

## HISTORICAL_STATUS (SCAN-1R2D2 round, kept for audit; superseded by the R2E block above)

> Everything in this block was preparation without a simulator. **SCAN-1R2E ran the simulator**
> and closed the rows it marked `NOT_RUN / PAUSED_BY_USER` (S1 fresh regression, S2 functional TT,
> preflight full, model binding, `temp=` syntax, rail-current sign); read the block above for status.


Updated 2026-10-13 during **SCAN-1R2D2 / S1 window-state criteria closed**. Start point re-read before
editing: remote `poc/scan-driver-1ch` = `c05042779f23151eaa9d5fd83d0c4917269ba36c` = local HEAD; main
= `23e471cb936b421ee97e1250c3be06edf96f9937`. No divergence, no other agent's work touched.
Full write-up: `reports/scan_driver_r2d2_state_contract.md`.

**No simulator was called in this round** -- no Spectre, no ngspice, no preflight full, no
operating-point probe, no Virtuoso, no local C²MOS job, no new-PDK run. `spectre/` and every audited
tool stay byte-identical (`git diff --name-only c050427 HEAD -- spectre/ scripts/sc1_read_psf.py
scripts/sc1_delay.py scripts/tb_preflight.sh scripts/sc1_supply_check.awk scripts/run_spectre.sh
scripts/sc1_s1r.sh scripts/sc1_s2.sh` → 0 lines).

| item | status | evidence |
|---|---|---|
| S1 window-state contract (shared) | **CLOSED, one implementation for both entries** | `scripts/sc1_s1_window_contract.py`: a state must hold **across the whole window** (high → window minimum above 0.9 V, low → window maximum below it); `blank` is compared **sample by sample** with the frozen PWL (1.8 V to 450 n, ramping to 0 by 460 n, nominally 0.9 V at 455 n) with band 0.09 V = half of one 1 ns step of that ramp (`POC_ASSUMPTION`, sources stated in the module); the clock is judged by its **real edges** (≥1 rise in T1, ≥1 rise + ≥1 fall in T2..T5) instead of "high once"; T2 additionally requires `d` high and T4/T5 require `d`/`q` low with `qbar` high. Reader exit codes are recorded as they come (3/4/5, never flattened to 1). The audited reader/delay/preflight/supply checker are untouched |
| A: future S1 regression entry | **COMPLETE as preparation, 23/23 cases** | `scripts/sc1_s1_r2d_regression.sh` now delegates every window to the contract instead of asking only whether a signal could be read. Before: the reviewer set `T2` blank to 1.8 V (T2 is *BLANK=0 while Q=1*) and got `T2_states row_verdict=PASS`, `S1_R2D_REGRESSION: PASS`, rc 0. Now: `T2_state_throughout_blank=FAIL` and the run exits non-zero on the value, not on a reader crash. Also fixed here: the row's reader exit code was hard-coded to 1; the contract's `\r\n` on a Windows host corrupted the next CSV field; a tuple-precedence bug made every clock failure raise `ValueError` and silently drop 25 of 32 rows; the "other failing checks" count picked up the module's own summary line and turned every negative into `FAULT_SETUP_INVALID` |
| C: historical re-analysis | **PARTIAL_NOT_VERIFIED (rc 3): 9 of 10 rows certified, 0 failing** | `scripts/sc1_r2d_s1_reanalysis.py` imports the same contract. Before: the reviewer's mutation (blank = 1.8 V at 410 ns, 0 V at every other sample, decks/history intact) still gave `CERTIFIED rows=10 failing=0` with T1/T3 stimulus PASS. Now that case returns rc 1 and names the PWL mismatch. On the **local** original raws the stricter rules are satisfied: T1 `q min 1.76555 V`, `qbar max 0.00123537 V`, blank matches the PWL over 117 samples (worst diff 1.93e-14), 1 rise / 1 fall; T2 `blank max 0 V`, `d min 1.8 V`; T3 release verified sample by sample over 192 samples; T4/T5 `d`/`q` low with `qbar min 1.79994 V`, 2 rises / 2 falls; F1 `DETECTED` **with** its setup verified (deck ties the gate BLANK pin to vss, blank source still the PWL, Q holds 1 across the window) but `NO_HISTORY` → not certified. `results/evidence/sc1_r2d2_s1_historical_reanalysis.csv` |
| Tests | **23/23 entry, 11/11 lineage, both platforms** | `results/evidence/sc1_r2d2_entry_selftest.csv`, `results/evidence/sc1_r2d2_reanalysis_selftest.csv`: guest Python 2.6.6 / bash 4.1.2 / gawk 3.1.7 and Windows Python 3.12 / bash 5.2.37. New cases: `a_t2_blank_high`, `c_blank_spike_at_410ns`, `c_blank_never_releases`, `c_high_state_dips`, `c_low_state_rises`, `c_clock_stuck_high`; the earlier 18 and 6 are kept, and each case now also rejects `MOCK_MISS` and a harness abort. Entry mocks stay mocks: preflight and the runner are scripted, the data is synthetic PSF-ASCII at 1 ns sampling read by the audited reader |
| S2 (no code change) | counts and PENDING wording corrected | static matrix is 37 rows = **35 at rc 7** (34 ordinary + the deliberately accepted legal-wiring/wrong-polarity case) + **2 at rc 1**. Model binding, `temp=` line syntax and the sign of a rail current summed from `save <inst>:1` all stay `PENDING`; a series rail `iprobe` remains refused by the static gate (measured rc 1 / `supply_contract` / 5 `SUPPLY_FAIL`) |
| Cloud C²MOS result | **EXTERNAL_CLOUD_REPORT / user-relayed, not local** | ngspice 42 `hs`, the cloud's own uploaded HSPICE/BSIM4 4.5 models, golden SHA `d1eed4e242fa...` (same as our `spectre/C2MOS_DFF.scs`), 18 devices unchanged; single stage and non-overlapping three stages pass TT/SS/FF/SNFP/FNSP, the 1 ms hold cases pass, and a 1 ns per-stage clock skew breaks the three-stage chain (reproduced with a finer step and `gear`). Conclusion recorded as theirs: keep single stage, measure inter-stage hold/skew next -- **not** a native-Spectre sign-off, and it started no local run |
| Guest network | **not restored by me; bounded attempts recorded** | read-only: `eth0` UP/LOWER_UP with 0 IPv4 addresses, empty route table, `sshd` running, host `VMnetDHCP` and `VMware NAT Service` Running (VMnet8 192.168.3.1). Then exactly three bounded `dhclient -1 eth0` runs through the VMware Tools channel: exit **1** each time, no lease. `ONBOOT`, VM power, snapshots, `.vmx`, NAT/VMware services, global SSH and license were all left alone; the Tools path (`scripts/push_chunked.sh`, untracked, md5-verified) stayed the transport. Network recovery is **not** simulation authorisation and nothing was inferred from it |
| S1 fresh regression / S2 functional TT / preflight full / C²MOS re-run / new-PDK run | **NOT_RUN / PAUSED_BY_USER** | unchanged, and this round's green offline results do not change that |
| R2 full acceptance / R3 / S3 / S4 | **NOT_COMPLETED / NOT_STARTED** | — |
| Geometry range / `SOA_SIGNOFF` | **NOT_VERIFIED / NO** | no L/W or rating table read from the model |
| `core_ok33`, autonomous power-fail | assumed control only; **NOT_IMPLEMENTED** | best future outcome stays `SAFE_OFF_WITH_ASSUMED_CORE_OK` |

### What this round does **not** claim

The contract is a statement about the recorded waveform matching the label. It is not a circuit
verdict: the local raws being consistent with the historical stimulus does not make S1 a fresh
regression, and the cloud C²MOS numbers are not local data. `PWL_TOL`, the transition counts and the
per-window state lists were derived from the frozen `sc1_s1r.sh` stimulus -- if that stimulus is ever
changed, the contract has to be re-derived, not loosened.

### Next step is a decision, not a continuation

Nothing here authorises a run. Under an explicit pause lift, the first real session should: resolve
`QODER_PDK_LIB` and run the S2 TT decks (measuring the rail-current sum's sign and, if wanted, a
`temp=` line -- both still `PENDING` because they have never been exercised), and run one fresh S1
regression through the entry, whose state contract is now the same one the offline tools use. S3 does
not follow from this round.

## HISTORICAL_STATUS (SCAN-1R2D1 round, kept for audit; superseded by the blocks above)

Updated 2026-10-13 during **SCAN-1R2D1 / test-preparation fixes on the accepted S2 topology**.
Baseline re-read before editing: remote `poc/scan-driver-1ch` = `34d5125a4dfd5c7423776547d6eab4f8fb616fee`
= local HEAD; main = `23e471cb936b421ee97e1250c3be06edf96f9937`. No divergence, no other agent's work
touched.

**No simulator was used in this round** -- no Spectre, no ngspice, no preflight full, no
operating-point probe, no Virtuoso, and the newly supplied PDK was not used for anything. The only gate
run is `PREFLIGHT_STATIC_PROBE=1`. The new S2 cell netlist stays byte-identical to the accepted version
and the audited tools are unchanged (`git diff --name-only 34d5125 HEAD -- <protected>` returns
nothing). Full write-up: `reports/scan_driver_r2d1_test_preparation.md`.

| item | status | evidence |
|---|---|---|
| S2 topology | **STATIC ACCEPTED (unchanged this round)** | `spectre/sc1_level_shifter_r2d.scs` sha `31324ca541a6a645...`; the per-device review stays in `reports/scan_driver_r2d_static_review.md` |
| A: future S1 regression entry | **COMPLETE as preparation, 18/18 mock cases** | `scripts/sc1_s1_r2d_regression.sh`: `-f` checks; reader status returned in this shell and judged before any numeric conversion (the draft's `$(...); rc=$READ_RC` died with `unbound variable`, rc 127); non-zero preflight = `PRECHECK_FAIL` with runner calls **0**; `SIM_FAIL` unless exit 0 **and** exactly one `S1REG_<tag>: PASS` **and** `CHECK error_hits=0` **and** a readable data file (an older raw is never used); truth rows asserted per row with blank/qbar read back at their own labels; stimulus verbatim from `sc1_s1r.sh` (clock `delay=50n rise=1n fall=1n period=100n width=50n`, data/blank PWLs, `stop=900n maxstep=1n method=traponly`), gate-only DC decks, real BLANK-to-vss rewire; rows via `scripts/sc1_csv_writer.py`; PDK bound in this shell (cad_env then git-ignored `spectre/pdk_local.env`), unresolved → BLOCKED before a deck exists. Dry run rc 0, `RUN=1` rc 5, authorised+unresolved rc 7. `results/evidence/sc1_r2d1_entry_selftest.csv`, every row `SYNTHETIC_MOCK_not_a_circuit_regression`, run from a local copy with mocked preflight/runner/reader |
| B: S2 decks and measurement prep | **COMPLETE as preparation: 37 decks / 37 distinct hashes, 64 envelope checks 0 failures, static 37/37 as promised** | `scripts/sc1_s2_r2d_gen.py`. B1 `seq_ok_early_release` rebuilt (vdd33 at 3.3 V from t=0, only the core ramps late) — the old deck drove 3.3 V into a 0 V rail. B2 the three held-`en` decks are labelled `EXTERNAL_DRIVE_FAULT` and each has an `en_follows` twin. B3 `include "${QODER_PDK_LIB}" section=tt` with `DECK_BINDING_PENDING` per row; no `temp=` line invented (`TEMP_LINE_SYNTAX_PENDING`); a series rail `iprobe` was **measured** with the static gate — rc 1, stage `supply_contract`, 5 `SUPPLY_FAIL` lines — so rails stay directly driven and the decks save per-device `save <inst>:1` currents plus every terminal node (sign convention of the sum PENDING). B4 C1 gained `dyn_c1_rise/fall/repeat3` and `load_c1_0/0.2/1/5pF` on the final `gate33`. B5 `load_pF` numeric; `future_verdict=NOT_RUN`; `static_certifies_dynamic_rail_range=no`. Duplicate deck emitted → refused (exit 3). `results/evidence/sc1_r2d1_{deck_index,static_matrix,pwl_audit,iprobe_static_probe}.csv` |
| C: S1 historical re-analysis | **PARTIAL_NOT_VERIFIED (rc 3) — 9 of 10 rows certified, 0 failing; NOT 10/10** | `scripts/sc1_r2d_s1_reanalysis.py` now keeps assertion, stimulus check, traceability and historical difference in separate columns (25), verifies each DC row's own blank/qbar read-back, requires the window's state signals to be readable, never converts a reader exit code into a number, lets the independent awk cross-check participate in the verdict, marks ceiling-reaching sample counts `lower_bound`, and states the tolerance band with its source (history = 6-decimal text, half step 5e-7; reader = 6 significant digits). Local raws reproduce history with diffs 0 … 4.8e-07 V. The one non-certified row is the fault injection: no committed CSV holds a historical value for it. `results/evidence/sc1_r2d1_s1_historical_reanalysis.csv`; synthetic lineage suite `results/evidence/sc1_r2d1_reanalysis_selftest.csv` (6/6: CERTIFIED / wrong_blank FAIL / missing_deck PARTIAL / missing_history PARTIAL + `ASSERTION_CHECK_ONLY` / unreadable_evidence FAIL / no_fault_run PARTIAL) |
| Local vs cloud provenance | **stated separately** | the 10 re-read rows come from raw PSF-ASCII on this machine only (`cadence_work/sc1_sim/sim/`, never committed). Manifest rows for that data and for the instructor PDK carry `cloud_can_verify_bytes=no`; nothing here claims cloud verification of bytes the cloud does not have |
| Protected inputs | **zero diff vs 34d5125** | whole `spectre/`, `scripts/sc1_s1r.sh`, `scripts/sc1_s2.sh`, `scripts/run_spectre.sh`, `sc1_read_psf.py`, `sc1_delay.py`, `tb_preflight.sh`, `sc1_supply_check.awk`; R2D evidence CSVs untouched, this round writes `sc1_r2d1_*` |
| S1 fresh regression, C²MOS re-run, preflight full | **NOT_RUN / PAUSED_BY_USER** | A proves control flow with mocks only |
| S2 functional TT, dynamic, power sequence, stress | **NOT_RUN** | no deck has been run; a static acceptance is not a rail-range statement |
| R2 full acceptance / R3 chaining / S3 / S4 | **NOT_COMPLETED / NOT_STARTED** | — |
| Geometry legality / `SOA_SIGNOFF` | **NOT_VERIFIED / NO** | no L/W range or absolute-rating table read from the model |
| `core_ok33`, autonomous power-fail | assumed control only; **NOT_IMPLEMENTED** | best future outcome stays `SAFE_OFF_WITH_ASSUMED_CORE_OK` |

### Retractions made this round (the blocks below keep their original wording as history)

* "S1 historical re-analysis **PASS 10/10 rows**" in the R2D block is **retracted**. Ten rows re-read
  with plausible values is not a certification: without decks or history the run must report
  PARTIAL / NOT_VERIFIED. The historical waveforms themselves still agree within the stated bands —
  the defect was the verdict, not the data.
* "the decks never drive 3.3 V into a 0 V rail" is **retracted**: `seq_ok_early_release` did exactly
  that. Fixed, and the offline audit now carries a mirrored copy of that waveform as a case it must
  reject.
* `st_c1_enhigh_no_guard` and `rail_18_33` are **retracted as separate cases**: both were
  byte-identical to `st_c1_enhigh_okhigh` (sha `5da1fac7a6fd2732`), so neither was a control.

### Next step is a decision, not a continuation

Nothing here authorises a run. When the owner lifts the pause, the first authorised action is the real
TT verification of the S2 decks with `QODER_PDK_LIB` resolved (static levels, rail currents with a
confirmed sign convention, per-device terminal voltages including `ns_m`, delay/slew per load, both
power-order ramps, backfeed), plus one fresh S1 regression through the new entry. It is **not** S3 and
it does not follow automatically from this round's offline results.

### Bridge state worth recording

Guest SSH was unreachable all round (`vmrun getGuestIPAddress` fails; tcp/22 times out) while the
VMware Tools channel worked, so files moved through an untracked local helper
`scripts/push_chunked.sh` (base64 chunks with md5 read-back verified). No VM, network or license
configuration was changed — bringing the guest interface up needs the owner's approval.

## HISTORICAL_STATUS (SCAN-1R2D round, kept for audit; superseded by the R2D1 block above)

Updated 2026-10-12 during **SCAN-1R2D / S2 static implementation + S1 offline re-analysis**.
Baseline re-read before editing: remote `poc/scan-driver-1ch` = `f7364f5df658cab60e037a1fe1cc65dae2e760cf`
= local HEAD; main = `23e471cb936b421ee97e1250c3be06edf96f9937`. No divergence, no other agent's work
touched.

**No simulator was used in this round** -- no Spectre, no ngspice, no preflight full, no operating-point
probe, no Virtuoso, and the newly supplied PDK was not used for anything. The user's pause on real-circuit
simulation stays in force, so nothing below is a circuit verdict.

| item | status | evidence |
|---|---|---|
| S2 static implementation | **COMPLETE** | `spectre/sc1_level_shifter_r2d.scs`: core `sc1_ls_core_r2d (en x y vdd18 vdd33 vss)` with the six devices of the review table, `sc1_ls_c0_r2d` (two 3.3 V stages, `gate33` keeps `x`'s polarity), `sc1_ls_c1_r2d` (static NAND `gate33=NOT(y AND core_ok33)`, parallel PMOS, series NMOS with the intermediate node `ns_m` named), plus `sc1_ls_c0_top_r2d` / `sc1_ls_c1_top_r2d`. Per-device D/G/S/B + W/L tables in `reports/scan_driver_r2d_static_review.md` |
| Device interfaces | **READ LOCALLY, not assumed** | vendor `inline subckt n33_ckt ( d g s b )` / `p33_ckt ( d g s b )`; bare `n18/p18/n33/p33` are BSIM4 `model` records, so instances here are primitives; the S1 measured truth table is only consistent with that same order, which is derivation from existing data, not a fresh `spectre -h` confirmation. Hashes of the three files read: `results/evidence/sc1_r2d_manifest.csv`, role `pdk_reference_readonly_hash_only` |
| Geometry legality | **NOT_VERIFIED** | `GEOMETRY_RANGE_READ = NO`: no L/W range or absolute-rating table in the readable local model README, so sizes only reuse shapes this PDK already accepted in completed runs (S1 1.8 V gate, 3.3 V device probe, DATA decks). `SOA_SIGNOFF = NO / FOUNDRY_REVIEW_REQUIRED` |
| S2 deck static validation | **PASS 29/29 (static only)** | `bash scripts/sc1_s2_r2d.sh` in the guest: 27 decks accepted at probe rc=7 with `CIRCUIT_VERDICT: NOT_RUN`, and the two intended negatives refused at `PREFLIGHT_STAGE=supply_contract` with reasons (`net vssx (Xt port vss) has no independent source from reference node 0`; missing 3.3 V rail). `simulator_called=no` on every row. `results/evidence/sc1_r2d_static_matrix.csv` |
| Supply gate over the new cell | **PASS with hierarchy resolved** | `sc1_supply_check.awk` (unchanged) reports `top=1 descendants=2 checked=8 internal=0` for both variants: every supply port of the core and of the output network resolves through the parent's port bindings to a declared rail. `neg_output_polarity_fault` is accepted by the static gate on purpose -- its polarity error is a circuit verdict and this round claims no detector caught it |
| S1 historical re-analysis | **PASS 10/10 rows, from the raw waveforms** | `results/evidence/sc1_r2d_s1_historical_reanalysis.csv`: 4 truth rows, 5 transient windows, BLANK-clamped negative (`DETECTED`), each with raw file SHA256, deck SHA256, reader rc, sample count and an independent group-aware awk cross-check; differences vs the historical summary are <= 5e-7 V and are the historical 6-decimal print, not a data change. This is `S1_HISTORICAL_REANALYSIS`, not a fresh regression, and it does not re-prove the golden C2MOS cell |
| Two mistakes in my own first pass | **found and corrected before the numbers above** | T2 was transcribed as `max` although a `>0.9 V` assertion takes the window **minimum** (the historical number 1.799913 is the min; awk confirms min 1.79991344 / max 1.80009894); and the sample-count probe had a bisection upper-bound bug reporting 128 where the window holds 157. The raw data never disagreed with history -- the intermediate script did |
| Future regression entries | **prepared, dry-run by default** | `scripts/sc1_s1_r2d_regression.sh` (reader rc before any `float()`, SI/negative values, no phantom `_t1` net, missing raw/negative/short window exit non-zero instead of being skipped) and `scripts/sc1_s2_r2d.sh`: both need `RUN=1` **and** `QODER_SIM_AUTHORISED=1`; `RUN=1` alone exits 5 and runs nothing, verified in the guest |
| Protected inputs | **zero diff vs f7364f5** | whole `spectre/`, `scripts/sc1_s1r.sh`, `scripts/sc1_s2.sh`, `scripts/run_spectre.sh`, and all audited tools (`sc1_read_psf.py`, `sc1_delay.py`, `tb_preflight.sh`, `sc1_supply_check.awk`); earlier evidence CSVs untouched, and `sc1_r2d_*` is the new naming |
| Gates | **PASS** | staged-object safety gate per commit, `provenance_check.py`, `netlist_stats.py` `DEVICE_COUNT_CHECK: PASS`, no PDK/model-card/raw-PSF/credential/vendor path committed |
| S1 fresh regression, C2MOS re-run, preflight full | **NOT_RUN / PAUSED_BY_USER** | `results/evidence/sc1_r2c_full_status.txt` still stands for the tool side; nothing here changes it |
| S2 functional TT, dynamic, power sequence, stress | **NOT_RUN** | decks exist with planned windows; no measurement, no assertion outcome |
| R2 full acceptance / R3 chaining / S3 / S4 | **NOT_COMPLETED / NOT_STARTED** | — |
| `core_ok33`, autonomous power-fail | assumed control only; **NOT_IMPLEMENTED** | best future outcome stays `SAFE_OFF_WITH_ASSUMED_CORE_OK` |

### Next step is a decision, not a continuation

The authorised next action is the real-PDK TT verification of exactly the decks listed in
`reports/scan_driver_r2d_static_review.md` §6 (static levels, rail currents with a calibrated sign
convention, per-device terminal voltages including `ns_m`, delay/slew per load, both power-order ramps
and backfeed). It is **not** S3, and it does not follow automatically from this round's green offline
results.

### Open questions worth the reviewer's judgement

* Core device sizing: equal W on the p33 pull-ups and n33 pull-downs is a starting point taken from
  precedent, not from analysis. The competition question (can 1.8 V on a 3.3 V-threshold n33 gate flip
  the cross couple at all, and which way does it fail if not) is the first thing to measure.
* Whether `C1` should ever carry an output buffer, and if so whether the extra two stages change the
  select polarity budget, is deliberately left unimplemented until a measured load case demands it.
* The primitive terminal-order question is inert for these connections only because bulk is tied to
  each device's own source rail everywhere except the C1 stack's intentional well tie. If any future
  deck separates S from B elsewhere, confirm the order with `spectre -h mos` first.


## HISTORICAL_STATUS (SCAN-1R2C round, kept for audit; superseded by the R2D block above)

Updated 2026-10-12 during **SCAN-1R2C / tool rework only**. Identity re-read before editing:
remote `poc/scan-driver-1ch` = `9159a3970f67d8e30e9a4d4a2cc88cd59bbee43c` = local HEAD (via
`git ls-remote`), main = `23e471cb936b421ee97e1250c3be06edf96f9937`. No divergence, nothing of anyone
else was touched.

**No simulator was called in this round**: no Spectre, no preflight full, no operating-point probe,
no Virtuoso, and the newly supplied PDK was not used. Allowed validation was offline synthetic
waveforms, the static supply preflight, CSV read-back and repository safety gates. The overall tooling
audit is **PENDING_REVIEW / REWORK** until the reviewer re-reads this round on the remote.

### Problem A: the attribution bound was still not the input's own 50 % crossings

| what 9159a39 did | what the code now does |
|---|---|
| `bounds` came from complete 10-90 % events, so an input that dipped to 0.4 V (above the 10 % level = 0.18 V) and came back produced **no bound at all**: a1 authenticated `t_in=2.5e-09 t_out=1.45e-08 delay_ns=12.000 MEASUREMENT_VALID=YES` rc=0 | the bound is the next crossing of the input's **own 50 % level in either direction**, scanned straight off the waveform: `t_next=5.642857 ns`, and a1 now answers `OUTSIDE_ATTRIBUTION ... candidate t_out=1.450000e-08 (candidate_delay_ns=12.000) is not inside [t_in=2.500000e-09, t_next=5.642857e-09)` with rc=4, `MEASUREMENT_VALID=NO` |
| the candidate filter tested the output event's **start**, never the 50 % point it then reported: a2 printed its own window ending at 5.1 ns while reporting `t_out=8.125 ns` as valid | the candidate is selected and validated by the reported 50 % point: a2 refuses with rc=4, and the boundary race (output 50 % **exactly** on `t_next`) also refuses -- `t_in <= t_out < t_next` strictly |
| mirrored polarities had the same hole | a1_mirror / a2_mirror refuse with the same numbers (t_in=2.5 ns / 1.5 ns, t_next=5.642857 ns / 5.5 ns) |
| -- | positives still measure: a dip that never reaches the input's 50 % level (plateau 1.2 V) leaves event 1 measurable at `delay_ns=12.000` rc=0 YES; a complete response measured at 10.125 ns against a 12.5 ns bound gives `delay_ns=8.625` rc=0 YES; `--in-event second` on the R2B deck still gives 12.5 / 14.5 / 2.000 ns; `--pairing diagnose` still shows the 12 ns candidate but with rc=6 and `MEASUREMENT_VALID=NO` |
| every refusal path | now prints `MEASUREMENT_VALID=NO`, and only a certified line prints `delay_ns=` (a refusal prints `candidate_delay_ns=`), so a reader cannot mistake a borrowed candidate for a measurement |

Semantics fixed for this round: attribution failure = `OUTSIDE_ATTRIBUTION` **rc 4**; no output event
at all = `NO_RESPONSE` rc 4; unorderable sampling = `AMBIGUOUS_RESOLUTION` rc 6; polarity beaten by an
earlier opposite event = `AMBIGUOUS_POLARITY` rc 6; `--pairing diagnose` = rc 6. No fixed ns cap, no
column period, no window-widening switch was added.

### Problem B (the reviewer's second hole): the preflight log was written asynchronously

* **Cause confirmed by fault injection, not asserted.** `scripts/sc1_r2c_lograce.sh` builds two
  variants from a copy of the committed wrapper with the SAME deliberately slow log writer, and reads
  the report file and the caller's capture immediately after each return: guest bash 4.1.2 → async
  writer lost **12/12** reads, committed wrapper lost **0/12**; Windows bash 5.x → **10/12** vs
  **0/12**; exit status stayed 7 (static probe) in both. Nothing here called a simulator, and the
  committed wrapper was never modified to produce the failure.
* **My first fix attempt was wrong and is recorded**: `TEE_PID=$!` + `wait` after
  `exec > >(tee ...)` passed 8/8 on Windows bash 5.2 but failed 8/8 on the guest, because bash 4.1
  does not set `$!` for a process substitution at all -- the "synchronisation" was a no-op there. The
  mechanism was therefore replaced, not patched: the wrapper now writes its report from its own
  process and echoes it to the saved stdout on exit, which is version independent.
* The matrix harness also refuses to classify an incomplete log: a row whose log has no final
  `TESTBENCH_PREFLIGHT:` line is `HARNESS_ERROR log_incomplete_no_final_verdict_line`, never a circuit
  verdict and never a silent stage-less read.
* Supply verdicts, exit codes and the static-stage rules are unchanged.

### Gate status

| item | status | evidence |
|---|---|---|
| EVENT_ATTRIBUTION_VALIDATION | **PASS 11/11** | `results/evidence/sc1_r2c_checker.csv` (guest Python 2.6, label `fixed_r2c_guest_py26`), same 11/11 on Windows Python 3.12; decks are reproducible with `scripts/sc1_r2c_casegen.py` |
| baseline behaviour before the fix | **6 of 11 rows failed at 9159a39** (5 authenticated with rc=0/YES, 1 refused without a validity flag) | `results/evidence/sc1_r2c_before.csv` |
| CHECKER_REGRESSION | **PASS** | 16/16 R2B (`sc1_r2c_checker_r2b_subset.csv`), 48/48 R2A (`sc1_r2c_checker_r2a_subset.csv`), 27/27 legacy -- all re-run on the guest; one R2B row's reason token moved from `NO_RESPONSE` to `OUTSIDE_ATTRIBUTION` because R2C refined the diagnosis, with `PROPDELAY` / `MEASUREMENT_VALID=YES` still forbidden |
| SUPPLY_STATIC_REGRESSION | **PASS 33/33** | `results/evidence/sc1_r2c_preflight_static.csv` + transcript; composition 8 acceptance + 13 circuit negatives + 10 tool faults + 2 harness = 33, and `simulator_called=no` on **all** 33 rows (the 8 acceptance rows stop at the static probe, rc=7, `CIRCUIT_VERDICT: NOT_RUN`). Earlier wording that implied the acceptance rows called the simulator is corrected in `sc1_r2b_full_status.txt` |
| CSV_AUDIT | **PASS** | `scripts/sc1_csv_audit.py` over the 33-row matrix, recomputing every verdict from the recorded logs |
| LOG_COMPLETION_VALIDATION | **PASS** | `results/evidence/sc1_r2c_lograce_guest.transcript.txt` (bash 4.1.2) and the Windows run quoted above |
| full preflight / C2MOS / S1 regression | **NOT_RUN_AFTER_R2C / PAUSED_BY_USER** | `results/evidence/sc1_r2c_full_status.txt`; b603820's full 31/31 and 9159a39-era static numbers are history only and are not claimed for this code |
| protected inputs | zero diff vs 9159a39 | `spectre/` whole tree, `sc1_s1r.sh`, `sc1_s2.sh`, `run_spectre.sh`, `sc1_supply_check.awk` (deliberately untouched this round), frozen DATA assets, and every earlier evidence CSV; hashes in `results/evidence/sc1_r2c_manifest.csv` |
| R2 / R3 / S3 / S4, SOA, autonomous power-fail | NOT_STARTED / NO / NOT_IMPLEMENTED | unchanged |

### Reproduce offline

```
python scripts/sc1_r2c_casegen.py --outdir DECKS
python scripts/sc1_r2c_selftest.py --decks DECKS --out results/evidence/sc1_r2c_checker.csv --version-label L
python scripts/sc1_r2b_selftest.py; python scripts/sc1_r2a_selftest.py; python scripts/sc1_checker_selftest.py
PROJ=/path/to/checkout bash scripts/sc1_r2c_lograce.sh 10 0.05
PROJ=/path/to/checkout bash scripts/sc1_preflight_selftest.sh static
```

### Still open for the reviewer

* The attribution rule uses the input's own next 50 % crossing as the bound. A deliberately
  multi-cycle response (real power-gating chains may answer later than one input change) is therefore
  refused rather than measured; if such a case is wanted, it needs a caller-supplied event pairing,
  not a widened window. Nothing was relaxed for that purpose in this round.
* Whether an exact-threshold plateau should count as one crossing (current, conservative rule) or as
  two is a judgement; the current choice creates a bound, which can only ever refuse.
* The old async `tee` behaviour is reproduced only with an injected slow writer; on a quiet machine the
  race may not appear, which the lograce script reports as INCONCLUSIVE rather than as a pass.
* Full-mode regression, C2MOS and S1 real-circuit re-reads remain paused by the user.


## HISTORICAL_STATUS (SCAN-1R2B round, kept for audit; superseded by the R2C block above)

Updated 2026-10-12 during **SCAN-1R2B / only-tool-repair**. Inputs re-read this session: branch
`poc/scan-driver-1ch` head `b60382099d369801c93d8e5f06adf2071a079eab` (the round's start, reviewed by
the cloud reviewer), earlier starts `5c8b8a7…` (first R2B counterexamples) and `41ffbf2…` (R2A),
main @ `23e471cb936b421ee97e1250c3be06edf96f9937`.

The overall tooling audit stays **REWORK** until the reviewer re-reads this round's remote evidence.
R2, R3, S3, S4 are not started. No simulator was called in this round.

### The two functional holes, with the numbers that close them

| hole | b603820 behaviour (reproduced locally before touching code) | R2B behaviour |
|---|---|---|
| **A. propdelay borrowed the next cycle's response** | the reviewer's deck gave `t_in=2.5e-09 t_out=1.45e-08 delay_ns=12.000 in_ev=2 out_ev=1 earlier_opposite_event=no` with **rc 0**: the first, unanswered pulse was credited with the second cycle's fall | default (event 1) is now `NO_RESPONSE … no complete fall output event before the next input change at 5.1e-09` **rc 4**; with `--in-event second` the real measurement is `t_in=1.250e-08 t_out=1.450e-08 delay_ns=2.000 MEASUREMENT_VALID=YES` **rc 0**; `--pairing diagnose` still prints the 12.000 ns pairing but with `MEASUREMENT_VALID=NO` **rc 6** |
| **B. an uncertified internal supply passed the gate** | the reviewer's deck printed `SUPPLY_INTERNAL … internal=1` and then `SUPPLY_RESULT PASS` with **rc 0**; the wrapper only emitted a scope note and the static probe exited 7 as if accepted | same deck now prints `SUPPLY_NOT_CERTIFIED X1.Xchild port vss is internal node @top.floating_ground` plus `SUPPLY_FAIL … is not certified: it maps to internal node … instead of a rail the contract covers`, `SUPPLY_RESULT FAIL`, **rc 1**; through the wrapper it is refused at `PREFLIGHT_STAGE=supply_contract` (matrix row n13) with `simulator_called=no` |

Attribution rule that replaced the "any later event" pairing: an output event may only be credited to
the selected input event while **no further input crossing of either direction** has begun -- the bound
comes from the input waveform itself, never from a fixed ns cap or from the 9.765625 us column period.
A missing 50 % crossing is `NO_HALF_CROSSING` (rc 4) instead of quoting the 10 % point, and a deck whose
sampling is too coarse to order the two edges is `AMBIGUOUS_RESOLUTION` (rc 6, `MEASUREMENT_VALID=NO`)
rather than `NO_RESPONSE`, which would have misdiagnosed an unresolvable measurement as an unanswered
input. Node 0 is now never treated as a subckt-local name, so a child reference tied straight to the
reference node is certified as the legal 0 V it is.

### Status of every gate this round touched

| item | status | evidence |
|---|---|---|
| R2B targeted regressions | **PASS 16/16 (8 regression)** | `results/evidence/sc1_r2b_checker.csv`; both reviewer decks, event selection, diagnose mode, 50 % vs 10 % reference, coarse-sampling ambiguity, two answered cycles, two-level hierarchy, internal vdd, node-0 child reference |
| R2A suite after the corrected semantics | **PASS 48/48 (21 regression)** | `results/evidence/sc1_r2b_checker_r2a_subset.csv`; three expectations changed by acceptance-semantic decision, not by loosening the tool: `r0b_same_dir_on_inverting_marked` → `…_refused` (rc 6), `r0b_missing_response` → `NO_RESPONSE` token, `r1b_internal_supply_reported` → `r1b_internal_supply_refused` (rc 1); `r0b_window_selects_event` renamed to `r0b_window_excludes_the_only_event` because its deck holds a single input event and never tested selection |
| Legacy measurement suite | **PASS 27/27** | `results/evidence/sc1_r2b_legacy27.csv` (guest Python 2.6) |
| Preflight matrix, static mode | **PASS 33/33** | `results/evidence/sc1_r2b_preflight_static.csv` + transcript: 8 acceptance + 13 circuit negatives + 10 tool faults + 2 harness = 33; no row reached the simulator except the acceptance rows probed with `PREFLIGHT_STATIC_PROBE=1` (rc 7, `CIRCUIT_VERDICT: NOT_RUN`) |
| CSV read-back audit | **PASS** | `scripts/sc1_csv_audit.py` recomputes every verdict from the recorded logs; 33 rows × 16 columns, unique ids |
| Preflight matrix, full mode (real PDK) | **NOT_RUN_AFTER_R2B / PAUSED_BY_USER** | `results/evidence/sc1_r2b_full_status.txt`. The b603820 full 31/31 result is kept as `sc1_r2a_preflight.csv` and describes the OLD tools; it is not claimed for this code |
| Count correction to the previous block | 31 = 7 + 12 + 10 + 2, so **24** rows were refusals/harness, not 22 | the sentence in the R2A block below was wrong and is marked |
| Protected inputs | untouched | `spectre/C2MOS_DFF.scs`, `sc1_scan_gate.scs`, `sc1_level_shifter.scs`, `scripts/sc1_s1r.sh`, `scripts/sc1_s2.sh`, `scripts/run_spectre.sh` unchanged; hashes and the fact that the old evidence CSVs were not overwritten are in `results/evidence/sc1_r2b_manifest.csv` |
| Safety / provenance | PASS | staged-object gate on every commit, `provenance_check.py`, `repo_safety_scan.py`; no PDK, model card, raw PSF, credential or vendor path committed |

### Offline reproduction, exactly as the reviewer would run it

```
python scripts/sc1_r2b_selftest.py --out results/evidence/sc1_r2b_checker.csv      # 16 cases
python scripts/sc1_r2a_selftest.py --out results/evidence/sc1_r2b_checker_r2a_subset.csv
python scripts/sc1_checker_selftest.py --out results/evidence/sc1_r2b_legacy27.csv
PROJ=/path/to/checkout bash scripts/sc1_preflight_selftest.sh static               # 33 cases
```
No simulator, no PDK, no licence. Interfaces added this round (documented in each tool's usage):
`--in-event first|second|N`, `--pairing accept|diagnose`, exit code 6 = diagnostic/ambiguous,
`MEASUREMENT_VALID=YES|NO` on every propdelay line, `SUPPLY_NOT_CERTIFIED` from the awk checker.

### Open for the reviewer / still unverified

* The full-mode matrix on this implementation (needs the teacher PDK; explicitly paused by the user).
* S1 real-circuit regression with the corrected tools: NOT_RUN. Nothing in this round judges any circuit.
* Whether the attribution bound should also be able to take an explicit response-window argument from
  the caller; the current rule uses the input's own next crossing, which is the strictest reading.
* R2 / R3 / S3 / S4 NOT_STARTED, `SOA_SIGNOFF: NO`, autonomous power-fail protection NOT_IMPLEMENTED.


## HISTORICAL_STATUS (SCAN-1R2A round, kept for audit; superseded by the R2B block above)

Updated 2026-10-12 during **SCAN-1R2A / R0-R1 tool rework**. Inputs re-read this session:
`poc/scan-driver-1ch` @ `41ffbf29673de15acf0fdc491f7daa7d113ddc88` (review start), circuit baseline
`fc6757bda8b410ebf34e4bbcf248eaa2a98a19b6`, main @ `23e471cb936b421ee97e1250c3be06edf96f9937`.

**The previous round's `27/27` and `11/11` are historical test-set results, not the overall verdict.**
The cloud review of `41ffbf2` returned REWORK for R0/R1; this round closes the named defects. Until
the reviewer re-reads the new remote evidence, the overall audit status of the tooling stays REWORK.

| item | status | evidence |
|---|---|---|
| R0-A edge splicing | **FIXED, proven offline** | `results/evidence/sc1_r2a_checker.csv` cases `r0a_*`; reviewer waveform (0,1,0,0,3.3,3.3 V) now gives NO_EDGE for `first_attempt` and 0.800 ns for `first_complete`, never 3.570 ns |
| R0-B inverting propdelay | **FIXED, proven offline** | `r0b_inverting_2ns` asserts t_in=2.500 ns, t_out=4.500 ns, delay 2.000 ns via `--edge-in/--edge-out`; `r0b_inverting_fall_to_rise_2ns` covers the other direction (t_in=4.500, t_out=6.500); `r0b_same_dir_on_inverting_marked` returns 6.000 ns **plus** `earlier_opposite_event=YES`; missing response and out-of-window input are `NO_EDGE`; legacy single-`--edge` interface still same-direction (`r0b_legacy_single_edge_same_phase`) |
| R0-C reader/delay contracts | **FIXED, proven offline** | `r0c_*`: `--require-n` enforced for window, sweep and whole file; unordered/duplicate time axis refused (`BAD_AXIS`); two-sample edge interpolates 0.2424->0.800 ns instead of crashing; unknown mode/edge and illegal K are `BAD_USAGE`; reversed window (`t0>t1`) and non-finite / overflowing / unit-suffixed rail voltage (`nan`, `1e400`, `3V3`) are `BAD_NUMERIC` rc 5 on both tools, never a silent fallback |
| R1-A checker fault = refusal | **FIXED, proven with local checker copies** | matrix `t01..t10`: awk syntax error, empty stdout, PASS-then-exit-3, missing/duplicate result token, `checked=0`, count mismatch, internal-count mismatch, PASS-with-FAIL detail, garbled report -- all refused at `PREFLIGHT_STAGE=supply_contract` **before** any Spectre call; the committed checker was never modified |
| R1-B supply semantics | **FIXED** | unresolved master, non-numeric contract value, zero instances, unmatched entry all refused; node 0 accepted as the 0 V reference; hierarchy resolved through port bindings (`descendants=2` counted); per-master entries let core-domain and high-domain instances coexist; rail-tie contradictions refused; subckt-local net with a global rail's name is refused, not guessed |
| R1-C negative-case protocol | **FIXED** | `scripts/sc1_preflight_selftest.sh` declares per case an expected rc **set**, rejection stage, required reason tokens (all must appear), the connection actually changed, and whether the simulator may be reached; missing deck/checker are `HARNESS_ERROR` rc 8; a positive whose simulator phase produced no data is BLOCKED, never PASS |
| Preflight matrix (offline static mode) | **PASS 31/31** | `results/evidence/sc1_r2a_preflight_static.transcript.txt`; no simulator involved |
| Preflight matrix (real PDK, full mode) | **PASS 31/31** | `results/evidence/sc1_r2a_preflight.csv` + `..._full.transcript.txt`; 7 acceptance cases ran the operating-point probe on the teacher PDK `section=tt` with `sim=yes`, 24 refusals/harness rows never called Spectre (the count in this round's review was mis-stated as 22: 31 = 7 acceptance + 12 circuit negative + 10 tool fault + 2 harness) |
| CSV read-back audit | **PASS** | `scripts/sc1_csv_audit.py` on the matrix: 16 columns per record, unique case ids, rc/stage/reason correspondence, verdict recomputed from the recorded logs |
| Legacy 27-case suite | **PASS 27/27** (guest Python 2.6) | `results/evidence/sc1_r2a_legacy27.csv`; two misleading names corrected -- `delay_propdelay_10ns` asserted 5 ns (renamed to the same-phase case) and `delay_partial_then_full` contains no second transition at all (renamed `delay_partial_only_holds_low`; the real double-event counterexample is `r0a_splice_first_complete`) |
| `psf_check` 9 cases / `safety_rules` 21 cases | **PASS on Python 3** (Windows + cloud reviewer) | these two suites use `open(..., encoding=)` and cannot run under the guest's Python 2.6 -- recorded as NOT_RUN on the guest, not as a pass there |
| R2 new S2 circuit | **NOT STARTED** (out of scope this round) | — |
| R3 real-circuit regression | **NOT STARTED** (out of scope this round) | S1 truth table / transient windows have **not** been re-read with the fixed tools; the old `s1r_*.csv` are prior-round evidence only |
| S3 / S4, Layout, DRC/LVS/PEX | NOT STARTED, out of scope | — |
| Golden DFF, S1 NOR, old S2 deck/scripts, frozen DATA | untouched | hashes in `results/evidence/sc1_r2a_manifest.csv` (`protected_netlist` rows) |

### Corrections to statements made in the previous round

* The supply map is the **4th positional argument** (`bash scripts/tb_preflight.sh NET 1.8 TAG "vdd18=1.8
  vdd33=3.3 vss=0"`, or `SUPPLY_MAP`), not a 5th one; the text below that says "5th call form" is wrong
  and superseded.
* `SUPPLY_RESULT PASS` alone was not sufficient evidence: the wrapper now also requires the checker's
  exit status, a well-formed and unique result token, a non-empty supply list and matching counts.
* Phase 1 (static parse) previously ran, then the script went on to call Spectre and only failed at the
  very end. Static refusal now happens before any simulator invocation, and `PREFLIGHT_STAGE` names the
  stage that refused.
* Phase 1's per-instance `vdd`/`vss` name checks are superseded (not deleted) when a contract is
  present: they demanded a port literally named `vdd`, which a dual-rail deck legitimately lacks. The
  legacy no-contract path is unchanged and still refuses the project's floating-vss bench.
* `V(0,n) dc=-1.8` puts the rail at **+1.8 V**. The checker now resolves source orientation with a
  sign; a test of mine that asserted the opposite was wrong and is replaced by two cases: terminals
  swapped with the sign kept (legal) and terminals swapped without it (rail at -1.8 V, refused).
* Comparing two declared rails needs a tolerance: `3.3 - 1.8` is not bit-exactly `1.5` in IEEE double,
  which made a legitimate 1.5 V tie source look like a contradiction.
* A subckt-local supply node that no preflight can certify is reported as `SUPPLY_INTERNAL` and counted
  (`internal=N`), and the wrapper prints `PREFLIGHT_SCOPE_NOTE`. It is not silently treated as checked,
  and if its name collides with a top-level rail the deck is refused instead of guessed.
* New offline-only entry point: `PREFLIGHT_STATIC_PROBE=1` stops after the static gates and exits **7**
  with `CIRCUIT_VERDICT: NOT_RUN`, so static-mode evidence can never be read as a circuit PASS.
* `SUPPLY_CHECK_AWK` exists so tests can point at a broken local copy of the checker; the committed
  checker is never edited to prove the gate closes.

### The previous round's 11 matrix cases are all still present, under new ids

`c01 -> p01` (legacy single-rail accepts), `c02 -> n12` (the committed floating-vss bench is still
refused), `c03 -> p02` (correct 1.8/3.3 dual supply), `c04 -> n01` (rail with no source),
`c05 -> n02` (wrong rail value), `c06 -> n03` (pins swapped), `c07 -> n04` (reference lifted),
`c08 -> p05` and `c09 -> p06` (declared 0 V power-down is a legal condition), `c10 -> n08` (a real
extra source shorting two declared rails), `c11a -> n09` (contract omits a port the cell exposes).
New rows extend the matrix to zero instances (n05), unknown instance master (n06), illegal contract
value (n07), reference node 0 (p04), hierarchical buffer with descendants audited (p03), mixed core
and high-domain instances through per-master entries (p07), local net with a global rail's name
(n11), ten checker fault-injection cases (t01..t10) and two harness-error cases (h01, h02). No case
was dropped to keep the suite green, and no expectation was loosened to accept a wrong circuit.

### Reproducing this round offline (no PDK, no licence)

```
python scripts/sc1_r2a_selftest.py --out results/evidence/sc1_r2a_checker.csv   # 48 cases
python scripts/sc1_checker_selftest.py --out results/evidence/sc1_r2a_legacy27.csv
PROJ=/path/to/checkout bash scripts/sc1_preflight_selftest.sh static            # 31 cases, rc 0
```
`static` mode exercises every refusal and the static gate of each acceptance deck; the same command with
`full` additionally runs the operating-point probe. On the guest, Python 2.6 and gawk 3.1.7 are the
versions actually used; gawk 3.1.7 exits **1** (not 2) on an awk syntax error, which is why t01 declares
an allowed exit-code set `1,2` and requires the reason token `checker_exit=` plus the text `syntax error`.

### Not verified by me, and left open for the reviewer

* Cloud-side re-run of the 48 + 27 suites and of `static` mode (needs bash + awk + Python only).
* Whether the S1 truth-table / transient-window numbers still hold when re-read with the fixed reader
  and delay tool -- that is R3, explicitly not started here.
* Any S2 circuit behaviour: nothing in this round judges a circuit; `R2` is NOT_STARTED and the old
  `scripts/sc1_s2.sh` remains defective and unrun.

### (history, SCAN-1R2 round, superseded by the block above) R0 in one line each


Reader and delay tool were rewritten against the specific defects the review reproduced, and are
now proven **offline** so a DUT simulation is never the evidence that the measuring tool works:

* group-wise parsing: `VALUE` is read as groups that each start with the axis, so a signal can no
  longer slide against `time` (the old parser dropped unparsable rows and returned 0 V for a window
  whose real max was 1.8 V, rc=0).
* NaN/Inf/illegal tokens are hard failures (`rc 5`), verified on both Windows Python and guest
  Python 2.6; a series 0, NaN, 0 can no longer report window max 0 with rc 0.
* truncation / ragged groups / value-before-axis are distinct non-zero exits (7 / 8).
* output is 6 **significant** digits, so a nanoampere is not printed as `0.000000`.
* `qty()` now accepts scientific notation (`1e-6`, `2.5E-12`), which the old regex rejected while
  its own docstring claimed support.
* edge measurement is directional and window-scoped: a fall cannot borrow the end of the preceding
  rise; `steady` requires an explicit window and reports min/max/mean over it instead of using the
  waveform extremum as "settled"; `propdelay` measures input-50% to output-50% for one event.
* tools are pure ASCII with a PEP 263 declaration: the guest's Python 2.6 refused a `µ` character
  in a source comment, which would have broken every guest-side measurement.

Compatibility confirmed: `test_safety_rules.py` and `test_psf_check.py` still pass, and the
rewritten reader reproduces the previously audited S1 numbers exactly (T1 worst case 0.0753447 V;
en rise 0.774 ns, fall 0.058 ns).

## Historical sections (kept; superseded parts marked)


Purpose: survive context compaction. Every fact below was measured in this session; nothing here is
carried over from a previous task's memory without a re-read. Updated at the end of each stage.

## Stage status

| stage | state | artifact |
|---|---|---|
| S0 read-only inventory | **COMPLETE** | this file, `cadence_work/sc1_sim/pdk_smoke.csv` |
| S1 1.8 V BLANK/ENABLE logic | **native TT regression PASS (one corner; SOA=NO)** | `results/evidence/sc1_r2e_s1_regression.csv`, `spectre/sc1_scan_gate.scs` |
| S2 level shifter + buffer | **TT function PASS 6/6, dynamics MEASURED; supply matrix/corners NOT_RUN** | `results/evidence/sc1_r2e_s2_static.csv`, `..._dynamic.csv`, `..._load.csv`, `..._negative.csv` |
| S3 high-side power switch | NOT_STARTED | — |
| S4 channel + chain + corners | NOT_STARTED | — |

## S1 detail (what is actually proven, and what is not)

Topology chosen: `SCAN_EN = Q AND NOT BLANK == NOR(qbar, BLANK)` -- 4 transistors instead of
NAND+inverter (8), because the golden C^2MOS subckt already publishes the complement on its `qbar`
port, so a NOR of (qbar, BLANK) is non-inverting with respect to Q. De Morgan step is written in the
cell header.

**MEASURED AND PASSED (4/4 rows, real DC sweep through `run_spectre.sh`, section=tt):**

```
Q=1 BLANK=0 -> en HIGH   PASS      (select allowed)
Q=0 BLANK=0 -> en LOW    PASS      (no select without data)
Q=1 BLANK=1 -> en LOW    PASS      (BLANK dominates an stored 1)
Q=0 BLANK=1 -> en LOW    PASS
```

**NOT YET PROVEN (do not carry these forward as PASS):**

1. `SCAN_DIGITAL_BLANK` via the real DFF: 0/4 windows. Cause is the testbench, not the gate --
   `tb_preflight.sh` refused the deck with `SFE-874` and "operating-point probe produced no data",
   so no transient ran. Still to establish: that a rising clock edge moves the select state, and
   that BLANK falls without disturbing `q`. The deck uses `pwl`/`pulse` sources and a `parameters`
   symbol referenced from a `pulse()` high= argument, which is a plausible trigger for the read-in
   failure and is the next thing to bisect (replace `high=VDDV` with a literal).
2. The mandatory fault injection was **wrong by construction** and is redesigned, not passed. My
   first attempt swapped the gate's two input nets, but NOR is symmetric, so swapping its inputs
   cannot change the function -- the "fault" was a no-op and proved nothing about the checker. The
   replacement (holding the gate's BLANK pin low while the bench asserts BLANK=1, i.e. an inverted
   strap) currently produces no psf data and its own read-in error, so `CHECKER_CAN_FAIL` is
   **UNVERIFIED**. Until injection works, the 4/4 truth table should be read as "matches my
   expectations", not "the harness can detect a wrong circuit".
3. `en=` value extraction in `sc1_s1.sh` prints the threshold text instead of the voltage (the
   `tr`/`grep -A1` pickup is wrong), so `s1_truth.csv` carries `want>0.9` in the en_V column. The
   verdicts come from `run_spectre.sh` itself and are unaffected, but the CSV is cosmetically wrong
   and must be fixed before it is quoted as evidence.

My own S1 scripting faults, recorded: an unterminated single quote (`cut -d' |` instead of
`cut -d' '`) which produced a misleading "unexpected EOF looking for )" at EOF; a `$'` sequence that
bash read as ANSI-C quoting; `//` used as if it were a bash comment; and a DC deck with no analysis
statement (hence no psf). None of these are PDK facts; all were harness bugs. Symptom worth
remembering: when a whole family fails identically, including a known-good member, suspect the
harness.


## Git / input identity (re-read, not assumed)

```
BASE_SHA       = 23e471cb936b421ee97e1250c3be06edf96f9937  (main, the approved C2MOS+DATA merge)
REVIEW_BRANCH  = poc/scan-driver-1ch  (created FROM main, per S0.1; NOT from the GUI feature branch)
golden C2MOS   = spectre/C2MOS_DFF.scs   sha256-prefix d1eed4e242fa2874   (4754 B, 18 MOS)
frozen DATA    = reports/data_driver_E_dnw_mpass.md  d749de158b84777f
                 reports/data_driver_1ch_frozen.md   9d0a0b2adbedcbab
tooling on main: tb_preflight.sh psf_check.awk precommit_safety_check.py repo_safety_rules.py
                 ddrv_run/gen/tran/xtalk.py netlist_stats.py provenance_check.py  -> all present
NOT on main    : scripts/git_push_reliable.ps1 (lives on feature/data-driver-virtuoso-schematic,
                 verified in NET-1). It will be located read-only from that branch when pushing,
                 not blind-copied, per task book section 6.
```

## STATUS CONFLICT FOUND (must be reported, not silently worked around)

Two remote branches exist that no prior report of mine created:

```
gexing321/docs/collaborator-rules          876c198...
gexing321/scan-driver/c2mos-schematic      411ac27...
```

`gexing321/scan-driver/c2mos-schematic` is built **directly on top of my GUI-2 HEAD 51ca02a** and
adds 8 commits (33 files, +3904/-1): a rebuilt C2MOS scan-driver schematic, a `c2mos_dff_tb` cell
built from the golden deck, Spectre verification of that schematic against the golden netlist, and a
desktop-shortcut delivery. Consequences for this task:

* `spectre/C2MOS_DFF.scs` is **unchanged** on their branch (diff empty) -- the golden is still shared.
* They already work in the `scan_` namespace (`scripts/scan_c2mos_tb_verify.sh`,
  `results/scan_c2mos_device_parameters.csv`). To avoid a collision on a future merge, **SCAN-1 uses
  the `sc1_` / `scan1_` prefix** for all new files.
* The task book's S0.1 warning not to base this on the GUI branch is satisfied: my branch starts at
  `main`, which is an ancestor of their branch. **No merge, no cherry-pick of their commits.**
* Whether their C2MOS schematic work should replace or precede this scan-driver POC is a reviewer
  decision, flagged here rather than resolved.

## Environment recovery actually performed

The guest had rebooted (uptime 56 min) and, because `ifcfg-eth0` keeps `ONBOOT=no`, `eth0` was
`UP/LOWER_UP` with **no IPv4 address** -- so SSH timed out. Diagnosis before action: `vmrun list`
(1 VM), `checkToolsState=running`, `getGuestIPAddress` failed, Tools-channel `ip addr` showed no
`inet`, `service sshd status` = running. With the user's explicit approval I ran
`dhclient -1 eth0` (temporary lease only; no `ifcfg-*`, `ONBOOT`, NAT or service change). The lease
came back as 192.168.3.128. Host->guest then still failed with `Get-NetNeighbor` = **Incomplete**
while guest->host ping worked; that was a stale Windows neighbor entry cached before the lease, and
it resolved on retry -- `SSH-2.0-OpenSSH_5.3`, no firewall/SSH/config change was involved.

## PDK / device facts, measured on this machine

```
SPECTRE   = /opt/MMSIM151/tools/bin/spectre   (licence checkout works after reboot)
MODEL LIB = pdk/smic18mmrf_teacher/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib
SECTIONS  = tt ss ff fnsp snfp mos_mc  (+ bjt_/dio_/mim_/res_/var_ per-device families)
            -> the task book's expected tt/ss/ff names are CONFIRMED present; every deck still
               prints the section it actually used.
MOS masters that exist: n18 p18 n33 p33, plus dnw variants n18_dnw(_4t)_ckt n33_dnw(_4t)_ckt
            p18_dnw(_4t)_ckt p33_dnw(_4t)_ckt, and nmvt/nnt 18/33 flavours.
NO 5 V FAMILY: there is no n50/p50 master. VSCAN is therefore capped at the 3.3 V devices, which
            is a hard input to the voltage budget below, not a preference.
```

### Which 3.3 V master can a high-side switch actually use (Spectre-measured, not name-guessed)

`scripts/sc1_pdk_smoke.sh` instantiates each candidate at 4 and 6 terminals and reports the real
Spectre verdict (`cadence_work/sc1_sim/pdk_smoke.csv`):

| master | 4-node (D G S B) | 6-node | meaning |
|---|---|---|---|
| `p33` | **ACCEPTED** | SFE-46 | plain 3.3 V PMOS, bulk is a 4th pin |
| `p33_ckt` | **ACCEPTED** | SFE-46 | same with R/C parasitics |
| `p33_dnw_4t_ckt` | **ACCEPTED** | SFE-46 | **deep-n-well isolated PMOS at 4 terminals -- the device a high-side anode switch needs** |
| `p33_dnw_ckt` | SFE-45 terminal count | SFE-46 | needs more nodes; not usable at 4 |
| `p33_dnw` | SFE-23 | SFE-23 | not a valid master name |
| `n33_dnw_4t_ckt` | **ACCEPTED** | — | consistent with the DATA-5 finding |

So the S3 high-side switch has a legal isolated-well 3.3 V PMOS (`p33_dnw_4t_ckt`), letting bulk be
tied to the local source/VSCAN rail instead of a fixed substrate -- this is the single most useful
S0 result, and it mirrors the n33 lesson from DATA-5 (never trust a device name; count terminals).

### My own S0 error, recorded so nobody repeats it

The first smoke run failed **all 16 cases including n18**, which the golden DFF proves works. Cause:
I invented the line `dc ana=dc`, which Spectre parsed as an instance named `dc` --
`ERROR (SFE-709): No master specified for instance 'dc'`. My classifier then reported the generic
`Error found by spectre during circuit read-in` summary, which made a bad deck look like missing
devices. Fix: copy analysis syntax from a deck known to run on this build
(`sw1 dc dev=Vsrc param=dc ...`, as in `spectre/nmos_probe.scs`) and grep the specific
`ERROR (/SFE-` line, never the summary. A blanket FAIL across a family that includes a known-good
member is evidence about the harness, not the DUT.

## Blocking analysis to carry into S2/S3 (voltage budget)

`ENGINEERING_DERIVATION`, from the task book's own constraint plus the confirmed device ceiling:

```
VSCAN >= Vf + V_DATA_MIN(0.5) + V_DROP_SCAN(0.1 target) + line + margin
ignore line/margin for the first POC:  VSCAN_MIN ~= Vf + 0.6 V
  Vf=2.5 -> 3.1 V   fits under 3.3 V
  Vf=2.7 -> 3.3 V   exactly at the rail, zero margin
  Vf=2.8 -> 3.4 V   OVER  -- and no 5 V device family exists to build it with
  Vf=3.0 -> 3.6 V   OVER
  Vf=3.3 -> 3.9 V   OVER
=> the 3.3 V conditional output domain can be proven as a POWER STAGE, but the full chain
   (anode switch + 15 uA sink + LED) is NOT provable at Vf >= 2.8 V inside legal devices.
   Expected honest verdict: SYSTEM_BUDGET_UNSATISFIED_AT_3V3 for the upper Vf rows,
   with the switch itself evaluated on its own merits. LED_VF_5UM_15UA stays NOT_DEFINED;
   the paper's 20 um LED at 2.6-2.8 V is a read-off-graph approximation for a different device
   and must not be quoted as this project's Vf.
```

## Golden-input conflict: found, then resolved with a repeatable method

`tb_preflight`/`sc1_s1.sh` printed `GOLDEN_SHA256=6f87440e...` while the repo's
`spectre/C2MOS_DFF.scs` hashes `d1eed4e2...`. Before trusting either, the files were compared:

```
repo   : 85 lines, subckt spans 38..85
guest  : 82 lines, subckt spans 35..82        -> same 48-line block, offset by exactly 3
MOS count both sides: 18
sha256 of the extracted "subckt c2mos_dff .. ends c2mos_dff" block (CR-stripped):
   repo  7d22c3a607507f3b
   guest 7d22c3a607507f3b      IDENTICAL
```

So the accepted circuit body is byte-identical; the guest copy simply lacks 3 header comment lines
that were added to the repo file later. Verdict: **C2MOS_GOLDEN_UNCHANGED: YES**, but the correct
comparison for this project is the *subckt block*, not the whole-file hash -- a whole-file hash
compares documentation and will keep raising false alarms (and the guest tree carries no `reports/`
directory at all, so report hashes cannot be taken on the guest).

## SCAN-1R status (2026-10-12, this session)

### S1 = REWORK -> now genuinely PASSING, with the real root cause of SFE-874

`SFE-874` was **my syntax, with file and line**:

```
ERROR (SFE-874): ".../s1_dff.scs" 11: Unexpected real number "100n". Expected close parenthesis.
ERROR (SFE-874): ".../s1_dff.scs" 13: Unexpected real number "400n". Expected close parenthesis.
```

Lines 11/13 were `type=pwl time=(0 100n ...) val=(...)`. `spectre -h vsource` on this machine
shows the supported forms: `type=pwl wave=[t v t v ...]` and `type=pulse val0=.. val1=..`.
Switching to those made `tb_preflight` PASS (rail + operating point, RAIL_WARNINGS=0) with
**nothing skipped** -- preflight failure still exits 7.

Truth table, measured volts (not thresholds), `s1r_truth.csv`: `Q=1/BLANK=0 -> 1.8 V`, the other
three rows `0.000000 V`. Transient, golden DFF + 4-transistor NOR, worst-case-in-window
(`s1r_transient.csv`): T1 en<=0.075 V, T2 en>=1.7999 V, T3 q>=1.7656 V across the BLANK release,
T4 en<=0.000004 V, T5 q<=0.002007 V -> **5/5, `SCAN_DIGITAL_BLANK: PASS`**. Stimulus sanity is
asserted first (clk actually reaches 1.8 V), because otherwise every window verdict is hollow.

Fault injection is now a real fault: the gate's BLANK pin is clamped to vss in a copy, thresholds
and expected values untouched, measured through the identical path. Correct circuit
`en=0.075345 V`, faulted circuit `en=1.800096 V` in the same window -> the unchanged T1 assertion
rejects it. `CHECKER_CAN_FAIL: PASS`. (The earlier attempt was invalid twice over: first it
swapped a NOR's inputs, which cannot change a symmetric function; then it "detected" via a window
assertion that had zero samples.)

Harness self-tests pass: unknown signal -> exit 3, empty data file -> exit 2, vss-floating bench
-> preflight rejects.

Two harness bugs found and fixed along the way, both of which could have produced false verdicts:
1. `run_spectre.sh` window mode passes `EXPECT_T0=400n` to awk as `-v t0=400n`; awk reads that as
   the number 400 and compares it against sample times near 4e-7, so windows silently contain zero
   samples and every `EXPECT_LT` assertion "fails" for a reason unrelated to the circuit. S1
   window judgement now goes through `sc1_read_psf.py`, which parses SI suffixes properly and
   refuses to answer with fewer than N samples (`--require-n`).
2. `sc1_delay.py` initially treated "first crossing above threshold" as an edge in either
   direction, which measured the end of a rise as a 194 ns "fall". Crossings are now directional;
   validated against known S1 data (rise 0.774 ns, fall 0.058 ns) and a flat rail correctly
   returns NO_EDGE/exit 4.

### S2 = BLOCKED, not passed. Do not read anything below as a level-shifter result.

Delivered but unverified: `spectre/sc1_level_shifter.scs` with two candidates -- A: diode-connected
`p33` load + `n33` driver (2 transistors, inverting, chosen because the S3 high-side PMOS needs
gate-low = selected); B: A plus one 3.3 V push-pull inverter as the gate buffer, to answer "is a
buffer needed" from timing data. `scripts/sc1_s2.sh` is written to measure levels, node-referenced
stress, delay versus 0/0.2/1/5 pF and missing-supply cases.

Blocker: preflight refuses the S2 static decks. Cause chain established so far, in order:
1. first the iprobe was in the VDD33 leg, so the subckt's `vdd33` pin was no longer driven by an
   independent source to node 0 -- preflight was right to refuse; removed.
2. then a single-point DC sweep was illegal: `ERROR (SPECTRE-16108): sw: Stop limit must not equal
   start limit.`; replaced with the 0/1.8 two-point sweep that S1 uses successfully.
3. still refusing, and the most likely remaining cause is a **tooling limit rather than a circuit
   fault**: `tb_preflight.sh` takes one `expected_vdd`, but this bench is dual-rail (vdd18=1.8 and
   vdd33=3.3 on the same instance), so one rail necessarily mismatches the single expectation.
   This is the last thing checked before context ran out and is NOT yet confirmed.

Next action for whoever picks this up: decide between (a) extending preflight to accept a per-port
rail map (a real improvement; must keep the existing negative bench failing), or (b) giving each
supply its own preflight pass. Do not obtain an S2 PASS by skipping the gate.

Also outstanding for S2: static current through the converter while selected is
`NOT_MEASURED`. Three bounded attempts failed (iprobe-in-rail broke preflight; two ad-hoc saves
produced rc=1 and rc=127 from my own harness), so it was dropped rather than faked. Same status
for the reverse-current-into-a-dead-rail number in the sequencing matrix.

No blocker. Next: **S1** -- transistor-level `SCAN_EN = Q & !BLANK` in n18/p18, 4-row truth table at
both rails, plus BLANK acting without disturbing the stored DFF state, run through
`tb_preflight.sh` before any verdict.

## Scope guards in force this stage

Nothing modified: teacher PDK (read-only greps only), golden C2MOS deck, frozen DATA reports, any OA
cellview, Cadence install, licence files, VM/Git/global config. New files are confined to
`cadence_work/sc1_sim/` on the guest and `sc1_`/`scan1_`/`scan_driver_` paths in the repo.
No foundry model text is being copied into the repo; only measured verdicts and the numbers actually
relied on are recorded.

## Historical sections (kept; superseded parts marked)

### SCAN-1R2 round status block, moved out of CURRENT_STATUS on 2026-10-12 (R2A)

## HISTORICAL_STATUS (SCAN-1R2 round, kept for audit; superseded)

Updated 2026-10-12 during SCAN-1R2 / S2-only. Baseline reviewed by the cloud reviewer:
`poc/scan-driver-1ch` @ `fc6757bda8b410ebf34e4bbcf248eaa2a98a19b6`, main @
`23e471cb936b421ee97e1250c3be06edf96f9937` (both re-read from the remote this session).

| item | status | evidence |
|---|---|---|
| R0 measurement tools | **PASS** | `results/evidence/sc1_r2_checker.csv` 27/27 offline synthetic cases, 4 regression cases |
| R1 dual-rail preflight | **PASS** | `results/evidence/sc1_r2_preflight.csv` 11/11 matrix; `scripts/sc1_supply_check.awk` + 5th call form, legacy path unchanged |
| R2 S2 circuit matrix | **NOT STARTED** (unblocked by R1, not attempted this session) | old `sc1_s2.sh` still has the review's defects |
| R3 S1 regression + real chaining | **NOT STARTED** | required because R0 changed the measuring path |
| S1 (previous round) | conditionally accepted logic POC; **must be re-run under R3** | `s1r_truth.csv` 4/4, `s1r_transient.csv` 5/5 |
| S3 / S4 | NOT STARTED, out of scope | — |
| main / teammate branches | untouched, not merged | remote re-read |

Commits this session on `poc/scan-driver-1ch`: `86df706` (R0), `12125f0` (R1), on top of the
reviewed baseline `fc6757b`.

### R1 in one line

`tb_preflight.sh` now accepts an explicit supply contract as a 5th argument
(`vdd18=1.8 vdd33=3.3 vss=0`), matched by declared port name rather than a `vdd` substring, so a
dual-rail bench is no longer mis-checked whichever single expectation is chosen. A **declared 0 V**
is a legitimate, still-verified value, which is what makes a power-down scenario expressible;
an undeclared, unconnected, wrongly-driven or swapped supply rail is refused, a supply-like port
missing from the map is refused, and a contract over zero instances refuses to pass vacuously. The
legacy 3-argument behaviour is preserved and proven by the matrix (legacy bench passes, the
project's floating-vss bench is still refused).

Two matrix rows failed for reasons that were mine, and the tool was left alone: a deck tying `vssx`
to node 0 through a source is genuinely legal (my "negative" was not negative), and one case invoked
the checker before its deck existed (rc 8 was a missing file, not a verdict).

### R2 next, in order

1. Rewrite `sc1_s2.sh` against §4.3 before any circuit verdict: `cur="NOT_MEASURED"` currently
   reaches `float()`, stress formulas assume candidate A's topology for candidate B, S2.4 skips
   preflight while the script claims it does not, `V18_float` is undefined under `set -u`, row labels
   must match the sample actually read, the load CSV header says fF but stores pF values, and
   internal nodes must be read by hierarchical name (`X1:shift`), not as top-level nets.
2. Implement the §5 cross-coupled core, then C0 and C1 with the polarity table verified by
   measurement, including the competition question the review flagged: whether a 1.8 V-driven n33 can
   actually flip the p33 cross-coupled pull-up. Sizes chosen from data, not from "classic circuit".
3. Use the new contract for every formal deck; report S2_SAFE_OFF_CONDITIONAL at best as
   `PASS_WITH_ASSUMED_CORE_OK`, and `S2_AUTONOMOUS_POWER_FAIL_SAFE: NOT_IMPLEMENTED`.

### Caution learned this session

Putting awk inside the shell script's single-quoted string produced an unterminated-string awk
program that silently broke even the previously-working legacy path. The checker now lives in its own
`.awk` file. Do not nest program text inside shell quoting again in these tools.
