#!/usr/bin/env python3
"""Render the T2A data-path timing diagram from the REAL run-4 VCD.

Standard library only (no matplotlib), so the figure can be regenerated on any
machine that produced the simulation. Every plotted value is read from the VCD;
nothing is synthesised. The window is centred on the first load_active rising
edge, which is where byte-0 pre-fetch, the first DCLK sampling edge and the
D0/D1 byte stream all meet.

Usage:
    python render_t2a_wave.py --vcd <tcon_t2a.vcd> --out <fig.svg> [--cycles 44]
"""
import argparse
import os

SAMPLES = [
    ("dclk", "tcon_t2a_tb.dut.dclk", "bit"),
    ("load_active", "tcon_t2a_tb.dut.load_active", "bit"),
    ("latch", "tcon_t2a_tb.dut.latch", "bit"),
    ("blank", "tcon_t2a_tb.dut.blank", "bit"),
    ("D0 (rows 2k)", "tcon_t2a_tb.dut.d0", "byte"),
    ("D1 (rows 2k+1)", "tcon_t2a_tb.dut.d1", "byte"),
]


def parse_vcd(path):
    """Parse a flat VCD.

    ModelSim declares the SAME identifier code for every hierarchical alias of
    one net (TB-level signal, DUT port, internal driver). A one-name-per-code
    map silently drops all but the last alias - which is why the first attempt
    saw zero transitions on dclk/load_active. Codes are therefore mapped to a
    LIST of names and every change is recorded under all of them.
    """
    scopes, ids, series = [], {}, {}
    t = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("$scope"):
                scopes.append(s.split()[2])
                continue
            if s.startswith("$upscope"):
                if scopes:
                    scopes.pop()
                continue
            if s.startswith("$var"):
                pr = s.split()
                try:
                    width = int(pr[2])
                except ValueError:
                    width = 1
                suffix = pr[5] if len(pr) > 5 and pr[5].startswith("[") else ""
                ids.setdefault(pr[3], []).append((".".join(scopes + [pr[4]] + ([suffix] if suffix else [])), width))
                continue
            if s.startswith("#"):
                t = int(s[1:])
                continue
            if not s:
                continue
            if s[0] == "b":
                pr = s.split()
                if len(pr) == 2 and pr[1] in ids:
                    bits = pr[0][1:]
                    val = int(bits, 2) if bits and all(c in "01" for c in bits) else 0
                    for nm, width in ids[pr[1]]:
                        if width > 1:            # vector change <-> vector signal
                            series.setdefault(nm, []).append((t, val))
            elif s[0] in "01xz" and len(s) > 1:
                if s[1:] in ids:
                    for nm, width in ids[s[1:]]:
                        if width == 1:           # scalar change <-> 1-bit signal
                            series.setdefault(nm, []).append((t, s[0]))
    return series


def byte_series(ser, base):
    """Rebuild an 8-bit value from ModelSim's bit-blasted per-bit variables.

    ModelSim dumps d0/d1 as eight independent 1-bit variables named
    "d0 [7]" ... "d0 [0]" when the net is a concatenation, so the byte has to be
    reassembled from the individual bits. Returns [(t, value), ...] or None.
    """
    bits = []
    for i in range(8):
        nm = None
        for cand in ("%s.[%d]" % (base, i), "%s [%d]" % (base, i)):
            if cand in ser:
                nm = cand
                break
        if nm is None:
            return None
        bits.append((i, ser[nm]))
    times = sorted({t for _, ev in bits for t, _ in ev})
    state = [0] * 8
    for i, ev in bits:
        for t, v in ev:
            if t == -1:
                continue
            if v == "1":
                state[i] = 1
            elif v == "0":
                state[i] = 0
    # replay in time order
    idx = [0] * 8
    out = []
    for t in times:
        for i, ev in bits:
            while idx[i] < len(ev) and ev[idx[i]][0] <= t:
                v = ev[idx[i]][1]
                state[i] = 1 if v == "1" else 0
                idx[i] += 1
        val = 0
        for i in range(8):
            if state[i]:
                val |= 1 << i
        out.append((t, val))
    return out


def window_events(events, t0, t1):
    """Events inside [t0,t1] with the value in force at t0 prepended."""
    out, cur = [], None
    for t, v in events:
        if t <= t0:
            cur = v
        elif t <= t1:
            out.append((t, v))
    return cur, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cycles", type=int, default=44)
    args = ap.parse_args()

    ser = parse_vcd(args.vcd)
    rises = [t for t, v in ser.get("tcon_t2a_tb.dut.load_active", []) if v == "1"]
    if not rises:
        raise SystemExit("no load_active rising edge found in the VCD")

    t_mark = rises[0]                       # ps
    t0 = t_mark - 20000
    t1 = t_mark + args.cycles * 10000

    W, LEFT, RIGHT = 1240, 190, 1180
    ROW_H, TOP = 78, 96
    H = TOP + ROW_H * len(SAMPLES) + 70

    def x(t):
        return LEFT + (t - t0) * (RIGHT - LEFT) / float(t1 - t0)

    parts = []
    parts.append(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="DejaVu Sans, Arial, sans-serif">\n'
        % (W, H, W, H)
    )
    parts.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>\n' % (W, H))
    parts.append(
        '<text x="%.0f" y="34" font-size="15" fill="#111">'
        'TCON T2A real data path — from the run-4 VCD (no synthesised data)</text>\n'
        % (W * 0.03)
    )
    parts.append(
        '<text x="%.0f" y="56" font-size="12" fill="#555">'
        'DCLK 50 MHz, 384 sampling edges per load window, D0 = even rows 2k, '
        'D1 = odd rows 2k+1; window opens at cycle 832</text>\n' % (W * 0.03)
    )

    # vertical grid every 100 ns
    grid0 = (t0 // 100000) * 100000
    gt = grid0
    while gt <= t1:
        gx = x(gt)
        parts.append(
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#e6e6e6" '
            'stroke-width="1"/>\n' % (gx, TOP - 24, gx, TOP + ROW_H * len(SAMPLES))
        )
        parts.append(
            '<text x="%.2f" y="%d" font-size="9" fill="#777" text-anchor="middle">'
            '%.0f</text>\n' % (gx, TOP + ROW_H * len(SAMPLES) + 16, gt / 1000.0)
        )
        gt += 100000

    parts.append(
        '<text x="%.2f" y="%d" font-size="10" fill="#444" text-anchor="end">'
        'time (ns)</text>\n' % (RIGHT + 40, TOP + ROW_H * len(SAMPLES) + 34)
    )

    for i, (label, name, kind) in enumerate(SAMPLES):
        y_mid = TOP + i * ROW_H + ROW_H * 0.55
        parts.append(
            '<text x="%d" y="%.1f" font-size="11" fill="#111" text-anchor="end">%s</text>\n'
            % (LEFT - 12, y_mid + 4, label)
        )
        events = ser.get(name)
        if events is None:
            events = byte_series(ser, name)
        cur, evs = window_events(events or [], t0, t1)
        if cur is None:
            continue
        lo, hi = (y_mid + 16, y_mid - 16) if kind == "bit" else (y_mid + 24, y_mid - 24)

        def yv(v):
            if kind == "bit":
                return lo if v == "1" or v == 1 else hi
            return lo - (min(int(v), 255) / 255.0) * (lo - hi)

        pts = [(x(t0), yv(cur))]
        for t, v in evs:
            pts.append((x(t), yv(cur)))
            pts.append((x(t), yv(v)))
            cur = v
        pts.append((x(t1), yv(cur)))
        colour = "#1f6feb" if kind == "bit" else "#8250df"
        d = " ".join("%.2f,%.2f" % p for p in pts)
        parts.append(
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.6"/>\n'
            % (d, colour)
        )
        if kind == "byte":
            parts.append(
                '<text x="%.1f" y="%.1f" font-size="9" fill="#8250df">0x00</text>\n'
                % (LEFT + 4, lo + 12)
            )
            parts.append(
                '<text x="%.1f" y="%.1f" font-size="9" fill="#8250df">0xFF</text>\n'
                % (LEFT + 4, hi + 2)
            )

    # marker at the load-window opening
    mx = x(t_mark)
    parts.append(
        '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#d1242f" '
        'stroke-width="1.4" stroke-dasharray="5,3"/>\n'
        % (mx, TOP - 18, mx, TOP + ROW_H * len(SAMPLES))
    )
    parts.append(
        '<text x="%.2f" y="%d" font-size="11" fill="#d1242f">'
        'load window opens (cycle 832, byte 0 pre-fetched on the previous falling edge)'
        '</text>\n' % (mx + 6, TOP - 24)
    )
    parts.append("</svg>\n")

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(parts))
    print("wrote", args.out, os.path.getsize(args.out), "bytes")
    print("window_ns %.1f -> %.1f" % (t0 / 1000.0, t1 / 1000.0))


if __name__ == "__main__":
    main()
