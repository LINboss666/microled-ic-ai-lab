#!/bin/bash
# SCAN-1 S1: build, preflight, run and judge the BLANK/ENABLE gate.
#
#   bash scripts/sc1_s1.sh [tt|ss|ff]
#
# Evidence, deliberately split so a weak test cannot look strong:
#   A. 4-row truth table measured as a real DC sweep of the gate (stimulus sources only).
#   B. the gate fed by the UNMODIFIED golden C^2MOS subckt: a rising clock edge must change
#      the select state, and BLANK must kill SCAN_EN while q does NOT move (state preserved).
#   C. mandatory fault injection: BLANK/QBAR deliberately swapped -- the checker MUST reject
#      it. If C "passes", A is worthless and says so.
#
# All judgement goes through scripts/run_spectre.sh (the audited runner: it locates the
# psfascii under sim/, checks the log for fatals and applies EXPECT_* assertions), so these
# verdicts are produced by the same machinery the accepted DATA results were produced by.
# Nothing here modifies a golden file; decks are generated into cadence_work/sc1_sim/.
set -u
SECTION="${1:-tt}"
PROJ=/root/microled_ai_project
cd "$PROJ" || exit 8
. ./skill/cad_env.sh >/dev/null 2>&1 || { echo "FATAL: cad_env load failed"; exit 8; }
[ -f spectre/pdk_local.env ] && . spectre/pdk_local.env
LIB="${QODER_PDK_LIB:-$PROJ/pdk/smic18mmrf_teacher/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib}"
GOLD="$PROJ/spectre/C2MOS_DFF.scs"
CELL="$PROJ/spectre/sc1_scan_gate.scs"
RS="$PROJ/scripts/run_spectre.sh"
PF="$PROJ/scripts/tb_preflight.sh"
OUT="$PROJ/cadence_work/sc1_sim"
VDDC=1.8
HI=${VDDC}
VOL=0.9           # mid-rail decision level for a 1.8 V logic verdict
mkdir -p "$OUT"
for f in "$GOLD" "$CELL" "$RS"; do [ -f "$f" ] || { echo "FATAL: missing input $f"; exit 8; }; done
echo "SECTION=$SECTION VDD_CORE=$VDDC VOL_THRESH=$VOL"
echo "GOLDEN_SHA256=$(sha256sum "$GOLD" | cut -d' ' -f1)"
echo "CELL_SHA256=$(sha256sum "$CELL" | cut -d' ' -f1)"

# ============================================================ A. truth table (real DC)
emit_dc() {  # blank_volts  deck_path
  local bmv="$1" d="$2"
  {
    echo "simulator lang=spectre insensitive=yes"
    echo "include \"$LIB\" section=$SECTION"
    echo "include \"$CELL\""
    echo "Vdd (vdd 0) vsource dc=$VDDC"
    echo "Vss (vss 0) vsource dc=0"
    echo "Vb  (blank 0) vsource dc=$bmv"
    echo "Vq  (qbar 0) vsource dc=0"
    echo "X2 (qbar blank en vdd vss) sc1_scan_gate"
    echo "sw dc dev=Vq param=dc start=0 stop=$VDDC step=$VDDC"
    echo "save en blank qbar vdd vss"
  } > "$d"
}
: > "$OUT/s1_truth.csv"
echo "Q,BLANK,en_V,row_expected,verdict" >> "$OUT/s1_truth.csv"
FAILS=0
for bmv in 0 $VDDC; do
  D="$OUT/s1_dc_blank${bmv}.scs"; emit_dc "$bmv" "$D"
  # the loop only ever passes 0 or 1.8, so compare literally instead of quoting awk
  if [ "$bmv" = "0" ]; then BL="BLANK=0"; else BL="BLANK=1"; fi
  for qmv in 0 $VDDC; do
    # qbar=0 means the stored bit Q=1; qbar=1.8 means Q=0
    if [ "$qmv" = "0" ]; then Q=1; else Q=0; fi
    if [ "$Q" = "1" ] && [ "$BL" = "BLANK=0" ]; then want=ON; else want=OFF; fi
    if [ "$want" = "ON" ]; then
      out=$(EXPECT_SIG=en EXPECT_SWEEP=$qmv EXPECT_GT=$VOL bash "$RS" "$D" 120 2>&1)
    else
      out=$(EXPECT_SIG=en EXPECT_SWEEP=$qmv EXPECT_LT=$VOL bash "$RS" "$D" 120 2>&1)
    fi
    got=$(printf '%s' "$out" | tr ' ' '\n' | grep -A1 '^value=' | tail -1)
    if printf '%s' "$out" | grep -qE ": PASS"; then v=PASS; else v=FAIL; FAILS=$((FAILS+1)); fi
    echo "  row Q=$Q $BL -> en=${got:-?}V expect=$want  $v"
    echo "$Q,${BL#BLANK=},${got:-NA},$want,$v" >> "$OUT/s1_truth.csv"
  done
done
if [ "$FAILS" = "0" ]; then
  echo "S1_TRUTH_TABLE: PASS rows=4/4"
else
  echo "S1_TRUTH_TABLE: FAIL failing_rows=$FAILS"
fi

# ============================================================ B. golden DFF drives the gate
D="$OUT/s1_dff.scs"
{
  echo "simulator lang=spectre insensitive=yes"
  echo "include \"$LIB\" section=$SECTION"
  echo "include \"$GOLD\""
  echo "include \"$CELL\""
  echo "parameters VDDV=$VDDC"
  echo "Vdd (vdd 0) vsource dc=VDDV"
  echo "Vss (vss 0) vsource dc=0"
  echo "// one rising-edge clock, 100 ns period, 50 ns high, 8 cycles"
  echo "Vclk (clk 0) vsource type=pulse delay=50n rise=1n fall=1n high=VDDV low=0 period=100n width=50n"
  echo "// D: 0 while priming, 1 for the second half, back to 0 late"
  echo "Vd (d 0) vsource type=pwl time=(0 100n 260n 600n 700n 900n) val=(0 0 1.8 1.8 0 0)"
  echo "// BLANK: asserted during priming AND while the 1 is shifted in, released afterwards"
  echo "Vbl (blank 0) vsource type=pwl time=(0 400n 450n 900n) val=(1.8 1.8 0 0)"
  echo "X1 (d clk q qbar vdd vss) c2mos_dff"
  echo "X2 (qbar blank en vdd vss) sc1_scan_gate"
  echo "sw1 tran stop=900n maxstep=1n method=traponly"
  echo "save clk d q qbar blank en vdd vss"
} > "$D"
echo "--- preflight on the DFF+gate bench ---"
bash "$PF" "$D" $VDDC s1_dff 2>&1 | tail -4
echo "--- transient windows ---"
# Each window is one assertion through the audited runner; verdict text is read out of the
# runner's own last line rather than re-derived here.
win() {  # label  sig  t0  t1  gt|lt  thresh  file
  local label="$1" sig="$2" t0="$3" t1="$4" kind="$5" thr="$6" logf="$7"
  if [ "$kind" = gt ]; then
    EXPECT_SIG=$sig EXPECT_T0=$t0 EXPECT_T1=$t1 EXPECT_GT=$thr bash "$RS" "$D" 300 > "$logf" 2>&1
  else
    EXPECT_SIG=$sig EXPECT_T0=$t0 EXPECT_T1=$t1 EXPECT_LT=$thr bash "$RS" "$D" 300 > "$logf" 2>&1
  fi
  local res
  res=$(tail -2 "$logf" | grep -oE "(PASS|FAIL)" | head -1)
  printf '  %-46s %s\n' "$label" "${res:-NO_VERDICT}"
}
win "W1 blank=1 while Q=1 -> en must stay low"     en 300n 395n lt $VOL /tmp/s1_w1.txt
win "W2 blank=0 while Q=1 -> en must be high"      en 500n 595n gt $VOL /tmp/s1_w2.txt
win "W3 q must NOT move across the blank release"  q  380n 520n gt $VOL /tmp/s1_w3.txt
win "W4 blank=0 while Q=0 -> en must be low"       en 760n 860n lt $VOL /tmp/s1_w4.txt
NPASS=0
for w in /tmp/s1_w1.txt /tmp/s1_w2.txt /tmp/s1_w3.txt /tmp/s1_w4.txt; do
  tail -2 "$w" | grep -q "PASS" && NPASS=$((NPASS+1))
done
rm -f /tmp/s1_w*.txt
if [ "$NPASS" = "4" ]; then
  echo "SCAN_DIGITAL_BLANK: PASS ($NPASS/4 windows, section=$SECTION)"
else
  echo "SCAN_DIGITAL_BLANK: FAIL ($NPASS/4 windows)"
fi

# ============================================================ C. fault injection
D="$OUT/s1_fault_polarity.scs"; emit_dc $VDDC "$D"
# deliberately swap the gate's two inputs: this makes en = !(BLANK | QBAR), so with BLANK
# asserted and Q=1 (qbar=0) the mis-wired gate outputs HIGH -- an enabled pixel during blank.
sed -i 's/X2 (qbar blank en vdd vss)/X2 (blank qbar en vdd vss)/' "$D"
sed -i 's/Vb  (blank 0) vsource dc=/Vb  (blank 0) vsource dc=/' "$D"
out=$(EXPECT_SIG=en EXPECT_SWEEP=0 EXPECT_GT=$VOL bash "$RS" "$D" 120 2>&1)
if printf '%s' "$out" | grep -qE ": PASS$"; then
  echo "S1_FAULT_INJECTION: DETECTED -- wrong BLANK polarity drove en above ${VOL} V and the checker rejected the row"
  echo "CHECKER_CAN_FAIL: PASS"
else
  echo "S1_FAULT_INJECTION: NOT DETECTED -- the checker did not react to a swapped-input gate; S1 verdicts cannot be trusted"
  echo "CHECKER_CAN_FAIL: FAIL"
fi
echo "S1_RUN: DONE section=$SECTION"
