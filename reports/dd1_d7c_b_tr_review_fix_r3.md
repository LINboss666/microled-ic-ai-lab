# DATA-7C-B-TR-R3 返工报告

日期：2026-11-12。本轮只修 R2 复审剩余的语义与记账缺口，保留已通过的部分，仍停在独立复审闸。

## 1. 输入与身份

| 项目 | 固定值 |
|---|---|
| worktree | `D:/ic617_d7c_b_tr_r3` |
| 分支 | `poc/data-pam-d7c-b-tr-r3` |
| BASE | `fc7ee7a59ea3bc70835f511a1f47650887ca9329`（R2 tip） |
| run_id | `r20261112_175259_3c2950` |
| 新证据目录 | `results/evidence/dd1_d7c_b_tr_r3_20261112_175259_3c2950` |

复审输入：`MicroLED_TR_R2_Independent_Review_REWORK_20261112.zip`（49,259 B，`6bb583d3…`，16/16 清单吻合）与 `MicroLED_TR_R2_Original_Package_Review_Addendum_20261112.zip`（43,407 B，`d46396d4…`，13/13 清单吻合）。补审已确认原包大小/SHA/CRC/381 成员/清单闭合与两个入口全部通过，**B5 关闭，原包缺件项关闭**。

## 2. B1：预检实际列语义

`_r2_preflight_semantics` 不再只读头部注释与五个常数。新增 `_r2_parse_sequence` 完整解析交付的列 schema：`column <name> unit <unit> encoding <CONSTANT|RUNS> count <n> [runs <r>]`，把 RUNS 展开回样本，并在展开时计数。

据此判据：列名唯一、`count` 必须等于 `samples`、RUNS 的重复数之和必须等于 `count`、常数列只能有一个值、**每个值必须有限**（`math.isfinite`，因此 `nan` 不再因 `abs(nan-x)>eps` 恒假而溜过）、`time` 单位 `s`、`Ip_branch:i` 单位 `A`、`data_en` 单位 `V`、时间轴严格递增、五个供电/夹持常数与冻结合同一致且有限、`data_en` 全程落在冻结逻辑轨内、头部样本数与清单样本数一致。

| 反例（原包内可复现） | R3 实际拒收理由 |
|---|---|
| 实际电流列 `unit A`→`unit V` | `column Ip_branch:i is declared in V, the frozen reader uses A` |
| 实际 `vdd18` 值→`nan` | `column vdd18 carries 780 non-finite value(s), the first nan` |
| `samples 780`→`779` | `column time declares 780 values against 779 samples` |
| 时间轴前两点互换 | `the time axis is not strictly increasing at sample 1 (3.53e-09 then 1.53e-09)` |

## 3. B2：执行/预算/settling 的事实派生

- `EXECUTION_COMPLETENESS`：从冻结合同的 `dut_launches + preflight_launches` 得到计划 18 次，逐个 `(case, role)` 只认账本里 `state=CONFIRMED`、`rc=0`、且自带 deck/raw/log 身份的所在行；`UNCERTAIN` 保留占额但不算完成。计划外被确认的启动同样拒收。
- `BUDGET_ACCOUNTING_STATUS`：从账本行数（19）加调整项（每个调整项的 `processes` 必须等于其 `launches` 条数）派生实际占额，再与合同总额 24、预算文件核准上限 22 比较；发布值必须等于派生值。
- `settling_*_left_limit_A`：从交付的 dut 序列在 `flat_stop` 处做二分定位与线性插值，与发布值比较（相对 1e-6）。真实值可在本机复现：TR-120 W0 在 1280 ns 处插得 `1.922842978252656e-06`，发布 `1.92284297825e-06`，相对差 1.4e-12。

| 反例 | R3 实际拒收理由 |
|---|---|
| TR-120 preflight 账行 `CONFIRMED`→`UNCERTAIN` | `1 of 18 planned launches are not confirmed in the ledger: [('TR-120', 'preflight')]` |
| 调整项加一次启动，实际占额 22，发布仍 21 | `status BUDGET_ACCOUNTING_STATUS publishes PARTIAL/21/24 but the actual inputs give PARTIAL/22/24` |
| TR-120 `settling_dc_left_limit_A`→`1000` | `TR-120 W0 publishes settling_dc_left_limit_A=1000.0 against 1.922842978252656e-06 interpolated at the deadline 1280 ns` |

## 4. B3：收敛上下文逐对比对

新增 `r2_context_differences()`：对每个冻结键，取配对的 refined/coarse 两行窗口，逐字段比较 `kind`、`code`、`window_start_ns`、`window_stop_ns`、`rise50_ns`、`fall50_ns`、`t50_ns`、`qlsb_C`、`tick_ns`、`qtarget_dc_C`（数值按相对 1e-9，缺字段算差异，`none == none` 不算匹配）。差异非空即拒收；同时要求 `tick_ns` 等于合同该对的 `tick_ns`，并要求发布的 `context_match` 必须等于派生结论 `YES`。

| 反例 | R3 实际拒收理由 |
|---|---|
| 首条收敛行 `context_match` YES→NO | `convergence key ('RS-FULL/TR-LONG', …, 'W0', '000') publishes context_match='NO' while the delivered windows agree on every measured field except maxstep` |

## 5. B4：去重必须读得到转录

- `Account.duplicate_bookings()`：不再接受"标签等于见证行 log 摘要"这种自陈。必须给出 `transcript` 相对路径，文件存在、其自身 SHA-256 同时等于声明的 link 与见证行的 `log_sha256`、正文点名两个行号与 case；否则一分不扣。
- `record.derive_duplicates()`：行内自报标签没有任何可读材料，直接返回空，并说明唯一可验证路径在 `Account` 侧。
- `rtl_checks()` 已改为委派 `r2_rtl_checks()`，删掉以 executable 摘要断言"四次/五行"的并行旧证明路径。

| 反例 | R3 实际结果 |
|---|---|
| 只填标签、无转录文件 | `duplicates=[]`、`processes=2`（占额不释放）；`record.derive_duplicates` 返回空 |
| 两行 refusal 填相同标签 | 同上，不再互相证明 |
| 提供真实转录且摘要吻合 | `duplicates=['R001']`、`processes=1`（能力保留且可核） |
| 真实五行账本 | `RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`，`proven_duplicates=[]`，保守占额 5/4，原账未改 |

## 6. 验证

| 项目 | 结果 |
|---|---|
| 干净 `--verify` | rc=0，`21/21 problems=0 excluded=4` |
| 禁止全部 subprocess 的 `--verify` | rc=0，同上 |
| 干净复算 | rc=0，`RECOMPUTE_R1 gate 838/838` |
| 反例 | **9/9 具名拒收**（B1 四项、B2 三项、B3 一项、B4 标签一项） |
| 冻结面 | 3278 项中 **3274 项逐 blob+mode 未变**，仅 4 个获准脚本改动，0 缺失，26 个新增文件（证据与探针） |

探针在两种树里都能跑：在 Git 检出里，B4 的账务 mock 会实际导入 `run`/`record` 并完成"只填标签不释放 / 提供真实转录释放一次"两组断言；在无 Git 的解包目录里，这两个模块按设计要读对象库，无法导入，探针把该段标为 `NOT_APPLICABLE` 并写出原因，而不是崩溃或静默跳过，其余 9 项反例与 3 项正控照常执行。

`841/841 → 838/838` 是检查器自身计数变化，不是新证据：旧 `rtl_checks()` 的五条并列断言被删除，改由 `r2_rtl_checks()` 一条统一记录，净减 4。它既不表示缺陷已关闭，也不表示四次进程已证成。

## 7. 保留与未做

- 真实电气结论未变：动态 33/37、名义 23/37 仍 FAIL，冻结 ±0.5 LSB 与全部窗口数值未改。
- 发布状态里只有三项字段语义变化：`CONVERGENCE_STATUS` 13/0→13/13、`NATIVE_SEQUENCE_REINTEGRATION` 835/835→37/37、`BUDGET_ACCOUNTING_STATUS` PASS→PARTIAL（21/24）；电气判定行逐项不变。
- 零 Spectre、零 RTL 编译/仿真、零 OA、零 guest、零 PDK/license/凭据读取；未改旧证据、旧账、旧 ZIP；未合并、未登记接受。
- 260 条历史模块自测仍未运行：`selftest()` 会走到受护栏保护的 `launch()`，本轮不冒真实启动的风险。

```text
R3_VERDICT=AWAITING_INDEPENDENT_REVIEW
B1_PREFLIGHT_COLUMN_SEMANTICS=FIXED
B2_FACT_DERIVATION=FIXED
B3_CONVERGENCE_CONTEXT=FIXED
B4_UNVERIFIED_LABEL_DEDUP=FIXED
B5=FIXED_AND_CLOSED_BY_REVIEW
ORIGINAL_R2_PACKAGE=VERIFIED_BY_REVIEW
NEW_SPECTRE_LAUNCHES=0
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
```
