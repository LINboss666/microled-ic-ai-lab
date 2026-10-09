#!/bin/bash
# GUI-2 B: start the .desktop Exec target with the GNOME session's own environment and prove a real
# virtuoso process appears. LAUNCHER_CHECK: PASS cannot show any of this, so this path does not use
# it. A pre-existing user session is only reported, never touched.
#
#   bash /tmp/gui2_real_launch.sh [program-to-launch]
set -u
F="${1:-/root/microled_ai_project/cadence_work/launch_virtuoso.sh}"
OUT=/tmp/gui2_launch.out
: > "$OUT"
[ -f "$F" ] || { echo "REAL_LAUNCH: FAIL (program $F missing)"; exit 9; }

GP=$(pgrep -f gnome-session | head -1)
[ -n "$GP" ] || { echo "REAL_LAUNCH: FAIL (no gnome-session)"; exit 9; }
echo "TARGET=$F"
echo "GNOME_SESSION_PID=$GP"
tr '\0' '\n' < "/proc/$GP/environ" | grep -E '^(DISPLAY|XAUTHORITY|HOME|USER)=' | sed 's/^/  env /'
echo "  env PATH_HEAD=$(tr '\0' '\n' < "/proc/$GP/environ" | sed -n 's/^PATH=//p' | cut -d: -f1-2 | tr '\n' ',')"

echo "=== pre-state: virtuoso already running? (reported, never touched) ==="
BEFORE=$(ps -eo pid,args | grep -E '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | tr '\n' ' ')
echo "  before_pids=[${BEFORE:-none}]"

# locate the env helper: prefer the copy deployed beside this script
ENVE="$(dirname "$0")/gui2_envexec.sh"
[ -f "$ENVE" ] || ENVE=/tmp/gui2_envexec.sh
[ -f "$ENVE" ] || { echo "REAL_LAUNCH: FAIL (gui2_envexec.sh not found)"; exit 9; }
setsid nohup bash "$ENVE" "$F" > "$OUT" 2>&1 < /dev/null &
WP=$!
echo "WRAPPER_PID=$WP"
sleep 2
echo "--- launcher output (first 2s) ---"
sed 's/^/  [L] /' "$OUT"

VP=""
i=0
while [ "$i" -lt 30 ]; do
  i=$((i + 1))
  sleep 3
  VP=$(pgrep -f '/opt/IC617.*/virtuoso' | head -1)
  if [ -n "$VP" ]; then
    echo "VIRTUOSO_PID=$VP (appeared after $((i * 3))s)"
    break
  fi
done

echo "--- full launcher stdout+stderr ---"
sed 's/^/  [L] /' "$OUT"

if [ -z "$VP" ]; then
  echo "VIRTUOSO_PROCESS: NONE (waited 90s)"
  echo "REAL_LAUNCH: FAIL"
  exit 8
fi
NEW=$(ps -eo pid,args | grep -E '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | tr '\n' ' ')
echo "AFTER_PIDS=[$NEW]"
echo "VIRTUOSO_PROCESS: PRESENT"
LOG=$(ls -t /root/microled_ai_project/cadence_work/logs/virtuoso_gui_*.log 2>/dev/null | head -1)
echo "SESSION_LOG=${LOG:-none}"

# A process is not a GUI. Cadence creates its top-levels unmapped first (libManager/libSelect are
# started with -unmapped) and maps the CIW when init finishes, so poll for a window that is actually
# IsViewable and carries a WM_STATE -- the same predicate a user's eyes would confirm.
export DISPLAY="${DISPLAY:-:0}"
WIN=""
j=0
while [ "$j" -lt 20 ]; do
  j=$((j + 1))
  sleep 3
  for w in $(xwininfo -root -tree 2>/dev/null | grep -iE '"Virtuoso|opus"' | sed -n 's/^ *\(0x[0-9a-f]*\).*/\1/p' | head -8); do
    MS=$(xwininfo -id "$w" 2>/dev/null | sed -n 's/^ *Map State: //p')
    if [ "$MS" = "IsViewable" ] && xprop -id "$w" WM_NAME 2>/dev/null | grep -q 'Virtuoso'; then
      WIN="$w"
      break
    fi
  done
  [ -n "$WIN" ] && { echo "VIRTUOSO_WINDOW=$WIN (viewable after $((j * 3))s)"; break; }
done
if [ -n "$WIN" ]; then
  xwininfo -id "$WIN" 2>/dev/null | grep -E "Map State|Width|Height|Absolute upper-left" | sed 's/^/  /'
  xprop -id "$WIN" WM_NAME WM_CLASS WM_STATE 2>/dev/null | sed 's/^/  /'
  echo "VIRTUOSO_WINDOW: VIEWABLE"
  echo "REAL_LAUNCH: PASS (process + viewable window on the session display)"
else
  echo "VIRTUOSO_WINDOW: NONE VIEWABLE (waited 60s after the process appeared)"
  echo "REAL_LAUNCH: PASS_AT_PROCESS_LEVEL_ONLY -- windows not confirmed on screen"
  exit 6
fi
exit 0
