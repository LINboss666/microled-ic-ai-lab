# c2mos_tb_cdf_audit.md — C²MOS 图形化 Testbench 修复前只读审计

审计对象：`microled_cells/c2mos_dff_tb/schematic`（guest `/root/microled_ai_project/cadence_work/microled_cells/`）
审核基准：commit `2aea10171d7ca80a4d85599ffa63df60a8dccd0e`，branch `gexing321/scan-driver/c2mos-schematic`
本轮性质：**只读**。未写入任何 OA cell、未改脚本、未改 PDK/analogLib/model/display.drf、未删建 cell。
原始证据：`results/evidence/c2mos_tb_cdf_audit.txt`（SECTION A–F，全部为命令原文）

---

## 0. 先更正上一轮的结论（这条最重要）

上一轮报告 `reports/c2mos_testbench_build_report.md:14` 写的是：

> ASG 没有把激励参数带进 OA 库 … `dc/val0/val1/period/delay/width/rise/fall` 在属性和 CDF 里都不存在
> ⇒ `c2mos_dff_tb` 不能充当验证载体

**这句话是错的，错因是查询用错了名字。** 黄金 deck 里的 `val0/val1/period/delay/width/rise/fall` 是
**Spectre 组件参数名**；`analogLib` 的 CDF 字典给这些量起的名字是 `v1/v2/per/td/tr/tf/pw`，两者的对应关系
写在厂商 `data.dm` 的 `propMapping` 里。用 Spectre 名字去查 OA 实例，查到的当然为空——这不能证明值不存在。

实测结论（SECTION E，机检 20 行全对齐）：

```
TB_CDF_CHECK: PASS     ROWS=20 BAD=0
```

**黄金激励的 20 个数值全部已经在 OA cell 里，raw 属性层和 CDF 层都在。** `c2mos_dff_tb` 的激励部分不是
"空壳"，它是一个数值完整、连接正确的 testbench。它缺的不是参数值，而是**仿真分析设置**（见 §1.2、§6）。

对应关系不是我推出来的，是从两处实测对出来的：
- 厂商侧：`analogLib/{vdc,vpulse,cap}/data.dm` 的 `parameters` 段与 `propMapping` 段（SECTION A）。
- 实例侧：ASG 自己写的 raw 属性就叫 OA 名字——`Vdd` 实例上存的是 `vdc=1.8`（不是 `dc=1.8`），
  而黄金 deck 那行写的是 `dc=VDDV`；`Ck` 实例上存的是 `per=2e-07`，而 deck 写的是 `period=2e-07`
  （SECTION B `TBCA-RAWPROP`）。即 `propMapping` 的对偶方向是 **(spectre 名 → OA 名)**，这一点由导入结果本身证明。

---

## 1. 当前 Testbench 缺少哪些参数

### 1.1 激励参数：不缺

| 实例 | master（实测） | raw 属性 | CDF 值 | 对黄金 |
|---|---|---|---|---|
| `Vdd` | analogLib/vdc:symbol | `vdc=1.8` `model=vdc` | `vdc=1.8` `srcType=dc` | 等值 |
| `Vss` | analogLib/vdc:symbol | `vdc=0` `model=vdc` | `vdc=0` `srcType=dc` | 等值 |
| `Ck` | analogLib/vpulse:symbol | `v1=0 v2=1.8 per=2e-07 td=1e-07 pw=1e-07 tr=1e-09 tf=1e-09 model=vpulse` | `200n/100n/100n/1n/1n` | 等值 |
| `Dd` | analogLib/vpulse:symbol | `v1=0 v2=1.8 per=4e-07 td=7e-08 pw=2e-07 tr=1e-09 tf=1e-09 model=vpulse` | `400n/70n/200n/1n/1n` | 等值 |
| `Cq`/`Cqb` | analogLib/cap:symbol | `c=5e-14 model=cap` | `c=50f` | 等值 |
| `X1` | microled_cells/c2mos_dff_1bit:symbol | `model=c2mos_dff_1bit` | — | 6/6 端口绑定（§4） |

结构计数：`instances=8 nets=7 terms=0 shapes=53 labels=0`。8 个实例 = 6 个电气源/负载 + `X1` + 一个 `basic/iopin`
（`PIN0`，见 §4）。`c=5e-14` 与 `50f` 是同一数值的不同写法（Cadence 会把数量纲归一化成 `50f`），比较必须按数值
不按字符串，即 AGENTS.md 第 29 条；本轮机检就是这么做的。

### 1.2 真正缺的三样东西（都不是"参数值"）

1. **仿真分析设置**：被导入的 `spectre/import/c2mos_dff_tb.scs` 里没有 `tran`、没有 `save`、没有任何 `analyze`
   语句（原文见 SECTION B 前的 deck 快照）；cellview 上也没有 ADE 会话状态。
   根因在生成脚本：`scripts/c2mos_tb_build.py:70-71` 解析出了 `tran stop=/maxstep=`，但 `build_deck()`
   **从未使用 `p["tran"]`**，因此黄金的 `tr1 tran stop=4.8*T maxstep=1e-4*T` 与 `save clk d q qbar` 从未进入 deck。
   第 71 行还带了 `else ("4.8*T","1e-4*T")` 的兜底默认值——若哪天 `tran` 行改写导致正则失配，脚本会**造出一组
   看起来像黄金的值**而不是 `BUILD_REFUSE`，这与它自己的"绝不新造数值"策略相冲突。
2. **`srcType` 没有实例属性**（`vpulse`/`vdc` 的 raw 属性里都没有它），CDF 报出的 `pulse`/`dc` 来自**主器件默认值**
   （SECTION A：`vpulse srcType def=[pulse]`、`vdc srcType def=[dc]`）。值是对的，但它不是这个实例显式存的东西。
   状态在机检表里如实写成 `MATCH_VIA_MASTER_DEFAULT`，没有算作"实例已存"。
3. **`c2mos_dff_tb` 只有 `schematic` 一个 view**（实测目录里仅 `schematic/`，无 `symbol`），
   且 cellview 上没有 `simViewList` / `modelFile` / `implementationPath` 等仿真实现属性（§6）。

`edgetype`（cyclic，"Type of rising & falling edge"）在两个 pulse 实例上为空——黄金 deck 也没写它，
所以**不算缺失**，只是 GUI 表单会显示空白。`tc1/tc2/tnom/noisefile/FNpairs/F1/N1` 同理为空，与黄金一致。

---

## 2. 每个参数在 analogLib 里真正叫什么

来源：`/opt/IC617/tools/dfII/etc/cdslib/artist/analogLib/{vdc,vpulse,cap}/data.dm`，SECTION A 原文。
`type=` 是 CDF 参数类型，`def=` 是主器件默认值（`def=[]` 表示厂商字典里默认值为空串）。

### analogLib/vdc — componentName `vsource`，netlistProcedure `spectreSrcPrim`，spectre instParameters `(dc mag phase xfmag pacmag pacphase tc1 tc2 tnom)`

| 黄金里的 Spectre 名 | OA CDF 真名 | CDF type | 主器件默认 | 实例实测 |
|---|---|---|---|---|
| `dc` | **`vdc`** | string | `def=[]` | Vdd=1.8 / Vss=0 |
| `type` | **`srcType`** | string | `def=[dc]` | 无实例属性，取默认 |
| `mag`/`phase` | `acm`/`acp` | string | `def=[]` | 空（黄金未写） |
| `xfmag`/`pacmag`/`pacphase` | `xfm`/`pacm`/`pacp` | string | `def=[]` | 空 |
| `tc1`/`tc2`/`tnom` | 同名 | string | `def=[]` | 空 |

### analogLib/vpulse — componentName `vsource`，netlistProcedure `spectreSrcPrim`，spectre instParameters 含 `val0 val1 period delay rise fall width type edgetype …`

| 黄金里的 Spectre 名 | OA CDF 真名 | CDF type | 主器件默认 | 实例实测（Ck / Dd） |
|---|---|---|---|---|
| `val0` | **`v1`** (prompt "Voltage 1") | string | `def=[0]` | 0 / 0 |
| `val1` | **`v2`** (prompt "Voltage 2") | string | `def=[0]` | 1.8 / 1.8 |
| `period` | **`per`** (Period) | string | `def=[]` | 200n / 400n |
| `delay` | **`td`** (Delay time) | string | `def=[]` | 100n / 70n |
| `width` | **`pw`** (Pulse width) | string | `def=[]` | 100n / 200n |
| `rise` | **`tr`** (Rise time) | string | `def=[]` | 1n / 1n |
| `fall` | **`tf`** (Fall time) | string | `def=[]` | 1n / 1n |
| `type` | **`srcType`** (Source type) | string | `def=[pulse]` | 无实例属性，取默认 |
| — | `dc` (prompt "DC source") | string | `def=[]` | 空（黄金 pulse 行无 `dc=`） |
| — | `edgetype` | cyclic | `def=[]`，选项 `""/linear/halfsine` | 空 |

注意 `vpulse` 字典里**既有 `vdc` 又有 `dc`**：`dc` 的 prompt 是 "DC source"，与 spectre 的 `dc=` 无关；
spectre 的 `dc=` 由 `vdc` 提供（`propMapping` 里 `dc vdc` 成对）。这一层混淆正是上一轮判断失误的现场。

### analogLib/cap — componentName `capacitor`，spectre instParameters `(c w l m scale trise ic tc1 tc2 area perim)`

| 黄金里的 Spectre 名 | OA CDF 真名 | CDF type | 主器件默认 | 实例实测 |
|---|---|---|---|---|
| `c` | **`c`** (Capacitance) | string | `def=[1p]` | Cq/Cqb = 50f（raw 5e-14） |
| — | `model` | string | `def=[]` | `cap`（ASG 写入） |
| — | `w/l/m/scale/ic/area/perim/polyCoef/c1..c20` | string/int | `def=[]`（`polyCoef` 报 0） | 全空 |

`cap` 的 `c` 默认是 `1p`。实例上的 `50f` 与默认不同，所以"意外停在默认值"这条 SCH-2 事故模式在这里不成立
（若成立，机检的 `MATCH` 会退化成 `MISMATCH`）。

---

## 3. 逐项对照黄金 Testbench（要求的五列表）

由 `scripts/c2mos_tb_cdf_check.py` 生成，原文在 SECTION E。`GOLDEN_VALUE` 是用 `scripts/c2mos_tb_build.py`
自带的 `parse_golden()`/`as_number()` 从冻结 deck 解析出来的，不是重打的。

```
GOLDEN_VALUE     CDF_PROPERTY_NAME  OA_RAW_VALUE   OA_CDF_VALUE   MATCH_STATUS                INSTANCE/DECK_ATTR
1.8              vdc                1.8            1.8            MATCH                       Vdd/dc
0                vdc                0              0              MATCH                       Vss/dc
pulse            srcType            ABSENT         pulse          MATCH_VIA_MASTER_DEFAULT    Ck/type
0                v1                 0              0              MATCH                       Ck/val0
1.8              v2                 1.8            1.8            MATCH                       Ck/val1
2E-7             per                2e-07          200n           MATCH                       Ck/period
1.0E-7           td                 1e-07          100n           MATCH                       Ck/delay
1.0E-7           pw                 1e-07          100n           MATCH                       Ck/width
1E-9             tr                 1e-09          1n             MATCH                       Ck/rise
1E-9             tf                 1e-09          1n             MATCH                       Ck/fall
pulse            srcType            ABSENT         pulse          MATCH_VIA_MASTER_DEFAULT    Dd/type
0                v1                 0              0              MATCH                       Dd/val0
1.8              v2                 1.8            1.8            MATCH                       Dd/val1
4E-7             per                4e-07          400n           MATCH                       Dd/period
7.0E-8           td                 7e-08          70n            MATCH                       Dd/delay
2E-7             pw                 2e-07          200n           MATCH                       Dd/width
1E-9             tr                 1e-09          1n             MATCH                       Dd/rise
1E-9             tf                 1e-09          1n             MATCH                       Dd/fall
5.0E-14          c                  5e-14          50f            MATCH                       Cq/c
5.0E-14          c                  5e-14          50f            MATCH                       Cqb/c
ROWS=20 BAD=0    ->  TB_CDF_CHECK: PASS
```

SECTION F 另外按 `propMapping` 把"网表器应当为这些实例写出什么"逐行列出，与黄金 deck 的对应行并列；
那是**名字查表的结果，不是 Cadence 写出的文件**（Cadence 没能写出网表，见 §6）。

---

## 4. Ground 与 Ports

实测（SECTION B）：

- **`gnd!` 网络存在且带 6 个 instTerm**：`Vdd.MINUS`、`Vss.MINUS`、`Ck.MINUS`、`Dd.MINUS`、`Cq.MINUS`、`Cqb.MINUS`。
  其余 6 个网络各 2 个 instTerm：`vdd`(Vdd.PLUS+X1.vdd)、`vss`(Vss.PLUS+X1.vss)、`clk`、`d`、`q`、`qbar`。
  `labels=0 shapes=0` 对每个网络都成立（走线画在 cellview 的 shapes 层，53 个）。
  **Vss 是被显式驱动的**（`X1.vss`→net `vss`→`Vss.PLUS`，`Vss` 是 `dc=0` 的 vdc 源），所以 AGENTS.md 第 19 条
  那个"`vss` 浮空导致 NMOS 全死"的失败模式在这个 cell 里不存在。
- **不要预设 `gnd!` 需要修改**：本轮无法证明它需要，也无法证明它不需要（§6 原生网表被阻断）。
  已实测的部分只有：ASG 把 deck 里的节点 `0` 变成了名为 `gnd!` 的网络（deck 写 `(clk 0)`，cell 里 `Ck.MINUS`→`gnd!`）。
  Cadence 的网表器会不会把 `gnd!` 写回 `0`：**UNVERIFIED_BY_THIS_BUILD**。
- **`PIN0` 是一个不连接任何东西的图形遗留物**：master `basic/iopin:symbol`，`instTerms=nil`，raw 属性 0 个，
  CDF 参数 0 个。它不绑定网络、不构成端口、不影响电气连接。
- **DUT 六个端口绑定全部正确**（`TBCA-CONNECT inst="X1"`）：`d→d`、`clk→clk`、`q→q`、`qbar→qbar`、`vdd→vdd`、`vss→vss`。
- **terms=0 的真实形状**：`c2mos_dff_1bit/schematic` 的 terminal 对象数 = **0**；
  同一 cell 的 `symbol` view 有 **6** 个 terminal（`d clk q qbar vdd vss`，方向均 `inputOutput`）。
  也就是说实例层连线是靠 symbol 的 pin 走通的（`X1` 拿到 6 个 instTerms 就是证据），
  schematic 视图自身没有端口对象。`c2mos_dff_tb` 自己的 `terms=0` 是另一回事：testbench 顶层本来不需要对外端口。
- **netlisting 所需的 view/配置：没有。** 对 5 个 cellview（TB、DUT、以及 analogLib 的 vdc/vpulse/cap symbol）
  各查 7 个属性 `simViewList` `simCompileList` `modelFile` `implementationPath` `source` `analogCell`
  `simulatorLanguage`，**35 个读数全部 nil**；`dbGetCellViewList` 对 5 个器件也返回 nil。

---

## 5. 能否进行 Virtuoso 原生网表生成

**不能。`NATIVE_NETLIST_BLOCKED`。**

- 启动路径：`MODE=restore`（AGENTS.md 记录的唯一能让 `asi*/nl*` 出现的启动方式），`rc=0`、token 命中、会话正常结束。
- 本轮新试的三种参数形状全部返回 nil（SECTION C）：
  `asiCreateSession(?simulator "spectre" ?cellView cv)`、
  同上加 `?tmpDir "/tmp/tb_audit/nl"`、
  `asiCreateSession(?simulator "spectre" ?libName ?cellName ?viewName)`。
  因此 `asiInitialize`/`asiNetlist`/`asiFinalNetlist` 根本没被走到。
- 这**补上了 SCH-2 那次探测的参数缺口**：`skill/sch2_native_netlist.il` 试的是不带 `?simulator` 的三种形状，
  死在 `ADE-5059 'nil' is not a valid simulator name`（`results/evidence/sch3_native_netlist_*.log`），
  当时无法区分"函数不可用"和"参数没给对"。现在带上了正确的 `?simulator "spectre"` 仍是 nil，
  所以结论从"疑似"升级为"两种参数形状族都已实测失败"。
- 命令行也没有独立网表器可退：`ls /opt/IC617/tools/bin/64bit /opt/IC617/tools/dfII/bin/64bit` 里匹配
  `netlist|^nl$|asi` 的只有 `oasisin`/`oasisout`（OA 导入导出，不是网表器）。
- 第二条独立理由：§4 末尾那 35 个仿真实现属性全 nil——即便 `asiNetlist` 可用，它也缺配置。
- 我没有用手写网表冒充 Cadence 原生网表。SECTION F 只是 `propMapping` 的查表结果并明确如此标注。

---

## 6. `scripts/c2mos_tb_build.py` 审计（只报告，未修改）

**A. spiceIn 非零 + cell 目录已存在时会不会误报成功？会，且不需要"目录已存在"这个前提。**

`scripts/c2mos_tb_build.py:194` 拿到 `rc` 之后只在 195 行打印，**整个退出码没有任何地方使用**；
判据是 203 行 `return 0 if os.path.isdir(os.path.join(cell_dir,"schematic")) else 1`——只看目录在不在。
于是三个缺口：
1. spiceIn 建出 `schematic` 目录**之后**才失败（例如后段某个实例报错），目录在、rc≠0，脚本返回 0；
2. 196–201 行从日志里挑 `SPICEIN-33/54/24/56/ERROR` 只**打印**，不参与判据，日志里有 `ERROR` 也照样 PASS；
3. 半途失败的残留会让**重试**撞上 169–170 行的 `if os.path.exists(cell_dir)` 直接 `return 7`
   "already exists"，操作者无法只凭退出码区分"完整"与"残缺"，必须自己去读 `asg_spicein_*.log`。

本轮**不能**实测这条（要实测就得再跑一次 spiceIn，即写库），所以：
`spiceIn 失败时 schematic 目录是否已存在` = **UNVERIFIED**；但"`rc` 未参与判据、日志错误未参与判据"
是代码事实。ASG 日志本身给出的旁证：`Saved and closed '...c2mos_dff_tb:netlist_tmp'` 出现在
`SPICEIN-33 successfully created the schematic view` **之前**（161/164 行，日志共 164 行），
即 ASG 先写临时 view 再落 `schematic`。

**B. 删 `type` 属性前有没有验证 `type=pulse`？没有。**
`scripts/c2mos_tb_build.py:116` 是 `a.pop("type", None)`——不看值就删。紧跟着 117/121 行只检查
"未知属性"和"缺属性"，而 `type` 已被 pop 掉，永远不进这两个集合。后果：如果黄金 deck 哪天写成
`type=sine`/`type=exp`，脚本会把它当 `vpulse` 的脉冲源导入并且一句报错都不出。
（本轮实测顺带说明当前为什么没事：`vpulse` 的 `srcType` 主器件默认就是 `pulse`，见 §1.2。）

**C. 导入结果有没有独立检查？没有，四项里只有"cell 存在性"。**
脚本侧：`cell_dir/schematic` 目录存在 = 唯一判据。实例数量、master、CDF 参数、net 连接**都在脚本之外**，
由 `skill/c2mos_tb_readback.il` 打印——而且那个 readback **只打印不判定**（没有任何 assert/退出码），
上一轮正是它打印了 `TB-CDF ... (("dc" ""))` 而没人据此判失败。本轮的 `scripts/c2mos_tb_cdf_check.py`
第一次把这件事变成有退出码的机检（`ROWS=20 BAD=0`/`TB_CDF_CHECK: PASS`，参数名来自厂商字典而非猜测）。

**D. 生成的 Testbench 缺不缺仿真分析设置？缺。** 见 §1.2 第 1 条：deck 里没有 `tran`/`save`，
`p["tran"]`（70–71 行）解析后从未使用，71 行还带一个会**造数值**的兜底默认值。

**另外一条不属于 A–D 但同样会误导人的**：`scripts/c2mos_tb_build.py:19` 的注释说
"`scripts/c2mos_tb_verify.sh` does that mapping and proves the result"，但 `scripts/c2mos_tb_verify.sh`
**不在版本库里**（`git ls-files scripts | grep c2mos_tb` 只有 `c2mos_tb_build.py`、
`report_build_c2mos_tb_prep.py`、`scan_c2mos_tb_verify.sh`）。这条注释指向一个不存在的文件。

---

## 7. 建议的最小修复动作（等批准，本轮一条都没做）

按"最小"排序，前三条就能让这个 cell 变成可仿真的 testbench：

1. **不要动激励参数。** 它们已经是黄金值（§3）。任何"补参数"的写入都是多余风险。
2. **补分析设置，走已被证明的那条路而不是手写进 OA**：把 `p["tran"]` 真正写进 deck
   （`tran stop=<黄金> maxstep=<黄金>` + `save clk d q qbar`），或者在 ADE GUI 里建 analyze/save 后保存会话。
   两者都不需要碰晶体管、不需要碰 `gnd!`、不需要碰 terms。
   若选 GUI 路线，验收判据必须回到机检：`c2mos_check.sh ff1_sch` 的 33/33 与两次 byte-identical。
3. **`type` 的显式校验**：`a.pop("type", None)` 之前先断言 `a["type"] == "pulse"`，否则 `BUILD_REFUSE`。
   同时删掉 71 行的兜底默认，改成解析不到就 `BUILD_REFUSE`。
4. **退出码判据**：`return` 之前把 `rc != 0` 和日志里出现的 `ERROR`/缺失 `SPICEIN-33` 一起算进失败条件；
   并在 `os.path.exists(cell_dir)` 的分支里打印"上一轮可能残缺，请核对 <log 路径>"而不是只给 7。
5. **导入后结构自检**（把 C 项四项变成脚本内判据，直接复用本轮 `skill/c2mos_tb_cdf_audit.il` +
   `scripts/c2mos_tb_cdf_check.py`，不要另写一份逻辑）：`instances=8 / nets=7`、六个 master 名字、
   `X1` 的 6 条 `instTerm→net`、以及 §3 那 20 行全 `MATCH*`。
6. **`c2mos_dff_tb` 要不要 `symbol` view**：testbench 顶层不需要被别人实例化，建议**不要**建，
   少一个可被误改的对象。
7. 修正 `scripts/c2mos_tb_build.py:19` 那条指向不存在文件的注释。

明确**不建议**的动作：改 `gnd!` 名字（无法验证收益、且 `Vss` 已显式驱动）；给 DUT 补 schematic terms
（本轮禁止事项，且实例连接已实测走通）；对 analogLib 做任何写入。

---

## 8. 修复前后各要检查什么

修复前（本轮已全部做完，作为基线）：
- `find microled_cells -type f ! -name '*.cdslck' | sort | xargs md5sum > before.md5`（本轮 36 个文件）
- analogLib 三个 `data.dm` 的 md5 + mode + 日期（SECTION D）
- `grep -c DEFINE cadence_work/cds.lib` = 6，内容不变（§9）

每做完一次写入，按顺序重跑，**顺序不能换**：
1. `bash scripts/sch_virtuoso.sh skill/c2mos_tb_cdf_audit.il 420 TB_CDF_AUDIT_DONE`（只读，mode "r"）
2. `python scripts/c2mos_tb_cdf_check.py --evidence <新日志>` → 必须仍是 `ROWS=20 BAD=0`、
   `TB_CDF_CHECK: PASS`；任何一行变成 `MISMATCH/MISSING` 立刻停手回滚
3. `md5sum -c before.md5` → 除被批准修改的目标文件外不得有任何失败
4. `python scripts/sch_parameter_integrity_check.py`（AGENTS.md 第 27 条那道门，确认没顺手改到晶体管尺寸）
5. `bash scripts/c2mos_check.sh ff1_sch 2e-7 <tag> 2` → `TESTBENCH_PREFLIGHT: PASS`、`total=33 failed=0`、
   两次 byte-identical、`SCHEMATIC_DFF_FUNCTION: PASS`
6. 若目标是"让 cell 能仿真"，还须补一条能证伪的判据：一份由 Cadence 自己写出、且我能读出节点名与
   `vsource` 行的网表。在此之前，"cell 可直接仿真"这句话必须写 **UNVERIFIED**。

---

## 9. 回滚方案

本轮**没有产生需要回滚的改动**，这本身就是实测的：

```
$ md5sum -c /tmp/tb_audit/mc_before.md5 | grep -v ': OK$'      ->  (无输出，36 个文件全 OK)
$ find .../artist/analogLib -type f -newermt 2026-10-11        ->  (无输出)
$ find .../artist/analogLib -name '*.cdslck'                   ->  (无输出)
```

`microled_cells` 36 个文件字节级未变（DUT `c2mos_dff_1bit/schematic/sch.oa` 含在内）；analogLib 无一个文件被写过；
`cadence_work/cds.lib` 仍是 6 条 `DEFINE`（`cdsDefTechLib basic analogLib smic18mmrf microled_dirver0 microled_cells`），
本轮没有增删库映射，也没有再建临时库。

下一次真要做写入时，回滚只需要一件事：`c2mos_dff_tb` 只有 `schematic` 一个 view，共 3 个文件
（`data.dm` 3388 B、`master.tag` 35 B、`sch.oa` 31684 B，均 21:01）。写前先
`tar cf /tmp/tb_audit/tb_before.tar microled_cells/c2mos_dff_tb`，回滚就是解回该 tar；
最坏情况删掉这一个 cell 目录即可完全恢复（DUT 与其他 cell 不在这个目录里）。
库级/工程级的既有备份仍在 `/root/migration_backup_20261011/`（`microled_dirver0/`、`cds.lib.orig`、
`manifest_md5.txt`、`locks/`），它早于 testbench，因此**不能**用它回滚 testbench，只能用它回滚库映射。

---

## 10. 需要人定的三件事（我没有自行修复）

- **T1 目标形态**：这个 cell 是要变成"ADE 里点 Run 就能仿真"的 testbench（则必须解决 §5 的原生网表阻断），
  还是只要当"GUI 里能看、数值可核对的图形件"（则 §3 已经达标，只差分析设置）？两条路的最小动作不同。
- **T2 `分析设置`的写入方式**：deck 里补 `tran/save` 再重导（需要覆盖现有 cell，与"不重建 cell"冲突，须批准），
  还是在 GUI 手工加 analyze（改动落在 ADE 会话状态里，OA 侧仍看不到）？
- **T3 上一轮报告的处理**：我已按 §0 在本报告里更正，并在
  `reports/c2mos_testbench_build_report.md` 顶部加了更正标记（原句保留以便审计追溯）。
  若你更希望整段删除重写，说一声，我按你的偏好改。
