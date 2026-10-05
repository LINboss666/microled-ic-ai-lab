# 一路 15 µA Micro LED Data Driver 最小单元 —— 设计与 Spectre 实测（DATA-1）

日期 2026-10-05，分支 `poc/data-driver-1ch`。工艺 = 老师交付副本 `smic18mmrf_teacher`（只读，未改任何模型/techfile/deck）。
所有数值来自仓库内的机器生成文件（`results/data_driver_dc.csv`、`results/data_driver_transient.csv`、
`results/evidence/ddrv_*.txt`），出处标在每节末。本轮**不建 Virtuoso schematic**。

## 状态

```
DATA_DRIVER_1CH        : PASS
SELECTED_TOPOLOGY      : cascode current sink + shared steered bias (candidate C_cascode)
OUTPUT_DEVICE          : n33  (3.3 V family, 1.8 V 域逻辑门控)
TRANSISTOR_COUNT       : 每通道 2 只走像素电流 (Mout + Mcas)；共享偏置块 4 只 (Mref/Msteer/Mdummy/Mbleed)
FUNCTIONAL             : ON = 14.9465 uA @ tt, err -0.357 %；OFF = 5 pA @ 3.3 V
COMPLIANCE             : +/-1% 从 0.4515 V 起，可用到 3.1505 V（本 testbench 上限）
TIMING/PVT             : 三工艺角已过（固定尺寸跨 corner）；无 mismatch / Monte Carlo / 温度扫描
DATA_DIRECTION_CONFLICT : 未出现（见下节）
DATA_DRIVER_AGENT_POC  : PASS          (本轮冻结状态，等独立源码 review)
INDEPENDENT_SOURCE_REVIEW : READY
SCALABILITY_CONCERN_FOUND : YES         (共享 vbias 与单通道 Mbleed 冲突，见 review notes；电路未改)
DEVICE_STRESS            : EXTRACTED    (六只管子的 max|VGS|/|VGD|/|VDS| 来自实测扫描)
电流定义 / compliance 办法 / 理想源清单 / 器件表与应力表：见
`reports/data_driver_review_notes.md` 与生成的 `reports/ddrv_topology_summary.md`
```

## 需求与来源标签（每条只有一个标签，机检 `scripts/provenance_check.py`）

| 条目 | 标签 | 依据 |
|---|---|---|
| `I_PIXEL_ON = 15 µA`，像素被选通发光期间的**瞬时**电流（不是帧平均） | `COURSE_REQUIREMENT` | 用户 2026-10-04 定义 D1，本轮重申 |
| 数据通道 = 吸收电流的一侧，`DATA_OUT → 15 µA sink → VSS` | `ENGINEERING_TOPOLOGY_CHOICE` | 用户本轮给的方向。**修正记录**：本报告第一版把它标成 `COURSE_REQUIREMENT`，那是过度声明——书面出处只有旧 GPT-6 交付包（`GPT6_LEGACY_PROPOSAL`），正式题目文字/图没有唯一确定电流在哪一侧。详见 `reports/data_driver_review_notes.md` 的 `REVIEW_PREP_BUG_FOUND`；此修正**不影响任何测量值**。 |
| 已核对：这与既有拓扑结论一致，故未触发 `DATA_DIRECTION_CONFLICT` | `ENGINEERING_DERIVATION` | `reports/topology_channel_check.md`、`reports/architecture_baseline.md` 的既有推导 |
| 列周期 9.765625 µs = 1/(1024×100 Hz)，只作时间尺度参考 | `ENGINEERING_DERIVATION` | 由题面 1024 列 + 60–100 Hz 直接推出 |
| ±1 / ±2 / ±5 % 判据、`VDD=1.8 V`、`RSEN=10 kΩ`、`Vcas=1.8 V`、扫描步长、边沿 1 ns | `POC_ASSUMPTION` | 题目未给，为本轮比较拓扑而定义，不构成指标 |
| Vf、VLED、灰阶位数、PWM/PAM 深度、消隐占比、数据锁存/移位协议 | `NOT DEFINED` | **未代入任何计算**，见"限制"一节 |

## 器件族选择：n18 还是 n33（不允许按名字决定）

先读 PDK 里两个 family 的注释与 section（只读；模型系数不复制到仓库）：`tt ss ff snfp fnsp mos_mc`
六个 MOS section；`n18` 标在 "1.8v core" 条目下，`n33` 标在 "3.3v" 条目下。几何合法性由 Spectre 自己
裁决（非法尺寸报 `CMI-2441`），本轮用到的 `l=1~2 µm`、`w=1e-5~4e-5 m` 全部通过，0 warning。

判据是**实测的输出特性**，同一 cascode 拓扑、同一尺寸、同一 15 µA：

| 输出管 | 扫到 | err @ 最高点 | ±1% 合规点 | ±5% 合规点 | rout | OFF 泄漏 @ 上限 |
|---|---|---|---|---|---|---|
| `n18` | 1.65 V（1.8 V 域上限） | −0.38 % | 0.4114 V | 0.1169 V | — | 26 pA |
| `n33` | 3.15 V（3.3 V 域上限） | +0.36 % | 0.4515 V | 0.1157 V | 1.29e8 Ω | 5 pA |

结论：两者在本 POC 的电流精度上同级（都 <0.4 %），差别在**可承受的漏压范围**——`n33` 把可用输出窗口从
1.65 V 扩到 3.15 V，OFF 泄漏还低一个数量级。因为 `Vf`/`VLED` 是 `NOT DEFINED`，不能假设 `DATA_OUT`
固定落在某个电压上，所以选 `n33` 做输出堆叠（`DATA_EN` 仍用 1.8 V 逻辑驱动，实测功能正常）。

> 未解决、需要人定的问题（不是本轮 blocker）：若最终 VLED 域使 `DATA_OUT` 需要承受 >3.3 V，
> 则固定 `smic18mmrf_teacher` 里没有合法单管（上一轮 `reports/topology_channel_check.md` 已记这条冲突），
> 那时要么改堆叠/改 VLED，要么索取 5 V 器件。**在这之前我不虚构任何电压。**

## 门控方案比较（同一 15 µA、同一尺寸、tt）

| 方案 | 每通道走电流的管子 | err @ 最高点 | ±5% 合规点 | 相对 B/C 多吃的余量 | ON 窗口内不达标 | 峰值电流 | OFF 泄漏 |
|---|---|---|---|---|---|---|---|
| `A_series`（电流路径里串开关管） | 2 | −4.07 % | 1.3574 V | +1.24 V | 4/4 个 ON 窗口（`NOT_FOUND`） | 80.7 µA | 24 pA |
| `B_gate`（门控偏置：转向 + 泄放） | 1 | +5.00 % | 0.1157 V | 基准 | 0/4 | 24.5 µA | 3 pA（1.8 V 逻辑下） |
| `C_cascode`（共源共栅 + 同样的门控偏置） | 2 | −0.36 % | 0.1157 V | 基准 | 0/4 | 19.9 µA | 5 pA |

- `A_series` 的失败有实测机制，不是调参没调好：串在路径里的开关管自己要吃 `Vds`，
  于是 ±5% 合规点被推到 **1.36 V**，本轮选的 1.2 V 测试点根本不在恒流区内（DC 已独立确认这一点），
  并且关断时 `mid` 节点放电到 0、再导通时要经 10 kΩ 采样电阻重新充电，形成 80 µA 的等电位冲击。
- `B_gate` 只有一条管子走电流，余度最低（0.116 V），但**单管镜像受沟道长度调制太大**：
  整个扫描范围内电流漂 9.17 %，`±1%` 找不到合规点。
- `C_cascode` 同时拿到两者：合规点仍低（0.116 V @±5%，0.4515 V @±1%），且调节到位
  （最高点 −0.36 %，rout 1.3×10⁸ Ω）。

按题目给的规则（A/B 证明不够才上 C），这里 A/B 的不足有明确数值依据，因此进入 C，并且**没有**堆更复杂的
结构（未用 regulated-cascode / 电流 DAC）。

## 尺寸扫描（合法范围内扫 L 与 W，目标不是面积最小）

同一 cascode 拓扑、`n33`、`vcas=1.8 V`、`tt`：

| L | W | err @ 最高 | ±1% 合规点 | ±2% | ±5% | 高于 ±5% 膝点的电流跨度 |
|---|---|---|---|---|---|---|
| 1 µm | 10 µm | +0.48 % | 0.6115 V | 0.4129 V | 0.1570 V | 5.17 % |
| 2 µm | 10 µm | +0.13 % | 0.4715 V | 0.2528 V | 0.1556 V | 3.89 % |
| **2 µm** | **20 µm**（选定） | **−0.36 %** | **0.4515 V** | **0.2129 V** | **0.1157 V** | **4.15 %** |
| 1 µm | 40 µm | +1.18 % | `NOT_FOUND` | 0.3729 V | 0.1171 V | 5.93 % |

`L` 与 `W` 的 tradeoff 明确：**加长 L 主要压制沟道长度调制（误差与跨度都变小），加大 W 主要降低膝点电压
（过驱电压 Vov 变小）**；`L=1 µm` 配大 `W` 反而最差（+1.18 % 且 ±1% 无解），说明单纯放大管子不能解决调节。
选定 `L=2 µm / W=20 µm`（`m=1`，未做 finger/multiplicity）。

## 共源共栅偏置：不需要升压

`vcas` 扫了 1.8 / 2.0 / 2.2 / 2.4 V：±1% 合规点都是 0.4515 V，误差从 −0.36 % 单调移到 +0.36 %，
rout 从 1.4×10⁸ 升到 1.7×10⁹ Ω。也就是说 **`vcas = 1.8 V`（芯片内部 1.8 V 域就能产生）已经达标**，
不需要为共源共栅管单独做升压。本轮 `vcas` 用理想电压源（`POC_ASSUMPTION`），真实的偏置堆叠留到下一阶段。

## Transient（`T=200 ns` 快测 + `T=9.765625 µs` 系统时间尺度）

| 周期 | V(DATA_OUT) | ON 窗口 | 最差进入 ±5% 时间 | 最差关断时间 | 峰值 | OFF 泄漏 | 判据 |
|---|---|---|---|---|---|---|---|
| 200 ns | 0.5 / 1.2 / 3.0 V | 101 ns | 37 / 44 / 40 ns | 11 / 14 / 7.5 ns | 15.9 / 19.9 / 20.8 µA | 8.8 / 24 / 21 nA | OK |
| 9.765625 µs | 0.5 V | 4.88 µs | 200 ns (4.1 %) | 11 ns | 15.9 µA | 74 pA | OK |
| 9.765625 µs | 1.2 V | 4.88 µs | 398 ns (8.1 %) | 7.7 ns | 19.9 µA | 352 pA | OK |
| 9.765625 µs | 3.0 V | 4.88 µs | 442 ns (9.0 %) | 299 ns | 20.8 µA | 6.1 nA | OK |

三个测试电压点不是硬编码：0.5 V 在 ±1% 合规点（0.4515 V）之上一点，1.2 V 在恒流区中段，
3.0 V 是 3.3 V 族内合法的高端（受 10 kΩ 采样电阻限制，实际最高测到 3.15 V）。

需要如实说明的两点：

- 慢周期下的进入时间（200–442 ns）**比快周期的 37–44 ns 大一个数量级**，原因是关断窗口越长，
  镜像栅节点被泄放管放得越空，每个像素导通时要重新充上去。也就是说**门控偏置方案的建立时间由偏置节点
  再充电决定**；在 4.88 µs 的 ON 窗口里占 4–9 % 可接受，但若以后要把一行的选通时间压到亚微秒级，
  这条就必须重新设计（例如常开偏置 + 只在输出侧门控）。
- 200 ns 那一组余量很小（44 ns 建立 / 101 ns ON 窗口，判据要求保持 40 %），
  它是**故意用作压力测试的时间尺度参考**，不代表任何已确定的数据通道协议。

## 三个工艺角（固定一套尺寸，不逐角重新调参）—— BASIC PROCESS CORNER PROBE ONLY

| corner | err @ 最高 | ±1% 合规点 | ±2% | ±5% | 跨度 |
|---|---|---|---|---|---|
| `tt` | −0.357 % | 0.4515 V | 0.2129 V | 0.1157 V | 4.15 % |
| `ss` | −0.550 % | 0.5115 V | 0.2330 V | 0.1169 V | 4.06 % |
| `ff` | −0.156 % | 0.4115 V | 0.2128 V | 0.1155 V | 3.49 % |

角名是从模型库的 `section` 列表实测读出的，没有猜。三角都满足 ±1%（在 ≥0.52 V 的输出电压以上），
说明这套尺寸对角度不敏感；**没有**做电压/温度扫描、mismatch、Monte Carlo，
所以这一节的地位是 `BASIC PROCESS CORNER PROBE ONLY`，**不能**读成 `PVT SIGNOFF PASS`。

## 电流定义与 compliance 提取办法（避免方向含糊）

```
IOUT = ( V(vsw) - V(data_out) ) / RSEN        # RSEN=10k，在通道之外的 testbench 元件
正方向 = 电流从测试源经 RSEN 流入 DATA_OUT 再向下到 VSS（"吸收"为正）
```

不用 `save i(...)` / `save X:current`：这个 Spectre build 分别报 SFE-874 与 SPECTRE-8059/8287
并忽略该 save，留 warning 的跑法不算证据。绝对值只用于 OFF 泄漏与峰值电流两处的报告，
误差、compliance 与瞬态带判据都用带符号的 IOUT。

compliance 的求法：`tol ∈ {1,2,5} %`，找**最低的** `V(data_out)` 使其**之上所有**采样点都满足
`|IOUT − 15 µA| ≤ tol·15 µA`；直接用采样点、不做插值，所以分辨率等于扫描步长
（步长 0.02 V 与 0.05 V 两组膝点都写进 CSV，见"限制"第 4 条）。上部可用电压还被 `RSEN` 压掉 0.15 V，
所以 3.3 V 扫描实际测到 ≈3.15 V。


## 复现

```bash
bash scripts/ddrv_run.sh selfcheck                          # 平板 testbench 的 preflight 必须能 FAIL
bash scripts/ddrv_run.sh dc C_cascode n33 2e-6 2e-5 tt 3.3 0.02
bash scripts/ddrv_run.sh tran C_cascode n33 2e-6 2e-5 9.765625e-6 1.2 tt 1e-9
bash scripts/ddrv_verify.sh                                  # 汇总判据 DATA_DRIVER_1CH: PASS
python scripts/ddrv_dump.py <psfascii> --stride 8            # 直接看波形
```

`QODER_PDK_LIB` 来自未跟踪的 `spectre/pdk_local.env`；runner 在该变量缺失时拒绝运行，
模型卡与 deck 从不进仓库。

## 限制与本轮没做的事（不能只报成功）

1. **`Vf` / `VLED` 仍是 `NOT DEFINED`**，所以没有建 LED 模型、没有虚构工作点。DC 把 `V(DATA_OUT)` 当
   独立变量扫；给出的答案是"要多少输出电压才能恒流"（±1% 需 ≥0.45 V），不是"真实像素上的电压"。
2. **15 µA 参考是理想电流源**（`IDEAL IREF = TESTBENCH ASSUMPTION`），`vcas` 也是理想电压源。
   真实的共享 bias/reference 系统不在本轮范围，最小通道本身只包含每路真正需要重复的 2 只管子。
3. **`RSEN = 10 kΩ` 是 testbench 造成的**：它把可扫上限压到 3.15 V，并且是开关瞬态峰值电流的来源。
   换成真实负载（含 LED 结电容与线路）后峰值会不同，本轮不声称已表征那部分。
4. **膝点对扫描步长敏感**：步长 0.02 V 时 ±2%/±5% 是 0.213/0.116 V，步长 0.05 V 时是 0.253/0.154 V。
   两者都写进 CSV，不挑一个好看的数。
5. `A_series` 判为不可用（`NOT_FOUND` + 80 µA 冲击），`B_gate` 判为调节不足（跨度 9.17 %，±1% 无解）：
   这两条是**本轮的负结果**，不是失败隐藏。
6. Transient 指标本身在写第一版时有过两个真 bug（窗口跨周期借样本、OFF 采样落在下一个 ON 窗口里），
   当时报出 837 ns 建立与 12 µA "OFF 泄漏"；波形核查后算法改成按窗口计算并重跑，
   上面的表是重跑后的数，`scripts/ddrv_dump.py` 与注释留在了仓库里说明这件事。
7. `MAX_MAJOR_REDESIGN` 未用满：拓扑只走到 A/B/C 三个候选，C 一次成型，没有随机改 W/L 碰运气。
8. 未做：384 通道扩展、数据锁存/移位、SPI、灰阶/PWM、TCON、schematic、layout、DRC/LVS/PEX。

## 最终单元的晶体管级 ASCII 拓扑

```
                      vsw (ideal VOUT test source, 本轮当独立变量扫)
                        o----[ RSEN 10k ]----o data_out
                                                 |
                        +------------------------+  <- DATA_OUT (吸收 15 uA)
                        |  Mcas  n33 L=2u W=20u   gate = vcas (=1.8 V)
                        +------------------------o node_m
                        |  Mout  n33 L=2u W=20u   gate = vbias
                        +------------------------o vss (= node 0)

   共享偏置块（不是每通道重复的器件）：
   vdd --[ IREF ideal 15u ]--o ref_top
                             |  Msteer  gate = data_en     -> vbias
                             |  Mdummy  gate = data_en_b   -> vss
        vbias o--o Mref (diode, 1:1) o--o vss
        vbias o--o Mbleed gate = data_en_b --> vss      (关断时把镜像栅放到 0)
```
