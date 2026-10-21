# DATA-7A-R4：仅修暂存与回滚的清理收尾

**You have NO access to the user–ChatGPT conversation; this task brief, the included review evidence and the named repository are your sources.**

用户转交本包授权的是一个已有验收工具问题组的限定修补。不是设计下一阶段，不是改 PWM/PAM 电路。先完整读 `REVIEW_DATA7A_R3.md`、本任务和 `reviewer/probe_cleanup_failures.py`。

## 1. 来源与边界

仓库：https://github.com/LINboss666/microled-ic-ai-lab。

- 本轮起点 T3：`33cd863093961d571aca3bd726beea32cb50ecfd`，分支 `poc/data-gray-d7a-r3`。
- R3 payload P3：`88e7a740cb7107bba93816beb452dc42a8a10b4b`。
- T2：`01e078bbf545b9191539dc1c0de228a6d8e7749b`。
- 原 Data-6 B：`731767519d1a51287eb5b7f4a6e4f9b8e613e990`。

先实际回读 T3；远端已变化须核实差异并报告，不静默吸收未知提交。在独立工作区从 T3 建自己的 `poc/data-gray-d7a-r4`，同名存在先检查。保护脏工作树，不 reset/stash/force/merge，不移动旧分支，不改仓库可见性。

开工先读 `README.md`、`AGENTS.md`、`CONTRIBUTING_AI.md`、`.gitignore`、原 DATA-7A/R1/R2/R3 四份任务、冻结 contract、R3 报告/交接、相关源码及本包审核证据。仓库没有的聊天、GUI、PDK、全 VCD 不可假定审核方已经看到。

**相对 T3 逐字节冻结**：

```text
rtl/dd1_d7a_gray_ctrl.sv
tests/dd1_d7a/tb_dd1_d7a_gray.sv
scripts/dd1_d7a_check.py
scripts/dd1_d7a_trace.py
scripts/dd1_d7a_evidence_check.py
reports/dd1_d7a_contract.md
scripts/repo_safety_rules.py
scripts/test_safety_rules.py
scripts/dd1_d7a_validate_handoff.py
reports/tasks/DATA-7A.md
reports/tasks/DATA-7A-R1.md
reports/tasks/DATA-7A-R2.md
reports/tasks/DATA-7A-R3.md
```

旧 Scan/Data-6、Spectre/deck/结果、PDK、OA、CDF、symbol、cds.lib、人工原理图继续冻结。不得进入 VM/Cadence/Spectre/OA，不修改数字契约、测量阈值或时间端点。

只允许改：`scripts/dd1_d7a_run.py` 的 publish/清理/恢复失败处理及相关入口自测/写保护用例；`scripts/dd1_d7a_publish_test.py` 的针对性回归；必要的同前缀新增回归；R4 报告、任务、交接、小型证据及打包必需表。运行身份中的任务版本和导出身份可如实更新，不能更改 RTL 激励、测量、综合判据或波形重判算法。若需扩范围，带证据 STOP。

R3 数值修补已独立通过，不再重写它。R3 报告输入 ZIP 摘要最后一位的抄录错误可以用一条明确勘误修正，不删除旧失败历史。

## 2. 先重现未修改 T3 的三个路径

把随包探针置于隔离目录，其同级 `repo/` 指向 T3 的可丢弃快照/独立克隆；不要指向用户实际正式交付目录注入故障。脚本创建 `repo/review/dd1_d7a/reviewer_r3_cleanup`，拒绝复用已有 fixture。

```text
python reviewer/probe_cleanup_failures.py
```

**此诊断 rc=0 表示三条缺陷均复现，不是 PASS。** 保存完整 JSON，核实三例前后摘要、marker、两次 recover、实际入口的 builder 哨兵结果。不要只看退出码。

| 必需场景 | 未修改 T3 的实际缺陷 |
|---|---|
| 第二个暂存文件已有字节，再抛 catchable I/O 错误 | 失败的当前文件没登记进 staged，残留 `.new`，marker 被删 |
| 暂存失败后，删除已登记暂存文件持续失败 | 清理函数返回失败列表，但异常处理仍删 marker |
| 提升失败，旧内容回滚成功，但删除剩余暂存文件持续失败 | 回滚忽略清理失败，随后删 marker，宣称旧集合已恢复 |

三例旧目标及无关文件均没有被破坏。缺陷是未完成清理丢失了事务身份；真实入口随后可以越过恢复闸。不要改写成“原电路数据错了”或“已观察到正式导出误报成功”。

## 3. 修后行为要求

1. **记录可能已创建的当前暂存文件。** 写入中、flush 或 fsync 抛错后，也必须识别并清理这个事务已经创建/正在创建的文件。只模拟写之前的异常不够。不得删除不属于本事务的文件。
2. **清理结果参与收尾判决。** 不得丢弃 `_discard_staging()` 的失败列表。旧内容回滚成功与整个事务收尾完成分别判定；只要本事务暂存/restore/marker 清理还有失败，就不能报告事务已关闭。
3. **无法清理时保留可恢复状态。** 保留 marker、备份和必要清单，不覆盖原事务。连续两次 recover 都须 `complete=false`；实际 publish 和 `do_export` 都持续拒绝新工作。不能用 `{needed:false}` 掩盖残留。
4. **解除故障后可恢复。** 使用该 marker 记录的备份，核实原文件内容及原先不存在状态，清理本事务文件，全部成功后再删除 marker。随后正常发布仍应工作。不能把所有失败永久锁死当成修好。
5. **准确描述失败边界。** 一次可捕获的部分写失败，如果清理完全成功，可返回拒收且无 marker/无本事务残留；如果清理失败，则留状态并拒绝。清理/marker 删除/恢复再失败也必须如实报告，不抹掉现场。继续不要求硬件级多文件断电原子。

实现由你选择，不限定某一条代码改法。不得以放宽判据、吞掉异常、跳过残留比较、关闭恢复门禁或改成“任何非零都通过”实现。

## 4. 针对性验收

每例新建 fixture，保护完整目标集合、原来不存在的目标、一个无关文件及一个别的阶段的 `.new`。保存文件名集合/摘要、备份/marker、命中阶段、拒收原因及 rc。

- 新正反例覆盖三条路径。部分写例要先真正写出字节再抛错；清理拒绝例要在连续两次重试中保持故障，不能在首次异常后自动解除再声称能持续拒收。
- 正常可清理的部分写失败：旧目标不变，当前失败文件也清掉，marker 不残留，仍非零拒收本次发布。
- 两种持续清理失败：marker 保留、备份不被新事务覆盖、两次 recover 均不完整；直接 publish 拒绝；真实 `do_export` 不到达 builder。
- 故障解除：原事务恢复完成，旧目标及不存在状态正确，本事务临时文件和 marker 清掉，无关内容不变；正常发布正例通过。
- 实际入口可使用**到达 builder 就抛异常的哨兵**证明边界，但必须标 `BOUNDARY_DIAGNOSTIC`；不能把 stub build/export 写成真正成功。
- 修后再跑原诊断，其 rc=1 只说明旧缺陷不再全部复现；必须逐例读 JSON，并用新的正向回归证明三条都正确。不能只用它的总 rc 放行。
- 保留原 23 例、入口原 32 条断言、原写保护 21 模式的测试意义；新增数量从实际执行结果统计，不预填“全 PASS”。波形 checker 自测、冻结数值复核器的 56 项与 15 例语义自测、交接结构检查也要通过。

完整证据目录的独立数值参考脚本 `reviewer/probe_numeric_full_copy.py` 可直接运行：正确数据/30.000 通过，30.5 与 257.5 只因对应数值项被拒，不能有 `EVIDENCE_DIGEST` 干扰。

## 5. 复用、门禁与报告

本轮仍可复用 `r2_20261021` 的冻结数字波形，不要求为工具问题重跑数千例，也不重新设计电路。实际复用必须有四类生成源摘要、原 VCD 文件及六条摘要；按原门禁重判再导出，不能只信缓存 PASS。没有原波形/身份不符则 BLOCKED，或在授权的数字范围重跑并如实报数。不得把旧 run_id 改成 R4 来冒充新仿真。

`NEW_RTL_SIMULATIONS`、`REUSED_RTL_RUN` 按实记录；新工具与发布证据用本轮真实摘要，生成波形仍归冻结源。不得改 source-drift/trace-drift 拒收，不要求兼容 Linux Yosys 0.33，不能把未解析综合统计改绿。

安全规则正反例、来源、器件计数、staged/history/objects 及 Git diff 范围检查照旧。执行者本机旧不可达 blob 继续如实 FAIL：不 GC、不打印、不豁免、不改历史。每个问题最多三次修补尝试，超过 STOP 留证；新安全异常直接 STOP。

新增 `reports/dd1_d7a_review_fix_r4.md`：写未修负例、根因、修法、逐场景结果、原回归、实际命令/rc、复用边界、失败历史和未解项。将本任务逐字节保存为 `reports/tasks/DATA-7A-R4.md`。更新 DATA-7A 交接 MD/JSON，明确 R3 的数值问题已关闭，R4 只处理清理收尾。

## 6. 提交和停止

先完成全部功能/脚本/证据修补再提交 payload P4；后续 D4 只改约定交接/元数据。普通推送自己的 R4 分支，实际 Git 与可用 API 回读 full SHA。缺一路明确 PARTIAL，不伪造双读。原分支保持原位，不 force/merge/跳 hooks。

bundle 从 Git blob 取字节，纳入新任务/报告/回归并机械查必需集合，核 ZIP 与 manifest 的每项字节数/摘要，不含完整 VCD、工具二进制、PDK 或秘密。报告本机包精确 SHA，避免把源 SHA、ZIP SHA、任务 SHA 混写。

```text
TASK_ID=DATA-7A-R4
BASE_SHA=33cd863093961d571aca3bd726beea32cb50ecfd
REPAIR_SCOPE=PUBLISH_CLEANUP_FINALISATION_ONLY
NUMERIC_TRUNCATION=CLOSED_IN_R3
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

交回独立复审后停止。最终接受/合并/进入下一阶段由用户决定，不进入 DATA-7B、MOS PWM、八档 PAM、电流集成、LUT、阵列、版图或 VM/Cadence/OA。
