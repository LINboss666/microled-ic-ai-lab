# DATA-7C-B-TR-D02 Agent 交接

日期：2026-11-13。本轮只修 B1（必需列 + 完整 PWL 见证），B2–B5 保持关闭，**停在独立复审**。

## 固定身份

- worktree `D:/ic617_d7c_b_tr_d02`，分支 `poc/data-pam-d7c-b-tr-d02`，BASE `71fb4ab049bc6aad1421f0b02b6ed27d7a8c07a2`（R4 tip，已发布）。
- run_id `d20261113_234820_29fb0d`，证据目录 `results/evidence/dd1_d7c_b_tr_d02_20261113_234820_29fb0d/`。
- 报告 `reports/dd1_d7c_b_tr_review_fix_d02.md`。

## 新 Agent 首先要知道的

1. B2 身份绑定、B3 收敛上下文、B4 转录语义、B5 无 Git 入口都已由复审关闭，回归仍通过；不要重开。
2. B1 现在按**冻结合同的必需列**和**deck 里可执行的 vsource/isource**判，不再读 `//` 注释。HYB 的 4/3 平台就是真实值，注释里的 8 是过期模板。
3. 缺列会立即停止后续取值核对并具名拒收；不要恢复"列存在才核对"的写法。
4. 17 项反例 = R4 的 14 项 + 删 iref_in、删 pam1、单平台化。全部具名拒收。
5. 真实电气仍动态 33/37、名义 23/37 FAIL；`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、`BUDGET_ACCOUNTING_STATUS=PARTIAL`、保守 5/4 保持。

## 入口

```text
python -B scripts/dd1_d7c_b_tr_r1_native.py --verify <显式 R1 证据目录>
python -B scripts/dd1_d7c_b_tr_r1_recompute.py <包根> --inputs <d02_inputs.json>
python -B scripts/dd1_d7c_b_tr_d02_probe.py <源包根> <不存在的新输出目录>
```

## 判据落点

- 必需列：`native.py` 的 `_r2_required_columns`（在 `_r2_preflight_semantics` 内调用，缺列即 return）。
- 可执行源：`_r2_deck_sources` / `_r2_source_value` / `_r2_source_crossings`。
- 见证：`_r2_witness`（供电三方一致、使能沿数量与时刻、逐平台位序）。

## 纪律

零 Spectre/RTL/OA/guest/PDK/license/凭据；不改旧证据、旧账、旧 ZIP、旧 deck；不合并、不登记接受；新轮新分支、新 run_id、不存在的新输出目录。
