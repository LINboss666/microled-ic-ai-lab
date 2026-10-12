# C2MOS-ADE-READBIND-01 — 证据修正报告（REWORK / EVIDENCE CORRECTION ONLY）

审核基准：`f026a20cbaf48dafac8cf8d4475f88a39f05f1af`
本轮性质：**只修正审计交付**。没有重新运行 ADE 绑定，没有创建 Setup Database，没有触碰 OA/PDK/Testbench。
实验的真实失败结果**保持原样**：`ADE_READBIND: ERROR`（情况 E），原始错误逐字保留（§4）。
证据：`results/evidence/c2mos_ade_readbind_once_correction.txt`（SECTION 1–5，全部命令原文）

---

## 任务1：正式校验器 —— 结论是 **未部署**，不是"通过"

`scripts/validate_handoff.py`（GitHub Bridge Review Workflow v1.0 的正式校验器）**在本机任何位置都不存在**。
搜索范围与结果（证据 SECTION 1）：

| 搜索位置 | 结果 |
|---|---|
| 本仓库工作树 `scripts/` | 只有 `test_ic617_bridge.ps1`，无校验器 |
| 每个远端分支的 tree（`git ls-tree` 逐 ref） | 无匹配 |
| 全部 git 历史（`git log --all --name-only`） | 从未提交过 |
| `D:\IC项目` 目录树 | 只有本轮新增的 `reports/agent_handoffs/` 与自写检查脚本 |
| `C:\Users\38324`（含 Downloads，top 3 层） | 无匹配 |

因此：

1. **撤回**上一轮的 `HANDOFF_STRUCTURE: PASS`。那只是 `python -m json.tool`（可解析性），不是 schema 校验，
   用它宣布结构通过是错的。
2. 我没有伪造正式校验器的输出。为可复核，我写了**明确非权威**的字段检查器
   `scripts/c2mos_handoff_field_check.py`（文件头就写明它不是 `validate_handoff.py`，
   且检查依据是任务书第十三节列出的字段清单）。

真实运行输出（同一命令，修正前后各一次；证据 SECTION 2 / 2b）：
```
$ python scripts/c2mos_handoff_field_check.py reports/agent_handoffs/C2MOS-ADE-READBIND-01.json
（修正前）JSON_PARSE: OK (20 top-level keys)
          MISSING_FIELD LOCAL_HEAD_SHA / REMOTE_HEAD_SHA / LOCAL_REMOTE_PARITY / ADE_READBIND_RESULT
          MISSING_FIELD DUT_UNCHANGED / TB_UNCHANGED / PDK_UNCHANGED / SECURITY_GATE
          MISSING_FIELD REPORT_PATH / EVIDENCE_PATH / KNOWN_LIMITATIONS
          BAD_VERDICT ''
          checked_required_fields=15 missing=11 problems=12
          HANDOFF_FIELD_CHECK: FAIL            rc=1
（修正后）JSON_PARSE: OK (36 top-level keys)
          checked_required_fields=15 missing=0 problems=0
          HANDOFF_FIELD_CHECK: PASS
```
**审核方判断成立**：原提交确实缺 11 个字段，现已补齐（`LOCAL/REMOTE_HEAD_SHA`、`PARITY`、
`ADE_READBIND_RESULT`、三项 `*_UNCHANGED`、`SECURITY_GATE`、`REPORT_PATH`、`EVIDENCE_PATH`、`KNOWN_LIMITATIONS`）。
`PDK_UNCHANGED` 的取值按 §3 一并降级为 `PARTIAL`。

## 任务2：源码一致性 —— **完全一致**，行号差异是"语句 vs 代码块"的数法差异

```
guest 实际运行文件  sha256 = 445df0a9f957aa9e9603576115af94368ab41aa2e080286b7f85641a605ec721  (59 行)
仓库提交文件        sha256 = 445df0a9f957aa9e9603576115af94368ab41aa2e080286b7f85641a605ec721  (59 行)
→ 逐字节相同（SOURCE_CONSISTENCY: PASS，无需保留两个版本，因为不存在两个版本）
```
行号问题澄清（证据 SECTION 3 / 3b 的 `grep -n` 与 `sed -n 41,48p | cat -n`）：
```
41  printf("RB-CREATE-SESSION %L\n" created)
42-46  printf("RB-STATE-BEFORE ..."        ← 一条跨 5 行的语句，第 45 行只是它的最后一个参数行
47  ; ---- THE ONE TARGET CALL, unguarded, exactly once ----
48  sdb = axlSetMainSetupDBLCV(created LIB CELL VIEW ?mode "r")     ← 目标调用，两份文件都在 48
```
所以"约 45 行"与"Cadence 报 48 行"指向**同一个文件里的同一条语句**：45 落在上一条 multi-line `printf` 内部。
不存在"跑了一份、提交了另一份"的情况，也没有发生静默覆盖。

## 任务3：`PDK_UNCHANGED` 的证据范围 —— 从 PASS 降级为 PARTIAL

四类检查必须分开陈述（证据 SECTION 4）：

| 对象 | 本轮实际做过的检查 | 能证明 | 不能证明 |
|---|---|---|---|
| 设计库 `microled_cells` | **逐文件 sha256**，36 文件，前后 diff 为空 | 内容字节级未变（这是 FULL 级证据） | — |
| PDK `/root/tech/teacher_pdk` | 文件数 3976→3976、`du` 176464KB→176464KB、实验窗口内 mtime 文件数 = 0、**1 个**关键模型文件 sha256 相同 | 计数/大小/时间戳未动，那一个 model 卡未动 | **全树 3976 文件内容未变**（实验前没有全树哈希基线，属 NOT_VERIFIED） |
| analogLib | 文件数 2628→2628、窗口内 mtime = 0、**抽样 3 个** `data.dm` 哈希 | 抽样件未动、无新增/改动时间戳 | 全树内容未变 |

因此结论改写为：**`DUT_UNCHANGED: PASS`、`TB_UNCHANGED: PASS`、`PDK_UNCHANGED: PARTIAL`**
（JSON 与 handoff 同步改写）。
另外为下一轮补上了真正的基线：本轮**事后**对 PDK 与 analogLib 做了全树逐文件 sha256 清单，
并给出聚合摘要（`PDK_MANIFEST_AGGREGATE_SHA256=20c6d98c…89d27`，3976 文件；
`ANALOGLIB_MANIFEST_AGGREGATE_SHA256=4f73da8e…e1f3`，2628 文件）。
**它只能作为今后的基线，不能倒推证明实验窗口内的内容一致性** —— 报告里就是这么标的。

## 任务4：原始错误保持不动

```
*Error* ddGetObjWritePath: argument #1 should be a ddUserType (type template = "b") - nil
*Error* load: error while loading file - ".../skill/c2mos_ade_readbind_once.il" at line 48
```
* 会话日志一字未改（原始日志仍在 `cadence_work/logs/sch_nograph_20261012_202316.log`，
  其内容已逐字收录在上一轮证据 SECTION C）。
* "缺 ADE Setup Database / 不存在 adexl view" 这一因果判断**仍是 DERIVED**，未升格为 DIRECTLY_OBSERVED：
  Cadence 从未打印"setup database 不存在"这类明文；它只是把 nil 传给了 `ddGetObjWritePath`。
  （"cell 只有 schematic、全库无 adexl view" 这部分才是 DIRECTLY_OBSERVED，两者已分开标注。）
* `ADE_READBIND: ERROR` 未被改写成 PASS；JSON 里新增 `original_failure_preserved: true` 与
  `correction_note`（本轮只改交付字段）。

## 修正清单（本轮改了什么）

| 文件 | 动作 |
|---|---|
| `reports/agent_handoffs/C2MOS-ADE-READBIND-01.json` | 补齐 15 个正式字段；`PDK_UNCHANGED` 降为 `PARTIAL`；新增 `source_consistency`、`integrity` 分范围陈述、`handoff_validator: VALIDATOR_NOT_DEPLOYED`、`security_gate_detail`；保留原错误与 DERIVED 等级 |
| `reports/agent_handoffs/C2MOS-ADE-READBIND-01.md` | 同步改写结论与证据范围，撤回 `HANDOFF_STRUCTURE: PASS` |
| `scripts/c2mos_handoff_field_check.py` | 新增：明确标注"非正式校验器"的字段检查 |
| `reports/c2mos_ade_readbind_once_correction.md` | 本报告 |
| `results/evidence/c2mos_ade_readbind_once_correction.txt` | 新增：搜索/哈希/行号/字段检查原始输出 |

## 未解决 / 仍需人工或下一轮

1. **正式 `validate_handoff.py` 不在本机** → 需要你把 GitHub Bridge Review Workflow v1.0 的校验器放到仓库或给出文件内容，我才能真正跑 schema 校验；现在只能给"字段齐备 + 可解析"这一较弱结论。
2. PDK/analogLib 在实验窗口内的**全树内容一致性**：NOT_VERIFIED（只有事后基线）。
3. 建了 setup database 后绑定是否成功、ADE XL 产品许可证、`?mode "r"` 在 view 存在时是否真不写、`terms=0` 与原生网表关系：均 NOT_VERIFIED。
4. 下一步仍需在"写库建 setup db"与"人工开 ADE 保存一次 setup"之间做决定 —— **均需授权**，我没有自行推进。
