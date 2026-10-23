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
| `DC-000` | dc_sweep | 0 (pam_sel=000, 1 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 1 branch(es) named by code 000 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-001` | dc_sweep | 1 (pam_sel=001, 2 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 2 branch(es) named by code 001 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-010` | dc_sweep | 2 (pam_sel=010, 3 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 3 branch(es) named by code 010 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-011` | dc_sweep | 3 (pam_sel=011, 4 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 4 branch(es) named by code 011 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-100` | dc_sweep | 4 (pam_sel=100, 5 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 5 branch(es) named by code 100 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-101` | dc_sweep | 5 (pam_sel=101, 6 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 6 branch(es) named by code 101 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-110` | dc_sweep | 6 (pam_sel=110, 7 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 7 branch(es) named by code 110 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `DC-111` | dc_sweep | 7 (pam_sel=111, 8 of 8 branches on) / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, vdd18, vss, Xdut.en0..en7, Xdut.enb0..en7, the eight Xdut.XuN.vbias_ch nodes | the DC operating point at each sweep step, no time window | Iref = 15u injected into the diode-connected Mref; theoretical unit current = 15u x (2.5/2)/(20/2) = 1.875 u, ESTIMATED_MIRROR_RATIO_ONLY | the 8 branch(es) named by code 111 are not the only ones conducting, the sunk current leaves the candidate band, or a non-selected branch keeps its local bias charged | clamp sweep 0.6 V to 1.5 V in 0.05 V steps; the inherited 1.2 V point is read off the same sweep | - | 2 | NOT_RUN |
| `TR-LONG` | transient | all eight codes, in ascending order, one platform each / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, the eight Xdut.XuN.vbias_ch nodes, Xdut.en0..en7 and Xdut.enb0..en7 | each listed platform window, integrated separately, no window straddles a code change | Iref = 15u into Mref; per-level charge compared against the estimated unit current, never against a measured value in this round | a platform whose integral does not match its code weight, a code change landing inside a window, two adjacent windows overlapping, or a branch conducting while its select term is off | 000@0-1;001@1.5-2.5;010@3-4;011@4.5-5.5;100@6-7;101@7.5-8.5;110@9-10;111@10.5-11.5 | - | 2 | NOT_RUN |
| `TR-120` | transient | 0 (pam_sel=000, one branch) / DATA_EN=1.8 V | iprobe current, data_out, the selected branch local bias node, iref_in, vcas | the flat part of the platform only, between the two declared edges | Iref = 15u into Mref; single-branch estimate 1.875 u ESTIMATED_MIRROR_RATIO_ONLY | the platform collapsing before the window opens, current flowing during the off window, or the tail failing to return to zero |  | - | 2 | NOT_RUN |
| `TR-200` | transient | 0 (pam_sel=000, one branch) / DATA_EN=1.8 V | iprobe current, data_out, the selected branch local bias node, iref_in, vcas | the flat part of the platform only, between the two declared edges | Iref = 15u into Mref; single-branch estimate 1.875 u ESTIMATED_MIRROR_RATIO_ONLY | the platform collapsing before the window opens, current flowing during the off window, or the tail failing to return to zero |  | - | 2 | NOT_RUN |
| `TR-OFFCODE` | transient | 011 then 100, then 000 then 111, always inside a gap / DATA_EN=1.8 V | iprobe current, data_out, the eight Xdut.XuN.vbias_ch nodes, iref_in, vcas | the second platform window, after one observed shut-down and discharge | Iref = 15u into Mref; the discharge itself is a native quantity and stays NOT_RUN here | a code change landing inside a window, a still-charged local bias node at the next turn-on, or current during an off window | 011@0.3-0.6;100@0.9-1.2;000@1.5-1.8;111@2.1-2.4 | - | 2 | NOT_RUN |
| `RS-FULL` | refined_step | all eight codes, in ascending order, one platform each / DATA_EN=1.8 V | iprobe current, data_out, iref_in, vcas, the eight Xdut.XuN.vbias_ch nodes, Xdut.en0..en7 and Xdut.enb0..en7 | each listed platform window, integrated separately, no window straddles a code change | Iref = 15u into Mref; per-level charge compared against the estimated unit current, never against a measured value in this round | a platform whose integral does not match its code weight, a code change landing inside a window, two adjacent windows overlapping, or a branch conducting while its select term is off | paired with TR-LONG | time_maxstep | 2 | NOT_RUN |
| `RS-LOW` | refined_step | 0 (pam_sel=000, one branch) / DATA_EN=1.8 V | iprobe current, data_out, the selected branch local bias node, iref_in, vcas | the flat part of the platform only, between the two declared edges | Iref = 15u into Mref; single-branch estimate 1.875 u ESTIMATED_MIRROR_RATIO_ONLY | the platform collapsing before the window opens, current flowing during the off window, or the tail failing to return to zero | paired with TR-120 | time_maxstep | 2 | NOT_RUN |
| `RS-SWITCH` | refined_step | 011 then 100, then 000 then 111, always inside a gap / DATA_EN=1.8 V | iprobe current, data_out, the eight Xdut.XuN.vbias_ch nodes, iref_in, vcas | the second platform window, after one observed shut-down and discharge | Iref = 15u into Mref; the discharge itself is a native quantity and stays NOT_RUN here | a code change landing inside a window, a still-charged local bias node at the next turn-on, or current during an off window | paired with TR-OFFCODE | time_maxstep | 2 | NOT_RUN |

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
