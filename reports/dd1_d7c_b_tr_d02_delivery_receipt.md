# DATA-7C-B-TR-D02 包外回放回执

日期：2026-11-13。

## 交付包

| 项目 | 值 |
|---|---|
| 文件 | `dd1_d7c_b_tr_d02_package_2004139.zip` |
| 大小 | 25,744,159 B |
| SHA-256 | `2559fac1a380dbe4c55b4cad9c56a5af7afada03e5c7e64415f3c6f465a5661a` |
| ZIP 成员 | 725（723 行清单 + README + 清单自身） |
| 打包来源 | 提交 `2004139735a0f40632591e792e0540290c429168`，分支 `poc/data-pam-d7c-b-tr-d02` |

本回执在打包之后提交，不包含在包内。

## 包外真无 Git 回放

解包目录 `D:/_d02_scratch/outside_2004139/package`，自身与全部 3 层祖先均无 `.git`（`git rev-parse --show-toplevel` 返回 128）。清除全部 `GIT_*` 定位覆盖，只记录处理方式。

| 入口 | rc | 实际输出 |
|---|---:|---|
| 包内清单逐项大小与 SHA | — | 723/723 吻合 |
| `scripts/dd1_d7c_b_tr_r1_native.py --verify <R1>` | 0 | `21/21 problems=0 excluded=4`，无范围备注 |
| `independent_recompute.py . --inputs <d02_inputs.json>` | 0 | `RECOMPUTE_R1 gate 838/838` |
| 同上 verify，禁用 `git` 子进程 | 0 | 同上 |
| 同上 recompute，禁用 `git` 子进程 | 0 | `838/838` |
| 包内探针 `dd1_d7c_b_tr_d02_probe.py` | 0 | 3 项正控 rc=0，15 项 CLI 反例全部具名拒收 |

B4 的三组方法级用例在无 Git 树中标 `NOT_APPLICABLE`（工程模块按设计读对象库），在 Git 检出中实际执行：标签不释放、两次启动不释放、`NOT_STARTED` 释放一次。

回放前后 725 个文件集合与 SHA-256 完全一致。

## 保留口径

`BUDGET_ACCOUNTING_STATUS=PARTIAL`、`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、保守 5/4 不变；动态 33/37、名义 23/37 电气 FAIL 与 ±0.5 LSB 阈值不变；检查器仍是 838 条；260 条历史模块自测未运行。

零 Spectre、零 RTL 编译/仿真、零 OA、零 guest、零 PDK/license/凭据读取；未改冻结 deck/序列/账本；未合并、未登记接受。

```text
PACKAGE_OUTSIDE_REPLAY=PASS
ORIGINAL_D02_ZIP_SHA256=2559fac1a380dbe4c55b4cad9c56a5af7afada03e5c7e64415f3c6f465a5661a
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
