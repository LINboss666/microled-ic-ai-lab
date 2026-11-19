# 安全闸门归属（SAFETY_OWNERSHIP）— rev2

日期：2026-11-19　范围：`FAULT_AUTO_REENABLE` + `ASYNC_FAULT_CAPTURE` 两个 P0 的架构核对
（**零 ModelSim**；本轮不修改 T5 已验收顶层）

---

## 0. 结论

1. **归属澄清成立**：引脚级 BLANK 由 `tcon_top.blank` 唯一驱动，`tcon_spi_regs.hw_blank`
   目前没有负载 → 上一轮 P0 是**潜伏**缺陷，不是当前误点亮。
2. **但顶层也有一个洞**：`fault_evt` 只在 `clk_ref` 上升沿采样，
   **短于一个时钟周期的 `FAULT_n` 脉冲会完全丢失** —— 组合关断闪一下，锁存不进 FSM。
3. **SPI 块同样有这个洞**（rev1 提案的 `disp_armed` 也只在 core 沿清零）。
   → 修法不是"再加一个同步粘滞位"，而是**故障边沿本身置位的异步锁存**。
4. V1.3 **没有**给 `FAULT_n` 任何最小脉宽或源端锁存保证（§12 只说开漏、线与、外部上拉）。

---

## 1. V1.3 原文（`v13_fulltext.txt`，SHA `6b42b136…`）

| 段落 | 原文 |
|---|---|
| 0492–0496 | `FAULT_n`：Driver **开漏**→TCON；**开漏／3.3 V／1**；**线与、外部上拉；任一故障拉低熄屏** |
| 0704 | 「TCON 捕获共享 `FAULT_n` 后置 COMM_TO」 |
| 0907 | 欠压 →「硬件关高边与恒流；**`FAULT_n` 拉低**」 |
| 0908 | 「所有电源恢复且故障清除，**不自动点亮**」 |
| 0912 | 过压/过热 →「回到滞回恢复区后**人工/Host 清除再使能**」 |
| 0915 | 时钟/帧超时 →「关断、锁存；**不得依赖已停止的 PCLK 检测自身失效**」 |
| 0916 | 时钟/帧超时 →「**下一合法帧边界并重新预充**」 |
| 0965 | 验证 →「**硬件先关；故障锁存；清状态不自动恢复显示**」 |

**推导**：`FAULT_n` 是线与开漏 + 外部上拉，是一个**异步电平**；
规格**没有**规定它至少保持一个 `clk_ref` 周期，也**没有**声明源端一定锁存。
因此"等一个时钟沿去采样"在合同上不成立。

---

## 2. 三条路径必须分清（任务书 §A.2）

| 路径 | RTL | 触发方式 | 4 ns 脉冲能否捕获 |
|---|---|---|---|
| `fault_n` → **组合关断** | `blank = … \|\| !safe \|\| flt \|\| …`，`safe = mode_en && rx_ready && fault_n` | 组合，无时钟 | ✅ 当拍拉高 |
| `fault_evt` → **FSM 锁存** | `wire fault_evt = act && (err_any \|\| !fault_n);`<br>`ST_ACTIVE: if (fault_evt) state <= ST_FAULT;` | `posedge clk_ref` | ❌ **丢失** |
| `hw_fault` → **SPI 块关断** | `hw_blank = … \| any_hw_fault` | 组合 | ✅ 当拍 |
| `hw_fault` → **核心锁存** | `fault_status <= n_fault` | `posedge clk` | ❌ 丢失 |
| `disp_armed` 清零 | `posedge clk` | ❌ 丢失 |

**"关断"有，"锁存"没有。** 这就是复审给出的：`BLANK` 在 12–15 ns 为 1、16 ns 回 0，
20 ns 的时钟沿看到 `fault_n=1` → 状态机仍在 ACTIVE。

---

## 3. 逐时刻证据

`tools/t6a_p0_async_fault.py` 产出的时间线（完整 64 行见 `ASYNC_FAULT_TIMELINE.csv`）：

| t (ns) | clk 沿 | fault_n | state | tcon_blank | panel_blank（集成后） |
|---:|---:|---:|---|---:|---:|
| 10 | 1 | 1 | ACTIVE | 0 | 0 |
| 12 | 0 | **0** | ACTIVE | **1** | 1 |
| 15 | 0 | 0 | ACTIVE | 1 | 1 |
| 16 | 0 | 1 | **ACTIVE** | **0** | 0 |
| 20 | 1 | 1 | **ACTIVE** | 0 | **0** ← 故障未被锁存 |

脉宽扫描（1/2/4/8/9/10/11/20 ns × 相位 0/2.5/5/7.5 ns）：
`fsm_only` 与 `sync_only` 在 **1/2/4 ns 全部丢失**（只有脉宽恰好跨过时钟沿的相位才侥幸捕获）；
`async_set` 在**全部 32 个组合**保持关断。

---

## 4. 修法：异步置位 / 同步清除

```verilog
always @(posedge clk or posedge any_hw_fault or negedge reset_n) begin
    if (!reset_n)          hw_fault_caught <= 1'b0;
    else if (any_hw_fault) hw_fault_caught <= 1'b1;   // 置位走故障边沿，不要时钟
    else if (clr_fault)    hw_fault_caught <= 1'b0;   // 清除必须走时钟沿
end
```

| 性质 | 怎么得到 | 对应条款 |
|---|---|---|
| 任意窄脉冲都能捕获 | 置位是 `posedge any_hw_fault` | 段0496「任一故障拉低熄屏」 |
| 时钟停了仍然关断 | 置位后 `hw_blank` 是组合 OR；没有时钟就跑不了 clear | 段0915 |
| 源消失后不自动恢复 | `hw_fault_caught` 粘滞，清它必须写 W1C | 段0908/0965 |
| 清掉后仍不点亮 | 清的是 `caught`，`disp_armed` 仍需显式 CTRL 写 | 段0912/0965 |

**优先级**：`!reset_n` > 置位（`any_hw_fault`）> `clr_fault`。
同一 always 块内"先写者优先"，所以 `fault_n` 仍为低时**清不掉**。

`clr_fault` 的产生条件：
```
wr_cap_o && wa[5:2]==A_FAULT && (n_fault == 0) && !any_hw_fault
```
即"一笔 FAULT 的 W1C，清完之后**一位都不剩**，且当前没有活故障"。
只要还有一位没清，`caught` 就保持 → 逐位区分的要求成立。

---

## 5. 归属不变的部分

```
blank_pin = tcon_top.blank  ||  hw_blank     // OR，不是选择
tcon_top.blank = blank_seq || !safe || flt || !act || (act && !disp_ok)
hw_blank       = blank_r | !en | any_hw_fault | hw_fault_caught | !disp_armed | disp_fault
```

- 顶层那把钥匙 = **帧合法 + 两级预充 + 标签有效**（`disp_ok`）；
- SPI 那把钥匙 = **Host 许可**（`disp_armed`）；
- 任一把不成立都不亮。

**顶层也要改**（R3，属 T5 代码，本轮只提案）：
`ST_FAULT` 目前只能靠整片复位退出，与段0912 的"Host 清除再使能"不符。
集成阶段应改为：`ST_FAULT` 只能由**一次显式 Host 再使能 + 重新预充 + 合法帧**退出。
否则客户要么永远点不亮，要么只能靠复位——两种都不合规格。

---

## 6. 本轮证据

| 文件 | 内容 |
|---|---|
| `tools/t6a_p0_async_fault.py` | 逐 ns 时间线 + 脉宽/相位扫描 + 清故障协议 + 死时钟 |
| `tools/t6a_p0_rearm_check.py` | **NBA 语义**状态模型（rev1 的"先更新 `fault_status` 再判准入"已废弃，原件在 `…_v1_archive.py`） |
| `t6a/ASYNC_FAULT_TIMELINE.csv` | 64 行逐 ns 时间线，含 fsm_only / async_set 两列 |
| `t6a/SUGGESTED_PATCH.diff.txt` | 候选补丁（`tcon_spi_regs` + `tcon_spi_top`），只在独立分支试应用 |

**RTL 未改**：`course/…` 分支上四个已验收源文件 SHA 与 RUN02 清单逐字节一致。
