# SCAN-1R2D2 — one S1 window-state contract, both entry points (no simulation)

Date 2026-10-13. Start point re-read before editing: `poc/scan-driver-1ch` =
`c05042779f23151eaa9d5fd83d0c4917269ba36c` (local HEAD and remote agreed), main =
`23e471cb936b421ee97e1250c3be06edf96f9937`.

**No simulator was called.** No Spectre, no ngspice, no preflight full, no operating-point probe, no
Virtuoso, no C²MOS run, no new-PDK run. The only gate used is `PREFLIGHT_STATIC_PROBE=1`, and this
round did not even need it. The pause on real-circuit simulation stays in force; the network
question is treated separately in §6.

Two things were actually open after R2D1 and both are closed here. Neither is a circuit result.

---

## 1. The hole, in the reviewer's own numbers

* **A (future entry).** Building on `sc1_r2d1_entry_selftest.good_values()` and setting only
  `table[('raw_tran','win=520n..620n:max','blank')]='1.8'`, the entry still reported
  `T2_states ... row_verdict=PASS` and `S1_R2D_REGRESSION: PASS` at rc 0 — while T2 is defined as
  *BLANK=0 while Q=1*. The states row only asked whether a signal **could be read**.
* **C (historical re-analysis).** With `build_tree(decks=True, history=True)` and the normal
  `s1r_dff.raw/sw1.tran.tran` mutated so that **blank is 1.8 V at t=410 ns and 0 V at every other
  sample**, everything else intact, the script returned rc 0 with `CERTIFIED rows=10
  certified_rows=10 failing=0` and T1/T3 stimulus PASS. A high state had been judged with the window
  **maximum** and a low state with the **minimum**, which proves only that a value appeared once;
  T3 never looked for the release at all.

Both were reproduced locally before being fixed, and both are now cases in the self-tests. Neither
reproduction says the historical data is wrong — it says the certification condition could let a
wrong stimulus through.

## 2. The shared contract — `scripts/sc1_s1_window_contract.py`

One module holds the rule; the bash entry calls it and the re-analysis imports it, so the same
meaning cannot be written twice again. Judgement only: it reads through the audited
`sc1_read_psf.py` and two small awk passes tied to this frozen stimulus. Nothing in
`sc1_read_psf.py`, `sc1_delay.py`, `tb_preflight.sh` or `sc1_supply_check.awk` was touched.

| window | output assertion (unchanged threshold) | states that must hold **across the whole window** | blank | clock |
|---|---|---|---|---|
| T1 400..455 n | `en(max) < 0.9 V` | Q high (window **minimum**), qbar low (window **maximum**) | every sample compared with the frozen PWL: 1.8 V to 450 n, ramping to 0 V by 460 n, nominally 0.9 V at 455 n — so the whole window is never demanded to be 1.8 V and one high sample never stands for the window | ≥1 rising edge (the 450 n edge that causes the transfer) |
| T2 520..620 n | `en(min) > 0.9 V` | blank low, Q high, qbar low, **d high** | (constant low: covered by the state maximum) | ≥1 rise and ≥1 fall |
| T3 410..520 n | `q(min) > 0.9 V` | qbar low | **the release itself**, sample by sample: high before 450 n, ramping, 0 V after 460 n | ≥1 rise and ≥1 fall |
| T4 700..860 n | `en(max) < 0.9 V` | blank low, **d low**, Q low, qbar high | (constant low) | ≥1 rise and ≥1 fall |
| T5 700..860 n | `q(max) < 0.9 V` | blank low, qbar high | (constant low) | ≥1 rise and ≥1 fall |

Provenance of every number used: `VOL = 0.9 V` is the historical decision level from
`scripts/sc1_s1r.sh`, kept verbatim, and high/low are strict `>` / `<` against it — the same sign
convention as the historical `gt`/`lt` assertions. The PWL breakpoints (blank, data, the clock's
delay/period/width) are copied from the same file (`HISTORICAL_STIMULUS`). `PWL_TOL = 0.09 V` is a
`POC_ASSUMPTION`: half of one 1 ns sample step of the 1.8 V over 10 ns release ramp at
`maxstep=1n`; it is 5 % of the swing, far from the 0.9 V threshold, and still 20× smaller than the
1.8 V error a missing release edge produces. A missing signal is not a threshold question: the real
reader exit code is recorded (3 no-signal, 4 too-few-samples, 5 bad number) and the check fails.

The clock is deliberately **not** required to be constant in any window — the historical stimulus
toggles every 100 ns — so the contract counts real crossings of the decision level instead of
accepting "it was high once".

F1 (the negative) now checks what makes it the fault: the deck text must tie the **gate's BLANK pin**
to `vss` while the **blank source** keeps its PWL, then the whole T1 contract is re-evaluated on the
faulted data — Q must hold 1 across 400..455 n and blank must still follow the ramp. Only if all of
that holds does a rejected T1 output assertion mean `DETECTED`; a T1 that passes is
`CHECKER_TOOTHLESS` (a failure), and a bench whose states do not match is
`DETECTED_BUT_SETUP_INVALID` (also a failure, and it says so rather than claiming a catch).

## 3. A — the future entry (`scripts/sc1_s1_r2d_regression.sh`)

The `Tn_states` rows are gone, replaced by one contract row per check (`T2_state_throughout_blank`,
`T3_stimulus_pwl_blank`, `T2_stimulus_clock_clk`, ...) written into the same CSV, each with the rule,
the measured value or violation count, the reader's real exit code and its own verdict; any failing
row sets `fail=1`. Six extra fields per window are now asserted instead of "readable".

Fixed along the way, all of it found by the local mocks rather than assumed:

* the entry wrote reader exit code `1` into its `READ_FAIL` row whatever the reader actually said —
  it now carries `READ_RC` from the real process (the reviewer's rule: do not flatten 3/4 to 1);
* the contract's rows were consumed with a `while read` loop, and Python on a Windows host wrote
  `\r\n`, which pushed a carriage return into the last field and made the CSV writer reject a row as
  13-field — the module now writes to the binary stream and the entry strips CR without hiding the
  exit code;
* `clk_check`'s failure path was `return 'FAIL', ('text' % args, fields)`, i.e. a **2-tuple**, so any
  clock failure raised `ValueError` inside the contract and the entry silently lost every window row
  (measured: rows dropped from 32 to 7 with rc 6); parentheses removed, case added;
* counting "other failing checks" picked up the report's own `WINDOW_CONTRACT T1 FAIL` summary line
  and made every negative look like a broken setup; the parsers now require `NF==7`;
* with the synthetic data sampled every 10 ns, the 450..460 ns ramp fell between samples and T1's PWL
  check had nothing to compare — the generator now samples at 1 ns, matching `maxstep=1n`, which is
  how the historical raw is built. A 10 ns grid could not see the release at all: reported rather
  than hidden.

## 4. C — the historical re-analysis (`scripts/sc1_r2d_s1_reanalysis.py`)

Its own `WINDOWS` table now carries only the id and the historical labels; the criteria come from the
shared module. The row keeps the four separations the review asked for and adds the contract's detail
into `signals_read_back`, so `assertion_verdict`, `stimulus_check`, `traceability` and
`historical_difference_V` stay different columns and a state failure can never be softened into
`PARTIAL`.

Measured on the **local** original data (raws `cadence_work/sc1_sim/sim/s1r_*.raw`, decks
`cadence_work/sc1_sim/s1r_*.scs`, history `s1r_truth.csv` / `s1r_transient.csv` — local bytes only,
the cloud reviewer has none of them):

| row | measured | n | assertion | **whole-window stimulus check** |
|---|---|---|---|---|
| Q1 BLANK0 | 1.8 V | 1 | PASS | blank 0 V, qbar 0 V as labelled |
| Q0 BLANK0 | 5.38288e-09 V | 1 | PASS | PASS |
| Q1 BLANK1 | 6.47156e-09 V | 1 | PASS | blank 1.8 V, qbar 0 V as labelled |
| Q0 BLANK1 | 1.03846e-09 V | 1 | PASS | PASS |
| T1 | en max 0.0753447 V | 117 | PASS | q **min 1.76555 V** high, qbar max 0.00123537 V low, blank matches the PWL over 117 samples (worst diff 1.93e-14), 1 rise / 1 fall |
| T2 | en min 1.79991 V | 157 | PASS | blank **max 0 V** low, q min 1.76571 V, qbar max 0.00119452 V, d min 1.8 V, 1 rise / 1 fall |
| T3 | q min 1.76555 V | 192 | PASS | qbar max 0.00282008 V low, **blank release verified sample by sample** (192 samples, worst diff 1.93e-14), 1 rise / 1 fall |
| T4 | en max 3.66477e-06 V | 275 | PASS | blank max 0 V, d max 0 V, q max 0.00200669 V, qbar min 1.79994 V, 2 rises / 2 falls |
| T5 | q max 0.00200669 V | 275 | PASS | blank max 0 V, qbar min 1.79994 V, 2 rises / 2 falls |
| F1 | en max 1.8001 V | 116 | **DETECTED** | gate BLANK pin tied to vss = YES, blank source still the PWL = PWL_KEPT, q min 1.76555 V across the window, blank PWL over 116 samples, 1 rise / 1 fall → the setup is the T1 experiment; `historical_agreement = NO_HISTORY`, so the row stays NOT_CERTIFIED |

**S1_HISTORICAL_REANALYSIS = PARTIAL_NOT_VERIFIED (rc 3): 9 of 10 rows certified, 0 failing.** The
stricter whole-window criteria did not break the historical reading — the original run does satisfy
them — and the one uncertified row is still the missing historical numeric for the negative, which is
not invented. Evidence: `results/evidence/sc1_r2d2_s1_historical_reanalysis.csv` (sanitised rows, no
raw bytes, no absolute paths).

## 5. Tests added, and the ones kept

`scripts/sc1_r2d1_entry_selftest.py` (local copy of the entry, mocked preflight/runner, **real
synthetic PSF-ASCII read by the audited reader**): **23 cases, 0 failures** on guest Python 2.6.6 /
bash 4.1.2 / gawk 3.1.7 and on Windows Python 3.12 / bash 5.2.37 — the 18 R2D1 cases (guards,
all_good, csv_structure, preflight/runner/reader refusals, truth and stimulus errors) plus
`a_t2_blank_high`, `c_blank_never_releases`, `c_blank_single_spike`, `c_high_state_dips`,
`c_low_state_rises`, `c_clock_stuck_high`. The reader-refusal case now uses a **delegating** mock so
that only the scripted query fails, and the assertion checks that no `MOCK_MISS` appears anywhere: a
case may not be "detected" by the harness falling over. Expected row counts are derived from the
contract table instead of a hard-coded number.

`scripts/sc1_r2d1_reanalysis_selftest.py`: **11 cases, 0 failures** on both platforms — the six
R2D1 lineage cases plus the reviewer's exact repro `c_blank_spike_at_410ns` (must FAIL, explicitly not
`PARTIAL_NOT_VERIFIED`), `c_blank_never_releases`, `c_high_state_dips`, `c_low_state_rises`,
`c_clock_stuck_high`, each asserted on the failing row, the reason text and the exit code. The
synthetic decks now also carry the `Vbl ... type=pwl` line: the earlier fixture zeroed the blank
**node** in the faulted run, which is a different fault, and it made the new setup check fail for the
wrong reason.

Everything in both files is synthetic: composed waveforms, 1.8 V and ns values as POC_ASSUMPTION,
labelled `SYNTHETIC_MOCK_not_a_circuit_regression` /
`SYNTHETIC_MOCK_not_historical_data`. Evidence: `results/evidence/sc1_r2d2_entry_selftest.csv`,
`results/evidence/sc1_r2d2_reanalysis_selftest.csv`.

## 6. Network and simulation authorisation, kept separate

Per `AGENTS.md` the only permitted network action is a temporary lease inside the guest, and this
task book explicitly allows running it through the working VMware Tools channel. Read-only first:
`eth0` is `UP,LOWER_UP` with 0 IPv4 addresses and an empty route table; `sshd` is running; host
`VMnetDHCP` and `VMware NAT Service` are both `Running` (VMnet8 = 192.168.3.1).

Then exactly three bounded attempts (`timeout 30/30/45`), never more:
`dhclient -1 eth0` → **exit 1** each time, `inet_count=0`, and the first attempt printed dhclient's
own "…exiting." line. No lease was obtained, so the Tools channel remains the transport
(`scripts/push_chunked.sh`, untracked, base64 chunks with md5 read-back verified). Nothing else was
touched: no `ONBOOT`, no VM power, no snapshot, no `.vmx`, no NAT or VMware service restart, no global
SSH or license change, and no credential value in any report. Simulation authorisation was **not**
inferred from any of this.

## 7. Facts owned by someone else, labelled as such

The **cloud C²MOS verification** the user relayed is recorded as `EXTERNAL_CLOUD_REPORT /
user-relayed`, not as a local measurement, and this round ran no C²MOS job locally because of it:
cloud used its own uploaded PDK's original HSPICE/BSIM4 4.5 models under ngspice 42 in `hs` mode, the
golden source SHA `d1eed4e242fa2874f38d8a2add34eba985e4e14ac8925041f7180e0dfcc5fcf3` (the same SHA
`results/evidence/sc1_r2d1_manifest.csv` records for `spectre/C2MOS_DFF.scs`), 18 devices unchanged;
at 1.8 V / 27 °C with 50 fF on Q and Qbar, single-stage and non-overlapping three-stage chains pass
in TT/SS/FF/SNFP/FNSP, and the 1 ms hold cases (store 0, store 1, clock held high, clock held low)
pass; delaying each stage's clock by 1 ns sequentially breaks the three-stage chain, reproduced with
a finer step and with `gear`. Its stated conclusion is to keep the single-stage topology and to
measure inter-stage hold and clock skew next — not a native-Spectre sign-off. The local
`S1_FRESH_REGRESSION`, `S2_FUNCTIONAL_TT` and the C²MOS re-run stay NOT_RUN, and S4 stays NOT_STARTED.

## 8. S2 count and wording corrections (no S2 code change)

* The static matrix is 37 rows: **35 rows at rc=7 — 34 ordinary cases plus the one deliberate
  legal-wiring/wrong-polarity case — and 2 rows at rc=1** (`neg_vss_miswire`,
  `neg_vdd33_source_absent`). R2D1's text said "34 accepted at rc 7 … plus the polarity case", which
  reads as if 34 were the rc=7 total; corrected here and in the checkpoint.
* Still `PENDING` and not silently upgraded: model binding until `run_spectre.sh` resolves
  `${QODER_PDK_LIB}`; the `temp=` line syntax (no deck in this project has ever carried one); the
  sign convention of a rail current summed from `save <inst>:1` (a series rail `iprobe` is refused by
  the static gate — measured rc 1 / `supply_contract` / 5 `SUPPLY_FAIL` lines).
* `spectre/sc1_level_shifter_r2d.scs` and every protected input are byte-identical:
  `git diff --name-only c050427 HEAD -- spectre/ scripts/sc1_read_psf.py scripts/sc1_delay.py
  scripts/tb_preflight.sh scripts/sc1_supply_check.awk scripts/run_spectre.sh scripts/sc1_s1r.sh
  scripts/sc1_s2.sh` → 0 lines.

## 9. States and stop

| item | status |
|---|---|
| S1_WINDOW_STATE_CONTRACT (A + C, shared) | **CLOSED**, 23/23 entry cases and 11/11 lineage cases on both platforms |
| S1_HISTORICAL_REANALYSIS | **PARTIAL_NOT_VERIFIED** (rc 3): 9/10 rows certified under the stricter contract, 0 failing, F1 without a historical value |
| S2_TOPOLOGY_STATIC_ACCEPTED | unchanged, byte-identical |
| R2D1 static preparation (S2) | unchanged; only its counts/wording corrected here |
| S1_FRESH_REGRESSION, S2_FUNCTIONAL_TT, preflight full, C²MOS re-run, new-PDK run | **NOT_RUN / PAUSED_BY_USER** |
| R2 full acceptance / R3 / S3 / S4 | **NOT_COMPLETED / NOT_STARTED** |
| `SOA_SIGNOFF` / geometry range | **NO / NOT_VERIFIED** |
| `core_ok33`, autonomous power-fail | assumed control only; **NOT_IMPLEMENTED** |

This stops at the **S1 state-criteria review gate**. Fixing the contract is not a simulation
authorisation, and nothing here starts one. The two things that need an owner decision before any
run: lifting the simulation pause (first real TT pass of the S1 and S2 decks with the model binding
resolved, plus confirming the rail-current sum's sign and the temperature-line syntax), and, separately,
whether to restore the guest's DHCP path at all.
