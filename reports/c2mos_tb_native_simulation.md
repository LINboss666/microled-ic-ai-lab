# c2mos_tb_native_simulation.md — c2mos_dff_tb 的仿真闭环验证

基准提交：`411ac27c2fc5b95b39626e451546eacfda3afad5`（branch `gexing321/scan-driver/c2mos-schematic`）
原始证据：`results/evidence/c2mos_tb_native_simulation.txt`（SECTION A–F，全部命令原文）
guest：`192.168.222.129`，IC617 6.1.7-64b + MMSIM 15.1，`date` = Mon Oct 12 2026 00:2x–00:5x CST

---

## 0. 结论先说

| 问题 | 实测结论 |
|---|---|
| Virtuoso 原生 netlisting | **不成功 → `NATIVE_NETLIST_BLOCKED`**（4 条启动路径全部实测，见 §1） |
| 本阶段目标"testbench 独立产生 waveform" | **达成，但不是走 ADE 原生网表**：网表由仓库既有的 **OA 回读路线**从 `microled_cells/c2mos_dff_tb` 的数据库内容生成（`NETLIST_PROVENANCE: OA_READBACK`），再交真实 Spectre 运行 |
| 仿真结果 | `TB_CELL_DFF_FUNCTION: PASS`，**33 条断言 0 失败**，两次运行逐字节一致，preflight 先过 |
| 四项判据（采样 / 互补 / 无直通 / 保持） | 全部有波形级证据，逐条对应见 §4 |
| 是否改动过库/器件/PDK | **没有**：`md5sum -c` 对 `microled_cells` 36 个文件 0 失败；analogLib、`/root/tech/teacher_pdk` 今日无任何文件写入；DUT `sch.oa` 仍 37796 B / 20:02（SECTION F） |

一句必须说清的话：**我没有把回读生成的网表当成 Cadence 原生网表**。文件头部第 5–7 行就是
`NETLIST_PROVENANCE: OA_READBACK ... NOT a native ADE netlist`（SECTION B 原文）。

---

## 1. Task 1：原生 netlisting 能力（实测矩阵）

| # | 启动路径 | API 族 | 结果 |
|---|---|---|---|
| 1 | `virtuoso -nograph`（`.cdsinit` 注入） | `asi*` `nl*` | SCH-2 已实测全 nil（`results/evidence/sch3_native_netlist_nograph.log`） |
| 2 | `virtuoso -nograph -restore` | `asi*`（含 `?simulator "spectre"` 的 4 种形状） | **nil**（SECTION A1） |
| 2 | 同上 | `sim*`（APS 批处理驱动）5 种调用 | **nil** |
| 2 | 同上 | `nl*`（`?simulator` + `?appName`） | **nil** |
| 2 | 同上 | **`axl*`（ADE XL）** | `axlCreateSession("tb_session") -> ("tb_session")` **会话能建**；`axlSetMainSetupDBLCV(...) -> nil` **器件挂不上** → 无 setup db → `axlGetTests/axlGetCorners/axlPutTest` 全 nil → `axlRunSimulation -> nil`，**网表从未生成** |
| 3 | `asg <file.il>`（第三条批处理路径，ASG 前端） | `axl*` | 连 `axlCreateSession` 都是 nil（SECTION A4）——`asg` 不加载 adexl context，比 `-restore` 更弱 |
| 4 | `MODE=gui`（DISPLAY=:0 + `hiSetInitFunc` 延迟初始化） | `axl*` | 进程把 context 载完（cdf/analog/HSPICE-ADE 可见）后**停在 CIW 提示符**，延迟函数没被调用，300 s 后被 runner 自身超时收走 → **UNVERIFIED**（既没成功也没失败，不能记成 blocked，也不能记成可用） |

补充事实（同一批只读会话里量到的）：
- `schCheck(cv)` 在 `-restore` 下对 `c2mos_dff_tb` 返回 **`((0 0))`**：0 错误 0 警告（SECTION A1）。
  所以"图画得没毛病"与"网表器不给用"是两件事，不要混着解读。
- 命令行侧没有独立网表器可退：`dfII/bin*/64bit` 里匹配 `netlist|^nl$|asi` 的只有 `oasisin/oasisout`。
- adexl 的 SKILL 代码确实在盘上（`dfII/etc/context/64bit/{adexl,simui,asimenv,mmsimenv}.cxt`），
  参考文档也在 `/opt/IC617/doc/adexlSKILLref`——**产品装了，批处理里挂不上器件**，这是本 build 的边界。
- 上一轮我写"load(adexl.cxt) 会挂死会话"是**错的**，已作废：真因是我自己的 SKILL 语法错了
  （`if(cond a b c)` 多参，SKILL 的 `if` 恰好三参），文件在加载期就中止，进程随后Idle 到超时。
  正确形式是 `when()`。修正写在 `skill/c2mos_tb_native_probe2.il` 的头注释里。

**结论：`NATIVE_NETLIST_BLOCKED`。** 我没有手写任何网表冒充原生输出。

---

## 2. 生成 netlist 的路径

| 种类 | 路径 | 说明 |
|---|---|---|
| Cadence 原生 Spectre 网表 | **不存在** | ADE XL 拿不到 setup db，`axlGetPointNetlistDir` 无历史可查（SECTION A2/A3） |
| 本轮实际用于仿真的网表 | guest：`/root/microled_ai_project/spectre/c2mos_dff_tb_from_oa.scs`<br>仓库：`spectre/c2mos_dff_tb_from_oa.scs` | 由 `scripts/c2mos_tb_deck_from_oa.py` 生成；器件侧全部取自 `skill/c2mos_tb_cdf_audit.il` 的 TBCA 回读，分析侧由 `c2mos_tb_build.parse_golden()` 从冻结 deck 解析 |
| DUT 体（子电路） | `spectre/generated/c2mos_dff_1bit_from_oa_readback.scs` | 仓库既有件，同样是 OA 回读产物（SCH-2 路线），被上面那份网表 `include` |
| Spectre 结果 | `spectre/sim/run_ff1_tb_native2.raw/tr1.tran.tran`（psfascii）<br>断言报告 `logs/c2mos_assert_ff1_tb_native2_{1,2}.txt` | 见 SECTION C/D/E |

生成器打印的自证信息（SECTION B 原文）：
```
SKIPPED_NON_ELECTRICAL [('PIN0', 'basic/iopin/symbol', 'instTerms unbound')]
GROUNDED_TERMINALS=6 (gnd! -> 0)
SOURCES=Ck Dd Vdd Vss CAPS=Cq Cqb DUT=X1 model=c2mos_dff_1bit ports=d,clk,q,qbar,vdd,vss
ANALYSIS tran stop=4.8*T maxstep=1e-4*T save=clk d q qbar
```
`DECK_REFUSE` 护栏是硬的：实例分类靠 master（不靠人名）、`type` 只接受 `pulse`、DUT 必须有 `model`
属性、任何非 `gnd!`/`0` 的 MINUS 连接直接中止、写数值必须 `Decimal` 原样往返否则拒绝。

---

## 3. analysis 设置（Task 2）

现在这份 testbench 的仿真设置是：

```
parameters T=2e-07
parameters VDDV=1.8
tr1 tran stop=4.8*T maxstep=1e-4*T        # = 960 ns 停止、20 ps 最大步长
save clk d q qbar
```
三条都是从冻结的 `spectre/c2mos_ff1_func.scs` 解析出来的（`parse_golden()` 的 `p["tran"]` 与新增的
`^save` 解析），不是我挑的数。

关于"最小修复落在哪"，我做了一个有意识的取舍，必须讲清楚：

- **做了**：新增生成器把 `tran`+`save` 真正写进**用来仿真的那份网表**，于是 Task 2 要的
  "testbench 具有 tran analysis + save(clk d q qbar)" 在仿真链路上成立（§4 用它跑出了波形）。
- **没做**：没有把 `tran`/`save` 塞进 `scripts/c2mos_tb_build.py` 写给 spiceIn 的那份
  `spectre/import/c2mos_dff_tb.scs`。原因：**未验证 ASG 会不会接受分析语句**（`spiceIn` 的活是把器件
  搬进 schematic，不是搬分析），而本轮禁止重建 cell，我没法实测这条，所以不改动那份输入。
- 因此 `scripts/c2mos_tb_build.py:70-71` 那段"解析了 `p["tran"]` 却从不使用、还带
  `else ("4.8*T","1e-4*T")` 兜底默认"的问题**仍然存在**，作为待批准的脚本整改项保留（上一轮 §5-D 已提）。
  它的正确修法是把分析写进"运行网表"而不是"导入网表"，正是新脚本做的事。
- **禁止项一律没碰**：没有改器件、没有改 MOS 尺寸、没有写 CDF 参数、没有动 analogLib/PDK/DUT
  （本轮全程 cellview 都以 mode `"r"` 打开；SECTION F 的 md5 复核是这件事的证据）。

---

## 4. waveform 结果（Task 3）

运行命令（复用仓库既有断言机器，没有另写一套）：
```
bash scripts/c2mos_check.sh ff1_tb 2e-7 native2 2
  TESTBENCH_PREFLIGHT: PASS      # STATIC_OK vdd 1.8 V 对节点 0 / vss 经独立源接到 0；OP_OK 两点都实测
  [1] assertions: total=33 failed=0
  [2] assertions: total=33 failed=0
  REPEAT: 2 runs produced byte-identical assertion reports
  TB_CELL_DFF_FUNCTION: PASS
```

四项判据逐条对应（`ff1` 断言表本来就是仓库为这四点设计的，见 `scripts/c2mos_check.sh:14-17` 注释）：

**① Q 跟随 D 采样** — 每个周期的两个窗口都对：
```
OK ASSERT q    [1.4e-07,1.9e-07] gt 1.7  n=2500 min=1.8    max=1.8
OK ASSERT q    [3.4e-07,3.9e-07] lt 0.1  n=2500 min=1.04e-08
OK ASSERT q    [5.4e-07,5.9e-07] gt 1.7 ...   （4 个周期 1,0,1,0 全覆盖）
OK CROSS clk thr=0.9 t=9.005e-07 ... / OK CROSS q t=9.0091e-07
```
时钟 50% → Q 50% 的实测延迟：`CLK50_to_Q50 = 1.84e-10 / 4.10e-10 / 1.84e-10 / 4.10e-10 s`
（下降沿 0.092 %T、上升沿 0.205 %T），且 `D50_to_CLK50 = 29–30 ns` = 数据确实**先于**捕获沿到位。

**② Qbar 互补** — 每个 q 窗口都配了一条反相窗口，全部 OK：
```
OK ASSERT qbar [1.4e-07,1.9e-07] lt 0.1  n=2500 min=6.33e-09 max=6.33e-09
OK ASSERT qbar [2.2e-07,2.9e-07] lt 0.1  n=3507 min=-0.000364 max=0.000284
```
（注意 max 是 `1.84122` 那一档的 q 窗口：时钟沿上有过冲，这是信息不是错误，preflight 也如实报
`RAIL_OVERSHOOT_WARNING` 而不判死。）

**③ 无直通（组合穿透）** — "late" 窗口 `[s+0.60T, s+0.95T]` 里 **d 正在翻转**，而 q 必须保持；
波形数据直接给出一帧证据（SECTION E）：
```
t=4.791570e-07 clk=0.000000 d=1.800000 q=0.000042 qbar=1.800000   # d 已升高，clk 还低 → q 没跟着走
t=4.991570e-07 clk=0.000000 d=1.800000 q=0.000011 qbar=1.800000
t=5.189980e-07 clk=1.800000 d=1.800000 q=1.800000 qbar=0.000000   # 时钟上升沿才把 1 收进去
```
**④ 保持** — 时钟低半周内 q/qbar 全程钉住（`min=1.79941/max=1.84122`、反向 `≈0`），
且两次运行逐字节一致（`REPEAT: byte-identical`）。

**波形截图这件事**：这台 VM 取不到可信像素（AGENTS.md 第 30 条实测：`import -window root` 只回一张
几百字节的平图，按窗口抓要么全黑要么 `Resource temporarily unavailable`）。所以按任务书允许的
"等价数据"保存：SECTION E 是 `scripts/psf_dump.awk` 对 psfascii 每 1000 点抽一行的
`t clk d q qbar` 表（48 行，覆盖 0–960 ns）。我没有放任何假截图。

---

## 5. 与 golden deck 的区别

机器比对（同一 T 替换后的两份运行网表，去掉注释/空行后 diff）：
```
diff <(ff1_sch 运行网表) <(ff1_tb 运行网表)  ->  11 行 < / >
```
差异全部是**写法**差异，没有一条是**数值**差异：

| 差异 | golden / ff1_sch 侧 | 本轮 OA 侧 | 性质 |
|---|---|---|---|
| 数值形式 | `val1=VDDV period=T delay=0.5*T` `c=50e-15` | `val1=1.8 period=2e-07 delay=1e-07` `c=5e-14` | 表达式 vs 已求值，数值相同（上一轮 20/20 行机检已证） |
| 行序 | Vdd/Vss 在前 | Ck/Dd 在前 | 网表顺序无语义 |
| 参考节点 | 无 | 多了 `global 0` | 我把单元里的 `gnd!` 显式映射成 `0`（6 个端子，生成器打印计数） |
| 参数行 | `parameters T=2e-7` | `parameters T=2e-07` | 同一数值 |

真正的、有意义的一条区别是**方向性的**：
- golden deck 的激励是**文本里写的**；
- 本轮激励是**从 `microled_cells/c2mos_dff_tb` 的数据库里读出来的**（源实例、值、端子→网络、
  负载容值、DUT 引用全走 TBCA 回读）。

这恰好就是本阶段要证明的东西：图形 testbench 的内容可以独立驱动一次仿真，而不需要有人再抄一遍数。
`X1` 行与 `include` 行两份网表**完全相同**——因为 DUT 侧走的是同一个 OA 回读子电路。

---

## 6. 是否需要处理 terms

本轮**没有处理，也不需要处理**，理由分三层，各自标注证据等级：

1. **实测：仿真路径不需要。** testbench 顶层 `terms=0` 是对的（顶层不对外开口），
   DUT `X1` 的 6 个 `instTerm` 全部按名绑到 `d/clk/q/qbar/vdd/vss`，`schCheck` 也是 `((0 0))`。
   本轮的网表由回读按**端子名**组装，端口名来自 symbol 的 6 个 terminal（`c2mos_dff_1bit/symbol`），
   不依赖 schematic 的 terminal 对象。
2. **实测：那个不连线的 `PIN0`（`basic/iopin`）确认无语义**——`instTerms=nil`、0 属性、0 CDF 参数，
   生成器把它归类为 `SKIPPED_NON_ELECTRICAL` 并打印原因，不是默默丢掉。
3. **UNVERIFIED：原生网表要不要 terms。** 由于 `NATIVE_NETLIST_BLOCKED`，我无法证明"补了 schematic
   terms 之后 ADE 就能出网表"，也无法证明相反。所以这一项**不能写成 PASS，也不能写成必须做**。
   如果以后要打通原生路径，先做的应当是 §1 表里第 4 行那条 GUI 路径（它还没被真正测出来过），
   而不是先去动 terms。

---

## 7. 机检与复现

| 门禁 | 命令 | 结果 |
|---|---|---|
| testbench 电气健康 | `scripts/tb_preflight.sh`（由 c2mos_check 自动先跑） | `TESTBENCH_PREFLIGHT: PASS` |
| 断言 | `scripts/psf_check.awk`（经 `scripts/c2mos_check.sh ff1_tb`） | `directives=33 failed=0` |
| 复现性 | 同上，`repeat=2` | 两份断言报告 `byte-identical` |
| 参数名/值映射 | `python scripts/c2mos_tb_cdf_check.py --evidence results/evidence/c2mos_tb_cdf_audit.txt` | `ROWS=20 BAD=0 → TB_CDF_CHECK: PASS`（本轮沿用，未回归） |
| 器件计数 | `python scripts/netlist_stats.py` | `DEVICE_COUNT_CHECK: PASS` |
| 来源标签 | `python scripts/provenance_check.py` | `SOURCE_PROVENANCE_CHECK: PASS` |
| 提交闸 | `python scripts/precommit_safety_check.py --mode staged` | `SAFETY_GATE: PASS` |

新代码只有两处，且都带拒绝路径：`scripts/c2mos_tb_deck_from_oa.py`（新）、
`scripts/c2mos_check.sh` 加一个 `ff1_tb` 模式（+3 行，含把 `ff1_tb` 纳入单 DFF 断言表那两处判断——
第一次跑就是因为漏了它而错用了移位链的 `q0/q1/q2` 判据，报出 14 条 `too-few-samples(n=0)`，
这也是一条实测教训：**加模式必须同时加分支条件**）。

---

## 8. 未改动证明

```
$ md5sum -c /tmp/tb_audit/mc_before.md5 | grep -v ': OK$'      -> 无输出（36/36 一致）
$ ls -A cadence_work 前后 diff                                   -> NO_NEW_TOPLEVEL_ENTRIES
$ find analogLib        -type f -newermt 2026-10-12            -> 无
$ find /root/tech/teacher_pdk -type f -newermt 2026-10-12      -> 无
$ ls -l .../c2mos_dff_1bit/schematic/sch.oa                     -> 37796 B, Oct 11 20:02（未变）
```
本轮 4 次 Virtuoso/asg 会话 + 2 次 Spectre 运行之后仍然如此，所以"只读 + 只新增文本文件"这句话
是有证据的，不是声明。

---

## 9. 遗留与需要人定

- **L1 原生网表仍是被阻断状态**。唯一没测干净的是 GUI/延迟初始化路径（进程活着但 init func 没触发，
  疑似缺 `XAUTHORITY`——`/root/.Xauthority` 在本机不存在，桌面真实用的是 `/var/run/gdm/auth-for-root-*/database`，
  AGENTS.md 第 32 条已记录）。要不要我带正确的 `XAUTHORITY` 再试一次 GUI 路径？那会在你的桌面上真的弹出
  Virtuoso 窗口，所以我没自作主张。
- **L2 Task 2 的落点**：现在的分析设置活在"运行网表"里。若你要求**分析必须在 OA cell/ADE 会话里可见**
  （GUI 打开 testbench 能看到 tran/save），那需要一次写操作（建 ADE 会话状态或补 cell 侧配置），
  本轮的 `axlSetMainSetupDBLCV -> nil` 说明批处理做不到，得走 GUI，需要批准。
- **L3 `c2mos_tb_build.py` 的 A/B/C/D 四项整改**仍未做（上轮只做了"报告建议"）。其中 A（退出码不看 `rc`）
  是最容易在下次误报 PASS 的一条。
- **L4** 我没动 `gnd!`、没动 `terms=0`、没建 `symbol` view——都按禁止事项保留原状。
