# results/ 文件说明

## 命名约定（仓库安全闸所致，不是内容改动）

仓库现存的 `scripts/precommit_safety_check.py` 只允许固定扩展名，白名单**不含**
`.v` / `.sv` / `.png`。为在不改判据、不禁用 hook 的前提下提交，本轮：

* Verilog / SystemVerilog 源码以 `*.v.txt` / `*.sv.txt` 入库，**内容逐字节不变**
  （复用的 `dd1_d7a_gray_ctrl.sv.txt` SHA-256 仍为 `6dbf464a49e49ad489188fa51920c30a3c89d6b3106046a4fefe558ef0a50c87`）。
  `tb/run_modelsim.sh` 会把它们复制到 scratch 并还原真实扩展名后再 `vlog -sv`。
* 波形与统计图改为 **SVG 矢量图**（`.svg` 在白名单内），由真实 VCD / 真实 CSV 渲染。
* 原始 ModelSim VCD / WLF、Spectre 大 PSF、原始 transcript 的**原始字节**保留在仓库外
  native scratch 与本轮 review ZIP 的 `native_originals/`。

## 行尾空白归一化（披露）

`modelsim_compile_log.txt`、`modelsim_transcript_run02.txt`、
`modelsim_vsim_stdout_run01_FAILED.txt`、`modelsim_vsim_stdout_run02.txt` 四份日志的
**仓库内副本只去除行尾空格/Tab**，以满足 `git diff --check`；没有任何内容字符被改动
（断言文本、计数、时间、警告全部原样保留）。含原始尾空白的字节版本保存在
review ZIP 的 `native_originals/` 与仓库外 scratch，可用 SHA-256 比对。

## 原始数值来源

| 文件 | 来自 | 点数 |
|---|---|---:|
| `dc_i_v.csv` | Spectre DC job S2 的 PSF-ASCII `Ip_out:i` | 19 |
| `tran_i_t.csv` | Spectre 瞬态 job S3 的 PSF-ASCII | 426 |
| `mc_samples.csv` | MC 30 个逐迭代 PSF 文件 `mc1-001..030` | 30 |
| `course_wave_events.csv` | ModelSim TB 在仿真中直接写出的事件 | 28 |
| `mc_stats.json` / `analog_summary.json` | `checks/analyze_analog.py` 从上述 CSV 复算 | — |
| `execution_ledger.csv` | 每次原生进程启动后即时登记 | 20 行 |

**没有**合成分布、补点、剔除坏点或手工绘制的通过曲线。

## SVG 行尾空白归一化（补充披露）

`figures/*.svg` 由 matplotlib 生成，其 `<path d=...>` 属性跨行且行尾带空格。
8 张 SVG 的仓库内副本**只去除了行尾空格/Tab**（换行符保留，SVG 把换行视为空白分隔，
path 数据与全部文本标签均未改动），以满足 `git diff --check`。
重跑 `checks/render_waveforms.py` / `checks/analyze_analog.py` 会再次产生行尾空格，
需做同样归一化；图形内容一致。

## R2 新增文件（只读补证）

| 文件 | 说明 |
|---|---|
| `mc_native_provenance.csv` | 30 个 MC 样本的原生 PSF 路径、字节数、SHA-256、`Ip_out:i` 原始值 |
| `mc_native_log_extract.txt` | 脱敏的成功/失败日志要点、逐迭代进度、mapping |
| `mc_mapping.txt` / `mc_iteration_status.txt` | 迭代映射与 29 条逐迭代进度行 |
| `waveform_correction_manifest.csv` | 被修正的 2 张 SVG 的新旧 SHA、修正原因、源 VCD SHA |
| `gui_attempt/gui_evidence.txt` | Virtuoso GUI 自动截图的失败证据（221/177 B、IsUnMapped、import 错误） |
| `failed_r1/` | R1 的旧图与旧 `analog_summary.json`，作为失败/退役样本保留，未删除 |
