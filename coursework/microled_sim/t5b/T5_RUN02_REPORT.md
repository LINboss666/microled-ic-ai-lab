# T5-B RUN02 报告：五颗真实 RTL 联合仿真（唯一一次授权复验）

日期：2026-11-18
授权：`T5_RUN02 = CONDITIONALLY_AUTHORIZED_ONCE`（≤1 次正式 ModelSim，仅改 TB）
本次使用：**1 次**（`vsim` 29 s，仿真到 10,425,265 ns）。**未跑第二次，未改 RTL。**

## 0. 结论

| 裁定项 | 结果 |
|---|---|
| `T5_RUN02` | **PASS_56_OF_56** |
| T6 五条件 | `1/1/1/1/1`，`RUNNER_EXIT=0` |
| 编译 | 0 errors / 0 warnings |
| Phase B 健康帧 | 1025 窗 / 787,200 字节 / **0 失配**（与 RUN01 完全一致，无退化） |
| Phase C 换表 | 恰好 1 个全暗窗（槽 1028），768 个 BLANK 低采样全关，随后按表 B 恢复非零导通 |
| Phase D/E/F/G | 故障、恢复、RX 污染全部保持通过 |
| RTL 改动 | **0**（十份 RTL/监视器 SHA 与已验收版本逐字节一致） |

## 1. 本轮只改 TB 三处语义（逐行 diff 在包内）

| 项 | 改法 |
|---|---|
| **E1 列归属/epoch** | 新增 `tab_b_slot`：换表槽（1027）起**装载**的列用表 B；显示槽 S 用 `(S-2) >= tab_b_slot` 判定，不再在 COMMIT 当刻一刀切。显式复位把 epoch 清零（Phase E/G 从 A 重新开始）。 |
| **E2 精确暗窗** | 每个 **BLANK 低**采样沿（不是单点、不是二态 `==`）检查 `d0_ch_en === 384'd0 && d1_ch_en === 384'd0`；暗窗由 TB 自己的换表记账推导（`switch_done && slot_done == switch_slot+1`），**不读 DUT 的 `col_valid`**；并有 `>=760` 的非零采样下限。 |
| **E3 PWM/映射** | 暗窗的 raw/map/PAM **照常比 768 字节**（按装载时的表 A），但 16 路 PWM 期望置 0 并仍计入 `pwm_windows`，不跳过该窗。 |

三处之外：新增取证打印 `T5_SWITCH_DARK / T5_SWITCH_EPOCH / T5_SWITCH_RESTART`、换表与 FAULT 的短窗口 `$dumpon/$dumpoff` 与 `T5_VCD_MARK` 绝对时间。**56 条断言名称、D01–D56 编号、健康帧判据一字未动**（`tools/t5_run02_precheck.py` 与 RUN01 快照逐名比对：56==56，零增删零重复）。

## 2. 原生结果

```
PHB slots=1027 windows=1025 sel_bad=0 tag_bad=0/0 frm_bad=0
    byte_bad=0 cont=787200 onehot_bad=0 pwm_bad=0/1025 no_win=0
PHC switch_slot=1027 bank=0/0 colv=0/0
T5_SWITCH_DARK window_slot=1028 low_cycles=768 invalid_cycles=768 on_viol=0 pwm_zero_viol=0
T5_SWITCH_EPOCH epoch_A_windows=1027 epoch_B_windows=2
T5_SWITCH_RESTART recovered_nonzero=1 bad_windows=0
PHD samples=400 bankflip=0 pend_bad=0 on_viol=0
PHF vcol=11 bad_col=8 err=000001 fsm=3
T5_COUNTS slots=5 windows=1040 compared_bytes=798720 byte_bad=0 sel_bad=0
    onehot_bad=0 tag_bad=0/0 frm_bad=0 pwm_bad=0 pwm_windows=1040
    dark_samples=4512 dark_viol=0 idle_blanklow=0 fault_blanklow=0
```

关键三点：

1. **暗窗是"实测全暗"而不是"没有窗"**：槽 1028 有 **768 个 BLANK 低采样**，其中 **768 个采样期 `col_valid=0`**，**0 个采样出现任何通道导通**，**0 个 PWM 零期望违约**。
2. **该窗内容仍然逐字节正确**：账本 `1028,2,1,2,2,1,2,1,0,0,1` —— 列/帧/两片标签全对、`bad_bytes=0`、`lut_tab=0`（表 A，即装载时的表）、`dark_expected=1`。**没有通过删掉这窗来消掉 1524。**
3. **随后按表 B 恢复**：`epoch_B_windows=2`、`recovered_nonzero=1`、`bad_windows=0`，窗 1029/1030 的 `lut_tab=1` 且 `bad_bytes=0`、PWM 非零导通。

## 3. 零仿真硬门（运行前完成并封存）

| 门 | 结果 |
|---|---|
| 十份 RTL/监视器 + 壳 SHA（壳须等于 RUN01 值） | PASS |
| 56 条断言名与 RUN01 快照逐名一致、无重复、无 `$fatal` | PASS |
| 语义静态检查：epoch 比装载槽 / 暗窗不读 DUT / 768 字节不跳过 / 暗窗 PWM 期望 0 | PASS |
| **原始 LUT 重放**：错误 epoch → **1524**（raw 0 + map 762 + PAM 762，与原生 `slot=1028 bad_bytes=1524` 逐位一致）；正确 epoch → **0** | PASS |
| 负控：暗窗单通道导通 → **REJECT**；暗窗零样本（空洞）→ **REJECT** | PASS |
| 十二源文件 `vlog` | 0/0 |

## 4. 证据包内容

- 原始 256×9 LUT HEX（`t3b/GRAY_LUT_DEFAULT.hex.txt`，SHA `e3e39b43…cb25`，878 B）**首次直接入包**；
- 三段短窗口 VCD 切片：启动（0–30 µs）、**换表 10.0415–10.0460 ms**、**FAULT 10.0806–10.0940 ms**，均带 `T5_VCD_MARK` 绝对时间；
- 1040 行逐列账本（新增 `lut_tab` / `dark_expected` 两列），全 0 失配；
- RUN01 原始失败证据**未覆盖**（仍指向前一包 SHA `548d4757…`）；
- 逐行 TB diff（+102/−24 行，全部为上述三处语义与取证输出）。

## 5. 未做与边界

SPI/寄存器文件、Pure 8-bit PWM、PAM_CFG=01、模拟电流阵列、STA/CDC/PVT、光学标定：**均未做**。
本轮的 `PASS` 仅指"五颗真实数字 RTL 在上述 56 条判据下的联合数字行为"，不含任何模拟/物理签核。
`main` 未动、无 PR、无 force、无自签 GO。

**终态：`WAITING_FOR_T5_RUN02_INDEPENDENT_REVIEW`。**
