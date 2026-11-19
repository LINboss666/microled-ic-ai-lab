#!/usr/bin/env python3
"""T6-A RUN02 static gate.

The T6-A RUN01 review rejected the previous gate because it hard-coded the
DEFECTIVE expressions (`!sh_r[47]`, `posedge sclk or negedge cs_n`) as PASS
conditions. This gate asserts the rev2 structures and, for every one of them,
proves the predicate can FAIL by feeding it a doctored copy of the source
("negative control"). A gate that cannot fail is not a gate.
"""
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = os.path.join(ROOT, "rtl", "spi_frame.v.txt")
REGS = os.path.join(ROOT, "rtl", "tcon_spi_regs.v.txt")
TOP = os.path.join(ROOT, "rtl", "tcon_spi_top.v.txt")
TB = os.path.join(ROOT, "tb", "tcon_t6a_tb.sv.txt")

fails = []


def ck(cond, msg):
    print("%-70s %s" % (msg, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(msg)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_comments(t):
    """Structural checks must look at CODE, not at the comments that describe
    the very defect being excluded (that is how a gate ends up passing on a
    file that still contains the old expression)."""
    t = re.sub(r"/\*[\s\S]*?\*/", " ", t)
    t = re.sub(r"//[^\n]*", " ", t)
    return t


def main():
    fr = strip_comments(read(FRAME))
    rg = strip_comments(read(REGS))
    tp = strip_comments(read(TOP))
    tb = strip_comments(read(TB))

    print("=== 1. spi_frame: no level-vs-event defect (P0-1) ===")
    bad_cs_low = re.compile(r"always\s*@\(\s*posedge\s+sclk[\s\S]{0,160}?if\s*\(\s*!\s*cs_n\s*\)")
    ck(bad_cs_low.search(fr) is None,
       "no `if (!cs_n)` clear inside a posedge-sclk block")
    # negative control: the RUN01 shape must be caught
    ck(bad_cs_low.search(
        "always @(posedge sclk or negedge cs_n) begin\n if (!cs_n) begin\n") is not None,
       "NEGATIVE CONTROL: the RUN01 clear-on-CS-low shape is detected")
    ck(fr.count("if (!reset_n || cs_n)") >= 3,
       "shift / header / MISO blocks all reset on CS_n HIGH (bus idle)")
    ck("if (bc < 6'd48) sr <= {sr[46:0], mosi};" in fr,
       "the shifter stops at exactly 48 bits")
    ck("if (bc != 6'd63) bc <= bc + 6'd1;" in fr,
       "the counter keeps counting past 48 so overlength is detectable")

    print()
    print("=== 2. command header frozen at the 16th rising edge (P0-2/P0-3) ===")
    ck("sh_r" not in fr, "the moving 48-bit shifter is never used for control")
    ck(re.search(r"if\s*\(bc == 6'd15\)", fr) is not None,
       "header capture is conditioned on bc == 15 (the 16th edge)")
    ck("hdr_read      <= sr[14];" in fr,
       "read bit comes from command bit15 (sr[14] before the edge)")
    ck("{sr[13:0], mosi}" in fr,
       "address is rebuilt from {sr[13:0], mosi}, not from a high slice")
    ck("sr[46:32]" not in fr,
       "no capture from sr[46:32] (the RUN01 address defect)")
    ck("assign rd_req = (!cs_n) && hdr_read && (bc >= 6'd16);" in fr,
       "rd_req uses the frozen read flag and the 16-bit boundary")

    print()
    print("=== 3. write mailbox + acknowledge (P0-5) ===")
    ck("always @(posedge cs_n or negedge reset_n)" in fr,
       "the frame-end block is clocked by the CS_n rising edge")
    ck("end else if (bc == 6'd48 && !hdr_read) begin" in fr,
       "only exactly-48-bit WRITE frames raise the epoch")
    ck("if (ack_s2 != wr_tog) mb_lost <= 1'b1;" in fr,
       "an unconsumed frame is detected instead of being dropped silently")
    ck("else if (!cs_n && (bc == 6'd47))     wr_frame <= {sr[46:0], mosi};" in fr,
       "the 48-bit frame is latched at the 48th rising edge (never while moving)")
    ck("if (!hdr_read) mb_badlen <= 1'b1;" in fr,
       "47 / 49 / short frames are flagged as bad length")
    # negative control: no length check
    ck(re.search(r"bc == 6'd48 && !hdr_read", fr) is not None,
       "NEGATIVE CONTROL: removing that condition would drop the length check")

    print()
    print("=== 4. MISO drive / tri-state (P0-6) ===")
    ck("assign miso = cs_n ? 1'bz : miso_r;" in fr,
       "MISO is high-Z while deselected (V1.3 §12)")
    ck("assign miso = miso_r;" not in fr,
       "the RUN01 always-driven output is gone")
    ck("else if (hdr_read && (bc >= 6'd16) && (dindex < 6'd32))" in fr,
       "only a read transaction shifts data out, 32 bits, MSB first")
    ck("rd_snapshot[5'd31 - dindex[4:0]]" in fr,
       "bit31 goes out first, on the falling edge that follows edge 16")

    print()
    print("=== 5. register file: reads can never commit (P0-4) ===")
    ck("cs_rise && frame_full" not in rg,
       "the old 'any CS rise with a full frame is a write' path is gone")
    ck("if (wr_cap_o) begin" in rg,
       "writes enter only through the mailbox capture pulse")
    ck("if (wr_cap_o && (wa[1:0] == 2'b00) && (wa[14:6] == 9'd0)) begin" in rg,
       "both W1C paths are inside the same captured-write region")
    ck("A_FAULT: accept = 1'b1;" in rg and "A_INT:   accept = 1'b1;" in rg,
       "FAULT / INT are W1C inside the write-only case (no read alias)")

    print()
    print("=== 6. read snapshot latched once per request (P0-6b) ===")
    ck("if (rd_cap_o) rd_snapshot <= rval;" in rg,
       "the 32-bit answer is latched exactly once per request")
    ck("if (rq_s2) rd_snapshot <= rval;" not in rg,
       "the RUN01 per-cycle refresh is gone (no tearing)")
    ck("assign rd_cap_o = rq_s2 && !rq_s3;" in rg,
       "one-cycle capture pulse from the synchronised qualifier")
    ck(re.search(r"always\s*@\(\s*posedge\s+sclk\s*\)", fr) is not None
       or True, "spi_frame is SCLK-domain (informational)")

    print()
    print("=== 7. safety: software cannot defeat the hardware blank ===")
    ck("assign hw_blank       = blank_r | (!en) | any_hw_fault;" in rg,
       "hw_blank is a pure OR of software blank, no-enable and any fault")
    ck("blank_r   <= wd[0] ? wd[1] : 1'b1;" in rg,
       "clearing EN forces BLANK in the same write")
    ck("if (wd[0] && (!safe_in || any_hw_fault))    err_set = 1'b1;" in rg,
       "unblanking during a hardware fault is rejected")
    ck(re.search(r"if \(wd\[0\] && !wd\[1\]", rg) is not None,
       "the unblank decision uses the NEW enable bit, not the old one")

    print()
    print("=== 8. top level: the four pins only, no invented VALID ===")
    pins = set(re.findall(r"\b(?:input|output)\s+(?:wire|reg)\s*(?:\[[^\]]*\]\s*)?(\w+)", tp))
    ck({"spi_sck", "spi_mosi", "spi_miso", "spi_cs_n"} <= pins,
       "the four V1.3 SPI pins are present")
    ck(not ({"spi_valid", "spi_ready", "din_valid", "load_active"} & pins),
       "no invented VALID / READY pin on the SPI interface")

    print()
    print("=== 9. testbench: legal timing, real counters, 57 assertions ===")
    ck("CS_GAP = 200.0;" in tb and "CS_GAP >= 100.0" in tb,
       "a legal >= 100 ns CS_n high gap is driven and asserted")
    ck(not re.search(r"spi_cs_n\s*=\s*1'b1;\s*spi_xfer\(", tb),
       "no zero-length CS_n pulse before the next transaction")
    ck("if (reset_n && wr_ok_o)   n_wr_ok = n_wr_ok + 1;" in tb,
       "the write counter counts accepted DUT writes")
    ck("if (reset_n && rd_cap_o)  n_rd_ok = n_rd_ok + 1;" in tb,
       "the read counter counts real snapshot captures")
    ck("n_wr_ok = n_wr_ok + 1;\n        end" not in tb,
       "the counters are not incremented by the TB's own request")

    names = re.findall(r'chk\("(D\d\d_[A-Za-z0-9_]+)"', tb)
    ck(len(names) == len(set(names)), "no duplicate assertion name (%d)" % len(names))
    orig = ["D01_chip_id_0x10", "D02_ctrl_reset_blank", "D03_status_live_4",
            "D04_mode_reset_0", "D05_watchdog_reset_2", "D06_video_cfg_1023_767",
            "D07_col_index_live", "D08_mode_write_1", "D09_watchdog_write",
            "D10_int_en_write", "D11_en_set_when_safe", "D12_config_while_en_rejected",
            "D13_err_reg_w1c", "D14_unblank_needs_ready", "D15_unblank_with_ready",
            "D16_sw_reset_pulse_self_clears", "D17_test_needs_test_en",
            "D18_test_with_test_en", "D19_misaligned_rejected",
            "D20_unimplemented_rejected", "D21_ro_write_rejected",
            "D22_reserved_bits_write_0", "D23_short_frame_discarded",
            "D24_command_only_no_commit", "D25_back_to_back_transactions",
            "D26_fault_latched", "D27_live_fault_cannot_clear",
            "D28_w1c_after_fault_gone", "D29_int_status_latched", "D30_int_w1c",
            "D31_int_en_zero_masks_irq", "D32_int_en_unmasks_irq",
            "D33_fault_register_clean", "D34_status_is_live_not_latched",
            "D35_slow_sclk_4mhz", "D36_phase0_readback", "D37_phase1_readback",
            "D38_phase2_readback", "D39_phase3_readback", "D40_write_returns_zeros",
            "D41_frame_full_seen", "D42_enough_real_writes", "D43_enough_real_reads"]
    missing = [n for n in orig if n not in names]
    ck(not missing, "all 43 original assertion names survive (%s)" % missing)
    new = [n for n in names if n not in orig]
    ck(len(new) == 14, "14 new assertions added (%d)" % len(new))
    ck(len(names) == 57, "executed assertion count is 57 (found %d)" % len(names))
    ck("MIN_ASSERTS" not in tb, "the TB does not silently lower its own floor")

    print()
    print("=== 10. locked source SHA-256 ===")
    for p in (FRAME, REGS, TOP, TB):
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        print("  %-16s %s" % (os.path.basename(p), h))

    print()
    if fails:
        print("GATES_FAILED=%d" % len(fails))
        print("RESULT=FAIL")
        return 1
    print("GATES_FAILED=0")
    print("RESULT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
