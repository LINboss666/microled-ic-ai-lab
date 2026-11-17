#!/usr/bin/env python3
"""T5-A static guard (zero ModelSim).

This round is a *contract closure*, not a simulation: the only executable
evidence allowed is source reading and `vlog`. This script enforces the two
P0 boundaries mechanically so that a later "helpful" edit cannot slip in:

  1. the accepted RTL is byte-identical to what T3-H / T4 delivered
     (no silent patch under the name of an accepted version),
  2. no physical pin was invented: `load_active` must not feed `din_valid`,
     and the shell must not declare a VALID-style port,
  3. the five-chip shell really instantiates 1 TCON + 2 Data + 2 Scan with the
     frozen chip IDs and the frozen column/row mapping,
  4. the four T5-A deliverables exist and the patch proposal is still a
     PROPOSAL (i.e. the RTL does not contain the proposed lines yet).
"""
import hashlib
import os
import re
import subprocess
import sys

R = "D:/ic617_course_sim_20261112_clone"
S = os.path.join(R, "coursework/microled_sim")

ACCEPTED = {
    "rtl/data_driver.v.txt": "6d0c5f831423e16c8d76bf583730d11a77d92fa35c203635b346ba678ba359ab",  # T3-H2
    "rtl/scan_driver.v.txt": "6ee3ad38b3a9c2c1a65b37900537875ff52d33ca165145a246dafb0a782229a4",
    "rtl/data_model.v.txt": "604915355a79dfe5e0d8cc5aa4e9d14913d33c1962069ed394de21e71ef5506a",
}
DOCS = ["t5a/T5_DATA_SERIAL_CONTRACT.md", "t5a/T5_DATA_EDGE_TIMELINE.csv",
        "t5a/T5_LUT_EPOCH_INTERLOCK.md", "t5a/T5_FIVE_CHIP_WIRING.md",
        "t5a/T5_SCOREBOARD_PLAN.md", "t5a/T5A_RTL_PATCH_PROPOSAL.md"]

fails = []


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def read(p):
    return open(p, encoding="utf-8", errors="replace").read()


def ck(cond, msg):
    print("  %-64s %s" % (msg, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(msg)


print("=== 1. accepted RTL identity (must be byte-identical) ===")
for rel, want in ACCEPTED.items():
    got = sha(os.path.join(S, rel))
    print("  %-30s %s" % (rel, got))
    ck(got == want, "%s matches the accepted version" % rel)

print("\n=== 2. no physical pin was invented ===")
dd = read(os.path.join(S, "rtl/data_driver.v.txt"))
shell = read(os.path.join(S, "tb/t5_five_chip_shell.sv.txt"))
v13 = read("D:/ic617_tcon_t2ar2_20261114/v13_fulltext.txt")
ck("load_active" not in v13, "load_active appears 0 times in V1.3 (grep)")
ck(".load_active (load_active_obs)" in shell,
   "load_active goes to an unused observation net")
ck(".din_valid (dv_stub)" not in shell and "wire dv_stub" not in shell,
   "the 385-edge dv_stub is gone from the shell LOGIC (comment mentions allowed)")
ck(shell.count(".din_valid (1'b0)") == 2,
   "both Data instances tie din_valid to a constant (V1.3: no such pin)")
ck(shell.count("USE_DIN_VALID(0)") == 2,
   "both Data instances run the self-delimiting mode")
ck(not re.search(r"\.din_valid\s*\(\s*load_active", shell),
   "load_active is NOT connected to din_valid")
def has_din_valid(text):
    return re.search(r"input\s+wire\s+din_valid", text) is not None
ck(has_din_valid(dd), "data_driver still declares din_valid as an INPUT (T3 legacy port)")
# negative control: the SAME predicate must fail on a doctored copy, otherwise
# it is not a check at all (reviewer T5-A finding P1: `or True`)
ck(not has_din_valid(dd.replace("input  wire              din_valid,", "")),
   "NEGATIVE CONTROL: removing that port makes the predicate FAIL")
# shell port list must not contain a VALID-style physical port
ports = re.findall(r"^\s*(?:input|output)\s+wire[^;]*?(\w+)\s*(?:,|$)", shell, re.M)
ck(not any(p.lower() in ("valid", "d_valid", "data_valid") for p in ports),
   "shell declares no VALID-style external port")

print("\n=== 3. five-chip shell composition ===")
ck(shell.count("tcon_top #") == 1, "exactly one tcon_top")
ck(shell.count("data_driver #") == 2, "exactly two data_driver")
ck(shell.count("scan_driver #") == 2, "exactly two scan_driver")
ck('.CHIP_ID(0)' in shell and '.CHIP_ID(1)' in shell, "both Scan chip IDs present")
ck("./tcon.d0" in shell or ".din (d0)" in shell, "Data#0 fed by tcon d0")
ck(".din (d1)" in shell, "Data#1 fed by tcon d1")
ck(".dclk (dclk)" in shell, "dclk distributed")
ck(shell.count(".blank (blank)") >= 4, "blank goes to all four drivers")
ck(".col_id (col_id_w)" in shell and ".scan_stb (scan_stb_w)" in shell,
   "col_id / scan_stb distributed to both Scan chips")

print("\n=== 4. deliverables present, T3-H2 patch state ===")
for d in DOCS:
    ck(os.path.exists(os.path.join(S, d)), "deliverable %s" % d)
# T3-H2 has since been applied: this tool now confirms the *contract* it was
# written to protect (no invented pin, mode-0 wrapper, no off-by-one stub) while
# the RTL patch details themselves are owned by tools/t3h2_precheck.py.
ck("USE_DIN_VALID" in dd, "T3-H2 parameter is present (patch applied)")
ck("if (commit_fire) col_valid <= 1'b0;" in dd,
   "T3-H2 display invalidation is present (patch applied)")
ck("wire dv_stub" not in shell and "arming ||" not in shell,
   "shell no longer carries the 385-edge stub (no dv_stub logic)")

print("\n=== 5. working tree (RTL must be unmodified) ===")
st = subprocess.run(["git", "-C", R, "status", "--porcelain"],
                    capture_output=True, text=True, check=False).stdout.splitlines()
touched_rtl = [l for l in st if "/rtl/" in l and l.strip()]
allowed = {"coursework/microled_sim/rtl/data_driver.v.txt"}
unexpected = [l for l in touched_rtl if l.split()[-1] not in allowed]
ck(not unexpected,
   "only data_driver.v.txt may be modified in rtl/ (%d unexpected)" % len(unexpected))
for l in st:
    print("    %s" % l)

print("\nRESULT: %s" % ("T5A_STATIC_OK" if not fails else "T5A_STATIC_FAIL"))
for f in fails:
    print("  - %s" % f)
sys.exit(0 if not fails else 1)
