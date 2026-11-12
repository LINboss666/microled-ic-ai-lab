# DATA-7C-B-TR-R4 返工报告

日期：2026-11-12。本轮只处理 R3 复审剩下的三处，保留已通过的修补，仍停在独立复审闸。

## 1. 输入与身份

| 项目 | 固定值 |
|---|---|
| worktree | `D:/ic617_d7c_b_tr_r4` |
| 分支 | `poc/data-pam-d7c-b-tr-r4` |
| BASE | `073c0f3705eb55fba8f017cc9d2927a54b129f9a`（R3 本地 tip，未发布） |
| run_id | `r20261112_205452_5e09f7` |
| 新证据目录 | `results/evidence/dd1_d7c_b_tr_r4_20261112_205452_5e09f7` |

复审输入：`MicroLED_TR_R3_Independent_Review_REWORK_20261112.zip`（42,628 B，`6647bc84…`，24/24 清单吻合）。R3 原包 666 成员与 B5 已被复审独立确认，本轮不再论证包身份。

**R3 分支仍未发布**：推送通道持续 `CONNECT tunnel failed, response 502`，直连 `github.com:443` 超时；`gh api` 通道正常。R4 因此基于本地 R3 tip，远端 `poc/data-pam-d7c-b-tr-r3` 与 `-r4` 两个 ref 都还待创建。

## 2. B1：预检的仪表与刺激见证

`--verify` 新增 `_r2_witness`，用**解码后的实际列**对照冻结合同与冻结 deck：

- 仪表：`Ip_branch:i` 必须是单一平值且等于合同 `deck_rules.preflight.expected.clamp_current_A`（1.5e-05 A，容差 1e-6 相对）；该值同时与 `clamp_V / load_ohms`（1.2 V / 80 kΩ）互核。`iref_in` 终值必须等于 `reference_node_V`（0.75 V），并与 `iref_A × reference_ohms`（15 µA × 50 kΩ）互核。
- 刺激：`data_en` 必须到达冻结逻辑低与 deck 声明的 DATA_EN 高电平；平台沿由样本插值得到，与 deck 的 `platform (rise50/fall50)` 逐项比对（容差 0.5 ns，本机复现偏差 ~1e-12 ns）；单平台用例再按 `pam2pam1pam0` 位序在平台中点核对 `pam_sel`。

判定范围在输出里显式标注：单平台用例（TR-120、TR-200、RS-LOW）做完整的沿与位序比对；多平台用例只判轨高与"至少有一次平台"，并逐例打印 `TR_R1_VERIFY_NOTE` 说明该例声明了几个平台、实际交付几个沿。HYB-120/HYB-200 的 deck 声明 8 个平台而交付序列分别为 4/3 个沿，这个不一致**没有被判为通过**，而是被记成一条待解释的备注——本轮不声称 HYB 的多平台时间线已与 deck 对齐。

| 反例 | R4 实际拒收理由 |
|---|---|
| 电流全列改为 0 A | `the clamp current is 0.0 A against the frozen 1.4999999999999999e-05 A that the 1.2 V clamp over the 80000.0 ohm meter load draws` |
| 使能全列改为 0 V | `the stimulus witness never reaches the 1.8 V logic high, its highest sample is 0.0 V` |

## 3. B2：账本行与交付序列的身份绑定

两个入口都做绑定，而不是各自核自己的声明：

- `--verify`：定位包内唯一的 `spectre_launch_account.csv`（多于一个即拒收），按 `launch_id` 取行，要求 `state=CONFIRMED`、`case_id`/`role` 与序列头一致，并要求 `run_id`、`deck_sha256`、`raw_sha256`、`log_sha256` 四项与序列头逐字相同。
- `--recompute`：先按 18 个计划 `(case, role)` 各取确认行，再把每行的 `launch_id` 与四项摘要同该 `(case, role)` 的**交付序列头**比对。

| 反例 | 两个入口的实际结果 |
|---|---|
| T004 的 `raw_sha256` 改成 64 个 0 | verify：`raw_sha256 is '000…0' in the account against 'c8192192…' in the delivered preflight`；recompute：`the confirmed row T004 carries raw_sha256='000…0' while the delivered TR-120/preflight sequence records 'c8192192…'` |

## 4. B4：转录必须证明"只有一次启动"

R3 只核了文件存在、SHA 相符、正文点到两个行号，所以一份写着"两次不同启动"的转录仍能释放一次占额。现在 `duplicate_bookings()` 要求转录同时满足：

1. 文件存在，其 SHA-256 等于声明的 link 且等于见证行的 `log_sha256`；
2. 正文含 `NOT_STARTED <重复行号>` 的机器可读声明；
3. 正文对重复行**没有**任何启动证据（`started`/`launched`/`executed`/`spawned`/`pid=`/`rc=`）；
4. 正文对见证行**有**启动证据。

任一不成立即不释放，`record.derive_duplicates()` 仍返回空。真实五行账本没有 reconcile 文件，因此继续保守计数。

| 场景 | R4 实际结果 |
|---|---|
| 只填标签、无文件 | `duplicates=[]`、`processes=2` |
| 正文写"R001 started pid=101; R002 started pid=102; two distinct executions" | `duplicates=[]`、`processes=2`（不再释放） |
| 正文写 `NOT_STARTED R001` + `STARTED R002 pid=4242 rc=0` | `duplicates=['R001']`、`processes=1`（能力保留） |

## 5. 验证

| 项目 | 结果 |
|---|---|
| 干净 `--verify` | rc=0，`21/21 problems=0 excluded=4`，另有 6 条范围备注 |
| 禁止全部 subprocess 的 `--verify` | rc=0 |
| 干净复算 | rc=0，`RECOMPUTE_R1 gate 838/838` |
| 反例 | **14/14 具名拒收**（新增 B1 两项、B2 双向两项、B4 一项） |
| 冻结面 | 3306 项中 **3302 项逐 blob+mode 未变**；3 个获准脚本改动；1 项为探针改名；31 个新增文件 |

探针从 `dd1_d7c_b_tr_r3_probe.py` 改名为 `dd1_d7c_b_tr_r4_probe.py`（内容同时扩充），所以基线里记为 1 项缺失 + 1 项新增，而不是留一个名不副实的 r3 文件。

## 6. 保留与未做

- 真实电气结论未变：动态 33/37、名义 23/37 仍 FAIL，冻结 ±0.5 LSB 与全部窗口数值未改。
- 检查器仍是 838 条：本轮只加判定，没有新增计数记录。
- 零 Spectre、零 RTL 编译/仿真、零 OA、零 guest、零 PDK/license/凭据读取；未改旧证据、旧账、旧 ZIP；未合并、未登记接受。
- 260 条历史模块自测仍未运行：`selftest()` 会进入受护栏保护的 `launch()`。
- 已知未闭合的解释项：HYB 预检的 deck 平台声明数与交付沿数不一致，本轮只记录不解释，需在下一轮或由数据主人裁定。

```text
R4_VERDICT=AWAITING_INDEPENDENT_REVIEW
B1_INSTRUMENT_AND_STIMULUS_WITNESS=FIXED
B2_LEDGER_IDENTITY_BINDING=FIXED
B4_TRANSCRIPT_EVENT_SEMANTICS=FIXED
B5=FIXED_AND_CLOSED_BY_REVIEW
PUSH_STILL_BLOCKED=YES
NEW_SPECTRE_LAUNCHES=0
ACCEPTANCE_REGISTERED=NO
MERGE_PERFORMED=NO
```
