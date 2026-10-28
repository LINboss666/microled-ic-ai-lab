# DATA-7C-B-TR 独立复审：REWORK

日期：2026-10-27（Asia/Shanghai）。本次结论是修补证据与验证工具；不要求改变电路，也不要求再跑九组原生仿真。

```text
REVIEW_RECOMMENDATION=REWORK
BASE_SHA=61621f6e3d887082ecd6a7ecc1c771f8e509a24a
CONTENT_SHA=f49ba9d78190f8c3da2adca9dbd4fb3e48d26841
DELIVERY_TIP_SHA=398c9e852c16db85cbfa4539e859534e117ff0d2
TABLE_ARITHMETIC_RECOUNT=209/209_PASS
REVIEWER_DEFECT_PROBES=9/9_REPRODUCED
RAW_WAVEFORM_REINTEGRATION=NOT_VERIFIED
ACCEPTANCE_REGISTERED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
REVIEWER_SPECTRE_LAUNCHES=0
REVIEWER_RTL_SIMULATIONS=0
REVIEWER_GUEST_CONNECTIONS=0
REVIEWER_OA_ACCESS=0
```

## 1. 复审实际取得了什么

网页端不能读取该私有仓库；本次改用现有 Git 通道 fetch，取得完整固定提交。独立 `git ls-remote` 读到：TR 分支为 `398c9e8…`，DC-R1 为 `61621f6…`，main 为 `23e471cb936b421ee97e1250c3be06edf96f9937`。没有声称审核方也独立走过 GitHub API。

全树 blob+mode 比较：BASE 的 2,935 个路径全部不变；tip 新增 89、修改 0、删除 0，新增字节 1,107,680。BASE..tip 为 8 枚提交。payload..tip 仅新增交付回执，父提交就是 f49ba9d。`git diff --check BASE..tip` rc=0。执行方的“87 文件 / 1,095,277 B”不是该最终提交区间的计数，需要在新报告分列口径。

归档任务书增加了来源前言；前言之后的正文与本会话正式批准文件逐字节相同，不是擅改任务。没有因为完整文件摘要不同而误判其正文漂移。

执行方本机 ZIP（375,053 B，声明摘要 `24de667280df3fd972144445aef31a47555649506532d794cf795fbd8f2862e1`）尚未上传，故本次不确认它的精确字节或成员。Git 内交付回执另记的是较早 f49ba9d 包（371,126 B、91 文件、另一摘要），两个归档身份应分别标注。

## 2. 已独立核对成立的进展

审核方读取了提交内 37 行窗口表、13 行收敛表、已接受 DC 原始 A 单位表和 9 份 DUT deck。独立 Decimal/PWL 复算 209 项全部通过：逐例固定 tick 和 QLSB、实际 deck 的 0.9 V 交叉、PAM 位序、名义/DC 目标、电荷误差、正负面积恒等式、逐窗收敛关联、deck 摘要，以及账本所载预检在 DUT 前结束。

这证明提交表格在这些关联上自洽，不能证明表中 Q 确实由原生采样正确积分所得。

四个动态超限窗口的表格复算结果：

| 窗口 | error_dynamic_LSB |
|---|---:|
| TR-OFFCODE W3 | -0.583518980605 |
| RS-SWITCH W3 | -0.582423831012 |
| HYB-120 W2 | -0.563928865408 |
| HYB-120 W3 | -0.542063361091 |

名义误差超限 14 窗，最大 +12.7233610002 LSB；收敛最大为 0.00121655155556 QLSB。它略高于回执“≤1.2e-3”的简写，仍远低于冻结的 0.01。原生电气负发现应保留，不能调宽判据或追改电路。

审核方实际调用了五个离线自测：contract 35/35、decks 19/19、trace 40/40、measure 51/51、run 27/27，全 rc=0。检查源码后确认本版 trace 自测只生成合成 VCD，没有启动 Icarus/vvp；交接所说该入口会启动仿真的文字已过期。本次对外部进程加了只许 Git 的审核护栏，原生/RTL 仿真均为零。

没有运行会重新发布证据并依赖本机 raw 的 record --gates/--selftest；它们不是当前 Git 提取物可完整重放的只读入口。history 闸实际 rc=0（227 commits / 3,025 objects，四类计数全 0）；provenance 实际 555 files / 559 labelled lines / 0 violations。没有对历史不可达对象执行 GC 或打印内容。

## 3. F1：缺少原生序列；198 项复算存在语义盲区（阻断）

任务 §9 要求交付可独立重算的原生 time/Iout/enable/PAM 序列，允许无损压缩。Git 只给窗口积分结果、节点均值与摘要；源码的 `record.package()` 额外装入的是两份 VCD gzip，没有原生电流序列的导出路径。完整 raw/log 留本机可以，但应另行输出无厂商内容的数值序列；“raw 不入包”并不免除这项要求。

`independent_recompute.py` 起点是已发布的 Q、目标 Q、tick 等结果列，并未重积分。审核方从当前 `recompute_source()` 原字节生成入口，原始表格得到 198/198 PASS；在副本上又实证三种错误各自仍 198/198 PASS：

1. 将所有 emission 的 `qtarget_dc_C` 改为该窗实测 Q、动态误差改 0、动态状态改 PASS。检查器没有回到已接受 DC 表乘 T50，错误 PASS 未被检出。
2. 将 TR-120 的参考 tick 改为 1000 ns，并同步 QLSB 与两误差列。检查器没有按固定案例映射回读 120 ns，仍通过。
3. 给第五条 RTL 账目补入自己的 executable 摘要和 rc，使其不能再算空白重复预订。入口仍固定使用 `len(rtl)-1`，继续认作四次。

需补齐：原生全精度数值序列、源/raw/deck/启动的身份链、从序列开始的独立积分与窗口关联；目标取冻结 DC、tick 取冻结案例；七种状态应重判内容，不能只查名字存在。禁止把自洽的伪造表格当成波形核验。

## 4. F2：占额记录仍可被旧实例覆盖；RTL 去重证据不足（阻断）

`run.Account.reserve()` 虽有锁，但在锁内没有重读盘中账本。审核方无需并行线程：A、B 依次从同一空账本初始化，上限 1；A reserve 成功，随后旧 B reserve 也成功，把 A 的已占额行覆盖为另一 case 的 T001，磁盘仍只剩 1 行。两次成功预约只能记下一次。属于任务 §6 明确要求防止的旧实例覆盖，正向上限自测没有覆盖此路。

应在锁内重读并验证实际磁盘状态；拒绝旧快照或用最新行追加，落盘失败保留旧账。原生重试输出也应带 launch_id：当前 Spectre `case_dir` 和本地 `run_id_case_role.raw/log` 按案例命名，同例重试仍能覆盖旧文件。不能以修过 RTL 日志命名来声称所有输出都不会再覆盖。

当前可直接核对的保守占额为主账本 19 条（含 T001 UNCERTAIN）+逃逸 2 次=21/24，余 3。22 是扣掉逃逸后的主账本上限，不能写成“22/24 已用、余3”。UNCERTAIN 不退额；这也不是审核方独立确认实际启动了21个进程。

RTL 有 5 条 REQUESTED/结算行，执行方称 R001/R002 为一次进程的双预订而计算 4 次。当前算法只凭同秒、同案例、某行无摘要/rc、另一行有目标摘要来判重复；这些条件不能证明第一条绝未启动。需补现存执行转录/日志等证据，或保留该计数为未独立证成。不得改写历史账本，不能靠给声明重复写一遍来完成证明；证据不可恢复则保守占额并如实报告预算边界，不能自行追认。

## 5. F3：Hybrid 检查只看宽度，漏掉起止相位（阻断）

`trace.check_frames()` 对普通非黑帧检查导通段数量和宽度，没有要求起点=t0、终点=t0+M*T。审核方用交付函数生成纯合成合法 VCD，正例转换通过；再将所有非黑普通帧的 data_en/data_en_b 同移 +10 ns，保持宽度、tick 和配置，`convert('HYB-200', …)` 仍接受并生成 PWL。三个普通发光帧都实际晚了10 ns，未被拒收。

需检查真实 consuming clk 沿与每个导通起止端点；安全帧还需逐点检查实际 fault 关闭、撤销后持续 tick、裸 START 确实发生且没有新 load/LATCH 授权。修复后只重读已存在的 VCD，不准重跑 RTL 掩盖此缺口。

该反例不表示本轮实际 VCD 已错相位；实际 VCD 尚在未上传包内。它证明当前放行规则不足以证成任务要求。

## 6. F4：原生导入缺校验，黑窗峰值不参与关断判决（阻断）

审核方编写格式完整、字段齐全的三点合成 PSF，正例能读取。只改一项后分别复现：

- 把 Ip_branch 的单位从 A 改成 V，`load_raw()` 仍接受。
- vdd18 全部设为 0 V，`load_raw()/observe()` 仍接受且宣称 finite=YES；没有与冻结供电或 PWL 逐点核对。
- 时间改为 0、2、1 ns，`load_raw()` 仍接受；observe 虽可标 monotonic=NO，却没有阻止导入/后续入口。积分基础函数可能另行拒绝该顺序，不能以此声称原生入口已拒收。

此外，`measure.statuses()` 的 SHUTOFF 只遍历 emission 行的尾段，完全不含三个 black 行。把黑窗的 peak/leak 改为 1 µA（限值150 nA），其净电荷为0，SHUTOFF 仍 PASS。黑窗的正负电流可以净积分抵消，不能因此通过关断。

需在数值使用前验证单位、严格递增时间、供电与逻辑输入、夹持/两端规则；坏输入明确拒收且不写正式输出。关断状态覆盖 emission 纯off尾和 black 64T/故障后黑窗的 max|I|。电气超限是有效 FAIL 结果；错单位/缺字段/错时间轴是证据拒收，两者分开。

## 7. 需要同时收口的解释与记录

延迟归因的 `newly` 用“本次支路数减上一个发光窗支路数”计算，并只取第一个新支路；但两个发光窗之间 DATA_EN 已关断，之前选中的支路也会再次开启。111→111 安全窗和100→000窗被记为 NO_NEW_BRANCH，不能据此判断没有译码/偏置开启过程。选中多支路时只看第一条的交叉也不能排除最后一条支路较迟。

修补时从已存内部原生序列读取每次上升时实际参与的所有支路，或把结论限定为“已观察节点的若干阈值先过、电流随后建立”；缺少器件OP/干预实验不能把时间先后写成已排除所有译码与偏置因素的因果签核。不改管宽或参考支路。

遗失的逃逸 raw 和覆盖日志只能保留事件说明，不能补造。历史 DATA-7B 超支、凭据事件、不可达对象均未由本复审解除。登记、合并与下一原生阶段仍未获授权。

## 8. 一轮离线修补即可；不为电气 FAIL 重跑

配套 `TASK_DATA7C_B_TR_R1.md` 把四组修补和证据补齐合为一个任务：新增 Spectre=0、vvp=0、OA=0、SSH/guest=0；本机只读重提取已保存 raw/VCD，发布新目录，旧记录/账本/deck/DUT 全保留。若缺序列无法恢复，明确 PARTIAL，不启动新仿真、不改旧结果追 PASS。

审核证据为 `checks/probe_tr_review_gaps.json`（9条反例及正例）、`checks/independent_table_recount.json`（209项）和五份自测日志。反例均在副本或合成输入中运行，未改交付源码和跟踪证据。

审核方自身有一处脚本错误：Decimal复算脚本最初 `max(generator,key=…)` 未给生成式加括号，编译期 SyntaxError，未产生数值结论；修正后才得到209/209。该失败不计入执行方缺陷，也未把失败运行冒充通过。
