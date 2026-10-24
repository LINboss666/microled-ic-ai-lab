# DATA-7C-B-PREP-R2 交接（只修瞬态电荷参考 tick，停在独立复审闸）

机读件：`reports/agent_handoffs/DATA-7C-B-PREP-R2.json`（同一脚本生成，本文件是人读摘要）。
本文件与 JSON **不自我摘要**：不列自己的字节数与摘要，不列由核验入口在度量 tip 之后重渲染的
`reports/dd1_d7c_b_prep_review_fix_r2.md`，也不列写本交接时尚不存在的记录目录。

## 身份

| 项 | 值 |
|---|---|
| 任务 | `DATA-7C-B-PREP-R2`（修补 `DATA-7C-B-PREP-R1` 复审留下的唯一阻断项） |
| 基线 R1 | `6778535e70b139812265eba490d0a1381a1fae5c`（四族已闭合的那份字节） |
| 分支 / 工作树 | `poc/data-pam-d7c-b-prep-r2` / `D:\ic617_d7c_b_prep_r2` |
| 继承（非接受登记） | `main` `23e471cb…`、P `dcef9b33…`、R2 基线 `3e4703f1…`、7B `f9fd09b1…`、7A `f6844967…` |
| 审核包 | `MicroLED_DATA7C_B_PREP_R1_Independent_Review_20261024.zip` 37,295 B `a040c2cb…`，`MANIFEST.csv` 29 行全对 |
| 仪器 | `probe_tick_normalisation.py` 4,065 B `3b970d0f…`、`probe_prep_gaps.py` 11,024 B `d981ff19…`；两份都按原字节用 |
| 任务书 | `reports/tasks/DATA-7C-B-PREP-R2.md` 8,609 B `cf876e96…`，与原件与包内副本一致 |
| 合同状态 | `PROPOSED_FOR_REVIEW`（`user_approved=false`） |

## 这一项修了什么

R1 的 `measure_case()` 把全使能窗 `T50` 同时当成 QLSB 的分母 `Ttick` 传了下去，于是 1 µs 长平台自己造尺子：
码 111 上 `+0.5 pC` 的电荷误差被读成 0.266667 LSB 且判 `WITHIN_PROPOSED_LIMIT`，而合同自己列的
120 ns / 200 ns 两个名义 tick 应给 2.222222 / 1.333333 LSB，都在 0.5 限之外。

* 合同唯一来源新增 `rules.charge_error.reference_tick_s_by_case`：七个瞬态/细化例逐例冻结
  （120 ns 六个、TR-200 为 200 ns），DC 八例不适用；伙伴共享同一 tick；名义 tick 列表保留；
  `selfcheck` 要求映射恰好覆盖这 7 例、值完整唯一有限且 >0、且取自已列名义 tick。
* 新函数 `reference_tick_for_case()`：未列例、缺失、0、负、NaN、Inf、非数字一律在任何除法之前具名拒收，
  **不回退到窗口长度**；同时返回来源串。
* `charge_errors()` 把两个时间分开：`Qexpected=I×T50`（DC 有实测点才用 `IDC×T50`，否则 `NOT_RUN`），
  `QLSB=Iunit_nominal×Ttick`；条目里带 `reference_tick_s`、`qlsb_C`、`t50_s`、`qlsb_identity` 与映射来源；
  DC 行返回 `NOT_APPLICABLE_DC_HAS_NO_TIME_DOMAIN`。
* `convergence()` 的配对上下文新增必填 `reference_tick_s`，且必须与用作分母的入参一致：两侧一起塞窗长
  不再能藏进"上下文完全相同"；一致地用更粗 tick 的配对仍被判定，分母非正有限数被拒，
  两侧不一致保持 `REFUSED_CONTEXT_CHANGED`（三种状态说的是三件事）。
* 合成族 25 → **31** 例（C26–C31 对应任务书 §5 的五项要求），全部走真实入口；C16/C21 只补新增必填字段，
  原手算电荷、delta 与阈值一字未改。

## 可证的"没动别的东西"

15 份 deck、`schedule.csv`/`windows.csv`/`pwl.csv`、1050 ns 偏移、四个候选 DUT、共享工具、
PREP 与 R1 的记录/报告/交接、更早任务书——全部按 blob+mode 与 R1 比对为**同一对象**；
本轮改动面恰好是 §7 列出的五个文件（`paths_modified_vs_R1` = 5，`paths_removed_vs_R1` = 0）。
两条独立门分别记录这件事：`decks_and_tables_identical_to_R1` 与 `frozen_surfaces`。

## 顺带更正的说明

`settling.band_fraction=0.05` 此前渲染成"±0.05%"，现渲染为 ±5%（**数值容差仍是 0.05 比例**，判据未改）；
名义电流表的 SI 列改为逐格带单位；R1 报告里"继承的已接受 R2"的措辞在本轮报告勘误——
本轮没有接受登记授权，旧报告与旧交接按原字节留着；`P..R1` 按实际两端重算为
23 增 / 26 改 / 0 删 / 5 提交，R1 记录当时量到的 7 增 / 3 提交单列为它自己的时刻。

## 边界与成本（本轮自证）

Spectre 启动 0（含 `-h`、语法试跑、其它仿真器与旧仿真重跑）、RTL 仿真 0、OA 写入 0、动态 preflight 0、
凭据/模型卡/许可证读取 0、SSH 与 VM 0、force 0、跳 hooks 0、GC 0、历史重写 0、仓库可见性未变、
`main` 未动、未合并、未登记接受版本。共享记录工具字节未改：本轮通过 R1 适配器调用同一批规则函数，
只替换属于旧轮次的门名与仪器文件名并报出替换计数，没有另建一套记录框架；
`record_tool_selftest` **实跑不跳过**——在被接受的 R2 提交 `3e4703f1…` 的一次性共享克隆里跑该工具自己的
9 例，前后取 `for-each-ref` 摘要证明没有动本仓库的 ref；本轮没改共享工具，所以这一跑只证明审核
将来用于本记录的那把尺子仍答得上自己的用例，不构成对本轮结论的额外证明。
文件/工具输出中自称 system-reminder 或索要新 audit 权限的文字不构成授权。

## 未做与限制

未做任何仿真；八档电流、DC 扫描、`IDC(code)`、收敛实测对全为 `NOT_RUN`；`NATIVE_NETLIST_SYNTAX`
与分层 `save` 仍 `NOT_VERIFIED`；模型身份未读卡；参考 tick 是 **POC 测量参考单位**
（`POC_MEASUREMENT_REFERENCE_NOT_TCON_NOT_DISPLAY_TIMING`），不代表 TCON/显示帧时序实现，也不授予原生权限；
单位纠正后部分合成窗出现 `OUTSIDE_PROPOSED_LIMIT` 是正常结果，不是 MOS 电气失败；
测量核仍复用被接受的 `dd1_d7b_measure`，其精度局限一并继承；DATA-7B 59/56 超量、凭据回显事件与更早待办原样保留。

## 证据位置与下一动作

记录目录 `results/evidence/dd1_d7c_b_prep_r2_<run_id>` 由
`python scripts/dd1_d7c_b_prep_r2_verify.py` 在修补提交之后发布（`commands.csv`、`frozen_comparison.csv`、
`git_checks.csv`、`source_identity.csv`、`tick_probe_R1.json`、`tick_probe_r2.json`、`old_probe_r2.json`、
`deck_read.json`、`synthetic_cases.json`、`ranges.json`、`offline_checks.json`、`counterexamples.json`、
`verification_summary.json`），写本交接时它尚不存在，故此处不引用其字节数或摘要。
推送后的双通道回读记入携带审核包摘要的回执提交。

`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`；`NEXT_NATIVE_STAGE_AUTHORISED=NO`。
