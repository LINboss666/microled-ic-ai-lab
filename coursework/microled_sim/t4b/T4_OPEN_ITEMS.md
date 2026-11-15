# T4 阶段的未决项登记（不在本轮修改任何 TCON/T3 代码）

日期 2026-11-15｜依据：T3 RUN05 复审报告 §4–§6、任务书 §G

---

## 1. `T3_LUT_VALID_OUTPUT_GATE_OPEN`（P0，进 T5 前必须先闭环）

**性质**：复审方的**代码静态发现**，不是 RUN05 仿真 FAIL，也不在本轮 T4 范围内修复（任务书 §G 明令不得在 T4 分支改 T3 代码）。

**缺口**：`rtl/data_driver.v.txt`

- 复位时 `ok_a=ok_b=0`、`lut_valid=0`，但 `lut_a/lut_b` 内容未初始化；
- `cfg_hybrid=1` 时仍执行 `lut_q = lut_{a,b}[din]`（即便 `lut_valid=0`）；
- 列装载只校验 384 字节数与溢出即可令 `col_valid=1`，**不要求 LUT 有效**；
- 输出许可 `hw_en = col_valid && !blank && fault_n`，**缺 `lut_valid`**。

**后果**：先收满一列、但 LUT 尚未 COMMIT 的窗口内，输出不被设计保证为 0（映射值还可能是未初始化态）。
与 `T3T4_SCOPE.md` §4"`LUT_VALID=0` 前不可显示"不符。

**建议的最小修复（待独立限定授权，不在本轮做）**：Hybrid 模式输出许可加 `lut_valid`；补一条定向测试"未提交 LUT + 完整合法列 + BLANK=0 ⇒ 恒零导通"，且不得依赖仿真 X 值偶然使断言通过；再补"有效提交后恢复显示"。

**状态**：`OPEN_P0`，需 `T3-H` 单独立项、限定一次仿真授权。

## 2. Pure 8-bit PWM 的 255→256 tick 位宽问题（OPEN，不纳入 T4 PASS）

`CNTW=8` 与 `PWM_MAX+1` 在 Pure 模式下满码需覆盖 256 tick，存在位宽/溢出风险；T3 未跑 Pure 模式。维持 `OPEN`。

## 3. PAM_CFG=01 四档模式（OPEN）

无冻结规格；`PAM=00` 八档数字侧已验，四档对照未冻结。

## 4. 模拟/电气类（不是数字 PASS 能覆盖的）

512 路高侧 MOS、8.68 Ω 输出上限、非选列放电、阵列 RC、光学标定、PVT、版图 DRC/LVS/PEX —— 全部 `OPEN`。

## 5. 时序/跨域类

无 CDC 签核、无 STA、无毛刺/亚稳态分析；`BLANK` 的异步组合关断路径登记为 `OPEN_ASYNC_BLANK`。
T4 的 setup/hold 是**数字波形时间戳**，不冒充 STA。

## 6. 系统级

`FAULT_n` 开漏线与到 TCON、TCON 侧故障锁存熄屏、SPI 清故障寄存器 —— 未实现，属 T5/系统阶段。
