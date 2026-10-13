# SCAN-1R2E1 — new-entry gate fixes and the re-read of already-recorded waveforms

Date 2026-10-13. Baselines: reviewed start `593a8beb9a55840d5f3c33633abb635713af84aa`, previous stage
`dd93f6f432a32fc5f1177223a50ff511e83351c2`; the remote tip was re-read with `git ls-remote` before
editing and equalled the start, so nothing of anyone else was merged or overwritten.

**No simulator was called in this round**: no Spectre, no ngspice, no preflight full, no
operating-point probe, no Virtuoso, no re-run of any S1/S2 deck. Everything here is (a) a fix to the
two entries this round added, (b) offline tests against isolated mocks, and (c) a re-read of files the
previous round already produced. Frozen inputs are byte-identical (see the gate block at the end).

## 1. PREFLIGHT_RC_PROPAGATION — closed

**The defect, as reproduced before the fix.** Both new entries called the preflight through a shell
pipeline (`... 2>&1 | tail -4` / `| tail -5`), so the value they stored was *tail's* exit status:
the reviewer's mock printed `PREFLIGHT_STAGE=supply_contract`, `TESTBENCH_PREFLIGHT: FAIL` and exited
1, and the row still read `rc=0 / PASS`, and the runner was still called afterwards.

That was not hypothetical: **the committed R2E calibration CSV contains the refusal the bug hid.**
`results/evidence/sc1_r2e_calibration.csv`, `PREFLIGHT_FULL` rows, verbatim note:

```
SUPPLY_RESULT FAIL
PREFLIGHT_STAGE=supply_contract
PREFLIGHT_REJECT: contract_refused:contract entry vdd18 matches no instance port
TESTBENCH_PREFLIGHT: FAIL (stage=supply_contract
```

with `rc=0`, `verdict=PASS`. The bench deck's rails are `rail`/`vss`, so the supply map `vdd18=1.8
vdd33=3.3` matched no instance port: the preflight was refusing all six calibration decks, and the
claim "preflight full on the same legal port contract, PASS 6/6" in `scan_driver_r2e_native_tt.md` §2
was wrong. **The same applies to the 15 S2 decks' `preflight_rc` values**: also `| tail`-derived, so
they must be read as unrecorded rather than as 0, and the retained excerpt (cut at 150 characters) shows
the `OP_OK supply net …` contract lines but stops before the completion marker. Preflight full passing
on the S2 decks is therefore not established by those files; the fixed rule requires the marker
explicitly, and satisfying it is the next authorised run's work. Corrected there (§4 below). It does **not** touch the calibration numbers: those rows carry
`runner_rc=0` and `SPECTRE name=… rc=0` read from the real runner exit (that call had no `tail`), and
the values are what the simulator produced.

**The fix.** `scripts/sc1_r2e1_call_contract.py` is now the single place both entries call anything:

* `call()` uses `subprocess.Popen(argv)` — no shell at all, so there is no pipeline whose status could
  stand in for the callee's (argv tokens are encoded natively, because py2.6 `execv` rejects unicode);
* the full output is captured first and only then shortened for display;
* `preflight_verdict(rc, text)` refuses unless `rc == 0` **and** the output contains exactly one
  `TESTBENCH_PREFLIGHT: PASS` and no FAIL line — so rc=0 with a missing, duplicated or contradicting
  completion marker is a tool/log fault, not a pass;
* a refusal returns immediately to the caller, which records the original rc and calls neither the
  runner nor any reader.

## 2. RUNNER_SUCCESS_CONTRACT — closed

**The defect.** Acceptance was `if '<LABEL>: PASS' appears`. The reviewer's mock printed this case's
PASS plus `CHECK error_hits=0` plus `SPECTRE name=mock.scs rc=3` and exited 3 → the row read
`rc=3 / verdict=PASS`.

**The fix.** `runner_verdict(label, deck, rc, text)` requires all of, and reports every failed
condition rather than the first:

| requirement | refusal reason written into the row |
|---|---|
| the runner's own rc is 0 | `runner_rc=N (a PASS token in the text does not override it)` |
| exactly one `<LABEL>: PASS` for this label | `N final PASS lines for label X, need exactly 1` |
| no `<LABEL>: FAIL` | `N final FAIL lines for label X` |
| exactly one `SPECTRE name=…` naming **this** deck, rc 0 | `spectre_rc=N` / `… not this deck` |
| `CHECK error_hits=0` | `CHECK error_hits=N` |
| `CHECK done_line='spectre completes with 0 error…'` | `done_line=…` |
| this run's datafile present, non-empty, **inside this deck's own `sim/`** | `datafile missing/unreadable/empty` / `datafile is outside this deck's sim directory` |
| the log present and non-empty | `logfile missing/unreadable/empty` |

`preflight_rc`, `runner_rc` and `spectre_rc` are kept as separate values in the row and in the
manifest; nothing re-encodes one into another. The datafile-identity rule is what catches the
"failed runner still pointing at a readable older raw" trap, and it fires before any reader runs. The
calibration entry also now writes **one deck file per candidate save form**, because three runs
sharing one deck name shared one raw directory.

**Verification — `scripts/sc1_r2e1_callpath_selftest.py`, 24/24 on guest Python 2.6.6 and Windows
Python 3.12** (`results/evidence/sc1_r2e1_callpath_selftest.csv`). It drives the *real* callers
(`sc1_r2e_s2_tt.run_case`, `sc1_r2e_calibrate.preflight_and_run`) with preflight/runner/reader/re-delay
mocks that live only in a temporary directory:

* every mock refuses if it is handed a path outside that directory, if `RUN` or
  `QODER_SIM_AUTHORISED` is in its environment, or if the runner's `$1` is not the netlist — so a call
  shape that could touch a real deck or leak an authorisation flag fails as
  `MOCK_REFUSED`/`MOCK_ENV_LEAK`/`MOCK_ARGV_ORDER_WRONG` instead of passing;
* each case asserts the concrete row (item, recorded rc, verdict, reason) **and** the
  preflight/runner/reader call counts read from the mock's own log; a driver exception is recorded as
  `CRASH → FAIL`, never as a detection.

| scenario | recorded rc | verdict | PF/RS/RD calls |
|---|---|---|---|
| preflight refuses with a FAIL line | 1 | BLOCKED | 1/0/0 |
| preflight rc=0, no completion marker | 0 | BLOCKED | 1/0/0 |
| preflight rc=0, marker twice | 0 | BLOCKED | 1/0/0 |
| preflight rc=0, PASS *and* FAIL | 0 | BLOCKED | 1/0/0 |
| runner rc=3 while printing this label's PASS + readable fixture | 3 | BLOCKED | 1/1/0 |
| runner rc=0, PASS twice | 0 | BLOCKED | 1/1/0 |
| runner rc=0, PASS belongs to another label | 0 | BLOCKED | 1/1/0 |
| runner rc=0, `CHECK error_hits=2` | 0 | BLOCKED | 1/1/0 |
| runner rc=0, `SPECTRE … rc=3` | 0 | BLOCKED | 1/1/0 |
| runner rc=0, `CHECK datafile=''` | 0 | BLOCKED | 1/1/0 |
| runner rc=0, datafile readable but from outside this run | 0 | BLOCKED | 1/1/0 |
| control: everything consistent | 0 | PASS | 1/1/16 (S2) · 1/1/0 (calibration stops after the run) |

The 26 existing entry cases and the 5 window-contract behaviours were kept and still pass
(`results/evidence/sc1_r2e1_s2_entry_selftest.csv`, 26/26 in the guest).

## 3. VTX_STRICT_INPUT — closed

**The defect.** `sc1_r2e_vtx.py` had its own lenient reader: a group missing one of the two signals
was skipped and the remaining samples still produced a certified extreme; `inf` was accepted; a
reversed time axis was accepted. The reviewer's three CLI counterexamples returned `rc=0` with values
`1 / 2e-09`, `inf / 1e-09`, `2 / 2e-09`.

**The fix.** The private parser is gone: the tool calls the audited `sc1_read_psf.parse()`, which
already refuses a non-finite value, a duplicate signal inside a group, a value row before the axis, a
file that ends inside a group, and any group whose signal set differs from group 0. Because `parse()`
does **not** validate the axis as a whole, the tool adds that itself and fails closed:

* the axis must be `time`; times must be strictly increasing (duplicate or reversed → `BAD_AXIS`, rc 8);
* every sample inside the window must carry both signals and the difference must be finite;
* unknown mode → rc 9; non-numeric or reversed window → rc 5; empty/too-short window → rc 4; missing
  signal → rc 3; absent file → rc 2. No refusal prints a number;
* the value and the time of the extreme are still printed (`%.6g` like the audited reader), and the
  tie-break policy is stated in the tool and printed with `--verbose`: **the first sample in file order
  that reaches the extreme wins**.

`python scripts/sc1_r2e_vtx.py --selftest` — 16 cases (4 positives incl. the tie rule, the 8-item bad
data list, plus usage refusals), **16/16 on both platforms**, each asserting the real subprocess exit
code and the exact value+time or the specific refusal text.

## 4. Re-read of what R2E already measured — no new simulation

### C1 stress rows, strict re-read → `results/evidence/sc1_r2e1_vtx_reanalysis.csv`

123 rows: every `DEVICE_STRESS_PEAKS` / `STRESS_CROSSCHECK` entry of the static and load groups,
recomputed with the strict tool on **the same case window the original row used** (a whole-file extreme
of the same node pair is a different question, and comparing that against a window value produced four
apparent FAILs on the first attempt — corrected, not papered over). Each row carries the original
run_id, case, item, target, the re-read file's SHA256, the node pair, the window with its sample count,
the original min/max, the strict min/max, the difference, the extreme times, the exit codes and a
verdict. **All 123 rows read PASS**, none was refused, so the strictness did not change any recorded
measurement — and it agrees inside the display quantisation band of the original 6-significant-digit
output (±5e-7 V at 1 V, ±1.6e-6 V at 3.3 V), which is a stated bandwidth, not a loose tolerance. The
three `STRESS_CROSSCHECK` rows are re-performed rather than diffed against prose: the device's own
exported `:vgs` against the strict node difference, worst disagreement 4.05e-6 V (the original rule was
1 mV). `SOA_SIGNOFF` stays **NO**.

### C2 sampled waveform excerpts → `results/evidence/sc1_r2e1_waveform_samples.csv`

195 rows of real, consecutive samples — no interpolation, no resampling, no raw PSF committed — each
with case, the re-read file's SHA256, the original sample group index, `time`, the needed node/current
values at that same sample and why the segment was chosen:

* `dyn_c0_rise` / `dyn_c0_fall` / `dyn_c1_rise` / `dyn_c1_fall` (1 pF): input 50 % edge, output
  90/50/10 % fall band, `Xt.x`, `Xt.y` (C1 also `core_ok33`, `Xt.Xnand.ns_m`) — e.g. the C0 input 50 %
  crossing sits between samples 513 (`en=0.874491`) and 514 (`en=0.906233`) at `t=1.02013852e-07 s`;
* `load_c1_5pF` and `load_c1_5pF_fine`: the same output 50 % fall in the coarse and the fine step, so
  the delay claim can be checked against both samplings;
* `dyn_c0_repeat3` / `dyn_c1_repeat3`: all **12** attributed pairs — each owning input 50 % edge and
  its answered output 50 % edge, plus the next input crossing of either direction, which is the
  boundary the audited tool refuses to answer past;
* `neg_output_polarity_fault`: the input 50 % rise and the output rise the wrong-polarity deck
  produced, i.e. the reason the normal C0 fall criterion said `NO_RESPONSE`;
* one per-device stress extreme (`Xt.Xcore.mn_left` VGS) with its D/G/S/B node voltages at that same
  sample, and one dynamic rail-current peak (`V33:i` most negative in the 5 pF case) with the other
  three source branches at the same samples. Currents keep the raw signed reading and the calibrated
  rule **injected = −(Vsource:i)**; no rail was broken and no drain sum substituted.

Zero segments were missing and zero refused. These rows cover only the sampled fragments: they are not
a re-do of the whole-window checks, which remain the audited windowed readers' job.

## 5. Report corrections applied to `scan_driver_r2e_native_tt.md`

1. **F1's value.** §4 of that report claimed the faulted deck gave `en max=0.0753447 V` "which cannot
   satisfy `< 0.9`". That number is the *normal* T1 row and it does satisfy the claim. The F1 row in
   `sc1_r2e_s1_regression.csv` is `F1_blank_clamped, signal=en, value_V=1.8001, row_verdict=DETECTED`
   with its setup row `PASS`: the fault holds `en` high, so `1.8001` fails `< 0.9`. Corrected in place,
   with the mistake's text preserved as a correction note; no experiment row was altered.
2. **Calibration run count.** §2 wrote "12/12 runs". The CSV holds **6** `TEMP_CONFIRMATION` rows, each
   reading two places in the same run (the log's `temp = 27` and the psfascii header's
   `"temp" 27.0000`) — so the correct statement is 6 runs, 12 consistent read-back values.
3. **`PREFLIGHT_FULL` on the calibration bench.** Corrected to the refusal quoted in §1 above, together
   with what that does and does not invalidate, and with the contract the bench actually needs
   (`rail=1.8 vss=0`), which stays for a future authorised run.
4. **`SAVE_PATH_AUDIT` wording.** Split into the two separate facts: the audited generated decks asked
   for `Xt.Xcore.x` / `Xt.Xcore.y` and this build ignores those names (`SPECTRE-8281`, a warning, not a
   fatal), and, separately, the signals this round's measurements needed were obtained — through the
   names the resolver derives (`Xt.x`, `Xt.y`), visible in each run's `SAVED_SIGNALS` trace list. The
   verdict stays `PARTIAL` on purpose: it is a defect found in the reviewed decks' save line, not a
   renamed pass.

## 6. Gates, and what still stands

```
protected (git diff --name-only 593a8be HEAD -- spectre/*.scs + the audited tools + the old S1/S2
  entries + the S1 window contract)                          -> 0 files
old CSVs                                                     -> none rewritten; every new artifact is
                                                                sc1_r2e1_*
safety gate / provenance / device count                      -> PASS / PASS / PASS
offline suites, guest 2.6.6 and Windows 3.12                  -> 16/16 vtx · 24/24 call path · 26/26 entry
simulator calls this round                                     -> 0 (also none of the fixed entries were
                                                                 re-run: that needs the next authorised
                                                                 session)
```

Unchanged by this round: the S1 native regression stays the R2E evidence (this round is *not* an S1
fresh rerun), the S2 numbers stay "already-recorded native" with this round's re-read layered on top,
dynamic figures stay `MEASURED` with `budget NOT_DEFINED`, `SOA_SIGNOFF NO`,
`AUTONOMOUS_POWER_FAIL NOT_IMPLEMENTED`, and no DHCP/NAT/service/`.vmx`/power/snapshot/licence action
was taken. Not started: the 37-deck supply matrix, R3, S3/S4, corners, layout.

Stopping again at the **native TT results review gate**.
