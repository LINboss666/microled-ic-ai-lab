# TCON T2B-BR 限定续测报告（2026-11-14）

**基线** `b1e92cd`（T2B-B 文档收口）｜ **分支** `course/microled-assignment-sim-20261112` ｜ **main** 未动
**本轮 EDA 消耗** ModelSim **1 次**（授权 1 次）｜ Spectre 0 ｜ Monte-Carlo 0 ｜ OA 0 ｜ STA `NOT_RUN`
**T1 `SCEN=ALL`（#5）** 未授权，**未运行**
**状态** `WAITING_FOR_INDEPENDENT_REVIEW`

---

## 0. 一句话

按 `T2B-BR` 任务书把"**验证模型用隐藏 100 MHz 时钟采样**"这个根本问题换成**针脚级采样**，
并在花掉唯一一次预算前后都留了可复算的证据：**#4 = 51/51 PASS，`core_n=1025`，`skipped_expected=0`，
每个装载窗 384 字节，`SCAN_STB` 选中的列 = 两颗 Data 显示 bank 的列**。
但 `IDLE` 的 BLANK 规格冲突**没有修**（登记，未关闭），T1 回归**没跑**，所以 §7 的裁定是
`T2B_JOINT_CONDITIONAL_PASS`，不是 `PASS`。

---

## 1. 逐条对应任务书

| 条目 | 要求 | 本轮做了什么 | 证据 |
|---|---|---|---|
| A1 | 核对 F1–F4 存在且可编译，且不得标 PASS | 见 §2：F1 被**更彻底的方案取代**（不是"推迟一拍"而是"不再有第二时钟"）；F2/F3/F4 保留并进入正式运行 | `02_vlog.log` 0 error 0 warning |
| A2 | 增加**针脚级** Scan 监视：真实 `posedge scan_stb` 采 `COL_ID`/`BLANK`，验 10/5 ns 与仅 BLANK 内 | 新增 `rtl/scan_pin_mon.v.txt`，只用引脚；`scan_model` 本身也从 `posedge clk` 改为 `posedge scan_stb` | §4、`t2b/PIN_MONITOR_OFFLINE_REPLAY.md` |
| A3 | Data 装载补**真实 `posedge dclk`** 的逐字节 monitor | 新增 `rtl/data_pin_mon.v.txt`；`data_model` 也改为只用 DCLK/LATCH/DIN | §3、§4 |
| A4 | 强化不可空洞：逐个数"应检健康选通"，比较次数必须相等；"该有效却被标无效而跳过"必须 FAIL | `exp_n / core_n / prech_n / skip_n` 四元账；`P16/P18/P46/P47` | §5 |
| A5 | 3528 不是丢包；统计延到第 10 个装载窗关闭，逐窗验 384 沿 / 384 字节 | 改为 `run_until_win(10,14)`；`P14/P15/P49` | §6 |
| A6 | IDLE 的 BLANK 冲突登记、分析最小修复对旧 T1 49 条的影响；不得宣称合规 | `t2b/IDLE_BLANK_SPEC_CONFLICT.md`；TB 每次运行打印 `T2B_IDLE_BLANK` | §7 |
| B | 1 次联合运行，禁重试，报告全部计数 | run04，见 §5 | transcript 在包内 |
| C | 普通 push、审核包、停独立审核 | §9、§10 | — |

---

## 2. F1–F4 的真实归宿（重要：这不是"偷偷绕过"，而是问题被消除）

| 编号 | T2B-B 时的补丁 | 本轮状态 |
|---|---|---|
| F1 | TB 观测推迟一拍（`pend`） | **删除**。要求"推迟一拍"的根源是 `scan_model` 用 100 MHz 时钟检边沿。现在 Scan 模型与监视器都直接在 `posedge scan_stb` 上锁存，**没有第二个时钟**，也就不需要推迟。旧代码留在 T2B-B 审核包里（`b1e92cd` 之前），可对比 |
| F2 | Data 标签解码 `{cap[1][7:6], cap[0]}` | **保留**，并成为 `data_model` 与 `data_pin_mon` 的共同解码规则 |
| F3 | tag1 期望改 8 bit | **保留**（`{col[9:8], frame[5:0]}`） |
| F4 | 受控 VCD 窗口 | **保留**并收紧为 `$dumpvars(1, …)`（只 dump 本层引脚与观测信号，不 dump 384 字节缓存），实测 **1.9 MB** |

**F1 的教训写进代码注释**：任何"因为模型晚一拍所以观测也晚一拍"的补丁，都是在用测试去迁就模型的缺陷。

---

## 3. 两个针脚级监视器（新文件）

### 3.1 `rtl/data_pin_mon.v.txt`

* 端口只有 `reset_n / dclk / din / latch` —— **没有 `clk`**；
* `latch_d` **只在 DCLK 上升沿更新**；`LATCH` 上升沿 → 关窗并比较；`LATCH` 下降沿 → 开窗，**该沿即 byte 0**；
* 每窗统计字节数、按自身解出的 `(frame, col)` 逐字节核对 382 个像素字节；
* 1 ns `#1` 只是 delta 稳定（`LATCH`/`DIN` 与沿同刻变化），不是第二个时钟。

### 3.2 `rtl/scan_pin_mon.v.txt`

* 端口只有 `reset_n / scan_stb / col_id / blank`；
* 在**真实** `posedge scan_stb` 采样，测 `setup`（距上次 COL_ID 变化）与 `hold`（到下次变化）；
* `n_outside_blank` 直接数"BLANK 外的选通"。

### 3.3 `rtl/data_model.v.txt` / `rtl/scan_model.v.txt`（改造）

两个替身都删掉了 `clk` 端口，改成与真实芯片同样的采样事件。
`data_model` 的 384 字节捕获、标签解码、逐字节校验仍是**模型自己算的**，不与 TCON 共享计数器。

---

## 4. 先离线验证"采样规则"，再花预算

`t2b/PIN_MONITOR_OFFLINE_REPLAY.md` + `tools/offline_pin_monitor_replay.py`：
用 **T2AR2 run03 的归档 VCD**（上一轮已被独立复审接受为 D0/D1 逐字节正确）回放这两条规则。

```
DATA: windows=22  all_384=True
  t=18245000  n=384 byte0=5A/67 pattern_col=[0, 256]
  t=28025000  n=384 byte0=5B/68 pattern_col=[1, 257]
  ...
SCAN: strobe_edges=22   setup min=8790.0 ns   outside_blank=0
```

结论：**22 个窗口全部恰好 384 字节，第 0 个字节就是第 0 行**（不会错位一个字节）。
复算过程中还排除了一个坑：若 `latch_d` 在"非采样沿的 LATCH 变化"时也更新，窗口会从 22 个掉到 **9** 个
（整窗被提前消费）。RTL 只在 `always @(posedge dclk)` 里更新 `latch_d`，因此不会踩到。

---

## 5. #4 正式运行（唯一一次，未重试）

**运行** `D:/ic617_course_sim_20261112_native/t2b_br_run04_joint`
**源码 SHA-256** 见 `00_source_sha256.txt`（11 个文件，逐字节可核对）
**编译** `Errors: 0, Warnings: 0` ｜ **VCD** 1,896,065 B ｜ **耗时** 约 40 s

```
PH1 slots=11 strobes=10 exp=10 core=9 prech=1 skip=0 content=72 edges=4224
    win0=10 win_bytes0=384 win_bad0=0 byte_bad0=0 first_strobe_col=0 first_core_col=1
PH3 strobes=4 core=3 exp=4 prech=1 disp_col=3 dm0_col=3 dm1_col=3
PH5 slots=1027 wraps=1 strobes=1026 exp=1026 core=1025 prech=1 skip=0
    lbl_bad=0 frm_bad=0 dv_bad=0 content=0 win0=1025 win_bad0=0 byte_bad0=0
T2B_COUNTS assert_count=51 fail_count=0 strobe_count=1064 valid_strobe_count=1025
    skipped_expected=0 content_compare=8200 precharge=1 core_n=1025 wraps=1
    f1=1 f2=1 first_pixel_col=1 bytes_per_window=384
T2B_IDLE_BLANK idle_blanklow_cycles=20
COURSE_RTL_RESULT=PASS   (51/51)
```

五项 transcript 检查（`t6_check_transcript.sh`）：`CHECK0..4` 全 1，`RUNNER_VERDICT=PASS`。

### 5.1 核心等式与它的计数

* `core_n = 1025` 次比较，全部在**真实 `posedge scan_stb`** 上做；
* `skip_n = 0`：**没有任何一次"应当比较却被判无效而跳过"**；
* `prech_n = 1`：只有第 1 个选通（列 0，此时 Data 尚未提交过任何 bank）被记为预充列，
  且此时 `dm0_ncom = dm1_ncom = 0`，即"确实还没有东西可显示"，不是"标记无效逃过比较"；
* `exp_n = core_n + prech_n + skip_n` 恒成立（`P18` / `P46` 断言）。

### 5.2 用原始 VCD 复核（不是读 TB 的自述）

`t2b_br_run04_vcd_recheck.txt`：直接解 `tcon_t2b.vcd`（phase-1 窗口，10 个窗口 / 10 次选通）

```
windows=10  strobe_edges=10
  t=28825000  n=384 tag_col=1  tag_frame=1  d1tag=1  byte_err=0
  t=38585000  n=384 tag_col=2  tag_frame=1  d1tag=1  byte_err=0
  ...（10 个窗口 byte_err 全 0）
windows with byte errors: 0

 idx  time_ns     COL_ID  BLANK  setup_ns
   0  19565000    0      1      19565
   1  29335000    1      1      520
   2  39095000    2      1      520
   ...  9  107455000   9      1      520
setup min=520.0 ns  max=19565.0 ns  outside_blank=0
COL_ID sequence at the strobes : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
```

要点：

* **`byte_err=0` 是对 10×384×2 = 7,680 个字节逐字节核对**（用窗口自己的 tag 解出 `(frame,col)` 再套公式），
  不是"TB 说 0 就是 0"；
* 每个窗口的第一个提交时刻（如 28,825,000 ns）**早于**对应选通（29,335,000 ns），
  选通时 `COL_ID` 与窗口 tag 的列号**相等**（1 vs 1、2 vs 2 …）；
* 第 0 次选通（`COL_ID=0`，19,565,000 ns）**早于**第一个窗口提交，正是那一列预充，
  与 `prech_n=1` 完全对应；
* `setup = 520 ns`（≥ 10 ns），`hold` 远大于 5 ns，**全部选通在 BLANK 内**。

---

## 6. `win_edges = 3528`：已按复审的算术确认，并改成正确的口径

装载窗 `[832,1600)` **跨两个槽**：起始槽只剩 `976−832 = 144` 个参考周期 = **72 个 DCLK 沿**，
下一槽再走 312 个沿，合计 384。10 个槽时统计到第 10 槽结束 → `9×384 + 72 = 3528`。
**这不是丢包，是截取位置。**（本轮 `edges=4224 = 11×384`：因为跑了 11 个槽、11 个窗全部完整，
数字与"每窗 384"精确自洽。）

本轮已把判据换成**逐窗**而不是"总数"：

* `P14_ten_complete_windows`：`dpm0_win == dpm1_win == 10`；
* `P15_every_window_384_bytes`：`win_badlen == 0` 且最后一窗 384；
* `P49_every_window_384_bytes`（整帧）：1025 个窗口 `badlen == 0`；
* `P17/P50_payload_byte_exact`：每个窗口 382 个像素字节逐字节校验。

---

## 7. IDLE 的 BLANK 冲突：登记，未修复，未宣称合规

`t2b/IDLE_BLANK_SPEC_CONFLICT.md` 记录了：V1.3 段 0810 要求"配置/预充/正常同步有效后才撤销 BLANK"，
而当前 `blank = blank_seq || !safe || flt || (act && !disp_ok)` 在 IDLE 下退化成 `blank_seq`。

* **实测**：#4 里 `blank==0 && FSM≠ACTIVE` 共 **20 个参考周期**（`T2B_IDLE_BLANK`），
  全部发生在复位后到第一个合法帧头之间；
* **最小修复**：加一项 `!act`（一行）；或加 `precharge_done`（需要 SPI，`NOT_IMPLEMENTED`）；
* **代价**：静态推演会打破旧 T1 至少 5 条（`R4_ready_blank_low`、`R6_recover_blank_low`、
  `R6_no_tick_while_blanked`、`T1_no_tick_in_blank`、`B8_no_tick_in_blank_frame`），
  而这 5 条验的正是"没有视频也能跑骨架"的旧前提；
* **本轮决定**：不改。改了就必须重跑 T1（#5 未授权），否则等于把未验证的改动塞进交付物。
  **因此本轮不声称 IDLE 已合规。**

---

## 8. 这一轮真正证成了什么 / 没证成什么

**证成了（有原始证据，可独立复算）**

1. V1.3 列首同步接收（`COL_SYNC + DE + byte0` 同沿）在 1027 槽内**无一次协议错误**；
2. 1025 次健康选通里，**`SCAN_STB` 时刻的 `COL_ID` = 两颗 Data 显示 bank 的列号 = 载荷里编码的列号**，
   帧号两侧一致，bank 有效且未污染；
3. 每个装载窗恰好 384 字节（1025 个窗口 `badlen=0`），每字节与 `(frame,col)` 的公式吻合；
4. 帧号跨 1024 槽回卷正确传播（`f1=1, f2=1, wraps=1`）；
5. 故障语义：预取后第 769 字节 → 溢出位置位 → 锁存 FAULT → 选通/LATCH/TICK 全 0、BLANK 恒高、
   载荷转零、Data 侧能识别污染列；
6. 复位恢复：重新预充不多发选通（4 次选通 / 5 槽），且恢复后比较数 = 期望数。

**没证成（明确列出，不许被读成"已通过"）**

* **T1 49 条回归未跑**（#5 未授权）→ `T1_REGRESSION = NOT_RUN`；
* **IDLE 的 BLANK 契约**：`SPEC_CONFLICT_REGISTERED`，未修复；
* **故障列的跨流水隔离**：本轮只证"该列不被选通 + 载荷转零"，**没有**证明"已经上总线的坏字节
  不会在后续列被显示"——那需要 Data 侧的行级存储与显示时序，属 T3/T4；
* **`fault_n` 毛刺 / CDC**：未做（无同步器、无去毛刺）；
* **STA**：`NOT_RUN`，520 ns / 5 ns 是理想 RTL 相位模型下的仿真值；
* **SPI / 寄存器 / 中断**：`NOT_IMPLEMENTED`；
* **384/512 通道电气实现**：行为替身，不是驱动阵列；
* **T3/T4/T5**：未开始。

---

## 9. Git

* 分支 `course/microled-assignment-sim-20261112`，`main` 未合并、未开 PR、未强推、未关 hook；
* 本轮提交见 §11（`git rev-parse HEAD`）；
* 远端：普通 `push`，结果以实际回执与回读为准（见 `gates.txt`）；回读失败即登记 `REMOTE_PENDING`，
  不用"推送成功回执"冒充"已独立回读远端 HEAD"。

## 10. 审核包

见同目录 `MicroLED_TCON_T2B_BR_20261114.zip`：修改前后 diff、正式源码、两个针脚监视器、
离线回放脚本与输出、run04 原生 transcript / vlog / VCD / 校验输出、门槛判定、SHA 清单、未完成项。

## 11. 裁定

| 项目 | 状态 |
|---|---|
| 针脚级采样（Scan / Data） | `IMPLEMENTED` + 离线回放验证 + #4 实测 |
| T2B 联合验证 | `PASS`（51/51，`core_n=1025`，`skip=0`） |
| 装载窗字节数 | `PASS`（1025 窗 × 384 B，逐字节核对） |
| IDLE BLANK 契约 | `SPEC_CONFLICT_REGISTERED / NOT_COMPLIANT` |
| T1 回归 | `NOT_RUN`（#5 未授权） |
| T2B 整体 | **`T2B_JOINT_CONDITIONAL_PASS`** |
| 下一步 | 待独立复审；复审放行后再申请 #5（T1 `SCEN=ALL`）与 T3/T4 |
