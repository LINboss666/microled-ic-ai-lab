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
