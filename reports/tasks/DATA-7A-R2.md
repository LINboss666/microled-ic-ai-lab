# DATA-7A-R2：恢复事务、检查器和发布完整性的限定修补

**You have NO access to the user–ChatGPT conversation; this task brief, the included prior task books/review records and the named repository are your sources.**

你是本地执行者 Qoder。用户把本任务包转交给你时，授权的是继续修补 DATA-7A 数字逻辑与验收工具，并停在独立复审闸。**不授权 DATA-7B、MOS PWM、八档 PAM、电流集成、LUT、阵列或版图。**

## 1. 固定起点与先读文件

仓库：`https://github.com/LINboss666/microled-ic-ai-lab`。

| 来源 | full SHA |
|---|---|
| 本轮必须从此开始，R1 最终远端 tip T1 | `0b64d1d62b851ac46e03a4d0250c8014984f2ef5` |
| R1 payload P1 | `b0196f995962e8098e218aabf86e5864792b7f8c` |
| R1 handoff D1 | `202f11c63d7163487af3e5f33843e4a742c9115a` |
| 原 DATA-7A 待修交付 D | `6a1f5a192f3f1618499335c4365d717bfcadef39` |
| DATA-6 已有基线 B | `731767519d1a51287eb5b7f4a6e4f9b8e613e990` |

先实际回读远端 `poc/data-gray-d7a-r1`，核对 T1。若分支已有新提交，读取并报告差异，不静默纳入未审核修改。用独立 worktree/工作区，从 T1 新建 `poc/data-gray-d7a-r2`；同名分支存在时先核查，不覆盖。保护用户和队友的脏工作区；不 reset、stash、force、改可见性、合并或移动旧分支。

必须完整阅读：

- 仓库 `AGENTS.md`、`README.md`、`CONTRIBUTING_AI.md`、`.gitignore`。
- 原 `reports/tasks/DATA-7A.md`、`reports/tasks/DATA-7A-R1.md`，这两份保持原字节。
- 本包 `REVIEW_DATA7A_R1.md`、所附此前 `original/REVIEW_DATA7A.md`、工作流 `workflow/github-bridge-review-workflow/SKILL.md` 及其引用规范。
- RTL/TB、全部 `scripts/dd1_d7a_*`、contract、R1 修补报告、交接 MD/JSON、正式小型证据。
- 本包 `reviewer/` 下的独立诊断代码及 `evidence/` 下实测输出。程序退出 0 表示缺陷复现成功，不能把诊断程序的 0 当成 DUT PASS。

本包的 `reviewer/repo/` 是从 T1 Git blob 取得的审查快照，不是完整 Git 工作区。实际修补以远端 T1 克隆为准。不要把本包的旧快照覆盖到自己的新实现上。

## 2. 范围和冻结项

允许修补：本轮 DATA-7A 的 RTL/TB、`dd1_d7a_` 前缀脚本、contract/实现说明、同前缀结果与报告、DATA-7A 交接 MD/JSON。可新增同前缀回归、`reports/dd1_d7a_review_fix_r2.md`，并逐字节保存本任务为 `reports/tasks/DATA-7A-R2.md`。

以下相对 T1 保持原字节：原 DATA-7A/R1 任务书、`scripts/dd1_d7a_validate_handoff.py`、两份共享安全规则与其它共享工具。B 已有的所有电路/证据继续冻结，尤其 Spectre、Scan、Data-6、PDK、OA、CDF、symbol、cds.lib、人工美化图。不得进入 VM、Cadence、Spectre 或 OA 来处理数字协议。

```text
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

不能修改原功能、时间端点、旧负结果或阈值来消除本轮问题；跨范围的改动需求应带证据 STOP。

## 3. 保持的数字契约

只做单通道 RTL 控制器，用两个实例验证；不是上千个通道。

- Pure：码 0=0 区间，1..254=c 区间，255=256 区间；PAM=7 是符号码，不是 15 µA。
- Hybrid：时间码 0=0，1..62=c，63=64 区间；3-bit PAM 是保持的选择码，八档模拟电流尚未定义和实现。
- 参考时钟 100 MHz；Pure tick 30/50 ns，Hybrid tick 120/200 ns，对应两种窗口 7.680/12.800 µs。tick 是同域使能。
- START 只预备；BLANK 释放后的首个有效 tick 消费边沿为 t0。完整窗口需 257/65 个边界事件；完成后额外 tick 不得重亮。
- DATA_EN_B 是最终 DATA_EN 的反相；PAM 从合法 LATCH 保持到下一合法 LATCH，包括 PWM 关闭尾段和 abort 后。
- 有效 BLANK/fault 至少 20 ns，断言相位可不在时钟沿；复位至少 1 µs。更短脉冲不承诺内部 abort 捕获；不把 RTL 组合关断冒充 MOS 延迟/硅上 CDC。
- 运行中可准备 next，当前 display/模式/PAM/宽度不能改变。一次完整 load 只能消费一次；相同码的新事务仍合法；load 与 LATCH 同沿拒收。
- 模式只在 `system_en=0, blank=1, 窗口不活动` 时接受；LATCH 不能采纳被拒模式，也不能擦除同沿错误。abort 后必须有新的 load/LATCH/START 才能恢复。
- 不新增 tick 分频器、976/977 调度、50 MHz CDC、SPI、帧存储、LUT 或物理偏斜签核。

## 4. 必须修补和验证的五组问题

### F1：撤销 abort 前旧 pending，补 next 的第二窗口正例

先在 T1 原字节复现 `probe_abort_pending.sv`：运行时预存 next=5；保持 `cfg_valid=1`；BLANK 或 fault 中止；不再产生新 load，只有 LATCH/START，就会 version1→2 并重亮。

使 abort 同时撤销旧显示授权和旧 pending 的恢复资格。明确 abort 与 load/LATCH/START 同沿的优先级；有效 abort 不能被同沿其它路径重新授权。PAM 保持规则不变。

分别对 BLANK/fault 测：只释放、只 START、只有新 load 没有 LATCH、无新 load 的 LATCH、**中止前已有 pending 后再 LATCH/START**，全部必须保持黑；真正中止后新 load/LATCH/START 才能恢复。也测中止后先发无效请求，再完整恢复。用 trace 同时证明 load 边沿、授权、版本、实际导通。

按 R1 已有要求落实 load/next 与 display 的配置身份，明确字段采样、完整性和保持条件。补真实两个窗口：窗口 A 运行时准备 next B，A 的输出和 PAM 不变；正常 DONE 后合法 LATCH B；第二窗口必须按 B 的码/PAM/宽度工作且只消费一次。至少包含 Pure 与 Hybrid、相同码的新 load、不同码/PAM。不能用只检查“当前不变”的 profile 1 代替第二窗口。

### F2：发布中途失败保护、独立故障 fixture、综合状态统一

先在隔离目录复现 `probe_publish_failure.py`，不得把它指向真实正式证据。原函数在第二次 rename 失败时已改第一文件、删第二文件、留旧 manifest。

保留发布前全量校验/重判优点。实现安全的整套发布/恢复机制：对可捕获 I/O 失败，非零返回后原有效文件集合及每份旧字节必须完整；不能遗留有效的新旧混合记录或丢文件。单文件原子替换不能被描述成多文件原子。可选有恢复记录的备份/回滚方案，或在既有边界内的完整代际方案；如需改正式交付路径或扩展范围，先提出方案 STOP。明确强杀/断电的保证边界，不支持时不能声称支持；未完成事务必须可识别，恢复前不能把它当成有效交付。

写保护每个模式从同一份已验证、可导出的干净 run **重新复制**，每例只注入自己的错误。记录：故障、命中阶段/原因、rc、所有目标文件前后 SHA、缺失/新增文件、临时文件和恢复状态。不能“任何异常都算该模式通过”。

至少覆盖 dry、输入拒收、编译失败、缺 trace、坏 trace、样本提取/跨锚点失败、源码过期、行数错误、trace 摘要错误、闸失败、导出准备失败，以及发布第一个/中间/最后目标替换失败。为证明坏 VCD 解析和样本路径确实走到，可在隔离 fixture 同步更新输入摘要后注入对应错误，不能让 hash 不符先挡住。保留正常发布正例。目标文件数量由真实发布集合产生，修正“8 写成 9”。

在 `synth_summary` 序列化前形成最终失败状态。入口 rc、持久状态、下游 gate 必须一致；`UNPARSED_FORMAT` 不能被 summary 的 `problems=[]` 和 Yosys 工具 rc=0洗成通过。补该负例。统计可支持两种格式或明确拒收，不要求安装与审核端相同版本。原始 Yosys 结构通过与统计解析失败分开记录。

### F3：功能突变必须真的产生相应错误

原 `stale_latch_accepted`、`latch_adopts_mode` 只屏蔽错误位，功能门仍在。不要删除旧失败/旧错误说明；明确作废其“功能类覆盖”的解释。

新增/修正真正功能 mutant：

1. 让没有新 load 的第二次 LATCH 真被接受并改变版本/显示。刺激必须让 `cfg_valid=1` 等其它条件合法，避免“不完整配置”先挡住。
2. 让 LATCH 真绕过模式限制、采纳未安全接受的模式，观察实际模式/PAM/窗口变化。
3. abort 重授权原 mutant 继续保留，并补 F1 的旧 pending 失效模型/反例。

每个先记录实际 patch、源码 SHA、真实编译/仿真和 trace，**先独立断言声称的故障已产生**，再证明相同未放宽 checker 拒收。原六类全保留并重跑；原两项丢错误位可作为附加诊断类，但不能冒充功能类。总类数可增加，报告分清类别，不能固定写“9/9”掩盖模型变化。

### F4：混码分别测量真实输出起点

先复现 `probe_mixed_start.py` 的真实 B-only 输出延迟 mutant：A 在1435 ns亮，B 在1445 ns亮，B 宽度不变，原混码仍6/6 PASS。

在混码检查中，对每个非零通道分别测实际 DATA_EN 开/关沿、精确 ps 宽度、与契约 t0/端点的关系、DONE 和窗后关闭；不要仅比较由公共输入推导的两个 t0，也不要向下取整区间数掩盖小于 tick 的偏差。黑码按无导通处理、另查窗口完成，不虚构其亮起沿。

保持六个合法混码场景，并使 B-only 晚一个参考周期、晚一个 tick、只移动一个边沿/宽度错误等真正失效被相同检查拒收。保留两实例不同时间码、不同 PAM 及 0/满码覆盖。明确这是逻辑边沿验证，不是物理 skew 签核。

### F5：复核器按契约检查组合与语义

先在隔离 evidence 副本复现 `probe_evidence_duplicate.py`：保留 case_id=2、复制 case1其它字段并更新 manifest 摘要，1535 个组合仍被原40项判PASS。真实 T1 矩阵本身是完整的，不能把此工具反例写成 T1 CSV 已坏。

复核器应由固定契约生成精确 `(mode,frame,tick,code,pam)` 期望集合，查唯一、缺项、额外项和合法值；不能只数 case_id。独立从码值/模式重算区间、窗口边界，检查两实例测量、PAM/版本、必要字段、finite值、身份链以及规定场景/功能突变确实执行。

必需负例要求出现、实际拒收且原因符合预期；`expect=refusal` 不能包容任意 FAIL/NOT_RUN/缺刺激。保持哈希匹配要求，但增加“更新哈希后语义仍错误”的负例，如重复组合、错误 exp_intervals、缺必需场景、错误预期拒收原因等。不得通过从 RTL 内部算法抄预期来闭环。

## 5. 执行和验收顺序

1. 探测本机工具和版本，复现 T1 五组问题。记录原始负结果，避免把我提供的诊断程序当回归 PASS。
2. 在允许范围修实现与验收工具；将每组新增反例转成修后应通过的正确行为回归。每个问题按仓库规定最多三次修补尝试，超过带证据 STOP。
3. 对最终同一版源码重跑 selftest、dry、1536 主矩阵、全部控制和混码场景、原六类及新增真实功能突变、综合、独立写保护与发布失败测试、导出及证据复核。旧 Data-6 不重跑。
4. 1536 主矩阵依旧 Pure512+Hybrid1024、3072实例观测；原36控制/6混码不能缩减，可因新增边界扩充。分别报告总数、通过、预期拒收及拒收原因，不把预期拒收混算成正例 PASS。
5. 记录工具差异和任何兼容改动。若原 TB 在 Icarus12不兼容，可在允许范围修为等价合法写法，并核对激励不变；不要把兼容副本的摘要冒充原 TB。
6. 工具缺失或新安全异常应 BLOCKED；不得用缓存/报告替代实测。安全规则双向例、staged/history/objects、provenance/device-count照旧执行。原本机不可达blob保持原样，如实FAIL；可在干净隔离克隆完成正常闸，不GC、不放宽、不打印内容。

## 6. 交付、payload、远端回读和停止

先完成所有功能/脚本/回归/证据，再提交 payload **P2**。后续 handoff **D2** 只写约定元数据，列清所有提交；若又改功能必须重新定义真实 payload，不能再冒充元数据。原任务书/验证器/冻结项做逐字节核验。

交付至少包括：

- `reports/dd1_d7a_review_fix_r2.md`：五组根因、T1负结果、修改、修后正负证据、实际命令/rc和未解项。
- DATA-7A 交接 MD/JSON：base=T1、B、分支、真实 P2/D2/tip语义、范围、每组修补状态、run_id、全部计数和保留状态。
- 必需的 RTL/TB、原任务/R1/R2任务、contract、runner/checker/reader/复核器、有效的小型证据与失败说明。
- reviewer bundle：从提交 blob 打包，按机械必需集合查漏、ZIP完整性、每项SHA与字节数校验。`--mode history`和内容扫描照旧；不提交完整VCD、工具二进制、PDK或隐私。
- 普通推送自己的 R2 分支。由实际 git 回读和已授权可用 API 回读最终 full SHA；某路不可用就明确 PARTIAL，不能借聊天报告补读。

不要因自行宣布“五项关闭”而进入下一阶段。完成后输出下面状态及 full tip 链接，把包交回独立审核：

```text
TASK_ID=DATA-7A-R2
BASE_SHA=0b64d1d62b851ac46e03a4d0250c8014984f2ef5
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
NEXT_STAGE_AUTHORISED=NO
NEW_SPECTRE_RUNS=0
NEW_OA_WRITES=0
```
