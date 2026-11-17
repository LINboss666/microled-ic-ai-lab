# T5_LUT_EPOCH_INTERLOCK —— COMMIT 与显示 bank 的归属（T5-A / P0-2）

日期 2026-11-17｜性质：**只读推导 + 最小修改提案**（未应用任何 RTL 改动；T5-A 为零 ModelSim）

---

## 1. 从 RTL 重新推导（不是复述复审结论）

`rtl/data_driver.v.txt`（T3-H 版本 `4ea897de…11c8be`）：

| 事实 | 代码位置 |
|---|---|
| 映射在**装载时**就按当时的活跃 LUT 算好 | `wire [8:0] lut_q = lut_bank ? lut_b[...] : lut_a[...]`；`map_load[wcnt] <= map_now` |
| 显示 bank 在 LATCH 上升沿整体复制 | `map_disp[i] <= map_load[i]`（仅当 `wcnt==NCH && !ovf`） |
| COMMIT 只翻银行与 `ok_*`，**不碰** `col_valid` / `map_disp` | `cmt_pend && cmt_ok` 分支只改 `lut_bank/ok_a/ok_b/mask_*` |
| 新门控只问"当前活跃 bank 有没有提交过" | `lut_ok = !cfg_hybrid \|\| lut_valid` |

⇒ `lut_valid` 是**配置**的有效性，不是**显示数据**与配置的**版本一致性**。
两者之间没有 epoch / 代数关联，芯片无从判断"屏幕上这一列是按新表算的还是旧表算的"。

## 2. 四条独立过渡序列（当前行为）

| # | 序列 | 当前结果 | 风险 |
|---|---|---|---|
| ① | 开机 LUT 无效 → 已存完整列（`col_valid=1`，映射=X/旧值）→ COMMIT（`lut_valid=1`）→ **不重新装载** → 撤 BLANK | `hw_en=1`，输出按**未提交时算出的映射**导通；首次开机时该映射是 X | **P0**：既未重新装载、又已"合法"，四态下还可能输出 X |
| ② | 有效表 A → 已显示某列 → COMMIT 新表 B → 旧列继续显示 | `col_valid` 保持 1，`lut_valid` 保持 1，输出仍按 **A** 的映射 | **P0**：灰阶静默错误（画面不报错、数值错） |
| ③ | COMMIT → **重新装载**合法列 → LATCH 提交 → 显示 | 映射来自新表，正确 | 安全（T3-H B2 实测过这一条） |
| ④ | FAULT/RESET 期间申请/进行 COMMIT | `safe_cfg = fault_n && blank && !win_open`；FAULT 期间 `cmt_ok=0`，`cmt_pend` **保持挂起**，等安全后自动提交；RESET 清 `cmt_pend` 与 `ok_*` | 挂起的 COMMIT 会在故障恢复后生效 → 若此时旧列仍在显示，落入序列 ①/② |

结论：**①②可达，③安全，④会把①/②延后触发**。当前 B1/B2 的 PASS 不覆盖①②，这与复审裁定一致。

## 3. 最小硬件安全语义（三选一）

| 方案 | 实现 | 芯片自保证？ | 代价 |
|---|---|---|---|
| **(i) COMMIT 作废显示 bank（推荐）** | COMMIT 成功那一拍 `col_valid <= 1'b0`（同一 always 块内多一条赋值） | ✅ | 每次换表后画面要等"新 LUT 装载 + LATCH 提交"的一个列周期才恢复；需接受换表期间黑屏 |
| (ii) 显示 bank 带 epoch 标签 | 增加 1 bit `disp_epoch`（提交列时锁存当前 `lut_epoch`），输出许可要求二者相等 | ✅ | 多 2 bit 状态 + 比较；能区分"同表重复提交"但与 (i) 的可见效果几乎相同 |
| (iii) 主机保持 BLANK 直到重载 | 由 TCON/SPI 强制顺序 | ❌ **当前不成立**：TCON **没有** LUT 提交端口（`cfg_lut_*` 是 Data 侧端口，SPI 未实现），无法强制 | 合同无法证明 → 只能标 OPEN |

**推荐 (i)**：一行、无新时钟域、可由芯片自身保证，且与 V1.3 段 0692–0705"LUT 只在 SAFE 阶段更换"的用法一致（换表本来就在 BLANK 内）。

## 4. 最小补丁（**未应用**）

```verilog
// in the `if (cmt_pend && cmt_ok) begin ... end` branch
    col_valid <= 1'b0;   // T5-A: the display bank belongs to the PREVIOUS mapping
```

只加这一行。`map_disp` 不清（省面积），但 `disp_ok=0` 已使输出全关；下一个"装载→LATCH 提交"的列
自然恢复 `col_valid=1`，且其映射由新活跃 LUT 算出 ⇒ 版本一致。

## 5. 回归影响清单（静态评估，需一次定向运行确认）

| 回归项 | 影响 | 说明 |
|---|---|---|
| T3 52 条（D01–D42） | **预期无影响** | 唯一 COMMIT 在 P1（此时还没有任何列装载，`col_valid` 本来就是 0）；P2–P6 无 COMMIT |
| T3-H 17 条（D43–D59） | **预期无影响** | B2 是 COMMIT 后**重新装载**，`col_valid` 会被新列重新置 1；B1 不涉及 COMMIT |
| 窗口普查 D42 | 无影响 | COMMIT 不动装载窗口 |
| 新增定向用例（审批后） | 必须补 | ① 开机 COMMIT 不重载 → 必须全暗；② A→B 换表 → 必须全暗直到重载；④ FAULT 挂起 COMMIT 恢复后 → 仍须全暗直到重载 |
| 时序/面积 | 极小 | 一条寄存器清零赋值；无新组合路径进入 `ch_en`（`col_valid` 本来就在路径上） |

## 6. 状态

- `LUT_COMMIT_RELOAD_INTERLOCK = OPEN_P0`（本文件给出方案 (i) 与回归清单，**未改 RTL**）
- 需要审批：是否采纳 (i)；采纳后需要一次**限定定向仿真**（不属于 T5 正式联仿预算）来证 ①②④。
- 在此之前，T5 正式联仿**不得**启动；也不得用"TB 按顺序操作"替代芯片自保证。
