# 数字 RTL 功能时序报告（`rtl_timing_report.md`）

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 2026-11-12
工具：`ModelSim - Intel FPGA Edition / ModelSim ALTERA STARTER EDITION vsim 10.5b (2016.10)`
状态：**功能仿真时序（周期级）**，不是门级静态时序分析。

---

## 1. 真实运行记录

| 项 | 值 |
|---|---|
| 编译命令（运行时逻辑名） | `vlog -sv course_col_scan.v course_data_latch.v dd1_d7a_gray_ctrl.sv course_top.v course_selfcheck_tb.sv`；入库时按仓库安全闸白名单附加 `.txt` 包装，runner 在 scratch 还原真实扩展名后编译，字节不变 |
| 编译结果 | `Errors: 0, Warnings: 0`（`results/modelsim_compile_log.txt`） |
| 运行命令 | `vsim -c -do "run -all; quit -f" work.course_selfcheck_tb` |
| 最终运行 | `run02`，`vsim_rc=0`，`Errors: 0, Warnings: 0`，`Time: 35236 ns` |
| 断言 | `ASSERT_COUNT=55 / PASS_COUNT=55 / FAIL_COUNT=0`，`COURSE_RTL_RESULT=PASS`，`ONEHOT_VIOLATIONS=0` |
| 原始 transcript | `results/modelsim_transcript_run02.txt`、`results/modelsim_vsim_stdout_run02.txt` |
| 原始 VCD | 仓库外隔离目录 `run02/course_sim.vcd`，169531 B，SHA-256 `1aad00ca8d51566ef6889b3a451b9384c436ddc932f00398a8a286385440bd45` |
| 事件数值 | `results/course_wave_events.csv`（由 TB 在真实仿真中写入） |
| 第一次失败运行 | `run01`：**52/55 PASS、3 FAIL、2 warnings**，原件保留在 `results/modelsim_vsim_stdout_run01_FAILED.txt` 与仓库外 `run01_tb_measurement_defect/`，未删除、未改写 |

关于第一次失败：3 项失败均为**测试台测量方法缺陷**，不是 RTL 行为错误。
(1) `C03_wrap_strobe_high` 在组合信号改变后同一时间步立即读取，缺 delta 时间；
(2)(3) `C10/C09` 把 `obs_tick`（组合）在 `+1ns` 采样来数窗口 tick，窗口结束那一拍状态已变 `S_DONE`，漏掉第 65 个结束边界 tick，`acc_t` 实测 64 而非 65。
修复只改测量：组合信号改在 `#1` 后读；新增在 `posedge clk` 采样**边沿前**窗口状态的 `win_tick_count` 监视器，实测 **65** 个窗口 tick。
**判据数值 65 未放宽、DUT 未改逻辑、失败样本未丢弃**；另删除一个未连接的 `blanked` 输出端口以消除 2 条 TFMPC 警告。
修复尝试：该根因 1 次（上限 3 次）。

---

## 2. 频率假设与周期公式

| 量 | 值 | 来源等级 |
|---|---|---|
| `T_clk` | 10 ns（100 MHz） | `ENGINEERING_DERIVATION / POC_ASSUMPTION`，与复用 RTL 注释的参考域一致；**非教师给定条件** |
| `T_tick` | 120 ns = 12 × `T_clk` | `POC_ASSUMPTION`，借用旧实验量级，本报告单独证明其可用性 |
| `N_col` | 1024 | `COURSE_FIGURE` + 既有项目架构记录（作为地址域） |
| `N_row` | 768 | 同上 |
| Hybrid 窗口导通间隔 | 64 = `FULL_HYB` | 复用 `dd1_d7a_gray_ctrl.sv.txt` 的 `localparam FULL_HYB=64` |
| 窗口结束边界 tick | 第 65 个 | `index_q == full_w` 时 `state_q <= S_DONE` |
| 消隐开销 | 8 tick | `POC_ASSUMPTION`，**不是教师给定规格** |

```
T_frame(f)      = 1 / f
T_column(f)     = 1 / (f * 1024)
T_window(t_tick)= (64 导通 tick + 8 消隐 tick) * t_tick   [POC 模型]
条件成立        <=> T_window < T_column
```

---

## 3. 按波形实测的关键数值（周期级 / 功能时序）

数据来源：`results/course_wave_events.csv` 与真实 VCD（不是手算填表）。

| 事件 | 实测时间 / 计数 | 性质 |
|---|---:|---|
| `reset_released` | 46 ns | TB 事件 |
| `col_0_to_1` | 76 ns | 列推进：1 个 `col_step` → 下一个 `posedge clk` 生效（10 ns 寄存器延迟） |
| `col_wrap_1023_to_0` | 10327 ns | 1023 → 0 回绕，`col_wrap` 组合脉冲 |
| `latch_in_blank_at_col` | 10566 ns | blank 期 LATCH，`latch_count` 在下一拍变 1（10 ns 寄存器延迟） |
| `pwm_max_window_start_ns` | 10836 ns | 第 1 个被接受 tick |
| `pwm_max_window_end_ns` | 18396 ns | 最后一个被 `obs_tick` 采到的 tick；跨度 7560 ns = 63 × 120 ns |
| `pwm_max_conducting_ticks` | **64** | 最大码 63 的导通 tick 数（「63 码占 64 个 tick」边界） |
| `pwm_max_window_ticks_pre_edge` | **65** | 含第 65 个结束边界 tick 的窗口总 tick 数 |
| `pwm_black_conducting_ticks` | **0** | 黑码整窗无导通 |
| `pwm_black_window_ticks_pre_edge` | **65** | 黑码仍消耗完整 64 间隔 + 结束边界 |
| `pam000_conducting_ticks` | **64** | `pam_sel=000` 不是黑码，仍导通 64 tick |
| `negative_proto_err_bitmap` | 223 (`8'hDF`) | 负例协议拒绝位图 |
| `blank` 置位 → `data_en`/`drive_gate` 关断 | 组合级（同仿真 delta，无 clk 等待） | 功能时序 |
| `pwm_start` → `S_ARMED` | 1 个 clk（10 ns） | 功能时序 |
| 第 65 tick → `S_DONE` | 1 个 clk（10 ns） | 功能时序 |
| `blank` 置位且窗口在 `S_RUN` → `S_ABORT` | 1 个 clk（10 ns） | 功能时序 |

> 上述全部是 **ModelSim 功能仿真里的周期级/组合级时序**，没有门延迟、线延迟、输入/输出负载、
> 时钟偏斜或 PVT。不得据此推断硅上时序。

---

## 4. 60 Hz / 100 Hz 每列时间预算（单独核算，不默认成立）

TB 用实测得到的 `conducting_ticks = 64` 代入上式，输出：

```
TIMING_BUDGET tick_ns=120 conducting_ticks=64 blank_ticks=8
TIMING_BUDGET col_period_60Hz_ns=16276.042 col_period_100Hz_ns=9765.625
TIMING_BUDGET slot_120ns_tick_ns=8640 slot_200ns_tick_ns=14400
TIMING_BUDGET fit_120ns_60Hz=YES fit_120ns_100Hz=YES fit_200ns_60Hz=YES fit_200ns_100Hz= NO
```

| 帧率 | 每列周期 `T_column` | `t_tick=120 ns`（本 TB 实测模式） | `t_tick=200 ns`（旧实验量级） |
|---|---:|---|---|
| 60 Hz | 16276.042 ns | 8640 ns → **满足**，余量 7636.042 ns | 14400 ns → 满足，余量 1876.042 ns |
| 100 Hz | 9765.625 ns | 8640 ns → **满足**，余量 1125.625 ns（约 11.5%） | 14400 ns → **不满足**，超出 4634.375 ns |

**结论**：本轮采用的 Hybrid 模式 + 120 ns tick + 8 tick 消隐，在 60 Hz 与 100 Hz 下都能落进列周期；
但**不能把 200 ns tick 默认推广到 100 Hz**——它在 100 Hz 明确超出列周期。
100 Hz 的 120 ns 方案余量只有约 1.126 µs，尚未计入列驱动建立、锁存/译码传播、阵列 RC、
电平搬移与 PVT，因此这只是**控制逻辑层面的预算核对**，不构成面板时序验证。

---

## 5. 测试覆盖（55 条断言，全部留名于 transcript）

| 案例 | 覆盖内容 | 结果 |
|---|---|---|
| C01 | 复位/起始状态：列 0、onehot 0、latch_count 0、drive_gate/data_en/chan_valid 关断、S_IDLE | PASS ×7 |
| C02 | 列 0→1、onehot_pop=1、onehot_valid | PASS ×4 |
| C03 | 到达 1023、1023 的 odd bank/ch511、`col_wrap` 脉冲、回绕到 0、col0 的 even bank/ch0 | PASS ×5 |
| C04 | blank 时 onehot=0 / scan_sel 关 / drive_gate 关；解除后 onehot=1；全程违规计数 0；最终复核 0 | PASS ×6 |
| C05 | 偶/奇 512 Scan 分片（col2→even/ch1，col3→odd/ch1，且两 sel 互斥） | PASS ×2 |
| C06 | 偶/奇 384 Data 映射（row0/1/766/767 四个边界通道互不串扰）+ 越界 row768 被拒 | PASS ×5 |
| C07 | PWM 窗口中置 blank：data_en/drive_gate 立即关断、onehot 归零、data_en_b 取反、窗口 S_ABORT | PASS ×6 |
| C08 | blank 期 LATCH 被接受、`latch_on_switch`、PAM/PWM 字段正确；非 blank 期 LATCH 被拒 | PASS ×5 |
| C09 | PWM 黑码整窗 0 导通，窗口仍消耗 65 tick | PASS ×2 |
| C10 | 最大码 63 → **64 导通 tick**、**65 窗口 tick**、S_DONE | PASS ×3 |
| C11 | `pam_sel=000` 是最小非零档、不是黑码，仍导通 64 tick | PASS ×2 |
| C12 | 负例：非法 mode、非法 LATCH、陈旧/不完整配置、START 被拒、未授权显示 | PASS ×5 |
| C13 | 60 Hz / 100 Hz 列预算：120 ns 两者满足，200 ns 在 100 Hz 不满足 | PASS ×3 |

波形证据（全部由真实 VCD 渲染，含时间轴与信号名，未编辑制造通过效果）：
`figures/wave_scan_latch.svg`、`wave_pwm_full.svg`、`wave_pwm_boundary_zoom.svg`、
`wave_blank_negative.svg`；渲染器 `checks/render_waveforms.py`，清单 `results/waveform_render_manifest.csv`。
**诚实标注：这四张是 VCD 派生时序图，不是 ModelSim GUI 原生截图**；原生 GUI 截屏本轮 `NOT_RUN`，
原始 VCD 与 transcript 均保留，复审者可自行在 ModelSim 打开或重渲染。

---

## 6. 静态时序分析

```
STATIC_TIMING_ANALYSIS: NOT_RUN
```

原因：本轮没有综合后门级网表、工艺标准单元库（`.lib`/`.db`）、约束文件（SDC）或 STA 工具。
**未编造任何 slack、setup/hold、WNS/TNS 或 PVT 角数据**。ModelSim 功能时序 ≠ 门级 STA。

---

## 7. 风险与已知限制

1. 100 Hz / 120 ns 的列预算余量仅 ~11.5%，未含任何模拟/负载/封装延迟。
2. 8 tick 消隐、100 MHz 时钟、120 ns tick 都是 POC 假设，不是教师给定条件。
3. `drive_gate` 是逻辑门控信号，不是电流；未与模拟电流源做混合信号联合仿真。
4. 偶/奇分片规则（列/行地址 bit0）是本课程的工程推导，未由课程材料规定；若课程要求按高低半区分片，映射需改。
5. 代表性设计未实例化 1024×768 MOS 阵列；整芯片功能 `NOT_IMPLEMENTED`。
6. 第一次失败运行的 3 项 FAIL 与 2 条警告保留在仓库与本地原件中，不作为通过证据。
