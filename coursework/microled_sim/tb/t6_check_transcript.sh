#!/usr/bin/env bash
# T6 transcript checker — the authoritative PASS/FAIL decision for the course
# ModelSim runs.
#
#   bash t6_check_transcript.sh <vsim_stdout_file> <min_asserts> <vsim_rc>
#
# Why this exists: on ModelSim ASE 10.5b (win32aloem, 2016.10) a `$fatal` does
# NOT make the process return non-zero when the -do script ends with `quit -f`;
# the shell observes rc=0 even though the transcript records `** Fatal:` and
# `Errors: 1`. Verified empirically in T6 negative run 3. Therefore the exit
# status alone must never be trusted: five independent conditions are checked
# and ANY failure makes this checker exit non-zero.
#
#   CHECK0  transcript has no "** Fatal:" line AND "Errors: 0"
#   CHECK1  vsim process return code == 0
#   CHECK2  transcript contains COURSE_RTL_RESULT=PASS
#   CHECK3  transcript contains COURSE_RTL_FAIL_COUNT=0
#   CHECK4  COURSE_RTL_ASSERT_COUNT >= min_asserts (>0)
#
# Exit codes: 0 all pass; 7 CHECK0; 3 CHECK1; 4 CHECK2; 5 CHECK3; 6 CHECK4.
set -uo pipefail

TR="${1:-}"
MIN="${2:-55}"
VSIM_RC="${3:-0}"

[ -f "$TR" ] || { echo "TRANSCRIPT_MISSING=$TR"; echo "RUNNER_VERDICT=FAIL"; exit 8; }

# ModelSim batch mode prefixes every $display line with "# "; normalise first.
NORM=$(mktemp 2>/dev/null || echo "./.t6_norm.$$")
sed -E 's/^#[[:space:]]?//' "$TR" > "$NORM" 2>/dev/null

RESULT_LINE=$(grep -a "^COURSE_RTL_RESULT=" "$NORM" | tail -1)
FAIL_LINE=$(grep -a "^COURSE_RTL_FAIL_COUNT=" "$NORM" | tail -1)
ASRT_LINE=$(grep -a "^COURSE_RTL_ASSERT_COUNT=" "$NORM" | tail -1)
FAILED_ASSERTION=$(grep -a "^COURSE_FAILED_ASSERTION=" "$NORM" | tail -1)
ERR_LINE=$(grep -aE "^\*?\*? *Errors: *[0-9]+, *Warnings:" "$NORM" | tail -1)
FATAL_LINE=$(grep -a "^\*\* Fatal:" "$NORM" | tail -1)

FAIL_COUNT=$(printf '%s' "$FAIL_LINE" | sed -E 's/.*=([0-9]+).*/\1/')
ASRT_COUNT=$(printf '%s' "$ASRT_LINE" | sed -E 's/.*=([0-9]+).*/\1/')
ERR_COUNT=$(printf '%s' "$ERR_LINE" | sed -E 's/.*Errors: *([0-9]+).*/\1/')
[ -n "$FAIL_COUNT" ] || FAIL_COUNT=-1
[ -n "$ASRT_COUNT" ] || ASRT_COUNT=-1
[ -n "$ERR_COUNT" ] || ERR_COUNT=-1

C0=0; C1=0; C2=0; C3=0; C4=0
[ -z "$FATAL_LINE" ] && [ "$ERR_COUNT" -eq 0 ] && C0=1
[ "$VSIM_RC" -eq 0 ] && C1=1
printf '%s' "$RESULT_LINE" | grep -q "COURSE_RTL_RESULT=PASS" && C2=1
[ "$FAIL_COUNT" -eq 0 ] && C3=1
{ [ "$ASRT_COUNT" -ge "$MIN" ] && [ "$ASRT_COUNT" -gt 0 ]; } && C4=1

echo "=== T6 VERDICTS (1=PASS 0=FAIL) ==="
echo "CHECK0_NO_FATAL_NO_ERRORS=$C0   (errors=$ERR_COUNT fatal=${FATAL_LINE:-none})"
echo "CHECK1_PROCESS_RC_ZERO=$C1   (vsim_rc=$VSIM_RC)"
echo "CHECK2_RESULT_MARKER_PASS=$C2   (${RESULT_LINE:-<missing>})"
echo "CHECK3_FAIL_COUNT_ZERO=$C3   (fail_count=$FAIL_COUNT)"
echo "CHECK4_ASSERT_COUNT_GE_MIN=$C4   (assert_count=$ASRT_COUNT min=$MIN)"
[ -n "$FAILED_ASSERTION" ] && echo "$FAILED_ASSERTION"

RC=0
if [ "$C0" = 0 ] || [ "$C1" = 0 ] || [ "$C2" = 0 ] || [ "$C3" = 0 ] || [ "$C4" = 0 ]; then
    echo "RUNNER_VERDICT=FAIL"
    [ "$C0" = 0 ] && RC=7
    [ "$C1" = 0 ] && RC=3
    [ "$C2" = 0 ] && RC=4
    [ "$C3" = 0 ] && RC=5
    [ "$C4" = 0 ] && RC=6
else
    echo "RUNNER_VERDICT=PASS"
fi
rm -f "$NORM" 2>/dev/null
echo "RUNNER_EXIT=$RC"
exit "$RC"
