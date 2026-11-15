#!/usr/bin/env python3
"""Static slot-index check for the T1 BOUNDARY phase (T1-V13B).

The T1 B7 assertion compares COL_ID at two slot boundaries and claims the
property "period 1024". That is only meaningful if the two observation points
really sit 1024 slot_start events apart. This script derives the mapping from
the testbench SOURCE TEXT, not from a hand-written table, so a later edit to
the loop bound or to the number of post-loop waits is caught here instead of
being discovered by an expensive ModelSim run.

What it does
  1. extracts the `scen_boundary` task body,
  2. reads the loop bound N from `while (slots < N)`,
  3. reads the base-sample condition `if (slots == K)`,
  4. counts the `@(posedge slot_start)` events AFTER the loop, up to the
     statement that samples `col_slot1026` (and separately `col_slot1025`),
  5. prints the index table and asserts the arithmetic.

Loop semantics used (and verified by the emitted table): `slots` counts
COMPLETED observations and the body runs after the wait, so the iteration with
slots==k observes the START OF SLOT k+1.

Usage:  python t1_slot_index_check.py [path/to/tcon_t1_tb.sv.txt]
Exit:   0 = arithmetic consistent, 1 = inconsistent (do not spend a run)
"""
import re
import sys

DEFAULT = "coursework/microled_sim/tb/tcon_t1_tb.sv.txt"


def task_body(src, name):
    i = src.index("task automatic %s" % name)
    j = src.index("endtask", i)
    return src[i:j]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    src = open(path, encoding="utf-8").read()
    body = task_body(src, "scen_boundary")

    m_bound = re.search(r"while\s*\(\s*slots\s*<\s*(\d+)\s*\)", body)
    if not m_bound:
        print("FAIL: loop bound not found")
        return 1
    n_loop = int(m_bound.group(1))

    m_base = re.search(r"if\s*\(\s*slots\s*==\s*(\d+)\s*\)\s*col_slot2\s*=", body)
    if not m_base:
        print("FAIL: base sample `if (slots == K) col_slot2 = ...` not found")
        return 1
    k_base = int(m_base.group(1))

    # split the body at the end of the while loop, keep the tail
    m_end = re.search(r"slots\s*=\s*slots\s*\+\s*1;\s*end\b", body)
    if not m_end:
        print("FAIL: loop tail not found")
        return 1
    tail = body[m_end.end():]

    # count slot_start waits in the tail before each sample
    def waits_before(varname):
        n = 0
        for line in tail.split("\n"):
            if re.search(r"@\s*\(\s*posedge\s+slot_start\s*\)", line):
                n += 1
            if re.search(r"\b%s\s*=" % re.escape(varname), line):
                return n
        return None

    w1025 = waits_before("col_slot1025")
    w1026 = waits_before("col_slot1026")
    if w1025 is None or w1026 is None:
        print("FAIL: post-loop sample statements not found")
        return 1

    # derived absolute slot indices
    base_slot = k_base + 1                       # iteration slots==K -> slot K+1
    last_loop_slot = n_loop                      # iteration slots==N-1 -> slot N
    s1025 = last_loop_slot + w1025
    s1026 = last_loop_slot + w1026
    gap = s1026 - base_slot

    print("source file            : %s" % path)
    print("loop bound N           : %d" % n_loop)
    print("base sample condition  : slots == %d" % k_base)
    print("post-loop waits to 1025: %d" % w1025)
    print("post-loop waits to 1026: %d" % w1026)
    print()
    print("  loop iteration   observed slot_start   COL_ID sample")
    print("  --------------   -------------------   -------------")
    for it in (0, k_base, n_loop - 2, n_loop - 1):
        tag = ""
        if it == k_base:
            tag = "  <- col_slot2"
        print("  slots == %-6d   start of slot %-6d %s" % (it, it + 1, tag))
    print("  (after loop)     start of slot %-6d   col_slot1025" % s1025)
    print("  (after loop)     start of slot %-6d   col_slot1026" % s1026)
    print()
    print("derived slots: col_slot2 = slot %d, col_slot1025 = slot %d, "
          "col_slot1026 = slot %d" % (base_slot, s1025, s1026))
    print("gap(col_slot1026 - col_slot2) = %d slot boundaries" % gap)

    ok = True
    if s1025 != 1025:
        print("FAIL: the sample labelled col_slot1025 is not taken at slot 1025")
        ok = False
    if s1026 != 1026:
        print("FAIL: the sample labelled col_slot1026 is not taken at slot 1026")
        ok = False
    if gap != 1024:
        print("FAIL: the two compared samples are %d slot boundaries apart, "
              "not 1024" % gap)
        ok = False

    # the assertion must still reference all three values (non-vacuity guard)
    m_chk = re.search(r'chk\("B7_col_id_period_1024_after_wrap",(.*?)\);', body, re.S)
    if not m_chk:
        print("FAIL: B7 assertion not found")
        return 1
    expr = m_chk.group(1)
    for need in ("col_slot1026", "col_slot2", "col_slot1025", "1023", "0"):
        if need not in expr:
            print("FAIL: B7 expression does not mention %r" % need)
            ok = False
    print()
    print("B7 expression           : %s" % " ".join(expr.split()))
    print("RESULT: %s" % ("SLOT_INDEX_OK" if ok else "SLOT_INDEX_BAD"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
