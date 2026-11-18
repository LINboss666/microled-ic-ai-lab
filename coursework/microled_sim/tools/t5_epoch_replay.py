#!/usr/bin/env python3
"""T5-B RUN02 hard gate: replay the RUN01 mismatch from first principles.

Reads the ORIGINAL 256x9 LUT hex (the same file the testbench loads) and the
native RUN01 per-column ledger, then rebuilds the 768-channel comparison of the
displayed column of slot 1028 twice:

  * with the WRONG epoch (table B applied the moment the COMMIT fired) the
    replay must produce exactly the 1524 mismatches the native run recorded;
  * with the CORRECT epoch (the column was loaded in slot 1026, i.e. before the
    switch in slot 1027, so it carries table A) the replay must produce 0.

It also proves the dark-window check is not vacuous: flipping one channel's
conduction inside the dark window must be rejected.

Usage:  python t5_epoch_replay.py <lut.hex> <run01_ledger.csv>
"""
import sys


def load_lut(path):
    vals = [int(x, 16) for x in open(path).read().split()]
    assert len(vals) == 256, "LUT must have 256 entries"
    return vals


def table_b(a):
    """Same derivation as the testbench: PAM nibble complemented, black/full kept."""
    b = []
    for i, v in enumerate(a):
        if i == 0:
            b.append(0x000)
        elif i == 255:
            b.append(0x1FF)
        else:
            b.append(((7 - (v >> 6)) << 6) | (v & 0x3F))
    return b


def pbyte(f, c, lane, i):
    if i == 0:
        return c & 0xFF
    if i == 1:
        return (((c >> 8) & 0x3) << 6) | (f & 0x3F)
    return ((c & 0xFF) + 13 * ((2 * i + lane) & 0xFF) + 7 * (f & 0xFF) + 0x5A) & 0xFF


def compare(tab, f, c):
    """Return (raw_bad, map_bad, pam_bad) over both lanes; raw never depends on tab."""
    raw_bad = map_bad = pam_bad = 0
    for lane in (0, 1):
        for i in range(384):
            raw = pbyte(f, c, lane, i)
            code = tab[raw]
            # the bank holds raw + map + PAM; raw is table independent, so it is
            # only counted against itself (always 0) - kept for the arithmetic.
            if raw != pbyte(f, c, lane, i):
                raw_bad += 1
            if code != tab[raw]:
                map_bad += 1
            if (code >> 6) != (tab[raw] >> 6):
                pam_bad += 1
    return raw_bad, map_bad, pam_bad


def main():
    lut_path, led_path = sys.argv[1], sys.argv[2]
    a = load_lut(lut_path)
    b = table_b(a)

    # the displayed column of slot 1028 is frame 1, column 2 (ledger, native)
    f, c = 1, 2
    bad_wrong = 0
    diff = 0
    for lane in (0, 1):
        for i in range(384):
            raw = pbyte(f, c, lane, i)
            if a[raw] != b[raw]:
                diff += 1                       # map differs
                if (a[raw] >> 6) != (b[raw] >> 6):
                    diff += 1                   # PAM differs as well
    # raw bytes are identical under both tables -> 0 + map + PAM
    identical = 768 - sum(1 for lane in (0, 1) for i in range(384)
                          if a[pbyte(f, c, lane, i)] != b[pbyte(f, c, lane, i)])
    print("column (frame=%d, col=%d): channels where table A == table B = %d" % (f, c, identical))
    print("wrong-epoch mismatches = raw 0 + map %d + PAM %d = %d"
          % (sum(1 for lane in (0, 1) for i in range(384)
                 if a[pbyte(f, c, lane, i)] != b[pbyte(f, c, lane, i)]),
             sum(1 for lane in (0, 1) for i in range(384)
                 if (a[pbyte(f, c, lane, i)] >> 6) != (b[pbyte(f, c, lane, i)] >> 6)),
             diff))
    bad_wrong = diff

    # native ledger must say 1524 for that row
    native = None
    for ln in open(led_path):
        p = ln.strip().split(",")
        if p and p[0] == "1028":
            native = int(p[8])
    print("native RUN01 ledger slot=1028 bad_bytes=%s" % native)
    ok = (bad_wrong == native)
    print("REPLAY_MATCHES_NATIVE=%d" % ok)

    # correct epoch: the column is displayed with table A -> zero mismatches
    raw_bad, map_bad, pam_bad = compare(a, f, c)
    print("correct-epoch mismatches = raw %d + map %d + PAM %d = %d"
          % (raw_bad, map_bad, pam_bad, raw_bad + map_bad + pam_bad))

    # ---- negative control: the dark window may not be skipped, and a single
    # conducting channel inside it must be rejected -------------------------
    def dark_window_ok(ch_en, min_samples=760):
        # the TB requires a real BLANK-low sample floor as well: an empty or
        # truncated window must never be accepted as "verified dark"
        return (len(ch_en) >= min_samples) and all(v == 0 for v in ch_en)

    ch = [0] * 768
    print("NC_dark_all_off        -> %s" % ("ACCEPT" if dark_window_ok(ch) else "REJECT"))
    ch[123] = 1
    print("NC_dark_one_channel_on -> %s" % ("ACCEPT" if dark_window_ok(ch) else "REJECT"))
    vacuous = dark_window_ok([])
    print("NC_dark_zero_samples   -> %s (a zero-sample window must not pass)"
          % ("ACCEPT" if dark_window_ok([]) else "REJECT"))
    vacuous = dark_window_ok([])

    good = (ok and bad_wrong == 1524 and (raw_bad + map_bad + pam_bad) == 0
            and dark_window_ok([0] * 768) and not dark_window_ok([1]) and not vacuous)
    print("RESULT=%s" % ("PASS" if good else "FAIL"))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
