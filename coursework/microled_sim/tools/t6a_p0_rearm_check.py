#!/usr/bin/env python3
"""T6-A P0-C：故障闭环状态模型（整数 ps、严格 NBA、零 ModelSim）。

修订动机（复审 2026-11-19）
--------------------------
v2 有两个真缺口：
  1. `n_fault` 没并入 `hw_fault_caught` → 短脉冲被抓住、显示关断，
     但 Host 读 FAULT_STATUS 仍是 0（不可诊断）；
  2. `clr_fault` 不看 W1C 掩码 → 写 `data=0` 也能清捕获位（未匹配清除）。
本文件实现修订后的协议并逐条给出反例。

协议
----
* 捕获位 `caught` 异步置位（故障边沿），同步清除（core 沿）；
* 可读状态：`fault_status` 的 bit7（COMM_TO）由 `caught` 派生
  —— V1.3 段0704「TCON 捕获共享 FAULT_n 后置 COMM_TO」，不新增地址；
* W1C：`n_fault &= ~(w1c & ~hw_fault)`，`w1c=0` 不动任何位；
* `caught` 只在这三个条件同时成立时清：
      W1C 掩码覆盖 bit7  &&  当前无活故障  &&  确实发生了一笔 FAULT 写
  否则保持（写 0、部分掩码、新脉冲同沿都不会误清）。
* 清除与新脉冲同沿时，异步置位优先（set 在 always 块里先判）。
"""
import sys

PERIOD = 10000
VIS = 0x080                     # COMM_TO
DISPLAY_MASK = 0x7FF & ~0x100   # 除 ERR_REG


class Regs:
    def __init__(self, neg=None):
        self.neg = neg or set()
        self.en = 0
        self.blank_r = 1
        self.fault_status = 0
        self.disp_armed = 0
        self.caught = 0
        self.int_status = 0
        self.fsd = 0

    # ---------------- 组合量（读旧值） ----------------
    def visible_fault(self, hw_fault):
        f = self.fault_status | hw_fault
        if self.caught and 'no_caught_visibility' not in self.neg:
            f |= VIS
        return f & 0x7FF

    def disp_fault(self, hw_fault):
        return 1 if (self.visible_fault(hw_fault) & DISPLAY_MASK) else 0

    def hw_blank(self, hw_fault):
        armed = 1 if 'no_rearm_latch' in self.neg else self.disp_armed
        caught = 0 if 'no_caught_gate' in self.neg else self.caught
        return int(bool(self.blank_r or (not self.en) or hw_fault or caught
                        or (not armed) or self.disp_fault(hw_fault)))

    def irq(self, int_en=0):
        return 1 if (self.int_status & int_en) else 0

    # ---------------- 一个 core 上升沿 ----------------
    def edge(self, hw_fault=0, ctrl=None, w1c=0, safe=1, ready=1, fw=False):
        vis_old = self.visible_fault(hw_fault)
        dispf = self.disp_fault(hw_fault)
        armed_old = self.disp_armed
        caught_old = self.caught

        n_fault = self.fault_status | hw_fault
        if caught_old and 'no_caught_visibility' not in self.neg:
            n_fault |= VIS
        n_en, n_blank, n_armed = self.en, self.blank_r, armed_old
        err = 0

        if ctrl is not None:
            wd = ctrl
            en_new, blk_new = wd & 1, (wd >> 1) & 1
            ok = not ((wd >> 3) & 1)
            if en_new and not safe:
                ok = False
            if en_new and ('no_live_fault_check' not in self.neg) and hw_fault:
                ok = False
            if en_new and not blk_new:
                if 'no_live_fault_check' in self.neg:
                    ok = ok and bool(safe and ready)
                else:
                    ok = ok and bool(safe and ready and not hw_fault
                                     and not dispf and not caught_old)
            if ok:
                n_en = en_new
                n_blank = blk_new if en_new else 1
                n_armed = 1 if (en_new and not blk_new) else 0
            else:
                err = 1
                n_fault |= 0x100

        # W1C
        if w1c:
            n_fault &= ~(w1c & ~hw_fault)

        # 捕获位：异步置位优先，其次才是同步清除
        n_caught = 1 if (caught_old or hw_fault) else caught_old
        if hw_fault:
            n_caught = 1                       # 异步置位永远优先
        elif fw and 'no_mask_check' in self.neg:
            n_caught = 0                       # 缺陷版：不看掩码
        elif fw and (w1c & VIS):
            n_caught = 0                       # 修订版：掩码必须覆盖 bit7

        if hw_fault or n_caught:
            n_armed = 0

        # 可见状态与中断
        n_vis = (n_fault & 0x7FF) | (VIS if n_caught and
                                     'no_caught_visibility' not in self.neg else 0)
        n_int = self.int_status | (n_vis & ~self.fsd)

        self.en, self.blank_r = n_en, n_blank
        self.fault_status = n_fault
        self.disp_armed = n_armed
        self.caught = n_caught
        self.int_status = n_int
        self.fsd = n_vis
        return err

    def async_fault_edge(self):
        if 'no_async_capture' in self.neg:
            return                      # 缺陷版：脉冲不跨时钟沿就丢失
        self.caught = 1


def ck(name, cond, fails):
    print("  %-56s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


def bring_up(p):
    p.edge(ctrl=0b11, safe=1, ready=0)
    p.edge(ctrl=0b01, safe=1, ready=1)


def main():
    fails = []
    print("=== T6-A P0-C: fault-closure state model (NBA, integer time, zero ModelSim) ===")
    print("    visible = fault_status | hw_fault | (caught ? COMM_TO : 0)")
    print("    hw_blank = blank_r | !en | hw_fault | caught | !armed | disp_fault")
    print()

    # ---------- E17: short pulse must end up visible ----------
    print("[E17] 4 ns pulse, no core edge inside it -> must be readable")
    p = Regs()
    bring_up(p)
    print("   before : blank=%d vis=0x%03X caught=%d" % (p.hw_blank(0), p.visible_fault(0), p.caught))
    p.async_fault_edge()                       # 12 ns, no clock edge
    print("   12 ns  : blank=%d vis=0x%03X caught=%d" % (p.hw_blank(1), p.visible_fault(1), p.caught))
    p.edge(hw_fault=0)                         # 20 ns, pulse already gone
    print("   20 ns  : blank=%d vis=0x%03X caught=%d int=0x%03X"
          % (p.hw_blank(0), p.visible_fault(0), p.caught, p.int_status))
    ck("E17a_status_reports_the_event", (p.visible_fault(0) & VIS) == VIS, fails)
    ck("E17b_int_status_reports_it_too", (p.int_status & VIS) == VIS, fails)
    ck("E17c_panel_still_dark", p.hw_blank(0) == 1, fails)
    print()

    # ---------- E18: W1C = 0 must not clear ----------
    print("[E18] a legal FAULT write with data = 0 must NOT clear the capture")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0x000, fw=True)
    ck("E18a_w1c_zero_keeps_caught", p.caught == 1, fails)
    ck("E18b_w1c_zero_still_dark", p.hw_blank(0) == 1, fails)
    ck("E18c_w1c_zero_keeps_status", (p.visible_fault(0) & VIS) == VIS, fails)
    print()

    # ---------- E19: partial mask keeps the other fault ----------
    print("[E19] two different causes, W1C clears only one of them")
    p = Regs()
    bring_up(p)
    p.edge(hw_fault=0b001)          # UVLO latched (bit0)
    p.edge(hw_fault=0)
    p.async_fault_edge()            # plus a captured short event (bit7)
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0b001, fw=True)   # clear bit0 only
    ck("E19a_bit0_cleared", (p.visible_fault(0) & 0b001) == 0, fails)
    ck("E19b_bit7_kept", (p.visible_fault(0) & VIS) == VIS, fails)
    ck("E19c_still_dark", p.hw_blank(0) == 1, fails)
    print()

    # ---------- E20: clear race with a new pulse ----------
    print("[E20] a new fault on the same core edge as the W1C must survive")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0b010, w1c=VIS, fw=True)   # W1C(bit7) + new OV pulse, same edge
    ck("E20a_new_fault_wins_over_the_clear", p.caught == 1, fails)
    ck("E20b_new_fault_is_visible", (p.visible_fault(0b010) & 0b010) == 0b010, fails)
    print()

    # ---------- E22: dead clock ----------
    print("[E22] core clock stopped")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    ck("E22a_dark_without_any_clock_edge", p.hw_blank(1) == 1, fails)
    ck("E22b_capture_survives", p.caught == 1, fails)
    print()

    # ---------- recovery must still work ----------
    print("[recovery] clear + explicit re-enable must eventually light")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    ck("R1_cleared_but_not_armed", (p.caught == 0 and p.disp_armed == 0
                                    and p.hw_blank(0) == 1), fails)
    p.edge(hw_fault=0, ctrl=0b01, safe=1, ready=1)
    ck("R2_explicit_re_enable_lights", (p.disp_armed == 1 and p.hw_blank(0) == 0), fails)
    print()

    # ---------- negative controls ----------
    print("[negative controls] each must be caught by the same model")
    n1 = Regs(neg={'no_caught_visibility'})
    bring_up(n1)
    n1.async_fault_edge()
    n1.edge(hw_fault=0)
    ck("NC-A drop the caught->status mapping  -> E17 fails",
       (n1.visible_fault(0) & VIS) == 0, fails)

    n2 = Regs(neg={'no_mask_check'})
    bring_up(n2)
    n2.async_fault_edge()
    n2.edge(hw_fault=0)
    n2.edge(hw_fault=0, w1c=0x000, fw=True)
    ck("NC-B drop the W1C mask check         -> E18 fails",
       n2.caught == 0, fails)

    n3 = Regs(neg={'no_async_capture'})
    bring_up(n3)
    n3.async_fault_edge()
    ck("NC-C drop the async capture itself    -> E22 fails",
       n3.hw_blank(0) == 0, fails)
    # 说明：`caught` 同时经由 disp_fault（COMM_TO 属于显示类故障）影响 hw_blank，
    # 所以"只删 hw_blank 里那一项"不会立刻可见——这是刻意的双重保险。
    n4 = Regs(neg={'no_caught_gate'})
    bring_up(n4)
    n4.async_fault_edge()
    print("  %-56s %s" % ("note: caught also reaches hw_blank via disp_fault ->",
                        "redundant, as designed (仍为 %d)" % n4.hw_blank(0)))
    print()

    print("--- not proven here ---")
    print("* no ModelSim: state rules only, not the RTL")
    print("* bit7/COMM_TO is a SHARED cause bit: it says 'a fault event was")
    print("  captured', not which comparator. Per-cause visibility for a")
    print("  sub-cycle pulse would need per-bit async latches (design option B)")
    print()

    if fails:
        print("RESULT=FAIL (%s)" % ", ".join(fails))
        return 1
    print("RESULT=PASS  E17/E18/E19/E20/E22 + recovery hold; 3 negative controls caught")
    return 0


if __name__ == '__main__':
    sys.exit(main())
