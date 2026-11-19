#!/usr/bin/env python3
"""T6-A 安全再使能 P0：零仿真静态反例推导（不跑 ModelSim）。

对照两版门控：
  CURRENT   hw_blank = blank_r | !en | any_hw_fault
  PROPOSED  hw_blank = blank_r | !en | any_hw_fault | !disp_armed | disp_fault

`disp_armed` 是"Host 显式再使能"锁存：只有一次通过全部条件的 CTRL 写
（EN=1 且 BLANK=0，且 SAFE/READY/无当前故障/无锁存显示故障）才能置 1；
复位、任何当前硬件故障、任一锁存显示故障、EN=0 或 BLANK=1 的写都会清 0。
`disp_fault` = fault_status 去掉 bit8（ERR_REG 是配置访问错误，不熄屏）。

运行 CE1..CE5 与两个负控，输出可复核的时序表。
"""
import sys

FAULT_MASK_DISPLAY = 0x7FF & ~0x100     # all fault bits except ERR_REG (bit8)


def blank_current(en, blank_r, any_hw_fault):
    return int(blank_r or (not en) or any_hw_fault)


def blank_proposed(en, blank_r, any_hw_fault, disp_armed, disp_fault):
    return int(blank_r or (not en) or any_hw_fault or (not disp_armed) or disp_fault)


class Regs:
    """Model of the proposed tcon_spi_regs behaviour (only the safety part)."""

    def __init__(self):
        self.en = 0
        self.blank_r = 1
        self.fault_status = 0
        self.disp_armed = 0

    def hw_blank(self, hw_fault, gate='proposed', neg=None):
        anyf = 1 if hw_fault else 0
        dispf = 1 if (self.fault_status & FAULT_MASK_DISPLAY) else 0
        if gate == 'current':
            return blank_current(self.en, self.blank_r, anyf)
        armed = self.disp_armed
        if neg == 'no_rearm_latch':
            armed = 1                       # latch deleted -> always "armed"
        if neg == 'no_fault_latch':
            dispf = 0                       # sticky history deleted
        return blank_proposed(self.en, self.blank_r, anyf, armed, dispf)

    def core_edge(self, hw_fault, ctrl_write=None, w1c=0, safe=1, ready=0, neg=None):
        """One 100 MHz edge: optional CTRL write / W1C, then fault handling."""
        # W1C on FAULT_STATUS (only clears bits whose source is gone)
        if w1c:
            self.fault_status &= ~(w1c & ~hw_fault)
        # latch live faults
        if hw_fault:
            self.fault_status |= hw_fault

        dispf = 1 if (self.fault_status & FAULT_MASK_DISPLAY) else 0
        if ctrl_write is not None:
            wd = ctrl_write
            en_new = wd & 1
            blank_new = (wd >> 1) & 1
            ok = True
            if en_new and not safe:
                ok = False
            if en_new and not blank_new and not (safe and ready and not hw_fault and not dispf):
                ok = False
            if ok:
                self.en = en_new
                self.blank_r = blank_new if en_new else 1
                if neg != 'no_rearm_latch':
                    self.disp_armed = 1 if (en_new and not blank_new) else 0
        # hardware fault always clears the rearm latch (last assignment wins)
        if neg != 'no_rearm_latch':
            if hw_fault or dispf:
                self.disp_armed = 0


def show(title, rows):
    print(title)
    print("  %-38s %-4s %-6s %-9s %-11s %-11s %-9s" %
          ("step", "en", "blank", "hw_fault", "latched_FAULT", "armed", "hw_blank"))
    for r in rows:
        print("  %-38s %-4d %-6d %-9d %-11s %-11s %-9d" %
              (r[0], r[1], r[2], r[3], r[4], r[5], r[6]))
    print()


def ce1(gate='proposed', neg=None):
    """Display on -> fault for >=1 core edge -> fault source removed, no W1C,
    no new EN command: must STAY dark."""
    d = Regs()
    rows = []
    # bring the panel up legitimately
    d.core_edge(0, ctrl_write=0b11, safe=1, ready=0)          # EN=1, BLANK=1
    d.core_edge(0, ctrl_write=0b01, safe=1, ready=1)          # EN=1, BLANK=0
    rows.append(("A display on", d.en, d.blank_r, 0,
                 1 if d.fault_status else 0, d.disp_armed, d.hw_blank(0, gate, neg)))
    # hardware fault for 3 core edges
    for _ in range(3):
        d.core_edge(0b001)                                    # UVLO present
        d.core_edge(0b001)
    rows.append(("B fault active (3 edges)", d.en, d.blank_r, 1,
                 1 if d.fault_status else 0, d.disp_armed, d.hw_blank(1, gate, neg)))
    # fault source removed, host does nothing
    for _ in range(3):
        d.core_edge(0)
    blank = d.hw_blank(0, gate, neg)
    rows.append(("C fault gone, no W1C, no re-enable", d.en, d.blank_r, 0,
                 1 if d.fault_status else 0, d.disp_armed, blank))
    return rows, blank


def ce2(gate='proposed', neg=None):
    """Fault gone + W1C clears FAULT_STATUS, still no re-enable: must stay dark."""
    d = Regs()
    rows = []
    d.core_edge(0, ctrl_write=0b11, safe=1, ready=0)
    d.core_edge(0, ctrl_write=0b01, safe=1, ready=1)
    d.core_edge(0b010)                                        # OV
    d.core_edge(0b010)
    d.core_edge(0)                                            # source gone
    d.core_edge(0, w1c=0b010)                                 # host clears the bit
    d.core_edge(0)
    blank = d.hw_blank(0, gate, neg)
    rows.append(("D fault gone + W1C cleared, no re-enable", d.en, d.blank_r, 0,
                 1 if d.fault_status else 0, d.disp_armed, blank))
    return rows, blank


def ce3(gate='proposed', neg=None):
    """While a fault is live (or in the same cycle as its W1C) a write of
    CTRL=EN1,BLANK0 must not light the panel."""
    d = Regs()
    rows = []
    d.core_edge(0, ctrl_write=0b11, safe=1, ready=0)
    d.core_edge(0b100)                                        # OT active
    d.core_edge(0b100)
    d.core_edge(0b100, ctrl_write=0b01, safe=1, ready=1)      # try to unblank during OT
    blank = d.hw_blank(0b100, gate, neg)
    rows.append(("E CTRL unblank attempted during OT", d.en, d.blank_r, 1,
                 1 if d.fault_status else 0, d.disp_armed, blank))
    return rows, blank


def ce4(gate='proposed', neg=None):
    """Fault gone + W1C + a fresh explicit EN=1/BLANK=0 with SAFE/READY:
    the permit may return (the frame/precharge key is tcon_top's job)."""
    d = Regs()
    rows = []
    d.core_edge(0, ctrl_write=0b11, safe=1, ready=0)
    d.core_edge(0, ctrl_write=0b01, safe=1, ready=1)
    d.core_edge(0b1000)
    d.core_edge(0)                                            # source gone
    d.core_edge(0, w1c=0b1000)                                # clear status
    d.core_edge(0, ctrl_write=0b01, safe=1, ready=1)          # explicit re-enable
    blank = d.hw_blank(0, gate, neg)
    rows.append(("F cleared + explicit re-enable", d.en, d.blank_r, 0,
                 1 if d.fault_status else 0, d.disp_armed, blank))
    return rows, blank


def ce5(gate='proposed', neg=None):
    """INT_EN=0, a read transaction, a short/over-long frame: none may bypass.

    Structural argument (the gate has no such input) plus a concrete sequence:
    with the rearm latch cleared, nothing except a passing CTRL write sets it.
    """
    d = Regs()
    d.core_edge(0, ctrl_write=0b11, safe=1, ready=0)
    d.core_edge(0, ctrl_write=0b01, safe=1, ready=1)
    d.core_edge(0b10000)                                      # CLOCK_LOST
    d.core_edge(0)
    # read transactions / short frames / INT_EN=0 are modelled as edges with no
    # CTRL write and no W1C: they must leave the latch at 0
    for _ in range(4):
        d.core_edge(0)
    blank = d.hw_blank(0, gate, neg)
    return [], blank


def main():
    fails = []
    print("=== T6-A safety re-arm P0: zero-simulation counterexample derivation ===")
    print("    (no ModelSim; pure static/state model of the two expressions)")
    print()

    rows, b = ce1('current')
    show("[CE1] current gate (hw_blank = blank|!en|hw_fault)", rows)
    cur_ok = (b == 1)
    print("CE1 CURRENT  hw_blank=%d  -> %s" % (b, "SAFE" if cur_ok else "VIOLATION (auto re-enable)"))
    print()

    rows, b = ce1('proposed')
    show("[CE1] proposed gate (+ rearm latch + sticky fault)", rows)
    print("CE1 PROPOSED hw_blank=%d  -> %s" % (b, "SAFE" if b == 1 else "VIOLATION"))
    if b != 1:
        fails.append("CE1")
    print()

    # the crown finding: the current gate really is broken
    if cur_ok:
        fails.append("CE1_CURRENT_SHOULD_VIOLATE")
    print("FINDING: with the current expression the panel is re-enabled with no host")
    print("         action at all (hw_blank 1 -> 0 when hw_fault drops). CONFIRMED.")
    print()

    for name, fn, want, note in (
            ("CE2", ce2, 1, "W1C without re-enable must stay dark"),
            ("CE3", ce3, 1, "unblank during a live fault must be refused"),
            ("CE4", ce4, 0, "cleared + explicit re-enable may light"),
            ("CE5", ce5, 1, "int_en=0 / reads / bad frames cannot bypass")):
        rows, b = fn('proposed')
        if rows:
            show("[%s] proposed gate" % name, rows)
        ok = (b == want)
        print("%s PROPOSED hw_blank=%d (want %d) -> %s   [%s]"
              % (name, b, want, "OK" if ok else "WRONG", note))
        if name == "CE2":
            _, bc = ce2('current')
            print("CE2 CURRENT  hw_blank=%d -> %s" % (bc, "SAFE" if bc == 1 else "VIOLATION"))
            if bc != 1:
                print("            (clearing the status alone also re-enabled display)")
        print()
        if not ok:
            fails.append(name)

    print("--- negative controls (the proposed gate must be able to fail) ---")
    # CE2 is where the rearm latch is the ONLY lock left (the W1C already
    # cleared the sticky bit), so deleting that latch has to show up there.
    _, n1 = ce2('proposed', neg='no_rearm_latch')
    print("NC-A delete the rearm latch     CE2 hw_blank=%d -> %s"
          % (n1, "detected" if n1 == 0 else "NOT DETECTED"))
    if n1 != 0:
        fails.append("NC-A")
    # deleting both locks reduces the gate to the RUN02 expression, which is
    # exactly the design the review rejected: CE1 has to fail there.
    d = Regs()
    d.core_edge(0, ctrl_write=0b11, safe=1, ready=0)
    d.core_edge(0, ctrl_write=0b01, safe=1, ready=1)
    d.core_edge(0b001); d.core_edge(0b001)
    d.core_edge(0); d.core_edge(0)
    n2 = blank_current(d.en, d.blank_r, 0)
    print("NC-B both locks deleted         CE1 hw_blank=%d -> %s"
          % (n2, "detected" if n2 == 0 else "NOT DETECTED"))
    if n2 != 0:
        fails.append("NC-B")
    print()
    print("   note: the sticky-fault term and the rearm latch overlap on CE1.")
    print("   CE2 (fault cleared by W1C, no re-enable) is covered by the latch")
    print("   alone; the sticky term additionally covers a stale/incorrect latch,")
    print("   which is exactly the RUN02 failure mode. Keeping both is deliberate.")

    print("--- what is NOT proven here ---")
    print("CE4's 'non-zero light output' needs the Data/Scan frame permit and a")
    print("real simulation; this model only proves the BLANK permit returns.")
    print("CE6 (clock phase / async reset corner) is a planned test, not run.")
    print()

    if fails:
        print("RESULT=FAIL (%s)" % ", ".join(fails))
        return 1
    print("RESULT=PASS  CE1..CE5 hold on the proposed gate; the current gate is")
    print("             confirmed to auto re-enable (CE1 CURRENT = VIOLATION).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
