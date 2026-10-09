# AGENTS.md — ic617_agent_bridge

本目录是给 Agent 用的 IC617 自动化桥接工程。开工前先读 `README.md`，本文件只写约束和坑。

## 通道

- 首选 SSH（密钥免密，`~/.ssh/id_rsa_ic617`）：`bash scripts/guest.sh ssh '<cmd>'`；`QODER_GUEST_IP` 由凭据文件提供默认值。
- Guest IP 优先用 `vmrun getGuestIPAddress` 现取；拿不到时才回退到凭据文件里记录的地址，并且必须再用 TCP/22 探一次确认它没过期。`192.168.3.128` 只是本次的值。
- VMware Tools（`vmguest.mjs` / `vmfile.mjs`）用于 VM 状态查询与 SSH 不可达时的应急执行。凭据自动从 `.ic617_agent_bridge_credentials` 读取（`guest.sh` 会 source 并导出），**不要向用户重复索要密码**。
- 改完 `skill/*.il`、`skill/cad_env.sh`、`skill/run_skill.sh` 后，跑一次 `test_ic617_bridge.ps1` 就够了——它会 scp 同步，Windows 侧是唯一真源。

## 硬约束

- 不对 VM 做开机/关机/reset/挂起/重启；不创建/删除/回滚快照；不改 `.vmx`。
- 所有 guest 侧写入限定在 `/root/qoder_ic617_sandbox/` 内。要在工程目录里跑，先得到用户明确批准。
- 不修改 PDK、不修改已有 Cadence library、不动他人 schematic/layout、不删任何 Cadence 工程。
- 不改 license 配置，不启停 license 服务。
- **凭据规则（2026-10-04 用户更新，优先于早期"不落盘"要求）**：guest root 凭据已按用户明确要求持久化在 `D:\ic617_agent_bridge\.ic617_agent_bridge_credentials`（被 `.gitignore` 排除）。直接读取使用，不要再问；但密码值绝不写进报告、聊天、日志、JSON、README、其他记忆文件，也绝不提交该文件。license 值同样只在运行时取用，不复制进仓库。
- 网络相关的唯一允许动作：guest 内 `dhclient -1 eth0`（临时租约）。不要改 `ifcfg-eth0` 的 `ONBOOT`，除非用户点头。
- 不要为了 SSH 兼容修改 Windows 全局 SSH 配置；兼容参数只加在单次命令行上。
- 每个问题最多 3 次修复尝试，然后带证据停下来汇报。

## 会踩的坑（都是实测结论）

1. **`/etc/env/virtuoso` 是包装脚本不是软链**，末尾 `virtuoso&` 会弹 GUI 并立刻返回。永远不要直接执行它；用 `skill/cad_env.sh` 取它的 `export` 行。它还有 `$D_LIBRARY_PATH` 拼写错误。
2. **该镜像不重启就没有网络**：`ifcfg-eth0` 是 `ONBOOT=no`。SSH 连不上先查 IP，而不是查密钥。
3. **OpenSSH_5.3 只提供 `ssh-rsa`/`ssh-dss`**，现代客户端默认拒绝。所以必须 `-oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa`，且**不能**用 ed25519 密钥。
4. **Git Bash 会改写 POSIX 风格路径**（argv 和环境变量值都会被换成 Windows 路径），所以 `vmguest.mjs`/`vmfile.mjs` 的路径必须经 base64 传入；不要把 `/tmp/...`、`/root/...` 直接当命令行参数丢给任何 Windows exe。
5. **`vmrun copyFileFromHostToGuest` 在这里报"文件名无效"**，上传走 `runProgramInGuest` + base64 + md5 回读；`copyFileFromGuestToHost` 正常。
6. **vmrun 会把外层命令里的 `$rc`/`$?` 吃掉**，所以 `vmguest.mjs` 用 base64 载荷内的 `trap ... EXIT` 自报退出码。
7. **dbAccess 的 SKILL 没有时钟**：`gettime/time/ctime/time2str/posixtime/today/now/date` 全部 nil；用 `getShellEnvVar("QODER_RUN_TS")`。
8. **`funcall(符号)` 在 dbAccess SKILL 里恒为 nil**，探测函数存在性必须逐个字面写出来，不能动态派发。
9. **`printf("%s", nil)` 会中断整个 `load`**（不是只打印 nil）。任何 `getShellEnvVar` 结果先过一层 nil 保护，参考 `skill/cadence_agent_test.il` 的 `qSv()`。
10. **guest 重启后 SSH 恢复顺序**：`vmrun list` → Tools 通道 `dhclient` → 再 SSH。中间不要用 `vmrun` 做电源操作。

## 验证纪律

- 声称可用之前必须真跑：`test_ic617_bridge.ps1 -Repeat 3` 全 PASS 才算通道可用。
- SKILL 脚本只认显式成功标识（token）+ `rc=0`，不看"没报错"就当成功。
- 日志留在 `logs/`（Windows）与 `$SANDBOX/logs/`（guest），两边都别删，那是证据。
- `reports/` 里的结论必须能对应到一条命令输出；不能对应就删掉那句话。

## Micro LED 工程（第二阶段起）

- 工程目录在 guest 的 **`/root/microled_ai_project`**（桥沙箱 `/root/qoder_ic617_sandbox` 只放桥基础设施，别混用）。Windows 侧文档镜像在 `microled/`。
- 需求只有 `spec/system_requirements.md` 那 7 条；其余参数（灰阶、消隐、pitch、Vf、工艺、VDD、PWM、复用系数…）全部是 `NOT DEFINED`。**不得把 NOT DEFINED 当已知量往下推。**
- 三个执行器带硬护栏，优先用它们而不是手写命令：`scripts/run_spectre.sh`（拒绝项目外 netlist）、`scripts/pdk_model_probe.sh`（8 项判据聚合）、`scripts/run_virtuoso.sh`（拒绝项目外 .il，HOME 全程重定向）。
- 大于约 3 KB 的文件不要用 `guest.sh push`：base64 载荷经 vmrun argv 有大小上限，会超时。用 scp。

## Cadence 侧实测坑（都已踩过并有对策）

11. **Spectre 组件名与语句顺序**：电压源是 `vsource`（不是 `source`）；分析语句是 `实例名 关键字 参数`，即 `sw1 dc dev=... param=dc start=... stop=... step=...`。`analyze=yes` 对 `dc` 非法（SFE-30 警告并忽略）。语法以本机 `spectre -h <组件>` 为准。
12. **默认输出即 `<netlist>.log` + `<netlist>.raw/`**，此 build 不接受 `-log/-raw`；要拿到可比对的数据必须跑真正的分析（纯 op 时 psfascii 只写空的 `logFile`）。`-format psfascii` 后从 `.raw/` 里选带 `TRACE`+`VALUE` 的文件，`logFile` 要跳过。
13. **TSMC 主 include 不可用**：`tsmc18/models/spectre/spectre.scs` 硬编码 `/opt/cadence/process/.tsmc18/...`（不存在）。直接 include 模型卡 `cr018gpii_v1d0.scs`，且 **`tt` 必须同时 include `stat_noise`**，否则 SFE-1996 `unknown parameter par1fn_mc`。
14. **厚栅器件有几何硬限**：SMIC `n50e2r` 要求 `lmin=1.4µm lmax=10µm wmin=0.6µm wmax=100µm`；违反时报 `CMI-2441` 后接莫名其妙的 `CMI-2434 'Vsat' must be positive`。选 L/W 前先读卡里的 lmin/lmax/wmin/wmax。
15. **full Virtuoso 不需要 X**。`virtuoso -nograph` 会自己拉起 Xvnc(:80)（`$HOME/.vnc-cds/`），4–6 s 完成。`-h` 只列 10 个选项，**没有** `-ilLoadFile`；SKILL 注入靠 `$HOME/.cdsinit` 里 `load("x.il") + exit()`，或 `-restore x.il` 且文件自己以 `exit()` 结尾（否则进程不退出，实测撞满超时）。
16. **SKILL 里 `~` 属性访问符会在解析期报错并中断整个 load**（试过 `l~name` 三种写法，均 `syntax error ... at line N column M` + `*Error* load`）。取 dd 对象属性改用函数式访问（如 `ddGetObjName(l)`），别在探针里赌。
17. **Spectre MOS 端序是 `Name ( d g s b ) ModelName`，衬极在最后**（权威来源：本机 `spectre -h bsim4`；`-h nmos` 会报 no such component，因为组件名是模型类型）。写成 `(A B 栅 衬)` 会把数据变成栅极；写成 `(A 栅 衬 B)` 会把时钟节点变成源极——两种都让"传输门"退化成拉电源/地的管子。已用 `spectre/tg_test_on.scs` / `tg_test_off.scs` 三条判据钉死这个结论（ON 传 1.8/传 0，OFF 阻断）。注意：这条只适用于**端序本身**；当初我把移位单元的失败归因到端序和"1.1 V 分压指纹"，那个归因是错的，真因见 19。
18. **~~互补两相 TG 锁存链有 keeper/写入尺寸冲突，无法用调宽解决~~（已作废，结论下早了）**：那条"实测 q1 在 clk=1 期间塌掉、q2 max 仅 6 mV"是在 testbench 里 `vss` 根本没接地的电路上得到的（见 19），所以它证明不了拓扑有问题，也证明不了 keeper 强度有冲突。`spectre/shift_unit_tb.scs` 至今没有在正确接地下重跑过，不能拿它下任何结论。C²MOS 单元通过只说明 C²MOS 这条路线可用，不说明 TG 路线不可用。
19. **`vss`/`gnd` 这类"只接源极和衬极"的网络必须显式接地**，否则整版数字单元看起来"全是 PMOS 在工作、NMOS 全死"。 Spectre 不会因为 `vss` 不与 `0` 相连而报错——它就是个浮空节点，所有 NMOS 电流路径不存在，管子关断，节点靠结漏电和时钟交叠电容被泵到 VDD 以上（实测 x2→2.18 V、y2→2.35 V，`gmin` 被降到 10 fS），波形特征是"输出恒定 ≈1.8 V、gt 断言全过、lt 断言全挂"。判据与修复：`spectre/nmos_probe.scs` 同一个 `n18` 三种写法（顶层、subckt+`parameters`、subckt+字面值）在没接地时三条曲线完全相同且都不导通，加 `Vss (vss 0) vsource dc=0` 后三者都正常分压（g=1.8→0.758 V）——顺带证伪了"顶层 parameters 在 subckt 内不可见"这个猜测。以后新 testbench 第一件事就是把每个电源网络接到源上。

20. **`vsource type=pulse` 的时间轴是 `delay → rise → width → fall`**：高电平平台 `width` 是从**上升沿结束之后**才开始计时的。所以想让数据在 `T0` 翻转，必须写 `width = T0 - delay - rise`，否则实际翻转点会晚一个 rise time。本项目第一轮 hold 扫描就是这样测偏的（旋钮 -1 ns 实际测的是 +1 ns 一侧），修法见 `scripts/c2mos_margin.sh` 的 `wid=` 注释。
21. **过沿检测必须是相邻两点 + 插值，不能是"第一个越过阈值的采样点"**。后者在 `t0` 之前信号已经为高时会报出假沿，且时间分辨率被 maxstep 吃掉。判据：`v_prev <= VTH && v_now > VTH`（下降沿反之）+ 线性插值；找不到必须显式 NOT FOUND，绝不能回退到最后一个采样点。checker 自己用合成波形测：`python scripts/test_psf_check.py`（9 例），不许拿被测电路当 checker 的用例。
22. **报告与器件计数之间要有机检**，不要手改数字：`python scripts/netlist_stats.py` 从 netlist 解析 MOS 总数/型号分组，并扫全部报告里 `N 管 / N MOS / N transistors` 的断言比对；来源标签与绝对化措辞由 `python scripts/provenance_check.py` 机检（`spec_v12_text.txt` = 旧 GPT-6 方案，标成 `TEACHER_PAPER`/`COURSE_REQUIREMENT` 直接 FAIL）。两者都支持行级 `check:skip` 注记，用于"引用被废除说法以说明它被废除"的历史句，而不是用来绕过检查。
23. **`git push --force-with-lease` 不会让被替换的 commit 对象从 GitHub 消失**。重写元数据后本地历史干净、远端 ref 也干净，但服务端仍会按 SHA 继续服务旧对象（实测 10 个里 9 个还在返回，`author/committer` 字段里带着被清掉的手机号邮箱；`GET /repos/<r>/commits/<oldsha>` → 200，不在任何 ref 上）。仓库是 PRIVATE 时这些响应要鉴权，公开的那一刻就变成任何人可按 SHA 匿名读取。所以"本地历史 PHONE=0"不等于"可以公开"：公开前必须逐 SHA 确认远端不再服务（`No commit found for SHA`，HTTP 422 而不是 404），见 `python scripts/public_release_audit.py` 的 `SUPERSEDED_COMMITS_SERVED_BY_REMOTE`。服务端 GC 时间不可观测、不可催；要立刻干净只能换一个全新仓库（新对象网络从未含旧 commit）或删库重建，两者都需人工决定。
24. **被 commit 闸拦下的 staged 内容会以 dangling object 形式留在 `.git` 里**。`git add` 先把 blob 写进对象库，闸门再拒绝提交——被拒的内容并没有因此消失。实测：一次失败的 staging 留下 1 个 dangling blob + 2 个 dangling tree，`--mode objects` 把它算成 `VENDOR_MODEL_TRACKED_FILES = 1`（这条不是误报，正是应该发现的形状）。所以两件事要分开：`git fsck` 报 dangling 只是本地清理状态，不等于泄漏；泄漏的判据是"不可达对象的内容也要过规则"，由 `precommit_safety_check.py --mode objects` 负责。清理由 `git prune --expire=now --dry-run` 先看、确认全不可达再执行；远端是否还服务被替换的对象是另一回事，见 23。
25. **`git push` 报 `Recv failure: Connection was reset` / 443 连不上，而同一时刻 `gh api` 正常**时，是 git 的 HTTP/2 传输被打断，不是凭据、不是闸门。只对当次命令加 `-c http.version=HTTP/1.1` 即可通过（实测：连败 3 次的同一分支一次成功）。不要为此改全局 git 配置，也不要动 SSH 全局安全设置。
26. **`guest.sh pull` 会覆盖本地已审文件，pull 之后必须立刻 `git status` 核对**。实测：一次性拉 `results/*.csv` 时，guest 上那份**旧的** C²MOS 结果（缺第四阶段复验产生的 `rev1/revnom` 行，共少 267 行）把仓库里已审核的 5 个 CSV 覆盖掉了，而 diff 里只看得到"减行"，很像我在删数据。规矩：只 pull 本轮新产生的文件名（或先 `tar` 到 /tmp 再解到临时目录对比），pull 完立即 `git status --short`，凡是**已审文件出现在 M 列表里就当作事故处理**——把外来副本移到 `review/` 下留档（该目录 ignored），再用 `git checkout --` 还原，绝不在没搞清来源前提交覆盖结果。

27. **Automated Schematic Parameter Integrity Gate（自动生成的原理图必须逐实例回读有效参数）**：禁止仅根据实例数量、连接关系或黄金 Spectre 仿真结果，宣布自动导入的 Virtuoso 原理图正确。必须从 OA 数据库重新读取每个 PDK 器件的有效参数（本 build 实测：CDF 参数字典与实例上**同名**的 OA 属性是同一份存储，`smic18mmrf/n18|p18` 的参数名是 `l/w/fw/m/fingers/model`，不是 `wf/mult/area`；用 `cdfGetInstCDF` + `cdfFindParamByName` 或 `dbFindProp` 读，`cdfParseFloatString` 判断是否真成了数值），与黄金网表逐实例比较，并检查 CDF 参数求值；未完成时必须报告 BLOCKED，不得把黄金 W/L 回填到导出网表来掩盖导入错误（SCH-1 就是这么把 18 只全部停在 PDK 默认 180n/220n 的原理图判成 PASS 的）。机检入口：`python scripts/sch_parameter_integrity_check.py`（任一有效 W/L 不匹配、任一参数不可求值、任一器件意外落在默认尺寸都非零退出；合法等于默认值不误杀；`--pdk-default-*` 必须按**被测器件族**给，见第 29 条），用例 `python scripts/test_sch_parameter_integrity_check.py`（11 例：SCH-2 的 7 例 + 族默认值声明不一致、3.3 V 器件落在 350n 默认、宽度属性缺失三例）。完整过程与陷阱（含 `cdfUpdateInstParam` 会把实例属性删掉这条，以及 SCH-3 在 3.3 V 族上的复现）见 `reports/lessons_learned/spicein_cdf_parameter_mapping.md`。

28. **判断编辑器 API 是否可用不能用 `getd`**（2026-10-09 SCH-3 实测纠正）：`getd('schCheck)` 返回 nil，
    但 `errset(schCheck(cv))` 真能跑并返回 `((errors warnings))`（`data_sink_1ch` → `(0 2)`，两条 solder-dot
    警告；`c2mos_dff_1bit_paramfix` → `(0 5)`，与用户在 GUI 看到的 5 条同坐标）。`schCreate`/`schCreateWire`
    经字面调用确认仍不可用。所以：SCH-1/SCH-2 里"批处理没有 schCheck"这句话是**探测方法错了**，
    凡是"这个函数存在吗"的问题都要用 `errset(<字面调用>)` 回答，`getd`/`funcall` 在这条路径上不可信
    （与第 8 条同源）。§12 这类"检查并保存"的状态据此如实写成 schCheck 的返回值，不要把 dbCheck 包装成它。

29. **PDK 的 CDF 默认值随器件族改变，门的参数必须跟着改**（SCH-3 实测）：`smic18mmrf/n18|p18` 默认
    `l=180n w=220n fw=220n`，而 `n33`、`n33_dnw_4t_ckt` 默认 `l=w=fw=350n`。把 `--pdk-default-l 180n
    --pdk-default-w 220n` 复用到 3.3 V cell 上，`DEFAULT_VALUE_FALLBACK_COUNT` 会恒为 0，SCH-2 那种
    "整批管子停在默认尺寸还报 PASS"的事故就换个器件名继续隐身。永久闸现在自己核对：回读日志带出
    `RD3-MPARAM`（master 自己的 CDF 默认值），与命令行声明不一致就 `PDK_DEFAULT_DECLARATION_MISMATCH_COUNT`
    非零退出。另一条同源坑：CDF 会把 `1e-06` 规范化成 `1u`，raw 属性与 CDF 必须**比数值不比字符串**。

30. **GUI-1 的两条实测坑（2026-10-09）**。① `scripts/sync2guest.sh` 的暂存目录原本只按 basename
    命名，一次传两个同名文件（`appearance/white/xresources.txt` 与 `appearance/original/xresources.txt`）
    就会让后一份覆盖前一份，**两个目的目录都拿到同一份内容且毫无报错**——已改成按参数序号暂存；
    凡是"看起来同步成功了"的结论都要回读目标文件本身的内容，不要只看文件名。② 这台 VM 上
    **不能用截图验证 GUI**：`import -window root` 在 `:0`（1076x1277）上只回一张几百字节的平面图，
    按窗口 id 抓取要么全黑要么 `Resource temporarily unavailable`，连 `xmessage` 要求蓝/白也读成全黑；
    批处理 Virtuoso 会话也没有可绘制窗口（CIW `Map State: IsUnMapped`，无参 `hiOpenWindow()` 建出的
    Graphics 窗口在没有 cellview 画进去之前不重绘，`hiOpenWindow(?appType "Schematic")` => nil）。
    所以显示层结论一律写成 `GUI_VISUAL_VERIFICATION: PENDING_USER_REVIEW`，可测的部分改测
    X 会话数据库（`xrdb -query` 读回 + `xrdb -load <快照>` 恢复）。另记：`xrdb` 走 cpp，资源文件里
    含撇号的 `!` 注释会报 `Unterminated character constant`；`Opus` 的绑定要用紧格式 `Opus.res:`，
    Cadence 自带样例文件 `tools/dfII/cdsuser/.Xdefaults` 明确警告过松散绑定会与 SKILL 设置冲突。
31. **推 GitHub 一律走 `scripts/git_push_reliable.ps1`，失败时报告阶段而不是重跑命令**（NET-1 实测，
    2026-10-09，详见 `reports/git_network_diagnosis.md` 与
    `reports/lessons_learned/git_transport_instability.md`）。① git 跑在 **Windows**
    （Git for Windows 2.49.0.windows.1，`http.sslBackend=schannel`），guest 完全不在这条路径上——
    不要把 Windows 代理设置和 RHEL 网络配置混为一谈。② 实测根因：**到 `github.com:443`
    （`20.205.243.166`）的直连会间歇失败**，同一会话内从 5/5 成功翻到 0/5，坏在两个层
    （`Failed to connect ... port 443`，以及 `expected flush after ref listing` / `curl 28` 卡死）；
    而 `gh` 用的是 `api.github.com`（`...168`，另一个 IP），所以"gh 正常、git 失败"从来不是代理差异。
    git 在全局/仓库/URL/remote 四级都没有代理配置，代理环境变量三级全 unset，`gh`（Go）同样走直连——
    **"gh 用代理、git 绕代理"这个候选根因已被证伪**，不要再据此"修代理"。③ 已验证的传输：
    **配置代理优先，强制直连（`-c http.proxy=`）兜底**，两条候选都要先用 `git ls-remote` 实测再选；
    用户配置的本地代理在 `127.0.0.1:7892`，本轮所有经它的 git 操作零失败。为什么不把代理持久化成
    仓库配置：那会让裸 `git push` 依赖"代理软件正好开着"，新引入一种故障；脚本已能探测+回退。
    需要用户授权才做：`git config --local http.https://github.com.proxy <verified-proxy>`。④ 用 git 自带的
    `http.lowSpeedLimit=1024 / http.lowSpeedTime=10` 给传输设界，别让半开连接把脚本挂死；不要靠
    PowerShell 盯进程超时（5.1 没有原生 timeout）。⑤ 绝不用 `--force` / `--force-with-lease` /
    `--no-verify`，绝不 REST 改写 ref，绝不为连上而 `http.sslVerify=false`，绝不关身份验证；远端 SHA
    不是本地 HEAD 的祖先时**停下报告**；`main`/`master` 不由该脚本推。⑥ `LOCAL_REMOTE_PARITY: PASS`
    只在独立回读（换一条非 push 通道的 `ls-remote`，或 `gh api` 打 `api.github.com`）拿到
    `REMOTE_SHA == LOCAL_SHA` 时才允许；回读不到就写 `PUSH_REPORTED_SUCCESS / REMOTE_PARITY_UNVERIFIED`，
    不许按 push 的 stdout 猜。⑦ SSH over 443 现状：`ssh.github.com:443` 可达，host key 三张指纹与
    GitHub `/meta` 公布密钥逐一对上（所以不是被代理中间人），但本机没有 GitHub 身份
    （`Permission denied (publickey)`，`~/.ssh` 只有虚拟机密钥），且列账户公钥需要扩 token scope——
    因此 `SSH_443: AUTH_NOT_CONFIGURED`，**不生成/上传密钥、不写 `~/.ssh`、不换 origin**。
    要 SSH 路线必须由用户先注册公钥。⑧ PowerShell 的一条通用坑（就出在这个脚本上）：命令解析顺序是
    别名→函数→cmdlet→可执行文件，所以**函数名不能与外部程序同名**——`function Git(...)` 里的
    `& git` 会递归调用函数自己，直到 `CallDepthOverflow`，症状是"git 什么都没输出"而不是报错。
     helper 一律取名 `InvokeGit`/`Get-PreArgs` 这类带动词或带连字符的形式，并写 `& git.exe`。
    另两条同类坑：PS 5.1 不能 `function F(@a)` 再在体内 splat `@a`（解析错误）；`Out-String` 会把
    原生命令 stderr 的 `ErrorRecord` 打印成 `+ FullyQualifiedErrorId : NativeCommandError` 而吞掉
    git 真正的报错，必须 `if ($_ -is [ErrorRecord]) { $_.Exception.Message }` 展平，否则阶段分类失效。
32. **改 Virtuoso 桌面启动脚本之后，禁止只跑静态检查就宣布可用**（GUI-2 实测，2026-10-09，详见
    `reports/lessons_learned/virtuoso_desktop_launch_failure.md`）。双击报
    `There was an error launching the application.` 的真实原因是 `launch_virtuoso.sh` **丢了执行位**
    （mode 644），而 `.desktop` 的 `Exec` 和 `TryExec` 都指向该文件本身：GNOME 先
    `access(TryExec, X_OK)` 再 `execv(Exec)`，两处都要 X_OK，实测 `execv -> errno 13 EACCES / rc=126`。
    ① **为什么静态检查完全骗得过人**：`bash -n` 和 `LAUNCHER_CHECK=1 bash <脚本>` 都是用 `bash` 起的，
    **`bash` 不需要执行位**，所以两条都一路 PASS 而图标照样打不开。凡是"验证桌面/图标/外部启动器"的
    结论，必须按被验证者的真实调用方式去调（`execv` 目标本身），不能用解释器代跑。
    ② 执行位是 `scripts/sync2guest.sh` 弄丢的：它原本对每个同步文件**硬编码 `chmod 644`**，收尾只给
    `$PROJ/scripts/*.sh` 补 `+x`，不管 `cadence_work/`。已改成按 `git ls-files -s` 的 index mode 决定
    落地权限（`100755 -> 755`）。**同时**该文件在仓库里原本是 `100644`，即执行位只靠 guest 上一次手工
    `chmod`，所以修复必须三处一起做：guest `chmod 755` + `git update-index --chmod=+x <file>` +
    部署通道按 git mode 走；只做其中一处必然复发。
    ③ **白色背景不是原因，且已有证据**（不要再来回猜）：主题块只有 `say`，xrdb 失败也只打印
    `theme NOT applied`，**没有任何 `bail`/`exit`**；受控 A/B（只差 `QODER_THEME`）两种都启动成功、
    CIW 都 `IsViewable`；而只差执行位时结果立刻翻转。另记：`QODER_THEME=none/original` **只跳过本次
    merge**，不会删掉已在 X 会话数据库里的 `Opus.*` 资源，彻底恢复要
    `bash scripts/gui1_white_theme.sh restore`（`xrdb -load` 快照，不是 `-remove`）。
    ④ 复测入口：`scripts/gui2_verify_desktop.sh`（14 项静态全链路，**故意不做 execv**——否则每跑一次
    就真起一个 Virtuoso，改用 `os.access(X_OK)` 给同一判据，结尾固定输出
    `VIRTUOSO_GUI: UNVERIFIED_BY_THIS_SCRIPT`）；`scripts/gui2_real_launch.sh` + `gui2_envexec.sh`
    （把 `/proc/<gnome-session>/environ` 逐项交给 `env`，用**桌面会话自己的环境**execv 真正的 Exec
    目标，再证明有 virtuoso 进程**且**窗口 `Map State: IsViewable` + `WM_STATE: Normal`）。
    判 GUI 起来**必须轮询 IsViewable**：`libManager`/`libSelect` 以 `-unmapped` 启动是正常的分段启动，
    一开始 `WM_STATE: not found` 不代表失败。
    ⑤ 本机环境事实（省得再探）：`/root/.Xauthority` **不存在**，桌面真实
    `XAUTHORITY=/var/run/gdm/auth-for-root-*/database`；桌面 `PATH` 首项是 `/etc/env`（那个末尾会自己
    拉 GUI 的包装脚本目录），但 `cad_env.sh` 只 eval 其中的 `export` 行、IC617 bin 仍在 PATH 前，实测
    桌面环境下仍解析到 `/opt/IC617//tools/dfII/bin/virtuoso`，且 launcher 的
    `case "$BIN" in /opt/IC617/*)` 护栏会拒绝别的路径；metacity 在跑；成功会话里也会有一条
    `Display :0 Error "BadAtom"`，与本故障无关，别当根因。
    ⑥ **没能验证的部分不许伪造**：真正由 nautilus 驱动的双击无法模拟（这台 VM 取不到可信像素），
    一律写 `DESKTOP_DOUBLE_CLICK: USER_VERIFICATION_REQUIRED`。另：`cadence_work/desktop/`（`.desktop`
    源文件）因扩展名白名单不含 `.desktop` 而**未被 git 跟踪**，快捷方式本身没有版本记录，改坏找不回来。
    ⑦ 若无法完成完整 GUI 启动路径验证，必须显式写 `DESKTOP_GUI_LAUNCH: UNVERIFIED`，不得以
    `LAUNCHER_CHECK: PASS` 代替。
