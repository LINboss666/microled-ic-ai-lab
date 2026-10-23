#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""dd1_d7c_a_r2_sign_check.py -- the probe sign rule, tested on hand-written synthetic samples.

DATA-7C-A-R2 F4. The review found that the draft deck wired the ammeter one way and described the
positive direction the other, so a native run would have returned a negative sink current and the
first person to see it would have been tempted to take abs(). The rule this script tests is the one
written into spectre/dd1_d7c_a_tb_draft.scs and into every row of the plan table before any run:

    Ip_branch (clamp_node data_out) iprobe   and   I_sink = Ip_branch

with no negation and no absolute value anywhere. Nothing here is measured: there is no simulator, no
waveform and no PSF file, and every number below is written out by hand. The amplitudes are integers
in femtoamperes and the times are integers in nanoseconds, so a charge is an exact integer in units of
1e-24 C and no floating-point tolerance is hiding an error. SYNTHETIC_NOT_MEASURED is carried on every
case so this file can never be read as evidence about the silicon.

Offline only: standard library, integers, the delivered plan table and the delivered deck text.
"""

from __future__ import absolute_import, division, print_function

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import dd1_d7c_a_offline_check as CHECK        # noqa: E402
import dd1_d7c_a_r2_plan as SCHEDULE           # noqa: E402

EVIDENCE_CLASS = 'SYNTHETIC_NOT_MEASURED'
CHARGE_UNIT = '1e-24 C (fA x ns, exact integer arithmetic)'
UNIT_CURRENT_FA = 1875          # 15 uA reference x (2.5/2)/(20/2): ESTIMATED_MIRROR_RATIO_ONLY
BRANCHES = 8


def sink_current(orientation, samples):
    """the deck's sign rule as one function, so the rule can be tested instead of asserted

    Positive terminal first is the node the current arrives from, so with the delivered order the
    reading already IS the branch current leaving data_out and nothing is applied to it. The reversed
    order is the same physics with the opposite sign, which is the mistake the review caught.
    """
    terminals = tuple(orientation)
    if terminals == SCHEDULE.PROBE_TERMINALS:
        return list(samples)
    if terminals == tuple(reversed(SCHEDULE.PROBE_TERMINALS)):
        return [-value for value in samples]
    raise ValueError('orientation %s is neither probe form, so the sign is undefined'
                     % (terminals,))


def areas(samples, dt_ns):
    """signed charge, and the positive and negative parts kept apart rather than folded together"""
    positive = sum(value * dt_ns for value in samples if value > 0)
    negative = sum(value * dt_ns for value in samples if value < 0)
    return positive + negative, positive, negative


def branch_currents(code):
    """one branch per conducting core: the thermometer count is pam_sel + 1, so code 000 sinks one"""
    selected = int(code, 2) + 1
    return [UNIT_CURRENT_FA] * selected


def cases(root):
    """(id, meaning, callable) -- every expectation below is a literal written by hand"""
    return [
        ('S1_delivered_deck_writes_the_positive_form',
         'the rule under test has to be the rule the delivered deck actually writes',
         lambda: _case_deck_matches(root)),
        ('S2_positive_reading_is_the_sink_current',
         'with clamp_node first the reading is the sink current unchanged, no negation applied',
         lambda: _case_identity()),
        ('S3_reversed_order_negates_the_same_physics',
         'turning the ammeter around flips every sample, which is why the order is fixed pre-run',
         lambda: _case_reversed()),
        ('S4_negative_tail_keeps_its_sign',
         'a negative area stays negative and is reported separately from the positive area',
         lambda: _case_areas()),
        ('S5_kcl_over_the_series_path',
         'the probe carries exactly the sum of the conducting branch currents, by code',
         lambda: _case_kcl()),
        ('S6_zero_window_is_not_a_measurement',
         'an all-zero synthetic window yields zero charge and is refused as evidence',
         lambda: _case_zero()),
        ('S7_third_orientation_is_refused',
         'a terminal pair that is neither probe form raises instead of silently picking a sign',
         lambda: _case_refuses()),
    ]


def _check(label, got, want, problems, extra=''):
    if got != want:
        problems.append('%s got %r, hand-written expectation %r%s'
                        % (label, got, want, extra))


def _case_deck_matches(root):
    problems = []
    line = CHECK.deck_probe_line(root)
    _check('the deck iprobe terminals', line,
           ('Ip_branch',) + SCHEDULE.PROBE_TERMINALS, problems)
    _spec, (plan, schema_problems) = CHECK.read_input_table(root, 'plan')
    if schema_problems:
        problems.append('the plan table is refused by its own schema: %s' % schema_problems[0])
    drift = [row.get('case_id') for row in plan
             if SCHEDULE.PROBE_ORIENTATION not in str(row.get('probe_orientation', ''))]
    _check('plan rows quoting the deck orientation', drift, [], problems)
    return problems, 'deck %s and %d plan rows quote the same terminals' % (
        ' '.join(line) if line else 'unreadable', len(plan))


def _case_identity():
    problems = []
    samples = [0, UNIT_CURRENT_FA, 2 * UNIT_CURRENT_FA, UNIT_CURRENT_FA]
    _check('I_sink', sink_current(SCHEDULE.PROBE_TERMINALS, samples), samples, problems)
    _check('charge', areas(samples, 1000)[0], 7500000, problems)
    return problems, 'SYNTHETIC fA samples %s read back unchanged, Q=7500000 in %s' % (
        samples, CHARGE_UNIT)


def _case_reversed():
    problems = []
    samples = [0, UNIT_CURRENT_FA, 2 * UNIT_CURRENT_FA, UNIT_CURRENT_FA]
    flipped = sink_current(tuple(reversed(SCHEDULE.PROBE_TERMINALS)), samples)
    _check('I_sink with the probe turned around', flipped,
           [0, -1875, -3750, -1875], problems)
    _check('charge with the probe turned around', areas(flipped, 1000)[0], -7500000, problems)
    _check('any absolute value in the flipped samples', [v for v in flipped if v > 0], [],
           problems, ' -- abs() would have hidden the orientation error')
    return problems, ('the same physics on (data_out clamp_node) reads %s, so a negative number is a '
                      'wiring fact and not something to repair afterwards' % flipped)


def _case_areas():
    problems = []
    samples = [1000000, -250000]
    total, positive, negative = areas(samples, 2000)
    _check('total charge', total, 1500000000, problems)
    _check('positive area', positive, 2000000000, problems)
    _check('negative area', negative, -500000000, problems)
    return problems, ('SYNTHETIC %s fA over 2000 ns: positive 2000000000, negative -500000000, total '
                      '1500000000 in %s -- the negative part is kept, never folded'
                      % (samples, CHARGE_UNIT))


def _case_kcl():
    problems = []
    _check('code 000 conducting branches', branch_currents('000'), [1875], problems)
    _check('code 010 branch sum', sum(branch_currents('010')), 5625, problems)
    _check('code 111 branch sum', sum(branch_currents('111')), 15000, problems,
           ' -- eight units at the estimated 1875 fA')
    for code, want in (('000', 1875), ('001', 3750), ('010', 5625), ('011', 7500),
                       ('100', 9375), ('101', 11250), ('110', 13125), ('111', 15000)):
        probe = sink_current(SCHEDULE.PROBE_TERMINALS, branch_currents(code))
        _check('probe reading for code %s' % code, sum(probe), want, problems)
    return problems, ('SYNTHETIC eight codes: the iprobe sum equals the conducting branch count x '
                      '1875 fA, 1875..15000 fA (ESTIMATED_MIRROR_RATIO_ONLY, not measured)')


def _case_zero():
    problems = []
    total, positive, negative = areas([0, 0, 0], 1000)
    _check('zero charge', (total, positive, negative), (0, 0, 0), problems)
    return problems, ('SYNTHETIC all-zero window gives (0, 0, 0) charge; it is a shape test, not a '
                      'measurement, and no sign claim is made from it')


def _case_refuses():
    try:
        value = sink_current(('clamp_node', 'vss'), [UNIT_CURRENT_FA])
    except ValueError as error:
        return [], ('SYNTHETIC (clamp_node vss) raised %s; the sign is only defined for the two '
                    'declared probe forms' % str(error)[:70])
    return ['orientation (clamp_node vss) returned %s instead of refusing' % value], ''


def run(root=ROOT):
    out = []
    for name, meaning, body in cases(root):
        try:
            problems, detail = body()
        except Exception as error:                    # noqa: BLE001 - a crash is a named MISS
            problems, detail = ['%s: %s' % (type(error).__name__, str(error)[:120])], ''
        out.append({'probe': name, 'verdict': 'HIT' if not problems else 'MISS',
                    'detail': detail if not problems else '; '.join(problems)[:220],
                    'meaning': meaning, 'evidence_class': EVIDENCE_CLASS,
                    'digest': 'n/a'})
    return out


def main(argv):
    root = os.path.abspath(argv[argv.index('--root') + 1]) if '--root' in argv else ROOT
    rows = run(root)
    failures = [row['probe'] for row in rows if row['verdict'] != 'HIT']
    for row in rows:
        print('%-42s %-5s %s' % (row['probe'], row['verdict'], row['detail'][:120]))
    print('D7C_A_R2_SIGN: %s (%d synthetic cases, failures: %s, evidence %s, charge unit %s)'
          % ('PASS' if not failures else 'FAIL', len(rows), failures or 'none', EVIDENCE_CLASS,
             CHARGE_UNIT))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
