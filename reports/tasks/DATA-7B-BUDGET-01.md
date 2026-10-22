# DATA-7B-BUDGET-01：Spectre 进程额度的真实账（2026-10-22 登记）

任务书：`reports/tasks/DATA-7B.md`（DATA-7B 原任务书逐字节副本）与
`reports/tasks/DATA-7B-R1.md`（DATA-7B-R1 任务书逐字节副本，SHA-256
`d35233770fb7bb9a52050937024a16c4106723094493b2c1381cae333b068bf3`，14,185 B）。

本文件只登记已经发生的事实，**不补写任何新授权，不把 59 次改写成 56 次，也不把违规改成 NOT_RUN**。
它是 R1 证据目录里 `launch_account.csv` 与 `launches_reconcile.csv` 的文字对照，两边数字必须一致。

## 1 三个不同的数

| 量 | 值 | 来源（可核字节） |
|---|---:|---|
| DATA-7B 原任务书授权 | 52 | `reports/tasks/DATA-7B.md` 的额度条目（`LAUNCH_BUDGET_TASKBOOK = 52`） |
| 用户在轮内追加 | +4 → 上限 **56** | 2026-10-21 用户在执行会话中的选择"追加授权 4 次，跑满 23 例"；这是唯一一次追加，没有第三次的记录 |
| guest 侧真实启动 | **59** | `results/evidence/dd1_d7b_r11_main/launches_reconcile.csv` 的逐目录计数（TOTAL 行 `preflight_logs=30, total_logs=59, dut_logs=29`），每条都能在 guest 任务根目录的日志数对上 |
| 超出上限 | **3** | 59 − 56 |

## 2 59 次的构成，以及为什么旧交付的账本只有 58 行

`launches_reconcile.csv`（T 交付时的原表，逐目录）：

| 任务根目录 | preflight | 总日志 | DUT | 计入上限 |
|---|---:|---:|---:|---:|
| r2_probe | 1 | 1 | 0 | 1 |
| r3_probe | 1 | 2 | 1 | 2 |
| r4_probe | 1 | 2 | 1 | 2 |
| r5_cal | 1 | 2 | 1 | 2 |
| r8_smoke | 1 | 2 | 1 | 2 |
| r9_main | 1 | 2 | 1 | 2 |
| r10_main | 1 | 2 | 1 | 2 |
| r11_main | 21 | 42 | 21 | 42 |
| r11_reuse | 2 | 4 | 2 | 4 |
| **TOTAL** | **30** | **59** | **29** | **59** |

`r1_probe` 在 T 的表里以 0 次出现（那个目录没起任何进程），所以 R1 重建的账户表按"有确认行才成行"
的规则不再为它生成一行；它仍然是 0 次，不改变任何总数。

T 交付包里的 `process_ledger.csv` 只有 **58 行**，构成是
`preflight DONE 27 / dut DONE 27 / static_negative DONE 4`，且 `launches_used_after` 的最大值只有 **42**
（那是 `r11_main` 单个 run 的局部计数器，不是整轮总数）。差额来自一个已登记的 R1-B 缺陷：
账本写在**共享**路径上，崩溃的轮会覆盖幸存的行。因此整轮真实总数**只能**由
`launches_reconcile.csv` 与 guest 文件计数得出，绝不能由 `process_ledger.csv` 的行数得出。
30 + 29 = 59 与 27 + 27 + 4 = 58 是两个不同问题的读数，旧报告把它们混为一谈过。

R1 起，账户表 `launch_account.csv` 按任务持久追加（每次启动前一行 REQUESTED，确认后 CONFIRMED，
失去联系转 UNCERTAIN 且继续占额度），并且**拒绝**把任何已确认行删掉或改小。R1 证据包里的
`launch_account.csv` 有 59 条 CONFIRMED（30 preflight + 29 dut），与对账表逐角色相加一致；
本轮新增的 0 次启动以 `REFUSED_NO_LAUNCH` 行记录，不占额度也不被隐藏。

## 3 本轮（DATA-7B-R1）的成本

| 项 | 值 |
|---|---|
| 新增 Spectre 进程 | **0**（离线重测，未建 SSH、未建 guest 任务根、`--dry` 与 mock 全在 ignored 目录） |
| 新增 OA 写入 | **0** |
| 新增四态 RTL 仿真 | **17**（上限 17；冻结 `rtl/dd1_d7a_gray_ctrl.sv` + 冻结 `tests/dd1_d7b/tb_dd1_d7b_pwm.sv`，本机 Icarus 14.0 devel，一次编译 17 次 `vvp`，逐案例一行记在 `rtl_reverify.csv`） |
| 历史违规状态 | `HISTORICAL_BUDGET_STATUS = VIOLATED_NOT_RETROACTIVELY_AUTHORISED` |

`BUDGET_RESPECTED` 在 R1 证据包上仍然是 **FAIL**，原因是 59 > 56 这一历史事实；
发布闸允许这一项作为唯一已披露失败通过，但检查器不把它改成 PASS，也不放宽判据。
要清掉这一项只有一条路：用户对此前 3 次超支作出处置。本任务不代用户作出处置。
