# CE 反例测试计划（CE_TEST_PLAN）— rev2：拆成两层

日期：2026-11-19　状态：**计划，未执行**。T6-A 的 2 次 ModelSim 已用尽；
本文件是"下一阶段申请预算时跑什么、怎么判、怎么保证不空洞"的依据。

---

## 0. 为什么拆成两层（rev1 的两处冲突）

| rev1 的问题 | 事实 | rev2 的处理 |
|---|---|---|
| CE3 要求"W1C 与 CTRL 在同一个 core 沿" | 一笔 SPI 事务只有一个地址，`wr_cap_o` 是单拍脉冲，**不可能同沿写两个寄存器** | 改为"**一个合法 CTRL 帧的 CS 上升沿**与**异步故障沿**临界"——这才是真实可达的同沿 |
| CE1/CE4 要"真实 LED 通道导通/恢复非零" | 被测顶层 `tcon_spi_top` **没有 Data/Scan 输出**，也没有帧/预充 | 拆成 **L1 SPI 单元安全**（只看许可）与 **L2 五芯片系统安全**（看 `ch_en`/PAM），L2 另立预算 |

**结论：`tcon_spi_top` 上的断言只能说"许可为 0/1"，不能说"灯亮/灭"。**

---

## L1 · SPI 单元安全（被测：`tcon_spi_top` + 候选补丁）

共同前提：core 100 MHz；SCLK 10/4 MHz；core 相位 0/2.5/5/7.5 ns；
CS 高间隔 ≥ 100 ns（另设 100 ns 边界一档）；四态精确比较；每个 core 沿采一次。

### L1-CE1 故障出现→源撤去→无 W1C→无再使能

| 步 | 动作 |
|---|---|
| 1 | 复位释放，`status_in={SAFE,READY}=1` |
| 2 | 写 `CTRL=0x3`，再写 `CTRL=0x1` → **记录 `hw_blank=0` 的非空洞样本** |
| 3 | `hw_fault[0]`（UVLO）保持 3 个 core 沿 |
| 4 | 撤去故障，**不发任何 SPI 事务**，持续 ≥ 200 沿 |

判据：第 3 步后 1 ns 内 `hw_blank===1`；第 4 步全程 `hw_blank===1`、`disp_armed===0`、
`hw_fault_caught===1`、`fault_status[0]===1`。**不允许出现 `hw_blank===0` 的采样。**

非空洞：第 2 步必须实测到 `hw_blank===0`（`lit_permit_samples > 20`），
否则"从来没亮过"也能过。**这里是"许可样本"，不是"LED 导通样本"。**

### L1-CE1a 短脉冲（**本轮的 P0**）

| 步 | 动作 |
|---|---|
| 1 | 同 CE1 步骤 1–2（`hw_blank=0`） |
| 2 | `hw_fault` 拉低 **2 ns / 4 ns / 8 ns**，每档分别对齐到 core 沿前 1/3/5/9 ns |
| 3 | 故障撤去，不发任何 SPI 事务 |

判据：脉冲结束后**立刻**（同一 ns 内）`hw_blank===1` 且 `hw_fault_caught===1`；
其后 200 沿全程为 1。
**这一档必须真的让脉冲落在两个沿之间**，TB 要在 transcript 打印脉冲起止与两侧 core 沿时间戳，
证明没有沿落在脉冲内（否则测的是"侥幸"情形）。

### L1-CE2 清状态但不重新使能

| 步 | 动作 |
|---|---|
| 1 | 同 CE1 步骤 1–3 |
| 2 | 撤去故障源 |
| 3 | 写 `FAULT_STATUS=0x1`（W1C），读回确认 bit0=0 |

判据：`fault_status[0]===0` 且 `hw_fault_caught===0`（清干净了）但
`disp_armed===0`、`hw_blank===1` 全程保持。
非空洞：读回必须真是 0；且 CE4 证明同一 W1C 之后**加**一次再使能确实能恢复，
说明 W1C 本身有效（不是写不进去）。

### L1-CE3 故障有效时写 CTRL=EN1/BLANK0

判据：`err_reg===1`、`en`/`blank_r` 不变、`disp_armed===0`、`hw_blank===1`。

### L1-CE3b 临界沿：CTRL 帧的 CS 上升沿与异步故障重合

| 步 | 动作 |
|---|---|
| 1 | `hw_blank=0`（已使能） |
| 2 | 发一笔**合法** CTRL=0x1，把 CS 上升沿对齐到 `hw_fault[3]` 的下降沿 ±1 ns（三档） |
| 3 | 故障撤去，等 4 个沿 |

判据：`err_reg===1`（写被拒）、`disp_armed===0`、`hw_blank===1` 之后不回落。
**不允许出现"故障已走、`disp_armed` 却是 1"**——这正是 NC-C 要抓的。

### L1-CE4 清状态 + 显式再使能（唯一允许恢复的入口）

判据：`disp_armed` 0→1、`hw_blank` 1→0；读回 `CTRL` 确认 `EN=1,BLANK=0` 真写进去了。
**不判 LED**（那是 L2）。

### L1-CE5 读事务 / 坏帧 / INT_EN=0

判据：`hw_blank` 恒 1；`disp_armed` 恒 0。
结构补充（静态门）：`hw_blank` 表达式不含 `rd_*`、`int_en`、`mb_*`。

### L1-CE6 复位与相位

| 子项 | 内容 |
|---|---|
| 6a | 复位在故障保持期间异步断言：`hw_blank` 立即 1；释放后 `disp_armed===0`、`hw_blank===1` |
| 6b | 复位在显示许可期间断言再释放：必须重新写 CTRL 才能恢复，不许自恢复 |
| 6c | 976/977 槽长无关（本层不涉及），改为 SCLK 10/4 MHz × 4 相位 × 三档脉宽 |

---

## L2 · 五芯片系统安全（**另一套环境、另一次预算**）

需要"带 SPI 的 `tcon_top` + 2×Data + 2×Scan"。本轮**没有**这个环境（P1-D）。

| 用例 | 判据 |
|---|---|
| S1 | 故障前：某列 768 路里有非零 `ch_en`，PAM 与 LUT 一致（非空洞） |
| S2 | 故障脉冲（4 ns）→ 下一个显示窗 768 路 `ch_en` 全 0，且**连续 ≥ 3 个窗** |
| S3 | 故障撤去 + W1C + 不再使能 → 继续全暗（≥ 3 窗） |
| S4 | + 显式再使能 → **重新预充（2 个 LATCH）后**才出现非零导通，且第一窗的列号/帧号正确 |
| S5 | 复位后：必须重新走完整序列（配置 → 预充 → 使能）才亮 |

**L2 不得用 L1 的断言冒充**：`hw_blank` 只是两把钥匙中的一把，另一把（帧/预充）在 `tcon_top`。

---

## 断言清单（L1，新增，预计 16–20 条）

| 建议名称 | 判据 |
|---|---|
| `E01_ce1_permit_reached_zero` | 步骤 2 有 `hw_blank===0` 采样（≥20） |
| `E02_ce1_fault_gone_stays_dark` | 步骤 4 无 `hw_blank===0` 采样 |
| `E03_ce1a_short_pulse_caught` | 脉冲结束时 `hw_blank===1` 且 `hw_fault_caught===1` |
| `E04_ce1a_pulse_between_edges` | transcript 时间戳证明脉冲内无 core 沿 |
| `E05_ce1a_2ns/4ns/8ns_all_caught` | 三档 × 四相位全过 |
| `E06_ce2_w1c_only_stays_dark` | `caught=0 && armed=0 && blank=1` |
| `E07_ce3_unblank_during_fault_rejected` | `err_reg=1 && armed=0` |
| `E08_ce3b_critical_edge_rejected` | 同上，三档 ±1 ns |
| `E09_ce3b_no_late_rearm` | 故障走后 `armed` 仍为 0 |
| `E10_ce4_reenable_sets_permit` | `armed` 0→1、`hw_blank` 1→0 |
| `E11_ce4_readback_confirms` | 读回 CTRL = 0x1 |
| `E12_ce5_int_en_zero_no_bypass` | `hw_blank` 恒 1 |
| `E13_ce5_reads_no_bypass` | 5 次读事务后仍暗 |
| `E14_ce5_bad_frames_no_bypass` | 30/47/49 沿帧后仍暗 |
| `E15_ce6_reset_clears_permit` | 复位后 `armed=0 && blank=1` |
| `E16_caught_latch_is_sticky` | 单次脉冲后 200 沿仍为 1 |

门槛：`MIN_ASSERTS` 必须等于实际执行条数（沿用 RUN02 纪律）。

---

## 负控（每项都要写清"哪个断言真的会失败"）

| 编号 | 注入 | 必须失败的断言 |
|---|---|---|
| NC-1 | 删 `disp_armed` 项 | `E06`（W1C 后 `hw_blank` 变 0） |
| NC-2 | 删 `hw_fault_caught` 项 | `E03`（脉冲结束后 `hw_blank` 变 0） |
| NC-3 | CTRL 准入去掉 `!any_hw_fault` / `!hw_fault_caught` | `E08` / `E09` |
| NC-4 | `hw_fault_caught` 的置位改回 `posedge clk` | `E05`（2/4 ns 失败） |
| NC-5 | `clr_fault` 改为无条件（不看 `n_fault==0`） | `E06`（逐位未清就放行） |

rev1 只写了"预期可能失败"，本轮改为**逐项绑定到具体断言**。

---

## 预算与准入

- 不占用 T6-A 已用尽的 2 次；需**新申请 L1 定向预算 1 次**（失败即停）。
- L2 需要独立环境与独立预算，不与 L1 混合。
- 准入前必须先通过：`vlog` 0/0、`tools/t6a_p0_rearm_check.py` 与
  `tools/t6a_p0_async_fault.py` 全过（含三个负控）、静态门（文本级负控）。
- 若 `cs_n` 与 core 同沿（L1-CE3b）在数字域给不出确定结论，
  **停在 `WAITING_FOR_P0_ASYNC_CAPTURE_ARCH_DECISION`**，不许试跑碰运气。
