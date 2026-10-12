#!/bin/bash
# SCAN-1R S1: BLANK/ENABLE verification, reworked after the S1 REWORK review.
#
#   bash scripts/sc1_s1r.sh [tt|ss|ff]
#
# What this fixes versus the previous attempt, all of it measured:
#  * SFE-874 root cause was MY syntax, not the PDK:
#      ERROR (SFE-874): ".../s1_dff.scs" 11: Unexpected real number "100n".
#                       Expected close parenthesis.   (same for line 13)
#    Those lines were `type=pwl time=(0 100n ...) val=(...)`, which this build does not accept.
#    spectre -h vsource on this machine shows the supported form: type=pwl wave=[t v t v ...]
#    and type=pulse val0=.. val1=.. . Used here as written in the help, not remembered syntax.
#  * preflight is mandatory and a failure STOPS the script with a non-zero exit. Nothing can
#    reach a verdict by skipping it.
#  * the evidence CSV now stores the measured en voltage pulled out of the psfascii by
#    sc1_read_psf.py, instead of the threshold text.
#  * the fault injection is a real fault: the gate's BLANK pin is clamped to vss in a copy, so
#    BLANK=1 no longer suppresses the select. The ORIGINAL assertion must catch it. Expected
#    values are untouched, so a "detection" cannot be manufactured.
#  * harness self-tests: nonexistent signal, empty data file, and a bench whose vss floats must
#    all be reported as failures by the tools, proving a green result means something.
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
RD="$PROJ/scripts/sc1_read_psf.py"
NEG="$PROJ/spectre/preflight_negative_vss_float.scs"
OUT="$PROJ/cadence_work/sc1_sim"
VDDC=1.8
VOL=0.9
mkdir -p "$OUT"
for f in "$GOLD" "$CELL" "$RS" "$PF" "$RD"; do
  [ -f "$f" ] || { echo "FATAL: required input missing: $f"; exit 8; }
done
echo "SECTION=$SECTION VDD_CORE=$VDDC DECISION_LEVEL=$VOL"
echo "GOLDEN_SUBCKT_SHA=$(sed -n '/^subckt c2mos_dff/,/^ends c2mos_dff/p' "$GOLD" | sha256sum | cut -d' ' -f1 | cut -c1-16)"

rc_stop=0

# ============================================================ A. truth table with real volts
emit_dc() {
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
CSV="$OUT/s1r_truth.csv"
echo "Q,BLANK,en_measured_V,row_expected,assert_verdict" > "$CSV"
echo "=== A. truth table (DC sweep, measured volts) ==="
# run_spectre's point assertion is used to EXECUTE and validate each deck; the reported voltage
# is then read out of the psfascii itself, so the CSV holds a measurement rather than a threshold.
for bmv in 0 $VDDC; do
  D="$OUT/s1r_dc_blank${bmv}.scs"; emit_dc "$bmv" "$D"
  bash "$RS" "$D" 120 > "$OUT/_dc_$(basename $D).log" 2>&1 || { echo "  SIM FAIL $D"; rc_stop=1; continue; }
  df=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_dc_$(basename $D).log" | head -1)
  if [ "$bmv" = "0" ]; then BSTATE=0; else BSTATE=1; fi
  for qmv in 0 $VDDC; do
    if [ "$qmv" = "0" ]; then Q=1; else Q=0; fi
    if [ "$Q" = "1" ] && [ "$BSTATE" = "0" ]; then want=ON; else want=OFF; fi
    val=$(python "$RD" --data "$df" --sig en --sweep "$qmv" 2>&1)
    case "$val" in
      *[!0-9.]*) echo "  READER_FAIL Q=$Q BLANK=$BSTATE : $val"; verdict=FAIL; rc_stop=1 ;;
      *)
        if [ "$want" = ON ]; then
          ok=$(python -c "print('PASS' if float('$val')>$VOL else 'FAIL')")
        else
          ok=$(python -c "print('PASS' if float('$val')<$VOL else 'FAIL')")
        fi
        verdict=$ok; [ "$ok" = PASS ] || rc_stop=1
        ;;
    esac
    echo "  Q=$Q BLANK=$BSTATE -> en=${val}V expect=$want  $verdict"
    echo "$Q,$BSTATE,${val},${want},${verdict}" >> "$CSV"
  done
done
if [ "$rc_stop" = "0" ]; then echo "S1_TRUTH_TABLE: PASS rows=4/4"; else echo "S1_TRUTH_TABLE: FAIL"; fi

# ============================================================ B. golden DFF drives the gate
D="$OUT/s1r_dff.scs"
{
  echo "simulator lang=spectre insensitive=yes"
  echo "include \"$LIB\" section=$SECTION"
  echo "include \"$GOLD\""
  echo "include \"$CELL\""
  echo "// stimulus syntax taken from 'spectre -h vsource' ON THIS BUILD:"
  echo "//   type=pulse val0=.. val1=..   and   type=pwl wave=[t v t v ...]"
  echo "// (the previous deck used time=(...) val=(...) and died at read-in, SFE-874)"
  echo "Vdd (vdd 0) vsource dc=1.8"
  echo "Vss (vss 0) vsource dc=0"
  echo "Vclk (clk 0) vsource type=pulse val0=0 val1=1.8 delay=50n rise=1n fall=1n period=100n width=50n"
  echo "Vd (d 0) vsource type=pwl wave=[0 0 260n 0 270n 1.8 620n 1.8 630n 0 900n 0]"
  echo "Vbl (blank 0) vsource type=pwl wave=[0 1.8 450n 1.8 460n 0 900n 0]"
  echo "X1 (d clk q qbar vdd vss) c2mos_dff"
  echo "X2 (qbar blank en vdd vss) sc1_scan_gate"
  echo "sw1 tran stop=900n maxstep=1n method=traponly"
  echo "save clk d q qbar blank en vdd vss"
} > "$D"

echo "=== B. preflight (mandatory; a failure stops the run) ==="
# Capture preflight's own status, not the status of a command appended to it with a pipe:
# `pf | tail` reports tail's exit code, which would silently let a refused bench through.
bash "$PF" "$D" $VDDC s1r > "$OUT/preflight.log" 2>&1
PFR=$?
tail -5 "$OUT/preflight.log"
if [ "$PFR" != "0" ]; then
  echo "S1_TRANSPARENT_PREFLIGHT: FAIL (exit $PFR) -> aborting before any verdict"
  exit 7
fi
echo "PREFLIGHT: PASS exit=0"
echo "--- running the transient once; all windows are then measured from that data ---"
bash "$RS" "$D" 300 > "$OUT/_sim.log" 2>&1
if ! grep -q ": PASS" "$OUT/_sim.log"; then
  echo "S1_TRANSIENT_SIM: FAIL -- runner refused the result"; tail -4 "$OUT/_sim.log"; exit 7
fi
DF=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_sim.log" | head -1)
echo "DATAFILE=$DF"
# window judging is done here, in SI units, with a minimum-sample guard. The previous version used
# run_spectre's window mode, which passes EXPECT_T0=400n to awk as -v t0=400n; awk reads that as the
# number 400 and compares it against sample times of ~4e-7, so every window looked empty and the
# LT assertions "failed" for a reason that had nothing to do with the circuit.
awk_win() {  # sig t0 t1 mode
  python "$RD" --data "$DF" --sig "$1" --t0 "$2" --t1 "$3" --mode "$4" --require-n 3 2>&1
}
cmpv() { python -c "
import sys
v=sys.argv[1]; t=float(sys.argv[2]); k=sys.argv[3]
try: x=float(v)
except ValueError: print('BAD'); sys.exit(0)
print('PASS' if (x>t if k=='gt' else x<t) else 'FAIL')" "$1" "$2" "$3"; }
win() {
  local label="$1" sig="$2" t0="$3" t1="$4" kind="$5"
  local got ok
  got=$(awk_win "$sig" "$t0" "$t1" "$([ "$kind" = gt ] && echo min || echo max)")
  ok=$(cmpv "$got" "$VOL" "$kind")
  printf '  %-52s %-4s worst-case=%s V  (window %s..%s, kind=%s)\n' "$label" "$ok" "$got" "$t0" "$t1" "$kind"
  echo "$label,$got,$ok" >> "$OUT/s1r_transient.csv"
  [ "$ok" = PASS ] || rc_stop=1
}
echo "--- transient windows (section=$SECTION) ---"
: > "$OUT/s1r_transient.csv"
echo "check,worst_case_in_window_V,verdict" >> "$OUT/s1r_transient.csv"
clkv=$(awk_win clk 60n 90n max)
if [ "$(cmpv "$clkv" $VOL gt)" = PASS ]; then
  echo "S1_STIMULUS_SANITY: PASS (clk reached $clkv V, so an en verdict means something)"
else
  echo "S1_STIMULUS_SANITY: FAIL -- clk only reached $clkv V"; rc_stop=1
fi
win "T1 BLANK=1 while Q=1 : en must stay low"     en 400n 455n lt
win "T2 BLANK=0 while Q=1 : en must be high"      en 520n 620n gt
win "T3 q undisturbed across BLANK release"        q  410n 520n gt
win "T4 BLANK=0 while Q=0 : en must be low"       en 700n 860n lt
win "T5 q follows the falling-data clock edge"     q  700n 860n lt
NPASS=$(grep -c ",PASS" "$OUT/s1r_transient.csv" 2>/dev/null || echo 0)
if [ "$NPASS" = "5" ] && [ "$rc_stop" = "0" ]; then
  echo "SCAN_DIGITAL_BLANK: PASS (5/5 windows, section=$SECTION)"
else
  echo "SCAN_DIGITAL_BLANK: FAIL ($NPASS/5 windows rc_stop=$rc_stop)"
fi

# ============================================================ C. real fault injection
# Same verified deck; the ONLY change is that the gate's BLANK pin is clamped to vss, i.e. a
# strap that never lets BLANK reach the gate. Expected values and thresholds are NOT touched, and
# the measurement path is identical to T1, so a detection here is real.
F="$OUT/s1r_fault_blank_clamped.scs"
sed 's/X2 (qbar blank en vdd vss) sc1_scan_gate/X2 (qbar vss en vdd vss) sc1_scan_gate/' "$D" > "$F"
bash "$RS" "$F" 300 > "$OUT/_fsim.log" 2>&1
FDF=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_fsim.log" | head -1)
FVAL=$(python "$RD" --data "$FDF" --sig en --t0 400n --t1 455n --mode max --require-n 3 2>&1)
if [ "$(cmpv "$FVAL" $VOL gt)" = PASS ]; then
  echo "S1_FAULT_INJECTION: DETECTED -- with BLANK clamped the gate drove en=$FVAL V during blank,"
  echo "                        while the correct circuit measured $(awk_win en 400n 455n max) V."
  echo "                        The unchanged T1 assertion rejected it. Expected values were not modified."
  echo "CHECKER_CAN_FAIL: PASS"
else
  echo "S1_FAULT_INJECTION: NOT DETECTED (faulted en=$FVAL V, threshold $VOL) -- checker is toothless"
  echo "CHECKER_CAN_FAIL: FAIL"; rc_stop=1
fi

# ============================================================ D. harness self-tests (must FAIL)
echo "=== D. negative tests of the checker itself ==="
python "$RD" --deck "$D" --sig does_not_exist --t0 400n --t1 455n >/tmp/n1.txt 2>&1
N1=$?
grep -q PASS "$OUT/_t1" >/dev/null && N1OK=PASS || N1OK=FAIL
if [ "$N1" = "3" ]; then echo "  missing-signal handled as NO_SIGNAL (exit 3) : PASS"; else echo "  missing-signal exit=$N1 (expected 3) : FAIL"; rc_stop=1; fi
: > /tmp/empty.psf
python "$RD" --data /tmp/empty.psf --sig en >/tmp/n2.txt 2>&1; N2=$?
if [ "$N2" = "2" ]; then echo "  empty data file handled as NO_DATA_FILE (exit 2) : PASS"; else echo "  empty file exit=$N2 (expected 2) : FAIL"; rc_stop=1; fi
rm -f /tmp/empty.psf /tmp/n1.txt /tmp/n2.txt
if [ -f "$NEG" ]; then
  if bash "$PF" "$NEG" 1.8 negtest >/tmp/n3.txt 2>&1; then
    echo "  vss-floating bench was ACCEPTED by preflight : FAIL (gate is toothless)"; rc_stop=1
  else
    echo "  vss-floating bench rejected by preflight      : PASS"
  fi
  rm -f /tmp/n3.txt
else
  echo "  negative bench $NEG absent : SKIPPED"
fi
echo "S1R_RUN: DONE section=$SECTION overall_rc=$rc_stop"
[ "$rc_stop" = "0" ] || exit 6
exit 0
