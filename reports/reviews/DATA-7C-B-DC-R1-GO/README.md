# DATA-7C-B-DC-R1 独立复审 GO 与限定接受登记

- 被审对象：`b7509c4766a6bbfd0413749d50a5f294192b60fb`（DATA-7C-B-DC-R1 的包回执 tip，tree `d91179901252d0b9c627faaa60478b2ce466252d`）
- 复审：`REVIEW_DATA7C_B_DC_R1_GO_20261026.md`，8503 B，sha256 `a4322daa0b127085762fcb9dcb53768e2a7fb9c19f0b1492fd7ad6b3d1cf1e24`，与用户附件逐字节相同（本目录只放这一份复审文件；本轮没有复审方 ZIP）
- 结论：`REVIEW_RECOMMENDATION=GO（限定）`，F1–F4 全 `CLOSED`，`NEW_BLOCKING_FINDINGS=0`
- 用户决定：`登记，限定范围`；两个非阻断待办的处置：`并入瞬态阶段`（原话记在 `registration.json`）

## 接受的是什么

八档单输出 PAM 在 TT/27 °C 的直流结果（152 DUT + 152 预检行，满量程 15.38270557 µA 落在 14.25–15.75 µA，
`Iunit_ref = 1.92283819625 µA`，严格单调，逐档残差小于 0.25 个单位），以及 DATA-7C-B-DC-R1 的离线提取／
判定／发布身份修补（有符号区间、必需信号缺失即拒收、完整矩阵前置、身份取 Git blob）。

## 不是什么

不合并 main、不批准任何原生启动、不追用上一轮余下的 4 次额度；不声明光学有效位数／SOA／失配／PVT；
云端未从原始 PSF 重提取，`.raw`/`.log` 仍在执行机；执行方 ZIP 不在仓库里，其字节与摘要写在被审提交的提交信息里。

## 登记时我自己核了什么

- 复审仪器 `probe_dc_review_gaps.py` 的 sha 与被审提交内的副本一致：`d48448b1…`
- `337563fc2269` → `b7509c4766a6bbfd0413749d50a5f294192b60fb`：新增 51 路径、删除 0、改动恰为三个 DC 脚本、2878 条既有路径 blob+mode 不变、3 笔提交
- `git diff --check 337563fc2269..b7509c4766a6bbfd0413749d50a5f294192b60fb` 输出 0 行；本轮记录 `source_identity.csv` 195 行路径唯一
- 远端两通道分别回读（`git ls-remote` 走系统代理 + GitHub API 直连），两条都等于被审 SHA，`main` 与被审基线未动
  ——具体时刻与 rc 逐条记在 `registration.json` 的 `remote_readback` 里
- 复审附件本身含 0 行带行尾空白：原样归档不改，避免以后把这条读成被审内容的缺陷

## 两个非阻断待办（按用户选择并入下一个自包含瞬态任务）

1. `matrix.py::observe()` 的必需集未列 `vss`，与提取器的必需清单不齐。
2. `data_out` 跟住夹持的 20 mV 护栏偏宽，复审建议收到 `1e-6 V + 1e-9*abs(clamp)` 量级并用真实导出精度验证；
   本轮 304 行实测差值均为 0，未因此受影响。

另记一笔交接注意：本目录在被审提交之后加入，任何之后重发布 R1 记录的一轮要把 `reports/reviews/DATA-7C-B-DC-R1-GO/`
列进它自己允许的新路径；本轮登记不动脚本、数值与账本。
