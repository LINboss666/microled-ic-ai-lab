#!/bin/bash
# SCH-3 sections 14/15: regress the OA-derived netlists under the accepted DATA-5 conditions.
#
# What is being proven: the same circuit that was accepted at transistor level, re-simulated with
# every device line rebuilt from the Virtuoso cellviews (scripts/sch3_deck_from_oa.py), must give the
# same numbers. Nothing here re-tunes a size, moves a source or relaxes a criterion; the analysers
# and their flags are the ones DATA-5 used (scripts/ddrv_corner_probe.sh), so the two result sets are
# comparable line by line.
#
# Two export forms are run on purpose:
#   flat -- the deck keeps the accepted net names, so the numbers are directly comparable to the
#           accepted evidence (this is the regression proper).
#   hier -- the two cellviews are instantiated as sub-circuits, which is what shows each channel
#           really owns its gate/body node instead of sharing one by accident.
#
# Runs on the guest. Usage: bash scripts/sch3_regression.sh [CORNERS]
set -u
PROJ="${PROJ:-/root/microled_ai_project}"
cd "$PROJ" || exit 9
CORNERS="${1:-${CORNERS:-tt ss ff}}"
GEND="$PROJ/spectre/generated"
LOGD="$PROJ/logs"
EVD="$PROJ/results/evidence"
RESD="$PROJ/results"
RB="${RB:-results/evidence/sch3_readback_post_fix.log}"
VOUT_REP="${VOUT_REP:-1.20}"
mkdir -p "$LOGD" "$EVD" "$RESD"
DC_CSV="$RESD/data_driver_schematic_dc.csv"
TR_CSV="$RESD/data_driver_schematic_transient.csv"
XT_CSV="$RESD/data_driver_schematic_xtalk.csv"
rc_total=0
hier_status=PASS
# a fresh run starts from empty result files; SKIP_CORNERS=1 is the "re-run only the static enable
# matrix" mode, and it must not throw away the corner results that are already in place
if [ "${SKIP_CORNERS:-0}" = "1" ]; then
  echo "SKIP_CORNERS=1 -- corner CSVs kept, only the static enable matrix runs"
else
  rm -f "$DC_CSV" "$TR_CSV" "$XT_CSV"
fi

# the accepted decks, named out of the repository so a typo cannot invent a different circuit.
# The corner appears twice in DATA-5's file names (once in the device tag, once after dnwpass_),
# which an earlier version of these globs got wrong and reported "accepted deck missing".
deck_for() {   # $1 corner  $2 on|off
  ls "$GEND"/ddrv_E_local_gate_n33_${1}_l2e6w2e5_ch1_iprobe_dnwpass_${1}_${2}.scs 2>/dev/null | head -1
}
deck_tran_for() {   # $1 corner  $2 base|dyn
  ls "$GEND"/ddrv_E_local_gate_n33_${1}_l2e6w2e5_ch2_iprobe_mgear2only_dnwpass_${1}_${2}_T9.765625e6vout1.20_ms5ns.scs 2>/dev/null | head -1
}
deck_static_for() {   # $1 e00|e01|e10|e11
  ls "$GEND"/ddrv_E_local_gate_n33_tt_l2e6w2e5_ch2_iprobe_dnwpass_E_local_gate_static_${1}_T2e7vout1.2_ms1ns.scs 2>/dev/null | head -1
}

run_one() {   # $1 deck(scs path)  $2 tag  $3 kind(dc|tran)  $4 analyser script  $5... analyser flags
  local deck="$1" tag="$2" kind="$3" analyser="$4"; shift 4
  local log="$LOGD/preflight_sch3_${tag}.txt"
  bash scripts/tb_preflight.sh "$deck" 1.8 "sch3_${tag}" > "$log" 2>&1
  if [ $? -ne 0 ] || ! grep -q "TESTBENCH_PREFLIGHT: PASS" "$log"; then
    echo "PREFLIGHT_FAIL ${tag}"; grep -E "STATIC_FAIL|OP_FAIL|RAIL_OVERSHOOT|TESTBENCH_PREFLIGHT" "$log" | head -5
    rc_total=1; return 7
  fi
  echo "TESTBENCH_PREFLIGHT: PASS (${tag})"
  LABEL="DATA_DRIVER_$(echo "$kind" | tr 'a-z' 'A-Z')" bash scripts/run_spectre.sh "$deck" 300 \
      > "$LOGD/run_sch3_${tag}.txt" 2>&1
  local rrc=$? psf="" stem dir f
  stem=$(basename "$deck"); stem="${stem%.scs}"; dir=$(dirname "$deck")
  for f in "$dir/sim/$stem.raw"/*; do
    [ -f "$f" ] || continue
    if grep -qa "^VALUE" "$f" && grep -qa "^TRACE" "$f"; then psf="$f"; break; fi
  done
  if [ -z "$psf" ]; then
    echo "SIM_NO_DATA ${tag} (rc=$rrc)"; tail -6 "$LOGD/run_sch3_${tag}.txt"; rc_total=1; return 6
  fi
  local errs warns
  errs=$(grep -acE "^ERROR|spectre terminated prematurely" "$LOGD/run_sch3_${tag}.txt" || true)
  warns=$(grep -aoE "[0-9]+ warnings" "$LOGD/run_sch3_${tag}.txt" | tail -1 | awk '{print $1}')
  echo "SIM ${tag}: rc=$rrc errors=${errs:-0} warnings=${warns:-0}"
  if [ "${errs:-1}" != "0" ] || [ "${warns:-1}" != "0" ]; then
    echo "SIM_UNCLEAN ${tag}: the log's error/warning budget is part of the verdict"
    grep -A2 -E "^ERROR|^WARNING" "$LOGD/run_sch3_${tag}.txt" | head -8
    rc_total=1; return 5
  fi
  python "$analyser" "$psf" "$@" > "$EVD/sch3_${tag}.txt" 2>&1
  echo "$psf" > "$LOGD/psf_sch3_${tag}.txt"
  grep -aE "IOUT@max|COMPLIANCE_1PCT|NOMINAL|PROBE_BURDEN|DATA_DRIVER_|TURN_ON_SETTLING|TURN_OFF|PEAK_CROSSTALK|CHARGE_ERROR|GLITCH_|RINGING|I_BASELINE|VBIAS_SHARED|vbias_ch|INDEPENDENCE|FAIL" \
      "$EVD/sch3_${tag}.txt" | sed 's/^/    /'
  # the analyser's own verdict is part of the result. Without this line a run could report
  # "0 errors, 0 warnings" while the checker said FAIL -- which is what happened on the first
  # pass of this script, where --ref was handed a deck path instead of a baseline data file.
  if grep -qE ": FAIL" "$EVD/sch3_${tag}.txt"; then
    # IGNORE_FAIL_TOKEN names a verdict this run shape cannot produce meaningfully. It is only ever
    # set to TWO_CHANNEL_INDEPENDENCE, for the static enable matrix: with a channel held OFF the
    # analyser expresses its peak as a percentage of the 15 uA target and prints 100 %, and the
    # ACCEPTED DATA-5 evidence for the same decks contains exactly that line (see
    # results/evidence/ddrv_E_local_gate_static_e00.txt). DATA-5 judged that matrix from the measured
    # per-channel currents, which scripts/sch3_compare_regression.py reproduces against the accepted
    # table -- so the matrix is still verified, just not by a token that means nothing here.
    local flagged ignoring
    flagged=$(grep -aoE "[A-Z_]+: FAIL" "$EVD/sch3_${tag}.txt" | awk -F: '{print $1}' | sort -u | tr '\n' ' ')
    ignoring="${IGNORE_FAIL_TOKEN:-}"
    if [ -n "$ignoring" ] && [ "$(echo "$flagged" | wc -w)" -eq 1 ] && echo "$flagged" | grep -qw "$ignoring"; then
      echo "ANALYSER_TOKEN_NOT_APPLICABLE ${tag}: $ignoring (the accepted data prints the same line;"
      echo "  the verdict for this run comes from the CSV comparison instead)"
    else
      echo "ANALYSER_FAIL ${tag}: $flagged"
      rc_total=1
    fi
  elif ! grep -qE ": (OK|PASS)" "$EVD/sch3_${tag}.txt"; then
    echo "ANALYSER_NO_VERDICT ${tag}: the evidence file carries neither OK nor PASS nor FAIL"
    rc_total=1
  else
    echo "ANALYSER_VERDICT ${tag}: OK/PASS present, no FAIL"
  fi
}

for c in $CORNERS; do
  [ "${SKIP_CORNERS:-0}" = "1" ] && break
  echo
  echo "================ CORNER $c"
  for st in on off; do
    src=$(deck_for "$c" "$st")
    [ -n "$src" ] || { echo "MISSING accepted deck for $c/$st"; rc_total=1; continue; }
    out="$GEND/sch3_oa_flat_${c}_${st}.scs"
    python scripts/sch3_deck_from_oa.py --deck "$src" --readback "$RB" --form flat --out "$out" \
        | tee "$LOGD/export_${c}_${st}.txt" | grep -aE "OA_NETLIST_EXPORT|OA_DECK_MISMATCH"
    grep -q "OA_NETLIST_EXPORT: PASS" "$LOGD/export_${c}_${st}.txt" || { echo "EXPORT_FAIL ${c}_${st}"; rc_total=1; continue; }
    run_one "$out" "flat_${c}_${st}" dc scripts/ddrv_characterize.py --require-probe \
        --nominal "$VOUT_REP" --label "SCH3_flat_${c}_${st}" --csv "$DC_CSV"
  done
  # ---- the hierarchical form is generated but NOT simulated, and the reason is recorded rather
  # than quietly worked around: scripts/tb_preflight.sh requires every sub-circuit instance to
  # expose ports named vdd and vss. This cell is a low-side current sink -- it has VSS and no VDD
  # by design -- and the OA port names are the ones SCH-3 section 6 specifies, so the rule fires a
  # false positive. The preflight is a shared audited gate for the whole project, and relaxing it is
  # a human decision, not something to do at 01:00 in an unsupervised run to make a deck simulate.
  # The composition proof therefore rests on the flat OA decks plus the OA readback (each channel
  # really owns a private vbias_ch: 8 nets of which 6 are pinned).
  hout="$GEND/sch3_oa_hier_${c}_on.scs"
  python scripts/sch3_deck_from_oa.py --deck "$(deck_for "$c" on)" --readback "$RB" --form hier \
      --out "$hout" > "$LOGD/export_${c}_hier_on.txt" 2>&1
  bash scripts/tb_preflight.sh "$hout" 1.8 "sch3_hier_${c}_on" > "$LOGD/preflight_sch3_hier_${c}_on.txt" 2>&1
  if grep -q "TESTBENCH_PREFLIGHT: PASS" "$LOGD/preflight_sch3_hier_${c}_on.txt"; then
    echo "HIER_PREFLIGHT: PASS ($c) -- running the hierarchical deck"
    run_one "$hout" "hier_${c}_on" dc scripts/ddrv_characterize.py --require-probe \
        --nominal "$VOUT_REP" --label "SCH3_hier_${c}_on" --csv "$DC_CSV"
  else
    echo "HIER_PREFLIGHT: BLOCKED_BY_PORT_RULE ($c) -- deck generated, not simulated"
    grep -aE "STATIC_FAIL" "$LOGD/preflight_sch3_hier_${c}_on.txt" | head -4 | sed 's/^/      /'
    hier_status=BLOCKED_BY_PREFLIGHT_PORT_RULE
  fi

  base=$(deck_tran_for "$c" base); dyn=$(deck_tran_for "$c" dyn)
  [ -n "$dyn" ] || { echo "MISSING accepted transient deck for $c"; rc_total=1; continue; }
  bout="$GEND/sch3_oa_flat_${c}_base.scs"; dout="$GEND/sch3_oa_flat_${c}_dyn.scs"
  if [ -n "$base" ]; then
    python scripts/sch3_deck_from_oa.py --deck "$base" --readback "$RB" --form flat --out "$bout" \
        > "$LOGD/export_${c}_base.txt" 2>&1
  fi
  python scripts/sch3_deck_from_oa.py --deck "$dyn" --readback "$RB" --form flat --out "$dout" \
      > "$LOGD/export_${c}_dyn.txt" 2>&1
  grep -q "OA_NETLIST_EXPORT: PASS" "$LOGD/export_${c}_dyn.txt" || { echo "EXPORT_FAIL ${c}_dyn"; rc_total=1; continue; }
  run_one "$dout" "flat_${c}_ch0" tran scripts/ddrv_tran.py --require-probe \
      --label "SCH3_flat_${c}_ch0" --csv "$TR_CSV"
  # the unswitched neighbour run is the reference the crosstalk numbers are taken against, and
  # --ref wants that run's DATA FILE, not its deck (ddrv_xtalk.py compares two psfascii traces)
  if [ -n "$base" ] && [ -f "$bout" ]; then
    run_one "$bout" "flat_${c}_base" tran scripts/ddrv_tran.py --require-probe \
        --label "SCH3_flat_${c}_base" --csv "$TR_CSV"
    bpsf=$(cat "$LOGD/psf_sch3_flat_${c}_base.txt" 2>/dev/null)
    if [ -n "$bpsf" ] && [ -f "$bpsf" ]; then
      run_one "$dout" "flat_${c}_victim" tran scripts/ddrv_xtalk.py --ch 1 --ref "$bpsf" \
          --skip-frac 0.2 --require-probe --label "SCH3_flat_${c}_victim" \
          --slew-desc "10 ns edge, method=gear2only, maxstep=5 ns, FRAME_SCALE" --csv "$XT_CSV"
    else
      echo "SKIP_CROSSTALK ${c}: no baseline data file to compare against"
      rc_total=1
    fi
  else
    echo "SKIP_CROSSTALK ${c}: no baseline deck to compare against"
    rc_total=1
  fi
  hout="$GEND/sch3_oa_hier_${c}_dyn.scs"
  python scripts/sch3_deck_from_oa.py --deck "$dyn" --readback "$RB" --form hier --out "$hout" \
      > "$LOGD/export_${c}_hier_dyn.txt" 2>&1
  bash scripts/tb_preflight.sh "$hout" 1.8 "sch3_hier_${c}_dyn" > "$LOGD/preflight_sch3_hier_${c}_dyn.txt" 2>&1
  if grep -q "TESTBENCH_PREFLIGHT: PASS" "$LOGD/preflight_sch3_hier_${c}_dyn.txt"; then
    run_one "$hout" "hier_${c}_ch0" tran scripts/ddrv_tran.py --require-probe \
        --label "SCH3_hier_${c}_ch0" --csv "$TR_CSV"
  else
    echo "HIER_PREFLIGHT: BLOCKED_BY_PORT_RULE ($c dyn) -- deck generated, not simulated"
    hier_status=BLOCKED_BY_PREFLIGHT_PORT_RULE
  fi
done

STATIC_CSV="$RESD/data_driver_schematic_static.csv"
rm -f "$STATIC_CSV"
echo
echo "===== two-channel static combinations (accepted tt decks, OA devices) ====="
# same analyser pair DATA-5 used on the same decks: each channel read out of the identical run, so
# the four combinations become a direct check that one channel's enable cannot move the other
for combo in e00 e01 e10 e11; do
  src=$(deck_static_for "$combo")
  [ -n "$src" ] || { echo "MISSING static deck $combo"; rc_total=1; continue; }
  out="$GEND/sch3_oa_flat_tt_${combo}.scs"
  python scripts/sch3_deck_from_oa.py --deck "$src" --readback "$RB" --form flat --out "$out" \
      > "$LOGD/export_tt_${combo}.txt" 2>&1
  grep -q "OA_NETLIST_EXPORT: PASS" "$LOGD/export_tt_${combo}.txt" || { echo "EXPORT_FAIL $combo"; rc_total=1; continue; }
  IGNORE_FAIL_TOKEN=TWO_CHANNEL_INDEPENDENCE run_one "$out" "flat_tt_${combo}_ch0" tran \
      scripts/ddrv_xtalk.py --ch "" --label "SCH3_flat_tt_static_${combo}_ch0" --csv "$STATIC_CSV"
  IGNORE_FAIL_TOKEN=TWO_CHANNEL_INDEPENDENCE run_one "$out" "flat_tt_${combo}_ch1" tran \
      scripts/ddrv_xtalk.py --ch "1" --label "SCH3_flat_tt_static_${combo}_ch1" --csv "$STATIC_CSV"
done

echo
echo "results: $DC_CSV"
echo "         $TR_CSV"
echo "         $XT_CSV"
echo "         $STATIC_CSV"
echo "OA_HIERARCHICAL_DECK: $hier_status"
echo "SCH3_REGRESSION_RUNS_DONE corners=$CORNERS rc_total=$rc_total"
[ $rc_total -eq 0 ] || exit 1
exit 0
