# DATA-7B 单通道固定电流 PWM 响应：实测报告（R1 更正版）

日期 2026-10-21 交付，2026-10-22 由 **DATA-7B-R1** 离线更正。原基线
`c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37`，被接受的 DATA-7A 内容版本
`f68449672774ac9266ba9e4893024e4f3027dd9d`。

| 层 | 位置 | 状态 |
|---|---|---|
| 原交付（T） | `results/evidence/dd1_d7b_r11_main/`，分支 `poc/data-pwm-d7b`，提交 `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50` | **完全冻结、未改一字节**；用 R1 复核器重跑它得 14 项具名 FAIL（`reports/dd1_d7b_review_fix_r1.md` §3） |
| R1 更正证据 | `results/evidence/dd1_d7b_r1_r20261022_122204_05417c/`，分支 `poc/data-pwm-d7b-r1` | 本报告 §3–§8 的每个数字都取自这里，不是手抄 |
| 逐项更正说明 | `reports/dd1_d7b_review_fix_r1.md` | 旧结论保留在 Git 历史里，不抹去"旧交付曾报错"的事实 |

电路、PWL、24 份原生 deck、冻结 RTL/TB、主 case 表、黄金表、`±0.5 LSB` / `150 nA` 判据与模拟条件本轮一律
未改；本轮新增 Spectre 进程 **0**、新增 OA 写入 **0**、新增四态 RTL 仿真 **17**（上限 17）。
本报告不记录自身文件大小或摘要。

## 1 边界图

```text
  [冻结 RTL, 逐字节 = A 的内容版本]
  rtl/dd1_d7a_gray_ctrl.sv
        |  iverilog -g2012 (真实四态仿真)                <- 实际 MOS? 否, 数字模型
        v
  tests/dd1_d7b/tb_dd1_d7b_pwm.sv  -->  VCD (data_en / data_en_b / obs_tick / win_state ...)
        |  scripts/dd1_d7b_trace.py: 黄金表核对 + t0=消费 tick 的采样沿 + 平移 2500 ns
        v                                             <- 离线验证激励, 不是产品控制通路
  有限斜率 PWL (0/1.8 V, 基准 2 ns 斜坡; 10 ns 为敏感性补测)
        |  Vde (data_en 0) vsource dc=0 type=pwl wave=[...]
        v
  +---------------------------------------------------------------+
  | dd1_d7b_pwm_stage  = 实际 MOS 被测区, 展开 7 管                |  <!-- check:skip 该数字由 `scripts/dd1_d7b_run.py --selftest` 的 master 混合断言机检 (n18x1,p18x1,n33×4,n33_dnw_4t_ckt x1 = 7)，逐文件 netlist 解析器不展开层级 -->
  |   Xbias  data_bias_ref      : Mref n33 (栅漏短接, 由 IREF 注入)|
  |   Xinv   dd1_inv18          : Mn1 n18 / Mp1 p18  -> data_en_b  |
  |   Xsink  data_sink_1ch      : Mpass_local n33_dnw_4t_ckt,       |
  |                               Mcas n33, Mout n33, Mbleed_local n33 |
  +---------------------------------------------------------------+
        |  Ip_out (clamp data_out) iprobe -> save Ip_out:i           <- 零负担安培表
        v
  Vclamp (clamp 0) vsource dc=1.2   (像素=钳位, 无 LED/Vf/VLED 模型)
  分析: tran stop=<窗口末+200 ns+50 ns> maxstep=0.5 ns (4 例 0.25 ns) method=gear2only
  模型: include "${QODER_PDK_LIB}" section=tt; 温度从 psf 的 temp 列反读并与 deck 交叉核对
```

R1 新增的一层闭环：这 17 份边沿文档现在**又被冻结 RTL + 冻结 TB 重跑过一次**（17 次新仿真），逐字段比对
304 项全 `AGREE`，新 VCD 连同 `$date`/摘要随包交付，并与原生 run 身份分列（`rtl_reverify.csv`，检查名
`RTL_EDGES_REVERIFIED`）。验证源（PWL、钳位、IREF、VCAS）仍不是被测产品通路；被测部分是 7 只真实 MOS。
本节同时说明本轮**没有**把 DATA-6 的 29 管顶层接到灰阶控制器上：wrapper 从 `data_en` 输出级接口进入，
不含灰阶计数器、8-bit 存储与片内数字驱动器。  <!-- check:skip 该数字由 `scripts/dd1_d7b_run.py --selftest` 的 master 混合断言机检 (n18x1,p18x1,n33×4,n33_dnw_4t_ckt x1 = 7)，逐文件 netlist 解析器不展开层级 -->

## 2 被测层级与器件

| 实例 | master | 展开 MOS |
|---|---|---|
| `Xbias` | `data_bias_ref` (`dd1_d6_bias_core.scs`) | 1 (`n33`) |
| `Xinv` | `dd1_inv18` (`dd1_d6_inv18.scs`) | 2 (`n18`, `p18`) |
| `Xsink` | `data_sink_1ch` (`dd1_d6_sink_core.scs`) | 4 (`n33`×3, `n33_dnw_4t_ckt`) |
| 合计 | | **7** = `n18×1, p18×1, n33×4, n33_dnw_4t_ckt×1` |

器件端网/尺寸逐条回读在两个包的 `decks/`（deck 原文）与 `environment.json`（master 的仓库/落盘摘要与剥除行
计数；R1 另含 `frozen_tools` 三项共享工具摘要，与 T 一致）。

冻结 leaf 落盘时剥除的只有 `parameters <port> <direction>` 方向注释行（本机 SFE-59 实测），每文件计数与
器件语句/端序摘要见下：

| master | 仓库字节 | 剥除行数 | 剥除前/后器件摘要 |
|---|---:|---:|---|
| `dd1_d6_bias_core.scs` | 4115e2d17a86 B | 2 | 一致（入口断言，不同即拒收） |
| `dd1_d6_sink_core.scs` | 6cfe2338014a B | 6 | 一致（入口断言，不同即拒收） |
| `dd1_d6_inv18.scs` | 04cd68330875 B | 4 | 一致（入口断言，不同即拒收） |
| `dd1_d7b_pwm_stage.scs` | cee61136e81b B | 6 | 一致（入口断言，不同即拒收） |

## 3 案例完成情况与实际执行（更正）

| 项 | 数量 | 说明 |
|---|---:|---|
| 计划 DUT 分析 | 24 | 与主 case 表一致 |
| 已产生判定行的窗口 | 27 | 26 判定行 + 1 标定行 |
| 正常码窗口 | 15 | |
| 安全场景窗口（中止+恢复） | 4 | BLANK/FAULT 各两窗，恢复窗齐备 |
| 收敛复测窗口 | 5 | 0.25 ns 复测，母案例全部在包内 |
| 输入斜率敏感性 | 1 | 10 ns |
| 电气判据 FAIL | 0 | 判据未改 |
| BLOCKED / 工具失败 | 0 | R1 把 T 遗留的 1 项 `BLOCKED_MISSING_PARENT` 离线补齐（§6） |
| **整轮真实 Spectre 进程** | **59** | 30 preflight + 29 dut，逐目录见 `launches_reconcile.csv`；旧版此格写 27，错 |
| 原任务书额度 / 追加后上限 / 超额 | 52 / 56 / **+3** | 见 `reports/tasks/DATA-7B-BUDGET-01.md`；旧版写"超额 0"，错 |
| **本轮（R1）新增 Spectre** | **0** | 离线重测：未建 SSH、未建任务根，`NEW_SPECTRE_LAUNCHES 0` |
| 本轮新增四态 RTL 仿真 | 17 | 上限 17，已用满；身份与原生 run 分列 |

旧交付 `process_ledger.csv` 的 58 行是 `preflight 27 / dut 27 / static_negative 4`，其中
`launches_used_after` 最大 42 只是 `r11_main` 单 run 的局部计数；整轮真实总数只由
`launches_reconcile.csv` 与 guest 日志计数得出（原因与逐目录账见 `reports/tasks/DATA-7B-BUDGET-01.md`）。
R1 起账本按 run 隔离、任务级账户持久追加，本轮 3 次离线导出产生的 75 条 `REFUSED_NO_LAUNCH` 也留在
`launch_account.csv` 里，不占额度、不删行、不改小。标定行与黑码/一码等 24 个案例全部指向**已真实运行并留档**
的原生 run，交付轮没有为它们再启动进程。

**样本身份**：每个窗口都标 `reused_from=adcdf27…`（原生 run、`src_launch_id`、deck/PWL/raw/log/psf 摘要逐行
在 `cases.csv`），本轮重新测量**不冒充**新的原生结果。交付包内 26 个电荷样本序列与 `dd1_d7b_r11_main` 的同名
序列**逐字节相同**（行摘要相等，`series_vs_accepted_bundle=IDENTICAL_BYTES`，由
`CHARGE_SERIES_MATCHES_ACCEPTED` 独立复核）；新增的 27 个序列（标定带 1 个 + 边沿片 26 个）显式标
`NEW_IN_R1_NOT_IN_ACCEPTED_BUNDLE`。

## 4 标定（更正：值现在有样本、有来源）

T 的标定行只有记录值（`verdict=REUSED`、`temp_read` 空），审核者无法复算 3.0..3.5 µs。现在标定带样本随包交付
（`charge_D7B-CAL_cal.0001.csv`，1,000 条），下表每个量都从这些字节重算：

| 量 | 值 | 窗 (ns) | 带内样本 | 积分跨度 (s) | section | temp (°C) | 读取来源 |
|---|---|---|---:|---:|---|---:|---|
| `Ical_A` | 1.493190564e-05 A | 3000.0..3500.0 | 1000 | 4.994999999998259e-07 | `tt` | 27.0000 | section from deck include line; temp from psf header temp column |
| `OFF_baseline_max_abs_A` | 7.338564169e-13 A | 1500.0..1900.0 | - | - | `tt` | 27.0000 | section from deck include line; temp from psf header temp column |
| `CAL_tail_max_abs_A` | 3.850281892e-09 A | 4400.0..4500.0 | - | - | `tt` | 27.0000 | section from deck include line; temp from psf header temp column |

判据：`Ical` 在 15 µA ±5 % 内；OFF 基线与末段 `max|I|` 均 ≤ 150 nA。`section`/`temp` 不是硬编码 ——
复核器要求二者能分别从 deck 的 include 行与 psf 头的 `temp` 列复现并互相核对
（`CALIBRATION_SAMPLES_RECOMPUTED`、`DECK_AND_PWL_BOUND`）。24 个案例行的 `section_read/temp_read` 全部是
`tt / 27.0000`。

## 5 电荷与时间结果（R1 重算，含修正的入带与关断）

T 的报告在这张表里把 19 个窗写成 `SETTLED`（旧判据其实只要求"存在一段 10 ns 入带"），关断列在短码窗一律落在
窗口末；两处都已修（根因见 `reports/dd1_d7b_review_fix_r1.md` §2 的 B1/B2/B3）。`err (LSB)` 的判据仍是冻结的
±0.5 LSB，未放宽。

| case | 窗口 | N | Qwin (C) | Qexpected (C) | err (LSB) | err (pC) | 尾电荷 (C) | 峰值 (A) | 入带 | 最长入带 (ns) | 关断 | 关断延迟 (ns) | 末 100 ns max\|I\| | 判定 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---:|---:|---|
| `D7B-P30-C000` | normal | 0 | 5.635977864e-18 | 0 | 0.000013 | 0.000006 | 1.467696213e-19 | 7.338544869e-13 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | 0.0000 | OFF | - | 7.338482518e-13 | PASS |
| `D7B-P30-C001` | normal | 1 | 3.018093995e-13 | 4.479571693e-13 | -0.326254 | -0.146148 | 3.014875594e-17 | 1.678340206e-05 | NOT_SETTLED_WITHIN_PULSE | 8.6106 | OFF | 23.0376 | 1.507339539e-10 | PASS |
| `D7B-P30-C002` | normal | 2 | 7.495840474e-13 | 8.959143386e-13 | -0.326661 | -0.146330 | 3.027148448e-17 | 1.684527942e-05 | NOT_SETTLED_WITHIN_PULSE | 38.6106 | OFF | 23.0357 | 1.513475207e-10 | PASS |
| `D7B-P30-C016` | normal | 16 | 7.020917946e-12 | 7.167314709e-12 | -0.326810 | -0.146397 | 3.209931715e-17 | 1.684531296e-05 | NOT_SETTLED_WITHIN_PULSE | 458.6106 | OFF | 23.0357 | 1.604848691e-10 | PASS |
| `D7B-P30-C254` | normal | 254 | 1.136273474e-10 | 1.13781121e-10 | -0.343277 | -0.153774 | 2.892892682e-15 | 1.684531295e-05 | NOT_SETTLED_WITHIN_PULSE | 7598.6106 | OFF | 23.0357 | 1.146725725e-08 | PASS |
| `D7B-P30-C255` | normal | 256 | 1.144808723e-10 | 1.146770353e-10 | -0.437906 | -0.196163 | 4.483553467e-14 | 1.684531295e-05 | NOT_SETTLED_WITHIN_PULSE | 7658.6106 | OFF | 23.0357 | 2.06008782e-08 | PASS |
| `D7B-P50-C001` | normal | 1 | 6.008611396e-13 | 7.465952821e-13 | -0.195198 | -0.145734 | 1.780146718e-17 | 1.684490151e-05 | NOT_SETTLED_WITHIN_PULSE | 28.6106 | OFF | 23.0357 | 8.900516459e-11 | PASS |
| `D7B-P50-C255` | normal | 256 | 1.909322292e-10 | 1.911283922e-10 | -0.262743 | -0.196163 | 4.483553467e-14 | 1.684531295e-05 | NOT_SETTLED_WITHIN_PULSE | 12778.6106 | OFF | 23.0357 | 2.06008782e-08 | PASS |
| `D7B-H120-C00` | normal | 0 | 5.635977864e-18 | 0 | 0.000003 | 0.000006 | 1.467696213e-19 | 7.338544869e-13 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | 0.0000 | OFF | - | 7.338482518e-13 | PASS |
| `D7B-H120-C01` | normal | 1 | 1.645489046e-12 | 1.791828677e-12 | -0.081671 | -0.146340 | 3.051991327e-17 | 1.684531296e-05 | NOT_SETTLED_WITHIN_PULSE | 98.6106 | OFF | 23.0357 | 1.525894298e-10 | PASS |
| `D7B-H120-C02` | normal | 2 | 3.437299002e-12 | 3.583657354e-12 | -0.081681 | -0.146358 | 3.102904599e-17 | 1.684531296e-05 | NOT_SETTLED_WITHIN_PULSE | 218.6106 | OFF | 23.0357 | 1.551346003e-10 | PASS |
| `D7B-H120-C62` | normal | 62 | 1.109423634e-10 | 1.11093378e-10 | -0.084280 | -0.151015 | 9.678310821e-16 | 1.684531295e-05 | NOT_SETTLED_WITHIN_PULSE | 7418.6106 | OFF | 23.0357 | 4.652476618e-09 | PASS |
| `D7B-H120-C63` | normal | 64 | 1.144808723e-10 | 1.146770353e-10 | -0.109476 | -0.196163 | 4.483553467e-14 | 1.684531295e-05 | NOT_SETTLED_WITHIN_PULSE | 7658.6106 | OFF | 23.0357 | 2.06008782e-08 | PASS |
| `D7B-H200-C01` | normal | 1 | 2.84063226e-12 | 2.986381129e-12 | -0.048805 | -0.145749 | 1.801950617e-17 | 1.684531296e-05 | NOT_SETTLED_WITHIN_PULSE | 178.6106 | OFF | 23.0357 | 9.009528297e-11 | PASS |
| `D7B-H200-C63` | normal | 64 | 1.909322292e-10 | 1.911283922e-10 | -0.065686 | -0.196163 | 4.483553467e-14 | 1.684531295e-05 | NOT_SETTLED_WITHIN_PULSE | 12778.6106 | OFF | 23.0357 | 2.06008782e-08 | PASS |
| `D7B-BLANK` | aborted | 4.5 | 1.869465307e-12 | 2.015807262e-12 | -0.326687 | -0.146342 | 3.058265078e-17 | 1.684531296e-05 | NOT_SETTLED_WITHIN_PULSE | 113.6106 | OFF | 23.0357 | 1.529030575e-10 | PASS |
| `D7B-BLANK` | recovery | 16 | 7.02853889e-12 | 7.167314709e-12 | -0.309797 | -0.138776 | 3.209931715e-17 | 1.684232466e-05 | NOT_SETTLED_WITHIN_PULSE | 459.1117 | OFF | 23.0338 | 1.604849129e-10 | PASS |
| `D7B-FAULT` | aborted | 4.5 | 1.869465307e-12 | 2.015807262e-12 | -0.326687 | -0.146342 | 3.058265078e-17 | 1.684531296e-05 | NOT_SETTLED_WITHIN_PULSE | 113.6106 | OFF | 23.0357 | 1.529030575e-10 | PASS |
| `D7B-FAULT` | recovery | 16 | 7.02853889e-12 | 7.167314709e-12 | -0.309797 | -0.138776 | 3.209931715e-17 | 1.684232466e-05 | NOT_SETTLED_WITHIN_PULSE | 459.1117 | OFF | 23.0338 | 1.604849129e-10 | PASS |
| `D7B-N1` | normal | 0 | 1.146770353e-10 | 0 | 256.000000 | 114.677035 | 2.986381129e-12 | 1.493190564e-05 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | 0.0000 | NEVER_WITHIN_LIMIT | - | 1.493190564e-05 | EXPECTED_REFUSAL |
| `D7B-CVG-P30-C001` | normal | 1 | 3.018456967e-13 | 4.479571693e-13 | -0.326173 | -0.146111 | 3.014935082e-17 | 1.675323625e-05 | NOT_SETTLED_WITHIN_PULSE | 8.9335 | OFF | 23.1853 | 1.507339186e-10 | PASS |
| `D7B-CVG-P30-C255` | normal | 256 | 1.144806548e-10 | 1.146770353e-10 | -0.438391 | -0.196381 | 4.508323524e-14 | 1.681715859e-05 | NOT_SETTLED_WITHIN_PULSE | 7658.9335 | OFF | 23.1854 | 2.059957084e-08 | PASS |
| `D7B-CVG-H120-C01` | normal | 1 | 1.645520531e-12 | 1.791828677e-12 | -0.081653 | -0.146308 | 3.052052349e-17 | 1.681715858e-05 | NOT_SETTLED_WITHIN_PULSE | 98.9335 | OFF | 23.1854 | 1.525893568e-10 | PASS |
| `D7B-CVG-BLANK` | aborted | 4.5 | 1.869496793e-12 | 2.015807262e-12 | -0.326617 | -0.146310 | 3.058326348e-17 | 1.681715858e-05 | NOT_SETTLED_WITHIN_PULSE | 113.9335 | OFF | 23.1854 | 1.529029839e-10 | PASS |
| `D7B-CVG-BLANK` | recovery | 16 | 7.028600629e-12 | 7.167314709e-12 | -0.309659 | -0.138714 | 3.209999117e-17 | 1.683735425e-05 | NOT_SETTLED_WITHIN_PULSE | 459.1709 | OFF | 23.1825 | 1.604848553e-10 | PASS |
| `D7B-SLEW-P30-C001` | normal | 1 | 2.543352736e-13 | 4.479571693e-13 | -0.432233 | -0.193622 | 3.015128364e-17 | 1.500612863e-05 | NOT_SETTLED_WITHIN_PULSE | 4.1759 | OFF | 23.7056 | 1.507431686e-10 | PASS |

`D7B-P30-C001` 这一行要单独说明，避免被读成"少 32.6 % 电荷所以判据失败"：实测 `Qwin 3.018093995e-13 C`、
目标 `4.479571693e-13 C`，差 `−0.146148 pC` = `−0.326254 LSB`，**在冻结的 ±0.5 LSB 判据内**；这个比例的电荷缺口
来自脉冲建立段，不构成光学位数结论。

## 5.1 时间码与实际边沿/关断的对照（更正）

新增列全部来自交付样本：`de 50% down` 现在按该窗**声明的脉冲段**查找（找不到写 `NOT_FOUND` 并计入
`未找到的沿`，不回退到 `t1`）；黑码/N1 这类无导通沿的窗明确 `NOT_APPLICABLE_NO_CONDUCTING_EDGE`，不虚构关断
延迟；电流 10 %/90 % 用 `0.1/0.9 × Ical` 与明确方向，由相邻原始样本夹持。

| case | window | tick (ns) | t0 (ns) | t1 (ns) | de 50% up | de 50% down | 关断点 (ns) | 电流 10% | 电流 90% | 10→90 (ns) | 声明脉冲 | 未找到的沿 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `D7B-P30-C000` | normal | 30 | 3915 | 11595 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | NOT_APPLICABLE_NO_CONDUCTING_EDGE | 3915.0000 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | NOT_APPLICABLE_NO_CONDUCTING_EDGE | - | 0 | - |
| `D7B-P30-C001` | normal | 30 | 3915 | 11595 | 3915.0000 | 3945.0000 | 3968.0376 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-P30-C002` | normal | 30 | 3915 | 11595 | 3915.0000 | 3975.0000 | 3998.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-P30-C016` | normal | 30 | 3915 | 11595 | 3915.0000 | 4395.0000 | 4418.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-P30-C254` | normal | 30 | 3915 | 11595 | 3915.0000 | 11535.0000 | 11558.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-P30-C255` | normal | 30 | 3915 | 11595 | 3915.0000 | 11595.0000 | 11618.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-P50-C001` | normal | 50 | 3915 | 16715 | 3915.0000 | 3965.0000 | 3988.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-P50-C255` | normal | 50 | 3915 | 16715 | 3915.0000 | 16715.0000 | 16738.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-H120-C00` | normal | 120 | 3915 | 11595 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | NOT_APPLICABLE_NO_CONDUCTING_EDGE | 3915.0000 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | NOT_APPLICABLE_NO_CONDUCTING_EDGE | - | 0 | - |
| `D7B-H120-C01` | normal | 120 | 3915 | 11595 | 3915.0000 | 4035.0000 | 4058.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-H120-C02` | normal | 120 | 3915 | 11595 | 3915.0000 | 4155.0000 | 4178.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-H120-C62` | normal | 120 | 3915 | 11595 | 3915.0000 | 11355.0000 | 11378.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-H120-C63` | normal | 120 | 3915 | 11595 | 3915.0000 | 11595.0000 | 11618.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-H200-C01` | normal | 200 | 3915 | 16715 | 3915.0000 | 4115.0000 | 4138.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-H200-C63` | normal | 200 | 3915 | 16715 | 3915.0000 | 16715.0000 | 16738.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-BLANK` | aborted | 30 | 3915 | 11595 | 3915.0000 | 4050.0000 | 4073.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-BLANK` | recovery | 30 | 12135 | 19815 | 12135.0000 | 12615.0000 | 12638.0338 | 12144.8533 | 12151.8114 | 6.9582 | 1 | - |
| `D7B-FAULT` | aborted | 30 | 3915 | 11595 | 3915.0000 | 4050.0000 | 4073.0357 | 3925.4947 | 3932.1453 | 6.6505 | 1 | - |
| `D7B-FAULT` | recovery | 30 | 12135 | 19815 | 12135.0000 | 12615.0000 | 12638.0338 | 12144.8533 | 12151.8114 | 6.9582 | 1 | - |
| `D7B-N1` | normal | 30 | 3915 | 11595 | NOT_APPLICABLE_NO_CONDUCTING_EDGE | NOT_APPLICABLE_NO_CONDUCTING_EDGE | - | NOT_APPLICABLE_NO_CONDUCTING_EDGE | NOT_APPLICABLE_NO_CONDUCTING_EDGE | - | 0 | - |
| `D7B-CVG-P30-C001` | normal | 30 | 3915 | 11595 | 3915.0000 | 3945.0000 | 3968.1853 | 3925.4712 | 3932.1843 | 6.7131 | 1 | - |
| `D7B-CVG-P30-C255` | normal | 30 | 3915 | 11595 | 3915.0000 | 11595.0000 | 11618.1854 | 3925.4712 | 3932.1843 | 6.7131 | 1 | - |
| `D7B-CVG-H120-C01` | normal | 120 | 3915 | 11595 | 3915.0000 | 4035.0000 | 4058.1854 | 3925.4712 | 3932.1843 | 6.7131 | 1 | - |
| `D7B-CVG-BLANK` | aborted | 30 | 3915 | 11595 | 3915.0000 | 4050.0000 | 4073.1854 | 3925.4712 | 3932.1843 | 6.7131 | 1 | - |
| `D7B-CVG-BLANK` | recovery | 30 | 12135 | 19815 | 12135.0000 | 12615.0000 | 12638.1825 | 12144.8310 | 12151.8523 | 7.0213 | 1 | - |
| `D7B-SLEW-P30-C001` | normal | 30 | 3915 | 11595 | 3915.0000 | 3945.0000 | 3968.7056 | 3927.2108 | 3933.8194 | 6.6086 | 1 | - |

绝对时刻与延迟在表里分列（延迟另在 `cases.csv` 的 `de_fall_delay_ns`、`turn_off_delay_ns`）；关断延迟落在
23.03–23.71 ns，`pulse_edges_missing` 全表 0。`de 50% down` 与脉冲段一致：1 码在 `t0+30 ns`、2 码 `+60 ns`、
16 码到 `4395.0000`，中止窗按保护中止落在 `4050.0000`，恢复窗 `12615.0000`。旧版这张表有 12 行的
`de 50% down` 是空的，且短码窗"关断"一律等于窗口末（11595/16715/19815），两处均已更正。

## 6 数值收敛（0.5 ns 对 0.25 ns，更正）

T 把 `D7B-CVG-P30-C001` 记成 `BLOCKED_MISSING_PARENT`，但母案例 `D7B-P30-C001` 的字节本来就在包里（属表构建
缺陷，离线补齐即可，不需新仿真）；原先三处 `NOT_FOUND_BOTH` 的边沿差现在可复算为 `0.0000 ns`。5 对全部
`CONVERGED`，dQ / dPeak 与各自限值同列：

| case | 窗口 | 母案例 | dQ (pC) | 限 (pC) | dPeak (uA) | 限 (uA) | d交越 (ns) | 判定 |
|---|---|---|---:|---:|---:|---:|---:|---|
| `D7B-CVG-P30-C001` | normal | `D7B-P30-C001` | 0.000036 | 0.004480 | 0.030166 | 0.837662 | 0.0000 | CONVERGED |
| `D7B-CVG-P30-C255` | normal | `D7B-P30-C255` | 0.000217 | 0.004480 | 0.028154 | 0.840858 | 0.0000 | CONVERGED |
| `D7B-CVG-H120-C01` | normal | `D7B-H120-C01` | 0.000031 | 0.017918 | 0.028154 | 0.840858 | 0.0000 | CONVERGED |
| `D7B-CVG-BLANK` | aborted | `D7B-BLANK` | 0.000031 | 0.004480 | 0.028154 | 0.840858 | 0.0000 | CONVERGED |
| `D7B-CVG-BLANK` | recovery | `D7B-BLANK` | 0.000062 | 0.004480 | 0.004970 | 0.841868 | 0.0000 | CONVERGED |

## 7 负例（更正：单位写进列名，身份补齐）

`D7B-N1` 是真实改接线的原生负例；T 的表把 µA 数值填进名为 `_A` 的列且 `run_id` 为空，现在列名改为
`window_peak_uA` / `last_100ns_max_abs_uA`，并绑定 `src_native_run`、`launch_id` 与 deck/raw/transcript 摘要。
`D7B-N2` 是静态供电负例，只有 rc 与 stage 不算证据，故补上拒绝原文与 0 次启动。

| case | 种类 | 检出 | 关键量（单位写进列名） | 身份 | 判定 |
|---|---|---|---|---|---|
| `D7B-N1` | dynamic_wiring | YES | q_win=1.146770353e-10 C; `window_peak_uA`=14.93190564; `last_100ns_max_abs_uA`=14.93190564 | 原生 run `r11_main` / launch `r11_main/L032`; deck `0a2d21311e96`; raw `b1ac38ee1081`; 实际接线差异 = enable 网络 | EXPECTED_REFUSAL / WIRING_FAULT_DETECTED |
| `D7B-N2` | static_supply_negative | YES | rc=1; stage=supply_contract; 该目录 Spectre 启动=0; supply_fail=`net vss (Xstage port vss) has no independent source from reference node 0` | 原生 run `r11_reuse`; deck `ea68ee4e62b0`; 转录 `4e6948688535` | EXPECTED_REFUSAL / SUPPLY_CONTRACT_DETECTED |

`D7B-N1` 的常亮电流恰为标定值，所以净电荷正好 `+256.000000 LSB`；"接线错误被同一复核器检出"与实际 enable
网络差异（`NEGATIVE_WIRING_DIFFERS`）分别可核，两件事不合并成一句"检测成功"。

## 8 结论分开写（更正）

* `EVIDENCE_STATUS = PASS_WITH_DISCLOSED_HISTORICAL_BUDGET_FAILURE`：R1 交付包在 39 项语义检查下唯一 FAIL 是
  `BUDGET_RESPECTED`（历史 59 > 上限 56 的事实，不改成 PASS、不放宽判据、不靠 NOT_RUN 洗白）。
  旧报告写的 `EVIDENCE_STATUS = PASS` 不可靠，**撤回**；旧 JSON 的 `27/27/27`、`scope_status=COMPLETE`、
  "超额运行 0" 同步撤回。
* `PWM_CURRENT_FEASIBILITY_TT = PASS_WITHIN_FROZEN_CRITERIA`：25 个判定窗 `|charge_error_LSB|` 最大
  `0.438391`（`D7B-CVG-P30-C255/normal`），全部 ≤ 0.5；非 N1 的末 100 ns `max|Iout|` 全局最大
  `2.0600878e-08 A ≈ 20.60 nA`（`D7B-P50-C255/normal`；审核者独立读到约 20.65 nA），仍 < 150 nA；
  5/5 收敛对 `CONVERGED`；`Ical` 在带内。**范围只到"单窗口净电荷与关断后末 100 ns 电流"**：不是光学有效
  位数，不是"电流全程稳定"，也不是亮度/PAM 结论。旧报告"全都 ≤ 0.74 pA"把电荷量当电流，**撤回**。
* 未达标的不是电荷，而是时间行为：23 个判定窗 `NOT_SETTLED_WITHIN_PULSE`，导通初期峰值最高
  `1.684531296e-05 A`（`D7B-P30-C016/normal`）。这与 TI SSZT647 描述的"使能式 PWM 建立/关断限制最短可用脉宽"
  同向，但不构成光学结论。
* 两条判据仍不是同一件事：电气判据若失败会被如实记录，而证据状态独立评。本轮两者都成立，但成立的前提是
  §3–§7 的更正与 39 项语义检查，不是旧版那种"20 项里 19 项 PASS"。
* 完成级别：`RTL_TRACE_DRIVEN_MOS_OUTPUT_MEASURED_TT`（边沿另加 17 次冻结 RTL 复验）。

## 9 限制最短脉冲的条件与后续候选（不在本轮实施）

候选限制因素，按本轮证据能支持的程度排序：

1. 栅支路与输出节点的充电路径（`Mpass_local` 把 `vbias_ch` 抬起来需要时间）——这是端口钳位下的**电气现象**，
   与 LED/面板无关；短窗内电流只到峰值的一部分，`NOT_SETTLED_WITHIN_PULSE` 即其表现。
2. 参考/共源共栅节点的建立：`Ical` 在标定窗是稳态值，但脉冲开始的前若干 ns 内 `node_m`/`vbias_ch` 仍在移动，
   电荷缺口主要来自这段。
3. 输入斜率敏感性（2 ns 对 10 ns）：`D7B-SLEW-P30-C001` 现在给出自己的 10 %/90 %
   （3927.2108 / 3933.8194 ns，`10→90 = 6.6086 ns`；2 ns 版 6.6505 ns），作为对照观察，不单独构成限制证据。

后续两个候选方向（**本轮不做**）：(a) 给最短码预留建立时间——即在窗口开始前预先使能一段导通准备，属于控制
协议改动；(b) 降低 `Mpass_local` 栅节点的驱动阻抗或改用更大宽度的传输管，属于器件改动，需先由用户决定是否
动已冻结的核心。

## 10 仍缺的项

八档 PAM 电流与模拟译码、共享偏置缓冲/保持电容、自主基准、灰阶 LUT 与光学标定、LED I–V、片内数字驱动器输出
阻抗、全 MOS 灰阶控制器与 OA 落实、CDC/skew、阵列与互连 RC、最终 VSCAN/VLED、PVT/温度/Monte Carlo、
版图/DRC/LVS/PEX、SOA 签核。本轮 PWL 回放不构成"外置控制"的最终方案。

本轮另有两个未解除项，按事实保留：历史超支 3 次的处置权在用户（`reports/tasks/DATA-7B-BUDGET-01.md`）；
凭据回显事件按 `reports/dd1_d7b_review_fix_r1.md` §0.2 单独记录，未由远端扫描宣告解除。
