# TCON T2AR2 限定纠错报告（先于 T3/T4）

**任务** `TCON-T2AR2-20261114` ｜ 依据：独立复审 `MicroLED_TCON_T2A_独立复审报告_20261114.md` 与限定纠错任务书
｜ 分支 `course/microled-assignment-sim-20261112` ｜ 基线 `14bf0fe` ｜ 本轮一个提交（见 `SUBMIT_PACK`）
｜ 状态：`WAITING_FOR_T2AR_INDEPENDENT_REVIEW`

---

## 1. 一页进度表（先读这张）

| # | 你的原缺陷（复审原文） | 改了什么 | 为什么 | ModelSim 具体测了什么 | 结果 |
|---|---|---|---|---|---|
| P0-1 | `tcon_top` 里 `blank = blank_seq \|\| !safe` 漏了 `slot_bad`；VCD 里 `slot_bad=1 && safe=1 && BLANK=0` 累计 9,320 ns | `blank = blank_seq \|\| !safe \|\| slot_bad`；`slot_bad` 改为**槽内粘滞**（`tb_start` 取 `!safe`，槽内任意一拍 `!safe` 也置位） | 故障恢复后不能在同一个槽里把 BLANK 重新打开，否则"整槽锁定熄屏"名不副实 | 新列 18：故障跨列起点、拍 100 恢复。计数器直接统计该槽 `blank==0` 的拍数，并要求 `LATCH/PWM_START/SCAN_STB` 全 0 | **X19/X20/X21 PASS**，`blank_low=0`（原反例是 932 拍） |
| P0-2 | 故障打断 LATCH 后，第 11 列仍在 116,425 ns 发出 `SCAN_STB` | 同一条粘滞规则；`latch/pwm_start/scan_stb/pwm_tick` 全部 `&& !slot_bad` | LATCH 没完成却被选通 = 未装载完成的列被选中 | 列 11（故障落在 828..836，即 LATCH 脉冲中段）统计 `scan_stb`/`pwm_start`/`latch` 拍数 | **X22/X23 PASS**（stb=0，pst=0，latch=0） |
| P0-3 | 预取后出现第 769 字节，TX 已锁存有效位，"此前发出的数据不能全部撤销" | `tcon_video_rx` 增加 `col_revoke`（仅对已提交列脉冲）；`tcon_data_tx` 增加 `revoked_q`，预取后撤销即转零并置 `load_blank`；`tcon_top` 在 `slot_cycle ≥ 831` 的撤销上置 `slot_bad` 整槽熄屏 | 已发出的字节物理上不能追回，正确做法是**取消这一列的显示许可**（BLANK 保持 + 不发 PWM_START/SCAN_STB），而不是假装撤销 | 新列 19：SYNC@830 提交 → 拍 834 送第 769 字节（**晚于** 831/832 预取点）。测 `err_flags[1]`、`slot_bad@900`、`SCAN_STB=0`、`PWM_START=0`、撤销后零字节数 | **X24/X25/X26/X27 PASS**（`lb=1, pbn=0, bytes=384`） |
| R02 | "先过早同步→再正常同步"是否算协议无效，未核查 | `proto_bad`：`COL_SYNC` 早于 768 字节到达即判定该列协议无效，后续合法同步不能"救活"；**不新增错误位**（6 位状态契约已冻结，`[0]` 已能唯一表达） | 一列只允许"768 B + 一个同步"（合同 §5）；先到的过早同步已证明字节相位不成立 | 新列 16：拍 600 过早同步 + 拍 830 合法同步 | **X28/X29 PASS** |
| P1 | `dut_small` 未连接 `err_now`，vsim-3017/3722 两条警告 | TB 补连接 | 警告会掩盖真问题 | `vsim` 尾部 `Errors: 0, Warnings: 0` | **0 警告** |
| P1 | 断言只覆盖"故障不位移"，但 TB 的列号来自 DUT 自身 | 新增**独立参考时基**：TB 内按 576/448 规格算术复现槽长，逐拍比较 `slot_cycle`/`slot_start`；`SCAN_STB` 拍上比较 `COL_ID` 与参考列号 | 你的原话："TB 的 `tb_col` 推进由 DUT `slot_cycle/slot_len` 派生，不能独立证明故障期间绝对时间轴未位移" | 整帧 1,008,949 拍逐拍比较 | **X30/X31 PASS**（`rf_bad=0, rf_col_bad=0`，参考槽数 1033） |
| P1 | setup/hold 用 `change_high==0` 只说明"高电平没变" | 保留时间戳法（S1/S2/X18），并用归档 VCD 独立复核 | 复审 §P1-E 要求以 VCD/时间戳为准，且不得宣称硅后成立 | VCD 独立解析：窗内 **setup 最小 5.000 ns / hold 最小 15.000 ns**（≥3/≥1）；DCLK 相邻沿间隔 8,482 个样本全部 20.000 ns | **S1/S2/X18 PASS**；STA 仍 `NOT_RUN` |
| P1 | GitHub 仍 `REMOTE_PENDING` | 见 §6 | — | — | 仍 `REMOTE_PENDING`（有证据，不重复重试） |

**一句话**：三处"故障期间显示系统必须处于安全状态"的控制缺口都补上了，并且是**用独立计数器/独立参考时基**测的，不是用 DUT 自己的信号自证。

---

## 2. 三个 P0 的实质（为什么这样改）

### 2.1 `slot_bad` 从"边界一次判定"改为"槽内粘滞"

原实现只在 `tb_start` 采一次 `!safe`。故障若发生在槽中间并恢复，`slot_bad` 仍是 0，于是：

- `blank` 在 `[c, 767]` 又变低（你测到的 9,320 ns）；
- `LATCH` 被打断后，`SCAN_STB` 照样在 880 发出。

现在：`tb_start` 重新判定，槽内任意一拍 `!safe` 也置位，只有**下一个干净列边界**才清。代价是"一个故障丢掉一整个槽的显示时间"，这对 `fault_n` 这种全局安全信号是正确取舍。**时基不动**（没有用复位时基来掩盖问题）。

### 2.2 预取后撤销 = 取消显示许可，不是"撤回字节"

`data_tx` 在 831/832 的下降沿预取 byte 0，此后每 20 ns 发一个字节。第 769 字节若在 834 到（已过预取点）：

- 835 拍 `err_flags[1]` 置位、`ok/col_ok` 清零、`col_revoke` 脉冲；
- 835 下降沿起 `revoked_q=1` → 载荷转零、`load_blank=1`；
- 836 拍 `slot_bad=1` → 该槽 `PWM_START`(840)/`SCAN_STB`(880) 全部不再发出。

**为什么不"撤回"**：834 之前发出的 2 个字节已经在总线上，RTL 无法收回。安全状态只能是"这一列不被选通、不进入灰阶"，所以整槽熄屏。像素层面的最终后果属于 T3/T4（Data/Scan 行为模型），本轮**不声称**光学已安全。

### 2.3 `proto_bad`：先过早同步 → 整列协议无效

合同 §5 只写了"同步时字节数 < 768 → underrun → 作废"，但没说"之后再补一个合法同步能不能救"。按"一列 = 768 B + 一个同步"的定义，先到的过早同步已经证明该列字节相位不成立，因此整列作废、后续同步不得复活。`err_flags[0]` 已能唯一表达这类错误，**不加第 7 位**，避免破坏 T2A 已交付的 6 位观测契约。

---

## 3. 运行账本（4 次，全部保留，含两次失败）

任务书给的预算是"正式 ModelSim 最多 4 次"，你建议"最多两次"。**实际用了 4 次**，原因是前两次各自抓到一个真缺陷，都必须留证并修掉后才能拿到你要的那两项结果：

| run | 时间 | 目的 | 断言 | 结果 | 失败物 |
|---|---|---|---|---|---|
| run01 | 15:31:45（12 s） | T2AR2 联合测试（首次） | 7/63 | **FAIL** `T7_no_change_while_dclk_high` | 保留：`t2ar2_run01_all/`（transcript + VCD 13.3 MB） |
| run02 | 15:33:12（17 s） | 修 T7 后复测 | 62/63 | **FAIL** `X31_abs_timebase_lockstep_reference` | 保留：`t2ar2_run02_all/`（`rf_bad=1,010,995`） |
| run03 | 15:35:24（12 s） | 修 X31 后复测（联合测试） | 63/63 | **PASS**，`Errors: 0, Warnings: 0` | — |
| run04 | 15:35:59（4 s） | T1 `SCEN=ALL` 回归 | 49/49 | **PASS** | — |

**run01 的真缺陷**（不是测试台问题）：`revoke` 分支直接清 `d0/d1`，可能落在 DCLK 为高的下降沿上，破坏"字节只在 DCLK 低电平发射"的接口规则。修法：撤销只置 posedge 域的 `revoked_q` 标志，载荷在下一次合法发射沿转零。**T7 是原有断言，本轮没有为它改判据。**

**run02 的真缺陷**（测试台缺陷，我的）：参考时基用 `#1` 采样 TB 的 `cfg_valid/run_en/rx_ready`，而 TB 是在 posedge 之后才驱动这些量，于是参考模型比 DUT **早一个周期**启动，逐拍比较全线错位。修法：加 `rf_arm` 寄存器对齐到 DUT 真正重启时基的那一拍。run02 还暴露了第二个问题：`revoke` 曾作为计数器分支的 `else if`，导致装载窗从 768 拍涨到 769 拍（`col19 bytes=385`）；已改为嵌套标志更新，run03 恢复 384。

> 补充说明：run01/run02 是本轮**新增代码**的缺陷，不是 T2AR 既有 49/49 的回归失败；T2AR 的 49 条在 run03 里全部仍然 PASS。

---

## 4. 证据分级（"归档日志离线检查"≠"新增原生仿真"）

| 结论 | 证据类型 | 可否据此宣称 |
|---|---|---|
| T2AR2 63/63、T1 49/49 | **新增原生 ModelSim 10.5b 运行**（run03/run04），transcript 原样保留 | 可以（限这两套断言覆盖面） |
| T6 五条件、MIN_ASSERTS 10/10、参考时基算术 4 项 | 离线重跑检查器 / 纯 shell 自测 | 只能证明"检查器与模型本身自洽" |
| D0/D1 逐字节 3,840 样本 0 失配、窗内 setup/hold、DCLK 20 ns | 对 run03 **原始 VCD** 的独立解析（`t2ar2_d0d1_samples.csv`，8,509 行） | 独立于 TB 的二次核对 |
| `fault_n` 毛刺/同步器、CDC、STA、灰阶联动、整芯片 | **未做** | 不得宣称 |

VCD 独立解析的边界要说清：dump 只覆盖槽 0..27（`tb_col>=28` 后 `$dumpoff`），所以"27 个装载窗、21 个满 384 沿、10 个有效列共 3,840 样本 0 失配"是**该窗口内**的结论，不是整帧。零载荷窗 = {4,5,7,8,9,16,18,21,22,23,25,26}，与设计里"作废/撤销"的列完全一致；列 19 不在零载荷集合里（撤销前有真实字节），符合 P0-3 的语义。

---

## 5. 仍有何风险（不要当成已解决）

1. **像素级后果未证明**。本轮只保证"控制沿一致 + 该槽熄屏"；Data 锁存/灰阶引擎与 Scan 选通的物理联动要等 T3/T4。复审的原话（"不能据此断言实际 LED 已经错误发光"）在本轮同样成立，反向也不成立。
2. **`fault_n` 仍是理想同步输入**。异步毛刺、亚稳态、同步器延迟都未覆盖；`safe` 组合进 `blank/latch/stb`，真实芯片需要同步器 + 去抖，本轮没有做，也没有声称做了。
3. **一个故障丢掉整槽**是本轮的有意取舍（fail-safe），代价是可见的闪烁/暗列；是否需要"仅丢本列、保留上一列显示"的策略，属于系统级取舍，留给后续轮次裁定。
4. **setup/hold 只是理想 RTL 相位**（5 ns / 15 ns），STA 仍 `NOT_RUN`；不构成硅后时序结论。
5. **T1 的 49 条断言没有为新增语义增加覆盖**（只在 T2A 侧加了 14 条），T1 只做回归不改判据。
6. **`dut_small`（N_COL=8）只证明参数化回卷**，不等于 1023→0 跨帧数据的完整证明；跨帧 bank 归属仍由列 1022/1023/0 三条覆盖。

---

## 6. Git

- 分支：`course/microled-assignment-sim-20261112`，未合并 `main`、未开 PR、未自签 GO。
- 基线 `14bf0fe`（T2AR），本轮一个新提交；提交前跑 `scripts/precommit_safety_check.py`（staged 模式），并 `git diff --check`。
- 远端：上一轮 push 因 git 传输层故障未成功，远端仍 `f06325b`；本轮按任务书**只做一次**常规 fast-forward 尝试，失败即登记 `REMOTE_PENDING`，不重试、不强推、不关 hook、不用 API 伪造。

---

## 7. 本轮改动文件

| 文件 | 改动 |
|---|---|
| `rtl/tcon_top.v.txt` | `blank` 纳入 `slot_bad`；`slot_bad` 槽内粘滞；`col_revoke` 接入；COL_ID 策略注释 |
| `rtl/tcon_video_rx.v.txt` | 新增 `col_revoke`、`proto_bad`；`sync_commit` 增加 `!proto_bad` |
| `rtl/tcon_data_tx.v.txt` | 新增 `revoke` 输入与 `revoked_q`；载荷在撤销后转零；装载计数不被撤销偷拍 |
| `rtl/tcon_t2ar2_edge_table.md` | **新增**：实现前冻结的三组反例逐拍边沿表 + 规则 G1/G2/G3 |
| `rtl/T2A_INTERFACE_CONTRACT.md` | §4/§5 增补：故障后整槽熄屏、预取前后 769 字节的两种处置、过早同步→协议无效、830 截止的措辞边界 |
| `tb/tcon_t2a_tb.sv.txt` | 列 16/18/19 新用例；每槽 BLANK/STROBE 计数；窗口按 TB 槽号归属；独立参考时基（X30/X31）；`err_now` 连接；49→**63** 条断言 |
| `tb/run_tcon_t2a.sh` | 断言下限 49→63 |
| `tb/run_tcon_t1.sh` | 增加硬墙钟 `timeout`（不改 49 条判据） |
| `tb/test_ref_timebase.sh` | **新增**：参考时基算术离线自测（576/448、1,000,000 拍、frac 周期） |

---

## 8. 未做（与任务书一致）

Spectre / Monte Carlo / Cadence OA **0 次**；未使用真实 PDK；未复制模型卡进 Git；未做 SPI/中断/CDC、T3/T4/T5 联调、STA、整芯片；未更改 50 MHz、64 tick、五芯片结构；未合并 main、未创建 PR、未自行宣布验收。
