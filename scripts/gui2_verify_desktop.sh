#!/bin/bash
# GUI-2: verify the WHOLE desktop launch chain, and say plainly which parts are static.
#
#   bash scripts/gui2_verify_desktop.sh
#
# Why this exists: `bash -n` and LAUNCHER_CHECK=1 both kept passing while the desktop icon was
# broken, because the failure was that the Exec target was not executable -- the desktop entry never
# reached the script. A checker that only reads the script cannot see that. So every line of this
# check is derived from what the desktop file actually points at.
#
# Nothing here starts Virtuoso and nothing here touches a running session.
# VIRTUOSO_GUI is reported as UNVERIFIED_BY_THIS_SCRIPT on purpose: use gui2_real_launch.sh for that,
# which proves a process AND a viewable window.
set -u
DESK="${GUI2_DESKTOP:-/root/Desktop/Cadence-Virtuoso-MicroLED.desktop}"
WORK="${GUI2_WORK:-/root/microled_ai_project/cadence_work}"
FAILED=0
ok()   { printf 'CHECK %-26s PASS  %s\n' "$1" "$2"; }
bad()  { printf 'CHECK %-26s FAIL  %s\n' "$1" "$2"; FAILED=1; }
note() { printf 'NOTE  %s\n' "$*"; }

[ -f "$DESK" ] || { bad DESKTOP_ENTRY_MISSING "$DESK"; echo "DESKTOP_ENTRY: FAIL"; exit 8; }

# --- 1. the desktop entry's own usability ---------------------------------------------------
# GNOME/nautilus on RHEL6 needs the .desktop itself to be executable for an icon to be launchable,
# and the file must be LF-terminated for the parser.
MODE=$(stat -c '%a' "$DESK")
case "$MODE" in
  *7|*5) ok DESKTOP_FILE_EXECUTABLE "mode=$MODE" ;;
  *)     bad DESKTOP_FILE_EXECUTABLE "mode=$MODE (icon is not launchable; chmod +x $DESK)" ;;
esac
if [ "$(tr -cd '\r' < "$DESK" | wc -c)" != "0" ]; then
  bad DESKTOP_FILE_LINEENDS "contains CR -- rewrite as LF"
else
  ok DESKTOP_FILE_LINEENDS "LF only"
fi

get() { sed -n "s/^$1=//p" "$DESK" | head -1; }
EXEC=$(get Exec); TRY=$(get TryExec); TYPE=$(get Type); TERM=$(get Terminal); PATH_=$(get Path)
note "Exec=$EXEC"
note "TryExec=${TRY:-<absent>}  Type=$TYPE  Terminal=$TERM  Path=${PATH_:-<absent, GNOME uses the session cwd>}"

# --- 2. Exec / TryExec targets: this is where the real failure was ----------------------------
target=${EXEC%% *}
[ -n "$target" ] || { bad EXEC_KEY_PRESENT "no Exec line"; }
if [ ! -f "$target" ]; then
  bad EXEC_TARGET_EXISTS "$target is missing"
elif [ ! -x "$target" ]; then
  # EACCES on execv is exactly the "There was an error launching the application." dialog.
  bad EXEC_TARGET_EXECUTABLE "$target exists but is NOT executable (execv -> EACCES); chmod +x $target"
else
  ok EXEC_TARGET_EXECUTABLE "$target"
fi
# what GNOME's TryExec pre-check does: access(path, X_OK). Failing it hides/errors the launcher
# before Exec is ever tried, so it must be checked separately from Exec.
if [ -n "$TRY" ]; then
  if [ -x "$TRY" ]; then ok TRYEXEC_ACCESSIBLE "$TRY"; else bad TRYEXEC_ACCESSIBLE "$TRY not executable -> GNOME rejects the entry before running Exec"; fi
fi
# Report the same verdict GNOME's execv would give, without performing it: a checker that runs
# execv on a working Exec target would really start Virtuoso every time it is invoked. os.access(
# X_OK) is the exact predicate that returned EACCES during the incident (errno 13 was measured live
# while the file was mode 644; see reports/lessons_learned/virtuoso_desktop_launch_failure.md).
if [ -f "$target" ]; then
  ACCESS=$(python -c "import os,sys; sys.stdout.write(str(int(os.access('$target', os.X_OK))))" 2>/dev/null)
  if [ "$ACCESS" = "1" ]; then
    ok EXEC_WOULD_BE_EACCES "os.access(X_OK)=true -> execv would succeed"
  else
    bad EXEC_WOULD_BE_EACCES "os.access(X_OK)=false -> execv returns errno 13 EACCES"
  fi
fi

# --- 3. the script content, which is all the earlier checks ever covered ----------------------
if bash -n "$target" 2>/dev/null; then ok LAUNCHER_SYNTAX "$target parses"; else bad LAUNCHER_SYNTAX "bash -n failed"; fi
if [ "$(tr -cd '\r' < "$target" | wc -c)" = "0" ]; then ok LAUNCHER_LINEENDS "LF only"; else bad LAUNCHER_LINEENDS "launcher contains CR"; fi

OUT=$(LAUNCHER_CHECK=1 bash "$target" 2>&1)
for k in CADENCE_ENV_LOADED PROJECT_WORKDIR_CORRECT CDS_LIB_FOUND; do
  if printf '%s\n' "$OUT" | grep -q "CHECK $k PASS"; then ok "$k" "reported PASS by the launcher itself"
  else bad "$k" "$(printf '%s\n' "$OUT" | grep "CHECK $k" | head -1)"; fi
done
if printf '%s\n' "$OUT" | grep -q "LAUNCHER_CHECK: PASS"; then ok LAUNCHER_CHECK "static"; else bad LAUNCHER_CHECK "launcher reported FAIL"; fi
printf '%s\n' "$OUT" | grep -E "^      (theme|DISPLAY|virtuoso|cds.lib)" | sed 's/^/  /'

# --- 4. the appearance feature must still be wired up ----------------------------------------
RES=$(printf '%s\n' "$OUT" | sed -n 's/.*resource_file=\(.*\)$/\1/p' | head -1)
if [ -n "$RES" ] && [ "$RES" != "none" ] && [ -f "$RES" ]; then
  ok WHITE_THEME_WIRED "resource_file=$RES"
  if grep -q "editorBackground" "$RES"; then ok WHITE_THEME_CONTENTS "sets Opus.editorBackground"; else bad WHITE_THEME_CONTENTS "no editorBackground in $RES"; fi
else
  note "WHITE_THEME not active in this run (resource_file=${RES:-unset}) -- enable with scripts/gui1_white_theme.sh enable"
fi

echo
echo "DESKTOP_ENTRY: $([ "$FAILED" = 0 ] && echo PASS || echo FAIL)"
echo "VIRTUOSO_GUI: UNVERIFIED_BY_THIS_SCRIPT (static checks only; run scripts/gui2_real_launch.sh,"
echo "              which proves a virtuoso process AND a viewable window on the session display)"
note "LAUNCHER_CHECK: PASS on its own does NOT mean the desktop icon works -- that is the exact"
note "confusion that hid this bug. A passing run here still needs the dynamic check."
[ "$FAILED" = 0 ] || exit 7
exit 0
