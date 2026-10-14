# SCAN-1 S3-C4 —— 只修 Symbol 的名称标注与图形短线

审核起点 `50a630e3c2b295a173d0fdf08d4b85edb6995d24`（本地 = `git ls-remote` = `gh api` 三方一致，工作树干净）。
唯一可写 OA 库：`/root/microled_ai_project/cadence_work/s3c_oa/microled_scan_s3c`。
范围只有 8 个 Symbol 视图里的**名称标签位置/归属**与**非电气图形短线**；terminal 名、方向、端口顺序、net 绑定、
pin 矩形、39 只 MOS、父原理图的实例/导线/wire label、叶原理图与晶体管图、PDK/母本/共享件一律冻结。
`NEW_SIMULATION_RUNS = 0`，未进 S4。

## 0 审核事实（先把上一轮的状态写对）

| 项 | 状态 | 依据 |
|---|---|---|
| SCREENSHOTS_RECEIVED_BY_REVIEWER | **YES** —— 六张完整原生视图 + mp5 局部图已由用户人工截图并提交云端审核 | S3C4 任务书；本地 `sc1_s3c4_*` 不复制这些图（任务书要求 BEFORE 图作为 REVIEWED_FAIL 来源归档在云端） |
| S3C3 的 VISUAL_REVIEW 结论 | **REVIEWED_FAIL_SYMBOL_LABELS**，不是"尚无截图" | 任务书审核意见；本报告 §1 |
| 本轮修后 VISUAL_REVIEW | **WAITING_REVIEWER**（本地无权判定；四张 AFTER 图待人工截） | §6 |
| 电气接线记录 | 39/39 层次 pin、23/23 外部 port 的 S3C3 已审结论继续有效，本轮未重布任何线 | `sc1_s3c4_log_pins_before_check.txt` / `..._after_check.txt` 两份都用 `scripts/sc1_s3c3_verify.py` 判 PASS |

`scripts/sc1_s3c3_shots_verify.py` 现在仍报 6 MISSING，这与云端已收图并不矛盾：截图来源是用户人工，未落地进本地工程。

## 1 审核指出的显示错误，以及真正的根因

审核看到的是：顶层 Symbol 底部接地 pin 旁边显示 `clk`、`vss` 文字留在右上；父图里 Xchain 底部连 vss 却标 `blank`、
右侧 gate33 旁又出现 `clk`；Xff 底部连 vss 内部标 `vdd`；Xcore 底部连 vss 内部仍是 `x`。

只读实测（`skill/sc1_s3c4_dump_symbols.il` → `sc1_s3c4_log_dump_symbols.txt`，8 个 Symbol 视图、48 个 terminal）说明：

* **归属关系在库里是对的**：48 个 pin figure 每个都恰好带 1 个 child 文字对象，layer `pin` purpose `label`，
  其 `theLabel` 就等于该 terminal 的名字（`SD-PINFIG owner=` 与 `SD-CHILD ... theLabel=` 双证）。
* **错的是位置**：S3C2 把 pin 按角色移到新边之后，标签文字没跟着走。例如 `sc1_scan_power_1ch_s3c` 的 vss
  pin 矩形在 y `-0.925..-0.75`（底部），其标签锚点仍在 `(1.125 0.5)`；`clk` 的标签在 `(0.0 -0.5)`，于是
  底部 pin 旁边显示的是别人的名字。
* 结论直接否定 S3C2 的判据：`s2aFindAxis` 按坐标找 label/stub，48/48 的几何通过**不能**证明文字归属，
  现场截图已经把这一点证伪。本轮改为**先按对象归属建立配对，确认唯一之后才动图形**。

## 2 配对与计划（`scripts/sc1_s3c4_fix_labels.py`）

1. `cv~>terminals` → 真名 + 方向；`term~>pins~>figs` → pin 矩形；再用 `pinFig~>pin~>name` 证明该矩形属于这个端子。
2. 从 pin figure 的 children 取文字对象，读 `theLabel`（普通 label 实测可读；`text/strings/val/name` 皆 nil，
   `dbGetq` 不认这个属性）。
3. 只接受"一个 label 属于一个端子且文字 == 端子名"的配对；缺/重/不可解析就报问题并拒绝动图，**绝不改真端子名**。
4. 目标位置：文字框整体落在本体内、贴着自己 pin 的那条边；与其他文字（含 cell 名和 `[@instanceName]`）不得重叠。
   `[@instanceName]` 在 Symbol 视图是正常占位，不当错误处理。
5. 移动用 `dbMoveFig(lab cv list(list(dx dy) "R0" 1.0))` —— 相对移动，保留每个标签自己的 justification。
6. 短线判据（实测纠正过一次）：`device/drawing` 的线必须**本体边界 → 自己 pin 矩形的朝向边**，
   例如 vss 的 stub 是 `(0.0 -0.75)..(0.0 -0.625)`。早期版本拿 pin 中心比对，把 43/48 误判为"未验证"，
   那是判据错、不是数据错。

pass 1 计划：48 配对全部唯一，**43 个标签位置错**，10 条 stub 缺失 + 10 条留在旧位置的 stub（正好成对：
pin 换了边，线没跟着换）；`body_lines_kept=0`（没有一条本体装饰线被误判为可删）。
`sc1_s3c4_labels_before.csv` / `sc1_s3c4_label_plan.csv` / `sc1_s3c4_stub_actions.csv` / `sc1_s3c4_plan_report.txt`。

## 3 先在副本上做，再做其余

`--copies sc1_scan_power_1ch_s3c=s3c4_top_sym_copy`：`dbCopyCellView` 出副本，只在副本上删 2 条残留 stub、
补 2 条本体→pin 的 stub、移动 8 个标签并保存；`skill/sc1_s3c4_dump_copy.il` 复用同一个只读 dump 脚本
（`unless(boundp('sdCells) ...)`）回读，`scripts/sc1_s3c4_verify_labels.py` 判 **9/9 PASS**
（`sc1_s3c4_verify_copy.csv`）。副本最后已移出交付库到 `scratch_not_delivered_20261014_s3c4/`。

## 4 全库应用与两轮结果

| 步 | 结果 | 证据 |
|---|---|---|
| pass 1（8 个 Symbol，43 移动 + 10/10 stub） | 会话 rc=0、token 到；43 行 `S4-MOVE moved=db:0x…`，无 SKIP/OPENFAIL | `sc1_s3c4_log_apply_pass1.txt` |
| pass 1 后比较 | **拒收**：`sc1_ls_c1_r2d:vdd33` 与 `sc1_scan_gate:vdd` 距自己 pin 0.4688 —— 粗 stagger 把标签推进本体深处（`[@instanceName]` 横在中间） | `sc1_s3c4_log_dump_symbols_after.txt`（当时） |
| 判据修正 | 内缩改为按 0.00625 网格逐档扫描 + 允许沿边平移，并加"已在位就保持"的幂等判据 | `scripts/sc1_s3c4_fix_labels.py` |
| pass 2（仅 2 个标签，dy=+0.275） | rc=0，token 到 | `sc1_s3c4_log_apply_pass2.txt`、`sc1_s3c4_label_plan_pass2.csv` |
| **最终回读（独立会话重开，48 行导出）** | `S3C4_LABEL_VERIFY: PASS`：48/48 ADJACENT，最大间隙 0.225，文字框全部在本体内、互不重叠、不比其他 pin 更靠近外来 pin；48/48 有正确 stub，0 条残留；terminal 名/方向/pin 矩形与 BEFORE 逐项相等；cell 名与 `[@instanceName]` 原样保留 | `sc1_s3c4_labels_after.csv`、`sc1_s3c4_log_dump_symbols_after.txt` |

父原理图（叶→根）Check and Save：`sc1_ls_c1_top_r2d` errors=0 warnings=10、`sc1_r3_scan_chain_1ch` errors=0
warnings=8、顶层 `sc1_scan_power_1ch_s3c` errors=0 warnings=0，三个都 `saved=t`。**没有借这一步重布线**：
同一脚本在检查前/后各导出一份 instTerm-net + wire points + pin 文字，共 146 行逐字节相同；
18 条 warning 的集合与 S3C3 已提交证据中的 18 条完全一致（同文本、同坐标），说明本轮没有引入新的检查项。
之后用 S3C3 的原生回读+比较器复跑：两份 dump 都是 `pins=39 attached=39 ports=23 ports_on_wire=23 PROBLEMS 0`。

## 5 库状态与安全边界

备份 `backup_microled_scan_s3c_20261014_s3c4.tgz` sha256
`ac04f0a10b3537d87858b30497f36fbbcf9fe455776876d196de47dcb7dcbde5`（100 753 B），
逐文件清单 `sc1_s3c4_backup_inventory_before.csv`（72 行）。修后 `sc1_s3c4_backup_inventory_after.csv` 仍 72 文件、
库内 11 项、写锁 0；副本已移出。未动 VM 电源/快照/.vmx/网络/NAT/DHCP/ONBOOT/license/全局 SSH/显示服务；
未 GC/prune；objects 闸既存 BLOCK `blob:955497fb18ac…` 原样保留并与 staged/history 分开记录；
PDK/模型/基础库/`microled_cells`/`data_sink_1ch`/手工 C²MOS/共享 `cds.lib`/Spectre 母本/共享
reader-delay-vtx-preflight-supply-runner 均未写；旧证据与旧清单字节未改。凭据未回显、未入库。

## 6 截图闸的两处收紧（任务书指定的唯一工具改动）

`scripts/sc1_s3c3_shots_verify.py`：① checklist 必须恰好 6 个**唯一** cell/view，否则 `CHECKLIST_BAD` 直接 FAIL；
② `standard_deviation` 不可读或非有限值一律 `VARIANCE_UNREADABLE` FAIL，不再允许"UNVERIFIED_BLANK 之后仍打印
non-blank PASS"。四个负例实测（无图 / 5 行清单 / 重复 cell-view / 六个不同内容但无 convert 的 20 kB 文件）都是 rc=1，
见 `sc1_s3c3_shots_verify_selftest.txt`。**限制要说清**：这台 Windows 没有 ImageMagick `convert`，所以真正的六张图
必须在装有 ImageMagick 的机器（例如 guest）上判，否则永远 FAIL —— 这是收紧后的有意行为，不是图没问题。

## 7 人工待办（本轮不停在这之上）

修后只需四张 AFTER 图（任务书规定）：顶层 `sc1_scan_power_1ch_s3c:symbol`、顶层 `schematic`、
`sc1_r3_scan_chain_1ch:schematic`、`sc1_ls_c1_top_r2d:schematic`；DFF 晶体管图与 bank 图本轮未改，
可复用既有人工图并注明来源。截图仍由用户人工完成，Agent 不得再循环尝试自动捕获，也不得把现有 PNG 改名冒充 AFTER。
最终 VISUAL_REVIEW 由云端看图判定，本地状态写 **WAITING_REVIEWER**。

`FINAL_VSCAN` / LED I-V / `N_active` / 真实电极 RC 仍 NOT DEFINED，`SOA_SIGNOFF=NO`，自主掉电保护未实现；
本轮不新增功能回归或面板签核结论。
