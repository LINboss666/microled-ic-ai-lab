# DATA-7C-A-R2 修补报告（离线，纯文本/图/合成算术；2026-10-23，停在独立复审闸）

任务书：`reports/tasks/DATA-7C-A-R2.md`（`C:\Users\LMX\Downloads\TASK_DATA7C_A_R2.md` 的逐字节副本，
摘要 `dcd29c277cc66ab01bbff28a45bf428d03aa6282c90e78686a268f6c09c228d4`，由字节比较确认相等）。
审核包：`MicroLED_DATA7C_A_R1_Independent_Review_20261023.zip`，80,010 B，
SHA-256 `ff5f45b6ca19c2f376b8954ea9e9e8f24a48bc3e979572df5f22e9faa01e2f86`，41 members，
`REVIEW_RECOMMENDATION=REWORK`。**这两个数字只写在包外**：本轮交付物里不声明本轮归档自身的摘要。

## 0 身份、边界与本轮实际做的事

| 项 | 值 | 怎么核 |
|---|---|---|
| 仓库 | `https://github.com/LINboss666/microled-ic-ai-lab` | 推送后两条通道各自回读 |
| 新基线 H（本轮起点） | `da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb`，tree `913c8a343aa3debede5e46bc52cae3d7d978940d`，父 `cb99d33` | `git rev-parse`/`git cat-file commit` |
| 被审 tip T（R1 前一手） | `89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79` | 同上 |
| 首轮基线 B | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` | 同上 |
| 本轮分支 | `poc/data-pam-d7c-a-r2`；R1 分支 `poc/data-pam-d7c-a-r1` 保持指向 H，不移动 | 回读输出 |
| 接受版 | DATA-7A `f684496…`、DATA-7B `f9fd09b…`、main `23e471c…` 全部原样未动 | 回读输出 |
| 逐字限制 | `NEW_SPECTRE_LAUNCH_LIMIT=0`、`NEW_RTL_SIMULATION_LIMIT=0`、`NEW_OA_WRITE_LIMIT=0`、`SSH_OR_VM_ACCESS_AUTHORISED=NO`、`NATIVE_PREFLIGHT_AUTHORISED=NO`、`NEXT_NATIVE_STAGE_AUTHORISED=NO`、`MERGE_OR_MAIN_PUSH_AUTHORISED=NO`、`ACCEPTANCE_REGISTRATION_AUTHORISED=NO` | 记录 `verification_summary.json` 的 `native_launches/rtl_simulations/oa_writes` 三值为 0 |
| 未做 | 未运行 Spectre（含 `-h`）、未跑 ngspice/Xyce/Icarus/Virtuoso/OA、未做动态 preflight、未重跑旧波形、未读凭据/PDK/模型卡、未改密码 licence 网络、未 GC、未重写历史、未 force、未跳 hooks | 本轮全部命令只调用 `python` 与 `git` 读操作 |
| 仍然在册的旧事件 | R1 期间一次提交用了 `-c core.hooksPath=` 跳过 `pre-commit`，已 `reset --soft` 重做并披露；孤立对象 `6416882` 保留未删 | R1 报告 §0.7/§6.7 与交接 `boundaries.hooks_skipped`；本轮不重写历史，所以该事件不消失 |

## 1 先复现，再动手（任务书 §3）

审核方仪器按原附件保存，一字节未改，摘要登记在交接 JSON：
`reviewer/probe_r1_remaining.py` = `c23ec4ff687033e12de11d0e324333d7d91ed6e4d97fb1f340ff542732b14658`，
`reviewer/probe_review_gaps.py` = `b65b0ca1bdd807e83f514294c3499ab7ab6a9ea20a1aac5b088365ca82d5658e`。

| 运行 | 对象 | baseline_checks | 逐例结果 | 结论 |
|---|---|---|---|---|
| `probe_r1_remaining.py` | H 的 `git archive` 只读提取 | 30 | 七个缺口 `reproduced=true` 全中，`all_gaps_reproduced=true`，rc=0 | 复现成立；`rc=0` 只代表"七个都还在"，不代表验收 |
| `probe_review_gaps.py` | T 的只读提取 | 22 | 八例全复现，`all_defects_reproduced=true` | R1 之前的老缺口在 T 上确实存在 |
| `probe_review_gaps.py` | H 的只读提取 | 30 | `all_defects_reproduced=false` | R1 关掉了八例中的七例；未关的那例见 §4 |

本轮修复后，同一件未修改仪器对交付字节的逐例结果见 §9 的 `R2 INSTRUMENT` 表（由记录渲染，不手填）。
每个问题的修补尝试次数上限 3 次；本轮实际尝试次数记在 §2–§6 各节末尾。

## 2 F1：顶层供电绑定进入功能判定（§4）

根因：R1 的 `Xdec` 供电端子只被"端口数对得上"检查过，逻辑求值把理想轨道直接交给译码器，所以
`vdd18` 端子接到 `vss` 时图仍"正确地"算出温度计码。

改法：新增闸 `TOP_SUPPLY_BINDINGS`（`scripts/dd1_d7c_a_offline_check.py:554` 一带），先取顶层方向为
`inputOutput` 的轨道集合（必须恰为 `vdd18`/`vss`），再逐个实例把 (master 端口 → 顶层网) 配对核两件事：
声明为轨道的端子必须落在**同名**顶层轨道上；每个实例至少有一个端子落在地标轨道上。16 种正常组合的
求值仍然从真实顶层映射取输入，不再假设。

正例：交付字节上 10 个顶层实例全部通过，闸 PASS。
反例（`scripts/dd1_d7c_a_guards.py` 注入，只改临时副本）：
`E25` 供电短到 vss、`E26` 两端子对调、`E27` 支路脱离地标、`E28` 轨道被逻辑网驱动，四例各自具名失败。
`E27` 的期望集合在 R2 变大：同一条断链现在除了 `TOP_SUPPLY_BINDINGS`，还会让
`UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE`、`MAIN_PATH_DATA_OUT_CAS_MOUT_VSS`、
`BLEED_GATED_BY_BRANCH_COMPLEMENT` 一起拒收——这正是审核方要的"顶层网必须真的进到连通性判定"。
DUT 源网表零改动（四个候选文件在 `H..tip` 上 blob 相同，见 §9 `R2 FROZEN` 表）；没有引入通用 SPICE 仿真器。
本问题尝试次数：1。

## 3 F2：四张输入表按声明模式在真实读取路径上校验（§5）

根因：`read_table()` 只看形状；破损的黄金行/声明行在别的循环里才撞上 `int()`，抛出未处理异常，
而 header-only 的空表被读成"零不匹配＝通过"。

改法：新增 `strict_int()`、`strict_read()`、`input_specs()`、`input_schema_checks()`，
在 `run_checks()` 起始处一次性按声明模式读四张表，产出新闸 `INPUT_TABLE_SCHEMAS` 与 15 列计划表模式；
`GOLDEN_TABLE_SCHEMA`/`THERMO_GOLDEN_16`/`TOP_INTEGRATED_THERMO_16`/`CLAIM_TABLE_MATCHES_PARSE`/
`REQUEST_TABLE_SCHEMA`/`NATIVE_PLAN_SHAPE` 全部改为消费严格行，模式失配时写"未求值"而不去猜。
校验面：逐字节表头相等、逐行宽度（多出来的单元格也算）、必填非空、整数域（有限、非负、允许集合）、
唯一键、声明对象键集合（缺与多都拒）、mask 与 `en0..en7` 一致、8 个 DC 例与码 `000..111` 双向对应、
细化配对为固定契约。失败消息带表名/行号/列名/实际值，不再有 traceback。

被冻的表保持原字节：`pam_mask_golden.csv`、`pam_request_refusal.csv` 在 `H..tip` 上未改。
其中两行的自由文本 `note` 里有未加引号的逗号，严格读法按声明的"末列自由文本回接"处理，并把哪几行
被放宽写进闸文本（`REQUEST_TABLE_SCHEMA`），不是静默容忍。
反例：`E29`（黄金行多一格）、`E30`（`en0=NaN`）、`E31`（声明表只剩表头）、`E32`（重复键）、
`E33`（契约外对象键）、`E34`（ invented 拒绝码）、`E35`（八个 DC 全改 000）、`E38`（单行额度改动），
逐一具名命中。`E34` 的期望集合去掉了 `INPUT_TABLE_SCHEMAS` 并写明理由：该层声明的范围是表头、宽度、
必填、唯一键、契约键集合与整数域，"码字必须属于闭集"是请求契约，由 `REQUEST_TABLE_SCHEMA` 拥有并点名
`R05` 与该值。
本问题尝试次数：2（第一次是 CSV 机械改动被 naive `split(',')` 破坏，改为 `csv.reader`/`csv.writer`）。

## 4 F3：发布记录的语义层与发布后只读入口（§6）

根因：R1 的复核器只做形状/摘要自洽，所以一条 `rc=99` 配 `PASS`、缺一条必经门、未知状态词、
摘要过期、子结果 FAIL 而汇总 PASS 都能混过去；R1 报告自己在 §8.1 承认有三个文件是记录之后改的，
但没有任何机器去看这件事。

改法：新增 `scripts/dd1_d7c_a_r2_record_check.py`（必经门集合、状态枚举、rc 与期望关系、
`INFORMATIONAL_NOT_PASS` 必须在期望里写明 INFORMATIONAL、冻结行的 `enforced` 必须与 `expectation`
一致且违例求和为 0、身份路径/字节/摘要/Git blob、子结果 JSON 与汇总互核）；
`scripts/dd1_d7c_a_verify.py` 在**写盘之前**用同一套规则判即将发布的行（`record_semantics` 门），
在**发布之后**再对磁盘字节跑一次（`published_record_recheck`），任何一条不过就把总结论判 FAIL。
通用 `read_table()` 按任务书保持形状专用。

负例：`dd1_d7c_a_r2_record_probes.py` 的 14 条改写全部要求指定短语拒收（`R1` rc99/PASS、`R2` 缺必经门、
`R3` 生造状态词、`R4` 汇总洗白、`R5` 过期摘要、`R6` 路径不存在、`R7` enforced 违例、`R8` 反例未命中却标 HIT、
`R9` 空期望集合、`R10` selftest NOT_RUN 被当 PASS、`R11` 门文本自相矛盾、`R12` 诊断未改字节、
`R13` 合成符号用例未标 `SYNTHETIC_NOT_MEASURED`）。正例 `R0` 确认完好夹具被接受。

对**已发布的 R1 记录**跑新入口（`git archive H` 只读提取里跑，避免把本轮改动误当 R1 的问题）：
`D7C_A_R2_RECORD_CHECK: FAIL (frozen_rows=24, gates=14, git_checks=2, identity_rows=37, 9 semantic
problems)`，九个问题全部落在 R1 自己披露过的三个文件上——
`reports/dd1_d7c_a_review_fix_r1.md`、`reports/agent_handoffs/DATA-7C-A.md`、
`reports/agent_handoffs/DATA-7C-A.json`，每文件各三条（字节数、磁盘摘要、H 上的 Git blob）。
本轮记录把这条判断做成门 `previous_record_reader_finds_its_own_staleness`：期望是"落在三个已披露路径
之外的违例数 = 0 且问题非空"，`rc` 就是违例数，不是聚合成功率。
诚实的限制：R1 报告 §8.1 的说法本身是对的（它承认了改动），缺陷是"记录无法自证"；本轮不改写 R1 记录，
旧目录一个字节没动（§9 `previous_round_record_dirs` 行）。
本问题尝试次数：3（含一次把 `--source-root` 加进读表器，否则对 R1 的审计会被本轮工作副本污染）。

## 5 F4：探针符号、时序算术与草案清理（§7）

符号：deck 现为 `Ip_branch (clamp_node data_out) iprobe`，串联回路的物理正方向是
`clamp_node → data_out → 支路 → vss`，因此 `I_sink = Ip_branch`，**不取负、不取 abs()**；
关断尾窗单独积负面积，不与正面积相消。口径在运行前写死：deck 注释、机读表 15 行的
`probe_orientation`/`sign_convention` 两列、以及 `scripts/dd1_d7c_a_r2_plan.py` 的常量是同一条声明，
新闸 `DECK_PROBE_ORIENTATION_MATCHES_PLAN` 从 deck 与顶层网表反推 clamp/DUT 输出节点后互核，
`E39` 把探针转回去必须具名失败。合成算术由 `scripts/dd1_d7c_a_r2_sign_check.py` 的 7 例核：
正读＝原样、反向取负、负面积保留、KCL 逐码等于导通支路数 × 1875 fA（`ESTIMATED_MIRROR_RATIO_ONLY`）、
零窗口不算测量、第三种端序直接拒收。所有样点是手写的整数 fA × ns（电荷单位 1e-24 C，精确整数），
每例带 `evidence_class=SYNTHETIC_NOT_MEASURED`，**没有任何一条是测量结果**。

算术：TR-LONG 的平台 1.0 TON、关态 0.5 TON、节距 1.5 TON、八段止于 11.5 TON 只写在
`dd1_d7c_a_r2_plan.py` 一处；`validate_schedule()` 先查八码覆盖、窗口互不重叠、间隔与声明相等、
短脉冲平台落在平直段内、细化配对 15 个字段相同且只差 `maxstep`、DC 码双向对应，
`PLAN_SCHEDULE_ARITHMETIC` 通过后才由同一来源渲染 CSV 行，报告与 bench 文本再引用同一常量。
H 上"正文说 0.5、窗口实为 1.5 TON 节距"的矛盾不可能再出现，因为两处不再各写各的。
`RS-FULL` 现在复制 TR-LONG 码 111 段之前的**全部**七段平台与分段，只有 `maxstep_ns` 不同。
15 例 = 8 DC + 4 瞬态 + 3 细化，全部 `result=NOT_RUN`；30/36 只是草案额度，不是授权。
旧的"EIGHTEEN"与"瞬态只换三位 PAM 码"的开场白已清除。
本问题尝试次数：2（一次是 `RS-FULL` 覆盖了 `failure_condition` 破坏配对同一性，去掉覆盖）。

## 6 D1：空白与明示勘误（§8）

`git diff --check 89b3dd8..da6f5fc` 与 `git diff --check 272d6de..da6f5fc` 都在 2026-10-23T13:09:28Z
返回 rc=2，且唯一位置是 `reports/dd1_d7c_a_review_fix_r1.md:443: new blank line at EOF`。
本轮只删文末换行，R1 正文一字未改；同一检查在 `H..本轮 tip` 上 rc=0（记录的 `git_checks.csv` 三行）。
R1 报告新增 §9 勘误表：登记两个区间的命令、返回码、时刻，以及"区间一律写全两端 SHA、时刻一律带 `Z`"
的后续口径。历史事实保留，包括被废掉的两个包的身份与跳过 hooks 的事件。

## 7 计数与回归

| 套件 | 本轮交付字节上的实测 | 与 R1 的关系 |
|---|---|---|
| 离线检查 | `D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none)` | R1 的 30 项全部保留，新增 4 项（`TOP_SUPPLY_BINDINGS`、`INPUT_TABLE_SCHEMAS`、`PLAN_SCHEDULE_ARITHMETIC`、`DECK_PROBE_ORIENTATION_MATCHES_PLAN`），计数由 JSON 行数解析而非自述 |
| 反例族 | `D7C_A_GUARDS: PASS (65/65 named exactly; not hit: none)` | 39 注入 + 14 记录语义 + 5 CSV 往返 + 7 合成符号；R1 的 29 条逐条仍在，期望集合变动的七条各带书面理由（§2–§5） |
| 验收工具自测 | `D7C_A_R1_SELFTEST: PASS (9 cases, failures: none)` | 自测脚本保持 H 字节；`NOT_RUN`/rc=2 情形仍与 9 项 PASS 分开计 |
| 计划表 | `PLAN_CHECK delivered_rows=15 schema_refusals=0 schedule_problems=0` | 由单一来源重渲染，逐行回读 |
| 合成符号 | `D7C_A_R2_SIGN: PASS (7 synthetic cases, failures: none)` | 新件，全部标注 SYNTHETIC |

**本轮仍开着的一例**：`published_record_reader_accepts_rc99_as_PASS` 在修复后的字节上仍报
`reproduced=true`。该诊断打的是通用形状读表器本身，任务书 §6 明确允许 `read_table()` 保持形状专用，
拒收改由新的语义入口承担（§4 的 14 条负例 + 对 R1 记录的 9 条真问题）。所以这一例不是被"绕开"，
而是本轮**有意不合**并已在 `REMAINING_OPEN_BY_DESIGN` 常量与闸文本里点名；其它六例若仍报 reproduced，
`reviewer_remaining_on_fixed_bytes` 门直接 FAIL。

## 8 安全与来源

凭据、license、PDK 路径、模型卡、原始 PSF/波形、`cds.lib`、库绝对路径一律未读、未入库；
共享工具与旧证据目录在 `H..tip` 上 diff 为零（`previous_round_record_dirs`、`tools_the_brief_freezes_this_round`）；
不删已发布中间件，新记录用新 run id；不 force、不跳 hooks、不 GC、不重写历史；
本轮不合并、不推 main、不做接受登记。`AGENTS.md` 与既有 provenance/safety/netlist_stats 工具按 H 字节保留。

## 9 机器写入的表（以下四张表由 `scripts/dd1_d7c_a_verify.py` 从记录渲染）

### 9.1 门与命令

<!-- BEGIN R2 GATES -->
<!-- END R2 GATES -->

### 9.2 验收工具自测逐例

<!-- BEGIN R2 SELFTEST -->
<!-- END R2 SELFTEST -->

### 9.3 审核方仪器逐例（T 与修复后字节）

<!-- BEGIN R2 INSTRUMENT -->
<!-- END R2 INSTRUMENT -->

### 9.4 三张对照表与冻结面

<!-- BEGIN R2 FROZEN -->
<!-- END R2 FROZEN -->

## 10 停止状态

```text
TASK_ID=DATA-7C-A-R2
BASELINE_UNDER_REPAIR=da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb
OFFLINE_CHECKS_PASS=34
COUNTEREXAMPLE_FAMILIES_PASS=65/65
RECORD_SEMANTIC_PROBES_PASS=14/14
TOOL_SELFTEST_CASES_PASS=9
SYNTHETIC_SIGN_CASES_PASS=7
NATIVE_PLAN_ROWS=15
PLAN_RESULTS=NOT_RUN
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
SSH_OR_VM_ACCESS_USED=NO
PDK_OR_MODEL_CARD_READ=NO
GIT_HISTORY_REWRITTEN=NO
FORCE_PUSH=NO
HOOKS_SKIPPED_THIS_ROUND=NO
PREVIOUS_ROUND_EVIDENCE_MODIFIED=NO
OPEN_ITEM=published_record_reader_accepts_rc99_as_PASS (declared by design, see section 7)
NEXT_NATIVE_STAGE_AUTHORISED=NO
MERGE_OR_MAIN_PUSH_AUTHORISED=NO
ACCEPTANCE_REGISTRATION_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
