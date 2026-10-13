# SCAN-1 R2E2 — bounded native re-verification: the calibration contract, the attribution boundary, and 15 S2 cases under the fixed gates

Repository https://github.com/LINboss666/microled-ic-ai-lab · branch `poc/scan-driver-1ch` ·
start point `b13525ca345fdef5743b19b42e68adb6f932772d` (re-read with `git ls-remote` before editing;
no unknown upstream commit). Task book:
`MicroLED_Qoder_SCAN-1R2E2_b13525c_有限原生复验.md`.

**Authorisation basis.** This continues the minimal native TT task the user authorised on 2026-10-13.
It is not a new circuit stage: two small fixes inside the new callers/extractor, the 2 calibration
cases, and the 15 S2 cases the book lists. No new model, corner, topology or operating condition was
added and R3 was not entered. Spectre really ran, in the guest (IC617 6.1.7-64b.78 + MMSIM Spectre
15.1.0.284.isr1, RHEL6.5, python 2.6.6), through the existing VMware Tools channel. No power,
snapshot, `.vmx`, licence, DHCP/NAT/service or `ONBOOT` operation was performed; guest writes stayed
inside `/root/microled_ai_project`.

**Deliverable labels.** `CALIBRATION_NATIVE_DEPENDENCIES PASS (2 cases)` · `S2_STATIC_TT PASS (6)` ·
`S2_REPRESENTATIVE_DYNAMIC PASS-with-measured-figures (6 + 2 + 1)` · `S1_REUSED_NATIVE_EVIDENCE` ·
three tool defects still `CLOSED` · `SOA_SIGNOFF NO` · `AUTONOMOUS_POWER_FAIL NOT_IMPLEMENTED` ·
`R3 / S3 / S4 NOT_STARTED`.

---

## 1 §2.1 — the calibration bench's supply contract is now read from the deck

`sc1_r2e_calibrate.py::preflight_and_run` still passed `vdd18=<volts>` / `vdd33=<volts>`, naming the
map after the **source instance**, while that bench's independent source and the `Xcal` port are both
called `rail`. The frozen supply checker therefore refused every calibration deck with
`contract entry vdd18 matches no instance port` — the refusal R2E1 later found hidden behind
`rc=0 / PASS`.

The map is now derived from the deck itself (`deck_supply_map()`): each `<V…> (<net> 0) vsource … dc=<v>`
contributes `<net>=<v>`, and the call is refused with `NO_RAIL_SOURCE_FOUND` unless the deck declares
exactly one non-zero-dc source. For these benches that yields literally `rail=1.8 vss=0` and
`rail=3.3 vss=0`. Nothing else moved: `tb_preflight.sh`, `sc1_supply_check.awk`, the real-exit-code and
single-completion-marker rules from R2E1 are unchanged and were not relaxed.

**A/B against the frozen checker, static layer only.** `PREFLIGHT_STATIC_PROBE=1` gives `rc=7` with
`CIRCUIT_VERDICT: NOT_RUN` — that is the *static* layer accepting the map, **not** a full preflight
PASS and not a circuit verdict. `rc=1` with `PREFLIGHT_REJECT: supply_contract` is the refusal R2E hit.
Transcript: `results/evidence/sc1_r2e2_static_supply_probe.txt` (real exit code captured per probe,
because a pipeline would have reported `grep`'s status instead).

| deck | map handed to the gate | real rc | what the frozen checker printed |
|---|---|---|---|
| `cal_v18_V18-i.scs` | `rail=1.8 vss=0` — derived | **7** | `SUPPLY_RESULT PASS` · `SUPPLY_GATE: PASS top=1 checked=2 supply_nets=2` · `CIRCUIT_VERDICT: NOT_RUN` |
| `cal_v18_V18-i.scs` | `vdd18=1.8 vdd33=3.3 vss=0` — R2E1 | **1** | `SUPPLY_FAIL contract entry vdd33 matches no instance port` · `PREFLIGHT_REJECT: contract_refused:…` |
| `cal_v33_V33-i.scs` | `rail=3.3 vss=0` — derived | **7** | `SUPPLY_RESULT PASS` · `SUPPLY_GATE: PASS top=1 checked=2 supply_nets=2` · `CIRCUIT_VERDICT: NOT_RUN` |
| `cal_v33_V33-i.scs` | `vdd18=3.3 vdd33=3.3 vss=0` — R2E1 | **1** | `SUPPLY_FAIL contract entry vdd33 matches no instance port` |

The two decks used for this A/B are the same files this round's calibration entry writes into
`cadence_work/sc1_sim/r2e2_cal/` (`cal_v18_V18-i.scs`, sha256 `c15d4c5a99b6d033…`, recorded as a `DECK`
row in the transcript), so the probe is reproducible without a separate deck generator: build the
decks with `--forms i`, then call `tb_preflight.sh` with `PREFLIGHT_STATIC_PROBE=1`.

**The one mock assertion the book asked for.** The preflight mock now validates the map it receives
against the deck it is given (the same rule the real checker applies), logs the exact string, and the
calibration **success control** asserts the received value:

```
ok         CAL  SIM_RUN          rc=0  PASS     PF/RS/RD=1/1/0  map='rail=1.8 vss=0'              PASS
stale_map  CAL  PREFLIGHT_FULL   rc=1  BLOCKED  PF/RS/RD=1/0/0  map='vdd18=1.8 vdd33=3.3 vss=0'   PASS
ok         S2   SIM_RUN          rc=0  PASS     PF/RS/RD=1/1/16 map='vdd18=1.8 vdd33=3.3 vss=0'    PASS
```

`stale_map` drives the pre-fix hand-written map through the same real caller: the refusal keeps its
original rc and reason, and **runner and reader are called 0 times**. S2's contract still comes from the
frozen generator (`sc1_s2_r2d_gen.contract`) and is unchanged. The list is now 13 scenarios over the
two entries with the calibration-only negative = **25 cases: 25/25 on guest python 2.6.6 and on
Windows python 3.12** (`results/evidence/sc1_r2e2_callpath_selftest.csv`). The matrix was not otherwise
widened.

The entry keeps its authorisation gate (`RUN=1` **and** `QODER_SIM_AUTHORISED=1`, otherwise
`CALIBRATION_BENCH … NOT_RUN` and rc 5) and `--forms i` restricts this round to the adopted
`save <source>:i` form — `:1`, `:current` and `save i(V18)` were not re-probed, and no second executor
was written: the same `preflight_and_run` path was exercised.

## 2 §2.2 — the repeat3 next boundary is a real 50 % crossing

R2E1's extractor looked for the first **sample** later than `t_in` and called it the next boundary, so
the first C0 answer recorded `next=102.013852 ns` — the owning edge's own right-hand sample — where the
audited `sc1_delay.py` uses 252 ns. Fixed in the new extraction layer
(`scripts/sc1_r2e1_reread.py`); `sc1_delay.py` and every other audited tool stay byte-identical.

* `crossing_times()` returns every crossing of the input level in **either direction**, interpolated
  between its two samples, under the audited tool's own three rules (a sample exactly on the level is
  credited when **reached**, so a left-hand plateau is skipped; a right-hand exact level is taken at
  that sample time; anything strictly between is linearly interpolated).
* `owning_crossing()` takes the crossing the answer belongs to — matched on the crossing itself with a
  tolerance of one step of the printed 6-significant-digit `t_in`, not on the rounded number — and
  returns the crossing after it. Where no later input edge exists the field is `END_OF_DATA`; a
  boundary is never invented.
* Segments are addressed by the crossing's own sample index, not by "nearest sample to `t_in`".
* Corrected output: **`results/evidence/sc1_r2e2_waveform_samples.csv`** — 217 rows
  (205 `MEASURED_SAMPLE` + 12 boundary rows), 0 refused. `sc1_r2e1_waveform_samples.csv` keeps R2E1's
  rows exactly as delivered.
* C0 fall band labels corrected: `2.97 V` is the **90 %** high end and `0.33 V` the **10 %** low end of
  a 90→10 falling edge. The sampled digits themselves are unchanged.
* The 5 pF decks now carry their **own** input 50 % neighbourhood, read from their own raws; the 1 pF
  deck's 102 ns value is not borrowed. The direction asked of each deck comes from the waveform
  (`any`): that stimulus only rises, so asking it for a fall was a question error, not a circuit fact,
  and it is no longer reported as a refusal.

The 12 attributed answers, printed by the extractor and stored as their own rows:

| case | t_in (s) | t_out (s) | t_next (s) | `t_in <= t_out < t_next` |
|---|---|---|---|---|
| dyn_c0_repeat3 | 1.02e-07 | 1.050534e-07 | 2.52e-07 | HOLDS |
| dyn_c0_repeat3 | 2.52e-07 | 2.548614e-07 | 4.02e-07 | HOLDS |
| dyn_c0_repeat3 | 4.02e-07 | 4.050469e-07 | 5.52e-07 | HOLDS |
| dyn_c0_repeat3 | 5.52e-07 | 5.548612e-07 | 7.02e-07 | HOLDS |
| dyn_c0_repeat3 | 7.02e-07 | 7.050418e-07 | 8.52e-07 | HOLDS |
| dyn_c0_repeat3 | 8.52e-07 | 8.548599e-07 | **END_OF_DATA** | HOLDS (no later input edge in this data) |
| dyn_c1_repeat3 | 1.02e-07 | 1.054287e-07 | 2.52e-07 | HOLDS |
| dyn_c1_repeat3 | 2.52e-07 | 2.539445e-07 | 4.02e-07 | HOLDS |
| dyn_c1_repeat3 | 4.02e-07 | 4.054286e-07 | 5.52e-07 | HOLDS |
| dyn_c1_repeat3 | 5.52e-07 | 5.539445e-07 | 7.02e-07 | HOLDS |
| dyn_c1_repeat3 | 7.02e-07 | 7.054286e-07 | 8.52e-07 | HOLDS |
| dyn_c1_repeat3 | 8.52e-07 | 8.539445e-07 | **END_OF_DATA** | HOLDS (no later input edge in this data) |

`t_out − t_in` for these rows is the delay the reviewer recomputed independently (3.053429 / 2.861506 /
3.428708 / 1.942310 ns), so the sampled evidence and the audited attribution now agree.

One bounded offline case guards the rule: `--what boundary` →
`results/evidence/sc1_r2e2_boundary_selftest.csv`, **6/6 PASS on both environments**. Its expectations
are built by hand on a 7-point fragment rather than by calling the code under test again, covering the
exact R2E1 shape (owning crossing 201 ns whose right-hand sample is 202 ns must yield the interpolated
**275 ns**, not 202 ns), the both-direction list (201 / 275 / 375 ns), the `END_OF_DATA` tail, and a
`t_in` before the first edge.

## 3 §1 — the 17-vs-15 correction

The five R2E S2 manifests really hold **17** case rows: static 6 + basic dynamic 4 + repeat3 2 + load
4 + polarity negative 1 (read back from the delivered files). The "15" that
`reports/scan_driver_r2e1_gate_review.md`, `reports/scan_driver_r2e_native_tt.md` §correction block and
this checkpoint repeated was a counting error and is corrected in place. This round re-runs **15** of
those 17: `load_c0_1pF` and `load_c1_1pF` overlap the 1 pF basic dynamic decks and stay as historical
readings, and the 37-deck power-sequence matrix was not run.

## 4 §3 — the bounded native run: 2 calibration cases + 15 S2 cases

New scratch only (`cadence_work/sc1_sim/r2e2_cal`, `r2e2_s2_static`, `r2e2_s2_dynamic`,
`r2e2_s2_load`, `r2e2_s2_negative`), new decks, new logs, new CSVs, all under `sc1_r2e2_*`; no R2E or
R2E1 deck, raw or CSV was overwritten. Model cards, PDK, geometry, connections and stimulus untouched;
rails stay direct `vsources` (no rail iprobe, no MOS drain sum); temperature stays
`simopt options temp=27`, read back from the produced files. Order: calibration → 6 static → dynamic →
load → negative.

### 4.1 how many processes actually ran (the dependency count is not hidden)

`scripts/sc1_r2e2_transcript.py` (offline, no simulation) pairs this round's recorded exit codes with
the artifacts each process left in its own directory:
`results/evidence/sc1_r2e2_dependency_transcript.csv`, **102 rows, every one `PRESENT`**:

| kind | rows | what it is |
|---|---|---|
| `DECK` | 17 | the deck this round wrote, with its sha256 and `section=tt` |
| `PREFLIGHT_DEPENDENCY_RUN` | **17** | `tb_preflight.sh` FULL mode's own operating-point analysis — a dependency of the gate, **not** a DUT measurement |
| `DUT_RUN` | **17** | the runner pass over the DUT/bench deck: the `temp =` line and `spectre completes with 0 errors …` read back from that log |
| `DUT_DATA` | 17 | the psfascii this run produced: header `temp`, trace count, sha256 |
| `RECORDED_RC` | 34 | the round's own `PREFLIGHT_FULL` and `SIM_RUN` rows (preflight rc / runner rc / spectre rc / `error_hits` / PASS-line count) |

So this round is **17 dependency simulations + 17 DUT runs = 34 Spectre invocations**, counted from the
files on disk rather than asserted from code. Claiming "preflight full passed" therefore no longer
hides an operating-point analysis, and no "zero simulations" claim appears anywhere.

### 4.2 `CALIBRATION_NATIVE_DEPENDENCIES` — 2 cases, `sc1_r2e2_calibration.csv` (31 rows, entry rc 0)

| item | V18 bench | V33 bench |
|---|---|---|
| `PREFLIGHT_FULL` | **rc=0 PASS**, `map=rail=1.8 vss=0 (V18 on rail)` | **rc=0 PASS**, `map=rail=3.3 vss=0 (V33 on rail)` |
| `SIM_RUN` | `runner_rc=0 preflight_rc=0 spectre_rc=0 error_hits=0 pass_lines=1` | same |
| `TEMP_CONFIRMATION` | log `temp=27`, psf header `temp=27.0000` | same |
| `SOURCE_CURRENT_CALIBRATION` | saved `−0.00018 A` ⇒ injected `+0.00018 A` | saved `−0.00033 A` ⇒ injected `+0.00033 A` |
| `BRANCH_PROBE_CALIBRATION` (`Xcal.Ip1:i`) | `+0.00018 A` | `+0.00033 A` |
| `HIERARCHICAL_NODE_READ` (`Xcal.node_mid`) | `0 V` (zero-drop iprobe) | `0 V` |
| `SAVE_FORM_BARE_INSIDE_SUBCKT` (`Ip1:i`) | `NO_SIGNAL`, reader rc 3 → `EXPECTED_REFUSAL` (measured negative kept) | same |
| `CURRENT_SIGN_CONVENTION` | `0.00018 vs 0.00018 A` PASS | `0.00033 vs 0.00033 A` PASS |

The calibration bench's **full** preflight passing is new: under R2E the same six calls were refusals.
The injected/reading sign convention is confirmed a second time natively, on both rails, against the
independent load-branch iprobe rather than a drain-current sum.

Read-only identity rows, re-hashed from the path the deck actually includes: lib
`fc8d321752f2bacf…` **MATCH**, `ms018_enhanced_v1p2_rev0_spe.mdl` `5187cae15226…` **MATCH**,
`…_readme_spe.txt` `f43d2585330a1cdd…` **MATCH**, and `section tt`'s nested include
`ms018_enhanced_v1p2_rev0_mis_spe.mdl = 4b62b398adee…` — the mis model TT really loads. Geometry rows
(`MODEL_RECORD_SOURCE` n18 line 53 / p18 line 258 / n33 line 654 / p33 line 866 and the four
`GEOMETRY_RANGE_READ` verdicts) unchanged. `CHARACTERISATION_RANGE` still only supports
`-40 C ~ 125 C`; there is still no absolute-rating table, so `SOA_SIGNOFF` stays **NO**.

### 4.3 `S2_STATIC_TT` — 6 cases, `sc1_r2e2_s2_static.csv` (110 rows) + manifest 6 cases

All six decks: `PREFLIGHT_FULL rc=0 PASS` with exactly one completion marker,
`SIM_RUN runner_rc=0 spectre_rc=0 error_hits=0 pass_lines=1`, `SAVED_SIGNALS PASS`; entry exit **0**
with `functional_FAIL=0 dependency=0 informational=6`.

| case | gate33 whole window | `Xt.x` / `Xt.y` | `Xt.Xcore.enbar` | verdict |
|---|---|---|---|---|
| `st_c0_en_low` | 3.3 … 3.3 V | 3.3 / 6.85e-10 V | 1.8 V | PASS |
| `st_c0_en_high` | 4.18812e-10 … 4.18813e-10 V | 6.85e-10 / 3.3 V | 6.47e-9 V | PASS |
| `st_c1_enlow_okhigh` | 3.3 … 3.3 V | 3.3 / 6.85e-10 V | 1.8 V | PASS |
| `st_c1_enhigh_okhigh` | 3.20036e-09 … 3.20036e-09 V | 6.85e-10 / 3.3 V | 6.47e-9 V | PASS |
| `st_c1_enlow_oklow` | 3.3 … 3.3 V | 3.3 / 6.85e-10 V | 1.8 V | PASS |
| `st_c1_enhigh_oklow` | 3.3 … 3.3 V | 6.85e-10 / 3.3 V | 6.47e-9 V | PASS |

HIGH states satisfy `min ≥ 3.135 V`, LOW states `max ≤ 0.30 V` (both still `POC_ASSUMPTION`: the final
VSCAN level is not defined yet), and the internal nodes are judged at their own domain 50 % (0.9 V for
the 1.8 V logic, 1.65 V for the 3.3 V gate). `en` / `core_ok` read back at their driven levels
(`S2_STIMULUS_READBACK`). Rail currents stay `MEASURED` — `S2_RAIL_CURRENT` is never compared against a
budget because no power or edge budget exists yet, and `injected = −(Vsource:i)` is the calibrated rule
from §4.2.

Per-device stress was re-measured in the same case windows: 30 `DEVICE_STRESS_PEAKS` rows (10 devices on
each of the two selecting static decks, 10 on the 5 pF load deck) and 3 `STRESS_CROSSCHECK` rows, where
the model's own exported `:vgs` and the node difference agree to **worst diff 0 V**. The 5 pF deck again
shows the load-driven overshoot (`mp_left`/`mp_na` VGS down to −3.4715 V, gate33 excursion giving VGD up
to 3.34536 V) — measured, recorded, and **not** turned into a rating statement.

### 4.4 `S2_REPRESENTATIVE_DYNAMIC` — 6 dynamic + 2 load + 1 negative cases

| group | file | rows | manifest | entry exit |
|---|---|---|---|---|
| dynamic: 4 basic both-direction + `dyn_c0_repeat3` + `dyn_c1_repeat3` | `sc1_r2e2_s2_dynamic.csv` | 89 | 6 cases, all `preflight_rc=0 spectre_rc=0 PASS` | **0** (`functional_FAIL=0 dependency=0 informational=27`) |
| load: `load_c1_5pF`, `load_c1_5pF_fine` (`maxstep=0.05 ns`) | `sc1_r2e2_s2_load.csv` | 38 | 2 cases, same rcs | **0** |
| negative: `neg_output_polarity_fault` | `sc1_r2e2_s2_negative.csv` | 11 | 1 case, same rcs | **0** |

Representative figures, all `MEASURED` with `budget NOT_DEFINED`:

* C0: `en(rise)→gate33(fall)` **3.053 ns**, `en(fall)→gate33(rise)` **2.861 ns** (`t_in=1.02e-07`,
  `t_out=1.050534e-07`); C1 guarded: **3.429 ns** / **1.945 ns**.
* `repeat3`: 6 attributed answers per case at 100/250/400/550/700/850 ns, C0 3.053 → 3.042 ns and C1
  3.429 / 1.945 → 1.944 ns across the cycles, each inside its own `[t_in, t_next)` window (§2), with the
  10-90 % edge rows and the last-quarter plateau satisfied.
* 5 pF worst representative: `en(rise)→gate33(fall)` **7.460 ns** coarse (`t_out=1.094596e-07`) and
  **7.479 ns** at `maxstep=0.05 ns` (`t_out=1.094791e-07`) — a 19 ps step effect, so the coarse deck
  resolves the same edge; the plateau over the last quarter settles at 3.9e-9 … 5.1e-9 V (coarse,
  n=625) and 2.2e-9 … 4.3e-9 V (fine, n=2500).
* The load decks' `gate33 rise` edge rows are `EXPECTED_REFUSAL`: that stimulus only rises, so a rise is
  not defined by it. That is a scope fact about the question, not a circuit failure, and the entry now
  derives the requested edge directions from the stimulus instead of assuming both.
* The negative is still a real negative: the normal C0 criterion refuses the faulted deck
  (`NO_RESPONSE en event 1 (t_in=1.020000e-07) has no complete fall output event`) while the opposite
  pairing answers `en(rise)→gate33(rise)` with `t_out=1.060154e-07`, **4.015 ns**, and
  `NEGATIVE_POLARITY` records `EXPECTED_REFUSAL`. A reader or preflight failure is never counted as a
  detection; here the refusal came from the waveform.

### 4.5 did it reproduce R2E's own numbers? (the point of a re-verification)

`scripts/sc1_r2e2_reproduce_compare.py` (offline; joins the two rounds' evidence on
item + case + signal/target and compares the printed digits) writes
`results/evidence/sc1_r2e2_native_reproduction.csv`, 213 rows:

```
EXACT=194   ONLY_R2E=19   ONLY_R2E2=0   SAME=0   TEXT=0   DIFFERS=0
```

Every value both rounds asked for is **digit-for-digit identical**: 30 `DEVICE_STRESS_PEAKS`, 3
`STRESS_CROSSCHECK`, 54 `S2_RAIL_CURRENT`, 24 `S2_DELAY` (including all 12 `repeat3`
`t_in / t_out / delay_ns` triples), 16 `S2_EDGE`, 8 `S2_PLATEAU`, 24 `S2_FUNCTIONAL_TT`, 10
`S2_STIMULUS_READBACK`, and the calibration currents, geometry and model rows. The 19 rows that only
R2E has are exactly the two deliberately-not-re-run 1 pF load decks (15 rows) and the two extra save
forms `:1` / `:current` (4 rows). No old row was edited to make this true.

## 5 §4 — exit semantics: three classes instead of one rc

`sc1_r2e_s2_tt.py::classify()` now splits the summary —

* **functional** `FAIL` → the circuit did not do what the case asserts;
* **dependency** `BLOCKED` / `NOT_AVAILABLE` / any other `PARTIAL` → the process or the data did not
  arrive, so nothing about the circuit may be judged (`SAVED_SIGNALS` with an empty trace list moved
  from `PARTIAL` to `NOT_AVAILABLE` for exactly this reason, and `DECK_BUILD UNKNOWN_CASE` likewise);
* **informational** → `SAVE_PATH_AUDIT PARTIAL`, `MEASURED`, `EXPECTED_REFUSAL`, `NOT_A_NUMBER`:
  printed with their own count, never renamed to PASS.

Exit is `0` only with neither failure type; `1` functional, `2` dependency, `3` both, `5` unauthorised
or unresolved model binding, `9` a bad selection. All four groups exited **0** while still printing
their six per-case `SAVE_PATH_AUDIT PARTIAL` rows. Those rows are the reviewed generator's
`Xt.Xcore.x` / `Xt.Xcore.y` save requests — `x`/`y` are **ports** of `Xcore`, so this build never saves
that spelling; the resolved names `Xt.x` / `Xt.y` were saved and judged in the same runs (see the
`S2_FUNCTIONAL_TT` rows above). The generator's bytes stay untouched, the warning stays visible, and
the main entry no longer reports rc=1 because of it, nor does it ignore real non-zero codes.

Two guards were added so a "finished" run cannot be an empty run: `--only` with an id the group does
not offer is refused (`UNKNOWN_CASE …`, rc 9) instead of dropping silently, and `--expect N` fails
(`SELECTION_COUNT`, rc 9) unless exactly N decks are selected. This round's four invocations used
`--expect 6 / 6 / 2 / 1` and the four manifests hold exactly 6, 6, 2, 1 case rows — 15 in total, each
with its own deck sha256, `preflight_rc`, `spectre_rc` and verdict.

## 6 the R2E preflight columns, restated

The calibration `PREFLIGHT_FULL` rows and the 17 S2 `preflight_rc` columns of the R2E round stay
**void** (read as unrecorded, never as 0): they were `| tail` statuses, and the retained excerpt stops
before the completion marker. What this round supplies is the missing effective native record —
`preflight_rc`, the single `TESTBENCH_PREFLIGHT` marker, `runner_rc`, `spectre_rc`, `error_hits` and the
data/log identity per case — under the fixed entry, with the R2E numbers reproduced exactly (§4.5).

## 7 `S1_REUSED_NATIVE_EVIDENCE`

S1 was **not** re-run and this report makes no fresh-S1 claim. The R2E1 fixes touched only the two new
callers and `sc1_r2e_vtx.py`; the independent S1 entry, its state contract and the shared window
contract are unchanged (`git diff --name-only b13525c HEAD` over the protected list → 0 files), so
R2E's fresh native S1 regression (32 × 14 rows, F1 `DETECTED` at `en = 1.8001 V`) stays this project's
S1 evidence.

## 8 offline suites, in both environments

| suite | cases | guest python 2.6.6 | Windows python 3.12 | artifact |
|---|---|---|---|---|
| call-path (isolated mocks, `SYNTHETIC_MOCK_NOT_A_CIRCUIT_RUN`) | 25 | **25/25** | **25/25** | `sc1_r2e2_callpath_selftest.csv` |
| S2 entry deck/measurement self test | 26 | **26/26** | **26/26** | `sc1_r2e2_s2_entry_selftest.csv` |
| strict voltage-difference tool | 16 | **16/16** | **16/16** | `sc1_r2e_vtx.py --selftest` (output quoted in the round log) |
| next-boundary rule | 6 | **6/6** | **6/6** | `sc1_r2e2_boundary_selftest.csv` |

Mock and offline results are never presented as circuit verdicts. Native runs are guest-only (Windows
has no Spectre), and that limitation is stated rather than glossed. The scripts that produced this
round's evidence are byte-identical on both sides (LF-normalised md5 compared for
`sc1_r2e_calibrate.py`, `sc1_r2e_s2_tt.py`, `sc1_r2e1_reread.py`, `sc1_r2e1_callpath_selftest.py`,
`sc1_r2e2_transcript.py`, `sc1_r2e2_reproduce_compare.py` → all MATCH); `sc1_r2e_manifest.py` and the
reproduction comparison run on the Windows side.

## 9 what this round does **not** claim

* `SOA_SIGNOFF **NO**` — measuring VGS/VGD/VDS/VGB per device again is not knowledge of an absolute
  rating; the readable PDK files still contain no rating table, only the `-40..125 C` characterisation
  range and model/bin geometry limits.
* `AUTONOMOUS_POWER_FAIL NOT_IMPLEMENTED`; the 37-deck power-sequence matrix was not run.
* Final `VSCAN`, the real panel load, LED `Vf`, and the power / edge / skew budgets remain **undefined**;
  dynamic figures are `MEASURED` against `budget NOT_DEFINED`, and the 1.8/3.3 V rails, TT/27 °C and
  1 pF/5 pF loads are `POC_ASSUMPTION`. The course's 15 µA single-pixel current was nowhere treated as a
  scan-electrode total.
* The sampled waveforms prove the segments they contain, not the whole raw; the 123-row R2E1 stress
  re-read stays a re-read of recorded data, and this round's 30 stress rows are new native measurements
  in the same windows.
* The `SAVE_PATH_AUDIT PARTIAL` rows and the generator's old save spelling are kept as they are; no
  verdict was renamed to improve a summary, and no size or topology was touched to manufacture a PASS.
* The C²MOS three-level skew question, Virtuoso schematic/symbol work, corners and layout are outside
  this round. The reviewer's own cloud numbers stay `EXTERNAL_CLOUD_REPORT`.

## 10 delivery, gates and stop point

Added: this report; `scripts/sc1_r2e2_transcript.py`, `scripts/sc1_r2e2_reproduce_compare.py`;
evidence `sc1_r2e2_calibration.csv` (+ `_log.txt`), `sc1_r2e2_s2_{static,dynamic,load,negative}.csv`
with their four `_manifest.csv`, `sc1_r2e2_callpath_selftest.csv`, `sc1_r2e2_s2_entry_selftest.csv`,
`sc1_r2e2_boundary_selftest.csv`, `sc1_r2e2_waveform_samples.csv`,
`sc1_r2e2_static_supply_probe.txt`, `sc1_r2e2_dependency_transcript.csv`,
`sc1_r2e2_native_reproduction.csv`.
Modified: `scripts/sc1_r2e_calibrate.py`, `scripts/sc1_r2e_s2_tt.py`, `scripts/sc1_r2e1_reread.py`,
`scripts/sc1_r2e1_callpath_selftest.py`, `scripts/sc1_r2e_manifest.py` (roles), the R2E1 report and the
R2E report's count statement, and `reports/agent_handoffs/SCAN-1.md` — the single CURRENT_STATUS moves
to R2E2 and the R2E1 block is demoted to history with a pointer listing what this round resolved.

Decks, raw PSF, PDK and model text, credentials, licence values and vendor paths are not committed; the
deck hashes and project-relative paths are carried in the manifests and in
`sc1_r2e2_dependency_transcript.csv` instead. One disclosure: the `PREFLIGHT_FULL` excerpt column keeps
the deck path exactly as the entry wrote it, and that prefix is this project's own VM directory
(`/root/microled_ai_project/…`), not a vendor location — earlier committed evidence
(`sc1_r2a_preflight.csv`, `sc1_r2e_s1_regression.csv`) already carries the same prefix, so the recorded
rows were left untouched rather than edited after the fact; the new transcript redacts it.

Gates: protected inputs (`spectre/`, C²MOS, `sc1_read_psf.py`, `sc1_delay.py`, `tb_preflight.sh`,
`sc1_supply_check.awk`, `run_spectre.sh`, the old S1/S2 entries, the S1 window contract, the frozen
generator) → **0 files changed** vs `b13525c`; every R2E/R2E1 evidence CSV → unchanged;
`scripts/provenance_check.py` → `SOURCE_PROVENANCE_CHECK: PASS` (447 files, 465 labelled lines, 0
violations); `scripts/netlist_stats.py` → `DEVICE_COUNT_CHECK: PASS`; the frozen S2 cell's 10-device
count per variant is what the entry's `CONNECTIVITY_RESOLVED` rows read back;
`results/evidence/sc1_r2e_manifest.csv` regenerated with the `r2e2_*` roles (63 rows);
`scripts/precommit_safety_check.py` runs as the git hook at commit, with no `--no-verify`, no force, no
history rewrite and no teammate-branch content.

**Stopped at the native TT results review gate.** The next decision belongs to the user: if the
effective native records and the functional judgements are accepted, the stage to open is
**R3 — control-chain chaining together with the scan output stage design** — not further general tool
engineering, and nothing advances automatically.
