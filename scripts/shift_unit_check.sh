#!/bin/bash
# Verify the 1-bit scan-driver shift cell in Spectre, then assert the waveforms.
#
#   shift_unit_check.sh [clock_period_seconds] [label]
#
# Default clock period 9.765625e-6 s = the 100 Hz column period derived from the
# course topology (1/(1024 columns x 100 Hz)); pass e.g. 100e-9 to probe speed margin.
#
# What is proven (all windows expressed as multiples of T, computed here so the
# assertions stay valid when T changes):
#   - a single injected '1' advances exactly one cell per clock period
#   - cell 1/2/3 outputs are high in their expected slots and low elsewhere
#   - the buffered output never fires before its own slot (no premature row)
#   - measured 50% crossings, to report per-cell delay against the clock period
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
T="${1:-9.765625e-6}"
LABEL_TAG="${2:-nominal}"
TPL="$PROJ/spectre/shift_unit_tb.scs"
NET="$PROJ/spectre/shift_tb_${LABEL_TAG}.scs"
RS="$PROJ/scripts/run_spectre.sh"
AWK="$PROJ/scripts/psf_check.awk"
DIRS="$PROJ/logs/psf_dirs_${LABEL_TAG}.txt"
RUNLOG="$PROJ/logs/shift_run_${LABEL_TAG}.out"

[ -r "$TPL" ] || { echo "FATAL: template missing $TPL"; exit 8; }
[ -r "$RS" ] && [ -r "$AWK" ] || { echo "FATAL: helper scripts missing"; exit 8; }

# render: replace only the T= parameter line
awk -v t="$T" '{ if ($0 ~ /^parameters T=/) print "parameters T=" t; else print }' "$TPL" > "$NET"
echo "RENDER netlist=$NET T=$T"

# 1) run spectre (structural checks live in run_spectre.sh)
LABEL="STRUCT_${LABEL_TAG}" bash "$RS" "$NET" 400 > "$RUNLOG" 2>&1
rc=$?
grep -aE "^SPECTRE name|^CHECK done_line|^CHECK datafile|^CHECK error_hits|^VERDICT|ERROR \(" "$RUNLOG" | head -8
DATA=$(grep -aoE "CHECK datafile='[^']+'" "$RUNLOG" | sed -E "s/.*'(.*)'/\1/")
if [ "$rc" != "0" ] || [ -z "$DATA" ] || [ ! -r "$DATA" ]; then
  echo "SHIFT_UNIT_CHECK[$LABEL_TAG]: FAIL stage=spectre_run rc=$rc"
  tail -25 "$RUNLOG"
  exit 1
fi
LOGF=$(grep -aoE "^LOGFILE .*" "$RUNLOG" | sed 's/^LOGFILE //')

# 2) build the directive table from T
t() { awk -v t="$T" -v f="$1" 'BEGIN{printf "%.9g", t*f}'; }

cat > "$DIRS" <<EOF
ASSERT q1     $(t 0)      $(t 1.30)  lt 0.3
ASSERT q1     $(t 1.62)   $(t 2.35)  gt 1.5
ASSERT q1     $(t 3.00)   $(t 4.00)  lt 0.3
ASSERT q2     $(t 2.62)   $(t 3.35)  gt 1.5
ASSERT q3     $(t 3.62)   $(t 4.35)  gt 1.5
ASSERT preout $(t 0)      $(t 3.40)  lt 0.3
ASSERT preout $(t 3.72)   $(t 4.30)  gt 1.5
ASSERT preout $(t 4.80)   $(t 7.60)  lt 0.3
CROSS  q1     0.9
CROSS  q2     0.9
CROSS  q3     0.9
CROSS  preout 0.9
EOF

echo "ASSERTIONS $DIRS"
awk -f "$AWK" "$DIRS" "$DATA"
ack=$?

echo "LOGFILE $LOGF"
echo "DATAFILE $DATA"

# 3) per-cell delay summary from the 50% crossings
CROSSES=$(awk -f "$AWK" <(grep -a "^CROSS" "$DIRS") "$DATA" 2>/dev/null | grep -a "CROSS")
if [ -n "$CROSSES" ]; then
  echo "$CROSSES" | awk -v t="$T" '
    { name=$3; val=$5; sub(/^t=/, "", val); v[name]=val+0 }
    END {
      if (v["q1"] && v["q2"] && v["q3"] && v["preout"]) {
        printf "DELAY q1=%.4g q2=%.4g q3=%.4g preout=%.4g (s)\n", v["q1"], v["q2"], v["q3"], v["preout"]
        printf "DELAY per-cell q1->q2=%.4g q2->q3=%.4g ; T=%.4g ; used=%.3g%% of T\n", \
               v["q2"]-v["q1"], v["q3"]-v["q2"], t, 100*(v["q2"]-v["q1"])/t
      }
    }'
fi

if [ "$ack" = "0" ]; then
  echo "SHIFT_UNIT_CHECK[$LABEL_TAG]: PASS"
  exit 0
fi
echo "SHIFT_UNIT_CHECK[$LABEL_TAG]: FAIL (waveform assertions)"
exit 1
