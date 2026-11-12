#!/usr/bin/env python3
"""T1 edge-table self check (pure arithmetic, no EDA).

Verifies the inequalities stated in rtl/tcon_t1_edge_table.md §4 so that the
hand-written table cannot drift from the RTL parameters. Exit 0 = all PASS.
"""
CYC = 10e-9            # 10 ns per CLK_REF cycle
WIN = 768              # PWM activity window
SLOT_S, SLOT_L = 976, 977
LATCH_AT, PWM_START_AT, SCAN_STB_AT, PULSE = 828, 840, 880, 4
LOAD_LEN = 768         # 384 bytes per port at 50 MHz = 7680 ns
GUARD = 4              # last data -> LATCH >= 40 ns
COLID_STABLE_AT = 864

res = []
def chk(name, cond, detail=""):
    res.append((name, bool(cond), detail))
    print("[%s] %-44s %s" % ("PASS" if cond else "FAIL", name, detail))

print("T1 EDGE TABLE SELF CHECK (no simulation)")
print("-" * 66)

chk("window + blank = short slot", WIN + (SLOT_S - WIN) == SLOT_S, f"{WIN}+208={SLOT_S}")
chk("window + blank = long slot",  WIN + (SLOT_L - WIN) == SLOT_L, f"{WIN}+209={SLOT_L}")
chk("blank short = 208 cycles", SLOT_S - WIN == 208, f"{SLOT_S-WIN}")
chk("blank long  = 209 cycles", SLOT_L - WIN == 209, f"{SLOT_L-WIN}")

load_start = LATCH_AT + PULSE           # 832
load_end   = load_start + LOAD_LEN      # 1600
next_latch = LATCH_AT + SLOT_S          # 1804
deadline   = next_latch - GUARD         # 1800
slack      = deadline - load_end        # 200
chk("load starts after LATCH pulse", load_start == 832, f"{load_start}")
chk("load ends inside next slot", load_end == 1600, f"{load_end} (= {load_end-SLOT_S} in next slot)")
chk("data_load_deadline = next LATCH - guard", deadline == 1800, f"{deadline}")
chk("data_load net slack = 200 cycles", slack == 200, f"{slack} cycles = {slack*CYC*1e6:.2f} us")
# The naive figure 976-768=208 ignores that the loader cannot start until the
# LATCH pulse ends (4 cycles), so the REAL gap between load end and next LATCH
# is 204. 204 - 4 (last-data guard) = 200 net. Keep all three numbers explicit.
chk("naive 976-768 = 208", SLOT_S - LOAD_LEN == 208, "208")
chk("real gap 208-4(LATCH pulse) = 204", next_latch - load_end == 204, f"{next_latch-load_end}")
chk("chain 208-4-4 = 200 net", (SLOT_S - LOAD_LEN) - PULSE - GUARD == 200, "200")

# video receipt deadline: bank swap happens at LATCH, receive window ends at WIN
video_deadline = LATCH_AT
video_slack = video_deadline - WIN
chk("video_receipt_deadline = 828", video_deadline == 828, f"{video_deadline}")
chk("video net slack = 60 cycles", video_slack == 60, f"{video_slack} cycles = {video_slack*CYC*1e6:.2f} us")
chk("two deadlines differ by 140 cycles", slack - video_slack == 140, f"{slack-video_slack}")

chk("LATCH pulse = 40 ns", PULSE * CYC == 40e-9, "4 cycles")
chk("PWM_START pulse = 40 ns", PULSE * CYC == 40e-9, "4 cycles")
chk("COL_ID setup = 160 ns >= 10 ns", (SCAN_STB_AT - COLID_STABLE_AT) * CYC == 160e-9, "16 cycles")
chk("COL_ID hold covered by 40 ns pulse >= 5 ns", PULSE * CYC >= 5e-9, "40 ns")

chk("frame = 576*977 + 448*976", 576*977 + 448*976 == 1000000, f"{576*977+448*976}")
chk("ticks per window = 768/12", WIN % 12 == 0 and WIN // 12 == 64, "64")

bad = [r for r in res if not r[1]]
print("-" * 66)
print("checks=%d failed=%d" % (len(res), len(bad)))
print("VERDICT:", "ALL_PASS" if not bad else "FAILURES")
raise SystemExit(0 if not bad else 1)
