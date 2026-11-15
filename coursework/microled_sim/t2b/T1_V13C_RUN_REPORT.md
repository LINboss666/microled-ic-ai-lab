# T1 V1.3 第三次运行 —— `SCEN=ALL` 55/55 PASS

**任务** `TCON-T1-V13B-20261115` ｜ 基线 `886d023` ｜ 授权 ModelSim **1 次，用了 1 次** ｜ **无重试**

---

## 1. 一句话结论

上一轮 B7 的失败原因（**两个采样点相隔 1023 个槽边界，却断言 `period_1024`**）已按复审的精确索引改正；
本轮唯一一次 `SCEN=ALL` 跑完 **全部 55 条断言**：

```
COURSE_RTL_ASSERT_COUNT=55   PASS=55   FAIL=0   RESULT=PASS
CHECK0..4 = 1,1,1,1,1        RUNNER_VERDICT=PASS   RUNNER_EXIT=0
Errors 0  Warnings 0         编译 0 error 0 warning
```

`B8 / B9 / B10 / B0` **第一次被执行，且全部通过**——这四条在前两轮分别卡在 `T3` 和 `B7`，从未跑过。

---

## 2. 本轮改了什么（只有一处，且只动 TB）

| 项 | 上一轮 | 本轮 |
|---|---|---|
| 比较点 | 槽 2 起点 vs 槽 1025 起点（**相隔 1023**） | 槽 2 起点 vs **槽 1026** 起点（**相隔 1024**） |
| 额外核对 | 无 | 槽 1025 = **1023**、槽 1026 = **0** |
| 断言 | `col_at_slot1025 == col_at_slot1` | `(col_slot1026 == col_slot2) && (col_slot1025 == 1023) && (col_slot1026 == 0)` |
| 断言总数 / 分组 | 55 / 27-17-11 | **55 / 27-17-11（未变）** |
| `chk` 名称 | `B7_col_id_period_1024_after_wrap` | **同名，未改** |
| 判据 | — | **加严**（三条件合一），未放宽、未允许差 1 |

改动范围：`tb/tcon_t1_tb.sv.txt` **+35 / −9**；6 个 RTL、时钟、2 µs 复位、视频协议、T6 checker **均未改**
（RTL 与上一轮审计源逐字节一致，`tcon_top = 0f8e9169…`）。
TB 哈希 `f06c7d17… → fa40f186…`，唯一变化就是这段采样与断言。

### 为什么"iteration k 看到槽 k+1"

`slots` 记的是**已完成观察次数**，而循环体在等待之后才执行；进入循环时 TB 已在槽 0 周期 0 内，
所以第一个 `@(posedge slot_start)` 等来的是槽 1 起点。表在 `t2b/T1_V13B_SLOT_INDEX_TABLE.md`：

| `slots` | 观察到的边界 |
|---:|---|
| 0 | 槽 1 起点 |
| **1** | **槽 2 起点** ← `col_slot2` |
| 1023 | 槽 1024 起点 |
| 循环后 +1 | 槽 1025 起点 ← `col_slot1025` |
| 循环后 +2 | 槽 1026 起点 ← `col_slot1026` |

---

## 3. 离线静态检查（花预算之前做的）

`tools/t1_slot_index_check.py` 不跑仿真，直接读 TB 源码文本推导绝对槽号：

```
loop bound N = 1024 ; base condition slots == 1
post-loop waits to 1025 = 1 ; to 1026 = 2
derived: col_slot2 = slot 2, col_slot1025 = slot 1025, col_slot1026 = slot 1026
gap(col_slot1026 - col_slot2) = 1024 slot boundaries
RESULT: SLOT_INDEX_OK
```

**负控**：删掉"槽 1026 那次等待"，检查器立刻报
`gap = 1023 boundaries / the two compared samples are 1023 slot boundaries apart, not 1024 / SLOT_INDEX_BAD (rc=1)`
——它复现的正是上一轮那个缺陷，说明这个检查器不是恒真的。

---

## 4. 实测结果（native transcript，不是自述）

```
FIRST_FRAME slots=1024 first_len=976 long=576 short=448 cycles=1000000 wraps=1
FIRST_FRAME_COLID col_slot2=0 col_slot1025=1023 col_slot1026=0 (expect 0, 1023, 0)
```

三个值**与离线推导逐个吻合**，而且三者缺一不可：

- `col_slot1026 == col_slot2` → 相隔严格 1024 个边界的周期性；
- `col_slot1025 == 1023` → **防空洞**：若 `col_id` 一直是 0，这条就挂，B7 不可能靠"两边都是 0"过关；
- `col_slot1026 == 0` → 环绕点本身对（1023 之后回到 0）。

时基算术独立复核：`576 × 977 = 562,752`，`448 × 976 = 437,248`，合计 **1,000,000** —— 与 10 ms @ 100 MHz 一致。
仿真结束时间 `10,227,040 ns` ≈ 1024 槽 + 2 槽 + 收尾（`$finish` 在 TB 第 558 行）。

---

## 5. 四条首次执行的断言

| 断言 | 含义 | 结果 |
|---|---|---|
| `B8_no_tick_in_blank_frame` | 整帧内不出现 `PWM_TICK && BLANK` | PASS（`blk_viol == 0`） |
| `B9_no_latch_outside_blank_frame` | `LATCH` 只在 BLANK 内 | PASS（`latch_viol == 0`） |
| `B10_no_stb_outside_blank_frame` | `SCAN_STB` 只在 BLANK 内 | PASS（`stb_viol == 0`） |
| `B0_no_unblank_before_precharge` | 两次 LATCH 之前不得撤 BLANK | PASS（`early_unblank == 0`） |

这四条都是"计数 == 0"型断言，所以要交代**它们不是空洞的**：
同一轮里 `T1_ticks_64_per_window`（64 个 tick）与 `T1_latch_pulse_40ns`、`T1_scan_stb_offset_880` 都 PASS，
说明 tick / LATCH / SCAN_STB 三类脉冲在本轮**确实产生过**；`R4b_precharge_never_unblanks_early`
还要求 `latch_events ≥ 2`。监视器不是没接到信号才返回 0。

---

## 6. 与上一轮日志的衔接

| run | 结果 | 卡在哪 | 本轮 |
|---|---|---|---|
| T1-V13 #1 | 39 PASS / 1 FAIL，40 条后停 | `T3_load_384_dclk_edges`（TB 在窗口起点后 1 ns 清零，抹掉同刻沿） | 已修（DCLK 栅格半开区间计数），本轮 PASS |
| T1-V13 #2 | 50 PASS / 1 FAIL，51 条后停 | `B7`（相隔 1023 却断言 1024） | 已修（比到槽 1026），本轮 PASS |
| **T1-V13 #3（本轮）** | **55 PASS / 0 FAIL，全部执行** | — | — |

前两轮的原始 transcript、VCD、失败件都保留了，本轮没有删除或改写任何旧证据。

---

## 7. 本轮的边界：哪些**没有**做

- 没有改 RTL、时钟、复位、视频协议、T6 checker、断言数量或阈值；
- 没有重跑 T2B 联合验证（其结论 `T2B_JOINT_CONDITIONAL_PASS` 沿用，未因本轮改动而"变强"）；
- 没有做：SPI/寄存器、中断、`fault_n` 毛刺与 CDC、STA、384/512 通道电气阵列、T3/T4/T5；
- `T2B-C` 登记的那条限制仍然有效：**TCON 没有 Data 的真实反馈信号**，预充完成靠自身 LATCH 计数，
  实芯片若丢脉冲/时钟异常，单靠计数未必发现——本轮的 55/55 不覆盖这一点；
- 完整帧期间 VCD 仍被 `$dumpoff` 关闭（10 ms 全帧波形曾写出 8 GB），所以**整帧 `COL_ID` 序列没有逐槽 VCD 证据**，
  只有 RTL 推导 + 本轮三个采样点 + `T2B` 整帧 1026 次选通作旁证。这一点不当成"已从 VCD 逐列复核"。
