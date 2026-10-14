#!/bin/bash
# Run skill/sc1_libcheck.il in a headless session started the way the desktop shortcut starts one, so
# "the library is visible" is tested against the cds.lib the user actually gets.
#
# What makes this different from scripts/sc1_s3c_run_oa.sh: that runner deliberately uses
# cadence_work/s3c_oa as the session cwd and an isolated HOME, so it reads s3c_oa/cds.lib and can only
# ever prove the ISOLATED session sees microled_scan_s3c. Cadence resolves cds.lib from the working
# directory, and /root/Desktop/Cadence-Virtuoso-MicroLED.desktop execs
# /root/microled_ai_project/cadence_work/launch_virtuoso.sh, which does `cd $WORK` then
# `exec virtuoso -log ...` with no -cdslib flag. Same cwd, same HOME here.
#
# Never executes /etc/env/virtuoso (that wrapper ends by starting a GUI); only the exports harvested
# by skill/cad_env.sh are used. No OA view is written by this script; NEW_SIMULATION_RUNS = 0.
#
#   PROJ=/root/microled_ai_project bash scripts/sc1_libcheck.sh <abs path of the .il>
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
IL="${1:?usage: sc1_libcheck.sh <abs .il>}"
[ -f "$IL" ] || { echo "REFUSED: $IL not found"; exit 9; }

# shellcheck disable=SC1091
. "$PROJ/skill/cad_env.sh" || { echo "FATAL: cadence env load failed"; exit 8; }
command -v dbAccess >/dev/null 2>&1 || { echo "FATAL: dbAccess not on PATH"; exit 8; }

cd "$WORK" || exit 9
export HOME=/root
mkdir -p "$WORK/logs"
LOG="$WORK/logs/libcheck_$(date +%Y%m%d_%H%M%S).log"
timeout "${LIBCHECK_TMO:-240}" dbAccess -load "$IL" > "$LOG" 2>&1
rc=$?
grep -E 'LC-|\*Error\*' "$LOG" | sed 's/^\\[a-z ]*//' | head -40
echo "LIBCHECK rc=$rc log=$LOG"
# rc=0 is not the verdict: a SKILL load error still exits 0, and so does a session that simply could
# not resolve the library. Only the script's own final line counts.
if grep -q 'LC-DONE resolved=t' "$LOG"; then VERDICT=PASS; else VERDICT=FAIL; fi
echo "LIBCHECK session_cwd=$WORK cds_lib=$WORK/cds.lib HOME=$HOME"
test -f "$WORK/cds.lib" && echo "LIBCHECK cds_lib_lines=$(grep -cE '^[[:space:]]*DEFINE' "$WORK/cds.lib")"
echo "LIBCHECK: $VERDICT"
[ "$VERDICT" = PASS ] || exit 1
exit 0
