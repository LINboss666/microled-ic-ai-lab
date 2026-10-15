# SCAN-UNIT-VIS-REGISTER-R1 -- 真实 Virtuoso 库注册核对（本轮未进入美化）

任务编号：`SCAN-UNIT-VIS-REGISTER-R1`（任务书内亦称 Gate-1 only 轮）
执行对象：本地 Qoder Agent，工作机 = 本 Windows 主机 + 其上的 RHEL6 guest `work-eda`
输入审查提交：`5b9b7f6a32edf483a428e48fa244b346e64544a0`（分支 `gexing321/scan-unit/1ch-beautify`，远端已回读同一 SHA）
冻结电路来源：`9049f111d943e9b322f21e1fa059a932cac93207`（HEAD 的祖先，已用 `git merge-base --is-ancestor` 证实）
本轮结论：**注册是对的，用户反馈最可能是"库名"问题；GUI 侧直接证据待用户回传；未做任何版式写入。**

---

## 0. 一句话回答"从仓库拉取的电路没有注册到 Virtuoso"

电路**不可能是"从仓库拉取后就绪"的**：`*.oa`、`cds.lib`、`cdsinfo.*`、`data.dm` 全部被 `.gitignore`
排除，仓库里只有六份冻结 Spectre 网表、四份黄金表、重建/核查脚本和上一轮运行日志。
而本轮实测：OA **确实在这台 guest 的盘上**，**确实已经注册进用户 GUI 所读的那份 `cds.lib`**，
一个只读会话**确实能打开全部 16 个 view**。

用户在这个 GUI 里看不到它，最可能的原因是**他找的名字不存在**：交付库叫 `sc1_s3c_team_pretty`，
而源端那台机器的库叫 `microled_scan_s3c` —— 后者在这台 guest 上 `find` 全盘**一个都没有**，也不在
Git 里；用户自己日常用的 `microled_cells` 里也**一个 scan cell 都没有**（`grep -iE "sc1|scan|bank|level|r3"`
→ `NONE`）。所以"按老名字找 → 找不到 → 判定没注册"与"其实注册好了"这两件事同时为真。

这条判断里，**"不存在/不在" 的部分是 DIRECTLY_VERIFIED；"用户当时搜的是哪个名字" 是推断**。
所以 `USER_GUI_VISIBILITY` 不写 PASS，写 `WAITING_USER`，见 §4。

---

## 1. 闸门状态矩阵（逐项，不打包成整体 PASS）

| 闸门 | 状态 | 证据落点 |
| --- | --- | --- |
| SOURCE_IDENTITY | **PASS** | `sc1_unit_r1_gate0_inventory.txt` §A：HEAD/父提交/远端 SHA/`9049f11..HEAD` 19 文件清单 |
| GUEST_IDENTITY | **PASS** | 同上 §B：`/proc/15224/cwd`、`cmdline`、`environ`、快捷方式 `Exec` 行、`launch_virtuoso.sh` 尾行 |
| OA_ON_DISK | **PASS** | 同上 §D：8 cell × 2 view（17 个 `.oa`），755，库内 0 个 `.cdslck`，PDK 目录存在 |
| CDS_LIB_REGISTRATION | **PASS** | 同上 §C + `sc1_unit_r1_registration_idempotency.txt`：唯一 DEFINE、路径有效、`7→7`、`OTHER_DEFS_INTACT=6/6`、sha 不变 |
| USER_GUI_VISIBILITY | **WAITING_USER** | `gui_vs_headless_visibility.md` §4：该会话日志内 `sc1_s3c_team_pretty` 出现 **0** 次；未向其注入命令 |
| GATE1_HEADLESS_VISIBLE | **PASS** | `sc1_unit_r1_libvis_remeasure.txt`：今日 21:19 重跑 `views_opened=16 of 16` + `LIBVIS: PASS` |
| ELECTRICAL_EQUIVALENCE_BEFORE | **NOT_RUN（沿用上一轮证据）** | 本轮未重跑 `sc1_s3c_readback.il` + `sc1_s3c_verify_oa.py`；旧 PASS 记为 `PREVIOUS_EVIDENCE`，见 §5 |
| PRESENTATION | **NOT_STARTED** | 未创建副本库，未移动任何 pin/figure；本轮明确不进入 Gate 2 |
| ELECTRICAL_EQUIVALENCE_AFTER | **NOT_RUN** | 无写入，故无 after；不许用"未改动"冒充"等价已复核" |
| VISUAL_REVIEW | **WAITING_USER** | 本机无像素通路；§4 给人工 8 cell 查看清单 |
| SECURITY_GATE | **PASS** | `sc1_unit_r1_handoff_validation.txt` §2/§3/§4：staged `objects_checked=6` 四类计数全 0；history `148 commits / 1332 blobs` 四类全 0；`provenance_check files=378 labelled_lines=506 violations=0`；反向用例（5 份变异 manifest + 12 条禁用路径 + 合成 model/license/password 内容块）全部被拒 |
| REMOTE_REF_VERIFIED | **PASS** | 同上 §5：`git ls-remote --heads origin` 回读 `gexing321/scan-unit/vis-register-r1` = `64c6b5e05646fae796e1399480436d669fa7a0af`；Gate 0 写前读过的 5 个 ref 逐字未变（另 5 个仅写后读到，按弱证据陈述） |

按任务书 §5 末段要求的分开写法：`GUI_LIBRARY_REGISTRATION=PASS`、`OA_IMPORT=PREEXISTING_CONFIRMED`、
`ELECTRICAL_EQUIVALENCE=PREVIOUS_EVIDENCE`、`PRESENTATION=NOT_DONE`。**不写整体 PASS。**

---

## 2. 四层拆分（Git / 磁盘 / 库表 / 运行时），逐库 TRUE 或 FALSE

| | `microled_cells` | `microled_scan_s3c` | `sc1_s3c_team_pretty` |
| --- | --- | --- | --- |
| Git 可见（OA 随仓库） | FALSE | FALSE | FALSE |
| OA 磁盘存在 | TRUE | **FALSE（全盘 `find` 无此目录）** | TRUE |
| 当前 `cds.lib` 有 DEFINE | TRUE（第 7 行） | FALSE | TRUE（第 11 行，唯一） |
| 运行时可解析 | TRUE（用户会话正在用它） | 不适用 | headless TRUE / **GUI 待用户确认** |

关键时序（决定诊断方向）：注册写入 `02:31:59` **早于** GUI 启动 `11:34:09`。运行中的会话不会重读库表，
但这个会话启动时那一行已经在文件里了，所以"缓存陈旧"被实测排除，而不是被论证排除。

## 3. 只读排查中顺带确认的既有缺陷（只报告，一律没修）

1. `cadence_work/s3c_oa/cds.lib`（隔离库表，GUI 不读）把 `sc1_s3c_team_pretty` **DEFINE 了两遍**，路径相同。
   产出者是 `scripts/sc1_s3c_setup.sh`。不影响用户可见性，但生成物不该有重复行。
2. `skill/sc1_s3c1_apply_dirs.il:31` 的行数守卫在本 build 里仍然只是装饰：`cdr` 未绑定，日志里
   `S3C1D-REFUSE the table has 0 rows, not the 48 declared ports` 之后紧跟八条成功的 `S3C1D-SAVE`。
   任何后续轮次若要用它，必须先在任务私有副本里做"空表真拒绝 + 48 行正反用例 + 真非零退出"，
   在那之前**不得把它的正常退出当作方向核查证据**。
3. 用户 GUI 日志第 95 行 `WARNING (TECH-2000152): … 'tsmc18' for design library 'microled_cells' was not found`
   —— 属于用户自有库的历史技术绑定，**与新库无关**，记下来防止被误挂到本轮交付上。
4. `/root/Desktop/cds.lib`（10-03，仅 5 个旧库）+ `libManager.log{,.1}` + 两个 `.cdslck` 是迁移前习惯的残留。
   如果有人仍在 Desktop 目录里起 Virtuoso，看到的就是那份 5 库列表 —— 这会精确复现"没注册"的表述。

## 4. 需要用户执行的最少量动作（十秒，只读）

先处理掉 ADE 的模态框（`Saving State -- ADE L (4)`、`spectre3: Save Results`），然后在 CIW 输入：

```skill
ddGetObj("sc1_s3c_team_pretty")
member("sc1_s3c_team_pretty" ddGetLibList()~>name)
```

- 第一行返回 `dd:0x…` → 库在这个会话的库表里且可解析；返回 `nil` → 不在。
- 第二行非 nil → 实时库列表含该库。若 `~>` 在本 build 抛错，等价写法：
  `member("sc1_s3c_team_pretty" setof(n ddGetLibList() n->name))`。
- **请把两行原样返回值贴回来**，不要只说"看到了/没看到"。两行结果互相矛盾时，保留矛盾上报，不要自行调和。

然后在 Library Manager 里按 **`sc1_s3c_team_pretty`** 这个名字找（不是 `microled_scan_s3c`，它在这台机器上不存在），
并按下面清单逐格打开 —— 本轮**不做外观判定**，只确认"能不能打开、端口在不在"：

| # | cell | 该看到的端口顺序 | 打开两个 view |
| --- | --- | --- | --- |
| 1 | `sc1_scan_power_1ch_s3c`（顶层） | `d clk blank core_ok33 scan vdd18 vdd33 vscan vss` | schematic + symbol |
| 2 | `sc1_r3_scan_chain_1ch` | `d clk blank core_ok33 gate33 vdd18 vdd33 vss` | schematic + symbol |
| 3 | `c2mos_dff` | `d clk q qbar vdd vss` | schematic + symbol |
| 4 | `sc1_scan_gate` | `qbar blank en vdd vss` | schematic + symbol |
| 5 | `sc1_ls_core_r2d` | `en x y vdd18 vdd33 vss` | schematic + symbol |
| 6 | `sc1_ls_c1_r2d` | `y core_ok33 gate33 vdd33 vss` | schematic + symbol |
| 7 | `sc1_ls_c1_top_r2d` | `en core_ok33 gate33 vdd18 vdd33 vss` | schematic + symbol |
| 8 | `sc1_s3b_p33_bank_7` | `scan bgate vscan` | schematic + symbol |

已知外观缺陷（**这就是下一轮 Gate 2 的活，本轮没动**）：所有 symbol 引脚都堆在符号右边缘
（x 1.1625–1.3375），没有本体轮廓，`text=nil` 即没有引脚名；叶层原理图仍是 spiceIn 默认摆放。
父图**不是**塌成 0x200 网格的（`Xbank` 在 x≈-0.06、`Xchain` 在 x≈3.06，已带 18/26/37 条 line 和 9–11 个标签），
不要再为这个不存在的毛病设计补救方案。

## 5. 电气等价的真实状态

本轮**没有**重跑图等价。上一轮在 `2ddf7a1` 的证据是：独立只读会话回读后
`scripts/sc1_s3c_verify_oa.py` 打印 `S3C_OA_GRAPH_EQUIVALENCE: PASS`，`failures=0`，
39 devices / 7 sub-instances / 48 schematic ports / 48 symbol terminals / 46 条连接 / 8 cell，
且负例对照真的触发过（`S3C_NEGATIVE rc_tampered=1 rc_intact=0`）。

本轮能补上的只有"没被动过"这一条间接证据：今日 21:19 重跑的 `LIBVIS` 与已入库的 02:42 记录
**shape/symTerms 全 16 项逐字相同**，`dbCheck=t`、`schCheck` 错误位 8 个全 0。这支持"基线仍是那份基线"，
但它不是图等价校验本身，所以矩阵里写 `NOT_RUN`、状态行写 `PREVIOUS_EVIDENCE`。
下一轮 Gate 2 的第 1 步必须按任务书 §4.1 重新实测 baseline，且验证器要显式传 `S3C_LIB=sc1_s3c_team_pretty`
（它默认值仍是 `microled_scan_s3c`），黄金阈值一字不改。

## 6. Git 与提交边界

- 账号：`gexing321`（author 与 branch 前缀即可辨识归属）；`git version 2.52/2.55` 两套并存，本轮用的是系统安装那套。
- 唯一个人任务分支：`gexing321/scan-unit/vis-register-r1`，基线 = 实际核实过的 `5b9b7f6`（不是 `2ddf7a1`，也从未指向队友 ref）。
- 护栏：`remote.origin.push = refs/heads/gexing321/*:refs/heads/gexing321/*`；push 一律显式单 ref refspec。
- 绝不触碰：`main`、`poc/scan-driver-1ch`、`feature/data-driver-virtuoso-schematic`、
  `feature/c2mos-virtuoso-schematic`、`poc/c2mos-dff`、`poc/data-driver-1ch`、
  以及原 `gexing321/scan-unit/1ch-beautify` 和 `gexing321/docs/collaborator-rules`（不同会话所有）。
  这些 ref 在 push 前后各做一次 `git ls-remote` 逐条比对。
- 无 force、无 tag push、无 `--all/--mirror/--delete`、无 amend/rebase 已推送历史、无 `--no-verify`。
- 本轮**只新增**：两份 handoff（`.md`/`.json`）、一份 `gui_vs_headless_visibility.md`、三份脱敏证据。
  不提交 `cds.lib` 本体、不提交 `.oa`/PDK/模型卡/许可证/私钥/raw PSF/机器库路径；`cds.lib` 由 `.gitignore` 兜住。
- 本轮 commit 链（全部在 `gexing321/scan-unit/vis-register-r1` 这一条新分支上）：
  - base（分支切出点，= 受审输入）`5b9b7f6a32edf483a428e48fa244b346e64544a0`
  - 交付提交 `64c6b5e05646fae796e1399480436d669fa7a0af`：6 files, 853 insertions，未修改任何既有文件
  - 回填提交：只改 `head_sha` / `push_status` / 远端回读 / 安全闸实参 / `HANDOFF_STRUCTURE` 一项，并新增
    `results/evidence/sc1_unit_r1_handoff_validation.txt`。**不预设其 SHA**，由
    `git ls-remote --heads origin refs/heads/gexing321/scan-unit/vis-register-r1` 与 `git rev-parse HEAD` 对照确认。
  - 交付提交已 `REMOTE_VERIFIED`（`ls-remote` 回读 = `64c6b5e0…`，回填提交回读 = `1ec505ee…` = 本地 HEAD）；
    第二次推送**先两次直连失败**（`Recv failure: Connection was reset`，随后 443 连接超时——其输出里那句
    `Everything up-to-date` 是传输已断之后的 sideband 残句，**不代表推送成功**），第三次用当次命令行代理才成功；
    全过程逐字存 `results/evidence/sc1_unit_r1_push_transport.txt`，结论只建立在推送之后的独立 `ls-remote` 回读上。
  - 远端审核入口
    `https://github.com/LINboss666/microled-ic-ai-lab/pull/new/gexing321/scan-unit/vis-register-r1`
    —— **PR 不由本 Agent 创建**，是否并入队长的分支是队长的决定。

## 7. 本轮明确没做的事

未创建副本库（不存在 `sc1_s3c_team_present_r1`）；未移动任何 symbol terminal 或引脚名；未改任何父图线端点；
未对 `sc1_s3c_team_pretty` 做过任何一次写打开（全部 mode `"r"`）；未向用户 PID 15224 会话注入任何命令；
未重启/关闭窗口/丢弃未保存工作；未删除任何 `.cdslck`；未动 `microled_cells` 与用户手工 DFF；
未跑 Spectre/ADE/新仿真；未做 layout/DRC/LVS/PEX/post-layout；未启动 Scan S4 或任务 #28 的任何内容。

## 8. STOP 与交回顺序

本轮停在 Gate 1：`USER_GUI_VISIBILITY = WAITING_USER`，按任务书"注册无法被用户日常 Virtuoso 实际看到时先 STOP，
不进入美化"执行，且用户已选择"只交注册核对报告，先进云端审核"。

交回顺序：① §0 + §4（用户 GUI 里到底可不可见、要他做的最小动作）；② 当前到 Gate 几 + §1 矩阵逐项；
③ 分支/base/head 全 SHA 与 `ls-remote` 独立回读 + 安全闸；④ 云端审核链接，**在 ChatGPT 审过并由用户 GO 之前不启动下一阶段**。
