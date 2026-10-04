# Phase DATA-3.5：Candidate E 瞬态数值真实性审计（物理耦合 vs 梯形积分振铃）

状态：
```
CANDIDATE_E_DC:                    PASS
CANDIDATE_E_STATIC_INDEPENDENCE:   PASS
CANDIDATE_E_TRANSIENT:             NUMERICAL_VALIDATION_REQUIRED -> 本轮完成
E_TRANSIENT_RESULT:                MIXED_NUMERICAL_AND_PHYSICAL
CANDIDATE_E_POC_STATUS:            ACCEPTABLE（附条件，见 §8）
```
电路完全冻结：`Mout/Mcas = n33 L=2u W=20u`、`Mpass_local = n33 L=2u W=5u`、
`Mbleed_local = n33 L=2u W=2u`、拓扑与 `Cbias`（本轮一律为 0/不加）不变，**没有做任何 sizing**。
证据：`results/data_driver_method_ab.csv`（22 次运行，全部读回自己用过的 method/reltol/maxstep）、
`results/evidence/ab_*.txt`（44 份）、`logs/ab_*.pipeline`。
脚本：`scripts/ddrv_method_ab.sh`；工具：`ddrv_gen.py --method/--errpreset`、
`ddrv_tran.py`/`ddrv_xtalk.py` 的 `ADJACENT_POINT_ALTERNATION` 检测。

---

## 1. traponly 到底从哪里来（不猜，逐项排除）

| 可能的来源 | 检查方法 | 结果 |
|---|---|---|
| 生成的 deck | `grep -cE "method\|reltol\|^options\|errpreset"` 于 `ddrv_E_..._A_default_slew1e-8...scs` | **0 处**（deck 里根本没有这些字） |
| 命令行 | `scripts/run_spectre.sh:82` 实际执行 `spectre "$NET" -64 -format psfascii` | 无 method/精度开关 |
| PDK / model include | `grep -cE "method\|traponly\|gear2only"` 于 `pdk/.../ms018_enhanced_v1p2_rev0_spe.lib` | **0 处** |
| 本机 simulator 默认 | `spectre/diag/method_default_probe.scs`：无 include、无 options 的纯 RC，`tran1 tran stop=900n step=100p maxstep=500p` | 运行头写 `errpreset="moderate"  method="traponly"  reltol=0.001` |
| 本机文档 | `spectre -h tran` → “`method` … **The default is derived from `errpreset'`**. Possible values are euler, trap, traponly, gear2, gear2only, trapgear2, trapeuler” | 与实探测一致 |

```
EFFECTIVE_TRANSIENT_METHOD: traponly
METHOD_SOURCE: Spectre 15.1.0.284 的内置默认 —— deck 未写 errpreset 时取 moderate，
               moderate 这个包同时给出 method=traponly、reltol=1e-3、relref=sigglobal、
               lteratio=3.5；不由本工程 deck、命令行或 PDK 设定
```
独立复核（不靠 RC 探针而靠真实 E 电路）：`A_default_*` 与 `A_traponly_*` 三个压摆下的
peak/charge/glitch/ringing 数值**逐位相同**（8.807476 µA / 0.0742 % / 1.708617e-05 s / 0.015709 µA），
所以生产默认 == traponly 在真实电路上也成立，不只是探针推断。

### 1.1 顺带纠正的两个方法事实

1. **per-analysis `reltol=` 在本机被接受但被忽略**：`tran1 tran ... reltol=0.0001` → 1 条 warning，
   运行头仍是 `reltol=0.001 / errpreset=moderate`。所以收紧容差只能用 `errpreset`。
2. **`errpreset` 是包不是单旋钮**：`errpreset=conservative` 同时把 reltol 设成 1e-4、
   `lteratio=10`、`relref=alllocal`，**并把 method 改成 gear2only**。因此本轮的容差实验必须
   显式钉住 method（`errpreset=conservative method=traponly`），并且每个运行都读回头部证明生效值 ——
   否则"只改了容差"这句话是假的。`ddrv_gen.py` 的 `--errpreset` 旁边总是配 `--method` 就是这个原因。

---

## 2. 积分方法 A/B（同一电路、同一激励、同一初值、同一 maxstep）

`T=9.765625 µs`（系统帧率）、`V(DATA_OUT)=1.20 V`（新零基准恒流区中点）、2 通道共享
`Mref + VBIAS_SHARED`、**CH1 = 常开受害通道**、**CH0 = 翻转侵犯通道**、`maxstep=5 ns`、
基线取同拓扑静态 (EN0,EN1)=(1,1) 运行的中位数（同一方法、同一 maxstep）。
`0.1 / 10 / 100 ns` 三种压摆全部测（不是只测好看的那个）。

| slew | 方法 | victim peak 串扰 | % of 15 µA | `Q_error` | 电荷误差 | >±1 % 毛刺时长 | victim 采样交替 |
|---|---|---|---|---|---|---|---|
| 0.1 ns | traponly（=默认） | 8.807476 µA | **58.72 %** | −3.914e-13 C | 0.0742 % | 1.709e-05 s | **YES** 0.015709 µA |
| 0.1 ns | gear2only | 8.988537 µA | **59.92 %** | −3.867e-13 C | 0.0732 % | **1.275e-07 s** | NO 0.000000 µA |
| 10 ns | traponly | 7.869516 µA | 52.46 % | −3.909e-13 C | 0.0741 % | 1.524e-07 s | NO 0.000618 µA |
| 10 ns | gear2only | 7.876419 µA | 52.51 % | −3.827e-13 C | 0.0725 % | 1.517e-07 s | NO 0.000000 µA |
| 100 ns | traponly | 2.363705 µA | 15.76 % | −4.464e-13 C | 0.0847 % | 3.498e-07 s | NO 0.000068 µA |
| 100 ns | gear2only | 2.241635 µA | 14.94 % | −4.460e-13 C | 0.0846 % | 3.343e-07 s | NO 0.000000 µA |

```
TRAPONLY_PEAK:   8.807476 uA (58.72 %) @0.1ns | 7.869516 uA (52.46 %) @10ns | 2.363705 uA (15.76 %) @100ns
GEAR2ONLY_PEAK:  8.988537 uA (59.92 %) @0.1ns | 7.876419 uA (52.51 %) @10ns | 2.241635 uA (14.94 %) @100ns
TRAPONLY_CHARGE_ERROR:  0.0742 / 0.0741 / 0.0847 %   (0.1 / 10 / 100 ns)
GEAR2ONLY_CHARGE_ERROR: 0.0732 / 0.0725 / 0.0846 %
```

**读法**：换到带数值阻尼的 gear2only 之后，峰值与电荷都留在同一位数（10 ns 点差 0.09 % 绝对、
0.1 ns 点差 2.1 % 相对、100 ns 点差 5.2 % 相对）→ **峰值串扰不是 ringing**。

同时抓到一个被 ringing 污染的量：**毛刺时长**。0.1 ns 压摆下 traponly 报 17.09 µs（占观测窗 48.6 %），
gear2only 报 0.1275 µs —— 差 **134 倍**。机理清楚：traponly 的样点交替把 `|I−I_baseline|`
长期顶在 ±1 % 带（0.15 µA）之上，于是"超时长度"其实是判据踩到了数值噪声；10/100 ns 两行里
两法一致（1.52e-07 vs 1.52e-07、3.50e-07 vs 3.34e-07），说明只有 0.1 ns 那一格被污染。
DATA-3 报告 §7.2 里"毛刺 17.1 µs / 52 %"这条**必须按 0.127 µs 重读**。

### 2.1 时间一致性（item 8 要求）

受害通道最坏样点与侵犯通道使能沿的距离（xtalk 直接给出）：

```
A_default_slew1e-10   worst sample t=4.1510e-05 s, 最近的 CH0 沿 t=4.1504e-05 s, delta 5.765e-09 s
A_gear2only_slew1e-10 worst sample t=4.1509e-05 s, 最近的 CH0 沿 t=4.1504e-05 s, delta 4.831e-09 s
```

扰动紧跟在邻居沿后 <6 ns，且两种方法一致；同一窗口内 `VBIAS_SHARED` 摆 0.2044 V（0.758–0.962 V）、
受害通道自己的 `vbias_ch1` 摆 0.0830 V（0.806–0.889 V），二者与电流误差同步 →
满足"只有 `VBIAS_SHARED`、`vbias_ch`、`I_victim` 时间一致才允许称物理串扰"的条件。
（这一条差点丢掉：`ddrv_xtalk.py` 之前把"邻居"取成了受害通道自己的常开使能，于是永远报
 "no edge found"、给出虚假的不相关。已在 `neigh = "data_en" if suf == "1" else "data_en1"` 修正，
 本轮 22 个运行全部用修正后的代码重新分析。）

---

## 3. maxstep 收敛（帧率、10 ns 压摆，每个方法三档）

| 方法 | maxstep | victim peak | 电荷误差 | 侵犯通道 ON_RIPPLE | 侵犯通道交替幅值 | 导通整定 | `ON_SETTLED` |
|---|---|---|---|---|---|---|---|
| traponly | 5 ns | 7.869516 µA (52.46 %) | 0.0741 % | 0.2659 µA | 0.266011 µA **YES** | 25.12 ns | 14.931906 µA |
| traponly | 1 ns | 7.873005 µA (52.49 %) | 0.0740 % | 0.2371 µA | 0.239167 µA **YES** | 25.62 ns | 14.931904–14.931906 µA |
| traponly | 0.5 ns | 7.879155 µA (52.53 %) | 0.0739 % | 0.0297 µA | 0.030889 µA YES(幅值 8.6× 缩小) | 24.99 ns | 14.931906–14.931911 µA |
| gear2only | 5 ns | 7.876419 µA (52.51 %) | 0.0725 % | 0.0000 µA | **0.000000 µA NO** | 27.53 ns | 14.931906 µA |
| gear2only | 1 ns | 7.831246 µA (52.21 %) | 0.0740 % | 0.0000 µA | 0.000000 µA NO | 25.57 ns | 14.931906 µA |
| gear2only | 0.5 ns | 7.878479 µA (52.52 %) | 0.0740 % | 0.0000 µA | 0.000000 µA NO | 24.91 ns | 14.931906 µA |

```
MAXSTEP_CONVERGENCE: PASS
```
物理量在 5 ns→0.5 ns（10 倍）之间：peak 变化 0.12 %（相对）、电荷 0.3 %（相对）、
整定 ≤2.5 ns、稳态电流 1e-6 µA 量级 —— 全部已收敛，且 1 ns→0.5 ns 基本不变，按指示不再继续缩小。
**唯一随步长显著变化的是交替幅值本身**（traponly 0.266→0.239→0.031 µA；gear2only 恒为 0.000000 µA），
这正是 trapezoidal ringing 的定义性特征：随离散步长消失，随积分方法消失。

```
ADJACENT_POINT_ALTERNATION_TRAP:   YES   （侵犯通道稳态段最高 0.4715 µA p2p，flip ratio 1.000；
                                          受害通道自身序列最大 0.0157 µA，仅 0.1 ns 那一格过阈）
ADJACENT_POINT_ALTERNATION_GEAR2:  NO    （6 个运行全部 0.000000 µA，无一例外）
```

---

## 4. 容差敏感性（只做一次确认）

`reltol` 的真实默认从运行头读回：**0.00100000**（`errpreset=moderate`）。
10× 收紧只能走 `errpreset=conservative`（→ reltol 1e-4），并显式钉住 method 以免同时换方法。

| 运行 | 头读回 | victim peak | 电荷误差 | 交替幅值 |
|---|---|---|---|---|
| traponly, reltol 1e-3（LEG A/B） | reltol=0.001 method=traponly | 7.869516 µA (52.463 %) | 0.0741 % | 0.000618 µA |
| traponly, reltol 1e-4 | `reltol=0.0001 errpreset=conservative method=traponly` | 7.870406 µA (52.469 %) | 0.0739 % | 0.012770 µA |
| gear2only, reltol 1e-3 | reltol=0.001 method=gear2only | 7.876419 µA (52.510 %) | 0.0725 % | 0.000000 µA |
| gear2only, reltol 1e-4 | `reltol=0.0001 errpreset=conservative method=gear2only` | 7.886312 µA (52.575 %) | 0.0731 % | 0.000000 µA |

```
RELTOL_SENSITIVITY: LOW
```
peak 移动 ≤0.065 % 绝对、电荷 ≤1 % 相对；`vbias` 扰动（0.0826 vs 0.0821 V）同样不动。
结论：报告的串扰不依赖求解容差。（注：conservative 还改 `lteratio` 3.5→10、`relref` sigglobal→alllocal，
所以这一格测的是"整套更严精度包"，不是单一 reltol 旋钮 —— 上面已明写。）

---

## 5. POC_STRESS_TEST：200 ns 时槽的方法交叉验证（只 10 ns 一挡）

| 方法 | victim peak | 电荷误差 | 毛刺时长 |
|---|---|---|---|
| traponly（=默认） | 7.877296 µA (52.515 %) | **3.5968 %** | 1.816e-07 s |
| gear2only | 7.857289 µA (52.382 %) | 3.5952 % | 1.702e-07 s |

```
POC_STRESS_TEST（不是系统工作周期）
```
两法一致 → 200 ns 槽里 3.6 % 的每槽电荷亏损同样是物理的，不是 ringing 假象。
它的含义是：若某天的扫描协议真的让每通道 200 ns 翻转一次，则同一结构的**时间平均**电流误差就是 3.6 %，
而不是帧率下的 0.074 %。这是"占空比/线时间"依赖，不是数值问题（题面 `NOT DEFINED`，见 §7）。

---

## 6. 拆分结论（item 8）

```
PHYSICAL_EDGE_DISTURBANCE
  幅度   2.24–8.99 µA = 14.9 %–59.9 % of I_PIXEL_ON（压摆 100→0.1 ns）
  证据   换积分方法保留（52.46 %→52.51 %；15.76 %→14.94 %）、maxstep 收敛到 0.12 %、
         容差 10× 收紧不动、紧跟邻居沿 <6 ns、与 VBIAS_SHARED(摆 0.016–0.204 V)
         和受害 vbias_ch1(摆 0.015–0.083 V) 同步
  机理   邻居 Mpass_local 沿的沟道电荷注入共享 VBIAS_SHARED；该节点直流阻抗只有 Mref 二极管
         (~1/gm) 且无保持电容 —— DATA-3 §7.3 的 Cbias bracket 已量化（10 pF 把 58.7 %→7.1 %）

NUMERICAL_RINGING  =  NUMERICAL_TRAPEZOIDAL_RINGING
  幅度   侵犯通道稳态段 ≤0.4715 µA p2p（=3.1 % of 15 µA，flip ratio 1.000）；
         受害通道 ≤0.0157 µA；随 maxstep 5ns→0.5ns 缩到 0.031 µA；gear2only 下恒 0.000000
  已剔除 不再把它算作电路 ripple，也不再算进串扰
  污染过 GLITCH_DURATION：0.1 ns 压摆下 17.09 µs（traponly）vs 0.1275 µs（gear2only），134 倍
```

```
E_TRANSIENT_RESULT: MIXED_NUMERICAL_AND_PHYSICAL
```
"混合"的具体分工：**幅度和电荷是物理的；振铃和"扰动持续时间"是数值的。**
因此 DATA-3 关于"E 的动态峰值串扰超我自定的 1 % 界"这句话，数值上站得住（不是假象），
但它当时还连带引用了一个被 ringing 放大 134 倍的持续时间，这一点现在必须更正。

---

## 7. 帧率工作点上的真实数字（item 10 要求重点报告的四项）

```
FRAME_SCALE_SETTLING:            24.9–27.5 ns（两方法、三档 maxstep 全在其中；5 ns/10 ns 代表值 25.1/25.5 ns）
FRAME_SCALE_STEADY_CURRENT:      14.931906 uA  (|I - 15 uA| = 0.454 %，与同一 VOUT 的 DC 曲线一致，
                                                22 个运行给出同一个数)
FRAME_SCALE_ELECTRICAL_CHARGE_ERROR: 0.0725 %–0.0847 %  （帧率；代表值 10 ns 压摆 0.0741 % trap / 0.0725 % gear2）
PHYSICAL_PEAK_TRANSIENT:         2.24–8.99 uA = 14.9 %–59.9 % of I_PIXEL_ON（持续时间 0.13–0.35 us/次沿）
```

`OPTICAL_MAPPING: NOT DEFINED` —— 以上只是**电荷**。本项目没有 Micro LED 电光模型、没有 `EQE(I)`、
没有光功率模型、课程也没给灰阶定义，所以**不允许**把"每帧电荷误差 0.07 %"写成"亮度误差 0.07 %"。
DATA-3 报告里那句已经删除并就地标注。

### 三类判据必须分开写（item 10）

| 类别 | 本轮用到的量 |
|---|---|
| `COURSE_REQUIREMENT` | 只有 `I_PIXEL_ON = 15 uA`（选中且点亮时的瞬时像素电流）。实测 14.931906 µA → 稳态误差 0.454 % 由 POC 带判据检查，课程本身未给容差 |
| `POC_FUNCTIONAL_CRITERION`（本工程自定、用来决定结构能不能用） | ON 曲线与被接受核心一致（实测 0.0000 %）；OFF 不破坏共享偏置；±5 % 带内必须在 ON 窗口保持 40 %；导通整定 < 帧时间 |
| `POC_CHARACTERIZATION_ONLY`（只描述特性，不当门限） | **PEAK 串扰百分比**、`Q_error`/`CHARGE_ERROR_PERCENT`、毛刺时长、`ON_RIPPLE`、`ADJACENT_POINT_ALTERNATION`、Cbias 敏感度 |

按这个分类：**峰值串扰单独不构成 blocker**（它不是课程要求，也没触发下面四条升级条件：
器件应力无越界、没有不整定（25 ns ≪ 4.88 µs ON 时间）、没有逻辑态错误、稳态电流无持续误差
—— `ON_SETTLED` 与 DC 逐位一致）。上一轮"因为一个自定 1 % 峰值界而单独宣布 E FAIL"作废。

```
CANDIDATE_E_POC_STATUS: ACCEPTABLE
```
**条件（必须随结论一起读）**：帧率 `T=9.765625 µs` 成立；如果线时间/使能翻转周期接近
200 ns 这一档（`POC_STRESS_TEST` 的实测每槽电荷亏损 **3.6 %**，属"持续电流误差"），
则该结论不成立，必须重判为 `REWORK`。课程对扫描/线时间没有任何规定
（`NOT DEFINED`），所以这个条件由评审/系统阶段决定，而不是由 agent 认定。

---

## 8. 交给评审的判定键（本轮唯一结论区）

```
E_TRANSIENT_RESULT:                     MIXED_NUMERICAL_AND_PHYSICAL
EFFECTIVE_TRANSIENT_METHOD:             traponly
METHOD_SOURCE:                          Spectre 内置 errpreset 默认 (moderate) —— deck/命令行/PDK 均未设置
TRAPONLY_PEAK:                          8.807476 / 7.869516 / 2.363705 uA  (0.1 / 10 / 100 ns)
GEAR2ONLY_PEAK:                         8.988537 / 7.876419 / 2.241635 uA
TRAPONLY_CHARGE_ERROR:                  0.0742 / 0.0741 / 0.0847 %
GEAR2ONLY_CHARGE_ERROR:                 0.0732 / 0.0725 / 0.0846 %
MAXSTEP_CONVERGENCE:                    PASS
RELTOL_SENSITIVITY:                     LOW
ADJACENT_POINT_ALTERNATION_TRAP:        YES   (≤0.4715 uA p2p, flip 1.000)
ADJACENT_POINT_ALTERNATION_GEAR2:       NO    (0.000000 uA, 6/6 运行)
FRAME_SCALE_SETTLING:                   24.9–27.5 ns
FRAME_SCALE_STEADY_CURRENT:             14.931906 uA (= DC 曲线, 0.454 % 偏低)
FRAME_SCALE_ELECTRICAL_CHARGE_ERROR:    0.0725–0.0847 %   (OPTICAL_MAPPING: NOT DEFINED)
CANDIDATE_E_POC_STATUS:                 ACCEPTABLE（条件：帧率尺度；200 ns 尺度下电荷亏损 3.6 % → REWORK）
```

---

## 9. 本轮发现的方法/工具缺陷（保留证据，不删）

| 缺陷 | 后果 | 处置 |
|---|---|---|
| `ddrv_xtalk.py` 把"邻居使能"取成受害通道自己的常开信号 | 永远报 "no edge found"，导致 item 8 要求的"与沿时间一致"无法证明，差点把物理串扰降级成未证 | 方向改正；22 个运行全部重新分析并给出 delta ≈ 5 ns |
| traponly 的样点交替被计入"毛刺持续时间" | 0.1 ns 压摆下高估 134 倍（17.09 µs vs 0.127 µs） | 新增 `ADJACENT_POINT_ALTERNATION` + 幅值/翻转率；结论按 gear2only 重述 |
| 以为可以按分析设 `reltol=` | 本机接受但忽略（1 warning，头部不变），若没读回头部就会误称"收紧了容差" | 改用 `errpreset`，并规定 `--errpreset` 必配 `--method`，每个运行读回 header |
| 把"电荷误差 <0.1 %"直接说成"亮度误差 <0.1 %" | 无电光模型的越界推断 | 已删除，标 `OPTICAL_MAPPING: NOT DEFINED` |
| 我自己启动审计时误用 `FRESH=1` | 绕过缓存重跑了一遍仿真，且两个写入者并发往同一 CSV 追加（29 行含 7 行重复） | 结果按 label 去重成 22 行（数值逐位一致，未损失证据）；脚本注释已说明缓存/FRESH 的区别 |

---

## 10. 没做什么

* **禁止 Candidate F**：本轮未实现、未测量，拓扑一字未动（评审明确要求）。
* **NO PVT / NO Monte Carlo / NO 温度扫描**：先确定 TT 瞬态真伪（评审要求）。
* 未建 schematic、未做 scan output、未做 layout、未 merge `main`。
* 旧 E 结果与 DATA-3 报告全部保留；本文只**追加**审计结论并就地标注两处必须更正的表述，
  没有重写历史数值。
* `Cbias` 敏感度沿用 DATA-3 §7.3 的 bracket 结果，本轮没有重复（它属于 testbench 参数，
  不属于 E 的设计），也没有把任何"加保持电容"的方案当作 E 的一部分。
