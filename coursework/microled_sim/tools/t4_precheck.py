#!/usr/bin/env python3
"""T4 zero-simulation pre-check.

Runs BEFORE the single authorized ModelSim run. Everything here is static: no
vsim is invoked, so a failure costs nothing and a success proves nothing about
behaviour, only that the sources and the script satisfy the frozen contract.

Checks
  1. source identity (SHA-256 of what WILL be simulated)
  2. RTL: the latch really is on posedge scan_stb, there is NO reference clock
     in the RTL, no delays, no functional initial, no file I/O, 512-bit output
  3. TB : 42 unique assertion names, 1024-address sweep, popcount one-hot rule,
     two DUT instances + two INDEPENDENT pin-level oracles, census printout,
     no hierarchical peeking into the DUT
  4. runner: FLOOR=42, MIN_ASSERTS external override, floor can never be lowered
  5. repo: no TCOn/T3 source was modified in this round
"""
import hashlib
import os
import re
import subprocess
import sys

R = "D:/ic617_course_sim_20261112_clone"
S = os.path.join(R, "coursework/microled_sim")

RTL = os.path.join(S, "rtl/scan_driver.v.txt")
EXP = os.path.join(S, "rtl/scan_exp.v.txt")
TB = os.path.join(S, "tb/tcon_t4_tb.sv.txt")
RUN = os.path.join(S, "tb/run_tcon_t4.sh")

fails = []


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def read(p):
    return open(p, "r", encoding="utf-8", errors="replace").read()


def ck(cond, msg):
    print("  %-62s %s" % (msg, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(msg)


print("=== 1. source SHA-256 (what WILL be simulated) ===")
for p in (RTL, EXP, TB, RUN):
    print("  %-52s %s" % (os.path.basename(p), sha(p)))

rtl, exp, tb, run = read(RTL), read(EXP), read(TB), read(RUN)

print("\n=== 2. scan_driver RTL contract ===")
ck(bool(re.search(r"always\s*@\s*\(\s*posedge\s+scan_stb", rtl)),
   "address latch on real posedge scan_stb")
ck(not re.search(r"(posedge|negedge)\s+clk\b", rtl),
   "NO reference clock in the RTL (scan_stb is the clock)")
ck(bool(re.search(r"output\s+wire\s*\[\s*511\s*:\s*0\s*\]\s+col_a", rtl)),
   "512-bit one-hot output col_a[511:0]")
ck("parameter integer CHIP_ID" in rtl, "CHIP_ID parameter present")
ck("col_id[9:1]" in rtl, "LOCAL_INDEX = col_id[9:1]")
ck("col_id[0] == MY_DIE" in rtl, "DIE_SEL = col_id[0] compared with CHIP_ID")
ck(bool(re.search(r"gate_ok\s*=.*reset_n.*armed.*!blank.*fault_n", rtl)),
   "gate = reset_n && armed && !blank && fault_n (hardware priority)")
ck(bool(re.search(r"512'd1\s*<<\s*lat_chan", rtl)), "one-hot decode from lat_chan")
ck("initial" not in rtl, "no functional initial block")
ck(not re.search(r"#\s*\d", rtl), "no #delay in the RTL")
ck(not re.search(r"\$(display|readmem|fopen|dump\w*)", rtl), "no file/console I/O in the RTL")
ck("inout" not in rtl, "no inout port")

print("\n=== 3. testbench contract ===")
names = re.findall(r'chk\("([A-Za-z0-9_]+)"', tb)
ck(len(names) == 42, "42 assertion sites (found %d)" % len(names))
ck(len(set(names)) == len(names), "all assertion names unique")
ck(sum(1 for n in names if n.startswith("D")) == 42, "all names carry a D-id")
for want in ("D12_sweep_1024_addresses_checked", "D16_sweep_global_always_onehot",
             "D38_response_not_clock_sampled", "D42_monitor_samples_not_vacuous"):
    ck(want in names, "required assertion %s" % want)
ck("addr < 1024" in tb, "1024-address sweep loop present")
ck("n_addr_checked == 1024" in tb, "sweep count asserted == 1024 (non-vacuous)")
ck("function integer popc" in tb, "independent popcount implemented in the TB")
ck("512'd1 << half" in tb, "per-address expectation computed from the loop variable")
ck(tb.count("scan_driver #") == 2, "exactly two DUT instances")
ck("CHIP_ID(0)" in tb and "CHIP_ID(1)" in tb, "both chip IDs instantiated")
ck(tb.count("scan_exp #") == 2, "two independent pin-level oracles instantiated")
ck("scan_pin_mon pm" in tb, "accepted pin monitor reused")
ck("COURSE_T4_STROBES" in tb and "expected=" in tb and "observed=" in tb
   and "checked=" in tb and "zero_or_multi_hot=" in tb and "cov_chip0=" in tb,
   "census printout (expected/observed/checked/zero_or_multi_hot/coverage)")
ck("dut0." not in tb and "dut1." not in tb, "no hierarchical peek into the DUTs")
ck("$fatal" in tb and "$finish" in tb, "self-checking fail-fast + finish")
ck("$dumpoff" in tb and "$dumpon" in tb, "VCD is windowed (small, reviewable)")

print("\n=== 4. runner identity ===")
ck("FLOOR=42" in run, "FLOOR=42")
ck('MIN_ASSERTS="${MIN_ASSERTS:-$FLOOR}"' in run, "MIN_ASSERTS external override kept")
ck("BAD_MIN_ASSERTS_BELOW_FLOOR" in run, "floor cannot be lowered")
ck("scan_exp.v" in run and "scan_pin_mon.v" in run, "oracle + monitor are compiled")
ck("timeout" in run, "wall-clock gate present")

print("\n=== 5. untouched modules (this round must not edit TCON/T3) ===")
try:
    changed = subprocess.run(
        ["git", "-C", R, "status", "--porcelain"],
        capture_output=True, text=True, check=False).stdout.splitlines()
except Exception as exc:                                   # pragma: no cover
    changed = []
    print("  git status unavailable: %s" % exc)
touched = [l for l in changed if l.strip()]
bad = [l for l in touched
       if re.search(r"(data_driver|data_model|tcon_|tcon_t3|tcon_t1|tcon_t2|course_)", l)
       and "t4" not in l.lower()]
ck(not bad, "no TCON/T3/Data source modified (%d paths changed)" % len(touched))
for l in touched:
    print("    %s" % l)

print("\nRESULT: %s" % ("PRECHECK_OK - the run may be spent"
                       if not fails else "PRECHECK_FAIL - do NOT spend a run"))
for f in fails:
    print("  - %s" % f)
sys.exit(0 if not fails else 1)
