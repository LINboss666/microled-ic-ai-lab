# 来源冻结与复用映射 — 课程作业仿真分支

任务号：`COURSE-MICROLED-SIM-20261112-R1` ｜ 日期：2026-11-12 ｜ 阶段：建分支时只读核对（非接受登记）

> 本文件冻结当天的远端事实，防止把历史 SHA 冒充最新 SHA。所有 SHA 均为**完整 40 位**。
> 本轮不改写、不顺手认可 TR-R1，不合并 `main`，不修改其他在审分支。

---

## 1. 仓库身份与当天远端回读

| 项 | 实测 |
|---|---|
| 仓库 | `D:/ic617_agent_bridge` |
| remote | `origin https://github.com/LINboss666/microled-ic-ai-lab.git`（fetch / push 同为同一 URL） |
| 主仓库检查时分支 | `poc/data-unit-1ch`（**未切换**） |
| 主仓库工作树 | `git status --short` 空输出，干净 |
| 既有 linked worktrees | 22 个，全部保持原状；本轮新增第 23 个 |
| `git fetch origin` | rc=0（只更新远端引用，未改任何本地分支） |
| `git ls-remote origin` | rc=0，下表的 SHA 均来自**真实远端回读**，不是本地 `rev-parse` |

### 当天远端 SHA（完整 40 位）

| 远端分支 | SHA | 本轮用途 |
|---|---|---|
| `refs/heads/main` = **BASE_SHA** | `23e471cb936b421ee97e1250c3be06edf96f9937` | 课程分支起点 |
| `poc/data-gray-d7a` | `6a1f5a192f3f1618499335c4365d717bfcadef39` | Data-7A 早期分支 tip（对照，非本轮复用源） |
| `poc/data-gray-d7a-r4` | `0bfe339b8dbbb43e8356fc14f7a81acfd429a683` | 对照 |
| `poc/data-pwm-d7b-r3` | `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` | Data-7B 限定接受分支 tip |
| `poc/data-pam-d7c-b-dc-r1` | `61621f6e3d887082ecd6a7ecc1c771f8e509a24a` | PAM DC-R1 限定接受分支 tip |
| `poc/data-pam-d7c-b-tr` | `398c9e852c16db85cbfa4539e859534e117ff0d2` | 对照（R1 修补 BASE） |
| `poc/data-pam-d7c-b-tr-r1` | `ec107af502b729225e49428e4d2d72bffc389dae` | **REWORK，仅参考，不得标为已接受基线** |

`refs/heads/course/microled-assignment-sim-20261112` 在远端与本地均**不存在**（建前双重核对），故不存在覆盖或强推。

### 新建的独立课程 worktree

```
branch   course/microled-assignment-sim-20261112
worktree D:/ic617_course_sim_20261112
起点     origin/main = 23e471cb936b421ee97e1250c3be06edf96f9937
命令     git worktree add -b <branch> <path> origin/main
```

`main`、所有 `poc/*` / `feature/*` / `gexing321/*` 分支及它们的 worktree 均未被 checkout、reset、stash、clean 或修改。

---

## 2. 仓库契约与既有安全闸（本轮已读，未修改）

| 文件 | 关键约束（摘录，不是重述为已认可） |
|---|---|
| `AGENTS.md` | 不对 VM 做电源/快照/`.vmx` 操作；guest 侧写入限沙箱；不修改 PDK、已有 Cadence library、schematic/layout；不改 license；凭据值绝不入库；SSH 不可达时用 VMware Tools 应急通道；单根因最多 3 次修复；`git push` 443 失败只对单次命令加 `-c http.version=HTTP/1.1` |
| `CONTRIBUTING_AI.md` | 先开 branch 再动手；不提交 PDK/秘密；`spectre 0 errors` ≠ PASS，必须数值断言；失败方案不得伪装 PASS；假设必须标来源；每轮生成 review bundle；审核通过前不得自动进入下一阶段；不碰 VM/账号危险操作 |
| `scripts/precommit_safety_check.py` | staged / history / objects 三模式，查 PDK、模型卡、secret 等 |
| `scripts/provenance_check.py` | 来源标签与绝对化措辞机检 |
| `scripts/make_review_bundle.py` | `<BASE> <HEAD>` 生成评审包，含真实源码/检查器/数值 |
| `scripts/run_spectre.sh` | 拒绝项目外 netlist；PDK 路径以 `${QODER_PDK_LIB}` 注入；HOME 重定向 |
| `reports/pdk_zip_vs_guest.md` | 老师 ZIP 与 guest 副本历史位级对比结论 |

本任务书 §6 的预算比旧轮更严格（ModelSim 12 / Spectre 3 / MC 1×≤30 / 单根因 ≤3 次修复），**遵守更严格者**；旧轮剩余额度不结转。

---

## 3. 复用映射（源分支 + 原 commit SHA + 原文件 SHA256 + 新路径 + 接受边界）

| # | 复用对象 | 源分支（当天远端 SHA） | 原 commit SHA | 原文件 SHA-256 / 字节 | 新课程路径 | 接受边界 |
|---|---|---|---|---|---|---|
| R1 | **Data-7A/7B 数字灰阶 RTL** `rtl/dd1_d7a_gray_ctrl.sv.txt` | `poc/data-pwm-d7b-r3` = `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` | `f9fd09b184a69a27cdb409205dfd4f4151408a23`（DATA-7B-R3 限定接受版本，位于该分支历史中，已核 `ANCESTOR=YES`） | `6dbf464a49e49ad489188fa51920c30a3c89d6b3106046a4fefe558ef0a50c87` / 12982 B | `coursework/microled_sim/rtl/dd1_d7a_gray_ctrl.sv.txt`（**逐字节复制，`cmp` 验证 `BYTE_IDENTICAL=YES`**） | 仅「数字逻辑/时序控制器」；**无 MOS、无 PAM 电流阶梯、无 LUT、无光学精度声明**。Hybrid 3-bit PAM + 6-bit PWM 是**控制字段**，不是已实现的 9 位光学有效精度 |
| R2 | **Data-7A 契约** `reports/dd1_d7a_contract.md` | `poc/data-gray-d7a` = `6a1f5a192f3f1618499335c4365d717bfcadef39` | `6a1f5a192f3f1618499335c4365d717bfcadef39` | `90fa9e7e623dcc434388b3bc77e28436f1cf2fa0c0039062342bf59a52798b36` / 12214 B | 只读引用，不复制到课程目录 | 早期契约；R1 的 R3/R4 修订关闭了 4 项协议缺陷，故本轮以 R1 字节为准 |
| R3 | **Data-7B PWM 契约与时序语义** `reports/dd1_d7b_contract.md`、`reports/dd1_d7b_pwm_current.md` | `poc/data-pwm-d7b-r3` | `f9fd09b184a69a27cdb409205dfd4f4151408a23` | `44bea6ff4cfc4236002ad97b002f490295a93a0e5bc975f91930e443c9035478` / 25572 B；`d6952660b414fb6f5f643bb2a6423fd8bb9addc15b8f0ae14cf04a5e03d17638` / 27572 B | 只读引用；语义在 `rtl_interfaces.md` / `rtl_timing_report.md` 中标注 | 6-bit PWM 的「63 码占 64 个 tick」语义来自 R1 的 `FULL_HYB=64`；120 ns / 200 ns 为旧实验值，**不是教师给定条件**，60/100 Hz 预算须单独证明 |
| R4 | **PAM DC-R1 单输出 TT 基线** `reports/dd1_d7c_b_dc_report.md` | `poc/data-pam-d7c-b-dc-r1` | `61621f6e3d887082ecd6a7ecc1c771f8e509a24a`（限定接受登记；被审 tip `b7509c4766a6bbfd0413749d50a5f294192b60fb`） | `b340eccf52e99774fe398e80268ff46a497c50a8dcd597a7b6af964eab912aa4` / 15237 B | 只读引用，作为可比实验基线 | 仅「八档单输出 PAM 的 TT/27 °C 直流实测」：`I111 = 15.382706 µA`（相对 15 µA 目标 +2.55%）、`Iunit_ref = 1.922838 µA`、152 条 DUT 行。**不含 PVT/SOA、光学、版图、整芯片或量产签核** |
| R5 | **电流源基本单元拓扑** `dd1_d7c_a_sink_unit.scs` / `dd1_d6_bias_core.scs` / `dd1_d7c_a_pam_top.scs` | 同上 | `61621f6e3d887082ecd6a7ecc1c771f8e509a24a` | `289ae1dd8edf91c806c2c2dfecc15d9b3b8524ed987849d0094bab1124369a3f` / 3954 B；`379536efb1dd9b2626e93ec384d572c734d5c1b398881c6de6ce4405e230c293` / 120 B；`8489616e4826fccdd7516d7b02764ae3850ad3e4476181b5ae0f5249ec5a08a5` / 3778 B | 结构参考；课程 `spectre/` 下为**新写**的自研最小单元网表 | 源文件自身标注 `CANDIDATE / NOT SIMULATED`；其电流值不得冒充课程实测。器件 D/G/S/B 端序 `(d g s b)` 与显式 `Vss (vss 0) vsource dc=0` 沿用 `AGENTS.md` 已实测的坑 17/19 |
| R6 | **DC-R1 原始数值表** `dc_matrix_dut.csv` | 同上 | `61621f6e3d887082ecd6a7ecc1c771f8e509a24a` | `23e9e1fb6aed01497ef34e37196176e4305228fdbd1fc389dcd4e4cd4cd4cfc3` / 37947 B | 只读对照，不复制 | 历史真实数值，仅用于说明课程新测条件的适用局限 |

### 明确不作为已接受基线

`poc/data-pam-d7c-b-tr-r1` = `ec107af502b729225e49428e4d2d72bffc389dae`：2026-11-12 独立复审判 **REWORK**，B1–B5 未关闭（含用户报告的无 Git 环境 `--verify` 启动失败）。本轮**只把它当历史背景读取**，不引用其结论、不追认、不改写、不合并。

---

## 4. 本轮新增与禁止事项

- 新增文件全部在 `coursework/microled_sim/`，全局审查文件在 `reports/course_sim/`。
- **不修改**原项目源码、旧证据、旧判据、旧历史、旧审核包、旧账本。
- 不上传 PDK 本体 / 模型卡 / Calibre deck / 老师原始 ZIP / license 地址 / 凭据 / 私有用户路径 / 原始大 PSF / WLF。
- 课程分支从 `origin/main` 独立建立；最终只做常规 commit 与 `git push -u origin course/microled-assignment-sim-20261112`；不合并 `main`、不自动 PR、不登记 GO。
