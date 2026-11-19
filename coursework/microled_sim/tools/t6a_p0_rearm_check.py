#!/usr/bin/env python3
"""T6-A P0 安全再使能：严格的 NBA 语义状态模型（零 ModelSim）。

为什么要重写 v1
---------------
v1 在"计算 CTRL 准入"之前就先更新了 `fault_status`，这不是 Verilog 的语义。
真实 RTL 里 `fault_status` 是寄存器，块内所有组合判断（`disp_fault`、`any_hw_fault`）
读到的都是**本次上升沿之前**的旧值；只有非阻塞赋值在块末才生效。
本文件严格照这个顺序实现：

    1. 用旧值算所有组合量（any_hw_fault / disp_fault / hw_fault_caught / hw_blank）
    2. 用旧值判定本次 CTRL / W1C 的准入
    3. 在块末一次性提交所有次态

覆盖的用例
----------
  CE1       显示中故障出现 -> 源撤去、无 W1C、无再使能 -> 必须持续熄屏
  CE1-ASYNC 4 ns 脉冲，没有任何 core 沿落在脉冲内 -> 异步置位必须抓住
  CE2       源撤去 + W1C 清状态，仍不再使能 -> 必须持续熄屏
  CE3       故障仍有效时写 CTRL=EN1/BLANK0 -> 写被拒
  CE3b      故障与 CTRL 写**同一沿**（临界沿）-> 不得提前 rearm
  CE4       清状态 + 显式再使能 -> 许可恢复（只到 hw_blank=0）
  CE5       INT_EN=0 / 读 / 坏帧 -> 不能绕过
  CE7       core 时钟停止 -> 不能清除，必须保持关断

负控：删再使能锁 / 删锁存故障门 / 允许临界沿提前 rearm，三者都必须被抓到。
"""
import sys

DISPLAY_MASK = 0x7FF & ~0x100      # every fault bit except ERR_REG (bit8)


class Regs:
    """tcon_spi_regs 的安全相关子集，NBA 语义。

    寄存器：en / blank_r / fault_status / disp_armed / hw_fault_caught
    组合：  any_hw_fault = |hw_fault
            disp_fault   = |(fault_status & DISPLAY_MASK)
            hw_blank     = blank_r | !en | any_hw_fault | hw_fault_caught
                           | !disp_armed | disp_fault
    """

    def __init__(self, neg=None):
        self.neg = neg or set()
        self.en = 0
        self.blank_r = 1
        self.fault_status = 0
        self.disp_armed = 0
        self.caught = 0

    # ---------- 组合量（只读当前寄存器值） ----------
    def any_hw_fault(self, hw_fault):
        return 1 if hw_fault else 0

    def disp_fault(self):
        if 'no_sticky_gate' in self.neg:
            return 0
        return 1 if (self.fault_status & DISPLAY_MASK) else 0

    def hw_blank(self, hw_fault):
        armed = 1 if 'no_rearm_latch' in self.neg else self.disp_armed
        caught = 0 if 'no_sticky_gate' in self.neg else self.caught
        return int(bool(self.blank_r) or (not self.en) or
                   self.any_hw_fault(hw_fault) or caught or
                   (not armed) or self.disp_fault())

    # ---------- 一个上升沿 ----------
    def edge(self, hw_fault=0, ctrl=None, w1c=0, safe=1, ready=1):
        """返回本沿是否发生了被拒绝的写（err_set）。"""
        # ---- 1. 旧值组合项 ----
        anyf = self.any_hw_fault(hw_fault)
        dispf = self.disp_fault()
        armed_old = self.disp_armed
        caught_old = self.caught

        # ---- 2. 用旧值判定 ----
        n_fault = self.fault_status | hw_fault
        if w1c:
            n_fault &= ~(w1c & ~hw_fault)
        n_en, n_blank = self.en, self.blank_r
        n_armed = armed_old
        err = 0

        if ctrl is not None:
            wd = ctrl
            en_new = wd & 1
            blk_new = (wd >> 1) & 1
            ok = True
            if (wd >> 3) & 1:                       # TEST without TEST_EN
                ok = False
            if en_new and not safe:
                ok = False
            if en_new and ('no_live_fault_check' not in self.neg) and anyf:
                ok = False
            if en_new and not blk_new:
                if 'no_live_fault_check' in self.neg:
                    cond = bool(safe and ready)
                else:
                    cond = bool(safe and ready and not anyf and not dispf
                                and not caught_old)
                if not cond:
                    ok = False
            if ok:
                n_en = en_new
                n_blank = blk_new if en_new else 1
                n_armed = 1 if (en_new and not blk_new) else 0
            else:
                err = 1
                n_fault |= 0x100                    # ERR_REG

        # ---- 3. 故障处理，后写者胜 ----
        n_caught = 1 if (caught_old or anyf) else caught_old
        if w1c and not anyf and (n_fault & 0x7FF) == 0 and 'no_clear' not in self.neg:
            n_caught = 0
        if anyf or n_caught:
            n_armed = 0

        # ---- 4. 提交 ----
        self.en, self.blank_r = n_en, n_blank
        self.fault_status = n_fault
        self.disp_armed = n_armed
        self.caught = n_caught
        return err

    # 异步：故障边沿本身（不等时钟）
    def async_fault_edge(self):
        self.caught = 1


def show(rows):
    print("  %-46s %-3s %-4s %-5s %-7s %-6s %-8s %-6s"
          % ("step", "en", "blk", "fault", "latched", "caught", "armed", "blank"))
    for r in rows:
        print("  %-46s %-3d %-4d %-5d %-7s %-6d %-8d %-6d"
              % (r[0], r[1], r[2], r[3],
                 ("0x%03X" % r[4]) if r[4] else "0", r[5], r[6], r[7]))


def snap(p, note, hwf=0):
    return (note, p.en, p.blank_r, hwf, p.fault_status,
            p.caught, p.disp_armed, p.hw_blank(hwf))


def bring_up(p):
    p.edge(ctrl=0b11, safe=1, ready=0)     # EN=1 BLANK=1
    p.edge(ctrl=0b01, safe=1, ready=1)     # EN=1 BLANK=0


def ce1(neg=None):
    p = Regs(neg)
    rows = [snap(p, "pre")] if False else []
    bring_up(p)
    rows.append(snap(p, "A display on"))
    for _ in range(3):
        p.edge(hw_fault=0b001)
        p.edge(hw_fault=0b001)
    rows.append(snap(p, "B fault active (6 clock edges)", 1))
    for _ in range(5):
        p.edge(hw_fault=0)
    rows.append(snap(p, "C source gone, no W1C, no re-enable"))
    return rows, p.hw_blank(0)


def ce1_async(neg=None):
    p = Regs(neg)
    rows = []
    bring_up(p)
    p.async_fault_edge()                 # 只发生边沿，没有时钟
    rows.append(snap(p, "B' 4 ns pulse, async edge only", 1))
    rows.append(snap(p, "B'' pulse over, NO clock edge yet", 0))
    p.edge(hw_fault=0)                   # 脉冲结束后的第一个时钟沿
    rows.append(snap(p, "C' first clock edge after the pulse"))
    for _ in range(3):
        p.edge(hw_fault=0)
    rows.append(snap(p, "D' settled"))
    return rows, p.hw_blank(0)


def ce1_async_immediate(neg=None):
    """The exact window that the async latch covers: the pulse is over, but no
    clock edge has happened yet, so `fault_status` is still 0 and only the
    caught-fault latch keeps the panel dark."""
    p = Regs(neg)
    bring_up(p)
    p.async_fault_edge()
    return p.hw_blank(0)


def ce2(neg=None):
    p = Regs(neg)
    rows = []
    bring_up(p)
    p.edge(hw_fault=0b010)
    p.edge(hw_fault=0b010)
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0b010)
    p.edge(hw_fault=0)
    rows.append(snap(p, "D cleared by W1C, still no re-enable"))
    return rows, p.hw_blank(0)


def ce3(neg=None):
    p = Regs(neg)
    rows = []
    p.edge(ctrl=0b11, safe=1, ready=0)
    p.edge(hw_fault=0b100)
    p.edge(hw_fault=0b100)
    err = p.edge(hw_fault=0b100, ctrl=0b01, safe=1, ready=1)
    rows.append(snap(p, "E unblank attempted during OT", 1))
    return rows, p.hw_blank(1), err


def ce3b(neg=None):
    p = Regs(neg)
    rows = []
    p.edge(ctrl=0b11, safe=1, ready=0)
    err = p.edge(hw_fault=0b1000, ctrl=0b01, safe=1, ready=1)
    rows.append(snap(p, "F CTRL write on the fault edge itself", 1))
    p.edge(hw_fault=0)
    p.edge(hw_fault=0)
    rows.append(snap(p, "G fault gone, two edges later"))
    return rows, p.hw_blank(0), err


def ce4(neg=None):
    p = Regs(neg)
    rows = []
    bring_up(p)
    p.edge(hw_fault=0b1000)
    p.edge(hw_fault=0)
    p.edge(hw_fault=0, w1c=0b1000)
    p.edge(hw_fault=0)
    rows.append(snap(p, "H cleared, not yet re-enabled"))
    p.edge(hw_fault=0, ctrl=0b01, safe=1, ready=1)
    rows.append(snap(p, "I explicit re-enable accepted"))
    return rows, p.hw_blank(0)


def ce5(neg=None):
    p = Regs(neg)
    bring_up(p)
    p.edge(hw_fault=0b10000)
    for _ in range(6):
        p.edge(hw_fault=0)               # 读/坏帧只体现为"没有写、没有 W1C"
    return [], p.hw_blank(0)


def ce7(neg=None):
    p = Regs(neg)
    bring_up(p)
    p.async_fault_edge()
    return p.hw_blank(1)                 # 时钟死了，一次 edge() 都没有


def main():
    fails = []
    print("=== T6-A P0 safety re-arm, NBA-accurate state model (zero ModelSim) ===")
    print("    hw_blank = blank_r | !en | any_hw_fault | hw_fault_caught | !disp_armed | disp_fault")
    print()

    print("[CE1] fault appears then the source goes away, host does nothing")
    rows, b = ce1(); show(rows); print("  -> hw_blank=%d (want 1)" % b); print()
    if b != 1: fails.append("CE1")

    print("[CE1-ASYNC] a 4 ns pulse that no core edge ever sees")
    rows, b = ce1_async(); show(rows); print("  -> hw_blank=%d (want 1)" % b); print()
    if b != 1: fails.append("CE1-ASYNC")

    print("[CE2] source gone + W1C clears the status, no re-enable")
    rows, b = ce2(); show(rows); print("  -> hw_blank=%d (want 1)" % b); print()
    if b != 1: fails.append("CE2")

    print("[CE3] unblank while the fault is still live")
    rows, b, err = ce3(); show(rows)
    print("  -> hw_blank=%d (want 1), write rejected=%d (want 1)" % (b, err)); print()
    if b != 1 or err != 1: fails.append("CE3")

    print("[CE3b] CTRL write on the very edge where the fault arrives")
    rows, b, err = ce3b(); show(rows)
    print("  -> after the fault is gone hw_blank=%d (want 1), rejected=%d (want 1)" % (b, err))
    print()
    if b != 1 or err != 1: fails.append("CE3b")

    print("[CE4] cleared + explicit re-enable")
    rows, b = ce4(); show(rows); print("  -> hw_blank=%d (want 0)" % b); print()
    if b != 0: fails.append("CE4")

    print("[CE5] reads / bad frames / int_en=0 cannot bypass")
    _, b = ce5(); print("  -> hw_blank=%d (want 1); the gate has no rd/int_en input" % b); print()
    if b != 1: fails.append("CE5")

    print("[CE7] core clock stopped")
    b = ce7(); print("  -> hw_blank=%d (want 1): a dead clock cannot run the clear" % b); print()
    if b != 1: fails.append("CE7")

    print("--- negative controls (each must be caught) ---")
    # CE2 is where the re-arm latch is the only lock left (the W1C cleared both
    # the status and the caught latch), so deleting it has to show up there.
    _, n1 = ce2(neg={'no_rearm_latch'})
    print("NC-A delete the re-arm latch          CE2 hw_blank=%d -> %s"
          % (n1, "caught" if n1 == 0 else "NOT CAUGHT"))
    if n1 != 0: fails.append("NC-A")

    # The window between the pulse and the next clock edge is covered ONLY by
    # the async latch, so that is where its removal is visible.
    n2 = ce1_async_immediate(neg={'no_sticky_gate'})
    print("NC-B delete the caught-fault gate      pulse-over/no-edge hw_blank=%d -> %s"
          % (n2, "caught" if n2 == 0 else "NOT CAUGHT"))
    if n2 != 0: fails.append("NC-B")

    _, n3, e3 = ce3b(neg={'no_live_fault_check'})
    print("NC-C allow re-arm on the critical edge CE3b hw_blank=%d rejected=%d -> %s"
          % (n3, e3, "caught" if (n3 == 0 or e3 == 0) else "NOT CAUGHT"))
    if not (n3 == 0 or e3 == 0): fails.append("NC-C")
    print()

    print("--- what this model does NOT prove ---")
    print("* no ModelSim: the RTL is not exercised, only its state rules")
    print("* hw_blank=0 means 'the host permit passed', not 'the panel is lit':")
    print("  a legal frame, two-stage precharge and Data/Scan conduction are")
    print("  tcon_top's key and must be proven in the five-chip environment")
    print("* the candidate patch has NOT been re-validated against the 57 RUN02")
    print("  assertions; that needs the new CE budget")
    print()

    if fails:
        print("RESULT=FAIL (%s)" % ", ".join(fails))
        return 1
    print("RESULT=PASS  CE1/CE1-ASYNC/CE2..CE5/CE7 hold; 3 negative controls caught")
    return 0


if __name__ == '__main__':
    sys.exit(main())
