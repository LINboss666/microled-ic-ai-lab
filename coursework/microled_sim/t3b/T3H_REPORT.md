# T3-H 报告 —— LUT 有效输出门控（唯一一次正式仿真）

日期 2026-11-17 ｜ 终态 `WAITING_FOR_T3_H_INDEPENDENT_REVIEW`
裁定：**`T3_H = PASS 69/69`**；`T3_H_SIM_BUDGET = 1_USED_OF_1`（预算用尽，无第二次）。

---

## 1. 一行修复（RTL 唯一功能变更）

```verilog
- wire hw_en = disp_ok && !blank && fault_n;
+ wire lut_ok = (!cfg_hybrid) || lut_valid;
+ wire hw_en  = disp_ok && lut_ok && !blank && fault_n;
```

`data_driver.v`：`896a3c54…1f5e` → **`4ea897de…11c8be`**（除该行外只有注释）。
无新增寄存器、无新时钟域、无时序路径变化；`reset / blank / fault_n` 仍是同一组合 AND 上的最高优先项。
`data_model`、`run_tcon_t3.sh`、LUT 码表 **未改**（SHA 与 RUN05 一致）。

## 2. 正式运行（唯一一次，vsim 9 s，仿真到 214,620 ns）

| 项 | 原生值 |
|---|---|
| 断言 | `ASSERT_COUNT=69`，`PASS=69`，`FAIL=0`，无重名（原 52 + 新 17） |
| 结果 | `COURSE_RTL_RESULT=PASS`，T6 五条件 `1/1/1/1/1`，`RUNNER_EXIT=0` |
| 编译 | vlog 0 errors / 0 warnings |
| 运行时 TB SHA | `de6fc35b…c34db`（与仓库逐字节一致，**未在跑后改 TB**） |

## 3. 三个定向场景的实际结果

**B1（P0 主用例）——未提交 LUT + 完整非零列**

```
T3H_B1_SAMPLES n=350 violations=0
D43 lut_invalid_after_reset            PASS   lut_valid===0
D44 complete_column_without_lut        PASS   col_valid===1 && lut_valid===0
D45 raw_payload_nonzero                PASS   载荷确实非零
D46 ch_en_exactly_zero                 PASS   350 个 DCLK 上升沿全部 ch_en === 384'b0（四态）
D47 samples_not_vacuous                PASS   350 > 300
```

`ch_en` 用四态精确比较：X 与 1 一样算违规。负控（静态推导，未额外耗仿真）：
复位后 active bank A 从未被写过 → `lut_a[*]=X` → `w_eff=X`；**修复前** `hw_en=1` 时
`ch_en = 1 && X && X = X` → `X !== 0` → D46 必失败；**修复后** `hw_en=0` 使 `0 && X = 0`
（Verilog 与门对 0 短路，与 X 无关）→ 精确 0。即"修不修"在 B1 上必然可分辨，不是 X 侥幸。

**B2 —— 真实 256 项 COMMIT + 重新装载**

```
D48 lut_committed                      PASS   lut_valid===1
D49 reloaded_column_valid              PASS   col_valid===1（重新装载，而非沿用旧 bank）
D50 map_matches_lut                    PASS   384 项 map_disp==lut_tab[raw_disp]
D51 pam_matches_lut                    PASS   384 路 PAM 档位一致
D52 on_time_matches_lut                PASS   384 路导通时间==LUT 有效宽度
D53 conduction_nonzero                 PASS   sum(on_cnt)>0（不是"全关也 PASS"）
D54 full_code_64_ticks                 PASS   满码 64 tick
```

**B3 —— 安全优先级未被新门控破坏**

```
D55 blank_kills_at_rising_edge         PASS   BLANK 自然上升沿 1 ns 后全关，违规 0
D56 display_active                     PASS   有效 LUT 下确实导通（|ch_en===1）
D57 fault_kills_active                 PASS   FAULT 1 ns 内全关
D58 fault_release_recovers             PASS   释放后恢复（DERIVED_GATE_NOT_LATCH 默认）
D59 reset_kills_active                 PASS   复位 1 ns 内全关
```

## 4. 原 52 条回归未退化

`PASS` 行中非 D43–D59 的条目 = **52**（含 D11–D15 三列各一次 = 15 行），名称与阈值一字未改。
`D42` 窗口普查：`opened384=15 closed384=14 counted=14 min=384 max=384 dropped=1`
—— 守恒式 `15=14+1` 成立；新增的 6 个 T3-H 窗口全部正常关闭，**没有多出第 2 个 dropped**
（设计上刻意在 cyc 700 / 640 收尾，避开 832 的新窗口起点）。

## 5. 运行前预检（零仿真）

- 编译预检：vlog 0 错 0 警。
- `tools/t3_precheck.py` → `PRECHECK_OK`：F1/F2/F3 保持；TB dclk 域 16 个变量 **0 双写者**；无 TB 块驱动 DUT 引脚；69 条断言、原 52 名无缺失。
- 采样网格与两个"计划落在哪个槽"的算术核对（见 `T3H_PRECHECK.md` §7）：T3-H 的显示窗必须落在"装载槽 ≥1"的槽位上，否则载荷模式会取到初始化值 —— 这一点在预检阶段就修正了，没有靠仿真试错。

## 6. 范围与未决

- 本证据仅覆盖 **Hybrid 数字侧**：`cfg_hybrid` 在窗口内动态变更**未测**，登记为模式配置时序约束（只允许在 `blank=1` 且无装载时变更）。
- Pure 8-bit PWM（255→256 tick 位宽 / 30 ns tick）仍 OPEN；`PAM_CFG=01` 仍 OPEN。
- 模拟恒流阵列、综合/STA/CDC、PVT/光学标定 —— 均未做。
- `T5` 未启动、未授权。
