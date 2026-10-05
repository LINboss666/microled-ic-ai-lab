#!/bin/bash
# ddrv_hold_compare.sh -- re-analyse the SAME frame-scale transient runs for the three
# Mpass body implementations (frozen vbias_ch / bodyfix vss / DNW vbias_ch) against the
# criterion the POC actually uses: does the always-on victim channel hold inside +/-5 % of
# its own static baseline, not merely avoid a big peak.
#
#   bash scripts/ddrv_hold_compare.sh
#   CORNERS="tt ss" bash scripts/ddrv_hold_compare.sh
#
# Analysis only: nothing here re-simulates. Every input is a run that already exists, so
# the comparison cannot quietly change the evidence it is judging. Missing variants are
# reported as skipped rather than guessed.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
cd "$PROJ" || exit 9
CORNERS="${CORNERS:-tt ss ff}"
CSV="$PROJ/results/data_driver_E_mpass_body_hold_compare.csv"
rm -f "$CSV"

for c in $CORNERS; do
  for pair in "frozen:" "bodyfix:_bulkvss" "dnw:_dnwpass"; do
    name="${pair%%:*}"
    mid="${pair#*:}"
    dyn=$(ls -1d spectre/generated/sim/*"_l2e6w2e5_ch2_iprobe_mgear2only${mid}_${c}_dyn_"*/tran1.tran.tran 2>/dev/null | head -1)
    base=$(ls -1d spectre/generated/sim/*"_l2e6w2e5_ch2_iprobe_mgear2only${mid}_${c}_base_"*/tran1.tran.tran 2>/dev/null | head -1)
    if [ ! -f "${dyn:-/nonexistent}" ]; then
      echo "SKIP $c $name (no $c transient run)"
      continue
    fi
    REFOPT=""
    [ -f "${base:-/nonexistent}" ] && REFOPT="--ref $base"
    echo "### $c $name"
    python scripts/ddrv_xtalk.py "$dyn" --ch 1 $REFOPT --skip-frac 0.2 --require-probe \
           --label "E_${c}_${name}_victim" \
           --slew-desc "10 ns edge, gear2only, maxstep=5 ns, FRAME_SCALE" \
           --csv "$CSV" 2>&1 |
      grep -aE "I_BASELINE|PEAK_CROSSTALK|CHARGE_ERROR|GLITCH_DURATION|VICTIM_HOLD|vbias_ch1|RINGING"
  done
done

echo "results: $CSV"
echo "HOLD_COMPARE_DONE corners=$CORNERS"
