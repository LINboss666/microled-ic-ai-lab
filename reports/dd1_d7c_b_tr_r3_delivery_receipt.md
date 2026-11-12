# DATA-7C-B-TR-R3 包外回放回执

日期：2026-11-12。

## 交付包

| 项目 | 值 |
|---|---|
| 文件 | `dd1_d7c_b_tr_r3_package_c20f42a.zip` |
| 大小 | 25,466,920 B |
| SHA-256 | `4ebc04f399a171474b01eb5d2422a21cc0e96a4dad0b1953f3aacd836b5821fb` |
| ZIP 成员 | 666（664 行清单 + README + 清单自身） |
| 打包来源 | 提交 `c20f42a238c768aea3dbf9ce38510f7504d0d214`，分支 `poc/data-pam-d7c-b-tr-r3` |

本回执在打包之后才提交，因此**不包含在包内**；包内 664 项按清单登记，非 Git 追加项为 `PACKAGE_README.md`、`package_manifest.csv`、`independent_recompute.py` 与两份 `.vcd.gz`。

## 包外真无 Git 回放

解包目录 `D:/_r3_scratch/package_outside_c20f42a/package`，其自身与全部 3 层祖先均无 `.git`（`git rev-parse --show-toplevel` 返回 128）。子进程环境清除全部 `GIT_*` 定位覆盖，只记录处理方式，不打印环境值。

| 入口 | rc | 实际输出 |
|---|---:|---|
| 包内清单逐项大小与 SHA | — | 664/664 吻合，0 不符 |
| `scripts/dd1_d7c_b_tr_r1_native.py --verify <R1>` | 0 | `21/21 problems=0 excluded=4` |
| `independent_recompute.py . --inputs <r3_inputs.json>` | 0 | `RECOMPUTE_R1 gate 838/838` |
| 同上 verify，禁用 `git` 子进程 | 0 | `21/21 problems=0 excluded=4` |
| 同上 recompute，禁用 `git` 子进程 | 0 | `838/838` |
| 包内探针 `dd1_d7c_b_tr_r3_probe.py` | 0 | 3 项正控 rc=0，8 项反例全部具名拒收 |

回放前后包内 666 个文件的集合与 SHA-256 完全一致。

## 关于包内探针的 B4 段

`Account` 与 `record` 所属的工程模块按设计要读对象库，因此在无 Git 的解包目录里无法导入。探针把该段标为 `NOT_APPLICABLE` 并写出原因，其余 8 项反例与 3 项正控照常执行；B4 的两组断言（只填标签不释放、真实转录释放一次）在 Git 检出中实际完成并留证于 `counterexamples/`。

## 保留口径

`BUDGET_ACCOUNTING_STATUS=PARTIAL`、`RTL_PROCESS_COUNT=NOT_INDEPENDENTLY_PROVEN`、保守占额 5/4 不变；动态 33/37、名义 23/37 电气 FAIL 与 ±0.5 LSB 阈值不变；260 条历史模块自测未运行；检查器计数 841→838 只因五条并列旧记录并为一条，不是新证据。

本轮零 Spectre、零 RTL 编译/仿真、零 OA、零 guest、零 PDK/license/凭据读取；未合并、未登记接受、未自签 GO。

```text
PACKAGE_OUTSIDE_REPLAY=PASS
ORIGINAL_R3_ZIP_SHA256=4ebc04f399a171474b01eb5d2422a21cc0e96a4dad0b1953f3aacd836b5821fb
STOP_REASON=AWAITING_INDEPENDENT_REVIEW
```
