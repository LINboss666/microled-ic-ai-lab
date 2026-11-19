# 故障锁存 / 清除 / 再使能协议（FAULT_REARM_PROTOCOL）— rev3

日期：2026-11-19　状态：**候选提案**（只在独立分支 `t6a-p0-candidate-20261119` 应用）
rev3 修的是 rev2 复审指出的两个真缺口：**抓住了但读不到**、**零掩码能清**。

---

## 1. rev2 的两个缺口（复审证据）

| 缺口 | 现象 |
|---|---|
| 可读性 | 4 ns 脉冲 → `hw_fault_caught=1`、`hw_blank=1`，但 `fault_status=0`、`int_status=0`、`fault_vis_o=0`。Host 读 `0x0C` 得到 **0** —— 芯片黑了却没有任何记录 |
| 清除 | `clr_fault` 只看 `n_fault==0 && !any_hw_fault`，**不看 W1C 掩码**。写 `data=0` 也满足条件 → 下一沿把捕获位清掉 |

后果：显示安全（不会误亮）但**不可诊断、不可恢复**；且清除协议违背 W1C 语义。

---

## 2. rev3 的做法：捕获位 = COMM_TO（bit7）

V1.3 段0704 原文：「**TCON 捕获共享 `FAULT_n` 后置 COMM_TO**」。
所以"被捕获的共享故障事件"本来就有归属位，**不需要新增地址**。

```verilog
// tcon_spi_regs
n_fault = fault_status | hw_fault
        | (err_set ? 11'h100 : 11'd0)
        | (hw_fault_caught ? 11'h080 : 11'd0);   // ← rev3 新增
...
if (w1c_f != 11'd0) n_fault = n_fault & ~(w1c_f & ~hw_fault);
```

`FAULT_STATUS` 读 mux 本来就返回 `fault_status`，所以：
**短脉冲 → `fault_status[7]=1` → Host 读 0x0C 得到 0x080 → `int_status[7]=1`。**

`fault_vis_o` 同步加上这一项，避免"寄存器有、观测口没有"的不一致。

---

## 3. 清除协议（rev3 的核心修正）

```verilog
clr_fault <= 1'b0;
if (wr_cap_o && (wa[5:2] == A_FAULT) && w1c_f[7] && !any_hw_fault)
    clr_fault <= 1'b1;
```

四个条件缺一不可：

| 条件 | 作用 | 去掉会怎样 |
|---|---|---|
| `wr_cap_o` | 必须真的是一笔**被捕获的写帧** | 读事务也能清（P0-4 回归） |
| `wa == A_FAULT` | 必须是写 FAULT_STATUS | 写别的寄存器误清 |
| **`w1c_f[7]`** | **掩码必须覆盖 bit7** | `data=0` 或部分掩码就把捕获清掉（rev2 缺陷） |
| `!any_hw_fault` | 活着时不许清 | 段0600「故障未消失不可清」被违反 |

于是：

| Host 写 | 结果 |
|---|---|
| `data = 0x000` | `w1c_f=0` → **不清任何位**，捕获保持（E18） |
| `data = 0x001`（只清 UVLO） | 只清 bit0；bit7 仍在 → 仍黑（E19） |
| `data = 0x080` | 若当前无活故障 → 清捕获；`disp_armed` 仍为 0 → 仍黑（R1） |
| `data = 0x081` | 两个一起清 |
| 清除当拍又来一个新脉冲 | 异步置位**优先**（always 块里 set 先判）→ 捕获保持（E20） |

**为什么不会死循环**：`fault_status[7]` 不是独立寄存器，而是 `caught` 的派生项；
W1C 清 `caught` 的同时掩码也把 bit7 从 `n_fault` 里去掉，二者同沿完成，
不存在"清了又立刻被 caught 重新置起"的循环。

---

## 4. 优先级（从高到低）

```
1. reset_n 异步复位                              → caught=0, armed=0
2. 故障异步置位  posedge any_hw_fault            → caught=1（不等时钟）
3. 同步清除      clr_fault（需掩码 bit7 + 无活故障）→ caught=0
4. 硬件活故障    any_hw_fault                     → hw_blank=1（组合，当拍）
5. 软件 BLANK / EN=0                              → hw_blank=1
6. Host 再使能   disp_armed                       → 只有它为 1 且 1..5 全不成立才可能亮
```

第 2 条与第 3 条在同一个 always 块里，**set 在前**，所以同沿新故障永远赢。

---

## 5. `disp_armed` 不变（rev2 已评审通过）

置位：一次 CTRL 写，`EN=1,BLANK=0`，且 `SAFE && READY && !any_hw_fault &&
!hw_fault_caught && !disp_fault`。
清零：复位 / 活故障 / 捕获位 / 锁存显示故障 / `EN=0` / `BLANK=1`。

---

## 6. 单沿矩阵（36 组，`EDGE_MATRIX_CONTROL.csv`，数值由脚本生成）

| start | ctrl | w1c | hw_fault | blank_old | blank_new | 拒绝 | 新状态 |
|---|---|---|---:|---:|---:|---:|---|
| CLEARED | – | 0x000 | 0x000 | 1 | 1 | 0 | armed=0（清完不清许可） |
| CLEARED | – | 0x001 | 0x000 | 1 | 1 | 0 | armed=0（部分掩码不清捕获） |
| CLEARED | 0x1 | 0x001 | 0x000 | 1 | **0** | 0 | armed=1 ← 唯一恢复入口 |
| CLEARED | 0x1 | 0x001 | 0x008 | 1 | 1 | **1** | armed=0 caught=1 |
| DARK | – | 0x001 | 0x000 | 1 | 1 | 0 | 仍黑 |

（完整 36 组在 CSV 里，脚本自己统计行数。）

---

## 7. 已知限制（必须随方案一起交）

1. **bit7 是"公共事件"位**：它说明"捕获到过一次故障事件"，**不能说明是哪一路**。
   要逐路原因，需要 11 个独立的异步锁存（设计选项 B），代价是 11 条异步置位路径，
   本轮未做、也未批准。
2. **物理最小脉宽未定**：异步置位的可靠下限由标准单元的 async-set 宽度、
   输入缓冲和开漏 RC 决定；本轮只声明**理想 RTL 级**行为。
3. **`clr_fault` 是 core 域的**：停钟时无法清除（这是刻意的安全性质，但也意味着
   停钟后必须恢复时钟才能服务 Host）。
4. **未仿真**：以上全部是状态模型结论。

---

## 8. 与 rev2 的差异一览

| 项 | rev2 | rev3 |
|---|---|---|
| 短脉冲可读性 | ❌ 读 0 | ✅ 读 0x080（COMM_TO） |
| INT_STATUS | ❌ 不置 | ✅ 置 bit7 |
| `fault_vis_o` | ❌ 不含捕获 | ✅ 含 |
| 零掩码 W1C | ❌ 会清 | ✅ 不清 |
| 部分掩码 | ❌ 也会清 | ✅ 只清被覆盖的位 |
| 同沿新故障 | ⚠️ 未定义 | ✅ set 优先 |
| 引脚 `FAULT_n` | ❌ 未接 | ✅ `tcon_spi_top` 新增端口并折入 bit7 |
| 矩阵组数 | 声称 24，实际 36 | 36，脚本统计 |
