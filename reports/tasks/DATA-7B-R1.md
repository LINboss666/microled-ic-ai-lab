# DATA-7B-R1：测量、证据与启动护栏限定返修

日期：2026-10-21。完成后停在独立复审闸。

**You have NO access to the user–ChatGPT conversation; the current task brief, the supplied review files and the named repository are your sources.**

## 0 唯一任务与硬边界

执行随包`REVIEW_DATA7B.md`指出的限定返修。现有净电荷的独立复算支持本轮抽样目标，但启动护栏、测量、复核器及文档尚不能给GO。

本轮**新增Spectre进程启动=0，新增OA写入=0**。不重跑动态preflight、不跑`spectre -h`、不以“补证据”为由启动原生仿真。过去59次按实际保留，上限56不追改为59/60。本轮允许离线处理留存raw、合成/mock测试及必要的四态RTL边沿复验。

不得修改晶体管电路、PWL、24份原生deck、冻结RTL、TB、主case表、黄金码表、原0.5 LSB/150 nA等判据或模拟条件。不得进入PAM、LUT、MOS灰阶控制器、OA、阵列、版图、TCON或其他阶段。不得合并main、改旧分支、force、跳hooks、改license/VM电源/网络配置、GC或重写历史。

## 1 固定来源

| 身份 | 值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| TASK_ID | `DATA-7B-R1` |
| 返修基线 T | `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50` |
| 原payload P | `9d73cc184a266e646ae827f0350f7c931d9faa25` |
| DATA-7B开发基线 B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 已验收DATA-7A内容 | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| 新分支建议 | `poc/data-pwm-d7b-r1` |
| main（保持不动） | `23e471cb936b421ee97e1250c3be06edf96f9937` |

开工先以Git协议和API核对T，读AGENTS/README/CONTRIBUTING_AI、原`reports/tasks/DATA-7B.md`、现有contract/report/handoff和本包全部审查结果。另读现有run/measure/evidence/trace源码，不能只看报告结论。

从T开独立worktree/个人分支；远端改变或建议分支已含未知工作时保留现场并报告，不覆盖。禁止把这轮当成“只修预算文档”：第2–5节均须闭环。

## 2 允许范围与冻结

允许修改：

- `scripts/dd1_d7b_run.py`、`scripts/dd1_d7b_measure.py`、`scripts/dd1_d7b_evidence_check.py`、必要的本任务`dd1_d7b_*`打包/离线辅助工具。
- 新增`tests/dd1_d7b/r1/`合成fixture和真实语义破坏自测；可新增同前缀独立测试脚本。
- `reports/dd1_d7b_contract.md`中针对测量定义、来源及状态的显式更正；不改案例或阈值。
- `reports/dd1_d7b_pwm_current.md`、`reports/dd1_d7b_review_fix_r1.md`、本轮/原DATA-7B handoff MD/JSON。
- 新增`reports/tasks/DATA-7B-R1.md`（本任务书逐字节副本）、`reports/tasks/DATA-7B-BUDGET-01.md`（真实52→56授权及59次历史，不补写新授权）。
- 新的`results/evidence/dd1_d7b_r1_<run_id>/`证据目录。

冻结：B已有全部跟踪路径；原DATA-7B任务书；`rtl/dd1_d7a_gray_ctrl.sv`；`scripts/dd1_d7b_trace.py`、TB、cases/golden表、7管wrapper；T的整个`results/evidence/dd1_d7b_r11_main/`。原始样本、deck/PWL、启动对账、日志不覆盖、不删除，不通过改旧证据消除失败。

如发现必须改冻结电路/输入或重新仿真才能解决，留下原因停止，不能自行推进。共享安全工具、runner/preflight/supply检查器及`dd1_d7b_validate_handoff.py`保持原样。

## 3 启动授权、账本、复用与发布

### 3.1 启动前拒绝和持久累计账

- 无模式参数应返回明确usage/拒绝，绝不进入native；模式冲突应拒绝。
- 原生入口必须显式授权，检查在任何远端准备动作前。`--dry`、自测、证据复核和离线重算均不得进入SSH/Spectre。
- 修复默认run_id：不能把`r%%Y...`当唯一ID；同名/已有目录应拒绝或生成真正唯一新ID，不能覆盖。
- 按任务持久累计启动/预留事件，重开进程、不同run_id和异常结束均不能清零。已有历史不丢失。每次preflight/DUT启动前检查剩余额度，不能运行后才发现越界。
- 同时保留“已请求/已确认启动/已完成/启动不确定”等事实，不能把失联或崩溃自动算0。保守占用额度与真实启动数应分列，防止既漏计又伪称全部已执行。
- 本轮历史事实是59/56，生产native入口在这份状态下必须拒绝继续；本返修任务又明确新增额度0。

用fake Link/runner证明：无模式、缺授权、边界55/56/59、跨实例重开、跨run、崩溃恢复、preflight内部一次启动及失败路径均不会越界或丢历史；断言被拒前外部调用数=0。只能用隔离合成账测试新计数，不真实启动验证额度护栏。

### 3.2 修复复用路径，禁止原生补齐

修正复用代码放进`static_probe()`却引用未定义变量的问题。复用必须在native循环进入任何preflight/DUT前完成分流；不要仅解析`--reuse`后仍新起进程。

复用前验证实际保留raw/log/deck/PWL的字节摘要、原生rc及preflight、器件源与电气参数一致。不能只抄账本里一个非空摘要、取glob第一个文件或硬编码tt/27。明确区分原生run身份、当前测量源码身份和本轮导出身份。

`--static-probe`修补与全部启动路径仅用mock证明，不在本轮操作guest验证。

### 3.3 发布前全量校验

用临时、尚不存在的整轮目录组装完整证据。完整性/语义校验失败不能移动成正式目录；发布成功与拒收都有独立测试，拒收前后的正式集合及摘要不变。不要再造跨多份旧正式文件的覆盖/回滚系统。

电气FAIL可以如实导出；虚假的PASS、缺必需文件/窗口/配对不能导出。历史预算违规必须保留独立状态；不能以它存在为由不检查其他语义，也不能靠改大上限消除它。

## 4 修复测量，并从原数据重算

1. 下降沿按对应原PWL/RTL脉冲查找，覆盖实际短脉冲和保护中止；不要只在完整窗口末500 ns查找。未找到不能回退到t1。黑码明确N/A，无导通沿不应虚构关断延迟。
2. 区分绝对时刻与延迟。给出`data_en`及真实反相器输出的相关50%交叉；电流上升/下降10%与90%用明确方向及阈值0.1/0.9×Ical，原始相邻样本夹持，缺失明确报告。
3. 持续入带必须一直保持到原预期关断沿之前且至少10 ns；先满足10 ns后离带不能叫持续稳定。截止时刻仍由原脉冲定义，不能为变绿延后/提前边界或扩大带宽。可另外报告最长入带片段，但不要把它与持续到关断前混用。
4. 关断时间应寻找后来真正持续低于150 nA的时刻；先低后反弹不代表永远不会再次关断。持续性覆盖本次关断段余下样本。
5. 分别积分正/负电流时，在每个线性插值零交叉处插点再积分。保留不等间隔时间、端点插值及SI单位；旧自测T3的错误黄金值也要按手算修正，不以净值恒等式替代分量正确性。
6. 由同一结果集合补齐四个收敛案例/五个窗口，含P30 code1父案例；dQ、峰值和有效交叉都重算。缺失必需配对或该有的交叉不是CONVERGED。

净电荷大多可直接从原完整分片重算。标定样本、必要电压边沿若不够，应先读本机留存raw；允许只读获取已知DATA-7B运行目录中的raw/log，优先本机镜像。不得通过调用原生runner“补产生”它们。禁止启动Virtuoso/OA/原生preflight、修改guest配置或读取/输出凭据值。

如果原raw不可获得，就标明对应校准/时间指标`BLOCKED_MISSING_RAW`；保留已经可复算的净电荷结果，不伪造标定样本，不改输入来重跑。

至少为持续稳定后离带、零交叉双极面积、先关断后反弹再永久关断、短脉冲下降沿、黑码无沿添加手算测试。随包探针是复现起点，不能把修后函数自己的返回值当黄金答案。

## 5 重建证据语义复核

复核器需从冻结任务/case表独立建立完整(case_id,window)集合、角色、模式、合法码域、tick/full-window映射、maxstep、输入沿和收敛配对。必须验证整数离散量的数学值，不通过float→int截断接受30.5；真实PSF采样时间仍保留非整数ps精度。

从提交字节重算或充分夹持的完整原生样本验证：

- 标定均值/min/max、OFF基线、标定末段、温度和section来源。
- `QLSB=Ical×T`、`Qexpected=QLSB×N`、净/正/负/尾电荷、末100 ns最大电流、峰值/时刻、相应电气判决；失败如实记录时允许证据一致性PASS。
- 两个安全场景的中止与恢复均齐备；N1独立原生负例与样本、实际接线diff、判决绑定；N2非零rc/supply_contract/零启动，不能只信YES。
- 所有必需deck/PWL及规范化摘要：修正`<case>.txt`与实际`<case>_pwl.txt`不一致；缺文件必须拒绝，不能if exists才检查。
- 完整收敛集合、dQ/峰值/交叉及各自限值；缺配对、空表或假CONVERGED明确失败。
- reconcile每行与TOTAL求和一致；启动日志/账记录能对应多少就写多少，不能从一个TOTAL字符串推出整轮守约。历史59保持违规；用户追加4只使授权52→56。
- 清单覆盖与文件集合一致、无自指摘要、分片顺序及完整性、源/运行/测量身份链。路径应是受约束相对路径，不越出证据根。

对随包8类篡改逐一复现后修复，再用同版检查器检验。每例重算清单摘要仍必须出现**与该语义破坏对应的新失败原因**。已有BUDGET_FAIL不能算作这些反例被检出。

`--selftest`必须从新checkout和已提交fixture/合成数据独立运行；缺ignored traceout/fake_evidence不允许SKIP却返回成功。既有测量器18/18、trace13/13只作历史对照，不代表已经覆盖新反例。

## 6 新证据与报告

在新R1证据目录保存纠正后的表、标定/边沿必要完整样本、收敛、自测、写保护/假Link记录和来源清单。可以逐字节复用原charge分片、deck/PWL，但保留原生run/source摘要，明确`reused_from=T`。不把本轮重新测量冒充新的原生结果。

原`dd1_d7b_r11_main`目录完全冻结。更正当前报告与handoff时，保留明确勘误说明和原T路径，不抹去旧交付曾报告错误的事实。

必须更正：

- 历史启动59、原授权52、追加后56、超额3；process_ledger58行的角色构成与仅27行被旧字符串识别的问题；environment中的42只是局部run，不是整轮总数。
- B..P新增818与B..T新增820的范围差别。
- 原报告EVIDENCE_STATUS=PASS/JSON计数27/超额0/scope COMPLETE及已披露“只预算失败”不可靠的结论。
- N1电流A与µA的列值错误、run身份；缺失的P30 code1收敛配对；标定温度/section缺项。
- 非N1末100 ns全局最大约20.65 nA（仍<150 nA），不能继续声称全都≤0.74 pA。
- P30 code1净电荷约0.30181 pC、目标约0.44796 pC，约少32.6%；±0.5 LSB目标通过的范围应写清，不能扩为光学有效位数或电流全程稳定。

新增`reports/dd1_d7b_review_fix_r1.md`逐项给出：旧T复现、根因、修改、修后正反例、实际命令/rc、仍未解决内容。自引用风险继续沿用原规则：报告/交接/manifest不写自身摘要；最终身份从固定Git blob与包外清单取得。

凭据回显单独记为事件，原值不入任务、报告、日志摘录或包。本任务不授权修改guest密码；不要用远端扫描PASS宣称该事件已经解除。

## 7 可重复验证、冻结和交付

1. 先在T原字节复现各组问题。所有fixture/假PROJ写ignored目录，不触碰正式证据；真实外部启动数必须0。
2. 完成工具修补；运行手算测量自测、入口/账本/复用/发布mock、8类语义篡改、真实交付重算、结构和来源检查。
3. 可在现有四态仿真器上对冻结RTL+冻结TB重验17份边沿（最多17次新RTL仿真）；新VCD日期/摘要与原native源身份分开，只比可复现边沿/PWL一致性，不替换旧身份，不改TB来凑一致。无需重跑DATA-7A全矩阵。
4. 核对B所有旧跟踪文件、冻结D7B电路/输入及原完整证据目录均不变；只允许第2节的工具/新证据/文档变化。
5. 原共享safety/provenance/device-count、staged/history/objects与空白检查按真实rc保留。既存不可达对象仍不得GC/打印/豁免，不可跳hooks。
6. 使用原结构验证器；结构PASS不能代替语义。历史预算违规继续列为事实，不能靠改成NOT_RUN或放宽预算洗白。需要保留PARTIAL等待用户处理历史偏差时如实写明。
7. 一枚功能/复算payload P1，再少量元数据提交D1；普通push新分支后Git/API双路回读。保留旧分支，不合main。审核包从固定Git blob生成，包含本任务、修补源码、自测、报告、新证据及冻结依赖的必要索引；不要漏SV/任务书，不含PDK、原raw/VCD、凭据或二进制。

若使用本包审查脚本作对照，保留其原文件，并明确它们是审查者工具；执行者自己新增的检查不能冒充审查者实测结果。先检查其中实际输入/输出路径再执行，禁止指向正式证据进行篡改测试。

## 8 停止与回执

```text
TASK_ID=DATA-7B-R1
BASE_SHA=adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50
REPAIR_SCOPE=MEASUREMENT_EVIDENCE_AND_EXECUTION_GUARDS_ONLY
NEW_SPECTRE_LAUNCHES=0
HISTORICAL_SPECTRE_LAUNCHES=59
HISTORICAL_AUTHORISED_CEILING=56
HISTORICAL_BUDGET_OVERRUN=3
NEW_OA_WRITES=0
CIRCUIT_AND_STIMULUS_CHANGED=NO
RAW_REUSED_FROM=<真实原生run及摘要>
NEW_RTL_SIMULATIONS=<实际值, 0..17>
EVIDENCE_INTEGRITY_STATUS=<实际结果>
MEASUREMENT_AND_GUARD_FIX_STATUS=<实际结果>
PWM_CURRENT_FEASIBILITY_TT=<按原判据重算的结果>
HISTORICAL_BUDGET_STATUS=VIOLATED_NOT_RETROACTIVELY_AUTHORISED
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

技术修补通过后，云端再给限定范围评审建议；是否接受历史执行超额由用户最终决定。不能为了重新获得“干净run”再仿真一轮，也不能自行进入下一阶段。
