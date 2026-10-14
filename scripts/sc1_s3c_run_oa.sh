#!/bin/bash
# SCAN-1 S3-C: run one SKILL file in a full Virtuoso session whose cwd is THIS TASK's isolated
# work directory, so the session resolves s3c_oa/cds.lib and nothing else.
#
# This is a copy-by-value of the pattern scripts/sch_virtuoso.sh proved (environment from
# skill/cad_env.sh, /etc/env/virtuoso never executed, HOME redirected into the project, SKILL
# injected by an isolated .cdsinit that loads the file and closes the session with exit(), a hard
# timeout, and a token verdict because rc=0 alone is not success). The original runner is not
# modified: its cwd is cadence_work, which resolves the shared library map, and S3-C must run
# against its own map.
#
#   bash scripts/sc1_s3c_run_oa.sh <abs.path.under.s3c_oa/file.il> [timeoutSec] [TOKEN]
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
S3C="$PROJ/cadence_work/s3c_oa"
IL="${1:?usage: sc1_s3c_run_oa.sh <abs .il under s3c_oa> [timeout] [TOKEN]}"
TMO="${2:-240}"
TOKEN="${3:-${TOKEN:-S3C_SKILL_DONE}}"

case "$IL" in "$S3C"/*.il) ;; *) echo "REFUSED: SKILL file must live under $S3C (got $IL)"; exit 9 ;; esac
[ -f "$IL" ] || { echo "REFUSED: $IL not found"; exit 9; }
[ -f "$S3C/cds.lib" ] || { echo "REFUSED: $S3C/cds.lib missing -- run scripts/sc1_s3c_setup.sh first"; exit 9; }

# shellcheck disable=SC1091
. "$PROJ/skill/cad_env.sh" || { echo "FATAL: cadence env load failed"; exit 8; }

HOME_DIR="$S3C/home"
mkdir -p "$HOME_DIR" "$S3C/logs"
cd "$S3C" || exit 9
export HOME="$HOME_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
LOG="$S3C/logs/s3c_oa_$STAMP.log"
OUT="$S3C/logs/s3c_oa_$STAMP.stdout"

if [ "${MODE:-nograph}" = "restore" ]; then
  rm -f "$HOME_DIR/.cdsinit"
  printf ';; restore mode runs the IL itself; nothing extra here\n' > "$HOME_DIR/.cdsinit"
else
  printf ';; written by scripts/sc1_s3c_run_oa.sh -- isolated init for one batch run\nload("%s")\n' "$IL" \
    > "$HOME_DIR/.cdsinit"
  printf 'exit()\n' >> "$HOME_DIR/.cdsinit"
fi

case "${MODE:-nograph}" in
  restore) CMD=(virtuoso -nograph -log "$LOG" -restore "$IL") ;;
  nograph) CMD=(virtuoso -nograph -log "$LOG") ;;
  gui)     [ -n "${DISPLAY:-}" ] || { echo "REFUSED: MODE=gui needs DISPLAY"; exit 9; }
           CMD=(virtuoso -log "$LOG") ;;
  *) echo "usage: MODE=nograph|restore|gui"; exit 9 ;;
esac

echo "RUN mode=${MODE:-nograph} cwd=$S3C home=$HOME timeout=${TMO}s il=$IL token=$TOKEN"
timeout "$TMO" "${CMD[@]}" > "$OUT" 2>&1
rc=$?
echo "RESULT rc=$rc"
COMBINED="$OUT"
[ -s "$LOG" ] && COMBINED="$LOG $OUT"
cp -f "$OUT" "$S3C/logs/s3c_last.stdout" 2>/dev/null
cp -f "$LOG" "$S3C/logs/s3c_last.log" 2>/dev/null
if grep -qsF "$TOKEN" $COMBINED; then
  echo "TOKEN_FOUND yes"
  echo "S3C_RUN_OA: PASS log=$LOG"
  exit 0
fi
echo "TOKEN_FOUND no"
echo "----- stdout head/tail -----"
head -20 "$OUT" 2>/dev/null
echo "..."
tail -30 "$OUT" 2>/dev/null
[ -s "$LOG" ] && { echo "----- log tail -----"; tail -30 "$LOG"; }
echo "S3C_RUN_OA: FAIL log=$LOG"
exit 1
