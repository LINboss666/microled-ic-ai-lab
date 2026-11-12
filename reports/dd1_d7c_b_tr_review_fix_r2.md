# DATA-7C-B-TR-R2 离线返工报告（B1–B5 一次收口）

日期：2026-11-12，Asia/Shanghai。本轮只修离线验证与结论口径；不是电路优化、不是原生阶段、不是接受登记。

## 1. 固定身份与授权

| 项 | 值 |
|---|---|
| TASK_ID | `DATA-7C-B-TR-R2` |
| BASE_SHA / BASE_TREE | `ec107af502b729225e49428e4d2d72bffc389dae` / `122e6c579390b03b3b414af63b8cd8d30233f199` |
| NEW_BRANCH | `poc/data-pam-d7c-b-tr-r2`（新 linked worktree `D:/ic617_d7c_b_tr_r2`） |
| run_id | `r20261112_144123_c4e480` |
| 新证据目录 | `results/evidence/dd1_d7c_b_tr_r2_20261112_144123_c4e480/` |
| 输入 | R2 任务包 60,756 B `e8f29029…`；内嵌 REWORK ZIP 44,551 B `67ca995b…`；补充复审 ZIP 22,515 B `5538d459…`；现成原审核包 23,729,459 B `b669632e…` |

任务包由用户于本对话转发并明确要求「按任务书执行（含 push）」。远端冻结 ref 在开工前只读回读全部一致；`poc/data-pam-d7c-b-tr-r2` 当时远端尚不存在。唯一任务所有者，不委派、不做结果合并。

## 2. 修前复现（作为修后对照）

- 真无 Git 环境：`D:/_r2_scratch/r20261112_144123_c4e480/prefix_no_git/original_package`，5 层祖先均无 `.git`；`git -C <包> rev-parse --show-toplevel` rc=128；清除 `GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR` 等定位覆盖（仅记录是否已清除，未打印环境值）。
- 原包 `scripts/dd1_d7c_b_tr_r1_native.py --verify <R1 证据目录>`：**rc=1**，traceback 落在 `dd1_d7c_b_tr_measure.py:33 → dd1_d7c_b_tr_contract.py:327/353/152/148/130`，`git cat-file blob 61621f6e…:spectre/dd1_d7c_b_prep/TR-LONG.scs` 报 `fatal: not a git repository`。与补充复审的独立复现一致。
- 同一目录 `independent_recompute.py`：**rc=0，`RECOMPUTE_R1 gate 838/838`**。这个数字只说明复算器能跑，不说明 `--verify` 可移植，也不说明检查器没有漏验。
- 原包回执的 `in-package replay rc=0` 继续作为历史执行方声明保留，未重写、未推测当时复用了哪个 Git 环境。
- 记录：`prefix_reproduction.json`、`prefix_verify_stderr.txt`、`prefix_recompute_stdout.txt`。

## 3. B1–B5 闭环表

| 阻断 | 修补 | 本轮证据 |
|---|---|---|
| B1 完整性漏验 | `native.py verify()` 重写：whole / parts / 冻结依赖 / 嵌套 `internal_fragment` 统一校长度与 SHA-256；分片编号连续且唯一；重接总长度与摘要；精确交付文件集合；拒未声明内容、缺片、重复身份、越界路径；9 份 preflight 从自身序列头与冻结电环境重判（单位、电流列、仿真器、deck/启动/raw/log 摘要、样本数、`vdd18/vss/vcas/clamp_node/data_out` 常量列），不复用旧 PASS 文本 | 干净 `21/21 problems=0 excluded=4`；8 个 B1 病例全部 rc=1 且具名拒收，含同步更新清单摘要的 preflight 单位语义突变 |
| B2 状态内容未重判 | `recompute.py` 新增精确十状态集合校验：拒缺/重/额外/非法 verdict/空值/NaN；verdict、measured、expected 全部从实际输入派生（37 窗、收敛表、序列清单、RTL 账户、两份 VCD 原字节）；BUDGET 行必须 PARTIAL 且分列 24/22/21 | 干净 `RECOMPUTE_R1 gate 841/841`；6 个 B2 病例具名拒收；新 `statuses.csv` 与 `status_diff.json` |
| B3 收敛键集合不完整 | 从任务书冻结表 + 契约 `convergence.pairs` 派生 13 个精确唯一 `(pair,refined,coarse,window,code)` 键；拒缺键/重复/未知 pair/空 context；核带符号 dQ = refined−coarse、QLSB = 1.875 µA×参考 tick、比值与逐窗 verdict，限值 0.01 不变 | 3 个 B3 病例具名拒收；正确集合与正确重排在干净输入通过 |
| B4 程序身份冒充进程身份 | `record.py derive_duplicates()` 与 `run.py Account.duplicate_bookings()` 去掉「同案例同秒/缺字段」弱推断，改为只认显式 `UNIQUE_START_TRANSCRIPT` 机械关联；standalone 出口 `rtl_process_finding()` 给出诚实结论 | 真实 5 行账本：`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、保守占额 5/4、原 5 行未改；4 个 mock 回归通过（同一 executable 两次仍计两次、UNCERTAIN 不自动扣减、无机械关联不扣减、有真实关联只去重一个预约） |
| B5 包内入口依赖 Git | `native.py` 把 5 个工程模块导入与 `TRC.contract()` 顶层调用收进 `load_engineering()`，只在 `--export/--budget/--selftest` 分支调用；`--verify` 只用标准库 + 包内清单/容器/冻结合同 | 包外真无 Git 目录从新包内部启动 `--verify` 与 `independent_recompute.py` 均 rc=0（见包外回执） |

B4 的完成方式是**如实披露并拒绝错误扣减**，不是证明「四次独立进程」。四个可执行摘要仍是程序身份；`BUDGET_ACCOUNTING_STATUS=PARTIAL`，不追认预算、不退款、不宣称剩余额度可用。

## 4. 新状态表口径修正

`status_diff.json` 逐行对照 R1/R2。电气数字、窗口、阈值、分母、冻结 DC 表与参考 tick **全部未改**。

| 状态 | R1 | R2 | 口径说明 |
|---|---|---|---|
| CONVERGENCE_STATUS | PASS 13/0 | PASS 13/13 | 13 个唯一键的「通过数/应有数」，不再是 13 行对一个 0 期望 |
| NATIVE_SEQUENCE_REINTEGRATION | PASS 835/835 | PASS 37/37 | 实际重积分的 37 窗；835 是工具内部检查条数，另列不作为自指证明 |
| BUDGET_ACCOUNTING_STATUS | PASS 21/24 | **PARTIAL** 21/24 | 分列 Spectre 总上限 24 / 主账上限 22 / 总占额 21；`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`；保守占额 5/4 是风险口径 |
| RTL_INPUT_PROVENANCE | PASS 2/2 | PASS 2/2 | 两份真实 VCD 解压 SHA-256 已实际核对；限定范围见补充复审的限制段，不证明历史进程完整登记 |
| DYNAMIC / NOMINAL | FAIL 33/37、23/37 | 不变 | 4 个动态失败窗与 14 个名义失败窗保留 |

动态 4 失败窗：TR-OFFCODE W3 `-0.583518980605`、RS-SWITCH W3 `-0.582423831012`、HYB-120 W2 `-0.563928865409` / W3 `-0.542063361091` LSB；最大名义误差 HYB-200 W2 `+12.723361000160` LSB。冻结 ±0.5 LSB 未改。

## 5. 验证与留证

- 探针 `scripts/dd1_d7c_b_tr_r2_probe.py`：在全新隔离副本上先跑干净双入口（rc=0），再一次只改一个事实；共 **18 例，18 例通过**（2 干净 + 16 反例），每例记录病例→突变→入口绝对路径→真实 rc→stdout/stderr→具名拒收词。缺文件/traceback 不算成功检出。结果 `counterexamples/counterexamples.json`。
- 干净复算 `RECOMPUTE_R1 gate 841/841` rc=0；干净 `--verify 21/21 problems=0 excluded=4` rc=0。两份 VCD 为具名未交付项，不计入验证成功。
- 冻结面：`frozen_baseline.txt` 逐 blob+mode 留 3246 项基线，`frozen_tree_comparison.json` 显示 **3242 项完全一致、0 缺失、4 项改动**（仅 `native.py` / `recompute.py` / `record.py` / `run.py`），20 个新文件全部为本轮输出。`OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO` 由这次逐字节比较支持；旧 `--gates` 曾写回旧表并按 Git 字节还原的历史事实继续披露，不用最终状态掩盖。
- 旧范围 `git diff --check` rc=2 的尾空白作为历史事实保留，未清理、未宣传全绿。
- 依赖本机 raw 的 260 条历史模块自测本轮 **NOT_RUN**（未恢复已删除 raw，不伪报 260/260）。

## 6. 未做与限制

零 Spectre、零 RTL 编译/仿真（含 -h/版本/语法预检）、零 OA、零 guest、零 PDK/license/凭据读取；未改 PDK、DUT、RTL、deck、原任务契约、六母本、18 份 deck 或旧账户；未合并、未登记接受、未 force、未跳 hook、未 GC、未删旧证据。两份 `.vcd.gz` 不在 Git 中（沿用原包口径，仅随新包携带并由报告记录解压 SHA-256）。

B4 未取得逐启动唯一进程日志，故停止追证，不重仿真、不新启动。预检语义重判覆盖单位、供电常量列与身份摘要，不扩展为物理 CDC/SOA 结论。R2 新状态表引用 BASE 的冻结序列与账户，未为新 prefix 重导出 32 MB 序列。

```text
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
TASK_ID=DATA-7C-B-TR-R2
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_COMPILATIONS=0
NEW_RTL_SIMULATIONS=0
NEW_OA_ACCESS=0
NEW_GUEST_CONNECTIONS=0
NEW_PDK_LICENSE_OR_CREDENTIAL_READS=0
CANDIDATE_DUT_CHANGED=NO
OLD_EVIDENCE_OR_ACCOUNT_CHANGED=NO
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN
BUDGET_ACCOUNTING_STATUS=PARTIAL
```
