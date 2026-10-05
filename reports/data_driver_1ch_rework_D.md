# DATA-2 rework —— 把门控下放到本通道 cascode 栅（Candidate D）实测结果

日期 2026-10-05，分支 `poc/data-driver-1ch`。上一轮独立 review 的结论是
`REVIEW DECISION: REWORK`，范围限定为：恒流核心 `Mout + Mcas`（n33，W=20 µm / L=2 µm）**已接受、不动**，
要改的是"共享 VBIAS + 每通道 Mbleed"这套门控不能支撑多通道独立开关。

```
DATA_DRIVER_1CH_REWORK : FAIL
TWO_CHANNEL_INDEPENDENCE : FAIL   (静态 0.000 % PASS，动态 19.4 % 超 1 % 判据)
DEVICE_STRESS_REVIEW_REQUIRED : YES (关断态 Mcas |VGD| = |VDS| = 3.30 V)
BASIC_PROCESS_CORNER_PROBE : NOT_RUN (前置条件"D 在 TT 完整 PASS"未满足，见判定一节)
SELECTED_TOPOLOGY      : 无（本轮不宣布新选择；C 仍作为 FUNCTIONAL_SINGLE_CHANNEL_BUT_NON_SCALABLE 保留）
```

## 1. Candidate D 是什么（唯一改动就是门控位置）

```
   vsw --[RSEN 10k]-- o data_out
                        |
                     Mcas  n33 W=20u L=2u   gate = DATA_EN   <-- 门控搬到这里
                        |
                     node_m
                        |
                     Mout  n33 W=20u L=2u   gate = VBIAS_SHARED  (常开)
                        |
                      vss (= 参考节点 0)

   共享偏置（常开，不再被任何通道拉放）：
   vdd --[ ideal IREF 15u ]--> vbias --o Mref (diode) --> vss
```

按 review 要求删掉的器件：`Msteer`、`Mdummy`、`Mbleed`、理想 `VCAS` 源、`DATA_EN_B`。
每通道 2 只，共享块 1 只（`Mref`）；参考那 15 µA 在任何通道关断时仍然消耗，属共享 bias overhead，
本轮只报告不作 blocker。清单与应力由 `scripts/ddrv_topology.py` 从 deck 现读生成，见
`reports/ddrv_D_topology_summary.md`。

## 2. 恒流核心没有被改变（166 点逐点比对，不是"看起来一样"）

| 量 | 已接受的 C（vcas=1.8） | Candidate D（gate=DATA_EN） |
|---|---|---|
| IOUT @ 扫描最高点 | 14.946478 µA | 14.946478 µA |
| 误差 | −0.357 % | −0.357 % |
| ±1 % 合规点 | 0.4515 V | 0.4515 V |
| ±2 % / ±5 % 合规点 | 0.2129 / 0.1157 V | 0.2130 / 0.1161 V |
| rout（上 40 %） | 1.29e8–1.36e8 Ω | 1.356e8 Ω |
| 两条 ON 曲线在 166 个相同采样点上的最大差 | —— | **0.000001 µA = 0.0000 %**（平均 3.1e-7 µA） |

ON 时 `Mcas` 的栅压在两个结构里都是 1.8 V，所以这既是合理性检查也是复现验证：它通过了。

## 3. 静态独立：PASS，而且干净到 1e-6 µA

两个完全相同的 D 通道共享同一 `vbias`，两路输出都固定在 1.2 V，四种使能组合各取稳态：

| EN0 | EN1 | I0 (µA) | I1 (µA) |
|---|---|---|---|
| 0 | 0 | 0.000000 | 0.000000 |
| 0 | 1 | 0.000000 | 14.931812 |
| 1 | 0 | 14.931812 | 0.000000 |
| 1 | 1 | 14.931813 | 14.931813 |

```
dI1 = |I1(EN0=1) - I1(EN0=0)| = 0.000001 uA = 0.000 % of 15 uA   -> ok  (判据 1 %)
dI0 = |I0(EN1=1) - I0(EN1=0)| = 0.000001 uA = 0.000 % of 15 uA   -> ok
STATIC_INDEPENDENCE : PASS
```

也就是说 D 修对了上一轮那个致命点：**一个通道关断不再把共享 `vbias` 拉走**（旧结构的 `Mbleed`
正是干这件事的），关掉的路自身电流也确实为 0（≤1 pA）。

## 4. 动态独立：FAIL —— 邻居的使能沿会在被观察通道上打出 2.8 µA 毛刺

CH1 使能常高、输出常 1.2 V，让 CH0 反复开关（沿速率 1 ns）：

| 周期 | CH1 均值 | CH1 相对自身均值的最大偏移 | CH1 最坏 \|I−15µA\| | 最差样本与邻居沿的距离 | 共享 VBIAS |
|---|---|---|---|---|---|
| 200 ns | 15.152531 µA | 2.833623 µA | 2.911317 µA = **19.409 %** | 1.8 ns | 0.8605..0.9065 V（p-p 46 mV） |
| 9.765625 µs | 15.113902 µA | 2.795105 µA | 2.908760 µA = **19.392 %** | 1.8 ns | 同上 |

机制核查（不是猜测，是两条独立测量）：

1. 毛刺**只**出现在邻居使能沿附近（最差样本距沿 1.8 ns，一个采样步以内）。
2. 把邻居的沿从 1 ns 放慢到 100 ns，同一条件下偏移从 2.834 µA 降到 0.440 µA（6.4 倍），
   仍超 1 % 但强烈指示这是**容性馈通**：`dV/dt` 通过 `Mcas0`/`Mout0` 的栅漏电容注入共享 `vbias`，
   而 `vbias` 正是 CH1 中 `Mout1` 的栅 —— 实测 `vbias` 摆动 46 mV，与 2.8 µA 的电流响应在跨导
   （15 µA 时 gm ≈ 75–120 µS）量级上自洽。
3. 静态 dI=1e-6 µA 说明直流路径上没有共享电阻性问题，问题纯在动态馈通与共享节点的阻抗。

```
DYNAMIC_INDEPENDENCE : FAIL (19.4 % >> 1 % POC 判据)
TWO_CHANNEL_INDEPENDENCE : FAIL
```

结论：把门控搬到 cascode 栅**消除了直流串扰**，但因为每个通道的开关沿仍要经过那个所有通道共用的
`vbias` 节点，动态上通道之间并不独立。要真正独立，`vbias` 必须在电气上"硬"起来（低阻抗去耦/局部缓冲
镜像栅），或者门控干脆回到通道内部（即 `A_series` 那条，代价 +1.24 V 余度）—— 这两条都改电路，
按本轮指示不做。

## 5. 关断态应力：本轮 D 的第二条硬伤

| device | 状态 | max abs VGS | max abs VGD | max abs VDS |
|---|---|---|---|---|
| `Mcas` | ON | 1.1475 V | 1.3505 V | 2.4980 V |
| `Mcas` | **OFF (DATA_EN=0)** | 0.0000 V | **3.3000 V** | **3.3000 V** |
| `Mout` | ON | 0.8843 V | 0.2317 V | 0.6525 V |
| `Mout` | OFF | 0.8843 V | 0.8843 V | 0.0000 V |
| `Mref` | 两态 | 0.8843 V | 0.0000 V | 0.8843 V |

门控搬到 `Mcas` 栅之后，关断时该管要独自吞下**整个输出电压摆幅**，而且是加在**栅-漏**上
（gate=0，drain=3.3 V）。3.3 V 家族的管子在工作里出现 `\|VGD\| = 3.3 V` 属于栅氧应力问题，
需要按 foundry 的极限规则复核 —— 因此：

```
DEVICE_STRESS : EXTRACTED（六项全部提取到，没有靠猜）
DEVICE_STRESS_REVIEW_REQUIRED : YES（关断态 Mcas 的 VGD/VDS 都是 3.30 V）
```

对上一轮"n18 绝不允许"的说法这里保持谨慎：按当前 PDK 的电压族与实测 ≈2.5 V 以上 `VDS`，
`n33` 仍是当前正确的工程选择；**精确 absolute maximum 以 foundry 文档为准**，不由本仓库下结论。

## 6. 单通道瞬态：D 的建立时间确实比旧结构快一个量级（这是它的优点，也记录下来）

| 条件 | C（上一轮，门控偏置） | D（本轮） |
|---|---|---|
| T=200 ns，VOUT 1.2 / 3.0 V | 44 / 40 ns | **7.7 / 6.6 ns** |
| T=9.765625 µs，VOUT 1.2 / 3.0 V | 398 / 442 ns | **157 / 44 ns** |
| 关断 | 7.5–299 ns | 1.0–14 ns（3.0 V 慢周期 1.6 µs 见 §7） |
| 峰值 | 19.9–20.8 µA | 32.1–33.4 µA |
| 每周期 VBIAS 是否被放到 0 再充 | **是**（这是慢的主因） | **否**，常开，仅 46 mV 纹波 |

## 7. 本轮没有解释完、也不掩饰的观测

1. 低输出电压点（源 0.50 V / 0.65 V，扣除 `RSEN` 的 0.15 V 后器件端 0.35 / 0.50 V，正好压在
   ±1 % 膝点附近）出现：峰值 73–80 µA，慢周期下 `TURN_ON_SETTLING = NOT_FOUND`
   且 OFF 窗口尾部仍有 3.38 µA。同一个测试点当初选 0.5 V 是我的疏忽 —— 忘了 `RSEN` 压降会把器件端
   拉到膝点之下（0.05 V 步长下 ±2 %/±5 % 膝点 0.253/0.154 V 也一样受影响）。
   我把它作为**未解释观测**留着，不当成 D 的判据（D 已经因 §4/§5 失败），也不改判据去凑 PASS。
2. `VOUT` 高端（3.0 V）时 OFF 泄漏随输出电压上升（DC 4 pA@3.3 V；瞬态窗口 20–80 pA），
   与 `Mcas` 关断时吞下全部电压的图像一致。

## 8. 本轮工具与流程缺陷（都是我自己的，全部已修并留此记录）

1. `build_D()` 第一版漏写 `Vdd/Vss` 两个源 —— 被 preflight 在仿真**之前**拦下。
2. 遗留的 `--vout` 文本替换对 D 二次生效，把 `dc=0.5` 变成 `dc=0.5.5` —— 同样被 preflight 拦下
   （SFE-691），所以没有产出任何错误数字。
3. `ddrv_twochan.sh` 里 `mean_of` 的匹配串漏了通道 0（标签是 `I_0 mean` 而不是 `I_ mean`），
   于是通道 0 的稳态值被当成"无数据"，一度让我把**静态**独立判成 FAIL。修好后静态是 0.000 % PASS。
   这条特别写出来：一个静默返回空的 grep 就能颠倒结论。
4. 双通道判定的汇总行原先可能漏掉子结果（该 FAIL 时仍打 PASS），已改成显式两行汇总 + 退出码。
5 个已审判据工具（`ddrv_characterize.py`、`ddrv_tran.py`）只加了可选的 `--net-suffix/--ensig`
参数，判据本身一字未改。

## 9. 判定与保留物

| 判据（review 给的 6 条） | 结果 |
|---|---|
| ON current regulation | PASS（与已接受曲线 1e-6 µA 内一致） |
| OFF behavior | PASS（DC 4 pA；关断态应力另计） |
| compliance | PASS（±1 % 从 0.4515 V） |
| transient | 部分：建立快 5 倍，但低电压测试点未达标（§7.1），且邻居沿造成被观察通道 19 % 扰动 |
| device stress extraction | 提取成功，但**结论是 `DEVICE_STRESS_REVIEW_REQUIRED`**（§5） |
| TWO_CHANNEL_INDEPENDENCE | **FAIL**（§4） |

六条没有同时满足，所以：

```
DATA_DRIVER_1CH_REWORK : FAIL
```

按指示**没有**退回旧的 shared-bleed 结构去写 PASS；旧 Candidate C 继续作为
`FUNCTIONAL_SINGLE_CHANNEL_BUT_NON_SCALABLE` 的反例保留（decks、CSV、报告与 Git 历史都在）。

## 10. 给下一轮 reviewer 的问题

1. 静态已 0.000 % 独立、动态 19 % —— 判定门控是否可接受的标准应该是"沿扰动幅度 × 持续时间"还是
   仅稳态差值？如果按前者，D 需要给 `vbias` 加低阻抗去耦/局部栅缓冲（会加管子），还是接受 +1.24 V 余度的
   路径内开关？
2. 关断态 `Mcas` 的 `|VGD| = |VDS| = 3.30 V`：3.3 V 家族里这种接法是否直接否决 D，还是可由
   输出电压上限（VLED/Vf 一旦确定）自然解除？
3. `VOUT` 低端的未解释观测（§7.1）：要不要我下一轮先把 `RSEN` 换成 1 kΩ（纹波/压降小 10 倍）
   再复测低电压点，以区分"testbench 驱动假象"与真实行为？
4. 本轮 `BASIC_PROCESS_CORNER_PROBE` 因前置条件未满足而 NOT_RUN —— 是否同意，还是要求 D 无论如何
   都先给三角直流数据以便对比？

## 复现

```bash
bash scripts/ddrv_twochan.sh                     # 静态 2x2 + 动态邻居沿 -> TWO_CHANNEL_INDEPENDENCE
bash scripts/ddrv_run.sh dc   D_local n33 2e-6 2e-5 tt 3.3 0.02
bash scripts/ddrv_run.sh dc   D_local n33 2e-6 2e-5 tt 3.3 0.02   # 加 EXTRA="--en 0" 测 OFF
bash scripts/ddrv_run.sh tran D_local n33 2e-6 2e-5 2e-7 1.2 tt 1e-9
python scripts/ddrv_topology.py <deck> --stress <psf>   # 器件清单 + 应力表
```

数据文件：`results/data_driver_dc.csv`（含 D 的 ON/OFF 全曲线）、`results/data_driver_transient.csv`、
`results/data_driver_xtalk.csv`（静态/动态逐例）、`results/evidence/ddrv_D*.txt`、
`reports/ddrv_D_topology_summary.md`。PDK、模型卡、deck、原始 PSF 一律不在仓库里。
