# Review notes —— C²MOS 单相主从 DFF（1 路扫描移位最小单元）

这段文本会被 `scripts/make_review_bundle.py --notes reports/c2mos_review_notes.md`
原样并入 REVIEW_README 的 "Task / requirements / assumptions" 一节。

## Task

本轮**不设计新电路功能**，只回答一个问题：在这套 IC617 + 老师 SMIC 018 MM RF 交付上，
AI 能否做出一个**能被数值断言证明可用**的扫描驱动器最小单元（1 路）。
交付物 = 一个 fully-static 单相 C²MOS 主从 DFF cell + 3 级相同实例链 + checker + 数值结果。

范围之外（按指示冻结）：扫描功率输出级、VLED、Micro LED Vf、电平搬移、版图、DRC/LVS、阵列。

## Requirement 分类（每条只有一个标签）

| 条目 | 标签 | 依据 |
|---|---|---|
| 1024 列 × 768 行、5 µm 像素、15 µA 为**选通态瞬时**像素电流、60–100 Hz | `COURSE REQUIREMENT` | 题目给定；15 µA 的定义由用户于 2026-10-04 明确 |
| 扫描驱动 = 列驱动（1024 根，2×512，上下，奇偶列，高边开关）；数据驱动 = 行驱动（768 根，2×384，左右，奇偶行，恒流吸收） | `TEACHER PAPER` | 规格书抽取文本 `spec_v12_text.txt` L8 / L17 / L32 / L76 / L79 / L112 |
| 列周期 9.765625 µs @100 Hz = 1/(1024×100)；单根扫描线最大电流 I_SCAN_MAX = 768×15 µA = 11.52 mA | `ENGINEERING DERIVATION` | 由上面两条直接推导，脚本 `scripts/microled_arch_calc.py` 内含反向自检 |
| 正式工艺 = 老师交付副本 smic18mmrf_teacher，只用 1.8 V 核心管 n18/p18 | `COURSE REQUIREMENT` | 用户指定；副本 CRC 与 zip 全对 |
| 本轮只做 1 路、只做移位 + 最小单元、不接输出级 | `COURSE REQUIREMENT`（用户指示） | 用户 2026-10-04 明确 |
| 测试时钟 T=200 ns、每管 50 fF 负载、源边沿 1 ns、电平判据 1.7 V / 0.1 V、13 个 margin | `POC ASSUMPTION` | 题目未给；不代表任何真实负载或规格 |
| 灰阶位数、PWM/PAM 深度、消隐占比、pitch、Vf、VLED、输出电压域、复用系数 | `NOT DEFINED` | 题目未给，**不得当已知量继续推算** |

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
2. **只跑了 `tt` corner、默认温度**。没有 ss/ff、没有电压/温度扫描、没有 mismatch、没有噪声。
   keeper 0.25× 的写入/保持裕量因此只在一种条件下成立。
3. **建立/保持的测量值受源边沿速率限制**：时钟与数据边沿都是 1 ns，所以
   setup ∈ (0.0, 0.2] ns、hold ≈ 0 ns 是"边沿限制下"的数，不是器件本征极限；
   要本征值需要把边沿压到 ~50 ps 重扫。
4. **hold 扫描里 margin ≤ 0 的三行不是保持测试**。原始采样显示 `d12` 在 499.98→501.7 ns
   之间才降完（数据边沿跨过时钟沿），那几行本质上是 setup 侧的行为，标签 HELD 容易被误读。
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
