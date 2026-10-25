# DATA-7C-B-DC：八档 PAM 单输出通道直流实测报告（停在独立复审闸）

## 1 身份与授权

| 项 | 值 |
|---|---|
| 任务 | `DATA-7C-B-DC`（任务书 `reports/tasks/DATA-7C-B-DC.md`，8,609 B 之外本轮为 13,213 B `4cb0e22b…`，与原件逐字节相同） |
| 登记的离线内容 | `e51c5320a28bd5043e21d08a0be97e9d5612cd16`（分支 `poc/data-pam-d7c-b-prep-r2`，复审建议 GO 的那份字节；登记见 `reports/reviews/DATA-7C-B-PREP-R2-GO/registration.json`） |
| 本轮分支 / 工作树 | `poc/data-pam-d7c-b-dc` / `D:\ic617_d7c_b_dc` |
| 授权 | 用户 2026-10-25 选择"批准 20 次，一跑到底"+"登记，限 PAM 候选与离线准备"；Spectre 上限 20 = 8 预检 + 8 DUT + 4 调试余量 |
| 实测判据来源 | `tests/dd1_d7c_b_prep/contract.json`（本轮冻结）之 `clamp`/`full_scale_absolute`/`eight_level_ratio`/`supplies`/`process_corner`；快照与漂移规则在 `tests/dd1_d7c_b_dc/contract.json` |
| 完成级别 | `NATIVE_PAM_DC_TT_MEASURED`（不超过此级别） |
| 成本 | Spectre 启动 16/20、RTL 0、瞬态 0、OA 0、凭据值记录 0、模型卡内容入库 0、PDK 绝对路径入库 0 |

## 2 复用而非重写

按 §3 读完必读源后，本轮只新增两个入口，不建通用 SPICE 解释器、不建事务发布框架、不复制旧额度：

* `scripts/dd1_d7c_b_dc_run.py`：派生运行副本、本轮专用账本、启动与取回、提取与判定、离线正反例族。
  端口方向标注的剥离、器件与端口序摘要、SSH/scp 通道与运行器应答解析全部调用已被接受的
  `scripts/dd1_d7b_run.py` 里的那几个函数（`strip_direction_annotations`、`device_digest`、
  `port_order_digest`、`DIRECTION_RE`、`Link`、`parse_runner`），psfascii 读取用 `scripts/sc1_read_psf.py`。
  该文件 `NEW_LAUNCH_GRANT = 0` 的启动入口与 56/59 的历史账户都没有被复用，也没有修改。
* `scripts/dd1_d7c_b_dc_matrix.py`：把提取的逐点行合并成 8×19 矩阵、独立复算判据、画两张图。
* `scripts/dd1_d7c_b_dc_record.py`：本轮记录表；不重命名旧轮次的门名，也不复制它们的记录框架。

## 3 模型身份与派生副本（只读核验，未花额度）

`results/evidence/dd1_d7c_b_dc_r20261026_015212_376554/model_identity.json`：四个模型
`n18/p18/n33/n33_dnw_4t_ckt` 在 deck 所引 `$QODER_PDK_LIB`（8,721 行、184 条相对 include）可达的树里
**各定义恰好一次**，`section tt` 存在；闭包用到的全部 W/L 都在卡的 lmin/lmax/wmin/wmax 之内。
模型卡里的数字没有写进仓库，只记判定结果与该文件的 sha256。

`spectre/dd1_d7c_b_dc/` 是生成物（`--emit`），`strip_account.json` 逐文件记录：六个 master 共剥离
**63 行**端口方向标注（4+2+20+22+6+9），剥离前后 `device_digest` 与 `port_order_digest` 全等，行数差
恰好等于剥离行数；八份 `.pre.scs` 预检副本各替换 **1 行** `Xdut` 为两行理想仪表负载、删除 **5 行**
`save Xdut…`，19 点夹持扫描、分析行、探针与显式 `Vss (vss 0) vsource dc=0` 与交付 deck 逐字节相同。

一个环境事实：guest 的 `spectre/pdk_local.env` 只有 `QODER_PDK_LIB/QODER_SMIC/QODER_TSV…` 四个键，
**没有** `QODER_NETLIST_DIR`，而交付 deck 的 include 用它。本轮没有去改那个 gitignore 的配置文件，
而是在运行载荷里显式导出它指向本轮 master 目录；执行器本身对未解析的 `${QODER_*}` 直接 rc=9 拒跑，
所以这条路径不可能被静默绕过。

## 4 方法与判据

八码在同一 data_out 通道上依次静态施加（`DATA_EN=1.8 V`、`pam0/1/2` 按权重 1/2/4、`Iref=15 µA` 注入
二极管连接参考节点，不用理想 VBIAS 替代），输出夹持 0.60–1.50 V 步 0.05 V 共 19 点，
`Ip_branch (clamp_node data_out) iprobe`，`I_sink = Ip_branch` 不取负不取绝对值。
主判据只作用于 1.20 V：满量程 14.25–15.75 µA、八码严格单调、共享 `Iunit_ref = I111/8` 且每档
`|Ik − (k+1)·Iunit_ref| ≤ 0.25·Iunit_ref`；绝对满量程与比例必须同时满足，归一化不能救整体偏小。
另按每码相对其 1.20 V 电流 ±5% 给包含 1.20 V 的**连续已测**区间、最低已验证点与相邻未通过点，不外推。

## 5 实测结果

判决：**PASS**，152 条唯一数据（8 码 × 19 点），全部来自原生输出。

<!-- BEGIN 7CBD_LADDER -->
<!-- END 7CBD_LADDER -->

满量程与共享单位：I111 = 15.382706 µA（带 14.25–15.75 µA ✓，相对 15 µA 目标 +2.55%），
`Iunit_ref = I111/8 = 1.922838 µA`，最大偏差 0.000000912 µA ≈ 0.0000005 个 Iunit_ref（限 0.25）。
名义阶梯是 `ESTIMATED_MIRROR_RATIO_ONLY` 的估算，实测比它整体高 2.55%——这正是本轮要测的量。

预检仪表见证（8 例逐条，非 DUT 结果）：19 点全部读 `clamp/80 kΩ`，在 1.20 V 点为 +15.000000 µA，
参考节点 0.750000 V，符号为正——探针方向与解析链在任何 DUT 数字被使用之前就被确认。

两张图由合并后的原生表绘制，轴标 V 与 µA：`figures/dc_iv_curves.svg`（八码 I–V 曲线）、
`figures/dc_ladder_at_1p20V.svg`（1.20 V 八档阶梯）。

## 6 闸与账本

<!-- BEGIN 7CBD_GATES -->
<!-- END 7CBD_GATES -->

<!-- BEGIN 7CBD_ACCOUNT -->
<!-- END 7CBD_ACCOUNT -->

账本 `launch_account.csv` 16 行 = 8 预检 + 8 DUT，D001…D016 无跳号，上限 20、余 4；
每次启动都先持久 `REQUESTED` 再进进程，失败不退额。D001 的 `state` 记为 FAILED 而 `rc=0`：那是
入口把运行器应答按整数比较造成的标签缺陷（进程本身成功，判据见
`D001_label_attestation.json`，行字节未改、原始 607 字节另存 `launch_account_as_first_written.csv`）。
紧随其后的那次调用在读表时崩溃——崩溃在 `reserve()` 之前，因此**没有起进程、没有花额度**。

## 7 冻结面与区间

<!-- BEGIN 7CBD_FROZEN -->
<!-- END 7CBD_FROZEN -->

<!-- BEGIN 7CBD_RANGES -->
<!-- END 7CBD_RANGES -->

被登记的离线内容之后，本轮真正改动的既有文件只有 §6 里那份复审点名要修的两个
（`scripts/dd1_d7c_b_prep_contract.py` 的 µA 换算与 `reports/dd1_d7c_b_prep_contract.md` 的重渲染）；
四份候选 DUT、15 份交付 deck、三张时序表、旧合同 JSON、共享工具与所有旧记录逐 blob 相同。

## 8 拒收与自证

`--selftest` 的 35 例全是离线合成、不起进程、不花额度：完美阶梯 PASS、整体减半的阶梯被绝对判据
判 FAIL 而比例判据仍 PASS（归一化救不了）、非单调被点名、负读数保持为负、缺点/重复点/无探针列/
无单位轴一律具名拒收、未授权调用在写任何文件之前拒、环境变量不能抬上限、失败仍占额、重开不退款、
被多余分隔符撕开的行读不回、带逗号的字段写不出、µA 列的渲染守卫。

## 9 本轮没有做也没有声称

未做瞬态、PWM/PAM 联合电荷、灰阶 LUT、完整 MOS 灰阶控制器、阵列、版图、SOA 评估；
`OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED`；`MERGE_PERFORMED=NO`；未推 `main`；未登记除
`e51c532…` 的 PAM 候选与离线准备之外的任何版本；不追认 DATA-7B 的 59/56 超量与凭据回显事件。
本轮的电压区间只说明"在这 19 个已测点上 ±5% 成立"，不等于 LED/电极的 RC 或 SOA 已验证。
原生语法只对**实际跑过的**派生 DC deck 得到确认，不外推到整个层级，也不外推到瞬态。

```text
TASK_ID=DATA-7C-B-DC
BASE_OFFLINE_CONTENT_SHA=e51c5320a28bd5043e21d08a0be97e9d5612cd16
SPECTRE_LIMIT=20
ACTUAL_SPECTRE_LAUNCHES=16
PAM_8LEVEL_DC_TT=PASS
COMPLETION_LEVEL=NATIVE_PAM_DC_TT_MEASURED
CANDIDATE_DUT_CHANGED=NO
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
PWM_PAM_TRANSIENT_INTEGRATION=NOT_RUN
GRAY_LUT=NOT_RUN
FULL_MOS_GRAY_CONTROLLER=NOT_RUN
OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED
SOA_SIGNOFF=NO
MERGE_PERFORMED=NO
NEXT_STAGE_AUTHORISED=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
