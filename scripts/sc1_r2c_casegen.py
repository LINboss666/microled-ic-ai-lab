#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2C: standalone generator for the event-attribution cases.

    python scripts/sc1_r2c_casegen.py --outdir DIR [--only case_name]

Deliberately standalone: the reviewer asked for the synthetic inputs to be reproducible without
importing a module that executes a whole test suite at import time. Every deck here is a two-signal
transient PSF-ASCII file with a strictly increasing time axis, no PDK and no simulator involved.

Cases (1.8 V / 3.3 V and the ns values are POC_ASSUMPTION tool-test conditions only):

  a1          input 50 % rises at 2.500 ns, then falls back through 50 % at 5.642857 ns (the low
              plateau 0.4 V is ABOVE the 10 % threshold, so no complete 10-90 % fall event exists
              and the old code saw no bound at all)
  a1_mirror   same deck with both polarities mirrored (en -> 1.8-en, out -> 3.3-out)
  a2          input 50 % at 1.5 ns, next input 50 % at 5.5 ns, output 50 % at 8.125 ns: the response
              STARTS inside the window but its 50 % measurement point is outside
  a2_mirror   same with polarities mirrored
  a1_perturb  a1 with the low plateau at 1.2 V: the dip never crosses the input's 50 % level, so it
              is not a logic change and the first event must still be measurable
  inside      a complete response whose 50 % point is strictly before the next input 50 % crossing
  boundary    the output 50 % point lands EXACTLY on the next input 50 % crossing
"""
from __future__ import print_function
import io, os, sys


try:
    _text = unicode
except NameError:
    _text = str


def u(s):
    # python 2.6 (the guest) refuses byte strings on an encoding-aware text stream
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def psf(pairs, axis='time'):
    n = len(pairs[0][1])
    out = ['"PSFversion" "1.00"', 'SWEEP', '"%s" "sweep" PROP(' % axis, '  "units" "s"', ')',
           'TRACE', 'VALUE']
    for i in range(n):
        for name, vals in pairs:
            out.append('"%s" %.17e' % (name, vals[i]))
    out.append('END')
    return '\n'.join(out) + '\n'


def mirror(en, out):
    return [1.8 - v for v in en], [3.3 - v for v in out]


NS18 = [i * 1e-9 for i in range(18)]
A1_EN = [0, 0, 0, 1.8, 1.8, 1.8, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 1.8, 1.8, 1.8, 1.8, 1.8]
A1_OUT = [3.3] * 15 + [0, 0, 0]
A1_EN_PERTURB = [0, 0, 0, 1.8, 1.8, 1.8, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2, 1.8, 1.8, 1.8, 1.8, 1.8]
# the R2B reviewer deck: identical except the low plateau sits at 0 V, BELOW the 10 % threshold, so a
# complete fall event does exist there. Both decks must refuse event 1, by different routes.
R2B_EN = [0, 0, 0, 1.8, 1.8, 1.8, 0, 0, 0, 0, 0, 0, 0, 1.8, 1.8, 1.8, 1.8, 1.8]
NS12 = [i * 1e-9 for i in range(12)]
A2_EN = [0, 0, 1.8, 1.8, 1.8, 1.8, 0, 0, 0, 0, 0, 0]
A2_OUT = [3.3, 3.3, 3.3, 3.3, 3.3, 2.9, 2.5, 2.1, 1.7, 1.3, 0.9, 0]
NS14 = [i * 1e-9 for i in range(14)]
NS18B = [i * 1e-9 for i in range(18)]
# input holds high until 12, falls through 50 % at 12.5 ns; the output's own fall is a COMPLETE
# 10-90 % event (it reaches 0 V) and its 50 % point is 10.125 ns, strictly inside the window.
INSIDE_EN = [0, 0] + [1.8] * 11 + [0] * 5
INSIDE_OUT = [3.3] * 7 + [2.9, 2.5, 2.1, 1.7, 1.3, 0.9, 0.5, 0.1, 0, 0, 0]
BOUND_EN = [0, 0, 1.8, 1.8, 1.8, 1.8, 0, 0, 0, 0, 0, 0]
BOUND_OUT = [3.3, 3.3, 3.3, 3.3, 3.3, 3.3, 0, 0, 0, 0, 0, 0]

CASES = {
    'a1': (NS18, A1_EN, A1_OUT, 'rise', 'fall'),
    'a1_mirror': (NS18,) + tuple(mirror(A1_EN, A1_OUT)) + ('fall', 'rise'),
    'a2': (NS12, A2_EN, A2_OUT, 'rise', 'fall'),
    'a2_mirror': (NS12,) + tuple(mirror(A2_EN, A2_OUT)) + ('fall', 'rise'),
    'a1_perturb': (NS18, A1_EN_PERTURB, A1_OUT, 'rise', 'fall'),
    'r2b_two': (NS18, R2B_EN, A1_OUT, 'rise', 'fall'),
    'inside': (NS18B, INSIDE_EN, INSIDE_OUT, 'rise', 'fall'),
    'boundary': (NS12, BOUND_EN, BOUND_OUT, 'rise', 'fall'),
}


def main():
    argv = sys.argv[1:]
    if '--outdir' not in argv:
        print('USAGE: sc1_r2c_casegen.py --outdir DIR [--only case]')
        return 2
    outdir = argv[argv.index('--outdir') + 1]
    only = argv[argv.index('--only') + 1] if '--only' in argv else None
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    names = sorted(CASES)
    wrote = []
    for name in names:
        if only and name != only:
            continue
        t, en, out, ein, eout = CASES[name]
        path = os.path.join(outdir, name + '.psf')
        with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u(psf([('time', t), ('en', en), ('out', out)])))
        meta = os.path.join(outdir, name + '.args')
        with io.open(meta, 'w', encoding='utf-8', newline='\n') as f:
            f.write(u('--edge-in %s\n--edge-out %s\n' % (ein, eout)))
        wrote.append(name)
    print('CASEGEN wrote %d decks into %s: %s' % (len(wrote), outdir, ','.join(wrote)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
