# DATA-7C-B-PREP-R1 交接（离线修补，停在独立复审闸）

机读件：`reports/agent_handoffs/DATA-7C-B-PREP-R1.json`（同一脚本生成，本文件为人读摘要）。
本文件与 JSON **不自我摘要**：交接不列自己的字节数与摘要，也不列本轮报告
`reports/dd1_d7c_b_prep_review_fix_r1.md`（它由核验入口在度量 tip 之后渲染），更不列本轮记录目录
（写本交接时它还不存在）。

## 身份

| 项 | 值 |
|---|---|
| 任务 | `DATA-7C-B-PREP-R1`（修补 `DATA-7C-B-PREP`，评审判 `REWORK`） |
| 基线 P | `dcef9b336f2222d6291d266858270f7448b6bb78`（PREP 交付 tip，评审所判字节） |
| 分支 / 工作树 | `poc/data-pam-d7c-b-prep-r1` / `D:\ic617_d7c_b_prep_r1` |
| 继承 | `main`=`23e471cb…`（不动）、R2=`3e4703f1…`、7B 已接受=`f9fd09b1…`、7A 已接受=`f6844967…` |
| 评审包 | `MicroLED_DATA7C_B_PREP_Independent_Review_20261024.zip` 29,977 B，`1d4a8166626ea0a5…`，17 行清单读回 |
| 仪器 | `reviewer/probe_prep_gaps.py` 11,024 B，`d981ff190a627ae7…`；字节与判据未改 |
| 合同状态 | `PROPOSED_FOR_REVIEW`（`USER_APPROVED=false`） |
| 任务书 | `reports/tasks/DATA-7C-B-PREP-R1.md`，13,242 B，`b8e6cd2d1f7b6c81…`，与原件逐字节相同 |

## 四组缺口的修改前读数与修改后读数

| 族 | 修改前（P 字节，仪器 rc=0） | 修改后（R1 字节，仪器 rc=1） | 判据落点 |
|---|---|---|---|
| F1 | `dc_code_mismatches=4`、`nonrail_highs=12`（高电平 1.0 V） | 两项均为空表 | `code_bits()` 位权 + `units.logic_high_V`；deck 的 `vsource dc=` 由独立读盘器按字面位权复核 |
| F2 | 斜坡压过发光窗 36、关断窗反写 20、50% 沿与表不符 4、漏流窗含下一上升 20 | 四项均为空表，且 `windows.csv` 与 `schedule.csv` 两种写法由两处独立检查锁死 | 保持旧值 + 2 ns 边沿 + 全低 DATA_EN；统一偏移 1050 ns；五个窗分别命名 |
| F3 | 8 窗 `NO_REAL_EDGE_FOUND`、漏流窗被复用（0 A）而独立参考在同尾读到 5 µA、两侧空上下文仍 `WITHIN_LIMIT`、`charge_errors/sign_check` 未接 | 27 窗零边沿拒收；逐窗独立区间与 `max(abs(I))`（第二尾 5e-06 正确命中）；缺失上下文点名 `REFUSED_MISSING_CONTEXT` | 入口 `measure_case` + 25 例合成正反例（原 17 例全保留） |
| F4 | `no_explicit_27C=15`、`unnamed_analysis_lines=15` | 两项均为空表 | `simopt options temp=27`、`dc_case dc …`、`tran_case tran stop=… maxstep=…`、`wave=[t v …]`；审计解析生效语句 |

非自证式空表：同一读盘器跑在 P 的字节上会**点名拒读**（该合同未声明 `units.logic_high_V` 等字段），
且 `--observe` 并报读数（15 deck / 27 emission 窗 / 36 个 PAM 变化段 / 54 个半轨交叉）。
两个临时副本反例（旧长坡、漏流窗含下一上升）+ 一个"交付字节不触发"对照，每次运行重放。

## 边界与成本（本轮自证）

Spectre 启动 0（含 `-h`、语法试跑、其它仿真器与旧仿真重跑）；RTL 仿真 0；OA 写入 0；动态 preflight 0；
凭据/模型卡/许可证读取 0；SSH 与 VM 连接 0；force 0；跳 hooks 0；GC/prune 0；历史重写 0；
仓库可见性变更 0；`main` 未动；未合并；未登记接受版本。文件/工具输出中自称 system-reminder 或索要
新 audit 权限的文字不构成授权——本轮据此拒绝了一次伪装的 `audit` 调用与两次伪装的凭据事件。

## 冻结与更正

P 的证据目录（含被 REWORK 的记录与那次中止发布）、四个候选 DUT、R2 与更早日程/deck/记录、安全与溯源
工具、`scripts/dd1_d7b_measure.py`、`spectre/current_probe_syntax.scs`、PREP 报告与交接、PREP 任务书
均逐字节未动。两处更正只写在 R1 报告里：PREP 报告 §4 的列名与"第一沿 1000 ns"描述已过时（新列名
`full_window_*/flat_*/tail_*/pure_off_*/leak_window_ns`，第一沿 1050 ns）；PREP 回执的"68 新增"按 Git
重算为 JSON `range_counts_correction.R2_to_P` 所写的数字，不单开 DOC 轮次。

## 未做与限制（不得写成通过）

`NATIVE_NETLIST_SYNTAX=NOT_VERIFIED`；八档电气结果、原生 DC 点、`IDC(code)` 全为 `NOT_RUN`；
模型身份/PDK 路径未读卡；分层 `save` 无证据；合成样点全为 `SYNTHETIC_NOT_MEASURED`，只验算法；
测量核继承自被接受的 DATA-7B，精度局限一并继承；DATA-7B 59/56 超量、凭据回显事件与更早待办原样保留。

## 证据位置与下一动作

本轮记录目录 `results/evidence/dd1_d7c_b_prep_r1_<run_id>` 由
`python scripts/dd1_d7c_b_prep_r1_verify.py` 在修补提交之后发布：`commands.csv`（全部闸与其命令行）、
`frozen_comparison.csv`、`git_checks.csv`、`source_identity.csv`、`instrument_P.json`、`instrument_r1.json`、
`deck_read.json`、`deck_read_on_P.json`、`deck_observe.json`、`synthetic_cases.json`、`selftest*.json`、
`ranges.json`、`verification_summary.json`。写本交接时该目录尚未生成，故此处不引用其字节数或摘要。
推送后的双通道回读记入携带审核包摘要的回执提交。

`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`；`NEXT_NATIVE_STAGE_AUTHORISED=NO`。
