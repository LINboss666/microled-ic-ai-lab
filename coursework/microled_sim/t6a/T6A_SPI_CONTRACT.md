# T6-A SPI / 寄存器合同（TCON 子集）

日期：2026-11-18；依据：V1.3 原件 `v13_fulltext.txt`（SHA `6b42b136…`）段 0569/0570/0704、§12 引脚表

## 1. 引脚（只读核对，不新增）

V1.3 §12：`SPI_SCK` / `SPI_MOSI` / `SPI_MISO` / `SPI_CS_n` 四根，**不新增第五根 VALID/READY**。
本设计 `tcon_spi_top` 只有这三个输入 + 一个输出，其余端口是芯片内部的状态输入与寄存器输出，不是引脚。

| 信号 | 方向 | 说明 |
|---|---|---|
| `spi_sck` | in | 模式 0，≤10 MHz |
| `spi_mosi` | in | 命令与写数据，MSB 先 |
| `spi_miso` | out | 读数据，后 32 个 SCK 返回 |
| `spi_cs_n` | in | 低有效；**上升沿提交写**，未完成帧丢弃 |

## 2. 帧格式（段0569）

- 16 bit 命令：`bit15 = 1 读 / 0 写`，`bit14:0 = 字节地址`，MSB 先；
- 32 bit 数据：MSB 先；
- 共 **48 个 SCK**；
- 写：CS_n 上升沿完整提交；不完整事务丢弃；
- 读：后 32 周期返回；
- 寄存器 32 bit、4 字节对齐；保留位读 0 写 0；未实现地址读 0、写忽略并置 `ERR_REG`。

## 3. 寄存器（TCON 子集，逐址）

| 地址 | 名称 | 位域 | 访问 | 复位 | 本设计行为 |
|---|---|---|---|---|---|
| 0x00 | CHIP_ID | [7:0] | RO | 0x10 | 常量 0x10（TCON）；写→ERR_REG |
| 0x04 | CTRL | [0]EN [1]BLANK [2]SW_RESET [3]TEST | RW/W1P | 0x2 | EN 置 1 需 SAFE；BLANK 置 0 需 EN&SAFE&READY；SW_RESET 单拍自清；TEST 需 TEST_EN |
| 0x08 | MODE | [0]FPS_SEL | RW | 0 | 写需 EN=0 且 SAFE=1，否则 ERR_REG 且不提交 |
| 0x0C | FAULT_STATUS | [10:0] | W1C | 0 | 硬件故障锁存；**故障未消失不可清** |
| 0x10 | INT_STATUS | [10:0] | W1C | 0 | 事件锁存，与 INT_EN 无关；清中断不解除熄屏 |
| 0x14 | INT_EN | [10:0] | RW | 0 | 只屏蔽 `irq`，不屏蔽保护 |
| 0x18 | STATUS | [0]READY [1]ACTIVE [2]SAFE [3]LUT_VALID | RO | 0x4 | 由 `status_in` 实时驱动，非恒真 |
| 0x1C | WATCHDOG | [15:0] | RW | 2 | 写需 EN=0&SAFE；写 0 仅 TEST_EN 允许 |
| 0x20 | TCON_VIDEO_CFG | [9:0] COLS_MINUS1 [19:10] ROWS_MINUS1 | RO | 0x000BFFFF | 常量 1023/767 |
| 0x24 | TCON_COL_INDEX | [9:0] | RO | 0 | `col_index_in` 实时值 |

其余地址（含 0x28 及以上的 Data/Scan 专用寄存器）**未实现**：读 0、写忽略并置 `ERR_REG`。
非 4 字节对齐地址同样按"未实现"处理。

## 4. CDC 方案（段0549）

| 方向 | 机制 |
|---|---|
| 写 | 帧位在 SCLK 停止后冻结；`CS_n` 经 **2 级同步 + 上升沿检测**作为唯一提交限定符；多位帧总线**不逐位同步** |
| 读 | 地址在第 16 个上升沿冻结（`rd_addr_hold`，数据相位内保持 ≥32 个 SCLK 周期）；单比特电平 `rd_req` 经 2 级同步后才允许采样地址；32 位应答以稳定寄存器返回，SPI 侧在**下一个下降沿**取第一位 |
| 复位 | `reset_n` 异步置位、同步释放；不复位跨域数据通路 |
| 优先级 | RESET / 硬件 FAULT / BLANK 高于 SPI 与中断屏蔽（段0934）；`INT_EN=0` 不关闭保护 |

## 5. 明确未实现（不伪装成已实现）

- Data / Scan 的 SPI 与寄存器（本阶段只做 TCON 子集）；
- SPI 与 100 MHz 之外的域（PCLK / DCLK / PWM 事件）的 CDC 约束与 STA；
- `GRAY_MODE=10/11`、`PAM_CFG=01`、UVLO/OTP 等模拟事件源（当前由 TB 以 `hw_fault` 激励，**不是片上模拟硬件**）；
- SPI 时序的建立/保持签核：仿真中的 5 ns/15 ns 余量不是 STA。

---

## 6. rev2 追加（2026-11-19，T6-A RUN01 复审后）

### 6.1 时钟域与写帧交接

| 域 | 时钟 | 内容 |
|---|---|---|
| SCLK | `spi_sck` | 移位器、头字段、MISO 移位 |
| CS | `spi_cs_n` 上升沿 | 48 位写帧保持寄存器、epoch、`mb_lost` / `mb_badlen` |
| CORE | `clk` 100 MHz | 2FF 同步、每 epoch 一次捕获、单次读快照 |

交接采用**单比特 epoch + 应答**：SPI 侧在 CS 上升沿翻 `wr_tog`（帧已冻结），核心 2FF 后
在自己域内比较 `tg_s2 != tg_seen` 得到**一拍的捕获脉冲**，处理完把 `tg_seen` 回送。
`ack_s2 != wr_tog` 时置 `mb_lost`：帧若被挤掉，**有标志位可读**，不会静默丢失。

### 6.2 最小 CS_n 高时间

核心捕获需要 3 个 core 周期（2FF + 捕获拍）= 30 ns。**合同值 100 ns**（10 拍，×3 余量），
低于此值可能丢帧（并由 `mb_lost` 记录）。TB 在所有交易间强制 200 ns 并断言 `CS_GAP >= 100`。

### 6.3 读事务

- `bit15=1`；地址在第 16 上升沿冻结并保持到 CS 上升沿；
- 核心只锁存**一次** 32 位快照（`rd_cap_o` 单拍），32 位期间不刷新，实时寄存器不会撕裂；
- 最坏路径：`rd_req` 上升 → 2FF → 捕获 = 30 ns，加相位 ≤ 40 ns，**10 MHz 下半个周期 50 ns**，余量 ≥10 ns；
- MISO 在 SCLK 下降沿更新，bit31 出现在第 17 上升沿；**CS_n 高时 MISO 为高阻**（V1.3 §12）。

### 6.4 安全优先级（软件不可绕过）

```
hw_blank = blank_r | (!en) | any_hw_fault
```
- 写 `EN=0` 时同一次写里强制 `BLANK=1`；
- 有任一硬件故障时，`EN=1,BLANK=0` 的写被拒绝并置 `ERR_REG`；
- `INT_EN=0` 只屏蔽 `irq`，不影响 `hw_blank`；
- unblank 的判定使用**本次写入的新 en 值**（RUN01 用的是旧值）。

### 6.5 帧长

恰好 48 沿才可能提交；47 / 49 / 短帧一律拒绝（寄存器无副作用），并置 `mb_badlen`。
