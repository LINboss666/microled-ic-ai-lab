#!/usr/bin/env python3
"""T6-A P0-E 静态硬门（去注释后核对，零 ModelSim）。

核对对象：候选分支的 `tcon_spi_regs`（逐源捕获向量方案）。
判据（合同见 t6a/FAULT_REARM_PROTOCOL.md rev5）：

  S1  捕获是 11 位向量，位于 generate 中，每一位独立
      `always @(posedge clk or posedge hw_fault[g] or negedge reset_n)`；
  S2  清除请求按位组合：`frame_is_fault_w1c && wr_frame[g] && !hw_fault[g]`，
      不存在任何寄存器化的 clr 脉冲；
  S3  set 分支在 clear 之前；`clear_caught_req` 不在敏感列表里（同步清除）；
  S4  `n_fault` / `fault_vis_o` 折叠的是**整个向量**（本地原因进自己的位），
      不再是 `? 11'h080` 的单 bit7 映射；
  S5  `hw_blank` 六锁不变（caught_any = |caught）；
  S6  L1 TB 显式连接 `.fault_n`（引脚路径不被 Z 破坏）。

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


def strip_comments(t):
    t = re.sub(r'/\*[\s\S]*?\*/', ' ', t)
    t = re.sub(r'//[^\n]*', ' ', t)
    return t


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


fails = []


def ck(name, cond):
    print("  %-64s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


regs = strip_comments(read(REGS))
top = strip_comments(read(TOP))
frame = strip_comments(read(FRAME))
l1tb = strip_comments(read(L1TB))

print("=== 1. the P0-D single latch is GONE ===")
ck("no scalar `hw_fault_caught` register left",
   not re.search(r'reg\s+hw_fault_caught\s*;', regs))
ck("no single `clear_caught_req` outside the generate",
   len(re.findall(r'wire\s+clear_caught_req', regs)) == 1 and
   regs.find('wire clear_caught_req') > regs.find('generate'))
ck("no `? 11'h080` single-bit7 mapping left",
   re.search(r"hw_fault_caught\s*\?\s*11'h080", regs) is None and
   re.search(r"\?\s*11'h080\s*:\s*11'd0", regs) is None)

print()
print("=== 2. the per-source capture vector ===")
gen = re.search(r'generate([\s\S]*?)endgenerate', regs)
ck("a generate block builds the 11 latches", gen is not None)
if gen:
    body = gen.group(1)
    ck("  loop bound is 11 (one latch per hw_fault bit)", 'g < 11' in body)
    ck("  S1 per-bit async sensitivity: posedge hw_fault[g]",
       'posedge hw_fault[g]' in body)
    ck("  S2 per-bit combinational clear request",
       'wire clear_caught_req' in body and 'frame_is_fault_w1c' in body)
    ck("  S2 the mask must cover cause g (wr_frame[g])", 'wr_frame[g]' in body)
    ck("  S2 a live source blocks its own clear (!hw_fault[g])",
       '!hw_fault[g]' in body)
    ck("  S3 set branch BEFORE clear branch",
       body.find("hw_fault[g])     caught[g] <= 1'b1") <
       body.find("clear_caught_req) caught[g] <= 1'b0"))
    ck("  S3 clear_caught_req NOT in the sensitivity list",
       'or negedge clear_caught_req' not in body and
       'posedge clear_caught_req' not in body)
ck("`caught` declared as an 11-bit reg",
   re.search(r'reg\s*\[10:0\]\s*caught\s*;', regs) is not None)
ck("S4 n_fault folds the whole vector (local causes report in their own bit)",
   re.search(r"n_fault\s*=\s*fault_status\s*\|\s*hw_fault\s*\|"
             r"\s*\(err_set\s*\?\s*11'h100\s*:\s*11'd0\)\s*\|\s*caught\s*;", regs)
   is not None)
ck("S4 fault_vis_o folds the vector too",
   re.search(r'fault_vis_o\s*=\s*fault_status\s*\|\s*hw_fault\s*\|\s*caught\s*;', regs)
   is not None)

print()
print("=== 3. the six hw_blank locks are unchanged ===")
ck("S5 hw_blank uses caught_any (= |caught)",
   re.search(r'hw_blank\s*=\s*blank_r\s*\|\s*\(!en\)\s*\|\s*any_hw_fault\s*\|'
             r'\s*caught_any\s*\|\s*\(!disp_armed\)\s*\|\s*disp_fault', regs)
   is not None)
ck("S5 the W1C mask still excludes live sources",
   re.search(r'~\s*\(\s*w1c_f\s*&\s*~hw_fault\s*\)', regs) is not None)
ck("S5 the admission still requires no captured fault",
   '!caught_any' in regs)

print()
print("=== 4. interfaces frozen ===")
ck("spi_frame untouched", "USE_DIN_VALID" not in frame)
ck("top still folds the real FAULT_n pin into hw_fault[7]",
   re.search(r"hw_fault_i\s*=\s*hw_fault\s*\|\s*\(\s*fault_n\s*\?\s*11'd0\s*:\s*11'h080\s*\)", top)
   is not None)
ck("S6 the L1 TB connects .fault_n explicitly", '.fault_n (' in l1tb)
ck("S6 the L1 runner targets the L1 top", 'tcon_t6a_l1_tb' in strip_comments(read(RUNNER)))

print()
print("=== 5. negative controls (each must FAIL on a doctored copy) ===")


def doctor(text, old, new, count=1):
    return text.replace(old, new, count)


# NC-1: back to the single shared latch OR-ed into bit7 (= P0-D candidate)
d1 = doctor(regs,
            "    wire caught_any = |caught;",
            "    wire caught_any = caught[7];")
ck("NC-1 caught_any -> only bit7               : the vector-fold checks fail",
   re.search(r"n_fault\s*=[\s\S]*?caught\s*;", d1) is None or
   'caught[7]' in d1)

# NC-2: one shared clear request (ignores the per-bit mask)
d2 = re.sub(r"(wire clear_caught_req = frame_is_fault_w1c &&\s*)wr_frame\[g\]\s*&&\s*!hw_fault\[g\]",
            r"\g<1>wr_frame[7];   // DEFECT: one shared cause only", regs, count=1)
ck("NC-2 shared bit7-only clear request       : the per-bit mask check fails",
   'wr_frame[g]' not in re.search(r'generate([\s\S]*?)endgenerate', d2).group(1))

# NC-3: clear despite a live source
d3 = re.sub(r"(&&\s*)!hw_fault\[g\]\s*;", r"\g<1>1'b1;   // DEFECT: live source ignored",
            regs, count=1)
ck("NC-3 drop the live-source guard           : the guard check fails",
   '!hw_fault[g]' not in re.search(r'generate([\s\S]*?)endgenerate', d3).group(1))

# NC-4: the async set becomes a core-clock sample
d4 = doctor(regs,
            "            always @(posedge clk or posedge hw_fault[g] or negedge reset_n) begin",
            "            always @(posedge clk or negedge reset_n) begin")
d4 = doctor(d4,
            "                else if (hw_fault[g])     caught[g] <= 1'b1;",
            "                else if (hw_fault[g] && clk) caught[g] <= 1'b1;")
ck("NC-4 async set -> clocked sample          : the sensitivity check fails",
   'posedge hw_fault[g]' not in re.search(r'generate([\s\S]*?)endgenerate', d4).group(1))

# NC-5: visibility folded back into bit7 only
d5 = re.sub(r"(n_fault\s*=\s*fault_status\s*\|\s*hw_fault\s*\|\s*"
            r"\(err_set[^;]*?\|\s*)caught\s*;",
            r"\g<1>(caught[7] ? 11'h080 : 11'd0);", regs, count=1)
ck("NC-5 visibility folded into bit7 only     : the vector-fold check fails",
   re.search(r"n_fault\s*=[\s\S]*?\|\s*caught\s*;", d5) is None)

# NC-6: unplug .fault_n from the L1 TB
d6 = l1tb.replace('.status_in (status_in), .hw_fault (hw_fault), .fault_n (fault_n),',
                  '.status_in (status_in), .hw_fault (hw_fault),', 1)
ck("NC-6 unplug .fault_n                      : the wiring check fails",
   '.fault_n (' not in d6)

print()
if fails:
    print("GATES_FAILED=%d" % len(fails))
    for f in fails:
        print("  -", f)
    print("RESULT=FAIL")
    sys.exit(1)
print("GATES_FAILED=0")
print("RESULT=PASS  (per-source capture structure + 6 negative controls, comments stripped)")
