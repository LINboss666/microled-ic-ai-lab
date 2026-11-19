# T6-A P0-B：异步故障捕获 + 再使能候选（零 ModelSim）

日期：2026-11-19　预算：**本轮 0 次 vsim**（T6-A 的 2/2 已在 RUN02 用尽）
状态：`WAITING_FOR_P0_ASYNC_CAPTURE_ARCH_DECISION`

---

## 1. 结论摘要

| 复审裁定 | 本轮回应 |
|---|---|
| `ASYNC_FAULT_CAPTURE = OPEN_P0` | 已复现（逐 ns 时间线 + 32 组脉宽/相位扫描），并给出**异步置位/同步清除**方案 |
| `HOST_REARM_DESIGN = APPROVED_IN_PRINCIPLE` | 保留两把锁，新增 `hw_fault_caught`，改成六项 OR |
| v1 模型"先更新 `fault_status` 再判准入"不符合 RTL | 已重写为 **NBA 语义**（旧值算组合、块末提交），v1 归档 |
| `SPI_ERROR_VISIBILITY = OPEN_P1` | rev1 的"随写 epoch 携带"被证明**失效**；改为独立的 toggle 事件线 |
| CE 计划两处执行冲突 | 已拆成 **L1 SPI 单元** 与 **L2 五芯片系统** 两层 |
| 是否允许改 RTL | 只在**独立分支**试应用候选补丁，`course/…` 分支四个已验收文件 SHA 未变 |

---

## 2. P0-B 的复现（这是本轮的核心证据）

`tools/t6a_p0_async_fault.py`，`FAULT_n` 在 12 ns 拉低、16 ns 释放（4 ns），
`clk_ref` 沿在 10 / 20 ns：

| t (ns) | clk 沿 | fault_n | state | tcon_blank | panel_blank |
|---:|---:|---:|---|---:|---:|
| 10 | 1 | 1 | ACTIVE | 0 | 0 |
| 12 | 0 | **0** | ACTIVE | **1** | 1 |
| 15 | 0 | 0 | ACTIVE | 1 | 1 |
| 16 | 0 | 1 | **ACTIVE** | **0** | 0 |
| 20 | 1 | 1 | **ACTIVE** | 0 | **0** |

**"关断"发生了，"锁存"没有。** 与复审给出的静态时间线逐行一致。

脉宽 / 相位扫描（宽 1/2/4/8/9/10/11/20 ns × 相位 0/2.5/5/7.5 ns）：

| 宽 (ns) | fsm_only | sync_only | async_set |
|---:|---|---|---|
| 1 / 2 / 4 | 仅相位 5.0 侥幸捕获，其余丢失 | 同左 | **全部保持关断** |
| 8 / 9 / 10 | 部分相位捕获 | 同左 | **全部保持** |
| 11 / 20 | 部分相位捕获 | 同左 | **全部保持** |

→ **加一个"core 采样的粘滞位"没有用**（`sync_only` 与 `fsm_only` 结果一致）；
必须让**置位走故障边沿**。

---

## 3. 方案：异步置位 / 同步清除

```verilog
always @(posedge clk or posedge any_hw_fault or negedge reset_n) begin
    if (!reset_n)          hw_fault_caught <= 1'b0;
    else if (any_hw_fault) hw_fault_caught <= 1'b1;
    else if (clr_fault)    hw_fault_caught <= 1'b0;
end
```

`hw_blank` 从三项变六项：

```
hw_blank = blank_r | !en | any_hw_fault | hw_fault_caught | !disp_armed | disp_fault
```

四条性质都用模型验证过：

| 性质 | 模型结果 |
|---|---|
| 任意宽脉冲都被捕获 | 32/32 组合保持关断 |
| 源消失后不自恢复 | CE1 全程 `hw_blank=1` |
| 清状态后仍不点亮 | CE2：`caught=0 && armed=0` → 仍为 1 |
| 时钟停住也不能清 | CE7：无时钟沿 → `caught` 仍为 1 |

---

## 4. NBA 语义的单沿矩阵（24 组，`EDGE_MATRIX_CONTROL.csv`）

关键几行（`blank_*` 用同一 `hw_fault` 输入算，便于对照）：

| start | ctrl | w1c | hw_fault | blank_old | blank_new | 拒绝 | 新状态 |
|---|---|---|---:|---:|---:|---:|---|
| ARMED | – | 0x000 | 0x008 | 1 | 1 | 0 | armed=0 caught=1 |
| ARMED | 0x1 | 0x000 | 0x008 | 1 | 1 | **1** | fault=0x108（ERR_REG） |
| DARK | – | 0x001 | 0x000 | 1 | 1 | 0 | **armed=0 caught=0**（清干净也不亮） |
| CLEARED | – | 0x001 | 0x000 | 1 | 1 | 0 | armed=0 |
| CLEARED | 0x1 | 0x000 | 0x000 | 1 | **0** | 0 | armed=1 ← 唯一恢复入口 |
| CLEARED | 0x1 | 0x000 | 0x008 | 1 | 1 | **1** | armed=0 caught=1 |

脚本里三条断言：live fault 下 unblank 必被拒；任何纯 W1C 都不能让 `blank` 1→0；
只有 `CLEARED + ctrl=0x1 + 无故障` 能 1→0。全过。

---

## 5. P1 的修正（rev1 方案失效）

rev1 的"`wr_flags` 随写 epoch 携带"在最需要它的场景下失效：
47/49 位坏帧 `bc != 48`，**不翻 `wr_tog`**，core 永远收不到。

改为**独立的 toggle 事件线**（`bad_tog` / `lost_tog`），与写邮箱同构但不共享，
并给出"47 位坏帧 → 立刻读 `FAULT_STATUS[8]`"的时序推演：

```
T+0      bad_tog 翻转（cs_n 域）
T+30ns   err_set → fault_status[8] <= 1（2FF + 捕获）
T+1700ns 最早可能的读数据相位（CS 高 100 ns + 16 bit 命令 @10 MHz）
```

**余量 56×**，任何合法 CS 高间隔下"坏帧后马上读"都能读到 `ERR_REG=1`。
代价：`ERR_REG` 只有 1 bit，分不清"坏长度"与"丢帧"；要分清需新增只读诊断寄存器（规格扩展，未做）。

---

## 6. CE 计划的两处修正

| rev1 | 问题 | rev2 |
|---|---|---|
| CE3 "W1C 与 CTRL 同沿" | 一笔事务只有一个地址，`wr_cap_o` 单拍，不可能同沿写两个寄存器 | 改为"CTRL 帧的 CS 上升沿"与"异步故障沿"临界 ±1 ns |
| CE1/CE4 判"真实导通/恢复非零" | `tcon_spi_top` 没有 Data/Scan 输出 | 拆成 L1（只看许可）与 L2（五芯片，另立预算）；L1 的断言只允许说 `hw_blank`，不得说灯 |

负控也从"预期可能失败"改为**逐项绑定断言**：NC-1→E06、NC-2→E03、NC-3→E08/E09、
NC-4→E05、NC-5→E06。

---

## 7. 候选补丁

| 项 | 值 |
|---|---|
| 文件 | `t6a/SUGGESTED_PATCH.diff.txt`（`tcon_spi_regs` + `tcon_spi_top`） |
| 规模 | `tcon_spi_regs` +49/−3 行；`tcon_spi_top` +5/−2 行 |
| 应用 | 只在**独立分支** `t6a-p0-candidate-20261119` 试应用 |
| 编译 | `vlog` **0 errors / 0 warnings** |
| `course/…` 分支 | RTL **未改**，四个源文件**内容**与 RUN02 运行时一致。`tcon_spi_regs` 在清单里是 CRLF（`bdde768a…`），新 checkout 因 `eol=lf` 为 LF（`05aaabbe…`），规范化后相同 |

---

## 8. 仍未完成（不要按已完成理解）

1. **没有 ModelSim**：候选补丁**未**在动态仿真下验证；57 条旧断言在新候选下的表现**未知**；
2. **顶层 `ST_FAULT` 退出策略**未改（属 T5 代码），"Host 再使能"在集成前后仍不一致；
3. **P1 未实施**：`mb_lost` / `mb_badlen` 仍不可经 SPI 读回；
4. **CDC/STA**：`cs_n` 作为功能时钟仍无约束；异步置位路径需要 STA 给出 recovery/removal 检查；
5. **L2 系统级安全**：没有"带 SPI 的五芯片"环境；
6. CE1–CE6 全是**计划**，未执行、未 PASS。

---

## 9. 下一步

建议同时提交两件事等审核：
1. 异步捕获方案（§3）与死时钟论证（§3 表）是否接受；
2. CE 分层（§6）与预算边界是否接受。

两项都点头后，再申请 **L1 定向预算 1 次**。

**终态：`WAITING_FOR_P0_ASYNC_CAPTURE_ARCH_DECISION`。不自签 `P0_CLOSED`。**
