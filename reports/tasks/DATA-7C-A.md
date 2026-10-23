# DATA-7C-A：八档 PAM 单通道候选 MOS 电路与离线验证

You have NO access to the user–ChatGPT conversation. Your sources are this complete task brief, the named repository at the pinned commits, and the public references explicitly identified below. Do not infer missing specifications from earlier model messages.

你是本地执行 Agent。本任务采用“用户决策 → 本地 Agent 执行 → GitHub 提交与回读 → 云端独立审核”的流程。**本轮要交真实候选 MOS 网表、离线源码验证和下一轮可执行验证计划，不只交一篇方案综述。** 本轮不启动任何原生仿真，完成后停在独立审核闸。

## 1 目标、授权和固定起点

目标：承接已收口的 DATA-7A/7B，准备缺失的八档 PAM 电流幅度最小单元。只设计**一个电流下拉输出**；内部允许多个并联电流支路，不复制成384/512/1024个通道，不搭建显示阵列。

| 项目 | 固定身份 |
|---|---|
| 仓库 | `https://github.com/LINboss666/microled-ic-ai-lab` |
| 本轮分支基线 / 登记提交 | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` |
| 已被独立复审、登记接受的 DATA-7B 版本 | `f9fd09b184a69a27cdb409205dfd4f4151408a23` |
| 接受记录所在分支 | `poc/data-pwm-d7b-r3` |
| main，应保持不动 | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 已接受 DATA-7A 内容 | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| 新分支建议 | `poc/data-pam-d7c-a` |
| 任务 ID | `DATA-7C-A` |

用户把本完整任务转交给你，授权的是**这一轮离线候选设计与准备工作**。不是授权 Spectre、RTL 仿真、OA、VM、合并或后续 DATA-7C-B。不得修改旧交接里的 NEXT_STAGE_AUTHORISED=NO 来制造新授权。

开始前：

1. 用现有 Git protocol 与 GitHub API 通道回读固定基线、已接受版本及 main，记录查询对象、完整 SHA、UTC、命令 rc。用户提供的旧回执不能冒充本次回读。
2. 确认 `272d6de…` 的父为 `f9fd09b…`，登记轮只改两份交接、增加五份复审文档，核心源码与证据未改。
3. 新建隔离 worktree 与新分支；已有同名目录/分支不得删除、覆盖或 force。工作目录可按本机选择，例如 `D:\ic617_d7c_a`，路径只是例子。
4. 若远端比固定基线更新，先只读检查其范围；不要顺手吸收新代码或把其他分支混入本任务。不能确认身份则 BLOCKED，保留已做只读调查。

本轮硬预算：

```text
NEW_SPECTRE_LAUNCH_LIMIT=0
NEW_RTL_SIMULATION_LIMIT=0
NEW_OA_WRITE_LIMIT=0
NATIVE_PREFLIGHT_AUTHORISED=NO
SSH_OR_VM_ACCESS_AUTHORISED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
MERGE_OR_MAIN_PUSH_AUTHORISED=NO
```

`spectre -h`、试跑一遍看语法、动态 rail preflight、重跑旧波形，都是本轮不允许的操作。不要读取或回显凭据，不修改密码、PDK、license 或 guest 网络。

## 2 必须先读的文件与来源等级

优先读根目录 `AGENTS.md`、`README.md`；本任务更窄的“无 VM、无仿真、仅新增文件”约束适用于本轮。

随后至少读：

- `reports/agent_handoffs/DATA-7B.md` 的 §11/§12 和 `.json` 的 acceptance_registration、r3、待办。
- `reports/reviews/DATA-7B-R3/REVIEW_DATA7B_R3.md`、`review_summary.json`、`source_identity.json`。
- `reports/dd1_d7a_contract.md`，特别是 PAM 尚未定义、端口、码值、满窗及授权协议。
- `reports/dd1_d7b_contract.md`，特别是测量窗口、Ical/电荷/关断的区分及历史勘误。
- `reports/tasks/DATA-7B.md`、`reports/tasks/DATA-7B-R3.md`，理解旧冻结边界；不得为了新任务修改它们。
- `rtl/dd1_d7a_gray_ctrl.sv`、`spectre/dd1_d7b_pwm_stage.scs`。
- `spectre/dd1_d6_bias_core.scs`、`spectre/dd1_d6_sink_core.scs`、`spectre/dd1_d6_inv18.scs`。
- `spec/system_requirements.md` 中与电流和 U10 有关的条目。它是早期登记，有些状态已过时；不得拿“未做任何晶体管设计”等旧状态覆盖最新接受记录。

事实分层：

| 事实 | 等级与限度 |
|---|---|
| Data 接 N 极作恒流下拉，Scan 接 P 极作高侧开关 | 已有项目分工；本轮不改变方向 |
| 已接受数字接口为 Pure 8-bit 时间码、Hybrid 6-bit 时间码 + 3-bit PAM 请求码 | 冻结的数字契约；不是光学有效9位的证明 |
| Pure code255对应256区间；Hybrid time63对应64区间 | 冻结契约，不改成255/63区间 |
| DATA-7B 用固定电流单通道输出级、离线RTL→VCD→PWL驱动 | 已有可复核结果，不是完整MOS灰阶控制器或混合信号闭环联合仿真 |
| 固定参考15 µA、逻辑1.8 V、VCAS=1.8 V、输出夹持1.2 V、TT/27°C | 继承的单通道POC测试条件；不能当最终VLED/VSCAN或SOA额定 |
| 八个实际PAM电流值 | **NOT DEFINED**，DATA-7A/7B没有冻结其正式值 |
| 下文1.875–15 µA档位、拓扑和几何起点 | 本任务供离线比较的 **POC_CANDIDATE / ENGINEERING_DERIVATION**，不是老师要求，也不是已通过模拟的结果 |

若旧文档出现5 V、像素pitch、封装或光学参数，与本轮无关，不顺手重写系统方案。保持五芯片架构、Data/Scan分工和已完成成果。

## 3 本轮候选定义：八个正电流档，一路输出

为把未定义项变成可审查对象，本轮**实现下面A候选的源网表**，但不得把它登记成正式电流规格。

候选A：八个相同单位下拉支路，开启数量为 `pam_sel + 1`。外部参考电流始终15 µA；理想镜像关系给出 `Iunit=15/8=1.875 µA`。这些是估算目标，实际电流必须留待原生仿真。

`unit_mask[0]` 对应第0支路；下表按 `[7:0]` 书写：

| pam_sel | 理论目标 µA | 导通支路数 | DATA_EN=1时的unit_mask |
|---|---:|---:|---|
| 000 | 1.875 | 1 | 00000001 |
| 001 | 3.750 | 2 | 00000011 |
| 010 | 5.625 | 3 | 00000111 |
| 011 | 7.500 | 4 | 00001111 |
| 100 | 9.375 | 5 | 00011111 |
| 101 | 11.250 | 6 | 00111111 |
| 110 | 13.125 | 7 | 01111111 |
| 111 | 15.000 | 8 | 11111111 |

DATA_EN=0时，八个支路**全部关闭**。第0支路只在发光使能时构成基础电流，不是永久导通。黑色由时间码0或DATA_EN=0控制，不把候选000误写成0 µA。

Pure模式未来仍可使用 PAM 请求码7选最高档，但本轮只准备接口，不连接或修改已接受控制器。

同时在方案中比较两个替代定义，不必搭建其完整网表：

- 同一A电流表的“基础1单位 + 二进制1/2/4单位”四支路结构：讨论支路权重、进位切换、器件匹配和偏置负载；不是只写1/2/4就得到八个正档。
- 常规0–7单位、最高15 µA的定义：它包含0电流档，单位应为15/7 µA，与上表语义不同。明确为何不在当前A候选中混用它。

不得把不同方案各自有利的端点、步长和DNL定义混在同一张结果表里。

Hybrid 6+3只表示512组数字编码组合，不意味着512个不同电荷或9个有效光学位。例：时间区间32×1单位电流与16×2单位电流理想电荷相同；时间码0配任何幅度都为黑。将这些重复关系写明，LUT/光学映射另做，不在本轮强行解决。

## 4 MOS候选电路必须做实

### 4.1 顶层接口与层次

候选顶层只需以下功能端口，名称可采用新前缀但要给逐项映射：

- 输入：`DATA_EN`、`PAM_SEL[2:0]`，1.8 V控制域。
- 外部参考/偏置：`IREF_IN`、`VCAS`。
- 输出：**一个** `DATA_OUT`。
- 电源：`VDD18`、`VSS`。

层次应能追踪到：3位请求 → MOS温度计译码 → 每支路使能与真实反相 → 八个单位电流支路 → 公共DATA_OUT。共享参考偏置清楚画出；每支路的局部偏置/内部节点不能意外短接。

这不是八个LED通道。不得产生八个独立DATA_OUT后称为“一路八档”。

### 4.2 继承现有电流路径，禁止理想源冒充PAM

现有已读源码：

- `data_bias_ref`：二极管连接Mref，n33，L=2 µm，W=20 µm。
- `data_sink_1ch`：Mcas、Mout、Mpass_local、Mbleed_local四管。
- Mout/Mcas原W=20 µm、L=2 µm；pass为`n33_dnw_4t_ckt`，其第四端接本地`vbias_ch`；不能擅自接VSS。
- 互补使能由真实MOS反相器产生，不能由第二个独立理想电压源代替。

在**新文件**中构建候选A。可作为起点：共享参考仍W=20 µm/L=2 µm；各单位Mout先取W=2.5 µm/L=2 µm，得到理论1:8镜像比；Mcas可按单位电流同步考虑W=2.5 µm。pass/bleed不盲目随电流全部除以8，先保留已有有效几何或给出有来源的选择。所有修改都只在新候选内。

这是几何/电流比例推导，不保证短沟道效应、输出电阻、局部偏置、参考负载、误差或瞬态达到目标。查不到几何合法性的仓库依据时标 `GEOMETRY_NOT_VERIFIED`，不读取guest/PDK原件来补，不猜“已通过PDK”。

必须逐管说明D/G/S/B和主电流方向；明确DATA_OUT→Mcas→Mout→VSS主路径，以及参考、pass、bleed路径。特别检查每支路DNW体连接和关断放电节点。

禁止：

- 用 `I = f(pam_sel)` 的理想受控源、Verilog-A/行为电流源代替八档MOS网络。
- 随码改变理想IREF或理想VBIAS来伪造电流档；IREF可作为testbench中固定外部参考，实际VBIAS必须由参考MOS建立。
- 一边保留原大电流Mout，一边只改表格或输出电流目标。
- 把八个数字mask/PWL输出当成已完成MOS译码器；译码和每支路互补控制都要有真实CMOS候选网表。

### 4.3 译码与接口责任

对j=1…7，温度计选择为 `PAM_SEL>=j`；第0支路选择恒为1。每支路真正使能为 `DATA_EN AND select[j]`。

可用静态CMOS反相器、NAND/NOR等组成译码与使能；给出门级到MOS的层次表。选择具体实现时照顾面积和扇出，不为做一个3-bit译码搭建通用处理器或大型库。

PAM请求必须在不发光期间更新，发光窗口内保持不变。这个最小单元不包含寄存、完整灰阶计数、授权撤销FSM或TCON；上游协议由已接受DATA-7A承担。不要新增BLANK/FAULT恢复逻辑后声称已验证整芯片重新授权。后续bench可以改变DATA_EN测试关断，但不等于本单元会自主判断LATCH/START权限。

未知X/Z、越界、空请求在离线用例/导出入口拒收；不能把这种软件拒收描述成真实模拟MOS能检测X/Z。

## 5 离线验证：从新网表取事实，不自说自证

本轮仅使用Python标准库、文本/层次解析、静态逻辑或连接性检查和Git。不得调用Icarus、Spectre、ngspice、Xyce、Virtuoso、OA或其他物理/RTL仿真器。

离线解析器只需支持新候选实际使用的明确语法子集，不建设通用SPICE平台；遇到不支持的语法就点名拒绝。数字门可按实际MOS连接匹配已检查的静态CMOS模板后组合验证；模拟支路只做结构与比例检查，不能从开关图推断实际模拟电流。

### 5.1 必须验证的内容

1. 解析**实际交付候选网表**的子电路、端口、实例、模型/器件名、连接和几何；检查重复实例、缺定义、端口数错、未声明端点、意外浮空或支路输出未并到公共端等错误。PDK器件可按明确的端口白名单当黑盒，不导入模型卡。
2. 独立手写上表8行及DATA_EN=0的8行黄金mask。用从实际译码网表得到的门/晶体管连接关系验证16种合法输入；不得用同一个比较函数同时生成DUT结果和golden。门单元的CMOS上拉/下拉结构需验证，不能只依赖实例名叫NAND就认定其行为是NAND。
3. 验证每支路的EN来自实际全局使能与选择网络、EN_B来自本支路真实反相节点；共享参考、局部节点、D/G/S/B及公共输出符合设计表。
4. 从实际参数计算Mref/Mout的W/L比例，明确它是 `ESTIMATED_MIRROR_RATIO_ONLY`。实例数、展开MOS数、m/fingers和有效宽度分别说明，不把8个电流单元写成8只MOS。
5. 新请求入口对X/Z、负数、>7、NaN/Inf或非整数拒收；不能把拒收当作模拟测试PASS。任何将来可能调用原生工具的入口在本轮都应先拒绝，再返回，不能先连接、写正式产物或创建模拟目录。

### 5.2 检查器自身必须有真实反例

在临时副本逐项修改，至少覆盖：

- PAM输入位序错；
- 某个温度计阈值错一档；
- 漏掉全局DATA_EN，导致第0或某支路一直使能；
- 一个支路漏接公共DATA_OUT；
- 共享Mref比例改错（如20 µm误成2.5 µm）；
- DNW pass体端误接VSS；
- EN_B误接常量或错误支路；
- 一个子电路端口次序或实例映射损坏。

每项先证明实际字节确被修改且对应故障被激励，再要求**指定新增失败项**点名。不能仅因总rc非0、既有失败、hash不符或读错路径就计“检出”。合法网表必须通过结构/逻辑检查；这些PASS只属于离线检查，绝不写成电气PASS。

沿用已知教训：明确要求 `new_failures == [expected_check]` 或其规定集合，禁止 `[] == []` 空洞为真；外部自测结果要解析JSON字段，不能只按rc认定成功。

## 6 下一阶段验证计划：只准备，不执行

输出一个可直接审议的原生验证计划和bench草稿；所有模拟结果列均为 `NOT_RUN`。bench中testbench电源/参考源与DUT分离，供电显式接地，包含路径可配置，不复制PDK/模型卡/许可证。

先建议以下矩阵，再说明每例目的、观察节点、测量区间、参考定义和失败条件：

- 8个DC案例：逐码检测绝对电流、单位支路电流、单调性、译码电平、参考/局部偏置；1.2 V夹持为继承POC点。若提出额外输出电压扫描，明确候选范围和余量测量口径，不冒充最终电气特性。
- 4个瞬态案例：八档长脉冲；120 ns短脉冲代表码；200 ns短脉冲代表码；DATA_EN关断与只在关态进行的多位换码。说明011→100、000→111等切换的检查位置。
- 3个细步长复测：从低档短窗、最高档和关断/换码案例中选择，写清与原案例的配对，不把理想输入沿相同当成模拟电流收敛。

**30/36不是本轮授权。** 若以后每个DUT案例配一次动态preflight，上述15个案例最多需30次原生启动，再留6次工具调试余量，可提出“总上限36”的新任务预算建议；这个数字只是可审议草案。本轮仍为0，不借用或重置DATA-7B旧账户的56次授权。

测量计划必须区分：

- 静态绝对误差对理论目标，归一化误差对共享参考/满档，单调性及DNL/INL；统一单位和归一基准，不能逐码标定后掩盖档位误差。
- 动态总电荷相对理论目标与相对该档实际静态电流的差别；不要把每档单独的脉冲误差单位擅自叫成“9-bit LSB”。
- 采样时刻与连续阈值时刻；入带持续到窗口自身deadline；正负电荷按插值过零点分段；关断与末段泄漏。
- 电气FAIL、证据缺失/BLOCKED、检查器异常、历史预算违规分别列状态。

实际档位、阈值、Q的归一方式、允许误差与仿真额度须在本轮独立审核后另行冻结，不能由执行者在原生运行中边看结果边改。没有LED I–V、阵列RC、驱动阻抗或PVT证据，不给光学/阵列/可靠性结论。

## 7 文件范围与交付物

本轮对固定基线实行**仅新增文件**：0条既有路径修改、0删除。所有旧源码、PDK引用、RTL/TB、任务书、合同、接受登记、共享安全与验证器、全部旧证据目录及已发布中间目录冻结。

不要顺手修DATA-7B的三条非阻断待办；在新报告列出它们及5条指定ref/22条全量ref的出处区别即可，新工具直接采用正确做法。旧接受字节不动。

建议新增：

```text
reports/tasks/DATA-7C-A.md                         本任务书逐字节副本
reports/dd1_d7c_a_pam_candidate.md                 方案比较、逐管解释、接口与未决项
reports/dd1_d7c_a_native_test_plan.md              下一阶段矩阵、判据候选与预算草案
reports/agent_handoffs/DATA-7C-A.md
reports/agent_handoffs/DATA-7C-A.json
spectre/dd1_d7c_a_*.scs                           新MOS门/译码/单位支路/顶层/bench草稿
scripts/dd1_d7c_a_*.py                            解析、离线验证及负例工具
tests/dd1_d7c_a/*                                 手写黄金表和小型离线用例
results/evidence/dd1_d7c_a_<unique_run_id>/*        源摘要、计数、逻辑/连接性正反例、命令rc、冻结比较
```

网表和文档要使新读者看懂主电流怎么流、哪只管选择档位、哪只管关断放电、为什么八支路仍只有一个输出。可提供一张依据网表的层次/连接图，清楚标 `CANDIDATE / NOT SIMULATED`；不是已生成Virtuoso/OA原理图。

先完成源码与验证，再冻结证据、生成计数/摘要、更新交接。每个重要里程碑持久化checkpoint；失败保留原因，不靠长会话记忆继续猜。已发布目录不能删掉重做或原地覆盖；新导出使用新run_id，故障注入只在临时副本。

证据和审核包保持小型；无完整PSF/VCD、工具二进制、PDK、模型卡或凭据。清单要机械覆盖文件集合，区分仓库源文件与打包器生成的README/验证器。清单不列自身，包内不写包本身摘要；归档身份在外部回执记录。

## 8 Git、审核闸与失败处理

1. 对全部基线tracked路径逐项比较(mode,blob)：必须全同。只检查几个目录、只看文件名或工作树diff不够。
2. 运行新候选离线检查和检查器反例，检查当前交付字节及新鲜提取物；结构验证器只证明schema，不能替代事实。
3. 按原安全规则和hooks检查新增源码/文档。既存objects问题如实记录，不打印疑似敏感对象、不GC、不改规则，不用扫描PASS声称旧凭据事件已解除。
4. 每条命令独立保存rc；管道不掩盖失败。`git diff --check BASE..tip`覆盖已提交区间，不能拿未跟踪文件尚未入比较时的空检查当最终结果。
5. 一个主要交付提交加必要交接记录即可；如有后续代码修正，按真实范围列出并重新验证相关项，不一概叫“纯元数据”。不为把SHA写入自身而连续制造空提交。head_sha角色、payload身份和远端tip分清；源摘要不自指。
6. 普通push新分支，禁止force、跳hooks、merge、修改可见性或推main。推送后Git protocol与已有API独立回读同一对象，旧分支与main不动；哪路不可用就如实标，不拿历史回执顶替。
7. 身份不符、关键连接/数据不能独立解析、需要改冻结共享工具、意外触及凭据/VM、或仅能用行为源实现时，带已完成产物和原因停下。同一问题最多3次修复尝试，之后报告具体阻塞，不无限循环。

交接必须把下面几层分开：候选MOS源设计完成、离线检查完成、原生语法尚未验证、八档电流尚未实测、是否被用户/审核方接受。不要用 `PAM_IMPLEMENTED=PASS` 一句话吞掉这些边界。

```text
TASK_ID=DATA-7C-A
BASE_SHA=272d6de6d2f2fc8a82d5038d73d6b3e4c656f683
ACCEPTED_DATA7B_CONTENT_SHA=f9fd09b184a69a27cdb409205dfd4f4151408a23
SCOPE=ONE_OUTPUT_EIGHT_LEVEL_PAM_CANDIDATE_MOS_AND_OFFLINE_VERIFICATION
PAM_LEVELS_STATUS=POC_CANDIDATE_NOT_FORMAL_SPEC
COMPLETION_LEVEL=CANDIDATE_MOS_NETLIST_WITH_OFFLINE_CHECKS
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
PWM_PAM_CURRENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
EXISTING_TRACKED_PATHS_MODIFIED=0
HISTORICAL_DATA7B_BUDGET=VIOLATED_59_OF_56_OVER_BY_3
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW_OF_CANDIDATE_AND_TEST_PLAN
```

## 9 公共参考，只用于架构概念

1. Analog Devices，Current Steering Digital-to-Analog Converters：
   https://wiki.analog.com/university/courses/tutorials/cmos-dac-chapter
   参考事实：二进制加权与全译码/相同单位电流结构有不同的匹配、开关与面积代价；电流源输出电阻和开关寄生影响误差。**它不证明本项目候选的匹配、单调性、瞬态或电流档值。**
2. Analog Devices，Using Hybrid Dimming with MAX25510 and MAX25511：
   https://www.analog.com/en/resources/technical-articles/using-hybrid-dimming-with-max25510-and-max25511.html
   参考事实：PWM时间调光和模拟电流调光可以组合。**它不是本项目3+6编码、15 µA、八档表或具体MOS拓扑的出处。**

两项网页由云端在2026-10-23读取。无需本地重复联网追论文才能开工；本任务已提取所需概念。不得把公共器件的mA级参数、IC内部实现或参考图误搬成本项目规格。
