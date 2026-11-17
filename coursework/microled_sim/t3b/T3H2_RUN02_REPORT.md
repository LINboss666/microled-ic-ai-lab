# T3-H2 RUN02 报告 —— COMMIT 观测修正 + 故障挂起验收（**91/91 PASS**）

日期 2026-11-17 ｜ 终态 `WAITING_FOR_T3H2_RUN02_INDEPENDENT_REVIEW`
裁定：**`T3_H2_RUN02 = PASS 91/91`**；`T3_H2_RUN02_BUDGET = 1_USED_OF_1`（复审另行批准的限定 1 次）。
`rtl/data_driver.v.txt` **未改动**（`6d0c5f83…`，与任务书 C.1 要求一致）；**只有 TB 变了**。

---

## 1. 结果

```
COURSE_RTL_ASSERT_COUNT=91  PASS=91  FAIL=0  RESULT=PASS
T6 1/1/1/1/1   RUNNER_EXIT=0   vlog 0 errors / 0 warnings   （vsim 2 s）
T3_WINDOW_CENSUS opened384=27 closed384=26 counted=26 min=384 max=384 dropped=1
```

RUN01 的 4 条失败全部转为 PASS，且都是**改了观测方式、不是放宽判据**。

## 2. 两处观测器重写（任务书 B1/B2）

**旧**：`if (lut_valid && !lut_valid_q) commit_count++` —— 第二次换表是 `lut_valid 1→1`，永远看不见；
且捕获发生在活动区，读的是 NBA 之前的值，晚一个沿。

**新**（`always @(posedge dclk)`）：

```verilog
pre_bank = lut_bank; pre_lt = latch_obs; pre_ltd = dut.latch_d;
pre_armed = dut.armed; pre_wcnt = dut.wcnt;      // 沿前值（活动区）
#1;                                              // 不用 #0，等 NBA 真的落地
post_bank = lut_bank;
if (reset_n && (post_bank !== pre_bank)) begin   // 银行真的翻了吗
    commit_events++;
    last_pre_ok = (pre_lt && !pre_ltd && pre_armed && pre_wcnt == 384);
    last_post_colv = {col_valid0, col_valid};
    last_both_bank_same = (lut_bank === lut_bank0);
end
```

`D62` 现在要求四件事同时成立：`commit_events` 增加、**PRE 满足合法 LATCH 提交条件**、
**POST 两片 `col_valid` 均为 0**、**两片 bank 一致**。不再是"看下一拍无效"。
`commit_count` 这个名字已从源码删除（静态门会检查）。

## 3. 故障挂起：从"可能空洞"改成银行级证据（B3）

旧的 `D72` 只比 `commit_count == k0`，而该计数器本就看不见第二次提交 → **可能空洞通过**（复审裁定）。

新的 `D72` 在 FAULT 期间连续采 400 个 DCLK 沿，要求：

```
T3H2_FAULT_HOLD samples=400 bank_flip=0 pend_seen=1 events=3 on_viol=0
```

- `bank_flip=0`：故障期间活跃 LUT 银行**一次都没翻**；
- `pend_seen=1`：`cmt_pend` 确实被看到保持挂起；
- `events=3`：`commit_events` 与请求前相同；
- `on_viol=0`：期间两片输出恒 0。

释放后只等**银行翻转**（`wait_commit_events`），不再等 `lut_valid` 变高，也不再空等 4000 沿。

## 4. 从 COMMIT 到首次重载的全暗区间（B4）

新增连续监视器：COMMIT 翻转后立即开启，**只在"首次 `col_valid` 上升（合法重载）"时结束**，
期间每个 5 ns 采样点都要求 `col_valid=0`、`ch_en===0`（两片），并统计 BLANK 低电平样本数。

```
T3H2_DARK_A samples=974 blank_low=768 viol=0 done=1     （表 A 换表后）
T3H2_DARK_B samples=974 blank_low=768 viol=0 done=1     （表 B 换表后，故障路径）
```

974 个采样、其中 768 个落在 BLANK=0 的真实显示窗内、0 次违规、都由合法重载结束 →
`D64/D65/D75/D76` 依据的是整段区间，而不是"某一拍的瞬间"。

## 5. 自定界模式的独立黄金比对（B5）

`dut0.din_valid` 仍硬接 `1'b0`。新增 **D79/D80**：连续两个显示窗，把 `dut0.raw_disp[0..383]`
逐项对比 TB 自己的 `exp_byte()`（**不是**与另一颗 DUT 比，避免"两颗一起错"），
索引 0 与 383 单独点名。**D81** 证明两个窗口分别落在 976 与 977 槽：

```
T3H2_MODE0_PHASES len0=976 len1=977
```

`D69` 仍在装载窗内（cyc∈[700,800)，此时 wcnt 尚未被 828 的 LATCH 清零）验证 `wcnt==384`、`ovf==0`。

## 6. 断言清单

- 历史 69 条（T3 + T3-H）**全部 PASS**，名称与阈值一字未改；
- T3-H2 原有 18 条（D60–D78）全部保留并通过；
- 本轮新增 3 条（D79/D80/D81），**总数 91**，`MIN_ASSERTS=91`。

## 7. 零仿真硬门（运行前，全部通过）

| 项 | 结果 |
|---|---|
| 四个运行时 SHA | `data_driver 6d0c5f83…`、`data_model 60491535…`、runner `cfe602dc…`、LUT `e3e39b43…` 全部与要求一致 |
| TB diff | 只改观测器/P8 等待/暗区监视/模式 0 黄金比对（见 `diff/`） |
| 静态门 `t3h2_run02_precheck.py` | `T3H2_RUN02_PRECHECK_OK` |
| 旧门 `t3_precheck.py` | `PRECHECK_OK`（26 个 dclk 域变量、**0 双写者**） |
| 负控 1 | `[0,1,1]/[0,1,0]` → 旧计数器得 1、bank 翻转得 2（证明旧口径必漏） |
| 负控 2 | 去掉 `last_post_colv===2'b00` 后该判据不再可验收（门会拒） |
| 负控 3 | `D72` 不是裸计数快照（必须同时有 bank/pending/输出三项） |
| 编译 | vlog 0 错 0 警 |

## 8. 边界（不因本轮 PASS 解锁的东西）

- 本次仍是**单颗 Data 的单元级**证据；五芯片联合仿真（T5）**未授权、未运行**。
- 模拟恒流阵列、512 路高侧、综合/STA/CDC/PVT/光学标定：均未做。
- LUT 表仍是"理想示例映射"，非光学标定；Pure 8-bit PWM 与 PAM_CFG=01 仍 OPEN。
- 故障恢复语义仍是 `DERIVED_GATE_NOT_LATCH`（释放后旧锁存列可恢复），系统级锁存需 TCON 合同收口。
