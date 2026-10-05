#!/bin/bash
# ddrv_run.sh -- one channel of the Micro LED data driver: generate -> preflight ->
# Spectre -> characterise. Runs on the guest (paths under $PROJ) and refuses to simulate
# when the testbench preflight does not pass.
#
#   ddrv_run.sh dc   <candidate> <model> <l> <w> [corner] [vmax] [step]
#   ddrv_run.sh sweep <candidate> <model> <corner> <vmax> <step> "<l...>" "<w...>"
#   ddrv_run.sh selfcheck
#
# Why a selfcheck: this round changed tb_preflight.sh so a FLAT deck (no cell subckt) is
# judged by net name plus operating point instead of being rejected outright. A relaxed
# gate must prove it still catches the failure it exists for, so selfcheck builds the same
# deck with its `vss`-to-0 source deleted and requires the preflight to FAIL.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
PY="${PY:-python}"
GEN="$PROJ/scripts/ddrv_gen.py"
CHAR="$PROJ/scripts/ddrv_characterize.py"
GENDIR="$PROJ/spectre/generated"
LOGDIR="$PROJ/logs"
RESDIR="$PROJ/results"
EVDIR="$RESDIR/evidence"
RSEN="${RSEN:-1e4}"
TARGET="${TARGET:-15e-6}"
mkdir -p "$GENDIR" "$LOGDIR" "$EVDIR" "$RESDIR"

# ---- how IOUT is observed for this run ------------------------------------------
# PROBE=iprobe is the only accepted method for a new baseline: the 10k sense resistor
# drops 150 mV at 15 uA and therefore moves the compliance knee it claims to measure.
# Its runs go to their own CSV files so a burdened number can never be read as the
# current baseline; the old files stay untouched as LEGACY_BURDENED_MEASUREMENT evidence.
PROBE="${PROBE:-rsen}"
case " ${EXTRA:-} " in *iprobe*) PROBE=iprobe;; esac
RSEN_GEN=""; RSEN_CHK="--rsen $RSEN"
if [ "$PROBE" = "iprobe" ]; then
  PROBE_GEN="--probe iprobe"; PROBE_CHK="--require-probe"
  DC_CSV="${DC_CSV:-$RESDIR/data_driver_dc_iprobe.csv}"
  TR_CSV="${TR_CSV:-$RESDIR/data_driver_transient_iprobe.csv}"
else
  PROBE_GEN=""; PROBE_CHK=""
  DC_CSV="${DC_CSV:-$RESDIR/data_driver_dc.csv}"
  TR_CSV="${TR_CSV:-$RESDIR/data_driver_transient.csv}"
fi

tag_of() { echo "$1_$2_$3_l$4_w$5_$6"; }   # candidate model corner l w vout

run_deck() {   # $1 = deck path, $2 = tag, $3 = expected vdd, $4 = kind (dc|tran)
  local deck="$1" tag="$2" vdd="$3" kind="$4"
  local log="$LOGDIR/preflight_${tag}.txt"
  bash "$PROJ/scripts/tb_preflight.sh" "$deck" "$vdd" "$tag" > "$log" 2>&1
  local prc=$?
  if [ "$prc" != "0" ] || ! grep -q "TESTBENCH_PREFLIGHT: PASS" "$log"; then
    echo "ABORT_BEFORE_SIM ${tag}: preflight said FAIL (see logs/preflight_${tag}.txt)"
    grep -E "STATIC_FAIL|OP_FAIL|RAIL_OVERSHOOT|TESTBENCH_PREFLIGHT" "$log" | head -6
    return 7
  fi
  echo "TESTBENCH_PREFLIGHT: PASS (${tag})"
  LABEL="DATA_DRIVER_$(echo "$kind" | tr "a-z" "A-Z")" \
      bash "$PROJ/scripts/run_spectre.sh" "$deck" 300 \
      > "$LOGDIR/run_${tag}.txt" 2>&1
  local rrc=$?
  # locate the PSF-ASCII data file the way the project's own runner defines it: a file in
  # <deck dir>/sim/<stem>.raw that carries both TRACE and VALUE sections (logFile does not)
  local stem dir psf=""
  stem=$(basename "$deck"); stem="${stem%.scs}"
  dir=$(dirname "$deck")
  for f in "$dir/sim/$stem.raw"/*; do
    [ -f "$f" ] || continue
    if grep -qa "^VALUE" "$f" && grep -qa "^TRACE" "$f"; then psf="$f"; break; fi
  done
  if [ -z "$psf" ] || [ ! -f "$psf" ]; then
    echo "SIM_NO_DATA ${tag} (run rc=$rrc)"
    tail -6 "$LOGDIR/run_${tag}.txt"
    return 6
  fi
  # a clean exit is not a result: the log's own error/warning budget is part of the verdict
  local errs warns
  errs=$(grep -acE "^ERROR|spectre terminated prematurely" "$LOGDIR/run_${tag}.txt" || true)
  warns=$(grep -aoE "[0-9]+ warnings" "$LOGDIR/run_${tag}.txt" | tail -1 | awk '{print $1}')
  echo "SIM ${tag}: rc=$rrc errors=${errs:-0} warnings=${warns:-0}"
  if [ "${errs:-1}" != "0" ] || [ "${warns:-1}" != "0" ]; then
    echo "SIM_UNCLEAN ${tag}: error/warning lines in the log must be explained, not ignored"
    grep -A2 -E "^ERROR|^WARNING" "$LOGDIR/run_${tag}.txt" | head -8
    return 5
  fi
  echo "$psf"
  return 0
}

dc_one() {     # candidate model l w corner vmax step
  local cand="$1" model="$2" L="$3" W="$4" corner="${5:-tt}" vmax="${6:-1.8}" step="${7:-0.02}"
  local tag deck psf out
  tag=$(tag_of "$cand" "$model" "$corner" "$L" "$W" "dc")
  # the probe method belongs in the tag: an unburdened re-run of a deck that already has
  # legacy evidence must not overwrite it
  [ "$PROBE" = "iprobe" ] && tag="${tag}_iprobe"
  [ -n "${TAGX:-}" ] && tag="${tag}_${TAGX}"
  deck=$("$PY" "$GEN" --candidate "$cand" --model "$model" --l "$L" --w "$W" \
             --corner "$corner" --vmax "$vmax" --step "$step" --mode dc \
             $PROBE_GEN ${EXTRA:-} ${TAGX:+--suffix "$TAGX"} --out "$GENDIR")
  deck=$(echo "$deck" | tail -1)
  [ -f "$deck" ] || { echo "GEN_FAILED $deck"; return 9; }
  # keep the diagnostics visible: run_deck's status lines go to the console, and the data
  # file it prints last is picked back out of the same stream
  run_deck "$deck" "$tag" 1.8 dc | tee "$LOGDIR/${tag}.pipeline"
  psf=$(grep -aE "^/" "$LOGDIR/${tag}.pipeline" | tail -1)
  if [ -z "$psf" ] || [ ! -f "$psf" ]; then
    echo "DC_FAIL $tag (no usable data file)"; return 8
  fi
  out="$EVDIR/ddrv_${tag}.txt"
  # DDRV_CSV_RESET=1 on the first point of a grid, so the CSV holds
  # exactly this grid instead of a mix of every run since the last reset
  [ "${DDRV_CSV_RESET:-0}" = "1" ] && rm -f "$DC_CSV"
  "$PY" "$CHAR" "$psf" --rsen "$RSEN" --target "$TARGET" --label "$tag" \
        $PROBE_CHK --csv "$DC_CSV" | tee "$out"
}

selfcheck() {
  local good broken log rc
  good=$("$PY" "$GEN" --candidate A_series --model n18 --l 5e-7 --w 2e-6 \
              --mode dc --out "$GENDIR")
  broken="${good%.scs}_nofloating.scs"
  # the negative fixture: identical deck with the vss-to-0 source removed
  grep -v "^Vss " "$good" > "$broken"
  bash "$PROJ/scripts/tb_preflight.sh" "$good" 1.8 sc_good > "$LOGDIR/sc_good.txt" 2>&1
  local rg=$?
  bash "$PROJ/scripts/tb_preflight.sh" "$broken" 1.8 sc_bad > "$LOGDIR/sc_bad.txt" 2>&1
  local rb=$?
  echo "-- flat good deck rc=$rg :"; grep -E "STATIC_NOTE|STATIC_OK|TESTBENCH_PREFLIGHT" "$LOGDIR/sc_good.txt" | head -4
  echo "-- floating-vss deck rc=$rb :"; grep -E "STATIC_FAIL|OP_FAIL|TESTBENCH_PREFLIGHT" "$LOGDIR/sc_bad.txt" | head -3
  if [ "$rg" = "0" ] && [ "$rb" != "0" ]; then
    echo "PREFLIGHT_FLAT_SELFCHECK: PASS"; return 0
  fi
  echo "PREFLIGHT_FLAT_SELFCHECK: FAIL (good=$rg broken=$rb)"
  return 1
}

tran_one() {   # candidate model l w period vout corner slew
  local cand="$1" model="$2" L="$3" W="$4" period="$5" vout="$6" corner="${7:-tt}" slew="${8:-1e-9}"
  local tag deck psf
  tag=$(tag_of "$cand" "$model" "$corner" "$L" "$W" "T${period}vout${vout}")
  [ "$PROBE" = "iprobe" ] && tag="${tag}_iprobe"
  [ -n "${TAGX:-}" ] && tag="${tag}_${TAGX}"
  deck=$("$PY" "$GEN" --candidate "$cand" --model "$model" --l "$L" --w "$W" \
             --corner "$corner" --mode tran --period "$period" --vout "$vout" \
             --slew "$slew" $PROBE_GEN ${EXTRA:-} ${TAGX:+--suffix "$TAGX"} --out "$GENDIR" | tail -1)
  [ -f "$deck" ] || { echo "GEN_FAILED $deck"; return 9; }
  run_deck "$deck" "$tag" 1.8 tran | tee "$LOGDIR/${tag}.pipeline"
  psf=$(grep -aE "^/" "$LOGDIR/${tag}.pipeline" | tail -1)
  if [ -z "$psf" ] || [ ! -f "$psf" ]; then echo "TRAN_FAIL $tag"; return 8; fi
  [ "${DDRV_CSV_RESET:-0}" = "1" ] && rm -f "$TR_CSV"
  "$PY" "$PROJ/scripts/ddrv_tran.py" "$psf" --rsen "$RSEN" --target "$TARGET" \
        $PROBE_CHK ${GATE_NET:+--gate-net "$GATE_NET"} ${ENSIG:+--ensig "$ENSIG"} \
        --label "$tag" --csv "$TR_CSV" | tee "$EVDIR/ddrv_${tag}.txt"
}

case "${1:-}" in
  dc) shift; dc_one "$@";;
  tran) shift; tran_one "$@";;
  sweep)
    shift
    cand="$1" model="$2" corner="$3" vmax="$4" step="$5"; Ls="$6"; Ws="$7"
    for L in $Ls; do for W in $Ws; do dc_one "$cand" "$model" "$L" "$W" "$corner" "$vmax" "$step"; done; done;;
  selfcheck) shift; selfcheck;;
  *) sed -n '1,18p' "$0"; exit 2;;
esac
