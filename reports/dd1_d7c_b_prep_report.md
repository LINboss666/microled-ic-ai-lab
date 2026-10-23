# DATA-7C-B-PREP 八档 PAM 原生验证准备报告（2026-10-23，停在独立复审闸）

任务书逐字节副本 `reports/tasks/DATA-7C-B-PREP.md`（18,448 B，SHA-256
`40a3eb148e038c4fb6ea4d5a7d48de4b2e9b22e6a34a685c34f912f2a3c8b126`，源
`C:\Users\LMX\Downloads\TASK_DATA7C_B_PREP_20261023.md`，逐字节比较相等；该文件无 CR，故 Git blob
与工作副本同为这 18,448 B）。

## 0 身份与边界

| 项 | 值 | 怎么核 |
|---|---|---|
| 仓库 | `https://github.com/LINboss666/microled-ic-ai-lab` | 推送后两条通道各自回读 |
| 工作基线 R2 | `3e4703f1763223024f442c0826e95055782bca13` | 双通道回读（§1） |
| 本轮分支 / 工作树 | `poc/data-pam-d7c-b-prep` / `D:\ic617_d7c_b_prep`（`git worktree` 自固定 R2 SHA） | `git worktree list` |
| 对照 | R1 分支 `poc/data-pam-d7c-a-r1` = `da6f5fc…`；被审 A 分支 = `89b3dd8…`；main = `23e471c…`；DATA-7B 线 = `272d6de…` | 同上，本轮全部不动 |
| 合同状态 | `PROPOSED_FOR_REVIEW`，**不是** `USER_APPROVED`；R2 的独立复审**未**由本轮给出接受结论 | `tests/dd1_d7c_b_prep/contract.json` |
| 逐字限制 | `NEW_SPECTRE_LAUNCH_LIMIT=0`、`NEW_RTL_SIMULATION_LIMIT=0`、`NEW_OA_WRITE_LIMIT=0`、`NATIVE_PREFLIGHT_AUTHORISED=NO`、`SSH_OR_VM_ACCESS_AUTHORISED=NO`、`PDK_OR_CREDENTIAL_ACCESS_AUTHORISED=NO`、`ACCEPTANCE_REGISTRATION_AUTHORISED=NO`、`MERGE_OR_MAIN_PUSH_AUTHORISED=NO`、`NEXT_NATIVE_STAGE_AUTHORISED=NO` | 记录 `verification_summary.json` 三项成本为 0 |
| 实际做的 | 纯 Python 文本/算术/Git 读；未起任何仿真器（含 `spectre -h`），未读 PDK/模型卡/凭据，未连 guest，未 GC、未重写历史、未 force、未跳 hooks（提交与推送钩子每次都真实运行） | 每条命令文本记在 `commands.csv` |
| 只新增 | 本轮对 R2 已有路径零修改零删除（§6），只写新路径 | 记录 `frozen_comparison.csv` enforced 行 |

## 1 开工核验（双通道，逐 ref 完整 SHA）

推送前于 `2026-10-23T16:50:38Z`（Git protocol，rc=0）与 `2026-10-23T16:50:50Z ~ 16:50:58Z`
（GitHub API，rc=0）读同一组 ref，两路一致：

| ref | 两路返回的完整 SHA | 判定 |
|---|---|---|
| `poc/data-pam-d7c-a-r2` | `3e4703f1763223024f442c0826e95055782bca13` | 本轮基线，与任务书固定值相同 |
| `poc/data-pam-d7c-a-r1` | `da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb` | R1 tip 未动 |
| `poc/data-pam-d7c-a` | `89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79` | 被审 tip 未动 |
| `main` | `23e471cb936b421ee97e1250c3be06edf96f9937` | 未动 |
| `poc/data-pwm-d7b-r3` | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` | DATA-7B 线未动 |
| `poc/data-pam-d7c-b-prep` | Git protocol 无该行；API 404 | 本轮分支当时尚未建立，这是正确答案而非读回失败 |

对象存在性另核：`f9fd09b184a69a27cdb409205dfd4f4151408a23`（DATA-7B 接受内容）、
`f68449672774ac9266ba9e4893024e4f3027dd9d`（DATA-7A 接受内容）与 R2 tip 三个对象 API 均按完整 SHA
返回自身。审核端已在固定 R2 字节上重放 34 项离线检查、65 条反例与记录复核，这只算进度核验，
不是 R2 的完整独立复审 GO。

## 2 电路边界与激励（本轮真正交付的东西）

四份候选 DUT 与 R2 逐字节相同（`gates / pam_dec / sink_unit / pam_top`，§6 的 enforced 行给结论）：
一个输出 `data_out`、八条单位下拉支路、一个共享二极管连接参考。`data_en=1` 时导通数
`pam_sel+1`，`data_en=0` 时全关；码 `000` 是**最低非零档**（一条支路 ≈ 1.875 µA 估算），不是黑码。
`Mref` 20 µm/2 µm、单位 `Mcas/Mout` 2.5 µm/2 µm，`Iref=15 µA` 外供 ⇒ 名义单位电流
1.875 µA，身份 `ESTIMATED_MIRROR_RATIO_ONLY`；`Mpass/Mbleed` 本轮不重新缩放。
LED 的 N 侧接 Data 恒流下拉、Scan 的 PMOS 高侧接 LED 的 P 侧这条极性和行列称呼未做任何统一化改写。

激励与观测全部从**一份**合同生成，避免同一个数出现第二个说法：

```text
tests/dd1_d7c_b_prep/contract.json   条件、判据、单位、名义阶梯、额度、与 R2 的差异
        ↓ scripts/dd1_d7c_b_prep_contract.py（唯一写手，含自校验）
tests/dd1_d7c_b_prep/schedule.csv    15 例逐例绝对时刻（ns）：平台起止、50% 沿、积分窗、关窗、
                                     尾窗、末 100 ns 漏流子窗、换码时刻与理由、stop、maxstep、配对
tests/dd1_d7c_b_prep/windows.csv     62 条窗口行（emission / off_tail / dc_sweep_point）
tests/dd1_d7c_b_prep/pwl.csv         215 个 PWL 点（DATA_EN 与三位 PAM 各自一条时间轴）
        ↓ scripts/dd1_d7c_b_prep_deckgen.py
spectre/dd1_d7c_b_prep/*.scs         15 份 deck 文本，每份把上述数字写在自己文件头
```

三处相对 R2 的实质改进，都是本轮该做的准备：

1. **统一 1 µs 初始关断预备**（`lead_off_ns=1000`），平台、换码点、积分窗、尾窗、stop 同量平移，
   `offset_applied_ns` 逐例记录。R2 的 `TR-LONG` 第一平台从 t=0 就点亮，使能没有上升沿可找；
   现在第一沿在 1000 ns，且码在 750 ns 就已稳定。
2. **"120 ns 平台"不再指两个时刻**：`platform_start/stop`、`enable_rise_50/fall_50`、
   `window_start/stop`、`tail_start/stop`、`leak_last100_start` 分列。使能斜坡关于其 50% 点对称，
   所以两次斜坡之间就是声明的积分窗（TR-120：平台 1120→1240，窗 1130→1230，尾 1240→1480，
   漏流子窗 1380→1480）。
3. **换码落在关窗中点**而非与沿重合（TR-LONG 提前 250 ns、TR-OFFCODE 提前 150 ns），
   "换码完全处于关态"因此是可检查的事实；规则与余量写在行里。

`RS-LOW/RS-FULL/RS-SWITCH` 与各自伙伴的 14 个身份字段逐字相等，只差 `maxstep`
（2.0 ns → 0.1 ns）；`RS-FULL` 复制 `TR-LONG` 的**全部八段**历史与分段，不从最后一窗重启。
DC 八例用静态 `Vdata_en (data_en 0) vsource dc=1.8`，瞬态用 `type=pwl` 有限沿，两种使能互斥
（同一节点两个源同时驱动是接线错误，deck 审计会拒）。每个网络显式接地，夹持源与参考电流源在
bench 层，PDK 只留 `${QODER_PDK_LIB}` 环境变量占位。层级 `save`、`type=pwl` 拼写与原生语法一律
`NOT_VERIFIED`：这些是审核方读的文字，不是本 build 已证特性。

## 3 测量口径（先定死，不看波形后改）

* 探针固定 `Ip_branch (clamp_node data_out) iprobe`，`I_sink = Ip_branch`；物理正方向
  `clamp_node → data_out → 导通支路 → vss`，与已接受 DATA-7B 台架的端序一致。原始电流与总电荷
  **永不**取 abs()。
* 关断尾流可正可负，不预设"尾段=负面积"。每个窗口单独给有符号 `Q`、`Qpos`、`Qneg`，并要求
  `Q = Qpos + Qneg`；漏流判据用 `max(abs(I))`，但同一段的正负两半必须仍然可见。
* 时间/电流/使能样点严格读取：非有限拒收、时间严格递增、自适应样点**不**取整到 ps 网格，
  并随结果返回显示量化界（`time_quantum_ps`）。
* 50% 沿用相邻两点 + 线性插值；找不到真实沿 → `NO_REAL_EDGE_FOUND`，绝不回退到窗口末点。
* 电荷：`Qexpected_nominal = Inominal(k) × T50`、`Qexpected_dc = IDC(k) × T50`；无 DC 原生值时后者
  `NOT_RUN`，不用几何比冒充 `IDC`。两者都按声明 QLSB 报，候选限 0.5 LSB 只作待审判据。
* 入带：目标 ±5%，持续 ≥10 ns，deadline 为该窗自身末点；曾入带但提前离带必须报
  `LEFT_BAND_BEFORE_DEADLINE`，未达条件 → `NOT_SETTLED_WITHIN_PULSE`；采样界定与插值连续界定分列。
* 配对：细化对照不得改符号、阈值、窗口、参考电流，改了记 `REFUSED_CONTEXT_CHANGED`；
  收敛必须同时给绝对差（C/fC），只报 `CONVERGED` 不算答案。

实现复用 DATA-7B 已接受内核 `scripts/dd1_d7b_measure.py`（`interp_pair:158`、`clip_window:174`、
`trapezoid:189`、`signed_areas:199`、`integrate:231`、`crossing:244`、`band_spans/
sustained_in_band:279-383`、`turn_off:410`、`tail_segment_max_abs:459`、`float_samples/
time_quantum_ps:118-155`），本轮只加八档特有的口径（阶梯双判、名义/DC 两种期望、状态映射）。
这些是**测量算法的验证**，不是电路性能：全部结果带 `SYNTHETIC_NOT_MEASURED`。

## 4 合成正反例（17 例，逐例见 `synthetic_cases.json`）

正例证明手算一致，负例先证明故障事实存在再要求具名拒收：C02 反接后 `Q=-1.875e-13 C`，
`abs()` 本可让它与正例一模一样，规则改为拒收；C03 把 deck 的 iprobe 端序换掉，deck 审计按语句行
（不是注释里的字符串）点名拒绝；C04 尾段 `+0.5 µA` 与 `-0.5 µA` 净电荷为 0 仍不过漏流判据；
C06 非均匀样点边界插值等于手算 `1.375e-13 C`；C08 的 NaN、重复时间、倒退时间、空样点表与
"没有真实沿"各自按名拒收；C09 提前离带不得记 `SETTLED`；C11 八档全体减半时比例判据通过而绝对
判据失败，总判 `FAIL`；C12 少给 `000` 档的阶梯被拒收；C13/C14/C15 细化例丢掉前七段平台、改掉
使能电平、少一组换码，都被日程表闸点名。

## 5 覆盖、额度与差异

15 例 = 8 DC + 4 瞬态 + 3 细化，全部 `NOT_RUN`；每例计划 1 个 DUT 进程 + 1 个 preflight 进程，
合计 15 + 15 + 6 余量 = 36 次草案，本轮授权仍为 0，且未来任何启动（含 `-h`、失败、崩溃、调试）
都计入总额，`REQUESTED` 执行前占额、恢复不退额。§9 的机器表给出逐例清单与门表。

与已交付 R2 字段的 5 处不一致登记在合同 `differences_vs_R2`（§7）：夹持扫描步长在机读表与 deck
草稿里不同（0.05 V / 0.1 V）、`TON` 在 deck 里是 4 µs 而日程源按 1000 ns 用、短脉冲注记
"每 120 ns 槽两个脉冲"与平台列的 120/200 ns 不一致、`TR-LONG` 首平台从 t=0 就导通、
"120 ns 窗"同时指平台与内缩后的积分窗。本轮**保留建议值**、给出差异与自己的做法，
不改旧报告说"历史本就一致"。

## 6 零修改与继承的信息项

相对 R2 的 `H..tip` 只新增本轮允许路径；R2 全部跟踪路径、四份候选 DUT、共享工具与安全闸脚本、
以及全部既有证据目录（含上一轮那枚被判 FAIL 的记录）在 blob 与 mode 上逐条相同
（`frozen_comparison.csv` 的 enforced 行求和为 0）。`git diff --check` 在 `R2..HEAD`、`T..HEAD`、
`B..HEAD` 三个真实提交区间都 rc=0。

`scripts/netlist_stats.py --check` 在本轮树与 R2 只读提取里给出**同样 11 条** `PROBLEM`
（`DEVICE_COUNT_CHECK: FAIL` 两侧一致），是上一轮已按 `INFORMATIONAL_NOT_PASS` 登记的既有范围限制，
本轮不顺手处理、也不把它算成通过。

## 7 还差什么才能启动（不由执行者给 GO）

1. R2 的独立复审结论与用户对 R2 的接受决定；本轮不登记接受版。
2. 本合同由审核冻结：名义/DC 两种归一取哪一种作 PASS 判据、0.5 LSB、0.25 Iunit_ref、0.15 µA、
   0.01×QLSB、±5% 与 10 ns、以及 §7 五条差异的裁定。
3. 原生执行源码的 SHA、总额 36 次的授权、以及本机**只读**环境核验范围（模型卡身份、`tt`+`stat_noise`
   的 include 组合、层级 `save` 与 `type=pwl` 两条未证语法先用探针确认）。
4. 缺任一项，本任务书不构成启动令牌。

## 8 本轮自己的缺陷（按实登记）

* 日程/合同/deck 三处首版各有真实错误：`'50%'` 未转义导致 `%` 格式抛 `TypeError`、
  refined 例的伙伴映射取错来源（复制出 0 条窗口行）、按 `signal` 分组把三位 PAM 当成同一节点、
  窗口计数比较把字符串和浮点比（导致每条窗都"失配"）、以及一个占位残留判断。
  全部由本轮自己的 `--emit/--check` 拒发布或 `D7C_B_PREP_CASES` 报 MISS 暴露，未进入已发布记录。
* deck 审计最初用子串判断探针端序，被注释里引用的正确字符串"掩护"过一次；C03 报 MISS 之后改成
  只匹配非注释语句行。这同样是"检查器自己看不见自己的错"这一类，记在这里而不是删掉。

## 9 机器写入的表（由 `scripts/dd1_d7c_b_prep_verify.py` 从记录渲染）

### 9.1 门与命令

<!-- BEGIN 7CB GATES -->
<!-- END 7CB GATES -->

### 9.2 15 例清单

<!-- BEGIN 7CB DECKS -->
<!-- END 7CB DECKS -->

### 9.3 合成正反例逐例

<!-- BEGIN 7CB CASES -->
<!-- END 7CB CASES -->

### 9.4 冻结面与 Git 区间

<!-- BEGIN 7CB FROZEN -->
<!-- END 7CB FROZEN -->

## 10 停止状态

```text
TASK_ID=DATA-7C-B-PREP
BASE_SHA=3e4703f1763223024f442c0826e95055782bca13
CONTRACT_STATE=PROPOSED_FOR_REVIEW
R2_INDEPENDENT_ACCEPTANCE=NOT_GRANTED_BY_THIS_TASK
CANDIDATE_DUT_NETLISTS_CHANGED=NO
EXISTING_TRACKED_PATHS_MODIFIED=0
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
PWM_PAM_CURRENT_INTEGRATION=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
GRAY_LUT=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW_OF_NATIVE_PREPARATION
```
