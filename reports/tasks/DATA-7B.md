# DATA-7B：单通道固定电流 PWM 响应验证任务书

版本日期：2026-10-21。交给本地执行者 Qoder；完成后停在独立审核闸。

**You have NO access to the user–ChatGPT conversation; the current task brief and the named repository are your sources.**

## 0 本轮要回答的问题

DATA-7A 已证明单通道灰阶控制器能按约定输出数字使能。现在需要回答：把这些脉冲送到已经冻结的恒流输出级，实际端口电流能否及时建立、关断，每个窗口输送的电荷与约定导通时间相差多少？

本轮只验证**一个通道、固定约 15 µA、TT、27 °C、输出钳位 1.2 V**。用冻结 RTL 的真实四态仿真输出生成有限斜率 PWL 激励，再运行原生 Spectre。真实 MOS 被测部分是既有参考管、恒流下拉核心和互补使能反相器。

本轮允许建立新的验证 wrapper，不改任何冻结晶体管的模型、尺寸、体端或电气连接。若短脉冲不满足电荷目标，交付 `REWORK_REQUIRED` 的测量结果并停止；不得自行调整器件、偏置、电路或阈值。

这一步有明确的实现边界：灰阶计数、存储和协议控制仍是 RTL；PWL 是离线验证激励。它不构成全 MOS 灰阶控制器、混合信号联合仿真、片内数字单元工艺映射或八档 PAM 的完成证明。后续产品仍计划片内产生 PWM，不能把本轮 PWL 回放改写成最终外置控制方案。

## 1 固定身份、远端及分支

| 项目 | 固定值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| TASK_ID | `DATA-7B` |
| 新工作分支建议 | `poc/data-pwm-d7b` |
| Git 开发基线 B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 已接受的 DATA-7A 内容版本 A | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| A 上的验收登记 | B；只向 `reports/agent_handoffs/DATA-7A.md` 增加 36 行，JSON、代码与证据未变 |
| DATA-6 固定参考 | `731767519d1a51287eb5b7f4a6e4f9b8e613e990` |
| 保持不动的 main | `23e471cb936b421ee97e1250c3be06edf96f9937` |

云端于 2026-10-21 实际回读了上述分支位置，并从 Git blob 读取冻结接口、器件定义、执行器及下表摘要。开工时还须用 Git 协议与 GitHub API 核对 B、A 的父子关系及远端位置；不要从 `main` 开发。

若远端基线发生变化，或建议分支已有不明工作，保留现场并报告；不 reset、不覆盖、不 force。可以在确认 B 后新建唯一同前缀工作分支及独立 worktree。不要清理以前的 worktree。

### 1.1 必须先读的仓库文件

- `README.md`、`AGENTS.md`、`CONTRIBUTING_AI.md`、`.gitignore`、`spec/system_requirements.md`。
- `reports/agent_handoffs/DATA-6.md`、`reports/agent_handoffs/DATA-7A.md` 和 `.json`。
- `reports/dd1_d7a_contract.md`、`reports/dd1_d7a_rtl.md`、`rtl/dd1_d7a_gray_ctrl.sv`。
- `spectre/dd1_d6_top.scs`、`dd1_d6_control.scs`、`dd1_d6_sink_unit.scs`、`dd1_d6_sink_core.scs`、`dd1_d6_bias_core.scs`、`dd1_d6_inv18.scs`。
- `scripts/dd1_d6_unit_tt.py`：了解方向注释兼容处理、零负担电流探针、原生 runner 及历史测量保留项；不调用其旧正式仿真入口。
- `scripts/run_spectre.sh`、`scripts/tb_preflight.sh`、`scripts/sc1_supply_check.awk`；按实际依赖继续读 PSF 读取器、调用契约与采样工具。
- `scripts/repo_safety_rules.py`、`test_safety_rules.py`、`precommit_safety_check.py`、`provenance_check.py`、`netlist_stats.py`、`make_review_bundle.py`。
- `scripts/dd1_d7a_validate_handoff.py`、`scripts/dd1_d7a_bundle.py`；只读参考，不改旧工具。

### 1.2 冻结摘要：对 Git blob 计算 SHA-256

| 路径 | SHA-256 |
|---|---|
| `rtl/dd1_d7a_gray_ctrl.sv` | `6dbf464a49e49ad489188fa51920c30a3c89d6b3106046a4fefe558ef0a50c87` |
| `reports/dd1_d7a_contract.md` | `37f55cb9f0783e2f184ad360f69ee07526f1aba5d39f6698388826b3b8652284` |
| `spectre/dd1_d6_sink_core.scs` | `6cfe2338014a4b152833ef1974f197b0e4c65e963947f57f0cc8b79b73ee91db` |
| `spectre/dd1_d6_bias_core.scs` | `4115e2d17a86fb92e7c222df085f1d1a82da14cb7640654d90f4e2589e9b31e7` |
| `spectre/dd1_d6_inv18.scs` | `04cd6833087511465aba06a3d2ba2f1ba71a49cce1ae962febff3b3eb1e4d79b` |
| `scripts/dd1_d6_unit_tt.py` | `8c80ba0d656a2403962b36fad32c7c088203374c532a03e41967357baad281a0` |
| `scripts/run_spectre.sh` | `c837893ae2b32309306d3b260bca01a3f7f1223b8d3a187a2072a1e3c14753f7` |
| `scripts/tb_preflight.sh` | `6255981cb6975149b3542305b4f24c7e283eb617b51427c594818134d2e4d3bc` |
| `scripts/sc1_supply_check.awk` | `7f7cb0223f97d1567425e0d42a6e104eca76584a80b4ca33ee554edbd707cfaa` |
| `scripts/repo_safety_rules.py` | `effac1a15bf269119c40f9339dc550352b1f65afaf010da4168a8f18895cc08c` |
| `scripts/test_safety_rules.py` | `236d52942748eadfe2b0353f6954daaf703f35f7c580e15e0802acab99083e96` |
| `scripts/dd1_d7a_validate_handoff.py` | `3c150d543465a5d17a9d63c700f6b895c82fb868cae9408b2afd47643603e1e5` |

这张表不是全部冻结集合。**B 中全部既有跟踪路径均冻结**；结束时逐路径比较 tree/blob，不能只抽查这 12 项。工作树换行规范化与已提交 blob 要分开记录。

## 2 事实、假设和保持未定义的内容

| 内容 | 本轮采用 | 来源层级与限度 |
|---|---|---|
| 产品需求背景 | 1024×768、60–100 Hz、像素选通导通目标 15 µA | 既有 `COURSE_REQUIREMENT` 登记；不是整帧平均 15 µA |
| 原有最小单元 | DATA-6 顶层展开 29 管，已验收限定 TT；本轮原样冻结 | 仓库已有交付；不把它的宽脉冲结果外推到 30 ns |
| 灰阶数字契约 | Pure 8-bit PWM；Hybrid 3-bit PAM 请求码 + 6-bit PWM 时间码 | `POC_ASSUMPTION`，继承已验收 DATA-7A；不是光学有效 9 位 |
| 固定电流测试条件 | IREF=15 µA、VCAS=1.8 V、VDD18=1.8 V、VSS=0 V、DATA_OUT 钳位 1.2 V | `POC_ASSUMPTION` / `TESTBENCH_ASSUMPTION`，沿用原核心代表性条件 |
| 模型与温度 | 现行 SMIC PDK，section=tt，27 °C | 限定原生 TT 探针；从产物反读，不用文件名代替实际 section/温度 |
| 输入转换条件 | 0–1.8 V；基准上升/下降时间 2 ns；补测一项 10 ns | 本任务新增 `POC_ASSUMPTION`；理想电压源驱动，未含片内数字驱动器输出阻抗 |
| 数值条件 | gear2only，基准 maxstep=0.5 ns；指定案例复测 0.25 ns | `POC_ASSUMPTION`，必须检验收敛，不能直接宣称采样精度 |
| 参考预建立 | 至少 2 µs，局部使能保持 0；不向 vbias_ch 预置电压 | 测试准备条件；不是产品上电时序已实现 |
| 实际八档电流 | 仍 NOT DEFINED，本轮 Hybrid 只固定 `pam_sel=7` 的时间路径 | 不能把理想 IREF 随码变化冒充八档 PAM 电路 |
| LED I–V、光学映射、真实互连 RC、最终 VLED/VSCAN、SOA | 保持 NOT_DEFINED / NOT_VERIFIED | 输出钳位不等于 LED、阵列或封装 |

DATA-6 中命名为 `D6_SETTLE` 的 17.8–20.5 ns 导通、22.4–23.1 ns 关断数据是**首次入带**；不能写成持续稳定时间。本轮另按第 6 节定义测量，不修改旧数据。

外部参考阅读（2026-10-21 已实际读取的厂家原始资料）：

1. TI，SSZT647，2018，https://www.ti.com/document-viewer/lit/html/SSZT647/GUID-B42F4989-AA4F-43DC-8333-DA8D9D9EAB78 。说明使能式 PWM 的实际电流建立/关断响应会限制最短可用脉宽。文中含开关电源示例，不能将其微秒数值搬到本项目。
2. Analog Devices，Using Hybrid Dimming with MAX25510 and MAX25511，2022-02-08，https://www.analog.com/en/resources/technical-articles/using-hybrid-dimming-with-max25510-and-max25511.html 。作为“时间与电流幅度共同调光”的概念参考；不是本项目 3+6 编码、拓扑或电流档的来源。

## 3 冻结与授权边界

### 3.1 允许新增的跟踪文件

- `spectre/dd1_d7b_*.scs`：自研验证 wrapper/可公开模板；不得含模型卡或本机 PDK 路径。
- `tests/dd1_d7b/`：自研 SV testbench、小型向量、独立黄金表和合成波形测试。
- `scripts/dd1_d7b_*.py`，必要时同前缀 `.sh` / `.ps1`。
- `reports/tasks/DATA-7B.md`：本任务书逐字节副本。
- `reports/dd1_d7b_contract.md`、`reports/dd1_d7b_pwm_current.md`。
- `reports/agent_handoffs/DATA-7B.md` 和 `.json`。
- `results/evidence/dd1_d7b_<run_id>/` 内脱敏文本、CSV、JSON、小型样本分片和命令转录。

不允许修改安全规则、旧 packer、旧 runner、旧 RTL/契约/检查器、旧报告/证据、系统规格书或 `AGENTS.md`。需要不同发布/打包行为就在本任务前缀内实现；若必须更改既有共享工具，则带原因停下，不自行扩大权限。

### 3.2 明确禁止

- 不修改/写入任何 OA 库、schematic、symbol、CDF、`cds.lib`、手工美化视图或 PDK；`NEW_OA_WRITES=0`。
- 不启动 Virtuoso/dbAccess、OA 导入、原理图美化或截图。
- 不做虚拟机电源、快照、`.vmx`、全局网络/SSH/注册表或 license 变更。
- 不设计八档 PAM、电流 DAC、共享偏置缓冲/保持电容、自主基准、新 MOS PWM 拓扑或数字标准单元映射。
- 不做 TCON、HDMI/DSP、LUT、完整灰度映射、CDC/skew、Scan 更改、阵列、多通道、corner/温度扫描、Monte Carlo、layout/DRC/LVS/PEX。
- 不合并 main、不移动旧分支、不 force、不跳 hooks、不改可见性、不 GC/prune 或重写历史。

### 3.3 本机和 guest 的实际执行授权

先只读探测当前 OS、工作树、Python、四态 RTL 仿真器、SSH 和 Spectre 版本；不假设 IP、安装路径或原 worktree 仍有效。利用既有凭据机制，不输出凭据值。

本任务被用户转交执行时，授予本轮限定的 SSH/scp 和原生 Spectre 验证权限。guest 写入限定在全新任务根：

`/root/microled_ai_project/cadence_work/dd1_d7b/<run_id>/`

建议将冻结的 `run_spectre.sh`、`tb_preflight.sh`、`sc1_supply_check.awk` 及实际所需依赖逐字节复制到这个任务根的 `scripts/`，计算与 B 的摘要一致性；使用任务根作为 `PROJ`。这样 frozen runner 的 `home/`、`logs/`、`sim/` 都落在本任务根。`PDK_ENV` 只读指向已有未跟踪的配置文件，不复制其内容，不在已跟踪文件中写出其实际值。环境加载器仍只读复用既有文件。

若隔离运行与实际工具不兼容，先报告阻塞；不退回覆盖既有工程脚本、共享 HOME 或旧正式结果目录。每个 case/attempt 使用唯一目录/文件名，避免旧 runner 删除同名旧日志的行为影响证据。

### 3.4 新的进程额度

本轮单独授权**最多 52 次 Spectre 进程启动**，包括动态 preflight、正式分析、失败/超时、临时探针及帮助调用。旧 DATA-6 的 19/20 额度不继承、不合并。

计划：24 次 DUT transient + 每次之前 1 次动态 rail preflight = 48 次；其余最多 4 次只供必要工具探测或纠错。每次启动前写入持久账，记录 launch_id、case_id、角色、源/激励/电路摘要、启动/结束、rc、被否决原因。失败也计数。达到上限即停止，不通过“重跑不计数”规避。

不运行额外的整套 PDK 探针或旧 DATA-6 回归。单个工程问题最多 3 次纠错尝试，且始终受总额度限制。电路不达标不属于授权修电路的理由。

## 4 MOS 被测边界：展开 7 个器件

建立 `dd1_d7b_pwm_stage`，建议端口顺序：

`(data_en iref_in vcas data_out vdd18 vss)`

内部只实例化三个冻结 master：

```spectre
Xbias (iref_in vss) data_bias_ref
Xinv  (data_en data_en_b vdd18 vss) dd1_inv18
Xsink (data_en data_en_b iref_in vcas data_out vss) data_sink_1ch
```

实际 MOS 为参考 1 + 反相器 2 + 下拉核心 4 = 7。按现有 PDK 主名口径统计：`n18×1, p18×1, n33×4, n33_dnw_4t_ckt×1`。从层级和实例展开机检，不用 grep 器件前缀。

原 DATA-6 的完整 29 管顶层及其 C²MOS DFF/NOR 仍原样保存。本轮 wrapper 刻意从 `data_en` 输出级接口进入，不能说“29 管电路已经接上了完整灰阶控制器”。7 管不包含灰阶计数器、8-bit 存储或片内数字驱动器。

连接必须保持：

- `DATA_OUT → Mcas → node_m → Mout → VSS` 为主下拉路径。
- Mref 栅漏短接；外部 IREF 注入该节点。不能用理想 VBIAS 电压源替掉 Mref。
- Mpass 使用冻结 `n33_dnw_4t_ckt`，体端接 `vbias_ch`，不能换回普通 n33 或改为 VSS。
- Mbleed 的栅接**实际 MOS 反相器输出** `data_en_b`。不以理想互补 PWL 或旧 qbar 替代。
- RTL 的 `data_en_b` 作为数字一致性检查对象保留在 VCD，但不强制钳住模拟反相器输出。

冻结 leaf 在 Spectre 落盘时只允许剥除已知不兼容的 `parameters <port> input/output/inputOutput` 方向注释；仓库原文件不改。对剥除行逐项留账，并核对**完整 subckt 端序、器件端网/模型/尺寸和其余语句**一致，不能只依赖一个可能漏行的简化摘要。

台架使用显式 VSS 独立 0 V 源、VDD18=1.8 V、IREF=15 µA、VCAS=1.8 V、输出钳位 1.2 V，以及零负担 `iprobe`。电流正方向固定为“钳位源流入 data_out、进入 DUT”，从探针原始有符号电流读取，不能用绝对值悄悄改方向。禁止额外电容、任意 initial condition、偏置修调或串联负担电阻。

供电契约使用 `vdd18=1.8 vdd=1.8 vss=0 VSS=0`，覆盖 wrapper 及三个 leaf 的实际端口拼写。先展开全部非 PDK 层级再检查，不能只查 wrapper 的顶层电源。

云端已经用冻结的 AWK 对上述结构草案做了纯离线核对：`top=1 descendants=3 checked=6 internal=0 masters=4 / PASS`；去掉 VSS 独立源则 rc=1、明确 `SUPPLY_FAIL`。此项没有启动 Spectre，不是实际本机 preflight 的替代；实际生成的每份 deck 仍须重新过闸。

## 5 从冻结 RTL 到 Spectre 的激励链

1. 用 B 中逐字节未改的 `dd1_d7a_gray_ctrl.sv`，加本轮新 testbench，运行真实四态仿真。一个控制器实例即可。
2. 参考时钟为 100 MHz；`tick` 是同域 clock-enable，分别隔 3/5/12/20 个参考周期。输入在采样沿之前建立，避免 TB race。
3. 严格执行安全模式采纳、load、LATCH、START、首个有效 tick 的协议；从真实 VCD 反读 `data_en`、`data_en_b`、`obs_tick`、模式、显示码、`pam_sel`、状态和配置版本。不能绕过 load/LATCH 直接强制内部寄存器。
4. 用独立手写期望表核对时间窗口；检查器不从 DUT 自己的 target/index 算期望。黑码无使能上升沿，其 t0 仍须从真实启动/tick 协议确定。
5. 基准 PWL 电平为 0/1.8 V，每个 RTL 边沿的真实时间作为模拟斜坡的 50% 位置；2 ns 斜坡从该时刻前 1 ns 到后 1 ns。10 ns 补测用前后各 5 ns。记录 VCD 时间单位、ps 整数时间、统一平移量和缩放规则。
6. PWL 时间严格递增，不允许 X/Z、NaN/Inf、时间倒退、重复时间的矛盾值、负时间或相邻斜坡重叠。遇到不能表示的短毛刺应拒收并报告；不静默删除、取整或拉长脉冲。
7. 同一份 VCD 的基准、收敛和斜率补测可复用，但必须记录相同 trace 摘要及不同转换条件。CAL 标定源为本任务单独声明的静态/长脉冲台架，不伪装成 RTL 输出。

规范导通区间数 N：Pure code 0→0，1…254→码值，255→256；Hybrid time 0→0，1…62→码值，63→64。PAM 请求码本轮固定 7，不扫描其余 7 码，也不宣称请求码已由模拟译码器转换成电流。

| 模式 | tick 间隔 T | 完整窗口 W |
|---|---:|---:|
| Pure / 100 Hz 时序例 | 30 ns | 7,680 ns |
| Pure / 60 Hz 时序例 | 50 ns | 12,800 ns |
| Hybrid 时间路径 / 100 Hz 时序例 | 120 ns | 7,680 ns |
| Hybrid 时间路径 / 60 Hz 时序例 | 200 ns | 12,800 ns |

这里的 60/100 Hz 只说明承接原时序预算；本轮未实现全阵列逐列刷新、976/977 调度或视频接口。

## 6 先冻结测量契约，再开始原生仿真

先完成 `reports/dd1_d7b_contract.md`、case 表、独立黄金表和离线检查器自测，记录摘要。开始 native 后不为变绿改阈值、窗口或 case；发现契约/工具错误就保留旧失败并标明作废原因和受影响的 run，不把不同源码证据拼成一次成功。

### 6.1 标定和基准

CAL：使能先低，2 µs 时升高，4 µs 时降低，仿真到至少 4.5 µs；使用同一 2 ns 沿和冻结 7 管 DUT。

- `Ical` 取 [3.0 µs, 3.5 µs] 的时间加权均值，同时输出该窗 min/max。
- 标定电流需处于 15 µA±5%：沿用 DATA-6 POC 容差，不改成产品精度承诺。
- OFF 基线取 [1.5 µs, 1.9 µs]；关断末段取 [4.4 µs, 4.5 µs]，记录有符号均值和 max(abs(I))。
- 稳态 OFF 的 max(abs(I)) ≤0.15 µA，沿用既有 POC 容差。
- 标定不通过则其他电流结论标为 BLOCKED，不能靠逐案例重新标定抹掉失配。

### 6.2 每个正常 PWM 窗口必须计算

令 t0 为该案例实际首个有效 tick，t1=t0+W。导通预期持续 N×T；模拟完成时间至少超过 t1 200 ns。

- 端口净电荷：`Qwin = integral(Iout(t), t0, t1)`。
- 目标电荷：`Qexpected = Ical × N × T`；另报以 15 µA 为参考的绝对增益误差，避免归一化隐藏它。
- `QLSB = Ical × T`；报有符号 `charge_error_LSB=(Qwin−Qexpected)/QLSB`。黑码不计算除以 Qexpected 的百分比。
- 分别报正向积分 Qpositive、负向积分 Qnegative，满足 `Qwin=Qpositive+Qnegative`；明确负电流是端口瞬态，不能直接当作 LED 发光电流。出现明显正负抵消时保留独立数值，不用净值证明光学灰阶。
- 单独积分 [t1,t1+200 ns] 的后窗尾电荷；不能只截到逻辑下降沿，也不能把尾电流删掉后叫准确 PWM。
- 窗口及后窗 Iout 最大/最小值、峰值时刻；data_en 与实际 data_en_b 的 50% 交叉及其差值。
- 电流 10%/90% crossing 的阈值分别为 0.1×Ical、0.9×Ical；若存在，用相邻样本夹持+线性插值；缺失输出 NOT_FOUND，不回退到最后一点。
- 持续入带时间：从实际 data_en 50% 沿起，找到电流进入 Ical±5% 后、持续至预期关断沿前且至少 10 ns 不离带的最早时刻。短脉冲没有这样的区间，标 `NOT_SETTLED_WITHIN_PULSE`，不冒称稳定。
- 关断时间：从 data_en 下降 50% 起，找到 |Iout|≤0.15 µA 且在该关断观察段余下样本始终不越限的最早时刻。

所有积分都按真实不等间隔时间做梯形积分，并在边界内插入插值点。禁止“样本均值×窗口宽度”、只取若干摘录点、外推不存在的端点，或对电流先取绝对值再冒充净电荷。分别报告窗口平均电流与电荷，不以峰值代替。

计算统一使用秒、安培、库仑，结果表保留 SI 原值列；ns、µA、pC 只作为明确换算后的展示列。例如名义 15 µA×30 ns=0.45 pC，不能混用时间单位。

### 6.3 本轮电气可行性目标

以下是**本任务提出的 POC 电气判据**，不是老师原始容差、foundry 额定值或光学有效位数：

1. 所有正常抽样码满足 `abs(charge_error_LSB) ≤ 0.5`；黑码也按同一绝对电荷尺度判断。Pure 满亮按 256 区间、Hybrid 满亮按 64 区间，不能当成 255/63，也不把最高码处约定的两区间跳变误判为 DUT 新错误。
2. 每个关闭后观察段最后连续 100 ns 的 max(abs(Iout)) ≤0.15 µA；BLANK/FAULT 释放后没有新授权时也应保持该条件。
3. 参考电流、极性、逻辑/PWL 边沿身份、所有必需数据和数值收敛检查通过。

后窗尾电荷、峰值、持续入带时间必须报告；其产品额定预算仍未定义。无 LED/光学模型，不从这组抽样码推出完整 8-bit 电气 DNL/INL、9-bit 光学灰阶或肉眼显示效果。

### 6.4 数值收敛

第 7 节指定的 4 例以 maxstep=0.25 ns 重新运行，其余电路、激励及积分区间保持相同：

- `abs(Qwin_0.25−Qwin_0.5) ≤0.01×QLSB`。
- `abs(peak_0.25−peak_0.5) ≤max(0.05×abs(peak_0.25), 0.15 µA)`。
- 存在的 50% crossing 时间差 ≤0.5 ns；缺失不能伪填 0。

不通过则相关可行性结论为 `NUMERICAL_NOT_CONVERGED`。保留两组数据，剩余额度只用于定位；禁止悄悄选择更好看的一组。由于未覆盖所有参数，本轮不会成为数值方法或器件可靠性签核。

## 7 固定案例矩阵：24 次 DUT 分析

| 组 | case ID | 内容 | DUT 次数 |
|---|---|---|---:|
| 标定 | `D7B-CAL` | 第 6.1 节固定长脉冲 | 1 |
| Pure 30 ns | `D7B-P30-C000/001/002/016/254/255` | 6 个独立窗口，实际冻结 RTL 输出 | 6 |
| Pure 50 ns | `D7B-P50-C001/255` | 最小和满亮 | 2 |
| Hybrid 120 ns | `D7B-H120-C00/01/02/62/63` | 5 个时间码，PAM 请求码恒为 7 | 5 |
| Hybrid 200 ns | `D7B-H200-C01/63` | 最小和满亮，PAM 请求码恒为 7 | 2 |
| 异步撤销 | `D7B-BLANK`、`D7B-FAULT` | Pure30、code16；见下文 | 2 |
| 真实接线负例 | `D7B-N1` | 复用 P30 黑码激励，仅把 wrapper 的使能实参接 vdd18 | 1 |
| 收敛复测 | `D7B-CVG-P30-C001/255`、`D7B-CVG-H120-C01`、`D7B-CVG-BLANK` | 与对应主案例相同，仅 maxstep 改为 0.25 ns | 4 |
| 输入斜率补测 | `D7B-SLEW-P30-C001` | 复用同一 VCD，模拟输入升/降时间由 2 ns 改为 10 ns | 1 |
| **合计** | | 24 DUT + 24 动态 preflight；另有静态负例和离线自测 | **24** |

按定义共有 15 个正常码窗口+2 个安全场景，需要 17 份真实 RTL 源 trace。标定不用 RTL，N1/收敛/斜率案例声明复用对应 trace。若工具组织为一次编译、多次仿真，逐次统计实际执行次数；不能将编译次数说成 trace 数。

安全场景：从合法 code16 窗口开始，在 `t0+4.5T` 异步拉高 BLANK 或 FAULT；到 `t0+7.5T` 撤销。tick 在撤销前后持续。无新 load/LATCH/START 时 data_en 必须继续为 0，不能因保护释放自行恢复。观察完原窗口后，按冻结契约完成一次全新的 load→LATCH→START，再产生一个 code16 正常窗口，证明真正恢复路径。mode 不变、参考电流不变。记录所有实际事件，避免用采样相位错误替代授权撤销验证。

安全案例的中止窗和恢复窗分行记录。中止窗的理想导通时间为 4.5T，报告 `Qexpected=Ical×4.5T` 及实际净/正/负/尾电荷，不拿未中止的 16T 误判它；该窗以正确关断、保持关闭和真实恢复为必需功能判据。恢复窗按正常 code16 和 0.5 LSB 电荷目标判断。

N1：只在新建的负例 deck 中，将实例使能实参由 `data_en` 改为 `vdd18`，使 7 管输出级保持开启；源 VCD/PWL 仍是黑码。逐语句 diff 证明只改变这一根接线，使用与正例相同检查器。必须观察到禁亮窗口的真实非零电流及超出判据；不是仅改 CSV、预期值或 `pass=false`。预期结论 `EXPECTED_REFUSAL / WIRING_FAULT_DETECTED`，不计入正常案例 PASS。

静态负例 N2：在独立目录将一个合法 deck 的 VSS 独立源去掉。沿用原冻结 supply checker，必须在 `stage=supply_contract`、非零 rc 拒绝，且该目录下 0 次 Spectre 启动。不能用“脚本没找到文件”代替 supply 拒收。

斜率补测是敏感性观察，独立报告相同电荷指标；若它不达目标，不抹掉基准条件结果，也不能宣称输入斜率不影响性能。

## 8 离线测量自测与执行器复用

### 8.1 检查器必须先自证

用手工可计算的合成波形测试，而不拿 DUT 数字当黄金值。至少覆盖：

1. 不等时间步长的矩形/三角形积分、内部窗口裁切与端点插值。
2. 正/负电流分别积分、正负抵消不能冒充无脉冲。
3. 黑码分母为零、满亮的 256/64 特例。
4. crossing 未被夹持、缺少窗口前后数据、尾部被截断时明确拒收。
5. 先入带后离带的波形不能报持续整定成功；短脉冲未整定有明确状态。
6. NaN/Inf、重复或倒退时间、空数据、错误单位、缺信号、X/Z 和斜坡重叠拒收。
7. 非整数 ps/码值不经截断变整数；接受数学上确实为整数的合法表示。
8. 对事件前摘录充当完整积分证据的旧型缺陷，要求失败。

增加至少 4 项离线破坏例：PWL 下降沿错移一个 tick、探针方向翻转、积分数据尾部缺失、case 表重复键且缺少另一必需案例。每例说明被破坏对象、实际触发的断言；不能仅靠改写结果字段证明检查器“检测成功”。它们不额外启动 Spectre。

### 8.2 安全复用，避免再造整套基础设施

复用冻结 runner、preflight、供电检查、PSF 读取、插值和 Git 安全规则。必要适配写在本任务前缀中，不能重新实现一套更宽松的 rail/成功判据。

为新入口提供明确模式，例如 `--selftest`、`--dry`、`--run`、`--check-evidence`。`--run` 还必须同时要求 `RUN=1` 与 `QODER_SIM_AUTHORISED=1`，并核对本轮 case 数和预算。所有静态检查在第一条 Spectre 启动之前完成；每次 DUT 之前再执行原动态 preflight，确认 rc、token、rails 和新产物身份。

`--dry`/未授权/拒收/缺工具等路径仅可使用忽略的 scratch；不写正式 evidence，不执行 Spectre。用预置非空正式文件夹测试文件集合和逐文件摘要不变。命令 rc 单独获取；不由 `tail`、管道或多命令链掩盖错误。

本轮正式证据建议采用**不可覆盖的整轮目录**：先在 ignored scratch 生成完整集合，全部校验后，将目录移动到尚不存在的 `results/evidence/dd1_d7b_<run_id>/`；目标已存在则拒收。避免复刻跨多个已有文件的回滚/覆盖发布器。临时目录和目标应在同一文件系统，保留失败现场；不声称强杀/断电持久性原子。

## 9 可独立复算的证据

本轮不再接受“仅事件前若干点”的摘录作为电荷证据。必须交付：

- 每个 case 的向量/黄金 N、RTL/VCD 摘要、PWL 完整可公开定义及转换参数。
- 每个实际 DUT 和 preflight 的身份、deck/源摘要、temp/section 反读、原始 rc/token、新产物摘要、进程账和失败尝试。
- `cases.csv`：必需集合、观测 t0/t1/交叉、Ical、Qwin、Qexpected、QLSB、charge_error_LSB、Qpositive/Qnegative、尾电荷、峰值/时刻、入带和关断状态、判定原因。
- `charge_samples_*.csv`：**覆盖所有积分区间及边界夹持点的完整时间/Iout 样本**，足以从提交字节重新算出电荷；不能仅保存测量结果或无误差界的下采样。负例/收敛/斜率补测同样覆盖。
- `edge_samples_*.csv`：包含每个用于声称的 50%/10%/90% crossing 两侧的实际样本，以及实际峰值点两侧；保存 data_en、真实 data_en_b、vbias_ch、参考节点、输出电流等所需值。
- `convergence.csv`、`negative.csv`、`source_identity.json`、`environment.json`、`process_ledger.csv`、离线自测和写保护转录。
- `manifest.json`：已提交字节的路径、大小、SHA-256、source/run/case 关系。manifest 不为自身写哈希；报告、handoff 也不写自身文件摘要。

大 CSV 按完整行拆为小于 180 KiB 的 UTF-8/LF 分片，记录表头、序号、范围、样本总数与完整序列摘要。禁止用压缩包/二进制绕过仓库规则。跟踪的新证据总量以 32 MiB 为上限，超出则保留本机完整数据并报告，不偷删样本或放宽规则；需要调整交付方式时交回审核决定。

增加 `scripts/dd1_d7b_evidence_check.py`：仅凭提交字节重算所有已交付电荷，验证矩阵完整/唯一、数值有限、分片顺序、正负积分恒等式、固定映射、case/run/source/digest 一致性及实际判据。语义篡改后即使重算摘要也必须被拒收。它不得联网/调用 Spectre，不得写被检查证据；云端可在没有 PDK 的环境运行。

复核器检验的是“记录是否与重算结果一致”。如实记录的电气指标 FAIL 可以通过证据一致性复核和导出；把 FAIL 写成 PASS 则必须拒收。不要把“所有电气指标必须先 PASS”设置成保存失败测量证据的条件。

纯摘要无法证明真实工具执行，因此同时交付脱敏的实际命令转录、关键原生输出和实际 VCD→PWL 边沿表。完整 VCD/PSF/工具二进制/PDK 本体保留本机 ignored 目录，不入库；摘录不能冒充全量 raw 交付。

## 10 报告：验证可靠与电气达标分开

`reports/dd1_d7b_pwm_current.md` 至少包含：

1. 一张清晰边界图：冻结 RTL→VCD→有限斜率 PWL→7 管 MOS 输出级→零负担探针。标明哪些是实际 MOS，哪些是验证源。
2. 实际被测层级、器件端网/尺寸、7 管统计；与冻结 29 管顶层的关系。
3. 24 次计划案例的实际完成/拒绝/未执行项及所有失败尝试；进程账有多少就写多少。
4. 短脉冲与满亮的 Iout 曲线、时间码与实际电荷对照、尾电流、数值收敛和 2/10 ns 沿差异。图为辅助，结论必须有可复算数据；若图形格式不在现有白名单，留在 ignored review 包中，不改安全规则。
5. 分别报告 `EVIDENCE_STATUS` 与 `PWM_CURRENT_FEASIBILITY_TT`。证据完整且判据真实执行可以 PASS；电路指标失败则可行性为 `REWORK_REQUIRED`，不能把它改叫整体电路 PASS。
6. 哪个条件先限制最短脉冲、是否只是端口钳位下的电气现象；提出后续 1–2 个候选方向但不实施。
7. 剩余缺项：八档 PAM、LUT/光学标定、全 MOS 数字控制器及 OA、驱动阻抗、CDC/skew、阵列 RC、最终电源、PVT/SOA。

若电气不达标，本轮依旧应提交完整结果供审核。无法满足任务验收时，handoff 的 `scope_status` 按事实为 PARTIAL/BLOCKED，不能在 test FAIL 时仍写 COMPLETE 来骗过结构验证器。

## 11 Git、交接与独立审核

重大里程碑及时更新本轮自己的 handoff；正文与 JSON 记录当前源 SHA、工具版本、case 进展、失败、下一步和 STOP，防止压缩上下文后失去边界。

交付时先形成一枚完整功能/测量 payload P，再用单独的少量元数据提交记录 P 与回读结果。`head_sha` 可固定为 P 并明确其角色；最终 D/tip 从 Git ref 或外部清单读取，不通过反复改文档追逐“自身 SHA”。本任务书副本必须逐字节匹配，不能悄悄改授权或阈值。

提交前运行并保留真实 rc：

- 本轮 checker/转换器自测、静态 gate、真实负例、收敛与离线 evidence check。
- 本轮 handoff 结构校验：可将冻结 `dd1_d7a_validate_handoff.py` 逐字节复制成 `dd1_d7b_validate_handoff.py` 使用，不改其校验语义。
- `test_safety_rules.py`、`provenance_check.py`、`netlist_stats.py`、staged/history/objects 扫描、base..payload 与 base..tip 的 `git diff --check`。
- B 的全部既有跟踪路径逐 blob 比较应 0 变化；仅新增允许前缀路径。记录 main 与全部旧远端 refs 前后位置，不因历史存在待验收 Scan 而改写其状态。

`--mode objects` 如再次命中既有不可达 blob，保留失败和身份，不打印内容、不 GC、不豁免、不据此宣称全库清洁。依原 staged/history hooks 决定正常个人分支 push；若 hook 拒绝就保留 PUSH_PENDING/BLOCKED，不跳过。不同克隆对象集不同，分别报告，不把某克隆无不可达对象当成所有本机已清洁。

先生成共享 `make_review_bundle.py B P` 所要求的基础审核包。若它遗漏 SV 或本轮完整依赖，在本任务新 packer 中补齐；不能修改共享 packer，不能静默漏文件。补充包取自固定 Git blob，明确包含本轮任务、源文件、黄金表/新 TB、冻结 RTL、三个冻结 leaf、调用的共享工具依赖、测量/复算脚本、报告、证据与交接。每项通过既有安全扫描；不把忽略的日志原件、PDK、VCD/PSF或二进制带入。

包内 `MANIFEST.csv` 逐项核对 zip 字节与 `git cat-file blob <D>:<path>`，附来源 full SHA 和必需文件集检查。ZIP 整体摘要只写到包外回执；最终包不能包含仍在变化的未提交工作树字节。工具发布身份与功能测量身份分别列出。

正常非 force push 自己的新分支后，Git 协议与 GitHub API 独立回读同一个分支对象及 SHA。网络失败如实记录；不把一个失败命令后另一个成功命令的 rc 混成 PASS。不要移动 `poc/data-gray-d7a-r4-doc` 或 main。

## 12 固定停止条件与回执

完成上述限定测量、证据、正常推送与双路回读后停下，等待云端实际读取 base..tip、源码、测量方法、正负结果及证据的独立审核。**执行者不能自行给最终 GO。**

遇到工具缺失、冻结摘要不符、隔离写入失败、预算不足、共享工具必须改动、安全拒绝或数据不能独立复算，按实情停下；不要为了推进自动做八档 PAM、新拓扑或 OA。

回执至少列出：

```text
TASK_ID=DATA-7B
BASE_SHA=c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37
ACCEPTED_RTL_CONTENT_SHA=f68449672774ac9266ba9e4893024e4f3027dd9d
PAYLOAD_SHA=<actual full SHA>
DELIVERY_TIP_SHA=<actual full SHA, read externally>
COMPLETION_LEVEL=RTL_TRACE_DRIVEN_MOS_OUTPUT_MEASURED_TT   # 仅完成相应测量时使用
EVIDENCE_STATUS=<PASS/FAIL/BLOCKED>
PWM_CURRENT_FEASIBILITY_TT=<PASS/REWORK_REQUIRED/NUMERICAL_NOT_CONVERGED/NOT_VERIFIED>
NEW_RTL_SIMULATIONS=<actual count>
NEW_SPECTRE_LAUNCHES=<actual count, including preflight/help/failures; must be <=52>
NEW_OA_WRITES=0
FROZEN_TRACKED_PATHS_CHANGED=0
PAM_8LEVEL_ANALOG_IMPLEMENTATION=NOT_RUN
FULL_MOS_GRAY_CONTROLLER_IMPLEMENTATION=NOT_RUN
GRAY_LUT_IMPLEMENTATION=NOT_RUN
PHYSICAL_CDC_AND_SKEW=NOT_VERIFIED
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
ARRAY_LAYOUT_DRC_LVS_PEX=NOT_RUN
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW  # 阻塞时改为真实阻塞原因
```

禁止为整洁抹掉未通过的电气结果。本轮结束后，是否改输出级、何时设计 PAM，以及何时把灰阶控制器落实成 MOS/OA，由用户在独立审核之后另行决定。
