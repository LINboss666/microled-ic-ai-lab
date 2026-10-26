# DATA-7C-B-TR contract (rendered)

Contract state `USER_APPROVED_FOR_EXECUTION_DATA_7C_B_TR`. Base `61621f6e3d887082ecd6a7ecc1c771f8e509a24a`, branch `poc/data-pam-d7c-b-tr`, main kept at `23e471cb936b421ee97e1250c3be06edf96f9937`.

## Authorisation

```text
APPROVAL_DATE=2026-10-26
APPROVAL_RESPONSE=YES
APPROVAL_TIMEZONE=Asia/Shanghai
APPROVED_TASK_BOOK=reports/tasks/DATA-7C-B-TR.md
EXISTING_TRACKED_PATHS_MAY_BE_MODIFIED=False
GUEST_WRITE_ROOT=/root/microled_ai_project/cadence_work/dd1_d7c_b_tr/<run_id>/
HISTORICAL_BUDGETS_MAY_BE_BORROWED=False
IVERILOG_COMPILATIONS_COUNT_AS_RTL_SIMULATIONS=False
MERGE_AUTHORISED=False
NEXT_STAGE_AUTHORISED=False
OA_ACCESS_AUTHORISED=False
RTL_FAILURE_OR_DEBUG_MARGIN=2
RTL_PLANNED_MAIN_RUNS=2
RTL_SIMULATION_TOTAL_LIMIT=4
SPECTRE_FAILURE_OR_DEBUG_MARGIN=6
SPECTRE_PLANNED_DUT_RUNS=9
SPECTRE_PLANNED_PREFLIGHTS=9
SPECTRE_TOTAL_LIMIT=24
STATUS=USER_APPROVED
```

## Nine cases

| case | source | tick ns | maxstep ns | partner | QLSB C | stop ns | launches |
|---|---|---:|---:|---|---:|---:|---:|
| TR-LONG | frozen_PREP | 120 | 2 | - | 2.25e-13 | 13050.0 | 1+1 |
| TR-120 | frozen_PREP | 120 | 2 | - | 2.25e-13 | 1530.0 | 1+1 |
| TR-200 | frozen_PREP | 200 | 2 | - | 3.75e-13 | 1610.0 | 1+1 |
| TR-OFFCODE | frozen_PREP | 120 | 2 | - | 2.25e-13 | 3750.0 | 1+1 |
| RS-FULL | frozen_PREP | 120 | 0.1 | TR-LONG | 2.25e-13 | 13050.0 | 1+1 |
| RS-LOW | frozen_PREP | 120 | 0.1 | TR-120 | 2.25e-13 | 1530.0 | 1+1 |
| RS-SWITCH | frozen_PREP | 120 | 0.1 | TR-OFFCODE | 2.25e-13 | 3750.0 | 1+1 |
| HYB-120 | accepted_RTL_new_VCD | 120 | 0.1 | - | 2.25e-13 | FROM_VCD | 1+1 |
| HYB-200 | accepted_RTL_new_VCD | 200 | 0.1 | - | 3.75e-13 | FROM_VCD | 1+1 |

## Charge

- `QLSB_nominal = 1.875e-06 A x Ttick`
- `Inom(k) x T50`
- `IDC(k) x T50`
- `(Qmeas - Qtarget_dc) / QLSB_nominal`, frozen limit `0.5`
- `(Qmeas - Qtarget_nominal) / QLSB_nominal`, independent limit `0.5`
- forbidden denominators: the length of the window under test; the measured Q of that window; a transient average current; the code current of that window multiplied by its length; I111 / 8 substituted for the nominal denominator

## DC reference at 1.20 V

| code | IDC A | Inom A |
|---|---:|---:|
| 000 | 1.922839108e-06 | 1.875e-06 |
| 001 | 3.845677157e-06 | 3.75e-06 |
| 010 | 5.768515211e-06 | 5.625e-06 |
| 011 | 7.691353271e-06 | 7.5e-06 |
| 100 | 9.614191336e-06 | 9.375e-06 |
| 101 | 1.153702941e-05 | 1.125e-05 |
| 110 | 1.345986748e-05 | 1.3125e-05 |
| 111 | 1.538270557e-05 | 1.5e-05 |

the accepted DC round measures I111 at 1.20 V as 1.538270557e-05 A, +2.551370 % above the 1.5e-05 A nominal, so a long or full-bright window may exceed 0.5 LSB on the nominal error and that is a reported result

## Carried followups

- `F-TR-1` (DC-R1 limited GO section 5(1)): vss is a required signal alongside the supplies; this round carries it in every new extraction and observation list
- `F-TR-2` (DC-R1 limited GO section 5(1)): the ideal iprobe two-terminal check uses 1e-06 V plus 1e-09 times the magnitude, is proven readable in this machine export precision, and is not a device drop spec

## Hybrid frames

| frame | cfg_hyb_time | cfg_hyb_pam | expected intervals |
|---|---:|---:|---:|
| B0 | 0 | 000 | 0 |
| L1 | 1 | 000 | 1 |
| M2 | 2 | 011 | 2 |
| F63 | 63 | 111 | 64 |
| A | 63 | 111 | planned 64, measured by the actual fault edge |

cfg_hyb_time == 63 maps to FULL_HYB = 64 intervals in the accepted RTL, so M = 64 and not 63

## Six stripped masters

- `spectre/dd1_d7c_b_dc/masters/dd1_d6_inv18.scs` at base `d535ad0112c31952d0c51e314cc57054b631b18c7457ba8088d970945ca6de77`
- `spectre/dd1_d7c_b_dc/masters/dd1_d6_bias_core.scs` at base `379536efb1dd9b2626e93ec384d572c734d5c1b398881c6de6ce4405e230c293`
- `spectre/dd1_d7c_b_dc/masters/dd1_d7c_a_gates.scs` at base `55c08f25eaee6184c8be263e8762559f51ff1c66be37c0a0dfb1c2b0e8f1e5de`
- `spectre/dd1_d7c_b_dc/masters/dd1_d7c_a_pam_dec.scs` at base `f4d458d21d82e91c3f0e4012cc8fb568c090c1bb364fd486bf0b82a469163b5a`
- `spectre/dd1_d7c_b_dc/masters/dd1_d7c_a_sink_unit.scs` at base `289ae1dd8edf91c806c2c2dfecc15d9b3b8524ed987849d0094bab1124369a3f`
- `spectre/dd1_d7c_b_dc/masters/dd1_d7c_a_pam_top.scs` at base `8489616e4826fccdd7516d7b02764ae3850ad3e4476181b5ae0f5249ec5a08a5`

## Convergence

- RS-FULL (maxstep 0.1 ns) against TR-LONG (maxstep 2 ns), same 120 ns tick, abs(dQ)/QLSB <= 0.01
- RS-LOW (maxstep 0.1 ns) against TR-120 (maxstep 2 ns), same 120 ns tick, abs(dQ)/QLSB <= 0.01
- RS-SWITCH (maxstep 0.1 ns) against TR-OFFCODE (maxstep 2 ns), same 120 ns tick, abs(dQ)/QLSB <= 0.01
- not covered: TR-200 has no dedicated fine-step partner, so no claim is made that every case has an independent fine-step check
- not covered: HYB-120 and HYB-200 have no fine-step pair of their own

## Published separately

```text
EXECUTION_COMPLETENESS
EVIDENCE_INTEGRITY
DYNAMIC_CHARGE_STATUS
NOMINAL_CHARGE_STATUS
SETTLING_STATUS
SHUTOFF_STATUS
CONVERGENCE_STATUS
```
