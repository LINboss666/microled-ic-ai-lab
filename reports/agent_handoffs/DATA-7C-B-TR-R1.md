# DATA-7C-B-TR-R1 handoff

To: the independent reviewer. From: the executing agent. Date: 2026-10-27/28 (UTC stamps in the files).

```text
TASK_ID=DATA-7C-B-TR-R1
BRANCH=poc/data-pam-d7c-b-tr-r1
BASE=398c9e852c16db85cbfa4539e859534e117ff0d2
REVIEWED_CONTENT=f49ba9d78190f8c3da2adca9dbd4fb3e48d26841
EVIDENCE=results/evidence/dd1_d7c_b_tr_r1_r20261027_143223_4c8a81
REPORT=reports/dd1_d7c_b_tr_review_fix_r1.md
TASK_BOOK_COPY=reports/tasks/DATA-7C-B-TR-R1.md
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

## What this round had to fix, and where the proof is

| review finding | repair | proof in the evidence directory |
| --- | --- | --- |
| F1 recompute started from the published Q | stdlib-only recomputer integrating from the exported native samples; frozen DC table shipped byte-for-byte; three forgeries wired to the real entry | `native_sequences/`, `dependencies/dc_matrix_dut.csv`, `recompute_r1.json`, `probe_forgery/r1_recompute_forgery.json` |
| F2 a stale `Account` could overwrite a charged row; `done_preflight=None` bypassed the meter preflight; retries overwrote answers | disk re-read + validation inside the lock, atomic replace, row-named pulls, mandatory preflight binding | `scripts/dd1_d7c_b_tr_run.py` selftest (44/44), `probe_after/probe_tr_review_gaps.json` |
| F3 an enable moved 10 ns late still converted | per-frame endpoint equality in the trace's own integer units, black frames, safety fault/hold/withdrawal/START/load rules, deck wave comparison | `scripts/dd1_d7c_b_tr_trace.py` selftest (50/50), `reconversion_*.json` |
| F4 import rules and the black-window shutoff | format and deck checks at every reachable entry, `SHUTOFF` over black-window peaks | `scripts/dd1_d7c_b_tr_measure.py` selftest (61/61), `statuses.csv` |

The nine reviewer counterexamples were reproduced first with the instrument kept byte-for-byte
(`probe_before`, 9/9 reproduced, rc=0) and re-run after the fixes (`probe_after`, rc=1: six of the
nine no longer reproduce, all positive controls still pass, 0 launches, only `git` and `python`
spawned). The three recompute probes of the instrument run the superseded table-only template on a
copy that carries no sequences, so they are recorded as `INSTRUMENT_NOT_APPLICABLE`; their closure
evidence is `tests/dd1_d7c_b_tr_r1/probe_r1_recompute_forgery.py`, which proves a complete clean
package re-derives (838/838) and then refuses each of the three forgeries by name.

## What is published here

* Ten statuses, seven from the electrical record plus `NATIVE_SEQUENCE_REINTEGRATION`,
  `RTL_INPUT_PROVENANCE`, `BUDGET_ACCOUNTING_STATUS`; the dynamic and nominal FAILs of the native
  round are preserved with the same windows and the same values.
* `windows_all.csv` re-extracted with the patched tools, `window_diff_r1.csv` stating every cell that
  moved (222, all newly added per-target settling columns; 1369 cells byte-identical).
* 18 native sequences, 2,562,403 samples, printed tokens verbatim, gzipped and carried as base85
  text containers, cut into ≤240 KiB parts because the repository safety rules admit no unknown
  binary extension and its history gate refuses a blob over 512 KiB; 142 delivered files, 32,193,607 B
  tracked against the 32,505,856 B export ceiling, and 33,088,723 B added to the repository by this
  round at the record commit (32,818,620 B of it numeric evidence), which is under the task's 32 MiB.
  `native_manifest.json` records the whole and per-part digests and
  `--verify` rejoins them: 19 verified, 2 named as excluded, 0 problems. The identity chain of every
  answer and the budget are published the same way (task 24, main ledger 22, occupied 21 with `T001`
  UNCERTAIN still charged).
* The reviewer package is built from committed blobs and now carries the import and input closure of
  the entries it promises to run, so inside the extracted copy, with no Git and no guest,
  `independent_recompute.py` re-derives 838/838 at rc=0 and
  `dd1_d7c_b_tr_r1_native.py --verify` rejoins every delivered part at rc=0 (19 verified, 2 named as
  excluded, 0 problems). Its bytes and sha256 are recorded outside the archive, in the delivery
  receipt.
* The two real traces are published by **identity** (name, byte count, uncompressed digest, the digest
  the native conversion recorded) and by their re-read result, not by copying their bytes into the
  tracked tree: `*.vcd` is a family this repository never tracks and those 416,278 B are what the RS-
  SWITCH and RS-FULL internal fragments needed to stay under the ceiling. Their gzip copies travel in
  the reviewer package, admitted there by the same digest check.

## What this round did not do

No simulator of any kind (no `-h`, no version, no syntax probe, no dynamic pre-check), no Icarus or
vvp, no OA, no SSH or guest connection, no credential, model-card or licence read, no circuit change,
no PDK change, no merge, no acceptance registration, no rewrite of any published report, handoff,
receipt or task book. The old published directory carries **no change of its own**: mid-round the
judging entry of the shared record tool rewrote three of its tables (the event and its exact byte
effects are in §9 of the fix report); those bytes were parked outside the repository, the committed
content was restored, and every file of that directory now equals its HEAD blob, which the handoff
JSON re-derives as `delivery_integrity.native_evidence_mismatches`. The judging entry no longer
publishes at all, and the record selftest proves it writes nothing into the directory it judges. A
partially built directory of this round's own aborted registration attempt was moved aside outside the
repository rather than deleted.

## Left open for the reviewer

* The internal 26 columns are re-integrable for the five short runs and, as declared native fragments,
  for RS-SWITCH (8 windows, 1,603,951 B) and RS-FULL (24 windows, 3,145,267 B). The HYB-120 and
  HYB-200 fragment sets (1,319,679 B and 977,397 B) do not fit the 312,249 B the ceiling leaves, so
  `native_manifest.json` states them as exact byte gaps and the per-step internal detail for those two
  cases stays in the published row tables rather than being claimed as re-integrable.
* Whether the delay attribution may be read as anything stronger than an observed threshold crossing.
* Whether `RTL_PROCESS_COUNT=4`, derived from four distinct executable digests on five rows, is the
  figure the reviewer accepts.
* The two escaped native processes keep their recorded charge; their deleted raws stay unrecoverable.

Nothing in this directory is self-registered: `ACCEPTANCE_REGISTERED=NO`, `MERGE_PERFORMED=NO`,
`NEXT_NATIVE_STAGE_AUTHORISED=NO`.
