# DATA-7C-B-TR-D02 返工报告

日期：2026-11-13。本轮只修 B1（必需列 + 完整 PWL 见证），B2–B5 保持关闭，仍停在独立复审闸。

## 1. 输入与身份

| 项目 | 固定值 |
|---|---|
| worktree | `D:/ic617_d7c_b_tr_d02` |
| 分支 | `poc/data-pam-d7c-b-tr-d02` |
| BASE | `71fb4ab049bc6aad1421f0b02b6ed27d7a8c07a2`（R4 tip，已发布） |
| run_id | `d20261113_234820_29fb0d` |
| 新证据目录 | `results/evidence/dd1_d7c_b_tr_d02_20261113_234820_29fb0d` |

复审输入：`MicroLED_TR_R4_Independent_Review_REWORK_20261112.zip`（48,809 B，`1807f655…`，36/36 清单吻合）。该轮结论：B2/B3/B4/B5 关闭，B1 三项漏检。

## 2. B1 之一：必需列不再可选

`_r2_required_columns` 按冻结合同 `required_signals.always_extracted` 的 12 个信号逐个强制，`Ip_branch_current` 按序列头 `native_current_column` 的别名匹配；`time` 要求 `s`、电流要求 `A`、其余要求 `V`。缺一列即具名拒收，并且**在缺列时直接停止后续取值核对**——R4 的 `if 'iref_in' in columns` / `len(bits)==3` 那种"缺席就跳过"的写法已删除。

| 反例 | D02 实际拒收理由 |
|---|---|
| 删除整个 `iref_in` 列 | `the frozen contract requires the iref_in column and the delivered preflight does not carry it` |
| 删除整个 `pam1` 列 | `the frozen contract requires the pam1 column and the delivered preflight does not carry it` |

## 3. B1 之二：按可执行源判，而不是按注释

`_r2_deck_sources` 只解析 deck 里真正的器件语句 `Vname (node 0) vsource ...` / `Iname (...) isource dc=...`，先剥掉 `//` 注释。PWL 的 `wave=[t v ...]` 按工程记数法还原到 ns/V；`dc=` 同样还原。同一节点上"理想电流源 + 0 V 电压源"的传感接法被识别为一对而非冲突。

判定内容：

- 供电与钳位：deck 的 `dc` 值、冻结合同的环境值、交付常数列三者互相一致。
- 使能：交付样本的 0.9 V 交越必须与可执行 PWL **数量相同、逐个时刻差 ≤ 0.5 ns**；单平台与多平台同一标准。
- 位序：每个平台的**中点**取最近样本，与 `VPAM0/1/2` 的 PWL 在该时刻的电平逐位比对（容差 1e-6 V）。

| 反例 | D02 实际拒收理由 |
|---|---|
| TR-LONG 的 8 对使能沿删到仅 1 对 | `the delivered stimulus shows 1 rising 0.9 V crossings against the 8 the executable deck PWL contains`（下降沿同） |

## 4. HYB「8 对 4/3」按复审结论处理

R4 把这条差异记为待解释备注。复审已定位：`// platform` 注释沿用了 8 平台模板，而实际执行的 `Vdata_en` PWL 只有 4 和 3 个脉冲，交付样本与可执行 PWL 相符。D02 因此不再读注释、不再产生这条备注：HYB-120 期望 4 个平台、HYB-200 期望 3 个，干净样本逐项吻合。**未改任何冻结 deck、旧序列或旧账，也未为此重跑仿真。**

## 5. 验证

| 项目 | 结果 |
|---|---|
| 干净 `--verify` | rc=0，`21/21 problems=0 excluded=4`，**无范围备注**（R4 的 6 条 NOTE 已消失，因为多平台现在全量判定） |
| 禁止全部 subprocess 的 `--verify` | rc=0 |
| 干净复算 | rc=0，`RECOMPUTE_R1 gate 838/838` |
| 反例 | **17/17 具名拒收**：R4 的 14 项全部仍在，新增 `B1_iref_missing`、`B1_pam1_missing`、`B1_single_platform` |
| B4 方法级三组 | 标签不释放、两次启动不释放、`NOT_STARTED` 释放一次 |
| 冻结面 | 3336 项中 **3334 项逐 blob+mode 未变**；1 个获准脚本改动（native.py）；1 项为探针改名；32 个新增文件 |

探针由 `dd1_d7c_b_tr_r4_probe.py` 改名为 `dd1_d7c_b_tr_d02_probe.py`，并自定位表目录（`D02 → R4 → R3`）与 VCD（`D02 → R4 → R3 → R2`），因此在 Git 检出与无 Git 解包目录里都能直接运行。

## 6. 保留与未做

- 动态 33/37、名义 23/37 电气 FAIL 与冻结 ±0.5 LSB 阈值不变；全部窗口数值未改。
- `RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、`BUDGET_ACCOUNTING_STATUS=PARTIAL`、保守占额 5/4 保持。
- 检查器仍是 838 条：本轮只加判定，没有新增计数记录，也不靠计数宣称关闭。
- 260 条历史模块自测仍未运行：`selftest()` 会进入受护栏保护的 `launch()`。
- 零 Spectre、零 RTL 编译/仿真、零 OA、零 guest、零 PDK/license/凭据读取；未合并、未登记接受。

```text
D02_VERDICT=AWAITING_INDEPENDENT_REVIEW
B1_REQUIRED_COLUMNS=FIXED
B1_COMPLETE_PWL_WITNESS=FIXED
B2_B3_B4_B5=UNCHANGED_CLOSED
HYB_PLATFORM_NOTE=RESOLVED_BY_EXECUTABLE_PWL
NEW_SPECTRE_LAUNCHES=0
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
```
