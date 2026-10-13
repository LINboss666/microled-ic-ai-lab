# SCAN-1 R3 — one scan channel's control chain, really chained (native TT record)

Round: **SCAN-1R3**, start point `281e58757682a00b12f6da9fafaf685dc8dcf120` (the R2E2 head the cloud
pulled and reviewed as `ACCEPT_TT_RECORDS / GO_R3`). Write-up of the record only — the circuit answer
is in `results/evidence/sc1_r3_chain_cases.csv` (428 rows), `sc1_r3_chain_manifest.csv` (9 rows),
`sc1_r3_waveform_samples.csv` (812 rows) and `sc1_r3_chain_dependency_log.txt` (296 lines).

> **Delivered-evidence note (SCAN-1R3A).** Two of those four files reached the repository at
> `f199245` as **header rows only** — `sc1_r3_chain_manifest.csv` 195 B / 0 data rows and
> `sc1_r3_waveform_samples.csv` 67 B / 0 data rows — while this report said "9 rows" and "177 rows".
> Both claims were true of the batch that ran and false of the bytes that were committed; the cause,
> the recovery and the corrected sample count are in `reports/scan_driver_r3a_delivery_repair.md`.
> Nothing about the circuit, the 428 native rows or the verdicts changed.

**Verdict: `R3_CONTROL_CHAIN: PASS`** — 8 normal cases + 1 real wiring fault, all nine decks preflight
`rc=0` and simulate `rc=0`, **0 functional FAIL, 0 dependency BLOCKED**, and the fault case is
`DETECTED` while every other state row in the same deck still holds.

## 1 What is new is only the connection

`spectre/sc1_r3_scan_chain.scs` (new, 36 lines) instantiates the three already-accepted cells. The port
orders were read off the cell files rather than taken from the task text:

| cell file | `subckt` line as it sits in the file | devices |
|---|---|---|
| `spectre/C2MOS_DFF.scs:38` | `c2mos_dff (d clk q qbar vdd vss)` | 18 |
| `spectre/sc1_scan_gate.scs:30` | `sc1_scan_gate (qbar blank en vdd vss)` | 4 |
| `spectre/sc1_level_shifter_r2d.scs:144` | `sc1_ls_c1_top_r2d (en core_ok33 gate33 vdd18 vdd33 vss)` | 10 |

```
subckt sc1_r3_scan_chain_1ch (d clk blank core_ok33 gate33 vdd18 vdd33 vss)
  Xff   (d clk q qbar vdd18 vss)             c2mos_dff
  Xgate (qbar blank en vdd18 vss)            sc1_scan_gate
  Xls   (en core_ok33 gate33 vdd18 vdd33 vss) sc1_ls_c1_top_r2d
```

Three consequences of reading instead of assuming:

* **the supply contract needs two names for one rail.** The 1.8 V cells declare `vdd`, the level
  shifter declares `vdd18`, and the frozen checker (`scripts/sc1_supply_check.awk::top_check`) keys on
  the **port name**, so every R3 deck passes `vdd=1.8 vdd18=1.8 vdd33=3.3 vss=0`. Both `vdd`
  connections land on the deck's `vdd18` net, which has its own independent source, so the certified
  potentials are reached rather than assumed. All 9 `PREFLIGHT_FULL` rows carry that map and `rc=0`.
* **device count is derived from the netlist, not stated.** `R3_DEVICE_COUNT` resolves the instance
  tree through the same `resolve_devices()` the accepted S2 entries use: **32 four-terminal devices**
  in every case, first paths `Xchain.Xff.mn_c, Xchain.Xff.mp_c, Xchain.Xff.mp_m1` — 18 + 4 + 10 with
  **no power output device**.
* **q / qbar / en stay inter-module nodes.** `R3_NO_IDEAL_INTERPOSE` greps each generated deck for any
  source attached to those three nets and records **`drivers found: none`** in all 9 cases; the only
  sources in a deck are `V18 (vdd18 0)`, `V33 (vdd33 0)`, `Vss`, `Ven (en …)` — and there is no `Ven`:
  `en` is reached as `Xchain.en`, the level shifter's input port. `d`, `clk`, `blank` and `core_ok33`
  are the only externally driven nets. `gate33` carries only the declared 1 pF or 5 pF capacitor.

## 2 Provenance: the guest mirror was stale, and the record was re-made

The first native attempt (same day, `R3-CHAIN-20261013T120713Z`) recorded
`C2MOS_DFF.scs=6f87440ea723…`, which is **not** the hash of the tracked file. Pulled back and compared:
guest 4497 B / 82 lines vs repository 4754 B / 85 lines, and the diff is **one comment hunk only**
(the old absolute "a write always wins" wording vs the reviewed measured-scope wording). No device
line, no `L`/`W`, no connection differs.

That is a provenance defect, not a circuit change, and it was closed by restoring the mirror rather
than by accepting a mismatched hash:

1. the stale guest bytes were copied into `/root/qoder_ic617_sandbox/C2MOS_DFF.stale_20261013.scs`
   (reversible) and also pulled to Windows temp and diffed before anything was written;
2. the **repository** bytes were pushed back through the Tools channel (`push_chunked.sh`, 4 chunks,
   host md5 `b82979bb…` == guest md5 `b82979bb…`). That helper is a bridge-side script under
   `D:\ic617_agent_bridge\scripts\` which is **not tracked** in this repository, so it is named here
   with the observable result it printed rather than presented as a deliverable;
3. all four included files were re-hashed on the guest and now equal the repository exactly —
   `C2MOS_DFF.scs d1eed4e242fa…`, `sc1_scan_gate.scs c078637719cc…`,
   `sc1_level_shifter_r2d.scs 31324ca541a6…`, `sc1_r3_scan_chain.scs 4dffb7856cc4…`;
4. the nine cases were **re-run natively** (`R3-CHAIN-20261013T122004Z`). Every deck sha256 in the new
   manifest equals the old one (`d081864d0e0c…` for `r3_q0_off`, `67fb26b08b26…` for `r3_write_q1_on`,
   …) and every reported number is bit-identical to the first attempt — 428 rows, the same 18/18
   propdelay answers, the same window values. That agreement is the expected result of a
   comment-only diff and it is what makes the re-run an identity check rather than a second experiment.

Delivered: **9 preflight processes + 9 DUT processes** for the batch this report describes
(`R3_PROCESS_COUNT preflight=9 DUT=9`), counted from artifacts on disk, not asserted. **That figure is
the delivered batch, not the round total** — see §9.

Batch labelling, so the two runs are never mixed: every delivered row carries
`run_id = R3-CHAIN-20261013T122004Z` (the repository-bytes batch). The earlier
`R3-CHAIN-20261013T120713Z` batch (comment-mismatched mirror) wrote to the **same paths**, so its own
copies of `sc1_r3_chain_manifest.csv` / `sc1_r3_waveform_samples.csv` / `sc1_r3_chain_cases.csv` / the
dependency log no longer exist as separate files anywhere; what survives of it is this report's §2
text plus the fact that its numbers were identical. Its artifacts are therefore **NOT RETAINED**, and
no claim below is supported by them.

The nine deck files the simulator read are still on the guest at
`cadence_work/sc1_sim/r3_chain/*.scs`, and their sha256 re-read one by one equals the `deck_sha256`
column of `sc1_r3_chain_manifest.csv` (`r3_q0_off d081864d0e0c…`, `r3_write_q1_on 67fb26b08b26…`,
`r3_blank_assert 67c590ef2cd4…`, `r3_blank_release e5b458d4f3b9…`, `r3_write_q0_off bd808f961d36…`,
`r3_repeat_101 f6a3fb12a868…`, `r3_external_guard 4b67ac132290…`, `r3_load5p 71a47958c2f4…`,
`r3_fault_blank_tied_vss 9989e6da5743…`) — 9 for 9. Following the R2E practice, the deck text is not
duplicated into the repository: **`--dry --expect 9` regenerates exactly these bytes**, and it does so
identically from Windows Python 3.12 and from the guest's Python 2.6.6 — the nine files regenerated on
this host hashed to the same nine values listed above, and the four cell copies written beside them
came back `d1eed4e242fa…`, `c078637719cc…`, `31324ca541a6…`, `4dffb7856cc4…`, i.e. the repository
bytes. So a reviewer with only the repository can rebuild the exact deck every number came from.

## 3 Stimulus framework, and the deck held to its own word

One framework (`POC_ASSUMPTION` stimulus choices, explicitly **not** a setup/hold budget): clock period
100 ns, high/low ≈50 ns, every edge 2 ns, `d` stable ≥20 ns before the rising edge that samples it,
`blank`/`core_ok33` changes ≥20 ns from any rising edge, `stop=900n maxstep=0.1n`, TT section,
`simopt options temp=27`, rails from independent `vsource`s, `vss` explicitly at 0.

`audit_frame()` re-reads the **emitted PWL** — not the generator's intent — and writes the check into
the CSV: 11 `DATA_SETUP` rows (e.g. `d change at 220n ns leads the next rising edge by 30.0 ns (need
>= 20)`), 26 `GUARD_SPACING` rows (e.g. `200n ns change is 50.0 ns from the nearest rising edge`), and
31 `WINDOW` rows that each state their sample count and their clearance from any ramp
(`established_Q0 [160n..190n] ns: 301 samples, 10.0 ns clear of any ramp`). All 68 come back `PASS`; a
violation would have blocked the case as `R3_SETUP_INVALID` before the simulator was called.

The DFF has no reset, so every case runs `blank=1`, `core_ok33=0`, `d=0` through **two real rising
edges** (50 ns, 150 ns) and only the `established_Q0` window after that is judged — read back, never
forced: `Xchain.q` low (`min=-8.73e-08 max=1.04e-07 V`), `Xchain.qbar` high (`1.8/1.8 V`) in all 9
decks.

## 4 The nine cases, judged whole-window

106 `R3_WINDOW_STATE` rows: a "high" claim needs the window **minimum**, a "low" claim the maximum,
with ≥10 samples from the strict reader; the 1.8 V domain is judged at its own 50 % level and `gate33`
against the `POC_ASSUMPTION` screening pair `≥3.135 V / ≤0.30 V`. 62 `R3_PLATEAU` rows carry the
steady-window min/max/mean separately from the transition intervals, so no single instant certifies a
window.

| case | what the deck had to show | representative whole-window values | verdict |
|---|---|---|---|
| `r3_q0_off` | a reset-free chain that was never written leaves the gate off | `en` 9.5e-07…1.2e-06 V low; `gate33` 3.3/3.3 V high at 250 ns and 450 ns; `q` low, `qbar` 1.8 V | 10/10 PASS |
| `r3_write_q1_on` | one legal write selects | `q`/`en` 1.8/1.8 V high, `qbar` 4.6e-09 V low, `gate33` −1.0e-08…1.8e-08 V low at both 250 ns and 350 ns | 10/10 PASS |
| `r3_blank_assert` | blank acts on the **output**, not on the store | `blanked_450`: `q` 1.8 V still high, `qbar` low, `en` 6.6e-09 V low, `gate33` 3.3 V high | 10/10 PASS |
| `r3_blank_release` | releasing away from an edge re-selects with **no rewrite** | `blanked_350` en low / gate33 high, `released_550` en 1.8 V / `gate33` 3.2e-09 V, `q` 1.8 V throughout | 14/14 PASS |
| `r3_write_q0_off` | a legal write of 0 switches off | `deselected_350`: `q` −4.7e-11…2.2e-08 V, `qbar` 1.79999…1.8 V, `en` 2.0e-06…4.7e-06 V, `gate33` 3.3 V | 10/10 PASS |
| `r3_repeat_101` | 1→0→1 through real clocks, three states | `state_1_after_250` selected, `state_0_after_350` deselected, `state_1_after_450` selected again | 14/14 PASS |
| `r3_external_guard` | the **external** guard path only | `guarded_450`: `gate33` 3.3 V high **while `en` stays 1.8 V and `q` stays 1.8 V**; `guard_back_650` `gate33` 3.2e-09 V | 14/14 PASS |
| `r3_load5p` | same logic at 5 pF, new dynamics | `selected_250` `gate33` **9.17e-06…0.0178 V** (≤0.30 V, the load's own low plateau), `blanked_350` 3.3 V, `released_550` 3.2e-09 V | 14/14 PASS |
| `r3_fault_blank_tied_vss` | the fault must refuse the blank assertion and nothing else | `blanked_450`: `en` **1.8/1.8 V**, `gate33` **3.2e-09 V** → both refused; the other 8 rows (incl. `selected_250`, `q`, `qbar`) still PASS | 8 PASS + 2 `EXPECTED_REFUSAL` |

36 `R3_STIMULUS_READBACK` rows confirm the stimuli themselves reached their declared rails in the wave
(`clk` 0…1.8 V, `blank` 0…1.8 V, `core_ok33` 0…3.3 V, `d` 0 or 0…1.8 V), so no judgement rests on the
generator text alone.

## 5 One end-to-end waveform, read from the data

`r3_write_q1_on`, event `clk_up_to_gate33_end_to_end` in
`results/evidence/sc1_r3_waveform_samples.csv` — the actual consecutive samples around each node's own
50 % crossing of **one** input edge (the 250 ns write), not a list assembled from different events.
Times in ns, values in V, `sample_group_index` is the row index in the simulator's own data file:

| idx | t | clk | q | qbar | en | gate33 |
|---|---|---|---|---|---|---|
| 2582 | 249.928 | 0.8356 | −2.8e-05 | 1.79999 | 1.7e-06 | 3.300 |
| 2584 | 250.003 | **0.9024** | 1.1e-04 | 1.80001 | 2.2e-06 | 3.300 |
| 2590 | 250.137 | 1.0234 | 0.6822 | 1.82868 | −3.5e-04 | 3.300 |
| 2592 | 250.183 | 1.0648 | **1.0072** | 1.66483 | −2.9e-03 | 3.300 |
| 2595 | 250.253 | 1.1274 | 1.4704 | **0.9218** | −1.2e-02 | 3.300 |
| 2602 | 250.356 | 1.2204 | 1.7891 | 0.0278 | **0.8958** | 3.29992 |
| 2645 | 252.040 | 1.8000 | 1.8000 | 7.3e-08 | 1.8000 | 1.9364 |
| 2647 | 252.240 | 1.8000 | 1.8000 | 3.2e-08 | 1.8000 | **1.6230** |
| 2649 | 252.440 | 1.8000 | 1.8000 | 1.0e-07 | 1.8000 | 1.3198 |

The exported event row states the interpolated crossings and the bound in one line:

```
input clk at 2.5e-07 s ; q at 2.50167135e-07 s ; qbar at 2.50254283e-07 s ;
en at 2.5035635e-07 s ; gate33 at 2.52222929e-07 s ; attribution bound t_next=3e-07 s
```

so `gate33 − clk = 2.223 ns` is recomputable from this file alone, and §6's native row agrees exactly.

Two things this table corrects versus the first draft of this report:

* **`clk` is not at its plateau when `q` crosses.** At `q`'s 50 % crossing `clk` reads 1.02–1.06 V,
  still inside its own 2 ns ramp (the clock's 50 % point is 250.003 ns, the sample at 250.183 ns is
  1.065 V). The propagation is therefore attributed to `clk`'s 50 % crossing precisely because the
  clock edge is still moving through the sampling instant — not because a settled clock pushed `q`.
* the 150 ns priming edge is **not** part of this chain. The first draft printed
  `clk 150 ns → q 250.167 ns → en → gate33`, which mixed the initialisation clock with the write edge;
  the initialisation now has its own `initialisation_crossing` row per case, labelled
  `NOT a cause of any judged response`.

The `en` node swings negative (−3.5e-04 … −1.2e-02 V) while `qbar` falls — the level shifter's input
being pulled through the gate cell, on a node no source drives.

## 6 Propagation, attributed by the audited tool

18 `R3_PROPDELAY` rows come from the accepted `scripts/sc1_delay.py` (input 50 % crossing, next
either-direction 50 % crossing as the attribution bound), and each is paired with an
`R3_PROPAGATION_50_50` row that prints `t_in`, `t_out`, `t_next` and the output's own 10 % onset so a
reviewer can recompute the answer from the same crossing lists. Since R3A the delivered
`sc1_r3_waveform_samples.csv` also carries those crossing lists per event, and
`scripts/sc1_r3a_verify_evidence.py` performs the recomputation itself: **18 of 18 events reproduce
their native delay (to the row's own 0.001 ns print precision) and their attribution bound, on the
guest and on Windows alike.** 14 answers are `PASS`, **4 refuse to answer**
(`NOT_MEASURED_OVERLAP`), and none of them is replaced by a summed estimate:

| case | input → output | delay | `t_in` / `t_out` / `t_next` (ns) |
|---|---|---|---|
| `r3_write_q1_on` | clk↑ → `q` | **0.167 ns** | 250.000 / 250.167 / 300.000 |
| `r3_write_q1_on` | clk↑ → `en` | **0.356 ns** | 250.000 / 250.356 / 300.000 |
| `r3_write_q1_on` | `en`↑ → gate33↓ | **1.867 ns** | 250.356 / 252.223 / `END_OF_DATA` |
| `r3_write_q1_on` | **clk↑ → gate33↓ (end-to-end)** | **2.223 ns** | 250.000 / 252.223 / 300.000 |
| `r3_blank_assert` | blank↑ → gate33↑ | **1.629 ns** | 400.000 / 401.629 / `END_OF_DATA` |
| `r3_blank_release` | blank↓ → `en`↑ | **0.342 ns** | 500.000 / 500.342 / `END_OF_DATA` |
| `r3_blank_release` | blank↓ → gate33↓ | **2.280 ns** | 500.000 / 502.280 / `END_OF_DATA` |
| `r3_write_q0_off` | **clk↑ → gate33↑ (end-to-end)** | **1.819 ns** | 350.000 / 351.819 / 400.000 |
| `r3_repeat_101` | edge 1 / 2 / 3 → gate33 | **2.223 / 1.819 / 2.224 ns** | 250 / 350 / 450 ns inputs |
| `r3_external_guard` | guard↓ → gate33↑ ; guard↑ → gate33↓ | **1.293 / 1.246 ns** | 400 / 600 ns inputs |
| `r3_load5p` | blank↓ → gate33↓ (**5 pF**) | **6.311 ns** | 500.000 / 506.311 / `END_OF_DATA` |

Four honest refusals, all the same mechanism: the output's **10 % onset precedes `t_in`**, so a 50 %
figure for that input edge would be a number attached to an event that had already begun —
`blank↑ → en↓` in `r3_blank_assert` (onset 399.823 ns vs `t_in` 400.000 ns), the same pair in
`r3_blank_release` and in `r3_load5p` (onset 299.816 ns), and `clk↑ → q↓` in `r3_write_q0_off` (onset
349.771 ns). The tool prints `AMBIGUOUS_RESOLUTION`; this round keeps it as `NOT_MEASURED_OVERLAP`
(informational) instead of relabelling it `PASS` and instead of quoting its 0.025–0.032 ns arithmetic
difference as a propagation delay. The cause is visible in the numbers: `blank` is a 2 ns ramp on a
100 ns clock, and `en`'s own fall is already under way before the ramp's midpoint.

**No fixed acceptance budget exists for any of these** — they are `MEASURED` against a timing spec that
the requirement set does not define (`NOT DEFINED`). The end-to-end rows are measured directly from
`clk` to `gate33`; nothing sums per-block delays.

## 7 Edges, plateaus and the two rails

18 `R3_EDGE` rows (10–90 %, `policy=first_complete`, from the accepted edge tool):

| load | gate33 fall | gate33 rise |
|---|---|---|
| 1 pF | **2.025 ns** (21 samples in the interval) | **1.849 / 1.850 / 2.005 ns** by source of the event |
| 5 pF | **9.893 ns** (99 samples) | **9.040 ns** (91 samples) |

The 4 `EXPECTED_REFUSAL` edge rows are `r3_q0_off` and `r3_fault_blank_tied_vss`, whose declared
stimulus produces no `gate33` edge to measure — recorded as a refusal, not as a zero.

18 `R3_RAIL_CURRENT` + 36 `R3_RAIL_PEAK` rows read the source currents as `save V18:i` / `save V33:i`
and convert with the calibrated rule **injected = −(Vsource:i)** (the 2-value `read_diff` against `vss`
gives the peak time). Range over the 9 decks:

* `vdd18` injected: peak out of the rail **0.202…0.698 mA** across the nine decks (worst
  `r3_write_q0_off` at 350.256 ns; `r3_q0_off`, which switches nothing, only reaches 0.202 mA), and
  peak back into the rail **13.2…13.8 µA**;
* `vdd33` injected: peak out of the rail **0.864…0.869 mA** on the decks whose stimulus pulls `gate33`
  down once (250.9–251.1 ns), **1.912…2.017 mA** on the decks that also do a blank/guard event
  (300.86…401.0 ns), **2.042 mA** at the 5 pF blank edge, and **0.8 nA** in `r3_q0_off` whose gate
  never falls; peak back into the rail **25.3…32.8 µA**;
* every rail row stays `MEASURED`: no standby/peak budget is defined, so no PASS is claimed on them,
  and no per-device rail sum is presented as verified (the series-`iprobe` supply-constraint finding
  from R2D stands).

## 8 The negative case is a real fault, and it is caught

`r3_fault_blank_tied_vss` changes **one statement** in one deck. `R3_FAULT_DECK_DIFF`:
`statements: 2 (instance 2, other 0) | comments: 2`, the pair being

```
-Xchain (d clk blank core_ok33 gate33 vdd18 vdd33 vss) sc1_r3_scan_chain_1ch
+Xchain (d clk vss     core_ok33 gate33 vdd18 vdd33 vss) sc1_r3_scan_chain_1ch
```

Everything else — the three cells, the sizes, the priming, the `d`/`clk`/`core_ok33` PWL, the 1 pF
load, the analysis line — is byte-equal, and the deck still runs with `preflight_rc=0 spectre_rc=0`.

`R3_NEGATIVE_RESULT: DETECTED` — `refused=2 held=8 of 10 ; external blank read back window min=0
max=1.8 V`. The external `blank` pin of the deck does toggle, the store keeps `q=1`, but `en` stays at
**1.8 V** and `gate33` stays at **3.2e-09 V** through the window that must blank: the fault is visible
as "blank no longer blanks", which is exactly the failure mode a chained design can hide. Pre-flight,
simulator, reader and priming all succeeded here, so this is a circuit detection and not a
`BLOCKED`/`SETUP_INVALID` outcome.

## 9 Exit semantics and offline checks

`main()` keeps the three classes R2E1 introduced: functional `FAIL` → exit 1; dependency
`BLOCKED`/`NOT_AVAILABLE`/other `PARTIAL` → exit 2; **informational** (`MEASURED`, `EXPECTED_REFUSAL`,
`NOT_MEASURED_OVERLAP`, `DETECTED`) printed with their own count and never renamed → exit 0.
`--only` with an unknown id returns 9 instead of silently dropping it, and `--expect N` returns 9 on a
wrong selection count. Delivered summary line:

```
R3_TT cases=9 rows=428 functional_FAIL=0 dependency=0 informational=120  -> exit 0
```

Verdict split of the 428 rows: **PASS 307 · MEASURED 109 · EXPECTED_REFUSAL 7 ·
NOT_MEASURED_OVERLAP 4 · DETECTED 1**.

**Authorisation semantics were changed by R3A.** The version that produced the rows above recorded
`NOT_RUN` and *then still wrote* `cases`/`manifest`/`samples`, which is how two delivered CSVs reached
Git as headers. The entry now prints `R3_TT_REFUSED …` and returns 5 **before** touching any file, and
`--dry` without `--out` writes its rows inside the scratch directory instead of onto the native
evidence path. `scripts/sc1_r3a_write_guard_check.py` proves it in an isolated temporary directory:
pre-seeded cases/manifest/samples/log keep their hashes, rc is 5, and no `sim/` artifact appears (no
runner call) — **9/9 on guest 2.6.6 and on Windows 3.12**.

Process counts, stated per batch rather than as a round total:

| batch | preflight | DUT | status of its own artifacts |
|---|---|---|---|
| `R3-CHAIN-20261013T120713Z` (stale comment mirror) | 9 | 9 | overwritten in place by the batch below, NOT RETAINED |
| `R3-CHAIN-20261013T122004Z` (delivered) | 9 | 9 | the files in `results/evidence/` |
| four aborted measurement attempts | not reconstructible | not reconstructible | same scratch paths, reused |

So the delivered batch is **18 Spectre invocations**, the round provably issued **at least 36**, and the
whole-round total is **UNKNOWN** — it cannot be recovered from the directory, because each batch wrote
to the same filenames. No cumulative count is claimed anywhere in this report.

`--selftest` (4 synthetic checks on the crossing/attribution helpers, including the two helper defects
this round pinned: `_near(…, after_only=False)` must return the **last** crossing at or before the
target, and `_next_after()` must be **strict**) passes **4/4 on guest Python 2.6.6 and on Windows
Python 3.12**, including after the R3A sampling change. `--dry --expect 9` builds all nine decks and
audits the frame with no simulator. The offline R2E suites were not re-run: nothing in them changed.

## 10 Deliberate limits of this record

* TT / 27 °C / 1.8 V / 3.3 V / 1 pF and 5 pF all stay `POC_ASSUMPTION`. **No corner, no temperature
  sweep, no supply ramp, no power-fail matrix** — the book forbids them for this round and none was
  run.
* `core_ok33` is driven by a testbench source: the guard path is proven as an **external** pin
  behaviour, and there is **no on-chip undervoltage detection**.
* `gate33` drives a declared capacitor and nothing else. This is **not** a scan electrode load; the
  electrode's real RC is `NOT DEFINED`.
* `SOA: NO` — no absolute-rating table exists in the readable delivery, and a model name containing
  `33` is not a rating.
* No frozen file was edited: the three cells, the accepted reader/delay/vtx/preflight/supply/runner
  tools, the S1/S2 generators and the call contract are read-only here (`git diff 281e587` over them:
  0 files). The new circuit content is one wrapper file; the new executable content is one thin entry.
* No new general tooling gate was opened: the six fix attempts this round were all inside the R3 entry
  itself (deck `wave=` spelling, ns→s unit in the reader call, an undefined variable in the delay
  tuple, deck text reused as runner output in the fault diff, window starts that cut the 2 ns ramp, and
  the two crossing-helper bugs), each with the failure it fixed recorded above.

**Stopped at the R3 single-channel control-chain + output-stage-plan review gate.** `S3_POWER_STAGE:
NOT_RUN`, `S4_CHAIN: NOT_STARTED`. The output-stage pre-design and the parameters that block it are in
`reports/scan_driver_r3_output_stage_plan.md`.
