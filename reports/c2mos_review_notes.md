# Review notes —— C²MOS 单相主从 DFF（1 路扫描移位最小单元）

这段文本会被 `scripts/make_review_bundle.py --notes reports/c2mos_review_notes.md`
原样并入 REVIEW_README 的 "Task / requirements / assumptions" 一节。

## Task

本轮**不设计新电路功能**，只回答一个问题：在这套 IC617 + 老师 SMIC 018 MM RF 交付上，
AI 能否做出一个**能被数值断言证明可用**的扫描驱动器最小单元（1 路）。
交付物 = 一个 fully-static 单相 C²MOS 主从 DFF cell + 3 级相同实例链 + checker + 数值结果。

范围之外（按指示冻结）：扫描功率输出级、VLED、Micro LED Vf、电平搬移、版图、DRC/LVS、阵列。

## Requirement 分类（每条只有一个标签，机检：`scripts/provenance_check.py`）

标签含义：`COURSE_REQUIREMENT` 老师正式题目文字或用户明确确认的课程条件；`COURSE_FIGURE`
正式题目里的布局结构图；`TEACHER_PAPER` 老师论文（Xiao et al., *A 64 x 64 GaN Micro LED
Monolithic Display Array*, Micromachines 16(2) 207, 2025, DOI 10.3390/mi16020207）的实际内容；
`ENGINEERING_DERIVATION` 由前三者算出；`GPT6_LEGACY_PROPOSAL` 只出自旧 V1.2 交付包；
`POC_ASSUMPTION` 本仿真自设条件；`NOT DEFINED` 题目未给。

| 条目 | 标签 | 依据 |
|---|---|---|
| 1024 列 × 768 行、5 µm 像素、15 µA 为**选通态瞬时**像素电流、60–100 Hz | `COURSE_REQUIREMENT` | 正式题目文字；15 µA 的含义由用户于 2026-10-04 明确确认 |
| 扫描驱动 = 列驱动（1024 根，2×512，上下，奇偶列，高边开关）；数据驱动 = 行驱动（768 根，2×384，左右，奇偶行，恒流吸收） | `COURSE_FIGURE` + `ENGINEERING_DERIVATION` | 正式布局结构图（Figure 3 的行列与上下/左右分区）加上 1024×768 的计数推导。**旧版把这条标成 `TEACHER PAPER` 是错的**：它当时唯一的引用是 `spec_v12_text.txt`，那是 `GPT6_LEGACY_PROPOSAL`，不能提升证据等级 |  <!-- check:skip 本行是在引用被废除的旧标签，不是在使用它 -->
| 列周期 9.765625 µs @100 Hz = 1/(1024×100)；单根扫描线最大电流 I_SCAN_MAX = 768×15 µA = 11.52 mA | `ENGINEERING_DERIVATION` | 由上面两行算出；`scripts/microled_arch_calc.py` 内含反向自检 |
| 正式工艺 = 老师交付副本 smic18mmrf_teacher，只用 1.8 V 核心管 n18/p18 | `COURSE_REQUIREMENT` | 用户指定；副本与 zip 逐文件 CRC 全对 |
| 本轮只做 1 路、只做移位 + 最小单元、不接输出级 | `COURSE_REQUIREMENT` | 用户 2026-10-04 明确指示 |
| 测试时钟 T=200 ns、每管 50 fF 负载、源边沿 1 ns / 50 ps 两组、电平判据 1.7 V / 0.1 V、13 个 margin | `POC_ASSUMPTION` | 题目未给；不代表任何真实负载或规格 |
| 灰阶位数、PWM/PAM 深度、消隐占比、pitch、Vf、VLED、输出电压域、复用系数 | `NOT DEFINED` | 题目未给，**不得当已知量继续推算** |
| 旧 `MicroLED_驱动芯片规格书_V1.2_最终交付包`（抽取件 `spec_v12_text.txt`）里的任何数值 | `GPT6_LEGACY_PROPOSAL` | 那是旧 GPT-6 生成的设计方案，不是老师论文也不是题面；只作对照，不作依据 |


## Circuit / clock 极性

外部只给一根 `clk`；`clkb` 由单元内部反相器产生。
`clk=0` 主锁存透明（`m = !d`）、从锁存保持；`clk=1` 主锁存保持、从锁存透明（`q = !m = d`）
→ **上升沿触发、D→Q 同相**。器件级 D/G/S/B 表与分相位导通表由 bundle 从 netlist **解析生成**，
不是手写的，所以不会和源码漂移。

## Known failures / 未做的部分（不能只报成功）

1. **上一轮 TG 移位单元的失败归因是错的，且没有被重跑过。** 真因是 testbench 的 `vss`
   从未接地（NMOS 全部无电流路径，节点被泵到 VDD 以上，Spectre 报 0 error）。因此
   "互补两相 TG 锁存链存在 keeper/写入强度冲突、拓扑不可行"这个结论**已作废**；
   `spectre/shift_unit_tb.scs` 至今没有在正确接地下验证过，它现在是 unknown，不是 FAIL 也不是 PASS。
2. **PVT 只做了三个工艺角探针，不是表征。** 工艺角名从模型库的 `section` 列表实测读出
   （`tt` / `ss` / `ff`，另有 `fnsp` / `snfp`），不猜。3 级链在 tt/ss/ff 下 40/40 断言都过、
   同一沿不穿透多級 ✓ 但仍是**单一 VDD(1.8 V)、单一温度、单一负载(50 fF)、无 mismatch、
   无 Monte Carlo、无噪声**。keeper 0.25× 的写入/保持裕量已被验证**在这些条件下成立**，
   不得写成"总能写入 / 全角保证"。
3. **建立时间：两组边沿速率给出同一夹逼。** 用实测 50% 跨点（VTH = 0.5·VDD）计：
   `setup_margin = t_CLK50 − t_D50`，1 ns 与 50 ps 两组都是 **≥ +0.200 ns 捕获、≤ 0.000 ns 失败**
   → 当前夹逼宽度就等于扫描步进 0.2 ns，边界并未被边沿速率扭曲。
4. **保持时间：`HOLD_CHARACTERIZED: NO`，且不得给数值 spec。** 实测
   `hold_margin = t_D50 − t_CLK50`（数据变化点相对时钟 50% 点）：
   - 1 ns 边沿组：**HOLD BOUNDARY NOT FOUND IN CURRENT SWEEP** ——
     no functional hold failure observed down to the tested source-delay margin = −1 ns；
     而且因为本仿真器的 pulse 时序是 `delay → rise → width`，1 ns 那组的**数据下降沿实际比旋钮值晚
     约一个 rise time**，所以它只测到了正 hold 侧，从未进入保持临界区；
   - 50 ps 边沿组：边界夹在 **≥ 0.000 ns 保持成功 / ≤ −0.400 ns 失败** 之间。
   两组结论不同本身就说明：源边沿速率正在主导观测值，而"源 delay 旋钮"不等于阈值到阈值的保持时间。
   因此本轮只标 PRELIMINARY CHARACTERIZATION，不产出 hold 规格。
5. **无复位**：从锁存是一对对称交叉耦合反相器，上电直流解未定义。testbench 用前两个（链：三个）
   时钟沿做 priming 才让状态确定，之后才断言。真实扫描驱动器一般自带 RST/blanking，这里按指示没加。
6. **完全没有覆盖真实负载条件**：15 µA 像素电流、列电极实际 RC、VLED 域都不在这个 POC 里，
   50 fF 只是栅负载占位。
7. 未做 schematic/layout/DRC/LVS；未做 1024 位以上的链；未做功耗与面积估计。

## Questions for reviewer（本轮最不确定的 3 点）

1. **单相 C²MOS 用在扫描驱动器列选择链上是否合适？** 这里没有时钟非交叠，靠的是"C²MOS 在不
   有效相位两条堆叠都断开轨"。在 9.765625 µs 列周期里，一根扫描线要保持整列时间；我测的保持窗口
   只有 100 ns（T=200 ns 时钟）。是否要求我按列周期量级（µs）重做保持/漏电验证，并补 ss/ff 与
   高 corner 温度，才允许声称可保持？
2. **priming 无复位是否可接受？** 现在链的初态靠"前几个沿把 DIN=0 移进去"来确定。真实扫描驱动器
   通常有复位/消隐来保证换列安全。如果课程要求上电确定态，我应该加异步复位（会改 cell），
   还是保持无复位 + priming 周期并在文档里写清楚？
3. **判据阈值与"full swing"的定义**：我用了 >1.7 V / <0.1 V（VDD=1.8 V）与 50% 跨点测延迟。
   审核方是否要求改成 (VDD−Vth) 之类的静态噪声容限口径，或者补充噪声容限/最小噪声裕量测量？
   以及：断言窗口的时间余量（早窗 +0.20T、晚窗 +0.60T）是否偏松？

## 复现要点

PDK 不在仓库里。netlist 通过 `include "${QODER_PDK_LIB}" section=tt` 引用模型库，该变量由
`scripts/run_spectre.sh` 从未跟踪的 `spectre/pdk_local.env` 载入；没有这个文件时 runner 会
明确拒绝运行，而不是给出一个看不懂的仿真错误。
