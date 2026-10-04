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
8. **仓库已 PUBLIC，身份清理仍开放（不是电路结论）。** `SOURCE_RELEASE_SAFETY = PASS`（PDK / 模型卡 /
   deck / 凭据 / 私钥 / raw PSF 都取不到，匿名整树 157 文件 0 命中），但 10 个被元数据重写替换的 commit 里
   仍有 9 个被 GitHub 按 SHA 服务，其 author/committer 字段带着旧地址 →
   `IDENTITY_PRIVACY_CLEANUP = PENDING_OWNER_ACCEPTED`（用户 2026-10-05 明确接受并要求暂缓处理）。
   原始 `PUBLIC_RELEASE_SAFETY_GATE` 与 `PUBLIC_RELEASE_POSTCHECK` 在这一项清零前继续报 FAIL，我没有把它们改成绿。
   这条不影响任何数值，也不构成 C²MOS 的 FAIL。详见 `reports/public_release_audit.md`。

## Questions for reviewer（本轮要 reviewer 明确回答的 3 点）

1. **18 MOS 的 C²MOS 拓扑是否存在结构性问题？** 判据请对着 `spectre/C2MOS_DFF.scs` 和 bundle 里由它现场
   解析出的器件表、ASCII 堆叠与"哪个相位哪几只 clock 管 ON"的推导表（`TOPOLOGY_DERIVATION: PASS`，
   master=`m`、slave=`q`）。特别是：主/从各自"数据堆叠 + keeper"的两两组合，在你看来是否构成可接受的
   单相 C²MOS，还是有我没看到的结构缺陷（例如 keeper 与数据堆叠共用节点导致的写/保持冲突）。
2. **单元内部自生成的 `clkb`（那个反相器）是否需要在下一阶段针对 race/skew 做更严格验证？** 现在每颗 FF
   自己产生互补相，实测没有同沿穿透（三工艺角各 40/40，`regression_compare` 前后一致）。要不要补
   clock 到 `clkb` 的延时分量、跨 FF 的相位错位、以及沿速率更陡时的穿透扫描，才算可以进 schematic？
3. **当前 checker + preflight 的强度是否足以批准进入 Virtuoso 原理图阶段？** 依据：合成波形判据用例
   （`CROSSING_CHECKER_UNIT_TEST`，9 例）、rail/0 参考预检加必须 FAIL 的负样本（`TESTBENCH_PREFLIGHT`）、
   器件计数与来源标签机检。如果你觉得还缺某一类自动检查（例如断言窗口收紧、跨 corner 判据、
   或把 `clk->Q` 提取改成阈值到阈值的静态噪声容限口径），请直接点名要哪一条。

上一轮遗留、仍未答的三点（不阻塞本轮，但会影响下一阶段）：是否按列周期量级（µs）重做保持/漏电并补
高低温 corner；无复位 + priming 是否可接受；full-swing 判据口径与断言窗口余量是否偏松。

## 复现要点

PDK 不在仓库里。netlist 通过 `include "${QODER_PDK_LIB}" section=tt` 引用模型库，该变量由
`scripts/run_spectre.sh` 从未跟踪的 `spectre/pdk_local.env` 载入；没有这个文件时 runner 会
明确拒绝运行，而不是给出一个看不懂的仿真错误。
