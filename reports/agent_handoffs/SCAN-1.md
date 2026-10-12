# SCAN-1 agent handoff checkpoint

## CURRENT_STATUS (single authoritative table; everything below this block is history)

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
| Preflight matrix (real PDK, full mode) | **PASS 31/31** | `results/evidence/sc1_r2a_preflight.csv` + `..._full.transcript.txt`; 7 acceptance cases ran the operating-point probe on the teacher PDK `section=tt` with `sim=yes`, 22 refusals/harness cases never called Spectre |
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
| S1 1.8 V BLANK/ENABLE logic | **PARTIAL -- truth table proven, drive/fault legs open** | `spectre/sc1_scan_gate.scs`, `scripts/sc1_s1.sh`, `cadence_work/sc1_sim/s1_truth.csv` |
| S2 level shifter + buffer | NOT_STARTED | — |
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

## CURRENT_STATUS (single authoritative table; older sections below are history)

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
