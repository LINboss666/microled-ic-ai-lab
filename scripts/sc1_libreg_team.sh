#!/bin/bash
# Register THIS round's library in the cds.lib that the desktop shortcut actually reads.
#
# Why this exists: scripts/sc1_s3c_setup.sh deliberately writes an isolated map under
# cadence_work/s3c_oa/ and proves the shared file is untouched. That is right for the batch
# sessions, but acceptance item 1 asks for the eight cells to appear in the Library Manager the
# user opens normally, and that session resolves cadence_work/cds.lib (the launcher does
# `cd $WORK` and passes no -cdslib). So exactly one DEFINE has to be added to the shared map.
#
# Adopted by reference from the source branch's scripts/sc1_libregister.sh (commit 0038821, read
# through `git show`, not merged): check the library is really on disk first, then treat three
# cases apart -- already registered at the same path (do nothing), registered at a different path
# (refuse, never overwrite), absent (back up, append one line). Idempotent by construction.
#
#   PROJ=/root/microled_ai_project LIB=sc1_s3c_team_pretty bash scripts/sc1_libreg_team.sh
set -u

PROJ="${PROJ:-/root/microled_ai_project}"
WORK="$PROJ/cadence_work"
LIB="${LIB:?REFUSE: LIB is required}"
# the delivered top of this hierarchy, per scripts/sc1_s3c_golden.py CELL_ORDER
TOPC="${TOPC:-sc1_scan_power_1ch_s3c}"
LIBDIR="${LIBDIR:-$WORK/s3c_oa/$LIB}"
SHARED="$WORK/cds.lib"
STAMP="$(date +%Y%m%d_%H%M%S)"

[ -r "$SHARED" ] || { echo "REFUSE: $SHARED unreadable"; exit 9; }
[ -d "$LIBDIR" ] || { echo "REFUSE: library dir not on disk: $LIBDIR"; exit 9; }
for V in schematic symbol; do
  [ -e "$LIBDIR/$TOPC/$V" ] || { echo "REFUSE: $LIB/$TOPC has no $V view on disk"; exit 9; }
done

BEFORE=$(sha256sum "$SHARED" | cut -d' ' -f1)
DEF_LINES_BEFORE=$(grep -cE '^[[:space:]]*DEFINE' "$SHARED")
HIT=$(grep -nE "^[[:space:]]*DEFINE[[:space:]]+${LIB}([[:space:]]|$)" "$SHARED" || true)

if [ -n "$HIT" ]; then
  SAME=$(printf '%s\n' "$HIT" | grep -cF "$LIBDIR" || true)
  if [ "$SAME" -ge 1 ]; then
    echo "ALREADY_REGISTERED: $LIB points at $LIBDIR -- no change made"
    printf '%s\n' "$HIT" | sed 's/^/  /'
  else
    echo "CONFLICT: $LIB is already defined at a different path; refusing to rewrite it"
    printf '%s\n' "$HIT" | sed 's/^/  EXISTING /'
    echo "  intended: $LIBDIR"
    exit 9
  fi
else
  cp -n "$SHARED" "$WORK/cds.lib.bak.${STAMP}_libreg" || { echo "REFUSE: backup failed"; exit 9; }
  echo "BACKUP: $WORK/cds.lib.bak.${STAMP}_libreg"
  {
    echo ""
    echo "# Added by scripts/sc1_libreg_team.sh on ${STAMP}: this round's own rebuilt library."
    echo "# One DEFINE only; every line above is untouched. Delete these three lines to revert."
    echo "DEFINE ${LIB} ${LIBDIR}"
  } >> "$SHARED"
  echo "APPENDED: DEFINE ${LIB} ${LIBDIR}"
fi

AFTER=$(sha256sum "$SHARED" | cut -d' ' -f1)
DEF_LINES_AFTER=$(grep -cE '^[[:space:]]*DEFINE' "$SHARED")
echo "DEFINE_LINES $DEF_LINES_BEFORE -> $DEF_LINES_AFTER"
echo "SHA256_BEFORE=$BEFORE"
echo "SHA256_AFTER=$AFTER"
if [ "$DEF_LINES_BEFORE" = "$DEF_LINES_AFTER" ] && [ "$BEFORE" = "$AFTER" ]; then
  echo "SHARED_CDS_LIB_UNCHANGED: yes"
else
  echo "SHARED_CDS_LIB_DIFF:"
  diff -u "$WORK/cds.lib.bak."*_libreg "$SHARED" 2>/dev/null | sed 's/^/  /' || true
fi
echo "OTHER_DEFS_INTACT=$(grep -cE '^[[:space:]]*DEFINE (cdsDefTechLib|basic|analogLib|smic18mmrf|microled_cells|microled_dirver0)\b' "$SHARED")/6"
echo "S3C_LIBREG_TEAM: done lib=$LIB"
exit 0
