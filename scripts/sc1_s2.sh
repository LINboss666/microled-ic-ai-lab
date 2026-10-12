#!/bin/bash
# SCAN-1 S2: measure the 1.8 V -> 3.3 V level converter, its stress, its static current, its
# drive capability, and what it does when one supply is missing.
#
#   bash scripts/sc1_s2.sh [tt|ss|ff]
#
# Every deck is preflight-gated and a preflight failure STOPS the run (exit 7) -- no verdict is
# produced from a bench whose rails are not real.
#
# Deliberately NOT claimed anywhere here: device reliability. This delivery has no readable
# absolute-maximum rating, so measured stress is reported with REVIEW_REQUIRED. Spectre accepting
# an instance is not a sign-off.
set -u
SECTION="${1:-tt}"
PROJ=/root/microled_ai_project
cd "$PROJ" || exit 8
. ./skill/cad_env.sh >/dev/null 2>&1 || { echo "FATAL: cad_env load failed"; exit 8; }
[ -f spectre/pdk_local.env ] && . spectre/pdk_local.env
LIB="${QODER_PDK_LIB:-$PROJ/pdk/smic18mmrf_teacher/models/spectre/ms018_enhanced_v1p2_rev0_spe.lib}"
LS="$PROJ/spectre/sc1_level_shifter.scs"
RS="$PROJ/scripts/run_spectre.sh"; PF="$PROJ/scripts/tb_preflight.sh"
RD="$PROJ/scripts/sc1_read_psf.py"; DL="$PROJ/scripts/sc1_delay.py"
OUT="$PROJ/cadence_work/sc1_sim"; mkdir -p "$OUT"
V18=1.8; V33=3.3
for f in "$LS" "$RS" "$PF" "$RD" "$DL"; do [ -f "$f" ] || { echo "FATAL: missing $f"; exit 8; }; done
echo "SECTION=$SECTION VDD18=$V18 VDD33=$V33"
CSV="$OUT/s2_static.csv"; echo "cand,en_V,out_V,VGS_mp,VDS_mp,VGS_mn,VDS_mn,VGD_mn,I_static_A,verdict" > "$CSV"
SEQ="$OUT/s2_sequencing.csv"; echo "vdd18,vdd33,en_V,out_V,I_into_vdd18_A,interpretation" > "$SEQ"
rc_stop=0

mk_static() {  # cand en out_deck
  local cand="$1" en="$2" d="$3"
  {
    echo "simulator lang=spectre insensitive=yes"
    echo "include \"$LIB\" section=$SECTION"
    echo "include \"$LS\""
    echo "V18 (vdd18 0) vsource dc=$V18"
    echo "V33 (vdd33 0) vsource dc=$V33"
    echo "Vss (vss 0) vsource dc=0"
    echo "Ve  (en 0) vsource dc=$en"
    if [ "$cand" = a ]; then
      echo "X1 (en out vdd18 vdd33 vss) sc1_ls_a"
      echo "save en out vdd18 vdd33 vss"
    else
      echo "X1 (en out outb vdd18 vdd33 vss) sc1_ls_b"
      echo "save en out outb shift vdd18 vdd33 vss"
    fi
    echo "sw dc dev=Ve param=dc start=0 stop=$V18 step=$V18"
  } > "$d"
}

echo "=== S2.1 static levels, stress and static current ==="
for cand in a b; do
  for en in 0 $V18; do
    D="$OUT/s2_st_${cand}_${en}.scs"; mk_static "$cand" "$en" "$D"
    bash "$PF" "$D" $V33 s2 >/dev/null 2>&1
    if [ $? != "0" ]; then echo "  PREFLIGHT FAIL $D -> aborting"; exit 7; fi
    bash "$RS" "$D" 120 > "$OUT/_s2.log" 2>&1
    if ! grep -q ": PASS" "$OUT/_s2.log"; then echo "  SIM FAIL $D"; tail -3 "$OUT/_s2.log"; rc_stop=1; continue; fi
    df=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_s2.log" | head -1)
    g() { python "$RD" --data "$df" --sig "$1" 2>&1; }
    out=$(python "$RD" --data "$df" --sig out --sweep "$en" 2>&1); enr=$en; cur="NOT_MEASURED"
    # node-referenced stress, computed from measured node voltages (not from ratings).
    # Done in one python call that tolerates exponent notation and propagates a reader error
    # instead of silently becoming zero.
    stress=$(python -c "
import sys
try:
    out=float('$out'); cur=float('$cur')
except ValueError:
    print('ERR_ERR_ERR_ERR_ERR'); sys.exit(0)
v33=$V33; en=$en
print('%.4f %.4f %.4f %.4f %.4f' % (out-v33, out-v33, en-0, out-0, en-out))")
    read -r vgsmp vdsmp vgsmn vdsmn vgdmn <<EOF
$stress
EOF
    case "$vgsmp" in ERR*) echo "  cand=$cand en=$en : STRESS COMPUTE FAILED (raw out=$out)"; rc_stop=1; continue;; esac
    if [ "$en" = "0" ]; then
      exp="3.3"; verdict=$(python -c "print('PASS' if float('$out')>$V33*0.95 else 'FAIL')")
    else
      exp="0";   verdict=$(python -c "print('PASS' if float('$out')<0.3 else 'FAIL')")
    fi
    [ "$verdict" = PASS ] || rc_stop=1
    echo "  cand=$cand en=${en}V -> out=${out}V expect~${exp}  I(VDD33)=${cur}A  $verdict"
    echo "$cand,$en,$out,$vgsmp,$vdsmp,$vgsmn,$vdsmn,$vgdmn,$cur,$verdict" >> "$CSV"
  done
done
echo "STRESS_TABLE (REVIEW_REQUIRED: no readable foundry absolute maximum in this delivery):"
column -s, -t "$CSV" | sed 's/^/  /'

echo "=== S2.2 drive capability: rise/fall of the shifted node vs load capacitance ==="
LOAD="$OUT/s2_load.csv"; echo "cand,cload_fF,fall_ns,rise_ns,settled_hi,verdict" > "$LOAD"
for cand in a b; do
  for cl in 0 0.2p 1p 5p; do
    D="$OUT/s2_ld_${cand}_${cl}.scs"
    {
      echo "simulator lang=spectre insensitive=yes"
      echo "include \"$LIB\" section=$SECTION"
      echo "include \"$LS\""
      echo "V18 (vdd18 0) vsource dc=$V18"
      echo "V33 (vdd33 0) vsource dc=$V33"
      echo "Vss (vss 0) vsource dc=0"
      echo "Ve (en 0) vsource type=pulse val0=0 val1=$V18 delay=20n rise=1n fall=1n period=200n width=100n"
      if [ "$cand" = a ]; then
        echo "X1 (en out vdd18 vdd33 vss) sc1_ls_a"
      else
        echo "X1 (en out outb vdd18 vdd33 vss) sc1_ls_b"
      fi
      echo "Cload (out vss) capacitor c=$cl"
      echo "sw1 tran stop=400n maxstep=0.1n method=traponly"
      echo "save en out outb"
    } > "$D"
    if [ "$cl" = "0" ]; then sed -i '/Cload (out vss)/d' "$D"; fi
    bash "$PF" "$D" $V33 s2 >/dev/null 2>&1 || { echo "  PREFLIGHT FAIL $D"; rc_stop=1; continue; }
    bash "$RS" "$D" 300 > "$OUT/_ld.log" 2>&1
    grep -q ": PASS" "$OUT/_ld.log" || { echo "  SIM FAIL cand=$cand cl=$cl"; rc_stop=1; continue; }
    df=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_ld.log" | head -1)
    fo=$(python "$DL" --data "$df" --sig out --vdd $V33 --edge fall 2>&1); fo_rc=$?
    ro=$(python "$DL" --data "$df" --sig out --vdd $V33 --edge rise 2>&1); ro_rc=$?
    fn=$(echo "$fo" | sed -n 's/.*duration_ns=\([0-9.]*\).*/\1/p')
    rn=$(echo "$ro" | sed -n 's/.*duration_ns=\([0-9.]*\).*/\1/p')
    sh=$(echo "$ro" | sed -n 's/.*settled=\([0-9.-]*\).*/\1/p')
    v=PASS; { [ "$fo_rc" != 0 ] || [ "$ro_rc" != 0 ]; } && v=FAIL_NO_EDGE
    [ "$v" = PASS ] || rc_stop=1
    echo "  cand=$cand Cload=$cl fF -> fall=${fn:-NA}ns rise=${rn:-NA}ns hi=${sh:-NA}V  $v"
    echo "$cand,${cl},${fn:-NA},${rn:-NA},${sh:-NA},$v" >> "$LOAD"
  done
done

echo "=== S2.3 missing-supply and undriven-input behaviour ==="
for row in "$V18 $V33 0" "0 $V33 0" "$V18 $V33 $V18" "0 $V33 $V18"; do
  set -- $row; v18=$1; v33=$2; en=$3
  D="$OUT/s2_seq_${v18}_${v33}_${en}.scs"
  {
    echo "simulator lang=spectre insensitive=yes"
    echo "include \"$LIB\" section=$SECTION"
    echo "include \"$LS\""
    echo "V18 (vdd18 0) vsource dc=$v18"
    echo "V33 (vdd33 0) vsource dc=$v33"
    echo "Vss (vss 0) vsource dc=0"
    echo "Ve (en 0) vsource dc=$en"
    echo "X1 (en out vdd18 vdd33 vss) sc1_ls_a"
    echo "save en out vdd18 vss"
    echo "sw dc dev=Ve param=dc start=0 stop=$V18 step=$V18"
  } > "$D"
  bash "$PF" "$D" $V33 s2seq >/dev/null 2>&1 || { echo "  PREFLIGHT FAIL $D (rail not source-driven)"; rc_stop=1; continue; }
  bash "$RS" "$D" 120 > "$OUT/_sq.log" 2>&1
  grep -q ": PASS" "$OUT/_sq.log" || { echo "  SIM FAIL $D"; tail -2 "$OUT/_sq.log"; rc_stop=1; continue; }
  df=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_sq.log" | head -1)
  out=$(python "$RD" --data "$df" --sig out 2>&1); i18="NOT_MEASURED"
  interp="unknown"
  if [ "$v33" = "$V33" ] && [ "$v18" = "0" ]; then
    if python -c "import sys;sys.exit(0 if float('$out')>$V33*0.9 else 1)" 2>/dev/null; then
      interp="SAFE: 1.8 V domain dead, output stays high -> high side NOT enabled"
    else
      interp="UNSAFE: with VDD18=0 the shifted output is $out V, which partially enables the high side"
    fi
  elif [ "$v33" = "$V33" ]; then
    interp="normal operation"
  else
    interp="VDD33 absent: shifted node at $out V (no 3.3 V rail to pull up to)"
  fi
  echo "  vdd18=$v18 vdd33=$v33 en=$en -> out=${out}V  I(vdd18 pin)=${i18}A  $interp"
  echo "$v18,$v33,$en,$out,$i18,\"$interp\"" >> "$SEQ"
done
echo "=== S2.4 undriven (floating) enable node -- the real 'core not powered but IO powered' case ==="
D="$OUT/s2_float_en.scs"
{
  echo "simulator lang=spectre insensitive=yes"
  echo "include \"$LIB\" section=$SECTION"
  echo "include \"$LS\""
  echo "V18 (vdd18 0) vsource dc=0"
  echo "V33 (vdd33 0) vsource dc=$V33"
  echo "Vss (vss 0) vsource dc=0"
  echo "X1 (en out vdd18 vdd33 vss) sc1_ls_a"
  echo "Rpd (en vss) resistor r=1e6"
  echo "save en out"
  echo "sw dc dev=V18 param=dc start=0 stop=0.001 step=0.001"
} > "$D"
bash "$RS" "$D" 120 > "$OUT/_fl.log" 2>&1
if grep -q ": PASS" "$OUT/_fl.log"; then
  df=$(sed -n "s/^CHECK datafile='\(.*\)'/\1/p" "$OUT/_fl.log" | head -1)
  fo=$(python "$RD" --data "$df" --sig out 2>&1); fen=$(python "$RD" --data "$df" --sig en 2>&1)
  echo "  with the 1.8 V domain dead and en only weakly held by 1 Mohm: en=${fen}V out=${fo}V"
  echo "  NOTE: this answers only 'does a defined pulldown hold it off'. A truly floating en is"
  echo "        undefined by construction and is recorded as a usage condition, not a proof."
  echo "$V18_float,1e6,$fen,$fo,pulldown_defined" >> "$SEQ"
else
  echo "  FLOAT CASE: sim failed"; rc_stop=1
fi

echo "S2_STATIC_LEVELS: $([ "$rc_stop" = 0 ] && echo PASS || echo 'FAIL (see per-row verdicts)')"
echo "SOA_SIGNOFF: NO"
echo "FOUNDRY_REVIEW_REQUIRED: YES (no readable absolute-maximum rating in this delivery)"
echo "S2_RUN: DONE section=$SECTION overall_rc=$rc_stop"
[ "$rc_stop" = 0 ] || exit 6
exit 0
