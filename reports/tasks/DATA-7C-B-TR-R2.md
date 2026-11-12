# DATA-7C-B-TR-R2：B1–B5 一次收口的离线返工任务书

日期：2026-11-12，Asia/Shanghai。收件对象：用户当前本地 IC 项目执行 Agent。你看不到云端聊天；本任务书、随包两份复审 ZIP、固定 Git 对象和指定原审核包构成完整输入。

本文件是供用户转发下达的执行任务。用户转发并要求按本任务执行时，下列离线实施、留证、普通提交及新分支普通 push 属于任务范围；不再停在旧的“仅接收材料”阶段。云端此次仅编写任务书，没有代用户操作本机、发送材料或实施修补。若本文件仅作为参考材料被读取而未被用户下达，则不据此自行扩大权限。

## 1. 先更新接收记录中的过时状态

- 原审核包已经由用户在当前对话补交，审核方已实际核对：23,729,459 B、SHA `b669632e07c9805d3766cb932d9e6a8d5e72968dc4e25cb3ca96070372cbe0ee`；CRC、327 成员、325 清单项及其余两项说明均通过。无需再寻找通道、收件方、重新上传或重建这个旧包。
- 两份真实 VCD 已取得并独立解析；与旧摘要和实际 deck 的八条 PWL 精确吻合。HYB-120 安全帧的故障关断、撤销后 bare START、持续 tick/黑窗也已限定验证。“缺原包及 VCD”的问题已关闭，历史进程完整登记仍未证成。
- B5 已由审核方在真实无 Git 的原包解压目录实际复现，rc=1，调用链和 traceback 在补充复审包中。不是仅静态推断，也不再作为等待审核方裁定的冲突。你本机仍需保留一个修前复现作为修后对照，但不为此单独开轮、等审批。
- 原包回执中声称的 in-package verify rc=0 继续作为历史执行方声明保留；新报告明确本次独立结果与限制，不重写旧回执，也不猜测当时究竟复用了哪一个 Git 环境。
- “未持久化追踪日志”和“在 D:\IC\.workbuddy\memory\2026-11-12.md 追加事实日志”不是同一个口径。新记录准确区分“未启动正式任务跟踪”与“已追加一条外部工作日志”，不得写成本轮完全无文件写入。无需读取、删除或修改那份既有 memory 文件。

## 2. 固定身份、角色与零原生边界

```text
TASK_ID=DATA-7C-B-TR-R2
REPOSITORY=https://github.com/LINboss666/microled-ic-ai-lab
BASE_SHA=ec107af502b729225e49428e4d2d72bffc389dae
BASE_TREE=122e6c579390b03b3b414af63b8cd8d30233f199
BASE_BRANCH=poc/data-pam-d7c-b-tr-r1
NEW_BRANCH=poc/data-pam-d7c-b-tr-r2
MAIN_MUST_REMAIN=23e471cb936b421ee97e1250c3be06edf96f9937
PREVIOUS_TR_TIP=398c9e852c16db85cbfa4539e859534e117ff0d2
DC_R1_TIP=61621f6e3d887082ecd6a7ecc1c771f8e509a24a
PREP_R2_TIP=e51c5320a28bd5043e21d08a0be97e9d5612cd16
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_COMPILATIONS=0
NEW_RTL_SIMULATIONS=0
NEW_OA_ACCESS=0
NEW_GUEST_CONNECTIONS=0
NEW_PDK_LICENSE_OR_CREDENTIAL_READS=0
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```

你为唯一任务所有者，不委派子 Agent，不做结果合并。本轮是修离线验证与结论口径；不是优化电路、恢复旧 raw、硬件/EDA 运行或接受登记。

允许：建立新 linked worktree/新分支、读取已保存的本任务相关 raw/VCD/日志、解包到全新目录、Python 标准库离线验证和临时副本反例、小范围源码修补、在新目录持久化任务日志与结果、真实安全钩子下普通提交与新分支普通 push、只读远端 ref 回读。

禁止：启动任何模拟器，包括 -h/版本/语法预检、iverilog/vvp、OA、SSH/VM；读取凭据/模型卡/license；修改 PDK/DUT/RTL/deck/原任务契约；force、跳 hook、GC、删旧证据、合并、登记接受。push 可复用既有 Git 认证机制，但不得打开或打印凭据文件。旧 24/4 配额及余量不转化成本轮启动授权。

## 3. 输入原件及核验

随任务包给出两份原字节审核 ZIP：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `MicroLED_TR_R1_Independent_Review_REWORK_20261112.zip` | 44,551 B | `67ca995b140784c4bff368e4d7b65624de18ae1b2a29d647fca9334067e9b6c6` |
| `MicroLED_TR_R1_Original_Package_Review_Addendum_20261112.zip` | 22,515 B | `5538d459c9ec16c70d96cf5a0a40bb4785a1b07db635853602fc90f4ee588b84` |

原执行包仍使用现成文件：`D:/ic617_d7c_b_tr_r1/review/dd1_d7c_b_tr_package_d6ad344.zip`。它未重复放入本任务包；先核上述完整摘要再只读使用，不重新生成相同名字冒充原件。

先读仓库 AGENTS.md、README.md、工作流及两份审核报告。补充报告更新原报告的缺件状态；其余 B1–B4 仍有效。探针源码是审核原件，先核摘要，保留原字节。原探针硬编码旧表路径/字段或预期“缺陷复现成功”时，另外写小型适配或新探针；不能修改审核判据，也不能把旧探针自身 rc=0 直接解释成修闭。

核对本地基线及工作区干净后，在新 worktree 从完整 BASE 建立 NEW_BRANCH。现有 R1 分支及 main/DC/TR/PREP ref 不移动；若新分支已存在且不是本轮预期身份，不覆盖它，记录具体冲突。读回远端 ref 后记录实际观察；若本任务指定的冻结 ref 已变化，不重置他人分支，以具体差异停止受影响的提交/push。

## 4. 冻结面与允许路径

全部既有 `results/evidence/` 文件、旧报告/回执/任务/审核原件、旧 ZIP、账户、接受登记，以及 contract、RTL/TB、六母本、候选 DUT、18 份 deck/其账户、共享基础工具和安全规则冻结，逐 blob+mode 留基线。原生目录：

```text
NATIVE=results/evidence/dd1_d7c_b_tr_r20261026_132228_3fc148
R1=results/evidence/dd1_d7c_b_tr_r1_r20261027_143223_4c8a81
DC=results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe/dc_matrix_dut.csv
```

可修改且仅限必要位置：

- `scripts/dd1_d7c_b_tr_r1_native.py`：B1/B5 校验及延迟导入。
- `scripts/dd1_d7c_b_tr_r1_recompute.py`：B1–B4 语义校验与实际输入选择。
- `scripts/dd1_d7c_b_tr_r1_publish.py`：仅按新校验生成本轮新目录结果；不能覆盖 R1。
- `scripts/dd1_d7c_b_tr_record.py`：仅与 B4 计数/新包闭包、无 Git 说明和本轮入口有关的部分；保留旧 evidence 只读判据。
- `scripts/dd1_d7c_b_tr_run.py`：仅修 `Account.duplicate_bookings/processes` 等 B4 相关的错误去重路径；不启动 runner、不变更启动授权或账户写入协议。

可新增小型 `scripts/dd1_d7c_b_tr_r2_*.py`、`tests/dd1_d7c_b_tr_r2/`、新 `results/evidence/dd1_d7c_b_tr_r2_<run_id>/`、`reports/dd1_d7c_b_tr_review_fix_r2.md`、`reports/agent_handoffs/DATA-7C-B-TR-R2.{md,json}`、本任务原字节副本 `reports/tasks/DATA-7C-B-TR-R2.md`。

不为新 prefix 重导出或重复跟踪 32 MB 序列。新报告/状态引用 BASE 的冻结序列与账户，在新包中复制原字节依赖即可。可用几个明确参数或一个小型本轮描述文件指明原生账本、数值序列、新状态表的位置；禁止依赖“猜最后一个目录”选择输入。不是建立通用事务、权限或审核平台的任务。确需白名单之外更改时先给具体必要差异，不自行扩展。

## 5. B1：完整性必须覆盖实际交付对象

当前 `native.verify()` 未分片分支只看文件存在，嵌套 `internal_fragment` 没有遍历；preflight 损坏后 verify 与 recompute 都会成功。

修后统一验证 whole、parts、冻结依赖和所有实际交付的嵌套片段：长度/SHA、分片编号及唯一性、各片摘要、重接总长度/SHA、精确文件集合。拒缺片、额外片、重复/非法清单项、目录越界、重复证据身份和未声明的交付内容；避免目录猜测造成读到另一个同名文件。不要只在 CLI 外加一层检查，底层可达入口与旧入口也不得形成旁路。

“已校验 N 项”只能计实际做过的检查。Git 跟踪树中两 VCD 是具名未交付，不能计验证成功；新审核包中带真实 gzip VCD 时，应在其实际位置核 gzip 和原字节摘要。预检 9 份数据除字节完整性外，若状态宣称执行/仪表/供电重判，就应从实际 preflight 序列和冻结刺激/环境计算，不复用旧 PASS 文本。

至少验证：同长首字节 T→X 的 TR-120 DUT whole、TR-120 preflight whole；RS-SWITCH 内部片段 part000 同长损坏；HYB-120 主序列 part000 损坏作为既有正确拒收对照；缺片/多片。每项先过完整干净输入，再做单一突变并指名拒收。更进一步：对一个 preflight 的单位或供电作语义突变并同步更新容器及清单摘要，仍必须在预检语义阶段拒收，不能仅靠旧摘要不符。

## 6. B2：十状态按实际内容重判

状态名集合必须精确，拒缺项/重复/额外/空数值/NaN/非法 verdict。先从实际输入形成事实结果，再比较发布的 verdict、measured、expected；不能以状态表自己的声明产生“期望值”。保持独立复算不 import 上层 measure/publish。

本轮新状态表明确各字段意义，避免原 `13/0` 或把工具的 835 条内部检查数当成物理样本覆盖的含混口径：

| 状态 | 本轮应核对的事实 |
|---|---|
| EXECUTION_COMPLETENESS | 9 DUT+9 preflight 对应固定计划，18/18 确认；UNCERTAIN/失败尝试仍留账 |
| EVIDENCE_INTEGRITY | 37 个精确窗口的 launch/raw/deck 身份与已交付数据关联；容器完整性另列全覆盖明细 |
| DYNAMIC_CHARGE_STATUS | 从序列+冻结 DC 目标得 33/37，FAIL |
| NOMINAL_CHARGE_STATUS | 从序列+名义目标得 23/37，FAIL |
| SETTLING_STATUS | 34 发光窗的明确目标、±5% 带、持续至少10ns和 flat_stop；不得核一个目标却声称两个目标都核过 |
| SHUTOFF_STATUS | 34 个纯 off 尾窗+3个全黑窗，共37；max\|I\|≤150nA |
| CONVERGENCE_STATUS | 三对13个唯一指定窗逐条重算；本轮计通过数/应有数，说明与旧13/0的字段语义修正 |
| NATIVE_SEQUENCE_REINTEGRATION | 37窗两列电荷结果实际重算的覆盖，可报37/37；工具检查条数另列，不作自指证明 |
| RTL_INPUT_PROVENANCE | 实际读取已取得的两份真实VCD/八条deck PWL后可报2/2；不能仅核两个case字符串或旧summary的PASS |
| BUDGET_ACCOUNTING_STATUS | 分列Spectre总上限24、主账上限22、总占额21；RTL按第8节，证据不足时整体PARTIAL，不伪造PASS |

settling 的最后离带、起点、deadline 左极限等既然作为实测字段发布，就要与实际序列比对；不得保留未校验的结论性字段。当前实际两目标都过，若实现发现真实差异，保留新发现并逐项说明，不改窗口或指标追绿。

至少将预算行改成 `FAIL,999,1`、对一个应 PASS 状态改 verdict、对一个状态单独改 measured/expected、加额外名称/删项/重复项；在完整输入及同步表级摘要情况下，各自具名拒收。合法的电气 FAIL，以及如实记录的历史 RTL UNKNOWN/PARTIAL，是有效结果，不应被伪装成格式损坏。

## 7. B3：精确收敛键集合，不只数13行

冻结期望来自契约、实际 deck 和计划的以下集合，而不是从待验 CSV 自己生成：

| refined/coarse | window_id → code |
|---|---|
| RS-FULL/TR-LONG | W0→000，W1→001，W2→010，W3→011，W4→100，W5→101，W6→110，W7→111 |
| RS-LOW/TR-120 | W0→000 |
| RS-SWITCH/TR-OFFCODE | W0→011，W1→100，W2→000，W3→111 |

先验证完整且唯一的 `(pair,refined_case,coarse_case,window_id,code)`，以及冻结 context_fields，不以两边都缺值作为匹配。再从两侧真实序列 Q 核带符号 dQ、1.875µA×120ns 的 QLSB、绝对比值和逐窗 verdict，限值0.01不变。

反例至少含：首条复制13次、用重复替换一条但保持13行、错 pair/code、改带符号 dQ。对未知 pair 不可跳过。正确集合与正确重排应通过；不得硬编码读取某个发布答案作为通过条件。

## 8. B4：把程序身份与进程身份分开

同秒同案例、某行缺字段、四个 executable SHA 都不足以证明 R001 没启动。纠正 `derive_duplicates()`、`Account.duplicate_bookings()` 和 standalone 入口的全部可达旁路，不能仅更改报告文字。

允许只读已有逐启动日志/命令转录，若有可交付的唯一启动关联证据，精确证明 R001 是未到 subprocess 的重复预约，并绑定 R002。不要让用户替 Agent 逐条查日志；能现成取得就一次整理，不能恢复就明确停止追证，不重仿真。

证据不够时采用原 R1 任务允许的诚实出口：`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`；保留5行原账，说明4行有启动材料、另1行不能排除，保守占额5/4。该保守占额是风险口径，不是断言已证实5次真实启动。`BUDGET_ACCOUNTING_STATUS=PARTIAL`，不追认预算、不退款、不宣称剩余额度可用；新任务的原生授权仍为0。如实完成这种披露及拒绝错误扣减，属于本项修补完成，不能为凑全PASS无限造工具或补跑。

必要小例：同一个 executable SHA 的两次确实不同启动仍计两次；无证据UNCERTAIN不自动扣减；五条实际带启动证据的行不可当四次；一个有真实机械关联的重复预约只能去重该预约。均使用临时账户和 mock，不写旧正式账。

## 9. B5：真无 Git 包内入口与调用证据

修前原包的独立复算已经是838/838；它不能替代 native.py 的可移植性测试。之前主审核探针调用的是 Git 检出里的 verify 脚本，即使证据来自无Git副本，也不是“从无Git包启动verify”。

修前用全新仓库外目录解包原 ZIP，记录实际脚本绝对路径、cwd、rc、stdout/stderr。目录和所有祖先不得含 `.git` 文件/目录；清除子进程里的 GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR 等 Git 定位覆盖。只记录这些变量是否已清除，不打印整个环境。可在启动测试前单独用只读 `git -C <解包目录> rev-parse --show-toplevel` 的具名失败证明无仓库；其调用与后面的待验脚本调用分开记录。

修后至少这两条均从最终新包内部的源码启动：

```text
python -B <解包目录>/scripts/dd1_d7c_b_tr_r1_native.py --verify <明确证据目录>
python -B <解包目录>/independent_recompute.py <明确包根/本轮输入选择参数>
```

如改了入口名，README给唯一真实命令，旧入口委派或指名拒绝，不保留声称可跑但漏验的旧入口。验证本身只依赖标准库及包内数据，不能调用git/guest/其它进程；可在离线测试中对 subprocess 做拒绝并记录，证明无隐藏Git依赖。export需要的工程导入可移到该分支内部，不为此更改冻结 contract 或强塞 .git。

新包内完整干净输入要成功，B1–B3的相同语义反例要具名失败；写前拒绝，前后正式树文件集合与摘要不变。Git绑定的 producer/packager 若不承诺可移植，在文档明确标明；不得为了输出rc=0静默跳过核验。

## 10. 物理规则保持不变

TT/27°C，IREF=15µA，vdd18/VCAS=1.8V，VSS=0，理想夹持1.20V；000是最低非零码，仅enable关断才黑。

```text
reference_tick(TR-200,HYB-200)=200ns；其余七例120ns
QLSB=1.875e-6A * reference_tick
Inom(k)=(k+1)*1.875e-6A
IDC(k)=冻结DC表1.20V的I_sink_A
Qnom=Inom*T50；Qdc=IDC*T50
err_nominal=(Q-Qnom)/QLSB；err_dynamic=(Q-Qdc)/QLSB
abs(err)<=0.5；abs(dQ)/QLSB<=0.01
```

保留动态4失败窗：TR-OFFCODE W3 -0.583518980605、RS-SWITCH W3 -0.582423831012、HYB-120 W2 -0.563928865409 / W3 -0.542063361091 LSB。名义仍14窗失败，最大HYB-200 W2 +12.723361000160 LSB。不调参考、器件尺寸、边沿、窗口、分母、阈值，不重导出平均/抽点序列。

两VCD的解压摘要分别为：HYB-120 `0d07a25a55787e3c6eda262e9c03d9b01c30fb21790ef90d49d3af5d604a191f`；HYB-200 `0798d47c83d22b119e7fa4a678449c2e929f23cf106d540c6c4a181ea7211eb1`。沿总宽2ns、整体+1000ns、bit序与真实deck不变；安全帧旧证明不扩大为物理CDC/SOA。

## 11. 一次实施与留证顺序

1. 核输入/BASE/冻结面，创建新worktree与run_id；持久化本轮任务日志到新R2目录。保留旧接收记录，不篡改历史阶段。
2. 在临时副本复现已有B1–B3和原包B5；记录预期缺陷行为与实际rc，B4列证据差距。只做覆盖五项必要测试，不重跑无关研发链。
3. 小范围修补；每次写前明确输出是新目录。缓存不得让后续突变复用旧PASS。先修完整性/预检，再做语义及状态重判，验证失败不得继续发布“成功状态”。
4. 同一版源码跑干净与反例，保存病例→突变→入口绝对路径→rc→拒收原因。更换输入清单摘要的语义反例，须在完整依赖下命中目标错误，不能靠缺文件/模块失败充数。
5. 从冻结序列产生本轮新状态与差异表；37窗电气数字不变、字节差异/口径变化逐项记录。B4若UNKNOWN/PARTIAL按实发布。
6. 新输出与所有旧正式证据前后按集合+SHA比对；不得只看git status。失败尝试保留在明确scratch/parked位置，不删或覆盖旧发布物。
7. 针对改动的模块做必要回归，旧R1修过的账户防覆盖、输入单位、时间轴、供电、+10ns端点、黑窗峰值等用现有离线测试回归即可。依赖本机raw的测试未跑则写NOT_RUN及原因，不伪报260/260。

不清理旧证据里的尾空白：原范围diff --check rc=2作为历史事实保留。本轮 `BASE..新HEAD` 应检查自己的新增/修改文本；不要用格式化整树制造额外差异。

## 12. 提交、打包、真正包外回放与停点

- 功能修改合成一个有意义的payload提交，记录可另提交；每次真跑安全钩子。钩子若要求禁区动作，停下报告具体冲突，不绕过。
- 复用既有数值容器，不重复入库。不扩大既有32MiB数值证据口径；列明复用量、本轮新增blob、修改后blob/净增长各自范围。若超出既定口径，不删旧数据、不私增限额，明确PARTIAL及缺口。
- 用已提交固定SHA打包到新文件名，如 `dd1_d7c_b_tr_r2_package_<commit>.zip`；不覆盖任何旧ZIP。包内含新脚本实际导入/读取闭包、冻结序列/DC/deck/账本、两份已有VCD及R2结果、正确README和精确成员清单。
- 包外使用全新无Git目录执行第9节完整流程，验证失败则修补并提交新固定SHA再生成新包；旧失败包保留。不要出现“测的是未提交字节，包却标已提交SHA”。
- 包摘要记包外回执，避免自指。回执必须写清包的payload SHA、后续仅回执提交的分支tip，以及每条实际包内脚本路径/rc；不能以本地rev-parse冒充第二路远端回读。
- 普通push仅NEW_BRANCH；回读远端完整SHA与时间，核对R1/main/DC/TR/PREP未动。不得发邮件/聊天或自行选择其它收件人；本轮审核材料通过用户当前对话回传原文件与回执。
- 交付最新报告、handoff、B1–B5闭环表、原/新状态差异、所有关键反例JSON/输出、固定SHA及原包附件。不要只发“全绿”；预检范围、RTL未知、真实电气FAIL分别明确。

最终停在独立复审，不自签GO，不登记接受，不合并，不开启下一原生阶段：

```text
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
TASK_ID=DATA-7C-B-TR-R2
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_COMPILATIONS=0
NEW_RTL_SIMULATIONS=0
NEW_OA_ACCESS=0
NEW_GUEST_CONNECTIONS=0
NEW_PDK_LICENSE_OR_CREDENTIAL_READS=0
CANDIDATE_DUT_CHANGED=NO
OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
```

`OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO`须由本轮冻结树比较支持；发生过写入/恢复的历史仍须披露，不用最终状态掩盖事故。若任一项无法完成，交付已做结果及具体限制，不能因希望全PASS而继续越权、重跑原生或造假。
