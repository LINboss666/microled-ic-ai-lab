# T6-A RUN02 报告（SPI 帧接收 + 寄存器文件 + CDC）

日期：2026-11-19　预算：T6-A 两次，RUN01 用 1 次，**本轮用掉最后 1 次**
裁定自评：`T6A_RUN02 = 57/57 PASS`（待独立复审，不自签 GO）

---

## 1. 一句话结论

RUN01 的四个 P0（CS 电平当事件、读写位取 `sh[47]`、地址取高位切片、读当写）以及复审新增的
三个 P0（MISO 未高阻、读快照每拍刷新、CDC 无握手）**全部按实际 RTL 重写**，零仿真硬门先全绿，
再用唯一一次 vsim 得到 **57/57 PASS**（原 43 条名称/阈值一律未改，新增 14 条）。

---

## 2. 零仿真阶段做了什么（先写后跑）

| 产出 | 内容 | 结果 |
|---|---|---|
| `tools/t6a_run02_model.py` | **逐边沿 RTL 状态模型**：直接按 RTL 语句实现（CS 高电平复位、第 16 沿头字段、MISO 下降沿移位、CS 上升沿 epoch、2FF+沿捕获、单次快照） | 4 类交易 × SCLK 10/4 MHz × core 相位 0/2.5/5/7.5 ns 全过；**7 个负控全部被拒** |
| `tools/t6a_edge_table.py` | 任务书 C 段要求的 48 沿时序表，两次连续交易，CS 高期间无 SCLK 沿 | PASS（见 §5） |
| `tools/t6a_run02_precheck.py` | 静态硬门：新结构必须存在、旧缺陷必须被判定为失败；**检查前先剥注释**（否则会被描述缺陷的注释骗过） | `GATES_FAILED=0` |
| `vlog` | 四个源文件 | 0 errors / 0 warnings |

负控（都在模型里真实跑出反例）：

| 编号 | 注入的旧缺陷 | 结果 |
|---|---|---|
| NC1 | 恢复 `if (!cs_n)` 在 SCLK 块里清零 | 移位不前进，捕获 0 帧，读返回错值 → 被拒 |
| NC2 | 读写位改回 `sh[47]` | 读永远识别不出 → 被拒 |
| NC3 | 地址改回 `sh[46:32]` | 读到错误寄存器 → 被拒 |
| NC4 | 去掉读写限定，读也提交 | W1C 副作用出现 → 被拒 |
| NC5 | 去掉 48 沿长度检查 | 47 沿帧被提交 → 被拒 |
| NC6/NC7 | 真设计下 47 / 49 沿 | 帧被拒、寄存器不变、`mb_badlen=1` |

---

## 3. 七个 P0 的落点

| 复审编号 | 问题 | rev2 做法 |
|---|---|---|
| P0-1 | CS 低期间每个 SCLK 沿清零 | 复位改成 **CS_n 高电平（总线空闲）**：`always @(posedge sclk or posedge cs_n or negedge reset_n) if (!reset_n \|\| cs_n)`。移位块、头字段块、MISO 块三处一起改；**第 1 个上升沿即计数为 1** |
| P0-2 | 读写位取自正在移位的 `sh[47]` | 第 16 沿（`bc==15`）冻结 `hdr_read <= sr[14]`，此后**不再碰移位器**；`rd_req` 用冻结位 |
| P0-3 | 地址取自 `sh[46:32]` | 同一沿用 `{sr[13:0], mosi}` 重建 15 位地址（`0x801C → 0x001C`，模型与边沿表双向验证） |
| P0-4 | 读会走写路径 / W1C | 写只经邮箱 epoch 进入；读事务**根本不产生 epoch**，因此主写路径与 FAULT/INT 两条 W1C 都不可能被读触发 |
| P0-5 | CS 上升清帧导致跨域丢帧 | 写帧在**第 48 上升沿**先落 `wr_frame`（此时已稳定），CS 上升沿只翻 `wr_tog`；核心 2FF 后用它自己的 epoch 应答；`ack_s2 != wr_tog` 时置 `mb_lost`，**丢帧会被记录而不是静默消失** |
| P0-6 | MISO 未高阻、快照撕裂 | `assign miso = cs_n ? 1'bz : miso_r`；`rd_snapshot` 改为 `if (rd_cap_o)` 单次锁存（`rd_cap_o = rq_s2 && !rq_s3`） |
| 附加 | EN=0 / BLANK / FAULT 优先级 | `hw_blank = blank_r \| !en \| any_hw_fault`（纯 OR，软件无法绕过）；写 EN=0 强制 BLANK=1；有硬件故障时禁止 unblank；unblank 判定用**新的** en 位 |

---

## 4. 原生结果

```
COURSE_RTL_ASSERT_COUNT=57  PASS_COUNT=57  FAIL_COUNT=0  RESULT=PASS
CHECK0..4 = 1/1/1/1/1        RUNNER_VERDICT=PASS   RUNNER_EXIT=0
vlog 0 errors / 0 warnings   vsim 8 s

T6A_COUNTS writes=39 reads=49 commits=95 sw_pulses=1 frames=106 captured=46 rejected=7
T6A_CDC    frames_sent=46 frames_captured=46 lost=0 badlen=1
```

- `captured=46 = writes 39 + rejected 7` —— 账目自洽，没有丢/重；
- `lost=0`：46 个写帧全部被核心消费，没有一个因为 CS 高间隔太短而丢失；
- `badlen=1`：全程只有 D23 那条 30 沿的短帧被标记（D24 的 20 沿同属短帧，但 `mb_badlen` 是 sticky，计数为 1 表示"发生过"）；
- `sw_pulses=1`：D16 的 W1P 只脉冲一次。

---

## 5. 48 沿时序表（节选，完整见 `evidence/precheck_edge_table.txt`）

```
=== transaction 0: WRITE 0x001C = 0x1234 ===
edge  bc_before bc_after rd_bit addr    next_miso epoch frame
   1      0        1        0     0x0000  0         0     0x000000000000
  16     15       16        0     0x0000  0         0     0x000000000000   <- 头字段在此沿之后
  17     16       17        0     0x001C  0         0     0x000000000000
  47     46       47        0     0x001C  0         0     0x000000000000
  48     47       48        0     0x001C  0         0     0x000000000000
  CS high 48       0        -     0x0000  -         1     0x001C00001234   <- epoch 翻转 + 帧冻结

=== transaction 1: READ 0x001C ===
  16     15       16        0     0x0000  0         1     （上一帧仍被持有）
  17     16       17        1     0x001C  0         1     <- 读方向在此已成立
  48     47       48        1     0x001C  0         1
  CS high 48       0        -     0x0000  -         1     0x801CFFFFFFFF
```
两次交易之间 CS_n 为高且**没有任何 SCLK 沿**，第二次仍能正确起帧。

---

## 6. 断言账

- 原 43 条：名称、阈值一字未改（`D01`–`D43`），全部 PASS；
- 新增 14 条（`D44`–`D57`）：读首字节四态定义、读不产生写副作用、W1C 读后仍可用、
  47/49 沿拒绝、MISO 高阻/选中驱动、读快照不撕裂、CDC 无丢无重、EN=0 强制 BLANK、
  故障禁止 unblank、INT_EN=0 不削弱安全、CS 高间隔合法；
- `MIN_ASSERTS=57`，runner 的 `FLOOR` 同时由 43 提到 **57**（不允许用旧门槛掩盖新增断言未执行）。

`D42/D43` 的计数口径已改为 DUT 真实事件（`wr_ok_o` / `rd_cap_o`），不再是 TB 自己发起的次数。

---

## 7. 仍然 OPEN（不得当成已完成）

1. **cs_n 作为功能时钟**：写帧的 48 位保持寄存器与 epoch 由 CS_n 上升沿驱动，STA 必须为它建约束；本轮只声明**功能级 CDC**，不是 CDC 工具签核。
2. **最小 CS 高间隔 = 100 ns**（10 个 core 周期，握手往返 3 拍的三倍余量）。更短的间隔可能丢帧——此时 `mb_lost` 会置位，但系统必须读它。
3. **只在 TCON 子集上验证**：10 个地址；Data/Scan 的寄存器集与 CHIP_ID 尚未参数化。
4. **SPI 时序参数**（建立/保持、SCLK 到 MISO 的 tV）只做过数字时间戳，不是 IO 时序签核。
5. 综合、STA、CDC、PVT、模拟阵列：全部未做。

**终态：`WAITING_FOR_T6A_RUN02_INDEPENDENT_REVIEW`。**
