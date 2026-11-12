# DATA-7C-B-TR-R2 交付回执（包外，非自指）

日期：2026-11-12，Asia/Shanghai。本回执写在审核包**外部**；包内不含本回执或其摘要。

## 固定 SHA 与包

```text
PAYLOAD_SHA        ff95b20ff08abe14f1b359c41e969bdb8116e134
PAYLOAD_BRANCH     poc/data-pam-d7c-b-tr-r2
BASE_SHA           ec107af502b729225e49428e4d2d72bffc389dae
DELIVERED_ZIP      review/dd1_d7c_b_tr_r2_package_ff95b20_v3.zip
ZIP_BYTES          24,001,519
ZIP_SHA256         402330e9a079ae4736f426b16e0f5c1fcd3fdedbedc04edf83035476a8bb1155
ZIP_MEMBERS        381 (379 manifest rows + PACKAGE_README.md + package_manifest.csv)
ZIP_CRC            PASS
```

包内所有可跟踪成员都是 `PAYLOAD_SHA` 那一提交的字节（`git archive` 生成），不是未提交字节。`independent_recompute.py`（63,484 B，来自 payload 的复算器原字节）、两份真实 VCD、README 与清单是明确标注的非 Git 附加物。

本回执是「仅回执提交」的唯一内容。它**不写自己的 commit SHA**（自指会改变树、形成无限回执循环）；推送后的分支 tip 与远端回读另记于 `remote_readback.json`，随本对话回传，不以本地 `rev-parse` 冒充第二路远端来源。

## 被取代但保留的包（不覆盖）

| 包 | SHA-256 | 结束它的具体缺陷 |
|---|---|---|
| `dd1_d7c_b_tr_r2_package_ff95b20.zip` | `173cba355e4b47793435e38f8b7c4e0ed5e021a5c1099f491a3257291b2c5a9c` | README 把 payload SHA 写成字面占位符 |
| `dd1_d7c_b_tr_r2_package_ff95b20_v2.zip` | `d594d74224f4466bf004e4569838e2b8c8787b7df5ad898d19c8f17969172033` | 打包闭包漏了 `tests/dd1_d7c_b_dc` 与 PREP/DC deck 目录，包内探针无法运行 |

三个包的被审字节完全相同，差别只在生成物（README、清单、闭包成员）；旧包全部保留。

## 包外真无 Git 回放（每条实际脚本路径与 rc）

解包目录 `D:/_r2_scratch/r20261112_144123_c4e480/package_outside_ff95b20_v3/package`，5 层祖先均无 `.git`；`git -C <包> rev-parse --show-toplevel` **rc=128**；子进程中的 `GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR/...` 定位覆盖已清除（只记录是否已清除，未打印环境值）。379 项清单逐字节 SHA-256 **0 不符**。

| 实际包内脚本绝对路径（相对包根） | rc | stdout 要点 |
|---|---:|---|
| `scripts/dd1_d7c_b_tr_r1_native.py --verify <R1 证据目录>` | **0** | `TR_R1_VERIFY 21/21 problems=0 excluded=4` |
| `independent_recompute.py . --inputs <R2>/r2_inputs.json` | **0** | `RECOMPUTE_R1 gate 841/841` |
| 同上两入口 + `sitecustomize` 拒绝任何 git 子进程 | **0 / 0** | 均仍成功，证明无隐藏 Git 依赖 |
| `scripts/dd1_d7c_b_tr_r2_probe.py <包根> <新输出目录>` | **0** | `R2_PROBE cases=18 passed=18 failed=0` |

写前拒绝：回放前后包内 381 个文件的「集合 + 逐文件 SHA-256」完全一致。证据：`package_outside_replay.json` 及 `outside_*_stdout/stderr.txt`。

## 修前对照与冻结面

- 修前真无 Git 原包：`--verify` **rc=1**（`git cat-file` 失败），`independent_recompute.py` **rc=0 838/838**。见 `prefix_reproduction.json`。
- 冻结面 3246 项逐 blob+mode 基线：3242 项完全一致、0 缺失、4 项改动（仅 4 个获准脚本）、20 个新输出文件。见 `frozen_tree_comparison.json`。历史 `--gates` 曾写回旧表并按 Git 字节还原的事实继续并列披露。
- 本轮 `BASE..PAYLOAD` 的 `git diff --check` rc=0；旧范围 rc=2 的尾空白作为历史事实保留，未清理。

## 结论口径（不宣称全绿）

B1/B2/B3/B5 修补完成并有干净与具名反例；B4 以诚实披露收口：`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、`BUDGET_ACCOUNTING_STATUS=PARTIAL`、保守占额 5/4 是风险口径，不是五次已证启动，也不追认 4 次。原 5 行账本未改。

动态 33/37、名义 23/37 电气 FAIL 保留；冻结 ±0.5 LSB 未改；4 个动态失败窗与最大名义误差 +12.723361000160 LSB 未变。260 条依赖本机 raw 的历史模块自测 **NOT_RUN**。旧 `838/838`、新 `841/841` 都只是检查器计数，不是电气合格或检查器完备的证明。预检语义重判限于单位、供电常量列与身份摘要，不扩展为物理 CDC/SOA 结论。

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
```
