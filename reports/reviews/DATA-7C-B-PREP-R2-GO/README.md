# DATA-7C-B-PREP-R2 限定接受登记（离线内容，非原生授权）

登记对象：`e51c5320a28bd5043e21d08a0be97e9d5612cd16`（分支 `poc/data-pam-d7c-b-prep-r2`，基线 R1 `6778535e70b139812265eba490d0a1381a1fae5c`）。
依据：用户于 2026-10-25 在 Qoder Desktop 对话里对本轮方案的选择——"批准 20 次，一跑到底"与
"登记，限 PAM 候选与离线准备"。用户点击的精确时刻对本 Agent 不可观测，因此本文件只给写出时刻
`2026-10-25T17:22:16Z`，不编造时间戳。

| 文件 | 内容 |
|---|---|
| `registration.json` | 登记范围、用户选择原文、本轮授权与仍禁止项、证据基础、复核计数 |
| `package_identity.json` | 审核包 ZIP 的字节与摘要、37 行 MANIFEST 的逐条摘要核验结果 |
| `review_package/` | 审核方 ZIP 的字节镜像（含 MANIFEST.csv 自身、checks/ 原始输出与两份原仪器） |

登记的是 **PAM 候选文本电路 + 15 例离线激励与测量准备**。它不表示八档电流已实测，不表示原生网表语法
已验证，不追认其它历史轮次，不合并 `main`。DATA-7B 的 59/56 超量与凭据回显事件原样保留。

复核方法（任何人在含 `.git` 的 checkout 里都能重放）：

```bash
python - <<'PY'
import csv, hashlib, io, os
m = 'reports/reviews/DATA-7C-B-PREP-R2-GO/review_package'
rows = list(csv.DictReader(io.open(os.path.join(m, 'MANIFEST.csv'), encoding='utf-8')))
bad = [r['path'] for r in rows if len(io.open(os.path.join(m, r['path']), 'rb').read()) != int(r['bytes'])
       or hashlib.sha256(io.open(os.path.join(m, r['path']), 'rb').read()).hexdigest() != r['sha256']]
print('MANIFEST rows %d, mismatches %s' % (len(rows), bad or 'none'))
PY
git cat-file blob e51c5320a28bd5043e21d08a0be97e9d5612cd16:scripts/dd1_d7c_b_prep_measure.py | sha256sum
```

本轮唯一被批准顺带修的非阻断项：`scripts/dd1_d7c_b_prep_contract.py` 名义电流表最后一格的 µA 换算
（`value` → `value*1e6`）与对应 Markdown 重渲染；JSON 安培数、判据与合同状态 `PROPOSED_FOR_REVIEW` 不变。
