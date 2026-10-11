# c2mos_gui_manual_review.md — C²MOS Virtuoso GUI 人工验收清单（只读生成）

生成时间：2026-10-11 20:4x（guest `work-eda`）
本轮性质：**只读**。未打开/未保存/未修改任何 cell、symbol、PDK、testbench；
所有清单内容来自**本机** OA 数据库回读与机检输出，出处逐条标注。

被验收对象：`microled_cells / c2mos_dff_1bit`（commit `afc7b10` 生成，`7307b26` 波形级验证通过）

---

## 0. 怎么进入 GUI（不新造流程）

1. 双击桌面图标 **MicroLED IC Project**
   （`/root/Desktop/MicroLED-IC-Project.desktop`，`755`，`Exec` 指向仓库已跟踪启动器）
2. 或命令行等价：`/root/microled_ai_project/cadence_work/launch_virtuoso.sh`
   （自检用 `LAUNCHER_CHECK=1 ./launch_virtuoso.sh`，不启动 GUI）
3. 启动器会打印它自己解析到的 `DISPLAY`、`XAUTHORITY`、`cds.lib` 与 `virtuoso` 路径 —— 请先核这 4 行。

> 注意：**不要**用 `/etc/env/virtuoso` 启动（它是包装脚本，末尾 `virtuoso&` 会立刻返回），
> 也不要用 `dbAccess`/`virtuoso -nograph` 看图形 —— 那两类是批处理通道。

## 1. Schematic 打开路径

**Library Manager 里**：Library `microled_cells` → Cell `c2mos_dff_1bit` → View `schematic` → Open。

| 项 | 值 |
|---|---|
| 库 | `microled_cells`（`cds.lib` 第 6 行 `DEFINE microled_cells /root/microled_ai_project/cadence_work/microled_cells`） |
| cell | `c2mos_dff_1bit` |
| 磁盘位置 | `/root/microled_ai_project/cadence_work/microled_cells/c2mos_dff_1bit/schematic/sch.oa` |
| 大小 / 时间 | 37,796 B / `2026-10-11 20:02`（自生成后**未再被写过**） |
| `master.tag` | `-- Master.tag File, Rev:1.0` + `sch.oa` |
| 技术库 | 库根出现 `tech.db`（第一个 cell 写入时由 OA 生成） |

- [ ] Library Manager 能看到库 `microled_cells`（与 `smic18mmrf`、`microled_dirver0` 并列）
- [ ] `c2mos_dff_1bit` 出现在 Cells 列表里
- [ ] 打开 schematic 后**没有**报错弹窗，尤其是不得出现 `'l' is a not real value` / `simW` 相关告警

## 2. Cellview 清单（本机磁盘实测）

`microled_cells` 库内 5 个 cell：

| cell | 视图 | 说明 |
|---|---|---|
| **`c2mos_dff_1bit`** | `schematic` + `symbol` | 本清单的验收对象（Scan Driver 数字核心 1 bit） |
| `data_sink_1ch` | `schematic` + `symbol` | 冻结 Data Driver（已单独验收） |
| `data_bias_ref` | `schematic` + `symbol` | 其共享偏置参考 |
| `sch1_top` | `schematic` | C²MOS 的 ASG 导入 wrapper |
| `sch3_top` | `schematic` | Data Driver 的 ASG 导入 wrapper |

`symbol` 视图由 spiceIn/ASG **自动生成**（`symbol.oa` 22,764 B），仓库对 SCH-3 已披露该行为；
本机**未**对 symbol 做过程序化校验 ⇒ 见 §3 的人工核对项。

- [ ] 5 个 cell、视图种类与上表一致（无多余 cell、无 `layout` 视图）
- [ ] `c2mos_dff_1bit` 的 symbol 引脚名 = `d clk q qbar vdd vss`（6 个，与 §3 一致）
- [ ] `smic18mmrf` 库可见且能打开 `n18`/`p18`/`n33`/`n33_dnw_4t_ckt` 器件（PDK 未被改动的旁证）

## 3. 外部接口（6 个端子）

来源：本机只读回读 `cadence_work/logs/sch_nograph_20261011_200240.log`。
单元内共 13 条网络，**其中 6 条带 pin**（即外部接口），7 条是内部节点。

| 端子 | 方向（黄金网表声明） | 连接到的器件端子（OA 实测，完整清单） |
|---|---|---|
| `clk` | input | `mn_c.G`、`mp_c.G`、`mn_s1.G`、`mp_m1.G`（**4** 处） |
| `d` | input | `mn_m2.G`、`mp_m2.G`（**2** 处） |
| `q` | output | `mn_k4.D`、`mn_s2.D`、`mp_k4.D`、`mp_s2.D`（drain）+ `mn_k3.G`、`mp_k3.G`（栅）⇒ **6** 处 |
| `qbar` | output | `mn_k3.D`、`mp_k3.D`（drain）+ `mn_k4.G`、`mp_k4.G`（栅）⇒ **4** 处 |
| `vdd` | power | **16** 处：9 只 p18 的 bulk 全在此；`mp_c/mp_k1..k4/mp_m1/mp_s1/mp_s2` 的 source 也在 vdd（`mp_m2/mp_s2` 的 source 是内部堆叠节点 `x1/y1`） |
| `vss` | power | **16** 处：9 只 n18 的 bulk 全在此；`mn_c/mn_k1..k4/mn_m1/mn_s1` 的 source 也在 vss（`mn_m2/mn_s2` 的 source 是 `x2/y2`） |

内部节点（不是端口）：`clkb`(4) `m`(8) `mb`(4) `x1`(2) `x2`(2) `y1`(2) `y2`(2)。

- [ ] 6 个端子名与大小写**完全**是 `d clk q qbar vdd vss`（黄金 subckt 头顺序）
- [ ] `vdd`/`vss` 各自只有 16 处连接，且**所有衬极都接轨**（ ⇒ 无独立 bulk 端口，符合 PDK 器件形态）
- [ ] `d` 只出现在 2 只管子的栅极上（不得出现 `d` 直接连到 `q`/`qbar` 的路径）
- [ ] 只有 1 个外部时钟输入 `clk`；`clkb` 必须是**内部**节点（4 处连接，都不是端口）

## 4. MOS 结构分区（18 只 = 9 `n18` + 9 `p18`）

分区依据 `spectre/C2MOS_DFF.scs` 的注释分组与本机回读的端子连接；尺寸来自机检表
`results/scan_c2mos_device_parameters.csv`。全部 `l=200n`、`m=1`、`fingers=1`。

| 分区 | 器件 | model / W | 端子连接（D G S B） |
|---|---|---|---|
| **时钟反相器**（`clk→clkb`） | `mn_c` | n18 / 2u | `clkb clk vss vss` |
| | `mp_c` | p18 / 4u | `clkb clk vdd vdd` |
| **master 锁存（求值相）** | `mp_m1` | p18 / 4u | `x1 clk vdd vdd`（时钟管在轨侧） |
| | `mp_m2` | p18 / 4u | `m d x1 vdd`（数据管在节点侧） |
| | `mn_m1` | n18 / 2u | `x2 clkb vss vss` |
| | `mn_m2` | n18 / 2u | `m d x2 vss` |
| **master keeper**（`m↔mb` 交叉耦合弱反相对） | `mn_k1` | n18 / 500n | `mb m vss vss` |
| | `mp_k1` | p18 / 1u | `mb m vdd vdd` |
| | `mn_k2` | n18 / 500n | `m mb vss vss` |
| | `mp_k2` | p18 / 1u | `m mb vdd vdd` |
| **slave 锁存（求值相）** | `mp_s1` | p18 / 4u | `y1 clkb vdd vdd` |
| | `mp_s2` | p18 / 4u | `q m y1 vdd` |
| | `mn_s1` | n18 / 2u | `y2 clk vss vss` |
| | `mn_s2` | n18 / 2u | `q m y2 vss` |
| **slave keeper**（`q↔qbar`） | `mn_k3` | n18 / 500n | `qbar q vss vss` |
| | `mp_k3` | p18 / 1u | `qbar q vdd vdd` |
| | `mn_k4` | n18 / 500n | `q qbar vss vss` |
| | `mp_k4` | p18 / 1u | `q qbar vdd vdd` |

结构要点（用于人工判断"画面对不对"）：
- 每个时钟化上下拉堆叠里**一只管看 `clk`、一只看 `clkb`**，master 与 slave 相反 ⇒ 非有效半周内两条支路都在轨侧断开，keeper 不会被写冲突。
- keeper 宽度是时钟路径宽度的 **0.25×**（n18 `2u→500n`、p18 `4u→1u`）。
- 数据通路 `d → m → q` 两级反相 ⇒ 上升沿触发、`q` 与 `d` 同相。

- [ ] 数 18 只 MOS：**9 n18 + 9 p18**，不得多也不得少
- [ ] 每只的 `W` 与上表一致（`2u×5 / 4u×5 / 500n×4 / 1u×4`），`L` 全 `200n`
- [ ] `simW` 属性在 Property Editor 里**不存在**（本轮清理后 18/18 `ABSENT`）
- [ ] master 与 slave 的时钟管栅极分别接 `clk`/`clkb` 且互为反相（不是两只同相）

摆放参考（ASG 自动放置，非设计意图，仅供"长这样才对"的核对）：整体落在
`x 0.075–8.925 µm`、`y 0.1375–10.0312 µm`；slave keeper 在左上（`mn_k4/mp_k4` x≈0.075），
master 支路在右列（x≈7.575–8.925），`mn_c/mp_c` 在右下/右上角（y≈8.0、9.4）。

## 5. 当前限制：`terms = 0`

**这是已知且刻意保留的状态，不是本轮新引入的缺陷。**

- OA 数据库里 `dbGet(cv "terms")` 读回 **0** 个端口对象；6 个外部接口目前只是**带名字的 net**（带 pin 的那 6 条），端口方向信息在批量会话里读不到。
- 出处：仓库对同一现象的历史判定 `PORT_DIRECTIONS_OA: UNREADABLE_IN_BATCH`；本机实测 `terms=0`（`results/evidence/scan_c2mos_tb_assert_ff1_schematic.txt` 同源的 `RD-CELL ... terms=(0)`）。
- 因此**功能验证走的是网表路线**：cellview → 只读回读 → `sch2_netlist_from_readback.py` 重建网表 → Spectre。已证明本机原理图的断言报告与冻结网表**逐字节相同**（`ff1 33`、`ff1_sch 33`、`shift3 40`、`shift3_sch 40`，零失败）。

GUI 里你会看到什么、该得出什么结论：

- [ ] 若 Schematic 窗口里 `d clk q qbar vdd vss` 显示为**网络标签而非 port 图形** ⇒ 符合预期（`terms=0`），**不要**判为画错
- [ ] 若 `Check > Electrical Rule` 报出与缺失端口相关的告警 ⇒ 属同一限制的连带表现，记录原文即可，不要当场改
- [ ] 若 symbol 视图里有 6 个引脚且名字正确 ⇒ 说明 ASG 生成的 symbol 独立于 `terms`，这反而是好消息；请与 §3 的端子表逐字比对
- [ ] 需要"有真端口"的版本吗？那是一个**新的写操作**（建 port 对象 + 保存），任务书本轮禁止，需你另行批准（仓库对应件：`scripts/sch1_gen_ports.py` + `skill/sch1_ports.gen.il`，历史上仍是未闭环项）

## 6. 禁止项遵守核实（本轮）

未修改 cell / symbol / PDK / testbench；未启动 GUI（清单里 §0 是**给你**的操作步骤）；
未改 `cds.lib`、`display.drf`、模型卡、`.vmx`；未 commit 任何库数据变更。
本轮只新增本报告文件。启动器与快捷方式仍是上一轮状态：
`launch_virtuoso.sh` md5 `57be646893b671721bbea0326e3e7e06`、`MicroLED-IC-Project.desktop` 433 B `755`。
