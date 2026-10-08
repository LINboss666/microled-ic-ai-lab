# SCH-3：Data Driver Candidate E-DNW 的 Virtuoso 原理图实现与自动验证

本轮把评审已接受的 15 µA 数据驱动（Candidate E-DNW）做成 IC617 里真实可编辑的 OA 原理图，
并按 SCH-2 建立的纪律逐实例回读验证。核心结论：**5/5 器件的 master、L、W、D/G/S/B 全部与黄金网表
一致，OA 派生网表在 tt/ss/ff 三 corner 的 DC 与帧尺度瞬态数值与已接受的 DATA-5 结果逐位相同
（3202 个比较项 delta 全为 0）**。同时纠正了本项目一条从 SCH-1 沿用至今的错误认知（见 §7）。

```
TASK:                       SCH-3 DATA DRIVER VIRTUOSO SCHEMATIC
TEACHER_PDK:                ms018_enhanced_v1p2_rev0 / library smic18mmrf
                            /root/microled_ai_project/pdk/smic18mmrf_teacher（未修改）
DESIGN_LIBRARY:             microled_cells（唯一可写库）
DATA_PDK_PARAMETER_SMOKE:   PASS
DATA_CHANNEL_SCHEMATIC:     microled_cells/data_sink_1ch   4 MOS / 8 nets / 6 port pins / 46 figures
DATA_BIAS_SCHEMATIC:        microled_cells/data_bias_ref   1 MOS / 2 nets / 2 port pins / 16 figures
PER_CHANNEL_MOS:            4
SHARED_MOS:                 1
DNW_MASTER:                 smic18mmrf/n33_dnw_4t_ckt（按名实例化，未用普通 n33 顶替）
OA_PARAMETER_READBACK:      PASS
GOLDEN_WL_MATCH:            L 5/5, W 5/5, MASTER 5/5
TERMINAL_CONNECTIVITY_MATCH: 5/5（A1..A6 六条断言全 PASS，OA_CONNECTIVITY: PASS）
CDF_EVALUATION_ERRORS:      0
SCHEMATIC_CHECK_AND_SAVE:   PASS（schCheck 0 errors；dbSave t；sink 有 2 条 solder-dot 警告，单列于 §8）
NATIVE_CADENCE_NETLIST:     BLOCKED（nograph 与 -restore 两条启动路径都对 data_sink_1ch 复测）
OA_DB_EXPORTER:             使用；导出网表的 W/L 与 D/G/S/B 全部取自 OA 回读
TT / SS / FF:               PASS / PASS / PASS（DC on+off、帧尺度瞬态、受害通道串扰）
TWO_CHANNEL_INDEPENDENCE:   PASS（静态 2x2 四组合 + 一常开一翻转的帧尺度瞬态，与 accepted 数值相同）
KNOWN_SOLDER_DOT_WARNINGS:  data_sink_1ch 2 条 —— 按禁区未处理
C2MOS_PROTECTION:           未改动（文件时间戳与 schCheck 计数双向确认，见 §1）
REVIEW_BRANCH:              feature/data-driver-virtuoso-schematic（依赖 feature/c2mos-virtuoso-schematic）
NEXT:                       USER_GUI_REVIEW
```

---

## 1. 工程保护与安全边界（§1）

| 检查 | 方法 | 结果 |
|---|---|---|
| 是否有 Virtuoso/GUI 会话 | guest `ps -ef \| grep -Ei "virtuoso\|cds_\|dbaccess\|xvnc"` | 0 进程（用户已关机；本轮未强制关闭任何会话） |
| OA 写锁 | `find /root/microled_ai_project -name ".cdslck*"`；库目录 `ls -a \| grep cdl` | 无锁 |
| C²MOS 三只 cell 是否被动 | 逐文件 mtime：`c2mos_dff_1bit/schematic/*` 仍为 2026-10-08 23:21，`_paramfix` 23:37，`_pre_paramfix` 文件 23:21 | 内容未变；`_pre_paramfix` 目录 mtime 变成 10-09 00:36 只是会话开合（目录内文件时间戳未变） |
| C²MOS 结构不变 | `schCheck` 只读打开 `c2mos_dff_1bit` 与 `_paramfix` | 各 0 error / 5 warning，5 条 solder-dot 坐标与用户此前在 GUI 看到的 5 条一致 |
| 写入范围 | 只新建 `data_sink_1ch`、`data_bias_ref`、`data_pdk_param_smoke`、`sch3_top`、`sch3_smoke_top` | 未覆盖任何既有 cellview（导入脚本对已存在 cell 直接 REFUSE 退出） |
| 正式 C²MOS 原理图 | 未触碰 | 任务 #71/#76 保持等待；不在本轮范围（§1 明令"不要顺手完成"） |

## 2. 分支与依赖（§2）

- 新分支 `feature/data-driver-virtuoso-schematic`，从 `feature/c2mos-virtuoso-schematic` 的
  HEAD `6a8ba7d` 切出。
- **依赖是显式的**：SCH-2 的永久闸 `scripts/sch_parameter_integrity_check.py`、它的单元测试、
  `AGENTS.md` 第 27 条与 `reports/lessons_learned/spicein_cdf_parameter_mapping.md` 只存在于那条分支上，
  所以本轮必须从它分叉而不是从 main 分叉（main=23e471c 尚无这些文件）。
- 未合并 main，未改写历史。

## 3. 黄金连接关系的提取（§3–§6）

权威来源：`spectre/generated/ddrv_E_local_gate_n33_tt_l2e6w2e5_ch1_iprobe_dnwpass_tt_on.scs`
（DATA-5 已接受、产出 `results/data_driver_Ednw_corner_*` 的那份 deck）。

`scripts/sch3_golden_extract.py` 解析它并做四件事，全部机检：

1. 器件守卫：`Mpass_local` master 必须是 `n33_dnw_4t_ckt`；Source==Body==本通道 `vbias_ch`；
   body 不得接 `vss`；`Mout` 栅 = `vbias_ch`；`Mcas` 栅 = `vcas`、漏 = `data_out`；
   `Mbleed_local` 栅 = `data_en_b`；`Mref` 二极管接法；`l/w` 必须解析成数值且无额外属性。
   → `GOLDEN_GUARDS: DNW_MASTER=n33_dnw_4t_ckt MPASS_SOURCE_EQ_BODY=YES MREF_DIODE=YES ...`
2. 按角色切成两个 cell：`data_sink_1ch`（Mout/Mcas/Mpass_local/Mbleed_local）与
   `data_bias_ref`（Mref）；理想 15 µA 源、VCAS/DATA_EN 源、iprobe、分析语句留在 testbench。
3. 端口改名走**声明表**（`results/data_driver_net_rename_map.csv`）：
   `data_en→DATA_EN, data_en_b→DATA_EN_B, vbias→VBIAS_SHARED, vcas→VCAS, data_out→DATA_OUT,
   vss→VSS`；内部节点 `node_m`、`vbias_ch` 保持原名（不做引脚）。
4. 回环校验：重新解析生成的 subckt，反向套用改名表，必须逐条还原成黄金 deck 的器件行
   → `ROUND_TRIP_DEVICES: 5/5`、`IMPORT_LINES_MATCH_GOLDEN: PASS`。
   连接关系不是手写的，且这条判断有脚本退出码背书。

引脚方向按 §6 的电路语义写进导入网表的声明（DATA_EN/DATA_EN_B/VBIAS_SHARED/VCAS=input，
DATA_OUT=output，VSS=inputOutput；`data_bias_ref` 的 VBIAS_SHARED=output）；
OA 侧回读在批处理里读不到方向（见 §9 已知问题）。DATA_OUT 只是电流下沉节点，
testbench 里它是被 `Vout` 源扫描的独立变量，原理图单元不驱动电压。

## 4. n33 与 n33_dnw_4t_ckt 的真实 CDF（§7，本轮第一个硬结论）

只读探测 `skill/sch3_cdf_probe.il`（日志 `results/evidence/sch3_cdf_probe.log`）：

| master | CDF 参数名 | **默认值** | 符号端子 |
|---|---|---|---|
| `n33` | `l w fw m fingers model` + `as ad ps pd` | **`l=350n w=350n fw=350n m=1 fingers=1`** | 4 只，按名 `D G B S` |
| `n33_dnw_4t_ckt` | 同上 | 同上 | 4 只，按名 `D G B S` |
| `n18`（对照） | 同上 | `l=180n w=220n fw=220n` | 4 只 |

三条必须写下来的事实：

1. **默认值随器件族改变**：3.3 V 族是 350n/350n，不是 n18 的 180n/220n。若照搬 SCH-2 的门参数
   （`--pdk-default-l 180n --pdk-default-w 220n`），"整批管子回退到默认"这件事**不会被检出**——
   也就是 SCH-2 事故换了个器件族就会重演。永久闸因此新增 `PDK_DEFAULT_DECLARATION_MISMATCH_COUNT`：
   回读日志里带出 master 自己的 CDF 默认值（`RD3-MPARAM`），与命令行声明不一致就直接失败。
2. 参数名沿用 `l/w/fw/m/fingers/model` 是**实测**出来的，不是假设；`wf/mult/area/nws/bulk/dnw` 全部 ABSENT。
3. 符号视图的端子列表顺序在不同 master 间不一样（n33 是 D G B S，n18 是 S G B D），
   所以任何"按位置连端子"的写法都不可用；回读一律按端子名取网络。

## 5. 冒烟门 data_pdk_param_smoke（§8）

尺寸刻意既不等于设计值也不等于默认值：`n33` 1u/8u、`n33_dnw_4t_ckt` 3u/7u。
写入→`dbSave`→新会话只读回读→永久闸：

```
MOS_MASTER_MATCH 2/2   L_MATCH 2/2   W_MATCH 2/2
UNRESOLVED/CDF_ERROR/INVALID_LENGTH/DEFAULT_VALUE_FALLBACK/PDK_DEFAULT_DECLARATION_MISMATCH = 0
DNW 端子映射：terms=("B" "D" "G" "S") D="smoke_d" G="smoke_g" S="smoke_s" B="smoke_b"
OA_DEVICE_PARAMETER_READBACK: PASS
DATA_PDK_PARAMETER_SMOKE: PASS
```

同一轮回读同时证实 **SCH-2 的缺陷在 3.3 V 族上一模一样重现**：spiceIn 写入修
`raw_l="1e-06"`、宽度只进 `simW`，`w/fw/fingers/m` 全是 ABSENT，CDF 报 350n 默认
（`results/evidence/sch3_smoke_readback.log`）。也就是说这不是"表达式名"的偶发问题，
而是导入器对符号封装型 PDK 器件的固有行为。

## 6. 正式生成、修参与回读（§9–§11）

流程（全部有可复现入口）：

```
python scripts/sch3_golden_extract.py ...        # 黄金 deck -> 两个 subckt + 改名表 + 黄金 CSV
bash scripts/sch3_asg_import.sh spectre/import/sch3_top.scs   # TOP=sch3_top CELLS="data_sink_1ch data_bias_ref"
python scripts/sch2_gen_param_skill.py results/data_driver_golden_data_sink_1ch.csv skill/sch3_sink_table.gen.il
bash scripts/sch_virtuoso.sh skill/sch3_fix_params.il          # SCH3_CELL=... SCH3_TABLE=...（不写 simW、不调任何 callback）
bash scripts/sch_virtuoso.sh skill/sch3_readback.il            # 新会话只读回读
bash scripts/sch3_verify.sh results/evidence/sch3_readback_post_fix.log
```

- 导入：`ASG_PROBLEM_LINES: 0`，两只 cell + 一个脚手架 top 建成。
- 修参前的回读（`results/evidence/sch3_readback_prefix.log`）：**W_MATCH 0/4 + 0/1，
  UNRESOLVED_PARAMETER_COUNT 8+2**，而同一份日志的连接关系检查 5/5 全对——
  这正是"连接正确≠参数正确"的实测样本。
- 修参后的回读：`results/data_driver_schematic_devices.csv` 五行全 PASS，
  `raw_*` 与 `cdf_*` 都是数值（`2u/20u/5u/2u`，fingers=m=1）。
- `sch3_fix_params.il` 里加了结构性守卫：cellview 中 master 属于 `smic18mmrf` 的实例数必须等于
  参数表行数，否则拒绝写入（防止"表少一只、那一只悄悄停在默认值"）。
- §8 的写参纪律：**不写 `simW`**（§7 明令），`w=fw`、`m=fingers=1`，数值字符串由
  `sch2_gen_param_skill.py` 生成并强制"写回原值必须精确相等"。

## 7. 纠正一条沿用两轮的错误认知（新教训）

`schCheck` 在批处理 `virtuoso -nograph` 会话里**可以调用**：

```
getd('schCheck) => nil            # 这条把本项目骗了两轮
errset(schCheck(cv)) => ((0 2))   # 实际返回 (errors warnings)，并打印具体警告
errset(schCreate) => nil          # schCreate/schCreateWire 确实不可用
```

依据日志 `results/evidence/sch3_schcheck_probe.log`：sink 0 error/2 warning、bias 0/0、smoke 0/0、
`c2mos_dff_1bit(_paramfix)` 各 0/5。也就是说编辑器包的"检查"函数是可达的，不可达的是"查询函数是否存在"
这条路径（与 `AGENTS.md` 第 8 条 `funcall` 恒为 nil 是同一类坑）。两条影响：

1. §12 可以按真实语义给出 `SCHEMATIC_CHECK_AND_SAVE: PASS`，不需要把 dbCheck 包装成它。
2. 反向教训：**不要用 `getd` 判定 API 可用性**，要用 `errset(<字面调用>)`。已写入 AGENTS 第 28 条。

## 8. 警告与禁区（§12、§16）

- `schCheck` 在 `data_sink_1ch` 报 2 条 `Warning: Solder dot on cross over at (1.2500, 0.5000)` /
  `(1.8750, 1.2500)`。这是导线交叉的几何问题，与 C²MOS 那 5 条同类，按 §16（不排版美化、不动交叉点）
  与 §12（单独上报）处理：**已知、未修、不影响电气性**。
- 本轮未做：布局美化、symbol 设计、扫描输出级、TCON、layout/DRC/LVS/PEX、384 通道、
  拓扑或 W/L 改动、C²MOS 正式原理图覆盖。
- 副作用披露：spiceIn/ASG 会为导入的 subckt 自动生成 `symbol` 视图（`data_sink_1ch/symbol` 等）。
  那是工具产物，不是设计 symbol，也未做任何验证；§16 禁止的是"最终 symbol"，此处没有交付 symbol 含义。

## 9. 网表与仿真回归（§13–§15）

原生网表器复测（`results/evidence/sch3_native_netlist_{nograph,restore}.log`，对象是本轮的
`data_sink_1ch`）：`asiCreateSession()` → nil、`nlCreateDesign/nlCreateFormatter` 三种参数形状全 nil，
两条启动路径一致 → `NATIVE_CADENCE_NETLIST_VERIFICATION: BLOCKED`。

于是用自制的 OA 导出器 `scripts/sch3_deck_from_oa.py`，标 `OA_DB_EXPORTER`，其纪律是：

- 器件行的 master、模型名、D/G/S/B 网络、`l=`、`w=` **只来自只读回读日志**；
- flat 形式还会把重建出的器件行与黄金 deck 逐条 diff（网络、master、条数），
  不一致就 `OA_DECK_MISMATCH` 退出——所以"原理图与已接受电路不再是同一连线"会中断回归而不是悄悄通过；
- testbench（include/理想源/iprobe/分析语句）逐字保留 accepted deck 的内容。

回归入口 `scripts/sch3_regression.sh`（`results/evidence/sch3_*.txt` 20 份，`rc_total=0`），
每步都跑 `tb_preflight.sh` + `run_spectre.sh` 并要求 `errors=0 warnings=0`，还要检查分析器自己的判定行。
比对入口 `scripts/sch3_compare_all.sh` 对照**仓库里已评审的** `results/data_driver_Ednw_*`：

| 数据 | 比较项 | 最大偏差 | 判定 |
|---|---|---|---|
| DC 扫描（3 corner × on/off，996 点 × 3 列） | iout_uA / err_pct / vbias_V | 0 | PASS |
| 帧尺度瞬态（ch0，3 corner × 20 列） | 整定、关断、ON 稳态、泄漏、振铃判据等 | 0 | PASS |
| 受害通道串扰（victim，3 corner） | peak/charge error、glitch 时长、保持率 | 0 | PASS |
| 双通道静态 2×2（4 组合 × 2 通道） | i_baseline、mean、节点电压 | 0 | PASS |

合计 3202 个 (组, 列) 比较项，delta 非零的行数：**0**。两列被显式排除并在脚本头部写明理由：
`ring_flip_ratio`（在基波 p2p=0.000000 µA 上统计符号翻转比例，两侧判据 `ADJACENT_POINT_ALTERNATION: NO`
本身已比对且一致）与 `q_error_C`（亚 fC 级残余绝对电荷，判据用的 `charge_error_pct` 已比对为 0）。

关键数值（OA 网表，与 accepted 相同）：`VBIAS_SHARED` tt/ss/ff = 0.884261 / 0.951269 / 0.818122 V；
`IOUT@1.2 V` = 14.931906 / 14.899428 / 14.964881 µA；导通整定 27.27 / 36.54 / 24.25 ns；
静态四组合 (0,0)(0,1)(1,0)(1,1) 的 I0/I1 与 accepted 表逐值相同；受害通道每帧电误差
0.0726 / 0.0877 / 0.0663 %。

层级形式（两个 cellview 作为 subckt 组合）的 deck 已生成（`spectre/generated/sch3_oa_hier_*.scs`）
但**未仿真**：`tb_preflight.sh` 要求每个 subckt 实例都带名为 `vdd`/`vss` 的端口，而本单元是低侧电流沉、
按 §6 没有 VDD 引脚，端口名也是规范的大写名——这是该闸的适用范围问题，不是电路缺陷。放宽共享闸是人工决定，
不在无人监督的夜间运行里顺手做，因此如实记为
`OA_HIERARCHICAL_DECK: BLOCKED_BY_PREFLIGHT_PORT_RULE`。两通道独立性因此由 flat 形式（每通道私有
`node_m/node_m1`、`vbias_ch/vbias_ch1`，共享一只 `Mref`）证明，加上 OA 侧证据：`data_sink_1ch` 8 条网络
中仅 6 条有 pin，`vbias_ch`/`node_m` 不是端口，即每通道实例天然持有自己的栅/体节点。

## 10. 已知问题与留给用户的事

1. **GUI 复核**：`data_sink_1ch` / `data_bias_ref` 属性编辑器里 Length/Total Width/Finger Width/Fingers/
   Multiplier 应显示 2u / 20u（Mpass 5u、Mbleed 2u）/ 2u / 1 / 1，且实例标签不得有 `*Error*`。
   批处理不重新求值 PCell 图形，`inst->bBox` 仍是默认符号尺寸，所以显示层只能由用户确认：
   `GUI_PARAMETER_DISPLAY: USER_VERIFICATION_REQUIRED`。
2. **端口方向**：ASG 建的端口是 `basic/iopin` 实例，批处理会话里 `cv->terms` 为空、
   `inst->direction` 为 nil，方向只能从导入网表的声明核对 →
   `PORT_DIRECTIONS_OA: UNREADABLE_IN_BATCH`（不是"全部 inputOutput"的默认值，是读不到）。
3. **2 条 solder-dot 警告**（§8）留给排版阶段。
4. `TECHNOLOGY_LIBRARY_ATTACHED: UNRESOLVED` 延续 SCH-1/2 的状态，本轮未触碰。
5. C²MOS 正式 cell 的参数修复仍未应用（等用户明确指示；本轮 §1 明令不得顺手做）。

## 11. 工件

脚本：`scripts/sch3_golden_extract.py`、`sch3_asg_import.sh`、`sch3_expect_from_netlist.py`、
`sch3_connectivity_check.py`、`sch3_verify.sh`、`sch3_deck_from_oa.py`、`sch3_regression.sh`、
`sch3_compare_regression.py`、`sch3_compare_all.sh`；改动的永久闸：
`scripts/sch_parameter_integrity_check.py`（新增族默认值一致性检查、数值而非字符串比较 CDF/raw）、
`scripts/test_sch_parameter_integrity_check.py`（11 例，含本轮三条新判别）、`scripts/sch2_golden_params.py`
（main 守卫，可复用 SI 解析器）。
SKILL：`skill/sch3_cdf_probe.il`、`sch3_readback.il`、`sch3_fix_params.il`、`sch3_dbcheck.il`、
`sch3_schcheck_probe.il`。
结果：`results/data_driver_golden_devices.csv`（+ 每 cell 一份）、`data_driver_net_rename_map.csv`、
`data_pdk_param_smoke_expected.csv`、`data_pdk_param_smoke_readback.csv`、
`data_driver_schematic_devices.csv`、`data_driver_schematic_connectivity.csv`、
`data_driver_schematic_{dc,transient,xtalk,static}.csv`、`data_driver_schematic_regression.csv`；
证据：`results/evidence/sch3_*.log|txt` 30 份。网表：`spectre/import/*.scs`、
`spectre/generated/sch3_oa_*.scs`。日志：guest `logs/sch3_regression_full.log`。

**NEXT: USER_GUI_REVIEW**，停在这里。不做 symbol、不做扫描输出级、不做 layout，不自建 main 合并。
