#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D: generate the finite S2 test matrix and its machine-readable index.

    python scripts/sc1_s2_r2d_gen.py --outdir DIR [--only DECK_ID]

This generator writes files and NOTHING else: it never calls Spectre, ngspice, preflight full or
Virtuoso, and importing it runs no suite. The decks are prepared for a future authorised session;
until then every deck's status is NOT_RUN and the only validation available is the static rail/supply
gate (tb_preflight.sh with PREFLIGHT_STATIC_PROBE=1, which exits 7 and prints CIRCUIT_VERDICT=NOT_RUN).

Each deck contains:
  * an include of spectre/sc1_level_shifter_r2d.scs by relative name, exactly as the other project
    decks do, so the same cell file is what a future run parses;
  * rail sources with an explicit dc= value -- the number the supply contract is asserted against at
    the operating point -- plus, for ramp decks, a type=pwl waveform whose TARGET is a separate field
    in the index. A contract at the operating point is not a claim about the ramp top;
  * the load capacitor on the FINAL gate33 net, never on a dangling historical `out`;
  * save statements using real hierarchical names (Xt.Xcore.x, Xt.Xnand.ns_m) so a later run measures
    the nodes this analysis is about.

Labels: POC_ASSUMPTION for voltages/sizes/loads/edges/windows, ENGINEERING_TOPOLOGY_CHOICE for the
circuit being exercised, NOT_DEFINED wherever no budget exists. Nothing here invents a limit.
"""
from __future__ import print_function
import hashlib, io, os, sys

NETLIST_RELPATH = 'sc1_level_shifter_r2d.scs'

try:
    _text = unicode
except NameError:
    _text = str


def u(s):
    if isinstance(s, _text):
        return s
    if isinstance(s, bytes):
        return s.decode('utf-8', 'replace')
    return _text(s)


def csvline(vals):
    return u(','.join([u('"') + u(v).replace(u('"'), u('""')) + u('"') for v in vals])) + u('\n')


def fmt(v):
    return '%.6g' % v


LOAD_CAP = {
    '0pF':   None,
    '0.2pF': 'Cload (gate33 0) capacitor c=0.2e-12\n',
    '1pF':   'Cload (gate33 0) capacitor c=1e-12\n',
    '5pF':   'Cload (gate33 0) capacitor c=5e-12\n',
}


def srcs(rail18, rail33, en, ok=None, ramp=None, en_pwl=None):
    out = []
    def one(name, node, value, key):
        if ramp and key in ramp:
            return '%s (%s 0) vsource dc=%s type=pwl wave=[%s]\n' % (
                name, node, fmt(value), ramp[key])
        return '%s (%s 0) vsource dc=%s\n' % (name, node, fmt(value))
    out.append(one('V18', 'vdd18', rail18, 'vdd18'))
    out.append(one('V33', 'vdd33', rail33, 'vdd33'))
    out.append('Vss (vss 0) vsource dc=0\n')
    if en_pwl:
        out.append('Ven (en 0) vsource dc=%s type=pwl wave=[%s]\n' % (fmt(en), en_pwl))
    else:
        out.append('Ven (en 0) vsource dc=%s\n' % fmt(en))
    if ok is not None:
        out.append(one('Vok', 'core_ok33', ok, 'core_ok33'))
    return ''.join(out)


def instance(variant):
    if variant == 'c0':
        return 'Xt (en gate33 vdd18 vdd33 vss) sc1_ls_c0_top_r2d\n'
    return 'Xt (en core_ok33 gate33 vdd18 vdd33 vss) sc1_ls_c1_top_r2d\n'


def saves(variant):
    txt = 'save en vdd18 vdd33 vss gate33\n'
    if variant == 'c1':
        txt += 'save core_ok33 Xt.Xnand.ns_m\n'
    return txt + 'save Xt.Xcore.x Xt.Xcore.y Xt.Xcore.enbar\n'


def build(c):
    txt = 'simulator lang=spectre insensitive=yes\ninclude "%s"\n' % NETLIST_RELPATH
    txt += srcs(c['rails'][0], c['rails'][1], c['en'], c.get('ok'), c.get('ramp'), c.get('en_pwl'))
    txt += c.get('pre', '')
    txt += instance(c['variant'])
    if LOAD_CAP[c['load']]:
        txt += LOAD_CAP[c['load']]
    txt += 'sw1 tran stop=%s maxstep=%s\n' % (c['stop'], c['maxstep'])
    txt += saves(c['variant'])
    return txt


D18, D33 = 1.8, 3.3

CASES = [
    dict(id='st_c0_en_low', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high, no select', why='C0 baseline level with en low'),
    dict(id='st_c0_en_high', variant='c0', rails=(D18, D33), en=D18, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 low, select allowed', why='C0 baseline level with en high'),
    dict(id='st_c1_enlow_okhigh', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high (shutdown)', why='polarity table row 1'),
    dict(id='st_c1_enhigh_okhigh', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 low (select allowed)', why='polarity table row 2'),
    dict(id='st_c1_enlow_oklow', variant='c1', rails=(D18, D33), en=0.0, ok=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high (shutdown)', why='polarity table row 3'),
    dict(id='st_c1_enhigh_oklow', variant='c1', rails=(D18, D33), en=D18, ok=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high even though en selects',
         why='the guard must win over en; the unguarded variant is a separate deck below'),
    dict(id='st_c1_enhigh_no_guard', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 low: this is the control that shows what core_ok33 buys',
         why='no-guard control case required by the review, kept as its own deck id so it cannot be '
             'confused with the guarded result'),
    dict(id='dyn_c0_rise', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (204n 1.8) (208n 0) (300n 0)',
         expect='one gate33 fall after en rises at 100 ns', why='selecting direction, fast edge'),
    dict(id='dyn_c0_fall', variant='c0', rails=(D18, D33), en=D18, load='1pF',
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='(0 1.8) (100n 1.8) (104n 0) (204n 0) (208n 1.8) (300n 1.8)',
         expect='one gate33 rise after en falls at 100 ns',
         why='shutdown direction starting from the selecting state'),
    dict(id='dyn_c0_repeat3', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='900n', maxstep='0.2n',
         windows=[('cycle1', 100e-9, 300e-9), ('cycle2', 400e-9, 600e-9),
                  ('cycle3', 700e-9, 900e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (250n 1.8) (254n 0) (400n 0) (404n 1.8) (550n 1.8) '
                '(554n 0) (700n 0) (704n 1.8) (850n 1.8) (854n 0) (900n 0)',
         expect='three gate33 transitions, one per input cycle',
         why='repeated cycles; the case that needs an explicit event pairing rule in the delay tool, '
             'NOT a widened window'),
    dict(id='dyn_c0_slow_edge', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='400n', maxstep='0.5n', windows=[('response', 150e-9, 400e-9)],
         en_pwl='(0 0) (100n 0) (120n 1.8) (220n 1.8) (240n 0) (400n 0)',
         expect='direction correct, slew dominated by the 20 ns input edge',
         why='slow input edge; no limit is invented, the numbers go to budget review'),
    dict(id='load_c0_0pF', variant='c0', rails=(D18, D33), en=0.0, load='0pF',
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (300n 1.8)',
         expect='transition present; 0 pF means no EXTERNAL capacitor, device parasitics remain',
         why='load sweep baseline'),
    dict(id='load_c0_0p2pF', variant='c0', rails=(D18, D33), en=0.0, load='0.2pF',
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (300n 1.8)',
         expect='delay and slew recorded', why='light load'),
    dict(id='load_c0_1pF', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (300n 1.8)',
         expect='delay and slew recorded', why='nominal POC load'),
    dict(id='load_c0_5pF', variant='c0', rails=(D18, D33), en=0.0, load='5pF',
         stop='600n', maxstep='0.2n', windows=[('response', 100e-9, 600e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (600n 1.8)',
         expect='delay and slew recorded; the window covers the heaviest prepared load and is not '
                'lengthened to make an edge appear',
         why='heavy load, also the step-size re-check case'),
    dict(id='rail_18_33', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='both rails valid: select allowed', why='reference corner of the supply matrix'),
    dict(id='rail_0_33', variant='c1', rails=(0.0, D33), en=0.0, ok=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='core dead and valid low: gate33 high',
         why='core clamped to 0 V with the high domain alive. A clamped source is a legal contract, '
             'which is different from a disconnected supply (a negative case)'),
    dict(id='rail_18_0', variant='c1', rails=(D18, 0.0), en=D18, ok=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='no 3.3 V available: no 3.3 V shutdown level may be demanded; report potential, '
                'current and stress separately',
         why='high domain clamped to 0 V, core alive'),
    dict(id='rail_0_0', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='everything down: only leakage/backfeed questions apply',
         why='both rails clamped to 0 V'),
    dict(id='seq_core_first', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load='1pF',
         stop='800n', maxstep='0.5n', windows=[('core_up', 100e-9, 300e-9),
                                               ('io_up', 400e-9, 700e-9)],
         ramp=dict(vdd18='(0 0) (100n 0) (300n 1.8) (800n 1.8)',
                   vdd33='(0 0) (400n 0) (600n 3.3) (800n 3.3)',
                   core_ok33='(0 0) (650n 0) (700n 3.3) (800n 3.3)'),
         expect='rail waveforms, gate33 and both rail currents recorded through both ramps',
         why='core ramps first'),
    dict(id='seq_io_first', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load='1pF',
         stop='800n', maxstep='0.5n', windows=[('io_up', 100e-9, 300e-9),
                                               ('core_up', 400e-9, 700e-9)],
         ramp=dict(vdd18='(0 0) (400n 0) (600n 1.8) (800n 1.8)',
                   vdd33='(0 0) (100n 0) (300n 3.3) (800n 3.3)',
                   core_ok33='(0 0) (650n 0) (700n 3.3) (800n 3.3)'),
         expect='gate33 stays high until core and valid are both established',
         why='high domain ramps first, core_ok33 asserted last'),
    dict(id='seq_core_down', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='800n', maxstep='0.5n', windows=[('select', 0.0, 300e-9),
                                               ('core_down', 300e-9, 600e-9)],
         ramp=dict(vdd18='(0 1.8) (300n 1.8) (500n 0) (800n 0)',
                   core_ok33='(0 3.3) (250n 3.3) (300n 0) (800n 0)'),
         expect='core_ok33 released at or before the core failure, gate33 returns high',
         why='core powers down with the high domain alive, guarded'),
    dict(id='seq_core_down_ok_held', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='800n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9)],
         ramp=dict(vdd18='(0 1.8) (300n 1.8) (500n 0) (800n 0)'),
         expect='counter-case: core_ok33 wrongly held high while the core dies, so gate33 can stay '
                'low; this exposure is reported, not hidden',
         why='same core ramp without releasing the valid signal'),
    dict(id='seq_io_down', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='800n', maxstep='0.5n', windows=[('io_down', 300e-9, 600e-9)],
         ramp=dict(vdd33='(0 3.3) (300n 3.3) (500n 0) (800n 0)',
                   core_ok33='(0 3.3) (300n 3.3) (350n 0) (800n 0)'),
         expect='with vdd33 down no 3.3 V shutdown level can exist; output, current and stress are '
                'reported separately', why='high domain powers down'),
    dict(id='seq_ok_early_release', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load='1pF',
         stop='900n', maxstep='0.5n', windows=[('ok_before_rails', 100e-9, 400e-9),
                                               ('rails_up', 400e-9, 800e-9)],
         ramp=dict(vdd18='(0 0) (400n 0) (600n 1.8) (900n 1.8)',
                   vdd33='(0 0) (500n 0) (700n 3.3) (900n 3.3)',
                   core_ok33='(0 0) (100n 0) (150n 3.3) (900n 3.3)'),
         expect='core_ok33 asserted while both rails are still ramping: measures what the guard does '
                'not protect against', why='early-release counter-case'),
    dict(id='seq_ok_delayed_drop', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='900n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9),
                                               ('ok_drop', 600e-9, 800e-9)],
         ramp=dict(vdd18='(0 1.8) (300n 1.8) (500n 0) (900n 0)',
                   core_ok33='(0 3.3) (600n 3.3) (650n 0) (900n 0)'),
         expect='core falls first and core_ok33 follows 300 ns later: measures the exposure window '
                'of a slow valid signal', why='delayed-release counter-case'),
]

# one inverter only: this is the old candidate-B polarity failure mode, expressed in the deck so the
# shipped cell netlist does not grow a device that no correct case uses.
SINGLE_STAGE_SUBCKT = (
    'subckt sc1_r2d_polarity_fault_buf (x gate33 vdd33 vss)\n'
    '  mp (gate33 x     vdd33 vdd33) p33 l=4e-7 w=5e-6\n'
    '  mn (gate33 x     vss   vss  ) n33 l=4e-7 w=5e-6\n'
    'ends sc1_r2d_polarity_fault_buf\n')

NEGATIVES = [
    dict(id='neg_vss_miswire', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='200n', maxstep='1n', windows=[],
         mutate=lambda t: t.replace('Xt (en gate33 vdd18 vdd33 vss)',
                                    'Xt (en gate33 vdd18 vdd33 vssx)'),
         static='refused at supply_contract: vss net vssx has no independent source to node 0',
         expect='n/a (static negative)',
         why='the historical floating-substrate accident, applied to the new netlist'),
    dict(id='neg_vdd33_source_absent', variant='c1', rails=(D18, D33), en=D18, ok=D33, load='1pF',
         stop='200n', maxstep='1n', windows=[],
         mutate=lambda t: t.replace('V33 (vdd33 0) vsource dc=3.3\n', ''),
         static='refused at supply_contract: net vdd33 has no independent source',
         expect='n/a (static negative)', why='a required rail left undriven is not a legal bench'),
    dict(id='neg_output_polarity_fault', variant='c0', rails=(D18, D33), en=0.0, load='1pF',
         stop='300n', maxstep='0.2n',
         windows=[('response', 100e-9, 300e-9)],
         en_pwl='(0 0) (100n 0) (104n 1.8) (300n 1.8)',
         pre=SINGLE_STAGE_SUBCKT,
         mutate=lambda t: t.replace(
             'Xt (en gate33 vdd18 vdd33 vss) sc1_ls_c0_top_r2d\n',
             'Xcore (en x y vdd18 vdd33 vss) sc1_ls_core_r2d\n'
             'Xbuf1 (x gate33 vdd33 vss) sc1_r2d_polarity_fault_buf\n'),
         static='ACCEPTED by the static gate on purpose: the wiring is legal, so a wrong polarity is '
                'a CIRCUIT verdict. Prepared only; this round does not claim any detector caught it.',
         expect='gate33 rises when en rises (inverted relative to C0) -- to be rejected by the '
                'future C0 polarity assertion',
         why='the old candidate-B single-stage polarity error, expressed without editing the cell'),
]

HEADERS = ['deck_id', 'file', 'deck_sha256', 'netlist_sha256', 'variant', 'analysis',
           'rail_contract_at_op_V', 'rail_waveform_target_V', 'stimulus', 'load_pF',
           'planned_windows_ns', 'expected_polarity', 'static_expectation', 'status',
           'requires_simulation', 'labels', 'why']


def contract(c):
    return 'vdd18=%s vdd33=%s vss=0' % (fmt(c['rails'][0]), fmt(c['rails'][1]))


def waveform_targets(c):
    if not c.get('ramp'):
        return 'none (dc rails only)'
    parts = []
    for k, w in sorted(c['ramp'].items()):
        nums = [t for t in w.replace('(', ' ').replace(')', ' ').split()]
        parts.append('%s->%s' % (k, nums[-1]))
    return ';'.join(parts)


def netlist_bytes(root):
    p = os.path.join(root, 'spectre', NETLIST_RELPATH)
    with open(p, 'rb') as f:
        return f.read()


def main():
    argv = sys.argv[1:]
    if '--outdir' not in argv:
        print('USAGE: sc1_s2_r2d_gen.py --outdir DIR [--only ID]')
        return 2
    outdir = argv[argv.index('--outdir') + 1]
    only = argv[argv.index('--only') + 1] if '--only' in argv else None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nlbytes = netlist_bytes(root)
    nlsha = hashlib.sha256(nlbytes).hexdigest()
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    # the decks include the cell by relative name, so the byte-identical cell file has to sit next to
    # them; the index records the hash of the file in spectre/, which is the one under review
    with open(os.path.join(outdir, NETLIST_RELPATH), 'wb') as f:
        f.write(nlbytes)
    rows, made = [], 0
    for c in CASES + NEGATIVES:
        if only and c['id'] != only:
            continue
        txt = build(c)
        if 'mutate' in c:
            txt = c['mutate'](txt)
        with io.open(os.path.join(outdir, c['id'] + '.scs'), 'w',
                     encoding='utf-8', newline='\n') as f:
            f.write(u(txt))
        stim = ['en=%s V' % fmt(c['en'])]
        if c.get('ok') is not None:
            stim.append('core_ok33=%s V' % fmt(c['ok']))
        if c.get('en_pwl'):
            stim.append('en pwl ' + c['en_pwl'])
        if c.get('ramp'):
            stim.append('pwl ' + ' ; '.join('%s: %s' % (k, v)
                                            for k, v in sorted(c['ramp'].items())))
        rows.append([c['id'], c['id'] + '.scs', hashlib.sha256(txt.encode('utf-8')).hexdigest(),
                     nlsha, c['variant'],
                     'tran stop=%s maxstep=%s' % (c['stop'], c['maxstep']),
                     contract(c), waveform_targets(c), ' ; '.join(stim),
                     c['load'].rstrip('F'),
                     ','.join(['%s:%.1f..%.1f' % (n, a * 1e9, b * 1e9)
                               for (n, a, b) in c.get('windows', [])]) or 'none',
                     c['expect'],
                     c.get('static', 'accepted at the static gate (probe exit 7, '
                                     'CIRCUIT_VERDICT: NOT_RUN)'),
                     'NOT_RUN', 'yes', 'POC_ASSUMPTION,ENGINEERING_TOPOLOGY_CHOICE', c['why']])
        made += 1
    ipath = os.path.join(outdir, 'sc1_r2d_deck_index.csv')
    with io.open(ipath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(HEADERS))
        for r in rows:
            f.write(csvline(r))
    print('R2D_GEN decks=%d index=%s netlist_sha256=%s' % (made, ipath, nlsha[:16]))
    print('R2D_GEN_STATUS: files written only; no simulator, no Virtuoso, no preflight full')
    return 0


if __name__ == '__main__':
    sys.exit(main())
