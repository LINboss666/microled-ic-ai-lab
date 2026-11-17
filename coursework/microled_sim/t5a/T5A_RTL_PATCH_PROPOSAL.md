# T5A_RTL_PATCH_PROPOSAL —— 两个 P0 的最小补丁提案（**均未应用**）

日期 2026-11-17｜T5-A 授权为零仿真：本文件只有提案与影响评估。
**当前工作树中的 RTL 仍是 T3-H 验收版本**（`data_driver` SHA `4ea897deebe39b6437acb40821b035bd98526f78f8e7a5da03abda2a1911c8be`），
`scan_driver` 仍是 T4 版本（`6ee3ad38…2229a4`）。任何补丁都必须单独审批 + 单独授权验证，
不得把改后的文件冒充"已通过 T3/T4"的版本。

---

## 补丁 P-1：Data 的 V1.3 自定界接收（对应 `DATA_INPUT_PROTOCOL = OPEN_P0`）

**动机**：V1.3 段 0548 规定 Data 自行以 LATCH 定界、数满 384 字节后停写；当前 RTL 依赖
`din_valid` 决定"这一拍是不是有效字节"，而这个端口在 V1.3 引脚表里没有对应物。

```verilog
 module data_driver #(
     parameter integer NCH     = 384,
     parameter integer PWM_MAX = 63,
     parameter integer CNTW    = 8,
+    parameter integer USE_DIN_VALID = 1   // 1 = current behaviour (T3 accepted)
+                                          // 0 = V1.3 self-delimited byte window
 ) (
...
-            if (win_open && din_valid) begin
+            wire byte_valid = USE_DIN_VALID ? din_valid : (win_open && (wcnt < NCH));
+            if (win_open && byte_valid) begin
```

**影响评估**

| 维度 | 评估 |
|---|---|
| 默认值 | `USE_DIN_VALID=1` ⇒ 现有 T3/T3-H 行为**逐位不变**（52+17 条断言不受影响） |
| 引脚 | **不新增任何端口**；`din_valid` 保留，`=0` 时被忽略 |
| 状态 | 不新增寄存器；`byte_valid` 是组合表达式（`wcnt` 已在路径上） |
| 时序 | `ch_en` 路径不变（本补丁不碰输出门控）；装载路径多一个二选一 |
| 385 字节 | `=0` 时第 385 沿因 `wcnt==NCH` 被丢弃，`ovf` 不会置位（系统不可达，见合同 §5） |
| 回归 | `=1`：无需重跑（默认路径未变）；`=0`：需一次**定向**运行证明 384 沿定界 + 385 沿丢弃 |

**风险**：`=0` 时若 TCON 真的少发（<384），Data 会把下一列的字节当成本列的 —— 但这在真实链路
不会发生（TCON 恒发 384），且属于"上游违约"，应在 TCON RX 侧检测。此风险写入合同。

---

## 补丁 P-2：COMMIT 作废显示 bank（对应 `LUT_COMMIT_RELOAD_INTERLOCK = OPEN_P0`）

**动机**：`lut_valid` 只能证明"当前活跃 LUT 提交过"，不能证明"屏幕上的这一列是用它算的"。

```verilog
             if (cmt_pend && cmt_ok) begin
                 cmt_pend <= 1'b0;
                 lut_bank <= ~lut_bank;
+                // T5-A: the display bank still belongs to the PREVIOUS mapping.
+                // Force one "load + LATCH commit" with the new LUT before any
+                // channel may conduct again. Chip-self-guaranteed, no new state.
+                col_valid <= 1'b0;
                 if (lut_bank) ok_a <= 1'b1;
                 else          ok_b <= 1'b1;
```

**影响评估**

| 维度 | 评估 |
|---|---|
| 引脚/状态 | 无新端口、无新寄存器（复用 `col_valid`） |
| 可见行为 | 换表后必须重新装载一列才会再亮 → 换表期间多黑 1–2 列（换表本来在 BLANK/SAFE 内） |
| T3 52 条 | 预期无影响：唯一的 COMMIT 在 P1（尚无任何列装载，`col_valid` 本就为 0） |
| T3-H 17 条 | 预期无影响：B2 是"COMMIT 后重新装载"，`col_valid` 会被重新置 1 |
| 需补的定向用例 | ① 开机 COMMIT 不重载 → 全暗；② A→B 换表旧列 → 全暗；④ FAULT 挂起 COMMIT 恢复 → 仍全暗直到重载 |
| 时序 | `col_valid` 已在 `ch_en` 路径上，无新增组合级 |

---

## 不提议的改动（明确排除）

- 不新增物理引脚（含把 `load_active` 引出为 `VALID`）。
- 不改 100 MHz / 50 MHz / 1024 列 / 768 行 / LUT 码表 / 窗口时序常量。
- 不实现 Pure 8-bit PWM 位宽问题、`PAM_CFG=01`、SPI 寄存器堆。
- 不改 `data_model`（oracle）与任何既有断言阈值。

## 审批与后续

1. 审批 P-1 的**参数名与默认值**（默认 1 是关键：保证已验收证据不失效）。
2. 审批 P-2 语义：是否接受"换表后必须重载一列才恢复显示"（若不可接受，改用 epoch 标签方案，
   代价是每 bank 多 1 bit 状态）。
3. 两项都批准后，建议**合并成一次**限定运行（T3-H2）覆盖：`=0` 定界、385 沿丢弃、
   ①/②/④ 过渡序列，并重跑 52+17 条回归；预算另批，不占 T5 正式联仿。
