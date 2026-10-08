# SCH-2 Part B：C²MOS 原理图参数七层审计

对象：`microled_cells/c2mos_dff_1bit/schematic`（老师 PDK `smic18mmrf`，`ms018_enhanced_v1p2_rev0`）。
样本：用户点名的 `mn_c`、`mn_k2`、`mp_c`、`mp_k2`（正好覆盖黄金网表的四档宽度 2u / 500n / 4u / 1u）。
所有"修复前"数据来自对**未修改备份** `c2mos_dff_1bit_pre_paramfix` 的一次独立只读回读
（`logs/sch1/rb_c2mos_dff_1bit_pre_paramfix.log`，由 `skill/sch2_readback.il` 打印），
"修复后"数据来自试验副本 `c2mos_dff_1bit_paramfix`（`logs/sch1/rb_c2mos_dff_1bit_paramfix.log`）。

## 1. 七层逐层实测

| 层 | 取法 | `mn_c` | `mn_k2` | `mp_c` | `mp_k2` |
|---|---|---|---|---|---|
| 1 黄金网表（`spectre/C2MOS_DFF.scs`，已解析成数值） | `scripts/sch2_golden_params.py` → `results/c2mos_golden_device_parameters.csv` | `l=ln→200n` `w=wc→2u` | `l=ln→200n` `w=wk→500n` | `l=ln→200n` `w=wcp→4u` | `l=ln→200n` `w=wkp→1u` |
| 2 SpiceIn 实际写了什么（`logs/sch1/asg_spiceIn_20261008_221818.log`） | 逐实例日志 | `Master Cellview 'smic18mmrf.n18:symbol' found`、`Created instance`、D/G/S/B 四条 `Created connection`、`propName='model' 'n18'`、`propName='l' propVal='ln'` | 同结构，`propVal='ln'` + `simW='wk'` | 同结构（p18），`l='ln'` | 同结构，`l='ln'` + `propName='simW'; propVal='wkp'` |
| 3 修复前 OA 实例属性 | `dbFindProp(inst nm)` | `l="ln"`；`w/fw/fingers/m` **ABSENT**；`simW="wc"` | 同左，`simW="wk"` | 同左，`simW="wcp"` | 同左，`simW="wkp"` |
| 4 老师 PDK CDF 参数集合与默认 | `cdfGetBaseCellCDF(ddGetObj("smic18mmrf" "n18"))` + `cdfFindParamByName` | 参数名 `l, w, fw, m, fingers, model`；`wf/mult/area/nws` = ABSENT；默认 `l=180n`、`w=220n`、`fw=220n`、`m=1`、`fingers=1`；prompt Length / Total Width / Finger Width / Multiplier / Fingers；`units=lengthMetric` | 同 `n18` | 同（`p18` 一致） | 同（`p18`） |
| 5 修复前 CDF 求值结果 | `cdfGetInstCDF(inst)` + `cdfParseFloatString` | `cdf_l="ln"`（求值→ 返回原串 `"ln"`，不是数）、`cdf_w="220n"`→`2.2e-07`（=PDK 默认，不是黄金值） | 同左 | 同左 | 同左 |
| 6 GUI 显示（用户报告） | 属性编辑器 + 实例标签 | Length 显示 `1n`（即字符串 `ln` 的字形）、Total/Finger Width `220n`、Fingers 1、Multiplier 1；`*Warning* 'l' is not a real value`；标签 `*Error*` | 与其它两只完全同值 | 同左 | 同左 |
| 7 Spectre 网表里的尺寸 | SCH-1 路线 `spectre/generated/c2mos_dff_1bit_from_schematic.scs` | `l=ln w=wc` + 头部 `parameters ln=2e-7 wc=2e-6 …`（默认值取自黄金网表） | `l=ln w=wk` | `l=ln w=wcp` | `l=ln w=wkp` |

四只样本的物理旁证：修复前 `inst->bBox` 全部是同一格点尺寸 `1.225 × 0.64375`
（例：`mn_c ((7.575 8.0125)(8.8 8.65625))`、`mn_k2 ((4.2 1.5125)(5.425 2.15625))`），
即符号根本没按 W/L 画过——与"参数取默认值"一致，排除了"只是显示层错"这一解释。

## 2. 回答审计问题：错误在哪一层

**不是"显示与底层不一致"（层 6 与层 3/4/5 完全一致：GUI 老实显示了 CDF 的默认值和不可求值的字符串）。**

主因在层 2→层 3→层 4 的**接口不匹配**，两个问题各自独立成立：

- **B1（参数没有正确落到 CDF 认识的字段，等价于"没导入"）**：SpiceIn 把黄金宽度写进
  `simW` 属性，而这套 PDK 的 CDF 只认 `w`（Total Width）与 `fw`（Finger Width）；`m`、`fingers`
  同样从未写出。结果 18 只管子的 `cdf_w/cdf_fw` 全部停在 PDK 默认 `220n`，四档宽度在原理图里不存在。
- **B2（参数求值失败）**：`l` 属性内容是黄金网表的**表达式名字** `ln`，而 cellview 内没有这些
  设计变量的数值（`dbFindProp(cv "ln")` 无、`cv->desVars` nil），`cdfParseFloatString("ln")` 原样返回
  字符串 → `'l' is not a real value` 与实例标签 `*Error*` 由此起。
- 层 7 是**掩盖机制**而非独立错误：SCH-1 的"从原理图导出"把 `l=ln w=wc` 这类表达式照抄进网表，
  再用黄金网表的 `parameters` 默认值补齐，于是仿真跑的是黄金电路，原理图里有没有这些参数从未被检验。

归因边界（未验证部分，明确标注）：为什么 SpiceIn 选择写 `simW` 而不是 `w`（是本机参数文件缺
device-map 所致，还是该版本导入器对"符号封装型 PCell"的固有行为），本站材料无法判定，不写成结论。
可以判定的是：验收缺一道"逐实例回读有效参数"的门，这道门现已存在（`scripts/sch_parameter_integrity_check.py`）。

## 3. 修复方法与验证（层 3/5 已闭合，层 6/7 留待用户）

| 样本 | 修复后属性 | 修复后 CDF | 求值 | 对黄金 |
|---|---|---|---|---|
| `mn_c` | `l=200n w=2u fw=2u m=1 fingers=1 simW=2u` | 同值 | `2e-07 / 2e-06` | ✓ |
| `mn_k2` | `l=200n w=500n fw=500n …` | 同值 | `2e-07 / 5e-07` | ✓ |
| `mp_c` | `l=200n w=4u fw=4u …` | 同值 | `2e-07 / 4e-06` | ✓ |
| `mp_k2` | `l=200n w=1u fw=1u …` | 同值 | `2e-07 / 1e-06` | ✓ |

全量：`OA_DEVICE_PARAMETER_READBACK: PASS`（`MOS_MASTER_MATCH 18/18`、`L_MATCH 18/18`、
`W_MATCH 18/18`，`UNRESOLVED/CDF_ERROR/INVALID_LENGTH/DEFAULT_VALUE_FALLBACK` 均 0），
`SCHEMATIC_STRUCTURE_UNCHANGED: PASS`，功能回归用只含 OA 数值的网表重跑：
`SCHEMATIC_DFF_FUNCTION: PASS`（33/33）、`SCHEMATIC_SHIFT3_FUNCTION: PASS`（40/40）。

仍未闭合的两条：
- 层 6（GUI）：批量会话不重新求值 PCell 图形（`inst->bBox` 未变），标签 `*Error*` 与 warning 是否消失属
  `GUI_PARAMETER_DISPLAY: USER_VERIFICATION_REQUIRED`；已存在的 5 个 Solder dot on cross over 警告按指示不处理。
- 正式 cell 尚未应用（操作者 Virtuoso 会话在跑）：`FINAL_SCHEMATIC_UPDATE: WAITING_FOR_USER_TO_CLOSE_EDITOR`。

测量工具：`skill/sch2_param_audit.il`（层 3/4/5 属性与 bbox）、`skill/sch2_cdf_probe3.il`
（CDF 参数字典与默认值）、`skill/sch2_readback.il`（七列回读）。
