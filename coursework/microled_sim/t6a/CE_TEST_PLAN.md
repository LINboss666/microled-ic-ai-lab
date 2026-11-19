# T6-A L1 安全验证计划（rev5，2026-11-19，P0-E）

> 分层裁定沿用 P0-B 复审：**L1 = SPI 单元安全**（只判寄存器/许可/锁存，
> 不许说"灯亮不亮"）；**L2 = 五芯片系统安全**（看真实 `ch_en`，另立预算）。
> 本文件是 L1 的执行计划——**已准备、未执行**（P0-E 仍为零仿真轮）。
> 上一版见 `_rev4_20261119/`。

## 1. 载体

| 物料 | 状态 |
|---|---|
| `tb/tcon_t6a_l1_tb.sv.txt`（LF `32a42819…`，纠正旧报告误写的 `f184d359`） | **已写、已编译（vlog 0/0）、未执行**；57 条 rev2 断言原样保留 + Phase S E01–E20 |
| `tb/run_tcon_t6a_l1.sh`（LF `e9d64131…`） | 已写、bash -n 通过；`FLOOR="77"`，vsim 命令就位 |
| DUT 端口 | `.fault_n(fault_n)` **显式连接**（缺省浮 Z 会被 `fault_n?0:0x080` 读成故障）；`.disp_armed_o/.hw_fault_caught_o` 同接 |
| 候选 RTL | `t6a-p0-candidate-20261119` @ `3cdd58c`（regs LF `6005c806…`），逐源捕获向量 |
| 时钟 | `clk_en` 门控（仅 Phase S 死时钟用例） |

## 2. Phase S 场景（E01–E20，不变）

每个故障脉冲 4 ns 宽、起点在 core 上升沿后 3 ns —— 起点与终点都落在两个时钟沿
之间，`pulse_edges` 计数器证明 `E02_pulse_really_escaped_the_clock`。逐条断言表
见上一版 §2（E01–E20 语义不变，未被 P0-E 改动）。

## 3. 历史回归（P0-E 新增，模型级已收口）

`tools/t6a_p0e_model.py` 按原 L1 TB 的真实交易顺序重放 D26–D33、D45–D53 与
Phase S——**57 条历史断言的名称与阈值一个都没动**，D33/D53 在逐源捕获合同下
自然成立（`FAULT_REARM_PROTOCOL.md` rev5 §3）。逐拍表：`t6a/L1_LEGACY_REPLAY.csv`。

## 4. 负控（五类，绑定具体断言；模型 `tools/t6a_p0e_model.py`）

| 负控 | 做法 | 必然失败的断言/反例 |
|---|---|---|
| NC-1 | 还原单锁存 OR 进 bit7 | D33 → status=0x080（复审反例）；NC-1b D53 被拒 |
| NC-2 | 删本地捕获 | C6a–d（亚周期本地脉冲丢失） |
| NC-3 | clr 不看掩码 | E14/E15 |
| NC-4 | 还原寄存器 clr_fault | D0 反例（bit 复活） |
| NC-5 | 放宽再使能准入 | C4（锁存未清写被接受；面板仍黑） |

以上全部已在零仿真模型中真实执行并 FAIL。静态门 `tools/t6a_p0e_precheck.py`
（注释先剥）再拦其中三类结构回退（NC-1/2/3 的 RTL 形态），共 6 个结构负控。

## 5. 执行顺序（L1 预算获批后，一次 vsim 内完成）

1. `reset` → 57 条 rev2 回归原样跑（名称/阈值不动，`MIN_ASSERTS≥77`）；
2. Phase S E01–E20；
3. 监视器计数写入 transcript（`T6A_L1_SAFETY split_edges=… resurrections=… permit_samples=…`）；
4. T6 五条件 + runner 退出码照常。

**停止条件**：任何一条 FAIL → 保留证据、不追加第二次。

## 6. 明确不属于 L1 的事项

- L2（五芯片、真实 `ch_en`、预充恢复）另立预算与环境；
- `hw_blank → blank` 引脚连线、`tcon_top` `ST_FAULT` 退出条件改造；
- 11 条异步置位路径与 `cs_n` 功能时钟的 STA 约束、PVT。
