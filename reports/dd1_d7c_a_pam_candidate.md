# DATA-7C-A 候选方案与离线验证：八档 PAM 电流最小单元（2026-10-23）

任务书逐字节副本 `reports/tasks/DATA-7C-A.md`（20,917 B，SHA-256
`3b55cef702da35786d68b533c0af363b4e6419d62acc2cd9d94ee7bf6051f180`，与用户附件字节相同，LF-only）。
本轮范围 `SCOPE=ONE_OUTPUT_EIGHT_LEVEL_PAM_CANDIDATE_MOS_AND_OFFLINE_VERIFICATION`。

**这份文件里没有任何电学结论。** 所有器件、比例、时序、电荷与档位数值都是 `CANDIDATE` /
`ENGINEERING_DERIVATION`，用于让下一轮的原生验证有明确对象；`NATIVE_NETLIST_SYNTAX=NOT_VERIFIED`，
`PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN`。本文件不写自身摘要，本轮 tip 从 Git ref 读。

| 身份 | 值 |
|---|---|
| 任务 / 基线 | `DATA-7C-A`，base = 登记提交 `272d6de6d2f2fc8a82d5038d73d6b3e4c656f683` |
| 已接受 DATA-7B 内容 | `f9fd09b184a69a27cdb409205dfd4f4151408a23`（`poc/data-pwm-d7b-r3`，独立复审限定 GO） |
| 本轮分支 / 工作树 | `poc/data-pam-d7c-a`（新建）/ `D:\ic617_d7c_a` |
| main | `23e471cb936b421ee97e1250c3be06edf96f9937`（不得移动） |
| 本轮成本 | 新增 Spectre **0**；新增 RTL 仿真 **0**；新增 OA 写入 **0**；无 `spectre -h`、无动态 preflight、无 SSH/VM、未读凭据 |
| 文件范围 | 对 base **仅新增**：0 条既有路径修改、0 删除 |

## 0 操作记录

1. 动工前两条独立通道回读：`git -c http.proxy=http://127.0.0.1:7892 ls-remote origin`（rc=0，22 行 ref）
   与 `gh api repos/LINboss666/microled-ic-ai-lab/git/ref/heads/<ref>`（rc=0，5 个 ref），
   查询时间 `2026-10-23T05:47:21Z`（本机 UTC）。两者对 `poc/data-pwm-d7b-r3 = 272d6de…`、
   `poc/data-pwm-d7b-r2 = b3fe93c…`、`poc/data-pwm-d7b-r1 = e97f02e…`、`poc/data-pwm-d7b = adcdf27…`、
   `main = 23e471c…` 一致；`f684496…` 另经 API 读到提交对象（DATA-7A 内容）。
   `git rev-list --count 272d6de..origin/poc/data-pwm-d7b-r3 = 0`，远端不比基线新，无需只读吸收他人代码。
2. 身份校验：`git rev-parse 272d6de^` = `f9fd09b…`；登记轮差异 `--name-status` 为
   **2 修改**（两份交接）+ **5 新增**（`reports/reviews/DATA-7B-R3/`），0 删除，
   `scripts/ results/ rtl/ tests/ spectre/` 出现 0 次——核心源码与证据未动，与复审声明一致。
3. 新建分支与隔离工作树；未删除或覆盖任何同名目录/分支，未在旧分支上写入。
4. 只读输入：`spectre/dd1_d6_inv18.scs`、`dd1_d6_bias_core.scs`、`dd1_d6_sink_core.scs`、
   `rtl/dd1_d7a_gray_ctrl.sv`、两份合同、`spec/system_requirements.md`、复审包内文档。全部按原字节读，未改。
5. 语法来源标注：`isource`/`iprobe`/`vsource`/`dc dev=… param=dc start=… step=…`/
   `include "${QODER_PDK_LIB}" section=tt` 取自仓库内已实测的 `spectre/current_probe_syntax.scs`；
   端序 `Name ( d g s b ) ModelName` 取自 `AGENTS.md` 坑 17；`vss` 必须显式接地取自坑 19；
   `type=pulse` 的 width 计时口径取自坑 20。**层级 `save` 与 `type=pwl` 加到译码输入这两项本仓库尚无实测**，
   在 bench 草稿里显式标 `NOT_VERIFIED`。

## 1 未定义项与来源等级（先把边界钉住）

| 事实 | 等级 | 限度 |
|---|---|---|
| Data 接 N 极作恒流下拉、Scan 接 P 极作高侧开关 | 项目既有分工 | 本轮不改方向，不重证 |
| Pure 8-bit 时间码 / Hybrid 6-bit 时间码 + 3-bit PAM 请求码 | 已冻结数字契约（`dd1_d7a_contract.md` §1/§2） | 不是光学 9 位有效位数的证明 |
| Pure 码 255 → 256 区间；Hybrid 时间码 63 → 64 区间 | 已冻结契约 | 本轮不改写成 255/63 |
| 15 µA = 像素被选通发光时的瞬时电流 | `COURSE_REQUIREMENT`（`spec/system_requirements.md` R3，题面+学生确认） | 不是帧平均，不是档位规格 |
| 15 µA 参考、1.8 V 逻辑、VCAS=1.8 V、输出夹持 1.2 V、TT/27 °C | 继承的单通道 POC 测试条件（DATA-7B） | 不是最终 VLED/VSCAN，不是 SOA 额定 |
| **八个实际 PAM 电流值** | **NOT DEFINED** | `dd1_d7a_contract.md` 明写"1.875/3.75/…/15 µA 未被采纳为正式档位值" |
| 下文候选 A 的档位表、拓扑、几何 | `POC_CANDIDATE` / `ENGINEERING_DERIVATION`（任务书给出） | 不是题目要求，也不是仿真结果 |
| 器件几何合法性（`n33`/`n33_dnw_4t_ckt`/`n18`/`p18` 的 wmin/lmin/多指规则） | `GEOMETRY_NOT_VERIFIED` | 本轮不读 guest/PDK 原件来补，不称"已过 PDK" |

`spec/system_requirements.md` 是早期登记，其"未做任何晶体管级设计"等状态**已被 DATA-7A/7B 的接受记录取代**；
本轮只按它的 R3/R8/R9 与 U10 条目取"电流"与"未定义"两类事实，不拿旧状态覆盖新记录。

## 2 三个候选定义的比较（不混表）

### 2.1 候选 A：八个相同单位支路，开启数 = `pam_sel + 1`（本轮交付源网表）

外部参考恒为 15 µA，理想镜像给 `Iunit = 15/8 = 1.875 µA`。导通支路数与掩码
（`unit_mask[7:0]`，`bit0` = 第 0 支路）：

| pam_sel | 导通支路 | unit_mask | 理论目标 µA |
|---|---:|---|---:|
| 000 | 1 | 00000001 | 1.875 |
| 001 | 2 | 00000011 | 3.750 |
| 010 | 3 | 00000111 | 5.625 |
| 011 | 4 | 00001111 | 7.500 |
| 100 | 5 | 00011111 | 9.375 |
| 101 | 6 | 00111111 | 11.250 |
| 110 | 7 | 01111111 | 13.125 |
| 111 | 8 | 11111111 | 15.000 |

`DATA_EN=0` 时八条全部关断。第 0 支路只在发光使能时构成基础电流，**不是永久导通**；
黑色由时间码 0 或 `DATA_EN=0` 控制，不把码 000 写成 0 µA。
端点：最小 1 单位，满档 8 单位 = 参考本身；步长 1 单位；
八条支路同尺寸，因此免去权重匹配与进位切换；理想权重精确时 DNL 可以为 0，但**实测 DNL 由失配决定**，本轮没有失配数据，不作零 DNL 断言。代价是器件数与译码规模翻倍，且完全依赖译码正确性。

### 2.2 候选 B：同一 A 电流表的"基础 1 单位 + 二进制 1/2/4 单位"四支路

要得到 1…8 单位（注意 A 的档位是 1..8，不是 0..7），四支路权重必须取 **1, 1, 2, 4**
（一个基础单位 + 二进制 1/2/4），而不是只写 1/2/4：三条二进制支路只能凑出 0..7，
缺"至少一个单位恒亮"的语义就凑不出 A 表的 8 个正档。逐条代价：

| 维度 | 候选 B 相对 A |
|---|---|
| 支路数 | 4 条（A 为 8 条），面积与布线少 |
| 权重器件 | 4 单位支路的 `Mout` 需 4 × 2.5 µm = **10 µm**（或等价 multiplicity），2 单位为 5 µm；A 全是同尺寸 2.5 µm |
| 进位切换 | 码 011→100 一类边界要**同时**断开 1+2 与接通 4：单次换码瞬间可能只剩基础 1 单位或出现 1+2+4 重叠，电流毛刺与电荷误差不由理想表决定 |
| 器件匹配 | 加权管与单位管的**失配贡献随权重放大**（4 单位支路的绝对失配大于单位支路），但这需要器件误差模型才能给出 DNL 数值；本轮没有 PDK 失配数据，只作定性说明 |
| 偏置负载 | 共享参考节点上的 pass 管少一半，但每支路局部偏置节点数也少一半，换码瞬态不同 |
| 译码 | 需 3→4 位二进制展开而非温度计，逻辑少但关键路径在进位 |

一句话口径：**理想权重精确时，温度计与二进制加权都可以有 DNL = 0**；温度计的优势是免去权重匹配与
进位切换，不是"结构性零 DNL 的证明"。没有失配与工艺角数据之前，本文件不作"二进制必然非零 DNL"的断言。

本轮**不搭 B 的完整网表**，只把它的权重/进位/匹配/偏置负载写明，供审核方决定是否值得用面积换掉温度计结构。

### 2.3 候选 C：常规 0…7 单位、满档 15 µA

`Iunit = 15/7 µA ≈ 2.142857 µA`，码 000 = **0 电流**（不发光的幅度码），码 111 = 7 单位 = 15 µA。
端点、步长与 A 不同，且**含 0 档**，因此 A 与 C 的"最小非零档""步长""DNL 定义"不可混在同一张结果表里。
不在 A 候选里混用 C 的理由：A 的语义把"是否发光"完全交给 `DATA_EN` 与时间码（本项目的
Pure/Hybrid 契约都是时间码 0 = 黑），幅度码因此不需要表示 0；若同时引入 C 的 0 档，
同一黑色会出现两条路径（时间码 0 与幅度码 0），下一轮的电荷判据就要先定义哪条权威。

## 3 拓扑、接口与逐管说明

### 3.1 顶层接口映射

候选顶层 `dd1_d7c_a_pam_1ch`（`spectre/dd1_d7c_a_pam_top.scs`）只需以下功能端口：

| 顶层端口 | 方向 | 域 | 来自/去向 |
|---|---|---|---|
| `data_en` | input | 1.8 V | 已接受控制器 `dd1_d7a_gray_ctrl.data_en`（本轮只准备接口，不连接、不改控制器） |
| `pam_sel0/1/2` | input | 1.8 V | 控制器 `pam_sel[2:0]`；bit0=权重 1，bit1=权重 2，bit2=权重 4 |
| `iref_in` | input | 模拟 | 测试台 15 µA 电流计注入的二极管连接参考节点，**不是理想 VBIAS** |
| `vcas` | input | 模拟 | 共源共栅偏置，继承 POC 值 1.8 V |
| `data_out` | **output（唯一）** | 模拟 | 一个电流下拉输出 |
| `vdd18` | inputOutput | 1.8 V | 只喂译码器 |
| `vss` | inputOutput | 地 | 参考、支路与译码器共同回流；bench 里必须显式接 0 V 源 |

控制器输出的 `data_en_b` **不在这里复用**：每条支路的 `EN_B` 必须是本支路 `EN` 的反相节点，
因为八条支路的 `EN` 各不相同，共享补信号在物理上就不足够（这一点复审可直接从网表反驳）。

### 3.2 层次（可从网表机械追出，不是文字图）

```text
CANDIDATE / NOT SIMULATED  —— 依据 spectre/dd1_d7c_a_pam_top.scs 与其包含的文件
dd1_d7c_a_pam_1ch            145 MOS（展开）  唯一输出 data_out
├─ Xref   data_bias_ref        1 MOS   Mref n33  (D=G=iref_in, S=B=vss)  二极管连接，W=20µm L=2µm
├─ Xdec   dd1_d7c_a_pam_dec  112 MOS   3 位请求 → 温度计选择 → 每支路使能与真实反相
│   ├─ Xterm_or10  dd1_d7c_a_or2   6 MOS  gor10 = pam1 | pam0
│   ├─ Xterm_and10 dd1_d7c_a_and2  6 MOS  gand10 = pam1 & pam0
│   ├─ Xsel1/Xsel2/Xsel3        dd1_d7c_a_or2   select1/2/3
│   ├─ Xsel5/Xsel6/Xsel7        dd1_d7c_a_and2  select5/6/7      select4 = pam2（直接连线）
│   └─ Xn<j>/Xa<j>/Xb<j>        nand2 + inv + inv  ×8   en<j> = data_en & select<j>，enb<j> = ~en<j>
│       （select0 = vdd18 轨，第 0 支路的与门一个输入接轨，不是浮空、也不是理想常量源）
└─ Xu0 … Xu7  dd1_d7c_a_sink_unit  4 MOS 一条，八条支路共 32 只器件   每条支路一个 DATA_OUT 端口，全部并到 data_out
    ├─ Mpass_local  n33_dnw_4t_ckt (D=iref_in G=en<j> S=vbias_ch B=vbias_ch) W=5µm L=2µm   继承宽度
    ├─ Mbleed_local n33              (D=vbias_ch G=enb<j> S=vss B=vss)                     W=2µm L=2µm   继承宽度
    ├─ Mcas         n33              (D=data_out G=vcas S=node_m B=vss)                    W=2.5µm L=2µm 单位化
    └─ Mout         n33              (D=node_m G=vbias_ch S=vss B=vss)                     W=2.5µm L=2µm 单位化
```

主电流方向：**`data_out` → `Mcas`(D→S) → `node_m` → `Mout`(D→S) → `vss`**；
`Mout` 的栅极是本支路 `vbias_ch`，`vbias_ch` 由 `Mpass_local` 从共享参考 `iref_in` 传送而来，
`Mpass_local` 的栅极是本支路 `en<j>`；关断期间 `Mbleed_local`（栅极 `enb<j>`）把 `vbias_ch` 放到 `vss`。
参考路径：`Iref_in`(bench 15 µA) → `Mref` 二极管连接 → 节点 `iref_in` → 八个 `Mpass_local` 漏端。

`vbias_ch` 与 `node_m` 只存在于每个 `Xu<i>` 作用域内（顶层不出现这两个名字，
检查器 `LOCAL_NODES_NOT_SHARED` 实测跨支路重叠 0），因此"八条支路"确实是八条独立的局部偏置链，
不是一条偏置被八处短接。`Mpass_local` 的第四端（DNW 体）**接自己的源极 `vbias_ch`，绝不接 `vss`**，
继承已接受核的做法；这条由 `DNW_PASS_BODY_LOCAL` 逐支路核。

### 3.3 几何与镜像比（估算，不含电学结论）

| 器件 | W | L | m | 依据 |
|---|---|---|---|---|
| `Mref` | 20 µm | 2 µm | 未设（=1） | 继承 `data_bias_ref`，不改 |
| 单位 `Mout` | 2.5 µm | 2 µm | 未设 | 任务书起点：`20/8 = 2.5`，理想镜像 `1:8` |
| 单位 `Mcas` | 2.5 µm | 2 µm | 未设 | 与单位电流同步考虑（任务书允许） |
| `Mpass_local` | 5 µm | 2 µm | 未设 | **不随电流除以 8**：它是传电压的开关，保留已用几何 |
| `Mbleed_local` | 2 µm | 2 µm | 未设 | **不随电流除以 8**：缩小会拖慢 `vbias_ch` 放电，属待测项 |
| 译码/使能管 | n18 2 µm / p18 4 µm | 0.2 µm | 1 | 继承 `dd1_inv18`/`sc1_scan_gate` 的 1.8 V 数字尺寸 |

计数口径（全部由 `dd1_d7c_a_offline_check.py` 从网表解析得到，不是手填；机读版在
`tests/dd1_d7c_a/device_count_claims.csv`，检查器 `CLAIM_TABLE_MATCHES_PARSE` 要求两者与解析三方一致）：
子电路实例 58；`dd1_d7c_a_pam_1ch` **展开 145 MOS**；`dd1_d7c_a_pam_dec` 112 MOS；
`dd1_d7c_a_sink_unit` 4 MOS 一条、八条支路合计 32 只器件；共享参考 `data_bias_ref` 1 MOS（在顶层计一次，
不在支路里重复计）；
`m` 在四条模拟管上**未书写**，按数值归一即为 `m=1`——它是 Spectre 的 multiplicity（同一器件描述重复几次），
**不等于**版图上的分指（finger），本任务没有 finger 参数也没有测过它；八条单位 `Mout` 的有效宽度合计
8 × 2.5 µm × 1 = 20 µm，与一只已接受 `Mout` 的 20 µm 等宽。"八条 2.5 µm 分立管"与"一只 20 µm 管"在匹配、
寄生与面积上并不等价（后者还要看它的分指与接触孔布置，本轮无参数约定可言），哪一种更好是待审议项，
本轮不选后一种，也不声称两种等效。

镜像比 `Mref(W/L) / Mout(W/L) = 8` 一律标 `ESTIMATED_MIRROR_RATIO_ONLY`：短沟道效应、输出电阻、
`Mpass_local` 上的局部偏置压降、参考负载与八管失配都未测，`GEOMETRY_NOT_VERIFIED`。

## 4 译码与使能的责任边界

温度计式（thermometer）选择，j = 1…7：`select<j> = (pam_sel >= j)`，`select<0> = 1`；
每支路真正使能 `en<j> = data_en AND select<j>`，`enb<j> = NOT en<j>`（本支路自己的反相节点）。
实现方程（`ENGINEERING_DERIVATION`，由 A 表导出，逐条在网表里可实现）：

```text
select1 = pam2 | (pam1 | pam0)          select5 = pam2 & (pam1 | pam0)
select2 = pam2 |  pam1                  select6 = pam2 &  pam1
select3 = pam2 | (pam1 & pam0)          select7 = pam2 & (pam1 & pam0)
select4 = pam2                          select0 = 1（接 vdd18 轨）
```

两处容易写错，各有自己的反例，且都由 16 行手抄黄金表（`tests/dd1_d7c_a/pam_mask_golden.csv`，
不是被测网表生成）抓住：

- **E02** 把 `Xsel3` 的第二输入由 `gand10 = pam1&pam0` 换成 `gor10`，于是 `select3` 的阈值低了一档，
  码 010 会点亮 4 条而不是 3 条。
- **E11** 把 `Xsel5` 的第二输入由 `gor10 = pam1|pam0` 换成 `select1 = pam2|(pam1|pam0)`；因为 `select1`
  已经含 `pam2`，`pam2 & select1 == pam2`，于是码 100 会点亮 6 条而不是 5 条。

门级实现只用静态 CMOS：`dd1_d7c_a_nand2`（串联 NMOS + 并联 PMOS）、`dd1_d7c_a_nor2`
（并联 NMOS + 串联 PMOS，与已接受 `sc1_scan_gate` 同形）、`dd1_d7c_a_and2/or2` = 上述单元 + 已接受
`dd1_inv18`。检查器不认名字：它把每只管的上拉/下拉图解出来（
`GATE_LOGIC_DERIVED_FROM_TRANSISTORS`），再自顶向下解整个译码器（`THERMO_GOLDEN_16`）。
**为什么不自建一整套库**：只做 2 输入门 + 反相器，共享 `pam1|pam0`、`pam1&pam0` 两项，
面积与扇出可控，不为一个 3 位译码搭通用逻辑。

时序与协议责任：PAM 请求只允许在不发光期间更新，发光窗口内保持不变——这条由已接受 DATA-7A 的
`pam_sel` 窗口内冻结契约承担（`dd1_d7a_contract.md` §2），本最小单元**不含**寄存、完整灰阶计数、
授权撤销 FSM 或 TCON，也不新增 BLANK/FAULT 恢复逻辑；bench 可以在关窗期间改 `DATA_EN` 与码值测试关断，
这不等于本单元会自行判断 LATCH/START 权限。

未知 X/Z、越界、空请求在**离线入口**拒收（`REQUEST_REFUSAL_TABLE`，16 种形状）。
这是软件边界：真实 MOS 支路看不见 X/Z，把拒收写成"模拟测试 PASS"是本轮禁止的说法。

## 5 Hybrid 6+3 的编码冗余（写明，不强行解决）

`6 位时间码 + 3 位 PAM 请求码 = 512 组数字编码组合`，但**不是** 512 个不同电荷，也不是 9 位光学有效位：

| 关系 | 说明 |
|---|---|
| 电荷等价 | 时间区间 32 × 1 单位电流与 16 × 2 单位电流的理想电荷相同（`Q = I × t`，同一参考下）；A 表内 码 011(4 单位) × 时间码 16 与 码 000(1 单位) × 时间码 64 也同电荷 |
| 黑 | 时间码 0 配任何幅度码都是黑；A 的幅度码 000 不是黑（它是 1 单位） |
| 上限 | 时间区间只有 64（Hybrid 满窗 64 区间），幅度只有 8 档，因此可分辨的 `I×t` 组合远少于 512，且高度重复 |
| 本轮不做 | LUT、光学映射、DEM/Mura 排布、实际 LED I–V 与阵列 RC —— 全部留待另做，不在本轮"强行解决" |

## 6 离线验证结果

<!-- BEGIN 7C OFFLINE -->
| 检查 | 结果 | 依据（截断到 180 字） |
|---|---|---|
| `NO_DUPLICATE_INSTANCES` | PASS | 65 (cell,identifier) pairs across M devices and X instances in 10 definitions |
| `TOP_HAS_ONE_OUTPUT_PORT` | PASS | output ports of dd1_d7c_a_pam_1ch: ['data_out'] (this is not eight channels) |
| `ALL_BRANCHES_ON_COMMON_OUTPUT` | PASS | 8 unit branches instantiated, DATA_OUT of every one on net data_out |
| `UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE` | PASS | all 8 branches bind EN/EN_B to their own enable pair, VBIAS_SHARED to the shared reference node, VCAS to vcas |
| `LOCAL_NODES_NOT_SHARED` | PASS | vbias_ch/node_m exist only inside instance scopes (branch 0 holds 2 local net(s)), no local name at top level, cross-branch overlap 0 |
| `REFERENCE_NODE_IDENTITY` | PASS | Xref expands to one diode-connected Mref whose D=G node is the net every unit pass device drains from (iref_in), with S=B=vss |
| `NETLIST_SUBSET_PARSED` | PASS | 7 files parsed, 10 subckt definitions, 145 expanded devices at dd1_d7c_a_pam_1ch, unsupported statements 0; candidate digests dd1_d7c_a_ga=d2def4e6,dd1_d7c_a_pa=9f6c8d78,dd1_d7c_a_ |
| `SUBCKT_MASTERS_DEFINED` | PASS | 58 subckt instances all resolve; models n18,n33,n33_dnw_4t_ckt,p18 against whitelist n18,p18,n33,n33_dnw_4t_ckt |
| `INSTANCE_PORT_COUNTS` | PASS | 58 instance bindings, each with exactly its master port count and order |
| `GOLDEN_TABLE_SCHEMA` | PASS | golden table has 16 rows over the 16 unique (enable,code) keys, masks of 8 characters of 0/1, en0..en7 consistent with the mask and branches_on equal to the popcount |
| `THERMO_GOLDEN_16` | PASS | 16 hand-written golden rows compared against the decoder transistors themselves, never generated by this evaluator |
| `TOP_INTEGRATED_THERMO_16` | PASS | 16 top-level enable/code combinations driven from the top pins, through the actual Xdec port binding, and read back at each branch EN/EN_B terminal (decoder port map {'pam0': 'pam_ |
| `GATE_LOGIC_DERIVED_FROM_TRANSISTORS` | PASS | pull-up/pull-down graphs give dd1_d7c_a_and2=0001; dd1_d7c_a_nand2=1110; dd1_d7c_a_nor2=1000; dd1_d7c_a_or2=0111; dd1_inv18=10 against hand-written boolean algebra |
| `EN_ENB_PAIR_PER_BRANCH` | PASS | every branch enb is one dd1_inv18 driven by that branch own en, and 16x8 pairs evaluate as exact complements |
| `DNW_PASS_BODY_LOCAL` | PASS | all 8 Mpass_local: drain on the shared reference node, gate on this branch en, source AND DNW body on this branch vbias_ch, never vss |
| `BLEED_GATED_BY_BRANCH_COMPLEMENT` | PASS | all 8 Mbleed_local discharge vbias_ch to vss and are gated by this branch enb |
| `MAIN_PATH_DATA_OUT_CAS_MOUT_VSS` | PASS | main path DATA_OUT -> Mcas -> node_m -> Mout -> vss per branch, gate of Mout is the local bias, gate of Mcas is the branch VCAS terminal |
| `DEVICE_COUNTS_DERIVED` | PASS | expanded MOS per cell data_bias_ref=1 data_sink_1ch=4 dd1_d7c_a_and2=6 dd1_d7c_a_nand2=4 dd1_d7c_a_nor2=4 dd1_d7c_a_or2=6 dd1_d7c_a_pam_1ch=145 dd1_d7c_a_pam_dec=112 dd1_d7c_a_sink |
| `DEVICE_COUNT_SEPARATION` | PASS | netlist statements 19, expanded devices at the top 145, hierarchy subckt instances 58, multiplicity sum 145 (m is unset on every device, so it contributes one each), finger paramet |
| `MIRROR_RATIO_ESTIMATED_ONLY` | PASS | reference Mref W=2e-5 L=2e-6 over unit Mout W=2.5e-6 L=2e-6 gives 8, tagged ESTIMATED_MIRROR_RATIO_ONLY: no short-channel, output-resistance, body-effect or matching behaviour is c |
| `UNIT_CORE_ISOMORPHIC_TO_ACCEPTED` | PASS | device by device dd1_d7c_a_sink_unit matches data_sink_1ch in model, L, multiplicity m and D/G/S/B role; only Mcas and Mout widths scale by 1/8, pass and bleed keep the accepted wi |
| `CLAIM_TABLE_MATCHES_PARSE` | PASS | 17 object-bound claims (data_bias_ref,data_sink_1ch,dd1_d7c_a_and2,dd1_d7c_a_nand2,dd1_d7c_a_nor2,dd1_d7c_a_or2,dd1_d7c_a_pam_1ch,dd1_d7c_a_pam_dec,dd1_d7c_a_sink_unit,dd1_inv18) e |
| `REPORT_CLAIMS_BOUND_TO_OBJECT` | PASS | every N MOS / N 管 / N transistors claim names the cell it counts and equals that cell-parsed total |
| `REPORT_CLAIM_COUNTS_MATCH` | PASS | secondary membership test: no claim equals a total parsed from some cell |
| `REQUEST_TABLE_SCHEMA` | PASS | 16 request rows with unique ids and codes from the closed set REQUEST_UNPARSED,REQUEST_OUT_OF_RANGE,REQUEST_NOT_INT,REQUEST_NOT_FINITE,ACCEPTED |
| `REQUEST_REFUSAL_TABLE` | PASS | 16 request shapes tried, including X/Z, empty, non-numeric, out of range, non-integer, non-finite and bool; this is a software boundary and no MOS branch can see X/Z |
| `NATIVE_ENTRY_REFUSED` | PASS | 4 environment combinations, entry refused in each before writing, directory digest unchanged and sentinel present |
| `NATIVE_PLAN_SHAPE` | PASS | 15 planned cases [('dc_sweep', 8), ('refined_step', 3), ('transient', 4)], all result NOT_RUN, DC rows hold DATA_EN=1.8 V with a named code, TR-LONG carries eight segments in one d |
| `DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS` | PASS | 39 active (non-comment) lines in the deck draft, analysis statements recognised by the keyword position with or without dev=: 0. This states only that the draft carries no analysis |
| `DRAFT_DECK_SYNTAX_INVENTORY` | PASS | every active deck line classifies into simulator/include/parameters/save/source/probe/instance/analysis; unrecognised active statements would be refused by name |

合计 30 项，失败：none。渲染来源 `offline_checks.json`（本目录）。
<!-- END 7C OFFLINE -->

<!-- BEGIN 7C GUARDS -->
| 反例 | 判决 | 注入文件 | 声明的新增失败集合 | 实测新增失败 | 字节改动证据 |
|---|---|---|---|---|---|
| `E01_pam_bit_order_swapped` | HIT | spectre/dd1_d7c_a_pam_dec.scs | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | 1 行改动，改前 9f6c8d78… |
| `E02_thermometer_threshold_off_one` | HIT | spectre/dd1_d7c_a_pam_dec.scs | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | 1 行改动，改前 9f6c8d78… |
| `E03_branch_ignores_global_data_en` | HIT | spectre/dd1_d7c_a_pam_dec.scs | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | 1 行改动，改前 9f6c8d78… |
| `E04_branch_left_the_common_output` | HIT | spectre/dd1_d7c_a_pam_top.scs | ALL_BRANCHES_ON_COMMON_OUTPUT | ALL_BRANCHES_ON_COMMON_OUTPUT | 1 行改动，改前 f46a2be5… |
| `E05_shared_reference_ratio_wrong` | HIT | spectre/dd1_d6_bias_core.scs | MIRROR_RATIO_ESTIMATED_ONLY | MIRROR_RATIO_ESTIMATED_ONLY | 1 行改动，改前 4115e2d1… |
| `E06_dnw_pass_body_tied_to_vss` | HIT | spectre/dd1_d7c_a_sink_unit.scs | DNW_PASS_BODY_LOCAL,UNIT_CORE_ISOMORPHIC_TO_ACCEPTED | DNW_PASS_BODY_LOCAL,UNIT_CORE_ISOMORPHIC_TO_ACCEPTED | 1 行改动，改前 60e06aa3… |
| `E07_enb_tied_to_a_constant` | HIT | spectre/dd1_d7c_a_pam_dec.scs | EN_ENB_PAIR_PER_BRANCH | EN_ENB_PAIR_PER_BRANCH | 1 行改动，改前 9f6c8d78… |
| `E08_subckt_port_order_corrupted` | HIT | spectre/dd1_d7c_a_sink_unit.scs | DNW_PASS_BODY_LOCAL,REFERENCE_NODE_IDENTITY,TOP_INTEGRATED_THERMO_16,UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE | DNW_PASS_BODY_LOCAL,REFERENCE_NODE_IDENTITY,TOP_INTEGRATED_THERMO_16,UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE | 1 行改动，改前 60e06aa3… |
| `E09_stale_device_count_in_report` | HIT | reports/dd1_d7c_a_pam_candidate.md | REPORT_CLAIMS_BOUND_TO_OBJECT | REPORT_CLAIMS_BOUND_TO_OBJECT | 摘要见 `counterexamples.json`（注入对象是本报告，包内不写自身摘要） |
| `E10_unsupported_syntax_refused` | HIT | spectre/dd1_d7c_a_pam_top.scs | ALL_BRANCHES_ON_COMMON_OUTPUT,BLEED_GATED_BY_BRANCH_COMPLEMENT,CLAIM_TABLE_MATCHES_PARSE,DEVICE_COUNTS_DERIVED,DEVICE_COUNT_SEPARATION,DNW_PASS_BODY_LOCAL,EN_ENB_PAIR_PER_BRANCH,GATE_LOGIC_DERIVED_FROM_TRANSISTORS,GOLDEN_TABLE_SCHEMA,INSTANCE_PORT_COUNTS,LOCAL_NODES_NOT_SHARED,MAIN_PATH_DATA_OUT_CAS_MOUT_VSS,MIRROR_RATIO_ESTIMATED_ONLY,NETLIST_SUBSET_PARSED,NO_DUPLICATE_INSTANCES,REFERENCE_NODE_IDENTITY,REPORT_CLAIMS_BOUND_TO_OBJECT,REPORT_CLAIM_COUNTS_MATCH,SUBCKT_MASTERS_DEFINED,THERMO_GOLDEN_16,TOP_HAS_ONE_OUTPUT_PORT,TOP_INTEGRATED_THERMO_16,UNIT_CORE_ISOMORPHIC_TO_ACCEPTED,UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE | ALL_BRANCHES_ON_COMMON_OUTPUT,BLEED_GATED_BY_BRANCH_COMPLEMENT,CLAIM_TABLE_MATCHES_PARSE,DEVICE_COUNTS_DERIVED,DEVICE_COUNT_SEPARATION,DNW_PASS_BODY_LOCAL,EN_ENB_PAIR_PER_BRANCH,GATE_LOGIC_DERIVED_FROM_TRANSISTORS,GOLDEN_TABLE_SCHEMA,INSTANCE_PORT_COUNTS,LOCAL_NODES_NOT_SHARED,MAIN_PATH_DATA_OUT_CAS_MOUT_VSS,MIRROR_RATIO_ESTIMATED_ONLY,NETLIST_SUBSET_PARSED,NO_DUPLICATE_INSTANCES,REFERENCE_NODE_IDENTITY,REPORT_CLAIMS_BOUND_TO_OBJECT,REPORT_CLAIM_COUNTS_MATCH,SUBCKT_MASTERS_DEFINED,THERMO_GOLDEN_16,TOP_HAS_ONE_OUTPUT_PORT,TOP_INTEGRATED_THERMO_16,UNIT_CORE_ISOMORPHIC_TO_ACCEPTED,UNIT_PORT_BINDING_MATCHES_DESIGN_TABLE | 3 行改动，改前 f46a2be5… |
| `E11_select5_reuses_select1` | HIT | spectre/dd1_d7c_a_pam_dec.scs | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | THERMO_GOLDEN_16,TOP_INTEGRATED_THERMO_16 | 1 行改动，改前 9f6c8d78… |
| `E12_top_pam_bits_swapped` | HIT | spectre/dd1_d7c_a_pam_top.scs | TOP_INTEGRATED_THERMO_16 | TOP_INTEGRATED_THERMO_16 | 1 行改动，改前 f46a2be5… |
| `E13_top_enable_tied_high` | HIT | spectre/dd1_d7c_a_pam_top.scs | TOP_INTEGRATED_THERMO_16 | TOP_INTEGRATED_THERMO_16 | 1 行改动，改前 f46a2be5… |
| `E14_reference_bound_to_vcas` | HIT | spectre/dd1_d7c_a_pam_top.scs | DNW_PASS_BODY_LOCAL,REFERENCE_NODE_IDENTITY | DNW_PASS_BODY_LOCAL,REFERENCE_NODE_IDENTITY | 1 行改动，改前 f46a2be5… |
| `E15_duplicate_mos_instance` | HIT | spectre/dd1_d7c_a_gates.scs | NO_DUPLICATE_INSTANCES | NO_DUPLICATE_INSTANCES | 1 行改动，改前 d2def4e6… |
| `E16_cascode_multiplicity_changed` | HIT | spectre/dd1_d7c_a_sink_unit.scs | DEVICE_COUNT_SEPARATION,UNIT_CORE_ISOMORPHIC_TO_ACCEPTED | DEVICE_COUNT_SEPARATION,UNIT_CORE_ISOMORPHIC_TO_ACCEPTED | 1 行改动，改前 60e06aa3… |
| `E17_golden_header_only` | HIT | tests/dd1_d7c_a/pam_mask_golden.csv | GOLDEN_TABLE_SCHEMA,THERMO_GOLDEN_16 | GOLDEN_TABLE_SCHEMA,THERMO_GOLDEN_16 | 1 行改动，改前 6ff91d98… |
| `E18_request_table_emptied` | HIT | tests/dd1_d7c_a/pam_request_refusal.csv | REQUEST_REFUSAL_TABLE,REQUEST_TABLE_SCHEMA | REQUEST_REFUSAL_TABLE,REQUEST_TABLE_SCHEMA | 1 行改动，改前 efbc0522… |
| `E19_claim_table_stale` | HIT | tests/dd1_d7c_a/device_count_claims.csv | CLAIM_TABLE_MATCHES_PARSE | CLAIM_TABLE_MATCHES_PARSE | 1 行改动，改前 aad52167… |
| `E20_plan_refines_more_than_time` | HIT | tests/dd1_d7c_a/native_case_plan.csv | NATIVE_PLAN_SHAPE | NATIVE_PLAN_SHAPE | 1 行改动，改前 0a55795f… |
| `E21_active_tran_without_dev` | HIT | spectre/dd1_d7c_a_tb_draft.scs | DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS | DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS | 3 行改动，改前 a7f4acec… |
| `E22_active_dc_with_dev` | HIT | spectre/dd1_d7c_a_tb_draft.scs | DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS | DRAFT_DECK_HAS_NO_ACTIVE_ANALYSIS | 3 行改动，改前 a7f4acec… |
| `E23_unknown_active_deck_statement` | HIT | spectre/dd1_d7c_a_tb_draft.scs | DRAFT_DECK_SYNTAX_INVENTORY | DRAFT_DECK_SYNTAX_INVENTORY | 3 行改动，改前 a7f4acec… |
| `E24_golden_key_duplicated` | HIT | tests/dd1_d7c_a/pam_mask_golden.csv | GOLDEN_TABLE_SCHEMA | GOLDEN_TABLE_SCHEMA | 2 行改动，改前 6ff91d98… |
| `C1_round_trip_ok` | HIT | - | CSV_SCHEMA | - | - |
| `C2_unquoted_comma_row` | HIT | - | CSV_SCHEMA | - | - |
| `C3_wrong_column_count` | HIT | - | CSV_SCHEMA | - | - |
| `C4_duplicate_key` | HIT | - | CSV_SCHEMA | - | - |
| `C5_header_only` | HIT | - | CSV_SCHEMA | - | - |

基线（未注入）失败集合：none；规则：`found == sorted(expected)` 且 expected 非空。E09/E17/E19 一类注入对象就是承载本表的文件或表本身，其改前改后摘要只出现在 `counterexamples.json`：把摘要写进被注入的文件会让每次渲染都不同。
<!-- END 7C GUARDS -->

结果解读口径：22 项检查全部只谈文本、连接与逻辑；10 项反例每项要求"新增失败集合 = 事先声明的集合"，
且非空（`[] == []` 不算检出）；每条命令的 rc 单独记在验证目录的 `commands.csv`。
`REPORT_CLAIM_COUNTS_MATCH` 把本报告与两份文档里所有 `N MOS / N 管 / N transistors` 断言
与从网表解析出的总数比对——这是 `scripts/netlist_stats.py` 的口径推广：该冻结工具把
**一个** cell 的总数与全部报告比对，基线上它已经报出一条既有失配（引用旧报告里"29 管"那句被指出的说法）。  <!-- check:skip 引用被指出的旧断言，不是本轮声明 -->
本轮不改那件工具、也不拿它的 PASS 当证据；推广版由上面这台新工具承担，并由反例 E09 证明它会失败。

## 7 继承的待办与出处区别（不在本轮修）

任务书 §7 要求列出而不是顺手修。DATA-7B-R3 复审的三条非阻断注记（用户决定留到下一轮维护）：

1. `ARCHIVE_README_COUNT_AND_SOURCE_WORDING`：R3 审核包生成的 README 写"53 个文件、README 不在清单内"，
   实际清单 54 条且含该 README（53 是仓库成员数）。
2. `AUXILIARY_ASSERTIONS_CAN_BE_STRICTER`：`scripts/dd1_d7b_r3_guards.py:253` 的 `new == named`
   在两者皆空时空洞为真；`scripts/dd1_d7b_r3_verify.py:245` 的仪器门只按 `rc==1` 判定，未读 JSON 字段。
   **本轮新工具直接采用正确做法**：`scripts/dd1_d7c_a_guards.py` 要求
   `found == sorted(expected)` 且 `expected` 非空（否则判 FAIL），并且所有外部自测结果按 JSON 字段读。
3. `CURRENT_RANGE_IS_10_COMMITS`：提交数要按回读时刻统计。

回读出处区别：交接 JSON 里 `remote_readback` 记录的是**查询的 5 个 ref**（main、D7B、R1、R2、R3）与
22 行全量 ref 的两个不同口径——5 条是"逐 ref 用 `gh api` 单独对象读"，22 行是
"`git ls-remote` 返回的 ref 总数"。两者不是同一件事，引用时必须写明查的是哪一个集合；
本轮 `commands.csv` 的每行都带命令全文，避免再出现"5/22 混写"。

## 8 未做与边界

未做：任何原生仿真（Spectre/Xyce/ngspice/Icarus/Virtuoso/OA 全部 0 次）、`spectre -h`、动态 rail
preflight、旧波形重跑、VM/SSH、凭据读取、密码/PDK/license/网络改动、合并、推 main、可见性变更、
GC、历史重写、force、跳 hooks、规则放宽。PAM/LUT/阵列/版图/TCON 未搭。
既有事实不变：DATA-7B 历史 59 次实际启动对固定授权 56 次、超支 3 次仍
`VIOLATED_NOT_RETROACTIVELY_AUTHORISED`，其包内 `BUDGET_RESPECTED` 继续 FAIL；四个已删 R1 中间目录
原字节不可得；凭据回显事件未解除。本轮不读凭据，也不以扫描 PASS 宣称该事件解除。

```text
TASK_ID=DATA-7C-A
BASE_SHA=272d6de6d2f2fc8a82d5038d73d6b3e4c656f683
ACCEPTED_DATA7B_CONTENT_SHA=f9fd09b184a69a27cdb409205dfd4f4151408a23
SCOPE=ONE_OUTPUT_EIGHT_LEVEL_PAM_CANDIDATE_MOS_AND_OFFLINE_VERIFICATION
PAM_LEVELS_STATUS=POC_CANDIDATE_NOT_FORMAL_SPEC
COMPLETION_LEVEL=CANDIDATE_MOS_NETLIST_WITH_OFFLINE_CHECKS
NATIVE_NETLIST_SYNTAX=NOT_VERIFIED
PAM_8LEVEL_CURRENT_MEASURED=NOT_RUN
NEW_SPECTRE_LAUNCHES=0
NEW_RTL_SIMULATIONS=0
NEW_OA_WRITES=0
EXISTING_TRACKED_PATHS_MODIFIED=0
MERGE_PERFORMED=NO
NEXT_NATIVE_STAGE_AUTHORISED=NO
SOA_SIGNOFF=NO
STOP_REASON=AWAITING_INDEPENDENT_REVIEW_OF_CANDIDATE_AND_TEST_PLAN
```
