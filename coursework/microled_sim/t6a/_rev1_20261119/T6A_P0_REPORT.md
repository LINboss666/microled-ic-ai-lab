# T6-A 安全再使能 P0：架构收口报告（零 ModelSim）

日期：2026-11-19　预算：**本轮 0 次 vsim**（T6-A 的 2/2 已在 RUN02 用尽）
状态：`WAITING_FOR_SPI_ARCH_REVIEW`

---

## 1. 结论摘要

| 项目 | 结果 |
|---|---|
| 复审 P0 `FAULT_AUTO_REENABLE` | **确认存在**（状态模型 CE1 复现：故障撤去后 `hw_blank 1→0`） |
| 当前是否真的会误点亮 | **不会** —— `hw_blank` 未连到任何引脚；引脚级 BLANK 仍由 `tcon_top.blank` 驱动 |
| 是否已修 | **否**。只交提案与反例；`rtl/` 四个文件 SHA 与 RUN02 清单逐字节一致 |
| 提案能否落地 | 可以：`SUGGESTED_PATCH.diff.txt` 对 `tcon_spi_regs` 加 6 处、共 +17/−2 行，`git apply --check` 通过，提案版本 `vlog` 0/0 |
| 需要谁再点头 | ① 补丁批准；② 新阶段定向仿真预算（建议 1 次）；③ 顶层 `ST_FAULT` 退出策略（属 T5 代码，需另批） |

---

## 2. P0 的精确根因

```verilog
// rtl/tcon_spi_regs.v.txt（已验收的 RUN02 版本）
wire any_hw_fault = |hw_fault;
assign hw_blank   = blank_r | (!en) | any_hw_fault;   // ← 只看"当前"故障
...
fault_status <= n_fault;                              // ← 历史故障是粘滞的
```

`hw_blank` 少了两个输入：**锁存的历史故障** 与 **Host 再使能许可**。
所以 `hw_fault` 一撤，`hw_blank` 立刻回 0，与 V1.3 段0908/0912/0965 冲突。

CE1 状态表（`tools/t6a_p0_rearm_check.py` 实跑）：

```
step                                en blank hw_fault latched armed hw_blank
A display on                         1   0      0         0      1      0
B fault active (3 edges)             1   0      1         1      0      1
C fault gone, no W1C, no re-enable   1   0      0         1      0      0   ← 违规
```

---

## 3. 为什么"现在还没有一颗芯片会误亮"

逐网核对了 T5 已验收的 `tcon_top.v.txt`：

```verilog
wire flt = (state == ST_FAULT);        // 只有 !reset_n 能退出
assign blank = blank_seq || !safe || flt || !act || (act && !disp_ok);
```

- 引脚级 `blank` 只由这个表达式驱动；
- `tcon_top` 里**没有** SPI 实例，`tcon_spi_top` 是独立顶层；
- 所以 `hw_blank` 目前是**没有负载的输出脚**。

但同时发现一个反向问题：**顶层 `ST_FAULT` 只能靠复位退出**，
比规格更严（段0912 要求 Host 清故障后可再使能）。集成时必须一并调整，
否则"Host 再使能"永远做不到。详见 `SAFETY_OWNERSHIP.md` §1.1 / §3 的 R3。

---

## 4. 提案（不应用）

```verilog
localparam [10:0] DISP_FAULT_MASK = 11'h7FF & ~11'h100;   // 除 ERR_REG
wire disp_fault = |(fault_status & DISP_FAULT_MASK);
reg  disp_armed;                                          // Host 再使能许可

assign hw_blank = blank_r | (!en) | any_hw_fault | (!disp_armed) | disp_fault;
```

- `disp_armed` 复位 0；只由一次"通过全部检查的 CTRL unblank 写"置 1；
  复位 / 当前故障 / 锁存显示故障 / EN=0 / BLANK=1 都会清 0；
- `ERR_REG`（bit8）**排除**在 `disp_fault` 之外——配置访问错误不该熄屏；
- 清零赋值放在 always 块末尾，故障永远压过同拍的置位。

**为什么不是"把 fault_status 直接 OR 进 hw_blank"**：那样只能做到"故障锁存期不亮"，
W1C 清掉之后权限又回来了（CE2 反例）。复审的提醒正是这一点，所以必须引入
"再使能许可"这个显式状态，而不是一个组合项。

---

## 5. 零仿真证据

| 文件 | 内容 | 结果 |
|---|---|---|
| `tools/t6a_p0_rearm_check.py` | 状态模型：当前门控 vs 提案门控，跑 CE1–CE5 | 当前门控 CE1 = **VIOLATION**；提案 CE1–CE5 全过 |
| 同上 · 负控 | 删再使能锁存 → CE2 破；两把锁全删 → CE1 破 | 两个负控都被抓到 |
| `t6a/SUGGESTED_PATCH.diff.txt` | +17 / −2 行，仅 `tcon_spi_regs` | `git apply --check` 通过，**未应用** |
| 提案版本 `vlog` | 与 `spi_frame` / `tcon_spi_top` 一起编译 | 0 errors / 0 warnings |

CE 结论（提案门控）：

```
CE1 故障撤去、无 Host 动作        hw_blank=1  SAFE
CE2 W1C 清状态、不再使能          hw_blank=1  SAFE   （当前门控此处为 0，也违规）
CE3 故障中写 CTRL=EN1,BLANK0      hw_blank=1  写被拒
CE4 清状态 + 显式再使能           hw_blank=0  允许恢复
CE5 int_en=0 / 读 / 坏帧          hw_blank=1  无法绕过
```

---

## 6. 本轮明确没有做的事

1. **没有跑 ModelSim**（预算 2/2 已用尽，也不占新预算）；
2. **没有修改任何已验收 RTL**——四个文件 SHA 与 RUN02 清单一致：
   `spi_frame 7d9465a6` / `tcon_spi_regs bdde768a` / `tcon_spi_top 07566c5b` / `tb a5cf32a1`；
3. **没有把 CE 任何一条登记为 PASS**——它们只是计划；
4. `STATUS_VISIBILITY.md` 里的错误可见性只有方案，`mb_lost` / `mb_badlen`
   **仍然不可经 SPI 读回**（P1-A 保持 OPEN）；
5. CDC 仍是功能级；`cs_n` 作为功能时钟的 STA 约束、PVT 余量均未做（P1-C 保持 OPEN）；
6. T5 的 56/56 结论不受影响，但也**没有**"带 SPI 的五芯片联合 PASS"（P1-D 保持 OPEN）。

---

## 7. 下一步建议

1. 评审 `SUGGESTED_PATCH.diff.txt` + `FAULT_REARM_PROTOCOL.md`；
2. 批准后，申请**新阶段定向预算 1 次**跑 `CE_TEST_PLAN.md` 的 CE1–CE6（不占 T6-A 的两次）；
3. 集成阶段按 `SAFETY_OWNERSHIP.md` 的 R1–R3 改顶层 `ST_FAULT` 退出条件，
   并做"带 SPI 的五芯片"一次联合验证（需另批预算）。

**终态：`WAITING_FOR_SPI_ARCH_REVIEW`。不自签 `T6A_PASS`，不自签 `P0_CLOSED`。**
