#!/usr/bin/env bash
# push_chunked.sh <hostFile> <guestAbsPath>  -- install one file when SSH is unreachable.
#
# Why this exists: the guest has no IP right now (vmrun getGuestIPAddress fails), so the SSH/scp route
# is out; vmrun copyFileFromHostToGuest returns "the filename is invalid" on this host, and a base64
# payload bigger than a few KB overflows the vmrun argv (spawn ENAMETOOLONG). So the file goes over the
# Tools RPC channel in small chunks, is reassembled in /tmp, and is only moved into place after its
# md5 has been read back and compared. LF-normalised on the way out, like sync2guest.sh does.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# = 2 ] || { echo "usage: push_chunked.sh <hostFile> <guestAbsPath>"; exit 9; }
SRC="$1"; DST="$2"
[ -f "$SRC" ] || { echo "no such file: $SRC"; exit 9; }

tmp="$(mktemp)"
tr -d '\r' < "$SRC" > "$tmp"
hostmd5=$(md5sum "$tmp" | cut -d' ' -f1)
b="$(base64 -w0 "$tmp")"
tag="push_$$_$(printf '%s' "$DST" | cksum | cut -d' ' -f1)"
g="/tmp/${tag}.b64"

# first call truncates; the rest append. 1800 bytes of base64 stays well inside the argv limit.
i=0
sent=0
for ((o=0; o<${#b}; o+=1800)); do
  c="${b:o:1800}"
  if [ "$i" = 0 ]; then op=">"; else op=">>"; fi
  out=$(bash "$HERE/guest.sh" run "printf %s '$c' $op $g; wc -c < $g" 90 2>&1)
  case "$out" in *"killed (timeout)"|*"bridge-error"*) echo "CHUNK $i FAILED: $out"; exit 9;; esac
  i=$((i+1)); sent=$((sent+${#c}))
done
echo "chunks=$i b64bytes=$sent"

final=$(bash "$HERE/guest.sh" run "base64 -d $g > $g.bin 2>/dev/null || { echo DECODE_FAIL; exit 1; }; \
  mkdir -p \"\$(dirname $DST)\"; cp -f $g.bin $DST || { echo COPY_FAIL; exit 1; }; \
  rm -f $g $g.bin; md5sum $DST | cut -d' ' -f1" 90 2>&1)
echo "host_md5=$hostmd5"
echo "guest_md5=$final"
case "$final" in *"$hostmd5"*) echo "PUSH_OK $DST"; exit 0;; esac
echo "PUSH_MD5_MISMATCH"; exit 1
