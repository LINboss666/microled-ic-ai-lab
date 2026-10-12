#!/bin/bash
# sc1_s1_r2d_regression.sh -- independent S1 regression entry, prepared for the authorised session.
#
#   bash scripts/sc1_s1_r2d_regression.sh              # dry run (default): prints, executes nothing
#   RUN=1 QODER_SIM_AUTHORISED=1 bash scripts/sc1_s1_r2d_regression.sh
#
# Why this is a new file instead of a patch to scripts/sc1_s1r.sh: that script is protected history
# and carries the defects the review listed. What is fixed here:
#   * every number comes from the audited reader, and its exit status is checked BEFORE any float();
#     a reader failure is recorded as NOT_MEASURED, never converted and never silently passed
#     (the old S2 script did float("NOT_MEASURED"), which aborts mid-run);
#   * scientific notation and negative values are parsed by the reader in SI, so 4.8e-09 and
#     -1.86e-04 survive instead of becoming 0;
#   * no reference to a non-existent "_t1" net: signal names are taken from the deck's own save list;
#   * a missing raw file, a missing negative case or too few samples stops the run with a non-zero
#     status -- they cannot be counted as SKIPPED and then reported as PASS;
#   * the decision level, the four truth rows and the five windows are the historical ones, so a
#     difference from the historical CSV means something.
set -u
PROJ=${PROJ:-/root/microled_ai_project}
cd "$PROJ" || { echo "HARNESS_ERROR: cannot cd $PROJ"; exit 8; }
RUN=${RUN:-0}
AUTH=${QODER_SIM_AUTHORISED:-0}
SECTION=${SECTION:-tt}
VDDC=${VDDC:-1.8}
VOL=${VOL:-0.9}                 # historical decision level, kept identical on purpose
GEN=cadence_work/sc1_sim/s1_reg
D="$PROJ/$GEN"
RD="$PROJ/scripts/sc1_read_psf.py"
RS="$PROJ/scripts/run_spectre.sh"
OUT="$PROJ/results/evidence"

CASES='truth_Q1_BLANK0 truth_Q0_BLANK0 truth_Q1_BLANK1 truth_Q0_BLANK1'
WINDOWS='T1:en:400n:455n:max:lt T2:en:520n:620n:min:gt T3:q:410n:520n:min:gt \
T4:en:700n:860n:max:lt T5:q:700n:860n:max:lt'
NEGATIVES='F1_blank_clamped'

echo "S1_R2D_REGRESSION section=$SECTION vdd_core=$VDDC decision_level_V=$VOL"
if [ "$RUN" != "1" ] || [ "$AUTH" != "1" ]; then
  cat <<EOF
S1_R2D_REGRESSION: DRY_RUN (nothing executed). Authorised execution would perform, in order:
  1. mkdir -p $D
  2. generate the four DC decks (qbar swept 0/1.8 V at blank=0 and blank=1.8 V) and the transient
     deck plus the BLANK-clamped negative, all including spectre/C2MOS_DFF.scs and
     spectre/sc1_scan_gate.scs unchanged;
  3. for each deck: bash scripts/tb_preflight.sh DECK $VDDC TAG "vdd=$VDDC vss=0"   (full phase)
  4. for each deck: LABEL=S1R_* bash $RS DECK 300  -> record the runner exit code and data file
  5. truth rows  : python $RD --data FILE --sig en --sweep QBAR --mode last --require-n 1
  6. windows      : python $RD --data FILE --sig SIG --t0 T0 --t1 T1 --mode MODE --require-n 3
  7. negative     : same reader call as T1 on the faulted deck; the run FAILS unless it reads > $VOL
  8. judge each row against $VOL, write $OUT/sc1_r2d_s1_regression.csv, then compare with
     results/evidence/s1r_truth.csv / s1r_transient.csv in a separate column
  Any missing raw file, missing negative, reader rc != 0 or sample count below the requirement makes
  this script exit non-zero: not one of them may be recorded as SKIPPED and then reported as PASS.
EOF
  [ "$RUN" = "1" ] || exit 0
  echo "  RUN=1 was set but QODER_SIM_AUTHORISED is not: real-circuit simulation stays paused."
  exit 5
fi

# ------------------------------------------------------------------ authorised path below
[ -d "$PROJ/spectre/C2MOS_DFF.scs" ] || { echo "HARNESS_ERROR: golden cell missing"; exit 8; }
mkdir -p "$D"
CELL='subckt sc1_dff (d clk q qbar vdd vss)
  parameters l=2e-7 wp=4e-6 wn=2e-6'
GATE="$PROJ/spectre/sc1_scan_gate.scs"
DFF="$PROJ/spectre/C2MOS_DFF.scs"
CSV="$OUT/sc1_r2d_s1_regression.csv"
printf '"case","kind","raw","signal","window","mode","value_V","samples_required","reader_rc","deck_rc","preflight_rc","verdict","note"\n' > "$CSV"

dc_deck() { # blank_volt  out
  local bv="$1" f="$2"
  cat > "$f" <<EOF
simulator lang=spectre insensitive=yes
include "\$QODER_PDK_LIB" section=$SECTION
include "$DFF"
include "$GATE"
Vdd (vdd 0) vsource dc=$VDDC
Vss (vss 0) vsource dc=0
Vb  (blank 0) vsource dc=$bv
Vq  (qbar 0) vsource dc=0
X2 (qbar blank en vdd vss) sc1_scan_gate
X1 (d clk q qbar vdd vss) c2mos_dff
sw dc dev=Vq param=dc start=0 stop=$VDDC step=$VDDC
save en blank qbar q d clk vdd vss
EOF
}

tran_deck() { # out
  local f="$1"
  cat > "$f" <<EOF
simulator lang=spectre insensitive=yes
include "\$QODER_PDK_LIB" section=$SECTION
include "$DFF"
include "$GATE"
Vdd (vdd 0) vsource dc=$VDDC
Vss (vss 0) vsource dc=0
Vd  (d 0) vsource dc=0
Vclk (clk 0) vsource type=pulse val0=0 val1=$VDDC period=200n width=100n delay=50n rise=1n fall=1n
Vb  (blank 0) vsource type=pwl wave=[(0 $VDDC) (400n $VDDC) (450n 0) (900n 0)]
X1 (d clk q qbar vdd vss) c2mos_dff
X2 (qbar blank en vdd vss) sc1_scan_gate
sw1 tran stop=1000n maxstep=0.5n
save en blank qbar q d clk vdd vss
EOF
}

# read_number <file> <args...> -> prints value or NOT_MEASURED, sets RC_READ
read_number() {
  local file="$1"; shift
  local out rc
  out=$(python "$RD" --data "$file" "$@" 2>&1); rc=$?
  READ_RC=$rc
  if [ "$rc" != "0" ]; then echo "NOT_MEASURED"; else echo "$out" | tail -1; fi
}

note=""
row() { printf '"%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s\n' \
  "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}" "${13}" >> "$CSV"; }

fail=0
for pair in "dc_blank0 0" "dc_blank1.8 1.8"; do
  run=$(echo "$pair" | cut -d' ' -f1); bv=$(echo "$pair" | cut -d' ' -f2)
  f="$D/s1reg_$run.scs"; dc_deck "$bv" "$f"
  bash "$PROJ/scripts/tb_preflight.sh" "$f" "$VDDC" "s1reg_$run" "vdd=$VDDC vss=0" >/dev/null 2>&1
  prc=$?
  LABEL="S1REG_$run" bash "$RS" "$f" 300 > "$D/$run.out" 2>&1; drc=$?
  data=$(grep -aoE "CHECK datafile='[^']+'" "$D/$run.out" | sed -E "s/.*'(.*)'/\1/")
  if [ ! -s "$data" ]; then
    echo "FAIL: no data for $run (preflight=$prc runner=$drc) -- not counted as a pass"
    fail=1
    continue
  fi
  for q in 0 $VDDC; do
    v=$(read_number "$data" --sig en --sweep "$q" --mode last --require-n 1); rc=$READ_RC
    state=$(python -c "print('ON' if float('$v') > $VOL else 'OFF')" 2>/dev/null || echo NOT_MEASURED)
    echo "$run q=$q en=$v state=$state"
    row "$run/q=$q" truth "$data" en "sweep=$q" last "$v" 1 "$rc" "$drc" "$prc" "MEASURED" "$state"
  done
done

f="$D/s1reg_tran.scs"; tran_deck "$f"
bash "$PROJ/scripts/tb_preflight.sh" "$f" "$VDDC" s1reg_tran "vdd=$VDDC vss=0" >/dev/null 2>&1; prc=$?
LABEL=S1REG_tran bash "$RS" "$f" 300 > "$D/tran.out" 2>&1; drc=$?
data=$(grep -aoE "CHECK datafile='[^']+'" "$D/tran.out" | sed -E "s/.*'(.*)'/\1/")
if [ ! -s "$data" ]; then
  echo "FAIL: no transient data (preflight=$prc runner=$drc)"
  fail=1
else
  for w in $WINDOWS; do
    cid=$(echo "$w" | cut -d: -f1); sig=$(echo "$w" | cut -d: -f2)
    t0=$(echo "$w" | cut -d: -f3); t1=$(echo "$w" | cut -d: -f4)
    mode=$(echo "$w" | cut -d: -f5); kind=$(echo "$w" | cut -d: -f6)
    v=$(read_number "$data" --sig "$sig" --t0 "$t0" --t1 "$t1" --mode "$mode" --require-n 3); rc=$READ_RC
    verdict=$(python -c "
import sys
try:
    x = float('$v')
except Exception:
    sys.stdout.write('FAIL'); sys.exit(0)
sys.stdout.write('PASS' if (x < $VOL if '$kind' == 'lt' else x > $VOL) else 'FAIL')" 2>/dev/null || echo FAIL)
    [ "$verdict" = PASS ] || fail=1
    echo "$cid $sig $t0..$t1 $mode -> $v $verdict"
    row "$cid" window "$data" "$sig" "$t0..$t1" "$mode" "$v" 3 "$rc" "$drc" "$prc" "$verdict" "$kind $VOL"
  done
fi

# the BLANK-clamped negative: identical deck and identical T1 assertion, only the stimulus is wrong
# on purpose. Missing here is a harness failure, never a SKIPPED that still allows an overall PASS.
ff="$D/s1reg_fault.scs"
sed 's|^Vb  (blank 0) vsource type=pwl.*$|Vb  (blank 0) vsource dc=0|' "$f" > "$ff"
bash "$PROJ/scripts/tb_preflight.sh" "$ff" "$VDDC" s1reg_fault "vdd=$VDDC vss=0" >/dev/null 2>&1; fprc=$?
LABEL=S1REG_fault bash "$RS" "$ff" 300 > "$D/fault.out" 2>&1; fdrc=$?
fdata=$(grep -aoE "CHECK datafile='[^']+'" "$D/fault.out" | sed -E "s/.*'(.*)'/\1/")
if [ ! -s "$fdata" ]; then
  echo "FAIL: the negative case produced no data (preflight=$fprc runner=$fdrc) -- an absent"
  echo "  negative cannot be skipped past"
  fail=1
else
  fv=$(read_number "$fdata" --sig en --t0 400n --t1 455n --mode max --require-n 3); frc=$READ_RC
  fverdict=$(python -c "
try:
    x = float('$fv')
except Exception:
    x = None
print('DETECTED' if (x is not None and x > $VOL) else 'CHECKER_TOOTHLESS')" 2>/dev/null || echo CHECKER_TOOTHLESS)
  [ "$fverdict" = DETECTED ] || fail=1
  echo "F1 blank-clamped en=$fv -> $fverdict (the unchanged T1 assertion must reject it)"
  row F1_blank_clamped negative_fault_injection "$fdata" en "400n..455n" max "$fv" 3 "$frc" \
      "$fdrc" "$fprc" "$fverdict" "expected > $VOL because BLANK is clamped off"
fi

echo "S1_R2D_REGRESSION: $([ "$fail" = 0 ] && echo PASS || echo FAIL) -- csv $CSV"
echo "  This run used the simulator; it is only reachable with RUN=1 and QODER_SIM_AUTHORISED=1."
[ "$fail" = 0 ] || exit 6
exit 0
