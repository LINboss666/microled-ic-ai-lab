# SOURCE_MANIFEST — 可核对原件清单

**任务** `TCON-T2B-20261114` A.6 ｜ 基线 `d17c5de` ｜ 未运行任何仿真

每个引用件都给出**完整 SHA-256**与字节数；`VIDEO_CONTRACT_DIFF.md` 的每条引文都能按 `v13_fulltext.txt` 的行首编号逐字核对。

| # | 原件 | 路径 | 字节 | SHA-256 |
|---|---|---|---|---|
| 1 | V1.3 原始规格书（唯一权威来源，SHA 与 T0R 认定一致） | `C:/Users/LMX/Downloads/V1.3_20261019_from_handoff.docx` | 3,412,105 | `6b61e4abf49616be12cd491bafe0003daad1ce0f69a20243bafa72c55354afaa` |
| 2 | V1.3 全文抽取（本文所有引文的行号来源） | `D:/ic617_tcon_t2ar2_20261114/v13_fulltext.txt` | 62,767 | `6b42b1365b95e74159467bbb1ff600c628eb7e690a13ab44a2888ab191d7a791` |
| 3 | TCON 顶层（blank/slot_bad/col_id/scan_stb） | `coursework/microled_sim/rtl/tcon_top.v.txt` | 12,543 | `c94e9ab9dec9cf4d807897593cd9c836cbdf03e120a70a342d4ef891e8768e12` |
| 4 | 视频接收（COL_SYNC 语义所在） | `coursework/microled_sim/rtl/tcon_video_rx.v.txt` | 11,155 | `6607d06c9fa59b46398176be262663bc25e5573554ecc4a91df964a80d79f51d` |
| 5 | 数据转发（预取/撤销/装载窗） | `coursework/microled_sim/rtl/tcon_data_tx.v.txt` | 8,049 | `a1528010fc195713b0404cd271c6da92426f1e8a6a3a4d1780cf02c4e11480f8` |
| 6 | 槽相位（LATCH 828 / PWM_START 840 / SCAN_STB 880） | `coursework/microled_sim/rtl/tcon_slot_seq.v.txt` | 2,229 | `f9b4f31720000912a7c8e0a6638d4a499549bd5dc77b461df954588f12b74903` |
| 7 | 时基（976/977、576/448、1024 槽） | `coursework/microled_sim/rtl/tcon_timebase.v.txt` | 4,431 | `1bb27df8ae799148096dbee3c1428379d5b2efd60905905fb8b115d9496953cd` |
| 8 | 双列 bank | `coursework/microled_sim/rtl/tcon_col_bank.v.txt` | 1,888 | `97c2b4bf1ed0ee54f33f5ee07290f8d81a1de8a59f36b86790b2c6c1d35aa7e4` |
| 9 | T2A 接口合同（本轮被指出的差异之一） | `coursework/microled_sim/rtl/T2A_INTERFACE_CONTRACT.md` | 5,948 | `94035c609ccca2719fd101437a104ea5dd81534e35870917f4e91ebdc86bbdb2` |
| 10 | T2A/T2AR2 测试台（63 条断言） | `coursework/microled_sim/tb/tcon_t2a_tb.sv.txt` | 36,349 | `373cb7c2fdfc9fea1d0a476beaa7bf515b48cb0f321f0d92292f1918a224da46` |
| 11 | T1 测试台（49 条断言，8 条未连接端口警告所在） | `coursework/microled_sim/tb/tcon_t1_tb.sv.txt` | 14,955 | `a1d9b706cef54d0cda19d217b1473cd04c5765b1a67316dded92dbde0636e9b3` |
| 12 | run03 原始 VCD（列 19 两字节/382 零的证据） | `D:/ic617_course_sim_20261112_native/t2ar2_run03_all/tcon_t2a.vcd` | 12,732,464 | `f736354192f47e82c2724fbe0418e21b3158e1cc76204015c98ea0f3c0984d39` |
| 13 | 由该 VCD 独立解析出的 D0/D1 采样 | `D:/ic617_course_sim_20261112_native/t2ar2_d0d1_samples.csv` | 224,893 | `4f9d1bb0214b7202d54c0b8e3fd7ae157a9fa39ed86405b254fffa1b87fd878f` |
| 14 | T2AR2 审核包（本轮被复审的对象） | `D:/ic617_tcon_t2ar2_20261114/MicroLED_TCON_T2AR2_Review_20261114.zip` | 2,273,756 | `5822b8a9ce5c73badc1f1e879183dfbdd4de42b4ea50bacf078a6dbff1346178` |
| 15 | T2AR2 独立复审报告（本轮输入） | `C:/Users/LMX/Downloads/MicroLED_TCON_T2AR2_独立复审报告_20261114.md` | 9,991 | `d45f51c3169de34ccfbd1916537a1bd5072e320dc8013cac8ce4c65c1e8e19ab` |
| 16 | T2B 任务书（本轮执行依据） | `C:/Users/LMX/Downloads/MicroLED_TCON_T2B_接口与流水对齐_Qoder任务书_20261114.md` | 3,232 | `5fe58363a196a2d37f69418e673c35360fe5665dbc9d7731bbfbf275b387c070` |
| 17 | T2AR VCD 独立复核 JSON（9,320 ns 反例） | `C:/Users/LMX/Downloads/MicroLED_T2AR_VCD_独立复核结果.json` | 2,911 | `1b9bc96a67b75ba379edac0713904d41467eac68913a52b4142ca92489489398` |
| 18 | 隔离副本 staged 闸门原始终端 | `D:/ic617_t2b_gate_isolated/gate_staged_repro.txt` | 168 | `76d200a97be9f5b6fcbb139869c18915ea29cd50eaa8b158dcad7bdc13b7dfcf` |
| 19 | 隔离副本 history 闸门原始终端 | `D:/ic617_t2b_gate_isolated/gate_history_repro.txt` | 199 | `850758ce3d11c9262009e6a4fd550d8a88f7bf46bdf7eb06b10c416a10ab7c77` |
| 20 | 隔离副本暂存文件清单（10 个对象） | `D:/ic617_t2b_gate_isolated/gate_staged_nameonly.txt` | 464 | `ee79bb8baed1b5f259fbeb7eee1df3a381779f3116510ca549de9e777f789897` |
| 21 | 隔离副本暂存 diffstat | `D:/ic617_t2b_gate_isolated/gate_staged_stat.txt` | 711 | `1c36c118ea558c3eb7357bd26a5b374d61418e1a6b583654c24564384b805aa5` |

## 关于“原件不在包内”的说明

- `V1.3_20261019_from_handoff.docx`（3,412,105 B）是**你提供的原件**，本包不复制它，只给出 SHA-256 与它的全文抽取 `v13_fulltext.txt`（逐段，行首为段号）。
- 复核方式：`sha256sum V1.3_20261019_from_handoff.docx` 应等于上表第 1 行的值；任取一条引文，在 `v13_fulltext.txt` 里按段号定位即可逐字比对。
- 上一轮 T2AR2 审核包与 run03 的 VCD 也一并列出 SHA，便于把“本轮结论”与“上一轮证据”钉在一起。
