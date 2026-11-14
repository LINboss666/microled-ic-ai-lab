# 针脚级监视器：在真实归档波形上的离线复算

**任务** `TCON-T2B-BR` A.2 / A.5 ｜ **本轮 ModelSim 消耗 = 1 次（仅 #4）**
**目的** 在花掉唯一一次正式仿真之前，先用**已经存在的真实波形**验证新监视器的采样规则，避免"用预算去发现时序模型写错了"。

---

## 1. 为什么可以用旧波形

`D:/ic617_course_sim_20261112_native/t2ar2_run03_all/tcon_t2a.vcd`
是 T2AR2 轮 `run03` 的原生 VCD（该轮的 D0/D1 已被独立复审逐字节接受，3,840 组采样 0 失配）。
它里面的 `dclk / latch / d0 / d1 / scan_stb / col_id / blank` 全部来自**同一个 `tcon_top` 的端口**，
与 T2B-BR 要观察的对象同源；本轮 RTL 没有改 `tcon_slot_seq` / `tcon_timebase` / `tcon_data_tx` 的相位。

因此这份 VCD 是验证"**采样规则**"的合格夹具：它能把"在哪个沿取第 0 个字节"这类问题暴露出来。

---

## 2. 被验证的规则（就是 RTL 里写的那两条）

**Data 端口**（`rtl/data_pin_mon.v.txt`、`rtl/data_model.v.txt`）

1. `latch_d` **只在 DCLK 上升沿更新**（不是每个 100 MHz 参考沿）；
2. 在 DCLK 网格上看到 `LATCH` 上升 → 关闭并比较上一个窗口；
3. 在 DCLK 网格上看到 `LATCH` 下降 → 该沿就是传输的**第 0 个采样沿**，当场取 byte 0；
4. 之后 383 个上升沿取 byte 1..383；满 384 字节后不再取，直到下一个 `LATCH` 上升。

RTL 里的 `#1` 只做 delta 稳定（`LATCH` / `DIN` 与沿同刻变化），因此复算脚本用"时间戳结束时"的值。

**Scan 端口**（`rtl/scan_pin_mon.v.txt`）

在真实 `posedge scan_stb` 上取 `COL_ID` / `BLANK`，并测 `setup = 本次沿 − 上次 COL_ID 变化`、
`hold = 下次 COL_ID 变化 − 本次沿`。

---

## 3. 复算脚本

`coursework/microled_sim/tools/offline_pin_monitor_replay.py`（纯 Python，无第三方依赖，不消耗任何 EDA 预算）

```
python offline_pin_monitor_replay.py <file.vcd>
```

### 3.1 早期版本的两个错误（已修正，留档说明为什么现在的规则才对）

| 尝试 | 规则 | 结果 | 结论 |
|---|---|---|---|
| 1 | 在 `negedge latch` **事件**上置 `armed`，在 `posedge dclk` 事件上取字节，两个事件同刻时按 VCD 行序 | 23 个窗口，但首个窗口 byte0 错位 | 同刻事件的**行序**不确定 → 不能用事件顺序定义相位 |
| 2 | 同 1，但 `armed` 用阻塞赋值、取字节延后 1 ns | 23 个窗口全部 384 字节，byte0 正确 | 这就是 RTL 现在的写法 |
| 3 | 把 `latch_d` 改成**只在 DCLK 沿**更新（RTL 最终版） | 22 个窗口全部 384 字节，byte0 全部正确 | ✅ 采用 |
| 4 | 若 `latch_d` 在"非 DCLK 沿的 latch 变化"时也更新 | 只剩 9 个窗口 | ❌ 会漏掉半个窗口，已排除 |

第 4 种是这轮最重要的一个坑：`latch_d` 一旦在非采样沿被更新，`LATCH` 上升沿就会被
"提前消费"掉，整窗丢失。RTL 里只在一个 `always @(posedge dclk)` 中更新 `latch_d`，因此不会踩到。

---

## 4. 结果（`run03` VCD，22 个窗口 / 22 次选通）

```
DATA: windows=22  all_384=True
  t=18245000  n=384 byte0=5A/67 pattern_col=[0, 256]
  t=28025000  n=384 byte0=5B/68 pattern_col=[1, 257]
  t=37785000  n=384 byte0=5C/69 pattern_col=[2, 258]
  t=47545000  n=384 byte0=5D/6A pattern_col=[3, 259]
  t=57305000  n=384 byte0=00/00 pattern_col=none (invalid/zero column)
  ...
  t=135445000 n=384 byte0=66/73 pattern_col=[12, 268]
  t=145205000 n=384 byte0=67/74 pattern_col=[13, 269]
  t=154965000 n=384 byte0=68/75 pattern_col=[14, 270]
  t=164745000 n=384 byte0=69/76 pattern_col=[15, 271]
  t=213565000 n=384 byte0=6E/7B pattern_col=[20, 276]
SCAN: strobe_edges=22
  t=9005000   col=0  blank=1 setup=9005.0 ns
  t=18765000  col=1  blank=1 setup=8790.0 ns
  ...
  setup min=8790.0 ns   outside_blank=0
```

读数：

* **每个窗口恰好 384 个字节**，没有一个窗口多一个或少一个 → `win_badlen` 的判据可用；
* `byte0` 就是该列的**第 0 行**（`5A / 5B / 5C / 5D` 对应列 0/1/2/3 的 `pat(c,0)`，`67/68` 对应 `pat(c,1)`）
  → 说明**不会错位一个字节**，标签解码才有意义；
* `pattern_col` 出现 `[c, c+256]` 双解是 T2AR2 载荷本身的低 8 位图案性质（无高位标签），
  不是判据缺陷；T2B 载荷的 byte1 带 `col[9:8]`，不存在双解；
* `pattern_col=none` 的 16 个窗口正是 T2AR2 里被故意作废的列（4/5/7/8/9/16/18/19/21/22/23/25/26 等），
  与 `exp_zero_col()` 一致 → 监视器能区分"健康窗口"和"作废窗口"；
* `SCAN`：22 次选通**全部** `blank=1`，`setup` 最小 8,790 ns。
  T2AR2 的 `COL_ID` 在**槽边界**换值，所以 setup ≈ 一整个槽；T2B 的 `COL_ID` 在 `LATCH`（周期 828）换值，
  预期 setup = 520 ns，仍远大于 V1.3 要求的 10 ns。

---

## 5. 这份复算能证明什么、不能证明什么

**能证明**

* 采样规则本身是**相位正确**的：384 字节、从第 0 个字节开始、标签字节落在 byte0/byte1；
* `latch_d` 只在 DCLK 沿更新的写法不会丢窗、不会多取；
* Scan 观察点取在真实上升沿时，`BLANK` 与 `COL_ID` 在那一刻是稳定的。

**不能证明**

* 不能替代 #4 的联合仿真：它没有 DUT 的 FSM、没有 2×768 B bank、没有 V1.3 列首同步；
* 不能证明 T2B 的 `COL_ID` 与 Data 显示列一致（那需要 Data 侧的标签，旧载荷没有标签）；
* 不能当作 STA：`setup/hold` 是理想 RTL 相位模型下的仿真值，时序签核仍是 `NOT_RUN`。
