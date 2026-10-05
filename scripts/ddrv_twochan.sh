#!/bin/bash
# ddrv_twochan.sh -- the two-channel independence test, for whichever candidate is under
# review (Candidate D used it and failed; Candidate E is judged by the same numbers).
#
#   CAND=E_local_gate GATEX="--mpass-model n18 --mbleed-model n18" bash scripts/ddrv_twochan.sh
#   CAND=D_local VOUT=1.2 bash scripts/ddrv_twochan.sh          # the legacy re-run
#
# Three questions, measured separately, because conflating them is how a coupling study
# produces a wrong verdict:
#
#   STATIC   four DC operating points (EN0,EN1) = (0,0) (0,1) (1,0) (1,1), both outputs
#            held at the same voltage. Crosstalk is a DIFFERENCE between two of them --
#            never the absolute error of a channel that is supposed to be off:
#                dI1 = | I1(EN0=1) - I1(EN0=0) |   with EN1 held on
#                dI0 = | I0(EN1=1) - I0(EN1=0) |   with EN0 held on
#   DYNAMIC  CH1 held on while CH0's enable pulses, at every slew in SLEWS, judged both as
#            a peak and as charge (scripts/ddrv_xtalk.py):
#                PEAK_CROSSTALK_ERROR, Q_error, CHARGE_ERROR_PERCENT, GLITCH_DURATION
#            The static (1,1) run is passed to the analyser as the baseline, so Q_error is
#            the neighbour's effect and not the channel's own regulation error.
#   SPEED    the same toggling run reported for the switching channel (turn-on/turn-off).
#
# POC cross-channel criterion: 1 % of 15 uA, on peak AND on charge (POC_ASSUMPTION -- a
# comparison number defined by these rounds to compare gating structures, not a course
# requirement). The accepted single-channel checkers are reused untouched, so this cannot
# move a goalpost to make the rework pass. NO SLEW IS SKIPPED: the review asked for 1, 10
# and 100 ns, and choosing the quietest one would be exactly the failure mode under review.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
CAND="${CAND:-D_local}"
MODEL="${MODEL:-n33}"
L="${L:-2e-6}"
W="${W:-2e-5}"
VOUT="${VOUT:-1.2}"            # both channels held at the same output voltage
SLEWS="${SLEWS:-1e-10 1e-8 1e-7}"
PERIODS="${PERIODS:-2e-7 9.765625e-6}"
GATEX="${GATEX:-}"             # candidate E's pass/bleed sizing, verbatim generator flags
PROBE="${PROBE:-iprobe}"       # the burdened method is not accepted for a new verdict
LIMIT_PCT=1.0
cd "$PROJ" || exit 9
# RES/EVD default to the names DATA-3 was reviewed under; a variant under test (the DNW
# pass device) points them elsewhere so re-running cannot rewrite evidence that is already
# under review.
RES="${RES:-$PROJ/results/data_driver_xtalk_${CAND}.csv}"
EVD="${EVD:-$PROJ/results/evidence}"
LOGS="$PROJ/logs"
mkdir -p "$EVD"
# the probe method is handed to ddrv_run.sh through PROBE so the generator, the checkers
# and the CSV file names all agree on one method; nothing here needs to repeat it
: > "$RES"
verdict_static=PASS
verdict_dynamic=PASS
base11=""

run_deck() {   # $1 tag, $2 extra generator flags, $3 period, $4 slew -> echoes psf path
  local tag="$1" ex="$2" T="$3" sl="$4"
  PROBE="$PROBE" DDRV_CSV_RESET=0 EXTRA="--channels 2 $ex --vout1 $VOUT" TAGX="$tag" \
    bash scripts/ddrv_run.sh tran "$CAND" "$MODEL" "$L" "$W" "$T" "$VOUT" tt "$sl" \
      > "$LOGS/$tag.pipeline" 2>&1
  grep -aE "^/" "$LOGS/$tag.pipeline" | tail -1
}

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

echo "=== STATIC: 2x2 enable matrix, both channels held at ${VOUT} V  [$CAND, probe=$PROBE]"
for e0 in 0 1; do for e1 in 0 1; do
  tag="${CAND}_static_e${e0}${e1}"
  p=$(run_deck "$tag" "--toggle none --en $e0 --en1 $e1 $GATEX" 2e-7 1e-9)
  if [ ! -f "${p:-/nonexistent}" ]; then
    echo "  ($e0,$e1): NO DATA -- see logs/$tag.pipeline"; verdict_static=FAIL; continue
  fi
  [ "$e0$e1" = "11" ] && base11="$p"
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
echo "=== DYNAMIC: CH1 held ON while CH0's enable pulses, every slew in [$SLEWS]"
for T in $PERIODS; do for SL in $SLEWS; do
  tag="${CAND}_dyn_T${T}_slew${SL}"
  p=$(run_deck "$tag" "--toggle 0 --en 1 --en1 1 $GATEX" "$T" "$SL")
  if [ ! -f "${p:-/nonexistent}" ]; then
    echo "  T=$T slew=$SL: NO DATA"; sed -n '1,5p' "$LOGS/$tag.pipeline"; verdict_dynamic=FAIL; continue
  fi
  out="$EVD/ddrv_${tag}.txt"
  REFOPT=""; [ -f "$base11" ] && REFOPT="--ref $base11"
  python scripts/ddrv_xtalk.py "$p" --ch "1" --label "toggling_neighbour_T${T}_slew${SL}" \
         --slew-desc "${SL} s, neighbour CH0 pulses; baseline from the static (1,1) run" \
         $REFOPT --csv "$RES" 2>&1 | sed 's/^/   /' | tee "$out"
  grep -aq "TWO_CHANNEL_INDEPENDENCE: PASS" "$out" || verdict_dynamic=FAIL
  echo "   -- same deck, channel 0 (the switching one), for context:"
  PROBE="$PROBE" python scripts/ddrv_tran.py "$p" --label "ch0_T${T}_slew${SL}" 2>&1 \
      | grep -aE "IOUT_SOURCE|TURN_ON|TURN_OFF|PEAK|VBIAS_SHARED|VBIAS_CH|GATE_PASS" | sed 's/^/     /'
done; done

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
