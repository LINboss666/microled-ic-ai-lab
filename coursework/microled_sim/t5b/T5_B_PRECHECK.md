# T5-B 预检与断言表（写于正式 vsim 之前，非运行后拟合）

日期：2026-11-18
依据：`MicroLED_T5B_五芯片真实RTL联仿_Qoder限定任务书_20261118.md`（B1–B8）
授权：**最多 1 次正式 ModelSim**。本文件在启动该次 vsim 之前完成并归档。

---

## 1. 被测对象（真实 RTL，非行为替身）

| 芯片 | 模块 | SHA-256 |
|---|---|---|
| TCON ×1 | `tcon_top` + `tcon_timebase` / `tcon_video_rx` / `tcon_col_bank` / `tcon_slot_seq` / `tcon_data_tx` | `0f8e9169…2363` / `1bb27df8…53cd` / `9c994527…7e06` / `97c2b4bf…a7e4` / `f9b4f317…4903` / `cc9d35f9…13d1` |
| Data ×2 | `data_driver`（`USE_DIN_VALID=0`，`din_valid` 接 `1'b0`） | `6d0c5f83…59ab`（T3-H2 验收版） |
| Scan ×2 | `scan_driver`（CHIP_ID=0/1） | `6ee3ad38…29a4`（T4 验收版） |
| 观测 | `data_pin_mon` ×2、`scan_pin_mon` ×1（T2B 原样复用） | `9a8ba4f2…3d74` / `7c280e13…4d10` |

`rtl/` 下十个文件与已验收版本**逐字节一致**（`tools/t5_b_precheck.py` 第 1 节十项全 ok）。

## 2. 结构结论（B1/B2）

- 接线壳 `tb/t5_five_chip_shell.sv.txt` 只做引脚直通，无 `dv_stub`/`bw_arm`/`bw_cnt`（T5-A 的 385 沿缺陷已删除）；
- 两颗 Data 均 `USE_DIN_VALID=0`，`din_valid` 接常量 `1'b0`，壳内不存在任何"造 valid"的逻辑；
- `load_active` 只作为观测输出存在，**没有**接到 `din_valid`；
- LUT 以 TB 端口注入 256×9 并 COMMIT，两片 `lut_valid` 必须为 1 才允许输出（T3-H 门控）。

## 3. 时序前提（离线模型证明，`tools/t5_framing_model.py` / `t5_offline_timeline.py`）

| 命题 | 结果 |
|---|---|
| 一帧 = 576×977 + 448×976 | **1,000,000 cycles** ✅ |
| 起始相位（slot0 时 DCLK 低）+ Data 在上升沿看到**本拍** LATCH | 1024/1024 槽逐字节有序，**0 失败** ✅ |
| 同一模型改成 `pre`（看到上一拍） | 7 槽中 3 槽错位 → 模型可分辨 ✅ |
| 预取晚一拍 | 7 槽中 3 槽错位 → 模型可分辨 ✅ |

流水映射（本 TB 断言依据）：装载窗在槽 S 的 `[832,1600)` 发列 S 的 768 字节 → 槽 S+1 的 LATCH 提交 → 槽 S+2 的显示窗点亮。
因此**槽 S 的显示窗必须显示列 S-2**，且该列正是 SCAN_STB 在槽 S-1 锁进 Scan 的 `COL_ID`。

## 4. 预写计数预期（正式运行前固定）

Phase B 跑 1027 个槽（帧 0 全部 + 帧 1 的列 0）：

| 量 | 预期 | 依据 |
|---|---:|---|
| 显示窗数 | **1025** | 1027 槽 − 前 2 槽预充 |
| 逐窗比较字节数 | **787,200** | 1025 × (384+384) |
| 每端口装载窗 | **≥1020**（实测 1026） | 每槽一个 384 字节窗 |
| SCAN_STB 数 | **≥1020**（实测 1026） | 每槽一个（预充后） |
| PWM 判据窗数 | **≥1000**（实测 1025） | 每显示窗一次，每窗 64 tick |
| PWM 通道覆盖 | **384/384 两片** | 每窗 8 通道、基址每次 +8 |
| 正常帧内"无窗槽" | **0** | 只有预充 2 槽允许无窗 |

Phase C：换表必须落在 **LATCH 上升沿**；随后**恰好 1 个暗窗**，再恢复且映射为表 B。
Phase D：FAULT 期间连续 **400 个 DCLK 沿** 银行不翻、`cmt_pend` 恒 1、768 路 `ch_en` 恒 0。
Phase F：767 字节列 → `err_flags[0]`，TCON 锁存 FAULT，不自动恢复。

## 5. 断言表（56 条，全部在运行前登记）

| 组 | 断言 | 判据 |
|---|---|---|
| A 配置/空闲 | D01–D08 | IDLE、无列、未提交、双片 COMMIT、银行翻转、提交未被拒、空闲 300 沿全关、IDLE 不释放 BLANK |
| B 全帧 | D09–D31 | 预充无窗、进入 ACTIVE、DCLK=20 ns、两端口每窗 384 B、窗口数相等、payload 逐字节、无 X、1025 窗、Scan 选列==期望、1024 位合并独热、双片标签==Scan、帧号、768 B 内容/LUT/PAM、PWM 宽度、通道覆盖、每窗有导通、显示必双有效、正常帧无暗窗、STB 数、setup/hold、列 0/1/2/1022/1023/下一帧 0 |
| C 换表 | D32–D37 | 换表在 LATCH 沿翻双片银行、同沿失效显示、1 个暗窗、随后按表 B 恢复、无残留旧列 |
| D 故障+挂起提交 | D38–D44 | FAULT 锁存、400 沿不翻银行、pending 保持、768 路恒 0、释放后仍不翻（TCON 已锁存）、持续全暗、无 STB |
| E 恢复 | D45–D50 | 复位清 LUT、重新 COMMIT、预充无早窗、回 ACTIVE、有显示、无 RX 错误 |
| F RX 污染 | D51–D54 | 欠载置 `err[0]`、锁存 FAULT、永不释放 BLANK、清 FAULT_n 不恢复 |
| G 二次恢复 | D55–D56 | 复位+合法帧后可显示、内容仍逐字节正确 |

## 6. 负控（必须 FAIL，`tools/t5_negative_control.py`）

| 项 | 注入 | 结果 |
|---|---|---|
| NC1 | Data#1 列标签错 1 | `DATA1_TAG` ✅ 被拒 |
| NC2 | Scan 地址错 1 | `SCAN_SELECTION` ✅ 被拒 |
| NC3 | LUT 已换但显示银行仍是旧映射 | `BANK_MAPPING` ✅ 被拒 |
| 正控 | 全正确 | ACCEPT ✅ |

标签单射性：列 0/256/512/768 两两不同；同列不同帧号不同 ✅。

## 7. 编译闸（B8）

十二个源文件 + LUT 一起 `vlog -sv`：**0 errors / 0 warnings**。
VCD 只窗口化开启（起始/末列/换表/故障），上限 200 MB；`vsim` 墙钟上限 5400 s；TB 内另有 30 ms 绝对守卫。

## 8. 本轮明示不做

SPI/寄存器文件、Pure 8-bit PWM、PAM_CFG=01、模拟电流阵列、STA/CDC/PVT、光学标定、main 合并、PR、自签 GO。
