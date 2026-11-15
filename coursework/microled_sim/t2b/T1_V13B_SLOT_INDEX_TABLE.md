# T1-V13B —— 槽号索引对照表（仿真前离线产出）

**任务** `TCON-T1-V13B-20261115` ｜ 基线 `886d023` ｜ 本轮 ModelSim 上限 **1 次**（尚未使用）

这份表是为了回答一个问题：**B7 到底比的是哪两个槽边界？**
上一轮的实现比的是"槽 2 起点"与"槽 1025 起点"，两者相隔 **1023** 个槽边界，却在断言里写着 `period_1024`。
本轮把比较点改到 **槽 2 ↔ 槽 1026**（相隔 1024），并额外核对两个绝对值。

---

## 1. 循环语义（为什么"iteration k"看到的是"槽 k+1"）

`scen_boundary` 的测量循环是：

```verilog
slots = 0;
while (slots < 1024) begin
    @(posedge slot_start);   // 等待"下一个"槽边界
    #1;
    if (slots == 1) col_slot2 = dut.col_id;
    ...
    slots = slots + 1;       // 等待之后才自增
end
```

关键点：**`slots` 记的是"已经完成的观察次数"，而循环体在等待之后才执行**。
进入循环前，TB 已经处在**槽 0 的周期 0 内**（`t_prev` 被设为"启动槽 0 的那个沿"）。
所以第一个 `@(posedge slot_start)` 等来的是**槽 1 起点**，不是槽 0 起点。

| 循环体内 `slots` 的值 | 实际观察到的槽边界 | 采样动作 |
|---:|---|---|
| 0 | 槽 1 起点 | 记录槽 0 长度（`first_len`） |
| **1** | **槽 2 起点** | **`col_slot2`** |
| 1022 | 槽 1023 起点 | — |
| 1023 | 槽 1024 起点 | 循环第 1024 次、也是最后一次 |
| 循环后 +1 次等待 | 槽 1025 起点 | `col_slot1025`（应 = 1023） |
| 循环后 +2 次等待 | 槽 1026 起点 | `col_slot1026`（应 = 0） |

因此上一轮报告里写"槽 1 vs 槽 1025"是错的，实际是**槽 2 vs 槽 1025，相隔 1023**。
本轮的 `col_slot2` 严格取在**槽 2 起点**（`slots == 1` 不变，只是名字改对了）。

---

## 2. 静态检查（不看仿真，直接读源码文本）

`tools/t1_slot_index_check.py` 从 TB 源码里抽出 `scen_boundary` 的任务体，
读取 `while (slots < N)` 的 N、`if (slots == K)` 的 K、以及循环之后到每个采样点之间的
`@(posedge slot_start)` 计数，然后算出绝对槽号：

```
source file            : coursework/microled_sim/tb/tcon_t1_tb.sv.txt
loop bound N           : 1024
base sample condition  : slots == 1
post-loop waits to 1025: 1
post-loop waits to 1026: 2

  loop iteration   observed slot_start   COL_ID sample
  --------------   -------------------   -------------
  slots == 0        start of slot 1
  slots == 1        start of slot 2        <- col_slot2
  slots == 1022     start of slot 1023
  slots == 1023     start of slot 1024
  (after loop)     start of slot 1025     col_slot1025
  (after loop)     start of slot 1026     col_slot1026

derived slots: col_slot2 = slot 2, col_slot1025 = slot 1025, col_slot1026 = slot 1026
gap(col_slot1026 - col_slot2) = 1024 slot boundaries
B7 expression           : (col_slot1026 == col_slot2) && (col_slot1025 == 10'd1023) && (col_slot1026 == 10'd0)
RESULT: SLOT_INDEX_OK
```

**负控**（证明这个检查器不是恒真）：把"槽 1026 的那次等待"删掉、让 `col_slot1026` 与
`col_slot1025` 取同一个边界，检查器立刻报

```
gap(col_slot1026 - col_slot2) = 1023 slot boundaries
FAIL: the two compared samples are 1023 slot boundaries apart, not 1024
RESULT: SLOT_INDEX_BAD   (rc=1)
```

即检查器复现的正是上一轮那个缺陷。

---

## 3. 预期值为什么是 0 / 1023 / 0（RTL 推导，不是从仿真里抄）

`tcon_top` 中 `col_id` 只在 `latch_evt`（`slot_cycle == LATCH_AT-1 = 827`，即 828 那一拍前）更新，
取的是当拍的**显示 bank 标签** `fw_sel_col`：

```verilog
else if (latch_evt)  col_id <= fw_sel_col;   // what LATCH just made current
```

所以 **槽 K 起点读到的 `col_id` = 槽 K−1 在 828 写入的值**。逐槽推：

| 槽边界 | 上一槽 LATCH 写入的值 | 说明 |
|---|---:|---|
| 槽 2 起点 | **0** | 槽 1 的 LATCH 把"第一个收满且合法的列"切成显示 bank，那是列 0（T2B-C 已修的启动语义：首列就是 0，不是 1） |
| 槽 1025 起点 | **1023** | 槽 1024 的 LATCH 写的是第一帧最后一列 |
| 槽 1026 起点 | **0** | 槽 1025 的 LATCH 写的是第二帧的列 0 → 环绕发生，且**回到与槽 2 完全相同的值** |

因此三个预期值不是"拟合出来的"，而是 RTL 那条更新语句 + 已验收的启动语义推出来的。

### 这三项分别在防什么

| 检查 | 防的问题 |
|---|---|
| `col_slot1026 == col_slot2` | 周期性：相隔**严格 1024** 个边界的两次采样必须相等 |
| `col_slot1025 == 1023` | **空洞性**：若 `col_id` 一直是 0，这条会挂，B7 就不可能"因为两边都是 0"而通过 |
| `col_slot1026 == 0` | 环绕点本身正确：1023 之后必须回到 0，而不是 1024（10 位截断前的值）或别的数 |

---

## 4. 帧边界的合法性（为什么槽 1024 不会把 `col_id` 冻住）

`col_id` 在 `flt` 时冻结。槽 1024 起点同时出现 `VSYNC + COL_SYNC`（视频驱动在第一帧最后一列之后把
`vcol` 归零、`vframe` 加一）。RX 的两个帧相位判据此时都成立：

- `next_col = vs_p ? 0 : in_col+1` → 0；`col_index = tb_col` 在槽 1024 起点也是 0 → `next_col != col_index` 为假，不置 `err_flags[2]`；
- `vs_p && (col_index != 0)` 为假 → 不置 `err_flags[4]`。

所以帧边界不会被判成相位错误，`flt` 不会被置起，槽 1025 的 LATCH 能正常写入第二帧的列 0。
旁证：T2B 联合验证里整帧 1026 次选通全部有合法显示 bank（`core_n = 1026`、`skip_n = 0`），
说明列号在 1023→0 处确实环绕过一次并且仍然合法（`wraps=1`）。

---

## 5. 本轮唯一一次运行的预期输出

```
FIRST_FRAME slots=1024 first_len=976 long=576 short=448 cycles=1000000 wraps=1
FIRST_FRAME_COLID col_slot2=0 col_slot1025=1023 col_slot1026=0 (expect 0, 1023, 0)
```

B1..B7 全部 PASS 后才会执行 B8/B9/B10/B0 —— 这四条**至今从未执行过**
（第一轮卡在 T3、第二轮卡在 B7），它们的计数器是跨场景累加的，本轮才第一次被真正检验。

---

## 6. 本轮改动的边界（与任务书 §4.1 的对应）

| 项 | 状态 |
|---|---|
| 只改 `tb/tcon_t1_tb.sv.txt` | ✅ `+35 / −9`，无其它源文件改动 |
| 断言总数 55、分组 27/17/11 | ✅ 未变 |
| 原有 `chk` 名称 | ✅ 未变（`B7_col_id_period_1024_after_wrap` 保留） |
| 硬判据是否放宽 | ❌ 未放宽，反而**加严**（三条件合一） |
| 6 个 RTL 文件 | ✅ 逐字节未变（与上一轮 `00_source_sha256.txt` 一致，`tcon_top = 0f8e9169…`） |
| 时钟 / 2 µs 复位 / 视频协议 / T6 checker | ✅ 未改 |
| 完整帧 VCD | ✅ 仍禁用（`$dumpoff` 在 `scen_boundary` 之前） |
