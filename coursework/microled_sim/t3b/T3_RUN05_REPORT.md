# T3 RUN05 报告（单次限定复验）

日期：2026-11-15 ｜ 授权依据：《MicroLED T3 RUN04 独立复审与 RUN05 单次授权_20261115.md》

## 0. 终态

**`T3_RUN05 = PASS 52/52`（唯一一次授权内运行）**
终态：`WAITING_FOR_T3_RUN05_INDEPENDENT_REVIEW`。未启动 T4/T5/Spectre/MC/OA/STA，未动 main，未开 PR，未自签 GO。

## 1. 正式运行结果（唯一一次，2026-11-15 21:25:49，耗时 4 s）

| 验收条件（授权合同 §四） | RUN05 原生结果 | 判定 |
|---|---|---|
| transcript 精确 52 条、52 PASS、0 FAIL | `COURSE_RTL_ASSERT_COUNT=52 / PASS_COUNT=52 / FAIL_COUNT=0`，PASS 名无重复 | ✅ |
| `COURSE_RTL_RESULT=PASS` | `COURSE_RTL_RESULT=PASS` | ✅ |
| T6 五条件全 1、checker 退出 0 | `CHECK0..CHECK4 = 1/1/1/1/1`，`RUNNER_VERDICT=PASS`，`RUNNER_EXIT=0` | ✅ |
| 编译 0 错 0 警、vsim 无 `$fatal` | vlog `Errors: 0, Warnings: 0`；CHECK0 `errors=0 fatal=none` | ✅ |
| D42 原生统计 opened=9 / closed=8 / counted=8 / min=384 / max=384 / dropped=1 | `T3_WINDOW_CENSUS opened384=9 closed384=8 counted=8 min=384 max=384 dropped=1` | ✅ 逐字命中 |
| 列 0/1/2 oracle 差分、D19 全 384 路导通、D20 黑码、D21 满码 64 tick、故障关断、非法长度继续通过 | `PASS D13_col2_oracle_bank_match` `D14_col2_oracle_tag_col` `D15_col2_oracle_not_corrupt` `D19_all_384_on_time_matches_lut` `D20_black_code_never_on` `D21_full_code_64_ticks`，及 D22–D37 全部继续执行并通过 | ✅ |

D42 六个分项：守恒式 `9 == 8+1` 成立、`dropped=1 ≤ 1`、`closed=8 ≥ 8`、`counted==closed`、`min=384=max`。

## 2. 锁源证据（预检，零 ModelSim）

| 项 | SHA-256 | 说明 |
|---|---|---|
| `rtl/data_driver.v.txt`（仓库/恢复/RUN04 运行时三处一致） | `896a3c541794c595e8b2a52d4927ac2e42e8849aeede3a55cc622d0ca0061f5e` | 未改 Data RTL，与授权要求一致 |
| RUN05 运行时 TB（恢复自仓库） | `2609627ac590d6cce48867ce0eb63915f9a58cb357cf144b80c937f9df71c6a6` | 修复版 |
| **RUN04 原生运行时 TB 原件**（`t3_run04/src/tcon_t3_tb.sv`，已保留） | `689e0d8902695fc808b4150e92ece81be71b503ea6e3db702640cf83804e67ee` | 与复审报告记录的 RUN04 执行 SHA 一致 |
| runner `run_tcon_t3.sh` | `c1668f452297ae51b073fd088106c30791ee166b4ffe4573fd6ded5dcb07d9a3` | **源码未修改**；`MIN_ASSERTS` 为 runner 既有环境变量覆盖（第 32 行），外部传 `MIN_ASSERTS=52 ≥ FLOOR=51` |
| LUT `GRAY_LUT_DEFAULT.hex.txt` | `e3e39b43f7e0f76e5f2865338c271402a1da5b1fd8b4e6193c0ed668f79cb253` | 未改 |

**RUN04 原生 TB vs RUN05 TB 功能差异（diff 证据已存档）**：仅 `win_nb_q <= win_nb;` 一行功能代码 + 6 行注释，其余逐字节相同。授权范围（"只允许修改这一项功能代码"）完全满足。

## 3. 其余预检（全部通过后才启动 ModelSim）

1. `win_nb_q` 单写：全 TB 唯一写入点 = posedge-dclk census 块第 191 行；`win_q` 快照同块同域。
2. `tools/t3_precheck.py` → `PRECHECK_OK`：15 个 TB dclk 域状态变量 0 双写者；F1/F2/F3 结构不变；52 条断言库存无缺失、判据无降级（D42 六条件与 RUN04 运行版逐字相同，`win_closed_384>=8` 强化已在 RUN04 版生效）。
3. `tools/t3_phase_timeline.py` → 两相位（LATCH 下降沿 20k+5 / 20k+15 ns）逐沿推演 byte0..byte383 流完全一致，DUT 与 oracle（+1 ns settle）在全部 384 个沿读同一字节。
4. 窗口计划静态枚举：场景 16 槽中 14 个 384 计划，P6 复位前实际开出 9 个（**RUN04 原生已观测** opened384=9 / dropped=1），故 closed=8 为修复后的推论——RUN05 原生输出 `closed384=8` 证实。
5. 编译预检（15:22，纯 vlog，**未调用 vsim，不耗仿真次数**）：0 错 0 警。

## 4. 证据清单（本机原生目录 `D:/ic617_course_sim_20261112_native/`）

- `t3_run05/`：`00_source_sha256.txt`、`01_vlib.log`、`02_vlog.log`、`03_vsim.stdout`（原生 transcript）、`05_t6_check.txt`、`transcript`、`t3_lut.hex`、`work/`
- `t3_run05.runner.log`：runner 全输出
- `t3run05_precheck/`：`00_run05_source_identity.txt`、`03_vlog.log`（编译预检）、`10_diff_run04_native_tb_vs_run05_tb.txt`、`20_t3_precheck.txt`、`21_phase_timeline.txt`、`22_census_expectation.txt`、`30_runner_identity.txt`
- `t3_run04/src/tcon_t3_tb.sv`：RUN04 原生 TB 原件（SHA `689e0d89…`）

## 5. 范围声明（不变项）

- 本轮证据仅在 **Hybrid 6-bit PWM + 理想 LUT 数字模型** 下成立。PAM_CFG=01、Pure 8-bit PWM（w_eff 位宽 + 30ns tick）、LUT 表的光学标定仍为 OPEN。
- D42 测量口径：DCLK 上升沿上 `din_valid` 有效的字节采样数（384 个），非全部连续 DCLK 脉冲数。
- T4 Scan Driver、T5 联合验证、综合/STA/CDC、384 路模拟恒流阵列均未启动。
- 远端推送：仅提交方保存 push/回读记录，未经审核环境独立认证。
