#!/bin/bash
# SCAN-1 S3C3: the one GUI session this round is allowed, and the screenshots it must produce.
#
# Why this is a separate launcher instead of scripts/sc1_s3c_run_oa.sh: that runner always appends
# exit() to the isolated .cdsinit, which would tear the windows down before anything can be
# captured. Here the session is started, its windows are waited for with xwininfo, each view window
# is captured with import(1) into a PNG, and only then is the session this script started
# terminated. The desktop session's own DISPLAY and XAUTHORITY are read from /proc, exactly the way
# GUI-2 proved a window reaches IsViewable; nothing about the display service is modified.
#
#   bash scripts/s3c3_gui_shot.sh <outDir> [waitSeconds]
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
S3C="$PROJ/cadence_work/s3c_oa"
OUT="${1:?usage: s3c3_gui_shot.sh <outDir> [waitSeconds]}"
WAIT="${2:-150}"
IL="$S3C/sc1_s3c3_gui_open.il"

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
printf ';; written by scripts/s3c3_gui_shot.sh -- opens the views and returns; no exit()\nload("%s")\n' "$IL" > "$HOME_DIR/.cdsinit"

virtuoso -log "$LOG" > "$LOG.stdout" 2>&1 &
VPID=$!
echo "LAUNCH pid=$VPID log=$LOG"

printf 'cell,view,window_id,title,png_bytes,png_sha256,map_state\n' > "$OUT/s3c3_windows.csv"
capture_one() {
  local cell="$1" view="$2" id="$3" title="$4" state="$5"
  local png="$OUT/s3c3_${cell}_${view}.png"
  import -window "$id" "$png" 2>"$OUT/.import_err"
  local bytes=0 sha=""
  if [ -s "$png" ]; then bytes=$(stat -c %s "$png"); sha=$(sha256sum "$png" | cut -d' ' -f1); fi
  printf '"%s","%s","%s","%s","%s","%s","%s"\n' "$cell" "$view" "$id" "$title" "$bytes" "$sha" "$state" \
    >> "$OUT/s3c3_windows.csv"
  echo "SHOT $cell:$view id=$id bytes=$bytes state=$state"
}

DEADLINE=$((SECONDS + WAIT))
declare -A SEEN
while [ $SECONDS -lt $DEADLINE ]; do
  alive=$(ps -p "$VPID" -o pid= 2>/dev/null | wc -l)
  [ "$alive" = "1" ] || { echo "FAIL_STAGE=session_alive virtuoso exited early"; break; }
  xwininfo -root -tree > "$OUT/.wininfo" 2>/dev/null
  done_rows=0
  while read -r cell view; do
    key="$cell:$view"
    [ -n "${SEEN[$key]:-}" ] && { done_rows=$((done_rows + 1)); continue; }
    # Cadence titles look like  "<lib>:<cell> <view>  (Virtuoso)"  for a design window; the earlier
    # match on "view:<view>" and "Design" found nothing while a window titled Virtuoso did exist
    line=$(grep -F "$cell $view" "$OUT/.wininfo" | grep -iE "virtuoso|design" | head -1)
    [ -n "$line" ] || line=$(grep -F "$cell" "$OUT/.wininfo" | grep -F "$view" | head -1)
    [ -n "$line" ] || continue
    id=$(echo "$line" | sed -n 's/^\s*\(0x[0-9a-f]*\).*/\1/p')
    state=$(echo "$line" | grep -o "IsViewable" | head -1)
    [ -n "$state" ] || state=$(echo "$line" | grep -o "IsUnMapped" | head -1)
    [ -n "$id" ] || continue
    capture_one "$cell" "$view" "$id" "$(echo "$line" | sed -n 's/.*"\(.*\)".*/\1/p')" "${state:-unknown}"
    SEEN[$key]="$id"
  done < "$S3C/s3c3_targets.txt"
  if [ ${#SEEN[@]} -ge 6 ]; then echo "CAPTURED all six"; break; fi
  sleep 8
done

echo "SESSION_ALIVE_BEFORE_KILL=$(ps -p $VPID -o pid= 2>/dev/null | wc -l)"
kill -TERM "$VPID" 2>/dev/null
sleep 5
kill -KILL "$VPID" 2>/dev/null
cp -f "$OUT/.wininfo" "$OUT/s3c3_wininfo_final.txt" 2>/dev/null
echo "WINDOWS_SEEN=$(grep -cE '\(Virtuoso\)|Design' "$OUT/s3c3_wininfo_final.txt" 2>/dev/null || echo 0)"
grep -oE '\(Virtuoso\)[^"]*|"[^"]*Virtuoso[^"]*"' "$OUT/s3c3_wininfo_final.txt" | sort -u | head -12
echo "GUI_SESSION_CLOSED pid=$VPID"
echo "SCREENSHOTS=$(ls "$OUT"/s3c3_*.png 2>/dev/null | wc -l) non-empty=$(find "$OUT" -name 's3c3_*.png' -size +1k | wc -l)"
grep -q "GW-END-OF-OPENS" "$LOG" "$LOG.stdout" 2>/dev/null && echo "OPENS_SEEN yes" || echo "OPENS_SEEN no"
echo "S3C3_GUI_SHOT: DONE out=$OUT"
