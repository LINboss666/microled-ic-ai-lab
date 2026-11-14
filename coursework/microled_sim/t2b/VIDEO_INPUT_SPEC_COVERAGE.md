# VIDEO_INPUT_SPEC_COVERAGE — V1.3 视频输入要求逐条覆盖与证据状态

**任务** `TCON-T2B-20261114` B 段 ｜ 基线 `84a1a71` ｜ **本轮 ModelSim 预算 3/3 已用尽，全部失败**
**状态口径**：`VERIFIED` = 有本轮原生 ModelSim PASS；`EXERCISED_FAIL` = 跑过但失败；`COMPILED_ONLY` = 只过 `vlog`（0 error 0 warning）；`NOT_RUN` = 没跑

> **先读这一句**：本轮**没有**任何一条 V1.3 输入要求达到 `VERIFIED`。所有实现都已写成、编译通过，但联合验证在 3 次预算内没有取得 PASS，T1 回归一次也没跑。下面每条都按实际状态标注，不写"应该没问题"。

---

## 1. 逐条覆盖

| # | V1.3 要求（出处） | 实现位置 | 静态检查 | 证据状态 |
|---|---|---|---|---|
| V1 | `COL_SYNC` 与 byte0 同一 PCLK 上升沿（§9 段0324、§12 段0411） | `tcon_video_rx.v.txt` `at0` 分支：cycle 0 采到 `sync_p` 才开列，byte0 同拍写入 | 逐拍推演见 `t2b/PIPELINE_FRAME_TAG_TIMELINE.md` §2 | `EXERCISED_FAIL`（run01–03 中该路径均被驱动，但核心判据因 TB 采样相位缺陷未真正比较，见 §3） |
| V2 | 每列恰好 768 个有效字节（§9、§12 段0406） | RX `idx` 计数 + 截止 830 检查 | — | `EXERCISED_FAIL`：767/769 用例分别置 `[0]`/`[1]`（P28/P14 打印为 PASS，但见 §3 说明） |
| V3 | `VSYNC` 与新帧首个 `COL_SYNC` 同沿（§9、§12 段0416） | RX `vs_p`/`next_col`；top `frame_start` 进入 ACTIVE | — | `EXERCISED_FAIL`：错位 VSYNC 置 `[4]`（P30） |
| V4 | 允许短暂停顿、整列在装载窗前完成（§9 段0324） | RX 只在 `de=1` 时计数，无位置约束 | — | `NOT_RUN`（本轮 TB 无停顿用例） |
| V5 | 1024 列/帧、102.4 kHz 平均列率（§4、§9） | 时基不变 | 算术核对见 `T2B_V13_FROZEN_INTERFACE.md` §8 | `EXERCISED_FAIL`：run03 PH5 `slots=1027 wraps=1`（帧长与回绕正常，但同轮 $dumpoff 前已判 FAIL） |
| V6 | 无 READY 握手（§9） | `safe` 只用模式级 `rx_ready` | — | `COMPILED_ONLY` |
| V7 | 两 Data、各 384 B/列（§12 D0/D1 行） | `tcon_data_tx` 384 B/口 | — | `EXERCISED_FAIL`：`win_edges=3528`（10 槽）与 3840 的差额未解释清，见 §4 遗留项 |
| V8 | 两 Scan、`COL_ID[0]` 选片、`[9:1]` 选 512 路（§12 段0486、§4 段0156） | `scan_model.v.txt` | — | `EXERCISED_FAIL`（P38 通道范围） |
| V9 | `SCAN_STB` 在 BLANK 内锁存列地址（§12 段0491、§14 段0709） | `tcon_top` `scan_stb` 门控 | — | `EXERCISED_FAIL`（P08/P37） |
| V10 | `LATCH` 仅 BLANK 内原子切换（§12 段0466） | `tcon_slot_seq` 828..831 | — | `EXERCISED_FAIL`（P11） |
| V11 | 四级标签 `rx=s / fwd=s / disp=s−1 / lit=s−2`，跨槽 fwd 两段（§9 段0323 + 本轮裁定） | `tcon_top` 的 `fw_*`/`disp_*`；`tcon_data_tx` 的 `fwd_*`+`load_done` | 见 `PIPELINE_FRAME_TAG_TIMELINE.md` | `EXERCISED_FAIL`（核心等式从未真正执行，见 §3） |
| V12 | 数据错误→锁存熄屏直到清故障（§20 段0917-0920，Q3=B） | `tcon_top` 四态 FSM + `blank` 表达式 | 见 `FAULT_RECOVERY_FSM.md` | `EXERCISED_FAIL`：P14–P19 打印 PASS，但同轮整体 FAIL |
| V13 | 无有效显示标签不得选通（Q2=A 裁定） | `scan_stb = stb_seq && safe && !flt && (!act \|\| disp_ok)` | — | `EXERCISED_FAIL` |
| V14 | 启动预充两列不丢首列（§9 段0323） | ACTIVE 下预充两槽 `disp_valid=0` → BLANK 保持、无选通 | 见 `PIPELINE_FRAME_TAG_TIMELINE.md` §2 | `EXERCISED_FAIL` |
| V15 | 50 MHz DCLK 连续、384 沿/窗（§12 段0461、§14） | `tcon_data_tx` 不变 | — | `EXERCISED_FAIL`（P10 20 ns） |

---

## 2. 本轮实际新增的"实物"

| 实物 | 文件 | 编译状态 |
|---|---|---|
| V1.3 列首同步接收状态机 | `rtl/tcon_video_rx.v.txt`（重写） | `vlog` 0 error 0 warning |
| 标签/显示许可/锁存熄屏 FSM 顶层 | `rtl/tcon_top.v.txt`（重写） | 同上 |
| 转发标签 + `load_done` + 故障零载荷 | `rtl/tcon_data_tx.v.txt`（重写） | 同上 |
| Data 行为替身 ×2 | `rtl/data_model.v.txt`（新） | 同上 |
| Scan 行为替身 ×2 | `rtl/scan_model.v.txt`（新） | 同上 |
| 联合 TB（39 条断言，P01–P40） | `tb/tcon_t2b_tb.sv.txt`（新） | 同上 |
| T2B runner（断言下限 39） | `tb/run_tcon_t2b.sh`（新） | `bash -n` OK |
| T1 TB 端口补全（8 条警告消除） | `tb/tcon_t1_tb.sv.txt`（改） | 同上 |

旧口径的文件（T2A/T2AR2 的 `tcon_t2a_tb`、`run_tcon_t2a.sh`、63 条断言）**原样保留**，按裁定只作归档，不用于新接口合规证明。

---

## 3. 三次运行的真实结论（这是本轮最重要的部分）

| run | 结果 | 失败点 | 定位到的根因 |
|---|---|---|---|
| #1 | 11/39 后中止（当时 chk 仍为 fail-fast） | `P11_latch_at_828` | TB 里两个 `#1` 块共用 `lat_d` 竞态：位置捕获读到已被本拍更新的 `lat_d`，边沿丢失 |
| #2 | 37/38 | `P39_frame_tag_propagates_across_wrap` | ① `data_model` 列号高位取错位（`cap[1][1:0]` 取成了 frame[1:0]，应为 `cap[1][7:6]`）；② TB 在 SCAN_STB 同拍读 Scan 模型，但 `SCAN_STB` 由 `slot_cycle` 组合产生、在时钟沿之后才抬升，真实 Scan 芯片要到**下一拍**才锁存 |
| #3 | 37/39 | `P39` + `P40_core_check_not_vacuous` | ② 未修，因此"核心等式"一次也没有真正执行；新增的**空洞性守卫 P40** 把这件事暴露出来 |

**必须写清楚的一件事**：run02/run03 里 `P03_labels_scan_eq_data`、`P05_banks_valid_and_clean`、`P07_content_matches_pattern` 显示 PASS，但它们是**空洞通过**——`cur_sel_v` 恒为 0，那些比较一次都没进。这正是上轮复审警告的"两个模型同时用错计数器仍显示 PASS"。P40（`core_n > 100`）就是为此加的，它在 run03 里 FAIL，因此本轮**没有任何"核心等式通过"的结论**。

---

## 4. 已修但未验证（留给下一次授权运行）

| 修复 | 内容 | 状态 |
|---|---|---|
| 采样相位 | Scan 观测改为"选通后一拍"读取（`pend`/`pend_col`） | `COMPILED_ONLY` |
| 列号解码 | `data_model` 改为 `{cap[1][7:6], cap[0]}` | `COMPILED_ONLY` |
| 内容模板 | TB 的 tag1 期望改为 `{cur_sel[9:8], frame[5:0]}`（与 8 bit 实际一致） | `COMPILED_ONLY` |
| 波形窗口 | TB 前 10 槽 `$dumpvars`，帧扫描前 `$dumpoff`（控体积） | `COMPILED_ONLY` |

**遗留未解释项**：run01–03 的 `win_edges` 在 10 槽内为 3528（若每槽满 384 应为 3840）。已确认 `load_cnt` 逻辑未改，怀疑与 `$dumpoff`/初相位或首个窗口起点有关，需在下一次运行时用打印核实，**不得**在未核实前当成"384 已证"。

---

## 5. 结论

- V1.3 输入接口、四级标签、锁存熄屏、Data×2/Scan×2 行为替身的**代码全部到位且编译零告警**。
- **本轮没有任何一条要求达到 VERIFIED**；T1 回归 `NOT_RUN`。
- 需要的下一步：**额外授权 2 次 ModelSim**（1 次联合验证 + 1 次 T1 `SCEN=ALL`），或按你的裁定另行安排。
- 不得据本文件宣称"T2B-B 通过""V1.3 合规""五芯片联动已验证"。
