# IDLE 状态的 BLANK 契约冲突（已登记，**未修复**）

**状态** `REGISTERED / NOT_COMPLIANT` ｜ 任务书 `TCON-T2B-BR` A.6
**结论先写清楚：当前 `tcon_top` 在 IDLE 状态下允许 BLANK 为低，这与 V1.3 §上电时序冲突。本轮不修改，
也不声称已经合规；本节只登记冲突、给出最小修复方案与它对旧 T1 49 条的影响。**

---

## 1. 规格原文（V1.3 原件，SHA-256 `6b61e4ab…afaa`）

`v13_fulltext.txt` 段 **0810**（§9 上电与初始化）：

> 上电、配置、校准、缓存预充、正常同步有效后，方撤销 BLANK

即：**BLANK 撤销是有前提的**。在"没有合法帧 / 缓存尚未预充"之前，外部引脚层面应保持 BLANK 有效。

`v13_fulltext.txt` 段 **918**（§20 异常保护）进一步要求异常后"当前及后续列全关"，
直到恢复合法帧——这与 IDLE 的条件同向。

## 2. 当前实现

`rtl/tcon_top.v.txt`：

```verilog
assign blank = blank_seq || !safe || flt || (act && !disp_ok);
```

* `act` = FSM 处于 `ACTIVE`（已收到 VSYNC+COL_SYNC 同沿的合法帧头）；
* 在 `IDLE`（`!act`）时最后一项被短路，于是 `blank = blank_seq`，
  即 **BLANK 在每槽的 [0,768) 周期为低**，与 `ACTIVE` 时完全一样；
* 同一状态下 `latch / pwm_start / scan_stb / pwm_tick` 的门控也是 `(!act || …)`，即 IDLE 下**不校验显示许可**。

后果：**"还没有合法视频帧"与"外部已经获得显示许可"之间的隔离并不完整。**
实际 LED 是否真的会亮，取决于 Data 侧有没有数据（当前模型在 IDLE 下没有提交过 bank，输出为全零），
但这属于"碰巧安全"，不是被 RTL 保证的安全。**不能把它描述成"外部安全熄屏"。**

`FAULT_RECOVERY_FSM.md` §4 当时是有意保留这个行为的：为了不推翻 T1 的时序骨架演示。
这正是复审指出的问题——**不能为了维持旧 49 条通过而默许未同步时的外部发光许可**。

## 3. 最小修复方案（本轮不实施）

```verilog
assign blank = blank_seq || !safe || flt || !act || (act && !disp_ok);
```

一行改动，语义变成"IDLE 恒熄屏"。若要保留"预充/校准完成"这一条件，可再加一个显式准入位：

```verilog
reg precharge_done;   // 由 SPI 配置区写入，本轮 SPI 未实现
assign blank = blank_seq || !safe || flt || !(act && precharge_done) || (act && !disp_ok);
```

第二种更贴 V1.3，但需要 SPI 寄存器（`NOT_IMPLEMENTED`），本轮不具备条件。

## 4. 影响面：会打破哪几条旧 T1 断言

在隔离副本上做的**静态推演**（未跑仿真，本轮只有 1 次 ModelSim，#4 用于联合验证）：

| T1 断言 | 依赖的现状 | 加了 `!act` 之后 |
|---|---|---|
| `R4_ready_blank_low` | 配置就绪但**没有视频**时 blank 必须为低 | **FAIL**（这是 T1 的"骨架"前提本身） |
| `R6_recover_blank_low` | 故障清除、恢复后 blank 为低 | **FAIL**（同上） |
| `R6_no_tick_while_blanked` | 计数 `pwm_tick && blank` | **FAIL**：IDLE 下 tick 不再被 blank 门控，64 tick/槽 全部计入 |
| `T1_no_tick_in_blank` | 同上 | **FAIL** |
| `B8_no_tick_in_blank_frame` | 同上 | **FAIL** |
| `T3_load_starts_at_832` / `T3_load_384_dclk_edges` | 依赖 IDLE 下 `load_active` 照常运行 | 需要逐条复核（`load_active` 不受 blank 门控，预计仍 PASS） |

即：**至少 5 条会从 PASS 变 FAIL**，而且这 5 条验的正是"没有视频也能跑时基骨架"这个旧前提，
**不是** V1.3 的外部契约。

## 5. 处理方式（本轮的立场）

1. **不改 RTL**：改了就必然打破 T1 的 49 条，而 T1 的目标运行（#5）本轮未获授权；
   在只允许一次仿真的前提下，改完无法给出任何验证证据，只会把"未验证的改动"混进交付物。
2. **不写"已合规"**：报告、覆盖表、提交信息里一律写 `IDLE_BLANK = SPEC_CONFLICT_REGISTERED`。
3. **用可核对的计数把它留在证据里**：TB 每次运行都打印
   `T2B_IDLE_BLANK idle_blanklow_cycles=<N>`，其中 N 是"`blank==0` 且 FSM 不在 ACTIVE"的参考周期数。
   本轮 #4 的实测值见 `T2B_BR_REPORT.md`；它可以直接被复审方核对。
4. **下一轮的正规做法**（建议写进 #5 的授权）：
   * 先加 `!act` 项；
   * 把 T1 的 `R4/R6` 改成"**新契约断言**"：`blank` 只在 `ACTIVE && disp_ok` 时才允许为低；
   * 保留旧版断言名与旧的期望值作为 `LEGACY_SKELETON` 场景（单独一个 SCEN），
     使"旧 49 条"与"V1.3 外部契约"两个口径**同时在册、互不覆盖**；
   * 再跑 #5。

## 6. 一句话

IDLE 的 BLANK 现在是"碰巧安全"，不是"被保证安全"。这一条**没有关闭**，
在 `VIDEO_INPUT_SPEC_COVERAGE.md` 中记为 `CONFLICT_REGISTERED`，不计入任何 PASS。
