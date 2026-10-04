#!/usr/bin/env python
# Build a manifest (relative path, size, crc32) of a directory tree.
# Used to compare the teacher's PDK zip against the copy inside the VM.
# Read-only: it never writes outside --out.
# Python 2.6 and 3 compatible (guest RHEL6 ships 2.6.6).
from __future__ import print_function
import hashlib
import json
import os
import sys
try:
    import zlib                      # py2.6 has zlib.crc32
except ImportError:
    zlib = None


def crc32(path):
    if zlib is None:
        return None
    c = 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            c = zlib.crc32(b, c)
    return '%08X' % (c & 0xffffffff)


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest().upper()


def main():
    if len(sys.argv) < 3:
        print('usage: tree_manifest.py <root_dir> <out.json> [--md5]')
        return 9
    root = os.path.abspath(sys.argv[1])
    out = sys.argv[2]
    use_md5 = '--md5' in sys.argv[3:]
    files = {}
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, '/')
        if rel_dir == '.':
            rel_dir = ''
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = (rel_dir + '/' + fn) if rel_dir else fn
            try:
                st = os.stat(full)
            except OSError:
                skipped += 1
                continue
            if not os.path.isfile(full):
                skipped += 1
                continue
            rec = {'size': st.st_size, 'crc': crc32(full)}
            if use_md5:
                rec['md5'] = md5(full)
            files[rel] = rec
    data = {'root': root, 'host': os.uname()[1] if hasattr(os, 'uname') else 'win',
            'files': files, 'skipped': skipped}
    with open(out, 'w') as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write('\n')
    print('root=%s files=%d skipped=%d -> %s' % (root, len(files), skipped, out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
