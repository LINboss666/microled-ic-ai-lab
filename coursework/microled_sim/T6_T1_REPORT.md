# T6 / T1 执行报告（真实状态，含未通过项）

**任务号** `TCON-T6-T1-20261112` ｜ 分支 `course/microled-assignment-sim-20261112`
**基线** `2e919a4e259c98f750c25737dd89eadfad10f079`（开始前远端回读一致）
**状态** `WAITING_FOR_T6_T1_INDEPENDENT_REVIEW`

---

## 1. 一句话结论

**T6 = PASS**（失败必被拦下，且有正例+两个负例）。
**T1 = 2/3**：复位/故障 **PASS**、时基与控制脉冲 **PASS**、整帧边界 **FB（未通过，缺陷在 TB 场景初始化，不在 RTL）**。
ModelSim 实跑 **9 次**（预算 6 + 你两次追加 + 一次我请求的第 9 次），全部逐条登记在 §2。

---

## 2. 九次 ModelSim 运行全账（不删失败）

| # | 目的 | 结果 | 退出/判定 | 失败归属 |
|---|---|---|---|---|
| 1 | T6 正例 | 55/55 通过，但 runner 报 `CHECK2/3/4=0` | runner rc=6 | **runner 解析 bug**：ModelSim 每行加 `# ` 前缀，未归一化 |
| 2 | T6 正例（修后） | 55/55，五项全 1 | rc=0 | — |
| 3 | T6 负例（`+define+COURSE_FAULT_INJECT`） | `** Fatal:`、`Errors: 1`、`fail_count=1`、断言 34 | runner rc=6 | 预期失败（证明判定链有效） |
| 4 | T1 场景1 复位/故障 | 编译 0 error；`R5_fault_sticky_status` 失败 | rc=5 | **TB bug**：`fault_seen` 是 `status[3]`，写成 `[4]` |
| 5 | T1 三场景合并 | `T1_latch_offset_828` 失败，实测 829/841/881 | rc=6 | **TB bug**：real→integer 四舍五入（828.5→829），应用 `$rtoi` |
| 6 | T1 三场景合并（修后） | 场景1 **19/19**、场景2 **14/14**、场景3 `B1` 失败（998,047 周期 / 1022 槽） | rc=6 | **TB bug**：以 `frame_wrap` 收尾，缺起始相位信息 |
| 7 | T1 场景3（追加授权） | 超时 540 s | rc=124 | **我的疏漏**：单场景未关 VCD dumping，写出 **8,084,669,077 B**，已删除 |
| 8 | T1 场景3（追加授权） | 超时 480 s | rc=124 | 帧首对齐 `do/while` 空转最多 1024 槽，仿真时间翻倍 |
| 9 | T1 场景3（你批准的最后一次） | 超时 420 s | rc=124 | **TB bug**：单场景未先发复位脉冲 → 时序寄存器停在 X → `slot_start` 不跳变，死等 |

**结论**：9 次里 **7 次失败全部是 TB/runner 的仪表缺陷**，没有一次是 RTL 功能错误；每次修复都只动 TB/runner，未改 RTL 判据。

---

## 3. T6 结果（PASS）

判据从"只看进程码"改成**五项独立校验**（`tb/t6_check_transcript.sh`）：

| 检查 | 内容 |
|---|---|
| CHECK0 | transcript 无 `** Fatal:` 且 `Errors: 0` |
| CHECK1 | vsim 进程 rc = 0 |
| CHECK2 | `COURSE_RTL_RESULT=PASS` 精确匹配 |
| CHECK3 | `COURSE_RTL_FAIL_COUNT=0` |
| CHECK4 | 实际断言数 ≥ 声明下限（55）且 > 0 |

**关键实证（重要发现）**：ModelSim ASE 10.5b 在 `$fatal` 之后若 `-do` 脚本含 `quit -f`，
**进程仍返回 rc=0**（负例 #3 中 `CHECK1=1`）。因此"只看退出码"本身不足以保证 D1 闭合；
本轮的判定权威是 transcript 五项校验，`$fatal` 只作为"立即终止 + 留下 Fatal 记录"。

正例：55/55，五项全 1，rc=0。
负例：`C10_max_code_conducting_ticks_64` 被注入故障 → `FAIL` → `$fatal` → 判定 rc=6；断言数 34 < 55 亦被 CHECK4 拦下。
第二个负例（离线复用第 2 次 transcript，`min=99`）：CHECK4=0 → rc=6。**未额外消耗仿真**。

---

## 4. T1 结果（2/3）

### 4.1 已通过

| 用例 | 证据 | 结果 |
|---|---|---|
| R1 复位态 | `blank=1, col_id=0, latch/pwm_start/scan_stb/tick/load=0` | 7/7 |
| R2 未配置 | `cfg_valid=0` 持续 BLANK | 2/2 |
| R3 非法 mode | `cfg_mode=2'b10` 持续 BLANK | 1/1 |
| R4 就绪 | 一个槽内 `blank` 下降、`status[0]=1` | 2/2 |
| R5 故障 | `fault_n=0` 后 **1 拍内** `blank=1`（远优于 ≤50 ns 目标）、无 `scan_stb`、`status[3]` 置位 | 4/4 |
| R6 恢复 | `fault_n=1` 后恢复显示；全程 tick/latch 越界计数 = 0 | 3/3 |
| T1–T3 时基 | 槽长 977（同槽另测 976）；**latch=828、pwm_start=840、scan_stb=880**；latch 脉宽 **4 拍 = 40 ns**；每窗 **64 个 tick**；`col_id` 递增 | 14/14 |

### 4.2 未通过：整帧边界（FB）

run6 实测：**998,047 周期 / 1022 槽 / 575 长 / 447 短**，起始列 = 第 3 列。

**算术闭合**：1024 − 1022 = 2 槽缺失 = 976 + 977 = **1,953**；998,047 + 1,953 = **1,000,000** ✓；
575 + 1 = **576** 长槽、447 + 1 = **448** 短槽 ✓。

即数据**与"整帧 1,000,000 周期、576 长 / 448 短"完全自洽**，但这只是**推导**，不是通过断言。
真正拦住的是一条 TB 自身的相位缺陷（用 `frame_wrap` 收尾，丢失起始列信息）。

**修复已完成（未运行）**：改为"固定数 1024 个连续槽"，因槽长序列以 1024 为周期，
任意连续 1024 槽的总和恒等于 1,000,000、恒含 576 长槽——**与相位无关**；
并给单场景补了 `reset_dut`（否则寄存器停在 X，第 9 次即死等）。

**下一轮只需一次运行**：`SCEN=BOUNDARY`（已修）或 `SCEN=ALL`，约 10 ms 仿真、不写波形。

---

## 5. T1 RTL 交付

| 文件 | 作用 | 说明 |
|---|---|---|
| `rtl/tcon_timebase.v.txt` | 列时基：976/977 用分数累加器（步长 576/1024），1024 槽累计精确 1,000,000 | 60 Hz 仅留接口参数，未实现 |
| `rtl/tcon_slot_seq.v.txt` | 槽内相位：窗口 / BLANK / LATCH / PWM_START / SCAN_STB / tick | 参数化，全部为 40 ns 脉冲 |
| `rtl/tcon_top.v.txt` | 顶层端口 + 安全门 + DCLK 50 MHz + 768 周期装载窗 + status | `safe=0` 时组合强制 BLANK |
| `rtl/tcon_t1_edge_table.md` | 逐沿表（先于 RTL） | 修正 T0R 的"208 净余量"与"s−1 全在 [0,767]" |
| `tb/tcon_t1_tb.sv.txt` | 三场景 TB，只观测不驱动时序 | 黑盒安全监视器 |
| `tb/run_tcon_t1.sh` / `tb/t6_check_transcript.sh` | runner 与判定器 | 复用 T6 五项校验 |

**T1 明确未实现**：768 B 接收、2×768 B 双 bank、奇偶分流、`D0/D1` 真实载荷（当前恒 `8'h00`）、
SPI 寄存器、中断、CDC、Data/Scan 晶体管级、STA。

---

## 6. 逐沿表对 T0R 的两处修正

| T0R 说法 | 本次修正 |
|---|---|
| "C 净余量 = 208 周期" | 208 是**毛差**；扣 LATCH 脉宽 4 拍 + 末数据保护 4 拍 → **净 200 周期（2.00 µs）** |
| "s−1 的装载落在 [0,767]" | 按 C 自 LATCH 后起算，装载**跨槽**：起于上一槽 −144，止于本槽 **619**；本槽 [0,767] 是**接收**窗口 |

另给出两套**不同**的截止：`video_receipt_deadline` = 槽内 **828**（净 60 周期 / 0.60 µs）、
`data_load_deadline` = 下一槽 **824**（净 200 周期 / 2.00 µs）。两者差 140 周期，
T2 的停顿用例**不得**混用同一数字。

---

## 7. 本轮未做的事

未跑 Spectre / MC / OA；未改 main 或其他分支；未合并；未启动 T2；未宣称整芯片或 T2 功能完成。
`D0/D1` 仍恒 0，`STATIC_TIMING_ANALYSIS = NOT_RUN`。
