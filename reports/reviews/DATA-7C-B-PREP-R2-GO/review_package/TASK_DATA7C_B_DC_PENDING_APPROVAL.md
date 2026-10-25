# DATA-7C-B-DC：八档PAM单输出TT直流实测（待用户批准）

You have NO access to the user–ChatGPT conversation. Your complete sources are this task brief, the accompanying independent-review package, the pinned repository and the user's explicit approval attached to this task. This document alone does not authorise native execution.

**本文件是可审阅的执行方案，当前未获原生授权。** 只有用户明确接受所列离线版本、批准本任务及Spectre总上限20次后，才可登记授权、读取本任务所需本地模型和进入guest。批准后，范围内的实现、SSH传输、只读检查、预检、实测与安全推送连续完成，不再逐个动作重复询问。

```text
TASK_ID=DATA-7C-B-DC
AUTHORISATION_STATUS=PENDING_USER_APPROVAL
CURRENT_GRANTED_SPECTRE_LIMIT=0
PROPOSED_SPECTRE_LIMIT=20
PROPOSED_DUT_RUNS=8
PROPOSED_NATIVE_PREFLIGHT_RUNS=8
PROPOSED_DEBUG_MARGIN=4
```

## 1. 固定来源与目标

| 对象 | 固定值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 建议接受的离线内容 | `e51c5320a28bd5043e21d08a0be97e9d5612cd16` |
| 离线分支 | `poc/data-pam-d7c-b-prep-r2` |
| 前轮R1 | `6778535e70b139812265eba490d0a1381a1fae5c` |
| main保持 | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 新分支建议 | `poc/data-pam-d7c-b-dc` |

目标：**同一个数据下拉输出通道，依次施加八码，测八个静态电流档及输出夹持扫描。** 不是八个LED通道，不扩1024×768阵列，不做瞬态PWM/PAM联合验证。

四份候选主文件继续冻结：

```text
spectre/dd1_d7c_a_gates.scs
spectre/dd1_d7c_a_pam_dec.scs
spectre/dd1_d7c_a_sink_unit.scs
spectre/dd1_d7c_a_pam_top.scs
```

原理：八码温度计译码选择1–8条单位恒流下拉支路，全部接同一data_out。Mref为20µm/2µm，单位Mcas/Mout为2.5µm/2µm，参考15µA，候选名义单位电流1.875µA。这是估算，真实值正是本轮要测的。

Data接LED N侧、Scan PMOS高侧接P侧；不因行列命名对调极性。PAM000是最低非零档，DATA_EN=0才全关。

## 2. 批准前与批准后的动作边界

批准前只能阅读本任务、复审包和已有仓库，不启动Spectre（包括-h）、其它仿真器、RTL、OA、动态preflight；不进入SSH/VM，不读本地凭据/模型卡。若只收到本待授权文件，记录PENDING并停止，不能自行填“用户已批准”。

用户批准本任务后，允许：

- 从固定SHA新建独立worktree，在新分支登记 `e51c532…` 为限定离线接受内容；只登记PAM候选及离线准备范围，不把其它历史轮次补成GO，不合并main。
- 通过已有桥和SSH通道，把本轮新deck/脚本送入guest的新运行目录，并取回本轮输出。
- 只读核验本任务所需模型身份、tt包含关系、器件几何支持和运行环境；PDK/模型卡/许可证内容不入库。
- 本轮最多20次Spectre进程启动，包含所有preflight、DUT、帮助、语法探针、失败、崩溃及调试。

始终禁止：OA读写任务/原理图改写、RTL仿真、瞬态模拟、修改DUT拓扑或W/L、修改PDK/license/密码、VM电源/快照操作、网络配置变更、force、跳hooks、GC、改历史、改变仓库可见性或推main。

已有密钥优先，运行时确需读取现有凭据配置时，只由既有桥加载，禁用命令回显；不得cat/grep打印凭据文件或把敏感值放进命令行、报告、JSON和日志。使用了运行时凭据加载就如实记录，不称“凭据读取0”；不自行改密码。

guest写入仅限 `/root/microled_ai_project/` 下本轮新建的独立运行目录；本任务获批即包含该明确路径范围的写入授权。桥基础设施不改，其他工程和运行目录不动。通道或许可不可用时只读定位后停止，不自动改网络或许可服务。

## 3. 必须先读并离线完成的准备

读根AGENTS.md、README.md、配套GO报告、`reports/tasks/DATA-7C-B-PREP-R2.md`、当前合同/日程/八份DC deck、候选四主文件及共享参考/反相器。

读已接受的 `scripts/dd1_d7b_run.py`、`dd1_d7b_measure.py`、`spectre/current_probe_syntax.scs` 及 `scripts/run_spectre.sh`；复用其已证原语、探针读数和运行原则，不复制其56次额度或59次历史种子，不改旧工具。

先正常回读源分支和main，记录完整SHA、UTC与rc；远端若有新提交，不无声吸收。新建worktree不覆盖已有目录。

本轮新增一个小型DC执行/提取入口即可，不新建通用SPICE解释器、事务发布框架或庞大突变平台。离线先验证：八码源电平/位序、19点网格、探针方向、供电与温度语句、结果解析的单位/缺点拒收、记账与未授权拒收。形成可追溯的执行源码提交后，在同一已批准任务内实测；无需把正常阶段再拆成多轮“先交工具”。

可同轮修正唯一非阻断笔误：`dd1_d7c_b_prep_contract.py` 渲染表中最后的 `value uA` 改为 `value*1e6 uA`，仅重渲染对应Markdown。JSON参数和电气算法不变，不为它单开DOC轮。

## 4. 本轮DC条件与判据（获批后即按此执行）

| 项目 | 条件 |
|---|---|
| 工艺/角/温度 | 已有SMIC18模型族，TT，27°C；精确模型身份先本地只读核验 |
| VDD18/VCAS/VSS | 1.8V / 1.8V / 显式0V |
| 外部Iref | 15µA注入二极管连接参考节点；不使用理想VBIAS替代 |
| DATA_EN | 静态1.8V，不能复用起始为0的脉冲源 |
| PAM位 | pam0=权重1、pam1=权重2、pam2=权重4；低0V、高1.8V |
| 输出夹持扫描 | 0.60–1.50V，步0.05V，共19点；1.20V必须是实际扫描点 |
| 探针 | `Ip_branch (clamp_node data_out) iprobe`，I_sink=Ip_branch，正方向为流向下拉支路 |
| 主评价点 | clamp=1.20V |
| 满量程 | I111为14.25–15.75µA，即15µA±5% |
| 八档比例 | Iunit_ref=I111/8，同一参考贯穿全表；每档偏差 `Ik-(k+1)*Iunit_ref` 不超过0.25个Iunit_ref |
| 顺序 | 八码电流严格单调增加 |

名义阶梯是1.875、3.750、5.625、7.500、9.375、11.250、13.125、15.000µA，身份仍为ESTIMATED_MIRROR_RATIO_ONLY。必须同时满足满量程绝对值和八码比例，不能用归一化掩盖全体电流偏小。

主判据只作用于1.20V；低夹持点电流下降应保留，不能把整段扫描都强行判PASS。另按每码相对其1.20V电流变化不超过±5%，给出包含1.20V的连续已测区间、最低已验证扫描点和相邻未通过点，不外推成更精确边界。该范围不等于实际LED/电极RC或SOA已验证。

## 5. 预检与原生派生文本

原15份PREP deck和候选主文件全保留。运行副本放在 `spectre/dd1_d7c_b_dc/` 或本轮新staging。

原子电路里的 `parameters <端口> input/output/inputOutput` 是端口方向标注；若与原生Spectre不兼容，只允许在派生include里精确剥离这些标注行。真实参数、端口顺序、D/G/S/B、模型、W/L、共享/局部节点必须逐项与冻结主文件一致，写出来源SHA和剥离清单，不编辑主文件，不重新画电路。

运行副本使用本项目已经验证的 `simopt options temp=27` 和有实例名的 `dc_case dc ...`。每个VSS显式接0。PDK包含通过运行时环境变量解析，本地核验tt及所需附属section，模型卡内容/专有路径/许可证信息不复制进仓库。

只读核验实际模型是否支持n18/p18/n33/n33_dnw_4t_ckt与所用尺寸。尺寸非法、缺模型或包含关系不能确认时，停止；不为通过私自换工艺、换模型、改W/L或电源。

每例preflight验证实际静态源、码位、电平、温度和探针符号。可复用既有供电预检方式，或在DUT替换为理想仪表负载的副本中使用：输出80kΩ在1.20V时应读+15µA；参考节点50kΩ配15µA注入时应为0.75V。阻值和预期均是仪表见证，不是PAM DUT结果。预检采用与本例相同的19点夹持扫描和源连接；读取源电平与输出，不能只看rc=0。

层级save先沿用准备版本。若本build不支持某个可选内部观察项，允许在运行副本移除该项并如实标NOT_OBSERVED；I_sink、data_out、实际供电/使能/PAM位及参考条件是必需。缺少内部en/vbias观察时，不声称逐支路内部状态已被原生确认。不得为观察而改变DUT拓扑。

## 6. 启动预算：先两端档，再补中间八码

建议执行顺序：DC-000、DC-111先行，每例preflight通过后才跑DUT；环境与提取链确认后，再跑001、010、011、100、101、110。端档正常不意味着中间档可以省略。

授权上限若为20：8 preflight + 8 DUT =16，另4次余量用于语法/调试/失败重试。20是本阶段总额，不是免费余量叠加；旧36次草案、DATA-7B 59/56和未来瞬态额度均独立，不互借、不追认。

每次启动前先持久登记REQUESTED，绑定task_id、case_id、preflight/DUT/debug、run_id、源SHA和序号，再启动进程。失败、帮助、崩溃、被终止、未取回结果的REQUESTED都占额，不退额；只做文件解析或静态检查不占Spectre额。

使用本任务专用账本，保持单执行器和明确锁；不使用会覆盖历史行的共享CSV，不直接调用旧56次硬编码账户。能复用已接受的纯函数就复用，新增账本只需保证先占额、追加留痕、恢复不退额及不得超过20，不开发新交易平台。

每次运行保留唯一目录；核对guest实际Spectre日志/进程启动与账本，底层多起一个Spectre也要计一次。若剩余额度不足完成必需剩余例，保留PARTIAL并停止。每个实质问题最多三次修补；不得自动提额度或反复弹询问用小额补齐。

## 7. 输出、提取与判定

预检与DUT分开。正式矩阵应为8个码×19个输出点＝152条唯一数据，不把debug或预检的理想负载结果计入。

逐点保存：case/码/夹持电压、实际data_out、带符号I_sink、实际供电与逻辑输入、Iref条件、角/温度、deck摘要、原输出摘要、run_id和进程序号。必须来自原生输出，不复制名义阶梯填表。

时间域QLSB不适用于本DC扫描，不生成“0.5LSB电荷PASS”。正负方向事先固定；负数如实诊断，不取abs翻正。NaN/Inf、缺点、重复点、单位缺失、1.20V点缺失、原输出与deck身份不一致都不得发布为完整PASS。

1.20V八码总表独立复算：绝对满量程、严格单调、共享I111/8及各码偏差；给出数值，不只写PASS。扫描曲线和比例表分开，绘制实际I–V曲线和八码阶梯，轴标V/µA。

若电流目标不满足，保留FAIL和原始结果，分析可能原因；本轮不调W/L、不替换候选以追PASS。若语法成功而电气失败，分别写清。成功级别最多为NATIVE_PAM_DC_TT_MEASURED，不能写PAM/PWM联合、光学9bit、版图或SOA完成。

## 8. 允许文件、证据与交付

新增范围：`scripts/dd1_d7c_b_dc_*.py`及必要新runner、`spectre/dd1_d7c_b_dc/`及派生include、`tests/dd1_d7c_b_dc/`、全新 `results/evidence/dd1_d7c_b_dc_<run_id>/`、本轮任务/合同/报告与 `reports/agent_handoffs/DATA-7C-B-DC.{md,json}`。

现有文件仅允许第3节所列单位渲染器和其Markdown的说明性修正；旧合同JSON、四DUT、原15deck、旧时序表、共享工具和旧证据全部冻结。

原始输出本机保留；远端提交经安全检查的deck、提取数据、统计、图与可复算摘要，不含PDK/模型卡/工具二进制/凭据/许可证内容。摘要不能替代必要的实际数值样本。新跟踪产物控制32MiB内，不删旧记录腾空间。

记录真实命令和rc、每个进程成本、失败尝试、环境/模型逻辑身份、实际source/deck/output对应、未观察项与PARTIAL/FAIL。没有执行的不称PASS，原生语法也只对实际跑过的派生DC deck确认，不外推到全部层级或瞬态。

提交前按原规则安全检查；常规push新分支后回读同一对象，旧分支/main不动。不让旧轮次的硬编码CLI迫使本轮重建记录平台；旧记录按原固定SHA解释，新证据能被独立重算即可。

审核包从最终Git blob构建，包含任务、用户批准记录、限定接受登记、DC合同、必要源/只读依赖、152条实际数据或真实PARTIAL、8档结论、账本对账、图和清单。仓库外重放提取/数值复算；ZIP摘要只写包外，不自指、不覆盖旧包。

完成后停在独立审核闸，不自行合并、不进入瞬态。最终回执明确：

```text
TASK_ID=DATA-7C-B-DC
BASE_OFFLINE_CONTENT_SHA=e51c5320a28bd5043e21d08a0be97e9d5612cd16
SPECTRE_LIMIT=20  # 仅在用户明确批准后生效；否则仍为0
ACTUAL_SPECTRE_LAUNCHES=<全部实际启动，含失败和调试>
PAM_8LEVEL_DC_TT=PASS_or_FAIL_or_PARTIAL
COMPLETION_LEVEL=NATIVE_PAM_DC_TT_MEASURED_or_ACTUAL_LOWER_LEVEL
CANDIDATE_DUT_CHANGED=NO
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
PWM_PAM_TRANSIENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
