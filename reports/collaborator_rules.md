# 协作者行为规则与推送环境（gexing321 侧交付）

作者身份：GitHub 登录名 `gexing321`（提交邮箱 `3832459201@qq.com`），是本仓库的 **Write 协作者**。
仓库属 **队长 `LINboss666`**，本文件由协作者侧编写，位于协作者分支
`gexing321/docs/collaborator-rules`，**未** 触碰队长的任何 ref。等待人工/另一模型审核后再决定是否进主线。

本文件只做两件事：把用户 2026-10-11 提出的两条硬要求写成可机检的规则，并记录这台新电脑上
Git/GitHub 环境的实测状态。不含电路内容，不改任何既有设计文件。

---

## 1. 用户提出的两条硬要求（原话转述）

1. 成为协作者之后，**一定不能污染 `LINboss666` 本来已经推送、或将来要推送的东西**。
2. **协助者推送的代码一定要加以区分。**

第 1 条的实质风险不是"读"，而是 Write 权限允许协作者移动队长的 ref：一次手滑的
fast-forward、一次 `--force`、一次删分支，都会破坏本项目"冻结基线 + 机检审核"的可追溯性。
`AGENTS.md` 23 已经实测过更坏的一面：force-push 之后服务端仍按 SHA 继续服务被替换的旧对象，
本地历史干净不等于远端干净。

## 2. 规则（协作者侧，逐条可执行）

| # | 规则 | 拦什么 |
|---|---|---|
| R1 | 队长的命名空间只读：`main`、`feature/*`、`poc/*` 一律不推、不移动、不删除 | 覆盖队长的成果 |
| R2 | 协作者产物只进 `gexing321/<类别>/<主题>`（例：`gexing321/docs/collaborator-rules`） | 分不清是谁推的 |
| R3 | 禁止 `--force` / `--force-with-lease` / `--delete` / `--mirror` / `--all` / `--tags` / 推 tag | 改写已发布历史 |
| R4 | 禁止对已存在于远端的提交做 `amend` / rebase / `filter-branch` | 基线 SHA 漂移 |
| R5 | 不在 `main` 上提交；本地 `main` 只跟随远端 | 误推的源头 |
| R6 | 合入队长分支由队长决定（PR/merge 不由协作者代开） | 替队长做审核结论 |
| R7 | `remote.origin.url` 永远指向队长的仓库，不改指向 fork | 悄悄改推送目标 |
| R8 | 凭据、token、guest 口令、license 值、本机账户名一律不进仓库；本机路径写 `<windows-user>` | 秘密与 PII 上公开仓 |

区分机制采用 **author + 分支前缀** 两路，用户明确不要额外的 commit 标记（如 trailer / 标题前缀），
所以区分靠这两处，二者都可机检：

```bash
git log --format='%an <%ae> %d' <BASE>..HEAD          # author 应为 gexing321
git ls-remote --heads origin | grep 'refs/heads/gexing321/'   # 远端可见协作者分支
```

## 3. 机械化护栏（本机实测，非口头保证）

写在**本仓库 `.git/config`**（本地生效，远端零影响，可随时删）：

```
remote.origin.push = refs/heads/gexing321/*:refs/heads/gexing321/*
```

行为已实测：本地没有 `gexing321/*` 分支时，裸 `git push` 在**本地即失败、不接触网络**，
因此 R5 的"手滑推 main"在机制层就不成立；显式写 refspec 仍可覆盖，即"违规必须是一个刻意动作"。

## 4. 推送环境实测状态（2026-10-11）

| 项 | 值 | 验证方式 |
|---|---|---|
| 系统 git | Git for Windows 2.55.0.windows.5，`C:\Program Files\Git`，在 Machine PATH | winget 安装并校验安装包哈希 |
| 另有内置 git | 2.52.0.windows.1（Qoder 自带，Agent shell 里 `git` 命中它） | `git --version` |
| 提交身份 | `gexing321 <3832459201@qq.com>`，**全局**（本机原先无任何身份，无法 commit） | `git var GIT_AUTHOR_IDENT` |
| 认证方式 | GCM 浏览器 OAuth（非粘贴 PAT），凭据持久化后可免交互推送 | 见下 |
| 写权限 | `permission=write role=write` | `gh api repos/LINboss666/microled-ic-ai-lab/collaborators/gexing321/permission` |
| 推送验证 | exit 0，`Everything up-to-date`（无 403） | `git push --dry-run origin main` |
| 免交互验证 | `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never` 下 dry-run 仍 exit 0 | 同上 |
| 安全闸 | `.git/hooks/pre-commit`(staged) + `pre-push`(history)，由 `scripts/install_hooks.sh` 装 | `--mode history`：66 commits / 872 objects，四类产品计数 0，`SAFETY_GATE: PASS` |
| 历史完整性 | 无 `.git/shallow`，非浅克隆，push 不受 shallow 限制 | `ls .git/shallow` 不存在 |
| `gh` | 2.102.0 已装并登录 `gexing321`，scopes `gist, read:org, repo`（keyring） | `gh auth status` |
| `node` | 仍缺失，`scripts/*.mjs` 不可用 | `node` command not found |

推送固定命令（代理**只加在单条命令上**，不进任何配置文件）：

```bash
git -c http.proxy=http://127.0.0.1:10090 -c http.version=HTTP/1.1 push
```

## 5. 本轮踩到的失败（不掩饰）

1. 第一次 dry-run 报 `remote: Permission to LINboss666/microled-ic-ai-lab.git denied to gexing321`
   —— 当时写权限尚未授予。403 会让 git 调用 `credential reject`，**把刚拿到的 token 抹掉**，
   所以失败尝试不留残余凭据。
2. 第二次报 `fatal: User cancelled dialog` —— 授权弹窗被取消，非配置问题。
3. 第三次报 `Failed to connect to github.com port 443 after 21129 ms` —— 同一次会话里
   `api.github.com` 直连始终 200，而 `github.com` 的 git 端点时好时坏（同期另一个会话在用 GitHub）。
   结论：**不要把 `api.github.com` 通当成 `github.com` 通**，git 流量默认走 `127.0.0.1:10090` 代理。
4. GCM 拿到的 GitHub token 复用给 `gh` 会失败：`error validating token: missing required scope
   'read:org'`。`gh` 需要自己那套设备码授权，两者是**两套独立存储**；`gh auth login` 没有
   改写 git 的 credential helper（`credential.helperselector.selected=manager` 保持不变）。
5. `cmdkey /list` 里查不到任何 GitHub 条目，但免交互推送能成功 —— **不要用 cmdkey 判断凭据是否
   持久化**，改用 `GCM_INTERACTIVE=never` 的 dry-run push。
6. 装完 `gh` 的**已开 shell 看不见它**（PATH 是安装前的快照），此时跑 `scripts/public_release_audit.py`
   会在 `gh api user` 那步失败。那是 PATH 问题不是鉴权问题，重开终端即可。

## 6. 需要审核方判断的问题

1. 命名空间用 `gexing321/<类别>/<主题>` 是否合适，还是应与仓库既有 `poc/`、`feature/` 约定合并
   （如 `poc/gexing321-<主题>`）？一旦有真实协作者产物进来，改名成本会上升。
2. 现在的护栏只在**本机**生效。是否需要在远端加保护（branch protection / 规定协作者只能开 PR），
   使护栏不依赖每台机器的自觉？
3. 本文件放在 `reports/` 是否与 `netlist_stats.py`、`provenance_check.py` 的扫描约定冲突？
   （已刻意避免器件计数断言与来源标签，需审核方确认这属于两类检查器的合法豁免。）
4. 本机提交邮箱是真实 QQ 邮箱，仓库为 PUBLIC，故该邮箱会出现在每一个新提交里。
   是否改用 GitHub noreply 身份？现有历史里 `237816241+LINboss666@users.noreply.github.com`
   才是仓库历史作者，两者会并存。
