#!/bin/bash
# SCH-3 verification entry point: one read-only readback log in, per-cell gates out.
#
# Both gates are called per cellview because they answer different questions and neither can
# substitute for the other (measured this round: the pre-fix readback passes every connectivity
# assertion while every device sits on the PDK default -- scripts/sch_parameter_integrity_check.py
# fails it, scripts/sch3_connectivity_check.py does not, and only running both is a check).
#
# The defaults handed to the gate are the 3.3 V family's own (350n/350n, measured in
# skill/sch3_cdf_probe.il and re-read off the master CDF inside every readback log). The gate
# refuses to run if those two facts disagree, so a copy-paste of n18's 180n/220n cannot silently
# disable the default-fall-back detector.
#
# Usage: bash scripts/sch3_verify.sh <readback.log> [out-prefix]
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
LOG="${1:?usage: sch3_verify.sh <readback.log> [out-prefix]}"
OUTP="${2:-results}"
[ -r "$LOG" ] || { echo "REFUSE: readback log unreadable: $LOG"; exit 9; }

GOLDEN_SINK="$ROOT/results/data_driver_golden_data_sink_1ch.csv"
GOLDEN_BIAS="$ROOT/results/data_driver_golden_data_bias_ref.csv"
GOLDEN_ALL="$ROOT/results/data_driver_golden_devices.csv"
NETMAP="$ROOT/results/data_driver_net_rename_map.csv"
for f in "$GOLDEN_SINK" "$GOLDEN_BIAS" "$GOLDEN_ALL" "$NETMAP"; do
  [ -r "$f" ] || { echo "REFUSE: missing $f -- run scripts/sch3_golden_extract.py first"; exit 9; }
done

TMPD="$(mktemp -d "${TMPDIR:-/tmp}/sch3_verify_XXXXXX")"
trap 'rm -rf "$TMPD"' EXIT

# the Cadence log prefixes every echoed line with "\o "; strip it once so the field positions below
# are deterministic
sed -e 's/^\\o //' "$LOG" > "$TMPD/clean.log"

# split into one file per cellview, keeping that cell's RD-ROW / RD-NETPIN / RD-NET / RD3-MPARAM
# lines (the RD-CELL line itself is kept too so the counters travel with their section)
awk -v dir="$TMPD" '
  /RD-CELL/ { name=$2; sub(/^[^/]*\//, "", name); gsub(/"/, "", name); cell=name;
              f = dir "/rd_" cell ".log"; print > f; next }
  cell != "" && (/RD-ROW/ || /RD-NETPIN/ || /RD-NET / || /RD3-MPARAM/) {
      print >> (dir "/rd_" cell ".log") }
' "$TMPD/clean.log"
for f in "$TMPD"/rd_*.log; do
  [ -e "$f" ] || { echo "REFUSE: the readback log has no RD-CELL sections"; exit 9; }
done

rc_total=0
run_gate() {   # $1 cell  $2 golden  $3 expect-mos  $4 expect-pins
  local cell="$1" golden="$2" nmos="$3" pins="$4"
  local rd="$TMPD/rd_${cell}.log"
  if [ ! -e "$rd" ]; then
    echo "MISMATCH: no readback section for $cell"
    rc_total=1
    return
  fi
  echo "===== gate: $cell ====="
  python "$HERE/sch_parameter_integrity_check.py" \
      --golden "$golden" --readback "$rd" \
      --out "$OUTP/${cell}_readback_check.csv" \
      --expect-mos "$nmos" --expect-pins "$pins" \
      --pdk-default-l 350n --pdk-default-w 350n --expect-lib smic18mmrf || rc_total=1
}

run_gate data_sink_1ch  "$GOLDEN_SINK" 4  DATA_EN,DATA_EN_B,VBIAS_SHARED,VCAS,DATA_OUT,VSS
run_gate data_bias_ref  "$GOLDEN_BIAS" 1  VBIAS_SHARED,VSS

echo "===== connectivity: both cells against the accepted deck ====="
python "$HERE/sch3_connectivity_check.py" --readback "$LOG" --golden "$GOLDEN_ALL" \
    --netmap "$NETMAP" --out "$OUTP/data_driver_schematic_connectivity.csv" || rc_total=1

# one device table for the reviewer: the per-cell gate tables, with the cellview each row belongs to
{
  echo "cell,$(head -1 "$OUTP/data_sink_1ch_readback_check.csv")"
  tail -n +2 "$OUTP/data_sink_1ch_readback_check.csv" | sed 's/^/data_sink_1ch,/'
  tail -n +2 "$OUTP/data_bias_ref_readback_check.csv" | sed 's/^/data_bias_ref,/'
} > "$OUTP/data_driver_schematic_devices.csv"
echo "DEVICE_TABLE: $OUTP/data_driver_schematic_devices.csv rows=$(( $(wc -l < "$OUTP/data_driver_schematic_devices.csv") - 1 ))"

echo "SCH3_VERIFY: $([ $rc_total -eq 0 ] && echo PASS || echo FAIL)"
exit $rc_total
