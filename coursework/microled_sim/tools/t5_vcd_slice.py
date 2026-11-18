#!/usr/bin/env python3
"""Slice a VCD to a time range so the review package stays small.

    python t5_vcd_slice.py <in.vcd> <out.vcd> <t0_ns> <t1_ns>

The output is a self-contained VCD: it replays the accumulated value of every
signal at t0 as a synthetic `#0` dump, then only the changes inside the range,
re-based to 0. Nothing is dropped that changes inside the window.
"""
import sys


def main():
    src, dst, t0_ns, t1_ns = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    t0 = int(t0_ns * 1000)          # 1 ps units
    t1 = int(t1_ns * 1000)
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    # header
    hdr_end = 0
    for i, ln in enumerate(lines):
        if ln.strip() == "$enddefinitions $end":
            hdr_end = i
            break
    header = lines[:hdr_end + 1]

    state = {}
    blocks = []                     # (time, [change lines])
    cur = None
    for ln in lines[hdr_end + 1:]:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            try:
                cur = int(s[1:])
            except ValueError:
                cur = None
            if cur is not None:
                blocks.append((cur, []))
            continue
        if s in ("$dumpoff", "$dumpon", "$end"):
            continue
        if cur is None:
            continue
        blocks[-1][1].append(s)

    def apply(change):
        # returns (id, formatted_value)
        if change[0] in "01xzXZ":
            return change[0:1], change[1:]
        if change[0] in "bB":
            parts = change.split()
            if len(parts) == 2:
                return parts[1], "b" + parts[0][1:]
        return None, None

    for t, ch in blocks:
        if t > t0:
            break
        for c in ch:
            i, v = apply(c)
            if i:
                state[i] = v

    out = list(header)
    out.append("#0")
    for i, v in state.items():
        if v.startswith("b"):
            out.append("%s %s" % (v, i))       # vector change: b<value> <id>
        else:
            out.append("%s%s" % (v, i))        # scalar change: <value><id>
    kept = 0
    for t, ch in blocks:
        if t <= t0 or t > t1:
            continue
        out.append("#%d" % (t - t0))
        out.extend(ch)
        kept += 1
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("%s  blocks_in_range=%d  bytes=%d" % (dst, kept, sum(len(x) + 1 for x in out)))


if __name__ == "__main__":
    main()
