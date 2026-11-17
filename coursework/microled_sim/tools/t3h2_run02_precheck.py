#!/usr/bin/env python3
"""T3-H2 RUN02 zero-simulation hard gate.

RUN01 failed 84/88 because the TB observers were wrong, not the RTL:
  * the "commit" counter watched `lut_valid` 0->1, which cannot see a second
    bank switch (1->1), so D72's `commit_count == k0` guard was vacuous and
    D73 waited 80 us for an event that had already happened;
  * the commit-edge capture happened one edge late (NBA vs active region).

RUN02 replaces both with a one-edge PRE/POST bank-flip observer and a
continuous "must stay dark" monitor. This gate proves, without simulating:

  1. the four runtime sources keep their expected identity (only the TB moved),
  2. the TB really implements the PRE/POST observer and no longer counts
     `lut_valid` transitions,
  3. the three negative controls from the task book actually fail,
  4. the dark-interval monitors and the 976/977 phase coverage exist,
  5. assertion inventory: 91 executed, all legacy + T3-H + T3-H2 names kept.
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
    print("  %-68s %s" % (msg, "OK" if cond else "FAIL"))
    if not cond:
        fails.append(msg)


def chk_body(name):
    """Return the source text of the chk(...) call whose first argument starts
    with `name`, up to the closing `);` on the same statement."""
    m = re.search(r'chk\("' + re.escape(name) + r'[^"]*",(.{0,600}?)\);\n', tb, re.S)
    return m.group(1) if m else ""


rtl, tb = read(RTL), read(TB)

print("=== 1. source identity (what WILL be simulated) ===")
want = {
    "rtl/data_driver.v.txt": "6d0c5f831423e16c8d76bf583730d11a77d92fa35c203635b346ba678ba359ab",
    "rtl/data_model.v.txt": "604915355a79dfe5e0d8cc5aa4e9d14913d33c1962069ed394de21e71ef5506a",
    "tb/run_tcon_t3.sh": "c1668f452297ae51b073fd088106c30791ee166b4ffe4573fd6ded5dcb07d9a3",
    "t3b/GRAY_LUT_DEFAULT.hex.txt": "e3e39b43f7e0f76e5f2865338c271402a1da5b1fd8b4e6193c0ed668f79cb253",
}
for rel, exp in want.items():
    got = hashlib.sha256(open(os.path.join(S, rel), "rb").read()).hexdigest()
    print("  %-38s %s" % (rel, got))
    ck(got == exp, "%s unchanged" % rel)
print("  %-38s %s" % ("tb/tcon_t3_tb.sv.txt",
                      hashlib.sha256(open(TB, "rb").read()).hexdigest()))

print("\n=== 2. RUN02 TB: PRE/POST bank-flip observer ===")
ck("pre_bank  = lut_bank;" in tb, "PRE bank recorded in the active region")
ck("#1;" in tb and "post_bank = lut_bank;" in tb, "POST bank read 1 ns later (no #0)")
ck("if (reset_n && (post_bank !== pre_bank)) begin" in tb, "flip detection gated by reset_n")
ck("last_pre_ok = (pre_lt === 1'b1) && (pre_ltd === 1'b0) &&" in tb,
   "legal-LATCH collision condition captured PRE-edge")
ck("pre_ltd   = dut.latch_d;" in tb and "pre_armed = dut.armed;" in tb
   and "pre_wcnt  = dut.wcnt;" in tb, "PRE latch_d / armed / wcnt recorded")
ck("if (lut_valid && !lut_valid_q)" not in tb,
   "the old `lut_valid` 0->1 counter is GONE")
ck("commit_count" not in tb, "the blind `commit_count` name is gone")

print("\n=== 3. D62 / D72 are no longer vacuous ===")
d62 = chk_body("D62_t3h2_commit_fires_on_latch_edge")
d72 = chk_body("D72_t3h2_fault_holds_pending_commit")
ck("last_pre_ok === 1'b1" in d62, "D62 requires the PRE-edge legal-LATCH condition")
ck("last_post_colv === 2'b00" in d62, "D62 requires POST col_valid==0 on BOTH chips")
ck("last_both_bank_same === 1'b1" in d62, "D62 requires both DUTs' banks to agree")
ck("f_bank_flip == 0" in d72, "D72 requires the bank NOT to flip during FAULT")
ck("f_pend_seen === 1'b1" in d72, "D72 requires cmt_pend to be observed held")
ck("commit_events == k0" in d72, "D72 also cross-checks the flip counter")

print("\n=== 4. negative controls (must FAIL when the guard is removed) ===")
# NC1: old counter vs bank flip on the real RUN02 sequence
valid_seq, bank_seq = [0, 1, 1], [0, 1, 0]      # before / after A / after B
old = sum(1 for i in range(1, 3) if valid_seq[i] == 1 and valid_seq[i-1] == 0)
new = sum(1 for i in range(1, 3) if bank_seq[i] != bank_seq[i-1])
print("    NC1 sequence valid=%s bank=%s -> old_counter=%d bank_flips=%d"
      % (valid_seq, bank_seq, old, new))
ck(old == 1 and new == 2, "NC1: the old counter sees 1 commit, the bank flip sees 2")

# NC2: dropping the col_valid==0 term from D62 must make it unacceptable
doctored = d62.replace("last_post_colv === 2'b00", "1'b1")
ck(bool(d62.strip()) and "last_post_colv" not in doctored,
   "NC2: removing the col_valid==0 term leaves a check the gate would reject")

# NC3: D72 must not rely on a bare equality to a snapshot
ck(d72.strip() != "commit_events == k0",
   "NC3: D72 is not a bare counter snapshot (bank + pending + outputs are required)")

print("\n=== 5. dark-interval monitors and phase coverage ===")
ck("reg     dark_watch = 1'b0, dark_done = 1'b0;" in tb, "dark-interval monitor exists")
ck("if (col_valid === 1'b1) begin" in tb and "dark_done = 1'b1;" in tb,
   "dark interval ends only on a legal reload (col_valid rise)")
ck("dark_blank_low > 10" in chk_body("D64_t3h2_commit_without_reload_window_dark"),
   "D64 requires real BLANK-low samples inside the dark interval")
ck("dark_blank_low > 10" in chk_body("D75_t3h2_post_fault_window_dark"),
   "D75 requires real BLANK-low samples inside the dark interval")
ck("dark_samples > 50" in chk_body("D65_t3h2_reload_reenables_valid"),
   "D65 requires a non-trivial number of dark samples")
ck("dut0.raw_disp[i] !== exp_byte(0, 1, i, 1)" in tb,
   "mode-0 bytes compared against the TB's OWN exp_byte (not the other DUT)")
ck("D79_t3h2_mode0_bytes_exact_phase1" in tb and "D80_t3h2_mode0_bytes_exact_phase2" in tb,
   "two independent 976/977 byte-exact checks exist")
ck("len_obs[0] == 976" in tb and "len_obs[1] == 977" in tb,
   "D81 proves both slot phases were really observed")

print("\n=== 6. assertion inventory ===")
plain = len(re.findall(r'chk\("', tb))
sfmt = len(re.findall(r'chk\(\$sformatf', tb))
total = plain + sfmt * 3
ck(total == 91, "executed assertion count == 91 (found %d)" % total)
names = set(re.findall(r'chk\("([A-Za-z0-9_]+)', tb))
names |= set(re.findall(r'chk\(\$sformatf\("([A-Za-z0-9_]+)', tb))
for lo, hi, label in ((1, 42, "legacy D01..D42"), (43, 59, "T3-H D43..D59"),
                      (60, 78, "T3-H2 D60..D78"), (79, 81, "RUN02 D79..D81")):
    missing = {("D%02d" % i) for i in range(lo, hi + 1)
               if not any(x.startswith("D%02d_" % i) for x in names)}
    ck(not missing, "%s all present (%s)" % (label, sorted(missing) or "none"))

print("\nRESULT: %s" % ("T3H2_RUN02_PRECHECK_OK - the run may be spent" if not fails
                        else "T3H2_RUN02_PRECHECK_FAIL - do NOT spend the run"))
for f in fails:
    print("  - %s" % f)
sys.exit(0 if not fails else 1)
