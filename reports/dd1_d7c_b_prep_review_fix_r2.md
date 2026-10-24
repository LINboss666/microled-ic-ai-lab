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
本轮不重跑共享工具的自测与 T/H 历史证据（该轮没改任何共享工具，`record_tool_selftest` 以
`SKIPPED_WITH_REASON` 记名），记录语义规则仍走共享检查器，只替换属于旧轮次的门名与仪器文件名并报出替换计数。

<!-- BEGIN 7CB_R2 GATES -->
<!-- END 7CB_R2 GATES -->

<!-- BEGIN 7CB_R2 TICK -->
<!-- END 7CB_R2 TICK -->

<!-- BEGIN 7CB_R2 TICKMAP -->
<!-- END 7CB_R2 TICKMAP -->

<!-- BEGIN 7CB_R2 CASES -->
<!-- END 7CB_R2 CASES -->

<!-- BEGIN 7CB_R2 RANGES -->
<!-- END 7CB_R2 RANGES -->

<!-- BEGIN 7CB_R2 FROZEN -->
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
