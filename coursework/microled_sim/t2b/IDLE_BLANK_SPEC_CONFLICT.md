# IDLE / 启动预充的 BLANK 契约（T2B-C：已修复）

**状态** `FIXED_AND_VERIFIED_IN_RUN_A2`（T2B-BR 时是 `REGISTERED / NOT_COMPLIANT`）
**证据** `t2bc_runA2_joint/03_vsim.stdout`：`T2B_IDLE_BLANK idle_blanklow_cycles=0`，
`P52_no_unblank_without_data`、`P53_idle_never_unblanks` 均 PASS。

---

## 1. 规格原文（V1.3 原件，SHA-256 `6b61e4ab…afaa`）

* §9 段 **0810**：上电、配置、校准、缓存预充、正常同步有效后，方撤销 BLANK
* §9 段 **0323**：启动先预充两级，显示帧边界相对输入延迟，但不丢失帧首两列
* §12 段 **0466**：`LATCH` 在 BLANK 内原子切换显示银行
* §20 段 **0918**：异常时当前及后续列全关，直到恢复合法帧

---

## 2. 修复前（T2B-BR，`b02f824`）

```verilog
assign blank = blank_seq || !safe || flt || (act && !disp_ok);
assign latch = latch_seq && safe && !flt && (!act || fw_ok);   // ← 第二个缺陷
```

两个独立缺陷：

1. **IDLE 撤 BLANK**：`act=0` 时 `blank` 退化成 `blank_seq`，每槽 [0,768) 仍为低。
   VCD 实测 `BLANK=0` 在 **995～1,015 ns**（20 ns）。
2. **首列丢失 + 无效发光许可**（复审新增 P0）：`latch` 被 `fw_ok` 门控，
   槽 0 的 LATCH 被吞掉 → 列 0 的 384 B 从没被 Data 捕获；
   而 `disp_ok` 只依赖 TCON 自己的标签，于是在 **20,535～28,215 ns（7,680 ns）**
   出现了 `BLANK=0`、Scan 已选列 0、两颗 Data bank 全无效的窗口。
   首个有效 bank 出现在 28,826 ns，装的是**列 1**。

根因一句话：**把结构性的时序信号 `LATCH` 当成了"有数据才发"的许可信号**。

---

## 3. 修复（本轮，`tcon_top.v.txt`）

```verilog
// LATCH 是预充流程的一部分，在 BLANK 内无条件（对 safe 而言）发出
assign latch = latch_seq && safe && !flt;

// 饱和 2 位的预充计数（Run A 抓到过 4 位自由计数回绕的缺陷）
reg [1:0] latch_cnt;
always @(posedge clk_ref or negedge reset_n)
    if (!reset_n)                                  latch_cnt <= 2'd0;
    else if (latch_issue && (latch_cnt != 2'd2))   latch_cnt <= latch_cnt + 2'd1;
wire precharge_done = (latch_cnt == 2'd2);

// 三条互相独立的门
wire disp_ok = disp_valid && !disp_poison && precharge_done;
assign blank     = blank_seq || !safe || flt || !act || (act && !disp_ok);
assign pwm_start = pstart_seq && safe && !flt && act && disp_ok;
assign scan_stb  = stb_seq    && safe && !flt && act && disp_ok;
assign pwm_tick  = tick_base  && window && safe && !flt && act && disp_ok;
```

**没有增加任何 Data→TCON 的物理反馈引脚**：`latch_cnt` 是 TCON 自己对"已发出几个 LATCH"的计数，
它与 Data 实际提交是否一致，由**独立 Data 模型**在仿真里核验（见 §4）。

---

## 4. 怎么被证伪 / 被证实

| 检查 | 修复前 | 修复后（Run A2） |
|---|---|---|
| `T2B_IDLE_BLANK idle_blanklow_cycles` | 20 | **0** |
| BLANK 为低而 Data bank 无效的周期数（每拍检查） | 932 拍（7,680 ns + 尾） | **0**（`P52`）|
| 首个被比较的显示列 | 列 1（列 0 从未提交） | **列 0**（`P19b_startup_first_column_is_0`）|
| 预充列被"允许跳过"的次数 | 1（`prech_n=1`） | **0**（`prech_n=0`，没有任何列被跳过）|
| 帧首两列（帧 1/帧 2 各列 0、列 1） | 未验证 | **全部经过接收→转发→提交→选通**（`P54`）|
| 整帧每个槽一次选通 | 898 / 1026 | **1026 / 1026**（`P39b`）|

原始 VCD（Run A2，phase-1 窗口）独立复核：

```
LATCH^  t=  9,285 ns           ← 修复前这一条根本不存在（槽 0 的 LATCH 被吞）
LATCH^  t= 19,045 ns
dm0_valid->1 / dm1_valid->1  t= 19,046 ns     ← 列 0 的提交
BLANK->0  t= 20,535 ns  col_id=0 dm0_v=1 dm1_v=1   ← 首次解除 BLANK 时数据已就绪
first window tag: col=0 frame=1
```

---

## 5. Run A 自己抓到的一个缺陷（留档）

第一次 Run A 是 **55/56**，唯一失败的 `P46` 报"整帧只有 898 次选通"。
根因是 `latch_cnt` 写成了 **4 bit 自由计数**，每 16 槽回绕，回绕到 0/1 的两槽
`disp_ok` 掉 0 → 每 16 槽丢 2 次选通 → `1026 − 2×64 = 898`，与实测**完全相等**。
改为饱和 2 位后 Run A2 得 1026/1026，并补了 `P39b_one_strobe_per_slot`
（`ph_stb == slot_done − 1`）专门守这一类漏选通。

---

## 6. 仍未关闭的部分（不要读成"启动全部合规"）

* **Run B（V1.3 合约 T1）没跑**：本轮 2 次预算已用完（A 失败 1 次 + A 重跑 1 次）。
  T1 TB 已按新合约重写并编译通过（55 条），但状态是 `COMPILED_ONLY / NOT_RUN`。
* `latch_cnt` 是**预测**，不是反馈。真实芯片若因为 Data 侧异常没有提交，
  TCON 不会知道——这属于 `fault_n` 闭环与 CDC，未做。
* 「预充两级」的**级数**取的是 2，来自 §9 的定性描述；V1.3 没有给出可机读的计数值。
* 真实 LED 是否发光取决于驱动阵列电气模型（未实现）。
