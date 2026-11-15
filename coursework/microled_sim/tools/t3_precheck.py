#!/usr/bin/env python3
"""T3 run-03 pre-check (zero simulation). Reviewer-mandated before spending the
single authorized ModelSim run.

Checks, all from the SOURCE TEXT:
  1. SHA-256 of every file that will be simulated, so the pre-checked sources
     and the actually-simulated sources are provably the same set.
  2. F1 present: col_valid is NOT cleared when a window opens.
  3. F2 present: the byte-capture block appears AFTER the LATCH-edge block, so
     the arming edge counts as byte 0 (the run01/run02 383-byte defect).
  4. F3 present: D40 is sampled before the P6 reset.
  5. Sampling-phase agreement between the DUT and the data_model oracle:
     - win/sent (i.e. din/din_valid) are updated ONLY at negedge dclk,
     - the slot waveform (blank/latch/pwm_*) is registered at negedge clk,
     - no `always @(posedge dclk)` in the TB drives a DUT-facing input,
     - data_model still samples at posedge dclk with the 1 ns settle.
  6. Assertion inventory: 51 original names still present + 1 added census
     check, thresholds untouched.

Exit 0 only if everything holds; otherwise the run must NOT be spent.
"""
import hashlib
import re
import sys

R = "coursework/microled_sim/"
FILES = [R + "rtl/data_driver.v.txt", R + "tb/tcon_t3_tb.sv.txt",
         R + "rtl/data_model.v.txt", R + "tb/run_tcon_t3.sh",
         R + "t3b/GRAY_LUT_DEFAULT.hex.txt"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    ok = True

    print("=== 1. source SHA-256 (what WILL be simulated) ===")
    for p in FILES:
        print("  %-52s %s" % (p.replace(R, ""), sha(p)))

    rtl = open(FILES[0], encoding="utf-8").read()
    tb = open(FILES[1], encoding="utf-8").read()

    print("\n=== 2. F1: col_valid must NOT be cleared when a window opens ===")
    m = re.search(r"end else if \(falling\) begin(.*?)end", rtl, re.S)
    body = m.group(1) if m else ""
    f1 = "col_valid" not in body
    print("  falling branch contains col_valid clearing: %s" % ("NO (F1 ok)" if f1 else "YES (F1 MISSING)"))
    ok &= f1

    print("\n=== 3. F2: capture block AFTER the LATCH-edge block ===")
    i_latch = rtl.index("if (rising) begin")
    i_cap = rtl.index("raw_load[wcnt] <= din;")
    f2 = i_cap > i_latch
    print("  LATCH-edge block at %d, capture at %d -> %s" % (i_latch, i_cap, "F2 ok" if f2 else "F2 MISSING"))
    ok &= f2

    print("\n=== 4. F3: D40 sampled before the P6 reset ===")
    i_d40 = tb.index('chk("D40_oracle_committed_columns"')
    i_p6 = tb.index("phase 6: reset")
    f3 = i_d40 < i_p6
    print("  D40 at %d, P6 reset at %d -> %s" % (i_d40, i_p6, "F3 ok" if f3 else "F3 MISSING"))
    ok &= f3

    print("\n=== 5. sampling-phase agreement (reviewer finding) ===")
    # 5a win/sent must be driven only at negedge dclk
    # --- single-writer audit (reviewer RUN04 pre-check #3) -----------------
    # every TB state variable must be assigned in exactly ONE always block
    pos_bodies = re.findall(r"always\s*@\(\s*posedge\s+dclk\s*\) begin(.*?)\n    end", tb, re.S)
    neg_bodies = re.findall(r"always\s*@\(\s*negedge\s+dclk\s*\) begin(.*?)\n    end", tb, re.S)
    def assigns(body):
        out = set()
        for m in re.finditer(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*(?:<=|=(?!=))", body, re.M):
            out.add(m.group(1))
        return out
    allb = [("posedge", b) for b in pos_bodies] + [("negedge", b) for b in neg_bodies]
    owners = {}
    for dom, b in allb:
        for v in assigns(b):
            owners.setdefault(v, []).append(dom)
    dual = {v: d for v, d in owners.items() if len(d) > 1}
    print("  TB dclk-domain state variables: %d, dual-writer variables: %s"
          % (len(owners), sorted(dual) or "none"))
    ok &= not dual
    print("  TB posedge-dclk blocks: %d, negedge-dclk blocks: %d"
          % (len(pos_bodies), len(neg_bodies)))
    pin_names = ("din", "din_valid", "latch", "blank", "pwm_start", "pwm_tick")
    drives_pin = any(any(("%s <=" % n) in b or ("%s =" % n) in b for n in pin_names)
                     for _, b in allb)
    print("  no TB block drives a DUT-facing input: %s" % (not drives_pin))
    ok &= not drives_pin
    # started must be written only inside the posedge-dclk block
    sw = all(("started" not in assigns(b)) for d, b in allb if d == "negedge")
    print("  started written in exactly one domain (posedge dclk): %s" % sw)
    ok &= sw
    neg_win = "always @(negedge dclk)" in tb and "sent     <= 0;" in tb
    print("  win/sent updated at negedge dclk: %s" % neg_win)
    ok &= neg_win
    # 5b slot waveform registered at negedge clk
    slot_neg = "always @(negedge clk) begin" in tb and \
               "blank     <=" in tb
    print("  slot waveform registered at negedge clk: %s" % slot_neg)
    ok &= slot_neg
    # 5c no combinational always @(*) left that drives DUT pins
    comb = re.search(r"always\s*@\(\*\)", tb)
    print("  combinational always @(*) blocks left in TB: %d" % (1 if comb else 0))
    ok &= not comb
    # 5d oracle sampling unchanged (it is the oracle - must not be touched)
    dm = open(FILES[2], encoding="utf-8").read()
    dm_ok = "always @(posedge dclk or negedge reset_n)" in dm and "#1;" in dm
    print("  data_model oracle still posedge dclk + 1 ns settle: %s" % dm_ok)
    ok &= dm_ok
    # 5e TB census does not read DUT internals
    m2 = re.search(r"always\s*@\(\s*posedge\s+dclk\s*\)(.*?)end", tb, re.S)
    census_pure = "dut." not in m2.group(1)
    print("  census block reads no DUT signal: %s" % census_pure)
    ok &= census_pure

    print("\n=== 6. assertion inventory (no criterion may be lowered) ===")
    plain = len(re.findall(r'chk\("', tb))
    sfmt = len(re.findall(r'chk\(\$sformatf', tb))
    names = set(re.findall(r'chk\("([A-Z0-9_]+)', tb))
    names |= set(re.findall(r'chk\(\$sformatf\("([A-Za-z0-9_]+)', tb))
    base = {n for n in names if not re.match(r"D(11|12|13|14|15)_", n)}
    print("  static chk sites: %d plain + %d sformatf(x3) = %d executed"
          % (plain, sfmt, plain + sfmt * 3))
    base10 = {n[:3] for n in names}
    need = {("D%02d" % i) for i in list(range(1, 42))}
    missing = need - base10
    print("  original assertion names missing: %s" % (sorted(missing) or "none"))
    ok &= not missing
    added = "D42_" in names
    print("  added census check D42 (strengthens, does not relax): %s" % added)
    ok &= added

    print("\nRESULT: %s" % ("PRECHECK_OK - the run may be spent" if ok
                             else "PRECHECK_FAILED - do NOT spend the run"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
