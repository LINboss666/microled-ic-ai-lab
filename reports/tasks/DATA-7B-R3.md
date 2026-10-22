# DATA-7B-R3：账户非法状态拒收与交接更正

这是 DATA-7B-R2 独立复审后提出的限定修补任务。用户转交本任务表示委托这项修补，不表示接受历史超支、不表示合并或授权 PAM/下一阶段。保留已经通过的电路、测量及旧问题修补，不扩大设计范围。

## 1 固定起点

仓库：`https://github.com/LINboss666/microled-ic-ai-lab`。

| 身份 | SHA |
|---|---|
| 被审 R2 / 本任务 base | `b3fe93c17de014cb16031438ce28c7152dd0020f` |
| R2 payload P2 | `6abe1bf5b93dc4bb12ba179cea0ab26929f33a90` |
| R2 的 R1 基线 | `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92` |
| 不得移动的 main | `23e471cb936b421ee97e1250c3be06edf96f9937` |

动工前用 Git protocol 和现有 GitHub API 通道独立回读固定起点；明确查询对象及完整 SHA。遇到网络不可达记 BLOCKED，不把旧回执冒充新读。新建分支建议 `poc/data-pwm-d7b-r3`、隔离 worktree；不在 main 或旧 R2 分支修改。

## 2 本次只做两件事

### 2.1 非法账户状态必须拒收

R2 任务 §3.2 已要求非法状态检查。本方在未经修改的 R2 重现：临时额度 1 的 mock 账，REQUESTED 改为未知或空状态后，重开变成 occupied=0，还能第二次 reserve。另把 R2 证据复制到临时目录，将 A001 改为未知状态、同步 no_launch 汇总并重新封存 manifest，证据复核仍只有历史预算失败。

运行随审核包交付的诊断：

```bash
python3 reviewer_account_states.py /absolute/path/to/checkout /absolute/path/to/diagnostic.json
```

R2 原字节上 rc=0 表示缺陷重现；两层修补后应 rc=1 / all_requirements_met=true，部分关闭为 rc=2。**逐项检查 JSON，不能只改 exit code 或只凭报错总数。** 诊断只在临时目录运行，不调用 SSH、Spectre、Icarus 或 OA。

修补要求：

1. 为 **Account** 明确唯一状态集合。按现有协议为 `REQUESTED / UNCERTAIN / CONFIRMED / COMPLETED / REFUSED_NO_LAUNCH`。空值、缺失、未知、大小写/空白变体不静默归为免费；明确拒绝。Ledger 现有 `DONE` 是另一张表的协议，不因复用校验而误拒冻结的合法旧文件。
2. 在 Account 读入后、recover/_restamp/写盘之前验证；计数、额度判断也不得把非法内存行当成零。非法输入拒收时保留原始账户字节，不删文件、不补默认状态、不把未知状态修成 REFUSED。
3. evidence checker 对 `launch_account.csv` **所有行**做同样的枚举检查，新增独立、稳定的点名失败（建议 `ACCOUNT_STATES_VALID`）。不能仅查冻结 seed 行，也不能依靠 no_launch 汇总不符、manifest 不符或已有 `BUDGET_RESPECTED` FAIL 代替此检查。
4. 合法 REQUESTED 仍从写入起占额，恢复为 UNCERTAIN 仍占额；CONFIRMED/COMPLETED 计一次，REFUSED_NO_LAUNCH 不计。55/56、冻结 seed 事实、原子替换、过期写者和关闭的 native 入口保持 R2 行为。不要新建大型状态机或事务框架。

必要离线正反例：未知和空状态的读盘拒收（分别保存输入/输出摘要，确认未写坏）；合法对象被注入未知内存状态后 counts/reserve 不放行；五种合法状态的已有计费语义保持；真实 R2 包未改动时新增状态检查 PASS；临时复制品改 A001 为未知/空、同步声明计数、重封 manifest 后只因相应非法状态产生新增失败。保留历史预算失败，不把总 rc=1 当成语义负例成功。

### 2.2 交接文档更正

用当前结果和 Git blob 机械生成/核对以下勘误，保留 R2 原始提交与勘误关系：

- R2 manifest：286 条 / 21,264,382 B，不含 manifest；目录 287 文件 / 21,323,343 B 含 manifest。不要混用。
- R2 exporter runner SHA-256 为 `dea050a5685eded854502f85c45f8f356acb006e5c421fd084513da5d39b70bc`。handoff 残留 R1 `64797d53…`，应更正并明确这是 R2 导出来源。R3 新校验器与 runner 摘要另列，不能冒充重新产生了 R2 样本。
- R2 新 RTL 仿真为 0；17 是 R1 历史仿真数，另列复用。不要把 R2/R3 当轮字段写成 17。
- R2 相对 H：8 个既有路径修改，其中 4 个代码路径，291 新增，0 删除。三份主工具并非全部既有修改路径。R3 的差异计数必须重新实测，不能复制本段数字当 R3 数字。
- 电流序列：26 条冻结复用，R1 新增 1 条 CAL；R2 新增 2 个 CAL 片段，相对原 D7B 共 3。`charge_series_new_in_r1=27` 应拆清来源；新增片段不等于新增仿真。
- R1 边沿时间四位小数 ns 对应 0.1 **ps**，纠正旧 0.1 ns 写法。
- R2 报告 §4 的“23 条最长带内段不足 10 ns”解释错误。C002 连续带内段约 39.09 ns，C255 约 7659.09 ns，仍未满足持续至 deadline 左侧的条件。保留 NOT_SETTLED 结论，只纠正原因，不改测量公式/判据。
- 报告重复“8 回执”合并；remote readback 明确被查询对象、完整 SHA、查询时间，历史 D2 时点记录与当前 tip 分列。报告、JSON、清单不写自身摘要，不以新提交自身 SHA 定义其自身身份。

本任务书逐字节入库到 `reports/tasks/DATA-7B-R3.md`。handoff 可新增 R3 对象承载修补身份、工具与验证记录；旧 R2 exporter 来源和运行身份单列保留，不用一个顶层摘要兼任两个角色。若更新 schema_version，说明字段口径，不改冻结结构验证器来迁就结果。

## 3 范围与冻结

允许：`scripts/dd1_d7b_run.py` 的 Account 状态验证相关小改动；`scripts/dd1_d7b_evidence_check.py` 的账户状态校验及相应自测；新增小型 `scripts/dd1_d7b_r3_*` 离线测试、`reports/dd1_d7b_review_fix_r3.md`、本任务书、验证证据目录；修改现有 DATA-7B MD/JSON 及 R2 修补报告作明确勘误。确有同一错误的 contract/pwm_current 说明可加小段勘误并列入路径表。其余源码冻结。

冻结：measure 核心、trace/四态解析器、所有 MOS/RTL/TB/wrapper/deck/PWL/case/golden、所有共享安全和 handoff 验证器、原开发 B 全部 1,107 路径、旧任务/授权记录；完整原 D7B、R1、**R2 当前 287 文件证据目录**。前轮已关闭的七类问题不重新实现，不改电气判决或统计窗口。

R3 直接对冻结 R2 包复核。新增小目录 `results/evidence/dd1_d7b_r3_<unique_run_id>/` 只放新工具身份、输入 R2 SHA/manifest 摘要、命令与单独 rc、状态正反例、旧回归结果和冻结路径比较。无需重新导出或复制 21 MB 模拟采样，更不能为修 handoff 改掉 R2 environment 的 exporter 摘要。

不删除/覆盖任何正式账户或已发布目录；故障注入只在临时副本。既有四个中间目录删除事件照实保留，不伪称恢复。旧预算 59/56、超支 3 次继续记 `VIOLATED_NOT_RETROACTIVELY_AUTHORISED`，预算失败不能加白名单后改成 PASS。凭据事件继续未解除；本任务不读凭据、不改密码、不进 VM。

```text
NEW_SPECTRE_LAUNCH_LIMIT=0
NEW_RTL_SIMULATION_LIMIT=0
NEW_OA_WRITE_LIMIT=0
NO_NATIVE_PREFLIGHT=YES
NO_SSH_OR_VM_WORK=YES
NO_PAM_LUT_ARRAY_LAYOUT_TCON_WORK=YES
NO_GC_REWRITE_FORCE_OR_HOOK_SKIP=YES
NO_MERGE_OR_MAIN_PUSH=YES
```

## 4 验证与交付

先在 base 的原字节复现本包诊断，保留输入身份与结果；后修补、再离线验证。不要先修改 base 再宣称“复现成功”。

1. 上述非法状态诊断：修前两例均可复现，修后均明确拒收；临时证据破坏产生新增点名失败。核对拒收前后文件摘要和文件集合。
2. 新状态正例与非法内存行测试通过；R2 的 run selftest、R1 guards、R2 guards（显式 `--bundle` 当前 R2 目录）及 evidence selftest 继续通过。measure/trace 未变则验证摘要并保留既有测试身份即可，不必重复为了增大计数。
3. 新 checker 评估原 R2 包：旧 43 项语义判决不变，新增状态检查 PASS，唯一总失败仍是历史 `BUDGET_RESPECTED`。若只增加一项检查，总数应为 44；实际以输出为准，记录新增项目清单，不硬改计数。
4. 新复核工具评估 R2 输入的“验证来源”与 R2 原 exporter 来源分开列。新工具不能因自身 hash 与旧 exporter 不同，就改旧产物身份或放宽来源校验；如需辅助入口，只做明确的验证记录，不重写旧 manifest。
5. 全树比较和白名单核对：原 B 的 1,107 路径、原 D7B/R1/R2 三个证据目录的 blob/mode 全量一致；实际新增/修改路径机械列出。`git diff --check` 必须检查已提交的 base..tip，不能用未跟踪文件看不见的工作树检查冒充。
6. 按已有安全闸与 hooks 工作；既存 objects FAIL 如实记录，不打印疑似敏感对象、GC 或改扫描规则。每条命令独立保存 rc，管道不能掩盖前序失败。

完成后形成一个功能 payload P3，后续 handoff/回读元数据提交逐枚说明；不要追写自身摘要。报告包括复现、根因、限定修法、正反例、新旧检查项目、全部来源与文档勘误、冻结全量比较、剩余历史事件。handoff 的“本轮”均指 R3，历史 R1/R2 值明确标年轮次。

可按本轮提交内 blob 打小审核包，带验证输入的精确路径/SHA 索引及全部新脚本/记录；不必复制旧电流样本。如自包含打包，保留旧依赖原字节，禁止 PDK、工具二进制、凭据和完整 PSF 入包。

推送新 R3 分支后用 Git protocol 与既有 API 双路回读 payload/tip、确认 main/R2/其他旧分支未动；一条通道失败如实分列。停在独立复审闸，不自行宣布 GO、不登记接受版、不合并、不启动下一阶段。

```text
TASK_ID=DATA-7B-R3
BASE_SHA=b3fe93c17de014cb16031438ce28c7152dd0020f
REPAIR_SCOPE=ACCOUNT_STATE_VALIDATION_AND_HANDOFF_CORRECTION_ONLY
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
HISTORICAL_BUDGET_STATUS=VIOLATED_59_OF_56_OVER_BY_3
NEXT_STAGE_AUTHORISED=NO
MERGE_PERFORMED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
