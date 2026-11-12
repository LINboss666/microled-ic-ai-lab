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
MIN_ASSERTS="${MIN_ASSERTS:-14}"
SRC="$COURSE_ROOT/coursework/microled_sim"

case "$SCEN" in
    RESET_FAULT) MIN_ASSERTS="${MIN_ASSERTS:-19}" ;;
    TIMEBASE)    MIN_ASSERTS="${MIN_ASSERTS:-14}" ;;
    BOUNDARY)    MIN_ASSERTS="${MIN_ASSERTS:-8}"  ;;
esac

mkdir -p "$RUN_DIR" || exit 9
cd "$RUN_DIR" || exit 9

RESTORE="$RUN_DIR/src"
mkdir -p "$RESTORE" || exit 9
for n in rtl/tcon_timebase.v rtl/tcon_slot_seq.v rtl/tcon_top.v tb/tcon_t1_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"

echo "=== TCON_T1_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "SCEN=$SCEN  MIN_ASSERTS=$MIN_ASSERTS"
echo "RUN_DIR=$RUN_DIR"

rm -rf work
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/tcon_timebase.v" \
    "$RESTORE/tcon_slot_seq.v" \
    "$RESTORE/tcon_top.v" \
    "$RESTORE/tcon_t1_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

vsim -c -do "run -all; quit -f" work.tcon_t1_tb +SCEN="$SCEN" > 03_vsim.stdout 2>&1
VSIM_RC=$?
echo "VSIM_RC=$VSIM_RC"
cat 03_vsim.stdout

CHECKER="$COURSE_ROOT/coursework/microled_sim/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T1_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
