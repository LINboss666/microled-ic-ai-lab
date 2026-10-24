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

<!-- BEGIN 7CB_R1 GATES -->
<!-- END 7CB_R1 GATES -->

<!-- BEGIN 7CB_R1 REPAIRS -->
<!-- END 7CB_R1 REPAIRS -->

<!-- BEGIN 7CB_R1 DECKS -->
<!-- END 7CB_R1 DECKS -->

<!-- BEGIN 7CB_R1 CASES -->
<!-- END 7CB_R1 CASES -->

<!-- BEGIN 7CB_R1 READ -->
<!-- END 7CB_R1 READ -->

<!-- BEGIN 7CB_R1 RANGES -->
<!-- END 7CB_R1 RANGES -->

<!-- BEGIN 7CB_R1 FROZEN -->
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
