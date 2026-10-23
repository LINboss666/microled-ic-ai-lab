# DATA-7C-A 交接（八档 PAM 单通道候选 MOS 与离线验证）

日期 2026-10-23。任务书逐字节副本 `reports/tasks/DATA-7C-A.md`（20,917 B，SHA-256
`3b55cef702da35786d68b533c0af363b4e6419d62acc2cd9d94ee7bf6051f180`）。
结构化字段在 `reports/agent_handoffs/DATA-7C-A.json`；本文件不写自身摘要，本轮 tip 从 Git ref 读。
上游：DATA-7B 已被独立复审给出**限定 GO** 并登记为接受版本 `f9fd09b184a69a27cdb409205dfd4f4151408a23`
（登记提交 `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683`，即本轮基线）。

## 1 身份

| 项 | 值 |
|---|---|
| 任务 / 基线 | `DATA-7C-A`，base = `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` |
| 分支 / 工作树 | `poc/data-pam-d7c-a`（本轮新建）/ `D:\ic617_d7c_a` |
| 范围 | `ONE_OUTPUT_EIGHT_LEVEL_PAM_CANDIDATE_MOS_AND_OFFLINE_VERIFICATION` |
| 完成级别 | `CANDIDATE_MOS_NETLIST_WITH_OFFLINE_CHECKS` |
| 档位状态 | `POC_CANDIDATE_NOT_FORMAL_SPEC`（八档实际电流仍 `NOT DEFINED`） |
| 文件范围 | 对 base **仅新增**：0 修改、0 删除 |
| 本轮成本 | Spectre **0**、RTL 仿真 **0**、OA 写入 **0**；未跑 `spectre -h`、无动态 preflight、无 SSH/VM、未读凭据 |
| 验证记录 | `results/evidence/dd1_d7c_a_r20261023_062341_cb1bd0/`（目录名在跑之前定下；`verification_summary.json` 的 `generated_utc` 才是真实生成时刻） |
| 停止状态 | `AWAITING_INDEPENDENT_REVIEW_OF_CANDIDATE_AND_TEST_PLAN` |

## 2 交付分层（不能用一句 `PAM_IMPLEMENTED=PASS` 吞掉）

| 层 | 状态 | 依据 |
|---|---|---|
| 候选 MOS 源设计 | **完成（文本层面）** | 5 个新 `.scs`：门单元、温度计译码、单位支路核、单输出顶层、bench 草稿 |
| 离线结构与逻辑验证 | **完成，22/22 PASS** | `scripts/dd1_d7c_a_offline_check.py`，反例 10/10 各自点名 |
| 原生网表语法 | **`NOT_VERIFIED`** | 本轮不允许任何仿真器调用，也不跑 `spectre -h`；层级 `save` 与 `type=pwl` 显式标未证 |
| 八档电流实测 | **`NOT_RUN`** | 15 例计划只写方案与判据口径，结果列全 `NOT_RUN` |
| PWM×PAM 电荷联合、灰阶 LUT、完整 MOS 灰阶控制器、光学有效位数 | **`NOT_RUN` / `NOT_VERIFIED`** | 见 `reports/dd1_d7c_a_native_test_plan.md` §5 |
| 是否被接受 | **未接受**，停在独立审核闸 | 审核方与用户决定；本轮不登记接受版、不合并、不授权下一阶段 |

## 3 候选 A 的语义（一句话 + 三条边界）

八条**相同**单位下拉支路，导通数 = `pam_sel + 1`，共享一只二极管连接 `Mref`（20 µm / 2 µm）与
15 µA 外部参考；单位 `Mout`/`Mcas` 取 2.5 µm / 2 µm，理想镜像 1:8 → 单位 1.875 µA、满档 15 µA。

- `DATA_EN=0` 时八条全关；码 000 是"一个单位亮"，**不是** 0 µA，黑色由时间码 0 或 `DATA_EN=0` 决定。
- 只有**一个** `data_out`：八条支路的 `DATA_OUT` 端子全部并到同一顶层净线（`ALL_BRANCHES_ON_COMMON_OUTPUT`）。
  这不是八个 LED 通道。
- `Mpass_local` 是 DNW 四端器件，体端接**本支路** `vbias_ch`（不是 VSS）；每条支路的 `vbias_ch`/`node_m`
  只在自己实例作用域内，顶层不出现这两个名字（`LOCAL_NODES_NOT_SHARED`、`DNW_PASS_BODY_LOCAL`）。

另外两个定义（二进制 1+2/4 加权四支路、常规 0…7 单位满档 15 µA）只在
`reports/dd1_d7c_a_pam_candidate.md` §2 比较权重、进位切换、匹配与偏置负载，**不搭网表、不混表**：
C 含 0 电流档、单位是 15/7 µA，与 A 的端点/步长/DNL 语义不同。

## 4 机读计数（全部由解析得到，不手填）

| 量 | 值 |
|---|---|
| 顶层展开 MOS | 145（`dd1_d7c_a_pam_1ch`） |
| 译码层 MOS | 112（`dd1_d7c_a_pam_dec`） |
| 单位支路核 | 4 × 8 = 32 |
| 共享参考 | 1（顶层计一次，不在支路重复） |
| 子电路实例 | 58 |
| 镜像比 | 8，`ESTIMATED_MIRROR_RATIO_ONLY` |
| 几何 | `GEOMETRY_NOT_VERIFIED`，未读 guest/PDK |

## 5 离线验证与反例

22 项检查 PASS（结构、端口数、重名实例、单输出、公共输出、局部节点不共享、DNW 体接法、
泄放管栅极、主通路 `DATA_OUT→Mcas→node_m→Mout→VSS`、16 行黄金温度计表、门级逻辑由晶体管的
上拉/下拉图解出、EN/EN_B 逐支路成对、镜像比、单位核与已接受核逐管同构、器件计数、
报告断言核对、请求拒收表、原生入口拒收、草稿无活动分析语句、用例表形状）。
10 项反例全部 HIT：位序错、阈值错一档、漏 `DATA_EN`、支路脱离公共输出、参考比例错、
DNW 体接 VSS、`EN_B` 接常量、子电路端口次序损坏、报告器件数过期、语法越界拒收。
规则是 `found == sorted(expected)` 且 `expected` 非空——`[] == []` 不算检出。

一项**不伪装成 PASS** 的记录：冻结工具 `scripts/netlist_stats.py` 只把总数与**单个** cell（默认 C2MOS 18）
比对，基线上已有 1 条既有失配；本轮把 11 条关于其它 cell 的断言如实记为
`INFORMATIONAL_NOT_PASS`，并给出推广版 `REPORT_CLAIM_COUNTS_MATCH`（由反例 E09 证明会失败）。

## 6 本轮操作记录

1. 动工前双路回读 `2026-10-23T05:47:21Z`（本机 UTC）：`ls-remote` 22 行 ref、`gh api` 逐 ref 读 5 条，
   `poc/data-pam-d7c-a` 尚不存在；base/main/R1/R2/D7B 全部核对一致。
2. 身份校验：`272d6de^ = f9fd09b`；登记轮差异 = 2 修改（交接）+ 5 新增（复审文档），
   `scripts/ results/ rtl/ tests/ spectre/` 出现 0 次。
3. 新建分支与隔离工作树，未删改任何同名目录/分支或旧分支。
4. 构建新工具过程中的自身缺陷（都在交付前修好并留下判据，不属已发布产物）：
   (a) 解析正则不容许行首缩进 → 已接受主文件被误判为"不支持语法"；
   (b) 层级展开把"子电路端口名"与"父层连线名"混为一谈 → 改为按端口映射解析全局净线身份；
   (c) 门级真值期望按位序写反（`_combos` 低位在前）→ 期望改为手写的逐输入组合表；
   (d) 单位核同构比较用全局净线名 → 内部节点带作用域前缀造成假失配 → 改为按角色（端口/局部名）比对；
   (e) 反例 E04/E06 的期望集合与真实连带失配不符 → E04 让主通路检查只看本支路 `DATA_OUT` 端子的
   解析身份（名称问题交给它自己的检查），E06 声明为两个具名检查的集合；
   (f) 渲染不收敛：E09 注入的对象正是本报告，若在报告里打印它的字节摘要就自指且每次渲染都变 →
   改为报告内不打印、完整摘要留在 `counterexamples.json`，固定点才成立。
5. 失败与阻塞：无。未用满 3 次修复上限的任何一项（每项一次改对并有判据）。

## 7 边界与继承待办

- 30/36 只是**草案**：15 例 × (DUT + 动态 preflight) = 30，另加 6 次调试余量；本轮 0 次启动，
  不借用也不重置 DATA-7B 的 56 次授权，历史 59/56 超支 3 次仍是违规，`BUDGET_RESPECTED` 继续 FAIL。
- 继承未修的三条 DATA-7B-R3 非阻断注记（用户决定留到下一轮维护）：
  审核包 README 口径、`dd1_d7b_r3_guards.py:253` 的空洞真与 `dd1_d7b_r3_verify.py:245` 只看 rc、
  提交数按回读时刻统计。本轮新工具直接按正确写法实现，不回头改已接受的字节。
- 回读出处区别：交接里"5 条 ref"是 `gh api` 逐对象查询，"22 行 ref"是 `ls-remote` 的全量行数，
  引用时必须写明是哪一个集合。
- 仍不做：PDK/模型卡/凭据读取、VM/SSH、合并、推 main、可见性变更、GC、历史重写、force、跳 hooks。
  凭据回显事件未解除；`SOA_SIGNOFF=NO`；`NEXT_NATIVE_STAGE_AUTHORISED=NO`。

## 8 下一步（等独立复审，不由执行者给 GO）

审核方需要判的不是"像不像方案"，而是：候选 A 的逐管说明是否与网表一致、温度计表是否真由
网表解出而非由表格倒推、15 µA 参考与 1:8 镜像的口径是否被正确标成估算、
反例集合是否真的非空点名、`netlist_stats` 那条是否被诚实记成 INFORMATIONAL 而非 PASS、
以及 30/36 草案是否可审。若通过，实际档位值、判决阈值、`Q` 归一方式与原生额度需另行冻结。
