#!/bin/bash
# SCH-1 read-only environment probe: what does the ALREADY RUNNING Virtuoso session
# actually see, and what desktop-launch machinery exists on this RHEL6 GNOME session.
# Prints no license values (CDS_LIC_FILE / LM_LICENSE_FILE are deliberately not read out).
set -u
VPID="${1:-}"

echo "## running virtuoso"
ps -eo pid,args | grep -E '/opt/IC617.*/virtuoso' | grep -v grep | head -3

if [ -n "$VPID" ]; then
  echo "## pid $VPID cwd"
  ls -l "/proc/$VPID/cwd" 2>/dev/null | sed 's/.*-> //'
  echo "## pid $VPID non-license env"
  tr '\0' '\n' < "/proc/$VPID/environ" 2>/dev/null | grep -E '^(DISPLAY|HOME|USER|PWD|CDS_LIB_PATH|OA_HOME|MMSIM_ROOT|CDS)=' | head -10
  echo "## cds.lib candidates it could have used"
  for f in /root/Desktop/cds.lib /root/cds.lib /root/.cdslib; do
    printf '%s : ' "$f"; [ -f "$f" ] && { echo present; grep -vE '^\s*(#|$)' "$f" | head -8 | sed 's/^/     /'; } || echo absent
  done
  echo "## library dirs open in that session (from its log if findable)"
  ls -1t /root/*.log /root/virtuoso*.log /root/Desktop/*.log 2>/dev/null | head -5
fi

echo "## desktop launch machinery"
for c in gnome-open gio desktop-file-install desktop-file-validate nautilus xlsclients xset; do
  p=$(command -v "$c" 2>/dev/null)
  echo "  $c=${p:-none}"
done

echo "## /root/Desktop contents"
ls -la /root/Desktop 2>/dev/null | head -12

echo "## existing .desktop files for cadence, if any (system launchers are read-only here)"
grep -rl -i "virtuoso" /usr/share/applications 2>/dev/null | head -5

echo "## icon candidates"
for i in /usr/share/icons/hicolor/48x48/apps/gnome-applications.png \
         /usr/share/pixmaps/fedora-logo-icon.png /usr/share/icons/gnome/48x48/apps/applications.png; do
  printf '%s : ' "$i"; [ -f "$i" ] && echo present || echo absent
done

echo "## project skill/cad_env.sh and site libs"
ls -1 /root/microled_ai_project/skill/cad_env.sh 2>/dev/null || echo "cad_env.sh missing in project"
for d in /opt/IC617/tools/dfII/etc/cdsDefTechLib /opt/IC617/tools/dfII/etc/cdslib/basic \
         /opt/IC617/tools/dfII/etc/cdslib/artist/analogLib; do
  printf '%s : ' "$d"; [ -d "$d" ] && echo present || echo absent
done

echo "## teacher PDK kit layout (read-only)"
K=/root/microled_ai_project/pdk/smic18mmrf_teacher
ls -1 "$K" 2>/dev/null | head -12
echo "  -- kit cds.lib --"
grep -vE '^\s*(#|$)' "$K/cds.lib" 2>/dev/null | head -10
echo "  -- lib.defs anywhere in kit --"
find "$K" -maxdepth 3 -name 'lib.defs' 2>/dev/null | head -5

echo "## old /root/tech PDK identity"
ls -1d /root/tech/* 2>/dev/null | head -8
grep -vE '^\s*(#|$)' /root/tech/smic_018mmrf-OA/smic_018mmrf-OA/SMIC_018_MMRF/cds.lib 2>/dev/null | head -6
echo "SCH1_ENV_PROBE_DONE"
