#!/bin/bash
# ddrv_verify.sh -- the aggregate numeric verdict for the one-channel data driver.
#
#   ddrv_verify.sh [model] [l] [w] [vcas]
#
# It re-runs, on the machine doing the checking, the four things the round claims:
#   1. ON  : IOUT(VOUT) sweep, +/-% compliance extraction and the error at the top point
#   2. OFF : the same deck with DATA_EN = 0, leakage reported (the course defines no
#            leakage number, so none is invented here)
#   3. repeat: the ON sweep again, compared line-for-line with run 1
#   4. transient at the system-scale period, VOUT taken from the DC curve
#
# Every threshold that is not 15 uA is a POC_ASSUMPTION characterisation criterion,
# declared here so a reviewer can disagree with the number instead of guessing it.
# "spectre completes with 0 errors" is NOT a verdict: run_spectre's own log budget is
# enforced inside ddrv_run.sh, and a FAIL here is reported as a FAIL.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
MODEL="${1:-n33}"
L="${2:-2e-6}"
W="${3:-2e-5}"
VCAS="${4:-1.8}"
VMAX=3.3            # 3.3 V family ceiling for n33 (POC_ASSUMPTION: not a course number)
STEP=0.05
ERR_ON_MAX=1.0      # % |error| allowed at the top of the sweep        POC_ASSUMPTION
JUMP_MAX=0.01       # max adjacent step as a fraction of target        POC_ASSUMPTION
PERIOD=9.765625e-6  # 1/(1024 x 100 Hz) column period, ENGINEERING_DERIVATION
VOUT_TR=1.2         # inside the +/-1% band found in the DC sweep      POC_ASSUMPTION

cd "$PROJ" || exit 9
R="$PROJ/results/evidence"
fail=0
say() { echo "$@"; }

grab() { grep -aE "$1" "$2" | head -1; }

# ---- 1. ON ---------------------------------------------------------------------
out=$(DDRV_CSV_RESET=0 EXTRA="--vcas $VCAS" TAGX=vfyOn \
      bash scripts/ddrv_run.sh dc C_cascode "$MODEL" "$L" "$W" tt "$VMAX" "$STEP" 2>&1)
echo "$out" > "$R/ddrv_verify_on.txt"
top=$(grab "^== " "$R/ddrv_verify_on.txt")
say "$top"
c1=$(grab "COMPLIANCE \+/-1%" "$R/ddrv_verify_on.txt")
c2=$(grab "COMPLIANCE \+/-2%" "$R/ddrv_verify_on.txt")
c5=$(grab "COMPLIANCE \+/-5%" "$R/ddrv_verify_on.txt")
say "   $c1"; say "   $c2"; say "   $c5"
err=$(echo "$top" | sed -n 's/.*err \(-\{0,1\}[0-9.]*\) %.*/\1/p')
jump=$(grab "MAX_ADJACENT_JUMP" "$R/ddrv_verify_on.txt" | awk '{print $3}')
case "$err" in ""|*[!0-9.-]*) say "DATA_DRIVER_ON: FAIL (cannot parse the error)"; fail=1;;
  *)
    if [ "$(echo "$err ${err#-}" | awk '{print (($2 <= '"$ERR_ON_MAX"') ? 1 : 0)}')" = "1" ]; then
      say "DATA_DRIVER_ON: PASS (|err| $err % at VOUT_top <= $ERR_ON_MAX %)"
    else
      say "DATA_DRIVER_ON: FAIL (|err| $err % exceeds $ERR_ON_MAX %)"; fail=1
    fi;;
esac
jm=$(echo "$jump" | awk '{print (($1 < '"$JUMP_MAX"') ? 1 : 0)}')
if [ "$jm" = "1" ]; then
  say "DATA_DRIVER_MONOTONIC: PASS (largest adjacent step $jump of target, < $JUMP_MAX)"
else
  say "DATA_DRIVER_MONOTONIC: FAIL (largest adjacent step $jump of target)"; fail=1
fi

# ---- 2. OFF --------------------------------------------------------------------
out=$(DDRV_CSV_RESET=0 EXTRA="--vcas $VCAS --en 0" TAGX=vfyOff \
      bash scripts/ddrv_run.sh dc C_cascode "$MODEL" "$L" "$W" tt "$VMAX" "$STEP" 2>&1)
echo "$out" > "$R/ddrv_verify_off.txt"
off=$(grab "^== " "$R/ddrv_verify_off.txt" | sed -n 's/.*IOUT@max=\([0-9.eE+-]*\) uA.*/\1/p')
say "DATA_DRIVER_OFF: |IOUT| at the top of the OFF sweep = $off uA"
say "  (no OFF leakage spec exists in the course material, so this is a reported number,"
say "   not a pass/fail criterion: REPORTED, NOT_SPECIFIED)"

# ---- 3. repeat -----------------------------------------------------------------
out=$(DDRV_CSV_RESET=0 EXTRA="--vcas $VCAS" TAGX=vfyRep \
      bash scripts/ddrv_run.sh dc C_cascode "$MODEL" "$L" "$W" tt "$VMAX" "$STEP" 2>&1)
echo "$out" > "$R/ddrv_verify_repeat.txt"
if diff <(grep -aE "^== |COMPLIANCE|ROUT|MAX_ADJ" "$R/ddrv_verify_on.txt" | sed 's/vfyOn/VREPEAT/g') \
        <(grep -aE "^== |COMPLIANCE|ROUT|MAX_ADJ" "$R/ddrv_verify_repeat.txt" | sed 's/vfyRep/VREPEAT/g') >/dev/null; then
  say "DATA_DRIVER_REPEATABLE: PASS (two independent runs parse identically)"
else
  say "DATA_DRIVER_REPEATABLE: FAIL"; diff "$R/ddrv_verify_on.txt" "$R/ddrv_verify_repeat.txt" | head -6
  fail=1
fi

# ---- 4. transient --------------------------------------------------------------
out=$(DDRV_CSV_RESET=0 EXTRA="--vcas $VCAS" TAGX=vfyTran \
      bash scripts/ddrv_run.sh tran C_cascode "$MODEL" "$L" "$W" "$PERIOD" "$VOUT_TR" tt 1e-9 2>&1)
echo "$out" > "$R/ddrv_verify_tran.txt"
grep -aE "TURN_ON_SETTLING|TURN_OFF|PEAK|OFF_LEAKAGE|DATA_DRIVER_TRAN" "$R/ddrv_verify_tran.txt"
if ! grep -aq "DATA_DRIVER_TRAN: OK" "$R/ddrv_verify_tran.txt"; then fail=1; fi

echo
if [ "$fail" = "0" ]; then
  echo "DATA_DRIVER_1CH: PASS"
else
  echo "DATA_DRIVER_1CH: FAIL"
fi
exit "$fail"
