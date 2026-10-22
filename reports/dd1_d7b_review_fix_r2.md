# DATA-7B-R2 返修报告：预算权威、时间测量与证据语义限定（2026-10-23）

任务书 `reports/tasks/DATA-7B-R2.md`（逐字节副本，SHA-256
`bb39b6d4c54d62ce…` 见 §8 回执，12,148 B）；审核意见 `REVIEW_DATA7B_R1.md` 判定 REWORK。

| 身份 | 值 |
|---|---|
| 本轮唯一基线 H（被审 R1 tip） | `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92` |
| 被修好的 R1 载荷 | `d13e251d2874a9a9942fa103ff7ead3c798b5b14` |
| 原 D7B 交付 T | `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50` |
| 开发基线 B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 被接受的 DATA-7A | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| main（未动） | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 分支 | `poc/data-pwm-d7b-r2`（本轮新建，工作树 `D:\ic617_d7b_r2`） |
| 交付证据 | 见 §6 机器段（包名、文件数、字节数由结果集写出，不手抄） |
| 外部成本 | 新增 Spectre 进程 **0**；新增 RTL 仿真 **0**；新增 OA 写入 **0**；只重新解析已交付的 17 份 VCD |

本报告不写自身摘要或大小；最终身份从固定 Git blob 与包外回执读。
§6 的表格由 `scripts/dd1_d7b_r2_result_set.py` 对发布包一次运行写出（`--embed`），
正文其余数字若与机器段冲突，以机器段为准。

## 0 本轮操作记录

1. 先在 H 的原字节上复现，再改代码。14 条探针全部 HIT，记录在
   `review/scratch/r2_reproduce.txt`（命令、原因、rc；含一次性 `python -` 内联复现的三条）。
   复现输出摘录见 §1/§2/§3 各表的 “在 H 上看到什么” 列。
2. 工作树从 H 新建，个人分支 `poc/data-pwm-d7b-r2`；未改动任何旧分支，未移动 `main`。
3. 账户：本轮把 R1 工作树的在途账本按字节复制到本工作树的 ignored 路径
   （`review/scratch/dd1_d7b_launch_account.csv`，SHA-256 与来源一致
   `963be40ae32c610a…`，209 行 = 59 CONFIRMED + 150 REFUSED_NO_LAUNCH），
   之后的每一次离线导出与守护测试都在同一账本上追加 `REFUSED_NO_LAUNCH` 说明行；
   **没有删除、重置或改写任何账本**，也未覆盖已发布目录。
   账本的这一增长是本机迭代的真实留痕：每次 `--remeasure` 暂存为 24 例各写一行“未启动进程”，
   `dd1_d7b_r1_guards.py` 的离线组也会写若干同类行。占额度的仍只有 59 条 CONFIRMED。
4. 冻结面：`results/evidence/dd1_d7b_r11_main` 与
   `results/evidence/dd1_d7b_r1_r20261022_123825_8e1294` 两个已发布目录逐字节未变
   （`git diff --name-only e97f02e -- <两目录>` 为空，见 §6 机器段）。
   本轮修改的工作树文件只有 4 个：三份主工具 `dd1_d7b_run.py`、`dd1_d7b_measure.py`、
   `dd1_d7b_evidence_check.py`，以及既有的离线辅助 `dd1_d7b_r1_gate_records.py`（增加
   `--evidence-base`，使回环测试能在本轮暂存包上重放）；新增 2 个 R2 脚本。
5. 未做：原生 preflight、`spectre -h`、任何重跑、OA/Virtuoso、PAM/LUT/阵列/版图/TCON、
   PDK/许可证/VM/凭据改动、GC、rewrite、force、跳 hooks、合并、改可见性。
   凭据事件仍未解除：本轮不改密码，也不以仓库扫描 PASS 宣称解除。
6. **发布后发现并修正的一个自检排序缺陷**（不影响包内字节，影响的是"检出"的证明力）：
   `dd1_d7b_r2_guards.py` 的 `newest_bundle()` 原写法在同时存在 R1 与 R2 包时会先回落到 R1 包，
   于是 C7（无样点支撑的 CAL 基线）等探针会在"旧包本来就失败"的检查上得到空洞的 HIT。
   包内 `gate_records.csv` 的 `r2_guards_closed` 行是用 `--bundle <暂存包>` 显式指定的，
   当时并非空洞检出；但为消除歧义，我在发布后改为"本轮包优先"并**对发布包重跑 14 条探针**：
   14/14 HIT，且每条只点名自己的检查（`review/scratch/r2_guards_on_published.txt`）。
   这条修正只改测试选择逻辑，未改判据、未改任何证据字节。

## 1 A 组：预算权威、账本耐久性与生产入口

| 缺陷 | 在 H 上看到什么 | 修法 | 现在的答案 |
|---|---|---|---|
| A1 复核器从被检查文件取授权 | 把 `launch_account.csv` 全部 `ceiling` 改成 60 后，`BUDGET_RESPECTED` 重新通过 | 判据常量固定 56；新增 `BUDGET_AUTHORITY_FIXED`：账户每一行 `ceiling`、`environment.json` 的 `ceiling`/`budget`、对账表 TOTAL 注记、以及 environment 里的账户计数都必须与固定 56 及账户行互相一致 | 伪 60 副本因未授权上限被点名拒收，同时 `BUDGET_RESPECTED` 仍按 56 判失败 |
| A2a 预留不占额度 | 56 上限的 55 行账上，第二次 `reserve` 被接受（`occupied` 仍是 55） | `REQUESTED` 自写入即计入 `occupied`；`counts()` 另报 `pending` | 第一次预留占到 56，第二次 `OverBudget` 拒；合成账内无真实调用 |
| A2b 种子历史只比 ID | 59 条历史 state 全改 `REFUSED_NO_LAUNCH` 后账户照常打开 | `SEED_FACTS` 逐字段绑定 `task_id/run_id/case_id/role/state/launch_evidence` | 改写被拒，原因点名是哪个字段、种子说什么、文件说什么 |
| A2c 崩溃恢复释放额度 | 恢复为 UNCERTAIN 的行仍占 55（价未退），但同一实例再预留两条都通过 | 保留恢复价 + 预留即占 | 恢复行占 55，第三条占到 56，第四条被拒 |
| A3a 先删再改名 | 替换失败后账户文件消失，只剩 `.tmp`；下一次读成空账 | 写 `.tmp` → fsync → `os.replace`；替换失败保留旧文件并抛错；载入时若盘上有 `.tmp` 残留先拒 | 注入 ENOSPC 后旧文件行数不减且错误上浮 |
| A3b 过期实例覆盖 | 两个实例同读一份账，后写的过期实例直接覆盖 | `AppendCSV` 记 `baseline_sha`，每次 `flush()` 先比盘上摘要；变了就拒 | 过期实例被拒，摘要对写在原因里 |
| A4 生产入口 | `--seed-from`／新账本／继承 `RUN=1` 可绕过 | `authorisation_problem()` 先按 `NEW_LAUNCH_GRANT<=0` 关闭原生入口，并指明本轮离线入口 | 任何环境组合下原生入口都返回拒绝；`--selftest` 第 11 项固定这一断言 |

算法性的 55/56 边界测试全部在隔离的合成账本（临时目录）上跑，不触碰正式产物。

## 2 B 组：时间测量与单位

| 缺陷 | 在 H 上看到什么 | 修法 | 现在的答案 |
|---|---|---|---|
| B1 deadline 左侧 | 审核手算反例（0/10/20 ns=1、30 ns=0.5、带宽 0.95–1.05、deadline 25 ns）被判 `SETTLED` | 把跨 deadline 的分段在 deadline 处切开并检查其左极限；曲线用样点连线裁切插值得到连续带内段；10 ns 与 ±5 % 判据不动；`longest_in_band_ps`（采样界定）与 `longest_in_band_interp_ps`（连续）分列 | 该例 `NOT_SETTLED_WITHIN_PULSE`，并把“离带于 21.0 ns、deadline 左极限 0.75”写进结果 |
| B2 互补相位 | `data_en` 下降沿处去找 `data_en_b` 的下降沿，短窗“碰巧”找到、长窗 `NOT_FOUND` | 按真实相位：`data_en` 升 ↔ `data_en_b` 降，`data_en` 降 ↔ `data_en_b` 升；未保存该节点时报 `NOT_SAVED` | `de_b_rise_50_ps` 落在 `data_en` 下降沿邻域；两路间隙 `de_and_de_b_edge_gap_ns`、`de_b_rise_gap_ns` 入表 |
| B3 20 mA 电流容差 | 复核器用 `max(0.02·阈值, 0.02)` A 认证约 15 µA 的穿越点 | 电流、电压各按 SI 阈值求**穿越时刻**，与声明值比时间；容差取列的显示精度 0.05 ps；边邻切片新增 `t_ps` 全精度时刻，切片只印 0.1 ps 时点名说明 | 把 23 条 `current_10pct_ns` 各移 5 ns 立即被 `EDGES_BRACKETED_BY_SAMPLES` 点名 |
| B4 采样时刻冒充连续阈值 | 表里 `off_ns=3968.0376`（首个合格样点）与连续穿越 `3967.86874` 被当同一精度 | 新增 `off_interp_ns`（相邻样点求阈）并保留 `off_ns`；`OFF_TIMES_RECOMPUTED` 额外要求 `off_ns` 必须是真实交付样点时刻 | P30-C001：`off_ns=3968.0376`、`off_interp_ns=3967.8687`，与审核独立算法一致 |
| B5 收敛表只算一个布尔 | 表里 `delta_edge_ns=9999` 仍写 `CONVERGED` | 逐列重算 delta 与限值（新增 `limit_edge_ns`），配对/判决按 dQ、dPeak、dEdge 三项合成；被比较的物理量写明是 `data_en` 的 50 % 下降沿 | 该篡改触发 `CONVERGENCE_RECOMPUTED` |

## 3 C 组：VCD、CAL 片段与语义破坏检出

| 缺陷 | 在 H 上看到什么 | 修法 | 现在的答案 |
|---|---|---|---|
| C1 只查摘要 | `rtl_reverify` 的 AGREE、日期、字段数都通过，但没人重读四态字节 | 复核器用冻结的 `dd1_d7b_trace` 重读交付的 17 份 `.vcd.txt`，把窗口 t0/t1、脉冲段、`segments_ps` 与 `pwl_edges_<case>.csv`、`rtl_reverify.csv`、各 case 行逐条绑定；`shift_ns`/`tail_ns`/golden 表随包交付并由摘要绑定 | `RTL_VCD_SEMANTICS_REPARSED` 通过：17/17 重解析、26 个窗口绑定一致 |
| C2 翻转一条跳变 | 冻结解析器会拒绝该字节（互补/脉冲数不符），复核器仍放行 | 上条的重解析即入口；篡改侧同时更新两侧摘要与 manifest，使哈希一致 | 只靠语义检出的破坏被点名（见 §4 反例表） |
| C3 CAL 缺基线/尾段 | 只有 2950.389–3749.889 ns 的带内片段；`if off`/`if tail` 跳过空集后仍写“全部已重算” | 从摘要一致的原 raw 只读导出 `1500–1900`、`4400–4500` 两段（含两侧边界样点）入包，`calibration.csv` 记数量、范围、原 raw 摘要、切片系列名、section/temp；积分按声明窗口边界插值、以实际覆盖范围为分母，覆盖不足时钳到样本真实终点并把两个跨度都写出；缺失时给 `BLOCKED_MISSING_CAL_OFF`/`_TAIL` | OFF 基线 800 样点、尾段 200 样点交付，`CALIBRATION_OFF_BASELINE_SAMPLES` 通过；把基线改成 100 nA 被点名 |
| C4 均值冒充完整 500 ns | 用内部样点跨度 499.5 ns 作分母 | 分母是窗口实际积分跨度；`band_samples` 记内部样点数 | Ical = `1.4931905642814956e-05` A，内部 1000 样点、跨度 500 ns 全部入表 |
| C5 反例面 | R1 的 8 类破坏仍被检出，但 7 类新语义破坏无人接 | `dd1_d7b_evidence_check.py --selftest` 收 8+7 类；每例重新封存 manifest 后仍须点出对应新失败 | 见下表：15/15 各自点名 |

七类新语义破坏（`review/scratch/r2_gaterec*/gate_records.csv` 也在包内重放）：

| 破坏 | 必须点名的检查 |
|---|---|
| 账户上限改 60 | `BUDGET_AUTHORITY_FIXED` |
| `off_ns` 置 0 | `OFF_TIMES_RECOMPUTED` |
| 电流 10 % 穿越点移 5 ns | `EDGES_BRACKETED_BY_SAMPLES` |
| 互补节点时刻置 0 | `EDGES_BRACKETED_BY_SAMPLES` |
| `delta_edge_ns` 置 9999 | `CONVERGENCE_RECOMPUTED` |
| 交付 VCD 跳变翻转（含两侧摘要伪造） | `RTL_VCD_SEMANTICS_REPARSED` |
| 无样点支撑的 CAL 基线值 | `CALIBRATION_OFF_BASELINE_SAMPLES` |

## 4 定义变更披露（不得当作“原证据全错”）

- 连续带内段改为“含 deadline 左极限”的插值定义。**已交付 26 个电流窗口的 `settled_status`
  在新旧定义下完全相同**（R1 包已把这批窗口记为 `NOT_SETTLED_WITHIN_PULSE`，23 条非 N1 窗口
  最长带内段不足 10 ns），故本轮没有任何电气结论被移动；变更只让“最后一个带内样点延伸到
  截止点”这类侥幸不再可能判成 `SETTLED`。
- `off_ns` 仍是首个合格采样时刻，逐条不变；新增的 `off_interp_ns` 是同一事件的连续阈值读数，
  两列并列而非替换。
- 用新复核器读**旧 R1 包**会额外报出 `EDGES_BRACKETED_BY_SAMPLES`（旧边邻切片只印 0.1 ps）与
  `CALIBRATION_OFF_BASELINE_SAMPLES`（旧包未交付两段 CAL 片段）。这是定义与精度升级的滞后，
  不是把旧包的全部语义判为错误；旧包按 `dd1_d7b_review_fix_r1.md` 的记录仍是“除已披露预算
  违规外 39 项一致”。本轮的正面结论只对本轮包成立。
- 旧包报告里 13 与 14 项失败数的差异（`dd1_d7b_review_fix_r1.md` §6.5 之后的一次工具改动）
  在 `dd1_d7b_contract.md` 的勘误里已点名，本轮不重述结论，只保留出处。

## 5 事实记录更正

| 项 | H 上的错处 | 本轮事实 |
|---|---|---|
| 账户规模 | 报告写 134 / 75 | 以 §6 机器段引用的本轮账本为准（59 CONFIRMED + N 条 REFUSED_NO_LAUNCH，占额度只看 CONFIRMED） |
| 改动面 | 容易读成“改了 7 份文件” | 修改的主工具 3 份 + 修改的既有离线辅助 1 份；从 T 到 H 的 Git tracked 变化为 7 条路径（审核独立算出），本轮不与之混写 |
| 电流序列 | `new_in_r1=27` 读起来像 27 条全新采样 | 26 条与接受包逐字节相同、`charge_D7B-CAL_cal` 为 R1 新增；本轮再新增 `cal_off`、`cal_tail` 两段切片，另有 26 条边邻切片因加 `t_ps` 而重算 |
| 中间目录 | 曾删 4 个 | 事实保留、不伪称可原样重建；本轮零删除 |
| 凭据事件 | — | 未解除；本轮未改密码，未以扫描 PASS 宣称解除 |

## 6 机器生成段：本轮结果集

<!-- BEGIN R2 RESULT SET -->
| 项 | 本轮值 |
|---|---|
| 包目录 | `results/evidence/dd1_d7b_r2_r20261022_160652_e880be` |
| run_id / mode | `r20261022_160652_e880be` / `remeasure` |
| 本轮基线 H | `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92` |
| 文件数 / 字节数 | 287 / 21323343 B（上限 33,554,432 B） |
| 复核项 | 43 项，PASS 42，FAIL 1 |
| 失败清单 | `BUDGET_RESPECTED` |
| 账户行数 / 组成 | 333 行：CONFIRMED=59 / REFUSED_NO_LAUNCH=274 |
| 占额度 / 固定授权 / 超 | 59 / 56（任务书 52 + 追加 4）/ +3 历史超支 |
| 本轮新增成本 | Spectre 0；RTL 仿真 0；OA 写入 0；追加授权额度 0 |
| case 行 / 判决 | 27 行：EXPECTED_REFUSAL=1 / PASS=26 |
| settled 分布 | MEASURED=1 / NOT_APPLICABLE_NO_CONDUCTING_EDGE=3 / NOT_SETTLED_WITHIN_PULSE=23 |
| off 分布 | NEVER_WITHIN_LIMIT=1 / OFF=26 |
| Ical | 1.493190564e-05 A（内部样点 1000，切片 `charge_D7B-CAL_cal`） |
| CAL 两段切片 | OFF 800 样点 `charge_D7B-CAL_cal_off`；尾段 200 样点 `charge_D7B-CAL_cal_tail` |
| |电荷误差| 最大 | 0.438391 LSB |
| 交付四态字节 | 17 份 VCD，823372 B（LF 交付字节，CRLF 摘要另表） |
| gate_records | 6 行（全部 PASS 才允许入包） |

切片系列共 55 条（索引行 158 条，一条系列可分多个切片文件），按种类分列它与接受包的逐字节关系；不用一个 `new_in_r1` 计数混指两类含义：

| 系列种类 | 与接受包的关系 |
|---|---|
| `charge_*` | IDENTICAL_BYTES=26 / NEW_IN_R1_NOT_IN_ACCEPTED_BUNDLE=3 |
| `edge_*` | NEW_IN_R1_NOT_IN_ACCEPTED_BUNDLE=26 |

本轮三份主工具的 SHA-256（包内 `environment.json` 记录的是导出时的同一摘要）：

| 工具 | SHA-256 |
|---|---|
| `dd1_d7b_run.py` | `dea050a5685eded854502f85c45f8f356acb006e5c421fd084513da5d39b70bc` |
| `dd1_d7b_measure.py` | `f3da5b53d5c777ec7f60c159fbf4b8840f6257019045146546e1e0a7793fbb7f` |
| `dd1_d7b_evidence_check.py` | `92a2d34db1526c2715e4cc616dc865a8e0691a625a89bcf9f52ffa48a676658e` |

包内 `environment.json` 记录的导出源码身份：measure `f3da5b53d5c777ec7f60c159fbf4b8840f6257019045146546e1e0a7793fbb7f`，evidence_check `92a2d34db1526c2715e4cc616dc865a8e0691a625a89bcf9f52ffa48a676658e`。

包内 gate 记录：

| gate | 判决 | rc | 命令 |
|---|---|---|---|
| `measure_selftest` | PASS | 0 | `scripts/dd1_d7b_measure.py --selftest` |
| `run_entry_selftest` | PASS | 0 | `scripts/dd1_d7b_run.py --selftest` |
| `trace_selftest` | PASS | 0 | `scripts/dd1_d7b_trace.py --selftest` |
| `evidence_tamper_selftest` | PASS | 0 | `scripts/dd1_d7b_evidence_check.py --selftest review/scratch/r2_stage_A/evidence/r20261022_160325_bd717c` |
| `execution_guards` | PASS | 0 | `scripts/dd1_d7b_r1_guards.py` |
| `r2_guards_closed` | PASS | 0 | `scripts/dd1_d7b_r2_guards.py --phase fixed --bundle review/scratch/r2_stage_A/evidence/r20261022_160325_bd717c` |
<!-- END R2 RESULT SET -->

## 6.5 发布后对发布包本身的重放（真实命令与结果）

| 命令 | rc | 结果 |
|---|---:|---|
| `python scripts/dd1_d7b_evidence_check.py results/evidence/dd1_d7b_r2_r20261022_160652_e880be` | 1 | 43 项，唯一失败 `BUDGET_RESPECTED`；manifest 覆盖 286 条 / 21,264,382 B，无自引用条目 |
| `python scripts/dd1_d7b_evidence_check.py --selftest results/evidence/dd1_d7b_r2_r20261022_160652_e880be` | 0 | `D7B_EVIDENCE_SELFTEST: PASS (15 counterfeits, 0 problem(s))`，8 类旧破坏 + 7 类新破坏各自点名 |
| `python scripts/dd1_d7b_r2_guards.py --phase fixed` | 0 | 14/14 HIT，base 为发布包；每条只点名对应检查（见 §0.6） |
| `python scripts/dd1_d7b_r1_guards.py` | 0 | `D7B_R1_GUARDS: PASS (8 groups, 0 problem(s))`（R1 的 8 类测试在当前字节上仍成立） |
| `python scripts/dd1_d7b_measure.py --selftest` | 0 | `PASS (24/24)`，含 §2 的手算反例 T6d 与 T8b |
| `python scripts/dd1_d7b_run.py --selftest` | 0 | `PASS (13 checks)`，含常量一致性与"原生入口在任何环境下都拒" |
| `python scripts/dd1_d7b_trace.py --selftest` | 0 | `D7B_TRACE_SELFTEST: PASS`（冻结解析器未改） |
| `python scripts/dd1_d7b_r2_result_set.py <发布包> --out review/scratch/r2_result_set.json --embed reports/dd1_d7b_review_fix_r2.md` | 0 | `D7B_R2_RESULT_SET: PASS (43 checks, 1 failure(s): BUDGET_RESPECTED)` |
| `python scripts/precommit_safety_check.py` | 0 | `SAFETY_GATE: PASS`，四类计数均为 0（staged 模式，0 对象） |
| `python scripts/provenance_check.py` | 0 | `SOURCE_PROVENANCE_CHECK: PASS`（files=430 labelled_lines=541 violations=0） |

冻结核对（同一条命令在发布前后各跑一次，结果一致）：

```text
git diff --name-only e97f02e -- results/evidence/dd1_d7b_r11_main \
                          results/evidence/dd1_d7b_r1_r20261022_123825_8e1294     # 空
git diff --name-status e97f02e -- .                                               # 5 个 M
    M scripts/dd1_d7b_run.py / dd1_d7b_measure.py / dd1_d7b_evidence_check.py
      / dd1_d7b_r1_gate_records.py（§2 允许修改的三份主工具与一份既有离线辅助）
      M reports/dd1_d7b_contract.md（§16 勘误，§2 允许的文档勘误）
新增只有 scripts/dd1_d7b_r2_guards.py、scripts/dd1_d7b_r2_result_set.py、
reports/dd1_d7b_review_fix_r2.md、reports/tasks/DATA-7B-R2.md 与
results/evidence/dd1_d7b_r2_r20261022_160652_e880be/；handoff 两份在下面 D 提交里更新。
```

## 7 未解与限制

1. `BUDGET_RESPECTED` 仍为唯一持续失败的检查：历史 59 次对固定授权 56，超出 3 次；
   本轮新增 0，也不追溯授权，处置权在用户。
2. 本轮没有任何新的 Spectre/RTL 字节产生；17 份 VCD 与 26 条电流序列全部复用已授权运行的字节，
   `charge_*` 序列与接受包逐字节比对结果在 §6 机器段列出。
3. 边邻切片只交付跳变 ±4 个样点，故 `data_en_b` 的升沿在某些窗口需靠 `de_fall_50` 邻域切片
   回推；若该邻域不含 0.9 V 穿越，本轮记为 `NOT_FOUND` 而非补数。
4. `gate_records.csv` 记录的是发布前暂存字节上的重放（包内文件一旦新增，manifest 必然变化），
   发布后我又对本轮包重跑了同一套复核与反例；两边结果都在 §6 机器段与交接回执中分列。
5. 新证据总量仍低于 32 MiB 上限，未删任何旧证据腾空间。

## 8 回执

见 `reports/agent_handoffs/DATA-7B.md` / `.json`。本轮停在独立复审闸：
`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`，不合并、不授权下一阶段、不做 SOA 签核。
