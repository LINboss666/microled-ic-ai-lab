# SCAN-1 R3A — R3 delivery evidence restored, no simulation re-run

Round: **SCAN-1R3A**, start point `f199245b66de38e549693d3fec55d0d746075790` (the R3 head the cloud
pulled and reviewed as `EVIDENCE_PENDING` for two files, circuit progress retained). Scope: the
delivery-omission and evidence-overwrite risk the review named. **No circuit, case, corner, temperature,
load or deck changed; no Spectre, ngspice, preflight, operating point or Virtuoso call was made.**

Result: `R3A_DELIVERY_REPAIR: DONE`, and the R3 verdict itself is unchanged
(`R3_CONTROL_CHAIN: PASS`) — what changed is that the repository now contains the bytes its own report
claims.

## 1 What the review found, confirmed against the repository

| file | committed at `f199245` | claimed by `reports/scan_driver_r3_control_chain.md` |
|---|---|---|
| `results/evidence/sc1_r3_chain_manifest.csv` | **195 bytes, 1 line, 0 data rows** | "9 rows" |
| `results/evidence/sc1_r3_waveform_samples.csv` | **67 bytes, 1 line, 0 data rows** | "177 rows" |

Verified with `git cat-file -s` on all three R3 commits (`ff831a5`, `f0368f7`, `f199245`): both files
were already reduced at the **first** commit, so no commit ever held the delivered content. The two
surviving files are intact: `sc1_r3_chain_cases.csv` 129979 B / 428 data rows, and the dependency log
15624 B / 296 lines. The reviewer's consequence is right: from the remote alone the 2.223 ns end-to-end
figure was not recomputable and the case/raw identity was not checkable. `EVIDENCE_PENDING` was the
correct call, and it was not a DUT failure.

## 2 Root cause: my own verification run, through a real hole in the entry

The mechanism is the one the review reproduced, and it is now **confirmed, not merely plausible**:
`sc1_r3_chain_tt.py::main()` used to be

```python
authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
if not authorised:
    for cid in ids:
        R.add('R3_TT_EXECUTION', ..., 'NOT_RUN', ...)
...
S2.write_rows(out_csv, R.rows, ROWS_HDR)      # cases
S2.write_rows(man_csv, man_rows, MAN_HDR)     # manifest  <- empty list -> header only
S2.write_rows(samp_csv, samp_rows, SAMP_HDR)  # samples   <- empty list -> header only
```

so a refusal wrote every evidence file before returning 5. `man_rows`/`samp_rows` are filled only
inside `run_case()`, which the refused path never reaches; `write_rows` always writes the header. The
dependency log survived because its write is guarded by `if R.log:` and `R.log` was empty — that single
guard is why exactly two of four files were lost.

How it fired: after the delivered batch I ran the entry **without** `RUN`/`QODER_SIM_AUTHORISED` to
demonstrate the refusal exit code. I redirected `--out` and `--scratch` to a temporary directory, but
not `--manifest`, `--samples` or `--log` — so `cases.csv` was spared (redirected), the log was spared
(empty `R.log`), and the manifest and samples were truncated in place, at their default paths, inside
the repository. Everything happened before `git add`, and both files were still untracked at that
moment, so no `git diff` ever showed a modification. The numbers I quoted in the report (9 / 177) were
true of the batch that ran and were read from the pulled copies earlier in the session — they were not
re-read from the files being committed. Two of my own process rules were violated in that order of
operations: verify the artefact you are about to ship, and never treat a hash list as a content check.

## 3 What the existing checks could not see, and what now sees it

Every gate this round ran compares **bytes**: `precommit_safety_check.py` (PDK/credential/vendor
content), `sc1_r2e_manifest.py` (sha256 + size per file), `make_review_bundle.py`
(`MANIFEST_MATCH: PASS` = manifest vs zip listing). A header-only CSV is a perfectly valid byte string,
so all three passed while the evidence was empty. `provenance_check.py` and `netlist_stats.py` read
reports and netlists, not CSV row counts.

Added in this round (`scripts/sc1_r3a_verify_evidence.py`, offline, both environments, **17/17 PASS**):

```
manifest has 9 data rows, not a header alone        rows=9 bytes=4093
the manifest cases are unique                       unique=9
one run_id across the delivered batch               R3-CHAIN-20261013T122004Z
preflight/spectre/runner/verdict columns populated  rc=0/0 verdicts=PASS
every judged case is in the manifest and vice versa judged=9 manifest=9 diff=none
waveform samples exist with data rows               rows=812
every sample row has the 9-column header width      widths=[9]
sample times are present and finite                 times=812
sampled signal values parse to finite numbers       values=6280 non-finite=0
sample deck hashes equal the manifest deck hashes   PASS
the identity index records every delivered deck as hash-matched   not-OK=none
decks present in this copy re-hash to their manifest values       re-hashed=9 present=9 (guest)
                                                                    absent-in-this-copy=9 (Windows)
every raw data file is hashed, none missing         PASS
each exported event list recomputes its native delay and bound    events=18 agree=18
```

The deck line deliberately distinguishes the two copies: the decks and raw live in the guest's
`cadence_work/`, which is not shipped in Git, so re-hashing them is only possible there — **9 of 9
re-hashed on the guest**, and on Windows the same check reports them absent in this copy rather than
mismatched, which is the honest reading. The identity index itself is the delivered record of that
verification.

The last line is the reviewer's own missing capability: **18 of 18** propagation rows now reproduce
their `t_in`, `t_out`, delay (within the row's 0.001 ns print precision) and `t_next` from the
delivered file, on guest 2.6.6 and on Windows 3.12 identically.

## 4 Overwrite protection, before any restoration

Fixed in `sc1_r3_chain_tt.py` exactly as scoped — nothing else:

* a refusal now **prints and returns 5 before any file write**; no `cases`/`manifest`/`samples`/`log`
  is created, truncated or replaced;
* `--dry` with no `--out` writes its rows inside the scratch directory (`dry_rows.csv`) instead of onto
  the native evidence path.

`scripts/sc1_r3a_write_guard_check.py` runs in a fresh temporary directory: pre-seed four files with
sentinel data, hash them, invoke the entry unauthorised, then require rc 5, all four hashes unchanged,
and no `sim/` artifacts (proof the runner was never called); then the same for `--dry` without `--out`
and for the two rc-9 refusals. **9/9 PASS on Windows 3.12 and on guest 2.6.6.** The 4-check timing
selftest (`--selftest`) still passes **4/4** on both. No mock matrix, no new framework, no transaction
system.

## 5 Restoration, with the lineage that makes it auditable

**`sc1_r3_chain_manifest.csv` — restored byte-for-byte.** The guest copy of the delivered batch
survived intact at `/root/microled_ai_project/results/evidence/`: 4093 B, 10 lines, 9 data rows. It was
pulled with md5 verification and hashes to

```
31cb61e9c818a298470e7b95e1872d4ef42fd00a60eef1e2fe268e8924cb6622
```

which is **exactly the value the round manifest committed at `ff831a5` records for that path** — so the
restored bytes are the delivered ones, not a reconstruction. 9 unique cases, one `run_id`,
`preflight_rc=0`, `spectre_rc=0`, `state_verdict=PASS` for all nine, and `deck_sha256` identical to the
batch attested in the R3 report.

**`sc1_r3_waveform_samples.csv` — re-exported from the original raw, not restored.** The pre-clobber
177-row version (28300 B, sha `dfe48761bde7…`, attested the same way in `ff831a5`) still exists on the
guest, but its content had to change anyway because of §6 below, so it was not copied back. The new
file comes from `scripts/sc1_r3a_export_samples.py`, which reads the nine
`sim/<case>.raw/sw1.tran.tran` data files the delivered batch left on disk (9/9 present and hashed),
parses them with the audited parser (`sc1_read_psf.parse` via `sc1_r2e1_reread.samples_of`) and calls
the R3 entry's **own** selection function, so the native path and the export cannot drift apart. No
case was re-run; nothing was called but python.

`results/evidence/sc1_r3_delivery_identity.csv` (9 rows) ties each case to
`run_id`, deck path + manifest deck sha + the sha re-read from the file on disk (`all OK`), the raw
data path + its sha256, the row count exported, and the `preflight_rc` / `spectre_rc` / verdict columns
**labelled `ORIGINAL RUN RECORD (committed manifest)`** — they are quoted from the delivered native
record, not measured again in this round.

## 6 The event-anchoring defect the review named, and what the file now holds

`emit_samples()` took `case_def['windows'][0]['cause']`, which is the **150 ns priming edge** in every
case, then each node's first crossing after it — so the printed chain
`clk 150 ns → q 250.167 ns → en 250.356 ns → gate33 252.223 ns` mixed the initialisation clock with the
write edge, and the report's §5 repeated it.

Corrected: each declared propagation event is its own block, bounded by that input's **next crossing in
either direction** (`_next_after`, the audited strict bound), the priming edge has its own
`initialisation_crossing` row marked `NOT a cause of any judged response`, and every segment row carries
the `sample_group_index`, `time_s`, the values of all eight saved nodes at that instant, the case, the
event and the deck/raw hashes. 812 rows: 18 `event_crossing_list`, 9 `initialisation_crossing`,
385 `segment`, 400 `window_samples`.

The write event now reads, as one event:

```
input clk at 2.5e-07 s ; q at 2.50167135e-07 s ; qbar at 2.50254283e-07 s ;
en at 2.5035635e-07 s ; gate33 at 2.52222929e-07 s ; attribution bound t_next=3e-07 s
```

Also corrected in the report: the claim that `clk` was already at its plateau when `q` crossed is
**wrong** — at `q`'s crossing the exported samples give `clk = 1.02…1.07 V`, still inside its 2 ns ramp.
The propagation is attributed to `clk`'s 50 % crossing precisely because the clock edge is still moving
at the sampling instant.

Minimum coverage the review asked for is present: `r3_write_q1_on` clk 250 ns with `q`/`qbar`/`en`/
`gate33` 50 % neighbourhoods and the next input crossing; `r3_load5p` blank 500 ns with `gate33`
around 506.311 ns (`5.06310645e-07 s`); the fault case's `blanked_450` window as 200 consecutive real
samples showing `blank = 1.8 V` (high), `q = 1.8 V` (Q held), and `en = 1.8 V` / `gate33 = 3.20036e-09 V`
(not blanked) across the whole window. Other generated blocks were kept. 177 is not a target: **812 is
what the corrected selection actually produces**, and the report says so.

Nothing was interpolated into the file: the rows are the simulator's own samples; interpolation happens
only in the crossing-time helper, which is the audited tool's rule, and its result is printed in the
event row.

## 7 Report and pre-design wording corrected

1. `reports/scan_driver_r3_control_chain.md`: header now states the two files reached Git as headers
   and points here; §2 scopes `9 + 9 = 18` to the delivered batch and adds a batch table (the
   `…T120713Z` batch's own CSVs were overwritten at the same paths → **NOT RETAINED**, whole-round
   process total is **UNKNOWN** and explicitly not derived from directory file counts); §5 replaced
   with the single-event table plus the corrected plateau statement; §6 records the 18/18
   recomputation; §9 documents the new refusal semantics.
2. `reports/scan_driver_r3_output_stage_plan.md`: the PMOS body is a **p-type body in an n-well**, not
   "p-well", and `D/G/S/B` is declared as intent with the real spelling to be read off the PDK cell —
   with layout/DRC/LVS/PEX out of course scope, so it is a modelling question and **not** an S3
   precondition; `Ron` is now `Ron = (V(S) − V(D))/I(D)` across **the switch's own** source-drain
   (`VSCAN − V_electrode`), and the report says explicitly that `VSCAN − V_data_node` includes the LED
   and the data driver's absorption voltage and must not be used as `VDS`; P8 reworded accordingly.
3. Added to §7 the two blocking sets: P1/P2/P3 gate any *panel* claim, while a `POC_ASSUMPTION`
   3.3 V-domain characterisation of a p33 device's own `Ron`/current/gate charge does **not** need LED
   `Vf`. That is written as an **S3-A proposal**, labelled as such, with "nothing of S3-A was run in
   this round" and "needs the reviewer's decision first" stated in the same paragraph.

## 8 Boundaries, gates and what remains open

* Frozen and unchanged: the three accepted cells, the new wrapper, the audited
  reader/delay/vtx/preflight/supply/runner tools, the S1/S2 generators, the call contract, and the 428
  native rows. `git diff f199245 -- <protected list>` is empty; `sc1_r3_chain_cases.csv` and the
  dependency log were not touched.
* Tools channel only: `guest.sh run` / `pull` / `push_chunked.sh`. No DHCP/NAT/service/`ifcfg`/`.vmx`
  change, no VM power or snapshot operation, no licence touch, no PDK or OA write.
* Gates re-run at delivery: safety (staged + history), `provenance_check`, `netlist_stats`, and now
  `sc1_r3a_verify_evidence` — all PASS; no raw PSF, model card, credential or vendor absolute path is
  committed (the identity CSV stores project-relative paths and hashes only).
* **Open / not claimed:** the original 177-row samples bytes are attested in Git by hash at `ff831a5`
  but are not themselves committed, and are superseded by the re-export; the earlier `…T120713Z`
  batch's artefacts are not retained; the whole-round Spectre process total is UNKNOWN;
`OUTPUT_STAGE_PRE_DESIGN` stays `PARTIAL`; `S3_POWER_STAGE: NOT_RUN`, `S4_CHAIN: NOT_STARTED`,
`SOA: NO`, `AUTONOMOUS_POWER_FAIL: NOT_IMPLEMENTED`.

## 9 Review bundle equality — bytes **and** row counts

The review bundle is local-only, but it must not be a different artefact from what Git carries, and a
hash list that matches itself proves nothing about content. Every R3 CSV was therefore compared to the
committed blob **and re-parsed inside the bundle**:

| file | sha256 in Git | sha256 in the bundle | identical | data rows read back |
|---|---|---|---|---|
| `sc1_r3_chain_manifest.csv` | `31cb61e9c818a298…` | same | yes | **9** |
| `sc1_r3_waveform_samples.csv` | `7e3dfb6d5dabfc4e…` | same | yes | **812** |
| `sc1_r3_chain_cases.csv` | `57b539ea4abcc60c…` | same | yes | **428** |
| `sc1_r3_delivery_identity.csv` | `59d674b05066a0ba…` | same | yes | **9** |

One layout note a reviewer will hit: `make_review_bundle.py` nests each group under its own top
directory twice (`results/results/evidence/…`, `reports/reports/…`) while scripts land under
`source/scripts/…`. That is pre-existing behaviour of an accepted tool and was not touched here; the
files themselves are byte-identical to the repository, so it only affects where to look.

The **remote** was read back independently of the local repository, at
`0405e6d0e6c1c2ed35af8e72ac2ffc41a6ee65df` through `gh api`: `sc1_r3_chain_manifest.csv` is served at
**4093 bytes** (it was 195 at `f199245`) and `sc1_r3_waveform_samples.csv` at **260849 bytes** (it was
67). A direct anonymous `raw.githubusercontent.com` fetch returned 0 bytes from this host at the same
moment, which is the known github.com:443 transport instability rather than a content difference — the
`api.github.com` route answered, so the sizes above are the served ones.

Stopped again at the **R3 single-channel control-chain + output-stage-plan review gate**, this time with
the evidence files matching the report. Next decision is the cloud's: recompute the delays from
`sc1_r3_waveform_samples.csv`, then choose between the S3-A characterisation proposal and the panel-level
route that needs P1/P2/P3.
