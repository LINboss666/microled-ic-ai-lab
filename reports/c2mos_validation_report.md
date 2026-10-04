# C²MOS 移位单元 —— 验证状态报告（第一轮独立 review 之后）

日期 2026-10-05。分支 `poc/c2mos-dff`。电路 topology **本轮未改**，改的是验证体系与文档。
所有数值都来自仓库内的机器生成文件，出处在每节末尾。

## 状态（两个层面必须分开，不许混）

```
FUNCTIONAL VALIDATION
  C2MOS_DFF_1CH          : PASS   33 断言，两次运行逐字节一致
  C2MOS_SHIFT_3STAGE     : PASS   40 断言 @T=200 ns 两次一致；@T=9.765625 us（应用列周期）亦 40/40
  三工艺角 corner 探针    : PASS   tt / ss / ff 各 40/40，同一沿不穿透多级
  TESTBENCH_PREFLIGHT    : PASS   （并有负样本 fixture 证明它能 FAIL）
  CROSSING_CHECKER_UNIT_TEST : PASS  9 合成用例
  DEVICE_COUNT_CHECK     : 由 netlist 生成，报告文本与之核对
  SOURCE_PROVENANCE_CHECK: 见 provenance 节

TIMING CHARACTERIZATION
  TIMING CHARACTERIZATION COMPLETE : NO
  HOLD_CHARACTERIZED               : NO
  FUNCTIONAL PASS 只证明"在 tt/1.8 V/27 C/50 fF/两种边沿下，每沿前进一级且不误触发"，
  不构成 DFF 已被表征。
```

## 1. 器件计数（A1）

计数由 `scripts/netlist_stats.py` 解析 `spectre/C2MOS_DFF.scs` 得到，不在文档里手抄：

```
TOTAL MOS = 18   (NMOS = 9, PMOS = 9)   models = {n18: 9, p18: 9}
internal clock inverter   2
master clocked stage      4
master keeper             4
slave clocked stage       4
slave keeper              4
```

上一版报告写的是"20 管 + 时钟反相器 2 管"和"22 管"，两处都与源码不符 —— 独立 review 的  <!-- check:skip 引用被废除的说法，正是在说明它被废除 -->
18 是对的。现在 `netlist_stats.py` 会扫全部报告里的 `N 管 / N MOS / N transistors` 断言并
与解析值比对，不一致直接 `DEVICE_COUNT_CHECK: FAIL`（这条自检本身就先抓到了我写错的两句）。
证据：`results/`（无，此项是静态解析）+ `python scripts/netlist_stats.py` 输出。

## 2. checker 修复与自检（A2/A3）

`psf_check.awk` 的 `CROSS/FALL` 原来是"第一个 >阈值 / <阈值 的采样点"，不是过沿检测。现在：

- 上升沿要求相邻两点满足 `v_prev <= VTH` 且 `v_now > VTH`，下降沿反之；
- 交点线性插值 `t = t_prev + (VTH − v_prev)/(v_now − v_prev)·(t_now − t_prev)`；
- `t0` 只限定"从何时开始接受过沿"，信号在 `t0` 已经为高不会被当成 `t0` 处的上升沿；
- 找不到时显式 `not-found`（绝不返回最后一个采样点），并附 `edges=` 计数便于核对。

checker 本身用**合成波形**测试，不拿 C²MOS 电路自证：`scripts/test_psf_check.py` 九例
（t0 前已为高、标准上升、标准下降、多次过沿只取 t0 后第一根、两点之间过沿的插值数值、
无过沿必须 NOT FOUND、样本正好落在阈值上、斜坡正好踩在阈值样本上、ASSERT 违例计数仍生效）
→ 输出 `results/checker_unit_test.txt`，全部 PASS。

## 3. testbench preflight（A8）

新增 `scripts/tb_preflight.sh`，在任何正式 transient 之前跑（`c2mos_check.sh`、
`c2mos_margin.sh` 已内建，FAIL 即拒绝仿真）：

- 静态相位：解析 testbench 与它 `include` 的 subckt，把实例端口按位置对上 subckt 端口名，
  要求每个 `vdd` 网络有到参考点 0 的独立源且电压等于预期值；每个 `vss` 网络**必须是 0 或由
  独立源等电位接到 0**。
- 仿真相位：自动生成 1.5 ns 的 op 探针网表（`save` 所有互联网络 + 每个实例的内部节点层次名），
  检查 t=0 时 vdd=预期、vss=0，并对任何高于 VDD / 低于参考的点报 `RAIL_OVERSHOOT_WARNING`
  （报告但不判死）。

三向验证（`results/preflight/`）：正常 TB → PASS；把预期 VDD 改成 3.3 V → `STATIC_FAIL` +
`OP_FAIL`；负样本 `spectre/preflight_negative_vss_float.scs`（故意不接 `vss`）→
`STATIC_FAIL vss net vss is NOT tied to reference node 0` 与 `OP_FAIL vss = 1.798`。
这个负样本正是当年 TG 实验的真实缺陷，如今会被自动拦下。

## 4. 时间测量改为"阈值到阈值"（A4/A5）

`scripts/c2mos_margin.sh` 现在每个点都从波形取 `t_D50`、`t_CLK50`、`t_Q50`（VTH = 0.5·VDD = 0.9 V），
再算 `setup_margin = t_CLK50 − t_D50`、`hold_margin = t_D50 − t_CLK50`、`clk→Q = t_Q50 − t_CLK50`；
源 delay 只是旋钮，不再被当成时间裕量。两组边沿速率各 13 点：

| 组 | 结果 |
|---|---|
| setup @1 ns 边沿 | 工作区间 [0.200, 20.000] ns，失败区间 [−1.000, 0.000] ns → 边界 (0.000, 0.200] |
| setup @50 ps 边沿 | 与工作区间同上 → 边界 (0.000, 0.200]，说明 setup 侧未被边沿速率扭曲，夹逼宽度=扫描步进 |
| hold @1 ns 边沿 | **HOLD BOUNDARY NOT FOUND IN CURRENT SWEEP**：no functional hold failure observed down to the tested source-delay margin = −1 ns。且因 pulse 时序为 `delay → rise → width`，该组数据下降实际比旋钮晚约一个 rise time，从未进入保持临界区 |
| hold @50 ps 边沿 | 工作 ≥ 0.000 ns，失败 ≤ −0.400 ns → 边界被夹在两者之间 |

两组 hold 结论不一致，正是"源边沿速率主导观测值"的直接证据，因此
**`HOLD_CHARACTERIZED: NO`**，本轮不产出任何 setup/hold 规格。
数据：`results/margin_setup_s1e-9.csv`、`results/margin_setup_s5e-11.csv`、
`results/margin_hold_s1e-9.csv`、`results/margin_hold_s5e-11.csv`；汇总在 `results/summary.json`
的 `margin_measured` 节。旧的按源 delay 写的 `results/margin_setup.csv` / `margin_hold.csv`
已在文件内标注 superseded（保留，不删，作为历史）。

## 5. 修 checker 后的完整回归（A9）

`scripts/regression_compare.py` 把修复前后同一测量逐条配对，判据是
`|new − old| <= 旧 transient maxstep`（=1e-4·T）：

```
compared=10  worst|delta|=1.66e-11 s   C2MOS_FUNCTION_REGRESSION: PASS
```

最大变化 16.6 ps 出现在 @9.765625 µs 那一组，其 maxstep 为 9.77e-10 s；
@200 ns 组最大 1.29e-11 s < 2e-11 s。也就是说：插值只改变了"交点落在哪一步"，
没有改变电路行为。没有为了维持旧数字而放宽判据。
基线（修复前）表保留在 `results/history/c2mos_delays_checker_before_fix.csv`。

## 6. 三个工艺角的小探针（A10）

`scripts/pvt_probe.sh` 先从 `QODER_PDK_LIB` 指向的模型库里 `grep` 出全部 `section` 名，
再按名字里可读的 nominal/slow/fast 角色映射；解析不出来就报
`PVT_PROBE: NOT_RUN_AMBIGUOUS_CORNER`，绝不自造 section。本次解析结果
`nominal=tt slow=ss fast=ff`（库里另有 `fnsp`、`snfp`）。

1.8 V、50 fF、3 级链、T=200 ns（应力速率）下三个角各 40/40 通过，clk→Q：
tt 0.4215 / ss 0.5128 / ff 0.3533 ns（FF0），且 q2 在 q1 首次取到该位的同一沿仍保持低
→ 没有出现"一个时钟沿穿过超过一级"。这很重要，因为每一级都用内部反相器自产 `clkb`。
证据：`results/evidence/c2mos_assert_shift3_pvt_{tt,ss,ff}_1.txt`、
`results/evidence/pvt_probe_summary.txt`。
**未做**：voltage sweep、temperature sweep、Monte Carlo、mismatch —— 按指示。

## 7. 来源标签（A6）

新增 `scripts/provenance_check.py`，规则：标签只能取
`COURSE_REQUIREMENT / COURSE_FIGURE / TEACHER_PAPER / ENGINEERING_DERIVATION /
GPT6_LEGACY_PROPOSAL / POC_ASSUMPTION / NOT DEFINED`；`TEACHER_PAPER` 必须在同段引用老师论文
（Micromachines 16(2) 207 / DOI 10.3390/mi16020207 / Xiao / 64×64 GaN）；
只引用 `spec_v12_text.txt`（= 旧 GPT-6 方案）的行不得升格为 `TEACHER_PAPER` 或  <!-- check:skip 引用被废除的说法，正是在说明它被废除 -->
`COURSE_REQUIREMENT`；keeper/写入/工艺角/裕量类句子里禁止 `always|guaranteed|all corners`  <!-- check:skip 引用被废除的说法，正是在说明它被废除 -->
（R4）。它同时认旧的 `【题面】/【规格书 V1.2】/【文献参考】/【计算得到】/【课程设计假设】` 记号。  <!-- check:skip 引用被废除的说法，正是在说明它被废除 -->

本次被抓出并已改正的实际违规：`reports/c2mos_review_notes.md` 把"扫描=列、数据=行"标成  <!-- check:skip 引用被废除的说法，正是在说明它被废除 -->
`TEACHER PAPER` 而唯一依据是 V1.2 抽取件 → 改为 `COURSE_FIGURE` + `ENGINEERING_DERIVATION`；  <!-- check:skip 引用被废除的说法，正是在说明它被废除 -->
`CONTRIBUTING_AI.md` 与新报告的带空格标签 → 下划线式；
`spectre/C2MOS_DFF.scs` 与 `scripts/microled_arch_calc.py` 的绝对化/来源表述 → 改为"已测条件下成立"。

## 8. 本轮明确不做的

async reset、BLANK、level shifter、扫描功率输出级、数据驱动、schematic、layout、DRC/LVS、
Monte Carlo；VLED / Micro LED Vf 仍 `NOT DEFINED`；输出域（1.8 V / 3.3 V）仍只是候选，不写成规格。

## 9. 复现

```bash
python scripts/test_psf_check.py --write-transcript results/checker_unit_test.txt
python scripts/netlist_stats.py                       # DEVICE_COUNT_CHECK
bash   scripts/tb_preflight.sh <proj>/spectre/c2mos_ff1_func.scs 1.8 good
bash   scripts/tb_preflight.sh <proj>/spectre/preflight_negative_vss_float.scs 1.8 bad   # 必须 FAIL
bash   scripts/c2mos_check.sh ff1 2e-7 rev1 2
bash   scripts/c2mos_check.sh shift3 2e-7 rev1 2
bash   scripts/c2mos_check.sh shift3 9.765625e-6 revnom 1
bash   scripts/c2mos_margin.sh setup 1e-9;  bash scripts/c2mos_margin.sh setup 5e-11
bash   scripts/c2mos_margin.sh hold  1e-9;  bash scripts/c2mos_margin.sh hold  5e-11
bash   scripts/pvt_probe.sh 2e-7
python scripts/export_results.py
python scripts/regression_compare.py --old results/history/c2mos_delays_checker_before_fix.csv \
       --new results/evidence/c2mos_delays_ff1_rev1_1.txt \
       --new results/evidence/c2mos_delays_shift3_rev1_1.txt \
       --new results/evidence/c2mos_delays_shift3_revnom_1.txt
python scripts/provenance_check.py
```
仿真侧命令都在 guest 的 `/root/microled_ai_project` 下执行，PDK 路径来自未跟踪的
`spectre/pdk_local.env`。
