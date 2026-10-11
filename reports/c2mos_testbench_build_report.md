# c2mos_testbench_build_report.md — C²MOS testbench 搭建与 DFF 验证

时间：2026-10-11 21:01–21:05（guest `work-eda`，IC617 6.1.7-64b / Spectre 15.1.0.284.isr1）
方法来源：仓库已有件（`spectre/c2mos_ff1_func.scs`、`spectre/c2mos_ff1_from_oa_readback.scs`、
`scripts/sch3_asg_import.sh` 的参数表、`scripts/c2mos_check.sh`、`scripts/tb_preflight.sh`、
`scripts/sch2_netlist_from_readback.py`）。**没有新设计验证方法**。

## 0. 结论先说

> **更正（2026-10-11 深夜，见 `reports/c2mos_tb_cdf_audit.md`）**：下表第三行"ASG 没有把激励参数带进 OA 库
> ……不能充当验证载体"**是错的**，已作废。错因是我用黄金 deck 里的 **Spectre** 参数名
> （`val0/val1/period/delay/width/rise/fall`）去查 analogLib 的 CDF，而这些量在 `analogLib` 字典里叫
> `v1/v2/per/td/tr/tf/pw`（对应关系写在厂商 `data.dm` 的 `propMapping` 里）。按正确名字回读后实测：
> **黄金激励的 20 个数值全部已在 cell 里，raw 属性层与 CDF 层一致**（`TB_CDF_CHECK: PASS`，`ROWS=20 BAD=0`）。
> 该 testbench 真正缺的是**仿真分析设置**（`tran`/`save`），不是参数值。原始判决句留在下表以便追溯。

| | |
|---|---|
| Task 1 testbench cell | **已建成**：`microled_cells/c2mos_dff_tb/schematic`，8 实例，DUT 按名绑定正确 |
| Task 2 DFF 验证 | **通过**：`SCHEMATIC_DFF_FUNCTION: PASS`，33 断言 0 失败，两遍逐字节一致，preflight 先过 |
| ~~⚠ 但有一个新发现的硬限制~~ **（本行结论已被上面更正作废）** | ~~**ASG 没有把激励参数带进 OA 库**：`vdc`/`vpulse` 的 `dc/val0/val1/period/delay/width/rise/fall` 在**属性和 CDF 里都不存在** ⇒ `c2mos_dff_tb` **不能**充当验证载体，验证仍须走文本 deck~~ |

第二行用的是仓库既有的 `ff1_sch` 路径（DUT = 从本机 OA cellview 回读重建的网表 + golden deck 激励），
它绕开了上面那条限制；第三行说明**为什么不能用新 cell 直接仿真**。

## 1. 创建了哪些文件

| 路径 | 性质 |
|---|---|
| `microled_cells / c2mos_dff_tb / schematic`（guest 库内） | 本次交付物，8 实例 |
| `spectre/import/c2mos_dff_tb.scs` | 由脚本从 golden deck 解析生成的导入网表（文件头声明来源） |
| `scripts/c2mos_tb_build.py` | 建库脚本（解析 golden → 写 deck → 可选 `--import` 调 spiceIn） |
| `skill/c2mos_tb_readback.il` | 只读回读件（实例/master/端子/网络/属性/CDF 参数） |
| `cadence_work/asg_in/c2mos_dff_tb_param.il`、`cadence_work/logs/asg_spiceIn_tb_*.log` | 导入参数与 spiceIn 日志（运行时产物） |

**已清理**：探针用的临时库 `microled_probe`（含 `tb_probe`/`tb_probe2` 与其 deck/参数件）已删除，
`cds.lib` 回到 6 条 DEFINE。**未改动**：`c2mos_dff_1bit`（`sch.oa` 仍 37,796 B、mtime 20:02 不变）、
任何 MOS 尺寸、拓扑、PDK、model、`display.drf`、Data Driver、golden deck、已有脚本。

## 2. testbench 结构说明（cellview 实测，`results/evidence/` 内 TB-* 行）

```
instances=8  nets=7  terms=0
Vdd   analogLib/vdc:symbol      PLUS->vdd   MINUS->gnd!
Vss   analogLib/vdc:symbol      PLUS->vss   MINUS->gnd!
Ck    analogLib/vpulse:symbol   PLUS->clk   MINUS->gnd!
Dd    analogLib/vpulse:symbol   PLUS->d     MINUS->gnd!
X1    microled_cells/c2mos_dff_1bit:symbol   d->d clk->clk q->q qbar->qbar vdd->vdd vss->vss
Cq    analogLib/cap:symbol      PLUS->q     MINUS->gnd!   c=5e-14 (prop) / 50f (CDF)
Cqb   analogLib/cap:symbol      PLUS->qbar  MINUS->gnd!   c=5e-14 (prop) / 50f (CDF)
PIN0  basic/iopin:symbol        （ASG 为节点 0 生成的 IO 引脚）
nets: gnd! vdd vss clk d q qbar
```

绑定关系完全正确：DUT 六个端子**按名**对上六条网络，负载分别挂在 `q`/`qbar`，
`cap` 的 50 fF 也确实进了库（属性 + CDF 双证）。

⚠ 两点结构性偏差（ASG 行为，不是我选的）：
1. 网表的参考节点 `0` 被改名为 **`gnd!`** 并插了 `PIN0`(basic/iopin)。
   若将来把这个 cell 再导回网表仿真，必须显式把 `gnd!` 映射回 `0`，
   否则参考节点浮动 —— 正是 `AGENTS.md` 第 19 条那个"全部 PMOS 在动、NMOS 全死"的失效模式。
2. `terms=0`：cellview 没有端口对象（与 DUT 同一限制，本阶段禁止处理）。

## 3. 输入时序（全部解析自 golden deck，脚本内无任何自定数值）

`scripts/c2mos_tb_build.py` 从 `spectre/c2mos_ff1_func.scs` 读出 `parameters T=` / `parameters VDDV=`
以及 `Ck`/`Dd`/`Cq`/`Cqb` 各行属性，用 **Decimal 精确求值**（`0.35*T` 得 `7e-08`，不用二进制 float，
否则会把十进制意图污染成 `6.9999999999999992e-08`），格式化后还要 `%.9g` 回读必须相等，
不等就 `BUILD_REFUSE`。未识别的属性一律拒绝而不是静默丢弃（`vsource` 独有的 `type=pulse` 是唯一显式豁免项）。

| 源 | 参数（golden 表达式 → 数值） |
|---|---|
| `Vdd` | `dc=VDDV` → **1.8 V** |
| `Vss` | `dc=0` → **0 V，显式接地**（`Vss (vss 0)`，非注释掉的默认） |
| `Ck` | `val0=0 val1=1.8 period=T→2e-07 delay=0.5T→1e-07 width=0.5T→1e-07 rise=fall=1e-09` |
| `Dd` | `val0=0 val1=1.8 period=2T→4e-07 delay=0.35T→7e-08 width=T→2e-07 rise=fall=1e-09` |
| `Cq`/`Cqb` | `c=50e-15` |
| DUT | `X1 (d clk q qbar vdd vss)`，与 golden 端口顺序一致 |
| 分析 | `tran stop=4.8*T maxstep=1e-4*T`（由 `c2mos_check.sh` 按 T 渲染） |

数据序列 `1,0,1,0,1`、`q` 断言窗跨越输入跳变等设计意图全部沿用 golden，未自行改时序。

## 4. 仿真命令

```bash
cd /root/microled_ai_project
# 建 testbench cell（数值只从 golden 解析；--import 才写库，且 cell 已存在时直接拒绝）
python scripts/c2mos_tb_build.py --dry-run
python scripts/c2mos_tb_build.py --import
# DFF 功能验证（仓库冻结路径：preflight -> run_spectre -> psf_check）
bash scripts/c2mos_check.sh ff1_sch 2e-7 review1 2
```

## 5. waveform 结果（本轮 `review1` 运行，tag `ff1_sch`）

```
TESTBENCH_PREFLIGHT: PASS        （静态：vdd 1.8 参考到 0；vss 经独立源接到 0）
[1] assertions: total=33 failed=0
[2] assertions: total=33 failed=0
REPEAT: 2 runs produced byte-identical assertion reports
SCHEMATIC_DFF_FUNCTION: PASS
```

工作点首样：`vdd=1.8 vss=0 clk=0 d=0`，`q=qbar≈0.8108`（交叉耦合上电中点，断言窗避开建立期）。

| 窗口 (s) | 断言 | n | min | max |
|---|---|---|---|---|
| 1.4e-7 – 1.9e-7 | `q gt 1.7` | 2500 | 1.8 | 1.8 |
| | `qbar lt 0.1` | 2500 | 6.33148e-9 | 6.33179e-9 |
| 2.2e-7 – 2.9e-7 | `q gt 1.7` | 3507 | 1.79941 | 1.84122 |
| | `qbar lt 0.1` | 3507 | −3.64368e-4 | 2.83933e-4 |
| 3.4e-7 – 3.9e-7 | `q lt 0.1` | 2500 | 1.04325e-8 | 1.0996e-8 |
| | `qbar gt 1.7` | 2500 | 1.8 | 1.8 |
| 4.2e-7 – 4.9e-7 | `q lt 0.1` | 3508 | −0.0137425 | 0.0283385 |
| | `qbar gt 1.7` | 3508 | 1.79973 | 1.80097 |

（其余窗口同量级；`d` 过沿 `7.05e-8 / 2.715e-7 / 4.705e-7`，与 golden 一致。）

## 6. Q / Qbar 功能判断

1. **D 输入变化被正确采样**：上升沿序列采到 `1,0,1,0,1`，`q` 恰好延迟一个时钟周期跟随，同相（`d→m→q` 两级反相）。
2. **CLK 有效边沿采样**：只在上升沿改变；`clk` 低电平半周期内 `q` 全窗稳定（`n=2500` 逐点成立）。
3. **Q 输出**：高摆幅 1.8 V、低摆幅 ~1e-8 V。
4. **Qbar 互补**：与 `q` 严格反相，16 个窗无一例外 ⇒ 无单端失效。
5. **保持功能**：非有效半周期内 `q`/`qbar` 由 keeper（宽 0.25×）主动维持到轨，不是寄生电容暂存；
   且 `q` 断言窗跨越 `d` 的跳变点仍成立 ⇒ **无组合直通**。

## 7. 与 golden 验证结果的差异

| 对比 | 结果 |
|---|---|
| golden 网表 deck（`ff1`）vs 本机原理图重建（`ff1_sch`），tag `local1` | **断言报告逐字节相同**（commit `7307b26`，两份 repeat 都相同）⇒ 原理图与冻结网表波形级等价 |
| 本轮 `review1` 再跑 `ff1_sch` | 33 断言 0 失败、两遍一致，与 `local1` 同结论（同一套时间窗，仅 tag 不同） |
| **新建的 `c2mos_dff_tb` cell vs golden deck** | ~~**结构等价但数值不等价**~~ **（本行作废）**：拓扑/绑定/负载一致这一点成立；"激励参数未被 ASG 保存"不成立——按 analogLib 的正确参数名回读，20 项黄金数值 raw 与 CDF 两层全部等值（`reports/c2mos_tb_cdf_audit.md` §3） |

## 8. 需要你定（我没有自行修复）

> **本节整块已被后续只读审计推翻，保留原文以便追溯。** 更正见 `reports/c2mos_tb_cdf_audit.md`：
> 所谓"没有任何激励数值"来自按 Spectre 名字查询（`val0/period/...`），而 analogLib 的真名是
> `v1/per/...`；按真名实测，数值完整。仍然成立的观察只有一条：`cell 目录只有 schematic`（无 symbol view），
> 以及本节 §7 指出的缺 `tran/save` 分析设置。真正的待定项缩减为两条，见新报告 §10 的 T1/T2。

```
Problem: microled_cells/c2mos_dff_tb 里的 vdc/vpulse 实例没有任何激励数值，   <-- 已证伪
         因此这个 cell 无法作为可仿真的 testbench。
Evidence: TB-PROP 只有 model；TB-CDF 只有空 dc；对照 cap 的 c=5e-14 确实保住了。
          同一份 deck 里的 X1 六端子按名绑定全部成功，说明不是导入整体失败。
Possible reason: analogLib 的 vpulse/vdc 参数在本 build 的 ASG 路径下不落 OA 属性，
                 而 spiceIn 的 simName/outputSimName 也未给该 cell 生成 spectre 视图（cell 目录只有 schematic）；
                 具体是 ASG 配置项还是该 build 的能力边界，尚未定论。
Need confirmation:
  T1 认可"验证载体继续用文本 golden deck（ff1_sch 路径），OA tb cell 只作图形化表示"这一处置吗？
  T2 若要 cell 真能承载激励，可选：(a) GUI 里手工填 analogLib 源参数（人工操作，非脚本）；
     (b) 我用 sch2_fix_params 那套"按 CDF 名写属性"的办法给源实例补写参数并 dbSave —— 这是新的写操作，
         且要先把 `gnd!`→`0` 的问题一并解决，需你明确批准范围；
     (c) 放弃 OA tb cell，删除它（也是写操作）。
  T3 若继续 (b)，`terms=0` 与 `gnd!` 两项就绕不过去了 —— 它们目前在你的禁止清单里。
```
