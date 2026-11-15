# T4_TEST_PLAN —— 测试向量表与逐项判据（运行前写定）

日期 2026-11-15｜本轮 ModelSim 已用 **0** 次（本文件写于首次 vsim 之前）
判据来源：`SCAN_PIN_CONTRACT.md` + 任务书 §D。**先写判据，后看波形**，防止拟合。

对象：`rtl/scan_driver.v` × 2（CHIP_ID=0/1），oracle = `rtl/scan_exp.v` × 2（纯引脚推导）。
断言实现：`tb/tcon_t4_tb.sv`，全部由 `chk()` 记名，共 **42** 条，每条执行一次，`FLOOR=42`。

---

## 1. 激励时间基

| 项 | 值 | 说明 |
|---|---|---|
| 参考时钟 | 10 ns（100 MHz） | **仅作测量网格**，不是 Scan 引脚；D38 专门证明锁存不依赖它 |
| `scan_stb` 脉宽 | 25 ns 高 / ≥10 ns 低 | 上升沿是唯一锁存事件 |
| 地址建立 | ≥ 25 ns（`col_id` 变化 → 上升沿） | 判据 ≥10 ns |
| 地址保持 | ≥ 40 ns（上升沿 → 下次 `col_id` 变化） | 判据 ≥5 ns |
| 显示窗 | `blank` 拉低后 30 ns 采样 | 组合门控已稳定 |

## 2. 测试向量表

| 阶段 | 向量 | 激励 | 期望 |
|---|---|---|---|
| P0 | 复位 | `reset_n=0`，`blank=1`，`fault_n=1`，200 ns | 两片 512 位全 0；诊断清零 |
| P0 | 复位释放 | `reset_n=1`，`blank=0`，无 STB | 仍全 0（未收到任何 STB） |
| P1 | 边界列 | 全局列 0 / 1 / 2 / 3 / 1022 / 1023，逐列合法 STB + 显示窗 | 列0→chip0 bit0；列1→chip1 bit0；列2→chip0 bit1；列3→chip1 bit1；列1022→chip0 bit511；列1023→chip1 bit511；另一片全 0；全局 popcount=1 |
| P2 | **1024 列遍历** | `addr = 0..1023`，每地址：`blank=1` → 建址 25 ns → STB 上升 → 30 ns 显示窗 → 采样 → `blank=1` 后 1 ns 查熄灭 | 每地址 bit-exact：`chip[addr[0]][addr/2]` 为 1，另一片全 0；全局 popcount=1；`blank` 抬高 1 ns 内全 0 |
| P3 | 锁存稳定性 | 显示列 2 后，无 STB 改 `col_id`→40 | 输出仍为 chip0 bit1；无新选通事件 |
| P3 | 新 STB 才换列 | 对 40 发合法 STB | chip0 bit20 |
| P3 | 多次改址 | 无 STB 连改 100/200/300 | 仍 chip0 bit20 |
| P3 | 跨片清列 | 对列 3 发合法 STB | chip1 bit1；chip0 全 0 |
| P4 | BLANK 即时关断 | 显示中 `blank=1`，1 ns 后采样 | 全 0；全程无"BLANK 高时输出非 0"样本 |
| P4 | BLANK 恢复 | `blank=0`，**不发 STB** | 恢复原列 chip1 bit1 |
| P4 | FAULT 即时关断 | `fault_n=0`，1 ns 后采样 | 全 0；全程无"FAULT 时输出非 0"样本 |
| P4 | FAULT 恢复 | `fault_n=1`，不发 STB | 恢复原列（`DERIVED_GATE_NOT_LATCH` 安全默认） |
| P5 | 非法 STB（BLANK=0） | 显示中改址 8 后对 `blank=0` 发 STB | 两片 1 ns 内全 0；两片 `err_stb_outside_blank=1` |
| P5 | 违规后恢复 | `blank=1` 对列 16 发合法 STB | chip0 bit8；`err` 保持 1（粘滞到复位） |
| P6 | 引脚时序 | `scan_pin_mon` 全程测量 | setup_min ≥10 ns；hold_min ≥5 ns；BLANK 外 STB 恰 1 次（故意） |
| P6 | 非时钟采样证明 | STB 上升沿放在参考时钟 posedge 后 6 ns，+2 ns 采样 `sel_col` | 已等于新地址（时钟采样实现在 +2 ns 仍为旧值） |
| P7 | 异步复位 | 显示中 `reset_n=0`，1 ns 后采样 | 全 0；释放后仍全 0（需新 STB） |

## 3. 逐项判据（42 条）

| ID | 判据 |
|---|---|
| D01/D02 | 复位期间 chip0/chip1 输出 == 0 |
| D03 | 复位期间 `sel_valid`×2 == 0 且 `err`×2 == 0 |
| D04 | 复位释放、无 STB、`blank=0`：全局仍 0 |
| D05–D10 | 列 0/1/2/3/1022/1023 的片选与本地 bit 精确正确，另一片全 0 |
| D11 | 列2→列3 切换后无残留（chip0 全 0，全局 popcount==1） |
| D12 | 遍历计数 == 1024（**非空洞**） |
| D13 | 1024 地址逐址与"循环变量独立算出的期望"零失配 |
| D14 | 每地址本地 bit 精确（`c[addr/2]` 为 1） |
| D15 | 两片各 512 次选列 |
| D16 | 1024 个显示窗全部全局 popcount == 1（`zero_or_multi_hot == 0`） |
| D17 | 非目标芯片 1024 次全 0 |
| D18 | 1024 次 `blank` 抬高，1 ns 内全 0 |
| D19 | 引脚监视器数到的 STB 上升沿数 == 计划数（无隐藏/多余选通） |
| D20/D21 | 无 STB 改址：列不变、无新选通事件 |
| D22/D23 | 新 STB 才换列；多次改址仍保持锁存 |
| D24 | 对另一片发 STB：本片全 0 |
| D25/D26 | BLANK 抬高 1 ns 内全 0；全程 0 违例样本 |
| D27 | BLANK 释放无需新 STB 即恢复原列 |
| D28/D29 | FAULT 拉低 1 ns 内全 0；全程 0 违例样本 |
| D30 | FAULT 释放恢复原列（已登记的 OPEN 安全默认） |
| D31/D32 | 非法 STB：1 ns 内全局 0，且两片协议错误位置 1 |
| D33/D34 | 非法后合法 STB 可恢复；`err` 粘滞到复位 |
| D35/D36 | setup_min ≥ 10 ns、hold_min ≥ 5 ns（数字时间戳，**非 STA**） |
| D37 | BLANK 外 STB 恰 1 次（= 故意注入） |
| D38 | STB 沿后 2 ns 已更新（证明锁存不由 100 MHz 参考时钟采样） |
| D39 | 诊断 `sel_valid` 与 512 位输出一致（全程 0 失配）+ 显示窗 chip0 有效、chip1 无效 |
| D40/D41 | 异步复位 1 ns 内全 0；释放后需新 STB |
| D42 | 监视器采样数 > 15000（非空洞） |

## 4. 必打印 census（防"一个 PASS 掩盖跳过的选列"）

```
COURSE_T4_STROBES expected=<计划 STB> observed=<引脚实测 STB> checked=<逐址比较数=1024>
                  zero_or_multi_hot=<显示窗非独热样本=0> cov_chip0=<512> cov_chip1=<512>
COURSE_T4_MONITOR samples=<> oracle_mismatch=<> onehot_samples=<> diag_sel_bad=<> blank_on=0 fault_on=0
COURSE_T4_TIMING  setup_min_ps=<> hold_min_ps=<> setup_bad=<> hold_bad=<>
```

## 5. 预算与停止条件

- 正式 vsim 预算 **2 次**；本轮**只跑第 1 次**（双片联合单元验证）。
- 第 1 次任何 FAIL → 立即停止、原样保存证据、送审，**不自动跑第 2 次**。
- 编译预检（vlog only）与静态脚本不计次数。
