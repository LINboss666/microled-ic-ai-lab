# Handoff — SCAN_UNIT_TEAM_BEAUTIFY（单路 Scan Driver 接收 + 独立库美化）

## 0. 身份与结论一览

| 字段 | 值 |
|---|---|
| 任务 | 从固定来源接收八模块单路扫描驱动，在本机重建独立 OA 库并美化 schematic + symbol |
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 只读来源分支 / 固定 SHA | `poc/scan-driver-1ch` / `9049f111d943e9b322f21e1fa059a932cac93207` |
| 已审基线 | `f21f30d249f729ef0108c9d1dcc78f642ba8bb18` |
| 我的工作分支 | `gexing321/scan-unit/1ch-beautify`（自固定 SHA 新建，BASE_SHA = `9049f11…`） |
| 分支名偏离 | 任务书建议 `feature/scan-unit-beautify-<id>`；本机 git 护栏 `remote.origin.push = refs/heads/gexing321/*:refs/heads/gexing321/*` 只允许推自己的命名空间，故改用 `gexing321/…`。**未**改动护栏配置。 |
| 本轮工作树 | 新建独立 clone `D:/IC项目/scan-unit-beautify/repo`；原有 `D:/IC项目/microled-ic-ai-lab`（`gexing321/scan-driver/c2mos-schematic` @ `6d23fb7`）未被切分支、未 pull、未 reset/clean/checkout -f |
| 目标新库（尚未创建） | `sc1_s3c_team_pretty`，库目录 `cadence_work/s3c_oa/sc1_s3c_team_pretty` |
| 本轮交付物 | 仅离线证据 + 本交接；**没有任何 OA 写入发生** |
| 推送 | 远端 `refs/heads/gexing321/scan-unit/1ch-beautify` = **`c6ffdd0caaf31d83ae86152ac685cf1c0af34bf6`**，`git ls-remote` 独立回读 = 本地 HEAD，普通推送、单 ref refspec、非 force、未跳 hook。途中通道断过一次（4 次失败已记在证据 APPENDIX C），恢复后全部落地。其余 ref 全部核对为未动：`main 23e471cb`、`poc/c2mos-dff cdd8597f`、`poc/data-driver-1ch b3d8bf43`、`poc/scan-driver-1ch 0038821e`、两个 `feature/* 6a8ba7dc / 51ca02a3`、`gexing321/docs 876c198`、`gexing321/scan-driver/c2mos-schematic 6d23fb7`。写这句话的提交在 `c6ffdd0` 之后，它自己是否落地请用同一条命令复查：`git ls-remote origin refs/heads/gexing321/scan-unit/1ch-beautify` |

### 六个状态（完成与阻塞严格分开）

| 状态 | 结论 | 依据 |
|---|---|---|
| SOURCE_FETCH | **COMPLETE** | 六份母本 `git show <SHA>` 逐字节 SHA-256 全部 MATCH（6/6）；四份黄金表复现行序一致；`--selftest` PASS（8 cell / 39 管 / 39 子绑定 / 48 方向行） |
| OA_IMPORT | **BLOCKED** | Cadence 所在的 RHEL6 guest 不可达：`vmrun list` 显示在运行、`checkToolsState` = running，但 `getGuestIPAddress` 失败、ssh `192.168.222.129:22` 连接超时。库未创建、spiceIn 未运行、16 个 view 一个都没有 |
| ELECTRICAL_EQUIVALENCE | **BLOCKED**（OA 侧未开始）+ 离线预比对 PASS | 与黄金表的 OA 回读比对必须有 OA 才能做。离线只完成一件事：现有 C²MOS 单元 vs 黄金 `c2mos_dff` 的逐管比对，见 §2 |
| SCHEMATIC_PRESENTATION | **NOT_STARTED** | 无库无图，无可美化的对象 |
| SYMBOL_PRESENTATION | **NOT_STARTED** | 同上 |
| VISUAL_REVIEW | **WAITING_USER** | 需要人工：(a) 在 Workstation 控制台恢复 guest 网络；(b) 通道恢复后按 §5 人工目视清单看图。自动像素捕获本来就不可用，不做闸门，也没有造占位 PNG |

一句话：**源侧全部核实通过，Cadence 侧一行未动，因为进不去那台机器。**

## 1. 离线做了什么（全部可复现）

命令：`python scripts/sc1_s3c_offline_verify.py --repo . --oa-readback-netlist <path> --scratch <dir>` → rc=0。
原始输出：`results/evidence/sc1_s3c_offline_verify.txt`。

| 项 | 结果 |
|---|---|
| 六份电路母本 blob 哈希 | `S3C_MASTERS: 6/6`（逐条 MATCH，含字节数） |
| `sc1_s3c_golden.py --selftest` | `S3C_SELFTEST: PASS`，`CELLS: 8`，`LEAF_DEVICES: 39` |
| 四份黄金表复现 | mos 39 / ports 48 / hier 8 / subinst 39，行序与内容 `IDENTICAL` |
| 导入文件发射 | `scan_import.scs` 104 行；`scan_params.il` 39 管；`scan_dirs.il` 48 行（schematic+symbol 两视图共 96 个对象） |

## 2. 旧 C²MOS 是否可复用（任务书 §7 第一个问题）

结论：**逐管电气字段等价，但有一处未解释的实例数差异，所以给"有条件复用"，不给无条件 PASS。**

比对对象是黄金 `c2mos_dff` 18 行 vs 我库里 `microled_cells/c2mos_dff_1bit` 的**数据库回读**（`spectre/generated/c2mos_dff_1bit_from_oa_readback.scs`，来自 `cadence_work/logs/sch_nograph_20261011_200240.log`，由 `skill/sch2_readback.il` 产出；分支 `gexing321/scan-driver/c2mos-schematic`，SHA-256 `0b566c321c3ea94fb69568d72ebe1dd3f59b6c52fa2e7ef544e78ee7b8e02664`）。

| 判据 | 结果 |
|---|---|
| 实例名集合 | 18 = 18，`name_set_equal=True`（mn_c/mn_k1..k4/mn_m1/mn_m2/mn_s1/mn_s2 + mp_ 同名套） |
| model / L / W / D / G / S / B | 18 行 × 7 字段 = 126 项，**mismatches = 0** |
| 端口冻结次序 | OA 侧 `subckt c2mos_dff_1bit (d clk q qbar vdd vss)` == 黄金 `d clk q qbar vdd vss` |
| 内部网名 | 两侧同名 `x1 x2 m mb y1 y2`，不需要映射表 |
| 逐行明细 | `results/evidence/sc1_s3c_c2mos_reuse_compare.csv`（18 行全 MATCH） |

未决项（必须在建新库之前用一次实时回读解决，不靠猜）：那次回读的 `RD-CELL` 报 `instances=24 nets=13`，而带 `model` 属性的只有 18 个；`terms=0` 是已知 API 假信号（应读 `cv->terminals`），但**多出的 6 个实例是什么**没有证据。因此新库里的 `c2mos_dff` 只做"按黄金母本导入"这一条路，旧图形版式可以在证明这 6 个对象是无电气内容的引脚/标注对象之后再复用。若它们带任何 net 连接，就不复用，直接采用固定来源副本。

## 3. 八模块状态

| cell | schematic | symbol | 说明 |
|---|---|---|---|
| `c2mos_dff` | NOT_STARTED | NOT_STARTED | 复用判定见 §2 |
| `sc1_scan_gate` | NOT_STARTED | NOT_STARTED | |
| `sc1_ls_core_r2d` | NOT_STARTED | NOT_STARTED | |
| `sc1_ls_c1_r2d` | NOT_STARTED | NOT_STARTED | 含 `mn_nt` S=ns_m / B=vss 的 bulk 细节，按黄金表落图 |
| `sc1_ls_c1_top_r2d` | NOT_STARTED | NOT_STARTED | 0 本层管 / 10 展开 |
| `sc1_r3_scan_chain_1ch` | NOT_STARTED | NOT_STARTED | 0 / 32 |
| `sc1_s3b_p33_bank_7` | NOT_STARTED | NOT_STARTED | mp1…mp7 显式 7 管，p33，L=0.4 µm、W=100 µm、m=1，S=B=vscan |
| `sc1_scan_power_1ch_s3c` | NOT_STARTED | NOT_STARTED | 0 / 39，去 iprobe 版，vscan 与 vdd33 保持两个端口不合并 |

`S3B`/`S3C` 的历史测试壳与 `sc1_ls_c0_r2d` 老对照路线本轮不碰。

## 4. 通道恢复后的执行顺序（已排好，不再重新设计）

1. 备份 `cadence_work/cds.lib` 与 `cadence_work/microled_cells`（复制，不覆盖原件），跑 `D:/IC项目/.schwork/sc1_precheck.sh` 只读体检：确认无用户 Virtuoso 进程、`smic18mmrf` 的 n18/p18/n33/p33 四个 master 在位、目标库名不存在。
2. `bash scripts/sc1_s3c_setup.sh sc1_s3c_team_pretty` → 独立库映射 `$WORK/s3c_oa/cds.lib`，脚本自证共享 `cds.lib` md5 前后不变。
3. 用 `scripts/sc1_s3c_asg.sh` 的形态跑本机 `spiceIn` 导入 §1 生成的 `scan_import.scs`：`outputLib=sc1_s3c_team_pretty`、`refLibList="smic18mmrf analogLib"`、`overwriteCells=NONE`、辅助 `topCell=s3c_asg_shell`（网表里已无同名 subckt，脚本第 34 行会拒绝同名）。这是网表→OA 转换，不是仿真。
4. 按 `skill/sc1_s3c_build_oa.il` 落实 `scan_params.il` 的 l/w/fw/m/fingers（回读 CDF 数值判断，不看 simW 文本，不改 PDK simW），再按 `skill/sc1_s3c1_apply_dirs.il` 落实 `scan_dirs.il` 的 48 行×2 视图方向。
5. 另开只读会话跑 `skill/sc1_s3c_readback.il` → `python scripts/sc1_s3c_verify_oa.py`：39 管 master/L/W/D/G/S/B、7 子实例 39 条绑定、48 schematic 端口 + 48 symbol terminal 全部对齐，取 `S3C_OA_GRAPH_EQUIVALENCE: PASS`。**在此之前不美化。**
6. 美化（只改几何与展示）：叶层 → symbol pin 定位 → 父图；父图按 DFF → BLANK gate → level shifter → PMOS bank 控制流；电源在上、地在下、信号左到右；只画真实连接点；`Xff.q`、`Xcore.x` 保留真实悬空并注明；移动 symbol pin 必须同步修新库所有受影响父图的线端点。
7. 叶到父 `Check and Save`：电气 error 零容忍，warning 分类记录（已知未用输出允许保留），不为清零 warning 加假负载。
8. 让 8 cell 在桌面快捷方式里可见：照 `scripts/sc1_libregister.sh` 的做法（只读参考，见 §4.5）备份 `cadence_work/cds.lib` 后追加**一条** `DEFINE sc1_s3c_team_pretty …`，保留全部原有 DEFINE/INCLUDE；再用 `scripts/sc1_libcheck.sh` + `skill/sc1_libcheck.il` 的同一种会话（cwd=`cadence_work`、HOME=`/root`、同一份 `cds.lib`、不带 `-cdslib`）证明可见，判据取脚本自己打印的 `LC-DONE resolved=t`，不取 `dbAccess` 的退出码。

## 4.5 来源分支在我固定之后又前进了 1 个提交（记录差异，不合并）

| 项 | 事实 |
|---|---|
| 远端 `poc/scan-driver-1ch` 现 tip | `0038821e6a93861848ac922ccca35c41a4de9bbb`（`git ls-remote` 独立回读） |
| 与固定 SHA 关系 | `9049f11` 是其祖先，领先 **1** 个提交：`local: register microled_scan_s3c in the cds.lib the desktop shortcut actually reads` |
| 六份母本 + 四份黄金表 | `git diff --name-only 9049f11 0038821 -- <十一个路径>` 输出**为空** ⇒ 一字未改，本轮按固定 SHA 做的核验继续有效 |
| 本轮要复用的七个工具文件 | 同样为空 ⇒ `sc1_s3c_golden.py / sc1_s3c_asg.sh / sc1_s3c_setup.sh / sc1_s3c_verify_oa.py / sc1_s3c_build_oa.il / sc1_s3c1_apply_dirs.il / sc1_s3c_readback.il` 与固定 SHA 完全一致 |
| 该提交只新增 | `reports/local_register_scan_library_20261015.md`、`scripts/sc1_libregister.sh`、`scripts/sc1_libcheck.sh`、`skill/sc1_libcheck.il` |
| 我的处置 | **未 merge、未 cherry-pick**（护栏与任务书都不允许把未审成果搬进我的工作分支）。只用 `git show 0038821:<path>` 读，把"注册 + 同一入口验证可见性"的做法在 §4 第 8 步本地重写 |
| 顺带收到的本机事实 | 那份报告实测这个 build 的 SKILL **没有 `getenv`**（`*Error* eval: undefined function - getenv`），取环境变量必须 `getshellenv` 且仍包 `errset`；`dbAccess -load` 在 SKILL 加载报错时照样返回 0，所以退出码不是判据。两条都与本机此前观察一致，继续生效 |

一个重要含义：源端那台机器的 `microled_scan_s3c` 已经**有完整 8 cell × 2 view 在盘上**（那份报告列了 72 个文件与顶层 `sch.oa`/`symbol.oa` 的字节数），但 `.gitignore` 排除 `*.oa`，所以 Git 里拿不到它。我这轮仍然是"按母本重建 + 自己美化"，不是"下载源端原 OA 字节"；若负责人另行私下发来源端最终 OA 包，可在核验来源后采用，但本轮没有等它，也没停住能做的源文件核验。


## 5. 需要人工的两件事

**(a) 恢复 guest 通道 —— 只能在本机 Workstation 控制台做**（agent 无法自助：进 guest 的唯一路径本身就是 ssh）。guest 内此前已获批准的一条命令：

```
pkill -9 dhclient; sleep 2; dhclient eth0        # 常驻续约，不动配置文件
```
若 `ip addr` 无 `inet` 但 dhclient 进程仍在，必须先 `pkill -9`，否则重复 `dhclient` 只会打印 "already running - exiting" 而永远拿不到地址。
不允许我做的（我也没做）：网卡 down/up 重启、改 `ifcfg-eth0`、动 VM 电源/快照/.vmx、改全局 ssh/代理/license。

**(b) 目视验收清单**（截图通道不可用，按任务书不作闸门，交人工判断）：顶层 `sc1_scan_power_1ch_s3c`、控制链 `sc1_r3_scan_chain_1ch`、转换核 `sc1_ls_core_r2d`、NAND `sc1_ls_c1_r2d`、装配 `sc1_ls_c1_top_r2d`、bank `sc1_s3b_p33_bank_7`、DFF `c2mos_dff`、选通 `sc1_scan_gate` —— 每项看两件事：schematic 网名/电源轨是否可辨认、symbol 的 pin 名是否落在自己的端子上（读取按 terminal→pins→figs→children，不按"最近文字"配对）。

## 6. 两个必须本地改一处源码的点（已核实到行）

| 位置 | 事实 | 计划 |
|---|---|---|
| `scripts/sc1_s3c_verify_oa.py:449` | `if 'microled_scan_s3c' not in master: continue` —— 只承认源端库名的子实例；换库名后层次检查会报"整棵树缺失" | 把库名做成参数（或 `--lib sc1_s3c_team_pretty`）。**黄金表与判定阈值不动** |
| `scripts/sc1_s3c_setup.sh:22-25` | 库名白名单 `sc1_s3c_*\|microled_scan_s3c`。**更正先前"该脚本拒绝 sc1_s3c_team_pretty"的二手判断**：实测 case 语句，`sc1_s3c_team_pretty` ALLOWED，`sc1_team_pretty` REJECTED | 无需改脚本，直接用建议库名 |

## 7. 边界与未做项（如实）

- 本轮没有：Cadence 写入、spiceIn、任何 OA 文件、任何仿真（任务书本轮明确排除 Spectre/ngspice/preflight/工作点）、layout/DRC/LVS/PEX、阵列/多通道/POR/UVLO/5 V/新工艺。
- 没有提交 PDK、模型卡、`cds.lib`、`*.oa`、raw PSF、凭据、机器库表或供应商绝对路径；本机 OA 与其备份按仓库既有策略留本机。若要实际接收美化后的 OA，结论是：**美化 OA 只在本机，尚未通过 Git 传输**。
- 未 merge、未 cherry-pick 队友未审成果、未 force、未跳 hook、未碰队长任何 ref；未做 gc/prune。
- 单一问题的尝试次数控制：guest 通道本轮 3 次只读探测（vmrun 地址查询、TCP/22、ssh BatchMode）后停止并保留现场，未使用任何改变状态的命令。
- POC 工作条件 TT / 27 °C / 1.8 V 与 3.3 V 只是来源侧已测条件，不当作面板签核；`core_ok33` 仍是外部接口假设，不是片内 POR/UVLO。

## 8. 证据文件

- `results/evidence/sc1_s3c_offline_verify.txt` —— 来源身份、六母本哈希、四黄金表复现、源侧工具事实、阻塞原始输出、复现命令。
- `results/evidence/sc1_s3c_c2mos_reuse_compare.csv` —— 18 行逐管 golden/oa 并排比对。
- `scripts/sc1_s3c_offline_verify.py` —— 上述离线判定的可复现脚本（只读 git，不碰 Cadence）。
- `results/evidence/sc1_s3c_handoff_validation.txt` —— 正式校验器（`D:/IC项目/.tools/validate_handoff.py`，sha256 `3c150d54…3e1e5`，仓库外、未修改）两次运行 + 一次反向对照：把 `scope_status` 改成 `COMPLETE`（而 `GUEST_CADENCE_CHANNEL` 是 FAIL）时校验器确实报 `FAIL — scope_status COMPLETE conflicts with a FAIL test`，所以这次的 PASS 不是空壳。
