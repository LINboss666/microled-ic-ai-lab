#!/usr/bin/env bash
# T4 runner — TWO Scan Driver chips, 512-way each (T4 digital core).
#
#   COURSE_ROOT=<worktree> RUN_DIR=<scratch> [MIN_ASSERTS=n]
#
# Restores the ".txt"-wrapped sources, compiles scan_driver + the independent
# pin oracle scan_exp + the accepted pin monitor scan_pin_mon + the TB, runs ONE
# phase, and delegates PASS/FAIL to the same five-condition checker used by
# T6 / T1 / T2B / T3.
#
# Budget: the task book allows at most 2 formal vsim runs for T4. This script
# runs exactly ONE. A compile-only invocation (vlog without vsim) is a
# pre-check and does not consume the budget.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112_clone}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native/t4}"
SRC="$COURSE_ROOT/coursework/microled_sim"

WALL_LIMIT_S="${WALL_LIMIT_S:-900}"
VCD_LIMIT_MB="${VCD_LIMIT_MB:-40}"

# Assertion floor: the T4 set is D01..D42, every check executed exactly once.
FLOOR=42

SRC_TB="$SRC/tb/tcon_t4_tb.sv.txt"
TOTAL=$(grep -c 'chk("' "$SRC_TB")
if [ "$TOTAL" -lt "$FLOOR" ]; then
    echo "RUNNER_VERDICT=TB_HAS_FEWER_CHECKS_THAN_FLOOR ($TOTAL < $FLOOR)"
    echo "RUNNER_EXIT=9"
    exit 9
fi

MIN_ASSERTS="${MIN_ASSERTS:-$FLOOR}"
case "$MIN_ASSERTS" in *[!0-9]*)
    echo "RUNNER_VERDICT=BAD_MIN_ASSERTS_NOT_INTEGER"; echo "RUNNER_EXIT=9"; exit 9 ;;
esac
if [ "$MIN_ASSERTS" -lt "$FLOOR" ]; then
    echo "RUNNER_VERDICT=BAD_MIN_ASSERTS_BELOW_FLOOR_$FLOOR"; echo "RUNNER_EXIT=9"; exit 9
fi

mkdir -p "$RUN_DIR" || exit 9
cd "$RUN_DIR" || exit 9
RESTORE="$RUN_DIR/src"
mkdir -p "$RESTORE" || exit 9
for n in rtl/scan_driver.v rtl/scan_exp.v rtl/scan_pin_mon.v tb/tcon_t4_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"
echo "--- source SHA-256 (identity of what is simulated) ---"
( cd "$RESTORE" && sha256sum * ) | tee 00_source_sha256.txt

echo "--- expected quantities (printed BEFORE the run, so it cannot be fitted) ---"
echo "EXPECT asserts=$TOTAL floor=$FLOOR"
echo "EXPECT sweep: 1024 global columns, 512 selections per chip, every address compared bit-exactly"
echo "EXPECT display windows: popcount({chip1,chip0}) == 1; BLANK/FAULT/RESET windows: == 0"
echo "EXPECT one deliberate illegal strobe outside BLANK: both chips flagged, global off"
echo "EXPECT latch on the REAL scan_stb rise, not on the 100 MHz reference clock"

echo "=== TCON_T4_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "MIN_ASSERTS=$MIN_ASSERTS (floor $FLOOR)"
echo "WALL_LIMIT_S=$WALL_LIMIT_S  VCD_LIMIT_MB=$VCD_LIMIT_MB"
echo "RUN_DIR=$RUN_DIR"

rm -rf work t4.vcd
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/scan_driver.v" \
    "$RESTORE/scan_exp.v" \
    "$RESTORE/scan_pin_mon.v" \
    "$RESTORE/tcon_t4_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

T0=$(date +%s)
timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t4_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
T1=$(date +%s)
echo "VSIM_RC=$VSIM_RC  ELAPSED_S=$((T1 - T0))"
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"; echo "RUNNER_EXIT=124"; exit 124
fi
cat 03_vsim.stdout

if [ -f t4.vcd ]; then
    VCD_MB=$(( $(stat -c%s t4.vcd) / 1048576 ))
    echo "VCD_MB=$VCD_MB  VCD_BYTES=$(stat -c%s t4.vcd)"
    if [ "$VCD_MB" -gt "$VCD_LIMIT_MB" ]; then
        echo "RUNNER_VERDICT=VCD_TOO_LARGE"; echo "RUNNER_EXIT=8"; exit 8
    fi
fi

CHECKER="$SRC/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T4_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
