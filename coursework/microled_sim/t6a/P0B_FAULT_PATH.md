# 故障路径逐网表（P0B_FAULT_PATH）

日期：2026-11-19　范围：从外部开漏 `FAULT_n` 到最终 BLANK 引脚与 Data/Scan 门控
依据：V1.3 §12/§13/§20 原文；`tcon_top.v.txt`（T5 已验收）；候选 `tcon_spi_top`/`tcon_spi_regs`
状态：**零仿真**。本表只陈述"哪根线在哪、什么极性、有没有连"，不替代仿真或 STA。

---

## 1. 逐网表

| # | 节点 | 位置 | 极性 | 已连接？ | 当前测试依据 |
|---|---|---|---|---|---|
| N1 | `FAULT_n`（引脚） | `tcon_top.fault_n`；候选 `tcon_spi_top.fault_n` | **低有效**，开漏线与 + 外部上拉（段0494–0496） | ✅ 两处都有端口 | T5 56/56 用 `tcon_top`；L1 尚无（见 §4） |
| N2 | `hw_fault[10:0]`（片内比较器） | `tcon_spi_regs.hw_fault` | 高有效，逐位对应 UVLO/OV/OT/…（段0704） | ✅ | T6-A RUN02（D55/D56 等） |
| N3 | `hw_fault_i[10:0]` | 候选 `tcon_spi_top`：`hw_fault \| (fault_n ? 0 : 11'h080)` | 把引脚折进 **bit7 = COMM_TO** | ✅ 候选新增 | ❌ 无（0 vsim） |
| N4 | `any_hw_fault` | `tcon_spi_regs`：`\|hw_fault_i` | 高有效 | ✅ | 同上 |
| N5 | `hw_fault_caught` | `tcon_spi_regs` 异步置位/同步清除 | 高有效，粘滞 | ✅ 候选新增 | 状态模型（E17/E22） |
| N6 | `n_fault` → `fault_status` | 同块：`fault_status \| hw_fault \| err \| (caught?0x080:0)` | 高有效，W1C | ✅ 候选修订（本轮修复） | 状态模型（E17） |
| N7 | `INT_STATUS` | `n_int = int_status \| (n_fault & ~fs_d)` | 高有效，W1C | ✅ 因 N6 修订而同步 | 状态模型（E17b） |
| N8 | `fault_vis_o` | `fault_status \| hw_fault \| (caught?0x080:0)` | 观测用 | ✅ 候选修订 | — |
| N9 | `hw_blank` | `blank_r \| !en \| any_hw_fault \| caught \| !disp_armed \| disp_fault` | 高=关断 | ✅ | RUN02（D53–D56）+ 本轮模型 |
| N10 | **引脚 BLANK** | `tcon_top.blank = blank_seq \|\| !safe \|\| flt \|\| !act \|\| (act && !disp_ok)` | 高=关断 | ⚠️ **未与 N9 相连** | T5 56/56 |
| N11 | Data 关断 | `data_driver.hw_en = disp_ok && lut_ok && !blank && fault_n`（T3-H2） | 高=导通 | ✅ | T3-H2 91/91；T5 56/56 |
| N12 | Scan 关断 | `scan_driver`：`cs_n` 高时 512 位全 0 | — | ✅ | T4 42/42 |

**结论一**：N1→N2/N3 的**极性映射只有候选里有**；`course/…` 分支上 `tcon_spi_top` 连
`fault_n` 端口都没有。所以"芯片级短脉冲已捕获"这句话，**只有在候选分支 + 正确接线之后**才成立。

**结论二**：N9 与 N10 **至今没有连在一起**。引脚 BLANK 仍只由 `tcon_top` 决定。

---

## 2. 三条并行的关断路径（不要混为一谈）

```
                    ┌─(a) 组合：tcon_top.blank 里 !safe(=fault_n) → 当拍拉高
FAULT_n ──┬─────────┤
          │         └─(b) 采样：fault_evt → ST_FAULT（clk_ref 上升沿）← 短脉冲会丢
          │
          └─(c) 候选：hw_fault_i[7] → any_hw_fault → hw_fault_caught（异步置位）
                                     → hw_blank（组合 OR）
```

| 路径 | 延迟 | 短脉冲能否锁存 | 归属 |
|---|---|---|---|
| (a) 组合关断 | 门延迟 | ❌（脉冲一过就恢复） | `tcon_top` |
| (b) FSM 锁存 | 1 个 `clk_ref` 周期 | ❌ | `tcon_top` |
| (c) 异步捕获 | 异步置位延迟 | ✅（理想 RTL 级） | 候选 SPI 块 |

**(c) 存在不等于芯片安全**：只要 N10 不接 N9，(b) 仍是引脚 BLANK 的唯一锁存路径，
短脉冲在整颗芯片层面**照样会丢**。这是 L2 必须先解决的问题。

---

## 3. 极性 / 语义对照

| 信号 | 0 的含义 | 1 的含义 | 注意 |
|---|---|---|---|
| `FAULT_n`（引脚） | 有故障 | 正常 | 开漏，多个驱动源线与 |
| `hw_fault[i]` | 无 | 有 | 与引脚相反，**必须显式取反再合并** |
| `hw_fault_caught` | 未捕获过 | 捕获过（粘滞） | 只能由 W1C(bit7) 且无活故障时清 |
| `fault_status[7]` | 无 COMM_TO 事件 | 有 | 由 `caught` 派生，不是独立寄存器 |
| `hw_blank` / `blank` | 允许显示 | 关断 | 高有效，与 `FAULT_n` 相反 |

映射代码（候选 `tcon_spi_top`）：

```verilog
wire [10:0] hw_fault_i = hw_fault | (fault_n ? 11'd0 : 11'h080);
```

若集成时直接用 `fault_n` 而不取反，或把 bit 号搞错，捕获器就看不到故障 —— 这是 L2 的
第一个检查点。

---

## 4. 每层能证明什么、不能证明什么

| 层 | 环境 | 能证明 | 不能证明 |
|---|---|---|---|
| **L0 状态模型**（本轮） | python | 状态规则、W1C 语义、优先级、死时钟 | 任何 RTL 行为 |
| **L1 SPI 单元** | `tcon_spi_top` | 由 `fault_n` **端口**驱动的捕获、可读状态、清除协议、`hw_blank` | 引脚 BLANK、Data/Scan 导通 |
| **L2 五芯片** | TCON+2Data+2Scan（带 SPI） | 真实 `ch_en` 关断、重新预充、恢复显示 | — |

**本轮只做到 L0。** L1 连 TB 都还没有 `fault_n` 端口（RUN02 的 `tcon_t6a_tb` 没有这个脚，
加端口后必须重新 compile + 复验 57 条，属新预算）。

---

## 5. 集成时必须冻结的接线（提案）

```
blank_pin = tcon_top.blank  ||  hw_blank
hw_fault_i = hw_fault | (fault_n ? 0 : 11'h080)
hw_fault[i] 与 fault_status[i] 的位序必须一致（UVLO=0 … SYNC_ERR=10，ERR_REG=8 仅内部）
```

三条硬规则：

1. **R1** `hw_blank` 不得是唯一关断源（OR，不是选择）；
2. **R2** 引脚极性只在一处转换（`hw_fault_i`），其它地方一律高有效；
3. **R3** `tcon_top.ST_FAULT` 的退出条件要改成"Host 显式再使能 + 重新预充 + 合法帧"，
   否则段0912 的"Host 清除再使能"永远做不到。

---

## 6. 本轮未做的事

- 没有把 N9 接到 N10（属 T5 顶层，需另批）；
- 没有为 `fault_n` 加 TB 端口（L1 预算）；
- 没有做 CDC/STA：异步置位路径需要 recovery/removal 检查，`cs_n` 功能时钟需要约束；
- 没有声称任何物理最小脉宽 —— 那是工艺库 + 输入模拟电路的事。
