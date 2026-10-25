# DATA-7C-B-PREP 电气合同草案（状态 PROPOSED_FOR_REVIEW，不是 USER_APPROVED）

机读来源：`tests/dd1_d7c_b_prep/contract.json`，由 `scripts/dd1_d7c_b_prep_contract.py` 生成；本文件由同一脚本渲染，任何一处手工改数都会让 `--check` 的固定点比较失败。
基线 R2 = `3e4703f1763223024f442c0826e95055782bca13`，分支 `poc/data-pam-d7c-b-prep-r2`。本轮不运行任何仿真器：Spectre 0 次（含 `-h`）、RTL 仿真 0 次、OA 写入 0 次、动态 preflight 0 次；15 例结果列一律 `NOT_RUN`。

## 1 条件与建议判据

| 项 | 建议值 | 判读方式与限制 |
|---|---|---|
| 工艺角与温度 | TT / 27 °C | 模型身份本轮未读卡，`NOT_VERIFIED_THIS_ROUND`，确切本地模型留给获批原生阶段核验 |
| 供电与参考 | VDD18=1.8 V、VCAS=1.8 V、Iref=1.5e-05 A 外供、VSS 显式接 0 | 参考是 bench 电流计注入二极管连接 Mref 的节点，不是理想 VBIAS；vss 不接地时所有 NMOS 通路不存在（桥手册坑 19） |
| 主评价输出夹持 | 1.2 V | 继承 POC 条件；不代表实际 LED、VLED 或最终 SOA（`POC_CLAMP_CONDITION_NOT_LED_NOT_VLED_NOT_SOA`） |
| 输出夹持扫描 | 0.6–1.5 V，步长 0.05 V | 1.20 V 必须是实际扫描点：网格 19 点，第 13 点即为它 |
| 满堂绝对电流 | 码 111 在 1.2 V 为 1.5e-05 A ±5%（1.425e-05–1.575e-05 A） | 候选可行性目标，不是规格；八档相对比例通过**不能**代替这一条 |
| 八档比例 | `Iunit_ref = I111/8`（同条件 DC 实测），逐档报 `Ik-(k+1)*Iunit_ref` | 建议绝对偏差不超过 0.25 个 Iunit_ref，且八码严格单调；归一基准全表一致，不得逐码换基准 |
| 关断漏流 | 每个关断尾窗末 100.0 ns 内 `max(abs(I_sink)) <= 1.5e-07 A` | 正负方向都报，不得把有正负反冲的尾段相消后写成零漏流；abs 只用于这条幅度判据，不用于总电荷 |
| 细步长配对 | 普通 2.0 ns / 细化 0.1 ns | 完整激励历史相同，只改 maxstep；配对的 14 个字段必须逐字相等 |
| 收敛 | 同窗口 `abs(dQ)/QLSB <= 0.01` | 同时必须给出绝对差（C 与 fC）；只报 `CONVERGED` 不算答案 |
| 电荷误差 | `Qexpected_nominal=Inominal(k)×T50`、`Qexpected_dc=IDC(k)×T50`，误差以 `QLSB=Iunit_nominal×Ttick` 报 | 候选建议限 0.5 LSB，**只作为待审判据**，本轮不宣称已满足；无 DC 原生值时后一种为 `NOT_RUN`，不得用几何比冒充；T50 只做期望电荷，不做分母 |
| 入带 | 目标电流 ±5%，持续至少 10.0 ns，deadline 为该窗自身末点 | 状态封闭集合 SETTLED_HELD, NOT_SETTLED_WITHIN_PULSE, LEFT_BAND_BEFORE_DEADLINE, NO_REAL_EDGE_FOUND, NOT_RUN；曾入带但在 deadline 前离带必须报 `LEFT_BAND_BEFORE_DEADLINE` |
| 样点 | every time and current must be finite; NaN or infinity is a named refusal | forbidden: adaptive native samples are not snapped to a ps grid；strictly increasing; equal or regressed time is a named refusal |

## 1.1 R1 的激励时间模型（本轮按复审把这一节写进合同）

| 量 | 值 | 为什么必须是这个值 |
|---|---|---|
| 纯关态预备结束 | 1000.0 ns | 使能在这一段全程为 0，初始码自 t=0 稳定 |
| 半沿宽 Emax | 50.0 ns | 三个瞬态族的沿宽（TR-LONG 50、TR-120/200 10、TR-OFFCODE 20 ns）都不得超过它，否则表里的 50% 点与 PWL 的交点不是同一个数 |
| 统一偏移 | 1050.0 ns | 每个瞬态时刻 = R2 相对时刻 + 这个数；首沿 50% 因此是 1050.0 ns，斜坡 1000.0→1100.0 ns，表与波形同一个数 |
| 换码沿 | 总宽 2.0 ns（中心前 1.0 ns 写旧值、中心后 1.0 ns 写新值） | 两点都必须落在纯关态窗内；只写"上一次目标→下一次目标"会让 PWL 直线穿过发光窗，PREP 字节里正是 36 段这样的斜坡 |

### 1.2 五种窗，各自有名字，不再混用

| 种类 | 边界 | 用途 |
|---|---|---|
| `emission` | rise50 -> fall50 | the charge of the whole enable window, the number convergence compares |
| `emission_flat` | rise_end -> fall_start | the flat-part mean current |
| `off_tail` | this fall50 -> next rise_start, or the declared stop for the last platform | signed tail Q, never folded into the emission charge |
| `pure_off` | fall_end -> next rise_start | the only region a code change or a leakage measurement may live in |
| `leak_last100` | the last 100 ns of off_tail | the magnitude test max(abs(I_sink)) against the shutoff limit, and nothing else；必须完整位于 `pure_off` 内，不足 100.0 ns 就 `REFUSE_THE_CONFIGURATION, never truncate silently` |

### 1.3 deck 必须写出的形式（来源是本项目已跑过的写法，不是本轮的猜测）

* `temperature` ← `simopt options temp=27`
* `dc_form` ← `dc_case dc dev=Vclamp param=dc start=0.6 stop=1.5 step=0.05`
* `tran_form` ← `tran_case tran stop=<this case absolute ns> maxstep=<this case ns>`
* `pwl_form` ← `Vname (node 0) vsource type=pwl wave=[t1 v1 t2 v2 ...]`
* `pwl_time_suffix` ← `n, whole nanoseconds`
* 已证出处：`spectre/current_probe_syntax.scs:35`, `scripts/dd1_d7b_run.py:239`, `scripts/dd1_d7b_run.py:288`。本轮没有运行仿真，所以这只是与已证文本的一致性，`NATIVE_NETLIST_SYNTAX` 仍为 `NOT_VERIFIED`，不许写成原生语法 PASS。

## 1.4 R1 修补的四组（复审点名，逐组对着审核事实）

* **`F1_PAM_bit_order_and_high_level`** — 缺陷：the three-character code string was written left-to-right into pam0/pam1/pam2, so pam0 received the weight-4 bit, and the high level was 1.0 V instead of the 1.8 V logic domain; four DC codes (001, 011, 100, 110) carried another code's identity。修法：value = int(code, 2); bit(k) = (value >> k) & 1; volts = bit * logic_high_V, used by the DC decks and the transient PWL alike, and read back from the delivered decks by an independent parser rather than from the generator。审核事实：REVIEW_DATA7C_B_PREP_20261024.md section 3 F1, checks/prep_probe.json F1.dc_code_mismatches (4 rows) and F1.nonrail_highs (12 rows)
* **`F2_PWL_and_window_physics`** — 缺陷：each PAM bit was written as one point per change with no hold pair, so PWL interpolation ramped the bit straight through the emission windows (36 overlaps); the first enable ramp carried an extra (lead, 0) point (declared 1000 ns, real crossing 1025/1010 ns); 20 declared off windows ran backwards; 20 leakage windows contained the next DATA_EN rise up to 0.9 V。修法：a code change is old value at t-1 and new value at t+1 inside the pure-off window; windows are five named kinds (see rules.window_kinds) with start strictly less than stop; the leakage window must lie wholly inside the pure-off window or the configuration is refused; the 50 % edges are interpolated from the delivered PWL and must equal the table。审核事实：REVIEW_DATA7C_B_PREP_20261024.md section 3 F2, checks/prep_probe.json F2.PAM_ramps_over_emission_count=36, backwards_off_windows=20, leakage_windows_with_next_enable=20, enable_50_percent_errors
* **`F3_measurement_entry_wiring`** — 缺陷：measure_case() handed the flat window bounds to the edge finder as the edge hint with a +/-5 ns search, so all eight TR-LONG windows answered NO_REAL_EDGE_FOUND; it took the first off_tail for every window and broke, so a 5 uA fault in a later tail was missed; it never called sign_check or charge_errors, and convergence accepted two sides with no context at all。修法：each emission window searches around its own rise50/fall50, reports the full-enable Q and the flat mean separately, keeps Qpos / signed Qneg / |Qneg|, calls sign_check and charge_errors, pairs window k with tail k, and refuses instead of falling back。审核事实：REVIEW_DATA7C_B_PREP_20261024.md section 3 F3, checks/prep_probe.json F3.entries (eight NO_REAL_EDGE_FOUND), F3.second_tail_independent_reference (ABOVE_LIMIT 5e-06 A while the main entry reported 0.0 A), F3.missing_pair_context_still_accepted=true
* **`F4_native_deck_known_contract`** — 缺陷：fifteen decks wrote bare `dc dev=...` / `tran stop=...` analysis lines and no `simopt options temp=27`, while this project has already run named analysis instances and an explicit temperature; the PWL spelling also differed from the proven `type=pwl wave=[...]` form。修法：decks state simopt options temp=27, an instance-named analysis line, and PWL as wave=[t v ...] with whole-nanosecond n-suffixed times; the audit parses the effective statement instead of matching a substring, so a comment can no longer vouch for a deck。审核事实：REVIEW_DATA7C_B_PREP_20261024.md section 3 F4, checks/prep_probe.json F4.no_explicit_27C (all 15) and F4.unnamed_analysis_lines (all 15); the review states plainly that this is textual inconsistency with proven project syntax, not a reproduced native error

### 1.1 R2 复审后仍开放的一项（本轮唯一修补目标）

* **`T1_qlsb_denominator_is_the_window_not_a_tick`** — 缺陷：measure_case() passed the full-enable window T50 as the QLSB tick as well, so a 1 us platform manufactured its own ruler: a +0.5 pC charge error on code 111 read as 0.266667 LSB and WITHIN_PROPOSED_LIMIT, where either nominal tick the contract already lists (120 ns, 200 ns) puts it at 2.222222 / 1.333333 LSB, outside the 0.5 limit。修法：rules.charge_error.reference_tick_s_by_case freezes the reference tick per case, partners share one value, the eight DC cases have none, and reference_tick_for_case() refuses an unknown, missing, zero, negative or non-finite tick by name before any division instead of falling back to the window length; Qexpected keeps I x T50 and QLSB becomes Iunit_nominal x Ttick, and convergence now carries reference_tick_s in its pair context and refuses when that field disagrees with the denominator it divides by。审核事实：REVIEW_DATA7C_B_PREP_R1_20261024.md section 3, checks/tick_probe.json and checks/fresh_tick_probe.json both rc=0 with defect_reproduced=true: delivered tick 1e-06 s, qlsb 1.875e-12 C, error 0.266667 LSB WITHIN, independent references 2.222222 and 1.333333 LSB outside

#### 1.1.1 逐例参考 tick（`rules.charge_error.reference_tick_s_by_case`，唯一来源即此表）

| case_id | 本轮 POC 参考 Ttick (ns) | QLSB = 1.875 µA × Ttick |
|---|---:|---:|
| `RS-FULL` | 120 | 2.25e-13 C = 225 fC = 0.225 pC |
| `RS-LOW` | 120 | 2.25e-13 C = 225 fC = 0.225 pC |
| `RS-SWITCH` | 120 | 2.25e-13 C = 225 fC = 0.225 pC |
| `TR-120` | 120 | 2.25e-13 C = 225 fC = 0.225 pC |
| `TR-200` | 200 | 3.75e-13 C = 375 fC = 0.375 pC |
| `TR-LONG` | 120 | 2.25e-13 C = 225 fC = 0.225 pC |
| `TR-OFFCODE` | 120 | 2.25e-13 C = 225 fC = 0.225 pC |
| DC 八例 | 不适用 | 时域 QLSB 不计算 |

伙伴（`TR-120`↔`RS-LOW`、`TR-LONG`↔`RS-FULL`、`TR-OFFCODE`↔`RS-SWITCH`）共享同一参考 tick；该映射是本轮为消除歧义提出的 **POC 测量参考单位**（`POC_MEASUREMENT_REFERENCE_NOT_TCON_NOT_DISPLAY_TIMING`），不表示 TCON 或显示帧时序已实现，也不授予任何原生权限。1 µs 长平台与 300 ns 换码平台可以包含多个参考 tick，这不把 Ttick 改成 T50。

## 2 名义电流阶梯（身份全部 ESTIMATED_MIRROR_RATIO_ONLY）

| PAM 码 | 导通支路数 | 名义电流 (µA) | 同一电流分别写成 A / fA / µA（每格带单位） |
|---|---:|---:|---|
| `000` | 1 | 1.875 | 1.875e-06 A = 1.875e+09 fA = 1.875 uA |
| `001` | 2 | 3.750 | 3.75e-06 A = 3.75e+09 fA = 3.75 uA |
| `010` | 3 | 5.625 | 5.625e-06 A = 5.625e+09 fA = 5.625 uA |
| `011` | 4 | 7.500 | 7.5e-06 A = 7.5e+09 fA = 7.5 uA |
| `100` | 5 | 9.375 | 9.375e-06 A = 9.375e+09 fA = 9.375 uA |
| `101` | 6 | 11.250 | 1.125e-05 A = 1.125e+10 fA = 11.25 uA |
| `110` | 7 | 13.125 | 1.3125e-05 A = 1.3125e+10 fA = 13.125 uA |
| `111` | 8 | 15.000 | 1.5e-05 A = 1.5e+10 fA = 15 uA |

代码位权：`pam_sel0`=bit0 权重 1，`pam_sel1`=bit1 权重 2，`pam_sel2`=bit2 权重 4；码 `000` 是**最低非零档**（一条支路），不得当黑码。

### 2.1 手算对照

* `Iunit_nominal = 15e-6 A x (2.5/2)/(20/2) = 15e-6 x 0.125 = 1.875e-6 A`
* `1.875 uA = 1.875e-6 A = 1.875e9 fA (multiply by 1e15 to go from A to fA)`
* `I111 nominal = 8 x 1.875e-6 A = 1.5e-5 A = 15.000 uA, which is the shared reference itself`
* `QLSB_nominal(120 ns) = 1.875e-6 A x 120e-9 s = 2.25e-13 C = 225 fC = 0.225 pC`
* `QLSB_nominal(200 ns) = 1.875e-6 A x 200e-9 s = 3.75e-13 C = 375 fC = 0.375 pC`
* `full scale band = 15 uA +/- 5% = 14.25 uA .. 15.75 uA = 1.425e-5 A .. 1.575e-5 A`
* `unit deviation limit = 0.25 x Iunit_ref; with Iunit_ref = I111/8 = 15 uA / 8 = 1.875 uA that is 0.46875 uA`
* `settle band = +/- 5% of the target of the code under test, hold at least 10 ns`
* `shutoff leakage = max(abs(I_sink)) over the last 100 ns of each declared tail window <= 0.15 uA`
* `1 TON = 1000 ns, so the nominal 120 ns and 200 ns platforms are 0.12 and 0.20 TON`

## 3 探针、符号与窗口口径

* 探针实例 `Ip_branch`，端序 `(clamp_node data_out)`，定义 `I_sink = Ip_branch`。
* 物理正方向：clamp_node -> data_out -> the conducting branch -> vss。
* I_sink = Ip_branch with no negation and no abs(); Q = integral of I_sink over the declared window, positive charge accumulating during the conducting window; the off-window tail is integrated as its own negative area and never cancels against it to claim a shut branch; declared before any run, not chosen after a sign
* 禁止取绝对值的对象：raw current, total charge。
* a shutoff tail may be positive or negative; it is never pre-assumed to be a negative area

## 4 日程来源与平移量

* 相对时刻唯一来源：scripts/dd1_d7c_a_r2_plan.py；本轮绝对时刻由 `scripts/dd1_d7c_b_prep_schedule.py` 计算并写入 `tests/dd1_d7c_b_prep/schedule.csv`。
* 统一初始关断预备 `1000 ns`，`offset_applied_ns` 逐例记录；平台、换码点、积分窗、尾窗与 stop 同一偏移量平移，不逐例各说各话。
* platform, 50% edges, ramp endpoints, code change, integration window, tail, pure-off, leakage sub-window and stop all shift by the same 1050 ns; the pure-off preparation ends at 1000 ns and the first ramp starts there, so no hold point sits inside a ramp

## 5 与已交付 R2 字段的差异（保留建议值，等审核定夺）

| id | R2 另一头的说法 | 冲突 | 本轮值 | 为什么不默改 | 状态 |
|---|---|---|---|---|---|
| `D1_clamp_sweep_step` | `tests/dd1_d7c_a/native_case_plan.csv column segments: "clamp sweep 0.6 V to 1.5 V in 0.05 V steps"`<br>`spectre/dd1_d7c_a_tb_draft.scs:149: "// dc_case_NNNN   dc dev=Vclamp param=dc start=0.6 stop=1.5 step=0.1"` | the delivered table and the delivered draft deck state different sweep steps for the same sweep, and the 0.1 V form also gives a different grid | 0.05 V, with 1.20 V required to be an actual sweep point | the task book section 4 fixes 0.60-1.50 V at 0.05 V; 0.05 V is the finer of the two, so the 1.20 V point stays on the grid either way and no R2 claim becomes false | AWAITING_REVIEWER_DECISION |
| `D2_ton_unit_is_four_microseconds_in_the_deck` | `spectre/dd1_d7c_a_tb_draft.scs:63 "parameters TON=4u // emission window length used by the long-pulse case (POC condition)"`<br>`scripts/dd1_d7c_a_r2_plan.py:33 TON_NS = 1000 and the plan columns are written in TON` | the deck parameter TON is 4 us while the schedule source uses TON as 1000 ns, so the same symbol means two times that differ by a factor of four | every generated deck states absolute times in ns and never uses a bare TON; the deck keeps TON=4u only as an inherited comment, not as a timing symbol | a deck whose "1.0 TON" means 4 us and a table whose "1.0 TON" means 1 us cannot be reviewed as the same stimulus | AWAITING_REVIEWER_DECISION |
| `D3_short_pulse_note_versus_platform` | `scripts/dd1_d7c_a_r2_plan.py:69 SHORT_CASES note "two pulses per 120 ns slot at the Hybrid 100 Hz pitch"`<br>`tests/dd1_d7c_a/native_case_plan.csv columns platform_TON=0.12 / 0.20 for TR-120 / TR-200` | the prose describes two pulses inside a 120 ns slot while the machine columns describe one 120 ns platform, and the 100 Hz pitch of a frame is not 120 ns at all | one platform per emission, 120 ns for TR-120 and 200 ns for TR-200, each stated as two absolute instants (t_rise_50, t_fall_50) plus the integration window inside it; the frame pitch is recorded separately as a 10 ms condition that the deck does not simulate | section 5 requires that "120 ns platform" stop meaning two different pairs of instants | AWAITING_REVIEWER_DECISION |
| `D4_tr_long_starts_conducting_at_t_zero` | `tests/dd1_d7c_a/native_case_plan.csv TR-LONG stimulus_start_TON=0 and segments "000@0-1"`<br>`reports/dd1_d7c_a_native_test_plan.md: "TR-LONG 在一个 deck 内排八个长发光窗"` | the first platform begins at t=0 with the enable already high, so there is no rising edge to detect for the first window and an edge finder would have to invent one | a uniform 1 us initial-off lead is inserted (LEAD_OFF_NS=1000), every platform, code change, integration window and stop shifts by the same amount, and the offset is recorded per case in the schedule table | section 5 asks for exactly this: the initial code settles before the first enable, and a level already high at t=0 is not a rising edge | RESOLVED_BY_THIS_ROUND_WITHIN_THE_ALLOWED_SHIFT |
| `D5_integration_window_is_narrower_than_the_platform` | `tests/dd1_d7c_a/native_case_plan.csv TR-120 window_TON=0.13-0.23 while platform_TON=0.12 starting at 0.12` | the declared window is 100 ns inside a 120 ns platform, which is right (the platform is inset by the 10 ns edges) but the prose calls both of them "the 120 ns window" | platform start/stop, 50% enable edges, and the integration window are separate named columns everywhere: platform_start_ns, platform_stop_ns, enable_rise_50_ns, enable_fall_50_ns, full_window_start_ns, full_window_stop_ns, flat_start_ns, flat_stop_ns | the charge of a window is only comparable between a nominal and a refined run if the window is one pair of instants, not a length in prose | RESOLVED_BY_THIS_ROUND_WITHIN_THE_ALLOWED_SHIFT |
| `D6_transient_offset_is_1050_ns_not_1000_ns` | `tests/dd1_d7c_a/native_case_plan.csv TR-LONG stimulus_start_TON=0, platform_TON=1.0, edge_TON=0.05 (all relative)`<br>`tests/dd1_d7c_b_prep/schedule.csv as delivered at the PREP tip: lead_off_ns=1000.000 with the first enable ramp written 950 -> 1050 and declared at 1000.000` | R2 declares only relative times, so the absolute shift is this round's own choice, and the PREP bytes chose one number for the table (1000 ns) and another for the waveform it actually generated (1025 ns interpolated) | every transient instant is R2 relative time + 1050 ns; the pure-off preparation ends at 1000 ns, the first ramp is 1000 -> 1100 ns and its 50 % point is 1050 ns, which is the number the table and the deck now share | a window whose declared edge and generated edge differ by 25 ns is not the window the integration was planned on, and the reviewer read this off the delivered PWL | CORRECTED_BY_R1_WITHIN_THE_ALLOWED_SHIFT_NOT_A_CHANGE_TO_R2 |

## 6 启动额度草案（本轮授权仍为 0）

* 建议总额 36 次：DUT 15 + 供电/激励 preflight 15 + 语法调试收敛余量 6。DRAFT_PROPOSAL_NOT_AUTHORISATION
* every launch counts, including -h, failures, aborts, crashes and debug; REQUESTED occupies the budget before the run and recovery never refunds it; preflight and DUT are counted separately
* 每例进程数逐行列在 `schedule.csv` 的 `launch_processes_dut` / `launch_processes_preflight` 两列（各 1），不只写"15 例"。
* 本轮不实现新的生产级账本；记账纪律沿用 DATA-7B 已接受的 `REQUESTED/UNCERTAIN/` 五态规则（`scripts/dd1_d7b_run.py` 的 `Account`），未来启动前必须先绑定：R2 接受版、本合同 SHA、执行源码 SHA、电流与电荷判据、原生总额度、本机只读环境核验范围。缺任一项都不能拿本任务书当令牌。
* DATA-7B 历史 `59_OF_56_OVER_BY_3 已 VIOLATED`：不借用、不重置、不抵扣、不改绿。

## 7 本轮不做、未证与待决

* 未证：NATIVE_NETLIST_SYNTAX, HIERARCHICAL_SAVE_SYNTAX, PWL_SPELLING_ON_DECODER_INPUTS, MODEL_CARD_IDENTITY, GEOMETRY_LEGALITY_AGAINST_PDK。
* 未跑：PAM_8LEVEL_CURRENT_MEASURED, PWM_PAM_CURRENT_INTEGRATION, FULL_MOS_GRAY_CONTROLLER, GRAY_LUT, SHUTOFF_LEAKAGE_MEASURED, CONVERGENCE_PAIR_MEASURED, DC_OPERATING_POINTS。
* 冻结件（本轮零修改）：`spectre/dd1_d7c_a_gates.scs`, `spectre/dd1_d7c_a_pam_dec.scs`, `spectre/dd1_d7c_a_sink_unit.scs`, `spectre/dd1_d7c_a_pam_top.scs`。
* NOT_RUN for all fifteen cases; a synthetic number never enters an electrical result

## 8 采纳路径（等审核与用户，执行者不自批）

1. 电流归一取同条件 DC 的 `I111/8`，还是取名义单位电荷；两者结果都要能同时呈现。
2. 电荷误差限 0.5 LSB、偏差不超过 0.25 个 Iunit_ref、漏流 1.5e-07 A、收敛 0.01×QLSB 是否照单采纳。
3. §5 五条差异逐条裁定：接受本轮值、回到 R2 说法，还是另定第三种。
4. 原生阶段总额 36 次是否批准，以及 preflight 与 DUT 的分列记账口径。
