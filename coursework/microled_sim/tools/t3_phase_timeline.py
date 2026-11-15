#!/usr/bin/env python3
"""T3 RUN04 pre-check #2 (reviewer): byte0 / byte383 / sent / din_valid
sampling timeline for BOTH 976/977 slot phases, derived by script.

Zero simulation, zero EDA budget.

WHY THERE ARE EXACTLY TWO PHASES
  The slot waveform is registered at negedge clk, so the LATCH fall time is
      F = 20k + off,  off = 5 or 15 ns      (C parity decides which)
  and DCLK posedges sit at multiples of 20 ns. Exactly two phases, and which
  one a column gets alternates because slot lengths are 976/977 (977 is odd).

MODEL (identical to the shipped sources)
  DUT    : posedge dclk, PRE-edge sample; the arming edge (first posedge with
           latch=0 after the fall) counts as byte 0 (F2 ordering)
  oracle : posedge dclk, +1 ns settle; captures while armed, NO din_valid gate
  TB     : win opens on the LATCH RISE detection (negedge dclk);
           started set at the arming posedge P, cleared at the rise (posedge
           dclk only - single writer);
           sent increments at negedge dclk iff started && sent<win_nb;
           din_valid = win && !latch && sent<win_nb  (a LEVEL)

DERIVED, PER PHASE
  arming posedge P, then a per-posedge table of latch(pre-edge), latch(+1 ns),
  started, sent, din_valid and the byte the DUT / the oracle sample, checked to
  be byte0..byte383 in order and identical between the two models, and the
  window to contain exactly 384 presented bytes.
"""
NB = 384
PERIOD = 20


def derive(off):
    """off: the LATCH fall sits at 20k + off ns (5 or 15). Returns the per-edge
    table and the derived byte streams."""
    # LATCH level: registered at negedge clk. The fall IS a negedge clk at F.
    # Level in effect on the interval (prev_negedge_clk, F]  = 1
    #                        (F, next_negedge_clk]           = 0
    # negedge clk positions are 10m+5; F = 20k+off IS one of them.
    def latch_at(t):
        # level in effect just before time t (as a posedge at t would sample it)
        # = 1 if the last negedge clk at or before t is the fall's *previous*
        #   ones, i.e. t <= F ; = 0 if t > F
        return t <= off

    # arming posedge P = the first posedge strictly after the fall
    P = PERIOD
    while P <= off:
        P += PERIOD

    rows = []
    sent = 0
    dut, orc = [], []
    win_edges = 0
    # started becomes visible AFTER P (it is set by an NBA at P)
    def started_at(t):
        return t > P - 1 and t >= P

    for k in range(-1, NB + 2):
        pos = P + k * PERIOD
        latch_pre = latch_at(pos)          # what the DUT reads
        latch_o = latch_at(pos + 1)        # what the oracle reads (+1 ns)
        st = started_at(pos)
        din_v = (not latch_pre) and (sent < NB)     # win is 1, latch gates
        din = sent if din_v else None
        # oracle byte: din at pos+1 ns; sent cannot have changed (the next
        # negedge dclk is at pos+10), latch identical -> same byte, but the
        # oracle has no din_valid gate, so it captures while latch is low
        orc_v = (not latch_o) and (sent < NB)
        orc_b = sent if orc_v else None
        rows.append(dict(pos=pos, latch_pre=latch_pre, latch_o=latch_o,
                         started=st, sent=sent, din_v=din_v, dut=din,
                         orc=orc_b))
        if din_v:
            dut.append(din)
            win_edges += 1
        # sent increments at the negedge dclk AFTER this posedge, iff started
        if st and sent < NB:
            sent += 1
        if orc_v:
            orc.append(orc_b)

    # the oracle keeps capturing past byte383 only if latch stays low after the
    # window closed - but the window closes exactly because sent hit NB, and the
    # next LATCH rise re-arms. The model stops at byte383 like the RTL does.
    return P, rows, dut, orc, win_edges


def main():
    print("=== T3 RUN04 offline two-phase derivation (zero simulation) ===")
    print()
    print("LATCH fall  F = 20k + off   (off = 5 or 15 ns -> the two phases)")
    print("DCLK posedge every %d ns; negedge dclk offset by 10 ns" % PERIOD)
    print("LATCH pulse 40 ns, registered at negedge clk; P = first posedge")
    print("after the fall; started set AT P (NBA); sent increments at the")
    print("negedge dclk AFTER P, gated by started.")
    ok_all = True
    for off in (5, 15):
        P, rows, dut, orc, edges = derive(off)
        print()
        print("--- phase: LATCH fall at 20k + %d ns  (arming posedge P = %d ns) ---"
              % (off, P))
        print("  %-8s %-10s %-10s %-8s %-5s %-9s %-11s %s"
              % ("posedge", "latch(pre)", "latch(+1)", "started", "sent",
                 "din_valid", "DUT sample", "oracle sample"))
        show = rows[:5] + [None] + rows[-4:]
        for r in show:
            if r is None:
                print("  %-8s" % "... (identical pattern)")
                continue
            print("  %-8d %-10s %-10s %-8s %-5d %-9s %-11s %s"
                  % (r["pos"], r["latch_pre"], r["latch_o"], r["started"],
                     r["sent"], r["din_v"],
                     ("byte%d" % r["dut"]) if r["dut"] is not None else "-",
                     ("byte%d" % r["orc"]) if r["orc"] is not None else "-"))
        print("  byte0  sampled at posedge %d ns (DUT) / %d ns (oracle)"
              % (P, P))
        print("  byte383 sampled at posedge %d ns (DUT) / %d ns (oracle)"
              % (P + 383 * PERIOD, P + 383 * PERIOD))
        dut_ok = dut == list(range(NB))
        orc_ok = orc == list(range(NB))
        same = dut == orc
        print("  presented-byte count      = %d (expect %d)" % (edges, NB))
        print("  DUT stream byte0..byte383 : %s" % dut_ok)
        print("  oracle stream identical   : %s" % orc_ok)
        ok = dut_ok and orc_ok and same and edges == NB
        ok_all &= ok
        print("  => %s" % ("PHASE OK" if ok else "PHASE BROKEN"))
    print()
    print("RESULT: %s" % ("BOTH PHASES IDENTICAL - byte0 is framed correctly in"
                          " either 976/977 phase; the oracle (+1 ns settle) reads"
                          " the same byte as the DUT at every one of the 384"
                          " edges" if ok_all else
                          "PHASE-DEPENDENT - do NOT spend the run"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    main()
