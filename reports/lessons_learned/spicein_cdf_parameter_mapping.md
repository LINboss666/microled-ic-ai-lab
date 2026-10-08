# SpiceIn 导入的 OA 原理图：器件参数静默落在 PDK 默认值上

本文只记录**我们自己**的过程与测量，不含老师 PDK 的源码、模型内容或 CDF 文件摘录；出现的
参数名、默认值都是 Virtuoso/CDF 界面上本来就会显示给用户的东西。

## 1. 问题现象

```
Project:  Micro LED IC AI Lab
EDA:      Cadence IC617 (virtuoso 6.1.7-64b)
PDK:      SMIC 0.18um Mixed-Signal RF (teacher copy, ms018_enhanced_v1p2_rev0)
Cell:     microled_cells/c2mos_dff_1bit/schematic
```

- SpiceIn (ASG) 从已验收的晶体管级黄金网表导入了 OA 原理图，导入成功（SPICEIN-33/54）。
- MOS 数量正确：`instances=24`（18 只 MOS + 6 个 `basic/iopin` 端口符号），`nets=13`。
- 连通性看着正确：`dbCheck()`→t、`dbSave()`→t，重新只读打开后 72/72 只实例端子绑到正确网络。
- 由"从原理图导出的网表"跑的 Spectre 功能回归全部通过（DFF 33/33、3 级移位 40/40）。
- 但用户在 Virtuoso GUI 里逐个看器件属性时，所有管子参数相同：

```
Instance: mn_c   Cell: n18
Length: 1n M   Total Width: 220n M   Finger Width: 220n M   Fingers: 1   Multiplier: 1
```

  （`1n` 实际是字符串 `ln`：设计变量的**名字**，不是数值——见 §2。）
- GUI 同时报 `*Warning* 'l' is not a real value`，实例标签上出现 `*Error*`。
- 黄金网表要求的是 `ln=200n`、`wc=2u`、`wcp=4u`、`wk=500n`、`wkp=1u` 四档不同尺寸。

结论：`SCHEMATIC_DEVICE_PARAMETERS: FAIL`，而当时所有其它闸门都是绿的。

## 2. 根因（逐条实测，不做未验证的归因）

R1. **这些实例的 CDF 参数与 OA 属性是同一份存储，且键名必须与 CDF 一致。**
    `cdfGetBaseCellCDF(ddGetObj("smic18mmrf" "n18"))` + `cdfFindParamByName(...)` 显示参数集合是
    `l, w, fw, m, fingers, model`（`wf`、`mult`、`area`、`nws` 报 ABSENT），
    prompt 分别是 Length / Total Width / Finger Width / Multiplier / Fingers / Model Name，
    `units=lengthMetric`，master 默认值 `l=180n`、`w=fw=220n`、`m=fingers=1`。
    实例侧写完属性后 `cdfGetInstCDF(inst)` 立刻读到同样的值，删除属性后 CDF 回到默认——
    所以 CDF 层就是属性的视图，属性名不对 = 参数不存在。

R2. **SpiceIn 只写了 `l`（内容是黄金网表里的表达式名字）和一个 CDF 不认识的 `simW`。**
    修复前的回读（`results/c2mos_schematic_device_readback.csv` 由
    `logs/sch1/rb_c2mos_dff_1bit_pre_paramfix.log` 生成）逐实例显示：
    `raw_l="ln"`、`raw_w=ABSENT`、`raw_fw=ABSENT`、`raw_fingers=ABSENT`、`raw_mult=ABSENT`、
    `simW="wc"|"wk"|"wcp"|"wkp"`、`cdf_w="220n"`、`cdf_fw="220n"`。
    即：**黄金宽度从来没进到 CDF 认识的参数里**，GUI 显示的 220n 就是 PDK 默认值。

R3. **`l="ln"` 是不可求值的文本，这是那条 warning 与 `*Error*` 的直接来源。**
    `cdfParseFloatString("ln")` 返回字符串 `"ln"`（文档：解析不了就返回原串），而
    `cdfParseFloatString("200n")→2e-07`、`"2u"→2e-06`、`"220n"→2.2e-07`、`"1"→1.0`。
    另外 cellview 里没有这些设计变量的数值（`dbFindProp(cv "ln")` 无、`cv->desVars` nil），
    所以名字在 OA 一侧没有任何可解析的对象。

R4. **物理证据一致**：修复前 18 只实例的 `inst->bBox` 完全同尺寸（1.225 × 0.64375 µm 格点），
    即符号没有按 W/L 变过——与"参数是默认值"互相印证，不是显示层的问题。

R5. **`cdfUpdateInstParam(inst)` 不能当"提交"用**（试点实测）：它返回 t，但之后该实例的
    `l / w / fw / simW / model` 属性全部读不回来。所以正确流程是"写属性→（不）调 callback→读回"，
    本文的修复方法不含任何 callback 调用。

R6. 归因边界：**根因在"导入器写的是仿真侧属性、没写 CDF 认识的几何参数"这条不匹配**（R1+R2）。
    至于是 SpiceIn 的设计还是本站参数文件的用法造成，本机没有可查的官方说明，未验证，
    不写成结论；但无论哪一侧，验收缺的门是"逐实例回读有效参数"（见 §3、§5）。

## 3. 为什么这种错误危险

- 实例数量对 ≠ 器件参数对：24/18 只都在，全是默认尺寸。
- 连通性对 ≠ 有效 W/L 对：`dbCheck` 只关心端子接在哪条线上，不关心沟道多宽。
- 黄金 Spectre 通过 ≠ 导入的原理图通过：跑的是我按属性**表达式** + 黄金默认值重建的网表，
  与原理图里的实际参数无关——自制导出器把黄金 W/L 补回网表，正好把 §2 的错误盖住了。
- `dbCheck` PASS ≠ 完整校验 PASS：它不检查参数是否存在、是否可求值。
- GUI 才会暴露的东西（属性编辑器、标签求值、符号是否按尺寸画）没有进入任何自动闸门。
- 一次"看起来比预期好"的结果（所有器件同宽）本身就是信号：黄金明明有四档宽度。

## 4. 最终有效的修复方法

对每只 MOS，在实例上按 CDF 的名字写**数值**属性（值经 `cdfParseFloatString` 可求值），
`fingers=1` 时总宽 = 指宽：

```
dbDeletePropByName(inst "l"); dbCreateProp(inst "l"       "string" "200n")
                               dbCreateProp(inst "w"       "string" "2u")     ; 黄金 W
                               dbCreateProp(inst "fw"      "string" "2u")     ; fingers=1
                               dbCreateProp(inst "m"       "string" "1")
                               dbCreateProp(inst "fingers" "string" "1")
                               dbDeletePropByName(inst "simW"); dbCreateProp(inst "simW" "string" "2u")
dbSave(cellView)   ; 不调用任何 CDF callback
```

- 写前先 `dbDeletePropByName`（已存在时 `dbCreateProp` 不会覆盖）。
- 顺序上无依赖：`fingers/m` 与 `w/fw` 一起写，不做条件性重算。
- 验证方式（都是必须的）：新会话只读重开 → `dbFindProp` 读原始属性、
  `cdfGetInstCDF` + `cdfFindParamByName` 读 CDF 值、`cdfParseFloatString` 求值、
  `inst->bBox` 与 `inst->instTerms` 的绑网一并回读。
  实测结果：`L_MATCH 18/18`、`W_MATCH 18/18`、`MOS_MASTER_MATCH 18/18`，
  `UNRESOLVED/CDF_ERROR/INVALID_LENGTH/DEFAULT_VALUE_FALLBACK` 四个计数全 0，
  结构对比 `SCHEMATIC_STRUCTURE_UNCHANGED: PASS`，功能回归
  `SCHEMATIC_DFF_FUNCTION: PASS`、`SCHEMATIC_SHIFT3_FUNCTION: PASS`（网表的 W/L 只来自回读数值）。
- 未验证项：PCell 图形的重新求值。批量会话不重画符号（bbox 未变），所以引脚与导线的对准、
  标签 `*Error*` 是否消失属于 **GUI_PARAMETER_DISPLAY: USER_VERIFICATION_REQUIRED**；
  已存在的 5 个 Solder dot on cross over 警告按指示未处理。
- 正式 cell 尚未更新：操作者的 Virtuoso 会话仍占用同一库（11 个 virtuoso 进程），
  `FINAL_SCHEMATIC_UPDATE: WAITING_FOR_USER_TO_CLOSE_EDITOR`；修复方案已在
  `c2mos_dff_1bit_pre_paramfix`（备份）与 `c2mos_dff_1bit_paramfix`（试验）两个副本上验证。

入口脚本：`skill/sch2_fix_params.il`（尺寸表由 `scripts/sch2_gen_param_skill.py` 从黄金 CSV 生成）、
`skill/sch2_readback.il`（回读）、`scripts/sch_parameter_integrity_check.py`（判定）。

## 5. 以后必须执行的检查

任何经 SpiceIn / SKILL / 自动生成得到的 schematic，在宣布 `SCHEMATIC_VERIFIED: PASS` 之前，
五项缺一不可：

| 检查 | 入口 |
|---|---|
| `INSTANCE_COUNT_CHECK` | `skill/sch2_readback.il` 的 `RD-CELL instances=` |
| `CONNECTIVITY_CHECK` | 逐实例 D/G/S/B 绑网 + `scripts/sch2_connectivity_diff.py` |
| `CDF_PARAMETER_CHECK` | `cdfGetInstCDF` + `cdfFindParamByName`，参数名以 PDK CDF 实测为准 |
| `OA_PARAMETER_READBACK` | `scripts/sch_parameter_integrity_check.py`（非零退出即阻断） |
| `NETLIST_PARAMETER_CHECK` | 网表里的 W/L 必须来自 OA 有效参数（`scripts/sch2_netlist_from_readback.py`），禁止黄金回填 |

同一检查器对今后 Data Driver 的原理图导入同样适用：它的 golden CSV、回读日志、PDK 默认值、
期望库名全是命令行参数，没有对 C²MOS 的特判；单元测试见
`python scripts/test_sch_parameter_integrity_check.py`（7 例，含"合法等于默认值不得误杀"一例）。


---

## 6. SCH-3 复现（2026-10-09）：同一缺陷换到 3.3 V 器件族，且门的参数若照抄就会漏检

Data Driver（`smic18mmrf/n33` 与深 N 阱 `n33_dnw_4t_ckt`）用同一条 spiceIn 路线导入后，
修参前的只读回读（`results/evidence/sch3_readback_prefix.log`）出现与本文 §1 完全同形的状态：

```
raw_l="2e-06"  raw_w=ABSENT  raw_fw=ABSENT  raw_fingers=ABSENT  raw_mult=ABSENT  simW="2e-05"
cdf_l="2u"     cdf_w="350n"  cdf_fw="350n"  cdf_fingers="1"     cdf_mult="1"
```

三点新增认识，都是本轮实测，不是推断：

1. **默认值随器件族变**：`n33` 与 `n33_dnw_4t_ckt` 的 CDF 默认是 `l=w=fw=350n`（`n18/p18` 是 180n/220n）。
   如果把 SCH-2 的门参数 `--pdk-default-l 180n --pdk-default-w 220n` 直接复用到 3.3 V cell，
   `DEFAULT_VALUE_FALLBACK_COUNT` 会一直是 0——本事故就换个器件名继续隐身。永久闸因此新增
   `PDK_DEFAULT_DECLARATION_MISMATCH_COUNT`：回读日志带出 master 自己的 CDF 默认值
   （`RD3-MPARAM` 行），与命令行声明不一致即失败；判定"是否落在默认"也优先用 OA 报出的族默认值。
   新增单元测试 CASE9/CASE10 专门盯这两条。
2. **CDF 会规范化参数字符串**：写入 `1e-06` 后 CDF 报回 `1u`。同一数值、不同字符串，
   所以 raw 与 CDF 的一致性必须比**数值**而不是比文本；旧版按字符串比较会在合法状态下误报
   `CDF_ERROR_COUNT`（CASE8 覆盖）。
3. **宽度丢失与 spiceIn 是否写了表达式无关**：黄金网表里 `l/w` 本来就是数字（`l=2e-6 w=2e-5`），
   导入后 `w/fw/m/fingers` 仍然 ABSENT。因此 §2 的根因不能表述成"设计变量没解析"，
   准确表述是：**导入器把宽度写进 CDF 不认的 `simW`，CDF 认的字段从未被写**。

修法与 SCH-2 相同（`dbDeletePropByName` + `dbCreateProp` 写数值到 `l/w/fw/m/fingers`，然后 `dbSave`，
不调任何 callback），SCH-3 另加两条纪律：

- 不再补写 `simW`（它不属于这些 master 的 CDF 参数字典）；
- 写入 SKILL 自带结构守卫：cellview 里 master 属于 `smic18mmrf` 的实例数必须等于参数表行数，
  不相等就拒绝写入（防止表少一只，那一只悄悄留在默认尺寸）。

结果：`data_sink_1ch` 4 只 + `data_bias_ref` 1 只，MASTER/L/W 5/5，`CDF_EVALUATION_ERRORS: 0`，
`TERMINAL_CONNECTIVITY_MATCH: 5/5`（DNW 的 D/G/S/B 按端子名绑定，Body 与本通道 Source 同网）。

## 7. 附：`getd` 不能用来判断编辑器 API 是否可用

本轮想给 §12 写"schCheck 在批处理里不存在"的旧结论时实测发现：

```
getd('schCheck)      => nil            # SCH-1/SCH-2 据此判定"不可用"，错
errset(schCheck(cv)) => ((0 2))        # 实际可调用，返回 (errors warnings) 并打印具体警告
errset(schCreate)    => nil            # schCreate / schCreateWire 确实不可用
```

同一份日志里，`data_sink_1ch` 报 0 error / 2 solder-dot warning，`c2mos_dff_1bit(_paramfix)` 各
0 error / 5 warning——警告坐标与用户在 GUI 里看到的 5 条一致，说明这个 `schCheck` 就是编辑器那套检查。
教训与本文 §3 的"计数器全 0 不等于验证通过"是同一类：**探测方法本身也要被验证**；
探测 API 只能靠 `errset(<字面调用>)`，不能靠 `getd`/`funcall`（AGENTS 第 8、28 条）。
