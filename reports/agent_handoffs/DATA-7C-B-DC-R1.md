# DATA-7C-B-DC-R1 交接（离线修补，停在独立复审闸）

- 任务书：`reports/tasks/DATA-7C-B-DC-R1.md`（附件逐字节，含来源与 sha256 声明）
- 复审包：`MicroLED_DATA7C_B_DC_Independent_Review_REWORK_20261026.zip` 47,977 B
  `e603abeef577d5a60415c50ac631fcfec286e9928edc1fe8f8037bdb42c398fe`，34 条 MANIFEST 行逐条对字节通过
- 分支 `poc/data-pam-d7c-b-dc-r1`，BASE `337563fc22699e480bf7fc82890750c126a50654`（上一轮 DC 的回执 tip）
- 限定接受的离线内容仍是 `e51c5320a28bd5043e21d08a0be97e9d5612cd16`：冻结 deck 与冻结面的来源
- 记录目录：`results/evidence/dd1_d7c_b_dc_r1_r20261026_071848_e6c5fe`
- 结构化字段在 `DATA-7C-B-DC-R1.json`，本文只做人读摘要；两边不一致以 JSON 与记录表为准。

## 本轮做了什么

四组缺口，全部离线：

1. **F1 有符号判据**：`band_of()` 从 `abs(abs(i)-abs(target))` 改回 `abs(i-target) <= 5%*abs(target)`，
   并在取带前拒非有限点。复审仪器"把八码 0.60 V 读数翻负"的反例现在把区间收窄到 0.65、点名 0.60 为相邻失败点，
   而 1.20 V 主点判据不受牵连。
2. **F2 必需观察**：`extract()` 在造任何行之前要求 axis、探针电流、data_out、vss、vdd18、vcas、data_en、
   pam0/1/2、iref_in 全部真实存在并核单位/列长/有限性；删掉合同值与 case 名兜底；逐点与本例冻结 deck 的静态源
   比对（高 1.8 V／低 0 V 两个窗口，中间电平拒收）；实测码＝deck 驱动码＝case 名；输出必须跟着被扫节点。
   `iref_source_A`、`corner`、`temp_C` 改为从 deck 读并标注为 deck 条件。
3. **F3 完整矩阵前置**：新增 `validate_dc_matrix()` 并接进 `judge()`、公开 `--judge`、`matrix check`；
   八主点算术抽成不返回 verdict 的 `main_point_arithmetic()`。8 行表、少一行、多一点、重复替换缺点、
   非有限、单位空、缺列、未知码全部在门前被拒。另发 `extraction_identity_resolution.csv`
   把 `(case, role, deck, raw)` 唯一映射到账本里 16 个真实 run_id/launch_id，旧行的 `manual/D000` 不改写。
4. **F4 发布身份**：身份一律取将要提交的 Git blob（并新增 `identity_source` 列与 `--verify-committed` 复核模式），
   不再取工作副本；两张 SVG 的旧身份行保留在旧记录里，`stale_fields_of_the_earlier_record.json` 机械证明
   "记录值＝blob 的 CRLF 形态"（45,208/19,316 对 44,364/18,923），本轮直接引用 BASE 的 LF 字节、不重画。
   dc_judgement 门的 A→µA 系数由 `1e9` 改为 `1e6`（正例 `9.1175e-13 A → 9.1175e-07 µA`），judgement 的 A 值未动。
   `observe()` 无原生答案时改为逐例 `NOT_OBSERVED`、整体 `NOT_RUN`、rc=3，不再写观测 PASS；
   本轮的观察是从本机保存的 8 份 `.raw` 读出来的，来源与摘要见 `observation_provenance.json`。

如实更正一条旧声明：`git diff --check e51c532..337563f` 实际 rc=2、378 处行尾空白，上一轮写成 0 是错的；
本轮不覆写那些已归档字节，只在 `git_checks.csv` 记实际 rc，并保证本轮自身区间 rc=0。

## 数字（未重跑，数值与上一轮一致）

1.20 V 处八码电流 1.922839 / 3.845677 / 5.768515 / 7.691353 / 9.614191 / 11.537029 / 13.459867 /
15.382706 µA；满量程带 14.25–15.75 µA 通过；`Iunit_ref = I111/8 = 1.92283819625 µA`；严格单调；
最大残差 9.1175e-13 A ＝ 9.1175e-07 µA ＝ 4.741688622672253e-07 个 `Iunit_ref`（限 0.25）；
八码 ±5% 已测区间 0.60–0.65…1.50 V 全 19 点，不外推。

## 成本与边界

`NEW_SPECTRE_LAUNCHES=0`、`NEW_RTL_SIMULATIONS=0`、`NEW_OA_WRITES=0`、`NEW_SSH_OR_VM_ACTIONS=0`、
`guest_connections=0`；未读凭据、PDK、模型卡或 license；上一轮余下的 4 次额度未动用也不外借；
16 行账本与 152+152 条原生表逐字节复用（`reuse_declaration.json` 记 BASE blob 摘要）。
未做瞬态、PWM/PAM 联合电荷、灰阶 LUT、控制器、阵列、版图、SOA；`OPTICAL_EFFECTIVE_BITS=NOT_VERIFIED`。
本轮能独立证明的是提交表的数值、判据、身份与账本关系，以及从本机保存答案重读的观察；
云端不能从原始 PSF 重提取，`.raw`/`.log` 仍不入仓库不入包。

`STOP_REASON=AWAITING_INDEPENDENT_REVIEW`，`ACCEPTANCE_REGISTERED=NO`，`MERGE_PERFORMED=NO`，
`NEXT_NATIVE_STAGE_AUTHORISED=NO`。记录提交之后还有一笔本轮提交，放 `--verify-committed` 的复核输出与
对 BASE 提交跑一次的复审仪器闭合结果；包摘要只写在包外的回执提交里。
