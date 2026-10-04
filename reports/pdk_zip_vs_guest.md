# 老师给的 `pdk资料.zip` vs 虚拟机里的 SMIC 018 MM RF —— 完整性对比

对比时间 2026-10-04。方式：zip 用 Python 读取条目+**CRC-32**，guest 侧用 `scripts/tree_manifest.py` 生成同格式清单（path/size/crc32），逐文件比对。**全程只读，`/root/tech` 未做任何修改。**

## 结论（一句话）

**不是同一份，虚拟机里那份明显更旧、且不完整**：老师给的是 2025 年的 `ms018_enhanced_v1p2_rev0`（**BSIM4**）+ `mse018_v1p11_rf`，虚拟机里是 2007-09-20 的 `ms018_v1p7`（**BSIM3v3**）+ `ms018_rf_v1p5`。两套模型文件名**零重叠**，模型类型都不同。因此本项目**必须使用老师那份**，已原样装入工程目录（`/root/microled_ai_project/pdk/smic18mmrf_teacher`，3975 文件，120 MB，解压后与 zip 逐文件 CRC 全对）。

## 1. 两份的规模与世代

| | 老师 `pdk资料.zip` | 虚拟机 `/root/tech/smic_018mmrf-OA/.../SMIC_018_MMRF` |
|---|---|---|
| zip 大小 | 55,826,083 B；5331 条目（3975 文件 + 1356 目录项）；解压 0.10 GB | — |
| 目录内文件数 | **3975** | **1825** |
| 磁盘占用 | 120 MB（解压副本） | 41 MB |
| 模型文件日期 | 2025-01-18（`ms018_enhanced_v1p2_rev0_spe.lib` 353,783 B） | **2007-09-20**（`ms018_v1p7_spe.lib` 27,545 B） |
| MOS 模型格式 | **BSIM4** | **BSIM3v3**（9 个 model 声明） |
| `.spe.mdl` 体积 | 154,312 B | 38,272 B（约 1/4） |
| RF 模型集 | `mse018_v1p11_rf_spe.lib`（218 KB）+ 电感/MIM/变容 `.ckt` | `ms018_rf_v1p5_spe.lib`（7.8 KB） |
| Verilog-A 无源 | `res.va`、`res_rf.va`、`gc.va`（栅漏电导） | 未见对应文件 |
| 工艺标称 | 0.18 µm Mixed-Signal **Enhanced** 1.8 V/3.3 V，1P6M | 0.18 µm Mixed-Signal 1.8 V/3.3 V 1P6M |

## 2. 逐文件比对结果

| 类别 | 数量 | 说明 |
|---|---|---|
| 路径相同且内容相同（CRC 一致） | **562** | 主要是 OA cell 的静态视图文件 |
| 路径相同但内容不同 | **768** | 含 `cds.lib`、`display.drf`、`smic18mmrf/.oalib`、`data.dm`、`*.Cat` 等 —— 一部分是版本差异，一部分是 guest 里库被 Cadence 打开过而重写 |
| 只在 zip 里 | **2645** | `Calibre/`(33)、`emxkit/`(11)、`docs/`(9)、`stream/`(2)、`SMIC18MMRF_skillUtility/`(2)、`techfile.tf`(1)、`models/`(84)、`smic18mmrf/` 多出的 cell 视图(2503) |
| 只在 guest 里 | **495** | `Spice_Model/`(56)、guest 自己的 `DRC/`(6)、`Design_Rule/`(5)、`Technology_File/`(5)、`LVS/`(3)、`techfile/`(1)、`icc.rules`(1)、`REVISION`(1)，以及 `models/` 里那 36 个 2007 版文件 |

`models/` 目录单独看：zip 84 个文件（其中 `models/spectre` 38 个，1,861,760 B）vs guest 36 个（`models/spectre` 19 个，236,813 B），**文件名交集为 0**。

## 3. 谁缺什么

- **虚拟机里缺**：老师这套 Enhanced BSIM4 模型全套、RF v1.11 模型、Verilog-A 无源模型、Calibre DRC/LVS/XRC 官方 deck（zip 里是 `SMIC_CalDRC_018LGMS_1833_V1.20_REV1_0.drc`、`SMIC_CalLVS_018MSERF_1833_V1.11_REV2_0.lvs`、XRC `TD-MM18-XC-2069-V1.20_REV0_0`）、`docs/` PDF 说明、`emxkit`、`techfile.tf`(77 KB)。
- **zip 里没有**（只存在于虚拟机那份）：guest 自带的旧 `DRC/LVS/Design_Rule/Technology_File/Spice_Model` 目录和 2007 版模型 —— 属于更早的一次交付，不是"zip 缺东西"。
- OA 库本体：zip 的 `smic18mmrf/` 有 3831 个文件，guest 只有 1709 个 → **虚拟机里的 OA 库视图也是不完整的**（少了约一半文件，含部分 cell 的额外视图）。

## 4. 装载与校验（可复现）

```
# zip 清单（Windows）
python scripts/tree_manifest.py  <dir>  ...            # 本次用 Python zipfile 直接读 CRC
# 传到 guest（53 MB，VMnet8 上 0.75 s）
scp pdk资料.zip root@<guest>:/root/microled_ai_project/
# 校验压缩包 + 解压到工程内独立目录（不碰 /root/tech）
unzip -tq ... ; unzip -q -d /root/microled_ai_project/pdk/smic18mmrf_teacher ...
# 生成 guest 清单并回传比对
python scripts/tree_manifest.py /root/microled_ai_project/pdk/smic18mmrf_teacher logs/teacher_copy_manifest.json
```

比对结果：`zip entries=3975 extracted=3975  missing_after_extract=0  crc_mismatch=0`
→ **guest 里的副本与老师的 zip 逐字节一致**（传输与解压都没有损坏或被裁剪）。
原始 zip 已从 guest 删除（省 53 MB），只保留解压副本。磁盘余量：装完后 `/` 仍有约 5.2 GB。

机器可读件：`pdk_compare/zip_manifest.json`、`pdk_compare/guest_mmrf_manifest.json`、`pdk_compare/teacher_copy_manifest.json`(guest)、`pdk_compare/mmrf_diff.json`。

## 5. 用老师这份模型做的验证（16 项判据里的 8 项）

入口按 kit 自带 readme 的规定写法：

```
include "/root/microled_ai_project/pdk/smic18mmrf_teacher/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib" section=tt
```

可用 corner（从 `.lib` 里实际读出）：MOS `TT FF SS FNSP SNFP MOS_MC`；`RES_/BJT_/DIO_/VAR_/MIM_` 各有各自 corner；RF 集在 `mse018_v1p11_rf_spe.lib`（`tt spirind_tt diffind_tt 3tdiffind_tt var_tt res_tt mim_tt mc`）。

器件几何合法范围（读卡得到，避免重蹈 SMIC 18EE 那次 CMI 报错）：

| 器件 | lmin | lmax | wmin | wmax |
|---|---|---|---|---|
| `n18` | 1.5e-7 | 1e-4 | 1.9e-7 | 1e-4 |
| `p18` | 1.5e-7 | 1e-4 | 1.9e-7 | 1e-4 |
| `n33` | 3.5e-7 | 1e-4 | 2.2e-7 | 1e-4 |
| `p33` | 3e-7 | 1e-4 | 2.2e-7 | 1e-4 |

实测结果（`MODEL_PROBE_SMIC18MMRF: PASS`，8/8）：

```
MMRF18_N_cutoff_at_rail      got=1.800000e+00  relerr=0.00e+00
MMRF18_N_on_pulls_node_down  dn=0.00479297  (< 1.75)
MMRF18_P_on_pulls_node_up    dp=1.77812     (> 0.05)
MMRF18_P_cutoff_at_ground    delta=1.647e-06
MMRF33_N_cutoff_at_rail      got=3.300000e+00  relerr=0.00e+00
MMRF33_N_on_pulls_node_down  dn=0.00863372  (< 3.2)
MMRF33_P_on_pulls_node_up    dp=3.26451     (> 0.05)
MMRF33_P_cutoff_at_ground    delta=1.604e-07
```

同时另两个库一并回归通过（同一次运行总计 16/16）：`MODEL_PROBE_TSMC18: PASS`(4/4)、`MODEL_PROBE_SMIC18EE: PASS`(4/4)、总 token `PDK_MODEL_PROBE: PASS`。

## 6. 对本项目的直接影响

1. 后续所有仿真/设计**只用** `/root/microled_ai_project/pdk/smic18mmrf_teacher`（老师的原始交付，位级一致）。`/root/tech` 那份 2007 版 BSIM3v3 不再作为设计依据，仅作历史对照。
2. 若之后要在 Virtuoso 里画 schematic/layout 并使用这个库，需要为它准备 `cds.lib` 指向**副本**路径（老师 zip 里的 `cds.lib` 是 221 B 的相对写法，guest 那份 282 B 是旧的绝对写法）。这一步会写进我们自己的工程目录，不动 `/root/tech`。
3. 老师的 zip 里有官方 Calibre DRC/LVS/XRC deck，所以后续做版图后**具备**跑规则检查的条件（但需要 Calibre license，本轮没试）。
4. `docs/` 里的 PDF（Layout_Techfile、模型 main document 等）是规格来源之一，需要具体器件参数时应先从这些文档或 `.lib` 读取，而不是猜测。

## 7. 安全边界

未修改 `/root/tech` 任何文件（对比只用 `stat/crc32`）；未修改虚拟机里的 PDK；老师 zip 只读并解到 `/root/microled_ai_project/pdk/`（新增 120 MB）；模型参数值未复制到本报告（只写器件名、corner 名、几何合法范围与 include 语法）。
