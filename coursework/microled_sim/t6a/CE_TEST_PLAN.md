# CE 反例测试计划（CE_TEST_PLAN）

日期：2026-11-19　状态：**计划，未执行**。T6-A 的 2 次 ModelSim 预算已用尽；
本文件只是"下一阶段申请预算时要跑什么、怎么判、怎么保证不空洞"的依据。

> 所有 CE 都**不得**登记为 PASS。当前的 P0 关闭证据只有
> `tools/t6a_p0_rearm_check.py` 的**状态模型**推导，不是仿真。

---

## 0. 共同前提

| 项 | 值 |
|---|---|
| DUT | `tcon_spi_top`（打上 `SUGGESTED_PATCH.diff.txt` 后的版本，需先批准） |
| 时钟 | core 100 MHz；SCLK 10 MHz 与 4 MHz 两档 |
| 相位 | core 相位 0 / 2.5 / 5 / 7.5 ns 四种（沿用 RUN02 的做法） |
| 槽长 | 976 / 977 两种（沿用 T3/T5 的混合槽长） |
| CS 高间隔 | ≥ 100 ns（合同值），另设一档 100 ns 边界、一档 60 ns（违规） |
| 观测 | `en`、`blank_r`、`hw_blank`、`fault_status`、`disp_armed`、`int_status`、`irq`、`err_reg`；**以及驱动侧真实的 `ch_en`/`ch_pam`**（非空洞必需） |
| 采样 | 每个 core 上升沿采一次，四态精确比较（X 与 1 一样算违规） |

---

## CE1 显示中故障脉冲撤去后持续熄屏

**目的**：堵住本轮 P0 的直接反例。

| 步骤 | 动作 |
|---|---|
| 1 | 复位释放，`status_in={SAFE,READY}=1` |
| 2 | 写 `CTRL=0x3`（EN=1,BLANK=1），再写 `CTRL=0x1`（EN=1,BLANK=0）→ 合法显示 |
| 3 | 注入 `hw_fault[0]`（UVLO）保持 **≥ 1 个 core 沿**（另做 3 沿、10 沿两档） |
| 4 | 撤去 `hw_fault[0]`，**不发任何 SPI 事务**，持续 ≥ 200 个 core 沿 |

**判据**
- 第 3 步：故障出现后 **1 ns 内**（组合门）`hw_blank===1`；
- 第 4 步：整段 `hw_blank===1`、`en===1`、`blank_r===0`、`fault_status[0]===1`、`disp_armed===0`；
  **一次 `hw_blank===0` 的采样都不允许**。

**非空洞**：第 2 步必须实测到 `hw_blank===0` 且驱动侧 `|ch_en===1`（否则"一直是黑的"也能过）。
建议断言：`lit_samples > 300` 且 `dark_violations == 0`。

**会失败的负控**：删掉 `disp_armed` 与 `disp_fault` 两项（回到 RUN02 表达式）→ 第 4 步出现 `hw_blank===0` → CE1 报错。

---

## CE2 清故障状态但不重新使能，仍熄屏

**目的**：验证 V1.3 段0965「清状态不自动恢复显示」。

| 步骤 | 动作 |
|---|---|
| 1 | 同 CE1 步骤 1–3（OV，`hw_fault[1]`） |
| 2 | 撤去故障源 |
| 3 | 写 `FAULT_STATUS=0x2`（W1C） |
| 4 | 读回 `0x0C` 确认 bit1=0；**不写 CTRL**，持续 ≥ 200 沿 |

**判据**：`fault_status[1]===0` 且 `hw_blank===1` 且 `disp_armed===0` 全程成立。

**非空洞**：读回必须真的是 0（不是读失败得 0）；另一方向：CE4 里同样的 W1C 后**加**一次再使能必须能亮，说明 W1C 本身有效。

**负控**：删掉 `disp_armed` 项、只保留 `disp_fault` → 第 4 步 `hw_blank===0` → 报错。

---

## CE3 有故障 / W1C 同沿时写 CTRL 不可点亮

| 步骤 | 动作 |
|---|---|
| 1 | 注入 `hw_fault[2]`（OT），保持 |
| 2 | 写 `CTRL=0x1`（EN=1,BLANK=0），SAFE/READY 都在 |
| 3 | 另一档：`hw_fault[2]` 撤去与 W1C **同一个 core 沿**，同沿再写 `CTRL=0x1` |
| 4 | 另一档：`hw_fault[...]` 撤去、W1C 已做，但同一笔写把 `BLANK` 置 1 又置 0（两次连续写） |

**判据**：`err_reg===1`、`en` 与 `blank_r` 不变、`disp_armed===0`、`hw_blank===1`；
第 3 档必须保证"同沿"真的同沿（TB 用 `@(posedge clk)` 精确对齐并在 transcript 打印该沿时间戳）。

---

## CE4 全部条件满足后才允许由暗到亮（非空洞）

| 步骤 | 动作 |
|---|---|
| 1 | 同 CE1 步骤 1–4（已暗） |
| 2 | W1C 清故障 |
| 3 | 写 `CTRL=0x1`（EN=1,BLANK=0），SAFE/READY=1，无故障 |
| 4 | 给一个合法帧（VSYNC+COL_SYNC+两级预充，若 DUT 只到 SPI 层则此步在 T5 集成用例里做） |

**判据**：`disp_armed` 由 0→1；`hw_blank` 由 1→0；**并且**驱动侧 `|ch_en` 出现非零采样
（`lit_samples > 300`），PAM 档位与 LUT 一致。

**这是唯一一个"必须变亮"的用例**——没有它，CE1/CE2 的"一直黑"就能骗过全部判据。

---

## CE5 INT_EN=0 / 读事务 / 坏帧都不能绕过

| 步骤 | 动作 |
|---|---|
| 1 | 处于故障后熄屏状态 |
| 2 | 写 `INT_EN=0`；做 5 次读事务（含读 `0x0C`、`0x18`、`0x24`）；发 2 个 30 沿短帧、1 个 49 沿长帧 |
| 3 | 检查 `hw_blank` |

**判据**：`hw_blank===1` 全程不变；`disp_armed===0`；
结构性补充：`hw_blank` 表达式里**不存在** `int_en`、`rd_req`、`mb_*` 任何输入（静态门已断言）。

---

## CE6 时钟相位与异步复位角落

| 子项 | 内容 |
|---|---|
| 6a | `cs_n` 上升沿与 core 沿**同刻/±1 ns**：写帧要么被完整接收、要么完全不接收，不允许"半帧被当帧" |
| 6b | 复位在故障保持期间异步断言：`hw_blank` 立即为 1，释放后仍为 1（`disp_armed` 复位值 0） |
| 6c | 复位在显示中异步断言，再释放：必须先写 CTRL 才能亮，不允许自恢复 |
| 6d | 976/977 两种槽长 × 四种 core 相位 × 两档 SCLK 的组合，各跑一遍 CE1 |

**判据**：所有子项 `hw_blank` 在此期间无 0 采样；6a 另需 `frames_sent == frames_captured`。

---

## 断言清单（新增，预计 14–18 条）

| 名称（建议） | 判据 |
|---|---|
| `E01_ce1_fault_gone_stays_dark` | CE1 第 4 步无 `hw_blank===0` 采样 |
| `E02_ce1_lit_before_fault` | CE1 第 2 步 `lit_samples > 300` |
| `E03_ce2_w1c_no_reenable_dark` | CE2 全程暗 |
| `E04_ce3_unblank_during_fault_rejected` | `err_reg===1`、`disp_armed===0` |
| `E05_ce3_same_edge_w1c_unblank` | 同沿仍被拒 |
| `E06_ce4_reenable_lights` | `hw_blank` 1→0 且 `lit_samples > 300` |
| `E07_ce5_int_en_zero_no_bypass` | `hw_blank` 恒 1 |
| `E08_ce5_bad_frames_no_bypass` | 短帧/长帧后仍暗 |
| `E09_ce6_async_reset_blank_immediate` | 复位沿后 ≤1 ns `hw_blank===1` |
| `E10_ce6_no_self_recovery_after_reset` | 释放后仍暗，直到 CTRL 写 |
| `E11_disp_armed_reset_zero` | 复位后 `disp_armed===0` |
| `E12_hw_blank_has_no_int_en_term` | 静态：表达式不含 `int_en`/`rd_*` |

**门槛**：`MIN_ASSERTS` 必须等于实际执行条数（沿用 RUN02 的纪律，不许用旧门槛掩盖新增断言）。

---

## 负控（必须能失败）

| 编号 | 注入 | 期望被抓到的地方 |
|---|---|---|
| NC-1 | 删 `disp_armed` 项，保留 `disp_fault` | CE2 |
| NC-2 | 删 `disp_fault` 项，保留 `disp_armed` | CE1（若 `disp_armed` 也被错误置位时）/ CE6a |
| NC-3 | 两项都删（= RUN02 表达式） | CE1 |
| NC-4 | `disp_armed` 置位条件去掉 `!any_hw_fault` | CE3 |
| NC-5 | `disp_armed` 清零条件去掉 `disp_fault` | CE2（在 W1C 之前先撤源的那一档） |

---

## 预算与准入

- 本计划**不占用** T6-A 已用尽的 2 次；需**重新申请**一个定向阶段预算（建议 1 次，失败即停）。
- 准入前必须先通过：静态门（含上述 NC 的文本级注入）+ 状态模型（`t6a_p0_rearm_check.py`
  扩到 CE1–CE6）+ `vlog` 0/0。
- 若 `cs_n` 与 core 同沿（6a）无法在数字域给出确定结论，**停在 `WAITING_FOR_SPI_ARCH_REVIEW`**，
  不得靠试跑碰运气。
