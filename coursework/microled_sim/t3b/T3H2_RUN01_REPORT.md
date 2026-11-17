# T3-H2 RUN01 报告 —— Data 自定界 + LUT 换表互锁（**失败即停**）

日期 2026-11-17 ｜ 终态 `WAITING_FOR_T3_H2_INDEPENDENT_REVIEW`
裁定：**`T3_H2_RUN01 = FAIL 84/88`**；`T3_H2_SIM_BUDGET = 1_USED_OF_1`（**无第二次，未追加**）。
TB 与 RTL 均保持运行时的字节状态，**跑后未做任何修补**（仓库 SHA == 运行时 SHA）。

---

## 1. 结果与失败项

```
COURSE_RTL_ASSERT_COUNT=88  PASS=84  FAIL=4  RESULT=FAIL
T6 0/1/0/0/1   RUNNER_EXIT=5   vlog 0 errors / 0 warnings
T3_WINDOW_CENSUS opened384=31 closed384=30 counted=30 min=384 max=384 dropped=1
```

| 失败项 | 时刻 | 直接原因 |
|---|---|---|
| `D62_commit_fires_on_latch_edge` | t=252,246,000（cyc 832, slot 3） | 我在 **832** 才捕获到 `ce_l=0 / ce_wcnt=1`，而 COMMIT 实际发生在 **828** |
| `D73_fault_release_fires_commit` | t=374,306,000（cyc 342, slot 16） | `commit_count` 没增加 |
| `D74_fault_commit_invalidates` | 同上 | 读到 `col_valid=1`（已被随后的重载恢复） |
| `D75_post_fault_window_dark` | t=374,605,000（cyc 371） | 该窗口已因重载而重新点亮 |

**69 条历史断言全部 PASS**（含 T3-H 的 D43–D59）。

## 2. 根因：两处 TB 观测器缺陷（RTL 无违约）

### 2.1 D62：观测器晚一个沿

监视器写在 `always @(posedge dclk)` 的活动区里：

```verilog
if (lut_valid && !lut_valid_q) begin ce_l = latch_obs; ce_wcnt = dut.wcnt; ... end
```

`lut_valid` 是 `lut_bank ? ok_b : ok_a` 的**组合读**，它在 COMMIT 那一拍的 NBA 区之后才变高；
而监视器的 `if` 在活动区执行、读到的仍是旧的 `lut_valid`。于是：
- **828**（COMMIT 真正发生、`latch=1`、`wcnt=384`、同沿还有一个合法 LATCH 提交）被漏掉；
- **832** 才检测到 0→1 跳变，但此时 `latch` 已回落为 0（LATCH 脉宽到 831）、`wcnt` 已被新窗口的 byte0 写成 1。

抓到的时刻 cyc=832 正是这个"晚一拍"的指纹。

**同沿失效本身是成功的**：`D63_commit_same_edge_clears_valid`（`col_valid===0 && col_valid0===0`）与
`D64_commit_without_reload_window_dark` 均 PASS —— 说明"COMMIT 与合法 LATCH 同沿时，
`col_valid` 最终为 0"这一优先级修复**按设计生效**。

### 2.2 D73/D74/D75：计数器只认 0→1，第二次换表不可见

`commit_count` 只在 `lut_valid` 的 **0→1** 跳变时自增。第一次 COMMIT（表 A）是 0→1 ✓；
第二次 COMMIT（表 B）时 `lut_valid` 已经是 1（两 bank 都提交过），**1→1 不被计数**。

因此 `wait_commit_count(k0+1, 4000)` 空等 80 µs（4000 个 DCLK）。而在这 80 µs 里：
COMMIT 确实在故障释放后的第一个安全沿发生 → `col_valid=0` → 下一列装载 → 下一拍 LATCH 提交 →
`col_valid` 又变 1。等到我检查时，D74/D75 看到的是"已经重新点亮的窗口"。

**COMMIT 确实发生了**，有三条独立证据：
1. `D76_post_fault_reload_reenables` PASS（`col_valid===1`）；
2. `D77_post_fault_conduction_nonzero` PASS（两片都真的导通）；
3. **`D78_display_follows_new_table_after_switch` PASS** —— 384 项 `map_disp == lut_b[...]`，
   即显示 bank 的内容来自 **表 B**。`lut_bank` 只有 COMMIT 能翻转，所以第二次 COMMIT 必然生效。

## 3. 本轮被证实的部分（84 条，含全部 P0 目标）

| 目标（任务书 §F） | 断言 | 结果 |
|---|---|---|
| `LEGACY_69_PASS` | 69 条历史 | ✅ 全过，名称/阈值一字未改 |
| `MODE0_BYTE0_383_PASS` | D70/D71 | ✅ `din_valid` 端口**接常量 1'b0** 时，两片 `raw_disp` 逐字节相同 |
| `EDGE385_IGNORED` | D69 | ✅ `wcnt==384 && ovf==0`（两片），多出的 DCLK 沿不写入 |
| `COMMIT_NO_RELOAD_DARK` | D63/D64 | ✅ 同沿 COMMIT 后 `col_valid=0`，随后窗口全暗 |
| `COMMIT_SAME_EDGE` | D63 | ✅ 同沿优先级（清 0）胜过 LATCH 分支的置 1 |
| `RELOAD_REENABLE_NONZERO` | D65–D67 | ✅ 换表后必须重新装载才恢复，且映射/导通与表一致 |
| `FAULT_PENDING_COMMIT` | D72 | ✅ 故障期间 COMMIT 挂起（不触发） |
| 换表后显示跟随新表 | D78 | ✅ 384 项与表 B 完全一致 |
| 自定界不影响历史 | 69 条 | ✅ 默认 `USE_DIN_VALID=1` 行为逐位不变 |

窗口普查 `31=30+1`、`min=max=384`：新增场景没有污染簿记。

## 4. 下一轮（若获授权）需要的**纯 TB** 修复

1. **提交沿观测**：把 `ce_l/ce_wcnt` 改为"在跳变被检测到的那一拍，使用**上一拍**登记的值"
   （`latch_q/wcnt_q` 打一拍），或改在 NBA 之后（`#0`/`#0.1`）采样。
2. **换表计数**：改为监视 `lut_bank` 翻转（`lut_bank !== lut_bank_q`），这样 0→1 与 1→0 都被计到。
3. **故障释放后的等待**：把 `wait_commit_count` 换成有界的 `wait_col_valid0`（等"变暗"而不是等计数），
   再连续检查"变暗 → 保持 → 重载后变亮"。

三处都只动 TB，**不动 RTL**；RTL 的两项修复（自定界、同沿优先级）已被本轮 84 条通过项支持，
但**按纪律不能据此自签 PASS**。

## 5. 锁源与纪律

| 文件 | 运行时 SHA |
|---|---|
| `rtl/data_driver.v.txt` | `6d0c5f831423e16c8d76bf583730d11a77d92fa35c203635b346ba678ba359ab` |
| `rtl/data_model.v.txt` | `604915355a79dfe5e0d8cc5aa4e9d14913d33c1962069ed394de21e71ef5506a` |
| `tb/tcon_t3_tb.sv.txt` | `9e5be3b6a217758406a4e6ffc0fa740a6a1caee5d9540143e0836a34d7e85b0d` |
| `tb/run_tcon_t3.sh` | `c1668f452297ae51b073fd088106c30791ee166b4ffe4573fd6ded5dcb07d9a3` |

仓库内两份文件与运行时**逐字节一致**（跑后未改）。TCON/Scan RTL 未动。
一次 vsim、一次编译预检；无 T5/Spectre/MC/OA/STA；未动 main、未开 PR、未自签 GO。

## 6. 同轮完成的 T5 侧修正（零仿真，独立于本次运行）

- 壳 `tb/t5_five_chip_shell.sv.txt`：**删除** 385 沿的 `dv_stub`；两颗 Data 改 `USE_DIN_VALID=0`
  且 `din_valid` 接常量 `1'b0`（与最终 wrapper 一致）；编译 0/0。
- `t5a/T5_SCOREBOARD_PLAN.md`：图样 P1 改为 **row0=列低8位、row1={列高2位,帧号}**（1024×64 单射，
  两 lane 各自可解）；明确"不得用 `ch_en` 单拍电平当字节，字节须由 `raw_disp` 观测或 PAM+整段
  on-time 反推"；S6 改为"故障锁存 → 持续全暗 → 显式复位+合法帧+重新预充后**再**验证恢复"。
- `t5a/T5_FIVE_CHIP_WIRING.md`：连线表随之更新。
- `tools/t5a_static_check.py`：删除 `or True`，改为可失败谓词 + **负控**（删掉端口后同一谓词必须 FAIL）。
