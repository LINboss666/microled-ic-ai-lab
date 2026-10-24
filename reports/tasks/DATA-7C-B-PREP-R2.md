# DATA-7C-B-PREP-R2：只修瞬态电荷参考tick

You have NO access to the user–ChatGPT conversation. Your complete sources are this task brief, its accompanying independent-review package, and the named repository at the pinned commit. Passing offline checks does not authorise native execution.

## 1. 单一目标与固定来源

- 仓库：https://github.com/LINboss666/microled-ic-ai-lab
- 本轮基线R1：`6778535e70b139812265eba490d0a1381a1fae5c`
- 原PREP P：`dcef9b336f2222d6291d266858270f7448b6bb78`
- R2：`3e4703f1763223024f442c0826e95055782bca13`
- main：`23e471cb936b421ee97e1250c3be06edf96f9937`
- 新分支建议：`poc/data-pam-d7c-b-prep-r2`

旧四族诊断已经由独立审核逐项确认关闭，15份deck和25例合成回归通过。**本轮只修T50误作Ttick这一项，不重做电路、PWL、窗口和历史工具。** DC激励准备的离线结果保留；本任务不等于八例DC原生授权。

```text
NEW_SPECTRE_LAUNCH_LIMIT=0
NEW_RTL_SIMULATION_LIMIT=0
NEW_OA_WRITE_LIMIT=0
SSH_VM_PDK_MODEL_CREDENTIAL_ACCESS_AUTHORISED=NO
NATIVE_PREFLIGHT_AUTHORISED=NO
ACCEPTANCE_REGISTRATION_AUTHORISED=NO
MERGE_OR_MAIN_PUSH_AUTHORISED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
```

0包括帮助、语法试跑、其它仿真器及旧仿真重跑。不读凭据/PDK/模型卡/许可证，不连guest，不force、不跳hooks、不GC、不改历史。合同仍为PROPOSED_FOR_REVIEW，36次仍只是草案。

## 2. 先复现，不修改审核仪器

读根AGENTS.md/README.md、本包复核报告、R1任务书、PREP测量/合同/合成脚本及本轮合同和日程。新建worktree，自固定SHA开分支；先回读远端，旧分支和main不动。

在未修改R1的archive副本运行：

```text
python reviewer/probe_tick_normalisation.py --root <R1副本> --out <新JSON>
```

预期rc=0、defect_reproduced=true：1µs窗中+0.5pC，被真实入口按0.266667LSB判在限内，而合同120/200ns单位应给2.222222/1.333333LSB。读取具体字段，不把rc=0写成验收PASS。

原 `probe_prep_gaps.py` 保留原字节，用于证明旧四族没有回归；无需重建T/H历史审核或重新执行所有旧发布器。每个实质问题最多三次修补尝试，然后带真实失败STOP。

## 3. 显式冻结本轮待审的参考单位映射

在本轮合同唯一来源里新增逐例参考tick，保持原名义电流1.875µA、0.5LSB误差限、0.01QLSB收敛限。

| case_id | 本轮POC参考Ttick | QLSB=1.875µA×Ttick |
|---|---:|---:|
| TR-120、RS-LOW | 120ns | 0.225pC |
| TR-200 | 200ns | 0.375pC |
| TR-LONG、RS-FULL | 120ns | 0.225pC |
| TR-OFFCODE、RS-SWITCH | 120ns | 0.225pC |
| DC八例 | 不适用 | 不计算时域QLSB |

这是为消除当前歧义而提出的POC测量参考，不是TCON或显示帧时序已经实现，也不授予原生权限。保留contract_state=PROPOSED_FOR_REVIEW。

可新增 `rules.charge_error.reference_tick_s_by_case`。7个瞬态/细化case必须完整、唯一、有限且大于0；伙伴共享参考tick。保留合同原有120/200ns名义单位列表。未知/缺失case应具名拒收，不按当前窗口长度回退猜测。

映射是测量元数据，不得修改15份deck、波形/窗口CSV或1050ns偏移。1000ns长窗、300ns换码平台可以包含多个参考tick；不能据此把Ttick改成T50。

## 4. 修改接入，公式分清两个时间

主入口改为等价于：

```python
t50_s = (fall50_ps - rise50_ps) * S_PER_PS
tick_s = reference_tick_for_case(row['case_id'], contract_data)
charge_errors(q_full, nominal_A, t50_s, idc_A, tick_s, evidence_class)
```

- `Qexpected_nominal=Inominal(k)*T50`；`Qexpected_dc=IDC(k)*T50`，后者没有实测点时仍NOT_RUN。
- `QLSB=Iunit_nominal*Ttick`，与平台长短和PAM档位无关。
- 返回本例reference_tick_s、QLSB、T50及映射来源，使审核能直接看出两个时间没有混用。
- tick为0、负数、非有限数或缺失时，在除法前具名拒收。沿用项目兼容的有限数检查，不引入与现有Python环境不兼容的依赖。
- 收敛也使用相同的逐例参考tick。为配对上下文增加明确参考tick并检查其与函数参数一致，不能两边一起传入窗口时长就把单位漂移隐藏掉。已有完整上下文测试可补上新增字段，原来的手算值/阈值不改。

禁止把QLSB改成该档电流×T50、实测Q、长窗本身，禁止改变激励或放宽阈值维持旧结论。修正后某些合成窗口出现OUTSIDE_PROPOSED_LIMIT是允许的，计算真实即可；它们不是实际MOS电气失败，也不要求所有合成波形在电气阈值内。

## 5. 只增加必要的接入正反例

使用真实 `measure_case()`，样本仍全部SYNTHETIC_NOT_MEASURED：

1. 保留审核+0.5pC反例：TR-LONG码111、1µs，真实入口应给QLSB0.225pC、误差约+2.222222LSB、OUTSIDE_PROPOSED_LIMIT。
2. TR-120与TR-200分别返回0.225/0.375pC；TR-LONG八个码共用0.225pC，不能随档位改变。
3. 修改临时合成输入的窗口宽度而保持本例reference tick不变时，期望电荷按T50改变，QLSB不变。配对元数据漂移仍须拒收；不要把这个正交算术测试当成允许改交付deck。
4. 对全部27个发光窗读回QLSB，逐例匹配上表，原25例回归不退化。
5. 同一个10fC的coarse/fine差值，在120ns参考下是0.044444QLSB，大于0.01；不能按1µs分母变成0.005333后放过。完整相同参考是正例；缺参考、参考不一致、0/负/NaN/Inf必须点名拒收。

审核新仪器保持原字节，修后预期rc=1、defect_reproduced=false。必须同时核对实际参考tick/QLSB和真实入口反例；全拒收、空返回或不再测该窗都不算修好。旧四族仪器仍应逐项为false。

## 6. 附带说明更正，不另开DOC轮

- 合同渲染器把比例0.05显示为±5%，不是±0.05%；数值容差仍0.05，不改变判据。
- 电流单位栏显式标注µA、A、fA，不把不同单位的裸数字写成同单位等式。
- 在新修补报告中勘误R1报告“继承的已接受R2”：本轮没有R2接受登记授权。旧报告/交接和旧记录保留原字节。
- 最终Git范围重新按实际两端SHA计算。基线P..R1实际为26改/23增/0删/5提交，早期7新增/3提交数字单列其时刻，不冒充最终tip。

## 7. 严格限定路径和交付

允许修改仅限：

```text
scripts/dd1_d7c_b_prep_measure.py
scripts/dd1_d7c_b_prep_contract.py
scripts/dd1_d7c_b_prep_cases.py
tests/dd1_d7c_b_prep/contract.json
reports/dd1_d7c_b_prep_contract.md
```

允许新增本任务书逐字节副本、`reports/dd1_d7c_b_prep_review_fix_r2.md`、`reports/agent_handoffs/DATA-7C-B-PREP-R2.{md,json}`、少量 `dd1_d7c_b_prep_r2_` 前缀验证和全新证据目录。

冻结四个候选DUT、15份deck、日程/PWL/窗口CSV、全部旧证据、旧任务/报告/交接、共享测量和安全工具。不要为了旧轮次CLI不认识新门名再创建一套记录框架。新记录有完整命令、逐命令rc、反例JSON、源码身份和冻结比较，足以让审核重放；旧记录只在其固定历史SHA下复核，不改旧记录去匹配新源码。

验收顺序：未改R1反例 → 限定修补 → 新旧正反例 → 合同/日程/deck/独立读盘及25例回归 → 冻结比较与已提交区间diff --check → 新鲜archive提取物重放。

只运行受改动影响的离线检查，不重做无关T/H历史、原生环境探测或发布系统。所有新输出使用新run_id，原有失败记录不删不覆。

普通push独立分支，安全钩子真实运行；再回读同一对象，完整SHA/UTC/rc分列。main与旧分支不动。审核包由最终Git blob构建，含本任务、修补报告、必要源/输入/只读依赖、两份原审核仪器和结果；仓库外实际重放，ZIP摘要只写包外，报告不自哈希。

```text
TASK_ID=DATA-7C-B-PREP-R2
BASE_SHA=6778535e70b139812265eba490d0a1381a1fae5c
REPAIR_SCOPE=TRANSIENT_REFERENCE_TICK_AND_UNIT_RENDERING_ONLY
PREVIOUS_F1_TO_F4_DIAGNOSTICS=REMAIN_CLOSED
CANDIDATE_DUT_NETLISTS_CHANGED=NO
DECK_PWL_AND_WINDOWS_CHANGED=NO
CONTRACT_STATE=PROPOSED_FOR_REVIEW
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
PWM_PAM_CURRENT_INTEGRATION=NOT_RUN
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

完成立即停止，不自给GO，不运行八例DC、不把36次草案变为授权。DATA-7B历史59/56、凭据事件与旧待办继续保留，不在本轮擅自处置。
