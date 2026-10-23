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
| 零压降电流探针 | `Ip_branch (data_out clamp_node) iprobe` + `save Ip_branch Ip_branch:current` | `spectre/current_probe_syntax.scs` 已实测 `iprobe` 与 `:current` 形态可用 |
| 路径可配置、不复制 PDK | `include "${QODER_PDK_LIB}" section=tt`、`include "${QODER_NETLIST_DIR}/…"` | 不导入模型卡/licence，也不把别人的库装进仓库 |
| 分析语句全部注释 | 草稿里 `dc`/`tran` 行都以 `//` 起头 | 检查器 `DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS` 实测"活动分析语句 0"，就算有人指过去也起不来 |
| 层级 `save` 语法未证 | `save Xdut.en0 …`、`save Xu0.vbias_ch …` 标 `NOT_VERIFIED` | 本仓库只实测过 `save 节点` 与 `save Mout:drain`；层级写法需在下一轮先以探针确认，不得改动已交付候选来"配合" |

每码一个 deck 的做法：把 8 个 DC 码和 4 个瞬态码的差异收敛到 `PAM0V/PAM1V/PAM2V` 三个参数，
由下一轮的生成器按参数替换产出，不手抄 8 份副本。本轮该生成器
`scripts/dd1_d7c_a_deckgen.py` 在 4 种环境组合下都**先拒绝再返回**，
且不创建目录、不动正式产物（`NATIVE_ENTRY_REFUSED`，含哨兵文件与目录摘要不变）。

## 2 用例矩阵（机读表的渲染，不重复手填数字）

<!-- BEGIN 7C PLAN -->
| 用例 | 类别 | 目的 | 观察节点 | 测量区间 | 参考定义 | 失败条件 | 草案额度 | 结果 |
|---|---|---|---|---|---|---|---:|---|
| `DC-000` | dc_sweep | absolute current of the single unit branch and the decoded level set at the lowest code | clamp_node current (iprobe), iref_in, vdd18, vss, Xdut.en0..en7, the eight XuN.vbias_ch | whole clamp sweep; the 1.2 V point is read off the sweep, not assumed | Iref = 15 uA injected into the diode-connected Mref; theoretical unit = Iref x (2.5/2)/(20/2) | branch current outside the candidate tolerance band, or en0 low, or any other branch's local bias node charged | 2 | **NOT_RUN** |
| `DC-001` | dc_sweep | second code: two unit branches on | clamp_node current, Xdut.en1, Xu1.vbias_ch | whole clamp sweep | same shared reference | mask not equal to the hand-written golden row G02, or non-monotonic step from DC-000 | 2 | **NOT_RUN** |
| `DC-010` | dc_sweep | third code | clamp_node current, Xdut.en2 | whole clamp sweep | same shared reference | mask mismatch G03 or step error beyond the candidate DNL | 2 | **NOT_RUN** |
| `DC-011` | dc_sweep | fourth code, the mid-point | clamp_node current, Xdut.en3 | whole clamp sweep | same shared reference | mask mismatch G04 | 2 | **NOT_RUN** |
| `DC-100` | dc_sweep | fifth code; the case that breaks if select1 is reused where pam1|pam0 is meant | clamp_node current, Xdut.en4, Xdut.en5 | whole clamp sweep | same shared reference | more than five branches on, i.e. gor10 replaced by sel1 in Xsel5 | 2 | **NOT_RUN** |
| `DC-101` | dc_sweep | sixth code | clamp_node current, Xdut.en5 | whole clamp sweep | same shared reference | mask mismatch G06 | 2 | **NOT_RUN** |
| `DC-110` | dc_sweep | seventh code | clamp_node current, Xdut.en6 | whole clamp sweep | same shared reference | mask mismatch G07 | 2 | **NOT_RUN** |
| `DC-111` | dc_sweep | full scale: eight branches, expected to equal the accepted 15 uA single-channel current | clamp_node current, iref_in, all eight local bias nodes | whole clamp sweep | full scale is the shared reference itself, so normalisation is against Iref and not against a fitted value | total below the candidate full-scale band, or one branch not contributing (a branch whose DATA_OUT is not on data_out) | 2 | **NOT_RUN** |
| `TR-LONG` | transient | long pulse at code 111: delivered charge per window, settling into band, shutoff | clamp_node current, data_out, iref_in, XuN.vbias_ch of every branch | from before the enable rise to after the enable fall plus the tail; band entry and exit by adjacent-sample interpolation | theoretical Q = target current x window; also measured against the same case's own static current | never entering the band, entering after the window deadline, or a shutoff tail beyond the candidate leak limit | 2 | **NOT_RUN** |
| `TR-120` | transient | 120 ns short pulse at a representative code (Hybrid spacing at 100 Hz) | clamp_node current, data_out, one local bias node per selected branch | the 120 ns platform, plus 200 ns after it | same | charge error per pulse beyond the candidate band; sampled-versus-interpolated edge disagreement larger than maxstep | 2 | **NOT_RUN** |
| `TR-200` | transient | 200 ns short pulse at the same code (Hybrid spacing at 60 Hz) | same as TR-120 | the 200 ns platform, plus 400 ns after it | same | same, and the 120-to-200 charge ratio must stay inside the candidate linearity band | 2 | **NOT_RUN** |
| `TR-OFFCODE` | transient | enable shutoff and code changes made only inside the off window: 011 to 100 and 000 to 111 | Xdut.en0..en7, the eight local bias nodes, clamp_node current | one off window plus the following emission window | same | a code changing while the output conducts, or a local bias node still charged at the start of the next window (bleed not working) | 2 | **NOT_RUN** |
| `RS-LOW` | refined_step | same stimulus as DC-000 with a finer sweep step near the 1.2 V region | clamp_node current, Xu0.vbias_ch | 0.9 V to 1.5 V at the finer step | same as its paired case | a result that moves more than the candidate resolution between the two steps, i.e. the coarse step was not converged | 2 | **NOT_RUN** |
| `RS-FULL` | refined_step | same stimulus as DC-111 with a finer sweep step | clamp_node current, all local bias nodes | 0.9 V to 1.5 V at the finer step | same as its paired case | full-scale value not reproduced within the candidate resolution | 2 | **NOT_RUN** |
| `RS-SWITCH` | refined_step | same stimulus as TR-OFFCODE with a smaller maxstep | enable nets, local bias nodes, clamp_node current | same windows as the paired case | same as its paired case | a transient feature that appears only at one maxstep, i.e. not resolved; identical input edge timing does NOT prove the analog current converged | 2 | **NOT_RUN** |

渲染来源：`tests/dd1_d7c_a/native_case_plan.csv`（15 行，草案额度合计 30，结果列全部为 `NOT_RUN`）。本表由 `scripts/dd1_d7c_a_verify.py` 写入，不手填。
<!-- END 7C PLAN -->

判据要点：DC 逐码给绝对电流、单位支路电流、单调性、译码电平与参考/局部偏置；
瞬态给八档长脉冲、120 ns 与 200 ns 短脉冲代表码、`DATA_EN` 关断与只在关态换码
（`011→100`、`000→111` 两个换码位置要单独检查）；3 例细步长复测与其配对原案例
（DC-000 / DC-111 / TR-OFFCODE）成对给出，只改 `maxstep`。
**理想输入沿相同不等于模拟电流收敛**，细步长配对比对的是特征是否随 `maxstep` 移动。

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
