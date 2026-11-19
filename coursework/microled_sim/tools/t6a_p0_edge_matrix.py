#!/usr/bin/env python3
"""T6-A P0 §C：单沿状态矩阵（严格 NBA 语义，零 ModelSim）。

任务书要求"用实际 Verilog 的 NBA 先旧值后新值写出 W1C、CTRL 再使能、live fault
同沿的精确状态表"。本脚本对每个组合打印 **本沿之前(OLD)** 与 **本沿之后(NEW)**
的 en / blank_r / fault_status / disp_armed / hw_fault_caught，
并给出该沿的 hw_blank（组合项用的是 OLD 值，与 RTL 一致）。

三种起点：
  ARMED   正常显示中（en=1, blank_r=0, armed=1, 无锁存故障）
  DARK    故障后熄屏（en=1, blank_r=0, armed=0, caught=1, latched=UVLO）
  CLEARED 已 W1C 清完、仍未再使能（armed=0, caught=0, latched=0）

用法：python t6a_p0_edge_matrix.py [--csv out.csv]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t6a_p0_rearm_check import Regs          # noqa: E402


def start(kind):
    p = Regs()
    if kind == 'ARMED':
        p.edge(ctrl=0b11, safe=1, ready=0)
        p.edge(ctrl=0b01, safe=1, ready=1)
    elif kind == 'DARK':
        p.edge(ctrl=0b11, safe=1, ready=0)
        p.edge(ctrl=0b01, safe=1, ready=1)
        p.edge(hw_fault=0b001)
        p.edge(hw_fault=0b001)
        p.edge(hw_fault=0)
    elif kind == 'CLEARED':
        p.edge(ctrl=0b11, safe=1, ready=0)
        p.edge(ctrl=0b01, safe=1, ready=1)
        p.edge(hw_fault=0b001)
        p.edge(hw_fault=0)
        # 捕获位以 COMM_TO(bit7) 的掩码清除，见 FAULT_REARM_PROTOCOL.md
        p.edge(hw_fault=0, w1c=0b001 | 0x080, fw=True)
        p.edge(hw_fault=0)
    return p


def snapshot(p):
    return (p.en, p.blank_r, p.fault_status, p.disp_armed, p.caught)


def fmt(st):
    return "en=%d blk=%d fault=0x%03X armed=%d caught=%d" % st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default=None)
    args = ap.parse_args()

    rows = []
    print("=== single-edge matrix (OLD -> NEW), NBA semantics ===")
    print("hw_blank is evaluated from the OLD registers, exactly like the RTL.")
    print()
    for kind in ('ARMED', 'DARK', 'CLEARED'):
        for ctrl in (None, 0b01, 0b11):
            for w1c in (0, 0b001):
                for hwf in (0, 0b1000):
                    p = start(kind)
                    old = snapshot(p)
                    blk_old = p.hw_blank(hwf)
                    err = p.edge(hw_fault=hwf, ctrl=ctrl, w1c=w1c,
                                 safe=1, ready=1, fw=bool(w1c) or ctrl is None)
                    new = snapshot(p)
                    rows.append((kind, ctrl, w1c, hwf, old, blk_old, new,
                                 p.hw_blank(hwf), err))
    print("  %-8s| %-4s| %-6s| %-6s| %-13s| %-13s| %-4s| %s"
          % ("start", "ctrl", "w1c", "fault", "blank_old(f)", "blank_new(f)", "rej",
             "NEW state"))
    for r in rows:
        c = "-" if r[1] is None else "0x%X" % r[1]
        print("  %-8s| %-4s| 0x%03X | 0x%03X | %-13d| %-13d| %-4d| %s"
              % (r[0], c, r[2], r[3], r[5], r[7], r[8], fmt(r[6])))
    print()

    if args.csv:
        with open(args.csv, 'w', encoding='utf-8', newline='') as f:
            f.write("start,ctrl,w1c,hw_fault,hw_blank_old,en_old,blk_old,fault_old,"
                    "armed_old,caught_old,rejected,hw_blank_new,en_new,blk_new,"
                    "fault_new,armed_new,caught_new\n")
            for r in rows:
                c = "" if r[1] is None else str(r[1])
                f.write("%s,%s,0x%03X,0x%03X,%d,%d,%d,0x%03X,%d,%d,%d,%d,%d,%d,0x%03X,%d,%d\n"
                        % (r[0], c, r[2], r[3], r[5],
                           r[4][0], r[4][1], r[4][2], r[4][3], r[4][4],
                           r[8], r[7],
                           r[6][0], r[6][1], r[6][2], r[6][3], r[6][4]))
        print("CSV written: %s" % args.csv)

    # 三条"必须成立"的性质，逐条断言
    fails = []
    # 1. 任何"live fault + ctrl unblank"的被拒，且不会被置 armed
    for r in rows:
        if r[1] == 0b01 and r[3] and r[4][4] is not None:
            if not (r[8] == 1 and r[6][3] == 0):
                fails.append("live-fault+unblank should be rejected and not armed")
    # 2. DARK 起点只要没有 ctrl，无论 W1C 与否都不会 armed
    for r in rows:
        if r[0] == 'DARK' and r[1] is None and r[6][3] == 1:
            fails.append("DARK must never end up armed without a CTRL write")
    # 3. hw_blank 不能因为 W1C 而从 1 直接变 0（除非同时被显式再使能）
    for r in rows:
        if r[2] and r[1] is None and r[5] == 1 and r[7] == 0:
            fails.append("a W1C alone flipped hw_blank 1->0")
    print()
    if fails:
        print("RESULT=FAIL")
        for f in set(fails):
            print("  -", f)
        return 1
    print("RESULT=PASS  (%d combinations, NBA order)" % len(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
