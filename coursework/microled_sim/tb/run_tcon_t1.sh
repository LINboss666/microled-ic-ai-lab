#!/usr/bin/env bash
# TCON T1 skeleton runner.
#
#   COURSE_ROOT=<course worktree> RUN_DIR=<scratch> SCEN=<name> bash run_tcon_t1.sh
#
# Restores the ".txt"-wrapped sources into scratch with their real extensions,
# compiles the T1 RTL + TB, runs ONE scenario, and delegates the PASS/FAIL
# decision to the same five-condition checker used by T6. The TB itself never
# drives time-base or control outputs; it only observes them.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native}"
SCEN="${SCEN:-RESET_FAULT}"
SRC="$COURSE_ROOT/coursework/microled_sim"
WALL_LIMIT_S="${WALL_LIMIT_S:-900}"

# Assertion floors are resolved by ONE shared, unit-tested function.
# T1R review F1: the previous inline `MIN_ASSERTS="${MIN_ASSERTS:-49}"` made the
# per-scenario case branches dead code, so every scenario silently demanded 49.
# shellcheck source=tb/scen_min_asserts.sh
. "$SRC/tb/scen_min_asserts.sh"

RESOLVED_MIN=$(resolve_min_asserts "$SCEN" "${MIN_ASSERTS:-}")
RESOLVE_RC=$?
echo "SCEN_MIN_RESOLVE=$RESOLVED_MIN rc=$RESOLVE_RC"
if [ "$RESOLVE_RC" -ne 0 ]; then
    echo "RUNNER_VERDICT=BAD_MIN_ASSERTS"
    echo "RUNNER_EXIT=9"
    exit 9
fi
MIN_ASSERTS="$RESOLVED_MIN"

mkdir -p "$RUN_DIR" || exit 9
cd "$RUN_DIR" || exit 9

RESTORE="$RUN_DIR/src"
mkdir -p "$RESTORE" || exit 9
# R04 (T2AR): tcon_top now instantiates the three T2A modules, so the T1
# runner must copy and compile them too - otherwise elaboration fails and the
# 49 T1 assertions are never actually exercised against the current top.
for n in rtl/tcon_timebase.v rtl/tcon_slot_seq.v rtl/tcon_video_rx.v \
         rtl/tcon_col_bank.v rtl/tcon_data_tx.v rtl/tcon_top.v \
         tb/tcon_t1_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"

echo "=== TCON_T1_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "SCEN=$SCEN  MIN_ASSERTS=$MIN_ASSERTS"
echo "RUN_DIR=$RUN_DIR  WALL_LIMIT_S=$WALL_LIMIT_S"

rm -rf work
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/tcon_timebase.v" \
    "$RESTORE/tcon_slot_seq.v" \
    "$RESTORE/tcon_video_rx.v" \
    "$RESTORE/tcon_col_bank.v" \
    "$RESTORE/tcon_data_tx.v" \
    "$RESTORE/tcon_top.v" \
    "$RESTORE/tcon_t1_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t1_tb +SCEN="$SCEN" > 03_vsim.stdout 2>&1
VSIM_RC=$?
echo "VSIM_RC=$VSIM_RC"
cat 03_vsim.stdout
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"
    echo "RUNNER_EXIT=124"
    exit 124
fi

CHECKER="$COURSE_ROOT/coursework/microled_sim/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T1_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
