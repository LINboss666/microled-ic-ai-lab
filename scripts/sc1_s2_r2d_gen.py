#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2D/R2D1: generate the finite S2 test matrix and its machine-readable index.

    python scripts/sc1_s2_r2d_gen.py --outdir DIR [--only DECK_ID] [--section tt]

This generator writes files and NOTHING else: it never calls Spectre, ngspice, preflight full or
Virtuoso, and importing it runs no suite. The decks are prepared for a future authorised session;
until then every deck's status is NOT_RUN, and the only validation available here is the static rail
and supply gate (tb_preflight.sh with PREFLIGHT_STATIC_PROBE=1, which exits 7 and prints
CIRCUIT_VERDICT=NOT_RUN). A static acceptance does not certify a dynamic rail range.

R2D1 changes, item by item against the review:
  B1  no deck may drive the high-domain valid into a rail that is not there. The old
      seq_ok_early_release ramped core_ok33 to 3.3 V at 100..150 ns while vdd33 only rose at
      500..700 ns, which is exactly the 3.3-into-0 V case it claimed to exclude. It now holds
      vdd33 at 3.3 V from t=0 and ramps only the CORE late, so "valid asserted before the core is
      alive" is still tested and the waveform stays inside the rail that exists.
  B2  three decks kept en at an ideal 1.8 V after vdd18 fell to 0. That is an external continued
      drive, not a driver that died with its supply, so those decks are labelled
      EXTERNAL_DRIVE_FAULT and each now has a twin whose en falls with the low rail
      (en_follows). Both situations are in the index; the over-drive is not hidden.
  B3  the model library is bound the way the 139 decks that have actually run bind it,
      `include "${QODER_PDK_LIB}" section=tt` -- the value is never committed; it comes from the
      git-ignored spectre/pdk_local.env, and run_spectre.sh refuses an unresolved variable with
      exit 9. Until that binding exists every deck carries DECK_BINDING_PENDING and no template is
      claimed to be directly runnable. Temperature: this project has never run a deck with a
      `temp=`/`temperature=` line (all 167 generated decks use the plain header), so 27 C is a
      POC_ASSUMPTION recorded in the index and the deck line itself is marked PENDING instead of
      being invented into 36 decks. Supply-branch current: a series `iprobe` in a rail WAS tried
      with the static gate and is refused (SUPPLY_FAIL: net vdd18 has no independent source from
      reference node 0, stage=supply_contract, rc=1 -- see
      results/evidence/sc1_r2d1_iprobe_static_probe.csv). The gate is not relaxed, so the decks use
      the two current forms this project measured to work: `save <node>` and
      `save <inst>:1` (MOS terminal 1 = drain in the D G S B order).
  B4  C1 now has both dynamic directions, repeated cycles and the 0/0.2/1/5 pF load sweep on the
      FINAL gate33 net, the same finite matrix that existed for C0.
  B5  load_pF is a number, not '1p'. The operating-point rail contract, the ramp TARGET and the
      stimulus stay three different columns, and every row carries future_verdict=NOT_RUN plus
      static_certifies_dynamic_rail_range=no.
  also fixed: the committed matrix carried st_c1_enhigh_no_guard as the "unguarded control", but its
      deck_sha256 was byte-identical to st_c1_enhigh_okhigh (5da1fac7a6fd2732), so it proved nothing.
      C0 with en high -- same rails, load and window, and a master with no core_ok33 port at all --
      is the real unguarded control, and it is recorded in st_c0_en_high's own row. The generator now
      refuses to emit two byte-identical decks at all (DUPLICATE_DECK, exit 3).
  PWL syntax: every waveform is the flat `wave=[t v t v ...]` form that passed on this build; the
      parenthesised pair form is not used anywhere in this generator.

Labels: POC_ASSUMPTION for voltages/sizes/loads/edges/windows, ENGINEERING_TOPOLOGY_CHOICE for the
circuit being exercised, EXTERNAL_DRIVE_FAULT for a stimulus an internal driver could not produce,
NOT_DEFINED wherever no budget exists. Nothing here invents a limit.
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


def load_cap(pf):
    if not pf:
        return None
    return 'Cload (gate33 0) capacitor c=%se-12\n' % fmt(pf)


# ---------------------------------------------------------------- per-variant wiring and saves
DEVICES = {
    'c0': ['Xt.Xcore.mp_drv', 'Xt.Xcore.mn_drv', 'Xt.Xcore.mp_left', 'Xt.Xcore.mp_right',
           'Xt.Xcore.mn_left', 'Xt.Xcore.mn_right', 'Xt.Xbuf.mp_i1', 'Xt.Xbuf.mn_i1',
           'Xt.Xbuf.mp_i2', 'Xt.Xbuf.mn_i2'],
    'c1': ['Xt.Xcore.mp_drv', 'Xt.Xcore.mn_drv', 'Xt.Xcore.mp_left', 'Xt.Xcore.mp_right',
           'Xt.Xcore.mn_left', 'Xt.Xcore.mn_right', 'Xt.Xnand.mp_na', 'Xt.Xnand.mp_nb',
           'Xt.Xnand.mn_nt', 'Xt.Xnand.mn_nb'],
}
NODES = {
    'c0': ['en', 'Xt.Xcore.enbar', 'Xt.Xcore.x', 'Xt.Xcore.y', 'Xt.Xbuf.n1', 'gate33'],
    'c1': ['en', 'Xt.Xcore.enbar', 'Xt.Xcore.x', 'Xt.Xcore.y', 'Xt.Xnand.ns_m', 'core_ok33',
           'gate33'],
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
    """Voltage and terminal-current saves in the two forms this project measured to work.

    The supply branch is NOT broken by an iprobe: the audited supply gate refuses a rail reached
    through a series element (measured with PREFLIGHT_STATIC_PROBE=1: rc=1, stage=supply_contract,
    5 SUPPLY_FAIL lines -- results/evidence/sc1_r2d1_iprobe_static_probe.csv), and the gate is not
    relaxed. So the decks save each device's terminal-1 current (terminal 1 is the drain in the
    vendor's D G S B order) together with every terminal node, and the rail current has to be
    assembled from those per-device currents; the sign convention of that sum is NOT confirmed by
    any run on this build and stays PENDING for the authorised session.
    """
    txt = 'save vdd18 vdd33 vss\n'
    txt += 'save %s\n' % ' '.join(NODES[variant])
    txt += '// per-terminal currents: the verified save forms on this build are save <node> and\n'
    txt += '// save <inst>:1 (spectre/current_probe_syntax.scs, reports/data_driver_candidate_E.md).\n'
    txt += '// No series iprobe on a rail: the static supply gate refuses a rail fed through one\n'
    txt += '// (measured rc=1 stage=supply_contract), so rail current = sum of the device currents on\n'
    txt += '// that rail; that sum is PENDING until a run confirms its sign convention.\n'
    txt += 'save %s\n' % ' '.join('%s:1' % d for d in DEVICES[variant])
    return txt


def header(section):
    return ('simulator lang=spectre insensitive=yes\n'
            '// model binding: run_spectre.sh expands ${QODER_PDK_LIB} from the git-ignored\n'
            '// spectre/pdk_local.env; with no binding it refuses the deck (exit 9), so every deck\n'
            '// here is DECK_BINDING_PENDING until then. section=%s is a measured master-section name;\n'
            '// temperature is a POC_ASSUMPTION (27 C) and NO temp= line is emitted, because no deck\n'
            '// in this project has ever run with one -- that syntax stays PENDING.\n'
            'include "${QODER_PDK_LIB}" section=%s\n'
            'include "%s"\n' % (section, section, NETLIST_RELPATH))


def build(c, section='tt'):
    txt = header(section)
    txt += srcs(c['rails'][0], c['rails'][1], c['en'], c.get('ok'), c.get('ramp'), c.get('en_pwl'))
    txt += c.get('pre', '')
    txt += instance(c['variant'])
    cap = load_cap(c['load'])
    if cap:
        txt += cap
    txt += 'sw1 tran stop=%s maxstep=%s\n' % (c['stop'], c['maxstep'])
    txt += saves(c['variant'])
    return txt


D18, D33 = 1.8, 3.3
NORMAL = 'normal: en never exceeds the vdd18 waveform'
OVERDRIVE = 'EXTERNAL_DRIVE_FAULT: an ideal source holds en above the present vdd18'

CASES = [
    dict(id='st_c0_en_low', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high, no select', why='C0 baseline level with en low'),
    dict(id='st_c0_en_high', variant='c0', rails=(D18, D33), en=D18, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 low, select allowed',
         why='C0 baseline level with en high. C0 has no core_ok33 port at all, so this row IS the '
             'unguarded control for the guarded pair below -- the R2D matrix carried a separate '
             'st_c1_enhigh_no_guard deck for that purpose, and the new duplicate detector shows it '
             'was byte-identical to st_c1_enhigh_okhigh, i.e. not a control at all'),
    dict(id='st_c1_enlow_okhigh', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high (shutdown)', why='polarity table row 1'),
    dict(id='st_c1_enhigh_okhigh', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 low (select allowed)',
         why='polarity table row 2, and at the same time the reference corner of the dual-rail '
             'matrix (1.8/3.3): the R2D matrix also carried a separate rail_18_33 deck, which the '
             'duplicate detector shows to have been byte-identical to this one -- one deck, two '
             'declared roles, instead of two decks with one name each'),
    dict(id='st_c1_enlow_oklow', variant='c1', rails=(D18, D33), en=0.0, ok=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high (shutdown)', why='polarity table row 3'),
    dict(id='st_c1_enhigh_oklow', variant='c1', rails=(D18, D33), en=D18, ok=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='gate33 high even though en selects',
         why='the guard must win over en; the unguarded control is st_c0_en_high, which has no '
             'core_ok33 port at all'),
    dict(id='dyn_c0_rise', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 204n 1.8 208n 0 300n 0',
         expect='one gate33 fall after en rises at 100 ns', why='selecting direction, fast edge'),
    dict(id='dyn_c0_fall', variant='c0', rails=(D18, D33), en=D18, load=1.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 1.8 100n 1.8 104n 0 204n 0 208n 1.8 300n 1.8',
         expect='one gate33 rise after en falls at 100 ns',
         why='shutdown direction starting from the selecting state'),
    dict(id='dyn_c0_repeat3', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='900n', maxstep='0.2n',
         windows=[('cycle1', 100e-9, 300e-9), ('cycle2', 400e-9, 600e-9),
                  ('cycle3', 700e-9, 900e-9)],
         en_pwl='0 0 100n 0 104n 1.8 250n 1.8 254n 0 400n 0 404n 1.8 550n 1.8 554n 0 700n 0 '
                '704n 1.8 850n 1.8 854n 0 900n 0',
         expect='three gate33 transitions, one per input cycle',
         why='repeated cycles; the case that needs an explicit event pairing rule in the delay tool, '
             'NOT a widened window'),
    dict(id='dyn_c0_slow_edge', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='400n', maxstep='0.5n', windows=[('response', 150e-9, 400e-9)],
         en_pwl='0 0 100n 0 120n 1.8 220n 1.8 240n 0 400n 0',
         expect='direction correct, slew dominated by the 20 ns input edge',
         why='slow input edge; no limit is invented, the numbers go to budget review'),
    # ---- C1 dynamic and load matrix (B4): the same finite shape C0 already had
    dict(id='dyn_c1_rise', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=1.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 204n 1.8 208n 0 300n 0',
         expect='one gate33 fall after en rises at 100 ns, with the guard open',
         why='C1 selecting direction: the guarded path has never had a dynamic case at all'),
    dict(id='dyn_c1_fall', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 1.8 100n 1.8 104n 0 204n 0 208n 1.8 300n 1.8',
         expect='one gate33 rise after en falls at 100 ns',
         why='C1 shutdown direction from the selecting state'),
    dict(id='dyn_c1_repeat3', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=1.0,
         stop='900n', maxstep='0.2n',
         windows=[('cycle1', 100e-9, 300e-9), ('cycle2', 400e-9, 600e-9),
                  ('cycle3', 700e-9, 900e-9)],
         en_pwl='0 0 100n 0 104n 1.8 250n 1.8 254n 0 400n 0 404n 1.8 550n 1.8 554n 0 700n 0 '
                '704n 1.8 850n 1.8 854n 0 900n 0',
         expect='three gate33 transitions with core_ok33 held high the whole time',
         why='repeated cycles through the NAND; the same pairing rule applies as for C0'),
    dict(id='load_c1_0pF', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=0.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
         expect='transition present; 0 pF means no EXTERNAL capacitor, device parasitics remain',
         why='load sweep baseline on the final gate33 net'),
    dict(id='load_c1_0p2pF', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=0.2,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
         expect='delay and slew recorded', why='light load on the final gate33 net'),
    dict(id='load_c1_1pF', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=1.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
         expect='delay and slew recorded', why='nominal POC load on the final gate33 net'),
    dict(id='load_c1_5pF', variant='c1', rails=(D18, D33), en=0.0, ok=D33, load=5.0,
         stop='600n', maxstep='0.2n', windows=[('response', 100e-9, 600e-9)],
         en_pwl='0 0 100n 0 104n 1.8 600n 1.8',
         expect='delay and slew recorded; the window covers the heaviest prepared load and is not '
                'lengthened to make an edge appear',
         why='heavy load, also the step-size re-check case'),
    dict(id='load_c0_0pF', variant='c0', rails=(D18, D33), en=0.0, load=0.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
         expect='transition present; 0 pF means no EXTERNAL capacitor, device parasitics remain',
         why='load sweep baseline'),
    dict(id='load_c0_0p2pF', variant='c0', rails=(D18, D33), en=0.0, load=0.2,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
         expect='delay and slew recorded', why='light load'),
    dict(id='load_c0_1pF', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='300n', maxstep='0.2n', windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
         expect='delay and slew recorded', why='nominal POC load'),
    dict(id='load_c0_5pF', variant='c0', rails=(D18, D33), en=0.0, load=5.0,
         stop='600n', maxstep='0.2n', windows=[('response', 100e-9, 600e-9)],
         en_pwl='0 0 100n 0 104n 1.8 600n 1.8',
         expect='delay and slew recorded; the window covers the heaviest prepared load and is not '
                'lengthened to make an edge appear',
         why='heavy load, also the step-size re-check case'),
    dict(id='rail_0_33', variant='c1', rails=(0.0, D33), en=0.0, ok=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='core dead and valid low: gate33 high',
         why='core clamped to 0 V with the high domain alive (the 1.8/3.3 reference corner of this '
             'supply matrix is the deck st_c1_enhigh_okhigh). A clamped source is a legal contract, '
             'which is different from a disconnected supply (a negative case)'),
    dict(id='rail_18_0', variant='c1', rails=(D18, 0.0), en=D18, ok=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='no 3.3 V available: no 3.3 V shutdown level may be demanded; report potential, '
                'current and stress separately',
         why='high domain clamped to 0 V, core alive'),
    dict(id='rail_0_0', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[('settled', 150e-9, 200e-9)],
         expect='everything down: only leakage/backfeed questions apply',
         why='both rails clamped to 0 V'),
    dict(id='seq_core_first', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load=1.0,
         stop='800n', maxstep='0.5n', windows=[('core_up', 100e-9, 300e-9),
                                               ('io_up', 400e-9, 700e-9)],
         ramp=dict(vdd18='0 0 100n 0 300n 1.8 800n 1.8',
                   vdd33='0 0 400n 0 600n 3.3 800n 3.3',
                   core_ok33='0 0 650n 0 700n 3.3 800n 3.3'),
         expect='rail waveforms, gate33 and both rail currents recorded through both ramps',
         why='core ramps first'),
    dict(id='seq_io_first', variant='c1', rails=(0.0, 0.0), en=0.0, ok=0.0, load=1.0,
         stop='800n', maxstep='0.5n', windows=[('io_up', 100e-9, 300e-9),
                                               ('core_up', 400e-9, 700e-9)],
         ramp=dict(vdd18='0 0 400n 0 600n 1.8 800n 1.8',
                   vdd33='0 0 100n 0 300n 3.3 800n 3.3',
                   core_ok33='0 0 650n 0 700n 3.3 800n 3.3'),
         expect='gate33 stays high until core and valid are both established',
         why='high domain ramps first, core_ok33 asserted last'),
    dict(id='seq_core_down', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='800n', maxstep='0.5n', windows=[('select', 0.0, 300e-9),
                                               ('core_down', 300e-9, 600e-9)],
         ramp=dict(vdd18='0 1.8 300n 1.8 500n 0 800n 0',
                   core_ok33='0 3.3 250n 3.3 300n 0 800n 0'),
         en_drive=OVERDRIVE,
         expect='core_ok33 released at or before the core failure, gate33 returns high',
         why='core powers down with the high domain alive, guarded. en stays at an ideal 1.8 V after '
             'vdd18 has fallen: that is a source continuing to drive, NOT a core driver losing its '
             'supply, so the row is labelled EXTERNAL_DRIVE_FAULT and the en_follows twin below is '
             'the case a dead core actually produces'),
    dict(id='seq_core_down_en_follows', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='800n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9)],
         ramp=dict(vdd18='0 1.8 300n 1.8 500n 0 800n 0',
                   core_ok33='0 3.3 250n 3.3 300n 0 800n 0'),
         en_pwl='0 1.8 300n 1.8 400n 0 800n 0', en_drive=NORMAL,
         expect='en falls with the low rail (never above vdd18 at any breakpoint) and the guard '
                'returns gate33 high',
         why='the twin of seq_core_down without the external over-drive: what a core driver whose '
             'supply collapses actually does'),
    dict(id='seq_core_down_ok_held', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='800n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9)],
         ramp=dict(vdd18='0 1.8 300n 1.8 500n 0 800n 0'),
         en_drive=OVERDRIVE,
         expect='counter-case: core_ok33 wrongly held high while the core dies, so gate33 can stay '
                'low; this exposure is reported, not hidden',
         why='same core ramp without releasing the valid signal; the held en is an external drive '
             'fault, labelled as such'),
    dict(id='seq_core_down_ok_held_en_follows', variant='c1', rails=(D18, D33), en=D18, ok=D33,
         load=1.0, stop='800n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9)],
         ramp=dict(vdd18='0 1.8 300n 1.8 500n 0 800n 0'),
         en_pwl='0 1.8 300n 1.8 400n 0 800n 0', en_drive=NORMAL,
         expect='core_ok33 held high and en falling with the rail: measures the guard exposure '
                'without an over-drive artefact',
         why='the ok_held counter-case with a legitimate low-domain stimulus'),
    dict(id='seq_io_down', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='800n', maxstep='0.5n', windows=[('io_down', 300e-9, 600e-9)],
         ramp=dict(vdd33='0 3.3 300n 3.3 500n 0 800n 0',
                   core_ok33='0 3.3 300n 3.3 350n 0 800n 0'),
         expect='with vdd33 down no 3.3 V shutdown level can exist; output, current and stress are '
                'reported separately', why='high domain powers down'),
    dict(id='seq_ok_delayed_drop', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='900n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9),
                                               ('ok_drop', 600e-9, 800e-9)],
         ramp=dict(vdd18='0 1.8 300n 1.8 500n 0 900n 0',
                   core_ok33='0 3.3 600n 3.3 650n 0 900n 0'),
         en_drive=OVERDRIVE,
         expect='core falls first and core_ok33 follows 300 ns later: measures the exposure window '
                'of a slow valid signal',
         why='delayed-release counter-case; en held at 1.8 V over a dead vdd18 is the external '
             'drive fault, so the en_follows twin below carries the same timing legitimately'),
    dict(id='seq_ok_delayed_drop_en_follows', variant='c1', rails=(D18, D33), en=D18, ok=D33,
         load=1.0, stop='900n', maxstep='0.5n', windows=[('core_down', 300e-9, 600e-9),
                                                         ('ok_drop', 600e-9, 800e-9)],
         ramp=dict(vdd18='0 1.8 300n 1.8 500n 0 900n 0',
                   core_ok33='0 3.3 600n 3.3 650n 0 900n 0'),
         en_pwl='0 1.8 300n 1.8 400n 0 900n 0', en_drive=NORMAL,
         expect='exposure window measured with en following the low rail',
         why='legitimate twin of seq_ok_delayed_drop'),
    dict(id='seq_ok_early_release', variant='c1', rails=(0.0, D33), en=0.0, ok=0.0, load=1.0,
         stop='900n', maxstep='0.5n', windows=[('ok_before_core', 100e-9, 500e-9),
                                               ('core_up', 500e-9, 900e-9)],
         ramp=dict(vdd18='0 0 500n 0 700n 1.8 900n 1.8',
                   core_ok33='0 0 100n 0 150n 3.3 900n 3.3'),
         expect='core_ok33 asserted while the CORE is still dead, inside a vdd33 that is already '
                '3.3 V: measures what the guard does not protect against',
         why='early-release counter-case, rebuilt for R2D1-B1. The old version ramped core_ok33 to '
             '3.3 V at 100..150 ns while vdd33 only rose at 500..700 ns, i.e. it drove 3.3 V into a '
             '0 V rail -- the very thing the report claimed no deck did. An external over-drive of '
             'the high domain is a different, separately named case (EXTERNAL_OVERDRIVE) and is not '
             'part of this round'),
]

# one inverter only: this is the old candidate-B polarity failure mode, expressed in the deck so the
# shipped cell netlist does not grow a device that no correct case uses.
SINGLE_STAGE_SUBCKT = (
    'subckt sc1_r2d_polarity_fault_buf (x gate33 vdd33 vss)\n'
    '  mp (gate33 x     vdd33 vdd33) p33 l=4e-7 w=5e-6\n'
    '  mn (gate33 x     vss   vss  ) n33 l=4e-7 w=5e-6\n'
    'ends sc1_r2d_polarity_fault_buf\n')

NEGATIVES = [
    dict(id='neg_vss_miswire', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='200n', maxstep='1n', windows=[],
         mutate=lambda t: t.replace('Xt (en gate33 vdd18 vdd33 vss)',
                                    'Xt (en gate33 vdd18 vdd33 vssx)'),
         static='refused at supply_contract: vss net vssx has no independent source to node 0',
         expect='n/a (static negative)',
         why='the historical floating-substrate accident, applied to the new netlist'),
    dict(id='neg_vdd33_source_absent', variant='c1', rails=(D18, D33), en=D18, ok=D33, load=1.0,
         stop='200n', maxstep='1n', windows=[],
         mutate=lambda t: t.replace('V33 (vdd33 0) vsource dc=3.3\n', ''),
         static='refused at supply_contract: net vdd33 has no independent source',
         expect='n/a (static negative)', why='a required rail left undriven is not a legal bench'),
    dict(id='neg_output_polarity_fault', variant='c0', rails=(D18, D33), en=0.0, load=1.0,
         stop='300n', maxstep='0.2n',
         windows=[('response', 100e-9, 300e-9)],
         en_pwl='0 0 100n 0 104n 1.8 300n 1.8',
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
           'en_drive_kind', 'planned_windows_ns', 'expected_polarity', 'static_expectation',
           'status', 'future_verdict', 'static_certifies_dynamic_rail_range',
           'deck_binding', 'supply_branch_current_method', 'temperature_model_line',
           'requires_simulation', 'labels', 'why']

TOL = 1e-9


def pwl_points(spec):
    """Flat 't v t v ...' (or a single dc value) -> ordered (time, value) breakpoints."""
    toks = spec.replace('(', ' ').replace(')', ' ').split()
    if len(toks) % 2:
        raise ValueError('PWL spec must be time/value pairs: %r' % spec)
    return [(toks[i], float(toks[i + 1])) for i in range(0, len(toks), 2)]


def contract(c):
    return 'vdd18=%s vdd33=%s vss=0' % (fmt(c['rails'][0]), fmt(c['rails'][1]))


def waveform_targets(c):
    if not c.get('ramp'):
        return 'none (dc rails only)'
    parts = []
    for k in sorted(c['ramp']):
        parts.append('%s->%s' % (k, pwl_points(c['ramp'][k])[-1][1]))
    return ';'.join(parts)


def envelopes(c):
    """(signal, waveform) pairs for the offline rail-envelope audit."""
    env = []
    for key, value, rampkey in (('vdd18', c['rails'][0], 'vdd18'),
                                ('vdd33', c['rails'][1], 'vdd33')):
        w = c.get('ramp', {}).get(rampkey)
        env.append((key, pwl_points(w) if w else [('0', value)]))
    w = c.get('en_pwl')
    env.append(('en', pwl_points(w) if w else [('0', c['en'])]))
    if c.get('ok') is not None:
        w = c.get('ramp', {}).get('core_ok33')
        env.append(('core_ok33', pwl_points(w) if w else [('0', c['ok'])]))
    return env


def binding_status(pdk_env):
    if os.path.exists(pdk_env):
        return ('LOCAL_ENV_PRESENT (not parsed here); DECK_BINDING_PENDING until run_spectre.sh '
                'expands ${QODER_PDK_LIB}')
    return ('BLOCKED: %s absent, run_spectre.sh refuses an unresolved ${QODER_PDK_LIB} with exit 9 '
            '(DECK_BINDING_PENDING)' % 'spectre/pdk_local.env')


def netlist_bytes(root):
    p = os.path.join(root, 'spectre', NETLIST_RELPATH)
    with open(p, 'rb') as f:
        return f.read()


def main():
    argv = sys.argv[1:]
    if '--outdir' not in argv:
        print('USAGE: sc1_s2_r2d_gen.py --outdir DIR [--only ID] [--section tt]')
        return 2
    outdir = argv[argv.index('--outdir') + 1]
    only = argv[argv.index('--only') + 1] if '--only' in argv else None
    section = argv[argv.index('--section') + 1] if '--section' in argv else 'tt'
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pdk_env = os.path.join(root, 'spectre', 'pdk_local.env')
    binding = binding_status(pdk_env)
    nlbytes = netlist_bytes(root)
    nlsha = hashlib.sha256(nlbytes).hexdigest()
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    # the decks include the cell by relative name, so the byte-identical cell file has to sit next to
    # them; the index records the hash of the file in spectre/, which is the one under review
    with open(os.path.join(outdir, NETLIST_RELPATH), 'wb') as f:
        f.write(nlbytes)
    rows, made = [], 0
    seen = {}
    for c in CASES + NEGATIVES:
        if only and c['id'] != only:
            continue
        txt = build(c, section)
        if 'mutate' in c:
            txt = c['mutate'](txt)
        sha = hashlib.sha256(txt.encode('utf-8')).hexdigest()
        if sha in seen:
            print('DUPLICATE_DECK: %s is byte-identical to %s' % (c['id'], seen[sha]))
            return 3
        seen[sha] = c['id']
        with io.open(os.path.join(outdir, c['id'] + '.scs'), 'w',
                     encoding='utf-8', newline='\n') as f:
            f.write(u(txt))
        stim = ['en=%s V' % fmt(c['en'])]
        if c.get('ok') is not None:
            stim.append('core_ok33=%s V' % fmt(c['ok']))
        if c.get('en_pwl'):
            stim.append('en pwl ' + c['en_pwl'])
        if c.get('ramp'):
            stim.append('pwl ' + ' ; '.join('%s: %s' % (k, c['ramp'][k])
                                             for k in sorted(c['ramp'])))
        rows.append([c['id'], c['id'] + '.scs', sha, nlsha, c['variant'],
                     'tran stop=%s maxstep=%s' % (c['stop'], c['maxstep']),
                     contract(c), waveform_targets(c), ' ; '.join(stim),
                     fmt(c['load']),
                     c.get('en_drive', 'steady dc, below both rails'),
                     ','.join(['%s:%.1f..%.1f' % (n, a * 1e9, b * 1e9)
                               for (n, a, b) in c.get('windows', [])]) or 'none',
                     c['expect'],
                     c.get('static', 'accepted at the static gate (probe exit 7, '
                                     'CIRCUIT_VERDICT: NOT_RUN)'),
                     'NOT_RUN', 'NOT_RUN',
                     'no (static gate checks wiring and the operating point, not a ramp)',
                     binding,
                     'sum of per-device `save <inst>:1` currents; a series rail iprobe is refused by '
                     'the static gate (measured rc=1 stage=supply_contract) and the sign convention '
                     'of the sum is PENDING',
                     'POC_ASSUMPTION 27 C; no temp= line emitted (no deck in this project has ever '
                     'run with one) -> TEMP_LINE_SYNTAX_PENDING',
                     'yes',
                     'POC_ASSUMPTION,ENGINEERING_TOPOLOGY_CHOICE', c['why']])
        made += 1
    ipath = os.path.join(outdir, 'sc1_r2d1_deck_index.csv')
    with io.open(ipath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(HEADERS))
        for r in rows:
            f.write(csvline(r))
    print('R2D1_GEN decks=%d index=%s netlist_sha256=%s' % (made, ipath, nlsha[:16]))
    print('R2D1_GEN_MODEL_BINDING: %s' % binding)
    print('R2D1_GEN_DUPLICATE_CHECK: %d distinct deck hashes over %d decks' % (len(seen), made))
    print('R2D1_GEN_STATUS: files written only; no simulator, no Virtuoso, no preflight full')
    return 0


if __name__ == '__main__':
    sys.exit(main())
