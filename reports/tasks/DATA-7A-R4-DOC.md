# DATA-7A-R4-DOC：只做三项文档收尾

**You have NO access to the user–ChatGPT conversation; this task brief, the included independent review and the named repository are your sources.**

R4 发布清理逻辑已独立复审通过；本任务只校正文档，不是 R5 功能修补，不是下一阶段设计。先读随包 `REVIEW_DATA7A_R4.md`，尤其 §6 的三个实际差异。

## 1. 固定来源和允许范围

仓库：https://github.com/LINboss666/microled-ic-ai-lab。

- 当前审核 tip T4：`0bfe339b8dbbb43e8356fc14f7a81acfd429a683`。
- R4 功能 payload P4：`c70039cb9764e00c9d780ad00a03d6c7ae9a2cb9`。
- R4 起点 T3：`33cd863093961d571aca3bd726beea32cb50ecfd`。

先实际回读远端；若已有未知提交则核实后报告，不静默合入。在独立工作区从 T4 建自己的 `poc/data-gray-d7a-r4-doc`，同名存在先检查。保护脏工作区，不 reset/stash/force/merge，不移动旧分支、不改可见性。

先读仓库 README、AGENTS、CONTRIBUTING_AI、.gitignore、原 R4 任务和当前报告/交接。

**全部代码、RTL/TB、checker/reader、数值复核器、publisher、打包器、安全规则、验证器、contract、原任务和全部实测/身份/转录证据相对 T4 逐字节冻结。** 不修改 `scripts/`、`rtl/`、`tests/`、`spectre/`、`results/`、`spec/`，不进入 VM/Cadence/Spectre/OA，不重跑 RTL、突变、综合、模拟或电路导出。

仅允许：

```text
reports/dd1_d7a_review_fix_r4.md
reports/agent_handoffs/DATA-7A.md
reports/agent_handoffs/DATA-7A.json
reports/tasks/DATA-7A-R4-DOC.md    # 本任务逐字节副本
```

若这四个文件不足以完成，报告原因 STOP，不自行扩到工具或电路。

## 2. 三项勘误

### A. R4 报告自身的大小与摘要过期

当前报告 §6 将自己列为 14,736 B、SHA256=`29170c9289c0731fbb083cf3f320719f40e3202ad9e6bf5c5a74576f08f6bbf1`。

T4 实际 Git blob 是 22,284 B、SHA256=`a0a64f4186874f74493a98165a3d8ad45ade81da56b5e8d8ceaf9cdc4053be74`。其余 11 条表内交付摘要已核对，不需要泛化重写。

删除或明确勘误这条“自身最终摘要”的过期断言，保留错误曾出现及为何更正的说明。**不要把上述 T4 摘要当作修改后报告的最终摘要再写回报告自身。** 修改后报告的最终身份只从外部 Git blob / bundle MANIFEST 记录，避免自指。不得改测量值或原失败历史。

### B. 交接 JSON 的回读命令分支名错误

`remote_readback.method_1` 写的是 `refs/heads/poc/data-gray-d7a-r3`，但该段描述 R4 payload P4。

先核实可用的原执行转录。能证明当时命令的，按转录更正标签，并明确原标签是文档错误；找不到原转录的，注明原命令不能独立重建，不能凭推测补一条“当时执行过”的记录。

**现在的新回读单独记录**在 `documentation_closeout` 之类的补记中，注明查询对象、实际 SHA 和时间。不要用当前 R4 tip 的回读覆盖或冒充历史 P4 回读，也不要把 JSON 原来的 `head_sha=P4` 改成文档提交 SHA——原字段明确定义的是功能 payload。

功能任务原字段继续准确表达 R4；文档补记区分 T4 审核对象、新的 doc 分支与本次文档改动，避免把未发生的新测试写成 PASS。

### C. 最终提交范围的空白检查不为 0

审核对 T4 执行 `git diff --check T3..T4`，实际 rc=2，只有 `reports/dd1_d7a_review_fix_r4.md:290: new blank line at EOF.`。

去掉末尾多余空行，文件以单个换行结束。对报告原先 rc=0 的叙述加实际范围勘误，不删除原命令转录，也不伪造它当时的输出。

对新文件先检查暂存内容，避免只检查未包含新增文件的工作树差异。最终至少实际执行：

```text
git diff --cached --check
git diff --check 33cd863093961d571aca3bd726beea32cb50ecfd <doc-tip>
```

记录真实 rc。最终范围应为 0；不是把旧 T4 的 rc=2 静默改写成 0。

## 3. 最小必要验证

无需重新跑功能、仿真和导出。只做与本任务有关的验证：

- 相对 T4 的 diff 仅含上述四个允许路径；全部代码/电路/证据无差异。
- 原 R4 26 事务例、49 入口断言、56 证据检查、15 语义自测等记录保持原身份，不宣称本轮重新执行。
- 用冻结的交接验证器检查 JSON 结构；摘要/身份字段逐项与它所声明版本的真实字节比较，历史记录不被当成当前字节。
- 更正后的回读标签不与 `branch`、payload/tip 语义矛盾；新增实时回读结果与实际查询对象一致。
- 原 R4 报告最终自身摘要由外部 MANIFEST 提供，没有新的静态自指错误。
- `git diff --check` 和新增文件暂存检查通过；原任务逐字节副本正确。
- 正常提交安全门禁不跳过。执行者既存不可达 blob 如仍使 objects FAIL，保留原状态，不 GC、不打印、不豁免、不改规则。

每个问题最多三次修补尝试，超出留证 STOP。没有理由为这次文档更正重建 OA、重跑 Spectre 或改变实测表。

## 4. 提交、打包与停止

普通提交、普通 push 自己的文档分支，不 force/merge/跳 hooks。实际 Git 与可用 API 回读新分支的 full SHA；缺一路就如实写 PARTIAL。不要移动原 R4 分支。

审核包从最终 Git blob 打包，核文件集合/字节数/摘要和 ZIP CRC。冻结打包器的前缀已会选中 `reports/tasks/DATA-7A-R4-DOC.md`，无需改代码；额外机械确认该新任务也在包内。把完整原 R4 交付文件保留，避免只给一段自然语言勘误。完整 VCD、工具二进制、PDK 和秘密不入包。

原 P4、T4 和本次 doc-tip 身份分开记录；不能让文件声称其自身未来 commit SHA。交接说明：代码与实测证据无变化、新仿真 0、新 Spectre 0、新 OA 写入 0，文档勘误后交回轻量复核。

```text
TASK_ID=DATA-7A-R4-DOC
BASE_SHA=0bfe339b8dbbb43e8356fc14f7a81acfd429a683
REPAIR_SCOPE=DOCUMENTATION_ONLY
CODE_CHANGED=NO
MEASURED_EVIDENCE_CHANGED=NO
NEW_RTL_SIMULATIONS=0
NEW_SPECTRE_RUNS=0
NEW_OA_WRITES=0
STOP_REASON=AWAITING_DOCUMENTATION_REVIEW
NEXT_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```

停在文档复核，不进入 DATA-7B、MOS PWM、八档 PAM、电流集成、LUT、阵列、版图、VM/Cadence/OA。最终接受和下一阶段授权仍由用户决定。
