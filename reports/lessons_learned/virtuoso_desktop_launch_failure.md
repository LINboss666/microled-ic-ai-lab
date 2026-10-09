# Virtuoso 桌面快捷方式无法启动：根因、修复、复现与回退（GUI-2，永久防错规则）

日期 2026-10-09。环境：RHEL 6.5 guest，GNOME/metacity，`DISPLAY=:0`，IC6.1.7-64b.78。
图标 = `/root/Desktop/Cadence-Virtuoso-MicroLED.desktop`，目标 =
`/root/microled_ai_project/cadence_work/launch_virtuoso.sh`。
验证工件：`scripts/gui2_verify_desktop.sh`（静态全链路）、`scripts/gui2_real_launch.sh` +
`scripts/gui2_envexec.sh`（用桌面会话真实环境做真实启动并证明窗口可绘制）。

## 1. 故障现象

双击 `Cadence Virtuoso - MicroLED` 弹：

```
There was an error launching the application.
```

同期误导性的"一切正常"证据（这是本轮最关键的方法论问题）：

```
bash -n launch_virtuoso.sh      -> rc=0
LAUNCHER_CHECK=1 bash launch_virtuoso.sh
   CHECK CADENCE_ENV_LOADED PASS
   CHECK PROJECT_WORKDIR_CORRECT PASS
   CHECK CDS_LIB_FOUND PASS
   LAUNCHER_CHECK: PASS
```

静态检查全绿而图标仍然起不来，**因为这两条检查都是用 `bash <脚本>` 跑的，而 `bash` 根本不需要
执行位**。桌面走的是另一条路：`execv(脚本)`。

## 2. 已确认根因

`launch_virtuoso.sh` 的**执行位丢了**（`-rw-r--r--`，mode 644），而 `.desktop` 的
`Exec=` 和 `TryExec=` 都指向这个文件本身：

```
Exec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh
TryExec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh
```

GNOME 的判定顺序是先 `access(TryExec, X_OK)` 再 `execv(Exec)`，两处都要求 X_OK。实测：

| 检查 | 修复前 | 修复后 |
|---|---|---|
| `ls -l` 权限位 | `-rw-r--r--` (644) | `-rwxr-xr-x` (755) |
| `access(X_OK)`（= TryExec 语义） | FAIL | PASS |
| `execv(Exec 目标)` | **errno 13 EACCES**，`Permission denied`，rc=126 | 真正进入脚本 |
| 真实启动结果 | 无进程、无窗口、无 `virtuoso_gui_*.log` | virtuoso 进程 + CIW `IsViewable` |

执行位是怎么丢的（因果链已定位到代码行）：GUI-1 修改 launcher 后用
`scripts/sync2guest.sh` 部署，该脚本第 54 行**对所有同步文件硬编码 `chmod 644`**，收尾只对
`$PROJ/scripts/*.sh` 补 `+x`，**不覆盖 `cadence_work/`**。所以 GUI-1 那次同步把 755 改成了 644。
旁证：GUI-1 之前的备份 `cadence_work/appearance/backup/launch_virtuoso_before_gui1.sh`
仍是 `-rwxr-xr-x`，mtime 停在 Oct 8 20:39；当前文件 mtime Oct 9 09:15 正是那次部署的时刻。

第二层原因：仓库里该文件的 index mode 是 **`100644`**（`git ls-files -s` 实测），也就是说执行位
从来只靠 guest 上一次手工 `chmod`，任何一次重新部署/签出都会再丢一次。**所以本轮同时修了仓库、
部署脚本和 guest 三处**，只 `chmod` 一次是不够的。

### 白色背景不是原因（有证据，不是推测）

任务明确要求"不允许在没有证据的情况下归咎于主题配置"，同样也不允许在有证据前把主题排除掉。四条
独立证据：

1. **代码路径不可能致命**：launcher 里的主题块只有 `say`（打印）和 `if xrdb -merge; then ... else
   打印 theme NOT applied`，**没有任何 `bail`/`exit`**；xrdb 失败也照样往下走到 `exec virtuoso`。
2. **主题生效时真实启动成功**：`theme applied via xrdb` 之后 `STARTING_VIRTUOSO`，
   pid 784，CIW 窗口 `0x1800020` `Map State: IsViewable`、`WM_STATE window state: Normal`。
3. **主题关闭时同样成功**（受控 A/B，两次只差 `QODER_THEME`）：

   | 执行位 | 主题 | 结果 |
   |---|---|---|
   | 缺失(644) | white（应用了） | **EACCES**，无进程 |
   | 存在(755) | white（应用了） | 启动成功，CIW IsViewable |
   | 存在(755) | `QODER_THEME=none` | 启动成功，CIW IsViewable |

   变量只动执行位时结果翻转，只动主题时结果不变 —— 根因是执行位。
4. `xrdb -query` 两条 `Opus` 资源始终在会话数据库里，与能否启动无关。

顺带按任务的提醒记录一条真实语义：`QODER_THEME=none/original` **只跳过本次 merge**，不会删掉已经在
X 会话数据库里的白色资源——A/B 的 leg B 里 `resource_file=none`，而 `xrdb -query` 仍显示
`Opus.editorBackground: #ffffff`。要彻底恢复必须显式
`bash scripts/gui1_white_theme.sh restore`（它用 `xrdb -load <快照>`，不是 `-remove`）。

## 3. 失败日志（原文，便于比对）

修复前，按桌面同样的方式直接 `execv`：

```
/root/microled_ai_project/cadence_work/launch_virtuoso.sh: Permission denied
direct_invoke_rc=126
('execv errno=', 13, 'Permission denied')
```

修复后，用 GNOME 会话自己的环境（`env` 逐项取自 `/proc/<gnome-session>/environ`）启动：

```
CHECK CADENCE_ENV_LOADED PASS
      virtuoso  : /opt/IC617//tools/dfII/bin/virtuoso
CHECK PROJECT_WORKDIR_CORRECT PASS
      DISPLAY   : :0   XAUTHORITY: /var/run/gdm/auth-for-root-<per-boot-token>/database
CHECK CDS_LIB_FOUND PASS
      theme     : white  resource_file=.../appearance/white/xresources.txt
      theme applied via xrdb (undo: bash scripts/gui1_white_theme.sh restore)
      session log: .../cadence_work/logs/virtuoso_gui_20261009_194033.log
STARTING_VIRTUOSO
VIRTUOSO_PID=784 (appeared after 3s)
VIRTUOSO_WINDOW=0x3600020 (viewable after 3s)   Map State: IsViewable   WM_STATE: Normal
REAL_LAUNCH: PASS (process + viewable window on the session display)
```

Cadence 侧唯一一条 X 报错，出现在**成功**的会话里，与本故障无关，记录以免被再次误当成根因：

```
Display :0 Error "BadAtom (invalid Atom parameter)"  request 20 error 5 serial 228
```

调查过程中排除掉的其它候选（都用实测排除，不是靠猜）：

* `/root/.Xauthority` **根本不存在**；桌面会话真正的 `XAUTHORITY` 是
  `/var/run/gdm/auth-for-root-<per-boot-token>/database`（mode 600）。launcher 只在 `XAUTHORITY` 未设且
  `~/.Xauthority` 存在时才设它，所以从 SSH 起时会退回"无 XAUTHORITY 也能连"（本机 X 允许本地连接）。
  从桌面环境起时 `XAUTHORITY` 已由会话提供，实测能连。**两种情况都不是失败原因。**
* 桌面 `PATH` 首项是 `/etc/env`，即那个"末尾会自己拉起 GUI"的包装脚本所在目录——这是本轮最危险的
  候选（若解析到它，等于偷偷执行了包装）。实测在**桌面真实环境**下 launcher 仍解析到
  `/opt/IC617//tools/dfII/bin/virtuoso`，因为 `cad_env.sh` 从包装里只 eval `export` 行、把 IC617
  的 bin 放到了 PATH 前面；且 launcher 自带 `case "$BIN" in /opt/IC617/*) ;; *) bail` 的护栏会拒绝
  任何别的路径。**排除。**
* `.desktop` 文件本身：mode 755、纯 LF、`Type=Application`、`Terminal=false`、字段完整，
  `Exec`/`TryExec` 指向的文件存在。**排除**（它只是引用了那个没有执行位的目标）。
* metacity 在跑（pid 3018），窗口不是因为没有 WM 而不映射。
* `libManager`/`libSelect` 以 `-unmapped` 启动是 Cadence 的正常分段启动方式，不代表失败；
  **必须轮询 `IsViewable` 才能判 GUI 起来**（第一次查 `WM_STATE: not found` 只是因为当时还没映射，
  不是错误）。

## 4. 修复方法

三处一起改，缺一个都会复发：

1. **guest 现状**：`chmod 755 /root/microled_ai_project/cadence_work/launch_virtuoso.sh`。
2. **仓库**：`git update-index --chmod=+x cadence_work/launch_virtuoso.sh`
   → index mode 由 `100644` 变 `100755`（blob SHA 未变，只改 mode）。
3. **部署通道**：`scripts/sync2guest.sh` 不再硬编码 644，改为按 `git ls-files -s` 的 mode 决定
   落地权限（`100755 → 755`，其余 `644`）。这样"仓库说它是可执行的"才是唯一事实来源。

白色背景功能**完整保留**，未动主题、未动 `display.drf`、未动任何电路文件。

### 新增的防错检查（可反复运行，无副作用）

```
bash /root/microled_ai_project/scripts/gui2_verify_desktop.sh   # 静态全链路 14 项
bash /root/microled_ai_project/scripts/gui2_real_launch.sh      # 真实启动 + 证明窗口 IsViewable
```

`gui2_verify_desktop.sh` 特意**不做** `execv`（否则每跑一次就真起一个 Virtuoso），只用
`os.access(X_OK)` 给出与 GNOME 相同的判据；它也不假装验证了 GUI——最后一行固定输出
`VIRTUOSO_GUI: UNVERIFIED_BY_THIS_SCRIPT`，并附一句 `LAUNCHER_CHECK: PASS` 本身不能证明桌面图标可用。

## 5. 如何复现

```
chmod 644 /root/microled_ai_project/cadence_work/launch_virtuoso.sh
# 双击图标 -> "There was an error launching the application."
# 命令行等价复现（不需要真双击）：
os.access(path, os.X_OK)      -> False
execv(path, [path])           -> OSError errno 13 EACCES   (rc=126)
# 而这两条仍然全绿，正是当初掩盖问题的原因：
bash -n <path>                -> rc=0
LAUNCHER_CHECK=1 bash <path>  -> LAUNCHER_CHECK: PASS
```

## 6. 如何回退

```
# 撤销本轮修复（不推荐，会让图标重新失效）：
chmod 644 /root/microled_ai_project/cadence_work/launch_virtuoso.sh
git -C D:\ic617_agent_bridge update-index --chmod=-x cadence_work/launch_virtuoso.sh
# sync2guest.sh 的 mode 逻辑回退：git revert 本轮 commit 即可（脚本只改了权限推导，没改内容路径）

# 只回退白色背景（与启动无关，二者互相独立）：
bash scripts/gui1_white_theme.sh restore     # xrdb -load 快照，恢复原会话资源数据库
```

回退是安全的：本轮没有修改 `.desktop` 内容、没有改 Cadence 安装目录、没有改 license、没有改 PDK、
没有改任何原理图/CDF 参数/OA 库。

## 7. 仍未验证的一项（不伪造）

`DESKTOP_DOUBLE_CLICK: USER_VERIFICATION_REQUIRED`。

我能验证的是"桌面所执行的那条命令，在桌面会话自己的环境下，确实起了 Virtuoso 并映射出可见窗口"
（`gui2_real_launch.sh` 用 `env` 逐项复制 `/proc/<gnome-session>/environ` 后 `execv` 同一个
`Exec` 目标）。我**没有**真正驱动 GNOME 对图标的双击（这台 VM 无法可靠取信像素，也无法模拟 nautilus
的图标点击路径），所以不写 `DESKTOP_DOUBLE_CLICK: PASS`。用户双击一次即可闭环。

另外记录一条仓库事实：`cadence_work/desktop/`（`.desktop` 源文件）**没有被 git 跟踪**——
`repo_safety_rules.py` 的扩展名白名单不含 `.desktop`。因此这个快捷方式本身没有版本记录，改坏无法
用 git 找回；本轮按"不覆盖用户原有快捷方式"的要求也没有动它的内容。
