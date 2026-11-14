# PROGRESS_NOTE — T2B 第 A 段执行回执

**任务** `TCON-T2B-20261114`（接口与流水标签对齐，A 段只读核查）
**基线** `d17c5de22a0d0879ccf2767ca20a9613d18947f1`，分支 `course/microled-assignment-sim-20261112`
**本轮 EDA 用量：ModelSim 0 次 / Spectre 0 / Monte Carlo 0 / OA 0**（只有 `vlog` 编译未跑；本段按任务书不编译、不仿真）
**状态：`WAITING_FOR_T2B_SCOPE_REVIEW`**（B 段未启动）

---

## 1. 做了什么（对应任务书 A.1–A.6）

| 段 | 内容 | 产物 |
|---|---|---|
| A.1 | 基线核对：本地 HEAD = `d17c5de`；`main` 未被修改（`23e471c`）；工作区干净；远端仍无法回读 → `REMOTE_PENDING` | 本文 §4 |
| A.2 | 从 SHA 已验的 V1.3 读 §4/§9/§12/§14（§3 只有论文综述，无接口条款），逐项标 `FROZEN_SPEC`/`DERIVED`/`ASSUMPTION`/`CONFLICT` | `VIDEO_CONTRACT_DIFF.md`（17 项，3 个 CONFLICT） |
| A.3 | 按绝对列标签画三槽时间线，区分启动预充与稳态；LATCH/SCAN_STB 的槽内位置与所属标签 | `PIPELINE_LABEL_TIMELINE.md` |
| A.4 | 列 19 逐级追踪：输入→TX 前 2 组→转零→下一次 LATCH→显示 bank→SCAN_STB；指出 `slot_bad` 在哪个边界清除 | `COLUMN_POISON_LIFETIME.md` |
| A.5 | 安全闸证据复现：在**隔离克隆**里 `git checkout --detach d17c5de` + `git reset --soft 14bf0fe`，重建真实暂存态，跑 staged 与 history 两种扫描，原始终端日志落在仓库外 | `gate_repro/`（见 §3） |
| A.6 | 只输出上述三份 + 本回执 + 原件清单，停 `WAITING_FOR_T2B_SCOPE_REVIEW` | 本文件 + `SOURCE_MANIFEST.md` |

**没有做的**：未改任何 RTL/TB；未新增断言；未重跑 ModelSim；未改 V1.3；未合并 main、未开 PR、未强推。

---

## 2. 三条主要发现（都比"测试脚本问题"重要）

### F1（P0）`COL_SYNC` 语义与 V1.3 相反 —— 确认成立，且证据是逐字的两处独立表述

- §12 信号表：「`COL_SYNC` … **新列首字节边界，同PCLK采样**」
- §9：「**`COL_SYNC`与第一个有效字节同一PCLK上升沿采样**，DE=1表示有效」

即 `COL_SYNC` 与 byte0 **同拍**，是列**开始**标记。当前 RTL 要求 `idx==768` 才接受（`tcon_video_rx.v.txt:108`），是"列**尾**确认"。这不是措辞偏差，而是接口方向相反：V1.3 的列边界来自输入端，本实现的列边界来自本地时基。

→ 由此 `63/63 PASS` 只证明了后者。上一轮复审 `POLICY_ACCEPTED / SPEC_CONFLICT_OPEN` 的判断正确，本段给出逐字依据。

### F2（P0）`SCAN_STB` 带的列号恒定偏大 1 列 —— 从静态推导变成可以写出来的等式

§14 的次序是「LATCH原子更新 → … → **SCAN_STB锁存新COL_ID** → BLANK=0」。`LATCH` 在 828，切进显示 bank 的是"上一次转发完成的列" = s−1；因此 `SCAN_STB` 锁的必须是 **s−1**。当前 `col_id <= tb_col`（=s）直接给了 `SCAN_STB`（`tcon_top.v.txt:184,274-275`）。

上轮复审说"两者可能相差一列，尚不是已确认故障"——本段把方向定死：**就是差 1，且方向固定**。同时说明为什么 `X30/T1_col_id` 验不出来：它们比的是两个"接收列"，同源同错。

### F3（P0）污染列的寿命短于流水 —— `slot_bad` 覆盖 1 槽，显示许可在 +2 槽

`slot_bad` 在下一个 `tb_start` 就清（`tcon_top.v.txt:172-176`）。列 19 的混合载荷（2 组真实 + 382 组零）在槽 20 的 `LATCH` 正常切入显示 bank，在**槽 21 的窗口点亮**，全程无 `blank`。列 11 那条路径更糟：`LATCH` 被抑制后显示 bank 与 Scan 地址**双双冻结**，结果是"重复上一列"而不是黑。

V1.3 §20 的原文是「**当前/后续列全关**」+「恢复合法帧，清故障后重新启动」，§9 是「均**锁存**熄屏」。当前实现是槽级熄屏，**不满足"后续列全关"**。

---

## 3. 上轮复审的两项工程问题：一条已复现，一条已定位

### 3.1 安全闸证据不一致 —— 已用隔离副本复现，原日志在仓库外

上轮我给出的 `gates_staged_precommit.txt` 是**提交之后**才重新跑的，所以显示 `objects_checked=0`，与 `gates.txt` 里"提交前 10 个对象"对不上。复审不接受是合理的。

本轮在隔离克隆（不碰已发布 commit）里重建了真实暂存态：

```
$ git checkout --detach d17c5de22a0d0879ccf2767ca20a9613d18947f1
$ git reset --soft 14bf0feabf566e298596246db4a6a8c09d5cae7c
$ git diff --cached --name-only | wc -l      -> 10
$ python scripts/precommit_safety_check.py
mode=staged objects_checked=10
PDK_TRACKED_FILES = 0
CREDENTIAL_TRACKED_FILES = 0
PRIVATE_KEYS_TRACKED_FILES = 0
VENDOR_MODEL_TRACKED_FILES = 0
SAFETY_GATE: PASS
```

10 个对象与 `diff/name-status.txt` 完全一致（3 个新增 + 7 个修改），日志与 name-status 都留在仓库外 `gate_repro/`。
**修正上一轮的说法**：那 10 个对象确实经过 staged 扫描，但当时只有我口述，现在才有可复现的原始终端。历史扫描 `--mode history` 是 800 个对象、PASS（59 个提交）。

### 3.2 T1 的 8 条未连接端口警告 —— 已定位到具体端口，本轮按要求不改

run04（T1 `SCEN=ALL`）transcript 实测：

```
** Warning: (vsim-3017) tcon_t1_tb.sv(39): [TFMPC] - Too few port connections. Expected 33, found 26.
** Warning: (vsim-3722) ... Missing connection for port 'err_flags'.
** Warning: (vsim-3722) ... 'err_now'.      'bank_valid'.   'bytes_rcvd'.
** Warning: (vsim-3722) ... 'bytes_sent'.   'load_blank'.   'load_cnt'.
** Errors: 0, Warnings: 8
```

即 `tcon_t1_tb.sv.txt:39-51` 的实例只接了 26/33 个端口，7 个观测口未接 + 1 条汇总告警。修法是把这 7 个口接到 TB 侧 dummy wire（T2A 侧已用同样办法清掉了自己的 2 条）。
**本轮不改**，因为它会改 TB 文件，而 A 段冻结"不改 RTL/TB"；且 TB 一改就必须重跑 T1，属于 B 段预算。**在此之前，T1 的 49/49 必须附带"8 warnings"的限定语，不能写成"0 warning"。** 上一轮我在 T2AR2 报告里只对 T2A 说了 0 warning，没提 T1 的 8 条，这是漏报，已在本文件更正。

---

## 4. 基线 / Git

| 项 | 值 |
|---|---|
| 分支 | `course/microled-assignment-sim-20261112`（独立克隆，未碰 `main`=`23e471c`） |
| 本地 HEAD | `d17c5de22a0d0879ccf2767ca20a9613d18947f1`（T2AR2 提交，未变） |
| 本轮新增提交 | 只有文档（`coursework/microled_sim/t2b/`），不动 RTL/TB |
| 远端 | `REMOTE_PENDING`：`ls-remote` / `push` 均为传输层失败（`CONNECT tunnel 502`、`schannel close_notify`），只试一次，不重试、不强推、不用 API 伪造 |
| 远端最后已知 | `f06325b0d10fd64d8377c3531b73bbc3dc4c24f1` |

---

## 5. 需要你裁定的三件事（B 段入口）

| 编号 | 决策 | 选项 | 我方建议 |
|---|---|---|---|
| Q1 | `COL_SYNC` 语义 | A 直接改成 V1.3（同步在 byte0，现有 63 条断言与全部激励重写）／B 只写文档承认差异／C 同一 RTL 两个明确命名模式（`SPEC_MODE` / `COURSE_MODE`） | **C 过渡、A 收口**；无论哪个，合同必须写明"本实现曾是列尾确认" |
| Q2 | `SCAN_STB` 列号 | A 改 `col_id` 为 s−1（改判据）／B 新增独立 `COL_ID_DISPLAY` 口 | **A**，与 Q1 一起一次性改，不偷偷改判据 |
| Q3 | 污染列寿命 | A 污染位随流水推 2 槽，显示窗口继续 blank／B 严格按 §20 锁存熄屏到下一个合法 `VSYNC` | **B 更贴原文**；若课程演示不能接受整帧黑，则 A + 明确"更弱的保证" |

---

## 6. B 段预算与允许改动（草案，待批）

| 项 | 草案 |
|---|---|
| ModelSim 正式运行 | **3 次上限**：1 次 T2B 联合（新标签等式 + 边界）、1 次 T1 回归、至多 1 次"有证据定位"的修复复验；第 3 次若仍失败即停，不自动续跑 |
| 允许改的 RTL | `tcon_top.v.txt`（`col_id` 来源、`blank` 表达式、per-column poison）、`tcon_video_rx.v.txt`（`COL_SYNC` 语义/poison 输出）、**新增** `data_model.v.txt`/`scan_model.v.txt`（行为替身，明确非晶体管级） |
| 不许改 | 时基常数（976/977、576/448）、DCLK 50 MHz、64 tick、五芯片结构、V1.3 任何数值 |
| 退场条件 | 任一新 `CONFLICT` 出现、或需要改 V1.3 语义、或第 3 次运行仍失败 → 停并回报 |
| 核心断言 | `at SCAN_STB: scan_latched_col == data_display_bank_col` 且 `poison(display_bank_col)==0`；不再以"两个独立计数相等"代替 |

---

## 7. 本轮明确不做

不改 RTL/TB；不跑任何仿真；不建 Data/Scan 行为模型（B.2）；不碰 SPI/中断/CDC/STA/PVT/整芯片；不改 V1.3；不合并 main、不开 PR、不宣布任何验收。
