# C2MOS-HANDOFF-SCHEMA-02 — 正式 handoff schema 统一

任务 ID：`C2MOS-HANDOFF-SCHEMA-02`
审核基线：`a81093b394dc63e616eca65ca5f8fb41a283aa41`
工作分支：`gexing321/scan-driver/c2mos-schematic`
被统一的交接件：`reports/agent_handoffs/C2MOS-ADE-READBIND-01.json`
校验记录：`results/evidence/c2mos_handoff_schema02_validation.txt`

**本轮性质：只统一交接数据。没有重新执行任何 Cadence 实验**（JSON 里以
`CADENCE_EXPERIMENT_RERUN = NOT_RUN` 明确记录），没有创建 ADE Setup Database，
没有触碰 OA / Testbench / DUT / PDK / analogLib / model / display.drf，没有清理锁。
实验结论原样保留：`ADE_READBIND: ERROR` + 原始错误逐字未改。

---

## 1. 正式校验器的来源与不可篡改性

| 项 | 值 |
|---|---|
| 提供的文件 | `C:/Users/38324/Desktop/validate_handoff(2).py`（3932 B） |
| SHA-256（使用前实测） | `3c150d543465a5d17a9d63c700f6b895c82fb868cae9408b2afd47643603e1e5` |
| 任务要求的 SHA-256 | `3c150d543465a5d17a9d63c700f6b895c82fb868cae9408b2afd47643603e1e5` |
| 一致 | **是**（先校验哈希，再执行） |
| 使用位置 | `D:/IC项目/.tools/validate_handoff.py`（**仓库外**，未提交进公开仓库） |
| 执行后 SHA-256 | 同上，未变 → **未修改校验器** |

真实命令与完整输出（三次，含证据文件从"不存在"到"存在"的边界）在校验记录文件里，摘要：
```
$ python D:/IC项目/.tools/validate_handoff.py reports/agent_handoffs/C2MOS-ADE-READBIND-01.json
run #1  HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified)   exit_code=0
run #2  HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified)   exit_code=0
run #3  HANDOFF_STRUCTURE: PASS (fields only; evidence/remote truth NOT verified)   exit_code=0
```
**这个 PASS 只证明字段结构**。校验器自己的 docstring 明写它"不访问 GitHub、不执行项目测试，
PASS 不代表推送一致性、技术结果或证据内容正确"——本报告与 JSON 都按这个边界陈述，
没有把它当技术结论。

## 2. 字段是"按正式名重写"，不是大小写别名绕过

上一版（`f026a20`/`a81093b` 携带的）用的是任务书第十三节的大写字段名（`TASK_ID`、`ADE_READBIND_RESULT`…）。
本次按正式 schema 的确切键名重建，**旧别名键已删除**（避免"靠别名骗过检查"）：

| 正式字段 | 取值 | 依据 |
|---|---|---|
| `schema_version` | `"1.0"` | 校验器要求字符串 `"1.0"` |
| `project_id` | `microled-ic-ai-lab` | 项目标识 |
| `task_id` | `C2MOS-ADE-READBIND-01` | 被交接的实验任务 |
| `repository` / `branch` | 仓库 URL / `gexing321/scan-driver/c2mos-schematic` | — |
| `base_sha` | `3c4bfbf19890ecbc7ca4f6c102c804f8e414e49a` | 该实验任务书给定的基线 |
| `head_sha` | `f026a20cbaf48dafac8cf8d4475f88a39f05f1af` | **语义见 §3** |
| `push_status` | `REMOTE_VERIFIED` | **只能来自真实远端回读**，见 §4 |
| `scope_status` | `PARTIAL` | 有 FAIL 测试时校验器禁止写 `COMPLETE` |
| `security_gate` | `PASS` | staged + history 两道 SAFETY_GATE、bundle SAFETY_SCAN、provenance、netlist_stats |
| `tests` | 10 项（见 §5） | 每项 `PASS` 都必须带**相对、非穿越**的 `evidence_path` |
| `evidence_paths` | 6 条相对路径 | 报告 + 三份证据 |
| `known_limitations` | 7 条 | 含"head_sha 不能自指" |
| `stop_reason` | `AWAITING_INDEPENDENT_REVIEW` | — |

实验细节没有被丢弃，而是集中到 `experiment` / `source_consistency` / `integrity` /
`validator_provenance` 四个块里（校验器忽略未知键，因此既不干扰 schema，也保住了全部来源信息）。

## 3. `head_sha` 的语义（不编造自指 SHA）

`head_sha = f026a20…` 指**携带本次 Cadence 实验交付物**（探针、实验报告、原始证据）的那次提交。
它**不是**本 manifest 所在提交——提交不可能包含自己的 SHA，编造它才算作弊。
后续提交单列在 `followup_commits`：`a81093b…`（证据修正轮），其远端回读值一并写明；
本轮 schema 提交完成后再由 handback/远端回读给出，不写进自己体内。
JSON 里 `head_sha_semantics` 字段就是这句话的落库版本。

## 4. `push_status` 的事实依据

只有 `REMOTE_VERIFIED` 是真实可主张的：每次 push 之后都用**非 push 通道**的
`git ls-remote` 独立回读，把远端 ref 与 `git rev-parse HEAD` 比对
（`f026a20` 与 `a81093b` 两次均相等）。校验器特别注明
`REMOTE_VERIFIED requires security_gate PASS (not proof of parity)` ——
即这条枚举值本身不代表奇偶性证明，真正的证明是那次独立回读，JSON 的 `push_status_basis` 写明了这一点。

## 5. `tests` 数组（真实状态，不粉饰）

| name | status | 说明 |
|---|---|---|
| `ADE_READBIND` | **FAIL** | 按任务书要求把实验失败如实登记为 FAIL（原始 `ddGetObjWritePath` 错误写在 `detail` 与 `experiment.raw_error`） |
| `DUT_UNCHANGED` | PASS | 逐文件 sha256，36/36 diff 为空 |
| `TB_UNCHANGED` | PASS | 同上 |
| `PDK_FULL_TREE_INTEGRITY` | **UNVERIFIED** | 实验窗口内没有全树基线 |
| `PDK_UNCHANGED_SCOPE` | FAIL | 明示"PASS 是夸大，已降级为 PARTIAL" |
| `ANALOGLIB_FULL_TREE_INTEGRITY` | UNVERIFIED | 当时只有计数 + mtime + 3 个抽样 |
| `SOURCE_CONSISTENCY_GUEST_VS_REPO` | PASS | guest 与仓库文件 sha256 相同、行号 48 一致 |
| `OFFICIAL_HANDOFF_VALIDATOR` | PASS | 本节内容，证据为校验记录文件 |
| `CADENCE_EXPERIMENT_RERUN` | **NOT_RUN** | 本轮零 Cadence 动作 |
| `NATIVE_NETLIST` | BLOCKED | 从未宣称可达；绑定失败发生在网表生成之前 |

`scope_status=PARTIAL` 与存在 FAIL 项是**自洽**的（校验器规则：`COMPLETE` 与任何 FAIL 冲突）。

## 6. 与自写检查器的关系

`scripts/c2mos_handoff_field_check.py`（上一轮我加的，只查 15 个自定字段）**不再是权威**；
JSON 的 `validator_provenance.supersedes` 就是这个声明。它保留在仓库里只作为"字段齐备性"的便利预检，
不得再据它宣布结构通过。

## 7. 已知限制

1. 正式校验器只查字段结构；证据内容真伪、远端是否真的等价，仍靠 GPT-6 独立读取远端判断。
2. `head_sha` 指向实验提交而非本轮提交（语义已写明），审阅者若要求"指向本轮 HEAD"，只能由外部 handback/后续提交表达。
3. Cadence 侧问题一个都没解决：`ADE_READBIND: ERROR` 依旧，是否缺 setup database 仍是 **DERIVED**，
   全树 PDK/analogLib 窗口内一致性 **NOT_VERIFIED**，ADE XL 产品许可 **NOT_VERIFIED**，
   `?mode "r"` 仍会去算写路径，`terms=0` 未触及。
4. 下一步两条路（授权写库建 setup db / 人工开 ADE 保存一次 setup 后重跑只读探针）仍未获授权，未执行。
