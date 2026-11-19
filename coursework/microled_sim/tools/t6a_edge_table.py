#!/usr/bin/env python3
"""Task-book C: an independent 48-edge timing table for two consecutive
transactions, with NO SCLK edge while CS_n is high in between.

Columns per edge: bitcnt BEFORE/AFTER, frozen header, MISO driven for the next
rising edge, mailbox epoch and the captured frame.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t6a_run02_model as M


def main():
    t_half = 50.0
    phase = 0.0
    txns = [(0x001C, 0x1234, 48), (0x801C, 0xFFFFFFFF, 48)]
    labels = ["WRITE 0x001C = 0x1234", "READ  0x001C"]

    ev = []
    t = 0.0
    for ti, (cmd, dat, n) in enumerate(txns):
        t0 = t
        ev.append((t0, 1, 'ncs', None, ti, 0))
        b = M.bits_of(cmd, dat, n)
        for k in range(n):
            tr = t0 + t_half * (2 + 2 * k)
            ev.append((tr, 2, 'psc', b[k], ti, k + 1))
            ev.append((tr + t_half, 2, 'nsc', None, ti, k + 1))
        tcs = t0 + t_half * (2 * n + 2)
        ev.append((tcs, 3, 'pcs', None, ti, 0))
        t = tcs + 200.0
    k = 0
    while phase + 10.0 * k <= t + 50:
        ev.append((phase + 10.0 * k, 0, 'core', None, -1, 0))
        k += 1
    ev.sort(key=lambda e: (e[0], e[1]))

    dut = M.Dut()
    want = {1, 2, 15, 16, 17, 47, 48}
    print("T6-A rev2 / 48-edge table (SCLK 10 MHz, core phase 0 ns)")
    print("CS_n is HIGH between the two transactions and carries NO SCLK edge.")
    print()
    cur = -1
    for (te, _o, kind, pl, ti, le) in ev:
        if kind == 'core':
            dut.core_edge()
            continue
        if ti != cur:
            if cur >= 0:
                print()
            cur = ti
            print("=== transaction %d: %s ===" % (ti, labels[ti]))
            print("edge  t(ns)   bc_before  bc_after  rd_bit  addr    next_miso  epoch  frame")
        if kind == 'ncs':
            dut.negedge_cs()
            print("  CS low      0          0         -       0x0000  -          %d      0x%012X"
                  % (dut.wr_tog, dut.wr_frame))
            continue
        if kind == 'pcs':
            before = dut.bc
            dut.posedge_cs()
            print("  CS high     %-9d 0         %d       0x%04X  -          %d      0x%012X"
                  % (before, dut.hdr_read, dut.rd_addr, dut.wr_tog, dut.wr_frame))
            continue
        if kind == 'psc':
            if le in want:
                print("%4d  %8.1f  %-9d  %-9d  %d       0x%04X  %-9s  %d      0x%012X"
                      % (le, te, dut.bc, dut.bc + 1, dut.hdr_read, dut.rd_addr,
                         "-" if dut.miso() is None else dut.miso(), dut.wr_tog,
                         dut.wr_frame))
            dut.posedge_sclk(pl)
        elif kind == 'nsc':
            dut.negedge_sclk()
    print()
    print("after transaction 1: wr_tog flipped once, wdog = 0x%04X" % dut.regs['wdog'])
    print("after transaction 2: last read snapshot = 0x%08X" % dut.rd_snapshot)
    ok = (dut.regs['wdog'] == 0x1234 and dut.rd_snapshot == 0x1234
          and dut.wr_frames == 1 and dut.mb_lost == 0 and dut.mb_badlen == 0)
    print("RESULT=%s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
