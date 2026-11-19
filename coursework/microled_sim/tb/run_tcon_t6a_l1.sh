#!/usr/bin/env bash
# T6-A **L1** runner — the rev2 suite PLUS Phase S (P0-D safety).
# PREPARED ONLY: never executed in the P0-D round (zero ModelSim).
#
#   COURSE_ROOT=<worktree> RUN_DIR=<scratch> [MIN_ASSERTS=n]
set -uo pipefail

COURSE_ROOT="${COURSE_ROOT:-D:/ic617_course_sim_20261112_clone}"
RUN_DIR="${RUN_DIR:-D:/ic617_course_sim_20261112_native/t6a_l1}"
SRC="$COURSE_ROOT/coursework/microled_sim"

WALL_LIMIT_S="${WALL_LIMIT_S:-900}"

FLOOR="86"   # 57 (rev2) + 20 (Phase S) + 8 (P0-F) + 1 (P0-F2 E20a)
SRC_TB="$SRC/tb/tcon_t6a_l1_tb.sv.txt"
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
for n in rtl/spi_frame.v rtl/tcon_spi_regs.v rtl/tcon_spi_top.v tb/tcon_t6a_l1_tb.sv ; do
    cp "$SRC/$n.txt" "$RESTORE/$(basename "$n")" || exit 9
done
echo "RESTORED_SOURCES=$(ls -1 "$RESTORE" | wc -l)"
echo "--- source SHA-256 (identity of what is simulated) ---"
( cd "$RESTORE" && sha256sum * ) | tee 00_source_sha256.txt

echo "--- expected quantities (printed BEFORE the run) ---"
echo "EXPECT asserts=$TOTAL floor=$FLOOR"
echo "EXPECT Phase S: one 4 ns pulse per capture, zero edges inside every pulse, split_edges=0, resurrections=0"
echo "EXPECT reset: CHIP_ID=0x10 CTRL=0x00000002 STATUS=0x4 WDOG=2 VIDCFG=0x000BFFFF"
echo "EXPECT 48 SCK per frame, MSB first, write commits on CS_n rising only"
echo "EXPECT illegal (misaligned / unimplemented / RO / config-while-EN) -> ERR_REG, no commit"
echo "EXPECT 32-bit readback of every written register, at 10 MHz and 4 MHz"

echo "=== TCON_T6A_RUNNER start $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "MIN_ASSERTS=$MIN_ASSERTS (floor $FLOOR)"
echo "RUN_DIR=$RUN_DIR"

rm -rf work t6a.vcd
vlib work > 01_vlib.log 2>&1
echo "VLIB_RC=$?"
vlog -sv "$RESTORE/spi_frame.v" "$RESTORE/tcon_spi_regs.v" \
        "$RESTORE/tcon_spi_top.v" "$RESTORE/tcon_t6a_l1_tb.sv" > 02_vlog.log 2>&1
VLOG_RC=$?
echo "VLOG_RC=$VLOG_RC"
cat 02_vlog.log
[ "$VLOG_RC" -eq 0 ] || { echo "RUNNER_VERDICT=COMPILE_FAILED"; echo "RUNNER_EXIT=2"; exit 2; }

T0=$(date +%s)
timeout "${WALL_LIMIT_S}s" vsim -c -do "run -all; quit -f" work.tcon_t6a_l1_tb > 03_vsim.stdout 2>&1
VSIM_RC=$?
T1=$(date +%s)
echo "VSIM_RC=$VSIM_RC  ELAPSED_S=$((T1 - T0))"
if [ "$VSIM_RC" -eq 124 ]; then
    echo "RUNNER_VERDICT=WALL_CLOCK_TIMEOUT"; echo "RUNNER_EXIT=124"; exit 124
fi
cat 03_vsim.stdout

CHECKER="$SRC/tb/t6_check_transcript.sh"
bash "$CHECKER" 03_vsim.stdout "$MIN_ASSERTS" "$VSIM_RC" | tee 05_t6_check.txt
RC=${PIPESTATUS[0]}

echo "=== artifacts ==="
ls -la
echo "=== TCON_T6A_RUNNER end $(date '+%Y-%m-%dT%H:%M:%S%z') ==="
echo "RUNNER_EXIT=$RC"
exit "$RC"
