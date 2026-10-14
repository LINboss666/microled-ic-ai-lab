# SCAN-1 S3-C — Virtuoso schematic and Symbol views of the verified single scan channel

Task book: `MicroLED_Qoder_SCAN-1S3C_a26c54b_schematic_symbol.md`. Reviewed start
`a26c54b6cccb503ce1283e58c39819ed1ca890de`, decision
`S3_B_TT_POC_ACCEPTED_WITH_OFFLINE_CORRECTIONS / GO_S3_C_SCHEMATIC_SYMBOL`.

**Headline state**

```
S3_B_TT_POC                        = ACCEPTED_WITH_OFFLINE_CORRECTIONS
S3_C_OA_SCHEMATIC                  = COMPLETE   (8 cells, this task's own library)
S3_C_OA_SYMBOL                     = COMPLETE   (8 symbol cellviews exist and reopen)
S3_C_OA_READBACK                   = COMPLETE   (two independent sessions, identical rows)
S3_C_OA_GRAPH_EQUIVALENCE          = PASS       (8/8 cells, 39/39 devices, counter-example refused)
S3_C_VISUAL_REVIEW                 = PENDING    (batch build cannot draw: measured, see section 7)
NEW_SIMULATION_RUNS                = 0
FINAL_VSCAN / LED_IV / N_ACTIVE / REAL_ELECTRODE_RC / BUDGETS = NOT_DEFINED
SOA_SIGNOFF                        = NO
AUTONOMOUS_POWER_FAIL              = NOT_IMPLEMENTED
S4                                 = NOT_STARTED
```

This round delivered views of a circuit that is already measured. It changed no topology, no size and
no model, and it started no simulator: no Spectre, no ngspice, no full preflight, no operating-point
run. The only Cadence programs executed were `spiceIn` (netlist → schematic importer, **1** invocation)
and `virtuoso -nograph` (**5** sessions: capability probe, library-create attempt, parameter write,
read-back pass 1, read-back pass 2). The netlist in `spectre/generated/` is *extraction from* the
schematic, not a simulation of it.

---

## 1 Start point, re-read before touching anything

| check | result |
|---|---|
| local HEAD | `a26c54b6cccb503ce1283e58c39819ed1ca890de` = the reviewed start |
| remote tip `poc/scan-driver-1ch` | read back with `gh api`; the direct `git ls-remote` attempt failed once with `curl 28 Recv failure: Connection was reset`, which on this link proves nothing either way (AGENTS rule 31), so the tip was taken from the API read-back |
| work tree | clean except two untracked local helpers (`scripts/git_push_reliable.ps1`, `scripts/push_chunked.sh`), no teammate files, no unknown upstream commits, nothing merged or cherry-picked |
| the seven frozen masters | md5 re-read and matched: `C2MOS_DFF.scs b82979bb…`, `sc1_scan_gate.scs 7cdfef80…`, `sc1_level_shifter_r2d.scs 8f770446…`, `sc1_r3_scan_chain.scs 409e6b91…`, `sc1_s3b_p33_bank.scs e9a212c7…`, `sc1_s3b_scan_power_1ch.scs d0d0e3d8…`, `sc1_s3b_scan_power_1ch_fault.scs 9b42ec87…`. All seven are byte-identical at delivery (`git diff` over them is empty) |
| guest channel | SSH is still down; everything went through the VMware Tools RPC (`scripts/guest.sh run/pull`) with md5 verification, and uploads through `scripts/push_chunked.sh` |
| running sessions | `ps` showed 0 Virtuoso processes before the first session, so no lock was held against anyone's open cellview |

## 2 What was read-only measured before any write

`skill/sc1_s3c_oa_probe.il`, one `virtuoso -nograph` session, every open in mode `r`. Its answers
decided the build, so they are recorded rather than assumed:

* **the PDK symbol terminals are not in one order across families** — `n18` and `p18` read
  `S G B D`, `n33` reads `D G B S`, `p33` reads `B D G S`. Every terminal in this round is therefore
  addressed **by name**, and the read-back prints the name set it actually found per instance
  (`("B" "D" "G" "S")` etc.), so a position-keyed mistake would be visible instead of silent.
* CDF parameter dictionary of all four masters: `l, w, fw, m, fingers, model` exist;
  defaults `180n/220n/220n/1/1` for `n18`/`p18` and `350n/350n/350n` for `n33`/`p33`;
  **`simW` is a real PDK field** carrying `iPar("w")`. Nothing was written to it, and no PDK field was
  deleted to make it read absent (task book section 5).
* Batch-session API: `dbOpenCellViewByType`, `dbSave`, `dbCheck`, `dbCreateInst`, `dbCreateTerm`,
  `dbCreatePin`, `dbCreateProp`, `dbDeletePropByName`, `dbFindProp`, `cdfGetInstCDF`,
  `cdfFindParamByName`, `cdfParseFloatString`, `dbCopyCellView` = present. `dbCreateFig`,
  `ddCreateCell`, `schCreate`, `schCreateWire`, `schCheck`, `schCreateSym`, `symCreate`,
  `schConvSch2Sym`, `hiCheckAndSave`, `hiCreateDirLib` = **`nil` in that session at that moment**.
  **Retracted in S3C1**: `getd` returning `nil` at process start does not prove the capability is
  absent — the schematic package loads later, and `schCheck` does run in the same `-nograph` mode once
  it has. Section 10 is the corrected measurement.
* An importer-made cell in the existing library (`microled_cells/c2mos_dff_1bit`) shows `terms=0` on
  the schematic side in batch, ports present as `basic/iopin` instances whose identity lives on the
  net's pin, and a **symbol view with the right terminals and 0 figures**. **Retracted in S3C1**: both
  readings used wrong attributes — `cv->terms` and `dbGet(sym "figures")` are supported and legitimately
  empty, while `cv->terminals` and `cv->shapes` are not, and this library's own symbols do carry body,
  pin and label graphics (section 10). Unaffected is that the file-scope wrapper
  cells (`sch3_top`, `sch1_import_top`) have no symbol at all — which decided the shape of the import
  (section 4).

## 3 The golden table, derived and reproduced on two interpreters

`scripts/sc1_s3c_golden.py` parses the six electrical masters (the fault deck stays a historical
negative and produced no schematic) and emits everything else. Nothing is typed from memory: if a
master changes, the tables and the import copy change with it, and the built-in `--selftest` refuses
to emit when a count or a body tie differs from the task book. It runs on Python 3.12 (workstation)
and Python 2.6.6 (the simulator host) and produces **the same bytes on both** — verified by md5 for
all four golden tables (`sc1_s3c_golden_mos.csv 21301a9f…`, `_hier c282008f…`, `_ports 311ae9d8…`,
`_subinst 0ae07fb0…`), the import copy and the parameter table. `scripts/sc1_s3c_verify_oa.py` was
then run on the guest's 2.6.6 against the same read-back log and reached the same verdicts
(`S3C_OA_GRAPH_EQUIVALENCE: PASS`, 8/8, counter-example refused, reopen consistent), so the acceptance
criterion does not depend on which machine evaluates it.

| file | rows | content |
|---|---|---|
| `results/evidence/sc1_s3c_golden_mos.csv` | 39 | cell, instance, top-anchored path (`Xchain.Xff.mn_c`, `Xbank.mp1`…), model, D/G/S/B nets, `l_m`/`w_m` in metres plus the source token, master file |
| `results/evidence/sc1_s3c_golden_hier.csv` | 8 | own devices vs expanded devices (18 · 4 · 6 · 4 · 10 · 32 · 7 · 39), direct children, port count |
| `results/evidence/sc1_s3c_golden_ports.csv` | 48 | per cell, per ordinal: port name, declared direction, role, and the master's own port order |
| `results/evidence/sc1_s3c_golden_subinst.csv` | 39 | every pin of every sub-circuit instance: child port → parent net |

Selftest asserts, among others: the top expands to **39** devices owned by exactly five leaf cells;
seven explicit `mp1…mp7`; every bank device `L=4e-07 W=1e-04` with **both S and B on `vscan`**; the
stacked NMOS `mn_nt` `S=ns_m` **`B=vss`** (the well/source split, not body-to-source); the formal top
carries no `iprobe` and merges `bgate` into `gate33`; and `metric()`/`mtxt()` round-trip exactly.

## 4 The build

**Isolation.** `scripts/sc1_s3c_setup.sh` created `cadence_work/s3c_oa/` and wrote **this task's own**
`cds.lib` by reading `cadence_work/cds.lib` and carrying every registration over (relative paths made
absolute so `microled_cells` still resolves), then appending one line for
`microled_scan_s3c → …/s3c_oa/microled_scan_s3c`. The shared file's md5 is printed before and after:
`a263050287c336b45be669ec75d14b48` both times, and it mentions the new library 0 times.
`scripts/sc1_s3c_run_oa.sh` is a copy-by-value of the proven runner with the cwd moved into `s3c_oa`;
the original `scripts/run_virtuoso.sh` and `scripts/sch_virtuoso.sh` were not modified.
The library directory is created by `spiceIn` itself — `hiCreateDirLib` is `nil` in this session, so
the intended `skill/sc1_s3c_mklib.il` step was a no-op and is kept as evidence of that measurement.

**One import, eight cells.** `scripts/sc1_s3c_golden.py --emit-import` writes
`asg_in/sc1_s3c_import.scs` (sha256 `7b7beeff8d19…`): the seven sub-cells plus
`subckt sc1_scan_power_1ch_s3c` plus a file-scope shell. The delivered top must be a sub-circuit
because `spiceIn` refuses a topCell that is also a subckt in the file (SPICEIN-77) **and** because the
measured fact from section 2 says a file-scope cell gets no symbol. `scripts/sc1_s3c_asg.sh` refuses
before running if any target cell already exists, if a `subckt`/`ends` header is missing, if the copy
does not hold exactly 39 device instance lines, if it still mentions `iprobe`, or if the bank line is
not `Xbank (scan gate33 vscan)`. Result: **`ASG rc=0`, `SPICEIN-54` success, 0 problem lines**, and
views:

```
c2mos_dff            schematic + symbol      sc1_ls_c1_top_r2d     schematic + symbol
sc1_scan_gate        schematic + symbol      sc1_r3_scan_chain_1ch schematic + symbol
sc1_ls_core_r2d      schematic + symbol      sc1_s3b_p33_bank_7    schematic + symbol
sc1_ls_c1_r2d        schematic + symbol      sc1_scan_power_1ch_s3c schematic + symbol
s3c_asg_shell        schematic only          <- importer plumbing, not one of the eight
```

Three deliberate, recorded differences from the masters, and no others: design variables substituted
by their own values (SCH-2 measured that `l=ln` lands as unevaluable text), port-direction
declarations added (structural annotation, no connectivity), and the formal top without the `iprobe`
with `gate33`/`bgate` merged — justified by the S3-B measurement that the two nodes sit at the same
potential, since the iprobe is a zero-drop meter.

**Sizes.** The import put `l` into the `l` property and the width into `simW`, leaving `w` and `fw`
absent and the CDF therefore reporting the master default:

```
S3CB-BEFORE "c2mos_dff" "mp_c" model="p18" raw_l="2e-07" raw_w="ABSENT" raw_fw="ABSENT"
            raw_simW="4e-06" cdf_l="200n" ...
```

That is the SCH-2 defect reproduced on this circuit, and `skill/sc1_s3c_build_oa.il` fixes it through
the parameter names each master's own CDF defines, from the generated table
(`sc1_s3c_param_table.gen.il`, sha256 `43f677e3d55d…`, 39 rows). It refuses a cell whose device count
does not match its row count, never calls `cdfUpdateInstParam`, never writes `simW`, edits no wire and
no figure, and writes only inside this task's library: **39 devices written, 195 properties, all eight
`dbSave` = t, no row-count mismatch, no missing instance.**

## 5 Independent read-back and the graph-equivalence verdict

`skill/sc1_s3c_readback.il` runs in a **separate** Virtuoso process after the writer exited, opens
every view in mode `r`, and prints only what the database gave it. `scripts/sc1_s3c_verify_oa.py`
compares that against the golden, always in one direction (does the OA side match the golden). Its
first pass found three of my own defects, which is the point of separating writer and reader: a
`model`-property test counted the seven sub-circuit instances as devices (an instance of a design cell
also carries a `model` here, so classification moved to the master's library), a `sorted(terms) !=
['D','G','S','B']` comparison compared an alphabetical name set against a positional one, and the
`q`-net assertion demanded two connections where the chain legitimately gives `q` only to `Xff`.

```
S3C_READBACK_ROWS cell=8 device=39 inst=55 net=64 pin=48 symbol=8 symterm=48
S3C_OA_DEVICE_COUNT 39 · S3C_OA_SUBINSTANCES 7 · S3C_OA_PORT_PINS 48 · S3C_OA_SYMBOL_TERMINALS 48
S3C_DBCHECK_ALL_T yes · S3C_CONNECTIVITY_MATCH 46/46 · S3C_EQUIVALENCE_MATCH 8/8
S3C_REOPEN_ROWS pass1=281 pass2=281 only_in_pass1=0 only_in_pass2=0   -> S3C_REOPEN_CONSISTENT: PASS
S3C_NEGATIVE rc_tampered=1 rc_intact=0
S3C_OA_GRAPH_EQUIVALENCE: PASS   failures=0
```

Against the task book's seven required results:

| required | result | how it was shown |
|---|---|---|
| 1 eight cells, schematic and symbol, reopenable | **yes** | 8 cells listed above; both views open in a fresh process; two passes byte-identical |
| 2 exactly nine top ports; per-cell port names, directions, symbol ↔ schematic | **names and binding yes; OA-side direction blocked** | top has 9 golden ports, 9 port nets, 9 symbol terminals, one pin per port (`sc1_s3c_ports.csv`, 48 rows). The importer's symbol terminals all read `inputOutput` and the schematic's `terms` list is empty in batch, so the *declared* direction (input / output / inputOutput, section 3 table) is carried by the import copy and the golden table, not by the OA object |
| 3 39 devices, model/L/W/terminal read back, seven fingers not folded | **yes** | `sc1_s3c_oa_readback.csv`: 39 rows, each with raw property, CDF value and `cdfParseFloatString` number for `l/w/fw/m/fingers`, `simW` reported untouched, `m=fingers=1` everywhere, and the seven `mp1…mp7` as separate instances at 100 µm |
| 4 per-MOS D/G/S/B nets vs golden, full 39-device expansion | **yes** | `sc1_s3c_connectivity.csv` 46 rows (39 devices + 7 sub-instances), all `MATCH`, nets read by terminal **name** |
| 5 every pin really bound, no floating net, `q`/`qbar`/`en` real internal nets | **yes** | no device terminal `UNCONNECTED`; every net has terminals or a pin; the three notes print `q` 1, `qbar` 2, `en` 2 terminal connections with no port pin |
| 6 formal top differs only by the iprobe and the merged node | **yes** | top has no `bgate` net, `Xbank (scan gate33 vscan)`; nothing else was merged or re-routed — the canonical text of all eight cells equals the golden |
| 7 saved, reopened, nothing pre-existing written | **yes, with one measured note** | see section 7 |

The verdict is labelled **OA_GRAPH_EQUIVALENCE**: an object-graph agreement between the shipped
schematic and the shipped netlist. It is not LVS (there is no layout), not a netlister output
(`asiNetlist` exists only on the `-restore` path and was never available to batch), and not a new
functional pass — the circuit's behaviour remains the accepted S3-B TT POC and nothing was re-simulated
to make these views.

Extracted text circuit table: **`spectre/generated/sc1_s3c_channel_from_schematic.scs`** (77 lines,
eight sub-circuits, every instance/model/size/net from database rows; only the *order* of each port
list comes from the golden, because a terminal set is unordered in the database). Internal net names
needed no mapping: they are identical to the masters' (`ns_m`, `enbar`, `x`, `y`, `q`, `qbar`, `en`,
`x1/x2/y1/y2`, `m`, `mb`, `clkb` all present), so the one-to-one mapping is the identity map, except
that the top's `bgate` no longer exists as a separate net by design.

## 6 The consolidated S3-B offline corrections (section 4 of the task book)

`scripts/sc1_s3c_s3b_corrections.py`, zero simulation, output
**`results/evidence/sc1_s3c_s3b_corrections.csv` (92 rows)**, self-checking: it first re-joins the
fifteen delivered sample parts with the audited splitter's own rule and refuses to compute unless the
rejoin hashes to the digest the index declares (`a9e32354…`, 3 583 407 bytes).

| item | what was wrong | what the correction table now says |
|---|---|---|
| **4A direction** | `S3B_BRANCH_CURRENT` printed `injected = −(Vsource:i)` on **all four** branches. For `VSCAN:i`, `V33:i`, `V18:i` that is the supply rule and it stays; for `Xtop.Ip_gate:i` it is wrong — an iprobe is a meter inside one branch | 9 rows `A_IPROBE_DIRECTION` (positive = gate33 → the seven bank gates, charging; negative = discharging back into the driver; the signed reading and the charge integral are kept exactly as delivered), 27 rows `A_RAIL_INJECTION_KEPT`. `measure_branches()` in the S3-B entry now prints the two conventions separately — label and comment only, no number changed |
| **4B precision** | `Ron 8.00029 Ω` (light) and `7.92883 Ω` (column) were divided out of a source-drain drop that had already been rounded to six significant digits | recomputed per sample from the shipped 17-digit values: light plateau **7.7407119837154896 Ω**, column plateau **7.9290616986611493 Ω**; per-sample range inside the plateau is printed too. Neighbourhood of the scan extreme, with the current band stated (±20 % of the plateau current): light **7.7121…7.7695 Ω**, column **7.8158…8.0457 Ω** — a recomputation *reference*, not a range the delivered figures must land in. Largest conducting plateau drop **0.08888283 V**, so the conditional 0.10 V figure is still met. The delivered CSV bytes were not rewritten |
| **4C text and state** | the report's `NO_EDGE` paragraph lumped the decks together; R3's manual gate load was written as 0.2 pF; the tail criterion risked being read as a convergence proof; the 148 figure mixed local and cloud evidence | 32 `C_EDGE_VERDICT` rows and a per-case table now in the report: `s3b_write_q1_light` `scan` **rise is PASS**, and the `scan` **fall is PASS** on five column decks (blank-assert, blank-release, write-q0, repeat101, guard-cycle); `0.2 pF` replaced by the values read out of `scripts/sc1_r3_chain_tt.py` — **1 pF default** (line 411 with `load=1.0`, printed as `load_default=1pF` at line 1066) and **5 pF** in `r3_load5p` (line 266); the settle wording now states explicitly that the `maxstep=0.05` sensitivity deck was never run and that nothing here certifies step-size convergence; `C_PROCESS_ACCOUNTING` splits **18 cloud-verifiable records** (nine full preflights + nine DUT runs, counted in `sc1_s3b_dependency_log.txt`) from **148 local Spectre output directories** (re-measured: eight native batches × 18 = 144 plus two 2-run probes), and says a reviewer cannot re-count the latter from the repository |

After those edits the S3-B gates were re-run on the delivered bytes and still pass:
`sc1_s3b_chain_power_tt.py --selftest` **24/24**, `sc1_s3b_verify_evidence.py` **49 checks 0 failures**.

## 7 Differences, limits and what was deliberately not done

* **`s3c_asg_shell` exists in the library and is not one of the eight.** It is the file-scope top the
  importer requires; its schematic is one instance of the delivered top wired port-to-port. Nothing in
  the electrical claim depends on it.
* **Every cell also carries a `data.dm` view** (Cadence's own metadata) and the shell shows a
  `netlist_tmp` step in the ASG log. Recorded, not used.
* **Symbol graphics and schematic pin directions are not deliverable in batch on this build.**
  **Retracted in S3C1 — this was an attribution, not a measurement.** The three claims it rested on
  ("this build's batch mode cannot draw", "the symbols have 0 figures", "batch cannot persist a
  direction") are all replaced by measured results in section 10: directions are written on the real
  terminal objects and read back from disk (96 of 96), the symbols have real body/pin/label graphics,
  `schCheck` runs in batch and reports per-view counts, and figures can be re-placed by assigning
  `bBox`/`xy`. What genuinely remains undone is the **role-based pin placement** and the wire repair it
  forces in the parent schematics, plus real screenshots — recorded as blocked with the exact reason
  rather than presented as finished.
* **`dbCheck` is reported as `dbCheck`.** It returns `t` for all eight cells; it checks the OA object
  graph and is not the editor's electrical Check-And-Save, which is unavailable here.
* **One directory mtime moved outside the new library.** `microled_cells`' own timestamp advanced
  during a session that opened it read-only; `find microled_cells -type f -newermt '2026-10-14'`
  returns **0 files**, and the same pattern of `.cdslck` siblings exists under `logs/` from earlier
  rounds, so the reading is a lock file created and removed inside that directory. No cell content
  changed. The PDK tree shows 0 files newer than today and the shared `cds.lib` md5 is unchanged.
* Not done, by instruction: no S4, no array, no multi-channel, no Data chaining, no PVT/corner, no
  5 V or stacking probe, no POR/UVLO or power-fail matrix, no layout/DRC/LVS/PEX, no fault-deck
  schematic. No gate was modified and no `--no-verify` was used.

## 8 How a reviewer opens it

The library lives in the guest at `/root/microled_ai_project/cadence_work/s3c_oa/microled_scan_s3c`
(812 KiB), with a restorable archive next to it:
`backup_microled_scan_s3c_20261014.tgz` (100 335 bytes, sha256 `d5c784b99b1794e2…`, contains the
library, this task's `cds.lib`, the import copy and the four SKILL files). It is inside the project and
git-ignored — no OA binary or PDK content is committed.

```bash
cd /root/microled_ai_project/cadence_work/s3c_oa
# this task's map only; the shared cadence_work/cds.lib is not used and was not modified
cat cds.lib                      # 5 carried-over DEFINEs + microled_scan_s3c
bash ../../scripts/sc1_s3c_run_oa.sh $PWD/skill/sc1_s3c_readback.il 600 S3CR_DONE
# or, in the GUI, start Virtuoso with this directory as cwd so the isolated map resolves:
#   cd /root/microled_ai_project/cadence_work/s3c_oa && DISPLAY=:0 virtuoso &
# then open library microled_scan_s3c, cell sc1_scan_power_1ch_s3c, view schematic / symbol.
```

Evidence to read first, in this order: `scripts/sc1_s3c_golden.py --selftest` output, then
`sc1_s3c_oa_readback.csv` + `sc1_s3c_connectivity.csv` + `sc1_s3c_ports.csv` +
`sc1_s3c_equivalence.csv`, then `spectre/generated/sc1_s3c_channel_from_schematic.scs` against
`spectre/sc1_s3b_scan_power_1ch.scs`, then `sc1_s3c_s3b_corrections.csv`, then
`cadence_work/s3c_oa/logs/` (ASG log and the five session logs).

Round bookkeeping: `results/evidence/sc1_s3c_round_manifest.csv` (150 rows, 22 of them `s3c_*`:
7 entry/check tools, 4 SKILL files, 9 evidence tables, the extracted netlist and this report; every
row carries sha256, byte count and whether the reviewer can re-hash those bytes from the repository).
`scripts/sc1_s3c_check_staged.py` re-parses the delivered tables before the commit — width, row
counts, `(cell, instance)` uniqueness on both sides of the comparison, finiteness of every numeric
token, that each correction row cites a deck/raw digest the delivered identity index really declares,
that the connectivity table is 39 + 7 rows of `MATCH`, that the equivalence table is 8 rows of `MATCH`,
and that the seven frozen masters plus the five delivered S3-B evidence files show **no diff against
HEAD**: **30 checks, 0 failures**.

## 9 Tool counts, and what a reviewer should decide

| tool | invocations | note |
|---|---|---|
| Spectre / ngspice / preflight / operating point | **0** | hard requirement of this round |
| `spiceIn` | 1 | eight cells and eight symbols in one pass, rc=0, 0 problem lines |
| `virtuoso -nograph` | 5 | probe, mklib attempt, parameter write, read-back ×2 |
| `dbCheck` | 8 | one per cell, all `t` |
| VMware Tools RPC | 14 runs + 8 pulls | every transfer md5-verified; 5 chunked uploads |

Open questions for the S3-C gate, none of which this round answered by itself:

1. Is a schematic set whose symbols carry terminals but no graphics an acceptable S3-C delivery, or
   should the symbol bodies and the placement be produced in one GUI session (which needs the user's
   display and would create lock files against their open editor)?
2. Are the declared port directions adequate evidence for section 6 item 2, given that the OA side
   cannot carry them in batch?
3. Does the reviewer want the seven sub-cell bodies placed into the five DFF regions now, or kept as
   importer placement until layout is actually in scope (it is currently out of course scope)?
4. Confirm the light-deck `Ron` correction (8.00029 → 7.7407 Ω) is recorded the way the reviewer
   wants: report text amended, delivered CSV untouched, correction table citing the original rows.

## 10 S3C1: corrected read-back, the direction write, and what actually blocks the placement

Everything below is a measurement from this task's own library, with the table that holds it named in
each bullet. `NEW_SIMULATION_RUNS = 0` still: no Spectre, no ngspice, no preflight `full`, no
operating point was run in this section.

* **Fields corrected** (`results/evidence/sc1_s3c1_oa_readback.csv`, 16 rows). For every view,
  `cv->terminals` and `cv->shapes` return counts; `cv->terms`, `cv->figures` and `cv->figs` return
  `EMPTY (supported, nothing in it)`. The S3-C conclusion was therefore built on attributes that are
  legitimately empty, not on absent graphics.
* **Directions written on the real objects and read back from disk**
  (`results/evidence/sc1_s3c1_ports.csv`, 96 rows = 48 schematic + 48 symbol terminals,
  `S3C1_PORT_ROWS 96 ... MISMATCH 0`). The working write is `termObj->direction = 'output`;
  `dbSetq(termObj->direction ...)` returns nil, and `intern("inputOutput")` raises. A separate process
  then opened the views and compared 96 objects with `objects compared: 96 mismatched: 0` and the
  distribution `inputOutput 40 / input 36 / output 20`. That replaces "batch cannot persist a
  direction".
* **Symbol graphics exist, per symbol** (`results/evidence/sc1_s3c1_graphics.csv`): every one of the
  eight has a `device/drawing` body rectangle, and pin rectangles = connector stubs = pin labels =
  terminal count (bank 3/3/3 with 13 shapes, `c2mos_dff` 6/6/6 with 22, top 9/9/9 with 31, ...).
* **...but all 48 pin centres lie to the right of the body**
  (`results/evidence/sc1_s3c1_symbol_side.csv`): 10 match their role — the ten signal outputs, which
  belong on the right — and **38 do not** (13 signal inputs, 11 supplies, 8 `vss`, plus `bgate`). This
  is the placement gap stated as a number.
* **Parents are internally consistent today** (`results/evidence/sc1_s3c1_connectivity.csv`): 39
  sub-instance pins, **39 reached by a wire figure of that same parent net**. Two things had to be
  measured to get that honest: net names are per view (the top schematic carries the bank's `bgate`
  pin on the net named `gate33`), and instances are not all `R0` — `S3C1_GEOM_TRANSFORMS MY,R0`, so a
  mirrored instance's pin x is `origin − symbol x`.
* **Editor check, with the counts kept** (`results/evidence/sc1_s3c1_editor_check.csv`): `schCheck` on
  the eight schematics returns `((0 5))` dff, `((0 1))` gate, `((0 2))` ls_core, `((0 1))` ls_c1,
  `((0 1))` ls_c1_top, `((0 1))` chain, `((0 0))` bank, `((0 0))` top — 0 errors everywhere, warnings
  kept as printed. On symbol views `schCheck` returns nil, and `symCheck`/`hiCheckAndSave` are absent,
  so the symbol side is checked by `dbCheck = (t)` (16/16 in the GUI session) and by the geometry
  tables, not by an editor check that does not exist here. `dbCheck` is still not presented as the
  editor's Check-And-Save.
* **Write capability, at three measured points** (`results/evidence/sc1_s3c1_tools_locks.csv`, 232
  rows from six sessions). Works: assign `fig->bBox` / `label->xy` (probe7: `SETBBOX rc=t changed=t`,
  then `dbSave`, `dbClose`, reopen **from disk** shows the moved box, and the terminal still owns the
  same pin object); assign terminal direction; `dbSave`; `dbCheck`; `schCheck` once the package has
  loaded. Does not work here: `dbMoveFig` in three argument orders (the two error texts pin the order
  down — `Invalid cellView` for `(fig delta)`, `Invalid figure` for `(cv fig delta)`),
  `dbCreateRect`/`dbCreateLine`/`dbCreateLabel`/`dbCreatePin` in six forms, and `dbDeleteObj`,
  `geMoveFig`, `schCreateWire`, `schDelete`, `symUpdateInst`, `schUpdateInst`, `schMaintainConn` are
  absent — they stay absent in a `-nograph` process and in the GUI process that never got an editor
  window.
* **Safety of this round**: the 72 delivered library files are byte-identical before and after
  (`logs/pre_scratch_lib.md5` vs `logs/post_cleanup_lib.md5`, `LIB_BACK_TO_72_IDENTICAL`). Five scratch
  cellviews created by the probes — `dbCopyCellView` writes its target to disk even when nothing is
  saved, which is itself a measured fact — were removed and the identity re-checked. No `.locks` entry
  existed at any point, no other Cadence process was running, no lock was deleted, no user window was
  touched, and the pre-S3C1 backup stays in the project
  (`backup_microled_scan_s3c_pre_s3c1_20261014.tgz`, sha256 `dc063aa7…8dcf5`).
* **Why the role placement is not delivered in this round, stated as a dependency rather than as a
  capability claim**: moving a symbol pin moves that pin's connection point in every parent instance,
  and the parent wire graphics end at the old points (Virtuoso says so itself — `SCH-2162: "… symbol"
  has been updated since "… schematic" was last saved`). With no delete and no create-wire primitive,
  the repair has to be an in-place re-lay of the segments that already exist, which needs a
  collision-checked route per net against other nets' wires, other pins' rectangles and instance
  boxes. A half-verified version of that would leave the already-accepted library visually wrong or,
  worse, electrically shorted, and the task forbids rebuilding the library. The usable primitive is
  proven; the router is the remaining work, tracked as S3C1-9.
* **Screenshots**: measured again rather than remembered — the CIW window exists (`0x3a0000c`) but
  reports `Map State: IsUnMapped`, `import -window` fails with `unable to read X window image …
  Resource temporarily unavailable`, and the `xwd` fallback writes 0 bytes. Same conclusion as GUI-1,
  so `VISUAL_REVIEW = PENDING`, and no externally drawn picture is presented as an OA view.
* **Graph equivalence on today's state** (`results/evidence/sc1_s3c1_equivalence.csv`): the existing
  comparator re-run on a fresh read-back gives `S3C_OA_DEVICE_COUNT 39`, `S3C_OA_PORT_PINS 48`,
  `S3C_OA_SYMBOL_TERMINALS 48`, `S3C_CONNECTIVITY_MATCH 46/46`, `S3C_EQUIVALENCE_MATCH 8/8`,
  `S3C_OA_GRAPH_EQUIVALENCE PASS`, `failures=0`.
* **Statuses, kept apart** — read-back fields `MATCHED`; port directions `MATCHED`; symbol graphics
  present `MATCHED`; symbol pin placement `NOT_DONE`; schematic presentation `NOT_DONE`; editor check
  `PARTIAL` (schematics only); graph equivalence `PASS`; visual review `PENDING`.

The four open questions in section 9 are now answered by data rather than by attribution: 1 — the
symbols do carry graphics, and the placement needs a router, not a different import; 2 — yes for the
directions, and the OA side does carry them in batch; 3 — the DFF region placement is still importer
placement, deliberately untouched, because moving instances without re-routing breaks the drawing;
4 — unchanged, already recorded.

* **Manifests**: `sc1_s3c_round_manifest.csv` was regenerated because its hash of this report had
  expired (the audit found exactly that); `sc1_s3c1_round_manifest.csv` is new and was generated last,
  after the final edit of this file, by the same tool (`scripts/sc1_r2e_manifest.py`), which now also
  carries `s3c1_*` roles. Verified against the bytes: the S3C1 manifest matches **194 of 194** rows;
  the refreshed S3-C manifest matches 193 of 194 and the single difference is *its own row for
  `sc1_s3c1_round_manifest.csv`*, which was written after it — two lists that index each other cannot
  both be self-consistent, so the ordering rule (the new round's manifest is generated last) decides
  which one carries the stale cross-reference. Neither manifest hashes itself.
* **This round's own verifier**: `scripts/sc1_s3c1_check.py` asserts 35 claims against the repository
  bytes, including the *unwanted* state on purpose (all 48 pin sides recorded as `right`, the role
  match at 10 of 48), so a later regeneration cannot quietly disagree with what section 10 claims.
