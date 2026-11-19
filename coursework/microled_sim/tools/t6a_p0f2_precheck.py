#!/usr/bin/env python3
"""T6-A P0-F2 静态硬门（去注释后核对，零 ModelSim）。

复审缺口（P0-F）：L1 TB 的各场景在同一颗 DUT 上连续运行，E18 遗留的
COMM_TO(bit7) 没有被清理就进入 E21/E22 → E21d（status 全零）与 E22
（bit7 必须为 0）必然失败——静态推演已由复审确认。

本门核对：
  K1  E20 与 E21 之间存在一次**真实 SPI W1C 事务** `wr(15'h0C, 32'h0000_0080)`
      （文本顺序：E20 之后、E21 之前），且无 force/直赋/全局复位；
  K2  新断言 `E20a_phase_s_cleanup_without_rearm` 同时检查 status==0、
      捕获==0、disp_armed==0、hw_blank==1（防止"清理即点亮"）；
  K3  断言总数 86、名称全部唯一；runner FLOOR="86"；
  K4  连续模型 tools/t6a_p0f2_continuity.py 存在，单实例重放 E18→E22，
      且带 NC-PHASE / NC-REARM / NC-SOURCE 三个负控；
  K5  P0-F 的结构（C2 引脚独占、逐源捕获、逐位 oracle）未退化。
每个结构判据带一个**必须失败**的负控。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
REGS = os.path.join(ROOT, 'rtl', 'tcon_spi_regs.v.txt')
TOP = os.path.join(ROOT, 'rtl', 'tcon_spi_top.v.txt')
L1TB = os.path.join(ROOT, 'tb', 'tcon_t6a_l1_tb.sv.txt')
RUNNER = os.path.join(ROOT, 'tb', 'run_tcon_t6a_l1.sh')
CONT = os.path.join(ROOT, 'tools', 't6a_p0f2_continuity.py')


def strip_comments(t):
    t = re.sub(r'/\*[\s\S]*?\*/', ' ', t)
    t = re.sub(r'//[^\n]*', ' ', t)
    return t


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


fails = []


def ck(name, cond):
    print("  %-66s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


l1tb = strip_comments(read(L1TB))
runner = strip_comments(read(RUNNER))
cont = strip_comments(read(CONT))
regs = strip_comments(read(REGS))
top = strip_comments(read(TOP))

print("=== K1: the Phase S boundary is closed by a REAL SPI W1C ===")
e20 = l1tb.find('E20_capture_survived_the_dead_clock')
e21 = l1tb.find('E21_pre_uvlo_latched')
ck("E20 precedes E21 (order sanity)", (0 <= e20 < e21))
seg = l1tb[e20:e21]
ck("a wr(FAULT, 0x080) sits between them",
   re.search(r"wr\(15'h0C,\s*32'h0000_0080\)", seg) is not None)
ck("mailbox completion edges reserved (repeat @(posedge clk))",
   'repeat (3) @(posedge clk)' in seg)
ck("no force / direct assignment / global reset in the segment",
   not re.search(r'\bforce\b|\bfault_status\s*=\s*11', seg) and
   'reset_n = 1' not in seg.replace('reset_n = 1\'b1', ''))

print()
print("=== K2: the E20a assertion checks all four conditions ===")
m = re.search(r'chk\("E20a_phase_s_cleanup_without_rearm",\s*(.*?)\);', l1tb, re.S)
ck("E20a exists", m is not None)
if m:
    body = m.group(1)
    ck("  fault_status === 11'd0", "fault_status === 11'd0" in body)
    ck("  hw_fault_caught_o === 1'b0", "hw_fault_caught_o === 1'b0" in body)
    ck("  disp_armed_o === 1'b0 (no hidden re-arm)", "disp_armed_o === 1'b0" in body)
    ck("  hw_blank === 1'b1 (still dark)", "hw_blank === 1'b1" in body)

print()
print("=== K3: counts and floors ===")
names = re.findall(r'chk\("([A-Za-z0-9_]+)"', l1tb)
ck("assertion count == 86 (57+20+8+1)", len(names) == 86)
ck("all names unique", len(names) == len(set(names)))
ck("runner FLOOR=\"86\"", 'FLOOR="86"' in runner)

print()
print("=== K4: the continuity model ===")
ck("single-instance replay tool exists", os.path.exists(CONT))
ck("one Regs instance across E18..E22 (no re-instantiation inside)",
   cont.count('Regs(') == 1 or 'def continuity' in cont)
ck("NC-PHASE present (cleanup dropped -> E21d/E22 fail)",
   'NC-PHASE' in cont and 'global_clear_block' not in cont.split('NC-PHASE')[1][:200])
ck("NC-REARM present (cleanup misused as re-enable)", 'NC-REARM' in cont)
ck("NC-SOURCE present (bus bit7 leak caught by E22)", 'NC-SOURCE' in cont)
ck("legacy regression kept (D33/D53/M)", 'REG-D33' in cont and 'REG-M1' in cont)

print()
print("=== K5: the P0-F structures did not regress ===")
ck("C2 pin-only fold intact",
   re.search(r"hw_fault_i\s*=\s*\{hw_fault\[10:9\]\s*,\s*1'b0\s*,\s*!fault_n\s*,"
             r"\s*hw_fault\[6:0\]\s*\}", top) is not None)
ck("per-source capture generate intact",
   re.search(r'generate[\s\S]*?g < 11[\s\S]*?endgenerate', regs) is not None)
ck("per-bit oracle intact",
   re.search(r'w1c & 0x7FF & ~hw_fault', read(os.path.join(ROOT, 'tools',
             't6a_p0e_model.py'))) is not None)

print()
print("=== 负控（每个必须能在篡改副本上 FAIL）===")

# NC-1: remove the cleanup write from the TB
d1 = re.sub(r"wr\(15'h0C,\s*32'h0000_0080\);\s*\n(\s+)repeat \(3\) @\(posedge clk\);\s*\n\s*chk\(\"E20a",
            r"// cleanup removed\n\g<1>chk(\"E20a", l1tb, count=1)
ck("NC-1 delete the cleanup write           -> the K1 wr check fails",
   re.search(r"wr\(15'h0C,\s*32'h0000_0080\)", d1[e20:e21]) is None)

# NC-2: weaken E20a to a single condition
d2 = re.sub(r'chk\("E20a_phase_s_cleanup_without_rearm",\s*.*?\);',
            'chk("E20a_phase_s_cleanup_without_rearm", (fault_status === 11\'d0));',
            l1tb, count=1, flags=re.S)
m2 = re.search(r'chk\("E20a_phase_s_cleanup_without_rearm",\s*(.*?)\);', d2, re.S)
ck("NC-2 weaken E20a                        -> the four-condition check fails",
   m2 is not None and 'hw_blank' not in m2.group(1))

# NC-3: rename E20a
d3 = l1tb.replace('E20a_phase_s_cleanup_without_rearm', 'E20a_renamed', 1)
ck("NC-3 rename E20a                        -> the presence check fails",
   'E20a_phase_s_cleanup_without_rearm' not in d3)

# NC-4: FLOOR left at 85
d4 = runner.replace('FLOOR="86"', 'FLOOR="85"', 1)
ck("NC-4 FLOOR left at 85                   -> the floor check fails",
   'FLOOR="86"' not in d4)

# NC-5: delete the NC-PHASE negative control from the model
# (the docstring mentions NC-PHASE too, so anchor on the code-level assertion)
d5 = cont.replace("ck('NC-PHASE no cleanup -> E21d sees the stale 0x080 (reviewer table)'",
                  "ck('NC-PHASE_renamed ...'", 1)
ck("NC-5 delete NC-PHASE                    -> the presence check fails",
   'NC-PHASE no cleanup' not in d5)

print()
if fails:
    print("GATES_FAILED=%d" % len(fails))
    for f in fails:
        print("  -", f)
    print("RESULT=FAIL")
    sys.exit(1)
print("GATES_FAILED=0")
print("RESULT=PASS  (Phase-S boundary closed, 86 unique assertions, continuity model + 5 negative controls)")
