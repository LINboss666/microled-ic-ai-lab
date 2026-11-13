# TCON T1R 纠错报告（真实运行结果）

**任务号** `TCON-T1R-20261113` ｜ 分支 `course/microled-assignment-sim-20261112`
**基线 HEAD** `f06325b0d10fd64d8377c3531b73bbc3dc4c24f1`
**状态** `WAITING_FOR_T1R_INDEPENDENT_REVIEW`
**本轮 ModelSim** 授权 1 次，实跑 2 次（第 2 次经你批准追加）；Spectre / MC / OA = **0**

---

## 1. 修改文件（路径）

| 文件 | 改动性质 |
|---|---|
| `coursework/microled_sim/rtl/tcon_timebase.v.txt` | 时基：frac 初值、hold→run 重启、首帧精确 |
| `coursework/microled_sim/rtl/tcon_top.v.txt` | 装载窗改为相位锁定 + 组合安全门；新增共享时序常量 |
| `coursework/microled_sim/tb/tcon_t1_tb.sv.txt` | 重写：新增故障注入、DCLK 实测、首帧边界 |
| `coursework/microled_sim/tb/run_tcon_t1.sh` | MIN_ASSERTS 修正为 23/16/10/49 |
| `coursework/microled_sim/rtl/tcon_t1_edge_table.md` | 半开区间 [−144, 624) 与装载窗 [832,1600) |
| `coursework/microled_sim/checks/tcon_cycle_table.py` | 装载区间改为半开并加断言 |
| `coursework/microled_sim/results/execution_ledger.csv` | 追加第 31–32 行 |
| `coursework/microled_sim/results/t6_t1/*` | 本轮 transcript / 断言清单 / 离线 T6 检查输出 |

## 2. 修改前后差异（关键片段）

### 2.1 时基（`tcon_timebase.v`）

```verilog
// 前：frac 复位为 0 -> 第一帧只有 575 长槽（999,999 周期，少 10 ns）
frac <= 10'd0;
// 后：frac 复位为 FRAC_INIT=576 -> 第一帧 576 长 / 448 短 = 1,000,000
frac <= FRAC_INIT;
```

```verilog
// 前：hold 时 slot_cycle 停在 0，enable 上升后第一拍被"吃掉"，slot0 只有 975 拍
end else if (!enable) begin slot_cycle <= 11'd0; ...
// 后：enable 上升沿重启 cycle 0，slot0 恢复满 976 拍
end else if (!enable_d) begin
    slot_cycle <= 11'd0; slot_len <= BASE_LEN; slot_start <= 1'b1; ...
```

### 2.2 装载窗（`tcon_top.v`）

```verilog
// 前：靠 LATCH 下降沿检测 -> 晚一拍（833 起）且故障可产生假下降沿
latch_d <= latch;
if (latch_d && !latch) begin load_run <= 1'b1; load_cnt <= 10'd0; end
assign load_active = load_run;

// 后：相位锁定在 slot_cycle==831 的边沿进入 832；组合门控，故障 0 拍关闭
wire load_start_pt = (slot_cycle == (LOAD_START - 1));   // LOAD_START = 832
else if (!safe) begin load_run <= 1'b0; load_cnt <= 10'd0; end
else if (load_start_pt && !load_run) begin load_run <= 1'b1; load_cnt <= 10'd0; end
assign load_active = load_run && safe;
```

### 2.3 TB（`tcon_t1_tb.sv`）

| 前 | 后 |
|---|---|
| `dclk === 1'b0 \|\| dclk === 1'b1`（等于没测） | 200 拍内 99–101 个上升沿 + 周期实测 20 ns |
| 无装载窗实测 | `@(posedge load_active)` 起测：起始 cycle、768 拍、384 个 DCLK 沿 |
| 边界用 `frame_wrap` 收尾、会跳过首帧 | 复位后**第一次** enable 起数满 1024 槽，含首帧 |
| 无故障注入 | LATCH 脉冲中途故障、装载窗中途故障各 3–4 条断言 |

## 3. 第一帧周期计算

| 项 | 值 |
|---|---|
| 每帧槽数 | 1024 |
| 长槽 / 短槽 | 576 × 977 + 448 × 976 |
| 一帧周期数 | 562,752 + 437,248 = **1,000,000** |
| 时间 | 1,000,000 × 10 ns = **10.000000 ms**（100 Hz） |
| 首槽 | **976**（短槽优先保留） |
| frac 初值 | **576**（关键：0 会得到 575/449 = 999,999，少 10 ns） |
| 实测（ModelSim） | `slots=1024 first_len=976 long=576 short=448 cycles=1000000 wraps=1` ✅ |

## 4. load_active 起止周期

| 项 | 值 |
|---|---|
| LATCH | `[828, 832)` = 4 拍 = 40 ns |
| **load_active** | **`[832, 1600)` = 768 拍 = 7.68 µs**（半开区间） |
| 相对下一槽起点 | **[−144, 624)** |
| 与下一 LATCH（1804）的间隔 | 204 拍；扣 4 拍末数据保护 → **净 200 拍（2.00 µs）** |
| 故障行为 | `safe` 拉低时 `load_active` **0 拍关闭**，`load_cnt` 同步清零，不会产生假装载 |
| 实测 | `T3_load_starts_at_832` / `T3_load_len_768_cycles` / `T3_load_384_dclk_edges` 全 PASS |

## 5. DCLK 实测频率

| 项 | 实测 |
|---|---|
| 周期 | **20 ns**（`T2_dclk_period_20ns` PASS） |
| 频率 | **50 MHz**（100 MHz ÷ 2，每拍翻转） |
| 200 拍内上升沿 | 100（断言窗口 99–101，PASS） |
| 装载窗内上升沿 | **384**（768 拍 ÷ 2，PASS） |

## 6. 完整断言数量

| 场景 | 断言数 |
|---|---:|
| RESET_FAULT（含两处故障注入） | **23** |
| TIMEBASE（含 DCLK 与装载窗） | **16** |
| BOUNDARY（首帧） | **10** |
| **合计** | **49** |

> 说明：你预期 TIMEBASE 为 15 条，实际 **16** 条。多出的一条是 `T3_load_starts_after_latch`——
> 它把 828 与装载窗起点 832 的先后关系单独固定下来，避免以后改参数时两者脱钩。
> 全部 49 条在本轮第 2 次运行中 **49/49 PASS**。

## 7. ModelSim 真实运行结果

| # | 场景 | 结果 | 判定 |
|---|---|---|---|
| 1 | `SCEN=ALL`（授权第 1 次） | 32/49 后在 `T3_load_starts_at_832` fatal | rc=6（**失败件保留**：`t1r_run01_fail_T3_measure_vsim.txt`） |
| 2 | `SCEN=ALL`（你批准的第 2 次） | **49/49 PASS**，CHECK0–4 全 1，rc=0，耗时 **10 s** | PASS |

**第 1 次失败的根因（属 TB，不属 RTL）**：装载窗 `[832,1600)` 会跨到下一槽的第 624 拍，
所以 TB 在周期 200 时"等待 load_active 变高"直接命中了**上一槽**的窗。用该次运行留下的 VCD 反查：
第二个装载窗的起始偏移 **832.0 周期**，即 RTL 从一开始就是对的。改为 `@(posedge load_active)` 后通过。

第 1 次运行的 VCD（1,073,571 B）保留在仓库外 `native/t1r_run_single/`；第 2 次运行对完整帧**未写 VCD**。

## 8. 分支与 Commit

| 项 | 值 |
|---|---|
| 分支 | `course/microled-assignment-sim-20261112` |
| 基线 | `f06325b0d10fd64d8377c3531b73bbc3dc4c24f1` |
| 本轮 Commit | 见 §10（提交后回填）与 `review_manifest.json` |
| main | `23e471cb936b421ee97e1250c3be06edf96f9937`（未动） |

## 9. 尚未完成的设计内容

`NOT_IMPLEMENTED`：T2 的 768 B 列接收与 2×768 B ping-pong ｜ 奇偶分流 ｜ `D0/D1` 真实载荷（现恒 `8'h00`）
｜ SPI 寄存器 / 中断 / 时钟丢失检测 / CDC ｜ Data 384 路与 Scan 512 路 ｜ 电平搬移 ｜ 面板阵列
｜ 版图 ｜ PVT / SOA ｜ STA ｜ 光学标定 ｜ 整芯片。
本轮 T1R 只覆盖 **时基 + 安全时序骨架 + 装载窗窗口形状**，不代表 T2 或整芯片。

## 10. 提交与停闸

提交后本节由 `git log` 回填；停闸 `WAITING_FOR_T1R_INDEPENDENT_REVIEW`，未合并 main、未开 PR、未启动 T2。
