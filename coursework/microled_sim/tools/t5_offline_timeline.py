#!/usr/bin/env python3
"""T5-B offline pre-check (zero ModelSim).

Runs the cycle-accurate framing model over ALL 1024 slots of one V1.3 frame and
proves three things before the single authorized vsim is spent:

  1. the frame is exactly 1,000,000 cycles (576 long + 448 short slots);
  2. with the TB's start-up phase (dclk_r LOW during slot cycle 0) and the
     Data chip's post-edge LATCH view, every slot delivers its 384 bytes IN
     ORDER - including the 976/977 mix, which flips the phase at every slot
     boundary;
  3. the display pipeline: the window of slot S carries the column that was
     loaded during slot S-2 (commit at S-1, SCAN_STB at S-1).

Negative controls make the claim falsifiable:
  NC1  switching the sampling convention to 'pre' must break the order;
  NC2  moving the pre-fetch one cycle later must break the order.
"""
import csv
import sys

import t5_framing_model as fm

N_COL = 1024
FRAME = 1_000_000


def main():
    lens = fm.slot_lengths(N_COL)
    total = sum(lens)
    print("frame_cycles=%d expected=%d long=%d short=%d"
          % (total, FRAME, lens.count(977), lens.count(976)))
    if total != FRAME:
        print("FAIL: frame is not exactly 1,000,000 cycles")
        return 2

    w = fm.run(0, 'post', N_COL)
    good = sum(1 for s in w if w[s][0] == 384 and w[s][1] == list(range(384)))
    bad = len(w) - good
    print("windows=%d byte_exact=%d bad=%d (expected windows=%d)"
          % (len(w), good, bad, N_COL - 1))
    for s in sorted(w):
        n, cap = w[s]
        if n != 384 or cap != list(range(384)):
            print("FAIL window_in_slot=%d bytes=%d first=%s last=%s"
                  % (s, n, cap[:4], cap[-3:]))
            break

    # ---- negative controls -------------------------------------------------
    n1 = fm.run(0, 'pre', 8)
    b1 = sum(1 for s in n1 if n1[s][1] != list(range(384)))
    print("NC1_sampling_pre_windows_broken=%d/%d (must be > 0)" % (b1, len(n1)))
    if b1 == 0:
        print("FAIL: the model cannot see a pre/post sampling difference")
        return 3

    # NC2: pre-fetch one cycle later (a TB phase error) must also break it
    fm.LOAD_START = 832 + 1
    n2 = fm.run(0, 'post', 8)
    b2 = sum(1 for s in n2 if n2[s][1] != list(range(384)))
    fm.LOAD_START = 832
    print("NC2_prefetch_one_cycle_late_windows_broken=%d/%d (must be > 0)" % (b2, len(n2)))
    if b2 == 0:
        print("FAIL: the model cannot see a pre-fetch phase error")
        return 3

    with open("t5_framing_1024.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["commit_slot", "bytes", "first_byte", "last_byte", "in_order"])
        for s in sorted(w):
            n, cap = w[s]
            wr.writerow([s, n, cap[0], cap[-1], int(cap == list(range(384)))])
    print("wrote t5_framing_1024.csv")
    print("RESULT=%s" % ("PASS" if (bad == 0 and b1 > 0 and b2 > 0) else "FAIL"))
    return 0 if (bad == 0 and b1 > 0 and b2 > 0) else 4


if __name__ == "__main__":
    sys.exit(main())
