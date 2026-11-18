#!/usr/bin/env python3
"""T5-B negative controls for the core scoreboard (small model, zero ModelSim).

The T5 testbench's central claim is a three-way equality inside every display
window:

    Scan's real 1024-bit one-hot  ==  Data#0 tag  ==  Data#1 tag  ==  expected
    and the 768 stored bytes (raw + LUT-mapped + PAM) belong to THAT column.

A checker that cannot fail proves nothing, so this script runs the same
decision rule on a good vector and on three deliberately wrong ones. Each
negative case MUST be rejected; the script fails if any of them passes.
"""
import sys

TAG_MASK = 0x3FF


def tag_bytes(col, frame):
    """pixel[0] and pixel[1] of a lane (V1.3 10-bit column + 6-bit frame)."""
    return (col & 0xFF), (((col >> 8) & 0x3) << 6) | (frame & 0x3F)


def decode_tag(b0, b1):
    return (((b1 >> 6) & 0x3) << 8) | b0, (b1 & 0x3F)


def judge(scan_col, tag0, tag1, frm0, frm1, exp_col, exp_frame, bank_matches_table):
    """The core decision rule, identical in spirit to window_body in the TB."""
    errs = []
    if scan_col != exp_col:
        errs.append("SCAN_SELECTION")
    if tag0 != exp_col:
        errs.append("DATA0_TAG")
    if tag1 != exp_col:
        errs.append("DATA1_TAG")
    if frm0 != exp_frame or frm1 != exp_frame:
        errs.append("FRAME_TAG")
    if not bank_matches_table:
        errs.append("BANK_MAPPING")
    return errs


def main():
    col, frame = 768, 3
    b0, b1 = tag_bytes(col, frame)
    d0 = decode_tag(b0, b1)
    d1 = decode_tag(b0, b1)
    print("encoding: col=%d frame=%d -> b0=0x%02X b1=0x%02X decode=%s"
          % (col, frame, b0, b1, (d0, d1)))

    fails = 0

    # ---- positive control: everything correct ---------------------------
    e = judge(col, d0[0], d1[0], d0[1], d1[1], col, frame, True)
    print("POS  correct vector            -> %s" % (e if e else "ACCEPT"))
    if e:
        print("FAIL: the rule rejects a correct vector")
        fails += 1

    # ---- NC1: Data#1 tag off by one -------------------------------------
    bad = (col ^ 1) & TAG_MASK
    nb0, nb1 = tag_bytes(bad, frame)
    n0 = decode_tag(nb0, nb1)
    e = judge(col, d0[0], n0[0], d0[1], n0[1], col, frame, True)
    print("NC1  Data#1 tag col^1          -> %s" % (e if e else "ACCEPT"))
    if not e:
        print("FAIL: a wrong Data#1 tag was accepted")
        fails += 1

    # ---- NC2: Scan address off by one -----------------------------------
    e = judge((col ^ 1) & TAG_MASK, d0[0], d1[0], d0[1], d1[1], col, frame, True)
    print("NC2  Scan selection col^1       -> %s" % (e if e else "ACCEPT"))
    if not e:
        print("FAIL: a wrong Scan selection was accepted")
        fails += 1

    # ---- NC3: LUT switched, display bank still holds the old mapping -----
    lut_a = {k: (k & 0x3F) for k in range(256)}
    lut_b = {k: ((7 - (k >> 6)) << 6) | (k & 0x3F) for k in range(256)}
    raw = 0x5A
    stale = lut_a[raw]                       # bank loaded before the switch
    fresh = lut_b[raw]                       # what the new table requires
    e = judge(col, d0[0], d1[0], d0[1], d1[1], col, frame, stale == fresh)
    print("NC3  stale bank after LUT swap  -> %s  (old=0x%03X new=0x%03X)"
          % (e if e else "ACCEPT", stale, fresh))
    if not e:
        print("FAIL: a display mapped by the OLD table was accepted")
        fails += 1

    # ---- tag injectivity: 0 / 256 / 512 / 768 must differ ---------------
    tags = [tag_bytes(c, frame) for c in (0, 256, 512, 768)]
    if len(set(tags)) != 4:
        print("FAIL: the column tag is not injective over 0/256/512/768")
        fails += 1
    else:
        print("OK   column tags distinct for 0/256/512/768: %s" % (tags,))
    same_col = [tag_bytes(col, f) for f in (0, 1, 63)]
    if len(set(same_col)) != 3:
        print("FAIL: the frame tag is not injective")
        fails += 1
    else:
        print("OK   frame tags distinct for 3 frame numbers")

    print("RESULT=%s" % ("PASS" if fails == 0 else "FAIL"))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
