# DATA-7C-B-TR-R1：一次完成的离线证据与检查修补

你看不到用户与ChatGPT的聊天。本任务、配套复审报告、审核仪器和固定Git身份是完整输入。按 GitHub Bridge Review Workflow v1.0 执行：复现→限定修补→同字节复测→普通推送→独立复审。本轮处理证据和规则缺口，不改善MOS电路，不为得到电气PASS重仿真。

## 0. 固定身份、范围与额度

```text
TASK_ID=DATA-7C-B-TR-R1
REPOSITORY=https://github.com/LINboss666/microled-ic-ai-lab
BASE_SHA=398c9e852c16db85cbfa4539e859534e117ff0d2
REVIEWED_CONTENT_SHA=f49ba9d78190f8c3da2adca9dbd4fb3e48d26841
ORIGINAL_TASK_BASE=61621f6e3d887082ecd6a7ecc1c771f8e509a24a
BRANCH=poc/data-pam-d7c-b-tr-r1
MAIN_MUST_REMAIN=23e471cb936b421ee97e1250c3be06edf96f9937
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_ACCESS=0
NEW_SSH_OR_GUEST_CONNECTIONS=0
NEW_PDK_LICENSE_OR_CREDENTIAL_READS=0
NEXT_NATIVE_STAGE_AUTHORISED=NO
MERGE_PERFORMED=NO
ACCEPTANCE_REGISTERED=NO
```

先读 AGENTS.md/README.md 和本复审报告。本任务允许必要的新worktree/分支、离线代码修补、只读本机已保存raw/VCD/日志、数值导出、普通提交/push；不允许任何模拟器启动（含-h、版本、语法检查、动态预检、其它仿真器）、Icarus/vvp、OA、SSH/VM、读取凭据/模型卡/许可证、改密码或网络。原24/4授权不扩展到本修补轮，也不借其余3次。

电路目标仍是八支路单输出PAM最小单元，Data下拉接N、Scan高侧接P。TT/27°C、IREF=15µA、vdd18/VCAS=1.8V、VSS=0、理想输出夹持1.20V。000为最低非零档，只有enable关断才黑。不涉及LED/高侧/阵列RC、LUT、全MOS控制器、TCON、版图、PVT/MC、SOA或光学位数。

## 1. 冻结面与可改路径

以下全部冻结：六母本/四候选DUT、RTL、原TB、18份已执行deck及deck_account、`tests/dd1_d7c_b_tr/contract.json`、旧9例计划、所有BASE已有结果目录/账户/报告/交接/回执/任务书、共享安全规则、旧轮工具及接受登记。先逐blob+mode核对。

只允许修改本轮六个自有脚本：`scripts/dd1_d7c_b_tr_{contract,decks,trace,measure,run,record}.py`；若无须修改某个就保持。不要修改共享解析/积分基础函数。可新增小型 `scripts/dd1_d7c_b_tr_r1_*.py`、`tests/dd1_d7c_b_tr_r1/`、新 `results/evidence/dd1_d7c_b_tr_r1_<run_id>/`、`reports/dd1_d7c_b_tr_review_fix_r1.md`、`reports/agent_handoffs/DATA-7C-B-TR-R1.{md,json}`、本任务原字节副本与本轮授权/限制记录。不要为了新prefix重发布旧记录。

不要再造通用事务平台、SPICE解释器或庞大突变工程。所有更改都必须直接对应下面四组问题；放在一个功能载荷提交中，记录/交接可另提交。中间失败证据保留，不删已发布目录，不覆写旧账本。

## 2. 先复现：九个审核反例

保持 `probe_tr_review_gaps.py` 原字节，记录SHA。对未改BASE提取物运行：

```text
python probe_tr_review_gaps.py <BASE_checkout> --out <new_scratch_before>
```

当前仪器rc=0表示9条缺陷全部复现，正例通过；没有原生启动。逐项读JSON，不把rc=0当修补通过。修后用相同反例判据逐项证明被拒收，并保留合法正例。原仪器的表格正例是旧版“仅表格”输入；升级为强制序列/冻结DC依赖后，该旧输入不再足够，不能强求它继续PASS。保持审核原件不改，另给一个小适配为这三项包侧反例提供本轮完整合法输入与冻结依赖，先证明干净副本通过，再只注入单一错误；不得改动错误内容、判据或用缺文件拒收冒充语义命中。原仪器若遇旧schema而中断，按INSTRUMENT_NOT_APPLICABLE记录，不按rc冒充修闭。

若新入口替代了旧入口，旧入口必须拒收或委派新校验，不可保留旁路。合成VCD由Python写文件，不调用RTL仿真器。

九项是：旧Account实例覆盖；错电流单位；0V的vdd18；倒退时间轴；Hybrid使能整体晚10ns仍接受；黑窗1µA仍SHUTOFF PASS；伪造DC目标且动态PASS；TR-120伪造1000ns分母；五条带进程证据的RTL行仍被机械减1。

## 3. F1：从已有原生序列重建独立证据链

不要重新起Spectre。对本机已保存的9 DUT和9预检raw作只读导出；先验原raw摘要与旧账本/launch_log一致。记录使用的旧run_id、launch_id、deck、源工具身份、旧raw摘要和新导出字节摘要。

至少交付9份DUT的全精度、严格递增原生采样：time、带符号Iout、data_en、pam0/1/2、vdd18、vss、vcas、clamp_node、data_out、共享参考节点。保留原生精度，不重采样、不抽点替代积分；允许无损gzip、分块和去重常量列，需有明确schema/单位、数量和还原说明。time/Iout和实际enable边界须能够无依赖本机的再积分。9预检提供对应原生输入/供电验证与仪表见证的可重算数据。内部26列至少给TR-LONG各档末50ns以及各代表性开启/关断/切码的原生片段；片段不足解释的地方写NOT_VERIFIED，不用均值摘要冒充全量瞬态。

旧raw/log不入库，不复制PDK/厂商路径/license/凭据。新跟踪数值证据仍限32MiB；先用无损压缩与去重复，不能删旧证据或丢测量窗。若确实放不下或某份raw已遗失，列明精确缺口并交PARTIAL，不增加额度、不补造数据。

保存已有两份真实VCD的无损交付形式，先核对旧转换记录的原始摘要，重新用修补后的离线读取器转换并与已执行Hybrid deck的四条PWL比较。无新vvp。VCD不可恢复则联合控制来源状态PARTIAL，不称完整证成。

独立重算器从序列开始积分，而非以窗口Q为输入答案：端点线性插值、跨零分段、full/flat/tail分开、max|I|、双目标settling与收敛。不得import本轮上层measure来证明自己；可用一个短小独立实现，并有手算面积正例。冻结：

```text
reference_tick(TR-200,HYB-200)=200 ns
reference_tick(other7)=120 ns
QLSB=1.875e-6 A * reference_tick
Inom(k)=(k+1)*1.875e-6 A
IDC(k)=已接受DC表1.20V对应码的I_sink_A原精度
Qnom=Inom*T50
Qdc=IDC*T50
error_nominal=(Q-Qnom)/QLSB
error_dynamic=(Q-Qdc)/QLSB
abs(error_dynamic)<=0.5；abs(error_nominal)<=0.5，分别报告
abs(dQ)/QLSB<=0.01
```

冻结DC表路径：`results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv`。包内包含该原字节依赖及摘要；不能只搬已算好的qtarget。37个精确窗口键、码位/实际边界/启动/raw/deck一一核对；三对13个收敛窗必须回连两边实际Q。七种状态逐内容重判，拒缺项/重复/额外/NaN，不能只查名称。

把三个伪造复算反例接到真实交付入口：替换Qdc为实测Q并声称动态PASS；TR-120改1000ns同步误差；给第五条RTL行自己的进程证据。它们必须点名拒收，即使CSV摘要同步刷新也不放过。正确负电气结果仍应成为有效交付，禁止把DYNAMIC/NOMINAL FAIL改写为证据损坏。

## 4. F2：修旧实例覆盖、明确预算与保存每次尝试

修改Account时先在锁内重读实际盘状态并验证其header/唯一顺序id/合法状态/固定上限；旧快照必须拒绝且保留原字节，或以最新状态追加。不能先用内存算id/余额再拿锁覆盖盘。落盘采用临时文件+原子替换，失败保留旧账；新增测试只针对本缺陷和必要失败保护，不开发泛化平台。

用两个顺序初始化的Account对象、上限1，A成功reserve后，旧B必须拒收或在不超限条件下只保留A；文件集合和摘要要核对。再做满额拒启/落盘失败旧账不变两个小反例。所有测试用临时账本，绝不碰旧正式账。

原生/RTL未来每次尝试的输出路径必须带独立launch_id/sim_id，同一case/role重试不覆盖旧raw/log/转换输入；本轮仅用mock验证路径和拒启，不连接guest。原生DUT必须读取本案例已通过的预检证据，默认None不能绕开；其证据绑定相同案例、实际刺激/供电/分析条件与完成时间。修旧入口同样不能逃逸。

旧19行Spectre账+2逃逸保守占额=21/24，余3；22是主账本扣除2后的上限。三者分别列：原任务总上限24、主账本上限22、总占额21。不要写22次已用且余3，也不把全部19预约宣称成19次独立证成的实际启动。T001 UNCERTAIN继续占额。

RTL去重不得硬编码len-1。R001/R002同秒+缺字段本身不是“第一条绝无进程”的证明。只读已有命令转录、逐启动日志/工具记录/摘要，机械关联真正重复的预订与唯一一次实际启动；证据够时计4、5行原样保留。若证据不足，明确 `RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN` 或按无法排除的REQUESTED保守占额，不改旧账、不伪造日志、不自行追认预算。历史证据无法恢复可以作为披露的未解限制交付，不为此反复运行任何仿真。

## 5. F3：Hybrid起点、终点及安全行为都必须核

仍只读已有VCD。普通非黑帧应逐端点检查：

```text
rise(data_en) == 消费首tick的clk正沿t0
fall(data_en) == t0 + M*T
M={time0:0, time1:1, time2:2, time63:64}
```

数字VCD使用其原整数时间单位比较，不添加无来由容差；obs_tick早5ns不能作t0。不得只验宽度。黑帧整64T无导通。PAM每帧保持、四条PWL位序/总2ns沿宽/统一右移1000ns与现存deck一致。

安全帧精确核对原计划fault=t0+2.5T+3ns、保持≥40ns，输出在真实fault沿逻辑关断；撤销后持续tick≥600ns，实际发过bareSTART，期间没有新load/LATCH/授权且保持黑。检查安全输出段不能跨过fault后再以“仅一个段”放行。没有物理CDC或时钟偏斜结论。

使用审核合成VCD的正例与+10ns整段平移反例；后者必须因起点/终点错误具名拒收。再给只延迟关断的安全反例。两份已有真实VCD均重新读回，结果和完整问题列表随包；若实际不满足，写实际FAIL，不改VCD、不重跑控制器。

## 6. F4：导入规则与黑窗关断

`load_raw()/observe()/measure_case()`任意可达入口都先校验：time单位s、严格递增且有限、信号列齐且长度一致、电流单位A/电压单位V（别拿V当A）、实际供电与冻结值一致；data_en/PAM逐点与本例deck的静态/PWL相符，按导出精度给数值容差，禁止0.9一刀切掩盖错误模拟电平；clamp=1.2V且理想探针两端仍按`1e-6+1e-9*abs(clamp)`。VSS在提取及观察必需集并必须实测接近0，不用合同值补。

错误单位、缺失、倒退时间、供电错误等是输入拒收，先拒再写，预置非空输出应逐摘要未变。正确格式下电荷/漏电超限则是有效电气FAIL，应留证据，不和格式拒收混淆。

SHUTOFF同时覆盖34个发光窗的纯off最后100ns与三个black窗的全窗max|I|≤150nA；三个black分别是两个零码64T和HYB-120故障撤销后保持。全黑窗Qtarget=0、无T50；Q正负抵消不能掩盖峰值。用净Q=0但峰值1µA的黑窗反例证明关断状态FAIL。保留nominal与IDC两个settling的实测状态/起点/最后离带/左极限，deadline不移过flat_stop。

## 7. 延迟解释与提交说明一并收口

不用“本次码减前次发光码”挑支路；上个窗之后已关断，所有本次应导通的支路都可能重新开启。按实际参与支路分别观察en/enb/vbias_ch的开启，给最早/最晚及各自身份，不取第一条代替全体。没有原生片段就限制结论，不凭均值排除偏置/译码因素。电流随后达到DC95%可以是时间观察，不能写成器件因果/SOA签核。只读重提取，不调参考/尺寸。

新报告记录正确最终区间：原BASE616..被审tip398为89新增、0改、0删、2935旧路径不变；f49..398只加回执。区分执行方f49包和398包的身份。原任务书增加来源前言、正文全同的事实可保留，不必抹平历史；新修补任务原字节入库。两次逃逸raw已删除、早日志被覆盖的事件如实保留，不能把摘要数字当可恢复原文。

## 8. 交付与停点

新run_id、新发布目录，旧37窗结果/账本/日志记录一字不动。只读重提取如有差异，逐窗列旧值/新值/原因，不把原电气负发现悄悄移走。七个状态分开，并加 `NATIVE_SEQUENCE_REINTEGRATION`、`RTL_INPUT_PROVENANCE`、`BUDGET_ACCOUNTING_STATUS`，只写实际级别。

保存源码→本轮修补自测→同一版字节导出→包外真实重放。包外入口只承诺确实能跑的操作，依赖Git的入口明确NOT_RUN；提供无Git也能由数值序列重积分的入口、冻结依赖和清单。所有会写文件的重放在副本；正式证据前后集合/摘要不变。Git blob来源摘要与LF发布字节绑定；不自指报告或包摘要。

提交安全钩子真实运行。普通push新分支，回读完整SHA和时间，既有main/DC/TR/PREP/RTL分支保持原位。不force、不跳hooks、不GC、不改写历史，不处理凭据或不可达对象事件。审核ZIP的摘要只记包外，不覆盖旧ZIP。交付包包括本任务、复审报告、审核原仪器及其基线/修后JSON、源码依赖、原生数值序列、VCD来源及再转换结果、所有窗口/状态/旧新差异/预算限制。完成后停：

```text
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_ACCESS=0
NEW_GUEST_CONNECTIONS=0
CANDIDATE_DUT_CHANGED=NO
OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```
