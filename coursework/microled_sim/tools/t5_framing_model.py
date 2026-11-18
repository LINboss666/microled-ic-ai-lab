#!/usr/bin/env python3
"""T5-B framing model: cycle-accurate model of tcon_data_tx + data_driver framing.

Two free parameters that the RTL itself does not spell out and that decide
whether byte 0 of a 384-byte transfer is really byte 0:

  phase : dclk_r during slot cycle 0 (0 = low, 1 = high). Set by the edge on
          which mode_en rises; the TB can choose it.
  conv  : what the Data chip sees at a DCLK rising edge that starts cycle g -
          'post' sees LATCH(g)   (post-edge value, i.e. the value in cycle g)
          'pre'  sees LATCH(g-1) (pre-edge value)

The archival T3 evidence decides `conv`: in t3_run04 the commit (LATCH rising
at cycle 828) cleared dut.wcnt at the edge starting cycle 828, which is only
possible with 'post'.

The model then checks, for every slot parity, how many of the 384 captured
bytes are the right ones.
"""
import sys

NCH = 384
LOAD_START = 832
LOAD_LEN = 768


def slot_lengths(n):
    out, frac, ln = [], 576, 976
    for _ in range(n):
        out.append(ln)
        frac, ln = ((frac + 576 - 1024), 977) if (frac + 576) >= 1024 else ((frac + 576), 976)
    return out


def run(phase, conv, nslots=8):
    lens = slot_lengths(nslots)
    # absolute cycle -> (slot, slot_cycle)
    abs2 = []
    base = 0
    for s, ln in enumerate(lens):
        for c in range(ln):
            abs2.append((s, c))
        base += ln
    total = len(abs2)
    dclk = lambda g: (g + phase) % 2          # dclk_r during cycle g

    # ---- tcon_data_tx state (mirrors the RTL's single negedge block) ----
    prefetched = False
    launched = 0          # bytes put on the bus (1 after the pre-fetch)
    tx_k = 0
    bus = -1              # byte index currently on the bus
    load_run = False
    load_cnt = 0

    # ---- data_driver state --------------------------------------------
    armed = False
    latch_d = False
    wcnt = 0
    cap = []
    windows = {}

    for g in range(total):
        s, sc = abs2[g]
        L = 1 if (828 <= sc < 832) else 0

        # ================= clk posedge starting cycle g ==================
        rising = (g > 0) and (dclk(g - 1) == 0) and (dclk(g) == 1)
        if rising:
            if conv == 'post':
                seen = L
            else:
                seen = 1 if (0 <= (sc - 1) < (lens[s]) and 828 <= (sc - 1) < 832) else 0
            did_capture = True
            if seen and not latch_d:                 # rising LATCH  -> commit
                if armed:
                    windows[s] = (wcnt, list(cap))
                armed = False
                wcnt = 0
                cap = []
                did_capture = False                  # win_open = 0 on this edge
            elif (not seen) and latch_d:             # falling LATCH -> open
                armed = True
                wcnt = 0
                cap = []
            latch_d = seen
            if armed and wcnt < NCH and did_capture:
                cap.append(bus)
                wcnt += 1

        # ================= clk negedge inside cycle g ===================
        # the RTL is ONE negedge chain: reset-point / pre-fetch / launch
        if sc == (LOAD_START - 2):                       # NOT gated by dclk_r
            prefetched = False
            launched = 0
            tx_k = 0
            bus = -1
        elif (sc == (LOAD_START - 1) or sc == LOAD_START) and dclk(g) == 0 and not prefetched:
            prefetched = True
            launched = 1
            tx_k = 0
            bus = 0
        elif load_run and dclk(g) == 0 and prefetched and (launched <= NCH - 1) and (tx_k != NCH - 1):
            tx_k += 1
            launched += 1
            bus = tx_k

        # load window counter: set on cycle LOAD_START-1, 768 cycles long
        if sc == (LOAD_START - 1):
            load_run = True
            load_cnt = 0
        elif load_run:
            if load_cnt == LOAD_LEN - 1:
                load_run = False
            else:
                load_cnt += 1

    return windows


def report(tag, windows):
    bad = 0
    detail = []
    for s in sorted(windows):
        n, cap = windows[s]
        ok = (n == NCH) and (cap == list(range(NCH)))
        if not ok:
            bad += 1
            detail.append((s, n, cap[:6], cap[-3:]))
    print("%-28s windows=%d bad=%d" % (tag, len(windows), bad))
    for d in detail[:6]:
        print("    slot=%d bytes=%d first=%s last=%s" % d)
    return bad


if __name__ == "__main__":
    print("=== framing model: 8 slots (mixed 976/977) ===")
    for phase in (0, 1):
        for conv in ('post', 'pre'):
            w = run(phase, conv)
            report("phase=%d conv=%s" % (phase, conv), w)
    print("\nlegend: phase = dclk_r during slot cycle 0; conv = LATCH value seen "
          "at a DCLK rising edge")
    sys.exit(0)
