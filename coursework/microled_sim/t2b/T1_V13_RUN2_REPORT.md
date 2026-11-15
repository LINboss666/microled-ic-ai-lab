# T1 V1.3 复验（第二次授权运行）报告 — 2026-11-15

**基线** `daa710dedd3fa39ec211cc60063034a77cbaaaca` ｜ **分支** `course/microled-assignment-sim-20261112` ｜ **main** 未动
**本轮 EDA**：ModelSim **1 次**（授权 1 次，已用完）｜ Spectre 0 ｜ MC 0 ｜ OA 0 ｜ STA `NOT_RUN`
**结果**：**FAIL** —— 51 条执行（50 PASS / 1 FAIL `B7_col_id_period_1024_after_wrap`），4 条未执行
**状态**：`WAITING_FOR_T1_V13_INDEPENDENT_REVIEW`
**上一轮报告**：`T1_V13_RUN_REPORT.md`（原样保留，未覆盖）

---

## 0. 两件事

**好的一半**：`T3_load_384_dclk_edges` **修好了并且 PASS**，而且此前从未执行过的
**首帧 1024 槽整组 `B1`–`B6` 全部 PASS**（1024 槽 / 首槽 976 / 576 长 448 短 / 1,000,000 拍 / 回绕 1 次）。

**坏的一半**：`B7` 失败，而且是**又一个测试台采样相位问题**——不是 RTL。
`col_id` 在每槽**周期 828** 更新（VCD 实测），所以在槽 K 的**周期 0** 读到的是槽 K-1 写入的值（= 列 K-2）。
`B7` 拿"槽 1 的周期 0"去比"槽 1025 的周期 0"，而槽 1 那次还没有任何标签（是复位默认 0），
于是比成了 `0` vs `1023`。

按任务书：仍 FAIL → 立即停闸，没有第二次，也没有改判据。

---

## 1. 本轮唯一改动（只改测量实现，判据一字未动）

```verilog
// 旧（上一轮）：@(posedge load_active); #1; load_edges = 0;     ← 抹掉边界沿
// 新：在 DCLK 栅格上直接按半开区间 [load_active↑, load_active↓) 计数
always @(posedge dclk) if (reset_n) begin
    ...
    if      ( load_active && !la_e) win_e = 1;          // 窗口第一个采样沿
    else if ( load_active &&  la_e) win_e = win_e + 1;  // 内部沿
    else if (!load_active &&  la_e) win_e_last = win_e; // 关闭边界：不计
    la_e = load_active;
end
```

读值改成"等 2 个 DCLK 沿后取 `win_e_last`"，**没有任何清零语句**，因此不存在"清零与采样竞态"。

`git diff` 只动了 `tb/tcon_t1_tb.sv.txt`（+30/−3 行）；
`grep -c 'chk("'` 仍为 **55**，`27 / 17 / 11` 分布不变，**没有一行 `chk(` 被改动**（`git diff -U0 | grep chk(` 为空）。

### 1.1 离线自检（用上一轮失败的 VCD，覆盖两种相位）

```
 win    t0(ns)     t1(ns)   span_ns  start_edge?  published_count  ok
  0  11125      18805     7680     YES          384              OK
  2  33525      41205     7680     YES          384              OK
  3  43285      50965     7680     YES          384              OK
  4  63815      71495     7680     YES          384              OK
  6  98765      106445    7680     YES          384              OK
  8  123105     130785    7680     YES          384              OK
  9  132865     140545    7680     YES          384              OK
 10  142635     150315    7680     no           384              OK
 11  152395     160075    7680     no           384              OK
 12  162165     169845    7680     YES          384              OK     ← 上一轮失败的那一窗
full 7680 ns windows = 10 ; all exactly 384 = True
phase coverage: 8 of 10 full windows have the opening boundary on a DCLK edge
closing-boundary: 8 full windows have a DCLK edge exactly at t1 -> excluded by '!la && la_e'
```

**起点同刻、起点不同刻、终点同刻、终点不同刻四种情形都精确计 384**，这正是复审要求的离线验证。

---

## 2. 实际运行

```
SCEN=ALL  MIN_ASSERTS=55  VCD_LIMIT_MB=120  WALL_LIMIT_S=900
compile: Errors 0 / Warnings 0
assert_count=51   PASS=50   FAIL=1   → fail-fast，剩余 4 条未执行
Errors: 1（$fatal 产生）  Warnings: 0
VCD: 见 runner 日志（< 120 MB）
```

### 2.1 新通过的（含上一轮完全没跑到的）

| 断言 | 说明 |
|---|---|
| `T3_load_384_dclk_edges` | **本轮修复点**，PASS |
| `T3_load_starts_after_latch` | 上一轮未执行 |
| `T4_slot2_len_976_or_977` | 上一轮未执行 |
| `T5_slot3_len_976_or_977`、`T5_col_id_advancing` | 上一轮未执行 |
| `B1_first_slot_976_short_first` | 上一轮未执行 |
| `B2_first_frame_1024_slots` | 上一轮未执行 |
| `B3_first_frame_cycles_1e6` | 上一轮未执行 |
| `B4_first_frame_576_long` | 上一轮未执行 |
| `B5_first_frame_448_short` | 上一轮未执行 |
| `B6_frame_wrap_exactly_once` | 上一轮未执行 |

首帧实测行：`slots=1024 first_len=976 long=576 short=448 cycles=1000000 wraps=1 col1=0 col1025=1023`
——**1024 列、576 长槽、448 短槽、恰好 1,000,000 个参考周期、`frame_wrap` 恰好 1 次**，与 V1.3 要求一致。

### 2.2 失败的那一条

```
FAIL B7_col_id_period_1024_after_wrap  (t=10,217,270 ns)
col1=0   col1025=1023
```

**根因（VCD 实测，不是推断）**：`col_id` 在每个槽的**周期 828** 更新
（`tcon_top` 的 `latch_evt = slot_cycle == 827`，寄存器在下一拍生效）。
VCD 实测更新点：`col_id->1 @ 12,575 ns`、`col_id->2 @ 22,345 ns`…，都落在 `slot_start + 828 拍`。

因此在**槽 K 的周期 0** 读到的 `col_id` 是**槽 K-1 在 828 写入的值**，即列 `K-2`：

* 槽 1 的周期 0：还没有任何标签 → 复位默认 **0**；
* 槽 1025 的周期 0：列 `1025-2 = 1023` → **1023**。

两者本来就不该相等——是我把比较点选错了相位，不是 `col_id` 没有周期 1024。
**判据本身（"过一帧后回到同一相位点"）没被放宽，是取样点差了一个槽。**

### 2.3 4 条完全没跑

`B8_no_tick_in_blank_frame`、`B9_no_latch_outside_blank_frame`、
`B10_no_stb_outside_blank_frame`、`B0_no_unblank_before_precharge`。
→ **整帧范围内的"无 tick / 无 LATCH / 无选通在 BLANK 外"以及"预充前不撤 BLANK"仍然没有证据。**

---

## 3. 建议（未执行，等你裁定）

| 方案 | 内容 | 代价 |
|---|---|---|
| **A（建议）** | 只改 `B7` 的**取样相位**：把比较点从"槽 1 vs 槽 1025"改成"槽 2 vs 槽 1026"（两者都在 `slot_start`、都在同一相位点），判据仍是"相隔 1024 槽后相等" | 1 次 ModelSim |
| A′ | 或者把取样点挪到 `SCAN_STB`（那里 `col_id` 恰好是 `K-1`，槽 1 与槽 1025 都是 0） | 同上 |
| B | 判据改成"允许差 1" | **不建议**，等于放宽判据 |
| C | 保持 FAIL，登记为"已知测量相位缺陷" | 0 次仿真，但 T1 永远停 FAIL |

我倾向 **A**：一行索引改动（`slots==2` / 多等一个槽边界），判据不动。
但要提醒：`B8/B9/B10/B0` 仍未跑过，**下一轮仍可能冒出新的失败**——这次 `B1`–`B6` 一次通过的先例说明它们大概能过，但我不敢保证。

---

## 4. 本轮做了什么 / 证实了什么 / 没证实什么

**做了**：只改 `tcon_t1_tb.sv.txt` 里的 DCLK 沿计数实现（+30/−3 行），跑 1 次 `SCEN=ALL`。

**证实了**（原生 transcript）：39→50 条 PASS；DCLK 每窗 384 沿的判定在真实运行中成立；
首帧 1024 槽 / 576+448 / 1,000,000 拍 / 一次回绕全部成立；启动安全、故障锁存、时基相位全部保持。

**没证实**：`col_id` 的帧周期（`B7` 取样点错）；`B8/B9/B10/B0` 未执行；
`latch_cnt` 仍是预测不是反馈；STA/CDC/SPI/384-512 通道电气实现/T3-T5 未做。

---

## 5. 裁定

| 项目 | 状态 |
|---|---|
| `T1_V13_SCEN_ALL` | **FAIL**（51 执行 / 50 PASS / 1 FAIL；4 条未执行） |
| `T3_load_384_dclk_edges` | **PASS**（本轮修复，离线自检 10/10 窗 384） |
| `B7_col_id_period_1024_after_wrap` | `TB_SAMPLING_PHASE_DEFECT`（判据未放宽，取样点差一个槽） |
| 首帧 1024 槽（`B1`–`B6`） | **PASS**（上一轮从未执行的整组） |
| `T1_V13_CONTRACT` | **`FAIL — NOT COMPLETE`** |
| 终态 | `WAITING_FOR_T1_V13_INDEPENDENT_REVIEW` |
