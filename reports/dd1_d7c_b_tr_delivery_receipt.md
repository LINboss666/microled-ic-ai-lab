# DATA-7C-B-TR delivery receipt

Written by the delivery step after the branch was pushed. It records read-back evidence and the
reviewer package identity; it does not register an accepted version, does not give a GO and does not
authorise any next stage.

## Identity under review

- task `DATA-7C-B-TR`, approved 2026-10-26 (Asia/Shanghai), response `YES`
- base `61621f6e3d887082ecd6a7ecc1c771f8e509a24a`, branch `poc/data-pam-d7c-b-tr`
- round commits, oldest first:
  - `dc2925d47a5885e1d3464feb9a9aa5ff709f1865` contract, decks, converter, runner, measurement
  - `ccb003480ee00ae51981153c945c69f5c41561e0` four tool defects the first native runs exposed
  - `7647fe1cc6f82066fcabd578e9f98de4bc69a0cd` recorded signal names and charged-process count
  - `9e96bdf46534f0a30b3f66392b897fe86f0a2979` charge processes, not bookings; half-open frames
  - `86fc70862ad27e37a9d3838fe7b892f3e281828e` hybrid run copies and the launch output guard
  - `c8b50e16547d4faf39b8f51865134b2d87b4f876` native measurement, black windows, record stage
  - `f49ba9d78190f8c3da2adca9dbd4fb3e48d26841` packaging replay and the round scope fix
- **content under review is `f49ba9d78190f8c3da2adca9dbd4fb3e48d26841`.** This receipt is a later
  commit that adds only this file, so the SHA of the receipt commit cannot be written inside it.

## Push and read-back

| step | value |
|---|---|
| push command | `git -c http.proxy=http://127.0.0.1:7892 push origin poc/data-pam-d7c-b-tr` |
| push started UTC | `2026-10-27T04:14:10Z` |
| push finished UTC | `2026-10-27T04:17:15Z` |
| push rc | `0` (`c8b50e1..f49ba9d`, new branch created on the first push of this round) |
| read-back path 1 | `git -c http.proxy=... ls-remote origin refs/heads/poc/data-pam-d7c-b-tr` -> `f49ba9d78190f8c3da2adca9dbd4fb3e48d26841` |
| read-back path 2 | `gh api repos/LINboss666/microled-ic-ai-lab/git/ref/heads/poc/data-pam-d7c-b-tr` -> `f49ba9d78190f8c3da2adca9dbd4fb3e48d26841` |
| main after this round | `refs/heads/main` = `23e471cb936b421ee97e1250c3be06edf96f9937`, unchanged |
| merge performed | NO |

The two read-back paths agree with the local `git rev-parse HEAD`. Both were run after the push and
their own UTC timestamps are printed above; the push start and finish are the two lines that bracket
the `c8b50e1..f49ba9d` update.

## Reviewer package

| field | value |
|---|---|
| file | `review/dd1_d7c_b_tr_package_f49ba9d.zip` |
| bytes | `371126` |
| sha256 | `62d4d2e8e2f1814c2cbb75fea4859234a5b5324b31ef6202cae52fe302b7cc1d` |
| built from | `f49ba9d78190f8c3da2adca9dbd4fb3e48d26841`, base `61621f6e3d887082ecd6a7ecc1c771f8e509a24a` |
| files packaged | `91`, refused by the packaging rules `0` |
| history safety gate rc over the packaged range | `0` |
| out-of-repo replay | extracted to `review/dd1_d7c_b_tr_replay_f49ba9d`, `RECOMPUTE 198/198`, rc `0` |
| digest recorded where | here and in the delivery message, never inside the archive |

`independent_recompute.py` re-derives every published number from the packaged tables, the contract
and the two ledgers: the QLSB of each case, both error columns, the T50 as the native 0.9 V interval,
the signed split of Q, each pair difference against the frozen convergence limit, the seven status
names, and the charged-process counts against the approved ceilings. It does not import this round
measurement module and it starts no simulator.

## Budget actually consumed

- Spectre: 19 account rows, 19 charged processes, 2 stray processes charged from the recorded
  budget adjustment, enforced ceiling 22 of the approved 24, **3 left unused**.
- RTL: 5 ledger rows, 4 charged vvp processes of the approved 4, **0 left**. The fifth row is a
  duplicate booking of one start, honoured only because the ledger itself proves it.
- Icarus compilations: recorded in `rtl/compile_*.json`, not charged, as the task book states.
- OA writes 0. PDK, library, schematic and layout untouched. Guest writes confined to
  `/root/microled_ai_project/cadence_work/dd1_d7c_b_tr/r20261026_132228_3fc148/`.
- New tracked bytes for the whole round: 1,095,277 over 87 files, under the 32 MiB ceiling. Raw
  answers, Spectre logs, guest logs, the compiled vvp and the unpacked traces stay on this machine,
  with their digests and local paths in `provenance.json` and `rtl/tool_identity.json`.

## Statuses as published

| status | verdict |
|---|---|
| EXECUTION_COMPLETENESS | PASS |
| EVIDENCE_INTEGRITY | PASS |
| DYNAMIC_CHARGE_STATUS | FAIL |
| NOMINAL_CHARGE_STATUS | FAIL |
| SETTLING_STATUS | PASS |
| SHUTOFF_STATUS | PASS |
| CONVERGENCE_STATUS | PASS |

The dynamic FAIL is four windows: TR-OFFCODE W3 at 0.5835, RS-SWITCH W3 at 0.5824, HYB-120 W2 at
0.5639 and HYB-120 W3 at 0.5421 LSB in absolute value, all over the frozen limit of 0.5. The nominal
FAIL is fourteen windows, up to +12.72 LSB at code 111, which follows from the +2.55 percent scale
deviation the DC round measured in the reference. No circuit was changed to turn either into a PASS,
and a dynamic pass is not presented as an uncalibrated grey-scale pass.

## Verification on the delivered bytes

- contract 35/35, decks 19/19, trace 40/40, measure 51/51, runner 27/27, record 32/32
- record gates 36/36
- `TR_DECK_CHECK PASS (9 decks, 9 preflights)`
- `git diff --check` and the staged safety hook clean over 60 objects
- no path tracked at `61621f6e` was modified or deleted; the working tree is clean apart from the
  deliberately local raw answers and logs

## Known gaps, stated rather than smoothed

- start `R004` carries no trace digest in the RTL ledger because it was settled before that column
  existed; its trace is bound through `hyb_inputs.json`, the deck identity block and the packaged
  gzipped copy, whose digest is verified before packaging.
- the two stray selftest launches left no raw bytes behind and the earlier of the two logs was
  overwritten by the later one; only the later digest has bytes behind it. No number from either is
  published.
- the repository ignore rules keep `*.vcd` and `*.gz` out of the object store, so the traces ship in
  the reviewer package instead of in git; the VCD to PWL conversion can be re-run from the package
  but not from a bare clone.
- the full object-store safety scan reports one pre-existing unreachable blob of 3,583,407 bytes from
  an earlier round. It is not part of this round, nothing here created it, and it was not pruned:
  pruning a shared object store is destructive and needs a decision from the user.
- the inherited preparation-round banner inside the deck templates still reads
  `Contract state: PROPOSED_FOR_REVIEW`; it is comment text of the frozen base blob and cannot be
  edited without breaking the byte-identity rule. The governing state of this round is
  `USER_APPROVED_FOR_EXECUTION_DATA_7C_B_TR`, recorded in the deck identity block and in the contract
  digest each deck stamps.

```text
COMPLETION_LEVEL=RTL_TRACE_DRIVEN_PAM_TRANSIENT_MEASURED_TT
NEW_SPECTRE_LAUNCHES=19/24 (plus 2 stray processes charged; 3 margin unused)
NEW_RTL_SIMULATIONS=4/4
NEW_OA_WRITES=0
CANDIDATE_DUT_CHANGED=NO
OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO
DYNAMIC_CHARGE_STATUS=FAIL
NOMINAL_CHARGE_STATUS=FAIL
SETTLING_STATUS=PASS
SHUTOFF_STATUS=PASS
CONVERGENCE_STATUS=PASS
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
PHYSICAL_CDC_AND_SKEW=NOT_VERIFIED
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
