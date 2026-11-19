# 故障锁存 / 清除 / 再使能协议（FAULT_REARM_PROTOCOL）— rev2

日期：2026-11-19　状态：**候选提案**（只在独立分支试应用；`course/…` 分支 RTL 未改）

---

## 1. 规格要求（V1.3 原文，见 `SAFETY_OWNERSHIP.md` §1）

1. 故障出现 → 不等 SPI，当拍关断；
2. 故障消失 → **不自动点亮**；
3. Host 清除故障状态 → **仍不自动点亮**；
4. 只有「Host 显式再使能 + 帧合法 + 重新预充」同时成立，才允许恢复。

rev1 只回答了 2/3/4；**rev2 补上 1 的"任意窄脉冲"部分**（`ASYNC_FAULT_CAPTURE`）。

---

## 2. 状态量（v2）

| 名称 | 域 | 复位 | 含义 |
|---|---|---|---|
| `en` | core | 0 | 软件总使能（CTRL[0]） |
| `blank_r` | core | 1 | 软件 BLANK 请求（CTRL[1]） |
| `fault_status[10:0]` | core | 0 | 历史故障锁存（W1C，源未消失不可清） |
| `disp_armed` | core | **0** | Host 再使能许可 |
| `hw_fault_caught` | **异步置位 / core 清除** | **0** | 任意窄脉冲的故障捕获（新增） |
| `clr_fault` | core | 0 | 清除 `hw_fault_caught` 的单拍脉冲 |

---

## 3. 输出门（六个锁）

```
hw_blank = blank_r                      // 软件 BLANK
         | (!en)                        // 未使能
         | any_hw_fault                 // 当前活故障（组合，当拍）
         | hw_fault_caught              // 异步捕获的任意窄脉冲（粘滞）
         | (!disp_armed)                // Host 从未授权
         | disp_fault                   // 锁存的显示类故障（除 ERR_REG）
```

前四项决定"关得多快"，后两项决定"会不会自己亮回来"。

`disp_fault = |(fault_status & 11'h7FF & ~11'h100)`：`ERR_REG`（bit8）是寄存器访问错误，
不熄屏 —— 一次地址写错不应该黑屏。

---

## 4. 异步捕获块

```verilog
always @(posedge clk or posedge any_hw_fault or negedge reset_n) begin
    if (!reset_n)          hw_fault_caught <= 1'b0;
    else if (any_hw_fault) hw_fault_caught <= 1'b1;   // 置位 = 故障边沿，不需要时钟
    else if (clr_fault)    hw_fault_caught <= 1'b0;   // 清除 = 时钟沿
end
```

- **置位优先**：`any_hw_fault` 仍为 1 时，`clr_fault` 无效（段0600「故障未消失不可清」）；
- **时钟死掉也不能清**：clear 只在 `posedge clk` 评估（段0915）；
- **复位最高**：`!reset_n` 异步清 0，上电不发光（段0903）。

`clr_fault` 的产生：

```
clr_fault <= wr_cap_o && (wa[5:2] == A_FAULT) && (n_fault == 0) && !any_hw_fault
```

即"一笔 FAULT 的 W1C，清完之后一位都不剩，且当前无活故障"。
只要还有一位没清，capture 保持 → 满足"逐位区分历史故障"。

---

## 5. `disp_armed` 的置位 / 清零

| 事件 | 动作 | 时机 |
|---|---|---|
| CTRL 写 `EN=1,BLANK=0` 且 `SAFE && READY && !any_hw_fault && !hw_fault_caught && !disp_fault` | 置 1 | 同一 core 沿 |
| 同一写的其它条件不满足 | 整笔拒绝（`ERR_REG`），保持 0 | 同上 |
| 任意 `any_hw_fault` / `hw_fault_caught` / `disp_fault` | 清 0 | 每个 core 沿（块末，压过置位） |
| 写 `EN=0` 或 `BLANK=1` | 清 0 | CTRL 写 |
| `!reset_n` | 清 0 | 异步 |

---

## 6. 单沿状态矩阵（NBA 语义，24 组，`EDGE_MATRIX_CONTROL.csv`）

RTL 里 `fault_status` 是寄存器，块内所有组合判断读的都是**沿之前**的值，非阻塞赋值在块末才生效。
下表按这个顺序算出（`blank_old` = 沿前用旧寄存器算的 `hw_blank`；
`blank_new` = 沿后用新寄存器、**仍给同样的 hw_fault 输入**算的值）。

| start | ctrl | w1c | hw_fault | blank_old | blank_new | 拒绝 | 新状态 |
|---|---|---|---:|---:|---:|---:|---|
| ARMED | – | 0x000 | 0x000 | 0 | 0 | 0 | en=1 blk=0 armed=1 caught=0 |
| ARMED | – | 0x000 | 0x008 | 1 | 1 | 0 | armed=0 caught=1 fault=0x008 |
| ARMED | 0x1 | 0x000 | 0x008 | 1 | 1 | **1** | armed=0 caught=1 fault=0x108（ERR_REG） |
| ARMED | 0x3 | 0x000 | 0x000 | 0 | 1 | 0 | blk=1 armed=0 |
| DARK | – | 0x001 | 0x000 | 1 | 1 | 0 | **armed=0 caught=0**（清干净也不亮） |
| DARK | 0x1 | 0x001 | 0x000 | 1 | 1 | **1** | armed=0 caught=1 fault=0x100 |
| CLEARED | – | 0x001 | 0x000 | 1 | 1 | 0 | armed=0（清状态不自动恢复） |
| CLEARED | 0x1 | 0x000 | 0x000 | 1 | **0** | 0 | armed=1 ← 唯一允许恢复的入口 |
| CLEARED | 0x1 | 0x000 | 0x008 | 1 | 1 | **1** | armed=0 caught=1 fault=0x108 |

三条必须成立的结论（脚本里逐条断言）：

1. **live fault + unblank 一律被拒**，且不会留下 `armed=1`；
2. **DARK / CLEARED 状态下，没有任何纯 W1C 组合能让 `blank` 从 1 变 0**；
3. 只有 `CLEARED + ctrl=0x1 + 无故障` 这一种组合能让 `blank` 1→0。

---

## 7. 与 v1 的差别（重要）

| 项 | v1 | v2 |
|---|---|---|
| 故障捕获 | 只在 core 沿 | **异步置位 / 同步清除** |
| 4 ns 脉冲 | 丢失（`disp_armed` 没被清掉，`fault_status` 没置位） | 捕获并保持 |
| 模型 | 在判准入前先更新 `fault_status`（**不符合 RTL**） | 严格 NBA：旧值算组合、块末提交 |
| 状态表 | 无 | 24 组单沿矩阵，可直接对照 RTL |

v1 的原件保留在 `t6a/_rev1_20261119/` 与 `tools/t6a_p0_rearm_check_v1_archive.py`，便于对照。

---

## 8. 边界与未完成

| 项 | 状态 |
|---|---|
| RTL | 仅独立分支试应用；`course/…` 上四个已验收文件 SHA 未变 |
| 仿真 | ❌ 零 ModelSim（T6-A 预算 2/2 已用尽） |
| 57 条旧断言在新候选下的表现 | ❌ **未验证**，需要新预算 |
| 顶层 `ST_FAULT` 退出策略 | ⏸ 需在 T5 集成阶段按 R3 改，属新预算 |
| `cs_n` 功能时钟的 STA/CDC | ❌ 未做 |

**任何"P0 已关闭"的说法都必须等到新预算下的定向仿真 + 独立复审。**
