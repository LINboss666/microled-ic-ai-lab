#!/bin/bash
# c2mos_check.sh -- run a C^2MOS testbench, assert its waveforms, emit the token.
#
#   c2mos_check.sh <ff1|shift3> [clockPeriodSeconds] [tag] [repeat]
#
#   ff1     one DFF cell                       -> token C2MOS_DFF_1CH
#   shift3  three identical stages in a chain   -> token C2MOS_SHIFT_3STAGE
#
# Every assertion window is written as a multiple of the clock period and converted
# here, so the same logical checks apply at the 200 ns stress clock and at the
# 9.765625 us application column period.
#
# Two windows per clock cycle are used on purpose:
#   early  [start+0.20T, start+0.45T]  -> inside the clock HIGH half (transparent)
#   late   [start+0.60T, start+0.95T]  -> inside the clock LOW half (hold phase);
#            the d transitions land inside these windows, so a pass proves hold AND
#            the absence of combinational feed-through at the same time.
#
# repeat>1 re-runs the identical netlist and requires the two assertion reports to be
# byte-identical. The slave keeper is a symmetric bistable whose power-on state is
# not specified, so "same verdict" alone would be weaker evidence than "same numbers".
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
TB="${1:?usage: c2mos_check.sh <ff1|shift3> [T] [tag] [repeat]}"
T="${2:-2e-7}"
TAG="${3:-run}"
REPEAT="${4:-1}"
RS="$PROJ/scripts/run_spectre.sh"
AWK="$PROJ/scripts/psf_check.awk"
LOGD="$PROJ/logs"

case "$TB" in
  ff1)    TPL="$PROJ/spectre/c2mos_ff1_func.scs";  TOKEN=C2MOS_DFF_1CH;      ;;
  shift3) TPL="$PROJ/spectre/c2mos_shift3.scs";    TOKEN=C2MOS_SHIFT_3STAGE; ;;
  *) echo "FATAL: unknown testbench '$TB'"; exit 8 ;;
esac
[ -r "$TPL" ] || { echo "FATAL: template missing $TPL"; exit 8; }
[ -r "$RS" ] && [ -r "$AWK" ] || { echo "FATAL: helper scripts missing"; exit 8; }
mkdir -p "$LOGD"

NET="$PROJ/spectre/run_${TB}_${TAG}.scs"
DIRS="$LOGD/c2mos_dirs_${TB}_${TAG}.txt"
awk -v t="$T" '{ if ($0 ~ /^parameters T=/) print "parameters T=" t; else print }' "$TPL" > "$NET"
# Optional model-section override (scripts/pvt_probe.sh uses it to re-run the identical
# assertions at another corner). Unset => whatever the template says, which is tt.
if [ -n "${SECTION:-}" ]; then
  awk -v s="$SECTION" '{ sub(/section=[A-Za-z0-9_]+/, "section=" s); print }' "$NET" > "$NET.tmp"
  mv "$NET.tmp" "$NET"
  echo "model section override = $SECTION"
fi

# t(<multiple of T>) -> absolute seconds
t() { awk -v t="$T" -v f="$1" 'BEGIN{printf "%.9g", t*f}'; }
# add(<number>, <offset>) -> number (assertion windows are written in units of T)
add() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.9g", a+b}'; }
# level -> the operator/threshold pair used for that logic level
thr() { if [ "$1" = "1" ]; then echo "gt 1.7"; else echo "lt 0.1"; fi; }

# ------------------------------------------------------------------ directives
build_dirs() {
  local f="$1" i s a b c d line
  : > "$f"
  if [ "$TB" = "ff1" ]; then
    echo "# ---- single C^2MOS DFF: q must repeat d's value one clock later: 1,0,1,0" >> "$f"
    local STARTS="0.5 1.5 2.5 3.5"
    local Q="1 0 1 0"
    i=1
    for s in $STARTS; do
      a=$(add "$s" 0.20); b=$(add "$s" 0.45)
      c=$(add "$s" 0.60); d=$(add "$s" 0.95)
      local j v; j=1; v=""
      for x in $Q; do [ "$j" = "$i" ] && v="$x"; j=$((j+1)); done
      line=$(thr "$v")
      echo "ASSERT q   $(t $a) $(t $b) $line" >> "$f"
      echo "ASSERT q   $(t $c) $(t $d) $line" >> "$f"
      # qbar is the complement of the stored value
      if [ "$v" = "1" ]; then line=$(thr 0); else line=$(thr 1); fi
      echo "ASSERT qbar $(t $a) $(t $b) $line" >> "$f"
      echo "ASSERT qbar $(t $c) $(t $d) $line" >> "$f"
      i=$((i+1))
    done
    echo "# ---- evidence that the INPUT really alternated 1,0,1,0 (not a lone '1')" >> "$f"
    echo "CROSS d 0.9 $(t 0.30)" >> "$f"
    echo "FALL  d 0.9 $(t 1.30)" >> "$f"
    echo "CROSS d 0.9 $(t 2.30)" >> "$f"
    echo "FALL  d 0.9 $(t 3.30)" >> "$f"
    echo "# ---- clk->Q, always referenced to the CLOCK RISING edge that captures" >> "$f"
    echo "#      (the cell has no reset, so q's level before the first rising edge is" >> "$f"
    echo "#       whatever the DC operating point left in the slave keeper -- the first" >> "$f"
    echo "#       edge is therefore not a valid 0->1 observation and is not measured.)" >> "$f"
    echo "CROSS clk 0.9 0"          >> "$f"
    echo "CROSS clk 0.9 $(t 1.40)"  >> "$f"
    echo "FALL  d   0.9 $(t 1.30)"  >> "$f"
    echo "FALL  q   0.9 $(t 1.40)"  >> "$f"
    echo "CROSS clk 0.9 $(t 2.40)"  >> "$f"
    echo "CROSS d   0.9 $(t 2.30)"  >> "$f"
    echo "CROSS q   0.9 $(t 2.40)"  >> "$f"
    echo "CROSS clk 0.9 $(t 3.40)"  >> "$f"
    echo "FALL  d   0.9 $(t 3.30)"  >> "$f"
    echo "FALL  q   0.9 $(t 3.40)"  >> "$f"
    echo "CROSS clk 0.9 $(t 4.40)"  >> "$f"
    echo "CROSS d   0.9 $(t 4.30)"  >> "$f"
    echo "CROSS q   0.9 $(t 4.40)"  >> "$f"
    return
  fi

  echo "# ---- 3-stage chain, expected table (cycle start: q0 q1 q2) ----" >> "$f"
  echo "#   3.5T: 1 0 0   4.5T: 0 1 0   5.5T: 1 0 1   6.5T: 0 1 0   7.5T: 1 0 1" >> "$f"
  local STARTS="3.5 4.5 5.5 6.5 7.5"
  local L0="1 0 1 0 1"
  local L1="0 1 0 1 0"
  local L2="0 0 1 0 1"
  i=1
  for s in $STARTS; do
    a=$(add "$s" 0.20); b=$(add "$s" 0.45)
    c=$(add "$s" 0.60); d=$(add "$s" 0.95)
    local j k v
    for k in 0 1 2; do
      local LIST
      case "$k" in 0) LIST="$L0";; 1) LIST="$L1";; 2) LIST="$L2";; esac
      j=1; v=""
      for x in $LIST; do [ "$j" = "$i" ] && v="$x"; j=$((j+1)); done
      line=$(thr "$v")
      echo "ASSERT q$k $(t $a) $(t $b) $line" >> "$f"
      echo "ASSERT q$k $(t $c) $(t $d) $line" >> "$f"
    done
    i=$((i+1))
  done
  echo "# ---- no race-through: while the '1' is only in FF0, FF2 must be low" >> "$f"
  echo "ASSERT q2 $(t 3.55) $(t 4.45) lt 0.1" >> "$f"
  echo "# ---- complementary output of each stage, one cycle each" >> "$f"
  echo "ASSERT q0b $(t 3.70) $(t 4.40) lt 0.1" >> "$f"
  echo "ASSERT q1b $(t 4.70) $(t 5.40) lt 0.1" >> "$f"
  echo "ASSERT q2b $(t 5.70) $(t 6.40) lt 0.1" >> "$f"
  echo "# ---- clk->Q per stage, at the edge where that stage first takes a '1'" >> "$f"
  echo "CROSS clk 0.9 $(t 3.40)" >> "$f"
  echo "CROSS q0  0.9 $(t 3.40)" >> "$f"
  echo "CROSS clk 0.9 $(t 4.40)" >> "$f"
  echo "CROSS q1  0.9 $(t 4.40)" >> "$f"
  echo "CROSS clk 0.9 $(t 5.40)" >> "$f"
  echo "CROSS q2  0.9 $(t 5.40)" >> "$f"
}

# xtime <assert-file> <CROSS|FALL> <signal> <t0> -> crossing time (empty if missing)
xtime() {
  awk -v k="$2" -v s="$3" -v z="$4" '
    $1=="OK" && $2==k && $3==s {
      t=$5; sub(/^t=/, "", t)
      if (NF>=6) { tt=$6; sub(/^t0=/, "", tt); if (tt+0 != z+0) next }
      print t; exit
    }' "$1"
}

run_once() {
  local idx="$1"
  local runlog="$LOGD/c2mos_run_${TB}_${TAG}_${idx}.out"
  local ass="$LOGD/c2mos_assert_${TB}_${TAG}_${idx}.txt"
  local data rc ack nf tot
  LABEL="STRUCT_${TB}_${TAG}_${idx}" bash "$RS" "$NET" 500 > "$runlog" 2>&1
  rc=$?
  data=$(grep -aoE "CHECK datafile='[^']+'" "$runlog" | sed -E "s/.*'(.*)'/\1/")
  if [ "$rc" != "0" ] || [ -z "$data" ] || [ ! -r "$data" ]; then
    echo "[$idx] SPECTRE RUN FAILED rc=$rc  log=$runlog"
    grep -aE "^SPECTRE name|^CHECK error_hits|ERROR \(" "$runlog" | head -6 | sed 's/^/    /'
    tail -18 "$runlog"
    return 1
  fi
  echo "[$idx] spectre finished, datafile=$(basename "$data")"
  awk -f "$AWK" "$DIRS" "$data" > "$ass"
  ack=$?
  grep -a "^FAIL\|^BAD" "$ass" | head -14 | sed 's/^/    /'
  nf=$(grep -ac "^FAIL" "$ass")
  tot=$(grep -acE "^(OK|FAIL)" "$ass")
  echo "[$idx] assertions: total=$tot failed=$nf"
  # clk->Q delays. tee'd into a file on purpose: a number that only exists in an
  # agent's console output is not evidence a human can re-check.
  local dl="$LOGD/c2mos_delays_${TB}_${TAG}_${idx}.txt"
  : > "$dl"
  if [ "$TB" = "ff1" ]; then
    local o kind cc qq dd
    for o in "1.40 FALL" "2.40 CROSS" "3.40 FALL" "4.40 CROSS"; do
      set -- $o; o=$1; kind=$2
      cc=$(xtime "$ass" CROSS clk "$(t $o)")
      qq=$(xtime "$ass" "$kind" q "$(t $o)")
      # the data 50% crossing that belongs to this edge: 0.10T before the edge search
      # start is where the pattern puts it (d toggles at edge - 0.15T)
      dd=$(xtime "$ass" "$kind" d "$(t $(add "$o" -0.10))")
      awk -v a="$cc" -v b="$qq" -v c="$dd" -v o="$o" -v k="$kind" -v tt="$T" 'BEGIN{
        lbl = (k=="CROSS" ? "rise" : "fall")
        if (a==""||b=="") { printf "  DELAY  %s t0=%sT: not measured\n", k, o; exit }
        printf "  TIMING edge=%sT kind=%-4s t_CLK50=%.6g t_Q50=%.6g t_D50=%s", o, lbl, a, b, \
               (c=="" ? "not-found" : sprintf("%.6g", c+0))
        printf "  D50_to_CLK50=%s  CLK50_to_Q50=%.6g s (%.3g%% of T)\n", \
               (c=="" ? "n/a" : sprintf("%.6g", a-c)), b-a, 100*(b-a)/tt }' | tee -a "$dl"
    done
  else
    local i t0 cc qq
    for i in 0 1 2; do
      t0=$(t $(add 3.4 $i))
      cc=$(xtime "$ass" CROSS clk "$t0"); qq=$(xtime "$ass" CROSS "q$i" "$t0")
      awk -v a="$cc" -v b="$qq" -v i="$i" -v tt="$T" 'BEGIN{
        if (a==""||b=="") { printf "  DELAY  FF%s clk->Q: not measured\n", i; exit }
        printf "  DELAY  FF%s clk->Q (rise) = %.4g s = %.3g%% of T\n", i, b-a, 100*(b-a)/tt }' | tee -a "$dl"
    done
  fi
  [ "$ack" = "0" ]
}

build_dirs "$DIRS"
echo "TB=$TB T=$T tag=$TAG"
echo "netlist=$NET"
echo "directives=$DIRS rules=$(grep -acE '^(ASSERT|CROSS|FALL)' "$DIRS")"

# ---- A8 gate: no formal transient unless the testbench rails are proven real ------
if [ "${SKIP_PREFLIGHT:-0}" != "1" ]; then
  echo "--- testbench preflight"
  pf_out=$(bash "$PROJ/scripts/tb_preflight.sh" "$NET" "${VDD_EXP:-1.8}" "$TB" 2>&1)
  pf_rc=$?
  echo "$pf_out" | grep -aE "STATIC_OK|STATIC_FAIL|OP_OK|OP_FAIL|RAIL_|TESTBENCH_PREFLIGHT" | sed 's/^/    /'
  if [ "$pf_rc" != "0" ]; then
    echo "$TOKEN: FAIL  (testbench preflight refused; see $LOGD/preflight_$(basename "$NET" .scs)_$TB.txt)"
    exit 1
  fi
fi

allok=1
for r in $(seq 1 "$REPEAT"); do
  run_once "$r" || allok=0
done

if [ "$allok" = "1" ] && [ "$REPEAT" -gt 1 ]; then
  a="$LOGD/c2mos_assert_${TB}_${TAG}_1.txt"
  b="$LOGD/c2mos_assert_${TB}_${TAG}_${REPEAT}.txt"
  if cmp -s "$a" "$b"; then
    echo "REPEAT: $REPEAT runs produced byte-identical assertion reports"
  else
    echo "REPEAT: reports differ between run 1 and run $REPEAT"
    diff "$a" "$b" | head -12
    allok=0
  fi
fi

if [ "$allok" = "1" ]; then
  echo "$TOKEN: PASS"
  exit 0
fi
echo "$TOKEN: FAIL"
exit 1
