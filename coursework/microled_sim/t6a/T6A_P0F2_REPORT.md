# T6-A P0-F2 报告：L1 连续场景边界闭合（零 ModelSim，2026-11-19）

**上游**：P0-F 复审 `T6A_P0F_STATIC = ACCEPT_WITH_SCOPE`、
`L1_TB_PHASE_CONTINUITY = FAIL_STATIC`、`L1_MODELSIM = HOLD`。
本轮按《P0-F2 任务书》：**0 次 vsim**，只改 L1 TB + 新增连续重放模型 + 静态门。
RTL（含 P0-F 的 C2 引脚独占与逐源捕获）一字未改。

## 1. 缺口确认（与复审逐格一致）

复审指出：真实 L1 TB 在同一颗 DUT 上连续运行，而软件模型按场景分段——E18
遗留的 COMM_TO(bit7) 会被带进 E21/E22，E21d（`status===0`）与 E22
（`bit7===0`）必然失败。我用单实例连续重放复现：

```text
NC-PHASE（无清理写）：E21d status=0x080 caught=0x080 → E21d/E22 断言 FAIL
                  复审 INDEPENDENT_L1_E18_TO_E22_REPLAY.csv 逐格一致
```

## 2. 修复（候选分支 `2e86c89`，只动 TB）

E20 之后、E21 之前插入**一次合法 SPI W1C** + 新断言（名称按裁定指定）：

```verilog
wr(15'h0C, 32'h0000_0080);
repeat (3) @(posedge clk);
chk("E20a_phase_s_cleanup_without_rearm",
    (fault_status === 11'd0) && (hw_fault_caught_o === 1'b0) &&
    (disp_armed_o === 1'b0) && (hw_blank === 1'b1));
```

四个条件同时锁住"清理但未顺手再使能、仍然熄屏"。无 force、无直赋、无复位。

## 3. 连续重放（`tools/t6a_p0f2_continuity.py`，单实例）

正控：E18 保持 → E19/E20 死时钟保持 → **E20a 清理且仍黑** → E21 多源矢量
（bit0 清、bit2 活、30 沿不复活）→ E21d 全清 → E22 总线 bit7 不置 COMM_TO →
E22b 引脚捕获 → E22c 合法清 —— 全 PASS，逐拍表
`t6a/E18_E22_CONTINUITY.csv`（含 check/expected/clause）。

负控（任务书 §B 三类 + 回归）：

| 负控 | 结果 |
|---|---|
| NC-PHASE 删清理写 | E21d=0x080、E22 FAIL（TB 级断言名被真实命中） |
| NC-REARM 清理后顺手再使能 | armed=1、hw_blank=0 —— 所以 E20a 断言必须禁止它 |
| NC-SOURCE 总线 bit7 误连 | fault_n=1 时 COMM_TO 被锁存（E22 的"牙齿"） |
| 回归 D33/D53/M1 | 同模型仍 PASS |

## 4. 静态门（`tools/t6a_p0f2_precheck.py`，注释先剥）

K1 清理写位于 E20/E21 之间且无 force/直赋/复位；K2 E20a 四条件齐备；
K3 断言 86、全唯一、FLOOR="86"；K4 连续模型与三负控存在；K5 P0-F 结构
（C2 折叠、逐源 generate、逐位 oracle）未退化。5 个负控全过。`GATES_FAILED=0`。

## 5. 断言与 SHA

- L1 TB 断言 **86 = 57 + 20 + 8 + 1**，名称全部唯一（`evidence/05`）；
  runner `FLOOR="86"`。
- P0-F tip TB LF `072c844c…`（与复审基线一致）→ P0-F2 tip LF `fb460170…`；
  **TB diff 非空（36 行）**，`diff/candidate_tb_diff.txt`。
- RTL 本轮零改动：top LF `b6c24bae…`、regs LF `6005c806…`、spi_frame LF
  `73923f19…`（与 P0-F 复审基线逐一相同）——`diff/` 内附说明，不以空文件充数。
- `tcon_spi_regs`（accepted 参考）LF `05aaabbe…`/CRLF `bdde768a…` 不变。

## 6. 编译与模型

L1 TB + 候选 RTL：vlog **0/0**（`evidence/04`）。模型从包内 `models/` 可直接
复跑（CSV 输出在仓库布局缺失时回落到脚本目录）。

## 7. Git

- `t6a-p0-candidate-20261119`：`2e86c89`（TB + 连续模型 + 静态门）
- `course/microled-assignment-sim-20261112`：文档与工具同步提交
- 推送状态以 `gates.txt` 为准（含远端回读）。

**终态：`WAITING_FOR_P0F2_ZERO_SIM_REVIEW`。** L1 唯一一次预算仍由您裁定。
