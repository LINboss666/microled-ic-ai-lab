#!/bin/bash
# READ-ONLY PDK inventory for the Micro LED feasibility study.
# It only lists, greps and cats. It never writes into any PDK directory:
# the single output file goes under $PROJ (the new project area).
set -u
PROJ="${PROJ:-/root/microled_ai_project}"
TECH="${TECH:-${QODER_TECH_ROOT:-/root/tech}}"
OUT="$PROJ/logs/pdk_inventory_raw_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$PROJ/logs" "$PROJ/reports"

emit() { echo "$@"; }

for p in "$TECH"/*/*; do
  [ -d "$p" ] || continue
  name=$(basename "$p")
  emit "================================================================================"
  emit "PDK_DIR $p"
  emit "SIZE    $(du -sh "$p" 2>/dev/null | cut -f1)"
  emit "--- cds.lib (library name -> path) ---"
  if [ -f "$p/cds.lib" ]; then grep -viE "^\s*(#|$)" "$p/cds.lib" | head -20; else emit "(no cds.lib at top)"; fi
  emit "--- OA libraries present (dirs with tech/lib markers, depth1) ---"
  find "$p" -maxdepth 2 -name "lib.defs" -o -maxdepth 2 -name "cdsinfo" -o -maxdepth 2 -type d -name "*.oa" 2>/dev/null | head -10
  emit "--- spectre model files ---"
  find "$p" -maxdepth 7 -iname "*.scs" 2>/dev/null | head -40
  emit "--- model file count by kind ---"
  for ext in scs mdl l eldo cckt net sp; do
    c=$(find "$p" -maxdepth 7 -iname "*.$ext" 2>/dev/null | wc -l); emit "  .$ext = $c"
  done
  emit "--- master/top include candidates ---"
  for f in spectre.scs toplevel.scs master.scs main.scs; do
    find "$p" -maxdepth 7 -name "$f" 2>/dev/null | head -3
  done
  emit "--- voltage families (dir names) ---"
  find "$p" -maxdepth 4 -type d \( -iname "*1p[0-9]v*" -o -iname "*1_[0-9]v*" -o -iname "*[0-9]v[0-9]*" -o -iname "*[0-9]d[0-9]*" -o -iname "*core*" -o -iname "*io*" \) 2>/dev/null | sed "s#$p#.#" | head -18
  emit "--- DRC / LVS decks ---"
  emit -n "  Assura: "; find "$p" -maxdepth 5 -type d -iname "*assura*" 2>/dev/null | head -3 | tr '\n' ' '; emit ""
  emit -n "  Calibre: "; find "$p" -maxdepth 5 -type d -iname "*calibre*" 2>/dev/null | head -3 | tr '\n' ' '; emit ""
  emit -n "  rules(.il/.sv/.drc): "; find "$p" -maxdepth 5 \( -iname "*.sv" -o -iname "*drc*" -o -iname "*lvs*" \) 2>/dev/null | head -4 | tr '\n' ' '; emit ""
  emit "--- techfile markers ---"
  find "$p" -maxdepth 4 -type d \( -iname "techfile*" -o -iname "Techfile*" -o -iname "tfassets*" \) 2>/dev/null | head -4
  emit -n "  tech db: "; find "$p" -maxdepth 5 -name "tech.db" 2>/dev/null | head -3 | tr '\n' ' '; emit ""
  emit "--- device-library cell samples (MOS-like cell names) ---"
  ls "$p" 2>/dev/null | grep -iE "mos|fet|n[0-9]{2}_|p[0-9]{2}_|nfet|pfet|nch|pch|dev" | head -18
  emit "--- release / foundry identity strings ---"
  for f in "$p"/ReleaseNote.txt "$p"/REVISION* "$p"/pdkInstall.cfg "$p"/PDK_doc/*release* "$p"/README*; do
    [ -f "$f" ] && { emit "  # $f"; grep -aiE "tsmc|smic|umc|gf|tower|insilicon|process|node|0\.18|65nm|180|version|release" "$f" 2>/dev/null | head -6 | sed 's/^/    /'; }
  done
  emit "--- model card: first device .model lines (proves parser target) ---"
  for f in $(find "$p" -maxdepth 7 -iname "*.scs" 2>/dev/null | head -3); do
    emit "  # $f"
    grep -ahiE "^\s*\.(model|model)\s|bsim|level=|section\s" "$f" 2>/dev/null | head -6 | sed 's/^/    /'
  done
done
emit "================================================================================"
emit "END"
