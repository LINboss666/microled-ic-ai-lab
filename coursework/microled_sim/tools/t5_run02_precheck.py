#!/usr/bin/env python3
"""T5-B RUN02 hard gate (zero ModelSim) — task book §3.

Checks, in order:
  1. the ten RTL/monitor files are byte-identical to the accepted versions;
  2. the integration shell is untouched (RUN01 SHA);
  3. the testbench DID change but keeps every one of the 56 assertion NAMES
     (no deletion, no rename, no duplicate) and contains no `$fatal`;
  4. the epoch is derived from the LOAD SLOT, the dark window from the switch
     bookkeeping (not from the DUT's col_valid), and the dark window still
     compares 768 bytes (no skipping);
  5. the LUT image is the original archive file;
  6. `git status` shows no RTL modification.
"""
import hashlib
import os
import re
import subprocess
import sys

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(S))

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
SHELL_SHA   = "5c9ee2ec5b34df8a4a824cbd6944b59d7ef26a1c7a619691734c15100fa1ebde"
TB_RUN01_SHA = "b075cc7ff0115c54780b4541275ec2f3e7ead3dd15041efecbf3352c0ae247f0"
LUT_SHA     = "e3e39b43f7e0f76e5f2865338c271402a1da5b1fd8b4e6193c0ed668f79cb253"

fails = []
NEEDLE = "or " + "True"


def ck(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        fails.append(what)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    print("=== 1. frozen RTL identity (10 files) ===")
    for rel, want in FROZEN.items():
        ck(sha(os.path.join(S, rel)) == want, "%s unchanged" % rel)

    print("\n=== 2. integration shell untouched ===")
    ck(sha(os.path.join(S, "tb/t5_five_chip_shell.sv.txt")) == SHELL_SHA,
       "t5_five_chip_shell.sv SHA == RUN01 value")

    print("\n=== 3. testbench: changed, but the assertion set is frozen ===")
    tb = open(os.path.join(S, "tb/tcon_t5_tb.sv.txt"), encoding="utf-8").read()
    tb_sha = sha(os.path.join(S, "tb/tcon_t5_tb.sv.txt"))
    ck(tb_sha != TB_RUN01_SHA, "TB differs from the RUN01 source (it must be edited)")
    names = re.findall(r'chk\("(D\d\d_[A-Za-z0-9_]+)"', tb)
    ck(len(names) == 56, "56 executed assertions (found %d)" % len(names))
    ck(len(set(names)) == 56, "no duplicate assertion name")
    base = None
    for cand in (os.environ.get("T5_RUN01_TB", ""),
                 "D:/ic617_course_sim_20261112_native/t5b_run02_precheck/tcon_t5_tb_run01.sv",
                 "/tmp/tcon_t5_tb_run01.sv"):
        if cand and os.path.exists(cand):
            base = cand
            break
    if base:
        old = re.findall(r'chk\("(D\d\d_[A-Za-z0-9_]+)"', open(base, encoding="utf-8").read())
        ck(sorted(old) == sorted(names), "the 56 names are IDENTICAL to RUN01 (no deletion/rename)")
    else:
        ck(False, "RUN01 TB snapshot available for the name comparison")
    ck("$fatal" not in tb, "no $fatal (a failing assertion still returns through T6)")
    for need in ["tab_b_slot", "win_dark_exp", "T5_SWITCH_DARK", "T5_SWITCH_EPOCH",
                 "T5_SWITCH_RESTART", "dark_low >= 760"]:
        ck(need in tb, "source contains %s" % need)

    print("\n=== 4. semantics: epoch per LOAD slot, dark window not skipped ===")
    # the epoch must compare the LOAD slot (S-2) against the switch slot
    ck("((slot_done - 2) >= tab_b_slot)" in tb,
       "epoch compares the display column's LOAD slot, not the commit moment")
    ck("tab_b_slot = switch_slot;" in tb,
       "epoch is anchored on the slot whose LATCH edge flipped the bank")
    ck("win_dark_exp = (switch_done && (slot_done == switch_slot + 1))" in tb,
       "the dark window is derived from TB bookkeeping, not from the DUT's col_valid")
    ck("tab_b_slot = 1000000000;" in tb,
       "an explicit reset clears the epoch (table A again)")
    # the 768-byte comparison must NOT be conditioned on the dark window
    body = tb.split("task automatic window_body;")[1].split("endtask")[0]
    ck("wbad = 0;" in body and "for (wi = 0; wi < 384; wi = wi + 1)" in body,
       "the dark window still compares 384+384 bytes (no skip)")
    ck(body.count("if (win_dark_exp") == 1 and "ch_on_bad" in body,
       "only the 'some channel on' and 'blank implies valid' rules are exempted")
    ck("if (win_dark_exp == 1) begin" in tb and "pwm_exp[jj]     = 0;" in tb,
       "the dark window expects zero PWM ticks instead of being dropped")

    print("\n=== 5. original LUT archive ===")
    ck(sha(os.path.join(S, "t3b/GRAY_LUT_DEFAULT.hex.txt")) == LUT_SHA,
       "258-entry gray LUT SHA == e3e39b43..cb25 (the file the reviewer recomputed from)")

    print("\n=== 6. no RTL modification in the work tree ===")
    st = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                        capture_output=True, text=True, timeout=60).stdout.splitlines()
    touched = [l for l in st if "/rtl/" in l]
    ck(not touched, "no rtl/ file modified (%d found)" % len(touched))

    print("\n=== 7. replay / negative controls already archived ===")
    for rel in ["tools/t5_epoch_replay.py", "tools/t5_negative_control.py",
                "tools/t5_offline_timeline.py"]:
        t = open(os.path.join(S, rel), encoding="utf-8").read()
        ck(NEEDLE not in t, "%s has no always-true predicate" % rel)

    print("\n=== RESULT ===")
    print("TB_SHA=%s" % tb_sha)
    print("GATES_FAILED=%d" % len(fails))
    print("RESULT=%s" % ("PASS" if not fails else "FAIL"))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
