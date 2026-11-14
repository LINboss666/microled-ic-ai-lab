# 旧 T1 49 条 → V1.3 合约映射（T2B-C）

**旧文件**：`tb/tcon_t1_tb.sv.txt` @ `b02f824`（49 条，`SCEN=ALL` 曾 49/49 PASS）
**新文件**：`tb/tcon_t1_tb.sv.txt` @ 本轮（55 条，V1.3 合约）
**旧 transcript**：`D:/ic617_course_sim_20261112_native/t1_run_t2ar2/03_vsim.stdout`（T2AR2 轮）与 `b02f824` 前的各轮，全部保留，**不删、不改判据**。

> **明确声明**：新 T1 **不是**"原版旧 49 条原样重跑"。旧 TB 在**完全没有视频输入**的情况下要求
> `R4_ready_blank_low`（BLANK 必须为低）并据此测量 64 个 tick —— 这与 V1.3 §9 段0810
> 「配置/校准/预充/正常同步有效后，方撤销 BLANK」直接冲突。把这种期望当作生产验收的 PASS 条件，
> 等于承认"没有画面也可以点亮面板"。因此本轮把该期望**替换**为 V1.3 期望，并在下表中逐条标注。

---

## 1. 逐条映射（49 条旧断言）

| # | 旧断言 | 旧判据 | V1.3 下是否仍适用 | 新断言 | 变化说明 |
|---|---|---|---|---|---|
| 1 | `R1_reset_blank_high` | 复位时 BLANK=1 | 适用 | `R1_reset_blank_high` | 不变 |
| 2 | `R1_reset_col_id_0` | 复位时 COL_ID=0 | 适用 | `R1_reset_col_id_0` | 不变 |
| 3 | `R1_reset_no_latch` | 复位时无 LATCH | 适用 | `R1_reset_no_latch` | 不变（`!safe` 已足够）|
| 4 | `R1_reset_no_pwm_start` | 复位时无 PWM_START | 适用 | `R1_reset_no_pwm_start` | 不变 |
| 5 | `R1_reset_no_scan_stb` | 复位时无 SCAN_STB | 适用 | `R1_reset_no_scan_stb` | 不变 |
| 6 | `R1_reset_no_tick` | 复位时无 PWM_TICK | 适用 | `R1_reset_no_tick` | 不变 |
| 7 | `R1_reset_no_load` | 复位时无 load_active | 适用 | `R1_reset_no_load` | 不变 |
| 8 | `R2_unconfigured_blank_high` | 未配置 BLANK=1 | 适用 | `R2_unconfigured_blank_high` | 不变 |
| 9 | `R2_unconfigured_no_stb` | 未配置无 SCAN_STB | 适用 | `R2_unconfigured_no_stb` | 不变 |
| 10 | `R3_illegal_mode_blank_high` | 非法 cfg_mode BLANK=1 | 适用 | `R3_illegal_mode_blank_high` | 不变 |
| 11 | `R4_ready_blank_low` | **配置就绪且无视频时 BLANK 必须为低** | **不适用（与 §9 段0810 冲突）** | `R4_idle_no_video_blank_high` | **判据反转**：无合法帧时 BLANK 必须为高 |
| 12 | `R4_status_ready` | `status[0]`（safe）=1 | 适用 | `R4_status_ready` | 不变 |
| 13 | `R5b_fault_during_latch_blank` | LATCH 中故障 → BLANK=1 | 适用 | `R5b_fault_during_latch_blank` | 不变 |
| 14 | `R5b_fault_during_latch_no_latch` | 同刻 LATCH=0 | 适用 | `R5b_fault_during_latch_no_latch` | 不变 |
| 15 | `R5b_fault_during_latch_no_phantom_load` | 之后 load_active=0 | 适用 | `R5b_fault_during_latch_no_phantom_load` | 不变 |
| 16 | `R5c_load_running_before_fault` | 装载窗进行中 | 适用 | `R5c_load_running_before_fault` | **前置改为独立复位**（见 #19）|
| 17 | `R5c_fault_during_load_closes_load` | 故障当拍关窗 | 适用 | `R5c_fault_during_load_closes_load` | 不变 |
| 18 | `R5c_fault_clears_load_counter` | `load_cnt`=0 | 适用 | `R5c_fault_clears_load_counter` | 不变 |
| 19 | `R5c_fault_during_load_blank` | 故障时 BLANK=1 | 适用 | `R5c_fault_during_load_blank` | 不变 |
| 20 | `R6_recover_blank_low` | **恢复 `fault_n` 后 BLANK 变低（自动恢复）** | **不适用（Q3=B 锁存，只允许复位恢复）** | `R6_fault_latched_blank_high` | **判据反转**：恢复 `fault_n` 后 BLANK 仍为高 |
| 21 | `R5_fault_sticky_status` | `status[3]`（fault_seen）粘滞 | 适用 | `R5_fault_sticky_status` | 不变 |
| 22 | `R6_no_tick_while_blanked` | 没有 `tick && blank` | 适用 | `R6_no_tick_while_blanked` | 不变（更强：PWM_TICK 现在也受 permit 门控）|
| 23 | `R6_no_latch_outside_blank` | 没有 `latch && !blank` | 适用 | `R6_no_latch_outside_blank` | 不变 |
| 24 | `T1_slot_len_976_or_977` | 槽长 976/977 | 适用 | `T1_slot_len_976_or_977` | 测量改在 **ACTIVE** 槽 |
| 25 | `T1_ticks_64_per_window` | 窗口 64 tick | 适用 | `T1_ticks_64_per_window` | 需要 permit（否则 tick 被门控）|
| 26 | `T1_latch_offset_828` | LATCH 偏移 828 | 适用 | `T1_latch_offset_828` | 不变 |
| 27 | `T1_pwm_start_offset_840` | PWM_START 偏移 840 | 适用 | `T1_pwm_start_offset_840` | 不变 |
| 28 | `T1_scan_stb_offset_880` | SCAN_STB 偏移 880 | 适用 | `T1_scan_stb_offset_880` | 不变 |
| 29 | `T1_latch_pulse_40ns` | LATCH 4 拍 | 适用 | `T1_latch_pulse_40ns` | 不变 |
| 30 | `T1_no_tick_in_blank` | 无 `tick && blank` | 适用 | `T1_no_tick_in_blank` | 不变 |
| 31 | `T2_dclk_100_edges_per_200_cycles` | DCLK 连续性 | 适用 | `T2_dclk_100_edges_per_200_cycles` | 不变 |
| 32 | `T2_dclk_period_20ns` | 周期 20 ns | 适用 | `T2_dclk_period_20ns` | 不变 |
| 33 | `T3_load_starts_at_832` | 装载窗起点 832 | 适用 | `T3_load_starts_at_832` | 不变 |
| 34 | `T3_load_len_768_cycles` | 768 拍 | 适用 | `T3_load_len_768_cycles` | 不变 |
| 35 | `T3_load_384_dclk_edges` | 384 DCLK 沿 | 适用 | `T3_load_384_dclk_edges` | 不变 |
| 36 | `T3_load_starts_after_latch` | LATCH 在装载前 | 适用 | `T3_load_starts_after_latch` | 不变 |
| 37 | `T4_slot2_len_976_or_977` | 第 2 槽长 | 适用 | `T4_slot2_len_976_or_977` | 不变 |
| 38 | `T5_slot3_len_976_or_977` | 第 3 槽长 | 适用 | `T5_slot3_len_976_or_977` | 不变 |
| 39 | `T5_col_id_advancing` | `col_id >= 2` | 适用 | `T5_col_id_advancing` | ACTIVE 下由标签驱动，仍成立 |
| 40 | `B1_first_slot_976_short_first` | 首槽 976 | 适用 | `B1_first_slot_976_short_first` | 不变 |
| 41 | `B2_first_frame_1024_slots` | 1024 槽 | 适用 | `B2_first_frame_1024_slots` | 不变 |
| 42 | `B3_first_frame_cycles_1e6` | 1,000,000 拍 | 适用 | `B3_first_frame_cycles_1e6` | 不变 |
| 43 | `B4_first_frame_576_long` | 576 长槽 | 适用 | `B4_first_frame_576_long` | 不变 |
| 44 | `B5_first_frame_448_short` | 448 短槽 | 适用 | `B5_first_frame_448_short` | 不变 |
| 45 | `B6_frame_wrap_exactly_once` | 回绕 1 次 | 适用 | `B6_frame_wrap_exactly_once` | 不变 |
| 46 | `B7_col_id_period_1024` | **`col_id` 在 1024 槽后回到起点** | 判据不成立（ACTIVE 下 `col_id` 是显示标签，滞后 1 槽） | `B7_col_id_period_1024_after_wrap` | 改为在 slot 1025 与 slot 1 比较（同一滞后）|
| 47 | `B8_no_tick_in_blank_frame` | 全程无 `tick && blank` | 适用 | `B8_no_tick_in_blank_frame` | 不变 |
| 48 | `B9_no_latch_outside_blank_frame` | 全程无 `latch && !blank` | 适用 | `B9_no_latch_outside_blank_frame` | 不变 |
| 49 | `B10_no_stb_outside_blank_frame` | 全程无 `stb && !blank` | 适用 | `B10_no_stb_outside_blank_frame` | 不变 |

**替换掉的 3 条**：#11（R4）、#20（R6）、#46（B7）——每条都写明了原因，没有一条是"为了通过而放宽"。
其中 #11 与 #20 是**判据反转**（更严），#46 是**判据修正**（原判据在 ACTIVE 下无意义）。

---

## 2. 新增的 6 条（V1.3 启动安全合同）

| 新断言 | 判据 | 为什么必须加 |
|---|---|---|
| `R4_idle_no_video_no_strobe` | IDLE 时无 SCAN_STB / PWM_START | 只有 BLANK=1 不够：不能让外部看到"有选通但黑屏"的假动作 |
| `R4b_precharge_never_unblanks_early` | `early_unblank==0` 且 `latch_events>=2` | **T2B-BR 的 7,680 ns 违规就是这一条**：BLANK 不得在两级预充完成前撤销 |
| `R4c_blank_low_after_precharge` | 预充完成后 BLANK 会正常撤销 | 证明修的是"顺序"而不是"永远黑屏" |
| `R7_reset_reprecharge_blank_low` | 故障锁存后经复位 + 重新预充可恢复杂显示 | Q3=B 的恢复路径必须真的能恢复 |
| `T0_permit_before_measure` | 时序测量前必须已有显示许可 | 否则 64 tick / 840 / 880 是在"无许可"的槽里测的，无意义 |
| `B0_no_unblank_before_precharge` | 整帧扫描期间 `early_unblank==0` | 把启动合同延伸到 1024 槽 |

---

## 3. 计数

| 场景 | 旧 | 新 |
|---|---|---|
| `RESET_FAULT` | 23 | **27** |
| `TIMEBASE` | 16 | **17** |
| `BOUNDARY` | 10 | **11** |
| `ALL` | 49 | **55** |

门槛写在 `tb/scen_min_asserts.sh`（`RESET_FAULT 27 / TIMEBASE 17 / BOUNDARY 11 / ALL 55`），
由 `tb/test_scen_min_asserts.sh` 自测（10/10，纯 shell，不耗仿真预算）。

---

## 4. 旧证据怎么处理

* 旧 `tcon_t1_tb.sv` 与旧 transcript **保留在 git 历史与审核包里**，不删除、不改判据；
* 旧 `49/49 PASS` 仍然成立——但它成立的是**旧骨架**语义，不等于 V1.3 合规；
* 从本轮起，任何"T1 通过"的表述都必须写成「V1.3 合约 T1 55/55」并注明这是新合约回归。
