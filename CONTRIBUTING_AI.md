# CONTRIBUTING_AI.md —— AI 参与本设计的固定工作流

本文件约束 **AI（Qoder）在本仓库里做 IC 设计时的行为**。人和 AI 都按它走。
它的存在理由很简单：**以后不得仅凭 AI 自己的总结报告判定电路正确。**

## 不可违反的 12 条

1. **先开 branch 再动手。** 一个 branch 只解决一个主要工程问题
   （`poc/*`、`feature/async-reset`、`feature/scan-output-stage`、`feature/data-current-sink`、
   `feature/level-shifter`）。禁止把 DFF + level shifter + 输出驱动 + 版图标进同一个 commit。
2. **不改 PDK。** 不修改、不重命名、不移动任何 foundry/老师交付的 PDK、`cds.lib`、techfile、
   模型卡、Calibre deck、已有 library、已有 schematic/layout。不确定是否只读时，按只读处理。
3. **不提交 PDK。** `.gitignore` 只是遮眼，真正的闸是 `scripts/precommit_safety_check.py`
   （pre-commit 查 staged blob，pre-push 查全历史 blob）。PDK 路径一律通过
   `spectre/pdk_local.env`（未被跟踪）以 `${QODER_PDK_LIB}` 形式注入 netlist。
4. **不提交秘密。** 凭据、SSH 私钥、token、license 服务地址值都不得进入工作树可跟踪区，
   更不得进入历史。凭据只允许存在于 `.ic617_agent_bridge_credentials`（已 ignore）。
5. **`spectre 0 errors` ≠ 电路 PASS。** 必须有数值断言：窗口电平、跨点时间、min/max、违例计数。
   工具是 `scripts/run_spectre.sh` + `scripts/psf_check.awk`；只看 log 里"没有 ERROR"**不构成证据**。
6. **失败方案不得伪装成 PASS。** 失败的 netlist、checker、结论原文必须留在仓库里，
   作废的结论用显式"作废"标注保留原文，不允许为了让仓库好看而删历史。
7. **假设必须标来源。** 每条参数归入且只归入一类：
   `COURSE_REQUIREMENT` / `COURSE_FIGURE` / `TEACHER_PAPER` / `ENGINEERING_DERIVATION` /
   `GPT6_LEGACY_PROPOSAL` / `POC_ASSUMPTION` / `NOT DEFINED`。
   `course_source/spec_v12_text.txt` 属于旧 GPT-6 生成方案 = `GPT6_LEGACY_PROPOSAL`，
   永远不得升格为 `TEACHER_PAPER` 或 `COURSE_REQUIREMENT`，除非同一事实能在老师正式题目
   文字、正式布局结构图，或老师论文（Xiao et al., Micromachines 16(2) 207, 2025,
   DOI 10.3390/mi16020207）里独立找到。通道方向这类结构结论 = `COURSE_FIGURE` +
   `ENGINEERING_DERIVATION`。违规由 `python scripts/provenance_check.py` 机检。
   题目没给的（灰阶位数、消隐、PWM 深度、pitch、Vf、VLED、VDD、复用系数、输出域）
   保持 `NOT DEFINED`，**不得当已知量继续往下算**。
8. **结构/方向类结论必须有出处。** 谁驱动谁、行列数量、电压域这类判断，要引用课程材料
   文件 + 段/行号；自己加的工程假设要显式写"这是假设"。
9. **一次修复尝试不超过 3 次。** 超出就停下来，输出 transistor-level 拓扑、每个 MOS 的
   D/G/S/B 接法、每个时钟相位哪些管导通，交给人工检查，而不是继续换第三种方案。
10. **每轮结束必须生成 review bundle**（`scripts/make_review_bundle.py <BASE> <HEAD>`），
    里面必须有真实源码（netlist / testbench / checker / 生成脚本）、验证报告和小型数值结果。
    只放 Markdown 总结不算交付。
11. **人工/ChatGPT 审核通过之前，不得自动进入下一阶段。** 包括但不限于：加复位、做输出级、
    做电平搬移、开版图。
12. **不碰虚拟机与账号的危险操作。** 不做电源/快照/`.vmx` 操作，不改 license 配置，
    不为兼容性降低全局 SSH 安全设置，不向用户索要密码或 token。

## 每轮固定动作（命令都可直接复制）

```bash
# 0) 开工前：确认在 branch 上，不在 main
git switch -c poc/<topic>

# 1) 实现 + 数值验证（Spectre 在 guest 上跑，Windows 侧只做镜像与 git）
bash scripts/sync2guest.sh spectre/<file>.scs scripts/<file>.sh
bash scripts/guest.sh ssh "bash /root/microled_ai_project/scripts/<check>.sh ..."

# 1b) 任何正式 transient 之前：testbench 自检（rail/0 参考/VDD 值；FAIL 即禁止仿真）
bash   scripts/tb_preflight.sh /root/microled_ai_project/spectre/<tb>.scs 1.8 <tag>
bash   scripts/tb_preflight.sh /root/microled_ai_project/spectre/preflight_negative_vss_float.scs 1.8 bad   # 必须 FAIL

# 1c) checker 自身的合成波形用例（不得拿被测电路验证判据）
python scripts/test_psf_check.py --write-transcript results/checker_unit_test.txt
python scripts/netlist_stats.py            # 器件计数由 netlist 生成并核对报告文本
python scripts/provenance_check.py         # 来源标签与绝对化描述

# 2) 把关键数值落到 results/（大波形数据库不入库），并核对判据修复前后的一致
python scripts/export_results.py
python scripts/regression_compare.py --old results/history/<before>.csv --new results/evidence/<after>.txt

# 3) 提交：pre-commit 闸会自动跑；单独手动跑也一样
python scripts/precommit_safety_check.py --mode staged

# 4) 生成评审包（自动跑 --mode history 闸）
python scripts/make_review_bundle.py <BASE_SHA> HEAD
```

## Review bundle 是给谁看的

给**人**和**另一个模型**看源码与 diff 的，不是给本 AI 自己打分用的。因此它必须包含真实
transistor-level netlist、testbench、checker 脚本、参数生成脚本和仿真数值，且必须包含
**已知失败与不确定点**；REVIEW_README 里必须主动提出本轮最不确定的 1–3 个设计问题。

## 什么绝不进仓库

任何 PDK 本体或模型卡原文、DRC/LVS/XRC deck、老师原始 ZIP、raw PSF/波形数据库（几十 MB～GB）、
VM 镜像、凭据与 key/token、`spectre/pdk_local.env`、`logs/`（桥运行日志）、`course_source/`
（老师交付的课程文档原件，只保留我们自己写的、带出处的报告）。
