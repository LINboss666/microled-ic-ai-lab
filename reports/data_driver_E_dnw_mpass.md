# Phase DATA-5：Candidate E-DNW —— 用 PDK 合法的隔离器件恢复 Mpass 的 isolated body

独立评审决定：普通 `n33` 把体端改接 `vss` 的 bodyfix **不接受**（`SS: FUNCTIONAL FAIL`），
指示"只换 `Mpass_local` 的器件主名"。本轮严格按这个范围做：拓扑、尺寸、共享偏置、
enable 语义全部不动；`Mout`/`Mcas`/`Mref`/`Mbleed_local` 仍是 `n33`；`Mpass` 保持 L=2 µm、
W=5 µm，不重新 sizing。

```
SELECTED_DNW_MASTER:        smic18mmrf/n33_dnw_4t_ckt
DNW_DEVICE_SMOKE:           PASS
MPASS_BODY_IMPLEMENTATION:  B = 本通道自己的 vbias_ch 节点（VSB = 0），每通道各一个
TT:  PASS
SS:  PASS        （DATA-4.5 的 8.18 uA / −45 % 失败已消失）
FF:  PASS
BASIC_PROCESS_CORNER_PROBE: PASS  (tt / ss / ff)
FRAME_SCALE_POC:            PASS  (T_COLUMN = 9.765625 us)
TWO_CHANNEL_INDEPENDENCE:   PASS  (静态 0.000 %；帧尺度每帧电误差 0.066–0.088 %)
DNW_AREA_COST:              PRESENT
FULL_PVT_SIGNOFF:           NO
DATA_DRIVER_1CH:            FROZEN_FOR_SCHEMATIC
IMPLEMENTATION:             Candidate E-DNW
```

---

## 1. DNW 候选器件审计（item 2 / 3，只读，结论-only）

两个 non-RF 候选都在库里真实存在（`ls` 目录清单 + `mosfets.Cat` + 本厂 LVS 器件表）。
**端子数不靠名字猜**：Spectre 自己的读数才是证据。

```
DNW_DEVICE_AUDIT:

n33_dnw_4t_ckt:
  terminals            = 4，netlist 顺序 (drain gate source bulk)
  isolated_body        = YES（第 4 端子可独立驱动且对沟道有作用，见 §2 smoke B）
  DNW/Psub 显式端子    = 无（模型只吃 4 个节点，阱/衬底由该器件主名自己带）
  Spectre usage        = 与 n33 家族同一写法（bsim4 model，非 subckt）；4 节点实例直接读通
  voltage family       = 3.3 V 器件族（与 n33/n33_ckt 同组）
  W/L 实测读通         = l=2e-6 w=5e-6，0 errors / 0 warnings / 0 notices
  OA/PCell master      = smic18mmrf/n33_dnw_4t_ckt（layout 基元 + symbol，无 schematic 视图）
  suitable_for_Mpass   = YES  <- 本轮选定

n33_dnw_ckt:
  terminals            = 至少 6（Spectre 实测拒绝 4 节点，见下方错误行）
  isolated_body        = YES（器件定义里另有阱节点与衬底节点）
  DNW/Psub 显式端子    = 是，需要外接
  端子的 netlist 顺序/身份 = 本地可读材料只给出"需要 ≥6 个端子"，没有可核实的顺序定义
  suitable_for_Mpass   = NO（本轮不用：接它就必须自己编 well connection，item 3 明确禁止）
```

Spectre 的实测拒绝行（我们自己的诊断 deck 产生，非 PDK 内容）：

```
ERROR (SFE-45): `Mb': An instance of `n33_dnw_ckt' needs at least 6 terminals (but has only 4).
```

同一只器件按 6 节点写（额外的两个节点各自接 0 V）时读通并算完（0 errors），但**这两个节点
谁是阱谁是衬底无法从可读材料确定**，所以只作为"端子数证据"留下，不用于设计。
RF 版 `dnw33_ckt_rf` / `dnw33_6t_ckt_rf` 按 item 2 未启用（两个普通 DNW master 里已有一个适用）。

`n33_dnw_4t_ckt` 的取舍理由（item 3 的优先原则）：它给的就是 D/G/S/独立 B，而阱与衬底的
外围连接由该主名自己封装——正好是 Candidate E 冻结版在网表里表达、但普通 `n33` 在工艺上
做不到的那件事。

---

## 2. 单器件 smoke（item 5）：先证明器件本身能用来做这件事

三个诊断 deck，全部 `spectre/diag/`，全部只含我们自己的网表与器件名：

| 探针 | 目的 | 实测 |
|---|---|---|
| `dnw_smoke_a_transfer.scs` | 实例化 / 端子映射 / 与 `n33` 是否同一只器件 | 二极管接法、VBS=0，扫 0→1.8 V：166 步上 `n33_dnw_4t_ckt` 与 `n33` 的电流逐点一致（0.78 V→1 µA、1.18 V→30 µA、1.78 V→169 µA 全部同值），0 errors 0 warnings 0 notices |
| `dnw_smoke_b_body_effect.scs` | 第 4 端子到底是不是 body | VGS=1.5 V、VDS=0.3 V 固定，把 body 拉到源极以下：Ids 75→47 µA（VSB 0→0.48 V），继续到 VSB≈1.2 V 时 22 µA；`Ibulk` 在文件打印精度（6 位小数，1 µA）内为 0.000000 A，即比沟道电流低两个数量级以上，衬底没有可测直流路径 |
| `dnw_smoke_c_terminal_count.scs` | `n33_dnw_ckt` 的端子数 | 4 节点被拒（SFE-45，"needs at least 6 terminals"）；6 节点读通 0 errors |

```
DNW_DEVICE_SMOKE: PASS
```

两点必须写清楚的边界：

* "阱真的把这块区域从衬底里切出来"是**工艺/器件定义**层面的事实（DATA-4.5 §2 的本厂 LVS
  器件识别 + DNW 主名单独存在），不是这三段仿真证明的；仿真能证明的是"第 4 端子是一只
  独立、对沟道有作用、没有低阻衬底直流通路的 body"。
* 4 端子模型不带阱节点与衬底节点，因此 **DNW 管体对衬底的电容/衬底二极管不在模型里**。
  这是这套器件定义的固有简化，本轮按 item 12 不做 DRC/LVS，也不试图用仿真补它；明天画
  原理图时器件主名照旧用它，衬底节点若需要建模，只能选 6 端子器件（要先有 PDK 文档给出的
  端子定义）。

---

## 3. 本轮自查到的生成器缺陷（必须先讲，因为它改过一版结果）

DATA-4.5 加的 `--mpass-bulk` 开关把默认值写成了**字面量 `"vbias_ch"`**，而通道 1 的局部节点
叫 `vbias_ch1`。于是双通道 deck 里通道 1 的 pass 器件体端被接到了**通道 0 的节点**：

```
results/evidence/mpass_bulk_bug.txt
< Mpass_local1 (vbias data_en1 vbias_ch1 vbias_ch1) n33_dnw_4t_ckt   <- 评审要的双通道电路
> Mpass_local1 (vbias data_en1 vbias_ch1 vbias_ch)   n33_dnw_4t_ckt   <- 错接
```

后果：第一次 E-DNW 双通道帧尺度跑出的"受害通道每帧电误差 14.97 %、±5 % 带内只保持
48.36 %"是**这个错接电路**的结果，不是 DNW 器件的结果。该版结果已被覆盖重跑，
`results/evidence/mpass_bulk_bug.txt` 保留缺陷证据。

发现方式：item 10 要求自动生成的连通性摘要（`scripts/ddrv_topology.py` 解析 deck 得到的
D/G/S/B 表）——如果只看单通道数字（单通道里 `vbias_ch` 恰好等于默认值，完全正确）就发现不了。

修法是按构造消除歧义，不是加一条断言：`--mpass-bulk` 默认改为"未指定"，未指定时每通道
用自己的节点；只有显式给值才覆写，并且任何显式值都自动进 deck 文件名。

回归证明（不是"看起来一样"，是逐字节）：

```
默认参数重生成 DATA-4 已评审的双通道帧尺度 deck  -> TWOCH_BYTE_IDENTICAL_AFTER_FIX
默认参数重生成 DATA-4 冻结单通道 DC deck        -> EXACT_MATCH_FROZEN（本轮再测一次仍成立）
```

顺带承认：DATA-4.5 的"逐字节复现"回归只测了单通道 deck，所以没抓到这个缺陷。
DATA-4.5 报出去的 bodyfix 数字不受影响（`vss` 与通道无关，`Mpass_local1 ... vss` 是对的）。

---

## 4. Candidate E-DNW 的定义（item 6）

与冻结 deck 的差别只有两行器件名，其余逐器件相同（见
`results/evidence/ednw_connectivity_ss.txt`，由 deck 解析生成）：

```
Mpass_local    (vbias  data_en   vbias_ch  vbias_ch)  n33_dnw_4t_ckt l=2e-6 w=5e-6   <- 主名换成 DNW
Mpass_local1   (vbias  data_en1  vbias_ch1 vbias_ch1) n33_dnw_4t_ckt l=2e-6 w=5e-6
Mout/Mcas/Mref/Mbleed_local*                                        = n33，体端 vss，W/L 不变
```

连通性摘要（item 10）：

```
PER-CHANNEL (每通道重复) : Mcas, Mout, Mpass_local, Mbleed_local, Mcas1, Mout1,
                           Mpass_local1, Mbleed_local1        = 8 只
SHARED (整块共用)        : Mref                                = 1 只
每通道节点   : vbias_ch / vbias_ch1（栅节点=body 节点）、node_m / node_m1、
               data_out / data_out1、data_en(_b) / data_en1(_b)、vcas / vcas1
全局节点     : vbias（VBIAS_SHARED）、vdd、vss(=0)
证明：Mpass_local 的 body = vbias_ch，Mpass_local1 的 body = vbias_ch1，两者是不同网表；
      两个 body 都不接 vss，所以 vbias_ch 没有被短到全局衬底。
```

---

## 5. 三 corner 复验：E-DNW 恢复了原冻结版的电气行为（item 7 / 8）

同一套探针（`scripts/ddrv_corner_probe.sh`，`gear2only`、`maxstep=5 ns`、
`T=9.765625 µs`、VOUT=1.2 V、零负担 iprobe，`PROBE_BURDEN=0`），每 corner 的 deck 都从
产出该数据的 deck 文件里回读 `include ... section=` 确认归属。

### DC

| 量 | 冻结(不可实现) | bodyfix(vss) | **E-DNW** |
|---|---|---|---|
| `VBIAS_SHARED` tt/ss/ff | 0.884261 / 0.951269 / 0.818122 V | 同 | 同 |
| ON 时 `VBIAS_SHARED − vbias_ch` | 0.000000 V（三 corner） | 0.000000 / 0.000052 / 0.000000 | **0.000000 V（三 corner）** |
| `IOUT@1.2 V` | 14.931906 / 14.899428 / 14.964881 µA | 14.931882 / 14.898749 / 14.964877 | **14.931906 / 14.899428 / 14.964881 µA** |
| 距 15 µA | −0.454 / −0.670 / −0.234 % | −0.454 / −0.675 / −0.234 % | −0.454 / −0.670 / −0.234 % |
| `COMPLIANCE_1/2/5PCT` | 0.46·0.22·0.12 / 0.50·0.24·0.12 / 0.42·0.20·0.12 V | 同 | 同 |
| `DC_STATIC_OFF_LEAKAGE`（全扫最大） | 0.000005 / 0.000000 / 0.000027 µA | 同 | **同** |
| OFF 时共享节点 | 0.884277 / 0.951454 / 0.818129 V 保持 | 同 | 同 |

### 帧尺度瞬态

| 量 | 冻结 | bodyfix | **E-DNW** |
|---|---|---|---|
| 导通整定 tt/ss/ff | 27.53 / 36.53 / 24.24 ns | 739.9 ns / **不整定(4/4)** / 49.71 ns | **27.27 / 36.54 / 24.25 ns** |
| 关断时间 | 10.46 / 10.77 / 10.42 ns | 11.43 / 10.85 / 9.89 ns | 10.08 / 10.77 / 10.41 ns |
| 稳态 ON 电流 | 14.931906 / 14.899428 / 14.964881 µA | 14.931810 / **8.18 µA** / 14.964877 | **14.931906 / 14.899428 / 14.964881 µA** |
| checker 判定 | OK / OK / OK | OK / **FAIL** / OK | **OK / OK / OK** |
| 受害 PEAK 串扰 | 52.509 / 45.246 / 52.936 % | 4.802 / 0.372 / 36.852 % | **52.515 / 45.245 / 52.937 %** |
| 每帧 `ELECTRICAL_CHARGE_ERROR` | 0.0725 / 0.0877 / 0.0663 % | 0.2131 / 0.2247 / 0.0976 % | **0.0726 / 0.0877 / 0.0663 %** |
| 毛刺 >±1 % 时长 | 151.7 / 218.9 / 128.7 ns | 2.342 µs / 0 / 291.3 ns | **144.0 / 218.9 / 129.6 ns** |
| 受害在 ±5 % 带内保持 | 99.71 / 99.69 / 99.74 % | 100 / 100 / 99.58 % | **99.72 / 99.69 / 99.74 %** |
| `ADJACENT_POINT_ALTERNATION` | NO | NO | **NO（三 corner 全 0.000000 µA）** |
| `TRANSIENT_OFF_WINDOW_RESIDUAL_CURRENT` | 0.000299 / 0.000306 / 0.000293 µA | 同 | **同** |

读法：E-DNW 与冻结版的差别落在第 3–4 位有效数字（整定 27.27 vs 27.53 ns、毛刺 144.0 vs
151.7 ns），而 bodyfix 的差别落在功能上。**"原电气行为恢复"成立，且现在是可制造的。**
不要求逐位相同，也没有靠改尺寸去凑（W/L 一字未动）。

`SS: FUNCTIONAL FAIL` 的根因确认是体效应：`n33` 的 body 只能接公共衬底，`VSB = vbias_ch`
抬高了阈值，pass 器件在 `VBIAS_SHARED` 最高的慢 corner 上送不满局部栅节点
（DATA-4.5 §5）。换成体端跟随源极（VSB=0）的 DNW 主名后，ss 的 8.18 µA / −45 % /
4 个 ON 窗口全不整定全部消失，稳态回到 14.899428 µA、整定 36.54 ns。

## 6. 两通道验证（item 9）

静态 2×2（两通道都钳在 1.2 V，四种 enable 组合，iprobe）：

```
EN0 EN1 : I0            I1
 0   0  : 0.000001 µA   0.000001 µA
 0   1  : 0.000001 µA  14.931906 µA
 1   0  : 14.931906 µA  0.000001 µA
 1   1  : 14.931906 µA 14.931906 µA

dI1（CH1 常开，CH0 通/断）= 0.000000 uA = 0.000 %  -> ok
dI0（CH0 常开，CH1 通/断）= 0.000000 uA = 0.000 %  -> ok
```

动态（CH1 常开、CH0 每帧翻转，`gear2only`、帧尺度、`maxstep=5 ns`）见 §5 表：受害通道
保持率 99.69–99.74 %，每帧电误差 0.066–0.088 %，振铃判据 NO。CH0 的通/断不改变 CH1 的
逻辑状态：CH1 自己的栅节点 `vbias_ch1` 全程 0.752–0.952 V 区间内、离 0 V 极远，ON 电平
与静态基线一致到 6 位小数。

`TWO_CHANNEL_INDEPENDENCE: PASS`。

（`results/evidence/mpass_body_hold_compare.txt` 里还带着 `ddrv_twochan.sh` 顺带跑出的
200 ns 时槽动态行——那是 DATA-3.5 的 `POC_STRESS_TEST` 时间尺度，判据 FAIL 与本轮结论
一致，不是帧尺度结果，别混着读。）

## 7. DNW 的代价与没做的事（item 11 / 12）

```
DNW_AREA_COST:           PRESENT
DNW_LAYOUT_COMPLEXITY:   PRESENT
FUTURE_384CH_SCALING:    NEEDS_AREA_REVIEW
NO_LAYOUT / NO_DRC / NO_LVS: 本轮只确认器件主名真实存在且能仿真
```

DNW 不是免费替换：本 kit 的 techfile 给 DNW 规定了微米量级的最小宽度与间距（远大于本单元
器件尺寸），PCell 手册另有一条 DNW guard-ring 选项与 LVS 相互影响的注意事项；每通道都要
一只自己的隔离管体（CH0/CH1 的 body 是两个不同节点），所以阵列放大时阱面积是按通道增长的。
这些留给明天的原理图/版图阶段和 384 通道的外推评审，不作为本轮的否决理由，也不许写成"免费"。

其它未做（都在禁区里）：温度、电源扫描、mismatch、Monte Carlo → `FULL_PVT_SIGNOFF: NO`；
没有 Candidate F、没有新拓扑、没有 Cbias、没有重新 sizing、没有 brightness/灰阶换算
（`OPTICAL_MAPPING: NOT DEFINED`）；200 ns 时槽仍是 `POC_STRESS_TEST`，若未来真用那个尺度
则 `REWORK_REQUIRED`。

## 8. 状态与工件

`reports/data_driver_1ch_frozen.md` 的 `BLOCKED_PENDING_BODY_DECISION` 与
`reports/data_driver_n33_body_audit.md` 的同名状态行，都由本文件的 `FROZEN_FOR_SCHEMATIC`
接棒；那两份是 DATA-4 / DATA-4.5 的历史记录，数据未改，只加了指向本文件的更正行。

冻结下来的器件定义（生成命令的可复现形式）：

```
FROZEN = --mpass-model n33_dnw_4t_ckt --mbleed-model n33 \
         --lpass 2e-6 --lbleed 2e-6 --wpass 5e-6 --wbleed 2e-6
         （--mpass-bulk 不给 = 每通道自己的体端）
```

工件：`spectre/diag/dnw_smoke_{a_transfer,b_body_effect,c_terminal_count}.scs`、
`spectre/generated/*dnwpass*.scs`、`results/data_driver_Ednw_corner_{dc,transient,xtalk}.csv`、
`results/data_driver_Ednw_static.csv`、`results/data_driver_E_mpass_body_hold_compare.csv`、
`results/evidence/dnw_{tt,ss,ff}_{on,off,ch0,victim}.txt`、
`results/evidence/dnw_static/ddrv_E_local_gate_static_*.txt`、
`results/evidence/mpass_body_hold_compare.txt`、`results/evidence/mpass_bulk_bug.txt`、
`results/evidence/ednw_connectivity_ss.txt`、`logs/ednw_3corner.log`。

**NEXT: VIRTUOSO_SCHEMATIC**，用真实主名 `smic18mmrf/n33_dnw_4t_ckt` 画 Mpass。
停在这里等 source review。
