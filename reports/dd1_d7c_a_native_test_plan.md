# DATA-7C-A 下一阶段原生验证计划（只准备，不执行；2026-10-23）

配套：候选源网表与逐管说明见 `reports/dd1_d7c_a_pam_candidate.md`，
bench 草稿见 `spectre/dd1_d7c_a_tb_draft.scs`，机读用例表见 `tests/dd1_d7c_a/native_case_plan.csv`。

**本文件不含任何仿真结果。** 15 个用例的 `result` 全部是 `NOT_RUN`，
`NATIVE_NETLIST_SYNTAX=NOT_VERIFIED`，`PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN`。
本轮 0 次 Spectre、0 次 RTL 仿真、0 次 OA 写入，未运行 `spectre -h`，未做动态 rail preflight，
未重跑旧波形；下面的额度只是**可审议草案**，不是授权。

## 1 bench 结构约定（先说清"什么是分离的"）

| 约定 | 落实位置 | 为什么 |
|---|---|---|
| 测试台电源/参考与 DUT 分离 | `Iref_in`（`isource dc=IREFU`）注入 `iref_in`；`Vdd18/Vss/Vcas/Vclamp` 全在 deck 层 | 已接受 `dd1_d7b_pwm_stage.scs` 的口径：`iref_in` 是 bench 电流计注入二极管连接参考的节点，**不是理想 VBIAS** |
| 供电显式接地 | `Vss (vss 0) vsource dc=0` | `AGENTS.md` 坑 19：`vss` 不接 0 时所有 NMOS 通路不存在，整版看起来"全是 PMOS 在工作" |
| 输出夹持独立 | `Vclamp (clamp_node 0) vsource dc=1.2`，串 `iprobe` 测支路总流 | 扫输出节点时不与码源打架；1.2 V 是继承的 POC 夹持条件 |
| 零压降电流探针 | `Ip_branch (clamp_node data_out) iprobe` + `save Ip_branch Ip_branch:current` | `spectre/current_probe_syntax.scs` 已实测 `iprobe` 与 `:current` 形态可用；端序按已接受 DATA-7B 的 `Ip_out (clamp data_out) iprobe` 写法 |
| 路径可配置、不复制 PDK | `include "${QODER_PDK_LIB}" section=tt`、`include "${QODER_NETLIST_DIR}/…"` | 不导入模型卡/licence，也不把别人的库装进仓库 |
| 分析语句全部注释 | 草稿里 `dc`/`tran` 行都以 `//` 起头 | 检查器 `DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS` 实测"活动分析语句 0"。**这句话只说草稿里没有要跑的分析**，不保证有人对 Spectre 指点这个文件时进程不会起来；禁止原生运行由入口授权闸保证，不由注释保证 |
| 分析语句识别不再依赖 `dev=` | 关键词出现在第二个位置即判定（`review_tran tran stop=1u maxstep=1n` 与 `... dc dev=V... param=dc ...` 两种形态各自是反例 E21/E22） | 审核方实测旧式只认 `dev=` 的写法会漏掉常见 tran 形式；越界的活动语句另由 `DRAFT_DECK_SYNTAX_INVENTORY` 具名拒收（E23） |
| DC 与瞬态用不同的使能形态 | DC 例用静态 `Vdata_en_dc (data_en 0) vsource dc=DEV1V`；瞬态例用有限沿 `type=pwl`，两者由生成器按例二选一 | 绝对电流读数要求支路在整个测量期间导通；沿用起始为 0 的脉冲波形会让 DC 点在"全关"状态下测 |
| 探针方向与取号先于运行声明 | `Ip_branch (clamp_node data_out) iprobe`，首端是电流**进入**探针的节点，因此正值就是被选中支路把电流从 `data_out` 抽向 vss 的下拉电流；`I_sink = Ip_branch`，**不取负、不取 abs()**，`Q = ∫ I_sink dt` 只在导通窗口累积正面积，关断尾窗单独积其负面积 | 串联回路的物理正方向是 `clamp_node → data_out → 支路 → vss`；R1 把端序写成 `(data_out clamp_node)` 却把正值解释成同一件事，等于运行前就把符号定反。检查器闸 `DECK_PROBE_ORIENTATION_MATCHES_PLAN` 用 deck 与机读表两端同时核这条口径，反例 E39 把探针转回去必须具名失败；`scripts/dd1_d7c_a_r2_sign_check.py` 用手写的合成样点核这条算术（**SYNTHETIC_NOT_MEASURED**，不是测量结果） |
| 层级 `save` 语法未证 | `save Xdut.en0 …`、`save Xdut.Xu0.vbias_ch …` 标 `NOT_VERIFIED` | 本仓库只实测过 `save 节点` 与 `save Mout:drain`；层级写法需在下一轮先用探针确认，不得改动已交付候选来"配合" |

每码一个 deck 的做法：8 个 DC 例之间的差异只有 `PAM0V/PAM1V/PAM2V` 三个码位参数与静态使能，
瞬态例之间还差时间平台宽度；由下一轮的生成器按参数替换产出，不手抄 8 份副本。
**只替换 PAM 三位不足以定义不同的瞬态波形**，所以每个瞬态例在机读表里逐行写自己的码、
平台起止与关断尾窗。本轮该生成器
`scripts/dd1_d7c_a_deckgen.py` 在 4 种环境组合下都**先拒绝再返回**，
且不创建目录、不动正式产物（`NATIVE_ENTRY_REFUSED`，含哨兵文件与目录摘要不变）。

## 2 用例矩阵（机读表的渲染，不重复手填数字）

<!-- BEGIN 7C PLAN -->
| 用例 | 类别 | 码与使能 | 观察节点 | 测量区间 | 参考定义 | 失败条件 | 分段/配对 | 细化对象 | 额度 | 结果 |
|---|---|---|---|---|---|---|---|---|---:|---|
| `DC-000` | dc_sweep | 0 (pam_sel=000, one branch) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | en0 low, or any other branch conducting, or the branch current outside the candidate band, or a non-conducting branch whose local bias node is charged | one static operating point per sweep step | - | 2 | NOT_RUN |
| `DC-001` | dc_sweep | 1 (pam_sel=001, two branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | mask differs from golden row G02, or the step from DC-000 is not one unit within the candidate band | as DC-000 | - | 2 | NOT_RUN |
| `DC-010` | dc_sweep | 2 (pam_sel=010, three branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | mask differs from G03, or DNL beyond the candidate band | as DC-000 | - | 2 | NOT_RUN |
| `DC-011` | dc_sweep | 3 (pam_sel=011, four branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | mask differs from G04 | as DC-000 | - | 2 | NOT_RUN |
| `DC-100` | dc_sweep | 4 (pam_sel=100, five branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | more than five branches conducting, i.e. the gor10 term replaced by sel1 in the AND of branch 5 | as DC-000 | - | 2 | NOT_RUN |
| `DC-101` | dc_sweep | 5 (pam_sel=101, six branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | mask differs from G06 | as DC-000 | - | 2 | NOT_RUN |
| `DC-110` | dc_sweep | 6 (pam_sel=110, seven branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | mask differs from G07 | as DC-000 | - | 2 | NOT_RUN |
| `DC-111` | dc_sweep | 7 (pam_sel=111, eight branches) / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | clamp sweep 0.6 V to 1.5 V; the inherited 1.2 V point is read off the sweep | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2); full scale is the shared reference itself, so normalisation is against Iref and never against a fitted value | total below the candidate full-scale band, a branch contributing nothing (its output is not on data_out), or a branch still charging its local bias node | as DC-000 | - | 2 | NOT_RUN |
| `TR-LONG` | transient | segments below: 000 001 010 011 100 101 110 111 / DATA_EN=1.8 V | iprobe output current, data_out, iref_in, each branch local bias node, the decoded enable nets | per segment: off gap, then the emission window, then the shutoff tail | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2); theoretical Q per segment = target current x window length, and separately against that segment own measured static current | a segment whose charge or monotonic step fails the candidate band, or a code changing inside its own emission window | 000 at 1.5TON..2.5TON then 0.5TON off; 001 at 4TON..5TON off 0.5TON; 010 at 6.5TON..7.5TON off 0.5TON; 011 at 9TON..10TON off 0.5TON; 100 at 11.5TON..12.5TON off 0.5TON; 101 at 14TON..15TON off 0.5TON; 110 at 16.5TON..17.5TON off 0.5TON; 111 at 19TON..20TON off 0.5TON | - | 2 | NOT_RUN |
| `TR-120` | transient | 0 (pam_sel=000, one branch) / DATA_EN=1.8 V | iprobe output current, data_out, Xdut.Xu0.vbias_ch, the seven other local bias nodes | platform 120 ns with finite rise and fall, plus a 200 ns shutoff tail after the platform | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2); the pulse charge is compared to the target and separately to the DC-000 measured static current of the same branch | never entering the candidate band, entering after the window deadline, or a shutoff tail beyond the leak limit | one platform per run | - | 2 | NOT_RUN |
| `TR-200` | transient | 0 (pam_sel=000, one branch) / DATA_EN=1.8 V | iprobe output current, data_out, Xdut.Xu0.vbias_ch | platform 200 ns with finite rise and fall, plus a 400 ns shutoff tail | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | same as TR-120, and the 120 ns to 200 ns charge ratio must stay inside the candidate linearity band | one platform per run | - | 2 | NOT_RUN |
| `TR-OFFCODE` | transient | 011 to 100 and 000 to 111, each transition inside the off window / DATA_EN=1.8 during the emission segments only V | Xdut.en0..en7, the eight local bias nodes, iprobe output current | one off window carrying the transition, then the following emission window, then its tail | external reference Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) | a code changing while the output conducts, or a local bias node still charged at the start of the next window, which would mean the bleed device is not discharging it | off 0..2TON with 011 to 100 at 1TON; emit 2TON..3TON; off 3TON..5TON with 000 to 111 at 4TON; emit 5TON..6TON | - | 2 | NOT_RUN |
| `RS-LOW` | refined_step | 0 (as TR-120) / DATA_EN=1.8 V | as TR-120 | identical window to TR-120 | identical to TR-120 | a feature that moves when maxstep shrinks, i.e. the coarse step was not resolved; equal ideal input edges are not evidence that the analog current converged | paired with TR-120 | time_maxstep | 2 | NOT_RUN |
| `RS-FULL` | refined_step | 7 (the last segment of TR-LONG) / DATA_EN=1.8 V | as the TR-LONG code 111 segment | identical window to that segment | identical to TR-LONG | full-scale charge not reproduced within the candidate resolution between the two steps | paired with TR-LONG | time_maxstep | 2 | NOT_RUN |
| `RS-SWITCH` | refined_step | 011 to 100 and 000 to 111 (as TR-OFFCODE) / DATA_EN=1.8 during the emission segments only V | enable nets, local bias nodes, iprobe output current | identical windows to TR-OFFCODE | identical to TR-OFFCODE | a discharge or turn-on transient that exists at only one maxstep, i.e. unresolved | paired with TR-OFFCODE | time_maxstep | 2 | NOT_RUN |

渲染来源：`tests/dd1_d7c_a/native_case_plan.csv`，15 例，草案额度合计 30；探针方向与取号在每一行相同且先于任何运行声明，逐字取自唯一结构化来源 `scripts/dd1_d7c_a_r2_plan.py`：`iprobe Ip_branch (clamp_node data_out), positive terminal first: a positive reading IS the branch sinking current out of data_out`。窗口、间隔与配对同一来源，改数字只能改那一处，`PLAN_SCHEDULE_ARITHMETIC` 再把它逐行核回机读表。
<!-- END 7C PLAN -->

判据要点（与机读表逐行对应，渲染由 `native_case_plan.csv` 生成，不手填）：

- **8 个 DC 例**：`pam_sel = 000…111` 每码一例，`DATA_EN` 取**静态** 1.8 V，参考固定 15 µA，
  扫输出夹持 0.6–1.5 V 后读 1.2 V 点；读的是探针总流、逐码的分支电流与译码/参考/局部偏置节点。
- **4 个瞬态例**：`TR-LONG` 在**一个 deck 内排八个长发光窗**（000…111 依次，窗口间留关态间隔，
  换码只发生在关态）——八段仍算一例一次启动，不是只做码 111 却称"八档长脉冲"；
  `TR-120` 与 `TR-200` 都用**最低档 000**（一条单位支路）分别取 120 ns 与 200 ns 平台，
  使低电流短窗真的被覆盖，两例只差时间；`TR-OFFCODE` 检查关断与只在关窗期间的换码
  （`011→100`、`000→111`），观察关断质量、局部偏置放电与下次导通。
- **3 例时间细化配对**：`RS-LOW`↔`TR-120`（低档短窗）、`RS-FULL`↔`TR-LONG` 的码 111 段（满档长窗）、
  `RS-SWITCH`↔`TR-OFFCODE`（关断/换码）。每对激励与条件完全相同、**只细化时间 `maxstep`**；
  DC 的电压扫步长是另一回事，不用它冒充时间收敛判据。**理想输入沿相同不等于模拟电流收敛**，
  配对比对的是特征是否随 `maxstep` 移动。

## 3 测量口径必须先分列（否则数字会互相掩盖）

| 类别 | 定义 | 不许混淆的点 |
|---|---|---|
| 静态绝对误差 | 每码实测电流 − 理论目标（目标 = `Iunit × 导通支路数`，`Iunit` 由参考与镜像比给出） | 目标不是拟合值；逐码自行归一后不得再声称"档位误差为零" |
| 归一化误差 | 实测 / 共享参考（满档 = 参考本身），统一 µA 与相对满档两种口径 | 归一基准必须全表一致，不能逐码换基准 |
| 单调性 / DNL / INL | 相邻码差分与理想步长之差；INL 相对同一条理想直线 | 候选 A 的结构 DNL 期望为 0，但**实测** DNL 由失配决定，不能拿结构期望当结果 |
| 动态总电荷（对目标） | `∫ i(t) dt` 在窗口内，相对 `I_target × t_window` | 用插值过零点分段，正/负电荷分别累计 |
| 动态总电荷（对该档实测静态） | 同一积分，除以该档自己实测的静态电流 | 两个口径必须同时给出并注明是哪一个，否则脉冲误差会被静态偏差掩盖或放大 |
| 入带时刻 | 相邻样点 + 线性插值的阈值穿越 | 采样时刻与连续阈值时刻是两个数，必须分列（DATA-7B 的教训） |
| 保持判据 | 入带后必须持续到**该窗口自身的 deadline 左侧** | 不得把"在 deadline 前离带"写成"时长不足"；两者是不同的失败原因 |
| 关断与末段 | 最后样点到窗口末端的电流与泄漏 | 末段泄漏不等于支路已关；每支路局部偏置节点的放电要单独看 |
| 状态分类 | 电气 FAIL / 证据缺失或 BLOCKED / 检查器异常 / 历史预算违规 | 四类分开记录，不得折叠成一个总 rc |

显示精度纪律（继承 DATA-7B）：任何四位小数 ns 列的分辨率只能是 0.1 ps，
比较容差要显式写出 LSB 与量化项，不得靠放宽容差凑通过。

## 4 额度草案（30/36 不是本轮授权）

```text
本轮（DATA-7C-A）实际成本：NEW_SPECTRE_LAUNCHES=0, NEW_RTL_SIMULATIONS=0, NEW_OA_WRITES=0
下一轮草案（仅供审议，未获授权）：
  用例 15 个（8 DC + 4 瞬态 + 3 细步长）
  若每个 DUT 案例配一次动态 rail preflight -> 15 x 2 = 30 次原生启动
  再加 6 次工具/语法调试余量                          -> 总上限建议 36
DATA-7B 旧账户的 56 次授权不借用、不重置、不追溯；历史 59 次实际启动对 56 次固定授权、
超支 3 次仍是 VIOLATED_NOT_RETROACTIVELY_AUTHORISED，处置权在用户。
```

若下一轮获授权，账户协议沿用已修好的规则：行写入即占额（`REQUESTED`）、崩溃恢复后无法证实的
运行记 `UNCERTAIN` 且保留占额、未知/空/大小写或空白变体状态一律拒收并保留原字节，
复核器对所有行独立核 `ACCOUNT_STATES_VALID`，`BUDGET_RESPECTED` 不因新工具而被改写。

## 5 仍需"另行冻结"的参数（执行者不得边看结果边改）

实际八档电流值与是否采纳 1.875–15 µA、判决阈值与允许误差、电荷 `Q` 的归一方式、
`Iunit` 是用参考比还是实测单位支路平均、细步长的 `maxstep` 配对判据、原生启动额度。
以上必须由独立审核与用户在本轮之后冻结；本轮只把它们列为待决项。

无 LED I–V、无阵列 RC、无片上驱动阻抗、无 PVT 角证据，因此本文件不给光学、
阵列或可靠性任何结论；`OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED`，`SOA_SIGNOFF=NO`。

## 6 停止状态

```text
TASK_ID=DATA-7C-A
NATIVE_PLAN_STATUS=PREPARED_NOT_EXECUTED
PLANNED_CASES=15
PLANNED_DRAFT_LAUNCH_UNITS=30
PLANNED_DRAFT_CEILING_INCLUDING_DEBUG=36
AUTHORISED_NATIVE_LAUNCHES_THIS_ROUND=0
NEXT_NATIVE_STAGE_AUTHORISED=NO
ALL_CASE_RESULTS=NOT_RUN
STOP_REASON=AWAITING_INDEPENDENT_REVIEW_OF_CANDIDATE_AND_TEST_PLAN
```
