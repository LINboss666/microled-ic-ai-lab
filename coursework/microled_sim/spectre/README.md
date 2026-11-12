# 课程 Spectre 交付说明（`spectre/`）

本目录只放**自研网表、测试文件与不含 PDK 内容的 runner**。
不包含任何 PDK 模型卡、模型参数、license 值、凭据、老师原始 ZIP 或原始大 PSF/波形数据库。

## 文件

| 文件 | 作用 | 真实运行状态 |
|---|---|---|
| `course_sink_unit.scs` | 课程新建的 Data 侧基本 NMOS 恒流下拉单元子电路（3 个 `n33`：Mref / Mout / Mcas，显式 D/G/S/B） | 被下列三个 job 真实调用 |
| `course_dc_tt.scs` | DC 工作点 + 0.60..1.50 V 夹持扫描（19 点） | **RUN**: job S1 首次启动 `save Ip_out:current` 被忽略（0 电流数据），job S2 修正后 0 error / 0 warning，19 点真实数值 |
| `course_tran_en.scs` | VCAS 偏置轨使能脉冲的瞬态 | **RUN**: job S3，0 error / 0 warning / 7 notices（数值方法提示），426 点真实波形 |
| `course_mc.scs` | 原生 `montecarlo` 分析 | **RUN**: 第 1 次启动语法解析失败（0 样本，已归档）；修正换行后正式启动 30 次迭代，0 error / 1 warning (SPECTRE-16006)，30 个样本全部提取 |
| `pdk_local.env.example` | 只列环境变量**名字**，不含任何真实路径 | 模板 |
| `run_course_spectre.sh` | 在原生环境里复现 job 的入口（不自动启动，需显式授权） | 参考脚本 |

## 环境注入（关键）

所有 `include "${QODER_PDK_LIB}"` 的**真实路径**来自 guest 上 gitignore 的
`spectre/pdk_local.env`，运行时以 `set -a; . <env>; set +a` 注入。
本目录**不含**该文件的真实值，也不含 `section` 之外的任何模型内容。
`course_dc_tt.scs` / `course_tran_en.scs` 用 `section=tt`，`course_mc.scs` 用 `section=mos_mc`
（该节含 `statistics { process {...} }` 与 `statistics { mismatch {...} }`）。

## 可比实验基线（不是本电路的验收阈值）

任务书指定优先采用已限定接受的 DATA-7C-B-DC-R1 单输出 TT 条件：
TT / 27 °C、`vdd18 = VCAS = 1.8 V`、`VSS = 0`、外部 `IREF = 15 µA`、输出理想夹持 `1.20 V`。

**适用局限**：历史 DC-R1 的 DUT 是八档单输出 PAM 电流阶梯，实测满量程
`I111 = 15.382706 µA`；本课程的 DUT 是**新建的 3 管基本单元**，拓扑不同，
因此历史数值只用于条件对照，**不是本电路的判据**，也没有为了追 PASS 改动任何阈值。

## 电流方向与测量

`Ip_out (clamp_node data_out) iprobe`；Spectre 15.1 里 `iprobe` 的电流变量就是实例名，
PSF TRACE 中为 `Ip_out:i`，单位 A。正读数表示电流从 `clamp_node` 流入 `data_out`，
再经 `Mcas -> NODE_M -> Mout -> VSS`，即下拉灌电流：`I_sink = Ip_out:i`，不取负、不取绝对值。

## 复现入口（需在原生 guest 环境、且获得新授权后）

```bash
set -a; . <untracked pdk_local.env>; set +a
. <sandbox>/bin/cad_env.sh
spectre course_dc_tt.scs      -64 -format psfascii
spectre course_tran_en.scs    -64 -format psfascii
spectre course_mc.scs         -64 -format psfascii
```

本轮的真实输出、日志与逐点数值见 `../results/` 与 `../../reports/course_sim/analog_test_report.md`。
原始大 PSF 文件保留在原生主机沙箱内，**不入库**；仓库只放脱敏后的小型 CSV 与统计图。
