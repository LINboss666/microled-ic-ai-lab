# c2mos_ade_binding_reaudit.md — ADE 设计绑定结论的独立复核（REWORK / READ-ONLY）

基准 SHA：`670fcb8cde1550fee4f4c9142417c87eafd15409`　个人分支：`gexing321/scan-driver/c2mos-schematic`
原始证据：`results/evidence/c2mos_ade_binding_reaudit.txt`（SECTION A–D，全部命令原文）
本轮性质：**只读事实核对**。没有再跑任何 ADE 调用、没有开 Virtuoso 会话、没有读改 OA 之外的任何东西；
`axlSetMainSetupDBLCV` / `axlPutTest` / `axlCommitSetupDB` / `axlRunSimulation` 一个都没调用（§六）。

**先给结论：上一轮我写的"唯一阻塞原因是没有 ADE 图形窗口"证据不足，本轮撤回。**
核对本机文档后发现的更可能是**我自己把第四个参数的语义用错了**；但这仍不足以解释全部，见 §7。

标注约定：**DIRECTLY_OBSERVED**（本轮命令输出）／**DOCUMENTED**（本机安装自带文档原文）／
**DERIVED**（由前两者推断）／**NOT_VERIFIED**（本轮无法证实，需人或需下一次实测）。

---

## 1. 任务1：函数签名核对

```
FUNCTION_SIGNATURE            [DOCUMENTED]
  axlSetMainSetupDBLCV( t_session t_libName t_cellName t_viewName [ ?mode t_mode ] ) => x_mainSDB / nil

ARGUMENT_MEANING              [DOCUMENTED]
  t_session    : axlCreateSession(t_sessionName) 建出来的会话名
  t_libName    : 设计所在库
  t_cellName   : 设计单元名
  t_viewName   : "the setup database specified by the given library, cell, or view"
                 —— 指向**存放 setup database 的那个 view**（ADE XL 自己的 setup view），
                 文档里所有示例给的都是 "adexl" / "adexl_view"，没有一处给设计视图名
  ?mode        : 示例出现 ?mode "r" —— 只读绑定（不建、不提交）

DOCUMENTATION_SOURCE          [本机版本，不用网络资料替代]
  /opt/IC617/doc/adexlSKILLref/sessionIl.html
      line 2434  签名
      line 477   axlSetMainSetupDBLCV(axlSession car(LibraryName) cadr(LibraryName) ViewName)
      line 482   axlSetMainSetupDBLCV( axlSession "myLib" "mycell" "adexl")  后续 axlSaveSetup/axlCommitSetupDB
      line 998   axlSetMainSetupDBLCV(axlSession "mylib" "mycell" "mycell_view") 形式（axlMainAppSaveSetup）
      line 485   "If you are running an ADE XL script in the standalone mode, after creating a new
                  session, you can set up a database for the session by using axlSetMainSetupDBLCV."
      另有一处示例直接写成： axlSetMainSetupDBLCV("session0" "myLib" "myCell" "adexl" ?mode "r")
  /opt/IC617/tools.lnx86/dfII/etc/context/64bit/adexl.cxt 存在（产品已装）
  /opt/IC617/doc/adexl/* 存在；安装清单 /opt/IC617/install/pkgs/adexl64b_lnx8606.17-p048lnx86.ok

CURRENT_CALL                  [DIRECTLY_OBSERVED，skill/c2mos_gui_ade_probe.il]
  line 101:  sdb = car(errset(axlSetMainSetupDBLCV(sess LIB CELL "schematic")))
  line 129:  printf("GAP-AFTER-ATTACH %L\n" errset(axlSetMainSetupDBLCV(sess2 LIB CELL "schematic")))

POSSIBLE_MISMATCH             [DOCUMENTED + DIRECTLY_OBSERVED 对照得出]
  第四参数我传的是设计视图 "schematic"，文档要求的是"setup database 所在的 view"（示例一律为 adexl 类）。
  => 参数语义不匹配，确证存在。
  但：该 cell 目前**根本没有** adexl setup view（见 §2），所以即使按文档传 "adexl"，
     也仍然没有可绑定的对象。因此"不匹配"是**必要条件之一**而非充分结论 —— 它是不是本轮 nil 的原因：NOT_VERIFIED。
```

补充（同为 DOCUMENTED）：`axlNewSetupDBLCV( t_libraryName t_cellName t_viewName ) => t / nil`
的说明是 "Creates a new setup db in the specified lib, cell, view location. **It automatically
overwrites any existing setup db** in any of the above mentioned locations." —— 这条是**写**且带覆盖语义，
本轮禁止，我没有调用它。

---

## 2. 任务2：该 cell 实际存在哪些 view

**DIRECTLY_OBSERVED**（dir library：一个 view 一个目录）：

```
c2mos_dff_tb     : schematic
c2mos_dff_1bit   : data.dm  schematic  symbol
data_sink_1ch    : data.dm  schematic  symbol
data_bias_ref    : data.dm  schematic  symbol
sch1_top         : data.dm  schematic
sch3_top         : data.dm  schematic

find microled_cells -type d ( -name 'adexl*' -o -name 'maestro' -o -name 'config' -o -name 'Ade*' )  -> 无
find cadence_work   -maxdepth 3 -type d -name 'adexl*'                                              -> 无
```

即：**只有 `schematic`**；`symbol/adexl/maestro/config` 一个都没有；整个工程里没有任何 ADE XL setup view。
我没有创建、没有修改、没有保存（本轮零写入，§SECTION D 指纹为证）。

---

## 3. 任务3：对上一轮证据的重新评估

### A. `axlGetWindowSession()` 返回 nil，是否只是因为没有打开 ADE XL 窗口？

它字面含义只是"**没有与窗口关联的会话**"。而 DOCUMENTED 的 standalone 用法明确不需要窗口；
并且本轮在旧日志里发现一条我上一轮没引用的**直接读数**：

```
\# ADE XL session 'probe_session' started on Mon Oct 12 19:14:29 2026      <- Cadence 自己打的 banner
\o GAP-AXL-SESSION "probe_session"
\o GAP-AXL-GET-WS (nil)
\o GAP-AXL-ATTACH nil
```

所以"无窗口 ⇒ 不能绑定"缺乏依据：**窗口不是绑定的前提**（DOCUMENTED + banner 实证 ADE XL 会话确实以独立方式起来了）。
但"有窗口时绑定是否会成功"：NOT_VERIFIED。

### B. `axlCreateSession()` 已返回会话对象，是否一定需要窗口会话才能绑定？

不一定。文档示例（line 482 / 998）就是 `axlCreateSession(...)` 直接接 `axlSetMainSetupDBLCV(...)`，
全程没提窗口。上一轮我把"绑定需要窗口会话"写成了因果，那一句是 **DERIVED 而非 OBSERVED，本轮撤回**。

### C. 第四参数与官方定义是否一致？

**不一致**（§1 POSSIBLE_MISMATCH）。文档要 setup-database view（"adexl"/"adexl_view"），我给的是 "schematic"。

### D. 当前是否已有可读取的 ADE XL view？

**没有**（§2）。这同时意味着：任何"按文档传 adexl 再试"的调用，在当前库状态下预期仍然拿不到 setup db；
要让它有对象可绑，必须先创建 —— 那是**写操作**（`axlNewSetupDBLCV` 还会覆盖既有 setup db），本轮禁止。

### E. 现有日志是否隐藏了实际 SKILL 错误信息？

**部分是，而且我发现上一轮有两处误读必须更正：**

1. 绑定调用前后**没有任何错误文本**（上面引的那段就是完整上下文：banner → SESSION → GET-WS → ATTACH → GAP_DONE）。
   因此这个 `nil` 是**静默 nil**，用现有日志无法区分"函数正常返回 nil"与"异常被 `errset` 吞掉"。
   上一轮我把它当作"设计绑定失败"这一个确定结论写出来，超出了证据强度。
2. 上一轮 §C 表里我写"`hiLoadContext`/`load(*.cxt)` 返回 nil，但**之后** `getd` 报出 `funobj`，
   所以'函数不存在'这一解释被排除"。真实日志是：
   ```
   \e *Error* lineread/read: syntax error encountered in input at line 1 column 1
        in file /opt/IC617/tools.lnx86/dfII/etc/context/64bit/simui.cxt
   ```
   —— 那是**把二进制 context 当 SKILL 源码读**的语法错误：我的"加载 context"从未成功。
   `getd` 之后报 `funobj` 只能说明这些符号本来就可解析（很可能是 ADE XL 会话启动时带起来的），
   **不能归因于我的 load 调用**。这条推论作废。
3. 方法论更正（下一轮用）：要拿到真实错误文本，就**不要**把待判定的调用包在 `errset` 里 ——
   把单独一个调用放进一次性 IL，让 Cadence 自己打印并中止（"中止"本身就是证据）。
   `errset` 各模式对错误打印的影响本轮未实测：NOT_VERIFIED。

### F. 上一轮所谓"License 正常"，验证的是哪一个许可证？

只验证了 **Virtuoso Framework License**：日志里唯一一行是
`Virtuoso Framework License (111) was checked out successfully.`（两个会话都只有这一行）。

- ADE / ADE XL 产品许可证是否可用：**NOT_VERIFIED**（没有任何相关 checkout/拒绝记录）。
- Spectre 可用：有间接实证（上一轮 `spectre` 真跑出 33/33 断言），但那是 MMSIM/Spectre 侧，
  不等于 ADE XL 的许可/配置正常。

---

## 4. 最终七问

**1) 上一轮"唯一阻塞原因"是否成立？**
**不成立，撤回。** 绑定 `nil` 至少有三个未排除的候选：(a) 第四参数语义不符（已确证存在该不匹配）；
(b) 该设计没有任何 ADE XL setup db（已确证 §2）；(c) ADE XL 许可/初始化条件（未验证 §F）。
本轮证据无法在三者之间定论。

**2) 是否存在参数视图不匹配？**
存在（DOCUMENTED + 代码原文对照）。

**3) 是否需要创建 ADE XL view？**
按文档语义**很可能需要**（绑定的对象是 setup database，而库里不存在）——但这是 DERIVED，未实测。
创建即写库，且 `axlNewSetupDBLCV` 自带"覆盖已有 setup db"的语义，必须先取得授权并做前像。

**4) 是否确实需要用户人工打开 ADE？**
**不是前提**（standalone 有文档 + banner 实证）。人工打开 ADE 只是"获得一个 setup view"的可能途径之一。
是否必需：NOT_VERIFIED。

**5) 下一次最小、可逆的测试应是什么？**
一条**只读**调用，按本机文档的形状写：
```
axlSetMainSetupDBLCV(<session> "microled_cells" "c2mos_dff_tb" "adexl" ?mode "r")
```
放在一次性 IL 里、**不包 errset**，这样返回值与（若有）错误文本同时到手，能一次区分 (a)(b)(c)：
- 若返回句柄 → 之前失败就是参数语义问题（且不需要建任何 view）；
- 若打印"没有 setup db / 视图不存在"类错误 → 是 (b)，下一步才讨论"要不要创建 setup view"；
- 若报许可/未初始化 → 是 (c)。
配套只读读数（都属 `axlGet*`，不写）：`axlGetMainSetupDB(sess)`（上一轮答 `(0)`）、`axlSetupStates(sess)`、
`axlNoSession()`、`axlSessionSignalList(sess)`。
`?mode "r"` 的只读性质来自文档示例；它对库的实际影响在**本机**未实测：NOT_VERIFIED —— 所以这一条
仍应作为"需要授权的最小写风险步骤"报备，而不是我自己默认执行。

**6) 哪些操作会触碰 OA 或 ADE 状态？**
- 会写：`axlNewSetupDBLCV`（建 + 覆盖 setup db）、`axlSaveSetup`、`axlCommitSetupDB`、`axlCommitSetupDBas`、
  `axlSaveSetupToLib`、`axlMainAppSaveSetup`、`axlPutTest`、`axlAddOutputSignal/axlAddOutputExpr`、
  `axlPutModel/axlSetModelFile/axlSetModelSection`、`axlSetEnabled`、`axlRunSimulation`（写 netlist+raw），
  以及 GUI 里的 Save/Setup 保存。
- 只读（本轮判读）：`axlCreateSession`、`?mode "r"` 绑定、`axlGet*` 一族、`ddGetObj`、
  `dbOpenCellViewByType(..., "r")`、`schCheck`、`dbGet`。

**7) 哪些结论仍需人工确认？**
- ADE XL 在本机是否被正确许可（§F）。
- 传 `"adexl"` + `?mode "r"` 的真实返回与错误文本（§5）。
- 若必须先建 setup view：用 SKILL 建、还是在 GUI 里由人保存一次更省事；以及建在哪个 view 上才符合本机约定。
- `terms=0` 与原生网表的关系（依旧未触及，仍是 NOT_VERIFIED）。

---

## 5. 只读性质与副作用复核

```
md5_failures=0                      # microled_cells 全部 36 个文件与基线逐字节相同
0355c086721b51254998f045b87209b8    c2mos_dff_tb/schematic/sch.oa
3de3224df0af59d8ba9953357f1dbe88    c2mos_dff_1bit/schematic/sch.oa
locks_in_lib=0   analoglib_new=0   pdk_new=0   virtuoso_pids=（空）
```
本轮只新增：本报告、`results/evidence/c2mos_ade_binding_reaudit.txt`、以及对上一轮报告顶部
一段**带标注的更正**（原文保留以便追溯）。guest 侧仅 `/tmp/tb_audit/` 下的读取产物；未清任何锁文件。

## 6. 遗留（未变）

上一轮记录的 3 个 `cadence_work/logs/*.log.cdslck`（我方超时/关闭会话留下的**日志锁**）仍在，按禁止项未清理。
`c2mos_tb_build.py` 的 A/B/C/D 四项整改仍未做。
