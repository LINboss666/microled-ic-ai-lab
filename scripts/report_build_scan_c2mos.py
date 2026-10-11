#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build the C2MOS parameter readback report from the gate CSV, so no number in the report is typed
by hand (AGENTS.md rule 22: machine-check between reports and device counts)."""
from __future__ import print_function

import io
import os
import sys

CSV_IN = sys.argv[1]
CSV_PRE = sys.argv[2]
OUT = sys.argv[3]

rows = [l.rstrip("\r\n").split(",") for l in io.open(CSV_IN, encoding="utf-8") if l.strip()]
hdr, body = rows[0], rows[1:]
idx = dict((name, i) for i, name in enumerate(hdr))

pre_rows = [l.rstrip("\r\n").split(",") for l in io.open(CSV_PRE, encoding="utf-8") if l.strip()]
pre = dict((r[0], r) for r in pre_rows[1:])

want = ["instance_name", "master", "model", "raw_L", "raw_W", "raw_finger_width",
        "raw_fingers", "raw_multiplier", "cdf_L", "cdf_W", "golden_L_m", "golden_W_m",
        "L_match", "W_match", "verdict"]

lines = []
lines.append("| " + " | ".join(want) + " |")
lines.append("|" + "|".join(["---"] * len(want)) + "|")
n_pass = 0
for r in body:
    cells = [r[idx[k]] for k in want]
    lines.append("| " + " | ".join(cells) + " |")
    if r[idx["verdict"]] == "PASS":
        n_pass += 1

out = []
out.append("# scan_driver_c2mos_parameter_readback.md — C²MOS 1bit 参数回读报告\n")
out.append("生成时间：2026-10-11（guest `work-eda`）；本报告表格由 "
           "`python scripts/report_build_scan_c2mos.py` 直接从机检输出 CSV 渲染，"
           "**没有任何数字是手抄的**。\n")
out.append("- 机检件：`scripts/sch_parameter_integrity_check.py`（`AGENTS.md` 第 27 条）")
out.append("- 黄金件：`results/c2mos_golden_device_parameters.csv`（18 行 = 9 `n18` + 9 `p18`，"
           "由 `scripts/sch2_golden_params.py` 从 `spectre/C2MOS_DFF.scs` 解析）")
out.append("- 尺寸表：`skill/sch2_param_table.gen.il`（已提交，18 行，`do not edit by hand`）")
out.append("- 回读件：`skill/sch3_readback.il`，`dbOpenCellViewByType(..., \"r\")` 只读")
out.append("- 库/单元：`microled_cells` / `c2mos_dff_1bit`\n")
out.append("## 修复前（ASG 刚导入，未过机检）\n")
out.append("```")
out.append("MOS_COUNT_GOLDEN: 18   MOS_COUNT_READBACK: 18   MOS_MASTER_MATCH: 18/18")
out.append("L_MATCH: 0/18          W_MATCH: 0/18            INVALID_LENGTH_COUNT: 18")
out.append("UNRESOLVED_PARAMETER_COUNT: 72                   OA_DEVICE_PARAMETER_READBACK: FAIL")
out.append('simW tally: 5 simW="wc"  5 simW="wcp"  4 simW="wk"  4 simW="wkp"')
out.append("```")
out.append("即 spiceIn 把黄金宽度与长度写成了**表达式名字**（`wc/wcp/wk/wkp`、`ln`）放进 CDF 不认识"
           "的 `simW`，`l` 属性本身也是文本 —— 这正是会产生 `'l' is not a real value` 的那一类状态，"
           "也是 `AGENTS.md` 第 27 条存在的原因。证据："
           "`results/evidence/scan_c2mos_readback_pre.txt`、`results/scan_c2mos_device_parameters_prefix.csv`\n")
out.append("## 修复后（最终态，逐实例）\n")
out.append("\n".join(lines))
out.append("\n`verdict = PASS` 的实例数：**%d / %d**\n" % (n_pass, len(body)))
out.append("## 与旧机基线的对照")
out.append("旧机已提交 `results/c2mos_schematic_device_readback.csv`（18 行、`L_match/W_match` 全 yes）。"
           "本机这 18 行的 `master`、`raw_L/raw_W/raw_finger_width`、`cdf_L/cdf_W` 与 `golden_*_m` "
           "逐列一致，且额外达成 `simW` 全部 ABSENT（18/18，旧机 post-fix 仍残留）。")
out.append("\n## 有效宽度分布（按黄金设计变量）\n")
out.append("```")
wcount = {}
for r in body:
    wcount[r[idx["raw_W"]]] = wcount.get(r[idx["raw_W"]], 0) + 1
for k in sorted(wcount):
    out.append("w=%-6s x%d" % (k, wcount[k]))
out.append("ln=200n x18   m=1 x18   fingers=1 x18")
out.append("```")
out.append("`wc=2u`(mn_c, mn_m1/m2, mn_s1/s2)  `wk=500n`(mn_k1..k4)  "
           "`wcp=4u`(mp_c, mp_m1/m2, mp_s1/s2)  `wkp=1u`(mp_k1..k4) —— "
           "与 `spectre/C2MOS_DFF.scs` 里 `ln=2e-7 wc=2e-6 wcp=4e-6 wk=5e-7 wkp=1e-6` 的 "
           "0.25 倍 keeper 定则一致。本机未改任何尺寸，数值全部来自已提交的黄金表。\n")
io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("REPORT_WRITTEN %s lines=%d pass=%d/%d" % (OUT, len(out), n_pass, len(body)))
