# 覆盖矩阵 — 任务书条目 → 交付路径 → 状态

任务号 `COURSE-MICROLED-SIM-20261112-R1`
状态词：`DONE`（有真实证据）/ `PARTIAL`（部分，有明确缺口）/ `BLOCKED` / `NOT_RUN` / `NOT_IMPLEMENTED`

| 任务书条目 | 交付路径 | 状态 | 实测摘要 |
|---|---|---|---|
| §1 ModelSim 环境（exe / 版本 / 命令行仿真） | `reports/course_sim/environment_audit.md`、`results/modelsim_compile_log.txt` | DONE | `vsim 10.5b` STARTER；最小 `vlog -sv` + `vsim -c` 真实跑通并生成 VCD |
| §1 Cadence / Spectre / OA 可运行状态 | `environment_audit.md` | DONE | guest 内 `spectre 15.1.0`、IC617、Tools 通道可用；SSH 阻塞已记录 |
| §1 PDK ZIP 存在 / 大小 / 可读性 / 条目 / 工艺标识 / 安全扫描 | `environment_audit.md` | DONE | 55,826,083 B；SHA `a3f82176…`；5331 条目；`testzip()=None`；异常路径/符号链接 0；SMIC 0.18 mmrf；无 TSMC |
| §1 统计模型能力与 MC 用法 | `environment_audit.md`、`monte_carlo_report.md` §1 | DONE | `section mos_mc` 含 process + mismatch；`spectre -h montecarlo` 可用 |
| §1 `environment_audit.md` | `reports/course_sim/environment_audit.md` | DONE | — |
| §2 远端 SHA / 来源冻结 / 专用分支 | `source_provenance.md` | DONE | BASE `23e471cb…`；课程分支从当天 `origin/main` 独立 worktree 建立；main 与其他分支未动 |
| §2 复用映射（源分支 + commit + SHA256 + 新路径 + 接受边界） | `source_provenance.md` §3 | DONE | Data-7B-R3 RTL `f9fd09b…` 逐字节复制（`BYTE_IDENTICAL=YES`）；DC-R1 条件作对照 |
| §3 完整可编译 RTL（列扫描 / 行锁存 / PWM / 简化顶层） | `rtl/`（4 文件） | DONE | `vlog -sv` 0 error 0 warning |
| §3 自检 TB（断言 + 负例），全部点名案例 | `tb/course_selfcheck_tb.sv.txt`、`results/modelsim_transcript_run02.txt` | DONE | **55 断言 / 55 PASS / 0 FAIL**；C01–C13 覆盖 1023→0、一次一列、偶奇分片、blank、63 码 64 tick、黑码、`pam_sel=000`、负例、60/100 Hz 预算 |
| §3 transcript / VCD / 波形图 | `results/modelsim_*`、`results/modelsim_vcd_manifest.csv`、`figures/wave_*.svg` | PARTIAL | transcript + VCD 原件保留；4 张图为**真实 VCD 渲染**，非 GUI 截图（见 B2） |
| §3 `rtl_interfaces.md` | `rtl_interfaces.md` | DONE | 逐端口、有效条件、周期、PAM/PWM 码语义、NOT_IMPLEMENTED 清单 |
| §3 `rtl_timing_report.md` / STA | `reports/course_sim/rtl_timing_report.md` | PARTIAL | 周期级功能时序 + 60/100 Hz 预算完整；`STATIC_TIMING_ANALYSIS: NOT_RUN` |
| §4 新建独立课程 OA library/cell + Check&Save | `results/oa_evidence.txt`、`spectre/course_oa_import.scs`、`course_oa_readback.il` | DONE | `course_sim_20261112` 新建；2 个 schematic + 1 symbol；共享 `cds.lib` MD5 未变 |
| §4 器件编号 / 型号 / D-G-S-B / 偏置 / 电源 / 测量方向 / 负载夹持 | `spectre/course_sink_unit.scs`、`analog_test_report.md` §1 | DONE | Mref/Mout/Mcas `n33`，显式端序，IREF 15 µA，显式 VSS=0，iprobe 方向明确 |
| §4 **原生 GUI 截图** | — | **BLOCKED** | 221 B 空白 root grab；既有 build 实测不可行；见 `known_failures_and_limits.md` B1 |
| §4 DC / 瞬态真实数值 | `results/dc_i_v.csv`、`tran_i_t.csv`、`figures/spectre_*.svg`、`analog_test_report.md` | DONE | 19 点 DC；426 点瞬态；1.20 V = 14.931905740 µA；t90 = 55.94 ns |
| §4 PDK include 环境变量注入 | `spectre/*.scs`、`pdk_local.env.example` | DONE | 只用 `${QODER_PDK_LIB}`，真实路径未入库 |
| §5 原生 Monte Carlo（模型 / seed / 样本 / 统计 / 直方图 / CSV / 脚本） | `monte_carlo_report.md`、`results/mc_samples.csv`、`mc_stats.json`、`figures/mc_histogram.svg`、`checks/analyze_analog.py` | **PARTIAL（待裁定）** | 30/30 样本真实；但两次启动与 `SPECTRE-16006` 需复审裁定，见报告 §3/§7 |
| §6 执行预算与账本 | `results/execution_ledger.csv` | PARTIAL | ModelSim **4/12**（含一次 .txt 包装还原后的复现）；Spectre 3/3；MC 1 正式 job（+1 解析失败启动，披露待裁定）；OA 仅新课程库。见 `known_failures_and_limits.md` |
| §7 README 逐项对应 | `coursework/microled_sim/README.md` | DONE | — |
| §7 rtl / tb / ModelSim 脚本 | `rtl/`、`tb/run_modelsim.sh` | DONE | 可复现 |
| §7 spectre / checks / figures / results | `spectre/`、`checks/`、`figures/`、`results/` | DONE | — |
| §7 reports 全套 | `reports/course_sim/` 8 个文件 | DONE | 环境 / 来源 / 接口 / RTL 时序 / 模拟 / MC / 失败限制 / 覆盖矩阵 |
| §7 `REVIEW_README.md` + 仓库外 review ZIP | `REVIEW_README.md`、仓库外 ZIP | DONE | 见最终交付说明 |
| §7 安全闸 / `git diff --check` / 常规 commit + push / 远端回读 | 见 `REVIEW_README.md` 与最终回复 | DONE | — |
| §8 停在 `WAITING_FOR_INDEPENDENT_REVIEW` | — | DONE | 未合并 main、未 PR、未登记 GO、未宣布整体验收 |
