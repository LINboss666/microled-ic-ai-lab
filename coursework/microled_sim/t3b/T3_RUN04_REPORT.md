# T3 RUN04 报告 —— 51/52，差分验证全部通过，唯一失败是 census 的一行丢失

**任务** `TCON-T3-RUN04-20261115` ｜ 授权 1 次，**用 1 次，FAIL，按纪律停止**

---

## 1. 结果

```
COURSE_RTL_ASSERT_COUNT=52   PASS=51   FAIL=1   RESULT=FAIL
T3_WINDOW_CENSUS opened384=9 closed384=0 counted=0 min=1000000 max=0 dropped=1
```

**51 条里包含 RUN03 全部 4 条失败中的 3 条**：

| RUN03 失败项 | RUN04 |
|---|---|
| D13/D14/D15 col2（与 oracle 错一字节） | **全部 PASS** —— 976/977 相位修复被仿真证实 |
| D42（census 统计） | **仍 FAIL** —— 但这次定位到一行缺失，见 §4 |

**被测 RTL `data_driver.v` 一字未改**（SHA `896a3c54…`，与 RUN03 实际仿真版本逐字节一致），
本轮全部改动在 TB 的时序组织与统计口径。

---

## 2. 预检（零仿真，全部通过）

| 复审要求 | 执行 |
|---|---|
| RTL 与 RUN03 仿真版本哈希一致 | 发现 run03 后我加过一段 Pure-mode 注释导致 SHA 变了，**已还原**到 `896a3c541794…61f5e` ✓（Pure-mode 的位宽/30 ns tick 限制改记在 `GRAY_CODE_MAPPING.md` 的 OPEN 清单里，不进 RTL） |
| 976/977 两相位逐沿推导 | `tools/t3_phase_timeline.py`：对 off=5 / off=15 两种相位各推导 384 拍的 `latch(pre)/latch(+1)/started/sent/din_valid/byte`，**两相位结果逐字节一致**：byte0 在 arming posedge、byte383 在 P+7660 ns、恰好 384 个呈现沿、oracle(+1 ns) 与 DUT 同字节 ✓ |
| `started` 多过程写入 | 已消除：`started` 现在只在 **posedge dclk** 一个块里赋值（rise→0、arming→1）；预检新增"双写审计"逐变量扫描，`dual-writer variables: none` ✓ |
| D42 增强 | `opened384 == closed384 + dropped`、`dropped<=1`、`closed384>=8`、`min==max==384` ✓ |
| 52 条断言、判据不降 | ✓ |
| 编译 0/0 | ✓ |

---

## 3. 功能证据（全部通过，且不再是空洞的）

```
D11/D12 ×3 列   384 字节装载 + 显示 bank 提交        PASS
D13/D14/D15 ×3 列  与独立 oracle 逐字节差分          PASS（含 col2）
D16/D17         映射 bank / PAM 档位随 LUT           PASS
D19             384 路导通拍数逐路 == LUT 有效宽度     PASS
D20/D21/D22     黑码 0 tick / 满码 64 tick / 饱和 63   PASS
D24–D30         短列/超长列不提交、可恢复             PASS
D31–D39         BLANK/故障/复位 同拍关断              PASS
D40             oracle 提交计数                       PASS
```

**RUN03 的 col2 差分失败已被仿真证实是测试台相位问题，修复有效。**

---

## 4. 唯一失败：D42 —— 一行缺失，已定位到语句级

探针证据（RUN04 原生 transcript）：

```
t=36415000 latch=1 cyc=828 win=0 sent=384   ← 上一窗已正常关闭（sent 计满、win 归 0）
t=36455000 latch=0 cyc=832 win=1 sent=0     ← 下一窗正常打开
```

即：**每个窗都正常关闭了**（`sent` 计满 384、`win` 归 0、`win_norm` 置 1）。
但 census 报 `closed384=0`。

根因：重构时我把快照搬进 posedge-dclk 块，**丢掉了 `win_nb_q <= win_nb;` 这一行**。
`win_nb_q` 从此恒为 0，快照里的守卫 `win_nb_q == 384` 永远不成立 →
每次正常关闭都走进"静默丢弃"路径（既不计 closed 也不计 dropped），
只有复位那次（`win_norm=0`）被计成 `dropped=1` —— 与 `opened384=9 / closed384=0 / dropped=1`
**完全吻合**。

修复 = 补回一行 `win_nb_q <= win_nb;`（posedge-dclk 块内，单写者不变）。
该行正确性可由检查直接证明：`win_nb_q` 在别处无任何赋值点，不补则守卫恒假。

---

## 5. 现在能说的和不能说的

**能说**
- Data Driver 384 路数字核的功能验证**在 RTL 不变的前提下全部通过**，包括与独立 oracle 的三列逐字节差分；
- 976/977 相位漂移的诊断被仿真证实（col2 从 FAIL 转 PASS）；
- `started` 单写者重构消除了双写隐患（预检审计 `dual-writer: none`）。

**不能说**
- 52/52 没拿到 → **T3 完整回归仍未通过**，不能提请 `ACCEPT_WITH_SCOPE`；
- D42 的逐窗 384 沿证据仍缺（机制对、账本错）；
- 综合/STA、Pure PWM、SPI、384 路模拟恒流源、T4、T5：未做。

---

## 6. 请求

追加 **1 次** ModelSim（T3 run05）。改动 = **一行** `win_nb_q <= win_nb;`（TB 统计簿记），
RTL 不变、52 条断言不变、判据不降。若 run05 仍有任何失败，我即停且不再请求。
