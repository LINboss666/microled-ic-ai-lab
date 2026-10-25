# DATA-7C-B-DC：八档 PAM 单输出通道直流实测报告（停在独立复审闸）

## 1 身份与授权

| 项 | 值 |
|---|---|
| 任务 | `DATA-7C-B-DC`（任务书 `reports/tasks/DATA-7C-B-DC.md`，8,609 B 之外本轮为 13,213 B `4cb0e22b…`，与原件逐字节相同） |
| 登记的离线内容 | `e51c5320a28bd5043e21d08a0be97e9d5612cd16`（分支 `poc/data-pam-d7c-b-prep-r2`，复审建议 GO 的那份字节；登记见 `reports/reviews/DATA-7C-B-PREP-R2-GO/registration.json`） |
| 本轮分支 / 工作树 | `poc/data-pam-d7c-b-dc` / `D:\ic617_d7c_b_dc` |
| 授权 | 用户 2026-10-25 选择"批准 20 次，一跑到底"+"登记，限 PAM 候选与离线准备"；Spectre 上限 20 = 8 预检 + 8 DUT + 4 调试余量 |
| 实测判据来源 | `tests/dd1_d7c_b_prep/contract.json`（本轮冻结）之 `clamp`/`full_scale_absolute`/`eight_level_ratio`/`supplies`/`process_corner`；快照与漂移规则在 `tests/dd1_d7c_b_dc/contract.json` |
| 完成级别 | `NATIVE_PAM_DC_TT_MEASURED`（不超过此级别） |
| 成本 | Spectre 启动 16/20、RTL 0、瞬态 0、OA 0、凭据值记录 0、模型卡内容入库 0、PDK 绝对路径入库 0 |

## 2 复用而非重写

按 §3 读完必读源后，本轮只新增两个入口，不建通用 SPICE 解释器、不建事务发布框架、不复制旧额度：

* `scripts/dd1_d7c_b_dc_run.py`：派生运行副本、本轮专用账本、启动与取回、提取与判定、离线正反例族。
  端口方向标注的剥离、器件与端口序摘要、SSH/scp 通道与运行器应答解析全部调用已被接受的
  `scripts/dd1_d7b_run.py` 里的那几个函数（`strip_direction_annotations`、`device_digest`、
  `port_order_digest`、`DIRECTION_RE`、`Link`、`parse_runner`），psfascii 读取用 `scripts/sc1_read_psf.py`。
  该文件 `NEW_LAUNCH_GRANT = 0` 的启动入口与 56/59 的历史账户都没有被复用，也没有修改。
* `scripts/dd1_d7c_b_dc_matrix.py`：把提取的逐点行合并成 8×19 矩阵、独立复算判据、画两张图。
* `scripts/dd1_d7c_b_dc_record.py`：本轮记录表；不重命名旧轮次的门名，也不复制它们的记录框架。

## 3 模型身份与派生副本（只读核验，未花额度）

`results/evidence/dd1_d7c_b_dc_r20261026_015212_376554/model_identity.json`：四个模型
`n18/p18/n33/n33_dnw_4t_ckt` 在 deck 所引 `$QODER_PDK_LIB`（8,721 行、184 条相对 include）可达的树里
**各定义恰好一次**，`section tt` 存在；闭包用到的全部 W/L 都在卡的 lmin/lmax/wmin/wmax 之内。
模型卡里的数字没有写进仓库，只记判定结果与该文件的 sha256。

`spectre/dd1_d7c_b_dc/` 是生成物（`--emit`），`strip_account.json` 逐文件记录：六个 master 共剥离
**63 行**端口方向标注（4+2+20+22+6+9），剥离前后 `device_digest` 与 `port_order_digest` 全等，行数差
恰好等于剥离行数；八份 `.pre.scs` 预检副本各替换 **1 行** `Xdut` 为两行理想仪表负载、删除 **5 行**
`save Xdut…`，19 点夹持扫描、分析行、探针与显式 `Vss (vss 0) vsource dc=0` 与交付 deck 逐字节相同。

一个环境事实：guest 的 `spectre/pdk_local.env` 只有 `QODER_PDK_LIB/QODER_SMIC/QODER_TSV…` 四个键，
**没有** `QODER_NETLIST_DIR`，而交付 deck 的 include 用它。本轮没有去改那个 gitignore 的配置文件，
而是在运行载荷里显式导出它指向本轮 master 目录；执行器本身对未解析的 `${QODER_*}` 直接 rc=9 拒跑，
所以这条路径不可能被静默绕过。

## 4 方法与判据

八码在同一 data_out 通道上依次静态施加（`DATA_EN=1.8 V`、`pam0/1/2` 按权重 1/2/4、`Iref=15 µA` 注入
二极管连接参考节点，不用理想 VBIAS 替代），输出夹持 0.60–1.50 V 步 0.05 V 共 19 点，
`Ip_branch (clamp_node data_out) iprobe`，`I_sink = Ip_branch` 不取负不取绝对值。
主判据只作用于 1.20 V：满量程 14.25–15.75 µA、八码严格单调、共享 `Iunit_ref = I111/8` 且每档
`|Ik − (k+1)·Iunit_ref| ≤ 0.25·Iunit_ref`；绝对满量程与比例必须同时满足，归一化不能救整体偏小。
另按每码相对其 1.20 V 电流 ±5% 给包含 1.20 V 的**连续已测**区间、最低已验证点与相邻未通过点，不外推。

## 5 实测结果

判决：**PASS**，152 条唯一数据（8 码 × 19 点），全部来自原生输出。

<!-- BEGIN 7CBD_LADDER -->
| 码 | 实测 I(1.20 V) /uA | 名义 /uA | 偏差 /uA | 偏差 / Iunit_ref | 已测 ±5% 区间 | 最低已验证 | 相邻未通过 |
|---|---:|---:|---:|---:|---|---:|---:|
| `000` | 1.922839 | 1.875 | 0.000000912 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `001` | 3.845677 | 3.750 | 0.000000764 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `010` | 5.768515 | 5.625 | 0.000000622 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `011` | 7.691353 | 7.500 | 0.000000486 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `100` | 9.614191 | 9.375 | 0.000000355 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `101` | 11.537029 | 11.250 | 0.000000233 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `110` | 13.459867 | 13.125 | 0.000000106 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
| `111` | 15.382706 | 15.000 | 0.000000000 | 0.000000 | 0.60..1.50 | 0.60 | NO_MEASURED_POINT_BELOW |
<!-- END 7CBD_LADDER -->

满量程与共享单位：I111 = 15.382706 µA（带 14.25–15.75 µA ✓，相对 15 µA 目标 +2.55%），
`Iunit_ref = I111/8 = 1.922838 µA`，最大偏差 0.000000912 µA ≈ 0.0000005 个 Iunit_ref（限 0.25）。
名义阶梯是 `ESTIMATED_MIRROR_RATIO_ONLY` 的估算，实测比它整体高 2.55%——这正是本轮要测的量。

预检仪表见证（8 例逐条，非 DUT 结果）：19 点全部读 `clamp/80 kΩ`，在 1.20 V 点为 +15.000000 µA，
参考节点 0.750000 V，符号为正——探针方向与解析链在任何 DUT 数字被使用之前就被确认。

两张图由合并后的原生表绘制，轴标 V 与 µA：`figures/dc_iv_curves.svg`（八码 I–V 曲线）、
`figures/dc_ladder_at_1p20V.svg`（1.20 V 八档阶梯）。

## 6 闸与账本

<!-- BEGIN 7CBD_GATES -->
| 门 | 命令 | rc | 期望 | 判决 | 依据 |
|---|---|---|---|---|---|
| `dc_offline_selftest` | `python dd1_d7c_b_dc_run.py --selftest` | 0 | 0 | PASS | DC_SELFTEST: PASS (35/35 named exactly, failures: none, evidence OFFLINE_NO_PROCESS) |
| `preparation_contract_selfcheck` | `python dd1_d7c_b_prep_contract.py --check` | 0 | 0 | PASS | D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=26 problems=0) |
| `preparation_schedule_check` | `python dd1_d7c_b_prep_schedule.py --check` | 0 | 0 | PASS | D7C_B_SCHEDULE_CHECK: PASS (rows=15 windows=143 pwl=300 problems=0) |
| `preparation_deck_check` | `python dd1_d7c_b_prep_deckgen.py --check` | 0 | 0 | PASS | D7C_B_DECKGEN_CHECK: PASS (15 decks, problems=0) |
| `preparation_deck_reader` | `python dd1_d7c_b_prep_r1_deck_read.py --check` | 0 | 0 | PASS | D7C_B_PREP_R1_DECK_READ: PASS (15 decks, problems=0) |
| `preparation_synthetic_cases` | `python dd1_d7c_b_prep_cases.py` | 0 | 0 | PASS | D7C_B_PREP_CASES: PASS (31/31 named exactly, failures: none, evidence SYNTHETIC_NOT_MEASURED) |
| `candidate_offline_checks` | `python dd1_d7c_a_offline_check.py` | 0 | 0 | PASS | D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none) |
| `candidate_counterexamples` | `python dd1_d7c_a_guards.py` | 0 | 0 | PASS | D7C_A_GUARDS: PASS (65/65 named exactly; not hit: none) |
| `earlier_handoff_binds_its_own_bytes` | `python dd1_d7c_b_prep_r2_verify.py --handoff-check` | 1 | 1 | PASS | rc=1 by design: the R2 handoff digests the bytes of its own round, and this round legitimately moved reports/dd1_d7c_b_prep_contract.md, scripts/dd1_d7c_b_prep_contract.p |
| `internal_observations_recorded` | `in process: read observed_signals.json, written by dd1_d7c_b_dc_matrix` | 0 | 0 | PASS | every required signal (data_out, clamp_node, the supplies, the three PAM bits, the reference node) is present in all 8 answers; the deck asks for 39 observation names and |
| `dc_handoff_structure` | `in process: handoff_check() over DATA-7C-B-DC.json against the record,` | 0 | 0 | PASS | fields, per-code uA re-derived from judgement.json, account labels and costs agreeing, digests against disk, markers, no self-listing |
| `dc_matrix_shape` | `python dd1_d7c_b_dc_matrix.py check <evidence>` | 0 | 0 | PASS | DC_MATRIX_CHECK: PASS (152 dut rows, 152 preflight rows, problems: none) |
| `dc_judgement` | `python dd1_d7c_b_dc_matrix.py judge <evidence> then read judgement.jso` | 0 | 0 | PASS | I111 15.382706 uA band [14.25, 15.75]; Iunit_ref 1.922838 uA; monotonic True; ratio True; worst deviation 0.000911750 uA; bands contain 1.20 V for all eight codes |
| `launch_account_reconciles` | `in process: read launch_account.csv, require one preflight and one dut` | 0 | 0 | PASS | 16 rows, ceiling 20, remaining 4, one preflight + one dut per case, every raw paired |
| `every_published_json_parses` | `in process: json.loads over every .json this round publishes` | 0 | 0 | PASS | 10 files parse |
| `record_line_endings` | `scan every published table for CR and round-trip a comma-and-quote row` | 0 | 0 | PASS | published files with CR: none; writer emits LF (confirmed) |
| `unauthorised_refusal_writes_nothing` | `python dd1_d7c_b_dc_run.py --launch DC-000 --role dut --out <temp> (wi` | 0 | 0 | PASS | rc=5 evidence_dir_created=False refusal=DC_LAUNCH {"case_id": "DC-000", "process_started": false, "refusal": "DATA-7C-B-DC: this call is not |
| `ceiling_refusal_before_a_process` | `in process: Account(ceiling=1) reserve, settle, reserve again` | 0 | 0 | PASS | LAUNCH_CEILING_REACHED: the account already carries 1 of 1 launches; a failure costs the budget and recovery n |
| `judgement_cannot_be_normalised_into_a_pass` | `python dd1_d7c_b_dc_run.py --selftest (case a_uniformly_short_ladder_i` | 0 | 0 | PASS | a half-height ladder reads FAIL on the absolute test while the ratio test passes, which is the pair the task book requires together |
| `provenance` | `python scripts/provenance_check.py` | 0 | 0 | PASS | SOURCE_PROVENANCE_CHECK: PASS |
| `history_safety` | `python scripts/precommit_safety_check.py --mode history` | 0 | 0 | PASS | SAFETY_GATE: PASS |
| `frozen_surfaces` | `in process: blob and mode comparison over explicit path lists against ` | 0 | 0 | PASS | enforced rows 9, violations 0, informational 0; details on the violating rows: none |
<!-- END 7CBD_GATES -->

<!-- BEGIN 7CBD_ACCOUNT -->
| 例 | 预检行 | DUT 行 | CONFIRMED | FAILED | UNCERTAIN | raw 配对 | log 配对 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `DC-000` | 1 | 1 | 1 | 1 | 0 | 2 | 2 |
| `DC-111` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
| `DC-001` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
| `DC-010` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
| `DC-011` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
| `DC-100` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
| `DC-101` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
| `DC-110` | 1 | 1 | 2 | 0 | 0 | 2 | 2 |
<!-- END 7CBD_ACCOUNT -->

账本 `launch_account.csv` 16 行 = 8 预检 + 8 DUT，D001…D016 无跳号，上限 20、余 4；
每次启动都先持久 `REQUESTED` 再进进程，失败不退额。D001 的 `state` 记为 FAILED 而 `rc=0`：那是
入口把运行器应答按整数比较造成的标签缺陷（进程本身成功，判据见
`D001_label_attestation.json`，行字节未改、原始 607 字节另存 `launch_account_as_first_written.csv`）。
紧随其后的那次调用在读表时崩溃——崩溃在 `reserve()` 之前，因此**没有起进程、没有花额度**。

## 7 冻结面与区间

<!-- BEGIN 7CBD_FROZEN -->
| 面 | 期望 | 强制 | 路径数 | 一致 | 失配 | 细节 |
|---|---|---|---:|---:|---:|---|
| four candidate DUT netslists | `identical` | yes | 4 | 4 | 0 | none; empty-name misses none |
| fifteen delivered PREP decks | `identical` | yes | 15 | 15 | 0 | none; empty-name misses spectre/dd1_d7c_b_prep |
| schedule windows and pwl tables | `identical` | yes | 4 | 4 | 0 | none; empty-name misses tests/dd1_d7c_b_prep |
| shared executors and measurement cores | `identical` | yes | 15 | 15 | 0 | none; empty-name misses none |
| preparation contract json | `identical` | yes | 1 | 1 | 0 | none; empty-name misses none |
| earlier records; reports and handoffs | `none_removed` | yes | 31 | 31 | 0 | none; empty-name misses results/evidence/dd1_d7c_b_prep,results/evidence/dd1_d7c_b_prep_r1,results/evidence/dd1_d7c_b_pr |
| modified files against the registered offline commit | `only_allowed_new` | yes | 2 | 2 | 0 | reports/dd1_d7c_b_prep_contract.md,scripts/dd1_d7c_b_prep_contract.py |
| paths added by this round | `only_allowed_new` | yes | 103 | 103 | 0 | unexpected: none |
| paths removed against the registered offline commit | `none_removed` | yes | 0 | 0 | 0 | none |
<!-- END 7CBD_FROZEN -->

<!-- BEGIN 7CBD_RANGES -->
| 区间 | 新增 | 改动 | 删除 | 重命名 | 提交 |
|---|---:|---:|---:|---:|---:|
| `P_to_R1_recomputed` | 23 | 26 | 0 | 0 | 5 |
| `R1_to_base` | 47 | 5 | 0 | 0 | 7 |
| `base_to_HEAD` | 103 | 2 | 0 | 0 | 13 |
<!-- END 7CBD_RANGES -->

被登记的离线内容之后，本轮真正改动的既有文件只有 §6 里那份复审点名要修的两个
（`scripts/dd1_d7c_b_prep_contract.py` 的 µA 换算与 `reports/dd1_d7c_b_prep_contract.md` 的重渲染）；
四份候选 DUT、15 份交付 deck、三张时序表、旧合同 JSON、共享工具与所有旧记录逐 blob 相同。

## 8 拒收与自证

`--selftest` 的 35 例全是离线合成、不起进程、不花额度：完美阶梯 PASS、整体减半的阶梯被绝对判据
判 FAIL 而比例判据仍 PASS（归一化救不了）、非单调被点名、负读数保持为负、缺点/重复点/无探针列/
无单位轴一律具名拒收、未授权调用在写任何文件之前拒、环境变量不能抬上限、失败仍占额、重开不退款、
被多余分隔符撕开的行读不回、带逗号的字段写不出、µA 列的渲染守卫。

## 9 本轮没有做也没有声称

未做瞬态、PWM/PAM 联合电荷、灰阶 LUT、完整 MOS 灰阶控制器、阵列、版图、SOA 评估；
`OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED`；`MERGE_PERFORMED=NO`；未推 `main`；未登记除
`e51c532…` 的 PAM 候选与离线准备之外的任何版本；不追认 DATA-7B 的 59/56 超量与凭据回显事件。
本轮的电压区间只说明"在这 19 个已测点上 ±5% 成立"，不等于 LED/电极的 RC 或 SOA 已验证。
原生语法只对**实际跑过的**派生 DC deck 得到确认，不外推到整个层级，也不外推到瞬态。

```text
TASK_ID=DATA-7C-B-DC
BASE_OFFLINE_CONTENT_SHA=e51c5320a28bd5043e21d08a0be97e9d5612cd16
SPECTRE_LIMIT=20
ACTUAL_SPECTRE_LAUNCHES=16
PAM_8LEVEL_DC_TT=PASS
COMPLETION_LEVEL=NATIVE_PAM_DC_TT_MEASURED
CANDIDATE_DUT_CHANGED=NO
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
PWM_PAM_TRANSIENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
