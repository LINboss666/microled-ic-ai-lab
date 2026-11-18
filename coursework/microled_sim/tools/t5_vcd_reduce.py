#!/usr/bin/env python3
"""Reduce a VCD to a chosen signal subset and a time range.

    python t5_vcd_reduce.py <in.vcd> <out.vcd> <t0_ns> <t1_ns> <name,name,...>

Keeps only the header entries of the selected signals, replaying their value at
t0 as a synthetic `#0` dump, then the changes inside the window re-based to 0.
A 100 MB window becomes a few hundred kB and stays replayable.
"""
import sys


def main():
    src, dst = sys.argv[1], sys.argv[2]
    t0, t1 = int(float(sys.argv[3]) * 1000), int(float(sys.argv[4]) * 1000)
    want = set(sys.argv[5].split(","))

    header, ids = [], {}
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.strip()
            if s.startswith("$var"):
                p = s.split()
                if len(p) > 4 and p[4] in want:
                    header.append(ln.rstrip("\n"))
                    ids[p[3]] = p[4]
            elif s == "$enddefinitions $end":
                header.append(ln.rstrip("\n"))
                break
            elif s.startswith(("$date", "$version", "$timescale", "$scope",
                               "$upscope", "$comment", "$end")) or ln.startswith("\t"):
                header.append(ln.rstrip("\n"))
    print("kept %d signals (requested %d)" % (len(ids), len(want)))
    if not ids:
        raise SystemExit("no signal matched")

    # ---- state at t0 (stream the whole file once) ------------------------
    state, cur, started, dumping = {}, 0, False, True
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.strip()
            if not started:
                if s == "$enddefinitions $end":
                    started = True
                continue
            if not s:
                continue
            if s == "$dumpoff":
                dumping = False
                continue
            if s == "$dumpon":
                dumping = True
                continue
            if s.startswith("#"):
                cur = int(s[1:])
                if cur > t0:
                    break
                continue
            if not dumping:
                continue
            if s[0] in "01xzXZ" and s[1:] in ids:
                state[s[1:]] = s
            elif s[0] in "bB":
                p = s.split()
                if len(p) == 2 and p[1] in ids:
                    state[p[1]] = "%s %s" % (p[0], p[1])

    # ---- header + t0 dump + in-range changes ----------------------------
    out = list(header)
    out.append("#0")
    for i, v in state.items():
        out.append(v)

    cur, started, dumping, last_t = 0, False, True, None
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            s = ln.strip()
            if not started:
                if s == "$enddefinitions $end":
                    started = True
                continue
            if not s:
                continue
            if s == "$dumpoff":
                dumping = False
                continue
            if s == "$dumpon":
                dumping = True
                continue
            if s.startswith("#"):
                cur = int(s[1:])
                if cur > t1:
                    break
                continue
            if not dumping or cur <= t0:
                continue
            body = None
            if s[0] in "01xzXZ" and s[1:] in ids:
                body = s
            elif s[0] in "bB":
                p = s.split()
                if len(p) == 2 and p[1] in ids:
                    body = "%s %s" % (p[0], p[1])
            if body is None:
                continue
            if cur != last_t:
                out.append("#%d" % (cur - t0))
                last_t = cur
            out.append(body)

    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("wrote %s (%d lines, %d bytes)" % (dst, len(out),
                                             sum(len(x) + 1 for x in out)))


if __name__ == "__main__":
    main()
