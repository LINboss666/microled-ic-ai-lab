# DATA-7C-B-TR-R3 Agent 交接

日期：2026-11-12。本轮只处理 R2 复审剩下的 B1–B4 语义与记账缺口，**停在独立复审**，不是接受登记或新阶段 GO。

## 固定身份

- worktree `D:/ic617_d7c_b_tr_r3`，分支 `poc/data-pam-d7c-b-tr-r3`，BASE `fc7ee7a59ea3bc70835f511a1f47650887ca9329`（R2 tip）。
- run_id `r20261112_175259_3c2950`，证据目录 `results/evidence/dd1_d7c_b_tr_r3_20261112_175259_3c2950/`。
- 报告 `reports/dd1_d7c_b_tr_review_fix_r3.md`。

## 新 Agent 首先要知道的

1. R2 原包与 B5 已由独立复审关闭；本轮不重新论证原包身份，只修语义。
2. B1–B4 已用干净正控 + 9 个具名反例验证；反例都在一次性副本里构造，原始证据未动。
3. 检查器计数由 841 变 838，是因为删掉旧 `rtl_checks()` 的五条并列断言、改由 `r2_rtl_checks()` 一条统一记录，**不是**新证据、也不代表任何缺陷关闭。
4. 真实电气仍为动态 33/37 FAIL、名义 23/37 FAIL；`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、`BUDGET_ACCOUNTING_STATUS=PARTIAL`、保守占额 5/4 保持。
5. 260 条历史模块自测仍未运行：`selftest()` 会进入受护栏保护的 `launch()`，本轮不冒险。

## 入口

```text
python -B scripts/dd1_d7c_b_tr_r1_native.py --verify <显式 R1 证据目录>
python -B scripts/dd1_d7c_b_tr_r1_recompute.py <包根> --inputs <r3_inputs.json>
python -B scripts/dd1_d7c_b_tr_r3_probe.py <源包根> <不存在的新输出目录>
```

`r3_inputs.json` 显式给出 `evidence.r1 / native / tables` 与 `vcd_dir`。两份 `.vcd.gz` 不入库，随审核包携带，位于 `results/evidence/dd1_d7c_b_tr_r3_…/rtl/`。

## 判据落点

- B1：`scripts/dd1_d7c_b_tr_r1_native.py` 的 `_r2_parse_sequence` + `_r2_preflight_semantics`。
- B2：`recompute.py` 的 `r2_confirmed_launches` / `r2_budget_facts` / `r2_settling_limits` / `r2_deadline_current`。
- B3：`recompute.py` 的 `r2_context_differences`，在 `r2_convergence_checks` 内逐键调用。
- B4：`run.py` 的 `duplicate_bookings`（要求真实转录文件并被重新哈希）与 `record.py` 的 `derive_duplicates`（返回空）。

## 纪律

零 Spectre/RTL/OA/guest/PDK/license/凭据；不改旧证据、旧账、旧 ZIP；不合并、不登记接受；新轮新分支、新 run_id、不存在的新输出目录。
