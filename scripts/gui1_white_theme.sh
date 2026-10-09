#!/bin/bash
# GUI-1: switch the Micro LED Virtuoso session between the white and the original theme, and
# validate that the mechanism being changed is the one this build actually uses.
#
#   DISPLAY=:0 bash scripts/gui1_white_theme.sh enable     # WHITE_THEME_ENABLE
#   DISPLAY=:0 bash scripts/gui1_white_theme.sh restore    # RESTORE_ORIGINAL_THEME
#           ... bash scripts/gui1_white_theme.sh status
#           ... bash scripts/gui1_white_theme.sh validate
#   DISPLAY=:0 bash scripts/gui1_white_theme.sh selfcheck
#
# The mechanism, chosen on measured grounds (see reports/virtuoso_white_background.md):
#   * IC6.1.7-64b.78 has no "Default Editor Background Color" entry: the string "Editor Background
#     Color" appears nowhere under /opt/IC617/tools/dfII, so the CIW Options -> User Preferences
#     route newer versions offer is not available here. That was checked, not assumed.
#   * the design-window background is the X resource Opus.editorBackground -- this installation's own
#     dfIIconfigStartup.html calls it "Color of design window background", and "editorBackground" is
#     an exact string inside the installed virtuoso binary. Opus.dragColor is included because its
#     documented meaning is the selection box, the zoom box and the move/stretch outlines, whose
#     stock white value would be invisible on a white canvas.
#   * exactly ONE channel is used: merging the project's resource file into the X session database
#     with xrdb, which is what Cadence's own sample resource file prescribes ("you need to run the
#     xrdb program to have a resource take effect once the X server has been started"). Handing the
#     file over through XENVIRONMENT was tried first and could not be verified on this machine,
#     because pixel capture from this X server does not work (root grabs come back flat, per-window
#     grabs come back black or "Resource temporarily unavailable") and Cadence maps no paintable
#     window in a batch session. The unverifiable route was dropped rather than shipped on an
#     assumption -- see scripts/gui1_xt_delivery_test.sh and scripts/gui1_window_capture.sh.
#
# Session-wide impact, stated deliberately: xrdb changes the X session's resource database, so any
# other Virtuoso started in the same X session also sees these two Opus resources. Only Opus.* keys
# are added; the database as found is snapshotted into cadence_work/appearance/backup/ before the
# first merge, and "restore" reloads exactly that snapshot.
#
# Idempotency: merging the same key/value repeatedly leaves one entry (selfcheck proves it), and the
# pointer files are rewritten from scratch, never appended.
set -u
PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
ADIR="$WORK/appearance"
BACKUP="$ADIR/backup"
BIN="${CDS_VIRTUOSO_BIN:-/opt/IC617/tools/dfII/bin/64bit/virtuoso}"
MODE="${1:-status}"
DIO="${DISPLAY:-}"
SNAP="$BACKUP/xrdb_query_original.txt"

[ -d "$ADIR" ] || { echo "REFUSE: $ADIR missing"; exit 9; }
mkdir -p "$BACKUP"

theme_file() {
  case "$1" in
    white)    echo "$ADIR/white/xresources.txt" ;;
    original) echo "$ADIR/original/xresources.txt" ;;
    *) return 1 ;;
  esac
}

xr() { DISPLAY="$DIO" xrdb "$@"; }

snapshot_db() {
  [ -n "$DIO" ] || return 0
  if [ ! -s "$SNAP" ]; then
    xr -query > "$SNAP" 2>&1
    echo "DATABASE_SNAPSHOT: $SNAP ($(grep -c . "$SNAP" 2>/dev/null || echo 0) lines)"
  fi
}

write_state() {   # $1 white|original
  local t="$1" f
  if ! f="$(theme_file "$t")"; then echo "REFUSE: unknown theme $t"; return 1; fi
  [ -f "$f" ] || { echo "REFUSE: theme file $f does not exist"; return 1; }
  printf '%s\n' "$t" > "$ADIR/theme"
  printf '%s\n' "$f" > "$ADIR/active_resources"
  echo "THEME=$t"
  echo "THEME_POINTER: $ADIR/theme"
  echo "RESOURCE_FILE: $f"
  return 0
}

apply_db() {   # $1 merge|restore
  local mode="$1" f
  if [ -z "$DIO" ]; then
    echo "APPLY: SKIPPED (no DISPLAY; the desktop launcher applies the theme at session start)"
    return 0
  fi
  if [ "$mode" = restore ]; then
    if [ -s "$SNAP" ]; then
      xr -load "$SNAP" && echo "APPLY: reloaded the backed-up database (Opus keys gone)"
    else
      echo "APPLY: no original snapshot to restore; the database was left alone"
      return 1
    fi
  else
    snapshot_db
    f="$(cat "$ADIR/active_resources" 2>/dev/null)"
    [ -f "${f:-}" ] || { echo "APPLY: no active_resources pointer; run enable first"; return 1; }
    xr -merge "$f" && echo "APPLY: merged $f"
  fi
  xr -query 2>/dev/null | grep -E '^Opus\.' | sed 's/^/  DB_OPUS /'
  return 0
}

validate() {
  local rc=0 name n p
  for name in editorBackground dragColor; do
    # strings is the reading that works: grep -x on a binary compares NUL-delimited chunks
    n=$(strings "$BIN" 2>/dev/null | grep -cx "$name")
    if [ "${n:-0}" -ge 1 ]; then echo "RESOURCE_NAME_IN_INSTALLED_BINARY $name: PASS (hits=$n)"
    else echo "RESOURCE_NAME_IN_INSTALLED_BINARY $name: FAIL ($BIN)"; rc=1; fi
  done
  if grep -q --binary-files=text "Opus.editorBackground" /opt/IC617/doc/dfIIconfig/dfIIconfigStartup.html 2>/dev/null; then
    echo "RESOURCE_DOCUMENTED_LOCALLY: PASS"
  else
    echo "RESOURCE_DOCUMENTED_LOCALLY: FAIL"; rc=1
  fi
  if [ -f "$BIN" ] && strings "$BIN" 2>/dev/null | grep -q "Editor Background Color"; then
    echo "USER_PREFERENCES_FIELD_AVAILABLE: YES (unexpected here -- re-check before using that route)"
  else
    echo "USER_PREFERENCES_FIELD_AVAILABLE: NO (the X-resource route is the supported path on this build)"
  fi
  for p in white original; do
    if [ -f "$(theme_file "$p")" ]; then
      echo "THEME_FILE $p: PASS $(wc -c < "$(theme_file "$p")") bytes"
    else echo "THEME_FILE $p: FAIL"; rc=1; fi
  done
  # Cadence's sample file warns that loose "Opus*resource:" bindings can conflict with SKILL
  if grep -hE '^Opus[*]' "$ADIR/white/xresources.txt" "$ADIR/original/xresources.txt" 2>/dev/null | grep -q .; then
    echo "BINDING_STYLE: FAIL (loose Opus* bindings found)"; rc=1
  else
    echo "BINDING_STYLE: PASS (tight Opus.resource bindings only)"
  fi
  if grep -q 'active_resources' "$WORK/launch_virtuoso.sh" 2>/dev/null; then
    echo "LAUNCHER_WIRED: PASS"
  else
    echo "LAUNCHER_WIRED: FAIL (the launcher would not apply the theme on start)"; rc=1
  fi
  if grep -q 'xrdb -merge' "$WORK/launch_virtuoso.sh" 2>/dev/null \
     && grep -q 'xrdb -query > ' "$WORK/launch_virtuoso.sh" 2>/dev/null \
     && grep -q 'xrdb -load' "$PROJ/scripts/gui1_white_theme.sh" 2>/dev/null; then
    echo "SESSION_IMPACT_HANDLED: PASS (launcher snapshots then merges; restore reloads the snapshot)"
  else
    echo "SESSION_IMPACT_HANDLED: FAIL (a merge with no snapshot/restore path is a one-way change)"
    rc=1
  fi
  for token in CADENCE_ENV_LOADED PROJECT_WORKDIR_CORRECT CDS_LIB_FOUND; do
    if grep -q "$token" "$WORK/launch_virtuoso.sh"; then
      echo "LAUNCHER_CHECK_PRESERVED $token: PASS"
    else
      echo "LAUNCHER_CHECK_PRESERVED $token: FAIL"; rc=1
    fi
  done
  echo "THEME_VALIDATE: $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
  return $rc
}

selfcheck() {
  local rc=0 n before after left
  [ -n "$DIO" ] || { echo "SELFCHECK needs DISPLAY (it measures the real resource database)"; return 9; }
  write_state white > /dev/null
  apply_db merge > /dev/null; apply_db merge > /dev/null; apply_db merge > /dev/null
  n=$(xr -query | grep -c '^Opus\.editorBackground')
  echo "IDEMPOTENT_OPUS_EDITORBACKGROUND_ENTRIES_AFTER_3_MERGES: $n (want 1)"
  [ "$n" = "1" ] || rc=1
  snapshot_db
  before=$(xr -query | grep -c .)
  apply_db restore > /dev/null
  after=$(xr -query | grep -c .)
  left=$(xr -query | grep -c '^Opus\.')
  echo "DATABASE_LINES: before_restore=$before after_restore=$after opus_keys_left=$left"
  [ "$left" = "0" ] || { echo "RESTORE_DID_NOT_REMOVE_OPUS_KEYS"; rc=1; }
  [ "$after" -ge 1 ] || { echo "RESTORE_EMPTIED_THE_WHOLE_DATABASE"; rc=1; }
  apply_db merge > /dev/null
  echo "ROUND_TRIP_OPUS_KEYS_AFTER_REENABLE: $(xr -query | grep -c '^Opus\.')"
  xr -query | grep -E '^Opus\.' | sed 's/^/  /'
  echo "SELFCHECK: $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
  return $rc
}

case "$MODE" in
  enable)    write_state white && apply_db merge ;;
  restore)   apply_db restore; write_state original ;;
  status)
    printf 'CURRENT_THEME: %s\n' "$(cat "$ADIR/theme" 2>/dev/null || echo unset)"
    printf 'RESOURCE_FILE: %s\n' "$(cat "$ADIR/active_resources" 2>/dev/null || echo none)"
    if [ -n "$DIO" ]; then
      printf 'OPUS_KEYS_LIVE_ON_%s: %s\n' "$DIO" "$(xr -query 2>/dev/null | grep -c '^Opus\.')"
      xr -query 2>/dev/null | grep -E '^Opus\.' | sed 's/^/  /'
    else
      echo "OPUS_KEYS_LIVE: unknown (set DISPLAY to query a running session)"
    fi
    ;;
  validate)  validate ;;
  selfcheck) selfcheck ;;
  *) echo "usage: gui1_white_theme.sh {enable|restore|status|validate|selfcheck}"; exit 9 ;;
esac
