# SCH-2：C²MOS 原理图 W/L 参数修复与永久防错

分支 `feature/c2mos-virtuoso-schematic`。日期 2026-10-08（guest）。
本轮唯一电路改动 = 修 OA 原理图里的器件实例参数；拓扑、黄金 W/L、D/G/S/B 一字未动。

## 0. 交付键块

```
TASK:                       SCH-2 C2MOS PARAMETER FIX
ROOT_CAUSE:                 SpiceIn 把黄金宽度写进 CDF 不认识的属性 simW，只把表达式名字 ln 写进 l；
                            n18/p18 的 CDF 参数是 l/w/fw/m/fingers/model（实测），
                            于是 w/fw 停在 PDK 默认 220n，l 不可求值（见 §2 与审计报告）
GOLDEN_MOS_COUNT:           18
OA_MOS_COUNT:               18
MOS_MASTER_MATCH:           18/18   (smic18mmrf/n18:symbol ×9, smic18mmrf/p18:symbol ×9)
W_MATCH:                    18/18
L_MATCH:                    18/18
CDF_PARAMETER_EVALUATION:   PASS    (UNRESOLVED=0, CDF_ERROR=0, INVALID_LENGTH=0, DEFAULT_FALLBACK=0)
OA_PARAMETER_READBACK:      PASS    (新会话只读重开，数值来自数据库本身)
CONNECTIVITY_UNCHANGED:     PASS    (INSTANCE_COUNT / MASTERS / EXTERNAL_PORTS / COUNTS 同 PASS)
NATIVE_CADENCE_NETLIST:     BLOCKED (asiCreateSession / nlCreateDesign / nlCreateFormatter 全部返回 nil)
SCHEMATIC_DFF_FUNCTION:     PASS    (33/33，网表 W/L 只来自 OA 回读数值)
SCHEMATIC_SHIFT3_FUNCTION:  PASS    (40/40，同上)
FINAL_SCHEMATIC_UPDATED:    NO      (WAITING_FOR_USER_TO_CLOSE_EDITOR，见 §5)
KNOWN_SOLDER_DOT_WARNINGS:  5 — DEFERRED_TO_USER
LESSONS_LEARNED_MD:         reports/lessons_learned/spicein_cdf_parameter_mapping.md
AGENTS_MD_RULE:             ADDED   (第 27 条 Automated Schematic Parameter Integrity Gate)
PARAMETER_INTEGRITY_CHECKER: PASS   (7 个用例，含 6 个指定用例)
REVIEW_BRANCH:              feature/c2mos-virtuoso-schematic
REVIEW_HEAD_SHA:            见本文末 §7
NEXT:                       USER_GUI_PARAMETER_REVIEW
```

## 1. 我在 SCH-1 的结论哪里是错的（必须先说清楚）

SCH-1 的 `GOLDEN_NETLIST_EQUIVALENCE: PASS` 比的是**属性里的表达式名字**（`l="ln"`、`simW="wcp"`）
和**从黄金网表补来的默认值**；它没有比过原理图自己的有效尺寸。当时的证据
`results/evidence/sch2_param_audit_prefix.log` 里其实已经印着 `PA-INST-BBOX` 全同尺寸、
`w` 属性不存在，我只把它当"字符串表达式"记进了报告 §5.3，没有据此判 FAIL。
所以那时 `SCHEMATIC_DEVICE_PARAMETERS` 应为 FAIL 而我写了等价 PASS —— 这是判据设计缺陷，
不是数据被改坏；现已由 `scripts/sch_parameter_integrity_check.py` 补成硬闸。

## 2. 根因（七层审计结论，全部实测）

详表见 `reports/c2mos_cdf_parameter_audit.md`。要点：

| 层 | 实测 |
|---|---|
| PDK CDF 参数字典 | `cdfGetBaseCellCDF` + `cdfFindParamByName`：`l/w/fw/m/fingers/model` 存在（默认 `180n/220n/220n/1/1`），`wf/mult/area/nws` 不存在 |
| SpiceIn 实际写入 | 日志逐实例：`propName='l' propVal='ln'`、`propName='simW' propVal='wc'`、`model`；从未写 `w/fw/m/fingers` |
| 修复前 OA 属性 | `raw_l="ln"`、`raw_w=ABSENT`、`raw_fw=ABSENT`、`raw_fingers=ABSENT`、`raw_mult=ABSENT` |
| 修复前 CDF 求值 | `cdf_l="ln"` → `cdfParseFloatString("ln")` 原样返回 `"ln"`（不是数）；`cdf_w="220n"` → `2.2e-07`＝默认 |
| GUI 显示 | Length `1n`（即字符串 `ln` 的字形）、Total/Finger Width `220n`、Fingers 1、Multiplier 1 + `'l' is not a real value` + 标签 `*Error*` |
| 物理旁证 | 18 只 `inst->bBox` 全等（`1.225 × 0.64375`），符号从未按 W/L 画过 |

两个独立问题：**B1 宽度没落到 CDF 认识的字段**（等价于没导入）；**B2 `l` 是不可求值的表达式名字**
（cellview 里没有这些设计变量的值：`dbFindProp(cv "ln")` 无、`cv->desVars` nil）。
显示层没有骗人——它显示的就是 CDF 的真值。
至于"为什么 SpiceIn 选 `simW`"本站材料无法判定，未写成结论（见 lessons §2 R6）。

## 3. 修复方法与为什么不能用 callback

试点（`results/evidence/sch2_pilot_mechanism_test.log`）逐机制对比后确定的写法：
按 CDF 的名字写**数值**属性，写完即 `dbSave`，不调任何 CDF callback：

```
dbDeletePropByName(inst "l") ; dbCreateProp(inst "l" "string" "200n")
                               dbCreateProp(inst "w"  "string" "<黄金 W>")
                               dbCreateProp(inst "fw" "string" "<同一 W，fingers=1>")
                               dbCreateProp(inst "m"  "string" "1")
                               dbCreateProp(inst "fingers" "string" "1")
                               dbCreateProp(inst "simW" "string" "<同一 W>")   ; 仿真侧属性与几何一致
```

试点同时抓到一条危险行为：`cdfUpdateInstParam(inst)` 返回 t，但之后该实例的
`l/w/fw/simW/model` 属性全部读不回来（它删属性，不是提交参数）——所以"批量调用所有 CDF callback"
这条路在本 build 明确不用。尺寸表由 `scripts/sch2_gen_param_skill.py` 从
`results/c2mos_golden_device_parameters.csv` 生成（18 行，`200n/2u/4u/500n/1u` 全是可求值数值），
写入脚本 `skill/sch2_fix_params.il`（18×6=108 条属性写，`FX-SAVE t`）。

## 4. 独立回读与不变性

`skill/sch2_readback.il` 在**新会话、只读、重开**后打印 18 行；判定由
`scripts/sch_parameter_integrity_check.py` 做（它只吃回读日志与黄金 CSV，不参与写入）：

```
MOS_COUNT_READBACK 18 | MOS_MASTER_MATCH 18/18 | L_MATCH 18/18 | W_MATCH 18/18
UNRESOLVED_PARAMETER_COUNT 0 | CDF_ERROR_COUNT 0 | INVALID_LENGTH_COUNT 0 | DEFAULT_VALUE_FALLBACK_COUNT 0
OA_DEVICE_PARAMETER_READBACK: PASS            （表：results/c2mos_schematic_device_readback.csv）
```

同一闸对**修复前备份**跑，结论是 FAIL（112 处不匹配 + `raw_w ABSENT`/`l="ln"` 逐实例列出），
即这道闸真的能抓到本次事故，不是只对着好数据点头。
结构不变性：`scripts/sch2_connectivity_diff.py` →
`INSTANCE_COUNT_UNCHANGED / CONNECTIVITY_UNCHANGED / MASTERS_UNCHANGED / EXTERNAL_PORTS_UNCHANGED /
COUNTS_UNCHANGED` 全 PASS（未移器件、未改导线、未重排、5 个 solder dot 警告原样留给用户）。

## 5. 正式 cell 为什么现在不写

`ps` 显示操作者的 Virtuoso 会话仍在跑（11 个 virtuoso 进程，22:50 起），`.cdslck` 已释放
（编辑器窗口关了），但该会话缓存过 `c2mos_dff_1bit/schematic`。若此时批量写入，
它 later 的一次保存可能把我的修复覆盖回去——正是本轮要消灭的那类静默事故。
按 spec：`FINAL_SCHEMATIC_UPDATE: WAITING_FOR_USER_TO_CLOSE_EDITOR`。
备份与验证副本已在库里：`c2mos_dff_1bit_pre_paramfix`（原始内容）、
`c2mos_dff_1bit_paramfix`（已修好并全闸通过）。你关掉 Virtuoso 后我按
`SCH1_CELL=c2mos_dff_1bit bash scripts/sch_virtuoso.sh skill/sch2_fix_params.il 600 FX_DONE`
应用，再对新 cell 跑一次回读闸门。

## 6. 网表与回归

- 原生 netlister 尝试（`results/evidence/sch2_native_netlist_attempt.log`）：在函数确实存在的
  `-restore` 路径上调 `asiCreateSession`（3 种参数形式）、`nlCreateDesign`（3 种）、
  `nlCreateFormatter`（2 种），全部 nil，没有产出任何文件 → `NATIVE_CADENCE_NETLIST_VERIFICATION: BLOCKED`。
  这条不是"没试"：`asiNetlist(n_session)` 的 session 对象在本 build 无公开无头构造入口。
- 因此功能回归用**只含 OA 数值**的网表：`scripts/sch2_netlist_from_readback.py` →
  `spectre/generated/c2mos_dff_1bit_from_oa_readback.scs`（`l=2e-07 w=2e-06` 这种纯数值行，
  文件头写明输入是回读日志，脚本从不打开黄金网表）；
  testbench `spectre/c2mos_{ff1,shift3}_from_oa_readback.scs` 与已验收版本逐行相同，
  只换 include；判据表由 `scripts/c2mos_check.sh` 的 `ff1_sch / shift3_sch` 复用，未放宽。
  结果 `SCHEMATIC_DFF_FUNCTION: PASS`（33/33，clk→Q 0.092–0.205 % T）、
  `SCHEMATIC_SHIFT3_FUNCTION: PASS`（40/40，4.215/4.329/3.957 ×10⁻¹⁰ s）。
  功能结论与黄金一致（同电路本该一致），但这次一致是**从原理图自己的参数**得到的。
- SCH-1 那份 `c2mos_dff_1bit_from_schematic.scs` 与两个 `_from_schematic.scs` testbench 保留为历史，
  其"表达式 + 黄金默认值"的口径已在文件头标注为被本轮取代。

## 7. Git

两枚 commit（本轮全部产物只含我们自己的电路数据与操作记录）：

- `fix:` 参数修复与验证链（SKILL 写入/回读、黄金表生成器、两个网表生成器、备份/试验 cell 脚本、
  证据日志、两份报告）
- `test:` 参数完整性闸 + 7 例单元测试 + `AGENTS.md` 第 27 条 + `reports/lessons_learned/`

闸：`python scripts/precommit_safety_check.py --mode staged` → `PDK_TRACKED_FILES = 0`、
`CREDENTIAL_TRACKED_FILES = 0`、`PRIVATE_KEYS_TRACKED_FILES = 0`、`VENDOR_MODEL_TRACKED_FILES = 0`、
`SAFETY_GATE: PASS`；`python scripts/provenance_check.py`、`python scripts/netlist_stats.py`
（`DEVICE_COUNT_CHECK: PASS`）。未 merge `main`。
HEAD SHA 由 `git log --oneline -1` 现取，写在这里必然过期，故本文不抄。

## 8. 请你确认（停在 USER_GUI_PARAMETER_REVIEW）

1. 关掉 Virtuoso 会话 → 我把修复应用到正式 `c2mos_dff_1bit` 并重跑闸门（脚本一条，已验证）。
2. 打开 `microled_cells/c2mos_dff_1bit_paramfix/schematic`，看属性编辑器里 `mn_c` 是否已是
   `Length 200n / Total Width 2u / Finger Width 2u`，`mp_c` 是否 `4u`、`mn_k1` 是否 `500n`；
   标签 `*Error*` 与 `'l' is not a real value` 是否消失（批量会话不重画 PCell 图形，这条只能你看）。
3. 若 GUI 里符号未按新尺寸重画或引脚与导线错位，属预期内的"参数改了、图形未重算"，
   是否要我下一步做重新求值/重排，等你决定（本轮禁止我动导线与布局）。
4. `sch1_import_top`（SCH-1 导入脚手架）与本轮的 `c2mos_dff_1bit_pre_paramfix`、
   `c2mos_dff_1bit_paramfix` 三个 cell 的去留。
