# Micro LED 驱动芯片组仿真设计 — 课程作业交付

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 分支 `course/microled-assignment-sim-20261112`
状态：`WAITING_FOR_INDEPENDENT_REVIEW`（**执行方不宣布整体验收通过**）

> **代表性单元，不是整芯片。** 本交付只实现课程要求的「范围明确、可独立编译的数字代表性设计」
> 与「Data 侧基本 NMOS 恒流下拉单元」。1024 列 × 768 行只作为**地址域**使用，
> 未实例化 MOS 像素阵列。Hybrid 3-bit PAM + 6-bit PWM 是**控制字段**，
> 不是已实现的 9 位光学有效精度。
> `TCON 全芯片 / Data 384 路电流源阵列 / Scan 512 路高侧驱动 / 电平搬移 / 版图 /
> PVT / SOA / 光学性能 / 门级 STA` 一律 `NOT_IMPLEMENTED` / `NOT_RUN`。

---

## 1. 课程题目逐项对应

| 课程要求 | 交付路径 | 状态 |
|---|---|---|
| Verilog 数字模块 RTL | `rtl/course_col_scan.v.txt`、`course_data_latch.v.txt`、`course_top.v.txt`、复用的 `dd1_d7a_gray_ctrl.sv.txt` | **已完成**（4 模块，可独立编译） |
| ModelSim 逻辑 / 时序功能验证 | `tb/course_selfcheck_tb.sv.txt`、`tb/run_modelsim.sh`、`results/modelsim_transcript_run02.txt` | **已完成**：`vsim 10.5b`，55 断言 55 PASS，0 error 0 warning |
| 全部 Verilog 源码与 Testbench | `rtl/`、`tb/` | **已完成** |
| 结合 PDK 的电流源基本单元原理图 | 课程 OA library `course_sim_20261112` / cells `course_sink_unit`、`course_sink_top`；证据 `results/oa_evidence.txt`；导入源 `spectre/course_oa_import.scs` | **部分完成**：真实 OA 原理图 + Check&Save + 结构化回读已完成；**原生 GUI 截图 BLOCKED** |
| Spectre 仿真 | `spectre/*.scs`、`results/dc_i_v.csv`、`tran_i_t.csv` | **已完成**：DC 19 点、瞬态 426 点，0 error |
| 仿真测试文件 | `spectre/course_dc_tt.scs`、`course_tran_en.scs`、`course_mc.scs`、`course_oa_import.scs` | **已完成** |
| 波形截图 | `figures/wave_*.svg`（4 张真实 VCD 渲染）、`figures/spectre_*.svg`（3 张真实 CSV 渲染） | **部分完成**：真实数值渲染，含时间轴 / 信号名 / 轴单位；**非 GUI 原生截图** |
| 时序报告 | `reports/course_sim/rtl_timing_report.md` | **已完成**（周期级功能时序 + 60/100 Hz 预算）；`STATIC_TIMING_ANALYSIS: NOT_RUN` |
| Monte Carlo 结果 | `reports/course_sim/monte_carlo_report.md`、`results/mc_samples.csv`、`mc_stats.json`、`figures/mc_histogram.svg` | **部分完成 / 待裁定**：30/30 真实样本；两次启动与 `SPECTRE-16006` 交复审裁定 |

## 2. 目录

```
rtl/        4 个 Verilog/SystemVerilog 源码（含逐字节复用的 Data-7B-R3 控制器）
tb/         自检 Testbench + 可复现 ModelSim 命令脚本
spectre/    自研网表、OA 导入源、只读回读 SKILL、环境模板、runner 说明
checks/     VCD 波形渲染器、PDK ZIP 审计器（见下）、模拟数值统计与绘图脚本
results/    脱敏后的原始小型 CSV/JSON、transcript、执行账本、OA 证据、哈希清单
figures/    由真实 VCD / 真实 CSV 生成的 8 张图
reports/course_sim/  (仓库根) 8 份审查报告
```

全局审查文件在仓库根 `reports/course_sim/`：`environment_audit.md`、
`source_provenance.md`、`rtl_timing_report.md`、`analog_test_report.md`、
`monte_carlo_report.md`、`known_failures_and_limits.md`、`coverage_matrix.md`。

## 3. 实测结果速览

| 项 | 真实数值 |
|---|---|
| 数字 RTL | 55/55 断言通过；最大码 63 → **64 导通 tick / 65 窗口 tick**；黑码 0 导通；`pam_sel=000` 仍导通 64 tick；全程「一次最多一列」违规 0 |
| 60 / 100 Hz 列周期 | 16276.042 ns / 9765.625 ns；120 ns tick 的 8.64 µs 列时隙两者均可容纳；**200 ns tick 在 100 Hz 超出** |
| DC（1.20 V，TT/27 °C） | `Iout = 14.931905740 µA`，相对 15 µA 目标 −0.453962 % |
| 瞬态 | 关态泄漏 ≈ 0.274 pA；导通中位 14.931906 µA；90 % 建立 55.94 ns；上升沿负位移电流真实保留 |
| Monte Carlo | 30/30 样本，均值 14.932017725 µA，样本标准差 0.008887858 µA，min/max 14.919569356 / 14.955811957 µA，CV 0.0595 % |
| 原生预算 | ModelSim **3/12**；Spectre 电路 job **3/3**；MC 正式 1 job × 30 样本（另有 1 次解析失败启动，已披露）；OA 只写新课程库 |

## 4. 必须先读的限制

`reports/course_sim/known_failures_and_limits.md` 列出全部真实失败与缺口，包括：
第一次 ModelSim 运行 52/55、DC 首次 `save` 无效、DC CSV 首次列错位、MC 首次解析失败、
瞬态 trapezoidal ringing notices、**Virtuoso GUI 截图 BLOCKED**、ModelSim GUI 截图 NOT_RUN、
STA NOT_RUN、SSH BLOCKED。所有失败原件均保留，未删、未改写、未用来凑 PASS。

## 5. 复现入口

```bash
# 数字（Windows，ModelSim 10.5b 命令行）
COURSE_ROOT=<本 worktree> RUN_DIR=<仓库外 scratch> bash coursework/microled_sim/tb/run_modelsim.sh
# 波形图（从真实 VCD 重渲染）
python coursework/microled_sim/checks/render_waveforms.py --vcd <scratch>/course_sim.vcd \
   --figures coursework/microled_sim/figures --manifest coursework/microled_sim/results/waveform_render_manifest.csv
# 统计（完全离线，从结果 CSV 复算）
python coursework/microled_sim/checks/analyze_analog.py \
   --results coursework/microled_sim/results --figures coursework/microled_sim/figures
# 模拟（需原生 guest 环境 + 新授权；PDK 路径由未跟踪本地环境注入）
spectre course_dc_tt.scs -64 -format psfascii     # 见 spectre/README.md
```

## 6. 停在独立复审

未合并 `main`、未创建 PR、未登记 GO、未宣布整芯片验收。
执行方不得自行签发通过；下一步由云端独立复审者按 `REVIEW_README.md` 逐项核对。
