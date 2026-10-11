# scan_driver_c2mos_schematic.md — C²MOS 1bit 从 Spectre 冻结设计到 Virtuoso schematic

执行时间：2026-10-11 20:02（guest `work-eda`，RHEL 6.5 / IC617 6.1.7-64b）
任务书：Scan Driver 数字核心 C²MOS，**transistor-level 已验证设计 → Virtuoso schematic**；
不重新设计、不改晶体管尺寸、不改 PDK、不做 hierarchy、不做 layout、不搭 testbench。
本轮性质：**生成 + 复验**，全部使用仓库既有冻结件。

---

## 1. 冻结前提（本轮没有新增任何设计判断）

| 冻结条件 | 来源（仓库既有） |
|---|---|
| `C2MOS_DFF_1CH: PASS` | `reports/c2mos_dff_result.md`、`reports/c2mos_validation_report.md` |
| `C2MOS_SHIFT_3STAGE: PASS` | `reports/c2mos_validation_report.md`（40 断言） |
| `FUNCTION_REGRESSION: PASS` | `reports/final_validation.md` |
| 结构 = **18 MOS**（9 `n18` + 9 `p18`） | `spectre/C2MOS_DFF.scs` + `scripts/netlist_stats.py` 机检 |
| 尺寸 `ln=2e-7 wc=2e-6 wcp=4e-6 wk=5e-7 wkp=1e-6` | `spectre/C2MOS_DFF.scs` 内 `parameters` 行 |
| 工艺 | `smic18mmrf` = `/root/tech/teacher_pdk/smic18mmrf`（老师 2025 BSIM4 Enhanced） |

**未改动**：`spectre/C2MOS_DFF.scs`（只读，导入脚本自己复制改名再 diff）、PDK、`display.drf`、
`techfile.tf`、模型卡、任何已有 cell。

## 2. 生成流程（一条命令串起来，脚本已入库）

驱动脚本 **`scripts/scan_driver_c2mos_pipeline.sh`**（本轮新增，逐步记录 rc 与 token），
在 guest 以 `setsid nohup` 分离执行，日志落 `cadence_work/logs/c2mos/`：

| 步 | 使用的仓库件 | 结果 |
|---|---|---|
| 1 导入 | `scripts/sch1_asg_import.sh`（**全默认参数**，无覆盖） | `ASG rc=0`，`SPICEIN-33/54` 命中 3 次 |
| 2 修复前回读 | `skill/sch3_readback.il`（mode `"r"`） | 机检 **FAIL**（记录缺陷形态） |
| 3 写尺寸 | `skill/sch3_fix_params.il` + 已提交 `skill/sch2_param_table.gen.il` | `rc=0`，token `FX3_DONE` |
| 4 清残留 | `skill/scan_del_simw.il`（本轮新增，见 §5） | 删除 18 个 `simW`，`DS_DONE` |
| 5 修复后回读 + 机检 | `sch3_readback.il` + `sch_parameter_integrity_check.py` | **PASS** |
| 6 结构不变证明 | `scripts/sch2_connectivity_diff.py --before --after` | **PASS** |

导入脚本的关键守卫（其自身实现，非我添加）：
`GOLDEN_INSTANCE_LINES=18  IMPORT_COPY_INSTANCE_LINES=18` —— 重写改名后逐行核对 MOS 行数与黄金一致，
不一致就拒绝再跑 spiceIn；且 `overwriteCells=NONE`，不覆盖任何既有 cell。
`BODYFORM=subckt_top`：SPICEIN-77 拒绝"topCell 同时是文件里的 subckt"，
所以按冻结流程生成一个 wrapper（`WRAPPER_TOP_CELL=sch1_top WRAPPER_INSTANCE=I1`）。

## 3. 结果

```
库 microled_cells 现有 cell：
  c2mos_dff_1bit   schematic + symbol      <- 本轮，Scan Driver 数字核心，机检 PASS
  data_sink_1ch    schematic + symbol      <- 上一轮，冻结 Data Driver，机检 PASS
  data_bias_ref    schematic + symbol      <- 上一轮，机检 PASS
  sch1_top         schematic               <- 本轮导入 wrapper（sch3_top 为上一轮 wrapper）
  tech.db / .oalib / data.dm / cdsinfo.tag
```

最终机检（`OA_DEVICE_PARAMETER_READBACK: PASS`，退出码 0）：

```
MOS_COUNT_GOLDEN: 18       MOS_COUNT_READBACK: 18
MOS_MASTER_MATCH: 18/18    L_MATCH: 18/18    W_MATCH: 18/18
CDF_ERROR_COUNT: 0         DEFAULT_VALUE_FALLBACK_COUNT: 0
INVALID_LENGTH_COUNT: 0    UNRESOLVED_PARAMETER_COUNT: 0
PDK_DEFAULT_DECLARATION_MISMATCH_COUNT: 0
PORT_PINS: clk d q qbar vdd vss
POST simW tally:  18 simW="ABSENT"
POST raw_w tally: 1u x4   2u x5   4u x5   500n x4      （cdf_w 与之逐项相同）
```

逐实例 18 行表格见 `reports/scan_driver_c2mos_parameter_readback.md`（由脚本从机检 CSV 渲染）
与 `results/scan_c2mos_device_parameters.csv`。

## 4. 修复前的真实缺陷形态（为什么必须过机检而不是看数量）

ASG 刚导完时，18 只管子的 **master 全对、实例数全对、连接全对**，但：

```
L_MATCH: 0/18    W_MATCH: 0/18    INVALID_LENGTH_COUNT: 18    UNRESOLVED_PARAMETER_COUNT: 72
simW: 5x"wc"  5x"wcp"  4x"wk"  4x"wkp"        l 属性写的是表达式名字 "ln"
```

也就是 spiceIn 把网表里的**设计变量名字**而不是数值搬进了属性，且宽度落在 CDF 不识别的 `simW` 上；
Virtuoso 读到的是 PDK 默认几何，GUI 会报 `'l' is not a real value` 一类告警。
`AGENTS.md` 第 27 条说的"SCH-1 就是这么把 18 只全部停在 PDK 默认 180n/220n 的原理图判成 PASS 的"
就是这条路径。本轮从修复前日志直接复现了它，并把它作为交付证据入库：
`results/evidence/scan_c2mos_readback_pre.txt`、`results/scan_c2mos_device_parameters_prefix.csv`。

## 5. 本轮新增的两件东西及其边界

1. **`scripts/scan_driver_c2mos_pipeline.sh`**：按顺序调用上面六个既有件，本身不含任何设计信息
   （没有 W/L、没有网表、没有拓扑）。
2. **`skill/scan_del_simw.il`**：删除导入器残留的 `simW` 属性。仓库既有件的规矩是"不再**补写** `simW`"
   （`sch3_fix_params.il` 全文不碰 `simW`），所以 `simW` 会作为惰性残留留下；
   本项目验收目标是 `simW ABSENT`，故补这一件。它的作用面被自证约束住：
   每个实例删除前后各打一行快照，含 `model/master/l/w/fw/m/fingers/D/G/S/B` 与 cellview 计数，
   日志原文（`results/evidence/scan_c2mos_pipeline_driver.txt`）：

   ```
   del count=18
   DS-BEFORE-SUMMARY instances=(24) nets=(13) shapes=(219) terms=(0)
   DS-AFTER-SUMMARY  instances=(24) nets=(13) shapes=(219) terms=(0)
   ```

   即**实例数、网络数、图形数、端口数一字未变**，只有 `simW` 从数值变为 ABSENT。
   另用 `sch2_connectivity_diff.py` 独立复核（它专断"只有尺寸字段允许变化"）：

   ```
   MOS_ROWS_BEFORE: 18   MOS_ROWS_AFTER: 18
   INSTANCE_COUNT_UNCHANGED: PASS   CONNECTIVITY_UNCHANGED: PASS
   MASTERS_UNCHANGED: PASS          EXTERNAL_PORTS_UNCHANGED: PASS
   COUNTS_UNCHANGED: PASS           SCHEMATIC_STRUCTURE_UNCHANGED: PASS
   ```

   单元拓扑与黄金网表逐脚对应（`sch1_asg_import.sh` 的 18/18 行守卫 + 上面的结构复核），
   本轮没有任何"优化"或"顺手改一下"的动作。

## 6. 完整性与约束遵守

- **PDK 零写入**：会话前后指纹均 **5333 条目、`diff` = 0 行**；PDK 内 `*.cdslck`/`CDS.log*`/`journal*` **0**
  （尽管每次会话都加载了厂商 `smic18mmrf/libInit.il`）。
- 未做 hierarchy / layout / DRC / LVS / PEX / testbench；未重设计；未改尺寸；未动 `data_sink_1ch`。
- 会话残留自查：结束时 `cdsMsgServer` 孤儿已清，`virtuoso_main=0`。
- 磁盘 `5.2G` 可用不变；PROJECT_ROOT 仍单源 `/root/microled_ai_project`。

## 7. 已知未处理项（不粉饰）

1. `terms=0`：ASG 生成的 cellview **没有 OA 端口对象**，端口以命名 net 形式存在
   （机检的 `PORT_PINS` 来自带 pin 的网络，故能列出 `clk d q qbar vdd vss`）。
   仓库对此的历史判定是 `PORT_DIRECTIONS_OA: UNREADABLE_IN_BATCH`，本轮按指示**未处理**，
   留给阶段7 人工在 GUI 里目视确认（这也是旧机同样存在的状态）。
2. `sch1_top` / `sch3_top` 两个导入 wrapper 仍在库里，是否作为交付物保留待定。
3. `symbol` 视图由 spiceIn 自动生成，本轮未对其做任何校验（无图形 API 可用）。
4. C²MOS 的功能级复验（`c2mos_check.sh ff1/shift3`）本轮**未跑** —— 任务书要求暂停且不搭 testbench，
   网表侧结论沿用仓库既有的 `C2MOS_DFF_1CH: PASS` / `C2MOS_SHIFT_3STAGE: PASS`，
   **不代表本机重跑过**。
