# DATA-7B 交接（单通道固定电流 PWM 响应验证）

日期 2026-10-21 交付，2026-10-22 由 **DATA-7B-R1** 更正工具、复算证据并修订本交接，2026-10-23 由 **DATA-7B-R2** 关闭预算权威、账本耐久与时间语义（§10），同日由 **DATA-7B-R3** 补账户非法状态拒收并更正交接残留值与解释（§11）。§1–§9 是 T/R1 的事实记录，§10 是 R2 的，均不抹去、不改写，只在其下追加更正。
任务书四份逐字节副本：`reports/tasks/DATA-7B.md`（SHA-256
`0f4db71f752aef5db9869fe097703a423266f433ee2e4040f621c7b0c6e21389`，34,198 B）与
`reports/tasks/DATA-7B-R1.md`（SHA-256
`d35233770fb7bb9a52050937024a16c4106723094493b2c1381cae333b068bf3`，14,185 B）、
`reports/tasks/DATA-7B-R2.md`（SHA-256 `bb39b6d4c54d62cebed74fdd46b22efb738eb215f9a7424807866604a01b5154`，12,148 B）与
`reports/tasks/DATA-7B-R3.md`（SHA-256 `2eb933bc0d8ddd91f34f50bee269e35a0576d0fee8caaf681729e7d1d3defaa1`，10,054 B）。三份返修任务书都是审核方交付件的逐字节副本，摘要按仓库内文件重算。
结构化字段在 `reports/agent_handoffs/DATA-7B.json`。本文件不写自身摘要，最终 SHA 从 Git ref 读。
§5 保留 T 轮原始缺陷记录，§4 是 R1 对本交接旧说法的更正清单——旧说法不抹去，只标错。

## 1 身份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| T 分支 | `poc/data-pwm-d7b`，提交 `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50`（未动） |
| R1 分支 | `poc/data-pwm-d7b-r1`（本轮新建，基线即 T） |
| Git 开发基线 B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 被接受的 DATA-7A 内容 A | `f68449672774ac9266ba9e4893024e4f3027dd9d`（B 的父提交） |
| main（未动） | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 冻结摘要核对 | 任务书 §1.2 的 12 项按 `git cat-file blob B:<path>` 计算，12/12 一致；R1 另核 `git diff --name-only adcdf27` 只含允许改动的工具/新证据/文档 |
| 工具 | 本机 `oss-cad-suite 2026-10-20`（Icarus 14.0 devel / Yosys 0.70+176）；guest RHEL6.5 + IC617 `spectre -64`，Python 2.6.6（仿真侧）/ 本机 Python 3.12.5（编排与测量）。R1 未启动任何原生工具 |
| R1 交付证据 | `results/evidence/dd1_d7b_r1_r20261022_123825_8e1294/`（284 文件；manifest 283 条 / 21,084,177 B，与暂存 Git blob 283/283 逐条一致） |
| T 交付证据 | `results/evidence/dd1_d7b_r11_main/`，完全冻结未改一字节；用 R1 复核器重跑得 **14 项具名 FAIL** |
| 身份分列 | 原生 run（`src_native_run`/`src_launch_id` + deck/PWL/raw/log/psf 摘要）· 测量源码（measure/runner/trace/evidence_check 四个摘要）· 本轮导出（`run_id` + `reused_from=adcdf27…`） |

## 2 R1 实际做了什么

1. **测量**（判据一字未改）：下降沿按该窗声明的脉冲段查找，找不到写 `NOT_FOUND` 并计数、不回退 `t1`；
   入带以实际下降沿为**排他期限**；关断段越过反弹继续扫；正负面积在插值过零点分段并断言
   `q = q_pos + q_neg`。手算用例并入 measure 自测 **22/22**。
2. **入口与额度**：模式闭合集 + 授权检查前置（无模式/多模式/未授权一律 rc=5 且不创建目录）；账本按 run
   隔离；任务级账户从 T 的 `launches_reconcile.csv` 播种、启动**前**记账、失联转 UNCERTAIN 且继续占额度；
   复用按字节摘要与原生 run 唯一性校验（漂移 deck/PWL/master、两个候选 run、缺 preflight 孪生一律拒）；
   发布前跑完整语义校验，只放行已披露的历史预算失败，拒收时正式目录逐条不变。守护 **8 组 PASS**。
3. **复核器**：从冻结契约独立重建 27 个 `(case_id, window)`、角色、模式、码域、tick/窗口映射、maxstep、
   输入沿与收敛配对，共 **39 项**；审核者注入的 8 类语义错误每类都产生自己的新失败或新原因；
   `--selftest` 无 SKIP 路径（缺基线即 FAIL rc=1）。
4. **离线重测并交付新包**：电荷样本与 T 的 26 个序列**逐字节相同**（`CHARGE_SERIES_MATCHES_ACCEPTED`
   独立复核），标定带与边沿邻域作为新分片随包交付；`negative.csv` 单位写进列名并绑定 run/launch/转录摘要；
   收敛缺配对的 P30 code1 离线补齐；标定 `section`/`temp` 从 deck include 行与 psf `temp` 列反读并互校。
5. **边沿复验**：冻结 RTL + 冻结 TB 重跑 17 份 trace（**17 次新四态仿真，用满上限**），304 个字段全
   `AGREE`；VCD 字节以 `r1rtl_<case>.vcd.txt` 交付并在 `rtl_reverify_delivery.csv` 并列登记仿真器摘要与
   交付摘要（原因：`.gitignore:84` 的 `*.vcd` 与 Git 的 CRLF 归一化）。篡改控制证明该比较不是空判。
6. **自测记录随包**：`gate_records.csv` 由 `dd1_d7b_r1_gate_records.py` 机器生成，只保留各门真实打印的
   判词与 rc，含本机路径的行整行丢弃并计数（不涂改、不粘贴）。

**本轮外部成本：新增 Spectre 进程 0，新增 OA 写入 0，新增四态 RTL 仿真 17。** 未进 guest、未建 SSH、
未起 Virtuoso/OA、未做 VM 电源/快照/网络/许可证操作、未 GC、未改写历史、未跳 hooks。

## 3 结果（验证可靠与电气达标分开）

* `EVIDENCE_STATUS = PASS_WITH_DISCLOSED_HISTORICAL_BUDGET_FAILURE`：39 项里唯一 FAIL 是
  `BUDGET_RESPECTED`（59 > 上限 56 的历史事实，保留 FAIL，不改判据、不改 NOT_RUN）。
* `PWM_CURRENT_FEASIBILITY_TT = PASS_WITHIN_FROZEN_CRITERIA`：25 个判定窗 `|charge_error_LSB|` 最大
  `0.438391`（`D7B-CVG-P30-C255/normal`）全部 ≤ 0.5；非 N1 末 100 ns `max|Iout|` 最大
  `2.0600878e-08 A ≈ 20.60 nA`（`D7B-P50-C255/normal`）< 150 nA；`Ical = 1.493190564e-05 A`；
  5/5 收敛对 `CONVERGED`；`D7B-N1` 判 `EXPECTED_REFUSAL / WIRING_FAULT_DETECTED`
  （`q_win = 1.146770353e-10 C = +256 LSB`）；`D7B-N2` rc=1、`stage=supply_contract`、该目录 0 次启动。
* 仍未达标的是时间行为：23 个判定窗 `NOT_SETTLED_WITHIN_PULSE`，导通初期峰值最高 `1.684531296e-05 A`
  （`D7B-P30-C016/normal`）。结论范围只到单窗净电荷与关断后末 100 ns 电流，**不是**光学有效位数、
  不是全程电流稳定、不是亮度或 PAM 结论。
* 完成级别：`RTL_TRACE_DRIVEN_MOS_OUTPUT_MEASURED_TT`（边沿另加 17 次冻结 RTL 复验）。

## 4 R1 对本交接旧说法的更正（旧说法保留在此，不抹去）

| 项 | 本文件旧说法（T） | 复算后的事实 | 证据 |
|---|---|---|---|
| 进程数 | "24 DUT + 24 动态 preflight = 48 次交付矩阵，其余 11 次是缺陷成本"，报告/JSON 另写 27 | 整轮 **59 = 30 preflight + 29 dut**；`environment` 的 42 是 `r11_main` 单 run 局部计数；27 只是幸存账本被旧字符串识别的行数 | `launches_reconcile.csv`、`launch_account.csv`、`reports/tasks/DATA-7B-BUDGET-01.md` |
| 账本 | "只有 27 行" | 实为 **58 行 = 27 preflight + 27 dut + 4 static_negative**，仍 ≠ 59；差额源于共享路径账本被崩溃轮覆盖（R1 已按 run 隔离） | 两包 `process_ledger.csv` |
| 超额 | "超出授权 3 次"（正确）但 JSON 写 `scope_status=COMPLETE`、"超额运行 0" | 52 → 追加 4 → 上限 56，实际 59，**超额 3**；`HISTORICAL_BUDGET_STATUS=VIOLATED_NOT_RETROACTIVELY_AUTHORISED`，交接 `scope_status=PARTIAL` | 同上 |
| 证据状态 | `PASS_WITH_BUDGET_EXCEPTION`，"20 项里 19 项 PASS" | 那 20 项漏掉审核者注入的 8 类语义错误（其中 1 类甚至让它 rc=0 全 PASS）；重建后 39 项，T 自身在同一大检查下 14 项具名 FAIL | `reports/dd1_d7b_review_fix_r1.md` §3 |
| 入带 | 19 个窗 `SETTLED` | 旧判据只要求存在一段 10 ns 入带；改为排他期限后 23 窗 `NOT_SETTLED_WITHIN_PULSE`、3 窗 `NOT_APPLICABLE_NO_CONDUCTING_EDGE`、标定行 `MEASURED` | `cases.csv`、measure 自测 T6b/T6c |
| 下降沿/关断 | 12 个窗 `de_fall_50` 为空、短码窗"关断 = 窗口末"（11595/16715/19815） | 按声明脉冲段重找：`C001` 下降 `3945.0000 ns`、关断 `3968.0376 ns`（延迟 23.0376 ns）；`pulse_edges_missing` 全表 0 | `cases.csv`、`edge_*.csv`、`rtl_reverify.csv` |
| 正负积分 | `q_positive` 重复计面积（`P30-C002` 交付 7.528301435e-13，样本重算 7.527008626e-13） | 在插值过零点分段，恒等式断言通过 | measure 自测、`CHARGE_RECOMPUTED` |
| 标定 | `verdict=REUSED`、无样本、`temp_read` 空、`tt` 由文件名代替 | 1,000 个带内样本随包，`integration 4.994999999998259e-07 s`；`section` 读自 deck include 行、`temp` 读自 psf `temp` 列并互相核对 | `calibration.csv`、`charge_D7B-CAL_cal.*.csv` |
| 收敛 | `D7B-CVG-P30-C001 = BLOCKED_MISSING_PARENT`，三处 `NOT_FOUND_BOTH` | 母案例字节本在包内，离线补齐后 5/5 `CONVERGED`，边沿差 `0.0000 ns` | `convergence.csv` |
| N1 | 列名 `_A` 填 µA 数值、`run_id` 空 | 列名改 `window_peak_uA`/`last_100ns_max_abs_uA`，绑定 `r11_main/L032` 与 deck/raw/transcript 摘要 | `negative.csv` |
| 末 100 ns | 报告另处写"全都 ≤ 0.74 pA" | 非 N1 最大 20.60 nA（审核者独立读到约 20.65 nA），仍 < 150 nA；0.74 pA 是把电荷当电流 | `cases.csv` |
| 包范围 | "B..P 新增 818" | B..P = 818，B..T = 820（P 之后 2 个元数据文件），不可混用 | `git diff --name-status` |
| P30 code1 | 数字本身正确，但容易被读成电荷判据失败 | `3.018093995e-13 C` 对目标 `4.479571693e-13 C` = `−0.326254 LSB`，在 ±0.5 LSB 内 | `cases.csv` |

## 5 T 轮的缺陷与成本（原文保留）

| # | 我自己的缺陷 | 后果 | 修法 |
|---|---|---|---|
| 1 | TB 的 BLANK/FAULT 忘记写入 code 16，首窗成了黑码 | 中止窗 0 导通（复现期发现，未耗额度） | TB 补 `pure_code=16`，重跑全部 trace |
| 2 | 中止事件锚在 `obs_tick` 上升沿（比采样沿早 5 ns） | 与 t0 定义不一致 | 改为 `@(posedge obs_tick); @(posedge clk)` 后计时 |
| 3 | PWL 写成 `wave=(t v)(t v)` | 本机读入 SFE-874，1 次失败启动 | 采用已验收的 `wave=[t v t v ...]` 纳秒拼式 |
| 4 | 把"整皮秒"规则误用到 PSF 采样网格 | 拒收真实仿真数据，1 次失败案例 | `float_samples` + 显示量化界 `time_quantum_ps` |
| 5 | deck stop 与测量边界重合，末样本比 stop 早 ~4 as | 尾窗积分越界拒收 | `STOP_MARGIN_NS=50` |
| 6 | 分片按固定行数切，单片 465 KB 超限 | 一次崩溃（1 次启动被计入失败） | 按实测字节自适应切分，去掉每行重复标识列 |
| 7 | 字段里出现逗号导致 CSV 列错位 | 复用行摘要串列 | `write_rows` 逗号拒写闸 |
| 8 | "复用分支"补丁插进 `static_probe` 的循环 | 本应 0 启动的补齐轮新起 4 次进程 | 交付集改由 `launches_reconcile.csv` 逐目录对账 |

**额度结论（R1 复核后）**：guest 侧实测 **59** 次 Spectre 进程（30 preflight + 29 dut），任务书 52，
用户追加 4 后上限 **56**，**超额 3**。发现后即停止，未再启动任何进程，也未把任何一次失败说成"不计数"。
R1 的账本/入口/发布修补已在 §2 第 2 条完成；预算项仍作为 FAIL 交付，处置权在用户。

## 6 本轮操作记录（不得省略）

1. **我删除了四个自己刚发布的中间 R1 证据目录**（`105514_12119e`、`105959_806e84`、`111106_b3171e`、
   `111346_e3f62c`；发布记录的字节数见 `reports/dd1_d7b_review_fix_r1.md` §0）。它们未提交、未推送，
   可由保留 raw 与当时脚本重生成，但原始字节已不在机上。用户中途指示不得先删记录再重做；此后一律
   新 staging 目录 + 新 run_id，已发布目录原地保留 —— 机上另有 5 个未提交的 R1 中间件目录，
   逐个用当前复核器重跑的结果已在修复报告 §0 登记。
2. **凭据回显事件**：一条写错的 `grep -vE` 使 guest 口令值在本机终端输出出现过一次。该值未进入任何任务
   文件、报告、日志摘录、JSON、README、记忆文件或 Git 对象；本任务不授权改口令，也未做远端扫描，
   因此**不宣称该事件已解除**。口令仍只在运行时从桥目录的凭据文件取用，该文件不入 Git。
3. 既存不可达 blob 仍使 `--mode objects` 扫描 rc=1（与 DATA-7A/R4 同一身份）：未打印、未 GC、未豁免，
   也不声称对象库干净。staged/history 扫描按真实 rc=0 记录。

## 7 边界与未做

PWL 是离线验证激励，不构成全 MOS 灰阶控制器、混合信号联合仿真、片内数字单元映射或八档 PAM 的完成证明；
后续产品仍计划片内产生 PWM。未做：八档 PAM/电流 DAC、LUT 与光学标定、LED I–V、真实互连 RC、最终
VSCAN/VLED、CDC/skew、阵列与多通道、corner/温度/MC、版图/DRC/LVS/PEX、OA 与 Virtuoso
（`NEW_OA_WRITES=0`，未启动 dbAccess/Virtuoso，未改 PDK 与他人库）、TCON/HDMI、DATA-7B 之外的任何
下一阶段内容。T 轮的 VM 网络只做了用户批准的 `dhclient -1 eth0`（临时租约，未改 `ifcfg-*`）；R1 未碰网络。
`tests/dd1_d7b/r1/` 固定夹具目录未新建：本轮夹具由自测与守护脚本从**已提交字节**在进程内合成，
在新 checkout 可独立复现（审核者要求的"缺 fixture 不许 SKIP"已满足）。

## 8 推送与回读

普通 push 新分支 `poc/data-pwm-d7b-r1`（非 force、未跳 hooks）；Git 协议与 GitHub API 两条独立路径回读，
逐条比对 `main`、`poc/data-pwm-d7b` 与其余旧分支未动。`head_sha` 固定为功能 payload 提交 P1，分支 tip
与最终包身份从 Git ref / 包外回执读，本文件不写自身 SHA。

## 9 下一步（等云端独立复审，不由执行者给 GO）

1. `BUDGET_RESPECTED` 仍 FAIL：历史超支 3 次的处置权在用户，本任务不代其追认。
2. 短窗不入带与 ~16.8 µA 导通峰值是最实的物理发现；是否为此改输出级由用户决定（本轮未动电路）。
3. 若要继续，建议先补"最短码的电荷-脉宽曲线"（同一 7 管结构，扫 N=1..8），而不是先做 PAM 译码。
4. 本轮工具遗留：17 次四态仿真上限已用满，再需复验须另行授权；VCD 交付形式依赖 `.gitignore:84`
   与 Git 行尾归一化这两条现实，若仓库策略变化需重估。

`NEXT_STAGE_AUTHORISED=NO`、`SOA_SIGNOFF=NO`、`MERGE_PERFORMED=NO`（`main` 与所有旧分支未动）。

## 10 R2 追加（2026-10-23，本轮事实全部来自本轮发布包）

| 项 | 值 |
|---|---|
| 本轮任务 / 基线 | `DATA-7B-R2`，唯一基线 H = `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92`（被审 R1 tip） |
| 分支 / 载荷 | `poc/data-pwm-d7b-r2`，功能载荷 P2 = `6abe1bf5b93dc4bb12ba179cea0ab26929f33a90` |
| 交付证据 | `results/evidence/dd1_d7b_r2_r20261022_160652_e880be`（287 文件 / 21323343 B；manifest 覆盖 286 条且与提交内 blob 286/286 逐字节一致；从 Git 提取物重新复核 43 项，唯一失败 `BUDGET_RESPECTED`） |
| 复核 | 43 项检查，PASS 42，FAIL 1（清单：BUDGET_RESPECTED） |
| 本轮成本 | 新增 Spectre 0；新增 RTL 仿真 0（R1 已用满 17 次，本轮只重新解析交付字节）；新增 OA 写入 0；动 guest 否 |
| 账户 | 333 行 = 59 CONFIRMED + 274 REFUSED_NO_LAUNCH；占额度 59；固定授权 56（任务书 52 + 追加 4）；历史超支 +3 |
| 电气 | 27 行判决 {EXPECTED_REFUSAL: 1, PASS: 26}；最大绝对电荷误差 0.438391 LSB；Ical 1.493190564e-05 A |
| 标定切片 | OFF 带内 800 样点、尾段 200 样点入包；原 raw 摘要 `e93bd38a2e2e2f64…` 与包内记录一致，直接核对 |
| 四态 | 17 份交付 VCD 全部由冻结解析器重读，26 个窗口的脉冲段与 `pwl_edges`、`rtl_reverify.csv`、case 行一致 |
| 系列比对 | 55 条系列（索引 158 行）：charge 26 条与接受包逐字节相同、3 条本轮新增；edge 26 条因新增全精度 `t_ps` 列而重算 |
| 未解 | 历史超支 3 次处置权在用户；凭据事件未解除；R1 旧包的 0.1 ns 边邻切片无法在 0.05 ps 上复核（定义/精度滞后，非"旧证据全错"） |

R2 关闭的缺陷（逐条修法与重放见 `reports/dd1_d7b_review_fix_r2.md`）：
预算判据从被检文件取（`BUDGET_AUTHORITY_FIXED`）、`REQUESTED` 不占额度、先删后改名的写盘、
过期实例覆盖、种子历史只比 ID、原生入口可被环境绕过、deadline 左侧不完整、互补节点相位错、
20 mA 电流容差、采样时刻与连续阈值混同、收敛表 `delta_edge` 不重算、只查摘要不重读 VCD、
CAL 的 OFF/尾段无样点支撑、以及 7 类语义破坏无人检出（现在 8+7 全部点名）。

本轮不合并、不授权下一阶段、不做 SOA 签核；停在独立复审闸。

## 11 R3 追加（2026-10-23，账户非法状态拒收与交接更正）

| 项 | 值 |
|---|---|
| 本轮任务 / 基线 | `DATA-7B-R3`，base = 被审 R2 tip `b3fe93c17de014cb16031438ce28c7152dd0020f` |
| 分支 | `poc/data-pwm-d7b-r3`（本轮新建）；基线只读检出 `D:\ic617_d7b_r3_base`（detached，未提交） |
| 载荷 P3 / tip | 见 §10 与 `r3.payload_sha`；本文件不写自身摘要，也不写自己的 tip |
| 范围 | 只补 Account 与复核器的非法状态枚举 + 交接/报告勘误；**不改电路、判据、样本、判决** |
| 新增检查 | `ACCOUNT_STATES_VALID`（43→44 项）；反例面 15→16 类 |
| 对 R2 包的复评 | 44 项中唯一失败仍是历史 `BUDGET_RESPECTED`；R2 包 287 文件逐字节未动 |
| 本轮成本 | Spectre 0；RTL 仿真 0；OA 写入 0；未进 guest、未读凭据、未改密码 |
| 剩余 | 历史 59/56 超支 3 次处置权在用户；凭据事件未解除；四个已删中间目录原字节不可得 |

R3 关闭的唯一代码缺陷（F1）：`Account` 与复核器都只按已知状态计费，却从不拒绝**未知/空/大小写或空白变体**，
所以把一行 `REQUESTED` 或 `REFUSED_NO_LAUNCH` 改成不认识的拼写就会静默失去占额；
配合同步 environment 汇总与重封 manifest，复核器不会新增任何失败。
修法是在读入后、`recover()/_restamp()/flush()` 前对全部行做枚举并抛错（拒收时保留原字节），
`counts()`/`_restamp()` 同样拒绝内存中被改坏的行，复核器新增 `ACCOUNT_STATES_VALID` 对所有行核对。
R2 §10 与上文各节是 R2 时点的事实，不追改；本节与 `corrections_r3` 只登记更正关系。
