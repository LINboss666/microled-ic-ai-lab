# Phase DATA-4.5：冻结前 Body-Terminal 器件可实现性审计

只回答一个问题：**老师 smic18mmrf PDK 里普通 `n33` 是否物理上允许把独立体端接到 `vbias_ch`？**

不重新设计 Candidate E，不换拓扑、不改 Cbias、不重新 sizing、不做 DNW 替换。

```
N33_BODY_ISOLATION:              NOT_SUPPORTED
MPASS_BODY_FINAL:                vss（BODYFIX 变体；本轮唯一可实现的接法）
BODYFIX_REQUIRED:                YES
TT_RECHECK:                      PASS
BASIC_PROCESS_CORNER_RECHECK:    FAIL_AT_SS（tt PASS / ff PASS / ss FAIL，判据见 §5）
DATA_DRIVER_1CH:                 BLOCKED_PENDING_BODY_DECISION
ISOLATED_3V3_NMOS_AVAILABLE:     YES（器件主名见 §6，未替换、未仿真）
```

---

## 1. 审计方式与只读边界

证据类型：`FOUNDRY_DEVICE_DEFINITION`（老师 kit 的 OA 库结构 + PCell 手册 + 器件目录 + 本厂
LVS 器件识别规则），**不是** Spectre model 的端子个数。普通 `n33` 的 BSIM model 确实有第四个
bulk 端子，但第四个端子只说明模型有这个节点，不说明版图上有可以独立偏置的阱——所以这条
线索完全不采信（评审 item 2 的理由）。

只读核查内容（全部在 guest，路径 `pdk/smic18mmrf_teacher/`）：

| 查了什么 | 位置 |
|---|---|
| 器件主目录（cell 清单与视图集合） | `smic18mmrf/`、`mosfets.Cat`、`rf_mosfets.Cat`、`primitives.Cat` |
| 分层映射与技术文件中的阱/衬底/DNW 层名 | `smic18mmrf/layer.map`、`techfile.tf` |
| PCell 手册对端子与器件族的定义 | `docs/Pcell_Library/SMIC_OA_CDS_Reference_Manual_...V1.20_REV0_0.pdf` §13.1、§14.1、§15.1、§15.7、§19 |
| 本厂 LVS 器件识别与体端归属 | `Calibre/LVS/SMIC_CalLVS_018MSERF_1833_V1.11_REV2_0.lvs`（体端/阱派生层定义在 700–735 行区，器件语句在 3210–3253 行区） |
| OA 器件主单元本体（layout/symbol/pdk.dat/data.dm） | 见 §7：这一条**没读通**，已如实记录 |

只读证明（探针前后各测一次）：

```
PDK 文件数              3975 -> 3975
mtime 晚于 2026-01-01    0 -> 0
*.cdslck 锁文件          0
```

PDK、`cds.lib`、techfile、model 文件、任何库/原理图/版图一个字节都没动；探针脚本自己写的
文件全部落在 `/root/microled_ai_project` 与 `/root/qoder_ic617_sandbox` 内。

---

## 2. 关键发现：`n33` 的体端是全片衬底，不是器件局部节点

按证据逐条列出（只写我们自己的结论和层名/器件名，不抄 deck 正文）：

1. **`n33` 没有 schematic 视图。** 它是版图基元器件主单元（`layout` + `symbol` +
   `ivpcell`/`pdk.dat`/`data.dm`，视图集合与 `n18`/`p33`/`n33_ckt` 完全一致）；器件定义来自
   几何，而几何里没有属于这只管子的阱层。有 schematic 内部接线可查的是 `rhrpo` 那类
   子电路单元，`n33` 家族五只 cell（`n33`/`n33_3t`/`n33_ckt`/`n33_dnw_ckt`/`n33_dnw_4t_ckt`）
   都没有。
2. **本厂 LVS 的器件识别把 `n33` 的体端绑在"全片 p 型体内区域"上。** 器件语句里 `n33`
   与 `n33_ckt` 的体端用的是同一个派生层；该派生层的定义是"整个模块面积减去 n 阱与环区"
   （模块面积由边界层向外放大 1 µm 得到），也就是说 `n33` 的体端节点是 **die-wide 的衬底**，
   全片所有普通 NMOS（`n18`、`n33`、`nmvt*`、`nnt*`）共用同一个体节点。同一处对衬底节点的
   定义又是"模块面积减去 DNW 覆盖区再减去环"，等于直接承认：本工艺里唯一能把某块区域从
   衬底里切出来的手段就是 DNW。（表达式原文在该文件的派生层定义区，此处只记结论。）
3. **普通 `n33` 的识别区显式排除深 N 阱。** 用于识别 `n33` 的栅极区域，定义里把子电路版本
   的区域和 DNW 标识区域都扣掉了；一旦画了深 N 阱，就不再被认成普通 `n33`，而必须改用带
   `_dnw_` 的器件名。
4. **隔离版本是另外命名的器件主单元，不是 `n33` 的参数。** 目录与本厂 LVS 器件表都列出
   `n33_dnw_ckt` 与 `n33_dnw_4t_ckt`；前者除 D/G/S/B 之外还另外给出"阱节点"和"衬底节点"
   两个端子，后者是四端子深 N 阱版本。反过来说：如果普通 `n33` 的体端本来就能独立接，
   这两族 cell 就是多余的。
5. **PCell 手册自己的措辞。** §13.1 说库里多数 MOS 是"4/3（common bulk）端子器件，
   体端子被显式接好"；§15.1 给普通 MOS 的端子集合是 D/G/S/B（+B2），而 §15.7 给 RF MOS
   才明确列出 `Psub`、`DNW` 作为独立节点。§19 的 add-wire 工具是把体端子自动接到
   `gnd!`/`vdd!` 这类固定电位，示例里没有、也不打算接到信号节点。
6. **本 kit 的 LVS 选项里有一条"检查 pwell 是否接到地"**（该文件 OPTION 20 的说明行），
   即出厂规则本身就假定 `n33` 的体节点是地电位，不是可编程节点。

### 电气后果（为什么这不是"风格问题"）

`Mpass_local` 的源极就是 `vbias_ch`，而 `vbias_ch` 在 ON 时被充到 `VBIAS_SHARED`
（tt 实测 0.884261 V）。若体端＝衬底并被驱动到 0.884 V：

* 源/漏 n+ 对 p 衬底的结将变成 **p 侧 0.884 V、n 侧 0 V** 的正偏，源极侧尤其严重——
  整个像素网络的电流会从衬底跑掉，且全片所有其它 n33 的 n+/p-sub 结一并正偏；
* 更根本的是：体端是全片唯一节点，**两只 Mpass 无法有各自不同的体电位**，
  而 Candidate E 的门控语义恰恰依赖每通道自己的 `vbias_ch`；
* 抽取网表里 `vbias_ch` 会和衬底节点短路，LVS 直接报 mismatch/short。

所以原冻结定义里的 `Mpass_local (vbias data_en vbias_ch vbias_ch) n33` **不可实现**。
`Mout`、`Mcas`、`Mref`、`Mbleed_local` 的体端本来就接 `vss`，不受影响。

---

## 3. Candidate E-bodyfix（不是 Candidate F）

只改一个网络，其余全部冻结——这是最接近原意的可实现接法：

```
Mpass_local   (vbias  data_en   vbias_ch  vss)  n33 l=2e-6 w=5e-6     <- 体端 vbias_ch -> vss
```

对照冻结 deck 的完整 diff 只有这一行和它上面的注释行（`diff` 实测，见
`results/evidence/bodyfix_3corner_pipeline.log`）。生成器新增 `--mpass-bulk {vbias_ch,vss}`，
**默认仍是 `vbias_ch`**，所以已评审的 deck 能逐字节复现：

```
用 HEAD 版与本版跑同一组 flag         -> IDENTICAL_DEFAULT
本版默认 flag vs 冻结 deck            -> EXACT_MATCH_FROZEN
--mpass-bulk vss                      -> 只多出 _bulk vss 一行（器件行见上）
```

`--mpass-bulk vss` 时 tag 自动追加 `_bulk vss`（`..._ch2_iprobe_mgear2only_bulkvss_tt_dyn_...`），
不依赖调用者记得 `--suffix`，变体不可能覆盖冻结 deck。

探针脚本 `scripts/ddrv_corner_probe.sh` 加了两个默认值不变的开关（`TAGP` 结果表前缀、
`EVP` 证据文件前缀），使 bodyfix 写进 `results/data_driver_Ebodyfix_*.csv` 与
`results/evidence/bodyfix_*.txt`，DATA-4 的已评审工件一个字节都没被重写。

体端改 `vss` 后的物理代价是**体效应**：`VSB = V(vbias_ch)`，Mpass 的阈值随局部节点电压升高，
正好在它需要把节点顶到 `VBIAS_SHARED` 的时候失去过驱动。`VBIAS_SHARED` 越高（ss corner）
代价越大。这不是拟合出来的说法，下面的数字按这个方向走。

---

## 4. TT 复验（评审 item 4 要求的全部量）

帧尺度 `T = 9.765625 µs`、`method=gear2only`、`maxstep=5 ns`、`reltol=1e-3`（从 run header
读回，不是假设）；零负担 iprobe，`PROBE_BURDEN` 三 corner 均 `max|V(vsw)−V(data_out)| = 0`。

| 量 | 冻结（体端=vbias_ch） | bodyfix（体端=vss） | 判定 |
|---|---|---|---|
| DC `vbias_ch` ON vs `VBIAS_SHARED` | 差 0.000000 V | 差 0.000000 V | 门控语义保持 |
| DC `IOUT@1.2 V` | 14.931906 µA（−0.454 %） | 14.931882 µA（−0.454 %） | `COURSE_REQUIREMENT` 参考点未劣化 |
| `COMPLIANCE_1/2/5PCT` | 0.4600 / 0.2200 / 0.1200 V | 0.4600 / 0.2200 / 0.1200 V | 完全一致 |
| `DC_STATIC_OFF_LEAKAGE`（全扫最大） | 0.000005 µA | 0.000005 µA | 一致 |
| DC OFF `vbias_ch` / 共享节点 | 0.000000 V / 0.884277 V 保持 | 0.000000 V / 0.884277 V 保持 | OFF 不破坏共享偏置 |
| ON 曲线 vs 被接受核心（166 点） | 0.000000 µA | −0.000023 µA = −0.0002 % 满度 | 仍算透明（`POC_FUNCTIONAL_CRITERION`） |
| 导通整定 | 27.53 ns | **739.9 ns** | 仍 < 帧时间（4.88 µs ON 的 15 %），但慢 27× |
| 稳态 ON 电流（窗口均值） | 14.931906 µA（0.454 %） | 14.931810 µA（0.455 %） | 一致 |
| `TRANSIENT_OFF_WINDOW_RESIDUAL_CURRENT` | 0.000299 µA | 0.000299 µA | 一致 |
| `ADJACENT_POINT_ALTERNATION` | NO（0.000000 µA） | NO（0.000010 µA） | 数值振铃没有回来 |
| 受害通道 PEAK 串扰 | 52.51 % | **4.80 %** | 峰值降 11×（`POC_CHARACTERIZATION_ONLY`） |
| 受害通道每帧 `ELECTRICAL_CHARGE_ERROR` | 0.0725 % | **0.2131 %** | 升 3×（同栏，只描述特性） |
| 毛刺 >±1 % 时长 | 151.7 ns | **2.342 µs** | 变长 15×（浅而长取代深而短） |
| 受害 `vbias_ch1` 摆幅 | 0.0665 V | **0.0051 V** | 两通道独立性变好 13× |

**两通道独立性（item 4 的"CH0 OFF/ON 不破坏 CH1 逻辑状态"）**：受害通道自身栅节点
`vbias_ch1` 全程停在 0.879629–0.884697 V（摆幅 5.1 mV），既不向 0 V 掉也不越过 ON 电平，
基线电流 14.931882 µA 与静态保持运行一致；因此邻居每帧翻转不改变 CH1 的通/断状态。

峰值变好、电荷误差变长，两者同源：体效应抬高了 Mpass 的导通电阻，边沿注入的电荷被摊到
更长的时间窗里。**不得**把这读成"bodyfix 让串扰变小所以更好"——按 DATA-3.5 的分层，
PEAK 只是 `POC_CHARACTERIZATION_ONLY`，真正的门限是稳态电流、整定与逻辑状态。

`OPTICAL_MAPPING: NOT DEFINED`——以上全是电学量，没有换算亮度或灰阶。

---

## 5. 三 corner 复验：ss 触发功能性失败

同一探针、同一批 flag，只把体端换成 `vss`；每个 corner 的归属都从**产出该数据的 deck 文件**
里读 `include ... section=` 核对（tt/ss/ff 三只 deck 各自 `section=tt/ss/ff`，且都含
`Mpass_local ... vss`；DATA-4 的三只冻结 deck 用同一方法复核，归属正确）。

| 量 | tt | ss | ff |
|---|---|---|---|
| DC `IOUT@1.2 V` | 14.931882 µA（−0.454 %） | 14.898749 µA（−0.675 %） | 14.964877 µA（−0.234 %） |
| `COMPLIANCE_1PCT` | 0.4600 V | 0.5000 V | 0.4200 V |
| `DC_STATIC_OFF_LEAKAGE` | 0.000005 µA | 0.000000 µA | 0.000027 µA |
| DC 门控压差（`VBIAS_SHARED − vbias_ch`） | 0.000000 V | 0.000052 V | 0.000000 V |
| `VBIAS_SHARED`（静态） | 0.884261 V | 0.951264 V | 0.818122 V |
| 导通整定 | 739.9 ns | **NOT_FOUND（4/4 未整定）** | 49.71 ns |
| 稳态 ON 电流 | 14.931810 µA | **8.1839–8.1880 µA** | 14.964877 µA |
| 相对 15 µA 误差 | 0.455 % | **45.44 %** | 0.234 % |
| 瞬态 `vbias_ch` 峰值（开关通道） | 0.884261 V | **0.902802 V（差 48.5 mV 到顶）** | 0.818122 V |
| `ADJACENT_POINT_ALTERNATION` | NO | NO | NO |
| checker 判定 | `DATA_DRIVER_TRAN: OK` | **`DATA_DRIVER_TRAN: FAIL`** | `DATA_DRIVER_TRAN: OK` |
| 受害 PEAK 串扰 / 电荷误差 | 4.80 % / 0.2131 % | 0.37 % / 0.2247 % | 36.85 % / 0.0976 % |

ss 的 FAIL 由 checker 自己下判，判据是 DATA-3.5 里已经评审过的
`POC_FUNCTIONAL_CRITERION`："ON 窗口内必须有 ≥40 % 时间待在 ±5 % 带内"。实测 4/4 个
ON 窗口都不满足，checker 原文：

> `IOUT does not stay inside +/-5% for 40% of the ON window in 4/4 ON windows — at this
> period the pixel is not regulated for most of the time it is selected`

机理与 §3 一致，且不是数值问题的冒充：`RINGING` 在三个 corner 都是 NO（交替幅度
0.000010 / 0.004094 / 0.000000 µA，远低于判据阈值），gear2only，maxstep 5 ns，与冻结版同一套
数值设置；ss 的 DC 曲线本身是好的（14.8987 µA、门控压差 52 µV），坏的是**帧内来不及**——
慢 corner 需要更高的 `VBIAS_SHARED`（0.9513 V），体效应把 Mpass 的过驱动吃光，局部栅节点
只能爬到 0.9028 V 就停住，镜像因此差 45 %。

顺带说明：ss 那一栏受害通道 PEAK 串扰只有 0.37 %，**不能当作优点**——它是因为开关通道
自己没正常导通，边沿注入随之变小。这个混淆已经在本报告里显式标注。

没有通过重新 sizing 去"修好" ss（评审 item 4：No re-sizing），也没有引入 Cbias 或新拓扑。

---

## 6. 隔离器件：只调查、只报名，不替换

按评审 item 5 的触发条件（普通 `n33` 不允许独立体端 **且** 体端接 `vss` 明确劣化功能）
确实成立，因此列出 PDK 实际提供的 3.3 V 隔离型 NMOS 器件主名（全部来自库目录清单、
`mosfets.Cat`/`rf_mosfets.Cat` 与本厂 LVS 器件表，**不是猜的**）：

```
ISOLATED_3V3_NMOS_AVAILABLE: YES
DEVICE_MASTERS (PDK 实际名称):
  smic18mmrf/n33_dnw_ckt        -- DNW 3.3 V 标称 VT NMOS（多端子：含阱节点与衬底节点）
  smic18mmrf/n33_dnw_4t_ckt     -- 四端子 DNW 3.3 V 标称 VT NMOS
  smic18mmrf/dnw33_ckt_rf       -- 3.3 V 四端子 DNW RF NMOS
  smic18mmrf/dnw33_6t_ckt_rf    -- 3.3 V 六端子 DNW RF NMOS（B / DNW / Psub 分开）
```

值得评审注意的一点（不做成结论）：冻结版的语义"体端与源极同节点"正好是 DNW 器件能做而
普通器件做不到的事——也就是说要恢复原来那套行为，需要改的是**器件主名**，不是拓扑。
DNW 的工艺代价是真实的：本 kit 的 techfile 对 DNW 规定了微米量级的最小宽度与间距
（远大于本单元的器件尺寸），具体条目见 `techfile.tf` 的 DNW min-width / min-spacing 行与
DRC 手册；另外 PCell 手册 §附注里提到 DNW MOS 的 guard-ring 选项可能与 LVS 冲突，需要手工
补 n 阱环。

**是否值得为 DNW 引入这些代价，由独立评审决定。本轮到此为止：未替换、未仿真任何 DNW 器件，
没有 Candidate F，没有新拓扑。**

---

## 7. 没做到的部分（如实记录）

* **OA 器件主单元的几何层内容没能读出来。** 想在版图上直接确认"普通 `n33` 有没有画 DNW"，
  三次尝试都没能通过这台机器的批量接口读到几何：
  1. `virtuoso -nograph` + `dbOpenCellViewByType(... "maskOnly" ...)`：viewType 被拒
     （`DB-270208 unrecognized database viewType`）；
  2. 改 `viewType=nil` 后拿到对象，但属性/图形读取全为 nil——这台 build 的 SKILL 解析器
     **不接受 `~`**（在 `~` 处直接 syntax error，已用最小样例二分确认：`~` 报错、`->` 通过）；
  3. 换 `dbAccess -load`：cellview 句柄有效，但 `dbGetFigures` / 属性读取一律返回 nil，
     `ddGetObj(...)->figs` 也是 0 个图形（该库每个 cell 带 `data.dm`，可能需转换或需完整
     GUI 上下文；PDK 自带 `batchSetCDF.ile` 在批量模式下也因 `ciwMenuInit` 缺失而中断，
     CDF 参数因此读不到）。
  结论依据因此来自本厂 LVS 器件识别 + PCell 手册 + 目录/层名这三条可读文本证据；几何级
  证据缺口保留在这里，不当已证。
* corner 归属打印有一个真 bug（deck 在 `generated/` 而非 `generated/sim/`，`grep` 找错目录
  静默失败）。本轮已改成从正确路径读 `include ... section=` 并逐 deck 复核；
  DATA-4 的数字另用手工核对确认归属正确（三只 deck 各自 `section=` 与标签一致）。

---

## 8. 状态

```
N33_BODY_ISOLATION:              NOT_SUPPORTED          （证据类型 FOUNDRY_DEVICE_DEFINITION）
MPASS_BODY_FINAL:                vss                    （候选可实现接法，功能在 ss 不成立）
BODYFIX_REQUIRED:                YES
TT_RECHECK:                      PASS
BASIC_PROCESS_CORNER_RECHECK:    FAIL_AT_SS             （tt PASS / ss FAIL / ff PASS）
DATA_DRIVER_1CH:                 BLOCKED_PENDING_BODY_DECISION
ISOLATED_3V3_NMOS_AVAILABLE:     YES
E_TRANSIENT_RESULT（DATA-3.5 事实保持）: MIXED_NUMERICAL_AND_PHYSICAL
FULL_PVT_SIGNOFF:                NO
REVIEW_HEAD_SHA:                 见随本文件提交的 review bundle 名与 manifest（本文件不写自己的 SHA，
                                 写了就必然过期）；远端此刻仍停在 DATA-4 的 `093cbcc` =
                                 PUSH_PENDING_NETWORK（github.com:443 三次不可达，含 curl 000；
                                 未改任何传输/全局配置）
NEXT:                            人工评审 —— 在 (a) 接受 ss 失败并把 POC 范围限定为
                                 tt/ff，或 (b) 用 PDK 的 DNW 3.3 V NMOS 恢复原语义
                                 之间选择
```

工件：`results/data_driver_Ebodyfix_corner_{dc,transient,xtalk}.csv`、
`results/evidence/bodyfix_{tt,ss,ff}_{on,off,ch0,victim}.txt`（12 份）、
`results/evidence/bodyfix_3corner_pipeline.log`（含每 corner 的 deck 名与 run header）、
`results/evidence/bodyfix_curve_diff.csv`、
`skill/pdk_body_probe.il`、`skill/pdk_lib_diag.il`、`skill/pdk_lib_diag2.il`、
`skill/pdk_well_probe.il`。
