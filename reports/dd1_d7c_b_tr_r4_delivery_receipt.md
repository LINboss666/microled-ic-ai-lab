# DATA-7C-B-TR-R4 包外回放回执

日期：2026-11-12。

## 交付包

| 项目 | 值 |
|---|---|
| 文件 | `dd1_d7c_b_tr_r4_package_7163ac5.zip` |
| 大小 | 25,606,525 B |
| SHA-256 | `8faeaffd31dce26488fe045d0fc566e1fba60442524ddd7be3bdda2311447d0e` |
| ZIP 成员 | 694（692 行清单 + README + 清单自身） |
| 打包来源 | 提交 `7163ac5ddca674e575f21f455b6b9c429e46e1d6`，分支 `poc/data-pam-d7c-b-tr-r4` |

本回执在打包之后提交，**不包含在包内**。

## 包外真无 Git 回放

解包目录 `D:/_r4_scratch/outside_7163ac5/package`，自身与全部 3 层祖先均无 `.git`（`git rev-parse --show-toplevel` 返回 128）。清除全部 `GIT_*` 定位覆盖，只记录处理方式，不打印环境值。

| 入口 | rc | 实际输出 |
|---|---:|---|
| 包内清单逐项大小与 SHA | — | 692/692 吻合 |
| `scripts/dd1_d7c_b_tr_r1_native.py --verify <R1>` | 0 | `21/21 problems=0 excluded=4` |
| `independent_recompute.py . --inputs <r4_inputs.json>` | 0 | `RECOMPUTE_R1 gate 838/838` |
| 同上 verify，禁用 `git` 子进程 | 0 | 同上 |
| 同上 recompute，禁用 `git` 子进程 | 0 | `838/838` |
| 包内探针 `dd1_d7c_b_tr_r4_probe.py` | 0 | 3 项正控 rc=0，12 项反例全部具名拒收 |

回放前后包内 694 个文件集合与 SHA-256 完全一致。包内探针的 B4 memset 段仍标 `NOT_APPLICABLE`（工程模块按设计读对象库），B4 的三组断言在 Git 检出中完成并留证。

## 发布状态（已完成）

推送在通道恢复后一次成功，pre-push 全历史闸 PASS（3628 objects）。两个分支都是新建 ref，未触发任何强制推送：

| 分支 | 远端 SHA | 通道 |
|---|---|---|
| `poc/data-pam-d7c-b-tr-r3` | `073c0f3705eb55fba8f017cc9d2927a54b129f9a` | git 协议 + GitHub API 一致 |
| `poc/data-pam-d7c-b-tr-r4` | `fab174c45d21a741c35ef15e9a131901d8304ec0` | git 协议 + GitHub API 一致 |

六个冻结 ref 全部未动：`main` `23e471cb…`、`dc-r1` `61621f6e…`、`prep-r2` `e51c5320…`、`tr` `398c9e85…`、`tr-r1` `ec107af5…`、`tr-r2` `fc7ee7a5…`。回读记录：`D:/IC/MicroLED_R3_R4_remote_readback_20261112.json`（`VERDICT=PASS`）。

## 保留口径

`BUDGET_ACCOUNTING_STATUS=PARTIAL`、`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、保守 5/4 不变；动态 33/37、名义 23/37 电气 FAIL 与 ±0.5 LSB 阈值不变；检查器仍是 838 条；260 条历史模块自测未运行。多平台预检的时间线只判轨高与"至少一次平台"，HYB 的声明/交付平台数不一致已作为备注记录，未声称对齐。

本轮零 Spectre、零 RTL 编译/仿真、零 OA、零 guest、零 PDK/license/凭据读取；未合并、未登记接受、未自签 GO。

```text
PACKAGE_OUTSIDE_REPLAY=PASS
ORIGINAL_R4_ZIP_SHA256=8faeaffd31dce26488fe045d0fc566e1fba60442524ddd7be3bdda2311447d0e
PUSH_COMPLETED=YES
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
