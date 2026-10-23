# DATA-7C-A-R2：限定离线补齐任务书

You have NO access to the user–ChatGPT conversation. Your complete sources are this task brief, its accompanying independent-review package, and the named repository at the pinned commits. Do not infer execution authority from an older plan, a passing exit code, or a proposed future budget.

用户交付本任务书时授权的是以下离线返修，不授权原生仿真、VM、接受登记、合并或下一阶段。四个正常候选电路保留，不重画、不扩阵列。

## 1 固定身份与权限

| 项目 | 固定值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 本轮 | DATA-7C-A-R2 |
| 被审 R1 tip / 新基线 H | `da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb` |
| 原 A tip T | `89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79` |
| 原开发基线 B | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` |
| 已接受 DATA-7B 内容 | `f9fd09b184a69a27cdb409205dfd4f4151408a23` |
| main 保持 | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| R1 分支保持 | `poc/data-pam-d7c-a-r1` = H |
| 建议新分支 | `poc/data-pam-d7c-a-r2` |

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

不得运行 Spectre（包括 `-h`）、ngspice/Xyce、Icarus、Virtuoso/OA、动态 preflight 或旧波形重跑；不得读取凭据、PDK、模型卡；不改密码/license/网络，不 GC、不重写历史、不 force、不跳 hooks。纯 Python 文本/图/合成数据检查与 Git 读取在范围内。

用本机现有 Git 与 API 通道回读同一个查询对象，记录 full SHA、UTC 与 rc。若一路不可用如实记录。新建独立 worktree；若 H 分支已经移动，先只读调查，不能无声吸收新提交或覆盖现有目录。

## 2 必读与已核实结果

先读根 `AGENTS.md`、`README.md`、本包 `REVIEW_DATA7C_A_R1.md`，以及：

- 原 `reports/tasks/DATA-7C-A.md` 和 `reports/tasks/DATA-7C-A-R1.md`；
- H 的候选/计划/R1 修补报告与 `reports/agent_handoffs/DATA-7C-A.{md,json}`；
- `scripts/dd1_d7c_a_{netlist,offline_check,guards,verify,validate_handoff,deckgen}.py` 与 `dd1_d7c_a_r1_selftest.py`；
- 四个 `spectre/dd1_d7c_a_{gates,pam_dec,sink_unit,pam_top}.scs`、bench 草稿；
- `tests/dd1_d7c_a/` 四张表；
- `spectre/current_probe_syntax.scs`，DATA-7B runner 的 `Ip_out (clamp data_out)` 连接与 measure 中正方向说明。

审核端已实际 fetch H，确认：B 的 2,533 路径零漂移，T 冻结的 2,547 路径零漂移；T..H 为 10 修改、24 新增、0 删除、12 commits，H 共 2,583 路径。原八例在 T 上 8/8 复现，在 H 上各有具名失败；正常 30 项、29 个反例、9 个记录自测及交接检查可重放。

本轮只补齐七项新定位诊断与相关计划/文档问题，不把已关闭的原八例重新设计一遍。1:8、1.875–15 µA 仍只是候选估算，无八档模拟实测。

## 3 先复现 H，保留原始记录

从 H 用 `git archive` 提取新的基线副本；不要覆盖原已发布证据。原样运行本包：

```text
python reviewer/probe_r1_remaining.py --root <未修改的H副本> --out <新的诊断JSON>
```

rc=0 的意思是七项缺口全部复现，**不是通过验收**。读取 JSON：baseline_checks=30，baseline_failures=[]；前五项为实际输入副本诊断，第六项明确为函数级读表定位，第七项为端序/KCL 推导，不是原生仿真。每项修改前后摘要不同，故障事实存在。

另保留原审核仪器 `probe_review_gaps.py`（本包 reviewer 中）及它在 T/H 的原始结果；不改仪器迁就代码。原八项回归必须逐项通过，不看聚合 rc。

每个问题最多三次修补尝试；之后带真实失败 STOP，不改预期/阈值凑结果。

## 4 F1：核对顶层实际电源绑定

故障是把 Xdec 的 `… enb7 vdd18 vss)` 改成 `… enb7 vss vss)`，30 项仍通过。当前检查只映射四个逻辑输入，`NL.evaluate(DECODER, …)` 又给子层提供理想电源。

- 在本项目支持语法内确认实际顶层 Xdec 的电源端身份，正常必须连到对应顶层 vdd18/vss。电源短接、调换、悬空或误接逻辑信号应具名拒收。
- 不修改 DUT，不为此重写通用 SPICE 模拟器。可以先做明确的实际绑定检查，再评估逻辑。
- 正常 16 种使能/码组合继续从实际顶层映射评估；新增电源短接临时副本必须失败，旧位序/使能/参考反例仍具名检出。

## 5 F2：统一实际输入路径的严格 schema 与数值域

缺口：严格 `read_table()` 没有覆盖 `read_rows()/DictReader` 的实际输入路径；黄金表多一格被忽略，计数表只剩表头仍通过，`en0=NaN` 抛未处理 ValueError。

对黄金、请求、计划、计数声明四张实际输入表：

1. 检表头完全相等、逐行列宽、必填项、唯一键；不忽略额外列，不先解析成 dict 后丢失坏列证据。
2. 黄金表仍是冻结的 16 个唯一 `(enable,code)`，8 位 0/1 mask、en0..en7、branches_on 一致；先校验再求值，有限整数域错误返回明确表/行/字段的结构化 FAIL，不崩栈。
3. 请求表保持原内容与 16 种请求覆盖；合法 ACCEPTED 对照与非法值分别核，不因 schema 异常继续遍历。
4. 计数表使用本项目明确的 `(object,count_kind)` 键集合与当前正常源解析值。空、缺、重复、额外/非法键都应拒收。可从契约手写必要键，不能从被删剩的行推导“应该存在的对象”。本轮 H 是 17 条声明；不把这个 17 与实际 MOS 总数混用。
5. 计划表的八个 DC case_id 必须与 code 000..111 一一对应；三组 refined 配对固定且条件一致，不能只检查“每行第一个字符是数字”或“总数15”。

至少保留正例（正常文件、合法引号/逗号、允许空的可选字段）和负例（黄金额外格、非有限/非整数、计数空表/缺键/重复、DC 重复全零）。正常黄金与请求表原字节冻结，只在临时副本造错。

## 6 F3：补一个小型已发布记录语义层

H 的正式记录形状已正确，不需要磁盘事务框架；但最终回读只核列宽/空值/唯一键，能接收 `rc=99, expected_rc=0, verdict_state=PASS`。

- 可保留通用 CSV 形状读器，并另设只针对本轮固定 schema 的 `validate_published_record` 类函数/只读入口。真正发布后的回读必须调用该语义层。
- `commands.csv`：核必需 gate 集合、唯一性、rc 与 expected_rc 的明确关系、允许的状态枚举；mandatory gate 缺失、失败、NOT_ATTEMPTED 不能变成总体通过。netlist_stats 的 INFORMATIONAL_NOT_PASS 必须照实保留。裸 archive 的 Git 自测 NOT_RUN/rc=2 与有 Git 历史时 9 例 PASS 分开。
- 核 `git_checks.csv` 的实际区间、rc，冻结表的 enforced/expectation 与违规计数，source_identity 路径/摘要/字节数，JSON 子结果与汇总/CSV 对应。记录中的历史文档身份明确标参考提交/时刻，不伪称最终当前字节；最终归档以实际 blob/清单为准。
- 负例要在临时证据副本中制造，若有 manifest 就同步重封，证明语义错误本身被拒，而非只因摘要失配被挡。至少覆盖 FAIL→PASS 洗白、rc99/PASS、mandatory gate 缺失/未知状态、错摘要或不存在路径、子检查失败但汇总PASS。
- 使用真正的发布后只读复核入口做正反例。包内第六项是函数级定位：若新设计把语义层放在新入口，通用 `read_table()` 仍只读形状可以保留；必须提供新入口的真实拒收结果，不能修改旧仪器后宣称“同一仪器都修好”，也不能只用 mock 调函数冒充端到端发布测试。
- 失败/拒收不改已发布目录；新运行用新 staging/run_id，旧文件一律留存。

## 7 F4：在运行前固定正确取号与自洽激励草案

### 7.1 探针方向

物理正下拉路径：`clamp_node → data_out → 下拉支路 → vss`。H 草稿 `Ip_branch (data_out clamp_node)` 的原始探针电流在此路径上为负。

请选择并在 deck/表/报告/handoff 统一一种定义：

- 推荐将 bench 探针改为 `Ip_branch (clamp_node data_out) iprobe`，定义 `I_sink=Ip_branch`；或
- 保留端序，明确在测量接口固定 `I_sink=-Ip_branch`。

这是 bench 与测量符号的修正，不改四个冻结 DUT，不允许 `abs()` 或看到结果后翻符号。用纯 Python 手写带符号合成样本/KCL 对照证明：正下拉给正 I_sink/正 Q，真实反向电流保留负号；正负面积分别积分，不相互抵消后宣称关断。标为合成自测，不能写“模拟实测”。原生语法仍 NOT_VERIFIED。

### 7.2 日程与覆盖

- 保持 15 例＝8 DC +4 transient +3 refined，结果全 NOT_RUN，30/36 仅草案。
- 修正 TR-LONG 的时间矛盾：H 相邻平台间实际差为 1.5 TON，文档却写0.5 TON。选择一个一致时间表，明确平台、有限沿、关态间隔、关态换码点、积分窗与尾窗，先从同一份结构化数据检查不重叠/8码覆盖，再渲染表/报告/bench说明。
- DC 静态 DATA_EN=1.8 V、Iref15µA、八码全覆盖、夹持扫描条件保留；TR-120/TR-200 仍用最低码000，并明确平台起止、有限沿和尾窗。
- TR-OFFCODE 的 011→100、000→111 只在关态；可观察局部偏置放电及下次导通。
- RS-LOW↔TR-120；RS-FULL↔TR-LONG；RS-SWITCH↔TR-OFFCODE。每对完整激励历史/供电/参考/初始条件一致，只改 maxstep；RS-FULL 可以只量末段，但不能丢掉此前七段激励后冒充同条件配对。
- 清除草稿顶部 EIGHTEEN/“瞬态只替换三个PAM位”等冲突旧说明。无需本轮输出可运行原生 deck，生成器仍先拒绝再写/连/启动。
- 实际档位值、误差容差、Q归一单位、细步长判据、原生额度继续待后续独立冻结，不因本次文字修复自动采纳。

## 8 文档和真实已提交范围

- H 的 `git diff --check T..H` 与 `B..H` 均 rc=2，唯一定位为 R1 报告443行 EOF空行；同轮去掉并追加范围/时刻勘误。保留历史当时的正确或错误事实，不把早期0改称最终0。
- H最终 T..H 是10改24增0删12commits；区分较早14新增的测量对象，别继续以旧字段代表新tip。
- 报告不声明自身摘要；ZIP摘要只留包外回执。减少无功能元数据提交，不追逐自指SHA；一份最终载荷+必要交接即可。
- 绕过 hooks 的既往事件不因新扫描 PASS 消失。只记录当前执行与用户待处置状态，不擅自追认历史。

## 9 白名单与冻结

冻结 H 的四个候选 DUT、正常黄金/请求表、原/R1任务书、既有全部证据目录、DATA-7A/7B接受源码与证据/登记、旧待办、共享安全/provenance/netlist_stats 等工具；B的2,533既有路径继续冻结。

允许修改 H 的路径只限：

```text
scripts/dd1_d7c_a_offline_check.py
scripts/dd1_d7c_a_guards.py
scripts/dd1_d7c_a_verify.py
scripts/dd1_d7c_a_validate_handoff.py
spectre/dd1_d7c_a_tb_draft.scs
tests/dd1_d7c_a/native_case_plan.csv
tests/dd1_d7c_a/device_count_claims.csv
reports/dd1_d7c_a_pam_candidate.md
reports/dd1_d7c_a_native_test_plan.md
reports/dd1_d7c_a_review_fix_r1.md
reports/agent_handoffs/DATA-7C-A.md
reports/agent_handoffs/DATA-7C-A.json
```

R1报告只作EOF与明示勘误；新根因/修法主要写R2报告。无需改的白名单文件别顺手改。`netlist.py`、`deckgen.py` 和 R1 selftest 保持原字节；若认为必须改冻结文件，先带理由 STOP，不自行扩围。

允许新增本任务逐字节副本 `reports/tasks/DATA-7C-A-R2.md`、R2修补报告、小型 `dd1_d7c_a_r2_` 前缀脚本/用例及独立新证据目录。审核仪器按未修改附件/摘要保存。禁止修改老证据以让新复核通过。

## 10 交付与验收

1. H 原字节的七项新定位与旧八项回归，逐项JSON；修补后保留对应正常/错误对象事实，不能用聚合rc充验收。
2. F1电源实际绑定；F2各表严格schema/有限数值/必要键；F3真正记录语义入口；F4方向合成测试与日程算术分别有正反例。
3. 原30正常检查、29反例、9记录自测可回归；新数量从交付字节解析，不手填。测试语义层与DUT层分开标。
4. B全树、H冻结面、H..tip白名单三者分别比较；四份正常候选/黄金/请求/旧记录全部blob+mode相同。
5. 新鲜 Git archive 提取物重放；需要Git历史的测试明确NOT_RUN并另在有历史副本跑，不能拿2算PASS或把崩溃当具名拒收。
6. 发布文件与Git blob逐项比较；最终 `git diff --check H..tip`、`T..tip`、`B..tip`真实已提交区间均通过，不能只检工作树。
7. 不删已发布中间目录；安全与来源检查按原规则执行，扫描失败如实保留；不输出敏感原文。
8. 普通push新分支后独立回读同一对象，记录fullSHA、UTC与每条rc；确认main、A、R1、DATA-7B分支原位。
9. 审核包从Git blob构建，包含自包含任务、报告、脚本、正负JSON、必要只读依赖及清单。真正放到仓库外验证包，不缺输入；归档摘要不写包内。

```text
TASK_ID=DATA-7C-A-R2
BASE_SHA=da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb
REPAIR_SCOPE=OFFLINE_CHECKERS_RECORD_SEMANTICS_AND_BENCH_PLAN_ONLY
CANDIDATE_DUT_NETLISTS_CHANGED=NO
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
PWM_PAM_CURRENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
HISTORICAL_DATA7B_BUDGET=VIOLATED_59_OF_56_OVER_BY_3
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

完成立即停在独立复审闸，不自行给GO，不登记接受版，不转入原生/八档电流/完整灰阶控制器/LUT/阵列/TCON/版图。历史预算、凭据事件与旧待办由用户处置。
