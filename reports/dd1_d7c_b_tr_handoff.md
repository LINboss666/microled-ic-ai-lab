# DATA-7C-B-TR handoff

Round `r20261026_132228_3fc148` on branch `poc/data-pam-d7c-b-tr`, HEAD `86fc70862ad27e37a9d3838fe7b892f3e281828e`, base `61621f6e3d887082ecd6a7ecc1c771f8e509a24a`. Contract state `USER_APPROVED_FOR_EXECUTION_DATA_7C_B_TR`. Generated 2026-10-27T03:51:48Z.

## What was delivered

- 9 prepared and joint cases, both roles: 18/19 Spectre account rows confirmed, 2 stray processes charged anyway, enforced ceiling 22 of the approved 24, 3 unused
- 4 vvp processes charged of the approved 4; both joint traces come from the accepted controller with no RTL change
- 37 window rows: 34 emission and 3 black, each bound to a charged launch and the delivered deck digest
- three convergence pairs, 13 window comparisons, 0 context refusals
- 36/36 record gates pass; 693598 newly tracked bytes over 60 files

## The seven statuses

| status | verdict | measured | expected | note |
|---|---|---|---|---|
| EXECUTION_COMPLETENESS | PASS | 18 | 18 | 18 of 18 planned launches confirmed, 19 account rows charged, 2 stray processes charged from the recorded budget adjustment, effective ceiling 22 of the approved 24, 4 vvp processes charged of the approved 4; rows kept charged and not refunded: T001 |
| EVIDENCE_INTEGRITY | PASS | 37 | 37 | 37 rows bound to a confirmed launch and the delivered deck; 9 cases carry the two-terminal check |
| DYNAMIC_CHARGE_STATUS | FAIL | 33 | 37 | abs(error_dynamic_LSB) <= 0.5, the frozen criterion of this task |
| NOMINAL_CHARGE_STATUS | FAIL | 23 | 37 | abs(error_nominal_LSB) <= 0.5 reported independently; a dynamic pass is never presented as an uncalibrated grey-scale pass |
| SETTLING_STATUS | PASS | 34 | 34 | against the DC target with a +/-5 % band, at least 10 ns, deadline flat_stop |
| SHUTOFF_STATUS | PASS | 34 | 34 | max(abs(I_sink)) <= 1.5e-07 A over the last 100 ns of the pure-off window only |
| CONVERGENCE_STATUS | PASS | 13 | 0 | abs(dQ)/QLSB <= 0.01 on the three declared pairs |

## Negative findings, published as findings

- dynamic charge over the frozen limit: TR-OFFCODE W3, RS-SWITCH W3, HYB-120 W2, HYB-120 W3
- nominal charge over the same limit: TR-LONG W2, TR-LONG W3, TR-LONG W4, TR-LONG W5, TR-LONG W6, TR-LONG W7, RS-FULL W2, RS-FULL W3, RS-FULL W4, RS-FULL W5, RS-FULL W6, RS-FULL W7, HYB-120 W2, HYB-200 W2
- the circuit was not modified to turn either into a PASS

## What this round does not claim

- no grey-scale LUT, no full MOS grey-scale controller, no array, no layout, no DRC, LVS or PEX, no optical measurement and no OA access
- no optical effective bits, no physical CDC or skew conclusion, no SOA sign-off
- NONE: this round does not register an accepted version and does not give itself a GO
- `NEXT_STAGE_AUTHORISED=NO`, `STOP_REASON=AWAITING_INDEPENDENT_REVIEW`
