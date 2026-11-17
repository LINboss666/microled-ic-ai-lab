# T5_FIVE_CHIP_WIRING —— 五芯片连接方案（T5-A 草稿，**未仿真**）

日期 2026-11-17｜壳：`tb/t5_five_chip_shell.sv.txt`（编译通过，0 错 0 警；**本阶段不跑 vsim**）

---

## 1. 实例与映射

| 实例 | 模块 | 参数 | 承担 |
|---|---|---|---|
| `u_tcon` | `tcon_top` | `N_COL=1024` | 时基/视频接收/双 lane 发送/Scan 地址 |
| `u_data0` | `data_driver` | `NCH=384, PWM_MAX=63, CNTW=8` | 偶数行 0,2,…,766（`d0`） |
| `u_data1` | `data_driver` | 同上 | 奇数行 1,3,…,767（`d1`） |
| `u_scan0` | `scan_driver` | `CHIP_ID=0` | 全局偶数列 0,2,…,1022 |
| `u_scan1` | `scan_driver` | `CHIP_ID=1` | 全局奇数列 1,3,…,1023 |

## 2. 连线表（逐根，来自壳源码）

| 源 | 目的 | 说明 |
|---|---|---|
| `u_tcon.d0[7:0]` | `u_data0.din` | 50 MB/s，row 0,2,…766 |
| `u_tcon.d1[7:0]` | `u_data1.din` | 50 MB/s，row 1,3,…767 |
| `u_tcon.dclk` | 两颗 Data 的 `dclk` | 50 MHz **连续**；Scan 不用时钟 |
| `u_tcon.latch` | 两颗 Data 的 `latch` | 只在 BLANK 内切换 bank |
| `u_tcon.pwm_start` / `pwm_tick` | 两颗 Data | 两片共用同一计数器起点 |
| `u_tcon.blank` | 两颗 Data + 两颗 Scan | 高有效，异步优先 |
| `fault_n`（外部，开漏线与） | 全部 5 颗 | 低有效 |
| `u_tcon.col_id[9:0]` | 两颗 Scan | 全局列号；`[0]` 分片、`[9:1]` 本地 |
| `u_tcon.scan_stb` | 两颗 Scan | BLANK 内上升沿锁存 |
| `u_tcon.load_active` | **不接任何东西** | RTL 内部观测；**禁止**当 VALID 引脚 |
| —（**无**，已删除） | 两颗 Data 的 `din_valid` 接 **常量 1'b0** | T3-H2 的 `USE_DIN_VALID=0` 让芯片自己数 384 沿；壳不再生成任何 valid |

## 3. `din_valid` 的处理（T3-H2 之后）

- V1.3 段 0548 明确"无需额外 VALID 线"，且 `load_active` 在 V1.3 中出现 **0** 次。
- 壳里**没有**把 `load_active` 接到 `din_valid`；两颗 Data 现在都以 `USE_DIN_VALID=0` 实例化，
  `din_valid` 端口接 **常量 1'b0** —— 与最终芯片 wrapper 的用法一致。
- 旧 `dv_stub`（壳侧"LATCH + 384 沿"模型）**已删除**：它实际产生 **385** 个有效沿
  （arming 沿 + 之后 384 沿），复审 T5-A 已给出逐沿反例。
- 因此 384 沿定界现在完全由芯片内部完成；T5 里才可以说 "chip-delimited"。
  但在 T3-H2 独立复审通过前，壳只是**编译草稿**，不构成任何 T5 证据。

## 4. 观测口（供 scoreboard 与 VCD）

壳输出：`d0_ch_en[383:0]`、`d1_ch_en[383:0]`、`d0_ch_pam`、`d1_ch_pam`、`d0/d1_col_valid`、
`d0/d1_lut_valid`、`s0_col_a[511:0]`、`s1_col_a[511:0]`、`tcon_col_id`、`tcon_scan_stb`。

**不含** `disp_col/disp_frame`：Data 的可综合 RTL **没有**这两个输出，T5 不得伪造，
必须用"实际 `raw_disp` 内容 + 独立视频刺激"推出期望（见 `T5_SCOREBOARD_PLAN.md`）。

## 5. 仍缺的东西（T5 正式仿真前必须补）

1. TCON 的 LUT 下发通道：V1.3 里 LUT 由 SPI 写（段 0680–0705），本轮 `cfg_lut_*` 仍是端口注入；
   SPI 未实现 → T5 只能端口注入，**不得**据此声称"配置通路已验"。
2. `cfg_hybrid` 的两片一致性：目前壳共用一根 `cfg_hybrid`（两片同模式）；若将来允许两片不同模式，
   需要拆成两路并登记时序约束。
3. 故障上报：`FAULT_n` 开漏线与到 TCON 未建模（壳里 `fault_n` 是外部输入）。
4. 预充/放电、512 路高侧、384 路恒流 —— 全在模拟侧，T5 不含。
