#!/usr/bin/env bash
# TCON T2A / T2AR runner — one phase per run, hard wall-clock timeout, VCD capped.
#
#   COURSE_ROOT=<worktree> RUN_DIR=<scratch> [MIN_ASSERTS=n]
#
# Restores the ".txt"-wrapped sources into scratch with their real extensions,
# compiles the whole T2A RTL + TB, runs ONE phase and delegates the PASS/FAIL
# decision to the same five-condition checker used by T6/T1.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native/t2a}"
SRC="$COURSE_ROOT/coursework/microled_sim"

WALL_LIMIT_S="${WALL_LIMIT_S:-600}"
VCD_LIMIT_MB="${VCD_LIMIT_MB:-60}"

# Assertion floor: the single "ALL" phase covers both the T2A regression set and
# the T2AR boundary set, 49 checks (T1-T8, C1-C5, E1-E11, R1-R4, W1, S1-S2,
# X1-X18). Never lower it.
FLOOR=49

# the TB must still contain at least as many checks as the declared floor
SRC_TB="$SRC/tb/tcon_t2a_tb.sv.txt"
TOTAL=$(grep -c 'chk("' "$SRC_TB")
if [ "$TOTAL" -lt "$FLOOR" ]; then
    echo "RUNNER_VERDICT=TB_HAS_FEWER_CHECKS_THAN_FLOOR ($TOTAL < $FLOOR)"
    echo "RUNNER_EXIT=9"
    exit 9
fi

MIN_ASSERTS="${MIN_ASSERTS:-$FLOOR}"
case "$MIN_ASSERTS" in *[!0-9]*)
    echo "RUNNER_VERDICT=BAD_MIN_ASSERTS_NOT_INTEGER"
    echo "RUNNER_EXIT=9"
    exit 9
    ;;
esac
if [ "$MIN_ASSERTS" -lt "$FLOOR" ]; then
    echo "RUNNER_VERDICT=BAD_MIN_ASSERTS_BELOW_FLOOR_$FLOOR"
    echo "RUNNER_EXIT=9"
    exit 9
fi

mkdir -p "$RUN_DIR" || exit 9
cd "$RUN_DIR" || exit 9

RESTORE="$RUN_DIR/src"
mkdir -p "$RESTORE" || exit 9
for n in rtl/tcon_timebase.v rtl/tcon_slot_seq.v rtl/tcon_video_rx.v \
         rtl/tcon_col_bank.v rtl/tcon_data_tx.v rtl/tcon_top.v \
         tb/tcon_t2a_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"

echo "=== TCON_T2A_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "MIN_ASSERTS=$MIN_ASSERTS (floor $FLOOR, TB has $TOTAL checks)"
echo "WALL_LIMIT_S=$WALL_LIMIT_S  VCD_LIMIT_MB=$VCD_LIMIT_MB"
echo "RUN_DIR=$RUN_DIR"

rm -rf work tcon_t2a.vcd
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/tcon_timebase.v" \
    "$RESTORE/tcon_slot_seq.v" \
    "$RESTORE/tcon_video_rx.v" \
    "$RESTORE/tcon_col_bank.v" \
    "$RESTORE/tcon_data_tx.v" \
    "$RESTORE/tcon_top.v" \
    "$RESTORE/tcon_t2a_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

T0=$(date +%s)
timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t2a_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
T1=$(date +%s)
echo "VSIM_RC=$VSIM_RC  ELAPSED_S=$((T1 - T0))"
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"
    echo "RUNNER_EXIT=124"
    exit 124
fi
cat 03_vsim.stdout

if [ -f tcon_t2a.vcd ]; then
    VCD_MB=$(( $(stat -c%s tcon_t2a.vcd) / 1048576 ))
    echo "VCD_MB=$VCD_MB  VCD_BYTES=$(stat -c%s tcon_t2a.vcd)"
    if [ "$VCD_MB" -gt "$VCD_LIMIT_MB" ]; then
        echo "RUNNER_VERDICT=VCD_TOO_LARGE"
        echo "RUNNER_EXIT=8"
        exit 8
    fi
fi

CHECKER="$SRC/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T2A_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
