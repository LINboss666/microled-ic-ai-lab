# SCAN-1 S3-A — the p33 high-side switch, measured on its own in the 3.3 V domain

Round: **SCAN-1S3A**, start point `b48a821a7e977a95c981a86c63430e4d796182c6` (the R3A head the cloud
pulled and reviewed as **`R3_REVIEW: PASS / GO_S3_A_3V3_CHARACTERISATION`**). Delivered batch
`run_id = S3A-20261013T160844Z`: **9 decks, 9 full preflights `rc=0`, 9 DUT runs `rc=0`, 92 result
rows + 77 DC points + 256 transient samples, 0 functional FAIL, 0 dependency BLOCKED.**

Status: **`S3_A_CHARACTERISATION: COMPLETE`** for the declared TT bias, and
**`CONDITIONAL_RON_TARGET: MET` at N=7** — where both words carry their full weight: *conditional*
because the target is the old draft's 0.10 V drop applied to an architecture-assumed 11.52 mA, and
*TT* because one section at one temperature is a characterisation point, not a signoff. `FINAL_PANEL_
VOLTAGE: NOT_DEFINED`, `LED_IV: NOT_DEFINED`, `S3_CHAIN_POWER_INTEGRATION: NOT_RUN`, `S4: NOT_STARTED`,
`SOA: NO`, `AUTONOMOUS_POWER_FAIL: NOT_IMPLEMENTED`.

## 1 Conditions, and the identity of what was actually read

| item | value | how it is known |
|---|---|---|
| process / section | `smic18mmrf_teacher`, `section=tt` | written in every deck, and the deck hash covers it |
| temperature | written `simopt options temp=27`; **read back `psf=27.0000` from all nine data headers** | the manifest column is filled from the file, not from the option line — the first version of that reader matched only `temp=` and reported `NOT_READ` (debug batch 3), which is now a verifier failure |
| model identity | lib `fc8d321752f2bacf…dcf95f`, main `…_spe.mdl 5187cae15226ffde…e7fc1`, README `f43d2585330a1cdd…d875`, and the `tt`-nested `…_mis_spe.mdl 4b62b398adee7ad6…534196` | re-hashed on the included path and stored **by hash only** in `sc1_s3a_identity.csv`; no PDK content, path or model card is committed |
| p33 geometry envelope | `lmin=3e-7`, `lmax=1e-4`, `wmin=2.2e-7`, **`wmax=1e-4`** | read back off the p33 `model` record (`lmin/lmax/wmin` on its parameter line, `wmax` on the following line) instead of repeating a reported figure — this is what the review asked for, and it confirms 100 µm as the model's own ceiling rather than a claim |
| terminal order | `(D G S B)`, `mp (d g vdd33 vdd33) p33 l= w=` | the order the accepted `sc1_level_shifter_r2d.scs` already uses, read off that file |
| rail | `vdd33 = 3.3 V` from its own independent source, `vss = 0` explicit | supply contract `vdd33=3.3 vss=0`; `SUPPLY_OK Xdev.vdd33 … SUPPLY_OK Xdev.vss … SUPPLY_RESULT PASS` in the static probe, then the full preflight in every case |
| what this is **not** | 3.3 V is `POC_ASSUMPTION`, not a VSCAN decision; there is no LED, no electrode, no R3 chain node in any deck | `S3A_ISOLATION` row per deck names the sources it found |

## 2 The nine decks, and how N was chosen

Five single-device sweeps ran first; only afterwards did the entry derive the candidate. `N` is computed
from a **measurement**, never from a formula on paper:

```
N_req = ceil(11.52 mA / I_SD(measured, largest legal W, VSD = 0.10 V)) = ceil(0.01152 / 0.00179623) = 7
N     = clamp(N_req, 1, 16) = 7          w_total = 7 x 100 um = 700 um
```

| deck | kind | shape | analysis | preflight rc | spectre rc | deck sha256 (16) | raw sha256 (16) |
|---|---|---|---|---|---|---|---|
| `s3a_on_w005` … `s3a_on_w100` | on-state DC | 1 device, `L=0.4 µm`, `W=5/10/20/50/100 µm` | `dc dev=VD param=dc start=3.3 stop=3.2 step=-0.01` | 0 | 0 | `17a715803a…` `eca27a2aaa…` `75803ea52d…` `086a72ed82…` `9458a29cf2…` | `a6ffc42e8c…` `67204d9412…` `c6a6204bf1…` `9611e5772f…` `4086d90496…` |
| `s3a_on_par` | on-state DC | **7** devices, `W=100 µm` | same bias | 0 | 0 | `eebc3251a7…` | `2881f04240…` |
| `s3a_off_par` | off-state DC | 7 devices, gate at the rail | `dc … start=3.3 stop=0 step=-0.33` | 0 | 0 | `aae0a6a31f…` | `1bcf373451…` |
| `s3a_dyn_light` | transient | 7 devices, `R=220 kΩ ∥ C=1 pF` | `tran stop=500n maxstep=0.1n` | 0 | 0 | `ae7bc0d522…` | `0ca2b36a63…` |
| `s3a_dyn_column` | transient | 7 devices, `R=286.458 Ω ∥ C=5 pF` | `tran stop=500n maxstep=0.1n` | 0 | 0 | `78a13b7348…` | `e7afb6953a…` |

Nine devices-decks is the ceiling the task set, and nine were used: nothing was deduplicated away
because `N=7 ≠ 1`, so the parallel on-state shape was genuinely new. Each deck carries its own
`subckt`, so the deck hash covers the exact device list; `S3A_DEVICE_COUNT` counts the instance lines
in the text the simulator reads (`N declared = N counted` in all nine), and **no `m=`/`nf=` multiplier
is used anywhere** — that interface was never verified on this build and inventing it would assume how
finger area and perimeter are summed.

`S3A_GEOMETRY` passes for all nine with `inside the read model range (a range, not a rating)`; no size
had to be dropped, and no model was substituted.

## 3 Single-device conductance versus W

Every row below is one measured point: `I_SD := +VD:i` (the bias instrument's own branch current) and
`Ron = (V(S) − V(D)) / I_SD` across the device's own source-drain. The `VSD = 0` point is recorded as
`NOT_DEFINED` with **no resistance written** — seven such rows, one per on-state deck.

| W (µm) | I_SD @0.01 V | @0.05 V | @0.10 V | Ron @0.01 V | Ron @0.05 V | **Ron @0.10 V** |
|---|---|---|---|---|---|---|
| 5 | 9.26218e-06 | 4.58104e-05 | 9.03754e-05 | 1079.7 | 1091.5 | **1106.5 Ω** |
| 10 | 1.8459e-05 | 9.13002e-05 | 1.80125e-04 | 541.7 | 547.6 | **555.17 Ω** |
| 20 | 3.68578e-05 | 1.82306e-04 | 3.59677e-04 | 271.3 | 274.3 | **278.03 Ω** |
| 50 | 9.2059e-05 | 4.55346e-04 | 8.98377e-04 | 108.6 | 109.8 | **111.31 Ω** |
| 100 | 1.84063e-04 | 9.10422e-04 | 1.79623e-03 | 54.33 | 54.92 | **55.672 Ω** |

What the table says, and what it does not:

* **Ron is inversely proportional to W**: at `VSD = 0.10 V` the product `W × Ron` is
  `5532.5 / 5551.7 / 5560.6 / 5565.6 / 5567.2 Ω·µm` for `W = 5 / 10 / 20 / 50 / 100 µm` — a
  **0.63 % spread across a twenty-fold width range**, i.e. `Ron ≈ 5560 Ω·µm / W`, and the ratio
  `1106.5 / 55.672 = 19.87` against a W ratio of 20. A conductance scaling, measured, with no model
  interpretation attached to it;
* the conductance is slightly **non-ohmic within each device** (Ron at 0.01 V sits 2.4–2.5 % below the
  0.10 V value on every deck), which is why the full 11-point `I–V` curve for every deck is in
  `results/evidence/sc1_s3a_dc_points.csv` rather than only the three biases quoted here;
* **sign discipline**: `max |VD:i − (−VS:i)|` over the eleven points of each deck is
  `0 … 1.2e-30 A` (largest case `1.04e-17 A` on the seven-device deck), and `VG:i` reads exactly zero on
  every DC point — so at these biases the two instruments and the gate branch are consistent to the
  reading precision. Raw signed `VD:i / VS:i / VG:i` and all seven per-device terminal currents are in
  the point table; nothing was smoothed. This is **not** a statement that the family has no bulk
  current: the accepted data-driver work measured real gate/bulk DC current in an `n33` device under a
  different bias structure, and this round neither confirms nor contradicts that.
* the device terminal reading `mp<k>:1` is **opposite in sign** to `+VD:i` on every point of every deck
  (`S3A_N_SCALING`), which is the convention this build reports; comparisons are therefore made on
  magnitudes, worst `||Σ mp:i| − |VD:i|| = 9.1e-18 A` single-finger and `6.4e-17 A` for N=7.

## 4 The candidate, and what "MET" is conditional on

| measured quantity | value | provenance of the comparison |
|---|---|---|
| single device at `VSD = 0.10 V` | `I_SD = 1.79623 mA`, `Ron = 55.672 Ω` | the largest legal W actually swept |
| `N_req` | `ceil(11.52 mA / 1.79623 mA) = 7` | from the measurement above, clamped to the declared ceiling 16 |
| candidate total at `VSD = 0.10 V` | **`12.5736 mA`**, `Ron = 7.9532 Ω` | the parallel deck's own instrument current |
| total versus `N × single` | `12.5736 mA` vs `7 × 1.79623 = 12.5736 mA`, **ratio 1.000** | both measured, in separate decks; at this bias the fingers share the current to the reading precision |
| conditional target | `Ron ≤ 8.6806 Ω` ⇒ **MET** | the old draft's 0.10 V drop divided by the architecture-assumed `768 × 15 µA` |

`S3A_CONDITIONAL_CURRENTS` records the two currents side by side on purpose: **15 µA is one selected
emitting pixel** (the teacher/user fact), and **11.52 mA only exists if one column is selected with up
to 768 pixels of it lit at once** (an architecture assumption this project has never confirmed with a
panel figure). The row also notes that 15 µA is `0.1193 %` of what the candidate carries, i.e. the light
bench load is a functional case, not a stress case. `MET` therefore means *the draft arithmetic is
satisfied at 27 °C, tt, 3.3 V, N=7, 700 µm total width* — not that a panel requirement is closed, and
not that any absolute rating has been met.

## 5 Off state, and the 3.3 V reverse bias

`S3A_OFF_STATE`: over `D = 3.3 → 0 V` with the gate at the rail, the largest branch current is
**`2.05563e-10 A` at `VSD = 3.3 V` (`VD = 0`)**, where `VGS = 0 V`, `VGD = 3.3 V`, `VDS = −3.3 V`,
`VGB = 0 V`. Eleven points, all in the point table.

Three separations the review insisted on and this table keeps: the draft's `0.1 µA per channel` is a
**reference printed next to the number, not a pass/fail** — the reading is 500× smaller only at tt/27 °C
and no high-temperature or corner leakage claim exists; the 3.3 V reverse bias is a **model experiment
condition**, not evidence about withstand capability; and `SOA_SIGNOFF` stays **NO** because no absolute
rating table was read.

## 6 The same candidate with an independent gate drive

The gate is a `pwl` instrument (`VG_WAVE`: 3.3 V off, 49→51 ns down to 0 V, 199→201 ns back up),
`stop=500 ns`, `maxstep=0.1 ns`. **`gate33` is not connected anywhere in these decks**, so nothing here
says the accepted level shifter can drive this device — that is exactly the S3-B question.

| quantity | `s3a_dyn_light` (220 kΩ ∥ 1 pF) | `s3a_dyn_column` (286.458 Ω ∥ 5 pF) |
|---|---|---|
| selected plateau (100–180 ns) | `V(D) = 3.29988 V`, device's own **`VSD = 116.07…116.14 µV`** | `V(D) = 3.21112 V`, **`VSD = 88.88 mV`** |
| load current in the plateau | `15.00 µA` (`V(D)/R`, stated as a derivation from a measured node) | `11.21 mA` |
| steady gate-current baseline, 10–40 ns | `−6.97e-16 … +6.90e-16 A` over 301 points | `−1.22e-15 … +1.21e-15 A` over 301 points |
| select edge `Q_G` (49–51 ns) | `−4.97349 pC` → **`C_eff,Q = 1.5071 pF`** | `−4.90488 pC` → **`1.4863 pF`** |
| blank edge `Q_G` (199–201 ns) | `+4.41972 pC` → `1.3393 pF` | `+4.61403 pC` → `1.3982 pF` |
| `VS:i` peak | `−17.0936 mA` at 49.9158 ns (source delivering) | `−41.8473 mA` at 50.1814 ns |
| `VG:i` peak | `+6.32935 mA` at 49.9794 ns | `+4.9384 mA` at 50.3397 ns |
| drain at the end of the run (480–500 ns) | **`1.52512 V`** (min 1.52512, max 1.61774) | `58.4 nV` |

About the last row, which is the one that gets misread: with the light load the electrode node is still
at **1.525 V when the run stops**. That is **not** evidence that the switch failed to turn off — the
plateau rows show it holding the pixel current at `VSD = 116 µV` while on, and the off-state deck shows
the branch current at 2e-10 A. Equally, it is **not** a reason to add a bleed device to the panel: the
discharge path here is a testbench resistor, and the real electrode RC is still undefined.

What the reading is **not yet** is an explained one. A bare 220 kΩ × 1 pF discharge starting from 3.3 V
over the 299 ns after the blank edge would reach `3.3·exp(-299/220) ≈ 0.848 V`, which is not what the
deck reads, so the simple `R×C` story does not account for it either: the device's own junction and
overlap charge, the coupling that happens during turn-off, and the voltage the node actually starts the
discharge from all still participate. The honest statement is that **this testbench still holds a
residual voltage with the device attached and the attribution is not complete**. S3-B measures the tail
after the real connection; nothing is auto-added here to explain it. The reading was obtained by asking
the strict reader about the delivered data file (`scripts/sc1_s3a_tail_read.py`,
`sc1_s3a_tail_readings.csv`, each row carrying the raw sha256 and the file's own last sample time
`5e-07 s`) — **no simulator was involved**.

`C_eff,Q = |Q_G| / 3.3 V` is an **equivalent charge load for this edge**, including the nonlinear and
Miller contributions of a 3.3 V gate ramp on a device that is turning on; nothing further is stacked on
top of it, so no separate "overlap capacitance" term is added. It is deliberately not called `Cgg`, and
no fixed capacitance was read out of the model. The four edges together give **1.339–1.507 pF**; the two
`select` edges alone are 1.486–1.507 pF, so a range quoted as "≈1.5 pF" describes only those two.

Scale comparison only, with each figure's own source named: the accepted R3 chain's `R3_EDGE` rows give
gate33 **10–90 % fall 2.025 ns (21 samples) on its declared 1 pF decks** and **9.893 ns fall (99
samples) / 9.040 ns rise on 5 pF**; R2E measured the same 9.893 ns for its `load_c1_5pF` case, which is
why the figure appears in two reports. Those are **edge durations**, not propagation delays — R3's
propagation rows are a different quantity from a different table (`r3_write_q1_on` at 1 pF:
`clk→gate33` 2.223 ns end-to-end, `en→gate33` 1.867 ns) — and the 1 pF / 5 pF there are artificial gate
capacitors on `gate33`, not this device. Against those edges the candidate's per-edge equivalent load of
1.339–1.507 pF sits inside the envelope the two declared loads bracket. **That is a magnitude
comparison, not a drive verification.**

## 7 Evidence, checks, and an honest batch accounting

Delivered files: `sc1_s3a_cases.csv` (92 rows), `sc1_s3a_dc_points.csv` (77), `sc1_s3a_dyn_samples.csv`
(256), `sc1_s3a_manifest.csv` (9), `sc1_s3a_identity.csv` (9), `sc1_s3a_tail_readings.csv` (8),
`sc1_s3a_dependency_log.txt` (a preflight and a runner excerpt per deck, vendor paths redacted), plus
three debug-batch logs kept because they are part of the story (§ below).

One column of `sc1_s3a_manifest.csv` is mislabelled and is **left as delivered**: the header says `W_m`
but the nine rows store the micrometre figure (5/10/20/50/100). Nothing about the devices was wrong —
`build_deck()` converts before writing `w=`, and `w_total_m` was already in metres — and the symptom was
this project's own verifier printing `W_best=1e+08 um`. The generator now writes metres under that name,
the verifier reads the width from `w_total_m / n_devices`, and
`results/evidence/sc1_s3b_s3a_manifest_correction.csv` (S3-B §2.1, written offline from the delivered
bytes) carries per row the original token, the corrected metre figure, `W_um`, `n_devices`, `w_total_m`,
and the sha256 of the deck rebuilt from that geometry — all nine rebuilt hashes equal the delivered
`deck_sha256`, so the correction is tied to the circuit that ran instead of to a sentence. The
generator's `--selftest` gained a ninth check: the manifest geometry columns are metres and
`w_total = W × N` equals the `w=` token the deck writes. The correction file is also machine-independent —
running it on the guest's Python 2.6.6 into a scratch copy
(`cadence_work/sc1_sim/s3b_offline/sc1_s3b_manifest_correction_guestcopy.csv`) produced sha256
`3878decaafc80f76a6dec8c36ed020c6c022c958ce1a63d14fc4630b49fdc198`, byte-identical to the delivered host
copy. No sample re-export was needed for the charge review: the four declared values already sit inside
the band derived from the shipped tokens (largest deviation 1.26e-16 C against a 4.45e-16 C band), so the
old 6-s.f. CSV stays as delivered.

`scripts/sc1_s3a_verify_evidence.py` parses the delivered bytes and **recomputes**: every `Ron` from the
signed columns (`checked=70, mismatches=0`), the `VSD=0` refusal, the candidate rank from the DC table
(`N_req=7`, deck ran `N=7`), column widths, finite times and values, deck/raw digest presence, and
project-relative identity paths — and, since the S3-B correction round, **each gate edge separately for
its own case**: that case's own contiguous sample block, its own declared baseline band, and its own
`raw_Q` / `net_Q` / `C_eff,Q`, compared inside a band derived from the 6-significant-figure export
propagated through the trapezoid. **59/59 PASS on Windows 3.12 and on the guest's Python 2.6.6**; the
entry's synthetic `--selftest` (9 checks: the trapezoid unit check, the `VSD=0` refusal, Ron arithmetic,
the sign cross-check, the geometry ceiling, the declared set, the edge integral, the temperature header
spelling, the manifest geometry columns) passes **9/9 in both environments**.

**Withdrawn claim, and why.** The version of that script delivered with S3-A reported "27/27 PASS" and
was quoted as having certified the four charges. It had not: it collected the `select_edge` rows of
*both* dynamic cases into one list sorted by time, integrated the mixture, and only asserted the result
was non-zero. A reviewer who edited a declared `net_Q` from `−4.97349 pC` to `−9999 pC` still got rc=0
and 27/27. The mixed figures quoted there (`−5.025 pC` / `+4.521 pC`) were aggregates of two different
decks and are removed from this report. The per-case recomputation is what §6's table now states
(`−4.97351513 / −4.90500583 / +4.41976395 / +4.61411385 pC` before the baseline each of its own rows
names, differences from the declared values of 2.5e-17…1.3e-16 C, i.e. export precision at 6 s.f.), and
`--negatives` demonstrates the two ways this could still be faked are refused: tampering one charge
declaration fails `s3a_dyn_light select_on: net_Q …`, and pasting the column case's `VG:i` samples into
the light case's block fails that block's `raw_Q` rebuild, while the delivered bytes pass.

Batch accounting, because four batches happened and only one is delivered:

| batch | outcome | why |
|---|---|---|
| 1 | 8 preflights, 7 DUT runs, then **crashed** | a tuple-index slip in the manifest row of the first dynamic deck; the crash happened before any write, so nothing was delivered and nothing was truncated. Kept as `sc1_s3a_debug_batch_log.txt` |
| 2 | 7 decks clean, **2 dynamic decks recorded `HARNESS_ERROR / BLOCKED`** | after the fix, the per-deck guard did its job: the batch finished and the two failures were reported where they happened instead of killing the run. `sc1_s3a_debug_batch2_log.txt` |
| 3 | all nine decks clean, **`temp_read_back = NOT_READ`** on every row | the reader looked for `temp=` while the psfascii header writes `"temp" 27.0000`. Physically complete, evidentially incomplete, so it was not delivered. `sc1_s3a_debug_batch3_log.txt` |
| **4** | **delivered**: `S3A_TT rows=92 … functional_FAIL=0 dependency=0`, rc 0 | every deck `preflight_rc=0`, `spectre_rc=0`, runner `PASS`, temperature read back from the data header |

Process counts, per batch, from the logs this round kept — the delivered figure and the retries are
never merged:

| batch | preflight OS-probe runs | DUT runs | note |
|---|---|---|---|
| probe (one deck, outputs redirected outside the official paths) | 1 | 1 | the first probe died earlier (`netlist_outside_project`, rc 9) and started no process |
| 1 | 8 | 7 | crashed on the eighth deck's manifest row, before its run |
| 2 | 9 | 9 | two dynamic decks recorded `HARNESS_ERROR / BLOCKED` |
| 3 | 9 | 9 | complete but `temp_read_back = NOT_READ` |
| **4, delivered** | **9** | **9** | `S3A_TT rows=92 functional_FAIL=0 dependency=0`, rc 0 |

so the delivered record is **18 Spectre processes of which nine are the preflight's own operating-point
dependency runs**, and this round issued **71 in total** across the five batches above — a sum of
preserved logs, not an estimate, and stated separately from the delivered batch.

Two refusals were demonstrated rather than asserted, on the delivered bytes and in an isolated temporary
directory: an unauthorised call prints `S3A_REFUSED …` and returns 5 **before** any evidence write, and
`--dry` without `--out` writes only into the scratch directory. `scripts/sc1_r3a_write_guard_check.py`
covers the same pattern for the R3 entry; the S3-A entry was written to that rule from the start.

## 8 What S3-B has to verify, now that the device side has numbers

The device questions this round could close: `Ron` versus W, the current one finger carries, how seven
share it, the off-state branch reading, and the charge each edge moves. The questions that remain are
all about **connection**, and none of them can be answered from an independent gate:

1. drive: does the accepted C1 level shifter still produce its measured edges with the real seven-device
   bank on `gate33` — the per-edge equivalent load measured here is **1.339–1.507 pF**, and it already
   contains the nonlinear and Miller charge of the edge that produced it, so no extra overlap-capacitance
   term is to be added to that figure; measured, not compared in scale;
2. polarity and state: `gate33 low = selected` has to hold with the electrode node present, including
   the `blank` and `core_ok33` paths with a real charge on that node;
3. the `VSD` the switch actually sees when the data driver is absorbing a column current, and what
   `V(G)` is during the transition while `V(S) = VSCAN`. The peaks measured here are **instrument
   readings of two different branches, not a current spec for the driver**: `−17.09 / −41.85 mA` is what
   the *source/body supply branch* of the high-side switch carried on the S3-A testbench, and
   `+6.33 / +4.94 mA` is what the *independent `VG` source* delivered through its own meter at the
   declared 2 ns edge. Once the real driver is connected, both the edge and the peak re-form from the
   interaction of `gate33` with the device, so neither number may be read as a minimum peak current that
   `gate33` must supply;
4. the discharged/hi-Z question the pre-design flagged: this round's 1.525 V tail is a **bench RC** whose
   precise attribution is still open (§6), so whether a real column line needs anything depends on P5
   (electrode RC) and P6 (off-state requirement), both still open;
5. the body/n-well connection as a netlist question, from the cell's own terminals — not a layout or
   LVS task, which this course excludes.

## 9 Not claimed by this round

No corner, no temperature sweep, no mismatch or Monte Carlo, no 5 V device or stack, no POR/UVLO, no
power-fail matrix, no electrode RC, no LED I–V, no array or multi-channel structure, and no
connection of this device to the R3 chain. The 3.3 V rail is a characterisation choice; the only
satisfied thing about `8.6806 Ω` is that the draft arithmetic admits it at the declared assumptions.

**Stopped at the S3-A electrical-characterisation review gate.** The candidate the data supports is
**7 × p33, L=0.4 µm, W=100 µm each (700 µm total)**; whether that becomes the S3-B chain-integration
deck is the reviewer's decision, as is the still-open P1 (`VSCAN`/`VLED`) and P2 (`Vf` or an I–V) pair
that gates any panel-level claim.

> **2026-10-14, after the review.** The cloud pulled these bytes and chose
> `GO_S3_B_3V3_CHAIN_POWER_INTEGRATION`, so the candidate above is what S3-B connects. The same review
> required three corrections to this report, and they are applied in place rather than in a new file: the
> `W_m` column of `sc1_s3a_manifest.csv` is a unit mislabel (§7), the four edge charges are now
> recomputed **per case** and the earlier "27/27 certified the charges" wording is withdrawn (§7), and the
> attribution of the branch peaks, of `C_eff,Q`, of the R2E/R3 citation and of the 1.525 V tail is
> corrected (§6, §8). Nothing else about the delivered numbers changed, and no delivered CSV was
> rewritten.
