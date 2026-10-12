# c2mos_gui_ade_probe.md — 真实 GNOME/Virtuoso GUI 下的 ADE 原生网表能力验证

基准提交：`8ed40289cd7ee12c5f282f09b3d127e3fc847c24`（branch `gexing321/scan-driver/c2mos-schematic`）
原始证据：`results/evidence/c2mos_gui_ade_probe.txt`（SECTION A–I，全部命令原文）
探测件：`skill/c2mos_gui_ade_probe.il`（只读；内含零个写侧 ADE 调用）
本轮性质：**只读**。OA 库、DUT、Testbench、analogLib、PDK 指纹前后一致（SECTION I）。

---

## 结论（一句话）

**GUI 真的起来了、编辑器真的初始化了、License 正常、器件读得到 —— 原生网表仍然不通，
而且卡点被精确锁定在一个步骤上：ADE 的"会话↔设计绑定"（`axlSetMainSetupDBLCV` 返回 nil），
它不是"API 不存在"，也不是参数、License、DISPLAY/XAUTHORITY 或 terms 的问题。**

因此 `NATIVE_NETLIST_BLOCKED` 依然成立，但含义比上一轮**更精确**：批处理与窗口化两种启动方式都测过，
失败点相同；打通它需要**人来开一个 ADE 窗口**或**授权一次写操作**（见 §H）。

---

## A. 真实 GUI 是否启动成功？

**成功**，且不是我自证的——用仓库既有的验证器 `scripts/gui2_real_launch.sh`（它按被验证者的真实调用方式
execv，并用 `Map State: IsViewable` + `WM_NAME` 做判据，AGENTS.md 第 32 条要求的就是这种判法）：

```
VIRTUOSO_PID=47292 (appeared after 3s)
VIRTUOSO_WINDOW=0x3400020 (viewable after 15s)
    Map State: IsViewable
  WM_NAME(STRING) = "Virtuoso® 6.1.7-64b - Log: .../virtuoso_gui_20261012_191734.log"
  WM_CLASS(STRING) = "Qt-subapplication", "Virtuoso"
REAL_LAUNCH: PASS (process + viewable window on the session display)
```

## B. 当前 DISPLAY / XAUTHORITY 是否正确？

**正确，且全部从当前活动会话现取，没有硬编码**：

```
gnome_session_pid=3032
  env DISPLAY=:0
  env XAUTHORITY=/var/run/gdm/auth-for-root-8x8Kba/database     # 读自 /proc/3032/environ
  x_sockets=X0   logged_in_users=root tty1 (:0)   Window Manager: gnome (metacity)
  Virtuoso Framework License (111) was checked out successfully.
```

两条**我自己的**踩坑记录（与 Cadence 能力无关，但必须写清，否则会被误读成阻塞证据）：
1. 第一次 `MODE=gui` 直接报 `REFUSED: MODE=gui needs DISPLAY`。根因是 `scripts/gui2_envexec.sh`
   的参数约定：它把 `/proc/<gnome-session>/environ` 的条目交给 `env`，**只有当它只收到一个"程序"参数时
   才成立**；我当时传了 `env MODE=gui bash ...`，第一个非 `KEY=VALUE` 令牌让 `env` 停止导出变量，
   会话环境变量被当成脚本的位置参数塞了进去。修法：把变量放进 wrapper 脚本，wrapper 作为唯一参数
   （`gap_run.sh` 里已注释说明）。
2. `Display :0 Error "BadAtom"` 在这一轮再次出现在会话 stdout 里 —— AGENTS.md 第 32 条已记录
   **成功会话里也会有这一条**，本轮它同样与结果无关，我没有把它当根因。

## C. ADE 相关 API 在 GUI 会话中返回什么？

窗口化会话（`.cdsinit` 注入）里的实测矩阵。`getd` 一栏注意：本 build 上 `getd` 曾被实测不可靠
（AGENTS.md 第 28 条），所以**调用结果才是主判据**。

| 入口 | 存在性（getd，探测时） | 调用结果 | 判读 |
|---|---|---|---|
| `schCheck(cv)` | — | **`((0 0))`** | 控制项：编辑器包真的初始化了，且 TB 图 0 错 0 警 |
| `hiGetMainWindow()` | — | `nil` | `.cdsinit` 时刻 CIW 窗口尚未创建（符合预期，不是失败） |
| `asiCreateSession(?simulator "spectre" ?cellView cv)` | 探测时 nil；**显式要 context 之后 `funobj:asiCreateSession`** | `nil` | **API 存在，调用失败** —— 不是"没有这个函数" |
| `asiCreateSession(?simulator ?libName ?cellName ?viewName)` | 同上 | `nil` | 参数形状已按文档给全，仍 nil |
| `asiNetlist` / `asiInitialize` | `funobj:asiNetlist`（post-load） | 走不到（无 session 对象） | 阻塞在上一步 |
| `nlCreateDesign` | `funobj:nlCreateDesign`（post-load） | `nil`（上一轮试过 5 种形状） | 同上 |
| `simSetDesign`（APS 族） | **`nil`（始终不存在）** | `nil` | APS 批驱动在本 install 未加载 → 这一族是真的没有 |
| `axlCreateSession("probe_session")` | — | **`"probe_session"`** | ADE XL 会话对象可创建 |
| `axlGetWindowSession()` | — | `(nil)` | **没有任何 ADE 窗口会话存在** —— 关键读数，见 §F |
| `axlSetMainSetupDBLCV(sess LIB CELL "schematic")` | `funobj:axlSetMainSetupDBLCV`（post-load） | **`nil`** | **设计绑定失败，就是这一步** |
| `axlNewSetupDBLCV(...)`（上一轮） | — | `nil` | 建立 setup db 也失败 |

关于 context：窗口化会话加载了 16 个 context，其中**没有 adexl / simui / asimenv / mmsimenv**
（`grep -c adexl` = 0）。显式请求加载时，`hiLoadContext("simui"/"adexl")` 与
`load("<...>.cxt")` 都返回 `nil` 且不报错；**之后** `getd` 对 `asiCreateSession/asiNetlist/nlCreateDesign/
axlSetMainSetupDBLCV` 报出 `funobj`。这条我如实写成"实测先后关系"，不过度解释：
可以确定的是"函数不存在"这个候选解释已被排除。

**分类结论**（任务书要求逐类区分）：
- API 不存在 → 仅 `sim*`（APS）成立；`asi*` / `nl*` / `axl*` 都存在。
- 参数不对 → 已排除：形状取自本机厂商文档 `/opt/IC617/doc/adexlSKILLref`，且批处理侧累计试过 7 种 `asi*` 形状。
- 会话初始化失败 → 已排除：见 §A/§B 控制项。
- **设计绑定失败 → 成立**（唯一失败点）。
- License 失败 → 已排除（框架 License checkout 成功）。
- DISPLAY/XAUTHORITY 失败 → 已排除（窗口 IsViewable）。

## D. 能否读取 Testbench 和 Symbol？

**两者都能读**：

```
GAP-TB-OPEN cell="c2mos_dff_tb" cv=db:0x1645ee1a instances=(8) nets=(7) terms=(0)
GAP-DUT-SYMBOL cell="c2mos_dff_1bit" open=db:0x17bee21a terminals=(6)
GAP-DUT-SYMPIN name="vss" dir="inputOutput"   ... vdd, qbar, q, clk, d   （共 6 条，全 inputOutput）
```
即 `c2mos_dff_tb/schematic` 与 `c2mos_dff_1bit/symbol` 在 GUI 会话里以 mode `"r"` 正常打开并读全。

## E. 能否在不修改现有 OA 的前提下生成 Cadence 原生网表？

**不能。** 三条原生路径本轮全部实测：
1. ADE-L `asi*`：session 创建失败（函数存在）→ 没有对象可供 `asiNetlist`。
2. `nl*`（`nlCreateDesign`/`nlNetlist`）：函数存在，调用 nil（上一轮 5 种形状）。
3. ADE XL `axl*`：会话可建，**设计绑定失败**；而 ADE XL 出网表只能通过"跑一次 run"
   （文档里没有 `axlNetlist` 这类只出网表的入口，索引里唯一的 `*Open*` 是 `axlOpenResDB`），
   而 `axlRunSimulation` + 其前置写操作（`axlPutTest` / `axlSetEnabled` / `axlCommitSetupDB`）
   在本轮是**明令禁止**的，我没有调用它们（探测件里根本没有这些符号）。

所以本轮**没有生成任何"Cadence 原生网表"**，我也没有把 OA 回读网表冒充它
（上一轮那份 `spectre/c2mos_dff_tb_from_oa.scs` 文件头仍写着 `NETLIST_PROVENANCE: OA_READBACK`）。

## F. 如果不能，具体阻塞在哪一步？

**阻塞在 ADE 的"会话 / 窗口应用对象 → 设计"绑定那一步**，证据链是：

```
GAP-AXL-GET-WS (nil)          # 当前没有 ADE (XL) 窗口会话
GAP-AXL-ATTACH nil            # axlSetMainSetupDBLCV 在这种状态下拒绝
GAP-AFTER-ATTACH nil          # 显式请求加载 context 之后，仍然拒绝
GAP-AFTER-AXL-BIND-EXIST (funobj:axlSetMainSetupDBLCV)   # 函数本身是在的
```

`axlGetWindowSession()` 返回 nil 是直接读数：批处理与 `.cdsinit` 注入都拿不到 ADE 窗口会话，
而绑定需要它。仓库 `scripts/sch_virtuoso.sh` 用来"等初始化完成后再执行"的钩子
`hiSetInitFunc` **在本 build 未定义**（两次 GUI 会话都报
`*Error* eval: undefined function - hiSetInitFunc`，且 `grep -rla` 在 `dfII/etc/context/64bit/` 下找不到该符号），
所以从代码里"等窗口出现之后再绑"这条路在这台机器上不存在。
**"人工在 CIW 里打开 ADE 窗口之后绑定是否会成功" —— UNVERIFIED**（我没有 xdotool/xte/wmctrl，
无法把键鼠事件送进那个窗口：`command -v xdotool xte wmctrl` 为空）。

## G. 是否需要修改 schematic terms？

**没有证据需要，也没有证据不需要。** 理由：
- 实测：TB `terms=(0)`，`schCheck` 给 `((0 0))`（0 错 0 警），DUT symbol 6 个 terminal 齐全，
  且上一轮 X1 的 6 个 `instTerm` 全部按名连上网络。也就是说**在失败点之前，terms 相关的东西都是健康的**。
- 阻塞发生在"绑定设计"阶段，比任何 terminal 处理都早，因此**不能把失败归因于 terms**。
- 反过来，"补了 terms 原生网表就通"同样**UNVERIFIED**（走不到那一步）。
- 本轮禁止修改任何现有 OA cell，我也确实没改（§I 指纹为证）。

## H. 下一步若要写 ADE 设置，准确要创建或修改哪些对象？

按最小顺序列清，**等你授权**（我按任务书要求在此停下，不自行执行）：

| # | 动作/对象 | 落在哪里 | 是否可回滚 |
|---|---|---|---|
| 1 | 一个 ADE(XL) 窗口会话：由人从 CIW 菜单打开 ADE（本机无 `axlOpen*`、无 `hiSetInitFunc`，脚本无法自己创建） | 内存 + Cadence 会话状态 | 关窗口即可 |
| 2 | `axlSetMainSetupDBLCV(session, microled_cells, c2mos_dff_tb, schematic)` | 可能在该 cell 目录下新增 setup/仿真状态对象 | 删该对象即恢复（本轮实测：它失败时**没有**留下任何文件，见 §I） |
| 3 | `axlPutTest(sdb, "<name>", "spectre")` + 工具参数 `tran stop=4.8*T maxstep=1e-4*T` | test/analysis 对象 | 同上 |
| 4 | `axlAddOutputSignal(session, test, "clk"/"d"/"q"/"qbar", ?save t)` | save 列表 | 同上 |
| 5 | `axlPutModel(corner, <PDK spe .lib 路径>)` + `axlSetModelSection(model, "tt")` | 模型引用（guest 本地路径，绝不入库） | 同上 |
| 6 | `axlRunSimulation(?session ...)` | 临时 run 目录里的 netlist + raw/psf | run 目录可整目录删除 |

影响面：**只有 `microled_cells/c2mos_dff_tb`（+ 一个临时 run 目录）**；不碰
`c2mos_dff_1bit`、不碰 MOS 尺寸、不碰 CDF 参数、不碰 analogLib、不碰 PDK。
回滚：写前 `tar cf /tmp/.../tb_before.tar microled_cells/c2mos_dff_tb`（上一轮已给过同样做法），
最坏情况删掉该 cell 目录即可完全恢复（TB 目录只有 `schematic/` 一个 view，3 个文件）。

## I. 本轮前后 OA / PDK 文件指纹是否一致？

**一致。** 全部在四次 GUI/ADE 会话之后复核：

```
md5_failures=0                      # md5sum -c 覆盖 microled_cells 全部 36 个文件
3de3224df0af59d8ba9953357f1dbe88  c2mos_dff_1bit/schematic/sch.oa   （与本轮开工前逐字节相同）
0355c086721b51254998f045b87209b8  c2mos_dff_tb/schematic/sch.oa     （同上）
analoglib_new=0   pdk_new=0   cdslib_defines=6
find microled_cells -name '*.cdslck'  -> 0
```

## J. 是否产生任何会话文件、锁或其他副作用？

有，全部列出：
1. `cadence_work/logs/` 下新增会话日志/输出（既有约定目录，不进 git）。
2. **3 个残留锁文件，且都是"日志文件"的锁，不在库里**：
   ```
   cadence_work/logs/virtuoso_gui_20261012_191734.log.cdslck
   cadence_work/logs/sch_nograph_20261012_190754.log.cdslck
   cadence_work/logs/sch_nograph_20261012_185629.log.cdslck
   ```
   来源：被我方超时收走/关闭的会话留下的 stale lock。**我按任务书"不要清理锁文件"没有删它们**；
   要清请确认无会话后再删（`microled_cells` 内 0 锁，已实测）。
3. 我自己启动的那个映射窗口 GUI 会话（pid 47292）已由我关闭（`kill`，SIGTERM），
   结束时 `virtuoso_pids=` 空。用户的会话本轮自始不存在（`virtuoso_pids_before=[none]`），我没有触碰任何他人进程。
4. `/tmp/tb_audit/` 下的探测 wrapper/日志（scratch，不在工程库）。
5. 仓库侧：只新增探测件与文档，**未修改任何既有冻结脚本**（`git diff --stat` 见交付信息）。

---

## 需要人定的两件事

1. **要不要人工开一个 ADE 窗口做一次对照？** 你在桌面上双击现有快捷方式（或我已验证过的启动链），
   在 CIW 里 Tools → Analog Design Environment，把 `microled_cells/c2mos_dff_tb/schematic` 放进去，
   然后告诉我"ADE 已打开"。我可以随后跑一次**只读**探测（`axlGetWindowSession` / `axlGetTests` /
   绑定检查），这能直接判掉 §F 里唯一剩下的 UNVERIFIED。
   （我无法替你做这一步：本机没有 xdotool/xte/wmctrl，也没有可用的 `hiSetInitFunc`/`axlOpen*` 钩子。）
2. **是否授权 §H 的 2–6 号写操作？** 授权范围只涉及 `c2mos_dff_tb` 与一个临时 run 目录；
   得到授权后我会先做 tar 前像，再逐步做，并在每一步后跑只读回读与 `md5 -c`。
