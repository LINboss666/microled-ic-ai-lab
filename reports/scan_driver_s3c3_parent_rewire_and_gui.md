---
name: scan-driver-s3c3
audit_start: 7a1fc43db9b9d7a17c5accdac2296196cb0bf709
branch: poc/scan-driver-1ch
new_simulation_runs: 0
s4: NOT_STARTED
soa_signoff: NO
---

# SCAN-1 S3-C3 —— 两个父原理图按实际接线修好，GUI 已正确启动、截图转人工

任务书 `MicroLED_Qoder_SCAN-1S3C3_7a1fc43_reconnect_parents.md`。本轮只改
`microled_scan_s3c` 里的 `sc1_ls_c1_top_r2d:schematic` 与 `sc1_r3_scan_chain_1ch:schematic`，
顶层 `sc1_scan_power_1ch_s3c:schematic` 只在最后做一次 Check and Save；八个 Symbol、golden 的 39 条 MOS 记录（模型/尺寸/端点）、
五个叶原理图一字未动。

## 0 状态（§7 要求的分项，一条不代表另一条）

| 维度 | 状态 | 出处 |
|---|---|---|
| OBJECT_GRAPH_MATCH | **PASS** —— 28 个子实例 pin 的 net 与 `golden_subinst.csv` 逐条一致（顶层 11 条另计） | `sc1_s3c3_log_reopen_dump_39pins.txt`、`sc1_s3c3_attach.csv` |
| GEOMETRIC_ATTACHMENT | **PASS 39/39** —— 引脚点＝symbol pin 矩形经 `dbTransformPoint(centre, inst~>transform)` 的绝对点，落在同 net 真实 segment 上 | `sc1_s3c3_attach.csv`，`scripts/sc1_s3c3_verify.py` |
| EXTERNAL_PORT_ATTACHMENT | **PASS 23/23** —— 每个外部 port 都有同 net 线段进入其 pin 框 | 同上 |
| POST_CHECK_SAVE_GRAPH_MATCH | **PASS** —— 每个视图都是「schCheck 现场提取 → 打印 instTerm/net → dbSave → 独立会话按磁盘字节重开 → 复算」；顶层 Check and Save 后 errors=0 warnings=0 | `sc1_s3c3_log_apply_ls_direct.txt`、`..._chain_direct.txt`、`..._top_check_and_save.txt`、`..._reopen_dump_39pins.txt` |
| PORT_DIRECTIONS | **96/96 未变**（本轮不碰 Symbol/端口方向；`sc1_s3c3_dump_pins.txt` 里每个 instTerm 的 dir 与 S3C2 记录一致） | `sc1_s3c3_dump_pins.txt` |
| SYMBOL_PLACEMENT | **48/48 保持**（Symbol 视图本轮只读；实例/端口移动只发生在两张父原理图内） | `sc1_s3c3_dump_pins.txt`（DP-SYM 段）、S3C2 报告 §3 |
| VISUAL_REVIEW | **REVIEWED —— 六张人工原生图 + mp5 局部图已交云端，结论 REVIEWED_FAIL_SYMBOL_LABELS**（显示错误是 Symbol 名称标签位置/归属，修复在 S3C4 报告）。GUI 会话本身已正确启动：六个视图窗口都是真实 X 窗口（`IsViewable`，600x450，六个互不重叠栅格位，`slots_confirmed=6/6`），但这台显示系统取不到可信像素（顶层窗口 134 字节空图，最大子窗口 `IsUnMapped`），故截图永久转人工，自动像素工具已删 | `sc1_s3c3_gui_manual_checklist.csv`、`sc1_s3c3_shots_verify.txt`（本地仍 6 MISSING，与云端已收图不矛盾：图在用户侧）、`sc1_s3c3_log_gui_manual_session.txt`、`sc1_s3c3_gui_window_tree_manual.txt`、`sc1_s3c3_gui_capture_attempts.txt`、S3C4 报告 §0/§1 |

`S3-C 整体 = REWORK 未完`：目视审核仍未关闭，所以不写 COMPLETE/ACCEPTED；未进 S4，`NEW_SIMULATION_RUNS=0`。

## 1 开工前置

本地=远端=`7a1fc43`；工作树只有未跟踪的 `results/evidence/_incoming/`。目标库 72 文件、848 KiB、
**写锁 0**、`virtuoso` 进程 0。整库备份
`$PROJ/cadence_work/s3c_oa/backup_microled_scan_s3c_20261014_s3c3.tgz`，
sha256 `ad074081a4e088573522ef111cc2fff757ec381ebedf99c705b8018f3acce2ed`（97,779 B），
逐文件 sha256+bytes 清单 `sc1_s3c3_backup_inventory.csv`（72 行）。本轮结束时两个临时副本 view
已移出目标库到 `scratch_not_delivered_20261014_s3c3/`，库内仍 11 项。

## 2 §4 要求的三个接口，实测结果（其中两条撤回旧结论）

| 调用 | 本机结果 |
|---|---|
| `lab~>theLabel` / `dbGet(lab 'theLabel)` | **都返回 net 名字**（`("en")`、`("d")`…）。S3C2 说“label 对象读不出文本”只测了 `~>text/~>strings/~>val/~>label/~>name`，**该断言撤回** |
| `dbGetq(lab 'theLabel)` | 返回 nil —— 这个拼法在本 build 不认，`dbGet` 才认 |
| `schCreateWireLabel` / `schCreateLabel` | **NIL**：`getd` 在 nograph 会话启动时和打开视图之后都是 nil；连“参数写错的 `dbCreateRect`”也拉不出 schematic 包（`S3-API ... schCheck=NIL`）。真正让它出现的是**一次成功的 `dbCreateLine`**：那之后 `schCheck=EXISTS`（`hiCheckAndSave` 仍 NIL）。`schCreateWireLabel` 未出现，因此没有猜它的调用形式 |
| `dbTransformPoint(pt, i~>transform)` | **EXISTS 且给出绝对点**，与 RAW 角点+origin 一致；本轮几何一律走它 |
| `cv~>insts` / `cv~>wireFigures` | 恒空 —— 有数据的是 `cv~>instances` 与 `cv~>shapes` 里 `layerName=="wire"` 的 `objType "line"`。上一轮“父图 0 根导线”就是这么来的误读，也是 S3C1 说 `cv->terms` 那类坑的同一种 |
| `i~>terminals` / `it~>figure` | 前者恒空，子实例端子要读 `i~>instTerms`；`it~>figure/figs/pinFig` 都是 nil ⇒ 引脚矩形只能从 master symbol 的 `tm~>pins~>figs` 拿（本轮照此实现） |

## 3 接线怎么做完的（不使用 928 行路由器）

`scripts/sc1_s3c3_plan.py` 从 `sc1_s3c3_dump_pins.txt` 读入绝对 pin 矩形（不手抄坐标），
按 §4 的固定摆放给出实例原点与端口位置，然后逐段生成导线/短 stub，并对**每条**候选做三类拒绝检查：
穿过别的实例本体、碰到别的 net 的 pin 框、与已放置的其它 net 几何接触。结果
`S3C3_PLAN rows=32 problems=0`（LS 14 段：3 直连 + 11 stub；chain 18 段：7 直连 + 11 stub）。
`scripts/sc1_s3c3_emit.py` 把这套表插进手写模板 `skill/sc1_s3c3_apply_tpl.il`（一个自包含文件，
没有嵌套 `load`），运行顺序严格是：
摆放实例/端口 → 画线（**只用几何，不再 `fig~>net =` 手填**）→ 每条线段放同名 wire label →
**之后**才删除旧几何（先画后删，否则最后一条图元被删时数据库会改名该 net）。

两条实测出来的硬规则（各花掉一次运行）：

1. 只靠几何相接、线段不带名字 label 时，schCheck 仍把两端 pin 报成 floating，线自己落到
   `netNN` —— 也就是说这个 build 里 **label 才是命名的来源**，所以每条线段都带自己的名字 label
   （端口侧也一样：端口的 terminal 名字不会传到接上去的线上）。
2. 旧图必须删。spiceIn 生成的导线 `objType` 是 `"line"`、layer `wire`，上一轮按 `objType=="wire"`
   统计成 0，于是新旧几何混在一起，schCheck 报 `Net "en" shorted to net "core_ok33"`（2 errors）。
   删掉旧几何+旧 label 后 errors=0。

## 4 §5 的闭环证据

临时副本 `s3c3_ls_copy` / `s3c3_chain_copy`（用 `dbCopyCellView`，跑完已移出库）：
`S3-CHECK errors=0 warnings=10 / errors=0 warnings=8`，`S3-VERDICT PASS saved=t`，
独立会话重开后 `S3C3_VERIFY views=s3c3_ls_copy,s3c3_chain_copy pins=28 attached=28 PROBLEMS 0`。
之后才按同一脚本的 `--direct` 形式落到交付视图：
`sc1_ls_c1_top_r2d` drawn 14/14、labelled 14/14、moved 8/8、errors=0 warnings=10、saved；
`sc1_r3_scan_chain_1ch` drawn 18/18、labelled 18/18、moved 11/11、errors=0 warnings=8、saved。
顶层只做 Check and Save：`errors=0 warnings=0 saved=t`（SCH-2162 随两条子图重存而消失）。
最后一次独立重开会话（`sc1_s3c3_log_reopen_dump_39pins.txt`）复算得
**pins=39/39、ports=23/23、无跨 net 接触、绑定=golden** —— `S3C3_VERIFY: PASS`。

### 归因更正（§7 点名要求）

S3C2 说两个父视图的告警“主要是 SCH-2162”，错。当时磁盘字节的 schCheck 实列
`sc1_ls_c1_top_r2d` 13 个 floating pin + 9 个 floating net、`sc1_r3_scan_chain_1ch` 25 + 14
（`sc1_s3c2_log_final_verify_disk_reopen.txt` 可查），SCH-2162 只是其中一类。
本轮修完后的 warning 分类（每次 schCheck 的完整计数都印在日志里）：

| 视图 | errors | warnings | 剩余 floating |
|---|---|---|---|
| `sc1_ls_c1_top_r2d` | 0 | 10 | 仅 `Xcore.x`（§3 允许的单端点 net） |
| `sc1_r3_scan_chain_1ch` | 0 | 8 | 仅 `Xff.q`（同上） |
| `sc1_scan_power_1ch_s3c` | 0 | 0 | 无 |
| 八个叶 symbol 视图 | schCheck 返回 nil，**不计 PASS** | — | — |

`0 error` 不再被当作必要接线有效的证明：有效性由 §0 的三项（逐 pin net 比对、几何吸附、post-check-save
重开复算）与上面这张表共同支撑。

## 5 GUI 与截图：会话已正确启动并把六个窗口放上屏幕，像素抓取失败，截图永久转人工

启动方式（`scripts/s3c3_gui_manual_session.sh`，前身 `scripts/s3c3_gui_shot.sh`）：隔离 `cds.lib` 与
`HOME`（工程内 `s3c_oa/home`），`DISPLAY`/`XAUTHORITY` 从 `/proc/<gnome-session>/environ` 读；
启动的是 `/opt/IC617/tools/dfII/bin/virtuoso -log …`（`type -a virtuoso` 确认不是 `/etc/env` 包装脚本）；
`$HOME/.cdsinit` 只 `load(sc1_s3c3_gui_open.il)`，**不写 exit()**；该入口不自己开窗口，而是
`hiEnqueueCmd` 把 `sc1_s3c3_gui_body.il` 排进事件循环——§6 要求的正是这个形状。

六次会话，一次比一次更远，每步都留了原始日志：

| 会话 | 结果 | 具体证据 |
|---|---|---|
| 1 | `OPENS_SEEN no` —— 我的 SKILL 用了 `foreach(t …)`，`t` 是受保护符号 | `sc1_s3c3_log_gui_session2_cdslog.txt`（这是调用方缺陷，不是显示系统） |
| 2 | 直接在 `.cdsinit` 里开：`geOpen` 返回 `window:2..7`，但 X 里没有任何视图窗口；日志根因 `*Error* eval: unbound variable - ciwHelpMenuSpec`，来自 `/opt/IC617/tools.lnx86/dfII/etc/tools/menus/schView.menus` line 342（厂商文件越界，不改） | 同上 |
| 3 | `hiEnqueueCmd` 延后 → **菜单错误消失，六个真实编辑器窗口出现在 X 里**（`("Qt-subapplication" "Virtuoso") 900x690`，各带 20 个子窗口）。但六个都落在同一像素 `+122+274`，且**没有 WM_NAME**，所以按标题 `"<cell> <view>"` 匹配抓不到 → `SCREENSHOTS=0`。`hiResizeWindow(w list(20 20 900 660))` 每次打印 `*WARNING* Invalid bounding box` 并返回 nil | `sc1_s3c3_log_gui_session3_enqueue.txt` |
| 4 | `hiResizeWindow` 换成两点形式 `list(list(llx lly) list(urx ury))` → **`resize=t`**，六个窗口落在六个互不重叠的 600x450 栅格位；`GW-SHOT` 握手 6/6 打出。抓图脚本在会话起来之前就枚举了一次窗口 → 0 张 | `sc1_s3c3_log_gui_session4_grid.txt`、`sc1_s3c3_gui_capture_attempts.txt` |
| 5 | 每个 marker 重新枚举 → **身份确认 `slots_confirmed=6/6`**（窗口确实坐在 SKILL 要求的栅格位上）。但 `import -window <顶层id>` 每张都是 134 字节的均匀图：Qt 顶层只是容器。`_NET_CLIENT_LIST_STACKING` 六次 raise 全部不变 → “抓最顶层”不能用来认 cell | `sc1_s3c3_log_gui_session5_topwindow.txt`、`sc1_s3c3_gui_capture_index.csv` |
| 6 | 改成向子窗口递归取最大者 → 选中的是**未映射**的 640x480 helper：`state=IsUnMapped`、`import: unable to read X window image '0x…': Resource …`、0 字节 | `sc1_s3c3_log_gui_session6_canvas.txt` |
| 人工 | 放弃自动像素，会话启动后**不 kill、留在屏幕上**：`READY_FOR_MANUAL_CAPTURE=yes`、六个窗口 id/几何写入 `sc1_s3c3_gui_manual_checklist.csv` | `sc1_s3c3_log_gui_manual_session.txt`、`sc1_s3c3_gui_window_tree_manual.txt` |

因此本轮 §6 的交付物换成任务书允许的另外两件：具体错误（上表）＋最短 CIW 打开脚本
`skill/sc1_s3c3_gui_body.il`（六个 `geOpen(?lib "microled_scan_s3c" ?cell … ?view … ?mode "r")`
+ 各自独立栅格位，`NEW_SIMULATION_RUNS=0`，全部只读）。`scripts/s3c3_gui_shot.sh` 与
`scripts/s3c3_gui_capture.py` 已删除，不留下一个已知取不到可信像素的工具冒充截图管线。

人工截图怎么做（会话仍在跑，pid 由启动器的 `SESSION_LEFT_RUNNING pid=…` 行给出，`kill <pid>` 即关）：
按 `sc1_s3c3_gui_manual_checklist.csv` 的六行点窗口，用 gnome-screenshot / PrintScreen 各截一张，
存为 `results/evidence/sc1_s3c3_shot_<cell>_<view>.png`（六张：顶层 schematic+symbol、DFF、bank、
两张修复父图），把 `map_state` 列的 `TODO_MANUAL` 填成实际状态。入库判定不靠人记：
`python scripts/sc1_s3c3_shots_verify.py` 从同一份清单读期望文件名，六张必须存在、≥20 000 字节、
SHA-256 互不相同、且 `standard_deviation>0`（空白图会被判 BLANK），通过才允许把 VISUAL_REVIEW 写成
已交付；本轮收尾时它的输出是 6 个 MISSING（`sc1_s3c3_shots_verify.txt`，即已知失败态）。
清单文件名与窗口身份的绑定来自启动器，不手抄，所以截错窗口会被判 MISSING 而不是被当成通过。

**后续事实（S3C4 任务书带来）**：这六张图与 mp5 局部图已由用户人工截好并提交云端审核，
`SCREENSHOTS_RECEIVED_BY_REVIEWER=YES`，审核结论 `REVIEWED_FAIL_SYMBOL_LABELS` —— 失败点不是接线，
而是 Symbol 的名称标签没跟着 pin 走。因此上面那段"把 PNG 放进 results/evidence"的入库路径不再是本轮的
完成条件：图在用户/云端侧，本地工程仍报 MISSING，两者不矛盾。修复与复验见
`reports/scan_driver_s3c4_symbol_labels.md`。

## 6 边界复述

未做也未被暗示：S4、任何 Spectre/preflight/工作点探针（`NEW_SIMULATION_RUNS=0`）、面板/亮度/功耗结论、
`FINAL_VSCAN`、LED I-V、`N_active`、真实电极 RC（仍 `NOT DEFINED`）、`SOA_SIGNOFF=NO`、
`AUTONOMOUS_POWER_FAIL` 未实现。共享 runner/reader/delay/vtx/preflight/supply 一字未动；
PDK/模型/基础库/`microled_cells`/`data_sink_1ch`/手工 C²MOS/共享 `cds.lib`/Spectre 母本只读；
旧 S3C1/S3C2/S3-B 证据 CSV 与两份旧清单字节未改；未 GC/prune，`955497fb18ac…` 那条 objects 闸
BLOCK 原样保留并与 staged/history 分开记录；未动 VM 电源/快照/.vmx/网络/NAT/DHCP/ONBOOT/license/
全局 SSH/显示服务；未删任何写锁（本来就为 0）；凭据未回显、未入库。
