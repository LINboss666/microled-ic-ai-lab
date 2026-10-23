# DATA-7C-B-PREP 交接（八档 PAM 原生验证准备，2026-10-23）

任务书逐字节副本 `reports/tasks/DATA-7C-B-PREP.md`（18,448 B，SHA-256
`40a3eb148e038c4fb6ea4d5a7d48de4b2e9b22e6a34a685c34f912f2a3c8b126`）。机读字段全在
`reports/agent_handoffs/DATA-7C-B-PREP.json`；本文件不写自身摘要，本轮 tip 从 Git ref 读。
详细叙述在 `reports/dd1_d7c_b_prep_report.md`，合同草案在 `reports/dd1_d7c_b_prep_contract.md`
（由 `tests/dd1_d7c_b_prep/contract.json` 渲染）。

## 1 身份

| 项 | 值 |
|---|---|
| 任务 / 基线 | `DATA-7C-B-PREP`，base = R2 `3e4703f1763223024f442c0826e95055782bca13` |
| 分支 / 工作树 | `poc/data-pam-d7c-b-prep`（本轮新建，独立 worktree）/ `D:\ic617_d7c_b_prep` |
| 范围 | 离线准备：电气合同草案、15 份 deck 文本与日程、合成测量正反例、启动额度草案 |
| 合同状态 | `PROPOSED_FOR_REVIEW`（不是 `USER_APPROVED`，未被审核冻结） |
| 完成级别 | `PREPARED_FOR_INDEPENDENT_REVIEW_NO_NATIVE_RUN` |
| 文件范围 | 相对 R2 **只新增**：修改 0、删除 0（记录 `frozen_comparison.csv` 的 enforced 行为 0 违例） |
| 本轮成本 | Spectre **0**（含 `-h`）、RTL 仿真 **0**、OA 写入 **0**、动态 preflight **0**、SSH/VM **0**、凭据与 PDK/模型卡 **未读** |
| 验证记录 | `results/evidence/dd1_d7c_b_prep_20261023_172056_48cc50/`（目录名在跑之前定下；`verification_summary.json` 的 `generated_utc` 才是真实生成时刻） |
| 停止状态 | `AWAITING_INDEPENDENT_REVIEW_OF_NATIVE_PREPARATION` |

## 2 交付分层（不用一句"准备好了"吞掉未测项）

| 层 | 状态 | 依据 |
|---|---|---|
| 电气合同（判据、单位、名义阶梯、额度、差异） | **完成（草案）** | `tests/dd1_d7c_b_prep/contract.json` + 自校验 `--check` PASS，报告由同一来源渲染且固定点成立 |
| 15 例日程与 PWL | **完成（文本）** | `schedule.csv` 15 行、`windows.csv` 62 行、`pwl.csv` 215 点，逐例时刻分列 |
| 15 份 deck | **完成（文本），语法未证** | `spectre/dd1_d7c_b_prep/*.scs`；`--to <scratch>` 重建并与交付字节逐字比较 |
| 测量算法 | **合成验证 17/17** | `scripts/dd1_d7c_b_prep_measure.py` 复用 DATA-7B 已接受内核；`SYNTHETIC_NOT_MEASURED` |
| 原生网表语法 / 层级 save / pwl 拼写 | **`NOT_VERIFIED`** | 本轮零仿真器调用，连 `-h` 都没跑 |
| 八档电流、PWM×PAM 电荷联合、灰阶控制器、LUT、光学有效位数、SOA | **`NOT_RUN` / `NOT_VERIFIED`** | 见合同 `not_run` 与本文件 §1 成本行 |
| 是否接受 R2 | **未接受**，本轮不给 | 任务书明令：可在 R2 复审未完成时做本轮准备，但不得自审宣布 R2 接受 |

## 3 电路与激励的三条硬边界

1. 一个输出 `data_out`、八条单位下拉支路、一个共享参考；`data_en=1` 导通 `pam_sel+1` 条，
   `data_en=0` 全关；码 `000` 是最低非零档（约 1.875 µA 估算），不是黑码。LED 的 N 侧接恒流下拉、
   Scan 的 PMOS 高侧接 LED 的 P 侧，未为统一行列称呼对调极性。
2. 名义电流身份 `ESTIMATED_MIRROR_RATIO_ONLY`：145 等计数由解析引用，不手抄成实测结论；
   `Mpass/Mbleed` 本轮不重新缩放；四份候选 DUT 与 R2 逐字节相同。
3. 探针端序与符号在任何运行之前定死：`Ip_branch (clamp_node data_out) iprobe`、`I_sink = Ip_branch`，
   原始电流与总电荷永不取 abs；尾流可正可负，`Q=Qpos+Qneg` 与 `max(abs(I))` 漏流判据分列。

## 4 与已交付 R2 的差异（保留建议值，等裁定）

`D1_clamp_sweep_step`、`D2_ton_unit_is_four_microseconds_in_the_deck`、`D3_short_pulse_note_versus_platform`、
`D4_tr_long_starts_conducting_at_t_zero`、`D5_integration_window_is_narrower_than_the_platform`
五条，逐条的"R2 另一头怎么说 / 冲突 / 本轮值 / 为什么不默改 / 状态"在合同 §5 表里。
本轮没有回去改任何 R2 报告来声称"历史本就一致"；统一 1 µs 初始关断与换码落在关窗中点，
是任务书 §5 允许的平移与要求，偏移量逐例记录在 `offset_applied_ns`。

## 5 启动额度：草案，不是授权

15 DUT + 15 preflight + 6 语法/调试/收敛余量 = 建议总额 36 次；本轮可用原生额度仍为 **0**。
每例的进程数逐行列在 `schedule.csv`。未来任何启动（含 `-h`、失败、被终止、崩溃、调试）计入总额，
`REQUESTED` 执行前占额、恢复记 `UNCERTAIN` 不退额，preflight 与 DUT 分列——记账纪律沿用 DATA-7B
已接受的 `Account`，本轮**不**新造生产级账本。启动前还需审核冻结：R2 接受版、本合同 SHA、
执行源码 SHA、电流/电荷判据、总额度与本机只读环境核验范围。缺任一项，本任务书不是令牌。
DATA-7B 历史 59/56 超支 3 次继续为 `VIOLATED_NOT_RETROACTIVELY_AUTHORISED`，不借用、不重置、不抵扣。

## 6 推送与回读

推送前双通道实测（Git protocol `2026-10-23T16:50:38Z`，GitHub API `2026-10-23T16:50:50Z ~ 16:50:58Z`）：
`poc/data-pam-d7c-a-r2=3e4703f1763223024f442c0826e95055782bca13`、
`poc/data-pam-d7c-a-r1=da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb`、
`poc/data-pam-d7c-a=89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79`、
`main=23e471cb936b421ee97e1250c3be06edf96f9937`、
`poc/data-pwm-d7b-r3=272d6de6d2f2fc8a82d5038d73d6b3e4c656f683`，两路逐字一致；
本轮分支 `poc/data-pam-d7c-b-prep` 在 Git protocol 无该行、在 API 为 404，这是"尚未推送"的正确答案。
推送与推送后的逐 ref 回读、以及审核包的名字与包外摘要，记在下面第 7 节和包外回执提交里；
本节不预告还没发生的数字。

## 7 还差什么才能启动

1. R2 的独立复审结论与用户的接受决定（本轮不登记）。
2. 审核对本合同的取舍裁定：电流归一取 `I111/8` 还是名义单位、0.5 LSB、0.25 Iunit_ref、0.15 µA、
   0.01×QLSB、±5% 与 10 ns，以及 §4 五条差异。
3. 原生执行源码 SHA、总额授权、本机只读环境核验（模型卡身份与 `tt`+`stat_noise` 组合、
   层级 `save` 与 `type=pwl` 先用探针确认，且不得为此改已交付候选）。
4. 缺任一项不得启动 DATA-7C-B 原生运行；执行者不给自己 GO，也不顺手开始联合电荷、LUT、TCON、
   阵列或版图。
