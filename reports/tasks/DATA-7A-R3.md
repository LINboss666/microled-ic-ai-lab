# DATA-7A-R3：只修发布恢复和证据数值校验

**You have NO access to the user–ChatGPT conversation; this task brief, the included review evidence and the named repository are your sources.**

用户转交本包时，授权的是两组验收工具的限定修补。**不是重新设计PWM，不是启动DATA-7B。** 先完整读 `REVIEW_DATA7A_R2.md`、本任务和包内两个新诊断。

## 1. 固定来源、规则与冻结范围

仓库：`https://github.com/LINboss666/microled-ic-ai-lab`。

- 本轮起点T2：`01e078bbf545b9191539dc1c0de228a6d8e7749b`，分支 `poc/data-gray-d7a-r2`。
- R2 payload P2：`e151ebca59bc60df5e6e4d16fd6907e9787ded0a`。
- R2 handoff D2：`ff477ae7996a6efe74bdd60d971443810daf485d`。
- R1 tip T1：`0b64d1d62b851ac46e03a4d0250c8014984f2ef5`。
- 原DATA-6基线B：`731767519d1a51287eb5b7f4a6e4f9b8e613e990`。

先实际回读T2；远端有新提交则读差异并报告，不静默合入。独立工作区从T2建自己的 `poc/data-gray-d7a-r3`，同名存在先检查。保护用户/队友脏工作树；不reset、不stash、不force、不merge、不移动旧分支、不改可见性。

先读仓库 `README.md`、`AGENTS.md`、`CONTRIBUTING_AI.md`、`.gitignore`；原DATA-7A、R1、R2任务；contract；R2报告/交接；相关源码/证据；包内工作流。原三份任务及 `dd1_d7a_validate_handoff.py` 保持原字节。

**相对T2逐字节冻结**：

```text
rtl/dd1_d7a_gray_ctrl.sv
tests/dd1_d7a/tb_dd1_d7a_gray.sv
scripts/dd1_d7a_check.py
scripts/dd1_d7a_trace.py
reports/dd1_d7a_contract.md
scripts/repo_safety_rules.py
scripts/test_safety_rules.py
```

旧Spectre、Scan、Data-6电路与结果、PDK、OA、CDF、symbol、cds.lib、手工美化图继续冻结。不得进入VM、Cadence、Spectre或OA。不修改数字契约、测量阈值、时间端点来使工具通过。

只允许修改：`scripts/dd1_d7a_run.py` 中发布/恢复/其失败处理与对应工具自测；`scripts/dd1_d7a_evidence_check.py` 的数值解析/比较/自测；同前缀新回归脚本；必要的同前缀报告、DATA-7A交接、小型证据和打包必需文件表。可保存本任务为 `reports/tasks/DATA-7A-R3.md`，新增 `reports/dd1_d7a_review_fix_r3.md`。如需改冻结电路或扩范围，带证据STOP。

已通过的行为保持：单通道、双实例；Pure 0/1..254/255对应0/c/256区间；Hybrid 0/1..62/63对应0/c/64区间；100MHz参考，Pure 30/50ns、Hybrid120/200ns tick；完整窗口257/65边界事件，完成后不得重亮；PAM只是选择码，不是八档电流；最终DATA_EN_B为DATA_EN反相；abort后新load/LATCH/START才恢复。完整定义见冻结contract和原任务。

## 2. A：修复事务恢复与暂存失败处理

先用未修改T2，在隔离fixture重现 `reviewer/probe_publish_recovery.py`。其rc=0表示四个缺陷复现，不是工具通过。禁止指向真实 `results/evidence` 注入故障。

必须关闭：

1. **读回真实备份位置。** export写 `<run_dir>/publish_backup`，marker记录了路径；恢复却默认去全局目录。恢复必须使用并核对同一事务记录的备份与文件集合，不能靠调用者碰巧传入正确参数。
2. **恢复不完整时保留未完成状态。** 缺失/摘要错误/不可读备份、写回失败等，应非零退出，保留marker及可恢复证据。第一次、第二次、重复调用都继续拒绝新发布，直到旧状态真正逐项恢复并核验。不能返回complete=false却删除marker。
3. **损坏marker不能当空事务成功。** 坏JSON、缺必要字段、错误字段类型或不完整事务身份应明确拒收，保留现场。不得以空`previous`的0/0判完整。对合法“原先不存在”的目标，必须记录并按不存在状态恢复；不能读取不存在文件的SHA。
4. **暂存阶段可捕获失败也要处理。** 将备份、marker写入、暂存、替换、校验和清理的错误边界说明白。可恢复的一次I/O失败后恢复旧有效集合并清理本事务临时文件；若回滚本身也失败，保留未完成状态并持续拒收，绝不能写“已恢复”。只清理本事务记录的临时文件，不扫描删除其它阶段或其它文件的`.new`。

不要求硬件级多文件断电原子，不要求部署数据库。保留“可捕获失败回滚、进程中断后依赖marker恢复”的边界，但这两条机制必须真实工作。未恢复前不能发起新事务覆盖原备份/marker，不能把旧新混合内容当有效交付。

每例从干净新fixture开始，保护所有目标及一个无关文件，保存前后文件集合和摘要、marker/备份状态、命中阶段、实际rc。至少测：

- 普通发布正例；首个/中间/最后替换可捕获失败回滚。
- 第二个暂存写失败；备份准备失败；回滚/清理再失败时的真实拒收状态。
- 使用非默认run目录中断于替换中间：不传人工备份路径也能按marker恢复，逐字节还原旧集合。
- marker损坏；缺一份备份；备份摘要错误；恢复写入失败。连续重试至少两次都不能丢状态或越过拒收；补全可恢复条件后再成功恢复。
- 对“之前不存在”的目标，恢复到不存在；无关文件保持不变。

真实入口 `do_export` 的恢复前置条件需要直接覆盖，不能只测低层函数再声称入口验证过。可以用“到达builder就抛诊断异常”的隔离边界探针证明恢复失败时没有越过门槛，但必须标为边界诊断，不能伪造build或export PASS。保持原正常发布和既有写保护用例的意义，不改成任意异常都通过。

## 3. B：数值解析必须保留误差和整数类型

先用 `reviewer/probe_numeric_precision.py` 在隔离证据副本复现：case2的30ns改成30.5ns、257次改成257.5次，刷新CSV摘要后，原R2复核器仍53项全PASS。当前正式R2数据没有这两种错误，不能说旧电路实测晚0.5ns。

消除用 `int(float(value))` 先截断再判等的路径：

- 码、段数、版本、边界次数等离散计数必须验证为整数再比较；小数不能靠截断成为合法整数。
- 时间量按明确单位精确比较，可用Decimal或整数ps；保留已有1ps/1ns精度规则，不能靠向下取整、round或新增容差吞掉0.5ns误差。
- 继续拒收非有限值、空/缺字段、非法组合；保留契约全集、区间/端点重算及原语义自测。不要从CSV错误期望或RTL内部算法反推黄金值。

在刷新manifest摘要后的自洽fixture上，至少加入错误width、错误endpoint、小数segments、小数boundary-count等明确负例；正常实际证据仍通过。报告各例命中的具体拒收项，不仅报告“非零”。若时间格式允许小数，区分合法表示与真正不符合契约，不是简单禁止所有小数。

## 4. 验证策略和证据复用边界

先做上述针对性工具回归，检查冻结文件摘要。**不为本轮工具修补重新设计或重画电路。**

本轮可复用R2已有、可核对身份的冻结RTL/TB/checker/reader波形，但必须说明复用的run_id、真实生成源摘要、VCD摘要、保留位置，重新判读验证与本轮工具导出的结果，不得把旧仿真改名成新仿真。复用必须建立在上述四类源字节不变且原波形真实存在的基础上；缺波形/身份不符应BLOCKED或重跑冻结数字回归，不能信缓存JSON。

如重新仿真，仍须1536主case（Pure512、Hybrid1024）、3072实例，保留R2的43控制+6混码及16真实模型；工具可额外用例，不删旧要求。若只复用，明确 `NEW_RTL_SIMULATIONS` 实测数量及 `REUSED_RTL_RUN`，不能声称“本轮新跑全部”。完整控制/突变等证据来源必须可追溯。

源与证据导出身份更新不能自相矛盾：manifest记录本轮真实发布的字节、实际工具源码；波形仍对应冻结RTL/TB/checker/reader。不能借此放宽旧的源漂移拒收。

只需在本机实测工具下完成工具链，不要求为Linux Yosys0.33重写统计解析。R2对不识别格式的非零退出/summary失败/下游拒收已正确，不得改绿。checker/entry/evidence原自测及新自测、发布/恢复正反例、正式证据复核、schema结构校验、安全规则双向例、staged/history/objects、来源/器件数照旧。

执行者本机既存不可达blob仍如实FAIL，保持原样，不GC、不打印内容、不放宽规则；新安全异常必须STOP。每个问题最多三次修补尝试，超过按仓库规则停止并留证据。

## 5. 提交与交接

先完成工具修改和全部必需验证，再提交payload P3。后续handoff D3只改约定元数据；若又改功能，必须重新如实界定payload，不能把代码藏进“元数据”提交。

交付包括：本任务逐字节副本、`reports/dd1_d7a_review_fix_r3.md`（T2原负结果、根因、修补、正确行为正反例、命令/rc、复用/新跑区别、未解项）、DATA-7A交接MD/JSON、真实小型证据与自包含bundle。原任务、规则、验证器、电路文件做逐字节冻结核对。

普通推送自己的R3分支；实际git与已授权可用API回读最终full SHA，缺一路就明确PARTIAL。bundle从Git blob取字节，按必需集合查漏，核ZIP/manifest每项摘要和字节数。不含完整VCD、工具二进制、PDK或秘密。

```text
TASK_ID=DATA-7A-R3
BASE_SHA=01e078bbf545b9191539dc1c0de228a6d8e7749b
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
NEXT_STAGE_AUTHORISED=NO
NEW_SPECTRE_RUNS=0
NEW_OA_WRITES=0
PWM_MOS_IMPLEMENTATION=NOT_RUN
PAM_8LEVEL_ANALOG_IMPLEMENTATION=NOT_RUN
HYBRID_CURRENT_INTEGRATION=NOT_RUN
GRAY_LUT_IMPLEMENTATION=NOT_RUN
PHYSICAL_CDC_AND_SKEW=NOT_VERIFIED
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
LAYOUT_DRC_LVS_PEX=NOT_RUN
SOA_SIGNOFF=NO
```

完成后停下交回独立审核。最终接受、合并和进入下一阶段仍由用户决定；不要自动推进MOS PWM、八档PAM、电流集成、LUT、阵列、版图或VM/Cadence/OA。
