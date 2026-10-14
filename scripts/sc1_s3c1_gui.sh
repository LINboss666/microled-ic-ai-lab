#!/bin/bash
# SCAN-1 S3C1: run ONE limited GUI Virtuoso session for this task's own library.
#
#   bash scripts/sc1_s3c1_gui.sh <abs.path.under.s3c_oa/file.il> [timeoutSec] [TOKEN]
#
# Why this file exists: scripts/sc1_s3c_run_oa.sh already knows how to start a full Virtuoso with
# this task's isolated HOME, its own .cdsinit and this task's cds.lib, and it refuses MODE=gui
# without a DISPLAY. The display belongs to the user's desktop session, so the values must come
# from that session and may not be guessed. scripts/gui2_envexec.sh reads the whole session
# environment out of /proc/<gnome-session>/environ, but it appends the program AFTER the entries,
# so it only works for a program with no arguments; a session run needs arguments (the SKILL file,
# the timeout, the token). This wrapper therefore takes exactly two values from the session --
# DISPLAY and XAUTHORITY -- verifies the X server answers, and keeps the Cadence environment from
# skill/cad_env.sh, which is what the audited runner already loads.
#
# Refusals, all of them checked before anything starts (task book: "先对本任务目标view确认写锁及
# 持有进程"): another Virtuoso process that could hold a write lock on a target view, a .locks
# entry in this task's library, no reachable X server, no session to borrow DISPLAY from.
# Nothing here kills a process, deletes a lock, edits a shared cds.lib or installs anything.
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
S3C="$PROJ/cadence_work/s3c_oa"
IL="${1:?usage: sc1_s3c1_gui.sh <abs .il under s3c_oa> [timeout] [TOKEN]}"
TMO="${2:-420}"
TOKEN="${3:-S8-DONE}"

fail() { echo "GUI1: REFUSED $*"; exit 9; }

case "$IL" in "$S3C"/*.il) ;; *) fail "SKILL file must live under $S3C (got $IL)";; esac
[ -f "$IL" ] || fail "$IL not found"
[ -f "$S3C/cds.lib" ] || fail "$S3C/cds.lib missing"
[ -x "$PROJ/scripts/gui2_envexec.sh" ] || fail "gui2_envexec.sh missing"

GP=$(pgrep -f gnome-session | head -1)
[ -n "$GP" ] || fail "no gnome-session process, so there is no desktop session to use"
[ -r "/proc/$GP/environ" ] || fail "cannot read /proc/$GP/environ"

ENVF="/proc/$GP/environ"
DISPLAY_VAL=$(tr '\0' '\n' < "$ENVF" | sed -n 's/^DISPLAY=//p' | head -1)
XAUTH_VAL=$(tr '\0' '\n' < "$ENVF" | sed -n 's/^XAUTHORITY=//p' | head -1)
[ -n "$DISPLAY_VAL" ] || fail "the session has no DISPLAY"

echo "GUI1: SESSION_PID=$GP DISPLAY=$DISPLAY_VAL XAUTHORITY=${XAUTH_VAL:-unset}"

# the check that matters is whether THIS user can actually paint on it, not whether the variable
# is set. xdpyinfo is the smallest honest test.
if ! DISPLAY="$DISPLAY_VAL" XAUTHORITY="$XAUTH_VAL" xdpyinfo -display "$DISPLAY_VAL" >/dev/null 2>&1; then
  echo "GUI1: REFUSED xdpyinfo cannot reach $DISPLAY_VAL (X server not usable from this session)"
  exit 9
fi
echo "GUI1: X_SERVER_OK=yes"

# a running Virtuoso is only a conflict when it could hold a write access to one of THIS task's
# views, so the evidence is recorded rather than guessed; the task still refuses to share.
# RHEL6 pgrep has no -a flag (measured: it printed its usage text and matched nothing, which would
# have made this check always pass), so the process list comes from ps.
OTHER=$(ps -eo pid=,cmd= | grep -E 'virtuoso|dbAccess' | grep -v grep | grep -v "$$" | head -5)
if [ -n "$OTHER" ]; then
  echo "GUI1: REFUSED another Cadence process exists, so a write session could conflict:"
  printf '%s\n' "$OTHER" | head -5
  exit 9
fi

LOCKS=$(find "$S3C/microled_scan_s3c" -maxdepth 3 -name '.locks' 2>/dev/null | head -3)
[ -z "$LOCKS" ] || { echo "GUI1: REFUSED lock entries present: $LOCKS"; exit 9; }
echo "GUI1: LOCKS=none LIB=$(basename "$S3C/microled_scan_s3c")"

mkdir -p "$S3C/out" "$S3C/logs"
GUI1_CAP_DIR="$S3C/out" MODE=gui DISPLAY="$DISPLAY_VAL" XAUTHORITY="$XAUTH_VAL" \
  bash "$PROJ/scripts/sc1_s3c_run_oa.sh" "$IL" "$TMO" "$TOKEN"
rc=$?

echo "GUI1: RUNNER_RC=$rc"
echo "GUI1: CAPTURE_DIR=$S3C/out"
ls -l "$S3C/out" 2>/dev/null | grep -E 'gui1|s8_' | head -20
for f in "$S3C/out"/gui1_capture_s8_*.txt; do
  [ -f "$f" ] || continue
  echo "--- $(basename "$f") ---"
  grep -E 'PNG=|_CAPTURE:|WINDOW_ID' "$f" | head -8
done
exit "$rc"
