#!/bin/bash
# DATA-6 section 8: run one SKILL file in a full Virtuoso session whose cwd is THIS TASK's isolated
# work directory, so the session resolves data_d6_oa/cds.lib and nothing else.
#
# This is a copy-by-value of the pattern scripts/sc1_s3c_run_oa.sh delivered (environment from
# skill/cad_env.sh, /etc/env/virtuoso never executed, HOME redirected into the project, SKILL
# injected by an isolated .cdsinit that loads the file and closes the session with exit(), a hard
# timeout, and a TOKEN verdict because rc=0 alone is not success). That runner is not modified: its
# cwd is s3c_oa, and DATA-6 must run against its own map.
#
#   bash scripts/dd1_d6_run_oa.sh <abs.path.under.data_d6_oa/file.il> [timeoutSec] [TOKEN]
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
D6="${D6OA:-$PROJ/cadence_work/data_d6_oa}"
IL="${1:?usage: dd1_d6_run_oa.sh <abs .il under data_d6_oa> [timeout] [TOKEN]}"
TMO="${2:-240}"
TOKEN="${3:-${TOKEN:-D6_SKILL_DONE}}"

case "$IL" in "$D6"/*.il) ;; *) echo "REFUSED: SKILL file must live under $D6 (got $IL)"; exit 9 ;; esac
[ -f "$IL" ] || { echo "REFUSED: $IL not found"; exit 9; }
[ -f "$D6/cds.lib" ] || { echo "REFUSED: $D6/cds.lib missing -- run scripts/dd1_d6_setup_oa.sh first"; exit 9; }

# shellcheck disable=SC1091
. "$PROJ/skill/cad_env.sh" || { echo "FATAL: cadence env load failed"; exit 8; }

HOME_DIR="$D6/home"
mkdir -p "$HOME_DIR" "$D6/logs"
cd "$D6" || exit 9
export HOME="$HOME_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
LOG="$D6/logs/d6_oa_$STAMP.log"
OUT="$D6/logs/d6_oa_$STAMP.stdout"

printf ';; written by scripts/dd1_d6_run_oa.sh -- isolated init for one batch run\nload("%s")\n' "$IL" \
  > "$HOME_DIR/.cdsinit"
printf 'exit()\n' >> "$HOME_DIR/.cdsinit"

CMD=(virtuoso -nograph -log "$LOG")
echo "RUN mode=nograph cwd=$D6 home=$HOME timeout=${TMO}s il=$IL token=$TOKEN"
timeout "$TMO" "${CMD[@]}" > "$OUT" 2>&1
rc=$?
echo "RESULT rc=$rc"
COMBINED="$OUT"
[ -s "$LOG" ] && COMBINED="$LOG $OUT"
cp -f "$OUT" "$D6/logs/d6_last.stdout" 2>/dev/null
cp -f "$LOG" "$D6/logs/d6_last.log" 2>/dev/null
if grep -qsF "$TOKEN" $COMBINED; then
  echo "TOKEN_FOUND yes"
  echo "D6_RUN_OA: PASS log=$LOG"
  exit 0
fi
echo "TOKEN_FOUND no"
echo "----- stdout tail -----"
tail -30 "$OUT" 2>/dev/null
[ -s "$LOG" ] && { echo "----- log tail -----"; tail -30 "$LOG"; }
echo "D6_RUN_OA: FAIL log=$LOG"
exit 1
