# T6-A P0-E 报告：故障源归属冻结 + 历史回归收口（零 ModelSim，2026-11-19）

**上游**：P0-D 复审 `T6A_P0D_W1C_FIX = STATIC_ACCEPT_WITH_SCOPE`、
`L1_LEGACY_REGRESSION = OPEN`、`COMM_TO_SOURCE_CONTRACT = OPEN`、
`L1_MODELSIM = HOLD`。本轮按《P0-E 限定任务书》：**0 次 vsim**，两项工作——
冻结诊断合同 + 在状态模型里重放原 57 条测试的全部故障交易。

## 1. 合同冻结（任务书 §B，方案 A）

选择 **方案 A + 逐源异步捕获**：

- **C2**：COMM_TO(bit7) 只代表共享 `FAULT_n` 事件（段0704 原文；极性在
  `tcon_spi_top` 折叠一次：`hw_fault_i = hw_fault | (fault_n ? 0 : 11'h080)`）；
- **C1**：本地 UVLO/OV/OT **不删除捕获**——每路各有一条异步置位/同步清除锁存
  （11 位 `caught[10:0]`，generate 实现），上报进**自己的状态位**，亚周期脉冲
  保护对每一路都保持（复审"不可简单屏蔽保护"的约束）；
- **C3**：W1C 位 k 同拍清 `status[k]` + `caught[k]`；活故障位不可清；零掩码不动；
  **无隐式跨位清除**；
- **C4/C5/C6**：恢复顺序、死时钟、六锁 `hw_blank` 不变。

## 2. 历史回归重放（任务书 §C，硬门）

模型按**原 L1 TB 的真实交易顺序**重放（D26–D33 = TB 行 318–346；D45–D53 = 行
443–455；含 D31/D32 的 INT_EN 操作与 D55 的 hw_fault[3] 路径）：

```text
D26/D27/D28/D29/D30/D31/D32/D33/D45/D46/D53  全部 PASS
D33: status == 0x000   ← 复审反例（0x080）的正面解
D53: CTRL 接受，hw_blank=0
```

每条检查标注了依据条款（C1–C6），逐拍表：`t6a/L1_LEGACY_REPLAY.csv`（含
old/new 状态、`check`、`expected`、`clause` 列）。**没有删断言、没有放阈值、
没有在 D33 前插复位**——D33/D53 的历史语义在合同 A 下自然成立。

Phase S E01–E20 同模型重放（引脚 4ns 脉冲路径）全过；另加 C6 回归：本地 OT 线
4 ns 毛刺 → 捕获进 **bit2**（不是 bit7）→ 可读、熄屏、W1C 0x004 同拍释放。

## 3. 负控（任务书 C 点名五类，全部真实 FAIL）

| 负控 | 复现结果 |
|---|---|
| NC-1 统一捕获进 bit7（= P0-D 候选） | D33 → **0x080**、NC-1b D53 被拒 —— 与您的 CSV 逐格一致 |
| NC-2 删本地捕获 | 亚周期脉冲丢失 |
| NC-3 误清 COMM_TO | W1C=0x000 清掉 bit7 |
| NC-4 旧注册清除 | bit 复活（P0-C 缺陷） |
| NC-5 放宽再使能准入 | 锁存未清写被接受（面板仍黑——fault-wins 块独立有效） |

静态门 `tools/t6a_p0e_precheck.py`（先剥注释）核对逐源结构 17 条 + **6 个结构负控**
（含"清除进敏感列表"、"单锁存回归"、"可见性折回 bit7"）。`GATES_FAILED=0`。

## 4. 候选 RTL（分支 `3cdd58c`）

`regs` LF `05aaabbe → 6005c806`（CRLF `bdde768a → 31d39030`）；`spi_frame`、
`tcon_spi_top`、已验收 57 条 TB 未动；L1 TB 未改（`32a42819…`，**纠正旧报告误写
的 `f184d359`**——该前缀是改名前的版本，行尾形式与 manifest 说明见
`evidence/07_rtl_sha_old_new.txt`）。编译：RTL 与 L1 TB 均 **0/0**。
补丁 `t6a/SUGGESTED_PATCH.diff.txt`（+104/−12），`git apply --check` 通过、未应用。

## 5. 三份既有模型照常运行

时间线 81 数据行（11/20 ns 4/4 硬门）、矩阵 36 数据行、v4 状态模型 PASS——
均与 P0-D 复审的独立复算一致。

## 6. 已知限制

- 零仿真：逐源锁存的动态行为、57 条回归、E01–E20 都还没有 vsim 证据；
- 11 条异步置位路径 + `cs_n` 功能时钟的 STA 约束、PVT、物理最小脉宽未做；
- `hw_blank → blank` 连线、`tcon_top` `ST_FAULT` 退出条件改造留待 L2 前集成。

## 7. Git

- `course/microled-assignment-sim-20261112`：模型/文档/补丁同步提交
- `t6a-p0-candidate-20261119`：`3cdd58c`（RTL）+ tools/docs 同步提交
- 推送：全部传输层失败 → `REMOTE_PENDING`（`gates.txt` 记录）

**终态：`WAITING_FOR_P0E_ZERO_SIM_REVIEW`。** L1 唯一一次预算仍由您裁定。
