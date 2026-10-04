#!/bin/bash
# ddrv_cbias_bracket.sh -- is the inter-channel disturbance a property of the CHANNEL or of
# the BIAS NETWORK?
#
#   bash scripts/ddrv_cbias_bracket.sh
#
# Candidate E's dynamic crosstalk was measured with the 15 uA reference left ideal (that is
# the scope this round was given). An ideal current source into a diode-connected device has
# a dynamic impedance of about 1/gm and no hold capacitance, while a real bias generator has
# both -- so the measured coupling is an upper bound on what the channel itself produces.
# This script runs the same two-channel toggling test with Cbias = none / 1 pF / 10 pF on
# VBIAS_SHARED to attribute the effect.
#
# Cbias is a TESTBENCH BRACKETING ELEMENT. It is not part of Candidate E, not claimed as a
# design, and not carried into any verdict line.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
GX="--mpass-model n33 --mbleed-model n33 --lpass 2e-6 --lbleed 2e-6 --wpass 5e-6 --wbleed 2e-6"
VOUT="${VOUT:-1.20}"
T="${T:-9.765625e-6}"
cd "$PROJ" || exit 9
RES="$PROJ/results/data_driver_xtalk_cbias_bracket.csv"
CB_LIST="${CB_LIST:-none 1p 10p}"
: > "$RES"

for cb in $CB_LIST; do
  CBFLAG=""
  [ "$cb" != none ] && CBFLAG="--cbias $cb"
  echo "=== Cbias = $cb   (VBIAS_SHARED hold capacitance standing in for a bias buffer)"
  PROBE=iprobe TAGX="cb${cb}_stat" EXTRA="--channels 2 --toggle none --en 1 --en1 1 --vout1 $VOUT $GX $CBFLAG" \
    bash scripts/ddrv_run.sh tran E_local_gate n33 2e-6 2e-5 "$T" "$VOUT" tt 1e-8 \
      > "logs/cb${cb}_stat.pipeline" 2>&1
  base=$(grep -aE "^/" "logs/cb${cb}_stat.pipeline" | tail -1)
  [ -f "${base:-/nonexistent}" ] || { echo "  baseline NO DATA"; sed -n '1,4p' "logs/cb${cb}_stat.pipeline"; }
  for sl in 1e-10 1e-8; do
    PROBE=iprobe TAGX="cb${cb}_dyn${sl}" EXTRA="--channels 2 --toggle 0 --en 1 --en1 1 --vout1 $VOUT $GX $CBFLAG" \
      bash scripts/ddrv_run.sh tran E_local_gate n33 2e-6 2e-5 "$T" "$VOUT" tt "$sl" \
        > "logs/cb${cb}_dyn${sl}.pipeline" 2>&1
    p=$(grep -aE "^/" "logs/cb${cb}_dyn${sl}.pipeline" | tail -1)
    if [ ! -f "${p:-/nonexistent}" ]; then
      echo "  slew=$sl NO DATA"; sed -n '1,4p' "logs/cb${cb}_dyn${sl}.pipeline"; continue
    fi
    echo "  -- neighbour slews at $sl, victim CH1 held on:"
    python scripts/ddrv_xtalk.py "$p" --ch 1 --ref "$base" --skip-frac 0.2 \
           --label "cbias_${cb}_slew$sl" --slew-desc "$sl s, Cbias=$cb" \
           --csv "$RES" 2>&1 | grep -aE "I_BASELINE|PEAK_CROSSTALK|CHARGE_ERROR|GLITCH|Q_error|TWO_CHANNEL|IOUT_SOURCE" \
           | sed 's/^/     /'
    python scripts/ddrv_tran.py "$p" --label "cbias_${cb}_slew${sl}_ch0" 2>&1 \
        | grep -aE "VBIAS_SHARED|TURN_ON" | sed 's/^/     /'
  done
done
echo "results: $RES"
