# T1 V1.3 合约单次回归报告（2026-11-14）

**基线** `fddecaf4c9c36e6c6d7b2072ab98055f7c93976f` ｜ **分支** `course/microled-assignment-sim-20261112` ｜ **main** 未动
**本轮 EDA**：ModelSim **1 次**（授权 1 次，已用完）｜ Spectre 0 ｜ MC 0 ｜ OA 0 ｜ STA `NOT_RUN`
**结果**：**FAIL**（40 条中 39 PASS / 1 FAIL，`fail-fast` 终止；剩余 15 条**从未执行**）
**状态**：`WAITING_FOR_T1_V13_INDEPENDENT_REVIEW`

---

## 0. 一句话

`SCEN=ALL` 跑到第 40 条断言时在 `T3_load_384_dclk_edges` 停下。
**这不是 RTL 缺陷**：用这次的原生 VCD 逐窗重算，每个完整装载窗内都有**恰好 384 个 DCLK 上升沿**
（win0/win2/win3/win4 全是 384）。
是**测试台的测量方式**把窗口起点那一个沿抹掉了：`@(posedge load_active); #1; load_edges = 0;`
——13 个窗口里有 11 个在 `load_active` 上升沿的同一时刻就有一个 DCLK 上升沿，
清零发生在 `t0+1 ns`，于是那一个沿被丢弃，计数变成 383。

按任务书「失败立即停止、不得重跑、不改判据后重跑」，**本轮到此为止，没有第二次运行**。

---

## 1. 运行前零仿真检查（全部通过，记录在案）

| 项 | 结果 |
|---|---|
| 分支 / HEAD / main | `course/microled-assignment-sim-20261112` / `fddecaf…` / `main` 未动 |
| 工作区 | 干净（提交前 `git status` 空） |
| 断言分布 | `RESET_FAULT 27` / `TIMEBASE 17` / `BOUNDARY 11` = **55**，与 `scen_min_asserts.sh` 一致 |
| `$dumpoff` | 在 `"ALL"` 分支里、`scen_boundary()` **之前** |
| VCD 阈值 | `VCD_LIMIT_MB=120`（本轮实测 **1.7 MB**） |
| `WALL_LIMIT_S` | 900（本轮实际 **< 1 s**） |
| 源文件 SHA-256 | 6 个 RTL 与 T2B-C Run A2 审计源**逐字节一致**（`tcon_top` = `0f8e9169…`） |
| T6 checker | 带 CHECK0..4 的正式版，`bash -n` 通过 |
| 编译预检查 | `Errors: 0, Warnings: 0`（不计预算） |

运行前**没有**修改任何 RTL / Testbench / 断言。只在 `run_tcon_t1.sh` 里加了两项**运行器侧**设施
（任务书 §1.3 明确要求）：运行前打印源文件 SHA-256、运行后按 120 MB 阈值判定 VCD 体积。
两者都不参与仿真语义。

---

## 2. 实际跑出来什么

```
COURSE_TCON_T1_SCENARIO=ALL
COURSE_TCON_T1_CONTRACT=V1.3_STARTUP_SAFETY
--- SCENARIO RESET_FAULT (V1.3 contract) ---
PASS R1_reset_blank_high / col_id_0 / no_latch / no_pwm_start / no_scan_stb / no_tick / no_load
PASS R2_unconfigured_blank_high / R2_unconfigured_no_stb
PASS R3_illegal_mode_blank_high
PASS R4_idle_no_video_blank_high          ← 旧 T1 的 R4 是相反的判据
PASS R4_idle_no_video_no_strobe
PASS R4_status_ready
PASS R4b_precharge_never_unblanks_early   ← 新增：两级预充完成前不撤 BLANK
PASS R4c_blank_low_after_precharge
PASS R5b_fault_during_latch_blank / no_latch / no_phantom_load
PASS R5c_load_running_before_fault / closes_load / clears_load_counter / blank
PASS R6_fault_latched_blank_high          ← 旧 T1 的 R6 是相反的判据（Q3=B 锁存）
PASS R5_fault_sticky_status
PASS R6_no_tick_while_blanked / R6_no_latch_outside_blank
PASS R7_reset_reprecharge_blank_low
--- SCENARIO TIMEBASE ---
PASS T0_permit_before_measure
SLOT len=977 ticks=64 latch=828 pstart=840 stb=880 pw=4
PASS T1_slot_len_976_or_977 / T1_ticks_64_per_window / T1_latch_offset_828
PASS T1_pwm_start_offset_840 / T1_scan_stb_offset_880 / T1_latch_pulse_40ns
PASS T1_no_tick_in_blank
PASS T2_dclk_100_edges_per_200_cycles / T2_dclk_period_20ns
PASS T3_load_starts_at_832 / T3_load_len_768_cycles
FAIL T3_load_384_dclk_edges   (t=169,845 ns)
COURSE_RTL_ASSERT_COUNT=40  FAIL_COUNT=1  RESULT=FAIL
```

`Errors: 1`（由 `$fatal` 产生，不是编译错误）；`Warnings: 0`；VCD 1,690,734 B。

**因此 `T6` 检查器的五条件必然不过**（`RESULT=PASS`、`FAIL_COUNT=0` 两条不成立），
`RUNNER_EXIT=6`。这次没有"把失败报成通过"的空间。

---

## 3. `T3_load_384_dclk_edges` 的根因：**测量窗口边界，不是 RTL**

### 3.1 测试台的写法

```verilog
@(posedge load_active);
#1;
t_load0    = $realtime - 1.0;
sc_at_load = dut.slot_cycle;
load_edges = 0;                 // ← 在 t0 + 1 ns 清零
@(negedge load_active);
t_load1     = $realtime;
chk("T3_load_384_dclk_edges", load_edges == 384);
```

`load_edges` 由 `always @(posedge dclk) if (load_active) load_edges++` 累计。
装载窗是 `[cycle 831, cycle 1599)`，共 768 个参考周期 = **384 个 DCLK 上升沿**。

### 3.2 原生 VCD 逐窗重算（不读 Testbench 计数器）

```
load windows found: 13
  win0  t0=11,125 ns   t1=18,805 ns   dclk_edges_inside=384
  win2  t0=33,525 ns   t1=41,205 ns   dclk_edges_inside=384
  win3  t0=43,285 ns   t1=50,965 ns   dclk_edges_inside=384
  win4  t0=63,815 ns   t1=71,495 ns   dclk_edges_inside=384
windows whose rising edge carries a dclk posedge at the SAME timestamp: 11 / 13
```

**每个完整窗口都是 384 个沿**，RTL 完全正确。
但 13 个窗口里有 **11 个**在 `load_active` 上升沿的同一时刻就有 DCLK 上升沿；
`#1` 之后清零，正好把这一拍抹掉 → 实测 383 → 断言 384 失败。

（`T3_load_starts_at_832` 与 `T3_load_len_768_cycles` 同时 PASS，说明窗口的位置和长度都对，
唯一出问题的是"把边界沿算不算进去"这一件事。）

### 3.3 为什么旧 T1 一直是 49/49

旧 T1 的 `reset_dut` 是 `step(20)/step(40)`，`cfg_valid` 紧跟着使能，DCLK 与槽相位恰好落在
"窗口起点没有 DCLK 沿"的奇偶上，所以这条测量从来没暴露过。本轮把复位改成 2 µs（任务书要求 ≥1 µs）
并改了使能顺序，奇偶翻转，**潜在缺陷就露出来了**。

**这是测试台缺陷，不是被测设计缺陷**——但这不改变本轮判定：按任务书，失败即停。

---

## 4. 本轮真实证实了什么 / 没证实什么

**证实了（原生 transcript，非自述）**

1. 复位期间 `BLANK=1`、`COL_ID=0`、无 LATCH / PWM_START / SCAN_STB / TICK / load；
2. 未配置、非法 `cfg_mode` → `BLANK=1`、无选通；
3. **IDLE（配置就绪但无视频）→ `BLANK=1`、无选通**（`R4`，旧判据的反面）；
4. **两级预充完成前不撤 BLANK**（`R4b`，`early_unblank==0` 且 `latch_events>=2`），
   预充完成后正常撤 BLANK（`R4c`）；
5. LATCH 期间故障 → `BLANK=1`、`LATCH=0`、无幽灵装载；
6. 装载窗中故障 → 关窗、`load_cnt=0`、`BLANK=1`；
7. **恢复 `fault_n` 不解除故障**（`R6` 锁存，Q3=B）；复位 + 重新预充后恢复正常（`R7`）；
8. 时基与相位：`len=977`、`ticks=64`、`LATCH@828`、`PWM_START@840`、`SCAN_STB@880`、LATCH 脉宽 4 拍；
9. DCLK：200 拍内 99–101 个沿、周期 20.000 ns；
10. 装载窗起点 832、长度 768 拍。

**没证实（`fail-fast` 之后从未执行）**

| 未执行 | 条数 |
|---|---|
| `T3_load_starts_after_latch` | 1 |
| `T4_slot2_len_976_or_977` | 1 |
| `T5_slot3_len_976_or_977`、`T5_col_id_advancing` | 2 |
| `B0_no_unblank_before_precharge`、`B1`–`B10`（1024 槽整帧） | 11 |
| **合计** | **15** |

所以：**首帧 1024 槽、576 长 / 448 短、1,000,000 拍、`frame_wrap` 一次、`col_id` 周期** 这一整组
**本轮完全没有证据**。不得引用 T2B-C 的 1027 槽结果替代——那是另一个 TB、另一组判据。

---

## 5. 建议（不擅自执行）

按任务书，失败后不得改判据重跑，所以下面只是建议，等你裁定：

| 方案 | 内容 | 代价 |
|---|---|---|
| **A（推荐）** | 只改**测量方式**，不改判据：`load_edges` 改为自由计数 + 在 `@(negedge load_active); #1` 取 `e1`、在 `@(posedge load_active)` 之前的一个负沿取 `e0`，断言 `e1-e0 == 384`（窗口内的沿数不变，仍是 384） | 1 次 ModelSim |
| B | 判据改成 `load_edges >= 383 && load_edges <= 384` 并注明边界 | **不建议**：等于放宽判据 |
| C | 保持现状，把 `T3_load_384_dclk_edges` 记为"已知测量缺陷，RTL 由 VCD 证成" | 0 次仿真，但 T1 永远停在 FAIL |

我倾向 **A**：它是同一判据（384 个沿）、只把"边界沿算不算"这件事测对，
而且 `T3_load_starts_at_832` / `T3_load_len_768_cycles` 已经证明窗口本身没错。

---

## 6. 顺带修掉的一处文字残留（复审第 37 段）

`tb/tcon_t2b_tb.sv.txt` 里 `T2B_IDLE_BLANK` 那行的注释还写着 `registered, NOT compliant`，
与 T2B-C 的实测（`idle_blanklow_cycles=0`）矛盾。本轮把它改成如实描述。
**这是一条 `$display` 字符串，不含任何逻辑或判据**；`git diff` 只有那一行，且 T2B 的
Run A2 用的是改动前的 SHA（记录在 `runA2_source_sha256.txt`，可对照）。按复审意见不需要为此重跑。

---

## 7. Git / 交付

* 提交与推送见 §8；push 若遇传输失败登记 `REMOTE_PENDING`，不强推、不改历史、不动 main。
* 审核包含：本轮原生 `03_vsim.stdout`、`02_vlog.log`、`00_source_sha256.txt`、`05_t6_check.txt`、
  `tcon_t1.vcd`、runner 日志、VCD 逐窗复核脚本输出。

## 8. 裁定

| 项目 | 状态 |
|---|---|
| `T1_V13_SCEN_ALL` | **FAIL**（40 条中 39 PASS / 1 FAIL；15 条未执行） |
| `T1_V13_CONTRACT` | `FAIL_NOT_RUN_TO_COMPLETION`（不能写成 PASS，也不能写成 NOT_RUN） |
| `T3_load_384_dclk_edges` | `TB_MEASUREMENT_DEFECT`（VCD 证明 RTL 每窗 384 沿） |
| `T2B_STARTUP_SAFETY` | 维持 `ACCEPT_WITH_SCOPE`（本轮未回退） |
| `T2B_OVERALL` | 维持 `CONDITIONAL_ACCEPT` |
| 下一步 | **`WAITING_FOR_T1_V13_INDEPENDENT_REVIEW`**，未自动重跑、未改判据 |
