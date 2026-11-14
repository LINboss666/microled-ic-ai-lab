# TCON T2B-C 报告：启动预充安全（2026-11-14）

**基线** `b02f824` ｜ **分支** `course/microled-assignment-sim-20261112` ｜ **main** 未动
**本轮 EDA**：ModelSim **2 次**（上限 2：A 失败 1 次 + A 重跑 1 次）｜ Spectre 0 ｜ MC 0 ｜ OA 0 ｜ STA `NOT_RUN`
**状态** `WAITING_FOR_T2B_STARTUP_SAFETY_INDEPENDENT_REVIEW`

---

## 0. 一句话

复审从 VCD 里抓到的 **7,680 ns 无效显示许可窗口**是真的：根因是 `LATCH` 被当成"有数据才发"的许可信号，
导致槽 0 的预充 LATCH 被吞、列 0 从未被捕获。修复后 **Run A2 = 57/57 PASS**：
`IDLE 撤 BLANK = 0 拍`、`BLANK 为低而 Data bank 无效 = 0 拍`、**首个被比较的列是列 0**、
帧首两列在两帧里都走完链路、整帧 `1026/1026` 槽各一次选通。
**但 Run B（V1.3 合约 T1）没跑**——2 次预算已用完，T1 新合约 TB 只到 `COMPILED_ONLY`。

---

## 1. 你发现的启动缺陷：确认，且根因比"少一次 LATCH"更深

原始 VCD（`t2b_br_run04_joint`，即上一轮交付的 #4）复现：

```
LATCH^    19,045 ns      ← 槽 0 的 LATCH（应在 9,285 ns）根本不存在
BLANK->0  20,535 ns      ← 首次解除 BLANK
BLANK->1  28,215 ns      ← 违规窗口结束（7,680 ns）
dm0/1_valid->1  28,826 ns ← 首个有效 bank，装的是**列 1**
```

| 环节 | 事实 |
|---|---|
| `latch = latch_seq && safe && !flt && (!act \|\| fw_ok)` | 槽 0 没有 `fw_ok`（还没有窗口关闭）→ **LATCH 被吞** |
| `disp_ok = disp_valid && !disp_poison` | 只看 TCON 自己的标签 → 槽 1 的 827 就"认为列 0 有效" |
| 结果 | 槽 2 的窗口在 Data bank 仍为空时被解除 BLANK，Scan 已选列 0 |
| 列 0 为什么彻底没有 | Data 从没 arm，列 0 的 384 B×2 上了总线却无人接收 |

**根因一句话**：把**结构性时序信号**（LATCH，预充流程的一部分）当成了**数据许可信号**。
V1.3 §12 段0466 的 LATCH 是"在 BLANK 内原子切换显示银行"的动作，它不该等数据。

---

## 2. 改了什么（`tcon_top.v.txt`，其余 RTL 未动）

| # | 改动 | 理由 |
|---|---|---|
| C1 | `unused fw_ok` 门控从 `latch` 移除：`assign latch = latch_seq && safe && !flt;` | 预充 LATCH 必须在 BLANK 内照发 |
| C2 | 新增 `latch_cnt`（**饱和 2 位**）+ `precharge_done` | 两级预充完成的显式标志 |
| C3 | `disp_ok = disp_valid && !disp_poison && precharge_done` | 第三条独立门 |
| C4 | `blank` 加 `!act`；`pwm_start/scan_stb/pwm_tick` 改 `act && disp_ok` | IDLE 不允许任何外部发光许可 |
| C5 | `data_pin_mon.n_edge` 16→32 bit | 384×1026 会溢出（只是报告量，但不该错） |

许可合同现在是一句话：**ACTIVE && 标签有效 && 预充完成**，三条门互相独立。
`LATCH` 仍受 `safe`/`flt` 约束（故障时不发），但**不受数据许可约束**。

**没有新增任何 Data→TCON 物理引脚**；`latch_cnt` 是 TCON 自己的计数，
它与 Data 实际提交是否一致，由独立 Data 模型在仿真中核验（`P52`）。

---

## 3. 逐槽启动时间线（详见 `t2b/STARTUP_PIPELINE_TIMELINE.md`）

| 槽 | 事件 | BLANK | Data bank |
|---|---|---|---|
| 0 | LATCH #1（9,285 ns）预充初始化；832..1598 送列 0 | 1 | 空 |
| 1 | LATCH #2（19,045 ns）切进显示银行 → **列 0 生效**；880 首个 SCAN_STB（列 0） | 1 | **列 0** |
| 2 | 窗口 20,535..28,215：**显示列 0**；827 标签→列 1；828 切列 1 | **0** | 列 0 |
| 3 | 窗口 30,295..37,975：**显示列 1** | 0 | 列 1 |

列 0 与列 1 都显示了，整体延迟两个槽 —— 正是 §9「显示帧边界相对输入延迟，但不丢失帧首两列」。

---

## 4. 两次运行的真实账本（失败的那次不删、不改判）

| run | 结果 | 说明 |
|---|---|---|
| **A（run1）** | **55/56 FAIL** | 唯一失败 `P46_core_compare_not_vacuous`：整帧只有 **898** 次选通，应 1026 |
| A 的根因 | — | `latch_cnt` 写成 **4 bit 自由计数**，每 16 槽回绕；回绕到 0/1 的两槽 `disp_ok` 掉 0 → 每 16 槽丢 2 次选通 → `1026 − 2×64 = 898`，**与实测完全相等** |
| 离线修复 | — | 改饱和 2 位；新增 `P39b_one_strobe_per_slot`（`ph_stb == slot_done−1`）专门守这一类 |
| **A2（run2）** | **57/57 PASS** | `Errors 0 Warnings 0`，五项 transcript 检查全 1 |

`P46` 是上一轮为"防空洞"加的守卫，这轮它抓到的却是**真实 RTL 缺陷**——这正是它该干的事。
两次 transcript 都在包内（`evidence/runA_FAIL_*`、`evidence/runA2_PASS_*`）。

---

## 5. Run A2 的数（复审可直接核）

```
PH1 slots=10 strobes=9  exp=9  core=9  prech=0 skip=0 content=72
    win0=10 win_bytes0=384 win_bad0=0 byte_bad0=0
    first_strobe_col=0  first_core_col=0        ← 上一轮是 1
PH3 strobes=4 core=4 exp=4 prech=0
PH5 slots=1027 wraps=1 strobes=1026 exp=1026 core=1026 prech=0 skip=0
    lbl_bad=0 frm_bad=0 dv_bad=0 content=0 win0=1026 win_bad0=0 byte_bad0=0
T2B_COUNTS assert_count=57 fail_count=0 strobe_count=1063 valid_strobe_count=1026
    skipped_expected=0 content_compare=8208 precharge=0 core_n=1026 wraps=1
    f1=1 f2=1 first_pixel_col=0 bytes_per_window=384
T2B_IDLE_BLANK idle_blanklow_cycles=0            ← 上一轮是 20
COURSE_RTL_RESULT=PASS  (57/57)
```

新增/收紧的硬门：

| 断言 | 判据 | 上一轮 |
|---|---|---|
| `P52_no_unblank_without_data` | 每拍：`BLANK=0 && ACTIVE` ⇒ 两颗 Data bank 有效且未污染 | 932 拍违规 |
| `P53_idle_never_unblanks` | `IDLE` 时 `BLANK=0` 的拍数 = 0 | 20 拍违规 |
| `P54_frame_head_col0_col1_displayed` | 帧1/帧2 的列0、列1 **都**完成比较 | 只有列1 |
| `P19b_startup_first_column_is_0` | 首个被比较的列 = 0 | 是 1 |
| `P39b_one_strobe_per_slot` | `ph_stb == slot_done−1` | 898/1026 |
| `P55_every_compared_column_valid` | `core_n == exp_n && skip_n == 0` | — |
| `P16_no_column_skipped_at_startup` | 启动段 `prech_n == 0 && skip_n == 0` | `prech_n=1` |

原始 VCD 独立复核（`evidence/runA2_vcd_recheck.txt`）：
`LATCH^ @9,285` 存在、`dm_valid@19,046`、`BLANK→0 @20,535 时 col_id=0 且两 bank 有效`、
首窗 tag `col=0 frame=1`、10 窗 ×384×2 字节 `byte_err=0`。

---

## 6. T1：新合约 TB 已写、已编译，**没跑**

按你的裁定，旧 49 条里有 3 条判据本身与 V1.3 冲突，不能原样当验收：

| 旧断言 | 旧判据 | 处理 |
|---|---|---|
| `R4_ready_blank_low` | 配置就绪、**无视频**时 BLANK 必须为低 | **判据反转** → `R4_idle_no_video_blank_high` |
| `R6_recover_blank_low` | 恢复 `fault_n` 后 BLANK 变低（自动恢复） | **判据反转** → `R6_fault_latched_blank_high`（Q3=B 锁存） |
| `B7_col_id_period_1024` | `col_id` 1024 槽后回起点 | **判据修正** → 在 slot 1025 与 slot 1 比较（ACTIVE 下标签滞后 1 槽） |

其余 46 条判据保留。新增 6 条启动合同（`R4_idle_no_video_no_strobe`、`R4b_precharge_never_unblanks_early`、
`R4c_blank_low_after_precharge`、`R7_reset_reprecharge_blank_low`、`T0_permit_before_measure`、
`B0_no_unblank_before_precharge`）。逐条映射在 `t2b/OLD_T1_ASSERTION_MAPPING.md`。

新 T1 还补了 V1.3 视频源（旧 TB **完全没有视频输入**，所以旧 49/49 是在"没有画面"的前提下测出来的），
复位改成 2 µs（≥1 µs）。场景门槛 `27 / 17 / 11 / 55` 由 `scen_min_asserts.sh` 提供，
自测 10/10（纯 shell，不耗预算）。

**状态：`COMPILED_ONLY / NOT_RUN`。** 本轮 2 次预算已用完（A 失败 1 + A 重跑 1），
按你的授权只重跑 A，B 没有跑。

---

## 7. 证成了什么 / 没证成什么

**证成了（有原生 transcript + VCD 复核）**

1. IDLE 状态不再解除 BLANK（0 拍违规）；
2. 首次解除 BLANK 时两颗 Data 显示 bank 已有效，且**首次显示的就是列 0**；
3. 帧首两列（帧 1、帧 2 各列 0/列 1）完整走完 接收→转发→提交→选通，**没有一列靠"预充跳过"回避**；
4. 整帧 1026/1026 槽各一次选通，`skip_n=0`，核心比较 `core_n=1026` 非空洞；
5. 故障锁存熄屏未被回退（`P22/P23/P24` 仍 PASS），恢复后重新预充不早发选通；
6. 时基、828/840/880、DCLK 20 ns、每窗 384 B 全部保持。

**没证成（不许读成通过）**

* **T1 V1.3 合约回归 `NOT_RUN`**：新 TB 只有编译证据；
* `latch_cnt` 是**预测**不是反馈；Data 侧若异常未提交，TCON 不知道（`fault_n` 闭环/CDC 未做）；
* 「两级预充」的级数 2 来自 §9 定性描述，V1.3 没有可机读计数；
* 整帧 VCD 未保留（`$dumpoff`），整帧证据是 transcript 计数器 + 逐窗断言；
* STA `NOT_RUN`；SPI/寄存器/中断 `NOT_IMPLEMENTED`；384/512 通道为行为替身；T3/T4/T5 未开始。

---

## 8. 裁定

| 项目 | 状态 |
|---|---|
| `T2B_STARTUP_SAFETY` | **PASS**（Run A2，57/57；`P52/P53/P19b/P54` 全 PASS） |
| `T2B_NORMAL_DATAPATH` | 保持 `ACCEPT_WITH_SCOPE`（未回退） |
| `T2B_JOINT` | `PASS`（本轮 57/57） |
| `T1_CONTRACT_TB` | `COMPILED_ONLY / NOT_RUN` |
| `T2B_OVERALL` | **`WAITING_FOR_T2B_STARTUP_SAFETY_INDEPENDENT_REVIEW`** |
| `GIT_REMOTE` | 见 `gates.txt` |

停在独立复审闸；未合并 main、未开 PR、未自签 GO、未启动 T3/T4。
