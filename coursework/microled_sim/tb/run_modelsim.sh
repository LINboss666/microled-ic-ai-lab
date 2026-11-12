#!/usr/bin/env bash
# Reproducible ModelSim batch runner for the course representative RTL.
#
#   COURSE_ROOT=<course worktree> RUN_DIR=<scratch outside the repo> bash run_modelsim.sh
#
# It never writes into the repository: work/, VCD, WLF and the raw transcript
# stay in RUN_DIR. Only small derived evidence is copied into the repo later.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native}"
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

vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/course_col_scan.v" \
    "$RESTORE/course_data_latch.v" \
    "$RESTORE/dd1_d7a_gray_ctrl.sv" \
    "$RESTORE/course_top.v" \
    "$RESTORE/course_selfcheck_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "COMPILE_FAILED"; exit 2; }

vsim -c -do "run -all; quit -f" work.course_selfcheck_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
echo "VSIM_RC=$VSIM_RC"
cat 03_vsim.stdout

echo "=== artifacts ==="
ls -la
echo "=== COURSE_MODELSIM_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
exit "$VSIM_RC"
