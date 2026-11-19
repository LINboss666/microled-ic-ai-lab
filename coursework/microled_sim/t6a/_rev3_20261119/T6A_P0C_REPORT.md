# T6-A P0-C：故障闭环整改（零 ModelSim）

日期：2026-11-19　预算：**本轮 0 次 vsim**
状态：`WAITING_FOR_P0B_REVISED_ZERO_SIM_ARCH_REVIEW`

---

## 1. 三条修正的落点

| 复审指出的问题 | 本轮处理 | 证据 |
|---|---|---|
| 抓住但读不到（`n_fault` 不含 `caught`） | 捕获位映射到 **COMM_TO(bit7)**，同时进 `fault_status`、`INT_STATUS`、`fault_vis_o` | `E17`、`FAULT_REARM_PROTOCOL.md` §2 |
| 零掩码 W1C 能清捕获位 | `clr_fault` 要求 `w1c_f[7]`；写 0 一位都不清，部分掩码只清被覆盖位 | `E18`/`E19` |
| 离线模型时间步进错误 | 改为**整数 ps 事件驱动**；11/20 ns 四相位全捕获成为硬门 | §3 |
| 模型源码未入包 | 三个 `.py` 全部放进 `tools/` | ZIP 清单 |
| CSV 行数虚报 | 行数由脚本统计数据生成 | §4 |
| `FAULT_n` 引脚未接入捕获 | 候选 `tcon_spi_top` 新增 `fault_n` 端口，折入 `hw_fault[7]` | `P0B_FAULT_PATH.md`、`E21` |

---

## 2. 可读性：短脉冲现在读得到

```
12 ns : blank=1 vis=0x081 caught=1     ← 脉冲期间（0x001 来自 hw_fault 本身）
16 ns : blank=1 vis=0x080 caught=1     ← 脉冲已过，只剩捕获位
20 ns : blank=1 vis=0x080 caught=1 int=0x080
```

`0x080` 就是 `COMM_TO`，依据 V1.3 段0704「TCON 捕获共享 `FAULT_n` 后置 COMM_TO」——
**没有新增地址**。Host 读 `0x0C` 得到 `0x0000_0080`，读 `0x10` 也有一位。

**限制（必须一起交）**：bit7 是"公共事件"位，只说明"捕获到过一次故障事件"，
**不说明是哪一路**。要逐路原因需要 11 个独立异步锁存（选项 B），本轮未做、未批准。

---

## 3. 清除协议：三个条件缺一不可

```verilog
clr_fault <= 1'b0;
if (wr_cap_o && (wa[5:2] == A_FAULT) && w1c_f[7] && !any_hw_fault)
    clr_fault <= 1'b1;
```

| Host 写 | 结果 | 用例 |
|---|---|---|
| `0x000` | 不清任何位，捕获保持 | E18 |
| `0x001` | 只清 UVLO，bit7 仍在 → 仍黑 | E19 |
| `0x080` | 无活故障时清捕获；`disp_armed` 仍 0 → 仍黑 | R1 |
| 同沿又来新脉冲 | 异步置位优先 → 保持 | E20 |

**不会死循环**：`fault_status[7]` 不是独立寄存器，而是 `caught` 的派生项；
W1C 掩码把 bit7 从 `n_fault` 去掉的同时 `caught` 也清，二者同沿完成。

---

## 4. 离线模型：时间基准改成整数 ps

rev1/rev2 用 1 ns 网格 + `(t - phase) % 10 == 0` 判断时钟沿，phase=2.5/7.5 ns 时
**一个沿都不产生**，于是 8/9/10/11/20 ns 也被报成"没捕获"。这是时间步进的错。

rev3 改为事件驱动（只在脉冲起、脉冲止、core 沿三个时刻改状态），全部整数皮秒，
脉冲取半开区间 `[start, start+width)`，相位平移的是**脉冲起点**。

修正后的扫描（与审核方的独立复算一致）：

| 宽度 | fsm 采样命中相位 | async 保持关断 |
|---|---|---|
| 1 ns | 1/4 | 32/32 全部 |
| 2 ns | 1/4 | 同上 |
| 4 ns | 2/4 | 同上 |
| 8 ns | 3/4 | 同上 |
| 9 / 10 / 11 / 20 ns | **4/4** | 同上 |

**硬门**：`11 ns` 与 `20 ns` 在四个相位全部捕获（`> 一个周期必然含一个沿`）。
rev2 记录的 2/4 是错的，已在本轮更正并写进脚本断言。

CSV 行数（脚本自己统计，不是手填）：

| 文件 | 数据行 | 含表头 |
|---|---|---|
| `ASYNC_FAULT_TIMELINE.csv` | **81**（0..80 ns，1 ns 网格） | 82 |
| `EDGE_MATRIX_CONTROL.csv` | **36**（3 start × 3 ctrl × 2 w1c × 2 fault） | 37 |

---

## 5. 断言与负控

新增/修订：`E17`（短脉冲可读）、`E18`（W1C=0 不清）、`E19`（部分掩码）、
`E20`（同沿新脉冲）、`E21`（`fault_n` 真实极性）、`E22`（停钟保持），
外加 `R1/R2` 恢复实验（防止"永远黑屏也 PASS"）。

负控全部改绑到**状态位本身**，不再绑"清完之后必须黑屏"：

| 编号 | 注入 | 失败点 |
|---|---|---|
| NC-A | `caught` 不并入 `n_fault` | E17（读回 bit7=0） |
| NC-B | `clr_fault` 不看掩码 | E18（写 0 把 caught 清掉） |
| NC-C | 去掉异步捕获 | E22（停钟不保持） |

三个都在同一个模型里真实返回 FAIL，不靠外部硬编码 oracle。

---

## 6. 候选补丁

| 项 | 值 |
|---|---|
| 分支 | `t6a-p0-candidate-20261119`（commit `bbcb831`） |
| 规模 | `tcon_spi_regs` +65/−? 、`tcon_spi_top` +14/−?（合计 +71/−8 行） |
| 新增端口 | `tcon_spi_top.fault_n`（V1.3 §12 的开漏低有效引脚） |
| 编译 | `vlog` **0 errors / 0 warnings** |
| 应用 | `course/…` 分支**未应用**；`git apply --check` 通过 |

**重要**：RUN02 的 TB 没有 `.fault_n` 端口，**加了端口的候选与旧 TB 不能一起 elaborate**。
所以 57 条断言在新候选下**未复验**，这是 L1 预算内的第一件事。

---

## 7. 仍未完成

1. 无 ModelSim：全部结论来自状态模型；
2. `tcon_top` 的 `ST_FAULT` 仍只能靠复位退出（段0912 未实现）；
3. `hw_blank` 与引脚 `blank` 仍**没有连**（`P0B_FAULT_PATH.md` N9/N10）；
4. P1（`mb_lost`/`mb_badlen` 可读）未实施；
5. 逐路原因记录（11 个异步锁存）未做；
6. CDC/STA、物理最小脉宽：未做；
7. L2 环境不存在。

---

## 8. 终态

`WAITING_FOR_P0B_REVISED_ZERO_SIM_ARCH_REVIEW`。
T6-A 原预算 2/2 不变；T5 验收不变；不自签 `P0_CLOSED`。
