#!/usr/bin/env python3
# repo_parity.py -- compare the Windows mirror against the guest project tree.
#
#   python scripts/repo_parity.py /tmp/guest_md5.txt
#
# guest_md5.txt lines are "<md5>  <relative/path>" as produced by
#   cd /root/microled_ai_project && find . -type f ... | xargs md5sum
#
# Windows-authored files are CRLF while the guest files are LF, so a byte-for-byte
# compare would report every file as different. The checksum used here is taken over
# the content with CR stripped, which is exactly the transformation sync2guest.sh
# applies on the way to the guest, so "same" means "same file, different line ending".
#
# Reports four buckets: same / differ (both sides exist, content differs) /
# only_guest (must be pulled) / only_host (Windows-only bridge infra, or drift).
import hashlib
import os
import sys

HOST_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Windows-side directories that mirror the guest under a different prefix
HOST_PREFIX_ALIAS = {"microled/": ""}
IGNORE_TOP = {"pdk", "home", "skill_run", "spectre_smoke_raw", ".git"}


def norm_md5(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.md5(data.replace(b"\r\n", b"\n")).hexdigest()


def host_files():
    out = {}
    for dirpath, dirnames, filenames in os.walk(HOST_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", "sim", ".vnc-cds", "home")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, HOST_ROOT).replace("\\", "/")
            if rel.split("/")[0] in IGNORE_TOP:
                continue
            out[rel] = norm_md5(full)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: repo_parity.py <guest_md5.txt>")
        return 9
    guest = {}
    with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 2:
                guest[parts[1]] = parts[0]
    host = host_files()

    same, differ, only_guest, only_host = [], [], [], []
    for rel, dig in sorted(guest.items()):
        h = host.get(rel)
        if h is None:
            for pre, _sub in HOST_PREFIX_ALIAS.items():
                if host.get(pre + rel) is not None:
                    h = host[pre + rel]
                    break
        if h is None:
            only_guest.append(rel)
        elif h == dig:
            same.append(rel)
        else:
            differ.append(rel)
    guest_names = set(guest)
    aliased = set("microled/" + r for r in guest)
    for rel, dig in sorted(host.items()):
        if rel not in guest_names and rel not in aliased and rel not in guest:
            only_host.append(rel)

    for name, lst in (("SAME", same), ("DIFFER", differ),
                      ("ONLY_GUEST (pull me)", only_guest), ("ONLY_HOST", only_host)):
        print("== %s: %d" % (name, len(lst)))
        for r in lst:
            print("   " + r)
    print("SUMMARY guest=%d host=%d same=%d differ=%d only_guest=%d only_host=%d"
          % (len(guest), len(host), len(same), len(differ), len(only_guest), len(only_host)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
