# 数字代表性设计 — 接口逐项说明（`rtl_interfaces.md`）

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 顶层 `rtl/course_top.v.txt` ｜ 所有文件的 `timescale 1ns/1ps`

> **范围声明（先读这一段）**：这是课程作业要求的「范围明确、可独立编译的数字代表性设计」。
> 它实现的是**地址域、控制字段与时序协议**，不是整芯片。
> `TCON 全芯片 / Data 全 384 通道 NMOS 电流源阵列 / Scan 全 512 通道高侧 PMOS 阵列 /
> 电平搬移 / LED 与面板负载 / 版图 / PVT / SOA / 光学标定` 一律 `NOT_IMPLEMENTED`。
> 1024 列 × 768 行是既有项目已记录的架构规模，这里只作为**地址宽度**使用，未实例化 MOS 阵列。
> 3-bit PAM + 6-bit PWM 是**控制字段**，不是已实现的 9 位光学有效精度。

---

## 1. 时钟、复位、全局信号

| 信号 | 方向 | 位宽 | 有效条件 / 周期 | 说明 |
|---|---|---|---|---|
| `clk` | in | 1 | 本 POC 假设 **100 MHz → 10 ns**；单一时钟域 | 与复用模块 `dd1_d7a_gray_ctrl.sv.txt` 注释里的「100 MHz reference domain」一致。`ENGINEERING_DERIVATION / POC_ASSUMPTION`，非教师给定条件 |
| `reset_n` | in | 1 | 低有效，异步置位、同步释放由 TB 保证 | 三个子模块共用。`reset_n=0` 时：`col_addr=0`、`onehot_pop=0`、`latch_count=0`、`chan_valid=0`、`win_state=S_IDLE`、`data_en=0`、`drive_gate=0` |
| `blank` | in | 1 | 高有效，组合级关断 | 三个子模块共用。`blank=1` 时列选通 one-hot 全 0、`data_out_en=0`、灰阶控制器 `data_en=0`，并使运行中的窗口进入 `S_ABORT`；**LATCH 只允许在 blank 期间被接受** |
| `fault` | in | 1 | 高有效 | 只接灰阶控制器；置位时 `data_en=0`、拒绝 LATCH/START、中止窗口 |

---

## 2. 列扫描 / 选通（`rtl/course_col_scan.v.txt`）

| 信号 | 方向 | 位宽 | 有效条件 / 周期 | 说明 |
|---|---|---|---|---|
| `scan_en` | in | 1 | 高有效 | 全局扫描使能；为 0 时不推进列、不产生选通 |
| `col_step` | in | 1 | 单 `clk` 上升沿的时钟使能脉冲 | 仅在 `scan_en=1 && blank=0 && reset_n=1` 时使 `col_addr` +1；在 1023 时回绕到 0 |
| `col_addr[9:0]` | out | 10 | 0..1023，模 1024 | 复位值 0；`col_step` 每有效一次 +1 |
| `scan_bank` | out | 1 | `col_addr[0]` | **偶/奇 512 通道分片**：0 = 偶列 Scan 芯片，1 = 奇列 Scan 芯片；两片各 512 通道，合计 1024 列。此为课程工程推导的映射，不是教师给定条件 |
| `scan_ch[8:0]` | out | 9 | `col_addr[9:1]`，0..511 | 所选 Scan 芯片内部的通道索引 |
| `scan_even_sel` / `scan_odd_sel` | out | 1 each | `scan_sel_valid && (scan_bank==0/1)` | 两者互斥，且任一时刻至多一个为 1 |
| `scan_sel_valid` | out | 1 | `scan_en && !blank && reset_n && onehot_valid` | 有且仅有一列被选时才有效 |
| `onehot_pop[10:0]` | out | 11 | 组合输出 | 真实 1024-bit one-hot 选通向量的 popcount；**恒为 0 或 1**，由 TB 连续监控，违规计数为 0 |
| `onehot_valid` | out | 1 | `onehot_pop <= 1` | 「一次最多一列被选」的可观测判据 |
| `col_wrap` | out | 1 | `scan_en && col_step && !blank && col_addr==1023` | 回绕拍的组合脉冲；读组合信号须留 delta 时间（见已知失败记录） |

**扫描切换周期**：本设计不把列切换硬绑定到某个固定帧率；`col_step` 由外部给出。列时间预算在
`reports/course_sim/rtl_timing_report.md` 里按 60 Hz / 100 Hz 单独核算，不默认成立。

---

## 3. Data 行数据 / 锁存 / 使能（`rtl/course_data_latch.v.txt`）

| 信号 | 方向 | 位宽 | 有效条件 / 周期 | 说明 |
|---|---|---|---|---|
| `row_addr[9:0]` | in | 10 | 0..767 合法 | **偶/奇 384 通道映射**：`row_addr[0]` 选 Data 芯片（0=偶、1=奇），`row_addr[9:1]` 为片内 0..383 通道索引；两片 × 384 = 768 行。课程工程推导 |
| `row_wdata[8:0]` | in | 9 | `[8:6]` = PAM select，`[5:0]` = 6-bit PWM time code | Hybrid 3-bit PAM + 6-bit PWM **控制字段**；不是 9 位光学有效精度 |
| `row_wr_en` | in | 1 | 上升沿采样 | 仅在 `row_addr < 768` 时写入对应 bank 的通道配置寄存器；同时把该字段记为「待锁存」（`prep_valid`） |
| `latch_stb` | in | 1 | 上升沿、且 `blank=1 && prep_valid=1` | 把待锁存字段提交到显示副本；非 blank 期的 LATCH 被拒绝且显示副本不变 |
| `active_col[9:0]` | in | 10 | 来自 `col_addr` | 用于记录 LATCH 时是否与上一次 LATCH 处于不同列 |
| `data_bank` / `data_ch[8:0]` | out | 1 / 9 | 组合 | 当前 `row_addr` 的映射结果 |
| `latched_ch_data[8:0]` | out | 9 | 组合读 | 当前 `row_addr` 指向的通道寄存器值，用于验证偶/奇 bank 不串扰 |
| `pam_sel[2:0]` / `pwm_code[5:0]` | out | 3 / 6 | 保持到下一次被接受的 LATCH | **`pam_sel=000` 是最低非零电流档，不是黑码**；黑码由 PWM time code=0 或 `blank` 产生 |
| `chan_valid` | out | 1 | 被接受 LATCH 后为 1 | 复位清零 |
| `data_out_en` | out | 1 | `chan_valid && !blank && reset_n` | 组合关断，不等下一个 tick |
| `latch_on_switch` | out | 1 | 上次被接受 LATCH 时 `active_col != 上一次记录列` | 「数据锁存与扫描切换关系」的可观测判据 |
| `latch_count[7:0]` | out | 8 | 每次被接受 LATCH +1 | 拒绝的 LATCH 不计数 |
| `row_in_range` | out | 1 | `row_addr < 768` | 越界写被忽略 |

**内部存储**：`mem_even[0:383]` / `mem_odd[0:383]` 各 9 bit，共 768 项**配置寄存器**，用于验证地址映射；
它们不是 384 个物理恒流输出通道，也不代表任何模拟电路。

---

## 4. 复用的灰阶控制器（`rtl/dd1_d7a_gray_ctrl.sv.txt`，Data-7B-R3 原字节）

来源冻结见 `reports/course_sim/source_provenance.md`。

| 信号 | 方向 | 位宽 | 有效条件 / 周期 | 说明 |
|---|---|---|---|---|
| `tick` (顶层 `pwm_tick`) | in | 1 | 同 `clk` 域的时钟使能 | TB 中每 12 个 `clk` 产生 1 拍 → **120 ns / tick**（POC 假设，非教师给定） |
| `mode[1:0]` | in | 2 | 0=Pure 8-bit PWM(256 tick)，1=Hybrid 3+6(64 tick)；其他为非法 | 模式变更必须在安全相（`disp_safe && blank && ~system_en`） |
| `cfg_pure[7:0]` / `cfg_hyb_time[5:0]` / `cfg_hyb_pam[2:0]` | in | 8 / 6 / 3 | 由 `cfg_valid` 上升沿登记为一次完整 load | `cfg_hyb_time=63` → `FULL_HYB=64`，即**「63 码占 64 个 tick」**；`cfg_hyb_time=0` → 黑码，整窗不导通 |
| `cfg_valid` | in | 1 | 上升沿产生 `load_pending` | LATCH 与新 load 同一拍视为 `E_AMBIGUOUS` 被拒 |
| `gray_latch` (→ `latch_stb`) | in | 1 | 上升沿、`blank=1 && system_en=1 && load_pending=1 && mode 与已采纳模式一致` | 接受后 `auth_q=1`、`cfg_version+1`、PAM/PWM 副本一起更新 |
| `pwm_start` | in | 1 | 上升沿、`auth_q=1` | 置 `S_ARMED`；保持高电平不会重复启动 |
| `system_en` | in | 1 | 高有效 | 门控 LATCH/START；安全相模式变更需要它为 0 |
| `data_en` / `data_en_b` | out | 1 | `run_q && ~blank && ~fault && reset_n` / 严格取反 | 灰阶导通请求，组合级安全门 |
| `obs_tick` | out | 1 | `tick && window_active && ~async_block` | 窗口实际接受的 tick（组合） |
| `pam_sel[2:0]` | out | 3 | 整窗保持 | Hybrid 下等于 `cfg_hyb_pam`；Pure 下为 `PAM_TOP_SYMBOL=7`（仅码值，不是电流档声明） |
| `win_state[2:0]` / `cfg_version[7:0]` / `proto_err[7:0]` | out | 3 / 8 / 8 | — | 状态机 / 版本计数 / 8 位拒绝位图（含 `E_STALE`、`E_MODE_UNSET`） |

**窗口周期（Hybrid）**：`S_ARMED` → 第 1 个 tick 进 `S_RUN`；`index_q` 0..63 共 **64 个导通间隔**；
第 **65** 个 tick 到达时 `index_q==64` 不再 `< full_w(64)`，`run_q=0` 且进 `S_DONE`。
所以 `63` 码对应 64 个导通 tick，而不是 63 个；这是 TB 专门测的边界。

---

## 5. 顶层组合输出

| 信号 | 有效条件 | 说明 |
|---|---|---|
| `drive_gate` | `data_en && data_out_en && scan_sel_valid && !blank && !fault` | **代表性逻辑门控信号**，不是实测像素电流，也不含任何 LED/面板负载模型 |

---

## 6. 未实现清单（供独立复审逐项核）

`NOT_IMPLEMENTED`: TCON 全芯片、Data 384 路恒流输出级、Scan 512 路高侧驱动、电平搬移、
1024×768 MOS 像素阵列、混合信号联合仿真、版图、PVT/SOA、光学效率/亮度/波长、
9 位光学有效精度、门级网表与 STA。
