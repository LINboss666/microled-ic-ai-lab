# 模拟电路测试报告（基本电流源单元）

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 2026-11-12
仿真器：`spectre 15.1.0.284.isr1 64bit`（Cadence MMSIM151，guest 原生环境）
状态：**部分完成**。DC / 瞬态 / Monte Carlo 均有真实数值；**Virtuoso 原生 GUI 截图 `BLOCKED`**。

---

## 1. 新建的独立课程 OA library / cell（真实对象，非文字网表）

| 项 | 值 |
|---|---|
| 课程 OA library | `course_sim_20261112`（**新建、独立、只写这一个库**） |
| cells / views | `course_sink_unit:schematic`、`course_sink_unit:symbol`、`course_sink_top:schematic` |
| 生成方式 | Cadence `spiceIn`（Analog Schematic Generation），`rc=0`，日志含 `Saved and closed` 与 `Spice In successfully created the schematic view` —— 即真实 Check&Save |
| 隔离证据 | 课程 `cds.lib` 从共享库映射**只读**拷贝 DEFINE，只追加一行新课程库；共享文件 MD5 前后均为 `d70cb62915d95a25b04c4fe9f21f876d`，`SHARED_UNCHANGED=yes`。**未改任何既有 OA 对象** |
| 只读打开方法 | 在课程 OA 目录（`cds.lib` 所在目录）执行 `dbAccess -load course_oa_readback.il`；或在 Virtuoso 中打开 `course_sim_20261112.course_sink_unit:schematic` |
| 原始 OA 数据 | 保留在 guest 沙箱本地，**未上传 proprietary OA 数据** |

结构化只读回读（`results/oa_evidence.txt`，`dbAccess rc=0`）：

```
course_sink_unit : instances=7  nets=5  terminals=4  shapes=39
nets      : VSS, NODE_M, DATA_OUT, VCAS, VB
instances : Mcas / Mout / Mref  (masterCell=n33, masterLib=smic18mmrf)
            PIN0..PIN3         (masterCell=iopin, masterLib=basic)
```

spiceIn 日志逐条记录了每个 MOS 的端口—网络映射，例如
`Created connection between net 'VB' and term 'D'/'G'`、`'VSS' and term 'S'/'B'`。

**器件编号 / 型号 / 显式 D-G-S-B**（Spectre MOS 端序 `(d g s b)`，衬极在最后）：

| 器件 | 型号 | D | G | S | B | L / W | 作用 |
|---|---|---|---|---|---|---|---|
| `Mref` | `n33` | VB | VB | VSS | VSS | 2 µm / 20 µm | 二极管连接参考管 |
| `Mout` | `n33` | NODE_M | VB | VSS | VSS | 2 µm / 20 µm | 1:1 镜像输出管 |
| `Mcas` | `n33` | DATA_OUT | VCAS | NODE_M | VSS | 2 µm / 20 µm | cascode，VCAS 偏置 |

偏置与参考：外部 `IREF = 15 µA` 注入 `VB`；`VDD18 = 1.8 V`、`VCAS = 1.8 V`、`VSS` 由
`Vss (vss 0) vsource dc=0` **显式接地**；输出为理想夹持源 `Vclamp`，DC 1.20 V、扫描 0.60–1.50 V。
电流方向：`Ip_out (clamp_node data_out) iprobe`，正读数 = `clamp_node → DATA_OUT → Mcas → NODE_M → Mout → VSS`
的下拉灌电流，`I_sink = Ip_out:i`，不取负、不取绝对值。

> **诚实标注**：任务书要求的「原生 GUI 截图（原理图 / 仿真设置 / 波形）」本轮 `BLOCKED`。
> 本轮 X display `:0` 可用，但 `import -window root` 只得到 **221 字节的空白 PNG**；
> 仓库既有实测记录 `skill/sc1_s3c3_gui_body.il` 也明确写了这个 build 的 Virtuoso 窗口是嵌套 Qt 子窗口、
> 自动像素抓取未完成、截图需人工完成。
> 因此这里**没有**把网表、示意草图或 VCD/CSV 渲染图冒充成 Virtuoso 已保存原理图的 GUI 截图；
> 只提供真实 OA 对象 + Check&Save 日志 + 结构化回读。见 `known_failures_and_limits.md`。

---

## 2. 可比实验基线与适用局限

| 条件 | 值 | 来源 |
|---|---|---|
| 工艺角 / 温度 | `section=tt` / 27 °C | 任务书指定的限定接受 DC-R1 条件 |
| 电源 | `vdd18 = VCAS = 1.8 V`、`VSS = 0` | 同上 |
| 参考电流 | 外部 `IREF = 15 µA` | 同上 |
| 输出夹持 | `1.20 V`（DC 另扫 0.60–1.50 V，步长 0.05 V，19 点） | 同上 |

**适用局限（必须声明）**：历史 DC-R1 的 DUT 是**八档单输出 PAM 电流阶梯**，实测满量程
`I111 = 15.382706 µA`、`Iunit_ref = 1.922838 µA`；本课程的 DUT 是**新建的 3 管基本单元**，
拓扑完全不同。历史数值只用于条件对照，**不是本电路的验收判据**；本轮没有为了追 PASS
改阈值、丢弃失败样本或把波形画成通过。

---

## 3. 真实运行结果

| Job | 命令 | rc | 结果 | 输出 |
|---|---|---|---|---|
| S1（DC 首次） | `spectre course_dc_tt.scs -64 -format psfascii` | 0 | `0 errors, 2 warnings`：`save Ip_out:current` 被判无效（SPECTRE-8059 / 8287），**PSF 里没有电流**。原件保留 | 沙箱 `S1_first_run.*` |
| S2（DC 修复） | 同上 | 0 | `0 errors, 0 warnings`；改用实例名 `save Ip_out`，TRACE 出现 `Ip_out:i`；19 点真实数值 | `results/dc_i_v.csv` |
| S3（瞬态） | `spectre course_tran_en.scs -64 -format psfascii` | 0 | `0 errors, 0 warnings, 7 notices`；426 点真实波形 | `results/tran_i_t.csv` |
| MC1 | `spectre course_mc.scs -64 -format psfascii` | 见 `monte_carlo_report.md` | 30 样本 | `results/mc_samples.csv` |

S1 的失败是**测试网表写法**问题，不是电气结论；修复只改 `save` 语句（一次修复尝试，上限 3 次）。

### 3.1 DC 结果（`results/dc_i_v.csv`，19 点，全部来自原生 PSF）

| 量 | 实测 |
|---|---:|
| 1.20 V 处 `Iout` | **14.931905740 µA** |
| 相对 15 µA 设计目标偏差 | **−0.068094260 µA（−0.453962 %）** |
| 0.60 V 处 `Iout` | 14.902507018 µA |
| 1.50 V 处 `Iout` | 14.932045508 µA |
| 全扫描 min / max | 14.902507018 / 14.932045508 µA |
| 参考节点 VB | ≈ 0.884261 V |
| `vcas` / `vdd18` / `vss` | 1.800000 V / 1.800000 V / 0.000000 V |

I–V 曲线图：`figures/spectre_dc_iv.svg`（轴标 V / µA，含 1.20 V 与 15 µA 参考线）。
该图由真实 CSV 渲染，**不是 GUI 波形截图**。

### 3.2 使能开关瞬态（`results/tran_i_t.csv`，426 点）

使能方式是 **VCAS 偏置轨脉冲**（`vsource type=pulse`）：
`val0=0`、`val1=1.8 V`、`delay=1 µs`、`rise=100 ns`、`width=3 µs`、`fall=100 ns`、`stop=8 µs`。
按本 build 的时间轴语义，高电平平台在 1.1–4.1 µs。

| 量 | 实测 |
|---|---:|
| 关态窗口（t < 0.9 µs）电流均值 / 最大绝对值 | 2.7393e-7 µA（≈ 0.274 pA）/ 见 `analog_summary.json` |
| 导通窗口（2–4 µs）电流中位数 | 14.931906 µA |
| 90 % 建立时间（相对导通中位数） | **1.055938 µs**，即自 1.0 µs 使能起点起 **55.94 ns** |
| 关断后（t > 5 µs）最大绝对泄漏 | ~2.0e-6 µA（≈ 2 pA） |
| 上升沿附近 | 存在**负位移电流**（最低约 −0.137 µA），真实保留、未剔除 |

7 条 notices 全是 `Found trapezoidal ringing on node Xdut.Mcas:int_s` 及
`Trapezoidal ringing is detected during tran analysis`（另有 365 条被抑制），
是数值积分方法提示，不是电气失败；如实记录，未隐藏。

波形图：`figures/spectre_tran_wave.svg`、`figures/spectre_tran_settling_zoom.svg`
（含时间轴 µs、电流轴 µA、VCAS 轴 V、图例与曲线标签；由真实 CSV 渲染，非 GUI 截图）。

---

## 4. 结论边界

「仿真通过」只表示**在以上所列测试条件下的数值证据**。本轮**不代表**：
完整芯片功能、PVT / SOA、光学性能、版图、DRC/LVS、门级 STA、量产签核、
1024×768 阵列驱动、TCON 或 Scan 高侧电路。整芯片功能一律 `NOT_IMPLEMENTED`。
