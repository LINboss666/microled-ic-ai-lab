#!/bin/bash
# Run one SKILL file through IC617 dbAccess, inside the sandbox, with a timeout.
#
#   run_skill.sh <abs.path.to/script.il> [timeoutSec]
#
# Safety guards (intentional, so an automated caller can never point this at a
# real project):
#   - the script must already exist and must live under $SANDBOX
#   - HOME is redirected into the sandbox so Cadence scratch files cannot land in
#     the real home directory
#   - cwd is $SANDBOX/work, so relative writes stay inside the sandbox
#   - stdout+stderr go to $SANDBOX/logs/<name>_<timestamp>.log and are echoed back
set -u

SANDBOX="${QODER_SANDBOX:-/root/qoder_ic617_sandbox}"
IL="${1:-}"
TMO="${2:-180}"

case "$IL" in
  "$SANDBOX"/*.il) ;;
  *) echo "REFUSED: script must be an existing .il under $SANDBOX (got: '${IL}')" >&2; exit 9 ;;
esac
[ -f "$IL" ] || { echo "REFUSED: $IL not found" >&2; exit 9; }
[ -d "$SANDBOX/work" ] || mkdir -p "$SANDBOX/work"

cd "$SANDBOX/work" || { echo "REFUSED: cannot enter $SANDBOX/work" >&2; exit 9; }
export HOME="$SANDBOX/home"; mkdir -p "$HOME"
. "$SANDBOX/bin/cad_env.sh" || { echo "FATAL: env load failed" >&2; exit 8; }

BIN="${IL##*/}"; NAME="${BIN%.il}"
LOG="$SANDBOX/logs/${NAME}_$(date +%Y%m%d_%H%M%S).log"
# dbAccess's SKILL has no clock built-in (gettime/time/ctime/time2str/posixtime/
# today/now all resolve to nil here), so the wall clock is injected for SKILL to read
# back via getShellEnvVar("QODER_RUN_TS"). QODER_HOST is injected too: bash sets
# HOSTNAME as a shell variable but does not export it in this non-login context,
# so getShellEnvVar("HOSTNAME") would be nil.
export QODER_RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export QODER_HOST="$(hostname 2>/dev/null || echo unknown)"
start=$(date +%s)
timeout "$TMO" dbAccess -load "$IL" > "$LOG" 2>&1
rc=$?
echo "RUN name=$NAME rc=$rc elapsed=$(( $(date +%s) - start ))s timeout=${TMO}s"
echo "LOGFILE $LOG"
echo "----- log -----"
cat "$LOG"
echo "----- end -----"
exit $rc
