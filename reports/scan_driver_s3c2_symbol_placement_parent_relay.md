# SCAN-1 S3-C2 — Symbol pins to their roles, and the parents that follow them

Task book: `MicroLED_Qoder_SCAN-1S3C2_22af9d0_finish_views.md`, start commit
`22af9d025457c077aeeb7ca10ace08049550de9e`, branch `poc/scan-driver-1ch`.
NEW_SIMULATION_RUNS = 0. Only `cadence_work/s3c_oa/microled_scan_s3c` was written.

## 0 Status, per dimension (each one is a separate verdict, none implies another)

| dimension | state | evidence |
|---|---|---|
| READBACK_FIELDS | MATCHED (unchanged from S3C1, re-read from disk this round) | `results/evidence/sc1_s3c2_log_final_verify_disk_reopen.txt`, `sc1_s3c2_comparator_final.txt` |
| PORT_DIRECTIONS | MATCHED 96 of 96, 0 mismatch | `results/evidence/sc1_s3c2_ports.csv` |
| SYMBOL_GRAPHICS | EXIST (8 views, body + pin rects + stubs + labels) | `results/evidence/sc1_s3c1_graphics.csv` (recomputed on the new dump) |
| PIN_PLACEMENT | **DONE 48 of 48** on the role side | `S3C1_SIDE_MATCHED 48 of 48`, `results/evidence/sc1_s3c1_symbol_side.csv` |
| SCHEMATIC_PRESENTATION | **PARTIAL** — the bank's parent is re-laid and role-arranged; `sc1_ls_c1_top_r2d` and `sc1_r3_scan_chain_1ch` are blocked and sit at their pre-S3C2 geometry | §5, §6 below |
| EDITOR_CHECK | 0 errors in all 8 schematics; warnings 0…39 per view, itemised in §6 | `results/evidence/sc1_s3c2_editor_check.csv` |
| GRAPH_EQUIVALENCE | PASS — 39 devices, 7 sub-instances, 46/46 connections, 8/8 canonical graphs, after disk reopen | `results/evidence/sc1_s3c2_comparator_final.txt` |
| VISUAL_REVIEW | **PENDING / no screenshot delivered** — see §7 | `reports/scan_driver_s3c1_*` X measurements, §7 |
| parent-pin geometric attachment | 14 of 39 sub-instance pins lie on a real same-net wire segment | `results/evidence/sc1_s3c2_attach.csv`, §5 |

## 1 Start conditions re-checked before any write

local HEAD = `22af9d0` = the reviewed start; `git ls-remote`/`gh api` read-back agrees; the
teammate branch `origin/gexing321/scan-driver/c2mos-schematic` = `411ac27` was not touched; the
work tree held only this round's untracked helpers; no unknown upstream commits appeared. Guest:
`ps` showed 0 Virtuoso/dbAccess processes and `find … -name '.cdslck*'` was empty, so no cellview
lock was held against anyone. The whole library was archived before the first write
(`backup_microled_scan_s3c_pre_s3c2_20261014.tgz`, sha256
`ce98f044b7f4b0138b9c84b5ddce3d5c9a99860009d33c2045740204991aaa33`) together with the per-file md5
list `cadence_work/s3c_oa/logs/pre_s3c2_lib.md5` (76 files) and, before the parent re-lay,
`logs/pre_s3c2_relay_lib.md5`.

**What this round changed on disk, stated as phases** (section 2 of the task book forbids calling a
phase-local comparison "the library was untouched"): the Symbol placement pass rewrote 8 symbol
views; the parent re-lay rewrote `sc1_scan_power_1ch_s3c:schematic`; two further schematics were
rewritten and then restored from the backup (md5-verified, §5). The five leaf schematics and all
read-only inputs are byte-identical to the start.

## 2 Section 3: the documented interfaces, measured on this task's own copies

`skill/sc1_s3c2_api_probe.il` on two scratch cellviews copied out of the delivered views
(`dbCopyCellView`, saved, reopened, then deleted). Every write form in the task book works here, so
the residual claim from S3C1 that batch mode "cannot draw" is retracted:

| call | result | object-count evidence |
|---|---|---|
| `dbMoveFig(fig cv list(list(dx dy) "R0" 1.0))` | moves; the negated origin restores | bBox shifted by exactly that delta, then back |
| `dbCreateRect(cv lpp list(list(x1 y1) list(x2 y2)))` | figure created | `S2-COUNT shapes` +1 |
| `dbCreateLine(cv list("wire" "drawing") …)` | figure created, `objType="line"` | shapes +1 |
| `dbCreateLabel(cv lpp pt "s2probe" "centerLeft" "R0" "stick" 0.0625)` | created; `justification` reads back | `was=nil now="centerLeft"` |
| `dbMakeNet(cv "s2_probe_net")` | net object returned | nets +1 |
| `dbCreatePin(net figure "s2_probe_net")` | real pin on a real figure | terminals 3 → 4 |
| `dbDeleteObject(fig)` | deleted | shapes 16 → 15 |
| `fig~>net = netObj` | accepted, `f~>net~>name` reads back the name | log lines `S2-SETNET-ASSIGN` |
| `i~>xy = list(x y)` on an **instance** | moves it; the bBox follows; the port's own name display moves with it | `S2W-MOVE-INST … bbox-was=… bbox-now=…`, then `S2W-SHAPE` after the moves |

Two attribute facts that cost a wasted round each and are now measured, not assumed:
`objType`/`purpose`/`justification` are **strings** (`equal(f~>objType "textDisplay")` = t, the
symbol form = nil; `type()` printed next to `%L` in `sc1_s3c2_log_attribute_types.txt`), and a
`label` figure exposes **no text attribute** in this build — `~>text`, `~>strings`, `~>val`,
`~>label`, `~>name` all read nil, `dbShow` does not exist. So this round never claims "the label
text exists"; it reports the label's figure, its anchor and the **net object** it carries
(`results/evidence/sc1_s3c2_wire_labels.csv`), which is readable and is what the connectivity uses.

## 3 Symbol placement: 48 pins to their role sides (section 5's target)

`scripts/sc1_s3c2_place.py` computes a plan (pitch 0.25 µm on the side, 0.40 µm on the top/bottom
rows so labels do not collide; pin rect 0.175 × 0.05; stub 0.125; label box 0.32 × 0.08), rejecting
any plan with a collision, and `scripts/sc1_s3c2_emit_il.py` inlines `skill/sc1_s3c2_apply_sym.il`
into one self-contained file (a nested `load` leaves the inner procedures unbound at the call site —
measured in S3C1, reproduced here). Applied to all 8 cells in one session, saved, closed, reopened:

```
S3C_RUN_OA: PASS   SAVES=8 OPENS=8 PLACED_FULL=48 REFUSES=0
S3C1_SIDE_MATCHED 48 of 48        (recomputed on the post-placement dump)
S3C2_PORT_ROWS=96 matched=96 mismatched=0
```

Input left, output right, positive supplies top, `vss` bottom, and for the bank specifically
`bgate` left / `scan` right / `vscan` top. The rule, the role table and the counts are in
`results/evidence/sc1_s3c1_symbol_side.csv`; the corrected role breakdown (18 inputs, 10 outputs,
13 supplies, 7 grounds) is in §0 of the S3C1 report's retraction note.

The rollback path was exercised, not just asserted: restoring the pre-S3C2 archive reproduced the
pre-round library (`ROLLBACK_VERIFIED_LIBRARY_BACK_TO_BASELINE`), and the same restore was used
twice more in §5.

## 4 The closed loop on a copy, as section 5 demands

`sc1_scan_power_1ch_s3c:schematic` (the parent of the 3-pin bank) was copied to
`s3c2_loop_top`, and the whole sequence ran on that copy first: **move → delete the view's wire
figures → draw one figure per planned segment from the connection the database reports → give it the
net object → schCheck → dbSave → dbClose → reopen from disk → read back.**

```
S2W-COPY-SRC "sc1_scan_power_1ch_s3c" open=t shapes=37 insts=11 nets=10
S2W-MOVES applied=11 refused=0        S2W-DELETE wire-figures-deleted=28
S2W-SCHCHECK raw=((0 0))               S2W-DRAW segments=10 labels=10 errors=0 warnings=0
KC-TERM … "Xbank" "bgate" net="gate33"     KC-TERM … "Xchain" "gate33" net="gate33"
```

Three things only this loop could establish, each measured rather than reasoned:

1. a port's name display travels with its `iopin` instance, so no separate text move is emitted
   (an emitted text move would have moved the same display twice);
2. an internal net (no port pin to anchor its name) comes back auto-named — `gate33` became
   `net11` — after its figures were replaced, and `~>name` assignment on a net object is refused
   (`RP-SET rc=nil`); a **wire label sitting on the wire** holds the name, which is what the
   delivered top view now does for `gate33`;
3. deleting a net's figures before drawing the replacement is what triggers the rename, so the
   applier draws the new figures first and deletes the remembered old ones after.

## 5 The delivered top view, and the two parents that are blocked

Applied to the real library in leaf→root order and re-read from disk in a separate session
(`sc1_s3c2_log_final_verify_disk_reopen.txt`):

| view | moves | wire figures deleted/created | schCheck | outcome |
|---|---|---|---|---|
| `sc1_scan_power_1ch_s3c` | 11 applied, 0 refused | 28 / 10 (+10 labels) | **0 errors 0 warnings** | kept, re-laid |
| `sc1_ls_c1_top_r2d` | 8 applied | 36 / 26 (+11 labels) | **1 error**: `Can't tap "<vdd33>" from net "core_ok33"` | **restored to baseline** |
| `sc1_r3_scan_chain_1ch` | 11 applied | 52 / 34 | **3 errors**: `Terminal "vdd18" shorted to terminal "blank"`, `… to "core_ok33"`, `Can't tap "<vdd18>" from net "core_ok33"` | **restored to baseline** |

Both restorations are md5-identical to `logs/pre_s3c2_lib.md5`
(`07190996e7e548f8cf0e1b59befd5a9e`, `e330aa5879cf3dca818cf3ab2fc378da`), so the delivered library
holds no half-finished drawing.

The re-lay plan is not a hand-tuned sketch: `scripts/sc1_s3c2_route.py` derives the block order from
the frozen sub-instance table (`Xchain.gate33 → Xbank.bgate`; `Xff.qbar → Xgate`, `Xgate.en → Xls`;
`Xcore.y → Xnand`), places the ports by role (inputs left, outputs right, supplies top, `vss`
bottom), and routes on a Hanan grid with Dijkstra on wire length, refusing every edge that touches an
instance body, another net's connection box, or another net's already-drawn segment — in Virtuoso a
touch is a connection, so a crossing of two nets is a short, not cosmetics. It retries a bounded
set of routing orders and, for a net with no crossing-free path, draws only short outward stubs
with a net-name label (§5 allows exactly this). `--fallback keep` leaves such a net's existing
figures untouched instead; both strategies and the outward-facing port stubs were tried on the two
views, all three produced schCheck errors, so both views are reported blocked rather than drawn
wrong. Their 25 sub-instance pins are consequently **not** on a same-net segment:

```
S3C2_ATTACH rows=39 reached=14 unreached=25      (results/evidence/sc1_s3c2_attach.csv)
  reached: the 11 pins of the re-laid top view + the 3 that were already attached
  unreached: 9 in sc1_ls_c1_top_r2d, 16 in sc1_r3_scan_chain_1ch
S3C2_CROSSNET contacts inside sc1_scan_power_1ch_s3c = 0
```

`sc1_s3c2_crossnet.csv` also lists 273 wire-wire contacts, all but three of them in the five leaf
views and the two rolled-back views, i.e. in geometry this round did not write. Those are the
importer's own drawings, where the extracted netlist still matches the golden table cell for cell;
this round therefore treats the geometric overlap test as a guard on what it drew (0 inside the
re-laid view) and the electrical verdict as the netlist comparison in §6, and says so instead of
quietly dropping either number.

## 6 Electrical re-read after the writes (section 6, reusing the existing comparators)

`scripts/sc1_s3c_verify_oa.py` on the fresh disk-reopened readback:

```
S3C_READBACK_ROWS cell=8 device=39 inst=55 net=64 pin=48 symbol=8 symterm=48
S3C_OA_DEVICE_COUNT: 39   S3C_OA_SUBINSTANCES: 7   S3C_OA_PORT_PINS: 48   S3C_OA_SYMBOL_TERMINALS: 48
S3C_DBCHECK_ALL_T: yes    S3C_CONNECTIVITY_MATCH: 46 / 46    S3C_EQUIVALENCE_MATCH: 8 / 8
S3C_OA_GRAPH_EQUIVALENCE: PASS      failures=0 notes=3
```

The three notes are the honest ones: `q`, `qbar`, `en` (and `x` in `sc1_ls_c1_top_r2d`) are internal
nets with 1 or 2 terminals and no port pin — that is the accepted netlist, not a defect of this
round, and `mn_nt` still carries `S=ns_m`, `B=vss` (§5's body warning) because no leaf view was
touched. Editor check per view, from `S10|C|` lines: 8/8 schematics with **0 errors**; the symbol
views answer `schCheck=nil`, recorded as "no schCheck for this view type", never as a pass. The
warning counts (0 in the re-laid top, 1…39 elsewhere) are dominated by `SCH-2162` — "the Symbol view
has been updated since this schematic was last saved" — which this round *caused on purpose* by
moving Symbol pins; it is listed per view in `sc1_s3c2_editor_check.csv`, and it disappears in the
view where the re-lay plus Check-and-Save ran (top: 0 warnings), which is the per-case handling
section 5 asks for rather than a timestamp trick.

## 7 No screenshot: what was tried and what is needed

Section 4 allows two independent GUI launches for this round. The measurements from S3C1
(`results/evidence/sc1_s3c1_gui.log`, `sc1_s3c1_gui_run.txt`) are unchanged and still the blocker:
a real `virtuoso` session on `:0` starts and loads `schView/wireEdit/selectSv.cxt`, but the windows
stay `Map State: IsUnMapped`, `import -window` answers "unable to read X window image … Resource
temporarily unavailable", and `xwd` writes 0 bytes. S3C2 did not re-run that experiment (the task
book forbids another broad API probe and the display service is out of bounds), so:
**VISUAL_REVIEW = PENDING, 0 screenshots delivered**. What is needed is one window that a real X
session maps — the shortest route is the user's own open Virtuoso: `geOpen(?lib
"microled_scan_s3c" ?cell "sc1_scan_power_1ch_s3c" ?view "schematic" ?mode "r")` and the same for
`symbol`, then capture. `skill/sc1_s3c2_ciw_parents.il` prints the current pins/nets of the two
blocked views for whoever finishes them there.

## 8 Retractions and corrections this round owns

1. "the S3C1 manifest matches 194 of 194 rows" — wrong; against the bytes a fetch actually gets it
   matches 192 of 194, and the refreshed S3-C manifest 191 of 194. The two manifests share two
   defects, and the S3-C manifest has a third:
   * `results/evidence/_incoming/sc1_s3c1_symbol_side.csv` is listed although the scratch area it
     lives in was never tracked, so no remote byte can verify the row (`NOT_IN_GIT`);
   * `results/evidence/sc1_s3c1_comparator_final.txt` records `8cd9229a8398…`/766 while the commit
     serves `145142988e32…`/750. Verified root cause: the manifest hashed the CRLF Windows working
     copy, and `.gitattributes` (`* text=auto eol=lf`) commits the LF-normalised bytes -- the file's
     content was never wrong (`EOL_NORMALISED`, 16 CRLF lines). This round's manifest hashes the
     LF-normalised bytes for that reason.
   * the S3-C row for `sc1_s3c1_round_manifest.csv` matches neither the working copy nor the blob
     while those two agree, so it was written against an earlier capture (`STALE_ROW`).
   Detail: `sc1_s3c2_manifest_corrections.csv`, raw: `sc1_s3c2_manifest_audit_output.txt`.
2. "13 inputs / 11 supplies / 8 grounds" — the role table gives 18 inputs, 10 outputs, 13 supplies,
   7 grounds across the 48 Symbol ports.
3. Any remaining suggestion that batch mode cannot draw or delete: retracted by §2's measurements.
4. "probe4 counted six measured failures of the create calls" — three of those used a layer
   (`"shape"`) these views do not carry and one used `getd('dbDeleteObj)`, a name that does not
   exist; the counts were never six failures of the documented form.

## 9 Limits, and what this round must not be read as saying

`SCHEMATIC_PRESENTATION` is PARTIAL and `VISUAL_REVIEW` is PENDING; the parent repair is delivered
for the bank's parent only. Layout/DRC/LVS/PEX were not touched and the eight schematics are
drawings, not a floorplan. `FINAL_VSCAN`, the LED I-V, `N_active`, real electrode RC and the power
budget remain **NOT DEFINED**; the TT/27 °C, 1.8/3.3 V and seven-transistor p33 bank remain POC
conditions; `SOA_SIGNOFF = NO`; autonomous power-fail behaviour is not implemented. Nothing in this
round changed a circuit, a device size or a simulation input, and no circuit or panel conclusion is
drawn from the re-arrangement.
