# 环境审计 — MicroLED 驱动芯片组仿真设计（课程作业）

任务号：`COURSE-MICROLED-SIM-20261112-R1`
审计日期：2026-11-12（Asia/Shanghai）
分支：`course/microled-assignment-sim-20261112`（从当天 `origin/main` 建立）
性质：**只读环境检查 + 被任务书 §1 明确许可的最小命令行能力探针**。不安装软件、不改 PDK / OA 库 / `cds.lib` / techfile / license、不重启或改 VM 配置、不读或记录凭据值。

> 本报告只记录非敏感运行信息、能力结论与摘要。PDK 模型卡内容、包内完整私有文件清单、license 地址、凭据、老师原始 ZIP 本体、用户目录绝对路径均不入库。所有 PDK 引用在交付文件中一律写成 `${QODER_PDK_LIB}` 之类的环境变量占位。

---

## 1. 结论速览

| 项 | 判定 | 依据 |
|---|---|---|
| ModelSim / Questa | `MODELSIM_AVAILABLE=YES` | 真实 `vlog -sv` + `vsim -c` 跑通最小自包含 RTL/TB，生成真实 VCD |
| Cadence Virtuoso / Spectre（guest） | `CADENCE_GUEST_REACHABLE=YES` | 既有合法 Tools 应急通道只读查询成功 |
| SSH 通道 | `BLOCKED_SSH`（不影响 Tools 通道） | 连接既有地址 22 端口超时；未做电源/网络配置改动 |
| PDK 工艺 | SMIC 0.18 µm Mixed-Signal RF / Enhanced（`smic18mmrf` 系列） | ZIP 顶层目录与模型文件名；无 TSMC 命中 |
| PDK 统计模型 | `STAT_MODEL_PRESENT=YES` | `statistics/process/mismatch/vary` 语法实存；`spectre -h montecarlo` 可用 |
| Monte Carlo | 模型条件满足；**是否真正跑成见 `monte_carlo_report.md`** | 不以"有语法"冒充"已运行" |
| STA | `STATIC_TIMING_ANALYSIS: NOT_RUN` | 无综合后网表、标准单元库、STA 工具 |
| 本阶段 Spectre 仿真 job | **0** | 仅执行版本与 `montecarlo` 帮助查询，均非电路仿真 |

---

## 2. Windows 数字工具

### 2.1 探测方式与原始结果

- `command -v` 逐一探测 `vsim vlog vlib vdel vmake vcover modelsim questasim spectre virtuoso ocean`：
  - 找到：`vsim`、`vlog`、`vlib`、`vdel`、`vmake`、`modelsim`（同一 `modelsim_ase/win32aloem` 目录，已在 PATH 中）。
  - 未找到：`vcover`、`questasim`、`spectre`、`virtuoso`、`ocean`。
  - PATH 中另有 `modelsim_ae/win32aloem`。
- 任务书列出的常见位置 `C:/intelFPGA/18.0/modelsim_ase`、`C:/altera/18.0/modelsim_ase`、`C:/Program Files/intelFPGA/18.0/modelsim_ase`、`D:/intelFPGA/18.0/modelsim_ase` 等**全部不存在**。实际可用安装位于本机 FPGA 工具分发目录下的 `modelsim_ase/win32aloem`（Intel FPGA Edition / Starter Edition 附带，与 Quartus 18.0 世代一致）。不因路径不是标准位置就判定不可用，也不把"找到 exe"当成"能跑"。
- 环境变量只记录名称：存在 `QUARTUS_ROOTDIR`；未发现任何 license 相关变量被导出（值一律不记录）。

### 2.2 版本（真实命令输出）

```
vlog -version  -> Model Technology ModelSim ALTERA vlog 10.5b Compiler 2016.10 Oct  5 2016   (rc=0)
vsim -version  -> Model Technology ModelSim ALTERA STARTER EDITION vsim 10.5b Simulator 2016.10 Oct  5 2016 (rc=0)
```

### 2.3 真实命令行仿真能力探针（§1 明确要求）

在系统临时隔离目录（不入库）放置最小自包含 `env_probe.v` / `env_probe_tb.v`（4-bit DFF + 自检断言 + 负例），执行：

```
vlib work
vlog -sv env_probe.v env_probe_tb.v
vsim -c -do "run -all; quit -f" work.env_probe_tb
```

实测：`vlib_rc=0`、`vlog_rc=0`（`Errors: 0, Warnings: 0`）、`vsim_rc=0`，transcript 输出
`ENV_PROBE_ERRORS=0` / `ENV_PROBE_RESULT=PASS` / `$finish at 16 ns`，并生成真实 `env_probe.vcd`
（VCD 头含 `ModelSim Version 10.5b`，SHA-256 `a625f52bb8f24954af4e1a8d1e6fa2fa58bfaf9733524127d07ef84f6168ef5e`）。
该次 `vsim` 已登记进 `results/execution_ledger.csv`，计入 12 次上限。

**判定：ModelSim 可用，`BLOCKED_MODELSIM` 不成立。** 因此本任务将真实运行数字 RTL 验证，不伪造波形。

---

## 3. Cadence / Virtuoso / Spectre

### 3.1 Windows 本机

`C:/cadence`、`D:/cadence`、`C:/Program Files/Cadence`、`D:/EDA/Cadence` 等常见安装位置均不存在；PATH 中无 `virtuoso` / `spectre`。Windows 侧不存在可直接调用的原生 Cadence 可执行程序。

### 3.2 既有合法入口

仓库 `AGENTS.md` 定义：首选 SSH；**SSH 不可达时使用 VMware Tools 通道（`vmguest.mjs` / `vmfile.mjs`）作应急执行**。本次按此约定处理，未新增通道、未改配置。

- `vmrun list`：`Total running VMs: 1`，为既有 IC617 实验虚拟机（只读状态查询）。
- `vmrun checkToolsState`：`running`。
- 进程列表：存在 `vmware-vmx.exe`，无 Windows 侧 `virtuoso` / `spectre` 进程。
- SSH 实测：`ssh ... root@<既有地址> port 22` → `Connection timed out`（rc=255）；`vmrun getGuestIPAddress` → `Unable to get the IP address`；DHCP 租约文件仅有一条 2026-10-28 的历史租约；TCP/22 不可达。
  **未执行** `dhclient`、未改 `ifcfg-*`、未动 VM 电源 / 快照 / `.vmx` / 网络配置 / license。
- 改用既有 Tools 应急通道：只读查询成功（`rc=0`）。

### 3.3 guest 内工具与 PDK 状态（Tools 通道只读）

| 项 | 实测 |
|---|---|
| 执行身份 | `uid=0` |
| Cadence 安装 | `IC617`、`MMSIM151` 目录存在 |
| Spectre 版本 | `@(#)$CDS: spectre version 15.1.0 64bit 11/12/2015 (sjfnl729) $` |
| `spectre -h montecarlo` | 返回 Monte Carlo Analysis 帮助，明确其为 swept analysis + child analyses，引用 statistics blocks |
| 老师交付 PDK 解压副本 | 存在，文件数 **3975** |
| 未跟踪的本地环境配置 | 存在（文件名 `pdk_local.env`，`rw-------`；**内容、路径、值均未读取也未入库**） |
| 相关进程 | 仅 `lmgrd`；无运行中的 `virtuoso` / `spectre` |
| guest 截屏工具 | `import`、`xwd`、`convert`、`xdpyinfo` 存在；`scrot`、`Xvnc` 未在 PATH |

### 3.4 统计模型能力（关键：决定 MC 能否真跑）

对老师交付的 Spectre 模型卡做**只读语法计数**（不输出、不复制任何模型内容）：

```
statistics_blocks=23   vary_statements=69   process_blocks=5   mismatch_blocks=18
```

对 ZIP 内 `models/` 目录做内存扫描（不解压、不输出内容）：83 个候选模型文件中 3 个含统计分布语法，
聚合命中 `statistics=52 / mismatch=37 / vary=140 / gauss=140 / process=15 / montecarlo=5`，
结论 `STAT_MODEL_PRESENT_IN_ZIP`。仓库历史报告 `reports/pdk_zip_vs_guest.md` 另记录该工艺可用 corner 名中含 `MOS_MC` 统计角。

**判定：`MC_BLOCKED_NO_STAT_MODEL` 不成立。** 统计模型与 `montecarlo` 分析均存在；MC 是否实际运行、样本数与统计结论以 `monte_carlo_report.md` 和 `results/` 原始数值为准。普通参数扫描不会冒充 Monte Carlo。

---

## 4. PDK 压缩包

| 项 | 实测 |
|---|---|
| 存在性 | 存在；用户交付副本与工作区副本 **SHA-256 相同** |
| 大小 | 55,826,083 B |
| SHA-256 | `a3f8217692c7f84e39aa519cbf87969b4124d063b0eebc44b47bf3a6c21d199c` |
| ZIP 可读性 | `testzip()` 返回 `None`（无 CRC 异常） |
| 条目 | 5331（3975 文件 + 1356 目录项），解压后合计 108,875,384 B |
| 条目类型 | 以 OA 库视图文件、`*.oa` / `*.tag` / `*.dm`、Spectre 模型、Calibre deck、文档为主 |
| 安全扫描 | **路径穿越 / 绝对路径 / 盘符路径 / 符号链接异常条目 = 0** |
| 工艺标识 | 顶层 `smic18mmrf/` 占 5150 条目；`models/spectre/` 38 个文件；含 `techfile.tf`、`cds.lib`、`display.drf`；关键字 `tsmc` 命中 **0** |
| 模型世代 | 文件名指向 `ms018_enhanced_v1p2_rev0`（Enhanced / BSIM4）与 `mse018_v1p11_rf` |

**正式工艺选择依据：** 任务书指定 SMIC 0.18 µm Mixed-Signal RF 为首选；ZIP 与 guest 中已装老师交付副本在文件数上一致（3975），仓库历史位级对比报告 `reports/pdk_zip_vs_guest.md` 记录"解压副本与老师 ZIP 逐文件 CRC 全对、3975/3975"。**本轮未重新逐文件重算 CRC，只复核文件数与历史结论**，不把历史结论冒充当日实测。未自动换成 TSMC，未把 3.3 V 器件当 5 V 用。

**未解压到任何旧 PDK 目录**：本轮全部为 ZIP 内存只读；若后续需要解包，只在仓库外隔离目录进行并复用同一异常条目检查。PDK 本体、模型卡、Calibre deck、老师原始 ZIP、raw PSF、凭据与 license 一律不进入工作树与 review 包。

---

## 5. 阻塞、风险与边界

| 编号 | 状态 | 说明 |
|---|---|---|
| E1 | `BLOCKED_SSH` | 既有 SSH 地址 22 端口超时、guest 无上报 IP；Tools 应急通道可用，故不影响后续只读/仿真通道，但大文件传输需分块或走 Tools 的 pull |
| E2 | `NOT_RUN`（本阶段） | 未启动任何 Spectre 电路仿真 job；版本与 `-h` 帮助查询不计入 job 上限 |
| E3 | `STATIC_TIMING_ANALYSIS: NOT_RUN` | 无综合后网表、工艺标准单元库与 STA 工具；ModelSim 功能时序不得冒充门级 STA |
| E4 | `BLOCKED` | Virtuoso **原生 GUI 截图**：本轮实测 X display `:0` 可用（Xorg 运行），但 `import -window root` 只得到 **221 字节空白 PNG**；仓库既有实测 `skill/sc1_s3c3_gui_body.il` 已记录该 build 的 Virtuoso 窗口是嵌套 Qt 子窗口、自动像素抓取未完成。本轮仍用 `spiceIn` 在**新建独立课程 OA 库**生成了真实 schematic/symbol 并取得 Check&Save 日志与结构化只读回读（`results/oa_evidence.txt`），但**没有**原生 GUI 截图，绝不把网表或渲染图冒充已保存原理图。见 `known_failures_and_limits.md` B1 |
| E5 | 授权边界 | 未改 VM 电源/快照/`.vmx`/网络配置/license；未读取或记录任何凭据值；未安装任何未知版本工具 |
| E6 | 一致性局限 | 本轮未重跑 3975 文件逐项 CRC 复算，仅复核数量并引用历史位级结论 |

**进入条件：** 只有对应环境被判定可用才进入该仿真子项。ModelSim 可用 → 进入 §3 数字验证；guest Cadence/Spectre 与统计模型可用 → 进入 §4/§5 模拟与 MC（每个 job 另按预算登记）。

---

## 6. 本阶段实际执行命令（脱敏摘要）

```
command -v vsim vlog vlib vdel vmake vcover modelsim questasim spectre virtuoso ocean
vlog -version ; vsim -version
vlib work ; vlog -sv env_probe.v env_probe_tb.v ; vsim -c -do "run -all; quit -f" work.env_probe_tb
python - <<'PY'  (zipfile 只读：CRC / 条目类型 / 异常路径 / 关键字 / 统计语法计数)
vmrun list ; vmrun checkToolsState ; vmrun getGuestIPAddress -verbose
bash scripts/guest.sh ssh '<只读查询>'          -> 超时，未重试扩容
bash scripts/guest.sh run '<只读查询>'          -> rc=0，Tools 通道可用
spectre -V ; spectre -h montecarlo               -> 版本/帮助，非仿真 job
git fetch origin ; git ls-remote origin          -> 远端回读，见 source_provenance.md
```
