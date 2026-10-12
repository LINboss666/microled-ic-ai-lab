# Handoff — C2MOS-ADE-READBIND-01（证据修正版 / EVIDENCE-CORRECTED）

| 字段 | 值 |
|---|---|
| TASK_ID | `C2MOS-ADE-READBIND-01` |
| BASE_SHA | `3c4bfbf19890ecbc7ca4f6c102c804f8e414e49a` |
| BRANCH | `gexing321/scan-driver/c2mos-schematic` |
| 实验交付 LOCAL/REMOTE HEAD | `f026a20cbaf48dafac8cf8d4475f88a39f05f1af` == `f026a20cbaf48dafac8cf8d4475f88a39f05f1af` |
| LOCAL_REMOTE_PARITY | **PASS**（`ls-remote` 独立通道回读，非以 push 输出为准） |
| **ADE_READBIND_RESULT** | **`ADE_READBIND: ERROR`**（情况 E，未返回句柄也未正常返回 nil） |
| 原始错误（逐字保留） | `*Error* ddGetObjWritePath: argument #1 should be a ddUserType (type template = "b") - nil` |
| runner | `rc=124`（180 s 超时）/ `TOKEN_FOUND no` / 一次执行、零重试 |
| DUT_UNCHANGED | **PASS**（逐文件 sha256，36/36 diff 为空；`4c9c1658…dc167c`） |
| TB_UNCHANGED | **PASS**（`7ee683e8…c3f56b`） |
| **PDK_UNCHANGED** | **PARTIAL**（不是 PASS，见下"证据范围"） |
| SECURITY_GATE | **PASS**（staged + pre-push history + bundle SAFETY_SCAN；provenance/netlist 亦 PASS） |
| HANDOFF 正式校验器 | **`VALIDATOR_NOT_DEPLOYED`** —— `scripts/validate_handoff.py` 在本机不存在（仓库/全部分支/全history/用户目录均无） |
| STOP_REASON | `AWAITING_INDEPENDENT_REVIEW` |

## 本轮修正了什么（不改动实验结论）

1. **撤回**上一轮的 `HANDOFF_STRUCTURE: PASS`：那只是 `python -m json.tool`（可解析性），不是 schema 校验。
2. 原 JSON **确实缺 11 个正式字段**（`LOCAL/REMOTE_HEAD_SHA`、`PARITY`、`ADE_READBIND_RESULT`、
   三项 `*_UNCHANGED`、`SECURITY_GATE`、`REPORT_PATH`、`EVIDENCE_PATH`、`KNOWN_LIMITATIONS`）→ 已补齐。
   检查用自写脚本 `scripts/c2mos_handoff_field_check.py`（文件头声明"非正式校验器"）：
   修正前 `HANDOFF_FIELD_CHECK: FAIL (missing=11)` → 修正后 `PASS (missing=0)`，真实输出在
   `results/evidence/c2mos_ade_readbind_once_correction.txt` SECTION 2/2b。
3. **`PDK_UNCHANGED` 由 PASS 降级为 PARTIAL**，并把四类证据分开陈述：
   设计库=逐文件 sha256（FULL）；PDK=文件数+du+窗口内 mtime=0+**1 个**关键 model 文件哈希；
   analogLib=文件数+mtime+**抽样 3 个** `data.dm`。全树内容一致性在实验窗口内是 **NOT_VERIFIED**。
   本轮另建了 PDK/analogLib 全树 sha256 聚合基线（`20c6d98c…`/`4f73da8e…`），
   但它只能服务下一轮，不能倒推证明上一轮窗口。
4. **源码一致性核对（任务2）**：实际运行的 guest 文件与提交文件 **sha256 完全相同**
   （`445df0a9f957aa9e9603576115af94368ab41aa2e080286b7f85641a605ec721`，各 59 行）。
   "约 45 行"与"Cadence 报 48 行"是**同一条语句**的数法差异：41 行是 `RB-CREATE-SESSION` 打印，
   42–46 是一条跨 5 行的 `printf`，48 才是目标调用。不存在两份不同源码。
5. 因果分级保持：`adexl` setup view 不存在 = **DIRECTLY_OBSERVED**（目录库列举）；
   "绑定失败是因为缺 setup database" = **DERIVED**（Cadence 没有打印该因果句）。

## 复核命令（reviewer 可直接重跑）

```
python scripts/c2mos_handoff_field_check.py reports/agent_handoffs/C2MOS-ADE-READBIND-01.json
sha256sum skill/c2mos_ade_readbind_once.il            # 与 guest 侧同名文件对比
```

## 仍未解决

* 正式 `validate_handoff.py` 不在本机 → 请把 workflow 包内的校验器交付到仓库，否则只能给字段级结论。
* 建 setup db 后绑定是否成功、ADE XL 产品许可、`?mode "r"` 在 view 存在时是否真不写、`terms=0` 与原生网表关系：均 NOT_VERIFIED。
* 下一步两条路（写库建 setup / 人工开 ADE 保存一次 setup）都**需要授权**，本轮未执行任何一项。
