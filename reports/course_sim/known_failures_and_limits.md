# 已知失败、缺口与限制（逐项，不隐藏）

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 停在 `WAITING_FOR_INDEPENDENT_REVIEW`

> 本文件是给独立复审者的「缺陷清单」，不是自评通过表。所有失败样本原件均保留。

## A. 本轮真实发生的失败（保留原件）

| # | 项 | 事实 | 处理 |
|---|---|---|---|
| A1 | ModelSim 第一次课程运行 | **52/55 PASS、3 FAIL、2 warnings**。3 项 FAIL 均为 TB 测量方法缺陷（组合信号同一 delta 读取；`obs_tick` 在 `+1 ns` 采样漏掉结束边界 tick）；2 条 TFMPC 警告来自一个未连接的 `blanked` 输出端口 | 只修测量方法（新增边沿前窗口计数监视器）与删除多余端口；判据数值 65 未放宽。原件：`results/modelsim_vsim_stdout_run01_FAILED.txt`、仓库外 `run01_tb_measurement_defect/`（含 VCD） |
| A2 | Spectre DC 首次启动（S1） | `0 errors, 2 warnings`：`save Ip_out:current` 被本 build 判无效并忽略，PSF **无电流数据** | 查 `spectre -h iprobe` 后改成实例名 `save Ip_out`；修复 1 次。原件：沙箱 `S1_first_run.log/.raw/.stdout` |
| A3 | DC CSV 首次导出 | 提取脚本把 PSF 的 SWEEP/TRACE 声明行也 grep 进来，导致列错位、出现假的 0 行 | 改为只解析 `VALUE` 段，重新导出 19 点并回拉校验；错误版未入库 |
| A4 | Monte Carlo 第一次启动 | `SFE-874`，子分析写在一行导致解析失败，`rc=2`，**0 样本 0 求解** | 只改换行，第二次启动 30 样本成功。原件：沙箱 `MC_start1_PARSE_FAIL.log/.stdout`。**预算口径见 `monte_carlo_report.md` §3，交复审裁定** |
| A7 | 最终 `git push` | 本地 commit 完成、pre-commit/pre-push 闸门全部 PASS，但 HTTPS 代理持续返回 `CONNECT tunnel failed, response 502` / `Empty reply from server`；直连超时，HTTP/1.1+openssl 亦 502；同时 `gh api` 通道正常，说明是 git 传输链路问题 | 按任务书失败分支**停止重试**，保留完整本地 commit 与仓库外 review ZIP；**未禁用 hook、未 force、未改 GitHub 邮箱隐私保护、未用 API 绕过造 commit**。远端分支是否最终存在以 `git ls-remote origin refs/heads/course/microled-assignment-sim-20261112` 为准 |（**R2 注**：网络恢复后第 8 次推送成功，远端回读 `37833a3a3698413ab9df5da8cc4400bfab515401`；本行是当时阻塞的**历史快照**，未改写原始失败证据） |
| A8 | `D1` 自动验收假阳性（未修） | `chk()` 只打印 FAIL 后 `$finish`；`run_modelsim.sh` 直接 `exit "$VSIM_RC"`，不校验 `COURSE_RTL_RESULT`/`FAIL_COUNT`。第一次 52/55 时 `vsim` 仍 rc=0 已证明该风险 | **R2 第一阶段未改 TB/runner**：该修复属于任务书第二阶段，需新的显式授权与 ModelSim 次数。状态 `OPEN_NOT_AUTHORISED_IN_R2_PHASE1` |
| A9 | `D2` 波形标注错位 119 ns（已修） | 旧图把 `18396 ns` 标为 window end / 65th tick；冻结 VCD 中 `win_state` 的 `RUN→S_DONE` 实为 **18515 ns** | 仅离线重绘：旧图归档 `figures/failed_r1/`，新图标注 `last obs_tick` 与 `RUN->S_DONE`；新旧 SHA 见 `results/waveform_correction_manifest.csv` |
| A10 | `D3` Data→灰阶未闭环（如实记录） | `pam_sel_lat`/`pwm_code_lat` **未接**到 `dd1_d7a_gray_ctrl` 的 `cfg_hyb_time`/`cfg_hyb_pam`；两模块仅经 `drive_gate` 相与 | 55/55 只证明代表性地址/锁存/独立 PWM 模块功能，**不是** TCON→Data→Scan 端到端链路。状态 `NOT_IMPLEMENTED_DOCUMENTED`；补链路属第二阶段，需授权 |
| A11 | `A2` MC 原生溯源（已补） | 新增 `results/mc_native_provenance.csv`（30 行：迭代号、PSF 相对路径、字节数、SHA-256、`Ip_out:i` 原始双精度值）、`mc_native_log_extract.txt`、`mc_mapping.txt`、`mc_iteration_status.txt` | 30/30 与 `mc_samples.csv` 逐条一致，30 个不同 PSF SHA、30 个不同值；未上传模型卡/PDK/许可证/大 PSF |
| A12 | `A1` 90% 术语（已修） | 原称"90 % 建立时间" | 改为 `first_cross_90pct_of_on_median` 并给出定义；补 2–4 µs 峰峰值 0.183752892 µA（1.2306 %）、±1 % 带 1.103750 µs、±5 % 带 1.057898 µs、ringing 7+365 notices 披露 |
| A13 | Virtuoso GUI 截图 | 自动抓取实测不可行：root 221 B、顶层 177 B、最大子窗口 `IsUnMapped` 且 `import` 报 `Resource temporarily unavailable` | 状态 `MANUAL_SCREENSHOT_REQUIRED`；人工步骤见 `coursework/microled_sim/spectre/MANUAL_SCREENSHOT_REQUIRED.md`，证据 `results/gui_attempt/gui_evidence.txt` |
| A6 | 首次 `git push` | GitHub 返回 `GH007: Your push would publish a private email address`；本轮未推送 commit 用了本地配置的私人邮箱，而仓库所有已发布 commit 均用 GitHub 官方 noreply 邮箱 | 用**与既有已发布 commit 相同**的 `237816241+LINboss666@users.noreply.github.com` 重新创建这个**尚未推送**的 commit（soft reset 到 base 后重新提交）；**未关闭 GitHub 邮箱隐私保护、未改任何已发布历史、未 force** |
| A5 | Spectre 瞬态 notices | 7 条 `trapezoidal ringing on Xdut.Mcas:int_s`（另 365 条被抑制），数值方法提示 | 如实记录，未隐藏，未改积分方法 |

## B. 未完成 / 阻塞项（`NOT_RUN` / `BLOCKED`）

| # | 项 | 状态 | 证据 / 原因 |
|---|---|---|---|
| B1 | **Virtuoso 原生 GUI 截图**（原理图 / 仿真设置 / 波形） | `BLOCKED` | 本轮 X display `:0` 可用（Xorg 运行），但 `import -window root` 只得到 **221 字节空白 PNG**；仓库既有实测 `skill/sc1_s3c3_gui_body.il` 已记录该 build 的 Virtuoso 窗口是嵌套 Qt 子窗口、自动像素抓取未完成、截图需人工完成。**未启动 GUI 伪造截图，未把网表/渲染图冒称已保存原理图**。真实 OA 对象、Check&Save 日志与结构化回读见 `results/oa_evidence.txt` |
| B2 | ModelSim **GUI 原生波形截图** | `NOT_RUN` | 四张波形图是**从真实 VCD 渲染**的时序图（`checks/render_waveforms.py`），含时间轴与信号名，但明确不是 GUI 截图；原始 VCD + transcript 保留可复核 |
| B3 | `STATIC_TIMING_ANALYSIS` | `NOT_RUN` | 无综合后网表、工艺标准单元库、SDC 与 STA 工具；**未编造任何 slack / setup / hold** |
| B4 | 门级 / 混合信号联合仿真、版图、DRC/LVS、PVT/SOA、光学效率、整芯片 TCON / Data / Scan 全功能 | `NOT_IMPLEMENTED` | 课程只交付代表性单元与控制逻辑 |
| B5 | SSH 通道 | `BLOCKED_SSH` | 既有地址 22 端口超时、guest 无上报 IP；改用仓库 `AGENTS.md` 定义的 VMware Tools 应急通道完成全部 guest 操作。未重启 VM、未改 `.vmx`/快照/网络配置/license |
| B6 | 「9 位光学有效精度」 | 明确否认 | Hybrid 3-bit PAM + 6-bit PWM 只是**控制字段**，不是已实现的光学精度 |

## C. 判据与来源上的诚实边界

1. `120 ns` tick、`100 MHz` 时钟、`8 tick` 消隐、偶/奇分片规则均为 `POC_ASSUMPTION` / `ENGINEERING_DERIVATION`，**不是教师给定条件**。
2. `200 ns` tick 在 100 Hz 下**不满足**列周期预算（14.4 µs > 9.765625 µs），已明确写出，未默认成立。
3. 历史 DC-R1 的 `15.382706 µA` 是八档 PAM 阶梯的限定接受结果，本课程的 3 管单元只作条件对照，**没有把历史阈值拿来验收新电路，也没有为追 PASS 改阈值**。
4. `poc/data-pam-d7c-b-tr-r1` = `ec107af5…` 为 REWORK，**未被引用为已接受基线**。
5. 所有 PDK 模型卡内容、模型真实路径、license 地址、凭据、老师原始 ZIP、原始大 PSF/WLF 均未入库；`oa_evidence.txt` 已脱敏，敏感词扫描为 0。

## D. 交付物中不存在的东西（不要去找）

- 不存在的「整芯片通过验收」声明、GO 登记、main 合并、自动 PR。
- 不存在的 GUI 原理图截图 PNG。
- 不存在的 `scalarfile` / `paramfile`（MC 因未定义 `export` 而未生成；数值来自 30 个逐迭代 PSF）。
- 不存在的伪造波形、补点、剔除坏点、手绘通过曲线。

## E. 建议复审者优先追问

1. MC 两次启动的预算口径（`monte_carlo_report.md` §3）。
2. GUI 截图 BLOCKED 是否可依法接受结构化 OA 证据替代，或必须补做人工截图。
3. `SPECTRE-16006` 下逐迭代 PSF 抽取是否算完整 MC 交付。
4. 100 Hz / 120 ns 的列预算余量仅 11.5 %，是否足以支撑课程结论。
5. 代表性设计与「整芯片」边界是否被任何一处文案越过。
