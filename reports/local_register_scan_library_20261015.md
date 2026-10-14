# 本机任务：让桌面快捷方式的 Virtuoso 看见 microled_scan_s3c

起点 `9049f111d943e9b322f21e1fa059a932cac93207`（本地 = `git ls-remote` = `gh api`），工作树干净。
本轮只做库可见性：不重新导入、不重建、不改电路、不调用 Spectre/ngspice/preflight/工作点、不开自动截图会话。

## 实际入口与它读的库表（读，不按文件名猜）

* 桌面项 `/root/Desktop/Cadence-Virtuoso-MicroLED.desktop`：
  `Exec=/root/microled_ai_project/cadence_work/launch_virtuoso.sh`（TryExec 同）。
* 该 launcher 里 `CDS_LIB="$WORK/cds.lib"`，先 `cd "$WORK"`，再 `exec virtuoso -log "$LOG"`，**没有 `-cdslib` 参数**；
  环境只从 `/etc/env/virtuoso` 里取 export 行，从不执行那个包装（它以 `virtuoso&` 结尾）。
* 所以会话按 Cadence 的规则读 `/root/microled_ai_project/cadence_work/cds.lib` —— 与用户截图里
  “Library path file” 显示的那份是同一个文件。该文件原来有 5 条 `DEFINE`（cdsDefTechLib、basic、analogLib、
  smic18mmrf、microled_cells），**没有** `microled_scan_s3c`，也没有 INCLUDE 链。
* 这不矛盾：`scripts/sc1_s3c_setup.sh` 当时故意只往 `s3c_oa/cds.lib` 注册，所以隔离批处理会话一直可见。

## 库确实存在（注册前只读核实）

`/root/microled_ai_project/cadence_work/s3c_oa/microled_scan_s3c`，72 个文件，8 个设计 cell 各有
`schematic/master.tag` 与 `symbol/master.tag`，顶层 `sc1_scan_power_1ch_s3c` 的 `sch.oa` 31 316 B、
`symbol.oa` 23 180 B 都在盘上。没有重建任何东西。

## 改了什么（一条 DEFINE）

`scripts/sc1_libregister.sh`：先查目标库与顶层两个 view 是否在盘上，再查三种情况——同名同路径已注册就
不动、同名指向别的路径就报 CONFLICT 且不覆盖、都没有才备份后追加。

* 备份：`cadence_work/cds.lib.bak.20261015_libreg`（`cp -n`，只留本机，含机器路径不入 Git）。
* 追加前后：`DEFINE` 行数 5 → 6，`microled_scan_s3c` 命中 1 行；`diff -u 备份 当前` 只多出

  ```text
  +DEFINE microled_scan_s3c /root/microled_ai_project/cadence_work/s3c_oa/microled_scan_s3c
  ```

  （另加三行注释与一个空行）；库表 sha256 `4814524693c3…6f22` → `8792832803a3…6ede`。
* 幂等已实测：第二次运行输出 `ALREADY_REGISTERED … (no change made)`，sha 不变，无重复行。
* PDK、`microled_cells`、`data_sink_1ch`、用户手工 C²MOS、其他 DEFINE/INCLUDE 一字未改。

## 验证到哪一步

用与快捷方式同样的方式起会话（cwd=`cadence_work`、HOME=`/root`、读同一份 `cds.lib`，无 `-cdslib`），
headless `dbAccess -load skill/sc1_libcheck.il`：

* 注册前：`LC-LIB obj="NONE"`、`LC-LIB-NOT-RESOLVING`、`LIBCHECK: FAIL` —— 快捷方式会话确实看不见。
* 注册后：`LC-LIB "microled_scan_s3c" obj=t`，8 个 cell 的 schematic 与 symbol 全部只读打开成功，
  顶层 `schematic` shapes=29 instances=11 terminals=9、`symbol` shapes=31 terminals=9，与 S3C4 已提交回读
  （`sc1_s3c4_log_dump_symbols_after.txt` / `sc1_s3c4_log_pins_after_check.txt` 里同一组计数）一致。`LIBCHECK: PASS`。
* 写入范围核对：OA 库 72 个文件的 `path|sha256|bytes` 与 S3C4 收尾清单
  `sc1_s3c4_backup_inventory_after.csv` 逐行相同（`identical=True`），没有比本轮更晚的文件，写锁 0。

**注册已核实；用户界面待刷新。** 已经在运行的会话（含我为四张 AFTER 图留的 pid 38069）不会自动重读库表，
也不该由我往里投命令；下次从快捷方式启动就是修正后的同一份工程库表。要在现有 CIW 里立刻刷新，最短输入是：

```lisp
ddUpdateLibList()
ddGetObj("microled_scan_s3c")
```

然后在 Open File 的 Library 下拉里选 `microled_scan_s3c`，顶层为 `sc1_scan_power_1ch_s3c`。
本轮没有做、也不声称做任何目视/截图核对。

## 工具与边界

* 新增可复现小脚本：`scripts/sc1_libregister.sh`（注册 + 备份 + 幂等 + diff）、
  `scripts/sc1_libcheck.sh` 与 `skill/sc1_libcheck.il`（按快捷方式同一入口解析库表，判据是脚本自己打印的
  `LC-DONE resolved=t`，不是 rc=0 —— 实测 `dbAccess` 在 SKILL 加载报错时也返回 0）。
* 本轮踩到的 build 事实：这个 SKILL 里没有 `getenv`（`*Error* eval: undefined function - getenv`），
  取环境变量要用 `getshellenv`，且仍要用 `errset` 包住以免个别项缺失直接中断脚本。
* 未动 VM 电源/快照/.vmx/网络/license/全局 SSH；未删锁、未 kill 任何会话、未 GC/prune；
  共享库表未被整体覆盖，也没把隔离库表 INCLUDE 进来；凭据只在运行时使用、未回显未入库。
* 停止条件已满足：目标库已由快捷方式使用的有效工程库表解析。S4 不启动；`SOA_SIGNOFF=NO`、
  面板参数仍未定义。
