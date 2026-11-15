# SCAN_PIN_CONTRACT —— Scan Driver 内部数字RTL 引脚与语义合同（T4 A 段，只读）

任务 `T4-SCAN-RTL-20261115`｜日期 2026-11-15｜ModelSim 消耗 **0 次**
依据：`T3T4_SCOPE.md` §3/§4（V1.3 段 0367–0382、0482–0496）、已归档 `scan_model.v.txt`（T2B-BR 已接受）、`scan_pin_mon.v.txt`、任务书 §A/§B。

每条都标 `FROZEN` / `DERIVED` / `OPEN`。**不把推导当规格、不把行为模型当 RTL。**

---

## 1. 引脚表（每颗 Scan Driver，CHIP_ID = 0 / 1）

| 引脚 | 方向 | 宽度 | 语义 | 采样/生效边沿 | 状态 |
|---|---|---|---|---|---|
| `col_id` | 输入 | 10 | 全局列地址 0…1023；`col_id[0] = DIE_SEL`，`col_id[9:1] = LOCAL_INDEX` | 仅在 `posedge scan_stb` 采样 | `FROZEN`（段0369–0370/0482–0486） |
| `scan_stb` | 输入 | 1 | 列地址选通；**真实上升沿**锁存 | `posedge scan_stb`，且须 `blank=1` | `FROZEN`（段0487–0491/0376） |
| `blank` | 输入 | 1 | 熄灭/预充，高有效；异步安全优先 | 组合，不看时钟 | `FROZEN`（段0477–0481/0376） |
| `fault_n` | 输入 | 1 | 故障，低有效；本芯片自身必须立即关断 | 组合，不看时钟 | `FROZEN`（段0379–0380/0492–0496） |
| `reset_n` | 输入 | 1 | 异步置安全态；低 ≥1 µs | 异步下降沿 | `FROZEN`（段0442–0446） |
| `col_a[511:0]` | 输出 | 512 | 高侧选列，**独热**；本芯片本地 512 路 | 组合跟随锁存+门控 | `FROZEN`（段0367–0368） |
| `clk_ref` / `clk` | — | — | **不存在**：Scan 侧不允许用参考时钟代采 `scan_stb` | — | `FROZEN`（任务书 §C；T2B-B review finding A 已确认） |
| `FAULT_n`（开漏输出到 TCON） | 输出 | 1 | 芯片向 TCON 上报故障 | — | `OPEN` / 本轮不实现（系统级线与，见 §5） |

**观测用诊断端口（非物理接口，仅供 TB 测量，不参与任何判据的"内部状态豁免"）**：
`sel_valid`、`sel_col[9:0]`、`sel_chan[8:0]`、`err_stb_outside_blank`。TB 的期望值一律由**引脚 + 已知激励**独立算出，不读这些端口当 oracle。

## 2. 优先级（从高到低）

| 级别 | 条件 | 动作 | 状态 |
|---|---|---|---|
| 1 | `reset_n=0` | 异步清零锁存与诊断；512 路全 0 | `FROZEN` |
| 2 | `fault_n=0` | 512 路全 0，**不等下一次 `scan_stb`**，不清锁存地址 | `FROZEN`（"不清锁存"为本轮安全默认，见 §4） |
| 3 | `blank=1` | 512 路全 0（预充期不得点亮任何列） | `FROZEN`（段0376/0477） |
| 4 | 锁存地址指向**本芯片** | 本地 `col_a[local_index]=1`，其余 0 | `FROZEN` |
| 5 | 锁存地址指向**另一颗** | 本芯片 512 路全 0 | `FROZEN`（段0377–0378 跨片互锁的单芯片义务） |

门控是**组合**的：任一级有效，`col_a` 在同一个 delta 内归零，不需要任何时钟沿。

## 3. 跨片映射（两片合计 1024 列）

| 芯片 | `CHIP_ID` | 承担的全局列 | 本地通道 |
|---|---|---|---|
| Scan#0 | 0 | 偶数（`col_id[0]=0`）：0,2,4,…,1022 | `col_id[9:1]` = 0…511 |
| Scan#1 | 1 | 奇数（`col_id[0]=1`）：1,3,5,…,1023 | `col_id[9:1]` = 0…511 |

系统义务：有效显示窗口内 `popcount({chip1_col_a, chip0_col_a}) == 1`；BLANK/预充/故障/复位期间为 0。
本芯片只保证本地独热 + 片号奇偶匹配；**跨片独热是系统级验证项**（T4 双片 TB 负责证明，T5 整机再证一次）。

## 4. 非法与边界语义（逐条给出可执行判据）

| 场景 | 规定行为 | 状态 |
|---|---|---|
| `scan_stb` 上升沿落在 `blank=0` | **协议违规**：该沿不得改变任何输出；本芯片清 `armed`（512 路全 0），并置粘滞 `err_stb_outside_blank=1` 直到复位。与已接受的 `scan_model` 安全策略一致 | `DERIVED_SAFE`（任务书 §D.5 要求"按 A 段冻结的安全策略处理并检查"；`scan_model` 先例：`sel_valid=0`） |
| `col_id` 在无 `scan_stb` 时变化 | 已锁存列不变；不得产生新选通 | `FROZEN`（段0487–0491 的"仅沿锁存"推论，任务书 §C 明示） |
| `blank` 抬高 | 当前列在同一个 delta 内熄灭；`blank` 恢复后**无需新 `scan_stb`** 即可恢复原列 | `FROZEN`（段0376/0477） |
| `fault_n` 拉低 / 恢复 | 拉低立即全关；**恢复后若 blank=0 且该列仍被锁存，则恢复导通**（故障是门控，不是本地锁存） | `OPEN` → 本轮安全默认 `DERIVED_GATE_NOT_LATCH`（V1.3 未规定本地故障锁存；不制造 SPI 清故障寄存器；系统级责任边界见 §5） |
| 复位释放后未收到任何 `scan_stb` | 512 路全 0（`armed=0`） | `FROZEN`（上电全关） |
| 连续两次 `scan_stb` 同一地址 | 幂等，输出不变 | `DERIVED` |
| `scan_stb` 前后 `col_id` 建立/保持 | setup ≥ **10 ns**，hold ≥ **5 ns**（数字波形时间戳） | `FROZEN`（V1.3，`scan_pin_mon` 已按此测量）；**不代表真实 STA** |

## 5. 系统责任边界（不在 T4 数字范围）

- Scan 芯片的 `FAULT_n` 开漏上报、TCON 侧故障锁存熄屏、SPI 清故障——系统级；本轮只实现本芯片输入 `fault_n` 的硬件优先关断。
- 512 路高侧 MOS、输出电阻 8.68 Ω、非选列的泄放/放电模型——模拟/电气，`OPEN`，本轮**不建**放电模型。
- 无 CDC：Scan 侧没有内部时钟域，唯一时序是 `scan_stb` 边沿；跨片 skew、板级传输线不对本轮作任何声称。

## 6. 与旧行为替身的界线

| 项 | 旧 `scan_model`（T2B-BR，已接受） | 本轮新 `scan_driver`（可综合） |
|---|---|---|
| 输出粒度 | 只给 `sel_valid/sel_col/sel_chan` 一个标量 | **真实 512 位独热总线** |
| 综合 | 不可综合（`initial`、无 512 位输出） | 可综合（无 `#delay`、无功能 `initial`、无文件 I/O） |
| 片号 | `CHIP` 参数比较 `col_id[0]` | `CHIP_ID` 参数，同一语义 |
| 安全门控 | `sel_valid` 上体现 | **组合门控 512 位输出本身** |
| oracle 用途 | 保留为参照（不复用其内部状态写新 RTL） | 新 TB 用独立引脚 oracle `scan_exp` + 逐地址已知值双路比对 |

## 7. 由本合同导出的待办（不在本轮修改）

- `T3_LUT_VALID_OUTPUT_GATE_OPEN`：T3 `data_driver` 的 `hw_en` 只关 `col_valid/blank/fault_n`，缺 Hybrid 模式 `lut_valid` 禁止条件（复审 §4）。**T4 分支不得修改 T3 代码**；另立 T3-H 限定授权补测（见 `T4_OPEN_ITEMS.md`）。
- Pure 8-bit PWM 的 255→256 tick 位宽问题：`OPEN`，不纳入 T4 PASS。
