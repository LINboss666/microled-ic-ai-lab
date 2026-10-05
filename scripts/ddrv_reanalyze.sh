#!/bin/bash
# ddrv_reanalyze.sh -- re-run the transient checker over every already-simulated iprobe
# deck. The PSF data does not change when a checker is corrected, so a metric fix must not
# cost a re-simulation series (and must not silently leave a mix of old and new rows in one
# CSV). preflight_*.raw dirs are skipped: they hold the preflight's own operating-point run,
# not a result.
#
#   bash scripts/ddrv_reanalyze.sh            # rebuild results/data_driver_transient_iprobe.csv
#   CSV=results/x.csv RESET=0 bash scripts/ddrv_reanalyze.sh
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
CSV="${CSV:-$PROJ/results/data_driver_transient_iprobe.csv}"
[ "${RESET:-1}" = "1" ] && rm -f "$CSV"
n=0
for d in $(ls -d "$PROJ"/spectre/generated/sim/*iprobe*.raw 2>/dev/null | grep -v preflight | sort); do
  p="$d/tran1.tran.tran"
  [ -f "$p" ] || continue
  lbl=$(basename "$d" .raw | sed -e 's/^ddrv_//' -e 's/_n33_tt_/_/' -e 's/_local_gate//')
  out="$PROJ/results/evidence/reanal_${lbl}.txt"
  python "$PROJ/scripts/ddrv_tran.py" "$p" --require-probe --label "$lbl" --csv "$CSV" \
      > "$out" 2>&1
  rc=$?
  printf "%-56s rc=%s | %s\n" "$lbl" "$rc" \
    "$(grep -aoE 'TURN_ON_SETTLING *: [0-9.e-]+ s|TURN_OFF *: [0-9.e-]+ s|ON_SETTLED *: [0-9.]+ \.\. [0-9.]+ uA|ON_RIPPLE *: [0-9.]+|OFF_LEAKAGE *: [0-9.]+|never settled' "$out" | tr '\n' ' ')"
  n=$((n + 1))
done
echo "REANALYZED runs=$n csv=$CSV"
