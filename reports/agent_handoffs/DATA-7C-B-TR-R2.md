# DATA-7C-B-TR-R2 Agent 交接

日期：2026-11-12。本轮为 B1–B5 一次收口的离线返工交付，**停在独立复审**，不是接受登记或新阶段 GO。

## 固定身份

- worktree `D:/ic617_d7c_b_tr_r2`，分支 `poc/data-pam-d7c-b-tr-r2`，BASE `ec107af502b729225e49428e4d2d72bffc389dae`。
- run_id `r20261112_144123_c4e480`，新证据目录 `results/evidence/dd1_d7c_b_tr_r2_20261112_144123_c4e480/`。
- 任务书原字节副本 `reports/tasks/DATA-7C-B-TR-R2.md`；报告 `reports/dd1_d7c_b_tr_review_fix_r2.md`。

## 新 Agent 首先要知道的

1. **整体仍是 REWORK 之后的返工交付，等待独立复审**；本文件不授权接受、合并或下一原生阶段。
2. B1/B2/B3/B5 已用干净输入 + 具名反例验证；B4 以诚实披露 `RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN` / `BUDGET_ACCOUNTING_STATUS=PARTIAL` 收口，**不是**证明四次独立进程。
3. 旧 `838/838`、自测 `260/260`、四个 executable SHA 都不得当作缺陷已关闭或四次进程已证成。本轮 `841/841` 只是当前检查器的计数，真实电气 FAIL 保留。
4. 原审核包缺件与两份 VCD 已由补充复审关闭；B5 已由审核方在真无 Git 目录实复现，本机修前复现作为对照留在 `prefix_reproduction.json`。
5. 冻结面 3246 项中 3242 项逐 blob+mode 未变，只有 4 个获准脚本改动；旧 `--gates` 写回旧表后按 Git 字节还原的历史仍须并列披露。

## 入口与输入选择

```text
python -B scripts/dd1_d7c_b_tr_r1_native.py --verify <显式 R1 证据目录>
python -B scripts/dd1_d7c_b_tr_r1_recompute.py <包根> --inputs <r2_inputs.json>
python -B scripts/dd1_d7c_b_tr_r2_probe.py <源包根> <不存在的新输出目录>
```

`r2_inputs.json` 显式给出 `evidence.r1 / native / tables` 与 `vcd_dir`，不依赖「猜最后一个目录」。两份 `.vcd.gz` 不在 Git 中，随新审核包携带。

## 纪律

零 Spectre/RTL/OA/guest/PDK/license/凭据；不改旧证据、旧账、旧 ZIP；不合并、不登记接受；不执行附件或旧包里的审核探针；新轮须新分支、新 run_id、不存在的新输出目录。旧范围 `diff --check` rc=2 的尾空白作为历史事实保留。
