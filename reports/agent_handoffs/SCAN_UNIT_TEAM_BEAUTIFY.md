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
| 目标新库 | `sc1_s3c_team_pretty`，库目录 `cadence_work/s3c_oa/sc1_s3c_team_pretty`（**已创建，8 cell × 2 view 在盘**） |
| 本轮交付物 | 离线来源核验 **+ 真实的 OA 重建与电气等价证明**；美化仍有余量，见下 |
| 推送 | 远端 `refs/heads/gexing321/scan-unit/1ch-beautify` = **`c6ffdd0caaf31d83ae86152ac685cf1c0af34bf6`**，`git ls-remote` 独立回读 = 本地 HEAD，普通推送、单 ref refspec、非 force、未跳 hook。途中通道断过一次（4 次失败已记在证据 APPENDIX C），恢复后全部落地。其余 ref 全部核对为未动：`main 23e471cb`、`poc/c2mos-dff cdd8597f`、`poc/data-driver-1ch b3d8bf43`、`poc/scan-driver-1ch 0038821e`、两个 `feature/* 6a8ba7dc / 51ca02a3`、`gexing321/docs 876c198`、`gexing321/scan-driver/c2mos-schematic 6d23fb7`。写这句话的提交在 `c6ffdd0` 之后，它自己是否落地请用同一条命令复查：`git ls-remote origin refs/heads/gexing321/scan-unit/1ch-beautify` |

### 六个状态（完成与阻塞严格分开）

| 状态 | 结论 | 依据 |
|---|---|---|
| SOURCE_FETCH | **COMPLETE** | 六份母本 `git show <SHA>` 逐字节 SHA-256 全部 MATCH（6/6）；四份黄金表复现行序一致；`--selftest` PASS（8 cell / 39 管 / 39 子绑定 / 48 方向行） |
| OA_IMPORT | **COMPLETE** | guest 通道恢复后完成。独立库 `sc1_s3c_team_pretty` 建立（`sc1_s3c_setup.sh` 接受该库名，共享库表 md5 前后不变）；spiceIn 导入 8 cell × schematic+symbol：`INFO (SPICEIN-33)`×9、`SPICEIN-54`、`ASG_PROBLEM_LINES: 0`、盘上 55 文件；CDF 尺寸 39 管逐管落实并 `S3CB-SAVE (t)`×8；方向 48 行落 16 视图 `S3C1D-VIEWS 16 MATCHED 96 WANT 96` |
| ELECTRICAL_EQUIVALENCE | **COMPLETE** | 写完另开**只读**会话回读，再 `python scripts/sc1_s3c_verify_oa.py`：`S3C_OA_GRAPH_EQUIVALENCE: PASS`、`S3C_VERDICT_COUNTS failures=0 notes=3`。39 管 / 7 子实例 / 48 schematic 端口 / 48 symbol terminal / 连接行 46-46 / 等价 cell 8-8 / `dbCheck` 全 t。反向对照 `S3C_NEGATIVE rc_tampered=1 rc_intact=0` ⇒ PASS 不是空转 |
| SCHEMATIC_PRESENTATION | **PARTIAL** | 电气已就绪，版式未整理：三张父图层实例**并非**重叠在 0×200（`Xbank` 在 x≈-0.06、`Xchain` 在 x≈3.06，源端报告的说法在我库里不成立），但端口 iopin 全挤在同一侧、线上无网名（回读 116 个对象 `text=nil`）。按 §7 要求还差左进右出、电源上/地下的排布与网名 |
| SYMBOL_PRESENTATION | **PARTIAL** | 48 个 terminal 方向正确，每个都带一个 pin 矩形（父层 23 个 `figType="rect"`），但 ①全部堆在 symbol 右边缘（x≈1.1625-1.3375）②没有外框③没有引脚名标签（`text=nil`）。注意 `dbGet(sy "figures")` 返回 0 是**取错集合**，不是符号为空——必须走 terminal→pins→figs |
| VISUAL_REVIEW | **WAITING_USER** | 自动像素捕获在本机不可用，不作闸门，也没有造占位 PNG；请按 §5 人工打开清单目视 |

一句话（本轮更新）：**源侧核实通过，OA 侧已在这台机器上重建完成并通过电气等价校验；剩下的只是版式整理，不改变电路。**

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

| cell | schematic | symbol | 回读实测（管数 / 端口 / 子实例） | 版式还差什么 |
|---|---|---|---|---|
| `c2mos_dff` | 在盘 | 在盘 | 18 管 / 6 端口 / shapes 219 / schCheck (0 5) | 18 管分区与网名；symbol 外框与引脚名 |
| `sc1_scan_gate` | 在盘 | 在盘 | 4 管 / 5 端口 / shapes 53 / (0 1) | 同上（4 管串并联） |
| `sc1_ls_core_r2d` | 在盘 | 在盘 | 6 管 / 6 端口 / shapes 78 / (0 2) | 左右对称、交叉耦合要看得出 |
| `sc1_ls_c1_r2d` | 在盘 | 在盘 | 4 管 / 5 端口 / shapes 53 / (0 1)；`mn_nt` 的 S=ns_m、B=vss 已按黄金表落好，未被"bulk 接 source"简化 | 栈形清楚即可 |
| `sc1_ls_c1_top_r2d` | 在盘 | 在盘 | 0 本层管 / 6 端口 / 2 子实例 / shapes 42 / (0 1) | 端口 iopin 同侧堆叠，未左进右出 |
| `sc1_r3_scan_chain_1ch` | 在盘 | 在盘 | 0 / 8 端口 / 3 子实例 / shapes 60 / (0 1) | 未按 DFF→BLANK→LS 控制流排布，无线上网名 |
| `sc1_s3b_p33_bank_7` | 在盘 | 在盘 | 7 管 / 3 端口 / shapes 101 / **schCheck (0 0)** | 七管横向等间距与三条公共网标注 |
| `sc1_scan_power_1ch_s3c` | 在盘 | 在盘 | 0 / 9 端口 / 2 子实例 / shapes 37 / **(0 0)** | 电源轨分通道、网名 |

八 cell 的 16 个 view 全部在盘且全部可只读打开（`views_opened=16 of 16`），`dbCheck` 全 t，`schCheck` 第一个元素（error 数）在八个 cell 上都是 0，合计 11 条非 error 提示。`S3B`/`S3C` 历史测试壳与 `sc1_ls_c0_r2d` 老对照路线本轮不碰。

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
- `results/evidence/sc1_s3c_handoff_validation.txt` —— 正式校验器（本机 `.tools/validate_handoff.py`，sha256 `3c150d54…3e1e5`，仓库外、未修改）多次运行 + 一次反向对照：把 `scope_status` 改成 `COMPLETE`（而 `GUEST_CADENCE_CHANNEL` 是 FAIL）时它确实报 `FAIL — scope_status COMPLETE conflicts with a FAIL test`，所以 PASS 不是空壳。
- `results/evidence/sc1_s3c_oa_session_verdicts.txt` —— 建库/导入/尺寸/方向/回读五个会话自己打印的 token 行（绝对路径已脱敏），逐字取自日志，不是我复述。
- `results/evidence/sc1_s3c_oa_readback_pass1.txt` —— 只读回读的 281 条记录（39 管 + 55 实例 + 48 端口 + 48 symbol terminal + dbCheck）。
- `results/evidence/sc1_s3c_connectivity_beautify.csv` / `sc1_s3c_equivalence_beautify.csv` / `sc1_s3c_ports_beautify.csv` / `sc1_s3c_oa_readback_beautify.csv` —— 校验器输出：46 条连接逐条 MATCH、8 cell 设备行数一致、端口名/序/向一致。
- `spectre/generated/sc1_s3c_team_pretty_from_schematic.scs` —— 从 OA 回读**抽取**的电路表（不是仿真产物，也不是母本复制），给 reviewer 与六份母本对眼。
- `results/evidence/sc1_s3c_parent_geometry_dump.txt` —— 三张父图 + bank 的几何实读（实例 bbox、pin fig、线/标签类型计数）。
- `results/evidence/sc1_s3c_libvis_check.txt` —— 用快捷方式同一会话形态打开 16 个 view 的结果与 `schCheck`/`dbCheck` 逐 cell 读数。
- `scripts/sc1_libreg_team.sh` / `skill/sc1_libvis_check.il` / `skill/sc1_s3cb_geom_dump.il` —— 本轮新增的三个小局部工具（注册、可见性、几何实读），都不改电路。

## 9. 本轮实际在 Cadence 上做了什么（通道恢复之后）

顺序、命令与原始 token 都在证据里；这一节只写"结论 + 被推翻的说法"。

| 步 | 动作 | 机器上的判据（不是我复述，是日志原行） |
|---|---|---|
| 0 | 只读体检 | 无用户 Virtuoso 进程；`smic18mmrf` 的 n18/p18/n33/p33 四个 master 在位（各带 spectre+symbol view）；磁盘 5.1G 可用 |
| 1 | 备份 | `cadence_work/backup_scan_unit_20261015/microled_cells` 与原 `cds.lib`；树指纹前后 `8ecc6aa4…` 相同，50 文件；`cds.lib` sha256 `690b623f…` 一致 |
| 2 | 建库 | `sc1_s3c_setup.sh sc1_s3c_team_pretty`：`SHARED_CDS_LIB_UNCHANGED: yes`（md5 前后同），隔离映射里 7 条 DEFINE |
| 3 | spiceIn 导入 | 8 cell 全部 `schematic=yes symbol=yes`（另有导入辅助壳 `s3c_asg_shell` 只有 schematic）；`ASG_PROBLEM_LINES: 0`；`INFO (SPICEIN-33)`×9 + `SPICEIN-54`；盘上 55 文件 / 780 KB；**没有**新建锁 |
| 4 | 落实尺寸 | `S3CB-OPEN` 每 cell 都给出 raw/CDF 两侧读数，39 管逐管 `S3CB-PROP` 后 `S3CB-AFTER` 的 `num_l/num_w` 等于黄金值；8 个 cell `S3CB-SAVE (t)`；`simW` 只读不写 |
| 5 | 落实方向 | `S3C1D-VIEWS 16 MATCHED 96 WANT 96`（48 端口 × 2 视图）；96 条 apply 行全部 `after==want`，`after_ne_want=0` |
| 6 | 只读回读 | 另开会话：`S3CR-MOS` 39 行、`S3CR-PIN` 48、`S3CR-SYMT` 48、`S3CR-INST` 55；`terms=0` 依旧（该字段在此 build 不可信），端口从 `cv->terminals` 取 |
| 7 | 电气比对 | `S3C_OA_GRAPH_EQUIVALENCE: PASS` / `S3C_VERDICT_COUNTS failures=0 notes=3` / `S3C_CONNECTIVITY_MATCH: 46-46` / `S3C_EQUIVALENCE_MATCH: 8-8` / `S3C_DBCHECK_ALL_T: yes`；反向对照 `S3C_NEGATIVE rc_tampered=1 rc_intact=0` |
| 8 | 注册到快捷方式库表 | `scripts/sc1_libreg_team.sh`：`DEFINE` 6→7，只多出我这一条，其余 6 条 `OTHER_DEFS_INTACT=6/6`；第二次运行 `ALREADY_REGISTERED … no change made`（幂等实测） |
| 9 | 可见性 + 编辑器检查 | 以快捷方式同一会话形态（cwd=`cadence_work`、无 `-cdslib`）跑：`LIBVIS-SUMMARY views_opened=16 of 16`、8 个 cell `dbCheck=t`、`schCheck` 的 error 位全 0，非 error 合计 11 条 |

### 被本轮实测推翻的三条说法

1. **"多出的 6 个实例身份不明"**（上一轮我留的活口）：新导入的黄金 `c2mos_dff` 同样 `instances=24 / pdkMos=18`，6 个差额逐条是 `master="basic"/"iopin"` 的端口对象、`instTerms=0`。**结论：旧 C²MOS 与黄金在实例构成上同形，复用条件成立**（详见 §2）。
2. **"父图层实例全挤在 0×200"**（源端 S3C3 报告的描述，我原打算照它的说法排工作）：我库里 `sc1_scan_power_1ch_s3c` 的 `Xbank` 在 x≈-0.06、`Xchain` 在 x≈3.06，三张父图分别有 18/26/37 条 `type="line"` 和 9~11 条 `type="label"`。**父图不是空的，也没有重叠**，源端那句是我没核就抄的，现按实测更正。
3. **`sc1_s3c_setup.sh` 拒绝 `sc1_s3c_team_pretty`**（上一轮我从二手判断写进交接的）：白名单是 `sc1_s3c_*`，实测 `ALLOWED`，本轮就是用它建的库。

### 还欠什么（明确人工待办，不改电路）

- symbol 视图：48 个 pin 全在符号右缘（`figType="rect"`，x≈1.1625–1.3375）、无外框、无引脚名（`text=nil`）。要做的是按角色分边（入左/出右/电源上/地下）+ 外框 + 名字标签，且**必须先定叶层 pin 位置再动父图线端点**。
- 叶层 schematic：`c2mos_dff` 等仍是 spiceIn 默认排布，未做分区对齐；bank 的七管等间距未整理。
- `sc1_s3c_verify_oa.py` 我改了 2 处（`LIB_NAME` 取自 `S3C_LIB`、449 行原硬编码库名），黄金表与阈值未动；`sc1_s3c1_apply_dirs.il` 里那行 `cdr` 在此 build 未绑定，导致它的行数守卫永远打印 `REFUSE … 0 rows` 却不中止（本轮 96/96 落对了，是靠后面的逐行 `after==want`，不是靠那个守卫）——这条建议下一轮连同库名一起参数化。
- 目视仍未做：本机没有可用取图通道，`VISUAL_REVIEW=WAITING_USER`，清单见 §5。美化后的 OA 只在**这台机器的这台 guest**上，Git 里没有 `*.oa`，没有上传，也没有冒充上传。

## 10. 复现（Cadence 侧）

```
PROJ=/root/microled_ai_project
LIB=sc1_s3c_team_pretty bash scripts/sc1_s3c_setup.sh $LIB
cp <本轮 scratch>/scan_import.scs $PROJ/cadence_work/s3c_oa/asg_in/sc1_s3c_import.scs
LIB=$LIB bash scripts/sc1_s3c_asg.sh
S3C_LIB=$LIB S3C_TABLE=$PROJ/cadence_work/s3c_oa/asg_in/sc1_s3c_param_table.gen.il \
  bash scripts/sc1_s3c_run_oa.sh $PROJ/cadence_work/s3c_oa/skill/sc1_s3c_build_oa.il 900 S3CB_DONE
S3C_LIB=$LIB S3C1_DIRS=$PROJ/cadence_work/s3c_oa/asg_in/sc1_s3c_dirs.gen.il \
  bash scripts/sc1_s3c_run_oa.sh $PROJ/cadence_work/s3c_oa/skill/sc1_s3c1_apply_dirs.il 900 S3C1D_DONE
S3C_LIB=$LIB bash scripts/sc1_s3c_run_oa.sh $PROJ/cadence_work/s3c_oa/skill/sc1_s3c_readback.il 900 S3CR_DONE
S3C_LIB=$LIB python scripts/sc1_s3c_verify_oa.py --golden <golden> --readback <pass1.log> --out <dir> --negatives
```

注意 token 名：方向脚本自己的结束 token 是 `S3C1D_DONE`（不是 `S3CD_DONE`）。本轮我先在这里报错过一次，runner 因此正确地报了 FAIL。

