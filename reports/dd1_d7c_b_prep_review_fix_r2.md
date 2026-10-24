# DATA-7C-B-PREP-R2 修补报告（合同状态 `PROPOSED_FOR_REVIEW`，不是 `USER_APPROVED`）

本轮是 **DATA-7C-B-PREP-R2**：按对 R1 字节的独立复审，只修**瞬态电荷归一化所用的参考 tick** 这一项，
附带 §6 的三处说明性更正。不重做电路、PWL、窗口与历史工具，也不进入原生阶段。

## 1 身份、授权与硬边界

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/LINboss666/microled-ic-ai-lab` |
| 本轮基线 R1 | `6778535e70b139812265eba490d0a1381a1fae5c`（被审 tip，四族已闭合的那份字节） |
| 原 PREP P | `dcef9b336f2222d6291d266858270f7448b6bb78`；R2 `3e4703f1763223024f442c0826e95055782bca13`；`main` `23e471cb936b421ee97e1250c3be06edf96f9937`（本轮都不动） |
| 新分支 / 工作树 | `poc/data-pam-d7c-b-prep-r2` / `D:\ic617_d7c_b_prep_r2`（自 R1 SHA 新建） |
| 任务书 | `reports/tasks/DATA-7C-B-PREP-R2.md`，8,609 B，sha256 `cf876e96aad39fac087845adc13854f9a0effdce295865f72dc23567736807e9`，与 Downloads 原件逐字节相同（0 个 CR），并与审核包内同名成员一致 |
| 审核包 | `MicroLED_DATA7C_B_PREP_R1_Independent_Review_20261024.zip` 37,295 B，sha256 `a040c2cb0246d7a411f135eca0021ffb12a508eb3818f1a327cdd9298c075298`；`MANIFEST.csv` 29 行全部按 bytes+sha256 校验通过，解包后无未列文件 |
| 两份仪器 | `reviewer/probe_tick_normalisation.py` 4,065 B `3b970d0fcff5d3f6…`；`reviewer/probe_prep_gaps.py` 11,024 B `d981ff190a627ae7…`；**字节与判据都未改**，本轮只做 rc=0（复现）→ rc=1（不再复现）的对照 |
| 评审结论 | `REVIEW_RECOMMENDATION=REWORK`、`REPAIR_SCOPE=TRANSIENT_Q_LSB_REFERENCE_ONLY`、`PREVIOUS_F1_TO_F4_DIAGNOSTICS=CLOSED`、`DC_BENCH_OFFLINE_PREPARATION=PASS`、`CANDIDATE_DUT_REDESIGN_REQUIRED=NO`、`NATIVE_EXECUTION_AUTHORISED=NO` |

授权上界（本轮自证）：`NEW_SPECTRE_LAUNCH_LIMIT=0`、`NEW_RTL_SIMULATION_LIMIT=0`、`NEW_OA_WRITE_LIMIT=0`、
`SSH_VM_PDK_MODEL_CREDENTIAL_ACCESS_AUTHORISED=NO`、`NATIVE_PREFLIGHT_AUTHORISED=NO`、
`ACCEPTANCE_REGISTRATION_AUTHORISED=NO`、`MERGE_OR_MAIN_PUSH_AUTHORISED=NO`、
`NEXT_NATIVE_STAGE_AUTHORISED=NO`。0 含帮助命令、语法试跑、其它仿真器与旧仿真重跑；未读凭据/模型卡/许可证、
未连 guest；未 force、未跳 hooks、未 GC、未改历史、未改仓库可见性；36 次发射仍是草案。

## 2 修改前：缺陷在未改动的 R1 archive 副本上逐项复现

入口：`python reviewer/probe_tick_normalisation.py --root <R1 archive 副本> --out <新的 JSON>` → **rc=0、
`defect_reproduced=true`**（rc=0 只表示误判复现，不是验收）。读回的具体字段：

| 量 | R1 交付入口实际给出 | 合同自己列出的两个名义 tick 应为 |
|---|---|---|
| 全使能窗 T50（TR-LONG 码 111） | 1e-06 s | — |
| 当作 QLSB 分母的 tick | **1e-06 s**（就是窗长本身） | 1.2e-07 s 或 2e-07 s |
| QLSB | 1.875e-12 C | 2.25e-13 C / 3.75e-13 C |
| 多余电荷 | +4.99999999999995e-13 C | 同（注入 0.5 pC） |
| 误差 | **0.266667 LSB，`WITHIN_PROPOSED_LIMIT`** | 2.222222 / 1.333333 LSB，都应越 0.5 限 |

同一副本上旧四族仪器仍 rc=1、`all_four_families_reproduced=false`，逐项 F1..F4 都是 false——
本轮的修补不得动这个结论，`old_four_families_still_closed` 门就是为此而设。

## 3 修补：参考 tick 是"该例的属性"，不是"该窗的长度"

* 合同唯一来源新增 `rules.charge_error.reference_tick_s_by_case`（§3 表的逐字冻结）：
  `TR-120/RS-LOW/TR-LONG/RS-FULL/TR-OFFCODE/RS-SWITCH = 120 ns`，`TR-200 = 200 ns`，DC 八例不适用；
  名义 tick 列表 120/200 ns 原样保留；`selfcheck` 要求该映射**恰好**覆盖这 7 例、值完整唯一有限且 >0、
  伙伴共享同一 tick，且取值必须来自合同已列的名义 tick。
* 新增 `reference_tick_for_case(case_id, contract)`：未列例、缺失、0、负数、NaN、Inf、非数字都在**任何除法之前**
  具名 `Refuse`，不回退到窗口长度；返回 `(tick_s, 来源串)`，来源串指名"合同里的哪一条"。
* `measure_case()` 现在是 `charge_errors(q_full, nominal_A, t50_s, idc_A, tick_s, …, tick_source)`，
  其中 `t50_s` 只进 `Qexpected_nominal=Inominal(k)×T50`（DC 有实测点时同理 `IDC(k)×T50`，没有仍 `NOT_RUN`），
  `tick_s` 只进 `QLSB=Iunit_nominal×Ttick`；返回条目带 `reference_tick_s`、`reference_tick_source`、`t50_s`
  与 `qlsb_identity`，让人直接看出两个时间没混用。DC 行返回 `qlsb_status=NOT_APPLICABLE_DC_HAS_NO_TIME_DOMAIN`。
* `convergence()` 的配对上下文新增必填字段 `reference_tick_s`，并要求它与用作分母的入参一致：
  两侧一起传入窗长不再能把单位漂移藏进"完全相同"里；分母非正有限数、两侧字段不一致、单侧漂移各自具名拒收，
  一致的粗/细对仍按同一把尺子判定（10 fC 在 120 ns 参考下 0.044444 QLSB > 0.01 判 `OUTSIDE_LIMIT`）。
* 未动清单（可证）：15 份 deck、`schedule.csv`/`windows.csv`/`pwl.csv`、1050 ns 偏移、四个候选 DUT、
  共享工具、PREP/R1 记录与报告与交接。`decks_and_tables_identical_to_R1` 门按 blob+mode 比对，
  `frozen_surfaces` 只允许那五个文件变动。

## 4 正反例：全部通过真实入口

合成族从 25 例增至 **31 例**，新增 6 例（C26–C31）逐条对应任务书 §5：审核的 +0.5 pC 反例经
`measure_case()` 给出 QLSB 0.225 pC、误差 +2.222222 LSB、`OUTSIDE_PROPOSED_LIMIT`；TR-120/TR-200 分别
0.225/0.375 pC 且 TR-LONG 八码共用 0.225 pC（其窗仍是 1 µs）；同一码 120 ns 与 1 µs 两种窗长下期望电荷
按 T50 变、QLSB 不变；27 个发光窗逐例读回 QLSB 全部等于合同映射；0/负/NaN/Inf/缺失/未知 tick 在除法前
具名拒收；收敛的分母与配对不一致时拒收。C16/C21 只补了新必填字段，原有手算电荷、delta 与阈值未改。
所有样点仍是 `SYNTHETIC_NOT_MEASURED`；出现 `OUTSIDE_PROPOSED_LIMIT` 是修正单位后的正常结果，
不是 MOS 电气失败，也不要求合成波形落在电气阈值内。

## 5 附带说明更正（同一轮做完，不另开 DOC 轮）

* 合同渲染器把 `settling.band_fraction=0.05` 显示成"±0.05%"，现按 ±5% 渲染；**数值容差仍是 0.05 比例**，
  判据一字未改（满量程那行原本就是 ±5%，未动）。
* 名义电流表的 SI 列改为逐格带单位（A / fA / µA），不再用等号连接不同单位的裸数字。
* **勘误 R1 报告**：其 §1 表格把 `3e4703f17632…` 称作"继承的已接受 R2"。本轮与历轮都没有获得 R2/接受登记授权
  （`ACCEPTANCE_REGISTRATION_AUTHORISED=NO`），该措辞应读作"继承的基线 R2 提交"。旧报告与旧交接按原字节保留，
  更正只写在这里。
* Git 范围按实际两端重算并写进记录：`P..R1` 为 23 增 / 26 改 / 0 删 / 5 提交（审核方独立重算亦为
  26 改 / 23 增 / 0 删 / 5 提交）；R1 记录当时量到的 7 增 / 3 提交是它自己那一刻的中间值，
  在 `ranges.json` 里单列为 `P..R1_at_R1_record`，不冒充最终范围。

## 6 闸与验收顺序

顺序按 §7：未改 R1 的反例 → 限定五文件的修补 → 新旧正反例 → 合同/日程/deck/独立读盘与 31 例回归 →
冻结比较与已提交区间 `git diff --check` → 新鲜 archive 提取重放（两份仪器都跑在提取里）。
本轮没有跳过的门：共享记录工具自己的自测在被接受的 R2 提交 `3e4703f1…` 的一次性克隆里实跑（本轮没改
任何共享工具，所以它只证明审核用来判本记录的那把尺子仍答得上自己的 9 例；"字节未动"由 `frozen_surfaces`
承担），DATA-7C-A 的 T/H 历史证据不重跑，因为本轮没有任何输入喂给它。记录语义规则仍走共享检查器，
只替换属于旧轮次的门名与仪器文件名并报出替换计数。

<!-- BEGIN 7CB_R2 GATES -->
| 门 | 命令 | rc | 期望 | 判决 | 依据 |
|---|---|---|---|---|---|
| `reviewer_tick_probe_on_R1_base` | `python review/MicroLED_DATA7C_B_PREP_R1_Independent_Review_20261024/re` | 0 | 0 | PASS | defect_reproduced; tick=1e-06 qlsb=1.875e-12 error_LSB=0.2666666666666658 verdict=WITHIN_PROPOSED_LIMIT; contract_ticks=2.22222 LSB,1.33333 LSB; instr |
| `reviewer_tick_probe_on_r2_bytes` | `python review/MicroLED_DATA7C_B_PREP_R1_Independent_Review_20261024/re` | 1 | 1 | PASS | defect_reproduced; tick=1.2e-07 qlsb=2.2499999999999998e-13 error_LSB=2.2222222222222148 verdict=OUTSIDE_PROPOSED_LIMIT; contract_ticks=2.22222 LSB,1. |
| `old_four_families_still_closed` | `python review/MicroLED_DATA7C_B_PREP_R1_Independent_Review_20261024/re` | 1 | 1 | PASS | all_four_families_reproduced; families=1_=closed,2_=closed,3_=closed,4_=closed; all_four=False; instrument sha256 matches the copy in the review packa |
| `reviewer_instrument_bytes_unchanged` | `sha256 of the two instruments on disk against the digests the review p` | 0 | 0 | PASS | probe_tick_normalisation.py=3b970d0fcff5d3f6, probe_prep_gaps.py=d981ff190a627ae7; both runs quote the same digests they computed for themselves |
| `contract_selfcheck` | `python dd1_d7c_b_prep_contract.py --check` | 0 | 0 | PASS | D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=26 problems=0) |
| `schedule_check` | `python dd1_d7c_b_prep_schedule.py --check` | 0 | 0 | PASS | D7C_B_SCHEDULE_CHECK: PASS (rows=15 windows=143 pwl=300 problems=0) |
| `deck_check` | `python dd1_d7c_b_prep_deckgen.py --check` | 0 | 0 | PASS | D7C_B_DECKGEN_CHECK: PASS (15 decks, problems=0) |
| `offline_checks` | `python dd1_d7c_a_offline_check.py --json` | 0 | 0 | PASS | D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none) |
| `counterexamples` | `python dd1_d7c_a_guards.py --json` | 0 | 0 | PASS | D7C_A_GUARDS: PASS (65/65 named exactly; not hit: none) |
| `deck_regenerated` | `python dd1_d7c_b_prep_deckgen.py --to <scratch>` | 0 | 0 | PASS | D7C_B_DECKGEN_REGENERATED 15 decks in a scratch tree, comparison problems=0 |
| `synthetic_measure_cases` | `python dd1_d7c_b_prep_cases.py --json <out>` | 0 | 0 | PASS | D7C_B_PREP_CASES: PASS (31/31 named exactly, failures: none, evidence SYNTHETIC_NOT_MEASURED) |
| `deck_read_still_clean` | `python dd1_d7c_b_prep_r1_deck_read.py --check --counterexample --json ` | 0 | 0 | PASS |   delivered_bytes_control        HIT   delivered TR-LONG and TR-OFFCODE raise 0 edge or leakage refusals: [] |
| `reference_tick_read_back` | `python -c reference_tick_read_back() in process: measure every transie` | 0 | 0 | PASS | 7 cases mapped, 27 windows read, 0 disagreements; DC cases refuse a tick by name; none |
| `decks_and_tables_identical_to_R1` | `git ls-tree -r blob+mode comparison of the 15 decks and the three timi` | 0 | 0 | PASS | 15 decks + 3 tables compared, 0 differ; the reference tick is measurement metadata, so no stimulus, window or 1050 ns offset moved |
| `fresh_extraction_replay` | `git archive d13f494028a9 / tar -x, then run every suite and both revie` | 0 | 0 | PASS | contract_check rc=0 D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=26 problems=0); schedule_check rc=0 D7C_B_SCHE |
| `handoff_structure` | `python dd1_d7c_b_prep_r2_verify.py --handoff-check (in process)` | 0 | 0 | PASS | fields, digests against disk, five editable files, four repairs named, zero costs and no self-listing |
| `native_entry_refused` | `python dd1_d7c_a_deckgen.py --probe <temp>` | 0 | 0 | PASS | DECKGEN_PROBE refused=True untouched=True reason=DATA-7C-A: this round authorises no native launch and no deck publication; NATIVE_AUTHORISED_THIS_ROU |
| `provenance` | `python scripts/provenance_check.py` | 0 | 0 | PASS | SOURCE_PROVENANCE_CHECK: PASS |
| `history_safety` | `python scripts/precommit_safety_check.py --mode history` | 0 | 0 | PASS | SAFETY_GATE: PASS |
| `record_tool_selftest` | `python dd1_d7c_a_r1_selftest.py --json <out>/selftest.json, run in a t` | 0 | 0 | PASS | clone_at_R2 PASS, 9 cases, failures: none; the shared tool is the same blob R2 has=True; source refs unchanged=True; output newlines normalised={'crlf |
| `git_range_counts` | `git diff --name-status and git rev-list --count over P..R1 and R1..HEA` | 0 | 0 | PASS | P..R1 23 added / 26 changed / 0 deleted / 5 commits, which is what the review of R1 recomputed (its own record measured 7 added over 3 commits at that |
| `frozen_surfaces` | `git ls-tree -r blob and mode comparison over explicit path lists again` | 0 | 0 | PASS | enforced rows 10, violations 0, informational 1; added vs R1 5, removed 0, modified 5 (the five editable files); git diff --check max rc=0 |
| `record_line_endings` | `scan every published file for CR and round-trip a comma-and-quote row ` | 0 | 0 | PASS | published files still carrying CR: none; the table writer emits LF (confirmed); instrument JSONs are normalised only after the parsed object is proven |

渲染发生在 `d13f494028a9` 之后、`record_semantics` 与 `published_record_recheck` 判定之前；本表不含本轮记录的摘要。
<!-- END 7CB_R2 GATES -->

<!-- BEGIN 7CB_R2 TICK -->
| 读数（逐项来自仪器 JSON） | R1 基线（未修） | R2 字节（已修） |
|---|---|---|
| 仪器 rc | 0 | 1 |
| defect_reproduced | True | False |
| 入口实际采用的分母 tick (s) | 1e-06 | 1.2e-07 |
| QLSB (C) | 1.875e-12 | 2.25e-13 |
| T50 全使能窗 (s) | 1e-06 | 1e-06 |
| 注入的多余电荷 (C) | 4.99999999999995e-13 | 4.99999999999995e-13 |
| 误差 (LSB) / 判决 | 0.266667 / WITHIN_PROPOSED_LIMIT | 2.22222 / OUTSIDE_PROPOSED_LIMIT |
| 合同两个名义 tick 下应为 | 2.22222 LSB @ 1.2e-07 s; 1.33333 LSB @ 2e-07 s | 同一个 120 ns 参考，即交付值 |

两份仪器都按原字节运行（`3b970d0fcff5` / `d981ff190a62`），rc 只是摘要；上表逐项读自 JSON 字段，修补的判据是 tick/QLSB 真变了并且判决越限，而不是空返回或整片拒收。
<!-- END 7CB_R2 TICK -->

<!-- BEGIN 7CB_R2 TICKMAP -->
| case_id | 参考 Ttick (ns) | QLSB (C) | 发光窗数 | 该例各窗 T50 (s) |
|---|---|---|---|---|
| RS-FULL | 119.99999999999999 | 2.2499999999999998e-13 | 8 | 1000 |
| RS-LOW | 119.99999999999999 | 2.2499999999999998e-13 | 1 | 120 |
| RS-SWITCH | 119.99999999999999 | 2.2499999999999998e-13 | 4 | 300 |
| TR-120 | 119.99999999999999 | 2.2499999999999998e-13 | 1 | 120 |
| TR-200 | 200.0 | 3.75e-13 | 1 | 200 |
| TR-LONG | 119.99999999999999 | 2.2499999999999998e-13 | 8 | 1000 |
| TR-OFFCODE | 119.99999999999999 | 2.2499999999999998e-13 | 4 | 300 |

DC 八例不在表内：合同规定其时域 QLSB 不适用，入口对该情形返回 `NOT_APPLICABLE_DC_HAS_NO_TIME_DOMAIN`。
<!-- END 7CB_R2 TICKMAP -->

<!-- BEGIN 7CB_R2 CASES -->
| 例 | 类型 | 判决 | 观察到的依据 | 说明 |
|---|---|---|---|---|
| C01_positive_sink_charge | POSITIVE | HIT | Q=1.875e-13 C over 100 ns at 1.875 uA, sign SINK_POSITIVE_AS_DECLARED | a 100 ns window at one unit current integrates to the hand-computed charge and reads positive |
| C02_reversed_probe_refused | NEGATIVE | HIT | the same physics on reversed terminals gives Q=-1.875e-13 C; abs() would have made it look identical to the positive cas | turning the ammeter around cannot be rescued by abs() |
| C03_deck_probe_order_named | NEGATIVE | HIT | line 79 became (data_out clamp_node) and the deck audit answered: TR-120.scs writes the probe as "Ip_branch (data_out cl | a deck written with the terminals swapped is refused by the deck audit |
| C04_cancelling_tail_fails | NEGATIVE | HIT | net Q=0 C looks like a shut branch, the magnitude test still says 0.5 uA against a 0.15 uA limit | a tail whose positive and negative halves cancel is not zero leakage |
| C05_quiet_tail_passes | POSITIVE | HIT | max(abs(I))=0.01 uA at 1380 ns inside the last 100 ns, under the 0.15 uA limit | a quiet tail passes and names its sample instant |
| C06_nonuniform_pencil_check | POSITIVE | HIT | Q=1.375e-13 C, boundaries interpolated onto the enclosing pairs | interpolated boundaries over unequal spacing match the arithmetic done by hand |
| C07_adaptive_precision | POSITIVE | HIT | kept 1.99902e+06 ps (quantum 50000 ps), which is the bound a reviewer needs beside the number | a printed simulator time is kept at its own precision with its display quantum reported |
| C08_garbage_named | NEGATIVE | HIT | four bad sample shapes and one edge-less window all refused by name | NaN, a repeated time, a backwards time, an empty list and a missing edge each refuse by name |
| C09_left_band_before_deadline | NEGATIVE | HIT | left the band at 1201.55 ns, held only None ns, deadline 1230 ns | entering the band and leaving early is not a settled window |
| C10_settled_held | POSITIVE | HIT | in band from the edge to the deadline, held 100 ns | staying in band to the deadline is the settled case |
| C11_halved_array | NEGATIVE | HIT | half current gives worst deviation 0 units of Iunit_ref, absolute 7.5 uA against the band 14.25-15.75 uA | eight levels at half current pass the ratio and fail the absolute target |
| C12_code_000_not_black | NEGATIVE | HIT | code 000 = 1 branch, and a ladder missing it is refused by name | the lowest code is one conducting branch and cannot be dropped from the ladder |
| C13_refined_lost_history | NEGATIVE | HIT | the schedule refused it: RS-FULL writes off_window_ns 2100.000-2500.000;3600.000-4000.000;5100.000-5500.000;6600.000-700 | a refined case that dropped the seven earlier platforms is not the same conditions |
| C14_refined_changed_supply | NEGATIVE | HIT | the schedule refused it: RS-LOW differs from TR-120 outside the time step: data_en_level_V | a refined case that also moved the enable level is refused |
| C15_refined_lost_transition | NEGATIVE | HIT | the schedule refused it: RS-SWITCH declares 3 code-change entries for 4 platforms | a refined case that dropped one code change is a different experiment |
| C16_convergence_absolute | NEGATIVE | HIT | delta Q=10 fC = 0.0444444 QLSB against a 0.01 limit; moving the window by 10 ns refuses the comparison | convergence always carries an absolute difference, and a moved window refuses the comparison |
| C17_two_charge_expectations | POSITIVE | HIT | nominal 1.875e-13 C vs DC NOT_RUN; QLSB 2.25e-13 C, error 0 LSB | nominal and DC expectations stay apart and the missing DC point is NOT_RUN, never a geometry guess |
| C18_leak_in_second_tail | POSITIVE | HIT | 8 codes, one 5 uA leak in platform 1: ABOVE_LIMIT at index [1] with max(abs(I)) = 5e-06 A over 100 ns, the other seven W | eight codes measured at once find the 5 uA leak in the second tail and nowhere else |
| C19_full_versus_flat_window | POSITIVE | HIT | full 2.15625e-13 C over 120 ns of enable versus flat 1.875e-13 C over 100 ns of flat part; the difference 2.8125e-14 C i | the full-enable charge and the flat charge are different numbers, each matching its own pencil arithmetic |
| C20_no_edge_refusal_left | POSITIVE | HIT | 27 windows over 7 transient cases measured through the entrance, edge refusals=0, edges off their declared instant=0 | every window of the delivered schedule finds its own interpolated 50% edges on the declared instant |
| C21_missing_context_refused | NEGATIVE | HIT | 6 context fields each refused by name when both sides omitted them; the complete pair converges at WITHIN_LIMIT | convergence refuses when a side does not carry the named context, instead of calling None equal to None |
| C22_leakage_window_refusals | NEGATIVE | HIT | a 10 ns tail refuses as REFUSED_LEAKAGE_OUTSIDE_PURE_OFF and an enable that reaches 1.8 V inside the window refuses as R | a leakage interval that reaches the pure-off start or a rising enable is refused, never shortened to fit |
| C23_dc_expectation_via_entrance | NEGATIVE | HIT | nominal 2.25e-13 C (-0.0416667 LSB) with the DC column NOT_RUN; supplying IDC 2 uA makes the DC expectation 2.4e-13 C, a | through the entrance a missing native DC point stays NOT_RUN while the nominal error is computed |
| C24_decks_read_clean | POSITIVE | HIT | 15 decks read from disk with the reader's own parser, problems=0 | the independent reader opens the fifteen delivered decks and finds nothing to report |
| C25_reader_names_the_shapes | NEGATIVE | HIT | 3 of 3 shapes refused by name on temporary copies (old_long_ramp, leak_window_over_next_rise, delivered_bytes_control) | the old long ramp and leakage over the next rise are refused by name on temporary copies |
| C26_half_pC_is_outside | NEGATIVE | HIT | TR-LONG code 111: T50 1 us stays the window, QLSB 0.225 pC comes from the 120 ns reference tick, error +0.5 pC = 2.22222 | the review +0.5 pC on a 1 us platform reads 2.222222 QLSB and OUTSIDE_PROPOSED_LIMIT through the entrance |
| C27_qlsb_follows_the_case | POSITIVE | HIT | TR-120 0.225 pC, TR-200 0.375 pC, TR-LONG eight codes all on 0.225 pC while its own window is 1 us (10 windows read) | one case keeps one ruler across its codes while TR-200 keeps its own 200 ns ruler |
| C28_expectation_scales_with_t50 | POSITIVE | HIT | 120 ns and 1 us windows of one code: expected 2.25e-13 C versus 1.875e-12 C, QLSB 2.25e-13 C both times, and the deliver | a wider window moves the expected charge and leaves the QLSB where the contract put it |
| C29_all_27_windows_read_back | POSITIVE | HIT | 27 windows across 7 transient and refined cases, every QLSB equal to Iunit x that case reference tick (TR-200=0.375 pC,  | every emission window of the delivered schedule carries its own case QLSB from the contract map |
| C30_bad_tick_refuses_first | NEGATIVE | HIT | 5 bad ticks each refused by name before the division, missing and unknown refuse too, and the DC row reports NOT_APPLICA | zero, negative, NaN, infinity, missing and unknown ticks refuse by name before any division |
| C31_convergence_uses_the_reference_tick | NEGATIVE | HIT | 10 fC over 120 ns is 0.0444444 QLSB against a 0.01 limit; a denominator that disagrees with the pair, a zero ruler and a | convergence divides by the tick the pair carries and refuses a denominator that disagrees with it |
<!-- END 7CB_R2 CASES -->

<!-- BEGIN 7CB_R2 RANGES -->
| 区间 | 新增 | 变更 | 删除 | 重命名 | 提交数 | 说明 |
|---|---|---|---|---|---|---|
| `dcef9b336f22..6778535e70b1`（P..R1，本轮基线区间） | 23 | 26 | 0 | 0 | 5 | 按实际两端 SHA 重算；R1 记录里那次测量（7 新增 / 3 提交）只属于它自己的时刻，不能当作最终范围 |
| `6778535e70b1..HEAD`（R1..本轮） | 5 | 5 | 0 | 0 | 3 | 度量于运行本入口时已提交的 HEAD=d13f494028a9；记录目录本身在下一个提交里 |
<!-- END 7CB_R2 RANGES -->

<!-- BEGIN 7CB_R2 FROZEN -->
| 比较 | 面 | 路径数 | 计数 | 前若干 | 期望 | 计入闸 |
|---|---|---:|---:|---|---|---|
| r2 | `every_R1_path_outside_the_five_editable_files` | 2714 | 0 |  | `identical` | yes |
| r2 | `four_candidate_DUT_netlists` | 4 | 0 |  | `identical` | yes |
| r2 | `fifteen_delivered_decks` | 15 | 0 |  | `identical` | yes |
| r2 | `schedule_windows_and_pwl_tables` | 3 | 0 |  | `identical` | yes |
| r2 | `accepted_DATA7B_measurement_and_run_core` | 3 | 0 |  | `identical` | yes |
| r2 | `shared_tools_safety_and_provenance` | 14 | 0 |  | `identical` | yes |
| r2 | `R1_and_PREP_records_reports_and_handoffs` | 31 | 0 |  | `identical` | yes |
| r2 | `earlier_task_books_and_reports` | 5 | 0 |  | `identical` | yes |
| r2 | `paths_added_this_round` | 5 | 0 |  | `only_allowed_new` | yes |
| r2 | `paths_removed_vs_R1` | 0 | 0 |  | `none_removed` | yes |
| r2 | `paths_modified_vs_R1` | 5 | 0 | reports/dd1_d7c_b_prep_contract.md;scripts/dd1_d7c_b_prep_cases.py;scripts/dd1_d7c_b_prep_ | `informational_listing` | no |
<!-- END 7CB_R2 FROZEN -->

## 7 未做、限制与不写成通过的事

* 本轮只修参考 tick 与三处说明。**没有**新增电气结论：八档电流、电荷、收敛对实测全为 `NOT_RUN`，
  `NATIVE_NETLIST_SYNTAX`/分层 `save` 仍 `NOT_VERIFIED`，模型身份未读卡。
* 120 ns 这个数值是 **POC 测量参考单位**（`POC_MEASUREMENT_REFERENCE_NOT_TCON_NOT_DISPLAY_TIMING`），
  不代表 TCON 或显示帧时序已实现；长窗与 300 ns 换码平台内含多个 tick 这一事实，不把 Ttick 改成 T50。
* `QLSB` 的绝对大小仍会影响越限判定，所以映射改动本身可能让此前"在限内"的合成窗口变为越限——
  这是单位纠正的正常结果，已在 §4 说明，不算失败也不做掩盖。
* 测量核继续复用被接受的 `dd1_d7b_measure`，其精度局限一并继承；本轮没改积分与插值实现。
* DATA-7B 的 59/56 超量、凭据回显事件与更早的待办原样保留，本轮不擅自处置。

## 8 停止条件

`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`。不自签 GO；不跑八例 DC、不把 36 次草案变成授权；
不合并、不动 `main`、不登记接受版本。
