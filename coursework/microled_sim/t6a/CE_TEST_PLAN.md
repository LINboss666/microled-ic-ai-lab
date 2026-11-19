# CE 反例测试计划（CE_TEST_PLAN）— rev3

日期：2026-11-19　状态：**计划，未执行**。T6-A 原预算 2/2 已用尽；本轮 0 次 vsim。
L1 需要**新阶段定向预算 1 次**（独立审批），L2 另开环境。

---

## 0. 分层不变（L1 / L2），但 L1 的边界要重新说清

| 层 | 被测 | 能判 | **不能判** |
|---|---|---|---|
| L1 | 候选 `tcon_spi_top`（含新增 `fault_n` 端口） | `hw_blank`、`disp_armed`、`hw_fault_caught`、`FAULT_STATUS`/`INT_STATUS` 读回 | 引脚 BLANK、Data/Scan 真实导通、预充 |
| L2 | TCON+2Data+2Scan（带 SPI） | 真实 `ch_en`/PAM、重新预充、恢复显示 | — |

rev2 的一条错误要在本轮明确：**L1 不能声称"灯亮了/没亮"**，只能说"许可为 1/0"。
所以下面每条用例都写明"非空洞"用的是哪一类样本。

---

## 1. 共同前提

core 100 MHz；SCLK 10/4 MHz；core 相位 0/2.5/5/7.5 ns；CS 高 ≥ 100 ns；
四态精确比较；每个 core 沿采一次；`MIN_ASSERTS` 等于实际条数。

---

## 2. L1 用例

### E01–E16（rev2 保留）

显示许可先到 0 → 故障出现 → 源撤去 → W1C → 再使能；含 2/4/8 ns 短脉冲、
临界沿、复位、读/坏帧/int_en 不得绕过。判据与 rev2 相同，不再重复。

### E17 短脉冲必须"读得到"（rev3 新增，P0）

| 步 | 动作 |
|---|---|
| 1 | 合法使能，`hw_blank=0`（记 `permit_low_samples`） |
| 2 | `fault_n` 拉低 **4 ns**，确保**没有任何 core 沿落在脉宽内**（transcript 打印两侧沿时间戳） |
| 3 | 脉冲结束，等 ≥ 3 个 core 沿 |
| 4 | 读 `0x0C`、`0x10` |

判据：
- `fault_status[7]===1`（COMM_TO），读回 `0x0C` 的 bit7 为 1；
- `int_status[7]===1`，读回 `0x10` 的 bit7 为 1；
- `hw_blank===1`、`disp_armed===0` 全程；
- `fault_vis_o[7]===1`（观测口与寄存器一致）。

非空洞：第 1 步必须有 `hw_blank===0` 的采样（否则"一直黑"也能过）。

### E18 W1C=0 不得清除（rev3 新增，P0）

| 步 | 动作 |
|---|---|
| 1 | 同 E17 步骤 1–3（捕获位=1、状态 bit7=1） |
| 2 | 写 `FAULT_STATUS = 0x0000_0000`（合法 48 沿写帧） |
| 3 | 等 ≥ 3 沿，再读 |

判据：`hw_fault_caught===1`、`fault_status[7]===1`、`hw_blank===1` —— **三项都不许变**。
负控：删掉 `w1c_f[7]` 条件 → 本用例必须 FAIL（且是 `caught`/状态真实变化，不是"黑屏"）。

### E19 部分掩码不得清掉别的原因（rev3 新增）

| 步 | 动作 |
|---|---|
| 1 | 制造两个原因：`hw_fault[0]`（UVLO）持续 ≥ 3 沿 → 撤去；再 4 ns 脉冲（→bit7） |
| 2 | 写 `FAULT_STATUS = 0x001` |
| 3 | 读回 |

判据：bit0 清 0，**bit7 仍为 1**，`hw_fault_caught===1`，`hw_blank===1`。
负控：把 `clr_fault` 条件从 `w1c_f[7]` 改回 `n_fault==0` → 本用例 FAIL。

### E20 清除与新脉冲同沿（rev3 新增）

| 步 | 动作 |
|---|---|
| 1 | 捕获位=1、状态 bit7=1 |
| 2 | 在**同一个 core 沿**：写 `FAULT_STATUS=0x080`，同时 `fault_n` 再拉低 4 ns（跨该沿） |
| 3 | 等 ≥ 3 沿 |

判据：`hw_fault_caught===1`（set 优先）、`fault_status[7]===1`、`hw_blank===1`。
TB 必须在 transcript 打印该沿时间戳与脉冲起止，证明"同沿"。

### E21 真实 `FAULT_n` 极性（rev3 新增）

候选 `tcon_spi_top` 新增了 `fault_n` 端口，因此 L1 **可以**驱动真实引脚：

| 步 | 动作 |
|---|---|
| 1 | 保持 `hw_fault=0`，只用 `fault_n=0` 拉低 4 ns |
| 2 | 检查捕获与读回 |

判据：`hw_fault_caught===1`、`fault_status[7]===1`。
（若 L1 平台最终没有 `fault_n` 端口，则本条降级为"L2 才能验证"，**不得**声称已验证。）

### E22 停钟保持（rev3 新增）

| 步 | 动作 |
|---|---|
| 1 | 合法使能，`hw_blank=0` |
| 2 | 停止 core 时钟（不再有 `posedge clk`） |
| 3 | `fault_n` 拉低 10 ns 再释放，**整段没有任何 core 沿** |
| 4 | 恢复时钟，等 3 沿 |

判据：第 3 步全程 `hw_blank===1`（组合项 + 异步锁存），`disp_armed` 保持 0；
第 4 步后仍为 1（clear 从未发生）。

---

## 3. 恢复实验（防止"永远黑屏也 PASS"）

| 步 | 动作 | 判据 |
|---|---|---|
| R1 | 清掉所有原因（掩码覆盖全部在置位） | `hw_fault_caught===0`、`disp_armed===0`、`hw_blank===1` |
| R2 | 一次显式 `CTRL=0x1`，`SAFE/READY` 有效 | `disp_armed===1`、`hw_blank===0`（记 `permit_low_samples>0`） |
| R3 | 读回 `CTRL` | 等于 `0x0000_0001`（真写进去了，不是读失败得 0） |

**没有 R2 的 `hw_blank=0`，E01–E22 的"黑屏"判据全部不可采信。**

---

## 4. 断言总表（L1，预计 24–28 条）

| 名称 | 判据 | 对应缺口 |
|---|---|---|
| E01/E02 | 许可先 0 后故障后保持 1 | 基础 |
| E03/E04/E05 | 2/4/8 ns × 四相位都捕获；脉冲内无 core 沿 | P0-B |
| E06/E07/E08/E09 | W1C-only 仍黑、故障中 unblank 被拒、临界沿被拒 | 再使能 |
| E10/E11 | 再使能后 `armed` 0→1、读回确认 | 恢复 |
| E12/E13/E14 | int_en=0 / 读 / 坏帧不得绕过 | 旁路 |
| E15/E16 | 复位清许可、捕获粘滞 | 复位 |
| **E17** | **短脉冲后 `FAULT_STATUS[7]`/`INT_STATUS[7]`=1** | **可读性** |
| **E18** | **W1C=0 后 `caught`/bit7 不变** | **清除协议** |
| **E19** | **部分掩码只清被覆盖位** | **清除协议** |
| **E20** | **同沿新脉冲胜过清除** | **优先级** |
| **E21** | **`fault_n` 端口可达同一捕获路径** | **引脚** |
| **E22** | **停钟保持** | **死时钟** |

---

## 5. 负控（每条必须绑定到真的会失败的断言）

| 编号 | 注入 | 必须失败 | 失败现象 |
|---|---|---|---|
| NC-1 | 删 `disp_armed` 项 | E06 | W1C 后 `hw_blank` 1→0 |
| NC-2 | `caught` 不并入 `n_fault` | **E17** | 读回 bit7=0 |
| NC-3 | `clr_fault` 去掉 `w1c_f[7]` | **E18、E19** | `caught` 被写 0 清掉 |
| NC-4 | `clr_fault` 去掉 `!any_hw_fault` | E07/E20 | 活故障中被清 |
| NC-5 | 异步置位改回 `posedge clk` | E03/E05/E22 | 2/4 ns 丢失、停钟不保持 |
| NC-6 | `hw_fault_i` 漏掉 `fault_n` 取反 | E21 | 引脚拉低无效 |

rev2 把 NC 绑在"清完之后必须黑屏"（E06）上是错的：那条在"一直黑"时也成立。
rev3 全部改绑到**状态位本身**（bit7 / `caught`）。

---

## 6. 准入与预算

- 准入前：`vlog` 0/0 + 三个模型（`t6a_p0_async_fault.py`、`t6a_p0_rearm_check.py`、
  `t6a_p0_edge_matrix.py`）全过且负控有效；
- TB 必须先补 `.fault_n` 端口（RUN02 的 TB 没有这个脚，直接跑会 elaborate 失败）；
- 预算：**新申请 L1 定向 1 次**，失败即停，不占 T6-A 的 2/2；
- 若 `cs_n` 与 core 同沿（E08）在数字域给不出确定结论，停在
  `WAITING_FOR_P0B_REVISED_ZERO_SIM_ARCH_REVIEW`，不许试跑。
