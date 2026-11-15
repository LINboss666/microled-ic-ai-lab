# T3 报告 —— Data Driver 内部数字逻辑（A 段完成，T3 验证 REWORK）

**任务** `TCON-T3T4-20261115` ｜ 基线 `a436f5e` ｜ **T3 ModelSim 2/2 已用，两次均 FAIL，无自动续跑**

---

## 1. 一句话

A 段（接口与灰阶码制冻结）**完成**，`data_driver` 可综合 RTL **写完且 0 error 0 warning**；
但两次正式仿真都失败，根因在第 2 次运行里被原始日志钉死（**383 vs 384 字节**），
修复已应用并编译通过，**但未验证**。按任务书 §D 停止，请求追加 1 次运行。

---

## 2. A 段交付（零仿真）

| 文件 | 内容 |
|---|---|
| `t3b/T3T4_SCOPE.md` | Data 384 路 / Scan 512 路接口逐条冻结，每行标 `FROZEN / DERIVED / OPEN`；时钟域、可综合边界、模拟不可替代部分 |
| `t3b/GRAY_CODE_MAPPING.md` | 8-bit → 3-bit PAM + 6-bit PWM 的码制：**LUT 机制 FROZEN**，表内容 `DERIVED_REPRODUCES_V13`，两个 `OPEN` 项 |
| `tools/gray_lut_derive.py` | 按 V1.3 §7 段0236 逐字实现的码表推导器，四项数字不符即返回非 0 |
| `t3b/GRAY_LUT_DEFAULT.hex.txt/.csv` | 256 项标定镜像 + 逐行 Q/PAM/PWM/tick/电流档 |

### 码制不是猜的

V1.3 段0236 给了算法和四个数字，我按它复现，**四个全对**：

```
distinct charge values (dedup)   : 268      V1.3 says 268      -> MATCH
min adjacent gap, all 268        : 1        V1.3 says 1/512 FS -> MATCH
max |Q - linear| / FS            : 21.7800% V1.3 says 21.78 %  -> MATCH
black = PAM0/PWM0, max = PAM7/PWM63        (段0218 两条硬规则) -> MATCH
RESULT: DERIVED_REPRODUCES_V13
```

抽码规则也定死了：268 个排序电荷按 `round(j·267/255), j=0..255` 等距抽 256 个。
换任何别的规则（取前 256、floor 抽样、无约束最近邻）都对不上 21.78 %——所以这不是拟合。

---

## 3. B 段：`rtl/data_driver.v` 做了什么

| 能力 | 依据 | 状态 |
|---|---|---|
| 384 通道原始双 bank（384×8 装载 + 384×8 显示） | 段0333 | 已实现 |
| 384 通道映射双 bank（384×9），**装载时逐字节查 LUT** | 段0335/0359 | 已实现 |
| 256×9 双银行 LUT + `COMMIT` 提交互锁（黑码/满码/写满三项检查、仅 SAFE 且无进行中装载才换银行） | 段0680–0696/0359 | 已实现 |
| 共享 PWM 计数器 + 384 路比较器（每芯片一个） | 段0338/0339 | 已实现 |
| PAM 3-bit 档位输出 | 段0340 | 已实现 |
| `PWM_START` 以 **toggle 握手**跨进 `PWM_TICK` 事件域（10 ns 事件不能被 20 ns 时钟采样） | 段0467–0476 | 已实现 |
| `BLANK/FAULT/RESET` **组合优先关断** | 段0355/0477–0481 | 已实现 |
| 短列/超长列**不提交**，保留旧内容但撤销显示许可 | 段0355 + T2B 合同 | 已实现 |
| `data_model` 保留为**独立 oracle**，不共享任何内部信号 | 任务书 §B.1 | 已实现 |

**没有**内置灰阶表——V1.3 规定 LUT 由 SPI 写入，所以上电全 0、未提交前不可显示；
标定镜像只由 TB 灌入。

---

## 4. 两次运行

| run | 结果 | 说明 |
|---|---|---|
| #1 | **27/51 PASS，24 FAIL** | 无诊断探针 |
| #2 | **25/51 PASS，26 FAIL** | 带 DBG 探针，根因在此定位 |

两次都 `vlog` 0 error / 0 warning；`data_driver` 与 `data_model` 同时编译进同一个 TB。

### 4.1 第 2 次运行的关键原始日志

```
DBG_EDGE  t=26705000 sent=0 nb=384 dut_wcnt=0 armed=0 dv=1 din=00
DBG_EDGE  t=26725000 sent=1 nb=384 dut_wcnt=0 armed=1 dv=1 din=01
DBG_EDGE  t=26745000 sent=2 nb=384 dut_wcnt=1 armed=1 dv=1 din=95
...
DBG_LATCH t=36415000 latch=1 slot=1 cyc=828 sent=384 dut_wcnt=383 colv=0 orc=1
```

**同一窗口：TB 送出 384 字节，独立 oracle `data_model` 收下 384 字节并提交（`orc=1`），
而新 RTL 只收到 383 字节（`dut_wcnt=383`）。** 这就是"两个模型行为不一致"的全部证据。

### 4.2 根因（已确证）

在 `always @(posedge dclk)` **同一个块**里，捕获块写在 LATCH 边沿块之前：

```verilog
if (win_open && din_valid) begin ... wcnt <= wcnt + 1; ... end   // 先执行 → wcnt=1
if (rising) ... else if (falling) begin ... wcnt <= 10'd0; end    // 后执行 → wcnt=0（赢）
```

同一个 always 块里对同一变量的多条非阻塞赋值，**最后执行的那条生效**。
于是 LATCH 下降沿（装载窗第一拍）：
1. `raw_load[0] <= byte0`、`wcnt <= 1`；
2. 紧接着 `falling` 分支把 `wcnt` 覆盖回 0；
3. 下一拍 `raw_load[0]` 被 byte1 覆盖 —— **byte0 丢失，整窗 383 字节，永不提交**。

这与 `data_model` 的语义（段0462：LATCH 1→0 那一拍**就是**新传输的第一个采样沿，byte0 取自该拍）
正好差一个字节，所以 oracle 提交、RTL 不提交。

### 4.3 顺带查出的第二个缺陷（已在第 2 次运行前修掉，尚未验证）

`col_valid` 原本在每个 LATCH **下降沿**（装载窗刚打开）就被清 0，导致整个显示窗口内
`col_valid` 恒为 0、`ch_en` 恒为 0。已改为"只在提交失败时清"。

---

## 5. 已应用但**未验证**的修复（请求 1 次运行验证）

| # | 文件 | 改动 | 依据 |
|---|---|---|---|
| F1 | `rtl/data_driver.v` | `col_valid` 不再在窗口打开时清零，只在提交失败时清零 | 显示 bank 在整个下一槽内必须保持有效 |
| F2 | `rtl/data_driver.v` | 把捕获块**移到** LATCH 边沿块之后，使下降沿那拍的 `wcnt<=wcnt+1` 成为最后一条赋值 | §4.2 的 383 vs 384 证据 |
| F3 | `tb/con_t3_tb.sv` | `D40_oracle_committed_columns` 移到 P6 复位**之前**采样（复位会清 oracle 的计数器，原位置恒失败） | 断言位置错误 |

F1/F2 之后重新 `vlog`：**0 error 0 warning**。但**没有跑过**，所以它们不能算已验证。

---

## 6. 现在能说的和不能说的

**能说**
- 8-bit → 3+6 的码制有 V1.3 明确依据，表内容四点复现；
- `data_driver` 是一份可综合、参数化、编译零告警的 384 路数字内核，接口按 §10/§12 逐条对齐；
- 两次失败的原始 transcript、DBG 探针输出、编译日志全部保留；
- 根因定位到具体语句和具体拍（`t=26705000` 那一拍）。

**不能说**
- 不能说 384 路装载/显示通过——**没有任何一列被成功提交**；
- 不能说灰阶引擎通过——`ch_en` 从未拉高，`on_cnt` 全 0；
- 不能说 PAM 档位正确——`D17` 虽然 PASS，但它比的是 `map_disp`（此时为 0）与 `ch_pam`，
  在无提交的情况下属于**空洞通过**，我不把它当证据；
- `PURE` 模式与 4 档 PAM 仍 `OPEN`；SPI/中断/UVLO/OTP、STA、CDC、384 路电气实现均未做。

---

## 7. 请求

**追加 1 次 ModelSim 运行**（T3 第 3 次），只跑 `run_tcon_t3.sh`，验证 F1+F2+F3。
若仍失败即停，不再请求；若通过，T3 内部数字可进入独立复审，然后再谈 T4。

T4（512 路 Scan 内部数字）**未开始**——任务书 §D 允许先 T3 后 T4，本轮按此顺序执行，
避免两条子线同时扩散。
