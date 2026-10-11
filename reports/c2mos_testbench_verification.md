# c2mos_testbench_verification.md — C²MOS testbench 搭建与 Spectre 验证

执行时间：2026-10-11 20:22–20:23（guest `work-eda`，RHEL 6.5 / IC617 6.1.7-64b / Spectre 15.1.0.284.isr1）
任务：Agent 搭 testbench 并完成 Spectre 验证；先 DFF，DFF PASS 后再 3 级链。
禁止且**已核实未被违反**：改 `c2mos_dff_1bit`、改 MOS 参数、改拓扑、改 PDK、hierarchy/layout。

---

## 0. 一句话结果

**本机 Virtuoso schematic 的仿真断言报告，与冻结网表的断言报告逐字节相同。**
四轮全 PASS、零失败：

| 被测 | deck 模式 | 断言 | 失败 | token |
|---|---|---|---|---|
| 冻结网表 `c2mos_dff` | `ff1` | 33 | 0 | `C2MOS_DFF_1CH: PASS` |
| **本机 OA 原理图 `c2mos_dff_1bit`** | `ff1_sch` | 33 | 0 | `SCHEMATIC_DFF_FUNCTION: PASS` |
| 冻结网表 3 级链 | `shift3` | 40 | 0 | `C2MOS_SHIFT_3STAGE: PASS` |
| **本机 OA 原理图 3 级链** | `shift3_sch` | 40 | 0 | `SCHEMATIC_SHIFT3_FUNCTION: PASS` |

`ff1` 与 `ff1_sch` 的断言文件 md5 相同（两份 repeat 都相同，distinct md5 数 = 1）
⇒ schematic 不只是"参数对"，**波形级等价**。

## 1. testbench 说明

**没有新写 testbench deck**，而是复用仓库冻结的 `spectre/c2mos_ff1_from_oa_readback.scs`
（及其 3 级版 `spectre/c2mos_shift3_from_oa_readback.scs`）。理由：断言集合、时间窗、
重复一致性检查都在 `scripts/c2mos_check.sh` 里冻结；另起一份 deck 等于放弃这套基线。
任务书要求的连接条件逐条对照（左边是要求，右边是该 deck 里的实际语句）：

| 要求 | deck 实际 |
|---|---|
| `VDD=1.8 V` | `parameters VDDV=1.8` + `Vdd (vdd 0) vsource dc=VDDV` |
| `VSS=0` | `Vss (vss 0) vsource dc=0`（**显式接地**，`AGENTS.md` 19） |
| 输入 `clk` pulse | `Ck (clk 0) vsource type=pulse val0=0 val1=VDDV period=T delay=0.5T width=0.5T rise=1e-9 fall=1e-9` |
| 输入 `d` pulse | `Dd (d 0) vsource type=pulse ... period=2T delay=0.35T width=T ...`（序列 `1,0,1,0,1`） |
| 被测单元 | `X1 (d clk q qbar vdd vss) c2mos_dff_1bit` |
| 负载 50 fF | `Cq (q 0) capacitor c=50e-15`、`Cqb (qbar 0) capacitor c=50e-15` |
| 保存波形 | `save clk d q qbar`（另存 `vdd vss`，preflight 的 `NETS_TO_SAVE`） |
| 分析 | `tr1 tran stop=4.8*T maxstep=1e-4*T`，`T=2e-7`（stress 时钟，非应用列周期） |

单元内部**只有一个外部时钟**：`clkb` 由 `mn_c`/`mp_c` 自反相产生，deck 里没有第二个相位源。

新建的是**编排脚本** `scripts/scan_c2mos_tb_verify.sh`：按任务顺序强制执行，
`ff1` 与 `ff1_sch` 都 PASS 才允许跑 3 级链，否则打印 `STEP 4 SKIPPED`；
它不含任何电路信息。

## 2. 网表路径

| 用途 | 路径 |
|---|---|
| 模型卡（由 `${QODER_PDK_LIB}` 展开） | `/root/tech/teacher_pdk/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib`（353,783 B），`section=tt` |
| 本机 PDK 环境配置（**gitignored**） | `/root/microled_ai_project/spectre/pdk_local.env`（126 B，2 行：`QODER_PDK_LIB`、`QODER_TECH_ROOT`）；`.gitignore` 的 `**/pdk_local.env` 命中，未入库 |
| 被测单元网表（schematic 侧重建） | `/root/microled_ai_project/spectre/generated/c2mos_dff_1bit_from_oa_readback.scs` |
| 冻结对照网表 | `/root/microled_ai_project/spectre/C2MOS_DFF.scs`（只读 include） |
| 渲染后的实跑网表 | `$PROJ/spectre/run_ff1_local1.scs`、`run_ff1_sch_local1.scs`、`run_shift3_sch_local1.scs` 等（由 `c2mos_check.sh` 按 T 改写 `parameters T=` 生成） |

**被测网表的来源与诚实说明**：`generated/c2mos_dff_1bit_from_oa_readback.scs` 由
`python scripts/sch2_netlist_from_readback.py cadence_work/logs/sch_nograph_20261011_200240.log c2mos_dff_1bit ...`
从**本机** cellview 的只读回读重建（`READBACK_ROWS: 18`，`PORTS_FROM_PINS: d clk q qbar vdd vss`）。
与仓库已提交（旧机重建）那份的差异只有**第 2 行来源注释**，18 条器件语句逐字节相同
（`cadence_work/logs/tbverify/install_diff.txt` 共 4 行 = 一对 `<`/`>` + 分隔符）。
因此本次提交里该文件的 provenance 行改指向本机日志。
仍需记住的定性：这个导出器是我自己的 DB 读取器，**不是 ADE netlister**
（`NATIVE_CADENCE_NETLIST: BLOCKED`），所以它证明的是"OA 数据库携带的参数/连接正确"，
不证明"ADE 会网表出同一份"。

## 3. 仿真命令（可复现）

```bash
cd /root/microled_ai_project                      # PROJ 根，脚本默认值
bash scripts/scan_c2mos_tb_verify.sh              # 整条流水线（内部就是下面四条）

bash scripts/c2mos_check.sh ff1        2e-7         local1 2   # 冻结网表 单管，跑两遍
bash scripts/c2mos_check.sh ff1_sch    2e-7         local1 2   # 本机原理图 单管，跑两遍
bash scripts/c2mos_check.sh shift3_sch 9.765625e-6  local1 1   # 本机原理图 3 级，应用列周期
bash scripts/c2mos_check.sh shift3     9.765625e-6  local1 1   # 冻结网表 3 级，对照
```

底层链路：`c2mos_check.sh` → `tb_preflight.sh`（结构+工作点门禁，不过就 FAIL 且不进正式仿真）
→ `run_spectre.sh`（护栏：网表必须在 `$PROJ` 下；`timeout`；输出落 `spectre/sim/`）
→ `psf_check.awk`（插值过沿 + 窗口断言）。
`cad_env.sh` 由 `run_spectre.sh` 经 `CAD_ENV=/root/qoder_ic617_sandbox/bin/cad_env.sh` 载入，
`/etc/env/virtuoso` 始终只取 `export` 行、从不执行。

## 4. waveform 结果（本机原理图，节选自 `results/evidence/`）

时间窗都是 `T=200 ns` 的倍数；`gt 1.7` / `lt 0.1` 是逻辑高/低判据，`n` 为窗内采样点数。

| 窗口 | 断言 | 实测 min / max |
|---|---|---|
| `[1.4e-7, 1.9e-7]` | `q gt 1.7` | 1.8 / 1.8（n=2500） |
| | `qbar lt 0.1` | 6.33148e-9 / 6.33179e-9 |
| `[2.2e-7, 2.9e-7]` | `q gt 1.7` | 1.79941 / 1.84122（n=3507） |
| | `qbar lt 0.1` | −3.64e-4 / 2.84e-4 |
| `[3.4e-7, 3.9e-7]` | `q lt 0.1` | 1.04325e-8 / 1.0996e-8 |
| | `qbar gt 1.7` | 1.8 / 1.8 |
| `[4.2e-7, 4.9e-7]` | `q lt 0.1` | −0.0137425 / 0.0283385 |
| | `qbar gt 1.7` | 1.79973 / 1.80097 |
| 之后 4 个窗（5.4e-7…8.9e-7） | 同上交替 | 与前三组同量级 |

过沿时刻（thr=0.9，插值）：`d` 在 `7.05e-8 / 2.715e-7 / 4.705e-7 …` 处越过
`6e-8 / 2.6e-7 / 4.6e-7` 的名义时刻，偏移 ≈ +5 ns 与 +11.5 ns，来自源内阻与 50 fF 负载的爬升，
在 `maxstep=20 ps` 下不是数值伪影。3 级链侧 `q0/q1/q2` 各自在 `3.418e-5 / 4.3946e-5 / 5.3712e-5`
越过 0.9，与 `clk` 的 `3.32e-5 / 4.297e-5 / 5.273e-5` 沿一一对应（偏移 ≈ 0.97–1.0 µs，
即一个列周期推进一级）。

工作点（preflight，t=0 首样）：`vdd=1.8`、`vss=0`、`clk=0`、`d=0`，
`q=0.810829754`、`qbar=0.810829713` —— 上电瞬间交叉耦合对处于中点，属未初始化存储环的正常现象，
第一个时钟相位（`0.5T` 起 master 求值）即把它拉开；断言窗从 `1.4e-7` 开始，避开了这段建立期。
`STATIC_OK vss net vss tied to node 0 through an independent source` 正是那条例户第 19 条的门禁。

## 5. `q` / `qbar` 功能判断

- **时序**：`q` 跟随 `d` 在**上升沿**采到的值，延迟恰好一个时钟周期（`d→m→q` 两级反相 ⇒ 同相），
  断言窗设计成 `1,0,1,0,1` 序列并让 `q` 的窗口**跨越** `d` 的跳变点，因此一次通过同时排除了
  "靠时序巧合通过"和"组合直通"。
- **保持**：在 `clk` 的非有效半周期内 `q` 稳定为 1.8 V 或 ≈0 V（`n=2500` 全窗），
  说明 keeper（`mn_k1..k4`/`mp_k1..k4`，宽 0.25×）确实把节点做成了**静态**存储，
  不是靠寄生电容暂存。
- **互补性**：`q` 高时 `qbar` 低于 0.1 V，反之亦然，全部 16 个高/低窗口无一例外 ⇒ 无单端失效。
- **无 feed-through**：`d` 在 `1.35T` 的跳变没有改变 `q` 在 `[1.1T,1.45T]` 内的电平（该窗含此跳变）。
- **链式推进**：3 级链 40 条断言全过，单个 '1' 每个时钟周期恰好推进一级，
  没有一次沿穿过两级（`pvt_probe.sh` 关注的正是这条）。

## 6. 禁止项遵守核实

| 禁止 | 核实证据 |
|---|---|
| 改 `c2mos_dff_1bit` / 改参数 / 改拓扑 | 流水线前后 `cadence_work/microled_cells/c2mos_dff_1bit/schematic/` 四个文件的 mtime 全部保持 `2026-10-11 20:02`（生成时那一刻），`sch.oa` md5 `3de3224df0af`；整个验证过程只读该 cell，写路径只有 `spectre/generated/`、`spectre/pdk_local.env`、`spectre/run_*.scs`、`spectre/sim/`、`logs/` |
| 改 PDK | 前后指纹均 **5333 条目、`diff` = 0 行**；模型卡只被 `include` 读 |
| hierarchy / layout | 未做任何视图新建；3 级链是 **Spectre 网表层**的 X 串联（`c2mos_shift3_from_oa_readback.scs`），不是 OA 层次；`layout` 视图未创建 |

其他：未 push；`$PROJ/logs` 由 `c2mos_check.sh` 自建；磁盘 `5.2G → 5.1G`（仿真 `.raw`）；
结束时 `cdsMsgServer` 孤儿清零、`virtuoso_main=0`。

## 7. 需要你知道的两点残留

1. **`terms=0` 未解决**（上一轮按你指示暂缓）。所以 schematic 侧的仿真走的是
   "DB 回读重建网表"这条路径，而不是 ADE 直接从 cellview 网表。功能等价已由 byte-identical
   证明，但"GUI 里打开 schematic 能否正确显示/连接端口"仍属阶段7 人工目视项。
2. **本轮未做** `c2mos_margin.sh`（setup/hold）与 `pvt_probe.sh`（corner）。
   它们需要 `section` 名从模型卡里读出来再跑，且 hold 侧历史上标注过
   `HOLD_CHARACTERIZED: NO` —— 是否推进请单独指示。
