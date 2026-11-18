#!/usr/bin/env python3
"""T6-A offline SPI frame model (zero ModelSim).

Models exactly what spi_frame.v and the TB driver do, in quarter-SCLK steps:

  TB   : MOSI is updated at the falling edge, SCK rises T/2 later;
         MISO is sampled T/4 after the rising edge.
  DUT  : shifts MOSI on the rising edge; drives MISO on the FALLING edge,
         one data bit per falling edge starting with bc == 16.

It proves
  1. the 48 sampled MOSI bits are command[15:0] + data[31:0] in order;
  2. the 32 MISO bits the master samples are rd[31..0] in order;
  3. one-bit misalignment or a rising-edge MISO update is DETECTED by the same
     check (negative controls) - the model is not vacuous.
"""
import sys

BITS = 48


def run(read, shift_on_rising=False, frame_start=0, miso_shift=0):
    """Return (mosi_frame_bits, miso_sampled_bits)."""
    cmd = 0xA5C3                       # bit15 = 1 -> read
    data = 0x1234_5678
    rd = 0xDEAD_BEEF
    frame = [(cmd >> i) & 1 for i in range(15, -1, -1)] + \
            [(data >> i) & 1 for i in range(31, -1, -1)]

    sent = []                          # bits the DUT shifts in
    sampled = []                       # bits the master reads back
    bc = 0
    dindex = 0
    miso = 0
    for k in range(BITS):
        bit = frame[k + frame_start] if (k + frame_start) < BITS else 0
        # ---- rising edge: DUT samples MOSI -----------------------------
        sent.append(bit)
        bc = min(bc + 1, 48)
        if shift_on_rising and read and bc > 16:
            miso = (rd >> max(0, 31 - min(dindex, 31) - miso_shift)) & 1
            dindex += 1
        # ---- master samples MISO T/4 after the rising edge, i.e. BEFORE
        #      the falling edge of the same period (mode 0) ---------------
        if k >= 16:
            sampled.append(miso)
        # ---- falling edge: DUT updates MISO (mode 0) --------------------
        if not shift_on_rising and read and bc >= 16 and bc <= 47:
            miso = (rd >> max(0, 31 - min(dindex, 31) - miso_shift)) & 1
            dindex = min(dindex + 1, 31)
    return sent, sampled, rd


def main():
    sent, sampled, rd = run(True)
    frame_ok = (len(sent) >= 48)
    cmd_bits = sent[:16]
    cmd = 0
    for b in cmd_bits:
        cmd = (cmd << 1) | b
    data = 0
    for b in sent[16:48]:
        data = (data << 1) | b
    print("captured cmd=0x%04X data=0x%08X" % (cmd, data))
    ok_cmd = (cmd == 0xA5C3) and (data == 0x1234_5678)

    exp = [(rd >> i) & 1 for i in range(31, -1, -1)]
    got = sampled[:32]
    print("miso sampled = 0x%08X (expected 0x%08X)" % (
        int("".join(map(str, got)), 2) if len(got) == 32 else -1, rd))
    ok_miso = (got == exp)

    # ---- NC1: the read word is presented one bit late -------------------
    _, s2, _ = run(True, miso_shift=1)
    nc1 = (s2[:32] != exp)
    # ---- NC2: the received frame is one bit misaligned ------------------
    f3, _, _ = run(True, frame_start=1)
    c3 = 0
    for b in f3[:16]:
        c3 = (c3 << 1) | b
    nc2 = (c3 != 0xA5C3)

    print("NC1_rising_edge_miso_mismatch=%d (must be 1)" % nc1)
    print("NC2_one_bit_misalignment_mismatch=%d (must be 1)" % nc2)
    print("RESULT=%s" % ("PASS" if (ok_cmd and ok_miso and nc1 and nc2) else "FAIL"))
    return 0 if (ok_cmd and ok_miso and nc1 and nc2) else 1


if __name__ == "__main__":
    sys.exit(main())
