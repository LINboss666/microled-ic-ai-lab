#!/usr/bin/env python3
"""Offline VCD re-slice + per-cycle census for the T5-B LUT-switch window.

The reviewer asked for the real COMMIT -> full slot-1028 dark window -> slot-1029
recovery, taken from the ORIGINAL RUN02 `t5.vcd`, without running ModelSim again.

    python t5_vcd_cycle_report.py <full.vcd> <out.csv> <t0_ns> <t1_ns> [out.vcd]

Writes
  * a per-100MHz-cycle CSV: blank, latch, col_valid(both), lut_bank(both),
    how many of the 768 ch_en bits are high at that instant, and a flag saying
    whether the cycle is inside a BLANK-low display window;
  * optionally a VCD slice of the same range (all signals, re-based to 0).
"""
import sys


def main():
    src, dst_csv, t0_ns, t1_ns = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    dst_vcd = sys.argv[5] if len(sys.argv) > 5 else None
    t0, t1 = int(t0_ns * 1000), int(t1_ns * 1000)

    ids = {"ch0": [], "ch1": [], "scal": {}}
    want = {"d0_lut_bank": "bank0", "d1_lut_bank": "bank1",
            "d0_col_valid": "colv0", "d1_col_valid": "colv1",
            "tcon_blank": "blank", "tcon_latch": "latch",
            "tcon_pwm_tick": "tick"}
    header = []
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            header.append(ln.rstrip("\n"))
            s = ln.strip()
            if s == "$enddefinitions $end":
                break
    for ln in header:
        s = ln.strip()
        if not s.startswith("$var"):
            continue
        p = s.split()
        name = p[4] if len(p) > 4 else ""
        if name.startswith("d0_ch_en"):
            ids["ch0"].append(p[3])
        elif name.startswith("d1_ch_en"):
            ids["ch1"].append(p[3])
        elif name in want:
            ids["scal"][want[name]] = p[3]
    ch0 = set(ids["ch0"]); ch1 = set(ids["ch1"])
    interesting = ch0 | ch1 | set(ids["scal"].values())
    inv = {v: k for k, v in ids["scal"].items()}
    print("ch_en bits: chip0=%d chip1=%d ; scalars=%s"
          % (len(ch0), len(ch1), ",".join(sorted(inv.values()))))

    state = {}
    rows = []
    slope = 10000                      # 10 ns in ps = one 100 MHz cycle
    cur_on = 0
    last_bucket = None

    def emit(t, st):
        on0 = sum(1 for i in ch0 if st.get(i) == "1")
        on1 = sum(1 for i in ch1 if st.get(i) == "1")
        rows.append((t, st.get(ids["scal"]["blank"], "?"),
                     st.get(ids["scal"]["latch"], "?"),
                     st.get(ids["scal"]["colv0"], "?"), st.get(ids["scal"]["colv1"], "?"),
                     st.get(ids["scal"]["bank0"], "?"), st.get(ids["scal"]["bank1"], "?"),
                     on0, on1))

    with open(src, "r", encoding="utf-8", errors="replace") as f:
        started = False
        cur = 0
        dumping = True
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
                try:
                    cur = int(s[1:])
                except ValueError:
                    continue
                if dumping and t0 <= cur <= t1:
                    b = (cur - t0) // slope
                    if last_bucket is not None and b != last_bucket:
                        emit(t0 + last_bucket * slope, state)
                    last_bucket = b
                continue
            if not dumping:
                continue
            # value change: state is tracked for the WHOLE file so that the
            # first row inside the range already has every signal's real value
            if s[0] in "01xzXZ":
                ident = s[1:]
                if ident in interesting:
                    state[ident] = s[0]
            elif s[0] in "bB":
                p = s.split()
                if len(p) == 2 and p[1] in interesting:
                    state[p[1]] = p[0][1:]
    if last_bucket is not None:
        emit(t0 + last_bucket * slope, state)

    with open(dst_csv, "w", encoding="utf-8") as f:
        f.write("t_ns,blank,latch,colv0,colv1,bank0,bank1,ch0_on,ch1_on\n")
        for r in rows:
            f.write("%d,%s,%s,%s,%s,%s,%s,%d,%d\n"
                    % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]))
    print("cycles=%d -> %s" % (len(rows), dst_csv))

    # ---- summary of the interesting span -----------------------------------
    win = [r for r in rows if r[1] == "0"]           # BLANK low
    dark = [r for r in win if r[3] == "0" or r[4] == "0"]
    on = [r for r in win if r[7] or r[8]]
    print("blank_low_cycles=%d  of_which_colv_invalid=%d  of_which_any_conduction=%d"
          % (len(win), len(dark), len(on)))
    flip = None
    prev = None
    for r in rows:
        if prev is not None and prev[5] != r[5]:
            flip = (r[0], prev[5], r[5])
            break
        prev = r
    print("lut_bank0_transition=%s" % (flip,))
    rec = None
    for i in range(1, len(rows)):
        if rows[i - 1][3] == "0" and rows[i][3] == "1":
            rec = rows[i][0]
            break
    print("colv0_0_to_1_ns=%s" % rec)

    if dst_vcd:
        sys.path.insert(0, ".")
        import t5_vcd_slice
        sys.argv = ["t5_vcd_slice.py", src, dst_vcd, str(t0_ns), str(t1_ns)]
        t5_vcd_slice.main()


if __name__ == "__main__":
    main()
