# DATA-7B-R3 独立审核材料

先读 `REVIEW_DATA7B_R3.md`。审核建议是限定 GO：F1/F2 关闭，无新增阻断返修，不再下发 R4。历史预算仍 FAIL，用户决定接受与后续授权。

被审远端：`https://github.com/LINboss666/microled-ic-ai-lab/tree/f9fd09b184a69a27cdb409205dfd4f4151408a23`。

本包是审核方新增的报告与复算记录，不是执行方交付 ZIP 的替代品；不复制仓库、PDK 或电流样本。

| 文件 | 内容 |
|---|---|
| REVIEW_DATA7B_R3.md | 完整意见、作用域、非阻断注记 |
| review_summary.json | 机器可读结论 |
| source_identity.json | 精确 ZIP、53 个源码成员、全树冻结、handoff 身份、连续/采样带内时长与最终 Git 回读 |
| account_states_base.json / fixed.json | 审核方原仪器在旧基线复现与最终 R3 关闭的逐字段结果 |
| checks/ | 13 条独立命令的真实输出、独立 rc 与参数 |
| reviewer_account_states.py | 上轮仪器原字节，不是执行方新写的验收器 |
| reviewer_r3_audit.py | 只读身份/冻结/文档与带内时长复核 |
| reviewer_r2_metrics.py | 审核方独立插值与积分函数，被当前 audit 导入；不导入项目测量核心 |
| run_review_checks.py | 本方离线命令重放器 |

独立仪器返回码约定：0 是旧缺陷复现；1 是两层关闭且 all_requirements_met=true；2 是部分关闭。必须检查 JSON 的新增点名失败，不能只看总 rc。

工具输入为含 base 和 tip 的完整仓库 checkout；旧 R2 证据目录是只读输入。源码和约 21 MB 样本按固定 Git SHA 引用，不重复装入本包。

```bash
python3 reviewer_account_states.py /absolute/path/to/base /absolute/path/to/base_result.json
python3 reviewer_account_states.py /absolute/path/to/R3 /absolute/path/to/fixed_result.json
python3 reviewer_r3_audit.py /absolute/path/to/R3 /absolute/path/to/MicroLED_DATA7B_R3_Package_20261023.zip
```

`run_review_checks.py` 中是本次审查目录的实际路径，异机运行前仅调整 checkout/输出位置，不改变输入 SHA 或预期语义。不要把重跑得到的文件覆盖正式发布目录。

本包不包含合并、接受登记、仿真或下一阶段执行指令。历史事故和未实现项目见完整报告。
