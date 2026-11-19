# T6-A 故障捕获 / 清除 / 再使能协议（rev4，2026-11-19，P0-D）

> 历史：rev1（disp_armed 首案）→ rev2（NBA 语义修正）→ rev3（COMM_TO 映射 + W1C 掩码）
> → **rev4（本版）**：清除请求改为组合，关闭复审发现的 `W1C_CLEAR_NBA_RACE`。
> 各版全文见 `_rev1/` `_rev2/` `_rev3/` 子目录。

## 1. rev3 遗留的缺陷（复审已独立复现）

rev3 的清除是**寄存器脉冲**，而捕获位在**另一个** always 块里：

```verilog
// 主块，第 N 沿
clr_fault <= 1'b0;
if (wr_cap_o && (wa[5:2]==A_FAULT) && w1c_f[7] && !any_hw_fault)
    clr_fault <= 1'b1;              // NBA：N 沿只"登记"

// 捕获块，同一个第 N 沿
else if (clr_fault) ...             // 读到的是旧值 0 —— 清不掉
```

于是按逐沿推演（与 `independent_nba_w1c_replay.csv` 一致）：

| 沿 | FAULT_STATUS[7] | caught | clr_fault | 说明 |
|---|---:|---:|---:|---|
| W0（W1C） | 1 → **0** | 1 | 0→1 | 状态清了，捕获块读旧值 |
| W1 | **0 → 0x080** | 1 → 0 | 1→0 | `n_fault` 把旧 caught OR 回 bit7，**复活** |
| W2 | 0x080 | 0 | 0 | 永久锁死 |
| CTRL 再使能 | — | — | — | `disp_fault=1` → **拒绝** |

后果：不是误亮，而是**合法恢复永远做不到**（`FAULT_REARM_R1_R2 = NOT_VERIFIED_IN_RTL`）。
v3 模型把清除写成了同拍（`fw and (w1c & VIS) -> caught=0`），所以没抓到——v4 模型
已按真实 RTL 拆成两个块并显式建模 `clr_old`/`clr_next`（见 §4）。

## 2. rev4 修复：组合清除请求，同拍生效

```verilog
wire clear_caught_req = wr_cap_o &&
                        (wa_w[1:0]  == 2'b00) &&
                        (wa_w[14:6] == 9'd0)  &&
                        (wa_w[5:2]  == A_FAULT) &&
                        wr_frame[7]           &&   // W1C 掩码必须覆盖 COMM_TO
                        !any_hw_fault;             // 活故障压过清除

always @(posedge clk or posedge any_hw_fault or negedge reset_n) begin
    if (!reset_n)          hw_fault_caught <= 1'b0;
    else if (any_hw_fault) hw_fault_caught <= 1'b1;    // set 永远赢
    else if (clear_caught_req) hw_fault_caught <= 1'b0; // 与 fault_status 同沿
end
```

要点：

1. **同拍**：`wr_cap_o` 高的那个 core 沿，主块算 `n_fault`（把 caught 旧值 OR 进
   bit7 后被 W1C 掩掉）→ `fault_status <= 0`；捕获块同时看到 `clear_caught_req=1`
   → `caught <= 0`。**同一个沿、同一笔写**，没有先后。
2. **`clr_fault` 寄存器整个删除**——不存在"先登记、下拍执行"。
3. **清除仍是同步的**：`clear_caught_req` 只进 `posedge clk` 分支，不在敏感列表里；
   核心时钟停死时既不清也丢不了（段0915 要求）。
4. **set > clear 双保险**：分支顺序 `any_hw_fault` 在前，且请求本身含 `!any_hw_fault`。
5. 输入都是寄存器/稳定值（`wr_frame` 整个 CS_n 事务不变；`wr_cap_o` 由同步后的
   toggle 生成），边沿处无毛刺风险。
6. 背靠背帧挤掉的场景仍由 `mb_lost` 报告，语义不变。

## 3. 修复后的闭环时序

| 沿 | FAULT_STATUS[7] | caught | 说明 |
|---|---:|---:|---|
| W0（W1C=0x080） | 1 → **0** | 1 → **0** | 同沿归零 |
| W1 / W2 | 0 | 0 | 连续三沿干净（模型 D1） |
| CTRL EN=1,BLANK=0 | 0 | 0 | 通过全部准入 → `disp_armed=1` |
| 之后 | 0 | 0 | `hw_blank=0`，连续 3 个许可采样（模型 D2） |

不变量（全轮有效）：
- 捕获 → `FAULT_STATUS[7]` / `INT_STATUS[7]` / `fault_vis_o`（COMM_TO，段0704）；
- `hw_blank = blank_r | !en | any_hw_fault | caught | !disp_armed | disp_fault`；
- 活故障 / 捕获 / 锁存任一存在 → 许可清零（块末尾，压过同拍置位）。

## 4. 模型（`tools/t6a_p0_rearm_check.py`，v4）

双块建模，两个 variant：
- `registered`（= rev3 缺陷）：捕获块读 `clr_old`；
- `fixed`（= rev4 候选）：捕获块读组合请求。

断言与负控（全部在同一执行里真实 FAIL 过）：

| ID | 内容 |
|---|---|
| D0a/b/c | **旧候选反例复现**：`000/1/1 → 080/0/0 → CTRL 拒绝`（与复审逐格一致） |
| D1a-d | 修复版：同沿归零 + 连续三沿干净 + 无残留 clr + 仍熄屏 |
| D2a/b | 显式再使能被接受 + **3 个非零许可采样** |
| D3a-e | W1C=0 不清；0x001 只清 bit0；0x080 清捕获+bit7；活故障清不掉；源撤后一笔覆盖两位的 W1C 清干净 |
| D4a/b | 其他地址 / 读事务不能清 |
| D5a/b | 清除沿后 1 ps 出现的脉冲被异步捕获；清除沿当时仍在的脉冲 set 胜 |
| E17-E22 | 可读性 / 零掩码 / 部分掩码 / 同沿新脉冲 / 死时钟 |
| R1/R2 | 清除后不许自动亮；显式再使能后可亮 |
| NC-1 | 还原寄存器延迟 → D1b 失败 |
| NC-2 | 去掉 caught→bit7 → E17a 失败 |
| NC-3 | 去掉 W1C bit7 掩码 → D3a 失败 |
| NC-4 | 去掉异步置位 → E22a 失败 |

## 5. 已知限制（不要按已完成理解）

- 本文件是**状态规则 + 组合结构**的零仿真证明；L1 定向仿真未获批、未执行；
- bit7 是**共享原因位**（段0704），只说明"捕获到过一次共享 FAULT_n 事件"，
  不指明哪一路；逐路原因需要 11 个独立异步锁存（选项 B，未批准）；
- 物理层：异步单元最小置位脉宽、开漏上拉、`cs_n` 功能时钟的 STA 约束均未做；
- `hw_blank` → 引脚 `blank` 的连线仍未定（`P0B_FAULT_PATH.md` N9/N10），
  整颗芯片级短脉冲防护要在 L2 五芯片环境里收口。
