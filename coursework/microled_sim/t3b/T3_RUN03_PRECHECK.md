# T3 运行前离线预检 —— DCLK 采样口径与源码一致性

**任务** `TCON-T3-RUN03-20261115` ｜ 授权：**1 次** ModelSim（尚未使用）
**复审指出的风险**：`din` 由 `sent` 组合生成，`sent` 在 `posedge dclk` 用 NBA 自增；
被测 RTL 在 `posedge dclk` 采**沿前值**，`data_model` 在 `posedge dclk` **后 1 ns** 采**沿后值**
→ 两个模型可能读到相邻两个字节。

---

## 1. 复核结论：这个风险是真实存在的，而且能解释 run02 的 D14/D15

### 1.1 旧 TB 的时序

```
t = k*20ns        posedge dclk
                    ├─ DUT  在沿前值采样  → din(sent = k)      ≡ byte[k]
                    ├─ TB   sent <= sent+1 （NBA，沿后才生效）
t = k*20ns + 1ns  ├─ data_model 采样 → din(sent = k+1) ≡ byte[k+1]
t = k*20ns + 10ns    negedge dclk（无采样）
```

**DUT 得到 byte[k]，oracle 得到 byte[k+1]** —— 恒定错开一个字节。

### 1.2 与 run02 原始日志对得上

| 观测 | 旧 TB 的预测 |
|---|---|
| `D14_col0_oracle_tag_col` PASS（or_col=0） | col0 的 byte0=0、byte1={0,frame}；错一字节后 cap[0]=byte1、cap[1]=byte2，解出 {byte2[7:6], byte1} = 0 → **碰巧**等于 0 |
| `D14_col1_oracle_tag_col` FAIL | col1 时 cap[0]=byte1=0x01、cap[1]=byte2 → 解出 ≠ 1 ✓ |
| `D14_col2_oracle_tag_col` FAIL | 同理 ✓ |
| `D15_col1/col2_oracle_not_corrupt` FAIL | 错位后 oracle 用**上一字节**当列号去核对图案，必然 corrupt ✓ |
| DUT 只收 383 字节 | 这是另一个独立缺陷（F2，同一块内 NBA 覆盖），与此无关 |

所以复审的判断成立：**D14/D15 对列 1/列 2 的失败不能用 383 字节解释，是测试台采样口径问题。**

---

## 2. 修法（只改测试激励/监视口径，不动任何判据）

让**所有 DUT 输入在 DCLK 上升沿之前至少 5 ns 就已稳定，并在沿后 1 ns 仍保持不变**。
这样"沿前采样"和"沿后+1 ns 采样"读到同一个值。

| 信号 | 旧驱动 | 新驱动 | 沿前建立 | 沿后保持 |
|---|---|---|---|---|
| `blank / latch / pwm_start / pwm_tick` | `cyc` 组合，随 posedge clk 变 | 在 **negedge clk** 寄存 | 5 ns | 5 ns |
| `din / din_valid`（`win`/`sent`） | `sent` 在 posedge dclk 自增 | `win`/`sent` 在 **negedge dclk** 更新 | 10 ns | 10 ns |

dclk 的上升沿与 clk 的上升沿同刻（`dclk <= ~dclk` @posedge clk），
而 negedge clk 在 posedge clk 之后 5 ns、negedge dclk 在 posedge dclk 之后 10 ns，
所以两种更新都落在**采样沿之后**，下一次采样沿之前保持稳定。

### 2.1 修完后的时间线

```
t = k*20ns        posedge dclk
                    ├─ DUT      采样 din(sent=k) = byte[k]
                    ├─ data_model 采样 din(sent=k) = byte[k]   ← 相同
t = k*20ns + 10ns   negedge dclk: sent <= k+1
```

两个模型逐字节一致，且 `din` 在采样沿前有完整 10 ns 的建立时间。

### 2.2 顺带加一条 TB 侧独立证据

新增 `D42_window_384_dclk_edges`：在 **TB 自己**统计每个装载窗（`win` 有效期间）
真实 `posedge dclk` 的个数，要求每个窗恰好 384。这条不读 DUT 任何内部信号，
是"逐窗 384 字节"的直接证据。

断言总数 51 → **52**，`FLOOR` 保持 51（只增不减）。

---

## 3. 源码一致性（F1/F2/F3 是否真的在待仿真源码里）

预检脚本 `tools/t3_precheck.py` 做四件事，全部为**零仿真**：

1. 打印 `rtl/data_driver.v.txt`、`tb/tcon_t3_tb.sv.txt`、`t3b/GRAY_LUT_DEFAULT.hex.txt` 的 SHA-256；
2. 断言 F1 存在：`col_valid` 不在 `falling` 分支被清零；
3. 断言 F2 存在：捕获块（`raw_load[wcnt] <= din`）出现在 `if (rising)` **之后**；
4. 断言 F3 存在：`D40` 的 `chk` 出现在 `phase 6: reset` 之前；
5. 断言 TB 的 `sent`/`win` 只在 `negedge dclk` 更新、槽波形只在 `negedge clk` 更新。

任何一项不满足即 rc≠0，不允许花那一次运行。

---

## 4. 本轮**不**改的东西

- 51 条断言的名称、判据、阈值一律不动（只新增一条 TB 侧统计）；
- 不改 V1.3 接口协议、不改 TCON 六个 RTL、不改 `data_model`（它是 oracle，改了就失去独立性）；
- 不放宽任何数值目标。

---

## 5. 仍然 OPEN（复审点名，本轮不解决）

| 项 | 说明 |
|---|---|
| Pure 8-bit PWM | `w_eff` 用 `CNTW` 位表示，`PWM_MAX=255` 时"满窗 256 tick"需要 9 位才能表达；TCON 侧 30 ns tick 也未实现 → 只验证 Hybrid 6-bit |
| 256 项 LUT 的唯一性 | 同一电荷 Q 可由不同 (PAM,PWM) 组合实现（如 Q=2 = PAM0/PWM2 = PAM1/PWM1），故本表只能是**理想模型示例表**，不是已标定的唯一原始表 |
| 综合 / STA | 只做到"可综合编码 + 编译零告警"，没有综合网表、没有 STA |
| 384 路模拟恒流源 | 不在数字范围 |
