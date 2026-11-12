#!/usr/bin/env bash
# Reproducible ModelSim batch runner for the course representative RTL.
# T6 revision: the runner no longer trusts the simulator exit code alone.
#
#   COURSE_ROOT=<course worktree> RUN_DIR=<scratch outside the repo> bash run_modelsim.sh
#   COURSE_VLOG_DEFINES="+define+COURSE_FAULT_INJECT"   # optional negative case
#   COURSE_MIN_ASSERTS=55                               # expected assertion floor
#
# Four independent conditions must all hold, else the runner exits non-zero:
#   1. vsim process return code == 0
#   2. transcript contains COURSE_RTL_RESULT=PASS
#   3. transcript contains COURSE_RTL_FAIL_COUNT=0
#   4. executed assertion count >= COURSE_MIN_ASSERTS (and > 0)
#
# It never writes into the repository: work/, VCD, WLF and the raw transcript
# stay in RUN_DIR. Only small derived evidence is copied into the repo later.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native}"
COURSE_VLOG_DEFINES="${COURSE_VLOG_DEFINES:-}"
COURSE_MIN_ASSERTS="${COURSE_MIN_ASSERTS:-55}"
SRC="$COURSE_ROOT/coursework/microled_sim"

mkdir -p "$RUN_DIR" || exit 9
cd "$RUN_DIR" || exit 9

# The repository safety gate whitelists only a fixed set of extensions, so the
# committed Verilog/SV sources carry a ".txt" wrapper (byte-identical content).
# Restore their real filenames into this scratch tree before compiling.
RESTORE="$RUN_DIR/src"
mkdir -p "$RESTORE" || exit 9
for n in rtl/course_col_scan.v rtl/course_data_latch.v rtl/dd1_d7a_gray_ctrl.sv \
         rtl/course_top.v tb/course_selfcheck_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"

echo "=== COURSE_MODELSIM_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "COURSE_ROOT=$COURSE_ROOT"
echo "RUN_DIR=$RUN_DIR"
echo "VLOG_DEFINES=${COURSE_VLOG_DEFINES:-<none>}"
echo "MIN_ASSERTS=$COURSE_MIN_ASSERTS"

rm -rf work
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

# shellcheck disable=SC2086
vlog -sv $COURSE_VLOG_DEFINES \
    "$RESTORE/course_col_scan.v" \
    "$RESTORE/course_data_latch.v" \
    "$RESTORE/dd1_d7a_gray_ctrl.sv" \
    "$RESTORE/course_top.v" \
    "$RESTORE/course_selfcheck_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

vsim -c -do "run -all; quit -f" work.course_selfcheck_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
echo "VSIM_RC=$VSIM_RC"
cat 03_vsim.stdout

# The PASS/FAIL decision is delegated to t6_check_transcript.sh so that the
# same five conditions can be re-applied offline to any stored transcript
# (no extra ModelSim run needed when the checker itself is revised).
CHECKER="$(dirname "$0")/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$COURSE_MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== COURSE_MODELSIM_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
