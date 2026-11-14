# REVIEW_README — 独立复审入口（停在 `WAITING_FOR_INDEPENDENT_REVIEW`）

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 2026-11-12
课程分支：`course/microled-assignment-sim-20261112`

> **T2A（2026-11-14，最新）**：新增 `tcon_video_rx` / `tcon_col_bank` / `tcon_data_tx` 并改造 `tcon_top`，
> 数据通路首次真实贯通。实测 29/29 PASS、逐字节 0 失配。请先读 `T2A_REPORT.md` §3（四次运行与三个真实缺陷）
> 与 §4（时基使能拆分）——这两节说明本轮改的不只是"加功能"，还修了三个会在真实芯片上出错的缺陷。
> `rtl/T2A_INTERFACE_CONTRACT.md` 是实现的合同，§5 列出与 V1.3 的两处已知偏离（窗内 DCLK、同源 PCLK）。
> 证据：`results/t2a/`（含两次失败 transcript 与逐字节 CSV）、`figures/t2a_datapath.svg`。

> **R2 变更（相对 R1）**：只做**只读补证与口径修正**，未改 RTL/TB、未启动新仿真。
> 新增 MC 原生溯源（`results/mc_native_provenance.csv` 等，30/30 与已导出值一致）、
> 更正 2 张波形图的 `RUN→S_DONE` 为 **18515 ns**（旧图留在 `figures/failed_r1/`）、
> 90% 改为有定义的 `first_cross_90pct_of_on_median` + 峰峰值 `0.183752892 µA` + ringing 披露、
> 预算改 **4/12**、`C12` 标注为"至少一位"、`D3` 明确未闭环。
> Virtuoso GUI 截图仍为 `MANUAL_SCREENSHOT_REQUIRED`（见 `spectre/MANUAL_SCREENSHOT_REQUIRED.md`）。
> `D1`（失败仍可能 rc=0）与 `D3` 闭环属第二阶段，**尚未授权**。
> 本轮 HEAD 以 `git rev-parse HEAD` 与包外 `review_package.sha256` / R2 ZIP 的 manifest 为准。
性质：**课程作业独立交付，不是任何既有轮次的返工、接受登记或 GO**。

---

## 1. 冻结的身份

| 项 | 值 |
|---|---|
| `base_sha`（当天 `origin/main` 真实远端回读） | **`23e471cb936b421ee97e1250c3be06edf96f9937`** |
| 起点 | 当天 `git ls-remote origin refs/heads/main` + `git fetch origin` |
| 分支 | `course/microled-assignment-sim-20261112`（建前本地/远端均不存在，无覆盖/强推） |
| `head_sha` | **按仓库约定 `AGENTS.md` §8.12「报告不得写自身摘要，ZIP 摘要放包外」，本文件不自述自身 commit 的 SHA**。权威值冻结在仓库外 review ZIP 的 `review_manifest.json`，并可由 `git ls-remote origin refs/heads/course/microled-assignment-sim-20261112` 独立回读；本轮对话的最终回执也给出完整 40 位 |
| 源文件哈希 | `coursework/microled_sim/results/file_hashes.csv`（每个交付文件的工作区字节 SHA-256 + 字节数）；Git 会按换行策略做 CRLF→LF 归一化，**blob 身份请用 `git rev-parse HEAD:<path>` / `git cat-file blob` 复核** |
| 审核包 | 仓库外 ZIP（含完整 `base..head` diff、源码、checkers、关键证据与 SHA256 manifest） |

> 为什么用**独立单分支克隆**推送：共享 `.git` 的 `pre-push` hook 会扫**全仓库历史**，
> 其中 4 个**其他分支历史既有**的 `.sv` 文件被扩展名白名单拒绝（`history: 276 commits`，
> `PDK=0 / CREDENTIAL=0 / PRIVATE_KEYS=0 / VENDOR_MODEL=0`）。
> `main` 自身 50 个 commit 经核实**完全不含** `.sv/.v/.png`。
> 任务书 §2 允许「独立 worktree **或独立克隆**」，故改用 `--single-branch --branch main` 克隆，
> **未禁用 hook、未 force、未改历史、未改判据、未降低仓库可见性防护**；克隆内同样安装仓库自带
> hook 并手动执行 staged/history 两模式。完整闸门输出冻结在 review ZIP 的 `gates.txt`。
> 首次 `git push` 另被 GitHub `GH007`（私有邮箱）拒绝，已改用仓库既有已发布 commit 的官方 noreply 邮箱重做未推送 commit；**未关闭邮箱隐私保护**。详见 `known_failures_and_limits.md` A6。


---

> 推送阶段另遇 git HTTPS 代理 502（`gh api` 通道正常），已停止重试并保留完整本地 commit；远端状态以 `git ls-remote` 与包外回执为准，见 `known_failures_and_limits.md` A7。

## 2. 复现入口

```bash
# 数字（Windows，ModelSim 10.5b 命令行；runner 会把 .txt 包装还原成 .v/.sv）
COURSE_ROOT=<本克隆> RUN_DIR=<仓库外 scratch> bash coursework/microled_sim/tb/run_modelsim.sh
# 波形（从真实 VCD 重渲染，输出为 SVG）
python coursework/microled_sim/checks/render_waveforms.py \
  --vcd <scratch>/course_sim.vcd --figures coursework/microled_sim/figures \
  --manifest coursework/microled_sim/results/waveform_render_manifest.csv
# 模拟数值统计（完全离线）
python coursework/microled_sim/checks/analyze_analog.py \
  --results coursework/microled_sim/results --figures coursework/microled_sim/figures
# PDK 压缩包只读审计
python coursework/microled_sim/checks/pdk_zip_audit.py --zip <teacher archive> \
  --json coursework/microled_sim/results/pdk_zip_audit.json
# 闸门
python scripts/precommit_safety_check.py --mode staged
python scripts/precommit_safety_check.py --mode history
python scripts/provenance_check.py
git diff --check
```

模拟网表的原生运行入口见 `spectre/README.md` 与 `spectre/run_course_spectre.sh`
（**本轮 3 个 Spectre job + 1 个 MC job 预算已用尽，重跑需新授权**）。

---

## 3. 测试预期 vs 实测（逐项，不合并口径）

| 检查 | 预期 | 实测 | 证据 |
|---|---|---|---|
| `vlog -sv` 编译 | 0 error | 0 error / 0 warning | `results/modelsim_compile_log.txt` |
| 自检断言总数 / 通过 | 全部通过 | **55 / 55 / 0 FAIL** | `results/modelsim_transcript_run02.txt` |
| 列 1023→0 回绕 | 回绕到 0 | PASS | 同上 C03 |
| 一次最多一列 | 违规 0 | **0** | 同上 C04 |
| 偶/奇 512 Scan / 384 Data 映射 | 不串扰 | PASS | 同上 C05/C06 |
| blank 强制关断 | 组合级关断 | PASS | 同上 C07 |
| PWM 最大码 63 | **64 导通 tick / 65 窗口 tick** | **64 / 65** | 同上 C10、`course_wave_events.csv` |
| PWM 黑码 | 0 导通 | **0** | 同上 C09 |
| `pam_sel=000` 非黑码 | 仍导通 64 tick | **64** | 同上 C11 |
| 60 / 100 Hz 列预算 | 120 ns tick 两者可容纳；200 ns 在 100 Hz 不可 | 16276.042 / 9765.625 ns；时隙 8640 / 14400 ns → **200 ns@100 Hz 不满足** | `reports/course_sim/rtl_timing_report.md` |
| DC 1.20 V 电流 | 记录实测，不设硬性验收阈值 | **14.931905740 µA**（−0.453962 % vs 15 µA） | `results/dc_i_v.csv` |
| 瞬态关态泄漏 / 建立 | 记录实测 | ≈0.274 pA / 90 % 建立 55.94 ns | `results/tran_i_t.csv` |
| Monte Carlo | 30 样本、单 seed、不剔点 | **30/30 成功**，均值 14.932017725 µA，sd 0.008887858 µA | `results/mc_samples.csv`、`mc_stats.json` |
| 原生预算 | ModelSim ≤12 / Spectre ≤3 / MC 1×≤30 | **4 / 3 / 1×30**（另有 1 次 MC 解析失败启动） | `results/execution_ledger.csv` |
| 安全闸 | staged/history 通过 | staged **PASS**；共享 `.git` history 因历史既有 `.sv` **FAIL**（非本轮）；克隆内结果见 ZIP `gates.txt` | 见 §1 |

### 正例
C01 复位、C02 列推进、C03 回绕、C04 单列、C05/C06 分片映射、C08 blank 期 LATCH、
C10 最大码边界、C11 `pam_sel=000`、C13 预算、DC/瞬态/MC 全部真实数值、OA Check&Save 回读。

### 负例（必须能检出且保留）
C07 blank 强制关断、`blank` 期外 LATCH 被拒、C09 黑码、C12 非法 mode / 陈旧配置 / START 被拒
（`proto_err = 8'hDF`）、ModelSim 第一次运行 3 项 FAIL、DC 首次 `save` 无效、
DC CSV 首次列错位、MC 首次解析失败、200 ns@100 Hz 预算不成立。
**所有失败原件保留，未删除、未改写、未拿来凑 PASS。**

---

## 4. 独立复审者请逐文件核的问题

1. **MC 预算口径**：`monte_carlo_report.md` §3 的两次启动（第 1 次解析失败 0 样本，第 2 次 30 样本）
   是否应计为超出「1 个正式 MC job」？若按最严格口径，本项结论应如何改写？
2. **GUI 截图缺口**：Virtuoso 原生 GUI 截图 `BLOCKED`（221 B 空白 root grab + 既有 build 实测），
   结构化 OA 证据（Check&Save 日志 + `dbAccess` 回读）能否替代？是否需要人工补截图？
3. **`SPECTRE-16006`**：未定义 `export` 标量表达式，但 30 个逐迭代 PSF 数值齐全，
   这算完整 MC 交付还是 `PARTIAL`？
4. **波形图性质**：4+4 张图是真实 VCD / 真实 CSV 渲染的 SVG，**不是 GUI 截图**，是否满足课程「波形截图」要求？
5. **100 Hz 预算**：120 ns tick 的余量仅 11.5 %，未含阵列 RC / 驱动建立 / PVT，课程结论是否应降级？
6. **命名约定**：为满足安全闸白名单，源码为 `*.v.txt` / `*.sv.txt`、图为 `.svg`、日志去尾空白。
   是否接受？runner 还原机制是否真的可复现（已实测第 4 次 vsim 复现 55/55）？
7. **来源边界**：是否有任何一处把 `poc/data-pam-d7c-b-tr-r1`（REWORK）写成已接受基线，
   或把「代表性单元」写成「整芯片」，或把 POC 假设写成教师给定条件？
8. **安全闸**：共享 `.git` 的 history 闸 FAIL 属历史既有；改用单分支克隆是否属于合规的「授权范围内」操作？

---

## 5. 交付状态与停闸

- 已执行：环境审计、独立分支、RTL/ModelSim、OA 新建、Spectre DC/瞬态、原生 MC、全部报告与证据。
- **未执行 / 阻塞**：Virtuoso 原生 GUI 截图、ModelSim GUI 截图、门级 STA、整芯片功能、
  PVT/SOA/光学、版图/DRC/LVS。详见 `reports/course_sim/known_failures_and_limits.md`。
- 未合并 `main`、未创建 PR、未登记 GO、未宣布整体验收。
- **停在 `WAITING_FOR_INDEPENDENT_REVIEW`**，由云端独立复审者逐项裁定；执行方不自行签发通过。
