# C2MOS-ADE-READBIND-01 — ADE XL 单次只读绑定实验报告

任务 ID：`C2MOS-ADE-READBIND-01`（用户已批准本次受控实验）
Git Base SHA：`3c4bfbf19890ecbc7ca4f6c102c804f8e414e49a`（执行前独立回读，远端 == 本地，工作树 clean）
个人分支：`gexing321/scan-driver/c2mos-schematic`
原始证据：`results/evidence/c2mos_ade_readbind_once.txt`（SECTION A–E，逐字命令输出）
探针：`skill/c2mos_ade_readbind_once.il`

标注：**DIRECTLY_OBSERVED** ／ **DOCUMENTED** ／ **DERIVED** ／ **NOT_VERIFIED**

---

## 1. 实际执行时间

**DIRECTLY_OBSERVED**：guest `work-eda` 单次会话 `Mon Oct 12 20:23:16 → 20:26:16 CST 2026`
（会话启动 20:23:16；ADE XL banner 20:23:37；绑定错误 20:23:4x；20:26:16 是被 runner 自身 180 s 超时
SIGTERM 收走的时刻，见 §8）。**只执行一次，没有重试、没有换参数、没有去掉 `?mode "r"`。**

## 2. 实际 Git Base SHA

`3c4bfbf19890ecbc7ca4f6c102c804f8e414e49a`；`git fetch` 后 `ls-remote` 独立回读同一 SHA；
`main` 仍 `23e471cb…`；工作树 `nothing to commit`。没有覆盖任何他人成果。

## 3. Cadence 版本

**DIRECTLY_OBSERVED**（会话日志头）：
```
Program:       @(#)$CDS: virtuoso version 6.1.7-64b 11/09/2015 12:45 (sjfnl165) $
Sub version:   sub-version  IC6.1.7-64b.78  (64-bit addresses)
Command line:  /opt/IC617/tools/dfII/bin/64bit/virtuoso -nograph -log ... -restore ...il
```

## 4. SKILL 探针源代码

见 `skill/c2mos_ade_readbind_once.il`（全文也已逐字并入证据 SECTION B）。要点：
目标调用**不包 errset**；禁止清单实测计数全为 0
（`axlNewSetupDBLCV`/`axlPutTest`/`axlSetTestToolArgs`/`axlSetEnabled`/`axlCommitSetupDB`/
`axlRunSimulation`/`dbSave`/`load(` 各 0 次出现）。

## 5. 唯一目标调用

**DIRECTLY_OBSERVED**（探针 line 48，日志回显的参数）：
```
RB-TARGET library="microled_cells" cell="c2mos_dff_tb" view="adexl" mode="r" session="rb_once_session"
sdb = axlSetMainSetupDBLCV(created "microled_cells" "c2mos_dff_tb" "adexl" ?mode "r")
```

## 6. 原始返回值

**没有返回值到手。** `RB-RETURN-VALUE` 那一行从未打印：调用抛出 SKILL 错误，`load` 当场中止。
因此本轮**不能**报告"返回句柄"（情况 A），也**不能**报告"返回 nil"（情况 B）——
函数没有正常返回过。

## 7. 完整错误上下文

**DIRECTLY_OBSERVED**（会话日志 line 81–96，逐字）：
```
RB-BEGIN
RB-TARGET library="microled_cells" cell="c2mos_dff_tb" view="adexl" mode="r" session="rb_once_session"
# ADE XL session 'rb_once_session' started on Mon Oct 12 20:23:37 2026
RB-CREATE-SESSION "rb_once_session"
RB-STATE-BEFORE axlGetWindowSession=(nil) axlGetMainSetupDB=0 axlSetupStates=nil
*Error* ddGetObjWritePath: argument #1 should be a ddUserType (type template = "b") - nil
*Error* load: error while loading file - "/root/microled_ai_project/skill/c2mos_ade_readbind_once.il" at line 48
```
之后 `RB-STATE-AFTER` 与 `axlCloseSession` 未执行，进程空转至 runner 超时：
```
*WARNING* Process was terminated by USER with SIGTERM signal
```

判读（分类见 §8 之后）：`ddGetObjWritePath` 的第一个参数拿到的是 `nil`，
即**它要用的那个 dd 对象不存在**。结合阶段A实测——`c2mos_dff_tb` 只有 `schematic` 一个 view，
整个库/工程内不存在任何 `adexl`/setup view——这是 DIRECTLY_OBSERVED 的失败形状；
"因为 adexl view / setup database 不存在"是 **DERIVED**。

## 8. 运行器退出码

```
runner_exit=1
RESULT rc=124                # scripts/sch_virtuoso.sh 的 timeout 180s 触发
TOKEN_FOUND no               # ADE_RB_DONE 未出现（load 已中止）
SCH_VIRTUOSO: FAIL  log=cadence_work/logs/sch_nograph_20261012_202316.log
```

## 9–11. 执行前 / 后指纹与 PDK 对比

> **证据范围修正（REWORK 轮，见 `reports/c2mos_ade_readbind_once_correction.md`）**：本节原来写的
> `PDK_UNCHANGED: PASS` 与 `ANALOGLIB_UNCHANGED: PASS` **夸大了证明范围**。实际做过的只有：
> 设计库逐文件 sha256（FULL，成立）、PDK 的文件数/du/实验窗口内 mtime=0 + **仅 1 个**关键 model 文件哈希、
> analogLib 的文件数/mtime + **抽样 3 个** `data.dm`。因此正确结论是
> **`DUT_UNCHANGED: PASS`、`TB_UNCHANGED: PASS`、`PDK_UNCHANGED: PARTIAL`**；
> 全树内容一致性在实验窗口内属 **NOT_VERIFIED**（本轮事后建立的全树基线只能服务下一轮）。
> 同理，本文 §13 中"`.finesimXL_root` 是唯一新增物"仅指设计相关目录，未含 `home/`、`logs/` 下的运行文件。

**DIRECTLY_OBSERVED**，全部为 `sha256`：
```
microled_cells 文件数           before 36   after 36     diff BEFORE/AFTER: 空（逐字节一致）
DUT  c2mos_dff_1bit/schematic/sch.oa   37796 B  4c9c1658c3d67b06…dc167c   前后相同
TB   c2mos_dff_tb/schematic/sch.oa      31684 B  7ee683e8051271f6…c3f56b   前后相同
DUT_UNCHANGED: PASS    TB_UNCHANGED: PASS
PDK 文件数 3976→3976，du 176464→176464，运行时刻之后新增 0
PDK model sha256 fc8d321752f2bacf…dcf95f 前后相同 → PDK_UNCHANGED: PASS
analogLib 2628→2628，今日新增 0 → ANALOGLIB_UNCHANGED: PASS
```

## 12. 是否产生新 ADE View

**没有。** 执行后逐目录确认：`c2mos_dff_tb : schematic`（仍只有一个），`find` 全库全工程
没有任何 `adexl*`/`Ade*`/`maestro`/`config`/`*setup*` 目录出现。

## 13. 异常会话或锁 / 副作用清单

```
virtuoso_pids after = []          # 无残留进程
locks_in_lib = 0   locks_in_pdk = 0   # 库与 PDK 内没有锁；上一轮遗留的 3 个 logs/*.log.cdslck 未清理（按禁止项）
本次运行新增的只是会话运行文件（非设计数据）：
  cadence_work/.finesimXL_root         <- 空目录，ADE XL/仿真框架自建，0 个条目
  cadence_work/home/.cdsinit           <- runner 注入的一次性 init（每轮都会重写）
  cadence_work/home/.vnc-cds/work-eda:80.{pid,log}
  cadence_work/logs/sch_nograph_20261012_202316.{log,stdout}
```
`.finesimXL_root` 是本轮**唯一新出现的东西**，是空目录、不含设计数据，我没有删除它（自动修复不在授权内）。

---

## 14. 当前已确认结论

1. **DIRECTLY_OBSERVED**：按本机文档形状调用绑定（view=`"adexl"`、`?mode "r"`）时，
   Cadence 抛 `ddGetObjWritePath: argument #1 should be a ddUserType - nil` 并中止加载。
   函数没有正常返回，因此本轮结果分类是 **情况 E：`ADE_READBIND: ERROR`**。
2. **DERIVED（并有 §2/阶段A 的实测支撑）**：错误里的 `nil` 是"要绑定的目标 view/dd 对象"，
   而 `c2mos_dff_tb` 确实没有 `adexl` view，全工程也没有任何 setup database view。
   所以**最可能的实际阻塞就是 ADE Setup Database 缺失**（情况 C 的内容），
   不是窗口、不是 License、不是 API 不存在。
3. **DERIVED（重要新读数）**：把本轮与上一轮的失败形状对比，两者不同——
   * 上一轮 `view="schematic"`：**静默 nil，无任何错误文本**（view 存在，但里面没有 setup db）；
   * 本轮 `view="adexl"` + `?mode "r"`：**立即 dd 对象为 nil 的类型错误**（view 本身不存在）。
   两条独立读数共同指向"缺 setup database"，而不再支持"需要人工开 ADE 窗口"。
4. **DIRECTLY_OBSERVED**：`axlCreateSession` 在无窗口的批处理里确实建起会话
   （Cadence 自己的 banner：`# ADE XL session 'rb_once_session' started`），
   且 `axlGetWindowSession()` 为 `(nil)` 与之并存 → 窗口不是会话的前提（与 DOCUMENTED 的 standalone 一致）。
5. **DIRECTLY_OBSERVED / 值得警惕**：即使传 `?mode "r"`，内部代码仍然走到 `ddGetObjWritePath`
   （写路径解析）。本轮**实测没有产生任何 OA 写入**（§9–12），但因此不能把 `?mode "r"` 当成
   "绝对不会写"的保证 —— 这正是任务§三第 4 条要查的问题，现在答案是：**部分否定的证据**。
6. **本轮没有生成网表、没有跑 Spectre、没有创建 ADE Setup、没有修改 Testbench。**
   不得（也没有）宣布 `NATIVE_NETLIST: PASS` 或 `ADE_SIMULATION: PASS`。

## 15. 尚未验证（不得写成结论）

- 创建 setup database 之后绑定是否会成功：**NOT_VERIFIED**（需要写操作，本轮禁止）。
- ADE XL 产品许可证是否满足：**NOT_VERIFIED**（本轮没有出现许可错误，但会话日志里只有
  Virtuoso Framework License 一行，没有 ADE XL 许可读数）。
- `?mode "r"` 在"view 存在"的情况下是否会落笔写文件：**NOT_VERIFIED**（本轮在解析阶段就中止了）。
- 是否还叠加其它前置条件（例如必须存在 `config`/`maestro` view、或必须 GUI 建过一次 setup）：**NOT_VERIFIED**。
- `terms=0` 与原生网表的关系：**NOT_VERIFIED**（未触及）。

## 16. 下一阶段建议与所需授权

**唯一建议的最小动作（需要明确授权，因为它会写库）：**
用 `axlNewSetupDBLCV("microled_cells", "c2mos_dff_tb", "<view>")` **在临时对象上**建立 setup database 后，
再跑一次同样的只读绑定，以便区分"缺 setup db"与"参数/许可"两类原因。
授权前必须讲清的三点风险（这也是我不自行执行的原因）：
1. 本机文档原文：`axlNewSetupDBLCV` **"automatically overwrites any existing setup db"** —— 覆盖语义；
2. 它会在 `microled_cells/c2mos_dff_tb` 下**新建 view 目录**，属于对设计库的写入；
3. 需要先做整目录前像（`tar cf`），回滚 = 删除该新增 view 目录，且必须验证 DUT/TB 的 `sch.oa`
   指纹不变（本轮已把基线 sha256 记录下来，可直接比对）。

如果不想写库，替代路径是**人工**：在真实 GUI 里打开 ADE 并对该 testbench 保存一次 setup，
然后再跑本轮这个只读探针做对照。两条路都需要你决定，我不会自行推进。

**STOP**：一次绑定实验已完成，按任务书第十四节立即停止，不进入创建 setup database、原生网表生成、
ADE 仿真、Testbench 修改或任何额外 Cadence 调查。
