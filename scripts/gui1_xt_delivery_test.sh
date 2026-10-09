#!/bin/bash
# GUI-1: decide the delivery channel by measuring it with a client this script can actually paint.
#
#   DISPLAY=:0 bash scripts/gui1_xt_delivery_test.sh
#
# Why an Xt client and not Cadence: measured in scripts/gui1_verify_theme.sh, a batch-driven Virtuoso
# session has no painted window to sample -- the CIW reports "Map State: IsUnMapped" (so import
# fails) and the graphics window Cadence creates is never repainted until a cellview is drawn in it
# (its interior read 100% black in every run, themed or not). So the delivery question cannot be
# answered through Cadence here, but it can be answered through any Motif/Xt client, and the answer
# decides which channel the launcher may use:
#
#   XENVIRONMENT honoured -> keep the project-scoped XENVIRONMENT, nothing else is touched
#   XENVIRONMENT inert    -> the launcher must use xrdb, which Cadence's own sample resource file
#                            recommends anyway ("you need to run the xrdb program to have a
#                            resource take effect once the X server has been started"), and that is
#                            a session-wide change to back up and to disclose
#
# Each probe window gets its own -title so it is found by name: an earlier version of this script
# matched the first "xmessage" line of xwininfo and measured a leftover window from the previous run,
# which made three different configurations look identical.
set -u
DIO="${DISPLAY:-}"
[ -n "$DIO" ] || { echo "REFUSE: set DISPLAY explicitly"; exit 9; }
export DISPLAY="$DIO"
[ -n "${XAUTHORITY:-}" ] || [ ! -f /root/.Xauthority ] || export XAUTHORITY=/root/.Xauthority
for c in xmessage import convert xwininfo; do
  command -v "$c" >/dev/null 2>&1 || { echo "TOOL_MISSING: $c"; exit 9; }
done

printf 'Xmessage*background: #ffffff\n' > /tmp/gui1_xt_white.ad
printf 'Xmessage*background: #0000ff\n' > /tmp/gui1_xt_blue.ad

measure_one() {   # $1 tag  $2 XENVIRONMENT file or empty
  local tag="$1" xenv="$2" title="XTPROBE_$1" wid png mean line
  if [ -n "$xenv" ]; then
    XENVIRONMENT="$xenv" xmessage -title "$title" -geometry 260x120+60+60 "$tag" &
  else
    xmessage -title "$title" -geometry 260x120+60+60 "$tag" &
  fi
  sleep 2
  line=$(xwininfo -tree -root 2>/dev/null | grep -F "\"$title\"" | head -1)
  wid=$(printf '%s\n' "$line" | sed -n 's/^[[:space:]]*\(0x[0-9a-f]*\)[[:space:]].*/\1/p')
  png="/tmp/gui1_xt_${tag}.png"
  if [ -n "$wid" ] && import -window "$wid" "png:$png" 2>/dev/null && [ -s "$png" ]; then
    mean=$(convert "$png" -gravity center -crop 60%x60%+0+0 +repage -resize 1x1! -depth 8 \
             -format '%[pixel:p{0,0}]' info:- 2>/dev/null)
    printf 'XT_%-8s window=%s interior=%s\n' "$tag" "$wid" "${mean:-unreadable}"
  else
    printf 'XT_%-8s NO_WINDOW_OR_NO_CAPTURE (title=%s id=%s)\n' "$tag" "$title" "${wid:-none}"
  fi
  pkill -f "xmessage -title $title" 2>/dev/null
  sleep 1
}

measure_one plain ""
measure_one white /tmp/gui1_xt_white.ad
measure_one blue  /tmp/gui1_xt_blue.ad
echo "EXPECTED_IF_XENVIRONMENT_WORKS: plain=stock, white=srgb(255,255,255), blue=srgb(0,0,255)"
a=$(xdpyinfo 2>/dev/null | grep -m1 'dimensions:')
echo "XSERVER $a"
