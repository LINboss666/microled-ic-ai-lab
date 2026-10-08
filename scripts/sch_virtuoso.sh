#!/bin/bash
# SCH-1 executor: run one SKILL file in a full Virtuoso session whose working directory is
# the Micro LED work dir, so it resolves exactly the same cds.lib the desktop launcher uses.
#
#   bash scripts/sch_virtuoso.sh <abs.path.to/file.il> [timeoutSec] [TOKEN]
#
# Why not reuse scripts/run_virtuoso.sh: that one cd's into $PROJ/skill_run, whose cds.lib is
# a leftover from DATA-4.5's PDK probe and knows nothing about microled_cells. A schematic
# session must see the same library map the user sees, so cwd has to be $WORK.
#
# Kept from the verified pattern:
#   * the environment is harvested by skill/cad_env.sh; /etc/env/virtuoso is never executed
#   * HOME is redirected into the project, and the .cdsinit we need is written THERE, so the
#     operator's own init is neither read nor modified
#   * SKILL injection via an isolated .cdsinit that loads the file and then exit()s
#   * the refused-outside-project guard, a hard timeout, and a token-based verdict:
#     rc=0 alone is not success, the token must appear
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
IL="${1:?usage: sch_virtuoso.sh <abs path .il> [timeout] [TOKEN]}"
TMO="${2:-240}"
TOKEN="${3:-${TOKEN:-SCH_SKILL_DONE}}"   # 3rd positional wins; the env form stays allowed

case "$IL" in "$PROJ"/*.il) ;; *) echo "REFUSED: SKILL file must live under $PROJ (got $IL)"; exit 9 ;; esac
[ -f "$IL" ] || { echo "REFUSED: $IL not found"; exit 9; }
[ -f "$WORK/cds.lib" ] || echo "WARN: $WORK/cds.lib missing -> the session will not see the project libraries"

# shellcheck disable=SC1091
. "$PROJ/skill/cad_env.sh" || { echo "FATAL: cadence env load failed"; exit 8; }

HOME_DIR="$WORK/home"
mkdir -p "$HOME_DIR" "$WORK/logs"
cd "$WORK" || exit 9
export HOME="$HOME_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
LOG="$WORK/logs/sch_nograph_$STAMP.log"
OUT="$WORK/logs/sch_nograph_$STAMP.stdout"

cat > "$HOME_DIR/.cdsinit" <<EOF
;; written by scripts/sch_virtuoso.sh -- isolated init for one batch run, not the operator's
load("$IL")
EOF

if [ "${DEFER:-0}" = "1" ]; then
  # Editor packages are only present once the environment has finished initialising, so the
  # IL must define sch1Main() and be invoked from the init hook instead of from .cdsinit.
  # The IL is then responsible for exit().
  printf 'hiSetInitFunc("sch1Main()")\n' >> "$HOME_DIR/.cdsinit"
else
  printf 'exit()\n' >> "$HOME_DIR/.cdsinit"
fi

# MODE=gui is not a cosmetic choice: measured on this build, `virtuoso -nograph` never loads
# the Schematic Editor package, so schCreate/schCreateWire/schCheck are simply absent there
# (getd('schCreate) -> nil, and every ddLoadContext/hiLoadContext/schInit variant returned nil
# without defining it). The DB-level API (dbCreateInst/dbCreateTerm/dbOpenCellViewByType) IS
# present in -nograph. Anything that must produce a real, checkable schematic therefore runs
# as a normal session against the desktop display, driven by the .cdsinit above and closing
# itself with exit().
case "${MODE:-nograph}" in
  nograph) CMD=(virtuoso -nograph -log "$LOG") ;;
  gui)     [ -n "${DISPLAY:-}" ] || { echo "REFUSED: MODE=gui needs DISPLAY"; exit 9; }
           CMD=(virtuoso -log "$LOG") ;;
  *) echo "usage: MODE=nograph|gui"; exit 9 ;;
esac

echo "RUN mode=${MODE:-nograph} cwd=$WORK home=$HOME timeout=${TMO}s il=$IL token=$TOKEN"
timeout "$TMO" "${CMD[@]}" > "$OUT" 2>&1
rc=$?
echo "RESULT rc=$rc"
COMBINED="$OUT"
[ -s "$LOG" ] && COMBINED="$LOG $OUT"
if grep -qsF "$TOKEN" $COMBINED; then
  echo "TOKEN_FOUND yes"
  echo "SCH_VIRTUOSO: PASS  log=$LOG"
  exit 0
fi
echo "TOKEN_FOUND no"
echo "----- stdout head/tail -----"
head -20 "$OUT" 2>/dev/null
echo "..."
tail -30 "$OUT" 2>/dev/null
[ -s "$LOG" ] && { echo "----- log tail -----"; tail -30 "$LOG"; }
echo "SCH_VIRTUOSO: FAIL  log=$LOG"
exit 1
