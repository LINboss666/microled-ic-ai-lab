# T6-A 故障捕获 / 清除 / 再使能协议（rev5，2026-11-19，P0-E — 合同冻结版）

> 历史：rev1（disp_armed 首案）→ rev2（NBA 语义修正）→ rev3（COMM_TO 映射 + W1C 掩码）
> → rev4（组合清除，P0-D）→ **rev5（本版）：故障源归属合同冻结 + 历史回归收口**。
> 各版全文见 `_rev1.._rev4/` 子目录。

## 1. 冻结的合同（C1–C6）

| 条款 | 内容 | 依据 |
|---|---|---|
| **C1** | 每一路故障源（共享 `FAULT_n` 引脚 + 本地 `hw_fault[10:0]`）各有一条**异步置位、同步清除**的捕获锁存。不依赖最小脉宽或源端锁存承诺。 | V1.3 段0492–0496（开漏/线与/低有效，规格未承诺脉宽）；P0-B 复审要求 |
| **C2** | **COMM_TO(bit7) 只代表共享 FAULT_n 事件**（引脚路径，极性在 `tcon_spi_top` 折叠一次）。本地 UVLO/OV/OT 的捕获进**各自的状态位**，不进 bit7。 | V1.3 段0704 原文：`TCON 捕获共享 FAULT_n 后置 COMM_TO` |
| **C3** | W1C 掩码位 k **同拍**清除 `status[k]` 与 `caught[k]`（组合清除请求）；活故障位不可清；零掩码一位不动；**无隐式跨位清除**（bit0/1/2 不清 bit7，反之亦然）。 | V1.3 段0599；P0-D 复审 |
| **C4** | 恢复 = 清除**全部**锁存原因（每位一次 W1C，可合并掩码）+ 显式 CTRL 再使能；清除本身不点亮；`disp_armed` 被任一活/捕获/锁存显示故障压回 0。 | V1.3 段0907–0912 |
| **C5** | 清除只走 `posedge clk` 分支 → 死时钟既不清也丢。 | V1.3 段0913–0915 |
| **C6** | `hw_blank = blank_r \| !en \| any_hw_fault \| caught_any \| !disp_armed \| disp_fault` 六锁不变。 | 已验收设计 |

**为什么不是"单锁存 OR 进 bit7"**（= P0-D 候选，复审 NC-1 反例）：任何本地故障都会
置 COMM_TO 且在自己被 W1C 清除后仍锁死 bit7 → 历史 D33（status 全零）失败、
D53（再使能）被拒——与本轮收到的 `independent_l1_regression_counterexample.csv`
逐格一致。**为什么不是"删本地捕获"**：亚周期脉冲保护会退化（C1），复审明令禁止。

## 2. 硬件实现（候选分支 `3cdd58c`）

```verilog
reg [10:0] caught;                       // 每源一条
generate for (g = 0; g < 11; g = g + 1) begin : g_cap
    wire clear_caught_req = frame_is_fault_w1c && wr_frame[g] && !hw_fault[g];
    always @(posedge clk or posedge hw_fault[g] or negedge reset_n) begin
        if (!reset_n)             caught[g] <= 1'b0;
        else if (hw_fault[g])     caught[g] <= 1'b1;    // set 永远赢
        else if (clear_caught_req) caught[g] <= 1'b0;   // 同拍、同掩码位
    end
end endgenerate
```

`n_fault = fault_status | hw_fault | (err_set ? bit8) | caught;`、
`fault_vis_o = fault_status | hw_fault | caught;`、
`hw_blank` 与 CTRL 准入使用 `caught_any = |caught`。
`frame_is_fault_w1c = wr_cap_o && 对齐 && A_FAULT`（与 P0-D 相同的 shake 手）。
代价：11 个异步置位触发器（原 1 个）；STA 需为 11 条异步置位路径建约束（登记）。

## 3. 历史回归重放（`tools/t6a_p0e_model.py`，逐事件、零仿真）

按原 L1 TB 的**真实交易顺序**重放（TB 行 318–346 / 443–455 / 460–471）：

| 检查 | 合同 | 结果 |
|---|---|---|
| D26 UVLO 锁存（bit0，无 bit7） | C2/C3 | PASS |
| D27 活故障不可清 | C3 | PASS |
| D28 源撤后 W1C → status 与捕获同拍归零 | C3/C4 | PASS |
| D29/D30 INT 锁存与 INT 地址 W1C | C2/C3 | PASS |
| D33 清 OT 后 **status == 0x000** | C2/C3 | **PASS**（复审反例的正面解） |
| D45/D46 bit1 锁存、读不清、W1C 生效 | C2/C3 | PASS |
| D53 清理后 CTRL 再使能被接受，hw_blank=0 | C4 | **PASS** |
| Phase S E01–E20（引脚 4ns 脉冲路径） | C1–C6 | PASS |

负控五类（任务书 C 指定，全部在同一模型里真实 FAIL）：

| 负控 | 复现的缺陷 |
|---|---|
| NC-1 单锁存 OR 进 bit7 | D33 → status=0x080（= 复审反例）；NC-1b D53 被拒 |
| NC-2 删本地捕获 | 亚周期本地脉冲丢失（C6 退化） |
| NC-3 误清 COMM_TO | W1C=0x000 也清 bit7 |
| NC-4 旧注册清除 | bit 复活（P0-C 缺陷） |
| NC-5 放宽再使能准入 | 锁存未清写被接受（面板仍被 fault-wins 压住——双保险独立有效） |

## 4. 已知限制

- 状态模型 + 静态门是零仿真证明；**L1 定向仿真仍未获批、未执行**；
  E01–E20 是计划不是结果；
- 11 条异步置位路径的 STA 约束、`cs_n` 功能时钟约束、PVT 未做；
- bit7 仍是共享原因位（只说明"发生过共享 FAULT_n 事件"）；
- `hw_blank` → 引脚 `blank` 连线、`tcon_top` `ST_FAULT` 退出条件改造留待集成（L2 前）。
