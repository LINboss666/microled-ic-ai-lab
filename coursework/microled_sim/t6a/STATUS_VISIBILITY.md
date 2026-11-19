# 错误状态可见性（STATUS_VISIBILITY）— rev2

日期：2026-11-19　针对 P1：`mb_lost` / `mb_badlen` 不可经四线 SPI 读回；
**且 rev1 的方案有一个硬伤**（复审 §E 指出）。

---

## 1. rev1 方案的硬伤

rev1 提议"把 `wr_flags[1:0]` 随写邮箱 epoch 一起送进 core"。这**不成立**：

```
spi_frame.v.txt（已验收）:
    end else if (bc == 6'd48 && !hdr_read) begin     // 只有"恰好 48 位的写帧"才翻 wr_tog
        ...
        wr_tog <= ~wr_tog;
```

47 位 / 49 位的坏帧 **`bc != 48`**，走的是 `else if (bc != 6'd48)` 分支——
它**只置 `mb_badlen`，不翻 `wr_tog`**。所以：

> 如果 Host 发完一个 47 位坏帧就再也不发成功写，`wr_tog` 永不翻转，
> core 永远收不到这次错误。**"随写 epoch 携带"在最需要它的场景下恰好失效。**

rev1 还有一个次要问题：`mb_badlen` 是**一经置位永不回零**的 sticky，
即使把它送进 core，也无法区分"这一次"和"上电以来第一次"。

---

## 2. 修法：给错误单独一个 epoch（不是随写帧携带）

错误是**独立事件**，就该有**独立的事件线**，和写邮箱同构但不共享：

```verilog
// spi_frame（cs_n 域）——仅在 CS 上升沿评估
output reg bad_tog;    // 任何长度 != 48 的事务
output reg lost_tog;   // 一个完整写帧到达时，上一帧还没被消费

always @(posedge cs_n or negedge reset_n) begin
    if (!reset_n)                bad_tog  <= 1'b0;
    else if (bc != 6'd48)        bad_tog  <= ~bad_tog;     // 47 / 49 / 截断
    ...
    if (bc == 6'd48 && !hdr_read) begin
        if (ack_s2 != wr_tog)    lost_tog <= ~lost_tog;    // 丢帧
        ...
    end
end
```

```verilog
// tcon_spi_regs（core 域）——与写 epoch 完全相同的接收器
reg bt_s1, bt_s2, bt_seen;
always @(posedge clk or negedge reset_n)
    if (!reset_n) begin bt_s1<=0; bt_s2<=0; bt_seen<=0; end
    else begin bt_s1 <= bad_tog; bt_s2 <= bt_s1; if (bt_s2 != bt_seen) bt_seen <= bt_s2; end
wire bad_evt = (bt_s2 != bt_seen);          // 单拍脉冲
```

`bad_evt` / `lost_evt` 并进 `err_set` → `ERR_REG`（FAULT_STATUS[8]）。

### 为什么这样对

| 性质 | 说明 |
|---|---|
| 单比特 CDC | toggle 是 1 bit，2FF 安全；不存在多位总线跨域 |
| 不需要后续成功写 | 坏帧自己翻 `bad_tog`，与写帧无关 |
| 不会重复计数 | 一次事件翻一次，core 侧沿检测一次 |
| 连续坏帧也不漏 | 相邻两次事务间隔 ≥ 48 个 SCLK（≥ 4.8 µs）≫ 2 个 core 周期 |
| 与现有 `wr_tog` 互斥 | 二者条件互斥（`bc==48` vs `bc!=48`） |

### 为什么不用"电平 + 2FF"

电平需要"什么时候回零"的协议。`mb_badlen` 现在永不回零，
若改成"下一事务开始回零"，又要求 Host 必须再发一笔事务才能复位——
第一笔坏帧之后如果 Host 直接来读，电平还是 1，读到的永远是"有错"，
W1C 也清不掉（源仍为 1）。toggle 没有这个问题：它表达的是**事件**，不是**状态**。

---

## 3. 零仿真状态推演：47 位坏帧 → 立刻读 FAULT_STATUS[8]

时间基线：`T` = 坏帧的 CS 上升沿；CS 高间隔取合同最小值 100 ns；SCLK 10 MHz。

| 时刻 | 事件 | 依据 |
|---|---|---|
| T | `bc=47` → `bad_tog` 翻转（cs_n 域） | `posedge cs_n` 块 |
| T+10 ns | `bt_s1` 采到新值 | 第 1 个 core 沿 |
| T+20 ns | `bt_s2` 采到 | 第 2 个 core 沿 |
| T+30 ns | `bad_evt` 单拍 → `err_set=1` → `fault_status[8] <= 1` | 第 3 个 core 沿 |
| T+100 ns | CS 落，读事务开始 | 合同最小间隔 |
| T+100+16×100 = T+1700 ns | 读的数据相位开始 | 命令 16 bit @10 MHz |
| T+1700+30 = T+1730 ns | `rd_snapshot` 锁定，含 bit8=1 | 2FF + 捕获 |

margin：**30 ns 的置位延迟 vs 1700 ns 的读取最早时刻，余量 56×**。
即"坏帧后马上读"在任何合法 CS 高间隔下都能读到 `ERR_REG=1`。
最坏情况（4 MHz SCLK）命令相位更长，余量更大。

结论：**`READ FAULT_STATUS[8] == 1` 在时序上是可保证的**，不需要等下一笔成功写。

---

## 4. 寄存器映射（不改地址表）

| 事件 | 落到哪 | 可读性 | 是否熄屏 |
|---|---|---|---|
| `bad_evt`（47/49/截断） | `FAULT_STATUS[8]`（ERR_REG） | ✅ 读 0x0C | ❌ 不熄屏 |
| `lost_evt`（写帧被丢） | `FAULT_STATUS[8]` | ✅ 读 0x0C | ❌ 不熄屏 |
| 真实通信超时 | `FAULT_STATUS[7]`（COMM_TO），**尚未实现** | ✅ | ✅ 熄屏 |

选择 `ERR_REG` 而不是 `COMM_TO` 的理由：
1. 坏帧是**访问/格式错误**，不是链路中断；`COMM_TO` 会熄屏，对调试期过于激进；
2. `ERR_REG` 已实现 W1C，且不参与 `disp_fault`（见 `FAULT_REARM_PROTOCOL.md` §3）；
3. 不需要新增地址（0x28 之类属于规格扩展，本轮不碰）。

**代价（要说清）**：`ERR_REG` 只有 1 bit，Host 无法区分"坏长度"和"丢帧"。
若要区分，需要一个只读诊断寄存器（如 0x28 `SPI_DIAG`），那属于**规格扩展**，
必须单独立项批准。在批准之前，**不得声称"通信异常具备完整的软件诊断能力"**。

---

## 5. Host 侧建议读法

1. 每笔写后读回目标寄存器比对（最强的完整性检查，不依赖新位）；
2. 周期性读 `0x0C`：bit8=1 → 至少发生过一次访问/格式错误；
3. 读 `0x10`（INT_STATUS）可用中断代替轮询（`INT_EN` 只屏蔽通知）；
4. 见到 bit8：先修 SPI 时序（保证 CS 高 ≥ 100 ns），再 W1C 清除，再重下配置。

---

## 6. 本轮状态

| 项 | 状态 |
|---|---|
| 设计 | ✅ 完成（toggle 事件 epoch，与写邮箱同构） |
| 零仿真推演 | ✅ 完成（§3，余量 56×） |
| RTL | ❌ **未改**（P1 不与 P0 混预算，任务书 §E 明确要求另开设计门） |
| 可读性 | ❌ 现状仍是"内部观测"，`mb_lost`/`mb_badlen` 经 SPI 读不到 |
