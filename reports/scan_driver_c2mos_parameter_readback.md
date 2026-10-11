# scan_driver_c2mos_parameter_readback.md — C²MOS 1bit 参数回读报告

生成时间：2026-10-11（guest `work-eda`）；本报告表格由 `python scripts/report_build_scan_c2mos.py` 直接从机检输出 CSV 渲染，**没有任何数字是手抄的**。

- 机检件：`scripts/sch_parameter_integrity_check.py`（`AGENTS.md` 第 27 条）
- 黄金件：`results/c2mos_golden_device_parameters.csv`（18 行 = 9 `n18` + 9 `p18`，由 `scripts/sch2_golden_params.py` 从 `spectre/C2MOS_DFF.scs` 解析）
- 尺寸表：`skill/sch2_param_table.gen.il`（已提交，18 行，`do not edit by hand`）
- 回读件：`skill/sch3_readback.il`，`dbOpenCellViewByType(..., "r")` 只读
- 库/单元：`microled_cells` / `c2mos_dff_1bit`

## 修复前（ASG 刚导入，未过机检）

```
MOS_COUNT_GOLDEN: 18   MOS_COUNT_READBACK: 18   MOS_MASTER_MATCH: 18/18
L_MATCH: 0/18          W_MATCH: 0/18            INVALID_LENGTH_COUNT: 18
UNRESOLVED_PARAMETER_COUNT: 72                   OA_DEVICE_PARAMETER_READBACK: FAIL
simW tally: 5 simW="wc"  5 simW="wcp"  4 simW="wk"  4 simW="wkp"
```
即 spiceIn 把黄金宽度与长度写成了**表达式名字**（`wc/wcp/wk/wkp`、`ln`）放进 CDF 不认识的 `simW`，`l` 属性本身也是文本 —— 这正是会产生 `'l' is not a real value` 的那一类状态，也是 `AGENTS.md` 第 27 条存在的原因。证据：`results/evidence/scan_c2mos_readback_pre.txt`、`results/scan_c2mos_device_parameters_prefix.csv`

## 修复后（最终态，逐实例）

| instance_name | master | model | raw_L | raw_W | raw_finger_width | raw_fingers | raw_multiplier | cdf_L | cdf_W | golden_L_m | golden_W_m | L_match | W_match | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mn_c | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | 200n | 2u | 2e-07 | 2e-06 | yes | yes | PASS |
| mn_k1 | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | 200n | 500n | 2e-07 | 5e-07 | yes | yes | PASS |
| mn_k2 | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | 200n | 500n | 2e-07 | 5e-07 | yes | yes | PASS |
| mn_k3 | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | 200n | 500n | 2e-07 | 5e-07 | yes | yes | PASS |
| mn_k4 | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | 200n | 500n | 2e-07 | 5e-07 | yes | yes | PASS |
| mn_m1 | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | 200n | 2u | 2e-07 | 2e-06 | yes | yes | PASS |
| mn_m2 | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | 200n | 2u | 2e-07 | 2e-06 | yes | yes | PASS |
| mn_s1 | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | 200n | 2u | 2e-07 | 2e-06 | yes | yes | PASS |
| mn_s2 | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | 200n | 2u | 2e-07 | 2e-06 | yes | yes | PASS |
| mp_c | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | 200n | 4u | 2e-07 | 4e-06 | yes | yes | PASS |
| mp_k1 | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | 200n | 1u | 2e-07 | 1e-06 | yes | yes | PASS |
| mp_k2 | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | 200n | 1u | 2e-07 | 1e-06 | yes | yes | PASS |
| mp_k3 | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | 200n | 1u | 2e-07 | 1e-06 | yes | yes | PASS |
| mp_k4 | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | 200n | 1u | 2e-07 | 1e-06 | yes | yes | PASS |
| mp_m1 | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | 200n | 4u | 2e-07 | 4e-06 | yes | yes | PASS |
| mp_m2 | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | 200n | 4u | 2e-07 | 4e-06 | yes | yes | PASS |
| mp_s1 | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | 200n | 4u | 2e-07 | 4e-06 | yes | yes | PASS |
| mp_s2 | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | 200n | 4u | 2e-07 | 4e-06 | yes | yes | PASS |

`verdict = PASS` 的实例数：**18 / 18**

## 与旧机基线的对照
旧机已提交 `results/c2mos_schematic_device_readback.csv`（18 行、`L_match/W_match` 全 yes）。本机这 18 行的 `master`、`raw_L/raw_W/raw_finger_width`、`cdf_L/cdf_W` 与 `golden_*_m` 逐列一致，且额外达成 `simW` 全部 ABSENT（18/18，旧机 post-fix 仍残留）。

## 有效宽度分布（按黄金设计变量）

```
w=1u     x4
w=2u     x5
w=4u     x5
w=500n   x4
ln=200n x18   m=1 x18   fingers=1 x18
```
`wc=2u`(mn_c, mn_m1/m2, mn_s1/s2)  `wk=500n`(mn_k1..k4)  `wcp=4u`(mp_c, mp_m1/m2, mp_s1/s2)  `wkp=1u`(mp_k1..k4) —— 与 `spectre/C2MOS_DFF.scs` 里 `ln=2e-7 wc=2e-6 wcp=4e-6 wk=5e-7 wkp=1e-6` 的 0.25 倍 keeper 定则一致。本机未改任何尺寸，数值全部来自已提交的黄金表。

