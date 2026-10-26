# DATA-7C-B-DC-R1 独立复审：限定 GO

日期：2026-10-26（北京时间）。固定审核对象：`b7509c4766a6bbfd0413749d50a5f294192b60fb`，基线：`337563fc22699e480bf7fc82890750c126a50654`。

## 结论与建议接受的范围

**REVIEW_RECOMMENDATION=GO（限定）**。原复审F1–F4均关闭，无新增阻断项，不要求DATA-7C-B-DC-R2或独立DOC返修轮。建议用户将此tip登记为“八档单输出PAM的TT直流结果及配套离线提取／判定／身份修补”的限定接受版本。

此结论不表示云端从原始PSF独立重提取，不批准新原生启动，不批准瞬态或合并main。用户决定是否登记；复审方未更改任何Git分支、未推送或登记接受记录。

```text
REVIEWED_TIP=b7509c4766a6bbfd0413749d50a5f294192b60fb
F1_SIGNED_BAND=CLOSED
F2_REQUIRED_NATIVE_SIGNALS=CLOSED
F3_COMPLETE_MATRIX_GATE=CLOSED
F4_COMMITTED_IDENTITY=CLOSED
NEW_BLOCKING_FINDINGS=0
RECOMMENDATION=LIMITED_GO
COMPLETION_LEVEL=NATIVE_PAM_DC_TT_MEASURED
NEW_NATIVE_LAUNCHES_BY_REVIEWER=0
NEW_RTL_SIMULATIONS_BY_REVIEWER=0
NEW_OA_WRITES_BY_REVIEWER=0
NEW_GUEST_OR_SSH_ACTIONS_BY_REVIEWER=0
ACCEPTANCE_REGISTERED_BY_REVIEWER=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```

## 1. 实际读取的来源与限度

网页访问私有仓库失败后，实际用Git协议取得完整SHA，独立detached检出读取源码和证据，并在Linux重放。远端Git回读：DC-R1=b7509c4…，DC=337563f…，main=23e471c…；GitHub API双路回读属于执行方声明，本轮未重复API通道。

`.raw/.log`按任务未入库。执行方本机“16份原生答案重提取、零字段差异”的记录及其摘要已读取，但云端不能从摘要验证未提供的原始波形。独立确认的是提交数值、严格提取／判定路径的合成正反例、冻结范围、字节身份、账本与来源映射。模型卡／guest会话／实际总启动量不在本次云端直接可观察面。

用户本机ZIP（2,364,298 B、b4a8a4f5…、656成员）未上传；本报告不认证其精确字节或包外27套件。下附审查包由本审核方新建，不能与执行方原ZIP混称。

## 2. 原仪器复现与修后闭合

使用上轮复审仪器原字节，SHA-256：`d48448b1880c7d011a660e72f8fe202ddd63b251ccc2b16dc037b4bc03aa9e25`。仓库交付的仪器副本与审核方原件完全一致。

| 对象 | rc | 逐字段结果 |
|---|---:|---|
| 未改BASE | 0 | 七项defect_reproduced均true；完整必需信号正例true |
| R1新正式记录 | 1 | 七项均false、reproduced_count=0；完整正例仍true；四种缺列各自具名拒收 |

rc=0在该仪器中表示发现旧缺陷；rc=1表示不再复现。判决来自JSON字段，不单看退出码。

- **F1**：`band_of()`保留符号，用`abs(i-target)`；反向0.60 V点退出区间，邻点与主点评价区分正确；非有限点拒收。
- **F2**：实际`extract()`强制vss等必需信号存在、声明单位正确、全列有限，逐点检查静态电平与码位，不用合同或case名补实测值。条件来源区分了deck与原生观察。
- **F3**：完整`judge()`及公开判定入口先走152点矩阵门；`main_point_arithmetic()`无verdict字段，不能单独宣告阶段PASS。原62项自测与8点反例已独立重放。
- **F4**：新source_identity的195条均逐条与当前tip的Git blob核对，路径唯一，字节数和摘要零差异。两张图的旧CRLF摘要由新记录明确接替，旧字节保留。

## 3. 电气与数据来源复算

独立Decimal脚本23项核算全部通过，期望计算未调用DUT自己的算术。范围包括152 DUT行、152预检行、单位/有限性/符号/实际条件列、key全集、原始分表与合并表一致、deck/raw摘要到账本配对、19点仪表负载见证、主点评价与有符号区间，以及195条Git身份。

| 项 | 独立结果 |
|---|---|
| I111@1.20 V | 15.38270557 µA，+2.55137047%，在14.25–15.75 µA内 |
| Iunit_ref | 1.92283819625 µA |
| 八码 | 1.922839108、3.845677157、5.768515211、7.691353271、9.614191336、11.537029410、13.459867480、15.382705570 µA |
| 单调／比例 | 严格单调；最大比例残差约4.74168862×10⁻⁷单位，小于0.25 |
| 残差单位 | 9.1175×10⁻¹³ A = 9.1175×10⁻⁷ µA，旧1000倍显示误差已更正 |
| 输出夹持 | 当前304行data_out与clamp显示值最大差0 V |
| 已测区间 | 各码0.60–1.50 V、19点；最大相对变化约0.198%，满足±5% |
| 来源映射 | 16条唯一来源映射，304行全部唯一配到账本 |
| 原数据 | 新记录的152+152行、16个分表和16行账本与旧记录逐字节相同 |

不将这些确定性TT模型的比例精度扩展为失配、PVT、光学位数或量产精度。不将0.60 V外推为恒流极限。PAM000是最低非零档，未验证关断瞬态。

## 4. 实际重放与冻结面

`checks/commands.json`中的19条离线命令，其rc均等于预期，包括：基线／修后原仪器、62项自测、母本、plan、账本、matrix check、公开judge、verify-committed、合同、日程、15deck、读盘、31合成、34候选门、65反例、history、provenance、本轮diff检查。

另外只读导入`handoff_check()`返回空问题列表；无raw的`observe()`在临时目录中返回rc=3、NOT_RUN，8例均NOT_OBSERVED。未运行会重发布证据的record主流程。原正式证据未被写入。

BASE→tip只修改三个允许DC脚本；新增51路径、删除0；其他2878个既有路径blob+mode保持不变。原两张SVG不改画、旧记录不覆写。`git diff --check BASE..tip`=0；旧e51..BASE的rc=2历史更正保留，不为清零改历史证据。

安全检查：history实际217 commits／2933 objects、四类计数全0；provenance为524文件／559标注行／0违规。它们不代表历史凭据回显事件已解除。

复审方先用195条身份所列文件构造无Git目录时，缺少未列入身份表的导入依赖`dd1_d7b_trace`，该次matrix检查rc=1；这是审核方取材范围不完整，不是执行方ZIP缺件结论。随后改用完整`git archive tip`到无.git目录重放matrix check并通过。初次失败输出保留在`fresh_matrix.txt`，正确重放输出见`fresh_full_archive_matrix.txt`。独立核算脚本适配时也修正了遗留的131唯一行数断言为195，未改变源数据或接受判据。

## 5. 对执行方三个问题的裁定

### （1）vss与输出跟随夹持

**vss应与同级供电并列为必需观察。**当前主提取器已经如此执行，所以F2关闭。`matrix.py::observe()`自身的REQUIRED_SIGNALS还没列vss；这是两个观察清单未完全对齐的非阻断待办，下一正常维护／瞬态阶段一起对齐即可，不开R2。

**不采用浮点“逐点绝对相等”。**理想iprobe在DC下两端应同电位，应采用与数值精度相符的小容差。当前20 mV护栏偏宽，但当前提交点的差值均为0，所以没有影响此次结果，不为它重跑或返修。建议下一阶段用例如`abs(data_out-clamp)<=1e-6 V + 1e-9*abs(clamp)`的明确一致性检查，并用真实导出精度验证；这不是电路的电压精度指标，不能拿20 mV当作正常探针压降。

### （2）main_point_arithmetic与validate_dc_matrix的分工

**满足本轮要求。**前者只给八主点算术，没有阶段verdict；后者约束完整矩阵，完整PASS入口先验证再判定。后续对提取后的表再做更强的条件／来源审计时，应明确它不是原始PSF真实性证明；当前来源由冻结输入、提取器和身份映射共同支撑。

### （3）旧SVG是否需要在旧目录加便条

**“旧记录保留＋新记录点名＋CRLF机械证明”可接受。无需再动旧目录，不需要补一枚提交。**旧摘要的错误性质与替代来源已经清楚，补便条不会增加本轮数值可信度。

## 6. 收口与下一步

建议按用户决定，仅登记`b7509c4766a6bbfd0413749d50a5f294192b60fb`为上述限定接受版本，不合并main。记录提交应在其后，引用被审SHA而非自身，保持原脚本/数值/账本不变。

接下来合理工作是PAM瞬态及PWM/PAM联合电流验证，必须另有自包含任务和原生额度；本报告不自动启用旧余量，也不批准新启动。当前可把两个非阻断待办（observe必需集对齐、理想探针一致性容差收紧）放进该正常阶段。低压扩扫可作为后续端档表征，不能修改本轮合同追溯重判。
