# ic617_agent_bridge

Windows(Qoder) -> VMware Workstation -> RHEL6 -> Cadence IC617 的自动化通道。
用于 SKILL 脚本执行、批处理、日志分析；不用于点鼠标。

## 1. 架构

```
Qoder / Windows 11                    RHEL6 虚拟机 (VMware Workstation 17.6.3)
----------------------                -----------------------------------------
test_ic617_bridge.ps1  --vmrun------> vmware-vmx 状态 / Tools guest-ops（备用通道）
        |
        +--ssh / scp (RSA 密钥, 免密)-> bash -l -> run_skill.sh
                                                  |
                                                  +-> cad_env.sh  (从 /etc/env/virtuoso 取 export)
                                                  +-> dbAccess -load xxx.il   (Virtuoso 6.1.7-64b)
                                                        |
                                                        +-> $SANDBOX/logs/<name>_<ts>.log  --scp--> Windows logs/
```

主通道是 **SSH**（密钥免密）。VMware Tools / `vmrun` 只在两种情况下使用：读取 VM 状态与 Guest IP，以及 SSH 不可达时的应急执行（需要临时凭据）。

## 2. 一键测试

```powershell
# 完整链路 + 三次复现
powershell -ExecutionPolicy Bypass -File scripts\test_ic617_bridge.ps1 -Repeat 3

# 跑 bonus 脚本（时间/目录/标记），同一条命令触发并校验
powershell -ExecutionPolicy Bypass -File scripts\test_ic617_bridge.ps1 `
  -SkillFile skill\cadence_agent_test.il -Token CADENCE_AGENT_TEST_OK
```

输出 6 个阶段逐条 PASS/FAIL，最后一行 `RESULT: PASS|FAIL`；FAIL 会打印失败阶段与 Cadence 的关键报错。
每次运行在 `logs/bridge_<时间戳>.json` 留一份结构化结果。

单独用：

```powershell
powershell -File scripts\probe_vm.ps1                    # VM/Tools/IP 探测（JSON）
powershell -File scripts\test_ssh.ps1 -TargetIp 192.168.3.128   # SSH 与协商诊断
node   scripts\scan_tcp.mjs 192.168.3 22                 # 网段 TCP 扫描（找 IP）
```

Git Bash 下的手工通道（调试最常用）：

```bash
export QODER_GUEST_IP=192.168.3.128
bash scripts/guest.sh ssh    'cd ~ && ls'                 # SSH 执行（登录 shell 环境）
bash scripts/guest.sh run    'ls' 60                      # VMware Tools 执行（需 QODER_GUEST_USER/PW）
bash scripts/guest.sh push   local_file /root/qoder_ic617_sandbox/bin/x.il
bash scripts/guest.sh pull   /root/qoder_ic617_sandbox/logs/x.log logs/x.log
```

## 3. Guest IP 怎么来

- 权威来源：`vmrun getGuestIPAddress <vmx>`，脚本优先用它。当前值 `192.168.3.128`。
- NAT 段 `192.168.3.0/24`（`vmnetnat.conf` 里 `ip = 192.168.3.2/24`；主机 VMnet8 = `192.168.3.1`；DHCP 池 `.128–.254`）。
- **重要**：guest 里 `ifcfg-eth0` 是 `ONBOOT=no`，本次是用 `dhclient -1 eth0` 临时拿到地址的。
  虚拟机重启后没有 IP，SSH 会连不上。恢复方式（任选其一）：
  1. 直接重跑 `test_ic617_bridge.ps1`——它会从 `.ic617_agent_bridge_credentials` 自动取凭据，并通过 Tools 通道执行 `dhclient eth0`；
  2. 在 Workstation 控制台里 `dhclient -1 eth0`；
  3. 手工指定：`-GuestIp 192.168.3.128`（前提是先起好网卡）。
- IP 变了不用改任何脚本，脚本每次重新解析。

## 4. Cadence 环境怎么载入

镜像里**没有**任何登录脚本设置 Cadence 变量。`which virtuoso` 能命中只是因为 `/etc/env` 在 `PATH` 里，而 `/etc/env/virtuoso` 是一个包装 **脚本**（不是软链），它 export 完环境变量后以 `virtuoso&` 结尾——直接跑它会弹 GUI 并立刻返回，无法用于自动化。

所以 `skill/cad_env.sh` 只做一件事：从 `/etc/env/virtuoso` 里 `grep` 出 `export` 行并 `eval`，不复制其值、不修改该文件。载入后可用：

| 变量/工具 | 值 |
|---|---|
| `CDS` | `/opt/IC617/` |
| `virtuoso` / `dbAccess` | `/opt/IC617/tools/dfII/bin/...`（`CDS_AUTO_64BIT=ALL` 使其走 `bin/64bit/`） |
| `OA_HOME` | `/opt/IC617/oa_v22.50.036/` |
| `MMSIM_ROOT` | `/opt/MMSIM151`（spectre 在 `tools/spectre/bin/spectre`） |
| license 变量 | 由 `cad_env.sh` 运行时提供，本仓库不记录其值 |

已知镜像缺陷：`/etc/env/virtuoso` 的 `LD_LIBRARY_PATH` 行写成 `$D_LIBRARY_PATH`（少一个 L）。`cad_env.sh` 预置该名字以避免 `set -u` 下报错。

## 5. SKILL 怎么执行

```bash
bash /root/qoder_ic617_sandbox/bin/run_skill.sh /root/qoder_ic617_sandbox/bin/<name>.il [timeoutSec]
```

`run_skill.sh` 的行为（也是它的安全护栏）：

- 只接受位于 `$SANDBOX` 下的、真实存在的 `.il`，否则 `REFUSED` 退出码 9；
- `cd $SANDBOX/work`、`HOME=$SANDBOX/home`，所以 Cadence 的临时文件（`CDS.log` 等）不会落到真实 HOME；
- 注入 `QODER_RUN_TS`（UTC）和 `QODER_HOST`，因为该 dbAccess 没有时钟内建函数、bash 非登录 shell 也不导出 `HOSTNAME`；
- `timeout N dbAccess -load` → stdout+stderr 进 `$SANDBOX/logs/<name>_<时间戳>.log`，并回显；
- 打印 `RUN name=… rc=… elapsed=…s`、`LOGFILE <绝对路径>`。

实测的 SKILL 能力（详见 `reports/cadence_probe.md`）：

- 可用：`printf`、`errset`、`foreach`/`let`/`procedure`、`getShellEnvVar`、`system`、`shell`
- 不可用：`gettime/time/ctime/time2str/posixtime/today/now/date/getenv/pipe/skillVersionName`，以及 `funcall(符号)` 动态派发（一律 nil）
- 取时间请用 `getShellEnvVar("QODER_RUN_TS")`；取工作目录用 `getShellEnvVar("PWD")`
- 写 SKILL 时把可能 nil 的值包一层（见 `skill/cadence_agent_test.il` 的 `qSv()`），否则 `printf("%s", nil)` 会中断整个 `load`

## 6. 已知限制

- `run_skill.sh` 走 `dbAccess`，它有 OA 但**没有完整图形环境**：`ge*`/`ui*`/`ted*` 等依赖 Virtuoso 会话的函数不可用。需要完整 API 时得用 `virtuoso -nograph -restore`，而那需要一个 X 环境（guest 里 `:0` 由 gdm 持有）。
- 虚拟机重启后网络回到 down，SSH 失效（见第 3 节）。
- License：`CDS_LIC_FILE` 指向的 TCP 端口上没有任何监听，`lmstat` 报 `No SERVER lines`，但 `dbAccess` 每次都报告 Framework License (111) 检出成功（0.03s）。实际授权来源未查明，本次未改动任何 license 相关配置。
- `vmrun copyFileFromHostToGuest` 在本环境返回"文件名无效"，因此上传走 `runProgramInGuest` + base64（已做 md5 回读校验）；反向 `copyFileFromGuestToHost` 正常。
- Git Bash 会把看起来像 POSIX 路径的 **argv 和环境变量值**改写成 Windows 路径，所以 `vmguest.mjs`/`vmfile.mjs` 的路径一律经 base64 传递。
- 密钥认证依赖 `~/.ssh/id_rsa_ic617`（RSA-3072）。RHEL6 的 OpenSSH_5.3 不支持 ed25519，别换成 ed25519 密钥。

## 7. 下一步扩展

1. 持久化网络：把 `ifcfg-eth0` 的 `ONBOOT` 改为 `yes`（本次刻意没改，属 guest 配置变更，需你确认）。
2. 正式工程批处理：新建一个指向真实 `cds.lib`/tech 的**工作目录**（不是复制 PDK），用 `dbAccess -load` 做 `db*` 查询与 netlist 导出；写操作前先在 sandbox 里做一次 dry-run 快照对比。
3. 需要完整 SKILL/图形 API 时，改走 `virtuoso -nograph -restore`，并给它一个独立的 `DISPLAY`（例如 `Xvfb`，或 guest 内第二个 X 会话）。
4. 仿真批处理：`spectre` 已在 PATH，可用同一 `run_skill.sh` 模式包一个 `run_netlist.sh`（输入网表 + 输出目录均在 sandbox/工程目录内）。
5. 日志分析：把 `logs/bridge_*.json` 汇入一个小的看板，跟踪 rc、耗时、license 检出时间漂移。

## 目录

```
ic617_agent_bridge/
├── README.md              本文件
├── AGENTS.md              给后续 Agent 的约束与坑
├── scripts/
│   ├── probe_vm.ps1                VM/Tools/IP 探测
│   ├── test_ssh.ps1                SSH 连通与算法协商诊断
│   ├── test_ic617_bridge.ps1       一键端到端 PASS/FAIL
│   ├── vmguest.mjs                 Tools 通道执行命令（base64 载荷 + 超时 + rc 回传）
│   ├── vmfile.mjs                  Tools 通道文件上传/下载（md5 校验）
│   ├── guest.sh                    上述三者的统一 CLI
│   └── scan_tcp.mjs                并发 TCP 扫描（找 guest IP）
├── skill/
│   ├── cad_env.sh                  从 /etc/env/virtuoso 载入 Cadence 环境
│   ├── run_skill.sh                sandbox 内的 SKILL 执行器（含护栏）
│   ├── skill_smoke_test.il         阶段4 smoke test
│   ├── cadence_agent_test.il       bonus：时间/目录/标记
│   └── probe_skill_*.il            SKILL 能力探测（解释了上面那张表）
├── reports/
│   ├── environment_probe.md        阶段1
│   ├── cadence_probe.md            阶段3+4
│   └── final_validation.md         阶段6 TEST1-7
└── logs/                           每次运行的 scp 回来的日志 + bridge_*.json
```

## 首次 bootstrap（换机器/重装镜像时才需要）

之后的运行全部免密，只有这一步需要一次性使用 guest 凭据：

```bash
ssh-keygen -t rsa -b 3072 -N "" -C "qoder-ic617-bridge" -f ~/.ssh/id_rsa_ic617   # 不能是 ed25519
cp ~/.ssh/id_rsa_ic617.pub logs/_pubkey.tmp
bash scripts/guest.sh push logs/_pubkey.tmp /root/.ssh/authorized_keys
bash scripts/guest.sh run  'chmod 600 /root/.ssh/authorized_keys; dhclient -1 eth0; service sshd status' 60
rm logs/_pubkey.tmp
```

## 凭据文件

`.ic617_agent_bridge_credentials`（仓库根目录，2026-10-04 应你要求持久化）内容：

- `QODER_GUEST_USER` / `QODER_GUEST_PW`：VMware Tools 通道用（SSH 主通道不需要）
- `QODER_GUEST_IP`：仅作为 `vmrun` 拿不到地址时的最后回退
- `QODER_SSH_KEY` / `QODER_SSH_COMPAT`：记录用的 SSH 参数（老 OpenSSH_5.3 的 SHA-1 兼容位）

读取顺序：`scripts/guest.sh` 在 `QODER_GUEST_PW` 未设置时自动 source 该文件并导出；
`scripts/test_ic617_bridge.ps1` 用它补 `QODER_GUEST_USER/PW/IP`。因此直接跑脚本即可，无需手工导出。

安全约束（已落实）：该文件由 `.gitignore` 排除，**绝不提交**；其中的密码值不会出现在任何报告、日志、
`bridge_*.json` 或文档里；license 值同样只由 `cad_env.sh` 运行时取用，不复制进仓库。

## 第二阶段（Micro LED 侦察，2026-10-04）

桥之上加了三层可复用的执行能力，工程数据都在 guest 的 `/root/microled_ai_project`：

| 用途 | Windows 侧 | guest 侧 | 验证结果 |
|---|---|---|---|
| PDK 只读盘点 | `skill/pdk_inventory.sh` → `reports/pdk_inventory.md` | `logs/pdk_inventory_raw.txt` | 5 个工艺库识别 |
| Spectre 执行器（带护栏 + 数值断言） | `scripts/run_spectre.sh`、`spectre/smoke_rc.scs` | `spectre_smoke/` | `SPECTRE_SMOKE_TEST: PASS`（relerr 0） |
| PDK 模型验证聚合 | `scripts/pdk_model_probe.sh`、`spectre/model_probe_*.scs` | `model_probe/` | 8/8 `PDK_MODEL_PROBE: PASS` |
| 系统级算术基线 | `scripts/microled_arch_calc.py`（py2.6/3 双兼容） | `results/`+`reports/` | `MICROLED_CALC: PASS` |
| 无图形 Virtuoso 探测 | `scripts/run_virtuoso.sh`、`skill/nograph_probe.il` | `skill_run/` | `VIRTUOSO_NOGRAPH: PASS` |

一条命令触发（guest 侧执行、Windows 侧判定）：

```bash
bash scripts/guest.sh ssh 'cd /root/microled_ai_project && bash scripts/pdk_model_probe.sh'
bash scripts/guest.sh ssh 'cd /root/microled_ai_project && MODE=nograph bash scripts/run_virtuoso.sh /root/microled_ai_project/skill/nograph_probe.il 150'
```

结论、坑与安全边界见 `reports/phase2_validation.md`；Cadence 侧新增的实测约束已写入 `AGENTS.md` 第 11–16 条。



---

## 第三阶段：版本管理 + 源码审核工作流（2026-10-05）

本目录现在是一个 git 仓库（`main` = 基线，`poc/c2mos-dff` = C²MOS 移位单元本轮工作）。
规则与流程写在 **`CONTRIBUTING_AI.md`**，调查结论写在 **`reports/git_workflow.md`**。

```bash
bash scripts/install_hooks.sh                       # 装 pre-commit / pre-push 安全闸
python scripts/test_safety_rules.py                 # 闸本身的双向用例（必须 PASS）
python scripts/repo_safety_scan.py                  # SAFE_TO_TRACK / MUST_IGNORE / NEEDS_REVIEW
python scripts/precommit_safety_check.py --mode staged
python scripts/precommit_safety_check.py --mode history
python scripts/precommit_safety_check.py --mode objects   # 含 .git 里的 dangling blob
python scripts/make_review_bundle.py main HEAD --notes reports/c2mos_review_notes.md
python scripts/repo_parity.py /tmp/guest_md5.txt    # Windows 镜像与 guest 结构是否一致
```

永远不入库：老师/代工厂 PDK 本体与模型卡原文、DRC/LVS/XRC deck、`course_source/`
（老师交付的课程文档原件）、`pdk_compare/`（PDK 文件清单）、`logs/`（桥运行日志）、
凭据、SSH 私钥、token、license 服务地址值、raw PSF 波形数据库。

PDK 路径不在任何被跟踪文件里：netlist 写 `include "${QODER_PDK_LIB}"`，
变量来自未跟踪的 `spectre/pdk_local.env`（模板 `spectre/pdk_local.env.example`）。

远程仓库：`https://github.com/LINboss666/microled-ic-ai-lab`（**PRIVATE**）。
