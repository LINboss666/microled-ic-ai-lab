# Phase DATA-4：Candidate E 最终冻结 + BASIC_PROCESS_CORNER_PROBE

评审决定：`REVIEW DECISION: GO` / `CANDIDATE_E: ACCEPTABLE_FOR_COURSE_POC`，
适用范围 `FRAME-SCALE POC: T_COLUMN = 9.765625 us`。
本轮不改电路、不重新 sizing、不跑 PVT signoff，只在冻结单元上做三个工艺 section 的基本探针。

> **DATA-4.5 撤回说明（措辞与状态更正，数据未动）**：本文件的 `FROZEN_FOR_SCHEMATIC` 依赖
> `Mpass_local (vbias data_en vbias_ch vbias_ch) n33` 这条连接。器件可实现性审计判定普通
> `n33` 的体端不是独立节点（见 `reports/data_driver_n33_body_audit.md`），因此冻结状态撤回为
> `BLOCKED_PENDING_BODY_DECISION`。下面所有实测数值保持原样，只是不再等于"可以直接画图"。
>
> **DATA-5 更新**：该 blocker 已按独立评审的决定解除——`Mpass_local` 换成真实存在的隔离主名
> `smic18mmrf/n33_dnw_4t_ckt`，冻结恢复，现行定义见 `reports/data_driver_E_dnw_mpass.md`。
> 本文件 §1–§4 描述的那份"体端接 vbias_ch 的 n33"网表**不是**可制造的定义，只作为历史测量保留。

```
DATA_DRIVER_1CH:                 FROZEN_FOR_SCHEMATIC   (现行实现 = Candidate E-DNW，见 reports/data_driver_E_dnw_mpass.md；DATA-4.5 曾撤回为 BLOCKED_PENDING_BODY_DECISION)
ACCEPTED_BY_REVIEW:              GO / ACCEPTED_FOR_COURSE_POC  (电路版本 = 4b3e571，见下方 REVIEW_HEAD_SHA)
TOPOLOGY:                        Candidate E (local mirror-gate enable)
REVIEW_HEAD_SHA:                 4b3e5710cd439fe04bac95d816653c8d3f308dfd = 被独立 review 接受的电路版本
                                 (Candidate E-DNW，Mpass = n33_dnw_4t_ckt；本文件与其后的 commit 只改文字，
                                 不改电路、W/L、testbench 或任何结果)
BASIC_PROCESS_CORNER_PROBE:      PASS
FULL_PVT_SIGNOFF:                NO
PHYSICAL_DYNAMIC_CROSSTALK:      PRESENT
NUMERICAL_TRAPEZOIDAL_RINGING:   IDENTIFIED
FRAME_SCALE_POC:                 PASS
200NS_STRESS_TEST:               REWORK_REQUIRED_IF_FUTURE_SYSTEM_USES_THIS_TIMESCALE
NEXT:                            VIRTUOSO_SCHEMATIC
```

---

## 1. 冻结内容（一字未动）

`spectre/generated/ddrv_E_local_gate_n33_tt_l2e6w2e5_ch1_iprobe_tt_on.scs` 的器件行就是全部定义：

| 实例 | 角色 | 模型 | L | W |
|---|---|---|---|---|
| `Mout` | 像素电流管 | n33 | 2e-6 | 2e-5 |
| `Mcas` | 共源共栅（定 compliance 拐点） | n33 | 2e-6 | 2e-5 |
| `Mref` | 共享偏置二极管（永不被 bleed） | n33 | 2e-6 | 2e-5 |
| `Mpass_local` | 本通道栅传递 | n33 | 2e-6 | 5e-6 |
| `Mbleed_local` | 本通道栅泄放 | n33 | 2e-6 | 2e-6 |

`parameters IREF=15u VDDV=1.8 VCASV=1.8`；`IREF` / `VCAS` / `DATA_EN` / `DATA_EN_B` 都是 testbench
理想源（`POC_ASSUMPTION`）。本轮**没有**做：Candidate F、任何新拓扑、`Mout/Mcas` 或
`Mpass/Mbleed` 改动、加 `Cbias`、按 corner 重新 tuning。`Cbias` 只作为 DATA-3.5 的
testbench bracket 存在过，冻结单元里没有它。

---

## 2. corner 名不许猜

`pdk/.../ms018_enhanced_v1p2_rev0_spe.lib` 自己的 `section` 语句（行号）：

```
26: section tt   1165: section ff   2301: section ss
3437: section fnsp   4573: section snfp   5709: section mos_mc
6862/6938/7014: dio_tt/dio_ff/dio_ss   7098+: bjt_*
```

取 `tt` + 一个慢 (`ss`) + 一个快 (`ff`)。`fnsp/snfp` 是"仅 NMOS / 仅 PMOS  flavour"，本单元没有
PMOS，用它们描述不了任何东西 → 不用。`mos_mc` 是 Monte-Carlo 段，属 `FULL_PVT_SIGNOFF` 范围，
本轮禁止。

归因不是假设：每个 corner 的数据都从"文件名里带该 corner 的 deck"产生，deck 第一行 include 打印为
`section=<该 corner>`（脚本 `ddrv_corner_probe.sh` 每次运行都把它印出来）。

---

## 3. 每 corner 只测必要项（DC 零负担 iprobe，瞬态 gear2only / 帧尺度）

瞬态全部用 **`method=gear2only`、`maxstep=5 ns`、`T=9.765625 µs`、`V(DATA_OUT)=1.20 V`、10 ns 沿**，
理由：DATA-3.5 证明 traponly 的样点交替是数值的，不能让它再混进冻结结果。
`I_BASELINE` 取同一 corner、同一 deck、`EN0=EN1=1` 常开的静态运行（所以电荷误差是"邻居开关造成的差值"，
不是本通道自身的调节误差）。全部 12 次仿真 `rc=0 errors=0 warnings=0`。

| 项目 | TT | SS（慢） | FF（快） |
|---|---|---|---|
| `VBIAS_SHARED`（DC ON） | 0.884261 V | 0.951269 V | 0.818122 V |
| `IOUT @ VOUT=1.20 V` | 14.931906 µA | 14.899428 µA | 14.964881 µA |
| 距 15 µA 误差（`COURSE_REQUIREMENT` 参考点） | −0.454 % | **−0.670 %** | −0.234 % |
| `COMPLIANCE_1PCT` | 0.4600 V | **0.5000 V** | 0.4200 V |
| `COMPLIANCE_2PCT` | 0.2200 V | 0.2400 V | 0.2000 V |
| `COMPLIANCE_5PCT` | 0.1200 V | 0.1200 V | 0.1200 V |
| `DC_STATIC_OFF_LEAKAGE`（DC 全扫 0→3.3 V 最大） | 0.000005 µA | 0.000000 µA | 0.000027 µA |
| OFF 时 `vbias_ch` / 共享节点 | 0.000000 V / 0.884277 V 保持 | 0 / 0.951454 V 保持 | 0 / 0.818129 V 保持 |
| 导通整定（帧尺度，邻居翻转的通道） | 27.53 ns | **36.53 ns** | 24.24 ns |
| 关断时间 | 10.46 ns | 10.77 ns | 10.42 ns |
| 稳态 ON 电流（窗口内均值） | 14.931906 µA | 14.899428 µA | 14.964881 µA |
| 与同 VOUT DC 曲线之差 | <10 nA | <10 nA | <10 nA |
| 受害通道 PEAK 串扰 | 7.876 µA = 52.51 % | 6.787 µA = 45.25 % | 7.940 µA = 52.94 % |
| 受害通道 `ELECTRICAL_CHARGE_ERROR` / 帧 | 0.0725 % | 0.0877 % | 0.0663 % |
| 毛刺 >±1 % 时长 | 151.7 ns (0.43 %) | 218.9 ns (0.62 %) | 128.7 ns (0.37 %) |
| `VBIAS_SHARED` 摆幅（动态） | 0.0821 V | 0.0926 V | 0.0784 V |
| 受害 `vbias_ch1` 摆幅 | 0.0665 V | 0.0558 V | 0.0677 V |
| `ADJACENT_POINT_ALTERNATION`（受害 / 开关通道） | NO 0.000000 / NO 0.000000 µA | NO / NO | NO / NO |
| `TRANSIENT_OFF_WINDOW_RESIDUAL_CURRENT`（瞬态 OFF 段均值） | 0.000299 µA | 0.000306 µA | 0.000293 µA |

> **这两个 OFF 量不是同一件事，不得混写**（DATA-4.5 item 7 的更正）：
> `DC_STATIC_OFF_LEAKAGE` 来自 `--en 0` 的 DC 稳态扫描（数据使能管一直关着，`vbias_ch = 0.000000 V`），
> 三 corner 最大 27 pA；`TRANSIENT_OFF_WINDOW_RESIDUAL_CURRENT` 来自**邻居通道正在翻转**的帧尺度瞬态里
> OFF 段最后 30 % 窗口 interior 的均值（同一时刻共享节点正在被隔壁通道每帧抽取，动态摆幅 0.078–0.093 V），
> 三 corner 最大 306 nA。两个数各自成立，原始数据未改；把 306 nA 说成"DC 关断泄漏"是错的，
> 把 27 pA 说成"瞬态也这么小"同样是错的。

（同一批数字的机器版：`results/data_driver_E_corner_dc.csv`、`..._transient.csv`、`..._xtalk.csv`；
逐行文字证据：`results/evidence/corner_*.txt`，12 份。）

---

## 4. 探针结论（允许说的与不允许说的）

**允许说的（实测）**：

* 三个 section 都能建立 15 µA：最差 `ss` 在代表性恒流点 1.2 V 上 −0.670 %，即 POC ±1 % 带内；
  电流随工艺方向单调合理（慢管略低、快管略高），跨度 65 nA = 0.44 % of 15 µA。
* 合规窗口随工艺平移但不塌陷：±1 % 拐点 0.42（ff）→ 0.50 V（ss），±5 % 拐点三 corner 同为 0.12 V；
  输出可达上限三 corner 都是 3.3000 V（零负担探针，`max|V(vsw)−V(data_out)| = 0`）。
* 帧尺度内一定整定：最慢 36.53 ns 只占 4.88 µs 导通时间的 0.75 %；稳态电流与同 VOUT 的 DC 曲线
  在三个 corner 都差 <10 nA。
* 门控语义在三个 corner 都成立：ON 时 `vbias_ch` 与 `VBIAS_SHARED` 差 0.000000 V；
  OFF 时 `vbias_ch = 0`，而共享节点保持 0.818/0.884/0.951 V —— 没有任何通道能把共享偏置放掉。
* 基本串扰形态与 DATA-3.5 一致且**不依赖数值方法**（本轮全程 gear2only，振铃恒 0.000000 µA）：
  峰值 45–53 % 是物理的，每帧电误差 0.066–0.088 %。

**不允许说的（评审 item 5 / 7）**：

* 这不是 PVT signoff：`FULL_PVT_SIGNOFF: NO`。缺温度扫描、缺电源电压扫描、缺 mismatch、
  缺 Monte Carlo、缺可靠性签核 → 只能叫 `BASIC_PROCESS_CORNER_PROBE`。
* 三个 MOS section 不覆盖温度与失配，也不构成"corner 之间取包络即安全"的论证。
* 电误差不得换算为亮度/灰阶：`ELECTRICAL_CHARGE_ERROR` 是终点，
  `OPTICAL_MAPPING: NOT DEFINED`（无电光模型、无 `EQE(I)`、无光功率模型、无灰阶定义）。

---

## 5. 冻结判据（item 8 的四条 blocker）

| 可能阻止冻结的条件 | 实测 | 结论 |
|---|---|---|
| 无法建立 15 µA | 三 corner 全部 14.899–14.965 µA（−0.23 %…−0.67 %） | 未触发 |
| 无法在 9.765625 µs 内 settling | 24.2–36.5 ns，占 ON 时间 ≤0.75 % | 未触发 |
| 错误逻辑状态 | ON 传到 `VBIAS_SHARED` 零压降、OFF 到 0 V 且共享节点不动 | 未触发 |
| 明显器件异常 | 无收敛问题（12/12 `errors=0 warnings=0`）、无振铃（gear2only 恒 0）、`DC_STATIC_OFF_LEAKAGE` ≤27 pA 且 `TRANSIENT_OFF_WINDOW_RESIDUAL_CURRENT` ≤306 nA（两个量分开看，见 §3 注）、无负向栅节点越界（最差 `vbias_ch = −0.000457 V`，约 0.5 mV 结偏置） | 未触发 |

→ `DATA_DRIVER_1CH: FROZEN_FOR_SCHEMATIC`，停在这里等最终 source review。
独立 review 已给出 `REVIEW DECISION: GO` / `DATA_DRIVER_1CH: ACCEPTED_FOR_COURSE_POC`
（接受的电路版本 = `4b3e571`，见文件头的 `REVIEW_HEAD_SHA`），下一步 `VIRTUOSO_SCHEMATIC`。
200 ns 时槽仍是 `POC_STRESS_TEST`（DATA-3.5 实测每槽电误差 3.6 %，两法一致，物理），
若未来系统真用这个时间尺度则 `REWORK_REQUIRED`。当前帧尺度结论不因此改变。

---

## 6. Git 与产物

* 分支 `poc/data-driver-1ch`：`4b3e571`（DATA-5，`Mpass_local` 换成 `n33_dnw_4t_ckt`）是独立
  review 接受的**电路**版本；本文件的 `REVIEW_HEAD_SHA` 就指它。之后的 commit 只改文字，
  不改电路、W/L、testbench 或任何结果。
* 接受后按评审指示把 `poc/data-driver-1ch` 合并进 `main` 并推送（合并前后都跑 safety gate，
  合并时工作树干净）。`MAIN_HEAD` 不写进本文件——写进去就必然过期，它由那一轮 handoff 给出，
  `git log main` 与 `git ls-remote origin main` 是权威来源。
* 本轮新增：`scripts/ddrv_corner_probe.sh`、`reports/data_driver_1ch_frozen.md`（本文）、
  3 份 corner CSV、12 份 corner 证据、12 份 corner deck（含 `section=tt/ff/ss` 自证）、
  `ddrv_xtalk.py` 的 CSV 引号修复。
* 未做：Candidate F、新拓扑、schematic、scan output、layout、DRC/LVS/PEX、384 通道、
  TCON、reset/blanking/level shifter。
* `IDENTITY_PRIVACY_CLEANUP = PENDING_OWNER_ACCEPTED` 与 IC 设计无关，状态不变。

## 7. 本轮我自己的缺陷（保留，不删）

| 缺陷 | 后果 | 处置 |
|---|---|---|
| `ddrv_corner_probe.sh` 把 corner 放在错误的位置参数槽（`"$c"` 没落到 `ddrv_run.sh tran` 的第 7 参），且我先用 Python 字符串替换去改脚本、替换没命中却没报错 | `ss`/`ff` 的**瞬态腿静默地跑了 `section=tt`**，三块结果逐位相同。DC 腿是真 corner（数值确实不同），所以只有"三块完全一样"这个反常暴露了问题 | 位置参数改对；脚本现在每次都从产生该数据文件的 deck 印出 `include ... section=`，并在证据里留 deck 名。第一轮所有 ss/ff 瞬态数字作废并重跑 |
| `ddrv_xtalk.py` 手写 CSV 时不给含逗号的自由文本字段加引号（`--slew-desc` 里有逗号） | 列错位：`vbias_shared_min_v` 里装进了 `" method=gear2only-"` 这种文本 | 加 `csv_field()` 引号化；三 corner 重新分析，列数校验 21/24 全行一致 |
| Python 字符串替换未命中即静默 | 一个"已修好"的假象 | 之后一律用带唯一上下文的 Edit；替换脚本先断言命中数 |

---

## 8. 给最终 source review 的三条

1. 冻结点是否正确：`T_COLUMN = 9.765625 µs` 这个适用范围由评审指定，本单元在该尺度上的
   每帧**电荷**误差 ≤0.088 %、峰值瞬时误差 45–53 %（物理，来自共享偏置动态阻抗）。
   若课程最终需要"瞬时电流也不得偏离 15 µA 超过 X %"，那就必须把共享偏置缓冲/保持电容纳入设计范围
   （DATA-3.5 的 `Cbias` bracket 显示 10 pF 可把峰值从 58.7 % 压到 7.1 %），那会改变面积预算。
2. `ss` 的 ±1 % 合规拐点 0.50 V：若 Micro LED 的 `Vf`/`VLED` 最终定下来使最低工作电压落在
   0.42–0.50 V 之下，需要重判 compliance（`Vf`、`VLED` 目前 `NOT DEFINED`，本轮不做任何代入）。
3. schematic 阶段的输入就是 §1 的表 + 12 份 deck；本 POC 只有 1 路（外加 2 路独立性测试用的
   双通道 testbench），384 通道的物理规划未开始。
