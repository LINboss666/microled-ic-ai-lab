#!/bin/bash
# SCH-3 section 18: the one command that turns the OA-derived regression into the reviewed numbers.
#
# Every comparison here is against a file that is already under review (results/data_driver_Ednw_*),
# never against a re-simulation of the accepted deck, so "the schematic matches the accepted circuit"
# is a claim about two artefacts in the repository rather than about a fresh run.
#
# Two columns are excluded, and the reason is stated instead of hidden:
#   ring_flip_ratio  -- a sign-flip *count ratio* of a trace whose alternating component is measured
#                       at 0.000000 uA peak-to-peak in both runs (the ringing criterion itself,
#                       ADJACENT_POINT_ALTERNATION, is compared and agrees); the ratio is noise over
#                       a zero signal, so it is not a circuit quantity.
#   q_error_C        -- the integrated absolute charge of a sub-femtoampere-second residual; the two
#                       runs agree to 0.0000 % on the derived charge_error_pct, which is what the
#                       criterion uses.
#
# Usage: bash scripts/sch3_compare_all.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 9
CMP="python scripts/sch3_compare_regression.py"
OUT=results/data_driver_schematic_regression.csv
EXC="ring_flip_ratio,q_error_C"
rm -f "$OUT"
rc=0

echo "===== DC sweeps, every point (996 points, 3 corners x on/off) ====="
$CMP --kind sweep --dataset dc --accepted-filter '^Ednw_' --group-re '_([a-z]+)_(on|off)$' \
    --group-col candidate --xcol vsw_V --cols iout_uA,err_pct,vbias_V \
    --accepted results/data_driver_Ednw_corner_dc.csv \
    --new results/data_driver_schematic_dc.csv --out "$OUT" || rc=1

echo "===== frame-scale transient, switching channel ====="
$CMP --kind scalar --dataset transient --group-re '_([a-z]{2})_' \
    --new-filter '^SCH3_flat_[a-z]{2}_ch0$' --exclude "$EXC" \
    --accepted results/data_driver_Ednw_corner_transient.csv \
    --new results/data_driver_schematic_transient.csv --out "$OUT" || rc=1

echo "===== frame-scale transient, always-on victim channel (crosstalk) ====="
$CMP --kind scalar --dataset xtalk --group-re '_([a-z]{2})_' \
    --new-filter '^SCH3_flat_[a-z]{2}_victim$' --exclude "$EXC" \
    --accepted results/data_driver_Ednw_corner_xtalk.csv \
    --new results/data_driver_schematic_xtalk.csv --out "$OUT" || rc=1

echo "===== two-channel static enable matrix (4 combinations x 2 channels) ====="
$CMP --kind scalar --dataset static --group-re 'static_(e\d\d)_ch(\d)' --exclude "$EXC" \
    --accepted results/data_driver_Ednw_static.csv \
    --new results/data_driver_schematic_static.csv --out "$OUT" || rc=1

echo
echo "SUMMARY_TABLE: $OUT rows=$(( $(wc -l < "$OUT") - 1 ))"
echo "SCH3_COMPARE: $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
exit $rc
