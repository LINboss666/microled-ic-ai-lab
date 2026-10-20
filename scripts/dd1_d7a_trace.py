# -*- coding: utf-8 -*-
"""DATA-7A four-state VCD reader used by the independent grey-scale timing checker.

    python scripts/dd1_d7a_trace.py            # parse a VCD given on the command line and report

Times are converted to integer picoseconds, so every width the checker compares is exact and no
floating-point tolerance ever decides a PASS/FAIL. The reader refuses a dump it cannot fully explain
(unknown symbol, missing $enddefinitions, backwards timestamp, non-integer timestamp, real-valued
change) instead of silently continuing: an unexplained trace is not evidence.
"""
from __future__ import print_function

import io
import os
import re
import sys

try:
    _text = unicode
except NameError:
    _text = str

TIME_UNIT_OK = (1e-12, 1e-9)          # 1 ps (Icarus prints the precision) or 1 ns
PS_PER_S = 10 ** 12
XZ = ('x', 'z')
MULT = {'s': 1.0, 'ms': 1e-3, 'us': 1e-6, 'ns': 1e-9, 'ps': 1e-12, 'fs': 1e-15}


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


class VcdError(Exception):
    pass


def _scale(num, unit):
    unit = (unit or 's').lower()
    if unit not in MULT:
        raise VcdError('unknown timescale unit %r' % unit)
    return num * MULT[unit]


class Trace(object):
    """logical scope path -> [(t_ps, value)] with value a bit string of 0/1/x/z"""

    def __init__(self, path):
        self.path = path
        self.changes = {}
        self.widths = {}
        self.id_names = {}
        self.order = []
        self.unit_s = None
        self.backwards = 0
        self.rezeroed = 0
        self.aliased = 0
        self.same_time_edges = 0
        self._load()

    # ------------------------------------------------------------------ parse
    def _load(self):
        txt = u(io.open(self.path, encoding='utf-8', errors='replace').read())
        if '$enddefinitions' not in txt:
            raise VcdError('no $enddefinitions in %s: nothing was dumped' % self.path)
        lines = txt.split('\n')
        stack = []
        t_ps = None
        last_ps = -1
        in_dump = False
        n = len(lines)
        i = 0
        while i < n:
            line = lines[i].strip()
            i += 1
            if not line:
                continue
            head_kw = line.split()[0] if line.startswith('$') else ''
            if head_kw in ('$dumpall', '$dumpvar', '$dumpports', '$dumpvalues'):
                continue                      # a section marker; the values below it belong to t=0
            if head_kw in ('$date', '$version', '$timescale', '$comment', '$scope', '$var',
                           '$enddefinitions') and '$end' not in line:
                # Icarus writes $date, $version and $timescale as multi-line keyword blocks
                while '$end' not in line and i < n:
                    line = line + ' ' + lines[i].strip()
                    i += 1
                if '$end' not in line:
                    raise VcdError('unterminated %s block in %s' % (head_kw, self.path))
            if line.startswith('$timescale'):
                m = re.match(r'^\$timescale\s+(\d+)\s*([a-zA-Zµ]*)', line)
                if not m:
                    raise VcdError('unreadable $timescale in %s' % self.path)
                self.unit_s = _scale(float(m.group(1)), m.group(2))
                continue
            if line.startswith('$scope'):
                parts = line.split()
                if len(parts) < 4:
                    raise VcdError('malformed $scope in %s' % self.path)
                stack.append(parts[2])
                continue
            if line.startswith('$upscope'):
                if not stack:
                    raise VcdError('$upscope without $scope in %s' % self.path)
                stack.pop()
                continue
            if line.startswith('$var'):
                parts = line.split()
                if len(parts) < 5:
                    raise VcdError('malformed $var in %s' % self.path)
                if not parts[2].isdigit():
                    raise VcdError('$var without a numeric width: %r' % line)
                full = '/'.join(stack + [parts[4]])
                if full in self.widths:
                    raise VcdError('duplicate variable name %s' % full)
                width = int(parts[2])
                sid = parts[3]
                # Icarus gives a module port and the net that drives it the same dump id: they are
                # one signal, so every name sharing that id has to receive the same value history
                if sid in self.id_names:
                    if self.widths[self.id_names[sid][0]] != width:
                        raise VcdError('dump id %r is shared by signals of different width' % sid)
                    self.id_names[sid].append(full)
                    self.aliased += 1
                else:
                    self.id_names[sid] = [full]
                self.widths[full] = width
                self.changes[full] = []
                continue
            if line.startswith('$enddefinitions'):
                in_dump = True
                t_ps = 0                      # values written before the first # belong to time 0
                continue
            if not in_dump:
                continue
            if line.startswith('#'):
                body = line[1:].strip()
                if not re.match(r'^\d+$', body):
                    raise VcdError('non-integer timestamp %r in %s' % (line, self.path))
                if self.unit_s is None:
                    raise VcdError('a timestamp appeared before any $timescale in %s' % self.path)
                if abs(self.unit_s * PS_PER_S - round(self.unit_s * PS_PER_S)) > 1e-9:
                    raise VcdError('timescale %r does not land on an integer picosecond' % self.unit_s)
                t_ps = int(body) * int(round(self.unit_s * PS_PER_S))
                if t_ps < last_ps:
                    self.backwards += 1
                    raise VcdError('timestamp %d goes backwards' % t_ps)
                if t_ps == last_ps:
                    self.rezeroed += 1
                    raise VcdError('duplicate timestamp %d: the dump states the same time twice, and the '
                                   'contract requires such a trace to be refused rather than guessed at '
                                   '(many signal changes inside ONE time block are normal, two blocks '
                                   'with the same value are not)' % t_ps)
                last_ps = t_ps
                continue
            if line.startswith('$'):
                continue                      # $comment / section markers inside the dump
            self._record(line, t_ps)
        if self.unit_s is None:
            raise VcdError('no $timescale in %s: widths would be unitless' % self.path)
        if self.unit_s not in TIME_UNIT_OK:
            raise VcdError('time base %g s is not one of the accepted 1 ps / 1 ns dump units; the '
                           'checker refuses to guess a scale' % self.unit_s)

    def _record(self, line, t_ps):
        head = line[0]
        if head in 'rR':
            raise VcdError('real-valued traces are not accepted as four-state evidence: %r' % line)
        elif head in '01':
            value, ref = head, line[1:].strip()
        elif head in 'xXzZ':
            value, ref = head.lower(), line[1:].strip()
        elif head in 'bB':
            parts = line.split()
            if len(parts) != 2:
                raise VcdError('malformed vector change %r' % line)
            value, ref = parts[0][1:].lower(), parts[1]
        else:
            raise VcdError('unparsable change line %r' % line)
        if not re.match(r'^[01xz]+$', value):
            raise VcdError('change value %r is not four-state' % value)
        if ref not in self.id_names:
            raise VcdError('dump for a symbol that $var never declared: %r' % ref)
        for full in self.id_names[ref]:
            width = self.widths[full]
            v = value
            if width == 1:
                if len(v) != 1:
                    raise VcdError('%s is one bit wide but changed to %r' % (full, v))
            else:
                if len(v) > width:
                    raise VcdError('%s is %d bits wide but changed to %r' % (full, width, v))
                # Icarus writes the minimal binary form, so a short vector carries implied leading
                # zeros; an over-long value is refused above and never silently truncated
                v = '0' * (width - len(v)) + v
            hist = self.changes[full]
            if hist and hist[-1][0] == t_ps:
                self.same_time_edges += 1
            hist.append((t_ps, v))

    # ----------------------------------------------------------------- access
    def resolve(self, name):
        if name in self.changes:
            return name
        hits = [k for k in self.changes if k == name or k.endswith('/' + name)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise VcdError('signal %s is not in the trace: refusing to assume a value' % name)
        raise VcdError('signal name %s is ambiguous between %s' % (name, ', '.join(sorted(hits))))

    def has(self, name):
        try:
            self.resolve(name)
        except VcdError:
            return False
        return True

    def edges(self, name):
        return list(self.changes[self.resolve(name)])

    def value_at(self, name, t_ps):
        hist = self.changes[self.resolve(name)]
        v = 'x'                                # no history means unset: unknown, never 0
        for tt, vv in hist:
            if tt <= t_ps:
                v = vv
            else:
                break
        return v

    def rises(self, name, t_from, t_to):
        n = self.resolve(name)
        hist = self.changes[n]
        out = []
        prev = 'x'
        for tt, vv in hist:
            if tt < t_from:
                prev = vv
                continue
            if tt > t_to:
                break
            if vv == '1' and prev != '1':
                out.append(tt)
            prev = vv
        return out

    def falls(self, name, t_from, t_to):
        n = self.resolve(name)
        hist = self.changes[n]
        out = []
        prev = 'x'
        for tt, vv in hist:
            if tt < t_from:
                prev = vv
                continue
            if tt > t_to:
                break
            if vv == '0' and prev == '1':
                out.append(tt)
            prev = vv
        return out

    def segments(self, name, t_from, t_to, level='1'):
        """maximal runs where the scalar holds `level`, clipped to [t_from, t_to]"""
        n = self.resolve(name)
        hist = self.changes[n]
        out = []
        cur = self.value_at(n, t_from)
        start = t_from if cur == level else None
        for tt, vv in hist:
            if tt <= t_from:
                continue
            if tt > t_to:
                break
            if cur == level and vv != level:
                out.append((start, tt))
                start = None
            if vv == level and cur != level:
                start = tt
            cur = vv
        if start is not None:
            out.append((start, min(t_to, hist[-1][0] if hist else t_to)))
        return out

    def unknown_spans(self, name, t_from, t_to):
        n = self.resolve(name)
        out = []
        seed = self.value_at(n, t_from)
        opened = t_from if any(c in XZ for c in seed) else None
        for tt, vv in self.changes[n]:
            if tt > t_to:
                break
            if tt < t_from:
                continue
            bad = any(c in XZ for c in vv)
            if bad and opened is None:
                opened = tt
            elif not bad and opened is not None:
                out.append((opened, tt))
                opened = None
        if opened is not None:
            out.append((opened, t_to))
        return out

    def values_in(self, name, t_from, t_to):
        """every value the signal holds inside the range, including the value carried in at t_from"""
        n = self.resolve(name)
        vals = set([self.value_at(n, t_from)])
        vals.update(vv for tt, vv in self.changes[n] if t_from < tt <= t_to)
        return vals

    @property
    def end_time(self):
        return max([v[-1][0] for v in self.changes.values() if v] or [0])


def bits(value):
    """four-state bit string -> (defined, int) ; x/z makes it undefined and the caller must refuse"""
    if any(c in XZ for c in value):
        return (False, None)
    return (True, int(value, 2))


def main(argv):
    if len(argv) < 2:
        print('usage: dd1_d7a_trace.py <file.vcd>')
        return 2
    tr = Trace(argv[1])
    print('signals=%d end_ps=%d backwards=%d rezeroed=%d'
          % (len(tr.changes), tr.end_time, tr.backwards, tr.rezeroed))
    for k in sorted(tr.changes):
        print('  %-40s w=%-3d changes=%d' % (k, tr.widths[k], len(tr.changes[k])))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
