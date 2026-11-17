# T5_DATA_SERIAL_CONTRACT —— Data 384 字节接收界面（T5-A / P0-1）

日期 2026-11-17｜性质：**只读接口收口**，T5-A 授权为 `AUTHORIZED_ZERO_MODELSIM`；本文件不含任何仿真结论，也不修改已验收 RTL。

V1.3 原文来源：`v13_fulltext.txt`（段号＝行首编号），SHA-256 `6b42b1365b95e74159467bbb1ff600c628eb7e690a13ab44a2888ab191d7a791`（三份归档副本一致：`ic617_tcon_t2ar2_20261114/`、`t2b_verify/evidence/`、`t2bb_verify/evidence/`）。

---

## 1. V1.3 逐字摘录（不是转述）

**段 0548**（原文）：

> "Data装载无需额外VALID线：每个LATCH启动下一装载段，在约定的后续DCLK边沿接收384字节，之后停写；TCON和两Data采用相同计数定义。启动预充时在BLANK内先发一次LATCH初始化装载计数，384字节和映射流水完成后再LATCH到显示银行。连续时钟不代表无限吞入。控制脉冲DCLK同步，脉宽至少40 ns。"

**段 0447–0461（Data 侧引脚表原文条目）**：

| 段 | 信号 | 方向 | 电平/宽度 | 速率 | 备注（原文） |
|---|---|---|---|---|---|
| 0447–0451 | `D0[7:0]` | TCON→Data1 | D／3.3 V／8 | 50 MB/s | Row0,2,…766顺序384字节 |
| 0452–0456 | `D1[7:0]` | TCON→Data2 | D／3.3 V／8 | 50 MB/s | Row1,3,…767顺序384字节 |
| 0457–0461 | `DCLK` | TCON→双Data | D／3.3 V／1 | 50 MHz | **持续时钟；每列装载计数384有效字节** |
| 0462–0466 | `LATCH` | TCON→双Data | D／3.3 V／1 | 102.4 kHz 平均 | 仅 BLANK 内原始/映射银行原子切换 |
| 0467–0471 | `PWM_START` | TCON→双Data | D／3.3 V／1 | 102.4 kHz | 同 DCLK 采样，清零并预备共同计数 |
| 0472–0476 | `PWM_TICK` | TCON→双Data | D／3.3 V／1 | Pure 33.333 MHz / Hybrid 8.333 MHz | BLANK 内无有效 tick |
| 0477–0481 | `BLANK` | TCON→全部 Driver | D／3.3 V／1 | — | 高有效；板级上拉默认熄屏 |

**核对结论**：V1.3 的 Data 引脚表 **没有** `VALID` / `READY` 一类的数据有效线。
（段 0315 的 VALID/READY 是**内部模块**握手；段 0549 明确"TCON→Data 为定长无反压外部链路"。）

**`load_active` 在 V1.3 全文中出现 0 次**（`grep -c` 实测 0）。它是 `tcon_data_tx` 的内部观测输出
（`assign load_active = load_run && safe && !fault;`），**不是芯片引脚**。

## 2. 当前 RTL 实况（事实，不含判断）

`rtl/data_driver.v.txt`（T3-H 已验收版本，SHA `4ea897de…11c8be`）：

```verilog
input  wire din_valid;                                   // 端口存在
...
if (win_open && din_valid) begin                          // 逐字节累计只看这一条
    if (wcnt < NCH) begin raw_load[wcnt] <= din; ... wcnt <= wcnt+1; end
    else begin ovf <= 1'b1; err_flags[1] <= 1'b1; end     // 385 字节 -> ovf
end
```

`rtl/tcon_top.v.txt` 有 `output wire load_active`，**没有** `d_valid` 一类输出；
`tcon_data_tx` 在每次装载窗内固定发 384 字节（`LOAD_START=832, LOAD_LEN=768 clk, NB_PORT=384`），
非法列时不是"少发/多发"，而是 `d0/d1 <= 8'h00` 且 `load_blank<=1`（**用零填充凑满 384**）。

## 3. 三个必答问题

**Q1：没有额外 VALID 引脚，Data 怎样准确接收 384 字节？**
答：以 **LATCH 下降沿之后的第一个 DCLK 上升沿为第 0 字节**，此后每个 DCLK 上升沿递增，
到 **第 384 个上升沿**（含第 0 个）为止，**之后停写**。这正是 V1.3 段 0548 的"每个 LATCH 启动下一装载段…
接收384字节，之后停写"。Data 自身已经具备这个计数器（`armed + wcnt`），缺的只是"何时算有效字节"的判据。

**Q2：连续 50 MHz DCLK 下怎样停止接收？**
答：**由自身的 384 计数停止**（`wcnt == NCH` 即停），不需要外部告诉它"这一拍有效"。
第 385 个上升沿到达时 `wcnt` 已满，写入被禁止 —— 与 `din_valid` 无关。
边沿表见 `T5_DATA_EDGE_TIMELINE.csv`：`[832,1600)` 恰好 384 个上升沿，第 385 个在下一槽 cyc 624 附近。

**Q3：385 字节超长检测归谁？**
答：**只能归 TCON 的 RX 端**。Data 在无 VALID 的外部链路上只看到"连续的 DCLK 沿"，
无法把"第 385 个沿"与"下一列的时钟"区分开 —— 它计数到 384 就必须停。
⇒ 真实链路里 T3 的 `ovf/err_flags[1]`（385 字节）**永不触发**，该场景是**单元级防御测试**，不是系统行为。
同理，TCON 对非法列的处理是"发 384 个 0x00 + load_blank"，Data 会把它当作一次**合法长度**提交，
结果是**全通道关断（全暗）**，而不是 T3 单元测试里的 `col_valid=0`。这条差异必须写进系统验收。

## 4. 合同选择（三选一，均需审批）

| 方案 | 内容 | 加物理引脚？ | 改已验收 RTL？ | 评价 |
|---|---|---|---|---|
| **A. 仅仿真口** | 保留 `din_valid` 作**仿真专用**输入；T5 连接壳内用"LATCH 定界 + 384 计数"生成它 | 否（壳内生成，文档标注非芯片引脚） | 否 | 最快，但把"芯片自己数到 384"这件事交给壳，**不能证明芯片自治** |
| **B. 参数化自治（推荐）** | `parameter USE_DIN_VALID=1`；默认 1 保持 T3 现状；`=0` 时改由 `win_open && (wcnt<NCH)` 门控，`din_valid` 忽略 | 否 | 是（1 行 + 参数，需审批） | 芯片自治、证据可信；T5 用 `=0` 实例化；默认 1 保证 T3 52+17 条回归**不受影响** |
| C. 新增 VALID 引脚 | 把 `load_active` 引出为物理 `VALID` | **是（违反 A.2）** | 是 | **禁止** |

**建议：B**，并在同一版本里保留 `din_valid` 端口（`USE_DIN_VALID=1` 时行为不变），
这样 T3 的既有断言集与 T5 的 V1.3 模式可以共用同一份源码，差异只是一个参数。

最小补丁（**未应用**，见 `T5A_RTL_PATCH_PROPOSAL.md`）：

```verilog
parameter integer USE_DIN_VALID = 1;
wire byte_valid = USE_DIN_VALID ? din_valid : (win_open && (wcnt < NCH));
...
if (win_open && byte_valid) begin ... end
```

## 5. 迁移表：T3 既有断言 vs V1.3 外部协议

| T3 断言 | 原语义（仿真协议） | 在 V1.3 真实链路下 | 处置 |
|---|---|---|---|
| D11–D15 三列 384 字节差分 | TB 逐字节给 `din_valid` | 等价（仍是 384 个沿） | **保留，不改** |
| D24/D25 383 字节短列 | TB 只给 383 个有效字节 | **不可达**：TCON 永远发 384（非法列补零） | 保留为单元防御测试，标注"系统不可达" |
| D26/D27/D28 385 字节超长 | TB 给 385 个有效字节 | **不可达**：Data 数到 384 即停，第 385 沿被丢弃；`ovf` 不触发 | 保留为单元防御测试；**系统级超长必须由 TCON RX 检测**（另立断言） |
| D30 非法后合法列恢复 | 顺序给列 | 等价 | 保留 |
| T3-H D43–D59 | 同上 | 一致（与装载协议无关） | 保留 |

**不删任何一条**；新增的 T5 断言应针对真实链路写：TCON 发出的第 385 个沿**不得**改变 Data 的 `raw_disp`。

## 6. 待审批事项

1. 是否采纳方案 B（`USE_DIN_VALID` 参数），以及 `=0` 模式是否需要单独的限定仿真授权。
2. TCON 侧"超长列"检测断言归入 RX 还是系统级（V1.3 无明文，标 **OPEN**）。
3. "非法列 = 384 个零"这一 TCON 现有行为是否就是规格意图（V1.3 段 0548 只说"之后停写"，未规定补零）——
   标 **OPEN**，不擅自改 TCON。
