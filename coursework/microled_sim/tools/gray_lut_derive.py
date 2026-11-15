#!/usr/bin/env python3
"""Derive the 3-bit PAM + 6-bit PWM gray LUT exactly as V1.3 §7 段0236 describes.

FROZEN by V1.3 (not invented here):
  * I_PAMk = (k+1) * 15/8 uA for k = 0..7            (段0236, "示例仅取...")
  * time code: 0 -> off, 1..62 -> that many ticks, 63 -> 64 ticks (段0218)
  * 3-bit PAM + 6-bit PWM = 8 x 64 = 512 control combinations (段0231/0233)
  * 9-bit LUT word: [8:6] PAM, [5:0] PWM (段0687 GRAY_MAP_DATA)
  * a 256-entry LUT maps the 8-bit video byte to that 9-bit word (段0218)
  * black code must be fully off, max code must be highest tier + full window (段0218)

DERIVED by this script (V1.3 states the algorithm and four resulting numbers,
but the machine-readable table is not part of the handoff):
  1. enumerate 8 tiers x 64 time codes, Q = I * ticks (integer arithmetic in
     units of 1 tick x 15/8 uA),
  2. de-duplicate identical charge values          -> V1.3 says 268
  3. sort ascending, select 256 entries evenly     -> the "256码排序抽样LUT"
  4. report min adjacent spacing                   -> V1.3 says 1/512 full scale
  5. report max |Q - linear| / full scale          -> V1.3 says 21.78 %

If step 2/4/5 do not reproduce 268 / 1-of-512 / 21.78 %, the derivation is NOT
the one V1.3 used and the table must be treated as OPEN. This script exits
non-zero in that case so a build cannot silently use a wrong table.

Outputs:
  t3b/GRAY_LUT_DEFAULT.hex.txt 256 lines "pam3_pwm6" (9-bit hex, e.g. "3F")
  t3b/GRAY_LUT_DEFAULT.csv     code, Q_units, pam, pwm, ticks, if_tiers
  stdout                       the derivation report
"""
import sys
from fractions import Fraction as F

QMAX_UNITS = 8 * 64          # 512 = one full-scale charge in units


def ticks(t):
    return 0 if t == 0 else (64 if t == 63 else t)


def main():
    q = {}
    for k in range(8):
        for t in range(64):
            q.setdefault((k + 1) * ticks(t), []).append((k, t))
    avail = sorted(q)
    n_uniq = len(avail)

    n = len(avail)
    picks = [avail[round(j * (n - 1) / 255)] for j in range(256)]
    mono = all(picks[i] < picks[i + 1] for i in range(255))

    lin = [F(j * QMAX_UNITS, 255) for j in range(256)]
    dev_fs = max(abs(F(picks[j]) - lin[j]) / QMAX_UNITS for j in range(256))

    min_gap_all = min(avail[i + 1] - avail[i] for i in range(n - 1))
    min_gap_sel = min(picks[i + 1] - picks[i] for i in range(255))

    print("=== V1.3 §7 段0236 derivation ===")
    print("enumerated combinations          : %d" % (8 * 64))
    print("distinct charge values (dedup)   : %d      V1.3 says 268  -> %s"
          % (n_uniq, "MATCH" if n_uniq == 268 else "MISMATCH"))
    print("full scale                       : %d units" % QMAX_UNITS)
    print("selected codes                   : %d" % len(picks))
    print("monotone                         : %s" % mono)
    print("min adjacent gap, all 268        : %d  (= 1/%d FS)  V1.3 says 1/512 -> %s"
          % (min_gap_all, QMAX_UNITS,
             "MATCH" if min_gap_all == 1 else "MISMATCH"))
    print("min adjacent gap, selected 256   : %d" % min_gap_sel)
    print("max |Q - linear| / FS            : %.4f %%   V1.3 says 21.78 %% -> %s"
          % (float(dev_fs) * 100,
             "MATCH" if abs(float(dev_fs) * 100 - 21.78) < 0.005 else "MISMATCH"))
    print("black code (video 0)             : Q=0, code = PAM %d / PWM %d"
          % (q[picks[0]][0][0], q[picks[0]][0][1]))
    print("max code (video 255)             : Q=%d, code = PAM %d / PWM %d"
          % (picks[255], q[picks[255]][0][0], q[picks[255]][0][1]))

    ok = (n_uniq == 268 and mono and min_gap_all == 1 and picks[0] == 0
          and picks[255] == QMAX_UNITS
          and abs(float(dev_fs) * 100 - 21.78) < 0.005)
    # the two "must" rules of 段0218
    black = q[picks[0]][0]
    top = q[picks[255]][0]
    black_off = (black[1] == 0)
    top_full = (top[0] == 7 and top[1] == 63)
    print("rule: black fully off            : %s (PWM code %d)" % (black_off, black[1]))
    print("rule: max = highest tier + full  : %s (PAM %d / PWM %d)"
          % (top_full, top[0], top[1]))
    ok = ok and black_off and top_full

    # write the artifacts
    lines = []
    for j, qq in enumerate(picks):
        k, t = q[qq][0]
        word = (k << 6) | t
        lines.append("%02X" % word)
    open("coursework/microled_sim/t3b/GRAY_LUT_DEFAULT.hex.txt", "w", newline="\n").write(
        "\n".join(lines) + "\n")
    rows = ["code,q_units,pam_level,pwm_code,ticks,current_uA_x8"]
    for j, qq in enumerate(picks):
        k, t = q[qq][0]
        rows.append("%d,%d,%d,%d,%d,%d" % (j, qq, k, t, ticks(t), k + 1))
    open("coursework/microled_sim/t3b/GRAY_LUT_DEFAULT.csv", "w", newline="\n").write(
        "\n".join(rows) + "\n")

    print()
    print("RESULT: %s" % ("DERIVED_REPRODUCES_V13" if ok else "DERIVED_MISMATCH_OPEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
