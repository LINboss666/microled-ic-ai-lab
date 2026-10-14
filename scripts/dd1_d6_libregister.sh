#!/bin/bash
# DATA-6 section 8: register microled_data_d6 in the ONE library map the desktop shortcut reads.
#
# Copy-by-value of the accepted scripts/sc1_libregister.sh (not modified), with this task's library,
# path and top cell. Same rules, same reasons: the shortcut's session resolves cadence_work/cds.lib,
# so a library that only exists in an isolated work directory is invisible to the user; the file is
# backed up before anything is appended; exactly one DEFINE is added; an existing mapping for the
# same name that points elsewhere is reported and NOT overwritten; the sha256 before and after plus a
# unified diff make "nothing else changed" a checkable statement.
#
#   PROJ=/root/microled_ai_project bash scripts/dd1_d6_libregister.sh
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
LIB_NAME=microled_data_d6
LIB_DIR="$WORK/data_d6_oa/$LIB_NAME"
CDS_LIB="$WORK/cds.lib"
STAMP="${STAMP:-dd1_d6_libreg}"
BAK="$CDS_LIB.bak.$STAMP"

[ -f "$CDS_LIB" ] || { echo "BLOCKED: $CDS_LIB missing -- the shortcut session would show no libraries at all"; exit 6; }
[ -d "$LIB_DIR" ] || { echo "BLOCKED: $LIB_DIR not found; not rebuilding a library"; exit 6; }
for v in schematic symbol; do
  [ -f "$LIB_DIR/dd1_data_top_1ch/$v/master.tag" ] \
    || { echo "BLOCKED: top view $LIB_NAME/dd1_data_top_1ch/$v is not on disk"; exit 6; }
done

if grep -qE "^[[:space:]]*DEFINE[[:space:]]+$LIB_NAME[[:space:]]+$LIB_DIR[[:space:]]*\$" "$CDS_LIB"; then
  echo "ALREADY_REGISTERED $LIB_NAME -> $LIB_DIR (no change made)"
  exit 0
fi
if grep -qE "^[[:space:]]*DEFINE[[:space:]]+$LIB_NAME([[:space:]]|\$)" "$CDS_LIB"; then
  echo "CONFLICT: $LIB_NAME is already defined, pointing somewhere else:"
  grep -nE "^[[:space:]]*DEFINE[[:space:]]+$LIB_NAME" "$CDS_LIB"
  echo "NOT OVERWRITING an existing mapping; reporting only"
  exit 7
fi

cp -n "$CDS_LIB" "$BAK" || { echo "BLOCKED: could not create $BAK"; exit 6; }
before=$(sha256sum "$CDS_LIB" | cut -d' ' -f1)
{
  printf '\n'
  printf '# %s: the desktop shortcut session reads this map (cadence_work/launch_virtuoso.sh cds the work\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '# dir, no -cdslib), so the DATA-6 one-bit data unit library built under data_d6_oa has to be\n'
  printf '# named here as well. One DEFINE; every pre-existing mapping is untouched.\n'
  printf 'DEFINE %s %s\n' "$LIB_NAME" "$LIB_DIR"
} >> "$CDS_LIB"

echo "BACKUP $BAK"
echo "CDS_LIB_SHA_BEFORE $before"
echo "CDS_LIB_SHA_AFTER  $(sha256sum "$CDS_LIB" | cut -d' ' -f1)"
echo "DEFINE_COUNT_AFTER $(grep -cE '^[[:space:]]*DEFINE' "$CDS_LIB")"
echo "TARGET_LINES $(grep -cE "^[[:space:]]*DEFINE[[:space:]]+$LIB_NAME" "$CDS_LIB")"
echo "--- diff against the backup ---"
diff -u "$BAK" "$CDS_LIB" | sed -n '1,30p'
echo "LIBREGISTER: DONE $LIB_NAME -> $LIB_DIR"
exit 0
