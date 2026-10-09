# GUI-1：把 Micro LED 的 Virtuoso 原理图背景设为白色（可恢复、随桌面快捷方式自动生效）

结论先说：**白色背景已经配置好并会在下次双击 `Cadence Virtuoso - MicroLED` 时自动生效**，
机制是这台机器唯一可用且有据可查的那一个（X 资源 `Opus.editorBackground`，经 `xrdb` 合并）。
**最终"看起来对不对"仍要你看一眼**——这台虚拟机上取不到可信的屏幕像素（下面第 5 节给了实测证据），
所以本轮不声称已在 GUI 里确认。

```
TASK:                       GUI-1 VIRTUOSO WHITE BACKGROUND
CURRENT_BACKGROUND:         black（IC617 内置默认；本机不存在任何覆盖它的配置）
BACKGROUND_CONFIG_SOURCE:   X 资源 Opus.editorBackground；~/.Xresources、~/.Xdefaults、
                            ~/.cdsinit、site .cdsinit、会话 RESOURCE_MANAGER 全都没有 Opus 项
CURRENT_DISPLAY_DRF:        /root/microled_ai_project/pdk/smic18mmrf_teacher/smic18mmrf/display.drf
                            （由 PDK 自己的 libInit 加载；本轮未改、未复制其内容）
CURRENT_LAUNCHER:           /root/Desktop/Cadence-Virtuoso-MicroLED.desktop
                            Exec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh
                            → 检查通过后 exec virtuoso -log <会话日志>
WHITE_BACKGROUND_CONFIG:    PASS
CONFIG_METHOD:              xrdb -merge cadence_work/appearance/white/xresources.txt
                            （Opus.editorBackground #ffffff + Opus.dragColor #000000）
DESKTOP_LAUNCHER:           PASS（LAUNCHER_CHECK: PASS，三条旧检查仍在原位且通过）
AUTO_LOAD_ON_NEXT_START:    YES
RESTORE_ORIGINAL_THEME:     READY（bash scripts/gui1_white_theme.sh restore）
GUI_VISUAL_VERIFICATION:    PENDING_USER_REVIEW
DISPLAY_DRF:                NOT_MODIFIED
SAFETY:                     未改任何电路/库/PDK/许可证/软件版本（第 6 节）
```

## 1. 调查：背景颜色到底由谁决定（§2，只读）

| 项 | 实测 |
|---|---|
| 版本 | `virtuoso version 6.1.7-64b 11/09/2015`，sub-version `IC6.1.7-64b.78`（`cadence_work/appearance/backup/version_before.txt`） |
| User Preferences 是否支持该字段 | **不支持**。`/opt/IC617/tools/dfII` 整棵树里找不到字符串 `Editor Background Color`；因此 §3 说的"优先用 CIW Options → User Preferences"这条路在这台机器上不存在（查过才下结论，没有照抄新版本的说明） |
| X 资源名 | `strings` 读本机 `virtuoso` 二进制：`editorBackground`、`dragColor`、`selectionColor`、`buttonColor` 各命中 1 次 → 这些是它真会去查的名字 |
| 本机自带文档 | `doc/dfIIconfig/dfIIconfigStartup.html`：`Opus.editorBackground` = "Color of design window background"；`Opus.dragColor` = "the selection box you draw around objects; the zoom box …; the outlines of objects you move, copy, or reshape; and the outlines of edges you stretch" |
| 出厂默认值 | Cadence 自带样例资源文件 `tools/dfII/cdsuser/.Xdefaults`（只读）：`!Opus.editorBackground: #000000` → 默认黑 |
| 现有用户配置 | `/root` 下没有 `.Xresources`/`.Xdefaults`/`.cdsinit`/`.cdsenv`/`.cadence`；`:0` 会话数据库只有 8 行 GNOME 项（`appearance/backup/xrdb_query_original.txt`） |
| display.drf 来源 | 每次会话日志都有 `Loading smic18mmrf/display.drf ... done!`，即老师 PDK 那份；本轮没动它 |

## 2. 选择的机制与为什么只用它一条（§3）

用 **X 资源 + xrdb 合并**，理由不是习惯而是排除法：

1. User Preferences 这条路在这台机器上不存在（第 1 节）。
2. 不改老师 PDK 的 `display.drf`，也不建项目副本来改显示包——背景本身不是 display 包属性，
   用 drf 解决背景是用错工具；`DISPLAY_DRF: NOT_MODIFIED`。
3. 先试的是**更项目隔离**的 `XENVIRONMENT`（只影响我们自己启动的会话），但它在本机**无法验证**
   （第 5 节两个原因），所以按"不许拿假设当交付"的规矩丢掉，改用 Cadence 自己样例文件写明的
   标准做法："you need to run the xrdb program to have a resource take effect once the X server
   has been started"。
4. 不叠加：任何时刻只有一条通道生效；启动器只做一件事——快照会话数据库，然后 `xrdb -merge`
   一个文件，里面只有两行 `Opus.` 键。

副作用如实写明：`xrdb` 改的是**整个 X 会话**的资源数据库，所以同一会话里用别的方式启动的
Virtuoso 也会读到这两项（这正是你要的效果，但必须说清楚是会话级）。只加 `Opus.*` 键，
其它 8 行 GNOME 项一个字不动；恢复用快照 `xrdb -load`，不是 `xrdb -remove`（那会清掉别人的项）。

## 3. 白色背景的可读性处理（§4）

本轮真正改的两个颜色，都是"在白底上会消失"的那两类：

| 元素 | 归属 | 本轮处置 |
|---|---|---|
| 设计窗口背景 | `Opus.editorBackground` | 设为 `#ffffff` |
| 选择框 / 框选矩形 / 移动·拉伸橡皮筋 / 预选中高亮 | `Opus.dragColor` | 出厂是白色，白底上等于隐形 → 设为 `#000000`（与白底对比度 21:1，按 WCAG 相对亮度公式由我们自己这两个值算出） |
| 导线、MOS 符号、pin、pin 名、实例名、参数标签、栅格、被选中对象、网络高亮 | 老师 PDK `display.drf` 的显示包（**未改、不可改**） | **GUI_PENDING**，见下 |

必须诚实的地方：那 9 类元素的画色来自 PDK 调色板，而这套调色板是为深色画布调的。
本机取不到可信像素（第 5 节），所以我**不能**说"全部清晰"。给你一张明天 30 秒能过完的清单：
打开 `microled_cells/data_sink_1ch/schematic`，逐项看——导线、MOS 符号轮廓、pin 与 pin 名、
实例名、参数标签、栅格、点选一个管子后的选中色、Trace 一个网络后的高亮色、框选矩形、
拖线时的橡皮筋。若其中任何一项看不清，说一句，我按 `display.drf` 的正规改法在**项目内副本**上
只调那几个必要的显示包（绝不动 PDK 原件），并用同一套开关管理。

## 4. 怎么切、怎么恢复（§5）

```
cadence_work/appearance/
    white/xresources.txt        #ffffff + 黑色 dragColor（生效的那份）
    original/xresources.txt     显式"不加任何 Opus 项"，作为对称的恢复目标
    theme                       一行：white | original
    active_resources            一行：当前主题的资源文件绝对路径
    backup/xrdb_query_original.txt   首次合并前的会话数据库快照（8 行，全是 GNOME 项）
    backup/home_dotfiles_before.txt  证明 /root 下本来就没有任何 X/cdsinit 配置
    backup/launch_virtuoso_before_gui1.sh  启动器改动前的原件
    backup/version_before.txt   版本与 hotfix 号
```

- `WHITE_THEME_ENABLE`：`bash scripts/gui1_white_theme.sh enable`
- `RESTORE_ORIGINAL_THEME`：`bash scripts/gui1_white_theme.sh restore`
- 看当前状态：`DISPLAY=:0 bash scripts/gui1_white_theme.sh status`
- 单次启动不套主题：`QODER_THEME=original` 再执行启动器
- 幂等性：指针文件每次整体重写；`xrdb -merge` 同键同名重复只留一条（第 6 项实测：连做 3 次合并后
  `Opus.editorBackground` 仍是 1 条）

## 5. 验证到什么程度、什么验不了（§7）

可复现入口：`DISPLAY=:0 bash scripts/gui1_verify_theme.sh`，四段全 PASS
（证据：`results/evidence/gui1_validate_20261009_091657.log`、
`gui1_selfcheck_20261009_091657.log`、`gui1_launcher_check_20261009_091657.log`）：

```
CONFIGURATION_VALIDATION: PASS     两个资源名在本机二进制里命中；本机文档写明其义；绑定用紧格式；
                                   启动器已接线；三条 SCH-1 检查原样保留
DATABASE_VALIDATION:      PASS     真读回 X 会话数据库：
                                   合并后 Opus 键 2 条且值正确；
                                   连续 3 次合并仍是 1 条（不无限追加）；
                                   restore 后行数 10 -> 8、Opus 键 0 条、GNOME 原项还在；
                                   重新 enable 又回到 2 条（往返成立）
LAUNCHER_VALIDATION:      PASS     LAUNCHER_CHECK: PASS；theme 行打印出将要合并的文件路径；
AUTO_LOAD_ON_NEXT_START:  YES      且 LAUNCHER_CHECK=1 模式不写数据库（CHECK_MODE_IS_SIDE_EFFECT_FREE: PASS）
DISPLAY_RESOURCE_VALIDATION: 同上（资源名/绑定/文档三项就是这一项）
```

验不了的部分，两条都是实测，不是"没试"：

1. **这台 X 取不到可信像素。** `import -window root` 在 1076x1277 的 `:0` 上只回一张 ~269 字节的
   平面图；按窗口 id 抓则要么整张全黑、要么报 `Resource temporarily unavailable`（CIW 的
   `Map State: IsUnMapped`）。连 `xmessage` 这种最简单的 Xt 客户端也被读成全黑——三次配置
   （默认 / 要求白 / 要求蓝）像素完全相同，见 `scripts/gui1_xt_delivery_test.sh` 与
   `results/evidence/gui1_capture_{baseline,proof,shipped}.txt`（那份抓取当时是按窗口 id 抓 Cadence
   自己的窗口写的，保留下来正是为了说明它测不出东西）。既然连已知颜色都测不出，
   截图就不能用来宣称白色生效。
2. **批处理会话里没有可绘制的窗口。** `hiOpenWindow(?appType "Schematic" …)` 返回 nil、
   `schHiOpenWindow` 不存在，只有无参 `hiOpenWindow()` 建出一个 900x700 的 Graphics 窗口，
   而空图形窗口在没有 cellview 画进去之前不会重绘（三次抓取都 100% 黑）。
   所以"editorBackground 到底让画布变成什么色"只能靠 GUI 看。

结论：`WHITE_BACKGROUND_CONFIG: PASS`（机制与状态已测量）、
`GUI_VISUAL_VERIFICATION: PENDING_USER_REVIEW`（画布观感待你看），
`WIRES/SYMBOLS/LABELS/HIGHLIGHT_VISIBLE: GUI_PENDING`。

## 6. 边界（§8）与顺手发现的两个坑

未做也未受影响：`c2mos_dff_1bit`、`c2mos_dff_1bit_paramfix`、`data_sink_1ch`、`data_bias_ref`
一律未打开写、未 `dbSave`（探测会话全部以只读方式打开并只报 `instances/nets/shapes` 计数）；
没有跑 SpiceIn、netlist、Spectre、layout/DRC/LVS/PEX；没碰许可证、PDK 路径与软件版本；
**没有"顺手"给 C²MOS 正式 cell 应用参数修复**（任务 #71/#76 仍然挂着）。
本轮启动/退出的是我自己为验证发起的会话（探测 SKILL 以 `exit()` 自我结束），
没有对任何既有 GUI 发信号或强杀。

两个坑，都已写进 `AGENTS.md` 第 30 条：

1. `scripts/sync2guest.sh` 的暂存目录只按 basename 命名，同一次调用里传两个同名文件
   （`appearance/white/xresources.txt` 与 `appearance/original/xresources.txt`）会让后者把前者的
   内容盖掉，**静默部署错文件**。已改为按序号暂存；这是 SCH-2 那类"看起来成功、内容不对"的同一形状。
2. `xrdb` 走 C 预处理器：资源文件里 `!` 注释如果含撇号/引号会被当成未结束的字符常量，
   逐行报 `Unterminated character constant`（键仍然合并成功，但日志脏）。资源文件因此保持
   短注释、不写撇号，说明文字放报告里。

## 7. Git 与远端状态（§9）

本轮提交在 `feature/data-driver-virtuoso-schematic` 上：

```
GUI-1 commit:  d3881ef  feat: give the Micro LED Virtuoso session a white schematic background...
上一条:        a53f646  SCH-3 data driver 原理图（已在远端，独立回读确认过）
Safety Gate:   staged 22 个对象，PDK/CREDENTIAL/PRIVATE_KEY/VENDOR_MODEL 计数全 0，PASS
```

推送状态：`git push` 三次尝试全部失败（两次 `Failed to connect to github.com port 443`、一次
`Recv failure: Connection was reset`），而**同一时刻 `gh api` 正常**并返回
`refs/heads/feature/data-driver-virtuoso-schematic = a53f646` —— 与 SCH-2 遇到的形状一致，
是 git 的 443 传输被阻断，不是闸门或凭据问题（只对当次命令加 `-c http.version=HTTP/1.1`，
未改任何全局配置）。因此：

```
LOCAL_REMOTE_PARITY: NOT_YET（本地 d3881ef / 远端 a53f646；远端尚未收到本轮提交）
```

等网络恢复后重跑 `git -c http.version=HTTP/1.1 push origin feature/data-driver-virtuoso-schematic`
并用 `git ls-remote` 或 `gh api .../git/refs/heads/...` 独立回读才算推上去；未 merge main。

