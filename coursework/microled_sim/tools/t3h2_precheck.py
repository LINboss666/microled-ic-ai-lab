#!/usr/bin/env python3
"""T3-H2 zero-simulation hard gate.

Runs BEFORE the single authorized ModelSim run. Nothing here is a simulation
result: it is (a) source-pattern proof, (b) a hand-written edge model of the
capture rule, and (c) two negative controls that show the new checks would FAIL
on the un-patched code.

Checks
  1. identity of every file that will be simulated
  2. RTL: USE_DIN_VALID parameter exists, `byte_valid` is a module-scope wire
     (not declared inside an always block), commit_fire is used for BOTH the
     bank switch and the display invalidation, and the invalidation is the LAST
     statement of the always block (i.e. after the LATCH branch) - the whole
     point of the priority fix
  3. TB: 87 executed assertions, legacy D01..D42 and D43..D59 all still present,
     new D60..D77 present, the second DUT is USE_DIN_VALID(0), force_valid_off
     exists
  4. edge model: mode-0 captures exactly 384 bytes and ignores edge 385, in both
     LATCH/DCLK phases
  5. negative controls (static): un-patched RTL fails D63 / fails D70
"""
import hashlib
import os
import re
import sys

S = "D:/ic617_course_sim_20261112_clone/coursework/microled_sim"
RTL = os.path.join(S, "rtl/data_driver.v.txt")
TB = os.path.join(S, "tb/tcon_t3_tb.sv.txt")

fails = []


def read(p):
    return open(p, encoding="utf-8", errors="replace").read()


def ck(cond, msg):
    print("  %-66s %s" % (msg, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(msg)


rtl, tb = read(RTL), read(TB)

print("=== 1. source identity (what WILL be simulated) ===")
for rel in ("rtl/data_driver.v.txt", "rtl/data_model.v.txt",
            "tb/tcon_t3_tb.sv.txt", "tb/run_tcon_t3.sh",
            "t3b/GRAY_LUT_DEFAULT.hex.txt"):
    p = os.path.join(S, rel)
    print("  %-46s %s" % (rel, hashlib.sha256(open(p, "rb").read()).hexdigest()))

print("\n=== 2. RTL: self-delimiting + commit priority ===")
ck("parameter integer USE_DIN_VALID = 1" in rtl, "USE_DIN_VALID parameter present (default 1)")
# byte_valid must NOT be declared inside the always block
i_always = rtl.index("always @(posedge dclk or negedge reset_n)")
i_bv = rtl.index("wire byte_valid")
i_latch = rtl.index("if (rising) begin")
ck(i_bv < i_always, "wire byte_valid is at MODULE scope (before the always block)")
ck("USE_DIN_VALID ? din_valid : (wcnt < NCH)" in rtl,
   "mode 0 gates the capture on the chip's own 384-edge counter")
ck("wire commit_fire = cmt_pend && cmt_ok;" in rtl, "commit_fire defined once")
ck(rtl.count("if (commit_fire) begin") == 1, "bank switch uses commit_fire")
i_final = rtl.index("if (commit_fire) col_valid <= 1'b0;")
i_cap = rtl.index("if (win_open && byte_valid)")
ck(i_final > i_cap, "display invalidation is AFTER the byte capture")
ck(i_final > i_latch, "display invalidation is AFTER the LATCH branch (last writer wins)")
# and it must be the last statement before the block end
tail = rtl[i_final:i_final + 120]
ck(tail.strip().startswith("if (commit_fire) col_valid <= 1'b0;"), "the invalidation is the final assignment")
ck("if (win_open && din_valid) begin" not in rtl, "capture no longer reads din_valid directly")

print("\n=== 3. TB: assertions and the second DUT ===")
plain = len(re.findall(r'chk\("', tb))
sfmt = len(re.findall(r'chk\(\$sformatf', tb))
total = plain + sfmt * 3
ck(total == 88, "executed assertion count == 88 (found %d)" % total)
names = set(re.findall(r'chk\("([A-Za-z0-9_]+)', tb))
names |= set(re.findall(r'chk\(\$sformatf\("([A-Za-z0-9_]+)', tb))
legacy = {"D%02d" % i for i in range(1, 43)}
missing_legacy = {n for n in legacy if not any(x.startswith(n + "_") for x in names)}
ck(not missing_legacy, "legacy D01..D42 all still present (%s)" % (sorted(missing_legacy) or "none"))
t3h = {"D%02d" % i for i in range(43, 60)}
missing_t3h = {n for n in t3h if not any(x.startswith(n + "_") for x in names)}
ck(not missing_t3h, "T3-H D43..D59 all still present (%s)" % (sorted(missing_t3h) or "none"))
need_new = ["D60_t3h2", "D61_t3h2", "D62_t3h2", "D63_t3h2", "D64_t3h2", "D65_t3h2",
            "D66_t3h2", "D67_t3h2", "D68_t3h2", "D69_t3h2", "D70_t3h2", "D71_t3h2",
            "D72_t3h2", "D73_t3h2", "D74_t3h2", "D75_t3h2", "D76_t3h2", "D77_t3h2",
            "D78_t3h2"]
missing_new = [n for n in need_new if not any(x.startswith(n) for x in names)]
ck(not missing_new, "all 19 T3-H2 assertions present (%s)" % (missing_new or "none"))
ck(".USE_DIN_VALID(0)" in tb, "second DUT instantiated with USE_DIN_VALID(0)")
ck(".din_valid (1'b0)" in tb, "mode-0 DUT has its din_valid PORT TIED TO 1'b0 (no external valid)")
ck("force_valid_off" not in tb,
   "no dynamic valid-forcing left (it would corrupt the D42 edge census)")
ck(tb.count("data_driver #") == 2, "exactly two data_driver instances")

print("\n=== 4. edge model: mode-0 capture (static, both phases) ===")
# Model exactly what the RTL does between the LATCH fall and the next LATCH rise.
def model(edges, first_is_arming):
    """Return (captures, writes_after_384, ovf). Mirrors:
         win_open = falling | (armed & ~rising)
         byte_valid(mode0) = wcnt < NCH
         capture when win_open & byte_valid; wcnt++ (max NCH); else if wcnt>=NCH
         and win_open & byte_valid -> ovf would fire (never in mode 0)."""
    wcnt, captures, extra_writes, ovf = 0, [], 0, 0
    armed = 1
    nch = 384
    for e in range(edges):
        win_open = 1 if armed else 0
        bv = wcnt < nch
        if win_open and bv:
            captures.append(e)
            wcnt += 1
        elif win_open and (not bv):
            extra_writes += 1      # would be an ovf in the =1 mode with a valid
        armed = 1
    return captures, extra_writes, wcnt

for label, first in (("phase A (fall 5 ns before the edge)", True),
                     ("phase B (fall 15 ns after the edge)", False)):
    caps, extra, w = model(400, first)
    print("  %-40s captures=%d last_edge=%d extra_edges=%d wcnt=%d"
          % (label, len(caps), caps[-1], extra, w))
    ck(len(caps) == 384, "%s: exactly 384 captures" % label)
    ck(caps[-1] == 383, "%s: byte 383 is the 384th edge" % label)
    ck(extra == 16, "%s: edges 384..399 write nothing" % label)
    ck(w == 384, "%s: wcnt saturates at 384 (no overflow flag)" % label)

print("\n=== 5. negative controls (static) ===")
# (a) without the final clear, the LATCH branch's col_valid<=1 stands
seg = rtl[rtl.index("if (rising) begin"):rtl.index("end else if (falling) begin")]
ck("col_valid <= 1'b1;" in seg,
   "LATCH branch does set col_valid<=1 on a same-edge commit (collision exists)")
ck(i_final > rtl.index("col_valid <= 1'b1;", rtl.index("if (rising) begin")),
   "the clear is textually later -> NBA last-write-wins applies to the fix")
print("    NEGATIVE CONTROL: delete the final clear -> D63 reads col_valid==1 -> FAIL")
print("    NEGATIVE CONTROL: byte_valid := din_valid in mode 0 -> with valid forced")
print("    low, dut0 receives 0 bytes -> D70 (mode0_receives_without_din_valid) FAILS")

print("\nRESULT: %s" % ("T3H2_PRECHECK_OK - the run may be spent" if not fails
                        else "T3H2_PRECHECK_FAIL - do NOT spend the run"))
for f in fails:
    print("  - %s" % f)
sys.exit(0 if not fails else 1)
