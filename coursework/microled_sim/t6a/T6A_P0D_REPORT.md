# T6-A P0-D 报告：W1C 同拍清除闭环（零 ModelSim，2026-11-19）

**上游**：T6-A P0-C 复审 `T6A_P0C_MODEL = PARTIALLY_ACCEPTED`，
`W1C_CLEAR_NBA_RACE = OPEN_P0`，`FAULT_REARM_R1_R2 = NOT_VERIFIED_IN_RTL`，
`L1_MODELSIM = HOLD`。本轮按《P0-D 限定任务书》执行：**0 次 vsim**，
只在候选分支改 `tcon_spi_regs` 的清除时序 + 离线模型/静态守卫。

## 1. 反例复现（先证明我们和复审看到的是同一个东西）

`tools/t6a_p0_rearm_check.py` v4 把模型拆成**两个 always 块**，`clr_fault` 作为真实
寄存器（主块第 N 沿登记、捕获块第 N 沿读旧值）。`registered` variant 输出：

```text
W0 W1C : status=0x000 caught=1 clr=1     ← D0a
W1 idle: status=0x080 caught=0 clr=0     ← D0b  bit7 复活
W2 idle: status=0x080
W3 CTRL: rejected=1 status=0x180 blank=1 ← D0c  再使能被拒
```

与 `independent_nba_w1c_replay.csv` 逐格一致（D0 三条断言锚死）。

## 2. 修复（候选分支 `t6a-p0-candidate-20261119`，提交 `fea14d6`）

```verilog
wire clear_caught_req = wr_cap_o && (wa_w[1:0]==2'b00) && (wa_w[14:6]==9'd0)
                        && (wa_w[5:2]==A_FAULT) && wr_frame[7] && !any_hw_fault;
...
else if (clear_caught_req) hw_fault_caught <= 1'b0;   // 与 fault_status 同沿
```

- `clr_fault` 寄存器**整个删除**（-1 个寄存器、-1 段时序）；
- 清除请求是组合的，输入全部是稳定值（`wr_frame` 整个事务不变）；
- set 优先级双保险：分支顺序 + `!any_hw_fault`；
- 清除仍只在 `posedge clk` 分支 → 死时钟清不掉；
- COMM_TO 映射、六项 `hw_blank`、W1C 掩码语义、`tcon_spi_top` 的 `fault_n`
  引脚折叠**全部不变**（任务书 §A）。

## 3. 修复后的逐沿证明（fixed variant）

```text
W0 W1C : status=0x000 caught=0 clr=0    ← D1a 同沿归零
W1/W2  : status=0x000 caught=0          ← D1b 连续三沿干净
CTRL   : armed=1, samples=[(1,0),(1,0),(1,0)]   ← D2 三个非零许可采样
```

其余：D3 掩码语义（0x000/0x001/0x080/活故障/源撤后）、D4 其他地址与读不能清、
D5 清除沿 ±1 ps 的新脉冲都被异步置位抓住、E17–E22、R1/R2 —— 全部 PASS；
**4 个负控**（还原寄存器延迟 / 去掉 caught→bit7 / 去掉掩码 / 去掉异步置位）
全部真实 FAIL。

## 4. 静态硬门（`tools/t6a_p0d_precheck.py`，注释先剥）

结构判据 17 条 + **5 个负控**（还原寄存器 / 清除进敏感列表 / 去掉活故障保护 /
去掉可见性映射 / L1 TB 拔掉 `.fault_n`）——每个负控都被抓。`RESULT=PASS`。

## 5. L1 测试台（D.7：显式连 `fault_n`，准备但不执行）

- `tb/tcon_t6a_l1_tb.sv.txt`（LF，`f184d359…`）：57 条 rev2 断言原样保留
  + Phase S E01–E20；脉冲 4 ns、起点沿后 3 ns（`E02` 证明逃逸条件为真）；
  `split_cnt`/`resurrect_cnt` 两个逐沿监视器直指 rev3 缺陷签名；
  `clk_en` 门控时钟做死时钟用例；`.fault_n` **显式连接**（NC-E 验证拔掉会被抓）。
- `tb/run_tcon_t6a_l1.sh`：`FLOOR=77`，vsim 命令就位，**未执行**。
- 编译：`vlog` **0 errors / 0 warnings**（`evidence/02_l1_tb_vlog.txt`）。

## 6. 三份既有模型照常运行（D.5）

| 模型 | 结果 | CSV |
|---|---|---|
| `t6a_p0_async_fault.py`（整数 ps 事件驱动） | PASS，11/20 ns 4/4 硬门 | 81 数据行 |
| `t6a_p0_edge_matrix.py`（36 组单沿矩阵） | PASS | 36 数据行 |
| `t6a_p0_rearm_check.py`（v4 双块） | PASS，D0 复现旧缺陷 | — |

（本轮顺带发现并纠正：candidate 分支上的 tools 是 P0-B 旧版，曾用它生成过
一版错误 CSV；上表数字全部来自 course 分支的修正版模型。）

## 7. 源码身份（两种行尾形式都给出）

| 文件 | course（已验收参考） | candidate（P0-D） |
|---|---|---|
| `tcon_spi_regs` | LF `05aaabbe…` / CRLF `bdde768a…` | **LF `6ce077f0…`** / CRLF `bf5e927c…` |
| `tcon_spi_top` | LF `07566c5b…` / CRLF `2624e7d3…` | LF `d71c2c1f…`（P0-C 引脚版，本轮未改） |
| `spi_frame` | LF `73923f19…` / CRLF `7d9465a6…` | 同左（未改） |
| `tcon_t6a_tb`（57 条） | LF `3a6ec32d…` / CRLF `a5cf32a1…` | 未改 |
| `tcon_t6a_l1_tb`（77 条） | — | LF `f184d359…` |

补丁 `t6a/SUGGESTED_PATCH.diff.txt`（+88/−12，两文件），对 course 分支
`git apply --check` 通过、**未应用**。

## 8. 已知限制

- **0 次 ModelSim**：候选 RTL 的动态行为未经仿真；57 条断言未在新候选下复验
  （L1 TB 已就位，等授权）；E01–E20 是计划不是结果；
- `hw_blank → blank` 引脚连线仍未定；`tcon_top` 的 `ST_FAULT` 仍只能复位退出；
- bit7 是共享原因位；CDC/STA/PVT/物理最小脉宽全部未做。

## 9. Git

- `course/microled-assignment-sim-20261112`：`98db901`（模型）+ 本轮文档提交
- `t6a-p0-candidate-20261119`：`fea14d6`（RTL + L1 TB + runner + 补丁）
- 推送与回读状态见 `gates.txt`

**终态：`WAITING_FOR_T6A_P0D_INDEPENDENT_REVIEW`。**
