# 安全闸门归属（SAFETY_OWNERSHIP）

日期：2026-11-19　范围：T6-A `FAULT_AUTO_REENABLE = OPEN_P0` 的架构核对（**零 ModelSim**）

---

## 0. 一句话结论

**今天没有任何一条路径能让 `tcon_spi_regs.hw_blank` 单独点亮像素** —— 它根本没有连到引脚。
但**一旦集成时把它当作最终 BLANK**，复审给出的反例就成立。同时，已验收的 `tcon_top`
用"只有复位才能退出"的 `flt` 兜底，是**安全但过严**（规格要求 Host 清故障后可再使能，
不需要整片复位）。所以收口动作是：**把"再使能许可"明确放到 SPI 寄存器块，并规定顶层不得
把 `hw_blank` 当作唯一的关断源**。

---

## 1. 现状：两条独立的安全路径

### 1.1 已验收的 T5 顶层 `tcon_top.v.txt`（SHA `…`，56/56 那版）

```verilog
localparam [1:0] ST_FAULT = 2'd3;             // latched safe state
wire flt = (state == ST_FAULT);
wire safe = mode_en && rx_ready && fault_n;

assign blank = blank_seq || !safe || flt || !act || (act && !disp_ok);

ST_ACTIVE: if (fault_evt) state <= ST_FAULT;
default:                  state <= ST_FAULT;   // latched: reset only
```

| 事实 | 含义 |
|---|---|
| `flt` 一旦置位**只有 `!reset_n` 能退出**（`default` 分支自锁） | 故障后不会自动恢复 —— **这条路径是安全的** |
| `blank` 是**引脚级** BLANK 的唯一表达式 | 顶层才是"谁最后释放 BLANK"的答案 |
| `blank` 里已经含 `!act`、`!disp_ok`（帧/预充） | 帧合法性与预充是顶层的第二把钥匙 |
| `fault_n` 是**引脚**（开漏线与时） | 硬件故障的入口在顶层，不在 SPI 块 |

**副作用**：`flt` 只能靠复位退出，而 V1.3 段0912 要求 OV/OT 恢复后
"人工/**Host 清除再使能**"，段0965 要求"清状态不自动恢复显示"——
顶层的策略比规格**更严**（需要整片复位而不是一次 SPI 事务），
集成时必须统一，否则"Host 再使能"永远做不到。

### 1.2 T6-A 新块 `tcon_spi_regs.v.txt`（RUN02 57/57 那版）

```verilog
wire any_hw_fault = |hw_fault;
assign hw_blank   = blank_r | (!en) | any_hw_fault;
```

| 事实 | 含义 |
|---|---|
| `hw_blank` 只在 `tcon_spi_top` 里作为 **output** 存在 | **没有连到 `tcon_top.blank`，也没有连到任何引脚** |
| `tcon_top` 里没有 SPI 实例，`tcon_spi_regs` 里没有 `blank_seq` | 两者目前是**并联的两套**，不是串联 |
| `fault_status` 对历史 `hw_fault` 粘滞，但 `hw_blank` **不查它** | 这就是复审的 P0 反例 |

---

## 2. 逐网接线：为什么现在"不会真的点亮"

```
              ┌────────────────────────────┐
  fault_n ───►│ tcon_top                   │
  (引脚)      │  state == ST_FAULT  ──► flt│──┐
              │  safe / act / disp_ok      │  ├──► blank (引脚)  ──► 驱动阵列
              └────────────────────────────┘  │
                                              │
              ┌────────────────────────────┐  │
  4 线 SPI ──►│ tcon_spi_top               │  │
              │  u_regs.hw_blank ──► 输出脚 │  ✗  未连接（T6-A 未集成）
              └────────────────────────────┘
```

- `tcon_spi_top` 是**独立顶层**，只用于 T6-A 单块验证；
- T5 的 `tcon_top` 没有 SPI 端口，T6 也没有把 `hw_blank` 接进去；
- 因此当前 RTL 里 `hw_blank` **不驱动任何发光路径**，P0 是**潜伏缺陷**，
  不是"现在芯片就会误点亮"。

**但**：`tcon_spi_top` 把 `hw_blank` 注释成"what the panel really sees"，
`gates.txt` 也称它是最终关断信号。只要集成者按这个注释接线，反例立刻变成真实缺陷。
**必须在集成前把它写成合同，而不是靠注释。**

---

## 3. 集成时必须满足的接线规则（提案）

```
blank_pin = tcon_blank_frame_level  ||  !spi_display_permit
            └── 帧/预充/标签（tcon_top，已有）      └── Host 许可（tcon_spi_regs，新增）

spi_display_permit = en && !blank_r && disp_armed && !disp_fault
```

三条硬规则：

| # | 规则 | 理由 |
|---|---|---|
| R1 | **`hw_blank` 不得是唯一关断源**：引脚 BLANK 必须是"顶层帧许可"与"SPI 许可"的 **OR** | 任一侧失效另一侧仍能关断；这也是复审要求的"证明它不可独自开灯" |
| R2 | `spi_display_permit` 里必须含**锁存的再使能位** `disp_armed`，不能是 `!hw_fault` 这种纯组合 | 故障消失 ≠ Host 许可；见 CE1/CE2 |
| R3 | 顶层的 `ST_FAULT` 退出条件要改成"**Host 显式再使能 + 重新预充 + 合法帧**"，而不是"只能复位" | 否则 V1.3 段0912 的"Host 清除再使能"无法实现 |

R3 是一条**顶层**改动，属于 T5 已验收代码，本轮**不动**，只登记为集成阶段的必要变更。

---

## 4. 三种可选归属，及推荐

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A | 只在 `tcon_spi_regs` 里加再使能锁存（本轮提案） | 改动最小、只碰 T6 新模块、可先验证 | 顶层 `flt` 仍需改 R3，否则故障后要整片复位 | **推荐**（先做 A，集成时做 R3） |
| B | 把 `hw_blank` 直接 OR 进 `tcon_top.blank`，不改 `flt` | 集成最快 | 故障后必须整片复位才能恢复显示，与规格不符；且 `hw_blank` 仍无锁存时 P0 直接生效 | 不推荐 |
| C | 再使能逻辑全部搬到 `tcon_top` | 单一权威 | 要动已验收的 T5 核心，回归面大 | 不推荐（除非重开 T5 预算） |

---

## 5. 上电与复位初值（与规格对齐）

| 信号 | 复位值 | 依据 |
|---|---|---|
| `en` | 0 | 段0903 "所有 LED 输出 OFF；BLANK 有效" |
| `blank_r` | 1 | 同上；`CTRL` 复位值 0x0000_0002 |
| `fault_status` | 0 | §13 复位列 |
| **`disp_armed`（提案）** | **0** | 上电不允许发光，必须走完段0810 的"SPI 配置与读回 → LUT/电流校准准入 → 缓存预充 → EN 与同步有效 → 撤消 BLANK" |

`disp_armed=0` 与 `en=0` 是**两把独立的锁**：前者是"Host 授权过"，后者是"当前使能中"。
只有两者同时成立、且无当前/历史显示故障、且顶层帧许可成立，才可能发光。

---

## 6. 本轮证据

- `tools/t6a_p0_rearm_check.py` 的 CE1 表：当前表达式在"故障撤去、Host 无动作"时
  `hw_blank 1 → 0`，**反例已确认**；
- 同一脚本对提案门控跑 CE1–CE5 全过，两个负控（删再使能锁存 / 删两把锁）都能被抓到；
- RTL 一字未改：`rtl/` 工作树 0 处修改，`SUGGESTED_PATCH.diff.txt` 只经 `git apply --check`
  验证可干净应用，**未应用**。

**结论：`FAULT_AUTO_REENABLE` 的责任归属 = SPI 寄存器块（许可）+ TCON 顶层（帧/预充/锁存），
两者必须 AND 后才允许发光，任一方都不得单独放行。**
