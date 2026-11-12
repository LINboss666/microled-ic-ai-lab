# DATA-7C-B-TR-R4 Agent 交接

日期：2026-11-12。本轮只修 R3 复审剩的三处（预检见证、账本身份绑定、转录事件语义），**停在独立复审**。

## 固定身份

- worktree `D:/ic617_d7c_b_tr_r4`，分支 `poc/data-pam-d7c-b-tr-r4`，BASE `073c0f3705eb55fba8f017cc9d2927a54b129f9a`（R3 本地 tip，**未发布**）。
- run_id `r20261112_205452_5e09f7`，证据目录 `results/evidence/dd1_d7c_b_tr_r4_20261112_205452_5e09f7/`。
- 报告 `reports/dd1_d7c_b_tr_review_fix_r4.md`。

## 新 Agent 首先要知道的

1. R3 原包（666 成员）与 B5 已由复审独立确认关闭，本轮不重复论证。
2. **两个 R3/R4 分支都还没推到远端**：git 通道 `CONNECT 502`、直连超时；`gh api` 正常。接手第一件事应是补齐 `poc/data-pam-d7c-b-tr-r3`（tip `073c0f3`）与 `-r4` 两个 ref。
3. 14 项反例全部具名拒收；其中 8 项是 R3 已有、6 项是本轮新增（B1 电流/使能全零、B2 双向身份、B4 两次启动转录、以及标签项）。
4. 多平台预检（HYB/RS-FULL/TR-LONG/TR-OFFCODE/RS-SWITCH）只判轨高与"至少一次平台"，逐例打印 `TR_R1_VERIFY_NOTE`。HYB 的 deck 声明平台数与交付沿数不一致，属**未解释项**，不要写成已对齐。
5. 真实电气仍动态 33/37、名义 23/37 FAIL；`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、`BUDGET_ACCOUNTING_STATUS=PARTIAL`、保守 5/4 保持。

## 入口

```text
python -B scripts/dd1_d7c_b_tr_r1_native.py --verify <显式 R1 证据目录>
python -B scripts/dd1_d7c_b_tr_r1_recompute.py <包根> --inputs <r4_inputs.json>
python -B scripts/dd1_d7c_b_tr_r4_probe.py <源包根> <不存在的新输出目录>
```

## 判据落点

- B1：`native.py` 的 `_r2_witness` + `_r2_deck_stimulus` + `_r2_parse_sequence`。
- B2：`native.py` 的 `_r2_find_ledger`/`_r2_bind_preflight`；`recompute.py` 的 `r2_sequence_headers` 与 `r2_confirmed_launches`。
- B4：`run.py` 的 `_declared_not_started`/`_start_evidence` 与 `duplicate_bookings`。

## 纪律

零 Spectre/RTL/OA/guest/PDK/license/凭据；不改旧证据、旧账、旧 ZIP；不合并、不登记接受；新轮新分支、新 run_id、不存在的新输出目录。
