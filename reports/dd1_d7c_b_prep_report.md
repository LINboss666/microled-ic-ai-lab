# DATA-7C-B-PREP 八档 PAM 原生验证准备报告（2026-10-23，停在独立复审闸）

任务书逐字节副本 `reports/tasks/DATA-7C-B-PREP.md`（18,448 B，SHA-256
`40a3eb148e038c4fb6ea4d5a7d48de4b2e9b22e6a34a685c34f912f2a3c8b126`，源
`C:\Users\LMX\Downloads\TASK_DATA7C_B_PREP_20261023.md`，逐字节比较相等；该文件无 CR，故 Git blob
与工作副本同为这 18,448 B）。

## 0 身份与边界

| 项 | 值 | 怎么核 |
|---|---|---|
| 仓库 | `https://github.com/LINboss666/microled-ic-ai-lab` | 推送后两条通道各自回读 |
| 工作基线 R2 | `3e4703f1763223024f442c0826e95055782bca13` | 双通道回读（§1） |
| 本轮分支 / 工作树 | `poc/data-pam-d7c-b-prep` / `D:\ic617_d7c_b_prep`（`git worktree` 自固定 R2 SHA） | `git worktree list` |
| 对照 | R1 分支 `poc/data-pam-d7c-a-r1` = `da6f5fc…`；被审 A 分支 = `89b3dd8…`；main = `23e471c…`；DATA-7B 线 = `272d6de…` | 同上，本轮全部不动 |
| 合同状态 | `PROPOSED_FOR_REVIEW`，**不是** `USER_APPROVED`；R2 的独立复审**未**由本轮给出接受结论 | `tests/dd1_d7c_b_prep/contract.json` |
| 逐字限制 | `NEW_SPECTRE_LAUNCH_LIMIT=0`、`NEW_RTL_SIMULATION_LIMIT=0`、`NEW_OA_WRITE_LIMIT=0`、`NATIVE_PREFLIGHT_AUTHORISED=NO`、`SSH_OR_VM_ACCESS_AUTHORISED=NO`、`PDK_OR_CREDENTIAL_ACCESS_AUTHORISED=NO`、`ACCEPTANCE_REGISTRATION_AUTHORISED=NO`、`MERGE_OR_MAIN_PUSH_AUTHORISED=NO`、`NEXT_NATIVE_STAGE_AUTHORISED=NO` | 记录 `verification_summary.json` 三项成本为 0 |
| 实际做的 | 纯 Python 文本/算术/Git 读；未起任何仿真器（含 `spectre -h`），未读 PDK/模型卡/凭据，未连 guest，未 GC、未重写历史、未 force、未跳 hooks（提交与推送钩子每次都真实运行） | 每条命令文本记在 `commands.csv` |
| 只新增 | 本轮对 R2 已有路径零修改零删除（§6），只写新路径 | 记录 `frozen_comparison.csv` enforced 行 |

## 1 开工核验（双通道，逐 ref 完整 SHA）

推送前于 `2026-10-23T16:50:38Z`（Git protocol，rc=0）与 `2026-10-23T16:50:50Z ~ 16:50:58Z`
（GitHub API，rc=0）读同一组 ref，两路一致：

| ref | 两路返回的完整 SHA | 判定 |
|---|---|---|
| `poc/data-pam-d7c-a-r2` | `3e4703f1763223024f442c0826e95055782bca13` | 本轮基线，与任务书固定值相同 |
| `poc/data-pam-d7c-a-r1` | `da6f5fc3f4977e0ab1447b8cd4982a68878a4bbb` | R1 tip 未动 |
| `poc/data-pam-d7c-a` | `89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79` | 被审 tip 未动 |
| `main` | `23e471cb936b421ee97e1250c3be06edf96f9937` | 未动 |
| `poc/data-pwm-d7b-r3` | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` | DATA-7B 线未动 |
| `poc/data-pam-d7c-b-prep` | Git protocol 无该行；API 404 | 本轮分支当时尚未建立，这是正确答案而非读回失败 |

对象存在性另核：`f9fd09b184a69a27cdb409205dfd4f4151408a23`（DATA-7B 接受内容）、
`f68449672774ac9266ba9e4893024e4f3027dd9d`（DATA-7A 接受内容）与 R2 tip 三个对象 API 均按完整 SHA
返回自身。审核端已在固定 R2 字节上重放 34 项离线检查、65 条反例与记录复核，这只算进度核验，
不是 R2 的完整独立复审 GO。

## 2 电路边界与激励（本轮真正交付的东西）

四份候选 DUT 与 R2 逐字节相同（`gates / pam_dec / sink_unit / pam_top`，§6 的 enforced 行给结论）：
一个输出 `data_out`、八条单位下拉支路、一个共享二极管连接参考。`data_en=1` 时导通数
`pam_sel+1`，`data_en=0` 时全关；码 `000` 是**最低非零档**（一条支路 ≈ 1.875 µA 估算），不是黑码。
`Mref` 20 µm/2 µm、单位 `Mcas/Mout` 2.5 µm/2 µm，`Iref=15 µA` 外供 ⇒ 名义单位电流
1.875 µA，身份 `ESTIMATED_MIRROR_RATIO_ONLY`；`Mpass/Mbleed` 本轮不重新缩放。
LED 的 N 侧接 Data 恒流下拉、Scan 的 PMOS 高侧接 LED 的 P 侧这条极性和行列称呼未做任何统一化改写。

激励与观测全部从**一份**合同生成，避免同一个数出现第二个说法：

```text
tests/dd1_d7c_b_prep/contract.json   条件、判据、单位、名义阶梯、额度、与 R2 的差异
        ↓ scripts/dd1_d7c_b_prep_contract.py（唯一写手，含自校验）
tests/dd1_d7c_b_prep/schedule.csv    15 例逐例绝对时刻（ns）：平台起止、50% 沿、积分窗、关窗、
                                     尾窗、末 100 ns 漏流子窗、换码时刻与理由、stop、maxstep、配对
tests/dd1_d7c_b_prep/windows.csv     62 条窗口行（emission / off_tail / dc_sweep_point）
tests/dd1_d7c_b_prep/pwl.csv         215 个 PWL 点（DATA_EN 与三位 PAM 各自一条时间轴）
        ↓ scripts/dd1_d7c_b_prep_deckgen.py
spectre/dd1_d7c_b_prep/*.scs         15 份 deck 文本，每份把上述数字写在自己文件头
```

三处相对 R2 的实质改进，都是本轮该做的准备：

1. **统一 1 µs 初始关断预备**（`lead_off_ns=1000`），平台、换码点、积分窗、尾窗、stop 同量平移，
   `offset_applied_ns` 逐例记录。R2 的 `TR-LONG` 第一平台从 t=0 就点亮，使能没有上升沿可找；
   现在第一沿在 1000 ns，且码在 750 ns 就已稳定。
2. **"120 ns 平台"不再指两个时刻**：`platform_start/stop`、`enable_rise_50/fall_50`、
   `window_start/stop`、`tail_start/stop`、`leak_last100_start` 分列。使能斜坡关于其 50% 点对称，
   所以两次斜坡之间就是声明的积分窗（TR-120：平台 1120→1240，窗 1130→1230，尾 1240→1480，
   漏流子窗 1380→1480）。
3. **换码落在关窗中点**而非与沿重合（TR-LONG 提前 250 ns、TR-OFFCODE 提前 150 ns），
   "换码完全处于关态"因此是可检查的事实；规则与余量写在行里。

`RS-LOW/RS-FULL/RS-SWITCH` 与各自伙伴的 14 个身份字段逐字相等，只差 `maxstep`
（2.0 ns → 0.1 ns）；`RS-FULL` 复制 `TR-LONG` 的**全部八段**历史与分段，不从最后一窗重启。
DC 八例用静态 `Vdata_en (data_en 0) vsource dc=1.8`，瞬态用 `type=pwl` 有限沿，两种使能互斥
（同一节点两个源同时驱动是接线错误，deck 审计会拒）。每个网络显式接地，夹持源与参考电流源在
bench 层，PDK 只留 `${QODER_PDK_LIB}` 环境变量占位。层级 `save`、`type=pwl` 拼写与原生语法一律
`NOT_VERIFIED`：这些是审核方读的文字，不是本 build 已证特性。

## 3 测量口径（先定死，不看波形后改）

* 探针固定 `Ip_branch (clamp_node data_out) iprobe`，`I_sink = Ip_branch`；物理正方向
  `clamp_node → data_out → 导通支路 → vss`，与已接受 DATA-7B 台架的端序一致。原始电流与总电荷
  **永不**取 abs()。
* 关断尾流可正可负，不预设"尾段=负面积"。每个窗口单独给有符号 `Q`、`Qpos`、`Qneg`，并要求
  `Q = Qpos + Qneg`；漏流判据用 `max(abs(I))`，但同一段的正负两半必须仍然可见。
* 时间/电流/使能样点严格读取：非有限拒收、时间严格递增、自适应样点**不**取整到 ps 网格，
  并随结果返回显示量化界（`time_quantum_ps`）。
* 50% 沿用相邻两点 + 线性插值；找不到真实沿 → `NO_REAL_EDGE_FOUND`，绝不回退到窗口末点。
* 电荷：`Qexpected_nominal = Inominal(k) × T50`、`Qexpected_dc = IDC(k) × T50`；无 DC 原生值时后者
  `NOT_RUN`，不用几何比冒充 `IDC`。两者都按声明 QLSB 报，候选限 0.5 LSB 只作待审判据。
* 入带：目标 ±5%，持续 ≥10 ns，deadline 为该窗自身末点；曾入带但提前离带必须报
  `LEFT_BAND_BEFORE_DEADLINE`，未达条件 → `NOT_SETTLED_WITHIN_PULSE`；采样界定与插值连续界定分列。
* 配对：细化对照不得改符号、阈值、窗口、参考电流，改了记 `REFUSED_CONTEXT_CHANGED`；
  收敛必须同时给绝对差（C/fC），只报 `CONVERGED` 不算答案。

实现复用 DATA-7B 已接受内核 `scripts/dd1_d7b_measure.py`（`interp_pair:158`、`clip_window:174`、
`trapezoid:189`、`signed_areas:199`、`integrate:231`、`crossing:244`、`band_spans/
sustained_in_band:279-383`、`turn_off:410`、`tail_segment_max_abs:459`、`float_samples/
time_quantum_ps:118-155`），本轮只加八档特有的口径（阶梯双判、名义/DC 两种期望、状态映射）。
这些是**测量算法的验证**，不是电路性能：全部结果带 `SYNTHETIC_NOT_MEASURED`。

## 4 合成正反例（17 例，逐例见 `synthetic_cases.json`）

正例证明手算一致，负例先证明故障事实存在再要求具名拒收：C02 反接后 `Q=-1.875e-13 C`，
`abs()` 本可让它与正例一模一样，规则改为拒收；C03 把 deck 的 iprobe 端序换掉，deck 审计按语句行
（不是注释里的字符串）点名拒绝；C04 尾段 `+0.5 µA` 与 `-0.5 µA` 净电荷为 0 仍不过漏流判据；
C06 非均匀样点边界插值等于手算 `1.375e-13 C`；C08 的 NaN、重复时间、倒退时间、空样点表与
"没有真实沿"各自按名拒收；C09 提前离带不得记 `SETTLED`；C11 八档全体减半时比例判据通过而绝对
判据失败，总判 `FAIL`；C12 少给 `000` 档的阶梯被拒收；C13/C14/C15 细化例丢掉前七段平台、改掉
使能电平、少一组换码，都被日程表闸点名。

## 5 覆盖、额度与差异

15 例 = 8 DC + 4 瞬态 + 3 细化，全部 `NOT_RUN`；每例计划 1 个 DUT 进程 + 1 个 preflight 进程，
合计 15 + 15 + 6 余量 = 36 次草案，本轮授权仍为 0，且未来任何启动（含 `-h`、失败、崩溃、调试）
都计入总额，`REQUESTED` 执行前占额、恢复不退额。§9 的机器表给出逐例清单与门表。

与已交付 R2 字段的 5 处不一致登记在合同 `differences_vs_R2`（§7）：夹持扫描步长在机读表与 deck
草稿里不同（0.05 V / 0.1 V）、`TON` 在 deck 里是 4 µs 而日程源按 1000 ns 用、短脉冲注记
"每 120 ns 槽两个脉冲"与平台列的 120/200 ns 不一致、`TR-LONG` 首平台从 t=0 就导通、
"120 ns 窗"同时指平台与内缩后的积分窗。本轮**保留建议值**、给出差异与自己的做法，
不改旧报告说"历史本就一致"。

## 6 零修改与继承的信息项

相对 R2 的 `H..tip` 只新增本轮允许路径；R2 全部跟踪路径、四份候选 DUT、共享工具与安全闸脚本、
以及全部既有证据目录（含上一轮那枚被判 FAIL 的记录）在 blob 与 mode 上逐条相同
（`frozen_comparison.csv` 的 enforced 行求和为 0）。`git diff --check` 在 `R2..HEAD`、`T..HEAD`、
`B..HEAD` 三个真实提交区间都 rc=0。

`scripts/netlist_stats.py --check` 在本轮树与 R2 只读提取里给出**同样 11 条** `PROBLEM`
（`DEVICE_COUNT_CHECK: FAIL` 两侧一致），是上一轮已按 `INFORMATIONAL_NOT_PASS` 登记的既有范围限制，
本轮不顺手处理、也不把它算成通过。

## 7 还差什么才能启动（不由执行者给 GO）

1. R2 的独立复审结论与用户对 R2 的接受决定；本轮不登记接受版。
2. 本合同由审核冻结：名义/DC 两种归一取哪一种作 PASS 判据、0.5 LSB、0.25 Iunit_ref、0.15 µA、
   0.01×QLSB、±5% 与 10 ns、以及 §7 五条差异的裁定。
3. 原生执行源码的 SHA、总额 36 次的授权、以及本机**只读**环境核验范围（模型卡身份、`tt`+`stat_noise`
   的 include 组合、层级 `save` 与 `type=pwl` 两条未证语法先用探针确认）。
4. 缺任一项，本任务书不构成启动令牌。

## 8 本轮自己的缺陷（按实登记）

* 日程/合同/deck 三处首版各有真实错误：`'50%'` 未转义导致 `%` 格式抛 `TypeError`、
  refined 例的伙伴映射取错来源（复制出 0 条窗口行）、按 `signal` 分组把三位 PAM 当成同一节点、
  窗口计数比较把字符串和浮点比（导致每条窗都"失配"）、以及一个占位残留判断。
  全部由本轮自己的 `--emit/--check` 拒发布或 `D7C_B_PREP_CASES` 报 MISS 暴露，未进入已发布记录。
* deck 审计最初用子串判断探针端序，被注释里引用的正确字符串"掩护"过一次；C03 报 MISS 之后改成
  只匹配非注释语句行。这同样是"检查器自己看不见自己的错"这一类，记在这里而不是删掉。
* 第一次发布跑完 19 行门判定后有**四行是错的，而且错法一样**：门名承诺的是 `da6f5fc`（R1 tip），
  代码喂给它的却是 R2 抽取树。`reviewer_remaining_on_H` 因此在已闭合六个缺口的字节上要求七个缺口
  全部复现（实测 1/7）；`previous_record_reader` 用 R2 字节审 R1 记录，把 12 条路径报成问题，而 R1
  自己披露的只有 3 条；`record_tool_selftest` 的九个用例里有一个用"所在树的真实比较行"构造干净表，
  在本轮树里 DATA-7C-A 白名单把这 30 条新路径当成违规，于是永远不可能干净；`handoff_structure`
  拒绝的是一个不可能成立的摘要——交接文件把自己列进了自己的 digest 表。
  前三个改法是**把参照树指对并复用上一轮自己的门函数**（`remaining_instrument_gate` 未改一字），
  第四个是把那两个文件从交接的身份表里拿出来、并让检查器拒绝"自我登记"这件事本身；
  `record_tool_selftest` 额外要求把树内失败逐条归因（本轮白名单确实允许这 30 条、工具字节与
  R2 相同、源仓 `for-each-ref` 摘要前后一致），否则仍算失败——不允许用"换个上下文跑就绿"糊过去。
* 发布本身撞了三次，都留了原样字节：`…_172056_48cc50`（已提交，8 个子结果 JSON、无 `commands.csv`）
  在 `git diff --check` **空输出**处崩——`communicate()[0] or ''` 把 `b''` 变成 str 再 `.decode`；
  `…_174500_f2b6a7`（14 门全 PASS）崩在同一函数里的名字遮蔽，`extracted` 既是三棵树字典又被后面
  单次抽取覆写成 bool；`…_174846_39a012`（23 行门判定）被自己的回读闸拦下——`source_identity.csv`
  把两份交接文件各登记两次（`read_table` 按主键拒读），同时缺 `record_line_endings` 这一强制门名。
  后两份未成为记录，整目录放在 Git 忽略的 `review/scratch/aborted_attempt{2,3}_…/`，一个字没改。
  同一个 `or ''` 写法在上一轮的 `scripts/dd1_d7c_a_verify.py:152` 里仍然存在，本轮按 §2 不动共享
  工具，只把位置和后果写在这里。
* 修完四门后第一次真正发布（`…_175526_9753e7`，24 门 0 失败）**没有**被提交：本节的复盘是在它测完
  tip 之后写进报告的，于是它 `source_identity.csv` 里对本报告的摘要当场变成假语句。与其提交一份
  自己会打脸的记录，不如整目录原样移到 `review/scratch/superseded_175526_…/`，用新的 run id 重发一次
  ——这正是 R1 因为"记录引用了它发布之后又写的文件"被抓到的同一件事，本轮不能靠事后注释补救。
  同一个理由又发生了一次：`…_181422_958378` 也是 24 门 0 失败，但发完之后才发现
  `report_render_fixed_point` 把自己的依据写成"表是源的函数、不是时刻的函数"——第一次渲染确实
  改了字节（长度差恰好为 0 让人误读成"没改"），而 git 区间行本来就带 UTC 时刻，这句话超出了证据；
  改成"固定点在一次运行内判定，表同时是时刻的函数"之后，那份记录对 `scripts/dd1_d7c_b_prep_verify.py`
  与报告的摘要再次失真，于是同样原样移到 `review/scratch/superseded_181422_…/`。
* `commands.csv` 里 `handoff_structure` 那行把入口写成 `python dd1_d7c_b_prep_verify.py
  --handoff-check`，可这个 flag 当时并不存在——记录引用了一个审核者照着敲就会失败的命令，比写错一个
  数字更糟。现在它真存在：只判交接、什么都不发布，`rc=0/1` 由同一套 `handoff_check()` 决定。
  另有一次被中途叫停的自动命名发布（`data_7c_b_prep_r20261023_182052_659156`，用了小写连字符的
  目录名而不是交接里约定的 run id），它从未成为记录，字节整目录放在 `review/scratch/killed_autonamed_…/`。
* `…_182017_eb2df7` 是 24 门 0 失败的记录，而且**已经随 `043d797` 推到远端**；推完才查出交接文件把本
  报告 digest 成了**重写前**的字节——发布运行会重渲染本报告，而交接写在重渲染之前。这正是 R1 被抓的
  那类"引用了自己发布之后又改写的文件"，只是这次引用者是交接。改法不是事后补摘要，而是让交接不再
  digest 任何它写不出字节的目标（自身两份 + 被本运行改写的报告），并把这条规则做进
  `handoff_check()`：再把它们列回去本身就变成 FAIL。该记录**不删**——已推送的证据目录只能保留，
  它继续作为 tip `7e883b7` 那次机器判读的原样字节留在 `results/evidence/`，地位由本轮最终记录取代。
* 中途差点踩线，也确实踩了一次小的：把它移去 `review/scratch/` 之后 `git status` 显出 15 行 `D`
  （已提交、已推送的文件），删除在提交前被拦下，用 `git checkout -- <dir>` 原样恢复；随后清理那份
  逐字节相同的 scratch 副本时，先用脚本比较了 15 个文件的 SHA-256 全等才动手。另一次是我自己的操作
  错误：为了回退一次演练渲染而 `git checkout -- reports/dd1_d7c_b_prep_report.md`，把本节尚未提交的
  更正一并抹掉了，只能重写——已提交的内容没丢，丢的是我几分钟前的草稿，这不影响交付字节的一致性。
* 因此 `…_184337_1fb057`（同样 24 门 0 失败，随 `2a23133` 本地提交）也被上面这段更正作废一次：它
  digest 的交接与报告字节在更正后又变了。它同样保留、不删、不改；本轮最终交付的记录是
  `results/evidence/dd1_d7c_b_prep_20261023_185017_03cccc`。被取代的记录留在仓库里，判据是"谁也不许
  为了让账面干净而删证据"，不是"最后那份一定全对"。

## 9 机器写入的表（由 `scripts/dd1_d7c_b_prep_verify.py` 从记录渲染）

### 9.1 门与命令

<!-- BEGIN 7CB GATES -->
| 门 | 命令 | rc | 期望 | 判决 | 依据 |
|---|---|---|---|---|---|
| `reviewer_instrument_on_T` | `python review/MicroLED_DATA7C_A_R1_Review_20261023/reviewer/probe_review` | 0 | 0 | PASS | baseline_checks=22 baseline_failures=none items=8/8 expected_rc=0 all_defects_reproduced=True; still reporting reproduced: top_pam_bits_swapped,top_en |
| `reviewer_instrument_on_fixed_bytes` | `python review/MicroLED_DATA7C_A_R1_Review_20261023/reviewer/probe_review` | 1 | 1 | PASS | baseline_checks=34 baseline_failures=none items=8/8 expected_rc=1 all_defects_reproduced=False |
| `reviewer_remaining_on_H` | `python D:\ic617_d7c_b_prep\review\MicroLED_DATA7C_A_R1_Review_20261023\r` | 0 | 0 | PASS | baseline_checks=30 baseline_failures=none all_gaps_reproduced=True cases=7/7 gap_state=reproduced=7 |
| `reviewer_remaining_on_R2_base` | `python D:\ic617_d7c_b_prep\review\MicroLED_DATA7C_A_R1_Review_20261023\r` | 1 | 1 | PASS | baseline_checks=34 baseline_failures=none all_gaps_reproduced=False cases=7/7 gap_state=closed=6; still reporting reproduced: published_record_reader_ |
| `reviewer_remaining_on_fixed_bytes` | `python D:\ic617_d7c_b_prep\review\MicroLED_DATA7C_A_R1_Review_20261023\r` | 1 | 1 | PASS | baseline_checks=34 baseline_failures=none all_gaps_reproduced=False cases=7/7 gap_state=closed=6; still reporting reproduced: published_record_reader_ |
| `offline_checks` | `python dd1_d7c_a_offline_check.py --json <out>` | 0 | 0 | PASS | D7C_A_OFFLINE_CHECK: PASS (34 checks, failures: none) |
| `counterexamples` | `python dd1_d7c_a_guards.py --json <out>` | 0 | 0 | PASS | D7C_A_GUARDS: PASS (65/65 named exactly; not hit: none) |
| `record_tool_selftest` | `python dd1_d7c_a_r1_selftest.py --json <out>/selftest.json run in a thro` | 0 | 0 | PASS | clone_at_R2 PASS (9 cases, failures: none); this_tree rc=1 FAIL, failing cases frozen_gate_counts_only_enforced_rows, other 8 cases PASS, all 53 paths |
| `synthetic_measure_cases` | `python dd1_d7c_b_prep_cases.py --json <out>` | 0 | 0 | PASS | D7C_B_PREP_CASES: PASS (17/17 named exactly, failures: none, evidence SYNTHETIC_NOT_MEASURED) |
| `contract_selfcheck` | `python dd1_d7c_b_prep_contract.py --check` | 0 | 0 | PASS | D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=13 problems=0) |
| `schedule_check` | `python dd1_d7c_b_prep_schedule.py --check` | 0 | 0 | PASS | D7C_B_SCHEDULE_CHECK: PASS (rows=15 windows=62 pwl=215 problems=0) |
| `deck_check` | `python dd1_d7c_b_prep_deckgen.py --check` | 0 | 0 | PASS | D7C_B_DECKGEN_CHECK: PASS (15 decks, problems=0) |
| `deck_regenerated_from_sources` | `python dd1_d7c_b_prep_deckgen.py --to <scratch>` | 0 | 0 | PASS | D7C_B_DECKGEN_REGENERATED 15 decks in a scratch tree, comparison problems=0 |
| `fresh_extraction_replay` | `git archive f9b4608b37a7 / tar -x, then run the suites there` | 0 | 0 | PASS | contract_check rc=0 D7C_B_CONTRACT_CHECK: PASS (state=PROPOSED_FOR_REVIEW sweep_points=19 markdown_rows=13 problems=0); schedule_check rc=0 D7C_B_SCHE |
| `previous_record_reader_finds_its_own_staleness` | `git archive da6f5fc3f497 / tar -x, then python scripts/dd1_d7c_a_r2_reco` | 0 | 0 | PASS | 9 semantic problems over 3 paths (DATA-7C-A.json,DATA-7C-A.md,dd1_d7c_a_review_fix_r1.md); paths outside the three R1 disclosed: 0 |
| `handoff_structure` | `python dd1_d7c_b_prep_verify.py --handoff-check (in process)` | 0 | 0 | PASS | fields, digests against disk, zero costs, markers and forbidden claims all checked |
| `native_entry_refused` | `python dd1_d7c_a_deckgen.py --probe <temp>` | 0 | 0 | PASS | DECKGEN_PROBE refused=True untouched=True reason=DATA-7C-A: this round authorises no native launch and no deck publication; NATIVE_AUTHORISED_THIS_ROU |
| `provenance` | `python scripts/provenance_check.py` | 0 | 0 | PASS | SOURCE_PROVENANCE_CHECK: PASS |
| `netlist_stats_scope` | `python scripts/netlist_stats.py --check` | 1 | INFORMATIONAL: this tool counts MOS lines, it does not judge this round | INFORMATIONAL_NOT_PASS | DEVICE_COUNT_CHECK: FAIL |
| `history_safety` | `python scripts/precommit_safety_check.py --mode history` | 0 | 0 | PASS | SAFETY_GATE: PASS |
| `frozen_surfaces` | `git ls-tree -r, blob and mode comparison over explicit path lists, plus ` | 0 | 0 | PASS | enforced rows 6, violations 0, informational rows 1, added 53, removed 0, modified 0; git diff --check R2..HEAD=0 T..HEAD=0 base..HEAD=0 |
| `record_line_endings` | `scan every published file for CR and round-trip a comma-and-quote row th` | 0 | 0 | PASS | published files still carrying CR: none; the table writer emits LF (confirmed); the instruments write their own JSON with platform newlines, so those  |

渲染发生在 `f9b4608b37a7` 之后、`record_semantics` 与 `published_record_recheck` 判定之前；最后两门的最终值与每条命令的完整文本在 `commands.csv`。本表不含本轮记录的摘要，摘要写在本目录的 `verification_summary.json`（它写于本文件之后，故不进摘要）。
<!-- END 7CB GATES -->

### 9.2 15 例清单

<!-- BEGIN 7CB DECKS -->
| 用例 | 类别 | 码 | 使能形态 | 平台 / 窗 / 尾 / 漏流子窗 (ns) | 换码 | stop | maxstep | 配对 | 进程 DUT+preflight | 结果 |
|---|---|---|---|---|---|---:|---:|---|---|---|
| `DC-000` | dc_sweep | `000` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-001` | dc_sweep | `001` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-010` | dc_sweep | `010` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-011` | dc_sweep | `011` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-100` | dc_sweep | `100` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-101` | dc_sweep | `101` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-110` | dc_sweep | `110` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `DC-111` | dc_sweep | `111` | static_dc | dc_no_time_window / dc_no_time_window / dc_no_time_window / dc_no_time_window | static_from_t0 | dc_no_time_window | not_applicable_dc_analysis | - | 1+1 | NOT_RUN |
| `TR-LONG` | transient | `000..111` | pwl_per_platform | 1000.000;2500.000;4000.000;5500.000;7000.000;8500.000;10000.000;11500.000 / 1050.000;2550.000;4050.000;5550.000;7050.000;8550.000;10050.000;11550.000 / 2000.000;3500.000;5000.000;6500.000;8000.000;9500.000;11000.000;12500.000 / 2400.000;3900.000;5400.000;6900.000;8400.000;9900.000;11400.000;12900.000 | 750.000;2250.000;3750.000;5250.000;6750.000;8250.000;9750.000;11250.000 | 13500.000 | 2.000 | - | 1+1 | NOT_RUN |
| `TR-120` | transient | `000` | pwl_single_platform | 1120.000 / 1130.000 / 1240.000 / 1380.000 | static_from_t0 | 1480.000 | 2.000 | - | 1+1 | NOT_RUN |
| `TR-200` | transient | `000` | pwl_single_platform | 1120.000 / 1130.000 / 1320.000 / 1460.000 | static_from_t0 | 1560.000 | 2.000 | - | 1+1 | NOT_RUN |
| `TR-OFFCODE` | transient | `011,100,000,111` | pwl_four_platforms | 1000.000;1600.000;2200.000;2800.000 / 1020.000;1620.000;2220.000;2820.000 / 1300.000;1900.000;2500.000;3100.000 / 1500.000;2100.000;2700.000;3300.000 | 850.000;1450.000;2050.000;2650.000 | 3400.000 | 2.000 | - | 1+1 | NOT_RUN |
| `RS-FULL` | refined_step | `000..111` | pwl_per_platform | 1000.000;2500.000;4000.000;5500.000;7000.000;8500.000;10000.000;11500.000 / 1050.000;2550.000;4050.000;5550.000;7050.000;8550.000;10050.000;11550.000 / 2000.000;3500.000;5000.000;6500.000;8000.000;9500.000;11000.000;12500.000 / 2400.000;3900.000;5400.000;6900.000;8400.000;9900.000;11400.000;12900.000 | 750.000;2250.000;3750.000;5250.000;6750.000;8250.000;9750.000;11250.000 | 13500.000 | 0.100 | TR-LONG | 1+1 | NOT_RUN |
| `RS-LOW` | refined_step | `000` | pwl_single_platform | 1120.000 / 1130.000 / 1240.000 / 1380.000 | static_from_t0 | 1480.000 | 0.100 | TR-120 | 1+1 | NOT_RUN |
| `RS-SWITCH` | refined_step | `011,100,000,111` | pwl_four_platforms | 1000.000;1600.000;2200.000;2800.000 / 1020.000;1620.000;2220.000;2820.000 / 1300.000;1900.000;2500.000;3100.000 / 1500.000;2100.000;2700.000;3300.000 | 850.000;1450.000;2050.000;2650.000 | 3400.000 | 0.100 | TR-OFFCODE | 1+1 | NOT_RUN |

文本由 `spectre/dd1_d7c_b_prep/DC-000.scs` 承载，逐例一份；`--to <scratch>` 重新生成一次并与交付字节比较（门 `deck_regenerated_from_sources`）。
<!-- END 7CB DECKS -->

### 9.3 合成正反例逐例

<!-- BEGIN 7CB CASES -->
| 例 | 类型 | 判决 | 观察到的依据 | 说明 |
|---|---|---|---|---|
| `C01_positive_sink_charge` | POSITIVE | HIT | Q=1.875e-13 C over 100 ns at 1.875 uA, sign SINK_POSITIVE_AS_DECLARED | a 100 ns window at one unit current integrates to the hand-computed charge and reads positive |
| `C02_reversed_probe_refused` | NEGATIVE | HIT | the same physics on reversed terminals gives Q=-1.875e-13 C; abs() would have made it look identical to the positive cas | turning the ammeter around cannot be rescued by abs() |
| `C03_deck_probe_order_named` | NEGATIVE | HIT | line 74 became (data_out clamp_node) and the deck audit answered: TR-120.scs writes the probe as "Ip_branch (data_out cl | a deck written with the terminals swapped is refused by the deck audit |
| `C04_cancelling_tail_fails` | NEGATIVE | HIT | net Q=0 C looks like a shut branch, the magnitude test still says 0.5 uA against a 0.15 uA limit | a tail whose positive and negative halves cancel is not zero leakage |
| `C05_quiet_tail_passes` | POSITIVE | HIT | max(abs(I))=0.01 uA at 1380 ns inside the last 100 ns, under the 0.15 uA limit | a quiet tail passes and names its sample instant |
| `C06_nonuniform_pencil_check` | POSITIVE | HIT | Q=1.375e-13 C, boundaries interpolated onto the enclosing pairs | interpolated boundaries over unequal spacing match the arithmetic done by hand |
| `C07_adaptive_precision` | POSITIVE | HIT | kept 1.99902e+06 ps (quantum 50000 ps), which is the bound a reviewer needs beside the number | a printed simulator time is kept at its own precision with its display quantum reported |
| `C08_garbage_named` | NEGATIVE | HIT | four bad sample shapes and one edge-less window all refused by name | NaN, a repeated time, a backwards time, an empty list and a missing edge each refuse by name |
| `C09_left_band_before_deadline` | NEGATIVE | HIT | left the band at 1201.55 ns, held only None ns, deadline 1230 ns | entering the band and leaving early is not a settled window |
| `C10_settled_held` | POSITIVE | HIT | in band from the edge to the deadline, held 100 ns | staying in band to the deadline is the settled case |
| `C11_halved_array` | NEGATIVE | HIT | half current gives worst deviation 0 units of Iunit_ref, absolute 7.5 uA against the band 14.25-15.75 uA | eight levels at half current pass the ratio and fail the absolute target |
| `C12_code_000_not_black` | NEGATIVE | HIT | code 000 = 1 branch, and a ladder missing it is refused by name | the lowest code is one conducting branch and cannot be dropped from the ladder |
| `C13_refined_lost_history` | NEGATIVE | HIT | the schedule refused it: RS-FULL differs from TR-LONG outside the time step: code_change_ns,enable_fall_50_ns,enable_ris | a refined case that dropped the seven earlier platforms is not the same conditions |
| `C14_refined_changed_supply` | NEGATIVE | HIT | the schedule refused it: RS-LOW differs from TR-120 outside the time step: data_en_level_V | a refined case that also moved the enable level is refused |
| `C15_refined_lost_transition` | NEGATIVE | HIT | the schedule refused it: RS-SWITCH differs from TR-OFFCODE outside the time step: code_change_ns | a refined case that dropped one code change is a different experiment |
| `C16_convergence_absolute` | NEGATIVE | HIT | delta Q=10 fC = 0.0444444 QLSB against a 0.01 limit; moving the window by 10 ns refuses the comparison | convergence always carries an absolute difference, and a moved window refuses the comparison |
| `C17_two_charge_expectations` | POSITIVE | HIT | nominal 1.875e-13 C vs DC NOT_RUN; QLSB 2.25e-13 C, error 0 LSB | nominal and DC expectations stay apart and the missing DC point is NOT_RUN, never a geometry guess |

每一例都是手算合成样点（`SYNTHETIC_NOT_MEASURED`）：验的是测量算法，不是电路性能；负例先证明注入的事实存在，再要求规则点名拒收，空期望对空结果不算检出。
<!-- END 7CB CASES -->

### 9.4 冻结面与 Git 区间

<!-- BEGIN 7CB FROZEN -->
| 比较 | 面 | 路径数 | 计数 | 前若干 | 期望 | 计入闸 |
|---|---|---:|---:|---|---|---|
| this_round | `every_R2_tracked_path_vs_tip` | 2613 | 0 |  | `identical` | yes |
| this_round | `four_candidate_DUT_netlists` | 4 | 0 |  | `identical` | yes |
| this_round | `shared_tools_and_safety_rules` | 14 | 0 |  | `identical` | yes |
| this_round | `previous_round_record_dirs` | 51 | 0 |  | `identical` | yes |
| this_round | `paths_added_this_round` | 53 | 0 |  | `only_allowed_new` | yes |
| this_round | `paths_removed_or_modified_vs_R2` | 0 | 0 |  | `none_removed` | yes |
| this_round | `added_paths_listed_for_the_reviewer` | 53 | 0 | reports/agent_handoffs/DATA-7C-B-PREP.json;reports/agent_handoffs/DATA-7C-B-PREP.md;report | `informational_listing` | no |

* `git diff --check 3e4703f1763223024f442c0826e95055782bca13..HEAD` → rc=0，0，committed range from 3e4703f17632 to HEAD at 2026-10-23T18:48:24Z
* `git diff --check 89b3dd8e244eaf14bd3bdb7d93b4c771a28fbb79..HEAD` → rc=0，0，committed range from 89b3dd8e244e to HEAD at 2026-10-23T18:48:24Z
* `git diff --check 272d6de6d2f2fc8a82d5038d73d6b3e4c656f683..HEAD` → rc=0，0，committed range from 272d6de6d2f2 to HEAD at 2026-10-23T18:48:25Z

R2 的全部 2613 条跟踪路径逐条比 (mode, type, blob)；四份候选 DUT、共享工具、安全闸脚本与全部旧证据目录各成一行为 enforced；本轮新增 53 条路径全部落在任务书 §9 允许的新路径前缀里，删除与修改计数为 0。
<!-- END 7CB FROZEN -->

## 10 停止状态

```text
TASK_ID=DATA-7C-B-PREP
BASE_SHA=3e4703f1763223024f442c0826e95055782bca13
CONTRACT_STATE=PROPOSED_FOR_REVIEW
R2_INDEPENDENT_ACCEPTANCE=NOT_GRANTED_BY_THIS_TASK
CANDIDATE_DUT_NETLISTS_CHANGED=NO
EXISTING_TRACKED_PATHS_MODIFIED=0
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
PWM_PAM_CURRENT_INTEGRATION=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
GRAY_LUT=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW_OF_NATIVE_PREPARATION
```
