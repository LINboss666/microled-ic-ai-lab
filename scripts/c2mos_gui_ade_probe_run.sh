#!/bin/bash
# GUI/ADE read-only probe driver (the run that produced
# reports/c2mos_gui_ade_probe.md). Header note kept verbatim from the session.
# Phase note: it does NOT write anything; it drives skill/c2mos_gui_ade_probe.il through
# the repo's own verified launch chain and manifests microled_cells before and after.
#
# Original comment follows.
# ---
# GUI/ADE read-only probe driver for the current phase. Reuses the repo's verified launch chain
# (scripts/gui2_envenvexec.sh -> the GNOME session's own environment, and scripts/sch_virtuoso.sh ->
# the isolated .cdsinit injection). Writes nothing into the project except logs/ under cadence_work
# (which the runner always creates) and /tmp scratch. Takes manifests before and after so any
# surprise object created by an ADE call is caught.
set -u
P=/root/microled_ai_project
M=/tmp/tb_audit
mkdir -p "$M"

echo "### S2 PRE-FLIGHT (live, nothing hardcoded)"
date
GP=$(pgrep -f gnome-session | head -1)
echo "gnome_session_pid=$GP"
if [ -n "$GP" ] && [ -r "/proc/$GP/environ" ]; then
  tr '\0' '\n' < "/proc/$GP/environ" | grep -E '^(DISPLAY|XAUTHORITY|HOME|USER|XDG_SESSION_TYPE|WAYLAND_DISPLAY)=' | sed 's/^/  env /'
else
  echo "  env UNREADABLE"
fi
echo "  x_sockets=$(ls /tmp/.X11-unix 2>/dev/null | tr '\n' ' ')"
echo "  logged_in_users=$(who 2>/dev/null | tr '\n' ';')"
BEFORE=$(ps -eo pid,args | grep -E '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | tr '\n' ' ')
echo "  virtuoso_pids_before=[$BEFORE]"
[ -n "$BEFORE" ] && echo "  USER_SESSION_PRESENT -- this driver will NOT kill it and will report only"
echo "  xprop=$(command -v xprop || echo MISSING)  wmctrl=$(command -v wmctrl || echo MISSING)"
ENVE="$P/scripts/gui2_envexec.sh"
[ -f "$ENVE" ] || ENVE=/tmp/gui2_envexec.sh
echo "  envexec_helper=$ENVE"

echo "### MANIFEST BEFORE"
find "$P/cadence_work/microled_cells" -type f ! -name '*.cdslck' | sort | xargs md5sum > "$M/gap_cells_before.md5" 2>/dev/null
echo "  cells_files=$(grep -c . "$M/gap_cells_before.md5")"
ls -A "$P/cadence_work" | sort > "$M/gap_cw_before.txt"
md5sum "$P/cadence_work/microled_cells/c2mos_dff_1bit/schematic/sch.oa" \
       "$P/cadence_work/microled_cells/c2mos_dff_tb/schematic/sch.oa" | sed 's/^/  FINGERPRINT /'
echo "  analogLib_files_newer_than_2026-10-12=$(find /opt/IC617/tools/dfII/etc/cdslib/artist/analogLib -type f -newermt 2026-10-12 2>/dev/null | wc -l)"
echo "  PDK_files_newer_than_2026-10-12=$(find /root/tech/teacher_pdk -type f -newermt 2026-10-12 2>/dev/null | wc -l)"
echo "  locks_now=$(find "$P/cadence_work/microled_cells" -name '*.cdslck' | wc -l)"

run_probe() {
  tag="$1"; shift
  echo "### PROBE [$tag] env: $*"
  # gui2_envexec.sh applies the GNOME session environment ONLY when it is handed a program and no
  # extra arguments (verified usage in scripts/gui2_real_launch.sh: `bash gui2_envexec.sh <prog>`).
  # Anything else lands after the first non-KEY=VALUE token and env stops exporting, which is exactly
  # how the first attempt of this probe died with "REFUSED: MODE=gui needs DISPLAY". So the per-run
  # variables go into a wrapper script, and the wrapper is the only argument.
  W="$M/gap_launch_$tag.sh"
  { echo '#!/bin/bash'
    echo "set -u"
    for kv in "$@"; do echo "export $kv"; done
    echo "exec bash \"$P/scripts/sch_virtuoso.sh\" \"$P/skill/c2mos_gui_ade_probe.il\" 300 GAP_DONE"
  } > "$W"
  chmod +x "$W"
  touch "$M/marker_$tag"
  while pgrep -f '/opt/IC617.*/virtuoso' >/dev/null; do echo "  waiting for a previous session to close"; sleep 10; done
  echo "  .cdsinit this run will read (attribution proof):"
  sed 's/^/    /' "$P/cadence_work/home/.cdsinit" 2>/dev/null || echo "    (none yet)"
  setsid nohup bash "$ENVE" "$W" > "$M/gap_$tag.out" 2>&1 < /dev/null &
  i=0
  while [ "$i" -lt 44 ]; do
    i=$((i + 1)); sleep 5
    VP=$(pgrep -f '/opt/IC617.*/virtuoso' | head -1)
    if [ -n "$VP" ] && [ "$i" -ge 3 ]; then
      WS=$(bash "$ENVE" "$M/gap_winstates.sh" 2>/dev/null | grep -a -i -E 'opus|virtuoso|ciw' | head -4 | tr '\n' '|')
      echo "  [t=$((i*5))s] virtuoso_pid=$VP gui_windows=${WS:-none-yet}"
    fi
    if grep -qs "SCH_VIRTUOSO:" "$M/gap_$tag.out"; then
      echo "  [t=$((i*5))s] probe finished"; break
    fi
  done
  echo "--- verdict lines [$tag] ---"
  grep -aE 'SCH_VIRTUOSO|RESULT rc|TOKEN_FOUND' "$M/gap_$tag.out" | sed 's/^/  /'
  echo "--- GAP lines [$tag] ---"
  { grep -ah 'GAP' "$M/gap_$tag.out" 2>/dev/null; } | sed 's/^/  /' | sort -u
}

printf '#!/bin/bash\nexport DISPLAY=%s\nexport XAUTHORITY=%s\nexec xprop -root _NET_CLIENT_LIST 2>&1\n' \
  "$(tr '\0' '\n' < "/proc/$GP/environ" | sed -n 's/^DISPLAY=//p')" \
  "$(tr '\0' '\n' < "/proc/$GP/environ" | sed -n 's/^XAUTHORITY=//p')" > "$M/gap_xprop.sh"
chmod +x "$M/gap_xprop.sh"

# The DEFER=1 variant is dropped on purpose. The hook scripts/sch_virtuoso.sh uses for it,
# hiSetInitFunc, is undefined on this build: two GUI sessions died with
# "*Error* eval: undefined function - hiSetInitFunc" before the probe body ran, and a strings sweep
# over every dfII context finds no such symbol. Asking the same question again would only burn a
# session, so it is reported as a measured fact instead.
echo "### hiSetInitFunc availability (the hook a deferred run would need)"
if grep -rla 'hiSetInitFunc' /opt/IC617/tools.lnx86/dfII/etc/context/64bit/ >/dev/null 2>&1; then
  echo "  found in a context file"
else
  echo "  ABSENT from every dfII context -- deferred-init injection cannot work on this build"
fi
run_probe cdsinit MODE=gui

echo "### MANIFEST AFTER"
echo "  md5 mismatches (blank means every file identical):"
md5sum -c "$M/gap_cells_before.md5" 2>&1 | grep -v ': OK$' | sed 's/^/    CHANGED /'
ls -A "$P/cadence_work" | sort > "$M/gap_cw_after.txt"
echo "  cadence_work top-level diff:"
diff "$M/gap_cw_before.txt" "$M/gap_cw_after.txt" | sed 's/^/    CW /'
echo "  locks created: $(find "$P/cadence_work/microled_cells" -name '*.cdslck' | wc -l)"
find "$P/cadence_work/microled_cells" -name '*.cdslck' -printf '    LOCK %p\n' | head -5
echo "  ADE/setup objects that appeared inside the library:"
find "$P/cadence_work/microled_cells" -newer "$M/marker_cdsinit" -printf '    NEW_OR_TOUCHED %p\n' | head -10
md5sum "$P/cadence_work/microled_cells/c2mos_dff_1bit/schematic/sch.oa" \
       "$P/cadence_work/microled_cells/c2mos_dff_tb/schematic/sch.oa" | sed 's/^/  FINGERPRINT_AFTER /'
echo "  analogLib_files_newer_than_2026-10-12=$(find /opt/IC617/tools/dfII/etc/cdslib/artist/analogLib -type f -newermt 2026-10-12 2>/dev/null | wc -l)"
echo "  PDK_files_newer_than_2026-10-12=$(find /root/tech/teacher_pdk -type f -newermt 2026-10-12 2>/dev/null | wc -l)"
echo "  virtuoso_pids_end=[$(ps -eo pid,args | grep -E '/opt/IC617.*/virtuoso' | grep -v grep | awk '{print $1}' | tr '\n' ' ')]"
echo GAPRUN_DONE
