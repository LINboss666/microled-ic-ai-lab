#!/bin/bash
# Register the existing OA library microled_scan_s3c in the cds.lib that the desktop shortcut's
# Virtuoso session actually reads. One DEFINE, nothing else.
#
# Which file this is allowed to touch, and why: /root/Desktop/Cadence-Virtuoso-MicroLED.desktop execs
# /root/microled_ai_project/cadence_work/launch_virtuoso.sh; that launcher does `cd "$WORK"` and then
# `exec virtuoso -log ...` with no -cdslib argument, so the session resolves $WORK/cds.lib -- the same
# file the user's Open File dialog reported as "Library path file". The S3-C round deliberately kept
# that map untouched and registered the library only in s3c_oa/cds.lib, which is why the isolated
# batch sessions see the library and the desktop session does not.
#
# Refusals, in order: target library directory absent (report BLOCKED, never rebuild), the name
# already defined with the same path (no-op, idempotent), the name already defined with a DIFFERENT
# path (report CONFLICT and change nothing). Other DEFINE/INCLUDE lines, the PDK, microled_cells and
# data_sink_1ch are not read-modified here. A timestamped backup is written next to the file before
# any write, and the whole change is shown as a diff so the scope is checkable.
#
#   PROJ=/root/microled_ai_project bash scripts/sc1_libregister.sh
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
LIB_NAME=microled_scan_s3c
LIB_DIR="$WORK/s3c_oa/$LIB_NAME"
CDS_LIB="$WORK/cds.lib"
STAMP="${STAMP:-20261015_libreg}"
BAK="$CDS_LIB.bak.$STAMP"

[ -f "$CDS_LIB" ] || { echo "BLOCKED: $CDS_LIB missing -- the shortcut session would show no libraries at all"; exit 6; }
if [ ! -d "$LIB_DIR" ]; then
  echo "BLOCKED: $LIB_DIR not found; not rebuilding a library"
  exit 6
fi
for v in schematic symbol; do
  [ -f "$LIB_DIR/sc1_scan_power_1ch_s3c/$v/master.tag" ] \
    || { echo "BLOCKED: top view $LIB_NAME/sc1_scan_power_1ch_s3c/$v is not on disk"; exit 6; }
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
  printf '# dir, no -cdslib), so the scan driver library built under s3c_oa has to be named here as well.\n'
  printf '# One DEFINE; every pre-existing mapping is untouched.\n'
  printf 'DEFINE %s %s\n' "$LIB_NAME" "$LIB_DIR"
} >> "$CDS_LIB"

echo "BACKUP $BAK"
echo "CDS_LIB_SHA_BEFORE $before"
echo "CDS_LIB_SHA_AFTER  $(sha256sum "$CDS_LIB" | cut -d' ' -f1)"
echo "DEFINE_COUNT_AFTER $(grep -cE '^[[:space:]]*DEFINE' "$CDS_LIB")"
echo "TARGET_LINES $(grep -cE "^[[:space:]]*DEFINE[[:space:]]+$LIB_NAME" "$CDS_LIB")"
echo "---- diff backup vs current ----"
diff -u "$BAK" "$CDS_LIB" | sed -n '1,40p'
echo "LIBREGISTER: DONE $LIB_NAME -> $LIB_DIR"
