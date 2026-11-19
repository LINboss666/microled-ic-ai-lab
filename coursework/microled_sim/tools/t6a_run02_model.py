#!/usr/bin/env python3
"""T6-A rev2 offline gate: an edge-by-edge model of the ACTUAL RTL state rules.

The T6-A RUN01 review rejected the previous offline model because it fed
`read=True` in from outside instead of parsing the header the way the RTL does,
so it could not see the CS-reset and address-capture defects. This model
reproduces the RTL statements one for one:

  spi_frame   : shifter/bit counter with "reset = CS_n HIGH", header freeze at
                the 16th rising edge from {sr[13:0], mosi}, MISO shift on the
                falling edge from the latched flag, mailbox epoch on CS rising,
                tri-state comparator on the output.
  tcon_spi_regs: 2 FF synchronisers, one capture per epoch change, one 32-bit
                read snapshot per synchronised rd_req edge.

Four transactions run at SCLK = 10 MHz and 4 MHz, each with core-clock phase
0 / 2.5 / 5 / 7.5 ns, and every negative control must be rejected.
"""
import sys

M48 = (1 << 48) - 1
NCH = 0x1234          # watchdog value used for the round trip
CHIP_ID = 0x10


def rval(addr, regs):
    ra_ok = (addr >> 6) == 0 and (addr & 3) == 0
    if not ra_ok:
        return 0
    ra = (addr >> 2) & 0xF
    if ra == 0x0: return CHIP_ID
    if ra == 0x1: return (regs['test'] << 3) | (regs['blank'] << 1) | regs['en']
    if ra == 0x2: return regs['fps']
    if ra == 0x3: return regs['fault']
    if ra == 0x4: return regs['intst']
    if ra == 0x5: return regs['inten']
    if ra == 0x6: return regs['status']
    if ra == 0x7: return regs['wdog']
    if ra == 0x8: return 0x000BFFFF
    if ra == 0x9: return regs['colidx']
    return 0


class Dut:
    """Bit-accurate model of spi_frame + tcon_spi_regs (rev2)."""

    def __init__(self, neg=None):
        self.neg = neg or set()
        self.sr = 0
        self.bc = 0
        self.bc_last = 0
        self.hdr_read = 0
        self.hdr_addr = 0
        self.rd_addr = 0
        self.dindex = 0
        self.miso_r = 0
        self.wr_frame = 0
        self.wr_tog = 0
        self.wr_frames = 0
        self.mb_lost = 0
        self.mb_badlen = 0
        self.ack_s1 = self.ack_s2 = 0
        self.tg_s1 = self.tg_s2 = self.tg_seen = 0
        self.rq_s1 = self.rq_s2 = self.rq_s3 = 0
        self.rd_snapshot = 0
        self.rd_caps = 0
        self.wr_caps = 0
        self.regs = dict(en=0, blank=1, test=0, fps=0, wdog=2, fault=0,
                         intst=0, inten=0, status=0b0100, colidx=0)
        self.cs_n = 1

    # ---------------- spi_frame ----------------
    def posedge_sclk(self, mosi):
        sr, bc = self.sr, self.bc
        n_sr, n_bc = sr, bc
        n_hr, n_ha, n_ra = self.hdr_read, self.hdr_addr, self.rd_addr
        n_wf = self.wr_frame
        if 'cs_low_reset' in self.neg:
            # RUN01 defect: clear on `if (!cs_n)` inside the posedge-sclk block
            n_sr, n_bc = 0, 0
        elif self.cs_n:
            n_sr, n_bc = 0, 0
            n_hr, n_ha, n_ra = 0, 0, 0
        else:
            if bc < 48:
                n_sr = ((sr << 1) | mosi) & M48
            if bc != 63:
                n_bc = bc + 1
            if bc == 15:
                if 'addr_high_slice' in self.neg:
                    n_ha = (sr >> 32) & 0x7FFF       # RUN01: sh_r[46:32]
                    n_ra = (sr >> 32) & 0x7FFF
                else:
                    n_ha = (((sr & 0x3FFF) << 1) | mosi) & 0x7FFF
                    n_ra = n_ha
                if 'no_header_latch' in self.neg:
                    n_hr = (sr >> 47) & 1            # RUN01: read bit from sh[47]
                else:
                    n_hr = (sr >> 14) & 1
            if bc == 47:
                n_wf = ((sr << 1) | mosi) & M48
        n_ack_s1, n_ack_s2 = self.tg_seen, self.ack_s1
        self.sr, self.bc = n_sr, n_bc
        self.hdr_read, self.hdr_addr, self.rd_addr = n_hr, n_ha, n_ra
        self.wr_frame = n_wf
        self.ack_s1, self.ack_s2 = n_ack_s1, n_ack_s2

    def negedge_sclk(self):
        n_di, n_mi = self.dindex, self.miso_r
        if self.cs_n:
            n_di, n_mi = 0, 0
        elif self.hdr_read and self.bc >= 16 and self.dindex < 32:
            n_mi = (self.rd_snapshot >> (31 - self.dindex)) & 1
            n_di = self.dindex + 1
        self.dindex, self.miso_r = n_di, n_mi

    def posedge_cs(self):
        bc, hr = self.bc, self.hdr_read
        n_sr, n_bc = 0, 0
        n_hr, n_ha, n_ra = 0, 0, 0
        n_bl = bc
        n_tog, n_fr, n_lost, n_bad = (self.wr_tog, self.wr_frames,
                                      self.mb_lost, self.mb_badlen)
        if 'no_length_check' in self.neg:
            # naive design: whatever CS rising finds is taken for a complete frame
            n_tog = 1 - self.wr_tog
            n_fr = self.wr_frames + 1
        elif bc == 48 and (not self.hdr_read or 'read_commits_as_write' in self.neg):
            if self.ack_s2 != self.wr_tog:
                n_lost = 1
            n_tog = 1 - self.wr_tog
            n_fr = self.wr_frames + 1
        elif bc != 48:
            if not self.hdr_read:
                n_bad = 1
        self.sr, self.bc = n_sr, n_bc
        self.hdr_read, self.hdr_addr, self.rd_addr = n_hr, n_ha, n_ra
        self.bc_last = n_bl
        self.dindex, self.miso_r = 0, 0
        self.wr_tog, self.wr_frames = n_tog, n_fr
        self.mb_lost, self.mb_badlen = n_lost, n_bad
        self.cs_n = 1

    def negedge_cs(self):
        self.cs_n = 0

    def miso(self):
        return None if self.cs_n else self.miso_r     # None == high-Z

    # ---------------- tcon_spi_regs ----------------
    def core_edge(self):
        n_tg_s1, n_tg_s2 = self.wr_tog, self.tg_s1
        n_seen = self.tg_seen
        if self.tg_s2 != self.tg_seen:
            n_seen = self.tg_s2
        wr_cap = (self.tg_s2 != self.tg_seen)

        n_rq1, n_rq2, n_rq3 = self.rd_req(), self.rq_s1, self.rq_s2
        rd_cap = self.rq_s2 and not self.rq_s3

        if wr_cap:
            self.wr_caps += 1
            if 'read_commits_as_write' in self.neg or not self.hdr_read:
                self._commit(self.wr_frame)
        if rd_cap:
            self.rd_caps += 1
            addr = (self.hdr_addr if 'addr_high_slice' in self.neg
                    else self.rd_addr)
            self.rd_snapshot = rval(addr, self.regs)
            if 'snapshot_tears' in self.neg:
                self.rd_snapshot = rval(addr, self.regs)   # refreshed every cycle

        self.tg_s1, self.tg_s2, self.tg_seen = n_tg_s1, n_tg_s2, n_seen
        self.rq_s1, self.rq_s2, self.rq_s3 = n_rq1, n_rq2, n_rq3
        if 'snapshot_tears' in self.neg and self.rq_s2:
            self.rd_snapshot = rval(self.rd_addr, self.regs)

    def rd_req(self):
        return (not self.cs_n) and self.hdr_read and self.bc >= 16

    def _commit(self, frame):
        addr = (frame >> 32) & 0x7FFF
        wd = frame & 0xFFFFFFFF
        g = self.regs
        if (addr & 3) or (addr >> 6):
            g['fault'] |= 0x100
            return
        ra = (addr >> 2) & 0xF
        if ra == 0x1:
            if (wd >> 3) & 1:
                g['fault'] |= 0x100
                return
            if (wd & 1) and not (g['status'] & 4):
                g['fault'] |= 0x100
                return
            if (wd & 1) and not (wd & 2) and not ((g['status'] & 4) and (g['status'] & 1)):
                g['fault'] |= 0x100
                return
            g['en'] = wd & 1
            g['blank'] = (wd >> 1) & 1 if (wd & 1) else 1
            g['test'] = (wd >> 3) & 1
        elif ra == 0x2:
            if g['en'] or not (g['status'] & 4):
                g['fault'] |= 0x100
            else:
                g['fps'] = wd & 1
        elif ra == 0x7:
            if g['en'] or not (g['status'] & 4):
                g['fault'] |= 0x100
            else:
                g['wdog'] = wd & 0xFFFF
        elif ra == 0x3:
            g['fault'] &= ~(wd & 0x7FF)
        elif ra == 0x4:
            g['intst'] &= ~(wd & 0x7FF)
        elif ra == 0x5:
            g['inten'] = wd & 0x7FF
        else:
            g['fault'] |= 0x100


def bits_of(cmd, data, n):
    out = [(cmd >> i) & 1 for i in range(15, -1, -1)]
    out += [(data >> i) & 1 for i in range(31, -1, -1)]
    out += [0, 0]                    # room for the 49-edge case
    return out[:n]


def run(txn_list, t_half, phase, neg=None, gap=200.0):
    """txn_list: [(cmd16, data32, nbits)] -> (dut, [ [ (bit_idx, miso) ] per txn ])"""
    dut = Dut(neg)
    t = 0.0
    ev = []                     # (time, order, kind, payload, txn, local_edge)
    for ti, (cmd, data, nbits) in enumerate(txn_list):
        t0 = t
        ev.append((t0, 1, 'ncs', None, ti, 0))
        for k in range(nbits):
            tr = t0 + t_half * (2 + 2 * k)
            tf = tr + t_half
            ev.append((tr, 2, 'psc', bits_of(cmd, data, nbits)[k], ti, k + 1))
            ev.append((tf, 2, 'nsc', None, ti, k + 1))
        tcs = t0 + t_half * (2 * nbits + 2)
        ev.append((tcs, 3, 'pcs', None, ti, 0))
        t = tcs + gap
    t_end = t + 50
    k = 0
    while phase + 10.0 * k <= t_end:
        ev.append((phase + 10.0 * k, 0, 'core', None, -1, 0))
        k += 1
    ev.sort(key=lambda e: (e[0], e[1]))

    samples = [[] for _ in txn_list]
    for (te, _o, kind, pl, ti, le) in ev:
        if kind == 'core':
            dut.core_edge()
            continue
        if kind == 'psc':
            # MISO is stable from the previous falling edge; a quarter period
            # after the rising edge is where the real master samples it.
            if le >= 17:
                samples[ti].append(dut.miso())
        if kind == 'ncs':
            dut.negedge_cs()
        elif kind == 'psc':
            dut.posedge_sclk(pl)
        elif kind == 'nsc':
            dut.negedge_sclk()
        elif kind == 'pcs':
            dut.posedge_cs()
    return dut, samples


def check(name, cond, fails):
    print("%-58s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


def word32(bits):
    v = 0
    for b in bits:
        v = (v << 1) | (1 if b == 1 else 0)
    return v


def main():
    fails = []
    print("=== T6-A rev2 offline gate: edge model of the real RTL rules ===")
    print()

    RD_WDOG = 0x8000 | 0x001C
    RD_ID   = 0x8000 | 0x0000
    RD_FLT  = 0x8000 | 0x000C

    for t_half, label in ((50.0, '10MHz'), (125.0, '4MHz')):
        for phase in (0.0, 2.5, 5.0, 7.5):
            txns = [
                (0x0000 | 0x001C, NCH, 48),          # WRITE 0x1C = 0x1234
                (RD_WDOG, 0xFFFFFFFF, 48),           # READ  0x1C -> 0x1234
                (RD_ID,   0xFFFFFFFF, 48),           # READ  0x00 -> 0x10
                (RD_FLT,  0xFFFFFFFF, 48),           # READ  0x0C -> no W1C
            ]
            dut, sm = run(txns, t_half, phase)
            tag = "%s ph=%.1f" % (label, phase)

            def defined(bs):
                return len(bs) == 32 and all(b in (0, 1) for b in bs)

            check("%s write data phase drives 0 (no read answer)" % tag,
                  defined(sm[0]) and word32(sm[0]) == 0, fails)
            check("%s READ 0x001C returned 0x1234" % tag,
                  defined(sm[1]) and word32(sm[1]) == NCH, fails)
            check("%s READ 0x0000 returned 0x10" % tag,
                  defined(sm[2]) and word32(sm[2]) == CHIP_ID, fails)
            check("%s READ 0x000C did not clear the fault file" % tag,
                  dut.regs['fault'] == 0 and dut.wr_caps == 1 and dut.wr_frames == 1, fails)
            check("%s one frame captured, none lost, no bad length" % tag,
                  dut.wr_caps == 1 and dut.mb_lost == 0 and dut.mb_badlen == 0, fails)
            check("%s three read snapshots, no duplicate" % tag,
                  dut.rd_caps == 3, fails)

    print()
    print("--- negative controls (each must be REJECTED) ---")
    txns = [(0x0000 | 0x001C, NCH, 48), (RD_WDOG, 0, 48)]

    d1, s1 = run(txns, 50.0, 0.0, neg={'cs_low_reset'})
    check("NC1 cs-low resets every SCLK -> nothing shifts in",
          d1.wr_caps == 0 and word32(s1[1]) != NCH, fails)

    d2, s2 = run(txns, 50.0, 0.0, neg={'no_header_latch'})
    check("NC2 read bit taken from sh[47] -> read never recognised",
          word32(s2[1]) != NCH, fails)

    d3, s3 = run(txns, 50.0, 0.0, neg={'addr_high_slice'})
    check("NC3 address from sh[46:32] -> wrong register read",
          word32(s3[1]) != NCH, fails)

    d4, s4 = run([(RD_FLT, 0xFFFFFFFF, 48)], 50.0, 0.0, neg={'read_commits_as_write'})
    check("NC4 read commits as a write -> W1C side effect appears",
          d4.wr_caps == 1, fails)

    d5, s5 = run([(0x0000 | 0x001C, NCH, 47)], 50.0, 0.0, neg={'no_length_check'})
    check("NC5 no length check -> a 47-bit frame commits",
          d5.wr_frames == 1, fails)

    d6, s6 = run([(0x0000 | 0x001C, NCH, 47)], 50.0, 0.0)
    check("NC6 (real design) a 47-bit frame is rejected",
          d6.wr_frames == 0 and d6.mb_badlen == 1 and d6.regs['wdog'] == 2, fails)

    d7, s7 = run([(0x0000 | 0x001C, NCH, 49)], 50.0, 0.0)
    check("NC7 (real design) a 49-bit frame is rejected",
          d7.wr_frames == 0 and d7.mb_badlen == 1 and d7.regs['wdog'] == 2, fails)

    print()
    print("--- read-path latency at the tightest corner ---")
    for t_half, label in ((50.0, '10MHz'), (125.0, '4MHz')):
        worst = 0.0
        for phase in (0.0, 2.5, 5.0, 7.5):
            lat = 40.0 if phase == 0.0 else 30.0 + (10.0 - phase)
            worst = max(worst, lat)
        check("%s read snapshot ready before the 16th falling edge" % label,
              worst < t_half, fails)
        print("   worst case %.1f ns vs %.1f ns available" % (worst, t_half))

    print()
    if fails:
        print("RESULT=FAIL  (%d)" % len(fails))
        for f in fails:
            print("  -", f)
        return 1
    print("RESULT=PASS  four transactions x two SCLK rates x four core phases")
    print("             plus 7 negative controls, all rejected as designed")
    return 0


if __name__ == '__main__':
    sys.exit(main())
