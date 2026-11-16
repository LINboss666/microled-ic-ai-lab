# T4 RUN02 报告 —— 双片 512 路 Scan Driver（第 2 次 / 共 2 次，T4 预算用尽）

日期 2026-11-16 ｜ 终态 `WAITING_FOR_T4_RUN02_INDEPENDENT_REVIEW`
裁定：**`T4_RUN02 = PASS 42/42`**；`T4_SIM_BUDGET = 2_USED_OF_2`（T4 正式仿真预算**用尽**，无第三次）。
RUN01 的 `FAIL 41/42` 原样保留在 `RUN01` 审核包与 `t4_run01/` 运行目录中，**未被改写为 PASS**。

---

## 1. 与 RUN01 的差异（严格限定在 TB）

| 项 | RUN01 | RUN02 | 说明 |
|---|---|---|---|
| `rtl/scan_driver.v` | `6ee3ad38…2229a4` | `6ee3ad38…2229a4` | **未改** |
| `rtl/scan_exp.v` | `8dd70a37…995a47d` | `8dd70a37…995a47d` | **未改** |
| `rtl/scan_pin_mon.v` | `7c280e13…8304d10` | `7c280e13…8304d10` | **未改** |
| `tb/run_tcon_t4.sh` | `cfe602dc…473667` | `cfe602dc…473667` | **未改**（FLOOR=42） |
| `tb/tcon_t4_tb.sv` | `9dbbb960…29d05` | `2811b3be…89c23a` | 仅下述三处 |

TB 的完整差异见 `evidence/diff_run01_tb_vs_run02_tb.txt`，内容只有：

1. `D42`：`n_cmp > 15000` → **`n_cmp >= 9500`**（复审指定值）。
2. 新增 `COURSE_T4_STROBES_AT_D19` 打印（D19 求值当刻的计划/实测计数）。
3. census 增加 **PRE_RESET** 快照（P7 复位之前），原末尾打印改标 **POST_RESET** 并注明"已被 P7 清除、不得引用"；同时打印 `setup_bad / hold_bad`。

断言名核对：42 → 42，**新增 0、删除 0、重命名 0**（脚本比对 `chk("...")` 名字集合）。
激励、相位、总时长未变：两次运行都在 `Time: 99,987 ns` 结束。

## 2. 正式运行结果（唯一一次，21:2x，vsim 6 s）

| 验收条件 | RUN02 原生值 |
|---|---|
| 断言 | `ASSERT_COUNT=42`，`PASS_COUNT=42`，`FAIL_COUNT=0`，名称无重复 |
| 结果标记 | `COURSE_RTL_RESULT=PASS` |
| T6 五条件 | `1/1/1/1/1`，`RUNNER_VERDICT=PASS`，`RUNNER_EXIT=0` |
| 编译 | vlog 0 errors / 0 warnings |
| 1024 列遍历 | `checked=1024`，`cov_chip0=512`，`cov_chip1=512` |
| 独立 oracle | `oracle_mismatch=0`（每次采样都比对） |
| 跨片独热 | `zero_or_multi_hot=0`，`onehot_samples=3,120` |
| 安全门控 | `blank_on=0`，`fault_on=0`，`diag_sel_bad=0` |
| D42 采样数 | `n_cmp=9,978` ≥ 9,500（阈值占理论上限 9,998 的 95%） |

## 3. 复位前 census（本轮新增，**取代 RUN01 末尾的哨兵值**）

```text
COURSE_T4_STROBES_AT_D19      expected=1035 observed=1035
COURSE_T4_STROBES_PRE_RESET   expected=1036 observed=1036 checked=1024
                              zero_or_multi_hot=0 cov_chip0=512 cov_chip1=512
COURSE_T4_TIMING_PRE_RESET    setup_min_ps=25000 hold_min_ps=40000
                              setup_bad=0 hold_bad=0
COURSE_T4_MONITOR             samples=9978 oracle_mismatch=0 onehot_samples=3120
                              diag_sel_bad=0 blank_on=0 fault_on=0
COURSE_T4_STROBES_POST_RESET  expected=1036 observed=0   ← P7 已清零，仅留审计
COURSE_T4_TIMING_POST_RESET   setup/hold=1000000000      ← 哨兵值，不得引用
```

## 4. RUN01 报告的一处口径错误，本轮已由实测澄清

- RUN01 报告写 `D19 1036==1036`；复审指出 **D19 在 D38 额外 STB 之前求值，应为 1035**。
- RUN02 实测：`COURSE_T4_STROBES_AT_D19 expected=1035 observed=1035` —— **复审的计数时点判断正确**，
  RUN01 报告那句是把 P7 边界值（1036）错贴到 D19 上，属报告口径错误，不影响 RUN01 的 D19 判据本身（当时比较的是同一时点的 1035==1035）。
- 同时确认：D38 之后、P7 之前为 `1036==1036`。两个时点均如实打印，未硬编码。

## 5. 预算与停止条件

- T4 授权 2 次正式 vsim：RUN01（FAIL）+ RUN02（PASS）= **2/2，预算用尽**，不存在第三次。
- `t4run02_precheck` 目录只有 `vlog` 编译（0 错 0 警）与静态脚本，**未调用 vsim**，不消耗预算。
- 未启动 T5 / Spectre / MC / OA / STA；未动 main；未开 PR；未自签 GO。

## 6. 仍然 OPEN（T4 PASS 不覆盖）

| 项 | 状态 |
|---|---|
| `T3_LUT_VALID_OUTPUT_GATE_OPEN`（`hw_en` 缺 `lut_valid`） | **P0 未关闭**，须 T3-H 限定授权补测；T4 分支未改动 T3 代码 |
| FAULT 恢复语义 | 本轮为 `DERIVED_GATE_NOT_LATCH`（故障释放后旧锁存列重新导通）；若系统要求故障锁存到合法帧重启，须在 TCON 系统安全合同/T5 收口 |
| 512 路高侧 MOS、8.68 Ω、非选列放电、FAULT_n 开漏上报 | 模拟/电气，未实现、未验证 |
| 综合 / STA / CDC / PVT / SOA / 光学标定 | 未做；setup/hold 25 ns / 40 ns 是数字波形时间戳，**不是 STA** |
| T5 五芯片新 RTL 联合验证 | 未启动，需另行授权 |
