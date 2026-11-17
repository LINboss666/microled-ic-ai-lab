# T3-H 预检与判据（**写于唯一一次正式仿真之前**，零仿真）

日期 2026-11-17｜授权：`T3_H_ONE_MODELSIM_AUTHORIZED_WITH_PRECHECK`
基线：T3 RUN05（52/52，`data_driver` SHA `896a3c54…1f5e`）

---

## 1. 变更清单与身份

| 文件 | 变更前 | 变更后 | 性质 |
|---|---|---|---|
| `rtl/data_driver.v.txt` | `896a3c541794c595e8b2a52d4927ac2e42e8849aeede3a55cc622d0ca0061f5e` | `4ea897deebe39b6437acb40821b035bd98526f78f8e7a5da03abda2a1911c8be` | **唯一允许的 RTL 修复** + 注释 |
| `tb/tcon_t3_tb.sv.txt` | `2609627ac590d6cce48867ce0eb63915f9a58cb357cf144b80c937f9df71c6a6` | `d57e959ca77d3e5d38519f2ae6a3bf6ed3a3c42232d25cf5310cdc020d1797e7` | 新增 P7 定向段 + 2 个监视器 + 17 条断言 |
| `rtl/data_model.v.txt` | `604915355a79dfe5e0d8cc5aa4e9d14913d33c1962069ed394de21e71ef5506a` | **同** | oracle 未改 |
| `tb/run_tcon_t3.sh` | `c1668f452297ae51b073fd088106c30791ee166b4ffe4573fd6ded5dcb07d9a3` | **同** | runner 未改（FLOOR 仍 51） |
| LUT | `e3e39b43f7e0f76e5f2865338c271402a1da5b1fd8b4e6193c0ed668f79cb253` | **同** | 码表未动 |

RTL 实际差异（除注释外）：`hw_en` 增加一个许可项

```verilog
- wire hw_en = disp_ok && !blank && fault_n;
+ wire lut_ok = (!cfg_hybrid) || lut_valid;
+ wire hw_en  = disp_ok && lut_ok && !blank && fault_n;
```

## 2. 缺口路径（静态，A.2）

1. `col_valid <= 1` 的条件只有 `armed && wcnt==NCH && !ovf`（LATCH 上升沿），**不看 `lut_valid`**。
2. 装载路径无条件 `lut_q = lut_{a,b}[din]`，`map_load[i] <= map_now`（`cfg_hybrid=1` 时为 `lut_q`）。
3. 输出 `ch_en[gi] = hw_en && (w_eff!=0) && (cnt_q<w_eff)`；修复前 `hw_en = col_valid && !blank && fault_n`。
4. 因此 **完整 384 字节 + `lut_valid=0` + `blank=0` + `fault_n=1`** 时，`hw_en=1`，`ch_en` 由未提交 bank 的映射值决定 → 可能导通，违反 `LUT_VALID=0 前不可显示`。
5. 禁止的是**实际 `ch_en[383:0]`**，不是把输出变成 X：因此 B1 用四态精确比较 `ch_en === 384'b0`，X 记为违规。

**为什么 X 一定会被抓到（负控，静态推导，不额外耗仿真）**：
复位后 `lut_bank=0` → 写入/读取的是 bank A，而 bank A 在 RUN05 的 P1 中从未被写过 → `lut_a[*] = X`
→ `map_load = X` → `w_eff = X` → 修复前 `hw_en=1` 时 `ch_en = 1 && X && X = X`（`X !== 0` 成立）
→ B1 的 `t3h_v1 > 0` → `D46` 失败。修复后 `hw_en=0` 使 `0 && X = 0`（Verilog 与门短路为 0，与 X 无关），`ch_en` 精确为 0。
**结论：B1 在修复前必失败、修复后必过；不依赖 X 偶然为 0。**

## 3. `lut_valid` 生效点与恢复语义（A.4）

- `ok_{a,b}` 在 COMMIT 的那一拍置位、同拍翻转 `lut_bank`，因此 `lut_valid` 在该 DCLK 沿之后立即为 1（组合读出）。
- 复位只清 `ok_a/ok_b`、`mask_*`、`lut_bank`，**不清 LUT 内容**；但"哪个 bank 是 active"会回到 A，而 A 可能是从未写过的 bank。
  → 因此 B2 的恢复必须**重新写满 256 项 + COMMIT + 重新装载合法列**，不能只撤 BLANK。

## 4. 优先级复查（A.3）

`hw_en` 仍是纯组合 AND，项序不影响功能：`reset`（经 `col_valid` 异步清零）、`blank`、`fault_n` 保持原有硬件优先；
新增项 `lut_ok` **不引入任何状态**（无新寄存器、无新时钟域），不改变 LATCH/DCLK/窗口时序。

## 5. `cfg_hybrid` 动态变更（A.5，登记约束，不测）

模式位在显示窗口内变更会立刻切换 `w_eff`/`ch_pam` 的解码来源。本轮**不做**动态切换测试，也不实现 Pure 8-bit PWM。
登记为模式配置时序约束：`cfg_hybrid` 只允许在 `blank=1` 且无装载时变更（与 COMMIT 的 `safe_cfg` 同域），待 T5/寄存器阶段收口。

## 6. 定向用例与判据（写于此，运行前）

| ID | 场景 | 判据 |
|---|---|---|
| D43 | 复位后 | `lut_valid === 0` |
| D44 | B1：完整 384 字节列、LUT 未提交 | `col_valid===1 && lut_valid===0` |
| D45 | B1：载荷非零（场景有效） | `raw_disp` 至少一项非 0 |
| D46 | B1：**核心** | 全窗口每个 DCLK 上升沿 `ch_en === 384'b0`（四态） |
| D47 | B1：非空洞 | 采样数 > 300 |
| D48 | B2：COMMIT 后 | `lut_valid === 1` |
| D49 | B2：重新装载 | `col_valid === 1` |
| D50 | B2：映射 | 384 项 `map_disp == lut_tab[raw_disp]` |
| D51 | B2：PAM | 384 项 `ch_pam == lut_tab[raw][8:6]` |
| D52 | B2：导通时间 | 384 路 `on_cnt == e_eff(i&255)`（64 tick 满窗） |
| D53 | B2：非"全关也 PASS" | `sum(on_cnt) > 0` |
| D54 | B2：满码 | `on_cnt[255] == 64` |
| D55 | B3：BLANK 自然上升沿 | 1 ns 后 `ch_en===0`，且边沿数 ≥1、违规 0 |
| D56 | B3：有效 LUT 下显示中 | `\|ch_en === 1` |
| D57 | B3：故障注入 | 1 ns 后 `ch_en===0` |
| D58 | B3：故障释放 | 1 ns 后恢复 `\|ch_en===1`（`DERIVED_GATE_NOT_LATCH` 默认） |
| D59 | B3：复位注入 | 1 ns 后 `ch_en===0` |

原有 52 条判据、名称、阈值**全部不动**；执行总数 **69**，`MIN_ASSERTS=69`。

## 7. 窗口普查不会被新场景破坏（关键）

D42 要求 `opened == closed + dropped`、`dropped<=1`、`min=max=384`。
T3-H 每个场景都在 **cyc 700（B1）/ 640（B3）** 收尾——此时该槽的字节流早已在 **cyc 624** 关闭，
而下一个窗口要到 **cyc 832** 才打开，所以新增窗口全部正常关闭，**不会多出第 2 个 dropped**。

## 8. 资源与停止条件

- 唯一一次正式 vsim（本阶段预算 1）；`MIN_ASSERTS=69`。
- 编译预检与静态脚本不计次数（已做：vlog 0/0）。
- 任何 FAIL：保留原生日志/VCD/SHA，停止，不再申请预算，不启动 T5。
