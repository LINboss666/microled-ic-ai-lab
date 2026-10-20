# DATA-7A 双模灰阶时序控制器逻辑与 RTL 验证任务书

**You have NO access to the user–ChatGPT conversation; the current task brief and the named repository are your sources.**

你是本地执行者 Qoder。用户已要求继续补齐 PWM 与 Hybrid PAM+PWM；本轮只执行下述数字逻辑阶段。你不能自行更改产品架构、PAM 拓扑、最终电流档、工艺或既有电路，也不能自行批准下一阶段。必须读完本文件后再开始。

## 0 项目、基线与本轮唯一交付

- 仓库：`https://github.com/LINboss666/microled-ic-ai-lab`。
- 任务 ID：`DATA-7A`。
- 新分支：`poc/data-gray-d7a`。若已存在，先检查来源和内容，不覆盖；冲突时新建同前缀的个人分支并记录。
- 固定开发基线：`731767519d1a51287eb5b7f4a6e4f9b8e613e990`，远端分支 `poc/data-unit-1ch`。
- 只读 Scan 参考：`0038821e6a93861848ac922ccca35c41a4de9bbb`，远端分支 `poc/scan-driver-1ch`。
- 云端在2026-10-20实际执行了远端 refs 回读，并读取固定 Data 提交下的约束、Data-6 报告和六份 Data 网表。摘要见随包 `SOURCE_AUDIT.json`。
- 本轮唯一交付：**可综合的单数据通道双模灰阶时序控制器 RTL、独立检查器和真实正负仿真证据**。用两个逻辑实例验证两颗 Data 的共同启动/时钟关系。
- 完成级别只能是 `RTL_LOGIC_VERIFIED`；不能写 `MOS_PWM_COMPLETE`、`PAM_CIRCUIT_COMPLETE`、`FULL_CHIP_COMPLETE` 或光学8位灰阶已实现。

本阶段由数字模型表达未来片内控制电路，**没有将 PWM 转移到外部 DSP/FPGA 作为最终产品方案**。后续仍需独立审核对应 MOS 电路及 OA 实现。

### 开始前必须读的具体文件

固定基线下：

- `README.md`、`AGENTS.md`、`CONTRIBUTING_AI.md`、`.gitignore`。
- `spec/system_requirements.md`。
- `reports/agent_handoffs/DATA-6.md`。
- `spectre/dd1_d6_top.scs`、`spectre/dd1_d6_control.scs`、`spectre/dd1_d6_sink_unit.scs`。
- `spectre/dd1_d6_sink_core.scs`、`spectre/dd1_d6_bias_core.scs`、`spectre/dd1_d6_inv18.scs`。
- `scripts/dd1_d6_unit_tt.py`：只了解既有测量保留项和禁止覆盖旧证据的纪律，不调用原生模拟仿真入口。
- `scripts/repo_safety_rules.py`、`scripts/test_safety_rules.py`、`scripts/precommit_safety_check.py`。
- `scripts/provenance_check.py`、`scripts/netlist_stats.py`、`scripts/make_review_bundle.py`。

随包：`workflow/github-bridge-review-workflow/SKILL.md` 及其三个 references、任务/交接模板。

本包已完整提取本阶段需要的外部规格事实。不要让用户重新解释历史聊天，也不要声称已阅读未随包交付的论文、课程原件或本机截图。

## 1 背景和来源分层

### 1.1 已有电路实际是什么

Data-6 顶层是 `dd1_data_top_1ch(d clk blank iref_in vcas data_out vdd18 vss)`。展开为29管：18管 C²MOS DFF、4管 NOR 消隐、2管互补使能反相器、4管恒流下拉和1管共享参考。`data_en = Q AND NOT blank`，模拟核心的关断控制同时需要互补 `data_en_b`。

它证明的是一位状态可以开关约15 µA的单路恒流下拉，已有记录仅对应限定 TT 条件及外部 IREF、VCAS；**它没有8位灰阶存储、PWM计数器、8档 PAM 或 LUT**。

Scan 最小单元为39管，已有电路不在本轮修改范围。Data 接 N 行阴极，Scan PMOS 高侧接 P 列阳极；左右 Data、上下 Scan 的奇偶交错分配继续保留。全局最多选通一列。不要改成四象限双端择路方案。

### 1.2 本阶段采用的事实和假设

| 内容 | 采用值或行为 | 来源与性质 |
|---|---|---|
| 阵列和刷新需求 | 1024列×768行，5×5 µm LED，60–100 Hz，15 µA为选通导通时的峰值目标 | `COURSE_REQUIREMENT`，已登记的题面/用户定义；不是整帧平均15 µA |
| 物理分工 | Data阴极恒流下拉，Scan阳极高侧；左右各384路、上下各512路 | 已确认系统方案；本轮不做通道阵列 |
| 灰阶模式 | Pure 8-bit PWM；Hybrid 3-bit PAM选择＋6-bit PWM | `POC_ASSUMPTION`，来自2026-10-19作业提交版规格书第6、9章，用户要求继续该方案；不是老师题面逐条给定 |
| Pure事件间隔 | 100 Hz示例30 ns，60 Hz示例50 ns；256个时间区间 | `POC_ASSUMPTION`＋`ENGINEERING_DERIVATION` |
| Hybrid事件间隔 | 100 Hz示例120 ns，60 Hz示例200 ns；64个时间区间 | 同上；本轮只验证数字区间和选择码 |
| 发光窗口 | 100 Hz为7.68 µs，60 Hz为12.8 µs，两种模式窗口相同 | 256×30/50 ns，或64×120/200 ns，工程计算 |
| 启动和消隐 | LATCH仅在BLANK内；PWM_START清零预备，不消耗发光时间；首个有效tick打开窗口 | 已采用规格书第13章的数字契约，具体见第3节 |
| 电流档 | 8个选择码；实际 I_PAM0…I_PAM7、修调和最终参考关系未定 | `NOT DEFINED`；本轮不填入1.875、3.75…15 µA作为正式档值 |
| 光学有效灰阶、LED I–V、阵列RC、最终VLED/VSCAN、SOA | 尚未确认 | `NOT DEFINED` / `NOT_VERIFIED`；RTL不能证明这些 |

7 µm中心节距、2 µm边缘间隙和四边50 µm预留、HDMI接收器＋DSP前端均为已有系统背景，不参与本轮数字验证，也不修改相关方案文件。

仓库较早的约束仍保留许多 NOT DEFINED。把本轮采用的数字控制假设单独写入 `reports/dd1_d7a_contract.md`，不得大范围改写旧登记或把旧 GPT 方案提升为课程原始要求。来源机检仍使用仓库原有标签；可以额外注明“本任务采用”，但不篡改标签意义。

## 2 冻结、允许范围和环境边界

### 2.1 冻结部分

除下面明确列出的新文件和两项安全工具小改外，**固定基线已有被跟踪文件均不改**。尤其包括：

- 所有既有 `spectre/` 网表、DFF/NOR/电平转换/高侧输出及Data模拟核心的拓扑、端序、尺寸。
- Data-6 与此前 CSV、阈值、报告、runner、preflight、器件回读与 OA 比较工具。
- 任何已有 OA 库、手工美化原理图、symbol、`cds.lib`、PDK、模型、技术库。
- `AGENTS.md`、`CONTRIBUTING_AI.md` 和系统需求登记，不用改它们来消除冲突或让检查器变绿。

两个模拟母本摘要必须与 `SOURCE_AUDIT.json` 一致：

- `spectre/dd1_d6_sink_core.scs`：`6cfe2338014a4b152833ef1974f197b0e4c65e963947f57f0cc8b79b73ee91db`。
- `spectre/dd1_d6_bias_core.scs`：`4115e2d17a86fb92e7c222df085f1d1a82da14cb7640654d90f4e2589e9b31e7`。

### 2.2 允许的新文件

- `rtl/dd1_d7a_*.sv`。
- `tests/dd1_d7a/` 内自研 SV testbench、Python检查器及小型JSON/CSV测试向量。
- `scripts/dd1_d7a_*.py`，确有必要时同前缀的 `.sh` / `.ps1` 入口。
- `scripts/dd1_d7a_validate_handoff.py`：从随包 `scripts/validate_handoff.py` 逐字节复制，不修改校验语义；原文件位于 workflow 包内。
- `reports/tasks/DATA-7A.md`：本任务书的可审计副本。
- `reports/dd1_d7a_contract.md`、`reports/dd1_d7a_rtl.md`。
- `reports/agent_handoffs/DATA-7A.md` 和 `.json`。
- `results/evidence/dd1_d7a_*` 的脱敏小型记录、命令输出、CSV、JSON及文件摘要。

本轮不添加第三方 IP、大波形、工具安装包或二进制构建产物。临时运行、VCD、编译可执行文件和突变源码写到已被忽略的 `review/dd1_d7a/<run_id>/`。禁止把编译器输出当文本源码入库。

### 2.3 必要且有限的安全工具例外

云端读到基线 `EXTENSIONS_ALLOWED` 尚无 `.sv`。为提交本轮自研 RTL，允许：

1. 仅在 `scripts/repo_safety_rules.py` 的原白名单中增加 `.sv`。
2. 在 `scripts/test_safety_rules.py` 增加对应正例；确认其它未知扩展仍拒收，原有专有模型/秘密等负例全部仍然有效。

不得放开全部未知扩展、增加路径豁免、禁用hook、削弱内容扫描或允许VCD/二进制。若还需要改别的安全规则，先停下报告，不扩大例外。

### 2.4 本机边界

- 先只读确认 OS、仓库位置、Python、Git、四态RTL模拟器及版本。不假设仍是同一电脑、WSL、IP或路径。
- 优先使用已有 Icarus Verilog 或支持本测试语法的其它四态模拟器。仅跑Python期望模型不算RTL仿真；只有两态仿真不能宣称X/Z检查通过。
- 还需用Yosys或已有等价综合工具对本轮RTL做独立的前端展开/综合结构检查，不读取testbench、不用专有标准单元库；这不是工艺映射、时序收敛或面积验收。
- 缺工具时可在被忽略的任务目录准备官方开源工具的隔离本地安装，记录来源、版本和下载摘要；不改系统全局PATH/注册表，不改商业license，不提交安装物。做不到则 `BLOCKED_TOOLCHAIN`。
- 本轮不需要操作VM、SSH凭据或Cadence。不改VM电源/快照、不动license、不往guest工程写文件。
- `NEW_SPECTRE_RUNS=0`，`NEW_OA_WRITES=0`。前轮进程账19/20是旧记录，不是本轮可继续消费的额度。

## 3 必须明确实现的数字契约

先把以下行为写进 contract，再实现 RTL。内部状态编码、分层和是否共享8位物理计数寄存器可自主选；外部可观察行为不能变。

### 3.1 模式与配置边界

- 模式为 Pure 和 Hybrid，非法模式码必须拒收并保持输出关闭。
- 模式只允许在 `system_en=0`、`BLANK=1`、窗口未运行的安全状态修改。成功修改后使原显示配置/预备状态失效，重新加载、LATCH、PWM_START后才可显示。
- 输入配置是本轮的**抽象单通道并行接口**：Pure有8位灰码；Hybrid有3位PAM选择码和6位时间码。为明确时序，可以用互斥字段或统一结构实现，但须文档化。
- 未实现384字节装载、SPI、帧缓存、LUT、地址译码。Hybrid配置来自测试向量，不假装来自已完成的8位视频灰度映射。
- 采用next/load与display两份配置。允许在当前窗口运行时加载下一份灰码；当前显示的码、模式和PAM选择不能跟着变。
- LATCH只在BLANK内、窗口不运行且有完整新配置时接受，原子更新全部相关字段。无新配置、LATCH越界、LATCH与新配置同沿导致版本不明等情况必须拒收/显式报协议错误，不得默默使用旧码。
- 运行中改模式、非法LATCH和不完整配置不能造成短暂发光。定义清楚拒收与恢复规则，并测试；不得以“不属于正常输入”跳过。

### 3.2 PWM码值定义

| 模式 | 输入时间码 | 应有导通区间数 | 全窗口区间数 |
|---|---|---:|---:|
| Pure | 0 | 0 | 256 |
| Pure | 1…254 | 等于码值 | 256 |
| Pure | 255 | 256 | 256 |
| Hybrid | 0，任意PAM码 | 0 | 64 |
| Hybrid | 1…62 | 等于时间码 | 64 |
| Hybrid | 63 | 64 | 64 |

满窗口必须有单独结束状态/条件，不能依靠8位或6位计数器自然回卷；窗口结束后持续关闭，直到下一次合法启动。

PAM选择码在LATCH之后、整个发光窗口及PWM关闭段保持稳定，到下一次合法LATCH再更新；不能在每次PWM关闭时把PAM选择切回0。Pure模式的选择输出可固定为最高合格档的**符号码7**，这不等于已经产生15 µA。

### 3.3 启动、tick与时间端点

- RTL内部验证参考时钟采用100 MHz，即10 ns周期，属于数字POC条件。tick为该时钟域内的clock-enable事件，不作为无约束的新派生时钟。
- PWM_START在BLANK=1、配置有效、reset/fault许可且system_en许可的准备序列内接收一次上升事件，清零并预备。可保持40 ns；**不能因其连续为高而每拍重置**。
- PWM_START不打开电流、不消耗第0个区间。BLANK释放后的第一个有效tick定义为`t0`，打开第0个区间。
- 第k个区间为`[t0+k*T, t0+(k+1)*T)`。若要求M个导通区间，输出在`t0`开启、在`t0+M*T`关闭；M=0全程关闭。
- 窗口终点分别为`t0+256*T`、`t0+64*T`。若使用同一个tick流表达启动及区间结束，应有257或65个**边界事件**；256/64是时间区间数，不是包含启动沿的总边界事件数。也可单列window_end事件，但必须与上述端点等价。
- BLANK内的tick不能消费区间，PWM_START前的tick不能发光；结束后继续给tick不得重复打开或溢出回卷。

| 测试条件 | tick间隔 | 100 MHz参考周期数 | 发光全窗口 |
|---|---:|---:|---:|
| Pure，100 Hz时序例 | 30 ns | 3 | 7680 ns |
| Pure，60 Hz时序例 | 50 ns | 5 | 12800 ns |
| Hybrid，100 Hz时序例 | 120 ns | 12 | 7680 ns |
| Hybrid，60 Hz时序例 | 200 ns | 20 | 12800 ns |

这里没有实现TCON的976/977参考周期列调度，也没有实现50 MHz DCLK与PWM域的CDC。所有同步输入由本测试参考域按明确建立条件提供；这些边界必须在报告中标 `NOT_IMPLEMENTED`，不得由本轮推出跨芯片物理偏斜≤5 ns或最高工作频率已达标。

### 3.4 复位、消隐和故障

- 上电/复位后输出关闭，无有效配置不得显示。RTL reset只是本模块新定义的逻辑端口，不代表旧C²MOS DFF已有复位或真实POR电路已实现。
- BLANK、reset与fault具有输出关闭优先权。BLANK或fault在时钟两沿之间断言时，最终使能必须被异步逻辑门控拉低，不能等下个tick或参考时钟。
- 本轮数字POC把有效BLANK/fault断言宽度设为至少两个参考时钟周期，断言相位任意；reset脉宽采用至少1 µs。更短的异步脉冲仍须在其有效期间组合门控关闭输出，但是否被内部abort状态捕获不作本轮已验证承诺。此脉宽条件是`POC_ASSUMPTION`，不代替最终芯片输入规格或CDC设计。
- 运行中BLANK或fault断言，中止本窗口并记录abort；随后仅撤销BLANK或清fault，**不得自动继续旧窗口**。必须在安全阶段重新完成有效加载/LATCH/启动序列。
- 用可综合的单一驱动实现abort/armed状态，避免以多个always过程驱动同一寄存器。仿真检查异步事件排序；不要写只在理想同沿激励下成立的状态机。
- 配置版本、窗口运行标志、done/abort和协议错误至少有可审计的输出或明确可观察节点。最终 `DATA_EN_B` 的逻辑关系为 `NOT DATA_EN`，包括消隐和故障状态；不要误用旧DFF的qbar代替。
- 异步关断的RTL零延迟只证明逻辑优先级，不证明MOS传播延迟、亚稳态、复位释放安全或真实器件毛刺已经解决。

### 3.5 与旧Data单元的接口限制

本轮只输出灰阶请求与安全门控后的逻辑使能/档位码，不连接或强制旧网表内部节点。

旧Data-6顶层只有`d/clk/blank`，PWM请求接到d后还会被DFF采样，不能把这种连接当成直接控制输出。后续MOS阶段需要单独审核：采用新的灰阶控制顶层复用冻结的模拟核心，还是设计明确时序的锁存接口。现在不得通过改端口、旁路DFF、强制`data_en`、给内部节点接理想源来“接通”它。

## 4 必须运行的验证

### 4.1 检查器先自证

先用手写、可独立算出的短波形测试检查器，不使用DUT自身输出作为唯一黄金答案。至少包含：精确一个区间、全窗口、off-by-one、漏掉终点、窄脉冲、全空CSV、缺信号、X/Z、重复时间戳、单位/时间刻度异常以及事件前取样冒充响应。

期望表与被测RTL不能共用同一个计数/比较实现。检查器必须从**本次真实模拟器生成的VCD或等价四态trace**读取实际输出、输入事件和时间刻度，逐段积分/计算导通时间并检查输出边沿，不能直接把灰码乘tick当“实测”。

### 4.2 穷举主矩阵

- Pure：两种tick间隔×全部256个灰码＝512例。
- Hybrid：两种tick间隔×8个PAM选择码×全部64个时间码＝1024例。
- 合计1536个唯一主case。每例用两个逻辑实例接收相同控制和相同显示配置，分别检查并比较完整输出trace，共3072个实例观测。
- 额外测试两实例不同灰码/不同PAM选择，确认数据相互独立但窗口起点、结束边界来自共同事件。混码测试另列，不混入1536例的主矩阵计数。
- 每个非零主case只允许一个连续导通段，实测宽度严格等于第3节定义；黑码0段，窗口结束后持续关闭至少两个额外tick。
- PAM选择码须与该case锁存值逐位相同且在窗口内无变化；不能只看末值。

### 4.3 状态和异常矩阵

至少覆盖：

1. 上电、无配置、重复reset、运行中reset。
2. PWM_START保持40 ns只接收一次；同沿控制冲突有明确拒收行为。
3. BLANK内tick、启动前tick、窗口结束后额外tick和长时间停钟。
4. 在最短脉冲中间、窗口中间、终点前后断言BLANK或fault，且事件与参考时钟错开。
5. 清fault/撤BLANK不能自动恢复；新合法准备序列可以恢复。
6. 运行中加载下一灰码，不改变当前波形；下一次LATCH后才使用新码。
7. 合法安全切模式、运行中切模式、非法模式码、不完整配置、非法LATCH。
8. 数据0/1/254/255，Hybrid时间码0/1/62/63及PAM码0/7的连续切换。
9. 输入或输出X/Z不能被Python数值转换成0或忽略；应明确FAIL/拒收，未定义初始化段也不能漏到宣称有效的窗口。

### 4.4 真负例和突变测试

在临时副本中分别制造下列错误，真实重新编译/运行被修改RTL并让原检查器拒收，不修改黄金判据：

- Pure满亮255只亮255个区间，或Hybrid63只亮63个区间。
- 计数器回卷后又打开输出。
- 去掉BLANK优先门控或使其延迟到tick才关闭。
- PWM_START为高期间每拍重置。
- 仅一个实例延后一个tick启动。
- fault清除后旧窗口自动恢复。

可选择每种缺陷能可靠触发的最小用例；每种记录实际source摘要、仿真状态、被原检查器击中的具体断言。`EXPECTED_REFUSAL`/`DETECTED`与正确RTL的PASS分开，不能把故障DUT功能结果写成PASS。故障模型失效或没有被抓住时，负例闸FAIL。

### 4.5 证据入口和写保护

建立一个独立入口，例如 `scripts/dd1_d7a_run.py`：

- `--selftest`：检查器合成trace测试，不调用EDA。
- `--dry-run`：只做环境/输入/计划检查，不改正式证据。
- `--run-rtl --out review/dd1_d7a/<run_id>`：真实编译和运行本轮SV源码，导出本轮trace与结果。
- 独立负例/突变入口，输出另一个临时目录。
- 仅在所有必需正负闸通过后，显式导出待提交的小型证据。

具体参数可合理调整，但文档须给出一条可复制的重跑命令。缺模拟器、路径错误、缺trace、解析失败必须非零退出；输出写入须用临时文件原子替换。用预置非空证据＋哈希负例证明dry/拒绝/失败路径不覆盖正式CSV、不能把其清成表头。

## 5 应交付的证据

至少包含：

- `dd1_d7a_environment.json`：实际工具版本和本轮命令，不含凭据、主机标识、机器私有路径。
- `dd1_d7a_cases.csv`：1536个唯一主case，字段至少有模式、示例帧率、时间码、PAM码、tick_ns、两实例实际导通区间数/宽度/段数、起止时刻、配置版本、判据结果、run_id。
- `dd1_d7a_control_cases.csv`：异常/同步/配置切换记录；列出全部必测场景并显示是否真实执行。
- `dd1_d7a_negative.csv`：故障类型、实际突变源码摘要、case、模拟器退出码、checker退出码、失败断言、DETECTED/NOT_DETECTED。
- `dd1_d7a_edge_samples.csv`：至少覆盖黑/最短/末级/满窗口和异步关断的输入与输出真实样本；样本须跨越自己的事件锚点，有事件前和事件后数据。禁止只取事件之前的点。
- `dd1_d7a_manifest.json`：SV/TB/checker/输入向量与实际trace的SHA256、工具版本、run_id、case计数和证据文件摘要。大VCD留本地，不能只有一个不可复算的VCD哈希。
- `dd1_d7a_checker_selftest.txt`、`dd1_d7a_write_guard.txt`、安全闸和冻结文件摘要核对结果。

为了让云端在没有PDK/VM时也能独立复跑，全部RTL、testbench、独立检查器和生成确定性测试向量的自研源码必须提交。保留可在普通四态RTL工具上重跑的命令。小型代表trace可导出为CSV；全量VCD留本地，通过完整源码与环境记录重跑。

实际脉宽与窗端点不能只用汇总行自述支撑。行数、唯一case数、有限性、每个case↔manifest↔源码/trace身份对应必须从准备提交的字节复算。缺例、重复例、空表、NaN/Infinity、未知值都FAIL。

## 6 分阶段执行和每个STOP

### A 只读基线与工具盘点

核对远端full SHA、工作树、已有分支和工具。保护脏工作树，不reset、不强行checkout、不stash或合并队友工作。建议独立worktree；如有本地既存对象污染，可在新的隔离clone仅取已接受基线，原工作区保持不动。

远端固定Data分支若已变更，记录新增full SHA并读差异：不要把未知新提交并入本轮。固定基线仍可准确取到且无依赖冲突时，在其上建独立新分支；若必须依赖更新内容，STOP等待云端重新审定基线。

先建立checkpoint，明确本轮 `NEW_SPECTRE_RUNS=0`、`NEW_OA_WRITES=0`。

### B contract、检查器与最小可证伪探针

先写数字契约和checker自测，优先验证满窗口端点、PWM_START保持和异步关断三个易错点。至少一个故意错误trace必须被拒收，才开始扩大RTL主矩阵。

### C 实现和完整验证

只在允许路径实现单通道控制器和双实例测试；执行第4节全部测试。用独立综合工具做前端展开、过程转网表和结构检查，确认无未解决层次、同一寄存器多驱动、非预期latch或不能综合的过程。若有有意使用的存储结构，必须逐个说明其功能和推断结果。不能只看语言编译通过；没有可用综合器时记`BLOCKED_SYNTHESIS`，保留已完成的仿真，不宣布本阶段全部完成。无需工艺映射、PPA或时序优化。

### D 证据、安全、提交与远端回读

- 每个测试里程碑及上下文压缩前更新 `reports/agent_handoffs/DATA-7A.md`，保留命令、rc、失败、计数、下一步和UNKNOWN。
- 压缩后先读任务书、checkpoint、git状态、提交与真实文件，再继续。每个根因最多3次修复尝试；不得放宽端点、漏电、采样范围或覆盖旧结果来凑PASS。
- 新增`.sv`小例外后先跑原安全规则全套正负测试，再跑staged/history/objects、provenance与device-count等原有要求。
- 原有Spectre器件数和旧证据应逐字节不变；“零个新增MOS”只是此阶段没有进行MOS实现，不能作为PWM电路面积结果。
- 若objects扫描发现前轮已知不可达blob，保留现状、只列摘要及与开工前相比是否新增，不GC、不打印内容、不重写历史。**不得把FAIL写成PASS**。可在不含该不可达对象的隔离clone完成本轮正常闸；若仍有未解决的安全问题，则STOP，不绕过hook/push。
- 生成本轮完整review bundle，除报告外须含RTL、TB、checker、向量来源和小型结果。审查bundle自己的manifest和文件集合；共享bundle脚本若漏收新rtl/tests目录，允许只编写`dd1_d7a_`前缀的补充打包器，仍调用原安全闸、不修改共享扫描器或共享bundle源码。
- 普通提交、普通push到自己的新分支。禁止main、旧Data/Scan或队友分支写入，禁止force、merge、cherry-pick、公开仓库或更改可见性。
- push后用`git ls-remote`和已授权可用的`gh api`两条途径读取分支full SHA并核对本地；第二条不可用就明确`REMOTE_PARITY_PARTIAL`，不能编造双路一致。不得输出认证值，也不要求用户再给密码/token。

### 交接SHA的自引用处理

不要把“包含自身JSON的最终commit SHA”硬写进同一被跟踪JSON造成循环改写。

允许两步收尾：先提交源码/测试/证据得到payload提交P，再提交交接元数据得到最终交付D。JSON的`head_sha`指P，并额外写`head_sha_semantics=payload_commit`；最终回执独立提供`delivery_head_sha=D`和两路远端D回读。验证P是D的祖先，P..D只含约定的交接/证据索引元数据，功能源码不变。云端实际审查对象是D以及base..D完整差异。

不要为追求字段表面相等反复补commit或谎报远端。若采用其它等价办法，先明确SHA语义并保证最终交付D可准确回读。

## 7 验收表与不能混用的状态

| 闸 | 必须满足 | 失败状态 |
|---|---|---|
| BASELINE_IDENTITY | full SHA和冻结摘要准确，无混入队友/新提交 | BLOCKED |
| CHECKER_SELFTEST | 正负合成trace、空/缺/未知值与单位等均按预期处理 | FAIL |
| SYNTHESIS_STRUCTURE | 独立工具真实展开/结构检查通过，无未说明的多驱动、latch或不可综合过程 | FAIL/BLOCKED |
| PURE_MATRIX | 512例、两实例，码0/1/254/255及各实际宽度正确 | FAIL |
| HYBRID_TIMING_MATRIX | 1024例、两实例，PAM码稳定、6位时间与满窗口正确 | FAIL |
| CONTROL_AND_ABORT | 配置原子性、安全切模式、异步关断、不自动恢复等全覆盖 | FAIL |
| MUTATION_DETECTION | 六类真实错误RTL均被同一独立checker击中 | FAIL |
| WRITE_GUARD | dry/拒绝/失败不破坏正式非空证据 | FAIL |
| EVIDENCE_IDENTITY | 1536唯一主case、3072实例观测、实际源码/trace/结果可追溯，无空表或非有限值 | FAIL |
| FREEZE_AND_SECURITY | 既有冻结字节不变，安全规则仅允许小例外，必须安全闸通过 | FAIL/BLOCKED |
| REMOTE_READBACK | 最终D的普通push和实际远端full SHA回读 | UNVERIFIED/PARTIAL/FAIL |

不论RTL结果如何，本轮均保留：

```text
PWM_MOS_IMPLEMENTATION=NOT_RUN
PAM_8LEVEL_ANALOG_IMPLEMENTATION=NOT_RUN
HYBRID_CURRENT_INTEGRATION=NOT_RUN
GRAY_LUT_IMPLEMENTATION=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
PHYSICAL_CDC_AND_SKEW=NOT_VERIFIED
NEW_SPECTRE_RUNS=0
NEW_OA_WRITES=0
LAYOUT_DRC_LVS_PEX=NOT_RUN
SOA_SIGNOFF=NO
```

已有Data-6的D6_SETTLE首次入带、旧事件摘录不能独立复算和92端子对象更正保留原记录，本轮不为这些旧保留项重跑仿真或重写旧证据。

## 8 最终人机交接

人可读MD至少列出：环境、真实base、分支、文件差异、各闸结果与证据、失败记录、未知项、后续电路接口风险。

机器JSON按随包 `assets/handoff.example.json` 和 `scripts/validate_handoff.py` schema 1.0填写，使用真实full SHA。任务号固定DATA-7A，`scope_status=COMPLETE`仅表示本轮RTL阶段完成；不能把未做MOS/PAM写为PASS。运行原校验器，说明它只查字段，不证明远端或电路事实。

最终回执格式：

```text
TASK_ID=DATA-7A
BASE_SHA=<40-hex>
BRANCH=<own branch>
PAYLOAD_SHA=<P full SHA>
DELIVERY_HEAD_SHA=<D full SHA>
REMOTE_GIT_SHA=<actual full SHA or UNAVAILABLE>
REMOTE_API_SHA=<actual full SHA or UNAVAILABLE>
LOCAL_REMOTE_PARITY=PASS/PARTIAL/UNVERIFIED/FAIL
RTL_LOGIC_STATUS=PASS/FAIL/BLOCKED
PURE_MAIN_CASES=<actual>/512
HYBRID_MAIN_CASES=<actual>/1024
INSTANCE_OBSERVATIONS=<actual>/3072
MUTATION_CLASSES_DETECTED=<actual>/6
NEW_SPECTRE_RUNS=0
NEW_OA_WRITES=0
REPORTS=<relative paths>
KNOWN_LIMITATIONS=<explicit>
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

完成本轮就STOP。不要自动进入MOS、8档PAM、LUT、电流集成、完整阵列、GUI美化或下一编号。用户把D链接发回后，ChatGPT会实际读取D的源码、base..D完整diff、检查器和证据；评审建议与用户GO后，才可另发下一阶段任务书。
