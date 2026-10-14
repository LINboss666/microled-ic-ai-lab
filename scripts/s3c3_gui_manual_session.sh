#!/bin/bash
# SCAN-1 S3C3: start the isolated GUI session and LEAVE IT RUNNING so the six views can be screenshotted
# by hand. Screenshots are a manual deliverable from this round on.
#
# Why no automated capture here: scripts/s3c3_gui_shot.sh + scripts/s3c3_gui_capture.py tried it and the
# measurements are recorded in results/evidence/sc1_s3c3_gui_capture_index.csv and
# sc1_s3c3_log_gui_session*.txt. What they proved: the session starts correctly, six editor windows
# exist and are IsViewable in six non-overlapping slots (slots_confirmed=6/6), but the top-level
# windows hold no pixels (a 134-byte uniform PNG each), the largest child is an unmapped helper
# (import: unable to read X window image), and the window manager's stacking order never follows
# hiRaiseWindow. Rather than ship a tool that cannot produce trustworthy pixels, this script only
# opens the windows, dumps the X evidence, and hands over to a person.
#
# This launcher deliberately does not use scripts/sc1_s3c_run_oa.sh: that runner appends exit() to
# the isolated .cdsinit, which would close the windows. DISPLAY/XAUTHORITY are read from the running
# desktop session's own environment; nothing about the VM, the display service, the network or the
# license configuration is changed, and the session this script started is the only one it touches.
#
#   PROJ=/root/microled_ai_project bash scripts/s3c3_gui_manual_session.sh <outDir> [waitSeconds]
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
S3C="$PROJ/cadence_work/s3c_oa"
OUT="${1:?usage: s3c3_gui_manual_session.sh <outDir> [waitSeconds]}"
WAIT="${2:-150}"
IL="$S3C/sc1_s3c3_gui_open.il"
TARGETS="$S3C/s3c3_targets.txt"

mkdir -p "$OUT"
[ -f "$IL" ] || { echo "REFUSED: $IL missing"; exit 9; }
GNOME_PID=$(pgrep -o gnome-session || true)
[ -n "$GNOME_PID" ] || { echo "FAIL_STAGE=desktop_session no gnome-session process"; exit 6; }
ENVF="/proc/$GNOME_PID/environ"
export DISPLAY=$(tr '\0' '\n' < "$ENVF" | sed -n 's/^DISPLAY=//p' | head -1)
export XAUTHORITY=$(tr '\0' '\n' < "$ENVF" | sed -n 's/^XAUTHORITY=//p' | head -1)
[ -n "${DISPLAY:-}" ] || { echo "FAIL_STAGE=display DISPLAY empty"; exit 6; }
echo "ENV DISPLAY=$DISPLAY XAUTHORITY=${XAUTHORITY:-none} gnome_pid=$GNOME_PID"

# shellcheck disable=SC1091
. "$PROJ/skill/cad_env.sh" || { echo "FATAL: cadence env load failed"; exit 8; }

HOME_DIR="$S3C/home"
mkdir -p "$HOME_DIR" "$S3C/logs"
cd "$S3C" || exit 9
export HOME="$HOME_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG="$S3C/logs/s3c3_gui_$STAMP.log"
printf ';; written by scripts/s3c3_gui_manual_session.sh -- opens the views and returns; no exit()\nload("%s")\n' "$IL" > "$HOME_DIR/.cdsinit"

virtuoso -log "$LOG" > "$LOG.stdout" 2>&1 &
VPID=$!
# the session is the deliverable here: it must outlive this script so the screenshots can be taken
disown "$VPID" 2>/dev/null || true
echo "LAUNCH pid=$VPID log=$LOG"

DEADLINE=$((SECONDS + WAIT))
READY=no
while [ $SECONDS -lt $DEADLINE ]; do
  alive=$(ps -p "$VPID" -o pid= 2>/dev/null | wc -l)
  [ "$alive" = "1" ] || { echo "FAIL_STAGE=session_alive virtuoso exited early"; break; }
  if grep -q "GW-READY-FOR-MANUAL-CAPTURE" "$LOG" 2>/dev/null; then READY=yes; break; fi
  sleep 4
done
echo "READY_FOR_MANUAL_CAPTURE=$READY"

xwininfo -root -tree > "$OUT/s3c3_wininfo.txt" 2>/dev/null
xwininfo -root -stats > "$OUT/s3c3_root_stats.txt" 2>/dev/null
xprop -root _NET_CLIENT_LIST_STACKING > "$OUT/s3c3_client_stacking.txt" 2>/dev/null

printf 'open_index,cell,view,window_id,geometry,map_state\n' > "$OUT/s3c3_capture_checklist.csv"
python - "$OUT/s3c3_wininfo.txt" "$OUT/s3c3_capture_checklist.csv" "$TARGETS" <<'PY' 2>/dev/null
import re, sys
# list Cadence's own top-level windows in creation order; that order is the order the SKILL script
# opened them, which is the only identity link available without reading pixels
LINE = re.compile(r'^\s*(0x[0-9a-f]+)\s(.*?)\s(\d+)x(\d+)([-+]\d+)([-+]\d+)\s+([-+]\d+)([-+]\d+)\s*$')
wins = []
for line in open(sys.argv[1]):
    m = LINE.match(line)
    if m and 'Virtuoso' in m.group(2):
        wins.append((m.group(1), int(m.group(3)), int(m.group(4)), int(m.group(7)), int(m.group(8))))
wins.sort(key=lambda w: int(w[0], 16))
design = wins[1:]  # the CIW is the first Virtuoso window the client creates
targets = [t.split() for t in open(sys.argv[3]) if t.strip()]
rows = []
for i, t in enumerate(targets):
    if i < len(design):
        wid, w, h, x, y = design[i]
        rows.append('"%d","%s","%s","%s","%dx%d+%d+%d","TODO_MANUAL"' % (i, t[0], t[1], wid, w, h, x, y))
open(sys.argv[2], 'a').write('\n'.join(rows) + ('\n' if rows else ''))
print('CHECKLIST rows=%d design_windows=%d' % (len(rows), len(design)))
PY

echo "SESSION_LEFT_RUNNING pid=$VPID  (kill it by hand when the screenshots are taken)"
echo "MANUAL_CAPTURE_GUIDE: click each of the six windows titled by its cell, then use gnome-screenshot"
grep -c 'GW-WIN' "$LOG" | sed 's/^/SKILL_WINDOW_ROWS=/'
tail -6 "$LOG" | tr -d '\r' | sed 's/^/LOGTAIL /'
echo "S3C3_GUI_MANUAL_SESSION: DONE out=$OUT"
