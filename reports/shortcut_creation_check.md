# shortcut_creation_check.md — MicroLED 桌面快捷方式（沿用仓库已有实现）

时间：2026-10-11 20:39（guest `work-eda`，RHEL 6.5 GNOME/metacity，X display `:0`）
目标名称：`MicroLED IC Project`
约束遵守：**没有新设计启动流程、没有改任何已有脚本、没有改 EDA 环境、没有改 PDK、没有改 git 历史**。

---

## 1. 找到的已有快捷方式实现（先报告，再照做）

| 文件（仓库内路径） | 作用 | 当前使用方式 |
|---|---|---|
| `cadence_work/launch_virtuoso.sh` | **唯一的启动器本体**（"the one approved way to start a full Virtuoso GUI"）：`. skill/cad_env.sh` 只取 `/etc/env/virtuoso` 的 `export` 行、`cd $WORK`、校验 `virtuoso` 落在 `/opt/IC617/*`、`cds.lib` 存在、`DISPLAY` 从**唯一**在听的 X socket 推导（多于一个就拒绝猜）、可选应用主题，最后 `exec virtuoso -log $LOG` | 由 `.desktop` 的 `Exec` 调用；`LAUNCHER_CHECK=1` 只做自检不启动 |
| `results/evidence/sch1_desktop_entry.txt` | `.desktop` 条目**逐字副本**（因提交闸只收文本扩展名，故以 `.txt` 入库）；指明 live 文件应在 `/root/Desktop/Cadence-Virtuoso-MicroLED.desktop` | 作为创建 `.desktop` 的模板 |
| `scripts/gui2_verify_desktop.sh` | 桌面链**静态**验收（`DESKTOP_ENTRY: PASS`），关键设计：检查的是 `Exec` 指向的**那个文件**是否可执行，因为 `bash -n` 与 `LAUNCHER_CHECK` 曾在图标坏掉时照样通过 | `GUI2_DESKTOP=<路径>` 可指定入口（我用了它，因此无需改脚本） |
| `scripts/gui2_real_launch.sh` | **动态**验收：用 `gui2_envexec.sh` 以 `gnome-session` 自己的环境启动 `Exec` 目标，要求出现进程 **且** 出现 `IsViewable` + 带 `WM_STATE` 的 Virtuoso 窗口 | `bash scripts/gui2_real_launch.sh [program]` |
| `scripts/gui2_envexec.sh` | 从 `/proc/<gnome-session>/environ` 用 `xargs -0 + env` 原样搬运会话环境（不重新引用、不漂移） | 被上一个脚本内部调用 |
| `scripts/sch1_verify_launcher.sh`、`scripts/gui1_white_theme.sh`、`scripts/gui1_verify_theme.sh` | 启动器/主题的更早一代检查与主题应用-还原工具 | 本轮只用 `gui2_*`（更新的一代） |
| `cadence_work/appearance/{theme,active_resources,white/xresources.txt,backup/…}` | 主题机制的既有数据（启动器读 `active_resources` 决定是否 `xrdb -merge`） | 随启动器一起部署，未改内容 |
| `scripts/sync2guest.sh` | Windows→guest 同步并**传递可执行位**（历史事故：丢了 exec 位导致 `execv errno=13`、图标报 "There was an error launching the application."） | 本轮用 `git archive` + `tar` 等价传递，并用 `chmod 755` 固定 |
| `reports/lessons_learned/virtuoso_desktop_launch_failure.md` | 上述事故的完整复盘（755 判据、TryExec 预检、`os.access` 而非真 execv） | 作为本轮验收标准来源 |

结论：仓库**已经有**启动器与 `.desktop` 的完整实现，且 `.desktop` 的 `Exec` 必须指向那个已跟踪脚本。
所以本轮的正确动作是**部署已跟踪的启动器 + 按已跟踪模板生成 `.desktop`**，
而不是把命令抄进快捷方式（那正是任务书禁止的做法）。

## 2. 创建的文件

| 路径 | 内容 | 权限 |
|---|---|---|
| `/root/Desktop/MicroLED-IC-Project.desktop`（guest） | 见 §4，除 `Name=` 外与 `results/evidence/sch1_desktop_entry.txt` 逐字一致 | `755`（图标可启动所需） |
| `/root/microled_ai_project/cadence_work/launch_virtuoso.sh`（guest） | 从仓库 blob **原样** `git archive` 解出，未编辑；md5 `57be646893b671721bbea0326e3e7e06` 与仓库一致，mtime 保持仓库内时间 `Oct 9 19:51` | `755` |
| `/root/microled_ai_project/cadence_work/appearance/**`（guest） | 同上，仓库原样 | 文件 `644` |
| `results/evidence/scan_shortcut_desktop_and_verification.txt`（仓库） | 本次 `.desktop` 原文 + 静态/动态验收输出 | — |
| `reports/shortcut_creation_check.md`（仓库） | 本报告 | — |

`/root/Desktop/Cadence-Virtuoso-MicroLED.desktop`（旧名）**没有**被创建：本机 `Desktop` 下此前没有任何 `.desktop`（实测 `ls /root/Desktop/*.desktop` → No such file）。

## 3. 修改的文件

**仓库内已跟踪文件：0 个修改**（只新增 2 个）。
guest 侧被本机新写入的只有：上面 `Desktop` 的一个入口、部署的启动器与 appearance 数据、
以及验证留下的 `cadence_work/logs/xrdb_{thismachine_before,after_theme,restored}.txt`、
`virtuoso_gui_20261011_203954.log`。
**没有修改**：任何 `scripts/*.sh`、`skill/*.sh`、`launch_virtuoso.sh` 本体、`cds.lib`、
PDK、`display.drf`、模型卡、cell/schematic/testbench、`.vmx`、`ifcfg-*`。

## 4. 快捷方式目标命令

```ini
[Desktop Entry]
Type=Application
Version=1.0
Name=MicroLED IC Project
GenericName=Cadence Virtuoso
Comment=Micro LED IC617 session (teacher smic18mmrf PDK; work dir /root/microled_ai_project/cadence_work)
Exec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh
Icon=/opt/IC617/share/cdssetup/icons/32x32/app-virtuoso.png
TryExec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh
Terminal=false
Categories=Development;
```

只有 `Name` 按任务书从 `Cadence Virtuoso - MicroLED` 改为 `MicroLED IC Project`；
`Exec`/`TryExec`/`Icon`/`Categories` 与模板逐字相同（图标文件实测存在，4736 B，2015 年时间戳）。

**没有任何硬编码新路径**：`Exec` 指向仓库已跟踪的启动器；工作目录、`cds.lib`、环境变量
全部由该启动器自己解析：

```
PROJ=${QODER_PROJ:-/root/microled_ai_project}   WORK=$PROJ/cadence_work
CAD_ENV=$PROJ/skill/cad_env.sh   （只 harvest export 行；/etc/env/virtuoso 从不被执行）
CDS_LIB=$WORK/cds.lib            （唯一真源，与 GUI 共用同一份库映射）
```

## 5. 验证结果

### 5.1 静态：`GUI2_DESKTOP=/root/Desktop/MicroLED-IC-Project.desktop bash scripts/gui2_verify_desktop.sh`

```
CHECK EXEC_TARGET_EXECUTABLE   PASS   CHECK TRYEXEC_ACCESSIBLE      PASS
CHECK EXEC_WOULD_BE_EACCES     PASS   os.access(X_OK)=true -> execv would succeed
CHECK LAUNCHER_SYNTAX          PASS   CHECK LAUNCHER_LINEENDS       PASS  LF only
CHECK CADENCE_ENV_LOADED       PASS   CHECK PROJECT_WORKDIR_CORRECT PASS
CHECK CDS_LIB_FOUND            PASS   CHECK LAUNCHER_CHECK          PASS
CHECK WHITE_THEME_WIRED        PASS   CHECK WHITE_THEME_CONTENTS    PASS  sets Opus.editorBackground
DESKTOP_ENTRY: PASS      （.desktop 自身 mode=755、CR 计数 0）
VIRTUOSO_GUI: UNVERIFIED_BY_THIS_SCRIPT  -> 需下面的动态验收
```

### 5.2 动态：`bash scripts/gui2_real_launch.sh`（GNOME 会话环境，`gnome-session` pid 3032）

```
启动器自检：CHECK PROJECT_WORKDIR_CORRECT PASS / CHECK CDS_LIB_FOUND PASS
            virtuoso : /opt/IC617//tools/dfII/bin/virtuoso
            DISPLAY  : :0   XAUTHORITY: /var/run/gdm/auth-for-root-8x8Kba/database
            cds.lib  : 6 条 DEFINE 全部打印（含 smic18mmrf 与 microled_cells）
            theme applied via xrdb
            STARTING_VIRTUOSO
VIRTUOSO_PROCESS: PRESENT      AFTER_PIDS=[22288]
VIRTUOSO_WINDOW=0x2200020 (viewable after 3s)
  Map State: IsViewable   Width 795  Height 193
  WM_NAME = "Virtuoso® 6.1.7-64b - Log: .../virtuoso_gui_20261011_203954.log"
  WM_CLASS = "Qt-subapplication", "Virtuoso"      WM_STATE: Normal
license: Virtuoso Framework License (111) was checked out successfully. (0.05s)
REAL_LAUNCH: PASS (process + viewable window on the session display)
```

三项要求逐条对应：**工作目录正确**（`PROJECT_WORKDIR_CORRECT PASS`，`cds.lib` 即项目那份）；
**环境变量加载正常**（`CADENCE_ENV_LOADED PASS`，且 `virtuoso` 落在 `/opt/IC617` 树内）；
**命令执行正常**（真实进程 + 可见窗口 + license 检出）。
并且这次启动**走的就是 `.desktop` 的 `Exec` 目标本身**，不是另开一条 bash。

### 5.3 现场恢复（动态验证必然产生的副作用）

`gui2_real_launch.sh` 的设计是"只报告、不杀既有会话"，所以它会把我启动的会话留下。清理与还原：

```
kill 22288（含子进程）      -> remaining_virtuoso=0
自有 cdsMsgServer 孤儿      -> msgserver_left=0
xrdb 副作用：本机启动前 8 行 -> 应用主题后 10 行（+2 Opus 键）
  用我自己在合并前抓的 xrdb_thismachine_before.txt 执行 xrdb -load
  diff before vs restored -> 空，XRDB_RESTORED_IDENTICAL，Opus_keys_now=0
```

即主题对 X 会话资源的改动**已完整还原**（不是用仓库里那台旧机器的
`appearance/backup/xrdb_query_original.txt` 去"还原"——那会把本机资源写成别人机器的状态）。
桌面入口与启动器在清理后仍然完好（`ls -l` 复核）。

## 6. 用法

双击 GNOME 桌面上的 **MicroLED IC Project** 图标即可。
命令行等价（无桌面时）：

```bash
LAUNCHER_CHECK=1 /root/microled_ai_project/cadence_work/launch_virtuoso.sh   # 只自检
/root/microled_ai_project/cadence_work/launch_virtuoso.sh                     # 真启动
```

## 7. 已知未做

1. 没有同时创建旧名 `Cadence-Virtuoso-MicroLED.desktop`（本机此前不存在，也非任务要求）。
   若要两个图标并存，说一声即可。
2. `.desktop` 只有真机 `Desktop` 一份；仓库里仍以 `.txt` 证据形式入库（提交闸只收文本扩展名，
   这是仓库既有做法，不是我的新发明）。
3. 未做 Windows 侧快捷方式（任务书说的是进入 guest 项目环境；仓库里也没有 Windows `.lnk` 生成的
   已跟踪实现可参考）。若需要 Windows 端一键 `ssh -t` 进项目，属于新流程，需你另行批准。
4. 图标是否出现在 GNOME 桌面取决于 `nautilus-desktop` 刷新；本次验证以 `.desktop` 内容与
   可执行位、以及 `Exec` 目标的真实启动为准，未去截桌面缩略图。
