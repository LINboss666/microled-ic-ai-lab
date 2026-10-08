#!/bin/bash
# SCH-1 A3: prove the desktop entry really brings up a Virtuoso GUI, and tell the two launch
# paths apart:
#
#   MODE=handler  gnome-open <desktop file>        (what a double-click drives)
#   MODE=exec     run the desktop entry's Exec line (what the handler ultimately does)
#
# Evidence rules, learned the hard way in this session:
#   * every line of a Virtuoso session log is prefixed \o \a \#, so no pattern may be anchored
#   * a session log must be attributed to a pid through /proc/<pid>/cmdline (the launcher puts
#     -log <path> on that command line); "newest log file" mis-attributed a late-starting
#     handler session to the exec session and produced a false FAIL
#   * the desktop handler can take ~2 minutes to spawn the process, so the default wait is
#     longer than the direct-Exec path needs
#   * every session this script sees appear is its own to close; pids that existed before the
#     call are never signalled
#
#   MODE=handler bash scripts/sch1_gui_test.sh
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
DESK="/root/Desktop/Cadence-Virtuoso-MicroLED.desktop"
LOGD="$WORK/logs"
MODE="${MODE:-exec}"
WAIT="${WAIT:-$([ "$MODE" = handler ] && echo 220 || echo 90)}"
mkdir -p "$LOGD"
RUNLOG="$LOGD/sch1_gui_test_${MODE}_$(date +%Y%m%d_%H%M%S).log"

say() { printf '%s\n' "$*" | tee -a "$RUNLOG"; }
vpids() { ps -eo pid,args | grep '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | tr '\n' ' '; }

[ -x "$DESK" ] || { say "DESKTOP_ENTRY missing/not executable"; exit 1; }
EX=$(grep -E '^Exec=' "$DESK" | head -1 | cut -d= -f2)
[ -x "$EX" ] || { say "desktop Exec not executable: $EX"; exit 1; }

if [ -z "${DISPLAY:-}" ]; then
  s=$(ls /tmp/.X11-unix 2>/dev/null | sed -n 's/^X\([0-9]*\)$/:\1/p' | head -1)
  [ -n "$s" ] || { say "no X socket: no desktop session to attach to"; exit 1; }
  export DISPLAY="$s"
fi
BEFORE=" $(vpids) "
say "MODE=$MODE DISPLAY=$DISPLAY wait=${WAIT}s pre-existing=[$BEFORE]"

case "$MODE" in
  handler) command -v gnome-open >/dev/null 2>&1 || { say "gnome-open absent"; exit 1; }
           gnome-open "$DESK" >>"$RUNLOG" 2>&1 & ;;
  exec)    ( cd "$WORK" && "$EX" </dev/null >>"$RUNLOG" 2>&1 ) & ;;
  *) say "unknown MODE"; exit 1 ;;
esac

NEWPIDS=""
i=0
while [ "$i" -lt "$WAIT" ]; do
  sleep 3; i=$((i + 3))
  for p in $(vpids); do
    case "$BEFORE" in *" $p "*) ;; *) NEWPIDS="$NEWPIDS $p";; esac
  done
  [ -n "$NEWPIDS" ] && break
done
NEWPIDS=$(printf '%s\n' $NEWPIDS | tr '\n' ' ')
say "appeared during the wait: [$NEWPIDS]"

if [ -z "${NEWPIDS// /}" ]; then
  say "VIRTUOSO_GUI           FAIL (no session process appeared within ${WAIT}s)"
  say "GUI_TEST_DONE FAIL"; exit 1
fi

# attribute each new pid to the session log it names itself
OKALL=1
for p in $NEWPIDS; do
  SLOG=$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | sed -n 's/.* -log \([^ ]*\.log\).*/\1/p')
  if [ ! -f "${SLOG:-/nonexistent}" ]; then
    say "  pid $p : no -log path in its cmdline; cannot grade"; OKALL=0; continue
  fi
  x=$(grep -ac "X display name" "$SLOG"); c=$(grep -ac "END OF SITE CUSTOMIZATION" "$SLOG")
  r=$(grep -ac "hiResizeWindow" "$SLOG");  l=$(grep -ac "License (111)" "$SLOG")
  say "  pid $p : log=$(basename "$SLOG") X-display=$x licence=$l site-init=$c window=$r"
  grep -aE "Program:|X display name|Library Manager|hiLoadDatabase" "$SLOG" | head -4 | sed 's/^/      /' >> "$RUNLOG"
  [ "$x" -ge 1 ] && [ "$c" -ge 1 ] || OKALL=0
done

for p in $NEWPIDS; do kill -TERM "$p" 2>/dev/null; done
sleep 8
for p in $NEWPIDS; do
  if ps -p "$p" >/dev/null 2>&1; then say "  pid $p still alive after TERM (left alone, not killed harder)"; else say "  pid $p closed"; fi
done
say "still running (pre-existing, untouched):[$(vpids)]"

if [ "$OKALL" = 1 ]; then say "VIRTUOSO_GUI           PASS"; say "GUI_TEST_DONE PASS"; else
  say "VIRTUOSO_GUI           FAIL (session(s) up but initialisation incomplete -- see pid lines)"
  say "GUI_TEST_DONE FAIL"; exit 1
fi
