# DATA-7B-R1 返修报告：测量、执行守护与证据复核（2026-10-22）

任务书 `reports/tasks/DATA-7B-R1.md`（逐字节副本，SHA-256
`d35233770fb7bb9a52050937024a16c4106723094493b2c1381cae333b068bf3`，14,185 B）；
审核意见 `REVIEW_DATA7B.md` 判定 REWORK。

| 身份 | 值 |
|---|---|
| 本轮基线 T | `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50` |
| T 的功能载荷 P | `9d73cc184a266e646ae827f0350f7c931d9faa25` |
| 开发基线 B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 被接受的 DATA-7A | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| main（未动） | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 分支 | `poc/data-pwm-d7b-r1`（本轮新建，工作树 `D:\ic617_d7b_r1`） |
| 交付证据 | `results/evidence/dd1_d7b_r1_r20261022_122204_05417c/`（发布 283 个文件；manifest 覆盖 282 条 / 21,199,023 B，上限 33,554,432 B） |
| 证据内记录源码身份 | measure `06079331aaaff1ef748198da80ccad8bafc5355fb4dd1cc8a555a1c17e7d474f`；runner `5e3b00d4b6f4…`；trace `8ae5edf9e814c13fea411b3d67e8e4e1f26fd1f394a080833b48675ad8cdb0ce`；evidence_check `e486aaa18eca…`（四个摘要与盘上脚本逐个重算一致，完整值在包内 `environment.json`） |
| 外部成本 | 新增 Spectre 进程 **0**；新增 OA 写入 **0**；新增四态 RTL 仿真 **17**（上限 17，已用满） |

本报告不写自身摘要或大小；最终身份从固定 Git blob 与包外回执读。

## 0 本轮操作记录（含破坏性动作，不得省略）

1. **我删除了四个自己刚发布的中间 R1 证据目录**（发布后又被下一条命令 `rm -rf` 清掉）：
   `dd1_d7b_r1_r20261022_105514_12119e`（发布记录 264 文件 / 20,255,993 B）、
   `..._105959_806e84`（264 / 20,270,467）、`..._111106_b3171e`（282 / 21,237,550）、
   `..._111346_e3f62c`（282 / 21,237,557）。
   动因是我在"改脚本→重导出"的迭代里清理上一版，以免 `results/evidence/` 下同时留着多份候选包。
   这四个目录当时都**未提交、未推送**，其内容可由保留的 raw 字节与当时的脚本重新生成，但
   **原始字节已不在机上**。用户在本轮中途明确指示不得先删记录再重做，此后我改用新 staging 目录 +
   新 run_id，并保留已发布目录。机上留下三个被后续脚本改动取代的中间件，保持原样不提交：
   `..._112014_0b7ee2`（manifest 281 / 21,179,420 B，`environment.json` 还没有
   `evidence_check_source_sha256`）、`..._115827_ee0cc6`（281 / 21,185,208 B，其复核器摘要
   `fe4cd40ebb84` 是"参照包自比"修正之前的版本）、`..._120120_65fd92`（281 / 21,190,894 B，
   复核器摘要 `45f41cf4949d`，还没有 `gate_records.csv`）。交付的是
   `..._122204_05417c`（282 / 21,199,023 B，复核器摘要 `e486aaa18eca`，含 `gate_records.csv`）。
   四个都在机上，用当前复核器逐个重跑：三个中间件是 `BUDGET_RESPECTED` + `GATE_RECORDS_SHIPPED`
   两项 FAIL（它们确实没带 gate 记录，不隐藏），交付包 39 项里只剩 `BUDGET_RESPECTED`。
   输出留在 `review/scratch/r1_gates/`，不提交。
2. **凭据回显事件（独立记录，不视为已解除）**：本轮早些时候一条 `grep -vE` 过滤式写错，使 guest 口令
   值在本机终端输出中出现过一次。该值没有写进任何任务文件、报告、日志摘录、JSON、README、记忆文件或
   Git 对象；本任务不授权修改 guest 口令，我也没有做远端扫描，因此**不使用"远端扫描 PASS"宣称事件
   已解除**。口令仍只按既有规则在运行时从 `D:\ic617_agent_bridge\.ic617_agent_bridge_credentials` 取用，
   该文件不入 Git。
3. 32 MiB 上限问题的处理方式是**删除每行重复的标识列**（分片从 8 列并回交付轮的 `t_ps,iout_A` 两列，
   样本数一条不减），不是删证据腾空间；结果 59,893,603 B → 21,199,023 B。

## 1 A 组：执行入口与累计额度

### A1 默认入口未经过仿真授权检查

* 旧 T 复现：在 T 字节上不带任何模式旗标调用 `scripts/dd1_d7b_run.py`，会落到原生分支并尝试建 SSH；
  即使 `QODER_SIM_AUTHORISED` 未设，也是在准备阶段之后才拒。
* 根因：模式判定用"如果没走离线分支就走原生"，没有闭合集；授权检查位于路径准备之后。
* 修改（`dd1_d7b_run.py`）：`MODES` 成闭合集，无模式/多模式/冲突模式一律在 `main()` 入口拒；
  `AUTH_VARS` 未同时置位即拒；新增 `--cal-from` 一律拒（本轮不允许"补产生"标定）；
  任何拒收发生在**创建目录之前**，`RuntimeError` 统一转 `D7B_REFUSED` 且 rc=5。
* 修后正例：`python scripts/dd1_d7b_run.py --dry` → `D7B_DRY: PASS (decks and gates only, 0 Spectre
  launches, 0 remote calls)`，rc=0。
* 修后反例：守护脚本 3.1/A1 组：无模式、模式冲突、未授权、带 `--cal-from`、账户已播种 → 全部 rc=5，
  且断言 `Link` 从未被构造、`masters` 未推送、磁盘上没多出目录。
* 命令与 rc：`python scripts/dd1_d7b_r1_guards.py` → rc=0，`A1 entry routing PASS`。

### A2 重开账本会清零并覆盖历史

* 旧 T 复现：`process_ledger.csv` 写在共享路径，新一轮重开把行覆盖掉；交付包只剩 58 行
  （27 preflight / 27 dut / 4 static_negative），而 `launches_reconcile.csv` 逐目录合计 59。
  旧 `launches_used_after` 最大值 42 只是 `r11_main` 单 run 的局部计数，被误当成整轮数。
* 根因：一个文件同时当"本轮流水"和"整轮账本"，且启动前的计数只在成功后写。
* 修改：`AppendCSV`（加载既有行、ID 连续性校验、拒丢弃行、字段禁逗号/换行、原子 flush）之上分两个对象 ——
  `Ledger`（每轮，发布后为空）与 `Account`（任务级持久，**从冻结的
  `dd1_d7b_r11_main/launches_reconcile.csv` 播种**，验证逐目录和与 TOTAL 后才接受）；
  `reserve()` 在**启动之前**记账并抛 `OverBudget`，崩溃后孤立的 REQUESTED 由 `recover()` 转 UNCERTAIN
  且继续占额度；`--remeasure` 断言账户 confirmed 前后不变。
* 修后正例：交付包 `launch_account.csv` 134 行 = 59 CONFIRMED（30 preflight + 29 dut）+ 75
  REFUSED_NO_LAUNCH（本轮 3 次离线导出各 25 条拒启动，0 次启动不占额度也不隐藏）。
* 修后反例（`dd1_d7b_r1_guards.py` 实测）：55/56/59 边界、跨进程重开、崩溃→UNCERTAIN 仍占额度、
  preflight 内层启动只计一次、拒收启动仍占位、已播种历史再播种被拒、谎报 TOTAL 的 reconcile 被拒、
  30/29 角色拆分、账本重开丢行/偷行/改表头均拒。
* 命令与 rc：`python scripts/dd1_d7b_r1_guards.py` → rc=0（`A2 ledger reopen`、`3.1 launch account` PASS）。

### A3 复用分支位置、发布前校验缺陷

* 旧 T 复现：`--reuse` 分支曾插进 `static_probe` 循环，使本应 0 启动的补齐轮新起 4 次进程；
  发布前只做字符串级检查，语义错误可进正式目录；"复用"只抄账本里一个非空摘要并取 glob 第一个文件。
* 修改：`resolve_reuse()` 逐案例按 **deck / PWL / masters / raw / psf / log 的字节摘要 + 转录 rc=0 且含
  SPECTRE 行** 选取唯一原生 run；一个转录或一个原生 run 不唯一即拒；器件摘要、实例行、条件、PWL 前缀
  与 stop 逐条比较（只允许文档化的 `STOP_MARGIN` 悬持点不同，写进 `identity_notes`）；
  `section` 从 deck 的 include 行读、`temp` 从 psf 的 `temp` 列读并与 deck 交叉核对（不再硬编码 tt/27）；
  复用拆分在任何启动**之前**完成；`publish()` 先跑完整语义检查，除
  `BUDGET_RESPECTED` 外任何失败都拒收，并证明拒收前后正式目录清单与摘要不变；
  manifest 在发布前写；run_id 必须匹配 `^r[0-9]{8}_[0-9]{6}_[0-9a-f]{6}$` 且目标目录不存在。
* 修后正例：24 个案例全部标 `reused_from=adcdf27`，`src_native_run` / `src_launch_id` /
  `measurement_source_sha256` 逐行落在 `cases.csv`。
* 修后反例（守护 3.3 组）：raw 漂移、两个候选 run、PWL 漂移、netlist 不同、master 互换、缺 preflight 孪生、
  未知案例、spec 格式错、dut 行重复 —— 全部被拒；发布闸反例用桩检查器证明
  `MATRIX_COMPLETE CHARGE_RECOMPUTED` 之类的失败会阻止移动，且拒收后正式目录逐条不变。
* 命令与 rc：`A3 byte-verified reuse PASS`、`A3 publish gate PASS`，rc=0。
  本轮真实拒收也发生过：`--publish` 在 `TRACKED_BYTES_WITHIN_LIMIT`（59.9 MB > 32 MiB）与
  `BUNDLE_CONTENT_CLEAN`（`.vcd` 不在文本白名单）时分别 rc=6、正式目录未被创建，之后才按第 0.3 条修正。

## 2 B 组：时间测量与正负积分

| # | 旧 T 的可复现错误 | 根因 | 修改 | 修后真实数值 | 手算/合成反例 |
|---|---|---|---|---|---|
| B1 | 12 个窗 `de_fall_50_ns` 为空，`off_ns` 一律等于窗口末（短码窗写 11595、P50/H200 写 16715）；未找到沿时静默回退到 `t1` | 下降沿只在整窗末 500 ns 内找；找不到就用 `t1` 当关断 | 逐"声明脉冲段"找上升/下降沿（段取自冻结 trace 的 `segments_ps`，并与 `full_intervals>0` 互校）；找不到记 `NOT_FOUND` 并计入 `pulse_edges_missing`；无导通沿的窗写 `NOT_APPLICABLE_NO_CONDUCTING_EDGE`，不虚构关断延迟；新增 `de_fall_delay_ns` 与 `turn_off_delay_ns`，绝对时刻与延迟分列 | `D7B-P30-C001/normal` 的 `de_fall_50 = 3945.0000 ns`、关断点 `3968.0376 ns`、延迟 `23.0376 ns`（旧表这两列是空与 11595）；`C002 3975.0000`、`C016 4395.0000`、`H120-C01 4035.0000`、`H200-C01 4115.0000`、中止窗 `4050.0000`、恢复窗 `12615.0000`；`pulse_edges_missing` 全表 0 | 测自 T9（3,945,000 ps 的真实短脉冲下降沿）、T9d/T9e/T9f：短脉冲、末段保护中止、无导通沿三类各一条手算用例 |
| B2 | 19 个窗记 `SETTLED`，包括脉宽不足 10 ns 的 1/2 码 | "持续入带"只要求存在一段 ≥10 ns，且允许越过下降沿继续算 | `sustained_in_band()` 以**下降沿为排他期限**（`t < until_ps`），要求入带段一直延伸到期限且长度 ≥ 10 ns；新增 `longest_in_band_ns` | 23 个窗 `NOT_SETTLED_WITHIN_PULSE`、3 个黑码/N1 窗 `NOT_APPLICABLE_NO_CONDUCTING_EDGE`、1 个标定行 `MEASURED`；`C001` 最长入带 `8.6106 ns`、`C002 38.6106`、`C016 458.6106` | T6b/T6c：一段 10 ns 入带但在期限前出带 → `NOT_SETTLED_WITHIN_PULSE`；审核者探针同判 |
| B3 | `q_positive` / `q_negative` 把同一块面积计了两次（例：`P30-C002/normal` 交付 7.528301435e-13，样本重算 7.527008626e-13） | 正负面积按符号分桶，未在过零点切段 | `signed_areas()` 在**插值过零点**处分段；`integrate()` 断言 `q == q_pos + q_neg`（相对 1e-9） | 26 个判定窗恒等式全部成立；`D7B-BLANK/aborted` 修正为 `q_pos 1.872582122e-12 / q_neg −3.116815209e-15` | 手算三角波 ±5e-10 的对称分解；T1–T16 共 22 项 |
| 附加 | 关断只扫到第一次反弹 | 先低后反弹被判"永远不会再关断" | `turn_off()` 在关断段内继续扫，`OFF` 附 `transient_off_ps`；真反弹给 `NOT_PERMANENTLY_OFF_BY_SEGMENT_END` + `first_rebound_ps`；另有 `NEVER_WITHIN_LIMIT` / `NO_DATA_IN_OFF_SEGMENT` | 26 窗 `OFF`，唯一 `NEVER_WITHIN_LIMIT` 是 N1（常亮负例，预期如此） | T4/T5 手算反弹用例 |

`python scripts/dd1_d7b_measure.py --selftest` → **rc=0，22/22 PASS**。
既有 18/18 只作历史对照，新反例已并入 22 项，不为旧数背书。

## 3 C 组：证据复核器（39 项语义检查）

原复核器 20 项在未改交付上只有预算项失败，但审核者注入 8 类错误后除第 6 类外都不产生对应失败
（第 6 类甚至让它 rc=0 全 PASS）。重建后的复核器从冻结契约
`tests/dd1_d7b/{cases,golden_windows}.csv` 独立重建 `(case_id, window)` 全集、角色、模式、合法码域、
tick/窗口映射、`maxstep`、输入沿与收敛配对；整数离散量用 Decimal 严格判（30.5 不再被 float→int 截断
放过），真实 PSF 采样时间保留非整数 ps 并受显示量化界 `time_quantum_ps` 约束。

审核者 8 类反例，每类都在 `--selftest` 里得到**自己的**新失败或新原因（对提交字节的一次性副本执行，
正式证据逐条未变，`SELFTEST_BASELINE ... rc=1 failures=14 项`）：

| 反例 | 注入 | 现检查名 | 实测 |
|---|---|---|---|
| 1 | P30 code1 关断电流改 15 µA 仍写 PASS | `LAST_100NS_RECOMPUTED` + `ELECTRICAL_VERDICT_CONSISTENT` | rc=1，两项成为新失败 |
| 2 | QLSB/Qexpected 同时加倍（重算约 −0.663）仍写 PASS | `QLSB_BOUND_TO_ICAL` + `ELECTRICAL_VERDICT_CONSISTENT` | rc=1，新失败；LSB 绑回 `Ical×T` 并按原判据重判 |
| 3 | 黑码 PWL 改恒高 | `DECK_AND_PWL_BOUND` | rc=1，新原因 `D7B-P30-C000: the PWL file hashes to 0ad2ae761b2c, the row says 0d395267d43f`（文件名改为真实 `<case>_pwl.txt`，缺文件不再跳过） |
| 4 | 删 FAULT 恢复窗 | `WINDOW_SET_COMPLETE` | rc=1，新失败 |
| 5 | convergence.csv 只留表头 | `CONVERGENCE_SET_COMPLETE` | rc=1，新失败（空表按名字报告，不再"已复核"） |
| 6 | reconcile TOTAL 由 59 改 27、分量仍 59 | `RECONCILE_SUMS_TO_TOTAL` | rc=1，新失败（逐目录求和 + 账户覆盖 + 每轮空账本仅在 0 启动时被接受） |
| 7 | `tick_ns` 改 30.5 | `DISCRETE_VALUES_MATHEMATICAL` | rc=1，新失败 |
| 8 | N1 观测电荷/峰值改 0 保留 YES | `NEGATIVES_BOUND_TO_BYTES` | rc=1，新原因 `D7B-N1: charge 0.0 disagrees with its case row 1.146770353e-10` |

另补齐：标定样本从字节重算（`CALIBRATION_SAMPLES_RECOMPUTED`，缺 raw 时点名
`BLOCKED_MISSING_RAW` 而非沉默）；tail/峰值/边沿都要有夹持样本（`PEAK_AND_TIME_RECOMPUTED` 要求在声称
峰值时刻 ±2 ps 内找到一条等于重算峰值的交付样本；`EDGES_BRACKETED_BY_SAMPLES` 核 92 个交叉）；
收敛不仅查 dQ，还对峰值/边沿与各自限值重判；`EVERY_SHARD_IS_INDEXED` 拒绝索引未点名的分片序列
（旧包 26 个 edge 序列正是这种"绑不上案例的字节"）；`CHARGE_SERIES_MATCHES_ACCEPTED` 把每个序列的
样本行摘要与冻结的 `dd1_d7b_r11_main` 直接比对；`IDENTITY_CHAIN` 区分**原生 run 身份 / 测量源码身份 /
本轮导出身份**；`MANIFEST_*` 三项管清单覆盖、无自指摘要与字节上限。

* `python scripts/dd1_d7b_evidence_check.py --selftest` → **rc=0**，`D7B_EVIDENCE_SELFTEST: PASS
  (8 counterfeits, 0 problem(s))`；缺基线时判 FAIL rc=1，**没有 SKIP 成功路径**。
* `python scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_r1_r20261022_122204_05417c` →
  **rc=1**，39 项中唯一失败 `BUDGET_RESPECTED`。
* `python scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_r11_main` → **rc=1**，14 项具名失败：
  `EVERY_SHARD_IS_INDEXED CHARGE_RECOMPUTED SETTLED_RECOMPUTED EDGES_BRACKETED_BY_SAMPLES
  CALIBRATION_SAMPLES_RECOMPUTED DECK_AND_PWL_BOUND NEGATIVES_BOUND_TO_BYTES CONVERGENCE_RECOMPUTED
  ACCOUNT_KEEPS_HISTORY ACCOUNT_COVERS_RECONCILE BUDGET_RESPECTED IDENTITY_CHAIN RTL_EDGES_REVERIFIED GATE_RECORDS_SHIPPED`。
  旧包目录一字未动，这份清单是"旧交付曾报什么"的记录，不是对新包的评价。
* `python scripts/dd1_d7b_run.py --selftest` → rc=0（11 项）；`dd1_d7b_trace.py --selftest` → rc=0（13 项）。
  `--selftest` 的夹具现在全部从**已提交**的 `pwl_edges_*.csv` / `cases.csv` 重建，不再依赖未提交的
  `review/scratch/traceout`（审核者曾在 T 上遇到 FileNotFoundError）。

## 4 D 组：报告与交接由同一复算结果生成

逐项更正（旧值来自 T 的字节，新值来自 R1 交付包，两者都可复算）：

| 项 | T 的说法 | 复算后的事实 | 证据 |
|---|---|---|---|
| 进程数 | 报告写"本轮 Spectre 进程 27"，JSON 写 `spectre_launches/dut_runs/preflight_runs = 27` | 整轮 **59**（30 preflight + 29 dut）；27 只是幸存账本被旧字符串识别出的行数；`environment` 的 42 是 `r11_main` 单 run 局部计数 | `launches_reconcile.csv`、`launch_account.csv`、`reports/tasks/DATA-7B-BUDGET-01.md` |
| 账本 | 58 行 | 58 行 = 27 preflight + 27 dut + 4 static_negative，**不等于** 59；差额由共享路径覆盖造成 | T `process_ledger.csv` + 本节 A2 |
| 额度 | "授权 52、追加后 56"（旧结论还把超额写成 0） | 52 → 追加 4 → 上限 56，实际 59，**超额 3**，状态 `VIOLATED_NOT_RETROACTIVELY_AUTHORISED` | 同上 |
| 状态 | 报告 `EVIDENCE_STATUS = PASS`，JSON `scope_status = COMPLETE` | 本轮 `EVIDENCE_STATUS` 由检查器给出：39 项 1 失败 = 仅 `BUDGET_RESPECTED`（历史事实），旧包在同一大检查下有 13 项具名失败 | `review/scratch/r1_gates/` 两份检查输出（正式记录以交付包内表为准） |
| 包范围 | B..P 新增 818 个文件 | B..P = 818，**B..T = 820**（P 之后还有 2 个元数据文件）；两个数不能混用 | `git diff --name-status c3513ff 9d73cc1` = 818 A；`... adcdf27` = 820 A |
| 标定 | 断言"从产物反读 section/temp"，但表里 `section_read=tt`、`temp_read` 为空，标定值只是记录值 | 标定带 `1000` 个样本、积分区间 `4.994999999998259e-07 s`，`section` 从 deck include 行读为 `tt`，`temp` 从 psf `temp` 列读为 `27.0000 °C` 并与 deck 交叉核对；`Ical = 1.493190564e-05 A`（15 µA ±5 %） | `calibration.csv` + `charge_D7B-CAL_cal.*.csv` 分片 |
| 收敛 | `D7B-CVG-P30-C001` 行 `BLOCKED_MISSING_PARENT`，另两行 `delta_edge = NOT_FOUND_BOTH` | 母案例已在包内，离线补齐后 5 对全 `CONVERGED`：`C001 dQ=0.000036 / 限 0.004480 pC，dPeak=0.030166 / 限 0.837662 uA，dEdge=0.0000 ns`；其余 4 对同表 | `convergence.csv` |
| N1 | `negative.csv` 列名带 `_A` 却填 `14.93190564`，`run_id` 空 | 列名改为诚实单位 `window_peak_uA` / `last_100ns_max_abs_uA`；`q_win = 1.146770353e-10 C = +256.000000 LSB`；身份补齐 `src_native_run=r11_main`、`launch_id=r11_main/L032`、deck/raw/transcript 摘要；判定 `EXPECTED_REFUSAL / WIRING_FAULT_DETECTED` | `negative.csv` |
| N2 | 判定只有 `YES` | 补齐 `rc=1`、`stage=supply_contract`、拒绝原文 `net vss (Xstage port vss) has no independent source from reference node 0`、该目录 `spectre_launches=0`、转录摘要与 `src_native_run=r11_reuse` | `negative.csv`、`decks/D7B-N2.scs`、`transcripts/carried_r11_reuse_*` |
| 末 100 ns | "全都 ≤ 0.74 pA" | 非 N1 全局最大 **2.0600878e-08 A ≈ 20.60 nA**（在 `D7B-P50-C255/normal`，审核者独立读到约 20.65 nA），仍 < 150 nA 判据；0.74 pA 那种说法把电荷量当电流 | `cases.csv` `last_100ns_max_abs_A` |
| P30 code1 | 容易被读成"约 −32.6 % 电荷缺口"是判据失败 | 实测 `Qwin 3.018093995e-13 C` 对目标 `4.479571693e-13 C`，即 `−0.326254 LSB / −0.146148 pC`，**在冻结的 ±0.5 LSB 判据内**；范围只到"单窗口净电荷"，不是光学有效位数，也不是全程电流稳定 | `cases.csv` 与电荷分片 |
| 峰值 | 只说"约 16.8 µA" | 最大窗口峰值 `1.684531296e-05 A`（`D7B-P30-C016/normal`）；黑码窗只有 OFF 基线 `7.338544869e-13 A` | `cases.csv` |
| 分片 | 26 个 `edge_*` 序列没进索引（"存在但绑不上案例"） | 全部列入索引并逐片校摘要/行数/首末行号；电荷 26 个序列与冻结包**逐字节相同**，新增 27 个序列（1 个标定带 + 26 个边沿片）在索引里显式标 `NEW_IN_R1_NOT_IN_ACCEPTED_BUNDLE` | `charge_index.csv` |

## 5 RTL 边沿复验（17 次，用满上限）

`scripts/dd1_d7b_r1_rtl_reverify.py`（本轮新增离线助手）：一次编译冻结
`tests/dd1_d7b/tb_dd1_d7b_pwm.sv` + `rtl/dd1_d7a_gray_ctrl.sv`
（`iverilog -g2012 -Wall`），对 17 个 trace 案例各跑一次 `vvp +CASE=… +VCD=…`，
再用**冻结** `dd1_d7b_trace.py` 的 `case_document()` 解析新 VCD，与交付的
`trace_<case>.json` 逐字段比：`data_en`/`data_en_b` 边沿、tick 采样沿、`clk_period`、`tick_lead`、
`end_ps`、中止/黑码/故障边沿与 `cfg_version/pam_sel/win_state`，以及每个窗的
`segments_ps`、`t0/t1/t_stop`、`conducted_ps`、`accepted_ticks`、`pwl_points` 与 `pwl_sha256`。
共比对 **304 个字段，17/17 AGREE**；新 VCD 的 `$date`、mtime 与摘要与原生身份分开记录
（`accepted_vcd_sha256` ≠ `new_vcd_sha256` 17/17，且 `accepted_vcd_on_disk_sha256` 与文档一致 17/17），
新 VCD 字节随包交付（17 个文件，953,717 B）。TB 与 RTL 未为凑一致而改：
`git diff adcdf27` 只有 3 个 `scripts/` 文件改动。

* 命令与 rc：`python scripts/dd1_d7b_r1_rtl_reverify.py --trace-dir
  D:/ic617_d7b/review/scratch/traceout --out review/scratch/r1_rtl2` → rc=0，
  `NEW_RTL_SIMULATIONS 17 (ceiling 17)`，`RTL_REVERIFY_CASES 17 AGREE=17 MISMATCH=0`。
* 反例（证明 AGREE 不是空判）：对已交付文档做五类离线篡改后重比 ——
  `segments_ps` 末段 +1 ps、`pwl_sha256` 换成 64 个 0、`t0_ps` +1000、`tick_lead_ps` +5000、
  以及把两个不同码的文档互相比 —— 全部 `MISMATCH` 并点名被改字段；未改文档自重比为 `AGREE, fields=16`。
  这些控制只读文档、不启仿真，因此没有超出 17 次上限。
* 复核器侧：`RTL_EDGES_REVERIFIED` 要求每案例一行、`verdict=AGREE` 且 `fields_compared>0`、
  新 VCD 在包内且摘要自洽、`accepted_vcd_sha256` 与 `source_identity.json` 一致、
  `rtl/tb` 摘要等于盘上冻结文件、行数 ≤ 17、新 VCD 必须带 `$date`；缺 `rtl_reverify.csv` 直接 FAIL
  （旧包正是这样被点名的）。
* 环境坑（记一条）：本机 `oss-cad-suite/bin/vvp.exe` 需要把 `oss-cad-suite/lib`（`libgcc_s_seh-1.dll`、
  `libstdc++-6.dll`）放进 PATH，否则报 `libvvp-1.dll` 打不开；助手内已按此定位工具。

## 5.5 自测与写保护/假 Link 记录随包交付

任务书 §6 要求新证据目录里带上"自测、写保护/假 Link 记录"。这类记录最容易出的问题有两个：一是手工粘贴
可以改行，二是守护脚本的 fixture 路径本身就带本机用户名与绝对路径，粘进仓库就等于把机器信息提交上去。
所以记录是机器生成的：`scripts/dd1_d7b_r1_gate_records.py` 用 `subprocess` 逐条跑 5 个离线门
（measure 自测、入口自测、trace 自测、8 类篡改自测、执行守护），只保留每条命令的 rc 与它**实际打印**的判词行，
含本机路径的行整行丢弃并计数（`lines_dropped_for_local_path`），再写成 `gate_records.csv`。

导出侧 `carry_gate_records()` 在复制进包之前先拒绝：缺文件、缺任何一个门、任何门 rc≠0 或 verdict≠PASS、
`printed_lines_kept=0`（PASS 却没有一行打印支撑）、任何字段仍含本机路径模式、以及
`starts_spectre/opens_socket/writes_outside_ignored` 不是 `NO`。复核器再用 `GATE_RECORDS_SHIPPED`
从包内字节独立复核同一组条件；缺文件直接 FAIL，所以旧包与两个早期中间件都被这一项点名。

* 命令与 rc：`python scripts/dd1_d7b_r1_gate_records.py --out review/scratch/r1_gaterec` → rc=0，
  `GATE_RECORDS 5/5 PASS`；随后 `--gate-records review/scratch/r1_gaterec` 的导出 rc=0 并发布。
* 反例：早期三个中间件包因为没有 `gate_records.csv` 被当前复核器判 `GATE_RECORDS_SHIPPED` FAIL（实测
  rc=1，见 §0.1），这条不是设计说明而是真发生过的拒收路径。
* 记录的是**工具门**，不含交付包自身的检查结果；包自身的结论以复核器现场输出为准（§3、§6）。

## 6 门与真实 rc（最终字节）

| 命令 | rc | 关键输出 |
|---|---:|---|
| `python scripts/dd1_d7b_measure.py --selftest` | 0 | `D7B_MEASURE_SELFTEST: PASS (22/22)` |
| `python scripts/dd1_d7b_run.py --selftest` | 0 | `D7B_RUN_SELFTEST: PASS (11 checks)` |
| `python scripts/dd1_d7b_trace.py --selftest` | 0 | `D7B_TRACE_SELFTEST: PASS (13/13)` |
| `python scripts/dd1_d7b_evidence_check.py --selftest` | 0 | `PASS (8 counterfeits, 0 problem(s))` |
| `python scripts/dd1_d7b_r1_guards.py` | 0 | `D7B_R1_GUARDS: PASS (8 groups, 0 problem(s))` |
| `python scripts/dd1_d7b_r1_rtl_reverify.py …` | 0 | `17 AGREE / 0 MISMATCH`，`NEW_RTL_SIMULATIONS 17 (ceiling 17)` |
| `python scripts/dd1_d7b_run.py --remeasure … --publish` | 0 | `NEW_SPECTRE_LAUNCHES 0`、`PUBLISHED …122204_05417c` |
| `python scripts/dd1_d7b_evidence_check.py <交付包>` | 1 | 39 项唯一失败 `BUDGET_RESPECTED`（历史事实，已披露） |
| `python scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_r11_main` | 1 | 14 项具名失败（第 3 节） |

冻结核对：`git diff --name-only adcdf27` = `scripts/dd1_d7b_evidence_check.py`、
`scripts/dd1_d7b_measure.py`、`scripts/dd1_d7b_run.py` 三个（第 2 节允许修改的工具）；
新增只有 `scripts/dd1_d7b_r1_guards.py`、`scripts/dd1_d7b_r1_rtl_reverify.py`、
`results/evidence/dd1_d7b_r1_r20261022_122204_05417c/` 与本轮文档。
B 的全部旧跟踪路径、冻结 D7B 电路/输入（`spectre/`、`tests/dd1_d7b/{cases,golden_windows,tb_dd1_d7b_pwm.sv}`、
`rtl/dd1_d7a_gray_ctrl.sv`）、共享 runner/preflight/supply checker（摘要见
`environment.json.frozen_tools`）与整个 `dd1_d7b_r11_main/` 均未变。

## 7 仍未解决（不靠本轮工具掩盖）

1. **历史超支 3 次**：`BUDGET_RESPECTED` 仍是 FAIL，处置权在用户；本轮没有追加授权，也没有把 59 说成已授权。
2. 短窗建立/关断行为是真实物理事件，不是本轮能"修好"的：23 个判定窗 `NOT_SETTLED_WITHIN_PULSE`，
   导通初期峰值最高 `16.845 µA`。是否为此改输出级由用户决定，本轮不改电路。
3. 交付包内没有原始 PSF/VCD 与 PDK 内容，只有可从保留 raw 复算的样本分片；参照包的
   26 个电荷序列以"逐字节相同 + 摘要登记"的方式引用，而非重复搬运。
4. 四个被删除的中间 R1 目录不可复原（第 0.1 条）。它们的 run_id、文件数与字节数已在上面登记。
5. 凭据回显事件仍未被"解除"，也未由远端扫描证明（第 0.2 条）。
6. `tests/dd1_d7b/r1/` 固定夹具目录未新建：本轮夹具由 `--selftest`/守护脚本从已提交字节在进程内合成，
   可在新 checkout 独立复现（审核者要求的"缺 fixture 不许 SKIP"已满足）。
7. 未合并 main、未动旧分支、未 GC、未跳 hooks；`NEW_RTL_SIMULATIONS` 已用满 17，后续若需再复验要另行授权。

## 8 回执

```text
TASK_ID=DATA-7B-R1
BASE_SHA=adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50
REPAIR_SCOPE=MEASUREMENT_EVIDENCE_AND_EXECUTION_GUARDS_ONLY
NEW_SPECTRE_LAUNCHES=0
HISTORICAL_SPECTRE_LAUNCHES=59
HISTORICAL_AUTHORISED_CEILING=56
HISTORICAL_BUDGET_OVERRUN=3
NEW_OA_WRITES=0
CIRCUIT_AND_STIMULUS_CHANGED=NO
RAW_REUSED_FROM=native runs r5_cal/r9_main/r10_main/r11_main/r11_reuse (24 案例逐行 src_native_run +
  src_launch_id；deck/pwl/raw/log/psf 摘要在 cases.csv 与 source_identity.json；
  reused_from=adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50)
NEW_RTL_SIMULATIONS=17
EVIDENCE_INTEGRITY_STATUS=PASS_WITH_DISCLOSED_HISTORICAL_BUDGET_FAILURE
  (39 项检查；唯一 FAIL=BUDGET_RESPECTED；旧包同检查 14 项具名 FAIL)
MEASUREMENT_AND_GUARD_FIX_STATUS=PASS
  (measure 22/22、run 11、trace 13/13、篡改自测 8/8、守护 8 组、边沿复验 17/17 AGREE 304 字段)
PWM_CURRENT_FEASIBILITY_TT=PASS_WITHIN_FROZEN_CRITERIA
  (25 个判定窗 |charge_error_LSB| 最大 0.438391 @ D7B-CVG-P30-C255/normal，全部 ≤0.5；
   非 N1 末 100 ns 最大 20.60 nA < 150 nA；Ical=14.93190564 uA；5/5 收敛对 CONVERGED；
   N1=+256 LSB 且判 EXPECTED_REFUSAL；结论只到单窗净电荷，不扩为光学位数或全程稳定)
HISTORICAL_BUDGET_STATUS=VIOLATED_NOT_RETROACTIVELY_AUTHORISED
```
