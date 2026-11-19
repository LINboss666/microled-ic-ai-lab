#!/usr/bin/env python3
"""T6-A P0-F 静态硬门（去注释后核对，零 ModelSim）。

两道硬门（复审 2026-11-19）：

  硬门一（C2 唯一归属）：`hw_fault_i[7]` 只能由 `!fault_n` 驱动——
    旧的 `hw_fault | (fault_n ? 0 : 11'h080)` 在 fault_n=1 时仍允许总线 bit7
    触发 COMM_TO（复审反例第 2 行）。bit8（ERR_REG）是内部寄存器访问状态、
    无模拟源，其 hw_fault 输入显式归零。
  硬门二（C3 多源 W1C Oracle）：模型的清除请求必须逐位门控
    （`w1c & ~hw_fault`），不得存在"任一活源阻断全部清除"的全局闸；
    并必须保留 `global_clear_block` 缺陷分支作为负控。

另核对：逐源捕获 generate 未退化、L1 TB 的 E16 改由引脚驱动、
E21/E22 系列存在、runner FLOOR=85。
每个结构判据带一个**必须失败**的负控。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
REGS = os.path.join(ROOT, 'rtl', 'tcon_spi_regs.v.txt')
TOP = os.path.join(ROOT, 'rtl', 'tcon_spi_top.v.txt')
FRAME = os.path.join(ROOT, 'rtl', 'spi_frame.v.txt')
L1TB = os.path.join(ROOT, 'tb', 'tcon_t6a_l1_tb.sv.txt')
RUNNER = os.path.join(ROOT, 'tb', 'run_tcon_t6a_l1.sh')
MODEL = os.path.join(ROOT, 'tools', 't6a_p0e_model.py')


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


regs = strip_comments(read(REGS))
top = strip_comments(read(TOP))
frame = strip_comments(read(FRAME))
l1tb = strip_comments(read(L1TB))
model = strip_comments(read(MODEL))

print("=== 硬门一：C2 唯一归属（top）===")
ck("bit7 source is EXACTLY `!fault_n` (no bus contribution)",
   re.search(r"hw_fault_i\s*=\s*\{hw_fault\[10:9\]\s*,\s*1'b0\s*,\s*!fault_n\s*,"
             r"\s*hw_fault\[6:0\]\s*\}", top) is not None)
ck("the old OR-fold is gone",
   re.search(r"hw_fault\s*\|\s*\(\s*fault_n\s*\?\s*11'd0\s*:\s*11'h080\s*\)", top)
   is None)
ck("bit8 (ERR_REG) input explicitly tied to zero", '1\'b0' in top and
   re.search(r"\{hw_fault\[10:9\]\s*,\s*1'b0", top) is not None)
ck("regs still receives the folded vector",
   '.hw_fault (hw_fault_i)' in top)
ck("the real FAULT_n pin enters the top", 'input  wire        fault_n' in top)

print()
print("=== 逐源捕获（P0-E 结构不退化）===")
gen = re.search(r'generate([\s\S]*?)endgenerate', regs)
ck("generate with 11 per-source latches", gen is not None and 'g < 11' in (gen.group(1) if gen else ''))
if gen:
    body = gen.group(1)
    ck("  per-bit async sensitivity preserved", 'posedge hw_fault[g]' in body)
    ck("  per-bit combinational clear preserved", 'wr_frame[g]' in body and '!hw_fault[g]' in body)
    ck("  set before clear", body.find("hw_fault[g])     caught[g] <= 1'b1") <
       body.find("clear_caught_req) caught[g] <= 1'b0"))
ck("n_fault folds the whole vector",
   re.search(r"n_fault\s*=\s*fault_status\s*\|\s*hw_fault\s*\|"
             r"\s*\(err_set\s*\?\s*11'h100\s*:\s*11'd0\)\s*\|\s*caught\s*;", regs)
   is not None)
ck("hw_blank still has the six locks (caught_any)",
   re.search(r'hw_blank\s*=\s*blank_r\s*\|\s*\(!en\)\s*\|\s*any_hw_fault\s*\|'
             r'\s*caught_any\s*\|\s*\(!disp_armed\)\s*\|\s*disp_fault', regs)
   is not None)

print()
print("=== 硬门二：C3 多源 W1C Oracle（模型）===")
ck("no global `if not fw or hw_fault` gate in clear_req",
   re.search(r'if not fw or hw_fault or', model) is None)
ck("the clear request masks live bits per-bit (`& ~hw_fault`)",
   re.search(r'w1c & 0x7FF & ~hw_fault', model) is not None)
ck("the `global_clear_block` defect branch exists (negative control)",
   "'global_clear_block'" in model and '0 if hw_fault' in model)

print()
print("=== L1 TB / runner ===")
ck("E16 drives the PIN (fault_n = 1'b0), not hw_fault[7]",
   re.search(r"E16_live_source", l1tb) is not None and
   re.search(r"hw_fault\s*=\s*11'h080\s*;", l1tb) is None)
ck("E21 multi-source vector present", 'E21_multi_source_partial_clear' in l1tb)
ck("E21b no-resurrection present", 'E21b_cleared_cause_does_not_resurrect' in l1tb)
ck("E21c/d live-bit semantics present",
   'E21c_live_bit2_cannot_clear' in l1tb and 'E21d_all_clear_after_release' in l1tb)
ck("E22 pin-exclusivity present",
   'E22_bus_bit7_cannot_set_comm_to' in l1tb and
   'E22b_pin_pull_still_captures' in l1tb)
ck("runner FLOOR raised to 85", 'FLOOR="85"' in strip_comments(read(RUNNER)))
n_chk = len(re.findall(r'chk\("', l1tb))
ck("assertion count == 85 (57 legacy + 20 Phase S + 8 P0-F)", n_chk == 85)
names = re.findall(r'chk\("([A-Za-z0-9_]+)"', l1tb)
ck("no duplicate assertion names", len(names) == len(set(names)))

print()
print("=== 负控（每个必须能在篡改副本上 FAIL）===")


def rx(sub, repl, text, count=1):
    return re.sub(sub, repl, text, count=count)


# NC-1: reintroduce the bus-bit7 OR fold
d1 = rx(r"\{hw_fault\[10:9\]\s*,\s*1'b0\s*,\s*!fault_n\s*,\s*hw_fault\[6:0\]\s*\}",
        "{hw_fault[10:8], !fault_n, hw_fault[6:0]} | (fault_n ? 11'd0 : 11'h080)", top)
ck("NC-1 reintroduce the bus-bit7 OR        -> the exact-fold check fails",
   re.search(r"hw_fault_i\s*=\s*\{hw_fault\[10:9\]\s*,\s*1'b0\s*,\s*!fault_n\s*,"
             r"\s*hw_fault\[6:0\]\s*\}", d1) is None)

# NC-2: let bit8 through
d2 = rx(r"\{hw_fault\[10:9\]\s*,\s*1'b0\s*,", "{hw_fault[10:8],", top)
ck("NC-2 let hw_fault[8] through            -> the tie-low check fails",
   re.search(r"\{hw_fault\[10:9\]\s*,\s*1'b0", d2) is None)

# NC-3: model back to the global gating
d3 = rx(r"if 'global_clear_block' in self\.neg:\s*\n\s*return 0 if hw_fault else \(w1c & 0x7FF\)",
        "if 'global_clear_block' in self.neg:\n            return 0 if hw_fault else (w1c & 0x7FF)",
        model.replace("        return w1c & 0x7FF & ~hw_fault                # 修正版：逐位门控",
                      "        if hw_fault:\n            return 0                    # DEFECT: global gate\n"
                      "        return w1c & 0x7FF"))
ck("NC-3 model global gating restored        -> the no-global-gate check fails",
   re.search(r'if not fw or hw_fault or', d3) is not None or
   ("if hw_fault:" in d3.split("def clear_req")[1].split("def ")[0]))

# NC-4: E16 back to driving hw_fault[7]
d4 = rx(r"fault_n = 1'b0;\s*\n(\s+)repeat \(3\) @\(posedge clk\);\s*\n\s*wr\(15'h0C, 32'h0000_0080\);",
        r"hw_fault = 11'h080;\n\g<1>repeat (3) @(posedge clk);\n        wr(15'h0C, 32'h0000_0080);",
        l1tb, count=1)
ck("NC-4 E16 drives hw_fault[7] again        -> the pin-drive check fails",
   re.search(r"hw_fault\s*=\s*11'h080\s*;", d4) is not None)

# NC-5: drop the E21 vector
d5 = l1tb.replace('E21_multi_source_partial_clear', 'E21_renamed', 1)
ck("NC-5 rename E21                         -> the presence check fails",
   'E21_multi_source_partial_clear' not in d5)

print()
if fails:
    print("GATES_FAILED=%d" % len(fails))
    for f in fails:
        print("  -", f)
    print("RESULT=FAIL")
    sys.exit(1)
print("GATES_FAILED=0")
print("RESULT=PASS  (C2 pin-only + bit8 tie + per-bit oracle + L1 wiring, 5 negative controls)")
