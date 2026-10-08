#!/bin/bash
# SCH-1 A: the one approved way to start a full Virtuoso GUI for the Micro LED project.
#
# Environment handling is not reinvented here. In this image the Cadence variables are not
# in any login profile: they live inside /etc/env/virtuoso, which is a wrapper that ENDS BY
# LAUNCHING THE GUI. That wrapper is therefore never sourced and never executed by us --
# skill/cad_env.sh harvests only its `export` lines, and this launcher reuses that already
# verified loader. Nothing here installs Cadence, edits a license file, or touches
# /etc/profile, .bashrc or any system launcher.
#
# DISPLAY is inherited, never invented. The desktop session's own value wins. If a caller
# has none, the display is derived from the single X socket the server is actually
# listening on; if there is more than one socket the launcher refuses to guess, because a
# wrong display number produces a session nobody can see and looks like a success.
#
#   LAUNCHER_CHECK=1 ./launch_virtuoso.sh   resolve everything, print the CHECK lines, exit
#   ./launch_virtuoso.sh                    the same checks, then start the GUI
set -u

PROJ="${QODER_PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
CAD_ENV="$PROJ/skill/cad_env.sh"
CDS_LIB="$WORK/cds.lib"

say()  { printf '%s\n' "$*"; }
chk()  { printf 'CHECK %s %s\n' "$1" "$2"; [ "$2" = PASS ] || FAILED=1; }
bail() { printf 'LAUNCH_FAIL: %s\n' "$*" >&2; exit 1; }
FAILED=0

[ -d "$WORK" ]   || bail "work dir $WORK does not exist yet"
[ -f "$CAD_ENV" ] || bail "no verified Cadence env loader at $CAD_ENV"

# this is the harvest-only loader; /etc/env/virtuoso itself is never run
. "$CAD_ENV" || bail "cad_env.sh reported failure (cannot read its source?)"

BIN=$(command -v virtuoso || true)
{ [ -n "${OA_HOME:-}" ] && [ -n "${CDS:-}" ] && [ -n "$BIN" ]; } \
  || bail "Cadence environment did not load (OA_HOME/CDS/virtuoso)"
case "$BIN" in
  /opt/IC617/*) ;;
  *) bail "virtuoso resolved outside the installed IC617 tree: $BIN" ;;
esac
chk CADENCE_ENV_LOADED PASS
say "      virtuoso  : $BIN"
say "      OA_HOME   : $OA_HOME"
say "      MMSIM     : ${MMSIM_ROOT:-unset}"

cd "$WORK" || bail "cannot enter $WORK"
if [ "$PWD" = "$WORK" ]; then
  chk PROJECT_WORKDIR_CORRECT PASS
else
  chk PROJECT_WORKDIR_CORRECT FAIL
fi

if [ -z "${DISPLAY:-}" ]; then
  socks=$(ls /tmp/.X11-unix 2>/dev/null | sed -n 's/^X\([0-9][0-9]*\)$/:&/p' | tr -d 'X')
  n=$(printf '%s\n' "$socks" | grep -c '^:')
  if [ "$n" = "1" ]; then
    export DISPLAY="$socks"
    say "      DISPLAY derived from the only listening X socket: $DISPLAY"
  elif [ "$n" = "0" ]; then
    bail "no X socket under /tmp/.X11-unix: there is no desktop session to attach to"
  else
    bail "several X sockets ($socks): set DISPLAY explicitly rather than guessing"
  fi
fi
if [ -z "${XAUTHORITY:-}" ] && [ -f "${HOME:-/root}/.Xauthority" ]; then
  export XAUTHORITY="${HOME:-/root}/.Xauthority"
fi
say "      DISPLAY   : $DISPLAY   XAUTHORITY: ${XAUTHORITY:-unset}"

if [ -f "$CDS_LIB" ]; then
  chk CDS_LIB_FOUND PASS
  say "      cds.lib   : $CDS_LIB"
  grep -vE '^[[:space:]]*(#|$)' "$CDS_LIB" | sed 's/^/          /'
else
  chk CDS_LIB_FOUND FAIL
  say "      cds.lib   : $CDS_LIB missing -> Library Manager would show no project libraries"
fi

# An existing session is never touched: report it and carry on.
OTHER=$(ps -eo pid,args | grep '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | head -3 | tr '\n' ' ')
[ -n "${OTHER:-}" ] && say "      note: Virtuoso already running (pid $OTHER) -- left untouched"

if [ "${LAUNCHER_CHECK:-0}" = "1" ]; then
  if [ "$FAILED" = "0" ]; then say "LAUNCHER_CHECK: PASS"; exit 0; fi
  say "LAUNCHER_CHECK: FAIL"; exit 1
fi

[ "$FAILED" = "0" ] || bail "checks did not pass; refusing to start a half-configured GUI"

mkdir -p "$WORK/logs" || bail "cannot create $WORK/logs"
LOG="$WORK/logs/virtuoso_gui_$(date +%Y%m%d_%H%M%S).log"
say "      session log: $LOG"
say "STARTING_VIRTUOSO"
exec virtuoso -log "$LOG" >> "$LOG.stdout" 2>&1
