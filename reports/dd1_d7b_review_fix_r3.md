# DATA-7B-R3 返修报告：账户非法状态拒收与交接更正（2026-10-23）

任务书 `reports/tasks/DATA-7B-R3.md`（逐字节副本，10,054 B，SHA-256
`2eb933bc0d8ddd91f34f50bee269e35a0576d0fee8caaf681729e7d1d3defaa1`，与审核包内同名条目一致）；
审核意见 `REVIEW_DATA7B_R2.md` 判定 **限定范围 REWORK**（前轮测量/来源/预算修补已通过复测）。

| 身份 | 值 |
|---|---|
| 本轮唯一基线（被审 R2 tip） | `b3fe93c17de014cb16031438ce28c7152dd0020f` |
| R2 功能载荷 P2 | `6abe1bf5b93dc4bb12ba179cea0ab26929f33a90` |
| R1 基线 H | `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92` |
| main（不得移动） | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 分支 / 工作树 | `poc/data-pwm-d7b-r3`（本轮新建）/ `D:\ic617_d7b_r3` |
| 基线只读检出 | `D:\ic617_d7b_r3_base`（detached @ `b3fe93c`，仅用于复现与比较，未提交任何改动） |
| 验证证据目录 | 见 §5 机器段（`results/evidence/dd1_d7b_r3_<run_id>/`） |
| 本轮成本 | 新增 Spectre **0**；新增 RTL 仿真 **0**；新增 OA 写入 **0**；无原生 preflight、无 SSH/VM |
| 电气 | 电路、判据、样本、判决**全部未动**；R2 的 287 文件包作为只读输入 |

本报告与包内文件都不写自身摘要；本轮 tip 与载荷 SHA 从 Git ref 读，不由本文件自称。
§5、§6 的表格由 `commands.csv` / `frozen_comparison.csv` 机械渲染（命令见该节末行）。

## 0 本轮操作记录

1. 动工前用两条独立通道回读固定基线：`git ls-remote`（经本机代理）与 `gh api
   .../git/ref/heads/<ref>`，两者对 `poc/data-pwm-d7b-r2 = b3fe93c…`、
   `main = 23e471c…`、`poc/data-pwm-d7b-r1 = e97f02e…`、`poc/data-pwm-d7b = adcdf27…`
   一致；`poc/data-pwm-d7b-r3` 查询返回 404（推送前确实不存在）。远端 ref 行数 21（新增分支后为 22）。
2. 新建分支与隔离工作树，未在 `main`、R2 或任何旧分支上修改；旧分支与 `main` 见 §8 的回读。
3. **先在基线原字节复现**，后改代码：
   `review/scratch/r3_diagnostic_base.json`（审核方诊断脚本对未修改检出的输出，rc=0）与
   `dd1_d7b_r3_guards.py --phase reproduce`（8/8 复现，工具取自 `b3fe93c` 的只读检出）。
   复现阶段的文件集合见 §5 机器段的 `commands.csv` 行 `r3_guards_reproduce_on_base`。
4. 冻结面：本轮**不删除、不覆盖、不改写**任何已发布目录或账户文件；
   `dd1_d7b_r11_main`、`dd1_d7b_r1_r20261022_123825_8e1294`、`dd1_d7b_r2_r20261022_160652_e880be`
   三个目录的 blob/mode 与基线全量一致（§6）。故障注入只在临时副本；真实账户未被写入。
5. 两次前置试跑留痕（都**不提交**，只在本地 ignored 之外的 `results/evidence/` 下原样保留）：
   `dd1_d7b_r3_r20261022_173926_f7d39c/` —— 第一轮验证把 `dd1_d7b_evidence_check.py <R2 包>` 的
   **预期 rc 写成 0**，而正确预期是 rc=1（唯一失败是已披露的历史预算违规），该门因此被判 FAIL；
   `dd1_d7b_r3_r20261022_174358_edd514/` —— 断言修正后重跑，13/13 PASS，但此时代码尚未提交，
   其 `frozen_comparison.csv` 里 `BASE..HEAD` 各行的 HEAD 仍等于 BASE，比较结果是**空洞的真**，
   不能当作 §6 的凭据。已把该缺陷改为断言口径修正，并在 P3 提交之后重跑一次验证，
   提交进仓库的目录是 `results/evidence/dd1_d7b_r3_r20261022_174818_502025/`（13/13 PASS，§5 与 §6 两表都取自它）。改的是断言与运行时机，
   不是判据、数据或电气结论。
6. 记录自身的一次缺陷与修正：已提交的 `..._174818_502025/commands.csv` 有一行单元格以空格结尾
   （260 字符截断的转录尾巴），而同一目录的 `git_checks.csv` 声称 `git diff --check` 干净——
   该断言在它被测量时成立，在该文件成为比较范围的一部分之后就不再成立。修法：`rows_write()`
   写出前逐个单元格 `rstrip()`，并把那一行的尾随空格就地清掉（只动空格，未动任何命令、rc、
   判决或正文），提交 `6fdae41` 后 `git diff --check b3fe93c..HEAD` 实测 0 行。
   由于该目录的 `tools_identity.csv` 记录的是运行时工具摘要，事后改工具会让它与自己列出的摘要
   不一致，因此用修好的工具**重跑一次完整验证**，权威记录是
   `results/evidence/dd1_d7b_r3_r20261022_180059_efda9d/`；旧目录原样保留、不删除不改写历史，
   §5 与 §6 两表取自新目录。
7. 本轮文档写入自身的一次破坏与恢复：用一段临时 Python 补丁改写 §10 的审核包段落时，字符串按字符
   展开，把 `reports/dd1_d7b_review_fix_r3.md` 的工作副本写成 13,838,728 B（每个原字符后重复粘贴整段
   新文字），SHA-256 `769e6cd9e6fa59f682223f39c13a812fb0aab566b0e61c20b47a0283d7f2d229`。
   该文件的**已提交版本未被触及**（`git cat-file -s HEAD:...` 在恢复前后都是 19,524 B），
   处置是把破坏副本原样挪进不入库的 `review/scratch/r3_corrupt_report_copy_13mb.md` 保留、
   再用 `git checkout -- <该文件>` 从提交恢复工作副本，然后改用逐段替换工具重打这一处编辑。
   未删除任何已发布产物、未改判据与数据；教训与 §0.6 同一类：**写入路径上的自指与量级都要事后实测**，
   这次是靠"文件大小与提交版本相差 700 倍"这一条判据立刻发现的。
8. 未做：PAM/LUT/阵列/版图/TCON、PDK/许可证/VM/凭据改动、GC、rewrite、force、跳 hooks、合并、
   改可见性、登记接受版。凭据回显事件仍未解除。

## 1 根因（F1）：非法账户状态被静默当成不占额

基线字节的 `Account` 只给列举出的状态计费，却**从不拒绝其余状态**：
装载/恢复（`__init__` → `recover()` → `_restamp()` → `flush()`）、`counts()`、`_restamp()`
三处都是"按状态分支计数"，未知或空状态自然落进所有分支之外，等于**免费**。
复核器 `check_launches()` 同样只按已知状态计数，没有对全部行做枚举校验，
所以只要伪造者把 environment 的汇总数一同改掉、重封 manifest，就没有任何检查会红。

在基线字节上的复现（合成额度 1、空 seed、无任何进程）：

| 注入 | 基线行为 |
|---|---|
| `state = UNRECOGNISED_STATE` | 重开成功，`occupied` 从 1 变 0，随后**第二次预留成功**并写出第二行 |
| `state = ''`（空） | 同上 |
| 内存里把合法行改成 `NOT_A_STATE` | `counts()` 仍返回计数、`reserve()` 仍写行 |
| 复制 R2 包，把 A001 改为未知状态、`launch_account.no_launch` 由 274 同步为 273、重算 manifest | 复核器仍只报 `BUDGET_RESPECTED`，**新增失败数为 0** |

边界按任务书写清：**当前发布账本 333 行全部是合法状态**，没有发现借此隐瞒新的实际启动，
原生入口仍关闭。这是损坏/非法输入的拒绝遗漏，不是又一次实际超支，也不推翻电气数据。

## 2 限定修法

1. `scripts/dd1_d7b_run.py`：新增 `ACCOUNT_STATES = (REQUESTED|UNCERTAIN|CONFIRMED|COMPLETED|
   REFUSED_NO_LAUNCH)` 与 `require_account_states()`；
   `Account.__init__` 在**读入之后、`recover()/_restamp()/flush()` 之前**校验全部行，
   空值/缺失/未知/大小写或空白变体一律 `RuntimeError` 拒收，**拒收时不写盘**，
   账户字节保持原样（探针按摘要核对），也不把未知状态"修成" REFUSED。
   `counts()` 与 `_restamp()` 同样先校验，因此内存里被改坏的行既不能被计数也不能被预留。
   `Ledger` 的 `DONE` 属另一张表的协议，未受影响（冻结旧文件不被误拒）。
2. `scripts/dd1_d7b_evidence_check.py`：新增独立点名检查 `ACCOUNT_STATES_VALID`，
   对 `launch_account.csv` **所有行**做同一枚举（缺文件时明确 FAIL），
   不依赖冻结 seed 行、不依赖汇总计数不符、不借用 `BUDGET_RESPECTED`。
   两份状态清单由 `--selftest` 第 10 项断言相等，不能各说各话。
3. 反例面扩为 16 类：新增 `illegal_account_state_with_synced_rollup`
   （改 A001 + 同步 environment 汇总 + 重封 manifest），必须只由 `ACCOUNT_STATES_VALID` 点名。
4. 没有新建状态机、事务框架或额外系统；改动只在这两个文件与新增的两个 R3 脚本内。

## 3 正反例（`scripts/dd1_d7b_r3_guards.py`，8 条）

| 探针 | 修前（基线工具） | 修后（本轮工具） |
|---|---|---|
| S1 未知状态读盘 | 重开成功且 `occupied=0`，随后第二次预留成功 | 拒收；文件摘要与注入前一致，行数仍为 2 |
| S2 空状态读盘 | 同上 | 拒收；字节不变 |
| S3 内存注入未知状态 | `counts()` 仍应答、`reserve()` 仍写行 | 两者都抛 `RuntimeError` |
| S4 五种合法状态计费语义 | 保持（55/56 边界、恢复仍占额、混合账 5 占额 2 免费） | 同样保持（未改语义） |
| S5 真实 R2 包 | 43 项、无状态枚举检查 | 44 项，`ACCOUNT_STATES_VALID` PASS，唯一失败仍 `BUDGET_RESPECTED` |
| S6 伪造副本（未知状态 + 同步汇总 + 重封） | 新增失败 0 | 新增失败恰为 `ACCOUNT_STATES_VALID` |
| S7 伪造副本（空状态） | 同上 | 同上 |
| S8 原生入口四种环境组合 | 全部拒绝 | 全部拒绝（未被本轮改动放松） |

审核方诊断脚本对本检出的复跑结果为 rc=1、`all_requirements_met=true`
（两个单元用例都 `reopen_accepted=false` 且 `second_reservation_accepted=false`，
伪造副本 `new_failures=["ACCOUNT_STATES_VALID"]`），输出随证据目录交付。

## 4 前轮行为保持不变

`dd1_d7b_r1_guards.py`（8 组）、`dd1_d7b_r2_guards.py --phase fixed --bundle <R2 包>`（14 探针）、
`dd1_d7b_evidence_check.py --selftest <R2 包>`（现 16 类反例）与
`dd1_d7b_measure.py --selftest`（24 项）、`dd1_d7b_trace.py --selftest`（13 项）
全部仍 PASS；`dd1_d7b_measure.py`、`dd1_d7b_trace.py`、`dd1_d7a_trace.py` 与全部
deck/PWL/case/golden/RTL/TB 在 `b3fe93c..HEAD` 内 blob 未变（§6），
因此既有测试身份未被悄悄替换。R2 报告的 26 项判决、43→44 项检查差集只有一项：新增的状态枚举。

## 5 门、命令与真实 rc

以下表格由 `results/evidence/<R3 目录>/commands.csv` 与 `frozen_comparison.csv` 渲染，
渲染命令：`python review/scratch/r3_render_tables.py`（只读 CSV，不重跑仿真）。

<!-- BEGIN R3 GATES -->
来源目录：`results/evidence/dd1_d7b_r3_r20261022_180059_efda9d`（本节与下一节同源；该目录由 `python scripts/dd1_d7b_r3_verify.py --out results/evidence/dd1_d7b_r3_r20261022_180059_efda9d --diagnostic <审核方诊断脚本>` 生成）

| 门（gate） | 命令 | rc | 判决 | 关键输出 |
|---|---|---|---|---|
| `measure_selftest` | `scripts/dd1_d7b_measure.py --selftest` | 0 | PASS | D7B_MEASURE_SELFTEST: PASS (24/24) |
| `run_selftest` | `scripts/dd1_d7b_run.py --selftest` | 0 | PASS | D7B_RUN_SELFTEST: PASS (14 checks) |
| `trace_selftest` | `scripts/dd1_d7b_trace.py --selftest` | 0 | PASS | D7B_TRACE_SELFTEST: PASS (13/13) |
| `r2_bundle_recheck` | `scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_r2_r20261022_160652…` | 1 | PASS | D7B_EVIDENCE_CHECK: FAIL (44 checks; 27 rows in scope; failures: BUDGET_RESPECTED) |
| `r2_evidence_selftest` | `scripts/dd1_d7b_evidence_check.py --selftest results/evidence/dd1_d7b_r2_r2026…` | 0 | PASS | D7B_EVIDENCE_SELFTEST: PASS (16 counterfeits; 0 problem(s)) |
| `r1_guards` | `scripts/dd1_d7b_r1_guards.py` | 0 | PASS | D7B_R1_GUARDS: PASS (8 groups; 0 problem(s)) |
| `r2_guards_closed` | `scripts/dd1_d7b_r2_guards.py --phase fixed --bundle results/evidence/dd1_d7b_r…` | 0 | PASS | D7B_R2_GUARDS: PASS (14 probes; 0 still open) |
| `r3_guards_closed` | `scripts/dd1_d7b_r3_guards.py --phase fixed` | 0 | PASS | D7B_R3_GUARDS: PASS (8 probes; 0 still open) |
| `safety_gate` | `scripts/precommit_safety_check.py` | 0 | PASS | SAFETY_GATE: PASS |
| `provenance_gate` | `scripts/provenance_check.py` | 0 | PASS | SOURCE_PROVENANCE_CHECK: PASS |
| `handoff_structure` | `scripts/dd1_d7b_validate_handoff.py reports/agent_handoffs/DATA-7B.json` | 0 | PASS | HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified) |
| `r3_guards_reproduce_on_base` | `python scripts/dd1_d7b_r3_guards.py --phase reproduce --scripts-dir <base b3fe…` | 0 | PASS | D7B_R3_GUARDS: PASS (8 probes; 0 not reproduced) |
| `reviewer_account_states_after_fix` | `python reviewer_account_states.py <this checkout> <diagnostic>` | 1 | PASS | } |

合计 13 条命令，失败 0 条（`-`）；`new_spectre_launches=0`、`new_rtl_simulations=0`、`new_oa_writes=0`；R2 包只读、未被改写（`NO -- read only`）。

本轮验证输入（`verification_input.csv` 摘要）：

| 项 | 值 |
|---|---|
| R2 bundle (frozen; read only) | results/evidence/dd1_d7b_r2_r20261022_160652_e880be |
| R2 files on disk (includes manifest.json) | 287 |
| R2 bytes on disk (includes manifest.json) | 21323343 |
| R2 manifest entries (excludes manifest.json) | 286 |
| R2 manifest covered bytes (excludes manifest.json) | 21264382 |
| R2 manifest.json sha256 | 1b7a74fc6d389cdde8fb4a3b31f045312409eae4bcd004356041110e70daa1cb |
| R2 manifest lists itself | False |
| R2 exporter measurement_source_sha256 | f3da5b53d5c777ec7f60c159fbf4b8840f6257019045146546e1e0a7793fbb7f |
| R2 exporter runner_source_sha256 | dea050a5685eded854502f85c45f8f356acb006e5c421fd084513da5d39b70bc |
| R2 exporter evidence_check_source_sha256 | 92a2d34db1526c2715e4cc616dc865a8e0691a625a89bcf9f52ffa48a676658e |
| R2 base_sha (this round's base) | e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92 |
| R2 run_id | r20261022_160652_e880be |
| base commit verified by this round | b3fe93c17de014cb16031438ce28c7152dd0020f |
| R2 payload commit P2 | 6abe1bf5b93dc4bb12ba179cea0ab26929f33a90 |
<!-- END R3 GATES -->

## 6 冻结全量比较

<!-- BEGIN R3 FROZEN -->
| 冻结面 | 比较路径数 | 不一致 | 前若干不一致 |
|---|---|---|---|
| `development_base_b_all_tracked_paths` | 1107 | 0 | - |
| `accepted_d7b_bundle` | 805 | 0 | - |
| `r1_bundle` | 284 | 0 | - |
| `r2_bundle` | 287 | 0 | - |
| `frozen_case_and_golden_tables` | 3 | 0 | - |
| `measure_core_and_trace_parser` | 3 | 0 | - |
| `shared_safety_runner_and_handoff_validators` | 12 | 0 | - |

比较口径：`git ls-tree -r` 的 (mode, blob) 逐路径对照，不只是列文件名。
<!-- END R3 FROZEN -->

## 7 F2：文档更正清单（机械核对，不改数据）

| 字段/位置 | 原写法 | 更正后 | 依据 |
|---|---|---|---|
| `measured.manifest_entries/bytes` | 283 / 21,084,177 | 286 / 21,264,382（不含 manifest 自身），另列目录 287 / 21,323,343 | 直接读 R2 包 `manifest.json` 与目录 |
| `source_identity.runner_source_sha256` | `64797d53…`（R1 导出器） | `dea050a5685eded854502f85c45f8f356acb006e5c421fd084513da5d39b70bc` | 取自 R2 包 `environment.json`；R3 校验工具摘要单列在 `r3.validation_tools`，不冒充 R2 生产者 |
| `rtl.new_rtl_simulations` | 17 | 本轮 0；`r1_historical_rtl_simulations=17` 另列 | 与 `this_round_cost`、R2 报告 §0 一致 |
| `frozen.tracked_paths_changed_vs_base` | 3（且比较对象是 adcdf27） | R2 相对 H 为 8 条既有路径修改（其中代码 4 条）、291 新增、0 删除；R3 自己的差异另按 `b3fe93c..HEAD` 实测 | `git ls-tree/ diff` 计算，不复制本段数字 |
| `measured.charge_series_new_in_r1` | 27 | 26 条冻结复用 + R1 新增 1（标定带）+ R2 新增 2（OFF/尾段切片）；边邻 26 条因加 `t_ps` 重算 | 读 R2 包 `charge_index.csv` 按系列去重 |
| `known_limitations` 边沿精度 | 0.1 ns | 0.1 **ps**（四位小数 ns 列）；R2 的 `t_ps` 为全精度 | `fmt_edge('%.4f' ns)` 的量化 |
| R2 报告 §4 因果 | "23 条最长带内段不足 10 ns" | 只有 3 条不足 10 ns（8.6106 / 8.9335 / 4.1759 ns），其余是**在截止点前约 0.79 ns 离开带宽**；判决不变 | 由发布包切片重算（数值见该节勘误） |
| R2 报告标题 | 相邻两个"## 8 回执" | 合并为一个 | 结构修正 |
| 回读记录 | 单一时点的 ref 值 | 分列"历史 D2 时点记录"与"R3 推送后当前值"，并写明查询对象、完整 SHA 与通道 | `remote_readback` 与 `r3_readback` |
| `dd1_d7b_contract.md` §16 穿越点验证行 | "切片只印 0.1 ns" | 0.1 **ps**（四位小数 ns 列的量化），并标注为 R3 更正 | 与 `%.4f` 的 ns 列一致的口径 |

## 8 剩余历史事实与边界

1. 历史实际启动 59 次、固定授权 56 次、超支 3 次：仍为 `VIOLATED_NOT_RETROACTIVELY_AUTHORISED`，
   本轮新增 0，不追溯授权，处置权在用户；证据内 `BUDGET_RESPECTED` 继续 FAIL，不加白名单。
2. 四个被删的 R1 中间证据目录原字节不可得，事件照实保留，不伪称恢复。
3. 凭据回显事件未解除：本轮未读凭据、未改密码、未进 guest，也不以扫描 PASS 宣称解除。
4. 既存不可达对象仍按原口径记录（不 GC、不打印内容、不改扫描规则）。
5. `data_en` 是理想 PWL 使能节点，其沿一致不等于片上驱动器延迟已验证；
   电荷 PASS 不等于整段电流已稳定 —— 23 个窗口保留 `NOT_SETTLED_WITHIN_PULSE` 负发现。
6. R3 不重新导出 21 MB 采样：验证目录只放身份、输入摘要、命令与 rc、状态正反例与冻结比较。


另记一条口径：审核方诊断脚本在 Windows 上以 CRLF 写出 `diagnostics/account_states_after.json`，
入仓时被 Git 归一为 LF——该文件不被任何清单摘要绑定（包内清单摘要按 Git blob 计算），
因此新鲜检出的字节与清单一致；这一点与 R2 里"交付的 VCD 必须已是 LF"是同一教训的不同面。

## 9 交付与回执

`TASK_ID=DATA-7B-R3`，`BASE_SHA=b3fe93c17de014cb16031438ce28c7152dd0020f`，
`REPAIR_SCOPE=ACCOUNT_STATE_VALIDATION_AND_HANDOFF_CORRECTION_ONLY`，
`NEW_SPECTRE_LAUNCHES=0`，`NEW_RTL_SIMULATIONS=0`，`NEW_OA_WRITES=0`，
`HISTORICAL_BUDGET_STATUS=VIOLATED_59_OF_56_OVER_BY_3`，`NEXT_STAGE_AUTHORISED=NO`，
`MERGE_PERFORMED=NO`，`SOA_SIGNOFF=NO`，`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`。

推送、双路回读与审核包路径在 §10（由推送之后的元数据提交记录，不由本文件自称）。

## 10 推送与回读

```text
git -c http.proxy=http://127.0.0.1:7892 push -u origin poc/data-pwm-d7b-r3   rc=0（新建分支，普通 push，非 force，未跳 hooks）
方法一  git -c http.proxy=http://127.0.0.1:7892 ls-remote origin   rc=0  22 行 ref（推送前 21 行）
方法二  gh api repos/LINboss666/microled-ic-ai-lab/git/ref/heads/<ref>   rc=0  逐个读取 5 个 ref
```

| 查询对象（refs/heads/…） | 两条通道读到的同一完整 SHA | 与上一轮的关系 |
|---|---|---|
| `poc/data-pwm-d7b-r3` | `039a28a35cab506beb498259025eb50c20964ce2`（此前一次回读为 `19f86ce16491f56dc6c223bdbcc789b5ef399291`，再前一次为 `a670a1190569f1fcf28338a2b8865d0bfbbf2f3b`；每次回读都标查询时间） | 本轮新建（P3 `242f43fdd4c775d4e92ebddde548e65b75aec402` 是其祖先，`git merge-base --is-ancestor` 为真） |
| `poc/data-pwm-d7b-r2` | `b3fe93c17de014cb16031438ce28c7152dd0020f` | 未动（本轮 base） |
| `poc/data-pwm-d7b-r1` | `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92` | 未动 |
| `poc/data-pwm-d7b` | `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50` | 未动 |
| `main` | `23e471cb936b421ee97e1250c3be06edf96f9937` | 未动 |

两条通道（`git ls-remote` 经本机代理，与 `gh api` 直连）在同一时刻对同一对象给出同一完整 SHA。
表中 SHA 是**写入本节的记录提交之前**的分支 tip；承载这段文字的记录提交再多一枚，其 SHA 只从
远端 ref 读，不由本文件自称。两条通道是同一对象的两个独立读法，不是两枚不同的证明；
这只是 ref 的回读，不表示技术结论由审核方接受。

审核包（全部取自本分支已提交的 blob，不复制旧电流样本）：
`review/scratch/MicroLED_DATA7B_R3_Package_20261023.zip`，构建器
`review/scratch/r3_build_package.py`（§3 允许的 scratch 工具，不入库；它只用 `git cat-file blob <rev>`
读提交，不读工作副本，且清单为空时主动拒收）。构建来源是本节所在那枚提交的 tip，其 SHA 由包内
`MANIFEST.json` 的 `commit` 字段给出、不由本文件复制。归档内 **56 个文件**：`MANIFEST.json`（54 条：
R3 两件改动工具、它们调用的全部冻结工具与更早轮次套件、`tests/dd1_d7b/` 三张只读表与 RTL/TB、
四份任务书、R1/R2/R3 三份报告、合同与 pwm_current 两份口径文档、交接 MD/JSON，以及**两枚都已提交的
`dd1_d7b_r3_*` 验证目录**）+ `verify_package.py` + `README.md`；较早那枚目录是 §0.6 记录缺陷的披露历史，
只携带最新那枚会让本包读成"只给审核方看对的那一次运行"，所以两枚都进包、并说明哪一枚权威。
自检 `python verify_package.py` 逐条核对清单内文件的字节数与 SHA-256，并对未列出的文件报失败。

- 本包**不写自身归档摘要**：包内任何文件一旦记下 zip 的 SHA-256，那次记录本身就改变了 zip。
  因此包内只留可自证的两项（`MANIFEST.json` 的 `commit` 与只读 R2 输入 `manifest.json` 的 SHA-256），
  zip 的字节数与 SHA-256 记在本段所在提交之后的元数据提交信息里（`git log` 可查）与交付回执中。
- **本包曾经的一次错误声明（不得抹去）**：提交 `f2fcae4` 的信息写了
  "Also recorded here: the reviewer package rebuilt from the pushed tip"，而那次 `r3_build_package.py`
  正因为提交里出现两枚 `dd1_d7b_r3_*` 目录而主动拒收并退出，磁盘上留下的仍是更早（`19f86ce` 时点、
  47 条目）的归档——"按已推送 tip 重建"当时并未发生。本节按构建器现在的真实行为改写（携带全部已提交
  目录、点名权威目录、去掉自指的摘要），改的是构建器的选取规则与这段说明，不是判据、数据或电气结论。
