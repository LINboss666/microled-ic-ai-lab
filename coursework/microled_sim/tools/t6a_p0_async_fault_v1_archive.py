#!/usr/bin/env python3
"""T6-A P0-B：短异步故障脉冲的逐时刻推导（零 ModelSim）。

对比三种"谁在锁存故障"：

  (1) FSM_ONLY   现行 tcon_top：`fault_evt = act && (!fault_n)` 只在 clk_ref
                 上升沿采样 -> 短于一个时钟周期的脉冲只要落在两个沿之间就丢失。
  (2) SYNC_ONLY  只加一个 core 时钟采样的粘滞位（`sticky <= sticky | fault`）
                 -> 同样丢失。
  (3) ASYNC_SET  本提案：`always @(posedge clk or posedge fault_assert or negedge rst)`
                 -> 故障**边沿本身**置位，不需要任何时钟沿；清除必须是时钟沿。

输出逐 ns 的时间线 CSV（与审核包里的 ASYNC_FAULT_PULSE_STATIC_TIMELINE.csv 同格式，
但多出 ASYNC_SET 一列），并对若干脉宽做批处理统计。

用法：
    python t6a_p0_async_fault.py                 # 打印 + 写 CSV
    python t6a_p0_async_fault.py --csv out.csv
"""
import argparse
import sys

CLK_NS = 10.0          # 100 MHz
FAULT_MASK = 0x7FF & ~0x100


class Plant:
    """只保留与安全有关的三个量：FSM 状态、粘滞位、许可。"""

    def __init__(self, mode='async_set'):
        self.mode = mode
        self.state = 'ACTIVE'
        self.sticky = 0            # (2) 同步粘滞 / (3) 异步置位锁存
        self.armed = 1             # disp_armed（Host 许可）
        self.fault_assert = 0      # |hw_fault 或 !fault_n
        self.clr = 0               # 软件的"清故障"请求（只在 core 沿有效）

    # ---- 组合项：BLANK 与两个域各自的关断 ----
    def tcon_blank(self):
        # tcon_top: blank = blank_seq | !safe | flt | !act | (act && !disp_ok)
        if self.state != 'ACTIVE':
            return 1
        return 1 if self.fault_assert else 0

    def fsm_latched(self):
        return 1 if self.state == 'FAULT' else 0

    def spi_hw_blank(self):
        if self.mode == 'fsm_only':
            return int(self.fault_assert)
        if self.mode == 'sync_only':
            return int(self.fault_assert or self.sticky or (not self.armed))
        # async_set
        return int(self.fault_assert or self.sticky or (not self.armed))

    def panel_blank(self):
        """集成后的引脚 BLANK = 顶层帧/故障 || SPI 许可（OR，不是选择）。"""
        return int(self.tcon_blank() or self.spi_hw_blank())

    # ---- 异步事件：故障边沿 ----
    def on_fault_edge(self, level):
        self.fault_assert = level
        if level and self.mode == 'async_set':
            self.sticky = 1        # 不等时钟沿

    # ---- 时钟沿 ----
    def on_clk(self):
        # FSM：只在这里采样
        if self.state == 'ACTIVE' and self.fault_assert:
            self.state = 'FAULT'
        # 同步粘滞（模式 2 / 3 的软件可见副本）
        if self.mode in ('sync_only', 'async_set'):
            if self.fault_assert:
                self.sticky = 1
            elif self.clr:
                self.sticky = 0
        # disp_armed 的清除同样在时钟沿
        if self.fault_assert or self.sticky:
            self.armed = 0
        self.clr = 0


def run(mode, pulse_start, pulse_len, total_ns=80, clr_at=None, edges_off=0.0):
    """edges_off 用来把时钟沿相对故障脉冲平移，覆盖相位。"""
    p = Plant(mode)
    rows = []
    t = 0
    while t < total_ns:
        # 故障电平（含 1 ns 分辨率）
        if pulse_start <= t < pulse_start + pulse_len:
            if not p.fault_assert:
                p.on_fault_edge(1)
        else:
            if p.fault_assert:
                p.on_fault_edge(0)
        if clr_at is not None and t == clr_at:
            p.clr = 1
        is_edge = ((t - edges_off) % CLK_NS) == 0 and t >= edges_off
        if is_edge:
            p.on_clk()
        rows.append((t, 1 if is_edge else 0, p.fault_assert,
                     p.state, p.tcon_blank(), p.spi_hw_blank(), p.panel_blank()))
        t += 1
    return rows


def widths():
    return [1, 2, 4, 8, 9, 10, 11, 20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default=None)
    args = ap.parse_args()

    print("=== T6-A P0-B: short asynchronous fault pulse (zero ModelSim) ===")
    print("clock 100 MHz = %g ns, fault pulse starts at t=12 ns" % CLK_NS)
    print()

    fails = []

    # ---------- the reviewer's exact case: 4 ns pulse, edges at 10 and 20 ----------
    rows = run('fsm_only', 12, 4)
    print("--- (1) CURRENT: only the FSM samples the fault ---")
    print("  t  clk  fault  state       tcon_blank  panel_blank")
    for r in rows[:26]:
        print("  %2d %3d %6d  %-10s %10d %12d" % (r[0], r[1], r[2], r[3], r[4], r[6]))
    tail = [r for r in rows if r[0] >= 20]
    lost = all(r[6] == 0 for r in tail)
    print("  after the pulse (t>=20): panel_blank stays 0 -> %s"
          % ("FAULT NOT LATCHED (the reported P0)" if lost else "latched"))
    if not lost:
        fails.append("CE-A current-should-lose")
    print()

    for mode, label in (('sync_only', '(2) SYNC-ONLY sticky (core-sampled)'),
                        ('async_set', '(3) ASYNC-SET / sync-clear (proposal)')):
        rows = run(mode, 12, 4)
        print("--- %s ---" % label)
        print("  t  clk  fault  state       tcon_blank  panel_blank")
        for r in rows[10:26]:
            print("  %2d %3d %6d  %-10s %10d %12d" % (r[0], r[1], r[2], r[3], r[4], r[6]))
        held = all(r[6] == 1 for r in rows[20:])
        print("  after the pulse (t>=20): panel_blank stays 1 -> %s"
              % ("HELD DARK" if held else "NOT HELD (the fault was lost)"))
        if mode == 'async_set' and not held:
            fails.append("CE-B proposal-must-hold")
        if mode == 'sync_only' and held:
            fails.append("CE-B sync-only-should-lose")
        print()

    # ---------- pulse-width sweep x clock phase ----------
    print("--- pulse-width sweep: does the panel stay dark after the pulse? ---")
    print("  width  phase  fsm_only  sync_only  async_set")
    worst = {}
    for w in widths():
        for off in (0.0, 2.5, 5.0, 7.5):
            res = []
            for mode in ('fsm_only', 'sync_only', 'async_set'):
                rr = run(mode, 12, w, total_ns=80, edges_off=off)
                res.append(1 if all(r[6] == 1 for r in rr if r[0] >= 12 + w) else 0)
            worst.setdefault(w, []).append(res)
            print("  %5d  %5.1f  %8d  %9d  %9d" % (w, off, res[0], res[1], res[2]))
    print()
    any_lost = any(r[0] == 0 for v in worst.values() for r in v)
    all_held = all(r[2] == 1 for v in worst.values() for r in v)
    print("  fsm_only loses at least one width/phase: %s (expected Yes)" % ("Yes" if any_lost else "No"))
    print("  async_set holds every width/phase  : %s (expected Yes)" % ("Yes" if all_held else "No"))
    if not any_lost:
        fails.append("CE-C fsm-only-should-lose-somewhere")
    if not all_held:
        fails.append("CE-C async-set-must-hold-everywhere")
    # a 10 ns pulse that straddles an edge is the "lucky" case
    rr = run('fsm_only', 12, 10)
    lucky = all(r[6] == 1 for r in rr if r[0] >= 22)
    print("  10 ns pulse (12..21, straddles the 20 ns edge): fsm_only holds = %s" % lucky)
    print()

    # ---------- clear protocol: only after the source is gone, and it does not re-arm ----------
    print("--- clear protocol (async_set) ---")
    p = Plant('async_set')
    log = []

    def step(t, fault, clr=False, note=''):
        p.on_fault_edge(fault)
        if clr:
            p.clr = 1
        p.on_clk()
        log.append((t, fault, p.sticky, p.armed, p.panel_blank(), note))

    step(10, 0, note='display on')
    step(20, 1, note='fault edge (async set)')
    step(30, 0, note='source gone, no W1C')
    step(40, 0, clr=True, note='W1C clears the sticky')
    step(50, 0, note='still no re-enable')
    print("   t  fault sticky armed blank  note")
    for r in log:
        print("  %2d %5d %6d %5d %5d  %s" % r)
    ok = (log[1][4] == 1 and log[2][4] == 1 and log[3][4] == 1
          and log[4][3] == 0 and log[4][4] == 1)
    print("  clear did NOT re-arm the panel -> %s" % ("OK" if ok else "WRONG"))
    if not ok:
        fails.append("CE-D clear-must-not-rearm")
    print()

    # ---------- dead clock ----------
    print("--- core clock stopped ---")
    p = Plant('async_set')
    p.on_fault_edge(1)                       # no clk edge at all
    print("  fault asserted with no clock edge: sticky=%d blank=%d"
          % (p.sticky, p.panel_blank()))
    dead_ok = (p.sticky == 1 and p.panel_blank() == 1)
    p2 = Plant('async_set')
    p2.on_fault_edge(1)
    p2.clr = 1                                # no clock edge -> the clear cannot run
    print("  a clear request cannot run without a clock edge: sticky=%d" % p2.sticky)
    dead_ok = dead_ok and (p2.sticky == 1)
    print("  => hardware stays dark while the clock is dead -> %s"
          % ("OK" if dead_ok else "WRONG"))
    if not dead_ok:
        fails.append("CE-E dead-clock")
    print()

    # ---------- CSV ----------
    if args.csv:
        rows = run('async_set', 12, 4)
        with open(args.csv, 'w', encoding='utf-8', newline='') as f:
            f.write("time_ns,clk_ref_rising,fault_n,state,tcon_blank_pin,"
                    "spi_hw_blank_fsm_only,spi_hw_blank_async_set,panel_blank\n")
            for r in rows:
                f.write("%d,%d,%d,%s,%d,%d,%d,%d\n"
                        % (r[0], r[1], 1 - r[2], r[3],
                           r[4], int(r[2]), r[5], r[6]))
        print("CSV written: %s" % args.csv)
        print()

    if fails:
        print("RESULT=FAIL (%s)" % ", ".join(fails))
        return 1
    print("RESULT=PASS")
    print("  * the current FSM-only sampling loses a sub-cycle pulse (P0 confirmed)")
    print("  * a core-sampled sticky does not help")
    print("  * an asynchronous-set / synchronous-clear latch holds at every width and phase")
    print("  * the clear cannot re-arm the panel, and a dead clock cannot clear it")
    return 0


if __name__ == '__main__':
    sys.exit(main())
