# DATA-7C-B-DC-R1：有符号判据、必需观察、完整矩阵前置与发布身份的离线修补

本轮不重跑电路，也不改电气判据。独立复审对已提交的 152 条 DUT 行与 152 条预检行做了 Decimal 独立复算并判 PASS，
本轮要修的是**工具与发布身份**：判据的符号、必需信号缺失时的兜底、完整矩阵的前置验证，以及记录绑定的是磁盘字节还是 Git blob。
任务书 `reports/tasks/DATA-7C-B-DC-R1.md` 固定 `NEW_SPECTRE_LAUNCHES=0`、`NEW_RTL_SIMULATIONS=0`、`NEW_OA_WRITES=0`、
`NEW_SSH_OR_VM_ACTIONS=0`，本轮全程未接触 guest、PDK、凭据或 license。

```text
TASK_ID=DATA-7C-B-DC-R1
BASE=337563fc22699e480bf7fc82890750c126a50654          （上一轮 DATA-7C-B-DC 的回执 tip，本轮从这里切出）
OLD_OFFLINE_BASE=e51c5320a28bd5043e21d08a0be97e9d5612cd16（用户登记的限定接受内容，仍是 deck 与冻结面的来源）
BRANCH=poc/data-pam-d7c-b-dc-r1
RECORD_DIR=results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe
REPAIR_SCOPE=OFFLINE_DC_MEASUREMENT_AND_IDENTITY_ONLY
```

## 1. 先在未改的 BASE 上复现

复现仪器按原字节使用（`reviewer_inputs/probe_dc_review_gaps.py`，sha 见 `reviewer_inputs/review_package_identity.json`），
在未修改的 BASE 检出上运行：

```text
python probe_dc_review_gaps.py --repo <BASE checkout> --out baseline_probe.json
rc=0，any_defect_reproduced=true，reproduced_count=7/7，positive_control.complete_required_signal_fixture_accepted=true
```

`rc=0` 在这台仪器里表示"至少检出一个缺陷"，不是 PASS，所以逐项读了字段：反向低压点仍算带内、8 行表被 judge 判 PASS、
vdd18/vcas/data_en 缺失被补成 1.800、pam0 缺失把 code 从 case 名补成 000、131 条身份里两张 SVG 与 Git blob 不符。
两份产物（JSON 与 stdout）随记录发布，包外的复审对照表在 `checks/`。

## 2. 四组缺口的根因、修改与修后字段

### F1 有符号 ±5% 区间

- 根因：`band_of()` 写成 `abs(abs(current) - abs(target)) <= limit`，与它自己声明的判据
  `abs(I(clamp) - I(1.2 V)) <= 5% * abs(I(1.2 V))` 不等价——把电流翻负，差值仍是 0，反向点被当成同值收进带内。
- 修改：核心改回 `limit = fraction * abs(target_A)` 与 `good = {v: abs(i - target_A) <= limit}`；
  并在取带之前先拒非有限点（NaN/Inf 不再靠"比较结果为 False"混成普通带外点）；读数一律保符号，不 `abs()` 翻正。
- 修后字段（同一台仪器）：`opposite_sign_at_0p60V_counted_inside_signed_5pct_band.defect_reproduced=false`，
  八码的 `lowest_verified_V` 全部从 0.60 收到 0.65、`adjacent_failing_V` 点名 0.60，主评价点判据不变、verdict 仍 PASS。
  未改的表仍读 0.60..1.50，说明修的是符号而不是把区间收紧。合成正反例 `--selftest` 里
  `a_signed_over_band_point_narrows_the_measured_interval`、`a_mid_scan_break_splits_the_interval_at_a_measured_point`、
  `a_non_finite_point_is_not_an_ordinary_band_failure`。

### F2 必需原生信号不得用合同值或 case 名兜底

- 根因：`extract()` 里 `'vdd18_V': cols['vdd18'][i] if 'vdd18' in cols else criteria()[0]['vdd18_V']`（data_en 甚至拿的是
  `vcas_V` 的合同值），`pam0/1/2` 缺失时 `pam_bits='NOT_OBSERVED'` 而 `code` 从 case 名补出来，判据里用 `> 0.9` 把任意
  中间电平当高电平。
- 修改：在构造任何行之前要求 axis、探针电流、`data_out`、`vss`、`vdd18`、`vcas`、`data_en`、`pam0/1/2`、`iref_in`
  全部真实存在，并核对各自的声明单位（电压 V、电流 A）、列长与全列有限性；逐点把测得电平与**本 case 冻结 deck** 的
  静态源比对（供电 1.8 V、VSS 显式 0 V、DATA_EN 与三个 PAM 位按高 1.8 V／低 0 V 两个窗口判，中间值直接拒收）；
  实测码位必须同时等于 deck 驱动的码与 case 名所指码；`data_out` 必须跟着被扫的夹持节点；
  deck 摘要与本例应使用的那份 deck 不符即拒收（预检比的是派生预检副本，DUT 比的是交付 deck）。
  `iref_source_A`、`corner`、`temp_C` 改为**从 deck 读出并标成 deck 条件**，`iref_node_V` 才是原生观测，
  来源区分写在返回值的 `origin_rule` 里。
- 修后字段：`missing_required_{vdd18,vcas,data_en,pam0}_accepted_by_extraction` 四项 `defect_reproduced=false`，
  每项的 `observed.refusal` 逐字点名缺的信号；complete fixture 的正例仍返回 19 行。
  `--selftest` 另加 9 个必需列缺失例、错单位例、供电与 deck 不符例、0.9 V 中间电平例、码位与 case 不符例、
  输出跟不住夹持例、deck 摘要错配例，以及"拒收不得写进已有输出的目录"（`--extract` 拒收后目录摘要逐个不变）。
  本轮用同一套必需集重读了本机保存的 8 份 DUT 原生答案（`observed_signals.json` 显示每例 41 列、必需集齐全、
  verdict PASS），因此**现有表的供电、使能、码位、参考节点都是实测值**这一条现在是工具强制的，不是手写声明。

### F3 任何完整阶段 PASS 之前先验证整张矩阵

- 根因：`judge()` 只要八个码各有 1.20 V 点就算 PASS，`--judge` 入口和 `matrix judge` 都不检查 8×19=152 的 key 全集。
- 修改：新增纯函数 `validate_dc_matrix()`（精确 key 全集、每行 role／case／code／pam_bits 一致、单位、有限数、
  uA 与 A 的换算一致、digest 非空、缺点/重复/额外/未知码/缺列全部拒收），接进 `judge()`、公开 `--judge` 与
  `matrix check`；八主点算术抽成 `main_point_arithmetic()`，它**不返回 verdict**，返回字典里没有 `verdict` 键。
- 修后字段：`eight_rows_accepted_by_judge_as_PASS.defect_reproduced=false`，observed 是 refusal 文本；
  `--judge` 对 8 行表答 rc=1 并打印 `DC_JUDGE_REFUSED`，对完整表仍 rc=0；
  `--selftest` 里 7 个矩阵变形全部在矩阵门前被拒（少一行、多一点、重复替换缺点、非有限、单位空、缺列、未知码），
  且负电流不翻正（`a_negative_reading_stays_negative_and_is_not_abs_flipped`）。
  判据本身未动：满量程 14.25–15.75 µA、`Iunit_ref = I111/8`、0.25 个单位的偏差限、严格单调、
  低夹持区间失败不等于 1.20 V 主点失败。
  行表里 `run_id=manual`/`launch_id=D000` 的历史事实**不改写**，另发 `extraction_identity_resolution.csv`
  用 `(case_id, role, deck_sha256, raw_sha256)` 唯一映射到账本里真实的 16 个 `run_id`/`launch_id`；缺失或一对多都拒收。

### F4 发布身份必须就是 Git 字节

- 根因：记录把**工作副本**的字节数与摘要写进 `source_identity.csv`，而 Windows 上那份 SVG 在磁盘上是 CRLF、
  进 Git 被归一成 LF，于是两条身份永远无法从 blob 复现（45,208 vs 44,364；19,316 vs 18,923）。
- 修改：`identity_rows()` 一律从 blob 取字节（`git cat-file blob :<path>`，即本条提交将要携带的字节），
  表格新增 `identity_source` 列；工作副本再也不是身份来源。新增 `--verify-committed <rev>`：提交后把每条身份行
  与 `git cat-file blob <rev>:<path>` 重算比对。旧记录不覆写、不搬动，`stale_fields_of_the_earlier_record.json`
  点名这两行、机械证明"记录值＝blob 的 CRLF 形态"，并说明本轮接替哪部分（图不重画、不重跑，直接引用 BASE 的 LF 字节）。
- 顺带修的显示错误：`record.py` 的 dc_judgement 门把 A 乘 `1e9` 却标成 µA，大了 1000 倍；
  现为 `1e6`，精确正例 `9.1175e-13 A -> 9.1175e-07 µA`（本轮实测最大残差即此值，等于 4.741688622672253e-07 个
  `Iunit_ref`）。judgement 里的 A 值未改。
- `observe()` 的空洞：没有任何原生答案时以前会写 verdict PASS；现在逐例 `NOT_OBSERVED`、整体 `NOT_RUN`、
  rc=3，且不再写观测 PASS。本轮的 PASS 观察是从本机保存的 8 份 `.raw` 读出来的，来源与摘要记在
  `observation_provenance.json`，`.raw` 本身不入仓库也不入包。
- 旧负结果如实更正：`git diff --check e51c5320..337563f` 实测 **rc=2、378 处行尾空白**（`git_checks.csv` 里的
  lines=756 是该检查的输出行数：每处一条位置行加一条引用行），分布在两份原样归档的前轮
  审查日志、两张 SVG、本轮 commands.csv 与一份历史 commands.csv；上一轮报告与回执把它写成 0，是错的。
  为不清零这些已发布字节，本轮只在 `git_checks.csv` 里按实际 rc 记录，并保证**本轮自己的改动区间**
  （`git diff --check --cached` 与 `BASE..HEAD`）为 rc=0。没有改 Git 的 whitespace 规则或属性。

## 3. 电气结果：表未重跑，数值不变

`judgement.json` 由修好的工具在逐字节复用的 152 行上重算，A 值与上一轮发布的一致；最大残差的**单位**按上文更正。

| 码 | I(1.20 V) / A | I(1.20 V) / µA | 名义 / µA |
|---|---|---|---|
| 000 | 1.922839108e-06 | 1.922839 | 1.875 |
| 001 | 3.845677157e-06 | 3.845677 | 3.750 |
| 010 | 5.768515211e-06 | 5.768515 | 5.625 |
| 011 | 7.691353271e-06 | 7.691353 | 7.500 |
| 100 | 9.614191336e-06 | 9.614191 | 9.375 |
| 101 | 1.153702941e-05 | 11.537029 | 11.250 |
| 110 | 1.345986748e-05 | 13.459867 | 13.125 |
| 111 | 1.538270557e-05 | 15.382706 | 15.000 |

满量程在 14.25–15.75 µA 带内、`Iunit_ref` 为 I111/8、严格单调、逐档偏差远小于 0.25 个单位——
这些结论的性质不变：来自同一批名义器件在 TT/27 °C 的确定性模型，不是失配、Monte Carlo、PVT、量产精度或光学位数的证明。

### 闸表（由记录填写）

<!-- BEGIN 7CBD_GATES -->
| 门 | 命令 | rc | 期望 | 判决 | 依据 |
|---|---|---|---|---|---|
| `dc_offline_selftest` | `python dd1_d7c_b_dc_run.py --selftest` | 0 | 0 | PASS | DC_SELFTEST: PASS (62/62 named exactly, failures: none, evidence OFFLINE_NO_PROCESS) |
| `preparation_contract_selfcheck` | `python dd1_d7c_b_prep_contract.py --check` | 0 | 0 | PASS | D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=26 problems=0) |
| `preparation_schedule_check` | `python dd1_d7c_b_prep_schedule.py --check` | 0 | 0 | PASS | D7C_B_SCHEDULE_CHECK: PASS (rows=15 windows=143 pwl=300 problems=0) |
| `preparation_deck_check` | `python dd1_d7c_b_prep_deckgen.py --check` | 0 | 0 | PASS | D7C_B_DECKGEN_CHECK: PASS (15 decks, problems=0) |
| `preparation_deck_reader` | `python dd1_d7c_b_prep_r1_deck_read.py --check` | 0 | 0 | PASS | D7C_B_PREP_R1_DECK_READ: PASS (15 decks, problems=0) |
| `preparation_synthetic_cases` | `python dd1_d7c_b_prep_cases.py` | 0 | 0 | PASS | D7C_B_PREP_CASES: PASS (31/31 named exactly, failures: none, evidence SYNTHETIC_NOT_MEASURED) |
| `candidate_offline_checks` | `python dd1_d7c_a_offline_check.py` | 0 | 0 | PASS | D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none) |
| `candidate_counterexamples` | `python dd1_d7c_a_guards.py` | 0 | 0 | PASS | D7C_A_GUARDS: PASS (65/65 named exactly; not hit: none) |
| `earlier_handoff_binds_its_own_bytes` | `python dd1_d7c_b_prep_r2_verify.py --handoff-check` | 1 | 1 | PASS | rc=1 by design: the R2 handoff digests the bytes of its own round, and the rounds since then legitimately moved reports/dd1_d7c_b_prep_contract.md, scripts/dd1_d7c_b_prep |
| `internal_observations_recorded` | `in process: read observed_signals.json, written by dd1_d7c_b_dc_matrix` | 0 | 0 | PASS | every required signal (data_out, clamp_node, the supplies, the three PAM bits, the reference node and vss) is present in all 8 answers read from native text; the deck ask |
| `dc_handoff_structure` | `in process: handoff_check() over DATA-7C-B-DC.json against the record,` | 0 | 0 | PASS | fields, per-code uA re-derived from judgement.json, account labels and costs agreeing, digests against disk, markers, no self-listing |
| `dc_matrix_shape` | `python dd1_d7c_b_dc_matrix.py check <evidence>` | 0 | 0 | PASS | DC_MATRIX_CHECK: PASS (152 dut rows, 152 preflight rows, unique keys 152 of 152, problems: none) |
| `dc_judgement` | `python dd1_d7c_b_dc_matrix.py judge <evidence> then read judgement.jso` | 0 | 0 | PASS | I111 15.382706 uA band [14.25, 15.75]; Iunit_ref 1.922838 uA; monotonic True; ratio True; worst deviation 9.117499998e-07 uA; bands contain 1.20 V for all eight codes; th |
| `launch_account_reconciles` | `in process: read launch_account.csv, require one preflight and one dut` | 0 | 0 | PASS | 16 rows, ceiling 20, remaining 4, one preflight + one dut per case, every raw paired |
| `every_published_json_parses` | `in process: json.loads over every .json this round publishes` | 0 | 0 | PASS | 10 files parse |
| `record_line_endings` | `scan every published table for CR and round-trip a comma-and-quote row` | 0 | 0 | PASS | published files with CR: none; writer emits LF (confirmed) |
| `unauthorised_refusal_writes_nothing` | `python dd1_d7c_b_dc_run.py --launch DC-000 --role dut --out <temp> (wi` | 0 | 0 | PASS | rc=5 evidence_dir_created=False refusal=DC_LAUNCH {"case_id": "DC-000", "process_started": false, "refusal": "DATA-7C-B-DC: this call is not |
| `ceiling_refusal_before_a_process` | `in process: Account(ceiling=1) reserve, settle, reserve again` | 0 | 0 | PASS | LAUNCH_CEILING_REACHED: the account already carries 1 of 1 launches; a failure costs the budget and recovery n |
| `judgement_cannot_be_normalised_into_a_pass` | `python dd1_d7c_b_dc_run.py --selftest (case a_uniformly_short_ladder_i` | 0 | 0 | PASS | a half-height ladder reads FAIL on the absolute test while the ratio test passes, which is the pair the task book requires together |
| `f1_signed_band_keeps_the_direction_of_a_reading` | `in process: judge the 152 published rows, then the same table with the` | 0 | 0 | PASS | signed criterion abs(I - I(1.2 V)) <= 0.05 * abs(I(1.2 V)): 8 of eight codes now narrow to 0.65 V with 0.60 V named as the adjacent failing point, the main 1.20 V verdict |
| `f2_a_missing_required_signal_is_a_refusal` | `in process: synthetic_psf with one required column removed at a time, ` | 0 | 0 | PASS | complete fixture gives 19 rows, code 000 from the columns and 000 from the deck; 10 of 10 required signals (axis probe included) refused by naming the signal, no nominal  |
| `f3_every_complete_pass_path_validates_the_matrix_first` | `in process: judge() over the 152 rows, over eight rows, and over seven` | 0 | 0 | PASS | the eight-row table is refused at the public --judge entry (rc=1), the full table judges PASS (rc=0), 7 of 7 mutations refused at the matrix gate (all named), and negatin |
| `f4_identity_rows_are_blob_bytes_and_the_stale_two_are_named` | `in process: re-derive the two figure digests from the committed LF blo` | 0 | 0 | PASS | the two figures a reviewer cannot reproduce from Git are exactly the CRLF rendering of the LF blob (2 paths named, 45208 bytes recorded against 44364 blob bytes); this re |
| `f5_the_saved_answers_still_extract_to_the_published_rows` | `python dd1_d7c_b_dc_run.py --extract <saved raw> --deck-sha <published` | 0 | 0 | PASS | 16 of 16 case/role answers re-extracted with the hardened extractor, 0 field differences against the published rows, 0 refusals (none); the native answers themselves are  |
| `f6_every_row_resolves_to_one_accounted_launch` | `in process: join (case_id, role, deck_sha256, raw_sha256) of the publi` | 0 | 0 | PASS | 16 distinct native sources carry the 304 published rows, every one of them exactly one accounted launch; no gap |
| `f7_an_answer_that_is_not_here_is_not_a_pass` | `python dd1_d7c_b_dc_matrix.py observe <empty dir>` | 0 | 0 | PASS | a directory without native answers now answers verdict NOT_RUN and rc 3 with all eight cases NOT_OBSERVED; the required signals are never inferred from a table of nothing |
| `f8_the_microamp_field_is_microamps` | `in process: format the worst residual with the published coefficient, ` | 0 | 0 | PASS | the exact positive case 9.1175e-13 A prints as 9.117500000e-07 uA; the worst residual of this round, 9.117499998e-13 A, prints as 9.117499998e-07 uA, while the earlier 1e |
| `provenance` | `python scripts/provenance_check.py` | 0 | 0 | PASS | SOURCE_PROVENANCE_CHECK: PASS |
| `history_safety` | `python scripts/precommit_safety_check.py --mode history` | 0 | 0 | PASS | SAFETY_GATE: PASS |
| `frozen_surfaces` | `in process: blob and mode comparison over explicit path lists against ` | 0 | 0 | PASS | enforced rows 13, violations 0, informational 0; details on the violating rows: none |
<!-- END 7CBD_GATES -->

### 阶梯与区间（由记录填写）

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

### 冻结面（由记录填写）

<!-- BEGIN 7CBD_FROZEN -->
| 面 | 期望 | 强制 | 路径数 | 一致 | 失配 | 细节 |
|---|---|---|---:|---:|---:|---|
| four candidate DUT netslists | `identical` | yes | 4 | 4 | 0 | none; empty-name misses none |
| fifteen delivered PREP decks | `identical` | yes | 15 | 15 | 0 | none; empty-name misses spectre/dd1_d7c_b_prep |
| schedule windows and pwl tables | `identical` | yes | 4 | 4 | 0 | none; empty-name misses tests/dd1_d7c_b_prep |
| shared executors and measurement cores | `identical` | yes | 15 | 15 | 0 | none; empty-name misses none |
| preparation contract json | `identical` | yes | 1 | 1 | 0 | none; empty-name misses none |
| earlier records; reports and handoffs | `none_removed` | yes | 34 | 34 | 0 | none; empty-name misses results/evidence/dd1_d7c_b_prep,results/evidence/dd1_d7c_b_prep_r1,results/evidence/dd1_d7c_b_pr |
| the measured DC round: tables, record, report and handoff | `identical` | yes | 51 | 51 | 0 | none; empty-name misses results/evidence/dd1_d7c_b_dc_r20261026_015212_376554 |
| the DC round report and handoff | `identical` | yes | 4 | 4 | 0 | none; empty-name misses none |
| the six masters and eight derived preflight decks of the DC round | `identical` | yes | 15 | 15 | 0 | none; empty-name misses spectre/dd1_d7c_b_dc |
| the DC contract of the measured round | `identical` | yes | 1 | 1 | 0 | none; empty-name misses none |
| modified files against the registered offline commit | `only_allowed_new` | yes | 0 | 0 | 0 | none |
| paths added by this round | `only_allowed_new` | yes | 0 | 0 | 0 | unexpected: none |
| paths removed against the registered offline commit | `none_removed` | yes | 0 | 0 | 0 | none |
<!-- END 7CBD_FROZEN -->

### 范围计数（由记录填写；e51c532..337563f 是上一轮的原生档，本轮区间单列）

<!-- BEGIN 7CBD_RANGES -->
| 区间 | 新增 | 改动 | 删除 | 重命名 | 提交 |
|---|---:|---:|---:|---:|---:|
| `BASE_to_HEAD_this_round` | 0 | 0 | 0 | 0 | 0 |
| `P_to_R1_recomputed` | 23 | 26 | 0 | 0 | 5 |
| `R1_to_base` | 47 | 5 | 0 | 0 | 7 |
| `e51c532_to_BASE_measured_round` | 115 | 2 | 0 | 0 | 15 |
<!-- END 7CBD_RANGES -->

### 十六次启动的账本（复用，未改写）

<!-- BEGIN 7CBD_ACCOUNT -->
| 例 | 预检行 | DUT 行 | CONFIRMED | FAILED | UNCERTAIN | raw 配对 | log 配对 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `DC-000` | 1 | 1 | 1 | 1 | 0 | 0 | 2 |
| `DC-111` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
| `DC-001` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
| `DC-010` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
| `DC-011` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
| `DC-100` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
| `DC-101` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
| `DC-110` | 1 | 1 | 2 | 0 | 0 | 0 | 2 |
<!-- END 7CBD_ACCOUNT -->

## 4. 同一轮的验证清单

- `--selftest` 62 例（原 35 例适配 + 本轮新增 27 例）全部按名检出，无失败，全程离线不起进程。
- 前轮套件不退步：`dd1_d7c_b_prep_cases.py` 31/31、`dd1_d7c_a_offline_check.py` 34 项、
  `dd1_d7c_a_guards.py` 65 反例、`dd1_d7c_a_r2_record_probes.py` 14 探针、合同/日程/15 deck/读盘检查全 PASS。
- 六份母本的 63 行端口方向标注剥离结果与提交逐字节一致（`--masters`），派生预检 deck 可从交付 deck 重推。
- 账本读取 16 行、`extraction_identity_resolution.csv` 16 个来源唯一、304 条行（DUT+预检）全部配对成功。
- 冻结面：BASE 的 152 条原生行、16 行账本、15 份 PREP deck、4 份候选 DUT、6 份派生母本与 8 份派生预检 deck、
  旧记录/报告/交接、共享工具与旧合同——blob 与 mode 逐条比不变；本轮只动了三个 DC 脚本。
- Git 安全闸：`precommit_safety_check.py --mode history`、`provenance_check.py`、凭据/私钥/厂商模型三类
  tracked 文件计数为 0。

## 5. 交付与可复核边界

- 本轮产物：三个 DC 脚本的修补、`results/evidence/dd1_d7c_b_dc_r1_<run_id>/`（复用声明、重算判定、
  身份解析表、旧记录过期字段、本机答案的观察与来源、复审仪器原字节与 BASE 复现结果）、
  本报告与 `reports/agent_handoffs/DATA-7C-B-DC-R1.{json,md}`、任务书副本。
- 记录身份表全部来自将要提交的 Git blob；提交后再用 `--verify-committed <tip>` 把每一行与
  `git cat-file blob <tip>:<path>` 重算比对，其输出与"抽到仓库外空目录重放"的 expected/actual rc
  记在后续提交与回执里，不写进被摘要的文件本身。
- 原始 `.raw`/`.log` 按上一轮任务书留在执行机，不进仓库也不进包；本轮**能**独立复算的是提交表里的数值、判据、
  身份与账本关系，以及从本机保存答案重读的观察，不能声称云端从原始 PSF 重提取过电流。
- 凭据与历史预算事件仍未解除：本轮没有读取凭据、没有进入 guest、没有动用上一轮余下的 4 次额度；
  DATA-7B 的 59/56 与历史凭据事件不在本轮处理范围。

## 6. 回执

```text
PAM_8LEVEL_DC_TT=PASS
COMPLETION_LEVEL=NATIVE_PAM_DC_TT_MEASURED
REPAIR_SCOPE=OFFLINE_DC_MEASUREMENT_AND_IDENTITY_ONLY
ORIGINAL_152_NATIVE_ROWS_CHANGED=NO
ORIGINAL_NATIVE_ACCOUNT_CHANGED=NO
CANDIDATE_DUT_CHANGED=NO
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
NEW_SSH_OR_VM_ACTIONS=0
PWM_PAM_TRANSIENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
ACCEPTANCE_REGISTERED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

## 7. 交给审核人的判读点

1. F2 的必需集是否够：本轮把 `vss` 也列为必需（deck 显式 0 V 源），并把 `data_out` 与夹持节点的一致性容差定在
   20 mV（工具护栏，不是电气结论）。若你认为该容差应更严或应改判为"逐点等于夹持"，请点名期望值。
2. F3 的矩阵门现在拒绝任何不完整表；`--selftest` 里主点算术函数与完整判定的分工是否符合你对"不能冒充阶段 PASS"的预期。
3. 旧记录的两条 SVG 身份：本轮选择"保留旧记录 + 新记录接替 + 机械证明 CRLF 根因"，而不是回填旧表。
   如果你更希望旧记录目录内出现一份指向本轮的更正便条，请说明放置路径与允许的字面内容（那会新增一次提交）。
