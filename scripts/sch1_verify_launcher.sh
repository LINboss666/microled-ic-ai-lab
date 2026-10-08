#!/bin/bash
# SCH-1 A3: verify the desktop launcher the way A3 lists it, from outside the launcher
# itself (so the launcher cannot grade its own homework). Read-only except for the log file
# this script writes under $PROJ/logs.
#
#   bash scripts/sch1_verify_launcher.sh
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
L="$WORK/launch_virtuoso.sh"
DESK="/root/Desktop/Cadence-Virtuoso-MicroLED.desktop"
CAD_ENV="$PROJ/skill/cad_env.sh"
LOG="$PROJ/logs/sch1_launcher_verify.log"
mkdir -p "$PROJ/logs"

: > "$LOG"
say() { printf '%s\n' "$*" | tee -a "$LOG"; }

[ -f "$L" ] && say "LAUNCHER_EXISTS      PASS $L" || say "LAUNCHER_EXISTS      FAIL $L"
[ -x "$L" ] && say "LAUNCHER_EXECUTABLE  PASS" || say "LAUNCHER_EXECUTABLE  FAIL (chmod +x $L)"

# the wrapper in /etc/env/virtuoso must stay untouched and unexecuted by us
if [ -r /etc/env/virtuoso ]; then
  say "ENV_WRAPPER_READABLE PASS (harvested by $CAD_ENV, never executed)"
else
  say "ENV_WRAPPER_READABLE FAIL"
fi

# 1) does the loader really produce a Cadence environment?
OUT=$(LAUNCHER_CHECK=1 bash "$L" 2>&1)
RC=$?
say "----- launch_virtuoso.sh under LAUNCHER_CHECK=1 (rc=$RC) -----"
say "$OUT"
echo "$OUT" | grep -q 'CHECK CADENCE_ENV_LOADED PASS' \
  && say "CADENCE_ENV_LOADED   PASS" || say "CADENCE_ENV_LOADED   FAIL"
echo "$OUT" | grep -q 'CHECK PROJECT_WORKDIR_CORRECT PASS' \
  && say "PROJECT_WORKDIR_CORRECT PASS ($WORK)" || say "PROJECT_WORKDIR_CORRECT FAIL"
echo "$OUT" | grep -q 'CHECK CDS_LIB_FOUND PASS' \
  && say "CDS_LIB_FOUND        PASS $WORK/cds.lib" || say "CDS_LIB_FOUND        FAIL"

# 2) the desktop entry: syntax, then the handler a double-click goes through
if [ -f "$DESK" ]; then
  say "DESKTOP_ENTRY_EXISTS  PASS $DESK"
  [ -x "$DESK" ] && say "DESKTOP_ENTRY_EXECUTABLE PASS" || say "DESKTOP_ENTRY_EXECUTABLE FAIL"
  DV=$(command -v desktop-file-validate || true)
  if [ -n "$DV" ]; then
    # RHEL6's desktop-file-validate has no --verbose: plain invocation, empty output = clean
    o=$("$DV" "$DESK" 2>&1)
    if [ -z "$o" ]; then say "DESKTOP_FILE_VALIDATE PASS (no complaints)"; else
      say "DESKTOP_FILE_VALIDATE REPORTS:"; say "$o" | head -12
    fi
  else
    say "DESKTOP_FILE_VALIDATE SKIP (tool absent)"
  fi
  # does the Exec target match the launcher we verified?
  EX=$(grep -E '^Exec=' "$DESK" | head -1 | cut -d= -f2)
  [ "$EX" = "$L" ] && say "DESKTOP_EXEC_MATCHES_LAUNCHER PASS ($EX)" \
                    || say "DESKTOP_EXEC_MATCHES_LAUNCHER FAIL ($EX)"
  IC=$(grep -E '^Icon=' "$DESK" | head -1 | cut -d= -f2)
  case "$IC" in /*) [ -f "$IC" ] && say "DESKTOP_ICON_PASS ($IC)" || say "DESKTOP_ICON_FAIL ($IC absent)" ;;
                *) say "DESKTOP_ICON_THEME ($IC)" ;; esac
else
  say "DESKTOP_ENTRY_EXISTS  FAIL $DESK"
fi

# 3) is a desktop session present to attach to, and does the existing user session stay alive?
SOCK=$(ls /tmp/.X11-unix 2>/dev/null | tr '\n' ' ')
say "X_SOCKETS             ${SOCK:-none}"
BEFORE=$(ps -eo pid,args | grep '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | tr '\n' ' ')
say "PRE_EXISTING_VIRTUOSO ${BEFORE:-none} (never signalled by this script)"
say "SCH1_LAUNCHER_VERIFY_DONE"
