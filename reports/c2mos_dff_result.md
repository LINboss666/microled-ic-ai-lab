# C²MOS 单相主从 DFF —— 1 路扫描移位最小单元 POC（通过）

日期 2026-10-04。工艺/模型：老师交付副本 `smic18mmrf_teacher`
（`models/spectre/ms018_enhanced_v1p2_rev0_spe.lib`，`section=tt`），只用 1.8 V 核心器件 `n18/p18`。
工具链：`spectre 15.1.0.284.isr1 -64 -format psfascii`，经 `scripts/run_spectre.sh` + `scripts/psf_check.awk` 断言。

## 结果

两个 PASS token 都拿到了：

| 项 | 判据数 | 结果 | 证据 |
|---|---|---|---|
| `C2MOS_DFF_1CH`（单级 DFF） | 29 | **PASS**，failed=0 | `logs/c2mos_assert_ff1_fast_1.txt` |
| 同上的重复运行 | 29 | **PASS**，两次断言报告逐字节相同 | `cmp` run1 vs run2 → `REPEAT: 2 runs produced byte-identical assertion reports` |
| `C2MOS_SHIFT_3STAGE`（3 级链，T=200 ns） | 40 | **PASS**，failed=0 | `logs/c2mos_assert_shift3_fast_1.txt` |
| 同上的重复运行 | 40 | **PASS**，逐字节相同 | 同上 |
| 同上的应用速率复跑（T=9.765625 µs = 100 Hz 列周期） | 40 | **PASS**，failed=0 | `logs/c2mos_assert_shift3_nominal_1.txt` |
| 相位级探针 `c2mos_diag.scs` | — | `m=!d`（clk=0）、`q=!m=d`（clk=1）、主锁存在 clk=1 时冻结 | `spectre/sim/c2mos_diag.raw/` |

没有采用第三种触发器风格，也没有加复位、脉冲发生器或输出级 —— 按你的指示执行。

## 单元结构（`spectre/C2MOS_DFF.scs`，18 MOS = 内部时钟反相器 2 + 主级堆叠 4 + 主级 keeper 4 + 从级堆叠 4 + 从级 keeper 4）

计数不手抄：`python scripts/netlist_stats.py` 从 netlist 解析出 NMOS=9 / PMOS=9 / 合计 18，并核对全仓库所有"N 管 / N MOS / N transistors"断言。

外部只有 `d clk` 两个信号，`clkb` 由单元内部反相器产生。**内部时钟极性明确记录**：
`clkb = !clk`；clk=0 时主锁存透明、从锁存保持；clk=1 时主锁存保持、从锁存透明 → 上升沿触发，`D→Q` 同相（两级反相）。

器件端序一律 `Name ( d g s b ) ModelName`（衬极在最后，AGENTS.md 第 17 条）。

| 管 | 型号 | D | G | S | B | 作用 |
|---|---|---|---|---|---|---|
| `mn_c` / `mp_c` | n18 / p18 | clkb | clk | vss / vdd | vss / vdd | 内部时钟反相 |
| `mp_m1` | p18 | x1 | **clk** | vdd | vdd | 主上拉堆叠·时钟管（靠电源侧） |
| `mp_m2` | p18 | m | **d** | x1 | vdd | 主上拉堆叠·数据管 |
| `mn_m1` | n18 | x2 | **clkb** | vss | vss | 主下拉堆叠·时钟管（靠地侧） |
| `mn_m2` | n18 | m | **d** | x2 | vss | 主下拉堆叠·数据管 |
| `mn_k1`/`mp_k1` | n18/p18 | mb | m | vss/vdd | vss/vdd | 主 keeper 反相器 m→mb |
| `mn_k2`/`mp_k2` | n18/p18 | m | mb | vss/vdd | vss/vdd | 主 keeper 反相器 mb→m |
| `mp_s1` | p18 | y1 | **clkb** | vdd | vdd | 从上拉堆叠·时钟管 |
| `mp_s2` | p18 | q | **m** | y1 | vdd | 从上拉堆叠·数据管 |
| `mn_s1` | n18 | y2 | **clk** | vss | vss | 从下拉堆叠·时钟管 |
| `mn_s2` | n18 | q | **m** | y2 | vss | 从下拉堆叠·数据管 |
| `mn_k3`/`mp_k3` | n18/p18 | qbar | q | vss/vdd | vss/vdd | 从 keeper q→qbar |
| `mn_k4`/`mp_k4` | n18/p18 | q | qbar | vss/vdd | vss/vdd | 从 keeper qbar→q |

关键点：每一对堆叠里的时钟管接**相反相位**（主管 PMOS 用 clk、NMOS 用 clkb；从管镜像）。

| 相位 | 主锁存 | 从锁存 | 是否存在对 keeper 的轨到轨冲突 |
|---|---|---|---|
| clk=0（clkb=1） | 两条堆叠都导通 → `m=!d` | `mp_s1`(gate=1) 断、`mn_s1`(gate=0) 断 → 与两条轨都断开 | 无。`d` 在此相位任意翻转都不影响 `q` |
| clk=1（clkb=0） | `mp_m1`(gate=1) 断、`mn_m1`(gate=0) 断 → 与两条轨都断开 | 两条堆叠都导通 → `q=!m=d` | 无。`d` 在此相位翻转也碰不到 `m`，只碰到已断开的堆叠里的栅极 |

尺寸：时钟路径 `wc=2 µm / wcp=4 µm`，keeper `wk=0.5 µm / wkp=1 µm`（0.25×），`l=0.2 µm` 全部。
已实测：在 tt / 1.8 V / 27 °C / 50 fF 这些条件下，写入由时钟路径赢、保持由 keeper 主动补荷（fully static），保持窗口内 min 1.8000 V、无跌落。电压、温度、工艺偏差、mismatch、Monte Carlo 均未运行，所以这不是"总能写入 / 全角保证"。

## 验证内容与判据

测试图形全部以时钟周期 T 的倍数表达，由 `scripts/c2mos_check.sh` 换算，所以 200 ns 应力时钟和
9.765625 µs 应用时钟共用同一套逻辑判据。每个周期取两个窗口：
早窗 `[+0.20T, +0.45T]`（clk 高、透明相位）与晚窗 `[+0.60T, +0.95T]`（clk 低、保持相位），
且 `d` 的跳变刻意落在晚窗内部 —— 一次通过同时证明"保持"和"无组合直通"。

单级（输入序列 1,0,1,0,1，不是单个 1）：

| 判据 | 窗口（T 的倍数） | 结果 |
|---|---|---|
| q 全摆幅高 `>1.7 V` | 0.70–0.95, 1.10–1.45, 2.70–2.95, 3.10–3.45 | 全部 OK（min 实测 1.8000） |
| q 全摆幅低 `<0.1 V` | 1.70–1.95, 2.10–2.45, 3.70–3.95, 4.10–4.45 | 全部 OK（max 实测 0.0000） |
| qbar 为反相存储节点 | 上述窗口的互补组合，8 个窗口 | 全部 OK |
| 输入确实交替翻转（4 次跨 0.9 V） | — | 全部 OK |

3 级链（`DIN → FF0 → FF1 → FF2`，三级完全相同的 cell 实例，单时钟）：期望表按移位语义先写死再仿真 ——

| 周期起点 | q0 | q1 | q2 | 含义 |
|---|---|---|---|---|
| 3.5T | 1 | 0 | 0 | '1' 只进了 FF0 |
| 4.5T | 0 | 1 | 0 | 每沿只前移一级；**FF2 不得同沿穿透** |
| 5.5T | 1 | 0 | 1 | |
| 6.5T | 0 | 1 | 0 | '0' 也前移一级 |
| 7.5T | 1 | 0 | 1 | |

30 个电平窗口 + 3 个 qbar 窗口 + 穿透专项窗口 `q2∈[3.55T,4.45T] < 0.1 V` 全部 OK（40/40）。

clk→Q 延迟（50% 跨点差，始终相对**捕获它的那个上升沿**测量）：

| 测量 | T=200 ns | T=9.765625 µs（应用速率） |
|---|---|---|
| 单级 上升 | 0.3974 ns（0.199 % T） | — |
| 单级 下降 | 0.1867 / 0.1783 ns | — |
| 链 FF0 / FF1 / FF2 上升 | 0.4123 / 0.4215 / 0.3947 ns | 0.4317 / 0.4506 / 0.4067 ns |

绝对延迟几乎不随周期变化（0.41 → 0.43 ns，差别来自打印分辨率与步长），符合"延迟由器件与负载决定"
的预期；相对占用从 0.21 % T 降到 0.0044 % T，说明 100 Hz 列周期下时序余量不是瓶颈。

## 建立/保持时间初步扫描（`scripts/c2mos_margin.sh`）

13 个 margin 各配一个独立 cell 实例与独立数据源、共享同一时钟，一次仿真扫完（13 实例、35 k 点）。
被测沿取第 3 个上升沿（2.5T），前两个沿只用来把从锁存置成确定状态（单元无复位，上电时 keeper 双稳态
的直流解未定义，这是仿真初值问题，不是靠加复位解决的）。

> **本节结论已被 `reports/c2mos_validation_report.md` 取代**（第一轮独立 review 之后）。
> 原因有两条：当时 margin 是按**电压源的 delay 旋钮**读成 setup/hold 的，而旋钮值不等于
> 阈值到阈值的裕量；并且当时的 `CROSS/FALL` 判据是"第一个越过阈值的采样点"，不是过沿检测。
> 下面保留原文，是为了让审核方看到结论是怎么被修正的，不代表当前状态。

建立时间（`d` 在 2.5T−margin 上升）：

| margin | 20 / 10 / 5 / 3 / 2 / 1.5 / 1 / 0.7 / 0.4 / 0.2 ns | 0 / −0.4 / −1.0 ns |
|---|---|---|
| q 在 [2.7T, 2.95T] | 1.8000 V → CAPTURED | ≈1.07e−8 V → REJECTED |

修正后的实测说法（阈值到阈值，VTH=0.5·VDD）：`setup_margin = t_CLK50 − t_D50`，
1 ns 与 50 ps 两组边沿都给出同一夹逼 **捕获 ≥ +0.200 ns、拒绝 ≤ 0.000 ns**，
即当前夹逼宽度就是扫描步进 0.2 ns。

保持时间：原报告写的"实测 t_hold ≈ 0 ns"**证据不足，已撤回**。正确表述是
**HOLD BOUNDARY NOT FOUND IN CURRENT SWEEP**，以及 no functional hold failure observed
down to the tested source-delay margin = −1 ns；进一步用 50 ps 边沿重测才把边界夹到
**≥ 0.000 ns 保持、≤ −0.400 ns 失败**之间。两组结果不一致本身就说明源边沿速率在主导观测值
（本仿真器的 pulse 时序是 `delay → rise → width`，1 ns 那组的数据下降沿实际比旋钮值晚约一个
rise time，从未进入保持临界区）。因此 **`HOLD_CHARACTERIZED: NO`**，本轮不产出任何
setup/hold 规格；数据在 `results/margin_*_s{1e-9,5e-11}.csv` 与 `results/summary.json`。

## 本轮挖出的真根因（推翻了上一轮的失败归因）

`vss` 这类只连接源极与衬极的网络必须显式接地。之前所有 testbench 都只有
`Vdd (vdd 0) vsource dc=1.8`，`vss` 从未与 `0` 相连 → 浮空 → 全部 NMOS 无电流路径、
恒等关断，节点被结漏电和时钟交叠电容泵到 VDD 以上（实测 2.18 / 2.35 V），`gmin` 被求解器降到 10 fS，
而 Spectre **不报任何错误或警告**。指纹是"`>1.7 V` 断言全过、`<0.1 V` 断言全挂、输出恒定 ≈1.8 V"。

判据文件 `spectre/nmos_probe.scs`：同一个 `n18` 的三种写法（顶层字面值、subckt+`parameters`、
subckt+字面值）在不接地时曲线完全一致且都不导通；加 `Vss (vss 0) vsource dc=0` 后三者一致正常
（g=1.8 → 0.758 V 分压）。这同时**证伪**了我中途猜的"顶层 `parameters` 在 subckt 内不可见"。

因此 `reports/shift_unit_status.md` 里"互补两相 TG 锁存链存在 keeper/写入强度冲突、无法用调宽解决"
的结论已作废（那条 TG 链从未在正确接地下跑过），AGENTS.md 第 18 条同步作废、新增第 19 条记录本坑。
C²MOS 通过只说明这条路线可用，**不说明 TG 路线不可行**。

## TESTBENCH ASSUMPTIONS（都不是课程给定的，也不外推为规格）

- `T = 200 ns` 应力时钟；应用列周期是 9.765625 µs（由拓扑派生 1/(1024×100 Hz)），另跑了一遍 40/40 通过。
- `Cload = 50 fF` 挂在每个 `q`/`qbar` 上，作为"下一级栅负载"的占位值；真实列电极负载依赖 NOT DEFINED 的输出域。
- 源边沿 1 ns；无噪声、无 PVT  corner（只 `tt`、27 °C 默认）。
- 断言阈值 1.7 V / 0.1 V 是本 POC 的摆幅判据，不是产品规范。
- 前两个时钟沿用于给从锁存确定初值（无复位单元的上电态由直流解决定，不指定）。

仍然冻结、未做任何设计或声明：扫描功率输出级、VLED、Micro LED Vf、输出电压域（1.8 V / 3.3 V 只是候选，
未写成规格）。异步复位未添加 —— 按约定，两个 token 都 PASS 之后才来问你这个决定。

## 文件

Windows 镜像 `D:\ic617_agent_bridge\`，guest 侧 `/root/microled_ai_project\` 同名相对路径。

| 文件 | 作用 |
|---|---|
| `spectre/C2MOS_DFF.scs` | 单元（18 MOS，无复位/无脉冲/无输出级） |
| `spectre/c2mos_ff1_func.scs` | 单级功能 testbench |
| `spectre/c2mos_shift3.scs` | 3 级链 testbench |
| `spectre/c2mos_diag.scs` | 相位级探针（两个实例：d=0 与 d=1.8） |
| `spectre/nmos_probe.scs` | 接地根因判据 |
| `scripts/c2mos_check.sh` | 渲染 T → 跑 Spectre → 建断言表 → 出 token；`repeat>1` 做逐字节一致性比对 |
| `scripts/c2mos_margin.sh` | 建立/保持扫描（一次仿真 13 实例），输出边界夹逼 |
| `scripts/psf_check.awk` | 新增 `CROSS/FALL <sig> <v> <t0>`：按沿配对测量，才能测逐级 clk→Q |
| `scripts/psf_dump.awk` | 波形采样表（`from/to`、`want=`），调试时用来看内部节点而不是猜 |
| `scripts/sync2guest.sh` | 宿主机→guest 安装并统一转 LF（CRLF 会让 bash/awk 静默改行为） |
| `logs/c2mos_assert_*`、`spectre/sim/*` | 断言原文与 log/raw，证据都在这里 |

## 安全边界（本轮）

未创建/修改任何 Cadence library、cell、schematic、layout；未改 PDK、`cds.lib`、techfile、模型卡；
未做 VM 电源/快照/`.vmx`/license 操作；未改 `/etc` 与 Windows 全局 SSH 设置。
所有新文件都在 `/root/microled_ai_project/`（及其 `spectre/sim/`、`logs/`）与 Windows 镜像目录内；
`run_spectre.sh` 的"netlist 必须在 $PROJ 下"护栏全程生效；密码只存在于
`D:\ic617_agent_bridge\.ic617_agent_bridge_credentials`，未进入任何日志、报告或 Git。
`sync2guest.sh` 的目的路径被强制约束在 `$PROJ` 之下，写不到 PDK。
