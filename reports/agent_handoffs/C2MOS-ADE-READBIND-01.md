# Handoff — C2MOS-ADE-READBIND-01

| 字段 | 值 |
|---|---|
| TASK_ID | `C2MOS-ADE-READBIND-01` |
| BASE_SHA | `3c4bfbf19890ecbc7ca4f6c102c804f8e414e49a` |
| BRANCH | `gexing321/scan-driver/c2mos-schematic` |
| ADE_READBIND_RESULT | **`ADE_READBIND: ERROR`**（任务书情况 E） |
| 返回值 | 未取得（调用抛错，`load` 在 line 48 中止） |
| 原始错误 | `*Error* ddGetObjWritePath: argument #1 should be a ddUserType (type template = "b") - nil` |
| runner | `rc=124`（180 s 超时）/ `TOKEN_FOUND no` / wrapper exit 1 |
| DUT_UNCHANGED | **PASS**（sha256 `4c9c1658…dc167c` 前后相同） |
| TB_UNCHANGED | **PASS**（sha256 `7ee683e8…c3f56b` 前后相同；`microled_cells` 36 文件 diff 为空） |
| PDK_UNCHANGED | **PASS**（3976 文件、176464 KB、model sha256 `fc8d3217…dcf95f` 全同；analogLib 2628 文件全同） |
| 新 ADE View | 无（`c2mos_dff_tb` 仍只有 `schematic`） |
| 残留进程/锁 | 0 进程；库内 0 锁、PDK 0 锁 |
| STOP_REASON | `AWAITING_INDEPENDENT_REVIEW` |

## 一句话交接

按本机文档形状（view=`"adexl"`、`?mode "r"`）**只执行一次**绑定：Cadence 抛出
`ddGetObjWritePath … - nil` 并中止加载，**函数没有正常返回**，因此判为 **情况 E（ERROR）**；
结合阶段A的实测（该 cell 只有 `schematic`，全工程无任何 `adexl`/setup view），
最可能的实际条件是"**没有 ADE setup database 可绑**"（DERIVED，未由工具明文确认）。
上一轮"需要人工开 ADE 窗口"的说法不成立：`axlCreateSession` 在无窗口批处理里就起了会话
（Cadence banner 为证）。

与上一轮对比是本轮最有价值的新读数：

| 调用 view | 观察 | 含义（DERIVED） |
|---|---|---|
| `"schematic"`（上轮，包 errset） | 静默 nil，无错误文本 | view 存在，但里面没有 setup database |
| `"adexl"` + `?mode "r"`（本轮，不包 errset） | 立即 `ddUserType` 类型错误 | 该 view 根本不存在 |

两条互不支持的读数合起来指向同一个缺失对象，而不是许可、窗口或 API 缺失。
同时得到一条安全提醒：**`?mode "r"` 并没有阻止代码走到写路径解析**（`ddGetObjWritePath`），
本轮实测未产生任何写入，但不能把 `"r"` 当作"绝对不会写"的保证。

## 证据与复现

* 报告：`reports/c2mos_ade_readbind_once.md`（16 项全覆盖，标注 DIRECTLY_OBSERVED / DOCUMENTED / DERIVED / NOT_VERIFIED）
* 原始证据：`results/evidence/c2mos_ade_readbind_once.txt`（SECTION A–E：阶段A指纹与预检、探针源码逐字、会话日志关键行、阶段D完整复核、前后 sha256 清单）
* 探针：`skill/c2mos_ade_readbind_once.il`
* 复核命令（任何 reviewer 可重跑，结构校验与本轮一致）：

```
python -m json.tool reports/agent_handoffs/C2MOS-ADE-READBIND-01.json > null   # JSON 可解析
```
键存在性检查见报告；本轮实际执行输出为 `HANDOFF_STRUCTURE: PASS`。
**注意：`HANDOFF_STRUCTURE: PASS` 只代表交接件结构合法，不代表 Cadence 实验通过**（实验结论是 E/ERROR）。

## 未完成 / 需要授权

* 未生成原生网表、未跑 ADE 仿真、未创建 ADE Setup、未修改 Testbench（全部按禁止项）。
* 下一步唯一建议：建立 setup database 后重复本探针做对照 —— 需要明确授权，
  因为 `axlNewSetupDBLCV` 文档明写"automatically overwrites any existing setup db"，
  且会在 `microled_cells/c2mos_dff_tb` 下新建 view。要求：先 `tar` 前像，后跑 sha256 比对。
* 替代路径：人工在 GUI 里打开 ADE 并保存一次 setup，再跑本探针（只读对照）。
* ADE XL 产品许可仍是 NOT_VERIFIED（日志只有 Virtuoso Framework License 一行）。
