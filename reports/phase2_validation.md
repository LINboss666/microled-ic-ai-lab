# Phase 2 validation — Micro LED 环境只读侦察与最小验证

日期：2026-10-04 · 执行者：Agent（全部自测，无需用户手测）
性质：只读侦察 + 独立工作区 + 最小 Spectre/SKILL 验证。**未做任何设计修改。**

## 1. 测试矩阵

| Test | Result | Evidence（原始输出摘录） |
|---|---|---|
| IC617 bridge（阶段1 通道回归） | PASS | `test_ic617_bridge.ps1` → `[PASS] 1.vmware / 2.guest-ip ip=192.168.3.128 / 3.ssh work-eda / root / 2.6.32-431.el6 / 4.sync / 5.skill dbAccess rc=0 / 6.token` → `RESULT: PASS` |
| PDK inventory | PASS | 5 个工艺库全部识别；原始扫描 `logs/pdk_inventory_raw.txt`（364 行）；结论表见 `reports/pdk_inventory.md` |
| Spectre standalone（不含任何 foundry model） | PASS | `SPECTRE name=smoke_rc.scs rc=0 elapsed=0s`；`spectre completes with 0 errors`；`CHECK numeric=OK (got=6.000000e-01 expected=6.000000e-01 relerr=0.00e+00)` → `SPECTRE_SMOKE_TEST: PASS`，且日志 0 条 WARNING |
| PDK Spectre model | PASS | `MODEL_PROBE_TSMC18: PASS`（4/4）+ `MODEL_PROBE_SMIC18EE: PASS`（4/4）→ `PDK_MODEL_PROBE: PASS`，`total checks passed=8 failed=0` |
| MicroLED calculations | PASS | `MICROLED_CALC: PASS`，selfcheck `pixels=True caseA_row=0.015360A caseB_row=11.796A md=True`；guest 2.6.6 与 host 3.12 输出**语义零差异** |
| Project directory | PASS | `/root/microled_ai_project/` 下 `README.md`、`spec/system_requirements.md`、`scripts/`×4、`skill/`×2、`spectre_smoke/`、`model_probe/`×4、`results/`、`reports/`、`logs/`、`home/`、`skill_run/` 均存在 |
| Virtuoso nograph | PASS | 三种模式实测：`MODE=nograph` rc=0 4s；`-restore 无 exit()` rc=124（不退出）；`-restore + exit()` rc=0 6s `TOKEN_FOUND yes` |
| （附加）跨 Python 版本可复现 | PASS | py2.6.6 vs py3.12 JSON 逐字段比较 `semantic diffs: 0` |

## 2. Spectre 独立验证细节

`/root/microled_ai_project/spectre_smoke/smoke_rc.scs`：1.8 V 源 + 10k/5k 分压，DC 扫描 0→1.8 V，**不含任何 PDK**。

```
CHECK done_line='spectre completes with 0 error'
CHECK datafile='.../sim/smoke_rc.raw/sw1.dc'
CHECK expected V(vm) at sweep=1.8 got='0.6'
CHECK numeric=OK  (got=6.000000e-01 expected=6.000000e-01 relerr=0.00e+00)
```

PSF-ASCII 数据行实测与理论分压逐点吻合：`dc=1.8 → vd=1.8, vm=0.6`。结论：**Spectre 15.1.0.284.isr1 64bit 可执行、license 正常（约 65 ms 检出）、netlist 解析正常、求解收敛、结果数值正确、输出文件存在**。

## 3. PDK 模型验证细节（8 项行为判据）

| 检查 | 实测 | 判据 |
|---|---|---|
| TSMC0.18 NMOS 截止 | `d=1.800000e+00`，relerr `0.00e+00` | 必须精确等于电源轨（无电流） |
| TSMC0.18 NMOS 导通 | `d=0.00511256` | < 1.75 → 成立 |
| TSMC0.18 PMOS 导通 | `p=1.77927` | > 0.05 → 成立 |
| TSMC0.18 PMOS 截止 | `delta=1.253e-06` | 精确等于 0（亚阈值漏电量级） |
| SMIC18EE n18e2r 截止 | `1.799990e+00`，relerr `5.56e-06` | 成立 |
| SMIC18EE n18e2r 导通 | `0.0052564` | 成立 |
| SMIC18EE n50e2r 截止 | `5.000000e+00`，relerr `0.00e+00` | 5 V 厚栅器件同样可用 |
| SMIC18EE n50e2r 导通 | `0.0381222` | < 4.9 → 成立 |

派生观察（供选型参考，非本轮决策）：TSMC 0.18 的 `nch` 在 W=2 µm / L=0.18 µm、Vgs=1.8 V、Vds≈5 mV 下即通过 100 kΩ 负载拉出约 **17.9 µA**（`(1.8−0.0051)/100k`）。与本项目 15 µA/像素量级同阶，说明 1.8 V 核心器件在毫微米级像素驱动上有余量。此为深线性区单点数据，**不构成尺寸依据**。

## 4. Micro LED 系统级基线（仅题面推导）

给定：1024×768、5 µm×5 µm、15 µA/像素、60–100 Hz、TCON×1 + 数据驱动×2 + 扫描驱动×2。

| 量 | 60 Hz | 100 Hz | 依据 |
|---|---|---|---|
| 像素总数 | **786,432** | 同 | H×V |
| 帧时间 | 16.667 ms | 10 ms | 1/f |
| 行时间（零消隐上界） | **21.70 µs** | 13.02 µs | 帧时间/768，消隐 NOT DEFINED |
| 逐行扫描每行可用时间 | 21.70 µs | 13.02 µs | 假设 A4：每次选通 1 行 |
| 每颗数据驱动通道数 | **512** | 同 | 1024/2 |
| 每颗扫描驱动通道数 | **384** | 同 | 768/2 |
| 每通道最低更新率（1 bit/时钟） | 23.59 MHz | 39.32 MHz | 512/行时间；灰阶层数 NOT DEFINED |
| 行选通速率 | 46.08 kHz | 76.80 kHz | 1/行时间 |
| 全部像素同时点亮的理论电流 | **11.796 A** | 同 | 786,432×15 µA |
| 逐行扫描瞬时行电流 | **15.36 mA/行** | 同 | 1024×15 µA，D1 定义下即选通行电流 |
| 派生：面板平均电流 | **15.36 mA** | 同 | 786,432×15 µA×(1/768)；因始终恰好一行被选通，数值上等于行电流 |
| 派生：单像素平均电流 | **19.53 nA** | 同 | 15 µA × 占空比 1/768 = 1.302e-3 |

**更正说明**：本节初稿曾把"面板平均电流"写成 20 µA（错把行电流又乘了一次占空比）。重写 `microled_arch_calc.py` 时新增的自检项 `panel_average` / `panel_avg_equals_row_current_when_one_row_always_on` 抓出了这个错误并已修正——正确关系是：一行常选通且无消隐时，**面板平均 = 瞬时行电流**，被占空比缩小的是**单像素平均**（19.53 nA）。

**定义 D1（2026-10-04 确认）**：15 µA = 像素被选通、处于发光状态时的**瞬时电流**，不是帧平均；帧平均一律作为由扫描占空比推导的派生量，方向不可颠倒。把 15 µA 当帧平均会推出单行 11.796 A 的荒谬结果，该解读已在脚本里作为 `excluded_interpretation` 留档但**不用于任何规格**。

**关键未定义项（已标注 NOT DEFINED，未擅自代入）**：像素 pitch 是否等于 5 µm、灰阶位宽、PWM 位深、消隐占比、LED 正向压降、工艺节点与 VDD、数据接口形式、是否要求 DEM/Mura/补偿、供电域与可靠性指标、扫描复用系数。

## 4.x 定义问题的处置

原报告把"15 µA 是瞬时还是帧平均"作为并列两种情形呈现，并写下"更可能是瞬时值，需课程确认"。2026-10-04 该定义已由用户确认为 **D1：瞬时（on-state）值**，因此本节只保留 D1 口径的数字；帧平均作为派生量给出，帧平均与瞬时值的关系见上表。规格里不再出现由被排除解读产生的任何数值。

## 5. Virtuoso 完整自动化能力探测

- `virtuoso -h` 在本 build 只暴露 10 个选项，**没有** `-ilLoadFile`/`-cmd` 之类；SKILL 注入的正规入口是 HOME 下的 `.cdsinit`（可用 `-nocdsinit` 跳过）。
- **无 DISPLAY 也能跑**：`MODE=nograph` 时 `display=<unset>`、`rc=0`、4–6 s 完成，并打印出完整 SKILL 引擎独有的 `ddGetLibList()`（13 个库对象）。
- 它**自动使用了自带的虚拟显示**：`$HOME/.vnc-cds/work-eda:80.log` 显示 `Xvnc version 3.3.7 ... Desktop name 'work-eda:80 (root)'`，同目录还有 `work-eda:80.pid`、`xstartup`。IC617 自带 `cdsXvnc`/`cdsVncserver`/`cdsXvncd`（`/opt/IC617/tools/bin/`）。**未安装任何系统软件，未改 /etc**（guest 里本来就有 `/usr/bin/Xvfb`，本轮没有使用它）。
- 两种可用注入方式：
  1. `HOME=<project>/home` 内写 `.cdsinit` → `load("<file>.il")` + `exit()` → `virtuoso -nograph -log L`：rc=0、5 s、**自动退出**。
  2. `virtuoso -nograph -restore <file.il>`：**确实会执行该 SKILL 文件**，但若文件末尾没有 `exit()` 进程不退出（实测 rc=124 撞满 120 s 超时）；文件末尾加 `exit()` 后 rc=0、6 s、标识齐全。
- 副作用审计：运行只在 `skill_run/` 留下我们的 log/stdout，在重定向的 HOME 里留下 `.cdsinit`、`.config`、`.vnc-cds`；未生成 `cds.lib`、未生成 `CDS.log` 于真实 `/root`；`/root/tech` 各 PDK 目录 mtime 仍是 **2022-05-09**。
- 未解析项（如实标注）：13 个库对象的**名称**未能取到——三种 `~name` 属性访问写法都在 SKILL 解析阶段报 `syntax error at line 37 column 50` 并中断整个 load（`*Error* load: error while loading file`）。预算 3 次用尽，已回退到可稳定 PASS 的探针版本，库名枚举留下一轮（改用 `ddGetObjName(l)` 一类函数式访问，而非 `~` 访问符）。

## 6. 本轮遇到的问题与处置（全部实测定位，无猜测式修复）

| 问题 | 根因（证据） | 处置 |
|---|---|---|
| `SFE-23 undefined model 'source'` / `dc1` | Spectre 组件名是 `vsource`；分析语句是"实例名在前、关键字在后" | 用本机 `spectre -h vsource` / `-h dc` 取权威语法后改写 |
| 首次 `-log/-raw/-format` 报 SPECTRE-132 | 该 CLI 把 inputfile 当作末位参数，且 `-log/-raw` 在此 build 非选项；默认日志名即 `<netlist>.log` | 改为 `spectre <net> -64 -format psfascii`，日志/raw 事后归档到 `sim/` |
| 只用 `op` 时 psfascii 无数据 | 无分析时只写 `logFile`，无 `TRACE` 数据段 | 改为真正的 DC 扫描，得到可数值比对的 `sw1.dc` |
| `analyze=yes` 报 SFE-30 | `analyze` 不是 `dc` 实例的合法参数（被忽略） | 从所有 netlist 移除，最终 smoke 日志 0 WARNING |
| TSMC0.18 `SFE-1996 unknown parameter par1fn_mc` | `tt` 段引用了定义在 `stat_noise` 段的 MC 噪声参数 | netlist 里追加 `section=stat_noise` include；**未修改 PDK** |
| SMIC 5V 器件 `CMI-2441` + `CMI-2434 'Vsat' must be positive` | L=0.5 µm 低于 `n50e2r` 的 `lmin=1.4e-6`（厚栅器件长沟道限定） | 读卡取得 lmin/lmax/wmin/wmax，改用 L=2 µm/W=10 µm |
| 供应商主文件不可用 | `tsmc18/models/spectre/spectre.scs` 硬编码 `/opt/cadence/process/.tsmc18/...`，该路径不存在 | 直接 include 模型卡；已在报告中标为陷阱 |
| `push` 14 KB 文件超时 | `vmguest.mjs` 的 base64 载荷经 vmrun argv 传输有大小上限 | >约 3 KB 的文件改走 scp（密钥免密）；已在工具链说明 |
| `-restore` 判定被污染 | 上一轮 `nograph` 写入的 `.cdsinit` 仍在，导致误判 | 删除 `.cdsinit` 复测，才得出"`-restore` 执行但不退出"的结论 |
| SKILL 属性访问中断 load | `l~name` 在本 SKILL 解析器报语法错（非运行期错） | 3 次预算用尽后回退到已验证版本，UNKNOWN 标注 |

## 7. 安全边界确认

| 项 | 结论 |
|---|---|
| 修改 PDK？ | **否。** `/root/tech/**` 全部 PDK 目录 mtime 仍为 2022-05-09；`find /opt/IC617 -maxdepth 2 -newermt 2026-10-04` → 空；本轮对 PDK 只有读操作 |
| 修改 cds.lib / techfile / model file？ | **否。** 未编辑任何一处；`smic18ee` 的失效 `cds.lib` 路径与 `tsmc18` 主文件的硬编码路径都只被记录，未被改动 |
| 修改/创建/删除 Cadence library、cell、schematic、layout？ | **否。** 未创建任何 OA 库或 cell；`ddGetLibList` 只做列表查询，未打开任何 cell view；`geGetEditCellView()` 返回 nil（无编辑器会话） |
| 跑 DRC / LVS？ | **否。** 只确认了 deck 文件存在 |
| 动 VM 电源 / 快照 / .vmx / license / 网络持久配置？ | **否。** 与阶段 1 一致：无电源操作、无快照、无 `.vmx` 编辑、无 license 改动、`ONBOOT` 仍为 `no` |
| 安装软件？ | **否。** 未装 Xvfb 或任何系统包；使用的是 IC617 自带 `cdsXvnc` |
| 写入范围 | 仅 `/root/microled_ai_project/**`（新增工作区）与 `/root/qoder_ic617_sandbox/**`（桥基础设施，本轮未新增内容）。运行期 `HOME` 重定向到项目内 `home/`，Cadence/Spectre 临时文件不污染 `/root` |
| 凭据与 license | 密码值只存在于 `.ic617_agent_bridge_credentials`（`.gitignore` 排除），不出现在任何报告/日志；license 值只运行时取用；本报告**未摘录任何模型参数数值**（仅器件名、corner 名、几何合法范围），符合 SMIC "no part of this file can be released"、TSMC "Security B" 的限制方向 |

## 8. 本轮创建/修改的文件

Windows（`D:\ic617_agent_bridge`）：新增 `reports/pdk_inventory.md`、`reports/phase2_validation.md`、`reports/architecture_baseline.md`、`results/architecture_baseline.json`(+`.guest_py26.json` 对照件)、`scripts/microled_arch_calc.py`、`scripts/run_spectre.sh`、`scripts/pdk_model_probe.sh`、`scripts/run_virtuoso.sh`、`spectre/smoke_rc.scs`、`spectre/model_probe_tsmc18_{nm,pm}.scs`、`spectre/model_probe_smic18ee_{nm,5v}.scs`、`skill/pdk_inventory.sh`、`skill/nograph_probe.il`、`microled/README.md`、`microled/spec/system_requirements.md`；修改 `AGENTS.md`（凭据规则）、`logs/pdk_inventory_raw.txt` 等运行日志。

Guest（`/root/microled_ai_project`）：`README.md`、`spec/system_requirements.md`、`scripts/{pdk_inventory,run_spectre,pdk_model_probe,microled_arch_calc}.…`、`skill/{nograph_probe,nograph_probe_exit}.il`、`spectre_smoke/smoke_rc.scs`+`sim/`、`model_probe/`×4+`sim/`、`results/architecture_baseline.json`、`reports/architecture_baseline.md`、`logs/{pdk_inventory_raw.txt,pdk_probe_tmp.out}`、`home/{.config,.vnc-cds}`、`skill_run/`×若干 log/stdout。

## 9. 事实 vs 建议（明确分开）

**事实**
1. 桥仍可用；Spectre 与 IC617 SKILL 均可从 Windows 一条命令驱动并自动判定 PASS/FAIL。
2. 本机有 5 个可安装的 OA 工艺库；其中 **TSMC 0.18 GP II (BSIM4, 1.8/3.3 V)** 与 **SMIC 0.18 EEPROM (BSIM3v3, 1.8/3.3/5/15.5 V)** 的模型已在本机 Spectre 上真跑通（各 4/4 判据）。
3. TSMC 0.18 库附带 Assura + Calibre 的 DRC/LVS deck、RF 无源（MIM/MOM/电感/变容）、BJT、电阻，且有 0.18 通用标准单元 **Liberty `.db`**（非 OA cell）。
4. SMIC 18EE 提供 **5 V 与 15.5 V** 器件（厚栅），但 `cds.lib` 里有指向未安装的 IC618 的死路径。
5. 65 nm (CMU65LP) 库**模型交付不完整**：`models/spectre|hspice|eldo` 为空，只有 2.5 V / 3.3 V 两套 online 卡；全库 `.ckt/.va` 无源模型文件数为 **0**；卡片标注 "Security B"。
6. 65 nm 与 0.18 RF 两个库本轮**未做仿真验证**（只盘点）。
7. Virtuoso 完整引擎可在**无 DISPLAY** 下 headless 运行，靠自带 Xvnc(:80)，注入机制为 `.cdsinit` 或 `-restore + exit()`，单次 4–6 s。
8. 系统级基线数字见 §4（D1 口径）：瞬时行电流 15.36 mA，面板平均同为 15.36 mA，单像素平均 19.53 nA。

**建议（不是本轮结论，需你确认）**
- 下一轮原建议是先做系统架构：`spec/system_requirements.md` 里仍有约 10 项 NOT DEFINED，其中灰阶层数、消隐占比、PWM 位深直接决定数据/扫描驱动器规格（"15 µA 是瞬时还是平均"这一项已于 2026-10-04 由 D1 确定为瞬时值）。
  **实际决定（同日）：用户选择先做"扫描驱动器的一个最小单元（一路）"作为 AI 可行性验证**，因此下一阶段的范围是按单元电路走，而不是先铺系统架构；工艺/VDD 等仍未定义，需要在开工前给出或由用户认可默认值。
- 工艺倾向（仅在"若课程允许自选"的前提下）：TSMC 0.18 GP II 作为主选，因为它是唯一"从模型到 DRC/LVS deck 到标准单元 Liberty"链条完整且本轮实测通过的库；SMIC 18EE 作为备选，仅在需要 >3.3 V 摆幅（例如 5 V / 15.5 V 器件）时考虑，但要先解决其 `cds.lib` 死路径。65 nm 不建议——模型不完整且许可限制最严。**这是建议，不是事实；最终以课程指定为准。**
- Verilog-A 排在系统架构之后、晶体管级之前：本轮确认 Spectre 15.1 能读 Verilog-A（SMIC 库里就有 `res.va` 且被正常打包），用 VA 建 LED/像素阵列与 TCON 行为模型，能在不画晶体管的前提下回答刷新率/灰阶/PWM 与电流预算的耦合问题。
- 扫描驱动器 vs 数据驱动器的晶体管级设计，应等 U2/U3/U4/U5 定义清楚后再选。

## 10. 停止点

按要求，本轮到此为止：**未**画 MOS、**未**建 schematic/layout、**未**改 PDK、**未**跑 DRC/LVS、**未**生成 1024×768 晶体管阵列、**未**自行决定工艺节点 / 灰阶位宽 / VDD。下一阶段的四条路线（系统架构 / Verilog-A / 晶体管级数据驱动 / 扫描驱动）等待你选定后再开始。

---

## 11. 报告之后的追加进展（同日，用户给出新输入后）

1. **D1 定义确认**：15 µA = 像素被选通、处于发光状态时的**瞬时电流**。§4 已按 D1 重写，并**更正初稿错误**：面板平均电流不是 20 µA，而是等于瞬时行电流 **15.36 mA**（因为始终恰好一行被选通）；被占空比缩小的是单像素平均 **19.53 nA**。该错误由重写时新增的自检断言抓出。
2. **老师指定使用 SMIC 018 MM RF**，并要求补做该库验证 → `MODEL_PROBE_SMIC18MMRF: PASS`（8/8：1.8 V 的 `n18/p18` 与 3.3 V 的 `n33/p33` 各 4 项）。全套回归从 8/8 扩到 **16/16 PASS**。
3. **PDK 完整性比对结论**：虚拟机那份是 2007-09-20 的 **BSIM3v3** 老交付（`ms018_v1p7`），老师 zip 是 2025-01-18 的 **BSIM4 Enhanced** 交付（`ms018_enhanced_v1p2_rev0` + `mse018_v1p11_rf` + 官方 Calibre DRC/LVS/XRC deck），两者模型文件**零交集**。老师那份已按位校验装入 `/root/microled_ai_project/pdk/smic18mmrf_teacher`（3975 文件 / 120 MB，CRC 全对），后续设计以它为准；`/root/tech` 未改动。详见 `pdk_zip_vs_guest.md`。
4. **下一阶段范围已由用户选定**：扫描驱动器一路的最小单元 = **1 bit 移位 + 输出缓冲**。尚未开工，待确认输出摆幅与行驱动架构两个问题。
