# Virtuoso 原理图截图：`MANUAL_SCREENSHOT_REQUIRED`

状态：**`MANUAL_SCREENSHOT_REQUIRED`**（自动抓取在本 build 上不可行，需人工在 VMware 控制台截图）
任务号 `COURSE-MICROLED-SIM-20261112-R1` 第二阶段前的 R2 补证项 ｜ 2026-11-12

> 本文件**不是**截图替代品，也不允许把网表、VCD/CSV 渲染图或示意草图当作原理图截图。
> 它只说明：真实 OA 原理图确实存在、其电气连接已被只读回读证明，以及人工截图的最小步骤。

## 1. 本轮实测证据（真实运行，只读）

原始证据：`results/gui_attempt/gui_evidence.txt`（guest 侧 `oa/gui/gui_evidence.txt`）。

| 项 | 结果 |
|---|---|
| X display | `:0` 可用（Xorg 运行，`xdpyinfo` rc=0） |
| Virtuoso GUI 启动 | 成功；8 s 内到达延迟打开的 `GW-READY-FOR-MANUAL-CAPTURE` |
| X 窗口树 | 两个 `("Qt-subapplication" "Virtuoso")` 窗口：900×690+2+26、795×193+2+26 |
| `import -window root` | **221 字节**空白 PNG（SHA-256 `42126a9e…`） |
| `import -window <顶层 0x2e002ad>` | **177 字节**空白 PNG（SHA-256 `6be923b0…`） |
| 顶层子窗口 | 20 个，最大 640×480，均无类名 |
| 最大子窗口 `0x2e00471` | `Map State: IsUnMapped`；`import` 报 `Resource temporarily unavailable`（XImportImage/5037） |

结论：窗口对象存在且可枚举，但 Qt 顶层是容器、最大子窗口未映射，**像素抓取在本 build 上不可行**。
这与仓库既有实测记录 `skill/sc1_s3c3_gui_body.il` 完全一致，不是本轮新引入的问题。

## 2. 已能证明原理图存在的证据（无需截图）

- OA library `course_sim_20261112`（新建、独立、只写此库）。
- `course_sink_unit:schematic`：7 个实例（`Mcas`/`Mout`/`Mref` = `smic18mmrf/n33`，`PIN0..3` = `basic/iopin`）、5 条网络、4 个端口、39 个图形。
- 逐端子连接（`dbAccess` 只读回读，`results/oa_evidence.txt` 与 `spectre/course_oa_readback2.il`）：
  - `Mref`：D→VB、G→VB、S→VSS、B→VSS
  - `Mout`：D→NODE_M、G→VB、S→VSS、B→VSS
  - `Mcas`：D→DATA_OUT、G→VCAS、S→NODE_M、B→VSS
  - `course_sink_top:schematic`：`Xdut` 实例，VB/VCAS/DATA_OUT/VSS 四端连接一致
- `course_sink_unit:symbol`：端口 `VB`/`VCAS`/`DATA_OUT`/`VSS`，方向 `inputOutput`。
- spiceIn 的 `Saved and closed` 与 `Spice In successfully created the schematic view` 日志行。

这些证明"OA 里有真实、已保存、连接正确的原理图"，但**不能替代**老师要求的软件界面截图。

## 3. 人工截图最小步骤（在 VMware 控制台，guest 桌面）

1. 打开 guest 桌面终端，执行：
   ```bash
   D=/root/qoder_ic617_sandbox/course_sim_20261112/oa
   cd "$D"
   export HOME="$D/home_gui"
   . /root/qoder_ic617_sandbox/bin/cad_env.sh
   virtuoso -log "$D/logs/gui_manual.log" &
   ```
   等待 CIW 出现（约 8–20 s）。
2. 在 CIW 菜单：`Tools → Library Manager`，打开库 `course_sim_20261112`，
   双击 `course_sink_unit` 的 `schematic`。
3. 需要截的 3 张图（每张都要能看到窗口标题栏或 CIW 作为身份标识）：
   - **图 1**：`course_sink_unit` 完整原理图，能看到 3 个 `n33`（Mref/Mout/Mcas）、4 个 iopin、
     网络标签 `VB`/`VCAS`/`DATA_OUT`/`NODE_M`/`VSS`。
   - **图 2**：任一 MOS 的 `Properties`（含 `l`/`w`/`model`），或 `Check and Save` 后 CIW 的
     检查消息（证明 Check&Save 通过）。
   - **图 3**：`course_sink_top` 原理图，能看到 `Xdut` 实例与四个端口连接。
4. 用桌面截图工具（`gnome-screenshot` 或 VMware 的 `VM → Capture Screen`）保存 PNG，
   建议命名 `course_sink_unit_schematic.png`、`course_sink_unit_props.png`、`course_sink_top.png`。
5. 把 PNG 放到仓库外目录（例如 `D:/ic617_course_sim_20261112_review/r2_manual_screenshots/`），
   并在 `REVIEW_README.md` 的人工截图登记表中填入文件名与 SHA-256。
6. 收尾：`kill %1`（或关闭 Virtuoso 窗口），不要修改任何 OA 对象。

## 4. 禁止事项

- 不得用 netlist、VCD/CSV 渲染图、手绘草图、截图编辑或拼接冒充原理图截图。
- 不得修改 PDK、既有 OA 库、`cds.lib`、techfile 或 license 配置。
- 不得为截图而改动 `course_sim_20261112` 中的任何已保存对象（只读打开即可）。
