#!/bin/bash
# GUI-2: run a program with the GNOME session's OWN environment, the way a desktop double-click
# would. env(1) consumes the NUL-separated KEY=VALUE entries read straight out of
# /proc/<gnome-session>/environ, so nothing is re-quoted and nothing can drift.
#
#   gui2_envexec.sh <program> [args...]
#
# This exists because the desktop PATH starts with /etc/env -- the directory holding the
# /etc/env/virtuoso wrapper -- and a test run from a plain ssh shell has a different PATH. Only a
# launch with the real session environment can show which virtuoso the launcher actually resolves.
set -u
PROG="${1:?usage: gui2_envexec.sh <program> [args...]}"
shift
GP=$(pgrep -f gnome-session | head -1)
[ -n "$GP" ] || { echo "ENVEXEC: FAIL (no gnome-session process)"; exit 9; }
[ -r "/proc/$GP/environ" ] || { echo "ENVEXEC: FAIL (cannot read /proc/$GP/environ)"; exit 9; }
echo "ENVEXEC_SESSION_PID=$GP"
# inner sh: $1 = program, remaining args = the environment entries appended by xargs
exec xargs -0 -a "/proc/$GP/environ" sh -c '
  P="$1"
  shift
  [ $# -gt 0 ] || { echo "ENVEXEC: FAIL (no session environment entries)"; exit 9; }
  exec env "$@" "$P"
' sh "$PROG" "$@"
