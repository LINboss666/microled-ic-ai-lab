#!/bin/bash
# sc1_s2_r2d.sh -- SCAN-1 R2D entry point for the new S2 decks.
#
#   bash scripts/sc1_s2_r2d.sh                                  # default: generate + static gate
#   RUN=1 bash scripts/sc1_s2_r2d.sh                            # refuses: needs an auth flag
#   RUN=1 QODER_SIM_AUTHORISED=1 bash scripts/sc1_s2_r2d.sh    # reserved for a future session
#
# "Static" here means tb_preflight.sh with PREFLIGHT_STATIC_PROBE=1: it stops after the structural
# supply/rail gates, exits 7 and prints CIRCUIT_VERDICT: NOT_RUN. That is the only validation this
# round performs. The user has paused C2MOS, PDK and all real-circuit simulation, so RUN=1 alone must
# not start anything; it also needs an explicit QODER_SIM_AUTHORISED=1, and R2D implements no
# execution path at all -- it stops with a message naming the future sequence.
set -u
PROJ=${PROJ:-/root/microled_ai_project}
cd "$PROJ" || { echo "HARNESS_ERROR: cannot cd $PROJ"; exit 8; }

D="$PROJ/cadence_work/sc1_sim/r2d"
GEN="$PROJ/scripts/sc1_s2_r2d_gen.py"
PF="$PROJ/scripts/tb_preflight.sh"
RUNNER="$PROJ/scripts/sc1_r2d_static_run.py"
INDEX="$D/sc1_r2d_deck_index.csv"
CSV="$PROJ/results/evidence/sc1_r2d_static_matrix.csv"
RUN=${RUN:-0}
AUTH=${QODER_SIM_AUTHORISED:-0}

if [ "$RUN" = "1" ]; then
  if [ "$AUTH" != "1" ]; then
    echo "S2_R2D_RUN_BLOCKED: RUN=1 also requires QODER_SIM_AUTHORISED=1; the user pause on real"
    echo "  circuit simulation is still in force. Nothing was simulated."
    exit 5
  fi
  echo "S2_R2D_RUN_NOT_IMPLEMENTED: R2D prepared decks and the static gate only. The execution"
  echo "  sequence to run after authorisation is listed in reports/scan_driver_r2d_static_review.md."
  exit 5
fi

python "$GEN" --outdir "$D" || { echo "S2_R2D: FAIL (generator)"; exit 6; }
[ -r "$INDEX" ] || { echo "HARNESS_ERROR: index $INDEX not written"; exit 8; }
[ -r "$RUNNER" ] || { echo "HARNESS_ERROR: $RUNNER missing"; exit 8; }

echo "=== static gate over the generated matrix (PREFLIGHT_STATIC_PROBE=1, no simulator) ==="
python "$RUNNER" --index "$INDEX" --decks "$D" --preflight "$PF" --out "$CSV"
rc=$?
[ "$rc" = "0" ] || { echo "S2_R2D: FAIL (static matrix, rc=$rc)"; exit 6; }
echo "S2_R2D_STATIC: PASS -- decks generated, static gate applied, every row CIRCUIT_VERDICT=NOT_RUN"
echo "  decks   : $D"
echo "  index   : $INDEX"
echo "  evidence: $CSV"
exit 0
