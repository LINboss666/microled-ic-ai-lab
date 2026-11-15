# T4 RUN01 报告 —— 双片 512 路 Scan Driver（第 1 次 / 共 2 次授权，**失败即停**）

日期 2026-11-15 ｜ 终态 `WAITING_FOR_T4_INDEPENDENT_REVIEW`
裁定：**`T4_RUN01 = FAIL (41/42)`**；`T4_SIM_BUDGET = 1_USED_OF_2`，第 2 次**未运行、未自动追加**。

---

## 1. 结果总览

| 项 | 值 |
|---|---|
| 运行目录 | `D:/ic617_course_sim_20261112_native/t4_run01` |
| 时间 | 21:58:35 起，vsim 8 s，仿真结束 `Time: 99,987 ns` |
| 编译 | vlog 0 errors / 0 warnings |
| 断言 | `ASSERT_COUNT=42`，`PASS=41`，`FAIL=1`，名称无重复 |
| T6 五条件 | `0/1/0/0/1` → `RUNNER_VERDICT=FAIL`，`RUNNER_EXIT=5`（正确拒绝失败结果） |
| 失败项 | **`D42_monitor_samples_not_vacuous`**（`n_cmp=9,978 < 15,000`） |

## 2. 功能证据（41 条全过，含全部契约判据）

| 判据组 | 结果 |
|---|---|
| D01–D04 复位/复位释放不选通 | PASS |
| D05–D11 边界列 0/1/2/3/1022/1023 片选与本地 bit | PASS |
| D12 遍历计数 == 1024（非空洞） | PASS |
| D13 1024 地址逐址与"循环变量独立期望"零失配 | PASS（`sw_mismatch=0`，且全程 `oracle_mismatch=0`） |
| D14 本地 bit 精确 | PASS |
| D15 两片各 512 次 | PASS（`cov_chip0=512`, `cov_chip1=512`） |
| D16 1024 显示窗全局独热 | PASS（`zero_or_multi_hot=0`，`onehot_samples=3,120`） |
| D17 非目标芯片 1024 次全 0 | PASS |
| D18 `blank` 抬高 1 ns 内全 0（1024 次） | PASS |
| D19 引脚实测 STB 数 == 计划数 | PASS（1036 == 1036，**在 P7 复位前求值**） |
| D20–D24 锁存稳定性/换列/跨片清列 | PASS |
| D25–D27 BLANK 即时关断/保持/恢复 | PASS（`blank_on=0`） |
| D28–D30 FAULT 即时关断/保持/恢复 | PASS（`fault_on=0`） |
| D31–D34 非法 STB 安全策略与粘滞错误位 | PASS |
| D35/D36 setup≥10 ns、hold≥5 ns | PASS（**在 P7 复位前求值**） |
| D37 BLANK 外 STB 恰 1 次 | PASS |
| D38 响应非时钟采样（沿后 2 ns 已更新） | PASS |
| D39 诊断 `sel_valid` 与 512 位输出一致 | PASS（`diag_sel_bad=0`） |
| D40/D41 异步复位 1 ns 内全 0、释放后需新 STB | PASS |
| **D42 采样非空洞（阈值 15,000）** | **FAIL**，实际 9,978 |

结论：**双片 512 路功能判据全部通过**（1024 列逐址 bit-exact、跨片严格独热、BLANK/FAULT/RESET 异步关断、锁存不由参考时钟采样）。
但这**不是 PASS**，按纪律原样保留失败。

## 3. D42 失败的根因（TB 自身计数阈值，与 DUT 无关）

- 监视器 `always @(negedge clk) #0.1 ...`：参考时钟 `always #5 clk = ~clk` 的**周期是 10 ns**，因此全程只有 9,978 个 negedge 采样点。
- 我在写 TB 时按"negedge 间隔 5 ns"估了 15,000 的下限，属于**阈值设定错误**，不是覆盖率不足：
  实际采样 9,978 次、其中 `onehot_samples=3,120`、1024 个地址逐址比较、`oracle_mismatch=0`。
- **修复只需一行**：阈值 15000 → 8000（或改为 `n_cmp > 8000`）。**本轮未改**，因为第 1 次失败后不得自行追加/修补后直接重跑，必须送审取得限定授权。

## 4. 同时发现的一处"报告口径"缺陷（不影响判据，但会误导读者）

末尾 census 打印发生在 **P7 异步复位之后**，而 `scan_pin_mon` 的计数器在 `negedge reset_n` 被清零，所以打印出：

```text
COURSE_T4_STROBES expected=1036 observed=0 checked=1024 ...
COURSE_T4_TIMING setup_min_ps=1000000000 hold_min_ps=1000000000 ...
```

`observed=0`、`setup_min=1e9` 是**复位后清空的快照**，不代表监视器没工作：
D19（1036==1036）、D35（setup 最小 25,000 ps）、D36（hold 最小 40,000 ps）都在 P7 复位前求值并通过。
建议第 2 次运行时把 census 打印移到 P7 之前（或额外打印一份 pre-reset 快照），否则审阅者容易被误导。
**本轮未改**，与 §3 一并留待授权。

## 5. 锁源与纪律

| 项 | SHA-256 |
|---|---|
| `rtl/scan_driver.v`（本次仿真） | `6ee3ad38b3a9c2c1a65b37900537875ff52d33ca165145a246dafb0a782229a4` |
| `rtl/scan_exp.v`（独立 oracle） | `8dd70a37194315fa994c99941c31b21932be58e2ea298a04d2278d321995a47d` |
| `rtl/scan_pin_mon.v`（复用，未改） | `7c280e130a36525836de425acb8c8875a61d6613108203c4c486562458304d10` |
| `tb/tcon_t4_tb.sv`（本次仿真） | `9dbbb96032c66a2f1bee10c76d06d724afa003e099eb079d6254898f9c729d05` |

- 未修改 TCON / T3 Data RTL / V1.3 / 旧 T1/T2B/T3 测试；`t4_precheck.py` §5 逐条核对通过。
- 未启动 T5 / Spectre / MC / OA / STA；未动 main；未开 PR；未自签 GO。
- 第 2 次仿真**未使用**；是否使用、以及是否允许上述两行修改，等待复审裁定。

## 6. 本轮已建立的可复用资产

- `t4b/SCAN_PIN_CONTRACT.md`：引脚/优先级/跨片映射/非法 STB 策略，逐条标 FROZEN/DERIVED/OPEN。
- `t4b/T4_TEST_PLAN.md`：运行前写定的向量表与 42 条判据。
- `t4b/T4_OPEN_ITEMS.md`：`T3_LUT_VALID_OUTPUT_GATE_OPEN` 等未决项独立登记（未在 T4 分支改 T3）。
- `rtl/scan_driver.v`：可综合、无参考时钟、组合安全门控、512 位真实独热输出。
- `rtl/scan_exp.v`：纯引脚推导的独立 oracle（与新 RTL 无共享内部信号）。
- 裁剪 VCD：`t4.vcd` 1,322,034 B（仅 4 个列窗口 + 故障/违规区间，非整帧）。
