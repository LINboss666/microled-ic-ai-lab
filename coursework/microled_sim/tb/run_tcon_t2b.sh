#!/usr/bin/env bash
# TCON T2B joint runner (V1.3 input + Data x2 / Scan x2 behavioural models).
#
#   COURSE_ROOT=<worktree> RUN_DIR=<scratch> [MIN_ASSERTS=n]
#
# Restores the ".txt"-wrapped sources, compiles the TCON + both models + the TB,
# runs ONE phase and delegates PASS/FAIL to the same five-condition checker used
# by T6 / T1 / T2A.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112_clone}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native/t2b}"
SRC="$COURSE_ROOT/coursework/microled_sim"

WALL_LIMIT_S="${WALL_LIMIT_S:-900}"
VCD_LIMIT_MB="${VCD_LIMIT_MB:-120}"

# Assertion floor: T2B joint set (P01..P51). Never lower it.
FLOOR=51

SRC_TB="$SRC/tb/tcon_t2b_tb.sv.txt"
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
for n in rtl/tcon_timebase.v rtl/tcon_slot_seq.v rtl/tcon_video_rx.v \
         rtl/tcon_col_bank.v rtl/tcon_data_tx.v rtl/tcon_top.v \
         rtl/data_model.v rtl/scan_model.v \
         rtl/data_pin_mon.v rtl/scan_pin_mon.v tb/tcon_t2b_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"
echo "--- source SHA-256 (identity of what is simulated) ---"
( cd "$RESTORE" && sha256sum * ) | tee 00_source_sha256.txt
echo "--- expected quantities (printed BEFORE the run, so it cannot be fitted) ---"
echo "EXPECT asserts=$TOTAL floor=$FLOOR  windows_phase1=10  bytes_per_window=384"
echo "EXPECT phase1: windows=10 bytes_per_window=384 strobes=10 core=9 prech=1 skip=0"
echo "EXPECT phase5(1027 slots): strobes=1026 core=1025 prech=1 skip=0 wraps=1"
echo "EXPECT anti-false-pass assertions: P15,P16,P17,P18,P19,P46,P47,P48,P49,P50,P51"

echo "=== TCON_T2B_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "MIN_ASSERTS=$MIN_ASSERTS (floor $FLOOR, TB has $TOTAL checks)"
echo "WALL_LIMIT_S=$WALL_LIMIT_S  VCD_LIMIT_MB=$VCD_LIMIT_MB"
echo "RUN_DIR=$RUN_DIR"

rm -rf work tcon_t2b.vcd
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/tcon_timebase.v" \
    "$RESTORE/tcon_slot_seq.v" \
    "$RESTORE/tcon_video_rx.v" \
    "$RESTORE/tcon_col_bank.v" \
    "$RESTORE/tcon_data_tx.v" \
    "$RESTORE/tcon_top.v" \
    "$RESTORE/data_model.v" \
    "$RESTORE/scan_model.v" \
    "$RESTORE/data_pin_mon.v" \
    "$RESTORE/scan_pin_mon.v" \
    "$RESTORE/tcon_t2b_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

T0=$(date +%s)
timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t2b_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
T1=$(date +%s)
echo "VSIM_RC=$VSIM_RC  ELAPSED_S=$((T1 - T0))"
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"; echo "RUNNER_EXIT=124"; exit 124
fi
cat 03_vsim.stdout

if [ -f tcon_t2b.vcd ]; then
    VCD_MB=$(( $(stat -c%s tcon_t2b.vcd) / 1048576 ))
    echo "VCD_MB=$VCD_MB  VCD_BYTES=$(stat -c%s tcon_t2b.vcd)"
    if [ "$VCD_MB" -gt "$VCD_LIMIT_MB" ]; then
        echo "RUNNER_VERDICT=VCD_TOO_LARGE"; echo "RUNNER_EXIT=8"; exit 8
    fi
fi

CHECKER="$SRC/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T2B_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
