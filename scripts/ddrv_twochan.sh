#!/bin/bash
# ddrv_twochan.sh -- the two-channel independence test for Candidate D.
#
#   ddrv_twochan.sh
#
# Two questions, measured separately, because conflating them is how a coupling study
# produces a wrong verdict:
#
#   STATIC   four DC operating points (EN0,EN1) = (0,0) (0,1) (1,0) (1,1), both outputs
#            held at the same voltage. Crosstalk is a DIFFERENCE between two of them --
#            never the absolute error of a channel that is supposed to be off:
#                dI1 = | I1(EN0=1) - I1(EN0=0) |   with EN1 held on
#                dI0 = | I0(EN1=1) - I0(EN1=0) |   with EN0 held on
#   DYNAMIC  CH1 held on while CH0's enable pulses: worst |I1 - 15uA| over the settled
#            part of the run (scripts/ddrv_xtalk.py).
#
# POC cross-channel criterion for both: 1 % of 15 uA (POC_ASSUMPTION -- a comparison
# number defined this round to compare gating structures, not a course requirement).
# The accepted single-channel checkers are reused untouched, so this cannot move a
# goalpost to make the rework pass.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
MODEL="${MODEL:-n33}"
L="${L:-2e-6}"
W="${W:-2e-5}"
VOUT="${VOUT:-1.2}"            # both channels held at the same output voltage
LIMIT_PCT=1.0
cd "$PROJ" || exit 9
RES="$PROJ/results/data_driver_xtalk.csv"
EVD="$PROJ/results/evidence"
mkdir -p "$EVD"
: > "$RES"
verdict_static=PASS
verdict_dynamic=PASS

# the analysis prints the channel as I_0 / I_1, so an empty argument has to become "0":
# matching on "I_ mean" silently returned nothing and turned a passing channel into "no data"
mean_of() { grep -aoE "I_${1:-0} mean *: *[0-9.]+" "$2" | head -1 | awk -F: '{print $NF}' | tr -d ' '; }

# difference as a percent of 15 uA, criterion applied; empty argument means missing data
calc() {
  awk -v x="$1" -v y="$2" -v lim="$LIMIT_PCT" 'BEGIN{
    if (x == "" || y == "") { print "  MISSING DATA"; exit 2 }
    d = (x > y) ? x - y : y - x
    p = d / 15 * 100
    printf "  %.6f uA = %.3f %%  -> %s\n", d, p, (p <= lim) ? "ok" : "OVER the criterion"
    exit (p <= lim ? 0 : 1) }'
}

echo "=== STATIC: 2x2 enable matrix, both outputs held at ${VOUT} V"
for e0 in 0 1; do for e1 in 0 1; do
  tag="D2static_e${e0}${e1}"
  DDRV_CSV_RESET=0 EXTRA="--channels 2 --toggle none --en $e0 --en1 $e1 --vout1 $VOUT" \
  TAGX="s${e0}${e1}" bash scripts/ddrv_run.sh tran D_local "$MODEL" "$L" "$W" 2e-7 "$VOUT" \
      tt 1e-9 > "$PROJ/logs/$tag.pipeline" 2>&1
  p=$(grep -aE "^/" "$PROJ/logs/$tag.pipeline" | tail -1)
  if [ ! -f "${p:-/nonexistent}" ]; then
    echo "  ($e0,$e1): NO DATA -- see logs/$tag.pipeline"; verdict_static=FAIL; continue
  fi
  out="$EVD/ddrv_${tag}.txt"
  { python scripts/ddrv_xtalk.py "$p" --ch ""  --label "static_e${e0}${e1}_ch0" --csv "$RES"
    python scripts/ddrv_xtalk.py "$p" --ch "1" --label "static_e${e0}${e1}_ch1" --csv "$RES"
  } 2>&1 | sed 's/^/     /' > "$out"
  i0=$(mean_of "" "$out"); i1=$(mean_of "1" "$out")
  echo "  EN0=$e0 EN1=$e1 : I0=${i0:-?} uA  I1=${i1:-?} uA"
  eval "S${e0}${e1}_0=\$i0"; eval "S${e0}${e1}_1=\$i1"
done; done

echo
echo "  static crosstalk (criterion: <= ${LIMIT_PCT} % of 15 uA)"
echo -n "  dI1, CH1 held on, CH0 turning on/off :"
c1=$(calc "${S11_1:-}" "${S01_1:-}"); s1=$?; printf "%s\n" "$c1"
echo -n "  dI0, CH0 held on, CH1 turning on/off :"
c0=$(calc "${S11_0:-}" "${S10_0:-}"); s0=$?; printf "%s\n" "$c0"
{ [ $s1 -eq 0 ] && [ $s0 -eq 0 ]; } || verdict_static=FAIL

echo
echo "=== DYNAMIC: CH1 held ON while CH0's enable pulses"
for T in 2e-7 9.765625e-6; do
  tag="D2dyn_T${T}"
  DDRV_CSV_RESET=0 EXTRA="--channels 2 --toggle 0 --en 1 --en1 1 --vout1 $VOUT" TAGX="d${T}" \
  bash scripts/ddrv_run.sh tran D_local "$MODEL" "$L" "$W" "$T" "$VOUT" tt 1e-9 \
      > "$PROJ/logs/$tag.pipeline" 2>&1
  p=$(grep -aE "^/" "$PROJ/logs/$tag.pipeline" | tail -1)
  if [ ! -f "${p:-/nonexistent}" ]; then
    echo "  T=$T: NO DATA"; sed -n '1,5p' "$PROJ/logs/$tag.pipeline"; verdict_dynamic=FAIL; continue
  fi
  out="$EVD/ddrv_${tag}.txt"
  python scripts/ddrv_xtalk.py "$p" --ch "1" --label "toggling_neighbour_T${T}" \
         --csv "$RES" 2>&1 | sed 's/^/   /' | tee "$out"
  grep -aq "TWO_CHANNEL_INDEPENDENCE: PASS" "$out" || verdict_dynamic=FAIL
  echo "   -- same deck, channel 0 (the switching one), for context:"
  python scripts/ddrv_tran.py "$p" --label "ch0_T${T}" 2>&1 \
      | grep -aE "TURN_ON|TURN_OFF|PEAK|VBIAS_SHARED" | sed 's/^/     /'
done

echo
echo "results: $RES"
echo "STATIC_INDEPENDENCE  : $verdict_static"
echo "DYNAMIC_INDEPENDENCE : $verdict_dynamic"
if [ "$verdict_static" = PASS ] && [ "$verdict_dynamic" = PASS ]; then
  echo "TWO_CHANNEL_INDEPENDENCE: PASS"
  exit 0
fi
echo "TWO_CHANNEL_INDEPENDENCE: FAIL"
exit 1
