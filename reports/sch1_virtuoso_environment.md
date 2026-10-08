# SCH-1：Micro LED Virtuoso 工作环境 + C²MOS DFF 原理图

> **⚠️ 本轮的"参数等价"结论已被 SCH-2 更正（2026-10-08）。**
> `GOLDEN_NETLIST_EQUIVALENCE: PASS` 当年比的是属性里的**表达式名字**与**从黄金网表补来的默认值**，
> 没有比原理图自己的有效尺寸；GUI 里 18 只管子实际全部停在 PDK 默认 `180n/220n`，`l` 还是不可求值的
> 字符串 `ln`。环境、连通性、端口、功能回归各结论仍然成立（功能回归用的是黄金网表口径，故它证明的是
> 电路本身，不是原理图的参数）。现状与修复见 `reports/sch2_c2mos_parameter_fix.md`，
> 教训与永久闸门见 `reports/lessons_learned/spicein_cdf_parameter_mapping.md` + `AGENTS.md` 第 27 条。


日期：2026-10-08（guest 本地时间）。分支：`feature/c2mos-virtuoso-schematic`（未合并 `main`）。
本轮只做 A/B/C/D；E 列的禁止项一律未触碰。

---

## 0. 结论摘要

| 键 | 值 | 证据 |
|---|---|---|
| `DESKTOP_LAUNCHER` | PASS（文件存在、`Type=Application`、`Exec=` 指向 launcher） | `results/evidence/sch1_part_a_launcher.txt`（条目全文在 `results/evidence/sch1_desktop_entry.txt`；`.desktop` 扩展名不在仓库白名单里，所以以 `.txt` 存档，真实文件在 guest 桌面） |
| `LAUNCHER_PATH` | `/root/microled_ai_project/cadence_work/launch_virtuoso.sh`（`-rwxr-xr-x`） | 本轮 `ls -l` 输出 |
| `VIRTUOSO_GUI` | PASS（经 desktop 条目 `Exec=` 同一条命令行拉起过真实会话）；**双击本身我没能测** | 20:40 用户控制台上真实出现过 CIW 会话（随后由用户交互关闭）；`gnome-open` 路径 3 次尝试均 FAIL，详见 §1 |
| `EXISTING_SMIC18MMRF_PATH` | `/root/tech/smic_018mmrf-OA/…/SMIC_018_MMRF`，库名注册为 `umc18mmrf`，模型文件 `ms018_v1p7*` | `results/evidence/sch1_pdk_ident.txt` |
| `TEACHER_PDK_PATH` | `/root/microled_ai_project/pdk/smic18mmrf_teacher`，`ms018_enhanced_v1p2_rev0` | 同上 + `ls models/spectre/` |
| `SAME_PDK` | **NO** | 两个目录里实际的文件名不同（v1p7 vs enhanced_v1p2_rev0） |
| `TEACHER_PDK_OA_REGISTERED` | PASS | `cadence_work/cds.lib` 只 `DEFINE smic18mmrf <teacher>`；实例的 master 解析为 `smic18mmrf/n18:symbol`、`smic18mmrf/p18:symbol`（`results/evidence/sch1_db_dump_c2mos_dff_1bit.log`） |
| `DESIGN_LIBRARY` | `microled_cells`（在项目目录内，不在 PDK 内） | guest `cadence_work/microled_cells/` |
| `TECHNOLOGY_LIBRARY_ATTACHED` | **UNRESOLVED（见 §5.3）**：cellview 上 `techGetTechFile()` 返回 `objType="techFile"` 的对象，库目录出现 `tech.db`，但批量会话读不到该 tech 的名字，无法证明它就是老师的 techfile | `logs/sch1/last_tech_probe.log`（未跟踪，留在 Windows 侧） |
| `N18_P18_SYMBOL_CDF` | PASS（symbol 视图存在且被真实使用） | `n18/symbol/symbol.oa`、`p18/symbol/symbol.oa` 在盘上；实例 master 为 `...:symbol`；实例上读到 `model/l/simW` 属性 |
| `SCHEMATIC` | `microled_cells/c2mos_dff_1bit/schematic`（真实可编辑 OA 视图，`sch.oa` 35 KB 量级） | `results/evidence/sch1_asg_import_final.txt`（含 SPICEIN-33/54 与 import 参数表） |
| `MOS_COUNT` | **18**（9 n18 + 9 p18，从 DB 读回） | `results/sch1_connectivity_c2mos_dff_1bit.csv`、`results/evidence/sch1_db_dump_c2mos_dff_1bit.log` |
| `SCHEMATIC_CHECK_AND_SAVE` | PASS（`dbCheck()`→t、`dbSave()`→t，重新以只读打开后 72/72 引脚仍绑定到网络） | `results/evidence/sch1_readback_after_check_save.txt` |
| `GOLDEN_NETLIST_EQUIVALENCE` | **PASS，但只对当时所比的维度成立**（18/18 行的 model、l **表达式名**、w **表达式名**、D/G/S/B 网络一致；网络/端口集合一致）。有效尺寸未比 → 已被 SCH-2 判 `SCHEMATIC_DEVICE_PARAMETERS: FAIL` 并修好 | `scripts/sch1_netlist_from_db.py` 输出 + `results/sch1_connectivity_c2mos_dff_1bit.csv` |
| `SCHEMATIC_DFF_FUNCTION` | **PASS**（33/33 断言，testbench preflight PASS） | `results/sch1_ff1_from_schematic_asserts.txt`、`results/sch1_ff1_from_schematic_delays.txt` |
| `SCHEMATIC_SHIFT3_FUNCTION` | **PASS**（40/40 断言） | `results/sch1_shift3_from_schematic_asserts.txt`、`results/sch1_shift3_from_schematic_delays.txt` |
| `SCHEMATIC_NETLIST_VERIFICATION` | 通过，但**导出器是我写的 DB 读取器，不是 ADE netlister**（见 §5.2） | `spectre/generated/c2mos_dff_1bit_from_schematic.scs` |
| `REVIEW_BRANCH` | `feature/c2mos-virtuoso-schematic` | 本轮 commit |

一句话：环境可用，原理图是真的，电气内容与已验收 golden 逐行等价，并且从原理图重建出来的 netlist 在老师 PDK 上跑通了 1bit DFF 与 3 级移位的功能回归。**遗留项集中在端口方向、technology 身份和一个 ASG 注入物**，全部列在 §5。

---

## 1. Part A：桌面启动器

* `/root/Desktop/Cadence-Virtuoso-MicroLED.desktop`：`Type=Application`、`Name=Cadence Virtuoso - MicroLED`、
  `Exec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh`、`Icon=/opt/IC617/share/cdssetup/icons/32x32/app-virtuoso.png`、
  `Terminal=false`。`desktop-file-validate` 无 error。
* launcher 自己检查并打印 `CHECK CADENCE_ENV_LOADED / PROJECT_WORKDIR_CORRECT / CDS_LIB_FOUND`，
  环境变量只从 `/etc/env/virtuoso` 里 harvest `export` 行（见 `skill/cad_env.sh`），**从不执行该包装脚本**，也不改它。
* DISPLAY 只从"本机上唯一在听的 X socket"推导，多个则拒绝猜测；不硬编码。
* 只报告不干预已存在的 virtuoso 进程（`LAUNCHER_CHECK=1` 分支在 exec 之前退出）。
* **双击没有被我验证**：`gnome-open`（handler 路径）在 SSH 环境下不能激活桌面，3 次尝试都 FAIL，
  我按纪律停在证据上；真实 GUI 会话是经 launcher 的 `Exec=` 同一条命令在用户控制台上起来过的。
  所以 `VIRTUOSO_GUI` 的证据等级是"命令行 + 用户控制台真实会话"，不是"我按了两次鼠标"。

## 2. Part B：两套 PDK 与工作库

* 两个候选都是 `smic18mmrf` 名字，但内容不同版本：老的 `ms018_v1p7`（注册名 `umc18mmrf`），老师的
  `ms018_enhanced_v1p2_rev0`。课程电路一律建在老师版本上。
* `cadence_work/cds.lib` 保留 `cdsDefTechLib / basic / analogLib`，只 `DEFINE smic18mmrf <teacher OA 目录>`
  与 `DEFINE microled_cells ./microled_cells`；老 PDK 不出现在这个 cds.lib 里，因此同名只解析到老师版本。
  没有覆盖 `/root/tech`，没有改 PDK 任何文件。
* 老师库自带 `libInit.il / libInitCktPro.il / SMIC18MMRF_skillUtility`，在真实会话里加载成功；
  其 `batchSetCDF.ile` 第 13 行调用 `ciwMenuInit`，在无头会话里报 `undefined function`（不影响库加载与实例化，
  已记录：`logs/sch1/asg_spiceIn_20261008_214222.log` 一类日志里可见）。
* 设计库 `microled_cells` 由批量会话创建（在 `cadence_work/` 下，不在 PDK 内）。
### 2.1 项目级 cds.lib 全文（文件本身不进 Git：仓库的 .gitignore 一律排除 `cds.lib`，目的是不把任何库映射带进版本库；内容抄录在这里供评审）

```
# SCH-1 B2 -- project-level library map for the Micro LED Virtuoso session.
#
# Why this file exists instead of reusing the kit's own cds.lib: the teacher kit resolves
# `smic18mmrf` *relative to the kit directory*, so it only works when the session is started
# inside the kit. A session started from this work dir must resolve the same library name to
# an absolute path. The foundry library name is kept exactly as the kit defines it -- nothing
# here renames a vendor library, and nothing in the kit is modified.
#
# Only ONE definition of smic18mmrf exists in this session, and it is the teacher copy
# (/root/microled_ai_project/pdk/smic18mmrf_teacher: 2025 kit, docs V1.20_REV0, BSIM4 model
# cards ms018_enhanced_v1p2_rev0). The older /root/tech/smic_018mmrf-OA delivery is
# deliberately absent: measured, it registers its OA library under the name `umc18mmrf` and
# carries the 2007-era ms018_v1p7 (BSIM3v3) cards, so admitting it would put two different
# 0.18 um RF kits inside one session -- the exact failure this round must not repeat.

DEFINE cdsDefTechLib /opt/IC617/tools/dfII/etc/cdsDefTechLib
DEFINE basic         /opt/IC617/tools/dfII/etc/cdslib/basic
DEFINE analogLib     /opt/IC617/tools/dfII/etc/cdslib/artist/analogLib

# foundry: the teacher PDK, OA library directory as shipped
DEFINE smic18mmrf    /root/microled_ai_project/pdk/smic18mmrf_teacher/smic18mmrf

# ours: read-write design library created by scripts/sch1_mklib.il
DEFINE microled_cells ./microled_cells
```


## 3. Part C：原理图是怎么建出来的（以及为什么不是 schCreate）

**批量会话里没有原理图编辑器 API。** 实测（日志都留在 `logs/sch1/`，其中评审要看的部分已裁剪进 `results/evidence/`）：

* `schCreate` / `schCreateWire` / `schCheck` / `hiCheckAndSave`：`-nograph`、GUI、`-restore` 三种启动路径下
  `getd` 全部 nil；`load()` 直接吃 `etc/context/64bit/schematic.cxt` 返回 nil（`.cxt` 是编译过的 context，
  由应用注册，`schView.cxt` 会自动加载而 `schematic.cxt` 不会）。
* 本 build 的 SKILL reader 在解析期就拒绝 `~` 属性操作符（`x~y` → syntax error），`->` 与
  `dbGet(obj "attr")` 可用；`printf` 没有 `%v`/`%S`；`errset()` 返回的是**列表**，直接喂 `%s` 会中断整个 load；
  `t` 是受保护符号，不能当循环变量。
* 可用的是数据库层：`dbCreateNet / dbCreateInst / dbCreateInstTerm / dbCreatePin / dbCreateTerm /
  dbCreatePath / dbCreateLabel / dbCreateRect / dbCheck / dbSave / dbFindNetByName / dbFindTermByName /
  dbFindProp / techGetTechFile`。

**采用的路径**：Cadence 自己的 netlist→schematic 导入器 `spiceIn`（ASG），它按 netlist 建实例、网络、
引脚与布局，不需要任何人凭印象连线。参数文件用 Cadence 官方样例格式（`spiceInParams` 平面 SKILL 列表）。
`scripts/sch1_asg_import.sh` 的护栏：golden 只读、import 副本与 golden 逐行 diff、任何 MOS 实例行不一致就
拒绝运行、目标 cell 已存在就拒绝覆盖、`overwriteCells "NONE"`。

`BODYFORM=subckt_top` 是被测出来的唯一可用形状：

* `topCell` 默认是字面串 `"top"`，不改就会把 `subckt c2mos_dff (…)` 当实例行读，最后一个端口 `vss`
  被当成 master → SPICEIN-24。
* `topCell` 若等于文件里存在的 subckt 名 → SPICEIN-77（top cell 就是文件作用域）。
  所以老师电路以 **sub-circuit 形式**导入（那才是 18 只管子 + 6 个端口的单元本体），文件作用域补一个
  wrapper 实例 `I1 (d clk q qbar vdd vss) c2mos_dff_1bit` 给导入器一个 top；wrapper 落在
  `microled_cells/sch1_import_top`，是导入脚手架，不是课程电路。
* `conn2schArgs` 用 Cadence 样例里那一串（`-asg … +NOXTRSCH`）会产出"18 实例 + 13 网络 + 208 图元但
  **网络与引脚完全没有绑定**"的原理图；只有不传该参数、用工具默认参数，`dbCheck()` 才把 72 只引脚绑上去
  （对比证据：`results/evidence/sch1_readback_after_check_save.txt` 是默认参数版，72/72 绑定；
  旧参数版 `logs/sch1/last_readback.log` 里 POST-CON 全是 UNCONNECTED，未跟踪、留在 Windows 侧）。

import 副本相对 golden 只改了这些行（`results/evidence/sch1_import_copy_vs_golden.txt`，12 行）：cell 名、
`simulator` 行位置、`global 0`、3 行端口方向声明、wrapper 的 `parameters` + `I1` 行。18 行实例语句一字未动。

## 4. Part D：读回、检查、netlist 等价、回归

1. **读回**（`skill/sch1_readback.il`，输出裁剪进 `results/evidence/sch1_readback_after_check_save.txt`）：以 `"a"` 模式打开 → `dbCheck()`=t → `dbSave()`=t → 关闭 →
   再以 `"r"` 打开，逐实例打印 `inst / master(lib,cell,view) / model / D G S B 各自绑定的网络`。
   结果（`results/evidence/sch1_readback_after_check_save.txt`）：`instances=24`（18 MOS + 6 个 `basic/iopin` 端口符号）、`nets=13`、`shapes=219`，
   **72/72 引脚已绑定**，网络计数 vdd=16、vss=16、m=8、q=6、clk/clkb/mb/qbar=4、d/x1/x2/y1/y2=2。
2. **端口**：`dbFindTermByName()` + `net->pins` 都能读到 6 个端口（d clk q qbar vdd vss），每个 1 个 pin。
   批量会话里没有 `dbSetTermDirection`，方向最终都记成 `inputOutput`（见 §5.1）。
3. **尺寸**：DB 里实例属性是 `l="ln"`、`simW="wcp"`（keeper 是 `wk/wkp`），与 golden 的表达式逐只一致。
   **cellview 不保存设计变量的数值**（`dbFindProp(cv "ln")`→MISSING，`cv "desVars"`→nil），
   所以导出 netlist 的 5 个 `parameters ln=2e-7 …` 默认值取自 golden，并在文件头写明这一点；
   比较的是表达式名，数值只是解释性缺省。
4. **从原理图出 netlist**：`skill/sch1_dump_for_netlist.il` 把 DB 行打到 stdout（`printf(port …)` 在本
   build 被拒绝），`scripts/sch1_netlist_from_db.py` 只吃这些行，重建
   `spectre/generated/c2mos_dff_1bit_from_schematic.scs` + `results/sch1_connectivity_c2mos_dff_1bit.csv`，
   并逐行比对 golden：`GOLDEN_NETLIST_EQUIVALENCE: PASS`（18/18，网络集合与端口集合一致）。
5. **回归**：两个 testbench 与已验收版本逐行相同，只换 cell 来源与 subckt 名
   （`spectre/c2mos_ff1_from_schematic.scs`、`spectre/c2mos_shift3_from_schematic.scs`），
   判据表由 `scripts/c2mos_check.sh` 的新 case `ff1_sch / shift3_sch` 复用同一份，未放宽：
   * DFF：`TESTBENCH_PREFLIGHT: PASS`（vdd=1.8、vss 独立源钉在 0），33 条断言 0 失败，
     `SCHEMATIC_DFF_FUNCTION: PASS`；clk→Q 50% 交点在 0.09 %–0.21 % T。
   * 3 级链：40 条断言 0 失败，`SCHEMATIC_SHIFT3_FUNCTION: PASS`；三级 clk→Q 延迟
     4.215e-10 / 4.329e-10 / 3.957e-10 s。
   * 时钟仍是 200 ns 压力节拍（与 golden 判据同源）；帧尺度 9.765625 µs 本轮没有重跑。

## 5. 已知偏差与未完成（都按证据写）

1. **端口方向**：6 个端口在 OA 里都记成 `inputOutput`。我按 spec 在 import netlist 里声明了
   `d clk input` / `q qbar output` / `vdd vss inputOutput`，但 ASG 只生成"引脚"这一种对象，
   批量侧又没有 `dbSetTermDirection`，方向没被区分。功能回归不受影响（Spectre 的 subckt 端口是位置的）。
2. **导出器不是 Cadence 的 netlister**：ADE-L 的 `asiNetlist`/`asiRawNetlist` 在 `-restore` 路径下确实
   存在（`skill/sch1_nl_probe.il`），但它们需要一个 session 对象（`asiCreateSession`），本机文档只给
   `asiNetlist(o_session)`，没有可无头构造会话的公开入口；`nlNetlist/nlCreateDesign/nlCreateFormatter`
   在本机文档里没有签名。所以 §4.4 走的是"从 DB 读行重建"。若评审要求必须是 ADE 的 netlist 产物，
   这一项应判 `SCHEMATIC_NETLIST_VERIFICATION: BLOCKED`；我这边给出的证据是 DB 行本身（`results/evidence/sch1_db_dump_c2mos_dff_1bit.log`）
   与由这些行重建的 netlist 同时可读，且回归判据未放宽。
3. **technology 身份**：`microled_cells` 有 `tech.db`，cellview 上 `techGetTechFile()` 返回 techFile 对象，
   但批量会话读不到它的 lib/cell/name（都是 nil），cds.lib 里我用的是 `cdsDefTechLib`。
   因此只写 UNRESOLVED，不声称"已挂老师 techfile"。本轮不做 layout/DRC/LVS，所以不阻塞。
4. **ASG 注入物**：早期 `flat` 形状下 ASG 会按默认 `masterCellForGnd "gnd"` 注入一个 `basic/iopin`（PIN0）
   并新建网络 `gnd!`；`dbDeleteInst` 在本 build 不可用（getd nil），删不掉。
   现在改成 `subckt_top` 形状后，生成的单元是干净的 13 网络 + 6 端口，没有 `gnd!`；
   但早期实验遗留的 cell 目录 `microled_cells/c2mos_dff_1bit`（flat 版）已被我替换：删除的是我自己本轮
   生成的三次失败产物（`c2mos_dff_1bit` flat 版、`sch1_bind_a`、`zz1_dff`、`zz1_top`），日志留存在
   `logs/sch1/`。库里现存 `c2mos_dff_1bit`（评审对象）与 `sch1_import_top`（导入脚手架）。
5. **双击**：见 §1，我没有谎称测过。
6. **没有做的**：symbol 视图（spec 明确禁止本轮创建）、layout/DRC/LVS/PEX、384 通道、TCON、
   reset/blanking/level shifter、扫描输出级、Data Driver 改动。

## 6. Git 与产物

* 本轮新增/改动（只含我们自己的 SKILL、脚本、日志、报告，无 PDK、无 vendor OA 库、无模型卡、无 techfile、
  无凭据）：
  `cadence_work/{launch_virtuoso.sh,cds.lib,desktop/*.desktop}`、`skill/sch1_*.il`（读回/导出/探针）、
  `scripts/sch1_{asg_import.sh,gen_ports.py,netlist_from_db.py,pdk_ident.sh,env_probe.sh,gui_test.sh,verify_launcher.sh,sch_virtuoso.sh}`、
  `skill/sch1_*.il`、`spectre/c2mos_{ff1,shift3}_from_schematic.scs`、
  `spectre/generated/c2mos_dff_1bit_from_schematic.scs`、
  `results/sch1_connectivity_c2mos_dff_1bit.csv`、
  `results/sch1_*.txt`、`results/evidence/sch1_*`、本报告。
* `scripts/c2mos_check.sh` 只加了两个 case（同一份判据表），没有改原 `ff1/shift3` 行为。
* 分支 `feature/c2mos-virtuoso-schematic`，不合并 `main`。

## 7. 停在这里

`NEXT: USER_SCHEMATIC_VISUAL_REVIEW` —
请在桌面会话里（双击 `Cadence Virtuoso - MicroLED`，或命令行跑
`/root/microled_ai_project/cadence_work/launch_virtuoso.sh`）打开
`microled_cells / c2mos_dff_1bit / schematic`，看三件事：

1. 布局是否可读（时钟反相器在左、master/slave 时钟栈居中、keeper 与输出在右，PMOS 在上、NMOS 在下，VDD 顶、VSS 底）；
   如果需要更规整的摆放，我按你的指示重排，不改电气。
2. 6 个端口是否显示为你要的形态（当前都是 `inputOutput`，§5.1）。
3. `sch1_import_top` 这个 wrapper 你要保留、改名还是让我在下一轮删掉。

**STOP**：不进入扫描输出级，不做 symbol，不做 layout，不做下一模块，等你看过原理图。
