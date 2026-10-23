# DATA-7B-R3 独立复审：限定 GO

审核日期：2026-10-23。

**审核建议：GO，限定为 R3 的账户非法状态修补、交接勘误，以及既有冻结 TT 证据的可复核性收口。F1、F2 均关闭，无新增阻断返修项，不要求再开 R4。**

这不是预算合规 PASS，也不是完整 PWM+PAM 芯片或流片签核。历史实际 59 次、授权 56 次、超出 3 次仍为违规，`BUDGET_RESPECTED` 继续 FAIL；处置与最终接受由用户决定。审核方未登记接受版本、未合并、未推送、未授权下一阶段。

## 1 审核对象与实际访问

仓库：[LINboss666/microled-ic-ai-lab](https://github.com/LINboss666/microled-ic-ai-lab)。

| 身份 | 完整值 |
|---|---|
| 本次实际读取的远端 tip | `f9fd09b184a69a27cdb409205dfd4f4151408a23` |
| R3 基线 / 被审 R2 | `b3fe93c17de014cb16031438ce28c7152dd0020f` |
| R3 初始载荷 P3 | `242f43fdd4c775d4e92ebddde548e65b75aec402` |
| ZIP 构建来源 | `e69dee995f47032ffa8a08adc7912afd97eb5b03` |
| 构建来源与被审 tip 的共同 tree | `6a991f9e142d83a02a1d6a81c3773a7ecc2abc56` |
| main，实测未动 | `23e471cb936b421ee97e1250c3be06edf96f9937` |

本方通过 `git ls-remote` 固定远端 SHA，再 fetch 并以 detached worktree 读取真实提交、完整 base..tip 差异、项目 AGENTS/README、修改的工具和全部新增脚本、报告及证据。网页读取仍失败，因此不声称本方完成了 GitHub HTML/API 双路回读。执行方的 API 回执仍标为其记录；本方直接核验的是 Git 远端、提交内字节与用户上传的原 ZIP。

当前完整区间共 10 个提交：初始 P3、验证工具修正与验证记录、文档/回读记录，以及后续空提交。不能把整个区间概括成“P3 后全是无代码元数据”：`6fdae412…` 对新验证辅助的 CSV 末尾空白处理确有修正；最终辅助工具摘要已单独核对。

## 2 上传 ZIP 的精确核验

| 检查 | 实测 |
|---|---|
| ZIP 字节数 | 329,067 B |
| ZIP SHA-256 | `325b71c46dbdefde6dcefdc79751ad041ac265c64aca79f0d30c66709481a1a6` |
| CRC / 文件集合 / 逐项清单摘要 | 全部通过 |
| 成员数 | 56 |
| manifest 条目数 | 54 |
| 真正的仓库源成员 | 53/53 与固定 tip 的 Git blob 完全相同 |
| 自检入口 | `verify_package.py` rc=0，54 files listed / 0 unlisted |
| 单独上传的 MD | 22,339 B；与 ZIP 内对应报告逐字节相同 |
| ZIP 构建 tree 与 tip tree | 相同，后续提交未改变该 tree |

精确口径：53 个仓库成员 + 1 个打包器生成的 README + MANIFEST + 自检脚本 = 56。生成的 README 也被列入 54 条 manifest，它不是仓库根目录 README 的副本。因而“全部成员都是 Git blob”“README 不在清单”“清单 53 条”这些包内说明不准确；实际源码成员、样本索引和报告没有字节错配。该说明问题记为非阻断注记，不把它当作电路或账户修补失败。

摘要记在构建后的 `7d5a0373…` 空提交信息，而不是写入包内文件，避免了归档自指。构建来源虽早于最终 tip，但共同 tree 一致，本方又逐成员核对了当前源码，因此本次 ZIP 确实可用于审查该 tip。

## 3 全树冻结与修改范围

base..tip 全量比较：6 条既有路径修改、20 条新增、0 删除，共 26 条差异路径。

6 条修改分别是 Account runner、evidence checker、交接 MD/JSON、contract 的一处口径勘误和 R2 报告的解释勘误。新增包括 R3 任务书、修补报告、两个离线脚本以及两个已提交的 R3 验证目录。旧验证目录是已披露历史，权威目录为 `dd1_d7b_r3_r20261022_180059_efda9d`。

| 冻结面 | 实际比较路径数 | blob/mode 差异 |
|---|---:|---:|
| 原开发 B 全部路径 | 1,107 | 0 |
| 原 D7B 证据 | 805 | 0 |
| R1 证据 | 284 | 0 |
| R2 证据 | 287 | 0 |
| case / golden / TB | 3 | 0 |
| measure 与两个 trace 解析器 | 3 | 0 |
| 共享安全、原生 runner/preflight、结构验证工具 | 12 | 0 |

R3 任务书 10,054 B / SHA-256 `2eb933bc0d8ddd91f34f50bee269e35a0576d0fee8caaf681729e7d1d3defaa1`，已与本方上轮原任务书逐字节比较一致。

R2 当前 286 项 manifest 再次逐项哈希核对无差异；其覆盖 21,264,382 B，加上 manifest 自身为目录 287 文件 / 21,323,343 B。本方没有修改这些文件。

## 4 F1：实际关闭

源码层面：Account 在装载后、恢复与重写前检查全部行；`counts()` 与 `_restamp()` 同样检查，reserve 经 counts 拒绝被破坏的内存状态。合法状态集合为五种精确拼写，未知/空/大小写或空白变体不被当作免费。Ledger 的 DONE 协议没有被误改。复核器对所有账户行新增单独的 `ACCOUNT_STATES_VALID`，缺失账户也明确失败。

本方保留上轮独立仪器原字节，分别对未改的 R2 基线与最终 R3 执行，不从执行方的表格倒推出结果。

| 本方诊断 | 未改 R2 | 最终 R3 |
|---|---|---|
| 未知状态重开 | 接受、占额变 0、第二次预留成功 | 拒绝，第二次预留未发生 |
| 空状态重开 | 同上 | 拒绝，第二次预留未发生 |
| 同步 roll-up 并重封 manifest 的未知态伪造包 | 无新增失败 | 新增失败恰为 ACCOUNT_STATES_VALID |
| 仪器结果 | rc=0，缺陷复现 | rc=1，all_requirements_met=true |

本方检查了 JSON 的逐项字段，`semantic_corruption_escaped=false`，没有只把 rc=1 当成通过。R3 suite 对空状态伪造包也实际报出同一独立失败；文件字节保护、内存注入拒绝和合法五态计费保持通过。当前发布账户仍是 59 CONFIRMED + 274 REFUSED_NO_LAUNCH，333 行合法状态，不把合成故障注入说成又发生了实际超支。

## 5 本方实际重放命令

每条命令的完整参数、单独 rc 与原始输出保存在 `checks/`；共运行 13 条离线命令。

| 检查 | 本方结果 |
|---|---|
| run selftest | rc=0，14 checks |
| 原 R2 包复核 | rc=1，44 项唯一失败 BUDGET_RESPECTED |
| evidence selftest，显式当前 R2 输入 | rc=0，16/16，逐项新增失败被点名 |
| R1 guards | rc=0，8 组 |
| R2 guards，显式当前 R2 输入 | rc=0，14/14 |
| R3 guards，最终工具 | rc=0，8/8，未知与空状态均实际出现 ACCOUNT_STATES_VALID |
| 同一 R3 guards，未改 R2 工具 | rc=0，8/8 重现/保持项，清楚分开工具目录 |
| 本方独立仪器，R2 / R3 | rc=0 复现 / rc=1 关闭，JSON 逐项核对 |
| handoff 结构 | rc=0；仅结构，不代替事实核对 |
| ZIP 自检 | rc=0；另有本方逐 Git blob 核对 |
| provenance | rc=0，434 files / 541 labelled lines / 0 violations |
| 本克隆 history 安全闸 | rc=0，四类计数均为 0，详见原始日志 |

measure 与 trace 均与 R2 相同，本轮以 blob 身份确认其复用，未再运行它们的自测来增加计数。R2 包复核本身仍重新解析交付证据。没有新 Icarus/RTL 仿真、没有 Spectre/preflight、没有 OA、SSH、VM 或凭据操作。

## 6 F2：交接与解释勘误关闭

本方从真实产物核对，以下更正均成立：

- manifest 与含 manifest 的目录数量/字节口径已分开。
- `source_identity` 保留 R2 exporter 的真实 runner 摘要 `dea050a5685eded854502f85c45f8f356acb006e5c421fd084513da5d39b70bc`；R3 的四份验证工具另列且全数匹配当前字节。权威目录 tools_identity 的 10 条也全匹配。
- 当轮 RTL 成本为 0，17 次明确属于 R1 历史；没有用改来源摘要冒充重新产生样本。
- R2 相对 H 的 8 个既有修改 / 291 新增，与 R3 相对自身 base 的 6 修改 / 20 新增分别列出。
- 电流序列 26 条复用、R1 新增 1 个标定带、R2 新增 2 个片段，未说成新仿真。
- 边沿四位小数 ns 对应 0.1 ps；重复标题已合并。
- 顶层保留 R2 exporter 身份，R3 对象单列修补与验证身份；这是角色区分，不应把顶层 R2 SHA 擅自替换为 R3 验证器 SHA。

对“不稳定原因”的说明，本方用独立插值代码按合同的 **Ical±5%** 重算交付电流采样。23 个 NOT_SETTLED 窗口里，只有三条最长采样界定带内段不足 10 ns：

| 窗口 | 采样界定 ns | 连续插值 ns |
|---|---:|---:|
| P30-C001 | 8.610590 | 9.092380 |
| CVG-P30-C001 | 8.933460 | 9.037823 |
| SLEW-P30-C001 | 4.175934 | 4.645542 |

C002 约 38.6106 ns（连续 39.0929 ns）、C255 约 7658.6106 ns（连续 7659.0929 ns），都远超过 10 ns。多数长窗仍在自身 deadline 前离带，未满足保持至截止左侧的定义。因此保留 23 个 NOT_SETTLED 判决并纠正“都因为时长不足”的解释是正确的。采样界定与连续插值两种数字不能混写；本方上轮的 9.0924 / 39.0929 是连续口径，与本次更正一致。

## 7 非阻断注记

以下如实留在本次审核中，不另开 R4，也不要求改变已经冻结的数据或等待一次新的全矩阵验证。

1. **打包 README 的口径。** 实际 54 条 manifest 包括生成的 README，53 个仓库成员才是逐 Git blob 相同的来源。README 内“53、README 不入清单、全部字节来自 Git”的措辞应按本报告 §2 解释。已有归档身份核验成立；后续正常维护时修说明即可。
2. **辅助断言可收紧。** R3 guards 的 S6/S7 使用 `new == named`，当两者都为空时单条探针会误真；宜直接要求 `new == ['ACCOUNT_STATES_VALID']`。验证汇总器对外部仪器主要按 rc=1 判断，也宜读取 JSON 字段。当前这两项没有使本轮结论变空洞：本方看到了实际新增 ACCOUNT_STATES_VALID；独立仪器完整 JSON 为真；独立于该布尔表达式的 16 类 evidence selftest 也要求对应检查新增失败。GO 建立在这些实际证据上，不建立在汇总 PASS 字样上。
3. **提交数口径。** 当前 base..tip 是 10 个提交；回执里的 9 对应最终空提交之前的计数。构建 tree 与最终 tree 相同，未发现这一次元数据增加带来未审源码变化。

执行方披露的早期打包失败、报告工作副本损坏、JSON 生成器曾丢回读条目的事件保留。最终上传报告匹配提交、JSON 保留角色和旧回读、有效包字节与来源得到本方核验；不单凭其已披露的中间错误重复开启电路返修。

较早 R3 验证目录的 commands.csv 曾清除行尾空格，因此不将其描述为“从未变化”；原始字节仍可从原提交取得。当前审核使用后续权威目录的工具身份与本方重新执行结果，不用旧目录的旧工具摘要冒充最终版本。

## 8 结论范围与尚未完成事项

R3 是账本与文档修补，电路完成级别维持 `RTL_TRACE_DRIVEN_MOS_OUTPUT_MEASURED_TT`。沿用的电气结论仅覆盖冻结 TT、单通道、固定夹持与理想有限斜率 PWL 激励下的约定电荷/关断判据；既有最大绝对电荷误差 0.438391 LSB 没有因本轮被改写。

8 档 PAM 模拟电流、完整 MOS 灰阶控制器、LUT、电流集成、真实片上驱动阻抗、物理 CDC/skew、光学有效位数、阵列与版图/DRC/LVS/PEX 均没有因这次 GO 被完成或授权。SOA_SIGNOFF 仍为 NO。

历史 59/56 超支 3 次继续记录为 VIOLATED_NOT_RETROACTIVELY_AUTHORISED；四个已删 R1 中间目录原字节不可得；凭据回显事件未解除。本方的安全扫描不证明这些历史问题解除，也不证明用户电脑所有未提交操作已被独立核实。

下一步可由用户决定是否登记本次固定 SHA 为限定接受版本。登记若获用户授权，应保留本审核范围、预算违规与非阻断注记；不自动合并 main、不自动进入 PAM 或下一阶段。main 仍携带需要另行处理的整合边界，本次审核没有授权一次性并入整条历史链。

```text
REVIEW_RECOMMENDATION=GO
REVIEW_SCOPE=DATA7B_R3_ACCOUNT_REPAIR_AND_HANDOFF_CORRECTION_WITH_FROZEN_TT_EVIDENCE
REVIEWED_SHA=f9fd09b184a69a27cdb409205dfd4f4151408a23
F1_ACCOUNT_STATE_VALIDATION=CLOSED
F2_HANDOFF_AND_EXPLANATION=CLOSED
NEW_BLOCKING_FINDINGS=0
HISTORICAL_BUDGET_STATUS=VIOLATED_59_OF_56_OVER_BY_3
BUDGET_RESPECTED=FAIL
COMPLETION_LEVEL=RTL_TRACE_DRIVEN_MOS_OUTPUT_MEASURED_TT
ACCEPTANCE_REGISTRATION_PERFORMED=NO
MERGE_PERFORMED=NO
NEW_SPECTRE_LAUNCHES_BY_REVIEWER=0
NEW_RTL_SIMULATIONS_BY_REVIEWER=0
NEW_OA_WRITES_BY_REVIEWER=0
NEXT_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```
