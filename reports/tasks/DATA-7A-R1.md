# DATA-7A-R1：独立审核发现问题后的限定修补任务

**You have NO access to the user–ChatGPT conversation; this task, the included original DATA-7A task book, review evidence and the named repository are your sources.**

你是本地执行者Qoder。用户将本包转交给你时，授权的是修补DATA-7A并再次停在独立审核闸；不是开始下一阶段。请先完整阅读本文件、`REVIEW_DATA7A.md`和随包原始任务书 `original/TASK_DATA7A.md`。

## 1 固定源头、工作方式与允许范围

仓库：`https://github.com/LINboss666/microled-ic-ai-lab`。

待修交付基线D：`6a1f5a192f3f1618499335c4365d717bfcadef39`，原分支`poc/data-gray-d7a`。原DATA-6基线B：`731767519d1a51287eb5b7f4a6e4f9b8e613e990`；原payload P：`ef6737d40912b91197df4c0954eee6edcff55ee0`。先实际回读远端，不用聊天报告代替。若远端已有后续提交，读差异并报告，不把未经审定的新提交静默并入。

在独立工作区从D创建自己的新分支，建议`poc/data-gray-d7a-r1`。若已存在先检查，不覆盖。保护用户和队友的脏工作树，不reset、不stash、不改旧分支；不合并、不force、不改仓库可见性。

先读D中的`README.md`、`AGENTS.md`、`CONTRIBUTING_AI.md`、`.gitignore`、原任务书、contract、RTL、TB、全部`dd1_d7a_`检查和执行工具、交接报告及证据。按包内原`workflow/github-bridge-review-workflow/SKILL.md`执行，不能假定你看得到此前聊天。

本轮只准修改本轮新增的DATA-7A RTL/TB、同前缀脚本、contract/实现说明、DATA-7A交接文件及`results/evidence/dd1_d7a_*`。可新增同一前缀的回归脚本和`reports/tasks/DATA-7A-R1.md`保存此任务。原`reports/tasks/DATA-7A.md`逐字节冻结，不改原要求来让新结果通过。复制的`dd1_d7a_validate_handoff.py`保持原字节与语义。

两项共享安全工具维持D的内容，本轮不扩大任何例外；其它B已有被跟踪文件全部冻结。尤其冻结旧Spectre电路、Data-6证据/阈值、Scan电路、PDK、OA、CDF、symbol、cds.lib和人工美化图。不得为修数字协议进入VM、Spectre、Cadence或OA。

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

## 2 不得改变的数字功能

保留原任务书全部定义：单通道控制器、双实例验证；Pure码0=0区间、1..254=对应区间、255=256区间；Hybrid时间码0=0、1..62=对应区间、63=64区间。Pure的PAM码7只是符号码。

参考时钟100 MHz。Pure两种tick为30/50 ns，Hybrid为120/200 ns；窗口分别7.68/12.8 µs。START只预备，BLANK释放后的首个有效tick为t0；满窗口257/65个边界事件，完成后额外tick不能回卷发光。不新增tick分频器、TCON调度、SPI、LUT、50 MHz CDC或物理偏斜声明。

最终DATA_EN_B必须等于NOT DATA_EN。有效BLANK/fault脉冲至少20 ns，断言相位任意；更短脉冲只需在有效期间被组合门控关断，不宣称内部abort一定捕获。复位按至少1 µs测试。异步关断只验证RTL逻辑优先级，不宣称MOS延迟或硅上CDC安全。

## 3 五项必须修复和复验的内容

### R1：abort后恢复必须经过新加载、LATCH和START

包内`probes/probe_protocol.sv`直接使用D的原RTL复现了问题：BLANK使窗口abort后，仅补START即可用version1再次发光。

使abort后的显示授权失效，原配置不能被新START再次授权。分别测试BLANK和fault：仅释放异常、仅补START、新加载但未LATCH、没有新加载的LATCH等不完整恢复序列均不得使旧窗口发光；完整新加载/LATCH/START才可恢复。PAM保持和正常完成后的既定行为不能被随意更改。

### R2：建立可消费的新配置身份，验证两份配置

一次完整load只能被一次合法LATCH消费。相同灰码允许在新load事务中重复写入；`cfg_valid`持续高、总线未变、没有新load的第二个LATCH必须拒收且不能增加版本。没有新配置、load与LATCH同沿、缺字段、复位/安全切模式后的旧配置均按原契约拒收。

明确load接口的采样条件和完整性标志，落实next/load与display两个配置身份。运行期间装载next，不改变当前display/模式/PAM/宽度；窗口结束后再合法LATCH使用它。用真实第二窗口证明next被正确保存和消费，不能只验证当前窗口未变。abort后必须满足新的恢复事务要求，不能把旧pending标记当成新的恢复配置。

### R3：消除LATCH绕过安全切模式的通路

模式只有在`system_en=0, BLANK=1, 窗口不活动`时才可被接受。接收新模式后使旧显示授权失效，按新模式重新完成配置序列。不能通过system_en=1时的LATCH直接采纳原本被拒的请求模式，也不能因此清掉其错误。

独立测试安全状态切换与非安全切换，涵盖IDLE/ARMED/RUNNING/DONE/ABORT中的相关组合。协议冲突需有明确优先级和可观察拒收，尤其LATCH与START同沿、mode变化与LATCH同沿。无需扩展新功能；不能改成“非法请求也允许换模式”的新契约。

### R4：修复导出失败保护和身份闭环

在触碰正式证据前完成全部校验、解析、样本提取和完整临时产物构建。缺VCD、坏VCD、无响应样本、源码/trace摘要不符、缺工具、错误路径或任何必需闸失败应非零退出，实际正式证据保持不变。输出采用安全的原子替换；涉及多文件更新时避免失败留下新旧混合记录。

导出时对当前源码/TB/checker/reader、缓存run和trace身份逐项核对。不能只相信缓存JSON中的PASS计数，也不能将旧run重新标为新源码通过。

写保护回归必须在隔离目录预置所有实际目标CSV/JSON的非空内容，记录每个文件摘要和文件集合。覆盖dry、拒绝、编译失败、缺trace、坏trace、样本检查失败及导出准备失败；之后逐个比较。不要只哈希`write_guard.txt`。包内`probes/probe_export.py`只是诊断fixture，已经证明旧代码在缺trace后覆盖了三份CSV；不得指向真实旧证据执行这个破坏性诊断。

完善证据复核器：以模式/帧率/tick/时间码/PAM组成的键检查完整主矩阵，不只检查case_id；由原契约重新计算区间和端点，检查两实例各测量字段、版本、PAM稳定、trace/run/source身份、精确必需场景及六类突变。空表、重复组合、缺例、NaN/Infinity、X/Z、缺字段等均拒收。缺失或失败的预期负例不能只因标了`expect=refusal`就忽略。

### R5：修复真实激励覆盖，并使检查器验证激励存在

修正向量生成器把`pam_b/ht_b/pure_b`只写入说明而没有传给TB的问题。2018必须真正看到PAM 0→7及7→0，且低占空比关闭尾段PAM继续保持；2023必须真正看到安全切模式后的非零及满亮配置，并有有效t0、输出宽度、完成状态和版本检查。补测双实例不同灰码与不同PAM，分别测两者的实际输出起点与窗口完成边界，不能把从公共刺激推算出的相同t0当作已测两实例同步。

按原任务书补齐最短脉冲中间、窗口中部、终点前后等BLANK/fault场景；用20 ns最小有效宽度和多个非时钟沿相位验证。加入原R1/R2/R3反例及完整恢复正例。复位承诺内的正例满足至少1 µs；短复位若另外测试，分清范围。停钟测试说明其发生阶段，不能把仅在DONE停钟写为已验证运行中行为。

原始VCD中重复时间标记必须按原契约拒收；不要把它与正常同一时间块内多个不同信号变化混淆。保留同一时间块的毛刺检测。补明确的X和Z负例。

原六类真正RTL突变仍须全部重新编译、运行并被同一个未放宽的检查器拒收；新增配置新鲜度、abort重新授权、LATCH绕过模式等失效模型验证新增检查能抓错。不能只改JSON标签或黄金期望。区分“一个参考周期延后”和“一个tick延后”的实际刺激及文字。

## 4 工具、证据和交接修正

先探测本机工具，不假设与审核端相同。使用真实四态模拟器及独立综合前端；工具不可用就BLOCKED，不能伪造复跑。本轮审核的Linux Icarus12/Yosys0.33和执行端Windows新版并非同一二进制。可在任务范围提供跨平台工具定位或明确可复制的原工具命令，不能改系统全局配置或商业license。

更新contract和说明以准确反映实现，但不能改变上述功能要求。综合报告从实际日志得出，未知统计格式明确标无法解析，不能以空字典宣称统计成功。

保留D及更早版本中的失败记录，不重写历史。新证据采用新的run_id，说明它替代哪份旧证据；保留旧提交可追溯。不覆盖旧Data-6结果，不为美化报告重跑模拟。

review bundle包含完整RTL/TB/checker/runner、原任务书、R1任务书、contract、真实小型正负证据和交接文件；按必需文件集合机械查漏，再检验ZIP可打开及manifest全部摘要。完整VCD、工具安装物、二进制、PDK不提交。

先修完并验证所有功能/工具，再提交payload P1；此后交接提交D1只改约定的元数据。不得再次在P1之后修功能脚本却写“元数据提交”。如确有额外变更，更新payload语义并如实记录，而非自引用反复补SHA。

共享安全规则保持D的内容，运行正负测试及staged/history/objects、provenance、原器件数检查。原本机不可达对象继续如实标FAIL，不GC、不打印内容、不放松闸；可在干净隔离克隆完成本轮正常闸。未解决的新安全问题必须STOP，不能绕过hook。普通push到自己的新分支，以git与已授权可用API读取最终full SHA；缺一条明确PARTIAL。

## 5 必需交付及停止条件

更新DATA-7A人读MD/机器JSON，记录每个R1问题的根因、修补、旧版实测负结果、新版正负回归、命令/rc、计数、UNKNOWN和范围。原schema校验只证明结构，不能充当事实验证。

另提供简短修补报告，例如`reports/dd1_d7a_review_fix.md`，列出B..新D1及D..D1变更范围，引用新证据。允许新增范围仅限本任务，若需扩大范围先带事实STOP。

最终回执至少包含：任务号DATA-7A-R1、固定base D、原DATA-6基线B、新分支、payload P1、delivery D1、两路远端回读、1536主case/3072实例计数、控制场景实际执行数、原六类及新增突变检测结果、导出失败保护结果、R1五组问题关闭情况、NEW_SPECTRE_RUNS=0、NEW_OA_WRITES=0、所有未实现状态、报告和review bundle路径。

```text
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
NEXT_STAGE_AUTHORISED=NO
```

完成修补后停下，把新D1链接交回。不得自动进入DATA-7B、MOS PWM、八档PAM、电流集成、LUT、完整阵列、GUI美化或版图。用户与独立审核方另行决定下一阶段。
