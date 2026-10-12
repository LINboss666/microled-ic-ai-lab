#!/bin/bash
# sc1_s2_r2d.sh -- SCAN-1 R2D/R2D1 entry point for the new S2 decks.
#
#   bash scripts/sc1_s2_r2d.sh                                  # default: generate + offline checks
#   RUN=1 bash scripts/sc1_s2_r2d.sh                            # refuses: needs an auth flag
#   RUN=1 QODER_SIM_AUTHORISED=1 bash scripts/sc1_s2_r2d.sh    # still refuses (no execution path)
#
# "Static" here means tb_preflight.sh with PREFLIGHT_STATIC_PROBE=1: it stops after the structural
# supply/rail gates, exits 7 and prints CIRCUIT_VERDICT: NOT_RUN. That is the only gate this round
# performs, next to the offline PWL envelope audit of the generator. The user has paused C2MOS, PDK and
# all real-circuit simulation, so RUN=1 alone must not start anything; it also needs an explicit
# QODER_SIM_AUTHORISED=1, and this entry still implements no execution path at all -- it stops with a
# message naming the future sequence.
#
# Paths passed to the static runner are ABSOLUTE on purpose: tb_preflight.sh refuses a netlist it
# cannot prove is inside $PROJ, and a relative --decks argument produced PREFLIGHT_STAGE=inputs /
# netlist_outside_project with exit 9 for all 37 decks (measured), which is a harness fault and was
# correctly never scored as a circuit result.
set -u
PROJ=${PROJ:-/root/microled_ai_project}
cd "$PROJ" || { echo "HARNESS_ERROR: cannot cd $PROJ"; exit 8; }

D="$PROJ/cadence_work/sc1_sim/r2d1_decks"
GEN="$PROJ/scripts/sc1_s2_r2d_gen.py"
PF="$PROJ/scripts/tb_preflight.sh"
RUNNER="$PROJ/scripts/sc1_r2d_static_run.py"
AUDIT="$PROJ/scripts/sc1_r2d1_pwl_audit.py"
PROBE="$PROJ/scripts/sc1_r2d1_iprobe_probe.py"
INDEX="$D/sc1_r2d1_deck_index.csv"
EV="$PROJ/results/evidence"
CSV="$EV/sc1_r2d1_static_matrix.csv"
AUDIT_CSV="$EV/sc1_r2d1_pwl_audit.csv"
PROBE_CSV="$EV/sc1_r2d1_iprobe_static_probe.csv"
RUN=${RUN:-0}
AUTH=${QODER_SIM_AUTHORISED:-0}

if [ "$RUN" = "1" ]; then
  if [ "$AUTH" != "1" ]; then
    echo "S2_R2D_RUN_BLOCKED: RUN=1 also requires QODER_SIM_AUTHORISED=1; the user pause on real"
    echo "  circuit simulation is still in force. Nothing was simulated."
    exit 5
  fi
  echo "S2_R2D_RUN_NOT_IMPLEMENTED: this round prepared decks and offline checks only. The execution"
  echo "  sequence to run after authorisation is listed in reports/scan_driver_r2d_static_review.md."
  exit 5
fi

for f in "$GEN" "$RUNNER" "$AUDIT" "$PROBE" "$PF"; do
  [ -r "$f" ] || { echo "HARNESS_ERROR: missing $f"; exit 8; }
done
mkdir -p "$EV"

python "$GEN" --outdir "$D" || { echo "S2_R2D: FAIL (generator)"; exit 6; }
[ -r "$INDEX" ] || { echo "HARNESS_ERROR: index $INDEX not written"; exit 8; }

echo "=== offline PWL envelope audit of the generator (no simulator) ==="
python "$AUDIT" --out "$AUDIT_CSV" || { echo "S2_R2D: FAIL (PWL envelope audit)"; exit 6; }

echo "=== static gate over the generated matrix (PREFLIGHT_STATIC_PROBE=1, no simulator) ==="
python "$RUNNER" --index "$INDEX" --decks "$D" --preflight "$PF" --out "$CSV"
rc=$?
[ "$rc" = "0" ] || { echo "S2_R2D: FAIL (static matrix, rc=$rc)"; exit 6; }

echo "=== measured question for B3: may a rail carry a series iprobe? (static probe only) ==="
python "$PROBE" --scratch "$PROJ/cadence_work/sc1_sim/r2d1_iprobe" --preflight "$PF" \
  --out "$PROBE_CSV" || { echo "S2_R2D: FAIL (iprobe probe)"; exit 6; }

echo "S2_R2D1_STATIC: PASS -- decks generated, envelopes audited, static gate applied, every row"
echo "  CIRCUIT_VERDICT=NOT_RUN and simulator_called=no"
echo "  decks   : $D"
echo "  index   : $INDEX"
echo "  evidence: $CSV ; $AUDIT_CSV ; $PROBE_CSV"
exit 0
