# DATA-7C-B-PREP-R2 独立复审：GO（离线准备范围）

日期：2026-10-24（北京时间）。建议接受的固定内容版本：`e51c5320a28bd5043e21d08a0be97e9d5612cd16`。

**REVIEW_RECOMMENDATION=GO。** 上轮唯一阻断项已关闭，旧四组诊断没有回归；本次没有新增阻断项，不要求PREP-R3，也不要求单独DOC轮。

GO的范围是：八档PAM候选文本电路、15例离线激励与测量准备。它不表示八档电流已实测，也不批准任何原生启动、OA写入或合并。

## 1. 固定源与直接核实范围

仓库：https://github.com/LINboss666/microled-ic-ai-lab

Git协议实际回读并fetch：

| ref | full SHA |
|---|---|
| `poc/data-pam-d7c-b-prep-r2` | `e51c5320a28bd5043e21d08a0be97e9d5612cd16` |
| PREP-R1 | `6778535e70b139812265eba490d0a1381a1fae5c` |
| PREP | `dcef9b336f2222d6291d266858270f7448b6bb78` |
| A-R2 | `3e4703f1763223024f442c0826e95055782bca13` |
| main | `23e471cb936b421ee97e1250c3be06edf96f9937` |

在独立worktree和同一SHA的全新git archive副本上复核。网页入口无法读取私有页面，因此本次源码证据来自实际Git对象；执行者的GitHub API回读未由本次复审独立重放。

执行者本机808,824 B的ZIP没有上传，本次不确认该归档字节或其摘要。本报告和配套审核包为审核方另行生成。

R1..本tip实际为：**5修改、47新增、0删除、7 commits**，共2,766个跟踪路径。修改路径恰好是任务书允许的五项；其余2,714条原路径blob+mode完全一致。四个候选DUT、15份deck、三张时序表和所有旧记录均冻结。任务书与审核方原件逐字节相同。

## 2. 阻断项关闭的实证

同一份 `probe_tick_normalisation.py`：

| 观察 | 未改R1 | 本轮R2 |
|---|---:|---:|
| rc / defect_reproduced | 0 / true | 1 / false |
| TR-LONG完整窗T50 | 1µs | 1µs |
| 入口的参考tick | 1µs，错误 | 120ns，符合合同 |
| QLSB | 1.875pC | 0.225pC |
| 多出0.5pC后的误差 | 0.266667LSB，在限内 | 2.222222LSB，越0.5限 |

本次逐字段读取，修补没有靠空返回、全拒收、改波形或改阈值完成。新鲜archive中再次得到同样结果。

审核方另行用手写码位/名义电流、交付deck中的实际使能PWL构造独立合成样点，经真实入口读回全部27个窗口：参考tick与QLSB均匹配指定逐例映射，0处不一致；DC八例拒绝时域tick。10fC的粗细差在120ns参考下为0.044444QLSB，正确越0.01限；改用1µs分母则被拒收。

所有这类样点均为 **SYNTHETIC_NOT_MEASURED**，不作为MOS电流或光学灰阶结果。

## 3. 实际重放与身份检查

| 检查 | 本次结果 |
|---|---|
| 原四族仪器 | 四族逐项false，无仪器错误；worktree和新archive一致 |
| 合同/日程/deck | 各rc=0，15例、143窗口行、300PWL点 |
| 独立deck读盘 | rc=0；15deck、27发光窗、36PAM变化段、54半轨交叉 |
| 合成测量 | rc=0，31/31 HIT |
| 候选离线检查/反例 | rc=0，34/34与65/65 |
| 本轮交接入口 | rc=0 |
| 正式记录的R2语义规则 | 25门，0问题 |
| 正式记录source_identity与实际tip的Git blob逐项核对 | 99/99相同，0失配 |
| 新鲜archive | 新旧仪器、31例重放均符合预期 |
| 已提交R1..tip的diff --check | rc=0 |
| history安全闸 | rc=0；199 commits / 2,767 objects，四类计数均0 |
| provenance | rc=0；495 files / 555 labelled lines / 0 violations |

冻结共享记录CLI确实仅报告三条旧轮次词汇问题：两个旧仪器门名缺失，以及两份旧仪器文件名缺失。R2适配规则检查当前三份仪器和逐字段结果；本次同时独立核对99个实际Git blob，未把共享CLI的rc=1冒称PASS。

完整证据在 `checks/`。本次没有运行会重写报告/发布记录的整轮执行器，也没有运行Spectre、RTL仿真、OA、SSH或读取凭据/模型卡。

## 4. 一项非阻断说明待办

合同Markdown名义电流表最后的µA显示仍少乘了1e6，例如：

```text
当前：1.875e-06 A = 1.875e+09 fA = 1.875e-06 uA
应为：1.875e-06 A = 1.875e+09 fA = 1.875 uA
```

JSON中的安培数、前一列1.875µA、主电流目标和实际测量算法均正确。这是渲染器最后一个占位值的单位换算笔误，不构成本轮电气/算法阻断。下一次正常维护时把 `value` 改为 `value*1e6` 并重渲染即可，**不为此再开PREP返修或DOC轮**。

## 5. 建议收口与下一阶段

建议由用户接受 `e51c532…` 为 **PAM_CANDIDATE_AND_OFFLINE_PREPARATION** 的限定版本。登记可在随后用户授权的新工作分支中完成；本次复审没有登记接受版，没有合并，也不追认其它历史轮次或DATA-7B的59/56超支。

后续可以先执行同一输出通道的八档DC测试：8个DUT + 8个供电/激励preflight + 4次调试余量，建议本轮Spectre总上限20次。配套任务书已经写出准确范围、条件、判据和停止点，但它是**待用户批准的方案**；当前授权仍为0。旧36次草案不会自动生效。

先DC后再决定瞬态，能先确认实际八档值、满量程与输出合规范围。此阶段不做PWM/PAM联合电荷、完整MOS灰阶控制器、LUT、TCON、阵列或版图。

```text
REVIEW_RECOMMENDATION=GO
REVIEW_SCOPE=PAM_CANDIDATE_AND_OFFLINE_PREPARATION_ONLY
TICK_NORMALISATION_BLOCKER=CLOSED
PREVIOUS_F1_TO_F4=CLOSED
NEW_BLOCKING_FINDINGS=0
NONBLOCKING_NOTES=1
PREP_R3_REQUIRED=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
```
