#!/usr/bin/env bash
# Convenience wrapper around the vmrun-based bridge.
# Credentials are read from the environment and are never written to disk:
#   export QODER_GUEST_USER=root
#   export QODER_GUEST_PW='<password>'
#
#   guest.sh run   "<shell command>" [timeoutSec]     -> runs in guest, prints stdout+stderr
#   guest.sh push  <hostFile> <guestAbsPath>          -> uploads one file
#   guest.sh pull  <guestAbsPath> <hostFile>          -> downloads one file
#   guest.sh ssh   "<command>"                        -> runs over SSH (key auth, login shell env)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
b64() { printf '%s' "$1" | base64 -w0; }

# Credentials: env wins; otherwise read the local-only file (never committed).
if [ -z "${QODER_GUEST_PW:-}" ] && [ -f "$HERE/../.ic617_agent_bridge_credentials" ]; then
  # shellcheck disable=SC1091
  . "$HERE/../.ic617_agent_bridge_credentials"
  export QODER_GUEST_USER QODER_GUEST_PW QODER_GUEST_IP
fi

# Default the SSH key to the bridge key; OpenSSH_5.3 cannot use ed25519.
export QODER_SSH_KEY="${QODER_SSH_KEY:-$HOME/.ssh/id_rsa_ic617}"

case "${1:-}" in
  run)
    shift
    node "$HERE/vmguest.mjs" "${1:?command required}" "${2:-120}"
    ;;
  push)
    shift
    [ $# -ge 2 ] || { echo "usage: guest.sh push <hostFile> <guestAbsPath>"; exit 9; }
    QODER_MODE=push QODER_SRC_B64="$(b64 "$(cygpath -w "$1")")" QODER_DST_B64="$(b64 "$2")" \
      node "$HERE/vmfile.mjs"
    ;;
  pull)
    shift
    [ $# -ge 2 ] || { echo "usage: guest.sh pull <guestAbsPath> <hostFile>"; exit 9; }
    QODER_MODE=pull QODER_SRC_B64="$(b64 "$1")" QODER_DST_B64="$(b64 "$(cygpath -w "$2")")" \
      node "$HERE/vmfile.mjs"
    ;;
  ssh)
    shift
    CMD="${1:?command required}"
    IP="${QODER_GUEST_IP:-}"
    KEY="${QODER_SSH_KEY:-$HOME/.ssh/id_rsa_ic617}"
    [ -n "$IP" ] || { echo "[guest.sh] QODER_GUEST_IP is not set" >&2; exit 9; }
    # RHEL6 ships OpenSSH_5.3, which only offers ssh-rsa/ssh-dss host keys; those
    # SHA-1 algorithms are disabled by default in OpenSSH >= 8.8, so they are
    # re-enabled for THIS connection only. No global SSH config is touched.
    opts=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new
          -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa
          -i "$KEY")
    p=$(printf '%s' "$CMD" | base64 -w0)
    f="qoder_$$_$(date +%s).sh"
    ssh "${opts[@]}" "root@$IP" "umask 077; printf '%s' '$p' | base64 -d > /tmp/$f; bash -l /tmp/$f; rc=\$?; rm -f /tmp/$f; exit \$rc"
    ;;
  *)
    grep '^#' "$0" | sed 's/^# \{0,1\}//'
    exit 9
    ;;
esac
