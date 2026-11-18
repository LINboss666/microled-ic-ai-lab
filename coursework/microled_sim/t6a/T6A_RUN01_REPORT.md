# T6-A RUN01 报告：TCON SPI / 寄存器首轮（FAIL 10/43）

日期：2026-11-18
授权：`T6_A_SPI_REGISTER_DEVELOPMENT = READY`（新增预算 ≤2 次正式 ModelSim）
本次使用：**1 次**（`vsim` 2 s）。**首次 FAIL → 立即停止，未跑第二次，未在运行后修改任何被测源。**

## 0. 结论

| 项 | 结果 |
|---|---|
| `T6A_RUN01` | **FAIL_10_OF_43** |
| T6 五条件 | `1/1/0/0/1` → 检查器正确判 FAIL |
| 编译 | 0 errors / 0 warnings |
| 根因 | **两个 RTL 缺陷，都在我新写的 `spi_frame` 里**（不是 TB 期望问题） |
| 是否已修 | **否**（按任务书停止，等复审授权） |
| 预算 | 1 / 2 已用 |

## 1. 直接证据

```
# T6A_COUNTS writes=34 reads=39 commits=77 sw_pulses=0 frames=0
```

`frames=0` 是决定性的：TB 每个核心时钟沿检查 `frame_full && bitcnt==48`，整个运行里**一次都没有出现**。
即：**48 位从未被移入**，`bc` 始终为 0，于是没有写提交、没有读应答（所有读回 0）。

10 条 PASS 全部是"读回 0"或"错误位为 0"这类**在空转下也会成立**的断言（D04/D13/D22/D28/D30/D31/D33/D40/D42/D43），
这本身暴露了我在 TB 里的一个**非空洞性漏洞**（见 §3）。

## 2. 根因（两处，均为 RTL 缺陷）

### D-1（决定性）`cs_n` 被当成异步复位，导致每个 SCLK 沿都清零

`rtl/spi_frame.v`：

```verilog
always @(posedge sclk or negedge cs_n) begin
    if (!cs_n) begin sh_r <= 0; bc <= 0; end       // <-- 事务期间 cs_n 恒为 0
    else       begin sh_r <= {sh_r[46:0], mosi}; ... end
end
```

SPI 事务期间 `cs_n` 一直是低电平，所以**每个 `posedge sclk` 都会命中 `if (!cs_n)` 分支清零**，
移位寄存器与位计数永远不前进。这是把"电平"当成了"事件"。

**正确写法**（下一步拟采用）：用 SCLK 域采样 `cs_n` 的历史值来识别**本帧第一个沿**，不再用 `cs_n` 做异步复位：

```verilog
always @(posedge sclk) cs_prev <= cs_n;
wire first = !cs_n && cs_prev;            // 帧首沿
always @(posedge sclk) begin
    if (!cs_n) begin
        if (first) begin bc <= 0; sh_r <= {47'd0, mosi}; end
        else       begin sh_r <= {sh_r[46:0], mosi}; bc <= bc + 1; end
    end
end
```

### D-2（被 D-1 掩盖，但确定存在）读写位极性反了，且写路径没有判读写

`rtl/spi_frame.v`：`assign rd_req = !cs_n && (bc >= 16) && !sh_r[47];`
V1.3 段0569 规定 **bit15 = 1 表示读**，所以读事务上 `sh_r[47]=1`，`!sh_r[47]=0` → `rd_req` **永远不会拉高** → 读通路不工作（MISO 恒 0）。

`rtl/tcon_spi_regs.v`：提交分支只判 `cs_rise && frame_full`，**完全没有判 `sh[47]`** →
一旦 D-1 修好，一次"读"事务也会被当成写提交（把 0 写进被读的寄存器，并触发 ERR_REG）。等价于 T3-H2 那类"没看该看的位"。

**拟采用的修正**：`rd_req = !cs_n && (bc>=16) && sh_r[47]`；MISO 仅在该条件成立时驱动；
`tcon_spi_regs` 的写提交加上 `&& !sh[47]`（bit15=0 才是写）。

## 3. 我自己 TB 的非空洞性缺陷（必须一并修）

`T6A_COUNTS` 的 `writes/reads` 是 TB **发起**的次数（`n_wr_ok/n_rd_ok`），不是 **DUT 真的提交/应答**的次数。
空转时它们照样增长，于是 10 条断言在"什么都没发生"的情况下 PASS。

**修正**：非空洞下限改为可观测事件——
- 写侧用 `frame_full` 且事务为写的计数；
- 读侧用"读回值与期望一致"的计数；
- 并新增一条断言：`committed_writes >= 20 && matched_reads >= 30`，否则 FAIL。

## 4. 尚未被本轮覆盖的部分

D-1 让 33 条断言从未真正被激励到，因此下列行为**本轮没有证据**（既不通过也不失败）：
寄存器复位值、写读回、非法地址/非对齐/RO 写、CS_n 截断、W1C 前置条件、INT_EN 屏蔽、10/4 MHz 与相位、背靠背事务。

## 5. 下一步（等授权，不自行开跑）

1. 按 §2 修 `spi_frame`（帧首沿识别 + 读位极性）；
2. 按 §2 给写提交加 `!sh[47]`；
3. 按 §3 修 TB 的非空洞下限；
4. 重新零仿真预检（SHA 冻结、43 条断言名不变、离线 SPI 模型仍 PASS、编译 0/0），
   再申请消耗第 2 次（也是最后一次）预算。

预算账：T6-A **1/2**。未跑 T1/T3/T4/T5、未跑 Spectre/MC/OA/STA、未动 main、未开 PR、未自签 GO。
**终态：`WAITING_FOR_T6A_RUN01_INDEPENDENT_REVIEW`。**
