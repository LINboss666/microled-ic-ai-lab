# DATA-7C-B-DC 交接（八档直流实测，停在独立复审闸）

机读件：`reports/agent_handoffs/DATA-7C-B-DC.json`（同一脚本生成，本文件是人读摘要）。
本文件与 JSON **不自我摘要**：不列自己的字节数与摘要，不列由记录入口在度量 tip 之后重渲染的
`reports/dd1_d7c_b_dc_report.md`，也不列写本交接时尚不存在的记录表。

## 身份

| 项 | 值 |
|---|---|
| 任务 | `DATA-7C-B-DC`（`reports/tasks/DATA-7C-B-DC.md`，13,213 B `4cb0e22b…`，与原件逐字节相同） |
| 基线 | 已登记离线内容 `e51c5320a28bd5043e21d08a0be97e9d5612cd16`（分支 `poc/data-pam-d7c-b-prep-r2`） |
| 分支 / 工作树 | `poc/data-pam-d7c-b-dc` / `D:\ic617_d7c_b_dc`；登记提交 `390886a` |
| 授权 | 用户 2026-10-25 两项选择："批准 20 次，一跑到底"、"登记，限 PAM 候选与离线准备"（原文与写出时刻记入 `registration.json`，不编造点击时间） |
| 判据 | 冻结的 `tests/dd1_d7c_b_prep/contract.json` 规则 + 本轮合同 `tests/dd1_d7c_b_dc/contract.json` 的快照与漂移拒收 |
| 完成级别 | `NATIVE_PAM_DC_TT_MEASURED`（不再高） |

## 实测结果（原生，非合成）

8 码 × 19 个夹持点 = **152 条唯一数据**，`PAM_8LEVEL_DC_TT = PASS`：

| 码 | I(1.20 V) µA | 名义 µA | 偏差 µA |
|---|---:|---:|---:|
| 000 | 1.922839 | 1.875 | +0.000000912 |
| 001 | 3.845677 | 3.750 | +0.000000764 |
| 010 | 5.768515 | 5.625 | +0.000000622 |
| 011 | 7.691353 | 7.500 | +0.000000486 |
| 100 | 9.614191 | 9.375 | +0.000000355 |
| 101 | 11.537029 | 11.250 | +0.000000233 |
| 110 | 13.459867 | 13.125 | +0.000000106 |
| 111 | 15.382706 | 15.000 | 0 |

满量程 15.382706 µA 在 14.25–15.75 µA 带内；严格单调；共享 `Iunit_ref = I111/8 = 1.922838 µA`，
各档偏差最大 0.912 pA，即 0.0000005 个 Iunit_ref（限 0.25）。相对 15 µA 目标整体高 2.55%——
名义阶梯的身份是 `ESTIMATED_MIRROR_RATIO_ONLY`，这个偏差正是要测的量。
每码相对自身 1.20 V 电流 ±5% 的**连续已测**区间为 0.60–1.50 V 全部 19 点；0.60 V 以下没有测过，
所以区间止于数据止处，相邻未通过点记为 `NO_MEASURED_POINT_BELOW`，不外推。

预检仪表见证（8 例，逐例读，不看总 rc）：探针在 1.20 V 点均为 `+15.000000 µA`（=1.2 V/80 kΩ），
参考节点均为 `0.750000 V`（=15 µA×50 kΩ），符号为正。这是"理想仪表"结果，不是 PAM 结果。

## 账本与成本

`launch_account.csv` 16 行 = 8 预检 + 8 DUT，`D001…D016` 无跳号；上限 20，余 4，未用调试余量。
先持久 `REQUESTED` 再起进程，失败不退额。**D001 记为 `FAILED` 而 `rc=0`**：入口把运行器文本字段按整数
比较造成标签错误（进程本身成功，原生 19 点与仪表见证都在），行字节未改、原始 607 字节另存
`launch_account_as_first_written.csv`，理由与复现写在 `D001_label_attestation.json`。紧随其后的调用
在读表时崩溃，崩溃发生在 `reserve()` 之前——没有起进程、没有花额度。

本轮真实使用（不写成 0）：guest SSH 会话与既有免密密钥、桥按 `AGENTS.md` 加载 gitignore 的凭据文件；
guest 侧只读打开 PDK 库与模型卡做身份/尺寸核验。**凭据值、模型卡内容、PDK 绝对路径均未进入任何
提交物**；模型身份见证只记判定结果与库文件 sha256。Spectre 16 次、RTL 0、OA 0、瞬态 0、`spectre -h`
类语法探针 0。

## 可证的"没动别的东西"

`frozen_comparison.csv` 逐 blob+mode 与 `e51c532` 比对：四份候选 DUT、15 份交付 deck、三张时序表、
旧 PREP 合同 JSON、共享执行器与测量核、旧记录/报告/交接全部同一对象；本轮改动的既有文件只有
`scripts/dd1_d7c_b_prep_contract.py`（µA 换算）与其渲染 `reports/dd1_d7c_b_prep_contract.md`。
`spectre/dd1_d7c_b_dc/` 全是生成物：6 份 master 剥 63 行端口方向标注（剥离前后 `device_digest`、
`port_order_digest` 全等）、8 份 `.pre.scs` 各替换 1 行 `Xdut` 为两行仪表负载并删 5 行 DUT 层级 save。
DUT 跑的 deck 字节与交付 blob 相同（`deck_sha256` 逐行记在账本里）。

## 未做与限制

未做瞬态、PWM/PAM 联合电荷、灰阶 LUT、完整控制器、阵列、版图、SOA；`OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED`；
区间只说明"在这 19 个已测点上 ±5% 成立"，不等于 LED/电极 RC 或 SOA 已验证；
原生语法只对**实际跑过的**派生 DC deck 得到确认，不外推到全层级或瞬态；
旧轮次的 `--handoff-check` 在本轮必然 rc=1（它们绑的是各自那一轮的字节），这一点被写成一条具名门而不是被掩盖；
`QODER_NETLIST_DIR` 在 guest 的 gitignore 环境文件里缺失，本轮按运行载荷导出而**没有**改那个文件；
DATA-7B 59/56 超量、凭据回显事件与更早待办原样保留。

## 证据位置与下一动作

记录与测量：`results/evidence/dd1_d7c_b_dc_r20261026_015212_376554/`
（`commands.csv`、`frozen_comparison.csv`、`git_checks.csv`、`source_identity.csv`、
`launches_reconcile.csv`、`launch_account.csv`、`judgement.json`、`dc_matrix_dut.csv`、
`dc_matrix_preflight.csv`、`rows_*.csv`、`model_identity.json`、`D001_label_attestation.json`、
`figures/*.svg`、`verification_summary.json`）。原生 `.raw/.log` 与 ssh 传输日志按任务书留在本机，
不进远端提交，其 sha256 记在账本与提取行里。

入口：`python scripts/dd1_d7c_b_dc_run.py --selftest|--masters|--plan|--emit|--launch|--extract|--account`；
`python scripts/dd1_d7c_b_dc_matrix.py check|merge|judge|plot <evidence>`；
`python scripts/dd1_d7c_b_dc_record.py --check-only`（发布同一批闸而不写字节）。

`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`；`NEXT_NATIVE_STAGE_AUTHORISED=NO`。本轮不自给下一步 GO，
不进入瞬态，不合并，不推 main。
