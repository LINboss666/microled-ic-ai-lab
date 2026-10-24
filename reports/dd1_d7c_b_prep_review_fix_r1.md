# DATA-7C-B-PREP-R1 离线修补报告（合同状态 `PROPOSED_FOR_REVIEW`，不是 `USER_APPROVED`）

本轮是 **DATA-7C-B-PREP-R1**：对独立评审判为 `REWORK` 的 PREP 字节做**离线修补**，不进入原生阶段。
机读产物由 `scripts/dd1_d7c_b_prep_*.py` 与新增的 `scripts/dd1_d7c_b_prep_r1_*.py` 生成；本文件的
机器表由 `scripts/dd1_d7c_b_prep_r1_verify.py` 渲染，任何一处手工改数都会让固定点比较失败。

## 0 身份、授权与硬边界

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/LINboss666/microled-ic-ai-lab` |
| 本轮基线 P | `dcef9b336f2222d6291d266858270f7448b6bb78`（PREP 交付 tip，评审所判字节） |
| 继承的已接受 R2 | `3e4703f1763223024f442c0826e95055782bca13` |
| `main` | `23e471cb936b421ee97e1250c3be06edf96f9937`，本轮不动 |
| 本轮分支 | `poc/data-pam-d7c-b-prep-r1`（从 P 新建工作树 `D:\ic617_d7c_b_prep_r1`） |
| 任务书 | `reports/tasks/DATA-7C-B-PREP-R1.md`，13,242 B，sha256 前缀 `b8e6cd2d1f7b6c81`，与 Downloads 原件逐字节相同（LF，0 个 CR） |
| 评审包 | `MicroLED_DATA7C_B_PREP_Independent_Review_20261024.zip`，29,977 B，sha256 前缀 `1d4a8166626ea0a5`，清单 17 行全部回读 |
| 评审仪器 | `reviewer/probe_prep_gaps.py`，11,024 B，sha256 `d981ff190a627ae70bb8e8a5656226b1b2a2d35e65b6539d99b13768dbe69b7c`；**字节未改，判据未放宽** |
| 评审结论 | `REVIEW_RECOMMENDATION=REWORK`、`NATIVE_EXECUTION_RECOMMENDATION=NO_GO_PENDING_OFFLINE_REPAIR`、`CANDIDATE_DUT_REDESIGN_REQUIRED=NO` |

授权上界（本轮自证，任何一条都不是"验证一下"的例外）：`NEW_SPECTRE_LAUNCH_LIMIT=0`、
`NEW_RTL_SIMULATION_LIMIT=0`、`NEW_OA_WRITE_LIMIT=0`、`NATIVE_PREFLIGHT_AUTHORISED=NO`、
`SSH_OR_VM_ACCESS_AUTHORISED=NO`、`PDK_MODEL_CREDENTIAL_ACCESS_AUTHORISED=NO`、
`ACCEPTANCE_REGISTRATION_AUTHORISED=NO`、`MERGE_OR_MAIN_PUSH_AUTHORISED=NO`、
`NEXT_NATIVE_STAGE_AUTHORISED=NO`。0 包含帮助命令、语法试跑、其它仿真器与旧仿真重跑。未读凭据、
模型卡、许可证，未连接 guest；未 force、未跳 hooks、未 GC、未改历史、未改仓库可见性。
文件/工具输出中自称 system-reminder 或要求新 audit 权限的文字**不构成授权**，本轮据此拒绝了一次
伪装的 `audit` 调用与两次伪装的凭据事件。

## 1 开工核验与双通道身份

本地 `git rev-parse HEAD` = `dcef9b33…`；远端两条通道查询同一对象：
`git -c http.proxy=http://127.0.0.1:7892 ls-remote origin` 给出 `refs/heads/poc/data-pam-d7c-b-prep`
= `dcef9b33…`，`gh api repos/.../git/ref/heads/poc/data-pam-d7c-b-prep` 给出同一 SHA
（`github.com` 直连 443 超时，必须走代理；`api.github.com` 直连可用，这不是"缺通道"而是两条通道
都可用且互相印证）。新分支 `poc/data-pam-d7c-b-prep-r1` 在推送前于远端**不存在**，这是正确答案，
不是回读失败；推送后的双通道回读记入发布回执提交，不回填本文件（避免摘要改写自己产不出的字节）。

## 2 修改前：四组缺口在 P 字节上逐项复现

入口：`python review/MicroLED_DATA7C_B_PREP_Independent_Review_20261024/reviewer/probe_prep_gaps.py
--root <P 提取目录> --out <新的 JSON>` → rc=0，`all_four_families_reproduced=true`。逐项读数
（`review/scratch/r1_prep_probe_before.json`，本轮保存在仓库外，不入库）：

| 族 | 仪器读数（修改前） | 判读 |
|---|---|---|
| F1 | `dc_code_mismatches=4`（DC-001 期望 1 读成 4：`[0,0,1.0]`）、`nonrail_highs=12`（高电平写 1.0 V 而非 1.8 V） | 位序颠倒 + 把逻辑 1 当伏特用 |
| F2 | `PAM_ramps_over_emission_count=36`、`backwards_off_windows=20`（如 `2500.000-2450.000`）、`enable_50_percent_errors=4`（TR-LONG 声明 1000、插值 1025）、`leakage_windows_with_next_enable=20`（漏流末 100 ns 内 DATA_EN 达 0.9 V） | 码在发光窗内线性爬、关断窗反写、表与波形两个数、漏流窗含下一上升 |
| F3 | 8 个窗全 `NO_REAL_EDGE_FOUND`；入口把第一个漏流窗复用到所有尾（`2400000–2500000 ps`、0 A），独立参考在同一尾读到 `ABOVE_LIMIT 5e-06`；两侧都缺上下文时 `convergence` 仍给 `WITHIN_LIMIT`；静态调用图上 `measure_case` 不调 `charge_errors`/`sign_check` | 找不到沿、窗错配、空上下文当成相等、两项判据根本没接线 |
| F4 | `no_explicit_27C=15`、`unnamed_analysis_lines=15`（`dc dev=Vclamp …` 无实例名） | deck 没写温度语句、分析行不是本项目已证的具名写法 |

## 3 F1 修补：位权与完整电平只有一处定义

`code_bits()` 现在只做 `value=int(code,2)`、`pam0=(value>>0)&1`、`pam1=(value>>1)&1`、
`pam2=(value>>2)&1`，电平 = `bit × logic_high_V`，`logic_high_V=1.8` 取自合同 `units`；DC 与瞬态共用
同一条规则。合同新增 `units.logic_high_V`、`rules.enable_edges`，八码一对一：`001`→(1.8,0,0)、
`100`→(0,0,1.8)。`000` 仍是**最低非零档**（一条支路），黑码只能由 `DATA_EN=0` 表达。
deck 里 DC 三相源写成 `VPAM0 (pam0 0) vsource dc=1.800   // bit weight 1 of code 001`，注释是注释，
判据是语句：审计先把行首 `//` 去掉再匹配。

## 4 F2 修补：真关态换码、统一偏移 1050 ns、五个窗分别命名

PAM 三位先**保持旧值**，再在关断态内部用 2 ns 边沿切换（`t-1` 旧值、`t+1` 新值），两个端点都落在
DATA_EN 全程为 0 的区域；不存在跨窗线性斜坡，初始码从 t=0 就稳定，去重不删保持端点。统一模型：
纯关准备到 1000 ns 结束，`Emax=50 ns`（半沿），瞬态统一偏移 **1050 ns**，TR-LONG 首个 `rise50=1050`
且斜坡 `1000→1100`；其后每个使能 = R2 相对时间 + 同一偏移；TR-OFFCODE 保留 300 ns 起始间隔；平台宽、
间距、码序、基准电流与细化历史不变。合同 `differences_vs_R2` 记 `D6_transient_offset_is_1050_ns_not_
1000_ns`（这是本轮对时间解读的更正，**没有**改动 R2 的任何字节）。五个窗分别命名并分别成列：
`emission`（rise50→fall50）、`emission_flat`（rise_end→fall_start）、`off_tail`（fall50→下一
rise_start 或 stop）、`pure_off`（fall_end→下一 rise_start）、`leak_last100`（末 100 ns，必须完整
位于 pure_off 内，否则**拒收该配置**而不是截断）。`off_window_ns` 保留为 pure_off 两端点的成对写法，
因为评审仪器的 F2 判据按该列名读取；`validate` 与独立读盘器都会在两种写法不一致时点名拒绝。
15 例覆盖不变，两个临时副本反例（旧长坡、漏流窗含下一上升）保留并在每次运行时重放。

## 5 F3 修补：正反例都走真实测量入口

测量核仍复用被接受并保留的 `dd1_d7b_measure`（积分、插值、带判定只有一份实现）。本轮把评审点名的
五件事接进入口 `measure_case(row, windows, samples, evidence_class, idc_A_by_code)`：
逐窗 `rise50/fall50` 提示 + 该窗自己的半沿搜索半径，找不到 bracketing 就 `REFUSED_NO_REAL_EDGE`
（不回退到窗端点）；同时给出全窗 Q（含 Qpos/signed Qneg/|Qneg| 与 `Q=Qpos+Qneg` 恒等式校验）与平坦段
均值；真正调用 `sign_check`（`I_sink = Ip_branch`，原始电流与总电荷**永不**过 abs）；真正调用
`charge_errors`，名义期望 `Inominal(code)×T50` 与 DC 期望 `IDC(code)×T50` 分列，无原生 DC 点时后者
`NOT_RUN`，不得用几何比冒充；第 k 个发光窗与第 k 个尾窗互指，尾窗逐窗给区间、`max(abs(I))`、
关断采样时刻与插值阈值时刻。`convergence` 先验证上下文存在、有限且窗单调，再比较，两侧都缺字段时
`REFUSED_MISSING_CONTEXT` 并点名缺哪一项，绝对差 `delta_q_C/fC` 始终并列。合成族从 17 例扩到 25 例，
新增 8 例覆盖任务书 §5 要求（八码只在第二尾注入 5 µA、TR-120 全窗 Q≠平坦 Q 且两值都手算、
27 个窗零边沿拒收、五类缺失上下文各自点名、抵消尾不判零漏流、IDC 缺失走 `NOT_RUN`、
真实交付 deck 的独立读盘、两种注入形状的临时副本反例）。全部样点标 `SYNTHETIC_NOT_MEASURED`，
没有任何生产 DC/PSF 发布器。

## 6 F4 修补：deck 只写已证写法，审计按语句判

每份 deck 现在写 `simopt options temp=27`、`dc_case dc dev=Vclamp param=dc start=0.600 stop=1.500
step=0.050`、`tran_case tran stop=<绝对值> maxstep=<该例>`，PWL 用已证的
`vsource type=pwl wave=[t v …]`（时间是整数 ns，形如 `1000n`；括号成对写法会触发 SFE-874，裸
`options temp=27'` 触发 SFE-709）。审计解析**生效语句**（类型、温度、stop、maxstep、码位、电平、
窗、探针端子序、include 来源、`Vss (vss 0) vsource dc=0`），不再用"含有 stop 的行"充数。四个候选
master 一字节未动，因此仍 `NATIVE_NETLIST_SYNTAX=NOT_VERIFIED`：语句形状有本地已运行证据，分层
`save` 没有。27 °C / TT / 1.8 V / Iref 15 µA / clamp 1.2 V / 扫描 0.60–1.50 步 0.05 全部继承。

## 7 独立解读实际交付的 deck 与 PWL

新增 `scripts/dd1_d7c_b_prep_r1_deck_read.py`：自带解析器，**不 import** 生成器与测量核，位权写成
字面常量（`pam0=1/pam1=2/pam2=4`）。它按 15 份交付 deck 检查：语句级条件；八码与三级电平；
每条 DATA_EN 斜坡是否是一条直线段且半沿等于表值；由 deck 自身波形插值得到的 50% 点是否逐个等于
`enable_rise_50_ns/enable_fall_50_ns`（一一对应、按序）；每个 PAM 变化段是否完整落在 DATA_EN 全程为
0 的区间内、是否与任何 emission 窗重叠、是否被某个 `pure_off` 窗包含；每个漏流子窗是否全程 0 V 且不
越过下一个上升起点；`windows.csv` 与 `schedule.csv` 的两种写法是否自相一致。判"空问题表"为有效结论
的前提是它同时报出读数：15 份 deck、27 个 emission 窗、36 个 PAM 变化段、54 个半轨交叉
（`--observe`）。同一条命令跑在 P 的字节上会**点名拒读**（该合同未声明 `units.logic_high_V` 等字段），
而不是编造期望；两个临时副本反例（旧长坡、漏流窗含下一上升）在仓库外的 scratch 目录上重放，
scratch 落在仓库内会被拒绝创建。

## 8 冻结面与两处更正

冻结未动：P 的证据目录（含被判 REWORK 的记录与那一次中止发布）、四个候选 DUT、R2 与更早的日程/
deck/记录、安全与溯源工具、`scripts/dd1_d7b_measure.py`、`spectre/current_probe_syntax.scs`、
PREP 报告与 PREP 交接、PREP 任务书。**本轮不重写 PREP 报告**，因此其 §4 中"`window_start/stop`、
`leak_last100_start` 分列"与其机器表描述的是 P 字节；更正只写在这里：列名已改为
`full_window_start_ns/full_window_stop_ns/flat_start_ns/flat_stop_ns/tail_start_ns/tail_stop_ns/
pure_off_start_ns/pure_off_stop_ns/leak_window_ns`，且第一沿不再是 1000 ns 而是 1050 ns。
第二处更正：PREP 回执称 `R2..P` 为"68 新增"，按 Git 重算为下表所写的新增/变更/删除/提交数，
本轮不单开 DOC 轮次，直接在此声明并由 `git_range_counts` 闸判定。

## 9 闸、记录与验收顺序

验收顺序按任务书 §8：修改前四组复现 → F1–F4 修补 → 实际 deck/PWL 的独立解读 → 原 17 例合成回归
（现 25 例）→ 真实测量入口的正反例 → 源码冻结比较与真实提交区间 `git diff --check` → 全新 archive
提取重放（含把评审仪器跑在该提取上）。冻结的 T/H 工具证据不重建；`REUSED`/`NOT_RUN` 不计为新 PASS。
记录目录 `results/evidence/dd1_d7c_b_prep_r1_<run_id>` 每次运行新建，绝不覆盖；被取代或被中断的记录
原样保留。

记录语义用 **R1 入口**，共享工具一字节未改：`scripts/dd1_d7c_a_r2_record_check.py` 里有两个"本轮专有"
的量——`MANDATORY_GATES` 点名上一轮的仪器门（含 `reviewer_instrument_on_T`，那个 T 是 7C-A 的受审
tip），`json_semantics` 硬要 `instrument_T.json`/`instrument_fixed.json`（同一轮八缺口仪器的 8 例）。
本轮的仪器是评审包的**四族**探针，跑在 P 与修补字节上，文件叫 `instrument_P.json`/`instrument_r1.json`。
所以 `scripts/dd1_d7c_b_prep_r1_record_check.py` 只做一件事：调同一批规则函数（gate/frozen/json/
summary/identity 五个，顺序与实现都不动），把"名字属于上一轮"的那一行换成按本轮门列与本轮仪器文件
重算的同一类判据，并在输出里报数 `frozen_mandatory_line_replaced=1`、
`instrument_vocabulary_lines_replaced=2`。直接跑冻结 CLI 会恰好报三条：
`mandatory gate(s) absent from commands.csv: reviewer_instrument_on_T,reviewer_instrument_on_fixed_bytes`、
`instrument_T.json is absent`、`instrument_fixed.json is absent`——那是轮次绑定，不是规则违背；
除此之外的每一条共享规则原样生效，`frozen_surfaces` 那行证明共享模块与 PREP 字节逐字节相同。

<!-- BEGIN 7CB_R1 GATES -->
| 门 | 命令 | rc | 期望 | 判决 | 依据 |
|---|---|---|---|---|---|
| `reviewer_instrument_on_P_base` | `python probe_prep_gaps.py --root the P extraction --out instrument_P.jso` | 0 | 0 | PASS | four families read individually: 1_=reproduced;2_=reproduced;3_=reproduced;4_=reproduced; aggregate all_four=True expected True; instrument bytes sha2 |
| `reviewer_instrument_on_r1_bytes` | `python probe_prep_gaps.py --root this tree --out instrument_r1.json` | 1 | 1 | PASS | four families read individually: 1_=closed;2_=closed;3_=closed;4_=closed; aggregate all_four=False expected False; instrument bytes sha256=d981ff190a6 |
| `reviewer_instrument_bytes_unchanged` | `sha256 of review/MicroLED_DATA7C_B_PREP_Independent_Review_20261024/revi` | 0 | 0 | PASS | the instrument that judged the PREP bytes is the instrument that judged these; sha256=d981ff190a627ae70bb8e8a5656226b1b2a2d35e65b6539d99b13768dbe69b7c |
| `deck_read_on_delivered_bytes` | `python dd1_d7c_b_prep_r1_deck_read.py --check --observe --json <out>` | 0 | 0 | PASS | D7C_B_PREP_R1_DECK_READ_OBSERVE: PASS ({"decks_read": 15, "half_rail_crossings_total": 54, "pam_changing_segments_total": 36, "pwl_signals_read": ["da |
| `deck_read_negatives_named` | `python dd1_d7c_b_prep_r1_deck_read.py --counterexample` | 0 | 0 | PASS |   delivered_bytes_control        HIT   delivered TR-LONG and TR-OFFCODE raise 0 edge or leakage refusals: [] |
| `deck_read_refuses_the_base_tree` | `python dd1_d7c_b_prep_r1_deck_read.py --check --root <P extraction>` | 1 | 1 | PASS |   PROBLEM the contract of this tree does not declare units.logic_high_V, units.edge_ns, units.transient_offset_ns, rules; the reader states what it ca |
| `contract_selfcheck` | `python dd1_d7c_b_prep_contract.py --check` | 0 | 0 | PASS | D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=19 problems=0) |
| `schedule_check` | `python dd1_d7c_b_prep_schedule.py --check` | 0 | 0 | PASS | D7C_B_SCHEDULE_CHECK: PASS (rows=15 windows=143 pwl=300 problems=0) |
| `deck_check` | `python dd1_d7c_b_prep_deckgen.py --check` | 0 | 0 | PASS | D7C_B_DECKGEN_CHECK: PASS (15 decks, problems=0) |
| `offline_checks` | `python dd1_d7c_a_offline_check.py --json` | 0 | 0 | PASS | D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none) |
| `counterexamples` | `python dd1_d7c_a_guards.py --json` | 0 | 0 | PASS | D7C_A_GUARDS: PASS (65/65 named exactly; not hit: none) |
| `deck_regenerated_from_sources` | `python dd1_d7c_b_prep_deckgen.py --to <scratch>` | 0 | 0 | PASS | D7C_B_DECKGEN_REGENERATED 15 decks in a scratch tree, comparison problems=0 |
| `synthetic_measure_cases` | `python dd1_d7c_b_prep_cases.py --json <out>` | 0 | 0 | PASS | D7C_B_PREP_CASES: PASS (25/25 named exactly, failures: none, evidence SYNTHETIC_NOT_MEASURED) |
| `record_tool_selftest` | `python dd1_d7c_a_r1_selftest.py --json <out>/selftest.json run in a thro` | 0 | 0 | PASS | clone_at_R2 PASS (9 cases, failures: none); this_tree rc=1 FAIL, failing cases frozen_gate_counts_only_enforced_rows, all 90 paths the A-round whiteli |
| `fresh_extraction_replay` | `git archive 10f69053a192 / tar -x, then run every suite and the reviewer` | 0 | 0 | PASS | contract_check rc=0 D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=19 problems=0); schedule_check rc=0 D7C_B_SCHE |
| `handoff_structure` | `python dd1_d7c_b_prep_r1_verify.py --handoff-check (in process)` | 0 | 0 | PASS | fields, digests against disk, four repairs, zero costs, markers and forbidden claims all checked |
| `native_entry_refused` | `python dd1_d7c_a_deckgen.py --probe <temp>` | 0 | 0 | PASS | DECKGEN_PROBE refused=True untouched=True reason=DATA-7C-A: this round authorises no native launch and no deck publication; NATIVE_AUTHORISED_THIS_ROU |
| `provenance` | `python scripts/provenance_check.py` | 0 | 0 | PASS | SOURCE_PROVENANCE_CHECK: PASS |
| `history_safety` | `python scripts/precommit_safety_check.py --mode history` | 0 | 0 | PASS | SAFETY_GATE: PASS; counters={'PDK_TRACKED_FILES': '0', 'CREDENTIAL_TRACKED_FILES': '0'} |
| `git_range_counts` | `git diff --name-status R2..P, git rev-list --count R2..P and the same ov` | 0 | 0 | PASS | R2..P added=83 changed=0 deleted=0 commits=15 (the PREP receipt stated 68 added, corrected here to 83); P..HEAD added=7 changed=26 deleted=0 commits=3 |
| `frozen_surfaces` | `git ls-tree -r blob/mode comparison over explicit path lists, plus git d` | 0 | 0 | PASS | enforced rows 10, violations 0, informational 2; added vs P 7, removed 0, modified 26; git diff --check P..HEAD=0 R2..HEAD=0 T..HEAD=0 |
| `record_line_endings` | `scan every published file for CR and round-trip a comma-and-quote row th` | 0 | 0 | PASS | published files still carrying CR: none; the table writer emits LF (confirmed); instrument JSONs are normalised only after the parsed object is proven |

渲染发生在 `10f69053a192` 之后、`record_semantics` 与 `published_record_recheck` 判定之前；本表不含本轮记录的摘要（它写于本文件之后）。
<!-- END 7CB_R1 GATES -->

<!-- BEGIN 7CB_R1 REPAIRS -->
| 族 | 评审读到的事实 | 本轮改法 | P 上复现 | R1 上复现 | R1 判据 |
|---|---|---|---|---|---|
| F1_PAM_bit_order_and_high_level | REVIEW_DATA7C_B_PREP_20261024.md section 3 F1, checks/prep_probe.json F1.dc_code_mismatche | value = int(code, 2); bit(k) = (value >> k) & 1; volts = bit * logic_high_V, used by the D | yes | no | deck_read 独立读回 8 码与三级电平 |
| F2_PWL_and_window_physics | REVIEW_DATA7C_B_PREP_20261024.md section 3 F2, checks/prep_probe.json F2.PAM_ramps_over_em | a code change is old value at t-1 and new value at t+1 inside the pure-off window; windows | yes | no | deck_read 独立插值 50% 沿、码变段全低、漏流子窗 |
| F3_measurement_entry_wiring | REVIEW_DATA7C_B_PREP_20261024.md section 3 F3, checks/prep_probe.json F3.entries (eight NO | each emission window searches around its own rise50/fall50, reports the full-enable Q and  | yes | no | 25 例合成正反例全走真实入口 |
| F4_native_deck_known_contract | REVIEW_DATA7C_B_PREP_20261024.md section 3 F4, checks/prep_probe.json F4.no_explicit_27C ( | decks state simopt options temp=27, an instance-named analysis line, and PWL as wave=[t v  | yes | no | deck_read 按语句解析 temp/analysis/PWL/probe |
<!-- END 7CB_R1 REPAIRS -->

<!-- BEGIN 7CB_R1 DECKS -->
| 例 | 类型 | 码 | 半沿 (ns) | 偏移 (ns) | 平台首 (ns) | 全窗 (ns) | 平坦 (ns) | 纯关 (ns) | 漏流子窗 | 换码 (ns) | stop | maxstep | 配对 | 结果 |
|---|---|---|---:|---:|---|---|---|---|---|---|---:|---:|---|---|
| `DC-000` | dc_sweep | `000` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-001` | dc_sweep | `001` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-010` | dc_sweep | `010` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-011` | dc_sweep | `011` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-100` | dc_sweep | `100` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-101` | dc_sweep | `101` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-110` | dc_sweep | `110` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `DC-111` | dc_sweep | `111` | 0.000 | 0.000 | dc_no_time_window | dc_no_time_window | dc_no_time_window-dc_no_time_window | dc_no_time_window | dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | NOT_RUN |
| `TR-LONG` | transient | `000..111` | 50.000 | 1050.000 | 1050.000 | 1050.000 | 1100.000-2000.000 | 2100.000 | 2400.000-2500.000;3900.000-4000.000;5400.000-5500.000;6900.000-7000.000;8400.000-8500.000;9900.000-10000.000;11400.000-11500.000;12950.000-13050.000 | static_from_t0;2300.000;3800.000;5300.000;6800.000;8300.000;9800.000;11300.000 | 13050.000 | 2.000 | - | NOT_RUN |
| `TR-120` | transient | `000` | 10.000 | 1050.000 | 1170.000 | 1170.000 | 1180.000-1280.000 | 1300.000 | 1430.000-1530.000 | static_from_t0 | 1530.000 | 2.000 | - | NOT_RUN |
| `TR-200` | transient | `000` | 10.000 | 1050.000 | 1170.000 | 1170.000 | 1180.000-1360.000 | 1380.000 | 1510.000-1610.000 | static_from_t0 | 1610.000 | 2.000 | - | NOT_RUN |
| `TR-OFFCODE` | transient | `011,100,000,111` | 20.000 | 1050.000 | 1350.000 | 1350.000 | 1370.000-1630.000 | 1670.000 | 1830.000-1930.000;2430.000-2530.000;3030.000-3130.000;3650.000-3750.000 | static_from_t0;1800.000;2400.000;3000.000 | 3750.000 | 2.000 | - | NOT_RUN |
| `RS-FULL` | refined_step | `000..111` | 50.000 | 1050.000 | 1050.000 | 1050.000 | 1100.000-2000.000 | 2100.000 | 2400.000-2500.000;3900.000-4000.000;5400.000-5500.000;6900.000-7000.000;8400.000-8500.000;9900.000-10000.000;11400.000-11500.000;12950.000-13050.000 | static_from_t0;2300.000;3800.000;5300.000;6800.000;8300.000;9800.000;11300.000 | 13050.000 | 0.100 | TR-LONG | NOT_RUN |
| `RS-LOW` | refined_step | `000` | 10.000 | 1050.000 | 1170.000 | 1170.000 | 1180.000-1280.000 | 1300.000 | 1430.000-1530.000 | static_from_t0 | 1530.000 | 0.100 | TR-120 | NOT_RUN |
| `RS-SWITCH` | refined_step | `011,100,000,111` | 20.000 | 1050.000 | 1350.000 | 1350.000 | 1370.000-1630.000 | 1670.000 | 1830.000-1930.000;2430.000-2530.000;3030.000-3130.000;3650.000-3750.000 | static_from_t0;1800.000;2400.000;3000.000 | 3750.000 | 0.100 | TR-OFFCODE | NOT_RUN |
<!-- END 7CB_R1 DECKS -->

<!-- BEGIN 7CB_R1 CASES -->
| 例 | 类型 | 判决 | 观察到的依据 | 说明 |
|---|---|---|---|---|
| C01_positive_sink_charge | POSITIVE | HIT | Q=1.875e-13 C over 100 ns at 1.875 uA, sign SINK_POSITIVE_AS_DECLARED | a 100 ns window at one unit current integrates to the hand-computed charge and reads positive |
| C02_reversed_probe_refused | NEGATIVE | HIT | the same physics on reversed terminals gives Q=-1.875e-13 C; abs() would have made it look identical to the positive cas | turning the ammeter around cannot be rescued by abs() |
| C03_deck_probe_order_named | NEGATIVE | HIT | line 79 became (data_out clamp_node) and the deck audit answered: TR-120.scs writes the probe as "Ip_branch (data_out cl | a deck written with the terminals swapped is refused by the deck audit |
| C04_cancelling_tail_fails | NEGATIVE | HIT | net Q=0 C looks like a shut branch, the magnitude test still says 0.5 uA against a 0.15 uA limit | a tail whose positive and negative halves cancel is not zero leakage |
| C05_quiet_tail_passes | POSITIVE | HIT | max(abs(I))=0.01 uA at 1380 ns inside the last 100 ns, under the 0.15 uA limit | a quiet tail passes and names its sample instant |
| C06_nonuniform_pencil_check | POSITIVE | HIT | Q=1.375e-13 C, boundaries interpolated onto the enclosing pairs | interpolated boundaries over unequal spacing match the arithmetic done by hand |
| C07_adaptive_precision | POSITIVE | HIT | kept 1.99902e+06 ps (quantum 50000 ps), which is the bound a reviewer needs beside the number | a printed simulator time is kept at its own precision with its display quantum reported |
| C08_garbage_named | NEGATIVE | HIT | four bad sample shapes and one edge-less window all refused by name | NaN, a repeated time, a backwards time, an empty list and a missing edge each refuse by name |
| C09_left_band_before_deadline | NEGATIVE | HIT | left the band at 1201.55 ns, held only None ns, deadline 1230 ns | entering the band and leaving early is not a settled window |
| C10_settled_held | POSITIVE | HIT | in band from the edge to the deadline, held 100 ns | staying in band to the deadline is the settled case |
| C11_halved_array | NEGATIVE | HIT | half current gives worst deviation 0 units of Iunit_ref, absolute 7.5 uA against the band 14.25-15.75 uA | eight levels at half current pass the ratio and fail the absolute target |
| C12_code_000_not_black | NEGATIVE | HIT | code 000 = 1 branch, and a ladder missing it is refused by name | the lowest code is one conducting branch and cannot be dropped from the ladder |
| C13_refined_lost_history | NEGATIVE | HIT | the schedule refused it: RS-FULL writes off_window_ns 2100.000-2500.000;3600.000-4000.000;5100.000-5500.000;6600.000-700 | a refined case that dropped the seven earlier platforms is not the same conditions |
| C14_refined_changed_supply | NEGATIVE | HIT | the schedule refused it: RS-LOW differs from TR-120 outside the time step: data_en_level_V | a refined case that also moved the enable level is refused |
| C15_refined_lost_transition | NEGATIVE | HIT | the schedule refused it: RS-SWITCH declares 3 code-change entries for 4 platforms | a refined case that dropped one code change is a different experiment |
| C16_convergence_absolute | NEGATIVE | HIT | delta Q=10 fC = 0.0444444 QLSB against a 0.01 limit; moving the window by 10 ns refuses the comparison | convergence always carries an absolute difference, and a moved window refuses the comparison |
| C17_two_charge_expectations | POSITIVE | HIT | nominal 1.875e-13 C vs DC NOT_RUN; QLSB 2.25e-13 C, error 0 LSB | nominal and DC expectations stay apart and the missing DC point is NOT_RUN, never a geometry guess |
| C18_leak_in_second_tail | POSITIVE | HIT | 8 codes, one 5 uA leak in platform 1: ABOVE_LIMIT at index [1] with max(abs(I)) = 5e-06 A over 100 ns, the other seven W | eight codes measured at once find the 5 uA leak in the second tail and nowhere else |
| C19_full_versus_flat_window | POSITIVE | HIT | full 2.15625e-13 C over 120 ns of enable versus flat 1.875e-13 C over 100 ns of flat part; the difference 2.8125e-14 C i | the full-enable charge and the flat charge are different numbers, each matching its own pencil arithmetic |
| C20_no_edge_refusal_left | POSITIVE | HIT | 27 windows over 7 transient cases measured through the entrance, edge refusals=0, edges off their declared instant=0 | every window of the delivered schedule finds its own interpolated 50% edges on the declared instant |
| C21_missing_context_refused | NEGATIVE | HIT | 5 context fields each refused by name when both sides omitted them; the complete pair converges at WITHIN_LIMIT | convergence refuses when a side does not carry the named context, instead of calling None equal to None |
| C22_leakage_window_refusals | NEGATIVE | HIT | a 10 ns tail refuses as REFUSED_LEAKAGE_OUTSIDE_PURE_OFF and an enable that reaches 1.8 V inside the window refuses as R | a leakage interval that reaches the pure-off start or a rising enable is refused, never shortened to fit |
| C23_dc_expectation_via_entrance | NEGATIVE | HIT | nominal 2.25e-13 C (-0.0416667 LSB) with the DC column NOT_RUN; supplying IDC 2 uA makes the DC expectation 2.4e-13 C, a | through the entrance a missing native DC point stays NOT_RUN while the nominal error is computed |
| C24_decks_read_clean | POSITIVE | HIT | 15 decks read from disk with the reader's own parser, problems=0 | the independent reader opens the fifteen delivered decks and finds nothing to report |
| C25_reader_names_the_shapes | NEGATIVE | HIT | 3 of 3 shapes refused by name on temporary copies (old_long_ramp, leak_window_over_next_rise, delivered_bytes_control) | the old long ramp and leakage over the next rise are refused by name on temporary copies |
<!-- END 7CB_R1 CASES -->

<!-- BEGIN 7CB_R1 READ -->
| 读数 | 值 |
|---|---|
| deck 数 | 15 |
| 窗类型计数 | {"dc_sweep_point": 8, "emission": 27, "emission_flat": 27, "leak_last100": 27, "off_tail": 27, "pure_off": 27} |
| PAM 变化段总数 | 36 |
| 半轨交叉总数 | 54 |
| 读到的 PWL 信号 | data_en, pam0, pam1, pam2 |

独立读盘由 `scripts/dd1_d7c_b_prep_r1_deck_read.py` 完成：它自带解析器，不 import 生成器与测量核，位权按 `pam0=1/pam1=2/pam2=4` 的字面常量写死。空问题表是在 27 个 emission 窗与 36 个 PAM 变化段上量出来的，不是沉默。
<!-- END 7CB_R1 READ -->

<!-- BEGIN 7CB_R1 RANGES -->
| 区间 | 新增 | 变更 | 删除 | 重命名 | 提交数 | 说明 |
|---|---|---|---|---|---|---|
| `3e4703f17632..dcef9b336f22` | 83 | 0 | 0 | 0 | 15 | 本轮基线区间，由 Git 重算；PREP 回执写的 68 新增在此更正为 83 |
| `dcef9b336f22..HEAD` | 7 | 26 | 0 | 0 | 3 | R1 修补区间，度量于运行本入口时已提交的 HEAD=10f69053a192；记录目录本身在下一个提交里 |
<!-- END 7CB_R1 RANGES -->

<!-- BEGIN 7CB_R1 FROZEN -->
| 比较 | 面 | 路径数 | 计数 | 前若干 | 期望 | 计入闸 |
|---|---|---:|---:|---|---|---|
| r1 | `every_P_path_outside_the_allowed_edit_surface` | 2670 | 0 |  | `identical` | yes |
| r1 | `allowed_edit_surface_modified_this_round` | 26 | 0 | reports/dd1_d7c_b_prep_contract.md;scripts/dd1_d7c_b_prep_cases.py;scripts/dd1_d7c_b_prep_ | `informational_listing` | no |
| r1 | `four_candidate_DUT_netlists` | 4 | 0 |  | `identical` | yes |
| r1 | `accepted_DATA7B_measurement_and_run_core` | 3 | 0 |  | `identical` | yes |
| r1 | `shared_tools_safety_and_provenance` | 14 | 0 |  | `identical` | yes |
| r1 | `PREP_record_as_published` | 23 | 0 |  | `identical` | yes |
| r1 | `earlier_round_record_dirs` | 51 | 0 |  | `identical` | yes |
| r1 | `PREP_report_handoff_and_task_book` | 4 | 0 |  | `identical` | yes |
| r1 | `R2_and_earlier_plan_and_decks` | 2 | 0 |  | `identical` | yes |
| r1 | `paths_added_this_round` | 7 | 0 |  | `only_allowed_new` | yes |
| r1 | `paths_removed_vs_P` | 0 | 0 |  | `none_removed` | yes |
| r1 | `paths_modified_vs_P` | 26 | 0 | reports/dd1_d7c_b_prep_contract.md;scripts/dd1_d7c_b_prep_cases.py;scripts/dd1_d7c_b_prep_ | `informational_listing` | no |
<!-- END 7CB_R1 FROZEN -->

## 10 已知失败、未做与限制（不写成通过）

* `NATIVE_NETLIST_SYNTAX=NOT_VERIFIED`：本轮 0 次 Spectre 调用，语句形状来自已运行的
  `scripts/dd1_d7b_run.py` 与 `spectre/current_probe_syntax.scs`，分层 `save` 仍无证据。
* 八档电气结果全部 `NOT_RUN`；`Qexpected_dc` 需要原生 DC 点，未运行；`Qexpected_nominal` 只是几何比。
* 模型身份、PDK 路径、`psf` 变量名一律未读卡，留给获批原生阶段逐项核验。
* 测量核仍是被接受的 `dd1_d7b_measure`：本轮没有重写积分/插值，因此它的精度局限一并继承。
* 合成样点全部 `SYNTHETIC_NOT_MEASURED`，只证明算法与判据，不证明电路。
* 既有待办与历史事件不变：DATA-7B 的 59/56 超量、凭据回显事件、更早轮次的遗留 todos 均保持原状，
  本轮未"顺手"处理。

## 11 停止条件

`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`。本轮不自行签发 GO，不启动 8 个 DC 例与 36 次发射草稿，
不改 `main`，不合并，不登记接受版本。
