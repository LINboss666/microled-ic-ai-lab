#!/bin/bash
# GUI-1 section 7: verify the white-background configuration with what this machine can actually
# measure, and say out loud what it cannot.
#
#   DISPLAY=:0 bash scripts/gui1_verify_theme.sh
#
# Measurable here:
#   CONFIGURATION_VALIDATION   the resource names are ones the installed binary looks up and the
#                              local manual documents; files parse; bindings are tight
#   DATABASE_VALIDATION        enable -> the two Opus keys really land in the X session database
#                              (xrdb -query readback); three merges still give one entry;
#                              restore -> the backed-up database comes back and no Opus key remains
#   LAUNCHER_VALIDATION        the desktop launcher's own SCH-1 checks still pass, and it reports
#                              the theme/resource file it is about to apply
#
# NOT measurable on this machine, and therefore reported as pending instead of claimed:
#   GUI_VISUAL_VERIFICATION    a screenshot of a painted design window. Two independent reasons were
#                              measured: pixel capture from this X server does not work (root grabs
#                              come back flat; per-window grabs come back black or "Resource
#                              temporarily unavailable" -- see results/evidence/gui1_capture_*.txt
#                              and scripts/gui1_xt_delivery_test.sh, where even a plain xmessage
#                              window read black in all three configurations), and a batch-created
#                              Virtuoso session never maps a paintable window (the CIW reports
#                              "Map State: IsUnMapped", and the graphics window Cadence creates is
#                              not repainted until a cellview is drawn in it, which SKILL cannot do
#                              here: hiOpenWindow(?appType "Schematic") => nil).
#
# No circuit database is touched by anything in this script (GUI-1 section 8).
set -u
PROJ="${PROJ:-/root/microled_ai_project}"
W="$PROJ/cadence_work"
OUTD="$W/logs"
DIO="${DISPLAY:-}"
[ -n "$DIO" ] || { echo "REFUSE: set DISPLAY (the desktop session's own value) so the database can be read back"; exit 9; }
export DISPLAY="$DIO"
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUTD"
rc_total=0

echo "##### 1. configuration #####"
if bash "$PROJ/scripts/gui1_white_theme.sh" validate > "$OUTD/gui1_validate_$STAMP.log" 2>&1 \
   && grep -q "THEME_VALIDATE: PASS" "$OUTD/gui1_validate_$STAMP.log"; then
  echo "CONFIGURATION_VALIDATION: PASS"
else
  echo "CONFIGURATION_VALIDATION: FAIL"; rc_total=1
fi
grep -E "RESOURCE_NAME_IN_INSTALLED_BINARY|RESOURCE_DOCUMENTED_LOCALLY|USER_PREFERENCES_FIELD|BINDING_STYLE|THEME_FILE|LAUNCHER_WIRED|SESSION_IMPACT_HANDLED|LAUNCHER_CHECK_PRESERVED|THEME_VALIDATE" \
    "$OUTD/gui1_validate_$STAMP.log" | sed 's/^/  /'

echo
echo "##### 2. the X session database, enable -> idempotency -> restore -> re-enable #####"
if bash "$PROJ/scripts/gui1_white_theme.sh" selfcheck > "$OUTD/gui1_selfcheck_$STAMP.log" 2>&1 \
   && grep -q "SELFCHECK: PASS" "$OUTD/gui1_selfcheck_$STAMP.log"; then
  echo "DATABASE_VALIDATION: PASS"
else
  echo "DATABASE_VALIDATION: FAIL"; rc_total=1
fi
grep -E "IDEMPOTENT_|DATABASE_LINES|RESTORE_|ROUND_TRIP_|DB_OPUS|Opus\.|SELFCHECK" "$OUTD/gui1_selfcheck_$STAMP.log" | sed 's/^/  /'

echo
echo "##### 3. the desktop launcher #####"
if LAUNCHER_CHECK=1 bash "$W/launch_virtuoso.sh" > "$OUTD/gui1_launcher_check_$STAMP.log" 2>&1 \
   && grep -q "LAUNCHER_CHECK: PASS" "$OUTD/gui1_launcher_check_$STAMP.log"; then
  echo "LAUNCHER_VALIDATION: PASS"
else
  echo "LAUNCHER_VALIDATION: FAIL"; rc_total=1
fi
grep -E "^CHECK |theme     :|virtuoso  :" "$OUTD/gui1_launcher_check_$STAMP.log" | sed 's/^/  /'
if grep -Eq "theme     : white  resource_file=$W/appearance/white/xresources.txt" "$OUTD/gui1_launcher_check_$STAMP.log"; then
  echo "AUTO_LOAD_ON_NEXT_START: YES (the launcher resolves and merges the theme file itself)"
else
  echo "AUTO_LOAD_ON_NEXT_START: NO"; rc_total=1
fi
# check mode must not change session state: the launcher applies xrdb only when it really starts
if grep -q "APPLY" "$OUTD/gui1_launcher_check_$STAMP.log"; then
  echo "CHECK_MODE_IS_SIDE_EFFECT_FREE: FAIL"; rc_total=1
else
  echo "CHECK_MODE_IS_SIDE_EFFECT_FREE: PASS"
fi

echo
echo "##### 4. what stays a human check #####"
echo "GUI_VISUAL_VERIFICATION: PENDING_USER_REVIEW"
echo "  reasons measured, not assumed: pixel capture from this X server is broken, and a batch"
echo "  session maps no paintable window; see the header of this script and results/evidence/."
echo
echo "ARTIFACTS: $OUTD/gui1_{validate,selfcheck,launcher_check}_$STAMP.log"
echo "GUI1_VERIFY_DONE rc_total=$rc_total"
[ "$rc_total" -eq 0 ] || exit 1
exit 0
