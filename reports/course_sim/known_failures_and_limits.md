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
