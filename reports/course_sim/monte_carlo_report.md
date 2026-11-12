# Monte Carlo 报告（原生 Spectre，30 样本）

任务号 `COURSE-MICROLED-SIM-20261112-R1` ｜ 2026-11-12
**`MONTE_CARLO: RUN`**（30/30 样本成功，全部来自原生求解；无合成分布）。

---

## 1. 统计模型能力（实测，不是假设）

| 检查 | 结果 |
|---|---|
| `spectre -h montecarlo` | 存在；说明其为 swept analysis + child analyses，引用 statistics blocks |
| 老师 SMIC 0.18 µm mmrf Spectre 模型卡 | 只读语法计数：`statistics` 23 块、`vary` 69 条、`process` 5 块、`mismatch` 18 块 |
| 明确的统计 section | `section mos_mc`，且该节内同时有 `statistics { process {...} }` 与 `statistics { mismatch {...} }` |
| 因此 | `MC_BLOCKED_NO_STAT_MODEL` **不成立**；`variations=all` 合法 |

模型卡内容与 `section` 之外的参数值**未复制到仓库**；`include "${QODER_PDK_LIB}" section=mos_mc`
的真实路径由未跟踪的本地环境文件在运行时注入。

## 2. 运行参数（单 job、单 seed、单角）

```
mc1 montecarlo numruns=30 seed=20261112 variations=all sampling=standard
    donominal=yes savefamilyplots=yes savedatainseparatedir=yes annotate=status {
  dc_mc dc
}
```

| 项 | 值 |
|---|---|
| 选用的变化类型 | **process + mismatch（all）** |
| 随机种子 | `20261112`（只此一个，未换 seed、未换角、未多轮重跑） |
| 样本数 | 30（任务上限 30） |
| 固定测量条件 | `Vclamp = 1.20 V`、`vdd18 = VCAS = 1.8 V`、`VSS = 0`、`IREF = 15 µA`、27 °C |
| 观测量 | `Ip_out:i`（固定输出偏置下的下拉电流） |
| nominal run | 有，`Iout = 14.931914727 µA` |
| 求解成功 / 失败 / 剔除 | **30 / 0 / 0** |

## 3. 两次启动的完整披露（请独立复审裁定预算口径）

**这是本轮最需要独立判断的一点，不隐藏、不自行判定通过。**

| # | 时间 | 命令 | rc | 样本求解 | 说明 |
|---|---|---|---|---:|---|
| 1 | 15:11:03 | `spectre course_mc.scs -64 -format psfascii` | **2** | **0** | 网表把子分析写成一行 `{ dc_mc dc }`，本 build 报 `SFE-874 Unexpected identifier "dc_mc"`、`spectre terminated prematurely`。**没有任何电路仿真、没有任何样本**。日志已归档为 `MC_start1_PARSE_FAIL.log` |
| 2 | 15:11:57 | 同上（只把子分析改成独立一行） | **0** | **30** | 正式 30 次迭代，`0 errors, 1 warning`；30 个 `mc1-001..030` 样本目录全部产出 |

**执行方口径**：第 1 次是语法解析失败启动（0 次求解），不构成「1 个正式 Monte Carlo job」；
第 2 次是唯一的正式 job。修复属于任务书 §6 允许的「单个根因 ≤3 次修复」，
且**未改 seed、角、样本数、判据、阈值**，只改了一个换行。

**最严格口径**：若独立复审把「任何 `spectre` 进程启动」都计入 MC 上限，
则本项应判 `BLOCKED_OVER_BUDGET`（2 次启动 > 1 job），30 个样本的数值只能作为
参考而不能算作业交付。**此项裁定权交给独立复审者，执行方不自行宣布通过。**

## 4. 实际数值（`results/mc_samples.csv`，30 行原始值）

| 统计量 | 值（µA） |
|---|---:|
| 样本数 n | 30 |
| 均值 | **14.932017725** |
| 样本标准差（ddof=1） | **0.008887858** |
| 总体标准差 | 0.008738472 |
| 中位数 | 14.930975575 |
| 最小 / 最大 | **14.919569356 / 14.955811957** |
| 均值 − 15 µA 目标 | −0.067982275 µA（−0.453215 %） |
| 变异系数 CV | 0.059522 % |

直方图：`figures/mc_histogram.svg`（8 bins，**由 30 个真实数值计算**，含均值线与 15 µA 目标线）。
统计脚本：`checks/analyze_analog.py` → `results/mc_stats.json`、`results/analog_summary.json`。
**没有剔除任何坏点，没有补点，没有合成分布。**

## 5. 警告与数据可靠性

`WARNING (SPECTRE-16006): Redundant monte carlo analysis was encountered. Neither scalar data nor
waveform data will be saved.` —— 因为网表里没有定义 `export` 标量表达式，ADE 风格的
`scalarfile` / `paramfile` 未生成。但 `savefamilyplots=yes savedatainseparatedir=yes`
**确实写出了 30 个逐迭代 PSF 文件**（`mc1_separate/mc1-001..030/mc1_dc_mc.dc`），
本报告全部 30 个数值均从这些文件的 `Ip_out:i` 字段抽取，`mc1.mapping` 也列出了 1..30 的目录映射。
原始 PSF 保留在原生主机沙箱，不入仓库。

## 6. 结论边界

30/30 样本在固定 1.20 V 夹持下给出极小的离散（CV ≈ 0.06 %），且均值与 TT 直流点一致。
这**只**说明本基本单元在该固定偏置、该统计模型、该 seed、30 个样本下的电流离散；
不代表工艺角覆盖、SOA、失配对全阵列/光学灰阶的影响、良率、或整芯片签核。
30 样本量过小，不能据此做分布尾部或良率外推。

## 7. 请独立复审回答

1. §3 的两次启动是否应计为超出「1 个正式 MC job」上限？若按最严格口径，本项结论应如何改写？
2. `SPECTRE-16006` 下从逐迭代 PSF 抽取标量，是否可接受为「原生 MC 数值证据」？
3. 未定义 `export` 表达式是否应视为 MC 设置不完整（`PARTIAL`），即使 30 个样本数值齐全？
