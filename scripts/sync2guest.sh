#!/usr/bin/env bash
# sync2guest.sh <hostFile>... -- install project files into the guest, LF-normalised.
#
#   mirrors the path under D:/ic617_agent_bridge to /root/microled_ai_project, e.g.
#     spectre/C2MOS_DFF.scs  ->  /root/microled_ai_project/spectre/C2MOS_DFF.scs
#     scripts/c2mos_check.sh ->  /root/microled_ai_project/scripts/c2mos_check.sh
#
# Why the staging step: the files are authored on Windows and arrive CRLF. Spectre
# tolerates CRLF in a netlist, bash and awk do not -- a CR inside a `while read` loop
# or an awk pattern silently changes behaviour. So everything goes through
# /tmp first and is stripped on the way into the project.
#
# Nothing outside /root/microled_ai_project is written; existing PDK/library files are
# never a valid argument here (the destination path is forced under $PROJ).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
[ $# -ge 1 ] || { echo "usage: sync2guest.sh <hostFile>..."; exit 9; }

# shellcheck disable=SC1091
. "$HERE/../.ic617_agent_bridge_credentials"
export QODER_GUEST_USER QODER_GUEST_PW QODER_GUEST_IP
KEY="${QODER_SSH_KEY:-$HOME/.ssh/id_rsa_ic617}"
PROJ="${PROJ:-/root/microled_ai_project}"
OPTS=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new
      -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAcceptedKeyTypes=+ssh-rsa -i "$KEY")

stage=/tmp/qoder_sync_$$
ssh "${OPTS[@]}" "root@${QODER_GUEST_IP}" "mkdir -p '$stage'" || exit 9

names=(); finals=(); dests=(); modes=()
for f in "$@"; do
  abs="$(cd "$(dirname "$f")" && pwd)/$(basename "$f")"
  case "$abs" in
    "$ROOT"/*) ;;
    *) echo "REFUSED: $f is not inside $ROOT"; exit 9 ;;
  esac
  rel="${abs#"$ROOT"/}"
  rel="${rel//\\//}"
  # The staging area is flat, so the file name alone would collide the moment two arguments share a
  # basename (cadence_work/appearance/white/xresources.txt and .../original/xresources.txt did exactly
  # this: both destinations got whichever file was uploaded last, silently). Stage under the index.
  idx="${#names[@]}"
  names+=("$stage/$idx--$(basename "$abs")")
  finals+=("$(basename "$abs")")
  dests+=("$PROJ/$(dirname "$rel")")
  # The destination mode comes from the repository, never from a hardcoded 644. This is what broke the
  # desktop icon: GUI-1 synced an edited cadence_work/launch_virtuoso.sh, this script forced mode 644
  # on it, and the .desktop Exec/TryExec both need that file executable -- GNOME's execv got EACCES
  # and reported "There was an error launching the application." while `bash -n` and LAUNCHER_CHECK
  # both kept passing. git mode 100755 -> 755.
  gmode=$(git -C "$ROOT" ls-files -s -- "$rel" 2>/dev/null | awk '{print $1; exit}')
  case "$gmode" in
    100755) modes+=("755") ;;
    *)      modes+=("644") ;;
  esac
  scp "${OPTS[@]}" "$abs" "root@${QODER_GUEST_IP}:${names[$idx]}" || exit 9
done

for i in "${!names[@]}"; do
  n="${names[$i]}"; f="${finals[$i]}"; d="${dests[$i]}"; m="${modes[$i]}"
  ssh "${OPTS[@]}" "root@${QODER_GUEST_IP}" \
    "mkdir -p '$d' && sed 's/\r\$//' '$n' > '$d/$f' && chmod $m '$d/$f' && ls -l '$d/$f'"
done
ssh "${OPTS[@]}" "root@${QODER_GUEST_IP}" "chmod +x $PROJ/scripts/*.sh 2>/dev/null; rm -rf '$stage'"
echo "SYNC done -> $PROJ"
