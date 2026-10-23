# DATA-7C-B-PREP：八档 PAM 实测准备任务书

You have NO access to the user–ChatGPT conversation. Your complete sources are this task brief and the named repository at the pinned commits. A plan, an executor PASS, or a proposed launch budget is not native-execution authority.

请完成八档 PAM 原生验证的离线准备，让下一次审核可以直接检查电路、激励和电气判据。保留四份候选 DUT，准备单输出最小单元，不扩展到上千通道。完成后推送独立分支，停在独立审核闸。

本任务允许准备新的方案、deck 文本和离线测量代码；不授权原生运行、接受登记或合并。不要把本任务改成另一轮通用工具平台建设。

## 1. 固定来源与当前状态

| 对象 | 固定值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 本轮任务 | DATA-7C-B-PREP |
| 工作基线 R2 | `3e4703f1763223024f442c0826e95055782bca13` |
| R2 分支 | `poc/data-pam-d7c-a-r2` |
| R1 对照 H | `da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb` |
| 原 A 对照 T | `89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79` |
| DATA-7B 接受内容 | `f9fd09b184a69a27cdb409205dfd4f4151408a23` |
| DATA-7B 登记基线 | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` |
| DATA-7A 接受内容 | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| main 保持 | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 本轮新分支建议 | `poc/data-pam-d7c-b-prep` |

R2 仍处于 `AWAITING_INDEPENDENT_REVIEW`，没有接受登记，也没有原生授权。审核端已在固定 R2 字节上重放：离线检查 34 项、反例 65 项、正式记录复核，均通过；这些只是进度核验，不代表 R2 完整独立复审 GO。

本任务不允许执行者自审后宣布 R2 接受。可以在 R2 复审未完成时做本轮离线准备；后续原生阶段必须另有 R2 审核结论、用户接受决定及明确启动授权。

```text
NEW_SPECTRE_LAUNCH_LIMIT=0
NEW_RTL_SIMULATION_LIMIT=0
NEW_OA_WRITE_LIMIT=0
NATIVE_PREFLIGHT_AUTHORISED=NO
SSH_OR_VM_ACCESS_AUTHORISED=NO
PDK_OR_CREDENTIAL_ACCESS_AUTHORISED=NO
ACCEPTANCE_REGISTRATION_AUTHORISED=NO
MERGE_OR_MAIN_PUSH_AUTHORISED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
```

这里的 0 包含 `spectre -h`、语法试跑、动态 preflight、失败启动、旧波形重跑及其它仿真器。纯 Python 文本生成、合成样本测量、自测及 Git 读取可执行。

## 2. 开工核验与必读材料

先读根 `AGENTS.md`、`README.md`，再读：

- `reports/tasks/DATA-7C-A.md`、`DATA-7C-A-R1.md`、`DATA-7C-A-R2.md`；
- `reports/dd1_d7c_a_pam_candidate.md`、`dd1_d7c_a_native_test_plan.md`、`dd1_d7c_a_review_fix_r2.md`；
- `reports/agent_handoffs/DATA-7C-A.md` 与同名 JSON；
- `scripts/dd1_d7c_a_r2_plan.py`、`dd1_d7c_a_r2_sign_check.py`、`dd1_d7c_a_r2_record_check.py`；
- `scripts/dd1_d7c_a_netlist.py`、`dd1_d7c_a_offline_check.py`、`dd1_d7c_a_deckgen.py`；
- `tests/dd1_d7c_a/` 中黄金表、请求表、计数声明表及原生计划表；
- 四份候选 DUT、bench 草稿及 `spectre/current_probe_syntax.scs`；
- DATA-7B 的 runner、measure 和已接受报告中有关电流方向、插值积分、关断尾段、收敛与启动记账的内容。

用独立 worktree 从固定 R2 SHA 开分支。先记录原始分支和 main 的 full SHA。能用 Git 协议和 API 时，回读同一查询对象，分别保留 UTC、rc 和完整 SHA；一路不可用如实标记，不称为双路已验证。

不要重复修已经关闭的缺口，不要重新生成旧证据。若发现 R2 存在新的实质问题，只写新的定位记录并隔离相关准备项；不要在本分支修改 R2 源码或旧记录。

R2 明确保留的通用 CSV 形状读器不承担记录语义判决，真实判决由新的 `dd1_d7c_a_r2_record_check.py` 承担；旧仪器对应一例仍 reproduced 是上轮任务允许的接口分工，不能只据此再开一轮返修。

## 3. 电路边界：一个输出、八条单位支路

四份正常候选 DUT 必须与 R2 的 blob 和 mode 完全一致：

```text
spectre/dd1_d7c_a_gates.scs
spectre/dd1_d7c_a_pam_dec.scs
spectre/dd1_d7c_a_sink_unit.scs
spectre/dd1_d7c_a_pam_top.scs
```

电流路径保持：LED 的 N 侧接 Data 恒流下拉，Scan 的 PMOS 高侧接 LED 的 P 侧。不能为统一行列称呼对调极性。

候选包含八条单位下拉支路、一个共享参考及唯一 `data_out`。`data_en=1` 时导通数为 `pam_sel+1`；`data_en=0` 时全部关断。PAM 码 000 是最低非零电流档，不能把它当黑码。

共享 Mref 为 20 µm/2 µm，单位 Mcas/Mout 为 2.5 µm/2 µm。以 Iref=15 µA 按几何比估算，单位支路为 1.875 µA。Mpass/Mbleed 不在本轮重新缩放。

| PAM 码 | 导通支路数 | 候选名义电流 / µA |
|---|---:|---:|
| 000 | 1 | 1.875 |
| 001 | 2 | 3.750 |
| 010 | 3 | 5.625 |
| 011 | 4 | 7.500 |
| 100 | 5 | 9.375 |
| 101 | 6 | 11.250 |
| 110 | 7 | 13.125 |
| 111 | 8 | 15.000 |

这些数值的身份均为 `ESTIMATED_MIRROR_RATIO_ONLY`，不是已测电流，也不因此成为正式产品规格。145 MOS 等计数由实际解析结果引用，不手抄为新的实测结论。

本轮不做完整 MOS 灰阶控制器、不接入整套 RTL 控制、不做 LUT/TCON/阵列/版图。6 bit PWM + 3 bit PAM 是控制字结构，不能写成已经实现 9 bit 光学有效灰阶。

## 4. 输出一份可审核的电气合同草案

新增 `tests/dd1_d7c_b_prep/contract.json`，作为本轮参数和判据的唯一来源，再由它渲染报告和 deck。状态固定为 `PROPOSED_FOR_REVIEW`，不是 `USER_APPROVED`。

以下是本任务提供的 POC 建议值，执行者不得看过仿真结果后调整。若离线即发现矛盾，保留建议值并给出具体差异，等待审核；不要默默改动。

| 项目 | 建议值与判读方式 |
|---|---|
| 工艺角与温度 | SMIC18 已有模型族的 TT、27 °C；本轮不读取模型卡，确切本地模型身份留给获批原生阶段核验 |
| VDD18 / VCAS / Iref | 1.8 V / 1.8 V / 15 µA 外供；VSS 显式接 0 |
| 主评价输出夹持 | 1.2 V，继承 POC 条件；不代表实际 LED、VLED 或最终 SOA |
| 输出夹持扫描 | 0.60–1.50 V，步长 0.05 V；1.20 V 必须是实际扫描点 |
| 满堂绝对电流 | 码 111 在 1.2 V 时为 15 µA ±5% 的候选可行性目标 |
| 八档比例 | 定义 `Iunit_ref=I111/8`；逐档报告 `Ik-(k+1)*Iunit_ref`，建议绝对偏差不超过 0.25 个 Iunit_ref，且八码严格单调 |
| 关断漏流 | 每个明确关断尾窗的末 100 ns，`max(abs(I_sink)) <= 0.15 µA`；正负方向都不能掩盖 |
| 细步长配对 | 先沿用 R2 普通 2.0 ns、细化 0.1 ns；完整激励历史相同，只改变 maxstep |
| 收敛建议 | 对同一窗口，细化与普通步长的 `abs(dQ)/QLSB <= 0.01`；同时给绝对差，不能只报 CONVERGED |

八档相对比例通过不能代替 15 µA 绝对电流通过；不得把全部电流偏小一半的结果用归一化“校正”成合格。扫描中不合格的低夹持点应保留，以提取候选合规电压范围，不要求整段扫描都满足主夹持点判据。

为后续短窗比较提出独立的归一单位：

```text
Iunit_nominal = 1.875e-6 A
Ttick_nominal = 120e-9 s 或 200e-9 s，分别注明对应测试计划
QLSB_nominal = Iunit_nominal * Ttick_nominal
             = 2.25e-13 C 或 3.75e-13 C
```

单位换算必须有手算对照：1.875 µA = 1.875e-6 A = 1.875e9 fA。不得从合成符号测试的任意数值尺度直接复制成物理电流。

正式电流归一建议使用同一条件 DC 扫描得到的 `I111/8`，同时保留名义单位的结果；采纳哪一种作为后续 PASS 判据，必须在原生授权前由审核冻结。本轮结果列仍全部为 NOT_RUN，不能用合成样本填入电气结果。

## 5. 准备 15 例 deck，保留 R2 覆盖意图

只生成文本，不调用仿真器。保持 8 DC + 4 瞬态 + 3 细化的覆盖结构：

| 类别 | case_id | 必须覆盖的内容 |
|---|---|---|
| 8 个 DC | DC-000 至 DC-111 | DATA_EN 静态 1.8 V，八码一一对应，输出夹持扫描；记录所有使能和局部偏置节点 |
| 长窗 | TR-LONG | 八个电流档各一个平台，关态换码；所有平台和所有关断窗分别测量 |
| 最低档短窗 | TR-120、TR-200 | 码 000，保留两种短窗；导通和尾段都测，不删未稳定结论 |
| 关态换码 | TR-OFFCODE | 完整覆盖 011→100 与 000→111，两组导通及其间关态都保存，不只量第二个平台 |
| 三个细化配对 | RS-LOW、RS-FULL、RS-SWITCH | 分别对应 TR-120、TR-LONG、TR-OFFCODE；RS-FULL 保留之前七段历史 |

以 R2 单一计划源的相对时刻为输入，生成本轮明确的结构化 PWL 点表。允许为瞬态统一增加 1 µs 初始关断预备时间；所有相关平台、换码点、积分窗与结束时刻整体平移，必须记录偏移量。初始码在首次使能前稳定，不把 t=0 已经为高的状态识别成上升沿。

逐例给出：供电、DATA_EN 形态、三个 PAM 位、初始关断、有限上升/下降沿、换码时刻、PWL 包络起止、平直段、50% 有效使能起止、积分窗、尾窗、stop、maxstep 和配对来源。不能继续只写“120 ns 平台”而不区分它指哪两个时刻。

从同一份结构化数据导出这些信息。验证：时间有序、平台不重叠、换码完全处于关态、八码覆盖、尾窗足够长、细化配对除 maxstep 外条件一致。若 R2 自然语言和数字仍有差异，本轮列出差异，在新合同中明确解释，不能修改旧报告后声称历史本就一致。

DC 不能复用起始为零的脉冲源来代替静态 DATA_EN。每个供电网络显式连接电源；输出夹持源与参考电流源在 bench 层，不写进 DUT。PDK include 只保留环境变量占位，不复制模型卡。

层级 save、PWL 拼写与原生语法的状态一律为 `NOT_VERIFIED`。可以参照已接受项目写法做离线检查，但不能因此称“已通过 Spectre 语法”。若为未来原生兼容需要剥离方向标注等，只生成派生文本并提供映射，不编辑冻结主文件。

## 6. 测量方法先写清，不能看波形后换口径

固定探针：`Ip_branch (clamp_node data_out) iprobe`，定义 `I_sink=Ip_branch`。物理正方向为夹持源经探针进入下拉支路再到 VSS。真实负电流保留负号，禁止对原始电流或总电荷取绝对值来翻正。

注意：关断尾流可能为正，也可能为负，不能预先把“尾段”写成“负面积”。单独计算每个窗口的有符号 Q、正面积 Qpos、负面积的幅值 Qneg，验证 `Q=Qpos-Qneg`。关断判据可使用 `max(abs(I))`，但不得把有正负反冲的尾段相消后写成零漏流。

实现小型离线测量函数，输入带单位的时间、电流及使能样本，至少完成：

1. 严格读取有限数值、时间严格递增；不把原生自适应采样点强制取整到 ps 网格。
2. 用相邻点和插值寻找使能 50% 上升/下降沿；无真实沿则明确拒收，不能回退到窗口终点。
3. 对积分边界插值，用实际时间加权梯形积分；遇过零点分段得到 Qpos/Qneg。
4. 同时保留完整使能窗 Q 和平直段平均电流，不能只剪掉开头误差后称整个短窗通过。
5. 分别计算 `Qexpected_nominal=Inominal(k)*T50` 与 `Qexpected_dc=IDC(k)*T50`；没有 DC 原生值时后者为 NOT_RUN，不能用几何比冒充 IDC。
6. 以所声明 QLSB 报告两种电荷误差；候选建议限为 0.5 LSB，但只作为待审判据，不在本轮宣称已满足。
7. 对进入并持续处于 ±5% 电流带作插值判定；需满足的持续时间建议为 10 ns。必须检查 deadline 前已离带的情况，未达条件就保留 `NOT_SETTLED_WITHIN_PULSE`。
8. 关断采样时刻与插值阈值时刻分列，尾窗末 100 ns 单独核对；同一窗口的 refined 对照不得改变符号、阈值、边界和参考电流。

这里验证的是测量算法，不是电路性能。合成样本输出明确写 `SYNTHETIC_NOT_MEASURED`；不得混进未来原生结果表。

## 7. 少量但有效的正反例

使用手写、可手算的合成样本和临时文本副本，不调用旧仿真重跑。优先复用已接受的解析与积分方法；不要另建通用 SPICE 解释器、事务发布框架或新的庞大突变平台。

必须证明以下失败会被对应规则拒收，而非只有 rc 不为零：

- 正常下拉与真实反向电流能区分；翻转探针连接不能靠 abs() 通过。
- 一段正/负尾流的总 Q 接近零，仍不能通过关断判据。
- 非均匀采样与边界落在两点间的样本，积分结果符合手算；NaN、重复/倒退时间和无真实沿被具名拒收。
- 曾进入带宽但在 deadline 前已离带，不能误判 SETTLED。
- 全部八档缩小一半，即使相对比例正确，绝对电流检查仍失败。
- 码 000 在 DATA_EN=1 时有一条支路，DATA_EN=0 时全关；不能拿 PAM000 代替黑码。
- 细化配对若换掉早先七段历史、漏掉一组换码、或同时改了供电，不能记为同条件收敛。

每个负例先证明被注入的故障事实存在，再检查诊断内容。期望失败集合非空且逐项匹配，不允许两个空列表相等就算检出。对于已有相关测试，只补本轮需要的覆盖，不以增加测试数量作为交付目标。

## 8. 原生启动额度只提出草案

建议下一次原生阶段总上限为 36 次：15 个 DUT + 15 个供电/激励 preflight + 6 次语法、调试或收敛余量。此处的 36 次没有得到授权，本轮可用原生额度仍为 0。

在合同中列出每例计划需要的进程，不仅写“15 例”。未来所有启动都计入总额，包括 `-h`、失败、被终止、崩溃和调试；REQUESTED 必须在执行前占额，恢复不能退额。preflight 与 DUT 分开计数，不能把失败当免费。

不用本轮实现新的生产级账本。可以引用 DATA-7B 已有记账纪律及需要绑定的新任务身份；不得运行原生入口“测试一下它会不会拒收”。不读取 guest、凭据或模型文件来补环境字段。

未来启动还需要审核冻结：R2 接受版本、合同 SHA、执行源码 SHA、电流/电荷判据、原生总额度和本机只读环境核验范围。缺任何一项都不能把本任务书当授权令牌。

DATA-7B 历史 59/56 超支 3 次继续为 `VIOLATED_NOT_RETROACTIVELY_AUTHORISED`，不能借用、重置、抵扣，也不把这个历史 FAIL 改绿。

## 9. 允许路径与冻结范围

本轮只新增，不修改 R2 已有文件。允许新增：

```text
reports/tasks/DATA-7C-B-PREP.md                 本任务书逐字节副本
reports/dd1_d7c_b_prep_contract.md             电气合同草案与待审取舍
reports/dd1_d7c_b_prep_report.md               准备结果、差异、失败与来源
reports/agent_handoffs/DATA-7C-B-PREP.md
reports/agent_handoffs/DATA-7C-B-PREP.json
scripts/dd1_d7c_b_prep_*.py                    小型生成/测量/复核脚本
tests/dd1_d7c_b_prep/                         合同、日程、合成正反例
spectre/dd1_d7c_b_prep/                       15 个新 deck 文本及必要派生 include
results/evidence/dd1_d7c_b_prep_<new_run_id>/  本轮独立离线证据
```

不修改已有 DUT、共享工具、安全规则、PDK、模型卡、许可证、旧交接、旧报告或旧证据目录。原有三个 R3 非阻断待办、凭据回显事件、已删除四个中间目录的事实保留，不在本轮顺手处理。

遇到必须修改冻结文件的情况，给出路径、原因和最小差异后停止相关项，不自己扩围。每个实质问题最多三次修补尝试；失败记录原样保留，不删已发布目录再重做。

## 10. 交付与外部审核

完成后应能在不连接 guest、不安装 EDA 工具的全新提取目录中：

1. 读取合同，重建 15 个 deck 的文本及其日程映射；所有电气结果仍为 NOT_RUN。
2. 重放合成测量正反例，得到具名、可手算的结果；验证单位和符号。
3. 核对 15 例覆盖、三对 refined 完整历史、DC 八码，以及 30+6 的未来启动计划。
4. 证明相对 R2 为零修改、零删除；四份 DUT 和原有所有路径 blob+mode 不变。
5. `git diff --check <完整R2 SHA>..<最终tip>` 通过，检查真实提交范围，不只看工作树。

报告用清楚的电路和测量语言，说明还差什么才能启动。不要把重点写成工具调用次数，不用长篇“全绿”替代未测项目。

从 Git blob 构建小型、自包含审核包，含任务书、合同、脚本、15 个 deck、必要只读依赖、离线结果及清单；不要把整个 7B 历史波形包重复塞入。本轮新增跟踪产物控制在 32 MiB 内；若超限先报告，不删旧产物腾空间。

新包必须在仓库外实际重放，缺 Git 历史的项目标 NOT_RUN，并与有历史环境的验证分列。清单列出成员摘要和字节数，报告不写自身摘要，ZIP 摘要只记在包外。用尽量少的载荷/交接提交完成，不追逐自指 SHA。

按既有规则运行提交与推送安全闸，正常 push 新分支，再回读同一远端对象。禁止 force、跳 hooks、GC、改写历史、改变仓库可见性、合并或推 main。发现旧 objects 扫描 FAIL 时如实保留，不为了本轮通过加豁免。

最终回执至少给出：完整基线、payload SHA、tip SHA、实际变更路径、合同状态、15 例清单、合成测试结果、包名和包外摘要、远端回读、未完成项。

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

交付立即停止。执行者不给自身 GO，不登记 R2 接受版，不自行开始 DATA-7C-B 原生运行、联合电荷验证、LUT、TCON、阵列或版图。
