---
name: scan-driver-s3c3
audit_start: 7a1fc43db9b9d7a17c5accdac2296196cb0bf709
branch: poc/scan-driver-1ch
new_simulation_runs: 0
s4: NOT_STARTED
soa_signoff: NO
---

# SCAN-1 S3-C3 —— 两个父原理图按实际接线修好，GUI 目视交付未完成

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
| VISUAL_REVIEW | **PENDING —— 0 张截图交付**。两次正确形式的 GUI 启动都跑到，但没有任何视图窗口出现；具体错误见 §5 | `sc1_s3c3_log_gui_session2_cdslog.txt`、`..._stdout.txt`、`..._windows_seen.txt` |

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

## 5 GUI 与截图：两次正确启动都没出图，交付的是错误本身

`scripts/s3c3_gui_shot.sh`：隔离 `cds.lib` 与 `HOME`（工程内 `s3c_oa/home`），
`DISPLAY`/`XAUTHORITY` 从 `/proc/<gnome-session>/environ` 读；启动的是
`/opt/IC617/tools/dfII/bin/virtuoso -log …`（确认过 `type -a virtuoso` 不是 `/etc/env` 的包装脚本）；
初始化文件只 `load(sc1_s3c3_gui_open.il)`，**不写 exit()**；抓图完全在 shell 侧用
`xwininfo` 找窗口 + `import -window` 落 PNG，绝不在 SKILL 里同步抓。

两次运行的事实（`sc1_s3c3_log_gui_session2_*`、`sc1_s3c3_log_gui_windows_seen.txt`）：

* 会话进程活着（`SESSION_ALIVE_BEFORE_KILL=1`），但 `GW-BEGIN/GW-END-OF-OPENS` 一次都没出现，
  `.cdsinit` 的 `load` 没有执行到；stdout 只有一行
  `Display :0 Error "BadAtom (invalid Atom parameter)" request 20 error 5 serial 233`
  （GUI-2 已记：成功会话也会有这条，不能当根因）；
* 轮询到的窗口树里只有 `Library Manager`、`Library Select`、`opus`（0x3a0000c，S3C1 那次的残留）
  与桌面组件，**没有任何视图窗口**；`SCREENSHOTS=0 non-empty=0`。
* 结论：根因是 GUI 会话没能走到 init 脚本执行阶段（停在启动对话框阶段），不是 API 不存在。
  §4 的两次机会用完，按任务书交最短 CIW 路线：把 `skill/sc1_s3c3_gui_open.il` 贴进 CIW 执行
  （或逐条 `geOpen(?lib "microled_scan_s3c" ?cell "sc1_scan_power_1ch_s3c" ?view "schematic" ?mode "r")`，
  目标清单在 `skill/s3c3_targets.txt`），窗口出来后 `import -window <id> shot.png` 即可，
  抓图索引留了 `sc1_s3c3_gui_capture_index.csv` 表头给这一步填。

## 6 边界复述

未做也未被暗示：S4、任何 Spectre/preflight/工作点探针（`NEW_SIMULATION_RUNS=0`）、面板/亮度/功耗结论、
`FINAL_VSCAN`、LED I-V、`N_active`、真实电极 RC（仍 `NOT DEFINED`）、`SOA_SIGNOFF=NO`、
`AUTONOMOUS_POWER_FAIL` 未实现。共享 runner/reader/delay/vtx/preflight/supply 一字未动；
PDK/模型/基础库/`microled_cells`/`data_sink_1ch`/手工 C²MOS/共享 `cds.lib`/Spectre 母本只读；
旧 S3C1/S3C2/S3-B 证据 CSV 与两份旧清单字节未改；未 GC/prune，`955497fb18ac…` 那条 objects 闸
BLOCK 原样保留并与 staged/history 分开记录；未动 VM 电源/快照/.vmx/网络/NAT/DHCP/ONBOOT/license/
全局 SSH/显示服务；未删任何写锁（本来就为 0）；凭据未回显、未入库。
