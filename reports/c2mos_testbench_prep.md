# c2mos_testbench_prep.md — C²MOS testbench 准备信息（**只读整理**）

时间：2026-10-11 20:1x（guest `work-eda`）
性质：**只读**。本轮没有新建/修改任何 cell、symbol、网表、deck、配置或库文件；
没有跑任何仿真；没有 push。§4/§5 给出的连接方式是**仓库既有 deck 的原文摘录**，不是新方案。
表格由 `python scripts/report_build_c2mos_tb_prep.py` 从
`results/scan_c2mos_device_parameters.csv` 与本机回读日志渲染，数字未手抄。

被审对象：`microled_cells / c2mos_dff_1bit`（commit `afc7b10` 那轮生成，18/18 机检 PASS）。

---

## 1. `c2mos_dff_1bit` schematic 实例列表

本机回读（`skill/sch3_readback.il`，`dbOpenCellViewByType(...,"r")`）读到的 18 只 MOS：

| inst | master | model | l | w | fw | fingers | m | D | G | S | B |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `mn_c` | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | `clkb` | `clk` | `vss` | `vss` |
| `mn_k1` | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | `mb` | `m` | `vss` | `vss` |
| `mn_k2` | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | `m` | `mb` | `vss` | `vss` |
| `mn_k3` | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | `qbar` | `q` | `vss` | `vss` |
| `mn_k4` | smic18mmrf/n18:symbol | n18 | 200n | 500n | 500n | 1 | 1 | `q` | `qbar` | `vss` | `vss` |
| `mn_m1` | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | `x2` | `clkb` | `vss` | `vss` |
| `mn_m2` | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | `m` | `d` | `x2` | `vss` |
| `mn_s1` | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | `y2` | `clk` | `vss` | `vss` |
| `mn_s2` | smic18mmrf/n18:symbol | n18 | 200n | 2u | 2u | 1 | 1 | `q` | `m` | `y2` | `vss` |
| `mp_c` | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | `clkb` | `clk` | `vdd` | `vdd` |
| `mp_k1` | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | `mb` | `m` | `vdd` | `vdd` |
| `mp_k2` | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | `m` | `mb` | `vdd` | `vdd` |
| `mp_k3` | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | `qbar` | `q` | `vdd` | `vdd` |
| `mp_k4` | smic18mmrf/p18:symbol | p18 | 200n | 1u | 1u | 1 | 1 | `q` | `qbar` | `vdd` | `vdd` |
| `mp_m1` | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | `x1` | `clk` | `vdd` | `vdd` |
| `mp_m2` | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | `m` | `d` | `x1` | `vdd` |
| `mp_s1` | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | `y1` | `clkb` | `vdd` | `vdd` |
| `mp_s2` | smic18mmrf/p18:symbol | p18 | 200n | 4u | 4u | 1 | 1 | `q` | `m` | `y1` | `vdd` |

分类：**n18×9 + p18×9**（共 18 只），`verdict` 全 PASS 18/18。
全部 `l` 同一值（黄金 `ln`），`w` 只有四种取值，对应时钟管 / 传输管 / keeper 三档宽度：

- `w=500n` ×4：`mn_k1`, `mn_k2`, `mn_k3`, `mn_k4`
- `w=1u` ×4：`mp_k1`, `mp_k2`, `mp_k3`, `mp_k4`
- `w=2u` ×5：`mn_c`, `mn_m1`, `mn_m2`, `mn_s1`, `mn_s2`
- `w=4u` ×5：`mp_c`, `mp_m1`, `mp_m2`, `mp_s1`, `mp_s2`

单元内网络共 13 条：`clk` `clkb` `d` `m` `mb` `q` `qbar` `vdd` `vss` `x1` `x2` `y1` `y2`。其中**带 pin 的只有 6 条**（即 testbench 需要驱动的端口），其余 7 条是内部节点。
## 2. 电源端 `vdd` / `vss`

`vdd` / `vss` 在 OA 数据库里的真实连接（按端子统计）：

- **`vdd`**：端子级连接 **16** 个（p18×16）
- **`vss`**：端子级连接 **16** 个（n18×16）

要点（决定 testbench 能接几个电源脚）：

- 9 只 `p18` 的 **bulk 全部接 `vdd`**、9 只 `n18` 的 **bulk 全部接 `vss`**（上表 B 列可见），所以衬偏是固定接法，**没有独立的 bulk 端口**。
- 单元只有 6 个外部端子，`vdd`/`vss` 各一个；带 `S=vdd`/`B=vdd` 之外，`mp_m1`(S=`x1`)、`mp_s1`(S=`y1`) 的 source 是内部堆叠节点，`mn_m1`(S=`x2`)、`mn_s1`(S=`y2`) 同理，说明上下拉是堆叠结构而非直接并到轨。
- 因为 `vss` 只出现在 source/bulk 上，**testbench 不显式接地就会整片失效**，见 §5.3 第 1 条。
## 3. 输入端 `d` / `clk`

`clk` 直接驱动 **4** 只管子的栅极：`mn_c`, `mn_s1`, `mp_c`, `mp_m1`。
其余时钟激励来自内部反相：`clkb` 由 `mn_c`/`mp_c` 这一对反相器产生（`mn_c` 的 D=`clkb`、G=`clk`，`mp_c` 同理），所以 **testbench 只允许给一个时钟**，外部再加第二相位于是错的。

`d` 只进入 master 的数据管栅极：**2** 只（`mn_m2`, `mp_m2`）；另有 `mn_k*`/`mp_k*` 交叉耦合对是 keeper，不接 `d`。
## 4. 输出端 `q` / `qbar`

`q` / `qbar` 的连接形态：
- `q`：作为 drain 出现于 `mn_k4`, `mn_s2`, `mp_k4`, `mp_s2`；作为栅极出现于 `G`=mn_k3, `G`=mp_k3；作为 source 出现于 -
- `qbar`：作为 drain 出现于 `mn_k3`, `mp_k3`；作为栅极出现于 `G`=mn_k4, `G`=mp_k4；作为 source 出现于 -
- ⇒ `q`/`qbar` 互为存储节点的交叉耦合对，两者都要接负载；仓库基准 deck 给的是 **各 50 fF**（`Cq`/`Cqb`），且 `save clk d q qbar`。
- `q` 相对 `d` 是同相、延迟一个时钟沿（两级反相：`d→m→q`）；上升沿触发（`clk=0` master 求值、`clk=1` slave 求值），这是 `C2MOS_DFF.scs` 头注释里明示的内部时钟极性，不是我推断的。
## 5. 推荐 Spectre testbench 连接方式

**结论：走网表路线，不走 ADE 直连 OA cell 的路线。** 两个理由都是实测/已记录的：

1. 本机 `c2mos_dff_1bit` 的 `terms=0`（OA 里没有端口对象，端口只是命名 net），
   而任务书禁止修改 schematic ⇒ ADE 无法把 testbench 绑到管脚上。
   仓库对这一状态的历史判定是 `PORT_DIRECTIONS_OA: UNREADABLE_IN_BATCH`。
2. 从 OA 侧生成可仿网表的既有路径是 `scripts/sch2_netlist_from_readback.py`
   （由 `skill/sch2_readback.il` 的 DB 回读行重建），
   而 Cadence 自己的 ADE netlister 在本 build 的批量会话里不存在
   （`asiNetlist/nlNetlist/nlCreateDesign` 只在 `-restore` 路径下出现，
   仓库结论 `NATIVE_CADENCE_NETLIST: BLOCKED`）。

### 5.1 两个被测对象，各自的 token 与含义（不要混用）

| 被测 | 来源 | deck | token |
|---|---|---|---|
| `c2mos_dff`（**黄金网表本体**） | `include "C2MOS_DFF.scs"` | `spectre/c2mos_ff1_func.scs` | `C2MOS_DFF_1CH` |
| `c2mos_dff_1bit`（**本机 OA 库重建**） | `include "generated/c2mos_dff_1bit_from_oa_readback.scs"` | `spectre/c2mos_ff1_from_oa_readback.scs` | `SCHEMATIC_DFF_FUNCTION` |

⚠ 树上现有的 `spectre/generated/c2mos_dff_1bit_from_oa_readback.scs` 头部自述其输入是
`logs/sch1/rb_c2mos_dff_1bit_paramfix.log`，即**旧机器**那次回读的产物。
要代表**本机**这个 cell，必须用本机回读日志重新生成：

```
python scripts/sch2_netlist_from_readback.py <本机的 readback.log> c2mos_dff_1bit <out.scs>
```

并且在报告里必须写清该网表的性质：**它是我自己的 DB 读取器重建的，不是 ADE netlister 的产物**
（`reports/shift_unit_status.md` 的原话：导出器不满足"必须是 ADE netlist 产物"这一条时应判
`SCHEMATIC_NETLIST_VERIFICATION: BLOCKED`）。也就是说第二个 token 证明的是
"OA 数据库里携带的参数是对的"，**不等于** "ADE 会网表出同样的东西"。

### 5.2 推荐的连接形态（原文来自 `spectre/c2mos_ff1_func.scs`）

```sp
simulator lang=spectre insensitive=yes
include "${QODER_PDK_LIB}" section=tt
include "C2MOS_DFF.scs"                 ; 或 generated/c2mos_dff_1bit_from_oa_readback.scs

parameters T=2e-7
parameters VDDV=1.8

Vdd (vdd 0) vsource dc=VDDV
Vss (vss 0) vsource dc=0                ; 见 5.3 第 1 条，绝不可省
Ck  (clk 0) vsource type=pulse val0=0 val1=VDDV period=T     delay=0.5*T width=0.5*T rise=1e-9 fall=1e-9
Dd  (d   0) vsource type=pulse val0=0 val1=VDDV period=2*T   delay=0.35*T width=T   rise=1e-9 fall=1e-9
X1  (d clk q qbar vdd vss) c2mos_dff    ; 端口顺序即 subckt 头，6 端，无 reset
Cq  (q    0) capacitor c=50e-15
Cqb (qbar 0) capacitor c=50e-15
tr1 tran stop=4.8*T maxstep=1e-4*T
save clk d q qbar
```

要点：

- **一个时钟**。单元内部用 `mn_c/mp_c` 自反相产生 `clkb`，
  testbench 里再加第二个相位源是错的（deck 注释原话 "ONE external clock"）。
- `T=2e-7`（200 ns）是 **stress 时钟**，比应用列周期 `9.765625 µs`（=1/(1024×100 Hz)）快约 49 倍；
  这个数值是 testbench 假设，**不是课程要求**，报告里不得当作单元参数。
- 数据序列设计成 `1,0,1,0,1`（不是单个 '1'），每次 `d` 跳变落在捕获沿前 `0.15T`、
  上一跳后 `0.35T`，即落在 master 透明相位中部；`q` 断言窗口**跨越**输入跳变点，
  因此通过同时证明" inactive 相位保持"与"无组合直通"。
- 单元内**没有** reset、脉冲发生器、输出级 —— 不要为它补激励（`spec/system_requirements.md` 的
  Micro LED Vf/输出域仍是 `NOT DEFINED`）。
- 50 fF 负载是**占位**，真实扫描负载属于未定义域。

### 5.3 四条硬性前置（都是踩过的坑，违反即结果无效）

| # | 规则 | 出处 |
|---|---|---|
| 1 | **`vss` 必须显式接地** `Vss (vss 0) vsource dc=0`。`vss` 只接触 source/bulk，不接就是一颗浮空网络：所有 NMOS 无电流路径、节点被时钟交叠泵到 VDD 以上（实测 x2→2.18 V、y2→2.35 V），Spectre 仍报 0 error 0 warning | `AGENTS.md` 19；`spectre/nmos_probe.scs` |
| 2 | **先跑 preflight 再跑 transient**：`scripts/tb_preflight.sh <netlist> [VDD_EXP=1.8] [tag]` 结构+工作点门禁，不过就不许正式仿真（`c2mos_check.sh` 已内置，FAIL 时打印 token + `preflight` 日志名） | `scripts/tb_preflight.sh` 头 |
| 3 | **pulse 时间轴是 `delay → rise → width → fall`**，高电平平台从上升沿**结束后**才计时 ⇒ 想让数据在 `T0` 翻转必须写 `width = T0 - delay - rise`。第一轮 setup/hold 扫描就是这样测偏一个 rise time 的 | `AGENTS.md` 20；`scripts/c2mos_margin.sh` |
| 4 | **过沿检测必须相邻两点 + 线性插值**，不能取"第一个越过阈值的采样点"；判据 `v_prev<=VTH && v_now>VTH`，找不到必须显式 `NOT FOUND`，不许回退到最后一个采样点。checker 自身用合成波形测（`python scripts/test_psf_check.py`，9 例） | `AGENTS.md` 21 |

其它与器件相关的既有约束（照抄，勿改）：Spectre MOS 端序 `Name ( d g s b )`，衬极在最后（`AGENTS.md` 17）；
模型卡用老师这份 `ms018_enhanced_v1p2_rev0_spe.lib` 的 `section=`，**corner 名一律从库里的 `section`
语句读出来，不许猜**（`scripts/pvt_probe.sh` 的规则）；
本 build 的 spectre 不接受 `-log/-raw`，输出即 `<netlist>.log` + `<netlist>.raw/`，
`-format psfascii` 后要从 `.raw/` 里挑同时含 `TRACE` 与 `VALUE` 的文件、跳过 `logFile`（`AGENTS.md` 12）。

## 6. `scripts/c2mos_check.sh` 的位置与运行条件

位置：`$PROJ/scripts/c2mos_check.sh`，本机 `PROJ=/root/microled_ai_project`（已实测存在）。

```bash
bash scripts/c2mos_check.sh <ff1|shift3|ff1_sch|shift3_sch> [clockPeriodSeconds] [tag] [repeat]
```

模式与 token（脚本 `case` 分支原文）：`ff1`→`C2MOS_DFF_1CH`、`shift3`→`C2MOS_SHIFT_3STAGE`、`ff1_sch`→`SCHEMATIC_DFF_FUNCTION`、`shift3_sch`→`SCHEMATIC_SHIFT3_FUNCTION`；失败打印同名 `: FAIL`。

运行条件（本轮逐条实测，路径存在性为 guest 内 `test -e`）：

- `scripts/run_spectre.sh`：PRESENT（护栏：netlist 必须在 `$PROJ` 下，否则 `REFUSED`）
- `scripts/psf_check.awk`：PRESENT（断言求值器，被 `c2mos_check.sh` 以 `-f` 调用）
- `scripts/tb_preflight.sh`：PRESENT（`c2mos_check.sh` 在正式 transient 前强制调用）
- `spectre/C2MOS_DFF.scs`：PRESENT（黄金单元本体，只读被 include）
- `spectre/c2mos_ff1_func.scs`：PRESENT（`ff1` 模板；`parameters T=` 行由驱动脚本按第 2 参数重写）
- `spectre/c2mos_shift3.scs`：PRESENT
- `spectre/c2mos_ff1_from_oa_readback.scs`：PRESENT（`ff1_sch` 模板）
- `spectre/generated/c2mos_dff_1bit_from_oa_readback.scs`：PRESENT，但其头部自述输入是旧机日志 `logs/sch1/rb_c2mos_dff_1bit_paramfix.log` ⇒ 代表本机需重生成
- **`spectre/pdk_local.env`**：**ABSENT** ⇒ `run_spectre.sh` 会 `REFUSED: ... needs environment variable(s)`；必须先由 `spectre/pdk_local.env.example` 复制并填 `QODER_PDK_LIB`
- `spectre/pdk_local.env.example`：PRESENT（模板，路径值需按本机填）
- 模型卡：`/root/tech/teacher_pdk/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib`，353,783 B，存在
- `spectre` 可执行：只有在 `. skill/cad_env.sh` 之后才在 PATH 上：`/opt/MMSIM151/tools/bin/spectre`
- `$PROJ/logs`：当前不存在，但 `c2mos_check.sh` 第 43 行 `mkdir -p` 自建（无需批准）
- 环境变量旋钮：`PDK_ENV`（默认 `$PROJ/spectre/pdk_local.env`）、`SECTION`（corner，脚本改 `section=` 行）、`VDD_EXP`（preflight 期望值，默认 1.8）、`TMO`、`SPECTRE_EXTRA`、`PROJ`
- Virtuoso 进程：0（批处理会话与仿真不冲突；跑 ADE 类 GUI 才需要 `:0`）
- 磁盘：`/` 剩 5.2 G / 50 G（90% 已用）——`sim/` 与 `.raw/` 会落盘，跑前三级链建议先看体积

与旧机对照的可复现调用（`reports/c2mos_validation_report.md` 里记录的原样命令行）：

```
bash scripts/c2mos_check.sh ff1 2e-7 rev1 2
bash scripts/c2mos_check.sh shift3 9.765625e-6 revnom 1
bash scripts/c2mos_margin.sh setup|hold 1e-9|5e-11
bash scripts/pvt_probe.sh 2e-7
bash scripts/tb_preflight.sh <abs.netlist> 1.8 <tag>
```

`repeat` 的用意是同一 testbench 跑两遍并逐字节比对断言输出，旧机据此判 `byte-identical`；本机复跑时应保留同样的两遍一致性检查，否则一次偶然的收敛差异会被当成结论。
## 7. 本轮未做（按要求禁止）

未搭 testbench、未跑仿真、未新建/修改 cell 与 symbol、未做 hierarchy/layout/DRC/LVS、未 push。
本机 `c2mos_dff_1bit` 的**功能级验证从未在本机跑过** —— 上一轮报告里引用的
`C2MOS_DFF_1CH: PASS` / `C2MOS_SHIFT_3STAGE: PASS` 是**旧机器的仓库既有结论**，不可当作本机结果。

## 8. 等人工确认的开放项

1. 被测对象选哪个：黄金网表 `c2mos_dff`（token `C2MOS_DFF_1CH`）、
   本机 OA 重建 `c2mos_dff_1bit`（token `SCHEMATIC_DFF_FUNCTION`）、还是两者都跑并对比；
2. 若选 OA 重建：是否批准我用**本机**回读日志执行
   `sch2_netlist_from_readback.py` 生成新的 `spectre/generated/...`（会写 `spectre/generated/`，
   不改 schematic），以及新文件叫什么名字以免覆盖旧机的同名件；
3. 时钟周期与负载取 stress(200 ns/50 fF) 还是应用列周期(9.765625 µs) 还是两者；
4. `spectre/pdk_local.env` 是否批准创建（当前 ABSENT，任何仿真都会被 `run_spectre.sh` 拒绝）；
5. 单管还是三级链（`shift3` 用 `spectre/c2mos_shift3.scs`，token `C2MOS_SHIFT_3STAGE`）。

