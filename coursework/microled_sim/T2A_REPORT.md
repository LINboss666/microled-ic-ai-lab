# TCON T2A 数据通路报告（首条真实数据链路）

**任务** `TCON-T2A-20261114` ｜ 分支 `course/microled-assignment-sim-20261112` ｜ 模型 `100 MHz CLK_REF = PCLK`（课程模型，**不声称已验证 CDC**）

停 `WAITING_FOR_T2A_INDEPENDENT_REVIEW`。本文件只报告已发生的真实运行，未发生的一律标 `NOT_RUN`。

---

## 1. 本轮交付了什么

TCON 第一次真正有数据通路，而不只是控制波形：

```
video_d/de/col_sync/vsync ──► tcon_video_rx ──► tcon_col_bank ──► tcon_data_tx ──► d0/d1 + dclk
                              (768B 接收+分类)   (2×768B ping-pong)  (每口 384B)
```

| 模块 | 新/改 | 职责 |
|---|---|---|
| `tcon_video_rx.v` | 新 | 768 B 逐字节接收；按 `COL_SYNC` 提交；五类错误分类；bank 归属标记 |
| `tcon_col_bank.v` | 新 | 2 × 768 B；每 bank 拆成 even/odd 两条 384 B 通道，供两路 Data 同址读取 |
| `tcon_data_tx.v` | 新 | 装载窗 `[832,1600)`；`dclk = load_run && !load_cnt[0]`；下降沿预取/换字节 |
| `tcon_top.v` | 改 | 集成上述三个模块，`mode_en` / `safe` 分离，导出 `err_flags`/`bank_valid`/`bytes_rcvd`/`bytes_sent`/`load_blank` |
| `tcon_timebase.v` / `tcon_slot_seq.v` | 未改 | T1R 已验收的时基与相位序列 |

**奇偶映射（本契约定义）**：第 k 个 DCLK 采样沿，`D0` = bank 偶数字节 `2k` = **行 2k**，`D1` = 奇数字节 `2k+1` = **行 2k+1**；两口各 384 行。详见 `rtl/T2A_INTERFACE_CONTRACT.md` §3。

## 2. 实测结果（run 4，唯一的通过运行）

| 项 | 实测 | 断言 |
|---|---|---|
| 断言 | **29 / 29 PASS**，`FAIL_COUNT=0`，`RESULT=PASS`，`Errors: 0`，rc=0 | — |
| 装载窗起点 | **832** | `T2` |
| 装载窗长度 | **768 周期**（7.68 µs） | `T3` |
| DCLK | 周期 **20 ns**（50 MHz），每窗 **384 个上升沿** | `T4`/`T5` |
| 每口字节数 | **384** | `T6` |
| 采样前后数据稳定 | DCLK 高电平期间 `d0/d1` **零次变化**（⇒ 建立 5 ns / 保持 5 ns） | `T7` |
| 逐字节比对 | **0 失配**（768 个比较值/有效列） | `T8` |
| `LATCH`/`PWM_START`/`SCAN_STB` | **828 / 840 / 880**，脉宽 **4 拍 = 40 ns** | `C1`–`C4` |
| `BLANK` 上升 | **768** | `C5` |
| 五类错误标志 | `err_flags = 11111`（全部被真实触发） | `E1`–`E5` |
| 无效 bank 输出 | 列 4/5/7/9 全 `8'h00`（该列不发光） | `E6`–`E9` |
| 装载期间故障 | 列 10 窗口被截断（**35/384** 字节） | `E10` |
| LATCH 期间故障 | 列 11 **完全没有装载窗** | `E11` |
| 恢复 | 列 12 满 384 字节且数据正确 | `R1` |
| 连续两列流水 | 列 0/1/2 均 384 且正确 | `R2` |
| 停顿列 | 列 3（DE 停 20 拍，787 拍收齐）仍 384 且正确 | `R3` |
| 重复 COL_SYNC | 列 6 数据仍有效 | `R4` |
| 小帧回卷 | `N_COL=8` 实例：`col_id` 7→0，`frame_wrap` 2 次，越界 0 | `W1` |

**逐字节证据**：`results/t2a/t2a_byte_samples.csv`（768 行，列 0 与列 3 的 `expected` / `actual` 全等）。列 0 前几个采样沿：`0x5A,0x74,0x8E,0xA8,0xC2,0xDC`（D0）与 `0x67,0x81,0x9B,0xB5,0xCF,0xE9`（D1），与 `pat(0,i)=i*13+0x5A` 逐项吻合。

**波形**：`figures/t2a_datapath.svg`，由 run 4 的真实 VCD 生成（纯标准库渲染，两次渲染 SHA 相同）。

## 3. 四次运行：三次失败、全部保留

预算 4 次，用满 4 次。**三次失败没有一次是"调判据追 PASS"**，每次都是先定位再改代码。

| # | 结果 | 根因（定位方式） | 修复 |
|---|---|---|---|
| 1 | 8 条后 `T8` 失败，失配 **9440** | ① RTL 写 bank 用了自增后的 `idx` → 整体错一位；② TB 的 `col_sync` 与最后一个字节**同拍**发出 → 接收端只看到 767 B（VCD 反查 `idx`/`sync_p` 时间） | 写地址改为与字节同拍寄存；`col_sync` 晚一拍 |
| 2 | 同上，失配 **7910** | 列边界那一拍：上一列遗留 `idx=768`，新列首字节被判成"第 769 字节溢出" → 整列作废（VCD 显示只有列 0 与故障后的列 12 有效） | 边界处理显式优先：`slot_last` 那一拍的字节就是新列的第 0 字节 |
| 3 | 同上，失配 **368** | ① TB 停顿写成"`drv_i` 落在区间内"，停顿期间 `drv_i` 不动 → **永久停顿**；② 设计缺陷：bank 有效位是"每 bank 一位"，列 3 没写完整，却把**两列前的旧数据**当成有效送出 | 停顿改为倒计数一次性触发；bank 增加**归属列号**，`col_valid = 归属==当前列 && 有效` |
| 4 | **29/29 PASS** | — | — |

失败件全部入库（`results/t2a/t2a_run0{1,2,3}_fail_bytecmp_vsim.txt`），未删改。

## 4. 顺带修掉的一个设计缺陷（不在任务书清单里）

`fault_n` 原先进 `safe`，而 `safe` 又驱动 `tcon_timebase.enable`。时基在 `enable` 上升沿会**把 `slot_cycle` 复位到 0**，因此一次 20 拍的故障会让整帧时序**后移**、并重跑当前列。本轮拆成：

- `mode_en = reset_n && cfg_valid && mode_ok && run_en` → 只决定"机器是否运行"，驱动时基；
- `safe = mode_en && rx_ready && fault_n` → 只决定"控制脉冲是否放行"，驱动 `blank/latch/pwm_start/scan_stb/load_active`。

效果：故障仍在 **0 拍**内关门控（`<=50 ns` 目标满足）、仍作废当前 bank，但**不再移动帧时序**。这也是 T1R 复审 F4 要求的"不要把接收未满当全机故障"的落地方式。

## 5. 与 V1.3 的偏差（必须知道）

| 项 | 本设计 | 说明 |
|---|---|---|
| `DCLK` | **只在装载窗内翻转**，窗外为低 | 让首个采样沿确定固定在周期 832。真实 Data 通常连续供钟 —— **已知偏离**，不是为了掩盖问题 |
| `PCLK` | 与 `CLK_REF` 同源同相 | 课程模型；**未验证 CDC**，异步输入只做同步假设 |
| bank 数 | 2 × 768 B | 无帧缓存、无转置（V1.3 §3/§9：转置在外部 DSP） |
| 灰阶引擎 | 不在 TCON | 归属 Data Driver |
| 无效列 | 该列 384 B 全 0（不发光），帧时序不变 | 不是整帧熄屏 |

## 6. 未实现（`NOT_IMPLEMENTED`）

SPI/寄存器组、中断、CDC、384/512 路晶体管级阵列、灰阶物理实现、电平搬移、版图、**STA（`NOT_RUN`）**、PVT/SOA、整芯片、T3/T4/T5 联调。
`Spectre / Monte Carlo / Virtuoso OA`：本轮 **0 次**。

## 7. 预算

| 资源 | 授权 | 实耗 |
|---|---|---|
| ModelSim 正式运行 | 4 | **4** |
| ModelSim 仅编译预检查（不仿真） | — | 4 次（每次 0 error / 0 warning，均登记） |
| Spectre / MC / OA | 0 | 0 |

## 8. 复现

```bash
COURSE_ROOT=<worktree> RUN_DIR=<scratch> bash tb/run_tcon_t2a.sh
```

runner 内置：只编译预检查、硬墙钟超时 `WALL_LIMIT_S=300`、VCD 体积上限 `VCD_LIMIT_MB=60`、
断言下限由 TB 源码 `chk("` 计数自动推导（当前 29）且外部不得下调。
通过的判据仍是 T6 的五条件 transcript 检查（`CHECK0..CHECK4`），不是退出码 ——
因为 ASE 10.5b 在 `$fatal` 后仍可能返回 0。
