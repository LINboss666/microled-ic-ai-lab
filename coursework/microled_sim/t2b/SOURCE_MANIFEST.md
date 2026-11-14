# SOURCE_MANIFEST — 可核对原件清单（B 段完成后的树）

**任务** `TCON-T2B-20261114` ｜ 提交 `8419518`（其父 `84a1a71` = T2B-A，`2d49108` = T2AR2）
｜ 作者邮箱已由 `13637520049@163.com` 改为 GitHub noreply（否则 push 被 GH007 拒绝），**文件内容未变**（`git diff 7aacc31 8419518` 为空）。

| # | 原件 | 路径 | 字节 | SHA-256 |
|---|---|---|---|---|
| 1 | V1.3 原始规格书（唯一权威来源） | `C:/Users/LMX/Downloads/V1.3_20261019_from_handoff.docx` | 3,412,105 | `6b61e4abf49616be12cd491bafe0003daad1ce0f69a20243bafa72c55354afaa` |
| 2 | V1.3 全文抽取（引文段号来源） | `D:/ic617_tcon_t2ar2_20261114/v13_fulltext.txt` | 62,767 | `6b42b1365b95e74159467bbb1ff600c628eb7e690a13ab44a2888ab191d7a791` |
| 3 | 视频接收（V1.3 列首同步，B 段重写） | `coursework/microled_sim/rtl/tcon_video_rx.v.txt` | 8,483 | `9c99452723f2770029e512ca9aebc6f8c7ad6a049abe5c7217ca6da8c1057e06` |
| 4 | 顶层（FSM/标签/熄灭门控，B 段重写） | `coursework/microled_sim/rtl/tcon_top.v.txt` | 14,704 | `3303dbc8f7aadc2c8dfbf0916b534e9c5c81bb6ba500d19f765a70db4e20a371` |
| 5 | 数据转发（fwd 标签/load_done/故障零载荷） | `coursework/microled_sim/rtl/tcon_data_tx.v.txt` | 6,948 | `cc9d35f9e35154c32e005c995778e29a2b191c8f3c70164ecff30f41cf5113d1` |
| 6 | 槽相位 | `coursework/microled_sim/rtl/tcon_slot_seq.v.txt` | 2,229 | `f9b4f31720000912a7c8e0a6638d4a499549bd5dc77b461df954588f12b74903` |
| 7 | 时基 | `coursework/microled_sim/rtl/tcon_timebase.v.txt` | 4,431 | `1bb27df8ae799148096dbee3c1428379d5b2efd60905905fb8b115d9496953cd` |
| 8 | 双列 bank | `coursework/microled_sim/rtl/tcon_col_bank.v.txt` | 1,888 | `97c2b4bf1ed0ee54f33f5ee07290f8d81a1de8a59f36b86790b2c6c1d35aa7e4` |
| 9 | Data 行为替身（新） | `coursework/microled_sim/rtl/data_model.v.txt` | 4,827 | `be891992fa1b1e54c9e852f6d7d83e791ca9e58dd72a9d1b0fd4751ff29c2164` |
| 10 | Scan 行为替身（新） | `coursework/microled_sim/rtl/scan_model.v.txt` | 2,709 | `f5b60e4e8e1e1928215c531917e0b5860a8370a03bd6ae62067079486f7b65a5` |
| 11 | 联合 TB（39 条断言） | `coursework/microled_sim/tb/tcon_t2b_tb.sv.txt` | 23,101 | `822b62c6ebef1e7bb25517c8c07a8f95f326ea3d6d883af0b9a47e9e1f17d6e7` |
| 12 | T1 TB（端口补全） | `coursework/microled_sim/tb/tcon_t1_tb.sv.txt` | 16,160 | `3a8af951bf53d32512808ffd73108c5863d50159ca1cfabd6aebf1be3e1081b1` |
| 13 | run03 联合验证原始 transcript | `D:/ic617_course_sim_20261112_native/t2b_run03_joint/03_vsim.stdout` | 3,276 | `7e604176656c881ea85f871bf19ca0f13742ca0d69fd60f9b22eb016979f2935` |
| 14 | run02 联合验证原始 transcript | `D:/ic617_course_sim_20261112_native/t2b_run02_joint/03_vsim.stdout` | 2,517 | `6937937ddc305c6206f7ff08373f3819eb65f903e27d50da53e5f949ddaeec84` |
| 15 | run01 联合验证原始 transcript | `D:/ic617_course_sim_20261112_native/t2b_run01_joint/03_vsim.stdout` | 1,498 | `774cffe926bf7d431a848f11bd14ae224bdfcb352c84b9e11afec9303bdd0afb` |
| 16 | T2B 任务书（执行依据） | `C:/Users/LMX/Downloads/MicroLED_TCON_T2B_B_Qoder_执行任务书_20261114.md` | 7,986 | `bcfdcecb6eff78d0f2d8ca63834a54beff18e780e67433d6083787fc01e4e0d5` |
| 17 | T2B-A 复审与裁定（本轮输入） | `C:/Users/LMX/Downloads/MicroLED_T2B_A_独立复审与方案裁定_20261114.md` | 7,593 | `f569320c57a59994d2c77fa5b9543bc4fecf62c5ce5465210ff702ff18a813e8` |

A 段（`VIDEO_CONTRACT_DIFF.md` 等）的行号引用以 `d17c5de` 为准，B 段重写后不再对应；结论已由 B 段实现回应。
