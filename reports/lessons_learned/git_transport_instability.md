# Git 传输不稳定：故障表现、根因、修复与恢复流程（NET-1，永久防错规则）

日期 2026-10-09。仓库 `D:\ic617_agent_bridge` -> `https://github.com/LINboss666/microled-ic-ai-lab`。
执行主机 Windows / Git for Windows 2.49.0.windows.1。分层证据见
`reports/git_network_diagnosis.md`；本文只留可长期复用的结论与流程。

## 1. 故障表现

`git push`（以及 `git ls-remote`、`git fetch`）对 `github.com:443` 间歇失败，同时 `gh api` 一直正常。
本轮捕获到的三种真实报错，全部来自同一条直连路径：

| 阶段 | 原文（截断） | 性质 |
|---|---|---|
| TCP 连接 | `fatal: unable to access 'https://github.com/.../': Failed to connect to github.com port 443 after 21114 ms: Could not connect to server` | 连不上 |
| 流被截断 | `fatal: expected flush after ref listing` | 连上了，smart-http 响应没收完 |
| 卡死 | `error: RPC failed; curl 28 Operation too slow. Less than 1024 bytes/sec` | 半开连接挂住，需外部超时才退出 |

历史窗口（GUI-1 交付时）连续 4 次 push 失败，症状与上表第 1、2 类相同；当时远端已由 `gh api` 读到
正确 SHA，只有 git 这条路不通。同一会话内直连从 5/5 成功翻转到 0/5 失败，所以**症状是抖动，不是
恒定不可用**——这点决定了后面的设计必须是"运行时选择"，不能是"记住某条路能用"。

## 2. 实际根因及证据

`ROOT_CAUSE_CONFIRMED`（失效阶段，三个独立窗口可重复）：

故障发生在**本 Windows 主机到 `github.com:443`（`20.205.243.166`）的直连 HTTPS 路径**上，在 TCP 连接
层和 smart-http 流层两种位置间歇失败。同一二进制、同一凭据、同一分钟内，经由用户已配置的本地代理
（`127.0.0.1:7892`）执行同样的 git 操作全部成功。因为 git 在全局/仓库/URL/remote 四个层级**都没有
任何代理配置**，环境变量层面也没有 `HTTP_PROXY`/`HTTPS_PROXY`，它只能走这条会抖的直连，且没有任何
备用路径，所以抖动直接变成 push 硬失败。

`gh` 一直正常的原因也已被测量澄清：`gh` 访问的是 `api.github.com`（`20.205.243.168`），**另一个
域名、另一个 IP、另一条边缘**，它自始至终健康。

`ROOT_CAUSE: UNRESOLVED`（关于"这条边缘为什么抖"）：

本机测不出来，也没有证据支持任何一种说法。未验证的候选包括：本机网络到 GitHub 前置地址的中间路由/
对等质量、本地代理或安全软件对直连 443 的选择性干预、GitHub 侧负载均衡在健康与不健康后端之间轮转。
**不编造结论**：本文只确认"哪一层坏了"，不声称知道"为什么坏"。

## 3. HTTPS 与 SSH 测试结果

| 通道 | 结果 | 依据 |
|---|---|---|
| HTTPS 直连（`-c http.proxy=`） | **INTERMITTENT** | 窗口 A 5/5 OK；窗口 B 3/3 FAIL；窗口 C 0/5 FAIL |
| HTTPS 经配置代理 | **PASS** | 全部尝试无一失败（探测 5、脚本 5、连续 5、对比 6、dry-run 2、push 1、回读 2） |
| `api.github.com`（`gh`） | **PASS** | 每个窗口都能读到 ref |
| SSH over 443（`ssh.github.com`） | **AUTH_NOT_CONFIGURED** | TCP 开放；三张 host key 指纹与 GitHub `/meta` 公布密钥逐一匹配；`StrictHostKeyChecking=yes` 下 `Permission denied (publickey)`；本机只有 `id_rsa_ic617`（虚拟机密钥），`known_hosts` 无 GitHub 条目 |

SSH 路线**没有被采用**，因为需要用户先去 GitHub 注册一把新公钥；按边界要求，到这一步就停下报告，
不生成密钥、不上传密钥、不改 `~/.ssh`、不为了列账户密钥去扩 `gh` token 的 scope。origin 保持 HTTPS
不变。三个 GitHub 域名都只有 A 记录、无 AAAA，所以 IPv6 不是原因，也没有动 hosts 或禁 IPv6。

## 4. 代理配置差异

实测的层级差异，是本轮最容易误判的地方：

| 层 | 状态 |
|---|---|
| WinINET（当前用户，浏览器/很多应用读的） | `ProxyEnable=1`，`http://127.0.0.1:7892` |
| WinHTTP（服务账户用的） | 直连 |
| 进程 / User / Machine 三级代理环境变量 | 全部 unset |
| git 全局、仓库、URL 级、remote 级代理 | 全部 unset |
| `gh`（Go，`ProxyFromEnvironment`） | 因此也走直连 |

结论：**"gh 用了代理而 git 绕过代理"这个高优先级候选根因被证伪。** 两个工具都走直连，差别只在目标
域名。真正的差别是"git 只知道一条路，而那条路会抖"。

隐私边界：本轮使用的代理地址不含用户名/密码，无需脱敏；代理凭据、GitHub token、Authorization 头、
Cookie 一律不写入报告、日志、提交或聊天。代理进程的**软件名**在会话中确认过，但故意不写进本文，以便
这份报告将来可以安全公开。

## 5. 最终解决方案

不改全局、不改系统代理、不改代理软件、不持久化仓库代理，而是把"测过再用"固化成脚本：
`scripts/git_push_reliable.ps1`。

1. 解析分支与 HEAD，拒绝 detached，拒绝 main/master（除非显式 `-AllowProtected`）。
2. 跑 `scripts/precommit_safety_check.py --mode history`，不 PASS 就停。
3. push 之前先读远端 ref；**候选顺序按实测排**：先配置代理，再强制直连。
   `direct` 一律带 `-c http.proxy=`，这样即使将来仓库级持久化了代理，两条候选仍然是两条真的路。
4. 要求远端 SHA 是本地的祖先，否则停止并报告，绝不覆盖。
5. 用 `git ls-remote` 实测每条通道，选第一条应答的。
6. 用选定通道做 `push --dry-run`。
7. 普通非强制 push；只有传输类失败才重试，重试间隔递增，并自动切到另一条候选通道。
8. 失败按阶段分类：`TRANSPORT_CONNECT` / `TRANSPORT_RESET` / `TRANSPORT_TIMEOUT` / `AUTHENTICATION`
   / `NON_FAST_FORWARD` / `HOOK_REJECTED`。
9. 独立回读远端 SHA：换一条**不是** push 所用通道走一遍 `ls-remote`，再用 `gh api`
   （`api.github.com`，不同主机）二次确认；两者都拿到才算验过，拿不到就写 `UNVERIFIED`。
10. 输出单一 RESULT 块。

禁用的动作，脚本里一个都不做：`--force`、`--force-with-lease`、`--no-verify`、自动 merge/rebase、
用 REST API 改写 ref 代替 push、`http.sslVerify=false`、关闭身份验证。pre-push hook 每轮都真实执行
（日志里能看到它打印的 `SAFETY_GATE: PASS`）。

另外用 git 自己的 `http.lowSpeedLimit=1024 / http.lowSpeedTime=10` 取代"从 PowerShell 盯进程超时"：
半开连接会被 git 主动掐掉并归入 `TRANSPORT_TIMEOUT`，而不是无限挂住。窗口 C 里那条 `curl 28` 就是它
生效的现场证据。

**为什么没有把代理写进仓库配置**：那样裸 `git push` 今天更稳，但会新引入一种故障——代理软件没开时
仓库彻底推不动。脚本已经能探测并回退，所以把"持久化代理"留成用户可授权的选项，而不是默认执行。
若要启用：`git -C D:\ic617_agent_bridge config --local http.https://github.com.proxy
http://127.0.0.1:7892`（`--unset` 即撤销）。

## 6. 推送前安全检查

顺序固定，缺一不可：

1. `SAFETY_GATE: PASS` 必须在任何网络动作之前拿到（`precommit_safety_check.py --mode history` 扫历史
   提交，含凭据、私钥、厂商模型、PDK/techfile 分类）。
2. 确认待推分支是当前确认过的功能分支，且 `symbolic-ref HEAD` 与它一致。
3. 读远端 SHA，确认推送是 fast-forward。
4. `push --dry-run` 通过。
5. 诊断日志进 Git 之前必须过脱敏与安全扫描：本轮的原始 stdout 留在 `%TEMP%`/`/tmp`，**不入库**；
   入库的只有两份 Markdown（无 token、无密码、无进程名）和脚本本身。

## 7. 推送后 SHA 验证

规则：`LOCAL_REMOTE_PARITY: PASS` 只在**独立回读**得到的 `REMOTE_SHA == LOCAL_SHA` 时才允许输出。

* 回读必须用与 push 不同的通道（脚本先试另一条候选通道），或用 `gh api` 打到 `api.github.com`。
* 回读拿不到 SHA 时，只能写：

  ```
  PUSH_REPORTED_SUCCESS
  REMOTE_PARITY_UNVERIFIED
  ```

  绝不允许根据 push 的 stdout（"Everything up-to-date"、`a53f646..9dde29f`）猜测最终状态。
  本轮 run3 就实地执行了这条纪律：脚本自身有个 bug 导致回读失败，尽管 `gh` 已经证实远端 SHA 正确，
  它输出的仍是 `UNVERIFIED` 而不是 PASS——这正是期望行为，bug 随后被修掉并复测为 PASS。
* 本轮实测：GUI-1 三个提交（`d3881ef`、`82957a6`、`9dde29f`）已推送，远端
  `feature/data-driver-virtuoso-schematic = 9dde29fd0e2dc54eeeeed58eb1ab42a3b8682661`，与本地 HEAD
  相等，由 `git ls-remote` 与 `gh api` 两条独立路径同时确认。`main` 未合并、未改动（远端 main 仍为
  `23e471c`）。
* 本文件与诊断报告自身的提交（`9098dad`）也用同一个脚本推送，选定通道同样是代理；推送后
  `git ls-remote`（走直连，几分钟前它还是 0/5）与 `gh api` 都回读到
  `9098dad3952ccf4b1a4dfcc78753f269eb05d09c` == 本地 HEAD。这条直连在约 20 分钟内从 5/5 → 0/5 → 又能
  用，正是"必须在运行时测量、不能记住上次哪条路好走"的直接证据。

## 8. 失败时的恢复流程

先分类，再决定，绝不无脑重跑同一条命令：

| 报告的阶段 | 含义 | 允许的下一步 | 禁止的下一步 |
|---|---|---|---|
| `TRANSPORT_CONNECT` | 直连 443 连不上 | 走 `git_push_reliable.ps1`，让它选另一条候选通道；确认本地代理进程是否在监听 | 重复裸 `git push`；改全局代理 |
| `TRANSPORT_RESET` / `curl 18/28` / `expected flush` | 连上了但流断了或卡住 | 同上；必要时等几分钟再试一次，用 `ls-remote` 先探 | 关掉 TLS 校验；`--no-verify` |
| `AUTHENTICATION` | 凭据/权限问题 | 检查 `gh auth status` 与 `credential.helper` 链 | 生成新 SSH key 绕过；扩 token scope |
| `NON_FAST_FORWARD` | 远端分支动了 | **停**，fetch 后人工看，报告差异 | `--force` / `--force-with-lease` / rebase 覆盖 |
| `HOOK_REJECTED` | 安全闸拦下 | 修被拦内容并重跑扫描 | 跳过 hook |
| `SSH_443 AUTH_NOT_CONFIGURED` | 主机可达但无身份 | 报告并请用户注册公钥后再评估 | 擅自改 origin / 写 `~/.ssh` |

判定纪律：本文件里"当前可用"的通道是**代理优先 + 自动回退**，不是"代理永远可用"。若哪天代理软件不开，
脚本会失败在 `PROXY_CONNECTION` 并自动落到强制直连——那时才轮到直连的表现说话。任何时候只成功一次，
不得写成"网络问题已彻底修复"。
