#!/usr/bin/env python3
"""T6-A P0-D 静态硬门（去注释后核对，零 ModelSim）。

复审要求（P0-D 任务书 D.6）：
  * 静态审查必须**先剥注释**再核对——rev3 曾出现"注释里描述缺陷、代码里仍是缺陷"
    的假阳性来源，反过来"注释里写了正确方案、代码里没改"同样会被注释骗过；
  * 清除请求必须是**组合** wire 且在同一拍生效，不得再是寄存器；
  * 捕获块的 set 必须仍在 clear 之前，且 `clear_caught_req` **不得**出现在
    敏感列表里（否则清除变成异步，死时钟也能清）；
  * L1 TB 必须显式连接 `.fault_n`。

每个结构判据都带一个**必须失败**的负控。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))   # coursework/microled_sim
REGS = os.path.join(ROOT, 'rtl', 'tcon_spi_regs.v.txt')
TOP = os.path.join(ROOT, 'rtl', 'tcon_spi_top.v.txt')
FRAME = os.path.join(ROOT, 'rtl', 'spi_frame.v.txt')
L1TB = os.path.join(ROOT, 'tb', 'tcon_t6a_l1_tb.sv.txt')
RUNNER = os.path.join(ROOT, 'tb', 'run_tcon_t6a_l1.sh')


def strip_comments(t):
    t = re.sub(r'/\*[\s\S]*?\*/', ' ', t)
    t = re.sub(r'//[^\n]*', ' ', t)
    return t


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


fails = []


def ck(name, cond):
    print("  %-62s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


regs = strip_comments(read(REGS))
top = strip_comments(read(TOP))
frame = strip_comments(read(FRAME))
l1tb = strip_comments(read(L1TB))

print("=== 1. the registered clear pulse is GONE (code, not comments) ===")
ck("no `clr_fault` identifier anywhere in the code", 'clr_fault' not in regs)
ck("no `clr_fault <=' assignment left", not re.search(r'clr_fault\s*<=', regs))

print()
print("=== 2. the combinational clear request ===")
m = re.search(r'wire\s+clear_caught_req\s*=([^;]+);', regs)
ck("`clear_caught_req` is a continuous assign (a wire, not a reg)", m is not None)
if m:
    body = m.group(1)
    ck("  driven by wr_cap_o (the same accepted write)", 'wr_cap_o' in body)
    ck("  address decode A_FAULT present", 'A_FAULT' in body)
    ck("  the W1C mask must cover bit7 (wr_frame[7])", 'wr_frame[7]' in body)
    ck("  a live fault blocks the clear (!any_hw_fault)", '!any_hw_fault' in body)
    ck("  4-byte alignment + implemented address checked",
       'wa_w[1:0]' in body and 'wa_w[14:6]' in body)
ck("it is declared BEFORE the capture block (no forward reference)",
   regs.index('wire clear_caught_req') < regs.index('hw_fault_caught <='))

print()
print("=== 3. the capture latch ===")
cap = re.search(r"always\s*@\(([^)]*)\)\s*begin\s*(.*?)\bend\b\s*end",
                regs[re.search(r'reg\s+hw_fault_caught\s*;', regs).start():], re.S)
ck("capture block found", cap is not None)
if cap:
    sens, body = cap.group(1), cap.group(2)
    ck("  sensitivity: posedge clk + posedge any_hw_fault + negedge reset_n",
       ('posedge clk' in sens) and ('posedge any_hw_fault' in sens) and
       ('negedge reset_n' in sens))
    ck("  clear_caught_req NOT in the sensitivity list (sync clear only)",
       'clear_caught_req' not in sens)
    set_at = body.find("any_hw_fault) hw_fault_caught <= 1'b1")
    clr_at = body.find("clear_caught_req) hw_fault_caught <= 1'b0")
    ck("  set branch BEFORE clear branch (set wins)", (0 <= set_at < clr_at))

print()
print("=== 4. visibility / status mapping still present ===")
ck("n_fault folds the capture into COMM_TO bit7",
   re.search(r'hw_fault_caught\s*\?\s*11\'h080', regs) is not None)
ck("W1C masks live faults out: `~(w1c_f & ~hw_fault)`",
   re.search(r'~\s*\(\s*w1c_f\s*&\s*~hw_fault\s*\)', regs) is not None)
fv = regs[regs.index('assign fault_vis_o'):]
fv = fv[:fv.find(';')]
ck("fault_vis_o still includes the capture", "11'h080" in fv)
ck("hw_blank still has six independent locks",
   all(t in regs for t in ('blank_r', '(!en)', 'any_hw_fault',
                           'hw_fault_caught', '(!disp_armed)', 'disp_fault')))

print()
print("=== 5. L1 TB wiring (reviewer requirement D.7) ===")
ck("`.fault_n (` explicitly connected in the L1 TB", '.fault_n (' in l1tb)
ck("fault_n is driven as a reg with pull-up default 1", "reg         fault_n" in l1tb
   or re.search(r'reg\s+fault_n\s*=\s*1\'b1', l1tb) is not None)
ck("both observation ports connected too",
   '.disp_armed_o (' in l1tb and '.hw_fault_caught_o (' in l1tb)
ck("a gated clock exists for the dead-clock test", 'clk_en' in l1tb)
ck("the runner uses the L1 top", 'tcon_t6a_l1_tb' in strip_comments(read(RUNNER)))

print()
print("=== 6. negative controls (each must FAIL on a doctored copy) ===")


def doctor(text, old, new):
    return text.replace(old, new, 1)


# NC-1: reintroduce the registered pulse exactly as rev3 had it
d1 = regs.replace("""        else if (clear_caught_req) hw_fault_caught <= 1'b0;""",
                  """        else if (clr_fault)    hw_fault_caught <= 1'b0;""", 1)
d1 = d1.replace("""    wire clear_caught_req = wr_cap_o &&""",
                """    reg  clr_fault;   // rev3 defect
    wire clear_caught_req = wr_cap_o &&""", 1)
d1 = d1.replace("""            // ---- 5. capture-latch clear -----------------------------------
""",
                """            // ---- 5. capture-latch clear -----------------------------------
            clr_fault <= 1'b0;
            if (wr_cap_o && (wa[5:2] == A_FAULT) && w1c_f[7] && !any_hw_fault)
                clr_fault <= 1'b1;
""", 1)
ck("NC-1 reintroduce the registered clear    -> the no-clr_fault check fails",
   'clr_fault' in strip_comments(d1))

# NC-2: move the clear into the sensitivity list (async clear)
d2 = regs.replace("always @(posedge clk or posedge any_hw_fault or negedge reset_n) begin\n"
                  "        if (!reset_n)          hw_fault_caught <= 1'b0;",
                  "always @(posedge clk or posedge any_hw_fault or negedge reset_n or "
                  "negedge clear_caught_req) begin\n"
                  "        if (!reset_n)          hw_fault_caught <= 1'b0;", 1)
ck("NC-2 make the clear asynchronous          -> the sensitivity check fails",
   'negedge clear_caught_req' in d2)

# NC-3: drop the live-fault guard
d3 = re.sub(r"(wire\s+clear_caught_req\s*=[\s\S]*?wr_frame\[7\]\s*&&\s*)!any_hw_fault",
            r"\g<1>1'b1", regs, count=1)
ck("NC-3 drop !any_hw_fault                   -> the guard check fails",
   '!any_hw_fault' not in re.search(r'wire\s+clear_caught_req\s*=([^;]+);', d3).group(1))

# NC-4: drop the caught->bit7 visibility mapping
d4 = regs.replace("hw_fault_caught ? 11'h080 : 11'd0", "11'd0")
ck("NC-4 drop the caught->bit7 mapping        -> the visibility check fails",
   re.search(r'hw_fault_caught\s*\?\s*11\'h080', d4) is None)

# NC-5: unconnected fault_n in the L1 TB
d5 = l1tb.replace('.status_in (status_in), .hw_fault (hw_fault), .fault_n (fault_n),',
                  '.status_in (status_in), .hw_fault (hw_fault),', 1)
ck("NC-5 unplug .fault_n                      -> the wiring check fails",
   '.fault_n (' not in d5)

print()
print("=== 7. interfaces frozen ===")
ck("spi_frame untouched by this round", "USE_DIN_VALID" not in frame)
ck("tcon_spi_top still exposes disp_armed_o / hw_fault_caught_o",
   'disp_armed_o' in top and 'hw_fault_caught_o' in top)
ck("tcon_spi_top folds the real FAULT_n pin into hw_fault[7]",
   re.search(r'hw_fault_i\s*=\s*hw_fault\s*\|\s*\(\s*fault_n\s*\?\s*11\'d0\s*:\s*11\'h080\s*\)', top)
   is not None)

print()
if fails:
    print("GATES_FAILED=%d" % len(fails))
    for f in fails:
        print("  -", f)
    print("RESULT=FAIL")
    sys.exit(1)
print("GATES_FAILED=0")
print("RESULT=PASS  (structure + 5 negative controls, comments stripped first)")
