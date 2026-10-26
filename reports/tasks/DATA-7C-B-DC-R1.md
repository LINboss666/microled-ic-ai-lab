<!-- Provenance, added when this task book was filed: the body below is the attached file byte for byte. -->

| field | value |
|---|---|
| attached file | `TASK_DATA7C_B_DC_R1.md`, 9857 bytes, sha256 `344d0b66d9781c3b676862387a0384626f54c2c052e711ec07633577942d66fd` |
| accompanying review package | `MicroLED_DATA7C_B_DC_Independent_Review_REWORK_20261026.zip`, 47977 bytes, sha256 `e603abeef577d5a60415c50ac631fcfec286e9928edc1fe8f8037bdb42c398fe`, 34 manifest rows verified |
| REVIEW_RECOMMENDATION | REWORK, limited to the offline extraction, judgement and evidence close-out |
| ELECTRICAL_RECOUNT_ON_COMMITTED_TABLES | PASS (independent Decimal re-count of the 152 DUT and 152 preflight rows) |
| native work authorised by this task | none: NEW_SPECTRE_LAUNCHES=0, NEW_RTL_SIMULATIONS=0, NEW_OA_WRITES=0, NEW_SSH_OR_VM_ACTIONS=0 |

---

# DATA-7C-B-DC-R1：一次完成有符号判据、必需观察与发布身份修补

你看不到用户与ChatGPT聊天；本任务、配套独立复审包和固定Git源是完整输入。按GitHub Bridge Review Workflow v1.0执行：修补→离线正反例→Git安全提交→回读→独立复审。用户已要求继续复核交付，本任务只含原范围离线修补；不要求也不授权任何原生操作。

## 0. 固定源与零原生成本

```text
TASK_ID=DATA-7C-B-DC-R1
REPOSITORY=https://github.com/LINboss666/microled-ic-ai-lab
BASE=337563fc22699e480bf7fc82890750c126a50654
BRANCH=poc/data-pam-d7c-b-dc-r1
OLD_OFFLINE_BASE=e51c5320a28bd5043e21d08a0be97e9d5612cd16
MAIN=23e471cb936b421ee97e1250c3be06edf96f9937
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
NEW_SSH_OR_VM_ACTIONS=0
NEXT_NATIVE_STAGE_AUTHORISED=NO
```

不运行Spectre（含-h、语法、其他仿真器、预检、重跑旧例），不读PDK/凭据/license、不进guest、不改环境或口令。可以只读本机自有已保存raw/log，但不因缺它们重新连接或启动。不得用旧20次余4次补跑；历史DATA-7B59/56及凭据事件不处理、不追认。无merge/force/GC/历史重写/跳hooks/仓库可见性改变/推main。

创建新worktree，不覆盖旧目录。先读根AGENTS、README、本轮原任务 `reports/tasks/DATA-7C-B-DC.md`、新复审报告与仪器、旧合同和三个DC脚本。回读源ref/full SHA，若源已变停下说明，不自行吸收。不要执行完整bridge自测（会触发超范围OA等动作）。

## 1. 目标与冻结面

当前表的152条DUT数据已经由审核方独立复算通过，不重做电路。四DUT及六母本、15份PREP deck、派生DC/preflight deck、合同电气值、旧证据/报告/交接/账本一律保持BASE字节。只修下面四组缺口，用现有数据给出正确的新离线判定与当前Git身份。

现有路径仅允许修改：

- `scripts/dd1_d7c_b_dc_run.py`
- `scripts/dd1_d7c_b_dc_matrix.py`
- `scripts/dd1_d7c_b_dc_record.py`

其他只允许新增本轮小型测试/仪器副本、`reports/tasks/DATA-7C-B-DC-R1.md`、`reports/dd1_d7c_b_dc_review_fix_r1.md`、`reports/agent_handoffs/DATA-7C-B-DC-R1.{md,json}`、全新 `results/evidence/dd1_d7c_b_dc_r1_<run_id>/`。旧原生表可直接只读引用；如新记录需要副本则逐字节复制并声明复用，不能重新标为新仿真。所有已发布路径不先删、不覆盖、不重命名。

不新建通用SPICE解析器、事务框架、记录平台；本轮是几处明确函数修补和端到端复核。每个实质问题最多3次修补尝试，再失败保留证据停止，不反复扩大任务。

## 2. 先复现，保留旧负结果

配套 `probe_dc_review_gaps.py` 不改字节。在未改BASE运行：

```bash
python probe_dc_review_gaps.py --repo <BASE_checkout> --out <new_scratch>/baseline_probe.json
```

预期rc=0、any_defect_reproduced=true、7个诊断逐项true，包含F1反向低压点、F3仅8行、F2四种缺失信号、F4两张图身份。逐字段读JSON，rc=2是仪器错误，不能当检出。仪器可在新记录上使用 `--evidence results/evidence/dd1_d7c_b_dc_r1_<run_id>`，新记录如未复制matrix/source_identity，应提供不覆盖原件的可重放视图并写明入口。仪器本身不得修改来通过。

## 3. F1：修正有符号区间与数值有效性

`band_of()` 核心必须是：

```python
limit = fraction * abs(target_A)
good = {v: abs(i - target_A) <= limit for v, i in pairs}
```

不能 `abs(abs(i)-abs(target))`。先拒非有限点，不让NaN/Inf靠比较为False变成普通带外点。负读数保留其符号，不取abs后作为正电流。

正反例：

- 原152行：主评价PASS、8码区间0.60..1.50。
- 仅将八码0.60 V读数变负：0.60为带外，连续已测下限应0.65，相邻失败点0.60；主评价可以仍PASS，必须明确主点与区间不是同一判据。
- 合成幅值真正偏离±5%、中间断点、负值、NaN/Inf分别给预期，不缩紧原电气指标。

## 4. F2：必需观察缺失不得填合同值

`extract()` 在构造任何行或写任何正式文件之前，要求：axis、探针电流、data_out、vdd18、vss、vcas、data_en、pam0/1/2、iref_in都真实存在；单位和各列长度/有限性可确认。沿用已接受PSF读取器，不改共享模块。

删除用合同补vdd18/vcas/data_en以及用case名补code的兜底。逐点静态源和码位应与本case的冻结deck一致；逻辑高1.8 V、低0 V，可用显式数值容差但不可把任意0.9V以上都当合格输入。全部PAM位必须实测，code/pam_bits/case不能混码。实际输出与扫描夹持不一致应拒收。

Iref源条件可从冻结deck读出，角/温度也是deck条件；如没有直接测得电流或原生温度字段，就按来源标记，不编造观测。可选内部节点缺失只标NOT_OBSERVED；必需项不能NOT_OBSERVED仍称完整提取。

已有合成PSF正例可能缺vss或PAM单位：完善明确的测试fixture，别为了保留错误fixture而降低要求。增加缺各必需项、错输入电平/错码/电平沿扫描改变、非有限、缺点/重复点、错误单位的拒收测试；正确fixture和现有本机raw仍应可读。拒收对预置非空输出目录逐摘要不变，不花原生额度。

## 5. F3：每个完整PASS入口都先验证同一个完整矩阵

新增或复用一个小型纯验证函数，将它连接到 `judge()`、公开`--judge`、matrix check/judge路径，不能只新增一个孤立自测入口。

要求：8码×19点精确key全集=152；每行角色、case/code/pam_bits、单位、有限数及条件一致；缺点/重复/额外/未知码/破损列拒收。若内部仍需要8主点算术函数，必须清晰命名，不能单独返回完整阶段PASS。

正反例至少包括：原152行PASS；仅8主点、151/153行、重复替换缺点、非有限、单位错各拒收；负电流不翻正。冻结满量程14.25–15.75µA、比例0.25单位、单调性等不变，不将低夹持区间失败等同于1.20V主点失败。

保留原`manual/D000`行不改写。追加 `extraction_identity_resolution.csv`，从(case_id,role,deck_sha256,raw_sha256)唯一对应到账本真实run_id/launch_id，共16个来源；缺失或一对多拒收。不要把新R1的run_id伪装成原生仿真run_id。

## 6. F4：新记录按Git字节闭合，历史不覆写

审核方已证明两SVG登记的正是CRLF散列，而Git保存LF。直接引用BASE中当前LF图，不重画、不重跑。新身份只从将交付的Git blob（或正确的stage blob）获取字节数与摘要；来源提交写完整SHA。对新记录从Git抽到仓库外重放，确保全部身份（含图）匹配。摘要不自指，不把新报告不断渲染后仍散列自己。

修正record.py中 A到µA的显示系数 `1e9 -> 1e6`，给一个精确正例 `9.1175e-13 A -> 9.1175e-7 µA`，不得改judgement的A值。新报告更正旧门描述的1000倍笔误。

旧范围 `git diff --check e51c532..337563f` 实际rc=2（378处空白），不是0；其中有原样保存审查日志和历史证据，不为清零破坏它们。新报告明确旧负结果，新改动区间 `BASE..new_tip` 应rc=0。不要改变Git whitespace规则或属性来掩盖。最终范围单列（BASE旧新增115/修改2/删除0/15提交为e51..BASE），不把早先103/13快照当最终范围。

旧记录保留，说明其两张图身份与单位描述过期，新的正式记录接替哪部分。不要把“包的MANIFEST自洽”当“其内部source_identity正确”。

若顺带处理`observe()`无raw返回PASS的空洞，只允许在matrix.py内小修：无raw必须NOT_RUN/NOT_OBSERVED，不再写观测PASS；包装脚本按预期字段验收，不为了rc=0伪称内部节点被本机重新观察。

## 7. 同一轮验证与交付

不分拆“先交工具再交证据”。一次完成：修补、上述正反例、35旧自测适配/必要扩展、原31合成/34候选/65反例不退步、小型账本读取与16行重算、必需旧母本冻结、交接检查、新记录身份核对和Git安全闸。

新报告至少列：每组根因→具体修改→旧复现→修后字段；电气8码总表保持原A数值；最大残差单位纠正；当前表无需重跑；16/20旧账本逐字节不变、无退额、0新启动；原始raw未带包的可复核边界；凭据及历史预算事件仍未解除。

审核仪器修后7项全部false才算关闭，但要读每项字段，不能仅看rc=1。新记录的完整key/身份正例必须通过，所有拒收路径不得写正式证据。正式发布后使用空目录从blob抽取重放，记录命令与expected/actual rc。不要调用会重写已发布证据的merge/observe/judge；需要写文件时用独立副本并复核原目录不变。

交付一个从最终blob构建的包：任务、报告、MD/JSON交接、修改源码、必要只读依赖、新记录、原始数值表/账本或可解析依赖、复现仪器原字节与正反结果、README/清单。生成导读用PACKAGE_README，不覆盖仓库README；Git依赖入口在无.git包里如实NOT_RUN，提供真实等价数值重算，不承诺不存在的CLI。摘要写包外且不自指。若提供旧ZIP，保持旧文件不覆盖，新包新名。

安全提交、普通push新分支、对同一对象回读full SHA；main及旧分支不动。不登记接受版，不自签GO，不进入瞬态。最终回执：

```text
REPAIR_SCOPE=OFFLINE_DC_MEASUREMENT_AND_IDENTITY_ONLY
ORIGINAL_152_NATIVE_ROWS_CHANGED=NO
ORIGINAL_NATIVE_ACCOUNT_CHANGED=NO
CANDIDATE_DUT_CHANGED=NO
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
NEW_SSH_OR_VM_ACTIONS=0
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
NEXT_NATIVE_STAGE_AUTHORISED=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
SOA_SIGNOFF=NO
```
