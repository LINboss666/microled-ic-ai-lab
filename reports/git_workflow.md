# Git 版本管理 + 源码审核工作流（本阶段交付）

日期 2026-10-04/05。本阶段**不做电路设计**，只把现有 AI-Cadence 工程变成可审计、可回退、
可交给人工/另一个模型审核的 Git 工作流。

## 仓库

| 项 | 值 |
|---|---|
| 本地路径 | `D:\ic617_agent_bridge` |
| 默认分支 | `main` |
| baseline commit | `89841c06e82dd2ccd34f1104563f97bd6ed0dd54` |
| 当前 HEAD | `461567bd1f527862f6e6a51a131a81ace4dbdf67`（branch `poc/c2mos-dff`） |
| 本轮 commit 数 | baseline + 5 |
| 被跟踪文件 | 101（全部本项目自研内容） |
| 仿真证据位置 | `results/`（CSV/JSON/checker 原文），**PSF 数据库不入库** |

**为什么仓库根在 Windows 而不是 guest**：`git`、`gh`（已登录）和 review bundle 的产出路径都在
Windows，而 guest 是执行区。两侧目录结构已对齐（`spec/ spectre/ scripts/ reports/ results/ skill/ logs/`），
差异只剩 guest 侧的运行产物（`pdk/ home/ skill_run/ spectre/sim/`，全部不入库）。
对齐由 `scripts/repo_parity.py` 逐文件比对（按去 CR 后的 md5）。

## 安全边界调查（git init 之前做的，三类）

`python scripts/repo_safety_scan.py`，输出快照留在 `results/repo_safety_scan.txt`。
对当时工作树 237 个文件的分类：

| 分类 | 数量 | 判据 |
|---|---|---|
| `MUST_IGNORE` | 12 | 凭据文件、`course_source/`（老师交付原件）、`pdk_compare/`（PDK 文件清单）、`logs/pdk_inventory_raw.txt`（PDK 目录原始清单）、review zip 产物 |
| `NEEDS_REVIEW` | 48 | 正文里出现 PDK 名称/安装路径的报告与 netlist 注释、`.out` 等非标准扩展名、>200 KB 文件 |
| `SAFE_TO_TRACK` | 177 | 其余自研内容 |

扫描器对**被排除的文件只打印前缀 + `<name withheld>`**，不在扫描报告里清点老师/PDK 的文件名。

`NEEDS_REVIEW` 的处置决定（都是可逆的 ignore 规则，没有删除任何文件）：
- `course_source/` → 不入库。那是老师交付的课程文档原件；我们自己的、带行号引用的结论已经在
  `reports/` 里。**需要审核原始题目文本时请从课程交付包取，不要指望仓库。**
- `pdk_compare/`（4 个机器生成的 PDK 文件清单，含数百条 vendor 路径）→ 不入库；
  结论保留在 `reports/pdk_zip_vs_guest.md`（只有文字与少量文件名）。
- `logs/`（桥运行日志：本地绝对路径、guest IP、命令回显）→ 不入库；
  评审需要的数值改为落到 `results/evidence/`。
- 正文里提到 PDK 名称/安装路径的报告与 netlist → **保留入库**。它们只是引用工艺名
  （老师指定的工艺本身就是设计信息），不含任何模型卡原文。已核实全仓库
  **没有任何 SPICE `.MODEL` 卡片、`.PARAM` 块，或 `+` 续行形式的 BSIM 阈值参数赋值，
  也没有 Calibre deck 段**。

## 硬性闸（不是 .gitignore）

`.gitignore` 只影响 `git status`，真正的拦截是 `scripts/precommit_safety_check.py`，
由 `scripts/install_hooks.sh` 装成两个 hook：

| hook | 模式 | 查什么 |
|---|---|---|
| `pre-commit` | `--mode staged` | 逐个读 **staged blob**（`git cat-file blob :path`），查路径规则、vendor 内容规则、秘密形状规则、体积、未知扩展名 |
| `pre-push` | `--mode history` | 遍历所有 commit 的每个唯一 blob —— 后来删掉的秘密仍在历史里，历史才是要推出去的东西 |

另有 `--mode objects`：把 `.git` 里**所有**对象（含 `git add` 后 `git reset` 留下的 dangling blob）
都扫一遍。本仓库实测 112 个对象全清。

规则只有一份：`scripts/repo_safety_rules.py`，被扫描器、闸、bundle 生成器共用，避免漂移。
**计数只用精确 fnmatch 匹配，不用子串**（早期子串版本把 `pdk_local.env.example` 当成 `.env` 秘密，
误报即被修正——闸误报太快就会被人类关掉，所以 `scripts/test_safety_rules.py` 同时钉住
"必须拦"和"必须不拦"两侧共 21 个用例，当前 PASS）。

秘密匹配是形状匹配：`password = <真实值>` 会命中，
而 "the password is never committed"、shell 的 `pwd=`（工作目录）、SKILL 的 `printf("pwd=%s")`
不命中——后两类在本仓库真实存在过。任何命中都**只打印路径/规则/行号，绝不打印值**。

## PDK 不进仓库，也不进 netlist 文本

commit 里的 netlist 一律写 `include "${QODER_PDK_LIB}" section=tt`。
Spectre 会在 `include` 路径里展开环境变量（本机实测：同一器件用字面路径与用变量结果一致，
g=1.8 → 0.758 V）。变量由 `scripts/run_spectre.sh` 从未跟踪的 `spectre/pdk_local.env` 载入；
缺该文件时 runner 直接拒绝并提示从 `spectre/pdk_local.env.example` 复制，而不是给出看不懂的仿真错误。
（实测拔掉了 env 文件后：`REFUSED: ... needs environment variable(s) QODER_PDK_LIB`。）

## 失败历史被保留（不伪装成 PASS）

baseline 里就带着失败的 TG 实验：`spectre/shift_unit_tb.scs`、`scripts/shift_unit_check.sh`、
`reports/shift_unit_status.md`。为让审核方能看见"错误结论 → 真因 → 修正"的完整过程，
`AGENTS.md`、`reports/shift_unit_status.md`、`scripts/psf_check.awk` 在 baseline 里被还原成
C²MOS 之前的内容（还原自本会话记录，非当时的快照，这一点写进了 baseline commit message），
branch 上的 diff 才真实呈现：作废第 18 条、新增第 19 条（浮空 `vss` 根因）、
`psf_check.awk` 支持按时钟沿配对测延迟。

## Review bundle

`python scripts/make_review_bundle.py main HEAD --notes reports/c2mos_review_notes.md`

产出 `review/review_bundle_<head7>/` 与同名 zip（49 个文件，约 125 KB）：
`REVIEW_README.md`、`manifest.txt`（逐文件 bytes + sha256）、`git_status.txt`、`git_log.txt`、
`git_diff.patch`、`changed_files.txt`、`source/`（netlist、testbench、checker、生成脚本）、
`reports/`、`results/`。

要点：
- **器件表与分相位导通表是从 bundle 里的 netlist 现场解析出来的**（`subckt` 端口、
  局部 `parameters` 展开、每个 MOS 的 D/G/S/B/L/W，以及时钟管的导通相位），
  所以表和源码不可能不一致。
- 打包前先跑 `--mode history` 闸；每个要复制的文件再过一次规则，命中就拒绝写出 zip。
- PDK 模型参数不复制；raw PSF 不复制；只带提取出来的数值。
- REVIEW_README 必含：Task、Requirement 四类标签、Circuit、Device list、Clock/state、
  Simulation 条件、Automatic checks（checker 文件 + 阈值 + 实测值）、
  **Known failures（7 条，不许只报成功）**、Files changed、Base/Head SHA、
  **Questions for reviewer（3 个本轮真不确定项）**。

## 首次 push 前的重扫（实测输出）

```
mode=history objects_checked=101
PDK_TRACKED_FILES = 0
CREDENTIAL_TRACKED_FILES = 0
PRIVATE_KEYS_TRACKED_FILES = 0
VENDOR_MODEL_TRACKED_FILES = 0
SAFETY_GATE: PASS
```

## 一处需要你知道的处置：Windows 用户名

phase-1/2 的两份报告里有本机账户名（`C:\Users\<账户>\...`）。这些 blob 从 baseline 起对 6 个 commit
都可达，所以在**任何 push 之前**做了历史重写：把账户名统一替换成 `<windows-user>`，
`git grep` 全历史命中数 = 0。重写前留了可验证的备份包
`review/history_before_pii_redaction.bundle`（`git bundle verify` 通过），重写后 SHA 见上表。
私有仓库也不值得留着身份标识——以后若转公开，这一步就不必再做了。

另外：本仓库 commit 作者沿用你机器上已有的 git 配置（账户名 + 手机号形式的邮箱），
按红线我没有改 git config。如果这让你不舒服，换成 GitHub 的 noreply 身份需要在第一次 push
之前重写作者信息，我可以照办。

## 以后每轮的固定流程

见 `CONTRIBUTING_AI.md`（12 条 + 每轮命令）。核心：**先开 branch；Spectre 0 errors ≠ PASS；
必须有数值断言；失败不许伪装；每轮结束生成 review bundle；人工审核通过前不进下一阶段。**
