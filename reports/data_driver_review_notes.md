# Data Driver 1CH —— 独立源码 Review 说明（第二轮 review 的入口文件）

状态：`DATA_DRIVER_AGENT_POC: PASS` / `INDEPENDENT_SOURCE_REVIEW: READY`。
本轮把成果冻结成可审状态：**没有**改 topology、**没有**重调 W/L、**没有**加候选、**没有**建 schematic。
`reports/ddrv_topology_summary.md` 与器件表/应力表都是 `scripts/ddrv_topology.py` 从 netlist 现读现生成的。

## Task（本轮做到哪、明确不做到哪）

做：一路 15 µA Micro LED data driver 最小单元；候选比较；DC 输出特性与 compliance；
DATA_EN 开/关；两个时间尺度的 transient；三个工艺角探针；机检 checker。
不做：384 通道、数据锁存/移位、SPI、灰阶/PWM、TCON、schematic、layout、DRC/LVS/PEX、
Monte Carlo、完整温度扫描（**这些是课程阶段安排，不是遗漏**）。

## Requirement 标签（每条只有一个标签，机检 `scripts/provenance_check.py`）

| 条目 | 标签 | 依据 |
|---|---|---|
| `I_PIXEL_ON = 15 µA`，像素被选通发光期间的**瞬时**电流 | `COURSE_REQUIREMENT` | 正式题目文字 + 用户 2026-10-04 的 D1 定义 |
| 数据通道做**低侧电流吸收**（`DATA_OUT → sink → VSS`） | `ENGINEERING_TOPOLOGY_CHOICE` | 用户本轮给的基本方向；**正式题目文字与已核实的图里没有唯一确定这一侧**，见下面 REVIEW_PREP_BUG_FOUND |
| "数据驱动 = 行驱动、恒流吸收"这句话的原始出处 | `GPT6_LEGACY_PROPOSAL` | 只出现在旧 GPT-6 交付包（抽取件 `spec_v12_text.txt` L112 等），**不升级成老师硬要求** |
| 列周期 9.765625 µs = 1/(1024 × 100 Hz) 只作时间尺度参考 | `ENGINEERING_DERIVATION` | 由题面 1024 列与 60–100 Hz 直接算出 |
| `VDD=1.8 V`、`RSEN=10 kΩ`、`vcas=1.8 V`、`±1/2/5%` 判据、1 ns 边沿、扫到 1.65/3.15 V | `POC_ASSUMPTION` | 题目未给，为本轮比较拓扑而设，不是指标 |
| `Vf`、`VLED`、灰阶位数、PWM/PAM、消隐占比、数据协议、复用系数 | `NOT DEFINED` | **未代入任何计算**；因此 compliance 只报"需要多少输出电压"，不声称真实工作点 |

### REVIEW_PREP_BUG_FOUND（准备 review 时发现的报告级 bug，不影响任何数值）

`reports/data_driver_1ch_result.md` 第一版把"低侧 current sink"标成了 `COURSE_REQUIREMENT`，依据写的是"用户本轮明示"。
**这是过度声明**：用户给的是本轮 POC 的架构方向，不是题目硬要求；而"恒流吸收"的书面出处属于旧 GPT-6 交付包。
本轮已把该条改成 `ENGINEERING_TOPOLOGY_CHOICE` + 把旧文档线索标成 `GPT6_LEGACY_PROPOSAL`，
并给 `scripts/provenance_check.py` 增加 `ENGINEERING_TOPOLOGY_CHOICE` 这个**非课程级**标签（附注释：不得用它声称题目要求）。
影响范围：只影响文档表述，**不影响** `DATA_DRIVER_1CH: PASS` 的任何测量值或判据。

另一条同类披露：已提交的 50 个 `spectre/generated/ddrv_*.scs` deck 里 `save` 行不含 `data_en/data_en_b`
（生成器后来加了，用于应力提取）。当时的结果文件与当时的 deck 是一致的；新的 stress 表来自
补跑的同参数 deck，deck 未提交（PSF 不进 Git）。

## Circuit —— 最终单元（每通道 2 只，共享块 4 只）

```
  DATA_OUT (pad / LED 阴极侧)
      |                     RSEN 10k 与 ideal Vout 都在通道之外（上方）
      +-- Mcas  n33  L=2e-6 W=2e-5   gate = vcas (=1.8 V)
      |            node_m
      +-- Mout  n33  L=2e-6 W=2e-5   gate = vbias
      |
     vss  (= Spectre 参考节点 0，显式由 Vss 源接上)

  共享偏置/门控块：
   vdd --[IREF ideal 15u]--> ref_top
   Msteer (d=ref_top g=data_en   s=vbias b=vbias)   开启时把参考电流接到镜像栅
   Mdummy (d=ref_top g=data_en_b s=vss   b=vss)     关断时吸收那 15 µA，ref_top 不浮空
   Mbleed (d=vbias   g=data_en_b s=vss   b=vss)     关断时把 vbias 放到 0
   Mref   (d=vbias   g=vbias     s=vss   b=vss)     二极管接法，与 Mout 同尺寸 -> 1:1
```

器件表（instance/model/W/L/m/D/G/S/B/role）与**实测端电压应力表**由
`scripts/ddrv_topology.py` 从 deck 解析生成，见 `reports/ddrv_topology_summary.md`，不手抄。

### 应力（ON 扫描实测最大值，只报电路里真出现过的端电压，不复制任何模型参数）

| device | max abs VGS | max abs VGD | max abs VDS |
|---|---|---|---|
| `Mcas` | 1.1475 V | 1.3505 V | **2.4980 V** |
| `Mout` | 0.8843 V | 0.2317 V | 0.6525 V |
| `Mref` | 0.8843 V | 0.0000 V | 0.8843 V |
| `Msteer` | 0.9157 V | 0.8518 V | 0.0640 V |
| `Mdummy` | 0.0000 V | 0.9482 V | 0.9482 V |
| `Mbleed` | 0.0000 V | 0.8843 V | 0.8843 V |

这条同时是 **n33 而不是 n18** 的关键证据之一：`Mcas` 的漏-源要承受 2.50 V，1.8 V 家族根本不允许。
`DEVICE_STRESS: EXTRACTED`（六只管子的三个端差全部提取成功，没有需要标 `REVIEW_REQUIRED` 的）。

## Enable 行为（不是"DATA_EN=0 所以关"这种一句话）

1. `Msteer` 的栅由 `data_en` 控制：关断时它断开，参考电流到不了 `vbias`。
2. `Mdummy` 的栅是 `data_en_b`：关断时它把整 15 µA 从 `ref_top` 吸到 `vss`，所以 `ref_top` 不会浮到 `vdd`，
   参考管本身仍被偏置着 —— 这是"转向 (steer)"而不是"切断参考"。
3. `Mbleed`（栅 `data_en_b`）把 `vbias` 拉到 ~0 V：`Mout` 的 `VGS<=0` 关断；`Mcas` 栅仍为 `vcas` 但已无电流可传。
4. 实测到的 OFF 电流路径：`Mout` 与 `Mcas` 串联的子阈值导电（`VGS≈0`，`VDS` 是整个输出电压）
   加上 `data_out`/`node_m` 的结泄漏。DC 扫到 3.3 V 时测得 **5 pA**。课程没给泄漏指标，所以这是
   **REPORTED, NOT_SPECIFIED**。

### SCALABILITY_CONCERN_FOUND（重要，留给 reviewer 判断，本轮不改电路）

`vbias` 是**一个共享节点**，而把它放地的 `Mbleed` 受**本通道** `data_en_b` 控制。
若 384 通道共用这一个 `vbias`，任何一路关断都会把共享栅电压拉下去，把别的路一起关掉。
也就是说：本轮 PASS 的门控结构在"一路 + 一组共享偏置"的语境下成立，但**不能按原样**扩展成
"多路各自独立 ON/OFF + 一个共享 VBIAS"。可行的扩展方式（都要改电路，故本轮不做）：
每通道复制 steer/dummy/bleed 三只（则每通道变 5 只，共享块的意义消失）；
或改成共享 `vbias` 常开 + 通道内本地开关（即 `A_series` 那条，代价是 +1.24 V 余度）；
或数据转向到 cascode 级/源侧的其它拓扑。

## Testbench 与全部理想源（"设计" vs "testbench 帮忙"）

| 项 | 值 | 分类 |
|---|---|---|
| `Vdd (vdd 0) vsource dc=VDDV=1.8` | 理想电源 | `POC_ASSUMPTION`（1.8 V 核心域由工艺给定） |
| `Vss (vss 0) vsource dc=0` | 显式把衬/源网络接参考节点 0 | 必需项（preflight 强制） |
| `Iref (vdd ref_top) isource dc=15u` | **理想 15 µA 参考电流** | `IDEAL IREF = TESTBENCH ASSUMPTION` |
| `Vcas (vcas 0) vsource dc=1.8` | **理想共源共栅栅压** | `POC_ASSUMPTION`，不是已设计的偏置堆叠 |
| `Vout (vsw 0) vsource dc=<swept>` | 输出电压当独立扫变量 | `POC_ASSUMPTION`（Vf/VLED 未定义，故不建 LED） |
| `Rsen (data_out vsw) resistor r=1e4` | 电流采样电阻 | `POC_ASSUMPTION`（同时限制扫到的最高电压，见限制） |
| `Vde/Vdeb (data_en / data_en_b 0)` | 理想互补使能驱动 | `POC_ASSUMPTION`，未建模本地锁存 |

**当前 PASS 不代表 reference generator 已设计完成。** 真实的共享 bias/reference 系统是下一阶段的事。

## IOUT 的定义（不允许方向含糊）

```
IOUT = ( V(vsw) - V(data_out) ) / RSEN          # 见 scripts/ddrv_characterize.py, ddrv_tran.py
正方向：电流由测试源经 RSEN **流入** DATA_OUT 再往下到 VSS，即"吸收"为正
```

不用 `save i(...)`：这个 build 对 `save i(Vout)` 报 SFE-874、对 `save Vout:current` 报
SPECTRE-8059/8287 并忽略之 —— 与其留下被忽略的 warning，不如把电流定义在显式电阻上。
**绝对值只出现在两处并明说**：OFF 泄漏与峰值电流按幅值报告（`abs(IOUT)`）；
ON 误差、compliance 判据、瞬态带判据都用带符号的 `IOUT`，且 `err = (IOUT − 15µA)/15µA`。

## Compliance 的提取办法（不是只给一个数）

- 判据：`|IOUT − 15µA| <= tol × 15µA`，tol = 1 % / 2 % / 5 %（`POC_ASSUMPTION`）。
- 定义：从扫描到的采样点里找**最低**的 `V(data_out)`，使得**它之上所有**点都落在带内
  （不是"第一个碰巧在带内的点"）。所以一个"合规点"意味着整个上半区间都在带内。
- 实现：直接取采样点，**不做线性插值** —— 因此膝点分辨率等于扫描步长。
- 因此步长敏感，两组都留下：`step=0.02 V` → ±2%/±5% = 0.2129/0.1157 V；
  `step=0.05 V` → 0.2526/0.1538 V。±1% 膝点两组都是 0.4515 V（那里曲线本来就平）。
- 上部受 `RSEN=10 kΩ` 限制：15 µA 时它自己吃掉 0.15 V，所以扫 3.3 V 时设备端最高只到 ≈3.15 V。

## Validation（两个层面必须分开）

```
FUNCTIONAL VALIDATION
  DATA_DRIVER_1CH (aggregate checker) : PASS   (ON 误差 / OFF / compliance / 单调 / 重复性)
  TESTBENCH_PREFLIGHT                 : PASS   (并有"删掉 Vss 就必须 FAIL"的 selfcheck)
  DATA_DRIVER_TRAN                    : OK     (按 ON/OFF 窗口分别计算)
  SOURCE_PROVENANCE_CHECK             : PASS
  DEVICE_COUNT_CHECK                  : PASS   (C2MOS 那 18 只管不受影响；本单元 6 只管由 deck 解析)

NOT DONE / NOT CLAIMED
  PVT                          : BASIC PROCESS CORNER PROBE ONLY（tt/ss/ff，同一套 W/L）
  电压扫描 / 温度扫描 / mismatch / Monte Carlo : 未做 -> 不能写 PVT SIGNOFF PASS
  timing characterization      : 不适用（本单元不是时序单元）
  reference/bias generator 设计 : 未做（本轮理想源）
```

## 已知失败与 bug 历史（不许只报成功）

1. `A_series`（串在电流路径里的开关）**被证据否决**：同一尺寸的 ±5% 膝点是 **1.357 V**，
   所以 1.2 V 测试点根本不在恒流区；瞬态四个 ON 窗口全部 `NOT_FOUND`，并有 **80.7 µA** 的等电位冲击
   （关断时 `mid` 放到 0，再开通时要经 10 kΩ 重新充电）。n33 与 n18 两种开关都跑了，结论一致。
2. `B_gate`（只有一条管子 + 门控偏置）**调节不足**：整程电流跨度 **9.17 %**，最高点误差 **+5.0 %**，
   ±1% 无解。膝点最低（0.116 V）是它的优点，但精度不够。
3. `C_cascode` 被选，但不是"看起来高级"：它在同等膝点下把误差压到 −0.36 %、rout 提到 1.3×10⁸ Ω。
4. 瞬态指标第一版有**两个真 bug**：搜索整条曲线导致跨周期借样本（200 ns 周期报出 837 ns 建立时间），
   以及 OFF 采样点落进下一个 ON 窗口（把 12 µA 报成"OFF 泄漏"）。看波形后改成按窗口计算并**全部重跑**；
   `scripts/ddrv_dump.py` 和这段说明留在仓库里。
5. 一次 `guest.sh pull` 用 guest 上的旧副本覆盖了 5 个已审 C²MOS 结果 CSV（少 267 行）。
   已还原成已审内容、外来副本移到 `review/`（ignored）留档，规则进 `AGENTS.md` 第 26 条。
6. 门控偏置的建立时间由 `vbias` 再充电决定：慢周期(9.77 µs)下进入 ±5% 要 200–442 ns，
   比快周期(200 ns)的 37–44 ns 大一个数量级 —— 关断窗口越长 `vbias` 放得越空。
7. `vcas` 扫过 1.8/2.0/2.2/2.4 V：±1% 膝点完全不变，误差从 −0.36 % 单调移到 +0.36 %。
   说明 1.8 V 域就能偏置，**不需要升压**；但真实的偏置堆叠仍未设计。
8. 三个工艺角是固定一套 W/L 的探针，**没有**逐角重调尺寸；无温度/电压扫描、无 mismatch/MC。
9. 未做：384 通道、锁存/移位、SPI、灰阶/PWM、TCON、schematic、layout、DRC/LVS/PEX。

## Questions for reviewer（本轮必须由 reviewer 定的 5 点）

1. `Mout + Mcas` 两管 cascode 电流吸收 + "共享转向/泄放门控"这套 bias 方法是否合理？
   （注意 `SCALABILITY_CONCERN_FOUND`：`vbias` 共享与单通道 `Mbleed` 互相冲突）
2. 选 `n33` 而不是 `n18` 是否被现有证据支持？依据是实测输出范围（1.65 V vs 3.15 V）、
   应力表（`Mcas` 的 VDS 达 2.498 V）与 OFF 泄漏低一个数量级；但 `Vf/VLED` 未定义，
   如果最终 VLED 让 `DATA_OUT` 超过 3.3 V，本 PDK 没有合法单管。
3. `VCAS = 1.8 V` 的理想偏置可以作为 POC 保留，还是"最小单元"里就必须先把 bias ladder 做出来？
4. 当前 shared steer/bleed 门控是否真的适合未来多通道独立 ON/OFF？如果不行，
   下一轮该走哪条：每通道本地开关（付 +1.24 V 余度）、源侧转向、还是别的结构？
5. 现在的 compliance / transient checker（采样点膝点、按窗口建立判据、10 kΩ 采样电阻定义电流、
   preflight 平板路径 + selfcheck）是否足以证明这个 POC 可以进 Virtuoso schematic 阶段？

## 复现

```bash
bash scripts/ddrv_run.sh selfcheck
bash scripts/ddrv_run.sh dc   C_cascode n33 2e-6 2e-5 tt 3.3 0.02
bash scripts/ddrv_run.sh tran C_cascode n33 2e-6 2e-5 9.765625e-6 1.2 tt 1e-9
bash scripts/ddrv_verify.sh                       # DATA_DRIVER_1CH: PASS / FAIL
python scripts/ddrv_topology.py <deck> --stress <psf>   # 器件表 + 应力表（PSF 不进 Git）
```
