#!/usr/bin/env python3
"""T6-A static gate (zero ModelSim) — task book §C.

Gates:
  1. the new SPI RTL is present and self-consistent (4 pins only, mode-0 MISO
     updated on the falling edge, single-bit qualifiers for every CDC);
  2. the register subset covers the V1.3 addresses it claims (0x00..0x24);
  3. the testbench has the frozen assertion set, no duplicates, no $fatal;
  4. the offline SPI frame model passes with its two negative controls;
  5. nothing outside the T6-A file set is touched (the T5 five-chip core stays
     frozen: its ten RTL files are unchanged).
"""
import hashlib
import os
import re
import subprocess
import sys

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(S))

T5_FROZEN = {
    "rtl/data_driver.v.txt":   "6d0c5f831423e16c8d76bf583730d11a77d92fa35c203635b346ba678ba359ab",
    "rtl/scan_driver.v.txt":   "6ee3ad38b3a9c2c1a65b37900537875ff52d33ca165145a246dafb0a782229a4",
    "rtl/tcon_top.v.txt":      "0f8e91698e06fb59be894c55e0e627d76f94aa984bac2ad80678ba0a00db2363",
    "rtl/tcon_data_tx.v.txt":  "cc9d35f9e35154c32e005c995778e29a2b191c8f3c70164ecff30f41cf5113d1",
    "rtl/tcon_video_rx.v.txt": "9c99452723f2770029e512ca9aebc6f8c7ad6a049abe5c7217ca6da8c1057e06",
    "rtl/tcon_timebase.v.txt": "1bb27df8ae799148096dbee3c1428379d5b2efd60905905fb8b115d9496953cd",
    "rtl/tcon_slot_seq.v.txt": "f9b4f31720000912a7c8e0a6638d4a499549bd5dc77b461df954588f12b74903",
    "rtl/tcon_col_bank.v.txt": "97c2b4bf1ed0ee54f33f5ee07290f8d81a1de8a59f36b86790b2c6c1d35aa7e4",
    "rtl/data_pin_mon.v.txt":  "9a8ba4f269ae8a9340ca368fe0e715e883966094ba898483a706aad0e2633d74",
    "rtl/scan_pin_mon.v.txt":  "7c280e130a36525836de425acb8c8875a61d6613108203c4c486562458304d10",
}
EXPECTED_ASSERTS = 43

fails = []
NEEDLE = "or " + "True"


def ck(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def read(p):
    return open(p, encoding="utf-8").read()


def main():
    print("=== 1. T5 five-chip core still frozen ===")
    for rel, want in T5_FROZEN.items():
        ck(sha(os.path.join(S, rel)) == want, "%s unchanged" % rel)

    print("\n=== 2. SPI front end (spi_frame) ===")
    fr = read(os.path.join(S, "rtl/spi_frame.v.txt"))
    pins = set(re.findall(r"\b(?:input|output)\s+(?:wire|reg)\s*(?:\[[^\]]*\]\s*)?(\w+)", fr))
    want = {"sclk", "cs_n", "mosi", "miso", "sh", "bitcnt", "frame_full",
            "we", "addr", "rd_req", "rd_addr_hold", "rd_snapshot"}
    ck(pins == want, "spi_frame pin set is exactly the 4 SPI pins + the register-file interface")
    ck(not ({"din_valid", "valid", "load_active", "data_valid"} & pins),
       "no invented VALID/READY pin on the SPI interface")
    ck("always @(negedge sclk or negedge cs_n)" in fr,
       "MISO is updated on the FALLING edge (mode 0)")
    ck("assign rd_req = !cs_n && (bc >= 6'd16) && !sh_r[47];" in fr,
       "rd_req is a single-bit LEVEL qualifier, never a multi-bit bus")
    ck("always @(posedge sclk or negedge cs_n)" in fr,
       "the frame shift register is clocked by SCLK and cleared by CS_n")
    ck("frame_full = (bc == 6'd48)" in fr, "a frame is exactly 48 bits")

    print("\n=== 3. register file / CDC (tcon_spi_regs) ===")
    rg = read(os.path.join(S, "rtl/tcon_spi_regs.v.txt"))
    ck("cs_m  <= cs_n;" in rg and "cs_s1 <= cs_m;" in rg and "cs_s2 <= cs_s1;" in rg,
       "CS_n crosses through a 2-flop synchroniser before the commit edge")
    ck("rq_s1 <= rd_req; rq_s2 <= rq_s1;" in rg,
       "the read qualifier crosses through a 2-flop synchroniser")
    ck("if (rq_s2) rd_snapshot <= rval;" in rg,
       "the read bus is sampled only after the qualifier is seen")
    ck("if (cs_rise && frame_full)" in rg,
       "a write commits on the CS_n RISING edge only")
    for a in ["A_CHIPID", "A_CTRL", "A_MODE", "A_FAULT", "A_INT", "A_INTEN",
              "A_STATUS", "A_WDOG", "A_VIDCFG", "A_COLIDX"]:
        ck(a in rg, "register address decoded: %s" % a)
    ck("cfg_ok   = (!en) && safe_in;" in rg,
       "mode/watchdog writes require EN=0 and SAFE=1 (V1.3 段0570)")
    ck("n_fault = n_fault & ~(w1c_f & ~hw_fault);" in rg,
       "a live hardware fault cannot be cleared by W1C (段0570)")
    ck("n_int = int_status | (n_fault & ~fs_d);" in rg,
       "INT_STATUS latches fault transitions even when INT_EN=0")
    ck("assign irq            = |(int_status & int_en);" in rg,
       "INT_EN only masks the notification")

    print("\n=== 4. testbench assertion set ===")
    tb = read(os.path.join(S, "tb/tcon_t6a_tb.sv.txt"))
    names = re.findall(r'chk\("(D\d\d_[A-Za-z0-9_]+)"', tb)
    ck(len(names) == EXPECTED_ASSERTS,
       "executed assertion count == %d (found %d)" % (EXPECTED_ASSERTS, len(names)))
    ck(len(set(names)) == len(names), "no duplicate assertion name")
    ck("$fatal" not in tb, "no $fatal")
    for need in ["reset", "unblank", "config_while_en_rejected", "misaligned_rejected",
                 "unimplemented_rejected", "ro_write_rejected", "short_frame_discarded",
                 "live_fault_cannot_clear", "w1c_after_fault_gone",
                 "int_en_zero_masks_irq", "slow_sclk_4mhz", "back_to_back_transactions",
                 "enough_real_writes", "enough_real_reads"]:
        ck(any(need in n for n in names), "assertion present: %s" % need)

    print("\n=== 5. offline SPI frame model ===")
    r = subprocess.run([sys.executable, os.path.join(S, "tools/t6a_spi_model.py")],
                       capture_output=True, text=True, timeout=120)
    out = r.stdout.strip().splitlines()
    ck("RESULT=PASS" in r.stdout, "t6a_spi_model.py PASS")
    for ln in out[-4:]:
        print("     " + ln)

    print("\n=== 6. no forbidden predicate in the checkers ===")
    for rel in ["tools/t6a_spi_model.py", "tools/t5_epoch_replay.py"]:
        ck(NEEDLE not in read(os.path.join(S, rel)), "%s clean" % rel)

    print("\n=== 7. work tree ===")
    st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                        capture_output=True, text=True, timeout=60).stdout.splitlines()
    touched = [l for l in st if "/rtl/" in l and ("data_driver" in l or "scan_driver" in l
                                                   or "tcon_top" in l or "tcon_data" in l
                                                   or "tcon_video" in l or "tcon_time" in l
                                                   or "tcon_slot" in l or "tcon_col" in l)]
    ck(not touched, "no T5 core RTL modified (%d found)" % len(touched))

    print("\n=== RESULT ===")
    print("SPI_RTL_SHA=%s" % sha(os.path.join(S, "rtl/spi_frame.v.txt")))
    print("REGS_RTL_SHA=%s" % sha(os.path.join(S, "rtl/tcon_spi_regs.v.txt")))
    print("TB_SHA=%s" % sha(os.path.join(S, "tb/tcon_t6a_tb.sv.txt")))
    print("GATES_FAILED=%d" % len(fails))
    print("RESULT=%s" % ("PASS" if not fails else "FAIL"))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
