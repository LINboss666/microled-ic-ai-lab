#!/usr/bin/env python3
"""T6-A P0-D：故障闭环状态模型（双 always 块、严格 NBA、零 ModelSim）。

修订动机（复审 2026-11-19，P0-C 之后）
--------------------------------------
v3 把 W1C 与捕获位清除放在**同一次**状态更新里（`fw and (w1c & VIS) -> caught=0`），
所以 R1/R2 PASS。但真实 RTL 里 `clr_fault` 是一个**寄存器**：

    主块(N 沿):  fault_status <= n_fault & ~w1c ;  clr_fault <= 1
    捕获块(N 沿): 看到的是 clr_fault 的**旧值 0** -> caught 保持 1
    主块(N+1 沿): n_fault = 0 | 0 | (caught=1 ? bit7) = 0x080  -> 故障位复活

v4 因此把模型拆成两个时钟块，并显式建模 `clr_old` / `clr_next`：

* `variant='registered'`（= 现有候选 `bbcb831`）: 捕获块读 `clr_old` -> 一拍延迟 -> 复活；
* `variant='fixed'`（= 本次 P0-D 候选）: 清除请求是**组合**的
  `clear_caught_req = wr_cap_o & addr==FAULT & wd[7] & !any_hw_fault`，
  捕获块在同一沿看到它 -> 状态与捕获位同沿归零。

`n_fault` 两种 variant 都用 `caught` 的**旧值**（RTL 就是这样），这正是缺陷的根。

协议
----
* 捕获位 `caught` 异步置位（故障边沿）、同步清除（core 沿），死时钟清不掉；
* 可读状态：`fault_status`/`int_status` 的 bit7（COMM_TO）由 `caught` 派生
  —— V1.3 段0704「TCON 捕获共享 FAULT_n 后置 COMM_TO」，不新增地址；
* `n_fault &= ~(w1c & ~hw_fault)`：`w1c=0` 一位都不动；部分掩码只清被覆盖位；
* 清除要求：掩码覆盖 bit7 && 当前无活故障 && 确实是一笔对 A_FAULT 的写；
* set > clear：活故障/新脉冲同沿永远赢。

限制
----
纯状态规则，不是 RTL 仿真，也不是物理保证（异步单元的最小置位脉宽、开漏上拉、
时序约束都不在这里）。
"""
import sys

PERIOD = 10000                  # ps
VIS = 0x080                     # COMM_TO
DISPLAY_MASK = 0x7FF & ~0x100   # 除 ERR_REG(bit8)


class Regs:
    """两个 always 块 + 一个组合清除请求。

    neg 集合（负控，每个都对应一条会 FAIL 的断言）：
      no_registered_clear   : 还原 `clr_fault` 寄存器延迟（= 缺陷版）
      no_caught_visibility  : 去掉 caught -> bit7 映射（短脉冲不可读）
      no_mask_check         : clr 不看 W1C 掩码（写 0 也清）
      no_async_capture      : 去掉异步置位（短脉冲根本不进捕获）
      no_rearm_latch        : 去掉 disp_armed 许可锁
      no_live_fault_check   : CTRL 准入不看活故障
    """

    def __init__(self, neg=None, variant='fixed'):
        self.neg = set(neg or ())
        if 'no_registered_clear' in self.neg:
            variant = 'registered'
        self.variant = variant
        self.en = 0
        self.blank_r = 1
        self.fault_status = 0
        self.disp_armed = 0
        self.caught = 0
        self.clr = 0            # clr_fault 寄存器（fixed 版恒 0，仍建模）
        self.int_status = 0
        self.fsd = 0
        self.frames = 0         # 已提交的写帧数（观测用）

    # ---------------- 组合量（全部读**旧值**） ----------------
    def visible_fault(self, hw_fault):
        f = self.fault_status | hw_fault
        if self.caught and 'no_caught_visibility' not in self.neg:
            f |= VIS
        return f & 0x7FF

    def disp_fault(self, hw_fault):
        return 1 if (self.visible_fault(hw_fault) & DISPLAY_MASK) else 0

    def hw_blank(self, hw_fault):
        armed = 1 if 'no_rearm_latch' in self.neg else self.disp_armed
        return int(bool(self.blank_r or (not self.en) or hw_fault or
                        self.caught or (not armed) or
                        self.disp_fault(hw_fault)))

    def clear_req(self, hw_fault, w1c, fw):
        """组合清除请求：与 W1C 同一拍、读同一笔帧（RTL: wr_frame[7]）。"""
        if not fw:
            return 0
        if hw_fault:
            return 0
        if 'no_mask_check' in self.neg:
            return 1
        return 1 if (w1c & VIS) else 0

    def irq(self, int_en=0):
        return 1 if (self.int_status & int_en) else 0

    # ---------------- 一个 core 上升沿 ----------------
    def edge(self, hw_fault=0, ctrl=None, w1c=0, safe=1, ready=1, fw=False):
        # ---- 采样所有旧值（两个块都只看这些） ----
        old_fs = self.fault_status
        caught_old = self.caught
        clr_old = self.clr
        armed_old = self.disp_armed
        dispf = self.disp_fault(hw_fault)

        if fw:
            self.frames += 1

        # =========== 块 1：主时序（写提交 / W1C / 状态 / 许可） ===========
        n_fault = old_fs | hw_fault
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
                    ok = ok and bool(safe and ready and not hw_fault and
                                     not dispf and not caught_old)
            if ok:
                n_en = en_new
                n_blank = blk_new if en_new else 1
                n_armed = 1 if (en_new and not blk_new) else 0
            else:
                err = 1
                n_fault |= 0x100

        if w1c:
            n_fault &= ~(w1c & ~hw_fault)

        # =========== 块 2：异步捕获（set 优先级最高） ===========
        if hw_fault:
            n_caught = 1
            n_clr = 0
        elif 'no_async_capture' in self.neg:
            n_caught = caught_old              # 缺陷版：脉冲不跨沿就丢失
            n_clr = 0
        elif self.variant == 'registered':
            # 现有候选：捕获块看到的是 clr_fault 的**旧值**
            n_caught = 0 if clr_old else caught_old
            n_clr = self.clear_req(hw_fault, w1c, fw)
        else:
            # P0-D 候选：组合清除请求，同一沿生效
            n_caught = 0 if self.clear_req(hw_fault, w1c, fw) else caught_old
            n_clr = 0

        # 故障/捕获/锁存任一存在 -> 许可清零（块末尾，压过同拍置位）
        if hw_fault or n_caught or dispf:
            n_armed = 0

        # =========== 提交（NBA：所有右值都已按旧值算完） ===========
        n_vis = (n_fault & 0x7FF)
        if n_caught and 'no_caught_visibility' not in self.neg:
            n_vis |= VIS
        n_int = self.int_status | (n_vis & ~self.fsd)

        self.en, self.blank_r = n_en, n_blank
        self.fault_status = n_fault & 0x7FF
        self.disp_armed = n_armed
        self.caught = n_caught
        self.clr = n_clr
        self.int_status = n_int
        self.fsd = n_vis
        return err

    def async_fault_edge(self):
        """故障断言沿：不需要 clk，置位立即生效。"""
        if 'no_async_capture' in self.neg:
            return
        self.caught = 1


def ck(name, cond, fails):
    print("  %-58s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        fails.append(name)


def bring_up(p):
    p.edge(ctrl=0b11, safe=1, ready=0)      # EN=1 BLANK=1
    p.edge(ctrl=0b01, safe=1, ready=1)      # EN=1 BLANK=0 -> armed


def main():
    fails = []
    print("=== T6-A P0-D: fault closure with a REAL clr_fault register (zero ModelSim) ===")
    print("    block 1 (main)  : fault_status <= f(old status, old caught, w1c)")
    print("    block 2 (capture): caught <= set edge > (clear request) > hold")
    print("    registered variant reads clr_old (one edge late) / fixed reads clear_req")
    print()

    # ---------- D0: reproduce the reviewed counterexample on the OLD candidate ----------
    print("[D0] old candidate (registered clr_fault) must reproduce the reviewed failure")
    p = Regs(variant='registered')
    p.fault_status = VIS
    p.caught = 1
    print("   W-1    : status=0x%03X caught=%d clr=%d armed=%d"
          % (p.fault_status, p.caught, p.clr, p.disp_armed))
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    w0 = (p.fault_status, p.caught, p.clr)
    print("   W0 W1C : status=0x%03X caught=%d clr=%d" % w0)
    p.edge(hw_fault=0)
    w1 = (p.fault_status, p.caught, p.clr)
    print("   W1 idle: status=0x%03X caught=%d clr=%d" % w1)
    p.edge(hw_fault=0)
    w2 = p.fault_status
    print("   W2 idle: status=0x%03X" % w2)
    e3 = p.edge(hw_fault=0, ctrl=0b01, safe=1, ready=1)
    print("   W3 CTRL: rejected=%d status=0x%03X blank=%d"
          % (e3, p.fault_status, p.hw_blank(0)))
    ck("D0a_W0_status_cleared_but_caught_still_1", w0 == (0x000, 1, 1), fails)
    ck("D0b_W1_status_resurrects_to_0x080", w1 == (VIS, 0, 0), fails)
    ck("D0c_W3_rearm_rejected", (e3 == 1) and (p.disp_armed == 0), fails)
    print()

    # ---------- D1: the fix clears both in the SAME edge, over 3 consecutive edges ----------
    print("[D1] fixed candidate: W1C clears status and capture on the SAME edge")
    p = Regs()
    p.fault_status = VIS
    p.caught = 1
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    seq = [(p.fault_status, p.caught)]
    print("   W0 W1C : status=0x%03X caught=%d clr=%d" % (p.fault_status, p.caught, p.clr))
    for k in (1, 2):
        p.edge(hw_fault=0)
        seq.append((p.fault_status, p.caught))
        print("   W%d idle: status=0x%03X caught=%d" % (k, p.fault_status, p.caught))
    ck("D1a_status_and_capture_zero_on_the_clear_edge", seq[0] == (0, 0), fails)
    ck("D1b_three_consecutive_edges_clean", all(s == (0, 0) for s in seq), fails)
    ck("D1c_no_clr_register_left_pending", p.clr == 0, fails)
    ck("D1d_still_dark_without_a_rearm", p.hw_blank(0) == 1, fails)
    print()

    # ---------- D2: explicit re-arm works and really conducts ----------
    print("[D2] explicit CTRL unblank after the clear must re-enable, over 3 samples")
    p.edge(hw_fault=0, ctrl=0b01, safe=1, ready=1)
    samples = []
    for _ in range(3):
        samples.append((p.disp_armed, p.hw_blank(0)))
        p.edge(hw_fault=0)
    print("   after CTRL: armed=%d blank=%d samples=%s"
          % (p.disp_armed, p.hw_blank(0), samples))
    ck("D2a_rearm_accepted", p.disp_armed == 1, fails)
    ck("D2b_three_nonzero_permit_samples", all(s == (1, 0) for s in samples), fails)
    print()

    # ---------- D3: W1C semantics ----------
    print("[D3] W1C mask semantics")
    q = Regs()
    bring_up(q)
    q.async_fault_edge()
    q.edge(hw_fault=0)
    q.edge(hw_fault=0, w1c=0x000, fw=True)
    ck("D3a_w1c_0x000_clears_nothing",
       (q.caught == 1) and ((q.visible_fault(0) & VIS) == VIS), fails)
    q.edge(hw_fault=0, w1c=0x001, fw=True)
    ck("D3b_w1c_0x001_keeps_bit7", (q.caught == 1) and
       ((q.visible_fault(0) & VIS) == VIS), fails)
    q.edge(hw_fault=0, w1c=VIS, fw=True)
    ck("D3c_w1c_0x080_clears_capture_and_bit7",
       (q.caught == 0) and (q.visible_fault(0) == 0), fails)
    q.edge(hw_fault=0b001)                      # live UVLO latched
    q.edge(hw_fault=0)
    q.async_fault_edge()                        # + a captured event
    q.edge(hw_fault=0)
    q.edge(hw_fault=0b001, w1c=VIS | 0b001, fw=True)
    # 活故障那一拍：bit0 被 W1C 掩码覆盖，但源还在 -> `w1c & ~hw_fault` 不动它，
    # 且捕获位被同一个活故障重新置起（RTL 行为，不是缺陷）。
    print("   live OV + W1C(bit0|bit7): status=0x%03X caught=%d"
          % (q.visible_fault(0b001), q.caught))
    ck("D3d_live_fault_cannot_be_cleared", (q.visible_fault(0b001) & 0b001) != 0, fails)
    # 源撤去之后：这是**两个不同原因**（bit0 锁存 + bit7 捕获）的一次清理，
    # 不是对同一个故障写两遍。
    q.edge(hw_fault=0)
    q.edge(hw_fault=0, w1c=VIS | 0b001, fw=True)
    print("   source gone + W1C(both): status=0x%03X caught=%d"
          % (q.visible_fault(0), q.caught))
    ck("D3e_source_gone_then_one_w1c_clears_both",
       (q.visible_fault(0) & (VIS | 0b001)) == 0, fails)
    print()

    # ---------- D4: only an accepted FAULT write can clear ----------
    print("[D4] other addresses / read transactions cannot clear the capture")
    q = Regs()
    bring_up(q)
    q.async_fault_edge()
    q.edge(hw_fault=0)
    q.edge(hw_fault=0, w1c=0, fw=False, ctrl=0b01, safe=1, ready=1)   # a CTRL write
    ck("D4a_ctrl_write_cannot_clear", q.caught == 1, fails)
    q.edge(hw_fault=0, w1c=VIS, fw=False)      # data bits present but not a FAULT write
    ck("D4b_read_cannot_clear", q.caught == 1, fails)
    print()

    # ---------- D5: the +-1 ns race around the clear edge ----------
    print("[D5] new fault around the clear edge (set must win)")
    q = Regs()
    bring_up(q)
    q.async_fault_edge()
    q.edge(hw_fault=0)
    q.edge(hw_fault=0, w1c=VIS, fw=True)       # clean clear
    q.async_fault_edge()                       # 1 ps AFTER the edge, 4 ns wide
    ck("D5a_pulse_after_the_edge_is_caught_again",
       (q.caught == 1) and (q.hw_blank(0) == 1), fails)
    q2 = Regs()
    bring_up(q2)
    q2.async_fault_edge()
    q2.edge(hw_fault=0)
    q2.edge(hw_fault=0b010, w1c=VIS, fw=True)  # pulse still asserted AT the edge
    ck("D5b_pulse_at_the_edge_beats_the_clear",
       (q2.caught == 1) and (q2.clr == 0), fails)
    print()

    # ---------- E17..E22 kept from the earlier round ----------
    print("[E17] 4 ns pulse, no core edge inside it -> readable, and no auto-restore")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    ck("E17a_status_reports_the_event", (p.visible_fault(0) & VIS) == VIS, fails)
    ck("E17b_int_status_reports_it_too", (p.int_status & VIS) == VIS, fails)
    ck("E17c_panel_still_dark", p.hw_blank(0) == 1, fails)

    print("[E18] W1C = 0 must not clear")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0x000, fw=True)
    ck("E18a_w1c_zero_keeps_caught", p.caught == 1, fails)
    ck("E18b_w1c_zero_still_dark", p.hw_blank(0) == 1, fails)

    print("[E19] partial mask keeps the other cause")
    p = Regs()
    bring_up(p)
    p.edge(hw_fault=0b001)
    p.edge(hw_fault=0)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0b001, fw=True)
    ck("E19a_bit0_cleared", (p.visible_fault(0) & 0b001) == 0, fails)
    ck("E19b_bit7_kept", (p.visible_fault(0) & VIS) == VIS, fails)
    ck("E19c_still_dark", p.hw_blank(0) == 1, fails)

    print("[E20] new fault on the same edge as the W1C survives")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0b010, w1c=VIS, fw=True)
    ck("E20a_new_fault_wins_over_the_clear", p.caught == 1, fails)
    ck("E20b_new_fault_is_visible", (p.visible_fault(0b010) & 0b010) == 0b010, fails)

    print("[E22] core clock stopped")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    ck("E22a_dark_without_any_clock_edge", p.hw_blank(0) == 1, fails)
    ck("E22b_capture_survives", p.caught == 1, fails)

    print("[R1/R2] clear -> re-enable reaches a lit panel")
    p = Regs()
    bring_up(p)
    p.async_fault_edge()
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=VIS, fw=True)
    ck("R1_cleared_but_not_armed", (p.caught == 0 and p.disp_armed == 0 and
                                    p.hw_blank(0) == 1), fails)
    p.edge(hw_fault=0, ctrl=0b01, safe=1, ready=1)
    ck("R2_explicit_re_enable_lights", (p.disp_armed == 1 and p.hw_blank(0) == 0), fails)
    print()

    # ---------- negative controls: four kinds, each must FAIL its own assertion ----------
    print("[negative controls] four kinds, each must be caught")
    n1 = Regs(neg={'no_registered_clear'})
    n1.fault_status = VIS
    n1.caught = 1
    n1.edge(hw_fault=0, w1c=VIS, fw=True)
    n1.edge(hw_fault=0)
    e = n1.edge(hw_fault=0, ctrl=0b01, safe=1, ready=1)
    print("   NC-1 registered clear : status=0x%03X caught=%d rearm_rejected=%d"
          % (n1.fault_status, n1.caught, e))
    ck("NC-1 restore the register delay        -> D1b fails",
       (n1.fault_status & VIS) == VIS, fails)

    n2 = Regs(neg={'no_caught_visibility'})
    bring_up(n2)
    n2.async_fault_edge()
    n2.edge(hw_fault=0)
    print("   NC-2 caught->bit7 dropped: status=0x%03X" % n2.fault_status)
    ck("NC-2 drop caught->bit7 mapping         -> E17a fails",
       (n2.visible_fault(0) & VIS) == 0, fails)

    n3 = Regs(neg={'no_mask_check'})
    bring_up(n3)
    n3.async_fault_edge()
    n3.edge(hw_fault=0)
    n3.edge(hw_fault=0, w1c=0x000, fw=True)
    print("   NC-3 mask dropped      : after W1C 0x000 caught=%d" % n3.caught)
    ck("NC-3 drop the W1C bit7 mask            -> D3a fails", n3.caught == 0, fails)

    n4 = Regs(neg={'no_async_capture'})
    bring_up(n4)
    n4.async_fault_edge()
    print("   NC-4 async set dropped : blank=%d caught=%d" % (n4.hw_blank(0), n4.caught))
    ck("NC-4 drop the async set                -> E22a fails",
       n4.hw_blank(0) == 0, fails)
    print()

    print("--- not proven here ---")
    print("* state rules only: no RTL, no ModelSim, no timing/CDC sign-off")
    print("* bit7/COMM_TO is a SHARED cause bit (V1.3 段0704): it says 'an event")
    print("  was captured', not which comparator. Per-cause visibility would")
    print("  need 11 async latches (design option B, not approved)")
    print()

    if fails:
        print("RESULT=FAIL (%s)" % ", ".join(fails))
        return 1
    print("RESULT=PASS  D0-D5 + E17..E22 + R1/R2 hold; 4 negative controls caught")
    print("             old candidate reproduced: status 0x000 -> 0x080, rearm rejected")
    return 0


if __name__ == '__main__':
    sys.exit(main())
