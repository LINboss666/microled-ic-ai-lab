#!/bin/bash
# ddrv_corner_probe.sh -- BASIC_PROCESS_CORNER_PROBE for the FROZEN Candidate E cell.
#
#   bash scripts/ddrv_corner_probe.sh
#   CORNERS="tt" bash scripts/ddrv_corner_probe.sh
#
# Scope, stated in the script so it cannot drift: this probes one frozen cell at three
# process sections. It is NOT a PVT sign-off: there is no temperature sweep, no supply
# sweep, no mismatch and no Monte Carlo, so FULL_PVT_PASS is a forbidden wording for anything
# produced here (review item 5).
#
# Corner names are taken from the model library's own `section` statements, not guessed:
#   pdk/.../ms018_enhanced_v1p2_rev0_spe.lib :  tt  ff  ss  fnsp  snfp  mos_mc
# (fnsp/snfp are NMOS-only / PMOS-only flavour sections and are deliberately not used here:
# this cell has no PMOS, so a "slow-N fast-P" corner describes nothing about it.)
#
# Nothing is re-tuned per corner: W/L, topology and the gate pair come from $FROZEN and the
# generator's defaults. Transients run at the system time scale only (T = 9.765625 us) with
# method=gear2only, because traponly's step-locked sample alternation is exactly the thing
# DATA-3.5 separated out and it must not leak back into the frozen numbers.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
cd "$PROJ" || exit 9

FROZEN="--mpass-model n33 --mbleed-model n33 --lpass 2e-6 --lbleed 2e-6 --wpass 5e-6 --wbleed 2e-6"
CORNERS="${CORNERS:-tt ss ff}"
VOUT_REP="${VOUT_REP:-1.20}"
VMAX="${VMAX:-3.3}"
STEP="${STEP:-0.02}"
FRAME=9.765625e-6
METHOD="${METHOD:-gear2only}"
DC_CSV="$PROJ/results/data_driver_E_corner_dc.csv"
TR_CSV="$PROJ/results/data_driver_E_corner_transient.csv"
XT_CSV="$PROJ/results/data_driver_E_corner_xtalk.csv"
EVD="$PROJ/results/evidence"
LOGS="$PROJ/logs"
mkdir -p "$EVD"
rm -f "$DC_CSV" "$TR_CSV" "$XT_CSV"

echo "### frozen cell under probe:"
python scripts/ddrv_gen.py --candidate E_local_gate --model n33 --l 2e-6 --w 2e-5 \
      --corner tt --vmax "$VMAX" --step "$STEP" --mode dc --probe iprobe --en 1 \
      $FROZEN --suffix frozen_echo --out "$LOGS" >/dev/null 2>&1
grep -aE "^M(out|cas|ref|pass_local|bleed_local)|^tran1|^method" "$LOGS"/*frozen_echo*.scs 2>/dev/null | head -8

for c in $CORNERS; do
  echo
  echo "================ CORNER $c"
  for st in on off; do
    e=1; [ "$st" = off ] && e=0
    echo "--- DC $st (0 -> ${VMAX} V, step ${STEP}, iprobe)"
    PROBE=iprobe DC_CSV="$DC_CSV" TAGX="${c}_${st}" \
      EXTRA="--en $e $FROZEN" \
      bash scripts/ddrv_run.sh dc E_local_gate n33 2e-6 2e-5 "$c" "$VMAX" "$STEP" \
        > "$LOGS/corner_${c}_${st}.pipeline" 2>&1
    p=$(grep -aE "^/" "$LOGS/corner_${c}_${st}.pipeline" | tail -1)
    if [ ! -f "${p:-/nonexistent}" ]; then
      echo "    NO DATA"; sed -n '1,4p' "$LOGS/corner_${c}_${st}.pipeline"; continue
    fi
    python scripts/ddrv_characterize.py "$p" --require-probe --nominal "$VOUT_REP" \
           --label "E_${c}_${st}" --csv "$DC_CSV" > "$EVD/corner_${c}_${st}.txt" 2>&1
    grep -aE "IOUT@max|COMPLIANCE_1PCT|COMPLIANCE_2PCT|COMPLIANCE_5PCT|NOMINAL|IOUT_SPAN whole|vbias_ch|PROBE_BURDEN|DATA_DRIVER_DC" \
      "$EVD/corner_${c}_${st}.txt" | sed 's/^/    /'
  done

  echo "--- TRAN static baseline (EN0=EN1=1 held) + toggling neighbour, T=$FRAME, $METHOD"
  PROBE=iprobe TR_CSV="$LOGS/corner_${c}_base.csv" TAGX="${c}_base" \
    EXTRA="--channels 2 --toggle none --en 1 --en1 1 --vout1 $VOUT_REP --method $METHOD $FROZEN" \
    bash scripts/ddrv_run.sh tran E_local_gate n33 2e-6 2e-5 "$FRAME" "$VOUT_REP" "$c" 1e-8 \
      > "$LOGS/corner_${c}_base.pipeline" 2>&1
  base=$(grep -aE "^/" "$LOGS/corner_${c}_base.pipeline" | tail -1)
  PROBE=iprobe TR_CSV="$TR_CSV" TAGX="${c}_dyn" \
    EXTRA="--channels 2 --toggle 0 --en 1 --en1 1 --vout1 $VOUT_REP --method $METHOD $FROZEN" \
    bash scripts/ddrv_run.sh tran E_local_gate n33 2e-6 2e-5 "$FRAME" "$VOUT_REP" "$c" 1e-8 \
      > "$LOGS/corner_${c}_dyn.pipeline" 2>&1
  p=$(grep -aE "^/" "$LOGS/corner_${c}_dyn.pipeline" | tail -1)
  if [ ! -f "${p:-/nonexistent}" ]; then
    echo "    NO DATA"; sed -n '1,4p' "$LOGS/corner_${c}_dyn.pipeline"; continue
  fi
  # attribution, not assumption. The corner is printed out of the deck that produced this
  # data file: an earlier version of this script passed the corner in the wrong positional
  # slot, so every "corner" silently re-ran section=tt and all three blocks came back
  # bit-identical -- a mis-wired probe that still produces numbers is the thing a reviewer
  # cannot otherwise catch.
  stem=$(basename "$(dirname "$p")" .raw)
  echo "    deck: $stem"
  grep -aE '^include' "$(dirname "$(dirname "$p")")/$stem.scs" | sed 's/^/      /'
  sed -n '1,120p' "$p" | grep -aE '^"(method|maxstep|reltol)"' | tr '\n' ' '
  echo "    (header above)"
  REFOPT=""; [ -f "${base:-/nonexistent}" ] && REFOPT="--ref $base"
  python scripts/ddrv_xtalk.py "$p" --ch 1 $REFOPT --skip-frac 0.2 --require-probe \
         --label "E_${c}_victim" --slew-desc "10 ns edge, method=$METHOD, maxstep=5 ns, FRAME_SCALE" \
         --csv "$XT_CSV" > "$EVD/corner_${c}_victim.txt" 2>&1
  grep -aE "I_BASELINE|PEAK_CROSSTALK|CHARGE_ERROR|GLITCH_|VBIAS_SHARED|vbias_ch1|RINGING" \
    "$EVD/corner_${c}_victim.txt" | sed 's/^/    /'
  python scripts/ddrv_tran.py "$p" --require-probe --label "E_${c}_ch0" \
         --csv "$LOGS/corner_${c}_ch0.csv" > "$EVD/corner_${c}_ch0.txt" 2>&1
  grep -aE "TURN_ON_SETTLING|TURN_OFF|ON_SETTLED|ON_RIPPLE|RINGING|OFF_LEAKAGE|VBIAS_SHARED|DATA_DRIVER_TRAN" \
    "$EVD/corner_${c}_ch0.txt" | sed 's/^/    /'
done

echo
echo "results: $DC_CSV"
echo "         $TR_CSV"
echo "         $XT_CSV"
echo "CORNER_PROBE_RUNS_DONE corners=$CORNERS method=$METHOD"
