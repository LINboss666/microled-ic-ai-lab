#!/usr/bin/env bash
# T3 runner — Data Driver digital core, single module.
#
#   COURSE_ROOT=<worktree> RUN_DIR=<scratch> [MIN_ASSERTS=n]
#
# Restores the ".txt"-wrapped sources, restores the gray LUT image as a plain
# .hex, compiles data_driver + the accepted oracle data_model + the TB, runs ONE
# phase and delegates PASS/FAIL to the same five-condition checker used by
# T6 / T1 / T2B.
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112_clone}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native/t3}"
SRC="$COURSE_ROOT/coursework/microled_sim"

WALL_LIMIT_S="${WALL_LIMIT_S:-900}"
VCD_LIMIT_MB="${VCD_LIMIT_MB:-120}"

# Assertion floor: T3 set (D01..D41; D11..D15 run once per column, so the
# executed count is 36 + 5*3 = 51). Never lower it.
FLOOR=51

SRC_TB="$SRC/tb/tcon_t3_tb.sv.txt"
TOTAL=$(grep -c 'chk("' "$SRC_TB")
TOTAL=$(( TOTAL + $(grep -c 'chk(\$sformatf' "$SRC_TB") * 3 ))
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
for n in rtl/data_driver.v rtl/data_model.v tb/tcon_t3_tb.sv; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
cp "$SRC/t3b/GRAY_LUT_DEFAULT.hex.txt" "$RUN_DIR/t3_lut.hex" || exit 9
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"
echo "--- source SHA-256 (identity of what is simulated) ---"
( cd "$RESTORE" && sha256sum * ) | tee 00_source_sha256.txt
sha256sum t3_lut.hex | tee -a 00_source_sha256.txt

echo "--- expected quantities (printed BEFORE the run, so it cannot be fitted) ---"
echo "EXPECT asserts=$TOTAL floor=$FLOOR"
echo "EXPECT phase2: 3 columns x 384 bytes, display bank == oracle bank"
echo "EXPECT phase3: 384 channels, on-time == LUT effective width, black=0, full=64"
echo "EXPECT phase4: 383-byte column dropped (valid=0), 385-byte column dropped + err[1]"
echo "EXPECT phase5: ch_en==0 within the same cycle as fault_n=0"

echo "=== TCON_T3_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "MIN_ASSERTS=$MIN_ASSERTS (floor $FLOOR)"
echo "WALL_LIMIT_S=$WALL_LIMIT_S  VCD_LIMIT_MB=$VCD_LIMIT_MB"
echo "RUN_DIR=$RUN_DIR"

rm -rf work t3.vcd
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"

vlog -sv \
    "$RESTORE/data_driver.v" \
    "$RESTORE/data_model.v" \
    "$RESTORE/tcon_t3_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

T0=$(date +%s)
timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t3_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
T1=$(date +%s)
echo "VSIM_RC=$VSIM_RC  ELAPSED_S=$((T1 - T0))"
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"; echo "RUNNER_EXIT=124"; exit 124
fi
cat 03_vsim.stdout

if [ -f t3.vcd ]; then
    VCD_MB=$(( $(stat -c%s t3.vcd) / 1048576 ))
    echo "VCD_MB=$VCD_MB  VCD_BYTES=$(stat -c%s t3.vcd)"
    if [ "$VCD_MB" -gt "$VCD_LIMIT_MB" ]; then
        echo "RUNNER_VERDICT=VCD_TOO_LARGE"; echo "RUNNER_EXIT=8"; exit 8
    fi
fi

CHECKER="$SRC/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T3_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
