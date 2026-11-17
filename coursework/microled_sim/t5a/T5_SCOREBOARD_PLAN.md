# T5_SCOREBOARD_PLAN —— 独立期望与覆盖守卫（T5-A 草稿，**未仿真**）

日期 2026-11-17｜目标：**不靠 DUT 派生计数器自证**。每条期望都说明"从哪来、为什么独立、怎样证明非空洞"。

---

## 1. 三条独立性规则（先定规则，再写代码）

| 规则 | 含义 | 反例（禁止） |
|---|---|---|
| R1 期望来自**外部刺激** | 每列/每行的期望字节由 TB 自己的图样函数算出，TB 不读 DUT 内部 | 用 `dut.raw_disp[i]` 当期望去比 `ch_en` |
| R2 跨芯片对齐靠**各自的实际输出** | Data 侧看 `ch_en/ch_pam`（引脚），Scan 侧看 `col_a[511:0]`（引脚），二者在**同一显示窗**比较 | 用 TCON 的 `disp_col` 当 Scan 的期望（同一颗芯片的两个派生量） |
| R3 计数不许同源 | "应发生多少次"由 TB 自己数；"实际发生多少次"由引脚监视器数；两者独立累计 | 用 DUT 的 `bytes_sent` 同时当期望和实测 |

Data **没有** `disp_col/disp_frame` 输出（源码事实），所以**不能**要求它输出列号；
列的归属只能由"这一列装载的字节内容"反推 —— 这正是 R1 的用法。

## 2. 视频图样（可逆、自识别）

| 图样 | 定义 | 用途 |
|---|---|---|
| P1 列迹 | `byte(row, col) = (col*7 + row*13 + 0x5A) & 255` | 每列都不同；可由任意 3 个字节反解列号 |
| P2 行梯 | `byte(row, col) = row & 255` | 验 384 通道逐路映射（配合 LUT 满码/黑码） |
| P3 边界 | 列 0/1/2/1022/1023、跨帧第一列 0 | 首列不丢、环绕不乱 |
| P4 污染 | 人为让 TCON RX 见到 383/385 的列 | 该列必须**全暗**，且不得串到相邻列 |

每列的实际字节序列由 TB 的 `exp_byte(col, frame, idx)` 生成，与 DUT 无共享状态。

## 3. 检查项与判据（先写死）

| # | 检查 | 期望来源 | 判据（非空洞条件） |
|---|---|---|---|
| S1 | 每列 384 字节全部到达 | TB 计数（`n_edges_in_window`） | `==384` 且窗口数 `==1024/帧` |
| S2 | Data#0/#1 的 `ch_en` 与"该列字节经 LUT 映射后的导通时间"一致 | TB 的 `exp_byte` + TB 的 `lut_tab` | 384 路**逐路**相等；采样数 ≥ 每路 64 tick |
| S3 | 同一显示窗内 Scan 实际选中列 == Data 实际显示的列 | Scan `col_a` 解出的全局列号 vs Data `ch_en` 反推的列（用 P1 图样反解） | 1024 次逐列一致；不得有一次"列号不可反解" |
| S4 | 两片 Scan 各 512 次选择，全局严格独热 | 引脚 popcount | 1024 次全部 `==1`；`zero_or_multi_hot==0` |
| S5 | 首列 0、次列 1、末列 1023、跨帧 0 不丢 | 图样 P3 | 四个边界各至少 1 次有效显示 |
| S6 | 污染列全暗且不位移 | 图样 P4 | 该列 `\|ch_en==0` 且**下一列**的期望仍然正确 |
| S7 | BLANK/FAULT 联动熄屏 | 引脚时间戳 | 抬升后 ≤1 ns 全关（五颗同时） |
| S8 | LUT 未提交 / 提交后未重载 → 不导通 | 见 T3-H + T5-A 提案 | 两场景各至少 1 次，且**必须由芯片自保证** |
| S9 | TCON 故障锁存不被 Data/Scan 自动恢复掩盖 | 系统语义 | 故障后需显式重启，不能"下一列又亮" |

## 4. 非空洞守卫（打印 + 断言双份）

```
T5_COVER columns_total=1024 columns_with_onehot=1024
         data0_bytes=384 data1_bytes=384 columns_byte_exact=1024
         scan0_sel=512 scan1_sel=512 zero_or_multi_hot=0
         boundary_hits=4/4 poisoned_dark=<> blank_kill=<> fault_kill=<>
         lut_uncommitted_windows=<> lut_reload_required_windows=<>
```

每条守卫都要断言 `>0`（或 `==期望值`），防止"一次都没发生也算过"。

## 5. VCD 与事件账本

- **窗口化 VCD**：只开 4 段 —— (a) 首 4 列，(b) 列 1022–1023 环绕，(c) 污染列，(d) BLANK/FAULT 注入。
  100 ms 全帧不录。
- **CSV 事件账本**（每列一行，紧凑）：
  `slot, frame, col, scan0_sel_chan, scan1_sel_chan, data0_col_valid, data1_col_valid, ch_en_popcount, first_byte, last_byte, expected_col_from_bytes, match`
  其中 `expected_col_from_bytes` 由 P1 图样反解，`match` 由 TB 独立算出。

## 6. 与"不许伪造"的边界

- 不新增任何 DUT 输出用于打分；读 `raw_disp` 只允许作**一致性交叉检查**（如 T3 的 D16），
  不得作为 S2/S3 的期望来源。
- 不把 TCON 的 `disp_col/fwd_col` 当作 Data/Scan 的独立标签。
- 不用 `bytes_sent` 自证 384 字节。

## 7. 状态

`T5_SCOREBOARD_PLAN = DRAFT`（随 T5 任务书一起送审；未写 TB、未仿真）。
