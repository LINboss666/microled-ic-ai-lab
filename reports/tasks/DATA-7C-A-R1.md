# DATA-7C-A-R1：限定离线返修任务书

You have NO access to the user–ChatGPT conversation. Your sources are this complete task brief, the accompanying independent-review package, and the named repository at the pinned commits. Do not infer additional execution authority from an earlier conversation or a proposed future budget.

你是本地执行 Agent。用户将本任务书交给你，授权的是以下限定离线修补；不是授权原生仿真、VM、接受登记、合并或 DATA-7C-B。完成后停在独立复审闸。

## 1 固定起点与目标

| 项目 | 固定值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 本轮 ID | DATA-7C-A-R1 |
| 修补基线 T | `89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79` |
| 原 DATA-7C-A 开发基线 B | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` |
| 已接受 DATA-7B 内容 | `f9fd09b184a69a27cdb409205dfd4f4151408a23` |
| main 保持 | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 原交付分支 | `poc/data-pam-d7c-a`，保持在 T |
| 建议新分支 | `poc/data-pam-d7c-a-r1` |

目的：保留候选 A 的正常 MOS 电路，补齐顶层验证、检查器输入与计数校验、证据 CSV 和 15 例原生草稿的缺口。**不是重新设计八档模拟电路，也不运行它。**

```text
NEW_SPECTRE_LAUNCH_LIMIT=0
NEW_RTL_SIMULATION_LIMIT=0
NEW_OA_WRITE_LIMIT=0
SSH_OR_VM_ACCESS_AUTHORISED=NO
NATIVE_PREFLIGHT_AUTHORISED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
MERGE_OR_MAIN_PUSH_AUTHORISED=NO
ACCEPTANCE_REGISTRATION_AUTHORISED=NO
```

`spectre -h`、动态 preflight、ngspice/Xyce、Icarus、Virtuoso/OA、旧波形重跑均不在范围。不得读取凭据、PDK 或模型卡；不改密码、license、网络；不 GC、不重写历史、不 force、不跳 hooks。

动工前用既有 Git protocol 和 API 通道回读同一查询对象，记录完整 SHA、UTC、rc。若一路不可用如实记录，不借用旧回执。核对 T 正好在原分支、B 是其祖先、main 未动；新建独立 worktree，不覆盖同名路径或分支。发现新提交时先只读调查，不顺手吸收。

## 2 输入文件与已核实结论

先读根 `AGENTS.md`、`README.md`，以及：

- 原任务 `reports/tasks/DATA-7C-A.md`；
- 本审核包 `REVIEW_DATA7C_A.md`、`checks/probe_review_gaps.json`、`checks/source_identity.json`；
- T 的两份候选/计划报告、`reports/agent_handoffs/DATA-7C-A.md/.json`；
- `scripts/dd1_d7c_a_netlist.py`、`offline_check.py`、`guards.py`、`verify.py`、`deckgen.py`、`validate_handoff.py`（均带完整前缀）；
- 五个 `spectre/dd1_d7c_a_*.scs` 与三份 `tests/dd1_d7c_a/*.csv`；
- `reports/dd1_d7a_contract.md` §2 的 Hybrid 63→64 区间规则。

审核方已实际获取 T，确认 B 的 **2,533 条既有路径 (mode,type,blob) 全同**；最终 T 是 **26 新增、0 修改、0 删除**，不是回执的 25。四个正常候选源文件给出的结构为单输出、八个单位支路、145 MOS；目前的正常接线与掩码可以保留。

原 22 项离线检查和 10 个反例在审核端重放均 rc=0；但审核方增加的八个临时副本诊断全部仍 22/22 PASS，说明存在真实漏检。本审核不是电流实测，1:8 与 1.875–15 µA 仍只是候选估算。

## 3 先复现，不覆盖原始交付

将审核包解压到新的 `review/` 子目录。先对原始 T 的提取副本运行随包 `reviewer/probe_review_gaps.py`，原脚本字节不改：

```text
python reviewer/probe_review_gaps.py --root <未修改的T提取物> --out <新的诊断JSON>
```

此仪器 **rc=0 表示八项缺陷全部复现**，不是通过验收。读取 JSON，确认 baseline 22、baseline_failures 空、8 个诊断都真的改了字节，逐项 `defect_reproduced=true`。根目录必须是 T 原始字节；不可把修过的目录当基线。

若仪器无法运行，先报告具体原因，不修改仪器来迁就代码，不用既有失败凑“检出”。实际修改前留存 T 阴性结果；每个问题最多三次修复尝试，之后诚实 STOP。

## 4 F1：验证顶层真实连接

当前黄金表直接评估 DECODER 子电路，未沿顶层 Xdec 的实际绑定输入。补充集成验证：

1. 对实际顶层的 `data_en/pam_sel0/1/2` 注入 16 组合，经实际 Xdec 位置映射解析内部网络，再检查每支路真实 EN/EN_B 与单位核的绑定。
2. 从实际顶层 Xref 展开参考管：D=G 应解析为共享 `iref_in`，S=B 为 `vss`；确认各单位 pass 的共享端接同一参考节点。仅比较 Mref/Mout 几何比不足以证明参考连接。
3. 保留现有子单元 CMOS 图推导，不按子电路名字认逻辑；也不把检查器常量构造出的正确输入映射冒充网表事实。
4. 给三个独立临时错误各自具名拒收：Xdec bit0/bit2 交换、Xdec 的 data_en 接 vdd18、Xref 接 vcas。

正常 16 种组合必须通过，且 DATA_EN=0 八支路全关。计数、掩码与错误对象取自实际展开连接；不能因 hash 改变就报拓扑错。

## 5 F2：检查器的身份、参数和空表

### 5.1 标识与参数

- 同 cell 作用域内检查 **M 器件和 X 实例**的重名，必要时跨类别也按所用语法的标识规则检查。不要只遍历展开 X 列表。
- 单位核同构要比较其实际使用的全部有效参数，至少 model、D/G/S/B、L、W、m。显式/隐式 `m=1` 可按数值归一后等价；`Mcas m=8` 必须被点名。
- 分开统计网表语句数、层级实例数、multiplicity、若存在的 finger 参数及有效宽度；未设置的 finger 参数不凭空生成。不扩展通用 SPICE 平台，仍只支持本任务实际语法子集，未知语法具名拒收。

### 5.2 黄金表与报告对象

- 黄金表必须恰好覆盖 `(enable∈{0,1}, code∈{0..7})` 的 16 个唯一键；检查字段、有限合法值、mask 长度和字母表。空表、缺行、重复、额外/非法键分别拒收，不可把没有 mismatch 当成功。
- 手写黄金值仍与 DUT 独立。正常黄金表原字节保留；不要用 DUT 结果覆盖黄金表。对请求拒收表的同类空遍历也检查，不能把零条记录说成“16 种已测”。
- 报告器件数要绑定**对象与计数口径**。顶层 145 误写成另一个 cell 的 112 必须失败；不再使用“数字属于任意已知总数集合”来放行。可以使用机器标记或明确对象表后生成报告段，不能建设任意中文语义解析器。
- 保留冻结 `netlist_stats.py` 的 INFORMATIONAL 记录和旧失配，不改该工具、不放宽安全规则。新的对象检查必须有自身真实反例。

## 6 F3：无活动分析、CSV 和发布验证

### 6.1 分析语句

修复分析行检查对 `dev=` 的错误依赖。至少覆盖：

```text
review_tran tran stop=1u maxstep=1n
review_dc dc dev=Vclamp param=dc start=0.6 stop=1.5 step=0.1
```

分别注入草稿临时副本，必须具名拒收；正常注释不误报。对超出支持范围的可疑活动语句拒收并解释，不悄悄略过。

文档只陈述“草稿中没有活动分析语句”。这不保证有人调用 Spectre 时进程不会启动；禁止原生运行仍由入口授权闸保障。保持原生入口先拒绝再写/连接/启动，所有环境组合仍拒收。

### 6.2 CSV 真实坏行

T 已发布的这些表有未引用逗号造成的列错位：

| 文件 | 声明列数 | 复现坏行 |
|---|---:|---|
| commands.csv | 6 | 行2=7列、行6=12列、行8=7列 |
| git_checks.csv | 5 | 行2=6列 |
| source_identity.csv | 4 | 行13–19均5列 |

原因是 `rows_write()` 自行用逗号 join。改用 Python 标准库 CSV writer，并在发布后**从将交付的字节**反读，严格核表头、列数、唯一键、状态/rc、路径与摘要。包含逗号、引号、换行等内容应正常往返或按明确 schema 拒收，不能忽略额外列。

旧目录 `results/evidence/dd1_d7c_a_r20261023_062341_cb1bd0/` 全部原字节冻结。不修旧表、不删坏记录；在新的 unique run_id 目录发布修正后的表与逐项勘误，标明哪个提交/来源时刻对应何种计数。

不必把一个小型离线任务扩展为复杂磁盘事务框架；只需防止覆盖已发布目录，避免失败/拒收路径改动正式产物，并确保失败状态不会被摘要或 schema PASS 洗白。新复核应识别所交付表的语义，不只比摘要。

## 7 F4：修正 15 例计划，仍只写草稿

保持候选总数 **15 个 = 8 DC + 4 transient + 3 refined**，无需运行、无需增加额度：

- DC-000…111 明确静态 DATA_EN=1.8 V、对应 PAM 位、固定参考15 µA、输出夹持扫描条件。说明读哪一个 Iout/各单位电流、偏置节点。不能只换 PAM 位而沿用起始为0的使能 PWL。
- TR-LONG 可在一个 deck 中安排八个长窗口，关态换码后逐档测量；不能只做111却称“八档长脉冲”。逐段给出 code、使能与积分窗，列出关态间隔。多个段仍是一例，并非多次启动。
- TR-120、TR-200 写明确的代表码，优先最低档000，使低电流短窗确实被覆盖；明确平台起止、有限沿及关断尾窗。这些仍为 POC 候选条件。
- TR-OFFCODE 明确011→100和000→111只在关态发生，分别观察关断、局部偏置放电及下次导通。
- RS-LOW 配低档短窗（例如 TR-120），RS-FULL 配 TR-LONG 的满档长窗，RS-SWITCH 配 TR-OFFCODE；每对保持相同激励与条件，仅细化时间 maxstep，比较模拟电流/电荷特征而非理想输入沿。此轮不把 DC voltage step 当时间收敛。
- 写明 `(data_out clamp_node)` 探针方向及“正下拉电流”的取号、Q 积分方向；不能运行后看到负数才改符号。
- 静态绝对误差、参考归一、DNL/INL、对目标与对实测静态的两种电荷误差分别列，采样与插值时刻分列。阈值与 Q 单位仍列为待用户/后续任务冻结，不偷设最终标准。

台架仍可保持草稿，但表、报告与草稿对应关系必须一致：八档DC的静态使能、长脉冲分段与短脉冲时间差异如何由下一阶段生成器设置，明确列出。所有结果 **NOT_RUN**，原生语法 **NOT_VERIFIED**。

15×(DUT+preflight)=30、加6调试=36仍为下一阶段**预算建议**。本轮额度0，DATA-7B历史59/56继续违规，不借用、不重置、不追认。

## 8 同时更正这些局部文字

不改拓扑、不重写全系统方案，只修本轮新文档中：

1. 单位宽2.5 µm时4单位=10 µm，不是20 µm；
2. 不把 m 直接称为 fingers；准确区分 multiplicity 与分指；
3. Hybrid6位时间码最大63，对应64区间，不存在合法时间码64；
4. 两种理想权重精确的DAC都可有DNL=0，不能无误差模型就断言二进制“结构性DNL非零”；统计性匹配讨论注明前提与未测；
5. select5误接的说明不要错误引用实际注入select3的E02；
6. T最终新增26路径，25条名单漏JSON自身；区分先期源提交、证据提交、最终tip的实测计数。

## 9 改动白名单与冻结面

**冻结：** B 的全部2,533条tracked路径；T原任务书；T四个正常候选电路文件（gates/pam_dec/sink_unit/pam_top）；正确的黄金掩码与请求表；T旧证据目录；DATA-7A/7B所有接受源码、证据、登记与旧三条非阻断待办；共享安全/provenance/netlist_stats等工具。

**允许修改的 T 路径仅为：**

```text
scripts/dd1_d7c_a_netlist.py
scripts/dd1_d7c_a_offline_check.py
scripts/dd1_d7c_a_guards.py
scripts/dd1_d7c_a_verify.py
scripts/dd1_d7c_a_validate_handoff.py
scripts/dd1_d7c_a_deckgen.py
reports/dd1_d7c_a_pam_candidate.md
reports/dd1_d7c_a_native_test_plan.md
reports/agent_handoffs/DATA-7C-A.md
reports/agent_handoffs/DATA-7C-A.json
tests/dd1_d7c_a/native_case_plan.csv
spectre/dd1_d7c_a_tb_draft.scs
```

并非必须改满白名单。只改与上述问题有关的内容。bench只改验证草稿/注释，不改变四个候选DUT文件来逃避反例。若发现必须改冻结候选才能继续，带证据停下说明，不擅自扩大范围。

允许新增：本任务逐字节副本 `reports/tasks/DATA-7C-A-R1.md`、`reports/dd1_d7c_a_review_fix_r1.md`、带本轮前缀的新离线自测/验证脚本、小型用例、新证据目录。原始审核方仪器作为未修改附件保存，可按摘要引用；不要改成总rc即PASS的包装器。

## 10 验收、证据与 Git

必须交付：

1. 原始 T 的八例复现结果，逐项解释根因；修后同一仪器结果，**8项逐项不再漏检**。注意只看到总rc=1不能满足此项（修一项也会rc=1）。每例改前/后摘要不同、真实故障仍存在、检查器产生对应具名失败；正常副本仍通过。若解析拒收应返回明确原因，不用异常栈冒充语义检出。
2. 原有10例重新执行；新增反例覆盖顶层映射、重复M名、m变化、表空/缺/重复/额外键、对象错配、活动分析、CSV异常。预期失败集合非空且准确，不靠基础故障/旧hash失败凑检出。新自测与验收对JSON逐字段判，不能只看进程rc。
3. 正常顶层16组合、每门真值、D/G/S/B、单位核同构与参考比检查；145/112/32/1/58计数由实际源解析。m/finger口径修正后四个正常DUT文件摘要仍与T相同。
4. 正常CSV往返与严格读取；错误CSV自身在摘要自洽时仍被schema拒收；新目录逐文件摘要与Git blob一致，旧证据不改。故障/拒收路径不覆盖已发布数据。
5. 修后计划表与报告/bench草稿一致；覆盖八档长窗、低档短窗和三组时间细化配对；结果全NOT_RUN，0额度不变。
6. 用新鲜Git提取物重放离线检查；原始B全路径(mode,blob)比较、T冻结面比较与T..tip路径白名单三者分别核。记录完整范围，不能只比较几个目录。
7. `git diff --check T..tip` 检查真实已提交区间。按原hooks与安全/provenance规则执行，不改旧对象、不打印疑似敏感内容；不可达对象旧问题与本轮结果分开。
8. 一枚主要载荷提交加必要交接记录即可；不追逐自指SHA，不为把SHA写进自身连续制造空提交。报告不含自身摘要；ZIP摘要只在包外回执。报告、handoff、清单必须指向同一当前交付字节。
9. 普通push新分支，分别回读Git/API同一对象，核旧分支与main未动。回读角色、fullSHA与UTC写清。保留原始历史记录，不把修补结果倒写成T当时已正确。

修补报告按F1–F4写原现象、根因、修改、旧负结果与新正反例，附真实命令/逐命令rc、源摘要、冻结比较与未解项。旧netlist_stats信息门如实保留，不能声称旧安全事件因新扫描PASS而解除。

```text
TASK_ID=DATA-7C-A-R1
BASE_SHA=89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79
REPAIR_SCOPE=OFFLINE_VERIFICATION_EVIDENCE_AND_NATIVE_PLAN_ONLY
CANDIDATE_DUT_NETLISTS_CHANGED=NO
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
PWM_PAM_CURRENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
HISTORICAL_DATA7B_BUDGET=VIOLATED_59_OF_56_OVER_BY_3
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

不得自行给GO。完成本轮即停，交独立复审；不进入原生、电流集成、LUT、阵列、TCON或版图。
