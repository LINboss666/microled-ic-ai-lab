# Phase DATA-3：测量方法修正（零负担取样）+ Candidate E 本地镜像栅门控

状态：`CANDIDATE_E_DC: PASS` / `CANDIDATE_E_STATIC_INDEPENDENCE: PASS` /
`CANDIDATE_E_TRANSIENT: NUMERICAL_VALIDATION_REQUIRED`
（DATA-3.5 更新。本文最初写的 `DATA_DRIVER_CANDIDATE_E: FAIL` 依赖一个**自己定义的**
`PEAK ≤ 1 %` 门限，而该门限既不是课程要求也没有先于数值真实性审计被验证 ——
瞬态部分的判定已由 `reports/data_driver_E_transient_audit.md` 接管，本文其余数值保持原样不重写。）

分支：`poc/data-driver-1ch`（未合并 `main`，未建 schematic/layout，未跑 PVT —— 见 §11）
评审输入：`15uA CASCODE CORE: KEEP / CANDIDATE D: REJECT / NEXT: LOCAL-GATE ENABLE`

---

## 1. 结论一览（评审要求的 9 行判定）

| 判定行 | 结果 | 依据（全部来自本轮新生成的证据） |
|---|---|---|
| DC REGULATION | **PASS** | E 的 ON 曲线与被接受核心逐点相同：166 个匹配点 `MAX_DEVIATION_all = 0.000000 uA = 0.0000 %`（`ddrv_curve_diff.py`） |
| OFF LEAKAGE | **PASS** | DC OFF 扫描 0→3.3 V 全程 `\|IOUT\| ≤ 0.000005 uA`（= 满量程 0.00003 %）；帧率瞬态内 OFF 段平均 0.080–0.201 uA（0.53–1.34 % of 15 uA，`POC_ASSUMPTION` 判据） |
| COMPLIANCE | **PASS** | 零负担新基准：`COMPLIANCE_1PCT 0.4600 V / 2PCT 0.2200 V / 5PCT 0.1200 V`，可用到 `V(DATA_OUT)=3.3000 V` |
| SINGLE-CHANNEL TRANSIENT | **PASS** | 导通整定 17.9–22.9 ns（帧周期）/ 18.7–20.4 ns（200 ns 周期）；三个测试电平的 `ON_SETTLED` 与 DC 曲线一致（14.8694 / 14.9319 / 14.9608 uA） |
| STATIC CHANNEL INDEPENDENCE | **PASS** | 2×2 使能矩阵：dI0 = dI1 = `0.000000 uA = 0.000 %`（判据 1 %，`POC_ASSUMPTION`） |
| PEAK DYNAMIC CROSSTALK | `POC_CHARACTERIZATION_ONLY`（数值真实性审计后重判） | 受害通道峰值偏差 2.36–8.91 uA = **15.8 %–59.4 %** of 15 uA，三种压摆率 × 两种周期全部超我自定的 1 % 界；该界**不是课程要求**，且峰值本身先要过 `reports/data_driver_E_transient_audit.md` 的方法/步长审计 |
| INTEGRATED **ELECTRICAL** CHARGE ERROR | 帧周期 <0.1 % / 200 ns 时槽 3.2–3.9 % | `CHARGE_ERROR_PERCENT` = 0.079–0.090 %（帧）；3.24–3.85 %（200 ns 周期内邻居每 200 ns 开关一次）。只声称电荷，不换算亮度：`OPTICAL_MAPPING: NOT DEFINED` |
| DEVICE STRESS | `NOMINAL_BOUNDARY / FOUNDRY_REVIEW_REQUIRED` | 全域最大 `\|VGS\| 1.8000 V`、`\|VGD\| 1.8000 V`、`\|VDS\| 2.6549 V`；工程材料中没有 foundry 可靠性限值，因此既不判 3.3 V 管击穿，也不判安全 |
| BASIC PROCESS CORNERS | **NOT RUN** | 按 item 11 规则：TT 功能集未全过（动态独立失败）→ 不跑 tt/ss/ff |

`DATA_DRIVER_CANDIDATE_E: FAIL` —— 不是电流核心失败，而是**门控的动态耦合**失败；机制已定位（§7）。
（DATA-3.5 修正：这一行当时把"我自己定的 `PEAK ≤ 1 %` 界"和"未经数值方法审计的峰值"当成了判定依据。
审计结论是峰值确实是物理的、不是 ringing，但 `PEAK` 属 `POC_CHARACTERIZATION_ONLY`，
所以正式状态改回 §0 那三行，不再由 agent 单方宣布 E 的 PASS/FAIL。）

---

## 2. item 1：把 RSEN 的测量负担从方法里去掉

### 2.1 探针语法在本机的可用性（先证明，再改方法）

`spectre/current_probe_syntax.scs`（本机 Spectre 15.1.0.284 实测）：

```
Vout (vsw 0) vsource dc=1.0
Ip1 (vsw data_out) iprobe
save Ip1:i Mout:1
```

* `Ip1 (vsw data_out) iprobe` + `save Ip1:i` → 有效，轨迹 `Ip1:i = 1.48694e-05 A`（VOUT 0.5 V）/ `1.49318e-05 A`（1.0 V）。
* `save Mout:1` → 有效，作为**独立交叉核对**（不是报告值）。
* `Ip1:current`、`Mout:drain`、`Mcas:drain` → SPECTRE-8059/8287 警告并被忽略；`save i(X)` → 致命 SFE-874。
  所以方法只用 `X:i`（iprobe）与 `X:1`（MOS 端子 1 电流）两种形式，且 `errors=0 warnings=0`。

**没有退回 10 k/1 k 采样电阻**：`ddrv_probe.py` 是唯一的电流取法入口，
`--require-probe` 让"数据文件里没有 iprobe 轨迹"直接判 FAIL，而不是静默用 `(v(vsw)-v(data_out))/RSEN`。
只有历史文件才走那条路，并在每一行输出上打 `LEGACY_BURDENED_MEASUREMENT`。

### 2.2 新基准：被接受的 cascode ON 核心，零负担重测

deck `ddrv_C_cascode_n33_tt_l2e6w2e5_iprobe.scs`（拓扑未动，只把 `Rsen` 换成 `Ip1`）：
n33 / L=2e-6 / W=2e-5 / VCAS=1.8 V / tt / `dc1 dc dev=Vout 0→3.3 V step 0.02`。

| 量 | 新（iprobe，零负担） | 旧（RSEN=10 kΩ，`LEGACY_BURDENED_MEASUREMENT`） |
|---|---|---|
| `COMPLIANCE_1PCT` | **0.4600 V** | 0.4515 V |
| `COMPLIANCE_2PCT` | **0.2200 V** | 0.2130 V |
| `COMPLIANCE_5PCT` | **0.1200 V** | 0.1161 V |
| 可达 `V(DATA_OUT)` 上限 | **3.3000 V** | 3.1505 V（差 149.5 mV = 15 uA × 10 kΩ） |
| IOUT@上限 | 14.960843 uA（−0.261 %） | 14.946478 uA（−0.357 %） |
| `IOUT_SPAN`（±5 % 拐点以上） | 14.4475…14.9608 uA = 3.42 % | 14.3948…14.9465 uA = 3.68 % |
| ROUT（上部 40 %） | 6.872e+07 Ω | 1.356e+08 Ω |
| 负担证据 | `max \|V(vsw) − V(data_out)\| = 0.000e+00 V` | 150 mV @ 15 uA |
| 观测自洽 | `\|Ip1:i − Mout:1\| ≤ 2.824e-08 A` = 满量程 0.188 % | — |

新数据是本轮以及后续所有比较的**当前基准**；旧 CSV/证据保留原样不重写（`results/data_driver_dc.csv`
= 负担版，`results/data_driver_dc_iprobe.csv` = 零负担版）。

两点必须讲清：

1. 对 **DC** 而言，负担的主要代价不是拐点数字（0.4515→0.4600 V，差 8.5 mV，且旧值来自非网格点），
   而是**输出可达范围被电阻吃掉 149.5 mV**，以及旧报告里 3.1505 V 这一"上限"其实是采样电阻的压降。
2. 对 **瞬态** 而言，负担更糟：10 kΩ 串在开关回路里同时 (a) 让 `V(DATA_OUT)` 不再是测试台设定的值、
   (b) 阻尼了耦合。上一轮 Candidate D 的 19.4 % 动态串扰是在有阻尼的条件下测的，
   本轮零负担复测同一类结构得到 15.8–59.4 % —— **旧方法的串扰是偏小的**，这一条影响历史结论的可比性，
   已在 §9 作为已知偏差记录（D 的 REJECT 结论不受影响，因为它同时还败在 3.30 V 的 \|VGD\| 上）。

### 2.3 顺带发现：这个 PDK 的 n33 模型有真实的栅/体直流电流

诊断 deck `spectre/diag/ddrv_diag_currents_semantics.scs`（保存全部端子电流）在 ON 稳态点实测：

```
Ip1:i       +1.38608446e-05      Mcas:1 (D) +1.38280415e-05
Mcas:2 (G)  -8.62954383e-07      Mcas:3 (S) -1.50985325e-05
Mout:1 (D)  +1.51015387e-05      Mout:2 (G) -4.37950738e-08
```

即 `Mcas` 的**栅端子流出 0.86 uA**、体端子流入约 2.1 uA，而数据线电流是 13.86 uA。
意义：`Ip1:i`（像素实际吸收的支路电流）与 `Mout:1`（管子 drain 电流）在动态里可以差 µA 量级，
两者不是同一个量。本轮报告一律以 **iprobe 的支路电流 = 像素电流** 为准，
`Mout:1` 只在 DC 用作 0.19 % 级别的方法自洽核对；瞬态里两者的差被明确标注为内部节点位移电流
（`ddrv_probe.py` 的 `PROBE_CROSSCHECK: note`），不当作 bug、也不当作错误。
模型为什么带栅流属于 PDK 侧问题，列入 §9 待查项。

---

## 3. Candidate E 拓扑（由 netlist 现场推导，非手抄）

deck：`spectre/generated/ddrv_E_local_gate_n33_tt_l2e6w2e5_ch1_iprobe_E_sel_on.scs`（1 通道，选定尺寸）

```
        vdd ──Iref(理想 15u, POC_ASSUMPTION)──┐
                                              Mref (vbias/vbias, n33 2u/20u)   ← SHARED BIAS
                                               │                              永远导通
                        VBIAS_SHARED ──────────┘
                             │  Mpass_local (D=vbias, G=data_en, S=B=vbias_ch)
                             ▼
                    vbias_ch ── Mout (n33 2u/20u) ── vss        ← 每通道 2 只核心管
                             ▲
                    vbias_ch ── Mbleed_local (G=data_en_b) ── vss
   DATA_OUT ── Mcas (G=vcas=1.8 V 理想源) ── node_m ── Mout
```

* 评审点名的性质被**实测**而不是被声明：OFF 时 `vbias_ch = 0.000000 V` 而 `VBIAS_SHARED` 保持
  `0.884277 V` —— 本通道的 bleed 碰不到共享节点。
* `vss` 显式接到 Spectre 参考节点 0（AGENTS item 19）；`Vf / VLED`：`NOT DEFINED`，
  所以 `V(DATA_OUT)` 只是被扫的测试变量，没有伪造 LED 模型（`ENGINEERING_TOPOLOGY_CHOICE`：低侧电流吸入）。
* 每通道 4 只 MOS（Mout/Mcas/Mpass_local/Mbleed_local）+ 共享 `Mref`；本轮不含反相器/latch，
  `DATA_EN / DATA_EN_B` 由理想互补源给出（`POC_ASSUMPTION`）。

---

## 4. item 5：单通道 DC —— 门控对电流核心零扰动

`results/data_driver_E_dc.csv` + `results/data_driver_curve_diff.csv`（都是零负担 iprobe）：

| 组态 | 匹配点 | `MAX_DEVIATION_all` | `COMPLIANCE_1PCT` | `vbias_ch` 相对 `VBIAS_SHARED` |
|---|---|---|---|---|
| E n33 选定 5u/2u，ON | 166 | **0.000000 uA = 0.0000 %** | 0.4600 V（与核心同） | 0.884261 V，最差压降 **0.000000 V** |
| E n33 默认 20u/2u，ON | 166 | 0.000000 uA = 0.0000 % | 0.4600 V | 同上 |
| E n18 默认 20u/2u，ON | 166 | 0.000003 uA = 0.0000 %（3 nA） | 0.4600 V | 同上 |
| E 任一，OFF | 166 | — | NOT_FOUND（正确：OFF 不该有电流） | `vbias_ch = 0.000000 V`，泄漏 ≤ 5 pA |

结论：**DC 无法区分 n18 与 n33，也无法区分尺寸** —— 门控器件在直流下只是"传到 / 不传"，
所以 item 3 的家族选择必须（也确实）落在应力、泄漏与速度上，而不是靠名字猜。

---

## 5. item 3：Mpass/Mbleed 家族与尺寸 —— 全部由测量决定

只允许动 `Mpass_local / Mbleed_local` 的 W/L；Mout/Mcas 保持被接受的 2u/20u n33。
起点是合法的小/中尺寸（L=1u 用于 n18，L=2u 用于 n33 —— 与已验证的 n33 核心同 L，避免未证实的最小长度）。

### 5.1 家族（默认 W 20u/2u，VOUT=3.3 V，T=200 ns，1 ns 边沿，`ms1ns`）

| 家族 | 导通整定 | `ON_SETTLED` | 采样纹波 | OFF 泄漏 | **VBIAS_SHARED 偏移** | 判定 |
|---|---|---|---|---|---|---|
| n18 | 11.3 ns | 14.960843 uA（0.26 %） | 1.62 uA | 25.9 nA | 0.515…0.929 V = **±0.369 V（20.5 %）** | **1/4 ON 窗口整定失败 → rc=1** |
| n33 | 15.1 ns | 14.960851 uA（0.26 %） | 0.72 uA | 30.3 nA | 0.724…0.954 V = **±0.161 V（8.9 %）** | 全部 rc=0 |

n18 被否，理由是可测的两条：对共享偏置的扰动是 n33 的 2.3 倍（薄 oxide → 单位面积栅电容更大 →
电荷注入更多），并且 3.3 V 测试点上 4 个 ON 窗口里有 1 个不能满足 ±5 % 保持判据。
它的直流传递能力、泄漏（10.6–26.5 nA，甚至更低）都不差 —— 所以这不是"低压管不行"，
而是**在同一 1.8 V 使能摆幅下 n18 注入更多沟道电荷**。反过来说，如果默认按名字选 n18（"1.8 V 域就用 1.8 V 管"）
会得到一个更差的通道，这正是评审要求"不按名称猜"的那一类错误。

### 5.2 尺寸扫描（n33，L=2u，VOUT=3.3 V，T=200 ns；`results/data_driver_E_gateSweep.csv`）

| Wpass / Wbleed | 导通整定 | `ON_SETTLED` 偏差 | PEAK | OFF 泄漏 | VBIAS_SHARED 偏移 |
|---|---|---|---|---|---|
| 2u / 2u | 30.8 ns | 0.0008 % | 18.3 uA | 168 nA | ±0.206 V |
| **5u / 2u（选定）** | **20.4 ns** | **0.0000 %** | **17.8 uA** | 227 nA | **±0.186 V** |
| 20u / 2u | 14.7 ns | 0.0000 % | 24.6 uA | 65 nA | ±0.258 V（上冲 1.018 V） |
| 2u / 20u | 37.2 ns | 0.0000 % | **49.7 uA** | **1353 nA** | ±0.495 V（`vbias_ch` 冲到 −0.23 V） |
| 5u / 20u | 26.7 ns | 0.0000 % | 42.2 uA | 532 nA | ±0.474 V |
| 20u / 20u | 20.5 ns | 0.0000 % | 24.3 uA | 56 nA | ±0.253 V |

选定 `n33 / L=2u / Wpass=5u / Wbleed=2u` 的理由（事先声明的判据顺序：偏置扰动 → 导通整定 → ON 电平偏差 → OFF 泄漏）：

* 共享偏置扰动最小档之一（±0.186 V，且过冲只到 0.915 V，不像 20u 那样上冲 1.018 V）；
* ON 电平与 DC 完全一致，PEAK  overshoot 最小（17.8 uA）；
* 代价：稳态 OFF 泄漏 0.08–0.20 uA，比 20u/2u 的 0.03–0.07 uA 大 3–6 倍。两者都远小于 15 uA，
  但**这个反向趋势没有被解释**（§9 第 3 条），因此记为已知未解项而不是"设计优点"。
* `Wbleed=20u` 明确被否：PEAK 49.7 uA、OFF 泄漏 1.35 uA（= 8.9 % of 15 uA）、并把 `vbias_ch` 打到 −0.23 V
  （衬结正偏风险）。

---

## 6. item 9：瞬态测试点全部取自新的零负担 DC 曲线

测试点选择（`ENGINEERING_DERIVATION`）：`COMPLIANCE_1PCT = 0.4600 V` → "刚好高于 1 % 拐点"取 **0.50 V**；
恒流区中段取 **1.20 V**；合法高点取扫描上限 **3.30 V**（零负担下真的可达，负担版只能到 3.1505 V）。
旧的 RSEN 时代 0.5 V 点**没有被继承**：同一个 0.5 V 在旧方法下意味着 `V(vsw)=0.65 V`。

`results/data_driver_transient_iprobe.csv`（37 次重分析全部用同一套修正后的度量；`iout_method=iprobe`）：

| 案例 | 周期 | VOUT | 导通整定 | 关断 | `ON_SETTLED` | 采样纹波 | OFF 泄漏 | VBIAS_SHARED |
|---|---|---|---|---|---|---|---|---|
| 核心 C_cascode | 200 ns | 0.50 / 1.20 / 3.30 | 30.5 / 31.5 / 31.1 ns | 1.5–7.8 ns | 14.8694 / 14.9319 / 14.9608 uA | ≤0.88 uA | 27.9–81.3 nA | −0.030…0.884 V（**被 bleed 放空**） |
| 核心 C_cascode | 9.765625 µs | 0.50 / 1.20 / 3.30 | 29.4 / 41.0 / 33.0 ns | 1.6–10.2 ns | 14.8694 / 14.9319 / 14.9608 uA | ≤1.30 uA | 30.6–79.5 nA | −0.029…0.884 V |
| **E 选定 5u/2u** | 200 ns | 0.50 / 1.20 / 3.30 | 18.7 / 20.4 / 20.4 ns | 2.7–9.5 ns | 14.8694 / 14.9319 / 14.9608 uA | ≤0.44 uA | 84–238 nA | 0.693…0.916 V（±0.19 V） |
| **E 选定 5u/2u** | 9.765625 µs | 0.50 / 1.20 / 3.30 | 17.9 / 22.9 / 22.6 ns | 2.7–8.9 ns | 14.8694 / 14.9320 / 14.9608 uA | ≤0.74 uA | 79.7–201 nA | 0.693…0.914 V（±0.19 V） |

读数：

* E 的**导通整定比被接受核心更快**（18–23 ns vs 29–41 ns），且 `vbias_ch` 在 ON 精确到达 `VBIAS_SHARED`、
  在 OFF 精确到 0 —— 门控本身是干净的。
* E 的 OFF 泄漏（帧率 0.08–0.20 uA）比核心（0.03–0.08 uA）大一个数量级；DC 下两者都是 pA 级，
  所以这是**动态/尺寸相关**的泄漏，未被完全解释（§9）。
* 核心在最高测试点（3.30 V）帧周期下 `ON_SETTLED` 为 14.9403–14.9626 uA，而 E 是 14.9608 uA ——
  E 在这一点上更贴近 DC；这条也写入"核心自身的已知行为"，不当作 E 的功劳。

### 6.1 方法修正（这是本轮第二个测量问题，比电路结论更重要）

第一次瞬态重跑时 `ON_SETTLED` 随 `maxstep` 摆动（20 ns→14.881、5 ns→14.961、1 ns→15.179 uA），
而 DC 同一工作点固定是 14.9608 uA。查下来的原因是**两个方法缺陷**，都不是电路现象：

1. `tran tran stop= step=` 里的 `step` 是**打印步长**，求解器上限 `maxstep` 没写时本机自动取 18 ns
   —— 200 ns 周期里每个使能窗口只有约 5 个采样点。已在 `ddrv_gen.py` 显式给
   `maxstep=min(period/200, 5 ns)`，并把有效值写进 deck 文件名（`_ms1ns` / `_ms5ns`），
   历史 deck 不被覆盖。`--maxstep` 可覆盖，收敛性表见 `results/data_driver_E_gateSweep.csv` 同批证据。
2. `method=traponly` 在步长接近局部栅节点 RC 时会让相邻采样**围绕真值交替**
   （实测 14.7329 / 15.1884 uA 交替，节点电压却完全稳定），此时**中位数只取到交替的一个分支**。
   度量改成"窗口内后 30 % 的**均值** + 报告 `ON_RIPPLE` 峰峰值"，并且**掐掉窗口两端采样**
   （落在边沿上的那一点会把 30 点的均值带偏 ~10 %，曾把 0.03 uA 的 OFF 泄漏读成 0.63 uA）。

修正后 37 个瞬态文件用同一把尺重算（`scripts/ddrv_reanalyze.sh`，不重新仿真）：
`ON_SETTLED` 与 DC 曲线在几乎每个案例上对齐到 <10 nA。三档 maxstep 的收敛复核：14.881 / 14.961 / 14.961 uA
（20 ns / 5 ns / 1 ns），即 5 ns 已收敛，20 ns 未收敛 —— 之前那一类结论里凡是用 18 ns 步长测的动态量都不可复现。

### 6.2 使能压摆与帧周期的物理冲突（已被硬闸拦下）

`slew=100 ns` 在 `T=200 ns` 时 Spectre 报
`WARNING (CMI-2210): Period is smaller than rise+width+fall. It is reset to rise+width+fall.`
—— 即仿真悄悄把周期改成 300 ns，测的就不是 200 ns 时槽了。
`ddrv_gen.pulse_problem()` 现在直接拒绝这种组合（`DDRV_GEN: REFUSED`），
100 ns 压摆只在帧周期 9.765625 µs 下测。评审要求的三种压摆率因此覆盖为：
1 ns / 10 ns 两种周期都测，100 ns 只在帧周期测（并给出拒绝理由，而不是挑一个"好看"的压摆）。

---

## 7. item 6/7：两通道独立性与电荷型串扰

deck：2 通道共享 `Mref + VBIAS_SHARED`，各自 `vbias_ch / Mpass / Mbleed / DATA_EN / DATA_EN_B`，
两通道 `V(DATA_OUT)` 都固定在 1.20 V。`results/data_driver_xtalk_E_local_gate.csv`、
证据 `results/evidence/ddrv_E_local_gate_*.txt`。

### 7.1 静态 2×2 使能矩阵 —— PASS（0.000 %）

| EN0,EN1 | I0 | I1 |
|---|---|---|
| 0,0 | 0.000001 uA | 0.000001 uA |
| 0,1 | 0.000001 uA | 14.931906 uA |
| 1,0 | 14.931906 uA | 0.000001 uA |
| 1,1 | 14.931906 uA | 14.931906 uA |

`dI1 = |I1(1,1) − I1(0,1)| = 0.000000 uA = 0.000 %`；`dI0 = 0.000000 uA = 0.000 %`。
静态隔离是**完全**的：共享节点在直流上被 Mref 钉住，通道互不影响。

### 7.2 动态：邻居开关时的受害通道（基线取同一 deck 的静态 (1,1) 运行）

| 周期 | 压摆 | 峰值串扰 | 峰值 % | `Q_error` | 电荷 % | >±1 % 毛刺时长 | 判定 |
|---|---|---|---|---|---|---|---|
| 200 ns | 0.1 ns | −8.91 uA | **59.4 %** | −3.89e-13 C | 3.85 % | 330 ns（49 %） | FAIL |
| 200 ns | 10 ns | −7.88 uA | **52.5 %** | −3.88e-13 C | 3.83 % | 182 ns（27 %） | FAIL |
| 200 ns | 100 ns | — | — | — | — | — | REFUSED（§6.2） |
| 9.77 µs | 0.1 ns | −8.81 uA | **58.7 %** | −3.91e-13 C | **0.079 %** | 17.1 µs（52 %） | FAIL(峰值)/PASS(电荷) |
| 9.77 µs | 10 ns | −7.87 uA | **52.5 %** | −3.91e-13 C | **0.079 %** | 152 ns（0.46 %） | FAIL(峰值)/PASS(电荷) |
| 9.77 µs | 100 ns | −2.36 uA | **15.8 %** | −4.46e-13 C | **0.090 %** | 350 ns（1.06 %） | FAIL(峰值)/PASS(电荷) |

`Q_error = ∫(I_victim − I_baseline)dt`、`CHARGE_ERROR_PERCENT = |Q_error|/(15 uA × 观测窗)`、
毛刺时长 = `\|I−I_baseline\|` 超 ±1 % 的相邻采样区间总长（`ddrv_xtalk.py --selftest` 用已知答案的
夹具校过这四式的算术）。

**读法（DATA-3.5 修正）**：扰动脉冲本身几乎是恒定电荷 —— 三种压摆下 `Q_error` 都是 −3.9e-13 C 量级；
压摆从 0.1 ns 放到 100 ns 把毛刺从 17.1 µs 收到 350 ns、把峰值从 58.7 % 压到 15.8 %。
所以每帧的 **`ELECTRICAL_CHARGE_ERROR`** 很小（<0.1 %）。

**这句原来写的"即灰阶亮度误差 <0.1 %"已删除**：本项目没有 Micro LED 电光模型、没有 `EQE(I)`、
没有光功率模型，也没有课程给出的灰阶定义 —— `OPTICAL_MAPPING: NOT DEFINED`。
电流积分只能声称是电流量；把它当成亮度需要一条未被给出的转移特性。

**峰值 vs 电荷两个量给出相反结论**（峰值超我自定的 1 % 界，电荷不超），这一点由 DATA-3.5 处理：
`PEAK` 属于 `POC_CHARACTERIZATION_ONLY`，不是 `COURSE_REQUIREMENT`，且它当时还没先通过
"是不是数值假象"的审计（见 `reports/data_driver_E_transient_audit.md`）。


### 7.3 耦合路径定位（item 8 之外的额外实验，带明确标签）

共享偏置节点的偏移与受害通道峰值误差一起看：

| 观测 | 值 |
|---|---|
| 邻居通道自己的 `TURN_ON_SETTLING` | 24.9 / 25.1 / 55.9 ns（0.1 / 10 / 100 ns 压摆） |
| `VBIAS_SHARED` 偏移（同一运行） | ±0.123 V（6.8 %）/ ±0.078 V（4.3 %）/ ±0.016 V（0.9 %） |
| 受害通道峰值误差 | 58.7 % / 52.5 % / 15.8 % |
| 受害通道 `vbias_ch1` | 与 `VBIAS_SHARED` 同步跌落（导通时 Mpass 是低阻通路） |

三条曲线同向：**串扰是通过共享偏置节点传播的**，不是通过衬底/布线（本 testbench 里根本没有建模）。
进一步用偏置保持电容做 bracket（`scripts/ddrv_cbias_bracket.sh`，`Cbias` 明确标注
**不属于 Candidate E**，只是替真实偏置缓冲的输出级说话）：

| Cbias @ VBIAS_SHARED | 共享节点偏移 | 受害通道峰值 | 每窗电荷误差 |
|---|---|---|---|
| 无（理想 15 uA 灌二极管） | ±0.123 V | 58.7 % | 3.85 % |
| 1 pF | ±0.037 V | 29.4 % | 3.24 % |
| 10 pF | ±0.005 V | **7.1 %** | 2.97 % |

结论分两半，且必须这样写：

* **峰值串扰** 由偏置网络动态阻抗主导：26× 更硬的偏置 → 峰值降 8×（58.7 % → 7.1 %）。
  也就是说 E 的"失败"有相当一部分不是通道拓扑的错，而是本轮被有意留为理想的偏置产生器。
* **每帧电荷亏损** 几乎不随偏置硬化而消失（3.85 % → 2.97 %），说明还剩一条与偏置阻抗无关的机制
  （候选是 pass/bleed 器件在 DATA_EN 边沿注入到 `vbias_ch` 的电荷 —— 观测到 `vbias_ch` 需要 >100 ns 才恢复）。
  这一条我没有在本轮关闭，列为 §9 未解项与评审问题。

---

## 8. item 8：Candidate E 的器件应力

`reports/ddrv_E_stress_dc_on.md`、`..._dc_off.md`、`..._tran_frame.md`（由 `ddrv_topology.py --stress`
从 deck+psf 现场推导，非手抄）。全域最大绝对值：

| 器件 | 角色 | `\|VGS\|max` | `\|VGD\|max` | `\|VDS\|max` |
|---|---|---|---|---|
| `Mout` (n33 2u/20u) | 像素电流 | 0.8843 V | 1.1813 V | 1.3467 V |
| `Mcas` (n33 2u/20u) | 共源共栅 | 1.1549 V | 1.5000 V | **2.6549 V** |
| `Mref` (n33 2u/20u) | 共享偏置（二极管） | 0.9124 V | 0.0000 V | 0.9124 V |
| `Mpass_local` (n33 2u/5u) | 本地栅传递 | 1.4102 V | 1.1008 V | 0.8843 V |
| `Mbleed_local` (n33 2u/2u) | 本地栅泄放 | **1.8000 V** | **1.8000 V** | 0.8843 V |

判定用 `NOMINAL_BOUNDARY / FOUNDRY_REVIEW_REQUIRED`：

* 没有把"n33 属于 3.3 V 家族"当作"3.3 V 绝对上限"。上面所有端子电压都 ≤ 2.655 V，
  在 3.3 V 域内、也在 1.8 V 域的 VDD 之内（`Mbleed_local` 的 1.80 V 恰好等于 VDD，是给真实
  1.8 V 使能信号的正常摆幅）。
* 工程材料里没有 foundry 给出的可靠性限值（栅氧、TDDB、VDS 上限），因此**不作任何 oxide 失效或
  安全裕量的断言**；需要 foundry 侧确认的项目：`Mcas` 在 `V(DATA_OUT)=3.3 V` 时的 2.655 V `VDS`
  与 1.500 V `VGD`，以及 `Mbleed_local` 1.80 V 栅应力在真实 384 通道占空下的寿命含义。
* `Mpass_local` 的 body 与 source 同接 `vbias_ch`（`VBS = 0`）。测到的唯一负摆是选定尺寸下 2 通道
  帧运行中的 `vbias_ch = −0.0012 V`（约 1.2 mV 结正偏）；`Wbleed=20u` 的组态会到 −0.23 V，已被否决。

---

## 9. 已知失败、未解观察与工具缺陷（全部保留证据，不删）

**已知失败**

1. ~~`PEAK DYNAMIC CROSSTALK` 超判据（§7.2 全部 6 个组合）~~ → **DATA-3.5 重判**：峰值 14.9–59.9 % 是
   **物理的**（换 gear2only、maxstep 5→0.5 ns、reltol 收紧 10× 都保留），但它属
   `POC_CHARACTERIZATION_ONLY`，不是课程要求，且当时未做该方法审计 —— 见
   `reports/data_driver_E_transient_audit.md`。同一条里"毛刺持续 17.1 µs"是 traponly 振铃造成的，
   gear2only 下是 0.127 µs（差 134 倍）。
2. 200 ns 时槽下 `CHARGE_ERROR_PERCENT` 3.6 %（两法一致，物理）；帧率下 0.072–0.085 %。
   只说电荷，不换算亮度（`OPTICAL_MAPPING: NOT DEFINED`）。
3. `E n18` 家族在 3.30 V 帧下 4 个 ON 窗口有 1 个不满足 ±5 % 保持（`rc=1`）—— 家族被否的实测依据之一。
4. 3 个历史 deck 在 `maxstep` 未约束时测出的整定/纹波结论不可复现（§6.1）；`core_T2e7vout3.30`
   （18 ns 步长）报 FAIL 而 1 ns 步长同一电路报 PASS，说明旧 FAIL 是方法产物。

**未解观察（不写成结论）**

1. 该 PDK 的 n33 模型在 ON 稳态带 0.86 uA 级 `Mcas` 栅电流与 ~2.1 uA 体电流（§2.3）。原因未查（PDK 侧）。
2. `traponly` 在 5 ns 步长下仍有 0.4–1.6 uA 峰峰采样交替，来源未完全定位。
3. `Mpass` 越大 → 稳态 OFF 泄漏越小（0.20 → 0.03 uA），与"更大 pass 器件注入更多电荷"的直觉相反，机制未解释。
4. 每帧电荷亏损对偏置硬化不敏感（3.85 → 2.97 %），剩余机制未关闭（§7.3）。

**本轮发现并修掉的工具缺陷（每个都有对应改动）**

| 缺陷 | 后果 | 修法 |
|---|---|---|
| `ddrv_tran.parse()` 只从 `PROP(` 声明收集轨迹名，而本机瞬态 TRACE 写作 `"Ip1:i" "A"` | 明明有 iprobe 轨迹却报"no iprobe trace"，`--require-probe` 把 37 个运行全判 FAIL | 数据行里出现的键也算轨迹名 |
| `ddrv_tran.py` 写 CSV 时格式串占位符少于参数（vbias 三列被静默丢弃） | `results/data_driver_transient.csv` 的 11 列表头与 14 列意图不一致，历史文件的 vbias 列实际缺失 | 21 列表头与占位符对齐，并保留旧文件不动 |
| `tran` 未给 `maxstep` | 200 ns 周期每窗口约 5 个采样点，整定与"是否落在带内"不可复现 | 显式 `maxstep`，值进文件名；三档收敛复核 |
| 尾部度量用中位数且不掐边沿 | 交替采样读到一半分支；边沿采样把均值带偏 ~10 % | 均值 + `ON_RIPPLE` + 窗口两端保护带 |
| `ddrv_xtalk.py` 重构后残留 `dev` 引用 | 分析崩溃、静态矩阵读空、误报 `STATIC_INDEPENDENCE: FAIL` | 删除死行；`--selftest` 已知答案夹具 |
| `ddrv_twochan.sh` 忘记 `--vout1` | 参考 deck 的受害通道在 0 V，得出 100 % 假串扰 | 加 `--vout1`，并在 `ddrv_xtalk.py` 里硬性比较两次运行的 `V(vsw)`（差 >1 mV 直接 FAIL） |
| `ddrv_topology.py`/`make_review_bundle.py` 用 dict comprehension | guest 的 Python 2.6 语法错误，应力表出不来 | 2.6 兼容写法（本轮改 `ddrv_topology.py` 两处；bundle 只在 Windows/Py3 跑，暂不改） |
| `C_cascode` 的 `--probe iprobe` 走文本替换 | 若替换失败会静默回到负担法 | `--require-probe` + `PROBE_BURDEN` 行实测 `V(vsw)−V(data_out)=0` |

---

## 10. Git 与产物

* 提交 1：`test: remove sense-resistor burden from data-driver characterization`
  （`ddrv_probe.py`、`spectre/current_probe_syntax.scs`、characterize/tran/xtalk/dump/curve_diff/reanalyze、
  新 DC/瞬态 CSV、§2 数字）
* 提交 2：`rework: isolate per-channel mirror gate from shared bias`
  （`ddrv_gen.py` 的 `build_E`/pulse guard/`--cbias`、E 的 deck 与证据、两通道与 bracket 脚本、
  本报告与三份应力表）
* `main` 未动；C（被接受核心）与 D（REJECT）的历史结果与报告全部保留，未改写电路或数值。
* E 的全部 deck 由 `scripts/ddrv_gen.py` 决定性地再生：每次运行的候选、模型、L/W、探针方式、门控家族与
  尺寸、周期、`V(DATA_OUT)`、压摆率和 `maxstep` 都编在证据文件名里（例如
  `..._ch1_iprobe_E_sel_on`、`..._T2e7vout3.30_ms1ns`、`..._S_5e-6_2e-6...`）。仓库里只提交
  选定配置的三份 deck；其余以再生命令 + 证据为准，避免把 100 多个派生文件当成果。

产物清单：`results/data_driver_dc_iprobe.csv`、`results/data_driver_E_dc.csv`、
`results/data_driver_transient_iprobe.csv`（37 行，全部 `iout_method=iprobe`）、
`results/data_driver_E_gateSweep.csv`、`results/data_driver_curve_diff.csv`、
`results/data_driver_xtalk_E_local_gate.csv`、`results/data_driver_xtalk_cbias_bracket.csv`、
`results/evidence/reanal_*.txt`（37）、`results/evidence/ddrv_E_*.txt`、
`reports/ddrv_E_stress_dc_on.md`、`reports/ddrv_E_stress_dc_off.md`、`reports/ddrv_E_stress_tran_frame.md`。

---

## 11. 没做什么（停在人工闸门前）

* **PVT 未跑**：item 11 的规则是 TT 功能集全过才跑 corner，动态独立未过 → 不跑，也不引用旧 corner 数字为 E 背书。
* **Candidate F 未实现/未测**（偏离评审的"E 与 F 都失败才判 NEEDS_REVIEW"，此处显式声明）：
  F 的关键元件是像素通路里的大尺寸串联开关，而该结构的直流误差在 DATA-1 已经量过
  （`A_series` 同拓扑、开关管与核心同尺寸：ON 电流 **−4.07 %**、±1 % 拐点抬到 **1.3574 V**、
  4/4 个 ON 窗口整定 `NOT_FOUND`、冲击 **80.7 µA** —— 见 `reports/data_driver_1ch_result.md` 的候选对比表）；
  同时 §7.3 显示 E 的动态失败主要由**共享偏置阻抗**决定，F 若用同一理想偏置支路，
  其"串扰≈0"只会来自理想电压源零阻抗这一 testbench 假设，而不是设计。
  要不要在这种前提下花一轮做 F，请评审定；需要的话我可以在下一次授权后按
  "固定 VBIAS + 固定 VCAS + 独立优化 W 的本地串联开关"补测，并把 `R_on×I` 扫描一并给出。
* 未做 schematic、layout、DRC/LVS/PEX、384 通道、TCON、reset/BLANK/level shifter。
* 偏置产生器（`VBIAS_SHARED` 的真实驱动与保持电容）仍属下一阶段范围外；本轮只允许它作为
  被标注的 testbench bracket 出现（§7.3）。
* `IDENTITY_PRIVACY_CLEANUP = PENDING_OWNER_ACCEPTED`（9 个被替换的 commit 对象仍被 GitHub 服务）
  与 IC 设计无关，保持原状态。

---

## 12. 给评审的 4 个问题

1. **判据**：两通道动态串扰同时有"峰值"和"每帧电荷"两个量，且它们给出相反的结论
   （峰值 15.8–59.4 % vs 每帧电荷 0.079–0.090 %）。Micro LED 的灰阶定义如果是"选中期间的时间平均电流"，
   1 % 判据应该绑在哪个量上？（现在的 POC 判据把两个都绑成 1 %，于是永远自相矛盾。）
   DATA-3.5 的处理：按评审 item 10，`PEAK` 归 `POC_CHARACTERIZATION_ONLY`，不再单独据此判 E FAIL；
   但"正式判据应该绑哪个量"仍然是评审的决定，不由 agent 补一个数就当规定。

2. **偏置网络归属**：`Cbias` 实验显示峰值串扰主要由共享偏置的动态阻抗决定（±0.123 → ±0.005 V，
   峰值 58.7 → 7.1 %）。是否允许把"共享偏置缓冲/保持电容"纳入下一阶段的设计范围（它会改变每通道面积预算），
   还是必须让通道本身对任意偏置阻抗免疫？
3. **F 的必要性**：在 A_series 已测到串联开关 `I×R_on` 误差、且 E 的失败已被部分归因到偏置网络的前提下，
   还要不要按原计划实现并测 F？
4. **未解的泄漏趋势**：`Mpass` 更大 → 稳态 OFF 泄漏更小（0.20 → 0.03 uA），与电荷注入直觉相反，
   且每帧电荷亏损不随偏置硬化消失（3.85 → 2.97 %）。是否接受"机制未关闭但量级 ≤1.4 % of I_PIXEL_ON"
   作为 POC 阶段的收尾条件？

---

## 13. 来源标签（本轮用到的全部标签）

| 标签 | 用在哪 |
|---|---|
| `COURSE_REQUIREMENT` | `I_PIXEL_ON = 15 uA`（瞬时像素电流，唯一正式电流指标） |
| `ENGINEERING_TOPOLOGY_CHOICE` | 低侧电流吸入；E 的本地栅节点 + 传递/泄放对 |
| `ENGINEERING_DERIVATION` | 三个瞬态测试电压的选点（0.50/1.20/3.30 V 来自新 ±1 % 拐点）、`maxstep` 上限、尺寸选择顺序 |
| `POC_ASSUMPTION` | ±1/2/5 % 判据、1 % 串扰判据、`VDD=1.8 V`、`VCAS=1.8 V` 理想源、`DATA_EN/DATA_EN_B` 理想互补源、15 uA 理想参考、扫描步长、观测窗后 30 %、`Cbias` bracket |
| `NOT DEFINED` | `Vf`、`VLED`、灰阶/帧率协议、消隐、数据锁存与移位协议、foundry 可靠性限值 |

`GPT6_LEGACY_PROPOSAL` 本轮没有新增使用；被接受核心的电路与数值一律未动。
