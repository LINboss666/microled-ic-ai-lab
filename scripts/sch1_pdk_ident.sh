#!/bin/bash
# SCH-1 B1: identify the two smic18mmrf candidates by artifacts, not by memory.
# Strictly read-only on both PDK trees. Prints only file names / dates / library
# structure facts, never model-card contents.
set -u

OLD=/root/tech/smic_018mmrf-OA
NEW=/root/microled_ai_project/pdk/smic18mmrf_teacher

echo "=== OLD tree: $OLD ==="
find "$OLD" -maxdepth 3 -type d 2>/dev/null | head -12
echo "-- any cds.lib in the old tree --"
find "$OLD" -maxdepth 4 -name cds.lib 2>/dev/null | head -5
for f in $(find "$OLD" -maxdepth 4 -name cds.lib 2>/dev/null | head -3); do
  echo "   [\$f]"
  grep -vE '^\s*(#|$)' "$f" 2>/dev/null | head -8 | sed 's/^/     /'
done
echo "-- model files the old tree actually carries --"
find "$OLD" -maxdepth 5 \( -name '*.lib' -o -name '*.scs' \) 2>/dev/null | head -12
echo "-- version-ish strings in file names (no content read) --"
find "$OLD" -maxdepth 5 -type f 2>/dev/null | grep -oE '[A-Za-z0-9_]*(v1p[0-9]|V1\.[0-9]|rev[0-9]|REV[0-9]|20[0-9]{2})[A-Za-z0-9_.]*' | sort -u | head -12
echo "-- newest mtime in the old tree (delivery date proxy) --"
find "$OLD" -type f -printf '%TY-%Tm-%Td %p\n' 2>/dev/null | sort -r | head -3
echo "-- old library cell names of interest --"
for c in n18 p18 n33 p33; do
  d=$(find "$OLD" -maxdepth 4 -type d -name "$c" 2>/dev/null | head -1)
  echo "   $c : ${d:-absent}"
done

echo
echo "=== TEACHER tree: $NEW ==="
ls -1 "$NEW" 2>/dev/null | head -12
echo "-- kit cds.lib --"
grep -vE '^\s*(#|$)' "$NEW/cds.lib" 2>/dev/null | head -8
echo "-- OA library dir(s) and their format --"
for d in "$NEW"/smic18mmrf; do
  echo "   $d : $(ls -1 "$d" 2>/dev/null | wc -l) entries; cdsinfo: $(head -1 "$d/cdsinfo.tag" 2>/dev/null)"
done
echo "-- model files (names only) --"
ls -1 "$NEW"/models/spectre/*.lib "$NEW"/models/hspice/*.lib 2>/dev/null | head -8
echo "-- doc file names carry the kit version --"
ls -1 "$NEW"/docs/Pcell_Library 2>/dev/null | head -5
echo "-- newest mtime in the teacher tree --"
find "$NEW" -type f -printf '%TY-%Tm-%Td %p\n' 2>/dev/null | sort -r | head -3
echo "-- teacher cells of interest + their views --"
for c in n18 p18 n33 n33_dnw_4t_ckt; do
  d="$NEW/smic18mmrf/$c"
  if [ -d "$d" ]; then
    echo "   $c : present, views = $(ls -1 "$d" | tr '\n' ' ')"
  else
    echo "   $c : absent"
  fi
done

echo
echo "=== are they the same kit? (mechanical comparison, not opinion) ==="
A=$(ls -1 "$NEW/smic18mmrf" 2>/dev/null | sort | md5sum | cut -c1-12)
echo "   teacher cell-list hash: $A"
B=$(find "$OLD" -maxdepth 4 -type d -name smic18mmrf -o -maxdepth 4 -type d -name 'SMIC_018*' 2>/dev/null | head -1)
echo "   old lib dir: ${B:-none}"
[ -n "${B:-}" ] && echo "   old cell count: $(ls -1 "$B" 2>/dev/null | wc -l)"
echo "   old model card present? $(ls "$OLD" 2>/dev/null | grep -c 'v1p7' ) "
echo "PDK_IDENTITY_PROBE_DONE"
