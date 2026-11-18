#!/usr/bin/env bash
# T5 runner — five REAL chips (1 TCON + 2 Data + 2 Scan), T5-B.
#
#   COURSE_ROOT=<worktree> RUN_DIR=<scratch> [MIN_ASSERTS=n]
#
# Restores the ".txt"-wrapped sources, restores the gray LUT image as a plain
# .hex, compiles the five accepted RTL modules + the two pin monitors + the
# integration shell + the TB, runs ONE scenario and delegates PASS/FAIL to the
# same five-condition checker used by T1 / T2B / T3 / T4.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112_clone}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native/t5}"
SRC="$COURSE_ROOT/coursework/microled_sim"

WALL_LIMIT_S="${WALL_LIMIT_S:-5400}"      # one frame is ~10.7 ms of simulated time
VCD_LIMIT_MB="${VCD_LIMIT_MB:-200}"

# Assertion floor: the frozen T5-B set (D01..D56). Never lower it.
FLOOR=56

SRC_TB="$SRC/tb/tcon_t5_tb.sv.txt"
TOTAL=$(grep -c 'chk("' "$SRC_TB")
if [ "$TOTAL" -lt "$FLOOR" ]; then
    echo "RUNNER_VERDICT=TB_HAS_FEWER_CHECKS_THAN_FLOOR ($TOTAL < $FLOOR)"
    echo "RUNNER_EXIT=9"; exit 9
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
for n in rtl/tcon_timebase.v rtl/tcon_video_rx.v rtl/tcon_col_bank.v \
         rtl/tcon_slot_seq.v rtl/tcon_data_tx.v rtl/tcon_top.v \
         rtl/data_driver.v rtl/scan_driver.v \
         rtl/data_pin_mon.v rtl/scan_pin_mon.v \
         tb/t5_five_chip_shell.sv tb/tcon_t5_tb.sv ; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
cp "$SRC/t3b/GRAY_LUT_DEFAULT.hex.txt" "$RUN_DIR/t5_lut_a.hex" || exit 9
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"
echo "--- source SHA-256 (identity of what is simulated) ---"
( cd "$RESTORE" && sha256sum * ) | tee 00_source_sha256.txt
sha256sum t5_lut_a.hex | tee -a 00_source_sha256.txt

echo "--- expected quantities (printed BEFORE the run, so they cannot be fitted) ---"
echo "EXPECT asserts=$TOTAL floor=$FLOOR"
echo "EXPECT phase B: 1027 slots, ~1025 display windows, both Data ports 384 B/window"
echo "EXPECT phase B: every window: Scan one-hot == Data0 tag == Data1 tag == slot-2 column"
echo "EXPECT phase B: 768 B/window byte-exact, LUT map + PAM exact, PWM width == LUT width"
echo "EXPECT phase C: LUT commit lands on the LATCH rising edge, 1 dark window, then B"
echo "EXPECT phase D: FAULT 400 edges, bank never flips, cmt_pend held, 768 ch_en == 0"
echo "EXPECT phase F: 767-byte column -> err[0], latched FAULT, no auto recovery"

echo "=== TCON_T5_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "MIN_ASSERTS=$MIN_ASSERTS (floor $FLOOR)"
echo "WALL_LIMIT_S=$WALL_LIMIT_S  VCD_LIMIT_MB=$VCD_LIMIT_MB"
echo "RUN_DIR=$RUN_DIR"

rm -rf work t5.vcd
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/tcon_timebase.v" \
    "$RESTORE/tcon_video_rx.v" \
    "$RESTORE/tcon_col_bank.v" \
    "$RESTORE/tcon_slot_seq.v" \
    "$RESTORE/tcon_data_tx.v" \
    "$RESTORE/tcon_top.v" \
    "$RESTORE/data_driver.v" \
    "$RESTORE/scan_driver.v" \
    "$RESTORE/data_pin_mon.v" \
    "$RESTORE/scan_pin_mon.v" \
    "$RESTORE/t5_five_chip_shell.sv" \
    "$RESTORE/tcon_t5_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

T0=$(date +%s)
timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t5_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
T1=$(date +%s)
echo "VSIM_RC=$VSIM_RC  ELAPSED_S=$((T1 - T0))"
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"; echo "RUNNER_EXIT=124"; exit 124
fi
cat 03_vsim.stdout

if [ -f t5.vcd ]; then
    VCD_MB=$(( $(stat -c%s t5.vcd) / 1048576 ))
    echo "VCD_MB=$VCD_MB  VCD_BYTES=$(stat -c%s t5.vcd)"
    if [ "$VCD_MB" -gt "$VCD_LIMIT_MB" ]; then
        echo "RUNNER_VERDICT=VCD_TOO_LARGE"; echo "RUNNER_EXIT=8"; exit 8
    fi
fi
if [ -f t5_column_ledger.csv ]; then
    echo "LEDGER_ROWS=$(( $(wc -l < t5_column_ledger.csv) - 1 ))"
fi

CHECKER="$SRC/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T5_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
