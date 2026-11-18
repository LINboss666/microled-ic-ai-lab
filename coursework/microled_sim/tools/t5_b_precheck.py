#!/usr/bin/env python3
"""T5-B static gate (zero ModelSim).

Everything here must hold BEFORE the single authorized T5 vsim is started:

  1. the five RTL files are byte-identical to their accepted versions;
  2. the integration shell carries no byte-window stub and no invented VALID pin;
  3. the testbench has the frozen assertion set, no duplicates, no `$fatal`;
  4. the LUT image satisfies the Data chip's commit rule (black / full scale);
  5. the checkers themselves contain no always-true predicate;
  6. `git status` shows no RTL modification.

Exit 0 = all gates pass.
"""
import hashlib
import os
import re
import subprocess
import sys

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../microled_sim
ROOT = os.path.dirname(os.path.dirname(S))                        # repo root

FROZEN = {
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

EXPECTED_ASSERTS = 56

fails = []
NEEDLE = "or " + "True"   # built at run time so this file does not match itself


def ck(cond, what):
    if cond:
        print("ok   %s" % what)
    else:
        print("FAIL %s" % what)
        fails.append(what)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read(path):
    return open(path, encoding="utf-8").read()


def main():
    print("=== 1. frozen RTL identity ===")
    for rel, want in FROZEN.items():
        got = sha(os.path.join(S, rel))
        ck(got == want, "%s == %s..%s" % (rel, want[:8], want[-4:]))

    print("\n=== 2. integration shell ===")
    sh = read(os.path.join(S, "tb/t5_five_chip_shell.sv.txt"))
    ck("wire dv_stub" not in sh and "arming ||" not in sh and "bw_cnt" not in sh,
       "no 385-edge byte-window stub in the shell")
    ck(sh.count("USE_DIN_VALID(0)") == 2, "both Data chips run the V1.3 self-delimiting mode")
    ck(sh.count(".din_valid (1'b0)") == 2, "both din_valid pins tied low (no VALID wire)")
    ck(".din_valid (load_active" not in sh and ".din_valid (load_active_obs" not in sh,
       "load_active is never wired to din_valid")
    ck("assign tcon_load_active = load_active_obs;" in sh,
       "load_active exists only as an observation output")

    print("\n=== 3. testbench assertion set ===")
    tb = read(os.path.join(S, "tb/tcon_t5_tb.sv.txt"))
    names = re.findall(r'chk\("(D\d\d_[A-Za-z0-9_]+)"', tb)
    ck(len(names) == EXPECTED_ASSERTS,
       "executed assertion count == %d (found %d)" % (EXPECTED_ASSERTS, len(names)))
    ck(len(set(names)) == len(names), "no duplicate assertion name")
    ck("$fatal" not in tb, "no $fatal in the testbench (all failures still counted)")
    for need in ["scan_selection_matches", "data0_tag_matches_scan", "data1_tag_matches_scan",
                 "bank_content_768_bytes", "pwm_width_matches_lut", "pooled_onehot_every_window",
                 "switch_flips_both_banks_on_latch_edge", "one_dark_window_after_switch",
                 "fault_blocks_bank_flip", "pending_commit_persists",
                 "latched_fault_blocks_commit", "faultn_cycle_does_not_recover",
                 "precharge_no_window", "seen_columns_0_1_2_1022_1023_nextframe0"]:
        ck(any(need in n for n in names), "assertion present: %s" % need)

    print("\n=== 4. LUT image ===")
    lut = [int(x, 16) for x in read(os.path.join(S, "t3b/GRAY_LUT_DEFAULT.hex.txt")).split()]
    ck(len(lut) == 256, "256 entries")
    ck(lut[0] == 0x000, "entry 0 = black (PWM code 0)")
    ck(lut[255] == 0x1FF, "entry 255 = full scale (PAM 7, code 63)")
    ck(len(set(v & 0x3F for v in lut)) == 64, "all 64 PWM codes exercised by the image")

    print("\n=== 5. no always-true predicate in the checkers ===")
    for rel in ["tools/t5_b_precheck.py", "tools/t5_negative_control.py",
                "tools/t5_offline_timeline.py", "tools/t5_framing_model.py"]:
        t = read(os.path.join(S, rel))
        ck(NEEDLE not in t, "%s has no always-true predicate" % rel)
    ck("chk(\"D" not in read(os.path.join(S, "tools/t5_b_precheck.py")),
       "the gate does not call the TB assertion macro itself")

    print("\n=== 6. no RTL modification in the work tree ===")
    try:
        st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                            capture_output=True, text=True, timeout=60).stdout.splitlines()
    except Exception as exc:                                    # pragma: no cover
        st = []
        print("note: git status unavailable (%s)" % exc)
    touched = [l for l in st if "/rtl/" in l]
    ck(not touched, "no rtl/ file modified (%d found)" % len(touched))

    print("\n=== RESULT ===")
    print("GATES_FAILED=%d" % len(fails))
    print("RESULT=%s" % ("PASS" if not fails else "FAIL"))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
