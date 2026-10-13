# SCAN-1R2E — first native Spectre TT results (calibration → S1 → S2)

Date 2026-10-13. Start: `dd93f6f432a32fc5f1177223a50ff511e83351c2` on `poc/scan-driver-1ch`, re-read with
`git ls-remote` before editing (remote tip was still exactly that commit, so no unknown upstream work
was mixed in). Executed under the authorisation recorded in this round's task book (2026-10-13 11:39:44
Asia/Shanghai) for the local minimal native TT scope only.

Everything below was produced by **this machine's Spectre** (IC617 6.1.7-64b.78 + MMSIM
Spectre 15.1.0.284.isr1, guest RHEL6.5) over the VMware Tools channel. Nothing here is a cloud result.
`S1` historical data stays `PARTIAL_NOT_VERIFIED` and is not upgraded by this round.

## Run identity

| item | value |
|---|---|
| calibration run | `R2E-C1`, csv `results/evidence/sc1_r2e_calibration.csv` (61 rows), log `..._log.txt` |
| S1 run id | inside `results/evidence/sc1_r2e_s1_regression.csv` (32 rows × 14 cols, audited 14-column layout) |
| S2 run ids | `R2E-S2-{static,dynamic,load,negative}-20261013T04xx..05xxZ`, per-deck manifests `sc1_r2e_s2_*_manifest.csv` |
| section | `tt` (measured master-section name in the included `.lib`) |
| temperature | 27 C — **read back**, see TEMP_CONFIRMATION |
| rails | 1.8 V / 3.3 V (POC_ASSUMPTION, not a course limit) |
| protected inputs | `git diff --name-only dd93f6f HEAD --` the audited netlists and tools → **0 files** |

Model identity: the `.lib` the decks include is `ms018_enhanced_v1p2_rev0_spe.lib`, sha256
`fc8d321752f2bacf…dcf95f` = the task book's uploaded value; the `section tt` body pulls
`ms018_enhanced_v1p2_rev0_mis_spe.mdl` (`4b62b398adee…`) and `ms018_enhanced_v1p2_rev0_spe.mdl`
(sha256 `5187cae15226ffde…e7fc1` = the uploaded value); README `..._readme_spe.txt` sha256
`f43d2585330a1cdd…d875` = the uploaded value. All three were re-hashed **from the loaded path this
round**, not taken from the file names (`UPLOAD_HASH_COMPARISON`, `MODEL_INCLUDE_GRAPH`).

---

## 1. MODEL_BINDING — PASS

`GEOMETRY_RANGE_READ` reads each limit out of the model record the `tt` section includes, and reports
the declaring file and line (`MODEL_RECORD_SOURCE`), with the frozen S2 sizes compared against it:

| model | lmin | lmax | wmin | record | sizes used by the frozen cell | verdict |
|---|---|---|---|---|---|---|
| `n18` | 1.5e-7 | 1e-4 | 1.9e-7 | `_spe.mdl` line 53 | l=2e-7, w_min=2e-6 | PASS |
| `p18` | 1.5e-7 | 1e-4 | 1.9e-7 | `_spe.mdl` line 258 | l=2e-7, w_min=2e-6 | PASS |
| `p33` | 3e-7 | 1e-4 | 2.2e-7 | `_spe.mdl` line 866 | l=4e-7, w_min=5e-6 | PASS |
| `n33` | 3.5e-7 | 1e-4 | 2.2e-7 | `_spe.mdl` line 654 | l=4e-7, w_min=5e-6 | PASS |

Three separate things, kept separate as required:

* **model/bin limits** — the table above, read from the included records;
* **characterisation range** — the README states `temperature range:-40C~125C` (5 lines), so 27 C is inside it;
* **absolute maximum ratings** — no rating table exists in any readable file of this release
  (`SOA_SIGNOFF: NO`). Nothing in this report is an SOA signoff.

## 2. TEMP_CONFIRMATION — PASS

`spectre -h options` on this build lists `temp=27 C` and `tnom=27 C`, but in this netlist language
`options` is a **device master**, so the vendor's own `section tt` spells it `setoption1 options
gmin=1e-14`. Measured on this machine: a bare `options temp=27` line is rejected
(`ERROR (SFE-709): … No master specified for instance 'options'`), and the accepted form is the
instantiation `simopt options temp=27`.

The value is then read back from files each run produced, not from a default or a generator comment:

* every calibration deck: log `temp = 27` **and** psfascii header `"temp" 27.0000` — **6 runs, 12
  consistent read-back values** (the two places inside one run are one run, not two);
* every S1 deck of this round (`s1reg_dc_blank0/1.8`, `s1reg_tran`, `s1reg_fault`): log line
  `temp = 27 C`;
* the S2 decks carry the same `simopt` line, so their 27 C is set explicitly rather than inherited.

## 3. SOURCE_CURRENT_CALIBRATION — PASS

Bench: one ideal rail → 10 kΩ → a zero-drop iprobe → vss, inside a subckt instance, i.e. the rail is
still driven **directly** by the vsource and no series element is inserted in it. Theory is exact:
1.8 V/10 k = 180 µA, 3.3 V/10 k = 330 µA. The runner rc, the tool rc and the model identity are
recorded per row.

> **Corrected in R2E1 (was: "`PREFLIGHT_FULL` (same port contract, rc=0) ran before each simulator
> call").** It did not pass. The committed `sc1_r2e_calibration.csv` keeps the note it captured —
> `SUPPLY_RESULT FAIL`, `PREFLIGHT_STAGE=supply_contract`, `PREFLIGHT_REJECT: contract_refused:contract
> entry vdd18 matches no instance port`, `TESTBENCH_PREFLIGHT: FAIL` — while the rc column says `0` and
> the verdict says `PASS`, because the entry called the preflight through `... | tail -4` and recorded
> *tail's* status. The bench's own rails are `rail`/`vss`, so the supply map has to name them (a
> `rail=1.8 vss=0` contract), and that re-run still belongs to an authorised session. What survives:
> the current/temperature values were produced by real runs whose `runner_rc=0` and
> `SPECTRE … rc=0` came from a call that had no `tail`, so the calibration conclusions stand; the
> preflight claim does not, and `scripts/sc1_r2e1_call_contract.py` now makes the mistake impossible
> for both entries (see `reports/scan_driver_r2e1_gate_review.md` §1-§2).

Measured save forms on this build (one candidate per deck, because a fatal save kills the file):

| save item | where | result |
|---|---|---|
| `V18:i` / `V33:i` | top-level vsource | saved as `"-V18:i" "A"` = **−180 µA / −330 µA** |
| `V18:1` | top-level vsource, terminal 1 | same value, unit `I` |
| `V18:current` | — | ignored: `SPECTRE-8059/8287` (`:current` is not a terminal/parameter) |
| `save i(V18)` | — | **fatal** `SFE-874`, deck does not run |
| `Ip1:i` | iprobe **inside** a subckt instance | ignored (`SPECTRE-8282`) — a device inside a subckt is not addressable bare |
| `Xcal.Ip1:i` | dotted instance path | **+180 µA / +330 µA**, unit `A` |
| `Xcal.node_mid` | dotted instance path | 0 V, as the zero-drop iprobe requires |

**Sign convention, stated explicitly because every S2 rail number below depends on it:** this build
saves the current *into* a source terminal, so a rail that delivers I amps reads as −I, and

    injected into the DUT  =  -(V18:i)  =  -(V33:i)  =  +Ip1:i (first terminal → second)

The row `CURRENT_SIGN_CONVENTION` checks that identity against the independent load-branch iprobe
(0.00018 vs 0.00018 A, 0.00033 vs 0.00033 A) instead of asserting it. **No MOS drain-current sum is
used as a supply current anywhere in this round**: the high-domain PMOS sits on source/bulk and a
switching run also moves gate, junction and displacement current, so drain sums cannot add up to the
rail. A series rail iprobe stays refused (measured in R2D1: `rc=1 stage=supply_contract`), and the
gate was not relaxed.

Attempts used: the first run failed on the temperature syntax (SFE-709), the second on two naming
mistakes of my own (an instance built as `V{name}` with `name='V18'` became `VV18`, and the load was
wrapped in a subckt whose devices are not bare-addressable). Both were diagnosed from the build's own
output before the third run; the third is the table above.

## 4. S1_FRESH_REGRESSION — PASS (new native data; historical data unchanged)

`bash scripts/sc1_s1_r2d_regression.sh` with `RUN=1 QODER_SIM_AUTHORISED=1`, frozen stimulus, frozen
4-row truth table and the shared T1..T5 window-state contract, written to the **new** file
`results/evidence/sc1_r2e_s1_regression.csv` (32 rows × 14 columns; the historical CSVs are untouched).

* truth table, all four rows PASS with the stimulus read back against its label:
  `Q=1 BLANK=0 → en=1.8 V`, `Q=0 BLANK=0 → en=5.38e-9 V`, `Q=1 BLANK=1 → en=6.47e-9 V`,
  `Q=0 BLANK=1 → en=1.04e-9 V`;
* `S1_STIMULUS_SANITY: PASS` (the clock really reached 1.8 V);
* T1..T5 contract **PASS on whole-window aggregates**, e.g. T1 `q min=1.76555`, `qbar max=0.00123537`,
  blank per-sample PWL worst deviation `1.93e-14` over 117 samples, clock 1 rise / 1 fall; T2 needs
  `blank max=0`, `q min=1.76571`, `d min=1.8`; T4/T5 `qbar min=1.79994`;
* **F1 DETECTED**: with the gate's BLANK pin tied to vss (the blank *source* keeping its PWL), the
  original T1 output assertion fails while every other T1 check still passes, so the refusal is
  attributable to the fault, not to a broken bench. The row is
  `F1_blank_clamped, signal=en, value_V=1.8001, row_verdict=DETECTED` with
  `F1_blank_clamped_setup … row_verdict=PASS`: **the fault holds `en` high, and 1.8001 V cannot satisfy
  the T1 claim `en max < 0.9 V`**. A preflight or reader failure would have been recorded as
  `FAULT_SETUP_INVALID` instead, which is not a detection.

  > Corrected in R2E1: this bullet first quoted `en max=0.0753447`, which is the *normal* T1 row's
  > value and does satisfy `< 0.9` — it cannot be the failing faulted measurement. The experiment rows
  > were not touched; only this sentence was wrong.

## 5. S2_FUNCTIONAL_TT — PASS, 6/6 static cases

New entry `scripts/sc1_r2e_s2_tt.py` (the R2D round had no execution path at all). It imports the
audited generator unchanged, adds only the two calibration-verified deck lines
(`simopt options temp=27`, `save V18:i V33:i Ven:i [Vok:i]`) plus the device terminal nodes resolved
from the frozen cell, then runs preflight full → Spectre → the audited reader/delay tools. Verdicts are
per case and per signal; `MEASURED` means a number with no defined acceptance limit, `EXPECTED_REFUSAL`
means a negative that a criterion rejected.

Whole-window plateau (min for a HIGH claim, max for a LOW claim), screening levels: output low ≤ 0.30 V,
high ≥ 3.135 V (POC_ASSUMPTION); internal nodes are judged against their own domain's 50 % level
(0.9 V / 1.65 V) and their raw values are reported either way.

| case | en | core_ok33 | enbar | x | y | **gate33** | verdict |
|---|---|---|---|---|---|---|---|
| st_c0_en_low | 0 | — | 1.800 V | 3.300 V | 6.85e-10 V | **3.300 V** | PASS |
| st_c0_en_high | 1.8 | — | 6.47e-9 V | 6.85e-10 V | 3.300 V | **4.19e-10 V** | PASS |
| st_c1_enlow_okhigh | 0 | 3.3 | 1.800 V | 3.300 V | 6.85e-10 V | **3.300 V** | PASS |
| st_c1_enhigh_okhigh | 1.8 | 3.3 | 6.47e-9 V | 6.85e-10 V | 3.300 V | **3.20e-9 V** | PASS |
| st_c1_enlow_oklow | 0 | 0 | 1.800 V | 3.300 V | 6.85e-10 V | **3.300 V** | PASS |
| st_c1_enhigh_oklow | 1.8 | 0 | 6.47e-9 V | 6.85e-10 V | 3.300 V | **3.300 V** | PASS |

Two questions the task book asked for measurement, not topology arguments:

* **can a 1.8 V-gated n33 beat the cross-coupled p33 pull-up?** Yes at TT/27 C with the frozen sizes:
  at `en=1.8 V`, `x=6.85e-10 V` and `y=3.300 V` — the low-domain driver wins both halves of the latch,
  and `gate33` follows to 4.2e-10 V (C0) / 3.2e-9 V (C1). This is a measured result at one corner, not
  a margin claim: no corner sweep was authorised this round.
* **does the guard beat a selecting core?** Yes: `st_c1_enhigh_oklow` has the core fully selected
  (x low, y high) and still puts 3.300 V on `gate33`.

Static rail currents, injected positive into the DUT (no budget defined, so `MEASURED`):
`vdd18` +21.6 pA when selecting, +31.4 pA when not; `vdd33` +5.4 pA (C0) / +3.8…8.8 pA (C1, depending
on which half of the NAND is off); the `en` source contributes ±0.5 pA at dc — consistent with a
purely capacitive gate load at a settled level.

### Finding, stated as two separate facts

**(a) What the reviewed decks asked for.** The generated line
`save en Xt.Xcore.enbar Xt.Xcore.x Xt.Xcore.y Xt.Xbuf.n1 gate33` cannot reach x and y: they are
**ports** of `sc1_ls_core_r2d` and internal nets of the top master, so this build's name for them is
`Xt.x` / `Xt.y`. It asks for `Xt.Xcore.x` and gets `WARNING (SPECTRE-8281) … Ignoring invalid item`, a
warning that does not stop the run — so the failure mode would have been a *missing reading*, quietly.
The generator's bytes stay exactly as reviewed; nothing was done about them here, and the verdict
`SAVE_PATH_AUDIT = PARTIAL` (one row per deck) is kept rather than renamed to PASS, because it is a
defect found in a reviewed artifact, not a success of this round.

**(b) What this round actually read.** The R2E decks add the names the resolver derives from the frozen
netlist (`Xt.x`, `Xt.y`, plus every device terminal node the stress rows need), and each case's
`SAVED_SIGNALS` row lists the trace names the run really wrote, so "the signal needed was present" is a
separate, checkable statement from (a). The general syntax came from measurement
(`scripts/sc1_r2e_two_level_probe.py`): hierarchical names use a **DOT** at any depth
(`Xt.x`, `Xt.Xcore.mp_drv:1`, `Xt.Xcore.mn_left sigtype=all`), while `Xt/Xcore/x`, `Xt.Xcore.mn:i`,
bare names inside a subckt and `save all` are ignored. `T10` and `T24..T26` of
`scripts/sc1_r2e_s2_selftest.py` (26/26; guest copy of this round's run in
`sc1_r2e1_s2_entry_selftest.csv`) pin the rule.

## 6. S2_REPRESENTATIVE_DYNAMIC — measured, and the wrong polarity is really refused

Delays use the audited event-attribution tool in acceptance mode, so an answer is only credited while
no further input crossing has happened; windows stop before the next input edge (249/399/549/699/849
ns) so a cycle can never borrow the next cycle's response.

| case | load | en↑→gate33↓ | en↓→gate33↑ | fall 10–90 % | rise 10–90 % |
|---|---|---|---|---|---|
| dyn_c0_rise | 1 pF | 3.053 ns | 2.861 ns | 1.196 ns (10 samples) | 3.629 ns (21 samples) |
| dyn_c0_fall | 1 pF | 3.044 ns | 2.862 ns | 1.187 ns | 3.630 ns |
| dyn_c1_rise | 1 pF | 3.429 ns | 1.945 ns | 2.031 ns | 1.855 ns |
| dyn_c1_fall | 1 pF | 3.429 ns | 1.942 ns | 2.024 ns | 1.853 ns |
| load_c0_1pF | 1 pF | 3.053 ns | not defined by the stimulus | 1.196 ns | — |
| load_c1_1pF | 1 pF | 3.429 ns | not defined by the stimulus | 2.031 ns | — |
| load_c1_5pF | 5 pF | **7.460 ns** | not defined | **9.893 ns** (49 samples) | — |
| load_c1_5pF_fine | 5 pF, maxstep 0.05 ns | **7.479 ns** | not defined | **9.892 ns** (197 samples) | — |

* repeated cycles (`dyn_c0_repeat3`, `dyn_c1_repeat3`, stop 900 ns): **12 delays, one per input edge**,
  3.053/3.047/3.042 and 2.861/2.861/2.860 ns for C0, 3.429/3.429/3.429 and 1.945/1.944/1.944 ns for C1
  — the cycle-to-cycle spread is ~10 ps, so the pairing rule is stable rather than accidental;
* the heaviest case was re-run at a quarter of the step and agrees to 0.3 % on the delay and 0.01 % on
  the edge duration, which is what "representative worst case re-checked finer" was for;
* an edge the stimulus cannot create is recorded as `EXPECTED_REFUSAL` with the reason
  (`en rises=1 falls=0 inside 1e-7..6e-7 s`), not as a circuit failure — asking the tool for a
  non-existent edge previously produced a `NO_EDGE` that looked like a defect;
* plateau: `gate33` holds 3.300 V (n=251) after the shutdown direction and settles to 6.3e-8…−6.4e-8 V
  (n=251) after the selecting direction, so both output levels are proven over a window;
* dynamic rail current peaks, injected positive: `vdd18` up to **+200.9 µA** and `vdd33` up to
  **+2.01 mA** at 1 pF, **+0.90 mA** at 5 pF — the order of magnitude of `C·dV/dt` for the loaded node,
  which is exactly why drain-current sums were not accepted as a rail measurement;
* per-device stress, from the saved D/G/S/B nodes (`sc1_r2e_vtx.py`, per-sample difference — taking the
  two node extremes separately would pair instants that never coexisted). Example at
  `st_c1_enhigh_okhigh`: `mn_left` VGS=1.8 V, VDS=6.9e-10 V; `mp_right` VGS=−3.3 V, VDS=−1.2e-9 V;
  `mn_nt`/`mn_nb` VGS=3.3 V, VDS≈1.6e-9 V. All rows are `MEASURED`, cross-checked for one device
  against the model's own exported parameter (`STRESS_CROSSCHECK … worst diff 0 V → PASS`).
  **`SOA_SIGNOFF: NO`** — these are readings, not a signoff, and no absolute rating table exists here.

**Negative that must run for real:** `neg_output_polarity_fault` (single-stage buffer, legal wiring,
wrong polarity) was simulated at TT with the normal C0 stimulus. The C0 criterion
`en(rise) → gate33(fall)` returned `NO_RESPONSE … has no complete fall output event at or after it`,
and the opposite pairing `en(rise) → gate33(rise)` answered with `delay_ns=4.015`, i.e. the wrong
polarity is really present and really refused (`NEGATIVE_POLARITY: EXPECTED_REFUSAL`, run rc 0,
preflight rc 0, reader rc 0). The `vss`-miswire and missing-`vdd33` negatives stay static-gate
refusals and were not sent to the simulator, as instructed.

---

## Explicitly not done, and not claimed

* the full 37-deck power-sequence matrix, brownout, undershoot detection, R3 chaining: **not run**;
  `core_ok33` is still a testbench high-domain assumption, not on-chip protection
  (`AUTONOMOUS_POWER_FAIL: NOT_IMPLEMENTED`);
* corners, layout, DRC/LVS/PEX, OA library changes, the full channel, S3/S4: out of scope this round;
* no power or slew budget existed, so none was invented;
* the uploaded PDK, model-card text, raw PSF, credentials and vendor paths are not in the repository
  (`SAFETY_GATE: PASS`; decks address the library as `${QODER_PDK_LIB}` from the git-ignored
  `spectre/pdk_local.env`);
* **cloud C²MOS wording correction, kept from the task book**: that report is an
  `EXTERNAL_CLOUD_REPORT / user-relayed` ngspice-42 experiment on the uploaded HSPICE/BSIM4 package —
  single-stage and **same-phase-clock** three-stage passing over TT/SS/FF/SNFP/FNSP at 1.8 V/27 °C with
  50 fF, and failing when each stage's clock is delayed by 1 ns. It is not a native Spectre result and
  it is not "non-overlapping three-stage"; the C²MOS topology is unchanged by this round.
* network: no `dhclient`, no ONBOOT/.vmx/service/license/VM-power action was taken or needed — the
  VMware Tools channel was sufficient, and the three earlier DHCP failures are recorded, not re-tried.

## Where this stops

The native TT scope of the authorisation is finished: calibration, one fresh S1 regression and the S2
minimal TT function + representative dynamics + the real polarity negative. Stopping at the
**native TT results review gate**: no power-fail matrix, no R3 chaining, no S3/S4 without a new
authorisation.
