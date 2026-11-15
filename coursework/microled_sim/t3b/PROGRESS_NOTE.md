# PROGRESS_NOTE —— T3/T4 第 1 轮（2026-11-15）

按任务书 §E 要求逐项交代。

---

## 1. 本轮做了什么

| 段 | 内容 | 仿真 |
|---|---|---|
| A | 冻结 Data/Scan 内部数字接口（`t3b/T3T4_SCOPE.md`）与灰阶码制（`t3b/GRAY_CODE_MAPPING.md`） | 0 |
| A | 写出码表推导器 `tools/gray_lut_derive.py`，产出 `GRAY_LUT_DEFAULT.hex.txt/.csv`，四项数字复现 V1.3 | 0 |
| B | 新建可综合 `rtl/data_driver.v`（384 路 / 双 bank / 256×9 双银行 LUT / 共享 PWM 引擎 / 硬件优先关断） | — |
| B | 新建 `tb/tcon_t3_tb.sv`（51 条断言）+ `tb/run_tcon_t3.sh` | — |
| B | 正式仿真 2 次，均 FAIL；第 2 次用 DBG 探针定位根因 | **2/2** |

## 2. 当前系统示意（谁产生信号）

```
TB 针脚发生器 ──dclk 20ns / LATCH 40ns@cyc828 / PWM_START 40ns@cyc840 /
                 PWM_TICK 120ns / BLANK≥cyc768 / D0[7:0]──┬─▶ data_driver  (被测)
                                                          └─▶ data_model   (独立 oracle)
```
本 TB **不接 TCON**：T3 是单模块验证，激励按冻结的 V1.3 数字在 TB 里独立产生，
这样 Data 的验证不依赖 TCON 是否已经测过。

## 3. 新旧模块路径

| 角色 | 路径 | 说明 |
|---|---|---|
| 被测（新） | `coursework/microled_sim/rtl/data_driver.v.txt` | 可综合 384 路数字核 |
| oracle（旧，保留） | `coursework/microled_sim/rtl/data_model.v.txt` | T2B-BR 已验收的行为替身，仅作差分参照 |
| TB（新） | `coursework/microled_sim/tb/tcon_t3_tb.sv.txt` | 51 条断言 |
| runner（新） | `coursework/microled_sim/tb/run_tcon_t3.sh` | FLOOR=51 |
| 文档（新） | `coursework/microled_sim/t3b/*.md` | 接口冻结 / 码制 / 本轮报告 |

## 4. 实测覆盖了什么（以及没覆盖什么）

| 项 | 状态 |
|---|---|
| LUT 双银行写入 + `COMMIT` 拒绝非法镜像（黑码不为 0） | **通过**（`D07`/`D08`） |
| 修正后 `COMMIT` 被接受、`lut_valid` 置位 | **通过**（`D09`） |
| 黑码/满码两条硬规则 | **通过**（`D10`，读的是码表本身） |
| 384 字节装载 → 显示 bank | **未通过**：所有窗口只有 383 字节（根因见 §5） |
| 384 路灰阶导通拍数 | **未验证**：`ch_en` 从未拉高 |
| 短列（383）不显示 | **通过**（`D24`/`D25`/`D29`）—— 但它是在"全都没提交"的情况下通过的，**不能算独立证据** |
| BLANK 期间无导通 | **通过**（`D38`）—— 同样是"从没拉高过"的空洞通过 |
| 故障同拍关断 | **通过**（`D33`/`D34`）—— 同上，空洞 |

**本轮 25 条 PASS 里有一半是空洞通过**，我不把它们当验收证据，只把 3 条与码表/提交互锁相关的算数。

## 5. 失败件与根因

| run | 目录 | 结果 | 根因 |
|---|---|---|---|
| #1 | `D:/ic617_course_sim_20261112_native/t3_run01` | 27/51 | 未定位（无探针） |
| #2 | `.../t3_run02` | 25/51 | **同一 always 块内 NBA 覆盖**：捕获块的 `wcnt<=wcnt+1` 被随后 `falling` 分支的 `wcnt<=0` 覆盖 |

决定性证据（run #2 原生 transcript）：

```
DBG_LATCH t=36415000 latch=1 slot=1 cyc=828 sent=384 dut_wcnt=383 colv=0 orc=1
```

同一窗口：TB 发 384 字节，oracle 收 384 并提交，新 RTL 只收 383 → byte0 在 arming 拍被吃掉。

两次运行的 transcript、vlog、runner 日志全部保留，未删任何失败件。

## 6. ModelSim 运行次数

| 阶段 | 授权 | 已用 |
|---|---:|---:|
| A（规格冻结） | 0 | **0** |
| T3 内部数字 | 2 | **2** |
| T4 内部数字 | 2 | **0**（未开始） |
| T5 系统联合 | 不在本轮授权 | 0 |

Spectre / Monte Carlo / OA / STA：**全 0**。

## 7. 保持 OPEN 的项

| 项 | 原因 |
|---|---|
| `PAM_CFG=01`（4 档 PAM 对照） | V1.3 只写"4档对照"，未给档位映射 |
| `GRAY_MODE=00`（Pure 8-bit PWM） | 需要 30 ns tick / 256 tick，TCON 侧发生器未实现 |
| 光学单调性 / 有效灰阶数 | 段0705：LUT_VALID 只代表写满与黑满码检查 |
| `I_PAM0…7` 真实档值与修调 | 由 5 µm LED I–V / 光学标定决定，数字侧只输出 3-bit 档位码 |
| `BLANK` 异步路径的毛刺/CDC | 本轮按规格做组合优先关断，未做 CDC 签核 |
| Scan 512 路内部数字（T4） | 本轮未开始 |

## 8. Git

- 分支 `course/microled-assignment-sim-20261112`，`main = 23e471c` 未动
- 本轮提交与推送状态见包内 `gates.txt`
- 未合并、未开 PR、未自签 GO

## 9. 停在哪

`WAITING_FOR_T3_T4_INDEPENDENT_REVIEW`，并请求 **T3 追加 1 次 ModelSim** 验证已应用的 F1/F2/F3。
