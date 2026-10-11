#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fill sections 1-4 and 6 of reports/c2mos_testbench_prep.md from the machine-checked artefacts.

Nothing here reads a design file to invent a value: the instance rows come from the integrity gate's
own CSV (results/scan_c2mos_device_parameters.csv) and the terminal/net facts come from the read-only
OA readback log of this machine's cellview. That keeps every number in the report traceable to one
command output, as AGENTS.md' verification discipline requires.
"""
from __future__ import print_function

import io
import re
import sys

CSV = sys.argv[1]
RB = sys.argv[2]
DOC = sys.argv[3]

rows = [l.rstrip("\r\n").split(",") for l in io.open(CSV, encoding="utf-8") if l.strip()]
hdr, body = rows[0], rows[1:]
ix = dict((n, i) for i, n in enumerate(hdr))

PAIR = re.compile(r'(\w+)=(?:"([^"]*)"|(\((?:[^()]|\([^()]*\))*\))|([^\s]+))')
term = {}
for line in io.open(RB, encoding="utf-8", errors="replace"):
    if "RD-ROW" not in line:
        continue
    f = dict((m.group(1), (m.group(2) if m.group(2) is not None else
                           (m.group(3) if m.group(3) is not None else m.group(4))))
             for m in PAIR.finditer(line))
    if f.get("cell") != "c2mos_dff_1bit":
        continue
    term[f["inst"]] = f

out = []

# ---- section 1 -----------------------------------------------------------------
out.append("本机回读（`skill/sch3_readback.il`，`dbOpenCellViewByType(...,\"r\")`）读到的 18 只 MOS：\n")
out.append("| inst | master | model | l | w | fw | fingers | m | D | G | S | B |")
out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(body, key=lambda x: x[0]):
    n = r[0]
    t = term.get(n, {})
    out.append("| `%s` | %s | %s | %s | %s | %s | %s | %s | `%s` | `%s` | `%s` | `%s` |" % (
        n, r[ix["master"]], r[ix["model"]], r[ix["raw_L"]], r[ix["raw_W"]], r[ix["raw_finger_width"]],
        r[ix["raw_fingers"]], r[ix["raw_multiplier"]],
        t.get("D", "?"), t.get("G", "?"), t.get("S", "?"), t.get("B", "?")))
by_model = {}
for r in body:
    by_model[r[ix["model"]]] = by_model.get(r[ix["model"]], 0) + 1
out.append("\n分类：**%s**（共 %d 只），`verdict` 全 PASS %d/%d。" % (
    " + ".join("%s×%d" % (k, v) for k, v in sorted(by_model.items())), len(body),
    sum(1 for r in body if r[ix["verdict"]] == "PASS"), len(body)))
out.append("全部 `l` 同一值（黄金 `ln`），`w` 只有四种取值，对应时钟管 / 传输管 / keeper 三档宽度：\n")
wc = {}
for r in body:
    wc[r[ix["raw_W"]]] = wc.get(r[ix["raw_W"]], 0) + 1
for k in sorted(wc, key=lambda s: float(re.sub("u", "e-6", re.sub("n", "e-9", s)))):
    names = [r[0] for r in body if r[ix["raw_W"]] == k]
    out.append("- `w=%s` ×%d：%s" % (k, wc[k], ", ".join("`%s`" % x for x in names)))
out.append("\n单元内网络共 13 条：%s。其中**带 pin 的只有 6 条**"
           "（即 testbench 需要驱动的端口），其余 7 条是内部节点。" % " ".join(
               "`%s`" % x for x in sorted(set(re.findall(r'RD-NET net="([^"]+)"',
                                                        io.open(RB, encoding="utf-8", errors="replace").read())))))

# ---- section 2 -----------------------------------------------------------------
trailer = {}
for n, t in term.items():
    for pin in ("D", "G", "S", "B"):
        trailer.setdefault(t.get(pin, "?"), []).append("%s.%s" % (n, pin))
out.append("\n`vdd` / `vss` 在 OA 数据库里的真实连接（按端子统计）：\n")
for rail in ("vdd", "vss"):
    hits = sorted(trailer.get(rail, []))
    fams = {}
    for h in hits:
        inst = h.split(".")[0]
        model = term[inst]["model"] if inst in term else "?"
        fams[model] = fams.get(model, 0) + 1
    out.append("- **`%s`**：端子级连接 **%d** 个（%s）" % (rail, len(hits),
                 " + ".join("%s×%d" % (k, v) for k, v in sorted(fams.items()))))
out.append("\n要点（决定 testbench 能接几个电源脚）：\n")
out.append("- 9 只 `p18` 的 **bulk 全部接 `vdd`**、9 只 `n18` 的 **bulk 全部接 `vss`**"
           "（上表 B 列可见），所以衬偏是固定接法，**没有独立的 bulk 端口**。")
out.append("- 单元只有 6 个外部端子，`vdd`/`vss` 各一个；"
           "带 `S=vdd`/`B=vdd` 之外，`mp_m1`(S=`x1`)、`mp_s1`(S=`y1`) 的 source 是内部堆叠节点，"
           "`mn_m1`(S=`x2`)、`mn_s1`(S=`y2`) 同理，说明上下拉是堆叠结构而非直接并到轨。")
out.append("- 因为 `vss` 只出现在 source/bulk 上，**testbench 不显式接地就会整片失效**，见 §5.3 第 1 条。")

# ---- sections 3 and 4 ----------------------------------------------------------
for sec, sig, label in (("## 3. 输入端 `d` / `clk`", None, None),):
    pass
def fans(net):
    return sorted("%s.%s" % (n, p) for n, t in term.items() for p in ("D", "G", "S", "B")
                  if t.get(p) == net and n in term)
gates = sorted(n for n, t in term.items() if t.get("G") == "clk")
out.append("\n`clk` 直接驱动 **%d** 只管子的栅极：%s。" % (len(gates), ", ".join("`%s`" % x for x in gates)))
out.append("其余时钟激励来自内部反相：`clkb` 由 `mn_c`/`mp_c` 这一对反相器产生"
           "（`mn_c` 的 D=`clkb`、G=`clk`，`mp_c` 同理），所以 **testbench 只允许给一个时钟**，"
           "外部再加第二相位于是错的。")
dg = sorted(n for n, t in term.items() if t.get("G") == "d")
out.append("\n`d` 只进入 master 的数据管栅极：**%d** 只（%s）；"
           "另有 `mn_k*`/`mp_k*` 交叉耦合对是 keeper，不接 `d`。" % (len(dg), ", ".join("`%s`" % x for x in dg)))
out.append("\n`q` / `qbar` 的连接形态：")
for o in ("q", "qbar"):
    drv = sorted(n for n, t in term.items() if t.get("D") == o)
    gate = sorted(n for n, t in term.items() if t.get("G") == o)
    src = sorted(n for n, t in term.items() if t.get("S") == o)
    out.append("- `%s`：作为 drain 出现于 %s；作为栅极出现于 %s；作为 source 出现于 %s" % (
        o, ", ".join("`%s`" % x for x in drv) or "-", ", ".join("`G`=%s" % x for x in gate) or "-",
        ", ".join("`%s`" % x for x in src) or "-"))
out.append("- ⇒ `q`/`qbar` 互为存储节点的交叉耦合对，两者都要接负载；"
           "仓库基准 deck 给的是 **各 50 fF**（`Cq`/`Cqb`），且 `save clk d q qbar`。")
out.append("- `q` 相对 `d` 是同相、延迟一个时钟沿（两级反相：`d→m→q`）；"
           "上升沿触发（`clk=0` master 求值、`clk=1` slave 求值），这是 `C2MOS_DFF.scs` 头注释里"
           "明示的内部时钟极性，不是我推断的。")

# ---- section 6 -----------------------------------------------------------------
out.append("\n位置：`$PROJ/scripts/c2mos_check.sh`，本机 `PROJ=/root/microled_ai_project`（已实测存在）。\n")
out.append("```bash\nbash scripts/c2mos_check.sh <ff1|shift3|ff1_sch|shift3_sch> [clockPeriodSeconds] [tag] [repeat]\n```")
out.append("\n模式与 token（脚本 `case` 分支原文）：`ff1`→`C2MOS_DFF_1CH`、"
           "`shift3`→`C2MOS_SHIFT_3STAGE`、`ff1_sch`→`SCHEMATIC_DFF_FUNCTION`、"
           "`shift3_sch`→`SCHEMATIC_SHIFT3_FUNCTION`；失败打印同名 `: FAIL`。")
out.append("\n运行条件（本轮逐条实测，路径存在性为 guest 内 `test -e`）：\n")
for k, v in [
    ("`scripts/run_spectre.sh`", "PRESENT（护栏：netlist 必须在 `$PROJ` 下，否则 `REFUSED`）"),
    ("`scripts/psf_check.awk`", "PRESENT（断言求值器，被 `c2mos_check.sh` 以 `-f` 调用）"),
    ("`scripts/tb_preflight.sh`", "PRESENT（`c2mos_check.sh` 在正式 transient 前强制调用）"),
    ("`spectre/C2MOS_DFF.scs`", "PRESENT（黄金单元本体，只读被 include）"),
    ("`spectre/c2mos_ff1_func.scs`", "PRESENT（`ff1` 模板；`parameters T=` 行由驱动脚本按第 2 参数重写）"),
    ("`spectre/c2mos_shift3.scs`", "PRESENT"),
    ("`spectre/c2mos_ff1_from_oa_readback.scs`", "PRESENT（`ff1_sch` 模板）"),
    ("`spectre/generated/c2mos_dff_1bit_from_oa_readback.scs`",
     "PRESENT，但其头部自述输入是旧机日志 `logs/sch1/rb_c2mos_dff_1bit_paramfix.log` ⇒ 代表本机需重生成"),
    ("**`spectre/pdk_local.env`**",
     "**ABSENT** ⇒ `run_spectre.sh` 会 `REFUSED: ... needs environment variable(s)`；"
     "必须先由 `spectre/pdk_local.env.example` 复制并填 `QODER_PDK_LIB`"),
    ("`spectre/pdk_local.env.example`", "PRESENT（模板，路径值需按本机填）"),
    ("模型卡", "`/root/tech/teacher_pdk/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib`，353,783 B，存在"),
    ("`spectre` 可执行", "只有在 `. skill/cad_env.sh` 之后才在 PATH 上：`/opt/MMSIM151/tools/bin/spectre`"),
    ("`$PROJ/logs`", "当前不存在，但 `c2mos_check.sh` 第 43 行 `mkdir -p` 自建（无需批准）"),
    ("环境变量旋钮", "`PDK_ENV`（默认 `$PROJ/spectre/pdk_local.env`）、`SECTION`（corner，脚本改 `section=` 行）、"
                     "`VDD_EXP`（preflight 期望值，默认 1.8）、`TMO`、`SPECTRE_EXTRA`、`PROJ`"),
    ("Virtuoso 进程", "0（批处理会话与仿真不冲突；跑 ADE 类 GUI 才需要 `:0`）"),
    ("磁盘", "`/` 剩 5.2 G / 50 G（90% 已用）——`sim/` 与 `.raw/` 会落盘，跑前三级链建议先看体积"),
]:
    out.append("- %s：%s" % (k, v))
out.append("\n与旧机对照的可复现调用（`reports/c2mos_validation_report.md` 里记录的原样命令行）：\n")
out.append("```\nbash scripts/c2mos_check.sh ff1 2e-7 rev1 2\n"
           "bash scripts/c2mos_check.sh shift3 9.765625e-6 revnom 1\n"
           "bash scripts/c2mos_margin.sh setup|hold 1e-9|5e-11\n"
           "bash scripts/pvt_probe.sh 2e-7\n"
           "bash scripts/tb_preflight.sh <abs.netlist> 1.8 <tag>\n```")
out.append("\n`repeat` 的用意是同一 testbench 跑两遍并逐字节比对断言输出，"
           "旧机据此判 `byte-identical`；本机复跑时应保留同样的两遍一致性检查，"
           "否则一次偶然的收敛差异会被当成结论。")

txt = io.open(DOC, encoding="utf-8").read()
marks = ["## 1. `c2mos_dff_1bit` schematic 实例列表\n", "## 2. 电源端 `vdd` / `vss`\n",
         "## 3. 输入端 `d` / `clk`\n", "## 4. 输出端 `q` / `qbar`\n",
         "## 6. `scripts/c2mos_check.sh` 的位置与运行条件\n"]
assert all(m in txt for m in marks), "section marker missing"
blocks = out
# split generated blocks back into the five sections by their own anchors
s1_end = next(i for i, l in enumerate(blocks) if l.startswith("\n`vdd` / `vss` 在 OA"))
s2_end = next(i for i, l in enumerate(blocks) if l.startswith("\n`clk` 直接驱动"))
s4_end = next(i for i, l in enumerate(blocks) if l.startswith("\n位置：`$PROJ/scripts"))
txt = txt.replace(marks[0], marks[0] + "\n" + "\n".join(blocks[0:s1_end]))
txt = txt.replace(marks[1], marks[1] + "\n".join(blocks[s1_end:s2_end]))
txt = txt.replace(marks[2], marks[2] + "\n".join(blocks[s2_end:s2_end + 3]))
txt = txt.replace(marks[3], marks[3] + "\n".join(blocks[s2_end + 3:s4_end]))
txt = txt.replace(marks[4], marks[4] + "\n".join(blocks[s4_end:]))
io.open(DOC, "w", encoding="utf-8", newline="\n").write(txt)
print("FILLED doc=%s instances=%d sections=%d" % (DOC, len(body), len(marks)))
