#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCAN-1 R2E: calibrate model binding, temperature and supply-source current BEFORE any DUT run.

    python scripts/sc1_r2e_calibrate.py [--scratch DIR] [--out CSV]

Authorised scope: this really runs Spectre (first run of the round) on a two-element calibration
bench, and preflight full on the same bench. Nothing about S1 or S2 is measured here.

What has to come out of it, and why each item is a separate row:

  MODEL_BINDING        -- ${QODER_PDK_LIB} resolved from the git-ignored local env, the file that the
                          deck actually includes hashed, and the section name the lib declares. A file
                          name matching the PDK is not evidence; the hash and the loaded path are.
  GEOMETRY_RANGE_READ  -- lmin/lmax/wmin read out of the model records this run includes, compared with
                          the frozen S2 sizes. Model/bin limits are NOT absolute maximum ratings and NOT
                          a characterisation range; the README's -40..125 C is the characterisation
                          range, and no absolute-rating table exists in the readable files, so
                          SOA_SIGNOFF stays NO.
  TEMP_CONFIRMATION    -- the netlist syntax comes from this build's own help (`spectre -h options`
                          lists `temp=27 C`), and the value is then read back out of the produced log,
                          not assumed from a generator comment or a default.
  SOURCE_CURRENT_*     -- the sign and name of a directly driven supply source's current. The rail is
                          NEVER broken by an iprobe (the audited supply gate refuses a rail reached
                          through a series element, measured in R2D1), so a verified iprobe sits in the
                          LOAD branch and the candidate save forms for the source itself are tried
                          beside it. Theory for the bench is exact: 1.8 V / 10 k = 180 uA and
                          3.3 V / 10 k = 330 uA, and the positive direction is stated explicitly.
                          Summing MOS drain currents is NOT used as a substitute for a supply current.

Exit code 0 only when every row is PASS. A missing licence, a fatal save form or an unreadable value
is recorded with its rc and log excerpt and the run stops there -- no zeros, no silent substitution.
"""
from __future__ import print_function

import hashlib
import io
import optparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
# R2E1: one shared call contract with the S2 entry. The R2E round decided a preflight from a pipe's
# exit status and a run from a PASS token; both are replaced by the callee's real rc plus the
# completion markers, error count and data identity the contract requires.
import sc1_r2e1_call_contract as CC

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


def sh(cmd, cwd=None):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd)
    raw = p.communicate()[0]
    txt = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    return p.returncode, txt


def scrub(text):
    """Keep the substance, drop vendor/user absolute paths from anything that goes into the repo."""
    out = []
    for line in text.split('\n'):
        if re.search(r'/root/|/opt/|/home/|/etc/', line):
            line = re.sub(r'(/root|/opt|/home|/etc)/[^\s"\']*', '<path-redacted>', line)
        out.append(line)
    return '\n'.join(out)


DECK = '''simulator lang=spectre insensitive=yes
// R2E calibration bench: an ideal rail, one 10k resistor and a verified zero-drop iprobe inside the
// LOAD subcircuit. The rail itself is never broken by a probe: the audited supply gate refuses a rail
// reached through a series element (measured in R2D1: rc=1 stage=supply_contract).
// Expected from Ohm alone: 1.8 V / 10 k = 180 uA and 3.3 V / 10 k = 330 uA, and because the iprobe is
// zero-drop the whole rail voltage falls across R1, so Xcal.node_mid must read ~0 V.
// Temperature: `spectre -h options` documents the parameter name `temp=27 C`, but in this netlist
// language `options` is a device master, not a keyword -- the vendor `section tt` itself declares
// `setoption1 options gmin=1e-14`. A bare `options temp=27` line is rejected by this build with
// SFE-709 "No master specified for instance `options'", so the instantiation form is used.
simopt options temp=27
include "{lib}" section=tt
subckt sc1_r2e_cal_load (rail vss)
  R1 (rail node_mid) resistor r=10000
  Ip1 (node_mid vss) iprobe
ends sc1_r2e_cal_load
{name} (rail 0) vsource dc={volts}
Vss (vss 0) vsource dc=0
Xcal (rail vss) sc1_r2e_cal_load
sw1 tran stop=20n maxstep=1n
// Hierarchical names were measured on this build (scripts/sc1_r2e_saveprobe.py): a DOT separates the
// instance from the internal name, `Xcal/...' and `Xcal:i' are ignored with SPECTRE-8281/8282 and the
// bare `Ip1:i' of a device that lives inside a subckt is ignored too, which is why the bare form is
// kept here as a live negative and the dotted forms carry the real readings.
save rail vss Xcal.node_mid Xcal.Ip1:i Ip1:i
{saves}
'''


SRC_LINE = re.compile(r'^\s*(V\S+)\s*\((\S+)\s+(\S+)\)\s+vsource\b([^\n]*)', re.M)


def deck_supply_map(path):
    """Build the supply map from the deck's own independent sources instead of naming it by hand.

    R2E1 called the gate with `vdd18=1.8' while this bench's source and Xcal port are both called
    `rail', so the audited checker refused every calibration run with
    `contract entry vdd18 matches no instance port' (kept in sc1_r2e_calibration.csv). Reading the
    map out of the deck means a renamed net cannot silently survive as a stale contract entry.

    -> (map, rail_instance, rail_net), or (None, ...) unless the deck declares exactly one
       nonzero-dc source whose second terminal is the ground net.
    """
    txt = u(io.open(path, encoding='utf-8', errors='replace').read())
    entries, rails = [], []
    for m in SRC_LINE.finditer(txt):
        inst, na, nb, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        dc = re.search(r'\bdc=(\S+)', rest)
        if not dc or nb != '0':
            continue
        try:
            v = float(dc.group(1))
        except ValueError:
            continue
        entries.append('%s=%s' % (na, dc.group(1)))
        if abs(v) > 1e-12:
            rails.append((inst, na))
    if len(rails) != 1:
        return None, None, None
    return ' '.join(entries), rails[0][0], rails[0][1]


def preflight_and_run(add, log_lines, deck, name, form, tag, volts):
    """preflight FULL then the runner, through scripts/sc1_r2e1_call_contract.py.

    Split out so the R2E1 call tests can drive THIS path with isolated mocks. The R2E form called both
    as `... 2>&1 | tail -N`, which reported TAIL's exit code: a supply_contract refusal that printed
    `TESTBENCH_PREFLIGHT: FAIL` and exited 1 was recorded as rc=0/PASS and the runner was still
    called. A PASS token alone is also no longer enough for the run: the real runner rc, this label's
    single completion line, the SPECTRE status rc, CHECK error_hits and this run's own readable
    datafile and log are all required, and each rc is stored under its own name.

    Returns (preflight_ok, runner_ok, datafile, logfile); a False means the caller reads nothing.
    """
    # The supply map is read FROM THE DECK rather than named after the source instance: the bench's
    # independent source is `V18 (rail 0) vsource ...', so the rail net the gate has to see is `rail',
    # and R2E1 still passed `vdd18=1.8' here, which the supply checker refused as matching no instance
    # port (kept in sc1_r2e_calibration.csv). Deriving it means a stale name cannot survive a rename.
    smap, src_inst, rail_net = deck_supply_map(deck)
    if smap is None:
        add('PREFLIGHT_FULL', os.path.basename(deck),
            'the deck declares exactly one nonzero-dc source on a grounded net',
            'NO_RAIL_SOURCE_FOUND', 9, 'BLOCKED',
            'the supply map is taken from the deck line, so nothing is called with a guessed name')
        return False, False, '', ''
    pf_cmd = '%s "%s" %s cal_%s "%s"' % (
        CC.hook('QODER_PF_CMD', 'bash ' + os.path.join(HERE, 'tb_preflight.sh')), deck, volts,
        name.lower(), smap)
    penv = dict(os.environ)
    penv.pop('PREFLIGHT_STATIC_PROBE', None)          # unset, not empty: this is the full gate
    pfr, pftxt = CC.call(pf_cmd, env=penv)
    pf_ok, pf_reason, pf_summary = CC.preflight_verdict(pfr, pftxt)
    add('PREFLIGHT_FULL', os.path.basename(deck),
        'the preflight own rc=0 AND exactly one TESTBENCH_PREFLIGHT: PASS',
        'rc=%s map=%s (%s on %s) | %s' % (pfr, smap, src_inst, rail_net,
                                          pf_summary.replace('\n', ' | ')[:110]), pfr,
        'PASS' if pf_ok else 'BLOCKED', '%s | %s' % (pf_reason, scrub(pftxt.strip()))[:150])
    if not pf_ok:
        return False, False, '', ''

    label = 'CAL_%s_%s' % (name, tag)
    # LABEL travels in the environment because run_spectre.sh's `$1` is the netlist; the mock asserts
    # that argv shape, so a wrong call shape cannot be mistaken for a successful run
    renv = dict(os.environ)
    renv['LABEL'] = label
    renv.pop('PREFLIGHT_STATIC_PROBE', None)
    rc, txt = CC.call('%s "%s" 120' % (CC.hook('QODER_RUN_CMD', 'bash ' + os.path.join(
        HERE, 'run_spectre.sh')), deck), env=renv)
    runner_ok, run_reasons, parts = CC.runner_verdict(label, deck, rc, txt)
    err = re.search(r'ERROR \([A-Z0-9-]+\)[^\n]*', txt)
    add('SIM_RUN', '%s %s' % (name, form),
        'runner rc=0 + one PASS for this label + spectre rc=0 + error_hits=0 + own data',
        'runner_rc=%s preflight_rc=%s spectre_rc=%s error_hits=%s pass_lines=%d'
        % (rc, pfr, parts.get('spectre_rc', ''), parts.get('error_hits', ''),
           parts.get('pass_lines', 0)), rc, 'PASS' if runner_ok else 'BLOCKED',
        ('; '.join(run_reasons)[:130] or
         scrub(err.group(0) if err else 'contract satisfied').replace('\n', ' ')[:130]))
    log_lines.append('=== %s %s run %s\n%s' % (name, form, 'accepted' if runner_ok else 'REJECTED',
                                               scrub(txt)))
    if not runner_ok:
        return True, False, '', ''
    return True, True, parts['datafile'], parts['logfile']


def main():
    op = optparse.OptionParser()
    op.add_option('--scratch')
    op.add_option('--out')
    op.add_option('--only')
    op.add_option('--forms', default='all',
                  help="'all' runs the three candidate save forms R2E probed; 'i' runs only the form "
                       "this project actually adopted (save <source>:i), which is what the R2E2 "
                       "re-verification is limited to")
    o, _ = op.parse_args()
    scratch = o.scratch or os.path.join(PROJ, 'cadence_work', 'sc1_sim', 'r2e_cal')
    out_csv = o.out or os.path.join(PROJ, 'results', 'evidence', 'sc1_r2e_calibration.csv')
    if not os.path.isdir(scratch):
        os.makedirs(scratch)
    rows = []
    log_lines = []

    def add(item, deck, expected, actual, rc, verdict, note):
        rows.append([item, deck, expected, actual, str(rc), verdict, note])
        print('%-22s %-14s exp=%-22s act=%-24s rc=%-4s %s' % (item, deck or '-', expected, actual,
                                                              rc, verdict))

    # ---------------------------------------------------------------- 1. model binding
    rc, txt = sh('cd %s && . ./skill/cad_env.sh >/dev/null 2>&1; '
                 '[ -f spectre/pdk_local.env ] && . spectre/pdk_local.env; echo "$QODER_PDK_LIB"' % PROJ)
    lib = txt.strip().split('\n')[-1]
    if not lib or not os.path.isfile(lib):
        add('MODEL_BINDING', '-', 'resolved local env file', 'NOT_RESOLVED', 1, 'BLOCKED',
            'set QODER_PDK_LIB in spectre/pdk_local.env; nothing else runs without it')
        write_out(out_csv, rows)
        return 1
    h = hashlib.sha256(open(lib, 'rb').read()).hexdigest()
    rc2, sect = sh('grep -c "^section tt" %s' % lib)
    add('MODEL_BINDING', os.path.basename(lib), 'section tt declared, file present',
        'sha256=%s section_tt_lines=%s' % (h[:16], sect.strip()), 0,
        'PASS' if sect.strip() not in ('0', '') else 'FAIL',
        'hash of the file the deck includes; recorded without its absolute path')

    # The task book's point: the same three digests as the uploaded archive are not enough -- the
    # binding has to be re-read from the file this round's deck actually includes, together with the
    # nested includes of the tt section and the load path.
    pdkdir = os.path.dirname(lib)
    inclist, inside_tt = [], False
    for line in io.open(lib, encoding='utf-8', errors='replace'):
        st = line.strip()
        if st.startswith('section '):
            inside_tt = st.split()[1].lower() == 'tt'
            continue
        if inside_tt and st.startswith('include '):
            inclist += re.findall(r'"([^"]+)"', st)
    inclist = sorted(set(inclist))
    mdlsha = {}
    for inc in inclist:
        p = os.path.join(pdkdir, inc)
        if os.path.isfile(p):
            mdlsha[inc] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    add('MODEL_INCLUDE_GRAPH', os.path.basename(lib), 'nested includes of section tt, each present',
        ' ; '.join('%s=%s' % (k, v[:12]) for k, v in sorted(mdlsha.items()))[:150], len(inclist),
        'PASS' if inclist and len(mdlsha) == len(inclist) else 'PARTIAL',
        'the model records come from these files, not from the .lib alone')
    for label, target, want in (('lib', os.path.basename(lib),
                                 'fc8d321752f2bacf530d5c5eb151f4e623086c174be8da3c19ee8d26e3dcf95f'),
                                ('mdl', 'ms018_enhanced_v1p2_rev0_spe.mdl',
                                 '5187cae15226ffdeef7c82e844d2ba15cc823b52a90b86eec55548b5f03e7fc1'),
                                ('readme', 'ms018_enhanced_v1p2_rev0_readme_spe.txt',
                                 'f43d2585330a1cdd438d280d066e3b678165d102084cb6aa3a071400d406d875')):
        p = os.path.join(pdkdir, target)
        got = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.isfile(p) else ''
        add('UPLOAD_HASH_COMPARISON', label, 'digest given in the task book',
            '%s on the included file' % ('MATCH' if got == want else 'DIFFERS'), 0,
            'PASS' if got == want else 'FAIL', 're-hashed this round from the loaded path')

    # ---------------------------------------------------------- 2. geometry limits, per model
    # Read straight out of the model records the tt section pulls in, with the declaring file kept so a
    # limit is never attributed to the wrong master. These records continue over several lines (the
    # lmin/lmax/wmin of n18 sit on a continuation line, measured), so the text up to the next `model'
    # statement is taken as one record rather than one line.
    geo = {}
    found = {}
    for fname in sorted(mdlsha):
        lines = [l.rstrip('\n') for l in io.open(os.path.join(pdkdir, fname),
                                                 encoding='utf-8', errors='replace')]
        starts = [i for i, l in enumerate(lines) if re.match(r'\s*model\s+\S+', l, re.I)]
        for n, i in enumerate(starts):
            name = re.match(r'\s*model\s+(\S+)', lines[i], re.I).group(1)
            end = starts[n + 1] if n + 1 < len(starts) else min(i + 40, len(lines))
            # the limits sit on the record's own continuation line (`+lmin = ... lmax = ... wmin = ...',
            # measured), so all three are matched together on one line and the first such line wins;
            # matching key-by-key over the whole record picked up an unrelated later wmin.
            for k in range(i, end):
                m = re.search(r'\blmin\s*=\s*([0-9.eE+-]+)\s+lmax\s*=\s*([0-9.eE+-]+)\s+'
                              r'wmin\s*=\s*([0-9.eE+-]+)', lines[k], re.I)
                if m:
                    found.setdefault(name.lower(), []).append(
                        (fname, 'line %d' % (k + 1)) + m.groups())
                    break
    for want in ('n18', 'p18', 'n33', 'p33'):
        recs = found.get(want, [])
        if not recs:
            add('MODEL_RECORD_SOURCE', want, 'a record with lmin/lmax/wmin exists', 'NOT_FOUND', 0,
                'PARTIAL', 'no such model record in the files the tt section includes')
            continue
        distinct = set(tuple(r[2:]) for r in recs)
        add('MODEL_RECORD_SOURCE', want, 'declared once, or identically wherever it is declared',
            ' ; '.join('%s %s lmin=%s lmax=%s wmin=%s' % r for r in recs)[:150], len(recs),
            'PASS' if len(distinct) == 1 else 'PARTIAL',
            'where the geometry limits below were read from')
        if len(distinct) == 1:
            geo[want] = list(recs[0][2:])
    rc, sizeraw = sh("grep -oE '(l18|l33|w18p|w18n|w33|w33n)=[0-9.eE+-]+' "
                     ' %s' % os.path.join(PROJ, 'spectre', 'sc1_level_shifter_r2d.scs'))
    sizes = {}
    for tok in sizeraw.split('\n'):
        if '=' in tok:
            k, v = tok.split('=', 1)
            try:
                sizes.setdefault(k, []).append(float(v))
            except ValueError:
                pass
    # which frozen sizes actually hang off which model record, read out of the cell itself
    checks = [('low-domain driver p18/n18', 'p18', ['l18'], ['w18p', 'w18n']),
              ('low-domain driver n18', 'n18', ['l18'], ['w18p', 'w18n']),
              ('cross-coupled / nand p33', 'p33', ['l33'], ['w33', 'w33n']),
              ('high-domain pull-down n33', 'n33', ['l33'], ['w33'])]
    for label, model, lkeys, wkeys in checks:
        if model not in geo or not any(k in sizes for k in lkeys):
            add('GEOMETRY_RANGE_READ', label, 'lmin/wmin for %s' % model, 'MODEL_OR_SIZE_NOT_FOUND',
                0, 'PARTIAL', 'the model record or the size parameter was not found in the files read')
            continue
        lmin, lmax, wmin = geo[model]
        lvals = [v for k in lkeys for v in sizes.get(k, [])]
        wvals = [v for k in wkeys for v in sizes.get(k, [])]
        worst_l_min, worst_l_max = min(lvals), max(lvals)
        worst_w = min(wvals)
        ok = (worst_l_min >= float(lmin) - 1e-15) and (worst_l_max <= float(lmax) + 1e-15) \
            and (worst_w >= float(wmin) - 1e-15)
        add('GEOMETRY_RANGE_READ', label, 'lmin=%s lmax=%s wmin=%s' % (lmin, lmax, wmin),
            'uses l=%s..%s w_min=%s' % (worst_l_min, worst_l_max, worst_w), 0,
            'PASS' if ok else 'FAIL',
            'model/bin limit read from the included .mdl; NOT an absolute maximum rating and NOT the '
            'characterisation range')
    rc, rr = sh('grep -ic "temperature range" %s' % os.path.join(
        os.path.dirname(lib), 'ms018_enhanced_v1p2_rev0_readme_spe.txt'))
    add('CHARACTERISATION_RANGE', 'README', 'temperature range stated',
        '%d lines state -40C~125C' % int(rr or 0), 0,
        'PASS' if int(rr or 0) > 0 else 'PARTIAL', '27 C is inside it; no absolute-rating table '
        'exists in the readable files, so SOA_SIGNOFF stays NO')

    # --------------------------------------------------- 3. the help text that justifies temp=
    rc, hlp = sh('. %s >/dev/null 2>&1; spectre -h options 2>&1 | grep -iE "temp=|tnom=" | head -4'
                 % os.path.join('/root', 'qoder_ic617_sandbox', 'bin', 'cad_env.sh'))
    add('TEMP_SYNTAX_SOURCE', 'spectre -h options', 'help lists the option name',
        ' ; '.join([l.strip() for l in hlp.split('\n') if l.strip()])[:120], 0,
        'PASS' if 'temp=' in hlp else 'FAIL', 'this build\'s own help, not remembered syntax')

    # --------------------------------------------------- 4. the two calibration benches
    # Everything above is read-only file inspection; this section calls the simulator, so it needs the
    # same two flags the S1/S2 entries need. Without them the read-only rows still stand and this
    # section records NOT_RUN -- the entry must not be executable "because main could be run".
    authorised = os.environ.get('RUN') == '1' and os.environ.get('QODER_SIM_AUTHORISED') == '1'
    if not authorised:
        for nm in ('V18', 'V33'):
            add('CALIBRATION_BENCH', 'cal_%s' % nm.lower(), 'RUN=1 and QODER_SIM_AUTHORISED=1',
                'refused', 5, 'NOT_RUN',
                'the read-only model/temperature rows above are file inspection; nothing was simulated')
        write_out(out_csv, rows)
        print('R2E_CALIBRATION forms=%s authorised=NO -> nothing ran' % o.forms)
        return 5

    # One candidate save form per run: a fatal save kills the whole deck. R2E probed three; R2E2
    # re-verifies only the one this project actually adopted, so the scope cannot widen by accident.
    forms = ['{n}:i'] if o.forms == 'i' else ['{n}:i', '{n}:1', '{n}:current']
    for name, volts, want in (('V18', 1.8, 1.8 / 1e4), ('V33', 3.3, 3.3 / 1e4)):
        deck = os.path.join(scratch, 'cal_%s.scs' % name.lower())
        for form in forms:
            form = form.format(n=name)
            tag = form.replace(' ', '_').replace(':', '-').replace('.', '_')
            # one deck FILE per candidate form: three runs sharing one name also shared one raw
            # directory, so a later failed run could point at an earlier readable file
            deck = os.path.join(scratch, 'cal_%s_%s.scs' % (name.lower(), tag))
            with io.open(deck, 'w', encoding='utf-8', newline='\n') as f:
                f.write(u(DECK.format(lib='${QODER_PDK_LIB}', name=name, volts=volts,
                                      saves='save %s' % form)))
            pf_ok, runner_ok, df, log = preflight_and_run(add, log_lines, deck, name, form, tag,
                                                           volts)
            if not pf_ok or not runner_ok:
                # the refusal is the end of this deck: no reader is called with a stale file
                continue

            # ---- temperature, read out of the produced files rather than assumed
            temp_log = temp_hdr = None
            if log and os.path.isfile(log):
                for line in io.open(log, encoding='utf-8', errors='replace'):
                    m = re.match(r'\s*temp\s*=\s*([0-9.eE+-]+)', line)
                    if m:
                        temp_log = m.group(1)
                        break
            if df and os.path.isfile(df):
                for line in io.open(df, encoding='utf-8', errors='replace'):
                    if line.startswith('VALUE'):
                        break
                    m = re.match(r'"temp"\s+([0-9.eE+-]+)', line)
                    if m:
                        temp_hdr = m.group(1)
            oktemp = temp_log is not None and temp_hdr is not None \
                and abs(float(temp_log) - 27) < 1e-6 and abs(float(temp_hdr) - 27) < 1e-6
            add('TEMP_CONFIRMATION', os.path.basename(deck), '27 C echoed by the run',
                'log temp=%s ; psf header temp=%s' % (temp_log, temp_hdr), 0,
                'PASS' if oktemp else 'PARTIAL',
                'both values are read from files this run produced; a generator comment or a build '
                'default is not a measurement')

            # ---- every saved quantity this deck should now carry
            readings = {}
            for sig in (form, 'Xcal.Ip1:i', 'Xcal.node_mid', 'Ip1:i'):
                if not df:
                    readings[sig] = (9, 'NO_DATAFILE')
                    continue
                rr2, val = CC.call('%s --data "%s" --sig %s --mode last'
                                   % (CC.hook('QODER_READ_CMD', '"%s" "%s"' % (sys.executable,
                                             os.path.join(HERE, 'sc1_read_psf.py'))), df, sig))
                readings[sig] = (rr2, val.strip().split('\n')[0])

            def num(sig):
                rc_, txt_ = readings[sig]
                if rc_ != 0:
                    return None
                try:
                    return float(txt_)
                except ValueError:
                    return None

            # the direct source branch. Its sign is the whole point of the bench: a rail that DELIVERS
            # want amps reads back as -want through the source, so the DUT-injected current is -I(source).
            src = num(form)
            if src is None:
                add('SOURCE_CURRENT_CALIBRATION', '%s %s' % (name, form), 'magnitude %.6g A' % want,
                    readings[form][1][:60], readings[form][0],
                    'EXPECTED_REFUSAL' if form.endswith(':current') else 'NOT_AVAILABLE',
                    'reader exit %s; no value is invented and no drain-sum is substituted'
                    % readings[form][0])
            else:
                add('SOURCE_CURRENT_CALIBRATION', '%s %s' % (name, form),
                    'saved as %.6g A when the rail delivers %.6g A' % (-want, want),
                    '%.6g A (so injected = %.6g A)' % (src, -src), readings[form][0],
                    'PASS' if abs(-src - want) <= 0.02 * want else 'FAIL',
                    'positive direction = out of the source into the load; the raw reading keeps the '
                    "simulator's own sign")

            # the load branch, by the verified zero-drop iprobe inside the subckt
            ipr = num('Xcal.Ip1:i')
            add('BRANCH_PROBE_CALIBRATION', '%s Xcal.Ip1:i' % name, '%.6g A, positive first->second'
                % want, '%.6g A' % ipr if ipr is not None else readings['Xcal.Ip1:i'][1][:60],
                readings['Xcal.Ip1:i'][0],
                'PASS' if ipr is not None and abs(ipr - want) <= 0.02 * want else 'NOT_AVAILABLE',
                'independent magnitude check of the same bench; dotted hierarchical name')

            node = num('Xcal.node_mid')
            add('HIERARCHICAL_NODE_READ', '%s Xcal.node_mid' % name, '|v| < 1 mV (zero-drop iprobe)',
                '%.6g V' % node if node is not None else readings['Xcal.node_mid'][1][:60],
                readings['Xcal.node_mid'][0],
                'PASS' if node is not None and abs(node) < 1e-3 else 'NOT_AVAILABLE',
                'proves the instance-path save really reaches inside the subckt')

            bare = num('Ip1:i')
            add('SAVE_FORM_BARE_INSIDE_SUBCKT', '%s Ip1:i' % name, 'refused: the device is not top-level',
                'read back %.6g A' % bare if bare is not None else readings['Ip1:i'][1][:60],
                readings['Ip1:i'][0],
                'EXPECTED_REFUSAL' if bare is None else 'FAIL',
                'measured as SPECTRE-8282/8287; if it ever reads, the hierarchy conclusion is wrong')

            if src is not None and ipr is not None:
                agree = abs((-src) - ipr) <= 0.02 * want
                add('CURRENT_SIGN_CONVENTION', '%s' % name,
                    '-(source branch) == +iprobe branch', '%.6g vs %.6g A' % (-src, ipr), 0,
                    'PASS' if agree else 'FAIL',
                    'this is the rule the S2 entries use for rail current; a sum of MOS drain currents '
                    'is not taken as the supply current')
            log_lines.append('=== %s %s run\n%s' % (name, form, scrub(txt)))

    write_out(out_csv, rows)
    with io.open(out_csv.replace('.csv', '_log.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(u(scrub('\n'.join(log_lines))))
    bad = [r for r in rows if r[5] not in ('PASS', 'EXPECTED_REFUSAL')]
    print('R2E_CALIBRATION rows=%d not_pass=%d (EXPECTED_REFUSAL rows are measured negatives, not '
          'failures)' % (len(rows), len(bad)))
    for r in bad:
        print('   %s: %s (%s)' % (r[0], r[6][:110], r[5]))
    print('R2E_CAL_CSV=%s' % out_csv)
    return 0 if not bad else 1


def write_out(path, rows):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    hdr = ['item', 'deck_or_target', 'expected', 'actual', 'rc', 'verdict', 'note']
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(csvline(hdr))
        for r in rows:
            f.write(csvline(r))


if __name__ == '__main__':
    sys.exit(main())
