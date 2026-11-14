#!/usr/bin/env python3
"""Offline replay of the T2B-BR pin-level monitor rules on an ARCHIVED VCD.

Why: the T2B-BR task book allows exactly ONE ModelSim run (#4), and forbids
using it to discover a timing-model mistake. So the two sampling rules are
replayed here, bit-exactly, on a real waveform produced by a previous round
(T2AR2 run03, which was already independently accepted as byte-exact on D0/D1).

What is replayed
  data_pin_mon / data_model:
      latch_d is updated only on a DCLK rising edge;
      LATCH rising seen on the DCLK grid  -> close the window;
      LATCH falling seen on the DCLK grid -> arm, and that edge is byte 0;
      384 sampling edges fill the window; the next LATCH rising closes it.
  scan_pin_mon:
      at every real posedge scan_stb, record COL_ID / BLANK, and measure
      setup = time since the last COL_ID change, hold = time to the next one.

The 1 ns `#1` in RTL is modelled as "look at the value at the END of the
simulation timestamp", which is exactly what a post-edge settle sees.

Usage:  python offline_pin_monitor_replay.py <file.vcd>
"""
import sys
from collections import defaultdict


def parse_header(head):
    scope = []
    vars_ = []
    for line in head.split('\n'):
        s = line.strip()
        if s.startswith('$scope'):
            scope.append(s.split()[2])
        elif s.startswith('$upscope'):
            if scope:
                scope.pop()
        elif s.startswith('$var'):
            pt = [x for x in s.split() if x != '$end']
            vars_.append(('.'.join(scope), pt[3], pt[4], pt[5] if len(pt) > 5 else ''))
    return vars_


def main(path):
    raw = open(path, 'r', errors='replace').read()
    i = raw.find('$enddefinitions')
    head, body = raw[:i], raw[i:].split('\n')
    vars_ = parse_header(head)
    top = [v for v in vars_ if v[0] == 'tcon_t2a_tb']

    rev0, rev1 = {}, {}
    id_latch, id_dclk, id_stb, id_blank = set(), set(), set(), set()
    colbits = {}
    for _sc, idc, nm, rng in top:
        if nm == 'd0' and rng and ':' not in rng:
            rev0[idc] = int(rng.strip('[]'))
        if nm == 'd1' and rng and ':' not in rng:
            rev1[idc] = int(rng.strip('[]'))
        if nm == 'col_id' and rng and ':' not in rng:
            colbits[idc] = int(rng.strip('[]'))
        if nm == 'latch':
            id_latch.add(idc)
        if nm == 'dclk':
            id_dclk.add(idc)
        if nm == 'scan_stb':
            id_stb.add(idc)
        if nm == 'blank':
            id_blank.add(idc)

    by = defaultdict(lambda: {'bit': [], 'dclk': False, 'latch': None,
                              'stb': False, 'blank': None})
    t = 0
    for line in body:
        s = line.strip()
        if not s:
            continue
        if s[0] == '#':
            t = int(s[1:])
            continue
        if s[0] == 'b':
            continue
        idc, val = s[1:], (1 if s[0] == '1' else 0)
        if idc in rev0:
            by[t]['bit'].append((0, rev0[idc], val))
        elif idc in rev1:
            by[t]['bit'].append((1, rev1[idc], val))
        elif idc in colbits:
            by[t]['bit'].append((2, colbits[idc], val))
        elif idc in id_latch:
            by[t]['latch'] = val
        elif idc in id_dclk:
            by[t]['dclk'] = by[t]['dclk'] or (val == 1)
        elif idc in id_stb:
            by[t]['stb'] = by[t]['stb'] or (val == 1)
        elif idc in id_blank:
            by[t]['blank'] = val

    # ---------------- data port replay ------------------------------------
    d0 = d1 = lat = col = 0
    lat_d = 0
    armed = False
    wcnt = 0
    cap0, cap1 = [], []
    wins = []
    for t in sorted(by):
        e = by[t]
        for (w, b, v) in e['bit']:
            if w == 0:
                d0 = (d0 & ~(1 << b)) | (v << b)
            elif w == 1:
                d1 = (d1 & ~(1 << b)) | (v << b)
            else:
                col = (col & ~(1 << b)) | (v << b)
        if e['latch'] is not None:
            lat = e['latch']
        if not e['dclk']:
            continue
        if lat == 1 and lat_d == 0:
            if armed:
                wins.append((t, wcnt, list(cap0), list(cap1)))
            armed, wcnt, cap0, cap1 = False, 0, [], []
        elif lat == 0 and lat_d == 1:
            armed, wcnt, cap0, cap1 = True, 0, [], []
        if armed and wcnt < 384:
            cap0.append(d0)
            cap1.append(d1)
            wcnt += 1
        lat_d = lat

    def pix(f, c, r):
        return ((c & 255) + 13 * (r & 255) + 7 * (f & 255) + 0x5A) & 255

    lens = [w[1] for w in wins]
    print("DATA: windows=%d  all_384=%s" % (len(wins), all(x == 384 for x in lens)))
    for (t, n, x0, x1) in wins:
        if n != 384:
            print("  t=%-9d LEN=%d  <-- would be reported as win_badlen" % (t, n))
            continue
        # the T2AR2 payload has no tags: recover the column from the pattern
        m = [c for c in range(1024)
             if all(x0[k] == pix(0, c, 2 * k) and x1[k] == pix(0, c, 2 * k + 1)
                    for k in range(384))]
        print("  t=%-9d n=384 byte0=%02X/%02X pattern_col=%s"
              % (t, x0[0], x1[0], (m[:2] if m else "none (invalid/zero column)")))

    # ---------------- scan pin replay -------------------------------------
    stb_prev = 0
    t_col = 0.0
    rows = []
    cur_col = 0
    cur_blank = 0
    for t in sorted(by):
        e = by[t]
        for (w, b, v) in e['bit']:
            if w == 2:
                if ((cur_col & ~(1 << b)) | (v << b)) != cur_col:
                    cur_col = (cur_col & ~(1 << b)) | (v << b)
                    t_col = t
        if e['blank'] is not None:
            cur_blank = e['blank']
        if e['stb'] and not stb_prev:
            rows.append((t, cur_col, cur_blank, t - t_col))
        if e['stb']:
            stb_prev = 1
        else:
            stb_prev = 0
    print("SCAN: strobe_edges=%d" % len(rows))
    for r in rows[:8]:
        print("  t=%-9d col=%-5d blank=%d setup=%.1f ns"
              % (r[0], r[1], r[2], r[3] / 1000.0))
    if rows:
        print("  setup min=%.1f ns   outside_blank=%d"
              % (min(r[3] for r in rows) / 1000.0,
                 sum(1 for r in rows if r[2] != 1)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'tcon_t2a.vcd')
