<!-- Provenance, added when this task book was filed: the body below is the attached file byte for byte. -->

| field | value |
|---|---|
| attached file | `TASK_DATA7C_B_TR_APPROVED.md`, 18980 bytes, sha256 `5fd564c29dbf953414b786707aca47790b5516d3ff0cb37ebd1a3a3b1ee15f55` |
| accompanying approved task package | `MicroLED_DATA7C_B_TR_Task_APPROVED_20261026.zip`, 15828 bytes, sha256 `c5f9d43b212c0b224181bbcd3a6a30961c148a33ec2c2a6b0f648d0906592ff1` |
| approval | the user replied **YES** on 2026-10-26 (Asia/Shanghai) to the proposal `TASK_DATA7C_B_TR_PENDING_APPROVAL.md`, 18676 bytes, sha256 `502763a7e7527986ac4611d9e7996f2f2dce6d67cebd20c710bd56e52a2b9b76` |
| ceilings | Spectre 24 (9 meter preflights + 9 DUT runs + 6 failure/debug), RTL simulation 4 (2 formal VCDs + 2 failure/debug) |
| baseline | `61621f6e3d887082ecd6a7ecc1c771f8e509a24a`; accepted DC content `b7509c4766a6bbfd0413749d50a5f294192b60fb`; main kept `23e471cb936b421ee97e1250c3be06edf96f9937` |
| new branch | `poc/data-pam-d7c-b-tr` |

---

# DATA-7C-B-TR：PAM瞬态与RTL驱动的PWM/PAM联合电荷（正式授权版）

你看不到用户与ChatGPT的聊天。本任务、配套输入核验记录、固定仓库SHA和配套authorisation.json中的用户批准记录，是完整输入。先读根AGENTS.md/README.md，再按本任务限定范围执行。采用GitHub Bridge Review Workflow v1.0：自包含任务→本地执行→安全推送→云端独立复审→用户决定接受。

## 0. 授权状态和总目标

**用户已于2026年10月26日（Asia/Shanghai）回复“YES”，批准上一份完整任务书及Spectre总上限24次、RTL仿真总上限4次。**这项授权只适用于本轮DATA-7C-B-TR；Qoder收到本正式版与配套授权记录后，按下文完成只读来源核验、离线检查及限定原生测量，不再为同一范围重复等待批准。原待批准版保留，授权来源见包内`authorisation.json`。

```text
TASK_ID=DATA-7C-B-TR
AUTHORISATION_STATUS=USER_APPROVED
APPROVAL_DATE=2026-10-26
APPROVAL_TIMEZONE=Asia/Shanghai
APPROVAL_RESPONSE=YES
CURRENT_GRANTED_SPECTRE_LAUNCHES=24
SPECTRE_TOTAL_LIMIT=24
PLANNED_NATIVE_PREFLIGHTS=9
PLANNED_NATIVE_DUT_RUNS=9
NATIVE_FAILURE_OR_DEBUG_MARGIN=6
CURRENT_GRANTED_RTL_SIMULATIONS=4
RTL_SIMULATION_TOTAL_LIMIT=4
PLANNED_RTL_MAIN_RUNS=2
RTL_FAILURE_OR_DEBUG_MARGIN=2
NATIVE_STAGE_AUTHORISED=DATA-7C-B-TR_ONLY
NEXT_STAGE_AUTHORISED=NO
```

目标是一轮完成：七个已准备的PAM晶体管瞬态例、两组由已接受RTL真实四态VCD驱动的Hybrid联合例、三对已有步长收敛、内部节点解释、正确的电荷与关断评价。**不是再开一轮只交工具的PREP；本轮离线实现和原生测量在本任务内连续完成。**失败的电气发现也要完整交付，不改电路追PASS。

## 1. 固定来源及接受边界

| 对象 | SHA／路径 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 新任务Git基线（含限定接受登记） | `61621f6e3d887082ecd6a7ecc1c771f8e509a24a` |
| 被接受的DC/R1实质内容 | `b7509c4766a6bbfd0413749d50a5f294192b60fb` |
| 接受登记 | `reports/reviews/DATA-7C-B-DC-R1-GO/registration.json` |
| main保持 | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 新分支 | `poc/data-pam-d7c-b-tr` |
| RTL | `rtl/dd1_d7a_gray_ctrl.sv`，基线所携带字节，须与已接受`f68449672774ac9266ba9e4893024e4f3027dd9d`逐字节核对 |
| 原RTL契约 | `reports/dd1_d7a_contract.md` |
| 已接受DC表 | `results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv` |
| 原瞬态准备 | `tests/dd1_d7c_b_prep/{contract.json,schedule.csv,windows.csv,pwl.csv}`及`spectre/dd1_d7c_b_prep/` |

同一个data_out，八条单位支路，pam=000对应最低非零电流；只有DATA_EN=0才全关。Data接LED N侧、Scan高侧接P侧，不改极性。当前夹持是理想测试条件，不是实际LED、扫描高侧或电极RC。

四候选DUT、六份已剥端口方向标注的派生母本、原15deck、旧合同／时序表、RTL、旧记录／报告／交接／账本全部冻结。6母本见`spectre/dd1_d7c_b_dc/masters/`；来源为原四DUT加`dd1_d6_inv18.scs`、`dd1_d6_bias_core.scs`。几何、参考结构及体端不动。

本次登记只新增三份`reports/reviews/DATA-7C-B-DC-R1-GO/`文件，其他内容未动；不要为了适配新目录去重发布R1或修改其历史NEW_PREFIXES。新任务自己记录当前base即可。

## 2. 本轮允许操作与禁止操作

本轮已批准：新worktree、新分支；本机编译／Icarus四态RTL仿真最多4次；通过已有SSH桥在guest本项目新目录运行Spectre最多24次；只读核验必要模型/环境身份，取回本轮原生输出；安全提交和普通push新分支。

Guest新写入仅限`/root/microled_ai_project/cadence_work/dd1_d7c_b_tr/<run_id>/`；使用现有模型与许可证配置，不能修改它们。已有桥运行时加载凭据可以使用，禁止打印、cat/grep回显、命令行嵌入或入库敏感值；用了运行时加载就如实记，不称“凭据读取0”。

始终禁止：OA读写／新画原理图、TCON／阵列／版图／DRC/LVS/PEX、换DUT/W/L/体端、改PDK/许可/密码、换bridge工具链、VM电源/快照/网络配置、force/GC/rewrite/跳hooks、merge、推main。通道不可用只读定位后停，不自动dhclient或重启服务。不要用完整bridge测试间接运行OA。

## 3. 一次完成的小型实现；不再写一套通用平台

新增本轮runner/measure/trace薄封装。复用：

- `dd1_d7b_measure.py`的积分、线性插值、阈值与稳定性基础函数。
- `dd1_d7b_trace.py`的真实VCD读取、边沿转PWL与t0经验；其旧scope／Pure专用约束不能未经核验硬套Hybrid。
- `dd1_d7c_b_prep_measure.py`的五种窗口、带符号面积、逐窗尾段与reference_tick区分。
- DC-R1严格必需信号、单位、输入条件和Git身份的既有实现思路；不能把静态提取器直接当瞬态提取器。

旧模块冻结；本轮小适配只放新前缀文件。若复用的上层函数把settling目标写死为名义电流，保留该名义结果，另用相同基础函数算IDC目标结果，不能把新参考偷换进旧列。

只做直接支持本次测量的离线正反例：积分端点与过零、缺信号／错单位／NaN／乱时序、VCD X/Z、错误tick、尾段配错、未授权写保护、全额拒启、字节身份。先通过这些小检查和端到端合成正例，再在同一任务内原生运行；不要新建通用SPICE解释器、事务平台或庞大突变工程。

## 4. 统一电气环境与两条待办

TT、27°C、vdd18=1.8 V、VCAS=1.8 V、显式VSS=0 V、外部IREF=15 µA注入冻结二极管参考，固定data_out夹持1.20 V。源与探针顺序沿用`Ip_branch (clamp_node data_out) iprobe`，I_sink=Ip_branch，不翻号不取abs。模型路径由既有环境变量提供，不把模型卡/厂商路径/license值入库。

本轮新提取及观察清单都必须含VSS。理想iprobe两端检查改为：

```python
abs(data_out_V - clamp_node_V) <= 1e-6 + 1e-9 * abs(clamp_node_V)
```

这是数值一致性容差，不是器件压降指标。先用本机导出精度证明该容差可读；不按浮点绝对相等，也不因假想容差问题启动额外仿真。本机旧304行可以只读重判，最大差0 V。原DC已接受20 mV值不改写；仅在新适配中落实。

原生派生deck沿用已跑通的`type=pwl wave=[...]`、具名`tran_case tran ...`和`simopt options temp=27`；运行载荷显式导出QODER_NETLIST_DIR，不改旧env文件。原生自适应时间保留浮点精度，严格递增、有限、单位明确；不要把原生时间强制取整到ps或按等间隔假设积分。显示量化误差与算法容差分列。

DUT每例必需保存：time、Ip_branch实际电流名、data_en、pam0/1/2、vdd18、vss、vcas、iref_in、clamp_node、data_out；以及8个`Xdut.en0..7`、8个enb、8个`Xdut.Xu0..7.vbias_ch`、代表性`Xu0.node_m`和`Xu4.node_m`。沿用此前DC确实收到的层级名字。可按唯一、无歧义的实际PSF名称映射；名字不存在就点名，不能补合同值、伪称观察通过或改变DUT端口来导出。

内部节点缺失时允许保留已取得的输出测量，但完整内部观察状态必须PARTIAL，不能给完整阶段PASS；不为此重画或改原理图。每次原生前只读检查save与模型命名，首次DUT就同时检查内部列，避免后面八例全跑完才发现没观察。

## 5. 九个原生DUT；每个各有一次原生仪表预检

### 5.1 七个已准备的瞬态deck

只用本轮新运行副本。冻结原源、原波形／窗口／分析条件不改；include改指向六份已接受剥离母本；只加本轮必需save、标识及来源。不许默改阶跃速度来追电气PASS。

| 案例 | 目的 | maxstep |
|---|---|---:|
| TR-LONG | 000→111八个1 µs发光窗、逐档稳定与尾段 | 2 ns |
| TR-120 | 最低非零档120 ns脉冲 | 2 ns |
| TR-200 | 最低非零档200 ns脉冲 | 2 ns |
| TR-OFFCODE | 011→100→000→111，仅关断区切码 | 2 ns |
| RS-FULL | TR-LONG逐窗收敛对照 | 0.1 ns |
| RS-LOW | TR-120收敛对照 | 0.1 ns |
| RS-SWITCH | TR-OFFCODE收敛对照 | 0.1 ns |

三对除maxstep外必须物理输入、测量窗和参考一致。TR-200没有专门细步对，不得声称所有案例都独立做过细步收敛。原PREP七例合计27个发光窗；每窗的full/flat/tail/pure-off/leak-last100都从交付PWL独立回读确认，不由生成器自证。

### 5.2 两个由已接受RTL生成的Hybrid联合案例

新增`HYB-120`与`HYB-200`，每个只仿真一份单通道RTL，tick为同100MHz时钟域enable，周期分别120/200 ns。不是新增RTL功能，不改控制器。每份VCD顺序包含：

| 帧 | cfg_hyb_time | cfg_hyb_pam | 预期导通区间M |
|---|---:|---:|---:|
| B0 | 0 | 000 | 0 |
| L1 | 1 | 000 | 1 |
| M2 | 2 | 011 | 2 |
| F63 | 63 | 111 | **64**，不是63 |

HYB-120额外包含一个安全窗A：time63/pam111，运行到t0+2.5T+3 ns时异步fault拉高（额外3 ns确保避开参考时钟沿），保持至少40 ns；撤销后在blank内仅发START，不load/LATCH，继续tick并证明至少600 ns保持黑；不做新的重新授权恢复窗。HYB-200不增加该安全窗。

每帧完整走原协议：reset后以mode00/blank1/system_en0起步；释放reset，安全相位将mode改01并保持至少2个参考周期；允许system_en；cfg_valid先低再高，完成新load，至少隔一个采样沿再LATCH，再隔采样沿START；blank解除后才消费第一个tick。tick在负沿提前置位，正沿消费；配置/锁存/START不得挤同一沿。每帧等win_state=DONE（黑码同样走完64区间），保持tick至少2次，再准备下一帧。每帧之间在DATA_EN=0下给至少500 ns准备/尾段，代码变化应结束于下次DATA_EN上升沿至少100 ns之前。

`clk`100 MHz、所有输入和输出、win_state、cfg_version、proto_err、obs_tick全部记四态VCD。t0取消费tick的参考clk正沿，不用提前5ns的obs_tick当t0。独立期望由输入code/实测tick生成；不是从DUT target算术抄期望。普通帧data_en在[t0,t0+M*T)导通、pam全帧及尾段保持，帧结束65个边界事件；零码全黑，不把PAM000当黑码。任何X/Z或非法协议均先拒收，不喂模拟。

用真实VCD的data_en、pam[2:0]转为0–1.8 V PWL，四条信号全部转换；每沿总宽**2 ns**、50%点对齐VCD原沿，保持成对hold/ramp点，不跨发光窗缓慢插值。整份波形统一右移1000 ns，不能只移enable不移PAM。自解析PWL复核所有原沿、位序、2ns斜率及初始值；边沿重叠直接拒收。两份原生Hybrid deck maxstep均0.1 ns。模拟以PWL驱动冻结PAM MOS，**不是MOS实现的RTL控制器，也不是实时混合仿真或物理CDC验证**。

每组4个常规帧，加HYB-120安全帧，共9个逻辑窗口（其中两个零码没有发光沿，单列黑窗；不套“找不到沿=失败”的发光窗函数）。安全窗按实际fault关闭沿测量，不把计划的64T当实际导通时间。

## 6. 原生预检与固定预算

9个DUT各配1次动态仪表预检：保留同一供电、PWL输入、time范围和maxstep，用80kΩ输出负载及50kΩ参考负载替代DUT，删除不存在的DUT层级save。1.20V夹持应恒定+15µA、参考节点0.75V；同时从原生输出回读输入PWL的电平/边沿/位序。理想电阻预检不会随DATA_EN关断，不能把它当DUT关断或阶梯结果。

**24 = 9 preflight + 9 DUT + 6调试／故障／帮助／语法余量**；RTL仿真总额4 = 两份正式VCD+最多两次失败/调试vvp。iverilog编译不是RTL仿真，但命令与失败仍记录；所有实际vvp启动含失败都占4。

Spectre包括-h／版本／语法探针／失败／崩溃／中断／runner内子调用，全部占额。不借DATA-7B59/56、不借DC余4、不把PREP36草案视为授权，不退款。旧账本不修改。本轮专用追加账本在每次进程前持久REQUESTED；一个执行器串行跑，锁内重读实际盘状态，防过期实例覆盖；恢复保留不确定请求占额，文件集合/摘要失败保留痕迹。

建议顺序：TR-LONG预检+DUT（2启动）确认列与符号→TR-120→TR-200→TR-OFFCODE→三个RS→HYB-120/200。每个DUT须本例预检已过才执行；不得只跑最亮档就省中间档。电气未达标保留FAIL继续完成已批准测量矩阵；基础供电/探针/刺激错误、缺模型、必需输出无法取得、剩余额度不足以完成必需剩余例时停PARTIAL。每个实质问题最多3次修补，不自动续额，不反复小额请求。

## 7. 统一测量与两种电荷误差（本任务已冻结）

从已接受DC表1.20 V点逐码读取IDC(k)，不抄四舍五入显示列；同时报告名义Inom=(k+1)×1.875µA。参考tick由案例固定：TR-200/HYB-200=200ns，其余7例=120ns；RS与其母例一致。

```text
QLSB_nominal = 1.875e-6 A × Ttick
120ns -> 2.25e-13 C；200ns -> 3.75e-13 C
Qtarget_nominal = Inom(k) × T50
Qtarget_dc      = IDC(k)  × T50
error_nominal_LSB = (Qmeas-Qtarget_nominal)/QLSB_nominal
error_dynamic_LSB = (Qmeas-Qtarget_dc)/QLSB_nominal
```

T50只取实际enable0.9V交叉间隔（安全窗取中止后的实际下降沿）；QLSB禁止使用窗长、该窗实测Q、瞬态测得平均电流，或改成代码自身电流×窗长。保持nominal分母，不用I111/8替换它。

**名义误差与动态误差两列同时保留**。DC已存在+2.55%整体偏差，长／满亮窗的名义误差可能明显超过0.5LSB，这是实际结果，不能藏掉。本任务动态保真指标冻结为`abs(error_dynamic_LSB)<=0.5`；名义误差同样按0.5给独立状态，但不把“动态通过”冒充未校准名义灰阶通过。原PREP合同保持PROPOSED原字节，新任务的合同写清该决定及来源。

每窗输出：实际rise/fall50、T50、full和flat的带符号Q、Qpos、signed Qneg、|Qneg|、电流峰值及时间、flat时间加权平均；tail单独积分，禁止把尾电荷并回主窗或用正负抵消证明关断。主结果不能由重采样或抽点近似替代原生样本积分；端点插值、过零拆分使用已接受基础函数。

settling同时给名义目标与IDC目标的±5%/至少10ns结果，deadline固定为本窗flat_stop（下降斜坡开始），报告起点和左极限、最后一次离带；短窗未稳定如实NOT_SETTLED_WITHIN_PULSE，不延后deadline。尾段最后100ns的max|I_sink|<=0.15µA；只在纯off内测，不夹入下一上升沿。黑窗无发光沿：按整64T窗口测Q与max|I|，用0为Qtarget、同固定QLSB给电荷状态，不硬造T50；故障后无新授权的600ns也单列黑窗。

三对收敛逐窗报告绝对dQ(C/fC)及abs(dQ)/QLSB<=0.01。对照上下文含case映射、码位、刺激摘要、测量窗、阈值、符号、DC参考身份、reference_tick和QLSB；只有maxstep允许不同。收敛不证明波形本身满足电气要求；缺上下文拒收，不能None==None当一致。

分开发布：EXECUTION_COMPLETENESS、EVIDENCE_INTEGRITY、DYNAMIC_CHARGE_STATUS、NOMINAL_CHARGE_STATUS、SETTLING_STATUS、SHUTOFF_STATUS、CONVERGENCE_STATUS。不得用一个总体PASS吞掉负发现；电气FAIL仍可完成有效测量交付。

## 8. 内部节点解释必须对应实测

TR-LONG每档给flat末端不少于50ns的时间加权观察：8个en/enb逻辑、8个vbias_ch、共享iref_in、代表性node_m；按应导通支路数k+1核对，未选支路局部偏置与选中支路区分。切档／关断给内部节点与输出电流叠图，解释延迟来自译码、偏置充放电或电流建立的哪一段；证据不足就写未能归因，不因整体+2.55%先认定参考支路有错。

不预设偏置节点必须等于某个手算电压，不以经验数字伪造MOS工作区结论；若原生没有器件OP参数，仅用已保存节点分析限制，不能凭节点名宣称SOA或饱和签核。此轮不调Iref/W/L、不扩0.3 V扫描、不添LED/高侧/电极RC。

## 9. 文件范围、证据与完整交付

新增：`scripts/dd1_d7c_b_tr_*.py`、`tests/dd1_d7c_b_tr/`（含新TB）、`spectre/dd1_d7c_b_tr/`（运行副本）、全新`results/evidence/dd1_d7c_b_tr_<run_id>/`、`reports/tasks/DATA-7C-B-TR.md`、本轮合同／报告／MD+JSON交接。**现有跟踪路径0修改、0删除**；两个待办在新适配里落实，旧DC-R1的源身份不漂移。

报告必须可以对照本任务独立理解，不依赖聊天或未上传截图。持久化checkpoint和两份账本；旧数据、旧已发布目录和中间失败产物不先删再重做，新run_id新staging。每个宣称都有真实命令／输出／数据，未执行NOT_RUN，不将合成自测装成电气结果。

原始raw/log本机保留，不含PDK/模型卡/license/凭据/厂商绝对路径的证据才可入库。供独立重算的本轮VCD、time/Iout/enable/PAM的原生序列可无损gzip（注明精度与身份）；内部节点可交付关键窗样本、全raw摘要与本机路径标识，但内部观察覆盖缺口要写清。32MiB新跟踪字节上限，先用无损压缩与去重复元数据控制，不能删旧证据或丢测量窗腾空间，不把抽点图当全量积分依据。

源码提交后再跑原生，记各运行使用的源码／deck／输入／raw摘要；修工具后重提取已保存raw不花额度但须新导出身份。最终所有CSV逐行语义核验，源和图摘要从Git blob取，LF规范化后再发布；不散列会再渲染的自己，不把回执SHA写成接受内容SHA。

安全hook真实运行，新分支普通push后回读完整SHA、UTC和rc；main、旧DC/RTL/各PREP分支保持原位。审核包包含任务与用户批准记录、新合同、9例计划、RTL/VCD-PWL核对、测量源码及依赖、原生序列/统计/图/账本/复用来源/未完成项。无.git解压环境只承诺实际可运行入口；Git绑定入口如实NOT_RUN，提供真正的独立数值重算。PACKAGE_README不占仓库README路径；ZIP摘要包外；包外重放写在副本，逐摘要确认正式证据未改。

交付后停独立复审，不登记接受版、不自给GO、不merge、不继续LUT/全MOS控制器/阵列/版图。即使所有POC指标通过，也不声称光学9bit、物理CDC/skew、SOA或可流片。

```text
COMPLETION_LEVEL=RTL_TRACE_DRIVEN_PAM_TRANSIENT_MEASURED_TT_or_ACTUAL_LOWER_LEVEL
NEW_SPECTRE_LAUNCHES=<all_actual>/24
NEW_RTL_SIMULATIONS=<all_actual_vvp>/4
NEW_OA_WRITES=0
CANDIDATE_DUT_CHANGED=NO
OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO
DYNAMIC_CHARGE_STATUS=<PASS_FAIL_PARTIAL>
NOMINAL_CHARGE_STATUS=<PASS_FAIL_PARTIAL>
SETTLING_STATUS=<actual>
SHUTOFF_STATUS=<actual>
CONVERGENCE_STATUS=<actual>
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
PHYSICAL_CDC_AND_SKEW=NOT_VERIFIED
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
