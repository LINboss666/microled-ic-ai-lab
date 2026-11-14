# VIDEO_INPUT_SPEC_COVERAGE — V1.3 视频输入要求逐条覆盖与证据状态

**任务** `TCON-T2B-BR-20261114` ｜ 基线 `b1e92cd` ｜ **本轮 ModelSim 1/1 已用（#4 PASS），T1 #5 未授权未跑**
**状态口径**
`VERIFIED` = 本轮原生 ModelSim #4 PASS 且判据在**针脚级**成立；
`PIN_MON_PASS` = 由针脚级监视器在 #4 中实测通过，但证据窗口只覆盖 phase-1 的 10 个窗口；
`REGISTERED` = 已识别为规格冲突，**未修复、不算通过**；
`NOT_RUN` = 没跑；`NOT_IMPLEMENTED` = 没实现。

> **先读这一句**：本轮把"用什么时钟采样"这个根本问题修好了，并拿到 **51/51 PASS**。
> 但 **T1 回归没跑**、**IDLE 的 BLANK 冲突没修**、**故障列的跨流水隔离没证**。
> 因此本文不会出现"T2B 通过""V1.3 合规"这类结论，只逐条给状态。

---

## 1. 逐条覆盖

| # | V1.3 要求（出处） | 实现位置 | 本轮证据 | 状态 |
|---|---|---|---|---|
| V1 | `COL_SYNC` 与 byte0 同一 PCLK 上升沿（§9 段0324、§12 段0411） | `tcon_video_rx.v.txt` `at0` 分支 | #4 全程 1027 槽无协议错误；`err_flags` 只在注入用例里置位 | `VERIFIED` |
| V2 | 每列恰好 768 字节（§9、§12 段0406） | RX `idx` + 截止 830 | 767/769 分别置 `[0]`/`[1]`（P20/P35）；正常列 `col_valid=1` | `VERIFIED` |
| V3 | `VSYNC` 与首列 `COL_SYNC` 同沿（§9、§12 段0416） | RX `vs_p`/`next_col`；top `frame_start` | 错位 VSYNC 置 `[4]`（P37）；跨帧 `f1=1 f2=1`（P45） | `VERIFIED` |
| V4 | 允许短暂停顿、整列在装载窗前完成（§9 段0324） | RX 只在 `de=1` 计数 | 本轮 TB 无停顿用例（T2A 轮有 20 拍停顿用例，但属旧协议 TB） | `NOT_RUN` |
| V5 | 1024 列/帧、102.4 kHz 平均列率（§4、§9） | 时基不变 | `PH5 slots=1027 wraps=1`，`P39/P40` | `VERIFIED` |
| V6 | 无 READY 握手（§9） | `safe` 只用模式级 `rx_ready` | 无专门断言 | `NOT_RUN` |
| V7 | 两 Data、各 384 B/列（§12 D0/D1 行） | `tcon_data_tx` 384 B/口 | **1025 个窗口 `badlen=0`，每窗 384 B**；VCD 逐字节复核 10 窗 × 384 × 2 = 7,680 B `byte_err=0` | `VERIFIED` |
| V8 | 两 Scan、`COL_ID[0]` 选片、`[9:1]` 选 512 路（§12 段0486、§4 段0156） | `scan_model.v.txt` | `P44` 通道 ≤ 511；选通时刻 `COL_ID` 序列 0..9 实测 | `PIN_MON_PASS` |
| V9 | `SCAN_STB` 在 BLANK 内锁存列地址（§12 段0491、§14 段0709） | `tcon_top` `scan_stb` 门控 | `spm_oob=0`（1064 次选通全部在 BLANK 内）；VCD 复核 `outside_blank=0` | `VERIFIED` |
| V10 | `LATCH` 仅 BLANK 内原子切换（§12 段0466） | `tcon_slot_seq` 828..831 | `P11_latch_at_828` | `VERIFIED` |
| V11 | 四级标签 `rx=s / fwd=s / disp=s−1 / lit=s−2`（§9 段0323 + 裁定） | `tcon_top` `fw_*`/`disp_*`；`tcon_data_tx` `fwd_*`+`load_done` | **`core_n=1025` 次在真实 `posedge scan_stb` 上比较**：`COL_ID == dm0_col == dm1_col`，`lbl_bad=0`，`skip_n=0` | `VERIFIED` |
| V12 | 数据错误→锁存熄屏直到清故障（§20 段0917-0920，Q3=B） | `tcon_top` 四态 FSM + `blank` | `P21/P22/P23/P24/P25`：FAULT 后 `f_stb=0 f_latch=0 f_tick=0 f_blanklow=0 f_dnz=1` | `VERIFIED`（限于已注入的 6 类错误） |
| V13 | 无有效显示标签不得选通（Q2=A 裁定） | `scan_stb = stb_seq && safe && !flt && (!act \|\| disp_ok)` | 预充列只出现 1 次（`prech_n=1`）且当时 `ncom=0` | `VERIFIED` |
| V14 | 启动预充不丢首列（§9 段0323） | ACTIVE 下首槽 `disp_valid=0` → BLANK 保持、无选通 | `PH1 strobes=10`（11 槽）、`first_strobe_col=0` | `VERIFIED`（首列只"不显示"，未丢数据；见 §3 风险） |
| V15 | 50 MHz DCLK 连续、384 沿/窗（§12 段0461、§14） | `tcon_data_tx` | `P10` 周期恒定 20 ns；**每窗 384 沿**（`P14/P15/P49`，不再用按槽累加的 `win_edges`） | `VERIFIED` |
| V16 | 上电/配置/预充/同步有效前保持 BLANK（§9 段0810） | **未实现**：IDLE 下 `blank = blank_seq` | `T2B_IDLE_BLANK idle_blanklow_cycles=20`；`t2b/IDLE_BLANK_SPEC_CONFLICT.md` | `REGISTERED`（**不合规，未修复**） |

---

## 2. 本轮"实物"增量

| 实物 | 文件 | 状态 |
|---|---|---|
| 针脚级 Scan 监视器（只用 `scan_stb/col_id/blank`） | `rtl/scan_pin_mon.v.txt`（新） | #4 实测 |
| 针脚级 Data 监视器（只用 `dclk/din/latch`，逐字节） | `rtl/data_pin_mon.v.txt`（新） | #4 实测 |
| Data 替身改为**无参考时钟**（`posedge dclk` + LATCH 电平） | `rtl/data_model.v.txt`（改） | #4 实测 |
| Scan 替身改为**真实 `posedge scan_stb`** 锁存 | `rtl/scan_model.v.txt`（改） | #4 实测 |
| 联合 TB 51 条断言（P01–P51），核心比较改到引脚 | `tb/tcon_t2b_tb.sv.txt`（改） | 51/51 PASS |
| 断言下限 39 → 51，运行前打印源码 SHA 与预期量 | `tb/run_tcon_t2b.sh`（改） | 已执行 |
| 采样规则离线回放脚本 | `tools/offline_pin_monitor_replay.py`（新） | 在 T2AR2 归档 VCD 上验证 |

---

## 3. 必须一起读的三条限制

1. **`core_n=1025` 是"每个健康选通都真的比较了"**，不是"每个槽都健康"。
   `exp_n=1026`，其中 1 次是预充列（`ncom=0`，确实无内容可显示），`skip_n=0`。
   `P18/P46/P47` 把这三个数绑在一起，任何"应检被跳过"都会 FAIL。
2. **首列（列 0）不显示**：首槽 `LATCH` 被 `fw_ok` 门控（没有已完成窗口），
   所以 Data 侧第一次提交发生在第 2 槽，列 0 只作预充。这是"预充"语义，但**是设计选择**，不是 V1.3 明文；
   若要求首列可见，需要改启动时序（不在本轮授权内）。
3. **VCD 证据窗口只覆盖 phase-1**（10 个窗口，`$dumpoff` 控体积）。
   整帧 1025 个窗口的证据是 transcript 里的计数器 + `P49/P50`，没有逐窗口的 VCD 逐字节复核；
   复审若要整帧 VCD，需要在下次运行时放开 dump（体积会到 GB 级，见 `T2AR2` 的教训）。

---

## 4. 结论

- V1/V2/V3/V5/V7/V9/V10/V11/V13/V14/V15 达 `VERIFIED`；V8 `PIN_MON_PASS`；
  V12 限于已注入错误类型；V4/V6 `NOT_RUN`；**V16 `REGISTERED`（不合规）**。
- **T1 49 条回归 `NOT_RUN`**（#5 未授权）。
- 不得据本文件宣称"T2B 通过""V1.3 全合规""五芯片联动已验证"——
  正确写法是 `T2B_JOINT_CONDITIONAL_PASS`。
