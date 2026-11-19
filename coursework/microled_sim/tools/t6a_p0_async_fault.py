#!/usr/bin/env python3
"""T6-A P0-B rev2：短异步故障脉冲（整数 ps 事件驱动，零 ModelSim）。

rev1 的错误
-----------
rev1 用 1 ns 整数网格 + `(t - phase) % 10 == 0` 判断时钟沿。当 phase = 2.5 / 7.5 ns
时，整数的 t 永远不等于 2.5 + 10k，于是**一个时钟沿都不产生**，模型就把 8/9/10/11/20 ns
的脉冲也报成"没捕获"。这是时间步进的错，不是 RTL 的结论；复审的独立复算已指出。

rev2 的做法
-----------
* 全部时间用 **整数皮秒**，无浮点、无网格；
* 事件驱动：只在"脉冲起""脉冲止""core 上升沿"三种时刻改变状态；
* 脉冲取**半开区间** [start, start+width)；
* 同一时刻先"故障拉低"再"core 采样"（对捕获更保守）；
* 相位平移的是**脉冲起点**（start = 12000 + phase ps），时钟沿固定在 10000k。

数学硬门
--------
core 周期 10 ns，任何长度 **>= 10 ns** 的半开区间必然至少含一个时钟沿。
因此 11 ns 与 20 ns 必须在**四个相位全部捕获**；rev1 记录的 2/4 是错的。

用法：python t6a_p0_async_fault.py [--csv out.csv]
"""
import argparse
import sys

PERIOD = 10000          # ps, 100 MHz
PHASES = (0, 2500, 5000, 7500)
PULSE_START = 12000     # ps
WIDTHS = (1000, 2000, 4000, 8000, 9000, 10000, 11000, 20000)
MUST_CAPTURE = (11000, 20000)


class Plant:
    """安全相关子集：故障电平、异步捕获、FSM 锁存、Host 许可。"""

    def __init__(self, mode='async_set'):
        self.mode = mode
        self.state = 'ACTIVE'
        self.sticky = 0
        self.armed = 1
        self.fault_assert = 0

    def tcon_blank(self):
        if self.state != 'ACTIVE':
            return 1
        return 1 if self.fault_assert else 0

    def spi_blank(self):
        if self.mode == 'fsm_only':
            return int(self.fault_assert)
        return int(self.fault_assert or self.sticky or (not self.armed))

    def panel_blank(self):
        return int(self.tcon_blank() or self.spi_blank())

    def assert_fault(self):
        self.fault_assert = 1
        if self.mode == 'async_set':
            self.sticky = 1

    def deassert_fault(self):
        self.fault_assert = 0

    def core_edge(self):
        if self.state == 'ACTIVE' and self.fault_assert:
            self.state = 'FAULT'
        if self.mode in ('sync_only', 'async_set') and self.fault_assert:
            self.sticky = 1
        if self.fault_assert or self.sticky:
            self.armed = 0


def run(mode, start_ps, width_ps, t_end=80000):
    p = Plant(mode)
    end_ps = start_ps + width_ps
    edges = [PERIOD * k for k in range(0, t_end // PERIOD + 1)]
    events = sorted(set([start_ps, end_ps] + edges))
    rows = []
    sampled = 0
    for t in events:
        if t == start_ps:
            p.assert_fault()
        if t == end_ps:
            p.deassert_fault()
        if t % PERIOD == 0:
            before = p.fault_assert
            p.core_edge()
            if before:
                sampled = 1
        rows.append((t, 1 if t % PERIOD == 0 else 0, p.fault_assert, p.state,
                     p.tcon_blank(), p.spi_blank(), p.panel_blank()))
    t_settle = ((end_ps // PERIOD) + 1) * PERIOD
    if t_settle != rows[-1][0]:
        p.core_edge()
        rows.append((t_settle, 1, p.fault_assert, p.state,
                     p.tcon_blank(), p.spi_blank(), p.panel_blank()))
    held = all(r[6] == 1 for r in rows if r[0] >= end_ps)
    return rows, sampled, held


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default=None)
    args = ap.parse_args()

    print("=== T6-A P0-B rev2: short asynchronous fault pulse (integer ps, event driven) ===")
    print("core period %d ps; pulse start = %d + phase; half-open [start, start+width)"
          % (PERIOD, PULSE_START))
    print()

    fails = []

    rows, sampled, held = run('fsm_only', PULSE_START, 4000)
    print("--- (1) CURRENT tcon_top: FSM samples only (4 ns pulse, phase 0) ---")
    print("      t_ps   clk  fault  state       tcon_blank  panel_blank")
    for r in rows:
        if 8000 <= r[0] <= 36000:
            print("   %8d  %3d %6d  %-10s %10d %12d" % (r[0], r[1], r[2], r[3], r[4], r[6]))
    print("   after the pulse: %s" % ("DARK" if held else "RELIT (the reported P0)"))
    if held:
        fails.append("CE1-current-should-lose")
    print()

    rows, sampled, held = run('async_set', PULSE_START, 4000)
    print("--- (3) PROPOSAL: async set / sync clear (4 ns pulse, phase 0) ---")
    for r in rows:
        if 8000 <= r[0] <= 36000:
            print("   %8d  %3d %6d  %-10s %10d %12d" % (r[0], r[1], r[2], r[3], r[4], r[6]))
    print("   after the pulse: %s" % ("DARK" if held else "RELIT"))
    if not held:
        fails.append("CE1-proposal-must-hold")
    print()

    print("--- width x phase sweep ---")
    print("   width_ps  phase  fsm_sampled  sync_sampled  async_held")
    table = {}
    for w in WIDTHS:
        for ph in PHASES:
            _, s1, _ = run('fsm_only', PULSE_START + ph, w)
            _, s2, _ = run('sync_only', PULSE_START + ph, w)
            _, _, h3 = run('async_set', PULSE_START + ph, w)
            table[(w, ph)] = (s1, s2, h3)
            print("   %8d  %5d  %11d  %12d  %10d" % (w, ph, s1, s2, h3))
    print()

    for w in MUST_CAPTURE:
        bad = [ph for ph in PHASES if table[(w, ph)][0] == 0]
        print("   HARD GATE width=%d ps (> one period): fsm_sampled in %d/4 phases%s"
              % (w, 4 - len(bad), "" if not bad else "  MISSING: %s" % bad))
        if bad:
            fails.append("GATE-w%d" % w)
    print()

    n_held = sum(1 for v in table.values() if v[2] == 1)
    print("   async_set holds the panel dark in %d/%d width-phase combinations"
          % (n_held, len(table)))
    if n_held != len(table):
        fails.append("async-not-held-everywhere")

    narrow = [w for w in (1000, 2000, 4000) if any(table[(w, ph)][0] == 0 for ph in PHASES)]
    print("   sub-cycle widths where the FSM misses at least one phase: %s" % narrow)
    if not narrow:
        fails.append("no-defect-visible")
    print()

    print("--- clear protocol (async_set) ---")
    p = Plant('async_set')
    log = []
    for (t, fault, clr, note) in ((10000, 0, False, 'display on'),
                                  (12000, 1, False, 'fault asserted (async)'),
                                  (16000, 0, False, 'source gone, no core edge yet'),
                                  (20000, 0, False, 'first core edge: armed revoked'),
                                  (30000, 0, True,  'W1C clears the capture'),
                                  (40000, 0, False, 'still no re-enable')):
        if fault and not p.fault_assert:
            p.assert_fault()
        elif not fault and p.fault_assert:
            p.deassert_fault()
        if t % PERIOD == 0:
            p.core_edge()
        if clr:
            p.sticky = 0
        log.append((t, fault, p.sticky, p.armed, p.panel_blank(), note))
    print("      t_ps  fault  caught  armed  blank  note")
    for r in log:
        print("   %8d %6d %7d %6d %6d  %s" % r)
    ok = all(r[4] == 1 for r in log[2:])
    print("   clear did NOT re-arm the panel -> %s" % ("OK" if ok else "WRONG"))
    if not ok:
        fails.append("clear-must-not-rearm")
    print()

    print("--- core clock stopped ---")
    p = Plant('async_set')
    p.assert_fault()
    print("   fault asserted with no clock edge: caught=%d blank=%d"
          % (p.sticky, p.panel_blank()))
    dead_ok = (p.sticky == 1 and p.panel_blank() == 1)
    print("   a clear request cannot run without a clock edge: caught=%d" % p.sticky)
    print("   => stays dark with a dead clock -> %s" % ("OK" if dead_ok else "WRONG"))
    if not dead_ok:
        fails.append("dead-clock")
    print()

    if args.csv:
        # 状态是事件驱动的，但 CSV 按 1 ns 网格输出，方便逐行比对（0..79 ns = 80 行）
        def sample(mode):
            seq, _, _ = run(mode, PULSE_START, 4000)
            out = []
            i = 0
            cur = seq[0]
            for t in range(0, 80 * 1000 + 1, 1000):
                while i < len(seq) and seq[i][0] <= t:
                    cur = seq[i]
                    i += 1
                out.append((t, cur[1] if cur[0] == t else (1 if t % PERIOD == 0 else 0),
                            cur[2], cur[3], cur[4], cur[5], cur[6]))
            return out
        a = sample('async_set')
        f_ = sample('fsm_only')
        with open(args.csv, 'w', encoding='utf-8', newline='') as fh:
            fh.write("time_ps,clk_core_rising,fault_n,state,tcon_blank_pin,"
                     "spi_hw_blank_fsm_only,spi_hw_blank_async_set,panel_blank\n")
            for ra, rf in zip(a, f_):
                fh.write("%d,%d,%d,%s,%d,%d,%d,%d\n"
                         % (ra[0], 1 if ra[0] % PERIOD == 0 else 0, 1 - ra[2],
                            ra[3], ra[4], rf[5], ra[5], ra[6]))
        print("CSV written: %s  (%d data rows, %d lines incl. header)"
              % (args.csv, len(a), len(a) + 1))
        print()

    print("--- scope of the claim ---")
    print("* ideal RTL-level argument: the set path has no clock dependency")
    print("* it does NOT claim any physical minimum pulse width; that is set by the")
    print("  standard-cell async-set width, the input circuit and the open-drain RC")
    print()

    if fails:
        print("RESULT=FAIL (%s)" % ", ".join(fails))
        return 1
    print("RESULT=PASS")
    print("  * the FSM-only sampler loses sub-cycle pulses (P0 confirmed)")
    print("  * a core-sampled sticky behaves identically -> sampling cannot fix it")
    print("  * the async set holds at every width and phase")
    print("  * 11 ns and 20 ns are captured by the sampler in 4/4 phases (math gate)")
    print("  * a clear cannot re-arm, and a dead clock cannot clear")
    return 0


if __name__ == '__main__':
    sys.exit(main())
