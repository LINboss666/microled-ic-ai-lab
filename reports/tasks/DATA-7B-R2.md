# DATA-7B-R2：预算、时间测量与证据语义限定返修

2026-10-22。交付后停在独立复审闸。

**You have NO access to the user–ChatGPT conversation; this task, the supplied review files and the named repository are your sources.**

## 0 目标与零新增仿真

关闭`REVIEW_DATA7B_R1.md`第3–6节问题。保留现有电路、冻结电流样本与17份已生成的RTL VCD。正负积分修复、原8类篡改检出及主要电荷结果已有独立支持，不重新实现它们。

```text
TASK_ID=DATA-7B-R2
BASE_SHA=e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
HISTORICAL_SPECTRE_LAUNCHES=59
HISTORICAL_AUTHORISED_CEILING=56
HISTORICAL_BUDGET_OVERRUN=3
```

R1已经用满17次RTL仿真；本轮只重新解析现有VCD，不能再次调用iverilog/vvp。禁止原生preflight、spectre help、模拟重跑、OA/Virtuoso、PAM/LUT/阵列/版图/TCON、改PDK/许可证/VM配置/密码。不得改阈值、波形、码表、电路来使结论变绿。

## 1 固定源头与开工

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 被审R1 tip H / 本轮唯一base | `e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92` |
| R1 payload | `d13e251d2874a9a9942fa103ff7ead3c798b5b14` |
| DATA-7B原交付T | `adcdf27769fa2d4b9e42dc4f9c5f8310e17d8c50` |
| 原开发B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 已接受DATA-7A内容 | `f68449672774ac9266ba9e4893024e4f3027dd9d` |
| 新分支建议 | `poc/data-pwm-d7b-r2` |
| main（保持） | `23e471cb936b421ee97e1250c3be06edf96f9937` |

先Git/API双路回读H；访问失败如实记，不冒充第二路。读AGENTS、README、CONTRIBUTING_AI、原D7B/R1任务书、当前contract及三份主工具、本包审核/脚本/JSON。建独立worktree，从H开个人分支；不覆盖未知工作，不改旧分支。

先在H原字节的临时fixture中复现，再修改。审查探针会导入被审版本；只在相应checkout和临时目录执行，不能把篡改目标指向正式证据。

## 2 允许修改与冻结

允许修改三份主工具`dd1_d7b_run.py`、`dd1_d7b_measure.py`、`dd1_d7b_evidence_check.py`及必要的现有`dd1_d7b_r1_*`离线辅助；新增小型`dd1_d7b_r2_*`测试；新增R2任务书、修补报告和handoff；当前contract/report/handoff可加明确勘误。新证据放`results/evidence/dd1_d7b_r2_<unique_run_id>/`。

冻结：原开发B全部1,107路径；原D7B/R1任务书及既有授权记录；所有晶体管文件、wrapper、RTL、TB、trace/四态解析器、case/golden；整个旧`dd1_d7b_r11_main`和R1的`dd1_d7b_r1_r20261022_123825_8e1294`目录；已有共享安全、runner/preflight/supply、handoff结构验证器。

已发布的任何中间目录、原账本不删除、不覆盖。用新的唯一run_id/staging导出；失败保留明确状态。缺资料允许BLOCKED，不允许重新仿真补产生。不得GC、rewrite、force、跳hooks、merge或改变可见性。

## 3 预算来源与账本

### 3.1 把授权与证据声明分开

固定授权是任务书52加用户追加4，即56；历史59保持违规。复核器不得从账户第一行`ceiling`自行取得最终授权，也不能用environment的随意数字替代固定来源。检查所有声明相互一致，与固定56不符须有具名失败。

原样复现“账户上限改60→39项全PASS”，修后该副本必须因未授权上限被拒，BUDGET_RESPECTED仍按56判断失败。历史59/56的诚实原始证据应继续仅保留真实预算违规，而非被视为所有语义都错误。

本轮新增额度0是独立硬限制。native入口不能因用户传入不同`--seed-from`、新account文件或继承的RUN环境变量而恢复启动。生产入口关闭，算法的55/56等测试用隔离mock账运行。

### 3.2 预留、冻结历史与写盘

REQUESTED从预留写入即占额度；恢复为UNCERTAIN不能释放它。合成55/56账第一次reserve占到56，第二次必须拒；没有真实外部调用。状态转CONFIRMED/COMPLETED不重复收费，明确区分请求、确认执行与不确定。

历史H行与冻结seed事实逐字段绑定，不仅检查ID存在；改59条历史state为REFUSED、改role/run等均应拒。持久账户缺失、损坏或存在未完成写盘时不能默认为首次空账；明确恢复或失败关闭。

修复先remove再rename的写法。旧文件必须保留到替换成功；可捕获写入/rename失败不能造成下次读成空账户。采用当前运行平台可用的原子替换，或明确恢复/拒绝机制；无需另造庞大发布事务框架。过期实例不得覆盖其他实例新增的历史，可用单写者锁或版本/文件摘要校验后拒绝。

至少覆盖：REQUESTED连续预留、崩溃恢复、修改seed状态/角色、flush替换失败、重开保留行、两个过期实例、非法状态和跨run。注入失败仅在临时文件；不真实启动、不删除正式账本来测试。

## 4 修复时间测量及相应字段

### 4.1 deadline左侧完整性

关闭手算反例：电流0/10/20 ns为1，30 ns为0.5；带宽0.95–1.05，deadline25 ns，21 ns离带，所以NOT_SETTLED。应裁切/插值跨deadline的分段，检查其左侧极限；不能将最后一个带内样本延伸到截止点。保持10 ns及±5%原判据。

保留现有长短窗NOT_SETTLED结果及有限斜率事实；不移动deadline/扩大带宽。最长带内段可保留采样界定版本，但须与连续插值定义明确区分。

### 4.2 电压、电流与关断

data_en上升对应data_en_b下降；data_en下降对应data_en_b上升。按真实相位搜索互补节点相关沿，消除“短窗碰巧找到、长窗NOT_FOUND”。优先从当前包已有上升/下降沿邻域样本重算。

从完整电流序列和相关电压样本重算off_status、off_ns、turn_off_delay、段边界及电流10%/90%交叉和上升时间，验证方向、先后顺序、门限与脉冲对应关系。不以字符串合法替代数值绑定。

时间如采用首个合格采样点，需明确它是采样时刻并给夹持界；如采用插值，则按相邻点求阈值。不要把约3968.0376 ns采样点与约3967.86874 ns连续阈值当成同一精度的事实。

消除电流门限使用0.02 A容差的问题。电流与电压分别按SI单位处理；以相邻样本夹持/插值和已声明显示精度验证交叉时刻。不能用20 mA容差认证约15 µA信号，也不能通过放宽幅度/时间容差使旧表通过。

收敛表每个数值列都要重算，特别是delta_edge及限值、配对、判决。不能只用case行算一个布尔值，却允许表内delta_edge=9999 ns仍称CONVERGED。明确本轮被比较的是哪些物理量/节点，理想输入沿一致不自动证明全部模拟沿收敛。

## 5 VCD、CAL及语义复核

### 5.1 读取实际VCD

利用冻结trace解析器重新读取已交付17份`.vcd.txt`，验证四态、互补关系、冻结golden和输入沿/窗口。将重算得到的事实与rtl_reverify表、PWL、case时刻绑定；不能仅查摘要、日期、AGREE和字段数量。

清楚区分原生run的旧VCD摘要、R1重新仿真的原始CRLF摘要、交付LF字节摘要；解析交付字节不等于本轮又仿真。正例17份应能通过。将P30 code1的data_en高跳变改低并更新相关摘要后，必须在语义上拒绝，正如冻结解析器能拒绝它的互补关系。

### 5.2 缺少CAL的OFF/尾段必须显式处理

H中的CAL样本只有约2950.389–3749.889 ns。它足够重算3000–3500 ns均值，但1500–1900 ns基线和4400–4500 ns尾段均缺样本。不得继续用`if off`/`if tail`跳过空集合并输出“全部已重算”。

优先从本机已保留、摘要一致的原raw导出这些小片段及必要边界样本。必要时沿用R1授权，只读获取已知运行目录的已有raw；必须与离线测量入口分开，不隐式联网，不启动原生工具，不扫描其他目录/读取输出凭据。

交付小片段应有数量、范围、原raw摘要与案例身份；温度/section来源用必要的非专有字段摘录闭环，不上传模型卡/PDK/完整PSF。对标定均值按完整3.0–3.5 µs边界插值；记录1000内部样本及实际被积分时长，不能把499.5 ns内部跨度冒充完整500 ns。

若保留raw不可获取，按具体指标报告BLOCKED_MISSING_CAL_OFF/TAIL等状态；仍保留可重算的Ical、净电荷和VCD结果，不伪造数据、不把缺失判为成功。

### 5.3 正反例

保留R1原8类测试并在当前R2证据运行；补上本包7类语义破坏：未授权上限60、off时刻0、错误电流阈值采样点、互补节点时刻0、收敛沿差9999、实际VCD跳变破坏、无样本支撑的CAL基线值。每例重新封存manifest仍须触发对应新失败；已有预算FAIL或hash不一致不算检出该语义破坏。

每个需要来源的字段都读真实产物；校验缺文件、缺片段、NaN/Inf、重复/越界/非相对路径时明确拒收。发布前校验完整且可复算。电气FAIL如实导出与证据被破坏是两类状态；历史预算违规也单独保留。

## 6 证据与文档一致

H中实际账户209行=59 CONFIRMED+150 REFUSED_NO_LAUNCH；报告134/75是旧数。更正时引用本轮真实账户，保留H勘误，不手工照抄本任务数字当本轮结果。区分3个修改主工具与7条全部修改旧路径；26条冻结电流序列与1条新增CAL，不用`new_in_r1=27`暗示全是新采样。

旧包失败数、当前包名/路径、计数、状态、源摘要由一份固定的新结果集生成并机械核对。先完成代码和复算，再冻结证据、生成报告与handoff；需要元数据提交时逐条标清其身份。报告/JSON/清单不写自身摘要。

四个已删中间目录原字节不可得，不伪称恢复或原样重建；事件保留。凭据事件继续未解除，本任务不改密码，也不靠仓库扫描PASS宣称事件解除。已有本机已发布产物全部保留。

证据使用新目录，可按明确相对路径和固定摘要引用冻结样本，减少重复字节；审核包须带上可复核的冻结依赖或明确索引。新证据32 MiB上限不足时报告原因，不能删旧证据或悄悄减样本。

## 7 验证、提交与停止

1. 在H复现本包问题，保存原因/命令/rc。所有新测试均合成或离线，0真实Spectre、0新RTL仿真。
2. 运行测量手算、账户与I/O故障、原8类及新增7类语义测试、原冻结解析器现有VCD正反例、实际数据复算、发布拒收/正例。工具自己的结果不作黄金答案。
3. 核对冻结路径与两个旧证据目录全部blob不变，正式产物未被删除/覆盖；完整diff不得混入别的阶段。
4. 原safety/provenance/device-count、staged/history/objects及空白检查如实保留；既存不可达对象仍不GC/打印/豁免，不跳hooks。结构验证不替代语义复核。
5. 一枚功能/证据payload P2，再少量清楚的元数据提交D2；普通push新分支，Git/API双路回读；不移动main或旧分支。审核包从固定Git blob取字节，自检清单且带完整源码/任务/测试/证据依赖，不只放报告。
6. 同版字节的交接必须明确哪些修复通过、哪些缺raw阻塞，不能因为历史预算失败尚在而不检查其他问题，也不能声称全部PASS。

```text
TASK_ID=DATA-7B-R2
BASE_SHA=e97f02ecf7c84d1e1a3fda214cec8eceadfa5f92
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
HISTORICAL_SPECTRE_LAUNCHES=59
HISTORICAL_AUTHORISED_CEILING=56
HISTORICAL_BUDGET_OVERRUN=3
HISTORICAL_BUDGET_STATUS=VIOLATED_NOT_RETROACTIVELY_AUTHORISED
ACCOUNT_FIX_STATUS=<实测>
TIME_AND_CAL_FIX_STATUS=<实测或具体BLOCKED>
EVIDENCE_SEMANTIC_FIX_STATUS=<实测>
EXISTING_VCDS_REPARSED=<实测数>
CIRCUIT_RTL_TB_PWL_CHANGED=NO
FROZEN_EVIDENCE_CHANGED=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```

技术复审给限定建议，用户最终接受/合并与历史偏差处置权保留。不要为了“获得干净的一轮”再次仿真。
