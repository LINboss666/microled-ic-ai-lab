# T6-A L1 安全验证计划（rev4，2026-11-19，P0-D）

> 分层裁定沿用 P0-B 复审：**L1 = SPI 单元安全**（只判寄存器/许可/锁存，
> 不许说"灯亮不亮"）；**L2 = 五芯片系统安全**（看真实 `ch_en`，另立预算）。
> 本文件是 L1 的执行计划——**已准备、未执行**（P0-D 为零仿真轮）。

## 1. 载体

| 物料 | 状态 |
|---|---|
| `tb/tcon_t6a_l1_tb.sv.txt` | **已写、已编译（vlog 0/0）、未执行**；57 条 rev2 断言原样保留 + Phase S E01..E20 |
| `tb/run_tcon_t6a_l1.sh` | 已写、bash -n 通过；`FLOOR=77`，vsim 命令就位 |
| DUT 端口 | `.fault_n(fault_n)` **显式连接**（缺省会浮 Z，被 `fault_n?0:0x080` 读成故障）；`.disp_armed_o/.hw_fault_caught_o` 同接 |
| 时钟 | `clk_en` 门控（仅 Phase S 用，用于死时钟用例） |

## 2. Phase S 场景设计（对应 `tcon_t6a_l1_tb` E01–E20）

每个故障脉冲 4 ns 宽、起点在 core 上升沿后 3 ns —— **起点与终点都落在两个
时钟沿之间**，`pulse_edges` 计数器证明 `E02_pulse_really_escaped_the_clock`。

| 断言 | 验证内容 |
|---|---|
| E01 | 脉冲前面板处于点亮态（armed=1, hw_blank=0）——防止"一直黑也能 PASS" |
| E02 | 脉冲内 core 沿数 = 0（逃逸条件为真，非空洞） |
| E03–E06 | 捕获置位；`FAULT_STATUS[7]`/`INT_STATUS[7]` 可读；面板熄灭 |
| E07 | 源撤去后 3 个沿无自动恢复 |
| E08 | **一次**合法 W1C 后 status[7] 与 caught 同沿归零 |
| E09/E10 | `split_cnt=0`（不存在"状态清了、捕获还在"的沿——rev3 缺陷的签名）；`resurrect_cnt=0`（bit7 不复活） |
| E11 | 未再使能前保持熄灭 |
| E12/E13 | 显式 CTRL 再使能被接受，连续 3 个非零许可采样 |
| E14/E15 | W1C=0x000 不清；0x001 部分掩码保留 bit7 |
| E16/E17 | 活故障清不掉；源撤后可清 |
| E18 | 读事务不清除 |
| E19/E20 | 核心时钟停死：保持熄灭、捕获不丢、时钟恢复后仍在 |

两个持续监视器（非单点检查）：
- `split_cnt`：逐沿查 `status[7]==0 && caught==1` —— rev3 RTL 恰好产生 1 次；
- `resurrect_cnt`：逐沿查 `status[7]` 0→1（窗口内无脉冲）。

## 3. 负控（D.4：四类，全部绑定具体断言）

| 负控 | 做法 | 必然失败的断言 |
|---|---|---|
| NC-A | 还原寄存器 `clr_fault`（rev3 写法） | E08/E09/E10 |
| NC-B | 去掉 caught→bit7 映射 | E04/E05 |
| NC-C | clr 不看 W1C 掩码 | E14/E15 |
| NC-D | 捕获改回 `posedge clk` 采样 | E02/E03 |
| NC-E | L1 TB 拔掉 `.fault_n` 连接 | 编译过但 E03 读 Z——静态门先抓 |

其中 NC-A..C 由 `tools/t6a_p0_rearm_check.py`（D0–D5 系列）与
`tools/t6a_p0d_precheck.py`（对篡改副本的结构判据）**在本轮已经真实执行并 FAIL**；
NC-D/E 属于 L1 执行日的动态检查。

## 4. 执行顺序（L1 预算获批后，一次 vsim 内完成）

1. `reset` → 57 条 rev2 回归原样跑（名称/阈值不动，`MIN_ASSERTS≥77`）；
2. Phase S E01–E20；
3. 两个监视器计数写入 transcript（`T6A_L1_SAFETY split_edges=... resurrections=... permit_samples=...`）；
4. T6 五条件 + runner 退出码照常。

**停止条件**：任何一条 FAIL → 保留证据、不追加第二次。

## 5. 明确不属于 L1 的事项

- L2（五芯片、真实 `ch_en`、预充恢复）另立预算与环境；
- `hw_blank → blank` 引脚连线、`tcon_top` `ST_FAULT` 退出条件改造（规格更严）；
- CDC/STA/PVT 签核；`cs_n` 功能时钟约束。
