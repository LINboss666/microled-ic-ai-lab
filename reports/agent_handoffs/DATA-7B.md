# DATA-7B 交接（单通道固定电流 PWM 响应验证）

日期 2026-10-21。任务书：`reports/tasks/DATA-7B.md`（逐字节副本，SHA-256
`0f4db71f752aef5db9869fe097703a423266f433ee2e4040f621c7b0c6e21389`，34,198 B）。
结构化字段在 `reports/agent_handoffs/DATA-7B.json`；本报告不写自身摘要，最终 SHA 从 Git ref 读。

## 1 身份

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/LINboss666/microled-ic-ai-lab |
| 工作分支 | `poc/data-pwm-d7b`（本轮新建，远端原无同名分支） |
| Git 开发基线 B | `c3513ffee57880bdc9d6d26d5c1c1a9a43c52e37` |
| 被接受的 DATA-7A 内容 A | `f68449672774ac9266ba9e4893024e4f3027dd9d`（B 的父提交） |
| main（未动） | `23e471cb936b421ee97e1250c3be06edf96f9937` |
| 冻结摘要核对 | 任务书 §1.2 的 12 项按 `git cat-file blob B:<path>` 计算，12/12 一致 |
| 工具 | 本机 `oss-cad-suite 2026-10-20`（Icarus 14.0 devel / Yosys 0.70+176）；guest RHEL6.5 + IC617 `spectre -64`，Python 2.6.6（仿真侧）/ 本机 Python 3.12.5（编排与测量） |
| 交付 run | `results/evidence/dd1_d7b_r11_main/`（24 DUT 案例 + 复用标定 `r5_cal` + 复用黑码/一码运行 `r11_reuse`） |

## 2 实际做了什么

1. 用**未改动的** `rtl/dd1_d7a_gray_ctrl.sv` 与新 TB `tests/dd1_d7b/tb_dd1_d7b_pwm.sv` 跑真实四态仿真，
   得到 17 份 trace（15 个正常码窗口 + BLANK/FAULT 各含中止与恢复两窗）。`t0` 取**消费 tick 的参考时钟沿**
   （`obs_tick` 比它早 5 ns，已机检 17 份一致），平移 2,500 ns，斜坡 50 % 位置钉在真实沿上。
2. 独立手写黄金表 `tests/dd1_d7b/golden_windows.csv` 核对窗口/边界事件数/导通宽度/脉冲数；
   17/17 通过，且检查器不从 DUT 的 `target_q` 反推期望。
3. 新建 7 管 wrapper `spectre/dd1_d7b_pwm_stage.scs`（只实例化三个冻结 master），
   `n18×1, p18×1, n33×4, n33_dnw_4t_ckt×1`，由 subckt 展开机检。
4. 冻结 runner/preflight/supply checker 逐字节复制进任务根并核摘要；`vdd18=1.8 vdd=1.8 vss=0 VSS=0`
   契约在**展开全部非 PDK 层级**后判 `SUPPLY_INSTANCES top=1 descendants=3 checked=6 internal=0
   masters=4 / PASS`；24 份 deck 全部先过静态闸（`PREFLIGHT_STATIC_PROBE=1`，0 次启动）。
5. 原生矩阵：24 DUT + 24 动态 rail preflight，TT / 27 °C / 钳位 1.2 V / `gear2only`，
   4 例以 0.25 ns 复测收敛，1 例改 10 ns 输入斜率。零负担 `Ip_out (clamp data_out) iprobe`，
   读原始有符号电流。
6. 离线自证：trace 13 项、measure 18 项（含 3 个破坏例）、entry 9 项（含 4 个破坏例）、
   `dd1_d7b_evidence_check.py` 20 项（其中 25 个窗口的电荷从交付样本重算）。

## 3 结果（验证可靠与电气达标分开）

* `EVIDENCE_STATUS = PASS_WITH_BUDGET_EXCEPTION`：20 项证据检查里 19 项 PASS；
  唯一 FAIL 是 `BUDGET_RESPECTED`（见 §4）。
* `PWM_CURRENT_FEASIBILITY_TT = PASS`：全部 24 个判定窗（含黑码、中止窗、恢复窗、N1 之外的正常窗）
  满足 `|charge_error_LSB| <= 0.5`；关闭后末 100 ns `max|Iout| <= 0.15 uA`；`Ical = 14.93190564 uA`
  在 15 uA ± 5 %；`D7B-N1` 真实接线负例被同一检查器判 `EXPECTED_REFUSAL / WIRING_FAULT_DETECTED`，
  `D7B-N2` 静态供电负例在 `stage=supply_contract` 以 rc=1 被拒且该目录 0 次启动。
* 如实记录的**未达标项不是电荷**，而是时间行为：30/50 ns 量级的短窗一律 `NOT_SETTLED_WITHIN_PULSE`
  （窗内从未持续 10 ns 入带），峰值电流在导通初期冲到约 16.8 uA；这与 TI SSZT647 描述的
  "使能式 PWM 建立/关断限制最短可用脉宽"一致，但不构成光学或亮度结论。
* 完成级别：`RTL_TRACE_DRIVEN_MOS_OUTPUT_MEASURED_TT`。

## 4 失败与成本（不得抹掉）

| # | 我自己的缺陷 | 后果 | 修法 |
|---|---|---|---|
| 1 | TB 的 BLANK/FAULT 忘记写入 code 16，首窗成了黑码 | 中止窗 0 导通（复现期发现，未耗额度） | TB 补 `pure_code=16`，重跑全部 trace |
| 2 | 中止事件锚在 `obs_tick` 上升沿（比采样沿早 5 ns） | 与 t0 定义不一致 | 改为 `@(posedge obs_tick); @(posedge clk)` 后计时；t0 统一定义为消费沿 |
| 3 | PWL 写成 `wave=(t v)(t v)` | 本机读入 SFE-874，1 次失败启动 | 采用已验收的 `wave=[t v t v ...]` 纳秒拼式 |
| 4 | 把"整皮秒"规则误用到 PSF 采样网格 | 拒收真实仿真数据，1 次失败案例 | 新增 `float_samples` + 显示量化界 `time_quantum_ps`，交付样本带界 |
| 5 | deck stop 与测量边界重合，末样本比 stop 早 ~4 as | 尾窗积分越界拒收 | `STOP_MARGIN_NS=50`，边界两侧都有夹持样本 |
| 6 | 分片按固定行数切，单片 465 KB 超限 | 一次崩溃（1 次启动被计入失败） | 按实测字节自适应切分，并去掉每行重复标识列 |
| 7 | 字段里出现逗号导致 CSV 列错位 | 复用行摘要串列 | `write_rows` 加逗号拒写闸，并修正该行 |
| 8 | "复用分支"补丁插进 `static_probe` 的循环 | 本应 0 启动的补齐轮新起 4 次进程 | 交付集改由 `launches_reconcile.csv` 逐目录对账 |

**额度结论：guest 侧实测 59 次 Spectre 进程**（`launches_reconcile.csv` 逐目录可核）。
交付矩阵本身用掉 48 次（24 DUT + 24 动态 preflight），其余 11 次是我上述缺陷的成本。
任务书授权 52，用户本轮追加 4（上限 56），因此**超出授权 3 次**。发现后即停止，未再启动任何进程，
未把任何一次失败说成"不计数"。

另有一条工具缺陷要留给下一轮修：进程账本写在共享路径，崩溃的轮会覆盖它，所以交付包里的
`process_ledger.csv` 只有 27 行（r5_cal/r11_main/r11_reuse 的幸存记录）；真实总数只能靠
`launches_reconcile.csv` 与 guest 文件计数对上。

## 5 边界与未做（本轮不主张 anything else）

PWL 是离线验证激励，不构成全 MOS 灰阶控制器、混合信号联合仿真、片内数字单元映射或八档 PAM 的完成证明；
后续产品仍计划片内产生 PWM。未做：八档 PAM/电流 DAC、LUT 与光学标定、LED I–V、真实互连 RC、
最终 VSCAN/VLED、CDC/skew、阵列与多通道、corner/温度/MC、版图/DRC/LVS/PEX、OA 与 Virtuoso
（`NEW_OA_WRITES=0`，未启动 dbAccess/Virtuoso，未改 PDK 与他人库）、TCON/HDMI、DATA-7B 之外的
任何下一阶段内容。VM 未做电源/快照/.vmx/license 操作；网络只做了用户批准的
`dhclient -1 eth0`（临时租约，未改 `ifcfg-*`）。

## 5.5 推送与回读

普通 push 新分支 `poc/data-pwm-d7b`（非 force、未跳 hooks）；Git 协议与 GitHub API 两条独立路径
都回读到同一 tip，`main`、`poc/data-gray-d7a-r4-doc` 与其余旧分支逐条比对未动。
`head_sha` 固定为功能 payload 提交，分支 tip 与最终包身份从 Git ref / 包外回执读，本文件不写自身 SHA。

## 6 下一步（等云端独立审核，不由执行者给 GO）

1. 短窗不入带与 ~16.8 uA 导通峰值是本轮最实的物理发现；是否为此改动输出级由用户决定。
2. 若要继续，建议先补"最短码的电荷-脉宽曲线"（同一 7 管结构，扫 N=1..8）而不是先做 PAM 译码。
3. 本轮遗留的工具修复：账本写入按 run 隔离；`--reuse` 分支位置；把 20 项证据检查里的预算项改成读
   `launches_reconcile.csv` 的唯一权威源。

`NEXT_STAGE_AUTHORISED=NO`、`SOA_SIGNOFF=NO`、`MERGE_PERFORMED=NO`（`main` 与所有旧分支未动）。
